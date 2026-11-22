# Ẩn stack trace và dữ liệu nội bộ

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng bằng các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào quy trình build và CI.

Request và response của API có thể chứa access token, cookie phiên, API key, email, số điện thoại, dữ liệu thanh toán hoặc thông tin nội bộ. Những giá trị này đôi khi xuất hiện trong header, query string hay JSON body. Nếu REST Docs ghi nguyên trạng vào snippet rồi đưa vào artifact CI hoặc tài liệu công khai, dữ liệu nhạy cảm có thể bị phát tán.

Bài học này hướng dẫn document lỗi bảo mật và thông tin nhạy cảm bằng cách kiểm soát dữ liệu trước khi sinh snippet. Sau bài, bạn có thể:

- Nhận diện dữ liệu nhạy cảm trong request, response, header và body.
- Phân biệt dữ liệu cần loại bỏ với dữ liệu cần giữ lại dưới dạng placeholder.
- Dùng operation preprocessors để xóa header hoặc thay giá trị nhạy cảm.
- Viết test xác nhận hành vi bảo mật mà không ghi credential thật vào tài liệu.
- Kiểm tra snippet và artifact để phát hiện rò rỉ ngoài ý muốn.
- Tích hợp bước tạo tài liệu đã làm sạch vào Asciidoctor và CI.

## 2. Rủi ro khi ghi nguyên request/response vào tài liệu

Ví dụ request xác thực:

~~~http
GET /api/profile HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.real-access-token
Cookie: SESSION=real-session-secret
X-Api-Key: live-api-key-value
Accept: application/json
~~~

Response có thể chứa cookie phiên:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=server-session-secret; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{
  "email": "person@example.com",
  "phone": "+84901234567",
  "displayName": "Nguyen An"
}
~~~

Nếu snippet chứa các giá trị trên, người đọc có thể sao chép credential hoặc xem dữ liệu cá nhân không thuộc phạm vi tài liệu. Dù token chỉ là fixture test, snippet vẫn dễ bị hiểu nhầm là credential có thể dùng được và có thể bị tái sử dụng ngoài ý muốn.

Nguyên tắc:

1. Không dùng secret thật trong test fixture.
2. Chỉ ghi những header/body field cần thiết để giải thích hợp đồng.
3. Xóa hoặc thay thế dữ liệu nhạy cảm trước khi snippet được ghi ra.
4. Kiểm tra output thực tế, không chỉ tin rằng preprocessor đã được cấu hình.
5. Giữ test assertion trên response/request gốc; preprocessing chỉ phục vụ tài liệu.

Preprocessor không làm sạch log, trace, database, test report hay request/response đã được lưu ở nơi khác. Cần quản lý các kênh lưu trữ đó riêng.

## 3. Phân loại dữ liệu cần bảo vệ

Trước khi viết preprocessor, lập danh sách nơi dữ liệu có thể xuất hiện:

| Nhóm dữ liệu | Vị trí thường gặp | Cách xử lý trong tài liệu |
| --- | --- | --- |
| Access token, refresh token, API key | Authorization, X-Api-Key, query, JSON | Xóa header hoặc thay giá trị bằng placeholder. |
| Session identifier | Cookie, Set-Cookie | Xóa toàn bộ header cookie hoặc che riêng giá trị. |
| Password, client secret | JSON request, form body | Không dùng giá trị thật; thay bằng placeholder trong snippet. |
| Email, số điện thoại, địa chỉ | JSON request/response | Dùng fixture giả; che hoặc thay nếu không cần ví dụ thật. |
| Dữ liệu thanh toán | Card number, bank account, payment token | Dùng dữ liệu test được nhà cung cấp cho phép; chỉ hiển thị phần cần thiết. |
| Mã định danh cá nhân | Government ID, ngày sinh | Loại bỏ hoặc dùng giá trị giả đã được kiểm soát. |
| Internal hostname/IP | URI, Location, hypermedia links | Chuẩn hóa host hoặc thay URI theo môi trường tài liệu. |
| Stack trace và thông tin triển khai | Error body, header debug | Không đưa vào response công khai; chỉ document error code và trace reference. |

Không phải mọi dữ liệu cá nhân đều là secret, nhưng vẫn cần cân nhắc mục đích, quyền truy cập và thời hạn lưu trữ của tài liệu. Ưu tiên dữ liệu giả có hình dạng hợp lệ thay cho dữ liệu thật rồi mới tìm cách che.

## 4. Chọn giữa xóa header và thay giá trị

Có hai cách phổ biến:

- Xóa toàn bộ header khi giá trị không cần thiết để hiểu API, ví dụ Authorization, Cookie hoặc Set-Cookie.
- Thay giá trị bằng placeholder khi tên header và sự hiện diện của nó là một phần hợp đồng, ví dụ Authorization: Bearer [REDACTED].

| Nhu cầu | Cách làm | Kết quả mong muốn |
| --- | --- | --- |
| Không cần hiển thị cookie | modifyHeaders().remove("Cookie").remove("Set-Cookie") | Header không xuất hiện trong snippet. |
| Cần cho thấy endpoint yêu cầu Bearer authentication | modifyHeaders().set("Authorization", "Bearer [REDACTED]") | Header vẫn thể hiện scheme, token được thay bằng placeholder. |
| Cần document API key header nhưng không công bố key | Thay giá trị X-Api-Key bằng [REDACTED] | Tên header còn lại, secret không xuất hiện. |
| Cần giữ cấu trúc error body nhưng ẩn email | replacePattern(...) với pattern cụ thể hoặc custom structured preprocessor | Field vẫn hiện diện với giá trị đã thay. |

Không xóa một header bắt buộc khỏi tài liệu nếu client cần biết phải gửi nó. Trong trường hợp đó, giữ tên header và mô tả cơ chế, còn giá trị credential phải là placeholder.

## 5. Xóa hoặc thay request headers bằng modifyHeaders()

Spring REST Docs cung cấp modifyHeaders() để thêm, đặt lại hoặc xóa header khỏi operation trước khi tạo snippet. Từ Spring REST Docs 3.0, đây là API thay thế cho factory method removeHeaders(...) đã deprecated.

Import:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;
~~~

Ví dụ xóa Authorization, Cookie và API key:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session")
        .header("X-Api-Key", "test-api-key"))
    .andExpect(status().isOk())
    .andDo(document("profile/get",
        preprocessRequest(
            modifyHeaders()
                .remove("Authorization")
                .remove("Cookie")
                .remove("X-Api-Key")
        )
    ));
~~~

Request vẫn được gửi với các header để ứng dụng thực thi xác thực. Preprocessor loại chúng khỏi bản operation dùng để ghi snippet. Do đó tài liệu không cho thấy credential.

Nếu muốn document rằng API dùng Bearer authentication, không nên xóa Authorization hoàn toàn. Hãy dùng giá trị test giả và che phần token để snippet vẫn thể hiện scheme.

## 6. Xóa response headers bằng modifyHeaders()

Response có thể chứa Set-Cookie, header debug hoặc header nội bộ. Dùng response preprocessor:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;

mockMvc.perform(post("/api/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(loginRequest))
    .andExpect(status().isOk())
    .andDo(document("auth/login",
        preprocessResponse(
            modifyHeaders()
                .remove("Set-Cookie")
                .remove("X-Internal-Debug")
        )
    ));
~~~

Nếu Set-Cookie không thuộc hướng dẫn tích hợp, có thể xóa khỏi snippet. Nếu cookie là cơ chế xác thực client cần biết, hãy document tên cookie, thuộc tính như HttpOnly/Secure/SameSite và cách sử dụng bằng một ví dụ giả đã được làm sạch; không công bố session ID thực.

Header xóa khỏi snippet vẫn có thể tồn tại trong response gốc. Test nên kiểm tra cookie/flag cần thiết trên response thực tế nếu chúng thuộc yêu cầu bảo mật.

## 7. Che giá trị header bằng modifyHeaders()

replacePattern(...) chỉ thay content/body của request hoặc response, không sửa header. Để giữ tên header và scheme nhưng thay credential, dùng modifyHeaders().set(...):

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

preprocessRequest(
    modifyHeaders().set("Authorization", "Bearer [REDACTED]")
)
~~~

Với request có API key:

~~~java
preprocessRequest(
    modifyHeaders().set("X-Api-Key", "[REDACTED]")
)
~~~

modifyHeaders().set(...) thay toàn bộ giá trị header bằng giá trị chỉ định. Nếu header có nhiều giá trị, set(...) đặt lại danh sách giá trị; hãy giữ lại các tham số cần thiết theo hợp đồng.

Trong test fixture, tốt nhất vẫn dùng chuỗi giả rõ ràng như test-token; preprocessor là lớp bảo vệ bổ sung cho snippet, không phải lý do để đưa secret thật vào test.

## 8. Che dữ liệu trong JSON body

removeHeaders(...) không xử lý JSON body. Với body, có thể dùng replacePattern(...) để thay một giá trị có cấu trúc ổn định.

Response ban đầu:

~~~json
{
  "id": 42,
  "email": "person@example.com",
  "phone": "+84901234567",
  "status": "ACTIVE"
}
~~~

Ví dụ thay email:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("person@example\\.com"),
        "[REDACTED_EMAIL]"
    )
)
~~~

Snippet sau preprocessing:

~~~json
{
  "id": 42,
  "email": "[REDACTED_EMAIL]",
  "phone": "+84901234567",
  "status": "ACTIVE"
}
~~~

Nếu phone cũng không cần công bố, bổ sung pattern riêng:

~~~java
preprocessResponse(
    replacePattern(
        Pattern.compile("person@example\\.com"),
        "[REDACTED_EMAIL]"
    ),
    replacePattern(
        Pattern.compile("\\+84901234567"),
        "[REDACTED_PHONE]"
    )
)
~~~

replacePattern(...) là thay thế chuỗi theo regex, không parse JSON. Pattern rộng có thể thay nhầm cùng chuỗi ở field khác hoặc làm hỏng JSON. Với payload phức tạp, thay đổi schema thường xuyên hoặc nhiều field cần masking, cân nhắc viết OperationPreprocessor tùy chỉnh để parse JSON, thay đúng key rồi serialize lại. Dù dùng cách nào, hãy kiểm tra snippet cuối.

## 9. Kết hợp request và response preprocessors

Có thể làm sạch hai phía độc lập:

~~~java
mockMvc.perform(post("/api/profile")
        .header("Authorization", "Bearer test-token")
        .header("Cookie", "SESSION=test-session")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "email": "person@example.com",
              "displayName": "An"
            }
            """))
    .andExpect(status().isOk())
    .andDo(document("profile/update",
        preprocessRequest(
            modifyHeaders()
                .remove("Cookie")
                .set("Authorization", "Bearer [REDACTED]"),
            replacePattern(
                Pattern.compile("person@example\\.com"),
                "[REDACTED_EMAIL]"
            )
        ),
        preprocessResponse(
            modifyHeaders()
                .remove("Set-Cookie")
                .remove("X-Internal-Debug"),
            replacePattern(
                Pattern.compile("person@example\\.com"),
                "[REDACTED_EMAIL]"
            )
        )
    ));
~~~

Request preprocessor chỉ làm sạch bản request snippet; response preprocessor chỉ làm sạch bản response snippet. Nếu API echo dữ liệu đầu vào, cần xử lý cả hai phía vì cùng một giá trị có thể xuất hiện trong request và response.

## 10. Bảo vệ error response

Error response là nơi dễ vô tình lộ thông tin nội bộ:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "Database connection failed at db-prod-01.internal:5432",
  "debug": "org.example.OrderRepository.findById(OrderRepository.java:87)",
  "traceId": "req-test-001"
}
~~~

API công khai nên trả thông tin an toàn:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred.",
  "traceId": "req-test-001"
}
~~~

Ưu tiên sửa exception handler để không đưa stack trace, hostname nội bộ hoặc câu lệnh SQL vào response. Preprocessor có thể che một giá trị trong snippet, nhưng không thay thế việc sửa response contract không an toàn.

Nếu traceId là thông tin tham chiếu được phép công bố, giữ lại một giá trị giả ổn định trong snippet. Không đưa trace token hoặc dữ liệu có thể dùng để truy cập hệ thống nội bộ.

### 10.1. Không trả stack trace trong error response công khai

Stack trace hữu ích cho developer khi chẩn đoán lỗi nội bộ, nhưng không phải dữ liệu dành cho API consumer. Nó có thể tiết lộ:

- Tên package, class, method và cấu trúc source code.
- Framework, thư viện và phiên bản đang dùng.
- Tên database, hostname, đường dẫn file hoặc topology nội bộ.
- Truy vấn, tên bảng hoặc chi tiết triển khai xuất hiện trong exception message.
- Giá trị đầu vào hoặc thông tin nhạy cảm được nhúng trong exception.

Một response công khai nên giữ status, error code, message an toàn và correlation ID:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
X-Request-Id: req-test-500

{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred.",
  "traceId": "req-test-500"
}
~~~

Stack trace đầy đủ được ghi ở server-side log có kiểm soát truy cập, gắn với cùng trace/correlation ID. Không gửi stack trace cho client rồi trông chờ REST Docs che nó; response production cũng phải an toàn trước khi đi qua tài liệu hóa.

### 10.2. Kiểm thử rằng stack trace không xuất hiện

MockMvc test có thể xác nhận response không chứa các field debug:

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isInternalServerError())
    .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
    .andExpect(jsonPath("$.stackTrace").doesNotExist())
    .andExpect(jsonPath("$.debug").doesNotExist())
    .andDo(document("orders/internal-error"));
~~~

Nếu API có schema cố định, hãy document các field được phép trả và để REST Docs phát hiện field không được mô tả. Assertion bổ sung giúp diễn đạt rõ yêu cầu không tiết lộ stackTrace/debug.

Không document một stack trace giả như thể đó là error contract. Nếu cần hướng dẫn troubleshooting, mô tả cách cung cấp trace ID và cách liên hệ hỗ trợ.

## 11. Test hành vi bảo mật mà không ghi secret thật

Test nên dùng credential giả được tạo riêng cho test:

~~~java
private static final String TEST_TOKEN = "test-token-not-valid-outside-tests";
~~~

Kiểm tra ứng dụng vẫn yêu cầu xác thực:

~~~java
mockMvc.perform(get("/api/profile")
        .header("Authorization", "Bearer " + TEST_TOKEN))
    .andExpect(status().isOk())
    .andDo(document("profile/get",
        preprocessRequest(
            modifyHeaders().set("Authorization", "Bearer [REDACTED]")
        )
    ));
~~~

Đây là minh họa cho request đã được xác thực thành công. Trong test thực tế, security configuration có thể dùng mock user, test JWT decoder hoặc test authentication provider. Không dùng credential production hoặc copy token từ môi trường thật vào source, log hay fixture.

Nếu mục tiêu là kiểm thử endpoint từ chối request không có token, hãy tạo operation riêng document 401 response. Không dùng preprocessor để làm biến mất bằng chứng rằng endpoint có yêu cầu xác thực.

## 12. Kiểm tra snippet sau khi làm sạch

Sau khi test chạy, đọc cả request và response snippets, không chỉ response-fields:

~~~text
build/generated-snippets/profile/update/
├── http-request.adoc
├── http-response.adoc
├── request-fields.adoc
└── response-fields.adoc
~~~

Checklist kiểm tra:

1. Không còn access token, refresh token, API key hoặc session ID thật.
2. Authorization vẫn thể hiện scheme nếu tài liệu cần mô tả Bearer authentication.
3. Cookie/Set-Cookie đã được xóa hoặc thay theo chủ đích.
4. Email, phone, địa chỉ và payment data trong body dùng fixture giả hoặc placeholder.
5. Không còn internal hostname, IP, stack trace, SQL hay debug header.
6. JSON vẫn hợp lệ và field quan trọng vẫn được giữ lại.
7. Status, error code và header bảo mật cần thiết vẫn được document.

Tìm các chuỗi nhạy cảm đã biết trong thư mục generated-snippets và artifact được đóng gói. Một preprocessor đúng ở operation này không bảo đảm operation khác cũng đã được làm sạch.

## 13. Tổ chức chính sách làm sạch dùng chung

Nếu nhiều test cần cùng quy tắc, tạo helper để tránh mỗi operation xử lý khác nhau:

~~~java
static OperationRequestPreprocessor sanitizeRequest() {
    return preprocessRequest(
        modifyHeaders()
            .remove("Cookie")
            .remove("X-Internal-Debug")
            .set("Authorization", "Bearer [REDACTED]")
    );
}
~~~

Đoạn helper trên chỉ minh họa ý tưởng tổ chức; kiểu trả về và cách ghép preprocessor cần khớp API thực tế của phiên bản Spring REST Docs trong dự án. Có thể tạo helper riêng cho request/response và gọi tại từng document operation.

Chính sách dùng chung nên có danh sách rõ:

- Header luôn xóa.
- Header giữ tên nhưng che giá trị.
- JSON field phải thay bằng placeholder.
- Hostname nội bộ cần chuẩn hóa.
- Field nào được giữ nguyên vì cần thiết cho ví dụ.

Không áp dụng masking toàn cục mù quáng. Một số header như Content-Type, WWW-Authenticate hoặc Retry-After có ý nghĩa hợp đồng và cần được giữ lại.

## 14. Tích hợp Asciidoctor và CI

Asciidoctor include snippet đã được làm sạch:

~~~asciidoc
== Cập nhật hồ sơ

=== HTTP request
include::{snippets}/profile/update/http-request.adoc[]

=== HTTP response
include::{snippets}/profile/update/http-response.adoc[]
~~~

Giả sử plugin Asciidoctor đã được cấu hình:

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

Chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

CI nên thực hiện thêm bước kiểm tra artifact:

- Tìm token fixture, API key pattern và session cookie không được phép xuất hiện.
- Kiểm tra internal hostname và debug information.
- Review snippet thay đổi khi test hoặc error schema đổi.
- Chỉ publish tài liệu sau khi test và bước kiểm tra output đều đạt.

Với Markdown thuần, cú pháp include:: của Asciidoctor không tự được xử lý; cần bước build riêng để nhúng snippet hoặc liên kết tới tệp được sinh.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| Authorization vẫn xuất hiện trong snippet | Chưa gắn request preprocessor vào đúng document operation hoặc pattern không khớp header thực tế. |
| Set-Cookie còn trong response | Chỉ xử lý request; thêm response preprocessor hoặc xóa header ở response. |
| JSON body vẫn có email thật | modifyHeaders không xử lý body; dùng fixture giả hoặc replacePattern/custom JSON preprocessor. |
| Regex thay nhầm nhiều field | Pattern quá rộng; giới hạn theo giá trị/key và kiểm tra snippet sau xử lý. |
| JSON sau masking không parse được | Replacement làm thay ký tự cấu trúc; dùng placeholder hợp lệ và kiểm tra payload. |
| Xóa mất header cần thiết cho client | Phân biệt secret value với header semantics; giữ header và thay giá trị khi cần. |
| Token test bị nhầm là credential thật | Đặt tên fixture rõ ràng, dùng giá trị không hợp lệ ngoài test và ghi chú trong tài liệu. |
| Snippet sạch nhưng artifact vẫn có secret | Kiểm tra test report, log, archive và các output khác; preprocessor chỉ làm sạch operation snippet. |
| Một operation bị bỏ sót masking | Dùng helper/chính sách chung và rà soát toàn bộ operation được document. |

## 16. Bài thực hành

1. Tạo endpoint yêu cầu Bearer authentication và viết test với token giả.
2. Dùng modifyHeaders().remove("Cookie") để xóa Cookie khỏi request snippet.
3. Dùng modifyHeaders().set("Authorization", "Bearer [REDACTED]") để giữ scheme nhưng thay token.
4. Tạo response có Set-Cookie và kiểm tra cách loại header khỏi response snippet.
5. Tạo JSON response chứa email giả; thay giá trị bằng placeholder trong snippet.
6. Tạo error response có debug field và sửa exception handler để không trả thông tin nội bộ.
7. Tạo helper sanitization dùng chung cho request và response.
8. Chạy Gradle/CI, tìm các chuỗi fixture nhạy cảm trong generated-snippets và artifact.

## 17. Ghi nhớ

- Không đưa credential thật hoặc dữ liệu cá nhân thật vào test fixture và tài liệu.
- modifyHeaders() thêm, thay hoặc xóa header khỏi bản operation được document; dùng riêng cho request hoặc response.
- replacePattern() thay content/body khớp regex; pattern phải hẹp để tránh làm hỏng payload.
- Giữ header có ý nghĩa hợp đồng và thay secret value khi client cần biết header đó tồn tại.
- Làm sạch cả request lẫn response vì API có thể echo dữ liệu đầu vào.
- Preprocessor chỉ ảnh hưởng snippet; không làm sạch log, trace, test report hay dữ liệu ở hệ thống khác.
- Kiểm tra generated snippets và artifact trước khi publish tài liệu.

## 18. Tài liệu tham khảo

- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): operation preprocessors và cách biến đổi request/response trước khi document.
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/Preprocessors.html): các factory methods như modifyHeaders và replacePattern.
- [Spring REST Docs — HeadersModifyingOperationPreprocessor](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/preprocess/HeadersModifyingOperationPreprocessor.html): các thao tác set, add, remove và removeMatching cho headers.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): nguyên tắc quản lý secret trong ứng dụng và quy trình phát triển.
