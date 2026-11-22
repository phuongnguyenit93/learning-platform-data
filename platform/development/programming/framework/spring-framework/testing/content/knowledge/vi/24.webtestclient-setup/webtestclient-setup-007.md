# Chọn ranh giới kiểm thử mà mỗi chế độ thực sự bao phủ

## Ranh giới kiểm thử quyết định điều gì được đưa vào bài test

WebTestClient cung cấp một API fluent để gửi request và kiểm tra response HTTP. Tuy nhiên, cùng một API này có thể chạy ở nhiều ranh giới khác nhau. Có chế độ tạo request/response mô phỏng bên trong Spring WebFlux; có chế độ gọi một server đang chạy qua HTTP thật.

Vì vậy, khi chọn cách tạo WebTestClient, điều cần xác định trước là bài test muốn xác nhận phần nào của ứng dụng:

- Một controller cùng các thành phần WebFlux tối thiểu cần để gọi controller.
- Cấu hình WebFlux và các bean đang có trong ApplicationContext.
- Một RouterFunction của mô hình functional endpoint.
- Toàn bộ ứng dụng đang chạy sau một cổng HTTP thực.

Các lựa chọn này không phải bốn mức độ chất lượng theo thứ tự tăng dần. Mỗi lựa chọn tạo ra một ranh giới khác nhau. Test ở ranh giới hẹp có thể chạy nhanh và chỉ rõ lỗi của một thành phần; test ở ranh giới rộng hơn có thể phát hiện vấn đề cấu hình hoặc tích hợp mà test hẹp không nhìn thấy. Chọn chế độ dựa trên hợp đồng cần xác nhận sẽ giúp bài test vừa có ý nghĩa vừa tránh kéo theo các thành phần không liên quan.

## Bốn cách khởi tạo WebTestClient

Các phương thức factory thường dùng:

~~~java
WebTestClient.bindToController(controller).build();

WebTestClient.bindToApplicationContext(applicationContext).build();

WebTestClient.bindToRouterFunction(routerFunction).build();

WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
~~~

Ba lựa chọn đầu tích hợp với hạ tầng kiểm thử mô phỏng của Spring WebFlux. Chúng không gửi request qua socket tới một server đang lắng nghe. Lựa chọn cuối tạo client kết nối tới server thật đang chạy.

| Chế độ | Đầu vào chính | Ranh giới được kiểm tra | Không tự động bao gồm |
| --- | --- | --- | --- |
| bindToController | Các controller instance | Controller và hạ tầng WebFlux tối thiểu để ánh xạ, bind request và tạo response | Toàn bộ cấu hình, component scan và filter chain của ứng dụng |
| bindToApplicationContext | WebFlux ApplicationContext | WebFlux infrastructure và các bean/cấu hình được đăng ký trong context | HTTP connector và hành vi của server container thật |
| bindToRouterFunction | RouterFunction | Định tuyến và handler của functional endpoint cùng hạ tầng WebFlux hỗ trợ | Annotation controller mapping và toàn bộ application context nếu không được cung cấp riêng |
| bindToServer | Địa chỉ server đang chạy | Request/response HTTP qua connector tới ứng dụng đang phục vụ request | Các hệ thống bên ngoài không được cấu hình hoặc không được gọi bởi ứng dụng |

## bindToController: tập trung vào controller

**bindToController(...)** phù hợp khi muốn kiểm tra một hoặc một vài controller cụ thể. Test cung cấp trực tiếp các controller instance; WebTestClient dựng hạ tầng WebFlux cần thiết để xử lý request và gọi chúng.

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController(new GreetingService()))
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

Ranh giới này hữu ích để kiểm tra:

- Mapping từ HTTP method và path đến handler method.
- Đọc path variable, query parameter, header và request body.
- Chuyển đổi tham số đầu vào, xử lý kiểu trả về và ghi response bằng WebFlux message codecs.
- Status và payload mà controller trả về.
- Exception handling được khai báo hoặc cấu hình trực tiếp cho phạm vi test.

Controller được đưa vào trực tiếp, nên test không chứng minh component scan của ứng dụng có tìm thấy controller hay không. Những bean khác của ứng dụng cũng không tự động xuất hiện chỉ vì controller có constructor dependency. Hãy truyền dependency rõ ràng, thường là mock hoặc fake khi mục tiêu là kiểm tra hành vi của controller.

Nếu cần kiểm tra một global concern như controller advice hoặc validator, cấu hình nó trong controller spec nếu API builder hỗ trợ, hoặc chuyển sang kiểm thử ApplicationContext khi muốn xác nhận cấu hình thật của ứng dụng. Việc thêm thủ công một thành phần vào test làm nó thuộc ranh giới test đó; điều này không chứng minh thành phần được đăng ký đúng trong cấu hình production.

Chọn chế độ này khi câu hỏi là: “Với các dependency đã được cung cấp, controller có diễn giải request và tạo response đúng không?” Nó không phù hợp để kết luận toàn bộ WebFlux application đã được lắp ráp đúng.

## bindToApplicationContext: kiểm tra cấu hình WebFlux đã lắp ráp

**bindToApplicationContext(applicationContext)** dùng một WebFlux ApplicationContext đã được chuẩn bị. WebTestClient lấy hạ tầng xử lý request từ context, nhờ đó bài test đi qua cấu hình WebFlux và các bean được đăng ký trong phạm vi đó.

Ví dụ với context được tạo từ cấu hình test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebFluxTestConfig.class)
class GreetingWebFluxTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .build();
    }

    @Test
    void resolvesGreetingThroughConfiguredWebFluxInfrastructure() {
        client.get()
                .uri("/greeting")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello");
    }
}
~~~

Tùy cấu hình context, ranh giới này có thể bao gồm:

- Controller và handler mapping được đăng ký trong context.
- WebFlux configuration, message codecs, formatter và validator.
- WebFilter, exception handler và các thành phần hạ tầng WebFlux được đăng ký.
- Các bean nghiệp vụ thật hoặc mock được khai báo trong context.

Khác với bindToController, test có thể phát hiện lỗi do cấu hình WebFlux không được import, bean không được đăng ký hoặc filter/handler không nằm trong chuỗi xử lý của context. Đây là lựa chọn phù hợp khi cần xác nhận các thành phần Spring được ghép với nhau đúng cách.

Request vẫn được xử lý qua mock request/response của WebFlux. Test không mở cổng TCP và không đi qua connector hoặc server container thật. Vì vậy, nó không xác nhận các vấn đề chỉ xuất hiện khi triển khai server, chẳng hạn cấu hình cổng, TLS, socket, giới hạn kết nối hay tích hợp cụ thể với runtime server.

Phạm vi của test phụ thuộc vào context được nạp. Một context tối giản chỉ import một vài cấu hình vẫn là context test tối giản; dùng bindToApplicationContext không tự biến nó thành toàn bộ application context production. Hãy kiểm tra rõ lớp cấu hình hoặc cơ chế bootstrap tạo ra context.

Chọn chế độ này khi câu hỏi là: “Các bean và cấu hình WebFlux trong context này có phối hợp để xử lý request đúng không?”

## bindToRouterFunction: tập trung vào functional endpoint

Spring WebFlux cho phép khai báo HTTP endpoint bằng functional routing thay vì annotation controller. Một RouterFunction mô tả cách chọn route dựa trên request và chuyển request tới handler tương ứng.

**bindToRouterFunction(routerFunction)** phù hợp khi muốn kiểm tra trực tiếp một RouterFunction. Test không cần dựng annotation controller mapping cho các route này.

Ví dụ:

~~~java
import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;
import static org.springframework.web.reactive.function.server.ServerResponse.ok;

RouterFunction<ServerResponse> routes = route(
        GET("/greeting"),
        request -> ok().bodyValue(Map.of("message", "Hello"))
);

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

Ranh giới này cho phép kiểm tra:

- Predicate có khớp đúng method, path, header hoặc điều kiện request hay không.
- Route có chọn đúng handler hay trả về not found.
- Handler tạo status, header và body đúng không.
- Các filter được compose trực tiếp vào RouterFunction có tác động đúng không.

Ví dụ, nếu route được tạo từ nhiều hàm rồi kết hợp bằng RouterFunctions.route(...) hoặc andOther(...), test có thể gửi request qua kết quả kết hợp đó để kiểm tra thứ tự và kết quả định tuyến.

RouterFunction được truyền trực tiếp nên test không chứng minh annotation controller của ứng dụng hoạt động. Nó cũng không tự động kiểm tra mọi bean hoặc WebFilter chỉ tồn tại trong một ApplicationContext khác. Nếu một filter, codec hoặc thành phần dùng chung là một phần của hợp đồng cần xác nhận, phải đưa cấu hình đó vào ranh giới test phù hợp, thường là bindToApplicationContext.

Chọn chế độ này khi câu hỏi là: “Bộ route functional và handler được cung cấp có phân loại request và trả response đúng không?”

## bindToServer: đi qua HTTP tới server đang chạy

**bindToServer()** tạo WebTestClient kết nối tới một server đang lắng nghe tại địa chỉ được cấu hình. Request được gửi qua client connector và đi vào server như một HTTP request thực.

Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

Với Spring Boot, một bài test có thể khởi động ứng dụng trên cổng ngẫu nhiên rồi kết nối tới cổng đó. Cách khởi động cụ thể phụ thuộc test setup; điều quan trọng là server phải sẵn sàng trước khi WebTestClient gửi request.

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingServerTests {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void servesGreetingOverHttp() {
        client.get()
                .uri("/greeting")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello");
    }
}
~~~

Ranh giới này bao gồm các thành phần thực sự được ứng dụng đang chạy sử dụng để phục vụ request, chẳng hạn:

- Server connector và đường truyền HTTP từ client tới server.
- Server runtime và cấu hình triển khai được bật trong môi trường test.
- WebFlux handler chain, filter, security và message codec đang hoạt động trong ứng dụng.
- Các bean nghiệp vụ và dependency mà ứng dụng thực sự kết nối tới trong cấu hình test.

Do có server thật, chế độ này phù hợp để phát hiện lỗi không xuất hiện trong mock request/response, như cấu hình server, connector hoặc sự khác biệt ở đường truyền HTTP. Nó cũng kiểm tra ứng dụng sau khi khởi động và lắp ráp các thành phần theo cấu hình của môi trường test.

Tuy vậy, “đi qua server thật” không đồng nghĩa với “đã kiểm thử mọi hệ thống bên ngoài”. Nếu database, message broker hoặc API bên thứ ba được thay bằng mock, test vẫn chỉ bao phủ cấu hình mock đó. Nếu cần xác nhận tích hợp với dependency thật, hãy cấu hình dependency tương ứng và quản lý vòng đời của chúng một cách rõ ràng.

Chọn chế độ này khi câu hỏi là: “Ứng dụng đang chạy có nhận HTTP request qua server và trả response đúng như client quan sát được không?”

## So sánh theo điều test thực sự cần xác nhận

| Câu hỏi cần trả lời | Chế độ phù hợp | Vì sao |
| --- | --- | --- |
| Một controller xử lý request và trả DTO đúng với dependency đã cung cấp? | bindToController | Phạm vi hẹp, tập trung vào controller |
| Controller, WebFilter, codec và cấu hình WebFlux trong context có phối hợp đúng? | bindToApplicationContext | Đi qua WebFlux infrastructure được lắp ráp trong context |
| Functional route chọn đúng handler và response? | bindToRouterFunction | Đưa RouterFunction trực tiếp vào test |
| Server đang chạy có nhận request HTTP và trả response qua connector? | bindToServer | Gửi request qua HTTP tới server thật |
| Cấu hình TLS, connector hoặc hành vi server runtime có đúng? | bindToServer | Các chế độ mock không đi qua server connector thật |
| Component scan hoặc cấu hình ứng dụng có đăng ký đúng controller/filter/bean? | bindToApplicationContext hoặc bindToServer | Cần dùng context được tạo bởi cấu hình ứng dụng tương ứng |

Không nên chọn bindToServer chỉ vì nó có ranh giới rộng hơn. Nó cần server được khởi động, thường tốn thời gian hơn và có thể cần quản lý cổng, dependency hoặc dữ liệu test. Nếu một test controller có thể xác nhận hợp đồng cần thiết ở bindToController, thêm server vào test có thể làm tăng chi phí mà không tạo thêm bằng chứng hữu ích.

Ngược lại, nếu lỗi cần phát hiện nằm ở việc đăng ký WebFilter hoặc cấu hình message codec, test chỉ tạo controller trực tiếp sẽ không kiểm tra được phần đó. Khi ấy phải mở rộng ranh giới sang ApplicationContext hoặc server thật.

## Cấu hình client không làm thay đổi ranh giới server

WebTestClient cho phép cấu hình phần client sau khi đã chọn cách kết nối. Ví dụ:

~~~java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .configureClient()
        .defaultHeader("X-Test-Client", "mvc-suite")
        .build();
~~~

**configureClient()** chuyển từ cấu hình server/test infrastructure sang cấu hình WebTestClient client. Các tùy chọn như default header, filter phía client hoặc response timeout ảnh hưởng cách client gửi request và xử lý response.

Việc thêm base URL, default header hoặc client filter không biến bindToController thành bindToServer. Ranh giới server-side vẫn do phương thức bind ban đầu quyết định. Tương tự, tăng response timeout không làm test bao phủ thêm connector, filter hoặc bean ứng dụng.

Khi cần cấu hình cả hai phía, hãy xác định riêng:

- **Phía server/test infrastructure:** controller, ApplicationContext, RouterFunction hay server đang chạy.
- **Phía client:** base URL, default header, authentication header, client filter, codec phía client và response timeout.

Việc tách hai phía giúp đọc test dễ hơn: một cấu hình xác định request đi vào đâu, cấu hình còn lại xác định client gửi và quan sát request như thế nào.

## WebTestClient với Spring MVC là một ranh giới khác

WebTestClient thường được dùng với Spring WebFlux. Spring Framework cũng cung cấp adapter **MockMvcWebTestClient** để dùng API kiểm tra kiểu WebTestClient trong khi request được thực thi bởi MockMvc của Spring MVC.

Ví dụ:

~~~java
WebTestClient client = MockMvcWebTestClient
        .bindToController(new GreetingMvcController())
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Hello");
~~~

Đây là tích hợp MockMvc, không phải bindToApplicationContext của WebFlux và cũng không phải bindToServer. Nó hữu ích khi muốn dùng cách viết request/response assertion của WebTestClient cho ứng dụng Spring MVC mà vẫn giữ ranh giới mock của MockMvc.

Nếu cần kiểm tra thêm các chi tiết đặc thù của MockMvc, adapter có thể cung cấp cách lấy lại kết quả MockMvc từ exchange result thông qua **MockMvcWebTestClient.resultActionsFor(...)**. Điều đó giúp truy cập các assertion hoặc API kiểm thử bổ sung của MockMvc khi cần.

Vì vậy, khi dự án dùng Spring MVC, hãy chọn adapter dành cho MockMvc nếu mục tiêu là kiểm thử MVC trong môi trường mock. Chỉ dùng bindToServer khi muốn gửi request qua server đang chạy.

## Những lỗi thường gặp khi chọn sai chế độ

### Dùng bindToController nhưng kỳ vọng component scan hoạt động

Controller được truyền trực tiếp nên test không xác nhận Spring Boot có tìm thấy controller qua component scan hay không. Nếu cần kiểm tra việc đăng ký bean từ cấu hình ứng dụng, hãy dùng ApplicationContext được bootstrap phù hợp.

### Dùng bindToApplicationContext nhưng nghĩ rằng đã kiểm tra HTTP connector

ApplicationContext mode xử lý request qua mock server-side exchange của WebFlux. Nó kiểm tra cấu hình framework trong context, nhưng không mở cổng hoặc gửi dữ liệu qua socket. Hãy dùng server mode cho hành vi connector.

### Dùng bindToRouterFunction cho annotation controller

RouterFunction là mô hình functional routing. Nó không thay thế RequestMappingHandlerMapping và không tự tìm các method có @GetMapping hoặc @PostMapping. Với annotation controller, chọn controller mode hoặc context mode.

### Dùng bindToServer nhưng server chưa sẵn sàng

Client không thể kết nối nếu ứng dụng chưa khởi động hoặc cổng chưa được xác định. Trong test dùng cổng ngẫu nhiên, chỉ tạo URL sau khi test framework đã cung cấp cổng server.

### Cho rằng server mode tự kiểm tra database và dịch vụ bên ngoài

Server mode chỉ đi qua ứng dụng đang chạy. Mức độ tích hợp sâu hơn phụ thuộc bean và dependency mà môi trường test đã cấu hình. Mock repository vẫn là mock repository dù request đi qua HTTP thật.

### Cấu hình client rồi hiểu nhầm server-side boundary

Default header, client filter hoặc base URL thuộc cấu hình client. Chúng không thêm controller, filter hoặc application bean vào hạ tầng server-side đang được kiểm thử.

## Quy trình chọn ranh giới trước khi viết test

1. Viết rõ hành vi cần bảo vệ: controller mapping, cấu hình WebFlux, functional route hay HTTP server.
2. Xác định thành phần nào bắt buộc phải chạy thật để test có ý nghĩa; liệt kê thành phần có thể thay bằng mock hoặc fake.
3. Chọn bindToController, bindToApplicationContext, bindToRouterFunction hoặc bindToServer theo ranh giới đó.
4. Kiểm tra nguồn tạo hạ tầng: controller instance, ApplicationContext, RouterFunction hay địa chỉ server.
5. Cấu hình riêng phía client nếu cần header, filter, base URL hoặc timeout.
6. Gửi request bằng exchange() và xác nhận status, header, body theo hợp đồng HTTP.
7. Nếu cần kiểm tra một ranh giới khác, tạo test phù hợp với ranh giới đó thay vì giả định một chế độ đã bao phủ mọi lớp.

Một test chỉ cung cấp bằng chứng cho những thành phần thực sự nằm trên đường đi của request trong cấu hình test. Chọn đúng ranh giới giúp biết chính xác điều gì đã được kiểm tra, điều gì còn nằm ngoài phạm vi, và nên đặt một bài test khác ở đâu khi cần xác nhận thêm.
