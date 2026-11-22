# Chia sẻ snippet configuration giữa các test

## 1. Vì sao cần chia sẻ cấu hình snippet?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Mỗi operation có thể sinh snippet về request, response, payload, parameters, headers và hypermedia links. Các snippet được biên soạn thành Asciidoctor/Markdown rồi đưa vào build, CI.

Trong một module, nhiều documentation test thường cần cùng quy tắc: output directory, template format, request/response preprocessors, default snippets, URI host/port và template overrides. Nếu mỗi test tự cấu hình, snippet dễ khác nhau và khi thay đổi format phải sửa nhiều nơi.

Chia sẻ cấu hình giúp test ngắn gọn, giữ đầu ra nhất quán và giảm công sức bảo trì. Nên chia sẻ quy tắc cấu hình trong helper hoặc test configuration, trong khi mỗi test vẫn tạo operation và descriptor riêng. Không chia sẻ builder hoặc trạng thái mutable giữa các test chạy song song.

## 2. Những thành phần có thể đưa vào cấu hình dùng chung

| Thành phần | Nơi cấu hình | Lý do chia sẻ |
| --- | --- | --- |
| Output directory | RestDocumentationContextProvider hoặc build | Tập trung snippet |
| Template format | SnippetConfigurer.withTemplateFormat(...) | Đồng nhất phần mở rộng và cú pháp |
| Default snippets | withDefaults(...), withAdditionalDefaults(...) | Tự động tạo snippet chung |
| Request preprocessor | OperationPreprocessors | Chuẩn hóa URI/header/body trước khi ghi |
| Response preprocessor | OperationPreprocessors | Pretty-print và làm sạch response |
| Template overrides | Test resources classpath | Dùng cùng Mustache templates |
| Operation attributes | Documentation configuration | Truyền metadata chung khi phù hợp |

Chỉ chia sẻ những quy tắc thực sự giống nhau giữa các test. Một endpoint có response nhạy cảm đặc thù có thể cần preprocessor riêng; endpoint streaming có thể không cần pretty-print body.

## 3. Chia sẻ cấu hình MockMvc bằng helper

Với MockMvc, cấu hình REST Docs được áp dụng thông qua documentationConfiguration(...). Có thể tạo phương thức dùng chung để cấu hình MockMvcConfigurer:

~~~java
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentation;
import org.springframework.restdocs.mockmvc.MockMvcRestDocumentationConfigurer;
import org.springframework.restdocs.templates.TemplateFormats;

final class RestDocsMockMvcConfig {

    private RestDocsMockMvcConfig() {
    }

    static MockMvcRestDocumentationConfigurer restDocs(
            RestDocumentationContextProvider contextProvider) {
        return MockMvcRestDocumentation.documentationConfiguration(contextProvider)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor());
    }
}
~~~

Ví dụ minh họa tập trung format. Kiểu trả về và fluent API cần được xác nhận với phiên bản Spring REST Docs của dự án; nếu cần cấu hình URI defaults, thêm phần uris() theo API phiên bản đó. Nếu không cần URI cố định, giữ URI từ test environment.

Áp dụng trong test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderDocumentationTest {

    @Autowired
    WebApplicationContext context;

    @Autowired
    RestDocumentationContextProvider restDocumentation;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(RestDocsMockMvcConfig.restDocs(restDocumentation))
                .build();
    }
}
~~~

Helper tạo configurer cho test context hiện tại. MockMvc được dựng trong BeforeEach, không lưu builder đã build sẵn dùng chung giữa các test.

## 4. Chia sẻ preprocessors

Preprocessor là phần có giá trị cao để chia sẻ. Ví dụ mọi request/response đều cần JSON dễ đọc và cần loại bỏ một số header có giá trị nhạy cảm:

~~~java
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessRequest;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.preprocessResponse;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.prettyPrint;
import static org.springframework.restdocs.operation.preprocess.Preprocessors.removeHeaders;

final class RestDocsPreprocessors {

    private RestDocsPreprocessors() {
    }

    static OperationRequestPreprocessor cleanRequest() {
        return preprocessRequest(
                prettyPrint(),
                removeHeaders("Authorization", "Cookie"));
    }

    static OperationResponsePreprocessor cleanResponse() {
        return preprocessResponse(
                prettyPrint(),
                removeHeaders("Set-Cookie"));
    }
}
~~~

Tên và import kiểu preprocessor cần khớp phiên bản Spring REST Docs. Với header nhạy cảm, chỉ xóa header khỏi snippet không có nghĩa test bỏ qua xác thực; request vẫn được gửi, preprocessor chỉ thay đổi bản ghi dùng để tài liệu hóa.

Áp dụng preprocessors ở operation:

~~~java
mockMvc.perform(get("/api/orders/{id}", "o-9001"))
        .andExpect(status().isOk())
        .andDo(document("orders-get",
                preprocessRequest(prettyPrint(), removeHeaders("Authorization")),
                preprocessResponse(prettyPrint())));
~~~

Nếu helper đã trả về OperationRequestPreprocessor hoặc OperationResponsePreprocessor, truyền trực tiếp vào overload document tương ứng. Không bọc preprocessRequest(...) lần thứ hai.

## 5. Dùng default snippets thống nhất

Có thể cấu hình những snippet được sinh cho mọi operation. Hai API cần phân biệt:

- withAdditionalDefaults(...) bổ sung snippet vào danh sách mặc định hiện có.
- withDefaults(...) thay thế danh sách mặc định bằng danh sách bạn chỉ định.

Nếu chỉ muốn bổ sung snippet, ưu tiên withAdditionalDefaults(...). Dùng withDefaults(...) khi thực sự muốn kiểm soát toàn bộ danh sách và sẵn sàng khai báo lại những snippet cần giữ.

Ví dụ ý tưởng cấu hình:

~~~java
documentationConfiguration(restDocumentation)
        .snippets()
        .withAdditionalDefaults(new CustomSummarySnippet());
~~~

CustomSummarySnippet là lớp snippet do dự án định nghĩa. Trước khi đưa snippet mặc định vào cấu hình chung, xác nhận mọi operation đều có thể tạo nó. Không phải endpoint nào cũng có body hoặc headers giống nhau.

## 6. Chia sẻ cấu hình WebTestClient

WebTestClient sử dụng documentationConfiguration(...) trong filter. Có thể tạo helper:

~~~java
static WebTestClientConfigurer restDocs(
        RestDocumentationContextProvider contextProvider) {
    return WebTestClientRestDocumentation.documentationConfiguration(contextProvider)
            .snippets()
            .withTemplateFormat(TemplateFormats.asciidoctor());
}
~~~

Kiểu trả về thực tế phụ thuộc API WebTestClient của phiên bản Spring REST Docs. Dùng IDE/compiler để xác nhận kiểu filter/configurer được cung cấp; mục tiêu là tập trung format và snippet configuration vào một helper.

Áp dụng:

~~~java
this.webTestClient = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .filter(WebTestClientRestDocumentation.documentationConfiguration(restDocumentation)
                .snippets()
                .withTemplateFormat(TemplateFormats.asciidoctor()))
        .build();
~~~

Giữ cùng format và quy tắc output giữa MockMvc và WebTestClient nếu chúng tạo tài liệu cho cùng API. Preprocessors có thể khác nhau vì một bên dùng Servlet stack, bên kia dùng Reactive stack.

## 7. Chia sẻ cấu hình REST Assured

REST Assured tích hợp REST Docs thông qua filter. Có thể cung cấp factory tạo filter cho từng test context:

~~~java
static RestDocumentationFilter restDocsFilter(
        RestDocumentationContextProvider contextProvider) {
    return documentationConfiguration(contextProvider)
            .snippets()
            .withTemplateFormat(TemplateFormats.asciidoctor());
}
~~~

Áp dụng trong test:

~~~java
given(this.spec)
        .filter(restDocsFilter(restDocumentation))
        .when()
        .get("/api/orders/o-9001")
        .then()
        .statusCode(200)
        .apply(document("orders-get"));
~~~

REST Assured có kiểu filter riêng so với MockMvc và WebTestClient. Không cố tạo một interface trả về cùng loại filter cho cả ba adapter; chia sẻ quy tắc cấp cao như format, URI, template và metadata, rồi dùng helper adapter-specific để áp dụng.

## 8. Tổ chức helper theo lớp

~~~text
src/test/java/
└── com/example/docs/
    ├── config/
    │   ├── RestDocsMockMvcConfig.java
    │   ├── RestDocsWebTestClientConfig.java
    │   ├── RestDocsRestAssuredConfig.java
    │   └── RestDocsPreprocessors.java
    ├── descriptors/
    │   ├── ApiHeaderDescriptors.java
    │   └── OrderFieldDescriptors.java
    └── tests/
        ├── OrderDocumentationTest.java
        └── CustomerDocumentationTest.java
~~~

Phân tách theo trách nhiệm:

- config: cách adapter tạo operation và ghi snippet.
- preprocessors: chuẩn hóa hoặc làm sạch request/response trước khi ghi.
- descriptors: mô tả hợp đồng API có thể tái sử dụng.
- tests: dữ liệu fixture, HTTP assertions và operation-specific documentation.

Tránh đưa mọi thứ vào một BaseDocumentationTest lớn với nhiều hook khó theo dõi. Helper nhỏ, tên rõ ràng thường dễ hiểu hơn kế thừa nhiều tầng.

## 9. Dùng JUnit setup để giảm lặp

Với JUnit Jupiter, BeforeEach phù hợp để tạo MockMvc từ context hiện tại. Nếu nhiều test class dùng cùng cấu hình, có thể dùng base class nhỏ:

~~~java
abstract class AbstractRestDocsMockMvcTest {

    @Autowired
    protected WebApplicationContext context;

    @Autowired
    protected RestDocumentationContextProvider restDocumentation;

    protected MockMvc mockMvc;

    @BeforeEach
    void configureMockMvc() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(RestDocsMockMvcConfig.restDocs(restDocumentation))
                .build();
    }
}
~~~

Test cụ thể kế thừa khi thực sự có chung lifecycle và cấu hình:

~~~java
class OrderDocumentationTest extends AbstractRestDocsMockMvcTest {

    @Test
    void getOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-9001"))
                .andExpect(status().isOk())
                .andDo(document("orders-get"));
    }
}
~~~

Nếu các test cần security, standalone setup, controller advice hoặc message converter khác nhau, dùng composition/helper thay vì ép tất cả vào một base class.

## 10. Tránh chia sẻ mutable state giữa các test

Chia sẻ factory/configuration là tốt; chia sẻ builder đã thay đổi trạng thái có thể gây lỗi khó tìm:

- Không tái sử dụng MockMvcBuilder rồi thêm filter/configurer theo từng test.
- Không giữ danh sách mutable descriptor rồi sửa nội dung sau khi test bắt đầu.
- Không dùng cùng operation identifier cho nhiều test tạo snippet khác nhau, trừ khi chủ ý ghi lại cùng operation.
- Không để test phụ thuộc thứ tự chạy để đọc snippet do test khác sinh.
- Không dùng output directory chung giữa các build song song nếu có thể ghi đè lẫn nhau.

Factory nên trả về cấu hình mới cho test context; descriptor nên được tạo mới khi cần trạng thái khác nhau. Mỗi operation nên có identifier ổn định, duy nhất trong output của build.

## 11. Cấu hình URI và output directory

REST Docs có thể cấu hình URI mặc định để snippet hiển thị host/scheme phù hợp tài liệu công khai:

~~~java
documentationConfiguration(restDocumentation)
        .uris()
        .withScheme("https")
        .withHost("api.example.test")
        .withPort(443);
~~~

Không đưa host nội bộ hoặc địa chỉ staging vào snippet nếu tài liệu hướng tới người dùng bên ngoài. Nếu endpoint dùng nhiều base URL hoặc version, cấu hình ở operation phù hợp.

Output directory thường được cung cấp qua RestDocumentationContextProvider và cấu hình build. Giữ một quy ước output thống nhất:

~~~text
build/
└── generated-snippets/
    ├── orders-get/
    ├── orders-create/
    └── customers-update/
~~~

Không hard-code output directory khác nhau trong từng test. Để plugin/build script quản lý thư mục sinh snippet, còn test tập trung vào operation và descriptors.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Snippet giữa các test có format khác nhau | Cấu hình format bị lặp và không đồng nhất | Dùng helper config chung cho adapter |
| Một số snippet thiếu HTTP request/response | Default snippets không được cấu hình giống nhau | Kiểm tra withDefaults/withAdditionalDefaults |
| Header nhạy cảm xuất hiện trong output | Preprocessor không được áp dụng cho operation | Đưa preprocessor vào helper và xác minh file sinh ra |
| MockMvc và WebTestClient có output khác | Mỗi adapter dùng format/preprocessor riêng | Chia sẻ quy tắc cấp cao và cấu hình adapter tương ứng |
| Test chạy song song ghi đè snippet | Operation identifier trùng hoặc output dùng chung | Đặt identifier duy nhất và cô lập output theo build |
| Base class khó mở rộng | Nhồi nhiều setup đặc thù vào lớp cha | Tách helper composition theo adapter |
| URI trong snippet trỏ host sai | URI defaults đặt ở cấu hình không phù hợp | Xem lại scheme/host/port và môi trường tài liệu |
| Build không tìm thấy snippet | Task biên soạn chạy trước test tạo snippet | Khai báo dependency task đúng thứ tự |

## 13. Bài thực hành

1. Tạo RestDocsMockMvcConfig để tập trung template format và URI defaults.
2. Tạo RestDocsPreprocessors dùng chung để pretty-print JSON và làm sạch Authorization/Cookie khỏi bản ghi.
3. Dùng helper trong hai documentation tests; so sánh cấu trúc snippet.
4. Bổ sung default snippets mà không làm mất những snippet mặc định đang dùng.
5. Tạo helper riêng cho WebTestClient hoặc REST Assured và thống nhất format.
6. Chuyển một test có cấu hình riêng sang helper dùng chung; giữ nguyên assertions và operation identifier.
7. Chạy test song song để xác nhận output không bị ghi đè do identifier trùng.

**Tiêu chí hoàn thành:** biết phần nào nên chia sẻ; tạo helper config cho adapter; tái sử dụng preprocessors và template format; giữ descriptor/operation riêng; tránh mutable state; build tạo snippet trước khi biên soạn.

## 14. Checklist trước khi commit

- [ ] Template format và output directory được cấu hình nhất quán.
- [ ] MockMvc/WebTestClient/REST Assured có helper adapter-specific phù hợp.
- [ ] Preprocessors chung được áp dụng cho đúng operation.
- [ ] Header nhạy cảm và cookie session được làm sạch trước khi ghi snippet.
- [ ] Default snippets được bổ sung mà không vô tình thay thế danh sách hiện có.
- [ ] Helper trả về config mới, không chia sẻ builder mutable giữa test.
- [ ] Operation identifiers không xung đột.
- [ ] Descriptor và assertions riêng vẫn nằm trong test phù hợp.
- [ ] Task sinh snippet chạy trước task Asciidoctor/Markdown.
- [ ] CI tạo tài liệu từ output của lần chạy test hiện tại.

**Ghi nhớ:** Chia sẻ snippet configuration bằng helper theo adapter và các quy tắc dùng chung như template format, preprocessors, URI defaults và output convention. Mỗi test vẫn giữ operation, assertions và descriptors riêng; cách tổ chức này giảm lặp mà không làm các test phụ thuộc trạng thái mutable hoặc thứ tự chạy.
