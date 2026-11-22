# SpringExtension và kết hợp với kiểm thử Spring

## 1. Bài toán: tài liệu REST API từ kiểm thử chạy trong Spring

Spring REST Docs giúp tạo tài liệu REST API có thể kiểm chứng: kiểm thử HTTP gửi request, khẳng định kết quả response, rồi sinh snippet về request, response, payload, path/query parameter và header. Snippet được đưa vào Asciidoctor hoặc quy trình Markdown và có thể dựng thành tài liệu trong build/CI.

Khi endpoint phụ thuộc vào controller, service, cấu hình MVC, validation, serializer hoặc cơ chế bảo mật do Spring quản lý, test chỉ khởi tạo controller bằng `new` có thể không phản ánh đúng hành vi của ứng dụng. **`SpringExtension`** giúp JUnit 5 khởi tạo và sử dụng **Spring TestContext Framework**, nhờ đó kiểm thử có thể lấy bean từ Spring context thực và dùng công cụ như `MockMvc`. **`RestDocumentationExtension`** cung cấp ngữ cảnh riêng cho Spring REST Docs.

Trong chương **JUnit và lifecycle** của module **SPRING_REST_DOCS**, mục tiêu của bài này là hiểu **cách hai extension cộng tác**, lựa chọn cách cấu hình phù hợp và tổ chức kiểm thử có khả năng tạo tài liệu tin cậy.

Sau bài học, bạn có thể:

- Phân biệt trách nhiệm của `SpringExtension` và `RestDocumentationExtension` trong JUnit Jupiter.
- Biết khi nào phải khai báo `SpringExtension` tường minh và khi nào annotation Spring Boot đã khai báo sẵn.
- Dùng `@Autowired WebApplicationContext` để xây dựng `MockMvc` có REST Docs.
- Viết một bài kiểm thử MVC sinh snippet từ endpoint thuộc Spring context.
- Tránh cấu hình trùng lặp, xung đột test client và những sai lầm khiến snippet không được tạo.

## 2. SpringExtension là gì?

`SpringExtension` thuộc **Spring TestContext Framework**, nằm trong package:

~~~java
org.springframework.test.context.junit.jupiter.SpringExtension
~~~

Nó tích hợp Spring TestContext vào **JUnit Jupiter** qua cơ chế extension. Những việc tiêu biểu mà Spring TestContext hỗ trợ gồm:

- **Tạo hoặc lấy lại `ApplicationContext` phù hợp** dựa trên cấu hình test, đồng thời có cơ chế lưu cache context để giảm thời gian khởi động.
- **Tiêm dependency vào test instance**, ví dụ `@Autowired` đối với `WebApplicationContext`, service hay bean trong context.
- **Thực thi các TestExecutionListener** của Spring cho các giai đoạn chuẩn bị test, trước/sau phương thức và dọn dẹp.
- **Hỗ trợ các tính năng của Spring Test**, ví dụ cấu hình hồ sơ test, test transaction, xử lý context bị đánh dấu bẩn và các loại test slice.
- **Kết nối với bộ phân giải tham số của JUnit Jupiter** đối với các trường hợp Spring hỗ trợ, chẳng hạn một số tham số được đánh dấu `@Autowired`.

Đăng ký thủ công như sau:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class SpringContextTest {
    // ...
}
~~~

Tuy nhiên, trong các ứng dụng Spring Boot, annotation như `@SpringBootTest` hoặc `@WebMvcTest` đã có cấu hình tích hợp `SpringExtension`. **Không cần đăng ký lại** chỉ để dùng `@Autowired` trong những test đã được cấu hình bằng các annotation đó.

### Phân biệt hai extension

| Khía cạnh | `SpringExtension` | `RestDocumentationExtension` |
| --- | --- | --- |
| Thuộc thư viện | Spring TestContext | Spring REST Docs |
| Mục đích chính | Khởi tạo, tiêm dependency và quản lý ngữ cảnh kiểm thử Spring | Quản lý ngữ cảnh tài liệu REST Docs theo vòng đời test |
| Đầu vào thường dùng | `@ContextConfiguration`, `@SpringBootTest`, `@WebMvcTest`, `@Autowired` | `@ExtendWith(RestDocumentationExtension.class)`, `RestDocumentationContextProvider` |
| Tài nguyên cung cấp | `ApplicationContext`, bean, cấu hình và hạ tầng test | `RestDocumentationContextProvider` dùng để cấu hình REST Docs |
| Có tự gửi HTTP request không? | Không | Không |
| Có tự sinh snippet khi chỉ đăng ký extension không? | Không | Không |

**Điểm mấu chốt:** `SpringExtension` không thay thế `RestDocumentationExtension`, và cả hai đều không thay thế bộ kiểm thử HTTP. Request được chạy bởi `MockMvc`, `WebTestClient` hoặc `REST Assured`; snippet được sinh khi bạn cấu hình REST Docs cho client và thực hiện thao tác `document(...)` (hoặc dùng cơ chế tài liệu tự động đã cấu hình).

## 3. Vòng đời kết hợp trong JUnit 5

Giả sử một test cần cả Spring context lẫn REST Docs. Sau khi các extension được đăng ký, luồng thực hiện về mặt khái niệm là:

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit Jupiter
    participant Spring as SpringExtension
    participant Context as Spring TestContext
    participant Docs as RestDocumentationExtension
    participant Setup as @BeforeEach
    participant MVC as MockMvc

    JUnit->>Spring: Chuẩn bị test instance
    Spring->>Context: Nạp hoặc lấy Spring context từ cache
    Context-->>Spring: Bean và WebApplicationContext
    Spring-->>JUnit: Tiêm các dependency vào test
    JUnit->>Docs: Bắt đầu ngữ cảnh REST Docs của test
    JUnit->>Setup: Gọi setUp(RestDocumentationContextProvider)
    Setup->>MVC: webAppContextSetup(context)
    Setup->>MVC: apply(documentationConfiguration(provider))
    JUnit->>MVC: perform(request) + assertions
    JUnit->>MVC: document("identifier", ...)
    MVC-->>JUnit: Các snippet REST Docs
    JUnit->>Spring: Callback sau test
    JUnit->>Docs: Hoàn tất vòng đời tài liệu
~~~

Đây là **sơ đồ trách nhiệm**, không phải cam kết về thứ tự tuyệt đối giữa mọi callback của hai extension. JUnit Jupiter có quy tắc đăng ký và thực thi callback riêng; các extension được thiết kế để cung cấp dịch vụ ở đúng giai đoạn cần thiết. Điều thực sự quan trọng với người viết test là: **trước `@BeforeEach`**, Spring đã chuẩn bị dependency cần thiết và REST Docs có thể cung cấp provider dùng cho test hiện tại.

Ba khái niệm cần tách bạch:

1. **Spring `ApplicationContext`:** có thể được **cache và tái sử dụng** giữa các test có cấu hình tương thích. Đây là cơ chế của Spring TestContext, không có nghĩa trạng thái mutable của bean luôn được tự động làm sạch.
2. **Test instance/JUnit lifecycle:** theo mặc định, JUnit Jupiter thường tạo instance mới cho mỗi test method (trừ khi có cấu hình khác). `@BeforeEach` chạy trước từng lần thực thi test.
3. **REST Docs context và identifier:** `RestDocumentationContextProvider` liên quan đến ngữ cảnh tài liệu của lần thực thi test; tên trong `document("...")` quyết định khu vực chứa snippet. Nên chọn identifier riêng cho từng kịch bản khác nhau.

Khi cần kiểm thử song song, đừng cho các kịch bản độc lập cùng ghi vào một identifier. Khi test làm thay đổi state của context, database hoặc singleton, phải có chiến lược cô lập dữ liệu tương ứng; bản thân hai extension không tự bảo đảm tính độc lập nghiệp vụ.

## 4. Cấu hình một bài test Spring MVC thuần dùng cả hai extension

Để nhìn rõ vai trò của từng thành phần, ví dụ dưới đây **không dùng tự động cấu hình của Spring Boot**. Spring TestContext tải một `WebApplicationContext` chứa controller, `MockMvc` sử dụng context đó và REST Docs sinh snippet khi request đã được kiểm chứng.

Với dự án sử dụng **JUnit Jupiter**, **Spring MVC/Spring Test** và `spring-restdocs-mockmvc` phiên bản tương thích, đặt lớp sau trong `src/test/java`:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})
@WebAppConfiguration
@ContextConfiguration(classes = GreetingDocumentationTest.WebConfig.class)
class GreetingDocumentationTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.TEXT_PLAIN))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Lan"))
                .andDo(document("greetings-get",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Tên người được chào")
                        )
                ));
    }

    @Configuration
    @EnableWebMvc
    static class WebConfig {
        @Bean
        GreetingController greetingController() {
            return new GreetingController();
        }
    }

    @RestController
    static class GreetingController {
        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.TEXT_PLAIN_VALUE)
        public String greeting(@PathVariable String name) {
            return "Hello, " + name;
        }
    }
}
~~~

### Tại sao ví dụ hoạt động?

1. `@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})` đăng ký cả hạ tầng Spring Test và REST Docs với JUnit Jupiter.
2. `@ContextConfiguration` khai báo cấu hình bean test; `@WebAppConfiguration` yêu cầu Spring tạo ngữ cảnh web thích hợp cho Spring MVC Test.
3. `@EnableWebMvc` tạo hạ tầng MVC, trong khi `@Bean` đăng ký controller của ví dụ. `SpringExtension` cho phép Spring tiêm `WebApplicationContext` vào field `@Autowired`.
4. `RestDocumentationExtension` cho phép JUnit cung cấp tham số `RestDocumentationContextProvider` cho `@BeforeEach`.
5. `MockMvcBuilders.webAppContextSetup(webApplicationContext)` tạo `MockMvc` sử dụng mapping và cấu hình MVC từ Spring context. `.apply(documentationConfiguration(restDocumentation))` gắn REST Docs vào client.
6. `get("/api/greetings/{name}", "Lan")` được import từ **`RestDocumentationRequestBuilders`**: nó giữ thông tin template của URL để `pathParameters(...)` mô tả đúng biến `name`.
7. `.andExpect(...)` kiểm chứng status/body. `.andDo(document("greetings-get", ...))` yêu cầu sinh snippet về thao tác HTTP và path parameter.

Trong bài này, response là chuỗi văn bản đơn giản để tập trung vào lifecycle. Nếu endpoint trả JSON, bạn có thể thêm `responseFields(...)`, `fieldWithPath(...)` và các assertion JSON tương ứng. Với request có body, query parameter, header hoặc cookie, dùng các snippet descriptor thích hợp cùng cơ chế `document(...)`.

### Điều gì xảy ra nếu bỏ từng mảnh cấu hình?

- Thiếu `SpringExtension` trong bài test Spring thuần: Spring TestContext có thể không được khởi tạo; field `@Autowired` không được tiêm như mong đợi.
- Thiếu `RestDocumentationExtension` trong cấu hình thủ công trên: JUnit không có resolver thích hợp cho tham số `RestDocumentationContextProvider` của test.
- Thiếu `@WebAppConfiguration` hoặc `@ContextConfiguration`: ngữ cảnh test có thể không phù hợp với `webAppContextSetup(...)` hoặc không chứa controller.
- Thiếu `documentationConfiguration(restDocumentation)`: MockMvc không được cấu hình với ngữ cảnh REST Docs.
- Thiếu `document(...)`: request vẫn có thể thành công nhưng test không yêu cầu tạo snippet tài liệu.

## 5. Kết hợp với Spring Boot: @WebMvcTest và @AutoConfigureRestDocs

Trong ứng dụng Spring Boot, thường có một cách ngắn gọn hơn để tạo tài liệu REST API ở lớp web. `@WebMvcTest` khởi tạo **lát cắt Spring MVC** cho controller và các thành phần web liên quan. `@AutoConfigureRestDocs` kết nối REST Docs với cơ chế kiểm thử được Boot hỗ trợ.

Ví dụ khung (controller `GreetingController` được đặt trong mã ứng dụng và có endpoint `GET /api/greetings/{name}`):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@AutoConfigureRestDocs
class GreetingBootDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void documentsGreeting() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan"))
                .andExpect(status().isOk())
                .andDo(document("greetings-get-boot",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Tên người được chào")
                        )
                ));
    }
}
~~~

Đoạn này minh họa **phong cách tích hợp Spring Boot**, giả định controller đã tồn tại và dự án dùng phiên bản Boot có các annotation tương ứng.

Những khác biệt với ví dụ thủ công:

| Tiêu chí | Spring MVC thuần (mục 4) | Spring Boot tự động cấu hình (mục 5) |
| --- | --- | --- |
| Chuẩn bị Spring context | `@ExtendWith(SpringExtension.class)` + `@ContextConfiguration` + `@WebAppConfiguration` | `@WebMvcTest` đã tích hợp Spring TestContext |
| Chuẩn bị MockMvc | Gọi `MockMvcBuilders.webAppContextSetup(...)` | Boot cung cấp `MockMvc` qua `@Autowired` |
| Cấu hình REST Docs | `RestDocumentationExtension` + `documentationConfiguration(provider)` | `@AutoConfigureRestDocs` |
| Phạm vi kiểm thử | Context do test tự khai báo | Lát cắt web do Boot lựa chọn |
| Cần cấu hình thêm dependency bên ngoài web? | Tự khai báo bean cần thiết | Cung cấp các dependency của controller nếu không có trong slice |

**Lưu ý về phụ thuộc của controller:** `@WebMvcTest` thường không nạp toàn bộ service, repository và cấu hình của ứng dụng. Nếu controller phụ thuộc vào một service, cần cung cấp bean thích hợp trong test (chẳng hạn mock bean bằng cơ chế có sẵn của phiên bản Spring đang dùng). Các dự án Spring Framework mới có `@MockitoBean`; một số phiên bản Spring Boot cũ hơn dùng `@MockBean`. Đừng giả định hai annotation có mặt ở mọi phiên bản.

### Khi nào dùng @SpringBootTest?

Nếu tài liệu cần kiểm tra luồng tích hợp đầy đủ hơn, có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class FullApplicationDocumentationTest {
    @Autowired
    MockMvc mockMvc;

    // Các @Test thực thi request và gọi document(...).
}
~~~

`@SpringBootTest` cung cấp ngữ cảnh ứng dụng rộng hơn; `@AutoConfigureMockMvc` tạo MockMvc cho ứng dụng test; `@AutoConfigureRestDocs` cấu hình REST Docs. Đổi lại, việc khởi động và phụ thuộc test thường nhiều hơn `@WebMvcTest`.

Dù chọn hình thức nào, hãy **dùng đúng client được cấu hình REST Docs**. Nếu đã `@Autowired MockMvc` do Boot cung cấp mà sau đó tự tạo một MockMvc khác không áp dụng REST Docs, lời gọi `document(...)` trên client mới có thể không hoạt động như mong đợi.

## 6. Cách chọn cơ chế đăng ký và cấu hình extension

Có ba trường hợp thực hành phổ biến:

| Bối cảnh | Hướng cấu hình khuyến nghị |
| --- | --- |
| JUnit 5 + Spring Test thuần + MockMvc xây dựng thủ công | `@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})`, `@ContextConfiguration`, `@WebAppConfiguration` và `documentationConfiguration(provider)` |
| Spring Boot với kiểm thử controller | `@WebMvcTest` + `@AutoConfigureRestDocs` + `@Autowired MockMvc` |
| Spring Boot với kiểm thử nhiều lớp ứng dụng | `@SpringBootTest` + `@AutoConfigureMockMvc` + `@AutoConfigureRestDocs` |

Một số điều nên kiểm tra trong code review:

- **`@ExtendWith(SpringExtension.class)` có thể đã có qua meta-annotation** như `@WebMvcTest` hoặc `@SpringBootTest`. Việc sao chép thêm annotation này thường không giải quyết lỗi cấu hình; hãy kiểm tra thực sự test được khởi tạo như thế nào.
- **Chọn một con đường cấu hình REST Docs rõ ràng** cho mỗi MockMvc. Kết hợp tùy tiện cả cấu hình thủ công và tự động trong cùng test làm khó truy vết nguồn thiết lập.
- **Không tái sử dụng `RestDocumentationContextProvider` ở biến `static`** hoặc giữ provider của test trước để cấu hình test sau.
- **Dùng identifier riêng** cho response có contract khác nhau, ví dụ `greetings-get-success` và `greetings-get-not-found`, đặc biệt khi test chạy song song.
- **Chỉ mô tả thứ đã được kiểm chứng.** Assertion cho status/body và mô tả snippet nên phản ánh cùng một contract.

## 7. Từ kiểm thử Spring tới snippet và trang tài liệu

Khi ca kiểm thử ở mục 4 chạy thành công, `document("greetings-get", ...)` yêu cầu REST Docs sinh các snippet mặc định cho request/response và snippet bổ sung cho path parameter.

Đầu ra thường xuất hiện ở:

- Gradle: `build/generated-snippets/greetings-get/`.
- Maven: `target/generated-snippets/greetings-get/`.

Tên thư mục có thể đổi theo cấu hình. Ví dụ các tệp cần kiểm tra:

| Snippet | Mô tả |
| --- | --- |
| `http-request.adoc` | Request HTTP gửi tới controller |
| `http-response.adoc` | Response HTTP sau khi controller xử lý |
| `curl-request.adoc` | Lệnh curl tương đương để tham khảo |
| `path-parameters.adoc` | Bảng mô tả tham số `name` |

Một trang Asciidoctor có thể tham chiếu đầu ra như sau:

~~~asciidoc
= Greeting API

== Chào theo tên

=== Request
include::{snippets}/greetings-get/http-request.adoc[]

=== Path parameters
include::{snippets}/greetings-get/path-parameters.adoc[]

=== Response
include::{snippets}/greetings-get/http-response.adoc[]
~~~

`{snippets}` là thuộc tính Asciidoctor được cấu hình để trỏ tới thư mục snippet. Bản thân `SpringExtension` hay `RestDocumentationExtension` **không biên soạn tài liệu cuối cùng**. Quy trình build/CI thường thực hiện:

~~~text
JUnit 5 + Spring TestContext
        |
        v
MockMvc / WebTestClient / REST Assured
        |
        v
Assertion HTTP + Spring REST Docs
        |
        v
generated-snippets/{identifier}/
        |
        v
Asciidoctor hoặc pipeline Markdown
        |
        v
Tài liệu REST API được đóng gói/xuất bản
~~~

Với Gradle/Maven, bước biên soạn phải nhận đúng thư mục snippet và phụ thuộc hợp lý vào tác vụ chạy test. Nếu đang biên soạn Markdown, cần có quy tắc xử lý định dạng snippet tương thích; các snippet mặc định thường ở dạng Asciidoctor.

## 8. Lỗi thường gặp khi tích hợp SpringExtension với REST Docs

| Triệu chứng | Nguyên nhân có thể xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| `@Autowired WebApplicationContext` bằng `null` trong test Spring thuần | Thiếu `SpringExtension`, thiếu `@WebAppConfiguration` hoặc thiết lập Spring TestContext sai | Kiểm tra annotation và lớp cấu hình MVC |
| Không tải được `ApplicationContext` | Bean thiếu dependency, cấu hình lỗi hoặc test slice không có bean cần thiết | Xem lỗi gốc khi khởi tạo context; cung cấp bean/mock phù hợp |
| JUnit báo không phân giải được `RestDocumentationContextProvider` | Thiếu `RestDocumentationExtension` ở cấu hình thủ công | Đăng ký REST Docs extension trong test JUnit Jupiter |
| REST Docs không tạo snippet | Client chưa được cấu hình REST Docs, thiếu `document(...)` hoặc nhầm MockMvc instance | Xác minh client thực thi request là client đã cấu hình |
| Test `@WebMvcTest` không tìm thấy service | Slice không nạp service/repository ứng dụng | Mock hoặc thêm đúng dependency cần thiết cho web test |
| Test tài liệu hóa path parameter thất bại | Dùng request builder không giữ URL template | Dùng `RestDocumentationRequestBuilders.get` và template `/api/greetings/{name}` |
| Test chạy được nhưng tài liệu build thiếu snippet | Tác vụ biên soạn chạy trước test hoặc trỏ sai thư mục | Kiểm tra task dependency, `{snippets}` và output directory |
| Hai test tạo snippet không ổn định | Dùng cùng một identifier cho các kịch bản hoặc ghi song song | Chọn identifier riêng, xác định chiến lược chạy song song |
| Kết quả test phụ thuộc thứ tự | Bean mutable, dữ liệu dùng chung hoặc context bị tái sử dụng với state còn sót | Cô lập dữ liệu; reset state đúng phạm vi; dùng `@DirtiesContext` có chọn lọc khi cần |

**Chẩn đoán theo tầng** sẽ hiệu quả hơn: xác minh JUnit/Jupiter đã chạy đúng → Spring context đã nạp và inject được → MockMvc gửi request đúng → assertion xanh → REST Docs ghi snippet → tác vụ biên soạn tìm thấy snippet. Cách này giúp tránh nhầm lỗi ứng dụng Spring với lỗi của REST Docs.

## 9. Thực hành: thử thay đổi cấu hình từng tầng

Dùng `GreetingDocumentationTest` ở mục 4 làm điểm xuất phát:

1. **Chạy test đúng:** xác minh response `200 OK`, body `Hello, Lan` và file `greetings-get/path-parameters.adoc` xuất hiện.
2. **Quan sát SpringExtension:** tạm thời bỏ `SpringExtension.class` khỏi `@ExtendWith` và chạy lại. Ghi nhận sự khác biệt ở việc chuẩn bị/inject Spring context; sau đó khôi phục annotation.
3. **Quan sát REST Docs extension:** tạm thời bỏ `RestDocumentationExtension.class` khỏi `@ExtendWith`, giữ `@BeforeEach` nhận `RestDocumentationContextProvider`. Quan sát lỗi phân giải tham số; khôi phục annotation.
4. **Quan sát cấu hình client:** giữ cả hai extension nhưng tạm thời bỏ `.apply(documentationConfiguration(restDocumentation))`. Theo dõi hành vi khi `document(...)` chạy trên MockMvc chưa được cấu hình; sau đó khôi phục.
5. **Thêm kiểm thử lỗi:** sửa controller để có kịch bản trả `404` và tài liệu hóa bằng identifier riêng. Cần bổ sung assertion cho body/status đúng với response thật.
6. **Thử Spring Boot:** trong một dự án Boot phù hợp, thay setup thủ công bằng `@WebMvcTest` + `@AutoConfigureRestDocs`, so sánh lượng cấu hình và các bean được nạp.
7. **Dựng tài liệu:** dùng Asciidoctor include `http-request.adoc`, `path-parameters.adoc` và `http-response.adoc` rồi gắn bước đó sau test trong build.

Tiêu chí tự đánh giá: bạn có thể chỉ rõ **extension nào cung cấp Spring context**, **extension nào cung cấp REST Docs provider**, **client nào thực hiện HTTP request**, **điểm gọi nào sinh snippet** và **tác vụ nào biên soạn tài liệu**.

## 10. Tổng kết

- `SpringExtension` kết nối JUnit Jupiter với Spring TestContext Framework: context, dependency injection và các tiện ích kiểm thử Spring.
- `RestDocumentationExtension` quản lý ngữ cảnh tài liệu REST Docs cho vòng đời của test JUnit 5; nó không quản lý bean Spring.
- Trong Spring MVC test thuần, có thể đăng ký **cả hai extension**, dùng `WebApplicationContext` dựng MockMvc rồi áp dụng `documentationConfiguration(provider)`.
- Trong Spring Boot, `@WebMvcTest`/`@SpringBootTest` đã tích hợp Spring TestContext; `@AutoConfigureRestDocs` cung cấp cách cấu hình REST Docs ngắn gọn cho client tương ứng.
- Chất lượng tài liệu REST API phụ thuộc vào cùng một chuỗi kiểm chứng: **test Spring đúng → request/response được assert → snippet được sinh → Asciidoctor/Markdown được dựng trong build và CI**.

