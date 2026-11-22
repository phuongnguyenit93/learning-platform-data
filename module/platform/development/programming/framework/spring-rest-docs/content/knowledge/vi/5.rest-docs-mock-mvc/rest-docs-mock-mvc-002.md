# Khởi tạo MockMvc từ `WebApplicationContext`

## 1. Vì sao dùng `WebApplicationContext`?

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP. Thay vì tự viết ví dụ request, response dễ bị lỗi thời, ta chạy endpoint, kiểm tra kết quả rồi để công cụ sinh **snippet** mô tả HTTP, payload, path/query parameter, header và các thành phần cần công bố. Snippet được đưa vào Asciidoctor/Markdown và có thể cập nhật tự động trong build, CI.

Spring REST Docs có thể tích hợp với MockMvc, WebTestClient hoặc REST Assured. Trong chương **MockMvc**, bài này tập trung vào cách dựng một đối tượng `MockMvc` **từ `WebApplicationContext` của Spring** để kiểm thử và tài liệu hóa endpoint Spring MVC.

`WebApplicationContext` là ngữ cảnh ứng dụng web mà Spring Test tải lên, chứa các bean và cấu hình MVC liên quan, chẳng hạn:

- `RequestMappingHandlerMapping` và các ánh xạ URL đến controller.
- `HandlerAdapter`, `HttpMessageConverter` để gọi handler, chuyển đổi JSON.
- `@ControllerAdvice`, trình xử lý ngoại lệ, validator và các thành phần MVC đã đăng ký.
- Các service, repository hoặc bean khác mà ứng dụng tạo trong phạm vi ngữ cảnh đang kiểm thử.

Khi gọi:

```java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .build();
```

MockMvc sử dụng cấu hình MVC từ `context` để xử lý request **ngay trong JVM**, không mở cổng hay thực hiện kết nối HTTP ra máy chủ thật. Với Spring REST Docs, ta thêm `documentationConfiguration(...)` trước `build()` để sinh snippet từ các request được chọn.

Kết quả mong đợi sau bài học: bạn có thể tạo và cấu hình MockMvc từ một `WebApplicationContext` hợp lệ, viết test HTTP sinh tài liệu, phân biệt cách dựng này với `standaloneSetup(...)` và xử lý các lỗi khởi tạo thường gặp.

## 2. Luồng khởi tạo và các thành phần cần có

```text
JUnit Jupiter
  |
  +-- Spring Test / Spring Boot Test
  |      |
  |      +-- Tạo WebApplicationContext
  |             |-- Controller / Service
  |             |-- MVC mapping / converter / advice
  |
  +-- RestDocumentationExtension
         |
         +-- RestDocumentationContextProvider
                   |
                   v
MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(documentationConfiguration(restDocumentation))
    .build()
                   |
                   v
mockMvc.perform(request)
    .andExpect(...)       <- kiểm tra hợp đồng HTTP
    .andDo(document(...)) <- sinh snippet
```

| Thành phần | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `WebApplicationContext` | Cung cấp cấu hình Spring MVC của bài kiểm thử | Phải được tải từ môi trường web servlet; không thể thay tùy ý bằng `ApplicationContext` thuần. |
| `MockMvcBuilders.webAppContextSetup(context)` | Tạo builder dựa trên MVC infrastructure trong context | Dùng được trong Spring MVC test, không cần web server thật. |
| `RestDocumentationExtension` | Tích hợp Spring REST Docs vào vòng đời JUnit Jupiter | Cung cấp `RestDocumentationContextProvider` cho phương thức setup. |
| `documentationConfiguration(restDocumentation)` | Bổ sung cấu hình sinh tài liệu cho builder | Phải `apply` trước khi gọi `build()`. |
| `MockMvc.perform(...)` | Thực thi request qua MVC infrastructure | Có thể kiểm tra status, body, header như các test MockMvc thông thường. |
| `document("identifier", ...)` | Ghi HTTP operation thành snippet | Gắn vào request cụ thể qua `andDo(...)`. |

**Điểm phân biệt:** `webAppContextSetup` trả lời câu hỏi “MockMvc sử dụng cấu hình MVC nào?”, còn `documentationConfiguration` trả lời “MockMvc tích hợp cơ chế ghi tài liệu ra sao?”. Chỉ cấu hình builder không làm phát sinh snippet nếu không có `document(...)` hoặc cơ chế ghi tài liệu mặc định được cấu hình rõ ràng.

## 3. Chuẩn bị dự án

Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.x, Spring MVC, JUnit Jupiter 5** và Gradle. Spring Boot quản lý các phiên bản dependency tương thích; với dự án không dùng Boot BOM cần chỉ định các phiên bản phù hợp.

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

`spring-boot-starter-web` cung cấp Spring MVC và JSON message converter; `spring-boot-starter-test` cung cấp Spring Test, MockMvc, JUnit Jupiter và các thư viện kiểm thử phổ biến; `spring-restdocs-mockmvc` cung cấp cầu nối Spring REST Docs với MockMvc.

Trong một ứng dụng Spring Boot thông thường, có thể dùng:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    @Autowired
    WebApplicationContext context;

    // Khởi tạo MockMvc bằng webAppContextSetup(context) trong @BeforeEach.
}
```

`@SpringBootTest` mặc định sử dụng `WebEnvironment.MOCK`, tải `ApplicationContext` có khả năng web servlet khi dự án có Spring MVC và servlet API. Nó đã tích hợp Spring Test với JUnit Jupiter; chỉ cần bổ sung `RestDocumentationExtension` để nhận ngữ cảnh Spring REST Docs.

## 4. Ví dụ đầy đủ: tài liệu hóa endpoint sách

Giả sử endpoint `GET /api/books/{id}` trả về:

```json
{
  "id": "b-100",
  "title": "Spring REST Docs"
}
```

Để ví dụ tự chứa và có thể đưa vào `src/test/java`, lớp test bên dưới khai báo một cấu hình Spring Boot tối thiểu và một controller mẫu ngay trong test. Với ứng dụng thật, thay `TestApplication` bằng class cấu hình chính của dự án và sử dụng controller nằm trong mã ứng dụng.

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        classes = BookApiDocumentationTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "b-100")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value("b-100"))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã định danh của sách")),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã định danh của sách"),
                                fieldWithPath("title")
                                        .description("Tên sách"))));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BookController.class)
    static class TestApplication {
    }

    @RestController
    static class BookController {

        @GetMapping(
                value = "/api/books/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> getBook(@PathVariable("id") String id) {
            return Map.of("id", id, "title", "Spring REST Docs");
        }
    }
}
```

### Phân tích từng bước

1. **Tải web context:** `@SpringBootTest` tải cấu hình `TestApplication`, kích hoạt auto-configuration cần thiết và đăng ký `BookController` qua `@Import`. Nhờ có Spring MVC trên classpath, Spring Test cấp `WebApplicationContext` cho trường `context`.
2. **Chuẩn bị Spring REST Docs:** `RestDocumentationExtension` cung cấp `RestDocumentationContextProvider` cho `@BeforeEach`. Không tạo thủ công đối tượng này.
3. **Dựng MockMvc:** `webAppContextSetup(context)` lấy các MVC bean đã cấu hình. `.apply(documentationConfiguration(restDocumentation))` gắn cơ chế tài liệu vào builder rồi `.build()` tạo MockMvc.
4. **Thực thi request có URI template:** `get("/api/books/{id}", "b-100")` giữ lại tên biến đường dẫn `id` để `pathParameters(...)` có thể mô tả chính xác tham số.
5. **Kiểm chứng rồi ghi tài liệu:** `andExpect(...)` kiểm tra kết quả thực tế. `andDo(document("books-get", ...))` sinh snippet cho request, response, tham số đường dẫn và trường JSON đã mô tả.

Ở lần chạy test thành công, Spring REST Docs tạo thư mục định danh `books-get` trong thư mục output snippet của build. Ví dụ mặc định thường là `build/generated-snippets/books-get/` với Gradle hoặc `target/generated-snippets/books-get/` với Maven.

## 5. Có thể dùng `@WebMvcTest` thay `@SpringBootTest` không?

Có, nếu mục tiêu là kiểm thử một lát cắt Spring MVC. `@WebMvcTest` cũng cung cấp ngữ cảnh web phù hợp với `webAppContextSetup(...)`, nhưng tải phạm vi bean nhỏ hơn. Nó thường phù hợp khi chỉ cần controller, MVC validation, message conversion và các thành phần MVC liên quan.

```java
@WebMvcTest(BookController.class)
@ExtendWith(RestDocumentationExtension.class)
class BookControllerDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
```

Đoạn trên giả sử `BookController` là controller đã định nghĩa trong mã dự án; import các annotation, class và static method tương ứng với ví dụ chính. Nếu controller phụ thuộc vào service không thuộc MVC slice, cần cung cấp bean giả lập hoặc cấu hình test thích hợp. Bài kiểm thử sẽ không tự có toàn bộ các bean ứng dụng như với `@SpringBootTest`.

| Tiêu chí | `@WebMvcTest` | `@SpringBootTest` + `WebEnvironment.MOCK` |
| --- | --- | --- |
| Ngữ cảnh | Tập trung vào MVC slice | Tải nhiều cấu hình và bean hơn, theo ứng dụng |
| Mục tiêu phù hợp | Kiểm thử tài liệu của controller độc lập | Tài liệu hóa hành vi endpoint có nhiều cấu hình tích hợp |
| Dependency bên ngoài MVC | Thường phải mock hoặc import bổ sung | Có thể có các bean thật, tùy cấu hình test |
| Chi phí chạy | Thường thấp hơn | Thường khởi tạo chậm hơn |
| Cách tạo MockMvc từ context | `webAppContextSetup(context)` | `webAppContextSetup(context)` |

Hai cách đều **khác `standaloneSetup(controller)`**: ở standalone, bạn truyền trực tiếp controller và tự khai báo các thành phần MVC cần thiết; ở web context, builder khai thác hạ tầng MVC từ context đã tải. Điều này giúp tài liệu phản ánh chính xác hơn cấu hình MVC của phạm vi test.

## 6. Phân biệt cấu hình thủ công với MockMvc tự động của Spring Boot

Spring Boot cũng hỗ trợ inject trực tiếp `MockMvc` được cấu hình tự động:

```java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class AutoConfiguredDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    // @Test: mockMvc.perform(...).andDo(document(...))
}
```

Ví dụ trên thuộc **cách Spring Boot tự cấu hình**: `@AutoConfigureMockMvc` tạo và cung cấp `MockMvc`; `@AutoConfigureRestDocs` tích hợp Spring REST Docs cho MockMvc đó. Để biên dịch cần import `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` và `org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs` trong Spring Boot 3.x.

Khi học `webAppContextSetup(...)`, nên dùng cách dựng thủ công như phần 4 để thấy rõ quá trình khởi tạo và vị trí áp dụng `documentationConfiguration(...)`. Nếu dự án đã dùng `@AutoConfigureMockMvc` để inject MockMvc, không cần khởi tạo thêm một đối tượng mới chỉ để tài liệu hóa cùng endpoint: hãy chọn nhất quán một cơ chế và cấu hình Spring REST Docs tương ứng.

## 7. Filter, Spring Security và những khác biệt dễ bỏ sót

`webAppContextSetup(context)` lấy **cấu hình Spring MVC** từ context, nhưng **không có nghĩa mọi servlet filter của ứng dụng đều mặc nhiên được thêm** vào MockMvc dựng thủ công. Nếu tài liệu cần phản ánh xác thực, phân quyền, session hoặc filter tùy chỉnh, cần thêm filter/configurer thích hợp khi dựng builder.

Ví dụ với `spring-security-test` và Spring Security trong ngữ cảnh ứng dụng:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .apply(documentationConfiguration(restDocumentation))
        .build();
```

Để dùng đoạn này, test classpath cần `org.springframework.security:spring-security-test` và application context phải có cấu hình Spring Security phù hợp. Sau đó có thể sử dụng các tiện ích kiểm thử như `@WithMockUser` để mô phỏng người dùng hoặc `csrf()` cho các thao tác cần CSRF token. Đừng kết luận API công khai cho phép truy cập vô danh chỉ vì test dùng MockMvc thủ công chưa gắn security filter.

Khi cần kiểm tra tính đúng đắn của request và response cho tài liệu:

- Kiểm tra `status()` và `contentType` thay vì chỉ nhìn snippet sinh ra.
- Với POST/PUT/PATCH, gửi `contentType(MediaType.APPLICATION_JSON)` và body tương ứng qua `content(...)`; mô tả `requestFields(...)` nếu cần.
- Nếu endpoint cần header, dùng `header(...)` hoặc `accept(...)` để gửi header thật rồi mô tả bằng `requestHeaders(...)`.
- Khi test dựa vào cookie, session, authentication hoặc filter, bảo đảm builder có thành phần cần thiết và assertions phản ánh đúng hành vi của ứng dụng.

## 8. Tùy chỉnh URI và sinh tài liệu từ snippet

MockMvc chạy trong JVM nên host, scheme và port xuất hiện ở snippet có thể khác URL công khai. Có thể cấu hình giá trị hiển thị ngay khi dựng MockMvc:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

Thay đổi này phục vụ **URL thể hiện trong tài liệu**, không khiến MockMvc gửi HTTP đến host bên ngoài.

Sau khi test `document("books-get", ...)` thành công, một số snippet điển hình có thể xuất hiện:

```text
build/generated-snippets/
└── books-get/
    ├── curl-request.adoc
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
```

Danh sách chính xác phụ thuộc phiên bản Spring REST Docs, default snippets và các descriptor đã khai báo; ví dụ cũng có thể bao gồm `httpie-request.adoc`. Các snippet không được mô tả hoặc không nằm trong bộ mặc định sẽ không tự nhiên xuất hiện.

Tài liệu Asciidoctor có thể nhúng trực tiếp kết quả:

```adoc
= Books API

== Lấy thông tin sách

include::{snippets}/books-get/http-request.adoc[]
include::{snippets}/books-get/path-parameters.adoc[]
include::{snippets}/books-get/http-response.adoc[]
include::{snippets}/books-get/response-fields.adoc[]
```

`{snippets}` phải được build cấu hình trỏ tới thư mục sinh snippet. Nếu biên soạn Markdown, cần chuyển đổi hoặc nhúng nội dung snippet theo cơ chế của dự án. Chuỗi thực thi trong build/CI nên là **chạy test → tạo snippet → biên soạn tài liệu → xuất bản**, với tác vụ biên soạn phụ thuộc vào tác vụ test để tránh dùng snippet cũ.

## 9. Các lỗi khởi tạo thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| `@Autowired WebApplicationContext` không inject được | Test không tải servlet web context, thiếu Spring MVC hoặc cấu hình Spring Test sai | Kiểm tra `@SpringBootTest`/`@WebMvcTest`, dependency MVC và loại web application đang dùng. |
| Ném lỗi khi `webAppContextSetup(context)` | `context` null hoặc không phải `WebApplicationContext` hợp lệ | Đừng tự `new` context; để Spring Test khởi tạo rồi inject. |
| Response `404` dù endpoint có trong code | Controller không được quét hoặc `@Import` vào context test, URL sai | Kiểm tra bean controller, `@RequestMapping`, cấu hình scan/import và đường dẫn request. |
| Response `401`/`403` khác ứng dụng thật | Security filter thiếu hoặc được áp dụng khác dự kiến; thiếu token hoặc mock user | Kiểm tra `springSecurity()`, dependency test, cấu hình filter và dữ liệu xác thực. |
| Response `406`/`415` | Sai `Accept`, `Content-Type` hoặc message converter | Gửi đúng header, kiểm tra converter trong context và `produces`/`consumes` của endpoint. |
| Không sinh snippet | Không gọi `andDo(document(...))`, test không chạy hoặc lỗi trước bước ghi | Kiểm tra bài test đã pass và thư mục output chính xác. |
| Lỗi path parameter khi tạo tài liệu | URI template bị mất hoặc mô tả tên không khớp | Dùng `get("/api/books/{id}", value)` và `parameterWithName("id")`. |
| `responseFields` làm test thất bại | Trường JSON thực tế chưa được mô tả hoặc path sai | Đối chiếu response, mô tả đầy đủ field; `optional()` hay `ignored()` chỉ khi phù hợp hợp đồng API. |
| Tài liệu có URL `localhost` | URI snippet chưa được cấu hình | Dùng `documentationConfiguration(...).uris()` để đặt host/scheme/port cần công bố. |

Không nên vô hiệu hóa kiểm chứng field chỉ để bài test chạy qua. Một lợi ích lớn nhất của Spring REST Docs là các thay đổi hợp đồng HTTP có thể khiến test tài liệu thất bại và buộc tài liệu được cập nhật.

## 10. Bài thực hành áp dụng

Từ ví dụ `BookApiDocumentationTest`:

1. Thêm endpoint `GET /api/books` nhận query parameter `title` và trả danh sách sách. Gửi request với `param("title", "...")`, kiểm tra kết quả rồi sinh `queryParameters(...)`.
2. Thêm endpoint `POST /api/books` nhận JSON chứa `title`. Kiểm chứng status, `Content-Type` và response, sau đó mô tả bằng `requestFields(...)` và `responseFields(...)`.
3. Dùng `@ControllerAdvice` để trả một JSON error thống nhất khi không tìm thấy sách. Tài liệu hóa cả trường hợp thành công lẫn lỗi, kiểm tra rằng `webAppContextSetup` dùng đúng advice trong context.
4. Nếu ứng dụng có Spring Security, thêm `springSecurity()` và tài liệu hóa response cho request có/không có quyền. Xác minh các filter mà test thực sự đã áp dụng.
5. Chạy test và đưa snippet mới vào tài liệu Asciidoctor hoặc Markdown; cấu hình CI kiểm tra và dựng tài liệu sau test.

**Tiêu chí hoàn thành:** Bài test chạy qua cấu hình MVC của `WebApplicationContext`, các assertion kiểm chứng response, snippet phản ánh request/response thực tế và tác vụ tài liệu sử dụng kết quả mới nhất từ test.

## 11. Checklist trước khi dùng trong dự án

- [ ] Có dependency Spring MVC, Spring Test/JUnit Jupiter và `spring-restdocs-mockmvc` tương thích.
- [ ] `WebApplicationContext` được Spring Test tải, inject thành công và chứa controller dự định tài liệu hóa.
- [ ] `RestDocumentationExtension` được đăng ký, `RestDocumentationContextProvider` được cung cấp cho `@BeforeEach`.
- [ ] Dùng `MockMvcBuilders.webAppContextSetup(context).apply(documentationConfiguration(restDocumentation)).build()`.
- [ ] Filter/security cần thiết được tích hợp theo đúng phạm vi kiểm thử.
- [ ] Các request dùng URI template, header, body đúng; response có assertions rõ ràng.
- [ ] `document(...)` tạo đủ snippet cần thiết; đường dẫn snippet được build/CI và Asciidoctor/Markdown sử dụng.

**Ghi nhớ:** `webAppContextSetup(context)` cho MockMvc sử dụng **MVC infrastructure của Spring context đã tải**; `documentationConfiguration(...)` gắn Spring REST Docs vào builder; `document(...)` biến kết quả của **một request được kiểm thử** thành snippet. Kết hợp ba bước này sẽ giúp tài liệu REST API bám sát hành vi thực tế của ứng dụng trong phạm vi test.
