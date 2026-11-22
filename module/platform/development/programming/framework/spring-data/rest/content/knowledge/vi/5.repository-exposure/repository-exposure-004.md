# Ẩn toàn bộ repository bằng `exported = false`

## Mục tiêu

Spring Data REST có thể tự động tạo REST resource cho các Spring Data repository được phát hiện trong ứng dụng. Khi một repository chỉ phục vụ xử lý nội bộ, hãy đặt `exported = false` trên chính interface repository để Spring Data REST không công bố các endpoint của repository đó.

Annotation cần dùng là `@RepositoryRestResource` trong package `org.springframework.data.rest.core.annotation`.

## Cấu hình

Ví dụ với Spring Data JPA:

    import org.springframework.data.jpa.repository.JpaRepository;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;

    @RepositoryRestResource(exported = false)
    public interface AuditRecordRepository
            extends JpaRepository<AuditRecord, Long> {
    }

Đặt annotation trên interface repository mà Spring Data REST phát hiện. Nếu ứng dụng dùng MongoDB, JDBC, Redis hoặc một module Spring Data khác, cách làm tương tự: giữ kiểu repository tương ứng và thêm `@RepositoryRestResource(exported = false)`.

`exported` mặc định là `true` khi repository được Spring Data REST công bố. Đặt thành `false` sẽ tắt việc export repository đó. Nếu cần ẩn nhiều repository, thêm annotation này vào từng interface cần ẩn.

## Những gì thay đổi

Khi repository được đánh dấu `exported = false`, Spring Data REST không tạo các tài nguyên REST dựa trên repository đó. Cụ thể:

- Không có collection endpoint của repository.
- Không có item endpoint theo ID thông qua repository đó.
- Các query method của repository không được công bố thành REST search resource.
- Repository không xuất hiện dưới dạng link trong API root của Spring Data REST.

Ví dụ, nếu repository vốn được truy cập qua `/api/audit-records`, sau khi tắt export thì request đến đường dẫn đó sẽ không còn được Spring Data REST phục vụ. API root `/api/` cũng không còn link đến repository này. Đường dẫn thực tế phụ thuộc `spring.data.rest.base-path` và cấu hình `path` của repository.

Việc tắt export chỉ ảnh hưởng đến REST endpoint do Spring Data REST tạo ra. Repository vẫn là Spring bean và ứng dụng vẫn có thể inject nó vào service hoặc component để đọc, ghi dữ liệu:

    @Service
    public class AuditRecordService {
        private final AuditRecordRepository repository;

        public AuditRecordService(AuditRecordRepository repository) {
            this.repository = repository;
        }

        public List<AuditRecord> findAll() {
            return repository.findAll();
        }
    }

Dữ liệu trong database không bị xóa và các thao tác repository trong code Java vẫn hoạt động bình thường.

## Phân biệt ẩn repository và ẩn một method

- Ẩn toàn bộ repository: dùng `@RepositoryRestResource(exported = false)` trên interface. Đây là cách dùng cho mục này.
- Chỉ ẩn một query method trong repository vẫn được export: dùng `@RestResource(exported = false)` trên method đó.

Ví dụ chỉ ẩn method tìm người dùng theo email:

    import org.springframework.data.rest.core.annotation.RestResource;

    @RestResource(exported = false)
    Optional<User> findByEmail(String email);

Không dùng cách ẩn từng method nếu yêu cầu là ngừng công bố toàn bộ repository; hãy đặt `exported = false` ở cấp interface.

## Kiểm tra kết quả

Sau khi khởi động lại ứng dụng, kiểm tra API root và endpoint của repository. Ví dụ nếu base path là `/api` và repository có path `audit-records`:

    GET /api/
    GET /api/audit-records

API root không nên còn link đến repository đã ẩn. Request đến collection endpoint của repository cần trả về trạng thái không tìm thấy tài nguyên (thường là `404 Not Found`). Hãy dùng path và link relation thực tế của ứng dụng khi viết integration test.

## Lưu ý về bảo mật

`exported = false` kiểm soát việc Spring Data REST tự động công bố repository; đây không phải cơ chế phân quyền. Nếu một `@RestController`, GraphQL endpoint hoặc API tùy chỉnh khác vẫn gọi repository và trả dữ liệu ra ngoài, endpoint đó vẫn có thể truy cập được. Hãy cấu hình Spring Security và kiểm tra quyền truy cập ở các endpoint hoặc service tương ứng khi cần bảo vệ dữ liệu.

## Khi cấu hình chưa có hiệu lực

1. Kiểm tra import đúng là `org.springframework.data.rest.core.annotation.RepositoryRestResource`.
2. Đảm bảo annotation nằm trên interface repository thực tế được Spring Data REST phát hiện, không chỉ nằm trên một interface cha không được đăng ký như repository.
3. Kiểm tra `spring.data.rest.base-path` và `path` để gọi đúng URL khi xác minh.
4. Kiểm tra xem có controller hoặc endpoint tùy chỉnh nào khác đang công bố cùng dữ liệu hay không; `exported = false` chỉ tắt các endpoint do Spring Data REST tạo từ repository.