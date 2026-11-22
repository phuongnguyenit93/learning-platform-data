# Preprocessor là gì và xử lý ở thời điểm nào

Spring REST Docs tạo snippet từ request và response được ghi nhận khi bài kiểm thử HTTP chạy. Tuy nhiên, message thô đôi khi chưa phù hợp để đưa thẳng vào tài liệu: JSON khó đọc, header có request ID ngẫu nhiên, request chứa cookie không cần công khai hoặc response mang hostname riêng của môi trường kiểm thử. **Preprocessor** cho phép biến đổi bản request hoặc response dùng để tạo snippet, giúp ví dụ dễ đọc, ổn định và an toàn hơn.

Điểm quan trọng là hiểu đúng thời điểm: preprocessor được áp dụng trong bước ghi nhận/tài liệu hóa operation, khi Spring REST Docs chuẩn bị tạo snippet. Nó không phải middleware xử lý request trong ứng dụng và không thay đổi response mà controller đã gửi về cho test. Vì vậy, assertion vẫn cần xác minh hành vi thật; preprocessor chỉ điều chỉnh bản message dùng cho tài liệu.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, parameter và header, rồi biên soạn Asciidoctor/Markdown và tích hợp vào build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích preprocessor trong Spring REST Docs giải quyết vấn đề gì.
2. Xác định thời điểm preprocessor chạy trong chuỗi test → assertion → document → snippet.
3. Phân biệt xử lý request và response qua `preprocessRequest(...)` và `preprocessResponse(...)`.
4. Dùng processor phổ biến để định dạng, loại bỏ hoặc thay đổi thông tin trong bản message được ghi lại.
5. Hiểu mối quan hệ giữa preprocessor, assertion và descriptor.
6. Tránh dùng preprocessor để che giấu lỗi implementation hoặc biến đổi dữ liệu thật trong ứng dụng.
7. Kiểm tra snippet và tích hợp bước xử lý vào build/CI.

## 2. Preprocessor là gì?

Preprocessor là thành phần xử lý được Spring REST Docs gọi trên request hoặc response trước khi tạo snippet. Nó nhận message được ghi nhận, áp dụng một hay nhiều phép biến đổi, rồi cung cấp kết quả đã xử lý cho bước tạo tài liệu.

Ví dụ response JSON ban đầu:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"name":"Notebook","active":true}
```

Sau khi định dạng, snippet có thể hiển thị:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "name": "Notebook",
  "active": true
}
```

Response của ứng dụng vẫn là message mà test đã nhận. Processor chỉ làm cho bản ghi snippet dễ đọc hơn.

### 2.1. Preprocessor không phải middleware của ứng dụng

| Thành phần | Chạy ở đâu | Mục đích |
| --- | --- | --- |
| Filter/interceptor ứng dụng | Trong luồng xử lý request/response của server | Xác thực, logging, thêm header hoặc thay đổi HTTP message thật |
| Test assertion | Trong bài test sau khi thực hiện request | Xác nhận status, header, body và hành vi |
| Spring REST Docs preprocessor | Trong bước tài liệu hóa operation | Chuẩn hóa bản request/response được ghi vào snippet |

Nếu dùng filter để xóa header response, client thật cũng có thể không còn nhận header đó. Nếu dùng preprocessor để xóa header khỏi snippet, response thật vẫn giữ nguyên. Hai thao tác có tác động khác nhau.

### 2.2. Vì sao cần preprocessor?

Các trường hợp thường gặp:

- Định dạng JSON/XML để người đọc dễ theo dõi.
- Chuẩn hóa hostname, port hoặc URL phụ thuộc môi trường.
- Thay request ID, timestamp hoặc token test bằng giá trị mẫu ổn định.
- Loại cookie, credential hoặc header nội bộ khỏi snippet công khai.
- Điều chỉnh body ví dụ để ẩn dữ liệu không cần thiết.
- Giữ snippet ổn định giữa các lần build, giảm diff không có ý nghĩa.

Không cần preprocessor cho mọi operation. Chỉ thêm khi có nhu cầu; chuỗi biến đổi thừa có thể làm ví dụ khác xa message đã được test.

## 3. Preprocessor chạy ở thời điểm nào?

Luồng khái quát của một operation:

```text
1. Chuẩn bị fixture và test client
             │
             ▼
2. Gửi HTTP request tới ứng dụng
             │
             ▼
3. Ứng dụng xử lý và trả response
             │
             ▼
4. Assertions kiểm tra status/header/body
             │
             ▼
5. Gọi document(identifier, ...)
             │
             ▼
6. Preprocessors biến đổi bản message được ghi nhận
             │
             ▼
7. Descriptor và snippet generation tạo file tài liệu
             │
             ▼
8. Asciidoctor/Markdown ghép snippet vào trang
```

Đây là mô hình khái quát. Với MockMvc, hook thường được gắn qua `andDo(document(...))`; WebTestClient và REST Assured dùng API/filter tích hợp tương ứng. Trong cả ba trường hợp, processor tham gia bước tạo tài liệu sau khi message của operation đã được ghi nhận.

### 3.1. Assertion kiểm tra kết quả thật

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(prettyPrint())
    ));
```

Assertions kiểm tra kết quả request trong test. Sau đó document áp dụng prettyPrint cho bản response dùng tạo snippet. Nếu server trả status sai hoặc thiếu header bắt buộc, test phải thất bại dù preprocessor có thể tạo output đẹp.

### 3.2. Preprocessor không sửa dữ liệu client nhận

Giả sử server trả:

```http
X-Request-Id: req-actual-8791
```

Preprocessor thay giá trị trong snippet thành:

```http
X-Request-Id: docs-request-id
```

Giá trị mẫu chỉ xuất hiện trong snippet. Client thật và assertion vẫn làm việc với giá trị server đã trả. Không dùng giá trị đã chuẩn hóa làm bằng chứng rằng server luôn trả đúng chuỗi mẫu đó.

## 4. Hai điểm gắn chính: preprocessRequest và preprocessResponse

Spring REST Docs cung cấp hai cách bọc processor:

- `preprocessRequest(...)`: áp dụng một hay nhiều processor lên request được ghi nhận.
- `preprocessResponse(...)`: áp dụng processor lên response được ghi nhận.

Ví dụ:

```java
.andDo(document("orders-get",
    preprocessRequest(prettyPrint()),
    preprocessResponse(prettyPrint())
));
```

Hai phía độc lập. Một operation có thể chỉ cần làm đẹp request, chỉ cần làm sạch response hoặc áp dụng các processor khác nhau cho mỗi phía.

### 4.1. Import API thông dụng

Với MockMvc, static imports thường có dạng:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
```

Ngoài ra, có thể import `removeHeaders`, `replacePattern` hoặc API sửa header tùy biến đổi cần thực hiện và phiên bản thư viện.

## 5. Các preprocessor thường gặp

### 5.1. prettyPrint()

`prettyPrint()` định dạng body để dễ đọc, thường hữu ích với JSON/XML:

```java
.andDo(document("products-get",
    preprocessResponse(prettyPrint())
));
```

`prettyPrint()` không thay đổi semantics payload. Nó không tự ẩn dữ liệu nhạy cảm, không sửa kiểu dữ liệu và không xác nhận schema. Với body không phải định dạng được hỗ trợ, hãy kiểm tra output thực tế.

### 5.2. removeHeaders(...)

`removeHeaders(...)` loại header khỏi message được ghi vào snippet. Ví dụ xóa cookie khỏi request và Set-Cookie khỏi response:

```java
.andDo(document("session-info",
    preprocessRequest(removeHeaders("Cookie")),
    preprocessResponse(removeHeaders("Set-Cookie"))
));
```

Header chỉ bị loại khỏi raw HTTP snippet; nó vẫn có thể tồn tại trong request/response thật. Dùng cách này khi header không cần thiết cho người đọc hoặc chứa dữ liệu không nên công khai. Nếu header thuộc hợp đồng và cần hướng dẫn client, thay giá trị bằng placeholder thay vì xóa tên header.

### 5.3. modifyHeaders(...)

`modifyHeaders()` cho phép thay đổi header trong bản message được ghi ra snippet, chẳng hạn thay Authorization bằng placeholder:

```java
.andDo(document("orders-get-authenticated",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    )
));
```

Cú pháp builder cụ thể cần khớp phiên bản Spring REST Docs. Mục tiêu là giữ tên header và cấu trúc request, trong khi không để credential test xuất hiện trong tài liệu. Assertion xác thực vẫn phải chạy trên request ban đầu dùng token test; preprocessor không kiểm thử server bằng placeholder.

### 5.4. replacePattern(...)

`replacePattern(...)` thay phần nội dung khớp regular expression trong message. Nó hữu ích khi chuỗi nhạy cảm xuất hiện trong giá trị header hoặc body và cần được thay theo quy tắc.

Khi dùng regex:

- Giới hạn pattern vào đúng trường cần xử lý.
- Chọn replacement có ý nghĩa và không gây hiểu sai.
- Kiểm tra cả trường hợp pattern khớp và không khớp.
- Đọc snippet sau test để bảo đảm không thay nhầm dữ liệu khác.

Không dùng regex quá rộng vì có thể làm hỏng ID nghiệp vụ hoặc ví dụ payload.

## 6. Kết hợp nhiều processor

Một operation có thể áp dụng nhiều phép biến đổi:

```java
.andDo(document("profile-get",
    preprocessRequest(
        prettyPrint(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Trace"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

Trong ví dụ, request được định dạng và Authorization được thay trong bản snippet. Response được định dạng, loại một số header và chuẩn hóa request ID. Chỉ giữ các bước cần thiết; biến đổi quá nhiều có thể làm message trong tài liệu khác đáng kể so với message thật.

### 6.1. Thứ tự processor có thể ảnh hưởng kết quả

Thứ tự biến đổi có thể quan trọng. Nếu processor đầu tiên xóa một header thì processor sau không còn header đó để thay giá trị. Nếu processor thay body trước khi beautify, kết quả định dạng dựa trên body đã thay.

Hãy xác định đầu ra mong muốn, đặt các bước theo thứ tự hợp lý, chạy test và đọc snippet cuối cùng. Khi thứ tự không tạo kết quả dự kiến, chỉnh processor và xác minh lại trên phiên bản thư viện thực tế.

## 7. Preprocessor và descriptor có vai trò riêng

Preprocessor thay đổi message được dùng cho snippet. Descriptor mô tả thành phần API mà người đọc cần hiểu. Hai thành phần bổ sung nhau nhưng không thay thế nhau.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Assertion | Kiểm tra hành vi thực tế | `status().isOk()`, kiểm tra header/body |
| Preprocessor | Chuẩn hóa bản message cho tài liệu | `prettyPrint()`, `removeHeaders(...)` |
| Descriptor | Mô tả field, parameter hoặc header | `responseFields(...)`, `requestHeaders(...)` |
| Raw snippet | Ví dụ request/response sau xử lý | `http-request.adoc`, `http-response.adoc` |
| Asciidoctor include | Ghép snippet vào trang nguồn | `include::{snippets}/...[]` |

Ví dụ loại Set-Cookie khỏi response snippet nhưng vẫn mô tả Content-Type:

```java
.andDo(document("login",
    preprocessResponse(removeHeaders("Set-Cookie")),
    responseHeaders(
        headerWithName("Content-Type")
            .description("Media type của response")
    )
));
```

Không khai báo descriptor cho Set-Cookie không đảm bảo header biến mất khỏi raw response. Ngược lại, remove header trong preprocessor không có nghĩa ứng dụng không trả header đó.

### 7.1. Kiểm tra descriptor khi message được xử lý

Khi preprocessor loại bỏ hoặc thay đổi thành phần mà descriptor cần mô tả, hãy kiểm tra cách phiên bản thư viện đang dùng xử lý snippet. Header đã bị xóa khỏi bản message ghi nhận sẽ không còn xuất hiện như raw header trước đó.

Nếu cần mô tả Authorization, có thể giữ descriptor giải thích scheme, thay credential bằng placeholder và dùng assertion để xác minh request test đã gửi token giả, server đã xử lý đúng.

## 8. Preprocessor trong các test client

Nguyên tắc không phụ thuộc test client, nhưng cách gắn recorder khác nhau:

| Test client | Điểm gắn tài liệu hóa thường gặp | Điều cần bảo đảm |
| --- | --- | --- |
| MockMvc | `andDo(document(...))` | MockMvc đã cấu hình REST Docs; dùng request builder giữ URI template khi cần |
| WebTestClient | Filter/documentation configuration trong chuỗi exchange | Client đã được tích hợp REST Docs và recorder nhận response |
| REST Assured | REST Docs filter gắn vào request specification | Filter được thêm đúng request và operation có identifier |

Không sao chép cú pháp andDo của MockMvc sang WebTestClient hoặc REST Assured. Dùng module/API dành cho test client tương ứng và gắn processor vào operation được tài liệu hóa.

## 9. Những giới hạn cần hiểu

### 9.1. Preprocessor không sửa ứng dụng

Nếu response thật đang chứa header nội bộ không nên trả cho client, removeHeaders chỉ che nó trong snippet. Cần sửa implementation nếu header đó không nên có trong HTTP response thật.

### 9.2. Preprocessor không thay thế assertion

Nếu test không kiểm tra status, body hoặc header, snippet sau xử lý vẫn có thể trông hợp lệ dù implementation trả sai. Assertion phải xác nhận điều quan trọng trên message thực.

### 9.3. Preprocessor không định nghĩa hợp đồng

Thay token thành placeholder chỉ tạo ví dụ an toàn hơn. Tác giả vẫn cần giải thích scheme, cách client lấy token và điều kiện xác thực.

### 9.4. Không biến đổi quá mức

Nếu xóa quá nhiều header hoặc thay giá trị có ý nghĩa, người đọc không còn thấy cách API hoạt động. Chỉ xử lý phần không cần công bố hoặc phần biến động không mang ý nghĩa cho ví dụ.

## 10. Ví dụ thực hành đầy đủ

Giả sử endpoint `GET /api/orders/{id}` yêu cầu Bearer authentication, trả JSON đơn hàng và `X-Request-Id`. Middleware test có thể thêm `Set-Cookie`. Snippet public cần Authorization placeholder, request ID ổn định và không có cookie.

```java
@Test
void getOrder_createsCleanDocumentation() throws Exception {
    mockMvc.perform(
            RestDocumentationRequestBuilders
                .get("/api/orders/{id}", 42L)
                .header("Authorization", "Bearer docs-test-token")
                .accept(MediaType.APPLICATION_JSON)
        )
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(document("orders-get-success",
            preprocessRequest(
                prettyPrint(),
                modifyHeaders()
                    .set("Authorization", "Bearer <access-token>")
                    .build()
            ),
            preprocessResponse(
                prettyPrint(),
                removeHeaders("Set-Cookie"),
                modifyHeaders()
                    .set("X-Request-Id", "docs-request-id")
                    .build()
            ),
            requestHeaders(
                headerWithName("Authorization")
                    .description("Bearer access token của client")
            ),
            responseHeaders(
                headerWithName("X-Request-Id")
                    .description("Mã dùng để truy vết request")
            ),
            responseFields(
                fieldWithPath("id")
                    .description("Mã định danh đơn hàng")
            )
        ));
}
```

Đây là ví dụ ghép processor, assertion và descriptor; dự án cần setup security filter chain nếu muốn chứng minh xác thực. `docs-test-token` phải là fixture giả chỉ dùng trong test. Đối chiếu imports và API builder với phiên bản Spring REST Docs của dự án.

Sau khi test chạy, kiểm tra:

- `http-request.adoc` có Authorization placeholder, không còn token fixture.
- `http-response.adoc` có request ID mẫu và không có Set-Cookie.
- `request-headers.adoc` và `response-headers.adoc` mô tả đúng semantics.
- `response-fields.adoc` phản ánh cấu trúc response.
- cURL/HTTPie snippet cũng không còn credential gốc.

## 11. Tích hợp tài liệu và CI

Sau test, Asciidoctor có thể include snippet đã xử lý:

```asciidoc
=== Tra cứu đơn hàng

==== Request

include::{snippets}/orders-get-success/http-request.adoc[]

==== Request headers

include::{snippets}/orders-get-success/request-headers.adoc[]

==== Response

include::{snippets}/orders-get-success/http-response.adoc[]

==== Response headers

include::{snippets}/orders-get-success/response-headers.adoc[]
```

Pipeline cần chạy test trước khi render:

```text
Clean generated output
       │
       ▼
Run HTTP documentation tests
       │
       ▼
Apply preprocessors and generate snippets
       │
       ▼
Validate snippets (secret scan / content checks)
       │
       ▼
Render Asciidoctor or Markdown
       │
       ▼
Review final artifact
       │
       ▼
Publish
```

Với Markdown, cú pháp include Asciidoctor không phải tính năng mặc định; cần bước chèn/chuyển đổi phù hợp. Preprocessor chỉ tạo snippet an toàn hơn, CI vẫn nên kiểm tra cả snippet sinh ra và bản HTML/PDF cuối trước publish.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| JSON snippet khó đọc | Chưa áp dụng prettyPrint | Dùng preprocessResponse(prettyPrint()) |
| Token còn trong raw request | Chỉ bỏ descriptor, không làm sạch raw message | Fixture giả và request preprocessor |
| Header đã xóa vẫn xuất hiện trong response thật | Nhầm processor với filter ứng dụng | Processor chỉ tác động snippet; sửa server nếu cần |
| Assertion pass dù snippet đã chuẩn hóa | Coi placeholder là bằng chứng giá trị server | Assertion trên message thật, review snippet riêng |
| Dữ liệu khác bị thay | Regex hoặc processor quá rộng | Thu hẹp quy tắc và kiểm tra output |
| Header cần mô tả bị mất | Dùng remove thay vì replace | Giữ tên header và thay giá trị |
| Snippet biến động mỗi build | Timestamp/ID động chưa chuẩn hóa | Fixture hoặc preprocessor ổn định |
| cURL còn token dù HTTP snippet đã sạch | Chỉ kiểm tra một loại output | Rà soát snippet dẫn xuất |
| Preprocessor không chạy | Gắn sai vị trí hoặc API test client | Xác nhận document hook/filter |
| Tài liệu có output cũ | Không clean hoặc test không chạy | Clean, chạy test, render cùng lifecycle |

## 13. Bài thực hành

Tạo tài liệu cho endpoint `GET /api/accounts/me`. Test dùng token giả và request ID động; response có thể chứa `Set-Cookie` do middleware test.

**Nhiệm vụ:**

1. Cấu hình documentation test bằng MockMvc hoặc test client phù hợp.
2. Gửi request bằng token giả, không đọc secret môi trường thật.
3. Assertion status, một field body và sự tồn tại của request ID trên response thực.
4. Dùng request preprocessor thay Authorization bằng placeholder.
5. Dùng response preprocessor loại Set-Cookie và chuẩn hóa request ID.
6. Thêm request/response header descriptors cho header thuộc contract.
7. Chạy test và kiểm tra raw HTTP, cURL, HTTPie và bảng header snippets.
8. Xác nhận token fixture không còn và request ID có giá trị mẫu ổn định.
9. Include snippet vào AsciiDoc hoặc dùng pipeline chèn snippet nếu đích là Markdown.
10. Chạy clean build và đưa bước kiểm tra output vào CI.

**Tiêu chí hoàn thành:** test kiểm tra message thật; preprocessor chỉ chuẩn hóa bản ghi; header cần thiết vẫn được mô tả; credential/cookie nhạy cảm không lọt vào snippet; tài liệu được render từ output mới của test.

## 14. Ghi nhớ

- Preprocessor biến đổi request/response được dùng để tạo snippet; nó không phải middleware của ứng dụng.
- `preprocessRequest(...)` xử lý bản request được ghi nhận; `preprocessResponse(...)` xử lý bản response được ghi nhận.
- `prettyPrint()` định dạng payload; `removeHeaders(...)` loại header khỏi snippet; `modifyHeaders()` thay đổi giá trị header trong bản ghi; `replacePattern(...)` thay nội dung khớp pattern.
- Assertion vẫn kiểm tra request/response thực; preprocessor không sửa message mà client nhận và không thay thế assertion.
- Descriptor giải thích field/header/parameter; preprocessor chuẩn hóa message; raw snippet hiển thị ví dụ sau xử lý.
- Chọn processor có chủ đích, kiểm tra thứ tự và đọc lại mọi snippet dẫn xuất trước publish.
- Nối test, preprocessor, snippet, Asciidoctor/Markdown và CI để tài liệu có thể tái tạo và không làm lộ dữ liệu nhạy cảm.
