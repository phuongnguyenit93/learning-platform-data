# Ẩn định danh người dùng và thông tin môi trường

## 1. Vì sao phải ẩn dữ liệu trong snippet?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Bảo mật**, tài liệu API được sinh từ request và response thực tế của các bài kiểm thử HTTP. Dữ liệu test đôi khi chứa user ID, email, số điện thoại, địa chỉ IP, tên host nội bộ, tên database, token giả lập hoặc URL của môi trường phát triển. Nếu snippet được publish, các giá trị này có thể tiết lộ cấu trúc nội bộ hoặc tạo thói quen đưa dữ liệu cá nhân vào tài liệu.

Spring REST Docs cung cấp operation preprocessors để biến đổi request/response trước khi ghi snippet. Có thể thay định danh bằng placeholder ổn định, loại bỏ header nội bộ hoặc chuẩn hóa URI về host mẫu. Nhờ vậy, ví dụ vẫn dễ hiểu và có thể kiểm chứng mà không mang theo thông tin môi trường thật.

Điều quan trọng: preprocessor chỉ biến đổi bản ghi tài liệu của Spring REST Docs. Nó không mã hóa dữ liệu, không thay đổi request gửi tới controller và không bảo vệ log ứng dụng, APM, database hay traffic runtime. Dữ liệu nhạy cảm vẫn cần được xử lý an toàn ở các lớp khác.

Sau bài học, bạn có thể:

- Nhận diện định danh người dùng và dấu vết môi trường trong request/response.
- Dùng replacePattern để thay dữ liệu nhạy cảm bằng placeholder.
- Dùng removeHeaders/modifyHeaders để loại bỏ hoặc chuẩn hóa header.
- Dùng modifyUris để chuẩn hóa scheme, host và port.
- Áp dụng preprocessor riêng theo operation.
- Kiểm tra snippet đã được mask và không chứa giá trị gốc.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**.

## 2. Phân loại dữ liệu cần ẩn

Trước khi viết preprocessor, xác định dữ liệu nào là định danh cá nhân, dữ liệu bí mật hoặc thông tin môi trường.

| Nhóm | Ví dụ | Cách xử lý trong snippet |
| --- | --- | --- |
| User identifier | userId, customerId, account number | Thay bằng placeholder như USER_ID |
| Thông tin liên hệ | email, phone, địa chỉ | Dùng dữ liệu mẫu không thuộc người thật hoặc thay bằng placeholder |
| Định danh phiên | session ID, correlation ID | Thay bằng giá trị mẫu ổn định hoặc bỏ nếu không cần |
| Credential | Authorization, Cookie, API key | Xóa header hoặc thay bằng token giả rõ ràng |
| Môi trường nội bộ | hostname, private IP, port, internal DNS | Chuẩn hóa URI hoặc thay bằng host mẫu |
| Hạ tầng | tên cluster, pod, database, schema | Loại khỏi snippet nếu không thuộc contract công khai |
| Dữ liệu nghiệp vụ nhạy cảm | số dư, giao dịch, hồ sơ khách hàng | Dùng fixture giả, không sao chép dữ liệu production |

Không phải mọi ID đều là bí mật. Tuy nhiên, ID thật có thể liên kết tới dữ liệu cá nhân hoặc tiết lộ quy mô, thứ tự tạo dữ liệu và cấu trúc hệ thống. Dùng ID giả ổn định trong fixture thường là lựa chọn tốt nhất; preprocessor là lớp bảo vệ bổ sung cho snippet.

## 3. Preprocessor hoạt động ở đâu?

Spring REST Docs cho phép cấu hình preprocessor ngay trên operation:

```java
document("users-find",
    preprocessRequest(...),
    preprocessResponse(...),
    ...
)
```

Request preprocessor biến đổi bản request được ghi vào snippet; response preprocessor biến đổi bản response được ghi vào snippet. Controller vẫn nhận request và client test vẫn nhận response thực tế.

Luồng tổng quát:

```text
MockMvc request
     |
     v
Application / Controller
     |
     v
HTTP response
     |
     +----> Test assertions dùng dữ liệu thực tế
     |
     v
Spring REST Docs operation
     |
     +----> preprocessRequest  -> request snippets
     |
     +----> preprocessResponse -> response snippets
                                  |
                                  v
                           Generated snippets
```

Vì assertions thường chạy trên response gốc trước khi document handler ghi snippet, test có thể kiểm tra hành vi thật và đồng thời xuất bản bản đã mask. Tuy nhiên, nên có assertion trực tiếp trên artifact/snippet sau build để chứng minh giá trị nhạy cảm đã bị loại.

## 4. Thay user ID bằng replacePattern

### 4.1. Mask định danh trong payload

Giả sử response có dữ liệu:

```json
{
  "userId": "usr-849201",
  "email": "alice.private@example.test",
  "displayName": "Alice",
  "status": "ACTIVE"
}
```

Tạo response preprocessor:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

preprocessResponse(
    replacePattern(
        Pattern.compile("usr-[0-9]+"),
        "USER_ID"
    ),
    replacePattern(
        Pattern.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}"),
        "user@example.test"
    )
)
```

Snippet response body sẽ chứa placeholder thay vì user ID và email fixture:

```json
{
  "userId": "USER_ID",
  "email": "user@example.test",
  "displayName": "Alice",
  "status": "ACTIVE"
}
```

Biểu thức regular expression phải phù hợp định dạng dữ liệu thực tế. Tránh regex quá rộng có thể thay nhầm nội dung hợp lệ hoặc quá hẹp khiến một biến thể định danh lọt qua. Với dữ liệu phức tạp, cân nhắc dùng fixture giả từ đầu và preprocessor chỉ làm lớp bảo vệ bổ sung.

### 4.2. Mask identifier trong request và response

Nếu user ID xuất hiện ở cả URL request và response payload, có thể áp dụng cho cả hai phía:

```java
document("users-find",
    preprocessRequest(
        replacePattern(
            Pattern.compile("usr-[0-9]+"),
            "USER_ID"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("usr-[0-9]+"),
            "USER_ID"
        )
    )
)
```

Kiểm tra snippet request line và response body sau khi build để xác nhận pattern thực sự bao phủ vị trí xuất hiện. Nếu định danh nằm trong URI được xử lý riêng bởi URI modifier, dùng modifier phù hợp và không giả định một regex body sẽ chuẩn hóa mọi thành phần URL.

## 5. Ẩn header nhạy cảm và thông tin môi trường

### 5.1. Xóa header không thuộc contract công khai

Các header như Authorization, Cookie, Set-Cookie hoặc header debug nội bộ thường không cần xuất hiện trong tài liệu công khai:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

preprocessRequest(
    removeHeaders("Authorization", "Cookie", "X-Internal-Debug")
),
preprocessResponse(
    removeHeaders("Set-Cookie", "X-Internal-Node", "Server")
)
```

Chỉ xóa header khỏi snippet khi chúng không phải phần contract mà người tích hợp cần biết. Nếu API yêu cầu client gửi Authorization, tài liệu vẫn nên giải thích cơ chế xác thực ở phần bảo mật riêng; không cần đưa token thật vào ví dụ.

### 5.2. Thay giá trị header bằng placeholder

Nếu header cần được tài liệu hóa nhưng giá trị thật có thể chứa thông tin môi trường, dùng modifyHeaders:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyHeaders;

preprocessResponse(
    modifyHeaders()
        .set("X-Request-Id", "REQUEST_ID")
        .set("X-Region", "example-region")
)
```

Ví dụ trên giữ tên header và thay giá trị. Dùng cách này khi header thuộc contract công khai nhưng giá trị trong test không nên được phát hành.

### 5.3. Chuẩn hóa URI host và port

Request/response snippet có thể chứa host môi trường:

```text
https://catalog-staging.internal.example:8443/api/products/42
```

Dùng modifyUris để chuẩn hóa scheme, host và port:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.modifyUris;

preprocessRequest(
    modifyUris()
        .scheme("https")
        .host("api.example.test")
        .removePort()
)
```

URI trong snippet trở thành host mẫu phù hợp với tài liệu công khai. Chỉ thay host nếu đây là URI minh họa; nếu API contract yêu cầu host do tenant hoặc client cấu hình, hãy giải thích base URL riêng thay vì làm sai semantics của endpoint.

## 6. Tổ chức một bộ preprocessor dùng chung

Có thể tạo helper trong test source:

```java
package com.example.catalog.docs;

import java.util.regex.Pattern;

import static org.springframework.restdocs.operation.preprocess.Preprocessors.*;

public final class DocumentationPreprocessors {

    private DocumentationPreprocessors() {
    }

    public static OperationRequestPreprocessor safeRequest() {
        return preprocessRequest(
            removeHeaders("Authorization", "Cookie", "X-Internal-Debug"),
            replacePattern(
                Pattern.compile("usr-[0-9]+"),
                "USER_ID"
            ),
            modifyUris()
                .scheme("https")
                .host("api.example.test")
                .removePort()
        );
    }

    public static OperationResponsePreprocessor safeResponse() {
        return preprocessResponse(
            removeHeaders("Set-Cookie", "X-Internal-Node", "Server"),
            modifyHeaders()
                .set("X-Request-Id", "REQUEST_ID"),
            replacePattern(
                Pattern.compile("usr-[0-9]+"),
                "USER_ID"
            ),
            replacePattern(
                Pattern.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}"),
                "user@example.test"
            )
        );
    }
}
```

Sau đó dùng trong operation:

```java
document("users-find",
    DocumentationPreprocessors.safeRequest(),
    DocumentationPreprocessors.safeResponse(),
    responseFields(
        fieldWithPath("userId").description("Mã người dùng"),
        fieldWithPath("email").description("Email liên hệ"),
        fieldWithPath("status").description("Trạng thái tài khoản")
    )
)
```

Factory này phù hợp với tài liệu công khai có quy tắc mask giống nhau. Với operation có contract khác, tạo preprocessor riêng hoặc bổ sung bước xử lý có tên rõ; không áp dụng một bộ mask rộng cho mọi API nếu nó làm thay đổi dữ liệu ví dụ cần thiết.

## 7. Kiểm tra snippet đã được mask

Không chỉ kiểm tra test thành công. Cần xác nhận artifact sinh ra không còn giá trị nhạy cảm.

### 7.1. Assertion trên response gốc

MockMvc test có thể xác nhận ứng dụng trả đúng dữ liệu fixture:

```java
mockMvc.perform(get("/api/users/{id}", "usr-849201")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.userId").value("usr-849201"))
    .andDo(document("users-find",
        DocumentationPreprocessors.safeRequest(),
        DocumentationPreprocessors.safeResponse(),
        responseFields(
            fieldWithPath("userId").description("Mã người dùng"),
            fieldWithPath("email").description("Email liên hệ"),
            fieldWithPath("status").description("Trạng thái tài khoản")
        )
    ));
```

Assertion kiểm tra response gốc vẫn đúng với fixture. Preprocessor áp dụng khi ghi snippet.

### 7.2. Kiểm tra file snippet sau test

Sau khi chạy test, kiểm tra các file trong build/generated-snippets/users-find:

```text
http-request.adoc
http-response.adoc
response-body.adoc
response-fields.adoc
```

Tìm các giá trị gốc cần mask:

```powershell
$snippetRoot = "build/generated-snippets/users-find"
$generatedText = Get-Content -Raw "$snippetRoot/http-request.adoc"
$generatedText += Get-Content -Raw "$snippetRoot/http-response.adoc"
$generatedText += Get-Content -Raw "$snippetRoot/response-body.adoc"

if ($generatedText.Contains("usr-849201")) {
    throw "User identifier leaked into generated snippets"
}
if ($generatedText.Contains("alice.private@example.test")) {
    throw "Email leaked into generated snippets"
}
```

Có thể đưa kiểm tra này thành task trong CI để build thất bại nếu giá trị cấm xuất hiện trong artifact. Với nhiều operation, tạo danh sách pattern/giá trị cần cấm theo fixture và quét toàn bộ thư mục generated snippets.

## 8. Tài liệu hóa mà không làm sai contract

Masking phải giữ nguyên ý nghĩa của ví dụ:

- Thay user ID bằng placeholder có định dạng rõ, ví dụ USER_ID.
- Giữ kiểu dữ liệu JSON; nếu ID là string, placeholder cũng phải là string.
- Không thay tên field, relation hoặc header thuộc contract công khai.
- Không xóa Content-Type hoặc status header cần thiết để hiểu response.
- Chuẩn hóa host môi trường nhưng không thay đổi path hoặc query có ý nghĩa.
- Giữ ví dụ đủ thực tế để client hiểu cách gọi API.

Nếu cần mô tả một header xác thực, hãy dùng giá trị giả như Bearer <escape>EXAMPLE_TOKEN</escape> và ghi rõ đó là placeholder. Không dùng token được sao chép từ môi trường chạy.

Với ID xuất hiện trong nhiều vị trí, dùng placeholder nhất quán trong cùng operation để người đọc nhận ra chúng tham chiếu cùng một resource. Nếu thay mọi ID bằng cùng một giá trị chung, hãy bảo đảm ví dụ không tạo ra quan hệ sai hoặc gây nhầm lẫn giữa các resource khác nhau.

## 9. Giới hạn bảo vệ và các lớp dữ liệu khác

Operation preprocessor chỉ tác động nội dung Spring REST Docs ghi vào snippet. Nó không tự động:

- Mask log của ứng dụng hoặc log của test framework.
- Thay đổi dữ liệu trong database hoặc message broker.
- Ẩn request/response khỏi proxy, tracing agent hoặc APM.
- Xóa dữ liệu khỏi report test, file dump hoặc artifact khác.
- Thay thế quản lý secret, kiểm soát truy cập hoặc chính sách dữ liệu test.

Vì vậy, ưu tiên dữ liệu giả ngay từ fixture. Không nạp dữ liệu production vào test chỉ vì có preprocessor. Giới hạn quyền truy cập artifact CI, kiểm tra log và chỉ publish các snippet đã được xác minh.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| User ID vẫn xuất hiện trong snippet | Regex không khớp định dạng hoặc chỉ áp dụng một phía. | Kiểm tra request và response riêng; mở rộng pattern có kiểm soát. |
| Email bị thay một phần | Regex chưa bao phủ domain hoặc ký tự hợp lệ. | Dùng pattern phù hợp dữ liệu và kiểm tra artifact sau test. |
| Header Authorization vẫn được ghi | Chưa gắn removeHeaders vào đúng request preprocessor. | Kiểm tra operation gọi safeRequest(). |
| Host staging xuất hiện trong HTTP snippet | Chưa chuẩn hóa URI hoặc chỉ sửa response. | Áp dụng modifyUris cho phía có chứa URI. |
| Header cần tài liệu bị xóa | removeHeaders quá rộng. | Chỉ xóa header bí mật/nội bộ; dùng modifyHeaders để thay giá trị cần giữ. |
| Snippet sai ví dụ nghiệp vụ | Regex thay nhầm ID hoặc path có ý nghĩa. | Thu hẹp pattern và kiểm tra request/response fixture. |
| Test pass nhưng artifact vẫn lộ dữ liệu | Chỉ assertion response gốc, không quét snippet. | Thêm artifact check vào CI. |
| Nghĩ preprocessor đã bảo vệ runtime | Nhầm thao tác sinh tài liệu với bảo vệ dữ liệu ứng dụng. | Mask fixture, log và tracing ở đúng lớp riêng. |

## 11. Bài thực hành

Tạo endpoint GET /api/users/{userId} trả user ID, email và status. Test fixture dùng user ID giả có pattern usr-849201 và email alice.private@example.test. Request/response test có thể chứa header xác thực giả và header môi trường nội bộ.

Thực hiện:

1. Tạo DocumentationPreprocessors.safeRequest() để xóa Authorization/Cookie, thay user ID và chuẩn hóa host.
2. Tạo safeResponse() để xóa Set-Cookie/header nội bộ, thay request ID và email.
3. Viết MockMvc test xác nhận response gốc đúng fixture rồi gắn preprocessors vào document(...).
4. Chạy test và đọc http-request.adoc, http-response.adoc, response-body.adoc.
5. Thêm kiểm tra tự động bảo đảm user ID và email gốc không xuất hiện trong snippet.
6. Xác nhận placeholder vẫn giữ kiểu dữ liệu và ví dụ còn dễ hiểu.
7. Include snippet đã mask vào Asciidoctor và chạy clean test asciidoctor.

**Tiêu chí hoàn thành:** nhận diện được dữ liệu định danh và môi trường; dùng replacePattern, removeHeaders, modifyHeaders và modifyUris đúng mục đích; kiểm tra artifact đã mask; hiểu preprocessor chỉ bảo vệ snippet, không thay thế bảo mật runtime.

## 12. Tài liệu tham khảo

- [Spring REST Docs — Preprocessing](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/preprocessors.html)
- [Spring REST Docs — OperationPreprocessor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/OperationPreprocessor.html)
- [Spring REST Docs — Preprocessors API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/operation/preprocess/Preprocessors.html)
- [OWASP Cheat Sheet Series — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Cheat Sheet Series — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
