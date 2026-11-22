# beforeTest và afterTest cho lifecycle thủ công

## 1. Mục tiêu: tự quản lý vòng đời Spring REST Docs

**Spring REST Docs** tạo tài liệu REST API từ các thao tác HTTP thực sự được kiểm thử. Một bài kiểm thử có thể sử dụng **MockMvc**, **WebTestClient** hoặc **REST Assured** để gửi request, kiểm chứng status, header và payload, sau đó sinh các snippet mô tả request, response, tham số, payload hoặc header. Các snippet này được biên soạn bằng **Asciidoctor/Markdown** và đưa vào quy trình build, CI.

Trong module **SPRING_REST_DOCS**, chương **JUnit và lifecycle** tập trung vào câu hỏi: *Ai chịu trách nhiệm khởi tạo và kết thúc ngữ cảnh tài liệu của từng lần chạy test?*

- Với JUnit Jupiter, `RestDocumentationExtension` làm việc đó qua cơ chế extension.
- Với JUnit 4, `JUnitRestDocumentation` làm việc đó qua rule.
- Với **TestNG**, bộ chạy kiểm thử tự viết hoặc chương trình kiểm chứng HTTP không dùng JUnit, ta có thể điều khiển trực tiếp **`ManualRestDocumentation`** thông qua **`beforeTest(...)`** và **`afterTest()`**.

Bài này đi sâu vào **cặp phương thức lifecycle**: gọi khi nào, ghép cặp ra sao, bảo đảm cleanup khi test thất bại, cách xử lý trường hợp setup lỗi và những lưu ý khi chạy nhiều test hoặc chạy song song.

Kết thúc bài học, bạn có thể:

1. Giải thích vai trò của `beforeTest(Class<?>, String)` và `afterTest()`.
2. Viết bộ kiểm thử HTTP có lifecycle thủ công chính xác.
3. Tích hợp lifecycle với TestNG hoặc với `try/finally` trong một chương trình tự chạy.
4. Phân biệt ngữ cảnh test, cấu hình HTTP client và thao tác `document(...)`.
5. Kiểm tra snippet được sinh và bảo đảm build/CI chỉ đọc đầu ra của các test đã chạy thành công.

## 2. ManualRestDocumentation và hai phương thức cốt lõi

`ManualRestDocumentation` thuộc package:

~~~java
org.springframework.restdocs.ManualRestDocumentation
~~~

Đối tượng này triển khai `RestDocumentationContextProvider` và quản lý ngữ cảnh REST Docs mà test phải thiết lập khi không có JUnit rule/extension làm hộ.

Ví dụ ngắn nhất về chu kỳ sử dụng:

~~~java
ManualRestDocumentation restDocs =
        new ManualRestDocumentation("build/generated-snippets");

restDocs.beforeTest(BookDocumentationTest.class, "getBook");
try {
    // Thực hiện HTTP request, assert response và document(...).
} finally {
    restDocs.afterTest();
}
~~~

Ý nghĩa của hai phương thức:

| Phương thức | Thời điểm gọi | Vai trò |
| --- | --- | --- |
| `beforeTest(Class<?> testClass, String testMethodName)` | Trước khi bắt đầu thao tác HTTP cần tài liệu hóa | Mở ngữ cảnh REST Docs cho lần thực thi test đã được xác định bằng lớp và tên phương thức. |
| `afterTest()` | Sau khi test kết thúc, kể cả khi có lỗi | Kết thúc và giải phóng ngữ cảnh của lần test. |

`beforeTest(...)` **không** gửi request, khởi động server hay tự tạo snippet. `afterTest()` **không** xuất trang Asciidoctor hay xác nhận assertion. Hai phương thức chỉ phụ trách **ngữ cảnh** cho quá trình tạo tài liệu.

Một đối tượng có thể có constructor không tham số hoặc nhận output directory:

~~~java
ManualRestDocumentation defaultOutput = new ManualRestDocumentation();

ManualRestDocumentation customOutput =
        new ManualRestDocumentation("build/generated-snippets");
~~~

Trong trường hợp dùng constructor có đường dẫn, REST Docs ghi snippet dưới thư mục được chỉ định khi `document(...)` được gọi. Đường dẫn tương đối thường được phân giải theo working directory của tiến trình test.

### Lớp và tên phương thức được truyền vào để làm gì?

Ví dụ:

~~~java
restDocs.beforeTest(BookDocumentationTest.class, "shouldGetBookById");
~~~

- `BookDocumentationTest.class` là danh tính lớp kiểm thử.
- `"shouldGetBookById"` mô tả phương thức hoặc kịch bản kiểm thử.
- Hai đối số này giúp cung cấp thông tin định danh ngữ cảnh cho REST Docs; chúng **không** thay thế identifier ở `document("books-get", ...)`.

Identifier `books-get` vẫn quyết định thư mục snippet con. Truyền tên method `shouldGetBookById` không tự khiến REST Docs ghi vào thư mục `shouldGetBookById` nếu mã test gọi `document("books-get", ...)`.

## 3. Ba lớp trách nhiệm cần phân biệt

Trong một kiểm thử tài liệu hóa REST API có **ba bước độc lập**:

| Bước | API minh họa | Tác động |
| --- | --- | --- |
| Quản lý lifecycle | `beforeTest(...)` / `afterTest()` | Mở và đóng ngữ cảnh REST Docs. |
| Cấu hình HTTP client | `documentationConfiguration(restDocs)` | Kết nối ngữ cảnh với MockMvc hoặc client được tích hợp. |
| Tạo snippet | `document("books-get", descriptors...)` | Ghi tài liệu cho thao tác HTTP cụ thể. |

Sơ đồ tổng thể:

~~~mermaid
flowchart TD
    A["Bộ chạy test: TestNG hoặc custom"] --> B["beforeTest(testClass, methodName)"]
    B --> C["REST Docs context được mở"]
    C --> D["Client đã áp dụng documentationConfiguration"]
    D --> E["HTTP request"]
    E --> F["Kiểm tra status / header / body"]
    F --> G["document(identifier, descriptors)"]
    G --> H["generated-snippets/identifier/*.adoc"]
    H --> I["afterTest(): đóng context"]
    I --> J["Asciidoctor / Markdown trong build, CI"]
~~~

Sơ đồ biểu diễn trách nhiệm và trình tự logic. Bản thân cấu hình client (`MockMvcBuilders...apply(...)`) có thể được xây dựng trong setup ngay sau khi đã mở ngữ cảnh; điều bắt buộc là **ngữ cảnh phải sẵn sàng trước khi tài liệu hóa request**.

**Không đồng nhất các phương thức:** gọi `beforeTest` mà quên `document` thường chỉ có nghĩa bạn đã mở ngữ cảnh nhưng không yêu cầu tạo snippet cho thao tác HTTP nào. Ngược lại, `document` được gọi khi chưa có ngữ cảnh phù hợp có thể thất bại. Cleanup đúng không thay thế cho các assertion HTTP cần thiết.

## 4. Quy tắc ghép cặp: một lần mở, một lần đóng

Hãy coi vòng đời mỗi lần thực thi test như một tài nguyên cần được quản lý:

~~~text
CHƯA MỞ
   |
   | beforeTest(...)
   v
ĐANG MỞ
   |
   | request + assertion + document(...)
   |
   | afterTest()
   v
ĐÃ ĐÓNG
~~~

Điểm kiểm soát quan trọng:

1. **Mở một lần:** gọi `beforeTest(...)` đúng một lần cho lần thực thi test trước khi request tài liệu hóa diễn ra.
2. **Không mở chồng:** không gọi `beforeTest(...)` lần thứ hai với ngữ cảnh trước còn mở. Việc mở lại khi ngữ cảnh chưa được kết thúc có thể gây `IllegalStateException`.
3. **Đóng kể cả khi test thất bại:** cleanup phải nằm trong `finally` hoặc hook teardown bảo đảm được chạy khi assertion ném lỗi.
4. **Không dùng lại ngữ cảnh đã đóng:** test tiếp theo cần `beforeTest(...)` mới trước khi tiếp tục sinh snippet.
5. **Không chia sẻ tùy tiện:** nếu các test chạy song song, cần chiến lược riêng cho trạng thái lifecycle và vị trí đầu ra, tránh các request ghi nhầm ngữ cảnh hoặc cùng file.

### Vì sao finally quan trọng?

Đây là mã dễ mắc lỗi:

~~~java
restDocs.beforeTest(MyCheck.class, "checkBook");

mockMvc.perform(get("/books/{id}", 42L))
        .andExpect(status().isOk());

restDocs.afterTest(); // Không chạy nếu assertion phía trên ném exception.
~~~

Cấu trúc an toàn hơn:

~~~java
restDocs.beforeTest(MyCheck.class, "checkBook");
try {
    mockMvc.perform(get("/books/{id}", 42L))
            .andExpect(status().isOk());
} finally {
    restDocs.afterTest();
}
~~~

Cấu trúc `try/finally` bảo đảm **nỗ lực cleanup** khi thân test kết thúc theo cách thông thường hoặc ném exception/error. Trong chương trình bị dừng đột ngột ở cấp tiến trình, không có cam kết `finally` được thực thi; do đó build cũng cần có cơ chế dọn và tái tạo output đáng tin cậy.

## 5. Ví dụ hoàn chỉnh: TestNG + MockMvc + snippet JSON

Ví dụ sử dụng **TestNG** để minh họa lifecycle không phụ thuộc JUnit. Bộ kiểm thử tạo MockMvc cho một controller đơn giản; mỗi test mở ngữ cảnh ở `@BeforeMethod` và đóng ở `@AfterMethod`.

Điều kiện: dự án có **Java 17+**, Spring MVC Test, Spring REST Docs MockMvc, **TestNG** và Jackson JSON converter. Với Gradle, phải cấu hình `useTestNG()` thay vì chỉ chạy JUnit Platform.

~~~java
import java.lang.reflect.Method;

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

public class BookDocumentationTestNgTest {

    private final ManualRestDocumentation restDocs =
            new ManualRestDocumentation("build/generated-snippets");

    private MockMvc mockMvc;
    private boolean documentationOpen;

    @BeforeMethod
    public void setUp(Method method) {
        restDocs.beforeTest(getClass(), method.getName());
        documentationOpen = true;

        try {
            mockMvc = MockMvcBuilders
                    .standaloneSetup(new BookController())
                    .apply(documentationConfiguration(restDocs))
                    .build();
        } catch (RuntimeException | Error setupError) {
            try {
                closeDocumentation();
            } catch (RuntimeException | Error cleanupError) {
                setupError.addSuppressed(cleanupError);
            }
            throw setupError;
        }
    }

    @Test
    public void getBookCreatesSnippets() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON)
                        .header("X-Trace-Id", "trace-example-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get-success",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã định danh sách")
                        ),
                        requestHeaders(
                                headerWithName("X-Trace-Id")
                                        .description("Mã theo dõi request mẫu")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã định danh sách"),
                                fieldWithPath("title")
                                        .description("Tên sách")
                        )
                ));
    }

    @AfterMethod(alwaysRun = true)
    public void tearDown() {
        closeDocumentation();
    }

    private void closeDocumentation() {
        if (documentationOpen) {
            try {
                restDocs.afterTest();
            } finally {
                documentationOpen = false;
            }
        }
    }

    @RestController
    static class BookController {
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

### Vì sao mở ngữ cảnh ở đầu @BeforeMethod?

Bước `setUp` gọi `beforeTest(...)` **trước** khi tạo MockMvc và áp dụng `documentationConfiguration(restDocs)`. Cách bố trí này rõ ràng: mọi thành phần REST Docs được thiết lập trong phạm vi của test đã mở. Sau đó, method `@Test` mới gửi request và gọi `document(...)`.

### Vì sao có cờ documentationOpen?

Cờ `documentationOpen` giúp phân biệt hai trường hợp:

- `beforeTest(...)` chưa chạy thành công: cleanup không được gọi nhầm trên ngữ cảnh chưa mở.
- `beforeTest(...)` đã thành công: teardown hoặc nhánh bắt lỗi trong setup gọi `afterTest()` đúng một lần.

`@AfterMethod(alwaysRun = true)` hỗ trợ cleanup ngay cả khi assertion trong test thất bại. Nhánh `catch` trong `setUp` bổ sung xử lý cho trường hợp **MockMvc setup lỗi sau khi ngữ cảnh đã mở**, vì không nên chỉ dựa vào việc framework có chạy teardown sau một cấu hình setup thất bại hay không.

Trong ví dụ, `documentationOpen` là field đơn giản vì **giả định các phương thức kiểm thử của cùng instance chạy tuần tự**. Khi bật TestNG parallel mode, thiết kế này cần thay đổi để trạng thái thuộc về từng lần thực thi test; không được dùng chung boolean hoặc đối tượng ManualRestDocumentation một cách thiếu kiểm soát.

### Assertion và snippet được nối thế nào?

Trong test:

- `RestDocumentationRequestBuilders.get(...)` giữ URL template `/api/books/{id}`, cần cho snippet path parameter.
- `.andExpect(...)` xác minh response có status `200`, `id = 42`, và `title = "Spring REST Docs"`.
- `.andDo(document("books-get-success", ...))` ghi snippet HTTP và mô tả path parameter, request header, JSON response fields.

Output thường là:

~~~text
build/generated-snippets/books-get-success/
    http-request.adoc
    http-response.adoc
    curl-request.adoc
    path-parameters.adoc
    request-headers.adoc
    response-fields.adoc
~~~

Tệp và số lượng chính xác còn phụ thuộc cấu hình snippet mặc định. Identifier `books-get-success` quyết định tên thư mục con; `beforeTest(..., "getBookCreatesSnippets")` chỉ cung cấp danh tính test cho ngữ cảnh.

## 6. Dùng try/finally khi không có test framework

Với một bộ kiểm chứng HTTP do ứng dụng tự chạy (không dùng TestNG/JUnit), có thể đóng gói lifecycle trong một hàm:

~~~java
static void runDocumentedCheck(
        ManualRestDocumentation docs,
        String methodName,
        ThrowingCheck check) throws Exception {

    docs.beforeTest(CustomHttpChecks.class, methodName);
    try {
        check.run();
    } finally {
        docs.afterTest();
    }
}

@FunctionalInterface
interface ThrowingCheck {
    void run() throws Exception;
}
~~~

Sử dụng trong mã kiểm chứng:

~~~java
ManualRestDocumentation docs =
        new ManualRestDocumentation("build/generated-snippets");

runDocumentedCheck(docs, "verifyBookResponse", () -> {
    MockMvc mvc = MockMvcBuilders
            .standaloneSetup(new BookController())
            .apply(documentationConfiguration(docs))
            .build();

    mvc.perform(get("/api/books/{id}", 42L))
            .andExpect(status().isOk())
            .andDo(document("books-manual-check"));
});
~~~

Đây là **khung minh họa**: `CustomHttpChecks`, `BookController`, các import và exception cần được đặt trong cùng chương trình kiểm thử thực tế. `get(...)` ở đây nên là request builder từ Spring REST Docs nếu dự định mô tả path parameter.

Khi dùng callback, cách viết này bảo đảm **không có người gọi nào quên `afterTest()`** trong nhánh thực thi chính. Tuy nhiên, một instance `ManualRestDocumentation` vẫn chỉ nên được dùng theo chính sách lifecycle đã chọn; không dùng chung tùy tiện giữa các luồng.

### Nếu cleanup cũng ném lỗi thì sao?

Trong Java, exception từ `finally` có thể che exception gốc của test. Khi cần chẩn đoán đầy đủ, một wrapper có thể ghi nhận lỗi cleanup dưới dạng **suppressed exception** thay vì làm mất stack trace ban đầu. Ví dụ TestNG ở mục 5 đã dùng cách này khi **setup** thất bại. Trong thư viện test helper hoàn chỉnh, cùng nguyên tắc nên áp dụng cho cả phần thực thi test.

Ở mức bài học, quy tắc nền tảng là: **test lỗi vẫn phải thực hiện cleanup**, đồng thời bảo tồn nguyên nhân thất bại chính để dễ điều tra.

## 7. Những thay đổi trạng thái dễ gây lỗi

### 7.1. Gọi beforeTest hai lần mà chưa afterTest

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");

// Chưa afterTest()
restDocs.beforeTest(MyChecks.class, "caseB"); // Sai lifecycle.
~~~

Đối tượng đang có ngữ cảnh mở; lời gọi `beforeTest` tiếp theo có thể ném `IllegalStateException`. Cần kết thúc ca A trước:

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");
try {
    // Kiểm thử A.
} finally {
    restDocs.afterTest();
}

restDocs.beforeTest(MyChecks.class, "caseB");
try {
    // Kiểm thử B.
} finally {
    restDocs.afterTest();
}
~~~

### 7.2. afterTest đặt sau assertion, không có finally

Nếu request hoặc assertion ném exception, đoạn cleanup ở cuối sẽ bị bỏ qua. Chuyển cleanup vào `finally` hoặc `@AfterMethod(alwaysRun = true)` và bảo vệ nhánh setup thất bại như ví dụ trước.

### 7.3. Đóng ngữ cảnh quá sớm

~~~java
restDocs.beforeTest(MyChecks.class, "caseA");
restDocs.afterTest();

// Lúc này mới chạy request và document(...): sai thời điểm.
~~~

Ngữ cảnh phải còn hoạt động khi client HTTP thực hiện thao tác cần tài liệu hóa.

### 7.4. Gọi document mà chưa cấu hình client

Ví dụ với MockMvc, bước sau là bắt buộc:

~~~java
mockMvc = MockMvcBuilders
        .standaloneSetup(new BookController())
        .apply(documentationConfiguration(restDocs))
        .build();
~~~

Nếu tạo một MockMvc khác **không áp dụng** cấu hình REST Docs rồi gọi `document(...)` trên nó, test có thể không ghi được snippet đúng. Chỉ gọi `beforeTest(...)` không tự động cấu hình mọi instance MockMvc.

### 7.5. Cấu hình output nhưng build đọc nhầm nơi

~~~java
new ManualRestDocumentation("build/api-snippets");
~~~

Khi đó Asciidoctor không thể tự đoán rằng snippet nằm ở `build/api-snippets` nếu build vẫn trỏ tới `build/generated-snippets`. Thư mục gốc trong constructor, identifier của `document(...)` và đường dẫn đầu vào của bước dựng tài liệu phải khớp nhau.

## 8. Test chạy nhiều lượt, data provider và song song

Một test method TestNG có thể được thực thi nhiều lần bởi `@DataProvider`, hoặc nhiều method chạy song song. Việc gọi `method.getName()` ở `beforeTest(...)` có thể tạo ra **cùng một tên method** cho nhiều lần thực thi. Điều đó không thay thế việc lựa chọn identifier duy nhất khi sinh snippet.

Ví dụ:

~~~java
// Lượt 1: GET /books/42 -> 200
document("books-get-42-success");

// Lượt 2: GET /books/404 -> 404
document("books-get-404-not-found");
~~~

Các nguyên tắc quan trọng:

| Rủi ro | Hướng xử lý |
| --- | --- |
| Hai lượt dữ liệu dùng cùng `document("books-get")` nhưng body khác | Đặt identifier theo **kịch bản ổn định** hoặc tách test; tránh ghi đè. |
| Test cùng class chạy đồng thời và dùng chung `documentationOpen` | Dùng đối tượng/lifecycle state riêng cho mỗi lần thực thi; không chia sẻ mutable state không được đồng bộ. |
| Hai tiến trình CI ghi vào cùng thư mục và identifier | Tách output theo job/module hoặc điều phối thứ tự ghi. |
| Response phụ thuộc dữ liệu ngẫu nhiên | Cố định fixture, che dữ liệu động bằng preprocessors phù hợp trước khi xuất bản. |
| Test nhiều lượt nhưng chỉ một lượt có assertion | Kiểm chứng từng nhánh HTTP cần tài liệu hóa. |

**Không giả định `ManualRestDocumentation` tự giải quyết bài toán đa luồng cho toàn bộ test suite.** Cần thiết kế rõ chủ sở hữu vòng đời của từng lần chạy, định danh snippet và thư mục output. Một lựa chọn đơn giản khi học là **chạy tuần tự**, tạo bài kiểm thử và identifier tách biệt; sau đó mới mở rộng sang concurrency có kiểm soát.

## 9. Áp dụng với Spring TestContext, WebTestClient và REST Assured

`beforeTest` và `afterTest` là lifecycle chung của **ManualRestDocumentation**, không phụ thuộc client cụ thể. Vì nó là `RestDocumentationContextProvider`, các integration module có thể dùng cùng đối tượng ngữ cảnh:

| Client | Điểm gắn tài liệu | Gợi ý sử dụng |
| --- | --- | --- |
| MockMvc | `MockMvcRestDocumentation.documentationConfiguration(docs)` qua `MockMvcBuilders.apply(...)` | Kiểm thử MVC với controller độc lập hoặc Spring `WebApplicationContext`. |
| WebTestClient | `WebTestClientRestDocumentation.documentationConfiguration(docs)` qua `filter(...)` | Kiểm thử WebFlux hoặc cấu hình WebTestClient tương ứng. |
| REST Assured | `RestAssuredRestDocumentation.documentationConfiguration(docs)` qua filter trong request specification | Kiểm thử endpoint HTTP đang chạy. |

Với TestNG cần Spring ApplicationContext, Spring Test hỗ trợ tích hợp qua `AbstractTestNGSpringContextTests` cùng `@ContextConfiguration`, `@WebAppConfiguration`, hoặc cấu hình phù hợp dự án. Khi đó Spring TestContext chuẩn bị bean; `ManualRestDocumentation` vẫn phải được mở/đóng trong hook thủ công.

Ví dụ rút gọn cho WebTestClient:

~~~java
docs.beforeTest(MyReactiveApiTest.class, "getBook");
try {
    WebTestClient client = WebTestClient.bindToController(controller)
            .configureClient()
            .filter(WebTestClientRestDocumentation
                    .documentationConfiguration(docs))
            .build();

    // client.get() ... exchange() ... expectStatus()
    // ... consumeWith(document("books-webtestclient-get")).
} finally {
    docs.afterTest();
}
~~~

Đây là **khung ý tưởng**, cần instance `controller`, import và dependency `spring-restdocs-webtestclient` phù hợp; cách gọi `document(...)` phía WebTestClient khác MockMvc. Với REST Assured, cấu hình filter `RestAssuredRestDocumentation.documentationConfiguration(docs)` trong request specification, rồi sử dụng filter `document(...)` phù hợp với REST Assured.

Ở cả ba công cụ, quy tắc thời điểm giống nhau: **mở ngữ cảnh → thực hiện request có tài liệu hóa → đóng ngữ cảnh**.

## 10. Output snippet và tích hợp build/CI

Ví dụ tạo `ManualRestDocumentation` với:

~~~java
new ManualRestDocumentation("build/generated-snippets")
~~~

và trong test gọi:

~~~java
document("books-get-success", ...)
~~~

thì thư mục output hợp lý là:

~~~text
build/generated-snippets/books-get-success/
~~~

Đây là mô hình **thư mục gốc** (`build/generated-snippets`) và **thư mục con** theo identifier (`books-get-success`). Đường dẫn tương đối chịu ảnh hưởng working directory của task test, nhất là trong multi-module build.

Ví dụ trang Asciidoctor:

~~~asciidoc
= Books API

== Lấy sách theo mã

=== HTTP request
include::{snippets}/books-get-success/http-request.adoc[]

=== Path parameter
include::{snippets}/books-get-success/path-parameters.adoc[]

=== Request headers
include::{snippets}/books-get-success/request-headers.adoc[]

=== HTTP response
include::{snippets}/books-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/books-get-success/response-fields.adoc[]
~~~

Thuộc tính `{snippets}` phải được cấu hình ở tác vụ Asciidoctor để chỉ đến **thư mục gốc**. Snippet mặc định thường được tạo ở dạng `.adoc`; để xuất Markdown, cần một bước biên soạn/chuyển đổi tương thích.

Ví dụ Gradle Groovy DSL nếu dùng TestNG và plugin Asciidoctor có task `asciidoctor`:

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

Cú pháp `attributes` có thể khác theo phiên bản plugin. Điều cần kiểm chứng là **task test chạy thành công trước**, **snippet tồn tại**, và **bước biên soạn đọc đúng đầu ra**.

Với Maven, thư mục thông dụng là `target/generated-snippets`. Nếu test dùng đường dẫn này, hãy cấu hình plugin dựng tài liệu lấy snippet ở cùng vị trí. Đừng để test xuất vào `build/generated-snippets` trong khi plugin lại mặc định đọc `target/generated-snippets`.

Một quy trình CI có thể thực hiện:

~~~text
1. Build dependencies, chọn đúng TestNG/custom test runner
2. Chạy các bài kiểm thử sinh tài liệu
3. Kiểm tra report: test thực sự được phát hiện và chạy
4. Xác minh generated-snippets/{identifier}/*.adoc
5. Chạy Asciidoctor hoặc pipeline Markdown
6. Đóng gói hoặc xuất bản tài liệu từ artifact được tạo
~~~

Trước khi công bố, kiểm soát dữ liệu mẫu để không đưa token, cookie nhạy cảm, thông tin cá nhân hoặc nội dung phản hồi thật của môi trường production vào snippet.

## 11. Chẩn đoán lỗi theo lifecycle

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `IllegalStateException` khi mở test mới | Lần trước chưa gọi `afterTest()`, hoặc mở chồng ngữ cảnh | Kiểm tra ghép cặp `beforeTest`/`afterTest`, cả nhánh lỗi của setup. |
| `document(...)` báo thiếu ngữ cảnh | Chưa gọi `beforeTest(...)`, hoặc gọi `afterTest()` trước khi request chạy | Đưa `beforeTest` vào setup trước request, dời cleanup về teardown/finally. |
| Test thất bại làm test sau không tạo snippet | Cleanup không chạy khi assertion lỗi | Dùng `finally` hoặc `@AfterMethod(alwaysRun = true)`, xử lý setup thất bại. |
| Test xanh nhưng không có snippet | Thiếu `document(...)` hoặc nhầm MockMvc instance | Kiểm tra chính client đang thực thi và identifier. |
| `pathParameters(...)` không nhận biết biến URL | Dùng request builder không lưu URL template | Sử dụng `RestDocumentationRequestBuilders.get` với path `/api/books/{id}`. |
| Response field descriptors không khớp body | Contract JSON đổi mà mô tả chưa đổi | Đối chiếu assertion, JSON thực tế và descriptors. |
| Có snippet nhưng Asciidoctor báo không tìm thấy | Thuộc tính `snippets`, identifier hoặc task dependency sai | Đối chiếu đường dẫn vật lý, include và thứ tự build. |
| TestNG không tạo file nào | Bộ test không được chạy hoặc chỉ chạy JUnit engine | Kiểm tra `useTestNG()`, cấu hình test runtime và report số test. |
| Hai test chạy song song ghi đè file | Dùng chung identifier/output hoặc state lifecycle mutable | Cô lập execution, đặt tên độc lập và tách output nếu cần. |
| Callback teardown ném lỗi khác với lỗi assertion | Cleanup tự ném exception, làm mất dấu nguyên nhân ban đầu | Bảo toàn exception gốc và thêm lỗi cleanup vào suppressed khi triển khai helper chung. |

Thứ tự điều tra hiệu quả là: **test runner → `beforeTest` → cấu hình client → request/assertion → `document` → `afterTest` → file snippet → build Asciidoctor/Markdown**.

## 12. Bài thực hành kiểm chứng lifecycle

Sử dụng `BookDocumentationTestNgTest` ở mục 5:

1. Chạy test với TestNG, xác minh HTTP `200` và các file `http-request.adoc`, `request-headers.adoc`, `response-fields.adoc`.
2. Tạm thời bỏ `beforeTest(...)` trong setup. Ghi nhận lỗi hoặc sự vắng mặt của ngữ cảnh khi REST Docs được gọi. Khôi phục lệnh.
3. Tạo thêm test thứ hai trong cùng class. Đảm bảo mỗi test mở/đóng ngữ cảnh riêng, không xảy ra lỗi mở chồng.
4. Tạm thay `assertion` để test thất bại. Xác minh teardown vẫn gọi cleanup; sửa assertion về kỳ vọng đúng.
5. Tạo một nhánh cố ý lỗi trong `setUp` **sau** `beforeTest`. Xác minh nhánh catch đóng ngữ cảnh và giữ lỗi setup gốc.
6. Đổi identifier thành `books-get-by-id-success`; kiểm tra thư mục con thay đổi trong khi output dir gốc giữ nguyên.
7. Đổi output dir thành `build/api-snippets`, cập nhật cấu hình Asciidoctor, dựng lại trang tài liệu.
8. Nếu muốn thử parallel TestNG, trước tiên thiết kế lại state và đối tượng lifecycle cho từng execution; chọn identifier duy nhất rồi kiểm tra các file không bị ghi đè.
9. Gắn test và tác vụ biên soạn vào CI, xác minh build thất bại khi assertion lỗi hoặc snippet bắt buộc không có.

**Tiêu chí hoàn thành:** bạn có thể chỉ ra nơi **mở ngữ cảnh**, nơi **đóng ngữ cảnh**, lý do cần `finally`/teardown, client nào được cấu hình REST Docs, thao tác nào tạo snippet và bước build nào sử dụng snippet.

## 13. Tổng kết

- `ManualRestDocumentation` phù hợp khi cần tự quản lý vòng đời REST Docs ngoài JUnit, như TestNG hoặc custom runner.
- `beforeTest(Class<?>, String)` **mở ngữ cảnh theo lần chạy test**; `afterTest()` **kết thúc ngữ cảnh**. Hai lời gọi cần được ghép cặp và cleanup phải được xử lý cả khi test lỗi.
- Ngữ cảnh lifecycle, cấu hình HTTP client và `document(identifier, ...)` là **ba trách nhiệm khác nhau**; thiếu một phần, tài liệu có thể không được sinh đúng.
- Khi chạy test lặp hoặc song song, cần cô lập state và tên identifier để tránh mở chồng ngữ cảnh hoặc ghi đè snippet.
- Snippet từ MockMvc/WebTestClient/REST Assured cần được biên soạn bằng Asciidoctor/Markdown và đưa vào build/CI với đường dẫn và thứ tự tác vụ nhất quán.

