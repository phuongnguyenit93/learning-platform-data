# WebTestClient để kiểm thử API phản ứng

## 1. Vì sao WebFlux cần kiểm thử theo hợp đồng HTTP *và* dòng dữ liệu?

Unit test Reactor chưa bảo đảm REST API đúng: client còn quan sát **URI, method, status, header, JSON, quyền và các sự kiện theo thời gian**. Lỗi binding, serialization hay security filter có thể nằm ngoài service test.

`WebTestClient` thuộc Spring Test, dùng **gửi request và kiểm tra HTTP response**, từ JSON hữu hạn tới SSE dài hạn; có chế độ mock không mở socket và chế độ gọi server thật.

~~~text
  WebTestClient
       |
       +-- bindToController(...)        --> mock server, controller nhỏ
       +-- bindToApplicationContext(...) --> mock server, WebFlux context
       +-- bindToServer().baseUrl(...)  --> HTTP server thật

  HTTP status/header/body/stream   +   Reactor StepVerifier
             |                                |
     hợp đồng phía client          signals / completion / cancellation
~~~

Bài thuộc chương **Spring WebFlux** của **INTEGRATION_API_REST**, áp dụng thiết kế REST resource/URI/method/status và hợp đồng dữ liệu, phân trang, cache, idempotency, bảo mật. Trọng tâm là **kiểm thử API**, không dạy lại Reactor.

Bạn sẽ dùng `@WebFluxTest`/`@SpringBootTest`, kiểm tra JSON/Problem Details, security, SSE, timeout và hủy subscription, tránh test quá yếu hoặc `block()` sai chỗ.

## 2. WebTestClient thực sự chạy đến đâu?

| Cách tạo client | Phạm vi | Dùng khi nào | Giới hạn |
|---|---|---|---|
| `WebTestClient.bindToController(controller)` | Controller + WebFlux infrastructure tối thiểu | Binding, serializer, status của một handler | Không tự bao gồm toàn bộ filter/security/config ứng dụng |
| `WebTestClient.bindToRouterFunction(router)` | Functional routing với handler phù hợp | Kiểm tra `RouterFunction`, predicate, handler | Phụ thuộc những filter/codec được đăng ký cho test |
| `WebTestClient.bindToApplicationContext(context)` | WebFlux `ApplicationContext`, mock request/response | Mapping, advice, converter và filters trong context | Không mở socket; không kiểm tra cấu hình network/server |
| `@WebFluxTest` + injected `WebTestClient` | MVC-like slice của WebFlux (controller-focused) | Test nhanh controller + JSON + advice + security tùy cấu hình | Service/repository thường cần mock; không thay integration test |
| `bindToServer()` hoặc `@SpringBootTest(RANDOM_PORT)` | HTTP server thực | Filters, proxy behavior gần thực, serialization, security integration | Chậm hơn; dữ liệu/port/dependency cần cô lập |

**Phân biệt:** `WebTestClient` không chỉ dùng cho WebFlux controller. Client này cũng có thể test server HTTP khác nếu dùng `bindToServer`. Ngược lại, `@WebMvcTest` và `MockMvc` là bộ công cụ cho **Spring MVC**, không nên hoán đổi với `@WebFluxTest` để “giữ nguyên test” khi ứng dụng đã chuyển stack.

### 2.1. Maven/Gradle cho ví dụ

Ví dụ dùng **Java 17+, Spring Boot 3.x, WebFlux**, phiên bản dependencies theo Boot BOM:

~~~xml
<!-- Trích đoạn dependencies trong pom.xml có Spring Boot parent/BOM -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
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
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

~~~groovy
// build.gradle (phiên bản do Spring Boot dependency management quản lý)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Với JWT thêm `spring-boot-starter-security` và `spring-boot-starter-oauth2-resource-server`. Test fake token **không thay thế** xác minh JWT runtime.

### 2.2. Hình thức một HTTP test

~~~java
client.get()
    .uri("/v1/orders/o-42")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.id").isEqualTo("o-42");
~~~

`exchange()` thực thi request. Đừng chỉ kiểm tra `isOk()`: schema, header hoặc tenant sai vẫn có thể trả 200.

## 3. Ứng dụng mẫu: truy vấn đơn và dòng sự kiện SSE

Giả sử một API có ba endpoint:

~~~http
GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json

GET /v1/orders?status=SUBMITTED&limit=20 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json

GET /v1/orders/events HTTP/1.1
Authorization: Bearer <access-token>
Accept: text/event-stream
~~~

Khi đọc chi tiết, nếu đơn tồn tại và người gọi có quyền, API trả `200` cùng JSON. Khi đọc collection, `Flux<OrderView>` được mã hóa thành JSON array nếu response là `application/json`. Khi đăng ký sự kiện, API phát `text/event-stream` có thể **không bao giờ tự kết thúc**.

### 3.1. DTO và service phản ứng

~~~java
record OrderView(String id, String status, int itemCount) {}
record OrderEvent(String orderId, String newStatus) {}

interface OrderQueryService {
    Mono<OrderView> findVisible(String actorId, String orderId);
    Flux<OrderView> findVisible(String actorId, String status, int limit);
    Flux<OrderEvent> eventsVisibleTo(String actorId);
}
~~~

`actorId` phải đến từ principal đã xác thực, không phải `?actorId=...`. Service/repository phải lọc tenant/owner; `Mono.empty()` từ truy vấn scoped có thể thành 404 trung tính.

### 3.2. Annotated WebFlux controller

~~~java
@RestController
@RequestMapping("/v1/orders")
class ReactiveOrderController {
    private final OrderQueryService service;

    ReactiveOrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {
        return service.findVisible(jwt.getSubject(), orderId)
            .map(ResponseEntity::ok)
            .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
    }

    @GetMapping
    Flux<OrderView> list(
            @RequestParam(name = "status", required = false) String status,
            @RequestParam(name = "limit", defaultValue = "20") int limit,
            @AuthenticationPrincipal Jwt jwt) {
        if (limit < 1 || limit > 100) {
            throw new InvalidLimitException();
        }
        return service.findVisible(jwt.getSubject(), status, limit);
    }

    @GetMapping(path = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<OrderEvent>> events(
            @AuthenticationPrincipal Jwt jwt) {
        return service.eventsVisibleTo(jwt.getSubject())
            .map(event -> ServerSentEvent.<OrderEvent>builder(event)
                .event("order-updated")
                .build());
    }
}
~~~

Mã là **khung minh họa**: cần import, hiện thực service/exception và security; `Jwt` phải được resource server xác thực. Không dùng Authorization giả trong test không có security filter để kết luận đã xác thực.

Lỗi `limit` → 400; resource không thấy → 404; `Flux.empty()` cho collection → **200 với `[]`**; SSE cần xử lý hủy kết nối. Quyền truy cập được xử lý riêng ở Mục 9.

## 4. Mức 1: bindToController và bindToRouterFunction

Hai chế độ này hữu ích khi muốn cô lập một controller hoặc functional route khỏi khởi động toàn ứng dụng. Test chạy qua hạ tầng WebFlux mock, **không cần port HTTP thật**.

### 4.1. Controller đơn giản không phụ thuộc bảo mật

~~~java
@RestController
class GreetingController {
    @GetMapping("/v1/greetings/{name}")
    Mono<Map<String, String>> greet(@PathVariable String name) {
        return Mono.just(Map.of("message", "Hello " + name));
    }
}

class GreetingControllerTest {
    WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();

    @Test
    void bindsPathAndSerializesMono() {
        client.get().uri("/v1/greetings/Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.message").isEqualTo("Hello Lan");
    }
}
~~~

`bindToController` **không tự mang theo toàn bộ security, advice, codec tùy biến** của ứng dụng. Muốn kiểm chứng các lớp này, đăng ký chúng cho test hoặc dùng application context.

### 4.2. Functional routing

WebFlux hỗ trợ `RouterFunction` bên cạnh annotation controllers. Test một route nhỏ:

~~~java
RouterFunction<ServerResponse> route = RouterFunctions.route(
    RequestPredicates.GET("/v1/health"),
    request -> ServerResponse.ok().bodyValue(Map.of("status", "UP"))
);

WebTestClient client = WebTestClient
    .bindToRouterFunction(route)
    .build();

client.get().uri("/v1/health")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.status").isEqualTo("UP");
~~~

Route có filter/authorization riêng phải đăng ký chúng trong test; test bỏ filter dễ **pass giả**.

## 5. Mức 2: @WebFluxTest cho controller và HTTP contract

`@WebFluxTest` là **test slice**: dựng phần WebFlux liên quan đến controller, message converters, validation và một số thành phần web; thông thường **không tải toàn bộ repository/service**. Mock dependency để test deterministic. Ví dụ dùng Spring Boot **3.5.x** với `@MockitoBean` (Spring Test hiện đại); các dự án Boot cũ thường dùng `@MockBean` theo phiên bản tương ứng.

### 5.1. Test GET với principal đã được mô phỏng

~~~java
@WebFluxTest(ReactiveOrderController.class)
@Import(ReactiveApiSecurityConfig.class)
class ReactiveOrderControllerTest {
    @Autowired WebTestClient client;
    @MockitoBean OrderQueryService service;

    @Test
    void getOrderReturnsJsonForAuthenticatedActor() {
        when(service.findVisible("u-17", "o-42"))
            .thenReturn(Mono.just(
                new OrderView("o-42", "SUBMITTED", 2)));

        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("u-17")))
            .get().uri("/v1/orders/o-42")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("o-42")
            .jsonPath("$.status").isEqualTo("SUBMITTED")
            .jsonPath("$.itemCount").isEqualTo(2);

        verify(service).findVisible("u-17", "o-42");
    }
}
~~~

`mockJwt()` từ `spring-security-test` dành cho mock reactive request; `ReactiveApiSecurityConfig` là cấu hình test ở Mục 9. Khi tự dựng client từ context, gắn `.apply(springSecurity())`; **mockJwt không có giá trị chứng minh bảo mật** nếu filter bị bỏ qua.

### 5.2. 404 khác JSON null

Khi service không thấy đơn trong scope được phép:

~~~java
@Test
void invisibleOrderDoesNotLeakItsExistence() {
    when(service.findVisible("u-17", "o-foreign"))
        .thenReturn(Mono.empty());

    client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("u-17")))
        .get().uri("/v1/orders/o-foreign")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody().isEmpty();
}
~~~

`Mono.empty()` mock chỉ chứng minh mapping thành 404. Cần integration test service/repository với hai tenant để xác nhận không rò BOLA/IDOR.

### 5.3. Collection, query binding và status lỗi

~~~java
@Test
void listBindsQueryAndSerializesFluxAsArray() {
    when(service.findVisible("u-17", "SUBMITTED", 2))
        .thenReturn(Flux.just(
            new OrderView("o-1", "SUBMITTED", 1),
            new OrderView("o-2", "SUBMITTED", 3)));

    client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("u-17")))
        .get()
        .uri(uri -> uri.path("/v1/orders")
            .queryParam("status", "SUBMITTED")
            .queryParam("limit", 2)
            .build())
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].id").isEqualTo("o-1")
        .jsonPath("$[1].id").isEqualTo("o-2")
        .jsonPath("$.length()").isEqualTo(2);

    verify(service).findVisible("u-17", "SUBMITTED", 2);
}
~~~

Nếu JSONPath `$.length()` không được hỗ trợ, dùng `expectBodyList(OrderView.class).hasSize(2)`. Chỉ assert thứ tự khi hợp đồng cam kết sort; pagination cần sort ổn định và test cursor.

~~~text
GET /v1/orders?limit=abc
→ Spring WebFlux không chuyển "abc" thành int
→ 400 Bad Request; không gọi service
~~~

Test conversion lỗi:

~~~java
@Test
void invalidLimitIsRejectedBeforeService() {
    client.mutateWith(mockJwt())
        .get().uri("/v1/orders?limit=abc")
        .exchange()
        .expectStatus().isBadRequest();

    verifyNoInteractions(service);
}
~~~

Nếu `@ControllerAdvice` có xử lý lỗi `InvalidLimitException` thành 400 với Problem Details, hãy `@Import` advice trong test slice; khác biệt giữa binding lỗi `limit=abc` và domain validation `limit=1000` nên được kiểm tra riêng. Test không được im lặng dùng response mặc định của framework nếu hợp đồng công bố body lỗi cụ thể.

## 6. Mức 3: bindToApplicationContext và server thực

### 6.1. bindToApplicationContext

Khi muốn có message codecs, filters, exception handlers và bean wiring của WebFlux context mà vẫn không mở port:

~~~java
@Autowired ApplicationContext context;

WebTestClient client = WebTestClient
    .bindToApplicationContext(context)
    .apply(springSecurity()) // Spring Security Test configurer
    .configureClient()
    .responseTimeout(Duration.ofSeconds(4))
    .build();
~~~

`.apply(springSecurity())` cần WebFlux security config trong context. Test slice nhanh nhưng có thể thiếu filter/bean khác; muốn toàn cấu hình dùng `@SpringBootTest`.

### 6.2. SpringBootTest với RANDOM_PORT

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveOrderHttpIT {
    @Autowired WebTestClient client;

    @Test
    void unauthenticatedRequestIsRejected() {
        client.get().uri("/v1/orders/o-42")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Trên cấu hình WebFlux tương thích, `@AutoConfigureWebTestClient` cung cấp client kết nối đến server theo test setup; kiểm tra host/port và autoconfiguration của **đúng Spring Boot version** nếu custom network test. Ở chế độ **RANDOM_PORT**, request đi qua HTTP server thực, nên `mockJwt()` vốn dành cho mock server không đại diện cho request HTTP đã ký. Để test 200/403 trên server thật, cung cấp bearer token hợp lệ cho test resource server hoặc dùng auth backend/test issuer có kiểm soát; không đưa token production vào test.

Test server thật nên dùng dependency cô lập: database test, broker fake, container có vòng đời rõ, hoặc contract stub khi thích hợp. Nếu repository/hạ tầng chưa sẵn sàng, dùng `@WebFluxTest` cho controller và integration test riêng cho persistence, không biến bài test HTTP thành unit test với tất cả thành phần thật không thể khởi động.

## 7. Kiểm thử response lỗi và Problem Details

Spring WebFlux có đường xử lý input khác Spring MVC Servlet. Ví dụ:

- `@RequestParam int limit` với `limit=abc` có thể dẫn tới `ServerWebInputException` vì conversion thất bại.
- `@Valid @RequestBody Mono<CreateOrderRequest>` có dữ liệu không hợp lệ có thể dẫn tới `WebExchangeBindException`.
- JSON hỏng có thể gây lỗi decoder/message reading khác trong chuỗi `ServerWebInputException`.
- Lỗi domain `InvalidLimitException` hoặc `OrderConflictException` do ứng dụng định nghĩa phải được ánh xạ bằng handler phù hợp.

**Không bê nguyên danh sách exception của Spring MVC vào WebFlux** rồi tin rằng mọi test sẽ chạy qua cùng handler. Cùng HTTP 400 nhưng nguyên nhân và đường xử lý khác; cần test theo **status, content type và application error code**, không phụ thuộc message nội bộ của framework.

### 7.1. Advice trả lỗi HTTP có cấu trúc

~~~java
@RestControllerAdvice
class ReactiveApiErrors {
    @ExceptionHandler(InvalidLimitException.class)
    ResponseEntity<ProblemDetail> invalidLimit() {
        ProblemDetail detail = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "limit phải nằm trong khoảng 1 đến 100.");
        detail.setType(URI.create(
            "https://api.example.com/problems/invalid-limit"));
        detail.setProperty("code", "INVALID_LIMIT");

        return ResponseEntity.badRequest()
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(detail);
    }
}
~~~

Đây là một handler tối giản, **chưa** xử lý tất cả lỗi binding/decoder/security. Trong `@WebFluxTest` cần đăng ký advice (nếu slice chưa tự chọn) để test đúng response production; trong `bindToController` có thể khai báo `.controllerAdvice(new ReactiveApiErrors())` theo API test builder. Với ứng dụng yêu cầu Problem Details thống nhất, cần bổ sung handler và cấu hình Spring Security tương ứng.

### 7.2. Test status, content type và error code

~~~java
@Test
void outOfRangeLimitReturnsProblemDetail() {
    client.mutateWith(mockJwt())
        .get().uri("/v1/orders?limit=1000")
        .exchange()
        .expectStatus().isBadRequest()
        .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
        .expectBody()
        .jsonPath("$.status").isEqualTo(400)
        .jsonPath("$.code").isEqualTo("INVALID_LIMIT");

    verifyNoInteractions(service);
}
~~~

Đối với lỗi nghiệp vụ có dữ liệu hợp lệ, ví dụ `POST /v1/orders` khi giỏ đã checkout, test `409 Conflict` cùng mã `ORDER_ALREADY_SUBMITTED`; nếu client gửi `If-Match` cũ, test `412 Precondition Failed` theo HTTP precondition, không thay bằng 409 tùy tiện. Thực thi đúng phải chứng minh **không có side effect**, không chỉ body JSON trông giống lỗi.

## 8. Luồng SSE: dùng StepVerifier thay vì chờ body kết thúc

Với SSE, response có `Content-Type: text/event-stream` và có thể phát nhiều sự kiện vô hạn. Gọi `expectBodyList(...).hasSize(n)` rồi chờ luồng kết thúc sẽ **treo** nếu publisher không hoàn thành. Hãy lấy `FluxExchangeResult<T>` và kiểm tra các signal quan trọng bằng `StepVerifier`, có **thời hạn tối đa** và **cancel**.

### 8.1. Luồng sự kiện mẫu

Giả sử service phát một event rồi giữ kết nối để chờ event mới:

~~~java
when(service.eventsVisibleTo("u-17"))
    .thenReturn(Flux.just(new OrderEvent("o-42", "PAID"))
        .concatWith(Flux.never()));
~~~

### 8.2. Test event, payload và chủ động hủy subscription

~~~java
@Test
void sseSendsExpectedEventAndCanBeCancelled() {
    when(service.eventsVisibleTo("u-17"))
        .thenReturn(Flux.just(new OrderEvent("o-42", "PAID"))
            .concatWith(Flux.never()));

    FluxExchangeResult<ServerSentEvent<OrderEvent>> result =
        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("u-17")))
            .get().uri("/v1/orders/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(
                new ParameterizedTypeReference<ServerSentEvent<OrderEvent>>() {}
            );

    StepVerifier.create(result.getResponseBody())
        .assertNext(event -> {
            assertEquals("order-updated", event.event());
            assertEquals("o-42", event.data().orderId());
            assertEquals("PAID", event.data().newStatus());
        })
        .thenCancel()
        .verify(Duration.ofSeconds(5));
}
~~~

Ở đây `ServerSentEvent<OrderEvent>` giữ metadata `event` và `data`. Cần cùng codec/JSON config ở test và production; nếu app chỉ phát chuỗi `data:...`, test bằng kiểu tương ứng thay vì ép object. `returnResult(...)` **không bắt buộc stream hoàn thành**; `StepVerifier` lấy phần đầu rồi chủ động cancel.

### 8.3. Test cancellation chạm tới upstream

~~~java
AtomicBoolean cancelled = new AtomicBoolean();
Flux<OrderEvent> source = Flux
    .just(new OrderEvent("o-42", "PAID"))
    .concatWith(Flux.never())
    .doOnCancel(() -> cancelled.set(true));

when(service.eventsVisibleTo("u-17")).thenReturn(source);
// Chạy request SSE và StepVerifier.thenCancel() như trên.
// Sau verify, assertTrue(cancelled.get()) khi test đã quan sát
// tín hiệu hủy tới upstream trong setup có kiểm soát.
~~~

Test cancellation chứng minh server không giữ subscription vô hạn sau khi client rời đi; trong môi trường network thật còn cần kiểm chứng cleanup subscription khi TCP disconnect, proxy timeout và shutdown. Nếu endpoint gửi heartbeat, test nên chấp nhận heartbeat hợp lệ mà vẫn xác nhận event nghiệp vụ đúng thứ tự.

### 8.4. Timeout và backpressure

`responseTimeout` của `WebTestClient` giúp tránh chờ mãi để nhận response; `StepVerifier.verify(Duration)` giúp tránh chờ vô hạn cho các signal tiếp theo. **Hai timeout không cùng ý nghĩa**. Reactive Streams dùng demand/backpressure ở tầng publisher, nhưng SSE chạy trên HTTP và có buffering/flush; một unit test `request(1)` không tự chứng minh mọi proxy/mobile client đều không bị tràn bộ nhớ.

Khi cần test chuỗi bị trì hoãn, `StepVerifier.withVirtualTime(...)` hữu ích **ở mức publisher/service thuần Reactor**:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(2))
    .expectSubscription()
    .thenAwait(Duration.ofHours(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Tạo publisher **trong supplier** để scheduler ảo có hiệu lực. Không giả định virtual time có thể tua thời gian của **socket HTTP thật, database hoặc external server**; với WebTestClient streaming qua HTTP cần test timeout thực tế có giới hạn và điều khiển clock của các component sở hữu lịch nếu cần.

## 9. Bảo mật: test filter, quyền và cách ly tenant

Một HTTP test trả `200` không chứng minh đã kiểm tra quyền. Ở ứng dụng phản ứng, Spring Security dùng `SecurityWebFilterChain`; cấu hình test cần chứa các filter thực sự muốn kiểm thử. Một cấu hình **tối thiểu cho test slice**:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveApiSecurityConfig {
    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/v1/orders/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Cấu hình này chỉ yêu cầu đăng nhập cho đường dẫn đơn hàng, **chưa định nghĩa JWT decoder hay quyền chi tiết**, nên chỉ là ví dụ để `mockJwt()` test filter. Production phải thêm resource server JWT verification, audience/issuer validation, quyền đọc/sửa và cách ly tenant; không lấy config test tối giản để thay security thật.

### 9.1. Những ca cần chạy

- **401:** không có authentication, endpoint yêu cầu đăng nhập. Nếu bật resource server trong integration test, kiểm tra token rỗng/hết hạn/sai chữ ký.
- **403:** principal hợp lệ nhưng không có authority theo policy; test `hasAuthority("SCOPE_orders.write")` cho endpoint ghi hoặc method security. Đừng chỉ mock service trả 403 mà bỏ kiểm tra filter/authorization thật.
- **404 trung tính:** resource thuộc tenant khác không được phép tiết lộ; kiểm tra JSON/body không chứa ID, tenant hay trạng thái ngoại phạm vi.
- **200:** actor có quyền xem đúng resource; bảo đảm server chỉ truyền dữ liệu của actor/tenant đó.

`mockJwt()` đưa principal vào **mock request** của Spring Security Test, không tự kiểm tra token bằng khóa công khai. Khi cần xác nhận **JWT runtime**, phải dùng test HTTP thực hoặc filter integration test với `ReactiveJwtDecoder` được kiểm soát; tuyệt đối không dùng token production. Test cookie/session authentication còn phải kiểm tra CSRF với POST/PATCH/DELETE, không tự tắt CSRF vì WebFlux là reactive.

## 10. Đúng reactive: subscription, blocking và lỗi xảy ra muộn

### 10.1. Controller không nên gọi block()

Sai:

~~~java
@GetMapping("/v1/orders/{id}")
OrderView get(@PathVariable String id) {
    return service.findById(id).block(); // Có thể chặn event-loop.
}
~~~

Đúng: trả `Mono<OrderView>` hoặc `Mono<ResponseEntity<OrderView>>`, để WebFlux subscribe/ghi response theo chuỗi reactive. `WebTestClient` test status/body giúp kiểm tra output, nhưng **không tự chứng minh** mọi repository call là non-blocking. Muốn phát hiện blocking trong reactive thread, có thể bổ sung BlockHound trong môi trường test được cấu hình tương thích, đo event-loop latency, và integration test ở tải phù hợp; không dựa vào một unit test 200 để suy kết luận về hiệu năng.

### 10.2. Đừng giấu lỗi xảy ra sau khi đã commit HTTP response

Với response streaming, server có thể đã phát `200 OK` rồi publisher mới lỗi. Khi header đã gửi, không thể đổi status thành 500 một cách tin cậy. Test stream cần assert **onError**, thứ tự sự kiện, cleanup và policy retry/notification riêng; nếu API dùng SSE, có thể phát event lỗi theo hợp đồng thay vì giả định status cuối luôn phản ánh toàn bộ outcome.

`StepVerifier` ở mức service là nơi kiểm tra `onNext`, `onError`, `onComplete` và cancellation. `WebTestClient` ở mức HTTP kiểm tra encoding, headers, security và dữ liệu client thực nhận. **Kết hợp hai lớp**, không dùng lớp này thay thế hoàn toàn lớp kia.

## 11. Ma trận kiểm thử tối thiểu

| Ca | Request/tình huống | Assertion quan trọng |
|---|---|---|
| W01 | GET đơn hợp lệ | `200` + JSON schema/ID/status đúng |
| W02 | GET đơn không tồn tại/không được phép thấy | `404`, không lộ metadata |
| W03 | GET collection có `status`/`limit` | Bind query đúng, JSON array, giới hạn/định dạng |
| W04 | Query `limit=abc` | `400` conversion, service không chạy |
| W05 | `limit=1000` | `400` Problem Details và error code |
| W06 | Resource không có credential | `401` qua security chain |
| W07 | Principal thiếu authority | `403` (test cả filter và policy) |
| W08 | Principal tenant B yêu cầu đơn tenant A | Không đọc được dữ liệu A; không rò ID |
| W09 | GET SSE nhận event hợp lệ | `text/event-stream` + event/data được decode |
| W10 | SSE không kết thúc | Test chỉ lấy event cần thiết rồi `thenCancel` với timeout |
| W11 | SSE publisher lỗi sau event | Test signal/error và không kỳ vọng đổi HTTP status đã commit |
| W12 | Client timeout/disconnect | Upstream được hủy hoặc cleanup theo contract |
| W13 | Service `Mono.empty()` vs `Flux.empty()` | Detail 404; collection 200 + array rỗng |
| W14 | POST idempotent/retry nếu API hỗ trợ | Không tạo hai side effect, status/body theo hợp đồng |

**Kiểm thử bảo mật và đồng thời cần dữ liệu thật ở tầng phù hợp.** Mock controller chỉ chứng minh cách HTTP mapping phản ứng với kết quả mock; test repository/service phải xác minh tenant-scoped query, optimistic lock, transaction và bất biến nghiệp vụ. Khi test đồng thời, dùng môi trường DB gần production thay vì suy ra từ test với `Flux.just(...)`.

## 12. Bài tập áp dụng và checklist

**Đề bài:** xây API:

~~~text
GET /v1/jobs/{id}          -> Mono<JobView>
GET /v1/jobs/{id}/events   -> Flux<ServerSentEvent<JobEvent>>
~~~

Job thuộc tenant của người tạo. Endpoint trạng thái trả 404 nếu không thấy; SSE có heartbeat, có thể chạy vô hạn. Hãy chọn cấp độ test và nêu các assertions cần thiết.

**Lời giải gợi ý:** dùng `@WebFluxTest` + `@MockitoBean` để kiểm tra GET `200`, JSON của job và `404` cho `Mono.empty()`; đưa `mockJwt()` vào mock security chain để kiểm tra principal, nhưng test tenant isolation với service/repository thực. Với SSE dùng `WebTestClient` nhận `text/event-stream`, `returnResult(ParameterizedTypeReference<ServerSentEvent<JobEvent>>)` và `StepVerifier` xác nhận event, heartbeat và `thenCancel().verify(Duration...)`. Thêm test 401/403, ngắt kết nối và lỗi stream. Dùng `@SpringBootTest(RANDOM_PORT)` cho vòng kiểm chứng security/codec qua HTTP thật; không dùng virtual time để giả lập socket.

**Checklist trước khi merge:**

- [ ] Chọn đúng `bindToController`, `@WebFluxTest`, `bindToApplicationContext` hoặc `RANDOM_PORT` theo ranh giới cần kiểm chứng.
- [ ] Kiểm tra **status, header, JSON field/schema**, không chỉ `isOk()`.
- [ ] Kiểm tra mapping `Mono.empty()`/`Flux.empty()` và lỗi binding/domain rõ nghĩa.
- [ ] SSE test có **timeout và cancel**, không chờ một stream vô hạn kết thúc.
- [ ] Security filter được gắn trong test; có ca 401/403/cross-tenant, không chỉ `mockJwt()`.
- [ ] Test blocking/late error/cancellation ở lớp reactive thích hợp.
- [ ] Bảo đảm kết quả deterministic, mock dữ liệu theo mỗi test và không dùng sleep tùy tiện.
- [ ] OpenAPI và response runtime thống nhất với path, status, authorization, media type.

**Tài liệu tham khảo:** [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html), [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html), [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html), [Spring Security — Reactive testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html), [Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

**Kết luận:** `WebTestClient` kiểm tra **API phản ứng từ góc nhìn HTTP**, còn `StepVerifier` kiểm tra các **signal của Publisher**. Chọn đúng phạm vi test, xác minh status/body/security và chủ động quản lý những dòng vô hạn sẽ giúp phát hiện cả lỗi REST contract lẫn lỗi streaming mà một test service đơn giản dễ bỏ sót.
