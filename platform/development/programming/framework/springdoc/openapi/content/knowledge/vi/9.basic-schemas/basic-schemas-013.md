# Ẩn thuộc tính khỏi tài liệu và tác động cần kiểm tra

Trong API Spring Boot, có những thuộc tính không nên xuất hiện trong tài liệu OpenAPI, chẳng hạn ghi chú nội bộ, trường phục vụ xử lý kỹ thuật hoặc dữ liệu không thuộc hợp đồng công khai. Springdoc-openapi hỗ trợ ẩn property khỏi schema bằng `@Schema(hidden = true)`. Tuy nhiên, ẩn một thuộc tính khỏi tài liệu chỉ thay đổi cách hợp đồng được mô tả; nó không tự loại thuộc tính khỏi JSON request/response, không thay đổi validation và không bảo vệ dữ liệu nhạy cảm. Để chọn đúng cách xử lý, cần phân biệt annotation Swagger với các annotation Jackson điều khiển dữ liệu thực tế.

## 1. Ẩn khỏi tài liệu khác với ẩn khỏi JSON

Một DTO có thể đồng thời tham gia ba lớp:

1. **Java model:** các field, getter, constructor và kiểu dữ liệu trong mã nguồn.
2. **JSON runtime:** nội dung Spring/Jackson thực sự đọc từ request hoặc ghi vào response.
3. **OpenAPI schema:** hợp đồng được springdoc tạo ra để client và công cụ hiểu request/response.

Các annotation khác nhau tác động vào những lớp khác nhau:

| Annotation | Tác động chính | Có tự thay đổi JSON runtime không? |
|---|---|---|
| Swagger `@Schema(hidden = true)` | Ẩn property khỏi schema OpenAPI | Không |
| Swagger `@Schema(accessMode = READ_ONLY)` | Đánh dấu property chỉ đọc trong hợp đồng OpenAPI | Không |
| Swagger `@Schema(accessMode = WRITE_ONLY)` | Đánh dấu property chỉ ghi trong hợp đồng OpenAPI | Không |
| Jackson `@JsonIgnore` | Bỏ qua property khi Jackson xử lý JSON | Có |
| Jackson `@JsonProperty(access = READ_ONLY)` | Cho phép property đi ra JSON nhưng không nhận từ JSON input | Có |
| Jackson `@JsonProperty(access = WRITE_ONLY)` | Cho phép nhận property từ JSON input nhưng không ghi ra JSON output | Có |

Vì vậy, nếu yêu cầu chỉ là không hiển thị một trường trong Swagger UI, `@Schema(hidden = true)` có thể phù hợp. Nếu yêu cầu là không để trường xuất hiện trong payload thực tế, cần điều khiển serialization/deserialization bằng Jackson hoặc thiết kế DTO riêng.

## 2. Dùng @Schema(hidden = true) để ẩn property khỏi OpenAPI

`@Schema` thuộc Swagger annotations, package `io.swagger.v3.oas.annotations.media`. Thuộc tính `hidden` cho biết property không được đưa vào schema được công bố.

Ví dụ:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public class AccountResponse {

    private Long id;
    private String email;

    @Schema(hidden = true)
    private String internalTraceId;

    // getters và setters
}
```

Trong schema OpenAPI, `id` và `email` có thể được mô tả như các property thông thường, còn `internalTraceId` được loại khỏi tài liệu. Client xem Swagger UI hoặc tải `/v3/api-docs` sẽ không thấy trường này trong schema.

Điều cần nhớ là `@Schema(hidden = true)` chỉ tác động tới tài liệu. Nếu Jackson vẫn nhìn thấy getter hoặc field và cấu hình serialization cho phép, response JSON vẫn có thể chứa `internalTraceId`. Tương tự, Spring vẫn có thể bind property đó từ request nếu kiểu dữ liệu và cấu hình Jackson cho phép.

### Ẩn property trong DTO request

```java
public class UpdateAccountRequest {

    private String displayName;

    @Schema(hidden = true)
    private String internalApprovalCode;

    // getters và setters
}
```

Trong tài liệu request, `internalApprovalCode` sẽ không được mô tả. Nhưng annotation này không tự ngăn client gửi field đó. Nếu endpoint phải từ chối hoặc bỏ qua giá trị do client gửi, hãy thiết kế DTO, Jackson binding và validation theo đúng chính sách nghiệp vụ.

## 3. Dùng @JsonIgnore khi muốn Jackson bỏ qua property

`@JsonIgnore` thuộc Jackson và tác động vào quá trình đọc/ghi JSON. Khi đặt trên property được Jackson nhận diện, nó thường khiến property bị bỏ qua trong cả serialization lẫn deserialization.

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class AccountResponse {

    private Long id;
    private String email;

    @JsonIgnore
    private String internalTraceId;

    // getters và setters
}
```

Với cấu hình Jackson thông thường, `internalTraceId` không được ghi vào JSON response và cũng không được gán từ JSON input. Vì springdoc thường dựa vào mô hình Jackson để suy luận schema, property bị `@JsonIgnore` bỏ qua thường cũng không xuất hiện trong OpenAPI.

Không nên dùng `@JsonIgnore` nếu chỉ muốn ẩn trường trong tài liệu nhưng vẫn cần trường đó xuất hiện trong JSON. Trong trường hợp ấy, dùng `@Schema(hidden = true)` và kiểm tra JSON runtime để xác nhận hành vi mong muốn.

Jackson có thể kết hợp annotation trên field, getter, setter hoặc cấu hình mix-in. Nếu cùng một property có nhiều accessor với annotation khác nhau, quy tắc hợp nhất của Jackson có thể ảnh hưởng kết quả. Hãy kiểm tra object JSON thực tế thay vì chỉ nhìn annotation tại một vị trí.

## 4. Phân biệt READ_ONLY và WRITE_ONLY

Nhiều DTO có trường chỉ phù hợp với một chiều dữ liệu. Ví dụ, client gửi mật khẩu khi tạo tài khoản nhưng server không bao giờ trả mật khẩu; ngược lại, `id` và `createdAt` do server tạo ra nên client không được gửi như dữ liệu đầu vào.

OpenAPI có hai trạng thái tương ứng:

- `readOnly`: property được dùng trong response. Theo hợp đồng, client không nên gửi property này trong request.
- `writeOnly`: property được dùng trong request. Theo hợp đồng, server không nên gửi property này trong response.

Trong Swagger annotations, có thể khai báo bằng `@Schema(accessMode = ...)`:

```java
public class Account {

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Long id;

    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    private String email;
}
```

`READ_ONLY` và `WRITE_ONLY` là metadata của schema OpenAPI. Chúng giúp tài liệu và client generator hiểu chiều sử dụng của property, nhưng không tự thực thi quy tắc đó ở Jackson hoặc Spring MVC.

### Kết hợp với Jackson để điều khiển JSON runtime

Nếu muốn cùng một class Java dùng cho request và response, Jackson `@JsonProperty(access = ...)` có thể điều khiển chiều đọc/ghi JSON:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class Account {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    private String email;
}
```

Với Jackson:

- `READ_ONLY`: property có thể được serialize ra response nhưng không được gán từ JSON input.
- `WRITE_ONLY`: property có thể được đọc từ JSON input nhưng không được serialize ra response.

Springdoc có thể nhận diện metadata Jackson và mô tả schema theo hướng tương ứng. Nếu cần kiểm soát tài liệu rõ ràng, có thể kết hợp `@JsonProperty(access = ...)` với `@Schema(accessMode = ...)`, nhưng phải tránh tạo ra hai cấu hình mâu thuẫn.

## 5. So sánh @Schema và @JsonProperty(access)

Hai annotation thường được dùng cho cùng một property nhưng giải quyết hai vấn đề khác nhau:

| Nhu cầu | Annotation phù hợp | Kết quả mong muốn |
|---|---|---|
| Không muốn property xuất hiện trong OpenAPI, nhưng JSON vẫn giữ nguyên | `@Schema(hidden = true)` | Property không có trong schema; runtime JSON không đổi |
| Không muốn property xuất hiện trong cả JSON và schema | `@JsonIgnore` | Jackson bỏ qua property; springdoc thường cũng bỏ qua |
| Muốn chỉ mô tả property ở response | `@Schema(accessMode = READ_ONLY)` | OpenAPI đánh dấu read-only |
| Muốn chỉ mô tả property ở request | `@Schema(accessMode = WRITE_ONLY)` | OpenAPI đánh dấu write-only |
| Muốn JSON chỉ xuất property trong response | `@JsonProperty(access = READ_ONLY)` | Jackson serialize, không deserialize |
| Muốn JSON chỉ nhận property từ request | `@JsonProperty(access = WRITE_ONLY)` | Jackson deserialize, không serialize |

Nếu vừa dùng `@Schema(hidden = true)` vừa dùng `@Schema(accessMode = READ_ONLY)` trên cùng property, `hidden` có nghĩa property không được công bố; do đó thông tin read-only cũng không còn hữu ích trong schema. Chọn một cách mô tả phù hợp với mục đích thay vì chồng annotation không cần thiết.

## 6. Ưu tiên DTO riêng cho request và response

Trong API thực tế, DTO request và response thường có mục đích khác nhau. Tách chúng giúp tránh phải điều khiển nhiều chiều dữ liệu trên cùng một class.

Ví dụ:

```java
public record CreateAccountRequest(
    @NotBlank String email,
    @NotBlank String password,
    String displayName
) {}

public record AccountResponse(
    UUID id,
    String email,
    String displayName,
    Instant createdAt
) {}
```

Controller:

```java
@RestController
@RequestMapping("/api/accounts")
class AccountController {

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    AccountResponse create(@Valid @RequestBody CreateAccountRequest request) {
        Account account = accountService.create(request);
        return AccountResponse.from(account);
    }
}
```

`CreateAccountRequest` có `password` vì client cần gửi mật khẩu để tạo tài khoản. `AccountResponse` không có trường này, do đó mật khẩu không thể vô tình xuất hiện trong response schema hoặc JSON response thông qua DTO này.

Tách DTO cũng giúp mỗi operation có schema đúng với vai trò của nó: request chỉ chứa dữ liệu client được phép cung cấp; response chỉ chứa dữ liệu server được phép công bố. Đây thường là cách dễ duy trì hơn khi một class dùng cho nhiều endpoint với yêu cầu khác nhau.

## 7. Ẩn trường nội bộ không phải là biện pháp bảo mật

Ẩn một property khỏi Swagger UI không bảo đảm dữ liệu đó được bảo vệ. Có thể xảy ra các tình huống:

- `@Schema(hidden = true)` làm schema không hiển thị nhưng Jackson vẫn serialize giá trị vào JSON response.
- Client có thể gửi property ẩn trong request nếu Jackson vẫn cho phép binding.
- Một endpoint khác dùng cùng DTO có thể công bố property đó theo cấu hình schema khác.
- Log, exception message, debugger hoặc endpoint khác vẫn có thể làm lộ dữ liệu.
- Client generator không tạo property ẩn trong model, nhưng server vẫn có thể gửi property đó ở runtime; điều này làm payload lệch hợp đồng.

Không dùng việc ẩn schema để bảo vệ mật khẩu, token, khóa bí mật, thông tin xác thực hoặc dữ liệu cá nhân. Hãy không đưa các giá trị đó vào response DTO, kiểm soát serialization, áp dụng phân quyền và kiểm tra dữ liệu ở server. Đối với input nhạy cảm như password, dùng DTO request riêng và bảo đảm response không bao giờ trả lại giá trị đã nhận.

## 8. Tác động tới schema được tái sử dụng

Springdoc có thể tạo schema trong `components.schemas` và dùng `$ref` từ nhiều operation. Nếu cùng một class được dùng cho cả request và response, thay đổi ẩn property có thể ảnh hưởng nhiều nơi tham chiếu tới schema đó.

Ví dụ một class `Account` được dùng ở cả `POST /accounts` và `GET /accounts/{id}`. Nếu đặt `@Schema(hidden = true)` trên `password`, property có thể biến mất khỏi schema được dùng chung. Khi đó client sẽ không thấy `password` trong request schema dù endpoint tạo tài khoản vẫn cần nhận nó.

Với trường hợp chỉ dùng ở một chiều, hãy cân nhắc:

- Tách `CreateAccountRequest` và `AccountResponse`.
- Dùng `@Schema(accessMode = WRITE_ONLY)` hoặc `READ_ONLY` nếu muốn một schema biểu đạt rõ chiều sử dụng.
- Dùng Jackson `@JsonProperty(access = ...)` khi cần quy tắc đọc/ghi JSON runtime tương ứng.
- Kiểm tra các `$ref` và schema thực tế của từng operation sau khi thay đổi.

Không giả định mỗi operation sẽ luôn có một bản schema độc lập chỉ vì nó dùng ở request hoặc response. Hãy mở tài liệu JSON/YAML để xác nhận cách springdoc tạo component và tham chiếu trong phiên bản đang sử dụng.

## 9. Ví dụ đầy đủ với trường nội bộ, read-only và write-only

Ví dụ dưới đây dùng DTO chung để minh họa ba mục tiêu khác nhau. Trong dự án thực tế, DTO riêng vẫn thường dễ kiểm soát hơn.

```java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public class AccountModel {

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private UUID id;

    private String email;

    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    @Schema(hidden = true)
    private String internalNote;

    @JsonIgnore
    private String internalCredential;

    // getters và setters
}
```

Ý nghĩa của từng property:

| Property | OpenAPI | JSON runtime theo Jackson |
|---|---|---|
| `id` | Read-only | Có thể xuất response; không nhận từ JSON input |
| `email` | Property thông thường | Đọc và ghi theo cấu hình thông thường |
| `password` | Write-only | Nhận từ JSON input; không xuất response |
| `internalNote` | Bị ẩn hoàn toàn khỏi schema | Vẫn có thể được đọc/ghi JSON nếu Jackson cho phép |
| `internalCredential` | Thường không xuất hiện do Jackson bỏ qua | Bị bỏ qua khi đọc/ghi JSON |

Không nên coi `internalNote` là bí mật chỉ vì nó bị ẩn khỏi OpenAPI. Nếu trường này không được phép xuất hiện trong JSON, cần thêm quy tắc Jackson phù hợp hoặc loại nó khỏi response DTO.

## 10. Kiểm tra tài liệu OpenAPI sau khi ẩn property

Sau khi ứng dụng khởi động, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Tìm schema tương ứng trong `components.schemas` và xác nhận:

1. Property có `@Schema(hidden = true)` không xuất hiện trong `properties`.
2. Property `READ_ONLY` có `readOnly: true` nếu được công bố trong schema.
3. Property `WRITE_ONLY` có `writeOnly: true` nếu được công bố trong schema.
4. Các property còn lại vẫn có kiểu, description, example, required và validation đúng.
5. Operation request/response tham chiếu đúng schema và không bị ảnh hưởng ngoài dự kiến.

Ví dụ schema OpenAPI mong đợi:

```yaml
AccountModel:
  type: object
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    email:
      type: string
    password:
      type: string
      writeOnly: true
```

`internalNote` và `internalCredential` không có trong ví dụ schema. Tuy nhiên, để biết JSON runtime có còn chứa chúng hay không, phải kiểm tra request/response thật hoặc kiểm tra trực tiếp bằng `ObjectMapper`.

## 11. Kiểm tra JSON runtime riêng với schema

### Kiểm tra serialization

Có thể dùng Jackson `ObjectMapper` để xác nhận các property nào thực sự xuất hiện trong JSON:

```java
ObjectMapper mapper = new ObjectMapper();
AccountModel account = new AccountModel();
account.setId(UUID.randomUUID());
account.setEmail("user@example.test");
account.setPassword("secret-value");
account.setInternalNote("only-for-operations");
account.setInternalCredential("internal-token");

String json = mapper.writeValueAsString(account);
```

Với các annotation trong ví dụ:

- JSON có thể chứa `id`, `email` và `internalNote`.
- JSON không chứa `password` vì property được đánh dấu `WRITE_ONLY`.
- JSON không chứa `internalCredential` vì `@JsonIgnore`.

`@Schema(hidden = true)` không loại `internalNote` khỏi JSON. Đây là kiểm tra quan trọng để tránh hiểu nhầm giữa tài liệu và hành vi runtime.

### Kiểm tra deserialization

Thử đọc JSON có `id`, `password` và các trường nội bộ để xác nhận Jackson chấp nhận hoặc bỏ qua từng property theo cấu hình:

```java
String input = """
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user@example.test",
      "password": "new-secret",
      "internalNote": "client-value",
      "internalCredential": "client-token"
    }
    """;

AccountModel parsed = mapper.readValue(input, AccountModel.class);
```

Với `READ_ONLY`, giá trị `id` trong JSON input không được gán vào property theo cấu hình Jackson. Với `WRITE_ONLY`, `password` có thể được gán khi đọc JSON. `@Schema(hidden = true)` không tự ngăn `internalNote` được binding. `@JsonIgnore` bỏ qua `internalCredential`.

Trong dự án, `ObjectMapper` có thể được Spring Boot cấu hình bằng module, mix-in, naming strategy hoặc customizer. Khi kiểm tra, nên dùng đúng bean `ObjectMapper` của ứng dụng thay vì chỉ tạo một instance mặc định, để kết quả giống runtime.

## 12. Kiểm tra endpoint và client generator

Kiểm tra schema không thay thế kiểm thử HTTP. Với mỗi DTO có property bị ẩn hoặc giới hạn chiều truy cập, nên kiểm tra:

| Kiểm tra | Câu hỏi |
|---|---|
| OpenAPI request schema | Client có biết property nào cần gửi và property nào chỉ được ghi không? |
| OpenAPI response schema | Client có biết property nào được trả về và property nào chỉ đọc không? |
| Request thực tế | Server có nhận hoặc bỏ qua property ngoài hợp đồng theo đúng chính sách không? |
| Response thực tế | Có trường nhạy cảm hoặc trường nội bộ nào bị serialize ngoài ý muốn không? |
| Validation | Các trường bắt buộc vẫn được kiểm tra dù một property bị ẩn khỏi tài liệu không? |
| Client generator | Model được sinh ra có đúng các trường, chiều truy cập và kiểu dữ liệu mong đợi không? |

Nếu dùng `@Schema(hidden = true)` cho một field vẫn có trong JSON, client generator sẽ không tạo field đó trong model. Khi server trả field ẩn, client có thể bỏ qua hoặc không thể truy cập dữ liệu đó. Nếu server yêu cầu client gửi một field bị ẩn khỏi request schema, client generator cũng không biết phải cung cấp giá trị đó. Đây là dấu hiệu hợp đồng không đầy đủ.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Field không xuất hiện trong Swagger UI nhưng vẫn có trong JSON | Dùng `@Schema(hidden = true)` | Đây là hành vi dự kiến; dùng Jackson nếu muốn thay đổi JSON |
| Field biến mất khỏi cả request và response schema | Dùng `@Schema(hidden = true)` trên class dùng chung | Dùng schema/DTO riêng hoặc access mode nếu field thuộc một chiều |
| Field nhạy cảm vẫn xuất hiện trong response JSON | Chỉ ẩn field trong tài liệu | Loại field khỏi response DTO hoặc cấu hình Jackson `WRITE_ONLY`/`@JsonIgnore` phù hợp |
| Client vẫn gửi được field không mong muốn | Chỉ dùng `@Schema(hidden = true)` | Kiểm soát binding bằng DTO, Jackson và validation |
| `password` xuất hiện trong response | Chưa cấu hình serialization write-only hoặc response dùng DTO không phù hợp | Dùng DTO response không có password hoặc Jackson `WRITE_ONLY` |
| `id` do client gửi được gán vào model | Chưa cấu hình read-only ở Jackson hoặc xử lý mapping thủ công nhận giá trị đó | Dùng Jackson `READ_ONLY`, DTO request riêng và kiểm tra mapping |
| Schema request/response dùng chung bị thiếu field | Một component bị ẩn hoặc tái sử dụng cho cả hai chiều | Tách DTO hoặc kiểm tra access mode và `$ref` |
| Springdoc không phản ánh annotation như dự kiến | Annotation đặt sai vị trí, cấu hình Jackson hoặc phiên bản thư viện ảnh hưởng introspection | Kiểm tra `/v3/api-docs`, vị trí annotation và cấu hình thực tế |

## 14. Quy trình quyết định cách ẩn property

Trước khi thêm annotation, xác định mục tiêu chính:

1. Nếu chỉ muốn loại property khỏi tài liệu, dùng `@Schema(hidden = true)` và xác minh JSON không bị thay đổi ngoài dự kiến.
2. Nếu muốn Jackson bỏ qua property khi đọc và ghi JSON, cân nhắc `@JsonIgnore`.
3. Nếu property chỉ được nhận từ request, dùng `@JsonProperty(access = WRITE_ONLY)` cho runtime và/hoặc `@Schema(accessMode = WRITE_ONLY)` cho hợp đồng.
4. Nếu property chỉ được trả trong response, dùng `@JsonProperty(access = READ_ONLY)` cho runtime và/hoặc `@Schema(accessMode = READ_ONLY)` cho hợp đồng.
5. Nếu request và response có cấu trúc khác nhau, ưu tiên DTO riêng để tránh schema dùng chung gây nhầm lẫn.
6. Kiểm tra OpenAPI JSON/YAML, JSON runtime, validation, quyền truy cập và client được sinh ra.

Ẩn thuộc tính là một quyết định về hợp đồng API. Cần bảo đảm tài liệu mô tả đúng những gì client được phép gửi và nhận, đồng thời JSON runtime không làm lộ dữ liệu nội bộ. Springdoc tạo schema; Jackson xử lý JSON; Spring Security và logic nghiệp vụ kiểm soát quyền truy cập. Ba lớp này phải được kiểm tra riêng và giữ nhất quán.

## 15. Tài liệu tham khảo

- [Swagger Core – Schema annotation](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): thuộc tính `hidden`, `accessMode` và cách mô tả schema.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): ngữ nghĩa của `readOnly` và `writeOnly` trong schema.
- [Jackson Annotations – JsonIgnore](https://github.com/FasterXML/jackson-annotations): điều khiển property được Jackson bỏ qua.
- [Jackson Annotations – JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html): các chế độ `AUTO`, `READ_ONLY`, `WRITE_ONLY`, `READ_WRITE`.
- [Springdoc OpenAPI](https://springdoc.org/): suy luận schema và tùy chỉnh tài liệu OpenAPI từ ứng dụng Spring Boot.
