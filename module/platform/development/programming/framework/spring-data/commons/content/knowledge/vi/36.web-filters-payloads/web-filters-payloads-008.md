# Xác thực payload và tách đối tượng đầu vào khỏi entity lưu trữ

## 1. Payload là hợp đồng thao tác, entity là trạng thái lưu trữ

Trong chương **Bộ lọc và payload web** của module **SPRING_DATA_COMMONS**, đối tượng nhận từ HTTP cần mô tả điều client được phép yêu cầu. Entity mô tả dữ liệu và metadata mà hệ thống quản lý để lưu trữ.

Hai đối tượng có thể chứa một số field giống nhau, nhưng không có cùng trách nhiệm.

Ví dụ tạo sản phẩm:

- Client được gửi SKU, tên, giá và tồn kho ban đầu theo quyền nghiệp vụ.
- Server xác định tenant từ ngữ cảnh đã xác thực.
- Store hoặc ứng dụng cấp ID theo chiến lược đã chọn.
- Version và auditing metadata được quản lý theo vòng đời lưu trữ.
- Một trạng thái như đã duyệt không được tự nhận từ request tạo thông thường.

Luồng có chủ đích:

~~~text
JSON hoặc form
    → input DTO
    → kiểm tra cấu trúc và giá trị đầu vào
    → command nghiệp vụ
    → kiểm tra quyền và quy tắc theo trạng thái
    → tạo/cập nhật aggregate trong phạm vi được phép
    → repository và ràng buộc của store
    → response DTO
~~~

Spring Data cung cấp abstraction repository, query và metadata chung. Nó không tự quyết định field nào người dùng được sửa hoặc tự biến mọi payload hợp lệ về cú pháp thành một lệnh nghiệp vụ hợp lệ.

## 2. Vì sao không nhận entity rồi save trực tiếp?

Cách viết ngắn sau che nhiều quyết định:

~~~java
@PostMapping("/products")
public Product create(@RequestBody Product product) {
    return repository.save(product);
}
~~~

Nếu Product có thêm tenantId, approved, version hoặc metadata nội bộ, chữ ký này dễ khiến hợp đồng đầu vào mở rộng theo sự phát triển của entity.

Các rủi ro cần xét:

| Vấn đề | Tình huống |
| --- | --- |
| Gán field ngoài quyền | Request cố thay tenantId hoặc trạng thái phê duyệt |
| Sai vòng đời create/update | Request tạo mang ID của một bản ghi đã có |
| Ghi đè dữ liệu không được gửi | Payload thiếu field nhưng entity mới có null hoặc giá trị mặc định |
| Mất metadata | Mapping thay thế làm mất version, createdAt hoặc chủ sở hữu |
| Ràng buộc bị dùng sai | Constraint phục vụ lưu trữ không phù hợp với từng thao tác web |
| API phụ thuộc schema | Một thay đổi entity vô tình đổi field nhận hoặc field trả về |

Mức tác động thực tế còn phụ thuộc mapper, accessor và cấu hình. Không nên dựa vào giả định rằng các field nhạy cảm “chắc sẽ bị bỏ qua”.

Một DTO chỉ có field được phép nhận làm giới hạn đầu vào dễ thấy hơn. Tuy nhiên, vẫn phải ánh xạ có chủ đích và kiểm tra quyền ở tầng nghiệp vụ.

## 3. Phân biệt các lớp kiểm tra

| Lớp | Ví dụ | Vị trí thích hợp |
| --- | --- | --- |
| Đọc và chuyển đổi | JSON sai cú pháp, chuỗi không chuyển được thành số | HTTP message converter |
| Constraint đầu vào | Tên không trống, giá dương, danh sách không quá dài | DTO và Bean Validation |
| Quyền truy cập | Người gọi được tạo sản phẩm cho tenant nào? | Security và service |
| Quy tắc nghiệp vụ | Sản phẩm đã khóa có được đổi giá không? | Domain/service |
| Tính toàn vẹn đồng thời | Hai request tạo cùng SKU | Unique constraint, version hoặc cơ chế store phù hợp |

Validation không thay thế authorization. Transaction không tự cấp quyền. Unique constraint cũng không tự tạo một thông báo lỗi phù hợp cho API.

Ví dụ dùng Java 17, Spring MVC trong hệ Spring Boot 3.5 và jakarta.validation. Ứng dụng phải có Bean Validation provider cùng cấu hình tương ứng; chỉ thêm annotation vào source không tự kích hoạt việc kiểm tra ở mọi đường gọi. [Bean Validation trong Spring](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)

## 4. DTO riêng cho thao tác tạo

~~~java
package com.example.catalog;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank
        @Pattern(regexp = "[A-Z0-9][A-Z0-9_-]{2,31}")
        String sku,

        @NotBlank
        @Size(max = 120)
        String name,

        @NotNull
        @DecimalMin("0.01")
        @Digits(integer = 10, fraction = 2)
        BigDecimal price,

        @NotNull
        @Min(0)
        Integer initialStock) {
}
~~~

Hợp đồng của ví dụ:

- SKU có từ 3 đến 32 ký tự, bắt đầu bằng chữ hoa hoặc chữ số; các ký tự còn lại có thể thêm dấu gạch dưới hoặc gạch ngang.
- Tên phải có nội dung và không quá 120 ký tự theo constraint đã chọn.
- Giá tối thiểu 0.01, có tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân.
- Tồn kho ban đầu bắt buộc có mặt dưới dạng một giá trị không âm.

Không có id, tenantId, approved hoặc createdBy trong DTO này.

### 4.1. Constraint null cần được hiểu riêng

Nhiều constraint về kích thước, định dạng hoặc khoảng giá trị chấp nhận null để có thể kết hợp với NotNull khi cần. NotBlank tự bao gồm yêu cầu về chuỗi không null và có nội dung.

Vì vậy, chỉ đặt Min(0) trên Integer không đủ biểu đạt “bắt buộc phải gửi”. Wrapper Integer kết hợp NotNull giúp phân biệt null với số 0 trong trường hợp tạo này. Primitive int thường không thể giữ thông tin null sau bước deserialize.

Bean Validation cũng hỗ trợ constraint trên phần tử container và cascade validation. [Đặc tả Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)

DTO trên không phân biệt missing và explicit null sau khi cả hai đã được deserialize thành null. Đối với create, cả hai đều bị từ chối ở field bắt buộc; với PATCH, cần hợp đồng khác.

### 4.2. Chuẩn hóa phải có chính sách rõ ràng

Ví dụ chọn từ chối SKU viết thường hoặc có khoảng trắng bằng constraint định dạng. Không tự chuyển mọi SKU thành chữ hoa mà chưa xem xét ý nghĩa nghiệp vụ.

Tên sản phẩm có thể được bỏ khoảng trắng ở hai đầu trước khi tạo aggregate. Phải xác định constraint áp lên chuỗi trước hay sau chuẩn hóa, và bảo vệ cùng ý nghĩa ở các đường gọi khác.

Tránh đổi dữ liệu không hợp lệ thành một giá trị mặc định chỉ để lưu được. Giá âm không nên tự trở thành 0 nếu nghiệp vụ không quy định như vậy.

## 5. Controller kích hoạt validation và ánh xạ sang command

Command mô tả lệnh nghiệp vụ, không chứa annotation của cơ chế JSON:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record CreateProductCommand(
        String sku,
        String name,
        BigDecimal price,
        int initialStock) {
}
~~~

Controller ánh xạ tường minh:

~~~java
package com.example.catalog;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping("/products")
    public ResponseEntity<ProductView> create(
            @Valid @RequestBody CreateProductRequest request) {

        var command = new CreateProductCommand(
                request.sku(),
                request.name(),
                request.price(),
                request.initialStock());

        ProductView created = service.create(command);

        return ResponseEntity
                .created(URI.create("/products/" + created.id()))
                .body(created);
    }
}
~~~

RequestBody đi qua HTTP message converter; Valid yêu cầu validation thích hợp trước khi xử lý đối tượng đầu vào. Với chữ ký đơn giản này, lỗi constraint của body thường đi theo MethodArgumentNotValidException và được xử lý thành HTTP 400. [RequestBody và validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)

Việc ánh xạ bốn field là một danh sách field được phép dùng cho lệnh tạo. Không dùng một phép copy mọi property từ payload sang entity rồi trông chờ rằng schema sau này sẽ không thêm field nhạy cảm.

Command vẫn cần được kiểm tra ở domain/service vì có thể đến từ một đường gọi ngoài HTTP. Valid trên controller không bảo vệ mọi caller.

## 6. Aggregate và repository: minh họa bằng Spring Data JDBC

Phần lưu trữ dưới đây chọn Spring Data JDBC để minh họa. Annotation Table thuộc relational mapping, còn Id và Version thuộc Spring Data. Đây không phải cấu hình entity JPA.

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("catalog_product")
public record Product(
        @Id Long id,
        UUID tenantId,
        String sku,
        String name,
        BigDecimal price,
        int stock,
        @Version Long version) {

    public static Product create(
            UUID tenantId, CreateProductCommand command) {

        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(command, "command");

        if (command.sku() == null
                || !command.sku().matches(
                        "[A-Z0-9][A-Z0-9_-]{2,31}")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }

        if (command.name() == null
                || command.name().isBlank()
                || command.name().length() > 120) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }

        BigDecimal price = command.price();
        if (price == null
                || price.compareTo(new BigDecimal("0.01")) < 0
                || price.scale() > 2
                || (long) price.precision() - price.scale() > 10) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }

        if (command.initialStock() < 0) {
            throw new IllegalArgumentException("Tồn kho không hợp lệ");
        }

        return new Product(
                null,
                tenantId,
                command.sku(),
                command.name().strip(),
                price,
                command.initialStock(),
                null);
    }
}
~~~

Factory bảo vệ lệnh tạo ngay cả khi caller không đi qua MVC. Ví dụ giữ các kiểm tra thuần, không gọi repository từ một constraint chỉ để kiểm tra hình thức của field.

Các constraint ở DTO và invariant của domain có phần giao nhau nhưng phục vụ các biên khác nhau. Có thể dùng hằng số/quy tắc chung khi phù hợp để tránh hai nơi thay đổi lệch nhau; không nên buộc domain phụ thuộc trực tiếp vào mọi chi tiết web.

Schema test và mapping phải phù hợp: ID được sinh theo chiến lược của backend, kiểu UUID được hỗ trợ và version được cấu hình đúng. Với JPA, MongoDB hoặc store khác, dùng mapping và cơ chế metadata tương ứng.

Repository:

~~~java
package com.example.catalog;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    boolean existsByTenantIdAndSku(UUID tenantId, String sku);

    Optional<Product> findByIdAndTenantId(Long id, UUID tenantId);
}
~~~

Derived query có tenant trong tên method để thể hiện phạm vi cần kiểm soát. Nó không tự cung cấp tenant đáng tin cậy: service phải lấy đúng giá trị từ ngữ cảnh server.

## 7. Service xác định tenant và quản lý lệnh tạo

Một abstraction lấy tenant hiện tại:

~~~java
package com.example.catalog;

import java.util.UUID;

public interface CurrentTenant {

    UUID requireId();
}
~~~

Implementation phải xác nhận người gọi và tenant đang hoạt động theo cơ chế xác thực của ứng dụng. Không triển khai requireId bằng cách tin trực tiếp query parameter hoặc header do client tùy ý gửi.

Response DTO có thể độc lập với entity:

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductView(
        Long id,
        String sku,
        String name,
        BigDecimal price,
        int stock,
        Long version) {
}
~~~

Service minh họa:

~~~java
package com.example.catalog;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ProductService {

    private final ProductRepository repository;
    private final CurrentTenant currentTenant;

    public ProductService(
            ProductRepository repository,
            CurrentTenant currentTenant) {
        this.repository = repository;
        this.currentTenant = currentTenant;
    }

    @PreAuthorize("hasAuthority('catalog:write')")
    @Transactional
    public ProductView create(CreateProductCommand command) {
        UUID tenantId = currentTenant.requireId();
        Product product = Product.create(tenantId, command);

        if (repository.existsByTenantIdAndSku(
                tenantId, product.sku())) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "SKU đã được sử dụng");
        }

        Product saved = repository.save(product);

        return new ProductView(
                saved.id(),
                saved.sku(),
                saved.name(),
                saved.price(),
                saved.stock(),
                saved.version());
    }
}
~~~

Ví dụ giả định method security đã được bật, transaction infrastructure đã được cấu hình và lời gọi đi qua bean/proxy thích hợp. Hệ thống thực tế có thể dùng một kiểu lỗi nghiệp vụ riêng thay ResponseStatusException để tách sâu hơn khỏi HTTP.

Không lấy tenantId, ID hoặc version ban đầu từ DTO tạo. Với aggregate bất biến, sử dụng instance trả về từ save để đọc ID và metadata sau lưu. CrudRepository nêu rõ thao tác save có thể trả instance khác với instance đầu vào. [Hợp đồng CrudRepository.save](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html)

### 7.1. exists rồi save vẫn có race condition

Hai transaction có thể cùng thấy SKU chưa tồn tại, sau đó cùng tạo.

Nếu nghiệp vụ yêu cầu SKU duy nhất trong mỗi tenant, schema còn cần unique constraint trên cặp tenant và SKU. Ví dụ logic SQL khi mapping dùng các column tương ứng:

~~~sql
ALTER TABLE catalog_product
ADD CONSTRAINT uq_product_tenant_sku
UNIQUE (tenant_id, sku);
~~~

Cú pháp và migration phải phù hợp database thực tế. Với document store hoặc loại kho khác, dùng cơ chế uniqueness tương ứng.

Kiểm tra exists giúp phản hồi sớm, nhưng không thay thế ràng buộc đồng thời. Lỗi unique cuối cùng có thể xuất hiện lúc thực thi ghi hoặc hoàn tất transaction. Việc chuyển nó thành 409 cần nhận diện đúng ràng buộc đã biết ở biên xử lý thích hợp.

Không đổi mọi DataIntegrityViolationException thành “SKU trùng”: lỗi đó có thể do ràng buộc khác, schema sai hoặc một nguyên nhân cần được xử lý riêng.

## 8. Chuẩn hóa lỗi payload mà không lộ dữ liệu đầu vào

API nên phân biệt lỗi không đọc được body với lỗi constraint trên một object đã đọc được.

Một controller advice cho chữ ký body đơn giản của ví dụ:

~~~java
package com.example.catalog;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PayloadErrors {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalid(
            MethodArgumentNotValidException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Payload không thỏa điều kiện đầu vào");

        problem.setTitle("Dữ liệu đầu vào không hợp lệ");
        problem.setProperty("code", "INVALID_PAYLOAD");

        var errors = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> new Violation(
                        error instanceof FieldError field
                                ? field.getField()
                                : "$",
                        error.getDefaultMessage()))
                .toList();

        problem.setProperty("errors", errors);
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ProblemDetail> unreadable(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Không đọc được payload theo định dạng yêu cầu");

        problem.setProperty("code", "UNREADABLE_PAYLOAD");
        return ResponseEntity.badRequest().body(problem);
    }

    public record Violation(String path, String message) {
    }
}
~~~

Ví dụ không đưa rejected value, toàn bộ request body hoặc thông điệp parser nội bộ vào response. Client có thể sửa field dựa trên path và message; hệ thống vẫn có thể dùng mã lỗi ổn định cùng cơ chế localization đã chọn.

Advice trên chưa bao phủ mọi loại validation của mọi chữ ký controller. Khi đặt constraint trực tiếp lên tham số method, Spring MVC có thể sử dụng HandlerMethodValidationException. Method validation qua proxy cũng có đường lỗi riêng. Cần ánh xạ đúng những trường hợp ứng dụng thực sự sử dụng. [Các cấp validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)

Nếu controller tự nhận BindingResult để xử lý lỗi, phải kiểm tra lỗi trước khi gọi service. Không vừa thấy lỗi rồi vẫn save như một luồng bình thường.

## 9. Field không khai báo trong DTO cần một chính sách

Request có thể cố gửi thêm:

~~~json
{
  "sku": "BOOK_001",
  "name": "Spring Data",
  "price": 100.00,
  "initialStock": 5,
  "tenantId": "tenant-khac",
  "approved": true,
  "version": 999
}
~~~

CreateProductRequest không có các field tenantId, approved và version. Tuy vậy, phản ứng HTTP còn phụ thuộc cấu hình deserializer:

- Chính sách nghiêm ngặt: từ chối property không biết.
- Chính sách cho phép mở rộng: bỏ qua property không biết, nhưng không ánh xạ chúng vào state nội bộ.

Cả hai đều cần kiểm thử; không suy rằng thiếu field trong DTO đồng nghĩa request luôn bị trả 400.

Với Spring Boot 3.5 và Jackson 2 của ví dụ, một lựa chọn cấu hình nghiêm ngặt là:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
~~~

Đây là ví dụ cấu hình của ứng dụng sử dụng bài học. Hiệu lực phải được xác nhận với mapper/converter thực tế, đặc biệt khi có tùy biến mapper hoặc nhiều media type. [Tích hợp Jackson của Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/features/json.html)

Chấp nhận một kiểu Java không nhất thiết đồng nghĩa JSON đã có đúng kiểu ký tự ban đầu: mapper có thể có quy tắc coercion. Nếu API bắt buộc giá là JSON number thay vì một string chuyển đổi được, hãy cấu hình và kiểm thử chính quy tắc đó.

### 9.1. JSON body và form binding không dùng mọi cơ chế giống nhau

WebDataBinder có thể cấu hình các field được phép bind cho đường property binding phù hợp. Điều này hữu ích với model attribute/form object. Tuy nhiên, không mặc định setAllowedFields sẽ tự lọc mọi property trong JSON RequestBody do Jackson deserialize.

Input DTO và mapping tường minh vẫn giúp thể hiện hợp đồng ở từng đường nhận dữ liệu. [WebDataBinder và InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)

## 10. Payload lồng nhau, collection và constraint liên field

Một API tạo nhiều sản phẩm có thể dùng DTO bọc:

~~~java
package com.example.catalog;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BatchCreateProductRequest(
        @NotEmpty
        @Size(max = 50)
        List<@NotNull @Valid CreateProductRequest> products) {
}
~~~

Cần kiểm tra cả container và phần tử:

- NotEmpty yêu cầu danh sách không null và có phần tử.
- Size giới hạn số phần tử theo hợp đồng.
- NotNull ở type argument từ chối phần tử null.
- Valid kích hoạt kiểm tra lồng vào từng request con.

Valid không tự có nghĩa là mọi object con phải khác null. Nếu object con bắt buộc tồn tại, cần constraint null tương ứng.

Với quy tắc như startDate không sau endDate, constraint riêng từng field là chưa đủ. Có thể dùng constraint ở cấp object hoặc kiểm tra nghiệp vụ phù hợp, đồng thời trả lỗi có đường dẫn/quy ước rõ ràng.

Không thực hiện một query đắt tiền cho từng phần tử chỉ để validation hình thức. Với thao tác batch, quyết định rõ toàn bộ cùng thành công hay cho phép kết quả riêng từng phần tử; transaction và lỗi phải phản ánh quyết định đó.

Giới hạn Size của collection được kiểm tra sau khi body đã được đọc thành object. Giới hạn request size, độ phức tạp parser hoặc số phần tử trước bước tạo object là những cơ chế riêng khi hạ tầng yêu cầu.

## 11. Create, replace và PATCH cần các hợp đồng khác nhau

Dùng cùng một DTO lớn cho mọi thao tác thường dẫn đến nhiều field “tùy lúc bắt buộc”. Có thể dùng validation groups khi thật sự phù hợp, nhưng DTO theo từng thao tác thường làm quyền sửa và ý nghĩa field rõ hơn.

| Thao tác | Câu hỏi cần chốt |
| --- | --- |
| Create | Field nào bắt buộc, field nào do server cấp? |
| Replace | Request có biểu diễn toàn bộ phần state mà client được thay thế không? |
| PATCH | Field vắng khác field gửi null như thế nào? |
| Đổi trạng thái | Người nào được chuyển từ trạng thái nào sang trạng thái nào? |

### 11.1. Không dùng null làm hai nghĩa cùng lúc

Ví dụ cập nhật tên:

| Payload | Một chính sách PATCH có thể chọn |
| --- | --- |
| Không có name | Giữ nguyên tên |
| name có string hợp lệ | Đổi tên |
| name là null | Từ chối vì tên không được null |
| name là chuỗi trắng | Từ chối theo invariant |

Một record chỉ có String name không tự giữ được sự khác biệt giữa field vắng và explicit null nếu cả hai deserialize thành null.

Cần một cơ chế ghi nhận sự hiện diện của field hoặc một định dạng patch đã được thiết kế và kiểm tra. Không coi Optional là giải pháp tự động cho mọi semantics missing/null.

### 11.2. Cập nhật aggregate đã được phép đọc

Đường cập nhật nên:

1. Nhận ID từ vị trí API đã quy định và DTO chỉ chứa thay đổi được phép.
2. Lấy tenant/actor từ ngữ cảnh server.
3. Tải aggregate theo cả ID và phạm vi được phép.
4. Kiểm tra trạng thái và token/version mong đợi nếu hợp đồng yêu cầu.
5. Áp dụng thay đổi có chủ đích, giữ metadata cần bảo toàn.
6. Lưu trong ranh giới transaction phù hợp và xử lý xung đột đồng thời.

Không tạo một Product mới từ request cập nhật rồi tùy tiện gán ID cũ và version null. Cách đó có thể làm sai nhận diện entity mới, vòng đời update hoặc optimistic locking theo module.

Nếu API nhận expectedVersion hoặc dùng If-Match, giá trị đó là điều kiện đồng thời cần kiểm tra. Nó không phải quyền cho client tự ghi metadata version bất kỳ vào bản ghi.

Kiểm tra version do client biết và kiểm tra version tại thời điểm ghi có thể bảo vệ các khoảng thời gian khác nhau. Thiết kế phải giữ ý nghĩa của cả hai khi nghiệp vụ cần.

## 12. Metadata và auditing do server quản lý

Một chính sách sở hữu field nên được viết rõ:

| Field | Nguồn quản lý trong ví dụ |
| --- | --- |
| SKU, tên, giá, tồn kho ban đầu | Payload đã kiểm tra và người có quyền thao tác |
| Tenant | Ngữ cảnh tenant đã xác thực |
| ID | Chiến lược cấp ID của ứng dụng/store |
| Version | Cơ chế đồng thời của module lưu trữ |
| CreatedBy, LastModifiedBy | Actor từ hạ tầng auditing đáng tin cậy |
| CreatedDate, LastModifiedDate | Nguồn thời gian của hạ tầng auditing |
| Trạng thái phê duyệt | Use case có quyền và quy tắc chuyển trạng thái |

Spring Data có abstraction auditing cho người tạo/sửa và thời điểm tạo/sửa, nhưng cần cấu hình theo store. Việc thêm field vào entity hoặc bỏ field khỏi DTO không tự bật auditing. [Auditing trong Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/auditing.html)

Ví dụ Product JDBC phía trên chỉ minh họa ID và version, chưa cấu hình đầy đủ auditing. Không suy rằng metadata người tạo/thời gian đã tự được lưu trong ví dụ đó.

Auditing cũng không thay thế phân quyền. Có createdBy trong dữ liệu không đồng nghĩa mọi query đã tự giới hạn theo người hiện tại.

Response DTO có thể công bố version phục vụ điều kiện cập nhật nếu hợp đồng cần. Không vì vậy mà đưa toàn bộ entity, tenant hoặc metadata nội bộ vào mọi response.

## 13. Payload projection và DTO lọc cũng cần ranh giới riêng

Spring Data có hỗ trợ đọc payload qua projection trong một số tích hợp web, chẳng hạn ProjectedPayload với các biểu thức đọc dữ liệu. Khả năng trích một giá trị không tự chứng minh giá trị đó đã được validation, được phép sử dụng hoặc có semantics cập nhật phù hợp.

Nếu dùng interface projection cho input, cần kiểm chứng việc áp dụng constraint trên getter, object lồng nhau và lỗi thiếu field với đúng hạ tầng đang dùng. Không giả định nó có cùng hành vi với record DTO trong mọi cấu hình. [Web databinding và payload projection](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)

Đối với bộ lọc tìm kiếm, nên có DTO riêng thay vì tái sử dụng CreateProductRequest hoặc bind trực tiếp entity làm mọi tiêu chí. Giá trị mặc định của entity, field metadata hoặc tenant do client gửi có thể làm lệch ý nghĩa tìm kiếm.

Derived query hoặc Query by Example giúp diễn đạt truy vấn; quyền truy cập vẫn phải được đưa vào phạm vi query hoặc policy thích hợp. Payload hợp lệ không được tự mở rộng phạm vi dữ liệu.

## 14. Kiểm thử body không hợp lệ trước khi service được gọi

Ví dụ kiểm thử MVC theo baseline Boot 3.5, có Spring Security Test và Mockito. Test chọn chính sách từ chối unknown property:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(
        controllers = ProductController.class,
        properties =
                "spring.jackson.deserialization.fail-on-unknown-properties=true")
@Import(PayloadErrors.class)
@WithMockUser(authorities = "catalog:write")
class ProductPayloadTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;

    @Test
    void invalidValuesDoNotReachService() throws Exception {
        mvc.perform(post("/products")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "BOOK_001",
                                  "name": "   ",
                                  "price": -1,
                                  "initialStock": null
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PAYLOAD"))
                .andExpect(jsonPath("$.errors").isArray());

        verifyNoInteractions(service);
    }

    @Test
    void unknownServerManagedFieldIsRejected() throws Exception {
        mvc.perform(post("/products")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "sku": "BOOK_001",
                                  "name": "Spring Data",
                                  "price": 100.00,
                                  "initialStock": 5,
                                  "tenantId": "tenant-khac"
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
~~~

WithMockUser và csrf phục vụ môi trường test có bảo mật tương ứng; khi dùng cơ chế xác thực riêng, cần thiết lập ngữ cảnh test phù hợp. Không tắt các filter rồi mặc định test đã phản ánh đầy đủ API được bảo vệ.

MockitoBean thay bean service trong context bằng mock. Vì vậy, test này kiểm tra biên MVC, chưa chứng minh quyền, tenant, domain factory hoặc transaction của service thật đã hoạt động. [Bean override bằng MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)

Các đoạn code là tài liệu minh họa thiết kế kiểm thử, không phải báo cáo một môi trường cụ thể đã chạy thành công.

### 14.1. Những bằng chứng còn cần ở các lớp khác

| Trường hợp | Bằng chứng cần có |
| --- | --- |
| Payload hợp lệ | Command chỉ mang field được phép và response theo hợp đồng |
| Giá quá nhiều chữ số | Constraint từ chối đúng field |
| Batch có phần tử null hoặc không hợp lệ | Cascade và container constraint hoạt động |
| Caller ngoài HTTP gửi command sai | Domain/service từ chối trước khi ghi |
| Tạo sản phẩm | Tenant lấy từ context đáng tin cậy |
| Hai tenant có cùng SKU | Hành vi đúng phạm vi uniqueness đã chọn |
| Hai request cùng tenant tạo cùng SKU | Ràng buộc store bảo vệ tính duy nhất |
| Cập nhật đối tượng tenant khác | Không ghi được tài nguyên ngoài quyền |
| PATCH thiếu field và gửi null | Có kết quả khác nhau theo hợp đồng |
| Update cạnh tranh | Version/điều kiện đồng thời được tôn trọng |
| Auditing | Field không bị payload ghi đè, nguồn actor/thời gian đúng |
| Response | Không xuất hiện field nội bộ ngoài hợp đồng |

Mock repository không chứng minh database có unique constraint. Một test repository không tự chứng minh validation của controller. Mỗi lớp kiểm thử phải gắn với điều nó thực sự quan sát được.

## 15. Các lỗi thiết kế thường gặp

| Cách làm | Điều cần sửa |
| --- | --- |
| RequestBody là entity rồi save ngay | Dùng input DTO và mapping theo thao tác |
| Chỉ dựa vào Valid trên controller | Bảo vệ cả đường gọi nghiệp vụ ngoài HTTP |
| Tin tenantId hoặc createdBy từ JSON | Lấy giá trị từ ngữ cảnh server đã xác thực |
| Bỏ qua null và missing trong PATCH | Lưu thông tin hiện diện và định nghĩa semantics |
| Copy mọi property sang entity | Liệt kê field được phép hoặc cấu hình mapper rõ ràng |
| Dùng exists làm bằng chứng duy nhất của uniqueness | Có ràng buộc đồng thời tại store |
| Tự đặt lại version khi cập nhật | Giữ đúng vòng đời và điều kiện optimistic locking |
| Dùng cùng DTO cho create, approve và search | Phân tách theo quyền và ý nghĩa của từng thao tác |
| Đổi mọi lỗi database thành lỗi người dùng | Chỉ ánh xạ nguyên nhân đã xác định |
| Trả toàn bộ exception hoặc rejected value | Dùng mã lỗi/path an toàn theo hợp đồng |

## 16. Tự kiểm tra

1. Vì sao một entity có constraint vẫn không nên mặc nhiên làm request DTO?
2. NotNull và Min(0) bảo vệ hai điều khác nhau như thế nào?
3. Valid ở controller có bảo vệ lời gọi service từ một tác vụ nền không?
4. Vì sao tenant, ID và auditing metadata không nên được copy từ JSON tạo?
5. Hai request đều qua existsByTenantIdAndSku có thể vẫn tạo xung đột như thế nào?
6. Một DTO chỉ có String name thiếu thông tin gì để xử lý PATCH?
7. Expected version của client khác quyền sửa metadata version ở điểm nào?
8. Vì sao test MVC dùng mock service chưa chứng minh database hoặc phân quyền đúng?
9. Khi dùng payload projection, cần xác minh thêm những hành vi nào?

Một biên đầu vào rõ ràng mô tả được dữ liệu client được gửi, cách dữ liệu ấy được kiểm tra và quyền mà thao tác cần có. DTO riêng, mapping tường minh, invariant nghiệp vụ và ràng buộc store phối hợp giúp repository cùng metadata Spring Data được sử dụng đúng theo khả năng của từng loại kho dữ liệu.
