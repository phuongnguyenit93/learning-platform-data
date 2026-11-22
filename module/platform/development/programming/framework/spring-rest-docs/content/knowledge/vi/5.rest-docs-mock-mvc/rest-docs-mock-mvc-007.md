# `RestDocumentationResultHandler` và tái sử dụng handler

## 1. Vì sao cần tái sử dụng result handler?

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP. Với tích hợp **MockMvc**, mỗi lần gọi `mockMvc.perform(...)` tạo ra một kết quả HTTP có thể được xác nhận bằng assertion và ghi thành snippet về request, response, payload, tham số hoặc header. Snippet sau đó được biên soạn thành Asciidoctor/Markdown và đưa vào build, CI. Spring REST Docs cũng có tích hợp cho WebTestClient và REST Assured; bài này tập trung vào cách tổ chức handler trong MockMvc.

Ở các bài trước, ta thường viết trực tiếp:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(document("books-get"));
~~~

Khi nhiều test đều cần cùng cách định dạng request/response, cùng bộ snippet mặc định hoặc cùng cấu hình tiền xử lý, việc lặp lại `document(...)` ở mọi test sẽ làm mã kiểm thử dài và dễ thiếu nhất quán. Spring REST Docs cung cấp **`RestDocumentationResultHandler`** để lưu cấu hình ghi tài liệu trong một đối tượng và tái sử dụng đối tượng đó:

~~~java
private RestDocumentationResultHandler documentationHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    documentationHandler = document("{method-name}");
    mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

Sau đó, mỗi request cần tạo snippet chỉ cần:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andDo(documentationHandler);
~~~

`RestDocumentationResultHandler` là một `ResultHandler` của MockMvc. Nó nhận kết quả thực thi request, chuyển tiếp việc ghi operation và snippet cho Spring REST Docs. **Handler có thể tái sử dụng; identifier và bộ snippet của handler cần được thiết kế phù hợp với từng nhóm test.**

## 2. `document(...)` trả về loại đối tượng nào?

Phương thức tĩnh `MockMvcRestDocumentation.document(...)` có các overload nhận identifier và các `Snippet`, rồi trả về một `RestDocumentationResultHandler`. Đối tượng này có thể được truyền vào `andDo(...)` như các `ResultHandler` khác:

~~~java
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

RestDocumentationResultHandler handler = document("books-get");
~~~

Phân biệt ba vai trò:

| Thành phần | Vai trò |
| --- | --- |
| `document("books-get", snippets...)` | Tạo một handler đã gắn identifier và danh sách snippet cần ghi. |
| `RestDocumentationResultHandler` | Đối tượng kết quả có thể truyền vào `andDo(...)` hoặc cấu hình ở builder. |
| `andDo(handler)` | Thực thi handler với kết quả request/response vừa chạy. |

Luồng thực thi:

~~~text
document("identifier", snippets...)
              |
              v
RestDocumentationResultHandler
              |
              +---------------------------+
                                          |
mockMvc.perform(request)                 |
       |                                  |
       v                                  |
andExpect(status/header/body)             |
       |                                  |
       v                                  |
andDo(handler) <--------------------------+
       |
       v
HTTP Operation -> Snippet writers
       |
       v
generated-snippets/<identifier>/
~~~

Điều quan trọng là tạo handler **không tự ghi file**. Snippet chỉ được ghi khi handler được chạy với kết quả của request, chẳng hạn qua `andDo(handler)` hoặc được gọi tự động thông qua `alwaysDo(handler)` trong MockMvc builder.

## 3. Tạo handler trong `@BeforeEach` và gọi lại ở nhiều test

Đây là mẫu cơ bản khi mỗi phương thức test thường thực hiện một operation cần tài liệu. Dùng `{method-name}` để identifier lấy theo tên phương thức test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CatalogDocumentationTest {

    private MockMvc mockMvc;
    private RestDocumentationResultHandler documentationHandler;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        documentationHandler = document("{method-name}");

        mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getCatalog() throws Exception {
        mockMvc.perform(get("/api/catalog")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(documentationHandler);
    }

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/catalog/{id}", "bk-101")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andDo(documentationHandler);
    }

    @Test
    void createBook() throws Exception {
        mockMvc.perform(post("/api/catalog")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"REST Docs\"}"))
                .andExpect(status().isCreated())
                .andDo(documentationHandler);
    }
}
~~~

Trong ví dụ, `document("{method-name}")` được tạo lại ở mỗi `@BeforeEach`, nên identifier được giải quyết theo method đang chạy, ví dụ `getCatalog`, `getBook`, `createBook`. Những test này vẫn dùng cùng một cách ghi snippet mà không phải lặp lời gọi `document(...)` với tên cố định.

Các class test minh họa `CatalogController` cần được định nghĩa trong test hoặc thay bằng controller thực tế của dự án. Mục tiêu của ví dụ là mô tả vòng đời handler, không phải tạo thêm một cấu hình ứng dụng đầy đủ.

## 4. Tái sử dụng handler cùng bộ snippet tùy chỉnh

Handler có thể được tạo cùng các snippet descriptor, tiền xử lý request/response và identifier. Khi cùng một nhóm test có cấu trúc response thống nhất, cấu hình này giúp chuẩn hóa tài liệu:

~~~java
import org.springframework.restdocs.mockmvc.RestDocumentationResultHandler;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

private RestDocumentationResultHandler documentationHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    documentationHandler = document(
            "{method-name}",
            preprocessRequest(prettyPrint()),
            preprocessResponse(prettyPrint()),
            responseFields(
                    fieldWithPath("id").description("Mã tài nguyên"),
                    fieldWithPath("title").description("Tên tài nguyên")));

    mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

Đây là **mẫu cấu hình rút gọn**; chỉ sử dụng chung descriptor trên cho các response thật sự có cả `id` và `title`. Nếu response của các endpoint có cấu trúc khác nhau, không ép chúng dùng chung `responseFields(...)`. Thay vào đó, tạo các handler chuyên biệt hoặc truyền descriptor riêng ở test tương ứng.

Ví dụ:

~~~java
private RestDocumentationResultHandler bookHandler;
private RestDocumentationResultHandler categoryHandler;

@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    bookHandler = document(
            "books/{method-name}",
            responseFields(
                    fieldWithPath("id").description("Mã sách"),
                    fieldWithPath("title").description("Tên sách")));

    categoryHandler = document(
            "categories/{method-name}",
            responseFields(
                    fieldWithPath("id").description("Mã danh mục"),
                    fieldWithPath("name").description("Tên danh mục")));

    mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

Tên identifier trong ví dụ được phân vùng theo nhóm tài nguyên. Khi dùng placeholder động, kiểm tra đường dẫn snippet thực tế do Spring REST Docs tạo ra trong lần chạy test; đừng tự suy ra tên thư mục chỉ từ tên biến handler.

## 5. Dùng `alwaysDo(handler)` khi muốn ghi mọi request

MockMvc builder cung cấp `alwaysDo(...)` để tự động chạy một `ResultHandler` sau mỗi request được thực thi qua MockMvc đó. Có thể dùng để tránh gọi `andDo(documentationHandler)` ở mọi test:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class AutomaticallyDocumentedApiTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        RestDocumentationResultHandler documentationHandler =
                document("{method-name}");

        mockMvc = MockMvcBuilders.standaloneSetup(new CatalogController())
                .apply(documentationConfiguration(restDocumentation))
                .alwaysDo(documentationHandler)
                .build();
    }

    @Test
    void getBook() throws Exception {
        mockMvc.perform(get("/api/catalog/{id}", "bk-101"))
                .andExpect(status().isOk());
    }
}
~~~

Với cấu hình này, handler được áp dụng cho tất cả request đi qua `mockMvc`, kể cả request trong test không có `.andDo(...)`. Điều đó tiện cho bộ test mà **mỗi request đều cần snippet**.

`alwaysDo(...)` cũng có hệ quả: request phụ trợ, request dùng để thiết lập trạng thái hoặc request cố ý tạo response lỗi cũng được ghi. Nếu không muốn tài liệu hóa mọi request, hãy dùng `andDo(...)` có chọn lọc. Đặc biệt, không vừa cấu hình `alwaysDo(documentationHandler)` vừa thêm `.andDo(documentationHandler)` cho cùng request, vì handler có thể được gọi hai lần và ghi operation trùng lặp.

**Khác biệt quan trọng về thứ tự kiểm chứng:** handler đăng ký bằng `alwaysDo(...)` được MockMvc gọi tự động trong quá trình `perform(...)`, trước khi chuỗi `ResultActions` trả về cho test tiếp tục gọi `andExpect(...)`. Vì vậy, snippet có thể đã được ghi dù assertion viết sau `perform(...)` thất bại. Nếu yêu cầu của nhóm là chỉ sinh tài liệu sau khi status/header/body đã được xác nhận, hãy dùng `andDo(handler)` đặt sau các `andExpect(...)` thay vì `alwaysDo(handler)`.

## 6. Chọn `andDo(handler)` hay `alwaysDo(handler)`?

| Tiêu chí | `andDo(documentationHandler)` | `alwaysDo(documentationHandler)` |
| --- | --- | --- |
| Phạm vi | Chỉ request được gắn handler | Mọi request thực thi qua MockMvc đã cấu hình |
| Kiểm soát | Rõ ràng tại từng test | Tập trung tại builder |
| Phù hợp | Test có request phụ, test nhiều kịch bản hoặc chỉ một số endpoint cần tài liệu | Bộ test tài liệu mà hầu hết request đều cần snippet |
| Rủi ro | Có thể quên gắn handler ở một test | Có thể sinh snippet ngoài ý muốn cho request phụ |
| Khả năng đọc test | Nhìn thấy rõ điểm ghi tài liệu | Test ngắn hơn nhưng phải biết cấu hình chung |

Một quy tắc hữu ích:

- Chọn **`andDo(handler)`** khi cần chủ động quyết định request nào được công bố.
- Chọn **`alwaysDo(handler)`** khi mọi request đều được tài liệu hóa và identifier tránh va chạm.
- Nếu một test thực hiện nhiều request khác nhau, cân nhắc tạo handler riêng và dùng `andDo(...)` tường minh cho từng request.

## 7. Identifier: tránh ghi đè snippet

Identifier xác định thư mục chứa snippet của operation. Khi tái sử dụng handler, phải đảm bảo các lần gọi ghi ra **đường dẫn khác nhau** nếu chúng biểu diễn operation khác nhau.

Ví dụ không tốt:

~~~java
RestDocumentationResultHandler handler = document("api-operation");
~~~

Nếu handler này được dùng cho nhiều request có response khác nhau, chúng cùng nhắm tới thư mục `api-operation`. File trùng tên có thể bị ghi đè, khiến kết quả build phụ thuộc thứ tự chạy test.

Có thể dùng placeholder:

~~~java
document("{method-name}");
document("{class-name}/{method-name}");
document("catalog/{method-name}");
~~~

Các placeholder như `{method-name}` và `{class-name}` cho phép xây identifier theo ngữ cảnh test. Một identifier có cấu trúc thường giúp phân nhóm snippet và đọc được mối quan hệ giữa file tài liệu với phương thức kiểm thử.

Khi một method có nhiều operation:

~~~java
@Test
void updateThenReadBook() throws Exception {
    mockMvc.perform(put("/api/books/{id}", "bk-101")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New title\"}"))
            .andExpect(status().isNoContent())
            .andDo(document("books-update"));

    mockMvc.perform(get("/api/books/{id}", "bk-101"))
            .andExpect(status().isOk())
            .andDo(document("books-get-after-update"));
}
~~~

Ở đây mỗi operation cần identifier riêng. Nếu chỉ dùng `{method-name}` cho cả hai handler trong cùng method, cả hai có thể cùng ghi vào một thư mục. Hãy bổ sung tên operation cụ thể như `books-update` và `books-get-after-update`, hoặc đặt identifier theo một quy ước kết hợp method và vai trò operation.

## 8. Tái sử dụng handler với tiền xử lý dữ liệu

Handler thường được dùng để chuẩn hóa cách hiển thị request/response. Ví dụ tất cả JSON snippet của một nhóm test đều được định dạng:

~~~java
RestDocumentationResultHandler jsonDocumentation =
        document(
                "{method-name}",
                preprocessRequest(prettyPrint()),
                preprocessResponse(prettyPrint()));
~~~

Sau đó:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andDo(jsonDocumentation);
~~~

Tiền xử lý được chạy trên dữ liệu operation dùng để ghi snippet. Nó giúp nội dung file dễ đọc hơn, nhưng không thay đổi mục tiêu kiểm tra của `andExpect(...)`. Nếu cần ẩn header hoặc giá trị nhạy cảm trong tài liệu, cấu hình preprocessor phù hợp và kiểm tra snippet đã sinh; không đưa credential thật vào test hoặc file được công bố.

Khi nhiều endpoint dùng cùng một preprocessor nhưng descriptor khác nhau, có thể tạo nhiều handler với cùng quy tắc tiền xử lý:

~~~java
RestDocumentationResultHandler bookDocumentation =
        document("{method-name}",
                preprocessResponse(prettyPrint()),
                responseFields(
                        fieldWithPath("id").description("Mã sách"),
                        fieldWithPath("title").description("Tên sách")));

RestDocumentationResultHandler categoryDocumentation =
        document("{method-name}",
                preprocessResponse(prettyPrint()),
                responseFields(
                        fieldWithPath("id").description("Mã danh mục"),
                        fieldWithPath("name").description("Tên danh mục")));
~~~

Để tránh trùng thư mục nếu hai nhóm handler cùng dùng trong một test class, hãy phân vùng identifier theo tài nguyên, ví dụ `books/{method-name}` và `categories/{method-name}`.

## 9. Tổ chức test và handler theo nhóm API

Trong một dự án lớn, nên thống nhất quy ước ở cấp test class:

| Nhóm test | Handler đề xuất | Lý do |
| --- | --- | --- |
| Một endpoint/operation trong mỗi test method | Một handler dùng `{method-name}` | Dễ tái sử dụng, identifier tự phân biệt theo method. |
| Nhiều endpoint cùng cấu trúc response | Một handler chung có descriptor tương thích | Tránh lặp cấu hình snippet và tiền xử lý. |
| Nhiều endpoint với payload khác nhau | Handler riêng cho từng nhóm schema | Không ép descriptor của endpoint này lên endpoint khác. |
| Test chứa nhiều request | Handler riêng gắn bằng `andDo(...)` | Tránh ghi các operation khác nhau vào cùng identifier. |
| Bộ test chỉ chứa request được tài liệu hóa | `alwaysDo(...)` | Giảm lặp và bảo đảm mọi request trong scope được ghi. |
| Test có request phụ hoặc request kiểm tra lỗi không công bố | `andDo(...)` có chọn lọc | Chỉ ghi những operation được chọn. |

Không nên tạo một handler dùng chung toàn module chỉ vì mọi test đều dùng MockMvc. Handler nên phản ánh phạm vi descriptor và quy ước identifier. Khi cấu trúc response thay đổi, các nhóm test dùng descriptor chung có thể cùng thất bại; đó là tín hiệu cần rà soát hợp đồng và phân tách handler nếu schema thực tế khác nhau.

## 10. Snippet được tạo ở đâu và đưa vào tài liệu thế nào?

Với Gradle:

~~~bash
./gradlew test
~~~

Thư mục mặc định thường là `build/generated-snippets/`; với Maven thường là `target/generated-snippets/`. Đường dẫn thật còn phụ thuộc cấu hình output của Spring REST Docs và build.

Ví dụ test có identifier `getBook` và `createBook` có thể tạo cây file:

~~~text
build/generated-snippets/
├── getBook/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── curl-request.adoc
│   └── response-body.adoc
└── createBook/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── request-fields.adoc
    └── response-fields.adoc
~~~

Đây là ví dụ rút gọn. Các snippet chính xác phụ thuộc vào bộ mặc định, danh sách `Snippet` truyền cho `document(...)`, và dữ liệu operation.

Một trang Asciidoctor có thể nhúng các snippet:

~~~adoc
= Catalog API

== Lấy sách

include::{snippets}/getBook/http-request.adoc[]
include::{snippets}/getBook/http-response.adoc[]

== Tạo sách

include::{snippets}/createBook/http-request.adoc[]
include::{snippets}/createBook/request-fields.adoc[]
include::{snippets}/createBook/http-response.adoc[]
include::{snippets}/createBook/response-fields.adoc[]
~~~

Tên thư mục trong ví dụ phải khớp identifier được handler thực sự tạo ra. Với placeholder như `{method-name}`, cần kiểm tra output thực tế để viết đúng đường dẫn include. Nếu xuất bản Markdown, cần bước chuyển đổi hoặc nhúng snippet phù hợp vì snippet mặc định thường ở định dạng AsciiDoc.

Build/CI nên thực hiện theo thứ tự **chạy test → ghi snippet → biên soạn tài liệu → xuất bản**. Tác vụ biên soạn cần phụ thuộc vào tác vụ test để không dùng lại snippet cũ.

## 11. Lỗi thường gặp khi tái sử dụng handler

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có snippet | Handler chỉ được tạo nhưng chưa gắn với `andDo(...)`/`alwaysDo(...)` | Kiểm tra request có thực sự gọi handler không. |
| Lỗi thiếu REST Docs context | Chưa đăng ký `RestDocumentationExtension` hoặc thiếu `documentationConfiguration(...)` | Cấp `RestDocumentationContextProvider`; áp dụng cấu hình trước `build()`. |
| Snippet bị ghi đè | Nhiều operation dùng cùng identifier | Dùng identifier duy nhất cho mỗi operation. |
| Descriptor lỗi ở một endpoint | Handler chung chứa field/header không xuất hiện ở endpoint đó | Tách handler theo schema hoặc tạo descriptor riêng. |
| Mọi request phụ đều bị ghi | Handler được cấu hình bằng `alwaysDo(...)` | Chuyển sang `andDo(...)` có chọn lọc hoặc tách MockMvc/test scope. |
| Cùng request tạo snippet hai lần | Vừa dùng `alwaysDo(handler)` vừa gọi `andDo(handler)` | Chỉ gắn handler theo một cơ chế cho request đó. |
| Nhiều request trong cùng method ghi chung thư mục | Identifier chỉ có `{method-name}` | Đặt identifier theo operation riêng trong method đó. |
| Include Asciidoctor không tìm thấy file | Đường dẫn giả định không trùng identifier đã resolve | Mở thư mục output và dùng tên file thực tế. |
| Nội dung snippet không đúng định dạng | Thiếu preprocessor hoặc dùng handler khác cấu hình | Chuẩn hóa handler và kiểm tra snippet output. |
| Test không mô tả được một số field | Dùng descriptor chung nhưng các response khác schema | Tách handler; không nới lỏng descriptor nếu API cần tài liệu strict. |

### Lưu ý về vòng đời và chia sẻ đối tượng

Tạo handler trong `@BeforeEach` là cách dễ hiểu vì mỗi test được chuẩn bị một cấu hình handler có identifier theo method. Cũng có thể lưu handler ở field và tái sử dụng khi cấu hình không phụ thuộc dữ liệu test. Dù chọn cách nào:

- Không thay đổi identifier hoặc danh sách snippet trong lúc test đang chạy.
- Tránh để nhiều test ghi đồng thời vào cùng một identifier/thư mục.
- Không dùng chung một handler với descriptor không tương thích cho các endpoint khác schema.
- Khi sử dụng `alwaysDo(...)`, nhận thức rõ mọi request qua MockMvc đó đều đi qua handler.

## 12. Bài thực hành

1. Tạo `RestDocumentationResultHandler` trong `@BeforeEach` với identifier `{method-name}`; dùng lại handler trong hai test GET khác nhau và kiểm tra hai thư mục snippet.
2. Chuyển handler sang `alwaysDo(...)`; chạy một test có hai request và quan sát cả hai operation được ghi. Đặt identifier phù hợp để chúng không va chạm.
3. Tạo một test cập nhật rồi đọc lại tài nguyên; dùng hai handler hoặc hai identifier riêng cho hai request.
4. Tái sử dụng preprocessor `prettyPrint()` cho nhiều handler nhưng đặt descriptor riêng cho schema Book và Category.
5. Cố ý dùng chung identifier cho hai operation và quan sát vấn đề output; sửa lại quy ước tên để mỗi operation có thư mục riêng.
6. Nhúng snippet vào Asciidoctor, chạy test trước khi biên soạn và kiểm tra dependency của tác vụ tài liệu trong CI.

**Tiêu chí hoàn thành:** biết cách tạo và dùng `RestDocumentationResultHandler`; phân biệt `andDo(handler)` với `alwaysDo(handler)`; tái sử dụng đúng bộ descriptor/preprocessor; identifier không va chạm; snippet được biên soạn từ output của lần test hiện tại.

## 13. Checklist sử dụng handler trong dự án

- [ ] MockMvc đã được tích hợp bằng `documentationConfiguration(...)` hoặc cơ chế tự cấu hình phù hợp.
- [ ] `RestDocumentationResultHandler` được tạo từ `document(identifier, snippets...)`.
- [ ] Handler được gắn bằng `andDo(...)` hoặc `alwaysDo(...)`, không vô tình dùng cả hai cho cùng request.
- [ ] Identifier được phân biệt cho từng operation, kể cả khi một test method thực hiện nhiều request.
- [ ] Descriptor dùng chung tương thích với tất cả response/request được handler ghi.
- [ ] Preprocessor được cấu hình nhất quán và không làm lộ dữ liệu nhạy cảm trong snippet công khai.
- [ ] Đã kiểm tra đường dẫn output thực tế và include trong Asciidoctor/Markdown.
- [ ] Build/CI tạo snippet mới sau khi test thành công rồi mới biên soạn/xuất bản tài liệu.

**Ghi nhớ:** `RestDocumentationResultHandler` cho phép gói identifier, snippet và cấu hình ghi tài liệu thành một đối tượng có thể tái sử dụng. `andDo(handler)` cho quyền chọn từng request; `alwaysDo(handler)` áp dụng handler cho mọi request của MockMvc. Lựa chọn đúng phạm vi, descriptor và identifier giúp giảm lặp mà vẫn tạo tài liệu REST API rõ ràng, không trùng lặp và có thể kiểm chứng.
