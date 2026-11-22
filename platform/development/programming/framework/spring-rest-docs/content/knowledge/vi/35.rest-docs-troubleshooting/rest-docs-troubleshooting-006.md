# Header hoặc cookie nhạy cảm bị lộ trong Spring REST Docs

## 1. Vì sao dữ liệu nhạy cảm xuất hiện trong tài liệu?

Spring REST Docs tạo snippet từ request và response được test client ghi nhận. Một request có thể chứa:

```http
GET /api/profile HTTP/1.1
Authorization: Bearer eyJhbGciOi...
Cookie: SESSION=abc123; refresh_token=secret-value
X-Api-Key: live-key-value
Accept: application/json
```

Nếu test ghi lại toàn bộ request headers mà không lọc, giá trị xác thực có thể xuất hiện trong http-request.adoc, curl-request.adoc hoặc snippet khác. Response cũng có thể chứa Set-Cookie, token mới, session identifier hoặc header nội bộ. Khi tài liệu được commit, đưa lên artifact server hay publish công khai, dữ liệu nhạy cảm có thể bị chia sẻ ngoài phạm vi dự kiến.

Module **SPRING_REST_DOCS** tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet cho request, response, payload, parameter và header rồi biên soạn thành Asciidoctor/Markdown trong build/CI. Bài thuộc chương **Chẩn đoán lỗi**, tập trung phát hiện và loại bỏ header/cookie nhạy cảm trước khi snippet được công bố.

Sau bài học, bạn có thể:

1. Nhận diện header, cookie và payload có thể chứa bí mật.
2. Dùng operation preprocessors để loại bỏ hoặc thay thế giá trị nhạy cảm.
3. Phân biệt dữ liệu test giả với credential thật.
4. Kiểm tra cả request và response snippets.
5. Thêm kiểm tra rò rỉ bí mật vào CI trước khi publish tài liệu.

## 2. Dữ liệu nào cần được xem là nhạy cảm?

| Header/cookie | Rủi ro |
| --- | --- |
| Authorization | Bearer token, Basic credentials, access token |
| Proxy-Authorization | Credential xác thực với proxy |
| Cookie | Session ID, refresh token, CSRF token |
| Set-Cookie | Session mới, token, cookie có phạm vi bảo mật |
| X-Api-Key, Api-Key | API key của client hoặc service |
| X-Auth-Token | Token xác thực tùy ứng dụng |
| X-Amz-Security-Token | Temporary cloud credential |
| Forwarded, X-Forwarded-* | Có thể tiết lộ địa chỉ nội bộ và topology |
| Location | Có thể chứa token trong URL nếu ứng dụng thiết kế không an toàn |

Body cũng có thể chứa password, email, số điện thoại, access token, private key hoặc dữ liệu cá nhân. Redact header không bảo vệ payload tự động.

### 2.1. Cookie cần kiểm tra cả hai chiều

Request dùng header Cookie:

```http
Cookie: SESSION=abc123; theme=dark
```

Response dùng Set-Cookie:

```http
Set-Cookie: SESSION=xyz789; Path=/; HttpOnly; Secure; SameSite=Lax
```

Nếu chỉ redact request Cookie, response Set-Cookie vẫn có thể làm lộ session identifier. Cần kiểm tra cả hai hướng.

## 3. Preprocessing trong Spring REST Docs

Spring REST Docs cho phép biến đổi operation trước khi tạo snippet:

- preprocessRequest(...) cho request.
- preprocessResponse(...) cho response.
- removeHeaders(...) để loại header.
- replacePattern(...) để thay nội dung khớp pattern.
- modifyHeaders() để chỉnh giá trị header.

Các preprocessor chỉ thay đổi dữ liệu dùng để tạo snippet. Chúng không thay đổi request đã gửi tới server hoặc response mà ứng dụng trả về. Redact trong tài liệu không thay thế việc bảo vệ credential trong test runtime, log, CI environment hoặc source control.

## 4. Loại bỏ header nhạy cảm bằng removeHeaders()

Ví dụ MockMvc:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("X-Api-Key", "test-api-key")
        .header("Cookie", "SESSION=test-session"))
    .andDo(document("profile",
        preprocessRequest(
            removeHeaders("Authorization", "X-Api-Key", "Cookie")
        )
    ));
```

Các header bị loại khỏi request snippet. Server vẫn nhận request như test đã gửi; chỉ representation được lưu trong tài liệu không còn các header đó.

### 4.1. Loại header ở response

Ví dụ response có Set-Cookie:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {"username":"demo","password":"test-password"}
                """))
    .andDo(document("login",
        preprocessResponse(
            removeHeaders("Set-Cookie", "Authorization", "X-Internal-Token")
        )
    ));
```

Nếu tài liệu cần mô tả cookie nhưng không cần giá trị thực, thay thế value thay vì xóa toàn bộ header. Xóa Set-Cookie cũng làm mất HttpOnly, Secure, SameSite, Path và Max-Age; hãy giữ lại attributes không nhạy cảm nếu chúng thuộc contract cần document.

## 5. Thay giá trị bằng placeholder

Trong nhiều tài liệu, người đọc cần biết header có mặt và định dạng tổng quát, nhưng không cần credential thật:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer abc.def.ghi"))
    .andDo(document("profile",
        preprocessRequest(
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .set("X-Api-Key", "<api-key>")
        )
    ));
```

Placeholder nên thể hiện định dạng mà client cần gửi. Ví dụ Authorization: Bearer <access-token> cho biết scheme Bearer mà không tiết lộ token.

modifyHeaders().set(...) đặt giá trị header mới. Nếu header gốc không có, preprocessor có thể thêm header đó vào snippet. Chỉ dùng cho header thực sự thuộc request contract; không thêm header minh họa mà request thật không gửi.

## 6. Redact một phần giá trị bằng pattern

Có thể giữ cấu trúc header nhưng thay token:

```java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;

mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer abc.def.ghi"))
    .andDo(document("profile",
        preprocessRequest(
            replacePattern(
                Pattern.compile("(?i)(Bearer\\s+)[A-Za-z0-9._~-]+"),
                "$1<redacted>"
            )
        )
    ));
```

Kết quả mong muốn:

```http
Authorization: Bearer <redacted>
```

Pattern chỉ minh họa token dạng Bearer. Token thực tế có thể chứa ký tự hoặc cấu trúc khác; không coi một regex đơn lẻ là bộ phát hiện bí mật toàn diện. Với tài liệu public, loại hẳn header hoặc dùng placeholder cố định thường dễ kiểm soát hơn.

Không thay chuỗi quá rộng. Pattern tổng quát có thể làm hỏng ID nghiệp vụ, URL, JSON field không nhạy cảm hoặc checksum. Viết pattern theo header/field cụ thể và test output sau preprocessing.

## 7. Tạo preprocessor dùng chung

Nếu nhiều operation cần loại bỏ cùng nhóm header, đóng gói cấu hình:

```java
import org.springframework.restdocs.operation.preprocess.OperationRequestPreprocessor;
import org.springframework.restdocs.operation.preprocess.OperationResponsePreprocessor;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

final class DocumentationRedaction {
    private DocumentationRedaction() {}

    static OperationRequestPreprocessor safeRequest() {
        return preprocessRequest(removeHeaders(
                "Authorization", "Proxy-Authorization", "Cookie",
                "X-Api-Key", "X-Auth-Token"));
    }

    static OperationResponsePreprocessor safeResponse() {
        return preprocessResponse(removeHeaders(
                "Set-Cookie", "Authorization", "X-Internal-Token"));
    }
}
```

Dùng trong test:

```java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session"))
    .andDo(document("profile",
        DocumentationRedaction.safeRequest(),
        DocumentationRedaction.safeResponse()
    ));
```

Danh sách header cần redact phải dựa trên contract và chính sách bảo mật của dự án. Bổ sung header riêng như X-Company-Secret hoặc X-Service-Credential nếu hệ thống sử dụng. Không giả định mọi hệ thống chỉ dùng tên header phổ biến.

## 8. Cookie: redact giá trị nhưng giữ thuộc tính bảo mật

Nếu cần document cookie attributes, xóa toàn bộ Set-Cookie sẽ làm mất chi tiết quan trọng. Một lựa chọn là thay value bằng placeholder nhưng giữ attributes:

```text
Set-Cookie: SESSION=<redacted>; Path=/; HttpOnly; Secure; SameSite=Lax
```

Có thể dùng preprocessor thay thế nội dung header cụ thể hoặc tạo operation preprocessor có logic parse cookie header. Khi xử lý cookie:

- Giữ tên cookie nếu tên đó là một phần contract.
- Thay value bằng placeholder.
- Giữ HttpOnly, Secure, SameSite, Path, Domain, Max-Age nếu cần document.
- Kiểm tra nhiều Set-Cookie header; không gộp chúng thành một giá trị nếu làm thay đổi semantics.

Không dùng regex đơn giản để tách mọi cookie nếu giá trị có dấu phân cách/encoding phức tạp. Dùng parser phù hợp hoặc preprocessor chuyên biệt và test trường hợp nhiều cookie.

## 9. Payload và query parameter cũng có thể chứa bí mật

Redact header không bảo vệ body. Ví dụ:

```json
{
  "username": "demo",
  "password": "real-password",
  "accessToken": "eyJhbGciOi...",
  "email": "person@example.com"
}
```

Tài liệu không nên dùng dữ liệu production thật. Hãy dùng fixture tổng hợp, không liên kết tới người thật:

```json
{
  "username": "demo-user",
  "password": "<password>",
  "accessToken": "<access-token>",
  "email": "user@example.test"
}
```

Nếu test cần secret để xác minh behavior, lấy từ secret store của CI hoặc tạo token giả ngắn hạn trong test setup. Không ghi secret vào fixture, log hoặc snippet. Khi payload có trường nhạy cảm, dùng dữ liệu giả hoặc body preprocessor/descriptors để thay giá trị trước khi lưu tài liệu.

Query string cũng có thể làm lộ token:

```text
GET /download?access_token=secret-value
```

Ưu tiên gửi credential qua header phù hợp thay vì URL nếu API design cho phép. URL có thể bị ghi vào access log, browser history và snippet.

## 10. REST Assured và WebTestClient

Các test client khác nhau nhưng nguyên tắc preprocessing giống nhau.

### 10.1. REST Assured

```java
given()
        .header("Authorization", "Bearer test-token")
        .cookie("SESSION", "test-session")
        .filter(document("profile",
                preprocessRequest(
                        removeHeaders("Authorization", "Cookie")
                )))
        .when()
        .get("/api/profile")
        .then()
        .statusCode(200);
```

Nếu response có Set-Cookie, thêm preprocessResponse(...) vào document filter. Đảm bảo dùng operation preprocessors của Spring REST Docs REST Assured integration.

### 10.2. WebTestClient

```java
webTestClient.get()
        .uri("/api/profile")
        .headers(headers -> headers.setBearerAuth("test-token"))
        .cookie("SESSION", "test-session")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("profile",
                preprocessRequest(
                        removeHeaders("Authorization", "Cookie")
                )));
```

Đối với response, áp dụng response preprocessor ở cùng document operation nếu cần redact Set-Cookie hoặc header nhạy cảm khác.

## 11. Đừng document secret test như credential thật

Dữ liệu test nên an toàn nếu bị đọc trong log hoặc artifact:

1. Không dùng access token production trong test documentation.
2. Không commit secret vào source, fixture, .env hoặc test report.
3. Dùng credential test có scope tối thiểu và thời hạn ngắn nếu cần gọi service thật.
4. Redact trước khi snippet được ghi ra disk.
5. Không bật debug logging có thể ghi request header/body chứa secret.
6. Nếu nghi credential thật đã lọt vào artifact, thu hồi/rotate credential và xử lý artifact theo quy trình incident của tổ chức.

Redaction trong Spring REST Docs không xóa secret khỏi HTTP client logs, test failure output, proxy logs hoặc CI trace. Cần kiểm soát các nơi lưu trữ đó riêng.

## 12. Kiểm tra snippet sau redaction

Sau khi chạy test, mở các file:

```text
build/generated-snippets/profile/http-request.adoc
build/generated-snippets/profile/curl-request.adoc
build/generated-snippets/login/http-response.adoc
```

Kiểm tra Authorization không còn token runtime, Cookie không còn session/refresh token, Set-Cookie không lộ value, API key/custom auth header đã được xử lý, curl-request không tái xuất hiện secret và payload/query string không chứa password/token thật.

Đừng chỉ kiểm tra http-request.adoc. cURL snippet có thể mang cùng header nhạy cảm; response snippets có thể lộ cookie mới; payload snippets có thể chứa token trong body.

## 13. Thêm leak check vào CI

Sau khi test sinh snippets, chạy bước tìm dấu hiệu bí mật:

```bash
grep -RniE \
  'Bearer [A-Za-z0-9._~-]{12,}|SESSION=[^;[:space:]]+|refresh_token=[^;[:space:]]+|X-Api-Key: [^<[:space:]]+' \
  build/generated-snippets
```

Đây chỉ là kiểm tra heuristic, không thay thế secret scanner. Có thể tích hợp công cụ secret scanning của tổ chức trên output snippet và tài liệu đã render.

CI nên chạy test, leak scan trên toàn bộ generated-snippets, scan tài liệu đã render, fail build khi phát hiện credential chưa redact và lưu log chẩn đoán mà không in lại giá trị secret.

Không echo token trong thông báo lỗi CI. Chỉ báo tên file, loại pattern và vị trí match.

## 14. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Token xuất hiện trong http-request | Chưa preprocess request hoặc dùng sai document overload | Gắn preprocessRequest(...) vào operation |
| cURL vẫn có Authorization | Chỉ kiểm tra http-request snippet | Kiểm tra curl-request và toàn output root |
| Cookie request đã ẩn nhưng Set-Cookie lộ | Chỉ redact request | Dùng preprocessResponse(...) |
| Cookie attributes bị mất | Xóa toàn bộ Set-Cookie | Thay value và giữ attributes cần document |
| Token trong JSON vẫn còn | Chỉ redact headers | Dùng synthetic fixture hoặc body redaction |
| API key custom không được phát hiện | Danh sách header chưa đầy đủ | Bổ sung tên header theo contract |
| Secret xuất hiện trong log dù snippet sạch | Redaction chỉ tác động REST Docs operation | Kiểm soát HTTP client/debug/CI logging riêng |
| Regex làm hỏng payload hợp lệ | Pattern quá rộng | Giới hạn pattern theo header/field và test output |

## 15. Bài tập thực hành

Một endpoint profile yêu cầu Bearer token và session cookie. Response login trả:

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=temporary-session; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"accessToken":"temporary-access-token","expiresIn":900}
```

Hãy thực hiện:

1. Viết test dùng token/cookie giả, không dùng credential thật.
2. Document request và response bằng Spring REST Docs.
3. Redact Authorization, Cookie và Set-Cookie.
4. Nếu cần mô tả cookie policy, thay value bằng <redacted> nhưng giữ attributes.
5. Xử lý token trong JSON response body bằng dữ liệu giả hoặc body preprocessor.
6. Kiểm tra http-request, curl-request, http-response và response body snippets.
7. Thêm CI leak check để fail nếu token test hoặc cookie value xuất hiện.

**Tiêu chí hoàn thành:** Snippet giữ lại contract cần thiết nhưng không chứa credential/session value; response cookie attributes vẫn được document khi cần; không có secret trong cURL, payload, logs hoặc artifact.

## 16. Ghi nhớ

Spring REST Docs ghi nhận request/response nên header và cookie có thể bị lưu nguyên vào snippet nếu không xử lý. Dùng preprocessRequest(removeHeaders(...)) cho Authorization, Cookie và API key; dùng preprocessResponse(...) cho Set-Cookie và response headers. Nếu cần giữ contract, thay value bằng placeholder thay vì xóa cả header. Kiểm tra HTTP request, cURL, response và payload; dùng dữ liệu test giả, kiểm soát log riêng và thêm leak scan vào CI trước khi publish tài liệu.

### Tài liệu tham khảo

- [Spring REST Docs — Preprocessing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses/preprocessors.html)
- [Spring REST Docs — Operation Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
