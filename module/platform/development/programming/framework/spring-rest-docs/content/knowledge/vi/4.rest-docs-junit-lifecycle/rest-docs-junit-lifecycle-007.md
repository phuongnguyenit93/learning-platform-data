# JUnit 5 được khuyến nghị và các framework khác

## 1. JUnit 5 phù hợp với lifecycle của Spring REST Docs như thế nào?

Module **SPRING_REST_DOCS** hướng dẫn tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP. Các bài test dùng MockMvc, WebTestClient hoặc REST Assured sẽ thực hiện request, xác nhận status/header/body rồi sinh snippet để biên soạn tài liệu Asciidoctor hoặc Markdown và chạy trong build/CI.

Spring REST Docs không yêu cầu toàn bộ dự án phải dùng duy nhất một test framework. Tuy nhiên, **JUnit Jupiter (JUnit 5)** là lựa chọn thuận tiện khi bắt đầu dự án mới vì Spring REST Docs cung cấp extension tích hợp trực tiếp với lifecycle của Jupiter. Extension tự quản lý ngữ cảnh tài liệu cho từng test và cho phép inject `RestDocumentationContextProvider` vào callback của test.

Các lựa chọn thường gặp:

| Framework | Cách tích hợp lifecycle | Mức độ thuận tiện |
| --- | --- | --- |
| JUnit Jupiter (JUnit 5) | `RestDocumentationExtension` và parameter injection | Được khuyến nghị cho dự án mới |
| JUnit 4 | `JUnitRestDocumentation` qua `@Rule` | Có tích hợp rõ ràng cho dự án cũ |
| TestNG | Tự gọi lifecycle bằng `ManualRestDocumentation` trong `@BeforeMethod`/`@AfterMethod` | Cần quản lý rõ setup/cleanup |
| Spock | Có thể dùng API REST Docs ở phần setup/cleanup của specification, thường qua `ManualRestDocumentation` | Phù hợp khi dự án đã chọn Spock |
| Framework tự viết | Tự điều phối `ManualRestDocumentation` hoặc context provider | Linh hoạt, nhưng người viết chịu trách nhiệm lifecycle |

“Được khuyến nghị” ở đây nói đến sự thuận tiện tích hợp và hệ sinh thái hiện đại, không có nghĩa REST Docs chỉ hoạt động với JUnit 5. Điểm chung của mọi lựa chọn là REST Docs cần biết **test nào đang chạy**, **snippet được ghi vào đâu** và **khi nào kết thúc context của test**.

## 2. JUnit Jupiter lifecycle cơ bản

Một test class Jupiter thường có các callback:

- `@BeforeAll` chạy một lần trước các test trong class.
- `@BeforeEach` chạy trước mỗi test method.
- `@Test` đánh dấu test method.
- `@AfterEach` chạy sau mỗi test method.
- `@AfterAll` chạy một lần sau tất cả test trong class.

Với cấu hình mặc định `@TestInstance(Lifecycle.PER_METHOD)`, JUnit tạo instance mới của test class cho mỗi test method. `@BeforeAll` và `@AfterAll` thường phải là static. Có thể chọn `PER_CLASS` để dùng instance callback, nhưng cần kiểm soát state chia sẻ.

Spring REST Docs có extension:

```java
@ExtendWith(RestDocumentationExtension.class)
class AccountDocumentationTest {
    // Test methods
}
```

`RestDocumentationExtension` tích hợp vào Jupiter extension model để tạo và quản lý documentation context. Extension cung cấp `RestDocumentationContextProvider` qua parameter resolution. Trong setup, truyền provider cho `documentationConfiguration(...)` khi tạo MockMvc/WebTestClient/REST Assured filter thích hợp.

### 2.1. Cấu hình MockMvc với @BeforeEach

Ví dụ dùng Spring MVC context có sẵn:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@ExtendWith({SpringExtension.class, RestDocumentationExtension.class})
class AccountDocumentationTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk());
    }
}
```

Nếu dự án dùng Spring Boot/JUnit Jupiter test integration và cấu hình tự động tương ứng, `@SpringBootTest` thường đã được đăng ký extension Spring thông qua meta-annotation; ví dụ có thể rút gọn thành `@ExtendWith(RestDocumentationExtension.class)`. Để làm rõ trách nhiệm, đoạn code trên thể hiện rõ cả hai extension.

Luồng mỗi test:

1. Jupiter khởi tạo test instance và inject dependency của Spring.
2. `RestDocumentationExtension` thiết lập context cho test.
3. `@BeforeEach` nhận `RestDocumentationContextProvider` rồi cấu hình MockMvc.
4. Test gửi request và xác minh HTTP response.
5. `document(...)` tạo snippet trong context của test.
6. Jupiter chạy cleanup callback và extension kết thúc documentation context.

Không cần tự tạo một thư mục output mới trong từng test method nếu đã dùng extension và cấu hình output directory theo dự án.

### 2.2. Setup thủ công cho standalone MockMvc

Với controller không cần Spring application context:

```java
@ExtendWith(RestDocumentationExtension.class)
class OrderControllerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new OrderController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void getOrder() throws Exception {
        mockMvc.perform(get("/api/orders/100"))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }
}
```

Standalone setup nhanh và cô lập, nhưng không tự nạp mọi thành phần cấu hình production. Nếu controller phụ thuộc converter, advice, validator, filter hoặc security config, cần đăng ký đúng các thành phần đó hoặc dùng integration test với application context.

## 3. Extension cung cấp gì và không làm gì?

Extension giúp quản lý documentation context và tích hợp với lifecycle Jupiter. Nó không thay thế các assertion HTTP, không tự viết descriptor field và không quyết định nội dung snippet.

| Công việc | Thành phần chịu trách nhiệm |
| --- | --- |
| Tạo/kết thúc context cho mỗi test | `RestDocumentationExtension` |
| Cung cấp context cho cấu hình client | `RestDocumentationContextProvider` |
| Gửi request HTTP trong test | MockMvc, WebTestClient hoặc REST Assured |
| Kiểm tra status/header/body | Assertion của framework HTTP test |
| Chọn snippet và mô tả field | `document(...)`, `requestFields(...)`, `responseFields(...)` |
| Ghép snippet vào tài liệu | Asciidoctor hoặc pipeline tài liệu của dự án |

Ví dụ, nếu test không gọi `andDo(document(...))` với MockMvc thì extension vẫn có thể chạy bình thường, nhưng test đó không yêu cầu tạo snippet REST Docs. Ngược lại, nếu test dùng `document(...)` nhưng MockMvc chưa được cấu hình với documentation configurer từ context tương ứng, việc sinh snippet không được kết nối đúng lifecycle.

## 4. Cấu hình output snippets

Đường dẫn snippet thường được cấu hình tập trung thay vì hard-code trong từng test:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
            .apply(documentationConfiguration(documentation)
                    .snippets().withDefaults(
                            CliDocumentation.curlRequest(),
                            HttpDocumentation.httpRequest(),
                            HttpDocumentation.httpResponse()
                    ))
            .build();
}
```

Đoạn code trên minh họa cấu hình default snippets bổ sung; trong dự án thật cần import helper tương ứng hoặc giữ cấu hình mặc định của phiên bản Spring REST Docs đang dùng. Nếu cấu hình output directory trong build, hãy bảo đảm test task và Asciidoctor cùng tham chiếu một thư mục.

Với Gradle thường gặp:

```text
build/generated-snippets/
```

Với Maven thường gặp:

```text
target/generated-snippets/
```

Đây là quy ước phổ biến; dự án có thể tùy chỉnh. Cần thống nhất giữa test setup, plugin Asciidoctor và CI.

## 5. JUnit 4: tích hợp qua @Rule

Dự án dùng JUnit 4 có thể tích hợp Spring REST Docs bằng `JUnitRestDocumentation`:

```java
import org.junit.Rule;
import org.junit.Test;
import org.junit.Before;
import org.springframework.restdocs.JUnitRestDocumentation;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

public class LegacyAccountDocumentationTest {

    @Rule
    public JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("target/generated-snippets");

    private MockMvc mockMvc;

    @Before
    public void setUp() {
        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(this.restDocumentation))
                .build();
    }

    @Test
    public void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andDo(document("accounts-get"));
    }
}
```

`JUnitRestDocumentation` là JUnit 4 Rule quản lý documentation context theo test. Ví dụ chỉ định output directory là `target/generated-snippets`; có thể thay bằng đường dẫn build của dự án. Test method dùng `@Test` của JUnit 4, không phải annotation Jupiter.

Không trộn ngẫu nhiên hai mô hình trong cùng một class: `@Rule` thuộc JUnit 4, còn `@ExtendWith`/`@BeforeEach` thuộc JUnit Jupiter. Nếu migration từ JUnit 4 sang Jupiter, thay cả lifecycle integration và dependency/import, không chỉ đổi tên annotation.

## 6. TestNG hoặc framework không có tích hợp extension tương ứng

Với framework không có extension/rule tích hợp trực tiếp, có thể quản lý bằng `ManualRestDocumentation`. Ý tưởng là:

1. Tạo một đối tượng `ManualRestDocumentation` cho test fixture.
2. Gọi `beforeTest(testClass, testMethodName)` trước test.
3. Cấu hình MockMvc hoặc client bằng documentation provider đó.
4. Gọi `afterTest()` sau test kể cả khi assertion thất bại.

Ví dụ cấu trúc TestNG:

```java
import org.springframework.restdocs.ManualRestDocumentation;
import org.testng.annotations.AfterMethod;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.Test;

class TestNgAccountDocumentationTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation();

    private MockMvc mockMvc;

    @BeforeMethod
    public void setUp(java.lang.reflect.Method testMethod) {
        restDocumentation.beforeTest(
                getClass(), testMethod.getName());

        mockMvc = MockMvcBuilders.standaloneSetup(new AccountController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    public void getAccount() throws Exception {
        mockMvc.perform(get("/api/accounts/42"))
                .andExpect(status().isOk())
                .andDo(document("accounts-get"));
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        restDocumentation.afterTest();
    }
}
```

Đây là khung minh họa: cần import MockMvc, MockMvcBuilders và các static request/assertion/documentation giống ví dụ MockMvc ở trên. Dùng `alwaysRun = true` trong TestNG giúp cleanup được gọi cả khi setup/test thất bại theo quy tắc lifecycle của TestNG.

Không gọi `beforeTest` một lần cho cả class nếu snippet context cần tách theo method. Mỗi test cần một context tương ứng với tên class/method và được kết thúc đúng một lần. Nếu framework có hook trước/sau từng test khác tên, ánh xạ cùng trách nhiệm lifecycle vào hook tương đương.

## 7. Spock và Groovy specifications

Spock dùng các block `setup()`, `cleanup()`, `setupSpec()` và `cleanupSpec()` thay cho annotation kiểu JUnit. Với Spring REST Docs, có thể quản lý context thủ công qua `ManualRestDocumentation` nếu không dùng một integration bridge riêng.

Ví dụ cấu trúc:

```groovy
import org.springframework.restdocs.ManualRestDocumentation
import spock.lang.Specification

class AccountDocumentationSpec extends Specification {

    ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation()

    def setup() {
        restDocumentation.beforeTest(
                getClass(), specificationContext.currentFeature.name)
        // Tạo MockMvc/WebTestClient bằng
        // documentationConfiguration(restDocumentation)
    }

    def cleanup() {
        restDocumentation.afterTest()
    }

    def "GET account documents the response"() {
        expect:
        // Gửi request, assert response và gọi document(...)
        true
    }
}
```

Đoạn trên biểu diễn ánh xạ lifecycle, không phải test endpoint hoàn chỉnh. Trong specification thực tế, cần cấu hình client, request, assertion và snippet. Đảm bảo `cleanup()` chạy ngay cả khi feature thất bại, đồng thời không chia sẻ một documentation context mutable giữa các feature song song.

Nếu dự án Spock đã có tích hợp Spring Test/Spock, tiếp tục dùng mô hình đó nhưng giữ quy tắc: context bắt đầu trước test, snippet gắn với đúng test và cleanup luôn hoàn tất.

## 8. Dùng WebTestClient hoặc REST Assured vẫn giữ cùng ý tưởng lifecycle

Jupiter extension không chỉ dành cho MockMvc. Nó cũng có thể cung cấp documentation context để cấu hình WebTestClient hoặc REST Assured.

### 8.1. WebTestClient

Ví dụ cấu hình:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    webTestClient = WebTestClient.bindToController(new AccountController())
            .configureClient()
            .filter(documentationConfiguration(documentation))
            .build();
}
```

Sau đó gửi request và ghi snippet theo API của WebTestClient REST Docs:

```java
webTestClient.get()
        .uri("/api/accounts/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .consumeWith(document("accounts-get"));
```

Trong ứng dụng có WebFlux server thực tế, có thể bind vào application context hoặc server tùy loại test. Chọn đúng cấu hình để test phản ánh converter/filter/security và routing thực tế.

### 8.2. REST Assured

Với REST Assured, documentation context được dùng để tạo filter:

```java
@BeforeEach
void setUp(RestDocumentationContextProvider documentation) {
    this.spec = new RequestSpecBuilder()
            .addFilter(documentationConfiguration(documentation))
            .build();
}
```

Trong test:

```java
given(this.spec)
    .filter(document("accounts-get"))
    .when()
    .get("/api/accounts/42")
    .then()
    .statusCode(200);
```

Import và cách kết hợp filter có thể khác theo phiên bản REST Docs/REST Assured. Hãy dùng integration artifact tương ứng với client đang chọn và xác nhận snippet được tạo từ HTTP exchange thật.

Dù dùng client nào, lifecycle chung vẫn gồm setup documentation context, gắn configurer/filter, chạy HTTP test, gọi document và cleanup.

## 9. Test parameterized, dynamic tests và identifier snippet

JUnit Jupiter hỗ trợ `@ParameterizedTest`, `@MethodSource`, `@CsvSource` và `@TestFactory`. Khi nhiều input tạo snippet, cần chọn identifier duy nhất, có ý nghĩa và ổn định.

Ví dụ:

```java
@ParameterizedTest
@ValueSource(strings = {"42", "43"})
void getAccount(String accountId) throws Exception {
    mockMvc.perform(get("/api/accounts/{id}", accountId))
            .andExpect(status().isOk())
            .andDo(document("accounts-" + accountId));
}
```

Hai test sẽ tạo snippet:

```text
accounts-42/
accounts-43/
```

Không dùng cùng identifier cho nhiều response khác nhau nếu test có thể chạy song song hoặc tạo nội dung khác nhau. Nếu cùng endpoint có nhiều kịch bản như success/not-found, hãy phân biệt rõ `accounts-get-success` và `accounts-get-not-found`.

Dynamic tests cũng cần identifier riêng:

```java
@TestFactory
Stream<DynamicTest> accountScenarios() {
    return Stream.of("42", "43")
            .map(id -> dynamicTest("account " + id, () -> {
                // Request, assertions và document("accounts-" + id)
            }));
}
```

Lưu ý: lifecycle của `@BeforeEach` áp dụng cho test factory method, không chạy lại riêng cho từng dynamic test node theo cách test method thông thường. Nếu mỗi dynamic test cần documentation context riêng, hãy tự tổ chức lifecycle trong executable hoặc ưu tiên parameterized test để tận dụng lifecycle theo từng invocation.

## 10. Chạy song song và quản lý context

JUnit Jupiter có thể chạy test song song khi bật cấu hình. Khi REST Docs tạo file snippet, cần bảo đảm:

- Mỗi test có documentation context riêng.
- Identifier snippet không trùng nếu nội dung khác nhau.
- Không dùng một `MockMvc`/WebTestClient mutable chung nếu setup của test khác nhau.
- Không chia sẻ `ManualRestDocumentation` giữa test concurrent.
- Không để hai test ghi cùng một file snippet.
- Fixture và dữ liệu test không phụ thuộc thứ tự chạy.

Nếu hai test cùng ghi `accounts-get`, kết quả có thể bị ghi đè hoặc gây lỗi cạnh tranh. Dùng identifier phân biệt theo scenario; không chỉ thêm tên method ngẫu nhiên nếu muốn snippet ổn định lâu dài. Khi muốn cô lập output mạnh hơn, cấu hình thư mục theo test/task hoặc tắt parallelism cho nhóm test sinh tài liệu cho đến khi identifier/context được thiết kế an toàn.

## 11. Chọn framework theo dự án

| Bối cảnh | Lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Dự án Spring mới, chưa có test framework legacy | JUnit Jupiter | Extension trực tiếp, parameterized tests và ecosystem mới |
| Dự án đang dùng JUnit 4 ổn định | Tiếp tục JUnit 4 integration | Không cần migration chỉ để sinh REST Docs |
| Dự án dùng TestNG | TestNG + ManualRestDocumentation | Ánh xạ lifecycle trước/sau method |
| Nhóm đã dùng Spock/Groovy | Spock + manual lifecycle hoặc integration phù hợp | Giữ ngôn ngữ kiểm thử hiện có |
| Nhiều test client khác nhau | Chọn theo HTTP stack | REST Docs có tích hợp cho MockMvc, WebTestClient và REST Assured |

Đừng đổi framework test chỉ vì muốn dùng Spring REST Docs. Chi phí migration, plugin build, extension khác, reporting và convention của nhóm cần được cân nhắc. Nếu đang tạo dự án mới, Jupiter thường là điểm bắt đầu ít cấu hình hơn; nếu dự án đã có JUnit 4/Spock/TestNG, vẫn có thể tích hợp bằng lifecycle tương ứng.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không inject được `RestDocumentationContextProvider` | Thiếu `@ExtendWith(RestDocumentationExtension.class)` hoặc method signature không ở lifecycle callback/test được hỗ trợ | Đăng ký extension và đặt parameter đúng callback |
| `documentationConfiguration` không nhận context mong muốn | Tạo configurer từ provider khác hoặc scope không đúng test | Truyền context được cấp cho test đang chạy |
| JUnit 4 Rule không được kích hoạt | Đang chạy engine Jupiter nhưng chỉ có `@Rule` JUnit 4 | Dùng Vintage engine khi cần legacy hoặc chuyển sang Jupiter extension |
| TestNG không tạo snippet | Chưa gọi `beforeTest`/`afterTest` hoặc cấu hình sai provider | Dùng `ManualRestDocumentation` và bảo đảm cleanup |
| Snippet bị ghi đè | Nhiều test dùng chung identifier | Tạo identifier ổn định, riêng cho scenario |
| Context không được cleanup khi test fail | Cleanup đặt ở logic chỉ chạy khi test thành công | Dùng `@AfterEach`/`@AfterMethod(alwaysRun = true)` hoặc hook cleanup tương đương |
| Kết quả không ổn định khi chạy song song | Dùng chung context, client hoặc snippet path | Tách context/identifier và kiểm soát concurrency |
| Test Jupiter chạy nhưng không sinh snippet | Chưa gọi `document(...)` hoặc chưa cấu hình REST Docs trên client | Gắn configurer/filter và gọi document trong HTTP test |
| Dùng dynamic test nhưng setup không chạy mỗi node | Hiểu sai lifecycle của `@TestFactory` | Dùng parameterized test hoặc quản lý context trong executable |
| Chọn framework chỉ vì REST Docs | Bỏ qua chi phí migration | Giữ framework hiện tại nếu nó đã đáp ứng nhu cầu |

## 13. Bài thực hành

Thực hành trên endpoint `GET /api/accounts/{id}`:

1. Tạo một test class Jupiter có `@ExtendWith(RestDocumentationExtension.class)`; inject `RestDocumentationContextProvider` vào `@BeforeEach`.
2. Cấu hình MockMvc, gửi request và xác nhận status/body trước khi gọi `document("accounts-get")`.
3. Chạy hai test method và quan sát mỗi test có documentation context riêng.
4. Tạo `@ParameterizedTest` cho nhiều account ID; sinh identifier khác nhau và kiểm tra snippet không ghi đè.
5. Chuyển test sang JUnit 4, dùng `JUnitRestDocumentation` Rule và so sánh lifecycle với Jupiter.
6. Viết một test TestNG dùng `ManualRestDocumentation`; bảo đảm `afterTest()` chạy cả khi assertion thất bại.
7. Thử cấu hình WebTestClient hoặc REST Assured, dùng cùng documentation context và xác minh snippet HTTP được sinh.
8. Bật parallel execution trong một nhóm test có identifier khác nhau; kiểm tra output không cạnh tranh.
9. Tạo một dynamic test và xác nhận `@BeforeEach` không phải callback được gọi riêng cho từng dynamic node.
10. Chạy task test trước task Asciidoctor, kiểm tra tài liệu cuối tham chiếu đúng snippets mới nhất.

**Tiêu chí hoàn thành:** bạn giải thích được lifecycle tích hợp của JUnit Jupiter, cấu hình `RestDocumentationExtension` với MockMvc, biết JUnit 4 dùng Rule và framework khác có thể dùng `ManualRestDocumentation`, đồng thời quản lý identifier/context an toàn cho parameterized, dynamic và parallel tests.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/reference/getting-started/index.html): thiết lập test framework và tích hợp Spring REST Docs.
- [Spring REST Docs — API Documentation](https://docs.spring.io/spring-restdocs/reference/index.html): các tích hợp MockMvc, WebTestClient và REST Assured.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): lifecycle, extension model, parameterized tests và dynamic tests.
- [Spring REST Docs API — ManualRestDocumentation](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html): lifecycle thủ công cho test framework khác.
- [Spring REST Docs API — RestDocumentationExtension](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html): extension dành cho JUnit Jupiter.
