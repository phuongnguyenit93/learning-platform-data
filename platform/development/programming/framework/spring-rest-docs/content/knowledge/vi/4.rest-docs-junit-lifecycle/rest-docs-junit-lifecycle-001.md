# RestDocumentationExtension trong JUnit 5

## 1. Mục tiêu và vị trí trong Spring REST Docs

**`RestDocumentationExtension`** là extension dành cho **JUnit Jupiter (JUnit 5)**, giúp Spring REST Docs tạo và quản lý ngữ cảnh tài liệu cho từng lần chạy kiểm thử. Khi kết hợp extension với **MockMvc**, **WebTestClient** hoặc **REST Assured**, chúng ta có thể tạo tài liệu REST API từ những yêu cầu và phản hồi HTTP thực sự được kiểm thử.

Đây là một mắt xích trong quy trình của **SPRING_REST_DOCS**: viết kiểm thử HTTP, xác minh hành vi API, sinh snippet mô tả request/response/payload/tham số/header, sau đó dùng Asciidoctor hoặc một quy trình biên soạn phù hợp để xuất bản tài liệu. Extension chỉ phụ trách **ngữ cảnh và vòng đời tài liệu**; việc gửi request, kiểm tra response và quyết định sinh snippet là trách nhiệm của các thành phần khác.

Sau bài này, bạn có thể:

- Đăng ký `RestDocumentationExtension` bằng `@ExtendWith` trong kiểm thử JUnit 5.
- Nhận `RestDocumentationContextProvider` ở `@BeforeEach` và cấu hình MockMvc để sinh tài liệu.
- Hiểu những bước xảy ra trước, trong và sau mỗi test.
- Tạo và kiểm tra các snippet REST Docs từ một ca kiểm thử HTTP.
- Nhận diện lỗi khi thiếu extension, thiếu cấu hình documentation hoặc sử dụng sai request builder.

## 2. Extension giải quyết việc gì?

Nếu chỉ chạy một kiểm thử MockMvc thông thường, bạn có thể xác nhận rằng endpoint trả về `200 OK` và nội dung JSON đúng kỳ vọng. Tuy nhiên, MockMvc **không tự động** biến những kết quả này thành tài liệu. Spring REST Docs còn cần biết ngữ cảnh của ca kiểm thử để xác định nơi lưu snippet và gắn thao tác HTTP với lần kiểm thử hiện tại.

JUnit 5 cung cấp cơ chế **extension** để thư viện tham gia vào vòng đời test. Với REST Docs, điểm nối tiêu biểu là:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class ApiDocumentationTest {
    // Các kiểm thử và cấu hình REST Docs nằm ở đây.
}
~~~

| Thành phần | Vai trò |
| --- | --- |
| `@ExtendWith(RestDocumentationExtension.class)` | Đăng ký REST Docs vào vòng đời JUnit Jupiter. |
| `RestDocumentationContextProvider` | Cung cấp ngữ cảnh tài liệu hiện hành để cấu hình bộ kiểm thử HTTP. |
| `documentationConfiguration(restDocumentation)` | Kết nối ngữ cảnh REST Docs với MockMvc; các client khác có API cấu hình tương ứng. |
| `MockMvc` / `WebTestClient` / `REST Assured` | Thực hiện yêu cầu HTTP trong kiểm thử. |
| `document("identifier", ...)` | Yêu cầu REST Docs ghi snippet của thao tác HTTP theo một định danh. |
| Asciidoctor/Markdown và build | Biên soạn các snippet đã sinh thành tài liệu để đọc hoặc xuất bản. |

**Phân biệt quan trọng:** có `@ExtendWith` không có nghĩa là mọi request đều tạo snippet. Đối với ví dụ MockMvc bên dưới, bạn vẫn cần áp dụng `documentationConfiguration(...)` và gọi `.andDo(document(...))` (hoặc cấu hình cách ghi tài liệu mặc định phù hợp).

## 3. Vòng đời JUnit 5 và ngữ cảnh REST Docs

Sơ đồ sau trình bày luồng khái niệm của một ca kiểm thử; JUnit Jupiter quản lý thứ tự callback, còn extension cung cấp ngữ cảnh cần thiết cho REST Docs.

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit Jupiter
    participant Ext as RestDocumentationExtension
    participant Setup as @BeforeEach
    participant MVC as MockMvc
    participant Docs as Spring REST Docs

    JUnit->>Ext: Bắt đầu một test
    Ext-->>JUnit: Thiết lập ngữ cảnh tài liệu
    JUnit->>Setup: Gọi setUp(RestDocumentationContextProvider)
    Setup->>MVC: apply(documentationConfiguration(provider))
    JUnit->>MVC: perform(request)
    MVC-->>JUnit: HTTP response
    JUnit->>JUnit: Kiểm tra các assertion
    JUnit->>Docs: andDo(document("books-get", ...))
    Docs-->>JUnit: Sinh snippet cho thao tác đã kiểm thử
    JUnit->>Ext: Kết thúc test
    Ext-->>JUnit: Hoàn tất vòng đời ngữ cảnh
~~~

Các mốc cần hiểu:

1. **Trước test:** JUnit nhận diện `@ExtendWith` và cho extension tham gia vòng đời của lần chạy kiểm thử.
2. **Thiết lập:** JUnit có thể truyền `RestDocumentationContextProvider` vào phương thức `@BeforeEach`. Ta dùng provider này để cấu hình MockMvc.
3. **Thực thi:** Test gửi request, kiểm tra status/header/body và gọi `document(...)` với các mô tả phù hợp.
4. **Kết thúc:** Ngữ cảnh REST Docs của lần chạy được hoàn tất. Test tiếp theo nhận vòng đời tài liệu của riêng nó.

Ngữ cảnh này gắn với **lần thực thi test**, không nên giữ trong biến `static` hoặc tự tạo một provider chung cho nhiều test. Với test chạy song song, cũng cần dùng **định danh snippet riêng** cho các kịch bản khác nhau để tránh cùng ghi vào một thư mục đầu ra.

`@BeforeEach` thường được chọn vì nó thiết lập MockMvc mới cho mỗi test. Đối với test dùng `@TestInstance(PER_CLASS)`, đối tượng test có thể được tái sử dụng, nhưng bạn vẫn nên chuẩn bị ngữ cảnh theo từng lần chạy.

## 4. Chuẩn bị dependency và test runner

Ví dụ chính sử dụng JUnit 5, Spring MVC Test và mô-đun `spring-restdocs-mockmvc`. Trong dự án Spring Boot, dependency kiểm thử thường có thể khai báo như sau:

**Maven (Spring Boot quản lý phiên bản dependency):**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Gradle Kotlin DSL (khi đã dùng Spring Boot dependency management):**

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.restdocs:spring-restdocs-mockmvc")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Nếu không dùng quản lý phiên bản từ Spring Boot/BOM, hãy khai báo phiên bản tương thích của các dependency. JUnit Jupiter phải được chạy bằng **JUnit Platform**; chỉ có dependency trên classpath nhưng chạy sai test engine thì extension không hoạt động như mong muốn.

## 5. Ví dụ hoàn chỉnh: sinh tài liệu endpoint GET

Ví dụ sau tự chứa controller để thấy rõ mối liên hệ giữa extension, request, assertion và snippet. Với Java 17+ và các dependency ở trên, có thể đặt lớp kiểm thử vào `src/test/java` của dự án Spring MVC/Spring Boot.

~~~java
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

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class BookApiDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new BookController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void shouldDocumentGetBook() throws Exception {
        mockMvc.perform(get("/books/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã định danh của sách")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã định danh của sách"),
                                fieldWithPath("title")
                                        .description("Tên sách")
                        )
                ));
    }

    @RestController
    static class BookController {
        @GetMapping("/books/{id}")
        public BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

Ví dụ dùng `standaloneSetup` nên không cần khởi động toàn bộ Spring ApplicationContext. Đây là cách phù hợp để học riêng cơ chế REST Docs; ở dự án thật, bạn có thể thay controller mẫu bằng controller của ứng dụng.

### Giải thích từng điểm nối

**`@ExtendWith(RestDocumentationExtension.class)`:** đăng ký extension với JUnit 5. JUnit sử dụng extension để chuẩn bị ngữ cảnh và giải quyết tham số `RestDocumentationContextProvider` trong `setUp`.

**`@BeforeEach void setUp(RestDocumentationContextProvider restDocumentation)`:** phương thức không tự tạo provider. JUnit và extension phối hợp để cung cấp đúng đối tượng của lần kiểm thử hiện hành.

**`.apply(documentationConfiguration(restDocumentation))`:** gắn REST Docs vào cấu hình MockMvc. Thiếu lời gọi này, `.andDo(document(...))` có thể không tìm thấy ngữ cảnh hoặc không có các cấu hình REST Docs cần thiết.

**`RestDocumentationRequestBuilders.get("/books/{id}", 42L)`:** dùng `get` được import từ **REST Docs**, thay vì `MockMvcRequestBuilders.get`, để lưu thông tin mẫu URL cần cho snippet `pathParameters`. Nếu chỉ đọc dòng `get(...)`, rất dễ bỏ sót điểm khác biệt ở lệnh `import static`.

**`.andExpect(...)`:** kiểm tra HTTP response trước khi sinh tài liệu. Tài liệu gắn với một hành vi API đã được xác minh bằng assertion.

**`.andDo(document("books-get", ...))`:** định danh `books-get` quyết định thư mục snippet. `pathParameters(...)` mô tả biến `id` trên đường dẫn; `responseFields(...)` mô tả các trường JSON. REST Docs mặc định kiểm tra chặt các trường response được tài liệu hóa, nên thay đổi cấu trúc response có thể làm test tài liệu thất bại nếu mô tả chưa cập nhật.

## 6. Kết quả sinh ra và cách sử dụng

Sau khi test chạy thành công, Spring REST Docs thường ghi các tệp Asciidoctor snippet vào vị trí đầu ra do cấu hình build quyết định. Với thiết lập thông dụng, thư mục là:

- Maven: `target/generated-snippets/books-get/`.
- Gradle: `build/generated-snippets/books-get/`.

Trong thư mục `books-get`, các snippet thường gặp gồm:

| Tên snippet | Nội dung |
| --- | --- |
| `http-request.adoc` | Request HTTP được thực thi. |
| `http-response.adoc` | Response HTTP nhận được. |
| `curl-request.adoc` | Ví dụ lệnh curl tái tạo request. |
| `path-parameters.adoc` | Bảng tham số đường dẫn từ `pathParameters(...)`. |
| `response-fields.adoc` | Bảng các trường JSON từ `responseFields(...)`. |

Đường dẫn thực tế và danh sách snippet còn tùy cách cấu hình REST Docs. Kiểm tra trong thư mục build sau khi chạy test thay vì giả định extension sẽ sinh sẵn một trang tài liệu hoàn chỉnh.

Nếu bạn dùng **Asciidoctor**, một trang API có thể ghép các tệp trên như sau:

~~~asciidoc
= Books API

== Lấy thông tin sách

=== Yêu cầu HTTP
include::{snippets}/books-get/http-request.adoc[]

=== Tham số đường dẫn
include::{snippets}/books-get/path-parameters.adoc[]

=== Phản hồi HTTP
include::{snippets}/books-get/http-response.adoc[]

=== Các trường phản hồi
include::{snippets}/books-get/response-fields.adoc[]
~~~

Thuộc tính Asciidoctor `{snippets}` cần được **cấu hình trong tác vụ biên soạn tài liệu** để chỉ đến thư mục chứa snippet, và tác vụ đó cần chạy **sau test**. Nếu viết tài liệu Markdown, bạn vẫn phải thiết lập cách chuyển đổi/chèn các snippet tương thích với đầu ra tài liệu; extension không tự thực hiện bước biên soạn này.

Chuỗi công việc thường là:

~~~text
JUnit 5 test
   -> MockMvc/WebTestClient/REST Assured
   -> REST Docs document(...)
   -> generated-snippets/
   -> Asciidoctor hoặc bước biên soạn Markdown
   -> tài liệu REST API xuất bản trong build/CI
~~~

## 7. Dùng extension với Spring ApplicationContext

`standaloneSetup` là lựa chọn tối giản. Khi cần kiểm thử cấu hình Spring MVC thực tế (message converter, validation, exception handler, security hoặc dependency injection), hãy dùng `webAppContextSetup` với `WebApplicationContext`.

Ví dụ khung thiết lập trong một dự án Spring Boot:

~~~java
@WebMvcTest(BookController.class)
@ExtendWith(RestDocumentationExtension.class)
class BookApiWebMvcDocumentationTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // Các @Test tiếp tục gọi perform(...).andDo(document(...)).
}
~~~

Đoạn trên là **khung tích hợp**: cần các `import`, controller, mock dependency và cấu hình ứng dụng tương ứng. `@WebMvcTest` đã tích hợp `SpringExtension` qua các annotation của Spring Boot; `RestDocumentationExtension` được thêm để quản lý ngữ cảnh REST Docs. Nếu dùng JUnit 5 với Spring Test thuần, cần đăng ký `SpringExtension` cùng với extension của REST Docs khi kiểm thử phụ thuộc vào Spring context.

Một số dự án Spring Boot dùng `@AutoConfigureRestDocs` để tự động tích hợp REST Docs với client kiểm thử do Boot cấu hình. Khi dùng cách này, hãy chọn **một chiến lược cấu hình rõ ràng** và kiểm tra client nào thực sự được dùng, tránh nghĩ rằng MockMvc tự tạo trong test đã được cấu hình giống MockMvc do Boot tiêm vào.

### Khi đổi công cụ kiểm thử HTTP

`RestDocumentationExtension` vẫn phụ trách lifecycle JUnit 5, nhưng API nối với công cụ kiểm thử sẽ thay đổi:

| Công cụ | Cách tích hợp tài liệu |
| --- | --- |
| MockMvc | `MockMvcRestDocumentation.documentationConfiguration(provider)` được áp dụng qua `MockMvcBuilders`. |
| WebTestClient | `WebTestClientRestDocumentation.documentationConfiguration(provider)` được gắn vào client bằng cơ chế filter. |
| REST Assured | `RestAssuredRestDocumentation.documentationConfiguration(provider)` được tích hợp vào request specification/filter. |

Vì vậy, **extension không thay thế MockMvc/WebTestClient/REST Assured**. Nó cung cấp phần ngữ cảnh chung cho cùng ý tưởng kiểm thử sinh tài liệu.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| JUnit không cung cấp được `RestDocumentationContextProvider` vào `@BeforeEach`. | Quên `@ExtendWith(RestDocumentationExtension.class)`, hoặc kiểm thử không chạy bằng JUnit Jupiter. | Kiểm tra annotation, dependency JUnit 5 và cấu hình JUnit Platform. |
| `document(...)` báo thiếu ngữ cảnh/cấu hình REST Docs. | MockMvc chưa áp dụng `documentationConfiguration(restDocumentation)`. | Đọc lại cách khởi tạo MockMvc trong `@BeforeEach`. |
| Test xanh nhưng không thấy tệp snippet mong muốn. | Không gọi `document(...)`, tìm sai thư mục output, hoặc nhầm client được cấu hình. | Kiểm tra `.andDo(...)`, identifier và đường dẫn output thực tế. |
| `pathParameters(...)` không tìm thấy tham số URL. | Sử dụng nhầm `MockMvcRequestBuilders.get` khi cần thông tin URL template. | Dùng `RestDocumentationRequestBuilders.get` và URL dạng `/books/{id}`. |
| Test tài liệu thất bại khi response thêm/bớt trường JSON. | Mô tả `responseFields(...)` chưa khớp response. | Sửa assertion và descriptors theo contract API mong muốn; không tắt kiểm tra chỉ để test xanh. |
| Hai bài test ghi đè hoặc làm lẫn snippet của nhau. | Cùng dùng `document("books-get")` cho các kịch bản không tương đương. | Đặt identifier riêng, ví dụ `books-get-success` và `books-get-not-found`. |
| Asciidoctor báo không tìm thấy snippet. | Chưa chạy test trước khi dựng tài liệu hoặc chưa cấu hình thuộc tính `snippets`. | Thiết lập quan hệ phụ thuộc tác vụ build và đường dẫn snippet. |

Lưu ý: một assertion đúng **chưa đảm bảo** đầy đủ tài liệu. Với endpoint trả nhiều nhánh trạng thái, bạn cần test và mô tả riêng những response có ý nghĩa, chẳng hạn `200`, `400` và `404`. Ngược lại, một snippet được tạo thành công cũng không thay thế kiểm tra nghiệp vụ và kiểm tra bảo mật.

## 9. Bài thực hành nhỏ: kiểm chứng tài liệu theo thay đổi API

Bắt đầu từ ví dụ `BookApiDocumentationTest`:

1. Chạy test, mở `books-get/http-response.adoc` và `books-get/response-fields.adoc`, đối chiếu với response thực tế.
2. Thêm trường `author` vào `BookResponse` và giá trị trả về trong `BookController`, nhưng **chưa** thay đổi `responseFields(...)`. Quan sát test tài liệu phát hiện response không còn khớp mô tả.
3. Bổ sung assertion cho `author`, rồi thêm `fieldWithPath("author").description("Tác giả")` vào `responseFields(...)`. Chạy lại test và xem snippet được cập nhật.
4. Tạo ca `404 Not Found` riêng với một identifier khác, ví dụ `books-get-not-found`, và chỉ tài liệu hóa response đúng với ca đó.
5. Cấu hình bước Asciidoctor dùng thư mục snippet vừa tạo, bảo đảm tài liệu được dựng **sau** khi test thành công trong CI.

**Tiêu chí hoàn thành:** test JUnit 5 chạy trên JUnit Platform; provider được cung cấp trong `@BeforeEach`; các request có assertion rõ ràng; snippet có định danh riêng và mô tả khớp HTTP response; bước dựng tài liệu tìm đúng file đã sinh.

## 10. Ghi nhớ

- `RestDocumentationExtension` là cầu nối **JUnit Jupiter ↔ ngữ cảnh Spring REST Docs**.
- `@ExtendWith` đăng ký extension; `RestDocumentationContextProvider` được lấy trong lifecycle của test, thông dụng nhất là tại `@BeforeEach`.
- `documentationConfiguration(provider)` nối ngữ cảnh với client HTTP; `document(...)` ra lệnh sinh snippet.
- Kiểm thử nên xác nhận response **trước khi** dùng response đó làm tài liệu; descriptors giúp phát hiện thay đổi contract.
- Quy trình build/CI cần chạy test, lấy snippet và biên soạn tài liệu. Việc xuất bản trang tài liệu là bước riêng với vòng đời extension.

