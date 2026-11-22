# Phân biệt custom snippet với tài liệu viết tay

## 1. Hai cách tạo nội dung trong tài liệu API

Khi xây dựng tài liệu REST API, không phải mọi thông tin đều phù hợp để sinh tự động từ bài kiểm thử. Một phần nội dung có thể được kiểm chứng trực tiếp từ HTTP request/response, trong khi phần khác cần người viết giải thích bối cảnh, quy trình hoặc quyết định nghiệp vụ.

Trong **SPRING_REST_DOCS**, Spring REST Docs nhận dữ liệu từ các bài test HTTP sử dụng MockMvc, WebTestClient hoặc REST Assured. Các snippet mặc định mô tả request, response, headers, fields, parameters và parts. Khi cần một loại snippet mới, nhóm có thể tạo **custom snippet** đọc operation context và render bằng template. Ngược lại, tài liệu viết tay là phần Markdown hoặc AsciiDoc do người viết duy trì trực tiếp.

Hai cách có mục tiêu khác nhau:

- **Custom snippet** sinh nội dung có cấu trúc từ một operation đã được test ghi nhận. Nó phù hợp với thông tin cần khớp dữ liệu HTTP, chẳng hạn method, URI, status, header được chọn hoặc danh sách multipart parts.
- **Tài liệu viết tay** trình bày nội dung biên soạn bởi con người, như lý do thiết kế, hướng dẫn tích hợp, quy trình nghiệp vụ, ví dụ tổng quan, lưu ý vận hành hoặc quyết định chưa thể biểu diễn bằng một lần gọi HTTP.

Bài này thuộc chương **Snippet customization** của **SPRING_REST_DOCS** — module tạo tài liệu REST API có thể kiểm chứng từ test HTTP, tạo snippet cho request, response, payload, tham số và header, sau đó biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể:

- Phân biệt nguồn dữ liệu và cơ chế kiểm chứng của custom snippet với tài liệu viết tay.
- Chọn nội dung nào nên sinh tự động, nội dung nào nên biên soạn.
- Hiểu giới hạn của việc kiểm chứng bằng test và rủi ro của nội dung viết tay.
- Kết hợp snippet với phần giải thích Markdown/AsciiDoc trong một tài liệu hoàn chỉnh.
- Thiết kế review và CI để phát hiện nội dung lỗi thời hoặc snippet bị thiếu.
- Tránh coi custom snippet là cách thay thế toàn bộ tài liệu hướng dẫn.

## 2. Custom snippet là gì?

Một custom snippet là một thành phần tài liệu hóa được đăng ký trong `document(...)` và thực thi trên operation context của Spring REST Docs. Operation chứa request và response mà test đã ghi nhận, cùng các attributes liên quan.

Ví dụ, muốn có file `operation-summary.adoc` với HTTP method, URI và status:

```java
public class OperationSummarySnippet extends TemplatedSnippet {

    public OperationSummarySnippet() {
        super("operation-summary", "operation-summary", Map.of());
    }

    @Override
    protected Map<String, Object> createModel(Operation operation) {
        Map<String, Object> model = new LinkedHashMap<>();
        model.put("operationName", operation.getName());
        model.put("method", operation.getRequest().getMethod().name());
        model.put("uri", operation.getRequest().getUri().toString());
        model.put("status", operation.getResponse().getStatus().value());
        return model;
    }
}
```

Template Mustache:

```adoc
.Operation summary
|===
|Thông tin|Giá trị

|Operation
|{{operationName}}

|HTTP method
|{{method}}

|URI
|{{uri}}

|Status
|{{status}}
|===
```

Đăng ký snippet cùng các snippet mặc định:

```java
mockMvc.perform(get("/api/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        new OperationSummarySnippet(),
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm")
        )
    ));
```

Khi test chạy, Spring REST Docs gọi custom snippet với `Operation`, custom snippet tạo model và template render nội dung. Output có thể là:

```text
build/generated-snippets/
└── products-get/
    ├── operation-summary.adoc
    └── response-fields.adoc
```

Đây vẫn là snippet được tạo tự động từ test. Người phát triển viết lớp Java và template, nhưng nội dung của `method`, `uri` và `status` được lấy từ operation thực tế.

Một custom snippet không nhất thiết phải dùng `TemplatedSnippet`; có thể implement `Snippet` trực tiếp nếu cần toàn quyền tạo output. `TemplatedSnippet` thuận tiện khi nội dung được trình bày bằng Mustache.

## 3. Tài liệu viết tay là gì?

Tài liệu viết tay là nội dung do người biên soạn viết trực tiếp trong tệp `.adoc` hoặc `.md`. Nó có thể được Asciidoctor hoặc Markdown builder kết xuất, nhưng Spring REST Docs không tự đối chiếu từng câu với HTTP operation.

Ví dụ phần hướng dẫn viết bằng AsciiDoc:

```adoc
== Lấy thông tin sản phẩm

API này được dùng để hiển thị trang chi tiết sản phẩm.
Client cần có quyền đọc catalog trước khi gọi endpoint.

=== Quy trình sử dụng

. Lấy mã sản phẩm từ danh sách catalog.
. Gọi API chi tiết với mã sản phẩm.
. Hiển thị tên, giá và trạng thái tồn kho từ response.

=== Lưu ý

Nếu sản phẩm đã bị ngừng kinh doanh, client vẫn có thể nhận
response thành công nhưng trường `active` sẽ có giá trị `false`.
```

Hoặc Markdown:

```markdown
## Lấy thông tin sản phẩm

API này phục vụ màn hình chi tiết sản phẩm. Client cần có quyền
đọc catalog trước khi gọi endpoint.

### Quy trình

1. Lấy mã sản phẩm từ danh sách catalog.
2. Gọi API chi tiết với mã sản phẩm.
3. Hiển thị dữ liệu trả về.

### Lưu ý

Sản phẩm đã ngừng kinh doanh vẫn có thể được truy vấn.
```

Người viết chịu trách nhiệm về nội dung, tính đúng đắn và việc cập nhật phần giải thích này khi nghiệp vụ thay đổi. Build có thể kiểm tra cú pháp hoặc include, nhưng bản thân việc kết xuất thành công không chứng minh mọi câu mô tả đều đúng với ứng dụng.

Tài liệu viết tay không đồng nghĩa với tài liệu kém chất lượng. Nó là lựa chọn cần thiết cho những điều không thể suy ra từ một lần HTTP exchange, như mục tiêu sử dụng, luồng nghiệp vụ, quyết định thiết kế, hướng dẫn retry hoặc ví dụ tích hợp nhiều operation.

## 4. So sánh theo nguồn dữ liệu và khả năng kiểm chứng

| Tiêu chí | Custom snippet | Tài liệu viết tay |
| --- | --- | --- |
| Nguồn dữ liệu | Operation context, descriptor và attributes | Nội dung do người viết cung cấp |
| Thời điểm tạo | Khi test tài liệu hóa chạy | Khi biên soạn hoặc build tài liệu |
| Kiểm chứng HTTP | Có thể đối chiếu với request/response đã ghi nhận | Không tự đối chiếu với HTTP exchange |
| Cách tạo | Java `Snippet`/`TemplatedSnippet` và template | Markdown/AsciiDoc |
| Cấu trúc | Có schema/model và template | Linh hoạt theo mục đích biên soạn |
| Thay đổi API | Có thể làm test/snippet fail khi dữ liệu không khớp | Có thể lỗi thời mà build vẫn thành công |
| Bối cảnh nghiệp vụ | Chỉ có nếu test truyền vào hoặc operation chứa dữ liệu đó | Có thể giải thích đầy đủ hơn |
| Bảo trì | Cần giữ code, model và template tương thích | Cần review nội dung và chủ sở hữu cập nhật |
| Mức tái sử dụng | Tốt với nhiều operation cùng cấu trúc | Tốt với hướng dẫn, quy trình và chương tổng quan |

Điểm quan trọng: custom snippet **có thể được kiểm chứng**, nhưng không có nghĩa mọi thông tin trong đó đều tự động đúng. Nếu snippet đưa `constraints`, `label` hoặc `businessRule` từ một giá trị hard-code trong Java, test chỉ xác nhận snippet được render; nó không chứng minh quy tắc đó khớp với validation thật của ứng dụng.

Ví dụ:

```java
model.put("maxUploadSize", "5 MiB");
```

Giá trị trên chỉ là metadata do người viết cung cấp. Muốn nó phản ánh cấu hình thật, cần lấy từ nguồn cấu hình có thẩm quyền hoặc viết test/assertion để so sánh với giới hạn thực thi.

## 5. Chọn custom snippet cho nội dung cần gắn với HTTP exchange

Nên dùng custom snippet khi nội dung có thể lấy từ operation và cần đồng bộ với test.

Các trường hợp phù hợp:

- Method, URI, response status và Content-Type.
- Danh sách request/response headers được chọn.
- Multipart part name, filename, Content-Type và kích thước.
- Một tập thông tin tóm tắt của operation.
- Correlation header hoặc pagination metadata đã được test ghi nhận.
- Nội dung kỹ thuật có cấu trúc cần sinh giống nhau cho nhiều operation.

Ví dụ snippet tóm tắt multipart:

```java
for (OperationRequestPart part : operation.getRequest().getParts()) {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("name", part.getName());
    item.put("filename", part.getSubmittedFileName());
    item.put("contentType", part.getHeaders().getContentType());
    item.put("size", part.getContent().length);
    parts.add(item);
}
```

Kết quả được sinh từ request multipart thực tế trong test. Nếu part `image` đổi Content-Type hoặc filename, snippet tiếp theo sẽ phản ánh dữ liệu mới.

Dùng allowlist khi lấy headers; không dump `Authorization`, `Cookie`, token hoặc dữ liệu nhạy cảm. Với filename hoặc query string có thể chứa dữ liệu riêng tư, cần chuẩn hóa trước khi đưa vào model.

### 5.1. Không sinh nội dung mà operation không thể chứng minh

Operation context không tự biết:

- Người dùng nên gọi API ở bước nào của nghiệp vụ.
- Vì sao một field là bắt buộc theo chính sách sản phẩm.
- Điều kiện retry hoặc backoff được khuyến nghị.
- Quy tắc phân quyền tổng thể nếu test chỉ chạy với một tài khoản.
- Giới hạn được thực thi tại API gateway nếu test chỉ gọi controller.
- SLA, quota hoặc cam kết vận hành.

Có thể truyền những thông tin này dưới dạng attributes hoặc cấu hình để template hiển thị, nhưng nếu chúng không được lấy và kiểm chứng từ nguồn đáng tin cậy, cần coi chúng là nội dung biên soạn. Đừng đặt tên cột “Đã xác minh” cho một giá trị chỉ được nhập thủ công.

## 6. Chọn tài liệu viết tay cho nội dung cần giải thích

Dùng Markdown/AsciiDoc trực tiếp cho:

- Giới thiệu sản phẩm và phạm vi API.
- Kiến thức xác thực, phân quyền và cách lấy token.
- Luồng nghiệp vụ đi qua nhiều operation.
- Quy tắc retry, idempotency, timeout và rate limit.
- Quy trình xử lý lỗi ở phía client.
- Hướng dẫn SDK, ví dụ kết hợp nhiều endpoint.
- Quyết định thiết kế, migration guide và changelog.
- Giải thích các giới hạn chưa thể kiểm chứng bằng một test HTTP.

Ví dụ, một đoạn hướng dẫn retry:

```markdown
### Xử lý khi gặp lỗi tạm thời

Khi nhận lỗi 503, client có thể thử lại theo chính sách retry
của ứng dụng. Sử dụng exponential backoff và giới hạn tổng số lần
thử lại. Không retry tự động các thao tác ghi nếu chưa xác định
tính idempotent của request.
```

Đoạn văn này cần review bởi người hiểu contract vận hành và nghiệp vụ. Nó không được xác minh chỉ vì trang Markdown được build thành công.

Đối với nội dung quan trọng như retry, timeout, quota hoặc bảo mật, nên chỉ rõ nguồn chuẩn và chủ sở hữu. Ví dụ, nếu giá trị lấy từ cấu hình runtime, đừng sao chép nhiều lần thành các con số hard-code trên nhiều trang.

## 7. Kết hợp custom snippet với tài liệu viết tay

Trong thực tế, tài liệu API hoàn chỉnh thường dùng cách kết hợp:

1. Người viết mô tả mục đích, luồng sử dụng và lưu ý nghiệp vụ bằng Markdown/AsciiDoc.
2. Test HTTP xác minh request/response và sinh snippet.
3. Trang tài liệu include các snippet ở đúng vị trí.
4. Build kiểm tra snippet có tồn tại và tài liệu kết xuất thành công.
5. Review viên kiểm tra cả dữ liệu sinh tự động lẫn nội dung biên soạn.

Ví dụ trang AsciiDoc kết hợp hai loại:

```adoc
= Product API
:toc: left

== Lấy thông tin sản phẩm

API này phục vụ trang chi tiết sản phẩm. Client cần có quyền
đọc catalog trước khi gọi endpoint.

=== HTTP request và response

include::{snippets}/products-get/http-request.adoc[]

include::{snippets}/products-get/http-response.adoc[]

=== Operation summary

include::{snippets}/products-get/operation-summary.adoc[]

=== Response fields

include::{snippets}/products-get/response-fields.adoc[]

=== Hướng dẫn sử dụng

. Gọi endpoint bằng mã sản phẩm đã nhận từ catalog.
. Đọc trường `active` để xác định sản phẩm còn kinh doanh hay không.
. Hiển thị `price` theo đơn vị tiền tệ được quy định trong response.
```

Trong ví dụ:
- Đoạn giới thiệu và hướng dẫn do người viết duy trì.
- `http-request`, `http-response`, `operation-summary` và `response-fields` được sinh từ test.
- Trang kết hợp hai nguồn thành một tài liệu liền mạch.

Cần tránh lặp lại thủ công các giá trị đã có trong snippet. Nếu URI thay đổi, snippet sẽ được sinh lại; một câu viết tay lặp URI có thể vẫn giữ giá trị cũ và gây mâu thuẫn.

## 8. Đối chiếu ví dụ: một endpoint, hai trách nhiệm

Giả sử endpoint `GET /api/products/{id}` trả:

```json
{
  "id": 42,
  "name": "Java in Practice",
  "active": true,
  "price": 250000
}
```

### Phần nên sinh từ test

Test có thể kiểm tra:
- Status `200`.
- Response Content-Type là `application/json`.
- JSON có `id`, `name`, `active`, `price`.
- Kiểu và mô tả field được khai báo trong `responseFields(...)`.
- URI chứa đúng product ID được gửi.

Ví dụ:

```java
mockMvc.perform(get("/api/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("active").description("Sản phẩm còn kinh doanh"),
            fieldWithPath("price").description("Giá sản phẩm, tính bằng VND")
        )
    ));
```

Snippet sinh giúp kiểm chứng các field được mô tả có trong response mẫu. Nếu response có field mới mà strict descriptor chưa cập nhật, test có thể báo lỗi; nếu field bắt buộc được mô tả nhưng không có trong response mẫu, test cũng có thể thất bại.

### Phần nên viết tay

Người biên soạn cần giải thích:
- Endpoint phục vụ màn hình hoặc use case nào.
- Client lấy `id` từ operation nào trước đó.
- Cách hiển thị sản phẩm đã ngừng kinh doanh.
- Có cần cache response hay không.
- Những trường hợp lỗi nghiệp vụ đặc biệt.

Các điều trên không được chứng minh chỉ bởi một response mẫu. Cần tài liệu nghiệp vụ hoặc test phù hợp làm nguồn xác nhận.

## 9. Quản lý thay đổi và chống drift

Custom snippet và tài liệu viết tay đều có thể lỗi thời, nhưng cách phát hiện khác nhau.

| Thay đổi | Custom snippet | Tài liệu viết tay |
| --- | --- | --- |
| URI đổi trong test | Có thể tự phản ánh ở lần sinh tiếp theo | Câu văn ghi URI thủ công có thể cũ |
| Response có field mới | Strict `responseFields` có thể phát hiện field chưa mô tả | Đoạn giải thích field viết tay cần review |
| Status lỗi thay đổi | Test assertion/snippet có thể phát hiện | Bảng status viết tay cần cập nhật |
| Chính sách retry đổi | Operation đơn lẻ thường không biết | Cần chủ sở hữu cập nhật hướng dẫn |
| Template đổi | Output snippet có thể thay đổi | Prose viết tay ít ảnh hưởng |
| Tên field nghiệp vụ đổi | Descriptor/test cần sửa | Các đoạn giải thích liên quan cũng cần review |

Đề xuất quản lý:

- Dùng test và strict descriptors cho phần contract có thể quan sát.
- Tách quy tắc nghiệp vụ và vận hành thành nội dung có owner.
- Link tới một nguồn chính sách chuẩn thay vì copy số liệu lặp lại.
- Review các đoạn prose nhắc tới URI, status, field hoặc header để tránh trùng dữ liệu tự động.
- Khi contract đổi, kiểm tra cả snippet và các phần viết tay phụ thuộc vào nó.
- Lưu generated snippets trong artifact hoặc diff của pull request để review.

## 10. Kiểm tra và review trong CI

Một pipeline tài liệu có thể có các bước:

```text
HTTP documentation tests
          |
          v
Spring REST Docs sinh snippets
          |
          +----------------------+
          |                      |
          v                      v
Custom snippet output       Static AsciiDoc/Markdown
          |                      |
          +----------+-----------+
                     |
                     v
           Asciidoctor / Markdown build
                     |
                     v
             Link/include checks
                     |
                     v
              Review và publish
```

CI có thể tự xác minh:
- Test tài liệu hóa thành công.
- Các snippet được kỳ vọng đã được sinh.
- Custom snippet chứa các giá trị method/status/part cần thiết.
- Asciidoctor include không trỏ tới file thiếu.
- Markdown/AsciiDoc build không lỗi cú pháp hỗ trợ.

CI không tự xác minh đầy đủ:
- Nội dung giới thiệu có đúng nghiệp vụ không.
- Ví dụ viết tay còn phù hợp với phiên bản API không.
- Khuyến nghị retry có an toàn không.
- Bảng quota hard-code có trùng cấu hình vận hành không.
- Quy trình nhiều bước có mô tả đúng thứ tự hay không.

Vì vậy, pull request thay đổi tài liệu cần có hai phạm vi review: review test/snippet và review prose/chính sách. Có thể dùng code owner hoặc reviewer phù hợp cho mỗi phần.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đưa toàn bộ hướng dẫn vào custom snippet | Chọn sai cơ chế cho nội dung cần giải thích | Viết prose trong AsciiDoc/Markdown và include snippet liên quan |
| Copy URI/status thủ công nhiều nơi | Lặp dữ liệu có thể sinh từ operation | Include `http-request`, `http-response` hoặc custom snippet |
| Cho rằng custom snippet luôn đúng | Model có thể chứa dữ liệu hard-code | Xác định nguồn dữ liệu và assertion cho từng giá trị |
| Prose sai nhưng CI vẫn pass | Build chỉ kiểm tra kết xuất, không hiểu ý nghĩa nghiệp vụ | Review nội dung và chỉ rõ owner/source |
| Snippet không được tạo | Chưa đăng ký custom snippet trong `document(...)` hoặc test không chạy | Kiểm tra test và output operation directory |
| Include bị thiếu | Tên operation/snippet trong tài liệu không khớp | Xác minh đường dẫn generated và include |
| Nội dung viết tay bị stale sau API change | Không có liên kết hoặc người chịu trách nhiệm | Search các tham chiếu và review phần phụ thuộc |
| Lộ token trong custom snippet | Đưa toàn bộ operation headers vào model | Chỉ lấy allowlist, mask và dùng dữ liệu test giả |
| Dùng snippet để công bố quota chưa kiểm chứng | Giá trị nhập thủ công được trình bày như dữ liệu runtime | Lấy từ nguồn cấu hình hoặc ghi rõ đây là chính sách biên soạn |

## 12. Quy trình chọn cách thể hiện

Trước khi thêm một phần nội dung, hãy đặt câu hỏi:

1. Giá trị có trực tiếp xuất hiện trong HTTP exchange được test không?
2. Giá trị có thể lấy ổn định từ `Operation` hoặc descriptor không?
3. Có cần test thất bại khi giá trị thay đổi hoặc không còn đúng không?
4. Nội dung có cần giải thích bối cảnh, nguyên nhân hoặc hướng dẫn nhiều bước không?
5. Ai chịu trách nhiệm cập nhật khi chính sách hoặc nghiệp vụ đổi?

Có thể dùng quy tắc thực hành:

| Nếu nội dung... | Cách thể hiện ưu tiên |
| --- | --- |
| Là method, URI, status, header, payload hoặc part đã test | Snippet mặc định hoặc custom snippet |
| Là bảng fields, parameters, links | Snippet mặc định với descriptors |
| Là bảng mới nhưng dữ liệu lấy từ operation | Custom snippet |
| Là mục đích API, use case và luồng nghiệp vụ | Tài liệu viết tay |
| Là chính sách vận hành hoặc retry | Tài liệu viết tay có owner/source |
| Là ví dụ HTTP cần khớp với test | Include snippet được sinh |
| Là hướng dẫn kết hợp nhiều operation | Tài liệu viết tay kết hợp nhiều snippet |

Không có quy tắc buộc một trang chỉ được dùng một cách. Trang tốt thường có cả prose giải thích và snippet kiểm chứng.

## 13. Bài thực hành

Với endpoint `GET /api/products/{id}`:

1. Viết test MockMvc kiểm tra status và response fields.
2. Include `http-request.adoc`, `http-response.adoc` và `response-fields.adoc` vào tài liệu.
3. Tạo `OperationSummarySnippet` để sinh method, URI và status trong một bảng.
4. Viết tay phần giới thiệu use case, quyền truy cập và các bước client sử dụng.
5. Bổ sung một mục retry hoặc caching, ghi rõ nguồn chính sách và người chịu trách nhiệm.
6. Thay URI endpoint trong mapping và chạy test; xác nhận snippet phản ánh URI mới.
7. Review các đoạn prose có nhắc URI hoặc field để tìm nội dung cũ.
8. Thêm test assertion cho các dữ liệu custom snippet quan trọng.
9. Chạy Asciidoctor và xác nhận toàn trang có đủ nội dung sinh tự động lẫn nội dung biên soạn.
10. Tạo pull request, yêu cầu review cho cả contract/snippet lẫn prose nghiệp vụ.

### Câu hỏi tự đánh giá

- Custom snippet lấy dữ liệu từ nguồn nào?
- Vì sao một custom snippet có thể chứa dữ liệu hard-code và không tự chứng minh nó đúng?
- Tài liệu viết tay khác snippet được sinh ở cơ chế kiểm chứng nào?
- Khi URI thay đổi, vì sao include snippet an toàn hơn copy URI vào nhiều đoạn prose?
- Nội dung nào phù hợp với `TemplatedSnippet`?
- Khi nào nên viết hướng dẫn bằng AsciiDoc hoặc Markdown?
- CI kiểm tra được những gì và không thể tự kết luận điều gì?
- Làm thế nào kết hợp hai cách mà không lặp dữ liệu?
- Ai nên review các chính sách retry, quota hoặc phân quyền viết tay?

**Ghi nhớ:** Custom snippet sinh nội dung có cấu trúc từ operation đã được test và phù hợp với dữ liệu HTTP cần đồng bộ. Tài liệu viết tay giải thích bối cảnh, nghiệp vụ và cách sử dụng mà một HTTP exchange không thể tự nói lên. Hãy kết hợp hai cách: test và snippet cho contract quan sát được, prose có nguồn và chủ sở hữu cho hướng dẫn cần biên soạn.

## Tài liệu tham khảo

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): tạo custom snippet, template và attributes.
- [Spring REST Docs — `TemplatedSnippet` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/snippet/TemplatedSnippet.html): render snippet từ operation model.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): include snippet và biên soạn trang tài liệu.
- [Spring REST Docs — `Operation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/Operation.html): dữ liệu operation được cung cấp cho custom snippet.
