# Đọc snippet thô trước khi đưa vào tài liệu cuối

## 1. Mục tiêu và bối cảnh

Spring REST Docs tạo ra các **snippet** từ HTTP operation do bài kiểm thử thực hiện. Snippet có thể mô tả request, response, body, headers, parameters, fields hoặc cung cấp lệnh CLI như curl/HTTPie. Trước khi include chúng vào trang Asciidoctor/Markdown, cần mở và đọc **snippet thô vừa được sinh** để xác nhận nội dung thực tế khớp với test và hợp đồng API.

Bước review này là một phần của module **SPRING_REST_DOCS**: tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP sử dụng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn tài liệu; rồi tích hợp vào build và CI.

Sau bài học, bạn có thể:

- Xác định output directory, identifier và các snippet được tạo từ một test.
- Đọc raw snippet request/response trước khi biên soạn trang tài liệu.
- Đối chiếu HTTP method, URI, headers, body, status và field descriptors với test.
- Phân biệt raw operation snippets, descriptor tables và tài liệu cuối đã biên soạn.
- Phát hiện thông tin sai, thiếu, không ổn định hoặc nhạy cảm trong snippet.
- Thiết lập quy trình review và CI để tránh publish tài liệu cũ hoặc sai lệch.

> **Raw snippet** là đầu ra trung gian do Spring REST Docs sinh từ operation và cấu hình hiện tại. Nó là bằng chứng về dữ liệu được ghi nhận trong lần test đó, nhưng không tự chứng minh mọi quy tắc nghiệp vụ đã đúng. Chất lượng tài liệu còn phụ thuộc assertions, descriptors và bước biên soạn.

## 2. Raw snippet nằm ở đâu?

Khi test ghi operation với identifier, ví dụ `document("orders-get-success")`, Spring REST Docs sinh các snippet dưới một thư mục ứng với identifier. Với cấu hình MockMvc phổ biến:

~~~java
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
~~~

Cấu trúc output có thể như sau:

~~~text
build/
└── generated-snippets/
    ├── orders-get-success/
    │   ├── curl-request.adoc
    │   ├── httpie-request.adoc
    │   ├── http-request.adoc
    │   ├── http-response.adoc
    │   ├── request-body.adoc
    │   ├── response-body.adoc
    │   ├── request-headers.adoc
    │   ├── response-headers.adoc
    │   ├── request-fields.adoc
    │   └── response-fields.adoc
    └── orders-create/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Đây là cấu trúc **minh họa**, không phải danh sách file bắt buộc trong mọi dự án. Các snippet mặc định có thể gồm `curl-request.adoc`, `httpie-request.adoc`, `http-request.adoc`, `http-response.adoc`, `request-body.adoc` và `response-body.adoc`. Các bảng `request-headers.adoc`, `response-headers.adoc`, `request-fields.adoc`, `response-fields.adoc`, `path-parameters.adoc` hoặc `query-parameters.adoc` chỉ xuất hiện khi test/cấu hình yêu cầu tạo chúng.

Đường dẫn thực tế phụ thuộc build tool và cấu hình:

| Môi trường | Output directory ví dụ |
| --- | --- |
| Gradle với cấu hình thường gặp | `build/generated-snippets` |
| Maven với cấu hình thường gặp | `target/generated-snippets` |
| Output tùy chỉnh | Giá trị được đặt trong REST Docs configurer/annotation |

Đừng đoán thư mục theo thói quen. Mở cấu hình của test hoặc build để xác định đúng output directory, rồi tìm thư mục có đúng identifier. Nếu có nhiều module hoặc nhiều task test, mỗi task có thể dùng cấu hình output khác nhau.

### 2.1. Identifier là chìa khóa để tìm đúng operation

Mỗi operation nên có identifier ổn định, dễ hiểu và phân biệt được tình huống:

| Identifier | Ý nghĩa |
| --- | --- |
| `orders-get-success` | Đọc đơn hàng thành công. |
| `orders-get-not-found` | Không tìm thấy đơn hàng. |
| `orders-create` | Tạo đơn hàng. |
| `orders-delete` | Xóa đơn hàng không có body response. |

Tránh dùng tên chung chung như `test1`, `sample` hoặc một identifier bị nhiều test dùng lại. Nếu hai operation khác nhau ghi cùng identifier, snippet có thể bị ghi đè hoặc tài liệu cuối include nhầm nội dung. Một identifier duy nhất cho một kịch bản giúp reviewer lần từ trang tài liệu về đúng test.

## 3. Phân biệt ba lớp nội dung

Trong quy trình Spring REST Docs, cần phân biệt:

1. **Raw operation snippets:** biểu diễn dữ liệu HTTP được ghi nhận, ví dụ `http-request.adoc` và `http-response.adoc`.
2. **Descriptor snippets:** bảng giải thích field/header/parameter đã khai báo, ví dụ `response-fields.adoc` hoặc `query-parameters.adoc`.
3. **Tài liệu cuối:** trang Asciidoctor/Markdown kết hợp snippet với tiêu đề, giải thích, ghi chú sử dụng, ví dụ nghiệp vụ và hướng dẫn tích hợp.

| Loại | Ví dụ | Điều nó cung cấp |
| --- | --- | --- |
| Raw request | `http-request.adoc` | Method, request target, headers và body được ghi nhận. |
| Raw response | `http-response.adoc` | Status, response headers và body được ghi nhận. |
| Body riêng | `request-body.adoc` / `response-body.adoc` | Chỉ payload của một chiều. |
| Lệnh CLI | `curl-request.adoc` / `httpie-request.adoc` | Cách dựng request để người đọc thử. |
| Descriptor table | `response-fields.adoc` | Tên field và mô tả do người viết khai báo, được kiểm tra với payload. |
| Tài liệu tổng hợp | `api.adoc` hoặc trang tương ứng | Nội dung có cấu trúc, diễn giải và include snippet. |

Raw snippet trả lời **“lần test này đã trao đổi gì?”**; descriptor trả lời **“các thành phần được mô tả có ý nghĩa gì?”**; tài liệu cuối trả lời **“người dùng API cần hiểu và thực hiện điều gì?”**.

Ví dụ, `http-response.adoc` có thể thể hiện `HTTP/1.1 201 Created` và header `Location`; `response-headers.adoc` giải thích ý nghĩa `Location`; trang cuối bổ sung rằng client có thể dùng URI đó để truy cập tài nguyên vừa tạo. Không nên kỳ vọng raw snippet tự cung cấp giải thích nghiệp vụ.

## 4. Quy trình đọc raw snippets sau khi chạy test

Một quy trình review có thể đi theo thứ tự sau:

~~~mermaid
flowchart TD
    A["Chạy HTTP test"] --> B{"Test và assertions pass?"}
    B -->|Không| C["Điều tra lỗi, không publish"]
    B -->|Có| D["Tìm output directory và identifier"]
    D --> E["Đọc raw request / response"]
    E --> F["Đọc descriptor tables"]
    F --> G["Đối chiếu contract, fixture và assertions"]
    G --> H{"Snippet chính xác và an toàn?"}
    H -->|Không| I["Sửa test, descriptor hoặc preprocessor"]
    I --> A
    H -->|Có| J["Include vào tài liệu cuối"]
    J --> K["Render và review trang tài liệu"]
    K --> L["Publish theo CI"]
~~~

Nên xem những phần sau theo thứ tự:

1. **Đúng operation:** thư mục có đúng identifier không? Có trùng identifier với test khác không?
2. **Request:** method, URI, query, path, headers và body có đúng với lời gọi test không?
3. **Response:** status, headers và body có đúng với những gì test đã nhận không?
4. **Descriptor:** các field/header/parameter cần giải thích có được ghi đầy đủ và đúng tên không?
5. **Tính ổn định và bảo mật:** có host nội bộ, token, cookie, timestamp, ID ngẫu nhiên hoặc dữ liệu riêng tư không?
6. **Tài liệu cuối:** include đúng identifier, đúng snippet và đúng heading không?

Raw snippets nên được review sau khi task test hiện tại hoàn thành và trước khi bước render/publish tài liệu chạy.

## 5. Đọc raw request: method, URI, headers và body

Giả sử test tạo đơn hàng:

~~~java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Id", "docs-001")
        .content("""
            {"productId":"BOOK-42","quantity":2}
            """))
    .andExpect(status().isCreated())
    .andDo(document("orders-create"));
~~~

Một `http-request.adoc` minh họa có thể là:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Request-Id: docs-001

{"productId":"BOOK-42","quantity":2}
~~~

Khi đọc file thực tế, đối chiếu từng thành phần:

| Thành phần | Nguồn trong test | Điều cần xác minh |
| --- | --- | --- |
| Method `POST` | `post("/api/orders")` | Đúng HTTP method endpoint công bố. |
| Path `/api/orders` | URI được request builder tạo | Đúng route và version prefix. |
| Query string | `queryParam(...)` hoặc URI có query | Có đủ tên, giá trị và encoding cần thiết. |
| `Content-Type` | `contentType(...)` | Body được khai báo đúng media type. |
| `Accept` | `accept(...)` | Media type client chấp nhận đúng contract. |
| Custom headers | `header(...)` | Tên và giá trị có ý nghĩa, không chứa secret. |
| Body | `content(...)` / `bodyValue(...)` / `body(...)` | Payload đúng cấu trúc, kiểu dữ liệu và giá trị mẫu. |

Nếu test gửi `quantity` là số nhưng raw body hiển thị `"quantity":"2"`, cần kiểm tra serialization và cách dựng body. Nếu request là GET không body nhưng snippet lại có body, hãy xác định test/client/preprocessor đã tạo gì trước khi quyết định nội dung đó có được phép theo contract hay không.

### 5.1. Request target và URI công khai

Với MockMvc, request có thể chạy trong tiến trình và không mở HTTP server thật. REST Docs có thể trình bày URL theo URI cấu hình riêng; vì vậy host `api.example.com` trong `curl-request.adoc` không chứng minh endpoint đó đang tồn tại ngoài môi trường test.

Nếu raw snippet hiển thị host nội bộ hoặc port ngẫu nhiên, kiểm tra cấu hình URI hoặc preprocessor. Chỉ thay host theo cách có chủ đích cho tài liệu công khai; đừng thay đổi raw source để che mất môi trường test mà reviewer cần biết.

### 5.2. Raw request body khác request fields

`request-body.adoc` hiển thị payload; `request-fields.adoc` là bảng descriptors. Ví dụ:

~~~json
{"productId":"BOOK-42","quantity":2}
~~~

Bảng mô tả có thể là:

| Field | Description |
| --- | --- |
| `productId` | Mã sản phẩm cần đặt. |
| `quantity` | Số lượng sản phẩm. |

Nếu raw body có thêm field `campaignCode` nhưng strict descriptor chưa mô tả, snippet generation có thể fail. Khi review, cần quyết định field mới có thuộc hợp đồng công khai hay chỉ là metadata test; không tùy tiện chuyển sang relaxed mode mà không hiểu thay đổi.

## 6. Đọc raw response: status, headers và body

Giả sử test mong đợi tạo đơn thành công:

~~~java
.andExpect(status().isCreated())
.andExpect(header().string(HttpHeaders.LOCATION, "/api/orders/102"))
.andExpect(jsonPath("$.id").value(102))
.andDo(document("orders-create"));
~~~

Một response snippet minh họa:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/102
Content-Type: application/json

{"id":102,"status":"PENDING"}
~~~

Checklist đối chiếu:

- Status có đúng với assertion và hợp đồng API không?
- `Location` có đúng URI của tài nguyên vừa tạo không?
- `Content-Type` có đúng media type được công bố không?
- Body có phản ánh cấu trúc và dữ liệu mà test đã kiểm tra không?
- Body có xuất hiện trong trường hợp status/method yêu cầu response không body không?
- Có header phát sinh từ môi trường test cần được chuẩn hóa hoặc giải thích không?

**Không suy luận test đã kiểm chứng tất cả chỉ từ raw response.** Nếu test chỉ có `status().isCreated()`, snippet thể hiện response nhưng chưa có nghĩa test đã assertion `Location`, `Content-Type` hay mọi field trong body. Reviewer phải đọc assertions và descriptors liên quan.

### 6.1. Body rỗng phải được giữ rỗng

Các trường hợp như `204 No Content`, `304 Not Modified` và response của `HEAD` không có body theo ngữ nghĩa HTTP. Snippet thô có thể chỉ hiển thị status và headers:

~~~http
HTTP/1.1 204 No Content
~~~

Nếu tài liệu cuối include `response-body.adoc` cho một response như vậy và sinh ra một khối JSON tưởng tượng, cần kiểm tra lại identifier và source. Không thêm payload chỉ để làm trang tài liệu trông đồng đều.

### 6.2. Status khác nhau cần identifier khác nhau

Không dùng chung một identifier cho response `200` và `404` của cùng endpoint. Nên có các operation riêng như:

~~~text
orders-get-success/
orders-get-not-found/
~~~

Khi include, tiêu đề nên nêu rõ tình huống thành công hay lỗi. Điều này giúp người đọc không nhầm một response mẫu với mọi kết quả có thể có của endpoint.

## 7. Đọc các descriptor snippets

Raw request/response cho biết dữ liệu đã ghi nhận. Các descriptor snippets giúp review xem **những phần quan trọng đã được mô tả chưa**.

| Descriptor API | Snippet | Câu hỏi review |
| --- | --- | --- |
| `pathParameters(...)` | `path-parameters.adoc` | Tên path variable và mô tả có đúng URI template không? |
| `queryParameters(...)` | `query-parameters.adoc` | Có đủ tham số, default, giới hạn và optional behavior không? |
| `requestHeaders(...)` | `request-headers.adoc` | Header nào là yêu cầu của client, header nào tùy chọn? |
| `responseHeaders(...)` | `response-headers.adoc` | Header nào ảnh hưởng cách client xử lý response? |
| `requestFields(...)` | `request-fields.adoc` | Payload gửi lên có được giải thích đủ không? |
| `responseFields(...)` | `response-fields.adoc` | Payload trả về có được giải thích đủ không? |
| `requestParts(...)` | `request-parts.adoc` | Multipart part có tên và ý nghĩa đúng không? |
| `formParameters(...)` | `form-parameters.adoc` | Trường form đã được phân biệt với query parameters chưa? |

### 7.1. Header descriptor không giống header raw

Raw `http-request.adoc` có thể chứa nhiều headers, bao gồm những header do client hoặc môi trường tự thêm. `request-headers.adoc` chỉ trình bày các headers đã được khai báo qua descriptors hoặc cơ chế tương ứng. Việc header không xuất hiện trong bảng không tự chứng minh raw request không có header đó.

Tương tự, `response-headers.adoc` là bảng giải thích những header được chọn; nó không nhất thiết là danh sách đầy đủ mọi header server đã trả. Với giá trị quan trọng, cần assertion cụ thể trong test.

### 7.2. Descriptor strict, optional và relaxed

Với field descriptors, chế độ strict giúp phát hiện field chưa được mô tả hoặc field bắt buộc không xuất hiện. `optional()` cho phép field có thể vắng mặt; `ignored()` loại một field khỏi bảng theo chủ đích; `relaxed...Fields(...)` bỏ qua field bổ sung chưa mô tả trong khi vẫn giữ yêu cầu với descriptors đã khai báo.

Khi raw snippet và descriptor table mâu thuẫn, không sửa bảng chỉ để test pass. Hãy xác định payload mới có phải thay đổi hợp đồng hay là dữ liệu ngoài phạm vi tài liệu, rồi cập nhật test/descriptor tương ứng.

## 8. Đọc snippets CLI và khả năng tái hiện

Các snippet `curl-request.adoc` và `httpie-request.adoc` cung cấp cú pháp để gọi lại request. Khi review, hãy đối chiếu chúng với `http-request.adoc`:

- Method có tương đương không?
- URL và query parameters có giữ đúng giá trị không?
- Header quan trọng có được truyền không?
- Body có đúng media type và dữ liệu không?
- Shell quoting và URL encoding có phù hợp môi trường hướng dẫn không?
- Host là địa chỉ có thể truy cập hay chỉ là URI mẫu của MockMvc?

Lệnh CLI không chứng minh response sẽ giống hệt khi chạy lại. Authentication, database, ID, clock, server state và headers mặc định của client có thể khác. Tài liệu cần chỉ rõ những prerequisite nếu người đọc muốn thực thi lệnh.

Đối với lệnh có tác dụng phụ như POST/PUT/PATCH/DELETE, nêu rõ đây là môi trường và dữ liệu thử. Không khuyến khích chạy lệnh trên production chỉ để kiểm tra snippet.

## 9. Review độ ổn định và tính bảo mật

Raw snippets có thể vô tình chứa dữ liệu không phù hợp để công khai:

| Dữ liệu | Rủi ro | Cách xử lý |
| --- | --- | --- |
| `Authorization` token/API key | Có thể cấp quyền truy cập hệ thống | Dùng fixture giả, thay bằng placeholder hoặc mask trước khi sinh. |
| `Cookie`/session ID | Có thể tái sử dụng phiên đăng nhập | Loại bỏ hoặc thay giá trị; không commit session file. |
| Email/điện thoại/địa chỉ thật | Lộ dữ liệu cá nhân | Dùng dữ liệu synthetic. |
| Host nội bộ/IP/private port | Tiết lộ hạ tầng hoặc làm lệnh không chạy được với độc giả | Chuẩn hóa URL công khai dành cho tài liệu và ghi rõ môi trường. |
| Timestamp/ID ngẫu nhiên | Làm diff tài liệu nhiễu | Dùng fixture ổn định hoặc preprocessor có chủ đích. |
| Stack trace/exception nội bộ | Tiết lộ cấu trúc triển khai | Sửa error response, chỉ công bố thông tin an toàn. |
| File/body nhị phân lớn | Tạo artifact lớn, khó review | Tài liệu hóa metadata, kích thước hoặc checksum thay vì nhúng toàn bộ. |

Preprocessor như `preprocessRequest(...)` và `preprocessResponse(...)` có thể format, loại hoặc thay giá trị trong **bản ghi tạo snippet**. Chúng không thay đổi request/response gốc mà ứng dụng đã xử lý. Nếu xóa header khỏi raw snippet, đừng đồng thời mô tả nó là header hiện diện trong descriptor table.

Với dữ liệu biến thiên, ưu tiên fixture ổn định. Không nên xóa mọi header khác biệt một cách máy móc: một số header có ý nghĩa hợp đồng như `Location`, `ETag`, `Cache-Control` hoặc `Content-Type` cần được giữ và kiểm tra.

## 10. Từ raw snippet tới trang tài liệu cuối

Sau khi review raw snippets và descriptors, biên soạn trang Asciidoctor:

~~~asciidoc
= Orders API

== Tạo đơn hàng

Gửi request JSON để tạo đơn hàng mới. Khi thành công, API trả status 201 và URI của đơn hàng trong Location.

=== HTTP request
include::{snippets}/orders-create/http-request.adoc[]

=== Request fields
include::{snippets}/orders-create/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-create/http-response.adoc[]

=== Response headers
include::{snippets}/orders-create/response-headers.adoc[]

=== Response fields
include::{snippets}/orders-create/response-fields.adoc[]

== Không tìm thấy đơn hàng

Nếu mã đơn hàng không tồn tại, API trả 404.

=== HTTP response
include::{snippets}/orders-get-not-found/http-response.adoc[]
~~~

Tài liệu cuối nên cung cấp ngữ cảnh:

- Mục tiêu endpoint và khi nào dùng.
- Method, path và điều kiện đầu vào.
- Ý nghĩa path/query parameters và request headers.
- Ví dụ request và response được sinh từ test.
- Status có thể trả và cách client xử lý.
- Authentication, prerequisite, giới hạn và lưu ý tác dụng phụ.
- Các lỗi quan trọng cùng cấu trúc body lỗi.

Không cần include mọi snippet mặc định vào mọi trang. Chỉ chọn những snippet giúp người đọc hiểu và gọi API; nhưng các raw snippet cần thiết phải được kiểm tra trước khi đưa vào.

### 10.1. Với Markdown

Cú pháp `include::{snippets}/...[]` là chỉ thị Asciidoctor, không tự động được hỗ trợ bởi mọi Markdown renderer. Nếu tài liệu cuối là Markdown, dự án cần template, plugin hoặc bước chuyển đổi/nhúng snippet phù hợp. Không copy nội dung thủ công nếu có thể tự động sinh hoặc cập nhật; thao tác copy tay dễ làm trang cuối lệch raw snippets ở lần test tiếp theo.

## 11. Tạo quy trình review có thể lặp lại

Một checklist review cho mỗi identifier:

| Bước | Hành động | Kết quả cần đạt |
| --- | --- | --- |
| 1 | Tìm đúng test và identifier | Truy vết được snippet về một operation cụ thể. |
| 2 | Mở `http-request.adoc` | Method, URI, query, headers và body đúng. |
| 3 | Mở `http-response.adoc` | Status, headers và body phản ánh test. |
| 4 | Mở descriptor tables | Field, parameter, header được mô tả đủ và có ý nghĩa. |
| 5 | Đọc assertions trong test | Biết chính xác điều gì được kiểm chứng. |
| 6 | Kiểm tra secret và giá trị biến thiên | Không lộ dữ liệu nhạy cảm; diff ổn định. |
| 7 | Kiểm tra lệnh CLI | URL, quoting, credentials prerequisite và tác dụng phụ rõ ràng. |
| 8 | Include và render tài liệu cuối | Không thiếu snippet, không nhầm identifier, link/heading hợp lý. |
| 9 | Review thay đổi trong diff | Chỉ có thay đổi có chủ đích, không có snippet cũ hoặc dữ liệu rác. |

Với endpoint quan trọng, nên giữ việc review raw snippet như một phần của pull request. Reviewer đọc test và snippet cùng nhau; nếu chỉ xem trang cuối, có thể khó nhận ra nguồn của một payload hoặc header sai.

## 12. Build và CI: tránh snippet cũ

Một lỗi phổ biến là tài liệu build thành công nhờ snippet **còn sót từ lần chạy trước**, dù test hiện tại không sinh chúng nữa. Một pipeline đáng tin cậy cần:

1. Chạy đúng test suite sinh REST Docs snippets.
2. Fail nếu test hoặc assertions thất bại.
3. Quản lý output directory để loại trừ artifact stale theo cách phù hợp với build.
4. Chạy Asciidoctor/Markdown build sau khi snippets đã sẵn sàng.
5. Fail nếu include path sai hoặc snippet bắt buộc thiếu.
6. Review diff và chỉ publish khi cả test lẫn document build thành công.

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Prepare clean snippet output"]
    B --> C["Run HTTP tests"]
    C --> D{"All tests pass?"}
    D -->|No| X["Fail pipeline"]
    D -->|Yes| E["Inspect / validate generated snippets"]
    E --> F["Build Asciidoctor/Markdown"]
    F --> G{"All includes and render pass?"}
    G -->|No| X
    G -->|Yes| H["Review artifact / diff"]
    H --> I["Publish documentation"]
~~~

Tên task và cách xóa output directory phụ thuộc Gradle/Maven, cấu trúc multi-module và cách dự án lưu generated files. Hãy cấu hình dependency rõ ràng để task tài liệu không chạy trước test. Không xóa thủ công thư mục build bằng một thao tác không được build tool quản lý nếu việc đó làm mất dữ liệu người khác cần.

### 12.1. Khi snippet thay đổi trong pull request

Một thay đổi hợp lệ có thể khiến nhiều raw snippet thay đổi, ví dụ:

- Đổi endpoint path hoặc API version.
- Thêm/bỏ request field hoặc response field.
- Thay status từ `200` sang `202` theo hợp đồng mới.
- Thêm header `ETag` hoặc `Location`.
- Chỉnh fixture, serializer hoặc preprocessor.
- Thay đổi identifier của operation.

Reviewer nên xác định thay đổi này có được phản ánh trong API code, test, descriptor và phần giải thích tài liệu cuối không. Nếu chỉ có raw snippet đổi mà không có lý do code/test đi kèm, cần điều tra trước khi merge.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy thư mục snippet | Test chưa chạy, identifier khác hoặc output directory khác | Kiểm tra cấu hình và test thực sự được thực thi. |
| Snippet có nội dung từ test cũ | Output directory còn artifact stale hoặc identifier bị dùng lại | Quản lý output theo build; đảm bảo identifier duy nhất. |
| Request snippet khác với test mong đợi | Test builder, query, header hoặc body được dựng khác giả định | Đối chiếu lời gọi test với `http-request.adoc`. |
| Response snippet status khác tài liệu | Endpoint thực tế trả status khác hoặc tài liệu dùng nhầm identifier | Dùng assertion cụ thể; include đúng operation. |
| Raw response đúng nhưng fields table thiếu | Chưa khai báo descriptor hoặc dùng nhầm identifier | Thêm descriptor và chạy lại test. |
| Descriptor table có header nhưng raw snippet thiếu | Header không được gửi/trả hoặc đã bị preprocessor xóa | Kiểm tra test và preprocess order. |
| JSON body thay đổi thứ tự/format | Serializer hoặc preprocessor thay đổi cách trình bày | So sánh cấu trúc và contract; chỉ so bytes khi contract yêu cầu. |
| Snippet chứa token/cookie thật | Test fixture dùng secret hoặc thiếu masking | Dùng dữ liệu giả, thay/loại header và tái sinh snippet. |
| URL raw snippet trỏ host nội bộ | URI test hoặc cấu hình tài liệu dùng host riêng | Chuẩn hóa URI hiển thị và giải thích môi trường thực thi. |
| Asciidoctor thiếu include | Identifier/path sai hoặc snippet chưa sinh | Chạy test trước và sửa include path. |
| Tài liệu cuối khác raw snippet | Copy thủ công hoặc build không tự động include | Dùng include/template và review generated diff. |

## 14. Bài thực hành

Giả sử API quản lý đơn hàng có hai operation:

- `POST /api/orders`: request gồm `customerId` và `items[]`; trả `201 Created` với `Location` và JSON body.
- `GET /api/orders/101`: trả `200 OK`, `Content-Type: application/json` và payload đơn hàng.

Thực hiện:

1. Viết hai HTTP tests và assertion cho status, headers, các field quan trọng.
2. Dùng identifier riêng `orders-create` và `orders-get-success`.
3. Chạy test; mở output directory và đọc `http-request.adoc`, `http-response.adoc`, `request-fields.adoc`, `response-fields.adoc`, `request-headers.adoc` và `response-headers.adoc` nếu có.
4. Đối chiếu raw snippets với code test: method, URI, media type, headers, body, status và các giá trị mẫu.
5. Cố ý thêm một field vào payload mà chưa mô tả; quan sát strict descriptor phát hiện thay đổi, rồi quyết định cập nhật contract/tài liệu hay bỏ qua field có chủ đích.
6. Kiểm tra snippet có dữ liệu nhạy cảm hoặc giá trị ngẫu nhiên; dùng fixture giả/preprocessor để tạo output an toàn và ổn định.
7. Include đúng snippets vào trang Asciidoctor, render tài liệu và review diff.
8. Thử làm test thất bại hoặc bỏ một identifier để xác nhận pipeline không publish từ artifact cũ.

**Tiêu chí hoàn thành:** truy vết được raw snippet tới test; xác nhận request/response và descriptor tables đúng; phát hiện dữ liệu thiếu, stale hoặc nhạy cảm; biên soạn trang cuối từ snippet đã review; và CI chỉ publish khi test lẫn document build đạt.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Asciidoctor — Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
