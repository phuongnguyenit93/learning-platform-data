# WebTestClient với controller, router hoặc ApplicationContext trong Spring WebFlux

## 1. WebTestClient dùng để kiểm thử điều gì?

**WebTestClient** là HTTP test client của Spring Framework. API của nó giống WebClient khi chuẩn bị request, nhưng sau khi gọi exchange() ta chuyển sang các assertion dành cho kiểm thử: HTTP status, headers, cookies, body JSON, DTO, danh sách hoặc reactive stream.

WebTestClient có thể chạy theo hai mô hình:

1. **Mock HTTP exchange**, không mở cổng mạng thật: client bind trực tiếp tới controller, RouterFunction hoặc ApplicationContext. Request/response là đối tượng mock trong Spring.
2. **Live HTTP exchange**, gửi request qua TCP tới server đang chạy: client dùng bindToServer().

Ba kiểu mock binding cần phân biệt:

- **bindToController(...):** tập trung vào annotated controller, dựng hạ tầng WebFlux cần thiết và đăng ký chính các controller được truyền vào.
- **bindToRouterFunction(...):** tập trung vào functional endpoint, sử dụng RouterFunction và handler lambda/HandlerFunction.
- **bindToApplicationContext(...):** lấy WebFlux configuration, handler mappings, web filters và những bean có liên quan từ ApplicationContext mà test đã khởi tạo.

Cả ba đều dùng WebTestClient để gọi HTTP-like request và assert response, nhưng **phạm vi hạ tầng được nạp** khác nhau. Nếu bạn muốn kiểm tra TCP, connector, TLS, reverse proxy hoặc cấu hình embedded server, phải dùng live-server test chứ không thể chỉ bind mock.

## 2. So sánh bốn cách tạo WebTestClient

| Cách | Có HTTP server thực? | Phạm vi | Khi nên dùng |
| --- | --- | --- | --- |
| bindToController(controller) | Không | Controller được chỉ định, hạ tầng WebFlux tối thiểu có thể tùy chỉnh | Test nhanh mapping, binding, status, body và collaboration giả lập |
| bindToRouterFunction(router) | Không | RouterFunction và các handler gắn vào router | Test predicates, path variables, route ordering, ServerResponse |
| bindToApplicationContext(context) | Không | Các WebFlux beans, mapping, filter, advice, codec từ context | Kiểm tra các thành phần phối hợp trong một web application context |
| bindToServer().baseUrl(...) | Có | HTTP transport, deployed server và cấu hình thật được kết nối | Integration/end-to-end HTTP, network-level behavior |

**Phân biệt quan trọng:** bindToApplicationContext có thể sử dụng một ApplicationContext đầy đủ nhưng **không** gửi request qua socket tới web server. Ngược lại, bindToServer có thể trỏ tới ứng dụng ở localhost, test environment hoặc một server từ xa.

### 2.1. Phạm vi unit test, slice test và integration test

- **Pure unit test:** gọi trực tiếp method controller/service, kiểm tra Mono/Flux bằng StepVerifier, không kiểm tra route, argument resolver hoặc codec.
- **Standalone WebTestClient:** bindToController hoặc bindToRouterFunction, kiểm tra qua mock HTTP exchange, hầu như không cần khởi động ApplicationContext.
- **Web slice:** @WebFluxTest load một phần Spring Boot context, tự cấu hình WebTestClient và dùng @MockitoBean cho dependency của controller.
- **Context integration:** @SpringBootTest + @AutoConfigureWebTestClient hoặc bindToApplicationContext dùng web application context.
- **Live HTTP integration:** @SpringBootTest(webEnvironment = RANDOM_PORT) hoặc server chạy độc lập, dùng WebTestClient qua HTTP port.

Không nên gọi một test là integration test chỉ vì nó có WebTestClient. Tên test cần phản ánh mức độ thành phần/transport được thực sự kiểm tra.

## 3. WebTestClient khác WebClient như thế nào?

WebClient là reactive HTTP client dùng trong ứng dụng. WebTestClient dùng để kiểm thử endpoint; bên trong nó sử dụng WebClient và thêm fluent assertion API.

Ví dụ test:

~~~java
client.get()
        .uri("/api/products/{id}", "p-1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("p-1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

Ý nghĩa:

1. get() chọn method.
2. uri() chọn path và biến URI.
3. accept() đặt Accept header.
4. exchange() thực hiện exchange test và trả ResponseSpec.
5. expectStatus() và expectHeader() kiểm tra HTTP metadata.
6. expectBody() đọc response body; jsonPath() kiểm tra một hoặc nhiều field JSON.

Đây là đoạn có thể đặt trong một test method, với biến client và MediaType đã được khai báo/import.

**Không nhầm** exchange() của WebTestClient với API WebClient.exchange() cũ đã deprecated. WebTestClient.exchange() là bước chuẩn của fluent testing API.

## 4. bindToController: kiểm tra annotated controller độc lập

### 4.1. Cách dựng client

~~~java
CatalogService stubService = new InMemoryCatalogService();
CatalogController controller = new CatalogController(stubService);

WebTestClient client = WebTestClient
        .bindToController(controller)
        .build();
~~~

Spring tạo hạ tầng WebFlux tương đương cấu hình WebFlux Java cần thiết, đăng ký controller đã truyền và định tuyến mock request đến các handler method.

Ví dụ GET /api/products/p-1:

~~~java
client.get()
        .uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Product.class)
        .isEqualTo(new Product("p-1", "Keyboard"));
~~~

Nhờ HTTP-like exchange, test bao phủ mapping annotations, path variables, body encoding và response status — hơn một pure unit test chỉ gọi controller.find() bằng Java.

### 4.2. Dependency không tự xuất hiện từ application context

Nếu controller có constructor:

~~~java
public CatalogController(CatalogService service) {
    this.service = service;
}
~~~

Với bindToController, test nên tự tạo controller và truyền mock/stub dependency. Không mong toàn bộ @Service hoặc @Repository được scan tự động như @SpringBootTest.

Có thể dùng Mockito:

~~~java
CatalogService service = Mockito.mock(CatalogService.class);
Mockito.when(service.findById("p-1"))
        .thenReturn(Mono.just(new Product("p-1", "Keyboard")));

WebTestClient client = WebTestClient
        .bindToController(new CatalogController(service))
        .build();
~~~

Ví dụ đó giả lập dependency để cô lập controller. Tuy nhiên mock sai có thể khiến test thành công mà không kiểm tra được logic truy cập dữ liệu thật. Kết hợp với test service và integration test khi thích hợp.

### 4.3. Cấu hình riêng cho ControllerSpec

WebTestClient.ControllerSpec có các API như:

- controllerAdvice(...) đăng ký exception handler/advice riêng cho standalone test.
- validator(...) đặt global Validator.
- formatters(...) thêm Converter hoặc Formatter.
- httpMessageCodecs(...) cấu hình HTTP readers/writers.
- argumentResolvers(...) thêm argument resolver.
- corsMappings(...) định nghĩa CORS mappings.
- webFilter(...) thêm WebFilter cụ thể.
- configureClient() chuyển sang cấu hình client như default headers, base URL, timeout.

Ví dụ minh họa codec limit và client response timeout:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new CatalogController(service))
        .httpMessageCodecs(codecs ->
                codecs.defaultCodecs()
                        .maxInMemorySize(256 * 1024))
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

Những cấu hình trên chỉ áp dụng cho test client/mock server được dựng; chúng không sửa configuration thật ở production.

### 4.4. Giới hạn quan trọng

bindToController không tự nạp toàn bộ WebFilter, SecurityWebFilterChain, custom codec beans hay @ControllerAdvice khác trong ứng dụng. Nếu production behavior phụ thuộc vào authentication, global exception mapping, custom message readers hoặc filter ordering thì cần đăng ký rõ các thành phần đó trong standalone test **hoặc** dùng bindToApplicationContext / Spring Boot test context.

Ví dụ nếu production có AuthenticationWebFilter từ Spring Security nhưng standalone test không có, một endpoint có thể trả 200 trong test và 401 ở deployment. Đây là khác biệt về **test scope**, không phải Spring Security bị lỗi.

## 5. bindToRouterFunction: kiểm tra functional endpoints

### 5.1. Functional endpoint trong WebFlux

Thay vì @RestController và @GetMapping, WebFlux có RouterFunction<ServerResponse> để ánh xạ RequestPredicate tới HandlerFunction.

Ví dụ một router:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
        .GET("/functional/ping", request ->
                ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new Greeting("pong")))
        .build();
~~~

Đoạn này giả sử record Greeting(String message) đã được định nghĩa. Nó không cần annotated controller.

Tạo client:

~~~java
WebTestClient client = WebTestClient
        .bindToRouterFunction(router)
        .build();

client.get()
        .uri("/functional/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("pong");
~~~

Spring dùng RouterFunctions.toWebHandler để tạo mock WebFlux handler chain từ router được truyền vào.

### 5.2. Kiểm tra RequestPredicate và path variables

Một route nhận sản phẩm:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route()
        .GET("/functional/products/{id}", request ->
                service.findById(request.pathVariable("id"))
                        .flatMap(product ->
                                ServerResponse.ok()
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .bodyValue(product))
                        .switchIfEmpty(
                                ServerResponse.notFound().build()))
        .build();
~~~

Test nên kiểm tra:

- Route đúng method/path trả 200.
- Route không khớp trả 404.
- ID không tồn tại trả 404.
- Content-Type và JSON response đúng.
- Nếu có nhiều predicates, route matching order được duy trì.
- Request filters/attributes được thêm vào test nếu functional handler phụ thuộc chúng.

### 5.3. Không nạp toàn bộ router của ứng dụng nếu chỉ truyền một router

bindToRouterFunction(router) chỉ bind những route nằm trong RouterFunction được truyền. Các router beans khác, global web filters hoặc security configuration từ ApplicationContext không tự xuất hiện.

Nếu route có dependency, cung cấp implementation hoặc mock service khi dựng RouterFunction. Nếu muốn test tất cả bean RouterFunction trong Boot context, bindToApplicationContext phù hợp hơn.

### 5.4. RouterFunction và Controller cùng tồn tại

Spring WebFlux cho phép cùng ứng dụng có annotated controllers và functional routes. ApplicationContext chứa cả hai được đăng ký qua HandlerMapping tương ứng.

Nhưng bindToController chỉ biết controller đã truyền; bindToRouterFunction chỉ biết router đã truyền. Điều đó tạo một chiến lược test tốt: kiểm tra từng route/controller độc lập ở lớp nhanh, rồi dùng bindToApplicationContext để xác nhận mọi mapping thật sự hoạt động cùng nhau.

## 6. bindToApplicationContext: mock HTTP với Spring context

### 6.1. Cơ chế

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class CatalogContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void checksConfiguredMappings() {
        WebTestClient client =
                WebTestClient.bindToApplicationContext(context).build();

        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Spring đã tạo ApplicationContext trước test. WebTestClient lấy WebFlux handler chain từ context thông qua WebHttpHandlerBuilder rồi xử lý request/response dạng mock.

Nó có thể sử dụng:

- Controller beans đã được Spring scan.
- Functional RouterFunction beans đã đăng ký.
- WebFilters, exception handlers và global config được context cung cấp.
- Codecs, formatters, validators theo WebFlux configuration.
- Security filters **nếu** context đã cấu hình Spring Security tương ứng.

Mức độ thực tế phụ thuộc context được nạp: một minimal test context vẫn khác full @SpringBootTest. Không mặc định tất cả dependency bên ngoài đều được kiểm tra chỉ vì ApplicationContext đầy đủ.

### 6.2. Dùng Boot tự cấu hình client

Với Spring Boot 3.5, có thể để Boot tạo WebTestClient:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CatalogIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsResource() {
        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Ở chế độ MOCK, embedded HTTP server **không mở port**. @AutoConfigureWebTestClient tự bind client vào application cho mock exchange. Đây là cách tiện khi không cần thao tác trực tiếp với ApplicationContext trong từng test.

### 6.3. Phân biệt @WebFluxTest

~~~java
@WebFluxTest(controllers = CatalogController.class)
class CatalogSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;
}
~~~

@WebFluxTest tạo web slice, tự cấu hình WebTestClient và chỉ scan các thành phần web cần thiết theo quy tắc Boot. @Service thông thường không tự xuất hiện; @MockitoBean cung cấp dependency giả.

Chọn:

- @WebFluxTest khi cần test controller và các quy tắc web mapping nhanh, không nạp toàn ứng dụng.
- @SpringBootTest(MOCK) + @AutoConfigureWebTestClient khi cần nhiều bean thực cùng phối hợp qua mock HTTP.
- @SpringBootTest(RANDOM_PORT) khi cần HTTP connector/server thật.

Lưu ý trong Spring Boot 4 các package và starter test có thay đổi; các import trong bài này cố định theo **Spring Boot 3.5.16**.

## 7. bindToServer: kiểm thử HTTP thực qua cổng mạng

### 7.1. Tạo client tới server đang chạy

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

Khi test gọi exchange(), client thật tạo HTTP request qua network tới baseUrl. Cách này bao phủ transport, endpoint server và những component được deploy ở địa chỉ đó.

Trong Spring Boot test nên để runtime chọn port ngẫu nhiên:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogLiveTest {

    @LocalServerPort
    int port;

    @Test
    void readsOverRealHttp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get().uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Đoạn trên là khung minh họa; ví dụ chạy được đầy đủ ở phần sau.

### 7.2. Chi phí và giới hạn

Live server tests thường chậm hơn mock binding: phải khởi động embedded server, có network I/O và có thể gặp lỗi bind port, TLS, proxy, environment. Nhưng đây là mức cần thiết để phát hiện sai sót không tồn tại trong mock exchange.

Ngay cả với RANDOM_PORT và HTTP thật, nếu database hoặc upstream service được mock thì test vẫn không phải end-to-end toàn hệ thống. Mức độ tích hợp phụ thuộc các dependency thật sự được kết nối.

## 8. Viết assertions đủ sâu

### 8.1. Status và headers

~~~java
client.post()
        .uri("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateProductRequest("Monitor"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON);
~~~

Không chỉ kiểm tra isOk nếu endpoint phải trả 201, 202, 204, 400, 404 hoặc 409. Status là một phần contract và cần test chính xác.

### 8.2. DTO

~~~java
client.get()
        .uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Product.class)
        .isEqualTo(new Product("p-1", "Keyboard"));
~~~

Với Java record, equals() so sánh các thành phần nên phù hợp để kiểm tra DTO deterministic.

### 8.3. Danh sách

~~~java
client.get()
        .uri("/api/products")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(Product.class)
        .hasSize(2)
        .contains(new Product("p-1", "Keyboard"));
~~~

expectBodyList gom body vào List. Chỉ dùng khi response hữu hạn và có kích thước phù hợp.

### 8.4. JSONPath

~~~java
client.get().uri("/api/products/p-1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("p-1")
        .jsonPath("$.name").isEqualTo("Keyboard");
~~~

JSONPath phù hợp khi chỉ cần một số trường, không muốn ràng buộc toàn bộ schema. Nếu cần kiểm tra contract toàn phần, có thể dùng .json(...) hoặc .expectBody(Product.class).isEqualTo(...).

### 8.5. Body không có dữ liệu

~~~java
client.delete().uri("/api/items/p-1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
~~~

Đây là snippet nếu ứng dụng có DELETE trả 204. Không nên gọi expectBodyList cho 204; cần xác nhận body rỗng bằng isEmpty().

### 8.6. Dừng ở nhiều assertions mà không fail sớm

WebTestClient.ResponseSpec có expectAll(...) để đánh giá nhiều expectation ở cùng response:

~~~java
client.get().uri("/api/products/p-1")
        .exchange()
        .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                        .contentTypeCompatibleWith(
                                MediaType.APPLICATION_JSON));
~~~

Khả năng tổng hợp nhiều assertion failures hữu ích khi kiểm tra metadata. Với JSON response, tiếp tục xác minh body qua expectBody/jsonPath hoặc typed DTO.

## 9. Reactive streaming và StepVerifier

### 9.1. Vì sao không dùng expectBodyList cho SSE vô hạn?

SSE dùng text/event-stream để server phát event theo thời gian. Nếu response không bao giờ kết thúc, expectBodyList hoặc expectBody() có thể chờ mãi hoặc cố aggregate lượng dữ liệu không giới hạn.

Spring Framework khuyến nghị gọi returnResult(Class) để nhận FluxExchangeResult<T> rồi dùng StepVerifier kiểm tra một phần stream.

~~~java
FluxExchangeResult<Tick> result = client.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(Tick.class);

StepVerifier.create(result.getResponseBody())
        .expectNext(new Tick(0, "pulse"))
        .expectNext(new Tick(1, "pulse"))
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

Ví dụ này dùng Tick record được định nghĩa trong project bên dưới. thenCancel() chủ động dừng subscription sau hai event, giúp test không bị treo do stream vô hạn.

### 9.2. Kiểm tra error, cancellation và backpressure

StepVerifier còn có:

- expectNext(...), expectNextCount(n), assertNext(consumer).
- expectError(...), expectErrorMatches(...).
- thenRequest(n) để điều khiển demand trong publisher test.
- thenCancel() để xác nhận lifecycle cancellation.
- verifyComplete() / verifyError().
- withVirtualTime(...) khi kiểm tra publisher dùng scheduler có thể ảo hóa.

Không mặc định rằng WebTestClient hoạt động với virtual time giống pure Reactor pipeline. Network I/O, connector và thời gian thực của HTTP mock/live exchange có thể không dùng scheduler ảo. Virtual time phù hợp hơn cho unit test trực tiếp lên Mono/Flux đã được thiết kế để sử dụng scheduler được kiểm soát.

### 9.3. Timeout cho streaming test

Nếu stream mãi không phát event, test phải fail sau thời gian hữu hạn. Dùng StepVerifier.verify(Duration.ofSeconds(...)) và client responseTimeout hợp lý; không sử dụng Thread.sleep để đoán timing.

Với slow stream, tránh expectBody() vì nó chỉ hoàn tất sau toàn bộ body. Lấy response stream và cancel sau số event mong muốn.

## 10. Security, filter và exception mapping thay đổi theo binding

### 10.1. Security filters

Khi ứng dụng có Spring Security, một @RestController có thể yêu cầu authentication. bindToController(controller) **không tự nạp toàn bộ SecurityWebFilterChain**. Test standalone bỏ qua security rất có thể nhận 200 cho request mà production sẽ trả 401.

Test bảo mật nên bindToApplicationContext với security chain thật hoặc dùng @WebFluxTest có cấu hình security hợp lệ. Khi dùng spring-security-test cho reactive WebTestClient, có thể áp dụng springSecurity() và mockUser()/csrf() nếu phù hợp với security configuration của test.

Snippet minh họa:

~~~java
WebTestClient secured = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

secured.mutateWith(mockUser("student"))
        .mutateWith(csrf())
        .post()
        .uri("/web/preferences")
        .exchange()
        .expectStatus().isOk();
~~~

Đoạn này chỉ dùng khi project thực sự có spring-security-test, Spring Security filter chain và endpoint /web/preferences. Nó **không** thuộc Maven demo tối giản bên dưới, vì demo tập trung ba cách bind WebTestClient.

### 10.2. Global @ControllerAdvice

bindToController chỉ nạp những controller/advice được đăng ký cho standalone setup. Nếu cần một @RestControllerAdvice tùy chỉnh, có thể gọi:

~~~java
WebTestClient.bindToController(controller)
        .controllerAdvice(new MyExceptionAdvice())
        .build();
~~~

MyExceptionAdvice ở đây là loại advice do ứng dụng định nghĩa. Với ApplicationContext binding, advice beans được Spring context phát hiện có thể tham gia bình thường.

### 10.3. WebFilter và WebFluxConfigurer

Một custom WebFilter có thể bổ sung correlation ID, request header, logging hoặc context. Nếu test standalone không có filter đó, assertion phụ thuộc header/filter có thể sai với production.

Có thể thêm .webFilter(...) vào mock server spec hoặc dùng bindToApplicationContext để tận dụng filter đã đăng ký trong context. Tương tự với custom converters, formatters, codecs và validators.

### 10.4. WebFlux so với Spring MVC

Với Spring WebFlux, dùng WebTestClient.bindToController và các kiểu bind như đã mô tả. Với Spring MVC, MockMvc là công cụ truyền thống; muốn dùng giao diện WebTestClient để kiểm tra Spring MVC standalone mock setup thì Spring có MockMvcWebTestClient.

Không áp nguyên hướng dẫn WebFlux trực tiếp vào ứng dụng Spring MVC có blocking Servlet stack rồi cho rằng cùng một binding backend.

## 11. Dự án chạy được: Java 17 và Spring Boot 3.5.16

Dự án gồm một annotated controller, một functional router, một SSE controller và nhiều test class với **cùng một model/service** để thấy rõ khác biệt giữa các kiểu binding.

Các chức năng:

- GET /api/products/p-1: trả Product.
- GET /api/products/missing: trả HTTP 404.
- GET /api/products: trả danh sách Product.
- POST /api/products: nhận JSON và trả 201 với Product vừa tạo mô phỏng.
- GET /functional/ping: trả JSON {"message":"pong"}.
- GET /functional/products/p-1: trả Product qua functional endpoint.
- GET /api/events: phát SSE theo thời gian.
- Các bài test: standalone controller, standalone router, ApplicationContext, Boot slice, live HTTP server.

Để test deterministic, service chỉ chứa dữ liệu cố định trong memory; không dùng database hoặc external API. Method create() tạo giá trị mẫu, **không** lưu bền vững.

### 11.1. Cấu trúc project

~~~text
webtestclient-bindings/
├── pom.xml
└── src/
    ├── main/java/example/testing/
    │   ├── DemoApplication.java
    │   ├── Product.java
    │   ├── CreateProductRequest.java
    │   ├── Greeting.java
    │   ├── Tick.java
    │   ├── CatalogService.java
    │   ├── InMemoryCatalogService.java
    │   ├── CatalogController.java
    │   ├── CatalogRouter.java
    │   └── EventsController.java
    └── test/java/example/testing/
        ├── ControllerBindingTest.java
        ├── RouterBindingTest.java
        ├── ApplicationContextBindingTest.java
        ├── WebFluxSliceTest.java
        └── LiveServerTest.java
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webtestclient-bindings</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dùng Java 17+ và Maven 3.9+ là phù hợp. spring-boot-starter-test cung cấp JUnit 5, AssertJ và Mockito cho các tests. reactor-test cung cấp StepVerifier. spring-boot-starter-validation hỗ trợ Jakarta Bean Validation.

### 11.3. DemoApplication.java

~~~java
package example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 11.4. Product.java

~~~java
package example.testing;

public record Product(String id, String name) {
}
~~~

### 11.5. CreateProductRequest.java

~~~java
package example.testing;

import jakarta.validation.constraints.NotBlank;

public record CreateProductRequest(
        @NotBlank String name
) {
}
~~~

### 11.6. Greeting.java

~~~java
package example.testing;

public record Greeting(String message) {
}
~~~

### 11.7. Tick.java

~~~java
package example.testing;

public record Tick(long sequence, String value) {
}
~~~

### 11.8. CatalogService.java

~~~java
package example.testing;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogService {

    Mono<Product> findById(String id);

    Flux<Product> all();

    Mono<Product> create(String name);
}
~~~

### 11.9. InMemoryCatalogService.java

~~~java
package example.testing;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class InMemoryCatalogService implements CatalogService {

    private final Map<String, Product> products = Map.of(
            "p-1", new Product("p-1", "Keyboard"),
            "p-2", new Product("p-2", "Mouse")
    );

    @Override
    public Mono<Product> findById(String id) {
        return Mono.justOrEmpty(products.get(id));
    }

    @Override
    public Flux<Product> all() {
        return Flux.just(
                products.get("p-1"),
                products.get("p-2"));
    }

    @Override
    public Mono<Product> create(String name) {
        return Mono.just(new Product("created", name));
    }
}
~~~

Ví dụ cố định thứ tự danh sách bằng cách gọi trực tiếp hai key p-1, p-2. Không duyệt Map.of bằng iteration order rồi khẳng định thứ tự luôn xác định.

### 11.10. CatalogController.java

~~~java
package example.testing;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity
                        .status(HttpStatus.NOT_FOUND)
                        .<Product>build());
    }

    @GetMapping
    public Flux<Product> all() {
        return service.all();
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Product>> create(
            @Valid @RequestBody CreateProductRequest request) {
        return service.create(request.name())
                .map(product -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(product));
    }
}
~~~

Các điểm cần test:

- Path /api/products/{id} lấy ID đúng.
- Mono.empty() từ service được ánh xạ thành 404.
- Flux<Product> được JSON encoder viết thành array hữu hạn.
- POST body JSON được decode thành record CreateProductRequest, validation kiểm tra @NotBlank.
- HTTP 201 được trả cho create().

### 11.11. CatalogRouter.java

~~~java
package example.testing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class CatalogRouter {

    @Bean
    public RouterFunction<ServerResponse> catalogRoutes(
            CatalogService service) {

        return RouterFunctions.route()
                .GET("/functional/ping", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new Greeting("pong")))

                .GET("/functional/products/{id}", request ->
                        service.findById(request.pathVariable("id"))
                                .flatMap(product ->
                                        ServerResponse.ok()
                                                .contentType(
                                                        MediaType.APPLICATION_JSON)
                                                .bodyValue(product))
                                .switchIfEmpty(
                                        ServerResponse.notFound().build()))
                .build();
    }
}
~~~

Ở đây RouterFunction là bean Spring nên có mặt khi bindToApplicationContext. Trong RouterBindingTest, ta tự gọi catalogRoutes(service) để lấy router độc lập mà không khởi tạo ApplicationContext.

Không dùng @RestController trên CatalogRouter. RequestPredicate và HandlerFunction được tạo thông qua RouterFunctions.route() builder.

### 11.12. EventsController.java

~~~java
package example.testing;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
public class EventsController {

    @GetMapping(
            path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Tick>> events() {
        return Flux.interval(Duration.ofMillis(30))
                .map(index ->
                        ServerSentEvent.<Tick>builder(
                                        new Tick(index, "pulse"))
                                .id(Long.toString(index))
                                .event("tick")
                                .build());
    }
}
~~~

Flux.interval tạo stream vô hạn. Endpoint SSE không có kết quả cuối tự nhiên; client hoặc test phải cancel khi đã nhận đủ event.

## 12. Các test chạy được của ba binding modes

### 12.1. ControllerBindingTest.java — bindToController

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ControllerBindingTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        CatalogService service = new InMemoryCatalogService();

        client = WebTestClient
                .bindToController(new CatalogController(service))
                .configureClient()
                .responseTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Test
    void readsExistingProduct() {
        client.get()
                .uri("/api/products/p-1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(Product.class)
                .isEqualTo(new Product("p-1", "Keyboard"));
    }

    @Test
    void returns404ForMissingProduct() {
        client.get()
                .uri("/api/products/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }

    @Test
    void decodesFiniteListOfProducts() {
        client.get()
                .uri("/api/products")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(Product.class)
                .hasSize(2)
                .contains(new Product("p-1", "Keyboard"),
                          new Product("p-2", "Mouse"));
    }

    @Test
    void postsJsonAndReceivesCreatedStatus() {
        client.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest("Monitor"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo("created")
                .jsonPath("$.name").isEqualTo("Monitor");
    }
}
~~~

Không có @SpringBootTest vì các dependency/controller được tạo trực tiếp. Client vẫn đi qua HTTP mapping, codecs và binding của WebFlux mock server.

### 12.2. RouterBindingTest.java — bindToRouterFunction

~~~java
package example.testing;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

class RouterBindingTest {

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        CatalogService service = new InMemoryCatalogService();

        RouterFunction<ServerResponse> router =
                new CatalogRouter().catalogRoutes(service);

        client = WebTestClient
                .bindToRouterFunction(router)
                .build();
    }

    @Test
    void routesFunctionalPing() {
        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }

    @Test
    void bindsPathVariableForFunctionalHandler() {
        client.get()
                .uri("/functional/products/p-2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-2", "Mouse"));
    }

    @Test
    void returns404WhenProductMissing() {
        client.get()
                .uri("/functional/products/missing")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody().isEmpty();
    }

    @Test
    void doesNotExposeControllerRoute() {
        client.get()
                .uri("/api/products/p-1")
                .exchange()
                .expectStatus().isNotFound();
    }
}
~~~

Test cuối cùng minh họa **isolation của bindToRouterFunction**: client này chỉ biết RouterFunction đã truyền; nó không scan annotated CatalogController.

### 12.3. ApplicationContextBindingTest.java — bindToApplicationContext

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ApplicationContextBindingTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebTestClient autoConfiguredClient;

    @Test
    void manuallyBoundClientSeesControllerAndRouter() {
        WebTestClient client = WebTestClient
                .bindToApplicationContext(context)
                .build();

        client.get()
                .uri("/api/products/p-1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Keyboard");

        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }

    @Test
    void bootAutoConfiguredMockClientIsEquivalentForHttpContracts() {
        autoConfiguredClient.get()
                .uri("/functional/products/p-2")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-2", "Mouse"));
    }

    @Test
    void beanValidationRejectsBlankName() {
        autoConfiguredClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateProductRequest(" "))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validatesAndCancelsStreamingResponse() {
        FluxExchangeResult<Tick> result = autoConfiguredClient
                .get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(Tick.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new Tick(0L, "pulse"))
                .expectNext(new Tick(1L, "pulse"))
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
~~~

Giải thích:

- ApplicationContext chứa CatalogController, CatalogRouter, EventsController và InMemoryCatalogService.
- Test đầu khởi tạo WebTestClient thủ công bằng bindToApplicationContext.
- Test tiếp dùng WebTestClient do @AutoConfigureWebTestClient tạo.
- Request validation đi qua cấu hình Bean Validation đã có từ starter-validation.
- Test SSE dùng FluxExchangeResult + StepVerifier, nhận hai event rồi hủy subscription.

**Không** có cổng HTTP thật được mở vì webEnvironment = MOCK.

### 12.4. WebFluxSliceTest.java — @WebFluxTest và @MockitoBean

~~~java
package example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(controllers = CatalogController.class)
class WebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    CatalogService service;

    @Test
    void controllerUsesMockService() {
        when(service.findById("p-9"))
                .thenReturn(Mono.just(
                        new Product("p-9", "Test Product")));

        client.get()
                .uri("/api/products/p-9")
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-9", "Test Product"));
    }
}
~~~

@WebFluxTest không nạp InMemoryCatalogService thật theo component scan thông thường, nên @MockitoBean tạo mock CatalogService cho controller. Đây là web slice hữu ích khi không muốn khởi động toàn bộ application.

Trong Spring Boot 3.5, import của @WebFluxTest là org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest; import của @MockitoBean là org.springframework.test.context.bean.override.mockito.MockitoBean.

### 12.5. LiveServerTest.java — bindToServer

~~~java
package example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LiveServerTest {

    @LocalServerPort
    int port;

    @Test
    void requestsUseRealHttpConnector() {
        WebTestClient client = WebTestClient
                .bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();

        client.get()
                .uri("/api/products/p-1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody(Product.class)
                .isEqualTo(new Product("p-1", "Keyboard"));

        client.get()
                .uri("/functional/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("pong");
    }
}
~~~

RANDOM_PORT giúp tránh xung đột cổng 8080 khi chạy test; @LocalServerPort lấy cổng được server thực chọn. WebTestClient.bindToServer() gửi HTTP request qua Reactor Netty client connector.

### 12.6. Chạy test và ứng dụng

Tại thư mục project có pom.xml:

~~~bash
mvn test
~~~

Khi dự án có đầy đủ các tệp như trên, Maven sẽ chạy JUnit tests. Kết quả mong muốn:

~~~text
Tests run: 14, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **kết quả kỳ vọng nếu các test đều pass**, không phải stdout đã đo bằng một lần chạy Maven thực tế. Số dòng log, warning và thứ tự test tùy Maven/JUnit/runtime. Nếu một test lỗi, đọc stack trace và xác định có khác biệt về web stack, validation provider, codec hoặc môi trường.

Chạy server để kiểm tra thủ công:

~~~bash
mvn spring-boot:run
~~~

Thử annotated controller:

~~~bash
curl -i http://localhost:8080/api/products/p-1
curl -i http://localhost:8080/api/products/missing
curl -i http://localhost:8080/api/products
~~~

Thử POST:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Monitor"}'
~~~

Thử functional router:

~~~bash
curl -i http://localhost:8080/functional/ping
curl -i http://localhost:8080/functional/products/p-2
~~~

Thử SSE, tham số -N vô hiệu hóa buffering của curl:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Một số response mẫu:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"p-1","name":"Keyboard"}
~~~

~~~http
HTTP/1.1 404 Not Found
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":"created","name":"Monitor"}
~~~

Kết quả status/body ở trên là contract của code demo; các headers như Date/Transfer-Encoding, Content-Length và thứ tự field có thể khác theo connector/runtime.

## 13. Chọn mức test hợp lý theo mục tiêu

| Mục tiêu | Nên chọn | Không cần |
| --- | --- | --- |
| Controller có mapping đúng và trả DTO đúng | bindToController | Khởi động tất cả services |
| Controller chuyển Mono.empty thành 404 | bindToController hoặc @WebFluxTest | Network server |
| Functional RouterFunction matches path/header | bindToRouterFunction | @SpringBootTest đầy đủ |
| @ControllerAdvice, WebFilter, Converter chạy cùng nhau | bindToApplicationContext với cấu hình phù hợp | TCP server nếu không kiểm tra transport |
| Kiểm tra web slice của Boot và mock service | @WebFluxTest + @MockitoBean | Database hay service thật |
| Kiểm tra Spring component scan và bean wiring | @SpringBootTest(MOCK) | Port thật |
| Kiểm tra server/HTTP connector/proxy behavior | bindToServer + RANDOM_PORT | Standalone mock |
| Kiểm tra SSE/NDJSON streaming | returnResult + StepVerifier | expectBodyList trên stream vô hạn |
| Kiểm tra bean validation, 400/422 contract | Web slice/context + validation provider | Gọi trực tiếp controller bằng Java |
| Kiểm tra authentication/filter-chain behavior | Context có Spring Security và test config | Standalone controller bỏ filter |

Không cần dùng mọi mức test cho tất cả endpoint. Test pyramid nên có nhiều unit/slice test nhanh, một số mock-context integration tests và một số live HTTP tests cho đường đi quan trọng.

## 14. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ bindToController gọi server thật | Test không bao phủ network/port/TLS | Dùng bindToServer với live server |
| Nghĩ bindToApplicationContext luôn là end-to-end | Không có HTTP socket khi mock binding | Phân biệt context và transport |
| Controller constructor cần service nhưng chỉ truyền class | Dependency chưa được cung cấp | Tạo controller với mock/stub hoặc dùng Spring context |
| Test standalone quên @ControllerAdvice | Lỗi được map khác production | controllerAdvice(...) hoặc context binding |
| Test standalone bỏ SecurityWebFilterChain | Endpoint nhận 200 thay vì 401 | Context integration với security chain và test security helpers |
| Dùng bindToRouterFunction rồi gọi @RestController path | 404 do controller không được bind | Bind controller riêng hoặc dùng context |
| Dùng @WebFluxTest nhưng mong @Service thật được load | Unsatisfied dependency | @MockitoBean hoặc @Import đúng collaborator |
| Dùng @SpringBootTest cho từng getter đơn giản | Test chậm, bối cảnh lớn không cần thiết | bindToController hoặc @WebFluxTest |
| Dùng @SpringBootTest(MOCK) để kiểm tra TCP | Không mở embedded server | RANDOM_PORT và bindToServer |
| Khẳng định status 200 nhưng không kiểm tra JSON | Test bỏ lọt sai field/body | expectBody, JSONPath hoặc typed DTO |
| Gom SSE vô hạn bằng expectBodyList | Treo test hoặc buffer vô hạn | returnResult + StepVerifier rồi cancel |
| Dùng block() hoặc subscribe() trong controller test | Che lifecycle/cancellation | Kiểm tra qua publisher/StepVerifier |
| Không kiểm tra 404 hoặc validation error | Thiếu negative test | Thêm 400/404/401/403 theo contract |
| Dùng Thread.sleep để chờ stream | Test flaky | StepVerifier với verify(Duration) |
| Giữ context có mutable shared state giữa tests | Các tests ảnh hưởng nhau | Reset state, stub/mock hoặc làm sạch fixture |
| Không giới hạn test timeout | CI có thể treo | Client responseTimeout và verify timeout |
| Khẳng định server mock đã chứng minh TLS | TLS handshake chưa được chạy | Live transport/security tests |
| Trộn spring-boot-starter-web với WebFlux rồi không kiểm tra web application type | Có thể chạy trên Spring MVC thay vì WebFlux | Chỉ dùng WebFlux starter hoặc đặt spring.main.web-application-type=reactive khi cần |

## 15. Checklist khi thiết kế bài test WebFlux

Trước khi commit test suite, kiểm tra:

1. Endpoint dùng annotated controller hay functional router?
2. Test cần mock WebFlux exchange hay HTTP transport thực?
3. Dependency của controller được cung cấp như thế nào?
4. Có filter/advice/security/config cần test không?
5. @WebFluxTest có đang dùng đúng package annotation theo Boot version không?
6. Có mock service bằng @MockitoBean và verify interaction nếu cần không?
7. Request có Content-Type, Accept, body và path/query params đúng không?
8. Status được assert chính xác (200, 201, 204, 400, 404, v.v.) không?
9. JSONPath/DTO assertion có kiểm tra đủ các field quan trọng không?
10. Response rỗng có được assert bằng isEmpty() không?
11. Streaming response có được cancel và timeout hữu hạn không?
12. @SpringBootTest(MOCK) có thật sự không mở port như mong muốn không?
13. RANDOM_PORT có dùng @LocalServerPort thay vì hardcode 8080 không?
14. Tests có phụ thuộc network, database hoặc thời gian thực ngoài ý muốn không?
15. Có test âm cho invalid input, missing entity và unauthorized request khi phù hợp không?
16. Tests có deterministic, độc lập thứ tự chạy và không leak subscription/connection không?

## 16. Ghi nhớ

- WebTestClient là HTTP test client của Spring, dùng WebClient để chuẩn bị request nhưng có API assertions riêng sau exchange().
- bindToController kiểm tra annotated controllers với mock request/response.
- bindToRouterFunction kiểm tra functional RouterFunction với mock request/response.
- bindToApplicationContext sử dụng WebFlux beans và handler chain từ Spring context nhưng vẫn không mở HTTP server thật.
- bindToServer gửi HTTP request thật tới server đang chạy.
- configureClient() chuyển từ mock server setup sang WebTestClient.Builder để đặt baseUrl, timeout hoặc default headers.
- @WebFluxTest tạo web slice và tự cấu hình WebTestClient; @MockitoBean cấp dependency giả trong Spring Boot 3.5.
- @SpringBootTest(MOCK) + @AutoConfigureWebTestClient kiểm tra app context với mock exchange; RANDOM_PORT khởi động server thật.
- expectBody(Class), expectBodyList(Class), expectBody().jsonPath và isEmpty là các API phổ biến.
- SSE và stream vô hạn nên dùng returnResult(Tick.class), FluxExchangeResult và StepVerifier.thenCancel.
- Không coi standalone mock test là bằng chứng security filters hoặc production server network đã được kiểm tra.
- Ưu tiên test đúng phạm vi rồi bổ sung live HTTP tests cho các contract quan trọng.

**Tài liệu chính thức và tham khảo:**
- [Spring Framework 6.2 — WebTestClient: controller, router, ApplicationContext, server và streaming](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Framework 6.2 — WebTestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html)
- [Spring Framework 6.2 — WebTestClient.ControllerSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.ControllerSpec.html)
- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @WebFluxTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Boot 3.5 — @AutoConfigureWebTestClient Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
