#!/usr/bin/env python3
"""按发帖时序、内容类型和网络中心性执行 K-means 角色聚类。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
ROLE_IDENTITY = {"触发者": "社会活动型", "偏引者": "学者型", "散逸者": "普通用户型"}
ALIASES = {
    "账号ID": "account_id",
    "类型": "identity_type",
    "形成期占比": "time_formation_share",
    "发展期占比": "time_development_share",
    "消弭期占比": "time_dissipation_share",
    "事实陈述占比": "content_fact_share",
    "情感表达占比": "content_emotion_share",
    "观点评论占比": "content_commentary_share",
    "转发评论互动占比": "content_repost_interaction_share",
    "度中心性": "centrality_degree",
    "中介中心性": "centrality_betweenness",
    "接近中心性": "centrality_closeness",
    "formation_share": "time_formation_share",
    "development_share": "time_development_share",
    "dissipation_share": "time_dissipation_share",
    "fact_share": "content_fact_share",
    "emotion_share": "content_emotion_share",
    "commentary_share": "content_commentary_share",
    "repost_interaction_share": "content_repost_interaction_share",
    "degree_centrality": "centrality_degree",
    "betweenness_centrality": "centrality_betweenness",
    "closeness_centrality": "centrality_closeness",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def feature_columns(data: pd.DataFrame) -> tuple[list[str], dict[str, list[str]]]:
    groups = {
        "time": [column for column in data if column.startswith("time_")],
        "content": [column for column in data if column.startswith("content_")],
        "centrality": [column for column in data if column.startswith("centrality_")],
    }
    empty = [name for name, columns in groups.items() if not columns]
    if empty:
        raise ValueError(
            "特征表必须同时包含 time_*、content_* 和 centrality_* 三组变量；"
            f"当前缺少：{empty}"
        )
    return groups["time"] + groups["content"] + groups["centrality"], groups


def read_features(path: Path) -> tuple[pd.DataFrame, list[str], dict[str, list[str]]]:
    data = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    data = data.rename(columns={column: ALIASES.get(str(column).strip(), str(column).strip()) for column in data})
    required = {"account_id", "identity_type"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"账号特征表缺少字段：{sorted(missing)}")
    if data["account_id"].isna().any() or data["account_id"].duplicated().any():
        raise ValueError("account_id 必须完整且每个账号仅出现一行")
    features, groups = feature_columns(data)
    for column in features:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[features].isna().any().any():
        bad = data[features].columns[data[features].isna().any()].tolist()
        raise ValueError(f"聚类变量含缺失或非数值：{bad}")
    share_columns = [
        column
        for column in groups["time"] + groups["content"]
        if column.endswith("_share") or column.endswith("_ratio")
    ]
    if ((data[share_columns] < 0) | (data[share_columns] > 1)).any().any():
        raise ValueError("时序占比和内容占比必须位于0至1")
    if (data[groups["centrality"]] < 0).any().any():
        raise ValueError("网络中心性不能为负数")
    return data, features, groups


def kmeans_pp(x: np.ndarray, k: int, seed: int, n_init: int = 50, max_iter: int = 500):
    best = None
    for run in range(n_init):
        rng = np.random.default_rng(seed + run)
        centers = [x[rng.integers(len(x))]]
        for _ in range(1, k):
            distance2 = np.min(
                np.stack([np.sum((x - center) ** 2, axis=1) for center in centers]), axis=0
            )
            centers.append(
                x[rng.integers(len(x))]
                if distance2.sum() == 0
                else x[rng.choice(len(x), p=distance2 / distance2.sum())]
            )
        centers = np.asarray(centers, dtype=float)
        labels = np.full(len(x), -1, dtype=int)
        for _ in range(max_iter):
            distances = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new_labels = distances.argmin(axis=1)
            if np.array_equal(labels, new_labels):
                break
            labels = new_labels
            for cluster in range(k):
                members = x[labels == cluster]
                if len(members):
                    centers[cluster] = members.mean(axis=0)
                else:
                    farthest = np.argmax(np.min(distances, axis=1))
                    centers[cluster] = x[farthest]
                    labels[farthest] = cluster
        inertia = float(np.sum((x - centers[labels]) ** 2))
        if best is None or inertia < best[0]:
            best = inertia, labels.copy(), centers.copy()
    return best


def silhouette(x: np.ndarray, labels: np.ndarray) -> float:
    clusters = sorted(set(labels))
    if len(clusters) < 2:
        return 0.0
    distances = np.sqrt(((x[:, None, :] - x[None, :, :]) ** 2).sum(axis=2))
    scores = []
    for index, label in enumerate(labels):
        same = labels == label
        same[index] = False
        if not same.any():
            scores.append(0.0)
            continue
        within = distances[index, same].mean()
        nearest = min(
            distances[index, labels == other].mean() for other in clusters if other != label
        )
        scores.append((nearest - within) / max(within, nearest) if max(within, nearest) else 0.0)
    return float(np.mean(scores))


def comb2(values: np.ndarray) -> float:
    return float(np.sum(values * (values - 1) / 2))


def adjusted_rand(labels_a: pd.Series, labels_b: np.ndarray) -> float:
    table = pd.crosstab(labels_a, labels_b).to_numpy()
    n = table.sum()
    if n < 2:
        return float("nan")
    cells = comb2(table)
    rows = comb2(table.sum(axis=1))
    columns = comb2(table.sum(axis=0))
    total = n * (n - 1) / 2
    expected = rows * columns / total
    maximum = (rows + columns) / 2
    return float((cells - expected) / (maximum - expected)) if maximum != expected else 1.0


def parse_role_map(value: str | None, k: int) -> dict[int, str]:
    if not value:
        return {}
    mapping = {}
    for item in value.split(","):
        try:
            cluster_text, role = item.split("=", 1)
            cluster = int(cluster_text.strip())
        except ValueError as error:
            raise ValueError("--role-map 格式应为 0=触发者,1=偏引者,2=散逸者") from error
        mapping[cluster] = role.strip()
    if set(mapping) != set(range(k)) or set(mapping.values()) != set(ROLE_IDENTITY):
        raise ValueError("--role-map 必须为每个簇各指定一次触发者、偏引者、散逸者")
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True, help="论文账号级特征表 CSV 或 XLSX")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2244313043)
    parser.add_argument("--expected-accounts", type=int, default=206)
    parser.add_argument(
        "--role-map",
        help="检查聚类中心后手工指定角色，例如 0=触发者,1=偏引者,2=散逸者",
    )
    parser.add_argument(
        "--write-account-results",
        action="store_true",
        help="导出账号聚类归属；默认关闭，避免复制账号级研究数据",
    )
    args = parser.parse_args()

    if not args.features.exists():
        raise FileNotFoundError(f"找不到账号特征表：{args.features}")
    data, features, groups = read_features(args.features)
    if args.expected_accounts and len(data) != args.expected_accounts:
        raise ValueError(f"论文聚类应有 {args.expected_accounts} 个账号，当前为 {len(data)} 个")
    if not 2 <= args.k <= min(6, len(data) - 1):
        raise ValueError("k 必须位于2至min(6, 样本数-1)")

    matrix = data[features].to_numpy(float)
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0, ddof=0)
    z = (matrix - mean) / np.where(std == 0, 1, std)
    diagnostics, models = [], {}
    for k in range(2, min(6, len(data) - 1) + 1):
        inertia, labels, centers = kmeans_pp(z, k, args.seed)
        diagnostics.append({"k": k, "inertia": inertia, "silhouette": silhouette(z, labels)})
        models[k] = (labels, centers)

    labels, centers = models[args.k]
    mapping = parse_role_map(args.role_map, args.k)
    roles = pd.Series(labels).map(mapping) if mapping else pd.Series([pd.NA] * len(labels))
    ari = adjusted_rand(data["identity_type"].astype(str), labels)
    profiles = pd.DataFrame(centers, columns=features)
    profiles.insert(0, "cluster", range(args.k))
    if mapping:
        profiles.insert(1, "role", profiles["cluster"].map(mapping))

    matches = []
    if mapping:
        for role, expected_identity in ROLE_IDENTITY.items():
            mask = roles.eq(role)
            matches.append(
                {
                    "role": role,
                    "expected_identity": expected_identity,
                    "cluster_size": int(mask.sum()),
                    "matching_accounts": int(
                        data.loc[mask.to_numpy(), "identity_type"].astype(str).eq(expected_identity).sum()
                    ),
                    "match_rate": float(
                        data.loc[mask.to_numpy(), "identity_type"].astype(str).eq(expected_identity).mean()
                    ),
                }
            )

    output = args.output_dir or project_root() / "analysis" / "outputs" / "clustering"
    output.mkdir(parents=True, exist_ok=True)
    diagnostics_frame = pd.DataFrame(diagnostics)
    diagnostics_frame.to_csv(output / "k_diagnostics.csv", index=False)
    profiles.to_csv(output / "cluster_profiles_zscore.csv", index=False)
    match_frame = pd.DataFrame(
        matches,
        columns=["role", "expected_identity", "cluster_size", "matching_accounts", "match_rate"],
    )
    match_frame.to_csv(output / "role_identity_match_summary.csv", index=False)
    metadata = {
        "input": str(args.features),
        "accounts": int(len(data)),
        "feature_groups": groups,
        "selected_k": args.k,
        "best_silhouette_k": int(
            diagnostics_frame.loc[diagnostics_frame["silhouette"].idxmax(), "k"]
        ),
        "adjusted_rand_index_vs_identity": ari,
        "role_mapping": mapping or None,
        "role_mapping_rule": (
            "角色名称不由身份标签反推。先检查标准化聚类中心，再通过 --role-map "
            "按行为特征手工指定；未指定时只报告无标签簇和ARI。"
        ),
        "account_level_results_written": bool(args.write_account_results),
        "note": "聚类用于识别行为功能，不用于推断组织身份。",
    }
    (output / "cluster_run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.write_account_results:
        private = data[["account_id", "identity_type"]].copy()
        private["cluster"] = labels
        private["role"] = roles
        private.to_csv(output / "account_role_assignments_private.csv", index=False, encoding="utf-8-sig")
    print(diagnostics_frame.to_string(index=False))
    print(match_frame.to_string(index=False))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
