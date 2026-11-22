# RequestPreprocessor và ResponsePreprocessor

Trong Spring REST Docs, request và response là hai message độc lập, có nội dung và mục đích mô tả riêng. Khi tạo snippet, ta thường cần xử lý khác nhau cho từng phía: request có thể cần thay Authorization, chuẩn hóa Host hoặc loại Cookie; response có thể cần định dạng JSON, chuẩn hóa request ID hoặc loại Set-Cookie. Hai nhánh preprocessor giúp thực hiện việc đó một cách tách biệt.

Spring REST Docs cung cấp các API gắn processor qua `preprocessRequest(...)` và `preprocessResponse(...)`. Về mặt kiểu xử lý, request được xử lý bởi `OperationRequestPreprocessor` và response được xử lý bởi `OperationResponsePreprocessor`. Những processor này tác động lên bản message dùng để sinh snippet. Chúng không thay đổi request đã gửi tới server hay response mà ứng dụng trả về cho test.

Bài học thuộc chương **Preprocessors** của module `SPRING_REST_DOCS`. Module thực hành tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp vào build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt nhiệm vụ của request preprocessor và response preprocessor.
2. Hiểu vai trò của `OperationRequestPreprocessor` và `OperationResponsePreprocessor`.
3. Gắn processor cho đúng phía bằng `preprocessRequest(...)` và `preprocessResponse(...)`.
4. Chọn processor phù hợp để định dạng body, thay header hoặc loại metadata khỏi snippet.
5. Kết hợp nhiều processor và kiểm tra ảnh hưởng của thứ tự xử lý.
6. Giữ assertion trên message thật và tránh nhầm bản ghi đã xử lý với hành vi ứng dụng.
7. Tổ chức test, snippet và CI sao cho request/response được tài liệu hóa nhất quán.

## 2. Hai loại message, hai nhánh xử lý

Một HTTP exchange gồm request từ client và response từ server:

```text
HTTP client / test
       │
       │ Request
       ▼
Spring application
       │
       │ Response
       ▼
Test nhận kết quả
       │
       ▼
document(identifier, ...)
       │
       ├── preprocessRequest(...)
       │       └── xử lý bản request được ghi nhận
       │
       └── preprocessResponse(...)
               └── xử lý bản response được ghi nhận
                       │
                       ▼
                 Snippet generation
                       │
                       ▼
               Asciidoctor / Markdown
```

Request processor và response processor không thể hoán đổi tùy tiện. Một số biến đổi chỉ có ý nghĩa ở request, chẳng hạn thay Authorization hoặc loại Cookie. Một số biến đổi chỉ có ý nghĩa ở response, chẳng hạn chuẩn hóa ETag, loại Set-Cookie hoặc định dạng body server trả về.

| Nhánh | Đối tượng được xử lý | Ví dụ thông tin | Snippet thường bị ảnh hưởng |
| --- | --- | --- | --- |
| Request | HTTP request được ghi nhận | Method, URI, request headers, request body | http-request, cURL, HTTPie, request header/field snippets |
| Response | HTTP response được ghi nhận | Status, response headers, response body | http-response, response header/field snippets |

Danh sách file cụ thể phụ thuộc descriptor và cấu hình test. Raw request/response là ví dụ message; các bảng descriptor được sinh từ những mô tả mà test khai báo.

## 3. RequestPreprocessor và preprocessRequest(...)

### 3.1. Vai trò của request preprocessor

Request preprocessor biến đổi request đã được ghi nhận trước khi Spring REST Docs tạo snippet. Nó phù hợp khi muốn:

- Làm đẹp request body JSON/XML.
- Thay Authorization hoặc API key test bằng placeholder.
- Loại Cookie, header nội bộ hoặc header môi trường.
- Chuẩn hóa Host, port hay URI trong ví dụ.
- Thay giá trị động mà người đọc không cần thấy.

Nó không thay đổi request được gửi tới controller/server. Nếu test gửi Bearer token giả, ứng dụng nhận giá trị đó; preprocessor có thể thay giá trị thành placeholder chỉ trong snippet.

### 3.2. Gắn request preprocessor

Ví dụ dùng MockMvc:

```java
mockMvc.perform(
        get("/api/orders/{id}", 42L)
            .header("Authorization", "Bearer docs-test-token")
            .header("Cookie", "SESSION=test-session")
            .accept(MediaType.APPLICATION_JSON)
    )
    .andExpect(status().isOk())
    .andDo(document("orders-get-authenticated",
        preprocessRequest(
            prettyPrint(),
            modifyHeaders()
                .set("Authorization", "Bearer <access-token>")
                .build(),
            removeHeaders("Cookie")
        )
    ));
```

Trong ví dụ:

- `prettyPrint()` định dạng request body nếu có body phù hợp.
- `modifyHeaders()` thay Authorization trên bản request được ghi thành snippet.
- `removeHeaders("Cookie")` loại cookie khỏi request snippet.
- Assertions vẫn quan sát kết quả của request gửi với token và cookie test ban đầu.

Cú pháp builder cần khớp phiên bản Spring REST Docs đang dùng. Token và session trong test phải là fixture giả; preprocessor là lớp làm sạch bổ sung chứ không phải lý do để đưa secret thật vào môi trường test.

### 3.3. Khi nào dùng request preprocessor?

| Tình huống | Xử lý phù hợp | Lý do |
| --- | --- | --- |
| Body JSON khó đọc | `prettyPrint()` | Cải thiện khả năng đọc |
| Bearer token test xuất hiện trong request | Thay Authorization | Giữ tên header, ẩn giá trị credential |
| Cookie session không cần cho người tích hợp | `removeHeaders("Cookie")` | Tránh công bố session identifier |
| Host/port phụ thuộc máy chạy test | Chuẩn hóa URI/Host bằng processor thích hợp | Snippet ổn định giữa local và CI |
| Query/body chứa dữ liệu fixture riêng | Thay phần dữ liệu có chủ đích | Không lộ thông tin không cần thiết |

Không loại header chỉ vì nó trông nội bộ nếu đó là một phần hợp đồng mà client cần hiểu. Trong trường hợp đó, giữ tên header và thay giá trị bằng placeholder rõ ràng.

## 4. ResponsePreprocessor và preprocessResponse(...)

### 4.1. Vai trò của response preprocessor

Response preprocessor xử lý response mà test đã nhận trước khi tạo snippet. Nó phù hợp khi muốn:

- Định dạng JSON/XML response.
- Loại Set-Cookie, trace/debug header hoặc metadata không công khai.
- Chuẩn hóa request ID, timestamp, ETag hoặc giá trị phụ thuộc môi trường.
- Thay hostname/URL tuyệt đối bằng giá trị mẫu.
- Che dữ liệu trong response body khi giá trị thật không cần thiết cho ví dụ.

Response thật vẫn được trả về cho test và client. Nếu assertion xác nhận response có X-Request-Id, assertion chạy trên giá trị thật; snippet sau preprocessing có thể hiển thị docs-request-id.

### 4.2. Gắn response preprocessor

Ví dụ:

```java
mockMvc.perform(get("/api/orders/{id}", 42L))
    .andExpect(status().isOk())
    .andExpect(header().exists("X-Request-Id"))
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("orders-get",
        preprocessResponse(
            prettyPrint(),
            removeHeaders("Set-Cookie", "X-Internal-Trace"),
            modifyHeaders()
                .set("X-Request-Id", "docs-request-id")
                .build()
        )
    ));
```

Ở đây prettyPrint định dạng response body, removeHeaders loại header không cần công khai và modifyHeaders thay request ID động bằng ví dụ ổn định. Test vẫn kiểm tra status, header có mặt và ID trong body trên response thật.

### 4.3. Khi nào dùng response preprocessor?

| Tình huống | Xử lý phù hợp | Lý do |
| --- | --- | --- |
| JSON response compact | `prettyPrint()` | Dễ đọc, review và học theo |
| Set-Cookie chứa session | `removeHeaders("Set-Cookie")` nếu cookie không thuộc ví dụ public | Không làm lộ session |
| Request ID thay đổi mỗi lần chạy | Thay giá trị bằng ID mẫu | Giảm diff không có ý nghĩa |
| Header trace nội bộ | Loại hoặc chuẩn hóa theo chính sách tài liệu | Tránh tiết lộ vận hành |
| Response chứa hostname môi trường | Thay host bằng tên ví dụ | Không gắn tài liệu với môi trường riêng |

Nếu header hoặc body là một phần hợp đồng cần mô tả, đừng xóa khiến client không còn thấy cách API hoạt động. Có thể giữ cấu trúc nhưng dùng dữ liệu giả.

## 5. So sánh hai nhánh

| Đặc điểm | RequestPreprocessor | ResponsePreprocessor |
| --- | --- | --- |
| Wrapper Spring REST Docs | `preprocessRequest(...)` | `preprocessResponse(...)` |
| Kiểu processor | `OperationRequestPreprocessor` | `OperationResponsePreprocessor` |
| Đối tượng | Request được ghi nhận | Response được ghi nhận |
| Ví dụ phổ biến | Authorization, Cookie, Host, request body | Set-Cookie, request ID, ETag, response body |
| Raw snippet chính | `http-request.adoc` và lệnh client | `http-response.adoc` |
| Tác động tới message thật | Không | Không |

Một số processor dùng được ở cả hai phía, ví dụ định dạng body hoặc thay header. Tuy nhiên, khả năng áp dụng cho cả hai không có nghĩa nên dùng cùng quy tắc ở cả hai. Hãy xem giá trị và ý nghĩa của message tương ứng.

## 6. Dùng đồng thời request và response processor

Một operation thường cần chuẩn hóa cả hai phía:

```java
.andDo(document("orders-get",
    preprocessRequest(
        prettyPrint(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    ),
    preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie"),
        modifyHeaders()
            .set("X-Request-Id", "docs-request-id")
            .build()
    )
));
```

Hai wrapper độc lập và có thể khai báo cùng trong một lời gọi document. Request giữ ví dụ xác thực nhưng thay token, bỏ cookie phiên; response giữ status/body có ý nghĩa, bỏ cookie server và thay request ID động. Việc tách hai nhánh giúp người review biết giá trị nào thay ở request và giá trị nào thay ở response.

### 6.1. Thứ tự nhiều processor trong cùng một nhánh

Thứ tự processor có thể ảnh hưởng output. Nếu processor đầu tiên xóa header, processor sau không còn header đó để thay. Nếu processor thay body rồi mới format, định dạng áp dụng trên body sau thay đổi.

Hãy xác định đầu ra mong muốn, đặt processor theo thứ tự hợp lý, chạy test và đọc snippet cuối cùng. Xác minh trên phiên bản thư viện thực tế thay vì suy ra mọi hành vi chỉ từ tên method.

## 7. Request/response processor và assertions

**Assertion bảo vệ hành vi API; preprocessor chuẩn hóa bản ghi dùng cho tài liệu.**

Response thật có thể là:

```http
HTTP/1.1 200 OK
X-Request-Id: req-8a1f2d
Set-Cookie: SESSION=real-test-session
Content-Type: application/json

{"id":42,"status":"PAID"}
```

Test assertion:

```java
.andExpect(status().isOk())
.andExpect(header().exists("X-Request-Id"))
.andExpect(jsonPath("$.status").value("PAID"))
```

Response snippet sau preprocessing có thể là:

```http
HTTP/1.1 200 OK
X-Request-Id: docs-request-id
Content-Type: application/json

{
  "id": 42,
  "status": "PAID"
}
```

ID mẫu và việc không còn Set-Cookie chỉ mô tả bản ghi tài liệu. Không dùng snippet sau xử lý để khẳng định ứng dụng thật trả chuỗi ID mẫu hoặc không trả Set-Cookie. Muốn kiểm tra các điều đó, assertion phải chạy trên response trước preprocessing.

## 8. Descriptor sau khi áp dụng processor

Descriptor như `requestHeaders(...)`, `responseHeaders(...)`, `requestFields(...)` và `responseFields(...)` mô tả contract. Preprocessor chuẩn hóa request/response làm nguồn cho snippet. Hai phần bổ sung nhau nhưng không thay thế nhau.

Ví dụ tài liệu hóa Authorization mà không công bố token:

```java
.andDo(document("orders-get",
    preprocessRequest(
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build()
    ),
    requestHeaders(
        headerWithName("Authorization")
            .description("Bearer access token do hệ thống xác thực cấp")
    )
));
```

Bảng descriptor giải thích header; raw request snippet thể hiện mẫu sau xử lý. Nếu xóa Authorization hoàn toàn bằng removeHeaders, hãy xem người tích hợp còn cần nhìn thấy header này trong ví dụ không. Không để bảng mô tả một điều trong khi raw request minh họa điều khác.

## 9. Tự xây processor khi built-in chưa đủ

Processor có sẵn thường đáp ứng nhu cầu phổ biến. Khi cần quy tắc phức tạp hơn, có thể tạo implementation riêng dựa trên API operation preprocessing của phiên bản thư viện đang dùng.

Custom processor nên:

- Chỉ thay đúng header/body được yêu cầu.
- Không thay status, method hoặc URI nếu không có mục tiêu tài liệu hóa rõ.
- Không sửa message gốc mà ứng dụng gửi/nhận.
- Có test xác nhận input và output.
- Có tên và mô tả nêu rõ lý do biến đổi.

Ví dụ ý tưởng: processor thay hostname trong request thành api.example.test, hoặc chuẩn hóa timestamp trong response body. Chi tiết interface/factory cần theo API version của Spring REST Docs; tránh tạo helper sửa chuỗi tùy tiện nếu built-in đã đủ.

Không dùng processor để biến status lỗi thành thành công, xóa field bắt buộc bị thiếu, sửa giá trị nghiệp vụ sai thành giá trị mong đợi hoặc che response không an toàn. Những cách đó che giấu lỗi và làm tài liệu mất giá trị kiểm chứng.

## 10. Tổ chức helper theo chiều request/response

Nếu nhiều test lặp chính sách snippet, có thể tạo helper riêng cho từng phía:

```java
static OperationRequestPreprocessor publicRequestPreprocessor() {
    return preprocessRequest(
        prettyPrint(),
        modifyHeaders()
            .set("Authorization", "Bearer <access-token>")
            .build(),
        removeHeaders("Cookie")
    );
}
```

```java
static OperationResponsePreprocessor publicResponsePreprocessor() {
    return preprocessResponse(
        prettyPrint(),
        removeHeaders("Set-Cookie", "X-Internal-Trace")
    );
}
```

Các đoạn trên minh họa cách tổ chức; kiểm tra kiểu trả về/import theo API Spring REST Docs trong dự án. Tách hai helper làm mục đích rõ hơn và tránh áp dụng chính sách response lên request.

Không dùng helper chung quá rộng nếu endpoint có contract khác nhau. Ví dụ một operation cần giữ Set-Cookie vì tài liệu hóa cơ chế cookie cho client; helper mặc định loại Set-Cookie không phù hợp.

## 11. Khác biệt theo test client

Nguyên tắc request/response preprocessing không phụ thuộc test client, nhưng điểm gắn recorder khác nhau:

| Client | Nơi gắn tài liệu hóa | Lưu ý |
| --- | --- | --- |
| MockMvc | `andDo(document(...))` | Cấu hình MockMvc với REST Docs; dùng builder giữ URI template khi cần |
| WebTestClient | Filter/documentation configuration trong chuỗi exchange | Cần module WebTestClient và recorder tương thích |
| REST Assured | REST Docs filter trong request specification | Gắn filter vào request đã cấu hình trước khi gửi |

Không sao chép cú pháp MockMvc cho client khác. Dùng API tích hợp tương ứng để truyền processor vào operation recorder.

## 12. Bài thực hành

Tài liệu hóa endpoint `GET /api/orders/{id}`. Request dùng Bearer token giả và Cookie phiên test. Response có X-Request-Id động, Set-Cookie từ middleware và JSON đơn hàng.

**Nhiệm vụ:**

1. Viết test với MockMvc và cấu hình Spring REST Docs.
2. Gửi Authorization token giả và Cookie giả.
3. Assertion status, header request ID tồn tại và field response quan trọng.
4. Dùng request preprocessor định dạng body nếu có, thay Authorization bằng placeholder và loại Cookie.
5. Dùng response preprocessor định dạng JSON, thay request ID bằng ID mẫu và loại Set-Cookie.
6. Khai báo request/response header descriptors đúng với contract public.
7. Chạy test, kiểm tra http-request, http-response, cURL/HTTPie và bảng header.
8. Xác nhận assertion kiểm tra message thật, còn snippet thể hiện bản đã xử lý.
9. Include snippet vào trang AsciiDoc.
10. Chạy clean build và kiểm tra output; thêm secret scan nếu tài liệu được publish.

**Tiêu chí hoàn thành:** hai nhánh processor được gắn đúng phía; secret được làm sạch khỏi snippet; status/body/header thật vẫn được assertion; descriptor nhất quán với ví dụ; tài liệu render từ output mới.

## 13. Ghi nhớ

- Request và response là hai message độc lập, vì vậy cần chọn đúng nhánh xử lý.
- `preprocessRequest(...)` áp dụng `OperationRequestPreprocessor` lên request được ghi nhận; `preprocessResponse(...)` áp dụng `OperationResponsePreprocessor` lên response được ghi nhận.
- Request processor thường chuẩn hóa Authorization, Cookie, Host, URI và request body; response processor thường xử lý Set-Cookie, request ID, ETag, header nội bộ và response body.
- Có thể gắn cả hai trong cùng document, nhưng nên giữ quy tắc riêng theo chiều message.
- Assertion kiểm tra message thật; preprocessor chỉ thay bản ghi snippet, không thay đổi ứng dụng hoặc dữ liệu client nhận.
- Descriptor giải thích contract; raw snippet thể hiện request/response sau preprocessing. Hai phần phải nhất quán.
- Kiểm tra thứ tự processor, mọi snippet dẫn xuất và kết quả render trong CI trước khi publish.
