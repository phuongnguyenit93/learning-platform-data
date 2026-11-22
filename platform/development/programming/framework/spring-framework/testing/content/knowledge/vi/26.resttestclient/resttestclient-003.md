# Bind tới controller, ApplicationContext hoặc router function MVC

`RestTestClient` là HTTP test client đồng bộ của Spring dành cho việc kiểm thử REST endpoint. Với Spring MVC, client có thể được bind trực tiếp vào controller, bind vào `WebApplicationContext` hoặc bind vào một MVC `RouterFunction`. Cả ba cách đều cho phép gửi request và kiểm tra status, header, body theo API gần với một HTTP client thực tế.

Điểm khác nhau nằm ở phạm vi hạ tầng MVC được đưa vào test:

- Bind vào controller tạo một môi trường MVC tập trung quanh controller được chỉ định.
- Bind vào ApplicationContext sử dụng cấu hình và các bean MVC trong context của ứng dụng.
- Bind vào router function kiểm thử trực tiếp tuyến xử lý được khai báo theo functional endpoint của Spring MVC.

Chọn đúng kiểu bind giúp test kiểm tra đúng ranh giới cần thiết, đồng thời tránh khởi tạo những thành phần không liên quan.

## 1. RestTestClient là gì?

`RestTestClient` cung cấp API request/response đồng bộ cho REST endpoint. Cách viết test quen thuộc:

~~~java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

Các bước chính:

1. Chọn HTTP method như `get()`, `post()`, `put()`, `patch()` hoặc `delete()`.
2. Cung cấp URI và các thành phần request như header, content type, query parameter và body.
3. Gọi `exchange()` để gửi request.
4. Kiểm tra status, header và body trong response.

Với Spring MVC, `RestTestClient` có thể chạy trên hạ tầng mock mà không mở cổng mạng. Điều này hữu ích cho kiểm thử controller và mapping HTTP nhanh. Nếu muốn kiểm tra giao tiếp qua HTTP connector và server đang chạy, dùng kiểu bind tới server thay vì bind mock.

`RestTestClient` thuộc Spring Framework 7.0 trở lên. Khi dự án đang dùng phiên bản Spring Framework cũ hơn, cần dùng công cụ tương ứng với phiên bản đó, chẳng hạn MockMvc hoặc WebTestClient với adapter phù hợp. Không thêm dependency hoặc đổi phiên bản chỉ để dùng ví dụ nếu dự án chưa nâng cấp.

## 2. Bind trực tiếp vào controller

`bindToController(...)` phù hợp khi muốn kiểm thử một hoặc một số controller cụ thể mà không cần khởi tạo toàn bộ `WebApplicationContext`.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    OrderResponse get(@PathVariable long id) {
        return orderService.findById(id);
    }
}
~~~

Tạo client bằng controller đã khởi tạo:

~~~java
OrderService orderService = mock(OrderService.class);
given(orderService.findById(42L))
        .willReturn(new OrderResponse(42L, "PAID"));

RestTestClient client = RestTestClient
        .bindToController(new OrderController(orderService))
        .build();

client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
~~~

Trong ví dụ, controller được tạo trực tiếp và nhận service mock qua constructor. Test tập trung vào cách Spring MVC ánh xạ request tới handler và tạo response.

### 2.1. Khi nào nên dùng bindToController?

Chọn cách này khi:

- Test chỉ cần một controller hoặc một nhóm controller nhỏ.
- Muốn kiểm tra mapping, binding, serialization và response của controller.
- Có thể cung cấp dependency trực tiếp qua constructor hoặc mock.
- Không cần các bean và cấu hình toàn cục khác trong application context.

Đây là lựa chọn gọn cho test tập trung. Tuy vậy, vì không nạp toàn bộ cấu hình MVC của ứng dụng, những thành phần như `@ControllerAdvice`, custom `Converter`, `Formatter`, `Validator`, message converter, interceptor hoặc filter có thể không giống cấu hình production nếu test không đăng ký chúng trong builder.

Ví dụ, nếu controller phụ thuộc exception advice dùng chung, test bind trực tiếp cần thêm advice vào cấu hình standalone nếu builder của phiên bản Spring đang dùng cung cấp tùy chọn đó. Nếu mục tiêu của test là xác nhận advice và các thành phần MVC đã được cấu hình toàn ứng dụng, bind vào context sẽ phù hợp hơn.

Không nên tự khởi tạo controller bằng `new` khi mục tiêu là kiểm tra quá trình Spring inject bean, proxy hoặc cấu hình bean. `bindToController` kiểm tra controller được cung cấp cho môi trường test; nó không chứng minh component scanning hoặc dependency injection của ứng dụng đã hoạt động.

## 3. Bind vào WebApplicationContext

`bindToApplicationContext(...)` dùng `WebApplicationContext` của ứng dụng. Spring MVC test infrastructure được thiết lập dựa trên các bean và cấu hình có trong context, vì vậy test có thể bao gồm nhiều thành phần hơn controller riêng lẻ.

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerRestTest {

    @Autowired
    WebApplicationContext context;

    @MockBean
    OrderService orderService;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }

    @Test
    void returnsOrderFromMvcApplicationContext() {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        client.get()
                .uri("/api/orders/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(42)
                .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

Ví dụ dùng `@WebMvcTest` để nạp slice MVC. Controller được chọn và các thành phần MVC liên quan được cấu hình theo test slice; service được thay bằng mock để test không cần truy cập tầng nghiệp vụ hoặc database thật.

Nếu cần cấu hình MVC đầy đủ hơn, có thể dùng context được tạo bởi `@SpringJUnitConfig`, `@ContextConfiguration` hoặc `@SpringBootTest`, tùy mục tiêu. `bindToApplicationContext(context)` không tự biến một context nhỏ thành context đầy đủ; phạm vi bean vẫn do cách khởi tạo context quyết định.

### 3.1. Những thành phần được kiểm tra cùng context

Khi bind vào context, test có thể xác nhận cách các thành phần MVC phối hợp:

- Controller được đăng ký trong context.
- `@ControllerAdvice` hoặc `@RestControllerAdvice` xử lý exception.
- `HttpMessageConverter` đọc request body và ghi response body.
- `ConversionService`, `Formatter` và `Validator` chuyển đổi/kiểm tra dữ liệu.
- Interceptor và cấu hình MVC đã được đăng ký trong context.
- Các cấu hình tích hợp như Spring Security, nếu test context có nạp chúng và request đi qua filter chain tương ứng.

Điều này khiến test gần cấu hình ứng dụng hơn nhưng cũng có thể làm context nặng hơn và phụ thuộc nhiều bean hơn. Nếu test thất bại do một thành phần không liên quan, hãy xem lại phạm vi context được nạp.

### 3.2. @WebMvcTest hay @SpringBootTest?

Hai cách này phục vụ mục đích khác nhau:

| Cách khởi tạo context | Phạm vi | Khi phù hợp |
|---|---|---|
| `@WebMvcTest` | MVC test slice, thường giới hạn controller và thành phần web cần thiết | Kiểm thử mapping, binding, validation, advice và response |
| `@SpringJUnitConfig` / `@ContextConfiguration` | Context test được khai báo rõ bằng cấu hình chỉ định | Test cấu hình MVC tùy chỉnh, không cần toàn bộ Boot |
| `@SpringBootTest` | Application context của Spring Boot với phạm vi rộng hơn | Kiểm tra tích hợp giữa nhiều bean và cấu hình ứng dụng |

`RestTestClient.bindToApplicationContext(context)` dùng context được inject; nó không quyết định annotation test nào phải dùng. Hãy chọn test context trước, rồi bind client vào context đó.

## 4. Bind vào router function của Spring MVC

Spring MVC hỗ trợ functional endpoint thông qua `RouterFunction`. Thay vì dùng annotation như `@GetMapping`, ứng dụng khai báo route và handler bằng API functional.

Một MVC router function dùng các kiểu trong package `org.springframework.web.servlet.function`, ví dụ `RouterFunction`, `ServerRequest` và `ServerResponse`. Không nhầm các kiểu này với router function của WebFlux trong package `org.springframework.web.reactive.function.server`.

Ví dụ khai báo route:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RequestPredicates.GET;
import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return route()
                .route(GET("/api/orders/{id}")
                                .and(accept(MediaType.APPLICATION_JSON)),
                        handler::getOrder)
                .build();
    }
}
~~~

Handler:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
class OrderHandler {

    private final OrderService orderService;

    OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    ServerResponse getOrder(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));
        OrderResponse response = orderService.findById(id);
        return ServerResponse.ok().body(response);
    }
}
~~~

Có thể bind trực tiếp vào router function:

~~~java
OrderService orderService = mock(OrderService.class);
OrderHandler handler = new OrderHandler(orderService);

RouterFunction<ServerResponse> routes = route()
        .GET("/api/orders/{id}", handler::getOrder)
        .build();

given(orderService.findById(42L))
        .willReturn(new OrderResponse(42L, "PAID"));

RestTestClient client = RestTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
~~~

Test này kiểm tra route predicate, path variable, handler và cách tạo response trong MVC functional endpoint. Vì router function được cung cấp trực tiếp, test có thể cô lập route cần kiểm tra mà không nạp toàn bộ application context.

### 4.1. Khi nào nên dùng bindToRouterFunction?

Chọn cách này khi:

- Endpoint được khai báo bằng Spring MVC functional routing.
- Muốn kiểm tra route predicate và handler function.
- Muốn xác nhận path, method, header predicate và response của router.
- Có thể cung cấp handler hoặc dependency cần thiết trực tiếp.

Nếu router function được đăng ký như một bean trong application context và phụ thuộc nhiều cấu hình chung, bind vào context sẽ kiểm tra cả việc đăng ký bean và cấu hình ứng dụng. Bind trực tiếp vào router function tập trung hơn, nhưng không chứng minh route đã được component/configuration của ứng dụng đăng ký đúng.

## 5. So sánh ba cách bind

| Tiêu chí | Controller | ApplicationContext | Router function |
|---|---|---|---|
| Đầu vào của builder | Controller instance | `WebApplicationContext` | MVC `RouterFunction` |
| Phạm vi | Một hoặc một nhóm controller được chỉ định | Các bean/cấu hình MVC trong context | Route function được cung cấp |
| Phù hợp với | Annotation-based controller | Kiểm thử tích hợp cấu hình MVC | Functional endpoint |
| Dependency | Thường truyền trực tiếp vào controller | Được lấy từ context | Thường được cung cấp qua handler hoặc context |
| Advice/converter/interceptor | Cần đăng ký vào cấu hình test nếu muốn dùng | Theo cấu hình context | Cần cấu hình hoặc bind context nếu phụ thuộc thành phần chung |
| Kiểm tra component scanning/bean registration | Không | Có trong phạm vi context | Không khi bind route instance trực tiếp |
| Chi phí khởi tạo | Thường thấp | Phụ thuộc kích thước context | Thường thấp |

Quy tắc lựa chọn:

- Controller annotation-based, cần test tập trung: `bindToController`.
- Cần xác nhận các bean MVC dùng chung: `bindToApplicationContext`.
- Endpoint dùng functional routing của Spring MVC: `bindToRouterFunction`.

## 6. Request và response giống nhau ở cả ba cách bind

Sau khi tạo client, API gửi request và assertion về cơ bản giống nhau. Ví dụ POST JSON:

~~~java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "web")
        .body("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 2
                }
                """)
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().exists(HttpHeaders.LOCATION)
        .expectBody()
        .jsonPath("$.sku").isEqualTo("COFFEE-01");
~~~

Test nên mô tả dữ liệu theo hợp đồng HTTP mà client thực sự gửi:

- Dùng đúng method và path.
- Đặt query parameter, path variable và header đúng vị trí.
- Khai báo `Content-Type` cho body và `Accept` cho response.
- Gửi JSON hoặc form data đúng định dạng.
- Kiểm tra status, response header và body.

Không nên biến một test bind vào controller thành test gọi trực tiếp method Java. Mục đích của RestTestClient là kiểm tra đường đi HTTP qua MVC test infrastructure.

## 7. Kết hợp với cấu hình MVC và exception handling

Giả sử ứng dụng có `@RestControllerAdvice` ánh xạ lỗi không tìm thấy đơn hàng:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", ex.getMessage()));
    }
}
~~~

Khi kiểm tra advice được cấu hình trong ứng dụng, bind client vào `WebApplicationContext` để test đi qua cấu hình đó:

~~~java
client.get()
        .uri("/api/orders/999")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
~~~

Nếu bind trực tiếp vào controller, cần bảo đảm advice được đăng ký trong cấu hình test. Nếu không, test có thể nhận response lỗi mặc định khác với ứng dụng thật. Đây là lý do nên chọn phạm vi bind dựa trên thành phần mà test cần chứng minh.

Tương tự, custom formatter, validator hoặc message converter có thể làm kết quả request binding khác nhau. Nếu test cần xác nhận converter dùng chung, hãy dùng context chứa converter đó hoặc đăng ký nó rõ ràng trong cấu hình test.

## 8. Phân biệt MVC router function và WebFlux router function

Tên `RouterFunction` xuất hiện ở cả Spring MVC và Spring WebFlux nhưng hai loại không dùng chung request/response type:

| Spring MVC | Spring WebFlux |
|---|---|
| `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| `ServerRequest` và `ServerResponse` của Servlet MVC | `ServerRequest` và `ServerResponse` reactive |
| Xử lý theo mô hình Servlet và API đồng bộ | Xử lý reactive với `Mono`/`Flux` |
| Có thể kiểm thử bằng `RestTestClient` | Thường kiểm thử bằng `WebTestClient` |

Không truyền WebFlux `RouterFunction` vào `RestTestClient.bindToRouterFunction(...)` của MVC. Nếu ứng dụng dùng WebFlux functional endpoint, chọn WebTestClient và API bind tương ứng.

## 9. Khi nào nên bind tới server thật?

Ba kiểu bind trong bài tập trung vào mock MVC infrastructure. Chúng không mở cổng mạng và không kiểm tra toàn bộ hành vi của Servlet container, connector hoặc proxy.

Khi cần kiểm tra giao tiếp HTTP thực tế, có thể chạy ứng dụng trên cổng ngẫu nhiên:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    int port;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void servesOrderOverHttp() {
        client.get()
                .uri("/api/orders/42")
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Test kiểu này phù hợp khi cần kiểm tra server connector, cấu hình cổng, filter ở server, serialization qua HTTP connector hoặc tương tác với client HTTP thật. Chi phí khởi động cao hơn test mock và thường cần thêm thời gian để ứng dụng sẵn sàng.

Không cần dùng server thật cho mọi test controller. Dùng mock binding cho phần lớn test MVC nhanh; thêm một số integration test có mục tiêu rõ ràng cho hành vi chỉ xuất hiện khi server thực sự chạy.

## 10. Những lỗi thường gặp khi chọn cách bind

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Controller test không thấy custom advice | Bind trực tiếp controller nhưng chưa đăng ký advice | Đăng ký advice trong test hoặc bind vào context |
| Custom converter không chạy | Test không dùng context/cấu hình có converter | Bind vào `WebApplicationContext` hoặc đăng ký converter |
| Controller cần dependency nhưng test không khởi tạo được | Tạo controller trực tiếp mà thiếu dependency | Truyền mock/stub qua constructor hoặc dùng context |
| Route functional trả 404 trong test | Bind nhầm router function hoặc route predicate không khớp | Dùng MVC `RouterFunction` và kiểm tra method/path/header |
| Route có trong ứng dụng nhưng test bind router riêng không tìm thấy | Test chỉ cung cấp một router instance khác | Lấy router bean từ context hoặc bind toàn context |
| Dùng RestTestClient cho WebFlux route | Nhầm API MVC và WebFlux | Dùng WebTestClient cho WebFlux |
| Test mong đợi hành vi Servlet container thật nhưng dùng mock binding | Mock infrastructure không mở socket/không chạy connector thật | Bind tới server đang chạy |
| Test context khởi tạo quá nặng | Dùng application context toàn phần cho test chỉ cần một controller | Cân nhắc `bindToController` hoặc MVC test slice |

## 11. Quy trình chọn và tạo RestTestClient

Trước khi viết test, xác định endpoint thuộc kiểu nào:

1. Nếu endpoint là controller annotation-based và chỉ cần kiểm tra handler, tạo controller cùng dependency cần thiết rồi dùng `bindToController`.
2. Nếu cần kiểm tra advice, converter, validator, interceptor hoặc bean registration trong ứng dụng, khởi tạo `WebApplicationContext` phù hợp rồi dùng `bindToApplicationContext`.
3. Nếu endpoint được khai báo bằng functional routing của Spring MVC, tạo hoặc lấy MVC `RouterFunction` rồi dùng `bindToRouterFunction`.
4. Nếu cần xác nhận connector và giao tiếp HTTP thật, chạy server và dùng `bindToServer`.
5. Sau khi bind, viết request theo hợp đồng HTTP và assertion cho status, header, body.

Không có kiểu bind nào luôn tốt nhất. Chất lượng test phụ thuộc việc phạm vi hạ tầng được khởi tạo có khớp với hành vi cần xác nhận hay không. Bind quá hẹp có thể bỏ sót cấu hình MVC dùng chung; bind quá rộng làm test chậm và khó xác định nguyên nhân thất bại.

Khi chọn giữa controller, ApplicationContext và router function, hãy bắt đầu từ entry point thực tế của endpoint. Annotation-based controller nên được test qua controller hoặc context; functional endpoint nên được test qua MVC router function hoặc context đã đăng ký router đó. Cách bind rõ ràng giúp test thể hiện đúng cấu trúc ứng dụng và giữ được ý nghĩa khi cấu hình MVC thay đổi.
