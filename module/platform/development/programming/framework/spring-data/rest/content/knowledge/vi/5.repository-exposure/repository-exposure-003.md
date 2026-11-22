# Ảnh hưởng của phạm vi `public` và annotation đến việc phát hiện repository trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao một Spring Data repository được tạo thành bean nhưng chưa chắc đã xuất hiện thành REST resource; phân biệt ảnh hưởng của phạm vi Java (`public` hoặc package-private) với annotation; và chọn đúng `RepositoryDetectionStrategy` để kiểm soát repository nào được Spring Data REST công bố.

## 1. Phân biệt việc tạo repository và việc công bố REST resource

Có hai bước riêng biệt:

1. **Spring Data nhận diện repository** theo cấu hình của module lưu trữ (JPA, JDBC, MongoDB, ...), sau đó tạo implementation/proxy để ứng dụng sử dụng.
2. **Spring Data REST quyết định repository nào được export** thành HTTP resource, chẳng hạn collection resource và item resource.

Vì vậy, một repository có thể hoạt động bình thường trong service nhưng không xuất hiện trong API Spring Data REST. Nguyên nhân thường nằm ở detection strategy, phạm vi truy cập của interface hoặc annotation dùng để công bố.

Trong bài này, từ “public” nói về **phạm vi truy cập của kiểu Java**. Nó không có nghĩa endpoint được phép truy cập công khai trên Internet và cũng không thay thế xác thực hay phân quyền.

## 2. Phạm vi Java ảnh hưởng thế nào?

Một top-level interface khai báo `public` có thể được truy cập từ package khác:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Nếu bỏ từ khóa `public`, interface top-level có phạm vi package-private:

```java
interface InternalCustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Spring Data REST mặc định xem repository public là ứng viên để công bố. Repository package-private thường bị loại khỏi danh sách mặc định vì nó được thiết kế để sử dụng nội bộ trong package. Tuy nhiên, annotation và detection strategy có thể thay đổi kết quả này.

Điểm cần nhớ: phạm vi package-private không tự biến repository thành một repository “không tồn tại”. Nó ảnh hưởng đến khả năng Spring Data REST chọn repository để tạo REST resource.

## 3. Vai trò của `@RepositoryRestResource`

`@RepositoryRestResource` là annotation đặt trên repository interface để tùy chỉnh cách Spring Data REST công bố repository. Annotation này có thể:

- Chỉ định đường dẫn collection bằng `path`.
- Chỉ định tên quan hệ trong HAL bằng `collectionResourceRel`.
- Quyết định resource có được export hay không bằng `exported` (mặc định là `true`).

Ví dụ:

```java
@RepositoryRestResource(
    path = "customers",
    collectionResourceRel = "customers"
)
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Repository trên được công bố dưới đường dẫn collection `/customers` (bên dưới base path nếu ứng dụng có cấu hình base path). Annotation giúp khai báo rõ ý định công bố và tùy chỉnh tên resource; nó không thay thế việc khai báo repository cho Spring Data module.

Để chủ động ẩn toàn bộ repository khỏi cơ chế export có xét annotation:

```java
@RepositoryRestResource(exported = false)
public interface AuditRepository
        extends CrudRepository<AuditEntry, Long> {
}
```

Khi cần ẩn một query method hoặc CRUD method cụ thể, dùng `@RestResource(exported = false)` trên method đó. Đây là phạm vi điều khiển khác với việc ẩn cả repository.

## 4. Bốn RepositoryDetectionStrategy

Spring Data REST dùng `RepositoryDetectionStrategy` để quyết định repository nào được chuyển thành REST resource. Bốn lựa chọn chuẩn có ý nghĩa như sau:

| Strategy | Quy tắc chọn repository |
| --- | --- |
| `DEFAULT` | Công bố repository public hoặc repository được đánh dấu rõ bằng `@RepositoryRestResource`; cờ `exported` được xét đối với repository được đánh dấu. |
| `ALL` | Công bố tất cả Spring Data repository, không phụ thuộc phạm vi Java hoặc cấu hình annotation. |
| `VISIBILITY` | Chỉ công bố repository có interface public; annotation không quyết định việc chọn repository. |
| `ANNOTATED` | Chỉ công bố repository được đánh dấu bằng `@RepositoryRestResource` (hoặc annotation REST tương ứng) và không bị đặt `exported = false`. |

Có thể so sánh kết quả với giả định mọi annotation đều dùng giá trị mặc định `exported = true`:

| Kiểu repository | DEFAULT | ALL | VISIBILITY | ANNOTATED |
| --- | --- | --- | --- | --- |
| Public, không annotation | Có | Có | Có | Không |
| Package-private, không annotation | Không | Có | Không | Không |
| Public, có `@RepositoryRestResource` | Có | Có | Có | Có |
| Package-private, có `@RepositoryRestResource` | Có | Có | Không | Có |

Bảng cho thấy hai điểm dễ nhầm:

- **Annotation có thể mở đường cho repository package-private** khi dùng `DEFAULT` hoặc `ANNOTATED`.
- **Annotation không mở rộng phạm vi của `VISIBILITY`**: repository vẫn phải là public. Ngược lại, `ANNOTATED` yêu cầu annotation nên một repository public nhưng không được đánh dấu sẽ không được công bố.

`ALL` là lựa chọn rộng nhất: mọi Spring Data repository đều được xét để export. Vì strategy này bỏ qua cấu hình visibility và annotation, không nên dựa vào annotation để giới hạn danh sách khi đã chọn `ALL`.

## 5. Chọn strategy theo mục tiêu

- Dùng **`DEFAULT`** khi muốn giữ hành vi thông thường: repository public được công bố tự động, còn repository không public có thể được chọn rõ bằng annotation.
- Dùng **`ANNOTATED`** khi muốn quản lý danh sách repository REST theo kiểu opt-in: chỉ những repository được đánh dấu mới trở thành resource.
- Dùng **`VISIBILITY`** khi quy ước của dự án là chỉ interface public mới được công bố, bất kể annotation.
- Dùng **`ALL`** khi thực sự muốn export tất cả repository, kể cả interface không public. Hãy kiểm tra kỹ phạm vi API trước khi chọn.

Nếu mục tiêu là một danh sách API được chủ động cho phép, `ANNOTATED` thường dễ rà soát hơn: nhìn vào repository interface có thể nhận ra repository nào được đánh dấu để công bố. Với chiến lược này, `exported = false` cho phép loại một repository đã được đánh dấu khỏi danh sách export.

## 6. Cấu hình detection strategy

Với Spring Boot, có thể đặt strategy trong `application.properties`:

```properties
spring.data.rest.detection-strategy=annotated
```

Các giá trị tương ứng là `default`, `all`, `visibility` và `annotated`.

Nếu cần cấu hình bằng Java, đăng ký một `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy.RepositoryDetectionStrategies;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategies.ANNOTATED);
    }
}
```

Cấu hình này thay đổi cách Spring Data REST chọn repository để export. Nó không thay thế cấu hình scan repository của module lưu trữ.

## 7. Annotation ở cấp repository và cấp method

Cần phân biệt hai cấp điều khiển:

- `@RepositoryRestResource(exported = false)` đặt trên interface để yêu cầu không công bố repository đó.
- `@RestResource(exported = false)` đặt trên query method, CRUD method hoặc association phù hợp để ẩn phần resource tương ứng.

Ví dụ ẩn một query method nhưng vẫn giữ collection resource:

```java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @RestResource(exported = false)
    List<Customer> findByEmail(String email);
}
```

Trong ví dụ này, repository vẫn được công bố; riêng endpoint tìm kiếm theo email không được export. Nếu muốn ẩn cả repository, đặt `exported = false` trên annotation cấp interface.

## 8. Cách kiểm tra khi repository không xuất hiện

Khi một repository không có link trong REST API, hãy kiểm tra theo thứ tự:

1. **Repository đã được Spring Data module nhận diện chưa?** Kiểm tra interface có kế thừa repository phù hợp, đúng module lưu trữ và nằm trong vùng scan hay không.
2. **Interface có phải public không?** Nếu package-private, `DEFAULT` và `VISIBILITY` có thể không chọn nó nếu không có annotation phù hợp.
3. **Strategy đang dùng là gì?** Đọc `spring.data.rest.detection-strategy` hoặc cấu hình trong `RepositoryRestConfigurer`; đừng suy luận từ annotation đơn lẻ.
4. **Annotation có được đặt đúng cấp không?** `@RepositoryRestResource` điều khiển repository; `@RestResource` có thể điều khiển method hoặc association.
5. **Có cấu hình base path không?** Resource có thể nằm dưới tiền tố khác thay vì ở root `/`.

Có thể gửi `GET /` (hoặc base path đã cấu hình) và xem các link HAL để kiểm tra collection resource nào đang được công bố. Nếu collection resource hoàn toàn không có, hãy kiểm tra detection strategy và việc nhận diện repository. Nếu collection có nhưng một thao tác trả về `405 Method Not Allowed`, hãy kiểm tra method tương ứng có tồn tại và có bị ẩn bằng `@RestResource(exported = false)` hay không.

Cuối cùng, không dùng Java visibility hoặc detection strategy làm cơ chế bảo mật. Chúng quyết định resource nào được tạo; quyền người dùng được phép gọi endpoint phải được bảo vệ riêng bằng Spring Security và các quy tắc authorization phù hợp.

## Tóm tắt

- `public` ảnh hưởng đến việc repository có được chọn theo `DEFAULT` hoặc `VISIBILITY` hay không.
- `@RepositoryRestResource` cho phép khai báo rõ repository cần công bố và tùy chỉnh resource.
- `DEFAULT` kết hợp public visibility với annotation; `ALL` bỏ qua cả hai; `VISIBILITY` chỉ xét public; `ANNOTATED` yêu cầu annotation.
- `@RepositoryRestResource` điều khiển cấp repository; `@RestResource` có thể ẩn method hoặc association cụ thể.
- Việc repository được export không đồng nghĩa endpoint đã được bảo vệ bằng xác thực và phân quyền.

## Tài liệu tham khảo

- [Spring Data REST — Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [RepositoryDetectionStrategy.RepositoryDetectionStrategies — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html)
- [@RepositoryRestResource — API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
