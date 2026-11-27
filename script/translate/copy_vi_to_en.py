#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script copy content/knowledge/vi sang content/knowledge/en cho một hoặc nhiều module.
Quy tắc:
- Không ghi đè file en đã có nội dung.
- Với file .md ở en đã tồn tại nhưng rỗng (0 byte hoặc chỉ có khoảng trắng),
  copy từ vi nếu Markdown nguồn có nội dung.
- Các file không phải .md đã tồn tại (ví dụ YAML) luôn được giữ nguyên.
- Copy các file chưa tồn tại như trước.
- Nếu location là một module cụ thể: copy cho module đó.
- Nếu location là một thư mục cha chứa nhiều module (vd: .../language/java/core):
  tự động phát hiện và copy cho tất cả các module con bên trong.
- Hỗ trợ tham số --dry-run để xem trước danh sách file sẽ copy mà không thực hiện ghi.
"""

import sys
import os
import shutil
import argparse
from pathlib import Path


def get_project_root() -> Path:
    """Xác định thư mục gốc của project java-learning."""
    current_file = Path(__file__).resolve()
    if len(current_file.parents) >= 3:
        return current_file.parents[2]
    return Path.cwd()


def resolve_base_path(location_input: str, project_root: Path) -> Path:
    """Xác định base_path từ location_input."""
    clean_input = location_input.strip().strip('"').strip("'")
    input_path = Path(clean_input)

    if input_path.is_absolute():
        base_path = input_path
    else:
        if (project_root / input_path).exists():
            base_path = project_root / input_path
        elif (Path.cwd() / input_path).exists():
            base_path = Path.cwd() / input_path
        else:
            base_path = project_root / input_path

    return base_path.resolve()


def find_target_modules(base_path: Path):
    """
    Trả về danh sách tuple (module_path, src_vi_dir, dst_en_dir).
    - Nếu base_path chính là 1 module (hoặc trỏ tới vi/knowledge): trả về 1 mục.
    - Nếu base_path là thư mục cha chứa nhiều module con có content/knowledge/vi:
      tìm tất cả các module con trực tiếp hoặc cấp sâu hơn.
    """
    targets = []

    # Trường hợp 1: base_path chính là module có content/knowledge/vi
    if (base_path / "content" / "knowledge" / "vi").exists():
        return [(base_path, base_path / "content" / "knowledge" / "vi", base_path / "content" / "knowledge" / "en")]

    # Trường hợp 2: base_path chính là thư mục vi
    if base_path.name == "vi" and base_path.parent.name == "knowledge":
        mod_root = base_path.parents[2] if len(base_path.parents) >= 3 else base_path.parent
        return [(mod_root, base_path, base_path.parent / "en")]

    # Trường hợp 3: base_path chính là content/knowledge
    if base_path.name == "knowledge" and (base_path / "vi").exists():
        mod_root = base_path.parents[1] if len(base_path.parents) >= 2 else base_path
        return [(mod_root, base_path / "vi", base_path / "en")]

    # Trường hợp 4: base_path là thư mục cha (như language/java/core), quét tìm tất cả module con
    if base_path.exists() and base_path.is_dir():
        # Quét các thư mục con có chứa content/knowledge/vi
        for path in sorted(base_path.glob("**/content/knowledge/vi")):
            if path.is_dir():
                mod_path = path.parents[2]
                targets.append((mod_path, path, path.parent / "en"))

    return targets


def has_markdown_content(path: Path) -> bool:
    """Kiểm tra Markdown có ký tự không phải khoảng trắng, không tải cả file vào RAM."""
    if path.stat().st_size == 0:
        return False
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        while chunk := stream.read(64 * 1024):
            if chunk.strip():
                return True
    return False


def copy_module_vi_to_en(mod_path: Path, src_dir: Path, dst_dir: Path, project_root: Path, dry_run: bool = False):
    """Copy file mới và bổ sung Markdown đích rỗng, không đụng file đích đã có nội dung."""
    try:
        rel_mod = mod_path.relative_to(project_root)
    except ValueError:
        rel_mod = mod_path

    print(f"\n📦 Module: {rel_mod}")
    print(f"   - Nguồn (vi): {src_dir}")
    print(f"   - Đích  (en): {dst_dir}")

    total_scanned = 0
    copied_count = 0
    filled_blank_count = 0
    skipped_count = 0

    for root, dirs, files in os.walk(src_dir):
        rel_root = Path(root).relative_to(src_dir)

        for file_name in files:
            total_scanned += 1
            src_file = Path(root) / file_name
            rel_file_path = rel_root / file_name if str(rel_root) != "." else Path(file_name)
            dst_file = dst_dir / rel_file_path

            if not dst_file.exists() and not dst_file.is_symlink():
                copied_count += 1
                if not dry_run:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
            elif (
                dst_file.is_file()
                and not dst_file.is_symlink()
                and dst_file.suffix.lower() == ".md"
                and not has_markdown_content(dst_file)
                and has_markdown_content(src_file)
            ):
                filled_blank_count += 1
                if not dry_run:
                    shutil.copy2(src_file, dst_file)
            else:
                skipped_count += 1

    action_label = "Sẽ copy" if dry_run else "Đã copy"
    fill_label = "Sẽ điền file MD rỗng" if dry_run else "Đã điền file MD rỗng"
    print(
        f"   👉 Tổng file vi: {total_scanned} | {action_label} mới: {copied_count}"
        f" | {fill_label}: {filled_blank_count} | Bỏ qua: {skipped_count}"
    )

    return {
        "module": str(rel_mod),
        "total": total_scanned,
        "copied": copied_count,
        "filled_blank": filled_blank_count,
        "skipped": skipped_count
    }


def main():
    parser = argparse.ArgumentParser(
        description="Copy file mới vi → en; chỉ ghi đè file MD đích trống nếu nguồn có nội dung."
    )
    parser.add_argument(
        "location",
        help="Đường dẫn module hoặc thư mục chứa nhiều module tính từ java-learning"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Xem trước các file sẽ được copy mà không thực hiện ghi."
    )

    args = parser.parse_args()
    project_root = get_project_root()

    print(f"🏠 Project root: {project_root}")
    base_path = resolve_base_path(args.location, project_root)

    if not base_path.exists():
        print(f"❌ Lỗi: Đường dẫn không tồn tại: {base_path}")
        sys.exit(1)

    targets = find_target_modules(base_path)

    if not targets:
        print(f"⚠️ Không tìm thấy module nào có content/knowledge/vi trong: {base_path}")
        sys.exit(1)

    print(f"🎯 Tìm thấy {len(targets)} module(s) cần xử lý.")
    if args.dry_run:
        print("🔍 [DRY-RUN MODE] Chỉ kiểm tra số lượng và danh sách, không thực hiện ghi đĩa.\n")

    summary_results = []
    for mod_path, src_dir, dst_dir in targets:
        res = copy_module_vi_to_en(mod_path, src_dir, dst_dir, project_root, dry_run=args.dry_run)
        summary_results.append(res)

    total_scanned_all = sum(r["total"] for r in summary_results)
    total_copied_all = sum(r["copied"] for r in summary_results)
    total_filled_blank_all = sum(r["filled_blank"] for r in summary_results)
    total_skipped_all = sum(r["skipped"] for r in summary_results)

    action_verb = "DỰ KIẾN COPY" if args.dry_run else "ĐÃ COPY THÀNH CÔNG"
    print("\n" + "=" * 60)
    print(f"🎉 TỔNG KẾT HOÀN TẤT ({len(summary_results)} modules):")
    print(f"  - Tổng số file vi quét được:   {total_scanned_all}")
    print(f"  - File mới {action_verb.lower()}:        {total_copied_all}")
    print(f"  - File MD rỗng được điền:     {total_filled_blank_all}")
    print(f"  - File bỏ qua:                {total_skipped_all}")
    print("=" * 60)


if __name__ == "__main__":
    main()
