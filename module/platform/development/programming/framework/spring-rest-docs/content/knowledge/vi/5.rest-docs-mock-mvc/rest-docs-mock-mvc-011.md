# Xử lý lỗi khi snippet thiếu hoặc request không đạt

## 1. Lần theo pipeline để tìm đúng nguyên nhân

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Với MockMvc, test gửi request qua Spring MVC, kiểm tra response rồi ghi snippet về request, response, payload, tham số và header. Các snippet được biên soạn thành Asciidoctor/Markdown và đưa vào build, CI. Bài này tập trung vào chẩn đoán lỗi trong luồng MockMvc.

Khi thư mục snippet bị thiếu hoặc request không đạt, lỗi có thể xuất hiện ở nhiều bước:

~~~text
Test discovery
     |
     v
MockMvc setup + REST Docs configuration
     |
     v
mockMvc.perform(request)
     |
     v
HTTP response
     |
     v
andExpect(status / header / body)
     |
     v
andDo(document(identifier, snippets...))
     |
     v
generated-snippets/<identifier>/
     |
     v
Asciidoctor / Markdown include
~~~

Nếu test không được chạy, không có operation để ghi. Nếu assertion trước khi ghi tài liệu thất bại, lời gọi document phía sau không được thực hiện. Nếu document chạy nhưng descriptor sai, Spring REST Docs có thể ném lỗi và không ghi đủ snippet. Nếu snippet đã tồn tại nhưng tài liệu không biên soạn được, nguyên nhân có thể nằm ở đường dẫn include.

Do đó, đừng kết luận REST Docs không hoạt động chỉ vì không thấy file. Bài học này giúp phân loại lỗi theo pipeline, đọc log và response, sửa descriptor, kiểm tra identifier/output path và tránh dùng snippet cũ trong CI.

## 2. Xác nhận test thực sự đã chạy

Trước tiên, kiểm tra bài test được phát hiện và thực thi:

~~~bash
./gradlew test
~~~

Có thể lọc theo class hoặc method:

~~~bash
./gradlew test --tests "com.example.docs.BookDocumentationTest"
./gradlew test --tests "com.example.docs.BookDocumentationTest.getBook"
~~~

Với Maven Surefire, dự án thường có thể chạy một class bằng:

~~~bash
mvn -Dtest=BookDocumentationTest test
~~~

Kiểm tra test report để trả lời các câu hỏi:

- Test có được phát hiện hay bị filter loại bỏ?
- Test passed, failed hay skipped?
- Có exception trong `@BeforeEach` trước khi `mockMvc.perform(...)` chạy không?
- Test có đi đến `andDo(document(...))` không?

Nếu test bị skipped hoặc không được phát hiện, Spring REST Docs không có operation để ghi. Khi chạy sai task hoặc filter, thư mục output có thể không xuất hiện dù dependency và cấu hình MockMvc hoàn toàn đúng.

## 3. Không có snippet: kiểm tra cấu hình nền tảng

Một test MockMvc tích hợp Spring REST Docs thường có ba phần: JUnit extension, context provider và builder configuration.

~~~java
@ExtendWith(RestDocumentationExtension.class)
class BookDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
~~~

Các điểm cần xác nhận:

1. Test class đăng ký `RestDocumentationExtension` của JUnit Jupiter, hoặc cơ chế tích hợp phù hợp với framework đang dùng.
2. Phương thức setup nhận `RestDocumentationContextProvider` đúng cách.
3. Builder gọi `apply(documentationConfiguration(restDocumentation))` trước `build()`.
4. Request gọi `andDo(document(...))`, hoặc handler được cấu hình qua `alwaysDo(...)`.
5. Dependency `spring-restdocs-mockmvc` nằm trong test classpath và tương thích với Spring Framework/Spring Boot.

Khi thiếu REST Docs context hoặc builder configuration, lỗi thường xuất hiện lúc setup hay lúc ghi operation. Đọc exception đầu tiên và nguyên nhân gốc trong stack trace; không chỉ nhìn dòng cuối của báo lỗi.

| Cách cấu hình MockMvc | Điều cần kiểm tra |
| --- | --- |
| `standaloneSetup(controller)` | Controller đã được truyền vào; service, advice, converter, validator hoặc filter cần thiết đã đăng ký tường minh. |
| `webAppContextSetup(context)` | Context được Spring Test tải và inject; controller cùng MVC bean cần thiết có trong context. |
| MockMvc tự cấu hình bởi Spring Boot | Annotation/auto-configuration đã bật; test đang gọi đúng MockMvc instance. |

Nếu setup thất bại, request chưa được gửi. Chưa cần điều tra `pathParameters(...)` hay file include cho tới khi MockMvc được tạo thành công.

## 4. Request không đạt: kiểm tra request thực gửi và response thực nhận

Khi `andExpect(...)` thất bại, xác định request có vào đúng handler và response thực tế là gì. Có thể in kết quả:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/books/{id}", "bk-101")
                .accept(MediaType.APPLICATION_JSON))
        .andDo(print())
        .andExpect(status().isOk());
~~~

`print()` hiển thị request, handler, status, header và body trong output test. Chỉ dùng dữ liệu giả; log có thể chứa token, cookie hoặc dữ liệu cá nhân.

Khi cần kiểm tra thủ công, lấy `MvcResult`:

~~~java
MvcResult result = mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andReturn();

int statusCode = result.getResponse().getStatus();
String body = result.getResponse().getContentAsString();
String contentType = result.getResponse().getContentType();
~~~

Các giá trị này giúp so sánh response thực tế với hợp đồng. Trong test thường ngày, ưu tiên matcher rõ ràng như `status()`, `header()`, `content()` và `jsonPath()`.

### Bảng chẩn đoán status phổ biến

| Kết quả | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `404 Not Found` | URL/method không khớp mapping hoặc controller không đăng ký | Kiểm tra URI, mapping, context hoặc builder. |
| `400 Bad Request` | Thiếu request parameter, body không hợp lệ, binding/validation thất bại | Kiểm tra parameter, JSON, kiểu dữ liệu, validator và exception handler. |
| `401 Unauthorized` | Thiếu thông tin xác thực hoặc security filter từ chối request | Kiểm tra authentication setup và filter chain trong MockMvc. |
| `403 Forbidden` | Không đủ quyền hoặc thiếu CSRF token khi endpoint yêu cầu | Kiểm tra quyền, spring-security-test, CSRF và security config. |
| `405 Method Not Allowed` | Dùng sai HTTP method cho URL | Đối chiếu method với mapping của controller. |
| `406 Not Acceptable` | `Accept` không tương thích với response endpoint có thể tạo | Kiểm tra `accept(...)`, `produces` và message converter. |
| `415 Unsupported Media Type` | `Content-Type` hoặc body không tương thích với `consumes` | Kiểm tra `contentType(...)`, request body và converter. |
| `500 Internal Server Error` | Exception trong controller/service hoặc lỗi không được xử lý | Tìm exception gốc, kiểm tra fake/mock dependency và advice. |

Không phải status 4xx nào cũng là test lỗi. Ví dụ test GET mã không tồn tại có thể **mong đợi 404**. Khi đó dùng `status().isNotFound()` và tài liệu hóa response lỗi bằng identifier riêng. Chỉ coi là thất bại khi status thực nhận khác status mà kịch bản quy định.

## 5. Assertion thất bại trước document: vì sao snippet không được tạo?

Chuỗi thông dụng:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.title").value("Spring REST Docs"))
        .andDo(document("books-get"));
~~~

Nếu status hoặc JSONPath assertion ném lỗi, chuỗi không đi tới `andDo(document(...))`. Thư mục `books-get` có thể không tồn tại hoặc không được cập nhật trong lần chạy này.

### Kiểm tra đúng status

Nếu API thiết kế POST trả `201 Created`, matcher phải kiểm tra status đó:

~~~java
mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"REST Docs\"}"))
        .andExpect(status().isCreated())
        .andDo(document("books-create"));
~~~

Không đổi matcher thành `is2xxSuccessful()` chỉ để test qua nếu hợp đồng yêu cầu đúng 201. Matcher quá rộng có thể che giấu lỗi API.

### Kiểm tra header và content type

~~~java
mockMvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"REST Docs\"}"))
        .andExpect(status().isCreated())
        .andExpect(header().exists(HttpHeaders.LOCATION))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andDo(document("books-create"));
~~~

`Accept` là header request biểu thị định dạng mong muốn; `Content-Type` của response cho biết server thực tế trả định dạng nào. Đặt `accept(APPLICATION_JSON)` không tự chứng minh response là JSON.

### Kiểm tra body

~~~java
.andExpect(jsonPath("$.id").value("bk-102"))
.andExpect(jsonPath("$.title").value("REST Docs"))
~~~

Đây là các matcher nối tiếp `perform(...)`. Nếu body có field sai hoặc thiếu, sửa logic endpoint/test data hoặc cập nhật expected value khi hợp đồng thật sự thay đổi. Đừng xóa assertion có ý nghĩa chỉ để snippet được ghi.

## 6. document đã chạy nhưng snippet vẫn lỗi

Nếu request và assertions đều thành công nhưng test lỗi trong `andDo(document(...))`, hãy kiểm tra exception của Spring REST Docs. Nhóm lỗi phổ biến nhất là descriptor không khớp operation.

### 6.1. Thiếu field trong responseFields

Response thực:

~~~json
{
  "id": "bk-101",
  "title": "Spring REST Docs",
  "price": 199000
}
~~~

Descriptor thiếu `price`:

~~~java
responseFields(
        fieldWithPath("id").description("Mã sách"),
        fieldWithPath("title").description("Tên sách"))
~~~

Với descriptor strict mặc định, Spring REST Docs có thể báo còn field chưa được tài liệu hóa. Nếu `price` thuộc hợp đồng công khai, thêm descriptor:

~~~java
responseFields(
        fieldWithPath("id").description("Mã sách"),
        fieldWithPath("title").description("Tên sách"),
        fieldWithPath("price").description("Giá niêm yết"))
~~~

Field lồng nhau cần path đúng, ví dụ `author.name` hoặc `items[].id`. Đối chiếu JSON thực nhận trước khi viết descriptor.

### 6.2. Descriptor trỏ đến field không tồn tại

Nếu khai báo `fieldWithPath("description")` nhưng response không có field này, REST Docs cũng báo lỗi. Kiểm tra:

- Tên JSON field có đúng chính tả và phân biệt chữ hoa/thường không?
- Field có nằm trong object lồng nhau không?
- Field có thực sự được trả trong kịch bản test này không?
- Có nhầm request field với response field không?

`optional()` chỉ phù hợp khi field có thể vắng mặt hợp lệ. `ignored()` hoặc relaxed snippets có thể hữu ích trong trường hợp có chủ ý, nhưng làm giảm mức kiểm soát field chưa được tài liệu hóa. Không sử dụng chúng như cách né lỗi chung.

### 6.3. Path/query parameter descriptor không khớp

Muốn tài liệu hóa path parameter, giữ URI template:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Mã sách"))));
~~~

Nếu viết URL đã thay giá trị như `get("/api/books/bk-101")`, Spring REST Docs không còn tên biến gốc `id` để liên kết theo cách URI template cung cấp. Tương tự, query descriptor cần đúng tên query thực tế:

~~~java
mockMvc.perform(get("/api/books")
                .queryParam("category", "java"))
        .andDo(document("books-search",
                queryParameters(
                        parameterWithName("category")
                                .description("Danh mục cần lọc"))));
~~~

Không dùng `param(...)` rồi mặc định cho rằng query string đã được biểu diễn như mong muốn; dùng `queryParam(...)` khi tài liệu hóa query URL.

### 6.4. Header descriptor không khớp

Trước khi khai báo `responseHeaders(...)`, xác nhận header thật sự tồn tại:

~~~java
.andExpect(header().string(HttpHeaders.LOCATION, "/api/books/bk-102"))
.andDo(document("books-create",
        responseHeaders(
                headerWithName(HttpHeaders.LOCATION)
                        .description("Đường dẫn tài nguyên mới"))))
~~~

Nếu header được thêm bởi filter/interceptor mà standalone setup chưa đăng ký, test standalone có thể không thấy header. Bổ sung thành phần cần thiết hoặc dùng `webAppContextSetup(...)` nếu mục tiêu là kiểm tra cấu hình ứng dụng đầy đủ.

## 7. Kiểm tra identifier, output directory và file cũ

Identifier trong `document("books-get")` quyết định thư mục gốc snippet. Kiểm tra chính xác chuỗi này với đường dẫn include:

~~~java
.andDo(document("books-get"));
~~~

~~~adoc
include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/http-response.adoc[]
~~~

Các nguyên nhân sai đường dẫn thường gặp:

- Test dùng `books-get` nhưng Asciidoctor include `book-get`.
- Identifier có placeholder `{method-name}`, nhưng include giả định tên thư mục cố định.
- Test ghi vào output directory tùy chỉnh, trong khi Asciidoctor trỏ đến `build/generated-snippets`.
- Test chưa chạy hoặc không gọi handler, nhưng thư mục cũ từ lần build trước vẫn còn.
- Tên snippet include không nằm trong bộ snippet được tạo hoặc không được khai báo.

Với Gradle, output mặc định thường ở `build/generated-snippets/`; với Maven thường ở `target/generated-snippets/`. Cấu hình dự án có thể thay đổi vị trí này.

Để loại trừ file cũ, chạy clean cùng test theo quy trình build của dự án:

~~~bash
./gradlew clean test
~~~

Clean giúp loại output còn sót từ lần trước. Không dùng việc folder đã tồn tại làm bằng chứng rằng test hiện tại đã ghi snippet thành công; kiểm tra test report, thời điểm sửa file và file được sinh trong lần chạy hiện tại.

## 8. Lưu ý riêng với alwaysDo

Có thể cấu hình:

~~~java
mockMvc = MockMvcBuilders.standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocumentation))
        .alwaysDo(document("{method-name}"))
        .build();
~~~

`alwaysDo(...)` gọi handler tự động trong quá trình MockMvc xử lý `perform(...)`, trước khi chuỗi `ResultActions` chạy các matcher `andExpect(...)`. Vì vậy, snippet có thể được ghi ngay cả khi assertion phía sau thất bại.

Nếu nhóm muốn chỉ sinh tài liệu sau khi status/header/body đã được xác nhận, dùng:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("bk-101"))
        .andDo(documentationHandler);
~~~

Không cấu hình cùng handler bằng `alwaysDo(...)` và lại gọi `andDo(handler)` trên cùng request; điều đó có thể tạo thao tác ghi lặp. Khi chẩn đoán snippet của test thất bại, xác định handler đang được gắn theo cơ chế nào.

## 9. Phân biệt lỗi test với lỗi biên soạn tài liệu

| Trạng thái | Dấu hiệu | Hành động |
| --- | --- | --- |
| Test thất bại trước khi document | Assertion status/header/body hoặc request exception | Sửa request/endpoint/expected result theo hợp đồng; document phía sau có thể chưa chạy. |
| Test lỗi trong lúc document | Exception của Spring REST Docs như descriptor mismatch hoặc preprocessor | Kiểm tra identifier, snippets, field path, parameter, header và preprocessor. |
| Test tạo snippet thành công nhưng tài liệu lỗi | Asciidoctor không tìm thấy include hoặc Markdown chưa chuyển snippet | Kiểm tra output path, `{snippets}`, identifier, tên file và task dependency. |

File include bị thiếu không nhất thiết là lỗi controller. Ngược lại, Asciidoctor biên soạn thành công cũng không chứng minh API đúng nếu test tài liệu thiếu assertion.

## 10. Ví dụ: query descriptor không khớp request

Giả sử test gửi query tên `lang` nhưng descriptor mô tả `language`:

~~~java
// Sai: request gửi "lang", descriptor lại mô tả "language".
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .queryParam("lang", "vi"))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                queryParameters(
                        parameterWithName("language")
                                .description("Ngôn ngữ"))));
~~~

Nếu controller bỏ qua query không biết đến, request vẫn có thể trả 200. Tuy nhiên, REST Docs không thể coi descriptor `language` là tham số đã xuất hiện. Sửa để khớp hợp đồng thật:

~~~java
mockMvc.perform(get("/api/books/{id}", "bk-101")
                .queryParam("language", "vi"))
        .andExpect(status().isOk())
        .andDo(document("books-get",
                pathParameters(
                        parameterWithName("id").description("Mã sách")),
                queryParameters(
                        parameterWithName("language")
                                .description("Ngôn ngữ phản hồi"))));
~~~

Nếu API không có query parameter đó, bỏ cả query lẫn descriptor. Không thêm tham số giả chỉ để tạo snippet.

## 11. Quy trình chẩn đoán có hệ thống

Khi gặp lỗi, đi lần lượt:

1. **Kiểm tra test report:** bài test có được phát hiện và chạy không?
2. **Kiểm tra setup:** MockMvc đã được tạo; extension và `documentationConfiguration(...)` đã hoạt động chưa?
3. **In request/response:** dùng `andDo(print())` hoặc `MvcResult` để biết request thực gửi, handler được chọn và response thực nhận.
4. **Đọc assertion đầu tiên thất bại:** status, header hay body? Sửa theo hợp đồng API thay vì nới matcher không cần thiết.
5. **Kiểm tra document:** handler có chạy không? Exception nhắc đến field, parameter, header, operation hay preprocessor nào?
6. **Kiểm tra file output:** identifier, output directory và snippet cụ thể có được tạo trong lần chạy này không?
7. **Kiểm tra biên soạn:** `{snippets}` và đường dẫn include có trùng với file thực tế không?
8. **Chạy clean build khi cần:** loại artifact cũ rồi tạo lại snippet và tài liệu theo đúng dependency task.

| Câu hỏi | Nếu không | Nếu có |
| --- | --- | --- |
| Test có được chạy? | Sửa test discovery/filter/task | Kiểm tra setup |
| MockMvc setup thành công? | Kiểm tra context, extension, builder | Kiểm tra request |
| Response đạt assertions? | In response và sửa nguyên nhân HTTP | Kiểm tra document |
| document chạy không exception? | Kiểm tra descriptor và preprocessor | Kiểm tra file output |
| Folder/file snippet mới tồn tại? | Kiểm tra identifier và output directory | Kiểm tra Asciidoctor/Markdown |
| Include trỏ đúng file? | Sửa `{snippets}` hoặc tên include | Kiểm tra build/publish |

## 12. Tích hợp kiểm tra vào build và CI

Một quy trình CI đáng tin cậy phải tạo snippet mới trước khi biên soạn tài liệu:

~~~text
checkout source
     |
     v
clean generated output
     |
     v
run MockMvc documentation tests
     |
     +-- failed -> stop pipeline
     |
     v
verify expected snippets / assemble docs
     |
     +-- missing include -> stop pipeline
     |
     v
publish documentation artifact
~~~

Điểm cần giữ:

- Bước biên soạn tài liệu phụ thuộc vào bước chạy test tạo snippet.
- Test failure hoặc snippet descriptor failure phải làm pipeline dừng.
- Output cũ không được đánh tráo thành output mới của lần chạy hiện tại.
- Có thể thêm bước kiểm tra file snippet bắt buộc hoặc để Asciidoctor fail khi include không tồn tại.
- Không công bố snippet chứa token, cookie, dữ liệu khách hàng hoặc bí mật môi trường.

Snippet mặc định của Spring REST Docs thường ở dạng AsciiDoc. Nếu sản phẩm dùng Markdown, cần bước chuyển đổi hoặc nhúng phù hợp; không giả định mọi file .adoc có thể include nguyên trạng trong Markdown renderer.

## 13. Bài thực hành

1. Bỏ `.apply(documentationConfiguration(restDocumentation))`, chạy test và xác định lỗi ở setup hay lúc ghi snippet.
2. Đổi expected status từ `isCreated()` thành `isOk()` trong test POST, sau đó kiểm tra vì sao test không đạt theo hợp đồng 201.
3. Thêm field JSON `currency` nhưng không thêm descriptor; quan sát lỗi strict của `responseFields(...)` rồi cập nhật mô tả.
4. Đổi identifier từ `books-get` thành `book-get` nhưng giữ nguyên include; xác định bước báo thiếu file và sửa đồng bộ.
5. Tạo test cố ý thất bại ở `andExpect(...)` trước `andDo(document(...))`; kiểm tra handler có được gọi không. Sau đó thử `alwaysDo(...)` và so sánh.
6. Chạy clean test rồi biên soạn tài liệu; xác minh snippet đến từ lần chạy mới, không phải artifact cũ.

**Tiêu chí hoàn thành:** xác định đúng lớp gây lỗi, đọc log/response để tìm nguyên nhân, sửa matcher hoặc descriptor theo hợp đồng thật, kiểm tra identifier/output/include và bảo đảm CI dừng khi test hoặc biên soạn tài liệu thất bại.

## 14. Checklist xử lý lỗi

- [ ] Test thực sự được phát hiện và chạy trong task/filter hiện tại.
- [ ] MockMvc đã cấu hình REST Docs đúng và setup hoàn tất.
- [ ] Request, handler, status, header và body thực nhận đã được kiểm tra.
- [ ] Assertion thất bại được phân biệt với lỗi trong `document(...)`.
- [ ] Descriptor field/parameter/header khớp operation thực tế.
- [ ] Identifier và output directory trùng với đường dẫn Asciidoctor/Markdown.
- [ ] Đã loại trừ artifact snippet cũ khi cần.
- [ ] `alwaysDo(...)` không ghi tài liệu ngoài dự kiến; ưu tiên `andDo(...)` sau assertion khi cần điều kiện đó.
- [ ] Build/CI tạo snippet trước khi biên soạn, và dừng khi test/include thất bại.

**Ghi nhớ:** Khi snippet thiếu, lần theo pipeline từ test discovery đến request, assertion, `document(...)`, file output và include. Xác định đúng bước thất bại sẽ giúp sửa nguyên nhân thực sự, giữ assertions có ý nghĩa và bảo đảm tài liệu REST API phản ánh request/response đã được kiểm chứng.
