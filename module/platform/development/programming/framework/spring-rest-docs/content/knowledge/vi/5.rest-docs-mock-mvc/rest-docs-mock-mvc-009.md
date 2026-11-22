# Đặt tên thư mục operation ổn định

## 1. Identifier quyết định vị trí snippet như thế nào?

**Spring REST Docs** sinh tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Từ request và response đã thực thi, công cụ ghi các **snippet** mô tả HTTP message, payload, tham số và header. Snippet sau đó được đưa vào tài liệu Asciidoctor/Markdown và quy trình build, CI để tài liệu có thể được tạo lại cùng mã nguồn.

Với MockMvc, mỗi lần ghi tài liệu thường có dạng:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
~~~

Chuỗi `"books-get"` là **identifier** của operation. Spring REST Docs dùng identifier này làm đường dẫn gốc cho nhóm snippet được tạo ra. Với output mặc định của Gradle, đường dẫn thường có dạng:

~~~text
build/generated-snippets/
└── books-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    └── response-body.adoc
~~~

Danh sách file minh họa phụ thuộc vào snippet mặc định, phiên bản và cấu hình dự án. Điều quan trọng là mọi snippet của lần ghi operation này được đặt dưới thư mục `books-get`. Tài liệu Asciidoctor có thể tham chiếu chúng bằng:

~~~adoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
~~~

Identifier không chỉ là nhãn hiển thị trong test. Nó là **một phần của cấu trúc file đầu ra và hợp đồng giữa test với tài liệu**. Nếu đổi identifier, đường dẫn include cũng cần đổi theo.

## 2. Thế nào là một identifier ổn định?

Một identifier tốt cần đáp ứng bốn tiêu chí:

1. **Có ý nghĩa nghiệp vụ:** nhìn tên biết operation hoặc tài nguyên nào đang được tài liệu hóa.
2. **Ổn định:** không đổi chỉ vì đổi tên class, method test, sắp xếp lại test hoặc thay dữ liệu mẫu không làm thay đổi hợp đồng.
3. **Duy nhất:** hai operation khác nhau không ghi vào cùng một thư mục snippet.
4. **Dễ tham chiếu:** ngắn, dễ đọc, không chứa ký tự khiến đường dẫn khó dùng trong hệ điều hành hoặc include Asciidoctor.

Quy ước thực tế:

~~~text
<resource>-<http-action>-<scenario>
~~~

| Identifier | Operation | Ý nghĩa |
| --- | --- | --- |
| `books-list` | `GET /api/books` | Liệt kê sách |
| `books-get` | `GET /api/books/{id}` | Đọc một sách |
| `books-create` | `POST /api/books` | Tạo sách |
| `books-update` | `PUT /api/books/{id}` | Cập nhật sách |
| `books-delete` | `DELETE /api/books/{id}` | Xóa sách |
| `books-get-not-found` | `GET /api/books/{id}` trả `404` | Không tìm thấy |
| `books-create-invalid` | `POST /api/books` trả mã lỗi theo hợp đồng | Dữ liệu tạo không hợp lệ |

Có thể thêm phiên bản API hoặc nhóm tài nguyên:

~~~text
v1-books-get
v1-books-create
v2-books-get
admin-users-list
public-catalog-search
~~~

Không nên đưa mọi chi tiết của request vào tên thư mục. Giá trị ID, query string động, ngày giờ hoặc dữ liệu ngẫu nhiên thường thuộc **dữ liệu của operation**, không phải định danh loại operation. Không tạo `books-get-bk-101` rồi `books-get-bk-102` chỉ vì test dùng hai mã sách khác nhau. Cả hai request đều mô tả cùng hợp đồng `GET /api/books/{id}`; identifier `books-get` thường phù hợp hơn.

## 3. Phân biệt identifier với tên test method và URI

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên test method | `getBookReturnsBookDetails()` | Giải thích mục tiêu kiểm thử trong mã Java. |
| URI template | `/api/books/{id}` | Mô tả đường dẫn HTTP và path parameter. |
| Identifier | `books-get` | Quyết định thư mục chứa snippet được sinh ra. |

Ví dụ:

~~~java
@Test
void getBookReturnsBookDetails() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "bk-101")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("books-get"));
}
~~~

Tên method có thể đổi thành `readBook()` mà không cần đổi identifier. URI có thể chuyển từ `/api/books/{id}` sang `/api/v1/books/{id}` nếu API được version hóa. Identifier tiếp tục là `books-get` nếu muốn giữ nhóm snippet theo tên operation ổn định; nếu v1 và v2 cùng được công bố, nên thêm namespace để tránh va chạm.

Nếu dùng placeholder `{method-name}`, đổi tên test có thể làm đổi thư mục snippet và buộc cập nhật include. Cách này tiện khi tên test chính là cấu trúc tài liệu mong muốn, nhưng **không tối ưu nếu cần đường dẫn tài liệu ổn định qua các lần refactor test**.

## 4. Thiết kế quy ước tên theo tài nguyên và hành động

### 4.1. Dùng danh từ tài nguyên và hành động dễ hiểu

Với REST API, danh từ thể hiện tài nguyên; HTTP method thể hiện loại thao tác:

~~~text
orders-list       GET    /api/orders
orders-get        GET    /api/orders/{id}
orders-create     POST   /api/orders
orders-replace    PUT    /api/orders/{id}
orders-update     PATCH  /api/orders/{id}
orders-delete     DELETE /api/orders/{id}
~~~

Tên `orders-get` rõ hơn các tên chung như `get1`, `test2` hoặc `api-call`. Khi endpoint có nhiều operation GET, bổ sung ý nghĩa:

~~~text
orders-list
orders-search
orders-get
orders-get-history
orders-get-summary
~~~

### 4.2. Thêm kịch bản khi cùng endpoint có nhiều kết quả tài liệu hóa

~~~text
orders-get
orders-get-not-found
orders-get-forbidden
orders-get-invalid-id
~~~

Chỉ tách kịch bản thành identifier riêng khi nó đáng được trình bày như một ví dụ HTTP độc lập trong tài liệu. Không nhất thiết tạo snippet riêng cho mọi nhánh nội bộ không tạo khác biệt có ý nghĩa với client.

### 4.3. Dùng chữ thường và dấu gạch ngang

Quy ước `kebab-case` thường dễ đọc:

~~~text
payment-methods-list
payment-methods-create
payment-methods-delete
~~~

Nên thống nhất viết thường, dùng dấu gạch ngang, tránh dấu cách, dấu tiếng Việt, ký tự đặc biệt và dấu phân cách thừa. Chọn cách gọi nhất quán cho cùng khái niệm, ví dụ `get` thay vì trộn `read`/`fetch`/`retrieve` nếu không có lý do nghiệp vụ. Spring REST Docs cho phép identifier có cấu trúc thư mục, nhưng tên phẳng bằng kebab-case thường đơn giản hơn cho nhóm mới.

## 5. Đặt tên cố định cho các operation trong MockMvc

Ví dụ một controller sách có ba operation. Mỗi test chọn identifier có ý nghĩa, không phụ thuộc tên method:

~~~java
@Test
void getBookReturnsDetails() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "bk-101")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("books-get",
                    pathParameters(
                            parameterWithName("id").description("Mã sách")),
                    responseFields(
                            fieldWithPath("id").description("Mã sách"),
                            fieldWithPath("title").description("Tên sách"))));
}

@Test
void createBookReturnsLocation() throws Exception {
    mockMvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"REST Docs Guide\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().exists(HttpHeaders.LOCATION))
            .andDo(document("books-create",
                    requestFields(
                            fieldWithPath("title").description("Tên sách"))));
}

@Test
void getMissingBookReturnsNotFound() throws Exception {
    mockMvc.perform(get("/api/books/{id}", "missing"))
            .andExpect(status().isNotFound())
            .andDo(document("books-get-not-found"));
}
~~~

Đây là các đoạn test minh họa lời gọi `document(...)`; cần đặt chúng trong test class đã cấu hình MockMvc và Spring REST Docs. Trong thực tế, thêm assertions về body/header và descriptor tương ứng trước khi ghi snippet.

Sau khi chạy test, cây thư mục có thể là:

~~~text
build/generated-snippets/
├── books-get/
├── books-create/
└── books-get-not-found/
~~~

Khi tên method được refactor, các thư mục vẫn giữ nguyên vì identifier là chuỗi cố định. Đây là lợi ích quan trọng khi tài liệu tham chiếu snippet bằng đường dẫn đã ổn định.

## 6. Một test method có nhiều HTTP operation

Một test có thể gửi nhiều request liên tiếp, ví dụ tạo rồi đọc lại tài nguyên:

~~~java
@Test
void createThenReadBook() throws Exception {
    mockMvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New book\"}"))
            .andExpect(status().isCreated())
            .andDo(document("books-create"));

    mockMvc.perform(get("/api/books/{id}", "bk-102"))
            .andExpect(status().isOk())
            .andDo(document("books-get-after-create"));
}
~~~

Mỗi lần `perform(...)` biểu diễn một HTTP operation riêng. Một test method có hai request cần hai identifier nếu muốn ghi hai nhóm snippet khác nhau. Không dùng một identifier duy nhất `books-flow` cho cả hai response, vì file của operation sau có thể ghi đè file cùng tên từ operation trước.

Nếu tài liệu cần trình bày luồng nhiều bước, vẫn giữ snippet riêng theo operation rồi mô tả trình tự ở trang Asciidoctor:

~~~adoc
== Tạo và đọc sách

=== Bước 1: Tạo sách
include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/http-response.adoc[]

=== Bước 2: Đọc sách vừa tạo
include::{snippets}/books-get-after-create/http-request.adoc[]
include::{snippets}/books-get-after-create/http-response.adoc[]
~~~

## 7. Placeholder động: khi nào nên và không nên dùng?

Spring REST Docs hỗ trợ placeholder trong identifier để dùng ngữ cảnh kiểm thử:

~~~java
document("{method-name}");
document("{class-name}/{method-name}");
document("catalog/{method-name}");
~~~

Placeholder có ích khi mỗi method test tạo đúng một operation, tên method được xem là tên tài liệu chính thức, nhóm test có quy ước đặt tên chặt chẽ hoặc muốn tự động phân vùng snippet theo test class.

Identifier tĩnh thích hợp hơn khi đường dẫn include phải ổn định qua đổi tên class/method, một method thực hiện nhiều operation, hoặc tên test mô tả chi tiết triển khai trong khi tên operation tài liệu cần ngắn và theo ngôn ngữ nghiệp vụ.

| Tiêu chí | Identifier tĩnh | Placeholder động |
| --- | --- | --- |
| Ổn định khi refactor tên test | Cao | Có thể thay đổi đường dẫn |
| Ít phải đặt tên tại từng request | Thấp hơn nếu mỗi operation cần tên riêng | Cao |
| Một method ghi nhiều operation | Dễ đặt tên riêng cho từng request | Cần hậu tố hoặc tên riêng |
| Tên folder theo ngôn ngữ nghiệp vụ | Kiểm soát trực tiếp | Phụ thuộc tên test |

Một mẫu kết hợp là prefix cố định và placeholder:

~~~java
document("catalog/{method-name}");
~~~

Cách này nhóm snippet theo tài nguyên nhưng vẫn phụ thuộc tên method. Nếu cần ổn định tuyệt đối, dùng identifier cố định như `catalog-search` hoặc `catalog-get`.

## 8. Tránh collision khi chạy test song song

Nếu hai request ghi vào cùng identifier, chúng cùng nhắm tới một thư mục. Nếu hai test chạy song song và ghi cùng file snippet, kết quả có thể phụ thuộc thứ tự hoàn thành. Vì vậy:

- Mỗi operation độc lập cần một identifier riêng.
- Không dùng chung identifier cho kịch bản thành công và lỗi nếu chúng tạo snippet khác nhau.
- Không tái sử dụng identifier cho test khác class nếu descriptor hoặc response khác nội dung.
- Với test chạy song song, phân vùng identifier theo nhóm test/operation và tránh writer cạnh tranh vào cùng đường dẫn.

Ví dụ phân vùng:

~~~text
v1-books-get
v1-books-create
v2-books-get
v2-books-create
admin-books-get
public-books-search
~~~

Identifier duy nhất không thay thế việc quản lý output directory hay dọn snippet cũ trong build. Nên để build tạo output trong thư mục sinh tự động và đảm bảo tác vụ test/documentation chạy theo trình tự rõ ràng.

## 9. Đặt tên identifier theo quy ước của nhóm

Một quy ước nên được ghi lại và áp dụng thống nhất:

~~~text
<api-version>-<resource>-<action>[-<scenario>]
~~~

Nếu chỉ có một phiên bản API, có thể bỏ phần `api-version`:

~~~text
<resource>-<action>[-<scenario>]
~~~

| Tên chưa tốt | Tên đề xuất | Lý do |
| --- | --- | --- |
| `test1` | `books-get` | Thể hiện tài nguyên và hành động |
| `getBookTest` | `books-get` | Tách tên test khỏi identifier |
| `books-bk101` | `books-get` | Không gắn folder với dữ liệu mẫu |
| `books-get-success-200-json` | `books-get` | Tránh đưa chi tiết đã thể hiện trong snippet vào tên |
| `orders` dùng cho GET và POST | `orders-list` và `orders-create` | Mỗi operation có thư mục riêng |
| `bookNotFoundTestV2` | `books-get-not-found` hoặc `v2-books-get-not-found` | Tên dễ đọc và xác định phạm vi rõ |

Quy tắc nên đủ để tránh trùng và nhận biết operation, đồng thời tránh biến identifier thành một câu mô tả dài.

Trước khi thêm identifier mới, hãy tự kiểm tra: tài nguyên là gì, HTTP method/operation nào, có phải kịch bản đặc biệt cần snippet riêng không, tên đã tồn tại chưa, tên folder có ổn định khi refactor test không và trang tài liệu sẽ tham chiếu đường dẫn nào.

## 10. Liên kết identifier với Asciidoctor và Markdown

Identifier ổn định giúp tài liệu tham chiếu snippet bằng đường dẫn cố định:

~~~adoc
= Books API

== Liệt kê sách
include::{snippets}/books-list/http-request.adoc[]
include::{snippets}/books-list/http-response.adoc[]

== Xem một sách
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]

== Tạo sách
include::{snippets}/books-create/http-request.adoc[]
include::{snippets}/books-create/request-fields.adoc[]
include::{snippets}/books-create/http-response.adoc[]

== Không tìm thấy sách
include::{snippets}/books-get-not-found/http-response.adoc[]
~~~

`{snippets}` phải trỏ đến output directory của Spring REST Docs. Các file include phải khớp chính xác identifier và tên snippet thực tế. Với Markdown, dùng cơ chế chuyển đổi/nhúng snippet do dự án thiết kế; snippet mặc định thường là AsciiDoc.

Khi đổi identifier, cập nhật đồng thời chuỗi identifier trong test/handler, mọi đường dẫn include Asciidoctor, script/template chuyển snippet sang Markdown nếu có, và các tham chiếu trong pipeline build. Không đổi folder đầu ra thủ công sau khi test chạy; identifier trong mã kiểm thử mới là nguồn sinh đường dẫn ở lần build tiếp theo.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Asciidoctor báo thiếu file include | Identifier trong test khác đường dẫn trong include | Mở thư mục `generated-snippets`, đối chiếu tên folder và cập nhật include. |
| Snippet của hai operation bị trộn | Hai request dùng cùng identifier | Tạo identifier riêng theo tài nguyên, method và tình huống. |
| Refactor tên test làm tài liệu không build | Identifier dùng `{method-name}` hoặc `{class-name}` | Chuyển sang identifier tĩnh nếu cần đường dẫn ổn định, hoặc cập nhật include theo tên mới. |
| Thư mục snippet có tên khó hiểu | Identifier dựa trên tên test kỹ thuật hoặc dữ liệu mẫu | Đổi sang tên ngắn theo operation nghiệp vụ. |
| Hai test song song ghi cùng folder | Identifier không duy nhất | Phân vùng identifier, tránh writer cạnh tranh và kiểm soát chạy song song. |
| Không tìm thấy snippet sau test | Request không gắn handler hoặc test dừng trước bước document | Kiểm tra `andDo(document(...))`, assertion và cấu hình `documentationConfiguration(...)`. |
| File snippet cũ vẫn còn sau đổi tên | Output directory chứa artifact từ lần chạy trước | Làm sạch output bằng tác vụ clean/build chuẩn của dự án rồi chạy test tạo lại. |
| Placeholder tạo folder ngoài dự kiến | Chưa đối chiếu cách resolve identifier | Kiểm tra thư mục sinh thật trước khi viết include. |

## 12. Bài thực hành

1. Viết ba test cho `GET /api/books`, `GET /api/books/{id}` và `POST /api/books`. Dùng identifier `books-list`, `books-get` và `books-create`.
2. Đổi tên các phương thức test nhưng giữ identifier cố định; kiểm tra folder không thay đổi.
3. Thêm test `GET` trả `404` và dùng `books-get-not-found`. Đưa hai nhóm snippet thành hai tiểu mục riêng trong Asciidoctor.
4. Tạo test method thực hiện POST rồi GET. Gắn identifier khác nhau cho hai request, sau đó xây tài liệu mô tả tuần tự hai bước.
5. Thử dùng `{method-name}`, đổi tên method và kiểm tra đường dẫn snippet mới. So sánh chi phí cập nhật include với identifier tĩnh.
6. Kiểm tra bộ test chạy song song: tìm identifier trùng và sửa quy ước trước khi đưa vào CI.

**Tiêu chí hoàn thành:** tên operation có ý nghĩa và ổn định; không có hai operation khác nhau ghi chung thư mục; refactor test không vô tình phá đường dẫn tài liệu; Asciidoctor/Markdown tham chiếu đúng snippet được tạo từ lần chạy test hiện tại.

## 13. Checklist trước khi thêm identifier mới

- [ ] Identifier mô tả tài nguyên và operation, không chỉ mô tả tên test.
- [ ] Dùng quy ước nhất quán, ưu tiên chữ thường và dấu gạch ngang.
- [ ] Kịch bản lỗi/response khác biệt có identifier riêng khi cần tài liệu hóa độc lập.
- [ ] Identifier không phụ thuộc ID dữ liệu mẫu hoặc giá trị ngẫu nhiên.
- [ ] Một test method có nhiều request đã đặt tên riêng cho mỗi operation.
- [ ] Placeholder động chỉ được dùng khi sự phụ thuộc vào tên test là chủ ý.
- [ ] Không có test song song nào ghi vào cùng identifier.
- [ ] Mọi include Asciidoctor/Markdown khớp với thư mục snippet thực tế.
- [ ] Build/CI tạo lại snippet trước khi biên soạn và xuất bản tài liệu.

**Ghi nhớ:** Identifier của `document(...)` quyết định thư mục snippet. Đặt tên theo tài nguyên, HTTP operation và kịch bản cần công bố giúp đường dẫn dễ hiểu, tránh ghi đè và ổn định trước thay đổi nội bộ của test. Đây là quy ước nhỏ nhưng có ảnh hưởng trực tiếp đến việc duy trì tài liệu REST API bằng Spring REST Docs.
