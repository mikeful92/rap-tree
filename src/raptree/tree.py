"""Neighbor-joining trees, midpoint rooting, split support, Newick/JSON output."""

from collections import Counter, defaultdict

import numpy as np

Adjacency = dict[int, list[tuple[int, float]]]


def neighbor_joining(D: np.ndarray) -> Adjacency:
    """Unrooted NJ tree (Saitou & Nei 1987). Leaves are nodes 0..n-1."""
    n = len(D)
    adj: Adjacency = defaultdict(list)
    if n == 2:
        adj[0].append((1, D[0, 1]))
        adj[1].append((0, D[0, 1]))
        return adj
    active = list(range(n))
    sub = np.array(D, float)
    next_id = n
    while len(active) > 2:
        m = len(active)
        r = sub.sum(axis=1)
        Q = (m - 2) * sub - r[:, None] - r[None, :]
        np.fill_diagonal(Q, np.inf)
        i, j = np.unravel_index(np.argmin(Q), Q.shape)
        li = 0.5 * sub[i, j] + (r[i] - r[j]) / (2 * (m - 2))
        li = max(li, 0.0)
        lj = max(sub[i, j] - li, 0.0)
        u = next_id
        next_id += 1
        for node, length in ((active[i], li), (active[j], lj)):
            adj[u].append((node, length))
            adj[node].append((u, length))
        d_new = 0.5 * (sub[i] + sub[j] - sub[i, j])
        keep = [k for k in range(m) if k not in (i, j)]
        new = np.zeros((len(keep) + 1, len(keep) + 1))
        new[:-1, :-1] = sub[np.ix_(keep, keep)]
        new[-1, :-1] = new[:-1, -1] = d_new[keep]
        sub = new
        active = [active[k] for k in keep] + [u]
    a, b = active
    adj[a].append((b, max(sub[0, 1], 0.0)))
    adj[b].append((a, max(sub[0, 1], 0.0)))
    return adj


def _paths_from(adj: Adjacency, start: int) -> tuple[dict, dict]:
    dist, parent = {start: 0.0}, {start: None}
    stack = [start]
    while stack:
        u = stack.pop()
        for v, w in adj[u]:
            if v not in dist:
                dist[v], parent[v] = dist[u] + w, u
                stack.append(v)
    return dist, parent


def midpoint_root(adj: Adjacency, n_leaves: int) -> int:
    """Insert a root halfway along the longest leaf-to-leaf path; returns its id."""
    leaves = range(n_leaves)
    best = (-1.0, 0, 0)
    for a in leaves:
        dist, _ = _paths_from(adj, a)
        b = max(leaves, key=dist.__getitem__)
        best = max(best, (dist[b], a, b))
    total, a, b = best
    dist, parent = _paths_from(adj, a)
    # walk back from b towards a until we pass the midpoint
    v = b
    while dist[parent[v]] > total / 2:
        v = parent[v]
    u = parent[v]
    w = dict(adj[u])[v]
    x = total / 2 - dist[u]  # distance from u to the root
    root = max(adj) + 1
    adj[u] = [(k, l) for k, l in adj[u] if k != v] + [(root, x)]
    adj[v] = [(k, l) for k, l in adj[v] if k != u] + [(root, w - x)]
    adj[root] = [(u, x), (v, w - x)]
    return root


def rooted(adj: Adjacency, root: int) -> dict:
    """Nested {id, length, children} dict."""

    def build(node, parent, length):
        kids = [build(v, node, w) for v, w in adj[node] if v != parent]
        return {"id": node, "length": float(length), "children": kids}

    return build(root, None, 0.0)


def leafsets(node: dict, n_leaves: int) -> frozenset:
    """Annotate each node with its leaf set; returns the root's."""
    own = {node["id"]} if node["id"] < n_leaves else set()
    node["leaves"] = frozenset(own).union(*(leafsets(c, n_leaves) for c in node["children"]))
    return node["leaves"]


def canonical_split(leaves: frozenset, n: int) -> frozenset | None:
    """Unrooted bipartition key: the side not containing leaf 0. None if trivial."""
    if 0 in leaves:
        leaves = frozenset(range(n)) - leaves
    return leaves if 2 <= len(leaves) <= n - 2 else None


def splits(adj: Adjacency, n: int) -> set[frozenset]:
    tree = rooted(adj, 0)
    leafsets(tree, n)
    out = set()

    def walk(node):
        for c in node["children"]:
            s = canonical_split(c["leaves"], n)
            if s:
                out.add(s)
            walk(c)

    walk(tree)
    return out


def build_tree(D: np.ndarray, names: list[str], replicates: list[np.ndarray] = ()) -> dict:
    """Midpoint-rooted NJ tree of D, internal nodes labeled with the fraction
    of replicate trees that contain the same split."""
    n = len(names)
    counts: Counter = Counter()
    for R in replicates:
        counts.update(splits(neighbor_joining(R), n))

    adj = neighbor_joining(D)
    tree = rooted(adj, midpoint_root(adj, n))
    leafsets(tree, n)

    def label(node):
        out = {"length": round(node["length"], 6)}
        if node["children"]:
            s = canonical_split(node["leaves"], n)
            if s and replicates:
                out["support"] = round(counts[s] / len(replicates), 3)
            out["children"] = [label(c) for c in node["children"]]
        else:
            out["name"] = names[node["id"]]
        return out

    return label(tree)


def to_newick(node: dict) -> str:
    def fmt(nd):
        if "children" in nd:
            inner = "(" + ",".join(fmt(c) for c in nd["children"]) + ")"
            if "support" in nd:
                inner += f"{round(nd['support'] * 100)}"
        else:
            inner = "'" + nd["name"].replace("'", "''") + "'"
        return f"{inner}:{nd['length']:.6f}"

    return fmt(node) + ";"
