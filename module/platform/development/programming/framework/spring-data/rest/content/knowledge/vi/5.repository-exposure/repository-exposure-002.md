# RepositoryDetectionStrategy: DEFAULT, ALL, VISIBILITY và ANNOTATED

## 1. Mục tiêu

Spring Data REST có thể tự động công bố các Spring Data repository thành tài nguyên HTTP. Ví dụ, một repository quản lý Customer có thể tạo collection resource tại `/customers`, item resource tại `/customers/{id}`, cùng các endpoint tìm kiếm nếu repository khai báo query method phù hợp.

Không phải repository nào trong ứng dụng cũng nên trở thành API công khai. **RepositoryDetectionStrategy** quyết định repository nào được Spring Data REST phát hiện và công bố. Chiến lược này được đặt trong `RepositoryRestConfiguration`.

Có bốn lựa chọn thường dùng:

- **DEFAULT**: công bố repository public theo mặc định; repository không public có thể được chọn rõ ràng bằng annotation.
- **ALL**: công bố mọi repository được Spring Data nhận diện, không phụ thuộc visibility hay annotation.
- **VISIBILITY**: chỉ công bố repository interface có modifier `public`.
- **ANNOTATED**: chỉ công bố repository được đánh dấu rõ ràng bằng annotation phù hợp.

Mặc định của Spring Data REST là **DEFAULT**.

## 2. Phân biệt bốn chiến lược

### DEFAULT

Đây là lựa chọn mặc định và phù hợp với cách dùng thông thường của Spring Data REST.

- Repository interface có modifier `public` được công bố.
- Repository interface không public bị ẩn, trừ khi được đánh dấu rõ ràng bằng `@RepositoryRestResource` với `exported = true` (giá trị mặc định của thuộc tính này).
- Nếu repository được đánh dấu `@RepositoryRestResource(exported = false)`, repository đó không được công bố, kể cả khi interface là public.

Ví dụ:

    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

Với DEFAULT, `CustomerRepository` được công bố vì interface là public.

Một repository nội bộ có thể không public:

    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

Với DEFAULT, repository này không được công bố. Nếu thật sự muốn công bố, có thể đánh dấu rõ ràng:

    @RepositoryRestResource(path = "internal-audits")
    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

### ALL

ALL chọn mọi repository mà Spring Data nhận diện, không xét modifier Java hoặc cấu hình annotation.

Điều đó có nghĩa là repository package-private cũng có thể được công bố. Annotation `exported = false` không phải bộ lọc trong chiến lược này; nếu chọn ALL, repository có annotation đó vẫn được xét là được công bố.

Ví dụ, cả hai interface sau đều được chọn:

    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

ALL có thể hữu ích khi thử nghiệm hoặc khi thực sự muốn công bố toàn bộ repository. Trong ứng dụng có nhiều repository phục vụ nội bộ, chiến lược này dễ làm lộ thêm endpoint ngoài dự kiến.

### VISIBILITY

VISIBILITY chỉ xét visibility của repository interface:

- Interface public được công bố.
- Interface package-private hoặc có visibility thấp hơn không được công bố.
- Annotation không thay đổi quyết định của chiến lược này. Vì vậy, một repository package-private vẫn bị ẩn dù có `@RepositoryRestResource`; ngược lại, repository public vẫn được chọn dù annotation đặt `exported = false`.

Ví dụ:

    @RepositoryRestResource(path = "internal-audits")
    interface InternalAuditRepository extends JpaRepository<AuditLog, Long> {
    }

Repository trên vẫn không được công bố với VISIBILITY vì interface không public.

VISIBILITY phù hợp khi quy tắc của ứng dụng chỉ dựa trên visibility của Java. Nếu cần chủ động chọn từng repository, hãy cân nhắc ANNOTATED.

### ANNOTATED

ANNOTATED dùng cách tiếp cận opt-in: repository phải được đánh dấu rõ ràng mới được công bố.

- Repository public nhưng không có annotation phù hợp sẽ không được công bố.
- Repository được đánh dấu `@RepositoryRestResource` và không đặt `exported = false` sẽ được công bố.
- Repository có `@RepositoryRestResource(exported = false)` bị loại khỏi danh sách công bố.
- Repository được đánh dấu có thể được công bố dù interface không public.

Ví dụ:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

Repository trên được công bố tại collection path `/customers`.

Repository sau không được công bố:

    @RepositoryRestResource(exported = false)
    public interface SecretRepository extends JpaRepository<Secret, Long> {
    }

Javadoc của enum cũng đề cập `@RestResource` trong tiêu chí annotation. Với repository-level configuration, `@RepositoryRestResource` là cách đánh dấu trực tiếp, dễ đọc và thường dùng nhất.

## 3. Bảng so sánh

Bảng dưới giả định các repository đều đã được Spring Data nhận diện và nằm trong phạm vi package scanning.

| Repository interface | DEFAULT | ALL | VISIBILITY | ANNOTATED |
|---|---:|---:|---:|---:|
| public, không có annotation | Có | Có | Có | Không |
| package-private, không có annotation | Không | Có | Không | Không |
| public, có `@RepositoryRestResource` | Có | Có | Có | Có |
| package-private, có `@RepositoryRestResource` | Có | Có | Không | Có |
| public, `exported = false` | Không | Có | Có | Không |
| package-private, `exported = false` | Không | Có | Không | Không |

Hai điểm dễ nhầm:

1. **DEFAULT và ANNOTATED** tôn trọng thuộc tính `exported` của annotation. DEFAULT còn tự động chọn repository public; ANNOTATED yêu cầu đánh dấu rõ ràng.
2. **ALL và VISIBILITY** bỏ qua cấu hình annotation khi quyết định chọn repository. Do đó, không nên dùng `exported = false` làm biện pháp ẩn repository nếu đang chọn ALL hoặc VISIBILITY.

## 4. Cấu hình chiến lược

Có thể cấu hình thông qua một bean triển khai `RepositoryRestConfigurer`. Ví dụ dưới đây chuyển toàn bộ ứng dụng sang ANNOTATED để chỉ công bố repository được đánh dấu rõ ràng.

    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
    import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy.RepositoryDetectionStrategies;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
    import org.springframework.web.servlet.config.annotation.CorsRegistry;

    @Configuration
    public class SpringDataRestConfig implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setRepositoryDetectionStrategy(
                    RepositoryDetectionStrategies.ANNOTATED
            );
        }
    }

Đổi giá trị enum để chọn chiến lược khác:

    RepositoryDetectionStrategies.DEFAULT
    RepositoryDetectionStrategies.ALL
    RepositoryDetectionStrategies.VISIBILITY
    RepositoryDetectionStrategies.ANNOTATED

Một cách viết ngắn hơn, ở các phiên bản hỗ trợ `RepositoryRestConfigurer.withConfig`, là:

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
            config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategies.ANNOTATED
            )
        );
    }

**Lưu ý phiên bản:** chữ ký của `configureRepositoryRestConfiguration` thay đổi giữa các thế hệ Spring Data REST. Ví dụ trên dùng chữ ký hiện hành có tham số `CorsRegistry`. Nếu project dùng phiên bản cũ, hãy đối chiếu Javadoc đúng với dependency đang cài và dùng chữ ký mà phiên bản đó cung cấp.

## 5. Ví dụ chọn repository theo nhu cầu

Giả sử ứng dụng có ba repository:

    public interface ProductRepository extends JpaRepository<Product, Long> {
    }

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository extends JpaRepository<Customer, Long> {
    }

    @RepositoryRestResource(exported = false)
    public interface CredentialRepository extends JpaRepository<Credential, Long> {
    }

Kết quả mong đợi:

- Với DEFAULT: ProductRepository và CustomerRepository được công bố; CredentialRepository bị ẩn.
- Với ALL: cả ba repository được công bố, kể cả CredentialRepository.
- Với VISIBILITY: cả ba đều là public nên cả ba được công bố; annotation không loại CredentialRepository.
- Với ANNOTATED: chỉ CustomerRepository được công bố; ProductRepository không có annotation và CredentialRepository bị đánh dấu exported=false.

Nếu thêm một repository package-private có `@RepositoryRestResource`, repository đó được công bố với DEFAULT và ANNOTATED, được công bố với ALL, nhưng bị ẩn với VISIBILITY.

## 6. Kiểm tra kết quả sau khi cấu hình

Sau khi khởi động lại ứng dụng, kiểm tra root resource của Spring Data REST. HAL root thường liệt kê các quan hệ liên kết tới collection resource đã được công bố.

    curl -i http://localhost:8080/

Nếu ứng dụng có CustomerRepository với path là `customers`, thử:

    curl -i http://localhost:8080/customers

Khi kiểm tra, hãy xác nhận:

1. Repository dự kiến được công bố có link trong root resource và endpoint collection phản hồi.
2. Repository dự kiến bị ẩn không xuất hiện trong danh sách link và endpoint không được phục vụ.
3. Repository package-private có kết quả đúng theo chiến lược đã chọn.
4. Nếu ứng dụng cấu hình base path, hãy thêm base path vào URL kiểm tra.

Kết quả HTTP cụ thể có thể phụ thuộc cấu hình ứng dụng và Spring Security. Việc repository không được Spring Data REST công bố không thay thế cho xác thực và phân quyền. Với endpoint đã công bố, vẫn cần cấu hình bảo mật phù hợp.

## 7. Chọn chiến lược nào?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Muốn giữ hành vi mặc định: public repository được công bố | DEFAULT |
| Muốn chỉ công bố những repository được đánh dấu chủ động | ANNOTATED |
| Muốn chỉ dựa trên public/package-private của Java | VISIBILITY |
| Muốn công bố mọi repository đã được nhận diện | ALL |

Trong API production, ANNOTATED thường là lựa chọn dễ kiểm soát khi muốn opt-in từng repository. DEFAULT phù hợp khi phần lớn public repository đều được phép trở thành REST resource. ALL cần được cân nhắc kỹ vì có thể công bố cả repository phục vụ nội bộ.

Nếu quy tắc công bố phức tạp hơn bốn lựa chọn trên, có thể tự triển khai `RepositoryDetectionStrategy` và định nghĩa logic trong phương thức `isExported(RepositoryMetadata metadata)`.

## 8. Bài tập thực hành

Một ứng dụng có các repository sau:

- `OrderRepository`: public, không có annotation.
- `PaymentRepository`: public, có `@RepositoryRestResource`.
- `InternalLogRepository`: package-private, có `@RepositoryRestResource`.
- `AdminRepository`: public, có `@RepositoryRestResource(exported = false)`.

Hãy xác định repository nào được công bố khi lần lượt chọn DEFAULT, ALL, VISIBILITY và ANNOTATED. Sau đó cấu hình ANNOTATED, khởi động ứng dụng và kiểm tra root resource để xác nhận chỉ các repository được chọn xuất hiện.

**Đáp án để tự đối chiếu:**

| Repository | DEFAULT | ALL | VISIBILITY | ANNOTATED |
|---|---:|---:|---:|---:|
| OrderRepository | Có | Có | Có | Không |
| PaymentRepository | Có | Có | Có | Có |
| InternalLogRepository | Có | Có | Không | Có |
| AdminRepository | Không | Có | Có | Không |

## 9. Ghi nhớ

- RepositoryDetectionStrategy quyết định repository nào được Spring Data REST công bố thành HTTP resource.
- DEFAULT là mặc định: public repository được chọn; annotation có thể chọn repository không public hoặc loại repository bằng `exported = false`.
- ALL chọn tất cả repository đã được nhận diện.
- VISIBILITY chỉ chọn interface public và bỏ qua annotation.
- ANNOTATED yêu cầu repository được đánh dấu rõ ràng và không bị `exported = false`.
- Chiến lược phát hiện repository không phải cơ chế xác thực hoặc phân quyền API.

## Tài liệu tham khảo

- Spring Data REST Reference — Customizing repository exposure: https://www.springframework.org/spring-data/rest/reference/5.1/customizing-sdr.html
- Spring Data REST Javadoc — RepositoryDetectionStrategies: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html
- Spring Data REST Javadoc — RepositoryRestConfigurer: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
