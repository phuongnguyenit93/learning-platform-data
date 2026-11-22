# Cấu hình MockMvc với `documentationConfiguration`

## 1. Mục tiêu và bối cảnh

**Spring REST Docs** sinh tài liệu REST API từ các bài kiểm thử HTTP. Công cụ này hỗ trợ các hướng kiểm thử với MockMvc, WebTestClient hoặc REST Assured; bài này tập trung vào **MockMvc**, nơi request được thực thi qua hạ tầng Spring MVC mô phỏng mà không cần mở cổng HTTP thật. Khi bài kiểm thử chạy thành công, Spring REST Docs ghi lại request, response và các mô tả đã khai báo thành **snippet** cho payload, tham số, header và nhiều phần khác; những snippet này có thể được đưa vào tài liệu Asciidoctor hoặc Markdown trong quá trình build và CI.

Trong bài này, điểm nối giữa MockMvc và Spring REST Docs là:

```java
MockMvcBuilders.standaloneSetup(controller)
    .apply(documentationConfiguration(restDocumentation))
    .build();
```

`documentationConfiguration(...)` thiết lập phần hỗ trợ tài liệu cho MockMvc. Sau đó, `document(...)` được gắn vào một lần thực thi HTTP để quyết định **request nào** được ghi thành snippet và **những phần nào** cần mô tả.

Sau khi học, bạn có thể:

- Khởi tạo `RestDocumentationContextProvider` cho từng bài kiểm thử bằng JUnit Jupiter.
- Áp dụng `documentationConfiguration(...)` khi dựng MockMvc bằng `standaloneSetup` hoặc `webAppContextSetup`.
- Kiểm chứng status, payload rồi sinh snippet từ request thực tế bằng `.andDo(document(...))`.
- Nhận biết vị trí snippet, thay đổi URI hiển thị và tránh các lỗi cấu hình thường gặp.

## 2. `documentationConfiguration` nằm ở đâu trong luồng kiểm thử?

Một bài kiểm thử tài liệu có bốn thành phần liên quan nhưng mang trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `RestDocumentationExtension` | Tích hợp với vòng đời JUnit Jupiter và cung cấp ngữ cảnh sinh tài liệu cho bài kiểm thử. |
| `RestDocumentationContextProvider` | Cung cấp ngữ cảnh mà cấu hình Spring REST Docs cần, bao gồm thông tin về lần kiểm thử và vị trí output. |
| `documentationConfiguration(restDocumentation)` | Áp dụng cấu hình Spring REST Docs cho `MockMvcBuilder` **trước** khi gọi `.build()`. |
| `document("identifier", ...)` | Ghi một thao tác HTTP cụ thể thành nhóm snippet có tên `identifier`, kèm các mô tả tùy chọn. |

Luồng xử lý có thể hình dung như sau:

```text
JUnit Jupiter + RestDocumentationExtension
             |
             v
RestDocumentationContextProvider
             |
             v
MockMvcBuilder.apply(documentationConfiguration(...))
             |
             v
        MockMvc.perform(...)
             |
             +--> andExpect(...): kiểm chứng HTTP response
             |
             +--> andDo(document("greetings-get", ...))
                           |
                           v
                 build/generated-snippets/greetings-get/
```

**Điểm cần phân biệt:** `.apply(documentationConfiguration(...))` chỉ chuẩn bị cơ chế ghi tài liệu trên MockMvc. Nó không tự tạo snippet cho mọi request. Để tạo snippet cho một request, thường dùng `.andDo(document(...))` sau `.perform(...)`.

## 3. Chuẩn bị dependency và môi trường

Ví dụ trong bài dùng **Java 17+**, **Spring MVC**, **JUnit Jupiter (JUnit 5)** và Gradle. Nếu dự án dùng Spring Boot, thường có sẵn các thư viện thử nghiệm từ `spring-boot-starter-test`; cần thêm module tích hợp MockMvc của Spring REST Docs:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong dự án Spring Boot có quản lý dependency, nên để Spring Boot BOM quản lý phiên bản Spring REST Docs tương thích. Nếu không dùng dependency management, cần khai báo phiên bản phù hợp cho các dependency này và bảo đảm có Spring MVC, JUnit Jupiter, Jackson (khi trả JSON).

Các import cốt lõi là:

```java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
```

Hai static import cuối trỏ tới hai phương thức khác nhau: một để **cấu hình MockMvc**, một để **ghi snippet** cho request.

## 4. Ví dụ đầy đủ với `standaloneSetup`

`standaloneSetup(...)` phù hợp khi cần kiểm thử và tài liệu hóa một controller độc lập mà không nạp toàn bộ `WebApplicationContext`. Giả sử endpoint `GET /api/greetings/{name}` trả về:

```json
{
  "message": "Xin chào, An"
}
```

Lớp kiểm thử sau tự chứa controller minh họa, cấu hình MockMvc và cách sinh tài liệu:

```java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class GreetingDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "An")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, An"))
                .andDo(document("greetings-get",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Tên người nhận lời chào")),
                        responseFields(
                                fieldWithPath("message")
                                        .description("Nội dung lời chào"))));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            return Map.of("message", "Xin chào, " + name);
        }
    }
}
```

Các điểm quan trọng trong ví dụ:

1. `@ExtendWith(RestDocumentationExtension.class)` đăng ký extension cho JUnit Jupiter. Tham số `RestDocumentationContextProvider` được extension cung cấp vào `@BeforeEach`; không cần khởi tạo bằng `new`.
2. `.apply(documentationConfiguration(restDocumentation))` xuất hiện **trước** `.build()`. MockMvc được tạo ra sau đó mới có cấu hình Spring REST Docs.
3. `get("/api/greetings/{name}", "An")` giữ nguyên **URI template**. Điều này giúp snippet `pathParameters(...)` biết `name` là tên tham số đường dẫn.
4. `andExpect(...)` kiểm chứng hành vi của endpoint; `andDo(document(...))` dùng kết quả HTTP để sinh tài liệu. Khi response sai, bài kiểm thử thất bại thay vì âm thầm chấp nhận hợp đồng API sai.
5. `"greetings-get"` là mã định danh của lần ghi tài liệu, đồng thời là tên thư mục chứa snippet. Nên chọn định danh ổn định và duy nhất cho từng thao tác HTTP được tài liệu hóa.

> Trong ứng dụng thực, controller thường nằm trong `src/main/java` và lớp test nằm trong `src/test/java`. Đặt controller lồng trong test ở đây chỉ để ví dụ có thể đọc độc lập.

## 5. Cấu hình bằng `webAppContextSetup` khi cần ngữ cảnh Spring MVC

Nếu endpoint phụ thuộc vào cấu hình MVC thật, chẳng hạn message converter, validation, exception handler, filter hoặc `@ControllerAdvice`, có thể dựng MockMvc từ `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@SpringBootTest
@ExtendWith(RestDocumentationExtension.class)
class GreetingWebContextDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // Viết các @Test sử dụng mockMvc.perform(...).andDo(document(...)).
}
```

Ở đây, `@SpringBootTest` tạo Spring application context và đã hỗ trợ tích hợp Spring Test với JUnit Jupiter. `RestDocumentationExtension` đảm nhiệm phần ngữ cảnh Spring REST Docs. Cả hai cách dựng MockMvc đều dùng cùng một lệnh `documentationConfiguration(restDocumentation)`.

| Tiêu chí | `standaloneSetup` | `webAppContextSetup` |
| --- | --- | --- |
| Khởi tạo | Truyền trực tiếp controller và các thành phần cần thiết | Dùng `WebApplicationContext` được Spring Test tạo |
| Phạm vi | Kiểm thử controller theo cấu hình tối thiểu | Bao gồm cấu hình MVC của context đã tải |
| Tốc độ và độ phức tạp | Thường nhanh, dễ cô lập | Có chi phí khởi tạo context và nhiều cấu hình liên quan |
| Khi nên dùng | Tài liệu endpoint độc lập, dễ kiểm soát | Tài liệu phải phản ánh mapping, converter và xử lý lỗi của ứng dụng thực |

Với Spring Security, lưu ý rằng `standaloneSetup` không tự áp dụng cấu hình filter bảo mật giống ứng dụng; còn khi dùng `webAppContextSetup`, cần cấu hình các filter/security integration thích hợp để kết quả tài liệu phản ánh hành vi cần kiểm thử.

## 6. Tùy chỉnh URI được thể hiện trong snippet

Request của MockMvc không đi qua một web server thật, vì thế URL được hiển thị trong snippet có thể cần đổi cho sát địa chỉ API công khai. Có thể tùy chỉnh tại thời điểm cấu hình:

```java
mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
        .apply(documentationConfiguration(restDocumentation)
                .uris()
                    .withScheme("https")
                    .withHost("api.example.com")
                    .withPort(443))
        .build();
```

Cấu hình trên chỉ xác định URI được Spring REST Docs sử dụng khi dựng snippet cho thao tác HTTP; MockMvc vẫn thực thi request trong bộ máy kiểm thử, không gửi request ra `api.example.com`.

Khi cần chỉnh cách biểu diễn payload của một thao tác cụ thể, có thể gắn **operation preprocessor** tại `document(...)`, ví dụ:

```java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;

// Phần sau đặt sau mockMvc.perform(...).andExpect(...)
.andDo(document("greetings-get",
        preprocessRequest(prettyPrint()),
        preprocessResponse(prettyPrint()),
        pathParameters(parameterWithName("name").description("Tên người nhận")),
        responseFields(fieldWithPath("message").description("Lời chào"))));
```

Đoạn cuối minh họa phần nối tiếp của chuỗi gọi MockMvc, không phải câu lệnh Java độc lập. `prettyPrint()` giúp JSON trong snippet dễ đọc hơn mà không thay đổi response thực tế được kiểm tra bằng `andExpect(...)`.

## 7. Kết quả sinh snippet và tích hợp vào tài liệu

Chạy bài kiểm thử thông qua Gradle:

```bash
./gradlew test
```

Trên Windows có thể dùng `gradlew.bat test`. Với cấu hình mặc định tương ứng khi sử dụng Gradle, snippet thường nằm ở `build/generated-snippets`; với Maven, vị trí thường là `target/generated-snippets`. Một lần chạy ví dụ sẽ sinh ra cấu trúc tương tự:

```text
build/
└── generated-snippets/
    └── greetings-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── request-body.adoc
        ├── response-body.adoc
        ├── path-parameters.adoc
        └── response-fields.adoc
```

Đây là danh sách minh họa các snippet thường gặp; bộ snippet thực tế phụ thuộc vào cấu hình mặc định, phiên bản Spring REST Docs và các `Snippet` được truyền cho `document(...)`. Một số cấu hình cũng tạo `httpie-request.adoc`.

Ví dụ tài liệu Asciidoctor có thể tham chiếu kết quả:

```adoc
== Lấy lời chào

include::{snippets}/greetings-get/http-request.adoc[]
include::{snippets}/greetings-get/path-parameters.adoc[]
include::{snippets}/greetings-get/http-response.adoc[]
include::{snippets}/greetings-get/response-fields.adoc[]
```

Thuộc tính `{snippets}` cần được cấu hình trỏ tới thư mục snippet trong bước biên soạn Asciidoctor. Đối với Markdown, có thể nhúng hoặc chuyển nội dung snippet theo cấu hình build được chọn. Để tài liệu không dùng snippet cũ, tác vụ biên soạn tài liệu trong build/CI nên phụ thuộc vào tác vụ chạy test tạo snippet.

## 8. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy thư mục snippet | Thiếu `.andDo(document(...))`, test không chạy, hoặc test không đi đến bước ghi tài liệu | Kiểm tra test được phát hiện và chạy; xác minh đường dẫn output và `document(...)` của request tương ứng. |
| Lỗi vì không có ngữ cảnh REST Docs | Chưa đăng ký `RestDocumentationExtension` hoặc chưa áp dụng `documentationConfiguration(...)` | Đăng ký extension, nhận `RestDocumentationContextProvider` và gọi `.apply(...)` trước `.build()`. |
| Tài liệu path parameter lỗi hoặc thiếu tên | Request không giữ URI template hoặc descriptor không khớp | Dùng `get("/api/greetings/{name}", value)` và `parameterWithName("name")`. |
| `responseFields(...)` làm bài test thất bại | Descriptor thiếu field xuất hiện trong JSON, khai báo sai path hoặc kiểu dữ liệu trả về khác dự kiến | Đối chiếu response thực tế; mô tả đầy đủ các field, dùng `.optional()` hoặc `.ignored()` khi đúng hợp đồng API. |
| URL trong snippet là `http://localhost:8080` | Đang dùng giá trị URI mặc định | Thiết lập `.uris().withScheme(...).withHost(...).withPort(...)`. |
| Controller chạy được trong ứng dụng nhưng test standalone thất bại | `standaloneSetup` thiếu converter, validator, advice hoặc dependency của controller | Đăng ký thành phần cần thiết cho standalone hoặc đổi sang `webAppContextSetup`. |
| Tài liệu hiển thị kết quả cũ | Build tài liệu không phụ thuộc bước kiểm thử tạo snippet | Chạy lại test trước khi biên soạn; nối dependency tác vụ trong Gradle/Maven/CI. |

Khi một `Snippet` mô tả request hay response không khớp dữ liệu thực tế, Spring REST Docs có thể **làm bài test thất bại**. Đây là đặc điểm chủ chốt của tài liệu có thể kiểm chứng: sửa API thì phải cập nhật bài kiểm thử và mô tả cho nhất quán.

## 9. Checklist thực hành

1. Thêm `spring-restdocs-mockmvc` cho phạm vi test và bảo đảm JUnit Jupiter hoạt động.
2. Khai báo `@ExtendWith(RestDocumentationExtension.class)` và nhận `RestDocumentationContextProvider` trong `@BeforeEach`.
3. Chọn `standaloneSetup` hoặc `webAppContextSetup` dựa trên phạm vi cần kiểm thử.
4. Gắn `.apply(documentationConfiguration(restDocumentation))` vào builder **trước** khi tạo MockMvc.
5. Thực thi request bằng `mockMvc.perform(...)`, kiểm chứng response bằng `andExpect(...)`, rồi gọi `andDo(document(...))` với các snippet descriptor phù hợp.
6. Chạy test, kiểm tra thư mục `generated-snippets`, sau đó đưa snippet vào tài liệu và quy trình build/CI.

**Ghi nhớ:** `documentationConfiguration` kết nối **cơ chế tài liệu** với MockMvc; `document` kết nối **một thao tác HTTP đã kiểm thử** với các snippet. Hai phần này cùng nhau tạo ra tài liệu REST API phản ánh hành vi thực tế của Spring MVC.
