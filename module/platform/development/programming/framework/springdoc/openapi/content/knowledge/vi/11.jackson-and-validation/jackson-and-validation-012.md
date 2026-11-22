# Vì sao annotation tài liệu không tự thực thi Bean Validation

Khi mô tả một request trong OpenAPI, ta có thể thấy các ràng buộc như trường bắt buộc, độ dài tối thiểu, giá trị số lớn nhất hoặc tập giá trị enum. springdoc-openapi có thể đọc annotation trên DTO và dùng chúng để tạo schema cho Swagger UI. Tuy nhiên, **schema chỉ mô tả hợp đồng**. Nó không tự chạy bộ kiểm tra dữ liệu bên trong ứng dụng Spring Boot.

Để server thật sự từ chối dữ liệu không hợp lệ, ứng dụng cần có Bean Validation provider, constraint phù hợp và điểm kích hoạt validation trong luồng xử lý Spring. Ví dụ, DTO có @NotBlank nhưng controller không kích hoạt validation thì không thể kết luận request sẽ bị từ chối chỉ vì OpenAPI hiển thị trường đó là bắt buộc.

Bài này phân biệt ba việc thường bị nhầm lẫn: khai báo ràng buộc trong Bean Validation, biểu diễn ràng buộc trong OpenAPI và thực thi kiểm tra khi request đi vào Spring MVC. Từ đó, ta biết cách cấu hình, kiểm thử và đồng bộ tài liệu với hành vi runtime.

## 1. Ba lớp trách nhiệm khác nhau

Một request có thể đi qua ba lớp xử lý:

1. **Bean Validation metadata**: annotation như @NotNull, @NotBlank, @Size, @Min và @Pattern mô tả các điều kiện mà dữ liệu phải thỏa mãn.
2. **OpenAPI schema**: springdoc đọc một phần metadata và biểu diễn thành required, minLength, maximum, pattern hoặc enum để người tích hợp hiểu hợp đồng.
3. **Runtime validation**: Spring gọi Bean Validation provider tại điểm được kích hoạt; provider thực thi constraint và trả về danh sách lỗi nếu dữ liệu không hợp lệ.

~~~mermaid
flowchart TD
    A["DTO và Bean Validation annotations"] --> B["springdoc đọc metadata"]
    B --> C["OpenAPI Schema"]
    C --> D["Swagger UI / tài liệu client"]
    A --> E["Spring MVC binding"]
    E --> F{"Có kích hoạt validation?"}
    F -->|Có| G["Bean Validation provider"]
    F -->|Không| H["Bỏ qua bước kiểm tra constraint"]
    G --> I{"Dữ liệu hợp lệ?"}
    I -->|Có| J["Controller xử lý request"]
    I -->|Không| K["Validation error"]
    H --> J
~~~

Sơ đồ cho thấy springdoc và runtime validation đọc cùng metadata nhưng thực hiện hai nhiệm vụ riêng. Việc tạo được schema không chứng minh provider đã được cài đặt, controller đã kích hoạt validation hoặc exception đã được xử lý đúng.

| Thành phần | Trả lời câu hỏi nào? | Ví dụ |
|---|---|---|
| Bean Validation annotation | Dữ liệu phải thỏa điều kiện gì? | @NotBlank, @Size(max = 100) |
| OpenAPI Schema | Client cần biết giới hạn nào? | type: string, maxLength: 100 |
| Runtime validation | Server có từ chối dữ liệu sai không? | @Valid và Validator |
| Exception handling | Server phản hồi lỗi validation ra sao? | HTTP 400 và error body |

## 2. Bean Validation annotation chỉ khai báo constraint

Bean Validation cung cấp API chuẩn để khai báo các điều kiện trên property, tham số, giá trị trả về hoặc toàn bộ object. Ví dụ DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateUserRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotNull
    @Email
    String email,

    @NotBlank
    @Size(min = 12, max = 128)
    String password
) {}
~~~

Các annotation trên gắn metadata constraint với thành phần dữ liệu:

- @NotNull yêu cầu giá trị không null.
- @NotBlank yêu cầu chuỗi khác null, có ít nhất một ký tự không phải khoảng trắng.
- @Size giới hạn kích thước chuỗi, collection, map hoặc mảng.
- @Email kiểm tra giá trị có dạng địa chỉ email theo định nghĩa của provider.

Đến đây, ứng dụng mới có khai báo điều kiện. Constraint không tự chạy mỗi khi object được tạo hoặc deserialize. Một thành phần gọi Bean Validation API, thường là Spring MVC hoặc method validation, phải yêu cầu provider kiểm tra object.

### Constraint không phải annotation tài liệu

Các annotation trên thuộc package Bean Validation, chẳng hạn:

- Spring Boot 3 / Jakarta: **jakarta.validation.constraints.NotBlank**.
- Spring Boot 2 / Java EE: **javax.validation.constraints.NotBlank**.

Annotation OpenAPI như @Schema và @Parameter thuộc swagger-annotations. Chúng mô tả tài liệu. Không dùng @Schema để thay thế constraint runtime, và cũng không coi việc có @NotBlank là bằng chứng Swagger UI đã tự kiểm tra request.

## 3. Cài Bean Validation provider

Ứng dụng cần có implementation của Bean Validation API. Với Spring Boot, dependency thường dùng là **spring-boot-starter-validation**. Starter này đưa API và provider tương ứng vào classpath.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Nếu dùng Spring Boot dependency management, thông thường không cần tự chỉ định version cho starter. Dùng phiên bản phù hợp với dòng Spring Boot của dự án.

Trong Spring Boot 3, các import Bean Validation thuộc namespace **jakarta.validation**. Dự án Spring Boot 2 thường dùng **javax.validation**. Không trộn hai namespace trong cùng một cấu hình nếu các dependency không tương thích.

Nếu chỉ có annotation API mà không có provider, metadata có thể vẫn xuất hiện trong class file và được công cụ tài liệu đọc, nhưng ứng dụng không có implementation tương ứng để thực thi constraint. Vì vậy, khi kiểm tra validation runtime, hãy xác minh dependency/provider thực sự có mặt.

## 4. Kích hoạt validation cho request body bằng @Valid

Trong Spring MVC, cách phổ biến để kích hoạt validation cho DTO JSON là đặt **@Valid** trên tham số **@RequestBody**:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;

@RestController
public class UserController {

    @PostMapping("/api/users")
    @ResponseStatus(HttpStatus.CREATED)
    public UserResponse create(
        @Valid @RequestBody CreateUserRequest request
    ) {
        // Chỉ xử lý nghiệp vụ sau khi binding và validation thành công
        return userService.create(request);
    }
}
~~~

Luồng xử lý thông thường:

1. Spring nhận HTTP request.
2. HttpMessageConverter đọc JSON và tạo CreateUserRequest.
3. Do tham số có @Valid, Spring yêu cầu validator kiểm tra object.
4. Nếu constraint vi phạm, quá trình gọi controller bị dừng và Spring tạo lỗi validation.
5. Nếu hợp lệ, controller mới được gọi để xử lý nghiệp vụ.

Với request body có lỗi binding hoặc validation, Spring MVC thường phát sinh **MethodArgumentNotValidException** trong luồng validation đối số. Ứng dụng có thể xử lý exception này để trả error response thống nhất.

### Bỏ @Valid có thể làm constraint không được thực thi

~~~java
@PostMapping("/api/users")
public UserResponse create(
    @RequestBody CreateUserRequest request
) {
    return userService.create(request);
}
~~~

Trong ví dụ này, @RequestBody vẫn đọc JSON thành DTO, nhưng không yêu cầu Spring chạy validation trên DTO theo cơ chế argument validation thông thường. Một chuỗi rỗng có thể đi tới controller nếu không có bước kiểm tra khác.

Việc springdoc vẫn đọc được @NotBlank và tạo schema có minLength hoặc required không làm thay đổi luồng runtime này.

## 5. @Valid và validation lồng nhau

@Valid còn dùng để yêu cầu kiểm tra đệ quy các object lồng bên trong. Xét request có địa chỉ:

~~~java
public record AddressRequest(
    @NotBlank
    String city,

    @NotBlank
    @Size(max = 120)
    String street
) {}

public record CreateCustomerRequest(
    @NotBlank
    String name,

    @Valid
    @NotNull
    AddressRequest address
) {}
~~~

@NotNull trên address yêu cầu object địa chỉ không null. @Valid trên cùng property yêu cầu validator tiếp tục kiểm tra các constraint bên trong AddressRequest. Nếu bỏ @Valid, @NotNull vẫn có thể kiểm tra address nhưng city và street bên trong sẽ không tự động được cascade validate qua property đó.

Với danh sách object:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    List<@NotNull @Valid OrderLineRequest> lines
) {}

public record OrderLineRequest(
    @NotBlank String productCode,
    @Min(1) @Max(100) int quantity
) {}
~~~

Container element constraints cho phép đặt constraint trực tiếp lên từng phần tử. @Valid yêu cầu cascade vào object của từng phần tử; @NotNull yêu cầu phần tử không null; @Min và @Max giới hạn quantity. Hãy kiểm tra phiên bản Bean Validation provider và cách binding collection của ứng dụng khi dùng container element constraints.

## 6. Validation cho query, path và header parameter

Các tham số HTTP đơn giản như page, size, ID hoặc header cũng có thể có constraint:

~~~java
@GetMapping("/api/books")
public List<BookResponse> list(
    @RequestParam
    @Min(0)
    int page,

    @RequestParam
    @Min(1)
    @Max(100)
    int size
) {
    return bookService.list(page, size);
}
~~~

Để constraint trên method parameter được thực thi, ứng dụng cần cơ chế **method validation** phù hợp với phiên bản Spring đang sử dụng và có Bean Validation provider. Cách kích hoạt phụ thuộc phiên bản:

- Với các phiên bản Spring trước hỗ trợ method validation tích hợp trong Spring MVC, thường dùng method validation qua proxy và đặt @Validated ở class hoặc bean phù hợp.
- Từ Spring Framework 6.1, Spring MVC có hỗ trợ method validation tích hợp cho controller. Khi dùng cơ chế tích hợp này, cần lưu ý không gắn @Validated ở cấp controller nếu điều đó khiến method được xử lý qua AOP method validation thay cho cơ chế tích hợp.

Không nên sao chép cấu hình @Validated từ dự án khác mà không xét phiên bản Spring. Hãy xác định cơ chế method validation đang dùng, sau đó kiểm tra lỗi thực tế với giá trị page hoặc size ngoài giới hạn.

### Phân biệt @Valid và @Validated

| Annotation | Vai trò thường gặp |
|---|---|
| @Valid | Kích hoạt cascade validation theo Jakarta Bean Validation; không chọn validation group |
| @Validated | Annotation của Spring, có thể chọn validation group và tham gia cơ chế method validation |

@Valid không thay thế @Min hoặc @Max. Nó yêu cầu validator đi vào object; constraint cụ thể vẫn phải được khai báo trên property hoặc parameter. @Validated cũng không tự tạo ra giới hạn dữ liệu nếu không có constraint tương ứng.

## 7. Validation groups và schema OpenAPI

Một DTO đôi khi có quy tắc khác nhau khi tạo mới và cập nhật. Bean Validation hỗ trợ **validation groups**:

~~~java
public interface Create {}
public interface Update {}

public record SaveBookRequest(
    @NotBlank(groups = {Create.class, Update.class})
    String title,

    @NotNull(groups = Create.class)
    UUID catalogId
) {}
~~~

Controller có thể chọn group tại điểm validation:

~~~java
@PostMapping("/api/books")
public BookResponse create(
    @Validated(Create.class) @RequestBody SaveBookRequest request
) {
    return bookService.create(request);
}

@PutMapping("/api/books/{bookId}")
public BookResponse update(
    @PathVariable UUID bookId,
    @Validated(Update.class) @RequestBody SaveBookRequest request
) {
    return bookService.update(bookId, request);
}
~~~

Validation group quyết định constraint nào được thực thi ở từng operation. OpenAPI schema thông thường mô tả một cấu trúc dữ liệu, không tự thể hiện toàn bộ quy tắc group được chọn theo runtime context. Nếu một property bắt buộc khi tạo mới nhưng tùy chọn khi cập nhật, một schema dùng chung có thể không truyền đạt chính xác cả hai hợp đồng.

Các cách xử lý:

- Tách CreateBookRequest và UpdateBookRequest nếu hai hợp đồng có ý nghĩa khác nhau.
- Dùng schema riêng cho từng operation khi cần mô tả khác biệt rõ ràng.
- Bổ sung mô tả và ví dụ để giải thích điều kiện theo ngữ cảnh.
- Kiểm tra schema do springdoc sinh ra vì cách xử lý group phụ thuộc phiên bản và tích hợp; không giả định mọi group sẽ được chuyển thành schema riêng tự động.

Với API công khai, DTO riêng cho create và update thường dễ hiểu hơn việc yêu cầu client suy ra group validation từ cùng một schema.

## 8. Bean Validation và những gì OpenAPI có thể biểu diễn

springdoc có thể đọc một số constraint và chuyển chúng thành các keyword của Schema Object. Khả năng ánh xạ cụ thể phụ thuộc phiên bản springdoc, swagger-core, Jakarta/Javax Validation và cấu hình.

| Bean Validation | Schema OpenAPI thường có thể mô tả | Giới hạn cần hiểu |
|---|---|---|
| @NotNull | required hoặc ràng buộc không null theo phiên bản OpenAPI | required nói property phải xuất hiện; nullable là khái niệm riêng |
| @NotEmpty | required và giới hạn rỗng phù hợp với kiểu dữ liệu | Không giống @NotBlank với chuỗi chỉ chứa khoảng trắng |
| @NotBlank | required và/hoặc minLength trong một số ánh xạ | minLength không thể loại mọi chuỗi chỉ có khoảng trắng |
| @Size(min, max) trên String | minLength, maxLength | Ý nghĩa đếm ký tự có thể khác chi tiết triển khai |
| @Size(min, max) trên Collection/Array | minItems, maxItems | Cần schema items đúng kiểu |
| @Size(min, max) trên Map | minProperties, maxProperties | Không mô tả được mọi constraint tùy biến trên key/value |
| @Min / @Max | minimum / maximum | Kiểm tra kiểu số và biên inclusive |
| @DecimalMin / @DecimalMax | minimum / maximum hoặc exclusive bound | Thuộc tính inclusive cần được giữ đúng |
| @Positive / @PositiveOrZero | minimum hoặc exclusiveMinimum | Phụ thuộc phiên bản và kiểu số |
| @Pattern | pattern | Regex của Java và JSON Schema không hoàn toàn đồng nhất |
| @Email | format email hoặc mô tả tương ứng | Quy tắc của provider có thể rộng hơn format email |
| @Past / @Future | Một số metadata thời gian nếu được hỗ trợ | Tính thời điểm hiện tại là điều kiện động, không phải giới hạn tĩnh đơn giản |

Các ánh xạ trong bảng là khả năng biểu diễn, không phải cam kết rằng mọi phiên bản sẽ sinh chính xác cùng một schema. Luôn mở /v3/api-docs để kiểm tra kết quả của dự án.

### required không đồng nghĩa với nullable

Trong OpenAPI, **required** cho biết property có phải xuất hiện trong object hay không. **Nullable** hoặc cách biểu diễn null cho biết property có thể nhận giá trị null hay không; cách biểu diễn phụ thuộc phiên bản OpenAPI.

Ví dụ:

- Một property có thể bắt buộc xuất hiện và không được null.
- Một property có thể không bắt buộc xuất hiện nhưng nếu có thì không được null.
- Một property có thể bắt buộc xuất hiện nhưng cho phép null, nếu hợp đồng cho phép điều đó.

@NotNull kiểm tra giá trị sau khi binding không null. Nếu JSON bỏ qua property và Jackson để giá trị Java thành null, constraint thường thất bại khi validation chạy. Nhưng không nên chỉ nhìn keyword required trong OpenAPI rồi kết luận server chắc chắn đã kiểm tra; phải kiểm thử runtime.

### @NotBlank không giống minLength

@NotBlank loại chuỗi null, rỗng và chuỗi chỉ có khoảng trắng. Schema string với minLength: 1 vẫn có thể chấp nhận chuỗi chứa một dấu cách. Vì vậy, ánh xạ minLength là mô tả gần đúng, không thay thế semantics của provider.

Tương tự, @Email và @Pattern có thể có quy tắc kiểm tra cụ thể hơn cách client validator diễn giải format hoặc regex. Nếu điều kiện quan trọng, hãy ghi rõ trong description, dùng pattern/schema phù hợp nếu có thể và kiểm thử server.

## 9. @Schema không gọi Validator

Annotation **@Schema** thuộc OpenAPI. Nó có thể bổ sung type, format, description, example, allowableValues, minimum, maximum, minLength, maxLength, pattern và requiredMode.

~~~java
public record CreateProductRequest(
    @Schema(
        description = "Tên sản phẩm, không được để trống",
        example = "Mechanical Keyboard",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String name
) {}
~~~

Schema trên chỉ tạo metadata cho tài liệu. Nếu muốn runtime từ chối tên rỗng, cần constraint Bean Validation và kích hoạt validation:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(
        description = "Tên sản phẩm, không được để trống",
        example = "Mechanical Keyboard",
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String name
) {}

@PostMapping("/api/products")
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Trong ví dụ, @NotBlank và @Size là constraint runtime; @Schema bổ sung cách trình bày hợp đồng; @Valid yêu cầu Spring kích hoạt kiểm tra DTO. Ba phần có liên quan nhưng không thể thay thế nhau.

Nếu chỉ có @Schema(minLength = 1), tài liệu có thể hiển thị minLength nhưng Bean Validation không có constraint tương ứng để server thực thi. Ngược lại, nếu chỉ có @NotBlank, server có thể kiểm tra đúng nhưng OpenAPI chưa chắc diễn đạt đầy đủ điều kiện không có khoảng trắng.

## 10. Validation lỗi được chuyển thành HTTP response như thế nào?

Khi validation thất bại, Spring MVC không tiếp tục gọi logic controller theo luồng thông thường. Ứng dụng cần quyết định cách trả lỗi cho client.

Có thể dùng @RestControllerAdvice để chuyển lỗi thành cấu trúc thống nhất:

~~~java
public record FieldViolation(
    String field,
    String message
) {}

public record ApiValidationError(
    String code,
    List<FieldViolation> violations
) {}

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiValidationError handleValidation(
        MethodArgumentNotValidException exception
    ) {
        List<FieldViolation> violations =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldViolation(
                    error.getField(),
                    error.getDefaultMessage()
                ))
                .toList();

        return new ApiValidationError(
            "VALIDATION_FAILED",
            violations
        );
    }
}
~~~

Đây là ví dụ đơn giản; trong ứng dụng thực tế cần xử lý cả lỗi binding, lỗi method validation và lỗi nghiệp vụ theo cấu trúc phù hợp. Không nên trả stack trace hoặc dữ liệu nội bộ của validator cho client.

springdoc không tự biết mọi error response do @RestControllerAdvice tạo ra trong tất cả tình huống. Hãy mô tả response lỗi bằng @ApiResponse/@ApiResponses hoặc cơ chế tùy biến dùng chung:

~~~java
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Tạo sản phẩm thành công"
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Dữ liệu request không hợp lệ",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ApiValidationError.class)
        )
    )
})
@PostMapping("/api/products")
public ProductResponse create(
    @Valid @RequestBody CreateProductRequest request
) {
    return productService.create(request);
}
~~~

Mô tả 400 trong OpenAPI giúp client biết hình dạng lỗi. Nó không kích hoạt validation và cũng không làm controller trả 400 nếu runtime chưa có cơ chế phát sinh lỗi tương ứng.

## 11. Kiểm thử để chứng minh validation thật sự chạy

Một schema có minLength hoặc required không đủ để chứng minh server từ chối request sai. Cần kiểm thử endpoint bằng request thực tế hoặc MockMvc.

Ví dụ MockMvc:

~~~java
@WebMvcTest(ProductController.class)
@Import(ApiExceptionHandler.class)
class ProductControllerValidationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void rejectsBlankName() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name": "   "}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_FAILED"));

        verifyNoInteractions(productService);
    }
}
~~~

Test trên kiểm tra hành vi runtime:

- Request body được đọc thành DTO.
- @Valid kích hoạt Bean Validation.
- @NotBlank phát hiện tên chỉ chứa khoảng trắng.
- Server trả HTTP 400 qua exception handler.
- Service không được gọi khi dữ liệu không hợp lệ.

Nên có cả test trường hợp hợp lệ để xác nhận request vẫn đi tới service và trả kết quả mong muốn. Với query/path parameter, hãy kiểm thử riêng method validation vì cơ chế kích hoạt có thể khác request body.

### Kiểm tra tài liệu OpenAPI độc lập

Có thể dùng integration test hoặc lấy JSON tại /v3/api-docs để kiểm tra:

- Schema có description, required, minLength, maxLength hoặc giới hạn số như mong muốn không?
- Request body có trỏ tới đúng component schema không?
- Response 400 có được mô tả với ApiValidationError không?
- Tên property có khớp JSON sau Jackson serialization không?

Hai nhóm test chứng minh hai kết quả khác nhau:

| Kiểm tra | Điều được chứng minh |
|---|---|
| Test /v3/api-docs | Tài liệu OpenAPI được sinh với schema mong muốn |
| MockMvc gửi dữ liệu sai | Server thực thi validation và trả lỗi |
| MockMvc gửi dữ liệu đúng | Request hợp lệ đi tiếp qua controller |

Không dùng kết quả của một nhóm để suy ra nhóm còn lại.

## 12. Constraint tùy biến và giới hạn biểu diễn trong OpenAPI

Bean Validation cho phép tạo constraint riêng. Ví dụ mã khách hàng phải tuân theo quy tắc nghiệp vụ:

~~~java
@Documented
@Constraint(validatedBy = CustomerCodeValidator.class)
@Target({FIELD, METHOD, PARAMETER, ANNOTATION_TYPE, TYPE_USE, RECORD_COMPONENT})
@Retention(RUNTIME)
public @interface ValidCustomerCode {
    String message() default "Mã khách hàng không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class CustomerCodeValidator
        implements ConstraintValidator<ValidCustomerCode, String> {

    private static final Pattern CODE =
        Pattern.compile("CUS-[A-Z0-9]{6}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || CODE.matcher(value).matches();
    }
}
~~~

DTO:

~~~java
public record CreateCustomerRequest(
    @ValidCustomerCode
    @Schema(
        description = "Mã khách hàng theo định dạng CUS- và sáu ký tự chữ/số",
        example = "CUS-A1B2C3",
        pattern = "^CUS-[A-Z0-9]{6}$"
    )
    String customerCode
) {}
~~~

Provider thực thi ValidCustomerCode bằng CustomerCodeValidator. springdoc không thể tự suy ra quy tắc regex từ logic Java tùy biến trong validator. @Schema(pattern = ...) bổ sung mô tả gần tương ứng cho tài liệu, nhưng hai định nghĩa phải được giữ đồng bộ bằng review và test.

Validator trên chủ động coi null là hợp lệ. Nếu customerCode cũng bắt buộc phải có giá trị, hãy kết hợp thêm @NotNull hoặc @NotBlank; constraint định dạng và constraint bắt buộc là hai điều kiện riêng.

Với constraint liên trường, chẳng hạn ngày kết thúc phải sau ngày bắt đầu, schema thông thường không diễn đạt đầy đủ logic so sánh giữa hai property. Có thể dùng class-level constraint để thực thi và mô tả quy tắc trong description hoặc tài liệu operation.

## 13. Jackson, binding và validation là các bước khác nhau

Trước khi Bean Validation kiểm tra object, Spring phải tạo object từ dữ liệu HTTP. Jackson hoặc HttpMessageConverter chịu trách nhiệm đọc JSON; Bean Validation kiểm tra object sau khi binding.

Ví dụ:

- JSON sai cú pháp hoặc sai kiểu có thể thất bại trong bước deserialize trước khi constraint chạy.
- JSON hợp lệ về cú pháp nhưng name rỗng có thể deserialize thành DTO, sau đó @NotBlank phát hiện lỗi.
- Property không được gửi có thể nhận giá trị null hoặc default tùy kiểu Java, constructor, Jackson và cấu hình.
- @JsonProperty, @JsonIgnore hoặc custom deserializer có thể làm thay đổi dữ liệu được đưa tới validator.

Vì vậy, khi một request bị từ chối, cần phân biệt lỗi parse/binding với lỗi Bean Validation. Khi một request vượt qua validation, điều đó cũng không chứng minh nó thỏa mọi quy tắc nghiệp vụ; các kiểm tra domain và database vẫn có thể cần thiết.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Swagger UI hiển thị required nhưng server vẫn nhận giá trị rỗng | Chỉ có schema hoặc constraint chưa được kích hoạt | Thêm provider, constraint và @Valid/@Validated phù hợp |
| @NotBlank không chặn chuỗi chỉ có khoảng trắng | Controller không kích hoạt validation hoặc provider thiếu | Kiểm tra dependency và test request runtime |
| @Valid trên request body nhưng lỗi không theo định dạng chung | Chưa có exception handler tương ứng | Xử lý MethodArgumentNotValidException và các lỗi binding |
| DTO lồng nhau không bị kiểm tra | Thiếu @Valid trên property/container element | Bổ sung cascade validation |
| Query @Min không chạy | Chưa cấu hình method validation đúng phiên bản | Kiểm tra Spring version và cơ chế method validation |
| Schema hiển thị minLength nhưng whitespace vẫn có thể được gửi | minLength không tương đương @NotBlank | Ghi rõ semantics, dùng pattern nếu phù hợp và kiểm thử server |
| Constraint custom không xuất hiện trong schema | springdoc không phân tích logic validator tùy biến | Bổ sung @Schema hoặc OpenApiCustomizer |
| Create và Update dùng chung schema nhưng required khác nhau | Validation groups không được thể hiện như hai hợp đồng riêng | Tách DTO/schema theo operation hoặc mô tả rõ |
| Response lỗi runtime không có trong OpenAPI | Chưa khai báo @ApiResponse hoặc customizer | Bổ sung response lỗi cho operation hoặc toàn tài liệu |
| JSON sai kiểu trả lỗi parse thay vì lỗi constraint | Deserialize thất bại trước Bean Validation | Kiểm tra HttpMessageConverter/Jackson và phân loại exception |

## 15. Quy trình đồng bộ Bean Validation và OpenAPI

Khi thêm hoặc sửa constraint, thực hiện lần lượt:

1. **Xác định quy tắc nghiệp vụ:** trường nào bắt buộc, giới hạn nào áp dụng, có phụ thuộc operation hoặc group không?
2. **Khai báo constraint runtime:** dùng Bean Validation annotation hoặc custom validator.
3. **Kích hoạt validation:** dùng @Valid, @Validated hoặc method validation phù hợp với điểm bind và phiên bản Spring.
4. **Mô tả schema:** kiểm tra springdoc đã ánh xạ constraint chưa; bổ sung @Schema nếu cần.
5. **Mô tả lỗi:** khai báo response lỗi tương ứng và định dạng error body.
6. **Test runtime:** gửi cả dữ liệu hợp lệ và không hợp lệ, xác nhận status code và payload lỗi.
7. **Test tài liệu:** đọc /v3/api-docs và đối chiếu schema với DTO, constraint và JSON thật.

Một thay đổi constraint có thể tác động đồng thời tới client, server và dữ liệu hiện có. Hãy đánh giá khả năng tương thích trước khi tăng giới hạn, đổi enum hoặc biến property tùy chọn thành bắt buộc.

## Kết luận

Bean Validation annotation khai báo quy tắc dữ liệu; springdoc có thể đọc một phần metadata đó để tạo OpenAPI schema; Spring MVC và Bean Validation provider mới là thành phần thực thi kiểm tra ở runtime. @Schema chỉ mô tả hợp đồng, còn @Valid/@Validated cùng provider và constraint phù hợp mới kích hoạt validation trong luồng xử lý. Hãy kiểm tra riêng JSON OpenAPI, request hợp lệ và request không hợp lệ để bảo đảm tài liệu, hành vi server và response lỗi luôn thống nhất.
