# Che Authorization, cookie session và token

## 1. Mục tiêu và bối cảnh

HTTP request/response thường chứa dữ liệu xác thực hoặc định danh phiên: header Authorization, cookie JSESSIONID, access token, refresh token, session ID, CSRF token và API key. Spring REST Docs ghi nhận operation từ HTTP tests và sinh snippet cho request, response, headers, body, curl hoặc HTTPie. Nếu những giá trị này được ghi vào snippet rồi commit, đính kèm CI artifact hoặc publish, thông tin có thể bị lộ.

Bài học thuộc chương **Bảo mật** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể nhận diện dữ liệu xác thực; dùng operation preprocessors để loại bỏ hoặc thay thế dữ liệu nhạy cảm; che Authorization, Cookie, Set-Cookie, CSRF headers và token trong body; kiểm tra mọi loại snippet; tổ chức CI phát hiện secret bị lộ.

> Che dữ liệu trước khi ghi snippet. Không dựa vào việc xóa thủ công file sau build vì request/response có thể đã xuất hiện trong log, report hoặc artifact khác.

## 2. Những dữ liệu cần bảo vệ

| Vị trí | Tên thường gặp | Rủi ro |
| --- | --- | --- |
| Request header | Authorization | Bearer token, Basic credentials hoặc scheme riêng. |
| Request header | Cookie | Session identifier và cookie xác thực. |
| Response header | Set-Cookie | Session ID/token server phát hành. |
| Request/response header | X-CSRF-TOKEN, X-XSRF-TOKEN | Token chống CSRF. |
| JSON request body | password, clientSecret, refreshToken | Credential/token gửi lên. |
| JSON response body | access_token, refresh_token, id_token | Token server trả về. |
| URL query/path | code, ticket, signed value | Có thể xuất hiện trong request line và curl command. |
| Log/metadata | Fixture, exception text | Có thể vô tình chứa bí mật. |

Phân loại dữ liệu:
- **Secret cần loại bỏ/thay thế:** password, private key, client secret, access/refresh token, session ID, API key.
- **Identifier nên cân nhắc ẩn:** email, số điện thoại, user ID nội bộ, customer reference.
- **Thông tin có thể công khai:** tên field, scheme Bearer, tên cookie, placeholder và dữ liệu giả được tạo riêng cho test.

Dữ liệu test không tự động an toàn để công bố. Dùng synthetic data, không gắn với tài khoản/người thật.

## 3. Redaction bằng operation preprocessors

Spring REST Docs cho phép áp dụng operation preprocessors trước khi snippets được ghi. Hai thao tác thường dùng là `Preprocessors.removeHeaders(...)` để loại headers và `Preprocessors.replacePattern(...)` để thay nội dung theo pattern. Có thể áp dụng riêng cho request hoặc response bằng `preprocessRequest(...)` và `preprocessResponse(...)`.

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("sessions-create",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-CSRF-TOKEN")
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie", "Authorization")
    )
));
~~~

Đây là ví dụ minh họa cách gắn preprocessor vào operation; static imports phải khớp version Spring REST Docs của dự án. Headers bị loại sẽ không xuất hiện trong snippets được tạo từ operation đã preprocess.

### 3.1. Preprocess trước khi ghi snippet

Một operation có thể sinh nhiều snippets từ cùng request/response: HTTP request, HTTP response, curl, HTTPie, request body và response body. Preprocessor ở operation layer xử lý operation trước khi các snippets render.

Nếu chỉ xóa Authorization khỏi file http-request sau build, giá trị vẫn có thể còn trong curl-request, httpie-request hoặc log. Vì vậy cần redaction ở bước preprocess.

### 3.2. Chọn headers cần loại bỏ

| Header | Hướng xử lý |
| --- | --- |
| Authorization | Loại bỏ hoặc thay placeholder vô hiệu. |
| Cookie | Loại nếu chứa session/authentication cookies. |
| Set-Cookie | Loại vì có thể chứa session/token mới. |
| X-CSRF-TOKEN | Loại hoặc thay placeholder. |
| X-XSRF-TOKEN | Loại hoặc thay placeholder. |
| Proxy-Authorization | Loại credentials proxy. |
| X-Api-Key | Loại API key. |

Không xóa headers một cách máy móc. Content-Type, Accept, Location, Cache-Control hoặc request ID có thể là một phần hợp đồng API. Xác định danh sách secret headers của hệ thống và áp dụng nhất quán.

## 4. Che Authorization và cookie session

Request xác thực có thể chứa:

~~~http
GET /api/orders/101 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...secret...
Accept: application/json
Cookie: JSESSIONID=abc123secret
~~~

**Cách 1 — loại header khỏi snippet:**

~~~java
.andDo(document("orders-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie")
    )
));
~~~

HTTP request snippet vẫn thể hiện method, path và headers không nhạy cảm. Phần giải thích operation mô tả endpoint yêu cầu Bearer authentication.

**Cách 2 — test dùng giá trị giả:** request có thể gửi giá trị không có quyền truy cập thật, ví dụ `Bearer DOCS_ONLY_TOKEN`. Với tài liệu công khai, vẫn nên preprocess hoặc thay bằng placeholder để người đọc không nhầm đây là credential hợp lệ.

Không dùng token của developer, token CI có quyền thật hoặc cookie copy từ browser đang đăng nhập vào test fixture.

### 4.1. Cookie và Set-Cookie

Session cookie có thể được phát hành trong response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=server-session-secret; Path=/; HttpOnly; Secure
Content-Type: application/json
~~~

Loại Set-Cookie trong response preprocessor:

~~~java
.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie")
    )
));
~~~

Nếu tài liệu cần giải thích cookie attributes, hãy mô tả riêng hoặc kiểm thử attributes mà không ghi session identifier. Có thể trình bày Path, HttpOnly, Secure và SameSite mà không tiết lộ giá trị cookie.

### 4.2. CSRF và custom auth headers

Hệ thống có thể dùng headers riêng như X-CSRF-TOKEN, X-Api-Key hoặc Proxy-Authorization. Đưa tên header nhạy cảm vào danh sách loại bỏ. Nếu tên header là một phần contract, mô tả nó riêng và dùng placeholder không có hiệu lực cho giá trị sample.

## 5. Che token trong request/response body

Loại header chưa đủ nếu body chứa token. Ví dụ login response:

~~~json
{
  "token_type": "Bearer",
  "access_token": "actual-access-token",
  "refresh_token": "actual-refresh-token",
  "expires_in": 900
}
~~~

Có thể dùng `replacePattern(Pattern, String)` trên request/response preprocessor để thay giá trị trước khi snippet được ghi.

~~~java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

private static final Pattern ACCESS_TOKEN =
    Pattern.compile("(\"access_token\"\\s*:\\s*\")[^\"]*(\")");

private static final Pattern REFRESH_TOKEN =
    Pattern.compile("(\"refresh_token\"\\s*:\\s*\")[^\"]*(\")");

.andDo(document("login-success",
    preprocessResponse(
        replacePattern(ACCESS_TOKEN, "$1[REDACTED]$2"),
        replacePattern(REFRESH_TOKEN, "$1[REDACTED]$2")
    )
));
~~~

Ví dụ dùng regex cho JSON string field cụ thể. Phải kiểm tra output thực tế của version REST Docs đang dùng và bảo đảm pattern khớp serialization. Với escaping/nested structure phức tạp, regex đơn giản có thể không đủ.

Không thay mọi trường tên chung chung như token nếu ứng dụng còn field nghiệp vụ không phải secret.

### 5.1. Giữ schema dễ hiểu sau redaction

Snippet sau khi che có thể giữ cấu trúc:

~~~json
{
  "token_type": "Bearer",
  "access_token": "[REDACTED]",
  "refresh_token": "[REDACTED]",
  "expires_in": 900
}
~~~

Nếu token không phải phần cần công bố, có thể loại field hoặc viết custom body preprocessor. Tài liệu phải phản ánh đúng contract: placeholder giữ schema nhưng không tiết lộ value.

## 6. URL và query parameters

Token đôi khi bị đặt trong URL:

~~~http
GET /api/callback?code=authorization-code-secret&state=opaque-state HTTP/1.1
~~~

URL xuất hiện trong request line, curl và HTTPie snippets. RemoveHeaders không che được query string. Tránh truyền access token/session secret qua URL. Với authorization code tạm thời, dùng code giả dành riêng cho documentation test hoặc preprocess request content phù hợp.

URL có thể được lưu trong access logs, proxy logs, browser history, analytics và monitoring. REST Docs redaction chỉ bảo vệ snippets sinh từ operation đã preprocess, không tự che application logs, test failure reports, HTTP client wire logs, CI debug output, cache hoặc artifacts khác.

## 7. Helper dùng chung cho security preprocessing

Nếu nhiều tests cần cùng chính sách, tạo helper:

~~~java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

private static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        removeHeaders(
            "Authorization",
            "Cookie",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN",
            "X-Api-Key",
            "Proxy-Authorization"
        )
    );
}

private static OperationResponsePreprocessor sanitizeResponse() {
    return preprocessResponse(
        removeHeaders("Set-Cookie", "Authorization")
    );
}
~~~

Dùng trong operation:

~~~java
.andDo(document("orders-create",
    sanitizeRequest(),
    sanitizeResponse(),
    requestFields(...),
    responseFields(...)
));
~~~

Imports và chữ ký helper cần khớp API REST Docs của dự án. Có thể bổ sung body redaction cho login/token operations thay vì áp dụng pattern không cần thiết cho mọi endpoint.

Không che quá mức: Content-Type, Accept, Location hoặc header mô tả contract vẫn nên giữ nếu không chứa secret. Review danh sách theo hệ thống thực tế.

## 8. Dùng synthetic credentials trong tests

Test credentials cần được thiết kế sao cho nếu lọt vào snippet cũng không cấp quyền thật:

- Dùng token giả chỉ có ý nghĩa trong test.
- Dùng mock authentication principal thay vì token developer.
- Không đọc secret production/CI rồi nhúng vào request test.
- Không commit .env, keystore hoặc credentials.
- Không dùng cookie từ browser session.
- Nếu test ký JWT, dùng signing key test riêng.
- Hạn chế wire/debug logging có thể in request.

JWT giả nhưng được ký bằng private key thật vẫn nguy hiểm. Tách signing key test và giới hạn issuer/audience/quyền của fixture.

## 9. Kiểm tra snippet không chứa secret

Dùng sentinel chỉ xuất hiện trong test fixture:

~~~java
private static final String TEST_SECRET =
    "DOCS_ONLY_SECRET_7f91c2";
~~~

Sau khi REST Docs tạo snippets, kiểm tra toàn bộ output không còn sentinel. Assertion minh họa:

~~~java
assertThat(allGeneratedSnippetText)
    .doesNotContain(TEST_SECRET)
    .doesNotContain("JSESSIONID=session-secret");
~~~

Kiểm tra exact secret sentinel thay vì cấm từ Authorization, vì docs có thể cần nói về tên header/authentication scheme. Có thể xác nhận placeholder [REDACTED] còn lại nếu đó là nội dung mong muốn.

### 9.1. Kiểm tra mọi loại snippet

Tìm trong toàn bộ generated output, không chỉ HTTP request:

- http-request và http-response.
- curl-request và httpie-request.
- request-body và response-body.
- request-fields và response-fields.
- Header/parameter/custom snippets.
- Trang Markdown/Asciidoctor sau assemble.

Token có thể đã bị che trong request snippet nhưng còn trong curl hoặc body snippet nếu preprocessor không áp dụng đúng operation/content.

## 10. Áp dụng cho từng HTTP test client

### 10.1. MockMvc

~~~java
mockMvc.perform(get("/api/orders/101")
        .header("Authorization", "Bearer DOCS_ONLY_SECRET")
        .cookie(new Cookie("JSESSIONID", "DOCS_SESSION_SECRET")))
    .andExpect(status().isOk())
    .andDo(document("orders-get",
        preprocessRequest(
            removeHeaders("Authorization", "Cookie")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ));
~~~

Ví dụ dùng synthetic values. Nếu controller cần authentication, cấu hình test security context bằng cơ chế Spring Security test phù hợp; không lấy token thật chỉ để vượt security filter.

### 10.2. WebTestClient

~~~java
webTestClient.get()
    .uri("/api/orders/101")
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders-get-webflux",
        preprocessRequest(
            removeHeaders("Authorization")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ));
~~~

Dùng WebTestClient REST Docs filter của đúng version Spring REST Docs. Redaction phải gắn vào operation trước khi snippet được ghi.

### 10.3. REST Assured

~~~java
given(specification)
    .header("Authorization", "Bearer DOCS_ONLY_SECRET")
    .filter(document("orders-get-restassured",
        preprocessRequest(
            removeHeaders("Authorization")
        ),
        preprocessResponse(
            removeHeaders("Set-Cookie")
        )
    ))
.when()
    .get("/api/orders/101")
.then()
    .statusCode(200);
~~~

Specification phải cấu hình server/base URI, port và REST Docs context. Filter cần dùng trong mọi operation có auth; có thể đặt redaction trong helper/filter chung.

## 11. Viết phần Authentication mà không lộ credential

Tài liệu vẫn cần giải thích scheme. Dùng placeholder rõ ràng trong phần hướng dẫn, không include raw header từ test:

~~~markdown
## Authentication

Endpoint yêu cầu Bearer token trong Authorization header.

Ví dụ giá trị header: Bearer <access-token>
~~~

Nếu muốn hiển thị request header trong tài liệu, viết ví dụ placeholder riêng sau khi redaction. Không include giá trị từng mang credential thật.

## 12. CI: phát hiện secret trong output tài liệu

~~~mermaid
flowchart TD
    A["HTTP tests với synthetic credentials"] --> B["Apply preprocessors"]
    B --> C["Generate snippets"]
    C --> D["Assemble Markdown/Asciidoctor"]
    D --> E["Scan snippets và final docs"]
    E --> F{"Sensitive value found?"}
    F -->|Yes| X["Fail build"]
    F -->|No| G["Render documentation"]
    G --> H{"Render and links pass?"}
    H -->|No| X
    H -->|Yes| I["Publish docs"]
~~~

CI cần:
1. Dùng synthetic data và sentinel rõ ràng.
2. Sinh toàn bộ REST Docs snippets.
3. Assemble trang cuối.
4. Scan generated directory và final docs.
5. Chạy secret scanner theo policy tổ chức.
6. Fail build nếu có sentinel/secret đáng ngờ.
7. Không in nguyên secret vào log khi báo lỗi.
8. Chỉ publish khi tests, scan và render đều pass.

Scanner có thể false positive, ví dụ token giả trong hướng dẫn. Dùng allowlist hẹp, có scope rõ và review; không allowlist credential thật.

### 12.1. Scan nhiều lớp

Scan generated snippets, assembled Markdown/Asciidoc, rendered HTML nếu có code examples và artifacts CI đính kèm. Nếu phát hiện secret thật, rotate/revoke theo policy. Xóa file trong working tree không xóa Git history, CI cache hoặc artifact đã publish.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Authorization còn trong curl | Preprocessor không gắn vào operation | Kiểm tra document(...) và mọi snippets. |
| Cookie lộ trong response | Chỉ remove request Cookie, quên Set-Cookie | Preprocess cả request và response. |
| Token còn trong body | Chỉ remove headers | Dùng body replacement phù hợp. |
| Query token vẫn còn | Secret nằm trong request line | Không dùng secret URL; dùng synthetic code và xử lý content. |
| Regex che sai JSON | Pattern không phù hợp serialization | Test payload thực và xác minh output. |
| Docs không giải thích auth | Đã loại header nhưng không viết scheme | Bổ sung mô tả và placeholder. |
| CI fixture dùng secret thật | Dùng credential từ environment | Tạo identity và token giả. |
| Leak chỉ phát hiện sau publish | Không scan generated/final docs | Thêm scan trước publish gate. |
| Scanner false positive | Pattern quá rộng | Dùng sentinel và allowlist hẹp. |
| Secret còn trong Git history | File từng được commit/artifact lưu | Rotate credential và xử lý history/artifacts. |

## 14. Bài thực hành

Tạo hai endpoint giả định:

- POST /api/auth/login trả access token và refresh token.
- GET /api/orders/101 yêu cầu Bearer authentication; ứng dụng có thể trả Set-Cookie nếu quản lý session.

Thực hiện:

1. Viết HTTP tests với synthetic credentials riêng.
2. Loại Authorization, Cookie, Set-Cookie và CSRF headers bằng preprocessors.
3. Mask access_token, refresh_token và password trong body snippets.
4. Nếu token xuất hiện trong query/request line, dùng dữ liệu giả và xử lý riêng.
5. Sinh HTTP, curl, HTTPie, request/response body và descriptor snippets.
6. Kiểm tra không snippet nào còn sentinel.
7. Viết phần Authentication bằng placeholder và mô tả scheme.
8. Assemble tài liệu cuối và scan lần nữa.
9. Cấu hình CI fail trước publish nếu phát hiện sentinel/secret.
10. Cố ý bỏ một preprocessor trong test thử nghiệm để xác nhận leak check bắt được sentinel.

**Tiêu chí hoàn thành:** tài liệu giải thích đúng cách xác thực nhưng không công bố credential; headers và body đã được làm sạch; mọi snippets và trang cuối được scan; tests dùng synthetic credentials; CI chặn publish khi phát hiện secret.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — Operation Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
