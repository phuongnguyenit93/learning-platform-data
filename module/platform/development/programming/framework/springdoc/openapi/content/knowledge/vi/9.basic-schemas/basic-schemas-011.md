# `readOnly`, `writeOnly`, `accessMode` và dữ liệu chỉ dùng cho một chiều trao đổi

Trong một API, không phải thuộc tính nào cũng được phép đi theo cả hai chiều. Một mã định danh thường do server tạo và chỉ trả về cho client; mật khẩu được client gửi khi tạo tài khoản nhưng không được trả lại trong response. OpenAPI có các thuộc tính `readOnly` và `writeOnly` để mô tả sự khác nhau này trong schema. Với springdoc-openapi, có thể khai báo metadata đó bằng `@Schema(accessMode = ...)` trên DTO.

Điều cần phân biệt là hợp đồng OpenAPI và hành vi xử lý JSON của ứng dụng. `@Schema` mô tả cách client nên sử dụng thuộc tính; annotation này không tự ngăn Jackson nhận hoặc xuất dữ liệu. Nếu cần kiểm soát JSON thực tế, phải cấu hình DTO, Jackson hoặc tách riêng request DTO và response DTO. Bài học này giải thích cách phối hợp các lớp đó để tài liệu được sinh phản ánh đúng API Spring Boot.

## 1. Vì sao cần mô tả dữ liệu một chiều?

Xét API tạo người dùng. Client gửi tên, email và mật khẩu; server tự tạo mã người dùng và thời điểm tạo. Khi trả kết quả, server gửi mã, tên, email và thời điểm tạo, nhưng không gửi mật khẩu.

```text
Request:
{
  "name": "Nguyen Van A",
  "email": "user@example.com",
  "password": "example-secret"
}

Response:
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Nguyen Van A",
  "email": "user@example.com",
  "createdAt": "2026-11-20T10:00:00Z"
}
```

Hai chiều trao đổi có cấu trúc gần giống nhau nhưng không có cùng tập thuộc tính:

- `id` và `createdAt` do server quản lý, chỉ nên xuất hiện trong response.
- `password` là dữ liệu đầu vào, không được đưa vào response.
- `name` và `email` có thể xuất hiện ở cả request lẫn response.

Nếu schema chỉ mô tả tất cả thuộc tính là dữ liệu đọc/ghi thông thường, người tiêu dùng API có thể hiểu nhầm rằng client được phép tự gửi `id` hoặc server có thể trả `password`. Metadata hướng truy cập giúp biểu đạt đúng ý nghĩa này.

## 2. Ý nghĩa của `readOnly` và `writeOnly` trong OpenAPI

OpenAPI định nghĩa hai thuộc tính Boolean trong Schema Object:

| Thuộc tính | Ý nghĩa trong hợp đồng | Ví dụ thường gặp |
|---|---|---|
| `readOnly: true` | Thuộc tính có thể được gửi trong response; không nên được gửi trong request | ID do server tạo, `createdAt`, `updatedAt` |
| `writeOnly: true` | Thuộc tính có thể được gửi trong request; không nên được trả trong response | Password, mã bí mật dùng để đăng ký |
| Không khai báo hoặc `false` | Không đánh dấu giới hạn một chiều bằng metadata này | `name`, `email`, `description` |

Trong ngữ cảnh API, “read” và “write” được nhìn từ phía người tiêu dùng hợp đồng:

- Client đọc dữ liệu từ response, vì vậy thuộc tính `readOnly` phù hợp với dữ liệu chỉ được server trả về.
- Client ghi dữ liệu bằng cách gửi request, vì vậy thuộc tính `writeOnly` phù hợp với dữ liệu chỉ được client cung cấp.

Ví dụ schema:

```yaml
User:
  type: object
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    password:
      type: string
      writeOnly: true
    name:
      type: string
```

Schema này nói rằng `id` thuộc chiều response, `password` thuộc chiều request, còn `name` không bị giới hạn theo hướng bởi hai thuộc tính trên.

`readOnly` và `writeOnly` là metadata của hợp đồng. Chúng không phải cơ chế xác thực, phân quyền hoặc mã hóa. Một client vẫn có thể tự tạo request chứa trường `id`; server phải quyết định cách xử lý request đó. Tương tự, đánh dấu `password` là write-only trong tài liệu không tự bảo đảm mật khẩu không xuất hiện trong JSON response nếu serializer vẫn xuất trường này.

## 3. `required` được hiểu theo từng chiều

`required` và `readOnly`/`writeOnly` bổ sung ý nghĩa cho nhau. Với OpenAPI 3.0, khi một thuộc tính read-only được liệt kê trong `required`, yêu cầu đó áp dụng cho response; khi một thuộc tính write-only được liệt kê trong `required`, yêu cầu đó áp dụng cho request.

Ví dụ:

```yaml
User:
  type: object
  required:
    - id
    - password
    - name
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    password:
      type: string
      writeOnly: true
    name:
      type: string
```

Diễn giải:

- `id` được yêu cầu trong response, không phải trường client cần gửi khi tạo người dùng.
- `password` được yêu cầu trong request, không phải trường server cần trả về.
- `name` được yêu cầu theo schema dùng chung; nó không bị giới hạn một chiều.

Quy tắc này giúp một schema dùng chung mô tả được hai hướng trao đổi. Tuy nhiên, công cụ sinh client, validator hoặc giao diện có thể hỗ trợ khác nhau đối với schema dùng chung có trường read-only/write-only. Khi request và response khác nhau đáng kể, hai schema riêng thường dễ hiểu và ổn định hơn.

## 4. `accessMode` trong annotation `@Schema`

Swagger Annotations cung cấp `Schema.AccessMode` để khai báo hướng truy cập của thuộc tính Java. Springdoc sử dụng metadata này khi xây dựng Schema Object.

Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| `Schema.AccessMode.AUTO` | Để thư viện tự suy luận theo metadata và quy tắc mặc định |
| `Schema.AccessMode.READ_ONLY` | Mô tả thuộc tính là read-only |
| `Schema.AccessMode.WRITE_ONLY` | Mô tả thuộc tính là write-only |
| `Schema.AccessMode.READ_WRITE` | Mô tả thuộc tính có thể đọc và ghi |

Ví dụ DTO dùng chung:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public class UserDto {

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private UUID id;

    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    private String password;

    @Schema(description = "Tên hiển thị của người dùng")
    private String name;

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    private Instant createdAt;

    // getters và setters
}
```

Springdoc có thể dùng `accessMode` để sinh `readOnly: true` hoặc `writeOnly: true` trong schema tương ứng. `READ_WRITE` biểu thị thuộc tính được sử dụng theo cả hai hướng; `AUTO` để quá trình suy luận mặc định quyết định.

`@Schema(accessMode = ...)` chỉ mô tả hợp đồng OpenAPI. Nếu DTO được dùng trực tiếp để nhận và trả JSON, cần cấu hình serialization/deserialization tương ứng hoặc dùng DTO riêng để hành vi runtime không mâu thuẫn với tài liệu.

## 5. Phân biệt `@Schema(accessMode)` với Jackson `@JsonProperty(access)`

Hai annotation có mục đích liên quan nhưng tác động ở hai lớp khác nhau:

| Annotation | Thư viện/lớp | Tác động chính |
|---|---|---|
| `@Schema(accessMode = READ_ONLY)` | Swagger/OpenAPI metadata | Mô tả thuộc tính chỉ đọc trong hợp đồng |
| `@Schema(accessMode = WRITE_ONLY)` | Swagger/OpenAPI metadata | Mô tả thuộc tính chỉ ghi trong hợp đồng |
| `@JsonProperty(access = READ_ONLY)` | Jackson serialization/deserialization | Cho phép serialize ra JSON; không nhận giá trị từ JSON đầu vào |
| `@JsonProperty(access = WRITE_ONLY)` | Jackson serialization/deserialization | Nhận giá trị từ JSON đầu vào; không serialize thuộc tính ra JSON |
| `@JsonIgnore` | Jackson serialization/deserialization | Bỏ qua thuộc tính theo cấu hình và vị trí áp dụng; thường loại bỏ cả hai chiều |

Ví dụ dùng đồng thời metadata OpenAPI và Jackson:

```java
public class UserDto {

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private UUID id;

    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    private String name;

    // getters và setters
}
```

Với cấu hình Jackson tương ứng:

- `id` có thể được serialize vào response, trong khi giá trị `id` gửi từ request không được dùng để gán thuộc tính.
- `password` có thể được đọc từ request, nhưng Jackson không serialize thuộc tính này vào response.
- `name` vẫn có thể được đọc và ghi theo quy tắc mặc định.

Springdoc tích hợp với Jackson và Swagger metadata, nhưng cách hợp nhất annotation và tạo schema có thể phụ thuộc phiên bản thư viện cùng cấu hình. Hãy kiểm tra cả JSON thực tế và tài liệu được sinh. Không chỉ dựa vào việc annotation xuất hiện trong mã nguồn.

### Khi nào dùng `@JsonIgnore`?

`@JsonIgnore` thường phù hợp với thuộc tính không nên tham gia JSON theo cách Jackson đang cấu hình. Nếu một thuộc tính cần đọc ở request nhưng không được trả trong response, `JsonProperty.Access.WRITE_ONLY` diễn đạt đúng hơn. Nếu một thuộc tính cần trả về nhưng không nhận từ request, `READ_ONLY` phù hợp hơn.

Không nên thay `WRITE_ONLY` bằng `@JsonIgnore` cho mật khẩu nếu ứng dụng vẫn cần nhận mật khẩu từ request. `@JsonIgnore` có thể khiến Jackson bỏ qua thuộc tính khi deserialize, làm dữ liệu đầu vào không được gán như mong muốn.

## 6. Ví dụ đầy đủ: một DTO dùng chung cho request và response

Trong một API nhỏ, có thể dùng chung DTO nếu các thuộc tính có thể biểu diễn rõ hướng truy cập:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.UUID;

public class UserDto {

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private UUID id;

    @Schema(description = "Tên người dùng", example = "Nguyen Van A")
    @NotBlank
    private String name;

    @Schema(description = "Email đăng nhập", example = "user@example.com")
    @Email
    private String email;

    @Schema(
        description = "Mật khẩu mới, chỉ dùng khi gửi request",
        accessMode = Schema.AccessMode.WRITE_ONLY
    )
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    // getters và setters
}
```

Controller có thể sử dụng DTO:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    UserDto create(@Valid @RequestBody UserDto request) {
        return userService.create(request);
    }
}
```

Hợp đồng có thể biểu diễn các thuộc tính `id` và `createdAt` là read-only, `password` là write-only. Trong JSON thực tế, Jackson phải được cấu hình để đáp ứng cùng quy tắc đó. Tầng dịch vụ cũng cần xử lý mật khẩu an toàn, chẳng hạn băm mật khẩu trước khi lưu; việc ẩn trường khỏi response không thay thế xử lý bảo mật dữ liệu.

## 7. Khi nào nên tách request DTO và response DTO?

Một DTO dùng chung tiện lợi khi cấu trúc đơn giản, nhưng càng nhiều quy tắc theo chiều thì càng khó hiểu. Trong ứng dụng thực tế, request và response thường khác nhau về field, validation, quyền ghi và cách đặt tên. Tách DTO giúp mô tả hợp đồng rõ ràng.

```java
public class CreateUserRequest {
    @NotBlank
    private String name;

    @Email
    private String email;

    @NotBlank
    private String password;

    // getters và setters
}
```

```java
public class UserResponse {
    private UUID id;
    private String name;
    private String email;
    private Instant createdAt;

    // getters và setters
}
```

Controller:

```java
@PostMapping
ResponseEntity<UserResponse> create(
        @Valid @RequestBody CreateUserRequest request) {
    UserResponse response = userService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
```

Springdoc có thể tạo hai schema riêng: `CreateUserRequest` cho request body và `UserResponse` cho response. Client thấy chính xác trường cần gửi và trường nhận được, không phải suy luận dựa trên `readOnly`/`writeOnly`.

Tách DTO đặc biệt hữu ích khi:

- Request và response có số lượng thuộc tính khác nhau đáng kể.
- Validation đầu vào khác quy tắc dữ liệu trả về.
- Có dữ liệu nhạy cảm chỉ nhận một chiều.
- API có nhiều thao tác cập nhật, tạo mới và đọc với tập field khác nhau.
- Cần giữ schema ổn định cho client generator hoặc nhiều nhóm tiêu thụ API.

`@Schema(accessMode)` vẫn hữu ích cho thuộc tính một chiều trong schema dùng chung hoặc khi cần nhấn mạnh hướng sử dụng. Tuy nhiên, không cần ép mọi API dùng một DTO duy nhất chỉ để tận dụng annotation này.

## 8. `readOnly` và `writeOnly` không phải cơ chế phân quyền

Các thuộc tính hướng truy cập mô tả dữ liệu trong hợp đồng, không thay thế bảo vệ ở server.

Ví dụ, client gửi `id` trong request dù schema đánh dấu read-only. Server phải quyết định bỏ qua, từ chối hoặc xử lý theo quy tắc cụ thể. Không được tin giá trị ID do client tự gửi nếu ID phải do hệ thống tạo hoặc xác định từ danh tính đã xác thực.

Tương tự, `writeOnly` không làm cho dữ liệu tự động an toàn. Mật khẩu vẫn có thể xuất hiện trong log request, exception message, trace, audit event hoặc bản ghi nếu ứng dụng ghi lại không đúng cách. Cần kiểm soát log, lưu trữ, truyền tải và vòng đời dữ liệu nhạy cảm.

Một số nguyên tắc:

- Không trả mật khẩu, token bí mật hoặc mã xác thực dùng một lần trong response.
- Không tin các trường read-only do client gửi để quyết định ID, vai trò, thời điểm tạo hoặc chủ sở hữu tài nguyên.
- Kiểm tra quyền ở service/controller/security layer; schema không thực hiện authorization.
- Không đưa giá trị bí mật thật vào `example` hoặc `default` của OpenAPI.
- Dùng DTO đầu vào được cho phép rõ ràng để tránh mass assignment các thuộc tính nội bộ.
- Kiểm tra JSON response thực tế để chắc chắn dữ liệu một chiều không bị serialize nhầm.

## 9. Ảnh hưởng đến `required`, validation và ví dụ

Một trường write-only có thể bắt buộc trong request nhưng không xuất hiện trong response. Ví dụ, `password` bắt buộc khi tạo tài khoản, nhưng không có trong response. Ngược lại, `id` có thể bắt buộc trong response vì server luôn trả ID, nhưng client không phải gửi ID khi tạo mới.

Khi dùng một schema chung, OpenAPI có thể dùng `required` kết hợp `readOnly`/`writeOnly` để diễn đạt sự khác nhau này. Tuy nhiên, validation trong Java cần đặt ở đúng DTO hoặc validation group để phù hợp với thao tác thực tế.

Ví dụ, nếu một DTO dùng cho cả tạo mới và cập nhật, password có thể bắt buộc khi tạo nhưng tùy chọn khi cập nhật. Một `@NotBlank` đơn giản trên cùng thuộc tính có thể không diễn đạt được cả hai quy tắc. Có thể dùng:

- DTO riêng `CreateUserRequest` và `UpdateUserRequest`.
- Bean Validation groups nếu có lý do duy trì một DTO.
- Các operation và schema riêng để công bố rõ yêu cầu theo từng thao tác.

`example` nên minh họa dữ liệu hợp lệ nhưng không dùng bí mật thực. Với thuộc tính write-only, có thể dùng placeholder như `example-secret` hoặc mô tả định dạng mà không công bố credential có thể sử dụng.

## 10. Kiểm tra schema và JSON runtime

Sau khi thêm `accessMode`, cần kiểm tra cả hai mặt của hợp đồng:

1. Mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`.
2. Tìm schema trong `components.schemas` và kiểm tra thuộc tính có `readOnly: true` hoặc `writeOnly: true` theo mong đợi.
3. Kiểm tra trường nào nằm trong danh sách `required` và ý nghĩa theo chiều request/response.
4. Gửi request có trường write-only để xác nhận Jackson bind đúng.
5. Gửi request có trường read-only để xác nhận ứng dụng bỏ qua hoặc từ chối theo chính sách đã chọn.
6. Kiểm tra response JSON không chứa trường write-only.
7. Kiểm tra response có chứa các trường read-only cần thiết.
8. Chạy OpenAPI validator và thử Swagger UI/client generator nếu các công cụ này được dùng trong dự án.

Ví dụ kiểm tra bằng request/response:

```text
POST /api/users
Content-Type: application/json

{
  "name": "Nguyen Van A",
  "email": "user@example.com",
  "password": "example-secret"
}
```

Response mong đợi không chứa `password`:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Nguyen Van A",
  "email": "user@example.com",
  "createdAt": "2026-11-20T10:00:00Z"
}
```

Nếu Swagger UI hiển thị đúng `writeOnly` nhưng response vẫn có password, metadata OpenAPI đã đúng nhưng Jackson/runtime chưa được kiểm soát. Nếu Jackson không trả password nhưng schema lại không đánh dấu write-only, payload runtime an toàn hơn tài liệu nhưng hợp đồng vẫn chưa diễn đạt đúng. Cần đồng bộ cả hai.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI không đánh dấu trường read-only | Thiếu `@Schema(accessMode = READ_ONLY)` hoặc metadata không được nhận diện | Kiểm tra import, annotation và schema được sinh |
| Password vẫn xuất hiện trong response | Chỉ dùng `@Schema(WRITE_ONLY)` mà Jackson vẫn serialize field | Dùng `@JsonProperty(access = WRITE_ONLY)` hoặc DTO response riêng |
| Client gửi ID nhưng server vẫn dùng giá trị đó | Chỉ đánh dấu read-only trong OpenAPI, không kiểm soát binding | Dùng Jackson access mode, DTO riêng và xác thực ở tầng nghiệp vụ |
| Trường bị bỏ qua cả request lẫn response | Dùng `@JsonIgnore` cho field cần nhận một chiều | Cân nhắc `JsonProperty.Access.WRITE_ONLY` hoặc `READ_ONLY` |
| Required không đúng theo request/response | Dùng schema chung nhưng chưa xét hướng truy cập hoặc validation | Tách DTO hoặc kiểm tra `required` và access metadata |
| Tạo mới và cập nhật có validation khác nhau | Dùng chung DTO với một bộ constraint | Tạo DTO riêng hoặc dùng validation groups có chủ đích |
| Schema request và response quá phức tạp | DTO dùng chung có nhiều field chỉ một chiều | Tách `CreateRequest`, `UpdateRequest` và `Response` |

## 12. Nguyên tắc thiết kế

- Dùng `readOnly` cho dữ liệu server trả về nhưng client không nên gửi, như ID và timestamp do server quản lý.
- Dùng `writeOnly` cho dữ liệu client gửi nhưng server không nên trả, như password hoặc secret đầu vào.
- Dùng `@Schema(accessMode = ...)` để mô tả hợp đồng OpenAPI.
- Dùng Jackson `@JsonProperty(access = ...)` hoặc DTO riêng để điều khiển JSON runtime.
- Không nhầm `@Schema` với cơ chế phân quyền, validation hoặc bảo vệ bí mật.
- Phân biệt `required` theo chiều request và response; không bắt client gửi trường read-only.
- Tách request DTO và response DTO khi cấu trúc hoặc validation khác nhau đáng kể.
- Không dùng `@JsonIgnore` nếu vẫn cần nhận hoặc trả thuộc tính theo một chiều.
- Kiểm tra schema được sinh, JSON request/response thực tế và hành vi của client generator.

## Kết luận

`readOnly`, `writeOnly` và `Schema.AccessMode` giúp OpenAPI diễn đạt thuộc tính chỉ xuất hiện ở một chiều trao đổi. Springdoc sử dụng metadata `@Schema(accessMode = ...)` để mô tả hợp đồng; Jackson `@JsonProperty(access = ...)` mới tác động đến việc đọc và ghi JSON trong runtime. Khi thiết kế API Spring Boot, hãy chọn đúng annotation cho từng lớp, tách request/response DTO nếu cần, và kiểm tra cả tài liệu OpenAPI lẫn payload thực tế để bảo đảm trường nhạy cảm hoặc trường do server quản lý không đi sai chiều.
