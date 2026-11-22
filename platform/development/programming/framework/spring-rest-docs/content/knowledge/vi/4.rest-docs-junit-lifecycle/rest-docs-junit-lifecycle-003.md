# @RegisterExtension và thư mục output tùy chỉnh

## 1. Khi nào cần tự đăng ký RestDocumentationExtension?

Trong module **SPRING_REST_DOCS**, tài liệu REST API được tạo từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Test trước hết xác minh request và response; Spring REST Docs sau đó sinh snippet về HTTP request, HTTP response, payload, tham số, header và các thành phần API liên quan. Snippet được đưa vào Asciidoctor hoặc quy trình biên soạn Markdown, rồi đóng gói trong build và CI.

Ở chương **JUnit và lifecycle**, ta đã biết có thể kích hoạt Spring REST Docs cho JUnit Jupiter bằng annotation:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class BookApiTest {
    // ...
}
~~~

Cách này ngắn gọn khi dùng cấu hình mặc định. Nhưng một số dự án cần **đường dẫn đầu ra cụ thể**, ví dụ:

- Dự án Gradle muốn các snippet nằm dưới `build/generated-snippets`.
- Dự án Maven muốn đặt snippet ở `target/generated-snippets`.
- Pipeline CI cần đọc từ một thư mục xác định để đóng gói hoặc xuất bản tài liệu.
- Một module muốn dùng thư mục riêng để tránh trộn snippet của nhiều nhóm kiểm thử.

Với JUnit 5, có thể dùng **`@RegisterExtension`** để tạo trực tiếp một instance của `RestDocumentationExtension` và truyền đường dẫn output vào constructor:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

**Phân biệt:** `@RegisterExtension` là annotation của **JUnit Jupiter** dùng để đăng ký một extension đã được tạo sẵn; `RestDocumentationExtension` là extension của **Spring REST Docs**. Constructor nhận đường dẫn giúp định cấu hình thư mục output của extension. Annotation này không tự thực hiện request HTTP hoặc sinh tài liệu hoàn chỉnh.

Sau bài học, bạn có thể dùng `@RegisterExtension` đúng cách, kiểm tra thư mục snippet thực tế và đồng bộ đường dẫn giữa test, Asciidoctor và CI.

## 2. @ExtendWith khác gì @RegisterExtension?

Hai cơ chế cùng đăng ký extension với JUnit Jupiter nhưng có cách khởi tạo khác nhau.

| Tiêu chí | `@ExtendWith(RestDocumentationExtension.class)` | `@RegisterExtension` |
| --- | --- | --- |
| Cách đăng ký | Khai báo **lớp** extension | Khai báo **field** chứa đối tượng extension |
| Ai khởi tạo instance? | JUnit | Mã test |
| Truyền tham số constructor tùy chỉnh | Không trực tiếp qua annotation | Có, khi tạo instance |
| Cấu hình thư mục output | Dùng mặc định hoặc cơ chế cấu hình khác | Truyền path qua `new RestDocumentationExtension("...")` |
| Phạm vi đăng ký | Trên class, method hoặc annotation kết hợp theo quy tắc JUnit | Trên field của class test |
| Cách dùng phổ biến | Thiết lập REST Docs tiêu chuẩn | Cần kiểm soát cách tạo/config extension |

Ví dụ so sánh:

~~~java
// Cách A: JUnit tạo extension theo kiểu đã khai báo.
@ExtendWith(RestDocumentationExtension.class)
class DefaultOutputDocumentationTest {
    // ...
}

// Cách B: Test tự tạo extension với đường dẫn đầu ra.
class CustomOutputDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");
}
~~~

Ở cách B, không cần khai báo thêm `@ExtendWith(RestDocumentationExtension.class)` trong cùng lớp chỉ để kích hoạt đúng extension đó. Đăng ký trùng có thể làm cấu hình khó theo dõi. Khi cần Spring context, có thể đăng ký **`SpringExtension` riêng** (qua `@ExtendWith` hoặc annotation Spring Boot), đồng thời dùng `@RegisterExtension` cho phần REST Docs.

### Instance field và static field trong JUnit Jupiter

JUnit Jupiter cho phép đăng ký extension qua field `static` hoặc field instance:

~~~java
// Instance field: dùng cho từng test instance.
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

~~~java
// Static field: instance extension được tạo ở phạm vi class.
@RegisterExtension
static final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("build/generated-snippets");
~~~

Lựa chọn này ảnh hưởng đến **thời điểm extension được đăng ký** trong vòng đời JUnit. Field `static` được đăng ký sớm hơn nên có thể tham gia những callback cấp lớp mà extension hỗ trợ; field instance được đăng ký sau khi tạo test instance. Với trường hợp tài liệu hóa từng HTTP request trong `@BeforeEach` và `@Test`, cách dùng **instance field** giúp code dễ đọc và gắn cấu hình với đối tượng test.

Không nên tự suy ra rằng dùng field `static` sẽ khiến các snippet bị gộp vào một test. REST Docs vẫn gắn thao tác ghi tài liệu với ngữ cảnh của lần thực thi test; vấn đề trùng file chủ yếu đến từ **identifier** trong `document(...)` và vị trí output đã chọn.

## 3. RestDocumentationExtension dùng đường dẫn đầu ra thế nào?

Constructor có dạng:

~~~java
new RestDocumentationExtension("build/generated-snippets")
~~~

Chuỗi truyền vào là **thư mục gốc chứa snippet**. Khi test gọi:

~~~java
document("books-get")
~~~

REST Docs ghi các file được sinh vào thư mục con ứng với identifier, ví dụ:

~~~text
build/
└── generated-snippets/
    └── books-get/
        ├── curl-request.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        ├── httpie-request.adoc
        └── ... (snippet bổ sung do test yêu cầu)
~~~

Tên và số lượng file phụ thuộc vào phiên bản REST Docs, cấu hình snippet mặc định và descriptors được dùng. Nếu test có `pathParameters(...)` hoặc `responseFields(...)`, những thao tác đó tạo thêm snippet mô tả tương ứng.

**Lưu ý về đường dẫn tương đối:** `"build/generated-snippets"` thường được phân giải tương đối theo thư mục làm việc của tiến trình chạy test. Trong multi-module build hoặc khi IDE và CI cấu hình working directory khác nhau, cùng một chuỗi path có thể dẫn đến thư mục thực khác nhau. Hãy xác minh đường dẫn trong môi trường build chính thức, đặc biệt khi chạy từ IDE.

Các nguyên tắc chọn output dir:

1. Đặt thư mục dưới khu vực **sản phẩm sinh ra bởi build** (ví dụ `build/` hoặc `target/`) khi phù hợp với công cụ dự án.
2. Sử dụng cùng một thư mục trong **extension, tác vụ test và công cụ biên soạn tài liệu**.
3. Dùng identifier ổn định, dễ đọc cho mỗi kịch bản; ví dụ `books-get-success`, `books-get-not-found`.
4. Đừng dùng identifier giống nhau cho các kiểm thử có nội dung snippet khác nhau chạy song song.
5. Nếu cần tách loại test, có thể chỉ định các thư mục output khác nhau cho các **nhóm test được cấu hình riêng**, đồng thời cập nhật build để thu thập đúng các nhóm đó.

## 4. Ví dụ hoàn chỉnh: JUnit 5, MockMvc và output tùy chỉnh

Ví dụ sử dụng một controller tối giản, `MockMvc` dạng standalone và `@RegisterExtension` để đưa snippet vào `build/generated-snippets`.

Để chạy trên một dự án Spring Boot có Spring MVC, cần các dependency kiểm thử tương thích như `spring-boot-starter-test` và `spring-restdocs-mockmvc`, đồng thời dự án có hạ tầng Jackson phục vụ JSON. Các ứng dụng thuần Spring Framework phải khai báo thêm các dependency MVC/Test/Jackson/JUnit tương ứng.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
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

class BookDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new BookController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentGetBook() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 7L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Spring REST Docs"))
                .andDo(document("books-get-success",
                        pathParameters(
                                parameterWithName("id")
                                        .description("Mã định danh sách")
                        ),
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã định danh sách"),
                                fieldWithPath("title")
                                        .description("Tên sách")
                        )
                ));
    }

    @RestController
    static class BookController {
        @GetMapping(value = "/api/books/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        BookResponse getBook(@PathVariable("id") Long id) {
            return new BookResponse(id, "Spring REST Docs");
        }
    }

    record BookResponse(Long id, String title) {}
}
~~~

### Phân tích những dòng quan trọng

**`@RegisterExtension`** đăng ký đối tượng `RestDocumentationExtension` đã khởi tạo. Nhờ constructor, test chủ động chọn thư mục output.

**`@BeforeEach setUp(RestDocumentationContextProvider documentation)`** nhận tham số do REST Docs extension hỗ trợ phân giải cho lần test hiện tại. Không cần tự tạo `RestDocumentationContextProvider`.

**`.apply(documentationConfiguration(documentation))`** cấu hình bộ xử lý REST Docs trên chính `MockMvc` sẽ chạy request. Nếu quên bước này, lời gọi `document(...)` không có hạ tầng ghi snippet phù hợp.

**`RestDocumentationRequestBuilders.get`** là import quan trọng. `pathParameters(...)` cần thông tin template URL; dùng builder của REST Docs giúp ghi nhận `"/api/books/{id}"` thay vì chỉ một path đã được thay giá trị.

**`.andExpect(...)`** xác minh response HTTP. **`.andDo(document("books-get-success", ...))`** tạo tài liệu gắn với response đã được kiểm chứng. Các descriptors `pathParameters` và `responseFields` mô tả contract của endpoint.

Nếu test thành công và output dir đúng, hãy tìm:

~~~text
build/generated-snippets/books-get-success/http-request.adoc
build/generated-snippets/books-get-success/http-response.adoc
build/generated-snippets/books-get-success/path-parameters.adoc
build/generated-snippets/books-get-success/response-fields.adoc
~~~

`@RegisterExtension` **không quyết định tên thư mục con** `books-get-success`; tên này đến từ đối số identifier của `document(...)`.

## 5. Phân biệt cấu hình output và cấu hình client

Một lỗi tư duy phổ biến là cho rằng vì đã khởi tạo extension bằng output dir, mọi request MockMvc sẽ tự được tài liệu hóa. Thực tế có ba điểm cấu hình độc lập:

| Điểm cấu hình | Ví dụ | Nó quyết định điều gì? |
| --- | --- | --- |
| Đăng ký extension | `@RegisterExtension` + `new RestDocumentationExtension("build/generated-snippets")` | Vòng đời REST Docs và thư mục đầu ra gốc |
| Cấu hình client | `.apply(documentationConfiguration(documentation))` | Client HTTP nào được REST Docs theo dõi |
| Ghi tài liệu | `.andDo(document("books-get-success", ...))` | Thao tác HTTP nào được ghi, tên snippet và các descriptors |

Một test có thể chạy assertion thành công mà không có snippet nếu thiếu bước ghi tài liệu. Ngược lại, một identifier hợp lệ không cứu được test thiếu cấu hình REST Docs trên client.

Sơ đồ mối quan hệ:

~~~mermaid
flowchart TD
    A["JUnit Jupiter"] --> B["@RegisterExtension"]
    B --> C["RestDocumentationExtension(outputDir)"]
    C --> D["RestDocumentationContextProvider"]
    D --> E["documentationConfiguration(provider)"]
    E --> F["MockMvc/WebTestClient/REST Assured"]
    F --> G["HTTP test + assertions"]
    G --> H["document(identifier, descriptors)"]
    H --> I["outputDir / identifier / *.adoc"]
    I --> J["Asciidoctor/Markdown build"]
    J --> K["Trang tài liệu REST API"]
~~~

Ở đây sơ đồ mô tả **luồng trách nhiệm**, không phải lệnh gọi nội bộ chi tiết cho từng client. Với WebTestClient hoặc REST Assured, cách nối `RestDocumentationContextProvider` vào client khác cú pháp MockMvc, nhưng cùng nguyên tắc: extension quản lý ngữ cảnh, client thực hiện HTTP và `document(...)` tạo snippet.

## 6. Kết hợp @RegisterExtension với SpringExtension

Nếu kiểm thử dùng Spring `WebApplicationContext` để lấy controller và các dependency từ ứng dụng, bạn có thể kết hợp:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestWebConfig.class)
@WebAppConfiguration
class SpringMvcDocumentationTest {

    @RegisterExtension
    final RestDocumentationExtension restDocumentation =
            new RestDocumentationExtension("build/generated-snippets");

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .apply(documentationConfiguration(documentation))
                .build();
    }

    // Test gọi mockMvc.perform(...).andDo(document(...)).
}
~~~

Đây là **khung tích hợp**, cần các import và lớp `TestWebConfig` chứa cấu hình MVC/controller tương ứng. `SpringExtension` chịu trách nhiệm tích hợp JUnit Jupiter với Spring TestContext và injection. `RestDocumentationExtension` vẫn được đăng ký bằng `@RegisterExtension` để cấu hình output dir. Hai phần không thay thế cho nhau.

### Spring Boot và @AutoConfigureRestDocs

Trong một dự án Spring Boot hỗ trợ cấu hình REST Docs tự động, có thể dùng một cách khác:

~~~java
@WebMvcTest(BookController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class BookBootDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    // Test thực hiện request, assertion và document(...).
}
~~~

Đoạn này là **khung cấu hình**: controller và dependency dùng trong slice phải sẵn sàng, và các import tương ứng phải được thêm. Với hướng cấu hình này, Spring Boot tự tích hợp REST Docs vào MockMvc do Boot quản lý. Khi dùng `@AutoConfigureRestDocs`, bạn thường **không cần tạo thêm `RestDocumentationExtension` thủ công** chỉ để chỉ định output dir. Nên chọn một cách cấu hình nhất quán cho client thực tế của test.

**Không trộn hai đường dẫn output một cách tình cờ:** ví dụ test tự tạo `RestDocumentationExtension("build/docs")` nhưng build lại đọc `build/generated-snippets`. Khi đó các snippet có thể đã được sinh nhưng trang tài liệu vẫn báo thiếu file.

## 7. Đưa đường dẫn tùy chỉnh vào Gradle, Maven và CI

Việc chọn output dir ở JUnit mới chỉ hoàn tất **bước sinh snippet**. Tài liệu cuối cùng cần biết nơi đọc snippet và phải được dựng sau khi các bài kiểm thử tương ứng hoàn tất.

### Gradle: sử dụng chung một đường dẫn

Giả sử test đặt:

~~~java
new RestDocumentationExtension("build/generated-snippets")
~~~

Với Gradle Groovy DSL và Asciidoctor JVM plugin, cấu hình minh họa có thể là:

~~~groovy
def snippetsDir = file("build/generated-snippets")

tasks.named("test") {
    useJUnitPlatform()
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    inputs.dir(snippetsDir)
    dependsOn(tasks.named("test"))
    attributes "snippets": snippetsDir
}
~~~

Tên tác vụ/cú pháp có thể cần điều chỉnh theo phiên bản plugin và loại task trong dự án. Điều cốt lõi là `test` ghi vào `snippetsDir`, Asciidoctor dùng cùng thư mục, và tác vụ dựng tài liệu phụ thuộc vào việc chạy test.

Nếu đây là một **Gradle multi-project build**, hãy xác định path tương đối theo working directory của task test trong module thích hợp. Chẳng hạn, nếu snippets nằm ở `module-a/build/generated-snippets`, task Asciidoctor ở module khác phải trỏ đến đúng thư mục thực đó.

### Maven: tương thích với thư mục target

Ở dự án Maven, có thể chọn:

~~~java
@RegisterExtension
final RestDocumentationExtension restDocumentation =
        new RestDocumentationExtension("target/generated-snippets");
~~~

Sau đó cấu hình bước biên soạn tài liệu và resource packaging đọc từ `target/generated-snippets`. Nếu cần dùng một thư mục tùy chỉnh khác, hãy cập nhật cả chỗ khởi tạo extension và cấu hình plugin/tác vụ đọc snippet. Tác vụ biên soạn phải chạy sau giai đoạn test sinh snippet.

### Asciidoctor: include đúng vị trí

Giả sử tệp `books-get-success` đã được sinh, phần Asciidoctor có thể viết:

~~~asciidoc
= Books API

== Lấy thông tin sách

=== Request
include::{snippets}/books-get-success/http-request.adoc[]

=== Path parameters
include::{snippets}/books-get-success/path-parameters.adoc[]

=== Response
include::{snippets}/books-get-success/http-response.adoc[]

=== Response fields
include::{snippets}/books-get-success/response-fields.adoc[]
~~~

Cần khai báo thuộc tính **`snippets`** trong tác vụ Asciidoctor sao cho nó trỏ tới thư mục mà extension đã dùng. `include::{snippets}/...[]` không tự suy ra đường dẫn từ Java test.

Đối với pipeline Markdown, các snippet mặc định của Spring REST Docs thường là file Asciidoctor `.adoc`, nên phải có bước chuyển đổi/nhúng phù hợp trước khi xuất Markdown hoặc trang HTML. Đổi output dir không tự đổi định dạng snippet.

### Quy trình CI tối thiểu

~~~text
1. Checkout và chuẩn bị runtime Java
2. Chạy JUnit Jupiter tests tạo REST Docs snippet
3. Xác minh outputDir/identifier/*.adoc tồn tại
4. Dựng Asciidoctor hoặc pipeline Markdown từ cùng outputDir
5. Đóng gói hoặc xuất bản tài liệu đã tạo
~~~

Nên để CI thất bại nếu test sinh tài liệu thất bại, hoặc nếu bước include yêu cầu một snippet mà không tìm thấy. Dữ liệu minh họa, credential, token và thông tin riêng tư cần được kiểm soát trong các request/response test trước khi đưa vào tài liệu xuất bản.

## 8. Thư mục output tùy chỉnh và kiểm thử chạy song song

Mọi lần gọi `document("identifier", ...)` sử dụng thư mục con theo identifier nằm dưới output dir. Khi nhiều test cùng sử dụng output dir, hãy chú ý:

- **Identifier riêng cho từng kịch bản:** `books-get-success`, `books-get-not-found`, `books-create-invalid`.
- **Không chia sẻ một identifier** giữa hai test đồng thời ghi các response khác nhau; kết quả có thể bị ghi đè hoặc trở nên không ổn định.
- **Không ghi snippet vào thư mục mã nguồn** nếu chúng là sản phẩm build cần tái sinh. Thư mục build thường tiện cho clean/rebuild.
- **Không giả định context Spring và context REST Docs có cùng vòng đời.** Spring có thể cache `ApplicationContext` giữa test; REST Docs gắn snippet với thao tác HTTP của lần chạy đang diễn ra.
- **Đừng thay outputDir tùy tiện giữa IDE, local build và CI.** Nếu cần đổi, nên cấu hình một nguồn giá trị duy nhất hoặc cập nhật các bên tiêu thụ cùng lúc.

Nếu có yêu cầu kiểm thử song song nghiêm ngặt, xem thêm cách cấu hình task isolation, naming và vị trí output của từng bộ test. Chỉ việc thêm `@RegisterExtension` không tạo ra bảo đảm an toàn khi nhiều tiến trình cùng ghi vào một file.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| JUnit không cung cấp được tham số `RestDocumentationContextProvider` | Chưa đăng ký extension, field `@RegisterExtension` không được tạo đúng, hoặc test không chạy bằng JUnit Jupiter | Kiểm tra annotation, constructor, `useJUnitPlatform()` và phiên bản dependency |
| Test qua nhưng không có snippet | Không có `document(...)`, hoặc test đang dùng client khác với client được cấu hình REST Docs | Xác minh `perform(...)`, `documentationConfiguration(...)` và identifier |
| Có snippet nhưng trong thư mục ngoài dự kiến | Đường dẫn tương đối được phân giải từ working directory khác | Kiểm tra working directory thực của process test và đường dẫn vật lý của file |
| Asciidoctor báo không tìm thấy `http-request.adoc` | Thuộc tính `snippets` trỏ sai, identifier sai hoặc chưa chạy test | Đối chiếu thư mục thực, `document(...)` và task dependency |
| Tài liệu cũ còn xuất hiện sau khi đổi đường dẫn | Build đọc một output dir khác hoặc tái sử dụng output không phù hợp | Đồng bộ output dir ở test/build và chạy quy trình clean/rebuild có kiểm soát |
| Hai test ghi đè snippet của nhau | Identifier trùng trong khi nội dung khác nhau | Đặt identifier riêng, cân nhắc phân tách tác vụ khi chạy song song |
| Lỗi `pathParameters(...)` | Dùng builder request không ghi URL template | Dùng `RestDocumentationRequestBuilders` với path dạng `/books/{id}` |
| Test Boot bị cấu hình REST Docs nhiều lần | Kết hợp `@AutoConfigureRestDocs` với setup thủ công không thống nhất | Chọn một chiến lược cho MockMvc thực sự được sử dụng |
| Tài liệu response fields không khớp JSON | Contract API thay đổi mà descriptor chưa cập nhật | Sửa assertion/descriptors đúng với contract cần xuất bản |

Khi chẩn đoán, nên đi theo thứ tự: **JUnit có chạy test không → extension có được đăng ký không → client HTTP có gắn REST Docs không → assertion có thành công không → `document(...)` có được gọi không → snippet được ghi ở đâu → Asciidoctor/CI đang đọc từ đâu**.

## 10. Bài thực hành: chuyển output dir và chứng minh build đọc đúng

Bắt đầu từ `BookDocumentationTest` ở mục 4:

1. Chạy test và kiểm tra `build/generated-snippets/books-get-success/` chứa các file request/response/path parameter/response fields tương ứng.
2. Đổi constructor thành `new RestDocumentationExtension("build/api-reference-snippets")`. Chạy lại test và xác minh file mới xuất hiện tại `build/api-reference-snippets/books-get-success/`.
3. Cập nhật cấu hình Asciidoctor để `{snippets}` trỏ vào `build/api-reference-snippets`. Dựng lại trang tài liệu và kiểm tra include không bị lỗi.
4. Đặt identifier mới `books-get-by-id-success`, chạy lại test và xác minh thư mục con được đổi theo identifier trong khi output dir gốc vẫn như cũ.
5. Thêm một test cho response lỗi (ví dụ `404`) bằng identifier riêng. Viết assertion phù hợp với response thực tế trước khi gọi `document(...)`.
6. Chạy quy trình từ một thư mục sạch trong CI hoặc môi trường build tái lập, xác minh rằng tài liệu chỉ được dựng **sau** khi snippet được sinh.

**Tiêu chí hoàn thành:** người học phân biệt được **thư mục gốc** trong constructor, **thư mục con** từ `document(identifier)` và **đường dẫn đầu vào** của Asciidoctor/Markdown. Khi đổi một trong ba, họ biết điều chỉnh các phần còn lại để build không tham chiếu snippet sai.

## 11. Ghi nhớ

- `@RegisterExtension` cho phép JUnit Jupiter dùng một **đối tượng extension được tạo sẵn**, phù hợp khi cần truyền tham số constructor.
- `new RestDocumentationExtension("...")` đặt **thư mục output gốc** cho snippet; `document("identifier", ...)` đặt **thư mục con** và nội dung tài liệu được sinh.
- Chỉ đăng ký extension chưa đủ: cần cấu hình đúng client MockMvc/WebTestClient/REST Assured và thực hiện `document(...)` sau các bước kiểm chứng HTTP.
- Với Spring TestContext, có thể kết hợp `SpringExtension` và `@RegisterExtension`; với Spring Boot, `@AutoConfigureRestDocs(outputDir = "...")` là lựa chọn khác nếu đang dùng cấu hình tự động.
- Build và CI phải dùng **cùng đường dẫn output**, thực hiện kiểm thử trước, sau đó biên soạn các snippet thành tài liệu Asciidoctor/Markdown.

