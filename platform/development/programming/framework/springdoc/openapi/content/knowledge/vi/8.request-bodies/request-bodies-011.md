# Giới hạn giữa mô tả cấu trúc đầu vào với kiểm tra dữ liệu ở thời gian chạy

Khi mô tả request body bằng springdoc-openapi, cần phân biệt hai việc: **công bố hợp đồng dữ liệu để client hiểu cách gửi request** và **kiểm tra dữ liệu thực tế khi ứng dụng nhận request**. OpenAPI Schema mô tả cấu trúc, kiểu dữ liệu và các ràng buộc mà client nên tuân theo. Spring MVC, Jackson, Bean Validation và tầng nghiệp vụ mới quyết định request có được chấp nhận khi chạy hay không.

Hai phần này nên thống nhất, nhưng chúng không tự thay thế cho nhau. Một schema có thể mô tả chuỗi tối đa 50 ký tự trong khi controller không bật validation; ngược lại, ứng dụng có thể từ chối một request vì quy tắc nghiệp vụ mà schema không thể diễn tả đầy đủ. Bài này giúp phân biệt các lớp đó và kiểm tra hợp đồng đầu vào một cách có hệ thống.

## 1. Ba lớp xử lý dữ liệu đầu vào

Một request JSON đi qua nhiều bước trước khi nghiệp vụ được thực hiện:

1. **Hợp đồng OpenAPI:** mô tả request body, media type, schema, field bắt buộc, kiểu dữ liệu, enum và các constraint có thể công bố.
2. **Binding và deserialize:** Spring MVC nhận HTTP request; Jackson chuyển JSON thành object Java. Nếu JSON sai cú pháp hoặc không chuyển được kiểu, request có thể bị từ chối ngay tại bước này.
3. **Validation và nghiệp vụ:** Bean Validation kiểm tra các constraint được khai báo; service/domain tiếp tục kiểm tra quy tắc phụ thuộc trạng thái hệ thống, quyền, dữ liệu hiện có hoặc quan hệ giữa nhiều trường.

Ví dụ, API tạo sản phẩm nhận JSON có trường name và price:

~~~json
{
  "name": "Wireless Mouse",
  "price": 450000
}
~~~

OpenAPI có thể mô tả name là chuỗi không rỗng và price là số lớn hơn 0. Khi request đến:

- Jackson kiểm tra JSON có thể chuyển thành CreateProductRequest hay không.
- Bean Validation kiểm tra name không trống và price dương nếu controller kích hoạt validation.
- Service kiểm tra mã sản phẩm có bị trùng, danh mục có tồn tại và người dùng có quyền tạo sản phẩm hay không.

Mỗi lớp trả lời một câu hỏi khác nhau. Schema giúp client xây dựng request hợp lệ theo hợp đồng; runtime validation bảo vệ ứng dụng; nghiệp vụ quyết định request có hợp lệ trong trạng thái thực tế của hệ thống hay không.

## 2. RequestBody và Schema trong OpenAPI

Trong OpenAPI, request body của một operation được mô tả bằng đối tượng Request Body. Trường content xác định media type và schema tương ứng.

Ví dụ rút gọn:

~~~yaml
paths:
  /api/products:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateProductRequest'
      responses:
        '201':
          description: Đã tạo sản phẩm

components:
  schemas:
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 120
        price:
          type: number
          minimum: 0
~~~

Có hai khái niệm required cần phân biệt:

- **requestBody.required:** cho biết toàn bộ body có bắt buộc phải gửi hay không.
- **schema.required:** liệt kê những property bắt buộc phải có bên trong object.

Nếu requestBody.required là true nhưng schema không liệt kê property nào trong required, body vẫn phải có nhưng các field có thể không bị đánh dấu bắt buộc. Ngược lại, property được liệt kê trong schema.required chỉ có ý nghĩa khi body được gửi.

Schema có thể mô tả:

| Thành phần | Ý nghĩa |
|---|---|
| type | Kiểu dữ liệu như object, string, integer, number, boolean hoặc array |
| required | Danh sách property bắt buộc trong object |
| properties | Định nghĩa từng field của object |
| enum | Tập giá trị được liệt kê |
| minLength / maxLength | Giới hạn độ dài chuỗi |
| minimum / maximum | Giới hạn giá trị số |
| minItems / maxItems | Giới hạn số phần tử của mảng |
| pattern | Biểu thức chính quy cho chuỗi |
| format | Gợi ý định dạng như date, date-time, email hoặc uuid |
| description / example | Giải thích và ví dụ cho client |

Các constraint này mô tả hợp đồng. Công cụ client có thể dùng chúng để hiển thị form, sinh mã hoặc kiểm tra request trước khi gửi. Việc backend có thực sự thực thi tất cả constraint hay không phụ thuộc implementation.

## 3. Dùng @Schema để mô tả hợp đồng

Annotation @Schema thuộc swagger-annotations và cung cấp metadata cho tài liệu OpenAPI. Có thể đặt trên DTO hoặc từng field:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

import java.math.BigDecimal;

@Schema(
    name = "CreateProductRequest",
    description = "Dữ liệu tạo sản phẩm mới"
)
public class CreateProductRequest {

    @Schema(
        description = "Tên sản phẩm",
        example = "Wireless Mouse",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    private String name;

    @Schema(
        description = "Giá bán, phải lớn hơn 0",
        example = "450000",
        minimum = "0.01",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    private BigDecimal price;

    @Schema(
        description = "Mô tả ngắn về sản phẩm",
        example = "Chuột không dây dùng cho văn phòng",
        maxLength = 500
    )
    private String description;

    // Constructor mặc định, getters và setters.
}
~~~

Các thuộc tính như description, example, minLength, maxLength, minimum và requiredMode giúp tài liệu rõ ràng hơn. Chúng không tự thêm logic kiểm tra vào controller.

Ví dụ, khai báo maxLength = 120 trên @Schema không làm Spring từ chối chuỗi dài 121 ký tự. Nếu muốn backend thực thi giới hạn này, cần thêm constraint runtime như @Size(max = 120) và kích hoạt validation.

Một DTO có thể dùng cả @Schema và Bean Validation trên cùng field. Cách này giúp hợp đồng công bố và quy tắc chạy thực tế nằm gần nhau, dễ đọc và dễ bảo trì.

## 4. Bean Validation kiểm tra dữ liệu khi chạy

Bean Validation định nghĩa các constraint như @NotNull, @NotBlank, @Size, @Min, @Max, @DecimalMin và @Pattern. Với Spring Boot 3, các annotation chuẩn thuộc namespace jakarta.validation.

Ví dụ:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public class CreateProductRequest {

    @NotBlank
    @Size(max = 120)
    private String name;

    @NotNull
    @DecimalMin(value = "0.01")
    private BigDecimal price;

    @Size(max = 500)
    private String description;

    // Constructor mặc định, getters và setters.
}
~~~

Các constraint thường gặp:

| Constraint | Điều kiện runtime |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không null và có ít nhất một ký tự không phải khoảng trắng |
| @NotEmpty | Chuỗi hoặc collection không được rỗng |
| @Size(min, max) | Độ dài chuỗi hoặc kích thước collection nằm trong giới hạn |
| @Min / @Max | Giá trị số nằm trong giới hạn nguyên |
| @DecimalMin / @DecimalMax | Giá trị số nằm trong giới hạn thập phân |
| @Positive / @PositiveOrZero | Giá trị phải dương hoặc không âm |
| @Email | Kiểm tra chuỗi theo quy tắc email của provider |
| @Pattern | Chuỗi phải khớp regular expression |
| @Past / @Future | Ngày hoặc thời điểm nằm trước hoặc sau hiện tại |

Cần chú ý rằng @NotNull và @NotBlank không giống nhau. @NotNull chỉ cấm null; chuỗi rỗng vẫn có thể được chấp nhận. @NotBlank phù hợp khi field phải có nội dung thực sự.

Tương tự, @Size(max = 120) không bắt buộc chuỗi phải có nội dung. Nếu field vừa bắt buộc vừa có giới hạn độ dài, kết hợp @NotBlank và @Size.

## 5. Kích hoạt validation bằng @Valid

Có constraint trên DTO chưa đủ để Spring tự kiểm tra mọi request. Với request body, hãy đánh dấu tham số bằng @Valid:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return productService.create(request);
    }
}
~~~

Khi có @Valid, Spring kích hoạt Bean Validation trên object sau khi request body được deserialize. Nếu constraint không đạt, Spring MVC thường phát sinh MethodArgumentNotValidException và trả về HTTP 400 theo cơ chế xử lý lỗi mặc định hoặc exception handler của ứng dụng.

Dự án cần có Bean Validation provider. Với Spring Boot, dependency thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Nếu không có provider, annotation có thể vẫn biên dịch nhưng việc kiểm tra runtime sẽ không diễn ra như mong muốn. Hãy xác nhận dependency validation trong cấu hình build và kiểm thử bằng một request vi phạm constraint.

@Valid và @Validated có vai trò liên quan nhưng không hoàn toàn giống nhau. @Valid là annotation chuẩn để kích hoạt cascade validation trên object. @Validated là annotation của Spring, có thể dùng để chọn validation group hoặc kích hoạt method validation trong các trường hợp phù hợp. Với request DTO thông thường, @Valid là cách phổ biến và dễ hiểu.

## 6. So sánh constraint trong OpenAPI với constraint runtime

Một số annotation Bean Validation có thể được springdoc/swagger-core chuyển thành constraint trong OpenAPI Schema. Ví dụ, @Size có thể tạo minLength/maxLength; @DecimalMin có thể tạo minimum hoặc exclusiveMinimum; @NotNull có thể ảnh hưởng required. Mức ánh xạ cụ thể phụ thuộc phiên bản thư viện, namespace validation và cấu hình dự án.

| Ý định | Mô tả OpenAPI | Kiểm tra runtime |
|---|---|---|
| Field phải có | required trong schema | @NotNull hoặc @NotBlank tùy kiểu |
| Chuỗi tối đa 120 ký tự | maxLength: 120 | @Size(max = 120) |
| Giá phải lớn hơn 0 | minimum hoặc exclusiveMinimum | @DecimalMin("0.01") hoặc constraint phù hợp |
| Email có định dạng | format: email | @Email |
| Mã chỉ gồm chữ và số | pattern | @Pattern |
| Ngày phải ở tương lai | format: date hoặc date-time | @Future |
| Danh sách tối đa 10 phần tử | maxItems: 10 | @Size(max = 10) |

Không nên giả định mọi constraint đều được chuyển đổi hoàn hảo. Có constraint chỉ mang ý nghĩa runtime, có constraint chỉ mang ý nghĩa tài liệu, và có constraint cần custom schema để diễn tả chính xác.

Sau khi thêm hoặc sửa annotation, hãy gọi /v3/api-docs và kiểm tra JSON thực tế. Nếu cần hợp đồng chính xác, có thể khai báo rõ @Schema để bổ sung metadata, nhưng vẫn phải giữ constraint runtime tương ứng.

## 7. Required, nullable và giá trị mặc định

Ba khái niệm này thường bị nhầm lẫn:

- **Required:** property phải xuất hiện trong request object.
- **Nullable:** property có được phép nhận giá trị null hay không.
- **Default:** giá trị mặc định được mô tả hoặc áp dụng khi không cung cấp, tùy cơ chế cụ thể.

Ví dụ:

~~~yaml
CreateProductRequest:
  type: object
  required:
    - name
  properties:
    name:
      type: string
      minLength: 1
    description:
      type: string
      maxLength: 500
~~~

Ở đây name bắt buộc phải có. description có thể bị bỏ qua. Việc bỏ qua description khác với gửi description: null; cách mô tả null phụ thuộc phiên bản OpenAPI và schema được sinh.

OpenAPI 3.0 thường dùng nullable: true để cho phép null. OpenAPI 3.1 dựa trên JSON Schema và biểu diễn kiểu null theo cú pháp type phù hợp của JSON Schema. Vì vậy, hãy đọc trường openapi ở đầu tài liệu và kiểm tra schema theo đúng phiên bản.

Trong Java, kiểu primitive như int hoặc boolean không thể nhận null. Nếu cần phân biệt field bị thiếu với giá trị 0 hoặc false, dùng wrapper như Integer hoặc Boolean. Với request tạo mới, điều này giúp validation phân biệt rõ dữ liệu không được gửi và giá trị mặc định của Java.

Không nhầm default trong OpenAPI với việc backend tự gán giá trị. Một default được công bố cho client không nhất thiết làm Jackson hoặc Spring tự gán giá trị đó. Nếu muốn backend có giá trị mặc định, hãy triển khai trong DTO, binder hoặc service và kiểm tra hành vi thực tế.

## 8. Validation cho object lồng nhau

Request body thường có cấu trúc lồng nhau. Ví dụ đơn hàng có thông tin người nhận và danh sách mặt hàng:

~~~java
public class CreateOrderRequest {

    @NotNull
    @Valid
    private ShippingAddress shippingAddress;

    @NotEmpty
    @Valid
    private List<OrderItemRequest> items;

    // Getters và setters.
}

public class ShippingAddress {

    @NotBlank
    private String recipient;

    @NotBlank
    private String street;

    @NotBlank
    private String city;

    // Getters và setters.
}

public class OrderItemRequest {

    @NotBlank
    private String productId;

    @Min(1)
    private Integer quantity;

    // Getters và setters.
}
~~~

@Valid trên property lồng nhau yêu cầu Bean Validation tiếp tục kiểm tra object con. Nếu thiếu @Valid, các constraint bên trong ShippingAddress hoặc OrderItemRequest có thể không được chạy khi kiểm tra object cha.

@Schema có thể mô tả quan hệ object bằng properties hoặc $ref trong components.schemas. Nhưng việc schema hiển thị field lồng nhau không có nghĩa các constraint của object con đã được kích hoạt ở runtime. Cần xác minh cả cấu trúc OpenAPI và hành vi validation.

## 9. Quy tắc liên trường và quy tắc nghiệp vụ

Nhiều điều kiện không thể biểu diễn đầy đủ bằng constraint trên một field riêng lẻ. Ví dụ:

- createdFrom phải nhỏ hơn hoặc bằng createdTo.
- discount không được lớn hơn subtotal.
- paymentMethod = BANK_TRANSFER thì bankAccount phải có giá trị.
- Ngày giao hàng phải sau ngày đặt hàng.
- Người dùng chỉ được đặt số lượng tối đa theo tồn kho hiện tại.

Có thể dùng class-level constraint hoặc custom validator cho quy tắc liên trường. Ví dụ đơn giản với class-level validation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator đọc cả hai field và quyết định object có hợp lệ hay không. Có thể bổ sung @Schema(description = "...") để giải thích quy tắc trong hợp đồng OpenAPI, vì OpenAPI Schema không tự suy ra được logic tùy biến của Java validator.

Quy tắc phụ thuộc trạng thái hệ thống nên đặt ở tầng nghiệp vụ. Ví dụ, tồn kho thay đổi theo thời gian nên không thể bảo đảm chỉ bằng một schema tĩnh. Backend cần kiểm tra tồn kho tại thời điểm xử lý và trả về response lỗi phù hợp nếu không đáp ứng.

## 10. Deserialize lỗi xảy ra trước Bean Validation

Không phải mọi request sai đều tạo ra lỗi Bean Validation. Jackson phải chuyển JSON thành Java object trước. Nếu không thể deserialize, validation có thể chưa được gọi.

Ví dụ JSON:

~~~json
{
  "name": "Wireless Mouse",
  "price": "not-a-number"
}
~~~

Nếu price là BigDecimal, Jackson không thể chuyển chuỗi not-a-number thành số. Spring MVC thường trả lỗi HTTP 400 thông qua HttpMessageNotReadableException.

Một số lỗi deserialize phổ biến:

| Dữ liệu gửi | Vấn đề |
|---|---|
| JSON sai cú pháp | Jackson không phân tích được document |
| price là chuỗi không phải số | Không chuyển được sang BigDecimal |
| quantity là object thay vì số nguyên | Kiểu JSON không khớp kiểu Java |
| ngày không đúng định dạng | Không chuyển được sang LocalDate/Instant |
| enum không tồn tại | Không chuyển được chuỗi sang enum |
| thiếu field primitive | Java có thể nhận giá trị mặc định như 0 hoặc false, tùy cấu hình |

Đây là lý do cần phân biệt lỗi deserialize với lỗi validation. Hai loại lỗi đều có thể trả HTTP 400 nhưng nguyên nhân và thông điệp khác nhau.

Nếu cấu hình Jackson cho phép bỏ qua property không biết, field lạ có thể bị bỏ qua thay vì làm request thất bại. Nếu cấu hình từ chối property không biết, cùng request đó có thể bị từ chối. Hành vi phụ thuộc cấu hình ObjectMapper và phiên bản Spring Boot.

## 11. Chuẩn hóa phản hồi lỗi validation

Client cần biết vì sao request bị từ chối. Hợp đồng OpenAPI nên mô tả các response lỗi phổ biến như 400, 401, 403 hoặc 409 tùy API.

Ví dụ error response:

~~~java
@Schema(name = "ValidationError")
public class ValidationErrorResponse {

    @Schema(example = "VALIDATION_FAILED")
    private String code;

    @Schema(example = "Request không hợp lệ")
    private String message;

    private List<FieldViolation> violations;

    // Getters và setters.
}

public class FieldViolation {

    @Schema(example = "name")
    private String field;

    @Schema(example = "must not be blank")
    private String message;

    // Getters và setters.
}
~~~

Có thể mô tả response trong controller:

~~~java
@Operation(summary = "Tạo sản phẩm")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Tạo sản phẩm thành công"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "JSON sai định dạng hoặc dữ liệu không đạt validation",
        content = @Content(
            schema = @Schema(implementation = ValidationErrorResponse.class)
        )
    )
})
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

@Schema và @ApiResponse mô tả cấu trúc lỗi. Chúng không tự chuyển MethodArgumentNotValidException thành ValidationErrorResponse. Muốn trả về định dạng nhất quán, ứng dụng cần xử lý exception, thường qua @RestControllerAdvice.

Ví dụ khung xử lý:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationErrorResponse> handleValidation(
        MethodArgumentNotValidException exception
    ) {
        // Chuyển field errors thành danh sách violations.
        ValidationErrorResponse body = buildValidationError(exception);

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ValidationErrorResponse> handleUnreadable(
        HttpMessageNotReadableException exception
    ) {
        // Trả thông báo JSON hoặc kiểu dữ liệu không đọc được.
        ValidationErrorResponse body = buildUnreadableError(exception);

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Các hàm buildValidationError và buildUnreadableError là phần triển khai của ứng dụng. Hãy tránh trả stack trace hoặc thông tin nội bộ cho client. Nội dung lỗi nên đủ rõ để sửa request nhưng không làm lộ chi tiết nhạy cảm.

## 12. Validation groups và các luồng tạo/cập nhật

Một DTO đôi khi được dùng cho nhiều operation nhưng mỗi operation có yêu cầu khác nhau. Ví dụ, khi tạo sản phẩm thì name bắt buộc; khi cập nhật một phần thì name có thể được bỏ qua.

Có thể dùng validation group:

~~~java
public interface Create {}
public interface Update {}

public class ProductRequest {

    @NotBlank(groups = Create.class)
    @Size(max = 120, groups = {Create.class, Update.class})
    private String name;

    @NotNull(groups = Create.class)
    @DecimalMin(value = "0.01", groups = {Create.class, Update.class})
    private BigDecimal price;

    // Getters và setters.
}
~~~

Controller có thể chọn group qua @Validated:

~~~java
@PostMapping
public ProductResponse create(
    @Validated(Create.class) @RequestBody ProductRequest request
) {
    return productService.create(request);
}

@PutMapping("/{id}")
public ProductResponse update(
    @PathVariable String id,
    @Validated(Update.class) @RequestBody ProductRequest request
) {
    return productService.update(id, request);
}
~~~

Đây là ví dụ minh họa về validation groups. Cần kiểm tra cách cấu hình Spring MVC, nhóm Default và các group sequence trong ứng dụng thực tế. Đặc tả OpenAPI thường cần mô tả request schema phù hợp cho từng operation; dùng chung một DTO cho nhiều luồng có thể làm schema khó thể hiện chính xác required của từng trường. Khi hợp đồng khác nhau đáng kể, DTO riêng cho Create và Update thường rõ ràng hơn.

## 13. Những gì OpenAPI không thể bảo đảm

Schema là một bản mô tả có cấu trúc, không phải toàn bộ chương trình kiểm tra request. Một số quy tắc không thể biểu diễn hoặc không thể thực thi thống nhất ở mọi client:

- Quy tắc phụ thuộc database, tồn kho, trạng thái giao dịch hoặc dữ liệu người dùng hiện tại.
- Quyền truy cập và quyền sở hữu tài nguyên.
- Điều kiện liên trường phức tạp hoặc logic tùy biến.
- Quy tắc phụ thuộc thời điểm, múi giờ hoặc cấu hình vận hành.
- Constraint do custom validator thực thi nhưng không có biểu diễn JSON Schema tương đương.
- Giới hạn kỹ thuật như rate limit, quota hoặc kích thước request do gateway áp dụng.

Ví dụ schema có thể mô tả quantity là integer lớn hơn 0. Nhưng schema không thể khẳng định người mua hiện còn đủ hạn mức để đặt số lượng đó. Backend phải kiểm tra tại thời điểm xử lý.

Cũng không nên xem format như email, date hoặc uuid là bằng chứng mọi client sẽ xác thực giống nhau. Một số công cụ chỉ dùng format để gợi ý hoặc hiển thị; backend vẫn phải kiểm tra dữ liệu theo quy tắc ứng dụng.

## 14. Kiểm tra tính nhất quán giữa schema và runtime

Sau khi thêm annotation, hãy kiểm tra hai phía.

**Kiểm tra OpenAPI JSON:**

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Tìm request body của operation:

~~~bash
jq '.paths["/api/products"].post.requestBody' openapi.json
~~~

Tìm schema:

~~~bash
jq '.components.schemas.CreateProductRequest' openapi.json
~~~

Đối chiếu:

- Request body có đúng media type không?
- requestBody.required có đúng không?
- Schema có đúng property và kiểu dữ liệu không?
- required có liệt kê các field cần thiết không?
- minLength, maxLength, minimum, enum, format có đúng không?
- Mô tả và example có khớp request thật không?

**Kiểm tra runtime:** gửi lần lượt request hợp lệ và request vi phạm từng constraint. Ví dụ:

~~~powershell
# Request hợp lệ
curl.exe -i -X POST http://localhost:8080/api/products -H "Content-Type: application/json" -d '{"name":"Wireless Mouse","price":450000}'

# Tên rỗng và giá âm
curl.exe -i -X POST http://localhost:8080/api/products -H "Content-Type: application/json" -d '{"name":"   ","price":-10}'
~~~

Kiểm tra status code, response body và log server. Nếu OpenAPI mô tả maxLength 120 nhưng backend vẫn nhận chuỗi dài hơn, có thể thiếu @Size hoặc @Valid. Nếu backend từ chối một request mà schema cho phép, hãy xem đó là constraint runtime bổ sung và cân nhắc mô tả trong description hoặc schema nếu có biểu diễn phù hợp.

## 15. Những sai lệch thường gặp

| Biểu hiện | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI đánh dấu field bắt buộc nhưng backend vẫn nhận thiếu | OpenAPI required chỉ là mô tả; kiểm tra @NotNull/@NotBlank, @Valid và logic mặc định của DTO |
| Backend từ chối request nhưng schema không thể hiện constraint | Thiếu metadata OpenAPI hoặc constraint là logic tùy biến |
| @Size có trong DTO nhưng request dài vẫn được nhận | Chưa kích hoạt validation, thiếu provider hoặc controller thiếu @Valid |
| JSON sai kiểu trả 400 nhưng không có field error | Jackson deserialize thất bại trước Bean Validation |
| Field null được chấp nhận dù không mong muốn | Thiếu @NotNull hoặc schema required/nullable không đúng |
| Field bị thiếu biến thành 0 hoặc false | DTO dùng primitive; cân nhắc wrapper và validation |
| Schema có example nhưng backend không nhận giá trị | Example chỉ minh họa, không tự cấu hình binding hoặc business logic |
| Validation object con không chạy | Thiếu @Valid trên property lồng nhau |
| Custom validator không xuất hiện trong OpenAPI | Cần mô tả bổ sung bằng @Schema hoặc description |
| Create và Update có required khác nhau nhưng dùng chung schema | Cân nhắc DTO riêng hoặc schema theo operation |

## 16. Checklist cho request body

- [ ] Đã khai báo đúng media type và schema của request body.
- [ ] Đã phân biệt requestBody.required với schema.required.
- [ ] Các field có type, format, enum và example chính xác.
- [ ] Các giới hạn có thể công bố được mô tả bằng Schema.
- [ ] Constraint runtime được khai báo bằng Bean Validation phù hợp.
- [ ] Controller kích hoạt validation bằng @Valid hoặc cơ chế phù hợp.
- [ ] Object lồng nhau có @Valid ở đúng vị trí.
- [ ] Quy tắc liên trường và nghiệp vụ được kiểm tra ở tầng thích hợp.
- [ ] Đã phân biệt lỗi deserialize với lỗi Bean Validation.
- [ ] Response lỗi được mô tả trong OpenAPI và có implementation tương ứng.
- [ ] Đã kiểm tra JSON tại /v3/api-docs.
- [ ] Đã thử request hợp lệ, request sai kiểu và request vi phạm constraint.

## 17. Nguồn tra cứu

- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – @RequestBody và message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)

OpenAPI Schema cho client biết cấu trúc request và các constraint được công bố. Spring/Jackson/Bean Validation và tầng nghiệp vụ chịu trách nhiệm xử lý, kiểm tra và quyết định request thực tế. Khi sửa DTO hoặc annotation, hãy xác minh cả JSON OpenAPI lẫn hành vi runtime để hai phần tiếp tục mô tả cùng một hợp đồng.
