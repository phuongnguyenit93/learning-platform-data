# Kiểm tra trường nhạy cảm không xuất hiện trong phản hồi

Trong nhóm **JSON và serialization** của Spring Boot, một lỗi bảo mật dễ bỏ sót là API trả về **nhiều dữ liệu hơn hợp đồng cho phép**. Ví dụ, entity/đối tượng nghiệp vụ có `passwordHash`, `resetToken` hoặc khóa truy cập của một integration, nhưng controller trả thẳng object ấy để Jackson serialize. JSON vẫn hợp lệ, HTTP vẫn 200, và các test chỉ kiểm tra `id`/`displayName` vẫn có thể xanh — trong khi dữ liệu bí mật đã xuất hiện trong phản hồi.

**Mục tiêu của bài học:** thiết kế response theo **allowlist** và viết test bảo đảm **trường nhạy cảm thực sự không tồn tại trong JSON**, kể cả khi trường có giá trị `null`, nằm trong object lồng nhau, ở nhiều phần tử của một mảng, hoặc nằm trong phản hồi lỗi. Test phải quan sát **payload JSON cuối cùng mà client nhận**, không chỉ kiểm tra một annotation hoặc đối tượng Java trước serialization.

Các công cụ chính:

- **Response DTO/projection:** chỉ định những trường được phép xuất hiện.
- **Jackson:** `@JsonIgnore`, `@JsonProperty(access = WRITE_ONLY)`, `ObjectMapper` và `JsonNode`.
- **Spring Boot `@JsonTest`:** kiểm tra cấu trúc JSON do Jackson serialize ở phạm vi hẹp.
- **Spring MVC `@WebMvcTest` + `MockMvc`:** kiểm tra JSON của HTTP response với mapping/advice/converter đang có trong web slice.
- **`jsonPath(...).doesNotHaveJsonPath()`:** khẳng định một đường dẫn JSON **không có mặt ngay cả khi giá trị bằng `null`**.

Ví dụ dưới đây nhắm đến **Java 17+, Spring Boot 3.4/3.5, Jackson 2 và Spring Framework 6.2**. Với Spring Boot 4.x, cách chia ranh giới và phép kiểm tra vẫn hữu ích, nhưng package của một số test annotations và cách quản lý Jackson phiên bản mới có thể khác; phải dùng đúng API theo phiên bản dự án.

## 1. Xác định đúng “không xuất hiện” trước khi test

Giả sử API có hai JSON:

```json
{
  "id": 42,
  "displayName": "Linh"
}
```

và:

```json
{
  "id": 42,
  "displayName": "Linh",
  "passwordHash": null
}
```

Hai phản hồi **không tương đương** nếu hợp đồng yêu cầu `passwordHash` **không được xuất hiện**. Ở JSON thứ hai, **tên trường vẫn bị tiết lộ**, và client có thể thấy rằng hệ thống có property đó. Giá trị `null` không đáp ứng một chính sách “field forbidden”.

Do đó cần phân biệt ba loại assertion:

| Kiểm tra | Điều được chứng minh | Có chấp nhận `{"secret":null}`? |
| --- | --- | --- |
| `jsonPath("$.secret").doesNotExist()` | Không có **giá trị khác null** ở đường dẫn | **Có thể có** |
| `jsonPath("$.secret").doesNotHaveJsonPath()` | **Không có đường dẫn**, kể cả null | **Không** |
| `JsonNode.has("secret") == false` | Node object không có key đó | **Không** |

API `doesNotHaveJsonPath()` của Spring MockMvc được thiết kế cho yêu cầu “đường dẫn vắng mặt kể cả null”. Đây thường là lựa chọn chính xác hơn `doesNotExist()` khi viết security regression test về **không rò tên field**.

**Những điều test kiểu này không tự bảo đảm:** dữ liệu bí mật có thể bị đưa vào một **tên trường khác** (ví dụ `debugMessage` chứa token), bị ghi vào HTTP header, log, trace, cookie, hoặc được lộ ở endpoint khác. Ngoài việc cấm key, cần kiểm tra **schema response đầy đủ**, giá trị sentinel và các ranh giới được phép khác.

## 2. Vì sao trả thẳng entity hoặc domain object dễ nguy hiểm?

Một domain object có thể chứa nhiều loại thông tin:

```text
Account (internal)
├── id
├── displayName
├── locale
├── passwordHash          [KHÔNG TRẢ]
├── resetToken            [KHÔNG TRẢ]
├── internalNote          [KHÔNG TRẢ]
└── integrations
    ├── provider          [CÓ THỂ TRẢ]
    └── apiKey            [KHÔNG TRẢ]
```

Nếu controller làm:

```java
@GetMapping("/{id}")
public Account get(@PathVariable long id) {
    return lookup.find(id); // Anti-pattern nếu Account chứa secrets.
}
```

thì serializer có thể thấy các accessor của `Account` và biến chúng thành JSON properties. Việc kết quả JSON có bị lọc hay không sẽ phụ thuộc các annotation/configuration; **không nên dựa vào may mắn** hoặc vào việc “client hiện tại không hiển thị trường đó”.

Đặc biệt dễ gặp rủi ro khi:

- Trả thẳng JPA entity/repository result thay vì response DTO.
- Dùng `Map<String, Object>` với nhiều trường copy từ internal model.
- Trả một object có nested `credentials`/`sessions`/`integrations`.
- Dùng reflection/object mapping tự động sao chép mọi property.
- Thêm một field nhạy cảm mới vào domain model nhưng quên cập nhật test.
- Một exception handler đưa `exception.getMessage()`, stack trace hoặc internal details vào response.
- Response cho danh sách chỉ được test phần tử đầu, còn phần tử sau rò thông tin.

**Biện pháp ưu tiên:** dùng **response DTO có field allowlist**, rồi viết test ở **serializer boundary** và **HTTP boundary**. Annotation che field trên domain object có thể là lớp phòng vệ bổ sung, nhưng response DTO làm hợp đồng rõ ràng và giảm tác động của thay đổi domain.

## 3. Ba chiến lược Jackson thường gặp

### 3.1. Response DTO (nên ưu tiên)

Thay vì serialize nguyên `Account`, tạo `AccountResponse` chỉ có các phần dữ liệu được phép:

```java
public record AccountResponse(
        long id,
        String displayName,
        Meta meta,
        List<IntegrationView> integrations) {
    public record Meta(String locale) {}
    public record IntegrationView(String provider) {}
}
```

Đây là đoạn khai báo khái niệm, chưa phải source file độc lập do thiếu import `List` và hàm chuyển đổi. Phần runnable ở mục 5 có class hoàn chỉnh.

Khi một field mới `privateKey` được thêm vào `Account`, nó **không tự động xuất hiện** trong `AccountResponse`, vì response chỉ định rõ những property được xuất. Đây là đặc tính **fail-closed by design** tương đối mạnh: muốn trả thêm một trường phải sửa contract và mapping có chủ đích.

**DTO không thay thế authorization**: `displayName`, `locale` hoặc `provider` cũng có thể là dữ liệu cá nhân/nhạy cảm trong bối cảnh cụ thể. Chỉ trả chúng khi policy của endpoint cho phép, và vẫn phải kiểm tra người gọi có quyền đọc bản ghi đó.

### 3.2. @JsonIgnore: chặn property khỏi JSON theo cấu hình Jackson

Ví dụ minh họa:

```java
public class InternalUser {
    public String username;

    @JsonIgnore
    public String passwordHash;
}
```

Với Jackson 2 được cấu hình thông thường, `@JsonIgnore` có thể ngăn `passwordHash` xuất hiện trong serialization. Nhưng cần lưu ý:

- Annotation trên field/getter/record component tương tác với quy tắc property discovery của Jackson; cần test **ObjectMapper thật được ứng dụng dùng**.
- `@JsonIgnore` không đồng nghĩa “không ai có thể đọc field trong memory”, cũng không xóa dữ liệu khỏi database/log.
- Với input cần **deserialize được nhưng không serialize**, `@JsonProperty(access = WRITE_ONLY)` thường mô tả mục tiêu rõ hơn.
- Nếu chuyển sang thư viện serializer khác hoặc customize ObjectMapper, phải kiểm chứng hành vi thực tế; đừng lấy annotation làm bằng chứng duy nhất.

Đây là đoạn ví dụ class riêng, thiếu imports và không dùng trong bộ runnable phía dưới. Nếu bạn áp dụng annotation trên domain object, vẫn nên có **test JSON thực** để phòng refactor làm thay đổi property visibility.

### 3.3. @JsonProperty(access = WRITE_ONLY): nhận đầu vào, không trả đầu ra

Với request chứa password, ứng dụng có thể cần **nhận** password trong JSON để xác thực, nhưng **không được serialize lại** khi object ấy bị dùng trong output. Jackson cung cấp:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
String password
```

Tên `WRITE_ONLY` được hiểu theo **góc nhìn của property trong Java**: Jackson được **ghi** giá trị vào property khi *deserialization*, nhưng không được **đọc** property ấy để *serialization*. Nó **không** có nghĩa “cho phép client chỉ đọc password”.

| Access | Serialize object → JSON | Deserialize JSON → object |
| --- | --- | --- |
| `AUTO` | Theo visibility/config | Theo visibility/config |
| `READ_ONLY` | Có thể xuất | Không nhận từ JSON |
| `WRITE_ONLY` | **Không xuất** | Có thể nhận từ JSON |
| `READ_WRITE` | Có thể xuất | Có thể nhận |

**Lưu ý:** `WRITE_ONLY` không tự đảm bảo mật khẩu được hash, lưu an toàn, xóa khỏi logs, hoặc bảo vệ trước lỗi response mapping khác. Một request DTO chứa password có thể phù hợp để nhận input; response DTO không nên chứa password property ngay từ đầu.

### 3.4. Không dùng null-exclusion làm chính sách bảo mật

`@JsonInclude(Include.NON_NULL)` có thể bỏ **các property có giá trị null**, nhưng khi một secret field nhận giá trị khác null, nó **vẫn có thể xuất hiện**. Đó là cách chỉnh hình thức JSON, **không phải kiểm soát truy cập dữ liệu nhạy cảm**.

Cũng không nên coi `@Schema(hidden = true)` (OpenAPI documentation), `@ToString.Exclude` (tác động string representation) hoặc việc frontend bỏ qua field là các biện pháp chặn Jackson serialize. Mỗi công cụ có phạm vi riêng.

## 4. Phương pháp test mạnh: positive contract + negative contract

Một security regression test nên kiểm tra cả hai phía:

**Positive contract:**
- Endpoint trả status/media type đúng.
- Các trường được phép như `id` và `displayName` có giá trị đúng.
- Nested object và array có schema/giá trị phù hợp.
- Không vô tình xóa hết dữ liệu rồi vẫn pass negative assertion.

**Negative contract:**
- Những đường dẫn nhạy cảm **không tồn tại kể cả null**.
- Không có key cấm ở bất kỳ tầng lồng nhau nào.
- Không có giá trị sentinel nhạy cảm nằm trong một field đổi tên.
- Response không có property ngoài allowlist.
- Error response không chứa thông điệp lỗi có secret, internal SQL/JWT/token.

Một ví dụ:

```java
mvc.perform(get("/accounts/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").value("Linh"))
        .andExpect(jsonPath("$.passwordHash")
                .doesNotHaveJsonPath())
        .andExpect(jsonPath("$.integrations[0].apiKey")
                .doesNotHaveJsonPath());
```

Đây là snippet trong test đã cấu hình `MockMvc`, chưa phải class độc lập. Assertion trên `$.integrations[0].apiKey` chỉ nói về **phần tử đầu tiên**. Với danh sách nhiều phần tử, cần kiểm tra **mọi phần tử** và nested objects; không dùng một index duy nhất để khẳng định toàn bộ payload an toàn.

## 5. Ví dụ Java 17+ hoàn chỉnh: domain có secret, response chỉ có allowlist

Ta xây một API nhỏ để minh họa cách giảm dữ liệu được expose và test JSON.

**Dữ liệu nội bộ:**
- `Account` chứa `id`, `displayName`, `locale`.
- Có các trường bí mật `passwordHash`, `resetToken`, `internalNote`.
- Danh sách `Integration` gồm tên provider và `apiKey`.

**Dữ liệu được phép trả trong ví dụ:**
- `id`, `displayName`.
- `meta.locale`.
- Mảng `integrations` chỉ chứa `provider`.

**Lưu ý bảo mật:** đây là API trình diễn serialization, **chưa có cơ chế authentication/authorization**. Trong ứng dụng thật, việc cho phép ai đọc Account và thông tin provider phụ thuộc policy; không nên deploy endpoint minh họa này dưới dạng API công khai khi chưa có kiểm soát quyền.

Cấu trúc project:

```text
src/
├── main/java/example/testing/redaction/
│   ├── AccountApplication.java
│   ├── Account.java
│   ├── AccountLookup.java
│   ├── AccountResponse.java
│   ├── AccountController.java
│   ├── LoginRequest.java
│   └── AccountMappingDemo.java
└── test/java/example/testing/redaction/
    ├── AccountResponseJsonTest.java
    └── AccountControllerTest.java
```

### 5.1. Boot entrypoint: AccountApplication.java

Tạo `src/main/java/example/testing/redaction/AccountApplication.java`:

```java
package example.testing.redaction;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountApplication.class, args);
    }
}
```

Đặt class ở package gốc của ví dụ để Spring Boot tìm được configuration. **API này dùng `@WebMvcTest` với mock `AccountLookup`**, nên không bắt buộc có implementation truy cập DB trong ví dụ. Nếu muốn chạy full application qua `SpringApplication.run`, phải có một implementation bean `AccountLookup`; việc này là phạm vi wiring production riêng và không phải mục tiêu của hai test slice được cung cấp.

Đừng kết luận rằng một `@WebMvcTest` xanh chứng minh cả ứng dụng production đã có bean lookup. Mock bean trong slice chỉ chứng minh controller và serializer trong context test đã hoạt động.

### 5.2. Domain object: Account.java

Tạo `src/main/java/example/testing/redaction/Account.java`:

```java
package example.testing.redaction;

import java.util.List;

public record Account(
        long id,
        String displayName,
        String locale,
        String passwordHash,
        String resetToken,
        String internalNote,
        List<Integration> integrations) {

    public Account {
        integrations = List.copyOf(integrations);
    }

    public record Integration(
            String provider,
            String apiKey) {
    }
}
```

Đây là record Java 17 với các accessor tự sinh. **Không serialize `Account` trực tiếp ra HTTP response**: nếu Jackson nhìn thấy record components, các trường `passwordHash`, `resetToken`, `internalNote` và `integrations[*].apiKey` có thể thành JSON properties.

`List.copyOf` giữ bản copy không thể sửa qua reference của record. Ví dụ giả định `integrations` không null, danh sách không chứa phần tử null và dữ liệu đầu vào đã được kiểm tra trước đó; nếu domain production cho phép null, cần chính sách normalization rõ và test riêng. Điều này không phải cơ chế bảo mật của serializer.

### 5.3. Dependency: AccountLookup.java

Tạo `src/main/java/example/testing/redaction/AccountLookup.java`:

```java
package example.testing.redaction;

import java.util.List;

public interface AccountLookup {
    Account find(long id);
    List<Account> list();
}
```

Đây là một **port/interface**. Trong `@WebMvcTest`, `@MockitoBean` cung cấp mock để controller có dependency. Production cần một adapter/service implementation thật nếu ứng dụng được boot đầy đủ.

### 5.4. Response DTO: AccountResponse.java

Tạo `src/main/java/example/testing/redaction/AccountResponse.java`:

```java
package example.testing.redaction;

import java.util.List;

public record AccountResponse(
        long id,
        String displayName,
        Meta meta,
        List<IntegrationView> integrations) {

    public AccountResponse {
        integrations = List.copyOf(integrations);
    }

    public static AccountResponse from(Account account) {
        List<IntegrationView> visibleIntegrations =
                account.integrations().stream()
                        .map(item ->
                                new IntegrationView(item.provider()))
                        .toList();

        return new AccountResponse(
                account.id(),
                account.displayName(),
                new Meta(account.locale()),
                visibleIntegrations);
    }

    public record Meta(String locale) {
    }

    public record IntegrationView(String provider) {
    }
}
```

**Vì sao đây là allowlist?** Response record chỉ có 4 components ở top level. Nested `Meta` chỉ có `locale`; `IntegrationView` chỉ có `provider`. Không có `passwordHash`, `resetToken`, `internalNote` hoặc `apiKey` để Jackson serialize.

Việc mapping được viết rõ thay vì copy tất cả properties. Nếu sau này Account thêm `secretKey`, output không tự xuất property mới. Nếu thật sự muốn trả thêm một field, phải chủ động thay `AccountResponse` và test response contract.

**Không thể chỉ dựa vào type để giải quyết authorization:** account id, display name, locale và danh sách provider có thể cũng cần bảo vệ theo quyền. Thiết kế DTO là một lớp bảo vệ **hình dạng response**, không phải toàn bộ chính sách data access.

### 5.5. Controller thật: AccountController.java

Tạo `src/main/java/example/testing/redaction/AccountController.java`:

```java
package example.testing.redaction;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final AccountLookup lookup;

    public AccountController(AccountLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public AccountResponse detail(@PathVariable long id) {
        return AccountResponse.from(lookup.find(id));
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public List<AccountResponse> list() {
        return lookup.list().stream()
                .map(AccountResponse::from)
                .toList();
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiError invalidRequest(
            IllegalArgumentException exception) {
        // Cố ý không serialize exception.getMessage().
        return new ApiError("INVALID_ACCOUNT_REQUEST");
    }

    public record ApiError(String code) {
    }
}
```

Trong ví dụ, `@ExceptionHandler` trả một error code cố định, **không đưa raw exception message ra JSON**. Điều này ngăn một thông báo lỗi có chứa token/SQL/internal detail xuất hiện chỉ vì service ném exception có message không phù hợp. Với ứng dụng thực, error response nên áp dụng policy nhất quán cho các loại exception khác, kể cả framework errors và global `@RestControllerAdvice`.

**Quan trọng:** test ở mục tiếp theo kiểm tra response HTTP trong MVC test slice. Nó không kiểm tra authentication, authorization hoặc quyền xem Account ID; những ranh giới đó cần test riêng.

### 5.6. Input DTO và WRITE_ONLY: LoginRequest.java

Tạo `src/main/java/example/testing/redaction/LoginRequest.java`:

```java
package example.testing.redaction;

import com.fasterxml.jackson.annotation.JsonProperty;

public record LoginRequest(
        String username,
        @JsonProperty(
                access = JsonProperty.Access.WRITE_ONLY)
        String password) {
}
```

Đây là **input DTO** để minh họa Jackson access. Với Jackson 2 hỗ trợ Java record, JSON có thể được deserialize vào field `password`, nhưng serialization của `LoginRequest` không được xuất key ấy.

**Không gửi `LoginRequest` lại cho client như response trong thiết kế thật.** `WRITE_ONLY` chỉ là lớp phòng vệ thêm; response vẫn nên có DTO riêng. Nếu bạn cần một password reset/secret exchange endpoint, không nên echo những dữ liệu đó dù đã có annotation.

### 5.7. Java thuần demo, không cần Spring/Jackson: AccountMappingDemo.java

Tạo `src/main/java/example/testing/redaction/AccountMappingDemo.java`:

```java
package example.testing.redaction;

import java.util.List;

public class AccountMappingDemo {
    public static void main(String[] args) {
        Account account = new Account(
                42L,
                "Linh",
                "vi-VN",
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(
                        new Account.Integration(
                                "billing", "KEY_TEST_ONLY"),
                        new Account.Integration(
                                "analytics", "KEY_TEST_ONLY")));

        AccountResponse response =
                AccountResponse.from(account);

        System.out.println(response.id());
        System.out.println(response.displayName());
        System.out.println(response.meta().locale());
        System.out.println(
                response.integrations().stream()
                        .map(AccountResponse
                                .IntegrationView::provider)
                        .toList());
    }
}
```

Biên dịch và chạy từ thư mục gốc project:

```bash
javac -d out src/main/java/example/testing/redaction/Account.java src/main/java/example/testing/redaction/AccountResponse.java src/main/java/example/testing/redaction/AccountMappingDemo.java
java -cp out example.testing.redaction.AccountMappingDemo
```

Stdout chính xác:

```text
42
Linh
vi-VN
[billing, analytics]
```

Đây là **demo Java thuần** về mapping DTO, không phải test JSON serialization vì nó không tải Jackson/Spring. Những giá trị `HASH_TEST_ONLY`, `RESET_TEST_ONLY`, `KEY_TEST_ONLY` chỉ là **sentinel thử nghiệm**, không phải mật khẩu/token thật. Mục tiêu là cho thấy mapper chỉ chuyển dữ liệu được phép, không vô tình đưa secret vào các property hiển thị.

## 6. @JsonTest: kiểm tra schema do Jackson serialize

Tạo `src/test/java/example/testing/redaction/AccountResponseJsonTest.java`:

```java
package example.testing.redaction;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class AccountResponseJsonTest {

    @Autowired
    private ObjectMapper mapper;

    @Test
    void responseHasExactlyTheAllowedJsonProperties()
            throws Exception {
        Account domain = new Account(
                42L, "Linh", "vi-VN",
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(new Account.Integration(
                        "billing", "KEY_TEST_ONLY")));

        JsonNode actual = mapper.readTree(
                mapper.writeValueAsString(
                        AccountResponse.from(domain)));

        JsonNode expected = mapper.readTree("""
                {
                  "id": 42,
                  "displayName": "Linh",
                  "meta": {"locale": "vi-VN"},
                  "integrations": [{"provider": "billing"}]
                }
                """);

        assertEquals(expected, actual);
        assertFalse(actual.has("passwordHash"));
        assertFalse(actual.has("resetToken"));
        assertFalse(actual.has("internalNote"));
        assertFalse(actual.path("integrations")
                .get(0).has("apiKey"));
    }

    @Test
    void writeOnlyPasswordCanBeReadButNotSerialized()
            throws Exception {
        LoginRequest input = mapper.readValue(
                """
                {"username":"demo","password":"PASS_TEST_ONLY"}
                """,
                LoginRequest.class);

        assertEquals("demo", input.username());
        assertEquals("PASS_TEST_ONLY", input.password());

        JsonNode serialized = mapper.readTree(
                mapper.writeValueAsString(input));

        assertEquals("demo",
                serialized.path("username").asText());
        assertFalse(serialized.has("password"));
    }

    @Test
    void jsonNullIsDifferentFromAbsentProperty()
            throws Exception {
        JsonNode node = mapper.readTree("""
                {"id":42,"resetToken":null}
                """);

        assertTrue(node.has("resetToken"));
        assertFalse(node.hasNonNull("resetToken"));
        assertFalse(node.has("passwordHash"));
    }
}
```

**Tại sao test này quan trọng?**

- `@JsonTest` tạo một Spring Boot **JSON slice**, đủ để test Jackson serialization theo cấu hình có trong slice, nhưng không khởi động toàn bộ MVC server hay database.
- `ObjectMapper.writeValueAsString(...)` tạo JSON thực; `readTree(...)` biến nó thành cây để kiểm tra keys/values.
- `assertEquals(expected, actual)` trên hai `JsonNode` xác minh **cấu trúc output chính xác**. Nếu serializer thêm một key mới, dù key đó không thuộc danh sách nhạy cảm hiện biết, assertion sẽ thất bại.
- Test `WRITE_ONLY` kiểm chứng **cả chiều deserialize lẫn serialize**, thay vì chỉ nhìn annotation.
- Test `null` cho thấy `JsonNode.has(...)` trả true khi key tồn tại với value `null`, còn `hasNonNull(...)` trả false. Chính sách “không xuất hiện” phải kiểm tra `has(...) == false`.

**Giới hạn:** JSON slice chứng minh hành vi mapper trong context test, không tự chứng minh endpoint HTTP đang dùng đúng DTO, đúng route/role/exception handling. Vì vậy cần thêm `MockMvc` test.

Với Spring Boot 3.4/3.5, import `@JsonTest` ở `org.springframework.boot.test.autoconfigure.json.JsonTest` và Jackson 2 `ObjectMapper` ở `com.fasterxml.jackson.databind.ObjectMapper` là phù hợp. Với Spring Boot 4.x, kiểm tra module/package và Jackson version tương ứng; không trộn các thế hệ của Boot/Jackson.

## 7. @WebMvcTest + MockMvc: kiểm tra JSON thực trả ra HTTP

Tạo `src/test/java/example/testing/redaction/AccountControllerTest.java`:

```java
package example.testing.redaction;

import java.util.List;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AccountController.class)
class AccountControllerTest {

    private static final Set<String> FORBIDDEN_KEYS = Set.of(
            "passwordHash", "resetToken", "internalNote",
            "apiKey", "accessToken", "clientSecret");

    private static final Set<String> TEST_SENTINELS = Set.of(
            "HASH_TEST_ONLY", "RESET_TEST_ONLY",
            "NOTE_TEST_ONLY", "KEY_TEST_ONLY");

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @MockitoBean
    private AccountLookup lookup;

    private static Account account(
            long id, String displayName, String locale) {
        return new Account(
                id, displayName, locale,
                "HASH_TEST_ONLY",
                "RESET_TEST_ONLY",
                "NOTE_TEST_ONLY",
                List.of(new Account.Integration(
                        "billing", "KEY_TEST_ONLY")));
    }

    @Test
    void detailExposesOnlyTheAllowlistedJson()
            throws Exception {
        when(lookup.find(42L))
                .thenReturn(account(42L, "Linh", "vi-VN"));

        String json = mvc.perform(get("/accounts/42"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.displayName")
                        .value("Linh"))
                .andExpect(jsonPath("$.passwordHash")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.resetToken")
                        .doesNotHaveJsonPath())
                .andExpect(jsonPath("$.integrations[0].apiKey")
                        .doesNotHaveJsonPath())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = mapper.readTree(json);
        JsonNode expected = mapper.readTree("""
                {
                  "id": 42,
                  "displayName": "Linh",
                  "meta": {"locale": "vi-VN"},
                  "integrations": [{"provider": "billing"}]
                }
                """);

        assertEquals(expected, actual);
        assertNoSensitiveData(actual);
        verify(lookup).find(42L);
    }

    @Test
    void listChecksEveryAccountAndNestedIntegration()
            throws Exception {
        when(lookup.list()).thenReturn(List.of(
                account(42L, "Linh", "vi-VN"),
                account(43L, "Mai", "en-US")));

        String json = mvc.perform(get("/accounts"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$[0].id").value(42))
                .andExpect(jsonPath("$[1].id").value(43))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode actual = mapper.readTree(json);
        JsonNode expected = mapper.readTree("""
                [
                  {
                    "id":42,
                    "displayName":"Linh",
                    "meta":{"locale":"vi-VN"},
                    "integrations":[{"provider":"billing"}]
                  },
                  {
                    "id":43,
                    "displayName":"Mai",
                    "meta":{"locale":"en-US"},
                    "integrations":[{"provider":"billing"}]
                  }
                ]
                """);

        assertEquals(expected, actual);
        assertNoSensitiveData(actual);
        verify(lookup).list();
    }

    @Test
    void errorResponseNeverEchoesExceptionSecrets()
            throws Exception {
        when(lookup.find(0L)).thenThrow(
                new IllegalArgumentException(
                        "RESET_TEST_ONLY"));

        String json = mvc.perform(get("/accounts/0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ACCOUNT_REQUEST"))
                .andExpect(jsonPath("$.message")
                        .doesNotHaveJsonPath())
                .andReturn()
                .getResponse()
                .getContentAsString();

        assertEquals(
                mapper.readTree(
                        """
                        {"code":"INVALID_ACCOUNT_REQUEST"}
                        """),
                mapper.readTree(json));
        assertNoSensitiveData(mapper.readTree(json));
        verify(lookup).find(0L);
    }

    private static void assertNoSensitiveData(JsonNode node) {
        if (node.isObject()) {
            node.fieldNames().forEachRemaining(key -> {
                assertFalse(FORBIDDEN_KEYS.contains(key),
                        "Forbidden JSON key: " + key);
                assertNoSensitiveData(node.get(key));
            });
        } else if (node.isArray()) {
            node.forEach(
                    AccountControllerTest::assertNoSensitiveData);
        } else if (node.isTextual()) {
            for (String sentinel : TEST_SENTINELS) {
                assertFalse(node.textValue().contains(sentinel),
                        "Sensitive test value leaked");
            }
        }
    }
}
```

**Ba test ở controller kiểm tra các ranh giới khác nhau:**

1. **Chi tiết một account:** kiểm tra HTTP 200, JSON media type, các trường hợp lệ, ba đường dẫn nhạy cảm vắng mặt và **toàn bộ schema** đúng allowlist. Nếu một developer đổi controller sang `return lookup.find(id)`, kết quả JSON dư key và test sẽ đỏ.
2. **Danh sách account:** xác minh cả hai phần tử của JSON array, không chỉ `$[0]`. Hàm `assertNoSensitiveData` đi đệ quy qua **mọi object và mọi array**, phát hiện key cấm ở bất kỳ độ sâu nào.
3. **Error response:** mock dependency ném một exception với message chứa `RESET_TEST_ONLY`. Handler phải trả một code cố định, không echo message. Test so **toàn bộ JSON error** và quét sentinel để bắt lỗi leak.

Hàm đệ quy cố tình kiểm tra cả **tên key** lẫn **giá trị sentinel**. Nếu vô tình đổi `apiKey` thành `debugValue` và đưa nội dung `KEY_TEST_ONLY` vào field đó, kiểm tra key cấm có thể bỏ qua, nhưng kiểm tra giá trị sentinel và phép so schema sẽ phát hiện.

**Chú ý về `jsonPath(...).doesNotHaveJsonPath()`:** kiểm tra đường dẫn cụ thể, gồm cả trường có giá trị `null`. Nó bổ sung, không thay thế, phép so cây JSON và recursion. Nếu chỉ kiểm tra `$.integrations[0].apiKey`, các phần tử khác hoặc nested object ở vị trí khác có thể còn bí mật; đó là lý do test danh sách đi qua toàn bộ response body.

**Tại sao dùng `@MockitoBean`?** Trong `@WebMvcTest`, service/adapter ngoài MVC slice thường không được tải. `@MockitoBean` tạo hoặc thay bean `AccountLookup` để controller inject được dependency, trong khi controller và MVC serialization thật vẫn chạy. Đây là test HTTP presentation layer, **không chứng minh repository hoặc production bean lookup tồn tại**.

## 8. Cấu hình Gradle và chạy bộ ví dụ

Với **Spring Boot 3.4/3.5** đã cấu hình plugin/dependency management phù hợp, phần liên quan trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải toàn bộ build file. Java 17 cần được cấu hình trong toolchain/source compatibility của project. Với Boot 3.4/3.5, starter web cung cấp MVC + Jackson 2 và starter test cung cấp JUnit Jupiter/MockMvc test support. `@MockitoBean` thuộc Spring Framework TestContext 6.2+, nên không dùng nguyên annotation này với Spring Boot 3.3 hoặc thấp hơn.

Chạy hai class:

```bash
./gradlew test --tests example.testing.redaction.AccountResponseJsonTest
./gradlew test --tests example.testing.redaction.AccountControllerTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.redaction.AccountResponseJsonTest"
.\gradlew.bat test --tests "example.testing.redaction.AccountControllerTest"
```

**Kỳ vọng:** `AccountResponseJsonTest` có **3 test methods**; `AccountControllerTest` cũng có **3 test methods**; tổng **6 JUnit tests** đều pass khi source và dependencies đúng như ví dụ.

Các unit/slice tests không cần HTTP server thực và không cần database. Việc JUnit/Gradle hiển thị stdout cụ thể phụ thuộc runner; **không có một stdout chung chính xác** cho các lệnh `gradlew test`. Xem test report để kiểm tra tên và kết quả.

Nếu muốn chạy **full application** bằng Boot main hoặc `@SpringBootTest`, cần thêm `AccountLookup` implementation bean (và authentication/authorization nếu route dùng thật). Ví dụ ở đây intentionally giới hạn vào hai **test slices** để kiểm tra serialization contract; không nên nói “full production boot chạy được” chỉ vì các slice pass.

## 9. Kiểm tra tất cả array/nested field, không chỉ index đầu tiên

Giả sử JSON trả:

```json
[
  {"id": 42, "integrations": [{"provider": "billing"}]},
  {"id": 43, "integrations": [
    {"provider": "analytics", "apiKey": "LEAK_TEST_ONLY"}
  ]}
]
```

Một assertion duy nhất `jsonPath("$[0].integrations[0].apiKey").doesNotHaveJsonPath()` vẫn có thể **pass**, vì khóa bí mật ở phần tử thứ hai.

**Ba chiến thuật bổ sung:**

- **So full JSON với expected allowlist:** chính xác với response DTO nhỏ/ổn định, bắt mọi property ngoài contract.
- **Duyệt `JsonNode` đệ quy:** phù hợp response lồng nhiều tầng/mảng dài, bắt mọi key bị cấm; test trong mục 7 còn quét giá trị sentinel.
- **JSONPath truy hồi:** có thể dùng biểu thức kiểu `$..apiKey` và assertion đường dẫn không xuất hiện, nhưng phải hiểu cách thư viện xử lý indefinite paths/arrays; khi policy nghiêm ngặt, test đệ quy hoặc JSON schema allowlist giúp giảm rủi ro bỏ sót do cách viết expression.

Phân biệt rõ:

- `JsonNode.has(field)` → key tồn tại, kể cả nếu value null.
- `JsonNode.hasNonNull(field)` → key có value không null.
- `JsonNode.path(field)` → trả missing node khi thiếu; cần kiểm tra `isMissingNode()` thay vì chỉ gọi `asText()` có giá trị mặc định.
- `JsonNode.get(field)` → trả null Java khi không có field; không nên nhầm với `NullNode` là JSON `null`.
- `JsonPathResultMatchers.doesNotExist()` → không yêu cầu key tuyệt đối vắng mặt nếu giá trị null.
- `JsonPathResultMatchers.doesNotHaveJsonPath()` → assert vắng mặt cả null.

**Đừng dùng string matching làm phép thử duy nhất.** Tìm chuỗi `"password"` trong body có thể tạo false positive (text nội dung hợp lệ có từ “password”) hoặc false negative khi key bị đổi tên, escape, case conversion hoặc giá trị rò trong property khác. Parse JSON và đối chiếu với một schema cho phép.

## 10. Negative test để tránh xanh giả

Một test chỉ kiểm tra absence rất dễ trở thành xanh giả nếu controller vô tình trả response rỗng, HTTP status sai hoặc exception handler trả lỗi thay vì body dự kiến.

Vì vậy, viết test với một **trạng thái input có chứa secret khác null**. Nếu chỉ khởi tạo `passwordHash = null`, annotation `@JsonInclude(NON_NULL)` có thể làm test xanh, nhưng production với giá trị thật lại bị lộ. Các sentinel thử nghiệm như `HASH_TEST_ONLY` giúp đảm bảo case thực sự có dữ liệu phải bị loại bỏ.

**Phương pháp mutation tư duy:** giả sử developer vô tình sửa:

```java
// Ví dụ anti-pattern; không áp dụng trong production:
@GetMapping("/{id}")
public Account detail(@PathVariable long id) {
    return lookup.find(id);
}
```

Kết quả thường thay đổi từ:

```json
{"id":42,"displayName":"Linh","meta":{"locale":"vi-VN"},"integrations":[{"provider":"billing"}]}
```

sang một object nhiều field, có thể có:

```json
{"id":42,"displayName":"Linh","locale":"vi-VN","passwordHash":"HASH_TEST_ONLY","resetToken":"RESET_TEST_ONLY","internalNote":"NOTE_TEST_ONLY","integrations":[{"provider":"billing","apiKey":"KEY_TEST_ONLY"}]}
```

Lúc đó, phép so `JsonNode expected == actual` và quét key/sentinel **phải fail**. Đó là dấu hiệu test bảo vệ được hợp đồng, không chỉ được dựng để chạy xanh với implementation hiện tại.

Không cần đưa đoạn anti-pattern vào code production. Mục tiêu là xác định lỗi mà test sẽ bắt được khi review hoặc khi cần chứng minh độ mạnh của test bằng mutation testing.

## 11. Không trả error message, exception và debug context tùy tiện

Một nơi rò thông tin thường bị quên là **error response**:

```json
{
  "error": "Token invalid: RESET_TEST_ONLY",
  "sql": "SELECT ...",
  "internalNote": "..."
}
```

Ngay cả khi happy path trả DTO sạch, một `@RestControllerAdvice` hoặc `@ExceptionHandler` dùng `ex.getMessage()` trực tiếp có thể đưa thông tin triển khai hoặc secret vào HTTP body.

Một pattern an toàn hơn là **error code được kiểm soát**:

```java
@ExceptionHandler(IllegalArgumentException.class)
@ResponseStatus(HttpStatus.BAD_REQUEST)
public ApiError invalidRequest(
        IllegalArgumentException exception) {
    return new ApiError("INVALID_ACCOUNT_REQUEST");
}
```

Đây là đoạn lấy từ controller runnable trong mục 5.5. Đừng kết luận mọi lỗi đều phải trả cùng code; trong hệ thống thật có thể phân loại lỗi input/authorization/conflict/server error, nhưng **message public phải được chủ động thiết kế**, không auto-expose exception nội bộ.

Với Spring `ProblemDetail` hoặc cấu hình error endpoint, cần test các field `detail`, `instance` và các extension properties nếu chúng có thể chứa dữ liệu nhạy cảm. Kiểm tra **status và schema error** bằng MockMvc/WebTestClient ở đúng boundary, không chỉ test một DTO happy path.

**Logs và traces là ranh giới khác:** loại secret khỏi JSON response chưa bảo đảm logger, MDC, tracing span attributes, exception stack trace hoặc application metrics không chứa secret. Bổ sung logging/security tests hoặc chính sách masking phù hợp, nhưng không lấy chúng thay cho response-body assertions.

## 12. Phân quyền khác với field redaction

Giấu `passwordHash` không làm một endpoint trở thành an toàn nếu bất kỳ người dùng nào cũng có thể gọi `GET /accounts/42` rồi xem dữ liệu người khác.

Cần tách ít nhất ba câu hỏi:

1. **Ai được đọc resource này?** Authentication/authorization, owner check, method/URL security, tránh broken object level authorization.
2. **Người đó được nhìn thấy những trường nào?** API DTO/field-level policy theo vai trò/bối cảnh.
3. **Các field không được phép có thực sự vắng mặt sau serialization không?** `@JsonTest` và HTTP response-body assertions.

Ví dụ một endpoint “người dùng xem tài khoản của mình” cần xác minh ID từ authentication principal, không tin ID do client tùy ý gửi. Một endpoint “admin xem tài khoản” có thể cho nhiều field hơn user thông thường, nhưng vẫn không nên trả raw credentials/token.

Nếu có role-based responses, nên thiết kế **DTO cụ thể cho từng contract** hoặc mapping có policy rõ và viết test cho từng role:

| Người gọi | Trường cho phép (ví dụ) | Trường bị cấm |
| --- | --- | --- |
| Anonymous | Theo public profile policy, có thể chỉ `displayName` | Email, token, reset data, internal notes |
| Owner | Các profile fields được policy duyệt | Password hash, reset token, API key |
| Admin | Một số metadata quản trị nếu được cho phép | Raw credentials, tokens, private keys |

Bảng trên chỉ minh họa policy; ứng dụng phải có quyết định nghiệp vụ/pháp lý cụ thể. **Không tự suy ra quyền truy cập từ việc user có thể gọi URL thành công.**

## 13. Slice test so với full context và HTTP integration

| Lựa chọn | Điều chứng minh | Điều chưa chứng minh |
| --- | --- | --- |
| JUnit thuần trên `AccountResponse.from(...)` | Mapping Java không đưa field nhạy cảm vào DTO | Jackson config/HTTP body |
| `@JsonTest` | Serialization/deserialization theo mapper của JSON slice | Route, service, security filter, DB |
| `@WebMvcTest` + `MockMvc` | MVC route/controller/advice/JSON response trong web slice | Service/repository thật nếu mock; network stack |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Wiring/config rộng hơn, MVC response với bean thực trong context | Socket thật; hạ tầng ngoài bị mock |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` | HTTP qua server cổng thật trong môi trường test | Không tự bảo đảm config/DB bên ngoài giống production |

Với JSON field redaction, **bắt đầu từ test hẹp để kiểm tra schema**, rồi bổ sung ít nhất một test HTTP presentation boundary. Nếu rủi ro nằm ở cấu hình toàn ứng dụng (custom Jackson modules/mixins, global advice, security response), cần một **full-context smoke/contract test** phù hợp.

**Nếu dùng MockMvc:** nó xử lý request bằng mock servlet infrastructure, không mở cổng HTTP thật. Nó vẫn kiểm tra được body do Spring MVC/Jackson tạo ra. Không phải mọi bài “response JSON sạch” đều cần server test `RANDOM_PORT`.

**Nếu dùng Spring WebFlux:** dùng `WebTestClient` và `@WebFluxTest` hoặc integration setup tương ứng; mục tiêu vẫn là kiểm tra payload cuối cùng, kể cả nested arrays/error bodies. Không dùng MockMvc cho reactive stack như thể cùng một công cụ.

## 14. Các trường hợp đặc biệt cần quyết định rõ

### 14.1. JSON naming strategies và alias

Jackson có thể chuyển tên Java `passwordHash` thành `password_hash` theo naming strategy. Một test chỉ cấm key `passwordHash` sẽ bỏ qua alias mới.

Biện pháp: **so toàn schema response** hoặc dùng một bộ từ khóa/alias theo convention thực. Với response DTO allowlist, thay đổi naming strategy có thể khiến expected tree khác và test báo lỗi, giúp phát hiện regression.

### 14.2. Null, empty list và @JsonInclude

Một property có giá trị null vẫn là một property nếu JSON có key đó. `@JsonInclude(Include.NON_NULL)` có thể bỏ null, còn `NON_EMPTY` có thể bỏ empty values tùy cấu hình; **không dùng các filter này làm biện pháp giấu secret**.

Nếu hợp đồng cho phép `"integrations":[]` nhưng không cho phép property bị thiếu, test positive phải xác minh mảng rỗng tồn tại. Ngược lại, nếu một optional field phải vắng mặt chứ không phải null, dùng `doesNotHaveJsonPath()`/`JsonNode.has(...) == false`.

### 14.3. @JsonView và role-specific serialization

`@JsonView` có thể chọn tập property theo view tại thời điểm serialize. Nó hữu ích khi application đã có policy view rõ ràng, nhưng dễ sai khi controller quên chỉ định view, view kế thừa field ngoài ý muốn hoặc cấu hình default-view inclusion thay đổi.

Với security-critical response, **DTO theo use case** thường dễ kiểm tra hơn so với một domain model mang nhiều annotation/view. Nếu vẫn dùng `@JsonView`, test cả từng view và response HTTP thực để khẳng định trường cấm không rò.

### 14.4. ObjectMapper tùy chỉnh, mixin và Jackson modules

Một module, custom serializer hoặc mixin có thể thay đổi property discovery. Unit test tạo `new ObjectMapper()` không bảo đảm giống mapper được Spring Boot cấu hình. `@JsonTest` có thể nạp JSON configuration phù hợp trong slice; `@WebMvcTest` kiểm tra MVC serialization. Khi lỗi phát sinh do production-only config, thêm full-context test dùng đúng mapper của ứng dụng.

Không tự cấu hình ObjectMapper khác trong test chỉ để assertion pass rồi tuyên bố contract production đã được bảo vệ.

### 14.5. Polymorphism và nested object tùy biến

Khi response chứa `Object`, `Map<String,Object>`, sealed hierarchies, Jackson polymorphic type info hoặc generic wrappers, một nested payload có thể expose field khác ngoài dự kiến. Recursion theo JSON tree và schema allowlist có giá trị hơn việc assert một path top-level.

Với response dạng pagination:

```json
{
  "items": [
    {"id":42,"displayName":"Linh"},
    {"id":43,"displayName":"Mai"}
  ],
  "total":2
}
```

Đừng chỉ kiểm tra `$.items[0].passwordHash`. Hãy kiểm tra **mọi item** và mọi nested field. Nếu API trả rất nhiều phần tử, không cần snapshot mọi giá trị, nhưng vẫn phải duyệt toàn bộ payload thực trong test fixture và kiểm soát list size.

### 14.6. Request và response có lifecycle khác nhau

Một field như password có thể cần deserialize từ request, nhưng **không được trả trong response**. `@JsonProperty(access=WRITE_ONLY)` là một lớp bảo vệ cho điều đó. Tuy nhiên, với endpoint thực tế, hãy tách `LoginRequest` khỏi `LoginResponse`; không reuse input DTO với secret như output DTO chỉ vì annotation hiện tại đang giấu được.

Đừng quên lỗi validation: nếu error response echo raw request body hoặc rejected value, secret đầu vào có thể bị lộ dù response DTO happy path không chứa password.

## 15. Những lỗi phổ biến

**1. Chỉ assert HTTP 200 và một field hợp lệ.** Test vẫn xanh khi serializer trả thêm password hash/token. Phải có negative assertions và schema allowlist.

**2. Dùng `doesNotExist()` khi mục tiêu là key vắng mặt tuyệt đối.** Một `{"passwordHash":null}` có thể được chấp nhận. Dùng `doesNotHaveJsonPath()`.

**3. Dùng `hasNonNull("secret") == false` làm bằng chứng không có property.** Nó cũng đúng với key hiện diện có `null`. Dùng `has("secret") == false`.

**4. Kiểm tra một phần tử đầu tiên rồi kết luận cả array sạch.** Duyệt tất cả phần tử hoặc so toàn JSON expected.

**5. Chỉ cấm một vài key mà bỏ qua các tên alias.** So toàn DTO schema hoặc duyệt key + sentinel values; xem naming strategy.

**6. Chỉ kiểm tra key mà bỏ qua secret xuất dưới tên khác.** Dùng dữ liệu sentinel không null và kiểm tra response values/schema.

**7. Chỉ kiểm tra secret có giá trị null trong fixture.** `NON_NULL` có thể làm test xanh giả; dùng test secret **khác null**.

**8. Trả trực tiếp JPA entity/domain model có credentials.** Thêm một field mới có thể tự động nới JSON contract. Dùng DTO allowlist.

**9. Dùng `@JsonIgnore` nhưng không test ObjectMapper thực tế.** Annotation/config/module có thể thay đổi theo refactor; test serialized JSON.

**10. Hiểu `WRITE_ONLY` là “client chỉ được đọc”.** Jackson WRITE_ONLY là nhận input khi deserialize, **không serialize output**.

**11. Dùng `@JsonInclude(NON_NULL)` làm biện pháp security.** Giá trị khác null vẫn rò.

**12. Dùng `@Schema(hidden = true)` hoặc giấu field ở frontend.** OpenAPI/UI không điều khiển runtime response serialization.

**13. Mock controller hoặc serializer trong HTTP test.** Test không còn đi qua đường MVC/Jackson muốn bảo vệ. Chỉ mock collaborator ngoài phạm vi cần chứng minh.

**14. Test @JsonTest xanh rồi suy ra endpoint trả DTO đúng.** Controller có thể trả một object khác; cần MockMvc/WebTestClient test.

**15. Quên error responses và framework errors.** Exception message/validation details có thể echo secret; kiểm tra những nhánh có nguy cơ.

**16. Bỏ qua authorization.** Không có credential leak không đồng nghĩa người dùng có quyền đọc resource ID bất kỳ.

**17. Đưa secret fixture thật vào test.** Dùng sentinel giả lập, không dùng mật khẩu/token production; test logs và CI artifacts cũng là nơi cần bảo vệ.

**18. Đặt @SpringBootTest cho tất cả JSON assertions.** Bắt đầu bằng JSON slice/web slice khi đủ, bổ sung full context chỉ cho rủi ro config/wiring thật.

## 16. Checklist kiểm tra response không lộ dữ liệu nhạy cảm

**Trước khi viết test:**

- Đã liệt kê các field bị cấm theo endpoint/role chưa (password, token, apiKey, reset data, internal notes, PII…)?
- Đã xác định **field nào được phép trả** bằng response schema/DTO rõ ràng chưa?
- Domain object có nested collections, Map, polymorphic types hoặc field alias không?
- Test fixture có **giá trị secret khác null** để bắt lỗi `NON_NULL`/mapping không?
- Error handler có thể echo exception/rejected values không?

**Khi viết test:**

- Có assert status, media type và các field được phép để tránh negative test xanh giả không?
- Có dùng `doesNotHaveJsonPath()` hoặc `JsonNode.has(...) == false` thay vì chỉ `doesNotExist()`/`hasNonNull` không?
- Có so **toàn schema allowlist** ở response đơn giản và kiểm tra nested arrays toàn bộ không?
- Có dùng sentinel để phát hiện secret bị rò qua một tên field khác không?
- Có test một account, danh sách nhiều account và ít nhất một error response có dữ liệu nguy cơ không?
- Test có đi qua Jackson/MVC thật tại boundary cần chứng minh không?

**Sau khi test xanh:**

- Có chắc controller không trả entity/domain object ngoài ý muốn không?
- Một field nhạy cảm mới được thêm vào domain có thể tự động vào response không?
- Có test riêng cho permission/owner check ngoài kiểm thử serialization không?
- Với custom ObjectMapper modules/views, context test có đúng config cần bảo vệ không?
- Những endpoint khác (create/update/export/admin/error) có cùng nguy cơ đã được bao phủ chưa?
- CI logs, traces, headers, cookies và debug payloads có chính sách riêng để tránh leak không?

**Kết luận:** đối với dữ liệu nhạy cảm, “không có giá trị” và “không có trường” là hai hợp đồng khác nhau. Cách bảo vệ thực tế là **response DTO với allowlist rõ ràng**, dữ liệu thử nghiệm có secret khác null, rồi kiểm chứng **JSON thực sau serialization** bằng `@JsonTest` và **HTTP response** bằng `MockMvc`/`WebTestClient`. Sử dụng `doesNotHaveJsonPath()` khi trường phải **vắng mặt cả khi null**, đồng thời kiểm tra đầy đủ schema và các nested arrays/error paths; không coi ẩn field là thay thế cho authorization.

## 17. Tài liệu tham khảo

- [Spring Framework — JsonPathResultMatchers API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/JsonPathResultMatchers.html): `doesNotHaveJsonPath()`, `doesNotExist()`, `hasJsonPath()`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@JsonTest`, `@WebMvcTest` và `@SpringBootTest`.
- [Jackson 2 — JsonProperty.Access](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-annotations/2.18.3/com/fasterxml/jackson/annotation/JsonProperty.Access.html): `WRITE_ONLY`, `READ_ONLY` và ý nghĩa serialization/deserialization.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử Spring MVC bằng mock HTTP request/response.
