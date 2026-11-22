# Viết tài liệu Markdown với nhiều operation

## 1. Mục tiêu bài thực hành

Một API thực tế có nhiều operation cùng thuộc một resource: liệt kê, xem chi tiết, tạo, cập nhật, xóa và tìm kiếm. Mỗi operation sinh một nhóm snippet riêng từ documentation test. Bài này hướng dẫn tổ chức các snippet đó thành tài liệu Markdown thống nhất, có cấu trúc dễ đọc và có thể build lại trong CI.

Spring REST Docs tạo snippet có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured. Test xác nhận request/response và descriptors; tài liệu Markdown tập hợp kết quả để người dùng API tra cứu. Trọng tâm là thiết kế bố cục cho nhiều operation, quản lý include path, tránh trùng lặp và kiểm tra các snippet được tham chiếu đều tồn tại.

## 2. Lập danh mục operation

Trước khi viết tài liệu, lập bảng inventory để biết mỗi operation cần snippet nào:

| Operation ID | Method và endpoint | Request snippets | Response snippets |
| --- | --- | --- | --- |
| products-list | GET /api/products | http-request, query-parameters | http-response, response-fields |
| products-get | GET /api/products/{id} | http-request, path-parameters | http-response, response-fields |
| products-create | POST /api/products | http-request, request-fields | http-response, response-fields |
| products-update | PATCH /api/products/{id} | http-request, path-parameters, request-fields | http-response, response-fields |
| products-delete | DELETE /api/products/{id} | http-request, path-parameters | http-response |

Đây là inventory mẫu. Tên operation ID phải khớp chuỗi truyền cho document(...) trong test. Không tự thêm include cho snippet mà operation không tạo.

Với mỗi operation, xác định HTTP method và URI, path/query parameters, headers, request body, response status/media type, response body và các field/links được mô tả. Inventory là hợp đồng giữa documentation tests và tài liệu biên soạn.

## 3. Chọn cấu trúc một trang Markdown

Với API nhỏ hoặc vừa, một file Markdown có thể tổ chức như sau:

~~~text
product-api.md
├── Giới thiệu
├── Quy ước chung
├── Authentication và headers
├── Products
│   ├── Liệt kê sản phẩm
│   ├── Xem sản phẩm
│   ├── Tạo sản phẩm
│   ├── Cập nhật sản phẩm
│   └── Xóa sản phẩm
├── Mã lỗi
└── Chạy documentation tests
~~~

Đặt nội dung chung ở đầu trang để không phải lặp lại ở từng operation. Trong mỗi operation, giữ thứ tự nhất quán: mục đích; request line và parameters; request headers/body; response status/headers; response fields hoặc links; lỗi liên quan.

Với API lớn, tách theo resource hoặc bounded context thành nhiều file. Chọn ranh giới theo cách người dùng API tìm thông tin.

## 4. Quy ước snippet output

Spring REST Docs ghi snippet theo operation identifier trong output directory, ví dụ:

~~~text
build/generated-snippets/
├── products-list/
│   ├── http-request.adoc
│   ├── query-parameters.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
├── products-get/
│   ├── http-request.adoc
│   ├── path-parameters.adoc
│   ├── http-response.adoc
│   └── response-fields.adoc
└── products-create/
    ├── http-request.adoc
    ├── request-fields.adoc
    ├── http-response.adoc
    └── response-fields.adoc
~~~

Tên snippet và phần mở rộng phụ thuộc snippet được cấu hình và template format. Asciidoctor thường sinh file .adoc; Markdown format có thể sinh file .md. Chọn operation ID ổn định, dễ hiểu và duy nhất để tránh ghi đè output.

## 5. Include snippet vào tài liệu

Nếu dự án dùng Asciidoctor để xử lý include, cú pháp là:

~~~adoc
include::{snippets}/products-get/http-request.adoc[]
~~~

Ví dụ trang AsciiDoc tập hợp nhiều operation:

~~~adoc
= Product API
:toc:
:sectnums:

== Giới thiệu

API quản lý vòng đời sản phẩm trong catalog.

== Liệt kê sản phẩm

=== Request
include::{snippets}/products-list/http-request.adoc[]
include::{snippets}/products-list/query-parameters.adoc[]

=== Response
include::{snippets}/products-list/http-response.adoc[]
include::{snippets}/products-list/response-fields.adoc[]

== Xem sản phẩm

=== Request
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]

=== Response
include::{snippets}/products-get/http-response.adoc[]
include::{snippets}/products-get/response-fields.adoc[]

== Tạo sản phẩm

=== Request
include::{snippets}/products-create/http-request.adoc[]
include::{snippets}/products-create/request-fields.adoc[]

=== Response
include::{snippets}/products-create/http-response.adoc[]
include::{snippets}/products-create/response-fields.adoc[]
~~~

Ví dụ dùng AsciiDoc làm nguồn để Asciidoctor resolve snippet. Nếu đầu ra cuối là Markdown thuần, cần dùng cơ chế include của static site generator hoặc script build. Không giả định mọi Markdown renderer tự hiểu cú pháp include của Asciidoctor.

## 6. Tổ chức Markdown thuần

Markdown thuần không có cú pháp include snippet chuẩn chung cho mọi renderer. Có hai cách thường dùng:

1. Dùng Markdown làm tài liệu biên soạn thủ công và đồng bộ nội dung snippet sau khi test sinh ra. Nếu copy thủ công, cần bước kiểm tra drift để tránh nội dung cũ.
2. Sinh Markdown bằng task/script đọc snippet output rồi ghép vào placeholder theo operation ID. Script phải báo lỗi khi thiếu file bắt buộc, không âm thầm bỏ qua include.

Ví dụ bố cục sau khi snippet được chèn:

~~~markdown
# Product API

## Giới thiệu

API quản lý sản phẩm trong catalog.

## Liệt kê sản phẩm

### Request

#### HTTP request

Nội dung được đồng bộ từ products-list/http-request.

#### Query parameters

Nội dung được đồng bộ từ products-list/query-parameters.

### Response

Nội dung được đồng bộ từ products-list/http-response và response-fields.
~~~

Các dòng mô tả trên là vị trí minh họa. Trong tài liệu phát hành, thay chúng bằng nội dung snippet thật hoặc link tới artifact đã publish.

## 7. Heading, mục lục và anchor

Đặt heading nhất quán cho từng operation:

~~~markdown
## Liệt kê sản phẩm
## Xem sản phẩm
## Tạo sản phẩm
## Cập nhật sản phẩm
## Xóa sản phẩm
~~~

Ví dụ mục lục:

~~~markdown
## Mục lục

- [Liệt kê sản phẩm](#liet-ke-san-pham)
- [Xem sản phẩm](#xem-san-pham)
- [Tạo sản phẩm](#tao-san-pham)
- [Cập nhật sản phẩm](#cap-nhat-san-pham)
- [Xóa sản phẩm](#xoa-san-pham)
~~~

Quy tắc tạo anchor từ heading có thể khác giữa renderer. Kiểm tra link trên nền tảng phát hành; nếu cần ổn định giữa nhiều renderer, dùng explicit anchor theo công cụ đang sử dụng.

## 8. Giữ phần dùng chung ở cấp tài liệu

Một trang nhiều operation thường có quy tắc áp dụng toàn API: base URL/version, authentication scheme, content types, timestamp format, currency, error format, pagination và correlation ID.

Ví dụ:

~~~markdown
## Quy ước chung

- Base path: `/api`.
- Request và response JSON dùng `application/json`.
- Thời gian dùng ISO-8601 UTC.
- Giá tiền đi kèm field `currency`.
- Lỗi validation dùng error code ổn định.
~~~

Chỉ ghi quy ước đã được xác nhận trong hợp đồng API hoặc test. Nếu một operation có ngoại lệ, ghi rõ ngay trong mục operation đó.

## 9. Đồng bộ operation ID với documentation tests

Tên operation ID được dùng ở cả test và tài liệu:

~~~java
mockMvc.perform(get("/api/products/{id}", "p-42"))
        .andExpect(status().isOk())
        .andDo(document("products-get",
                pathParameters(
                        parameterWithName("id").description("Mã sản phẩm"))));
~~~

Tài liệu tham chiếu cùng identifier:

~~~adoc
include::{snippets}/products-get/http-request.adoc[]
include::{snippets}/products-get/path-parameters.adoc[]
include::{snippets}/products-get/http-response.adoc[]
~~~

Khi đổi products-get thành tên khác, sửa mọi include tham chiếu identifier cũ. Không cần tạo response-fields snippet cho DELETE trả 204 vì response không có body.

## 10. Kiểm tra include path

Build tài liệu nên thất bại nếu snippet bắt buộc không tồn tại. Với Asciidoctor, include thiếu thường khiến build báo lỗi; tránh cấu hình cho phép include thiếu nếu tài liệu cần đầy đủ.

Nếu dùng task/script ghép Markdown, kiểm tra từng file trước khi ghi output:

~~~text
for each operation in inventory:
    for each required snippet:
        verify file exists
        append snippet content
    if file missing:
        fail documentation task
~~~

Đây là pseudocode. Script thực tế cần đọc UTF-8, resolve đúng output directory và trả lỗi có operation ID cùng tên snippet bị thiếu.

Các lỗi cần phát hiện gồm sai operation ID, sai tên snippet, sai phần mở rộng, include trỏ output directory cũ, test chưa chạy và snippet bị include lặp ngoài ý muốn.

## 11. Tích hợp vào Gradle và CI

Quy trình tổng quát:

~~~text
Clean generated snippets
          |
          v
Run documentation tests
          |
          v
Verify operation inventory
          |
          v
Resolve or assemble Markdown includes
          |
          v
Build documentation artifact
          |
          v
Publish or archive
~~~

Nếu dùng Asciidoctor:

~~~groovy
tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir layout.buildDirectory.dir('generated-snippets')
}
~~~

Nếu dùng Markdown thuần, tạo task riêng phụ thuộc test và khai báo generated snippets là input, Markdown assembled file là output. Điều này giúp Gradle hiểu dependency và chỉ chạy lại task khi input thay đổi. Đảm bảo task không đọc output cũ sau lần test thất bại.

Trong CI, lưu HTML hoặc Markdown artifact cùng build để reviewer so sánh khi operation hoặc template thay đổi. Chỉ publish sau khi documentation tests và bước kiểm tra include đều thành công.

## 12. Kiểm tra tính nhất quán giữa các operation

| Kiểm tra | Câu hỏi |
| --- | --- |
| Tên operation | Heading có nói rõ hành động và resource không? |
| HTTP method/path | Có khớp controller và test không? |
| Parameters | Path/query parameters có mô tả đủ và đúng optional không? |
| Request body | Chỉ liệt kê field client thực sự gửi không? |
| Response | Status, media type và body có khớp test không? |
| Error cases | Lỗi quan trọng có ví dụ và schema không? |
| Snippet includes | Tất cả đường dẫn có tồn tại sau documentation tests không? |
| Shared conventions | Quy tắc chung có bị lặp hoặc mâu thuẫn không? |

Không sao chép nguyên descriptor chỉ vì hai operation có field cùng tên. Required/optional và ngữ nghĩa của field phải phản ánh đúng từng endpoint.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Một mục operation thiếu response | Chưa include http-response hoặc response-fields | Đối chiếu inventory và output folder |
| Markdown renderer hiển thị nguyên include directive | Renderer không hỗ trợ cú pháp Asciidoctor | Dùng Asciidoctor hoặc task chuyển snippet sang Markdown |
| Include không tìm thấy file | Sai operation ID, tên snippet hoặc extension | So sánh với generated-snippets |
| Nội dung operation bị lặp | Include cùng snippet nhiều lần | Kiểm tra bố cục và danh sách include |
| Anchor mục lục không hoạt động | Renderer tạo slug khác dự kiến | Kiểm tra anchor trên nền tảng phát hành |
| Tài liệu còn snippet cũ | Output directory không được clean | Clean output và khai báo input/output đúng |
| Một operation dùng thuật ngữ khác | Descriptor bị khai báo riêng không thống nhất | Tái sử dụng factory cho ngữ nghĩa thật sự chung |
| DELETE include response-fields nhưng file không tồn tại | Operation không có response body | Bỏ include field snippet và mô tả status 204 |

## 14. Bài tập capstone

Tạo một tài liệu Product API nhiều operation:

1. Viết phần giới thiệu, base path, authentication và content type.
2. Lập operation inventory cho list, get, create, update và delete.
3. Viết documentation tests có identifier ổn định cho từng operation.
4. Include request, parameters, request fields, response và response fields phù hợp.
5. Tạo mục lục và anchor tới từng operation.
6. Thêm mục error responses và quy ước pagination dùng chung.
7. Dùng Asciidoctor include hoặc task assemble Markdown để tạo tài liệu cuối.
8. Thêm bước kiểm tra mọi snippet bắt buộc tồn tại.
9. Chạy build sạch trong CI và lưu artifact.

**Tiêu chí hoàn thành:** mọi operation có mục tài liệu; include khớp identifier và file được sinh; phần chung không lặp; operation không có body không tham chiếu response-fields; navigation hoạt động trên renderer đích; build thất bại khi thiếu snippet bắt buộc.

## 15. Checklist trước khi đưa vào CI

- [ ] Có operation inventory với method, path, identifier và snippet cần thiết.
- [ ] Identifier trong document(...) khớp include path.
- [ ] Mỗi operation có heading và thứ tự nội dung thống nhất.
- [ ] Base URL, authentication và content types được viết một lần ở cấp tài liệu.
- [ ] Query/path parameters và request/response fields đúng contract.
- [ ] Không include snippet không được sinh.
- [ ] Markdown renderer hỗ trợ cơ chế include đã chọn.
- [ ] Anchor và mục lục được kiểm tra trên renderer mục tiêu.
- [ ] Task biên soạn phụ thuộc documentation tests.
- [ ] CI làm sạch output cũ, kiểm tra include và lưu artifact cuối.

**Ghi nhớ:** Tài liệu Markdown nhiều operation cần inventory rõ ràng, cấu trúc mục nhất quán và cơ chế đồng bộ snippet đáng tin cậy. Dùng operation ID ổn định, chỉ include file thực sự được sinh và để CI kiểm tra include path sẽ giúp tài liệu tổng hợp theo sát HTTP tests.
