# Thuộc tính bắt buộc, requiredMode và khả năng nhận null

Khi mô tả schema của một request hoặc response, hai câu hỏi thường bị nhầm lẫn: **Client có phải gửi thuộc tính này hay không?** và **Nếu thuộc tính được gửi, giá trị của nó có được phép là null hay không?** OpenAPI biểu diễn hai quy tắc đó độc lập. Một thuộc tính có thể bắt buộc nhưng vẫn cho phép null; cũng có thể tùy chọn nhưng nếu xuất hiện thì phải có giá trị khác null.

Với springdoc-openapi, schema thường được tạo từ DTO Java, annotation OpenAPI và Bean Validation. Annotation **@Schema(requiredMode = ...)** cho phép kiểm soát rõ việc thuộc tính có bắt buộc hay không. Khả năng nhận null được mô tả riêng theo phiên bản OpenAPI: OpenAPI 3.0 dùng **nullable**, còn OpenAPI 3.1 dùng cú pháp JSON Schema. Nắm rõ các lớp này giúp tài liệu sinh ra phản ánh đúng dữ liệu mà controller thực sự chấp nhận.

## 1. Hai câu hỏi độc lập: có phải gửi field và có được gửi null?

Xét một request tạo khách hàng có ba thuộc tính:

```json
{
  "email": "linh@example.com",
  "displayName": "Linh",
  "phone": null
}
```

Email và displayName cần được cung cấp. Phone có thể được bỏ qua; nếu client gửi phone, hợp đồng cho phép giá trị null. Hai thuộc tính đầu là bắt buộc, còn phone vừa tùy chọn vừa nullable.

Trong OpenAPI, danh sách required của một object schema liệt kê tên các thuộc tính bắt buộc phải xuất hiện. Quy tắc này không tự nói thuộc tính có được nhận null hay không. Khả năng nhận null được biểu diễn trong schema của chính thuộc tính.

Ví dụ OpenAPI 3.0:

```yaml
type: object
required:
  - email
  - displayName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
  phone:
    type: string
    nullable: true
```

Ở đây:

- Email và displayName phải xuất hiện trong object và có giá trị theo kiểu string.
- Phone có thể không xuất hiện.
- Nếu phone xuất hiện, giá trị của nó có thể là string hoặc null.

## 2. Phân biệt requestBody.required và schema.required

OpenAPI có hai cấp required thường xuất hiện gần nhau:

| Vị trí | Phạm vi | Ý nghĩa |
|---|---|---|
| requestBody.required | Toàn bộ phần thân request | Client có phải gửi body hay không |
| schema.required | Các thuộc tính của object | Những field nào phải xuất hiện trong object |

Ví dụ body bắt buộc nhưng chỉ có một field bắt buộc:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
        properties:
          name:
            type: string
          description:
            type: string
```

Client phải gửi một JSON object và phải có name. Field description có thể bỏ qua. Nếu body không được gửi, request vi phạm requestBody.required; nếu body là object rỗng, body đã có mặt nhưng object thiếu field name.

Ngược lại, một operation có thể cho phép body vắng mặt nhưng nếu client gửi body thì phải tuân theo schema:

```yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        type: object
        required:
          - reason
        properties:
          reason:
            type: string
```

Trong trường hợp này, client có thể không gửi body. Nếu gửi object, reason phải xuất hiện. Hai cấp required giải quyết hai câu hỏi khác nhau và không thay thế nhau.

## 3. Bốn trạng thái của một thuộc tính

Kết hợp tính bắt buộc và khả năng nhận null tạo ra bốn trường hợp:

| Thuộc tính | Phải xuất hiện? | Cho phép null? | Hành vi |
|---|---:|---:|---|
| Bắt buộc, không nullable | Có | Không | Phải gửi giá trị hợp lệ, khác null |
| Bắt buộc, nullable | Có | Có | Phải gửi field; giá trị có thể là null |
| Tùy chọn, không nullable | Không | Không | Có thể bỏ field; nếu gửi phải có giá trị khác null |
| Tùy chọn, nullable | Không | Có | Có thể bỏ field hoặc gửi null |

Ví dụ OpenAPI 3.0 cho cả bốn trường hợp:

```yaml
type: object
required:
  - id
  - middleName
properties:
  id:
    type: integer
    format: int64
  middleName:
    type: string
    nullable: true
  nickname:
    type: string
  secondaryPhone:
    type: string
    nullable: true
```

- ID: bắt buộc và không nullable.
- MiddleName: bắt buộc nhưng nullable.
- Nickname: tùy chọn và không nullable.
- SecondaryPhone: tùy chọn và nullable.

Trường hợp bắt buộc nhưng nullable hữu ích khi hợp đồng yêu cầu client thể hiện rõ thuộc tính trong mọi request, kể cả khi chưa có giá trị. Trường hợp tùy chọn và nullable có thể hữu ích với một số quy ước cập nhật, nhưng cần nói rõ khác biệt giữa bỏ field và gửi null.

## 4. requiredMode trong annotation @Schema

Swagger Annotations cung cấp requiredMode trong @Schema để xác định một thuộc tính có bắt buộc hay không. Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| Schema.RequiredMode.AUTO | Để thư viện suy luận từ metadata và cấu hình hiện có |
| Schema.RequiredMode.REQUIRED | Đánh dấu thuộc tính là bắt buộc |
| Schema.RequiredMode.NOT_REQUIRED | Đánh dấu thuộc tính là không bắt buộc |

Ví dụ:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateCustomerRequest(
    @Schema(
        description = "Địa chỉ email đăng nhập.",
        requiredMode = Schema.RequiredMode.REQUIRED,
        example = "linh@example.com"
    )
    String email,

    @Schema(
        description = "Tên hiển thị của khách hàng.",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String displayName,

    @Schema(
        description = "Số điện thoại phụ, có thể chưa được cung cấp.",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    String secondaryPhone
) {
}
```

AUTO là chế độ mặc định trong nhiều phiên bản annotation hiện đại. Thư viện có thể suy luận từ kiểu Java, annotation validation và metadata khác. Kết quả suy luận phụ thuộc phiên bản swagger-core/springdoc và cách DTO được khai báo. Với hợp đồng công khai, nên đặt REQUIRED hoặc NOT_REQUIRED tường minh ở các field quan trọng rồi kiểm tra tài liệu được sinh ra.

requiredMode chỉ kiểm soát việc field có phải xuất hiện trong object hay không. Nó không phải cờ cho phép null. Muốn biểu đạt nullability, cần dùng cách mô tả phù hợp với phiên bản OpenAPI mà ứng dụng xuất ra.

### 4.1. Không nhầm requiredMode với thuộc tính required cũ

Các phiên bản Swagger Annotations cũ có thuộc tính boolean required trên @Schema. Ở các phiên bản mới, requiredMode là cách khai báo rõ ràng hơn và thay thế cách dùng boolean cũ trong những API đã đánh dấu deprecated. Khi nâng cấp dependency, hãy xem Javadoc của phiên bản đang dùng và ưu tiên requiredMode nếu có.

Không khai báo cả required và requiredMode với hai giá trị mâu thuẫn. Khi có xung đột giữa annotation, Bean Validation và cấu hình tùy biến, kết quả tài liệu có thể khó dự đoán.

## 5. Kết hợp requiredMode với Bean Validation

Bean Validation kiểm tra dữ liệu khi request được binding vào DTO. Một số annotation thường gặp:

| Annotation | Quy tắc kiểm tra |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không được null, rỗng hoặc chỉ chứa khoảng trắng |
| @NotEmpty | Chuỗi, collection hoặc mảng không được null và không rỗng |
| @Size(min, max) | Giới hạn kích thước chuỗi, collection hoặc mảng |
| @Email | Kiểm tra giá trị theo quy tắc email của validator |

Ví dụ DTO:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Email
    String email,

    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Size(max = 100)
    String displayName,

    @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED, nullable = true)
    @Size(min = 1, max = 30)
    String phone
) {
}
```

Ở đây, @NotBlank bảo đảm email và displayName không null, không rỗng và không chỉ có khoảng trắng. @Email bổ sung kiểm tra định dạng email. Ví dụ này dùng OpenAPI 3.0 và cho phép phone bị bỏ qua hoặc nhận null; nếu có giá trị khác null, @Size yêu cầu độ dài từ 1 đến 30 ký tự.

Để validation được thực thi khi controller nhận request, cần kích hoạt validation, thường bằng @Valid trên tham số @RequestBody và dependency Bean Validation phù hợp:

```java
@PostMapping
public CustomerResponse create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    return customerService.create(request);
}
```

Annotation OpenAPI mô tả hợp đồng cho công cụ và người đọc. Bean Validation mới là phần thực thi các ràng buộc ở thời điểm xử lý request. Không nên chỉ khai báo @Schema(requiredMode = REQUIRED) rồi cho rằng Spring tự từ chối giá trị null.

### 5.1. required và @NotNull có vai trò khác nhau

requiredMode = REQUIRED nói với người dùng API rằng field phải xuất hiện trong object JSON. @NotNull là một quy tắc validation trên giá trị sau khi Jackson chuyển JSON thành Java object.

Ví dụ:

- Nếu client bỏ field email, Jackson có thể tạo DTO với giá trị null; @NotNull hoặc @NotBlank sẽ phát hiện sau khi validation chạy.
- Nếu client gửi email bằng null, giá trị sau binding cũng là null; @NotNull sẽ từ chối.
- Nếu client gửi chuỗi rỗng, @NotNull không từ chối chuỗi rỗng; @NotBlank mới kiểm tra trường hợp này.

Khi dùng @NotNull trên một field nullable theo ý nghĩa nghiệp vụ, hợp đồng sẽ mâu thuẫn. Hãy thống nhất annotation schema, validation và hành vi controller.

## 6. Phân biệt nullability trong OpenAPI 3.0 và 3.1

Cú pháp cho phép null phụ thuộc phiên bản đặc tả.

### 6.1. OpenAPI 3.0: dùng nullable

Trong OpenAPI 3.0, một schema có thể khai báo nullable: true cùng với type:

```yaml
type: object
required:
  - note
properties:
  note:
    type: string
    nullable: true
```

Field note phải xuất hiện nhưng giá trị có thể là string hoặc null. Nếu bỏ nullable: true, schema string thông thường không chấp nhận null.

### 6.2. OpenAPI 3.1: dùng JSON Schema type

OpenAPI 3.1 dựa trên JSON Schema 2020-12. Có thể mô tả kiểu string hoặc null bằng union type:

```yaml
type: object
required:
  - note
properties:
  note:
    type:
      - string
      - "null"
```

Hoặc dùng anyOf:

```yaml
note:
  anyOf:
    - type: string
    - type: "null"
```

Trong OpenAPI 3.1, không sử dụng nullable: true như cách chuẩn để thêm null vào kiểu dữ liệu. Hãy dùng cú pháp JSON Schema tương ứng. Đồng thời, kiểm tra phiên bản Swagger UI, validator và client generator có hỗ trợ OpenAPI 3.1 hay không.

## 7. Khai báo nullability với springdoc

Springdoc tạo tài liệu theo phiên bản OpenAPI mà dự án cấu hình và hỗ trợ. Với OpenAPI 3.0, annotation @Schema(nullable = true) có thể được dùng để mô tả thuộc tính nullable:

```java
public record CustomerProfile(
    @Schema(
        description = "Tên đệm; thuộc tính phải xuất hiện nhưng có thể null.",
        requiredMode = Schema.RequiredMode.REQUIRED,
        nullable = true
    )
    String middleName,

    @Schema(
        description = "Số điện thoại phụ; có thể bỏ qua và có thể null.",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED,
        nullable = true
    )
    String secondaryPhone
) {
}
```

Ví dụ này minh họa cú pháp cho tài liệu OpenAPI 3.0. Nếu dự án xuất OpenAPI 3.1, hãy xác nhận cách phiên bản springdoc/swagger-core đang dùng biểu diễn kiểu union với null. Không mặc định rằng nullable = true trong annotation sẽ tạo ra schema 3.1 đúng như mong muốn.

Để kiểm tra phiên bản tài liệu, mở /v3/api-docs và xem trường openapi ở đầu JSON. Tùy phiên bản springdoc, có thể cấu hình phiên bản API docs bằng thuộc tính springdoc.api-docs.version với giá trị được thư viện hỗ trợ. Sau khi thay đổi, xác nhận output thực tế thay vì chỉ dựa vào cấu hình.

## 8. Java primitive, wrapper và khả năng null

Kiểu Java ảnh hưởng trực tiếp đến khả năng biểu diễn null sau khi binding:

| Java type | Có thể mang null? | Giá trị mặc định khi thiếu trong nhiều trường hợp binding |
|---|---:|---|
| int | Không | 0 |
| long | Không | 0 |
| boolean | Không | false |
| Integer | Có | null |
| Long | Có | null |
| Boolean | Có | null |
| String | Có | null |
| BigDecimal | Có | null |

Nếu một field số thực sự bắt buộc và cần phát hiện việc client không gửi field, kiểu wrapper như Integer hoặc Long kết hợp @NotNull thường thể hiện ý định rõ hơn primitive. Với primitive, giá trị thiếu có thể trở thành giá trị mặc định của kiểu, khiến ứng dụng khó phân biệt client không gửi với client gửi 0 hoặc false.

Ví dụ:

```java
public record UpdateSettingsRequest(
    @NotNull
    Integer pageSize,

    Boolean emailNotifications
) {
}
```

pageSize bắt buộc và không được null. emailNotifications có thể bị bỏ qua hoặc null nếu hợp đồng cho phép. Nếu ứng dụng muốn phân biệt hai trường hợp đó, DTO và logic binding phải giữ được thông tin về sự hiện diện của field.

## 9. Thiếu field và gửi null khi cập nhật

Với thao tác PATCH, việc phân biệt field không xuất hiện và field có giá trị null đặc biệt quan trọng:

```json
{
  "displayName": "Linh Nguyễn"
}
```

Request này có thể mang ý nghĩa chỉ cập nhật displayName, giữ nguyên các field khác.

```json
{
  "displayName": "Linh Nguyễn",
  "phone": null
}
```

Request thứ hai có thể mang ý nghĩa xóa số điện thoại. Tuy nhiên, nếu cả hai trường hợp đều được ánh xạ vào DTO có String phone, Jackson thường tạo ra null khi field bị thiếu hoặc khi field được gửi với giá trị null. Khi đó, code không thể phân biệt hai ý định chỉ bằng giá trị của thuộc tính.

Có một số cách giải quyết:

- Dùng DTO patch có cơ chế lưu lại trạng thái field đã xuất hiện trong JSON.
- Dùng định dạng chuẩn như JSON Merge Patch nếu hợp đồng cần quy ước rõ giữa bỏ field và null.
- Dùng kiểu wrapper chuyên biệt như JsonNullable<T> cùng module Jackson tương ứng nếu dự án đã chọn thư viện này.
- Tách operation hoặc thiết kế request command rõ ràng nếu cập nhật có quy tắc nghiệp vụ riêng.

Không nên tuyên bố rằng null có nghĩa xóa field nếu cách binding hiện tại không phân biệt được field bị bỏ qua và field được gửi null.

## 10. RequiredMode, validation và schema có thể tạo ra mâu thuẫn

Một số cấu hình dễ tạo tài liệu không nhất quán:

| Cấu hình | Mâu thuẫn |
|---|---|
| requiredMode = REQUIRED nhưng DTO không có validation và code chấp nhận null | Tài liệu nói field bắt buộc nhưng backend có thể chấp nhận null |
| requiredMode = NOT_REQUIRED cùng @NotNull | Schema nói có thể bỏ field, nhưng validation từ chối giá trị null sau binding |
| nullable = true cùng @NotNull | Schema cho phép null nhưng validation từ chối |
| Java primitive cho field được mô tả nullable | Kiểu Java không thể giữ giá trị null |
| Field không required nhưng có default trong schema, backend không áp dụng default | Tài liệu gợi ý hành vi mà server không thực hiện |

Khi gặp mâu thuẫn, hãy xác định hợp đồng nghiệp vụ trước, sau đó đồng bộ ba lớp:

1. Schema OpenAPI: required và nullability.
2. DTO/Bean Validation: kiểu Java và các constraint.
3. Logic xử lý: cách ứng dụng hiểu field thiếu, null và giá trị mặc định.

## 11. Ví dụ đầy đủ: DTO và schema cho hồ sơ khách hàng

Giả sử API tạo hồ sơ có quy tắc:

- Email bắt buộc, không được null và phải đúng định dạng.
- DisplayName bắt buộc, không được null hoặc chỉ có khoảng trắng.
- MiddleName bắt buộc phải xuất hiện, nhưng được phép null.
- Phone tùy chọn và nullable; nếu có giá trị khác null, độ dài phải từ 1 đến 30 ký tự.

Với OpenAPI 3.0, có thể mô tả schema như sau:

```yaml
type: object
required:
  - email
  - displayName
  - middleName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
    minLength: 1
  middleName:
    type: string
    nullable: true
  phone:
    type: string
    nullable: true
    minLength: 1
```

DTO Java có thể được khai báo:

```java
public record CreateProfileRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Email
    String email,

    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    String displayName,

    @Schema(
        requiredMode = Schema.RequiredMode.REQUIRED,
        nullable = true
    )
    String middleName,

    @Schema(
        requiredMode = Schema.RequiredMode.NOT_REQUIRED,
        nullable = true
    )
    @Size(min = 1, max = 30)
    String phone
) {
}
```

@Size cho phép giá trị null và chỉ kiểm tra kích thước khi giá trị khác null. Vì vậy, ví dụ này nhất quán với hợp đồng phone tùy chọn và nullable: field có thể bị bỏ qua hoặc gửi null; nếu gửi chuỗi, độ dài phải từ 1 đến 30 ký tự. Nếu yêu cầu nghiệp vụ là cấm cả chuỗi chỉ chứa khoảng trắng nhưng vẫn cho phép null, cần một constraint tùy chỉnh có ngữ nghĩa phù hợp.

Ví dụ thể hiện vì sao không thể suy luận required và nullable chỉ từ một annotation duy nhất. Chúng phải được phối hợp theo ý nghĩa nghiệp vụ.

Riêng middleName là field bắt buộc nhưng nullable. Không thể dùng @NotNull để kiểm tra sự hiện diện vì constraint đó cũng từ chối giá trị null hợp lệ. Nếu backend phải phân biệt field bị bỏ qua với field được gửi rõ ràng là null, cần kiểm tra sự hiện diện ở bước deserialize. Với record hoặc constructor property, có thể cân nhắc metadata Jackson như @JsonProperty(required = true) trên creator property, hoặc dùng custom deserializer; hãy kiểm tra hành vi với phiên bản Jackson của dự án và viết integration test cho cả hai payload. @Schema chỉ mô tả hợp đồng, không tự thực thi yêu cầu field phải xuất hiện.

## 12. Kiểm tra schema được springdoc sinh ra

Sau khi khởi động ứng dụng, mở endpoint OpenAPI, thường là /v3/api-docs. Tìm schema tương ứng trong components.schemas và kiểm tra:

1. Danh sách required có đúng các field bắt buộc xuất hiện không?
2. Field bắt buộc nhưng nullable có nằm trong required đồng thời cho phép null không?
3. Field tùy chọn có bị đưa nhầm vào required do annotation hoặc validation không?
4. Kiểu Java primitive có tạo ra schema không tương thích với nullability không?
5. Cú pháp null có khớp phiên bản OpenAPI 3.0 hoặc 3.1 không?
6. Ví dụ JSON có phản ánh đúng cả field bị bỏ qua và field null không?

Có thể dùng Swagger UI để thử các payload khác nhau, nhưng nên kiểm tra JSON/YAML gốc vì đây là hợp đồng mà các công cụ sinh client và validator sử dụng.

### 12.1. Tạo kiểm thử validation cho DTO

Có thể kiểm tra constraint bằng Bean Validation trong unit test hoặc integration test. Ví dụ:

```java
@SpringBootTest
class CreateCustomerRequestValidationTest {

    @Autowired
    Validator validator;

    @Test
    void emailMustNotBeNull() {
        var request = new CreateCustomerRequest(
            null,
            "Linh",
            null
        );

        var violations = validator.validate(request);

        assertThat(violations)
            .anyMatch(v -> v.getPropertyPath().toString().equals("email"));
    }
}
```

Ví dụ giả định CreateCustomerRequest có ba thành phần email, displayName, phone như phần trên và dự án đã cấu hình Bean Validation cùng AssertJ. Kiểm thử này xác nhận constraint trên DTO; nó không tự xác nhận OpenAPI schema. Cần có kiểm tra riêng trên tài liệu JSON/YAML để xác minh required và nullability.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Cho rằng required đồng nghĩa không được null | Field bắt buộc nhưng nullable bị mô tả sai | Khai báo required và nullability độc lập |
| Dùng requestBody.required để đánh dấu field | Toàn bộ body bị hiểu là bắt buộc hoặc tùy chọn sai | Đặt danh sách required trong object schema |
| Dùng requiredMode để cho phép null | Schema không thể hiện nullability | Dùng nullable cho OAS 3.0 hoặc union type cho OAS 3.1 |
| Chỉ dùng @Schema(requiredMode = REQUIRED) để validation | Backend vẫn có thể nhận null | Bổ sung Bean Validation hoặc logic kiểm tra |
| Dùng primitive cho field cần phân biệt thiếu và null | Giá trị mặc định che mất trạng thái thiếu | Dùng wrapper và constraint phù hợp |
| Dùng @NotNull cho chuỗi cần loại cả chuỗi rỗng | Chuỗi rỗng vẫn có thể qua validation | Dùng @NotBlank hoặc constraint phù hợp |
| Dùng nullable: true trong schema 3.1 | Validator hoặc generator có thể diễn giải sai | Dùng JSON Schema type union hoặc anyOf |
| Dùng DTO thường cho PATCH nhưng cần phân biệt missing/null | Jackson có thể ánh xạ cả hai thành null | Dùng kiểu giữ trạng thái hiện diện hoặc định dạng patch |
| Tin rằng AUTO luôn suy luận đúng hợp đồng | Kết quả có thể thay đổi theo dependency và metadata | Khai báo tường minh và kiểm tra tài liệu sinh ra |

## 14. Ghi nhớ

- requestBody.required xác định toàn bộ body có bắt buộc hay không.
- schema.required xác định thuộc tính nào của object phải xuất hiện.
- Một field có thể bắt buộc nhưng nullable; cũng có thể tùy chọn nhưng không nullable.
- @Schema(requiredMode = REQUIRED/NOT_REQUIRED/AUTO) kiểm soát tính bắt buộc của field trong schema, không thay thế nullability.
- Bean Validation như @NotNull, @NotBlank và @NotEmpty kiểm tra giá trị khi ứng dụng xử lý request.
- OpenAPI 3.0 dùng nullable: true; OpenAPI 3.1 dùng cú pháp JSON Schema để cho phép null.
- Java primitive không thể chứa null; wrapper giúp biểu diễn trạng thái chưa có giá trị rõ hơn.
- Với PATCH, cần định nghĩa rõ khác biệt giữa field bị bỏ qua và field được gửi với null.
- Luôn kiểm tra tài liệu JSON/YAML do springdoc sinh ra và đối chiếu với validation cùng hành vi controller.

Khi thiết kế schema cho Spring Boot, hãy quyết định riêng hai điều: field có phải xuất hiện trong request hay không và giá trị null có được chấp nhận hay không. Sau đó thể hiện quyết định bằng requiredMode, nullability, Bean Validation và logic binding phù hợp. Sự nhất quán giữa các lớp này giúp Swagger UI, client generator và backend hiểu cùng một hợp đồng dữ liệu.
