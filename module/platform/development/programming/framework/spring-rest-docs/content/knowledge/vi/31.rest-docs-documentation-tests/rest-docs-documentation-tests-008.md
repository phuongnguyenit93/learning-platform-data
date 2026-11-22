# Test bảo mật không để token lọt vào snippet

## 1. Vì sao snippet cần được kiểm tra bảo mật?

Spring REST Docs ghi lại request và response từ các bài kiểm thử HTTP để sinh tài liệu API. Điều này rất hữu ích vì snippet phản ánh dữ liệu đã đi qua operation được test. Tuy nhiên, request/response có thể chứa thông tin không được phép công bố: access token, refresh token, cookie phiên, API key, email thật, số điện thoại, dữ liệu cá nhân hoặc nội dung nhạy cảm trong JSON.

Nếu test dùng credential thật hoặc preprocessor không che dữ liệu trước khi ghi snippet, những giá trị này có thể xuất hiện trong `http-request.adoc`, `request-headers.adoc`, `request-body.adoc`, custom snippet hoặc artifact CI. Generated documentation thường được commit, publish hoặc lưu làm artifact; một secret đã lọt vào đó có thể tồn tại lâu sau khi credential bị thu hồi.

Trong **SPRING_REST_DOCS**, test HTTP bằng MockMvc, WebTestClient hoặc REST Assured là nguồn sinh snippet cho request, response, payload, parameters và headers. Bài này thuộc chương **Kiểm thử tài liệu**, tập trung vào việc bảo đảm dữ liệu nhạy cảm được loại bỏ hoặc thay thế trước khi ghi snippet, đồng thời kiểm tra output để phát hiện rò rỉ.

Sau bài học, bạn có thể:

- Nhận diện vị trí token và dữ liệu nhạy cảm có thể lọt vào snippet.
- Dùng request/response preprocessors để loại bỏ hoặc thay thế header.
- Che field nhạy cảm trong request và response body.
- Bảo vệ custom snippet bằng nguyên tắc allowlist.
- Kiểm tra generated snippets và artifact CI không chứa secret.
- Phân biệt dữ liệu giả trong test với credential thật trong môi trường chạy.
- Xử lý sự cố nếu secret đã bị commit hoặc publish.

## 2. Những nơi có thể làm lộ secret

Thông tin nhạy cảm không chỉ nằm trong `Authorization`. Hãy kiểm tra tất cả phần dữ liệu mà test hoặc custom snippet có thể ghi ra.

| Vị trí | Ví dụ | Rủi ro |
| --- | --- | --- |
| Request headers | `Authorization: Bearer ...`, `X-API-Key` | Lộ credential gọi API |
| Cookies | `JSESSIONID`, session cookie | Lộ phiên đăng nhập |
| Request body | `password`, `refreshToken`, `clientSecret` | Lộ thông tin xác thực |
| Query parameters | `?access_token=...` | Secret nằm trong URI |
| Response body | access token, reset token, dữ liệu cá nhân | Lộ credential hoặc PII |
| Multipart parts | file chứa dữ liệu thật, metadata nhạy cảm | Lộ nội dung upload |
| Custom snippet | dump toàn bộ headers hoặc body | Bỏ qua cơ chế che ở snippet mặc định |
| CI logs/artifacts | test failure in request, generated snippets | Secret lan sang log hoặc artifact |

Hãy lập allowlist dữ liệu được phép công bố. Ví dụ, request documentation có thể giữ `Accept`, `Content-Type` và một header correlation giả; không cần ghi giá trị `Authorization` hoặc cookie phiên.

Không nên dùng dữ liệu production để tạo snippet. Test fixture nên chứa dữ liệu tổng hợp, tên miền giả và credential dành riêng cho test.

## 3. Che request headers bằng preprocessor

Spring REST Docs cung cấp request preprocessors để biến đổi request trước khi snippet được ghi. Hai lựa chọn thường dùng là `removeHeaders(...)` và `modifyHeaders(...)`.

### 3.1. Loại bỏ header nhạy cảm

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-API-Key")
    ),
    requestHeaders(
        headerWithName("Accept").description("Định dạng response")
    )
));
```

`removeHeaders(...)` xóa header khỏi bản request được ghi vào snippet. Nó không xóa header khỏi request thực tế mà test gửi tới ứng dụng; operation vẫn được xác thực với credential cần thiết, nhưng tài liệu không lưu giá trị đó.

Nếu header không cần xuất hiện trong tài liệu, loại bỏ toàn bộ header là lựa chọn đơn giản. Nếu muốn giữ tên header nhưng thay giá trị bằng placeholder, dùng `modifyHeaders(...)`.

### 3.2. Thay giá trị bằng placeholder

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <redacted>")
            .set("X-API-Key", "<redacted>")
    )
));
```

Cách này giúp người đọc biết endpoint yêu cầu header nào mà không thấy credential thật. Kiểm tra cú pháp `modifyHeaders()` theo version Spring REST Docs của dự án; API builder hỗ trợ thao tác đặt, xóa hoặc thay đổi header.

### 3.3. Kết hợp nhiều thao tác

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie"),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-API-Key", "<api-key>")
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer token dùng để xác thực"),
        headerWithName("Accept")
            .description("Định dạng response")
    )
));
```

Header `Cookie` bị loại bỏ; `Authorization` và `X-API-Key` vẫn có mặt với giá trị placeholder. `requestHeaders(...)` mô tả contract của header, còn preprocessor kiểm soát giá trị được ghi ra. Không đưa token thật vào phần description hoặc ví dụ.

## 4. Che response headers

Response cũng có thể chứa dữ liệu nhạy cảm như `Set-Cookie`, token mới hoặc header nội bộ. Dùng response preprocessor tương ứng:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Token")
    ),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Định dạng response")
    )
));
```

Nếu response contract cần thể hiện sự tồn tại của `Set-Cookie`, hãy thay giá trị bằng placeholder thay vì xóa header, và chỉ mô tả những thuộc tính không nhạy cảm. Cookie value, session identifier và token không được đưa vào snippet.

Không giả định request preprocessor cũng áp dụng cho response. Cần cấu hình đúng `preprocessRequest(...)` và `preprocessResponse(...)` theo dữ liệu cần bảo vệ.

## 5. Che secret trong request và response body

Header preprocessing không bảo vệ JSON body. Nếu request có:

```json
{
  "username": "demo-user",
  "password": "correct-horse-battery",
  "clientSecret": "secret-value"
}
```

cần thay thế các giá trị nhạy cảm trước khi tạo snippet. Spring REST Docs cung cấp `replacePattern(...)` để thay chuỗi khớp regex trong nội dung đã preprocess.

Ví dụ:

```java
import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

.andDo(document("oauth-token",
    preprocessRequest(
        replacePattern(
            Pattern.compile("\"password\"\\s*:\\s*\"[^\"]*\""),
            "\"password\":\"<redacted>\""
        ),
        replacePattern(
            Pattern.compile("\"clientSecret\"\\s*:\\s*\"[^\"]*\""),
            "\"clientSecret\":\"<redacted>\""
        )
    )
));
```

Có thể áp dụng `preprocessResponse(...)` tương tự nếu response body có token:

```java
.andDo(document("oauth-token",
    preprocessResponse(
        replacePattern(
            Pattern.compile("\"accessToken\"\\s*:\\s*\"[^\"]*\""),
            "\"accessToken\":\"<redacted>\""
        ),
        replacePattern(
            Pattern.compile("\"refreshToken\"\\s*:\\s*\"[^\"]*\""),
            "\"refreshToken\":\"<redacted>\""
        )
    )
));
```

Regex trên chỉ minh họa cho JSON đơn giản. Với JSON lồng sâu, escape phức tạp hoặc cấu trúc thay đổi, regex có thể bỏ sót hoặc thay sai nội dung. Hãy cân nhắc preprocess bằng parser JSON, duyệt cây dữ liệu và thay giá trị theo JSON path. Nếu có thể, dùng fixture không chứa secret ngay từ đầu; redaction là lớp bảo vệ bổ sung.

### 5.1. Không nhầm redaction với validation

Preprocessor chỉ thay đổi bản operation được ghi ra snippet. Nó không chứng minh endpoint đã mã hóa hoặc bảo vệ secret đúng cách, và cũng không thay thế test bảo mật của ứng dụng.

Ví dụ, thay `"password":"..."` bằng placeholder trong snippet không có nghĩa server đã lưu password an toàn. Việc lưu trữ, hash, truyền tải và xác thực cần test/kiểm soát riêng.

## 6. Ví dụ MockMvc: request có token nhưng snippet không có token

Giả sử endpoint cần Bearer token để truy cập. Test dùng credential giả dành riêng cho test:

```java
@Test
void documentProfileWithoutLeakingAccessToken() throws Exception {
    String testToken = "test-only-token-123";

    mockMvc.perform(get("/api/profile")
            .header("Authorization", "Bearer " + testToken)
            .header("X-API-Key", "test-api-key")
            .cookie(new Cookie("JSESSIONID", "test-session"))
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(document("profile-get",
            preprocessRequest(
                removeHeaders("Cookie"),
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .set("X-API-Key", "<api-key>")
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Bearer token xác thực"),
                headerWithName("X-API-Key")
                    .description("API key của ứng dụng"),
                headerWithName("Accept")
                    .description("Định dạng response")
            ),
            responseFields(
                fieldWithPath("id").description("Mã người dùng"),
                fieldWithPath("displayName").description("Tên hiển thị")
            )
        ));
}
```

Request thực tế vẫn gửi token test để authentication hoạt động. Request snippet được ghi với placeholder và không chứa cookie. Với token thật, không được dựa riêng vào việc test sau này sẽ che nó; test documentation phải dùng credential giả lập hoặc credential ephemeral đã được tạo chỉ cho test.

Nếu hệ thống dùng security filter, có thể dùng test security principal hoặc token ký bằng key test. Không gọi dịch vụ xác thực production chỉ để tạo snippet.

## 7. Kiểm tra generated snippet không chứa secret

Redaction cần được kiểm tra như một yêu cầu của test. Sau khi document operation chạy, đọc các snippet liên quan và xác nhận giá trị nhạy cảm không xuất hiện.

Ví dụ:

```java
Path operationDir = snippetsDir.resolve("profile-get");

String requestSnippet = Files.readString(
        operationDir.resolve("http-request.adoc")
);

assertThat(requestSnippet)
        .doesNotContain("test-only-token-123")
        .doesNotContain("test-api-key")
        .doesNotContain("test-session")
        .contains("<access-token>")
        .contains("<api-key>");
```

Nếu snippet khác cũng có thể ghi headers, kiểm tra cả `request-headers.adoc`, custom summary hoặc file body tương ứng. Không chỉ kiểm tra `http-request.adoc`.

Có thể viết helper quét toàn bộ thư mục operation:

```java
try (Stream<Path> files = Files.walk(operationDir)) {
    List<String> generated = files
            .filter(Files::isRegularFile)
            .map(path -> {
                try {
                    return Files.readString(path);
                } catch (IOException exception) {
                    throw new UncheckedIOException(exception);
                }
            })
            .toList();

    assertThat(generated)
            .noneMatch(content -> content.contains("test-only-token-123"));
}
```

Để phát hiện nhiều loại secret, có thể kiểm tra danh sách giá trị giả đã dùng trong test. Tránh ghi chính secret vào assertion message hoặc log khi test thất bại; chỉ báo tên loại dữ liệu và file bị ảnh hưởng.

## 8. Bảo vệ custom snippet bằng allowlist

Custom snippet có thể đọc trực tiếp `OperationRequest.getHeaders()`, `OperationResponse.getHeaders()` hoặc body. Nếu code dump toàn bộ headers, nó có thể bỏ qua redaction mà nhóm đã cấu hình cho snippet mặc định.

Không nên:

```java
model.put("requestHeaders", operation.getRequest().getHeaders());
```

Thay vào đó, chọn rõ header được phép:

```java
HttpHeaders headers = operation.getRequest().getHeaders();

model.put("accept", headers.getFirst("Accept"));
model.put("contentType", headers.getFirst("Content-Type"));
model.put("correlationId", headers.getFirst("X-Correlation-Id"));
```

Đây là allowlist: chỉ những trường được chọn mới đi vào template. Nếu custom snippet cần Authorization header để mô tả sự hiện diện, hãy đưa một boolean hoặc placeholder vào model thay vì giá trị thật:

```java
model.put(
    "authorizationPresent",
    headers.containsKey(HttpHeaders.AUTHORIZATION)
);
model.put("authorizationValue", "<redacted>");
```

Cũng cần áp dụng allowlist với response headers, cookies, query parameters và multipart part metadata. Đừng đưa raw request/response body vào custom snippet trừ khi thực sự cần và đã có chiến lược redaction phù hợp.

## 9. Dữ liệu nhạy cảm trong query, multipart và response

### 9.1. Query parameters

Tránh truyền token qua query string. URL có thể được ghi trong `http-request.adoc`, log server, proxy và monitoring. Nếu API cũ bắt buộc nhận query secret, thay thế giá trị trong request preprocessor hoặc không include URI đầy đủ; ưu tiên thiết kế lại để dùng header Authorization.

### 9.2. Multipart parts

File upload có thể chứa dữ liệu thật. Dùng fixture giả, không dùng ảnh giấy tờ, hợp đồng, hồ sơ khách hàng hoặc file production. Custom snippet chỉ nên ghi part name, media type và kích thước; không dump bytes hoặc nội dung part nếu không cần.

### 9.3. Response body

Các endpoint đăng nhập, refresh token, reset password hoặc tạo API key thường trả credential trong response body. Dùng response preprocessor để thay token bằng placeholder trước khi sinh `response-body.adoc` hoặc HTTP response snippet. Nếu cần mô tả schema, `responseFields(...)` có thể mô tả field token mà không cần đưa giá trị thật; test nên dùng token giả.

### 9.4. Dữ liệu cá nhân

Email, số điện thoại, địa chỉ và định danh cá nhân cũng cần được xử lý theo chính sách dữ liệu của tổ chức. Thay bằng dữ liệu tổng hợp nhất quán, ví dụ `user@example.test`; không dùng dữ liệu production rồi kỳ vọng regex che mọi vị trí.

## 10. Bảo vệ secret trong cấu hình test và CI

Redaction trong snippet không thay thế quản lý credential:

- Không hard-code credential production trong source, test fixture hoặc build file.
- Dùng test principal, mock authentication hoặc token ký bằng key riêng cho test.
- Nếu test cần secret tạm thời, lấy từ secret store của môi trường CI và chỉ cấp quyền tối thiểu.
- Không in header/body nguyên bản ra console khi test fail.
- Giới hạn quyền truy cập artifact CI chứa generated snippets.
- Không publish artifact test thô nếu chưa chạy bước kiểm tra secret.
- Xóa hoặc rotate credential nếu phát hiện giá trị thật đã bị ghi vào repository hoặc artifact.

Với test documentation, credential giả cố định thường phù hợp hơn secret dùng chung từ môi trường. Mục tiêu là kiểm tra luồng authentication mà không tạo ra dữ liệu nhạy cảm có giá trị thực.

## 11. Xử lý khi secret đã lọt vào snippet

Nếu phát hiện token hoặc dữ liệu nhạy cảm trong generated documentation:

1. Dừng publish artifact bị ảnh hưởng.
2. Xác định loại credential, phạm vi và nơi đã được lưu hoặc chia sẻ.
3. Thu hồi/rotate credential nếu đó là secret còn hiệu lực.
4. Xóa giá trị khỏi source và generated snippets; tạo lại artifact sau khi redaction được sửa.
5. Kiểm tra commit history, CI artifacts, package/site đã publish và bản cache.
6. Thực hiện quy trình incident/security của tổ chức nếu dữ liệu đã ra ngoài phạm vi kiểm soát.
7. Thêm test assertion hoặc scanner để ngăn tái diễn.

Chỉ xóa file khỏi working tree không làm secret biến mất khỏi Git history hoặc artifact đã publish. Nếu secret thật đã được commit, cần xử lý theo quy trình thu hồi và làm sạch lịch sử được tổ chức phê duyệt; không coi việc sửa commit mới là đủ.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong `http-request.adoc` | Chưa preprocess request | Dùng `removeHeaders` hoặc `modifyHeaders` |
| Token vẫn có trong custom summary | Custom snippet đọc raw headers từ operation | Chuyển sang allowlist và placeholder |
| Cookie xuất hiện dù đã che Authorization | Chỉ xử lý một header | Loại bỏ/che cả `Cookie` và `Set-Cookie` |
| Password xuất hiện trong request body | Chỉ redact headers | Dùng body preprocessor hoặc fixture giả |
| Access token xuất hiện trong response body | Chỉ preprocess request | Dùng `preprocessResponse(...)` |
| Regex không che JSON lồng nhau | Regex không hiểu cấu trúc JSON | Parse JSON và thay theo path |
| Test pass nhưng snippet vẫn có secret | Chưa assertion trên generated output | Quét toàn bộ operation directory |
| Secret lộ trong log CI | Test failure dump request/response | Tắt log raw, dùng dữ liệu giả và kiểm soát reporter |
| Dùng token thật để kiểm thử tài liệu | Tái sử dụng credential môi trường | Dùng mock principal hoặc token test |
| Chỉ xóa snippet khỏi branch mới | Secret còn trong history/artifact | Rotate và xử lý history/artifact theo incident process |

## 13. Asciidoctor và build/CI

Các snippet đã preprocess được include như bình thường:

```adoc
= Profile API
:toc: left

== Lấy hồ sơ

=== HTTP request
include::{snippets}/profile-get/http-request.adoc[]

=== Request headers
include::{snippets}/profile-get/request-headers.adoc[]

=== Response fields
include::{snippets}/profile-get/response-fields.adoc[]
```

Luồng CI đề xuất:

```text
Documentation HTTP tests
        |
        v
Request/response preprocessors
        |
        +--> Remove or replace sensitive headers
        +--> Redact sensitive body fields
        |
        v
Spring REST Docs generated snippets
        |
        v
Secret scan + assertions on generated files
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

Với Gradle và plugin Asciidoctor đã cấu hình:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Secret scan nên chạy sau khi test tạo snippet và trước khi artifact được publish. Scanner là lớp kiểm tra bổ sung; test assertion theo các giá trị test cụ thể vẫn cần thiết vì scanner tổng quát có thể bỏ sót token có định dạng riêng.

Không lưu generated snippets có secret vào cache công khai. Khi build thất bại vì phát hiện secret, log chỉ nên báo file/path và rule bị vi phạm, không in lại giá trị đã phát hiện.

## 14. Bài thực hành

Với endpoint `GET /api/profile` yêu cầu Bearer token:

1. Tạo token giả dành riêng cho test và gửi qua `Authorization`.
2. Dùng `preprocessRequest(removeHeaders(...))` hoặc `modifyHeaders()` để loại bỏ/thay token.
3. Thêm cookie phiên và API key giả; bảo đảm chúng cũng được che.
4. Tạo một request JSON có field `password` và `clientSecret`; dùng body preprocessor thay giá trị trước khi ghi snippet.
5. Tạo endpoint response có `accessToken`; dùng `preprocessResponse(...)` để che response body.
6. Thêm custom snippet chỉ đọc allowlist headers; không dump `HttpHeaders` nguyên bản.
7. Sau test, quét toàn bộ operation directory và assert các giá trị giả nhạy cảm không xuất hiện.
8. Chạy secret scanner trên generated snippets trước Asciidoctor/publish.
9. Kiểm tra CI logs không in raw request hoặc response khi test thất bại.
10. Thử cố ý bỏ một preprocessor để xác nhận assertion bảo mật làm build thất bại.

### Câu hỏi tự đánh giá

- Vì sao `Authorization` và `Cookie` cần được xử lý trước khi ghi snippet?
- `removeHeaders(...)` khác `modifyHeaders()` như thế nào?
- Request preprocessor có che response body không?
- Vì sao phải kiểm tra custom snippet riêng?
- Khi nào regex redaction không an toàn với JSON?
- Tại sao dữ liệu test giả vẫn cần assertion trên generated output?
- Secret scan nên chạy ở bước nào trong CI?
- Nếu secret thật đã được commit, vì sao chỉ xóa file hiện tại là chưa đủ?
- Làm thế nào giữ tên header trong tài liệu nhưng không lộ giá trị?

**Ghi nhớ:** Hãy coi generated snippet là artifact có thể được commit và publish. Dùng dữ liệu giả, preprocess cả request lẫn response, ưu tiên allowlist cho custom snippet và kiểm tra output sau khi sinh. Redaction trong tài liệu không thay thế quản lý secret, và một token thật đã lọt vào history hoặc artifact cần được thu hồi, xử lý như sự cố bảo mật.

## Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): request/response preprocessors và thay đổi nội dung trước khi sinh snippet.
- [Spring REST Docs — `Preprocessors` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `removeHeaders`, `modifyHeaders`, `replacePattern` và các helper.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): mô tả request/response headers.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý, luân chuyển và bảo vệ secret.
