# Phân biệt annotation ánh xạ và ràng buộc validation thực tế

Khi xây dựng API nhận JSON, một DTO Java thường có nhiều annotation cùng lúc. Một số annotation thuộc Jackson, dùng để quyết định JSON được đọc hoặc ghi như thế nào. Một số annotation khác thuộc Jakarta Bean Validation, dùng để kiểm tra dữ liệu sau khi đã được ánh xạ thành object Java.

Hai nhóm annotation có thể xuất hiện cạnh nhau trên cùng một field, nhưng chúng giải quyết hai vấn đề khác nhau:

- **Annotation ánh xạ (mapping):** mô tả tên property, kiểu JSON, định dạng, cách chuyển đổi, null handling, subtype hoặc việc property có tham gia serialize/deserialize hay không.
- **Ràng buộc validation:** mô tả dữ liệu nào được xem là hợp lệ theo quy tắc của ứng dụng, ví dụ chuỗi không được để trống, số tiền phải dương, email phải đúng định dạng hoặc danh sách không vượt quá số phần tử cho phép.

Jackson có thể đọc JSON hợp lệ về cú pháp và tạo được DTO, nhưng object đó vẫn có thể vi phạm quy tắc nghiệp vụ. Ngược lại, một giá trị có vẻ hợp lệ theo validation cũng không thể được kiểm tra nếu Jackson không ánh xạ được JSON vào kiểu Java trước đó.

Vì vậy, cần tách rõ các giai đoạn: parse JSON, ánh xạ JSON thành object, kiểm tra validation và cuối cùng mới xử lý nghiệp vụ.

## 1. Mapping và validation trả lời hai câu hỏi khác nhau

Giả sử API nhận yêu cầu tạo tài khoản:

```json
{
  "display_name": "An Nguyen",
  "email_address": "an@example.com",
  "age": 17
}
```

Jackson cần biết:

- `display_name` ánh xạ vào property Java nào?
- `email_address` tương ứng với `email` hay một tên khác?
- `age` là JSON number hay string?
- Có cần chuyển đổi định dạng ngày, enum hoặc kiểu tùy biến không?

Đó là các câu hỏi về mapping.

Ứng dụng cần biết thêm:

- Tên hiển thị có được để trống không?
- Email có đúng định dạng và có bắt buộc không?
- Người đăng ký có đủ tuổi theo quy định dịch vụ không?
- Độ dài tên có nằm trong giới hạn không?

Đó là các câu hỏi về validation và nghiệp vụ.

Một DTO có thể kết hợp cả hai nhóm:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class CreateAccountRequest {
    @JsonProperty("display_name")
    @NotBlank
    @Size(max = 80)
    private String displayName;

    @JsonProperty("email_address")
    @NotBlank
    @Email
    private String email;

    @Min(18)
    private Integer age;

    // Getter và setter...
}
```

`@JsonProperty` nói với Jackson tên JSON của property. `@NotBlank`, `@Size`, `@Email` và `@Min` là ràng buộc validation. Việc Jackson gán được giá trị vào field không có nghĩa các ràng buộc này đã được kiểm tra.

## 2. Những annotation Jackson thường gặp thuộc nhóm ánh xạ

Các annotation dưới đây điều khiển cách Jackson đọc hoặc ghi JSON. Chúng không tự động thay thế Bean Validation.

| Annotation | Vai trò chính | Ví dụ |
| --- | --- | --- |
| `@JsonProperty` | Đặt tên JSON hoặc chỉ định property tham gia mapping | Java `displayName` ↔ JSON `display_name` |
| `@JsonAlias` | Chấp nhận tên thay thế khi deserialize | Nhận `email`, `email_address` hoặc `mail` |
| `@JsonIgnore` | Bỏ qua property trong mapping theo cấu hình annotation | Không nhận/ghi field nội bộ |
| `@JsonInclude` | Quy định khi nào property được ghi ra JSON | Bỏ null hoặc empty khi serialize |
| `@JsonFormat` | Quy định hình thức biểu diễn/đọc một số kiểu | Định dạng ngày giờ hoặc shape số |
| `@JsonCreator` | Chỉ định constructor/factory dùng để tạo object | Tạo DTO bất biến từ JSON |
| `@JsonSetter` | Tùy chỉnh cách gán property, bao gồm null handling | Từ chối explicit JSON null |
| `@JsonDeserialize` | Chọn deserializer hoặc cách chuyển đổi đầu vào | Đọc kiểu tùy biến |
| `@JsonSerialize` | Chọn serializer đầu ra | Ghi value theo wire format riêng |
| `@JsonTypeInfo` | Cấu hình thông tin subtype khi xử lý đa hình | Discriminator `kind` |

Ví dụ, `@JsonFormat` có thể yêu cầu ngày được đọc theo pattern cụ thể. Nếu chuỗi không parse được, Jackson báo lỗi mapping/format. Điều đó không giống một ràng buộc nghiệp vụ như “ngày đặt lịch phải nằm trong tương lai”. Pattern định dạng xác định chuỗi có thể chuyển thành kiểu ngày hay không; validation xác định ngày đã chuyển đổi có được chấp nhận hay không.

## 3. @JsonProperty không có nghĩa là dữ liệu bắt buộc hợp lệ

`@JsonProperty` thường được dùng để đặt tên property trong JSON:

```java
public class CustomerRequest {
    @JsonProperty("customer_name")
    private String name;
}
```

Jackson dùng tên `customer_name` khi đọc/ghi theo cấu hình phù hợp. Annotation này không tự bảo đảm:

- Property phải xuất hiện trong JSON.
- Giá trị không được null.
- Chuỗi không được rỗng hoặc chỉ chứa khoảng trắng.
- Giá trị phải thỏa quy tắc nghiệp vụ.

Nếu cần bắt buộc giá trị sau khi ánh xạ, dùng ràng buộc validation phù hợp:

```java
@JsonProperty("customer_name")
@NotBlank
private String name;
```

Ngay cả khi property có `@NotBlank`, validation chỉ chạy khi ứng dụng thực sự gọi Bean Validation, ví dụ thông qua `@Valid` trong Spring MVC hoặc `Validator.validate()` trong code Java. Chỉ gọi `ObjectMapper.readValue()` không tự động chạy toàn bộ constraint trên DTO.

### 3.1. required của @JsonProperty có phạm vi hạn chế

`@JsonProperty(required = true)` thường được hiểu nhầm là một validation bắt buộc tổng quát:

```java
@JsonProperty(value = "customer_name", required = true)
private String name;
```

Thuộc tính `required` của Jackson chủ yếu có ý nghĩa với creator properties, chẳng hạn tham số constructor hoặc factory method được Jackson dùng để tạo object. Nó không phải cơ chế validation tổng quát bảo đảm mọi field/getter/setter thông thường luôn có mặt và khác null.

Nếu hợp đồng yêu cầu một giá trị bắt buộc, hãy dùng Bean Validation như `@NotNull` hoặc `@NotBlank` và bảo đảm validation được kích hoạt. Nếu cần phân biệt property bị thiếu với property có JSON null ngay trong quá trình deserialize, hãy dùng creator/null handling phù hợp với hợp đồng và kiểm thử cả hai trường hợp.

## 4. @JsonAlias chỉ là tên đầu vào thay thế

`@JsonAlias` cho phép Jackson chấp nhận nhiều tên JSON cho cùng một property khi deserialize:

```java
public class CustomerRequest {
    @JsonProperty("email_address")
    @JsonAlias({"email", "mail"})
    @NotBlank
    @Email
    private String email;
}
```

Các payload sau có thể ánh xạ vào cùng property `email`:

```json
{"email_address":"an@example.com"}
```

```json
{"email":"an@example.com"}
```

```json
{"mail":"an@example.com"}
```

Alias chủ yếu phục vụ chiều đọc. Khi serialize, tên chính theo cấu hình property được sử dụng. `@JsonAlias` không kiểm tra nội dung email và không làm cho property trở thành bắt buộc.

Đây là cách hỗ trợ tương thích ngược khi API đổi tên field. Validation vẫn áp dụng trên property Java sau khi Jackson đã gán giá trị, bất kể input dùng alias nào.

## 5. @JsonIgnore và @JsonInclude không phải constraint

`@JsonIgnore` điều khiển việc property có tham gia quá trình ánh xạ hay không:

```java
@JsonIgnore
private String internalToken;
```

Nó không có nghĩa giá trị của `internalToken` hợp lệ hay không hợp lệ. Nếu field bị ignore, Jackson có thể không đọc hoặc ghi field đó theo cấu hình annotation; Bean Validation không biến `@JsonIgnore` thành quy tắc kiểm tra dữ liệu.

`@JsonInclude` điều khiển việc serialize property, ví dụ:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
private String middleName;
```

Nếu `middleName` là null, property có thể bị bỏ khỏi JSON đầu ra. Điều này không có nghĩa null bị cấm khi nhận JSON. Inclusion là chính sách output; constraint như `@NotNull` là chính sách validation trên object.

Một DTO có thể có `@JsonInclude(NON_NULL)` nhưng vẫn chấp nhận null đầu vào nếu không có validation hoặc null handling khác. Hai hành vi cần được thiết kế riêng.

## 6. @JsonFormat kiểm tra khả năng parse, không kiểm tra quy tắc nghiệp vụ

Ví dụ property ngày:

```java
public class BookingRequest {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    private LocalDate bookingDate;
}
```

`@JsonFormat` giúp Jackson hiểu cách đọc/ghi giá trị ngày theo pattern. Một chuỗi sai định dạng như `"31/12/2026"` có thể không parse được theo `yyyy-MM-dd`.

Nhưng một ngày parse thành công như `"2020-01-01"` vẫn có thể không hợp lệ nếu quy tắc nghiệp vụ yêu cầu ngày đặt lịch phải ở hiện tại hoặc tương lai. Ràng buộc như `@FutureOrPresent` mới biểu diễn điều kiện đó:

```java
@JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
@FutureOrPresent
private LocalDate bookingDate;
```

Hai annotation làm hai việc khác nhau: Jackson chuyển chuỗi thành `LocalDate`; Bean Validation so sánh ngày đã chuyển đổi với thời điểm hiện tại.

## 7. @JsonSetter nulls và sự khác biệt giữa thiếu với null

Một property có thể rơi vào ba trạng thái khác nhau:

```json
{}
```

Property không xuất hiện.

```json
{"name": null}
```

Property xuất hiện với JSON null.

```json
{"name": ""}
```

Property xuất hiện với chuỗi rỗng.

`@JsonSetter` có thể cấu hình cách xử lý explicit null:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class CreateUserRequest {
    @JsonSetter(nulls = Nulls.FAIL)
    private String name;
}
```

Với cấu hình trên, khi JSON gửi rõ `"name": null`, Jackson từ chối trong quá trình deserialize. Nhưng nếu JSON bỏ hẳn `name`, setter có thể không được gọi và property có thể giữ giá trị mặc định hoặc giá trị khởi tạo. Do đó, `Nulls.FAIL` không thay thế việc kiểm tra property bắt buộc phải xuất hiện.

Các lựa chọn `Nulls` thường dùng:

| Giá trị | Ý nghĩa tổng quát |
| --- | --- |
| `SET` | Gán null theo hành vi thông thường |
| `SKIP` | Bỏ qua việc gán khi input là null |
| `FAIL` | Báo lỗi khi gặp explicit null |
| `AS_EMPTY` | Dùng empty value do deserializer cung cấp |
| `DEFAULT` | Dùng chính sách mặc định ở cấp property/configuration |

Null handling là một phần của quá trình mapping. Validation như `@NotNull` kiểm tra giá trị Java sau khi object đã được tạo. Tùy mục tiêu, có thể dùng cả hai: `Nulls.FAIL` để từ chối explicit null sớm và `@NotNull` để bảo vệ object ở mọi luồng tạo khác.

## 8. Jackson coercion cũng không phải validation nghiệp vụ

Jackson có thể chuyển đổi một số kiểu JSON sang kiểu Java theo coercion rules hoặc cấu hình `CoercionConfig`. Ví dụ, một số cấu hình có thể cho phép đọc chuỗi số thành integer hoặc xử lý empty string thành null/empty value.

Giả sử:

```json
{"quantity":"12"}
```

Nếu coercion cho phép, Jackson có thể ánh xạ chuỗi `"12"` thành `int` hoặc `Integer`. Điều đó chỉ cho biết dữ liệu có thể chuyển đổi theo chính sách mapper; nó không bảo đảm quantity lớn hơn 0 hoặc không vượt giới hạn kho hàng.

Ràng buộc nghiệp vụ cần được mô tả riêng:

```java
@Positive
@Max(1000)
private Integer quantity;
```

Nếu hợp đồng yêu cầu JSON number chứ không chấp nhận string, hãy cấu hình coercion chặt hơn hoặc dùng kiểu/deserialize policy phù hợp. Validation không nhất thiết phát hiện được sự khác biệt giữa number `12` và string `"12"` sau khi Jackson đã coercion cả hai thành cùng một `Integer`.

Đây là lý do cần quyết định rõ hợp đồng ở cả hai tầng:

- Jackson mapping quy định dạng JSON nào được chấp nhận và chuyển đổi thành kiểu Java.
- Validation quy định giá trị Java nào được phép tiếp tục vào nghiệp vụ.

## 9. Jakarta Bean Validation là gì?

Jakarta Bean Validation định nghĩa API chuẩn để khai báo và thực thi các ràng buộc trên object Java. Các annotation thường được import từ `jakarta.validation.constraints`.

Các constraint phổ biến:

| Constraint | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị Java không được null |
| `@NotBlank` | Chuỗi không null và phải có ít nhất một ký tự không phải whitespace |
| `@NotEmpty` | Chuỗi/collection/map/array không null và không rỗng |
| `@Size(min, max)` | Giới hạn kích thước chuỗi hoặc số phần tử của container |
| `@Min` / `@Max` | Giới hạn số nguyên theo cận dưới/trên |
| `@DecimalMin` / `@DecimalMax` | Giới hạn số thập phân theo cận dưới/trên |
| `@Positive` / `@PositiveOrZero` | Số phải dương hoặc không âm |
| `@Negative` / `@NegativeOrZero` | Số phải âm hoặc không dương |
| `@Email` | Kiểm tra chuỗi theo quy tắc email của provider |
| `@Pattern` | Chuỗi phải khớp regular expression |
| `@Past` / `@PastOrPresent` | Ngày/thời điểm phải ở quá khứ hoặc không muộn hơn hiện tại |
| `@Future` / `@FutureOrPresent` | Ngày/thời điểm phải ở tương lai hoặc không sớm hơn hiện tại |
| `@AssertTrue` / `@AssertFalse` | Giá trị boolean phải đúng/sai theo constraint |

Constraint có ý nghĩa riêng. Ví dụ, `@Email` không thay thế `@NotBlank`: nhiều provider xem null hoặc chuỗi rỗng là hợp lệ đối với `@Email`, vì việc bắt buộc nhập giá trị là nhiệm vụ của constraint khác. Nếu email vừa bắt buộc vừa phải đúng định dạng, thường kết hợp `@NotBlank` và `@Email`.

## 10. Ví dụ DTO kết hợp mapping và validation

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class CreateAccountRequest {
    @JsonProperty("display_name")
    @NotBlank(message = "Tên hiển thị không được để trống")
    @Size(max = 80, message = "Tên hiển thị không được vượt quá 80 ký tự")
    private String displayName;

    @JsonProperty("email_address")
    @JsonAlias("email")
    @NotBlank(message = "Email là bắt buộc")
    @Email(message = "Email không đúng định dạng")
    private String email;

    @JsonProperty("age")
    @NotNull(message = "Tuổi là bắt buộc")
    @Min(value = 18, message = "Tuổi phải từ 18 trở lên")
    private Integer age;

    // Getter và setter...
}
```

Các annotation Jackson xác định cách JSON được ánh xạ:

- `display_name` gắn với `displayName`.
- `email_address` là tên chính, `email` là alias khi đọc.
- `age` ánh xạ vào property số nguyên.

Các constraint xác định dữ liệu sau mapping có hợp lệ không:

- Tên không được null, rỗng hoặc chỉ có khoảng trắng.
- Tên không vượt quá 80 ký tự.
- Email phải có giá trị và đúng định dạng.
- Tuổi phải được cung cấp và ít nhất là 18.

Nếu JSON không thể parse thành kiểu Java, lỗi xảy ra trước validation. Nếu JSON parse và bind thành object nhưng `age = 16`, validation sẽ báo vi phạm `@Min`.

## 11. @Valid để kiểm tra object lồng nhau

Constraint trên DTO con không tự động được duyệt chỉ vì object cha có property đó. Cần cascade validation bằng `@Valid`:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public class CreateOrderRequest {
    @NotNull
    @Valid
    private CustomerRequest customer;

    @NotNull
    @Valid
    private AddressRequest shippingAddress;
}
```

DTO con:

```java
public class CustomerRequest {
    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;
}
```

Khi validator kiểm tra `CreateOrderRequest`, `@Valid` yêu cầu đi tiếp vào `CustomerRequest` và `AddressRequest` để kiểm tra constraint bên trong.

Với collection, có thể kết hợp container element validation:

```java
public class CreateOrderRequest {
    @NotEmpty
    private List<@NotNull @Valid OrderLineRequest> lines;
}
```

Ở đây:

- `@NotEmpty` yêu cầu danh sách có ít nhất một phần tử.
- `@NotNull` trên type argument yêu cầu mỗi phần tử không null.
- `@Valid` cascade vào từng `OrderLineRequest`.

Nếu thiếu `@Valid`, constraint trong DTO con có thể không được kiểm tra khi chỉ validate object cha.

## 12. Gọi Bean Validation trực tiếp trong Java

Bean Validation không phụ thuộc vào Jackson. Ứng dụng có thể tạo object bằng constructor, builder, database mapper hoặc test rồi gọi validator.

Ví dụ:

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.ConstraintViolation;

import java.util.Set;

try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();

    CreateAccountRequest request = new CreateAccountRequest();
    request.setDisplayName("   ");
    request.setEmail("not-an-email");
    request.setAge(16);

    Set<ConstraintViolation<CreateAccountRequest>> violations =
            validator.validate(request);

    for (ConstraintViolation<CreateAccountRequest> violation : violations) {
        System.out.printf(
                "%s: %s%n",
                violation.getPropertyPath(),
                violation.getMessage()
        );
    }
}
```

`Validator.validate()` trả về tập `ConstraintViolation`. Nếu tập rỗng, object không vi phạm các constraint được áp dụng trong validation group hiện tại. Nếu có phần tử, mỗi violation chứa property path, message, invalid value và constraint descriptor.

Để thực thi validation, ứng dụng cần có Bean Validation provider trên classpath. Chỉ thêm annotation API mà không có provider triển khai có thể khiến việc tạo `ValidatorFactory` thất bại.

## 13. Validation trong Spring MVC sau khi Jackson deserialize

Trong Spring MVC, một request body JSON thường đi qua các bước:

```text
HTTP request body
       │
       ▼
HttpMessageConverter (Jackson)
       │ parse + deserialize
       ▼
CreateAccountRequest
       │
       ▼
@Valid / Bean Validation
       │
       ├── Có constraint violation → trả lỗi validation
       │
       └── Hợp lệ → gọi controller/service
```

Controller có thể khai báo:

```java
@PostMapping("/accounts")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateAccountRequest request
) {
    accountService.create(request);
    return ResponseEntity.noContent().build();
}
```

Spring dùng message converter để deserialize JSON trước. Khi object được tạo, `@Valid` kích hoạt Bean Validation trên request object. Nếu constraint vi phạm, Spring MVC thường ném `MethodArgumentNotValidException` và trả phản hồi lỗi validation theo cấu hình ứng dụng.

Nếu JSON sai cú pháp hoặc không ánh xạ được vào DTO, lỗi xảy ra ở bước message conversion trước khi validation có thể chạy. Trong Spring, lỗi đọc body thường được thể hiện bằng `HttpMessageNotReadableException` với nguyên nhân Jackson bên dưới.

### 13.1. Phụ thuộc validation trong Spring Boot

Với Spring Boot, cần có starter validation phù hợp với phiên bản ứng dụng, ví dụ:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Spring Boot 3 sử dụng namespace `jakarta.validation.*`; dự án Spring Boot 2 cũ thường sử dụng `javax.validation.*`. Không trộn annotation API của hai namespace trong cùng một ứng dụng nếu dependency stack không hỗ trợ chúng.

`@Valid` là annotation chuẩn của Jakarta Bean Validation dùng để cascade. `@Validated` là annotation của Spring, thường được dùng khi cần validation group hoặc method validation theo cơ chế Spring. Với một request DTO đơn giản, `@Valid` trên `@RequestBody` thường là đủ.

## 14. @Valid và @Validated khác nhau

| Annotation | Nguồn | Vai trò thường gặp |
| --- | --- | --- |
| `@Valid` | Jakarta Validation | Kích hoạt cascade validation trên object/field lồng nhau; dùng được trong nhiều tích hợp như Spring MVC |
| `@Validated` | Spring Framework | Kích hoạt validation trong Spring và hỗ trợ chỉ định validation groups; thường dùng trên bean/service hoặc method |

Ví dụ dùng group:

```java
public interface CreateGroup {}
public interface UpdateGroup {}

public class UserRequest {
    @NotBlank(groups = CreateGroup.class)
    private String username;
}
```

Controller hoặc service có thể dùng cơ chế Spring hỗ trợ để chọn group phù hợp. Nếu chỉ dùng `@Valid` mà không cấu hình group khác, validation thường chạy với `Default` group.

Validation group hữu ích khi cùng một DTO có quy tắc khác nhau cho create và update. Tuy nhiên, nếu quy tắc khác nhau quá nhiều, DTO riêng cho từng use case thường dễ hiểu hơn.

## 15. Phân biệt property bị thiếu, null, empty và blank trong validation

Các trạng thái sau không giống nhau:

| Giá trị Java sau mapping | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `null` | Vi phạm | Vi phạm | Vi phạm |
| `""` | Hợp lệ | Vi phạm | Vi phạm |
| `"   "` | Hợp lệ | Hợp lệ theo kiểm tra độ dài thông thường | Vi phạm |
| `"An"` | Hợp lệ | Hợp lệ | Hợp lệ |

`@NotEmpty` kiểm tra không null và kích thước lớn hơn 0; chuỗi chỉ có whitespace vẫn có độ dài lớn hơn 0. `@NotBlank` dành cho chuỗi và yêu cầu có ít nhất một ký tự không phải whitespace.

Property bị thiếu trong JSON không phải một giá trị Java riêng biệt sau khi object đã được tạo. Nếu DTO field không được gán, nó thường giữ giá trị mặc định:

- Reference type thường là `null` nếu không có giá trị khởi tạo.
- Primitive `int` mặc định là `0`.
- Primitive `boolean` mặc định là `false`.

Do đó, `@NotNull` trên `Integer` có thể phát hiện field thiếu sau khi mapping vì giá trị là null; `@NotNull` trên primitive `int` không thể phân biệt field thiếu với giá trị `0`. Nếu cần phân biệt, dùng wrapper type (`Integer`, `Boolean`) hoặc creator/property presence handling phù hợp.

## 16. @NotNull không đồng nghĩa với @JsonSetter(nulls = FAIL)

Hai annotation này có thời điểm và phạm vi khác nhau:

```java
@JsonSetter(nulls = Nulls.FAIL)
@NotNull
private String reference;
```

- `@JsonSetter(nulls = FAIL)` từ chối explicit JSON null trong quá trình Jackson deserialize property.
- `@NotNull` kiểm tra giá trị Java sau khi object đã được tạo và Bean Validation chạy.

Nếu field bị thiếu, `@JsonSetter(nulls = FAIL)` không nhất thiết được kích hoạt vì setter không nhận explicit null. `@NotNull` có thể phát hiện giá trị còn null khi validator kiểm tra object.

Kết hợp hai cơ chế có thể hữu ích nếu muốn lỗi null bị phát hiện sớm trong mapping và vẫn muốn bảo vệ object khi được tạo từ các nguồn khác. Nhưng nếu chỉ cần kiểm tra DTO sau khi deserialize, Bean Validation có thể đủ.

## 17. Ràng buộc cấp class và quy tắc nghiệp vụ liên quan nhiều field

Không phải mọi quy tắc đều thuộc một field. Ví dụ `startDate` phải trước `endDate`, hoặc ít nhất một trong hai trường `phone` và `email` phải có giá trị.

Có thể dùng class-level constraint với annotation tùy biến hoặc một số constraint chuẩn phù hợp.

Ví dụ ý tưởng cho ngày bắt đầu/kết thúc:

```java
@ValidDateRange
public class BookingRequest {
    private LocalDate startDate;
    private LocalDate endDate;
}
```

`@ValidDateRange` là constraint do ứng dụng định nghĩa, với `ConstraintValidator` kiểm tra quan hệ giữa hai field. Đây là validation nghiệp vụ; Jackson chỉ cần ánh xạ từng chuỗi ngày thành `LocalDate` theo định dạng đã định.

Không nên cố mã hóa quy tắc liên-field bằng cách đặt nhiều annotation mapping trên từng field. Mapping tập trung vào việc chuyển JSON thành mô hình; validation kiểm tra tính nhất quán của mô hình đó.

## 18. Validation không thay thế kiểm tra bảo mật và quyền nghiệp vụ

Một DTO vượt qua Bean Validation không có nghĩa request được phép thực hiện hành động. Ví dụ:

- `@Positive` xác nhận số tiền lớn hơn 0, nhưng không xác nhận người dùng có quyền thanh toán số tiền đó.
- `@Size(max = 100)` giới hạn kích thước chuỗi, nhưng không ngăn SQL injection nếu code vẫn xây dựng query không an toàn.
- `@Email` kiểm tra hình thức địa chỉ, nhưng không chứng minh mailbox tồn tại hoặc người gửi sở hữu địa chỉ đó.
- `@Pattern` xác nhận chuỗi khớp regex, nhưng không thay thế authorization.

Sau mapping và validation, ứng dụng vẫn cần thực hiện kiểm tra domain, authorization, uniqueness, trạng thái hiện tại và các quy tắc phụ thuộc database/service.

## 19. Thứ tự xử lý và cách phân loại lỗi

Một request JSON thường trải qua các giai đoạn sau:

| Giai đoạn | Thành phần | Ví dụ lỗi |
| --- | --- | --- |
| 1. Đọc byte và parse JSON | Jackson Core | JSON thiếu dấu ngoặc, dấu phẩy hoặc dấu nháy |
| 2. Ánh xạ JSON vào DTO | Jackson Databind | Token không khớp kiểu, ngày không parse được, creator không hợp lệ |
| 3. Validation object | Jakarta Bean Validation | `@NotBlank`, `@Min`, `@Email` bị vi phạm |
| 4. Kiểm tra domain | Service/domain model | Ngày kết thúc trước ngày bắt đầu, tài khoản đã tồn tại |
| 5. Authorization | Security/application | Người dùng không có quyền thao tác |
| 6. Persist và xử lý nghiệp vụ | Repository/service | Vi phạm unique constraint, trạng thái thay đổi đồng thời |

Đừng gộp mọi lỗi thành “JSON không hợp lệ”. JSON có thể hợp lệ về cú pháp nhưng sai kiểu mapping; object có thể map thành công nhưng vi phạm constraint; object có thể vượt validation nhưng vẫn không được phép theo domain hoặc authorization.

## 20. Gợi ý xử lý lỗi trong API

Trong Spring MVC, có thể phân loại lỗi theo exception:

- `HttpMessageNotReadableException`: body không đọc/deserialize được, thường do JSON syntax, token shape hoặc format mapping.
- `MethodArgumentNotValidException`: DTO đã được bind nhưng có constraint violation khi `@Valid` chạy.
- Exception domain riêng: dữ liệu đã qua validation cơ bản nhưng vi phạm quy tắc nghiệp vụ.

Phản hồi API nên giúp client biết field nào sai và vì sao, nhưng tránh trả stack trace hoặc thông tin nội bộ. Ví dụ cấu trúc lỗi validation:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "age",
      "message": "Tuổi phải từ 18 trở lên"
    }
  ]
}
```

Lỗi mapping có thể dùng mã khác, chẳng hạn `INVALID_REQUEST_FORMAT`, vì client cần biết JSON không thể được đọc vào request model. Tách mã lỗi giúp frontend, API consumer và log vận hành xác định đúng giai đoạn xảy ra lỗi.

## 21. Kiểm thử riêng mapping và validation

Nên kiểm thử hai trách nhiệm độc lập.

### 21.1. Test mapping

```java
ObjectMapper mapper = new ObjectMapper();

CreateAccountRequest request = mapper.readValue(
        """
        {
          "display_name": "An Nguyen",
          "email": "an@example.com",
          "age": 20
        }
        """,
        CreateAccountRequest.class
);

assertEquals("An Nguyen", request.getDisplayName());
assertEquals("an@example.com", request.getEmail());
assertEquals(20, request.getAge());
```

Test này xác nhận tên property và alias được ánh xạ đúng. Nó không chứng minh constraint đã được chạy.

### 21.2. Test validation

```java
Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

CreateAccountRequest request = new CreateAccountRequest();
request.setDisplayName("   ");
request.setEmail("not-an-email");
request.setAge(16);

Set<ConstraintViolation<CreateAccountRequest>> violations =
        validator.validate(request);

assertFalse(violations.isEmpty());
```

Test này xác nhận constraint được thực thi trên object Java. Nó không kiểm tra tên JSON hoặc coercion.

### 21.3. Test tích hợp cả hai giai đoạn

Một test tích hợp có thể deserialize JSON thành DTO rồi gọi validator, tương tự pipeline HTTP. Nên có các trường hợp:

- JSON đúng cấu trúc, dữ liệu hợp lệ.
- JSON đúng cấu trúc, dữ liệu vi phạm constraint.
- JSON sai cú pháp.
- JSON đúng cú pháp nhưng token không khớp kiểu Java.
- Property bị thiếu.
- Property explicit null.
- Chuỗi rỗng và chuỗi chỉ có whitespace.
- Alias cũ và tên property mới.

Việc tách test mapping và validation giúp xác định lỗi nằm ở tầng nào khi test thất bại.

## 22. Chọn annotation theo đúng mục đích

| Yêu cầu | Công cụ phù hợp |
| --- | --- |
| Đổi tên field JSON | `@JsonProperty` |
| Chấp nhận tên cũ khi đọc | `@JsonAlias` |
| Bỏ property khỏi JSON mapping | `@JsonIgnore` |
| Không ghi null/empty khi serialize | `@JsonInclude` |
| Đọc ngày theo pattern | `@JsonFormat` |
| Từ chối explicit null khi gán property | `@JsonSetter(nulls = Nulls.FAIL)` |
| Yêu cầu giá trị Java khác null | `@NotNull` |
| Chuỗi bắt buộc có ký tự không phải whitespace | `@NotBlank` |
| Giới hạn độ dài chuỗi hoặc số phần tử | `@Size` |
| Kiểm tra email | `@Email` |
| Kiểm tra số dương | `@Positive` |
| Kiểm tra ngày ở tương lai | `@Future` |
| Kiểm tra object con | `@Valid` |
| Kiểm tra quan hệ giữa nhiều field | Class-level custom constraint hoặc domain validation |

Nếu một annotation không mô tả đúng câu hỏi mà ứng dụng cần trả lời, có thể bạn đang dùng sai tầng.

## 23. Ghi nhớ

- Jackson mapping annotations quyết định cách JSON được parse, đổi tên, chuyển đổi và ghi ra; chúng không tự động chạy Bean Validation.
- `@JsonProperty` đặt tên property; nó không phải constraint bắt buộc hay non-null tổng quát.
- `@JsonProperty(required = true)` chủ yếu có ý nghĩa với creator properties; không thay thế `@NotNull`/`@NotBlank` cho DTO thông thường.
- `@JsonAlias` chấp nhận tên đầu vào thay thế; validation vẫn kiểm tra cùng property Java sau mapping.
- `@JsonInclude` điều khiển output; nó không cấm null đầu vào.
- `@JsonFormat` quy định cách chuyển đổi/biểu diễn; constraint như `@FutureOrPresent` kiểm tra giá trị ngày sau khi parse.
- `@JsonSetter(nulls = FAIL)` xử lý explicit JSON null trong mapping; nó không tự phát hiện mọi property bị thiếu.
- Bean Validation dùng `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@Email` và các constraint khác để kiểm tra object Java.
- `@Valid` cascade validation vào object/collection lồng nhau; nếu thiếu, constraint của DTO con có thể không chạy khi validate cha.
- Spring MVC thường deserialize request body trước rồi mới kích hoạt validation bằng `@Valid`.
- JSON syntax/mapping errors khác validation errors và khác domain/authorization errors.
- Hãy test mapping và validation riêng, sau đó có test tích hợp cho toàn bộ request pipeline.

Khi thiết kế hợp đồng dữ liệu, hãy dùng annotation Jackson để mô tả cách JSON trở thành object Java và dùng Bean Validation để mô tả object nào được chấp nhận. Tách hai trách nhiệm này giúp API xử lý rõ ràng các trường hợp sai cú pháp, sai kiểu, thiếu dữ liệu và vi phạm quy tắc nghiệp vụ.
