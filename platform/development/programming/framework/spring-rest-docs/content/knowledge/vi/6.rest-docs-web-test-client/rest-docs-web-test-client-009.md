# Document endpoint WebFlux và endpoint MVC tương thích

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Test gửi request và xác nhận response; Spring REST Docs tạo snippet cho request, response, payload, tham số và header; Asciidoctor/Markdown ghép snippet vào quy trình build và CI.

Chương **WebTestClient** tập trung vào client kiểm thử HTTP có fluent API. Tuy nhiên, ứng dụng Spring có thể xử lý request bằng hai nền tảng web khác nhau:

- **Spring WebFlux**: mô hình reactive, thường dùng controller trả về §Mono§/§Flux§ hoặc functional endpoint.
- **Spring MVC**: mô hình Servlet, thường dùng controller đồng bộ trả về DTO/§ResponseEntity§, dù MVC cũng hỗ trợ một số kiểu xử lý bất đồng bộ.

§WebTestClient§ được thiết kế để kiểm thử WebFlux, nhưng Spring còn cung cấp adapter §MockMvcWebTestClient§ để dùng giao diện WebTestClient với Spring MVC. Nhờ adapter này, ta có thể viết request, assertion và REST Docs theo phong cách tương tự cho cả hai nền tảng.

Sau bài học, bạn có thể:

- Phân biệt cách bind WebTestClient trực tiếp với WebFlux và cách bind qua MockMvc cho Spring MVC.
- Chọn §bindToController(...)§ hoặc §bindToApplicationContext(...)§ theo phạm vi kiểm thử.
- Cấu hình Spring REST Docs filter cho cả hai kiểu endpoint.
- Viết test JUnit 5 sinh snippet từ controller reactive và controller MVC.
- Sử dụng §MockMvcWebTestClient.resultActionsFor(...)§ khi cần assertion đặc thù của MockMvc.
- Tránh nhầm adapter kiểm thử MVC với một WebFlux server thật hoặc một kết nối HTTP qua mạng.

## 2. Hai nền tảng web, một giao diện kiểm thử

Điểm chung là test có thể viết theo chuỗi:

~~~java
client.get()
    .uri("/api/greetings")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Xin chào");
~~~

Nhưng đối tượng tiếp nhận request phía sau client khác nhau:

| Nội dung | WebFlux | Spring MVC |
| --- | --- | --- |
| Nền tảng web | Reactive WebFlux | Servlet-based Spring MVC |
| Client bind trực tiếp | §WebTestClient.bindToController(...)§ | §MockMvcWebTestClient.bindToController(...)§ |
| Bind vào Spring context | §WebTestClient.bindToApplicationContext(...)§ | §MockMvcWebTestClient.bindToApplicationContext(...)§ |
| Controller thường gặp | §Mono<T>§, §Flux<T>§ hoặc kiểu phản hồi hỗ trợ khác | DTO, §ResponseEntity<T>§, kiểu phản hồi MVC |
| Hạ tầng được kiểm thử | WebFlux §HttpHandler§ và bean WebFlux trong context | MockMvc và Servlet MVC infrastructure |
| Có mở cổng mạng? | Không, với bind trực tiếp/context | Không, adapter chuyển request vào MockMvc |

~~~mermaid
flowchart TD
    A["Bài test dùng fluent WebTestClient API"] --> B{"Endpoint thuộc nền tảng nào?"}
    B -->|"Spring WebFlux"| C["WebTestClient.bindToController / bindToApplicationContext"]
    B -->|"Spring MVC"| D["MockMvcWebTestClient.bindToController / bindToApplicationContext"]
    C --> E["REST Docs documentationConfiguration filter"]
    D --> E
    E --> F["exchange + expectStatus/header/body"]
    F --> G["consumeWith(document(...))"]
    G --> H["Snippets → Asciidoctor / CI"]
~~~

**Quy tắc chọn API:** dùng §WebTestClient.bindTo...§ cho ứng dụng WebFlux; dùng §MockMvcWebTestClient.bindTo...§ khi endpoint chạy trên Spring MVC. Adapter MVC dùng MockMvc để thực hiện request trong môi trường test, không biến ứng dụng MVC thành WebFlux.

## 3. Dependency và cấu hình theo nền tảng

### 3.1. Dự án WebFlux

Ví dụ dependency Gradle Groovy DSL cho một ứng dụng Spring Boot WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

### 3.2. Dự án Spring MVC

Với ứng dụng MVC, dùng starter web thay cho starter WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-webtestclient'
}
~~~

§spring-boot-starter-test§ cung cấp Spring Test và MockMvc; §spring-restdocs-webtestclient§ cung cấp tích hợp REST Docs dành cho WebTestClient. §MockMvcWebTestClient§ nằm trong Spring Test. Spring Boot thường quản lý phiên bản dependency tương thích.

Đối với dự án không dùng Spring Boot, cần khai báo các module Spring Framework, Spring Test, Spring REST Docs và JUnit 5 tương thích nhau. Không sao chép nguyên phiên bản từ một dự án khác nếu Spring Framework và Spring REST Docs đang lệch phiên bản.

**Lưu ý về ứng dụng có cả hai starter:** nếu cùng đưa §spring-boot-starter-web§ và §spring-boot-starter-webflux§ vào classpath, Spring Boot thường ưu tiên cấu hình MVC khi cả hai cùng hiện diện. Việc một controller trả §Mono§ không tự chứng minh ứng dụng đang chạy trên WebFlux. Hãy xác định web application type và hạ tầng thực tế trước khi chọn API bind. Khi bài test dùng hai cấu hình riêng biệt, nên tách test context để tránh vô tình kiểm thử sai nền tảng.

## 4. Cấu hình REST Docs dùng chung

Với JUnit 5, Spring REST Docs cung cấp §RestDocumentationExtension§ và §RestDocumentationContextProvider§:

~~~java
@ExtendWith(RestDocumentationExtension.class)
class GreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        // Tạo client theo nền tảng web đang kiểm thử.
    }
}
~~~

Sau khi tạo builder đúng loại, gắn filter:

~~~java
.configureClient()
.filter(documentationConfiguration(restDocumentation))
.build();
~~~

Với client được tạo bằng §bindToController(...)§ hoặc §bindToApplicationContext(...)§, §configureClient()§ chuyển từ cấu hình server test sang phần cấu hình client để thêm filter. §documentationConfiguration(...)§ đăng ký xử lý giao dịch HTTP cho Spring REST Docs. Ở mỗi test cần tài liệu hóa, gọi §consumeWith(document("operation-id", ...))§.

Hai import tĩnh chính:

~~~java
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

Lớp test MVC dùng §MockMvcWebTestClient§ để khởi tạo client, nhưng filter REST Docs vẫn được cấu hình theo cơ chế WebTestClient. Điều này cho phép dùng cùng kiểu descriptor như §pathParameters§, §requestFields§, §responseFields§, §requestHeaders§ và §responseHeaders§.

## 5. Ví dụ WebFlux: tài liệu hóa reactive controller

Giả sử endpoint WebFlux §GET /api/greetings§ trả JSON:

~~~json
{
  "message": "Xin chào"
}
~~~

Test hoàn chỉnh:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class WebFluxGreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = WebTestClient.bindToController(new GreetingController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsGreetingEndpoint() {
        client.get()
            .uri("/api/greetings")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào")
            .consumeWith(document("webflux/greetings",
                responseFields(
                    fieldWithPath("message")
                        .description("Lời chào trả về cho client")
                )
            ));
    }

    @RestController
    static class GreetingController {

        @GetMapping(
            path = "/api/greetings",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Mono<Map<String, String>> greeting() {
            return Mono.just(Map.of("message", "Xin chào"));
        }
    }
}
~~~

Ở đây:

1. §WebTestClient.bindToController(...)§ tạo môi trường WebFlux test từ controller được chỉ định.
2. §documentationConfiguration(...)§ đăng ký REST Docs filter trên client.
3. §exchange()§ thực hiện request; status, content type và JSON được xác nhận.
4. §consumeWith(document("webflux/greetings", ...))§ tạo snippet và bảng mô tả field response.

Controller trả về §Mono§, nhưng test chỉ cần kiểm tra response JSON hữu hạn. Nếu endpoint trả Flux hữu hạn được encode thành JSON array, có thể kiểm tra các phần tử bằng JSONPath và mô tả descriptor theo cấu trúc array. Với stream không kết thúc như SSE, cần chiến lược kiểm tra luồng riêng, không chờ gom toàn bộ body chỉ để tạo snippet.

## 6. Ví dụ Spring MVC: dùng MockMvcWebTestClient

Giả sử ứng dụng MVC có controller đồng bộ:

~~~java
@RestController
class MvcGreetingController {

    @GetMapping(
        path = "/api/mvc/greetings",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> greeting() {
        return Map.of("message", "Xin chào từ MVC");
    }
}
~~~

Để kiểm thử controller này bằng fluent WebTestClient API, khởi tạo client từ §MockMvcWebTestClient§:

~~~java
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;

@ExtendWith(RestDocumentationExtension.class)
class MvcGreetingDocumentationTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        this.client = MockMvcWebTestClient
            .bindToController(new MvcGreetingController())
            .configureClient()
            .filter(documentationConfiguration(restDocumentation))
            .build();
    }

    @Test
    void documentsMvcGreetingEndpoint() {
        client.get()
            .uri("/api/mvc/greetings")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("Xin chào từ MVC")
            .consumeWith(document("mvc/greetings",
                responseFields(
                    fieldWithPath("message")
                        .description("Lời chào từ controller Spring MVC")
                )
            ));
    }

    @RestController
    static class MvcGreetingController {

        @GetMapping(
            path = "/api/mvc/greetings",
            produces = MediaType.APPLICATION_JSON_VALUE
        )
        public Map<String, String> greeting() {
            return Map.of("message", "Xin chào từ MVC");
        }
    }
}
~~~

Điểm khác biệt nằm ở dòng khởi tạo:

~~~java
MockMvcWebTestClient.bindToController(new MvcGreetingController())
~~~

Adapter chuyển request của WebTestClient vào MockMvc, nơi Spring MVC xử lý controller và Servlet MVC infrastructure. Các lời gọi §exchange()§, §expectStatus()§, §expectHeader()§, §expectBody()§ và §consumeWith(document(...))§ vẫn quen thuộc.

Không thay dòng trên bằng §WebTestClient.bindToController(...)§ để kiểm tra một MVC controller. Cách bind trực tiếp đó dành cho WebFlux; nó không dựng MockMvc Servlet infrastructure.

## 7. Bind vào ApplicationContext thay vì controller đơn lẻ

Bind trực tiếp controller phù hợp với test tập trung vào endpoint. Khi cần kiểm tra routing, controller advice, converter/codec, filter hoặc các bean khác trong cấu hình web, hãy bind vào Spring context được tạo cho test.

### 7.1. WebFlux ApplicationContext

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(webFluxApplicationContext)
    .configureClient()
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

§webFluxApplicationContext§ phải là context có cấu hình WebFlux và những bean cần kiểm thử.

### 7.2. Spring MVC ApplicationContext

~~~java
WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(mvcWebApplicationContext)
    .configureClient()
    .filter(documentationConfiguration(restDocumentation))
    .build();
~~~

§mvcWebApplicationContext§ phải là WebApplicationContext của Spring MVC. Đối với test Spring Boot MVC, có thể dùng test slice như §@WebMvcTest§ hoặc context integration phù hợp, sau đó inject context để tạo adapter. Với WebFlux, dùng cấu hình test WebFlux tương ứng.

**Không dùng nhầm context:** một ApplicationContext chứa controller không nhất thiết đã có đúng hạ tầng web. Hãy kiểm tra application type, MVC/Flux configuration, bean dependencies và các filter cần có trong test. Test slice cố ý giới hạn bean được nạp; service hoặc repository bị loại khỏi slice phải được cung cấp mock/test bean nếu controller phụ thuộc vào chúng.

## 8. Khi nào cần truy cập MockMvc ResultActions?

Thông thường, assertion của WebTestClient đủ để xác nhận status, header và body. Trong một số test MVC, bạn có thể cần dùng matcher hoặc API đặc thù của MockMvc. §MockMvcWebTestClient§ cung cấp §resultActionsFor(exchangeResult)§ để lấy §ResultActions§ từ kết quả đã nhận.

Ví dụ:

~~~java
import org.springframework.test.web.servlet.ResultActions;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

var exchangeResult = client.get()
    .uri("/api/mvc/greetings")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

ResultActions mvcResult = MockMvcWebTestClient.resultActionsFor(exchangeResult);

mvcResult
    .andExpect(status().isOk())
    .andExpect(handler().handlerType(MvcGreetingController.class));
~~~

Đoạn này giả định §client§ đã được tạo bằng §MockMvcWebTestClient§ và endpoint MVC tồn tại. §resultActionsFor(...)§ dành cho adapter MVC; không dùng cho client WebFlux thông thường. Nó hữu ích khi cần assertion dựa vào chi tiết servlet handler, model hoặc kết quả xử lý MockMvc mà fluent assertion của WebTestClient không biểu đạt trực tiếp.

Đối với phần tài liệu REST Docs, vẫn nên dùng filter §documentationConfiguration(...)§ và callback §document(...)§ trên giao dịch WebTestClient. Không cần chuyển sang MockMvc REST Docs chỉ vì test MVC dùng adapter; hãy chọn một cơ chế tài liệu hóa nhất quán cho từng test.

## 9. Dùng descriptor chung cho WebFlux và MVC

Vì cả hai trường hợp đều sử dụng WebTestClient REST Docs integration, các descriptor thường dùng giữ nguyên:

| Nội dung API | Descriptor |
| --- | --- |
| Path parameter | §pathParameters(parameterWithName("id").description(...))§ |
| Query parameter | API query/request parameter tương ứng với phiên bản REST Docs |
| Request header | §requestHeaders(headerWithName("X-Request-Id").description(...))§ |
| Response header | §responseHeaders(headerWithName("Location").description(...))§ |
| Request JSON field | §requestFields(fieldWithPath("name").description(...))§ |
| Response JSON field | §responseFields(fieldWithPath("message").description(...))§ |

Ví dụ một operation POST có thể dùng chung mẫu descriptor:

~~~java
client.post()
    .uri("/api/greetings")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("name", "Lan"))
    .exchange()
    .expectStatus().isCreated()
    .expectBody()
    .jsonPath("$.message").isEqualTo("Xin chào, Lan")
    .consumeWith(document("greetings/create",
        requestFields(
            fieldWithPath("name").description("Tên người nhận lời chào")
        ),
        responseFields(
            fieldWithPath("message").description("Lời chào được tạo")
        )
    ));
~~~

Đây là đoạn minh họa; endpoint POST phải thực sự được khai báo trong controller/router tương ứng và trả status 201 cùng JSON theo cấu trúc trên. Khi dùng cho WebFlux hoặc MVC, phần khởi tạo client phải theo đúng nền tảng như các mục trước.

Descriptor giúp tài liệu không chỉ là bản sao JSON. Nếu response thêm field bắt buộc chưa mô tả, REST Docs có thể làm test thất bại. Hãy cập nhật descriptor sau khi đánh giá thay đổi hợp đồng; dùng §.optional()§ hoặc §.ignored()§ khi phù hợp với ý nghĩa thực tế của field.

## 10. So sánh bind trực tiếp, bind context và server thật

| Kiểu kiểm thử | API khởi tạo | Hạ tầng được đưa vào test | Khi nên dùng |
| --- | --- | --- | --- |
| WebFlux controller | §WebTestClient.bindToController(...)§ | Controller và hạ tầng WebFlux mô phỏng | Test endpoint reactive có phạm vi hẹp |
| WebFlux context | §WebTestClient.bindToApplicationContext(...)§ | Bean và cấu hình web trong context WebFlux | Kiểm tra routing/filter/advice của WebFlux |
| MVC controller | §MockMvcWebTestClient.bindToController(...)§ | Controller và MockMvc MVC infrastructure | Test endpoint MVC qua fluent WebTestClient API |
| MVC context | §MockMvcWebTestClient.bindToApplicationContext(...)§ | WebApplicationContext và MockMvc setup | Kiểm tra cấu hình MVC và các bean trong context |
| HTTP server thật | §WebTestClient.bindToServer()§ | Kết nối qua mạng tới server đang chạy | Integration test về cổng, proxy hoặc behavior end-to-end qua HTTP |

§MockMvcWebTestClient§ không mở cổng HTTP; request được thực hiện qua MockMvc. Nếu mục tiêu là kiểm tra deployment, port, proxy hoặc server mạng thực tế, hãy dùng client bind tới server đang chạy. Với lựa chọn cuối, việc khởi động/dừng server và base URL phải được quản lý trong test setup.

## 11. Đưa snippet vào Asciidoctor và CI

Trong ví dụ, identifier tách biệt nền tảng để người đọc dễ nhận ra nguồn:

~~~text
build/generated-snippets/
├── webflux/
│   └── greetings/
│       ├── http-request.adoc
│       ├── http-response.adoc
│       └── response-fields.adoc
└── mvc/
    └── greetings/
        ├── http-request.adoc
        ├── http-response.adoc
        └── response-fields.adoc
~~~

Đây là các snippet tiêu biểu; tệp thực tế phụ thuộc loại request/response và descriptor. Một trang Asciidoctor có thể ghép cả hai:

~~~asciidoc
= Greetings API
:snippets: build/generated-snippets

== WebFlux endpoint
include::{snippets}/webflux/greetings/http-request.adoc[]
include::{snippets}/webflux/greetings/http-response.adoc[]
include::{snippets}/webflux/greetings/response-fields.adoc[]

== MVC endpoint
include::{snippets}/mvc/greetings/http-request.adoc[]
include::{snippets}/mvc/greetings/http-response.adoc[]
include::{snippets}/mvc/greetings/response-fields.adoc[]
~~~

Với Gradle (giả sử plugin Asciidoctor và task §asciidoctor§ đã được cấu hình):

~~~groovy
def snippetsDir = layout.buildDirectory.dir("generated-snippets")

tasks.named("test") {
    outputs.dir(snippetsDir)
}

tasks.named("asciidoctor") {
    dependsOn(tasks.named("test"))
    inputs.dir(snippetsDir)
    attributes "snippets": snippetsDir.get().asFile
}
~~~

CI có thể chạy §./gradlew clean test asciidoctor§ sau khi cấu hình đầy đủ task. Cả test WebFlux lẫn MVC phải pass trước khi trang được dựng. Nếu descriptor không khớp payload hoặc assertion status/header/body thất bại, build phải phát hiện lỗi thay vì xuất bản tài liệu cũ như kết quả mới. Markdown thuần cần một bước riêng để chèn hoặc liên kết snippet; cú pháp §include::§ thuộc Asciidoctor.

## 12. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân và cách xử lý |
| --- | --- |
| MVC controller không được map khi dùng §WebTestClient.bindToController(...)§ | Đang dùng sai adapter; dùng §MockMvcWebTestClient.bindToController(...)§ cho Spring MVC. |
| WebFlux controller không hoạt động khi dùng MockMvc adapter | §MockMvcWebTestClient§ dành cho Spring MVC; chuyển sang WebTestClient bind WebFlux. |
| Spring Boot chọn MVC dù có dependency WebFlux | Kiểm tra cả hai starter có cùng trên classpath và cấu hình application type; xác định hạ tầng thật trước khi chọn test. |
| MVC test thiếu bean | Test slice không nạp bean nghiệp vụ; thêm mock/test bean hoặc dùng context rộng hơn theo mục tiêu. |
| Filter/ControllerAdvice không chạy như production | Bind trực tiếp controller không tự nạp toàn bộ cấu hình; cân nhắc bind vào context phù hợp. |
| REST Docs filter không được gọi | Kiểm tra đúng client có §documentationConfiguration(...)§ và request cần tài liệu có §consumeWith(document(...))§. |
| Không có snippet sau khi test MVC pass | Kiểm tra §spring-restdocs-webtestclient§, callback document và thư mục generated snippets. |
| Không dùng được §resultActionsFor(...)§ | Phương thức này dành cho kết quả từ MockMvcWebTestClient; không gọi với WebFlux WebTestClient thông thường. |
| Asciidoctor không tìm thấy snippet | Đối chiếu operation identifier, output directory và dependency task test → asciidoctor. |

## 13. Bài thực hành

1. Chạy §WebFluxGreetingDocumentationTest§, tìm snippet §webflux/greetings§ và đối chiếu JSON với assertion.
2. Chạy §MvcGreetingDocumentationTest§, xác nhận client được tạo bằng §MockMvcWebTestClient§ và snippet nằm dưới §mvc/greetings§.
3. Cố ý thay §MockMvcWebTestClient§ bằng §WebTestClient§ trong test MVC, quan sát sự khác biệt khi dựng môi trường, rồi khôi phục adapter đúng.
4. Chuyển một test MVC từ bind controller sang bind ApplicationContext; bổ sung mock bean cần thiết và quan sát filter/routing có trong context.
5. Dùng §resultActionsFor(exchangeResult)§ để thêm một MockMvc handler assertion cho endpoint MVC.
6. Ghép snippet WebFlux và MVC vào cùng một trang Asciidoctor; cấu hình CI chạy cả hai nhóm test trước khi dựng tài liệu.

## 14. Ghi nhớ

- WebTestClient là giao diện fluent dùng để gửi request và xác nhận response; loại server test phía sau client phải khớp với nền tảng ứng dụng.
- WebFlux dùng §WebTestClient.bindToController(...)§ hoặc §bindToApplicationContext(...)§.
- Spring MVC dùng §MockMvcWebTestClient.bindToController(...)§ hoặc §bindToApplicationContext(...)§ nếu muốn viết test theo WebTestClient API.
- REST Docs WebTestClient filter và các descriptor có thể dùng chung cho cả hai loại endpoint.
- §MockMvcWebTestClient.resultActionsFor(...)§ là cầu nối tới assertion đặc thù MockMvc khi cần; nó không áp dụng cho client WebFlux thông thường.
- Chọn bind controller cho test hẹp, bind ApplicationContext cho cấu hình web rộng hơn và bind server thật khi cần xác nhận HTTP qua mạng.
- Chỉ dựng/publish tài liệu sau khi test của cả hai nền tảng đã chạy thành công trong build/CI.
