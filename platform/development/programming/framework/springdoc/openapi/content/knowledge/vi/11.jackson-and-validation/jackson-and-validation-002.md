# `@JsonProperty`, `@JsonIgnore` và cách đối chiếu với `@Schema`

Trong một API Spring Boot, tên thuộc tính Java không nhất thiết là tên thuộc tính JSON mà client nhìn thấy. Jackson quyết định cách object được chuyển thành JSON response và cách JSON request được chuyển thành Java object. Springdoc-openapi đọc metadata của model, bao gồm nhiều annotation Jackson, để tạo schema OpenAPI. Annotation `@Schema` bổ sung thông tin cho tài liệu như mô tả, ví dụ, trạng thái chỉ đọc hoặc chỉ ghi.

Ba annotation thường được dùng cùng nhau nhưng có vai trò khác nhau:

- `@JsonProperty` điều khiển tên và quyền đọc/ghi của thuộc tính trong quá trình Jackson xử lý JSON.
- `@JsonIgnore` loại thuộc tính khỏi quá trình tuần tự hóa và/hoặc giải tuần tự hóa theo cấu hình annotation.
- `@Schema` mô tả cách thuộc tính xuất hiện trong hợp đồng OpenAPI; nó không tự thay đổi JSON runtime của Jackson.

Khi xây dựng tài liệu API, cần đối chiếu cả JSON thực tế lẫn `/v3/api-docs`. Nếu chỉ nhìn DTO Java hoặc Swagger UI, có thể bỏ sót trường hợp tên JSON bị đổi, thuộc tính bị bỏ qua hoặc một field chỉ xuất hiện ở request hay response.

## 1. Luồng từ DTO Java đến JSON và OpenAPI

Một request/response đi qua các bước chính:

1. Controller nhận hoặc trả về một kiểu Java.
2. Với request body, Jackson dùng `ObjectMapper` và các cấu hình/annotation để chuyển JSON thành object Java.
3. Với response body, Jackson dùng `ObjectMapper` để chuyển object Java thành JSON.
4. Springdoc phân tích mapping, kiểu Java, Jackson metadata và Swagger Annotations để tạo schema trong OpenAPI.
5. Swagger UI và các client generator dùng schema đó để hiển thị hoặc tạo request/response.

Có thể hình dung mối quan hệ như sau:

```mermaid
flowchart TD
    A[DTO Java và Jackson annotations] --> B[Jackson ObjectMapper]
    B --> C[JSON request/response thực tế]
    A --> D[springdoc-openapi]
    D --> E[OpenAPI Schema]
    F[@Schema metadata] --> D
    E --> G[Swagger UI và client generator]
    C --> H[Đối chiếu hợp đồng]
    G --> H
```

Jackson quyết định dữ liệu được đọc/ghi ở runtime. Springdoc mô tả hợp đồng dựa trên thông tin mà nó nhận diện được. `@Schema` giúp bổ sung ý nghĩa còn thiếu hoặc điều chỉnh metadata tài liệu. Ba phần này cần nhất quán.

## 2. Đổi tên thuộc tính JSON bằng `@JsonProperty`

### 2.1. Tên Java và tên JSON

Giả sử DTO có thuộc tính Java `displayName`, nhưng API muốn sử dụng key `display_name`:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class UserResponse {

    @JsonProperty("display_name")
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Jackson dùng tên `display_name` khi ghi JSON và nhận key đó khi đọc JSON, theo access mode mặc định của thuộc tính. Response có dạng:

```json
{
  "display_name": "Nguyen An"
}
```

Request body tương ứng cũng gửi key `display_name`:

```json
{
  "display_name": "Nguyen An"
}
```

Trong OpenAPI, tên property cũng nên là `display_name`. Springdoc có thể đọc `@JsonProperty` để mô tả đúng tên JSON mà Jackson sử dụng.

### 2.2. Dùng với Java record

Với record, có thể đặt annotation trên record component:

```java
public record CreateUserRequest(
        @JsonProperty("display_name") String displayName,
        @JsonProperty("email_address") String emailAddress
) {}
```

JSON được mong đợi:

```json
{
  "display_name": "Nguyen An",
  "email_address": "an@example.com"
}
```

Record component được Jackson hỗ trợ trong các phiên bản phù hợp. Với dự án đang dùng Jackson cũ hoặc có cấu hình custom visibility, hãy kiểm thử serialization/deserialization thực tế thay vì chỉ dựa vào ví dụ.

### 2.3. `@JsonProperty` và naming strategy

Jackson có thể áp dụng naming strategy ở cấp `ObjectMapper`, ví dụ chuyển `displayName` thành `display_name` cho toàn bộ DTO. `@JsonProperty("display_name")` khai báo tên tường minh cho thuộc tính cụ thể và giúp hợp đồng dễ nhận biết.

Nếu dự án đã cấu hình `PropertyNamingStrategies.SNAKE_CASE`, không nhất thiết phải thêm `@JsonProperty` vào mọi field. Dùng annotation khi tên JSON khác quy tắc chung, cần giữ tên ổn định hoặc muốn thể hiện rõ một tên wire-format đặc biệt.

Ví dụ naming strategy:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder.propertyNamingStrategy(
            PropertyNamingStrategies.SNAKE_CASE
    );
}
```

Khi naming strategy và `@JsonProperty` cùng tác động, hãy kiểm tra JSON đầu ra từ chính `ObjectMapper` mà Spring sử dụng. Cũng cần kiểm tra schema do springdoc tạo ra để bảo đảm tên property không bị lệch.

### 2.4. `@Schema(name = ...)` không thay thế `@JsonProperty`

Không dùng `@Schema(name = "display_name")` với kỳ vọng Jackson sẽ đổi key JSON. `@Schema` là metadata OpenAPI; nó không cấu hình quá trình tuần tự hóa. Để đổi tên thuộc tính JSON, dùng `@JsonProperty` hoặc naming strategy của Jackson.

Có thể kết hợp hai annotation:

```java
public record UserResponse(
        @JsonProperty("display_name")
        @Schema(description = "Tên hiển thị của người dùng", example = "Nguyen An")
        String displayName
) {}
```

Ở đây `@JsonProperty` xác định key JSON; `@Schema` bổ sung mô tả và ví dụ cho key đó trong OpenAPI.

## 3. Ẩn thuộc tính khỏi JSON bằng `@JsonIgnore`

`@JsonIgnore` đánh dấu một thuộc tính mà Jackson không nên xử lý như một property JSON thông thường. Cách dùng phổ biến là loại trường nội bộ hoặc dữ liệu nhạy cảm khỏi cả quá trình ghi và đọc JSON:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class UserAccount {

    private String username;

    @JsonIgnore
    private String passwordHash;

    // getters và setters
}
```

Khi serialize, `passwordHash` không xuất hiện trong JSON response. Khi deserialize, JSON gửi key tương ứng cũng không được bind vào property bị ignore theo cấu hình mặc định của annotation.

Response:

```json
{
  "username": "an.nguyen"
}
```

Springdoc thường loại property bị Jackson ignore khỏi schema. Điều này giúp tài liệu phản ánh cấu trúc JSON mà Jackson thực sự công bố.

### 3.1. `@JsonIgnore` không phải cơ chế phân quyền

Ẩn một field khỏi JSON không thay thế kiểm soát truy cập dữ liệu ở tầng service hoặc security. Nếu dữ liệu nhạy cảm không được phép xuất hiện trong response, nên thiết kế response DTO chỉ chứa các trường được phép công bố. Không dựa vào việc client không nhìn thấy property trong Swagger UI để bảo vệ dữ liệu.

Tương tự, nếu `passwordHash` bị ignore trong request DTO, client không thể dùng JSON thông thường để gán thuộc tính đó. Tuy nhiên, mật khẩu đầu vào thường là dữ liệu write-only và cần một field riêng, được xác thực rồi băm ở server; không dùng chung field lưu hash nội bộ làm field nhận mật khẩu thô.

### 3.2. Khi cần chỉ đọc hoặc chỉ ghi, không nên ignore toàn bộ

Nếu một thuộc tính cần được gửi trong request nhưng không được trả trong response, hoặc ngược lại, `@JsonIgnore` có thể quá mạnh vì nó loại property khỏi cả hai chiều theo cách dùng thông thường. Hãy cân nhắc `@JsonProperty(access = ...)` ở phần tiếp theo.

## 4. Điều khiển hướng dữ liệu bằng `@JsonProperty(access = ...)`

`@JsonProperty` có thuộc tính `access` để chỉ rõ một property được đọc vào Java hay ghi ra JSON theo hướng nào:

| Access mode | Jackson khi serialize response | Jackson khi deserialize request |
|---|---|---|
| `AUTO` | Theo quy tắc thông thường | Theo quy tắc thông thường |
| `READ_ONLY` | Có thể ghi property ra JSON | Không nhận giá trị từ JSON để gán property đó |
| `WRITE_ONLY` | Không ghi property ra JSON | Nhận giá trị từ JSON |
| `READ_WRITE` | Ghi property ra JSON | Nhận giá trị từ JSON |

Tên `READ_ONLY` và `WRITE_ONLY` được nhìn từ góc độ của Jackson: đọc từ object để ghi JSON hoặc ghi vào object khi đọc JSON. Với API, điều đó tương ứng response-only và request-only.

### 4.1. Trường chỉ xuất hiện trong response

Ví dụ `id` do server tạo, client không được gán khi tạo mới:

```java
public record UserDto(
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        UUID id,
        String displayName
) {}
```

Jackson có thể serialize `id` trong response nhưng bỏ qua giá trị `id` gửi trong request. Khi mô tả OpenAPI, property này phù hợp với `readOnly: true`.

### 4.2. Trường chỉ nhận trong request

Ví dụ mật khẩu khi tạo tài khoản:

```java
public record CreateAccountRequest(
        String username,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password
) {}
```

Jackson nhận `password` từ request body để ứng dụng xử lý, nhưng không ghi thuộc tính này ra JSON khi object được serialize. Trong OpenAPI, property này phù hợp với `writeOnly: true`.

Không trả lại mật khẩu thô trong response, kể cả khi request đã nhận thành công. Hãy dùng response DTO riêng để công bố đúng các trường cần thiết.

## 5. Đối chiếu access mode với `@Schema`

OpenAPI Schema Object có hai metadata quan trọng:

- `readOnly: true`: thuộc tính được xem là chỉ đọc, thường được gửi từ server về client.
- `writeOnly: true`: thuộc tính được xem là chỉ ghi, thường được client gửi lên server.

Swagger Annotations biểu diễn chúng bằng `@Schema(accessMode = ...)`:

```java
public record CreateAccountRequest(
        String username,

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.WRITE_ONLY,
                description = "Mật khẩu mới; chỉ được gửi trong request"
        )
        String password
) {}
```

`@JsonProperty(access = WRITE_ONLY)` định hình hành vi Jackson. `@Schema(accessMode = WRITE_ONLY)` nói với consumer OpenAPI rằng thuộc tính là write-only. Dùng cả hai khi cần làm rõ hai lớp hợp đồng và bảo đảm giá trị nhất quán.

Tương tự với trường chỉ đọc:

```java
public record UserResponse(
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.READ_ONLY,
                description = "Mã người dùng do hệ thống cấp"
        )
        UUID id,
        String displayName
) {}
```

Springdoc có thể suy ra một số metadata từ Jackson access mode, nhưng hành vi cụ thể còn phụ thuộc phiên bản springdoc, Swagger Core và cách model được phân tích. Nếu schema là phần quan trọng của hợp đồng, hãy kiểm tra `readOnly`/`writeOnly` trong `/v3/api-docs`.

### 5.1. `@Schema(hidden = true)` khác với `@JsonIgnore`

`@Schema(hidden = true)` ẩn thuộc tính khỏi tài liệu OpenAPI. Nó không yêu cầu Jackson loại thuộc tính khỏi JSON runtime.

```java
public class InternalUserView {

    private String username;

    @Schema(hidden = true)
    private String internalNote;

    // getters và setters
}
```

Trong trường hợp này, Jackson vẫn có thể serialize `internalNote` nếu không có cấu hình khác. Swagger UI có thể không hiển thị property đó, nhưng JSON response vẫn có thể chứa nó. Nếu property không được phép đi ra khỏi server, dùng response DTO phù hợp hoặc cấu hình Jackson như yêu cầu runtime; không chỉ ẩn schema.

Ngược lại, `@JsonIgnore` tác động đến JSON runtime và springdoc thường phản ánh việc property bị bỏ qua. Không cần thêm `@Schema(hidden = true)` chỉ để lặp lại cùng một mục đích, trừ khi có lý do tài liệu riêng.

## 6. Chọn annotation theo yêu cầu API

| Yêu cầu | Annotation phù hợp | Tác động chính |
|---|---|---|
| Đổi `displayName` thành key `display_name` trong JSON | `@JsonProperty("display_name")` | Jackson đổi tên thuộc tính JSON; springdoc có thể phản ánh tên đó. |
| Loại hẳn một property khỏi JSON | `@JsonIgnore` | Jackson bỏ qua property; springdoc thường bỏ property khỏi schema. |
| Chỉ trả `id` trong response | `@JsonProperty(access = READ_ONLY)` | Jackson serialize nhưng không nhận giá trị từ JSON request. |
| Chỉ nhận `password` trong request | `@JsonProperty(access = WRITE_ONLY)` | Jackson nhận request nhưng không serialize property. |
| Đánh dấu property read-only/write-only trong hợp đồng | `@Schema(accessMode = READ_ONLY/WRITE_ONLY)` | Thêm `readOnly`/`writeOnly` cho OpenAPI. |
| Ẩn property khỏi tài liệu nhưng vẫn giữ JSON runtime | `@Schema(hidden = true)` | Chỉ ảnh hưởng tài liệu OpenAPI. |
| Thêm mô tả, ví dụ, format hoặc giới hạn | `@Schema(...)` | Bổ sung metadata schema; không đổi JSON runtime. |

Quy tắc thực hành:

- Dùng annotation Jackson để định nghĩa JSON thực tế.
- Dùng `@Schema` để mô tả ý nghĩa và giới hạn của hợp đồng.
- Dùng DTO request và response riêng khi hai hướng dữ liệu có cấu trúc khác nhau đáng kể.
- Tránh dùng một annotation tài liệu để cố sửa hành vi runtime hoặc dùng Jackson annotation để thay thế mô tả nghiệp vụ.

## 7. Ví dụ hoàn chỉnh với Request DTO và Response DTO riêng

Một thiết kế rõ ràng là tách DTO nhận request và DTO trả response:

```java
public record CreateUserRequest(
        @JsonProperty("display_name")
        @NotBlank
        @Schema(description = "Tên hiển thị", example = "Nguyen An")
        String displayName,

        @JsonProperty("email_address")
        @Email
        @Schema(description = "Địa chỉ email", example = "an@example.com")
        String emailAddress,

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.WRITE_ONLY,
                description = "Mật khẩu đầu vào"
        )
        @NotBlank
        String password
) {}
```

```java
public record UserResponse(
        @JsonProperty(value = "user_id", access = JsonProperty.Access.READ_ONLY)
        @Schema(description = "Mã người dùng do hệ thống cấp", accessMode = Schema.AccessMode.READ_ONLY)
        UUID id,

        @JsonProperty("display_name")
        @Schema(description = "Tên hiển thị", example = "Nguyen An")
        String displayName,

        @JsonProperty("email_address")
        String emailAddress
) {}
```

Controller:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<UserResponse> create(
            @Valid @RequestBody CreateUserRequest request) {
        UserResponse response = userService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Request JSON:

```json
{
  "display_name": "Nguyen An",
  "email_address": "an@example.com",
  "password": "secret-value"
}
```

Response JSON:

```json
{
  "user_id": "c0a8012e-7f4b-4e7a-9b8d-6e1d5a6a1234",
  "display_name": "Nguyen An",
  "email_address": "an@example.com"
}
```

Trong ví dụ này, password chỉ thuộc request DTO; response DTO không có field đó. Điều này làm cho cấu trúc dữ liệu ở hai hướng rõ ràng, dễ kiểm thử và ít phụ thuộc vào cách công cụ biểu diễn schema read/write của cùng một model.

## 8. Cách Springdoc phản ánh Jackson annotations

Springdoc dùng model converter và metadata của Jackson/Swagger để xây dựng schema. Các trường hợp phổ biến có thể được phản ánh như sau:

| Jackson metadata | JSON runtime | OpenAPI thường mong đợi |
|---|---|---|
| `@JsonProperty("display_name")` | Key là `display_name` | Property có tên `display_name`. |
| `@JsonIgnore` | Property bị bỏ qua theo hướng áp dụng | Property không xuất hiện trong schema. |
| `@JsonProperty(access = READ_ONLY)` | Ghi ra JSON, không nhận từ JSON | `readOnly: true` khi được nhận diện. |
| `@JsonProperty(access = WRITE_ONLY)` | Nhận JSON, không ghi ra JSON | `writeOnly: true` khi được nhận diện. |
| `@Schema(description = ...)` | Không đổi JSON | Có `description` trong schema. |
| `@Schema(example = ...)` | Không đổi JSON | Có ví dụ trong schema. |
| `@Schema(hidden = true)` | Không đổi JSON | Property bị ẩn khỏi tài liệu. |

Đây là kết quả mong đợi theo mục đích của các annotation, không phải cam kết rằng mọi tổ hợp annotation hoặc mọi phiên bản thư viện đều tạo output giống nhau. Jackson mixin, custom serializer/deserializer, property naming strategy, visibility configuration và model converter tùy chỉnh có thể làm thay đổi kết quả.

### 8.1. Kiểm tra schema request và response riêng

Với operation có request body và response, mở `/v3/api-docs` rồi kiểm tra:

- Schema được tham chiếu trong `requestBody.content.application/json.schema`.
- Schema response tương ứng trong `responses.<status>.content.application/json.schema`.
- Tên property đúng với JSON key thực tế.
- Field bị ignore không xuất hiện ngoài ý muốn.
- `readOnly` và `writeOnly` được đặt đúng chiều nếu dùng chung schema.
- Mô tả, ví dụ, format và validation constraint còn nguyên.

OpenAPI có thể tái sử dụng một schema qua `$ref`. Với DTO dùng chung ở nhiều operation, hãy kiểm tra xem springdoc tạo một schema chung hay các schema theo ngữ cảnh request/response, tùy cấu hình và phiên bản. Nếu một field có quy tắc khác biệt rõ rệt theo hướng dữ liệu, DTO riêng thường dễ hiểu hơn.

## 9. Kiểm tra JSON runtime bằng `ObjectMapper`

Không nên chỉ kiểm tra annotation trong source code. Hãy kiểm tra JSON thực tế bằng `ObjectMapper` được cấu hình giống ứng dụng:

```java
@SpringBootTest
class UserJsonMappingTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesJsonPropertyName() throws Exception {
        UserResponse response = new UserResponse(
                UUID.fromString("c0a8012e-7f4b-4e7a-9b8d-6e1d5a6a1234"),
                "Nguyen An",
                "an@example.com"
        );

        String json = objectMapper.writeValueAsString(response);

        assertThat(json).contains("\"user_id\"");
        assertThat(json).contains("\"display_name\"");
        assertThat(json).doesNotContain("\"displayName\"");
    }
}
```

Với `WRITE_ONLY`, kiểm tra cả hai chiều: JSON request có thể gán property, nhưng JSON được serialize từ object không chứa property đó. Với `READ_ONLY`, kiểm tra property xuất hiện trong JSON response nhưng giá trị gửi từ request không ghi đè được property theo access mode.

Nếu ứng dụng có nhiều `ObjectMapper`, custom module hoặc cấu hình theo media type, hãy inject đúng mapper mà HTTP message converter đang sử dụng. Một mapper tự tạo trong test có thể không phản ánh cấu hình runtime thật.

## 10. Kiểm thử hợp đồng OpenAPI

Có thể dùng MockMvc để lấy OpenAPI JSON và kiểm tra tên property. Ví dụ minh họa:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserOpenApiSchemaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsJsonPropertyNames() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.schemas.UserResponse.properties.display_name"
                ).exists())
                .andExpect(jsonPath(
                        "$.components.schemas.UserResponse.properties.displayName"
                ).doesNotExist());
    }
}
```

Tên schema thực tế có thể khác do cách springdoc đặt tên model hoặc cấu hình `@Schema(name = ...)`. Trong test dự án, kiểm tra đường dẫn schema đúng với tài liệu đã sinh hoặc truy cập schema qua `$ref` của operation thay vì giả định mọi model luôn có cùng tên component.

Nên có test riêng cho các trường hợp:

1. `@JsonProperty` đổi tên đúng trong JSON request và response.
2. `@JsonIgnore` loại property khỏi JSON runtime và schema.
3. `READ_ONLY`/`WRITE_ONLY` hoạt động đúng ở chiều Jackson tương ứng.
4. `@Schema(hidden = true)` ẩn property khỏi OpenAPI nhưng không bị nhầm là đã loại property khỏi JSON runtime.
5. Tài liệu OpenAPI phản ánh đúng request/response DTO sau khi thay đổi naming strategy hoặc ObjectMapper configuration.

## 11. Những trường hợp cần chú ý

### 11.1. Annotation đặt trên field, getter hoặc setter

Jackson có thể hợp nhất metadata từ field, getter, setter và constructor parameter thành một logical property. Khi cùng một property có annotation ở nhiều vị trí, kết quả phụ thuộc quy tắc introspection và cấu hình visibility. Nếu tên JSON hoặc access mode không như mong muốn, kiểm tra tất cả accessor liên quan thay vì chỉ nhìn field.

Ưu tiên đặt annotation nhất quán tại một vị trí rõ ràng theo kiểu DTO đang dùng. Với record, đặt annotation trên record component; với JavaBean, chọn field hoặc getter/setter theo quy ước của dự án.

### 11.2. `@JsonIgnore` và cấu hình hai chiều

`@JsonIgnore` thường loại property khỏi cả serialization và deserialization. Jackson có một số cách điều khiển property theo hướng, như `@JsonProperty(access = ...)` hoặc cấu hình liên quan của `@JsonIgnoreProperties` (`allowGetters`, `allowSetters`). Những cơ chế này có ý nghĩa khác nhau và cần được kiểm thử với mapper thực tế.

Nếu mục tiêu là property chỉ nhận trong request hoặc chỉ trả trong response, `@JsonProperty(access = WRITE_ONLY/READ_ONLY)` thường thể hiện ý định rõ hơn việc phối hợp `@JsonIgnore` với annotation trên accessor khác.

### 11.3. Custom serializer/deserializer

`@JsonSerialize`, `@JsonDeserialize`, `JsonSerializer` hoặc `JsonDeserializer` tùy chỉnh có thể làm JSON runtime khác với schema suy ra từ kiểu Java. Ví dụ, một object Java có thể được serialize thành chuỗi hoặc một định dạng đặc biệt. Trong trường hợp đó, cần bổ sung `@Schema(type = ..., format = ...)` hoặc customizer phù hợp để OpenAPI mô tả đúng representation thực tế.

Không mặc định rằng springdoc có thể suy ra mọi cấu trúc JSON được tạo bởi serializer tùy chỉnh. Hãy kiểm tra JSON đầu ra và schema song song.

### 11.4. `@JsonInclude` không giống `@JsonIgnore`

`@JsonInclude(Include.NON_NULL)` có thể làm Jackson bỏ qua property khi giá trị null trong quá trình serialize. Nó không đồng nghĩa property bị loại khỏi model hoặc luôn không xuất hiện. Schema vẫn có thể mô tả property đó, với tính optional/nullability tùy cấu hình.

Nếu API có thể bỏ qua property khi null, hãy phân biệt:

- Property không tồn tại trong JSON vì giá trị null và inclusion policy.
- Property không được hỗ trợ trong hợp đồng.
- Property được hỗ trợ nhưng không bắt buộc trong request.

Ba trường hợp này có ý nghĩa khác nhau với client.

## 12. Quy trình đối chiếu Jackson và OpenAPI

Khi thêm hoặc sửa annotation trên DTO, có thể làm theo quy trình sau:

1. **Xác định JSON contract**: ghi rõ key nào được nhận trong request và key nào được trả trong response.
2. **Chọn DTO phù hợp**: tách request/response nếu hai chiều có field khác nhau.
3. **Cấu hình Jackson**: dùng `@JsonProperty`, `@JsonIgnore`, access mode hoặc naming strategy để tạo đúng JSON runtime.
4. **Bổ sung OpenAPI metadata**: dùng `@Schema` cho mô tả, ví dụ, readOnly/writeOnly hoặc hidden khi cần.
5. **Kiểm tra serialization/deserialization**: dùng mapper của ứng dụng để xác nhận JSON thực tế.
6. **Kiểm tra `/v3/api-docs`**: đối chiếu property name, schema, `$ref`, access mode và constraint.
7. **Kiểm tra HTTP integration**: gửi request thực và xem response qua controller để xác nhận message converter dùng cùng cấu hình.
8. **Cập nhật test hợp đồng**: bảo vệ những tên JSON và trường dữ liệu mà client đang phụ thuộc.

## 13. Checklist review

- [ ] Tên JSON được xác định bằng `@JsonProperty` hoặc naming strategy phù hợp.
- [ ] Tên property trong OpenAPI khớp với JSON runtime.
- [ ] `@JsonIgnore` chỉ được dùng khi thực sự muốn Jackson bỏ qua property.
- [ ] Trường request-only/response-only dùng access mode phù hợp hoặc DTO riêng.
- [ ] `@Schema(accessMode = ...)` nhất quán với Jackson access mode.
- [ ] `@Schema(hidden = true)` không bị nhầm là đã ẩn dữ liệu ở runtime.
- [ ] `@Schema(name = ...)` không được dùng thay cho đổi tên JSON.
- [ ] Custom serializer/deserializer và naming strategy đã được kiểm tra.
- [ ] `/v3/api-docs` phản ánh đúng tên, hướng đọc/ghi và thuộc tính bị bỏ qua.
- [ ] Integration test kiểm tra cả JSON runtime và schema OpenAPI.

## 14. Tài liệu tham khảo

- [Jackson `@JsonProperty` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html)
- [Jackson `@JsonIgnore` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson `@JsonIgnoreProperties` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnoreProperties.html)
- [OpenAPI Specification 3.1.2 – Schema Object](https://spec.openapis.org/oas/v3.1.2.html#schema-object)
- [Swagger Annotations – `@Schema`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Schema.html)
- [springdoc-openapi FAQ](https://springdoc.org/faq.html)

`@JsonProperty` và `@JsonIgnore` định hình JSON mà Jackson thực sự đọc và ghi. `@Schema` giúp mô tả hợp đồng mà client nhìn thấy. Khi dùng đúng vai trò và kiểm tra cả JSON runtime lẫn `/v3/api-docs`, tài liệu OpenAPI sẽ phản ánh chính xác hơn tên property, trường bị loại bỏ và các thuộc tính chỉ được gửi hoặc chỉ được trả về.
