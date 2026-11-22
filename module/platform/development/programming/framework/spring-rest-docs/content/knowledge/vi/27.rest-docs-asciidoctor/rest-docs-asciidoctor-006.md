# Nhúng từng snippet riêng lẻ

## 1. Vì sao cần include từng snippet?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ HTTP tests bằng MockMvc, WebTestClient hoặc REST Assured. Mỗi operation được ghi nhận bằng `document("operation-id", ...)` và có thể sinh nhiều snippet riêng: request/response, headers, parameters, fields, links hoặc ví dụ lệnh client.

Asciidoctor cung cấp macro `include::` để nhúng một file snippet tại đúng vị trí trong tài liệu. Thay vì include toàn bộ snippet của operation bằng `operation::id[]`, người viết có thể chọn chính xác file nào cần xuất hiện, đặt tiêu đề tiếng Việt riêng và thêm phần giải thích sát với từng ví dụ.

Ví dụ:

```asciidoc
== Lấy sách theo ID

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

Cách include riêng phù hợp khi:

- Muốn sắp xếp request, headers, parameters, response và fields theo luồng đọc cụ thể.
- Cần giải thích ý nghĩa hoặc điều kiện nghiệp vụ ngay trước/sau một snippet.
- Chỉ muốn công bố một phần output được sinh ra.
- Muốn đặt title, anchor, admonition hoặc cross-reference riêng cho từng phần.
- Cần kết hợp snippet tự sinh với ví dụ, bảng hoặc hướng dẫn do người viết quản lý.

## 2. Cú pháp cơ bản và attribute `snippets`

Cú pháp include một snippet:

```asciidoc
include::{snippets}/<operation-id>/<snippet-name>.adoc[]
```

Trong đó:

| Thành phần | Ý nghĩa |
| --- | --- |
| `{snippets}` | Attribute trỏ tới thư mục gốc chứa generated snippets. |
| `<operation-id>` | Identifier truyền vào `document("...", ...)` trong HTTP test. |
| `<snippet-name>.adoc` | Tên file snippet thực tế, ví dụ `http-request.adoc`. |
| `[]` | Phần tùy chọn của include macro; để rỗng khi không cần thuộc tính bổ sung. |

Ví dụ operation trong test:

```java
filter(document("books-get",
        pathParameters(
                parameterWithName("id").description("Mã sách")),
        responseFields(
                fieldWithPath("id").description("Mã sách"),
                fieldWithPath("title").description("Tên sách"))))
```

Test tạo snippet dưới thư mục operation `books-get`. Nếu dùng Gradle convention phổ biến, đường dẫn đầy đủ là `build/generated-snippets/books-get/`; với Maven thường là `target/generated-snippets/books-get/`.

Khi `spring-restdocs-asciidoctor` được nạp đúng vào Asciidoctor plugin, extension có thể cung cấp attribute `snippets` theo build tool. Nếu dự án không dùng extension hoặc cần custom output directory, cấu hình attribute từ build hoặc trong file nguồn:

```asciidoc
:snippets: ../../build/generated-snippets
```

Không khai báo một đường dẫn tuyệt đối phụ thuộc máy cá nhân. Quan trọng là nơi test ghi snippet và giá trị `{snippets}` phải trỏ cùng một thư mục.

## 3. Include request và response

Hai snippet cơ bản thường là `http-request.adoc` và `http-response.adoc`:

```asciidoc
== Lấy sách theo ID

=== Request
include::{snippets}/books-get/http-request.adoc[]

=== Response
include::{snippets}/books-get/http-response.adoc[]
```

`http-request.adoc` thể hiện method, URI, headers và body của request đã được test ghi nhận. `http-response.adoc` thể hiện status, response headers và body. Hai snippet này cung cấp bức tranh HTTP hoàn chỉnh trước khi người đọc xem bảng mô tả chi tiết.

Có thể thêm giải thích giữa các phần:

```asciidoc
=== Request
Client gửi GET tới URI của sách. ID được truyền trong path.

include::{snippets}/books-get/http-request.adoc[]

=== Response
Khi tìm thấy sách, server trả HTTP 200 và representation JSON.

include::{snippets}/books-get/http-response.adoc[]
```

Phần mô tả phải khớp hành vi được test xác nhận. Không viết status hoặc payload trong lời giải thích khác với snippet thực tế.

## 4. Include headers riêng

Spring REST Docs có thể tạo `request-headers.adoc` và `response-headers.adoc` khi test khai báo descriptor headers. Include chúng ở phần riêng nếu người đọc cần tra cứu nhanh:

```asciidoc
=== Request headers
include::{snippets}/books-create/request-headers.adoc[]

=== Response headers
include::{snippets}/books-create/response-headers.adoc[]
```

Ví dụ test descriptor:

```java
filter(document("books-create",
        requestHeaders(
                headerWithName("Content-Type")
                        .description("Định dạng payload gửi lên"),
                headerWithName("Accept")
                        .description("Định dạng response client chấp nhận")),
        responseHeaders(
                headerWithName("Content-Type")
                        .description("Định dạng response"),
                headerWithName("Location")
                        .description("URI của sách vừa được tạo"))))
```

Không phải mọi operation đều sinh header snippet. Nếu test không truyền `requestHeaders(...)` hoặc `responseHeaders(...)`, file tương ứng có thể không tồn tại. Chỉ include những file thực sự được tạo; không giả định tất cả operation đều có tất cả loại snippet.

## 5. Include path/query parameters và request parameters

Đường dẫn parameter snippet phụ thuộc loại descriptor đã khai báo trong test:

```asciidoc
=== Path parameters
include::{snippets}/books-get/path-parameters.adoc[]

=== Query parameters
include::{snippets}/books-list/query-parameters.adoc[]

=== Request parameters
include::{snippets}/legacy-search/request-parameters.adoc[]
```

Ví dụ:

```java
filter(document("books-list",
        queryParameters(
                parameterWithName("page").description("Trang cần lấy"),
                parameterWithName("size").description("Số phần tử mỗi trang"))))
```

Path parameters, query parameters và request parameters là các nhóm khác nhau. Dùng đúng snippet tương ứng với descriptor của test. Với form parameter hoặc multipart request, tên file và loại descriptor có thể khác tùy API Spring REST Docs được sử dụng; hãy kiểm tra generated directory thay vì tự đoán filename.

## 6. Include request/response body và field tables

Body snippet hiển thị payload thực tế; field snippet mô tả cấu trúc và ý nghĩa của từng field. Có thể đặt cả hai theo thứ tự:

```asciidoc
=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response body
include::{snippets}/books-create/response-body.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
```

Hai loại snippet không thay thế nhau:

| Snippet | Nội dung |
| --- | --- |
| `request-body.adoc` | Payload request mẫu được ghi lại. |
| `request-fields.adoc` | Bảng field request và mô tả. |
| `response-body.adoc` | Payload response mẫu được ghi lại. |
| `response-fields.adoc` | Bảng field response và mô tả. |

Khi payload dài, phần body có thể cung cấp ví dụ JSON để copy; bảng fields giúp hiểu kiểu và ý nghĩa của field. Nếu tài liệu cần gọn, có thể chỉ include một trong hai nhưng phải bảo đảm người tích hợp vẫn có đủ thông tin để sử dụng API.

## 7. Include hypermedia links riêng

Với response HAL hoặc Atom, `links.adoc` mô tả relation và ý nghĩa của các liên kết. Có thể đặt cạnh HTTP response:

```asciidoc
=== HTTP response
include::{snippets}/orders-get/http-response.adoc[]

=== Link relations
include::{snippets}/orders-get/links.adoc[]
```

`http-response.adoc` giữ `href` và metadata trong payload; `links.adoc` cung cấp bảng relation/description. Nếu operation không dùng `links(...)` trong test hoặc không có link được extractor nhận diện, file `links.adoc` có thể không được sinh.

## 8. Tổ chức một operation hoàn chỉnh bằng include riêng

Ví dụ cấu trúc một trang tạo sách:

```asciidoc
== Tạo sách

Endpoint tạo một tài nguyên mới. Client gửi JSON body; server trả HTTP 201
và header Location trỏ tới tài nguyên vừa tạo.

=== Request
include::{snippets}/books-create/http-request.adoc[]

=== Request headers
include::{snippets}/books-create/request-headers.adoc[]

=== Request body
include::{snippets}/books-create/request-body.adoc[]

=== Request fields
include::{snippets}/books-create/request-fields.adoc[]

=== Response
include::{snippets}/books-create/http-response.adoc[]

=== Response headers
include::{snippets}/books-create/response-headers.adoc[]

=== Response fields
include::{snippets}/books-create/response-fields.adoc[]
```

Đây là cấu trúc minh họa. Chỉ giữ các include mà test thực sự sinh ra. Nếu test không khai báo header descriptors, bỏ phần header table; nếu endpoint không có request body, bỏ request body và request fields.

## 9. Tạo anchor và liên kết tới snippet cụ thể

Khi include từng snippet, có thể đặt anchor để cross-reference từ phần khác:

```asciidoc
[[books_get_request]]
=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

[[books_get_response]]
=== HTTP response
include::{snippets}/books-get/http-response.adoc[]
```

Liên kết từ nơi khác:

```asciidoc
Xem ví dụ <<books_get_request, request lấy sách>> và
<<books_get_response, response trả về>>.
```

Anchor giúp người đọc chuyển trực tiếp đến đoạn request hoặc response cần tra cứu. Dùng tên anchor ổn định, duy nhất trong toàn tài liệu; không dùng lại cùng một anchor cho nhiều operation.

## 10. Điều chỉnh cách trình bày quanh snippet

Vì mỗi snippet được include riêng, người viết có thể kiểm soát heading và nội dung bao quanh:

```asciidoc
=== Request headers

Header `If-None-Match` cho phép client gửi validator đang có để kiểm tra
resource có thay đổi hay không.

include::{snippets}/books-get/request-headers.adoc[]

NOTE: Client chỉ gửi header này khi đã lưu ETag của lần đọc trước.
```

Có thể sử dụng table, admonition, list, source block hoặc cross-reference. Tuy nhiên, không nên sửa nội dung snippet sinh tự động sau mỗi lần test; hãy chỉnh test descriptor, preprocessor hoặc template nếu nội dung generated cần thay đổi.

Nếu cần thay đổi title/level hoặc định dạng của bảng, include tường minh giúp đặt heading và thuộc tính AsciiDoc quanh file. Một snippet có cấu trúc riêng như table có thể mang thuộc tính mặc định trong chính file được sinh; kiểm tra output trước khi thêm thuộc tính để tránh tạo markup không hợp lệ.

## 11. Chọn lọc snippet thay vì include tất cả

Không cần include mọi snippet cho mọi endpoint. Chọn theo câu hỏi mà người đọc cần trả lời:

| Operation | Snippet thường hữu ích |
| --- | --- |
| `GET /books/{id}` | `http-request`, `path-parameters`, `http-response`, `response-fields`. |
| `GET /books?page=...` | `http-request`, `query-parameters`, `http-response`, `response-fields`. |
| `POST /books` | `http-request`, `request-fields`, `http-response`, `response-headers`, `response-fields`. |
| `PATCH /books/{id}` | `http-request`, `path-parameters`, `request-fields`, `http-response`. |
| Hypermedia resource | `http-response`, `links`, `response-fields`. |

Ví dụ một trang API ngắn có thể chỉ include request, response và fields; phần headers/parameters được đưa vào khi chúng có ý nghĩa riêng. Không include snippet chỉ vì file tồn tại nếu nó không giúp người đọc hiểu hợp đồng.

## 12. Tổ chức nhiều operation thành các file tài liệu riêng

Với API lớn, chia mỗi resource hoặc operation thành file riêng:

```text
src/docs/asciidoc/
├── index.adoc
├── common/
│   └── authentication.adoc
└── operations/
    ├── books-get.adoc
    ├── books-create.adoc
    └── orders-get.adoc
```

File `index.adoc`:

```asciidoc
= Store API
:toc:
:snippets: ../../build/generated-snippets

include::common/authentication.adoc[]

== Books
include::operations/books-get.adoc[]
include::operations/books-create.adoc[]

== Orders
include::operations/orders-get.adoc[]
```

Ví dụ file `operations/books-get.adoc`:

```asciidoc
=== Lấy sách theo ID
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]
```

Đảm bảo attribute `{snippets}` được cấu hình đúng và include trong file lồng nhau được phân giải theo vị trí file chứa include. Trong dự án dùng `spring-restdocs-asciidoctor`, có thể để extension cung cấp attribute thay vì hard-code đường dẫn tương đối.

## 13. Tránh include snippet không tồn tại hoặc output cũ

Include là thao tác đọc file; nó không kiểm tra test đã pass hay chưa. Nếu test không chạy hoặc thất bại sau khi filter đã ghi snippet, file cũ có thể vẫn nằm trong thư mục generated-snippets.

Một số quy tắc hữu ích:

- Clean generated output trước lần build tạo tài liệu.
- Chạy test trước Asciidoctor và chỉ render khi test thành công.
- Dùng identifier riêng cho mỗi scenario, ví dụ `books-get-200` và `books-get-404`.
- Kiểm tra file hiện diện trước khi thêm include mới.
- Không commit chỉnh sửa thủ công bên trong thư mục generated snippets.
- Nếu một snippet không còn được sinh, xóa include hoặc cập nhật test theo hợp đồng mới.

Ví dụ snippet của các status khác nhau:

```asciidoc
== Lấy sách thành công
include::{snippets}/books-get-200/http-response.adoc[]

== Không tìm thấy sách
include::{snippets}/books-get-404/http-response.adoc[]
```

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `include file not found` | Sai `{snippets}`, operation ID hoặc filename. | Kiểm tra thư mục output và tính path từ file `.adoc` hiện tại. |
| Include một loại snippet nhưng file không có | Test chưa khai báo descriptor tương ứng hoặc không sinh snippet đó. | Kiểm tra `document(...)` và output directory; chỉ include file có thật. |
| Request/response hiển thị nhưng field table không có | Chưa dùng `requestFields(...)`/`responseFields(...)`. | Bổ sung descriptor và chạy test lại. |
| Include lặp cùng snippet | Một file được nhúng ở nhiều section hoặc include từ cả macro và thủ công. | Chọn một vị trí chính hoặc giải thích rõ lý do lặp. |
| Nội dung include sai scenario | Identifier trùng hoặc snippet cũ còn lại. | Dùng identifier riêng và clean output. |
| Path đúng trong index nhưng sai ở file operation | Đường dẫn tương đối được tính từ file chứa macro. | Dùng `{snippets}` hoặc tính lại theo vị trí file operation. |
| Title/heading bị lồng sai | Snippet được include trong section có cấp heading không phù hợp. | Điều chỉnh heading bên ngoài và kiểm tra cấu trúc HTML cuối. |
| Tài liệu phát hành dù test đỏ | Asciidoctor/publish không phụ thuộc kết quả test. | Gating task/job: test pass mới render và publish. |

## 15. Checklist thực hành

- [ ] Đã xác định operation identifier từ `document("...")`.
- [ ] Đã kiểm tra generated snippets và chọn đúng tên file cần include.
- [ ] Attribute `{snippets}` trỏ đúng thư mục build hiện tại.
- [ ] Đã include request/response để trình bày trao đổi HTTP hoàn chỉnh.
- [ ] Đã chọn header, parameter, body, field hoặc link snippets theo nhu cầu operation.
- [ ] Đã thêm heading, giải thích, anchor hoặc cross-reference nếu cần.
- [ ] Không include file không tồn tại hoặc snippet từ scenario khác.
- [ ] Identifier riêng cho status/scenario để tránh ghi đè.
- [ ] Build clean, test thành công trước khi Asciidoctor chạy.
- [ ] HTML/PDF cuối có đúng thứ tự, không thiếu include và không lặp nội dung ngoài ý muốn.

Nhúng từng snippet riêng lẻ giúp kiểm soát chính xác nội dung và bố cục tài liệu API. `{snippets}` cung cấp đường dẫn gốc; operation identifier và tên file xác định phần output cần đọc. Khi kết hợp request/response với các bảng headers, parameters, fields và links phù hợp, tài liệu vừa giữ được ví dụ HTTP do test sinh ra vừa giải thích rõ hợp đồng cho người tích hợp.

## Tài liệu tham khảo

- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [Spring REST Docs – Default Snippets](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/default-snippets.html)
- [Spring REST Docs – Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started.html)
- [Asciidoctor – Include Directive](https://docs.asciidoctor.org/asciidoc/latest/directives/include/)
