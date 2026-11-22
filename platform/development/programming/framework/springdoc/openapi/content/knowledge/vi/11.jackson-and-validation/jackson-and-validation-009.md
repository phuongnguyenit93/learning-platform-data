# Nhóm validation và giới hạn suy luận tự động của tài liệu

Spring Boot có thể kiểm tra dữ liệu request bằng Bean Validation, còn springdoc-openapi đọc metadata từ controller, DTO, Jackson và các annotation liên quan để tạo schema. Hai cơ chế này phối hợp để tài liệu mô tả được nhiều ràng buộc, nhưng chúng không có cùng trách nhiệm: Bean Validation thực thi điều kiện ở runtime; OpenAPI công bố hợp đồng cho client và công cụ tích hợp.

Khi một DTO dùng nhiều nhóm validation, có kiểm tra giữa các field, custom validator hoặc Jackson thay đổi cách serialize, tài liệu sinh tự động có thể không thể hiện đầy đủ hành vi thực tế. Bài học này giải thích cách tổ chức validation group, cách springdoc suy luận các ràng buộc phổ biến và những trường hợp cần mô tả schema có chủ đích.

## 1. Bean Validation và schema OpenAPI giải quyết hai việc khác nhau

Bean Validation kiểm tra object sau khi dữ liệu đã được bind vào Java. OpenAPI Schema mô tả hình dạng và các giới hạn công khai của dữ liệu được gửi qua HTTP.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Jackson | Đọc JSON thành Java object hoặc serialize object thành JSON | Đổi tên property, bỏ qua field, định dạng ngày |
| Bean Validation | Kiểm tra object theo các constraint đã khai báo | @NotBlank, @Size, @Positive |
| Validation group | Chọn nhóm constraint cần chạy trong một lần validation | OnCreate, OnUpdate |
| springdoc-openapi | Đọc metadata và sinh OpenAPI Schema/Operation | type, required, minLength, pattern |
| OpenAPI validator/client | Diễn giải hợp đồng được công bố | Kiểm tra payload hoặc sinh client |

Ví dụ, DTO có field name với @NotBlank. Khi controller kích hoạt validation, Bean Validation từ chối chuỗi rỗng hoặc chỉ có khoảng trắng. Springdoc có thể phản ánh ràng buộc đó vào schema, nhưng schema được sinh chỉ là mô tả cho client; nó không chạy Bean Validation thay server.

Ngược lại, một mô tả trong @Schema như description hoặc example không tự tạo validation. Nếu tài liệu nói giá trị phải lớn hơn 0 nhưng DTO không có constraint và service không kiểm tra, server vẫn có thể nhận giá trị âm.

## 2. Các constraint Bean Validation thường gặp

Các annotation constraint phổ biến có thể được springdoc và swagger-core dùng để bổ sung giới hạn cho schema. Mức ánh xạ cụ thể phụ thuộc phiên bản và cấu hình; hãy xác minh JSON/YAML được sinh ra.

| Constraint | Ý nghĩa runtime | Schema thường có thể biểu diễn |
| --- | --- | --- |
| @NotNull | Giá trị không được null | Property bắt buộc hoặc ràng buộc không null |
| @NotBlank | Chuỗi phải có ký tự không phải khoảng trắng | required và/hoặc minLength; whitespace-only có thể không được diễn đạt đầy đủ |
| @NotEmpty | Chuỗi, collection, map hoặc array không được rỗng | minLength: 1 hoặc minItems: 1 tùy kiểu |
| @Size(min, max) | Giới hạn kích thước chuỗi/collection/map/array | minLength/maxLength hoặc minItems/maxItems |
| @Min, @Max | Giới hạn số nguyên | minimum/maximum |
| @DecimalMin, @DecimalMax | Giới hạn số thập phân | minimum/maximum và tính exclusive nếu phù hợp |
| @Positive, @PositiveOrZero | Số phải dương hoặc không âm | minimum/exclusiveMinimum |
| @Negative, @NegativeOrZero | Số phải âm hoặc không dương | maximum/exclusiveMaximum |
| @Pattern | Chuỗi phải khớp regular expression | pattern |
| @Email | Giá trị có dạng email theo validator | format: email hoặc mô tả tương đương |
| @Past, @Future | Ngày/thời điểm phải nằm trước hoặc sau hiện tại | Có thể cần mô tả bằng description; schema không tự biết đồng hồ runtime |

Ví dụ DTO:

~~~java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @NotNull
    @DecimalMin("0.01")
    BigDecimal price,

    @NotBlank
    @Pattern(regexp = "^[A-Z]{3}$")
    String currency
) {}
~~~

Với Spring Boot 3 trở lên, Bean Validation dùng package jakarta.validation. Ứng dụng cần có provider, thường được đưa vào qua dependency spring-boot-starter-validation. Với Spring Boot 2, các annotation tương ứng thường nằm trong javax.validation.

Khi controller nhận DTO, kích hoạt validation:

~~~java
@PostMapping
ProductView create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}
~~~

Nếu thiếu @Valid hoặc cơ chế validation tương đương, constraint trên DTO có thể không được thực thi ở điểm nhận request như mong đợi. Hãy kiểm tra cả dependency validation và cách controller kích hoạt validation.

## 3. Hiểu đúng required, nullable và giá trị bị bỏ qua

required trong OpenAPI và @NotNull có liên quan nhưng không hoàn toàn đồng nghĩa.

- required trong object schema nói rằng property phải xuất hiện trong JSON.
- nullable nói rằng giá trị property có được phép là null hay không; cách biểu diễn phụ thuộc phiên bản OpenAPI.
- @NotNull kiểm tra giá trị Java sau khi bind không được null. Khi property JSON bị bỏ qua, field tham chiếu thường nhận null và constraint có thể thất bại.
- @JsonInclude có thể khiến Jackson bỏ property khi serialize response; điều này ảnh hưởng đến việc property có xuất hiện trong JSON trả về.

Ví dụ:

~~~java
public record ProfileRequest(
    @NotNull String displayName,
    String nickname
) {}
~~~

displayName cần có giá trị; nickname có thể vắng mặt. Tuy nhiên, cách phân biệt property vắng mặt với property có giá trị null còn phụ thuộc Jackson binding, kiểu Java, constructor và cấu hình. Nếu API cần ba trạng thái riêng biệt (không gửi, gửi null, gửi giá trị), cần mô hình hóa rõ ràng thay vì chỉ dựa vào một String có thể null.

Đừng kết luận rằng mọi property có @NotNull sẽ luôn được công bố đúng trong required của mọi phiên bản springdoc. Hãy mở /v3/api-docs, kiểm tra components.schemas và đối chiếu với payload thực tế. Nếu cần hợp đồng rõ ràng, có thể dùng @Schema(requiredMode = Schema.RequiredMode.REQUIRED) hoặc tách request/response model phù hợp.

Ví dụ khai báo metadata tường minh:

~~~java
@Schema(
    description = "Tên hiển thị, bắt buộc khi tạo hồ sơ",
    requiredMode = Schema.RequiredMode.REQUIRED
)
@NotBlank
String displayName
~~~

requiredMode chỉ điều khiển tài liệu OpenAPI. @NotBlank mới thực thi kiểm tra dữ liệu khi runtime.

## 4. Validation group là gì?

Validation group cho phép dùng các tập constraint khác nhau tùy thao tác. Một DTO có thể được dùng khi tạo mới và cập nhật, nhưng một số field chỉ bắt buộc ở một trong hai tình huống.

Nếu không chỉ định groups trên constraint, constraint thuộc nhóm Default. Có thể khai báo các group riêng bằng interface:

~~~java
public interface OnCreate {}
public interface OnUpdate {}
~~~

Gắn group lên từng constraint:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ProductCommand {

    @Null(groups = OnCreate.class)
    @NotNull(groups = OnUpdate.class)
    private Long id;

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    @Size(max = 80, groups = {OnCreate.class, OnUpdate.class})
    private String name;

    @NotNull(groups = OnCreate.class)
    @Positive(groups = {OnCreate.class, OnUpdate.class})
    private Integer quantity;

    // Getter và setter
}
~~~

Ý nghĩa:

- Khi tạo mới, id phải null, name phải có nội dung và quantity phải có giá trị dương.
- Khi cập nhật, id phải có giá trị; name vẫn bắt buộc; nếu quantity được gửi thì phải dương theo constraint đang áp dụng.
- Constraint không gắn group cụ thể sẽ thuộc Default và chỉ chạy khi Default được chọn hoặc được đưa vào group sequence phù hợp.

Group không tự kích hoạt chỉ vì được khai báo trên DTO. Controller hoặc tầng gọi validator phải chọn group cần chạy.

## 5. Kích hoạt group bằng @Validated

Trong Spring MVC, có thể dùng @Validated trên tham số request body để chỉ định group:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @PostMapping
    ProductView create(
            @RequestBody @Validated(OnCreate.class) ProductCommand command) {
        return productService.create(command);
    }

    @PutMapping("/{id}")
    ProductView update(
            @PathVariable Long id,
            @RequestBody @Validated(OnUpdate.class) ProductCommand command) {
        return productService.update(id, command);
    }
}
~~~

@Validated là annotation của Spring, có thể chỉ định validation hint/group. @Valid của Jakarta Validation thường kích hoạt nhóm Default khi dùng trên request body. Nếu cần nhóm cụ thể, dùng @Validated với group tương ứng và kiểm thử trên phiên bản Spring đang chạy.

Không nên nhầm @Validated trên tham số với @Validated trên class/service. Khi đặt trên class, annotation còn có thể tham gia kích hoạt method validation thông qua proxy của Spring. Cơ chế method validation và validation request body là hai điểm tích hợp khác nhau; hãy đặt annotation đúng nơi cần thực thi.

Với method validation, có thể khai báo nhóm trên method hoặc type theo cơ chế Spring validation. Nếu dự án dùng Spring Framework 6.1 trở lên, cần đọc hướng dẫn method validation của phiên bản đó vì hỗ trợ validation tích hợp trong MVC có thay đổi so với cách dùng proxy AOP truyền thống.

## 6. Group sequence và thứ tự kiểm tra

@GroupSequence cho phép yêu cầu các nhóm được kiểm tra theo thứ tự. Nếu nhóm trước có lỗi, các nhóm sau trong sequence sẽ không chạy.

~~~java
public interface BasicChecks {}
public interface BusinessChecks {}

@GroupSequence({
    ProductCommand.class,
    BasicChecks.class,
    BusinessChecks.class
})
public class ProductCommand {
    @NotBlank(groups = BasicChecks.class)
    private String name;

    @Positive(groups = BusinessChecks.class)
    private Integer quantity;

    // Getter và setter
}
~~~

Khi re-define Default group sequence trên class, sequence phải chứa chính class đó để đại diện cho các constraint thuộc Default của class. Không đưa Default.class vào sequence thay cho class. Các group trong sequence được đánh giá tuần tự; nếu một group vi phạm, các group sau bị bỏ qua.

Group sequence hữu ích khi muốn kiểm tra cấu trúc cơ bản trước, rồi mới chạy các kiểm tra tốn kém hoặc phụ thuộc điều kiện. Tuy nhiên, sequence không tự biến thành điều kiện OpenAPI. springdoc không thể suy ra một schema riêng chỉ từ thứ tự thực thi validation.

## 7. Validation lồng nhau và group conversion

DTO có thể chứa object lồng nhau. @Valid kích hoạt cascade validation để kiểm tra object con:

~~~java
public class AddressCommand {
    @NotBlank
    private String city;

    @NotBlank
    private String street;

    // Getter và setter
}

public class CustomerCommand {
    @NotBlank
    private String name;

    @Valid
    @NotNull
    private AddressCommand address;

    // Getter và setter
}
~~~

Nếu muốn đổi group khi đi vào object con, dùng @ConvertGroup:

~~~java
public class CustomerCommand {
    @Valid
    @ConvertGroup(from = OnCreate.class, to = AddressCreateChecks.class)
    private AddressCommand address;
}
~~~

@ConvertGroup chỉ có hiệu lực tại cascade validation được đánh dấu @Valid. Group conversion hữu ích khi object con có lifecycle validation khác object cha.

Schema OpenAPI thường mô tả cấu trúc lồng nhau qua properties và $ref. Nó có thể thể hiện các constraint tĩnh ở object con, nhưng không nhất thiết biết rằng controller đã đổi group bằng @ConvertGroup. Vì vậy, không giả định tài liệu tự tạo ra một biến thể schema khác cho từng group lồng nhau.

## 8. Constraint cấp class và quy tắc giữa nhiều field

Một số điều kiện không thuộc riêng một field. Ví dụ ngày kết thúc phải sau ngày bắt đầu, hoặc phải cung cấp email hoặc số điện thoại. Có thể tạo class-level constraint với ConstraintValidator:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "Ngày kết thúc phải sau ngày bắt đầu";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

public class BookingRequest {
    @NotNull
    private LocalDate startDate;

    @NotNull
    private LocalDate endDate;

    // Getter và setter
}

public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }
        return value.getEndDate().isAfter(value.getStartDate());
    }
}
~~~

Validator trả true khi dữ liệu chưa đủ để so sánh vì @NotNull chịu trách nhiệm báo lỗi thiếu field. Nếu muốn báo lỗi tại một property cụ thể, có thể cấu hình ConstraintValidatorContext để tạo property node.

springdoc có thể đọc một số annotation constraint phổ biến trên field, nhưng không thể tự suy ra mọi thuật toán trong custom ConstraintValidator. Trong ví dụ trên, schema nhìn thấy hai ngày bắt buộc nhưng không thể tự biết quan hệ endDate phải sau startDate chỉ từ tên class validator.

Hãy công bố quy tắc giữa field bằng description hoặc tài liệu nghiệp vụ, đồng thời kiểm tra runtime. Với OpenAPI 3.1, một số điều kiện có thể mô tả bằng JSON Schema if/then/else, dependentRequired hoặc composition. Tuy nhiên, điều kiện so sánh giá trị của hai ngày vẫn có thể cần mô tả bằng văn bản hoặc custom validation ngoài schema chuẩn.

## 9. Những giới hạn suy luận tự động của springdoc

Springdoc xây dựng OpenAPI bằng cách phân tích controller, kiểu Java, generic, annotation OpenAPI, metadata validation và một phần annotation Jackson. Đây là quá trình suy luận từ metadata tĩnh; nó không chạy toàn bộ ứng dụng để thử mọi đường đi của dữ liệu.

Các trường hợp sau thường cần xem xét thủ công:

| Trường hợp | Vì sao khó suy luận tự động | Cách xử lý |
| --- | --- | --- |
| Validation group khác nhau theo operation | Một DTO có nhiều tập constraint; schema component có thể được dùng chung | Tách request DTO theo thao tác hoặc tùy biến schema theo operation |
| @GroupSequence | Thể hiện thứ tự chạy validation chứ không phải cấu trúc dữ liệu mới | Mô tả rõ quy tắc runtime; test các group |
| Custom ConstraintValidator | Logic có thể truy vấn database, clock hoặc service | Bổ sung description, custom schema nếu biểu diễn được và kiểm thử server |
| Constraint cấp class/cross-field | Ràng buộc liên quan nhiều property | Mô tả quan hệ trong operation/schema; cân nhắc JSON Schema composition |
| Điều kiện phụ thuộc người dùng hoặc trạng thái | Cần context runtime và dữ liệu bên ngoài payload | Mô tả lỗi nghiệp vụ và response; không giả định schema đủ |
| Jackson custom serializer/deserializer | Wire format có thể khác kiểu Java | Mô tả schema tường minh hoặc đăng ký ModelConverter |
| @JsonView hoặc view theo endpoint | Một DTO có thể có nhiều hình dạng JSON tùy view | Dùng DTO riêng hoặc cấu hình schema theo operation |
| @JsonInclude | Property có thể bị bỏ khi serialize null/empty | Kiểm tra JSON response thực tế và required/nullable |
| Giá trị được tính trong getter | Giá trị JSON có thể không tương ứng field lưu trữ | Mô tả property công khai và xác minh output |
| Converter tùy chỉnh cho enum/date/value object | Cách parse/serialize có thể là quy ước riêng | Dùng @Schema type/format/example và kiểm thử converter |

Đặc tả OpenAPI phải mô tả hợp đồng HTTP quan sát được, không phải toàn bộ cấu trúc nội bộ của Java. Nếu kiểu Java hoặc metadata không phản ánh wire format, cần sửa model hoặc bổ sung mô tả OpenAPI.

## 10. Jackson có thể thay đổi hình dạng JSON

Jackson điều khiển cách object được đọc và ghi. Một số annotation có thể ảnh hưởng trực tiếp đến schema:

| Annotation/cấu hình | Ảnh hưởng JSON | Điều cần kiểm tra trong OpenAPI |
| --- | --- | --- |
| @JsonProperty | Đổi tên property hoặc quyền đọc/ghi | Tên property và readOnly/writeOnly |
| @JsonIgnore | Bỏ qua property khi đọc/ghi theo cấu hình | Property có nên xuất hiện trong schema không |
| @JsonInclude | Bỏ qua null/empty khi serialize | Property có thể vắng mặt trong response |
| @JsonFormat | Định dạng ngày, thời gian hoặc số | type/format/example khớp chuỗi thực tế |
| @JsonUnwrapped | Đưa property lồng ra cấp cha | Cấu trúc schema có khớp JSON phẳng không |
| @JsonView | Chọn tập property theo view | Mỗi operation có thể cần schema khác nhau |
| @JsonTypeInfo | Thêm discriminator hoặc chọn subtype | oneOf/discriminator và payload thực tế |
| Custom serializer/deserializer | Tùy biến hoàn toàn wire representation | Cần schema tường minh hoặc converter riêng |

Ví dụ password chỉ được nhận khi tạo tài khoản và không được trả về:

~~~java
public record CreateAccountRequest(
    String username,
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    String password
) {}
~~~

Property write-only có ý nghĩa khác với field bị @JsonIgnore hoàn toàn. Nó có thể xuất hiện trong request nhưng không xuất hiện trong response. Nếu dùng cùng một DTO cho cả request và response, cần xác nhận springdoc đánh dấu writeOnly phù hợp; cách rõ ràng hơn thường là tách CreateAccountRequest và AccountResponse.

Ví dụ @JsonInclude:

~~~java
public class AccountResponse {
    private String id;

    @JsonInclude(JsonInclude.Include.NON_NULL)
    private String nickname;
}
~~~

Khi nickname null, Jackson có thể bỏ property khỏi JSON response. Điều này không giống một property luôn hiện diện với giá trị null. Nếu client cần hiểu chính xác, hãy mô tả property là tùy chọn và kiểm tra cách schema biểu diễn nullable theo phiên bản OpenAPI.

## 11. Một DTO cho nhiều thao tác có thể làm tài liệu mơ hồ

Dùng cùng DTO cho create và update có vẻ giảm code, nhưng có thể tạo ra hợp đồng khó hiểu:

- Create cần name và quantity.
- Update cần id; một số field có thể tùy chọn.
- Validation group chọn các constraint khác nhau.
- Response có thể ẩn password hoặc chứa field chỉ đọc.

Nếu cả hai operation tham chiếu cùng một component ProductCommand, OpenAPI thường chỉ có một schema component chung. Một component không thể vừa yêu cầu field name ở operation này vừa làm field đó tùy chọn ở operation khác mà không có cấu trúc composition riêng.

Thiết kế rõ hơn bằng hai DTO:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @NotNull
    @Positive
    Integer quantity
) {}

public record UpdateProductRequest(
    @NotBlank
    @Size(max = 80)
    String name,

    @Positive
    Integer quantity
) {}
~~~

Controller công bố hai request schema riêng:

~~~java
@PostMapping
ProductView create(@Valid @RequestBody CreateProductRequest request) {
    return productService.create(request);
}

@PatchMapping("/{id}")
ProductView update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateProductRequest request) {
    return productService.update(id, request);
}
~~~

Khi hợp đồng create/update khác nhau, DTO riêng thường giúp client hiểu rõ hơn và tránh phụ thuộc vào việc công cụ có diễn giải validation group giống nhau hay không. Validation group vẫn hữu ích cho domain object hoặc những trường hợp tái sử dụng có chủ đích, nhưng không nhất thiết là lựa chọn tốt nhất cho mọi request model công khai.

## 12. Khi cần tùy biến schema theo operation

Nếu phải giữ chung DTO vì lý do nội bộ, nhưng mỗi operation cần một schema khác nhau, có thể dùng @Parameter/@Schema hoặc OpenAPI customizer để công bố request body riêng. Ví dụ cấu hình requestBody bằng annotation:

~~~java
@Operation(
    summary = "Tạo sản phẩm",
    requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
        required = true,
        content = @Content(
            schema = @Schema(implementation = CreateProductRequest.class)
        )
    )
)
~~~

Với customizer, có thể truy cập operation theo path/method và thay schema tham chiếu. Việc này cần cẩn thận để không thay đổi component dùng chung ngoài ý muốn. Nếu schema được tái sử dụng ở nhiều operation, tạo component riêng cho từng hợp đồng hoặc dùng inline schema khi thích hợp.

@Schema(requiredMode = ...), description, example, allowableValues và các keyword composition chỉ bổ sung metadata OpenAPI. Chúng không thay thế Bean Validation, Jackson hoặc logic nghiệp vụ. Mọi thay đổi schema phải được kiểm tra ở /v3/api-docs sau khi ứng dụng khởi động.

## 13. Kiểm tra validation và tài liệu theo từng operation

Khi thêm hoặc sửa constraint, kiểm tra cả ba lớp:

1. Runtime: gửi payload hợp lệ và không hợp lệ để xác nhận constraint đúng group đã chạy.
2. Serialization: kiểm tra JSON thực tế trước và sau khi Jackson xử lý.
3. Contract: kiểm tra schema trong /v3/api-docs và Swagger UI có phản ánh đúng field, type, required, format và giới hạn.

Ví dụ test tích hợp với MockMvc:

~~~java
@WebMvcTest(ProductController.class)
class ProductControllerValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsBlankName() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"name":"   ","price":100}
                    """))
            .andExpect(status().isBadRequest());
    }
}
~~~

Ví dụ này minh họa kiểm tra runtime cho constraint mặc định; cần bổ sung test riêng cho từng validation group và từng operation. Test schema có thể tải JSON OpenAPI rồi xác nhận các property và keyword mong đợi tồn tại.

Khi dùng group, nên có ma trận test:

| Operation | Group | Payload kiểm tra |
| --- | --- | --- |
| POST create | OnCreate | id null, name hợp lệ, quantity dương |
| POST create | OnCreate | id có giá trị hoặc thiếu quantity |
| PUT update | OnUpdate | id có giá trị, name hợp lệ |
| PUT update | OnUpdate | thiếu id hoặc name sai |

Không chỉ test trường hợp thành công. Một group bị chọn nhầm có thể khiến constraint không chạy hoặc chạy ngoài ý muốn.

## 14. Checklist giới hạn suy luận tự động

Trước khi công bố tài liệu, hãy tự hỏi:

- Controller có kích hoạt validation ở đúng tham số không?
- Group nào được chọn cho từng operation?
- Constraint thuộc Default hay group tùy chỉnh?
- Có group sequence hoặc group conversion không?
- Có custom validator hoặc điều kiện giữa nhiều field không?
- Jackson có đổi tên, bỏ qua, định dạng hoặc biến đổi property không?
- DTO có được dùng chung cho request và response không?
- Schema sinh ra có khớp JSON thực tế không?
- Có quy tắc phụ thuộc database, người dùng, thời gian hoặc trạng thái nghiệp vụ không?
- Những quy tắc không thể biểu diễn bằng schema đã được mô tả trong operation hoặc tài liệu bổ sung chưa?

Nếu câu trả lời cho thấy schema không thể biểu đạt hết logic, hãy công bố phần cấu trúc có thể kiểm tra bằng OpenAPI và mô tả phần còn lại bằng văn bản, mã lỗi hoặc tài liệu nghiệp vụ. Không tạo ra một schema có vẻ chính xác nhưng lại mâu thuẫn với runtime.

## 15. Quy trình thiết kế validation và OpenAPI

Khi thiết kế DTO và tài liệu:

1. Xác định request/response model và wire format thực tế do Jackson tạo ra.
2. Đặt constraint cơ bản trên field và chọn validation group theo từng operation nếu cần.
3. Dùng @Valid cho cascade; dùng @Validated để chọn group phù hợp.
4. Dùng @GroupSequence chỉ khi cần thứ tự kiểm tra và hiểu rõ quy tắc dừng khi có lỗi.
5. Đặt custom/cross-field validation ở class hoặc service và mô tả điều kiện đó cho client.
6. Kiểm tra springdoc đã phản ánh các constraint tĩnh đúng chưa; không giả định nó hiểu logic tùy chỉnh.
7. Nếu một DTO có nhiều hợp đồng khác nhau, cân nhắc tách request/response DTO hoặc tạo schema riêng theo operation.
8. Đối chiếu OpenAPI JSON/YAML với test runtime và payload thực tế.

Springdoc giúp giảm việc viết tài liệu thủ công bằng cách suy luận từ code, nhưng chất lượng hợp đồng phụ thuộc vào metadata mà ứng dụng cung cấp. Validation group, custom validator và Jackson customization là những nơi cần chủ động kiểm tra để bảo đảm client nhìn thấy đúng dữ liệu và đúng giới hạn mà server thực thi.

## Tài liệu tham khảo

- [Jakarta Bean Validation – Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework – Validation Groups](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jackson Annotations – GitHub](https://github.com/FasterXML/jackson-annotations)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [springdoc-openapi – Documentation](https://springdoc.org/)
