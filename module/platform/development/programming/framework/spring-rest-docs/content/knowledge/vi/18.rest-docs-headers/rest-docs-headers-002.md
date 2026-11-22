# Document response headers bằng responseHeaders

HTTP response không chỉ gồm status và body. Header còn truyền tải metadata để client hiểu representation, theo dõi request, cache, định vị tài nguyên mới hoặc xử lý cập nhật có điều kiện. Với **Spring REST Docs**, ta mô tả các header này bằng `responseHeaders(...)` và `headerWithName(...)`. Các descriptor tạo snippet bảng header, giúp người đọc hiểu header nào thuộc hợp đồng, ý nghĩa ra sao và trong điều kiện nào nó xuất hiện.

Bài học thuộc chương **Headers** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI. Bài này tập trung vào **response header**: khai báo descriptor, kiểm thử giá trị, xử lý header tùy chọn, sinh snippet và đưa bảng header vào tài liệu API.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của response header với client.
2. Dùng `responseHeaders(...)` kết hợp `headerWithName(...)` để tạo bảng mô tả.
3. Phân biệt raw HTTP response snippet với bảng header từ descriptor.
4. Kết hợp assertion để kiểm tra header quan trọng.
5. Mô tả header bắt buộc và tùy chọn đúng hợp đồng.
6. Xử lý header động, nhạy cảm hoặc không nên công khai.
7. Sinh và include `response-headers.adoc` trong Asciidoctor, kiểm soát việc tạo snippet trong CI.

## 2. Response header là một phần của hợp đồng HTTP

Response HTTP có status line, headers và body. Header chứa metadata về representation hoặc hướng dẫn cho client và intermediary. Ví dụ:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/501
Cache-Control: no-store
ETag: "order-501-v1"
X-Request-Id: req-demo-001

{
  "id": 501,
  "status": "CREATED"
}
```

| Header | Ý nghĩa khái quát | Client có thể cần làm gì |
| --- | --- | --- |
| `Content-Type` | Kiểu representation của response | Chọn parser phù hợp |
| `Location` | URI liên quan tới tài nguyên mới hoặc đích điều hướng | Dùng URI để truy cập tài nguyên |
| `Cache-Control` | Chỉ thị cache | Tuân thủ chính sách lưu cache |
| `ETag` | Validator đại diện cho representation | Gửi validator trong request có điều kiện nếu API hỗ trợ |
| `X-Request-Id` | Mã tương quan theo quy ước dịch vụ | Cung cấp mã khi tra cứu log hoặc yêu cầu hỗ trợ |

Không phải endpoint nào cũng trả tất cả các header này. `Location` thường có ý nghĩa khi tạo resource; `ETag` hữu ích nếu API hỗ trợ validator; `Cache-Control` phụ thuộc chính sách cache. Tài liệu chỉ nên cam kết header thật sự thuộc hợp đồng của operation.

### 2.1. Header chuẩn và header riêng của API

`Content-Type`, `Location`, `Cache-Control`, `ETag` và `Last-Modified` có semantics HTTP được biết đến rộng rãi. Header riêng như `X-Request-Id` hoặc `X-RateLimit-Remaining` cần giải thích rõ hơn: ai tạo, có luôn xuất hiện không, định dạng/đơn vị là gì, client có cần lưu hoặc gửi lại không, và giá trị có thay đổi giữa các request không.

Không chỉ ghi “mã request” nếu client cần biết đây là giá trị opaque, không được tự parse, hoặc phải cung cấp cho bộ phận hỗ trợ.

## 3. responseHeaders(...) và headerWithName(...)

Spring REST Docs cung cấp API mô tả response header trong `org.springframework.restdocs.headers.HeaderDocumentation`.

Cấu trúc cơ bản:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI của tài nguyên vừa được tạo"),
    headerWithName("X-Request-Id")
        .description("Mã tương quan của response")
)
```

- `responseHeaders(...)` nhận danh sách descriptor của response header.
- `headerWithName("...")` tạo descriptor cho một header theo tên.
- `description(...)` giải thích ý nghĩa dành cho người đọc.
- `optional()` đánh dấu header có thể vắng mặt trong response được tài liệu hóa.

Khi đặt trong `document(...)`, Spring REST Docs sinh snippet bảng header, thông thường có tên `response-headers.adoc`.

Ví dụ trong operation:

```java
.andDo(document("orders-create-success",
    responseHeaders(
        headerWithName("Location")
            .description("URI của đơn hàng vừa được tạo"),
        headerWithName("X-Request-Id")
            .description("Mã dùng để truy vết lần xử lý")
    )
));
```

Descriptor mô tả **header nào và ý nghĩa của nó**. Nó không thay thế assertion xác nhận header có mặt hoặc có giá trị đúng. Nếu hợp đồng yêu cầu `Location` trỏ tới đơn hàng vừa tạo, hãy kiểm tra URI đó bằng assertion riêng.

Tên header không phân biệt hoa thường theo HTTP semantics. Trong code và tài liệu, nên giữ một cách viết thống nhất như `Content-Type`, `Location`, `ETag` và `Cache-Control` để dễ đọc.

## 4. Ví dụ: tài liệu hóa header của response tạo tài nguyên

Giả sử `POST /api/orders` nhận request hợp lệ, tạo đơn hàng và trả:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/orders/501
X-Request-Id: req-demo-001

{
  "id": 501,
  "status": "CREATED"
}
```

Test nên xác nhận status, header và body rồi khai báo descriptor:

```java
@Test
void createOrder_documentsResponseHeaders() throws Exception {
    mockMvc.perform(
            post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerId":12,"productId":7,"quantity":2}
                    """)
        )
        .andExpect(status().isCreated())
        .andExpect(header().string(
            "Location", "/api/orders/501"
        ))
        .andExpect(header().exists("X-Request-Id"))
        .andExpect(jsonPath("$.id").value(501))
        .andDo(document("orders-create-success",
            responseHeaders(
                headerWithName("Location")
                    .description("URI của đơn hàng vừa được tạo"),
                headerWithName("X-Request-Id")
                    .description("Mã tương quan để truy vết response")
            )
        ));
}
```

Đây là phần test minh họa; dự án cần controller/fixture tạo response xác định và setup Spring REST Docs cho MockMvc. Các static import chính:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Cần các import khác như `MockMvc`, `MediaType`, JUnit annotations và cấu hình REST Docs. Với WebTestClient hoặc REST Assured, cách gửi request và gắn documentation configuration khác với MockMvc, nhưng descriptor response header vẫn giữ cùng ý nghĩa.

### 4.1. Assertion và descriptor có trách nhiệm khác nhau

| Thành phần | Điều được xác nhận/tạo ra |
| --- | --- |
| `status().isCreated()` | HTTP status là `201` |
| `header().string("Location", "/api/orders/501")` | Giá trị Location đúng theo fixture |
| `header().exists("X-Request-Id")` | Header trace có mặt |
| `responseHeaders(...)` | Bảng mô tả ý nghĩa header trong snippet |

Nếu bỏ assertion, test có thể ghi lại một response chứa `Location` sai mà vẫn sinh tài liệu. Nếu bỏ descriptor, header có thể xuất hiện trong `http-response.adoc` nhưng không có bảng header riêng. Dùng cả hai để kiểm tra giá trị và giải thích hợp đồng.

### 4.2. Kết hợp với body và request descriptors

Cùng một operation có thể mô tả request fields, response headers và response fields:

```java
.andDo(document("orders-create-success",
    requestFields(
        fieldWithPath("customerId").description("Mã khách hàng"),
        fieldWithPath("productId").description("Mã sản phẩm"),
        fieldWithPath("quantity").description("Số lượng")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của đơn hàng mới")
    ),
    responseFields(
        fieldWithPath("id").description("Mã đơn hàng"),
        fieldWithPath("status").description("Trạng thái ban đầu")
    )
));
```

Operation này có thể tạo `request-fields.adoc`, `response-headers.adoc`, `response-fields.adoc` và các snippet HTTP mặc định. Chỉ khai báo descriptor cho thành phần thật sự hiện diện và thuộc hợp đồng.

## 5. Header bắt buộc và header tùy chọn

Một header có thể chỉ xuất hiện trong một số response. Ví dụ `Location` có trong response tạo resource `201` nhưng không có trong response lỗi `400`. Descriptor phải phản ánh đúng điều kiện hiện diện.

### 5.1. Header bắt buộc

Nếu mọi response thành công của `POST /api/orders` phải có `Location`, khai báo header không optional:

```java
responseHeaders(
    headerWithName("Location")
        .description("URI của đơn hàng vừa tạo")
)
```

Nếu header không có, việc tài liệu hóa có thể thất bại. Thêm assertion cho giá trị/format nếu đó là cam kết quan trọng.

### 5.2. Header tùy chọn

Nếu `X-Request-Id` có thể vắng mặt theo hợp đồng:

```java
responseHeaders(
    headerWithName("X-Request-Id")
        .description("Mã tương quan nếu được phát sinh")
        .optional()
)
```

`optional()` cho phép header vắng mặt trong operation được tài liệu hóa mà không bị xem là một header bắt buộc thiếu. Nó không có nghĩa client phải gửi header này trong request và không có nghĩa mọi response chắc chắn sẽ chứa nó.

Không dùng `optional()` chỉ để làm test pass khi header thực tế phải luôn xuất hiện. Nếu hợp đồng yêu cầu bắt buộc, giữ descriptor bắt buộc và thêm assertion xác nhận header.

### 5.3. Header chỉ có trong một loại response

Không khai báo `Location` là bắt buộc trong descriptor dùng chung cho cả success và error nếu nó chỉ có ở `201`. Tạo operation riêng:

- `orders-create-success`: có `Location`.
- `orders-create-invalid`: không có `Location`, chỉ mô tả header thực sự xuất hiện.

Mỗi operation có descriptor phù hợp với response riêng. Tránh helper descriptor chung nếu điều kiện xuất hiện header khác nhau.

## 6. Một số response header thường gặp

### 6.1. Location

`Location` thường chỉ URI của tài nguyên được tạo hoặc đích điều hướng. Với `201 Created`, header này giúp client xác định tài nguyên mới. Tài liệu cần nói rõ URI tương đối hay tuyệt đối theo hành vi API, path chứa định danh nào và client nên sử dụng ra sao. Nếu giá trị là phần quan trọng của hợp đồng, hãy kiểm tra trực tiếp:

```java
.andExpect(header().string(
    "Location", "/api/orders/501"
))
```

Không chỉ xác nhận header tồn tại nếu client cần dựa vào URI đó.

### 6.2. ETag và Last-Modified

`ETag` và `Last-Modified` có thể dùng làm validators để hỗ trợ cache hoặc conditional requests. Nếu API hỗ trợ `If-None-Match` hoặc `If-Modified-Since`, giải thích mối liên hệ: client nhận validator, lưu theo resource/representation, gửi lại trong request có điều kiện, và server có thể trả `304 Not Modified` khi điều kiện phù hợp.

Ví dụ descriptor:

```java
responseHeaders(
    headerWithName("ETag")
        .description("Validator của representation dùng với If-None-Match"),
    headerWithName("Last-Modified")
        .description("Thời điểm chỉnh sửa cuối theo HTTP-date")
)
```

Không phải API nào cũng có cả hai header. Chỉ tài liệu hóa header server thực sự trả và có cam kết. Nếu validator thay đổi theo dữ liệu, cần test tình huống thay đổi và conditional request chứ không chỉ test sự hiện diện.

### 6.3. Cache-Control và Vary

`Cache-Control` mô tả chính sách cache. `Vary` chỉ ra request header nào ảnh hưởng đến representation được chọn. Ví dụ:

```java
responseHeaders(
    headerWithName("Cache-Control")
        .description("Chỉ thị cache áp dụng cho response"),
    headerWithName("Vary")
        .description("Request header ảnh hưởng đến representation")
)
```

Nếu cần, giải thích directive như `no-store` hoặc `max-age` và phạm vi áp dụng. Bảng snippet cho thấy giá trị mẫu; phần diễn giải phải nêu chính sách được cam kết.

### 6.4. Content-Type

`Content-Type` xác định media type của representation. Với JSON API, response thường dùng `application/json` hoặc media type có suffix JSON. Tài liệu có thể nói media type được trả, versioning qua media type nếu dùng và parser phía client cần chọn.

`Content-Type` thường đã hiện trong `http-response.adoc`. Nếu cần bảng header riêng, phải khai báo `responseHeaders(...)`; nó không tự tạo `response-headers.adoc` chỉ vì raw response có header đó.

### 6.5. Phân trang và giới hạn tốc độ

API có thể dùng header `Link` cho trang tiếp/trước, `X-RateLimit-Limit` và `X-RateLimit-Remaining` cho hạn mức, hoặc `Retry-After` để gợi ý thời điểm thử lại. Tên và semantics header riêng không đồng nhất giữa các API. Cần định nghĩa format, đơn vị, điều kiện xuất hiện và cách client xử lý; không khuyến khích retry liên tục chỉ dựa vào một giá trị mẫu.

## 7. Header động và header nhạy cảm

Một số response header thay đổi giữa các lần test: request ID, trace ID, timestamp, ETag, cookie hoặc metadata phụ thuộc môi trường. Raw HTTP snippet có thể hiển thị header đã ghi nhận, nên phải phân biệt header thuộc hợp đồng với header tình cờ do framework, proxy hay container thêm vào.

Không đưa các giá trị nhạy cảm vào tài liệu public nếu không có mục đích an toàn:

- `Set-Cookie` chứa session identifier.
- Token hoặc thông tin xác thực.
- Header nội bộ tiết lộ danh tính, topology hoặc hạ tầng.
- Trace metadata có thể lộ thông tin vận hành.
- Giá trị gắn với dữ liệu cá nhân.

Dùng fixture giả và preprocessors để loại bỏ/thay các giá trị cần thiết trước khi ghi snippet. Việc lọc snippet không thay thế việc sửa response thật nếu implementation đang rò rỉ dữ liệu.

### 7.1. Chuẩn hóa giá trị động

Có thể dùng `preprocessResponse(prettyPrint())` để làm đẹp response:

```java
.andDo(document("orders-create-success",
    preprocessResponse(prettyPrint()),
    responseHeaders(
        headerWithName("Location")
            .description("URI của đơn hàng vừa tạo"),
        headerWithName("X-Request-Id")
            .description("Mã tương quan của response")
    )
))
```

`prettyPrint()` chỉ định dạng nội dung, không tự thay request ID động. Nếu cần chuẩn hóa header, hãy dùng preprocessor thay thế phù hợp với phiên bản Spring REST Docs và xác nhận snippet cuối không còn dữ liệu thật. Assertion phải kiểm tra response gốc; không dùng preprocessor để che status hoặc header sai.

### 7.2. Có nên mô tả mọi header?

Không. Chỉ chọn header mà client cần đọc/gửi lại, header ảnh hưởng cache/điều hướng/conditional request/retry hoặc header API công bố như một phần giao diện. Header hạ tầng không ổn định, không có cam kết nên không đưa vào bảng hợp đồng; raw response snippet cũng cần được rà soát để tránh gây hiểu nhầm.

## 8. Sinh và đọc response-headers.adoc

Khi test gọi `responseHeaders(...)`, Spring REST Docs tạo snippet bảng header cho identifier tương ứng, thông thường là `response-headers.adoc`.

Ví dụ output:

```text
target/generated-snippets/
└── orders-create-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-fields.adoc
    ├── response-headers.adoc
    └── response-fields.adoc
```

Bảng có thể thể hiện:

| Header | Mô tả |
| --- | --- |
| `Location` | URI của đơn hàng vừa được tạo |
| `X-Request-Id` | Mã tương quan để truy vết response |

Cấu trúc chi tiết phụ thuộc template/version. `response-headers.adoc` là bảng descriptor; `http-response.adoc` là ví dụ HTTP có header và body thực tế. Một file giải thích header, file còn lại cho thấy header xuất hiện như thế nào trong ví dụ.

Các lý do thường không có `response-headers.adoc`: test chưa khai báo `responseHeaders(...)`, test không chạy tới `document(...)`, descriptor được gắn vào identifier khác hoặc test thất bại trước khi ghi snippet. Không include file này cho mọi operation nếu test không sinh ra nó.

## 9. Nhúng bảng header vào Asciidoctor

Trong file AsciiDoc, đặt phần header ngay sau ví dụ response:

```asciidoc
=== Tạo đơn hàng

Gửi request hợp lệ để tạo đơn hàng mới.

==== Response

include::{snippets}/orders-create-success/http-response.adoc[]

==== Response headers

Bảng dưới đây mô tả các header quan trọng mà client có thể sử dụng.

include::{snippets}/orders-create-success/response-headers.adoc[]

==== Response fields

include::{snippets}/orders-create-success/response-fields.adoc[]
```

Attribute `{snippets}` phải trỏ tới output directory Spring REST Docs, chẳng hạn `target/generated-snippets` trong Maven. Với Markdown, cần bước chuyển đổi hoặc chèn snippet tương thích; `include::{snippets}/...[]` là cú pháp Asciidoctor, không phải chức năng mặc định của mọi Markdown renderer.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Header có trong raw response nhưng không có bảng | Chưa khai báo `responseHeaders(...)` | Thêm descriptor cho header thuộc hợp đồng |
| `response-headers.adoc` không xuất hiện | Test không chạy hoặc không gọi descriptor | Kiểm tra test và identifier |
| Test lỗi vì thiếu header | Descriptor bắt buộc nhưng response không có | Xác minh hợp đồng; chỉ dùng `optional()` nếu đúng là tùy chọn |
| Header có mặt nhưng giá trị sai | Chỉ có descriptor, thiếu assertion | Thêm assertion cho giá trị/format |
| Dùng chung descriptor cho success và error | Header chỉ có ở một loại response | Tạo operation riêng |
| Bảng chứa header nội bộ | Mô tả mọi header của server | Chọn header public và chuẩn hóa raw snippet |
| Snippet đổi mỗi lần chạy | Request ID/timestamp động | Dùng fixture hoặc preprocessor |
| Asciidoctor không tìm thấy include | Sai identifier hoặc output directory | Đối chiếu `document(...)` với attribute snippets |
| Raw snippet lộ cookie/token | Ghi nguyên header nhạy cảm | Dùng dữ liệu giả, preprocessor và kiểm tra output |

## 11. Best practices

1. Chỉ mô tả header thuộc hợp đồng, không biến header tình cờ của proxy/container thành cam kết API.
2. Kết hợp descriptor với assertion: descriptor giải thích, assertion xác nhận sự hiện diện và giá trị.
3. Dùng `optional()` chỉ khi header thật sự có thể vắng mặt.
4. Tách operation cho response khác nhau, ví dụ `201` có `Location` và `400` không có.
5. Giải thích semantics để client biết cách dùng `Location`, `ETag`, `Cache-Control`, `Retry-After` hoặc request ID.
6. Chuẩn hóa header động và loại dữ liệu nhạy cảm trước khi xuất bản.
7. Kiểm tra cả raw response và bảng header để bảo đảm nhất quán.
8. Nối test tạo snippet trước bước render trong CI.

## 12. Bài thực hành

Tài liệu hóa endpoint `POST /api/orders`. Khi tạo thành công, API trả `201 Created`, `Location`, `X-Request-Id` và JSON đơn hàng. Khi request không hợp lệ, API trả `400 Bad Request` cùng schema lỗi và không có `Location`.

**Nhiệm vụ:**

1. Viết hai HTTP test riêng: `orders-create-success` và `orders-create-invalid`.
2. Ở test thành công, kiểm tra status, giá trị `Location`, sự hiện diện của `X-Request-Id` và một field body quan trọng.
3. Dùng `responseHeaders(...)` mô tả hai header của response thành công.
4. Ở test lỗi, chỉ mô tả header thực sự thuộc response 400; không dùng descriptor bắt buộc cho `Location`.
5. Nếu `X-Request-Id` có thể vắng mặt theo hợp đồng, dùng `optional()` và giải thích điều kiện.
6. Chạy test, xác nhận output operation có `response-headers.adoc`.
7. Include bảng header vào trang AsciiDoc dưới response tương ứng.
8. Kiểm tra snippet không chứa cookie, token hoặc request ID từ môi trường thật.
9. Chạy build sạch và xác nhận trang render đúng.

**Tiêu chí hoàn thành:** mỗi operation có descriptor phù hợp, giá trị quan trọng được kiểm tra bằng assertion, bảng header được sinh và include đúng, header tùy chọn được mô tả chính xác và output không lộ dữ liệu nhạy cảm.

## 13. Ghi nhớ

- `responseHeaders(...)` khai báo descriptor cho response header; `headerWithName(...)` xác định header và `description(...)` giải thích ý nghĩa.
- Descriptor tạo `response-headers.adoc`; raw response snippet vẫn ghi ví dụ HTTP của operation.
- Dùng assertion riêng để xác nhận header tồn tại và có giá trị/format đúng.
- `optional()` chỉ dùng khi header thực sự có thể vắng mặt theo hợp đồng.
- Tách descriptor cho response khác nhau, ví dụ `201 Created` có `Location` và `400 Bad Request` không có.
- Chỉ công bố header cần thiết cho client; xử lý header động/nhạy cảm trước khi xuất bản.
- Include bảng header vào Asciidoctor và nối việc sinh snippet vào build/CI để tài liệu được tạo lại từ test hiện tại.
