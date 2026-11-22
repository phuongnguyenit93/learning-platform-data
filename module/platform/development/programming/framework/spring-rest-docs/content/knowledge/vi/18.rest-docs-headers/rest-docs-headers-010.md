# Tiền xử lý để che hoặc thay header

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao cần tiền xử lý HTTP request/response trước khi Spring REST Docs ghi snippet.
- Phân biệt che giá trị header, thay giá trị, xóa một header và xóa các header khớp mẫu.
- Dùng preprocessRequest(...) và preprocessResponse(...) để áp dụng preprocessor đúng phía.
- Bảo vệ Authorization, Cookie, API key, session identifier và dữ liệu nội bộ mà vẫn giữ thông tin hữu ích cho tài liệu.
- Nhận biết khi việc xóa header khiến descriptor không còn thấy header cần tài liệu hóa.
- Kiểm tra snippet đầu ra và đưa bước phát hiện bí mật vào quy trình review/build/CI.

## 1. Vì sao cần tiền xử lý header?

Spring REST Docs ghi lại HTTP exchange trong documentation test. Request và response có thể chứa các header cần thiết để hệ thống hoạt động nhưng không nên xuất hiện nguyên giá trị trong tài liệu phát hành.

Ví dụ request xác thực:

```http
GET /api/me HTTP/1.1
Accept: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.production-like-secret
X-Internal-Tenant: tenant-7842
X-Request-Id: 9c0d8d9f-4e5a-4b83-9b01-0a0021f12a18
```

Một số giá trị trong ví dụ có thể:

- Là credential hoặc token có thể cấp quyền truy cập.
- Là định danh nội bộ không dành cho consumer.
- Thay đổi mỗi lần test, khiến snippet khó đọc và khó review.
- Chứa thông tin môi trường, tenant hoặc dữ liệu không nên phát hành.

Nếu lưu nguyên exchange, các giá trị này có thể đi vào http-request.adoc, http-response.adoc hoặc các snippet khác, sau đó được include trong trang tài liệu. **Tiền xử lý giúp tạo một biểu diễn an toàn và ổn định hơn trước khi sinh snippet.**

Tiền xử lý là một lớp bảo vệ của pipeline tài liệu. Nó không thay thế việc dùng fixture giả, bảo vệ secret trong CI, review artifact và quản lý quyền truy cập vào tài liệu.

## 2. REST Docs tiền xử lý ở đâu trong luồng tạo snippet?

Một HTTP documentation test thông thường:

1. Tạo request với header/body cần thiết.
2. Gửi request qua MockMvc, WebTestClient hoặc REST Assured.
3. Kiểm tra status, header và body bằng assertion.
4. Gọi document(...) để ghi lại exchange và sinh snippet.

Khi thêm preprocessor, luồng có thể hình dung:

```mermaid
flowchart TD
    A[HTTP request chứa giá trị test] --> B[Thực thi request]
    B --> C[Nhận response]
    C --> D[Assertion trên hành vi cần xác minh]
    D --> E[Preprocess request và/hoặc response]
    E --> F[REST Docs ghi exchange đã xử lý]
    F --> G[HTTP/header/body snippets]
    G --> H[Asciidoctor hoặc Markdown renderer]
```

Hai hàm gắn preprocessor quan trọng:

| Hàm | Đối tượng được xử lý | Ví dụ |
| --- | --- | --- |
| preprocessRequest(...) | Request được ghi vào snippet | Che Authorization, thay API key hoặc xóa header nội bộ |
| preprocessResponse(...) | Response được ghi vào snippet | Che Set-Cookie, token trả về hoặc header định danh nội bộ |

Chỉ xử lý phía có chứa dữ liệu cần bảo vệ. Nếu secret chỉ có trong request, không cần áp dụng cùng một quy tắc cho response; nếu response chứa cookie/session token, cần xử lý response riêng.

## 3. Các chiến lược xử lý header

Có bốn lựa chọn thường gặp. Hãy chọn dựa trên mục đích của tài liệu.

| Chiến lược | Cách làm | Kết quả |
| --- | --- | --- |
| Thay giá trị | Dùng replacePattern(...) để thay phần nhạy cảm | Header vẫn xuất hiện, giá trị được che hoặc thay bằng placeholder |
| Thay toàn bộ giá trị header | Dùng preprocessor thay header value, nếu API/version cung cấp phù hợp | Giữ tên header, thay giá trị |
| Xóa header cụ thể | Dùng removeHeaders(...) | Header không còn trong exchange được ghi lại |
| Xóa header theo mẫu | Dùng removeMatchingHeaders(...) | Các header có tên khớp pattern bị loại bỏ |

Với tài liệu API, **thay giá trị thường hữu ích hơn xóa** khi người đọc cần biết header phải được gửi. Ví dụ, Authorization có thể vẫn cần xuất hiện trong request mẫu để chỉ rõ scheme Bearer, nhưng token cần được thay bằng giá trị giả.

Xóa header phù hợp khi header hoàn toàn không thuộc tài liệu dành cho consumer, ví dụ X-Internal-Debug hoặc header routing nội bộ. Không nên xóa một header bắt buộc của API nếu trang cần hướng dẫn client gửi nó.

## 4. Thay giá trị nhạy cảm nhưng giữ tên header

### 4.1. Thay token bằng placeholder

Ví dụ với MockMvc, dùng replacePattern(...) trong request preprocessor:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.replacePattern;

import java.util.regex.Pattern;

mockMvc.perform(get("/api/me")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-access-token")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("current-user",
        preprocessRequest(
            replacePattern(
                Pattern.compile("Bearer [^\\s]+"),
                "Bearer <REDACTED>"
            )
        ),
        requestHeaders(
            headerWithName(HttpHeaders.AUTHORIZATION)
                .description("Bearer access token; bắt buộc với endpoint này")
        )
    ));
```

Ở đây:

- Test vẫn gửi credential giả để security layer có thể xử lý.
- Request preprocessor thay chuỗi token trong nội dung được ghi snippet.
- Tên Authorization vẫn tồn tại, nên snippet vẫn có thể thể hiện cách xác thực.
- Descriptor requestHeaders(...) tiếp tục mô tả header.

Biểu thức chính quy cần được kiểm tra với định dạng credential mà dự án dùng. Ví dụ trên chỉ minh họa token dạng Bearer value; API key, Basic credentials, chữ ký hoặc custom scheme cần pattern phù hợp.

Trong source Java, dấu gạch chéo ngược của regex phải được escape trong string literal. Pattern mẫu phía trên minh họa cách khớp phần token sau scheme Bearer; có thể thay bằng pattern khác nếu format credential của dự án khác.

### 4.2. Dùng giá trị giả ngay từ test

Preprocessor không phải lý do để dùng secret production trong test. Hãy ưu tiên:

```java
.header(HttpHeaders.AUTHORIZATION, "Bearer documentation-test-token")
```

Sau đó thay bằng placeholder trong snippet nếu giá trị đó không cần hiển thị:

```text
Authorization: Bearer <REDACTED>
```

Nếu token giả có thể được dùng để truy cập một môi trường test được chia sẻ, vẫn nên xử lý như credential: giới hạn quyền, thời hạn và phạm vi sử dụng. Không đưa token có hiệu lực vào repository chỉ vì nó được gọi là test token.

## 5. Khi nào nên xóa header?

### 5.1. Xóa một header cụ thể

Nếu header chỉ phục vụ nội bộ và không cần xuất hiện trong tài liệu:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

document("orders-get",
    preprocessRequest(
        removeHeaders("X-Internal-Tenant", "X-Debug-Route")
    )
)
```

Các header trên bị loại khỏi request được ghi snippet. Hãy bảo đảm chúng không phải một phần hợp đồng công khai mà consumer cần gửi.

### 5.2. Xóa header theo mẫu

Khi có một nhóm header nội bộ với quy tắc đặt tên rõ ràng, có thể dùng removeMatchingHeaders(...):

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeMatchingHeaders;

document("orders-get",
    preprocessRequest(
        removeMatchingHeaders("X-Internal-.*", "X-Debug-.*")
    )
)
```

Pattern cần đủ hẹp để không vô tình xóa header công khai như X-Request-Id hoặc một header tùy biến mà client cần biết. Trước khi dùng rule theo mẫu, hãy rà soát tập header có thể xuất hiện trong test.

### 5.3. Cẩn trọng với Authorization

Nếu tài liệu endpoint cần nói client phải xác thực, không nên xóa Authorization rồi chỉ ghi “cần token” bằng lời nếu request snippet được kỳ vọng minh họa đầy đủ. Thay giá trị để giữ:

```http
Authorization: Bearer <REDACTED>
```

Nếu endpoint công khai không yêu cầu xác thực hoặc header không thuộc ví dụ, xóa có thể phù hợp. Quyết định phụ thuộc trang tài liệu cần truyền đạt gì.

## 6. Xử lý response header và cookie

Response có thể chứa session cookie:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: session=opaque-session-value; HttpOnly; Secure; Path=/
X-Request-Id: req-9281

{"id":"user-42","name":"Lan"}
```

Nếu trang API không cần giá trị cookie, có thể loại Set-Cookie khỏi response snippet:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

document("login",
    preprocessResponse(removeHeaders("Set-Cookie"))
)
```

Nếu muốn giữ thông tin rằng server phát hành cookie nhưng không lộ giá trị, cần dùng cách thay giá trị phù hợp với nội dung Set-Cookie và kiểm tra kết quả đầu ra. Không gộp nhiều Set-Cookie thành một chuỗi comma-separated; mỗi cookie là một field value riêng và thuộc tính Expires có thể chứa dấu phẩy.

Với X-Request-Id, nếu giá trị thay đổi mỗi lần chạy nhưng tên header quan trọng, có thể thay bằng một placeholder ổn định bằng preprocessor. Điều này giúp snippet dễ review và tránh gây hiểu nhầm rằng ID mẫu luôn cố định.

## 7. Giữ descriptor khi đã tiền xử lý

Một điểm dễ mắc lỗi: preprocessor được áp dụng lên exchange trước khi REST Docs sinh snippet. Vì vậy, nếu bạn **xóa** header trước khi tạo snippet nhưng vẫn khai báo descriptor cho chính header đó, descriptor có thể không còn tìm thấy header tương ứng.

Ví dụ không phù hợp nếu muốn mô tả Authorization:

```java
document("current-user",
    preprocessRequest(removeHeaders("Authorization")),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token")
    )
)
```

Header đã bị xóa khỏi request được xử lý, nhưng descriptor vẫn yêu cầu tài liệu hóa nó. Test có thể thất bại vì header không còn trong exchange được REST Docs quan sát.

Nếu cần giữ header trong bảng, thay giá trị thay vì xóa:

```java
document("current-user",
    preprocessRequest(
        replacePattern(
            Pattern.compile("Bearer [^\\\\s]+"),
            "Bearer <REDACTED>"
        )
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token; bắt buộc")
    )
)
```

Nếu header không cần công bố, có thể xóa và bỏ descriptor tương ứng. Hãy bảo đảm phần prose vẫn mô tả đầy đủ các điều kiện xác thực khác nếu endpoint yêu cầu chúng.

## 8. Preprocessor request và response trong cùng một test

Một request/response có thể cần xử lý cả hai phía:

```java
document("current-user",
    preprocessRequest(
        replacePattern(
            Pattern.compile("Bearer [^\\\\s]+"),
            "Bearer <REDACTED>"
        ),
        removeHeaders("X-Internal-Tenant")
    ),
    preprocessResponse(
        removeHeaders("Set-Cookie"),
        replacePattern(
            Pattern.compile("req-[A-Za-z0-9-]+"),
            "req-<ID>"
        )
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token")
    ),
    responseHeaders(
        headerWithName("X-Request-Id")
            .description("Mã truy vết response")
    )
)
```

Đây là ví dụ minh họa cách kết hợp preprocessor; cần điều chỉnh regex theo định dạng thực và giữ các header có descriptor. Nếu response có X-Request-Id nhưng pattern thay thế khiến toàn bộ giá trị thành req-<ID>, descriptor vẫn mô tả đúng header nhưng snippet sẽ không còn ID cụ thể.

Không nên dùng một regex quá rộng trên toàn exchange nếu nó có thể xóa hoặc thay đổi giá trị JSON, URI, header không liên quan. Ưu tiên rule hẹp và test bằng dữ liệu mô phỏng có thể dự đoán.

## 9. Thay đổi giá trị có cấu trúc và các trường hợp nhạy cảm khác

### 9.1. API key trong custom header

Ví dụ:

```http
X-Api-Key: live-key-value
```

Nếu header là yêu cầu tích hợp, giữ tên và thay giá trị:

```java
preprocessRequest(
    replacePattern(
        Pattern.compile("live-key-value"),
        "<REDACTED>"
    )
)
```

Trong thực tế, dùng fixture giả hoặc pattern bám theo cấu trúc key; không phụ thuộc một chuỗi literal có thể thay đổi mà không ai nhận ra.

### 9.2. Thông tin định danh người dùng hoặc tenant

Header X-Tenant-Id, X-User-Id có thể là một phần contract của API nội bộ hoặc chỉ là metadata do gateway thêm. Hãy quyết định:

- Nếu consumer phải gửi, giữ tên và dùng giá trị giả như tenant-demo.
- Nếu header nội bộ được gateway thêm, thường xóa khỏi snippet dành cho consumer.
- Nếu giá trị cần thiết để giải thích behavior, thay bằng placeholder có ý nghĩa thay vì giá trị thật.

Không coi mọi header có tiền tố X- là bí mật hoặc nội bộ. Cần xác định ownership và người dùng của từng header.

### 9.3. Correlation ID

Correlation ID thường có ích trong tài liệu vận hành, nhưng tài liệu API có thể chỉ cần cho biết response cung cấp một mã truy vết. Có thể thay giá trị ngẫu nhiên bằng một ID cố định mang tính ví dụ:

```http
X-Request-Id: req-example
```

Nếu client cần chuyển ID này cho bộ phận hỗ trợ, hãy nói rõ header được trả trong response và nên lưu lại khi báo lỗi.

## 10. Cách kiểm tra preprocessor thực sự hoạt động

Đừng chỉ nhìn test xanh. Hãy mở các snippet sau khi test chạy và xác nhận:

| Artifact | Điều cần kiểm tra |
| --- | --- |
| http-request.adoc | Không có token/API key thật; header cần công bố vẫn xuất hiện |
| request-headers.adoc | Descriptor vẫn có đủ các header đã chọn |
| http-response.adoc | Cookie/session value và internal ID đã được xử lý |
| response-headers.adoc | Chỉ còn header thuộc phạm vi tài liệu |
| Trang Asciidoctor cuối | Không có dữ liệu nhạy cảm xuất hiện do một include khác |

Một số preprocessor áp dụng lên nhiều snippet được tạo từ cùng operation. Vì vậy, khi thay rule, hãy kiểm tra cả HTTP exchange lẫn bảng header và body snippet nếu test tạo chúng.

### 10.1. Kiểm thử pattern che dữ liệu

Tạo giá trị giả có cấu trúc giống dữ liệu thật nhưng không có quyền truy cập, ví dụ:

```text
Bearer documentation-only-token-123
```

Sau khi chạy test, dùng tìm kiếm trong thư mục generated snippets để xác nhận:

- Chuỗi fixture gốc không xuất hiện.
- Placeholder dự kiến xuất hiện.
- Tên header vẫn xuất hiện nếu cần công bố.
- Các phần không liên quan vẫn giữ nguyên.

Đây là kiểm tra artifact an toàn và có thể tự động hóa trong CI. Không đưa secret thật vào đầu vào của test chỉ để chứng minh regex có che được hay không.

## 11. Build và CI

Tiền xử lý là một phần của thao tác sinh snippet, do đó thường được kiểm tra khi documentation test chạy:

```mermaid
flowchart TD
    A[HTTP test dùng fixture giả] --> B[Assertion hành vi]
    B --> C[Request/response preprocessors]
    C --> D[Sinh snippet]
    D --> E[Kiểm tra artifact không có secret]
    E --> F[Asciidoctor hoặc Markdown]
    F --> G[Review và lưu tài liệu]
```

Một pipeline có thể thực hiện:

1. Chạy test documentation trên dữ liệu giả.
2. Sinh snippets vào thư mục output sạch.
3. Tìm các chuỗi fixture bí mật đã biết để bảo đảm chúng không xuất hiện trong artifact.
4. Kiểm tra các header công khai cần thiết vẫn hiện diện.
5. Render Asciidoctor/Markdown.
6. Review HTML/PDF và các snippet trước khi phát hành.

Không nên chỉ quét http-request.adoc; secret có thể xuất hiện trong http-response.adoc, curl-request.adoc, body snippet, log test hoặc file debug khác. Phạm vi kiểm tra nên bao gồm toàn bộ artifact được phát hành.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Descriptor Authorization không tìm thấy header | removeHeaders("Authorization") đã xóa header trước khi tạo snippet | Dùng thay giá trị hoặc bỏ descriptor nếu header không công bố |
| Token vẫn xuất hiện trong snippet | Regex không khớp format thật hoặc preprocessor gắn sai phía | Kiểm tra request/response thực, pattern và vị trí áp dụng |
| Response snippet còn session cookie | Chỉ preprocess request mà không preprocess response | Xử lý response bằng preprocessResponse(...) |
| Header nội bộ vẫn có trong output | Danh sách remove không bao phủ header đó | Rà soát header thực tế; thêm rule hẹp và test |
| Header công khai bị xóa nhầm | Pattern xóa quá rộng | Thu hẹp pattern, kiểm tra header contract |
| Tên header mất khỏi HTTP request | Dùng remove thay vì replace | Thay value bằng placeholder khi vẫn cần minh họa header |
| Set-Cookie bị hỏng sau khi xử lý | Gộp cookie hoặc parse dấu phẩy sai | Giữ từng field value riêng; xử lý cookie theo cú pháp riêng |
| HTML sạch nhưng snippet thô vẫn chứa secret | Chỉ kiểm tra output render, bỏ qua thư mục snippet | Quét toàn bộ artifact trước khi đóng gói |

## 13. Checklist tiền xử lý header

- [ ] Xác định header chứa secret, dữ liệu cá nhân hoặc metadata nội bộ.
- [ ] Xác định header có thuộc hợp đồng client cần biết hay không.
- [ ] Dùng replace/mask khi cần giữ tên header; chỉ remove khi header không nên xuất hiện.
- [ ] Chọn đúng preprocessRequest(...) hoặc preprocessResponse(...).
- [ ] Đảm bảo descriptor không trỏ đến header đã bị xóa.
- [ ] Dùng fixture giả ngay từ đầu; không đưa secret production vào test.
- [ ] Kiểm tra cả HTTP snippet, header snippet, body snippet và artifact cuối.
- [ ] Xác nhận giá trị bị che không thể khôi phục từ log hoặc file phụ.
- [ ] Tự động hóa tìm kiếm fixture gốc/secret marker trong CI.

## 14. Bài tập thực hành

Endpoint GET /api/profile có:

- Request header Authorization: Bearer ..., bắt buộc để xác thực.
- Request header X-Internal-Tenant, được gateway thêm và không thuộc contract public.
- Response header Set-Cookie, chứa session cookie.
- Response header X-Request-Id, client có thể dùng để yêu cầu hỗ trợ.

Hãy thực hiện:

1. Viết test dùng token giả và xác minh status/body của profile.
2. Dùng request preprocessor thay giá trị Authorization bằng Bearer <REDACTED> nhưng giữ tên header.
3. Xóa X-Internal-Tenant khỏi request snippet nếu tài liệu dành cho consumer không cần nó.
4. Dùng response preprocessor xử lý Set-Cookie; quyết định giữ dạng placeholder hay loại hẳn dựa trên yêu cầu trang tài liệu.
5. Thay X-Request-Id ngẫu nhiên bằng giá trị ví dụ ổn định và giữ header trong response snippet.
6. Include request/response/header snippets vào Asciidoctor.
7. Tạo bước CI tìm các fixture gốc trong toàn bộ output và làm build thất bại nếu chúng còn xuất hiện.

**Câu hỏi tự kiểm tra:** Nếu đã dùng removeHeaders("Authorization"), có thể vẫn khai báo headerWithName("Authorization") trong requestHeaders(...) để bảng tài liệu nói client phải gửi token không? Không nên. Preprocessor đã loại header khỏi exchange dùng để sinh snippet nên descriptor có thể không khớp. Khi muốn vừa giữ header vừa che giá trị, hãy thay giá trị; nếu xóa vì không công bố, bỏ descriptor tương ứng và mô tả security ở phần thích hợp.

## Kết luận

Tiền xử lý giúp Spring REST Docs tạo snippet an toàn và ổn định từ HTTP exchange. Dùng preprocessRequest(...) cho request và preprocessResponse(...) cho response; thay giá trị khi cần giữ tên header trong tài liệu, xóa header khi nó không thuộc phạm vi consumer. Cần đặc biệt cẩn trọng với Authorization, API key, Cookie, Set-Cookie và định danh nội bộ. Vì preprocessor thay đổi exchange mà REST Docs quan sát, việc xóa một header có thể làm descriptor của header đó không còn khớp. Hãy dùng fixture giả, kiểm tra snippet thô và trang render, rồi tự động quét artifact trên CI trước khi phát hành.
