#!/usr/bin/env python3
"""清洗并核验 2021—2025 年知情代理人发帖工作簿。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


PAPER_COUNTS = {
    "社会活动型": {2021: 1388, 2022: 799, 2023: 301, 2024: 365, 2025: 183},
    "学者型": {2021: 384, 2022: 215, 2023: 117, 2024: 186, 2025: 145},
    "普通用户型": {2021: 495, 2022: 297, 2023: 70, 2024: 6, 2025: 1},
}
VALID_YEARS = set(range(2021, 2026))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0)


def load_posts(book: Path) -> pd.DataFrame:
    required_sheets = {"账号匹配", "21-23清洗数据", "24-25数据"}
    available = set(pd.ExcelFile(book).sheet_names)
    missing_sheets = required_sheets - available
    if missing_sheets:
        raise ValueError(f"工作簿缺少工作表：{sorted(missing_sheets)}")

    parts = []
    for sheet, period in (("21-23清洗数据", "2021-2023"), ("24-25数据", "2024-2025")):
        frame = pd.read_excel(book, sheet_name=sheet)
        frame.columns = [str(column).strip() for column in frame.columns]
        required = {"类型", "账号名称", "账号ID", "日期（原始）", "年份", "推文原文"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{sheet} 缺少字段：{sorted(missing)}")
        frame["数据期间"] = period
        frame["来源工作表_分析"] = sheet
        parts.append(frame)

    data = pd.concat(parts, ignore_index=True, sort=False)
    data["类型"] = data["类型"].astype("string").str.strip()
    data["账号名称"] = data["账号名称"].astype("string").str.strip()
    data["账号ID"] = normalize_id(data["账号ID"])
    data["推文原文"] = data["推文原文"].astype("string").str.strip()
    data["年份"] = pd.to_numeric(data["年份"], errors="coerce").astype("Int64")
    data["日期_解析"] = pd.to_datetime(data["日期（原始）"], errors="coerce", format="mixed")
    for column in ("回复数", "转发数", "点赞数", "浏览量", "有效评论数"):
        if column in data:
            data[column] = numeric(data[column])

    data["关键字段完整"] = (
        data[["类型", "账号ID", "年份", "推文原文"]].notna().all(axis=1)
        & data["账号ID"].ne("")
        & data["推文原文"].ne("")
    )
    data["年份有效"] = data["年份"].isin(VALID_YEARS)
    data["日期可解析"] = data["日期_解析"].notna()
    data["日期年份一致"] = data["日期_解析"].dt.year.astype("Int64").eq(data["年份"])
    duplicate_key = ["账号ID", "日期（原始）", "推文原文"]
    data["疑似重复"] = data.duplicated(duplicate_key, keep=False)
    data["进入分析"] = data["关键字段完整"] & data["年份有效"]
    return data


def account_check(book: Path) -> dict:
    accounts = pd.read_excel(book, sheet_name="账号匹配")
    accounts.columns = [str(column).strip() for column in accounts.columns]
    if "类型" not in accounts:
        raise ValueError("账号匹配表缺少“类型”字段")
    counts = accounts["类型"].astype("string").str.strip().value_counts()
    return {
        "账号总数": int(len(accounts)),
        "完全重复行": int(accounts.duplicated().sum()),
        "身份分布": {str(key): int(value) for key, value in counts.items()},
    }


def raw_clean_comparison(root: Path) -> dict:
    folder = root / "data" / "数据清洗过程"
    result = {}
    for label, name in (("清洗前", "24-25年涉疆发文.csv"), ("清洗后", "24-25年涉疆发文_clean.csv")):
        path = folder / name
        if not path.exists():
            result[label] = {"存在": False}
            continue
        frame = pd.read_csv(path)
        result[label] = {
            "存在": True,
            "文件": str(path.relative_to(root)),
            "行数": int(len(frame)),
            "列数": int(len(frame.columns)),
            "完全重复行": int(frame.duplicated().sum()),
            "空单元格": int(frame.isna().sum().sum()),
        }
    if all(result.get(label, {}).get("存在") for label in ("清洗前", "清洗后")):
        before = result["清洗前"]["行数"]
        after = result["清洗后"]["行数"]
        result["变化"] = {
            "删除行数": before - after,
            "保留率": round(after / before, 6) if before else None,
        }
    return result


def count_check(valid: pd.DataFrame) -> pd.DataFrame:
    actual = valid.groupby(["类型", "年份"]).size()
    rows = []
    for identity, years in PAPER_COUNTS.items():
        for year, expected in years.items():
            observed = int(actual.get((identity, year), 0))
            rows.append(
                {
                    "类型": identity,
                    "年份": year,
                    "论文表4": expected,
                    "工作簿": observed,
                    "差值_工作簿减论文": observed - expected,
                    "是否一致": observed == expected,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=project_root())
    parser.add_argument("--input", type=Path, help="默认读取 data/数据清洗过程 下的合并工作簿")
    parser.add_argument("--output-dir", type=Path, help="默认写入 analysis/outputs/cleaning")
    parser.add_argument(
        "--write-row-level",
        action="store_true",
        help="额外导出逐条规范化数据；默认关闭，避免在分析目录复制研究原始记录",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    book = args.input or root / "data" / "数据清洗过程" / "知情代理人21-25年发帖清洗及转发均值.xlsx"
    output = args.output_dir or root / "analysis" / "outputs" / "cleaning"
    if not book.exists():
        raise FileNotFoundError(f"找不到输入文件：{book}")
    output.mkdir(parents=True, exist_ok=True)

    data = load_posts(book)
    valid = data[data["进入分析"]].copy()
    summary = (
        valid.groupby(["类型", "年份"], dropna=False)
        .agg(
            发帖数=("推文原文", "size"),
            活跃账号数=("账号ID", "nunique"),
            平均转发数=("转发数", "mean"),
            平均点赞数=("点赞数", "mean"),
            平均回复数=("回复数", "mean"),
        )
        .reset_index()
    )
    check = count_check(valid)
    report = {
        "输入文件": str(book),
        "账号匹配": account_check(book),
        "输入帖文行数": int(len(data)),
        "进入分析行数": int(len(valid)),
        "实际有发帖账号数": int(valid["账号ID"].nunique()),
        "关键字段不完整行": int((~data["关键字段完整"]).sum()),
        "研究期外或年份无效行": int((~data["年份有效"]).sum()),
        "日期无法解析行": int((~data["日期可解析"]).sum()),
        "日期与年份不一致行": int((data["日期可解析"] & ~data["日期年份一致"]).sum()),
        "疑似重复行_仅标记未自动删除": int(data["疑似重复"].sum()),
        "论文表4一致单元格": int(check["是否一致"].sum()),
        "论文表4总单元格": int(len(check)),
        "清洗前后比较": raw_clean_comparison(root),
        "逐条数据是否导出": bool(args.write_row_level),
        "方法说明": (
            "脚本执行字段统一、账号ID规范化、日期和年份校验、关键字段过滤、"
            "非负互动量处理、疑似重复标记及论文口径核对。疑似重复必须结合帖文ID或链接人工复核，"
            "程序不会仅凭相同正文自动删除。"
        ),
    }
    summary.to_csv(output / "summary_by_year_identity.csv", index=False, encoding="utf-8-sig")
    check.to_csv(output / "paper_table4_count_check.csv", index=False, encoding="utf-8-sig")
    (output / "data_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.write_row_level:
        valid.to_csv(output / "posts_normalized_private.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
