# Phối hợp JSON Schema hoặc Bean Validation khi phù hợp

Jackson Databind chuyển JSON thành object Java và ngược lại. Quá trình ánh xạ này kiểm tra được cú pháp JSON, kiểu token và khả năng tạo giá trị Java, nhưng không tự xác nhận toàn bộ hợp đồng dữ liệu hoặc quy tắc nghiệp vụ của ứng dụng.

Ví dụ, một request có thể parse thành DTO hợp lệ về mặt Java nhưng vẫn thiếu field bắt buộc theo API, chứa chuỗi vượt quá độ dài cho phép, có ngày kết thúc trước ngày bắt đầu hoặc dùng một tổ hợp field không hợp lệ. Để kiểm soát các trường hợp này, ứng dụng thường phối hợp Jackson với **JSON Schema** và/hoặc **Bean Validation**.

Hai cơ chế giải quyết những lớp vấn đề khác nhau:

- **JSON Schema** kiểm tra cấu trúc và giá trị của tài liệu JSON trước hoặc độc lập với quá trình bind vào DTO: property bắt buộc, kiểu JSON, giới hạn số/chuỗi, cấu trúc object/array, enum, property bổ sung và các quy tắc schema khác.
- **Bean Validation** kiểm tra trạng thái object Java sau khi Jackson deserialize: `@NotNull`, `@NotBlank`, `@Size`, `@Positive`, constraint trên phần tử collection, kiểm tra object lồng nhau và quy tắc nhiều field.

Không phải ứng dụng nào cũng cần cả hai. Chọn lớp kiểm tra dựa trên nơi hợp đồng được chia sẻ và loại lỗi cần phát hiện. Nếu JSON là hợp đồng công khai giữa nhiều ngôn ngữ hoặc service, JSON Schema có thể giúp producer/consumer dùng chung quy tắc. Nếu quy tắc gắn với model Java và nghiệp vụ backend, Bean Validation thường là lựa chọn tự nhiên. Với API quan trọng, hai lớp có thể bổ sung cho nhau.

## 1. Jackson làm gì và không làm gì?

Jackson có thể từ chối JSON sai cú pháp, token không phù hợp với kiểu đích, enum không nhận diện theo cấu hình mặc định, unknown property khi `FAIL_ON_UNKNOWN_PROPERTIES` được bật, hoặc object không thể tạo theo creator/constructor đã cấu hình.

Ví dụ DTO:

```java
public class CreateUserRequest {
    private String name;
    private String email;
    private Integer age;

    // Getter và setter
}
```

JSON sau có thể deserialize thành object thành công:

```json
{
  "name": " ",
  "email": "not-an-email",
  "age": -5
}
```

Các giá trị đều có kiểu tương thích với property Java: string, string và integer. Jackson không tự biết rằng tên phải có ký tự, email cần đúng định dạng theo quy tắc ứng dụng và tuổi phải không âm.

Jackson cũng không phải một công cụ JSON Schema validator. Các annotation như `@JsonProperty(required = true)` không thay thế một bộ kiểm tra schema đầy đủ; mức hỗ trợ và semantics của chúng gắn với data binding cụ thể. Tương tự, `@JsonInclude` điều khiển serialize output, không xác nhận request đầu vào.

## 2. Hai thời điểm kiểm tra dữ liệu

Một pipeline thường gặp có thể đặt kiểm tra schema trước khi bind, rồi kiểm tra object sau khi bind:

```text
HTTP request body / JSON bytes
          |
          v
       Jackson
          |
          v
      JsonNode
          |
          +----> JSON Schema validation
          |            |
          |            +-- lỗi schema -> trả lỗi request
          |            |
          |            v
          |       schema hợp lệ
          |
          v
    ObjectMapper.readValue()
          |
          v
      Java DTO
          |
          v
      Bean Validation
          |
          +-- constraint violations -> trả lỗi field
          |
          v
   nghiệp vụ / service layer
```

Có thể dùng riêng từng lớp:

- JSON Schema trước binding khi cần xác nhận đúng tài liệu JSON mà producer gửi.
- Bean Validation sau binding khi cần kiểm tra object Java và quan hệ giữa các property.
- Cả hai khi cần hợp đồng JSON có thể chia sẻ và validation object/domain riêng.

Đừng nhầm việc JSON parse thành công với việc request hợp lệ. Đó là hai bước khác nhau.

## 3. JSON Schema kiểm tra hợp đồng ở cấp tài liệu JSON

JSON Schema là một định dạng mô tả cấu trúc và ràng buộc của JSON. Schema có thể quy định:

- Root phải là object, array, string, number, boolean hoặc null.
- Property nào bắt buộc phải xuất hiện.
- Kiểu dữ liệu của từng property.
- Giới hạn `minLength`, `maxLength`, `minimum`, `maximum`.
- Giá trị nằm trong tập cho phép bằng `enum` hoặc `const`.
- Cấu trúc và số lượng phần tử của array.
- Property bổ sung có được phép hay không.
- Các cấu trúc lồng nhau, tham chiếu `$ref`, composition và điều kiện schema.

Ví dụ schema cho request tạo user:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["name", "email", "age"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 80
    },
    "email": {
      "type": "string",
      "format": "email",
      "maxLength": 254
    },
    "age": {
      "type": "integer",
      "minimum": 0,
      "maximum": 130
    }
  },
  "additionalProperties": false
}
```

Schema này quy định root object phải có ba key, `name` là string có độ dài giới hạn, `email` là string mang format email, `age` là integer trong khoảng cho phép và không nhận property ngoài danh sách.

### 3.1. required khác với type và null

Trong JSON Schema, `required` yêu cầu key xuất hiện. Nó không tự cấm giá trị null. Nếu property cần có và không được null, hãy khai báo cả `required` lẫn type không chứa `null`:

```json
{
  "type": "object",
  "required": ["email"],
  "properties": {
    "email": {
      "type": "string"
    }
  }
}
```

Với schema trên:

| JSON | Kết quả |
|---|---|
| `{}` | Không hợp lệ vì thiếu key `email` |
| `{"email": null}` | Không hợp lệ vì null không phải string |
| `{"email": "a@example.com"}` | Hợp lệ về type/required |

Nếu muốn cho phép null, schema có thể dùng type array:

```json
{
  "type": ["string", "null"]
}
```

### 3.2. additionalProperties và unknown property

`additionalProperties: false` từ chối property không được liệt kê trong schema. Đây là kiểm tra ở cấp JSON document.

Jackson có cơ chế riêng `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`. Hai cơ chế không đồng nghĩa:

- JSON Schema kiểm tra tên property theo schema trước khi hoặc độc lập với DTO.
- Jackson kiểm tra property có thể được ánh xạ vào Java type hay không trong quá trình binding.

Nếu JSON Schema cho phép property mở nhưng Jackson DTO không có `@JsonAnySetter` và vẫn bật `FAIL_ON_UNKNOWN_PROPERTIES`, bước binding vẫn có thể thất bại. Ngược lại, nếu Jackson bỏ qua unknown property, nó có thể làm mất dữ liệu mà schema đã cho phép.

Hãy xác định một chính sách nhất quán. Với dữ liệu mở, có thể dùng `additionalProperties` dạng schema và `@JsonAnySetter` để thu thập extension. Với API nghiêm ngặt, đặt `additionalProperties: false` và giữ chính sách unknown property phù hợp.

### 3.3. Kiểm tra enum bằng JSON Schema

Schema có thể giới hạn giá trị string:

```json
{
  "type": "string",
  "enum": ["NEW", "PAID", "CANCELLED"]
}
```

Điều này kiểm tra tập giá trị ở cấp JSON trước khi Jackson chuyển string thành enum Java. Nếu enum Java có `UNKNOWN` fallback nhưng schema không liệt kê `REFUNDED`, schema vẫn từ chối `REFUNDED`. Đây có thể là điều mong muốn nếu contract phải nghiêm ngặt; nếu consumer cần tương thích với giá trị enum mới, schema cũng phải có chính sách phù hợp.

### 3.4. format không phải lúc nào cũng là assertion

JSON Schema định nghĩa các format như `email`, `date`, `date-time`, `uri` và một số định dạng khác. Tùy dialect và validator, `format` có thể được xử lý như annotation hoặc assertion; nhiều thư viện cần bật format assertion hoặc đăng ký format validator cụ thể.

Vì vậy, không nên cho rằng chỉ viết `"format": "email"` là mọi validator đều sẽ từ chối email sai. Kiểm tra tài liệu của validator và cấu hình format validation đang dùng. Nếu format là yêu cầu bắt buộc, hãy bật assertion tương ứng hoặc bổ sung constraint riêng.

## 4. Tích hợp JSON Schema validator với Jackson

Jackson tạo `JsonNode` rất thuận tiện cho việc đưa JSON vào một thư viện JSON Schema validator. Thư viện validator là thành phần riêng; Jackson không tự thực hiện các keyword schema.

Một luồng triển khai điển hình:

1. Dùng `ObjectMapper.readTree()` parse request thành `JsonNode`.
2. Đưa node vào JSON Schema validator đã biên dịch/tải schema.
3. Nếu có lỗi, chuyển validation messages thành response lỗi theo API.
4. Nếu hợp lệ, dùng `treeToValue()` hoặc `convertValue()` để tạo DTO.
5. Chạy Bean Validation nếu còn các constraint ở cấp object.

Ví dụ minh họa với NetworkNT JSON Schema Validator. API khởi tạo có thể thay đổi theo phiên bản thư viện, nên cần khóa dependency và dùng đúng tài liệu của version dự án:

```java
JsonNode schemaNode = mapper.readTree(schemaJson);
JsonNode inputNode = mapper.readTree(requestBody);

JsonSchemaFactory factory = JsonSchemaFactory.getInstance(
    SpecVersion.VersionFlag.V202012
);
JsonSchema schema = factory.getSchema(schemaNode);

Set<ValidationMessage> errors = schema.validate(inputNode);
if (!errors.isEmpty()) {
    throw new InvalidRequestSchemaException(errors);
}

CreateUserRequest request = mapper.treeToValue(
    inputNode,
    CreateUserRequest.class
);
```

Các kiểu `JsonSchemaFactory`, `JsonSchema`, `SpecVersion` và `ValidationMessage` ở ví dụ thuộc thư viện validator, không thuộc Jackson. Hãy kiểm tra package import và overload đúng với phiên bản NetworkNT mà ứng dụng đang dùng.

### 4.1. Tải và cache schema

Không nên đọc và biên dịch file schema cho mỗi request. Schema thường không đổi theo từng request, vì vậy nên tải, resolve `$ref` và biên dịch một lần khi ứng dụng khởi động, sau đó tái sử dụng đối tượng schema đã chuẩn bị.

Ví dụ thiết kế service:

```java
public class UserSchemaValidator {
    private final JsonSchema schema;

    public UserSchemaValidator(JsonSchema schema) {
        this.schema = schema;
    }

    public void validate(JsonNode input) {
        Set<ValidationMessage> errors = schema.validate(input);
        if (!errors.isEmpty()) {
            throw new InvalidRequestSchemaException(errors);
        }
    }
}
```

Khởi tạo `JsonSchema` trong composition root rồi inject vào service. Nếu schema thay đổi theo version API, quản lý cache theo schema/version thay vì ghi đè một instance đang được request sử dụng.

### 4.2. Quản lý `$ref` và schema ngoài

Schema có thể tham chiếu schema khác bằng `$ref`. Hãy quyết định rõ nguồn schema được phép tải. Với ứng dụng production, nên đóng gói schema hoặc dùng registry tin cậy, kiểm soát truy cập mạng và cache. Không nên để request tự cung cấp schema URI tùy ý rồi validator tải tài nguyên từ URL không kiểm soát.

Đảm bảo validator dùng đúng dialect được khai báo trong `$schema`. Một số keyword và semantics khác nhau giữa Draft 7, 2019-09 và 2020-12. Cấu hình sai dialect có thể khiến schema được diễn giải không đúng ý định.

## 5. Bean Validation kiểm tra object Java

Jakarta Bean Validation (trước đây là Javax Bean Validation) định nghĩa API annotation và `Validator` để kiểm tra constraint trên object. Một implementation phổ biến là Hibernate Validator.

Các constraint thường dùng:

| Annotation | Ý nghĩa phổ biến |
|---|---|
| `@NotNull` | Giá trị không được null |
| `@NotEmpty` | Không null và không rỗng với kiểu được hỗ trợ |
| `@NotBlank` | Chuỗi không null và có ít nhất một ký tự không phải whitespace |
| `@Size(min, max)` | Kích thước/độ dài nằm trong giới hạn |
| `@Min`, `@Max` | Giá trị số nằm trong giới hạn nguyên |
| `@Positive`, `@PositiveOrZero` | Số dương hoặc không âm |
| `@DecimalMin`, `@DecimalMax` | Giới hạn cho kiểu số thập phân |
| `@Email` | Kiểm tra hình thức email theo implementation/spec |
| `@Pattern` | Chuỗi khớp regular expression |
| `@Past`, `@Future` | Ngày/thời điểm trước hoặc sau hiện tại |
| `@Valid` | Cascade validation sang object lồng nhau hoặc phần tử container |

Các constraint có thể đặt trên field, getter, constructor parameter hoặc method parameter theo mục tiêu validation. Trong DTO request, đặt trên field/property thường dễ đọc.

## 6. Khai báo constraint trên DTO

Ví dụ request tạo user:

```java
public class CreateUserRequest {
    @NotBlank
    @Size(max = 80)
    private String name;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @NotNull
    @Min(0)
    @Max(130)
    private Integer age;

    // Getter và setter
}
```

Ở đây:

- `@NotBlank` từ chối null, chuỗi rỗng và chuỗi chỉ chứa whitespace.
- `@Size(max = 80)` giới hạn độ dài tên.
- `@Email` kiểm tra định dạng email theo validator.
- `@NotNull` bảo đảm age được cung cấp và không null.
- `@Min` và `@Max` giới hạn tuổi.

Dùng `Integer` thay cho `int` khi cần phân biệt age bị thiếu/null với age bằng 0. Với primitive, Jackson không thể gán null vào field; giá trị mặc định có thể là 0 và làm mất dấu hiệu field không được cung cấp.

### 6.1. Kết hợp constraint theo đúng ý nghĩa

`@Size` không tự cấm null. Nhiều constraint như `@Size`, `@Pattern` hoặc `@Email` xem null là hợp lệ để có thể kết hợp với `@NotNull`/`@NotBlank` khi cần bắt buộc.

Ví dụ:

```java
@NotBlank
@Size(min = 8, max = 64)
private String password;
```

`@NotBlank` kiểm tra có nội dung; `@Size` kiểm tra độ dài. Hai constraint bổ sung nhau.

`@Email` không thay thế xác minh email thực sự tồn tại hoặc người dùng sở hữu địa chỉ đó. Nó chỉ kiểm tra hình thức theo quy tắc validator.

## 7. Chạy Bean Validation sau Jackson deserialize

Trong Java thuần, có thể tạo `Validator` từ `Validation`:

```java
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();
```

Sau khi Jackson tạo DTO:

```java
CreateUserRequest request = mapper.readValue(
    requestBody,
    CreateUserRequest.class
);

Set<ConstraintViolation<CreateUserRequest>> violations =
    validator.validate(request);

if (!violations.isEmpty()) {
    throw new RequestValidationException(violations);
}
```

`validator.validate()` trả về tập constraint violation. Mỗi violation cung cấp:

- Property path: đường dẫn property vi phạm.
- Message: thông báo đã được nội suy.
- Invalid value: giá trị không đạt constraint.
- Root bean và leaf bean liên quan.
- Constraint descriptor và annotation metadata.

Ứng dụng thường chuyển các violation thành response HTTP 400 với danh sách lỗi field. Không nên trả toàn bộ `invalidValue` cho client nếu giá trị có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm.

### 7.1. Helper kiểm tra DTO

Có thể đóng gói việc kiểm tra:

```java
public final class BeanValidationSupport {
    private final Validator validator;

    public BeanValidationSupport(Validator validator) {
        this.validator = validator;
    }

    public <T> void validate(T value) {
        Set<ConstraintViolation<T>> violations = validator.validate(value);
        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }
    }
}
```

`Validator` được thiết kế để tái sử dụng. Tạo `ValidatorFactory`/`Validator` ở giai đoạn khởi tạo ứng dụng và đóng factory khi ứng dụng dừng nếu lifecycle của framework yêu cầu. Không tạo factory mới cho mỗi request.

## 8. Cascade validation cho object lồng nhau

Constraint trên object cha không tự động chạy trên object con. Cần đặt `@Valid` ở property muốn cascade:

```java
public class AddressRequest {
    @NotBlank
    private String street;

    @NotBlank
    private String city;

    @NotBlank
    @Pattern(regexp = "[0-9]{5,10}")
    private String postalCode;

    // Getter và setter
}

public class CreateUserRequest {
    @NotBlank
    private String name;

    @NotNull
    @Valid
    private AddressRequest address;

    // Getter và setter
}
```

`@NotNull` yêu cầu address tồn tại; `@Valid` yêu cầu validator kiểm tra các constraint bên trong `AddressRequest`.

Nếu chỉ có `@Valid` mà không có `@NotNull`, giá trị null thường không tạo cascade violation vì không có object con để kiểm tra. Nếu address là bắt buộc, dùng cả hai.

### 8.1. Cascade vào phần tử collection

Bean Validation hỗ trợ container element constraints:

```java
public class CreateOrderRequest {
    @NotEmpty
    private List<@NotNull @Valid OrderLineRequest> lines;
}

public class OrderLineRequest {
    @NotBlank
    private String sku;

    @Positive
    private int quantity;
}
```

`@NotEmpty` yêu cầu list có phần tử. `@NotNull` kiểm tra từng phần tử không null. `@Valid` cascade vào từng `OrderLineRequest`, nơi `sku` và `quantity` được kiểm tra.

Với map, có thể đặt constraint trên key và value:

```java
private Map<@NotBlank String, @NotNull @Valid SettingRequest> settings;
```

Điều này cần Bean Validation 2.0 trở lên (Jakarta Bean Validation 2.0/3.0+) và implementation hỗ trợ container element constraints.

## 9. Constraint ở cấp class để kiểm tra nhiều field

Một số quy tắc không thể kiểm tra độc lập trên từng field. Ví dụ ngày bắt đầu phải trước ngày kết thúc.

```java
@ValidDateRange
public class BookingRequest {
    private LocalDate startDate;
    private LocalDate endDate;

    // Getter và setter
}
```

Annotation constraint:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "startDate must be on or before endDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator:

```java
public class DateRangeValidator
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

        return !value.getEndDate().isBefore(value.getStartDate());
    }
}
```

Validator ở cấp class có thể kiểm tra đồng thời nhiều property. Ví dụ trên để các constraint `@NotNull` riêng quyết định ngày nào bắt buộc; class-level validator chỉ kiểm tra quan hệ khi cả hai ngày đã có.

### 9.1. Gắn violation vào một property cụ thể

Mặc định class-level violation có path ở cấp object. Có thể xây dựng property path để API trả lỗi gần field hơn:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "endDate must not be before startDate")
    .addPropertyNode("endDate")
    .addConstraintViolation();
return false;
```

Điều này giúp client hiển thị lỗi cạnh `endDate`. Hãy giữ message rõ ràng và không đưa thông tin nội bộ vào nội dung trả về.

## 10. Validation group cho các luồng khác nhau

Cùng một DTO có thể được dùng ở nhiều giai đoạn. Ví dụ khi tạo user, `password` bắt buộc; khi cập nhật profile, password có thể không được gửi.

Khai báo group:

```java
public interface Create {}
public interface Update {}
```

Đặt constraint theo group:

```java
public class UserCommand {
    @NotBlank(groups = {Create.class, Update.class})
    private String name;

    @NotBlank(groups = Create.class)
    @Size(min = 12, groups = Create.class)
    private String password;
}
```

Chọn group khi validate:

```java
validator.validate(command, Create.class);
validator.validate(command, Update.class);
```

Nếu muốn luôn chạy constraint thuộc group `Default` cùng một group khác, có thể dùng group sequence hoặc khai báo nhóm kế thừa `Default` theo cách phù hợp. Đừng giả định `validator.validate(value, Create.class)` tự chạy mọi constraint `Default`; group selection cần được thiết kế rõ ràng.

### 10.1. Group sequence

`@GroupSequence` có thể quy định thứ tự các nhóm, chẳng hạn kiểm tra cấu trúc cơ bản trước rồi mới chạy quy tắc đắt hơn. Khi một nhóm trong sequence có violation, các nhóm sau không được chạy. Dùng sequence khi thứ tự validation có ý nghĩa và muốn tránh thực hiện bước tiếp theo trên object đã không đạt điều kiện trước đó.

## 11. JSON Schema và Bean Validation bổ sung cho nhau

Hai cơ chế có thể diễn đạt một số ràng buộc tương tự, nhưng không có nghĩa phải sao chép toàn bộ mọi rule vào cả hai.

| Tiêu chí | JSON Schema | Bean Validation |
|---|---|---|
| Đầu vào | Tài liệu JSON/JsonNode | Object Java |
| Thời điểm | Có thể trước data binding | Sau khi object được tạo hoặc trong lifecycle validation |
| Required key | Có keyword `required` | Thường chỉ thấy trạng thái object sau binding; thiếu và null có thể đã bị gộp |
| Kiểu JSON | `type`, `oneOf`, `anyOf`, ... | Kiểu Java và constraint trên giá trị |
| String/number limits | `minLength`, `maximum`, ... | `@Size`, `@Min`, `@DecimalMax`, ... |
| Nested structure | `properties`, `items`, `$ref` | `@Valid` và container element constraints |
| Cross-field rule | `if/then/else`, composition, schema logic | Class-level constraint hoặc method validation |
| Chia sẻ giữa nhiều ngôn ngữ | Tốt, schema là artifact độc lập | Gắn với hệ sinh thái Java/Jakarta |
| Quy tắc nghiệp vụ phụ thuộc service/database | Không phù hợp nếu cần truy vấn trạng thái runtime | Có thể đặt ở service/domain layer; constraint validator chỉ nên dùng dependency có chủ đích |

Một phân chia thực tế:

- JSON Schema xác nhận cấu trúc public contract và các giới hạn có thể mô tả độc lập với Java.
- Bean Validation xác nhận các constraint của DTO Java, bao gồm nested object và cross-field rule.
- Service/domain layer kiểm tra quy tắc cần dữ liệu bên ngoài như email đã tồn tại, tài khoản có quyền, số dư đủ hoặc trạng thái hiện tại cho phép chuyển đổi.

Không nên đưa mọi quy tắc nghiệp vụ vào Bean Validation chỉ vì có thể viết một `ConstraintValidator`. Các kiểm tra cần I/O hoặc phụ thuộc transaction thường phù hợp hơn ở service/domain layer.

## 12. Những khác biệt cần xử lý cẩn thận

### 12.1. Missing và null

JSON Schema có thể phân biệt key không xuất hiện với key xuất hiện nhưng null bằng `required` và `type`. Sau khi Jackson bind vào DTO thông thường, cả hai trường hợp có thể cùng trở thành null.

Ví dụ:

```json
{}
```

và:

```json
{"email": null}
```

Nếu DTO chỉ có `String email`, Bean Validation `@NotNull` sẽ thấy null ở cả hai trường hợp. Nếu nghiệp vụ cần phân biệt “không gửi field” với “gửi null để xóa giá trị”, cần giữ presence information, ví dụ:

- Validate `JsonNode`/JSON Schema trước khi bind.
- Dùng wrapper type biểu diễn absent/present/null.
- Dùng custom deserializer hoặc DTO patch có cờ presence.
- Dùng JSON Merge Patch/JSON Patch với semantics đã xác định.

### 12.2. Unknown properties

JSON Schema `additionalProperties` và Jackson `FAIL_ON_UNKNOWN_PROPERTIES` cần thống nhất. Nếu schema cho phép extension nhưng DTO không lưu chúng, dữ liệu có thể bị bỏ hoặc lỗi ở bước binding tùy cấu hình.

### 12.3. Enum values

JSON Schema `enum` có thể từ chối literal mới trước khi Jackson xử lý. Nếu DTO enum dùng `UNKNOWN` fallback, cần quyết định schema có cho phép giá trị mở hay không. Một schema liệt kê tập enum cố định và một DTO chấp nhận mọi giá trị thành `UNKNOWN` là hai chính sách khác nhau.

### 12.4. Format validation

Bean Validation `@Email` và JSON Schema `format: email` không nhất thiết dùng cùng một thuật toán hoặc cùng mức độ nghiêm ngặt. Nếu producer và consumer cần kết quả đồng nhất, hãy định nghĩa test cases chung và xác nhận cấu hình validator của cả hai phía.

### 12.5. Coercion của Jackson

Jackson có thể chuyển một số token sang kiểu Java theo coercion config. JSON Schema thường kiểm tra kiểu JSON gốc. Ví dụ chuỗi `"25"` có thể được Jackson coercion thành integer trong một cấu hình, nhưng schema `type: integer` sẽ từ chối vì giá trị JSON gốc là string.

Nếu hợp đồng yêu cầu kiểu JSON chính xác, hãy validate schema trước khi binding và tránh coercion ngoài ý muốn. Nếu chấp nhận coercion, ghi rõ trong contract và test.

## 13. Tích hợp Bean Validation với Spring hoặc framework

Trong Spring MVC, một request body có thể được deserialize bằng Jackson rồi validate bằng Bean Validation thông qua `@Valid` hoặc `@Validated`:

```java
@RestController
@RequestMapping("/users")
public class UserController {
    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateUserRequest request) {
        userService.create(request);
        return ResponseEntity.noContent().build();
    }
}
```

Framework cần có Bean Validation provider trên classpath và được cấu hình phù hợp. Với Spring Boot, starter validation thường cung cấp tích hợp cần thiết; phiên bản Spring Boot/Jakarta namespace phải tương thích với ứng dụng.

Nếu validation thất bại, framework có thể ném exception như `MethodArgumentNotValidException` (Spring MVC) hoặc exception tương ứng ở stack đang dùng. Nên có exception handler để chuyển lỗi thành response thống nhất.

### 13.1. Jakarta hay javax?

Các phiên bản cũ của Bean Validation dùng namespace `javax.validation.*`. Jakarta Bean Validation 3.0 chuyển sang `jakarta.validation.*`. Không trộn hai namespace trong cùng một model hoặc dependency graph nếu framework chỉ hỗ trợ một thế hệ API.

Ví dụ import Jakarta:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Với project cũ, có thể phải dùng `javax.validation.*` theo phiên bản framework. Hãy xem dependency tree và baseline của framework trước khi chọn import.

## 14. Chuẩn hóa lỗi trả về client

JSON Schema validator và Bean Validation có thể trả lỗi theo format khác nhau. API nên chuyển chúng về một cấu trúc response nhất quán, ví dụ:

```json
{
  "type": "https://example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "errors": [
    {
      "path": "email",
      "code": "NotBlank",
      "message": "Email is required"
    },
    {
      "path": "age",
      "code": "Minimum",
      "message": "Age must be zero or greater"
    }
  ]
}
```

Các field có thể gồm:

- `path`: JSON Pointer hoặc Bean Validation property path.
- `code`: mã lỗi ổn định để client xử lý.
- `message`: nội dung hiển thị đã được chuẩn hóa/localize.
- `rejectedValue`: chỉ thêm nếu an toàn và cần thiết; không trả password/token.

JSON Schema thường dùng JSON Pointer để chỉ vị trí trong document; Bean Validation dùng property path. Có thể chuẩn hóa cả hai về một quy ước như JSON Pointer hoặc path dạng `address.postalCode`.

Không nên trả stack trace, tên class nội bộ hoặc toàn bộ JSON đầu vào trong response lỗi production.

## 15. Ví dụ pipeline hoàn chỉnh trong Java thuần

Ví dụ sau minh họa thứ tự parse tree, schema validation, bind và Bean Validation. Phần `schemaValidator` đại diện cho adapter quanh thư viện JSON Schema đã chọn:

```java
public class RequestPipeline {
    private final ObjectMapper mapper;
    private final JsonSchemaValidator schemaValidator;
    private final Validator beanValidator;

    public RequestPipeline(
            ObjectMapper mapper,
            JsonSchemaValidator schemaValidator,
            Validator beanValidator) {
        this.mapper = mapper;
        this.schemaValidator = schemaValidator;
        this.beanValidator = beanValidator;
    }

    public <T> T readAndValidate(
            String json,
            Class<T> targetType) throws JsonProcessingException {

        JsonNode tree = mapper.readTree(json);

        schemaValidator.validate(tree);

        T value = mapper.treeToValue(tree, targetType);

        Set<ConstraintViolation<T>> violations = beanValidator.validate(value);
        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        return value;
    }
}
```

Interface adapter:

```java
public interface JsonSchemaValidator {
    void validate(JsonNode document);
}
```

Adapter giữ cho code nghiệp vụ không phụ thuộc trực tiếp API của một thư viện schema cụ thể. Nó cũng là nơi chuyển schema validation messages thành exception hoặc lỗi có cấu trúc.

Trong ứng dụng production, nên phân biệt exception cú pháp JSON, lỗi schema, lỗi binding và lỗi Bean Validation để response/telemetry có mã phân loại phù hợp. Không gom tất cả thành một lỗi “invalid JSON” chung chung.

## 16. Hiệu năng và vòng đời

Validation có chi phí. Một số nguyên tắc:

- Tạo `ObjectMapper`, `ValidatorFactory`, `Validator` và schema đã biên dịch ở giai đoạn khởi tạo, sau đó tái sử dụng theo lifecycle của ứng dụng.
- Tránh đọc cùng request body nhiều lần; parse thành `JsonNode` một lần nếu cần schema validation trước binding.
- Với payload lớn, cân nhắc JSON Schema validator có hỗ trợ streaming nếu yêu cầu hiệu năng/bộ nhớ đòi hỏi; tree model giữ toàn bộ document trong bộ nhớ.
- Giới hạn kích thước request và độ sâu JSON ở tầng HTTP/parser phù hợp để tránh payload quá lớn hoặc lồng nhau bất thường.
- Tránh constraint validator thực hiện truy vấn database cho từng property hoặc tạo N+1 query.
- Dùng validation groups hoặc pipeline theo giai đoạn nếu có các bước kiểm tra đắt hơn.
- Cache schema theo version và thay đổi schema có kiểm soát.

Không nên bỏ validation chỉ để tăng throughput khi dữ liệu không đáng tin cậy. Hãy đo bằng payload đại diện và tối ưu vị trí/loại validation phù hợp.

## 17. Khi nào chỉ cần một cơ chế?

**Chỉ dùng Bean Validation** có thể đủ khi:

- Hợp đồng chỉ được tiêu thụ trong hệ sinh thái Java.
- DTO Java là nguồn định nghĩa contract chính.
- Các constraint tập trung vào giá trị object, nested bean và quy tắc nhiều field.
- Không cần chia sẻ schema độc lập với client hoặc service khác.

**Chỉ dùng JSON Schema** có thể đủ khi:

- Cần kiểm tra document JSON độc lập với Java.
- Schema được chia sẻ giữa nhiều ngôn ngữ hoặc consumer.
- Quy tắc chủ yếu là cấu trúc, required, type, enum và giới hạn giá trị JSON.
- Sau validation, hệ thống chuyển sang một representation không cần Bean Validation.

**Dùng cả hai** khi:

- Public API có schema contract được version hóa.
- Backend vẫn cần constraint trên DTO và object lồng nhau.
- Có cross-field rule hoặc custom constraint thuộc model Java.
- Cần phát hiện cả lỗi document lẫn lỗi object/domain.

Các quy tắc cần dữ liệu bên ngoài như quyền truy cập, tồn tại trong database, trạng thái giao dịch hoặc giới hạn theo tài khoản nên được kiểm tra ở service/domain layer sau khi request vượt qua validation đầu vào.

## 18. Những lỗi thường gặp

**Cho rằng Jackson deserialize thành công nghĩa là request hợp lệ.** Parse chỉ xác nhận JSON có thể được ánh xạ; cần schema/Bean Validation hoặc kiểm tra nghiệp vụ cho các ràng buộc khác.

**Dùng Bean Validation để phát hiện field JSON bị thiếu nhưng DTO đã mất presence information.** `@NotNull` không phân biệt key không gửi với key gửi null trong DTO thông thường. Dùng JSON Schema hoặc biểu diễn presence riêng khi cần phân biệt.

**Chỉ dùng `@Valid` mà quên `@NotNull`.** `@Valid` cascade khi object con tồn tại; nó không tự yêu cầu property phải có.

**Dùng `@Size` để bắt chuỗi không null.** `@Size` thường chấp nhận null. Kết hợp `@NotNull` hoặc `@NotBlank` tùy kiểu và ý nghĩa.

**Cho rằng `format: email` luôn được kiểm tra.** Format assertion phụ thuộc dialect/cấu hình validator. Bật format validation hoặc dùng constraint riêng và test.

**Nhầm `required` với cấm null.** JSON Schema `required` chỉ yêu cầu key xuất hiện; type phải loại null nếu null không hợp lệ.

**Chỉ tắt `FAIL_ON_UNKNOWN_PROPERTIES` mà không kiểm tra schema.** Field lạ có thể bị bỏ âm thầm. Quyết định rõ ignore, capture hay reject.

**Schema cho phép additional properties nhưng DTO không lưu chúng.** Binding có thể bỏ hoặc fail tùy Jackson config. Dùng `@JsonAnySetter` nếu cần giữ extension.

**Schema enum và enum fallback mâu thuẫn.** Schema có thể từ chối giá trị trước khi Jackson ánh xạ thành `UNKNOWN`. Đồng bộ contract và chính sách tương thích.

**Dùng constraint validator để truy vấn database trong mỗi field.** Việc này làm validation phụ thuộc I/O và có thể tạo tải lớn. Đưa kiểm tra nghiệp vụ phù hợp sang service/domain layer.

**Tạo ValidatorFactory hoặc compile schema trên mỗi request.** Tái sử dụng các đối tượng đã khởi tạo theo lifecycle phù hợp.

**Trả rejected value nhạy cảm trong lỗi validation.** Chuẩn hóa thông báo và loại bỏ password, token hoặc thông tin riêng tư.

## 19. Quy trình triển khai

1. Xác định hợp đồng JSON cần chia sẻ và version hóa.
2. Dùng JSON Schema cho các ràng buộc document như required, type, enum, range, array, nested structure và additional properties nếu phù hợp.
3. Chọn đúng dialect JSON Schema và cấu hình format assertion của validator.
4. Parse request một lần thành `JsonNode` nếu cần validate schema trước binding.
5. Chỉ bind DTO khi document vượt qua schema validation.
6. Đặt Bean Validation constraint trên DTO; dùng `@Valid` cho object lồng nhau và container element.
7. Dùng class-level constraint cho quy tắc nhiều field, nhưng chuyển kiểm tra phụ thuộc database/service sang tầng nghiệp vụ.
8. Phân biệt missing, null, empty và unknown property/enum theo hợp đồng.
9. Chuẩn hóa lỗi schema và Bean Validation thành response có path/code/message nhất quán.
10. Cache schema, mapper và Validator theo lifecycle ứng dụng.
11. Viết test cho JSON sai cấu trúc, field thiếu, null, enum lạ, nested violations, cross-field violations và coercion.
12. Đồng bộ schema, DTO và client contract trong quy trình versioning/release.

## 20. Kiểm thử các lớp validation

Nên tách test theo nơi phát hiện lỗi:

| Test | Thành phần được kiểm tra |
|---|---|
| JSON sai cú pháp | Jackson parser |
| Thiếu key `email` | JSON Schema `required` |
| `email` là number thay vì string | JSON Schema type hoặc Jackson binding |
| `email` là chuỗi rỗng | Schema `minLength` và/hoặc Bean Validation `@NotBlank` |
| `age` âm | Schema `minimum` và/hoặc Bean Validation `@Min` |
| Unknown property | Schema `additionalProperties` và Jackson unknown-property policy |
| Enum literal không có trong contract | Schema `enum` và enum deserializer policy |
| Address thiếu `city` | Schema nested `required` và Bean Validation cascade |
| `endDate` trước `startDate` | Class-level Bean Validation constraint hoặc schema conditional rule |
| Email đã tồn tại trong database | Service/domain validation |

Nếu cùng một quy tắc xuất hiện trong schema và Bean Validation, test cần xác nhận cả hai không mâu thuẫn. Có thể giữ bộ test contract JSON làm nguồn kiểm tra chung để các implementation khác ngôn ngữ cũng dùng được.

## Kết luận

Jackson đảm nhiệm parse và data binding; JSON Schema kiểm tra tài liệu JSON theo contract độc lập với Java; Bean Validation kiểm tra object Java sau khi deserialize. JSON Schema phù hợp với required key, JSON type, enum, cấu trúc lồng nhau và property bổ sung. Bean Validation phù hợp với constraint trên property, phần tử collection, object lồng nhau và quy tắc nhiều field. Khi phối hợp, hãy validate schema trước binding nếu cần giữ sự khác biệt giữa missing và null, sau đó chạy Bean Validation trên DTO. Giữ các kiểm tra phụ thuộc database hoặc trạng thái hệ thống ở service/domain layer, chuẩn hóa lỗi trả về client và tái sử dụng mapper, validator cùng schema đã biên dịch.
