# Replacing patterns trong URI hoặc body

Request và response được ghi nhận trong Spring REST Docs có thể chứa những giá trị không ổn định hoặc không nên công bố: hostname nội bộ, random port, callback URL, token nằm trong query string, request ID, timestamp hoặc dữ liệu fixture. Nếu đưa nguyên các giá trị đó vào snippet, tài liệu có thể khó tái sử dụng, tạo diff liên tục hoặc làm lộ thông tin môi trường. Operation preprocessors cho phép chuẩn hóa bản message được dùng để sinh snippet; `replacePattern(...)` hữu ích khi cần thay một mẫu văn bản bằng giá trị ổn định.

Cần chọn đúng processor theo vị trí dữ liệu. `replacePattern(...)` xử lý nội dung message phù hợp với pattern; `modifyUris()` dành cho chuẩn hóa scheme, host và port của request URI; `modifyHeaders()` phù hợp khi thay một header cụ thể. Path và query parameter có cấu trúc, encoding và ý nghĩa riêng. Không dùng regex quá rộng trên toàn message vì có thể thay nhầm ID nghiệp vụ, API version hoặc cú pháp JSON.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `replacePattern(...)` hoạt động trong bước preprocessing trước khi sinh snippet.
2. Phân biệt thay thế nội dung body với chuẩn hóa request URI và response header.
3. Viết regex có phạm vi rõ để thay token, timestamp, hostname hoặc dữ liệu fixture.
4. Giữ nguyên path, query parameter và cấu trúc body không thuộc mục tiêu thay thế.
5. Xử lý URL encoding, ký tự đặc biệt và trường hợp pattern không khớp.
6. Kết hợp preprocessor với assertion và descriptor mà không che lỗi API.
7. Kiểm tra raw snippet và artifact đã render trước khi publish.

## 2. Khi nào cần replacing patterns?

Một request/response được ghi nhận có thể chứa giá trị khó dùng trong tài liệu:

```text
GET http://localhost:53128/api/orders/42?traceId=run-98127 HTTP/1.1
Authorization: Bearer docs-test-token
Accept: application/json
```

Response có thể chứa:

```json
{
  "id": 42,
  "createdAt": "2026-11-17T08:12:42.381Z",
  "callbackUrl": "https://node-17.internal:8443/callback?token=temporary-secret"
}
```

Tài liệu có thể cần ví dụ ổn định:

```json
{
  "id": 42,
  "createdAt": "2026-01-01T00:00:00.000Z",
  "callbackUrl": "https://api.example.test/callback?token=<callback-token>"
}
```

Các lý do thường gặp: host/port môi trường test khác domain công bố; timestamp/request ID ngẫu nhiên làm snippet thay đổi; query string có token hoặc authorization code; body có dữ liệu fixture riêng tư; URL callback mang hostname nội bộ. Không phải mọi giá trị động đều nên thay. Nếu timestamp format, ID format, ETag hoặc query parameter là nội dung cần dạy, hãy giữ semantics và chỉ thay dữ liệu cụ thể nếu cần.

## 3. replacePattern(...) xử lý nội dung message

Spring REST Docs cung cấp API `replacePattern(Pattern, String)` trong nhóm operation preprocessors. Có thể kết hợp với `preprocessRequest(...)` hoặc `preprocessResponse(...)` tùy nội dung cần xử lý.

Ví dụ thay trace ID trong response content:

```java
.andDo(document("orders-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("traceId=[A-Za-z0-9-]+"),
            "traceId=docs-trace-id"
        )
    )
));
```

Processor thay phần content khớp pattern trong bản response dùng để sinh snippet. Nó không sửa response controller đã trả cho test. Assertion vẫn nhìn thấy message gốc.

### 3.1. Request body và response body

Có thể đặt processor ở hai phía:

```java
.andDo(document("orders-create",
    preprocessRequest(
        replacePattern(
            Pattern.compile("customer-\\d+"),
            "customer-demo"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("trace-[A-Za-z0-9-]+"),
            "trace-docs"
        )
    )
));
```

Request processor xử lý content của request được ghi nhận; response processor xử lý content của response được ghi nhận. Chỉ áp dụng khi biết giá trị nằm trong content và thay thế không làm sai cấu trúc payload.

### 3.2. Kết hợp với prettyPrint()

Nếu cần vừa thay giá trị vừa định dạng JSON, có thể kết hợp processor trong cùng nhánh. Thứ tự có thể ảnh hưởng output, vì vậy phải chạy test và kiểm tra snippet sau xử lý:

```java
.andDo(document("profile-get",
    preprocessResponse(
        replacePattern(
            Pattern.compile("run-[0-9]+"),
            "docs-run"
        ),
        prettyPrint()
    )
));
```

Nếu pattern khiến JSON không còn hợp lệ hoặc thứ tự biến đổi không cho output dự kiến, sửa fixture/pattern hoặc thay đổi thứ tự processor. Đừng mặc định mọi tổ hợp đều độc lập.

## 4. Regex có phạm vi hẹp

Giả sử body có:

```json
{
  "requestId": "req-783ad9",
  "status": "ACCEPTED"
}
```

Có thể thay chuỗi có format tương ứng:

```java
replacePattern(
    Pattern.compile("req-[A-Za-z0-9-]+"),
    "req-docs"
)
```

Cách này sẽ thay mọi chuỗi trong content có dạng req-..., không riêng field requestId. Nếu nhiều field cùng format, regex có thể thay nhầm. Với body phức tạp, fixture cố định hoặc custom processor hiểu cấu trúc JSON có thể an toàn hơn.

### 4.1. Tránh regex quá rộng

Không dùng quy tắc chung như thay mọi chuỗi chữ/số hoặc mọi URI bằng placeholder. Pattern quá rộng có thể làm mất resource ID, enum nghiệp vụ, API version như /v1/, query parameter cần mô tả hoặc giá trị cần giữ để minh họa schema.

Trước khi dùng regex, viết ra ít nhất một input phải thay và một input gần giống phải được giữ nguyên. Chạy test cho cả hai để kiểm chứng ranh giới.

### 4.2. Capturing group và replacement

Khi cần giữ lại một phần chuỗi, dùng capturing group. Ví dụ giữ key token và thay riêng value:

```java
replacePattern(
    Pattern.compile("([?&]token=)[^&\\s]+"),
    "$1<access-token>"
)
```

Group thứ nhất giữ dấu ? hoặc & và tên parameter; phần value được thay bằng placeholder. Kiểm tra với nhiều query parameter, token URL-encoded và trường hợp token là parameter cuối cùng. Java replacement string có quy tắc riêng cho $ và dấu gạch chéo ngược; cần escape phù hợp nếu replacement chứa các ký tự này.

## 5. URI không giống body: chọn processor đúng

Request URI gồm scheme, authority/host, port, path, query và fragment. `replacePattern(...)` không phải URI parser. Để chuẩn hóa các thành phần request URI phổ biến, dùng processor chuyên biệt:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build()
    )
));
```

Cấu hình này dành cho scheme, host và port của request URI được ghi nhận. Nó không tự định nghĩa quy tắc thay path hoặc query parameter.

### 5.1. Thay host/port

Nếu test dùng localhost và random port nhưng tài liệu cần domain canonical, `modifyUris()` rõ ràng hơn regex trên toàn message. Path và query cần được giữ lại:

```http
GET https://api.example.test/v1/orders/42?expand=items HTTP/1.1
```

Path /v1/orders/42 và query expand=items vẫn là phần contract.

### 5.2. Thay path hoặc query parameter

Trước khi thay, xác định parameter nào nhạy cảm hoặc chỉ là dữ liệu test; có cần giữ key và vị trí trong tài liệu không; value có được URL-encode không; có nhiều parameter trùng tên không; dấu &, =, ?, # có thể xuất hiện bên trong encoded value không.

Nếu chỉ thay token query, regex phải giới hạn tới value của key đó. Nếu cần thay nhiều thành phần URI hoặc parse query phức tạp, dùng URI-aware custom request preprocessor theo API version hoặc tạo fixture URL an toàn ngay từ đầu. Không thay toàn bộ path nếu path là contract.

## 6. Link trong response header

`Location` hoặc `Link` có thể chứa host nội bộ, callback URL hoặc token. Với một header xác định, thường dễ kiểm soát nếu dùng `modifyHeaders()`:

```java
.andDo(document("orders-create",
    preprocessResponse(
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/api/orders/42"
            )
            .build()
    )
));
```

Ví dụ dùng giá trị hoàn chỉnh đã biết. Nếu path có ID động, dùng fixture xác định hoặc custom response processor có hiểu biết URI; tránh hard-code ID mẫu khiến snippet không khớp response test.

Header Link có thể chứa nhiều URI cùng tham số rel. Regex đơn giản có thể làm hỏng dấu ngoặc góc hoặc quan hệ next/prev. Với cấu trúc này, dùng fixture cố định hoặc parser phù hợp rồi kiểm tra header sau xử lý.

## 7. Thay URL hoặc token trong JSON/XML/text body

### 7.1. JSON body

Ví dụ response:

```json
{
  "verificationUrl": "https://auth.internal/verify?token=secret-value",
  "status": "PENDING"
}
```

Có thể thay hostname/token bằng pattern hẹp, nhưng cần xác nhận kết quả vẫn là JSON hợp lệ. Nếu kiểm soát được fixture, an toàn hơn là tạo response test bằng domain và token giả ngay từ đầu.

Với JSON phức tạp, custom processor parse JSON, thay đúng field rồi serialize lại thường đáng tin cậy hơn regex trên toàn chuỗi. Phải giữ đúng kiểu dữ liệu, escaping, array và nested fields.

### 7.2. XML body

Token có thể xuất hiện trong text node hoặc attribute:

```xml
<verification>
    <url>https://auth.internal/verify?token=secret-value</url>
</verification>
```

Regex có thể thay chuỗi nhưng không hiểu namespace, entity hoặc CDATA. Với XML phức tạp, dùng fixture an toàn hoặc processor dựa trên XML parser để thay đúng node/attribute.

### 7.3. Text body

Text thuần phù hợp hơn với `replacePattern(...)` khi format đơn giản:

```text
Request req-8912 failed validation
```

Có thể chuẩn hóa thành:

```text
Request req-docs failed validation
```

Vẫn phải giữ error code, mã giao dịch hoặc định danh public mà người đọc cần hiểu.

## 8. Kết hợp request và response preprocessing

Một operation có thể xử lý cả hai chiều:

```java
.andDo(document("verification-create",
    preprocessRequest(
        modifyUris()
            .scheme("https")
            .host("api.example.test")
            .removePort()
            .build(),
        replacePattern(
            Pattern.compile("trace-[A-Za-z0-9-]+"),
            "trace-docs"
        )
    ),
    preprocessResponse(
        replacePattern(
            Pattern.compile("([?&]token=)[^&\\s]+"),
            "$1<verification-token>"
        ),
        modifyHeaders()
            .set(
                "Location",
                "https://api.example.test/verification/42"
            )
            .build()
    )
));
```

Trong ví dụ, request URI được chuẩn hóa bằng modifyUris; request content được xử lý bằng pattern nếu có chuỗi tương ứng; response content thay token; response Location được thay trực tiếp. Cấu hình thực tế phải đặt processor ở đúng phía và xác nhận đúng thành phần bị thay.

## 9. Assertions và descriptor phải dựa trên contract thật

Preprocessor chỉ biến đổi bản message dùng tạo snippet. Test assertions cần xác nhận response gốc:

```java
mockMvc.perform(get("/api/verification/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("Location"))
    .andExpect(jsonPath("$.status").value("PENDING"))
    .andDo(document("verification-get",
        preprocessResponse(
            replacePattern(
                Pattern.compile("https://[^/]+/verify"),
                "https://api.example.test/verify"
            )
        ),
        responseFields(
            fieldWithPath("status")
                .description("Trạng thái xác minh")
        )
    ));
```

Ví dụ minh họa assertion xác minh status thật, còn preprocessor thay URL trong bản ghi. Nếu Location hoặc verification URL có path sai, test phải phát hiện; không viết regex sửa cả path sai thành path mong đợi.

Descriptor như requestParameters, responseFields, requestHeaders hoặc responseHeaders mô tả hợp đồng. Đừng để descriptor mô tả URL khác với raw snippet hoặc phần diễn giải viết tay.

## 10. Đọc lại và kiểm tra snippet sau thay thế

Sau khi test chạy, kiểm tra toàn bộ file của identifier, không chỉ một snippet:

```text
target/generated-snippets/verification-create/
├── http-request.adoc
├── http-response.adoc
├── curl-request.adoc
├── httpie-request.adoc
├── request-headers.adoc
├── response-headers.adoc
└── response-fields.adoc
```

Danh sách thực tế phụ thuộc descriptor. Kiểm tra host/port nội bộ đã thay đúng nơi; token/secret không còn trong URL/query/body; path, API version và query parameter public vẫn đúng; Link giữ quan hệ rel; JSON/XML vẫn hợp lệ; ID nghiệp vụ không bị thay nhầm; cURL/HTTPie và HTML/PDF cũng không còn giá trị cũ.

Nếu giá trị nhạy cảm đã vào artifact hoặc repository, sửa snippet mới chưa đủ; cần xử lý artifact cũ và credential theo quy trình an toàn của tổ chức.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Host request vẫn là localhost | Chỉ dùng replacePattern trên body hoặc sai điểm gắn | Dùng preprocessRequest(modifyUris(...)) |
| Host trong Location không đổi | Nhầm modifyUris xử lý response header | Dùng response header processor |
| Token vẫn còn trong query | Regex không bao phủ key/encoding thực tế | Rà soát key, encoding và test pattern |
| Query parameter kế tiếp bị mất | Regex tham lam hoặc không giới hạn | Giới hạn value tới ampersand/whitespace |
| Path/API version bị thay | Pattern quá rộng | Giới hạn vùng thay, giữ path contract |
| Link header bị hỏng | Regex không giữ cú pháp nhiều link/rel | Dùng fixture hoặc custom parser |
| JSON không hợp lệ | String replacement phá escaping | Kiểm tra JSON; ưu tiên dữ liệu giả |
| ID nghiệp vụ bị đổi | Nhiều value cùng khớp regex | Thu hẹp pattern hoặc fixture xác định |
| Assertion pass nhưng snippet sai | Chỉ review output, bỏ qua contract | Assertion message thật và review snippet riêng |
| HTML/PDF còn URL cũ | Chỉ scan một file hoặc artifact cũ | Clean, render lại và scan mọi artifact |

## 12. Best practices

1. Dùng fixture URL/token giả ngay từ đầu; pattern replacement là lớp chuẩn hóa bổ sung.
2. Chọn processor theo vị trí: modifyUris cho request URI, modifyHeaders cho header, replacePattern cho content.
3. Giới hạn regex và kiểm thử trường hợp khớp lẫn không khớp.
4. Giữ path, API version và query parameter có ý nghĩa nghiệp vụ.
5. Chú ý URL encoding, dấu phân cách, fragment và capturing group.
6. Dùng parser-aware processor khi JSON/XML/Link phức tạp; regex không phải parser cấu trúc.
7. Assertion kiểm tra request/response thật; preprocessor chỉ thay bản ghi snippet.
8. Descriptor và phần viết tay phải thống nhất với ví dụ sau xử lý.
9. Kiểm tra HTTP, cURL, HTTPie, header/body snippets và artifact đã render.
10. Chạy clean build và scan secret/link patterns trong CI trước publish.

## 13. Bài thực hành

Tạo documentation test cho endpoint POST /api/verifications. Response chứa Location có host nội bộ, JSON có verificationUrl và query token ngẫu nhiên, cùng requestId động. Tài liệu cần host ví dụ, token placeholder và ID ổn định.

**Nhiệm vụ:**

1. Tạo fixture request/response giả; không dùng token thật.
2. Assertion status, path của Location, trạng thái xác minh và request ID trên response gốc.
3. Dùng modifyUris để chuẩn hóa host/port request URI nếu cần.
4. Dùng modifyHeaders hoặc processor phù hợp để thay host của Location.
5. Dùng replacePattern với pattern hẹp để thay token trong body.
6. Chuẩn hóa request ID động nếu nó không phải trọng tâm contract.
7. Kiểm tra JSON còn hợp lệ và query parameter public còn nguyên.
8. Include raw response, response headers và response fields trong AsciiDoc.
9. Scan snippet và HTML/PDF để bảo đảm không còn token/host nội bộ.
10. Chạy clean build để xác nhận tài liệu được tạo lại từ test hiện tại.

**Tiêu chí hoàn thành:** host và token nhạy cảm không lộ; link giữ đúng path/query semantics; body hợp lệ; assertion xác minh response thật; descriptor và snippet nhất quán.

## 14. Ghi nhớ

- replacePattern(Pattern, String) thay phần content khớp pattern trong bản message dùng tạo snippet.
- modifyUris() chuyên chuẩn hóa scheme/host/port của request URI được ghi nhận.
- modifyHeaders() phù hợp khi thay một header cụ thể như Location; không mặc định xử lý mọi URL trong body.
- Path/query phải giữ đúng semantics; regex cần giới hạn và tính đến URL encoding.
- Với JSON/XML/Link phức tạp, fixture an toàn hoặc processor hiểu cấu trúc đáng tin cậy hơn regex rộng.
- Assertion kiểm tra message thật; preprocessing chỉ chuẩn hóa bản ghi tài liệu.
- Đọc lại toàn bộ snippet dẫn xuất và artifact đã render trước khi publish.
