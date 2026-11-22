# Không ghi secret vào generated snippets

## 1. Vì sao generated snippets cần được bảo vệ?

Spring REST Docs ghi nhận HTTP request và response từ các bài kiểm thử để sinh tài liệu API. Các snippet như `http-request.adoc`, `request-headers.adoc`, `request-body.adoc`, `http-response.adoc` và `response-body.adoc` có thể chứa dữ liệu nhạy cảm nếu test gửi credential hoặc payload thật.

Một token lọt vào snippet có thể được commit vào Git, đính kèm trong artifact CI, đưa lên website tài liệu hoặc lưu trong cache. Việc xóa giá trị khỏi file ở commit sau không tự xóa nó khỏi lịch sử hay artifact đã phát hành. Vì vậy, bảo vệ snippet phải bắt đầu từ dữ liệu test, tiếp tục ở bước preprocessing và kết thúc bằng kiểm tra output trước khi publish.

Trong **SPRING_REST_DOCS**, test HTTP dùng MockMvc, WebTestClient hoặc REST Assured làm nguồn sinh snippet cho request, response, payload, parameters và headers. Chương **Bảo mật** tập trung vào việc bảo đảm các tài liệu được tạo ra không chứa secret. Bài này hướng dẫn nhận diện dữ liệu nhạy cảm, dùng preprocessors, bảo vệ custom snippet, kiểm tra generated files và tổ chức CI an toàn.

Sau bài học, bạn có thể:

- Nhận diện secret có thể xuất hiện trong request, response và custom snippets.
- Dùng dữ liệu giả hoặc credential test có vòng đời ngắn.
- Loại bỏ hoặc thay thế header nhạy cảm trước khi ghi snippet.
- Che dữ liệu trong body, URI, cookie và multipart metadata.
- Kiểm tra toàn bộ output để bảo đảm giá trị secret không xuất hiện.
- Bảo vệ log và artifact CI, đồng thời xử lý khi secret đã bị lộ.

## 2. Những vị trí có thể làm lộ secret

| Vị trí | Ví dụ | Rủi ro |
| --- | --- | --- |
| Request header | `Authorization: Bearer ...`, `X-API-Key` | Lộ quyền gọi API |
| Cookie | `Cookie`, `Set-Cookie`, session ID | Chiếm phiên đăng nhập |
| Query string | `?access_token=...` | URI được ghi vào HTTP snippet và log |
| Request body | `password`, `clientSecret`, `refreshToken` | Lộ thông tin xác thực |
| Response body | access token, reset token, API key | Lộ credential mới phát hành |
| Multipart | file thật, metadata cá nhân, filename nhạy cảm | Lộ nội dung hoặc định danh |
| Custom snippet | dump toàn bộ headers/body | Bỏ qua redaction của snippet chuẩn |
| CI | console output, test report, artifact | Mở rộng phạm vi rò rỉ |

Không chỉ token mới là secret. Email, số điện thoại, địa chỉ, mã khách hàng, dữ liệu y tế hoặc thông tin thanh toán cũng có thể là dữ liệu cần bảo vệ theo chính sách tổ chức.

## 3. Bắt đầu bằng dữ liệu test an toàn

Redaction là lớp bảo vệ bổ sung. Cách tốt nhất là không đưa secret thật vào test tài liệu hóa.

- Dùng principal giả lập, mock authentication hoặc token chỉ có giá trị trong test.
- Nếu cần kiểm tra Bearer authentication, tạo token bằng key riêng dành cho test; không đọc token production từ máy developer.
- Dùng dữ liệu tổng hợp như `user@example.test`, số điện thoại giả và file fixture vô hại.
- Không dùng bản sao database production làm fixture.
- Không ghi credential vào source, `application-test.yml`, build file hoặc test report.

Ví dụ token giả:

```java
String testToken = "test-only-token-123";

mockMvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk());
```

Token này chỉ minh họa cho test. Nếu test cần token có chữ ký hợp lệ, hãy ký bằng key test hoặc dùng cơ chế security test của framework. Không tái sử dụng credential đang cấp quyền trên môi trường thật.

## 4. Loại bỏ request headers nhạy cảm

Spring REST Docs có request preprocessors chạy trước khi snippet được ghi. Dùng `removeHeaders(...)` khi header không cần xuất hiện trong tài liệu:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Authorization", "Cookie", "X-API-Key")
    )
));
```

Preprocessor thay đổi bản request dùng cho tài liệu hóa. Request thực tế vẫn được gửi với token để authentication chạy; giá trị header bị loại khỏi bản ghi snippet.

Nếu tài liệu cần thể hiện rằng endpoint yêu cầu header, có thể mô tả header bằng `requestHeaders(...)` nhưng không đưa giá trị bí mật vào ví dụ. Chỉ xóa giá trị là đủ khi người đọc không cần thấy header; nếu cần giữ tên và thay giá trị, dùng `modifyHeaders(...)`.

## 5. Thay giá trị header bằng placeholder

`modifyHeaders()` cho phép đặt giá trị an toàn trong request được ghi:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

.andDo(document("profile-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .set("X-API-Key", "<api-key>")
    )
));
```

Kết quả vẫn cho thấy header mà client cần gửi, nhưng giá trị thật không được ghi vào snippet. Có thể kết hợp xóa cookie:

```java
.andDo(document("profile-get",
    preprocessRequest(
        removeHeaders("Cookie"),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
    )
));
```

Kiểm tra API builder theo phiên bản Spring REST Docs trong dự án. Tránh ghi placeholder có hình dạng giống credential đang hoạt động; dùng giá trị hiển thị rõ là giả như `<access-token>`.

## 6. Bảo vệ response headers

Response có thể chứa `Set-Cookie`, token mới hoặc header nội bộ. Dùng `preprocessResponse(...)` riêng:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

.andDo(document("login-success",
    preprocessResponse(
        removeHeaders("Set-Cookie", "X-Internal-Token")
    )
));
```

Nếu cần mô tả cookie hoặc header token trong contract, thay giá trị bằng placeholder và chỉ công bố thuộc tính không nhạy cảm. Không giả định `preprocessRequest(...)` tự áp dụng cho response; mỗi phía phải được cấu hình rõ ràng.

## 7. Che dữ liệu trong request và response body

Header preprocessing không che các field trong JSON. Ví dụ body đăng nhập:

```json
{
  "username": "demo-user",
  "password": "test-password-value",
  "clientSecret": "test-client-secret"
}
```

Với JSON đơn giản, `replacePattern(...)` có thể thay các chuỗi nhạy cảm trước khi snippet được ghi:

```java
import java.util.regex.Pattern;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

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
```

Có thể áp dụng cách tương tự cho response:

```java
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
```

Regex chỉ phù hợp với cấu trúc đã biết và đơn giản. JSON có escape, nested object hoặc nhiều định dạng có thể khiến regex bỏ sót. Với payload phức tạp, dùng parser JSON để thay giá trị theo path rồi serialize lại, hoặc thiết kế fixture không chứa secret ngay từ đầu. Không coi regex là bộ lọc bảo mật tổng quát.

## 8. Tránh secret trong URI và query parameters

Không nên truyền access token hoặc API key qua query string. URI thường được ghi vào `http-request.adoc`, access log, reverse proxy và hệ thống giám sát.

Nếu API hiện hữu buộc phải nhận query secret:

- Ưu tiên thay đổi API để dùng Authorization header.
- Nếu chưa thể thay đổi, dùng request preprocessor để thay query value trước khi ghi snippet.
- Kiểm tra cả `http-request.adoc` và snippet `request-parameters.adoc`.
- Không đưa query string thô vào custom snippet.

Một lần redaction trên header không che query string. Phải kiểm tra riêng URI và parameters.

## 9. Multipart parts và file upload

Multipart request có thể chứa file thật, filename chứa tên khách hàng hoặc JSON metadata có dữ liệu riêng tư. Dùng file fixture tổng hợp và metadata giả. Custom snippet nên giới hạn thông tin ở part name, media type và kích thước nếu các trường đó đủ cho tài liệu.

Không đưa `part.getContent()` hoặc `getContentAsString()` trực tiếp vào custom snippet khi chưa có quy tắc redaction. Filename cũng là dữ liệu do client cung cấp; không giả định nó luôn vô hại.

Nếu cần minh họa file, dùng fixture công khai hoặc tạo dữ liệu ngẫu nhiên trong test. Không lấy tài liệu, ảnh hồ sơ hoặc file upload từ production để sinh docs.

## 10. Custom snippet phải dùng allowlist

Custom snippet có thể đọc trực tiếp `OperationRequest`, `OperationResponse` và headers. Nếu đưa toàn bộ `HttpHeaders` vào model, nó có thể làm lộ dữ liệu dù snippet mặc định đã được preprocess.

Không nên:

```java
model.put("headers", operation.getRequest().getHeaders());
```

Thay vào đó, chọn rõ những giá trị được phép công bố:

```java
HttpHeaders headers = operation.getRequest().getHeaders();

model.put("accept", headers.getFirst(HttpHeaders.ACCEPT));
model.put("contentType", headers.getContentType());
model.put("authorizationPresent",
        headers.containsKey(HttpHeaders.AUTHORIZATION));
model.put("authorizationValue", "<access-token>");
```

Đây là allowlist: chỉ các key được chọn mới được đưa vào template. Áp dụng cùng nguyên tắc cho response headers, cookies, URI, query parameters và multipart metadata. Nếu custom snippet tự đọc raw operation data, hãy bảo đảm nó dùng dữ liệu đã được làm sạch hoặc tự redaction trước khi tạo model.

## 11. Kiểm tra generated snippets sau khi ghi

Preprocessor có thể bị bỏ sót khi một test mới được thêm. Vì vậy, cần assertion trên output generated, không chỉ kiểm tra code có gọi `removeHeaders(...)`.

Ví dụ sau khi test sinh snippet:

```java
Path operationDir = snippetsDir.resolve("profile-get");
String request = Files.readString(
        operationDir.resolve("http-request.adoc"));

assertThat(request)
        .doesNotContain("test-only-token-123")
        .doesNotContain("test-api-key")
        .doesNotContain("test-session")
        .contains("<access-token>");
```

Kiểm tra thêm `request-headers.adoc`, body snippet và custom snippets nếu chúng được tạo. Có thể quét tất cả file trong operation directory:

```java
try (Stream<Path> paths = Files.walk(operationDir)) {
    List<String> contents = paths
        .filter(Files::isRegularFile)
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();

    assertThat(contents)
        .noneMatch(content -> content.contains("test-only-token-123"));
}
```

Không đưa giá trị secret vào assertion failure message hoặc log. Test chỉ cần báo file nào vi phạm và loại dữ liệu nào bị phát hiện.

## 12. Quản lý secret trong CI

Redaction trong snippet không thay thế quản lý credential. Pipeline nên:

1. Dùng test principal hoặc credential dành riêng cho test.
2. Không in raw request/response khi test thất bại.
3. Chạy documentation tests và sinh snippets.
4. Quét generated files trước khi kết xuất hoặc publish.
5. Giới hạn quyền đọc artifact CI.
6. Không publish thư mục test thô nếu chưa qua kiểm tra secret.
7. Lưu log scanner mà không in lại giá trị đã phát hiện.

Secret scanner là lớp bổ sung. Scanner tổng quát có thể không nhận diện token theo định dạng riêng của tổ chức; assertion trên các giá trị test cụ thể vẫn cần thiết.

## 13. Xử lý khi secret đã lọt vào snippet

Nếu phát hiện credential thật trong snippet hoặc artifact:

1. Dừng publish hoặc chia sẻ artifact bị ảnh hưởng.
2. Xác định loại secret, phạm vi truy cập và các nơi đã lưu bản sao.
3. Thu hồi hoặc rotate credential nếu nó còn hiệu lực.
4. Sửa test/preprocessor và tạo lại snippets sạch.
5. Kiểm tra Git history, CI artifacts, website tài liệu và cache.
6. Thực hiện quy trình incident/security của tổ chức nếu secret đã ra ngoài phạm vi kiểm soát.
7. Bổ sung assertion hoặc scanner để ngăn tái diễn.

Chỉ xóa file khỏi working tree không xóa secret khỏi Git history hoặc artifact đã publish. Việc làm sạch lịch sử cần theo quy trình được tổ chức phê duyệt, sau khi credential đã được thu hồi.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Token xuất hiện trong HTTP request snippet | Chưa preprocess request | Dùng `removeHeaders` hoặc `modifyHeaders` |
| Cookie vẫn xuất hiện | Chỉ che Authorization | Xử lý `Cookie` và `Set-Cookie` riêng |
| Password xuất hiện trong body | Chỉ redaction headers | Dùng body preprocessor hoặc fixture giả |
| Access token xuất hiện trong response | Chỉ preprocess request | Dùng `preprocessResponse` |
| Custom summary làm lộ token | Dump raw headers | Dùng allowlist và placeholder |
| Query token còn nguyên | Không kiểm tra URI | Không truyền secret qua query; redact URI nếu bắt buộc |
| File upload chứa dữ liệu thật | Dùng fixture production | Thay bằng file tổng hợp |
| Test pass nhưng snippet vẫn lộ secret | Không assert output | Quét toàn bộ operation directory |
| Secret xuất hiện trong log CI | Reporter in request/response khi fail | Dùng dữ liệu giả và tắt raw logging |
| Chỉ xóa file mới | Secret còn trong history/artifact | Rotate và xử lý history/artifact theo incident process |

## 15. Asciidoctor và build/CI

Các snippet đã được preprocess vẫn được include như bình thường:

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

Luồng CI:

```text
Documentation HTTP tests
        |
        v
Request/response preprocessors
        |
        +--> Remove or replace sensitive headers
        +--> Redact sensitive body values
        |
        v
Generated snippets
        |
        v
Secret assertions + scanner
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

Secret scan phải chạy sau khi snippet được tạo và trước khi artifact được publish. Build tài liệu thành công không tự chứng minh nội dung an toàn; bước kiểm tra secret là một gate riêng.

## 16. Bài thực hành

Với endpoint `GET /api/profile` yêu cầu Bearer token:

1. Tạo token giả dành riêng cho test.
2. Gửi token qua `Authorization` và dùng `modifyHeaders()` để thay bằng `<access-token>` trong snippet.
3. Gửi cookie phiên và API key giả; bảo đảm chúng bị xóa hoặc thay thế.
4. Tạo request JSON có `password` và `clientSecret`; redact trước khi ghi body snippet.
5. Tạo response có `accessToken`; dùng response preprocessor để che giá trị.
6. Viết custom snippet chỉ lấy allowlist headers.
7. Quét toàn bộ operation directory và assert các giá trị test bí mật không xuất hiện.
8. Thêm secret scanner vào CI trước Asciidoctor/publish.
9. Kiểm tra log khi test thất bại không in raw request hoặc response.
10. Bỏ thử một preprocessor để xác nhận assertion làm build thất bại.

### Câu hỏi tự đánh giá

- Vì sao `Authorization`, `Cookie` và `Set-Cookie` cần được xử lý riêng?
- `removeHeaders(...)` khác `modifyHeaders()` ở kết quả snippet như thế nào?
- Request preprocessor có che response body không?
- Vì sao custom snippet cần allowlist ngay cả khi snippet chuẩn đã được preprocess?
- Khi nào regex redaction không đủ an toàn cho JSON?
- Vì sao cần assertion trên generated files sau khi chạy test?
- Secret scan nên chạy trước hay sau bước sinh snippets?
- Nếu secret thật đã được commit, vì sao chỉ xóa file ở commit mới là chưa đủ?
- Làm thế nào thể hiện header cần thiết mà không lộ giá trị?

**Ghi nhớ:** Hãy coi generated snippets là artifact có thể được commit và publish. Dùng dữ liệu giả, preprocess cả request lẫn response, giới hạn custom snippet bằng allowlist và kiểm tra output sau khi sinh. Redaction không thay thế quản lý secret; nếu credential thật đã lọt vào history hoặc artifact, cần thu hồi và xử lý theo quy trình incident.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): request/response preprocessors.
- [Spring REST Docs — `Preprocessors` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): `removeHeaders`, `modifyHeaders`, `replacePattern` và helper liên quan.
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html): mô tả request/response headers.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý và luân chuyển secret.
