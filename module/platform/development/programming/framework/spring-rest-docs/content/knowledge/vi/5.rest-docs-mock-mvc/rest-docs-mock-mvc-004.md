# Thực hiện request bằng MockMvc

## 1. Mục tiêu bài học

Trong Spring MVC, **MockMvc** cho phép gửi request HTTP mô phỏng đến `DispatcherServlet` rồi quan sát response mà không cần khởi động một máy chủ HTTP thật. Đây là một cách quan trọng để kiểm thử controller, ánh xạ URL, kiểu nội dung, header, tham số, body và mã trạng thái.

Với **Spring REST Docs**, request thực thi trong bài kiểm thử còn là nguồn dữ liệu để sinh các **snippet** có thể kiểm chứng: request/response HTTP, ví dụ `curl`, JSON payload, path/query parameter, form parameter, request part, request/response header. Các snippet sau đó được đưa vào tài liệu Asciidoctor/Markdown và quy trình build/CI. Cơ chế tương tự cũng có thể áp dụng qua WebTestClient hoặc REST Assured; bài này tập trung vào nhánh **MockMvc**.

Sau bài học, bạn có thể:

- Tạo các HTTP request GET, POST, PUT, PATCH, DELETE bằng `MockMvcRequestBuilders`.
- Cung cấp URI template, query/form parameter, header, cookie, session, body JSON và multipart.
- Phân biệt request builder, `mockMvc.perform(...)`, `andExpect(...)`, `andDo(...)` và `andReturn()`.
- Tạo snippet Spring REST Docs từ request đã chạy và được kiểm chứng.
- Xác định lỗi thường gặp khi test dùng sai URL, `Content-Type`, `Accept`, payload hoặc descriptor.

## 2. Luồng thực thi: từ request builder đến snippet

Một request MockMvc thường có cấu trúc:

```java
mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .header("X-Correlation-Id", "req-001")
                .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value("task-100"))
        .andDo(document("tasks-get-basic"));
```

| Thành phần | Mục đích |
| --- | --- |
| `get(...)`, `post(...)`, `put(...)`, `patch(...)`, `delete(...)` | Tạo `MockHttpServletRequestBuilder`, biểu diễn phương thức, URI và dữ liệu request cần gửi. |
| `mockMvc.perform(builder)` | Thực thi request bằng cơ chế Spring MVC đã cấu hình và trả về `ResultActions`. |
| `andExpect(resultMatcher)` | Kiểm tra response như status, header, content type, JSON field; assertion sai làm test thất bại. |
| `andDo(resultHandler)` | Thực hiện hành động sau request, ví dụ `print()` hoặc Spring REST Docs `document(...)`. |
| `andReturn()` | Lấy `MvcResult` để kiểm tra thêm request/response đã xử lý; thường không cần khi các matcher đã đủ. |

```text
MockMvcRequestBuilders.get/post/put/...
         |
         +-- URI template, query/form params, headers, cookies, body
         |
         v
    mockMvc.perform(...)
         |
         v
  DispatcherServlet (trong test)
         |
         v
    HTTP response mô phỏng
         |
         +-- andExpect(...): kiểm chứng hành vi
         |
         +-- andDo(document(...)): ghi snippet vào generated-snippets
         |
         +-- andReturn(): nhận MvcResult (nếu cần)
```

**Lưu ý:** `MockMvc` không truy cập mạng khi xử lý request thông thường. Nó chạy request bằng hạ tầng servlet/MVC mô phỏng trong cùng tiến trình test. Kết quả có giá trị trong phạm vi controller, bean, filter và các thành phần đã được cấu hình cho chính test đó.

## 3. Chuẩn bị MockMvc tích hợp Spring REST Docs

Ví dụ sử dụng **Java 17+, Spring MVC, Spring Boot 3.x, JUnit Jupiter** và Gradle. Nếu đã dùng Spring Boot dependency management, các phiên bản dependency tương thích nên được quản lý qua BOM của dự án.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Với một controller độc lập, có thể cấu hình trong `@BeforeEach`:

```java
@ExtendWith(RestDocumentationExtension.class)
class TaskRequestDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }
}
```

Các kiểu và method được import từ `org.junit.jupiter.api`, `org.springframework.restdocs`, `org.springframework.test.web.servlet` và static import `MockMvcRestDocumentation.documentationConfiguration`. `RestDocumentationExtension` cung cấp ngữ cảnh test cho Spring REST Docs. Nếu controller cần service, converter, advice hay filter đặc thù, thêm chúng vào builder theo phạm vi test hoặc sử dụng `webAppContextSetup(context)` để lấy cấu hình MVC từ web application context.

`documentationConfiguration(restDocumentation)` **cấu hình bộ ghi tài liệu**; nó không tự ghi mọi request. Để ghi request cụ thể thành snippet, sử dụng `.andDo(document(...))`, và nên kiểm chứng response trước khi ghi.

## 4. Ví dụ đầy đủ: GET, POST và DELETE có tài liệu

Giả sử API quản lý công việc có ba endpoint:

- `GET /api/tasks/{id}?includeDetails=true`: lấy công việc, đọc path/query parameter và header truy vết.
- `POST /api/tasks`: nhận JSON chứa `title`, tạo công việc và trả `201 Created`.
- `DELETE /api/tasks/{id}`: xóa công việc, trả `204 No Content`.

Lớp kiểm thử sau đặt một controller mẫu ngay trong test để thể hiện rõ cách dựng request và tạo snippet. Trong dự án thật, dùng controller của mã ứng dụng và dữ liệu test phù hợp.

```java
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class TaskRequestDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new TaskController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetTask() throws Exception {
        mockMvc.perform(get("/api/tasks/{id}", "task-100")
                        .queryParam("includeDetails", "true")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Correlation-Id", "req-001"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string("X-Correlation-Id", "req-001"))
                .andExpect(jsonPath("$.id").value("task-100"))
                .andExpect(jsonPath("$.details").value("Có thêm thông tin"))
                .andDo(document("tasks-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã công việc")),
                        queryParameters(
                                parameterWithName("includeDetails")
                                        .description("Có trả về chi tiết hay không")),
                        requestHeaders(
                                headerWithName("Accept")
                                        .description("Định dạng response mong muốn"),
                                headerWithName("X-Correlation-Id")
                                        .description("Mã truy vết của request")),
                        responseHeaders(
                                headerWithName("X-Correlation-Id")
                                        .description("Mã truy vết phản hồi")),
                        responseFields(
                                fieldWithPath("id").description("Mã công việc"),
                                fieldWithPath("title").description("Tên công việc"),
                                fieldWithPath("state").description("Trạng thái"),
                                fieldWithPath("details")
                                        .description("Thông tin bổ sung"))));
    }

    @Test
    void documentCreateTask() throws Exception {
        mockMvc.perform(post("/api/tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Viết tài liệu API"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/tasks/task-101"))
                .andExpect(jsonPath("$.id").value("task-101"))
                .andExpect(jsonPath("$.title").value("Viết tài liệu API"))
                .andDo(document("tasks-create",
                        requestFields(
                                fieldWithPath("title")
                                        .description("Tên công việc cần tạo")),
                        responseHeaders(
                                headerWithName("Location")
                                        .description("Địa chỉ tài nguyên mới")),
                        responseFields(
                                fieldWithPath("id").description("Mã công việc mới"),
                                fieldWithPath("title").description("Tên công việc"),
                                fieldWithPath("state").description("Trạng thái"))));
    }

    @Test
    void documentDeleteTask() throws Exception {
        mockMvc.perform(delete("/api/tasks/{id}", "task-101"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""))
                .andDo(document("tasks-delete",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã công việc cần xóa"))));
    }

    @RestController
    public static class TaskController {

        @GetMapping(value = "/api/tasks/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, Object>> find(
                @PathVariable("id") String id,
                @RequestParam("includeDetails") boolean includeDetails,
                @RequestHeader("X-Correlation-Id") String correlationId) {

            Map<String, Object> task = new LinkedHashMap<>();
            task.put("id", id);
            task.put("title", "Học MockMvc");
            task.put("state", "OPEN");
            if (includeDetails) {
                task.put("details", "Có thêm thông tin");
            }
            return ResponseEntity.ok()
                    .header("X-Correlation-Id", correlationId)
                    .body(task);
        }

        @PostMapping(value = "/api/tasks",
                     consumes = MediaType.APPLICATION_JSON_VALUE,
                     produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> create(
                @RequestBody Map<String, String> request) {
            return ResponseEntity.created(URI.create("/api/tasks/task-101"))
                    .body(Map.of(
                            "id", "task-101",
                            "title", request.get("title"),
                            "state", "OPEN"));
        }

        @DeleteMapping("/api/tasks/{id}")
        public ResponseEntity<Void> deleteById(@PathVariable("id") String id) {
            return ResponseEntity.noContent().build();
        }
    }
}
```

### Phân tích kết quả

1. **Request GET:** `get("/api/tasks/{id}", "task-100")` đưa tên `id` vào URI template và thay bằng giá trị thực tế. `queryParam("includeDetails", "true")` thêm query vào URL, `accept(...)` đặt header `Accept`, `header(...)` đặt header truy vết. Các descriptor tương ứng lấy đúng thông tin từ request.
2. **Request POST:** `contentType(...)` báo cho controller cách đọc body; `content(...)` truyền chuỗi JSON thực tế. `requestFields(...)` mô tả trường `title`, còn `responseFields(...)` mô tả JSON trả về. Header `Location` được kiểm chứng và tài liệu hóa.
3. **Request DELETE:** vì response `204` không có payload, test kiểm tra body rỗng và chỉ mô tả path parameter; không khai báo `responseFields(...)` cho JSON không tồn tại.
4. **Kết quả được kiểm chứng:** `andExpect(...)` chạy sau `perform(...)` và trước `andDo(document(...))`. Nếu assertion thất bại, chuỗi gọi thông thường dừng tại assertion đó và bài test thất bại.
5. **Snippet phân tách theo thao tác:** `tasks-get`, `tasks-create`, `tasks-delete` là các identifier độc lập. Mỗi lần ghi tài liệu tạo hoặc cập nhật các snippet của request tương ứng.

Controller trong ví dụ luôn trả về dữ liệu xác định để tập trung vào cách tạo request. Các kiểm thử khác phải kiểm chứng service, database, validation hoặc bảo mật thật nếu đó là một phần quan trọng của hành vi API.

## 5. Nắm vững URI template, query parameter và form parameter

### URI template và path parameter

Ưu tiên truyền **template cùng giá trị thay thế** khi tài liệu hóa biến đường dẫn:

```java
get("/api/tasks/{id}", "task-100")
get("/api/teams/{teamId}/tasks/{taskId}", "team-01", "task-100")
```

Cách này giữ thông tin tên biến để Spring REST Docs tạo `path-parameters.adoc` chính xác:

```java
pathParameters(
        parameterWithName("teamId").description("Mã nhóm"),
        parameterWithName("taskId").description("Mã công việc"))
```

Nếu chỉ gửi chuỗi URL đã thay sẵn như `get("/api/tasks/task-100")`, cơ chế ghi path parameter có thể không biết biến gốc mang tên `id`. Không nên dùng giá trị tùy ý rồi mô tả một tên biến không còn trong template.

### Query parameter

Với GET/DELETE hoặc các request có query trên URL, dùng:

```java
mockMvc.perform(get("/api/tasks")
        .queryParam("state", "OPEN")
        .queryParam("page", "0")
        .queryParam("tag", "spring", "rest-docs"));
```

`queryParam(...)` phản ánh các giá trị trong **query string** và phù hợp khi muốn dùng `queryParameters(...)` của Spring REST Docs:

```java
queryParameters(
        parameterWithName("state").description("Lọc theo trạng thái"),
        parameterWithName("page").description("Chỉ số trang, bắt đầu từ 0"),
        parameterWithName("tag").description("Các nhãn, có thể lặp lại"))
```

`param(...)` cũng đặt request parameter trong MockMvc và thường dùng để mô phỏng dữ liệu form hoặc bind vào `@RequestParam`. Tuy nhiên, khi mục tiêu là **tài liệu hóa query string**, hãy dùng `queryParam(...)` để query được biểu diễn rõ trong URL của snippet. Đây là điểm cần chú ý vì query parameter và form parameter được phân loại khác nhau trong Spring REST Docs hiện đại.

### Form URL-encoded

Form HTML thông thường gửi các cặp tên/giá trị với `application/x-www-form-urlencoded`:

```java
mockMvc.perform(post("/api/subscriptions")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "reader@example.com")
        .param("topic", "java", "spring"));
```

Phần controller có thể nhận `@RequestParam("email")` và `@RequestParam("topic")`. Khi viết tài liệu cho form, sử dụng `formParameters(...)` với descriptor phù hợp thay vì khai báo trường JSON bằng `requestFields(...)`. Để xác nhận biểu diễn body chính xác như client thật, cũng có thể gửi body đã URL-encode một cách tường minh, ví dụ `email=reader%40example.com&topic=java`.

## 6. Header, content type, cookie, session và dữ liệu xác thực

### Header và content negotiation

```java
mockMvc.perform(post("/api/tasks")
        .header("X-Correlation-Id", "req-002")
        .accept(MediaType.APPLICATION_JSON)
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Đọc tài liệu\"}"));
```

- `Accept` mô tả **kiểu response client mong muốn**. Server có thể trả `406 Not Acceptable` nếu không đáp ứng được.
- `Content-Type` mô tả **định dạng body gửi lên**. Controller có `consumes` không tương thích có thể trả `415 Unsupported Media Type`.
- `header(name, values...)` thêm header thường, như `Authorization`, `If-Match` hay mã truy vết; mô tả các header có ý nghĩa bằng `requestHeaders(...)`.
- `characterEncoding("UTF-8")` xác định encoding của request khi cần kiểm soát rõ cách giải mã ký tự. Với JSON UTF-8, dùng encoding và content type nhất quán.

Một request có header `Authorization` trong MockMvc chưa đồng nghĩa đã kiểm thử bảo mật. Nếu endpoint sử dụng Spring Security, hãy tích hợp đúng filter chain hoặc cấu hình kiểm thử bảo mật cần thiết; token giả với mọi giá trị có thể chỉ là một header chưa được xác thực.

### Cookie và session

```java
import jakarta.servlet.http.Cookie;

mockMvc.perform(get("/api/profile")
        .cookie(new Cookie("theme", "dark"))
        .sessionAttr("selectedTab", "overview"));
```

`cookie(...)` gửi cookie; `sessionAttr(...)` cung cấp session attribute cho request trong test. Những giá trị này chỉ có tác dụng nếu controller, interceptor hoặc filter thực sự đọc chúng. Khi tài liệu hóa cookie, có thể sử dụng snippet descriptor tương ứng của Spring REST Docs; không nhầm cookie request với header hoặc body JSON.

### Nhiều giá trị tham số

```java
get("/api/tasks")
    .queryParam("tag", "spring", "mockmvc")
    .queryParam("state", "OPEN")
```

Một tên query parameter có thể xuất hiện nhiều lần. Controller thường nhận bằng `List<String>`, mảng hoặc kiểu tương thích tùy cấu hình binding. Bài test nên có assertion cho việc xử lý nhiều giá trị, nhất là khi endpoint áp dụng lọc và phân trang.

## 7. PUT, PATCH, multipart và request body

Ngoài GET, POST và DELETE, có thể dựng các phương thức khác bằng cùng nguyên tắc:

```java
mockMvc.perform(put("/api/tasks/{id}", "task-100")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Đổi tên\",\"state\":\"DONE\"}"));

mockMvc.perform(patch("/api/tasks/{id}", "task-100")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"state\":\"DONE\"}"));
```

Hai đoạn này là các ví dụ gửi request, chưa kèm assertions và `document(...)`. `PUT` thường được API dùng để thay thế trạng thái tài nguyên; `PATCH` dùng cho cập nhật từng phần. Ý nghĩa thực tế phụ thuộc hợp đồng API. Nếu `PATCH` nhận định dạng patch riêng như `application/merge-patch+json`, hãy đặt `Content-Type` đúng định dạng đã thiết kế.

### Multipart request

Upload tệp bằng `MockMultipartFile`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.mock.web.MockMultipartFile;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

MockMultipartFile file = new MockMultipartFile(
        "file",
        "guide.txt",
        "text/plain",
        "Nội dung mẫu".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/attachments")
        .file(file)
        .param("category", "docs"));
```

`multipart(...)` mặc định xây dựng request POST dạng `multipart/form-data`, trong đó `file` là tên part. Controller tương ứng có thể dùng `@RequestPart("file") MultipartFile file` hoặc `@RequestParam("file") MultipartFile file` tùy hợp đồng. Với Spring REST Docs, mô tả tệp bằng `requestParts(partWithName("file").description(...))`; nếu part mang JSON riêng, có thể mô tả payload part bằng các snippet hỗ trợ phần payload đó.

Không dùng `requestFields(...)` để mô tả byte của tệp như thể đó là một thuộc tính JSON thông thường. Với multipart có thêm trường text như `category`, cần phân biệt form parameter và multipart part theo cách API thực sự nhận dữ liệu.

## 8. Kiểm chứng response để tài liệu có giá trị

Các assertion phổ biến:

```java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.id").value("task-100"))
.andExpect(jsonPath("$.state").value("OPEN"))
.andExpect(header().string("X-Correlation-Id", "req-001"))
```

Đây là **các phương thức nối tiếp** trong chuỗi `perform(...)`, không phải câu lệnh Java độc lập. Khi response là JSON có thứ tự field không ổn định, hãy kiểm tra những giá trị quan trọng với `jsonPath(...)` thay vì so sánh nguyên văn toàn bộ chuỗi JSON.

Khi cần xem request/response để chẩn đoán:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc.perform(get("/api/tasks/{id}", "task-100")
        .queryParam("includeDetails", "true")
        .header("X-Correlation-Id", "req-001"))
    .andDo(print())
    .andExpect(status().isOk());
```

`print()` hữu ích khi debug, nhưng có thể đưa body và header nhạy cảm vào log test; nên sử dụng phù hợp với dữ liệu kiểm thử. Khi muốn đọc kết quả trực tiếp:

```java
MvcResult result = mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .header("X-Correlation-Id", "req-001"))
        .andExpect(status().isOk())
        .andReturn();

String responseBody = result.getResponse().getContentAsString();
int httpStatus = result.getResponse().getStatus();
```

`MvcResult` nằm trong `org.springframework.test.web.servlet.MvcResult`. Cách lấy kết quả này phù hợp cho những kiểm tra đặc biệt; với trường hợp thường gặp, matcher có sẵn rõ ràng và dễ bảo trì hơn.

## 9. Tạo snippet Spring REST Docs từ request thực tế

Phần `document(...)` gắn vào `ResultActions` như `print()`, nhưng nhiệm vụ là ghi operation dưới một identifier:

```java
mockMvc.perform(get("/api/tasks/{id}", "task-100")
                .queryParam("includeDetails", "true")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Correlation-Id", "req-001"))
        .andExpect(status().isOk())
        .andDo(document("tasks-get",
                pathParameters(
                        parameterWithName("id").description("Mã công việc")),
                queryParameters(
                        parameterWithName("includeDetails")
                                .description("Yêu cầu thêm chi tiết")),
                requestHeaders(
                        headerWithName("Accept").description("Định dạng response"),
                        headerWithName("X-Correlation-Id")
                                .description("Mã truy vết")),
                responseFields(
                        fieldWithPath("id").description("Mã"),
                        fieldWithPath("title").description("Tên"),
                        fieldWithPath("state").description("Trạng thái"),
                        fieldWithPath("details").description("Chi tiết"))));
```

Đây là phiên bản rút gọn của test GET ở phần 4; hãy dùng cấu hình MockMvc đã bật Spring REST Docs. Các descriptor đóng vai trò **hợp đồng tài liệu**: nếu tên tham số hoặc trường JSON không khớp, Spring REST Docs có thể làm test thất bại thay vì tạo tài liệu sai.

Những snippet thường gặp:

| Snippet | Nguồn dữ liệu |
| --- | --- |
| `http-request.adoc`, `http-response.adoc` | Request và response HTTP trong test. |
| `curl-request.adoc`, `httpie-request.adoc` | Cách gọi API minh họa bằng lệnh client, tùy bộ snippet mặc định. |
| `path-parameters.adoc` | `pathParameters(...)` cho URI template. |
| `query-parameters.adoc` | `queryParameters(...)` cho tham số query. |
| `form-parameters.adoc` | `formParameters(...)` cho form được gửi. |
| `request-headers.adoc`, `response-headers.adoc` | `requestHeaders(...)` và `responseHeaders(...)`. |
| `request-fields.adoc`, `response-fields.adoc` | `requestFields(...)` và `responseFields(...)` cho payload có cấu trúc. |
| `request-parts.adoc` | `requestParts(...)` cho multipart request. |

Sau `./gradlew test`, nếu output dùng mặc định Gradle, một số file sẽ nằm trong thư mục `build/generated-snippets/tasks-get/`. Với Maven, vị trí thường là `target/generated-snippets/`. Bộ file chính xác phụ thuộc cấu hình sinh snippet và phiên bản Spring REST Docs.

Ví dụ trang Asciidoctor sử dụng kết quả:

```adoc
= Tasks API

== Lấy công việc

include::{snippets}/tasks-get/http-request.adoc[]
include::{snippets}/tasks-get/path-parameters.adoc[]
include::{snippets}/tasks-get/query-parameters.adoc[]
include::{snippets}/tasks-get/request-headers.adoc[]
include::{snippets}/tasks-get/http-response.adoc[]
include::{snippets}/tasks-get/response-fields.adoc[]

== Tạo công việc

include::{snippets}/tasks-create/request-fields.adoc[]
include::{snippets}/tasks-create/http-response.adoc[]
include::{snippets}/tasks-create/response-headers.adoc[]
```

`{snippets}` phải được chỉ tới đường dẫn thư mục sinh snippet trong tác vụ biên soạn. Khi đầu ra là Markdown, có thể nhúng/chuyển snippet theo cơ chế build mà dự án sử dụng. Build/CI nên nối tác vụ **test tạo snippet → biên soạn tài liệu → xuất bản** bằng quan hệ phụ thuộc, để không công bố tài liệu từ snippet cũ.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Nhận `404 Not Found` | URI/method không khớp `@RequestMapping` hoặc controller chưa được đăng ký | Kiểm tra method, URI template và nguồn cấu hình MockMvc. |
| Nhận `400 Bad Request` | Thiếu `@RequestParam` bắt buộc, body không giải mã được hoặc dữ liệu không hợp lệ | Kiểm tra `queryParam`/`param`, kiểu dữ liệu và JSON thực gửi. |
| Nhận `415 Unsupported Media Type` | Gửi body không có `Content-Type` tương thích với `consumes` | Đặt `contentType(...)` phù hợp; kiểm tra JSON converter. |
| Nhận `406 Not Acceptable` | `Accept` không phù hợp `produces` hoặc converter | Đối chiếu `accept(...)`, cấu hình controller và converter. |
| Nhận `401`/`403` ngoài dự kiến | Bảo mật/filter hoặc CSRF trong phạm vi test chưa phù hợp | Thiết lập authentication/CSRF và security filter chain theo hợp đồng API. |
| Dữ liệu query không hiện trong snippet như mong đợi | Dùng `param(...)` nhưng muốn biểu diễn query URL | Dùng `queryParam(...)` cho dữ liệu query và `queryParameters(...)` tương ứng. |
| `pathParameters(...)` thất bại | Dùng URL đã thay giá trị nhưng không giữ tên biến | Dùng `get("/api/tasks/{id}", value)`. |
| `requestFields(...)` báo thiếu trường | JSON body khác descriptor hoặc content type sai | So sánh body thực tế, cập nhật trường tài liệu, kiểm tra optional/ignored khi đúng API. |
| Không có thư mục `generated-snippets` | Chưa cấu hình REST Docs, thiếu `document(...)` hoặc test chưa chạy thành công | Kiểm tra extension, `documentationConfiguration`, `andDo(document(...))` và test report. |
| Tài liệu có host `localhost` thay vì host công khai | Chưa cấu hình URI hiển thị của REST Docs | Dùng `documentationConfiguration(...).uris().withScheme(...).withHost(...).withPort(...)`. |

Khi có lỗi, hãy bắt đầu từ request thực sự được dựng và response thực sự được nhận. Một assertion đúng trên status, header và payload giúp phân biệt lỗi API với lỗi mô tả snippet.

## 11. Bài thực hành củng cố

1. Thêm `GET /api/tasks` với `state=OPEN&page=0`; viết test dùng `queryParam`, kiểm tra JSON list và sinh `queryParameters(...)`.
2. Thêm `PUT /api/tasks/{id}` nhận JSON có `title`, `state`; kiểm tra response và tài liệu hóa request/response fields.
3. Thêm form `POST /api/subscriptions` với `application/x-www-form-urlencoded`; kiểm tra cách request nhận `param(...)` và tạo snippet `formParameters(...)`.
4. Thêm multipart upload cho `POST /api/attachments`; kiểm tra status, tên file và tài liệu hóa part `file` bằng `requestParts(...)`.
5. Chạy bài kiểm thử, kiểm tra thư mục snippet, ghép chúng vào Asciidoctor hoặc Markdown và bảo đảm CI không biên soạn tài liệu trước khi test hoàn thành.

**Tiêu chí hoàn thành:** request được dựng đúng method, path, query, header và body; assertion kiểm chứng HTTP response; mỗi request cần công bố sinh snippet có identifier ổn định; tài liệu build được từ snippet mới nhất.

## 12. Checklist khi viết request MockMvc

- [ ] Chọn đúng request builder theo phương thức HTTP.
- [ ] Giữ URI template khi cần tài liệu path parameter; dùng `queryParam(...)` cho query trên URL.
- [ ] Đặt `Content-Type` khi gửi body; đặt `Accept` khi cần kiểm soát định dạng response.
- [ ] Kiểm tra header, cookie, session, authentication/filter nếu chúng ảnh hưởng hành vi API.
- [ ] Xác minh status, content type và payload bằng matcher phù hợp trước khi ghi tài liệu.
- [ ] Dùng `andDo(document(...))` và descriptor nhất quán với request/response thực tế.
- [ ] Kiểm tra generated snippets và đưa bước kiểm thử vào build/CI trước khi biên soạn Asciidoctor/Markdown.

**Ghi nhớ:** `MockMvcRequestBuilders` định nghĩa **request cần gửi**; `mockMvc.perform(...)` thực thi request qua Spring MVC; `andExpect(...)` xác nhận **hành vi thật trong phạm vi test**; `andDo(document(...))` chuyển kết quả HTTP thành snippet. Nhờ đó tài liệu REST API có thể được tạo, kiểm chứng và cập nhật cùng mã nguồn.
