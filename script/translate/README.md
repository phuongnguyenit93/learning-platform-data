# Translate Helper Scripts

Thư mục chứa các script hỗ trợ dịch thuật và quản lý tài liệu đa ngôn ngữ cho dự án `java-learning`.

---

## 1. `copy_vi_to_en.py`

Script sao chép cấu trúc và các tệp tài liệu từ `content/knowledge/vi` sang `content/knowledge/en` của module được chỉ định.

### Tính năng
- **Giữ file đã có nội dung**: File `.md` đích đã có nội dung được giữ nguyên.
- **Bổ sung Markdown trống**: File `.md` ở `en` có 0 byte hoặc chỉ chứa khoảng trắng sẽ nhận nội dung từ `vi` nếu nguồn có nội dung; không copy nguồn trống đè lên file đích trống.
- **Giữ nguyên metadata hiện hữu**: File không phải Markdown (ví dụ `.yml`) đã tồn tại không bị ghi đè. Các file chưa tồn tại vẫn được copy.
- **Giữ nguyên cấu trúc thư mục**: Tự động tạo thư mục con tương ứng bên `en`.
- **Hỗ trợ `--dry-run`**: Xem trước danh sách các file sẽ được copy mà không làm thay đổi ổ đĩa.
- **Tự động nhận diện đường dẫn**: Chấp nhận đường dẫn module tương đối từ gốc project `java-learning` hoặc đường dẫn trực tiếp.

### Cách sử dụng

Từ thư mục gốc của project `java-learning`:

```bash
# 1. Chạy thử nghiệm để kiểm tra danh sách file (khuyên dùng trước khi copy thật)
python script/translate/copy_vi_to_en.py module/infrastructure/cloud/architecture --dry-run

# 2. Chạy copy thực tế
python script/translate/copy_vi_to_en.py module/infrastructure/cloud/architecture
```

### Ví dụ tham số `location` hợp lệ:
- `module/infrastructure/cloud/architecture`
- `module/infrastructure/cloud/architecture/content/knowledge`
- `module/infrastructure/cloud/architecture/content/knowledge/vi`
