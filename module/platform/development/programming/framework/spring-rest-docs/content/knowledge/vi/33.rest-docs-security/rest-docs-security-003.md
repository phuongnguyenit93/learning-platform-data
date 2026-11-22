# Replacing patterns trong body hoặc header

## 1. Mục tiêu

HTTP request/response có thể chứa access token, session ID, API key, password, email hoặc dữ liệu nội bộ. Spring REST Docs ghi lại operation và sinh snippets từ dữ liệu đó. Trước khi tạo tài liệu, cần thay giá trị nhạy cảm bằng placeholder hoặc loại bỏ chúng.

Cần phân biệt hai vùng dữ liệu:

- **Headers:** tập hợp tên và giá trị như Authorization, Cookie, Set-Cookie, X-Api-Key.
- **Content/body:** nội dung request/response, thường là JSON, XML hoặc text.

Spring REST Docs cung cấp hai nhóm API khác nhau. **modifyHeaders()** thêm, set hoặc remove header. **replacePattern(Pattern, String)** thay các đoạn khớp regex trong content của request/response. replacePattern không thao tác trực tiếp trên header collection.

Bài học thuộc chương **Bảo mật** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể phân biệt xử lý header/body, thay header value bằng placeholder, che field trong body, kết hợp request/response preprocessors, viết custom preprocessor khi cần regex trên header và kiểm tra secret leak trong CI.

## 2. Nhận diện vùng cần thay thế

~~~http
POST /api/profile HTTP/1.1
Authorization: Bearer real-access-token
X-Api-Key: real-api-key
Content-Type: application/json

{
  "email": "person@example.test",
  "password": "plain-or-test-secret",
  "displayName": "An"
}
~~~

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=real-session-id; Path=/; HttpOnly; Secure
Content-Type: application/json

{
  "id": 42,
  "email": "person@example.test",
  "accessToken": "new-access-token",
  "displayName": "An"
}
~~~

| Vùng | Ví dụ | Cơ chế |
| --- | --- | --- |
| Request header | Authorization | modifyHeaders set/remove. |
| Request header | X-Api-Key | modifyHeaders set/remove. |
| Response header | Set-Cookie | modifyHeaders set/remove. |
| Request body | password, email | replacePattern hoặc content-aware modifier. |
| Response body | accessToken, PII | replacePattern hoặc content-aware modifier. |
| URL/query | token trong request line | Synthetic value hoặc xử lý URI riêng. |

Xác định thông tin cần giữ để giải thích contract. Có thể giữ tên header Authorization và scheme Bearer nhưng thay credential. Email dùng địa chỉ tổng hợp.

## 3. Thay header value bằng modifyHeaders()

Spring REST Docs 3.x/4.x cung cấp modifyHeaders() để thêm, set và remove request/response headers.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

.andDo(document("profile-update",
    preprocessRequest(
        modifyHeaders().set("Authorization", "Bearer <access-token>")
    )
));
~~~

Header vẫn xuất hiện trong snippet nhưng value đã được thay bằng placeholder không có hiệu lực. Cách này hữu ích khi muốn tài liệu thể hiện authentication scheme mà không công bố credential.

Thay API key:

~~~java
preprocessRequest(
    modifyHeaders().set("X-Api-Key", "<api-key>")
);
~~~

Hoặc loại header:

~~~java
preprocessRequest(
    modifyHeaders()
        .remove("Cookie")
        .remove("X-Internal-Auth")
);
~~~

### 3.1. Thay header response

Dùng cùng preprocessor cho response:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("login",
    preprocessResponse(
        modifyHeaders()
            .set("Set-Cookie", "SESSION=<session-id>; HttpOnly; Secure")
            .set("X-Request-Id", "<request-id>")
    )
));
~~~

Nếu không cần mô tả cookie, remove Set-Cookie. Nếu cần mô tả Path, HttpOnly, Secure hoặc SameSite, giữ attributes nhưng thay session value.

### 3.2. Set hay remove?

| Cách làm | Kết quả | Khi phù hợp |
| --- | --- | --- |
| set(name, placeholder) | Header còn tên và value giả | Muốn mô tả header contract. |
| remove(name) | Header không xuất hiện | Header không cần thiết cho ví dụ. |
| Không preprocess | Giá trị gốc được ghi | Chỉ khi value chắc chắn công khai. |

Không xóa Content-Type, Accept, Location hoặc Cache-Control nếu chúng là một phần hợp đồng API.

## 4. replacePattern() cho body

replacePattern() nhận Java Pattern và replacement string. Nó tìm đoạn khớp trong content request/response rồi thay bằng giá trị mới.

~~~json
{
  "email": "person@example.test",
  "password": "my-secret-password",
  "displayName": "An"
}
~~~

Pattern che password:

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

private static final Pattern PASSWORD_FIELD =
    Pattern.compile("(\"password\"\\s*:\\s*\")[^\"]*(\")");

.andDo(document("profile-update",
    preprocessRequest(
        replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
    )
));
~~~

Kết quả mong muốn:

~~~json
{
  "email": "person@example.test",
  "password": "[REDACTED]",
  "displayName": "An"
}
~~~

Group 1 giữ tên field và dấu quote mở; group 2 giữ quote đóng. Replacement giữ cấu trúc JSON và chỉ thay value. Pattern này dành cho JSON string đơn giản; phải kiểm tra escaping, multiline và serialization thực tế.

## 5. Che nhiều field

Có thể dùng một pattern với danh sách field nhạy cảm:

~~~java
private static final Pattern SECRET_FIELDS = Pattern.compile(
    "(\"(password|clientSecret|accessToken|refreshToken)\"\\s*:\\s*\")[^\"]*(\")"
);
~~~

Áp dụng cho response:

~~~java
.andDo(document("login",
    preprocessResponse(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

Tên field phải khớp payload thực tế. Không dùng pattern quá rộng như token nếu API có field nghiệp vụ cùng tên nhưng không phải secret.

Cần che cả hai chiều thì cấu hình riêng:

~~~java
.andDo(document("credential-exchange",
    preprocessRequest(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    ),
    preprocessResponse(
        replacePattern(SECRET_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

Request preprocessor không tự áp dụng cho response và ngược lại.

## 6. Kết hợp header và body replacement

~~~java
.andDo(document("login",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .remove("Cookie"),
        replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
    ),
    preprocessResponse(
        modifyHeaders()
            .set("Set-Cookie", "SESSION=<session-id>; HttpOnly; Secure"),
        replacePattern(TOKEN_FIELDS, "$1[REDACTED]$3")
    )
));
~~~

Header transformation và content transformation cùng được áp dụng lên request/response tương ứng. Pattern phải khớp schema thực tế và cần xác minh generated output.

Giữ snippet có ích: Content-Type, Accept, field names, status code và response shape; thay credential bằng placeholder; dùng dữ liệu tổng hợp cho email, phone và customer ID.

## 7. Regex trên header values: giới hạn và cách mở rộng

replacePattern() xử lý content body; nó không quét header collection. Nếu biết tên header và muốn thay toàn bộ value, dùng modifyHeaders().set():

~~~java
preprocessRequest(
    modifyHeaders().set("Authorization", "Bearer <access-token>")
);
~~~

Nếu cần thay một phần value theo regex, có thể viết custom OperationPreprocessor:

~~~java
OperationPreprocessor maskAuthorizationValue = operation -> {
    // Đọc headers của operation.
    // Thay credential trong Authorization bằng placeholder.
    // Tạo operation mới, giữ method, URI, body và metadata còn lại.
    return operationWithSanitizedHeaders;
};
~~~

Đây là pseudo-code, không phải implementation copy/paste. Cần dùng OperationRequest/OperationResponse API và factory/constructor đúng version REST Docs. Nếu chỉ cần thay toàn bộ value, modifyHeaders().set() đơn giản hơn.

### 7.1. Không dựa vào HTTP snippet text dump

REST Docs giữ headers và content ở các cấu trúc riêng. replacePattern() được thiết kế cho content. Không suy luận rằng nó sẽ thay header chỉ vì file HTTP snippet cuối cùng hiển thị header và body trong cùng một văn bản.

## 8. Tránh regex làm hỏng JSON

Regex đơn giản có thể không đủ nếu value chứa escaped quotes, backslashes, newline hoặc JSON lồng nhau.

~~~json
{
  "credentials": {
    "password": "secret",
    "metadata": {
      "note": "text with an escaped quote: \"hello\""
    }
  }
}
~~~

Với JSON phức tạp, cân nhắc ContentModifier:

1. Parse JSON thành tree bằng thư viện của dự án.
2. Duyệt đúng JSON paths cần che.
3. Thay value bằng placeholder.
4. Serialize lại JSON.
5. Kiểm tra Content-Type và charset.
6. Trả content mới cho operation preprocessor.

Spring REST Docs có ContentModifier và ContentModifyingOperationPreprocessor để thay request/response body. Cách này phù hợp khi cần hiểu cấu trúc JSON thay vì thay text bằng regex.

Không parse mọi body như JSON. XML, multipart và binary cần xử lý riêng.

## 9. Preprocessors mặc định cho nhiều tests

Nếu mọi operation đều cần cùng policy, cấu hình default request/response preprocessors trong RestDocumentationConfigurer.

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation)
        .operationPreprocessors()
        .withRequestDefaults(
            modifyHeaders().set("Authorization", "Bearer <access-token>")
        )
        .withResponseDefaults(
            modifyHeaders().set("Set-Cookie", "SESSION=<session-id>")
        ))
    .build();
~~~

Default preprocessors giúp tránh quên redaction. Tuy nhiên, nếu chỉ một số endpoint có Authorization hoặc Set-Cookie, policy chung có thể thêm placeholder không cần thiết. Có thể kết hợp defaults với preprocessors riêng cho operation.

WebTestClient và REST Assured cũng có documentation configurer để cấu hình default operation preprocessors. Kiểm tra đúng client instance và version.

## 10. Kiểm tra generated snippets

Dùng sentinel trong test fixture:

~~~java
private static final String DOCS_SECRET =
    "DOCS_ONLY_SECRET_92a1";
~~~

Sau khi test sinh snippets, đọc toàn bộ output và xác nhận:

~~~java
assertThat(allGeneratedSnippetText)
    .doesNotContain(DOCS_SECRET)
    .doesNotContain("my-secret-password");
~~~

Kiểm tra placeholder còn lại nếu đó là output mong muốn. Scan toàn bộ:

- http-request và http-response.
- curl-request và httpie-request.
- request-body và response-body.
- Request/response headers.
- Custom snippets và trang Markdown/Asciidoctor sau assemble.
- Rendered HTML nếu code examples được publish.

Không chỉ kiểm tra file request/response chính; cùng operation có thể sinh nhiều snippets.

## 11. Ví dụ với MockMvc, WebTestClient và REST Assured

### 11.1. MockMvc

~~~java
mockMvc.perform(post("/api/profile")
        .header("Authorization", "Bearer DOCS_ONLY_SECRET")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"email\":\"person@example.test\",\"password\":\"DOCS_ONLY_PASSWORD\"}"))
    .andExpect(status().isOk())
    .andDo(document("profile-update",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ));
~~~

Dùng synthetic credentials. Nếu controller cần authentication, cấu hình test security context bằng Spring Security test; không lấy token thật chỉ để vượt security filter.

### 11.2. WebTestClient

~~~java
webTestClient.post()
    .uri("/api/profile")
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(profileRequest)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("profile-update-webflux",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ));
~~~

Gắn preprocessors vào operation được ghi bởi WebTestClient REST Docs filter.

### 11.3. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .contentType("application/json")
    .body(profileRequest)
    .filter(document("profile-update-restassured",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer <access-token>"),
            replacePattern(PASSWORD_FIELD, "$1[REDACTED]$2")
        )
    ))
.when()
    .post("/api/profile")
.then()
    .statusCode(200);
~~~

REST Assured documentation filter phải dùng cùng REST Docs context. Kiểm tra output sau khi filter chạy.

## 12. CI: kiểm tra và chặn secret leak

~~~mermaid
flowchart TD
    A["HTTP tests with synthetic values"] --> B["Apply header preprocessors"]
    B --> C["Apply body pattern/content preprocessors"]
    C --> D["Generate all snippets"]
    D --> E["Assemble final docs"]
    E --> F["Scan sentinels and secret patterns"]
    F --> G{"Secret found?"}
    G -->|Yes| X["Fail CI"]
    G -->|No| H["Render and validate docs"]
    H --> I{"All checks pass?"}
    I -->|No| X
    I -->|Yes| J["Publish"]
~~~

CI nên:

1. Dùng synthetic credentials và sentinel riêng.
2. Chạy REST Docs tests.
3. Scan generated snippets trước assemble.
4. Assemble tài liệu cuối và scan lần nữa.
5. Kiểm tra rendered HTML/artifacts nếu có.
6. Fail build nếu sentinel hoặc secret pattern bị phát hiện.
7. Không in nguyên secret vào log.
8. Chỉ publish sau khi tests, scanning và rendering pass.

Scanner có thể false positive. Dùng allowlist hẹp cho placeholder fixture và review; không allowlist credential thật.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| replacePattern không đổi Authorization | Header không thuộc body content | Dùng modifyHeaders().set/remove(). |
| Header đã đổi nhưng password còn | Chỉ preprocess headers | Thêm replacePattern hoặc ContentModifier. |
| Chỉ request được mask | Quên preprocessResponse | Cấu hình cả request và response. |
| JSON bị hỏng sau regex | Pattern không xử lý escaping/nested values | Dùng JSON-aware ContentModifier. |
| Một số operation còn secret | Không dùng helper/default preprocessors | Kiểm tra operation và cấu hình defaults. |
| curl snippet còn credential | Chỉ kiểm tra http-request | Scan mọi snippets. |
| Header contract biến mất | Remove thay vì set placeholder | Dùng set khi cần giữ tên/header scheme. |
| Placeholder bị hiểu là token thật | Placeholder giống credential hợp lệ | Dùng chuỗi rõ như <access-token>. |
| CI phát hiện sau publish | Scan đặt sau publish | Đưa leak scan vào publish gate. |
| Regex thay nhầm field nghiệp vụ | Pattern quá rộng | Match đúng field/path và test fixture. |

## 14. Bài thực hành

Tạo endpoint login và endpoint cập nhật profile:

- POST /api/auth/login nhận username/password, trả accessToken.
- PATCH /api/profile nhận Authorization và JSON có email/password.
- Response có Set-Cookie và request ID.

Thực hiện:

1. Viết HTTP tests với synthetic credentials.
2. Dùng modifyHeaders().set() để thay Authorization bằng placeholder.
3. Dùng modifyHeaders().set() hoặc remove() để xử lý Set-Cookie và X-Api-Key.
4. Dùng replacePattern() để che password/accessToken trong body.
5. Với JSON nested/escaped phức tạp, thử ContentModifier.
6. Gắn preprocessors cho request và response đúng operation.
7. Sinh HTTP, curl, HTTPie, body và descriptor snippets.
8. Scan snippets và assembled docs bằng sentinel.
9. Cố ý bỏ một preprocessor để xác nhận CI phát hiện leak.
10. Ghi lại vì sao header replacement và body replacement dùng API khác nhau.

**Tiêu chí hoàn thành:** header values được set/remove đúng; body fields được thay theo pattern hoặc content-aware modifier; JSON còn hợp lệ; mọi snippets không còn sentinel; CI chặn publish nếu secret xuất hiện.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring REST Docs — ContentModifier API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/ContentModifier.html)
- [Spring REST Docs — HeadersModifyingOperationPreprocessor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/HeadersModifyingOperationPreprocessor.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
