# Tổ chức nhiều operation trong một file Markdown

## 1. Mục tiêu và bối cảnh

Một REST API thường có nhiều operation trên cùng resource: tạo, đọc, cập nhật, xóa, tìm kiếm và thao tác nghiệp vụ. Nếu mỗi operation nằm ở trang riêng, người đọc phải di chuyển nhiều nơi. Nếu ghép tất cả vào một file Markdown mà không có cấu trúc, trang sẽ dài, khó tìm và dễ include nhầm snippet.

Bài học thuộc chương **Markdown** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippet cho request, response, payload, tham số và header; biên soạn Asciidoctor/Markdown rồi đưa vào build và CI.

Sau bài học, bạn có thể thiết kế trang chứa nhiều operation, đặt heading/anchor ổn định, tổ chức snippet theo identifier, ghép fragment vào trang cuối, tránh collision và xác minh navigation trong CI.

> “Một file Markdown” là một trang tài liệu xuất bản. Nội dung vẫn có thể được assemble từ nhiều fragment và snippet để dễ bảo trì.

## 2. Khi nào nên gom nhiều operation vào một trang?

Một trang chung phù hợp khi các operation cùng phục vụ một resource hoặc workflow, dùng chung authentication, error conventions và domain vocabulary.

Ví dụ Orders API:

| Nhóm | Operation | Mục đích |
| --- | --- | --- |
| Collection | **GET /api/orders** | Liệt kê/tìm kiếm đơn hàng. |
| Collection | **POST /api/orders** | Tạo đơn hàng. |
| Item | **GET /api/orders/{orderId}** | Lấy một đơn hàng. |
| Item | **PUT /api/orders/{orderId}** | Cập nhật đơn hàng. |
| Item | **DELETE /api/orders/{orderId}** | Xóa/hủy theo contract. |
| Action | **POST /api/orders/{orderId}/confirm** | Xác nhận đơn hàng. |

Nên tách trang nếu operation có quy trình rất khác, tài liệu quá dài, API versions có audience riêng, hoặc platform docs không điều hướng tốt. Tiêu chí gộp là mối liên hệ mà người đọc cần hiểu, không phải chỉ vì các endpoint dùng cùng HTTP.

## 3. Thiết kế cấu trúc một trang Markdown

Cấu trúc tham khảo:

~~~markdown
# Orders API

## Tổng quan
## Authentication và conventions
## Error responses

## Orders collection
### Liệt kê đơn hàng
### Tạo đơn hàng

## Một đơn hàng
### Lấy đơn hàng
### Cập nhật đơn hàng
### Xóa đơn hàng

## Operation nghiệp vụ
### Xác nhận đơn hàng

## Schemas và enum
## Changelog
~~~

Cấu trúc có ba lớp:

1. **Thông tin dùng chung:** base path, authentication, content types, pagination, error format.
2. **Operation:** method/path, mô tả, parameters, request, response, status và snippet.
3. **Thông tin tham chiếu:** schemas, enum, giới hạn và changelog.

Giữ conventions chung ở đầu trang. Trong từng operation chỉ nhắc lại điều kiện ngoại lệ.

### 3.1. Mục lục và anchor

Với trang dài, thêm mục lục:

~~~markdown
## Mục lục

- [Tổng quan](#tong-quan)
- [Authentication](#authentication-va-conventions)
- [Error responses](#error-responses)
- [Orders collection](#orders-collection)
  - [Liệt kê đơn hàng](#liet-ke-don-hang)
  - [Tạo đơn hàng](#tao-don-hang)
- [Một đơn hàng](#mot-don-hang)
  - [Lấy đơn hàng](#lay-don-hang)
  - [Cập nhật đơn hàng](#cap-nhat-don-hang)
- [Operation nghiệp vụ](#operation-nghiep-vu)
  - [Xác nhận đơn hàng](#xac-nhan-don-hang)
~~~

Anchor tự động phụ thuộc Markdown renderer. Slug tiếng Việt, dấu câu và heading trùng có thể được xử lý khác nhau giữa các nền tảng. Kiểm tra anchor sau khi render hoặc đặt ID theo cơ chế của renderer. Mục lục phải được cập nhật khi thêm/đổi operation; CI có thể kiểm tra các anchor đích.

## 4. Naming operation và snippet identifiers

REST Docs ghi operation với identifier:

~~~java
.andDo(document("orders-create", ...))
~~~

Identifier tạo thư mục operation trong generated snippets:

~~~text
build/generated-snippets/
├── orders-list/
├── orders-create/
├── orders-get/
├── orders-update/
├── orders-delete/
└── orders-confirm/
~~~

Quy ước tốt:

- Chữ thường, dấu gạch ngang, có namespace resource/module.
- Nêu hành động và scenario; tránh tên mơ hồ như test1.
- Ổn định dù test method được đổi tên.
- Tách identifier success/error khi output khác nhau.
- Không dùng cùng identifier cho hai test ghi khác response vào cùng file.

| Scenario | Identifier |
| --- | --- |
| Liệt kê thành công | orders-list |
| Tạo thành công | orders-create |
| Tạo với body sai | orders-create-invalid |
| Lấy đơn hàng | orders-get |
| Không tìm thấy | orders-get-not-found |
| Cập nhật xung đột | orders-update-conflict |

Identifier là contract giữa test và trang tài liệu. Khi đổi identifier, phải cập nhật đường dẫn snippet có liên quan.

## 5. Khuôn mẫu thống nhất cho một operation

Dùng cùng một cấu trúc giúp người đọc biết thông tin nằm ở đâu:

~~~markdown
### Tạo đơn hàng

**POST** /api/orders

Tạo đơn hàng mới cho khách hàng hiện tại.

**Authentication:** Bearer token.

**Request headers:** Content-Type: application/json.

**Responses:**
- 201 Created: Đã tạo đơn hàng.
- 400 Bad Request: Request không hợp lệ.
- 401 Unauthorized: Chưa xác thực.
- 409 Conflict: Xung đột nghiệp vụ.

#### HTTP request
[Snippet được ghép tại đây]

#### Request fields
[Snippet được ghép tại đây]

#### HTTP response
[Snippet được ghép tại đây]

#### Response fields
[Snippet được ghép tại đây]
~~~

Bỏ qua các phần không liên quan nếu đã được giải thích ở conventions chung. Với parameter hoặc response đặc biệt, ghi rõ để client không phải suy đoán.

Trật tự khuyến nghị: HTTP method/path; mục đích và quyền; parameters/headers; request body/fields/constraints; response statuses; response body/fields; error cases và side effects. Duy trì trật tự giữa các operation.

## 6. Ghép nhiều snippet vào một trang Markdown

Spring REST Docs sinh Markdown snippets, nhưng Markdown thuần không có cú pháp include file chuẩn. Muốn một trang cuối chứa nhiều operation, cần chọn cơ chế ghép:

- Static site generator hỗ trợ include/partials.
- Plugin include của renderer hiện có.
- Build task/preprocessor đọc snippet files và chèn vào trang.
- Nguồn cấu trúc sinh ra một trang Markdown tổng hợp.

Ví dụ source page có marker riêng:

~~~markdown
# Orders API

## Orders collection

### Liệt kê đơn hàng
<!-- snippet: orders-list/http-request.md -->
<!-- snippet: orders-list/http-response.md -->

### Tạo đơn hàng
<!-- snippet: orders-create/http-request.md -->
<!-- snippet: orders-create/http-response.md -->
<!-- snippet: orders-create/request-fields.md -->

## Một đơn hàng

### Lấy đơn hàng
<!-- snippet: orders-get/http-request.md -->
<!-- snippet: orders-get/http-response.md -->
~~~

Các comment là **marker minh họa**, không phải directive Markdown chuẩn. Chúng chỉ hoạt động nếu build preprocessor được cấu hình để resolve path, validate file và chèn nội dung. Dùng plugin/site generator thì thay bằng cú pháp include của chính công cụ.

### 6.1. Partials theo operation

Một cấu trúc source có thể là:

~~~text
docs/
├── pages/
│   └── orders.md
└── partials/
    └── orders/
        ├── intro.md
        ├── list.md
        ├── create.md
        ├── get.md
        └── update.md
~~~

Trang chính include từng partial theo thứ tự. Partial operation có thể include snippet files trong generated snippets directory nếu công cụ cho phép. Nhờ đó trang xuất bản vẫn là một trang, trong khi từng operation được review riêng.

Cần xác nhận công cụ có hỗ trợ nested includes và đường dẫn nằm ngoài source directory. Không giả định mọi Markdown engine hỗ trợ cùng cú pháp.

### 6.2. Yêu cầu với preprocessor

Nếu tự viết bước ghép, tối thiểu cần:

- Resolve snippet root từ một cấu hình duy nhất.
- Chặn path traversal ra ngoài generated snippets directory.
- Fail nếu snippet bắt buộc không tồn tại.
- Giữ nguyên code fences, newline và UTF-8.
- Phát hiện marker trùng hoặc include lồng ngoài dự kiến.
- Ghi trang cuối vào build directory, không ghi đè source page.
- Chạy deterministic để cùng source/snippets cho cùng output.

Tránh regex replace thiếu kiểm soát nếu marker có thể xuất hiện trong code examples hoặc nội dung người dùng.

## 7. Bố cục trang Orders API minh họa

~~~markdown
# Orders API

## Tổng quan

Orders API cho phép người dùng đã xác thực quản lý đơn hàng.

**Base path:** /api/orders

**Authentication:** Bearer token.

**Media type:** application/json.

### Quy ước chung

- ID do server cấp.
- Timestamp theo ISO-8601 trong contract.
- Lỗi theo schema error chung.
- Pagination bắt đầu từ page 0.

## Error responses

| Status | Ý nghĩa |
| --- | --- |
| 400 | Request/parameter không hợp lệ. |
| 401 | Thiếu hoặc sai xác thực. |
| 403 | Không có quyền. |
| 404 | Không tìm thấy resource. |
| 409 | Xung đột trạng thái. |

## Orders collection

### Liệt kê đơn hàng

**GET** /api/orders

Trả về danh sách theo bộ lọc và phân trang.

#### HTTP request
<!-- snippet: orders-list/http-request.md -->

#### HTTP response
<!-- snippet: orders-list/http-response.md -->

#### Query parameters
<!-- snippet: orders-list/query-parameters.md -->

#### Response fields
<!-- snippet: orders-list/response-fields.md -->

### Tạo đơn hàng

**POST** /api/orders

Tạo đơn hàng mới.

#### HTTP request
<!-- snippet: orders-create/http-request.md -->

#### Request fields
<!-- snippet: orders-create/request-fields.md -->

#### HTTP response
<!-- snippet: orders-create/http-response.md -->

#### Response fields
<!-- snippet: orders-create/response-fields.md -->

## Một đơn hàng

### Lấy đơn hàng

**GET** /api/orders/{orderId}

#### Path parameters
<!-- snippet: orders-get/path-parameters.md -->

#### HTTP request
<!-- snippet: orders-get/http-request.md -->

#### HTTP response
<!-- snippet: orders-get/http-response.md -->

#### Response fields
<!-- snippet: orders-get/response-fields.md -->

## Changelog

| Version | Thay đổi |
| --- | --- |
| v1 | Phiên bản đầu tiên của tài liệu. |
~~~

Đây là bố cục minh họa. Marker phải được công cụ build thay bằng snippet thật hoặc build phải báo lỗi; nếu marker xuất hiện nguyên văn trong trang cuối thì bước assemble chưa hoàn tất.

## 8. Tái sử dụng mô tả chung

Nhiều operation dùng chung authentication, content type, pagination, error schema, enum, idempotency và versioning conventions. Đặt nội dung chung ở đầu trang hoặc trong partial.

Không copy/paste một đoạn dài vào mọi operation vì khi rule đổi, các bản sao dễ lệch. Tuy nhiên, ngoại lệ của operation phải được nêu ngay trong operation.

| Loại thông tin | Vị trí |
| --- | --- |
| Bearer token là cơ chế chung | Authentication đầu trang. |
| Operation yêu cầu scope orders:approve | Operation cụ thể. |
| Error schema dùng chung | Error responses. |
| Lỗi domain riêng khi confirm | Operation confirm. |
| Pagination bắt đầu từ 0 | Common conventions; query descriptor nếu cần. |

## 9. Nhiều scenario cho cùng operation

Một endpoint có thể có success, validation error, not found, forbidden hoặc conflict. Tách heading và identifier để không include nhầm response:

~~~markdown
### Lấy đơn hàng

**GET** /api/orders/{orderId}

#### Thành công — 200 OK
<!-- snippet: orders-get/http-response.md -->

#### Không tìm thấy — 404 Not Found
<!-- snippet: orders-get-not-found/http-response.md -->

#### Không có quyền — 403 Forbidden
<!-- snippet: orders-get-forbidden/http-response.md -->
~~~

Dùng convention resource-operation-outcome. Không bắt buộc đổi identifier đã ổn định chỉ để theo mẫu hình thức; điều quan trọng là unique, rõ nghĩa và nhất quán.

## 10. Bảng operation index

Bảng index gần đầu trang giúp chọn nhanh:

| Method | Path | Mô tả | Section |
| --- | --- | --- | --- |
| GET | /api/orders | Liệt kê | Orders collection |
| POST | /api/orders | Tạo | Orders collection |
| GET | /api/orders/{orderId} | Lấy chi tiết | Một đơn hàng |
| PUT | /api/orders/{orderId} | Cập nhật | Một đơn hàng |
| DELETE | /api/orders/{orderId} | Xóa/hủy | Một đơn hàng |
| POST | /api/orders/{orderId}/confirm | Xác nhận | Operation nghiệp vụ |

Index có thể viết tay hoặc sinh tự động. Nếu viết tay, thêm operation phải cập nhật index và heading. CI có thể kiểm tra mọi row trỏ tới anchor tồn tại. Index nên chứa method/path/mục đích/section, không nhồi toàn bộ schema vào một bảng quá rộng.

## 11. Thứ tự và tính nhất quán

Một quy tắc nhóm có thể là collection operations, item operations, nested resources, business actions, rồi webhooks/admin operations. Trong nhóm, thường xếp list, create, read, update, delete, rồi actions. Có thể chọn thứ tự khác nếu workflow domain tự nhiên hơn; quan trọng là nhất quán và dễ dự đoán.

Mỗi operation nên có các heading cốt lõi: purpose, parameters, request, responses. Bỏ phần không liên quan hoặc ghi rõ không có nếu người đọc có thể hiểu nhầm. Không để operation đầu có response fields còn operation sau thiếu chỉ vì quên include.

## 12. Nhiều người cùng làm và source fragments

Một trang cuối có thể assemble từ fragments:

~~~text
docs/
├── pages/
│   └── orders.md
└── partials/
    └── orders/
        ├── intro.md
        ├── list.md
        ├── create.md
        ├── get.md
        └── errors.md
~~~

Generated snippets thường nên nằm trong build directory để tái tạo, không nhất thiết dưới source docs. Khi nhiều developer cùng làm, phân chia theo operation, tránh hai test ghi cùng identifier, dùng partial riêng và assemble trang tổng hợp sau merge. Cách này giảm merge conflicts so với việc tất cả cùng sửa một trang dài.

## 13. CI: xác minh page có đủ operation

~~~mermaid
flowchart TD
    A["Run REST Docs HTTP tests"] --> B{"Tests pass?"}
    B -->|No| X["Fail CI"]
    B -->|Yes| C["Generate snippets per identifier"]
    C --> D["Assemble one Markdown page"]
    D --> E["Check required snippet references"]
    E --> F["Check anchors and links"]
    F --> G["Render Markdown"]
    G --> H{"All checks pass?"}
    H -->|No| X
    H -->|Yes| I["Review and publish"]
~~~

CI nên kiểm tra:

- Mỗi operation trong index có heading/anchor tương ứng.
- Identifier trong source được tạo bởi test hiện tại.
- Snippet bắt buộc tồn tại; include thiếu phải fail.
- Không có identifier collision hoặc file bị ghi đè ngoài ý muốn.
- Thứ tự operation đúng convention.
- Link mục lục/index không gãy.
- Tables, fenced code blocks và tiếng Việt render chính xác.
- Trang assemble không còn marker chưa xử lý.
- Clean build tạo lại đúng trang, không phụ thuộc artifact cũ.

File tồn tại chưa chứng minh snippet thuộc đúng operation. Nếu identifier bị dùng lại, test có thể ghi đè nhưng CI vẫn thấy file. Với tài liệu lớn, kiểm tra thêm HTTP method/path trong snippet hoặc review generated diff.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang quá dài, khó tìm | Thiếu nhóm headings/mục lục | Chia collection/item/action và thêm index. |
| Include nhầm response | Dùng chung identifier cho nhiều scenario | Tách identifier success/error. |
| Snippet bị ghi đè | Nhiều test dùng một identifier | Đặt identifier unique. |
| Operation mới không có trong index | Index thủ công không cập nhật | Sinh index hoặc kiểm tra anchor trong CI. |
| Marker include còn nguyên | Preprocessor/plugin chưa chạy | Kiểm tra tool và fail nếu còn marker. |
| Link mục lục gãy | Slug khác renderer hoặc heading đổi | Kiểm tra sau render, dùng ID ổn định. |
| Authentication lặp và lệch | Copy/paste nhiều lần | Đưa common rule vào phần chung/partial. |
| Operation thiếu parameter/header | Khuôn mẫu không đầy đủ | Dùng checklist descriptor thống nhất. |
| Scenario success/error lẫn lộn | Không có heading con/identifier riêng | Tách outcomes. |
| Merge conflict thường xuyên | Nhiều người sửa một trang | Chia partial theo operation. |
| Local và CI khác nhau | Plugin/renderer hoặc version không pin | Dùng cùng cấu hình. |
| Snippet cũ sau clean build | Output directory/task dependency sai | Quản lý output và chạy đúng test task. |

## 15. Bài thực hành

Tạo trang Markdown **Customers API** với các operations:

- **GET /api/customers**
- **POST /api/customers**
- **GET /api/customers/{customerId}**
- **PATCH /api/customers/{customerId}**
- **DELETE /api/customers/{customerId}**

Với mỗi operation có ít nhất một scenario thành công; operation quan trọng nên có not found hoặc validation error.

Thực hiện:

1. Thiết kế heading tree, mục lục và operation index.
2. Viết REST Docs HTTP tests với identifier ổn định cho từng operation/scenario.
3. Sinh snippets và xác nhận filename/extension theo template format.
4. Chọn partials, plugin include hoặc preprocessor.
5. Assemble một trang Markdown chứa thông tin chung và mọi operation.
6. Tái sử dụng authentication/error conventions, ghi riêng ngoại lệ theo operation.
7. Kiểm tra mọi mục index trỏ tới anchor tồn tại.
8. Kiểm tra marker đã được resolve và snippets bắt buộc không thiếu.
9. Render trong CI; thử clean build để xác nhận không phụ thuộc artifact cũ.
10. Thêm operation mới và xác nhận index, heading, identifier và trang cuối đều cập nhật.

**Tiêu chí hoàn thành:** một trang Markdown có thể điều hướng tới mọi operation; mỗi operation dùng đúng snippet từ HTTP tests; scenarios tách rõ; nội dung chung được tái sử dụng; CI phát hiện include, link, identifier và render errors.

## Tài liệu tham khảo

- [Spring REST Docs — Working with Markdown](https://docs.spring.io/spring-restdocs/reference/working-with-markdown.html)
- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html)
- [CommonMark Specification](https://commonmark.org/)
- [Markdown Guide — Extended Syntax](https://www.markdownguide.org/extended-syntax/)
- [MkDocs — Content and Navigation](https://www.mkdocs.org/user-guide/writing-your-docs/)
- [Docusaurus — Markdown Features](https://docusaurus.io/docs/markdown-features)
