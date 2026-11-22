# Output directory tùy chỉnh cho extension hoặc rule

## 1. Khi nào cần chỉ định output directory?

Spring REST Docs ghi snippet vào một thư mục output. Theo mặc định, thư mục này được suy ra từ build tool: Maven thường dùng **target/generated-snippets** và Gradle thường dùng **build/generated-snippets**. Nếu muốn gom snippet vào một thư mục riêng, lưu theo cấu trúc dự án, dùng thư mục tạm cho một bộ test hoặc tách output giữa các nhóm tài liệu, có thể truyền đường dẫn tùy chỉnh khi tạo extension hoặc rule quản lý vòng đời tài liệu.

Điểm cấu hình nằm ở test framework:

| Test framework | Thành phần quản lý context | Cách đặt output directory |
| --- | --- | --- |
| JUnit Jupiter (JUnit 5/6) | RestDocumentationExtension | Constructor RestDocumentationExtension(String outputDirectory) |
| JUnit 4 | JUnitRestDocumentation rule | Constructor JUnitRestDocumentation(String outputDirectory) |
| TestNG hoặc framework tự quản lý | ManualRestDocumentation | Constructor ManualRestDocumentation(String outputDirectory) |

Output directory là **gốc** mà REST Docs dùng để ghi snippet. Document identifier trong lời gọi document(...) tiếp tục tạo thư mục con bên dưới gốc này. Ví dụ, output directory là build/docs-snippets và identifier là orders/create thì các snippet được ghi dưới build/docs-snippets/orders/create/.

Trong module **SPRING_REST_DOCS**, snippet được sinh từ test HTTP với MockMvc, WebTestClient hoặc REST Assured rồi đưa vào tài liệu Asciidoctor/Markdown và build/CI. Khi đổi output directory, cần cập nhật đường dẫn input của bước biên soạn tài liệu cùng lúc; nếu không, test có thể sinh snippet thành công nhưng Asciidoctor vẫn tìm ở thư mục cũ.

## 2. JUnit Jupiter: tùy chỉnh bằng RestDocumentationExtension

### 2.1. Đăng ký extension bằng field

Với JUnit Jupiter, có thể khai báo extension như một field bằng @RegisterExtension:

~~~java
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.restdocs.RestDocumentationExtension;

class OrderDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/custom-snippets");

    // Test methods
}
~~~

Constructor nhận chuỗi đường dẫn output. Extension quản lý RestDocumentationContext cho mỗi test và cung cấp context cho cấu hình MockMvc, WebTestClient hoặc REST Assured.

Nếu không cần đường dẫn riêng, có thể dùng extension class-level:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class OrderDocumentationTest {
}
~~~

Extension mặc định chọn thư mục dựa trên build tool. Dùng constructor có tham số khi cần chủ động kiểm soát vị trí output.

### 2.2. Cấu hình MockMvc với extension đã đăng ký

Ví dụ đầy đủ:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/custom-snippets");

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
            .apply(documentationConfiguration(documentation))
            .build();
    }

    @Test
    void documentsOrder() throws Exception {
        this.mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andDo(document("orders/get-one"));
    }
}
~~~

Trong BeforeEach, extension được JUnit kích hoạt và inject RestDocumentationContextProvider. documentationConfiguration(documentation) kết nối provider với MockMvc; provider mang theo output directory đã đặt trong constructor. Lệnh document("orders/get-one") tạo thư mục con theo identifier.

Ví dụ giả định controller và dependency cần thiết đã có trong test context. Chi tiết cấu hình mock phụ thuộc ứng dụng; phần trọng tâm là extension và output path.

### 2.3. Cấu hình WebTestClient

Với WebFlux, dùng cùng provider để cấu hình WebTestClient:

~~~java
@BeforeEach
void setUp(
        ApplicationContext applicationContext,
        RestDocumentationContextProvider documentation) {
    this.webTestClient = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .filter(documentationConfiguration(documentation))
        .build();
}
~~~

Khi test thực hiện request và gọi consumeWith(document("orders/get-one")), Spring REST Docs ghi snippet vào output directory mà extension quản lý. Nếu WebTestClient được bind theo controller, router function hoặc server thật, giữ nguyên nguyên tắc: gắn REST Docs filter dùng cùng RestDocumentationContextProvider.

## 3. JUnit 4: tùy chỉnh bằng JUnitRestDocumentation rule

JUnit 4 dùng @Rule với JUnitRestDocumentation. Truyền thư mục riêng vào constructor:

~~~java
import org.junit.Rule;
import org.springframework.restdocs.JUnitRestDocumentation;

public class OrderDocumentationTest {

    @Rule
    public JUnitRestDocumentation restDocumentation =
            new JUnitRestDocumentation("target/custom-snippets");

    // MockMvc tests
}
~~~

Rule quản lý RestDocumentationContext cho mỗi test method. Khi cấu hình MockMvc, truyền rule làm context provider:

~~~java
private MockMvc mockMvc;

@Before
public void setUp() {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(this.restDocumentation))
        .build();
}
~~~

Test có thể ghi snippet:

~~~java
mockMvc.perform(get("/orders/42"))
    .andExpect(status().isOk())
    .andDo(document("orders/get-one"));
~~~

Với constructor new JUnitRestDocumentation("target/custom-snippets"), output sẽ ở:

~~~text
target/custom-snippets/
└── orders/
    └── get-one/
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
~~~

Đây là cơ chế dành cho JUnit 4. Không đặt JUnitRestDocumentation vào test JUnit Jupiter như một rule; JUnit Jupiter dùng RestDocumentationExtension.

## 4. Framework không dùng JUnit extension/rule: ManualRestDocumentation

Spring REST Docs cung cấp ManualRestDocumentation cho trường hợp test framework không hỗ trợ extension/rule tự động, điển hình là TestNG hoặc test lifecycle tự quản lý.

~~~java
import org.springframework.restdocs.ManualRestDocumentation;

public class OrderTest {

    private final ManualRestDocumentation restDocumentation =
            new ManualRestDocumentation("build/custom-snippets");

    @BeforeMethod
    public void beforeMethod(Method method) {
        this.restDocumentation.beforeTest(
                OrderTest.class, method.getName());
    }

    @AfterMethod
    public void afterMethod() {
        this.restDocumentation.afterTest();
    }
}
~~~

Khi cấu hình MockMvc, truyền restDocumentation vào documentationConfiguration(...) như một RestDocumentationContextProvider:

~~~java
this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
    .apply(documentationConfiguration(this.restDocumentation))
    .build();
~~~

Sau đó, trong test:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get-one"));
~~~

Khác với JUnit extension/rule, ManualRestDocumentation cần được thông báo lúc test bắt đầu và kết thúc bằng beforeTest(...), afterTest(). Đảm bảo hook kết thúc được gọi kể cả khi test thất bại; dùng try/finally hoặc cơ chế teardown của framework.

## 5. Output directory kết hợp document identifier

Có hai cấp đường dẫn riêng:

1. **Output directory** chọn thư mục gốc.
2. **Document identifier** chọn thư mục con cho một thao tác HTTP.

Ví dụ:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-reference");

mockMvc.perform(get("/orders/42"))
    .andDo(document("orders/get-one"));

mockMvc.perform(post("/orders"))
    .andDo(document("orders/create"));
~~~

Cấu trúc output:

~~~text
build/api-reference/
└── orders/
    ├── get-one/
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── create/
        ├── http-request.adoc
        └── http-response.adoc
~~~

Không nhúng identifier vào output directory lần thứ hai. Ví dụ đặt extension ở build/api-reference/orders rồi identifier lại là orders/get-one sẽ tạo đường dẫn lặp orders/orders/get-one. Chọn một root ổn định và đặt identifier theo resource/action.

## 6. Dùng identifier có tham số để tách snippet theo test

Spring REST Docs hỗ trợ placeholder trong document identifier:

| Placeholder | Giá trị |
| --- | --- |
| {methodName} | Tên test method nguyên dạng |
| {method-name} | Tên test method theo kebab-case |
| {method_name} | Tên test method theo snake_case |
| {ClassName} | Tên class test nguyên dạng |
| {class-name} | Tên class test theo kebab-case |
| {class_name} | Tên class test theo snake_case |
| {step} | Số thứ tự lần gọi service trong test hiện tại |

Ví dụ:

~~~java
mockMvc.perform(get("/orders/42"))
    .andDo(document("{class-name}/{method-name}"));
~~~

Với class OrderDocumentationTest và method getOrderDetails, thư mục identifier được tạo theo tên chuẩn hóa:

~~~text
order-documentation-test/get-order-details/
~~~

Placeholder hữu ích khi nhiều test method dùng chung cấu hình tài liệu và cần output riêng. Nếu identifier cố định bị tái sử dụng bởi các test khác nhau, snippet cùng tên có thể được ghi vào cùng thư mục và gây ghi đè hoặc khó truy nguyên.

Placeholder {step} hữu ích khi trong cùng một test có nhiều lần gọi service và cần tách snippet cho từng lần. Chỉ dùng khi các lần gọi có ý nghĩa tài liệu độc lập.

## 7. Đồng bộ custom output directory với Asciidoctor

Khi đổi output directory, Asciidoctor phải đọc đúng thư mục mới. Ví dụ extension ghi vào build/api-reference:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/api-reference");
~~~

Gradle Groovy DSL:

~~~groovy
def snippetsDir = file('build/api-reference')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
~~~

Asciidoctor:

~~~adoc
= Orders API

== Lấy chi tiết đơn hàng

include::{snippets}/orders/get-one/http-request.adoc[]
include::{snippets}/orders/get-one/http-response.adoc[]
~~~

Với Maven, cấu hình output của test và plugin tài liệu dùng chung một property, ví dụ thư mục target/api-reference. Dù build tool là gì, custom output directory cần nhất quán ở ba nơi: extension/rule, khai báo output/input của build và snippets attribute của Asciidoctor.

Nếu test dùng extension output build/api-reference nhưng Asciidoctor vẫn trỏ build/generated-snippets, include sẽ báo thiếu tệp. Kiểm tra đường dẫn tuyệt đối hoặc xem cây thư mục sau khi chạy test để xác định nơi snippet thực sự được ghi.

## 8. Đường dẫn tương đối và đường dẫn tuyệt đối

Constructor của extension/rule nhận một chuỗi output directory:

~~~java
new RestDocumentationExtension("build/api-reference");
new JUnitRestDocumentation("target/api-reference");
~~~

Đường dẫn tương đối thuận tiện vì dự án có thể chạy trên máy developer và CI mà không sửa mã nguồn. Dùng đường dẫn tuyệt đối chỉ khi môi trường build có một vị trí cố định được cấu hình rõ ràng; tránh ghi cứng đường dẫn máy cá nhân.

Với dự án multi-module, xác định test đang chạy trong module nào và output directory tương đối được giải quyết từ working directory/project context của test process. Nếu muốn tập trung snippet ở root repository, hãy truyền một đường dẫn được tính từ cấu hình dự án thay vì giả định mọi module có cùng working directory.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Extension vẫn ghi vào generated-snippets mặc định | Dùng extension class-level thay vì instance có constructor path | Đăng ký field bằng @RegisterExtension và truyền output directory |
| JUnit 4 không compile với RestDocumentationExtension | Dùng API JUnit Jupiter trong test JUnit 4 | Dùng JUnitRestDocumentation với @Rule |
| JUnit Jupiter không nhận rule | Dùng @Rule kiểu JUnit 4 | Dùng @RegisterExtension |
| Test sinh snippet đúng nơi nhưng Asciidoctor báo thiếu | Snippets attribute vẫn trỏ thư mục cũ | Đồng bộ attribute và input directory |
| Snippet bị trộn giữa các test | Nhiều test dùng identifier giống nhau | Dùng identifier phân biệt, có thể kết hợp {class-name} và {method-name} |
| Tạo đường dẫn lặp resource | Output root đã chứa resource nhưng identifier lại lặp resource | Giữ output root chung, để identifier tạo thư mục con |
| Test framework không gọi before/after thủ công | Dùng ManualRestDocumentation nhưng thiếu lifecycle hook | Gọi beforeTest và afterTest trong hook của framework |
| Build CI ghi ra thư mục máy developer | Đường dẫn tuyệt đối bị hard-code | Dùng đường dẫn tương đối hoặc property theo môi trường |

## 10. Bài tập thực hành

Tạo test tài liệu hóa endpoint GET /orders/{id} và cấu hình output directory riêng là build/team-api-snippets.

Thực hiện:

1. Với JUnit Jupiter, đăng ký RestDocumentationExtension bằng @RegisterExtension và constructor nhận build/team-api-snippets.
2. Cấu hình MockMvc bằng documentationConfiguration(RestDocumentationContextProvider).
3. Sinh snippet với identifier orders/get-one.
4. Tạo thêm test method dùng identifier {class-name}/{method-name} để quan sát cách tách output.
5. Nếu dự án còn test JUnit 4, cấu hình riêng bằng JUnitRestDocumentation("build/team-api-snippets") và @Rule.
6. Cho Gradle khai báo output/input directory và truyền cùng đường dẫn vào Asciidoctor attribute snippets.
7. Render trang AsciiDoc và xác nhận include đọc từ build/team-api-snippets/orders/get-one/.

**Tiêu chí hoàn thành:** extension hoặc rule ghi snippet vào custom output directory; document identifier tạo đúng thư mục con; Asciidoctor đọc cùng một root; các test không ghi đè snippet của nhau.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RestDocumentationExtension API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/RestDocumentationExtension.html)
- [Spring REST Docs — JUnitRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/JUnitRestDocumentation.html)
- [Spring REST Docs — ManualRestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/ManualRestDocumentation.html)
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/index.html)
