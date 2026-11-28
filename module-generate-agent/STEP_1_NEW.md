# STEP 1 NEW — Kích hoạt module (độc lập, file-first)

Không dùng `java-learning`, Gradle, Google Sheets hoặc Oracle. Mọi lệnh chạy từ
**root của repository `learning-platform-data`**, ở bất cứ đường dẫn clone nào.

## 1. Prime xác định và kích hoạt đúng module

1. Đọc `GENERAL_AGENT_RULES.md` và toàn bộ `rules/`. Nhận đúng một đường dẫn
   `module/<category>/<...>/<module>` bên trong data repository.
2. Xác minh module là thư mục thực, không đi qua symlink, không tự tạo module
   nếu chưa được yêu cầu, không can thiệp module khác.
3. Khi người dùng yêu cầu kích hoạt module, tạo `module_activate.json` ngay
   trong module (nếu thiếu), với JSON chuẩn:

   ```json
   {"isModule": true}
   ```

   Nếu file đã có, không ghi đè metadata khác; chỉ chỉnh `isModule` sau khi
   xác minh phạm vi và quyền thực hiện. Nếu `isModule` là false, script sẽ
   từ chối xử lý, không được tự bỏ qua trạng thái này.

## 2. Khởi tạo module-info.json từ template nội bộ

Template chuẩn nằm ở **`learning-platform-data/module-info-base.json`**.
Script `script/module-generate/step1/activate_module.py` chỉ bổ sung key/field
**còn thiếu** trong `module-info.json`, không ghi đè VALUE/TYPE/DESCRIPTION
hiện hữu, không tự sửa `SERVICE_NAME` hoặc `CURRENT_STEP`. Không cần parent
repository, không đọc `java-learning/module-info-base.json`.

```powershell
python script/module-generate/step1/activate_module.py --module "module/<path>" --dry-run
python script/module-generate/step1/activate_module.py --module "module/<path>" --apply
```

Script mặc định dry-run. `--all` chỉ dùng khi người dùng yêu cầu thao tác hàng
loạt; không thay `--module` bằng `--all` để tránh sửa module ngoài phạm vi.
Nếu một module có JSON sai schema, symlink hoặc lỗi filesystem, dừng và xử lý
blocker, không xóa/reset file.

## 3. Prime bổ sung metadata còn trống

Prime/AI nghiên cứu chủ đề thực tế để điền hai trường trong
`module-info.json` **chỉ khi VALUE còn trống**:

- `SERVICE_NAME.VALUE`: định danh chính xác UPPER_SNAKE_CASE; kiểm tra không
  trùng trên toàn module catalog.
- `SERVICE_NAME_DESCRIBE.VALUE`: mô tả ngắn, đúng phạm vi kiến thức.

Giữ nguyên `SPECIAL_NOTE`, `MODULE_LANGUAGE` và `CURRENT_STEP`; không suy
diễn đường dẫn hay thay thế metadata đã do người khác viết. Nếu thiếu thông tin
để điền chính xác, báo BLOCKER. Kiểm tra lại JSON, trạng thái active, định danh,
và file mới sau mọi thay đổi.

## 4. Checkpoint

Sau khi Prime QA và readback thành công, chỉ nâng
`module-info.json.CURRENT_STEP.VALUE` từ `"0"` lên `"1"` nếu cần.
Không ghi lùi trạng thái đã có; không ghi `master.json` hay Google Sheets.
Không tự commit/push hay chuyển STEP tiếp theo.

**Điều kiện hoàn thành:** module kích hoạt, module-info.json có đủ field từ
template, SERVICE_NAME và SERVICE_NAME_DESCRIBE hợp lệ, CURRENT_STEP đã được
readback, không có thay đổi ngoài module được giao.
