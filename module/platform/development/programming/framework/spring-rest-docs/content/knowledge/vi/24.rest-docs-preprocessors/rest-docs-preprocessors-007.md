# Modifying headers và che dữ liệu nhạy cảm

## 1. Vì sao cần xử lý header và dữ liệu nhạy cảm?

Trong module **SPRING_REST_DOCS**, các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured tạo generated snippets từ request/response. Snippet thường có request line, headers và body. Những nội dung này đôi khi chứa metadata chỉ dành cho vận hành hoặc giá trị không được phép xuất bản:

- Header nội bộ như X-Internal-Node, X-Debug-Trace.
- Header biến đổi theo môi trường như Date hoặc Server.
- Thông tin xác thực trong Authorization, Cookie hoặc session header.
- API key, access token, refresh token hoặc chữ ký.
- Dữ liệu cá nhân hay thông tin không cần thiết trong JSON body.

Spring REST Docs có operation preprocessors để chỉnh bản ghi request/response trước khi ghi snippet. Hai nhóm thao tác thường gặp là **chỉnh header** và **che giá trị trong body**.

Cần hiểu ranh giới: operation preprocessor tác động lên bản ghi REST Docs dùng để tạo tài liệu. Nó không tự xóa header khỏi HTTP request đã gửi, không thay đổi response mà client nhận và không phải biện pháp bảo mật runtime. Nếu API thật đang gửi secret trái với contract, cần sửa API hoặc cấu hình bảo mật.

## 2. Operation preprocessors và vị trí áp dụng

Preprocessor nhận operation request/response đã capture, chỉnh bản ghi rồi trả kết quả cho bước tạo snippet.

| API | Vai trò |
| --- | --- |
| `OperationPreprocessor` | Hợp đồng xử lý operation request hoặc response |
| `preprocessRequest(...)` | Gắn preprocessor vào request của operation |
| `preprocessResponse(...)` | Gắn preprocessor vào response của operation |
| `modifyHeaders()` | Tạo processor chỉnh header collection |
| `replacePattern(...)` | Thay đoạn text khớp regular expression |
| Custom preprocessor | Thực hiện quy tắc masking theo cấu trúc hoặc domain |

Import các helper:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessRequest;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
```

Các helper request/response trong ví dụ thuộc integration MockMvc. Với WebTestClient và REST Assured, vị trí gắn preprocessor theo API integration tương ứng, nhưng nguyên tắc xử lý operation vẫn giống nhau.

Một operation có thể chỉ xử lý request, chỉ xử lý response hoặc xử lý cả hai. Chỉ áp dụng processor ở phía có dữ liệu cần điều chỉnh.

## 3. Thêm, thay và xóa header bằng modifyHeaders()

`modifyHeaders()` tạo processor để thay đổi header collection của request/response được ghi lại. Có thể thêm header, đặt giá trị hoặc xóa header.

### 3.1. Thay giá trị header

Khi muốn giữ tên header trong tài liệu nhưng không công bố giá trị thật, dùng placeholder:

```java
.andDo(document("accounts-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer [REDACTED]")
    )
))
```

Snippet vẫn thể hiện request có Authorization, nhưng bearer token thực tế không xuất hiện. Cách này phù hợp khi tài liệu cần giải thích client phải gửi thông tin xác thực.

### 3.2. Xóa header không cần công bố

Một số header chỉ phục vụ hạ tầng nội bộ:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .remove("Date")
            .remove("X-Internal-Node")
            .remove("X-Debug-Trace")
    )
))
```

Các header đó không còn xuất hiện trong snippet response. Chỉ xóa header không thuộc contract hoặc không có ích cho người đọc. Không xóa Content-Type, Location, ETag hoặc Cache-Control nếu client cần hiểu hành vi API.

### 3.3. Thêm header đại diện

Có thể chuẩn hóa một header trong bản ghi tài liệu:

```java
.andDo(document("orders-get",
    preprocessResponse(
        modifyHeaders()
            .set("X-API-Version", "v1")
            .remove("X-Internal-Node")
    )
))
```

Chỉ thêm giá trị đại diện nếu nó phản ánh contract. Không tạo header giả mà client không cần gửi hoặc nhận trong API thực.

## 4. Chọn remove hay set khi xử lý header nhạy cảm

Giả sử request capture có:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.signature
X-Request-Id: 1b2c3d4e-5f6a-7b8c
Content-Type: application/json
```

Có hai lựa chọn:

**Xóa header:**

```java
preprocessRequest(
    modifyHeaders().remove("Authorization")
)
```

Dùng khi không muốn header xuất hiện trong tài liệu, hoặc header chỉ phục vụ hạ tầng nội bộ. Tuy nhiên client đọc tài liệu có thể không biết operation yêu cầu xác thực.

**Thay giá trị:**

```java
preprocessRequest(
    modifyHeaders()
        .set("Authorization", "Bearer <access-token>")
        .set("X-Request-Id", "<request-id>")
)
```

Cách này giữ cấu trúc header để mô tả contract. Với API public, thường nên che giá trị nhưng giữ tên header nếu nó có ý nghĩa với client.

Nếu `requestHeaders(...)` mô tả một header, xóa header đó trong preprocessor có thể làm snippet không còn phản ánh thông tin cần tài liệu hóa. Khi muốn mô tả sự hiện diện của header, hãy giữ tên và thay giá trị.

## 5. Che giá trị trong body bằng replacePattern()

Body cũng có thể chứa token hoặc dữ liệu không nên xuất bản:

```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiJ9.real-secret",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "profile": {
    "email": "lan@example.test"
  }
}
```

`replacePattern(Pattern, String)` thay đoạn text khớp regex trong operation content:

```java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.andDo(document("auth-token-create",
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\"")
    )
))
```

Snippet response sau khi xử lý:

```json
{
  "accessToken": "[REDACTED]",
  "tokenType": "Bearer",
  "expiresIn": 3600,
  "profile": {
    "email": "lan@example.test"
  }
}
```

Regex chỉ nhắm vào property accessToken có giá trị JSON string. Vì đây là thay thế trên text, pattern phải phù hợp whitespace, escaping và serialization thực tế. Tránh regex quá rộng có thể phá dữ liệu không nhạy cảm hoặc cấu trúc JSON.

`replacePattern` chỉ che bản ghi tài liệu. Nếu API thật trả token, client vẫn nhận token đó qua HTTP. Hãy dùng fixture giả; tuyệt đối không lấy token production để làm dữ liệu test với kỳ vọng preprocessor luôn che đúng.

## 6. Che nhiều field và giữ nguyên JSON shape

Có thể kết hợp nhiều pattern:

```java
.andDo(document("auth-token-create",
    preprocessResponse(
        replacePattern(
            Pattern.compile(
                "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
            "\"accessToken\":\"[REDACTED]\""),
        replacePattern(
            Pattern.compile(
                "\"refreshToken\"\\s*:\\s*\"[^\"]+\""),
            "\"refreshToken\":\"[REDACTED]\""),
        replacePattern(
            Pattern.compile(
                "\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\"")
    )
))
```

Giới hạn từng pattern theo tên field và giá trị cần thay. Không thay mọi email nếu email là dữ liệu ví dụ mà contract muốn giữ; một fixture giả ổn định có thể rõ ràng hơn masking.

Giữ key với placeholder thường giúp snippet vẫn thể hiện response shape:

```json
{
  "accessToken": "[REDACTED]",
  "refreshToken": "[REDACTED]",
  "expiresIn": 3600
}
```

Nếu field nhạy cảm không thuộc contract public, quyết định có nên bỏ nó khỏi tài liệu hay không. Masking chỉ thay giá trị trong snippet; nó không làm field biến mất khỏi response thật.

## 7. Khi regex chưa đủ: custom preprocessor hiểu JSON

Regex phù hợp với field đơn giản, tên ổn định và JSON serialization nhất quán. Với object lồng, array hoặc nhiều kiểu dữ liệu, cân nhắc custom `OperationResponsePreprocessor`:

1. Đọc operation body và Content-Type.
2. Chỉ parse khi media type là JSON phù hợp.
3. Parse body thành JSON tree.
4. Thay giá trị tại path nhạy cảm bằng placeholder.
5. Serialize JSON lại.
6. Trả operation đã chỉnh cho REST Docs.

Cách này ít phụ thuộc whitespace và escaping hơn regex. Tuy nhiên custom processor phải xử lý charset, body rỗng, content type không phải JSON, parse failure và serialization options. Không parse mọi body như JSON.

Pseudo-code minh họa ý tưởng:

```java
OperationResponsePreprocessor maskSensitiveJsonFields =
        operation -> {
            // Kiểm tra Content-Type là application/json.
            // Parse operation.getContent() thành JsonNode.
            // Thay accessToken/refreshToken bằng "[REDACTED]".
            // Serialize lại và trả operation có content đã thay.
            return operation;
        };
```

Đây không phải implementation có thể compile trực tiếp. Implementation thật cần dùng builder/API operation của phiên bản Spring REST Docs đang dùng và có unit test cho JSON nested, array, null, body rỗng và malformed JSON.

## 8. Kết hợp header modification và body masking

Một operation có thể cần xử lý cả request và response:

```java
.andDo(document("accounts-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer [REDACTED]")
            .set("X-Request-Id", "<request-id>")
    ),
    preprocessResponse(
        modifyHeaders()
            .remove("X-Internal-Node")
            .remove("X-Debug-Trace"),
        replacePattern(
            Pattern.compile(
                "\"email\"\\s*:\\s*\"[^\"]+\""),
            "\"email\":\"user@example.test\"")
    )
))
```

Trong ví dụ:

- Request snippet giữ Authorization nhưng thay token bằng placeholder.
- Request ID được chuẩn hóa để generated diff ổn định.
- Response snippet bỏ header nội bộ.
- Email trong response được thay bằng địa chỉ ví dụ.

Nếu response body phản chiếu Authorization header, cần áp dụng response preprocessor tương ứng. Xử lý request không tự động che cùng giá trị trong response.

## 9. Thứ tự preprocessor và các snippet liên quan

Thứ tự processor có ý nghĩa nếu processor sau đọc nội dung đã thay đổi bởi processor trước. Ví dụ, nếu một bước thay Content-Type, formatter hoặc parser phía sau có thể nhận diện body khác. Nếu regex chạy trước formatter, pattern phải khớp body ban đầu; nếu formatter chạy trước, pattern phải khớp representation sau định dạng.

Nguyên tắc thực hành:

- Chuẩn hóa dữ liệu không ổn định trước khi sinh snippet.
- Che secret trước khi ghi snippet chứa body/header đó.
- Giữ header contract cần mô tả; chỉ xóa metadata không cần công bố.
- Kiểm tra tất cả snippet của operation, không chỉ http-response.
- Xem xét request/response fields, curl request và custom snippets có lấy dữ liệu từ cùng operation không.

Preprocessor thường làm thay đổi bản ghi operation chung mà các snippet sử dụng. Đừng giả định một processor chỉ ảnh hưởng đúng một file snippet.

## 10. Ví dụ MockMvc: che Authorization và token response

Ví dụ dùng JUnit Jupiter, MockMvc và Spring REST Docs. Controller trả token giả lập; test tạo snippet có placeholder.

```java
import java.util.Map;
import java.util.regex.Pattern;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessRequest;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class SensitiveDataDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TokenController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentTokenResponseWithoutRealSecret() throws Exception {
        mockMvc.perform(get("/api/token")
                        .header("Authorization", "Bearer test-secret-value")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(document("token-get",
                        preprocessRequest(
                                modifyHeaders()
                                        .set("Authorization", "Bearer [REDACTED]")
                        ),
                        preprocessResponse(
                                replacePattern(
                                        Pattern.compile(
                                            "\"accessToken\"\\s*:\\s*\"[^\"]+\""),
                                        "\"accessToken\":\"[REDACTED]\"")
                        )
                ));
    }

    @RestController
    static class TokenController {
        @GetMapping(value = "/api/token",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        Map<String, Object> token() {
            return Map.of(
                    "accessToken", "server-generated-test-secret",
                    "tokenType", "Bearer",
                    "expiresIn", 3600
            );
        }
    }
}
```

Trong dự án thật:

- Không lấy token production từ environment để đưa vào test.
- Không log body/header chưa che trong assertion failure hoặc custom reporter.
- Kiểm tra snippet sau khi chạy và xác nhận không có giá trị gốc.
- Nếu dùng requestHeaders để mô tả Authorization, dùng mô tả tổng quát như “Bearer access token”.
- Thêm test cho regex với whitespace và escaping khác nhau.

## 11. Masking trong tài liệu không thay thế bảo mật API

Phân biệt các trường hợp:

| Tình huống | Xử lý trong REST Docs | Xử lý ở API/runtime |
| --- | --- | --- |
| Token client cần gửi | Thay giá trị trong snippet, giữ header và mô tả format | Xác thực token thật theo contract |
| Email/điện thoại demo | Dùng fixture giả hoặc mask trong snippet | Áp dụng quyền truy cập và data policy |
| Password hash/secret nội bộ không được trả | Không đưa giá trị vào snippet | Loại khỏi DTO/serializer và test không rò rỉ |
| Trace ID nội bộ | Xóa header hoặc thay giá trị trong snippet | Xem xét có nên gửi header ra ngoài |
| Cookie/session thật | Thay hoặc loại khỏi recorded request | Quản lý cookie/session an toàn |

Nếu secret không được phép xuất hiện trong HTTP response, test phải xác nhận nó không có trong response thật:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.accessToken").doesNotExist());
```

Nếu yêu cầu key hoàn toàn vắng mặt, phân biệt với key có giá trị null. Có thể parse response thành JSON tree và kiểm tra `has(...)`.

Secret cũng có thể lộ trong fixture, test report, failure log, HTTP client logging hoặc CI artifact khác. Hãy dùng dữ liệu giả và kiểm soát logging từ đầu.

## 12. Kiểm thử việc che dữ liệu

Nên xác minh masking như một phần của test suite tài liệu:

- Kiểm tra snippet không chứa secret marker của fixture.
- Kiểm tra placeholder vẫn giữ key cần tài liệu hóa.
- Kiểm tra header contract vẫn xuất hiện nếu descriptor yêu cầu.
- Kiểm tra header nội bộ đã bị remove theo policy.
- Kiểm tra regex không thay nhầm field không nhạy cảm.
- Kiểm tra JSON có whitespace, escaped quote, nested object và array.
- Kiểm tra body không phải JSON không bị custom JSON masker parse sai.
- Kiểm tra Asciidoctor include đúng snippet vừa sinh.

Đặt marker giả dễ nhận biết trong fixture để tìm trong output. Không dùng secret thật kể cả khi đã cấu hình preprocessor; một lỗi cấu hình không được phép ghi credential thật vào artifact.

## 13. Tích hợp Asciidoctor và CI

Asciidoctor include snippet theo identifier:

```adoc
= Token API
:snippets: build/generated-snippets

== Lấy token

=== HTTP request
include::{snippets}/token-get/http-request.adoc[]

=== HTTP response
include::{snippets}/token-get/http-response.adoc[]
```

Build nên chạy documentation tests trước Asciidoctor để snippet được sinh từ test hiện tại. Có thể thêm bước kiểm tra artifact để tìm secret marker gốc. Bước này nên kiểm tra generated snippets và tài liệu render, vì custom template có thể tạo output khác snippet mặc định.

CI cần fail nếu secret marker còn xuất hiện, header contract bị xóa ngoài ý muốn, snippet stale, regex thay nhầm field hoặc test API không rò rỉ field nhạy cảm thất bại.

Không dùng script che secret sau khi publish làm giải pháp chính. Che ngay trong operation preprocessing trước khi ghi snippet và giữ test kiểm chứng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Authorization biến mất khỏi snippet | Dùng remove trong khi cần mô tả header | Dùng set với placeholder |
| Token vẫn còn trong response snippet | Chỉ che request hoặc regex sai | Áp dụng response preprocessor và test output |
| JSON body bị hỏng | Regex quá rộng hoặc replacement không hợp lệ | Giới hạn pattern; cân nhắc JSON-aware processor |
| Email hợp lệ bị thay nhầm | Pattern quá rộng | Dùng fixture giả hoặc pattern/path cụ thể |
| Header contract không xuất hiện | Xóa header descriptor cần | Thay giá trị thay vì remove |
| Header nội bộ vẫn xuất hiện | Xử lý sai phía request/response | Chọn đúng operation preprocessor |
| API vẫn trả password hash | Nhầm masking snippet với bảo mật | Sửa DTO/serialization và test response thật |
| Snippet diff không ổn định | Request ID, Date hoặc token đổi mỗi lần | Chuẩn hóa giá trị trong recorded operation |
| Secret xuất hiện trong test report | Failure/logger ghi raw exchange | Dùng fixture giả và hạn chế HTTP logging |
| Preprocessor sau không khớp | Thứ tự làm đổi representation | Kiểm tra dữ liệu sau từng bước |

## 15. Bài thực hành

Dùng endpoint lấy token và endpoint xem profile:

1. Tạo request với Authorization giả lập. Dùng `modifyHeaders().set(...)` để thay giá trị trong snippet nhưng giữ header.
2. Thêm X-Internal-Node vào response. Dùng `remove(...)` nếu header không thuộc contract cần công bố.
3. Thử `set(...)` với placeholder và so sánh khi tài liệu cần thể hiện header tồn tại.
4. Trả JSON có accessToken và refreshToken; dùng `replacePattern(...)` để thay bằng [REDACTED].
5. Tạo fixture có whitespace/escaping khác nhau; kiểm tra regex che đúng mà không phá JSON.
6. Thêm email; quyết định dùng dữ liệu giả hay mask trong snippet.
7. Tạo response có passwordHash. Viết assertion xác nhận API không gửi field đó.
8. Kết hợp header modification và body masking trong cùng operation; kiểm tra cả request lẫn response.
9. Sinh snippets và tìm secret marker trong toàn bộ generated-snippets; build phải fail nếu marker còn.
10. Include snippets đã che vào Asciidoctor và review artifact cuối.

**Tiêu chí hoàn thành:** bạn biết dùng `modifyHeaders()` để add/set/remove header của bản ghi REST Docs; che body bằng `replacePattern(...)` hoặc custom operation preprocessor; phân biệt remove với placeholder; hiểu preprocessor không bảo vệ HTTP runtime; và kiểm thử để không có secret thật lọt vào generated snippets/CI artifacts.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessing.html): operation preprocessors, chỉnh request/response trước khi tạo snippet.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `modifyHeaders`, `replacePattern` và helper preprocessing.
- [Spring REST Docs — OperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/OperationPreprocessor.html): hợp đồng xử lý operation trước khi sinh tài liệu.
