# Chọn RestTestClient, WebTestClient hay MockMvc theo phiên bản và mô hình

Spring cung cấp nhiều cách gửi request và xác nhận response khi kiểm thử ứng dụng web. Ba API thường được cân nhắc là `MockMvc`, `WebTestClient` và `RestTestClient`. Chúng có cú pháp tương tự ở một số điểm nhưng được thiết kế cho các mô hình ứng dụng và nhu cầu kiểm thử khác nhau.

`MockMvc` là công cụ kiểm thử trực tiếp tầng Spring MVC trên Servlet API mô phỏng. `WebTestClient` là HTTP client không đồng bộ, phù hợp nhất với Spring WebFlux và cũng có thể kết nối tới server thật hoặc dùng adapter cho Spring MVC. `RestTestClient` là HTTP client đồng bộ mới hơn, dựa trên `RestClient`, có thể kiểm thử Spring MVC qua MockMvc hoặc gửi request tới server đang chạy.

Việc lựa chọn cần xét hai yếu tố: ứng dụng đang dùng Spring MVC hay WebFlux, và test cần chạy ở tầng mock hay qua HTTP thật. Phiên bản Spring cũng quan trọng vì `RestTestClient` chỉ có từ Spring Framework 7.0.

## 1. Ba công cụ giải quyết những nhu cầu khác nhau

### MockMvc

`MockMvc` thuộc Spring MVC Test trong module `spring-test`. Nó thực hiện request thông qua `DispatcherServlet` và các thành phần Spring MVC, sử dụng request/response Servlet mô phỏng thay vì mở cổng HTTP.

MockMvc phù hợp khi ứng dụng dùng Spring MVC và test cần kiểm tra các chi tiết ở tầng Servlet/MVC như:

- Request mapping và handler method được chọn.
- Binding `@PathVariable`, `@RequestParam`, `@RequestBody` và validation.
- Message converter, formatter, interceptor và controller advice.
- Model, view, flash attributes và exception resolution.
- Servlet filter được đăng ký trong MockMvc.
- Async request thông qua `MvcResult` và `asyncDispatch(...)`.

Ví dụ:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsOrder() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42));
    }
}
```

MockMvc có các matcher phong phú như `status()`, `header()`, `content()`, `jsonPath()`, `handler()`, `model()` và `view()`. Test có thể lấy `MvcResult` để đọc handler, exception đã giải quyết, request, response hoặc thông tin async.

MockMvc không kiểm tra kết nối TCP, TLS, connector, reverse proxy hoặc quá trình deploy ứng dụng trên Servlet container. Nó xác nhận luồng xử lý Spring MVC trong môi trường mock.

### WebTestClient

`WebTestClient` thuộc Spring WebFlux và được giới thiệu từ Spring Framework 5.0. Đây là HTTP client không đồng bộ, xây dựng trên `WebClient`, có API kiểm thử response theo chuỗi expectation.

Với WebFlux, WebTestClient có thể bind trực tiếp vào controller, application context hoặc router function để chạy test không cần server. Nó cũng có thể kết nối đến một server đang chạy để thực hiện end-to-end test.

Ví dụ kiểm thử WebFlux bằng application context:

```java
@SpringJUnitConfig(WebFluxConfig.class)
class ReactiveOrderControllerTest {

    private WebTestClient client;

    @BeforeEach
    void setUp(ApplicationContext context) {
        client = WebTestClient.bindToApplicationContext(context).build();
    }

    @Test
    void returnsOrder() {
        client.get()
                .uri("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(42);
    }
}
```

WebTestClient cũng có thể dùng với Spring MVC. Trong trường hợp đó, dùng `MockMvcWebTestClient` để tạo client dựa trên MockMvc:

```java
WebTestClient client = MockMvcWebTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

Đây là adapter cho phép dùng API client của WebTestClient trong test MVC. Request vẫn được xử lý bởi MockMvc và Servlet mock; không có HTTP socket thật.

WebTestClient hữu ích khi cần một API test nhất quán cho WebFlux và HTTP thật, hoặc khi test reactive stream, SSE và các tình huống bất đồng bộ. Nó đòi hỏi các thư viện WebFlux/Reactor tương ứng trên classpath.

### RestTestClient

`RestTestClient` được giới thiệu từ Spring Framework 7.0. Nó là HTTP client đồng bộ, xây dựng trên Spring `RestClient`, nhưng bổ sung facade dành cho kiểm thử response.

RestTestClient có thể bind vào controller, Spring application context hoặc router function để kiểm thử bằng request/response mô phỏng. Nó cũng có thể kết nối tới server đang chạy thông qua `bindToServer()`.

Ví dụ bind vào MVC application context:

```java
@SpringJUnitConfig(WebMvcConfig.class)
class OrderRestTestClientTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }

    @Test
    void returnsOrder() {
        client.get()
                .uri("/api/orders/{id}", 42)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(OrderResponse.class)
                .consumeWith(result -> assertThat(
                        result.getResponseBody().getId()).isEqualTo(42));
    }
}
```

API request của RestTestClient giống `RestClient` cho đến `exchange()`. Sau đó test dùng các expectation như `expectStatus()`, `expectHeader()` và `expectBody()`. Spring cũng cung cấp `RestTestClientResponse` để viết assertion theo phong cách AssertJ.

RestTestClient là lựa chọn tự nhiên cho ứng dụng MVC đồng bộ khi nhóm muốn API giống một HTTP client thực tế và muốn dùng cùng cách viết test cho mock setup lẫn live server. Nó không phải reactive client như WebTestClient.

## 2. Mốc phiên bản cần nhớ

| Công cụ | Phiên bản Spring Framework | Ghi chú |
| --- | --- | --- |
| MockMvc | Có từ Spring Framework 3.2 | Kiểm thử Spring MVC qua Servlet API mô phỏng |
| WebTestClient | Có từ Spring Framework 5.0 | Client không đồng bộ; chủ yếu dành cho WebFlux, có thể dùng với MVC qua `MockMvcWebTestClient` |
| RestTestClient | Có từ Spring Framework 7.0 | Client đồng bộ dựa trên `RestClient`; hỗ trợ mock MVC setup và server thật |

Từ đó có thể suy ra:

- Dự án Spring Framework 5.x hoặc 6.x có thể dùng MockMvc và WebTestClient, nhưng chưa có `RestTestClient`.
- Dự án Spring Framework 7.x có thể cân nhắc cả ba công cụ.
- Spring Boot 3.x quản lý Spring Framework 6.x, vì vậy không cung cấp `RestTestClient` từ Spring Framework.
- Spring Boot 4.x quản lý Spring Framework 7.x, do đó có thể dùng `RestTestClient` và các cấu hình test tương ứng.

Không nên thêm riêng một phiên bản `spring-test` mới vào dự án đang dùng các module Spring cũ. Hãy để Spring Boot dependency management hoặc một BOM thống nhất phiên bản của toàn bộ module Spring.

## 3. Chọn theo mô hình ứng dụng

### Ứng dụng Spring MVC

Spring MVC chạy trên Servlet API. Các controller đồng bộ thường được kiểm thử trực tiếp bằng MockMvc.

Chọn MockMvc khi:

- Cần matcher chuyên biệt của Spring MVC như handler, model, view, flash attribute hoặc async result.
- Cần kiểm tra `DispatcherServlet`, Servlet request attributes, filter hoặc exception resolver.
- Muốn test MVC slice nhanh với `@WebMvcTest`.
- Dự án chưa dùng Spring Framework 7.0.

Chọn RestTestClient khi:

- Dự án đã dùng Spring Framework 7.0 trở lên.
- Muốn viết test theo API đồng bộ giống `RestClient`.
- Muốn cùng một kiểu request/expectation dùng được với MockMvc setup và server thật.
- Không cần truy cập các chi tiết nội bộ riêng của `MvcResult` trong phần lớn test.

Chọn WebTestClient cho MVC khi:

- Nhóm đã chuẩn hóa test theo API WebTestClient.
- Cần chia sẻ cách viết test giữa MVC và WebFlux.
- Muốn tận dụng API client không đồng bộ và có thể chuyển từ mock MVC sang live server.

Khi dùng WebTestClient với MVC, nhớ sử dụng `MockMvcWebTestClient` cho mock setup. Không gọi `WebTestClient.bindToApplicationContext(...)` với MVC context theo cách dành cho WebFlux.

### Ứng dụng Spring WebFlux

WebFlux dùng mô hình reactive với `WebHandler`, Reactor và các kiểu dữ liệu như `Mono`/`Flux`. MockMvc không phải công cụ kiểm thử WebFlux vì nó dựa trên Servlet API và Spring MVC.

WebTestClient là lựa chọn mặc định phù hợp cho WebFlux vì:

- Có thể bind vào controller, application context hoặc router function.
- Có thể xác nhận `Mono`, `Flux`, streaming response và SSE.
- Hỗ trợ test không cần server hoặc kết nối tới server thật.
- API request/response được thiết kế cho các luồng HTTP bất đồng bộ.

RestTestClient là client đồng bộ. Dù nó có thể gửi request đến một server HTTP đang chạy, nó không thay thế WebTestClient khi cần xác nhận hành vi reactive, backpressure hoặc streaming theo cách reactive.

### Ứng dụng có cả Spring MVC và WebFlux trên classpath

Spring Boot thường ưu tiên Spring MVC nếu cả Spring MVC và WebFlux cùng xuất hiện trên classpath. Vì vậy, không nên suy luận loại application context chỉ từ việc có dependency `spring-webflux`.

Hãy xác định rõ web application type và test đúng mô hình:

- MVC: dùng MockMvc, RestTestClient bind MockMvc hoặc WebTestClient qua `MockMvcWebTestClient`.
- WebFlux: dùng WebTestClient với WebFlux application context hoặc live server.

Nếu cần kiểm thử WebFlux trong một dự án có cả hai stack, hãy cấu hình web application type reactive cho test context hoặc tách cấu hình test phù hợp.

## 4. Chọn theo phạm vi kiểm thử: mock hay HTTP thật

Một yếu tố quan trọng khác là test cần chạy đến đâu.

| Phạm vi | MockMvc | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Controller độc lập, không mở server | Có | Có; MVC qua `MockMvcWebTestClient` | Có từ Framework 7.0 |
| Spring application context với mock request/response | Có | Có; MVC qua adapter hoặc WebFlux context trực tiếp | Có từ Framework 7.0 |
| WebFlux reactive controller | Không | Có | Không phải lựa chọn phù hợp cho kiểm tra reactive semantics |
| Router function | Không phải API chính cho WebFlux router | Có cho WebFlux router | Có binding router function theo API RestTestClient |
| HTTP qua cổng mạng thật | Không | Có qua `bindToServer()` | Có qua `bindToServer()` |
| Servlet container, TLS, connector và network behavior | Không | Có nếu kết nối live server | Có nếu kết nối live server |

### Mock setup

Mock setup gọi trực tiếp hạ tầng xử lý của framework bằng request/response mô phỏng. Nó thường nhanh và dễ cô lập hơn. Tuy nhiên, test không xác nhận được connector, TLS, context path ở server thật, proxy hoặc các hành vi phụ thuộc container.

Ví dụ MockMvc:

```java
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

Ví dụ RestTestClient:

```java
RestTestClient client = RestTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

Ví dụ WebTestClient cho WebFlux:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
```

### Live server setup

Nếu cần kiểm tra HTTP thực, ứng dụng phải được khởi động và client phải gửi request qua mạng. WebTestClient và RestTestClient đều có thể bind đến server đang chạy:

```java
WebTestClient webClient = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

RestTestClient restClient = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

Với Spring Boot, có thể khởi động server trên cổng ngẫu nhiên:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureRestTestClient
class OrderHttpIntegrationTest {

    @Test
    void servesOrderOverHttp(@Autowired RestTestClient client) {
        client.get()
                .uri("/api/orders/{id}", 42)
                .exchange()
                .expectStatus().isOk()
                .expectBody(OrderResponse.class)
                .consumeWith(result -> assertThat(
                        result.getResponseBody().getId()).isEqualTo(42));
    }
}
```

Trong Spring Boot 4, có thể dùng `@AutoConfigureRestTestClient` để cấu hình RestTestClient cho test. Với WebTestClient, dùng `@AutoConfigureWebTestClient` và bảo đảm dependency WebFlux phù hợp có trên classpath. Các annotation và package của Boot có thể thay đổi theo major version; hãy dùng tài liệu đúng phiên bản đang quản lý.

MockMvc không có chế độ live server. Nếu cần HTTP thật cho ứng dụng MVC, hãy dùng RestTestClient hoặc WebTestClient với server đang chạy.

## 5. So sánh API request và assertion

| Công việc | MockMvc | WebTestClient | RestTestClient |
| --- | --- | --- | --- |
| Tạo GET request | `perform(get("/path"))` | `get().uri("/path")` | `get().uri("/path")` |
| Thực hiện request | `perform(...)` | `exchange()` | `exchange()` |
| Kiểm tra status | `andExpect(status().isOk())` | `expectStatus().isOk()` | `expectStatus().isOk()` |
| Kiểm tra header | `andExpect(header()...)` | `expectHeader()...` | `expectHeader()...` |
| Kiểm tra JSON | `jsonPath(...)` | `expectBody().jsonPath(...)` | `expectBody().jsonPath(...)` |
| Đọc object | Deserialize từ response hoặc `jsonPath` | `expectBody(Type.class)` | `expectBody(Type.class)` |
| Kiểu client | Servlet MVC test API | Reactive/non-blocking | Synchronous/blocking |
| Truy cập chi tiết MVC result | Trực tiếp qua `MvcResult` | Qua MockMvc adapter nếu cần | Tùy API; có thể dùng response result của client |

Ví dụ cùng một mục tiêu với ba API:

```java
// MockMvc
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));

// WebTestClient
webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

// RestTestClient
restTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

Hai client WebTestClient và RestTestClient có cách viết khá giống nhau. Khác biệt quan trọng nằm ở mô hình thực thi: WebTestClient là client reactive, còn RestTestClient là client đồng bộ.

## 6. Dependency và cấu hình theo phiên bản

### Dự án Spring Boot 3.x

Spring Boot 3.x dùng Spring Framework 6.x. Dự án có thể dùng MockMvc và WebTestClient, nhưng chưa thể dùng `RestTestClient` vì lớp này chưa có trong Spring Framework 6.x.

Với MVC test, `spring-boot-starter-test` cung cấp các thư viện kiểm thử phổ biến, bao gồm Spring Test. Dự án MVC cần starter web tương ứng. Nếu muốn dùng WebTestClient, thêm Spring WebFlux dependency và cấu hình đúng client/adapter.

### Dự án Spring Boot 4.x

Spring Boot 4.x dùng Spring Framework 7.x, vì vậy có thể sử dụng RestTestClient. Boot cung cấp auto-configuration riêng cho các test client. Với test MVC slice, hãy xem annotation phù hợp cho mock transport; với full `@SpringBootTest`, `@AutoConfigureRestTestClient` có thể cấu hình client tương ứng.

Boot 4 chia nhỏ một số module và package test so với Boot 3. Không sao chép import của Boot 3 vào Boot 4 nếu package đã được chuyển. Hãy để Boot BOM quản lý phiên bản và tham khảo dependency/starter tương ứng với major version.

### Dự án Spring Framework không dùng Boot

Khai báo module cần thiết với cùng phiên bản Spring:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-webmvc")
    testImplementation("org.springframework:spring-webflux")
}
```

Đoạn cấu hình chỉ minh họa các module Spring liên quan. Chỉ thêm `spring-webflux` nếu test dùng WebTestClient; ứng dụng MVC thuần không cần thêm WebFlux chỉ để dùng MockMvc hoặc RestTestClient. Cần dùng dependency management/BOM hoặc khai báo phiên bản nhất quán cho các module.

Với Framework 6.x, không thể khai báo `RestTestClient` bằng cách thêm riêng `spring-test` 7.x vào dự án. Hãy nâng đồng bộ Spring Framework lên 7.x nếu muốn dùng client mới.

## 7. Tích hợp Spring Security và filter

Ba client có thể gửi request qua cấu hình bảo mật tùy cách được bind.

Với MockMvc, khi tự tạo từ `WebApplicationContext`, cần thêm Spring Security filter chain nếu muốn kiểm tra authorization:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

Với WebTestClient dùng MockMvc adapter, bảo đảm MockMvc underlying được cấu hình với filter chain. Với RestTestClient bind vào application context, dùng cấu hình MVC/security thực sự được nạp trong context. Với live server, request đi qua filter chain đang chạy trong server.

Trong mọi trường hợp, việc chỉ gắn một user giả vào request không chứng minh filter chain đã tham gia. Test phải kiểm tra đúng đường đi security mà ứng dụng sử dụng.

## 8. Tiêu chí lựa chọn nhanh

| Tình huống | Lựa chọn nên ưu tiên | Lý do |
| --- | --- | --- |
| Spring MVC, cần kiểm tra mapping, model, view, handler hoặc `MvcResult` | MockMvc | API chuyên sâu cho Servlet MVC |
| Spring MVC, muốn API đồng bộ giống HTTP client, Spring 7+ | RestTestClient | API dựa trên RestClient, bind được MockMvc hoặc server |
| Spring MVC, muốn dùng chung API với WebFlux | WebTestClient qua `MockMvcWebTestClient` | Dùng chung client API, MVC vẫn xử lý qua MockMvc |
| Spring WebFlux reactive | WebTestClient | Phù hợp với Reactor, async và streaming |
| Spring MVC trên Spring Framework 6.x | MockMvc hoặc WebTestClient adapter | RestTestClient chưa tồn tại ở Framework 6.x |
| Spring MVC trên Spring Framework 7.x | MockMvc hoặc RestTestClient; WebTestClient khi cần | Chọn theo độ sâu MVC hay kiểu HTTP client |
| Kiểm thử qua cổng HTTP thật với client đồng bộ | RestTestClient (7.0+) | Giao tiếp HTTP thật bằng API đồng bộ |
| Kiểm thử qua cổng HTTP thật với client reactive | WebTestClient | Client không đồng bộ, phù hợp streaming |
| Kiểm tra Servlet container hoặc TLS | RestTestClient/WebTestClient bind server | Cần server thật; MockMvc không mở socket |

## 9. Những nhầm lẫn thường gặp

### Nghĩ WebTestClient chỉ dùng cho WebFlux

WebTestClient được thiết kế chủ yếu cho WebFlux nhưng có thể dùng với Spring MVC thông qua `MockMvcWebTestClient`. Khi dùng adapter, request vẫn được xử lý bằng MockMvc. Điều này giúp chia sẻ API test nhưng không biến ứng dụng MVC thành WebFlux.

### Nghĩ MockMvc kiểm tra HTTP thật

MockMvc gọi `DispatcherServlet` trong cùng tiến trình với Servlet mock. Nó không gửi request qua TCP. Muốn kiểm tra server, connector, TLS hoặc proxy, hãy khởi động server và dùng một HTTP client.

### Nghĩ RestTestClient có trong Spring Boot 3.4 vì MockMvcTester đã có

`MockMvcTester` được giới thiệu trong Spring Framework 6.2, còn `RestTestClient` được giới thiệu trong Spring Framework 7.0. Đây là hai API khác nhau. Spring Boot 3.4 có thể hỗ trợ MockMvcTester nhưng vẫn dùng Framework 6.2 và chưa có RestTestClient.

### Dùng RestTestClient thay WebTestClient cho mọi ứng dụng reactive

RestTestClient là client đồng bộ. Nó không cung cấp cùng mô hình reactive như WebTestClient. Với WebFlux, streaming, SSE hoặc kiểm tra hành vi reactive, WebTestClient thường phù hợp hơn.

### Dùng MockMvc cho WebFlux controller

MockMvc dựa trên Servlet API và Spring MVC. WebFlux dùng `WebHandler` và reactive stack. Dùng WebTestClient cho WebFlux thay vì cố đưa WebFlux controller vào MockMvc.

### Cho rằng mock binding và live server tương đương

Một client có thể hỗ trợ cả mock binding và live server, nhưng phạm vi kiểm thử khác nhau. Mock binding không kiểm tra network hoặc container. Live server test chậm hơn và cần quản lý cổng, môi trường, dữ liệu và transaction phù hợp.

## 10. Chiến lược kết hợp trong một dự án

Một dự án không cần chỉ chọn một công cụ cho mọi test. Có thể phân tầng:

1. Dùng MockMvc cho phần lớn MVC slice test cần xác nhận mapping, binding, validation và exception handling.
2. Dùng RestTestClient nếu dự án Spring Framework 7+ muốn kiểm tra MVC theo API HTTP đồng bộ và tái sử dụng cấu hình client.
3. Dùng WebTestClient cho WebFlux controller, reactive flow, streaming hoặc khi nhóm muốn một API client chung giữa reactive stack và server thật.
4. Dùng một số test live server với RestTestClient hoặc WebTestClient để xác nhận cổng HTTP, filter thực tế, container và cấu hình triển khai.

Không cần chuyển tất cả MockMvc test sang client khác chỉ vì API mới xuất hiện. Hãy giữ công cụ phù hợp nhất với hành vi đang xác nhận và nâng cấp theo phiên bản Spring mà dự án đã chọn.

## 11. Quy trình quyết định

Trước khi chọn công cụ, trả lời lần lượt:

1. Ứng dụng là Spring MVC hay Spring WebFlux?
2. Test cần xác nhận chi tiết MVC/Servlet hay chỉ cần gửi HTTP request và kiểm tra response?
3. Test cần request/response mô phỏng hay cần kết nối đến server đang chạy?
4. Phiên bản Spring Framework hiện tại là 6.x hay 7.x?
5. Nhóm cần client đồng bộ giống RestClient hay client reactive giống WebClient?
6. Test có cần truy cập `MvcResult`, handler, model, view hoặc async dispatch không?

Nếu là MVC và cần chi tiết Servlet, ưu tiên MockMvc. Nếu là WebFlux, ưu tiên WebTestClient. Nếu là MVC đồng bộ trên Framework 7+, muốn HTTP client facade và có thể chuyển giữa mock/live server, cân nhắc RestTestClient. Nếu cần HTTP thật, hãy chọn RestTestClient hoặc WebTestClient bind tới server đang chạy.

## 12. Tài liệu tham khảo

- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## 13. Kết luận

MockMvc là công cụ chuyên sâu cho Spring MVC và Servlet request mô phỏng. WebTestClient là client reactive, phù hợp nhất với WebFlux nhưng cũng có thể kiểm thử MVC qua `MockMvcWebTestClient`. RestTestClient là client đồng bộ mới từ Spring Framework 7.0, phù hợp cho MVC và có thể bind vào mock context hoặc server thật.

Hãy chọn theo mô hình ứng dụng, phạm vi kiểm thử và phiên bản Spring đang dùng. MVC cần chi tiết `MvcResult` thì dùng MockMvc; WebFlux và reactive streaming thì dùng WebTestClient; MVC đồng bộ trên Spring 7+ muốn API HTTP client thì cân nhắc RestTestClient. Với mọi yêu cầu liên quan đến network hoặc Servlet container thật, hãy dùng client kết nối server thay cho mock-only test.
