# ManualRestDocumentation khi không dùng JUnit

## 1. Bối cảnh: sinh tài liệu REST API mà không phụ thuộc vào JUnit

Spring REST Docs tạo tài liệu từ **các thao tác HTTP được kiểm chứng bằng bài kiểm thử**. Một kiểm thử thường gửi request bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**, xác nhận response, rồi tạo các snippet mô tả request, response, payload, tham số và header. Các snippet được đưa vào Asciidoctor hoặc pipeline Markdown để dựng tài liệu trong build và CI.

Trong module **SPRING_REST_DOCS**, chương **JUnit và lifecycle** giới thiệu cơ chế gắn quá trình tạo tài liệu với vòng đời kiểm thử. Với JUnit Jupiter, ta có `RestDocumentationExtension`; với JUnit 4, ta có `JUnitRestDocumentation`. Nhưng không phải dự án nào cũng dùng JUnit. Một số dự án sử dụng **TestNG**, bộ chạy kiểm thử nội bộ hoặc gọi thao tác HTTP từ một chương trình kiểm chứng riêng.

Trường hợp này cần **`ManualRestDocumentation`**: thành phần cho phép mã kiểm thử **tự thông báo thời điểm bắt đầu và kết thúc mỗi test** để Spring REST Docs có đủ ngữ cảnh sinh snippet.

Sau bài học, bạn có thể:

- Hiểu chính xác vai trò của `ManualRestDocumentation` và sự khác biệt với extension/rule của JUnit.
- Chủ động gọi `beforeTest(Class<?>, String)` và `afterTest()` ở đúng lifecycle.
- Tích hợp `ManualRestDocumentation` với MockMvc trong một kiểm thử **TestNG** hoàn chỉnh.
- Áp dụng ý tưởng tương tự cho WebTestClient, REST Assured và bộ kiểm thử tự xây.
- Chọn thư mục đầu ra, tạo snippet, biên soạn Asciidoctor/Markdown và xử lý lỗi trong build/CI.

## 2. ManualRestDocumentation là gì?

Lớp `org.springframework.restdocs.ManualRestDocumentation` quản lý **`RestDocumentationContext`** theo cách thủ công. Lớp này triển khai interface `RestDocumentationContextProvider`, nhờ đó có thể truyền trực tiếp vào API cấu hình REST Docs cho các client HTTP.

Các API quan trọng:

~~~java
import org.springframework.restdocs.ManualRestDocumentation;

ManualRestDocumentation docs = new ManualRestDocumentation();
ManualRestDocumentation customDocs =
        new ManualRestDocumentation("build/generated-snippets");

docs.beforeTest(MyApiTest.class, "shouldDocumentGetBook");

// Chạy HTTP request, assertion và document(...).

docs.afterTest();
~~~

| Thành phần | Chức năng |
| --- | --- |
| `new ManualRestDocumentation()` | Tạo đối tượng quản lý ngữ cảnh, dùng thư mục snippet mặc định phù hợp với môi trường build được hỗ trợ. |
| `new ManualRestDocumentation("...")` | Chỉ định thư mục gốc của snippet. |
| `beforeTest(Class<?> testClass, String testMethodName)` | Đánh dấu bắt đầu **một lần thực thi test**, tạo ngữ cảnh tài liệu tương ứng. |
| `afterTest()` | Đánh dấu kết thúc test và giải phóng ngữ cảnh đã tạo. |
| `RestDocumentationContextProvider` | Giao diện mà MockMvc, WebTestClient hoặc REST Assured có thể nhận khi cấu hình REST Docs. |
| `document("identifier", ...)` | Yêu cầu tạo snippet từ thao tác HTTP đang được kiểm chứng. |

**Ràng buộc lifecycle:** mỗi lần gọi `beforeTest(...)` thành công cần được ghép với **một lần `afterTest()` khi test kết thúc**, ngay cả khi assertion thất bại. Không gọi `beforeTest(...)` lần nữa trên cùng một ngữ cảnh chưa được kết thúc: API có thể ném `IllegalStateException` nếu ngữ cảnh đã tồn tại.

`ManualRestDocumentation` không tự chạy request và không tự viết tài liệu hoàn chỉnh. Nó chỉ cung cấp ngữ cảnh. Client HTTP và thao tác `document(...)` vẫn là những phần riêng phải được cấu hình.

## 3. So sánh với JUnit 4 và JUnit Jupiter

| Khía cạnh | JUnit 4 | JUnit Jupiter | Không dùng JUnit |
| --- | --- | --- | --- |
| Thành phần REST Docs | `JUnitRestDocumentation` | `RestDocumentationExtension` | `ManualRestDocumentation` |
| Cách kích hoạt | `@Rule` | `@ExtendWith` hoặc `@RegisterExtension` | Tự tạo instance |
| Ai mở và đóng ngữ cảnh test? | JUnit rule | JUnit extension | Mã test gọi `beforeTest` và `afterTest` |
| Điểm thiết lập thường dùng | `@Before` | `@BeforeEach` | `@BeforeMethod` của TestNG hoặc hook tương đương |
| Phụ thuộc vào runner của JUnit? | Có | Có | Không |
| Có phải cấu hình MockMvc/WebTestClient/REST Assured? | Có | Có | Có |

Với TestNG, **không sử dụng `@Rule` hay `@ExtendWith`**: hai annotation đó thuộc hệ sinh thái JUnit. Sử dụng `@BeforeMethod` và `@AfterMethod` để điều khiển lifecycle của `ManualRestDocumentation`.

Nếu dự án đã dùng JUnit Jupiter hoặc JUnit 4 và có API REST Docs tương ứng, nên chọn cách tích hợp tự động sẵn có của bộ kiểm thử. `ManualRestDocumentation` đặc biệt phù hợp khi framework hiện tại không cung cấp cơ chế JUnit rule/extension.

## 4. Vòng đời đúng: beforeTest → HTTP → afterTest

Ví dụ luồng thực thi với TestNG và MockMvc:

~~~mermaid
sequenceDiagram
    participant NG as TestNG
    participant Setup as @BeforeMethod
    participant Manual as ManualRestDocumentation
    participant MVC as MockMvc
    participant Docs as REST Docs
    participant Cleanup as @AfterMethod

    NG->>Setup: setUp(Method)
    Setup->>MVC: Tạo và cấu hình MockMvc
    Setup->>Manual: beforeTest(testClass, methodName)
    NG->>MVC: perform(request)
    MVC-->>NG: HTTP response
    NG->>NG: Assertion status, header, body
    NG->>Docs: document("identifier", descriptors)
    Docs-->>NG: Tạo snippet trong outputDir
    NG->>Cleanup: tearDown() kể cả khi test thất bại
    Cleanup->>Manual: afterTest()
~~~

Một số điểm cần chú ý:

1. **Trước request đầu tiên cần tài liệu hóa**, phải gọi `beforeTest(...)` để thiết lập ngữ cảnh.
2. `testClass` và `testMethodName` giúp REST Docs biết test nào đang được chạy. Trong TestNG, bạn có thể nhận đối tượng `java.lang.reflect.Method` ở `@BeforeMethod` và lấy `method.getName()`.
3. Khi cấu hình MockMvc, truyền chính đối tượng `ManualRestDocumentation` vào `documentationConfiguration(...)`.
4. Test vẫn phải kiểm tra HTTP response rồi gọi `document(...)` để sinh snippet.
5. **Sau mỗi test**, kể cả khi assertion ném exception, gọi `afterTest()` để giải phóng ngữ cảnh trước khi chạy test kế tiếp.

**Giới hạn của hook cleanup:** `@AfterMethod(alwaysRun = true)` là một cách tốt để giảm nguy cơ bỏ sót cleanup khi test thất bại. Nếu quá trình setup lỗi trước khi `beforeTest(...)` được gọi, logic cleanup cần biết liệu ngữ cảnh đã được mở hay chưa; phần xử lý chuyên biệt này được trình bày ở mục 7.

## 5. Chuẩn bị dependency và test runner

Ví dụ chính dùng **TestNG + Spring MVC Test + Spring REST Docs MockMvc**. Dự án cần các thư viện tương thích, bao gồm Spring MVC, `spring-test`, `spring-restdocs-mockmvc`, TestNG và bộ chuyển JSON như Jackson (nếu ví dụ trả JSON).

Với Gradle Groovy DSL và quản lý phiên bản Spring/Spring REST Docs thông qua BOM hoặc cấu hình dependency hiện có:

~~~groovy
dependencies {
    testImplementation 'org.testng:testng:7.10.2'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}

tasks.named('test') {
    useTestNG()
}
~~~

`spring-test` và `spring-restdocs-mockmvc` ở ví dụ trên cần có phiên bản được quản lý bởi build. Cần bổ sung `spring-webmvc` và Jackson trong các cấu hình dự án không có sẵn chúng.

Nếu dùng Maven, hãy bảo đảm plugin chạy test phiên bản phù hợp có thể **phát hiện và thực thi TestNG**, đồng thời dependency `org.testng:testng` có mặt trong phạm vi kiểm thử. Đừng nhầm `useJUnitPlatform()` trong Gradle với lệnh chạy TestNG: chỉ cấu hình JUnit Platform không đồng nghĩa các phương thức `org.testng.annotations.Test` sẽ được chạy.

Một bài TestNG thông thường import:

~~~java
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.Test;
~~~

Các annotation này khác với `org.junit.Test` và `org.junit.jupiter.api.Test`. Khi test không được chạy, sẽ không có snippet mới dù code cấu hình REST Docs hoàn toàn hợp lệ.

## 6. Ví dụ hoàn chỉnh: TestNG + MockMvc + ManualRestDocumentation

Ví dụ sau có một controller mẫu, response JSON, kiểm chứng status/payload và tạo snippet cho đường dẫn, header request và các trường response. Vì dùng `MockMvcBuilders.standaloneSetup(...)`, test **không cần** Spring ApplicationContext.

Giả định dự án đã có Spring MVC Test, REST Docs MockMvc, Jackson và TestNG. Đặt class vào `src/test/java` và chạy bằng TestNG:

~~~java
import java.lang.reflect.Method;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.restdocs.ManualRestDocumentation;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.request.RequestDocumentation.headerWithName;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.pathParameters;
import static org.springframework.restdocs.request.RequestDocumentation.requestHeaders;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class GreetingApiTestNgDocumentationTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(Method method) {
        this.mockMvc = MockMvcBuilders
                .standaloneSetup(new GreetingController())
                .apply(documentationConfiguration(restDocumentation))
                .build();

        restDocumentation.beforeTest(getClass(), method.getName());
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }

    @Test
    public void getGreetingIsDocumented() throws Exception {
        mockMvc.perform(get("/api/greetings/{name}", "Lan")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Trace-Id", "trace-demo-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.message").value("Xin chao, Lan"))
                .andDo(document("greetings-get-success",
                        pathParameters(
                                parameterWithName("name")
                                        .description("Tên được dùng để tạo lời chào")
                        ),
                        requestHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Mã theo dõi request dùng trong ví dụ")
                        ),
                        responseFields(
                                fieldWithPath("name")
                                        .description("Tên từ URL"),
                                fieldWithPath("message")
                                        .description("Nội dung phản hồi")
                        )
                ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(value = "/api/greetings/{name}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public Map<String, String> greet(@PathVariable("name") String name) {
            Map<String, String> body = new LinkedHashMap<>();
            body.put("name", name);
            body.put("message", "Xin chao, " + name);
            return body;
        }
    }
}
~~~

### Phân tích những điểm nối quan trọng

**`new ManualRestDocumentation("build/generated-snippets")`:** chọn thư mục snippet gốc. Đây là đối tượng được tái sử dụng tuần tự giữa các test method của instance TestNG; mỗi lần chạy có lifecycle ngữ cảnh riêng nhờ `beforeTest` và `afterTest`.

**`@BeforeMethod setUp(Method method)`:** TestNG cung cấp phương thức kiểm thử sắp chạy. `method.getName()` là tên được đưa vào ngữ cảnh tài liệu. Trên TestNG, nếu dùng data provider thì nhiều lượt gọi cùng một test method có thể có cùng tên; identifier snippet cần được đặt sao cho các dữ liệu đầu vào không ghi đè lẫn nhau.

**`documentationConfiguration(restDocumentation)`:** cấu hình MockMvc sử dụng ngữ cảnh do `ManualRestDocumentation` cung cấp. Khởi tạo ManualRestDocumentation thôi chưa đủ; chính client thực thi request phải được cấu hình REST Docs.

**`beforeTest(getClass(), method.getName())`:** phải được gọi trước khi MockMvc thực hiện request. Nếu bỏ dòng này, REST Docs sẽ không có ngữ cảnh đang mở để xử lý thao tác HTTP.

**`RestDocumentationRequestBuilders.get(...)`:** import từ REST Docs để bảo toàn thông tin URL template `/api/greetings/{name}`, cần thiết khi sinh snippet `pathParameters`.

**`.andExpect(...)`:** xác nhận status và các trường JSON; điều này giúp tài liệu dựa trên response đã được kiểm chứng.

**`.andDo(document(...))`:** chọn identifier `greetings-get-success` và mô tả tham số đường dẫn, request header, response fields. Các snippet bổ sung thường có tên `path-parameters.adoc`, `request-headers.adoc` và `response-fields.adoc`.

**`@AfterMethod(alwaysRun = true)`:** có trách nhiệm gọi `afterTest()` để không để lại ngữ cảnh của lần kiểm thử trước. Đây là phần mà JUnit rule/extension thường quản lý tự động.

### Dự kiến output

Với working directory phù hợp và các snippet mặc định, thư mục đầu ra có thể là:

~~~text
build/
└── generated-snippets/
    └── greetings-get-success/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── path-parameters.adoc
        ├── request-headers.adoc
        └── response-fields.adoc
~~~

Danh sách chính xác phụ thuộc cấu hình REST Docs và phiên bản đang sử dụng. Dấu hiệu cần xác nhận là thư mục con theo identifier có các file được yêu cầu và nội dung tương ứng với request/response mà test đã kiểm chứng.

## 7. Đảm bảo cleanup khi test hoặc setup thất bại

Trong môi trường kiểm thử dài hạn, không nên để test sau kế thừa ngữ cảnh tài liệu của test trước. Đặc biệt, `beforeTest(...)` có thể báo `IllegalStateException` nếu đối tượng đã có một ngữ cảnh chưa được kết thúc.

Với **chương trình kiểm thử thủ công**, cách chắc chắn để bảo đảm cleanup là dùng `try/finally`:

~~~java
ManualRestDocumentation docs =
        new ManualRestDocumentation("build/generated-snippets");

docs.beforeTest(MyHttpChecks.class, "verifyGetGreeting");
try {
    MockMvc mvc = MockMvcBuilders
            .standaloneSetup(new GreetingController())
            .apply(documentationConfiguration(docs))
            .build();

    mvc.perform(get("/api/greetings/{name}", "Lan"))
            .andExpect(status().isOk())
            .andDo(document("greetings-manual-check"));
} finally {
    docs.afterTest();
}
~~~

Đoạn này là **khung sử dụng**: giả định `MyHttpChecks`, `GreetingController`, các import và hạ tầng MockMvc đã có. Nếu cần `pathParameters(...)` trong snippet, giữ import request builder của REST Docs như ví dụ chính.

Trong **TestNG**, `@AfterMethod(alwaysRun = true)` là hook hợp lý. Nếu bước `@BeforeMethod` có thể thất bại trước khi `beforeTest(...)` được thực hiện, thêm một cờ trạng thái cục bộ để chỉ cleanup khi đã mở ngữ cảnh:

~~~java
private boolean documentationStarted;

@BeforeMethod
public void setUp(Method method) {
    // Chuẩn bị MockMvc hoặc client HTTP trước.
    mockMvc = createConfiguredMockMvc();

    restDocumentation.beforeTest(getClass(), method.getName());
    documentationStarted = true;
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    if (documentationStarted) {
        try {
            restDocumentation.afterTest();
        } finally {
            documentationStarted = false;
        }
    }
}
~~~

Đây là **mẫu xử lý lifecycle**, cần phương thức `createConfiguredMockMvc()` của test hiện tại. Khi dùng nhiều luồng TestNG đồng thời, một boolean instance field không đủ để bảo đảm cô lập. Cần thiết kế **mỗi test execution có ngữ cảnh và trạng thái cleanup riêng**, đồng thời phân biệt identifier/output để tránh xung đột tệp.

Trong trường hợp setup thành công nhưng assertion thất bại, `afterTest()` vẫn phải được gọi; đó là lý do không nên đặt cleanup ở cuối thân test sau dòng assertion.

## 8. Tích hợp với Spring TestContext trong TestNG

Kiểm thử ở mục 6 dùng controller đơn giản. Trong ứng dụng thực, controller có thể phụ thuộc service, bean validation, message converters hoặc cấu hình MVC của Spring. Khi đó có thể dùng **Spring TestContext Framework cho TestNG** với `AbstractTestNGSpringContextTests` và `@ContextConfiguration`.

Ví dụ khung:

~~~java
@ContextConfiguration(classes = DocumentationWebConfig.class)
@WebAppConfiguration
public class WebContextDocumentationTest
        extends AbstractTestNGSpringContextTests {

    @Autowired
    private WebApplicationContext context;

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(Method method) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .apply(documentationConfiguration(restDocumentation))
                .build();

        restDocumentation.beforeTest(getClass(), method.getName());
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }

    // @Test: mockMvc.perform(...).andExpect(...).andDo(document(...))
}
~~~

Đây là **khung tích hợp**, cần khai báo import, `DocumentationWebConfig` và các bean/controller phù hợp; không phải toàn bộ chương trình sẵn chạy.

Phân biệt trách nhiệm:

- `AbstractTestNGSpringContextTests` và Spring TestContext hỗ trợ chuẩn bị ApplicationContext và inject bean khi dùng TestNG.
- `ManualRestDocumentation` quản lý lifecycle của **ngữ cảnh tạo tài liệu REST Docs**.
- `MockMvc` sử dụng `WebApplicationContext` để thực thi request với cấu hình MVC của ứng dụng.
- `document(...)` yêu cầu tạo snippet từ thao tác HTTP đã được xác nhận.

Việc dùng Spring TestContext với TestNG **không tự động thay thế** `beforeTest`/`afterTest` của ManualRestDocumentation. Khi dự án dùng Spring Boot, cũng cần phân biệt client do Boot tự cấu hình với client được tạo thủ công; tránh giả định mọi instance MockMvc đều đã tích hợp REST Docs.

## 9. Áp dụng với WebTestClient và REST Assured

`ManualRestDocumentation` triển khai `RestDocumentationContextProvider`, vì vậy cùng một ý tưởng lifecycle có thể áp dụng cho các client HTTP khác. Điều thay đổi là **cú pháp cấu hình client**, không phải ý nghĩa của `beforeTest` và `afterTest`.

### WebTestClient

Với ứng dụng có `ApplicationContext` phù hợp:

~~~java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation("build/generated-snippets");

private WebTestClient webTestClient;

@BeforeMethod
public void setUp(Method method) {
    webTestClient = WebTestClient.bindToApplicationContext(applicationContext)
            .configureClient()
            .filter(WebTestClientRestDocumentation
                    .documentationConfiguration(restDocumentation))
            .build();

    restDocumentation.beforeTest(getClass(), method.getName());
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    restDocumentation.afterTest();
}
~~~

Khung này cần biến `applicationContext` được khởi tạo hợp lệ, các import và dependency `spring-restdocs-webtestclient` tương thích. Khi gọi request, dùng API `WebTestClientRestDocumentation.document(...)` hoặc cách tích hợp phù hợp với phiên bản REST Docs.

### REST Assured

Với một dịch vụ HTTP sẵn sàng được kiểm thử:

~~~java
private final ManualRestDocumentation restDocumentation =
        new ManualRestDocumentation("build/generated-snippets");

private RequestSpecification specification;

@BeforeMethod
public void setUp(Method method) {
    specification = new RequestSpecBuilder()
            .addFilter(RestAssuredRestDocumentation
                    .documentationConfiguration(restDocumentation))
            .build();

    restDocumentation.beforeTest(getClass(), method.getName());
}

@AfterMethod(alwaysRun = true)
public void tearDown() {
    restDocumentation.afterTest();
}
~~~

Khung này dùng các loại `RequestSpecification`, `RequestSpecBuilder` của REST Assured và các API từ `spring-restdocs-restassured`. Test còn phải xác định URL/base URI, thực thi request, assertion và filter `document(...)` thích hợp.

| Công cụ | Cách gắn REST Docs vào client | Bối cảnh |
| --- | --- | --- |
| MockMvc | `MockMvcBuilders...apply(documentationConfiguration(docs))` | Kiểm thử Spring MVC trong tiến trình |
| WebTestClient | `configureClient().filter(documentationConfiguration(docs))` | Kiểm thử WebFlux hoặc HTTP theo cấu hình client |
| REST Assured | `RequestSpecBuilder().addFilter(documentationConfiguration(docs))` | Kiểm thử API HTTP bằng REST Assured |

Không nên thay tên package/import một cách máy móc giữa ba công cụ: mỗi integration module có lớp `documentationConfiguration`/`document` tương ứng.

## 10. Từ snippet đến Asciidoctor, Markdown và CI

`ManualRestDocumentation` có constructor nhận output directory:

~~~java
new ManualRestDocumentation("build/generated-snippets")
~~~

Khi test gọi `document("greetings-get-success", ...)`, kết quả thường nằm ở:

~~~text
build/generated-snippets/greetings-get-success/
~~~

**Phân biệt hai cấp đường dẫn:** constructor chọn **thư mục gốc**, còn `document(identifier)` xác định **thư mục con**. Đường dẫn tương đối có thể phụ thuộc working directory của tiến trình test, do đó cần kiểm tra cấu hình IDE, multi-module build và CI.

Một trang Asciidoctor có thể nhúng snippet như sau:

~~~asciidoc
= Greeting API

== Lấy lời chào

=== HTTP request
include::{snippets}/greetings-get-success/http-request.adoc[]

=== Request header
include::{snippets}/greetings-get-success/request-headers.adoc[]

=== Path parameter
include::{snippets}/greetings-get-success/path-parameters.adoc[]

=== HTTP response
include::{snippets}/greetings-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/greetings-get-success/response-fields.adoc[]
~~~

Ở đây thuộc tính `{snippets}` phải được đặt trong cấu hình Asciidoctor để chỉ đến thư mục gốc mà test đang ghi. Để bảo đảm thứ tự, tác vụ tạo tài liệu phải phụ thuộc vào test suite **TestNG** tương ứng.

Ví dụ Gradle Groovy DSL minh họa:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    useTestNG()
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir
}
~~~

Ví dụ giả định dự án đã áp dụng plugin Asciidoctor có task tên `asciidoctor`; cú pháp thuộc tính có thể thay đổi theo phiên bản plugin. Với Maven, cấu hình giai đoạn test bằng TestNG, rồi chỉ định plugin Asciidoctor đọc từ thư mục snippet tương ứng (thường là `target/generated-snippets` nếu dùng output dir của Maven).

Nếu dùng pipeline Markdown, hãy nhớ snippet mặc định của REST Docs thường ở dạng Asciidoctor `.adoc`. Cần cấu hình chuyển đổi/nhúng tương thích thay vì giả định output directory sẽ tự làm thay đổi định dạng.

Quy trình tổng thể:

~~~text
TestNG hoặc custom test runner
        |
        v
ManualRestDocumentation.beforeTest(...)
        |
        v
MockMvc / WebTestClient / REST Assured
        |
        v
HTTP assertions + document(...)
        |
        v
ManualRestDocumentation.afterTest()
        |
        v
generated-snippets/{identifier}/
        |
        v
Asciidoctor / pipeline Markdown
        |
        v
Tài liệu REST API trong build và CI
~~~

Bước build cần kiểm tra sự tồn tại của snippet thiết yếu và không đưa dữ liệu nhạy cảm từ request/response thật vào trang tài liệu được công bố. Khi đổi output dir hoặc tên identifier, hãy cập nhật cả nơi sinh và nơi đọc tài liệu.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `IllegalStateException` khi gọi `beforeTest(...)` | Ngữ cảnh test trước chưa được giải phóng hoặc gọi `beforeTest` hai lần. | Kiểm tra đối ứng giữa `beforeTest` và `afterTest`, tránh gọi lặp trong setup. |
| Request được xử lý nhưng không tạo snippet | Quên `document(...)` hoặc cấu hình REST Docs trên sai client. | Xác minh `documentationConfiguration(docs)` áp dụng vào client đang chạy và có lệnh `document`. |
| Lỗi do không có ngữ cảnh REST Docs | Chưa gọi `beforeTest(...)` trước request hoặc đã gọi `afterTest()` quá sớm. | Điều chỉnh thứ tự setup/test/teardown, dùng hook per-test. |
| Một test thất bại khiến test sau lỗi | Thiếu `afterTest()` khi exception xảy ra. | Dùng `@AfterMethod(alwaysRun = true)` hoặc `try/finally`. |
| Không có file snippet dù build báo thành công | TestNG test không được phát hiện hoặc không được chạy. | Kiểm tra test engine, Gradle `useTestNG()`, cấu hình Maven và thống kê test. |
| `pathParameters(...)` không khớp URL | Dùng builder không giữ template của path. | Dùng `RestDocumentationRequestBuilders.get` với URL `/api/greetings/{name}`. |
| Response fields kiểm tra thất bại | JSON response không khớp mô tả, hoặc thiếu một field. | Đối chiếu body thực, assertion và `fieldWithPath(...)`. |
| Snippet xuất hiện ở thư mục khác | Working directory khác giữa IDE/build/CI. | Xác minh đường dẫn vật lý và đồng bộ output directory. |
| Các test TestNG data-driven ghi đè nhau | Nhiều lượt test chia sẻ cùng identifier. | Tạo định danh snippet theo kịch bản hoặc dữ liệu kiểm thử có thể dự đoán. |
| Test chạy song song không ổn định | Ngữ cảnh/tên file/đối tượng mutable bị chia sẻ không kiểm soát. | Cô lập state per-execution và tên output; kiểm tra chiến lược chạy song song. |
| Asciidoctor không tìm thấy include | Chưa chạy test, thiếu snippet hoặc thuộc tính `snippets` sai. | Xác minh task dependency và đường dẫn `{snippets}` sau khi test sinh file. |

Một cách chẩn đoán có hệ thống:

1. **Bộ chạy TestNG có thực sự chạy test không?**
2. **Có gọi `beforeTest(...)` đúng một lần trước thao tác HTTP không?**
3. **Client dùng để gửi request có được cấu hình REST Docs không?**
4. **Assertion status/body có thành công không?**
5. **`document(...)` có được gọi và dùng identifier đúng không?**
6. **`afterTest()` có được gọi dù test thất bại không?**
7. **Snippet nằm ở thư mục nào và bước Asciidoctor/Markdown đang đọc ở đâu?**

## 12. Bài thực hành: kiểm chứng lifecycle ngoài JUnit

Bắt đầu với `GreetingApiTestNgDocumentationTest` ở mục 6:

1. Chạy TestNG và xác minh status/body kỳ vọng; tìm `greetings-get-success/http-request.adoc`, `request-headers.adoc` và `response-fields.adoc`.
2. Tạm bỏ `restDocumentation.beforeTest(...)` trong `@BeforeMethod`, chạy test và quan sát lỗi của thao tác tài liệu hóa. Khôi phục lệnh.
3. Tạm bỏ `@AfterMethod` hoặc `afterTest()` rồi chạy liên tiếp nhiều test trên cùng đối tượng (ở môi trường thử nghiệm đã được cô lập). Quan sát tác động của ngữ cảnh chưa dọn, sau đó khôi phục cleanup.
4. Chuyển `afterTest()` vào `finally` trong một chương trình kiểm thử HTTP tự chạy, chủ động tạo exception để xác nhận nhánh cleanup vẫn thực hiện.
5. Đổi output directory thành `build/api-snippets`, chạy lại test, cập nhật Asciidoctor để include đúng file.
6. Thêm một kiểm thử response lỗi như `404 Not Found` với assertion và identifier `greetings-get-not-found`. Đối chiếu response thực tế với snippet.
7. Nếu dùng TestNG `@DataProvider` hoặc chạy song song, thiết kế identifier riêng cho từng kịch bản, rồi xác minh các file được sinh mà không ghi đè lẫn nhau.
8. Đưa bài kiểm thử TestNG và bước dựng tài liệu vào CI; cho build thất bại khi test không chạy hoặc snippet bắt buộc không xuất hiện.

**Tiêu chí hoàn thành:** bạn có thể phân biệt ngữ cảnh test với HTTP operation, nêu đúng thời điểm mở/đóng ngữ cảnh, chọn client đã cấu hình REST Docs, kiểm chứng snippet và chỉ ra được liên kết tới tài liệu được dựng.

## 13. Ghi nhớ

- **`ManualRestDocumentation`** quản lý ngữ cảnh Spring REST Docs thủ công khi **không dùng JUnit**, đặc biệt phù hợp với TestNG hoặc bộ chạy kiểm thử riêng.
- Phải ghép **`beforeTest(testClass, testMethodName)`** với **`afterTest()`** cho từng lần thực thi test; cleanup cần chạy kể cả khi assertion thất bại.
- **`documentationConfiguration(docs)`** nối ngữ cảnh vào client MockMvc/WebTestClient/REST Assured; **`document(identifier, ...)`** mới yêu cầu tạo snippet.
- Constructor có thể chỉ định **thư mục output gốc**, còn identifier quyết định thư mục con; cả hai phải khớp cấu hình build, Asciidoctor/Markdown và CI.
- Tài liệu API đáng tin cậy cần đủ chuỗi **chạy test thực sự → xác minh response → sinh snippet → biên soạn và xuất bản tài liệu**.

## Tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html): phần thiết lập kiểm thử khi không dùng JUnit.
- [ManualRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html): constructor, `beforeTest`, `afterTest` và `RestDocumentationContextProvider`.

Hãy chọn phiên bản tài liệu và thư viện tương ứng với phiên bản Spring REST Docs đang dùng trong dự án, vì cách tích hợp với Spring Boot, TestNG hoặc công cụ biên soạn có thể khác nhau giữa các dòng phiên bản.

