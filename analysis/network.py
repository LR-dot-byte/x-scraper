#!/usr/bin/env python3
"""构建年度关注或评论有向网络并计算论文所述网络指标。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import networkx as nx
import pandas as pd


VALID_YEARS = set(range(2021, 2026))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def relationship_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"找不到关系文件或目录：{path}")
    files = sorted(
        item
        for item in path.iterdir()
        if item.is_file()
        and item.suffix.lower() in {".csv", ".xlsx", ".xls"}
        and not item.name.startswith(("~$", "."))
    )
    if not files:
        raise FileNotFoundError(f"目录中没有 CSV/XLSX 关系文件：{path}")
    return files


def infer_year(path: Path) -> int | None:
    match = re.search(r"(?<!\d)(202[1-5])(?!\d)", path.stem)
    return int(match.group(1)) if match else None


def normalize_id(series: pd.Series) -> pd.Series:
    values = (
        series.astype("string")
        .str.strip()
        .str.replace(r"^https?://(?:www\.)?(?:x|twitter)\.com/", "", regex=True)
        .str.replace(r"/.*$", "", regex=True)
        .str.lstrip("@")
        .str.lower()
    )
    return values.where(values.isna() | values.eq(""), "@" + values)


def standardize_columns(
    data: pd.DataFrame, network_type: str, fallback_year: int | None
) -> pd.DataFrame:
    data = data.copy()
    data.columns = [str(column).strip() for column in data.columns]
    # 实际关注表格式：send 为被采集账号，followers 为其关注者。
    # 有向边按“关注者 → 被关注账号”构造。
    if network_type == "follow" and {"send", "followers"}.issubset(data.columns):
        data["source"] = data["followers"]
        data["target"] = data["send"]
    aliases = {
        "年份": "year",
        "源账号": "source",
        "关注者ID": "source",
        "评论者ID": "source",
        "目标账号": "target",
        "被关注者ID": "target",
        "原帖作者ID": "target",
        "评论时间": "time",
    }
    data = data.rename(columns={column: aliases.get(column, column) for column in data})
    if "year" not in data and "time" in data:
        data["year"] = pd.to_datetime(data["time"], errors="coerce", format="mixed").dt.year
    if "year" not in data and fallback_year is not None:
        data["year"] = fallback_year
    required = {"year", "source", "target"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"{network_type}关系表缺少字段：{sorted(missing)}")
    result = pd.DataFrame(
        {
            "year": pd.to_numeric(data["year"], errors="coerce").astype("Int64"),
            "source": normalize_id(data["source"]),
            "target": normalize_id(data["target"]),
        }
    )
    result["weight"] = (
        pd.to_numeric(data["weight"], errors="coerce").fillna(1).clip(lower=1)
        if "weight" in data
        else 1
    )
    return result


def read_nodes(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    data = read_table(path)
    aliases = {"年份": "year", "账号ID": "account_id", "节点ID": "account_id"}
    data = data.rename(columns={column: aliases.get(str(column).strip(), str(column).strip()) for column in data})
    if "account_id" not in data:
        raise ValueError("节点表至少需要 account_id（或“账号ID”）字段")
    result = pd.DataFrame({"account_id": normalize_id(data["account_id"])})
    result["year"] = (
        pd.to_numeric(data["year"], errors="coerce").astype("Int64") if "year" in data else pd.NA
    )
    return result.dropna(subset=["account_id"]).drop_duplicates()


def average_directed_reachable_path(graph: nx.DiGraph) -> tuple[float, int]:
    distance_sum = 0
    pair_count = 0
    for source, lengths in nx.all_pairs_shortest_path_length(graph):
        for target, distance in lengths.items():
            if source != target:
                distance_sum += distance
                pair_count += 1
    return (distance_sum / pair_count if pair_count else 0.0), pair_count


def build_graph(rows: pd.DataFrame, node_ids: list[str]) -> tuple[nx.DiGraph, pd.DataFrame, int]:
    rows = rows.dropna(subset=["source", "target"]).copy()
    rows = rows[rows["source"].ne("") & rows["target"].ne("")]
    self_loops = int(rows["source"].eq(rows["target"]).sum())
    rows = rows[rows["source"].ne(rows["target"])]
    weighted = rows.groupby(["source", "target"], as_index=False)["weight"].sum()
    graph = nx.DiGraph()
    graph.add_nodes_from(node_ids)
    for row in weighted.itertuples(index=False):
        graph.add_edge(row.source, row.target, weight=float(row.weight))
    return graph, weighted, self_loops


def analyze_year(year: int, rows: pd.DataFrame, node_ids: list[str], seed: int):
    graph, weighted, self_loops = build_graph(rows, node_ids)
    undirected = graph.to_undirected()
    avg_path, reachable_pairs = average_directed_reachable_path(graph)
    nontrivial_components = [
        component for component in nx.connected_components(undirected) if len(component) > 1
    ]
    if nontrivial_components:
        largest = undirected.subgraph(max(nontrivial_components, key=len))
        undirected_path = nx.average_shortest_path_length(largest)
    else:
        undirected_path = 0.0
    if undirected.number_of_edges():
        communities = nx.community.louvain_communities(undirected, weight=None, seed=seed)
        modularity = nx.community.modularity(undirected, communities, weight=None)
    else:
        communities, modularity = [], 0.0

    reciprocated_directed_edges = sum(1 for source, target in graph.edges if graph.has_edge(target, source))
    mutual_share = (
        reciprocated_directed_edges / graph.number_of_edges() if graph.number_of_edges() else 0.0
    )
    metric = {
        "year": year,
        "nodes": graph.number_of_nodes(),
        "directed_edges": graph.number_of_edges(),
        "interaction_weight_total": float(sum(data["weight"] for _, _, data in graph.edges(data=True))),
        "self_loops_excluded": self_loops,
        "density": float(nx.density(graph)),
        "average_path_length_directed_reachable_pairs": float(avg_path),
        "reachable_ordered_pairs": reachable_pairs,
        "average_path_length_undirected_largest_component": float(undirected_path),
        "average_clustering_undirected_unweighted": float(
            nx.average_clustering(undirected) if graph.number_of_nodes() else 0.0
        ),
        "average_clustering_directed_fagiolo_unweighted": float(
            nx.average_clustering(graph) if graph.number_of_nodes() else 0.0
        ),
        "modularity_louvain_undirected_unweighted": float(modularity),
        "mutual_relationship_share": float(mutual_share),
        "reciprocal_dyads": int(reciprocated_directed_edges // 2),
        "weak_components": nx.number_weakly_connected_components(graph) if graph else 0,
        "communities": len(communities),
    }

    in_degree = nx.in_degree_centrality(graph)
    out_degree = nx.out_degree_centrality(graph)
    betweenness = nx.betweenness_centrality(graph, normalized=True, weight=None)
    closeness_in = nx.closeness_centrality(graph)
    closeness_out = nx.closeness_centrality(graph.reverse(copy=False))
    node_rows = []
    denominator = 2 * (graph.number_of_nodes() - 1) if graph.number_of_nodes() > 1 else 1
    for node in graph.nodes:
        node_rows.append(
            {
                "year": year,
                "account_id": node,
                "in_degree": graph.in_degree(node),
                "out_degree": graph.out_degree(node),
                "degree_centrality_total": graph.degree(node) / denominator,
                "in_degree_centrality": in_degree[node],
                "out_degree_centrality": out_degree[node],
                "betweenness_centrality": betweenness[node],
                "closeness_centrality_in": closeness_in[node],
                "closeness_centrality_out": closeness_out[node],
            }
        )
    return metric, pd.DataFrame(node_rows), weighted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--follow-edges", type=Path, help="关注关系边表，至少含 year,source,target")
    source.add_argument("--comments", type=Path, help="评论关系表，可用评论时间推导年份")
    parser.add_argument("--nodes", type=Path, help="可选节点名册；关注网络应传入206个样本以保留孤立节点")
    parser.add_argument(
        "--year",
        type=int,
        choices=range(2021, 2026),
        metavar="2021-2025",
        help="当关系文件没有年份列时，为该文件指定年度",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--seed", type=int, default=2244313043)
    parser.add_argument(
        "--write-node-results",
        action="store_true",
        help="导出节点中心性和加权边；默认关闭，避免复制账号级研究数据",
    )
    args = parser.parse_args()

    network_type = "follow" if args.follow_edges else "comment"
    input_path = args.follow_edges or args.comments
    if not input_path or not input_path.exists():
        raise FileNotFoundError(f"找不到关系表或目录：{input_path}")
    output = args.output_dir or project_root() / "analysis" / "outputs" / "network"
    output.mkdir(parents=True, exist_ok=True)

    files = relationship_files(input_path)
    raw_parts, edge_parts = [], []
    for path in files:
        raw_part = read_table(path)
        raw_parts.append(raw_part)
        edge_parts.append(
            standardize_columns(raw_part, network_type, args.year or infer_year(path))
        )
    raw = pd.concat(raw_parts, ignore_index=True, sort=False)
    edges = pd.concat(edge_parts, ignore_index=True, sort=False)
    nodes = read_nodes(args.nodes)
    invalid_years = int((~edges["year"].isin(VALID_YEARS)).sum())
    edges = edges[edges["year"].isin(VALID_YEARS)].copy()
    missing_endpoints = int(edges[["source", "target"]].isna().any(axis=1).sum())
    edges = edges.dropna(subset=["source", "target"])
    if network_type == "follow":
        edges = edges.drop_duplicates(["year", "source", "target"])

    metrics, node_results, weighted_results = [], [], []
    for year in sorted(int(value) for value in edges["year"].unique()):
        if nodes is None:
            node_ids = sorted(set(edges.loc[edges["year"].eq(year), ["source", "target"]].stack()))
        elif nodes["year"].notna().any():
            node_ids = nodes.loc[nodes["year"].eq(year), "account_id"].tolist()
        else:
            node_ids = nodes["account_id"].tolist()
        metric, node_frame, weighted = analyze_year(
            year, edges[edges["year"].eq(year)], node_ids, args.seed + year
        )
        metrics.append(metric)
        node_results.append(node_frame)
        weighted.insert(0, "year", year)
        weighted_results.append(weighted)

    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(output / f"{network_type}_network_metrics_by_year.csv", index=False)
    metadata = {
        "network_type": network_type,
        "input_files": [str(path) for path in files],
        "input_rows": int(len(raw)),
        "valid_edge_rows": int(len(edges)),
        "invalid_or_out_of_range_year_rows": invalid_years,
        "missing_endpoint_rows_after_year_filter": missing_endpoints,
        "node_roster_used": bool(nodes is not None),
        "node_level_results_written": bool(args.write_node_results),
        "method": (
            "有向网络密度；有向可达节点对及最大无向连通分量两种平均最短路径；"
            "无向投影与Fagiolo有向两种未加权平均聚类系数；"
            "Louvain无向未加权模块度；相互关系占全部有向边的比例；"
            "节点层计算入度、出度、总度、中介和入/出接近中心性。"
        ),
        "caveat": (
            "未传入节点名册，孤立节点不会进入分母；正式复现206账号关注网络时必须使用 --nodes。"
            if nodes is None
            else "已使用节点名册，名册中的孤立节点进入网络规模与密度分母。"
        ),
    }
    (output / "network_run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.write_node_results:
        pd.concat(node_results, ignore_index=True).to_csv(
            output / f"{network_type}_node_centralities_private.csv",
            index=False,
            encoding="utf-8-sig",
        )
        pd.concat(weighted_results, ignore_index=True).to_csv(
            output / f"{network_type}_weighted_edges_private.csv",
            index=False,
            encoding="utf-8-sig",
        )
    print(metrics_frame.to_string(index=False))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
