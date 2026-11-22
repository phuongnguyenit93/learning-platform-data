# Tài nguyên REST, request và response trong một operation

Trong **Spring REST Docs**, tài liệu API được xây dựng từ những tương tác HTTP đã được kiểm thử. Để đọc đúng một đoạn tài liệu, trước hết cần phân biệt ba khái niệm: **tài nguyên REST (resource)** là đối tượng nghiệp vụ mà API cung cấp; **request** là yêu cầu của client đối với tài nguyên; **response** là kết quả server trả về. Một lần request đi cùng response tương ứng tạo nên một **operation** mà Spring REST Docs có thể ghi lại và mô tả.

Bài học thuộc chương **Mô hình tài liệu**, tập trung vào cách nhìn một operation làm đơn vị tài liệu. Các ví dụ dùng Spring REST Docs với MockMvc; cùng tư duy có thể áp dụng với WebTestClient hoặc REST Assured. Từ operation, chúng ta tạo snippet cho đường dẫn, tham số, header, payload và đưa chúng vào tài liệu Asciidoctor/Markdown trong quy trình build và CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tài nguyên, URI, biểu diễn JSON, request, response và operation.
- Chỉ ra những thành phần HTTP phải mô tả để người dùng gọi đúng một endpoint.
- Thiết kế các operation kiểm thử riêng cho trường hợp thành công và lỗi.
- Gắn tài liệu vào kiểm thử MockMvc để tạo snippet từ request/response thực tế.
- Ghép các snippet thành tài liệu có thể tái tạo trong build và kiểm tra trên CI.

## 2. Tài nguyên REST không đồng nghĩa với một request

Giả sử một dịch vụ quản lý sách có tài nguyên **sách**. URI `/api/books/42` định danh sách có mã `42`; client có thể tương tác với tài nguyên này bằng những HTTP method khác nhau.

| Phương thức và URI | Ý nghĩa nghiệp vụ | Response thường gặp |
| --- | --- | --- |
| `GET /api/books/42` | Đọc biểu diễn của sách 42 | `200 OK` với JSON; `404 Not Found` nếu không có sách |
| `GET /api/books?author=An` | Tìm danh sách sách theo bộ lọc | `200 OK` với danh sách và metadata |
| `POST /api/books` | Yêu cầu tạo một tài nguyên sách mới | `201 Created`, thường kèm header `Location` |
| `PUT /api/books/42` | Thay thế trạng thái tài nguyên theo hợp đồng của API | `200 OK` hoặc `204 No Content` |
| `PATCH /api/books/42` | Cập nhật một phần trạng thái tài nguyên | `200 OK` hoặc `204 No Content` |
| `DELETE /api/books/42` | Xóa sách 42 | `204 No Content` hoặc mã lỗi thích hợp |

**Resource** là khái niệm nghiệp vụ; **URI** là định danh hoặc địa chỉ để truy cập; **representation** là dữ liệu mà client và server trao đổi về resource, chẳng hạn một JSON object. Nhiều URI có thể liên quan đến cùng loại resource và một URI có thể hỗ trợ nhiều method. Vì vậy, một dòng tài liệu cho “resource sách” chưa đủ thay thế cho tài liệu về từng cách tương tác.

Ví dụ, hai yêu cầu cùng dùng `/api/books/42` nhưng `GET` và `DELETE` mang ý nghĩa, điều kiện đầu vào và kết quả khác nhau. Tài liệu cần xác định rõ **method + đường dẫn + trường hợp xử lý**, thay vì chỉ liệt kê URI.

## 3. Operation: đơn vị được quan sát và ghi lại

Một HTTP operation là một lần trao đổi có request và response tương ứng trong quá trình kiểm thử:

```text
Client
  │  GET /api/books/42?locale=vi
  │  Accept: application/json
  ├──────────────────────────────────────► Server
  │
  │  HTTP/1.1 200 OK
  │  Content-Type: application/json
  │  {"id":42,"title":"Spring REST Docs","locale":"vi"}
  ◄──────────────────────────────────────┤
```

Trong mô hình Spring REST Docs:

1. Kiểm thử gửi request bằng MockMvc, WebTestClient hoặc REST Assured.
2. Ứng dụng (hoặc controller trong bài test) tạo response.
3. Kiểm thử xác nhận hành vi bằng các assertion, chẳng hạn HTTP status và trường JSON.
4. Spring REST Docs tiếp nhận request/response của lần thực thi đó và tạo các snippet theo cấu hình `document(...)`.
5. Asciidoctor/Markdown tham chiếu các snippet để trình bày hợp đồng API cho người đọc.

Một operation có **dữ liệu quan sát được** (method, URI, header, body, status) và **mô tả do người viết khai báo** (ý nghĩa tham số, trường JSON, ví dụ). Việc ghi nhận request/response giúp ví dụ bám sát hành vi kiểm thử. Tuy nhiên, một bài test vẫn chỉ chứng minh trường hợp mà nó thực sự chạy qua; nó không tự bao phủ mọi nhánh lỗi, mọi vai trò hay mọi biến thể của API.

### 3.1. Phân tách các thành phần của request

Ví dụ request đọc một cuốn sách:

```http
GET /api/books/42?locale=vi HTTP/1.1
Host: api.example.test
Accept: application/json
```

| Thành phần | Giá trị trong ví dụ | Câu hỏi mà tài liệu phải trả lời |
| --- | --- | --- |
| HTTP method | `GET` | Client cần thực hiện hành động gì? |
| Path | `/api/books/42` | Đường dẫn truy cập và biến nào nằm trong path? |
| Path parameter | `id = 42` | `id` định danh đối tượng nào, có ràng buộc gì? |
| Query parameter | `locale = vi` | Bộ lọc hoặc tùy chọn này có bắt buộc không? |
| Request header | `Accept: application/json` | Client mong đợi định dạng response nào? |
| Request body | Không có trong ví dụ | Có phải gửi payload? Nếu có, gồm các field nào? |

`Accept` cho biết dạng representation mà client muốn nhận; `Content-Type` cho biết kiểu dữ liệu của body **đang được gửi**. Hai header có vai trò khác nhau. Request `GET` ở trên không có body nên không cần mô tả các request field. Với `POST` có JSON body, cần mô tả cả `Content-Type` và cấu trúc payload.

**Path parameter** là một phần của đường dẫn có tên trong route template, ví dụ `{id}`. **Query parameter** nằm sau dấu `?` và thường điều chỉnh cách tìm kiếm, lọc hoặc trình bày. Không được coi `id` trong `/api/books/{id}` là query parameter.

### 3.2. Phân tách các thành phần của response

Ví dụ response thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 42,
  "title": "Spring REST Docs",
  "locale": "vi"
}
```

| Thành phần | Ý nghĩa | Điều cần mô tả |
| --- | --- | --- |
| Status | `200 OK` | Yêu cầu thành công theo trường hợp nào? |
| Response header | `Content-Type` | Kiểu biểu diễn trả về; thêm header khác nếu có hợp đồng |
| Response body | JSON object | Cấu trúc, kiểu và ý nghĩa từng field |
| `id` | Số nguyên | Mã định danh của sách |
| `title` | Chuỗi | Tên sách |
| `locale` | Chuỗi | Ngôn ngữ mà dữ liệu ví dụ sử dụng |

Response không phải lúc nào cũng có JSON body. `204 No Content` thông thường không có body; `404 Not Found` có thể có JSON lỗi hoặc body rỗng tùy thiết kế; `201 Created` thường dùng `Location` để chỉ URI của tài nguyên vừa tạo. **Mỗi trường hợp phải dựa trên hợp đồng và response thực sự**, không suy luận body từ status rồi viết tài liệu theo giả định.

### 3.3. Một resource có thể có nhiều operation tài liệu

Với `GET /api/books/{id}`, tối thiểu cần cân nhắc hai tình huống:

| Operation kiểm thử | Request | Response | Nội dung cần tài liệu hóa |
| --- | --- | --- | --- |
| `books-get` | `GET /api/books/42` | `200` và thông tin sách | Path parameter, response fields, header liên quan |
| `books-get-not-found` | `GET /api/books/999` | `404` và định dạng lỗi (nếu có) | Điều kiện không tìm thấy, status, cấu trúc lỗi |

Đây là **hai lần tương tác riêng** dù cùng route. Đặt định danh snippet khác nhau giúp ví dụ thành công và lỗi không ghi đè lẫn nhau. Khi API còn có `400`, `401`, `403`, `409` hoặc phân trang, hãy bổ sung operation cho những hành vi có ý nghĩa với người tích hợp. Không nhất thiết sinh tài liệu cho mọi kết hợp đầu vào; hãy chọn các tình huống hình thành hợp đồng công khai của API.

## 4. Tạo operation thực tế bằng MockMvc và Spring REST Docs

Ví dụ dưới đây dùng một controller rất nhỏ để tập trung vào ranh giới giữa resource và operation. Controller trả về cùng một sách mẫu hoặc `404`. Trong dự án thực, dữ liệu có thể đến từ repository/service và fixture test cần được chuẩn bị có thể lặp lại.

```java
@RestController
class BookController {

    @GetMapping(
        value = "/api/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<BookDto> getBook(
            @PathVariable long id,
            @RequestParam(defaultValue = "vi") String locale) {

        if (id != 42L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(
            new BookDto(42L, "Spring REST Docs", locale)
        );
    }

    record BookDto(long id, String title, String locale) {}
}
```

Kiểm thử JUnit 5 với MockMvc có thể thiết lập như sau. Các import Java được lược bớt cho dễ đọc; sử dụng `RestDocumentationExtension`, `MockMvcBuilders.standaloneSetup`, `MockMvcRestDocumentation.documentationConfiguration` và các hàm tài liệu hóa tương ứng từ Spring REST Docs. Ví dụ sử dụng API `queryParameters` của Spring REST Docs 3.x.

```java
@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
            .standaloneSetup(new BookController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void getBook_documentation() throws Exception {
        mockMvc.perform(
                get("/api/books/{id}", 42L)
                    .queryParam("locale", "vi")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title").value("Spring REST Docs"))
            .andDo(document("books-get",
                pathParameters(
                    parameterWithName("id")
                        .description("Mã định danh sách cần đọc")
                ),
                queryParameters(
                    parameterWithName("locale")
                        .description("Mã ngôn ngữ của kết quả")
                        .optional()
                ),
                requestHeaders(
                    headerWithName("Accept")
                        .description("Kiểu dữ liệu client muốn nhận")
                ),
                responseFields(
                    fieldWithPath("id")
                        .type(JsonFieldType.NUMBER)
                        .description("Mã định danh sách"),
                    fieldWithPath("title")
                        .type(JsonFieldType.STRING)
                        .description("Tên sách"),
                    fieldWithPath("locale")
                        .type(JsonFieldType.STRING)
                        .description("Mã ngôn ngữ trong response")
                )
            ));
    }
}
```

Ở đoạn kiểm thử này, `get` cần được import từ `RestDocumentationRequestBuilders.get` của Spring REST Docs. Builder đó giữ thông tin URI template `/api/books/{id}` để `pathParameters(...)` nhận ra biến `id`. `MockMvcRequestBuilders.get` thông thường không tự cung cấp thông tin template cần thiết theo cùng cách.

Một nhóm import tĩnh quan trọng:

```java
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
```

Các lớp `JsonFieldType`, `RestDocumentationExtension`, `RestDocumentationContextProvider`, `MockMvc`, `MockMvcBuilders`, `MediaType` và các annotation JUnit/Spring cần được import như bình thường. Dự án cũng cần dependency Spring REST Docs tương thích với Spring Framework/Boot đang dùng.

### 4.1. Vì sao assertion và document cùng nằm trong một test?

`andExpect(status().isOk())` và `jsonPath(...)` kiểm tra kết quả chạy thật. `andDo(document(...))` lấy chính request và response của lần chạy đó để sinh tài liệu. Khi hành vi ứng dụng đổi, assertion có thể thất bại; khi JSON chứa field không được mô tả hoặc thiếu field bắt buộc được mô tả, snippet `responseFields(...)` có thể báo lỗi theo chế độ kiểm tra nghiêm ngặt mặc định.

Do đó test tài liệu hóa có hai vai trò bổ sung nhau:

- **Bằng chứng hành vi:** operation đã đi qua endpoint và thỏa các assertion.
- **Kiểm tra mô tả:** các thành phần được khai báo trong snippet khớp với payload và tham số quan sát được.

Đừng hiểu “đã sinh snippet” là đã kiểm tra đủ cả API. Ví dụ trên chưa xác nhận hợp đồng của `404`, giới hạn locale hay trường hợp thiếu quyền truy cập; chúng cần những test phù hợp nếu nằm trong phạm vi API.

### 4.2. Đọc bộ snippet được sinh ra

Sau khi test thành công, Spring REST Docs thường ghi snippet dưới thư mục build, chẳng hạn `target/generated-snippets/books-get/` với Maven hoặc `build/generated-snippets/books-get/` với Gradle (phụ thuộc cấu hình dự án).

| Snippet | Thể hiện phần nào của operation? |
| --- | --- |
| `http-request.adoc` | Request line, header và body quan sát được |
| `http-response.adoc` | Status line, header và body response quan sát được |
| `curl-request.adoc` | Ví dụ lệnh cURL tương ứng |
| `httpie-request.adoc` | Ví dụ lệnh HTTPie tương ứng |
| `request-body.adoc` / `response-body.adoc` | Body riêng để tiện chèn vào tài liệu |
| `path-parameters.adoc` | Bảng path parameter từ `pathParameters(...)` |
| `query-parameters.adoc` | Bảng query parameter từ `queryParameters(...)` |
| `request-headers.adoc` | Bảng request header từ `requestHeaders(...)` |
| `response-fields.adoc` | Bảng field của response từ `responseFields(...)` |

Những snippet dạng mô tả như `path-parameters.adoc` và `response-fields.adoc` chỉ xuất hiện khi test yêu cầu tạo chúng. Với operation không có body, các snippet body tương ứng có thể rỗng; đừng chèn mục “Request body” vào tài liệu một cách máy móc.

## 5. Operation tạo tài nguyên: request body và response header

Để thấy rõ khác biệt, xét một operation khác, `POST /api/books`:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "title": "HTTP API Design"
}
```

Response giả định theo hợp đồng tạo thành công:

```http
HTTP/1.1 201 Created
Location: /api/books/43
Content-Type: application/json

{
  "id": 43,
  "title": "HTTP API Design"
}
```

Trong operation này, tài liệu phải mô tả:

- Request body có field `title` (kiểu chuỗi, bắt buộc theo ví dụ hợp đồng).
- `Content-Type` của request xác định định dạng JSON gửi đi.
- Status `201 Created` chỉ ra tạo tài nguyên thành công.
- `Location` chỉ tới resource mới và có thể là URI tương đối hoặc tuyệt đối theo hợp đồng dịch vụ.
- Response body cung cấp `id` do server tạo và `title` của resource.

Trong test `POST` thực sự, sau khi gửi JSON bằng `.contentType(MediaType.APPLICATION_JSON).content(...)`, cấu hình snippet có thể là:

```java
.andDo(document("books-create",
    requestHeaders(
        headerWithName("Content-Type")
            .description("Định dạng JSON của request")
    ),
    requestFields(
        fieldWithPath("title")
            .type(JsonFieldType.STRING)
            .description("Tên sách cần tạo")
    ),
    responseHeaders(
        headerWithName("Location")
            .description("URI của sách vừa được tạo")
    ),
    responseFields(
        fieldWithPath("id")
            .type(JsonFieldType.NUMBER)
            .description("Mã sách do server cấp"),
        fieldWithPath("title")
            .type(JsonFieldType.STRING)
            .description("Tên sách đã lưu")
    )
));
```

Đoạn này minh họa **phần `document(...)`** của test tạo sách; để chạy được, controller phải thật sự hỗ trợ `POST /api/books`, test phải kiểm tra status `201`, response body và các header theo hợp đồng. Không ghép snippet `books-create` với response của test `GET`: chúng là hai operation khác nhau.

Nếu một request có field lồng nhau, có thể mô tả bằng đường dẫn JSON, ví dụ `author.name`, `items[].id`. Nếu header hoặc field thực sự không bắt buộc, dùng `optional()` một cách có chủ đích. Không đánh dấu mọi field là optional chỉ để test qua, vì tài liệu sẽ đánh mất hợp đồng bắt buộc của API.

## 6. Mối quan hệ giữa tài liệu resource và tài liệu operation

Tài liệu thường có hai tầng:

- **Tầng resource:** mục đích nghiệp vụ, cách xác định tài nguyên, quy tắc chung, quyền truy cập, các trạng thái và liên kết tới các hành động.
- **Tầng operation:** method, path template, tham số, header, body, status, response fields và ví dụ tương ứng với từng trường hợp.

Ví dụ cấu trúc tài liệu:

```text
Sách (/api/books)
├── Đọc sách: GET /api/books/{id}
│   ├── Thành công: 200 → books-get
│   └── Không tồn tại: 404 → books-get-not-found
├── Tạo sách: POST /api/books
│   ├── Thành công: 201 → books-create
│   └── Dữ liệu sai: 400 → books-create-invalid
└── Xóa sách: DELETE /api/books/{id}
    └── Thành công: 204 → books-delete
```

Đối với một endpoint có nhiều mã response, hãy ghi rõ **điều kiện dẫn đến mã đó**. Chỉ đặt hai đoạn HTTP response liên tiếp mà không nói khi nào xuất hiện sẽ khiến người đọc không xác định được hành vi mong đợi.

Một số quyết định nên được chốt ở tầng hợp đồng: trường nào được phép vắng mặt, field nào có thể là `null`, format ngày giờ, chuẩn mã lỗi, yêu cầu xác thực và cách phân trang. Spring REST Docs có thể mô tả/kiểm tra nhiều thành phần đó, nhưng người viết vẫn phải xác định quy tắc nghiệp vụ trước.

## 7. Đưa snippet operation vào tài liệu Asciidoctor hoặc Markdown

Spring REST Docs tạo các mảnh tài liệu; các mảnh đó cần được biên soạn thành trang hoàn chỉnh. Chẳng hạn một file AsciiDoc cho operation đọc sách:

```asciidoc
=== Đọc chi tiết sách

Lấy thông tin một sách theo mã định danh. Khi tìm thấy, API trả về 200.

==== Ví dụ request
include::{snippets}/books-get/http-request.adoc[]

==== Path parameter
include::{snippets}/books-get/path-parameters.adoc[]

==== Query parameter
include::{snippets}/books-get/query-parameters.adoc[]

==== Ví dụ response
include::{snippets}/books-get/http-response.adoc[]

==== Response fields
include::{snippets}/books-get/response-fields.adoc[]
```

Build phải trỏ attribute `{snippets}` đến thư mục snippet của test và đảm bảo thứ tự công việc:

```text
Chạy kiểm thử HTTP
       │
       ▼
Sinh generated-snippets/
       │
       ▼
Chuyển AsciiDoc thành HTML/PDF (hoặc biên soạn Markdown)
       │
       ▼
Kiểm tra và xuất bản tài liệu
```

Đối với Markdown, có thể dùng một bước build để chèn nội dung snippet hoặc tạo các đoạn Markdown tương ứng; không giả định directive `include::{snippets}/...[]` là cú pháp Markdown được mọi trình biên dịch hỗ trợ. Việc gắn `test` và `asciidoctor`/bước biên soạn vào pipeline CI giúp ngăn tài liệu được xuất bản từ các snippet chưa tái tạo trong lần build đó.

Nếu muốn ví dụ request dễ đọc hơn, có thể dùng preprocessor như `preprocessResponse(prettyPrint())` trong `document(...)`. Khi tài liệu có token hoặc dữ liệu nhạy cảm, cần loại bỏ/che chúng trong ví dụ xuất bản, đồng thời đảm bảo assertion vẫn kiểm tra dữ liệu thích hợp trong test. Cũng có thể chuẩn hóa hostname, port và URI để ví dụ không phụ thuộc máy chạy CI.

## 8. Những lỗi thường gặp khi mô hình hóa operation

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bảng `path-parameters` không tạo được | Test dùng request builder không giữ URI template | Dùng `RestDocumentationRequestBuilders.get/post/...` với `{id}` |
| Response field test lỗi dù status đúng | Payload thêm field chưa mô tả, field được mô tả bị thiếu hoặc kiểu không khớp | Cập nhật hợp đồng hoặc test theo hành vi mong muốn; chỉ dùng `relaxedResponseFields` khi thực sự cần tài liệu hóa một phần |
| Tài liệu `POST` không có body | Chèn snippet từ operation `GET` hoặc test chưa gửi payload | Tạo test và snippet riêng cho `POST`, có `requestFields(...)` |
| Hai trường hợp thành công/lỗi xuất hiện cùng một ví dụ | Dùng chung tên snippet cho các tình huống | Đặt identifier rõ ràng, ví dụ `books-get` và `books-get-not-found` |
| Tài liệu hiển thị host nội bộ/token thật | Request test chứa dữ liệu môi trường hoặc header nhạy cảm | Chuẩn hóa host/URI, lọc hoặc che thông tin trước khi xuất snippet |
| Trang build thiếu file `include` | Test chưa chạy, sai đường dẫn snippets hoặc task build không có dependency cần thiết | Cấu hình sinh snippet trước bước biên soạn, kiểm tra output trong CI |
| Chỉ có response mẫu nhưng không mô tả điều kiện | Thiếu phân tích hành vi operation | Ghi rõ khi nào `200`, `201`, `400`, `404`, v.v. xuất hiện |

Cần phân biệt việc **mô tả** một field trong bảng với việc **kiểm thử nghiệp vụ** của field đó. `responseFields(...)` kiểm tra tài liệu hóa cấu trúc, nhưng không thay thế assertion về giá trị như `jsonPath("$.id").value(42)` hoặc các kiểm tra phân quyền, trạng thái nghiệp vụ và lỗi.

## 9. Bài thực hành tự kiểm tra

Giả sử nhóm đang bổ sung endpoint `GET /api/books/{id}?locale=vi` và `POST /api/books`.

1. Xác định resource chung, path parameter và query parameter của operation đọc sách.
2. Tạo hai test đọc sách cho `200` và `404`, mỗi test có định danh `document(...)` riêng.
3. Trong test `200`, kiểm tra status, một field nghiệp vụ quan trọng và mô tả toàn bộ field trả về; kiểm tra rằng snippet `response-fields.adoc` được tạo.
4. Trong test tạo sách, gửi một JSON request body, xác nhận `201` cùng `Location` rồi mô tả `requestFields`, `responseHeaders` và `responseFields`.
5. Ghép các snippet vào trang tài liệu và chạy lại build từ trạng thái không có snippet cũ. Tài liệu phải được tạo đầy đủ chỉ từ những test của build hiện tại.

**Tiêu chí hoàn thành:** mỗi ví dụ HTTP trong trang tài liệu truy ra được một operation test cụ thể; mỗi field/tham số có ý nghĩa rõ ràng; các tình huống thành công và lỗi không dùng chung snippet; CI sinh lại được tài liệu khi chạy test và build.

## 10. Ghi nhớ

- **Resource** là đối tượng nghiệp vụ; **request** diễn tả điều client muốn làm; **response** thể hiện kết quả của server; **operation** gắn một request với response thực sự trong một lần thực thi.
- Một route có thể sinh nhiều operation cần mô tả, tùy method và tình huống thành công/lỗi.
- Test của Spring REST Docs vừa xác nhận hành vi HTTP qua assertion, vừa tạo snippet từ request/response, header, tham số và JSON field.
- Trang tài liệu hoàn chỉnh cần kết hợp các snippet với giải thích về hợp đồng, đồng thời được tái tạo và kiểm tra trong build/CI.
