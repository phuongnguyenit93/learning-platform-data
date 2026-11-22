# JUnitRestDocumentation trong JUnit 4

## 1. JUnit 4 nằm ở đâu trong quy trình Spring REST Docs?

**Spring REST Docs** tạo tài liệu REST API từ các bài kiểm thử HTTP. Thay vì viết mô tả request và response hoàn toàn bằng tay, ta gửi request qua **MockMvc**, **WebTestClient** hoặc **REST Assured**, xác nhận kết quả bằng assertion và yêu cầu thư viện sinh các **snippet** cho HTTP request, HTTP response, payload, tham số, header và các thành phần khác. Snippet sau đó được biên soạn thành tài liệu Asciidoctor/Markdown trong quy trình build và CI.

Trong module **SPRING_REST_DOCS**, chương **JUnit và lifecycle** tập trung vào cách gắn Spring REST Docs vào bộ kiểm thử. Nếu dùng **JUnit Jupiter (JUnit 5)**, cơ chế quen thuộc là `RestDocumentationExtension` với `@ExtendWith` hoặc `@RegisterExtension`. Trong một dự án vẫn chạy **JUnit 4**, thành phần tương ứng là **`JUnitRestDocumentation`**, hoạt động cùng **`@Rule`** của JUnit 4.

Bài học này giúp bạn:

- Khai báo đúng `JUnitRestDocumentation` bằng `@Rule` và hiểu vì sao rule phải được JUnit 4 thực thi.
- Kết hợp rule với `MockMvcRestDocumentation.documentationConfiguration(...)` để tạo snippet từ request đã được kiểm thử.
- Chỉ định thư mục output, đặt identifier cho từng kịch bản và biên soạn tài liệu bằng Asciidoctor.
- Phân biệt `JUnitRestDocumentation` với `SpringRunner` và `RestDocumentationExtension`.
- Xử lý các lỗi thường gặp trong dự án JUnit 4, kể cả trường hợp build dùng JUnit Platform.

**Phạm vi:** bài tập trung vào API JUnit 4 để bảo trì dự án hiện có. Với dự án mới đang dùng JUnit Jupiter, cơ chế extension của REST Docs thường là lựa chọn tự nhiên hơn.

## 2. JUnitRestDocumentation là gì?

Lớp `org.springframework.restdocs.JUnitRestDocumentation` là **JUnit 4 rule** của Spring REST Docs. Nó cung cấp ngữ cảnh tài liệu quanh mỗi lần thực thi test, đồng thời có thể nhận đường dẫn thư mục snippet khi khởi tạo.

Cách khai báo thường gặp:

~~~java
import org.junit.Rule;
import org.springframework.restdocs.JUnitRestDocumentation;

public class ApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation();
}
~~~

Nếu cần chỉ định thư mục output:

~~~java
@Rule
public final JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("build/generated-snippets");
~~~

Ở đây:

- `@Rule` là annotation của **JUnit 4** để JUnit áp dụng rule vào từng test method.
- `JUnitRestDocumentation` đảm nhận phần ngữ cảnh REST Docs cho vòng đời của test.
- Constructor với `"build/generated-snippets"` chọn **thư mục gốc** để ghi snippet; tên thư mục con sẽ do `document(identifier, ...)` quyết định.
- Field `@Rule` thông thường phải là **`public` và không `static`**, để JUnit 4 nhận diện và thực thi đúng. Có thể dùng `final` như ví dụ.

Đừng nhầm với `@ClassRule`: đó là cơ chế ở **phạm vi lớp** trong JUnit 4. Cấu hình `JUnitRestDocumentation` trong bài này dùng `@Rule` ở **phạm vi test method**, phù hợp khi tạo tài liệu cho từng request được kiểm chứng.

### Rule không tự động ghi mọi HTTP response

Chỉ khai báo `@Rule` chưa có nghĩa JUnit sẽ lưu tất cả request. Với MockMvc, bạn còn phải:

1. Dùng `restDocumentation` để cấu hình MockMvc.
2. Gửi HTTP request bằng MockMvc.
3. Kiểm tra kết quả HTTP bằng các assertion.
4. Gọi `document("identifier", descriptors...)` để sinh snippet.

Nhờ vậy, tài liệu bám vào **hành vi API được kiểm thử**, thay vì tạo ra từ những lời mô tả không có kiểm chứng.

## 3. Vòng đời JUnit 4 và ngữ cảnh REST Docs

JUnit 4 dùng **rule** để bao quanh phần thực thi một test. Với `JUnitRestDocumentation`, có thể hình dung luồng như sau:

~~~mermaid
sequenceDiagram
    participant JUnit as JUnit 4
    participant Rule as JUnitRestDocumentation
    participant Setup as @Before
    participant MVC as MockMvc
    participant Docs as Spring REST Docs

    JUnit->>Rule: Áp dụng rule cho test method
    Rule-->>JUnit: Chuẩn bị ngữ cảnh tài liệu
    JUnit->>Setup: Chạy setUp()
    Setup->>MVC: apply(documentationConfiguration(rule))
    JUnit->>MVC: perform(request)
    MVC-->>JUnit: HTTP response
    JUnit->>JUnit: andExpect(...) kiểm chứng response
    JUnit->>Docs: andDo(document("identifier", ...))
    Docs-->>JUnit: Ghi snippet vào output directory
    JUnit->>JUnit: Chạy @After nếu có
    JUnit->>Rule: Hoàn tất phạm vi thực thi test
~~~

Sơ đồ mô tả trách nhiệm của các bước, không đi sâu vào mọi callback nội bộ của JUnit. Điều cần nắm là **ngữ cảnh REST Docs được chuẩn bị trước khi phương thức `@Before` cấu hình MockMvc**, và rule hoàn tất phạm vi của một test sau khi phần kiểm thử kết thúc.

| Thành phần JUnit 4 | Nhiệm vụ khi tài liệu hóa |
| --- | --- |
| `@Rule JUnitRestDocumentation` | Chuẩn bị và hoàn tất ngữ cảnh REST Docs của từng lần thực thi test. |
| `@Before` | Khởi tạo client HTTP như `MockMvc`, áp dụng cấu hình REST Docs. |
| `@Test` | Thực thi HTTP request, assertion và `document(...)`. |
| `@After` | Dọn dẹp tài nguyên test nếu cần; không phải nơi bắt buộc sinh snippet. |
| `@RunWith(SpringRunner.class)` | Tích hợp JUnit 4 với Spring TestContext khi test cần Spring ApplicationContext. |

**Hai vòng đời khác nhau:** Spring TestContext có thể cache `ApplicationContext` giữa nhiều test; `JUnitRestDocumentation` quản lý ngữ cảnh ghi tài liệu của test đang chạy. Vì vậy, không nên suy ra rằng việc cache Spring context cho phép hai test ghi chung identifier mà vẫn có nội dung độc lập.

## 4. Dependency và cách chạy JUnit 4

Ví dụ dùng Spring MVC Test, Spring REST Docs MockMvc và JUnit 4. Nếu dự án có BOM hoặc quản lý dependency của Spring Boot, phiên bản các thư viện Spring/Spring REST Docs cần được chọn tương thích với dòng Spring đang sử dụng.

### Maven (minh họa dependency trong dự án đã quản lý phiên bản)

~~~xml
<dependencies>
    <dependency>
        <groupId>junit</groupId>
        <artifactId>junit</artifactId>
        <version>4.13.2</version>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.restdocs</groupId>
        <artifactId>spring-restdocs-mockmvc</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ngoài các dependency trên, dự án phải có Spring MVC và bộ xử lý JSON tương ứng với controller được kiểm thử (ví dụ Jackson). Nếu không dùng BOM hoặc cơ chế quản lý phiên bản, hãy khai báo phiên bản phù hợp cho `spring-test` và `spring-restdocs-mockmvc`.

### Gradle Groovy DSL (minh họa)

~~~groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Các artifact không kèm phiên bản trong ví dụ trên giả định build đã có BOM/quản lý phiên bản. Nếu dự án dùng `spring-boot-starter-test`, hãy kiểm tra xem **JUnit 4** và (khi cần) **JUnit Vintage** đã thực sự được đưa vào test runtime chưa.

### Phân biệt JUnit 4 runner và JUnit Platform

- Với cách chạy JUnit 4 trực tiếp, build phải dùng cơ chế phát hiện và thực thi test của JUnit 4.
- Nếu Gradle/Maven chạy kiểm thử thông qua **JUnit Platform**, những test viết bằng `org.junit.Test` và `@Rule` chỉ được chạy khi có **JUnit Vintage TestEngine** phù hợp.
- Chỉ bật `useJUnitPlatform()` trong Gradle mà thiếu Vintage có thể khiến các test JUnit 4 **không được phát hiện**; lúc đó test không sinh snippet dù mã nguồn trông hợp lệ.
- Những test viết bằng `org.junit.jupiter.api.Test` thuộc **JUnit Jupiter**, dùng REST Docs extension (`RestDocumentationExtension`), không dùng `@Rule` của JUnit 4.

Ví dụ cấu hình Gradle khi dự án **chạy trực tiếp JUnit 4**:

~~~groovy
tasks.named('test') {
    useJUnit()
}
~~~

Nếu toàn dự án chạy trên JUnit Platform, hãy cấu hình engine Vintage và phiên bản tương thích thay vì áp dụng máy móc đoạn `useJUnit()` trên.

## 5. Ví dụ hoàn chỉnh: JUnit 4 + MockMvc + response JSON

Ví dụ sau là một ca kiểm thử dạng standalone: controller được tạo trực tiếp, không cần khởi động Spring ApplicationContext. Vì thế, **không cần `SpringRunner`** trong bài kiểm thử này.

Giả định môi trường có JUnit 4, Spring MVC Test, Spring REST Docs MockMvc và Jackson hỗ trợ ghi response JSON. Đặt lớp kiểm thử trong `src/test/java`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;
import org.springframework.http.MediaType;
import org.springframework.restdocs.JUnitRestDocumentation;
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

public class GreetingApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(this.restDocumentation))
                .build();
    }

    @Test
    public void getGreetingProducesDocumentation() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.message").value("Hello, Lan"))
                .andDo(document("greetings-get-success",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Tên người được chào")
                        ),
                        responseFields(
                                fieldWithPath("name")
                                        .description("Tên từ tham số đường dẫn"),
                                fieldWithPath("message")
                                        .description("Nội dung lời chào")
                        )
                ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            Map<String, String> response = new LinkedHashMap<>();
            response.put("name", name);
            response.put("message", "Hello, " + name);
            return response;
        }
    }
}
~~~

### Tại sao ví dụ này sinh được snippet?

**1. `@Rule` đăng ký đúng lifecycle.** JUnit 4 áp dụng `JUnitRestDocumentation` quanh lần thực thi test. Constructor chọn thư mục gốc `build/generated-snippets`.

**2. `@Before` dựng MockMvc có REST Docs.** `standaloneSetup(new GreetingController())` tạo môi trường MVC cho controller mẫu. `documentationConfiguration(this.restDocumentation)` kết nối ngữ cảnh từ rule với MockMvc.

**3. Request builder lưu thông tin path template.** Trong phần `import static`, `get(...)` được lấy từ **`RestDocumentationRequestBuilders`**, giúp `pathParameters(...)` nhận biết placeholder `{name}` trong URL.

**4. Assertion kiểm chứng contract API.** Test yêu cầu status `200 OK`, trường JSON `name = "Lan"` và `message = "Hello, Lan"`. Nếu ứng dụng thay đổi response, assertion hoặc phần mô tả trường có thể phát hiện sự không khớp.

**5. `document(...)` sinh snippet.** Identifier `greetings-get-success` là tên thư mục con. Descriptors `pathParameters(...)` và `responseFields(...)` tạo thêm snippet mô tả các phần tương ứng. Spring REST Docs có thể kiểm tra chặt mô tả field, nhờ đó tài liệu phản ánh cấu trúc payload đang được kiểm thử.

Ví dụ response kỳ vọng:

~~~json
{
  "name": "Lan",
  "message": "Hello, Lan"
}
~~~

Sau khi test chạy thành công, các file dự kiến gồm:

~~~text
build/generated-snippets/
└── greetings-get-success/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── path-parameters.adoc
    └── response-fields.adoc
~~~

Tên file còn phụ thuộc các snippet mặc định và cấu hình thực tế của phiên bản REST Docs. Thư mục gốc do rule chọn; thư mục con do `document("greetings-get-success", ...)` chọn.

## 6. Kết hợp JUnitRestDocumentation với SpringRunner

Ví dụ ở mục 5 kiểm thử controller độc lập. Nếu controller phụ thuộc vào bean do Spring quản lý hoặc bạn muốn dùng cấu hình thực tế của Spring MVC, hãy kết hợp **`SpringRunner`** với **`JUnitRestDocumentation`**.

Trong JUnit 4:

- **`@RunWith(SpringRunner.class)`** tích hợp test với **Spring TestContext Framework**, bao gồm tải context và tiêm `@Autowired`.
- **`@Rule JUnitRestDocumentation`** quản lý ngữ cảnh tài liệu cho mỗi test.
- **`MockMvcBuilders.webAppContextSetup(...)`** tạo MockMvc dựa trên web application context.

Ví dụ khung cấu hình:

~~~java
import org.junit.Before;
import org.junit.Rule;
import org.junit.runner.RunWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.restdocs.JUnitRestDocumentation;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit4.SpringRunner;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;

@RunWith(SpringRunner.class)
@WebAppConfiguration
@ContextConfiguration(classes = TestWebConfiguration.class)
public class SpringMvcApiDocumentationTest {

    @Rule
    public final JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("build/generated-snippets");

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
~~~

Đây là **khung tích hợp**: `TestWebConfiguration` cần tồn tại và khai báo đủ cấu hình MVC/controller cho test; bổ sung test method, import phù hợp và dependency riêng của ứng dụng trước khi chạy.

**Phân biệt trách nhiệm:** `SpringRunner` quản lý tích hợp Spring TestContext; `JUnitRestDocumentation` hỗ trợ tạo ngữ cảnh tài liệu. Chúng có thể tồn tại cùng nhau vì runner và rule là hai cơ chế tích hợp khác nhau của JUnit 4. Đăng ký rule không tự động khởi tạo Spring context; ngược lại, dùng SpringRunner không tự làm phát sinh tài liệu REST Docs.

### Với dự án Spring Boot

Trong các phiên bản Spring Boot hỗ trợ cấu hình REST Docs tự động, một test controller có thể dùng:

~~~java
@RunWith(SpringRunner.class)
@WebMvcTest(GreetingController.class)
@AutoConfigureRestDocs
public class GreetingBootDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    // @Test: perform(...).andExpect(...).andDo(document(...))
}
~~~

Đoạn trên là **khung ý tưởng**, giả định `GreetingController` nằm trong mã ứng dụng và các dependency cần thiết cho `@WebMvcTest` đã được cung cấp. `@AutoConfigureRestDocs` cấu hình REST Docs cho MockMvc do Spring Boot tạo. Khi dùng cách tự động cấu hình này, thường **không cần thêm `@Rule JUnitRestDocumentation`** cho chính client đó.

Đối với dự án Boot hiện đại, hãy kiểm tra chính sách hỗ trợ JUnit 4, thư viện Vintage và các annotation thuộc phiên bản đang sử dụng. Các API tích hợp cũ không nên được sao chép nguyên xi vào dự án đã chuyển hoàn toàn sang JUnit Jupiter.

## 7. Đường dẫn output, identifier và kiểm thử song song

`JUnitRestDocumentation` cho phép nhận thư mục gốc qua constructor:

~~~java
new JUnitRestDocumentation("target/generated-snippets")
~~~

Cấu hình này thường phù hợp với Maven. Với Gradle, ví dụ thường là:

~~~java
new JUnitRestDocumentation("build/generated-snippets")
~~~

Nếu không truyền đường dẫn, thư viện có quy ước mặc định cho môi trường build được hỗ trợ. Tuy nhiên, trong dự án nhiều module, nhiều tác vụ hoặc cấu hình CI riêng, **truyền đường dẫn tường minh** giúp dễ kiểm tra hơn.

Giả sử bạn gọi:

~~~java
document("greetings-get-success")
~~~

Thư mục được ghi về mặt logic sẽ là:

~~~text
<output-directory>/greetings-get-success/
~~~

**Đường dẫn tương đối** được xác định dựa trên working directory của tiến trình chạy test. Vì vậy, cùng một chuỗi `"build/generated-snippets"` có thể tạo ra vị trí khác nhau nếu IDE, Maven, Gradle và CI sử dụng working directory khác nhau.

Các nguyên tắc nên áp dụng:

| Quyết định | Lý do |
| --- | --- |
| Chọn một thư mục gốc nhất quán với build | Asciidoctor/CI có thể tìm đúng snippet sau khi test hoàn tất. |
| Dùng identifier riêng cho mỗi kịch bản | Tránh ghi đè giữa response thành công, lỗi validation và lỗi không tìm thấy. |
| Đặt tên phản ánh hành vi API | Ví dụ `greetings-get-success`, `greetings-get-not-found`, `greetings-post-invalid`. |
| Không dùng cùng identifier cho test chạy song song có output khác nhau | Hai luồng có thể ghi vào cùng file và tạo tài liệu không ổn định. |
| Để sản phẩm sinh ra dưới thư mục build | Thuận tiện cho cơ chế clean, cache và đóng gói. |

Bản thân `@Rule` **không có cơ chế tự động đảm bảo** rằng hai test dùng chung identifier sẽ an toàn khi ghi song song. Việc phân chia thư mục/identifier cần nằm trong thiết kế bộ test và tác vụ build.

## 8. Biên soạn snippet thành tài liệu Asciidoctor và Markdown

Ví dụ test ở mục 5 tạo snippet `greetings-get-success`. Một trang Asciidoctor có thể chèn các file như sau:

~~~asciidoc
= Greeting API

== Lấy lời chào theo tên

=== HTTP request
include::{snippets}/greetings-get-success/http-request.adoc[]

=== Path parameters
include::{snippets}/greetings-get-success/path-parameters.adoc[]

=== HTTP response
include::{snippets}/greetings-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/greetings-get-success/response-fields.adoc[]
~~~

Thuộc tính **`{snippets}`** phải được tác vụ biên soạn gán cho **thư mục gốc** mà JUnit rule đã dùng. Chỉ có file `.adoc` trong `build/generated-snippets` chưa tạo ra tài liệu xuất bản.

Một cấu hình Gradle Groovy DSL minh họa, giả định dự án đã áp dụng plugin Asciidoctor tương ứng và tên task là `asciidoctor`:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    // Chọn useJUnit() hoặc JUnit Platform + Vintage theo test runtime.
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir
}
~~~

Cú pháp thuộc tính có thể cần điều chỉnh theo phiên bản Asciidoctor Gradle plugin được dự án sử dụng. Dù dùng Maven, Gradle hay hệ thống build khác, vẫn cần đồng bộ ba phần:

1. Test JUnit 4 ghi vào **output directory** đã định.
2. Công cụ Asciidoctor hoặc pipeline Markdown đọc **đúng output directory** đó.
3. Bước dựng tài liệu chạy **sau** các test có nhiệm vụ tạo snippet và thất bại khi đầu vào bắt buộc không có.

Spring REST Docs mặc định thường sinh snippet Asciidoctor `.adoc`. Nếu đích xuất bản là Markdown, cần pipeline chuyển đổi hoặc cơ chế snippet tùy chỉnh tương thích. Việc chọn JUnit 4 hay 5 không tự thay đổi định dạng snippet.

Luồng tổng thể:

~~~mermaid
flowchart TD
    A["JUnit 4 Test + @Rule"] --> B["MockMvc / WebTestClient / REST Assured"]
    B --> C["Kiểm chứng HTTP response"]
    C --> D["document(identifier, descriptors)"]
    D --> E["generated-snippets/identifier/*.adoc"]
    E --> F["Asciidoctor hoặc pipeline Markdown"]
    F --> G["Artifact tài liệu trong build / CI"]
~~~

Nếu pipeline CI không tạo được tài liệu, hãy kiểm tra **test có thực sự được phát hiện và chạy không** trước khi sửa bước Asciidoctor. Đây là điểm hay bị bỏ qua khi build đã chuyển sang JUnit Platform nhưng chưa hỗ trợ JUnit 4 qua Vintage.

## 9. Các lỗi thường gặp với JUnitRestDocumentation

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| JUnit báo field `@Rule` không hợp lệ | Field thiếu `public` hoặc khai báo `static` cho `@Rule` thông thường | Dùng `@Rule public final JUnitRestDocumentation ...`. |
| Test JUnit 4 không được chạy | Build đang chạy Jupiter/JUnit Platform mà không có Vintage | Kiểm tra test engine, cấu hình Gradle/Maven và số lượng test thực thi. |
| Không thấy snippet dù assertion thành công | Chưa gọi `document(...)` hoặc client không được cấu hình REST Docs | Kiểm tra `.andDo(document(...))` và `documentationConfiguration(restDocumentation)`. |
| Gọi `document(...)` nhưng báo lỗi ngữ cảnh | Không có rule hoạt động hoặc MockMvc chưa áp dụng documentation configuration | Kiểm tra khai báo `@Rule`, lifecycle JUnit 4 và cách khởi tạo MockMvc. |
| `pathParameters(...)` không nhận ra biến đường dẫn | Dùng request builder không giữ URL template | Import `RestDocumentationRequestBuilders.get` và request `"/api/greetings/{name}"`. |
| Response fields descriptor không khớp | JSON thay đổi nhưng tài liệu chưa cập nhật | Đối chiếu JSON response với các `fieldWithPath(...)` và assertion. |
| `@Autowired WebApplicationContext` bằng `null` | Test dùng Spring context nhưng không có `SpringRunner` hoặc cấu hình context chưa phù hợp | Kiểm tra `@RunWith(SpringRunner.class)`, `@ContextConfiguration` và `@WebAppConfiguration`. |
| Có snippet nhưng Asciidoctor không tìm thấy | Sai thuộc tính `snippets`, sai identifier hoặc thứ tự build | Kiểm tra thư mục vật lý, include path và phụ thuộc giữa các tác vụ. |
| Test chạy không ổn định khi song song | Các test cùng ghi file theo một identifier | Dùng identifier riêng và xác định chiến lược cô lập output. |
| Sau khi chuyển sang JUnit 5, `@Rule` không còn tác dụng | Test đã chạy bằng Jupiter trong khi rule thuộc JUnit 4 | Chuyển sang `RestDocumentationExtension` với `@ExtendWith`/`@RegisterExtension` và cấu hình provider tương ứng. |

Có thể xử lý theo chuỗi chẩn đoán: **JUnit 4 test thực sự chạy → `@Rule` hợp lệ → MockMvc được cấu hình REST Docs → request/assertion thành công → `document(...)` được gọi → snippet được ghi đúng nơi → Asciidoctor/Markdown đọc đúng nơi**.

## 10. Từ JUnit 4 sang JUnit Jupiter: những phần cần thay đổi

Hai phiên bản JUnit dùng cơ chế lifecycle khác nhau. Khi nâng cấp, không thể chỉ đổi `import org.junit.Test` thành `org.junit.jupiter.api.Test` và giữ nguyên `@Rule`.

| JUnit 4 | JUnit Jupiter (JUnit 5) |
| --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `org.junit.Before` | `org.junit.jupiter.api.BeforeEach` |
| `org.junit.After` | `org.junit.jupiter.api.AfterEach` |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)`, trừ khi meta-annotation Spring đã đăng ký |
| `@Rule JUnitRestDocumentation` | `@ExtendWith(RestDocumentationExtension.class)` hoặc `@RegisterExtension` |
| `documentationConfiguration(restDocumentation)` nhận đối tượng rule | `documentationConfiguration(provider)` nhận `RestDocumentationContextProvider` của lần test hiện tại |
| `JUnitRestDocumentation("build/generated-snippets")` | Có thể dùng `@RegisterExtension` với `new RestDocumentationExtension("build/generated-snippets")` |

Ví dụ chuyển một phần cấu hình:

**Trước — JUnit 4:**

~~~java
@Rule
public final JUnitRestDocumentation restDocumentation =
        new JUnitRestDocumentation("build/generated-snippets");

@Before
public void setUp() {
    mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(restDocumentation))
            .build();
}
~~~

**Sau — JUnit Jupiter:**

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");

@BeforeEach
void setUp(RestDocumentationContextProvider provider) {
    mockMvc = MockMvcBuilders.standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(provider))
            .build();
}
~~~

Ví dụ Jupiter cần thay import tương ứng, trong đó `@RegisterExtension` thuộc `org.junit.jupiter.api.extension`. Khi dùng `@ExtendWith(RestDocumentationExtension.class)` thay vì `@RegisterExtension`, JUnit tạo extension theo cơ chế khai báo lớp; kiểm tra cách cấu hình output dir tương ứng.

**Lưu ý:** chuyển test engine có thể ảnh hưởng thứ tự lifecycle, kiểm tra tham số, cách tích hợp Spring context và các thư viện kiểm thử khác. Nên chuyển từng bộ test, kiểm tra số lượng test thực thi, assertion và snippet được sinh ra trong CI.

## 11. Bài thực hành: bảo trì tài liệu JUnit 4 trong CI

Bắt đầu với `GreetingApiDocumentationTest` ở mục 5:

1. Chạy test bằng JUnit 4 và xác minh `greetings-get-success/http-request.adoc`, `http-response.adoc`, `path-parameters.adoc` và `response-fields.adoc` có mặt.
2. Tạm bỏ `.andDo(document(...))`, chạy lại từ thư mục output đã được làm sạch và kiểm tra rằng không có snippet mới cho ca đó. Khôi phục lời gọi.
3. Tạm bỏ `.apply(documentationConfiguration(this.restDocumentation))` và quan sát lỗi hoặc sự vắng mặt của dữ liệu tài liệu khi chạy `document(...)`; sau đó khôi phục.
4. Đổi đường dẫn constructor sang `"build/api-snippets"`. Chạy lại test rồi cập nhật cấu hình Asciidoctor đọc đúng thư mục này.
5. Thêm kịch bản API trả lỗi `404` với assertion phù hợp, đặt identifier riêng như `greetings-get-not-found`.
6. Nếu dự án sử dụng JUnit Platform, xác nhận test JUnit 4 được chạy nhờ Vintage. So sánh với lúc thiếu Vintage để hiểu vì sao bài test có thể không được phát hiện.
7. Tạo một phiên bản JUnit Jupiter dùng `RestDocumentationExtension` và đối chiếu vị trí snippet, nội dung response fields và kết quả dựng tài liệu.

**Tiêu chí hoàn thành:** biết lý do cần `@Rule` và `JUnitRestDocumentation`, chỉ ra được chỗ tạo client HTTP, chỗ ghi snippet, nơi lưu output và đường đi từ test đến tài liệu được xuất bản.

## 12. Ghi nhớ

- **`JUnitRestDocumentation` là rule của JUnit 4** dùng để cung cấp ngữ cảnh REST Docs theo lifecycle kiểm thử; khai báo bằng `@Rule` trên instance field hợp lệ.
- **`SpringRunner` có trách nhiệm khác**: tích hợp Spring TestContext với JUnit 4. Chỉ cần SpringRunner khi test phụ thuộc hạ tầng Spring context tương ứng.
- **MockMvc vẫn phải được cấu hình** bằng `documentationConfiguration(restDocumentation)`; `document(identifier, ...)` mới chọn thao tác HTTP và descriptors để sinh snippet.
- **Output directory** từ constructor và **identifier** từ `document(...)` phải nhất quán với đường dẫn mà Asciidoctor/Markdown và CI sử dụng.
- Khi chuyển sang **JUnit Jupiter**, thay cơ chế rule bằng **`RestDocumentationExtension`**, cập nhật lifecycle callback và kiểm tra test engine thực sự chạy các bài kiểm thử.

