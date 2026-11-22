# Khác biệt hành vi giữa MockMvc và WebTestClient

## 1. Mục tiêu bài học

Trong module **SPRING_REST_DOCS**, ta tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP với MockMvc, WebTestClient hoặc REST Assured. Test gửi request, xác nhận response và Spring REST Docs sinh snippet cho request, response, payload, tham số và header. Các snippet được biên soạn bằng Asciidoctor/Markdown rồi đưa vào quy trình build và CI.

MockMvc và WebTestClient đều có thể kiểm thử Spring MVC, nhưng chúng mô phỏng request theo hai mô hình khác nhau. MockMvc gọi trực tiếp Spring MVC qua Servlet API mô phỏng; WebTestClient dùng API client reactive và có thể bind vào ứng dụng trong bộ nhớ hoặc gửi request qua HTTP tới server đang chạy. Vì thế, cùng một endpoint có thể có khác biệt về cách khởi tạo, async handling, filter, codec, URI và cách quan sát response.

Bài học này giúp chẩn đoán khác biệt giữa hai công cụ và chọn đúng cấu hình cho Spring REST Docs. Sau bài, bạn có thể:

- Phân biệt execution model của MockMvc và WebTestClient.
- Chọn binding mode phù hợp với Spring MVC, WebFlux hoặc server thật.
- Hiểu những khác biệt về Servlet filters, WebFilters, message converters và codecs.
- Xử lý async response và reactive publisher đúng cách.
- Cấu hình REST Docs cho cả hai client và so sánh snippet tương ứng.
- Chẩn đoán khi status, header, body hoặc URI khác nhau giữa hai test.

## 2. Khác biệt cốt lõi về execution model

### 2.1. MockMvc

MockMvc kiểm thử ứng dụng Spring MVC mà không khởi động HTTP server thật. Nó dựng Servlet request/response mô phỏng và gọi Spring MVC infrastructure trong test process.

~~~java
mockMvc.perform(get("/api/orders/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42));
~~~

MockMvc phù hợp để kiểm tra controller mapping, argument binding, validation, exception handling, response serialization, Servlet filters và Spring MVC interceptors trong cấu hình test. MockMvc không kiểm tra TCP connection, reverse proxy, TLS termination hoặc cấu hình network của server triển khai thật.

### 2.2. WebTestClient

WebTestClient cung cấp fluent API kiểu WebClient để gửi request và kiểm tra response. Nó có nhiều cách binding:

- bindToController(...): dựng WebFlux hoặc cấu hình controller trong bộ nhớ.
- bindToApplicationContext(...): bind vào application context.
- bindToRouterFunction(...): bind trực tiếp vào WebFlux RouterFunction.
- bindToServer(): gửi HTTP tới server đang chạy.
- bindToServer().baseUrl(...): cấu hình địa chỉ server thật.

Ví dụ binding vào controller:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(orderService))
    .build();

client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(42);
~~~

WebTestClient không đồng nghĩa với WebFlux. Nó cũng có thể kiểm thử Spring MVC qua mock server adapter hoặc gửi request HTTP tới một server Servlet đang chạy. Hãy xem binding mode cụ thể trước khi kết luận test đang kiểm tra stack nào.

## 3. Bảng so sánh nhanh

| Khía cạnh | MockMvc | WebTestClient |
| --- | --- | --- |
| API kiểm thử | Servlet MVC test API | Fluent client API, dựa trên WebClient |
| Gọi ứng dụng | Trực tiếp qua mock Servlet infrastructure | In-memory binding hoặc HTTP server thật |
| Spring MVC | Hỗ trợ trực tiếp | Có thể kiểm thử qua mock server adapter hoặc server thật |
| Spring WebFlux | Không phải công cụ dành cho WebFlux | Hỗ trợ tự nhiên |
| HTTP server/network | Không khởi động server/network thật | Chỉ có khi bindToServer hoặc dùng server thật |
| Async/reactive | Hỗ trợ Servlet async theo cơ chế MockMvc | Hỗ trợ reactive response và publisher assertions |
| Request body | Servlet request builder | Body inserter và client API |
| Response body | MockMvc result matchers | expectBody, returnResult và WebTestClient matchers |
| REST Docs | MockMvcRestDocumentation | WebTestClientRestDocumentation |
| Phù hợp | Ứng dụng Spring MVC cần test nhanh ở tầng MVC | WebFlux, API fluent dùng chung, hoặc test qua HTTP thật |

Không chọn công cụ chỉ dựa vào cú pháp. Chọn theo lớp cần kiểm chứng: controller/MVC behavior, reactive pipeline hay HTTP server và network boundary.

## 4. Chọn đúng WebTestClient binding mode

### 4.1. bindToController

Binding này tạo client gắn với controller và các thành phần WebFlux được cấu hình cho test:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .build();
~~~

Phù hợp với test nhỏ, cô lập controller. Nếu controller phụ thuộc service, validator, converter hoặc exception advice, cần cung cấp các thành phần liên quan hoặc dùng application context để test cấu hình đầy đủ hơn.

### 4.2. bindToApplicationContext

Binding vào context giúp dùng cấu hình Spring Web đã được nạp:

~~~java
@Autowired
WebApplicationContext context;

WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

Đoạn trên sử dụng MockMvcWebTestClient của Spring Test để dùng WebTestClient API với Spring MVC mock infrastructure. Nó vẫn không khởi động server thật.

Với WebFlux application context, dùng WebTestClient bind theo WebFlux test setup tương ứng:

~~~java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .build();
~~~

Kiểu context và cấu hình phải tương ứng với stack ứng dụng. Không dùng ví dụ WebApplicationContext Servlet cho WebFlux reactive context.

### 4.3. bindToServer

Khi cần kiểm tra HTTP server thật:

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080")
    .build();
~~~

Client gửi request qua HTTP tới server. Cách này có thể kiểm tra embedded server, Servlet/WebFlux runtime, network stack cục bộ và một số filter/container configuration thực tế. Nó cũng làm test phụ thuộc vào server lifecycle, port và thời gian khởi động.

Nếu cần kiểm tra TLS, reverse proxy hoặc gateway, test phải chạy qua đúng boundary đó; bindToServer localhost không tự kiểm chứng proxy production.

## 5. Vì sao cùng endpoint có thể cho kết quả khác?

Hai test có thể khác nhau vì chúng không chạy qua cùng pipeline:

~~~mermaid
flowchart TD
    A["Test request"] --> B{"Client / binding"}
    B --> C["MockMvc"]
    B --> D["WebTestClient in-memory"]
    B --> E["WebTestClient HTTP server"]
    C --> F["Mock Servlet request"]
    D --> G["Mock WebHandler / MVC adapter"]
    E --> H["HTTP connector + server runtime"]
    F --> I["Controller / MVC pipeline"]
    G --> I
    H --> I
    I --> J["Response"]
~~~

Những thành phần có thể tạo khác biệt:

- Servlet filters và Servlet container behavior.
- WebFlux WebFilters và reactive handler chain.
- MVC HttpMessageConverter so với WebFlux HttpMessageReader/HttpMessageWriter.
- Content negotiation và default media type.
- Async dispatch, deferred result và reactive publisher completion.
- Context path, servlet path, base URL và proxy forwarding headers.
- Security configuration và thứ tự filter.
- Exception resolver/advice được load trong test slice hay full context.

Khi kết quả khác nhau, xác định khác biệt xuất hiện ở layer nào trước khi sửa assertion hoặc tài liệu.

## 6. Khác biệt giữa Servlet filters và WebFilters

Spring MVC thường dùng Servlet Filter, HandlerInterceptor và Spring Security filter chain. WebFlux dùng WebFilter và reactive security chain. Một filter được đăng ký trong Servlet container không tự động chạy trong WebFlux pipeline.

Ví dụ:

- MockMvc test có thể đi qua Servlet filter nếu test setup đăng ký filter đó.
- WebTestClient bind vào WebFlux context đi qua WebFilter.
- WebTestClient bindToServer đi qua filter/handler chain của server đang chạy.

Nếu header X-Request-Id xuất hiện trong response của MockMvc nhưng thiếu trong WebTestClient, kiểm tra nơi tạo header: Servlet filter, WebFilter, controller advice hay gateway.

Không thêm header thủ công trong test chỉ để làm snippet giống nhau nếu ứng dụng thật không bảo đảm header đó. Hãy quyết định header thuộc hợp đồng của API hay chỉ là chi tiết môi trường.

## 7. Message converters và codecs

Spring MVC dùng HttpMessageConverter để đọc request body và ghi response body. WebFlux dùng codecs (HttpMessageReader/HttpMessageWriter) theo reactive stack.

Các cấu hình có thể khác nhau:

- Jackson ObjectMapper và module đăng ký.
- Java time serialization và date format.
- Naming strategy hoặc property inclusion.
- Content-Type và Accept negotiation.
- Cách xử lý empty body, null và streaming media type.

Ví dụ một response ngày tháng có thể khác format nếu hai application context dùng ObjectMapper cấu hình khác nhau. Trước khi thay snippet, so sánh cấu hình converter/codec thực tế.

Kiểm tra response content type:

~~~java
// MockMvc
mockMvc.perform(get("/api/orders/42"))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON));
~~~

~~~java
// WebTestClient
client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
~~~

Nếu body khác nhưng status giống nhau, hãy so sánh raw response, content type và serialization config trước khi kiểm tra REST Docs.

## 8. Async và reactive response

### 8.1. Servlet async với MockMvc

Spring MVC có thể trả kết quả bất đồng bộ qua Callable, DeferredResult hoặc WebAsyncTask. MockMvc có cơ chế async dispatch:

~~~java
MvcResult result = mockMvc.perform(get("/api/report"))
    .andExpect(request().asyncStarted())
    .andReturn();

mockMvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andDo(document("reports/get"));
~~~

Nếu document operation trước khi async dispatch hoàn tất, snippet có thể không đại diện cho response cuối cùng. Hãy chờ async result và thực hiện dispatch theo đúng quy trình.

### 8.2. Reactive response với WebTestClient

WebTestClient đợi exchange và có thể kiểm tra body theo publisher:

~~~java
client.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(OrderResponse.class)
    .hasSize(2);
~~~

Với streaming endpoint như Server-Sent Events hoặc Flux dài vô hạn, không collect toàn bộ body vô hạn. Chọn test giới hạn số phần tử, timeout và kiểm tra media type/stream events phù hợp.

### 8.3. Đừng nhầm async với reactive

Servlet async vẫn chạy trên Servlet MVC; reactive publisher không tự biến endpoint thành WebFlux. Xác định return type, dispatcher và runtime của controller trước khi chọn cách test.

## 9. Request URI, context path và base URL

MockMvc request thường mô phỏng path nội bộ:

~~~java
mockMvc.perform(get("/api/orders/42")
        .contextPath("/store"))
    .andExpect(status().isOk());
~~~

WebTestClient server binding dùng địa chỉ server:

~~~java
WebTestClient client = WebTestClient
    .bindToServer()
    .baseUrl("http://localhost:8080/store")
    .build();
~~~

Đừng thêm cùng prefix ở cả baseUrl và URI nếu kết quả sẽ thành /store/store/api/orders. Phân biệt:

- Public base URL: scheme, host, port và prefix client dùng.
- Context path: gốc web application trong Servlet container.
- Servlet path: path được ánh xạ tới servlet.
- Endpoint path: path mapping của controller/router.

Để snippet nhất quán, cấu hình URI documentation của REST Docs riêng với URI mà test client thực sự gửi. Không dùng documented URI modifier để sửa request routing của test.

## 10. Cấu hình Spring REST Docs cho MockMvc

Dùng MockMvcRestDocumentation.documentationConfiguration(...) trong MockMvc builder:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.mockMvc = MockMvcBuilders.webAppContextSetup(this.context)
        .apply(documentationConfiguration(restDocumentation))
        .build();
}
~~~

Document operation:

~~~java
mockMvc.perform(get("/api/orders/{id}", 42))
    .andExpect(status().isOk())
    .andDo(document("orders/get"));
~~~

Spring REST Docs ghi snippet dựa trên mock request/response mà MockMvc tạo. Cấu hình host/scheme/port documented bằng URI configurer nếu cần:

~~~java
documentationConfiguration(restDocumentation).uris()
    .withScheme("https")
    .withHost("api.example.com")
    .withPort(443);
~~~

## 11. Cấu hình Spring REST Docs cho WebTestClient

Dùng WebTestClientRestDocumentation.documentationConfiguration(...):

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.webTestClient = WebTestClient
        .bindToApplicationContext(this.applicationContext)
        .configureClient()
        .filter(documentationConfiguration(restDocumentation))
        .build();
}
~~~

Import tĩnh và class cần dùng:

~~~java
import org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation;
import org.springframework.restdocs.RestDocumentationContextProvider;

import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.documentationConfiguration;
~~~

Sau đó document operation:

~~~java
webTestClient.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("orders/get"));
~~~

Tên API và overload có thể khác theo phiên bản Spring REST Docs; dùng dependency version của dự án làm căn cứ. Điểm quan trọng là áp dụng WebTestClient REST Docs filter cho client trước khi gọi exchange và gắn document vào response operation.

## 12. MockMvcWebTestClient: dùng WebTestClient API với Spring MVC

Spring Test có MockMvcWebTestClient cho phép dùng fluent WebTestClient API để kiểm thử Spring MVC bằng MockMvc infrastructure:

~~~java
WebTestClient client = MockMvcWebTestClient
    .bindToApplicationContext(context)
    .build();
~~~

Sau khi exchange, có thể lấy MvcResult nếu cần assertion ở tầng Servlet:

~~~java
EntityExchangeResult<byte[]> result = client.get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .returnResult();

MockMvcWebTestClient.resultActionsFor(result)
    .andExpect(handler().handlerType(OrderController.class));
~~~

Đây là cầu nối hữu ích khi muốn fluent client assertions nhưng vẫn cần kiểm tra MVC handler details. Nó không biến ứng dụng thành WebFlux và không tạo HTTP server thật.

Khi kết hợp Spring REST Docs, chọn integration tương ứng với client/API đang dùng và kiểm tra snippet output. Không áp dụng đồng thời hai REST Docs filter cho cùng một operation.

## 13. So sánh snippet từ hai client

Khi cùng document một endpoint bằng MockMvc và WebTestClient, có thể dùng cùng operation identifier trong hai test suite riêng, nhưng cần tránh ghi đè snippet đồng thời hoặc tạo output không xác định.

Nên so sánh:

| Snippet | Điều cần đối chiếu |
| --- | --- |
| http-request | Method, URI, query parameters, headers và body. |
| http-response | Status, headers, media type và body. |
| request-fields | Field path, type, optional/ignored và description. |
| response-fields | Schema JSON, nullability và nested paths. |
| path-parameters | Tên parameter, vị trí và mô tả. |
| response-headers | Header thực tế và ý nghĩa hợp đồng. |

Nếu hai test mô phỏng cùng một public contract, khác biệt trong snippet thường là tín hiệu cần điều tra. Tuy nhiên, không bắt buộc mọi byte snippet phải giống nhau: request host, port, header runtime hoặc formatting có thể khác do binding mode.

## 14. Bảng chẩn đoán khác biệt thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| MockMvc trả 200, WebTestClient trả 404 | URI/base path, context path hoặc router mapping khác | In request URI; xác nhận binding mode và controller mapping. |
| MockMvc có security header, WebTestClient không có | Servlet Filter và WebFilter khác nhau hoặc filter chưa đăng ký trong test | Xác định component tạo header và kiểm tra security chain của từng stack. |
| Body JSON khác format | ObjectMapper/converter/codec config khác | So sánh application context, converter và codec customizers. |
| MockMvc test async timeout | Chưa dispatch async result hoặc timeout cấu hình quá ngắn | Dùng asyncStarted, asyncDispatch và cấu hình timeout hợp lý. |
| WebTestClient body rỗng | Publisher chưa emit, handler trả empty hoặc test chọn sai body extractor | Kiểm tra status, content type, publisher và expectBody/expectBodyList. |
| Snippet URI có prefix lặp | Prefix đặt cả trong baseUrl và request URI | Tách public base URL, context path và endpoint path. |
| Response header chỉ khác trong bindToServer | Server filter/container/gateway thêm hoặc loại header | So sánh in-memory binding với HTTP server thật. |
| Exception body khác nhau | Advice không được load hoặc handler khác nhau giữa context | Kiểm tra @ControllerAdvice scan/import và exception type. |
| REST Docs snippet không được sinh | Filter/documentationConfiguration chưa gắn hoặc document consumer không được gọi | Kiểm tra client setup, exchange chain và output directory. |
| Test chạy riêng pass nhưng chạy suite fail | Shared state, port, generated snippets hoặc test order | Dùng context/test isolation và operation identifiers duy nhất. |

## 15. Quy trình điều tra có hệ thống

Khi hai client cho kết quả khác nhau, đi theo thứ tự:

1. **Xác nhận runtime:** ứng dụng là Spring MVC hay WebFlux? WebTestClient đang bind in-memory hay HTTP server?
2. **So sánh request:** method, URI, context path, headers, content type và body có giống nhau không?
3. **So sánh pipeline:** Servlet filters, WebFilters, interceptors, security chain và exception advice nào được chạy?
4. **So sánh serialization:** converters/codecs, ObjectMapper và content negotiation có giống nhau không?
5. **Kiểm tra async:** response đã hoàn tất chưa, publisher đã emit/complete chưa?
6. **Đọc response gốc:** status, headers và body trước khi REST Docs preprocessing.
7. **Đọc snippets:** xác nhận REST Docs filter đã áp dụng đúng và không có operation ghi đè.
8. **Chọn đúng test boundary:** mock test cho controller contract, server-bound test cho HTTP runtime, external integration test cho proxy/gateway.

Không sửa tài liệu để che khác biệt chưa hiểu rõ. Snippet phải phản ánh response đã được xác nhận; nếu hai runtime có hợp đồng khác nhau, tài liệu phải thể hiện đúng biến thể hoặc hệ thống cần thống nhất hợp đồng.

## 16. Tích hợp Asciidoctor và CI

Asciidoctor include snippet được sinh từ test:

~~~asciidoc
== Lấy đơn hàng

=== HTTP request
include::{snippets}/orders/get/http-request.adoc[]

=== HTTP response
include::{snippets}/orders/get/http-response.adoc[]

=== Response fields
include::{snippets}/orders/get/response-fields.adoc[]
~~~

Gradle task có thể nối test và Asciidoctor:

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

Chạy:

~~~bash
./gradlew clean test asciidoctor
~~~

Nếu có hai test suite tạo snippet cho cùng operation, nên cấu hình output directory riêng hoặc chọn một suite làm nguồn snippet chính. Tránh để test song song ghi đè cùng file.

## 17. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Dùng WebTestClient nhưng nghĩ test đã chạy HTTP thật | Client đang bindToApplicationContext hoặc bindToController | Chuyển sang bindToServer nếu cần server boundary. |
| Dùng MockMvc để kiểm tra TLS/proxy | MockMvc không tạo network/TLS connection | Dùng test qua HTTP server/gateway thật. |
| WebTestClient không chạy Servlet filter | Test đang dùng WebFlux pipeline hoặc filter chưa đăng ký | Xác nhận runtime và đăng ký filter đúng stack. |
| MockMvcWebTestClient bị nhầm với WebFlux | Đây là adapter cho Spring MVC mock infrastructure | Dùng WebFlux context/client khi kiểm thử reactive stack. |
| Snippet response khác do codec | Cấu hình serializer không đồng nhất | Chia sẻ cấu hình hoặc document khác biệt có chủ đích. |
| Async snippet ghi response chưa hoàn tất | Chưa dispatch/consume kết quả cuối | Hoàn thành async flow trước document operation. |
| Không tìm thấy REST Docs snippet | Chưa cấu hình filter hoặc thiếu document(...) | Áp dụng đúng documentationConfiguration và consumer. |
| Snippet bị ghi đè giữa các suite | Dùng chung operation identifier/output path | Tách output hoặc tuần tự hóa suite tạo snippet. |

## 18. Bài thực hành

1. Tạo một endpoint GET đơn giản trong Spring MVC và document bằng MockMvc.
2. Kiểm thử cùng controller bằng MockMvcWebTestClient và so sánh fluent assertions.
3. Tạo WebFlux handler và document bằng WebTestClient bind vào application context.
4. Chạy server cục bộ rồi dùng bindToServer() để kiểm tra HTTP boundary.
5. So sánh response headers và JSON serialization giữa các binding mode.
6. Tạo một Servlet Filter và một WebFilter thêm correlation ID; quan sát test nào đi qua từng filter.
7. Tạo một MVC async endpoint và kiểm thử bằng asyncDispatch.
8. Tạo reactive endpoint trả Flux hữu hạn và kiểm tra body bằng WebTestClient.
9. Sinh snippets vào thư mục riêng cho từng suite, rồi ghép bộ snippet được chọn vào Asciidoctor.
10. Chạy Gradle/CI và xác nhận test/documentation không ghi đè output của nhau.

## 19. Ghi nhớ

- MockMvc kiểm thử Spring MVC qua mock Servlet infrastructure, không mở HTTP server thật.
- WebTestClient là fluent HTTP test client; binding mode quyết định nó kiểm thử in-memory hay qua server thật.
- MockMvcWebTestClient cho phép dùng WebTestClient API với Spring MVC mock infrastructure; nó không phải WebFlux runtime.
- Servlet Filters và WebFlux WebFilters thuộc hai pipeline khác nhau.
- MVC converters và WebFlux codecs có thể tạo khác biệt về serialization và content negotiation.
- Hoàn tất Servlet async dispatch hoặc reactive exchange trước khi document response.
- Cấu hình REST Docs riêng cho MockMvc và WebTestClient; tránh hai suite ghi đè cùng snippet.
- Dùng mock tests cho controller contract và server-bound tests khi cần xác nhận HTTP runtime/network boundary.

## 20. Tài liệu tham khảo

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử Spring MVC bằng mock Servlet API.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): binding modes và kiểm thử WebFlux/MVC qua WebTestClient.
- [Spring REST Docs — MockMvc](https://docs.spring.io/spring-restdocs/reference/working-with-mockmvc.html): tích hợp REST Docs với MockMvc.
- [Spring REST Docs — WebTestClient](https://docs.spring.io/spring-restdocs/reference/working-with-webtestclient.html): tích hợp REST Docs với WebTestClient.
