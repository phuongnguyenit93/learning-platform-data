# Thiết kế DTO, kiểm tra đầu vào và chuyển đổi sang mô hình lưu trữ

Trong ứng dụng Spring WebFlux dùng Spring Data Relational R2DBC, dữ liệu đi từ HTTP request qua nhiều lớp trước khi được ghi xuống database. DTO mô tả hợp đồng API; validation xác nhận request hợp lệ; application service thực hiện quy tắc nghiệp vụ; mapper chuyển dữ liệu sang mô hình domain hoặc entity; repository R2DBC đảm nhiệm persistence reactive.

Tách các trách nhiệm này giúp API không phụ thuộc trực tiếp vào schema database. Khi thêm cột nội bộ, đổi tên property hoặc thay cách lưu trữ, hợp đồng HTTP có thể giữ nguyên. Ngược lại, khi API thay đổi, entity và schema không phải thay đổi theo một cách máy móc.

Một luồng xử lý điển hình:

~~~mermaid
flowchart TD
    A[HTTP request JSON] --> B[WebFlux deserialization]
    B --> C[Request DTO]
    C --> D[Bean Validation]
    D --> E[Application service]
    E --> F[Domain/business validation]
    F --> G[Mapper]
    G --> H[R2DBC persistence entity]
    H --> I[Reactive repository]
    I --> J[(Database)]
    J --> K[Saved entity]
    K --> L[Response mapper]
    L --> M[Response DTO]
    M --> N[HTTP response JSON]
~~~

Bài học này trình bày cách thiết kế request/response DTO, sử dụng Bean Validation trong WebFlux, thực hiện kiểm tra nghiệp vụ bất đồng bộ, chuyển DTO sang entity R2DBC, xử lý create/update/PATCH, chuẩn hóa lỗi API và kiểm thử toàn bộ luồng reactive.

## 1. Phân biệt DTO, domain model và persistence entity

Ba loại object có thể chứa dữ liệu tương tự nhưng có mục đích khác nhau.

| Loại object | Trách nhiệm | Ví dụ field |
| --- | --- | --- |
| Request DTO | Mô tả dữ liệu client được phép gửi. | name, price, categoryId |
| Domain model/command | Biểu diễn ý định và quy tắc nghiệp vụ. | CreateProductCommand, Product |
| Persistence entity | Biểu diễn dữ liệu được Spring Data ánh xạ với bảng. | id, name, price, categoryId, createdAt |
| Response DTO | Mô tả dữ liệu API được phép trả về. | id, name, price, createdAt |

Không nên dùng một entity làm request body và response body cho mọi endpoint. Làm như vậy có thể khiến client gửi được những field chỉ server mới được quyền quản lý, hoặc làm lộ dữ liệu nội bộ khi serialize response.

Ví dụ, bảng products có các cột:

~~~sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0),
    category_id UUID NOT NULL,
    internal_cost NUMERIC(12, 2),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE
);
~~~

Client chỉ cần gửi tên, giá bán và category. Client không được tự quyết định id, internal_cost, created_at hoặc updated_at.

Request DTO:

~~~java
public record CreateProductRequest(
    String name,
    BigDecimal price,
    UUID categoryId
) {}
~~~

Persistence entity có thể chứa nhiều field hơn:

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("category_id") UUID categoryId,
    @Column("internal_cost") BigDecimal internalCost,
    @Column("created_at") Instant createdAt,
    @Column("updated_at") Instant updatedAt
) {}
~~~

Response DTO chỉ trả field công khai:

~~~java
public record ProductResponse(
    UUID id,
    String name,
    BigDecimal price,
    UUID categoryId,
    Instant createdAt
) {}
~~~

Cách tách này giúp tránh mass assignment: client không thể ghi trực tiếp những field như internalCost hoặc audit timestamp chỉ bằng cách thêm chúng vào JSON.

## 2. Thiết kế request DTO theo use case

Nên thiết kế DTO theo thao tác API thay vì cố dùng một DTO lớn cho mọi tình huống.

Ví dụ:

- CreateProductRequest: dữ liệu tối thiểu để tạo sản phẩm.
- ReplaceProductRequest: toàn bộ field mà client được phép thay thế trong PUT.
- PatchProductRequest: các field có thể cập nhật một phần.
- ProductResponse: dữ liệu trả về.
- ProductSummaryResponse: projection nhỏ cho danh sách.

Create và update thường có yêu cầu khác nhau. Khi tạo mới, name và price có thể bắt buộc. Khi cập nhật một phần, các field có thể vắng mặt. Dùng chung DTO có thể làm validation trở nên mơ hồ.

DTO nên biểu diễn hợp đồng HTTP, không nên mang annotation persistence như @Table, @Id hoặc @Column. Tương tự, entity R2DBC không nên mang trách nhiệm của một request model.

### Dùng kiểu dữ liệu phù hợp

| Dữ liệu | Kiểu Java thường phù hợp | Lưu ý |
| --- | --- | --- |
| Tiền/giá | BigDecimal | Tránh double/float cho số tiền cần độ chính xác. |
| ID UUID | UUID | Xác định format JSON và database tương ứng. |
| Ngày giờ tuyệt đối | Instant hoặc OffsetDateTime | Quy định rõ timezone và cách lưu. |
| Ngày lịch | LocalDate | Không tự gắn timezone nếu nghiệp vụ chỉ là ngày. |
| Số lượng | Integer/Long | Dùng kiểu đủ phạm vi và kiểm tra giới hạn. |
| Trạng thái | Enum hoặc string code | Không cho client tùy ý đặt trạng thái nội bộ. |
| Danh sách con | List<DTO> | Dùng nested validation. |

Không dùng String cho mọi field chỉ vì JSON truyền dữ liệu dưới dạng text. Kiểu DTO nên thể hiện ý nghĩa và giúp Jackson/validation phát hiện dữ liệu sai sớm.

## 3. Bean Validation cho request DTO

Spring WebFlux hỗ trợ Jakarta Bean Validation khi ứng dụng có provider tương ứng và request body được đánh dấu validation. Với Spring Boot, dependency thường dùng là validation starter.

Ví dụ dependency Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Request DTO có thể khai báo constraint trực tiếp:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
    @NotBlank(message = "Name is required")
    @Size(max = 160, message = "Name must not exceed 160 characters")
    String name,

    @NotNull(message = "Price is required")
    @DecimalMin(value = "0.01", message = "Price must be greater than zero")
    BigDecimal price,

    @NotNull(message = "Category is required")
    UUID categoryId
) {}
~~~

Các constraint này kiểm tra dữ liệu cục bộ, không cần truy cập database:

- @NotNull: giá trị không được null.
- @NotBlank: chuỗi không null, không rỗng và có ít nhất một ký tự không phải whitespace.
- @NotEmpty: chuỗi, collection hoặc array không được null/rỗng tùy kiểu hỗ trợ.
- @Size: giới hạn độ dài hoặc số phần tử.
- @Positive/@PositiveOrZero: kiểm tra dấu số.
- @DecimalMin/@DecimalMax: giới hạn số thập phân.
- @Email: kiểm tra hình dạng địa chỉ email theo validator.
- @Pattern: kiểm tra chuỗi bằng regular expression.
- @Past/@Future: kiểm tra quan hệ thời gian.

Validation không thay thế constraint ở database. Request hợp lệ ở tầng HTTP vẫn có thể xung đột với dữ liệu được ghi bởi request khác.

### Kết hợp nhiều constraint

Một field có thể có nhiều constraint:

~~~java
public record RegisterCustomerRequest(
    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 8, max = 100)
    String password
) {}
~~~

Mỗi constraint kiểm tra một điều kiện. Không nên viết một regex khổng lồ cho mọi quy tắc nếu các annotation tiêu chuẩn đã diễn đạt rõ.

Với tiền, dùng BigDecimal và giới hạn cả giá trị lẫn precision/scale nếu hợp đồng API yêu cầu. @Digits có thể giới hạn số chữ số nguyên và phần thập phân:

~~~java
@Digits(integer = 10, fraction = 2)
@DecimalMin("0.01")
BigDecimal price
~~~

Database vẫn nên có NUMERIC/DECIMAL với precision và scale phù hợp.

## 4. Validation cho object lồng nhau và collection

Nếu request chứa object con, đặt @Valid để kích hoạt validation đệ quy.

~~~java
public record CreateOrderRequest(
    @NotNull
    UUID customerId,

    @NotEmpty
    @Size(max = 100)
    List<@NotNull @Valid CreateOrderLineRequest> items
) {}

public record CreateOrderLineRequest(
    @NotNull
    UUID productId,

    @NotNull
    @Positive
    Integer quantity
) {}
~~~

Ở đây:

- @NotEmpty yêu cầu danh sách có ít nhất một phần tử.
- @Size(max = 100) giới hạn số dòng trong một request.
- @NotNull trên phần tử ngăn danh sách chứa null.
- @Valid yêu cầu validator kiểm tra từng CreateOrderLineRequest.
- @Positive bảo đảm quantity lớn hơn 0.

Nếu chỉ đặt @Valid trên collection nhưng không có @NotEmpty, danh sách rỗng vẫn có thể hợp lệ. Nếu chỉ đặt @NotNull cho collection, danh sách rỗng vẫn được chấp nhận. Hãy chọn constraint đúng với hợp đồng nghiệp vụ.

### Validation cấp object

Một số quy tắc phụ thuộc nhiều field, ví dụ ngày bắt đầu phải trước ngày kết thúc. Có thể tạo class-level constraint:

~~~java
@ValidDateRange
public record SearchBookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, SearchBookingRequest> {

    @Override
    public boolean isValid(
            SearchBookingRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return !value.endDate().isBefore(value.startDate());
    }
}
~~~

Các constraint @NotNull riêng chịu trách nhiệm bắt field thiếu. Class-level validator trả true khi thiếu một trong hai field để tránh tạo lỗi trùng lặp hoặc dereference null. Nếu muốn gắn lỗi vào một field cụ thể, có thể dùng ConstraintValidatorContext để thêm property node.

Custom Bean Validation validator nên thực hiện kiểm tra đồng bộ, nhanh và không có side effect. Không gọi database reactive bằng cách block trong ConstraintValidator.

## 5. Kích hoạt validation trong WebFlux controller

Với annotated controller, đánh dấu request body bằng @Valid:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService products;

    public ProductController(ProductService products) {
        this.products = products;
    }

    @PostMapping
    public Mono<ResponseEntity<ProductResponse>> create(
            @Valid @RequestBody CreateProductRequest request) {

        return products.create(request)
            .map(response -> ResponseEntity
                .created(URI.create("/api/products/" + response.id()))
                .body(response));
    }
}
~~~

WebFlux giải mã JSON thành DTO rồi thực hiện validation trước khi chuyển request vào controller. Nếu request body không hợp lệ, pipeline xử lý request kết thúc bằng lỗi binding/validation.

Không cần tự gọi validator rồi subscribe trong controller cho trường hợp request body thông thường. Dùng cơ chế validation tích hợp của Spring giúp lỗi được xử lý trong request lifecycle.

### Validation cho query parameter và path variable

Các tham số đơn như page, size hoặc quantity cũng cần kiểm tra:

~~~java
@GetMapping
public Flux<ProductResponse> list(
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {

    return products.list(page, size);
}
~~~

Cách kích hoạt method validation và loại exception có thể khác giữa các phiên bản Spring Framework. Với Spring Framework 6.1 trở lên, native method validation của MVC/WebFlux có các cơ chế và exception riêng; ứng dụng dùng @Validated class-level AOP có thể đi theo đường xử lý khác. Hãy cấu hình theo phiên bản Spring Boot đang dùng và chuẩn hóa các loại lỗi validation tương ứng trong exception advice.

Không cho client yêu cầu page size không giới hạn. Giới hạn tối đa giúp tránh một request tạo ra lượng dữ liệu quá lớn.

## 6. Xử lý validation error nhất quán

WebFlux có thể phát sinh WebExchangeBindException khi request body không vượt qua binding/validation. Các lỗi method validation có thể dùng exception khác tùy phiên bản framework và kiểu khai báo controller.

Nên chuẩn hóa thành response error DTO thay vì trả trực tiếp exception:

~~~java
public record ApiValidationError(
    String code,
    String message,
    Map<String, String> fieldErrors
) {}
~~~

Ví dụ exception advice cho lỗi request body:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiValidationError> handleBodyValidation(
            WebExchangeBindException exception) {

        Map<String, String> errors = exception.getFieldErrors().stream()
            .collect(Collectors.toMap(
                FieldError::getField,
                error -> Objects.requireNonNullElse(
                    error.getDefaultMessage(),
                    "Invalid value"
                ),
                (first, ignored) -> first
            ));

        ApiValidationError body = new ApiValidationError(
            "VALIDATION_FAILED",
            "Request contains invalid fields",
            errors
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Ví dụ minh họa handler đồng bộ cho exception validation. Nếu ứng dụng chuẩn hóa mọi handler theo reactive return type, có thể trả Mono<ResponseEntity<ApiValidationError>>. Cần bổ sung handler cho các exception method validation được phiên bản Spring của dự án sử dụng.

Response ví dụ:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "fieldErrors": {
    "name": "Name is required",
    "price": "Price must be greater than zero"
  }
}
~~~

Không trả stack trace, SQL, tên bảng nội bộ hoặc thông tin kết nối trong response. Với client, error code và field path ổn định hữu ích hơn raw message từ database hoặc validator.

### Không phụ thuộc vào câu chữ lỗi để client xử lý

Thông điệp có thể thay đổi theo locale hoặc phiên bản. Nếu frontend cần logic ổn định, hãy dùng error code như VALIDATION_FAILED, PRODUCT_NOT_FOUND hoặc PRODUCT_CODE_CONFLICT; message chỉ dành cho hiển thị.

## 7. Phân biệt validation đầu vào và validation nghiệp vụ

Không phải mọi quy tắc đều nên đặt trong Bean Validation.

Có thể chia thành ba lớp:

| Lớp | Loại kiểm tra | Ví dụ |
| --- | --- | --- |
| Request validation | Kiểm tra hình dạng và giới hạn dữ liệu. | Name không rỗng, price dương, items không rỗng. |
| Domain/application validation | Kiểm tra quy tắc nghiệp vụ. | Sản phẩm phải thuộc category đang hoạt động; người dùng có quyền đặt hàng. |
| Database constraints | Bảo vệ tính toàn vẹn ở mức lưu trữ. | UNIQUE code, FOREIGN KEY category_id, CHECK price > 0. |

Bean Validation không nên truy cập database để kiểm tra category tồn tại hoặc email chưa được sử dụng. Validator chuẩn là synchronous; việc truy vấn database từ đó thường dẫn tới block hoặc tạo một cơ chế bất đồng bộ khó kiểm soát.

Thay vào đó, service thực hiện kiểm tra bất đồng bộ bằng repository:

~~~java
public Mono<Product> create(CreateProductCommand command) {
    return categories.findById(command.categoryId())
        .switchIfEmpty(Mono.error(
            new CategoryNotFoundException(command.categoryId())
        ))
        .flatMap(category -> {
            if (!category.active()) {
                return Mono.error(
                    new CategoryInactiveException(category.id())
                );
            }

            ProductEntity entity = mapper.toNewEntity(command);
            return products.save(entity);
        });
}
~~~

Đây là reactive domain check: repository trả publisher, service kết hợp bằng flatMap và switchIfEmpty. Không cần block để lấy category trước khi lưu.

### Kiểm tra trước ghi không thay thế constraint

Giả sử service kiểm tra email chưa tồn tại rồi mới insert. Hai request đồng thời có thể cùng vượt qua bước kiểm tra và cùng insert. Unique constraint ở database mới là lớp bảo vệ cuối cùng.

Luồng đúng là:

1. Validation đầu vào giúp trả lỗi sớm và rõ.
2. Kiểm tra nghiệp vụ giúp tạo thông báo phù hợp.
3. Database constraint bảo vệ dữ liệu trong điều kiện cạnh tranh.
4. Service chuyển lỗi constraint cụ thể thành lỗi domain/API.

Không bỏ unique constraint chỉ vì đã có một query exists trước insert.

## 8. Chuyển DTO thành command và entity lưu trữ

Không nên để controller tự xây dựng entity hoặc chứa logic persistence. Có thể dùng mapper để chuyển DTO thành command:

~~~java
public record CreateProductCommand(
    String name,
    BigDecimal price,
    UUID categoryId
) {}
~~~

Mapper thuần:

~~~java
@Component
public class ProductRequestMapper {

    public CreateProductCommand toCommand(CreateProductRequest request) {
        return new CreateProductCommand(
            request.name().trim(),
            request.price(),
            request.categoryId()
        );
    }
}
~~~

Application service nhận command:

~~~java
@Service
public class ProductService {

    private final ProductRepository products;
    private final CategoryRepository categories;
    private final ProductMapper mapper;
    private final Clock clock;

    public ProductService(
            ProductRepository products,
            CategoryRepository categories,
            ProductMapper mapper,
            Clock clock) {
        this.products = products;
        this.categories = categories;
        this.mapper = mapper;
        this.clock = clock;
    }

    public Mono<ProductResponse> create(CreateProductCommand command) {
        return categories.findById(command.categoryId())
            .switchIfEmpty(Mono.error(
                new CategoryNotFoundException(command.categoryId())
            ))
            .flatMap(category -> {
                if (!category.active()) {
                    return Mono.error(
                        new CategoryInactiveException(category.id())
                    );
                }

                ProductEntity entity = mapper.toNewEntity(
                    command,
                    clock.instant()
                );

                return products.save(entity)
                    .map(mapper::toResponse);
            });
    }
}
~~~

Trong ví dụ, ProductMapper thực hiện chuyển đổi thuần giữa command, entity và response. Clock được inject để kiểm thử timestamp ổn định thay vì gọi thời gian toàn cục ở nhiều nơi.

Controller chỉ điều phối HTTP và chuyển request DTO thành command:

~~~java
@PostMapping
public Mono<ResponseEntity<ProductResponse>> create(
        @Valid @RequestBody CreateProductRequest request) {

    CreateProductCommand command = requestMapper.toCommand(request);

    return productService.create(command)
        .map(response -> ResponseEntity
            .created(URI.create("/api/products/" + response.id()))
            .body(response));
}
~~~

Tùy kiến trúc, controller có thể gọi service nhận DTO trực tiếp rồi mapper bên trong service. Điều quan trọng là không để entity persistence trở thành hợp đồng request/response ngoài ý muốn.

## 9. Mapping entity R2DBC

Spring Data Relational ánh xạ entity với bảng bằng các annotation như @Table, @Id và @Column.

~~~java
@Table("products")
public record ProductEntity(
    @Id UUID id,
    String name,
    BigDecimal price,
    @Column("category_id") UUID categoryId,
    @Column("created_at") Instant createdAt,
    @Column("updated_at") Instant updatedAt
) {}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<ProductEntity, UUID> {
}
~~~

Mapper có thể viết thủ công:

~~~java
@Component
public class ProductMapper {

    public ProductEntity toNewEntity(
            CreateProductCommand command,
            Instant now) {

        return new ProductEntity(
            null,
            command.name(),
            command.price(),
            command.categoryId(),
            now,
            now
        );
    }

    public ProductResponse toResponse(ProductEntity entity) {
        return new ProductResponse(
            entity.id(),
            entity.name(),
            entity.price(),
            entity.categoryId(),
            entity.createdAt()
        );
    }
}
~~~

Nếu ID do database sinh, entity mới có thể để id null theo chiến lược ID và database đã cấu hình. Spring Data R2DBC có thể nhận giá trị ID được sinh và trả entity đã lưu tùy kiểu cột, driver và cách mapping. Hãy xác nhận bằng integration test trên database mục tiêu.

Không trả entity trực tiếp cho API. Response mapper là nơi chọn field công khai, đổi format hoặc ẩn cột nội bộ.

### Khi nào dùng MapStruct?

MapStruct phù hợp với mapping lặp lại giữa nhiều DTO, command và entity. Nó tạo code mapping tại compile time, giúp phát hiện một số lỗi kiểu dữ liệu sớm.

Với mapping nhỏ, constructor hoặc factory method tường minh thường dễ đọc hơn. Dù dùng công cụ nào, các quyết định nghiệp vụ như giá trị mặc định, quyền sở hữu field và thời điểm tạo ID phải được thể hiện rõ, không để mapper tự động sao chép mọi property một cách thiếu kiểm soát.

## 10. Dùng map và flatMap đúng trong reactive mapping

Trong reactive service:

- map dùng khi chuyển đổi đồng bộ một giá trị đã có.
- flatMap dùng khi bước tiếp theo trả về Mono/Flux.
- then dùng khi chỉ quan tâm publisher trước hoàn tất, không cần giá trị của nó.
- switchIfEmpty xử lý publisher không phát phần tử.
- onErrorMap chuyển loại lỗi nhưng vẫn giữ error signal.

Ví dụ mapping đồng bộ:

~~~java
return productRepository.findById(id)
    .map(mapper::toResponse);
~~~

Ví dụ cần kiểm tra category bất đồng bộ:

~~~java
return categoryRepository.findById(categoryId)
    .switchIfEmpty(Mono.error(
        new CategoryNotFoundException(categoryId)
    ))
    .flatMap(category ->
        productRepository.save(
            mapper.toEntity(command, category)
        )
    )
    .map(mapper::toResponse);
~~~

Không dùng map khi lambda trả Mono, nếu không sẽ tạo Mono<Mono<T>>. Không dùng block để lấy kết quả reactive rồi mới mapping.

### Không tự subscribe trong controller/service

Không viết:

~~~java
public Mono<ProductResponse> create(CreateProductRequest request) {
    productRepository.save(mapper.toEntity(request)).subscribe();
    return Mono.just(new ProductResponse(...));
}
~~~

Cách này tách thao tác ghi khỏi publisher trả về. Caller có thể nhận response trước khi insert hoàn tất, lỗi insert không truyền tới HTTP pipeline và transaction context không còn được kiểm soát đúng.

Hãy trả publisher kết hợp đầy đủ:

~~~java
public Mono<ProductResponse> create(CreateProductCommand command) {
    return productRepository.save(mapper.toEntity(command))
        .map(mapper::toResponse);
}
~~~

## 11. Create, PUT và PATCH cần DTO khác nhau

Create, replace và partial update có semantics khác nhau.

### Create

Create DTO thường yêu cầu các field bắt buộc và không nhận ID do server sinh:

~~~java
public record CreateProductRequest(
    @NotBlank @Size(max = 160) String name,
    @NotNull @DecimalMin("0.01") BigDecimal price,
    @NotNull UUID categoryId
) {}
~~~

### PUT: thay thế biểu diễn được phép cập nhật

PUT thường thể hiện một trạng thái thay thế cho resource theo hợp đồng API. Các field bắt buộc cần có validation rõ:

~~~java
public record ReplaceProductRequest(
    @NotBlank @Size(max = 160) String name,
    @NotNull @DecimalMin("0.01") BigDecimal price,
    @NotNull UUID categoryId
) {}
~~~

Service nên tải entity hiện tại, kiểm tra quyền và chuyển trạng thái theo quy tắc domain. Không nên dùng request làm entity hoàn chỉnh rồi save trực tiếp.

### PATCH: cập nhật một phần

PATCH cho phép chỉ gửi một số field. Ví dụ:

~~~java
public record PatchProductRequest(
    @Size(max = 160) String name,
    @DecimalMin("0.01") BigDecimal price
) {}
~~~

Trong ví dụ đơn giản này, null có thể được quy ước là “không thay đổi”. Nhưng khi đó client không thể dùng null để xóa một field nullable. Java record cũng không tự phân biệt field bị bỏ qua với field được gửi rõ ràng là null sau khi deserialize.

Nếu API cần ba trạng thái — không gửi field, gửi null để xóa, gửi giá trị để cập nhật — hãy dùng một kiểu biểu diễn presence-aware, ví dụ JsonNullable với module Jackson phù hợp hoặc một custom deserializer/patch document. Không đoán semantics từ null.

### Cập nhật entity hiện tại

~~~java
public Mono<ProductResponse> patch(
        UUID id,
        PatchProductRequest request) {

    return products.findById(id)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
        .flatMap(current -> {
            String name = request.name() == null
                ? current.name()
                : request.name().trim();

            BigDecimal price = request.price() == null
                ? current.price()
                : request.price();

            ProductEntity updated = new ProductEntity(
                current.id(),
                name,
                price,
                current.categoryId(),
                current.createdAt(),
                clock.instant()
            );

            return products.save(updated);
        })
        .map(mapper::toResponse);
}
~~~

Ví dụ này quy ước null là không đổi và không cho patch category. Nếu category cũng được phép cập nhật, cần kiểm tra category tồn tại và còn hoạt động trước khi lưu. Nếu field có thể được xóa bằng null, phải dùng presence-aware DTO để phân biệt rõ.

Không cho request PATCH thay đổi id, createdAt, internalCost hoặc owner/tenant chỉ bằng cách thêm property ngoài hợp đồng.

## 12. Kiểm tra quyền và dữ liệu theo tenant

Một request có thể hợp lệ về kiểu nhưng không được phép truy cập resource. Ví dụ client gửi categoryId tồn tại nhưng thuộc tenant khác.

Không tin tenantId, ownerId hoặc userId được gửi trong request nếu các giá trị đó phải lấy từ danh tính đã xác thực. Đọc identity từ security context hoặc thông tin đã được server xác minh, rồi áp dụng vào query/service.

Ví dụ:

~~~java
public Mono<ProductResponse> create(
        CreateProductCommand command,
        UUID authenticatedTenantId) {

    return categories.findByIdAndTenantId(
            command.categoryId(),
            authenticatedTenantId
        )
        .switchIfEmpty(Mono.error(
            new CategoryNotFoundException(command.categoryId())
        ))
        .flatMap(category ->
            products.save(mapper.toNewEntity(
                command,
                authenticatedTenantId
            ))
        )
        .map(mapper::toResponse);
}
~~~

Query có tenant condition giúp tránh lấy dữ liệu của tenant khác. Database constraint có thể bổ sung bảo vệ nếu schema được thiết kế để đảm bảo quan hệ tenant.

Validation và authorization là hai việc khác nhau: field hợp lệ không đồng nghĩa người dùng có quyền thực hiện thao tác đó.

## 13. Chuyển lỗi nghiệp vụ và constraint thành HTTP response

Application service nên phát exception domain rõ ràng thay vì trả null hoặc chuỗi lỗi tự do.

Ví dụ:

- ProductNotFoundException: resource không tồn tại.
- CategoryNotFoundException: tham chiếu không hợp lệ.
- CategoryInactiveException: quy tắc nghiệp vụ không cho phép.
- ProductCodeAlreadyExistsException: xung đột mã duy nhất.

Controller advice chuyển exception thành status và error DTO:

~~~java
@RestControllerAdvice
public class ProductApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            ProductNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "PRODUCT_NOT_FOUND",
                "Product was not found"
            ));
    }

    @ExceptionHandler(ProductCodeAlreadyExistsException.class)
    public ResponseEntity<ApiError> handleConflict(
            ProductCodeAlreadyExistsException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError(
                "PRODUCT_CODE_CONFLICT",
                "Product code already exists"
            ));
    }
}
~~~

Trong WebFlux, exception handler có thể trả về reactive type nếu cần; các ví dụ dùng ResponseEntity trực tiếp cho response đồng bộ sau khi exception đã phát sinh.

Nếu repository phát DuplicateKeyException, chỉ chuyển thành ProductCodeAlreadyExistsException khi xác định đúng constraint tương ứng. Không chuyển mọi DataIntegrityViolationException thành 409 cho cùng một lý do, vì lỗi NOT NULL, CHECK hoặc FOREIGN KEY có semantics khác.

Không để raw SQL error, constraint message hoặc stack trace lộ ra ngoài API.

## 14. Chuẩn hóa dữ liệu ở đúng lớp

Một số phép chuẩn hóa có thể làm ở DTO mapper hoặc domain factory:

- Trim khoảng trắng ở đầu/cuối.
- Chuẩn hóa mã sản phẩm theo quy ước.
- Chuyển chuỗi rỗng thành null nếu hợp đồng cho phép.
- Chuẩn hóa enum/string code.
- Tạo giá trị dẫn xuất không phụ thuộc database.

Các thao tác cần kiến thức database hoặc mapping nên nằm ở persistence mapper/converter. Các quy tắc nghiệp vụ không nên bị giấu trong DTO constructor.

Ví dụ factory:

~~~java
public record CreateProductCommand(
    String name,
    BigDecimal price,
    UUID categoryId
) {
    public static CreateProductCommand from(
            CreateProductRequest request) {

        return new CreateProductCommand(
            request.name().trim(),
            request.price(),
            request.categoryId()
        );
    }
}
~~~

Không trim hoặc lower-case mọi chuỗi theo một quy tắc chung. Với tên hiển thị, địa chỉ, mật khẩu, mã định danh và email có semantics khác nhau. Chuẩn hóa phải có chủ đích và nhất quán với cách tìm kiếm/so sánh.

### Tiền và làm tròn

Không tự động làm tròn giá trị BigDecimal trong mapper nếu nghiệp vụ chưa quy định. Nếu database có scale hai chữ số, cần xác định:

- API có chấp nhận nhiều hơn hai chữ số không?
- Có làm tròn HALF_UP, HALF_EVEN hay từ chối?
- Giá trị được lưu và giá trị trả về có cùng scale không?
- Currency được xác định ở đâu?

Hãy đặt quy tắc ở domain/application layer và bảo đảm database precision/scale tương ứng.

## 15. Phân trang và sắp xếp từ request

Nếu API nhận page, size hoặc sort, không truyền trực tiếp mọi giá trị client gửi vào SQL.

Giới hạn page size:

~~~java
private Pageable toPageable(int page, int size) {
    if (page < 0) {
        throw new InvalidPageRequestException("Page must be non-negative");
    }

    if (size < 1 || size > 100) {
        throw new InvalidPageRequestException(
            "Page size must be between 1 and 100"
        );
    }

    return PageRequest.of(
        page,
        size,
        Sort.by(Sort.Direction.DESC, "createdAt")
    );
}
~~~

Nếu cho client chọn sort field, dùng allowlist property được phép. Không ghép tên cột tự do vào SQL. Bind parameter chỉ thay thế giá trị, không thay thế identifier hoặc keyword.

Với R2DBC custom SQL, dùng named bind parameters cho giá trị và whitelist tên cột/order direction trước khi tạo cấu trúc SQL.

## 16. Kiểm thử DTO, validation và mapping

Nên chia kiểm thử theo tầng.

### Unit test DTO validation

Có thể dùng Validator của Jakarta Bean Validation để xác minh constraints:

~~~java
@Test
void rejectsInvalidCreateProductRequest() {
    CreateProductRequest request = new CreateProductRequest(
        " ",
        BigDecimal.ZERO,
        null
    );

    Set<ConstraintViolation<CreateProductRequest>> violations =
        validator.validate(request);

    assertFalse(violations.isEmpty());
}
~~~

Test này xác minh constraint trên DTO, không cần database.

### WebFlux controller test

Dùng WebTestClient gửi request sai:

~~~java
@Test
void returnsBadRequestForInvalidProduct() {
    webTestClient.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {
              "name": " ",
              "price": 0,
              "categoryId": null
            }
            """)
        .exchange()
        .expectStatus().isBadRequest()
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_FAILED");
}
~~~

Nên kiểm tra service không bị gọi khi request validation thất bại. Cấu hình test context phải dùng WebFlux và exception advice thật để xác nhận pipeline validation.

### Unit test mapper

Kiểm tra DTO/command chuyển thành entity đúng:

~~~java
@Test
void mapsCreateCommandToNewEntity() {
    Instant now = Instant.parse("2026-01-01T00:00:00Z");

    ProductEntity entity = mapper.toNewEntity(command, now);

    assertNull(entity.id());
    assertEquals(command.name(), entity.name());
    assertEquals(command.price(), entity.price());
    assertEquals(now, entity.createdAt());
}
~~~

Mapper test giúp phát hiện field bị bỏ quên hoặc gán nhầm. Nếu dùng MapStruct, có thể kiểm tra mapping generated code qua test hành vi.

### R2DBC integration test

Dùng database thật hoặc Testcontainers để kiểm tra:

- Entity được ghi với đúng cột.
- Generated ID được trả về.
- Enum, UUID, BigDecimal và timestamp mapping đúng.
- Constraint được database thực thi.
- Readback tạo response DTO đúng.
- Lỗi duplicate được chuyển thành domain/API error phù hợp.

Mock repository không thể xác nhận schema, driver conversion hoặc constraint thực tế.

## 17. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng entity làm request body | API phụ thuộc schema và dễ bị mass assignment. | Tạo request DTO riêng. |
| Client có thể gửi id/createdAt/internal field | DTO nhận quá nhiều property hoặc bind entity trực tiếp. | Chỉ khai báo field client được phép gửi. |
| @Valid không chạy | Thiếu annotation trên request body, provider hoặc cấu hình validation. | Thêm validation dependency và @Valid. |
| Nested DTO không được validate | Thiếu @Valid ở object/collection lồng nhau. | Đặt @Valid và constraint collection phù hợp. |
| Dùng Bean Validation để query database | Validator đồng bộ bị block hoặc sai reactive model. | Chuyển kiểm tra tồn tại/quyền sang service reactive. |
| Exists check rồi vẫn duplicate | Race condition giữa kiểm tra và insert. | Giữ unique constraint và xử lý duplicate cụ thể. |
| PATCH không thể xóa field nullable | DTO không phân biệt omitted và explicit null. | Dùng presence-aware patch representation. |
| Dùng map cho bước trả Mono | Tạo Mono lồng nhau. | Dùng flatMap. |
| Gọi subscribe/block trong controller/service | Tách publisher khỏi request lifecycle. | Trả và kết hợp Publisher. |
| Response lộ cột nội bộ | Serialize entity trực tiếp. | Dùng response DTO và mapper. |
| Update ghi đè field server quản lý | Sao chép toàn bộ request vào entity. | Tải entity hiện tại và cập nhật allowlist field. |
| Validation lỗi trả 500 | Exception advice không xử lý exception WebFlux phù hợp. | Chuẩn hóa binding và method validation exception. |
| Dữ liệu hợp lệ ở API nhưng lỗi database | Thiếu domain check hoặc DB constraint/type khác hợp đồng. | Đồng bộ validation, mapping và schema. |

## 18. Quy trình thiết kế một endpoint WebFlux với R2DBC

Khi xây dựng endpoint tạo hoặc cập nhật resource, có thể đi theo trình tự:

1. **Xác định hợp đồng HTTP:** request gửi field nào, response được phép trả field nào?
2. **Tạo DTO riêng:** không tái sử dụng entity persistence làm request/response.
3. **Chọn kiểu dữ liệu:** BigDecimal cho tiền, UUID cho định danh, kiểu ngày giờ đúng semantics.
4. **Khai báo Bean Validation:** kiểm tra null, blank, size, range và nested object.
5. **Kích hoạt validation trong WebFlux:** dùng @Valid cho request body và chuẩn hóa lỗi binding.
6. **Tạo command/domain input:** chuẩn hóa dữ liệu theo quy tắc nghiệp vụ.
7. **Kiểm tra bất đồng bộ:** dùng repository reactive để xác minh resource, trạng thái và quyền.
8. **Map sang entity:** chỉ gán field server cho phép và tạo metadata có chủ đích.
9. **Lưu bằng R2DBC:** kết hợp publisher qua map/flatMap, không subscribe/block.
10. **Map kết quả thành response DTO:** chỉ trả field công khai.
11. **Chuyển lỗi thành API error:** phân biệt validation, not found, conflict và lỗi hệ thống.
12. **Kiểm thử từng tầng:** validator, mapper, WebFlux endpoint và database integration.

Thiết kế DTO, validation và mapping rõ ràng giúp WebFlux giữ được luồng reactive xuyên suốt từ HTTP tới R2DBC. Request DTO bảo vệ hợp đồng API; Bean Validation kiểm tra dữ liệu cục bộ; application service thực hiện quy tắc nghiệp vụ bất đồng bộ; mapper chuyển dữ liệu sang entity persistence; repository chịu trách nhiệm lưu trữ. Khi tách các lớp này, giới hạn field được kiểm soát, lỗi được phản hồi nhất quán và thay đổi schema ít ảnh hưởng tới API.
