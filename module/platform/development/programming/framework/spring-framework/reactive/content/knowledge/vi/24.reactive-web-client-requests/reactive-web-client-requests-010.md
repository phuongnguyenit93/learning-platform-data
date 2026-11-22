# Tích hợp HTTP service interface bằng `@HttpExchange` và `WebClientAdapter` trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Gửi yêu cầu WebClient. Bài học xây dựng một client HTTP theo contract interface: khai báo endpoint bằng `@HttpExchange`, `@GetExchange`, `@PostExchange`, sau đó tạo proxy thực thi request qua `WebClientAdapter`. Ta đi từ mapping method/parameter, reactive return types và cấu hình WebClient tới error handling, timeout, bảo mật, test HTTP và cách chọn giữa interface proxy với WebClient fluent API.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích HTTP Service Client là gì và proxy được tạo bởi `HttpServiceProxyFactory` hoạt động ra sao.
2. Phân biệt vai trò của `@HttpExchange`, các annotation method như `@GetExchange` và `WebClientAdapter`.
3. Khai báo một HTTP API contract bằng Java interface, bao gồm path, query, header, body, cookie và multipart.
4. Chọn đúng return type `Mono<T>`, `Flux<T>`, `Mono<Void>` hoặc `Mono<ResponseEntity<T>>`.
5. Cấu hình `WebClient`, base URL, codec, filter, authentication, timeout và error handler trước khi tạo proxy.
6. Đăng ký proxy như Spring bean và inject vào service/controller.
7. Kiểm thử request thực tế bằng HTTP mock server, kiểm tra method, URL, header, body, status và response.
8. Biết khi nào interface proxy làm code rõ hơn và khi nào cần gọi `WebClient` trực tiếp.

**Ý chính:** `@HttpExchange` mô tả hợp đồng HTTP ở dạng interface; `HttpServiceProxyFactory` tạo implementation cho interface; `WebClientAdapter` nối proxy với một `WebClient` đã cấu hình. Interface giúp code gọi service giống như gọi một Java dependency, còn việc kết nối mạng, codec, filter và reactive lifecycle vẫn do WebClient đảm nhiệm.

## 2. HTTP Service Client nằm ở đâu trong kiến trúc?

Nếu dùng WebClient trực tiếp, mỗi lần gọi service thường phải mô tả method, URI, header, body và cách decode response:

~~~java
Mono<CatalogItem> item = webClient.get()
    .uri("/api/catalog/{id}", id)
    .header("X-Request-Id", requestId)
    .retrieve()
    .bodyToMono(CatalogItem.class);
~~~

HTTP Service Client chuyển phần mô tả endpoint thành một interface:

~~~java
public interface CatalogHttpService {

    @GetExchange("/api/catalog/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id,
        @RequestHeader("X-Request-Id") String requestId);
}
~~~

Sau khi tạo proxy, code gọi:

~~~java
Mono<CatalogItem> item =
    catalogHttpService.getById(id, requestId);
~~~

Proxy đọc annotation và method arguments, tạo request values, chuyển chúng qua adapter tới WebClient, rồi trả reactive result cho caller.

~~~text
Business service / controller
            |
            v
    CatalogHttpService
       Java interface
            |
            v
   HttpServiceProxyFactory
     đọc annotation + args
            |
            v
      WebClientAdapter
            |
            v
         WebClient
   filters / codecs / connector
            |
            v
        HTTP network
            |
            v
    Remote HTTP service
            |
            v
      response decoding
            |
            v
       Mono / Flux / entity
~~~

Các thành phần có vai trò riêng:

| Thành phần | Vai trò |
| --- | --- |
| `@HttpExchange` | Khai báo thuộc tính chung cho các method trong interface, ví dụ base path, Accept và Content-Type mặc định. |
| `@GetExchange`, `@PostExchange`, `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | Khai báo HTTP method và path của từng operation. |
| `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` | Ánh xạ method arguments thành URL, query, header và request body. |
| `HttpServiceProxyFactory` | Đọc contract interface và tạo client proxy. |
| `WebClientAdapter` | Triển khai `ReactorHttpExchangeAdapter`, chuyển lời gọi proxy sang WebClient. |
| `WebClient` | Thực hiện HTTP I/O, encode/decode body, quản lý connector, filter và reactive response. |

HTTP Service Client là một lớp khai báo API trên WebClient. Nó không tạo HTTP server, không tự triển khai remote service và cũng không thay thế WebClient connector.

## 3. Khi nào nên dùng interface proxy?

Interface proxy phù hợp khi ứng dụng gọi một API có contract ổn định và nhiều nơi cùng sử dụng:

- Nhiều service cùng gọi một Catalog, Billing hoặc Identity API.
- Muốn tập trung endpoint path, header, request/response DTO và tài liệu method ở một nơi.
- Muốn mock dependency ở unit test bằng interface.
- Muốn thay cách thực thi client mà giữ nguyên API Java của caller.
- Muốn phân tách client theo downstream host hoặc bounded context.

WebClient fluent API vẫn phù hợp khi request có logic động phức tạp, response cần phân nhánh thủ công theo status/header, hoặc chỉ có một request đặc biệt không đáng tạo interface riêng.

| Tiêu chí | HTTP Service interface | WebClient trực tiếp |
| --- | --- | --- |
| Khai báo endpoint | Annotation trên method | Fluent chain tại nơi gọi |
| Tái sử dụng contract | Tốt; nhiều caller dùng cùng interface | Cần tự trích helper/client class |
| URI/path/header/body | Map qua method arguments | Khai báo trực tiếp trong chain |
| Reactive | `Mono`, `Flux` và reactive adapter types | `Mono`, `Flux` và Publisher |
| Filter, codec, TLS, pool | Cấu hình trên WebClient underlying | Cấu hình trực tiếp trên WebClient |
| Xử lý response nâng cao | Có thể cần custom adapter decorator hoặc WebClient method riêng | Toàn quyền điều khiển bằng `exchangeToMono`/`exchangeToFlux` |
| Test caller | Mock interface dễ dàng | Thường mock WebClient chain hoặc test qua mock server |
| Hợp với | Contract ổn định, dùng lại nhiều | Request đặc thù, logic HTTP linh hoạt |

Không cần biến mọi request thành một interface. Hãy tạo HTTP service interface khi nó đại diện cho một dependency có tên và contract có ý nghĩa trong domain.

## 4. Khai báo interface với `@HttpExchange`

`@HttpExchange` được đặt ở type level để định nghĩa thuộc tính chung. Annotation method cụ thể quyết định HTTP verb và path.

~~~java
@HttpExchange(
    url = "/api/catalog",
    accept = MediaType.APPLICATION_JSON_VALUE
)
public interface CatalogHttpService {

    @GetExchange("/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id);

    @PostExchange(
        contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<CatalogItem> create(
        @RequestBody CreateCatalogItem request);

    @DeleteExchange("/{id}")
    Mono<Void> delete(
        @PathVariable("id") String id);
}
~~~

Trong ví dụ:
- `url="/api/catalog"` là prefix dùng chung.
- `accept` đặt header `Accept: application/json`.
- `@GetExchange("/{id}")` tạo GET tới `/api/catalog/{id}`.
- `@PostExchange` tạo POST tới `/api/catalog`.
- `contentType` khai báo `Content-Type: application/json`.
- `@RequestBody` yêu cầu WebClient serialize DTO thành body.
- `Mono` giữ request/response ở dạng reactive.

Có thể khai báo toàn bộ URL ở từng method nếu interface chỉ có vài endpoint khác nhau. Dùng type-level prefix khi các operation cùng thuộc một resource/API.

### 4.1. Các annotation HTTP method

| Annotation | HTTP method | Ví dụ |
| --- | --- | --- |
| `@HttpExchange(method = "GET")` | GET | Method tùy biến với annotation tổng quát |
| `@GetExchange` | GET | Đọc resource |
| `@PostExchange` | POST | Tạo resource hoặc thực hiện command |
| `@PutExchange` | PUT | Thay thế resource |
| `@PatchExchange` | PATCH | Cập nhật một phần |
| `@DeleteExchange` | DELETE | Xóa resource |

`@GetExchange`, `@PostExchange`, `@PutExchange`, `@PatchExchange` và `@DeleteExchange` là shortcut của `@HttpExchange` với HTTP method tương ứng. Không đặt hai method có cùng contract nhưng annotation/path mâu thuẫn; hãy giữ mỗi method đại diện cho một operation cụ thể.

### 4.2. Thuộc tính của `@HttpExchange`

Các thuộc tính thường dùng:

- `url`: URL hoặc URI template; có thể đặt prefix ở type level.
- `method`: HTTP method, đặc biệt khi dùng `@HttpExchange` trực tiếp.
- `contentType`: loại nội dung request.
- `accept`: kiểu response mong muốn.
- `headers`: các header cố định dạng `name=value`.

Method-level mapping cho biết endpoint cụ thể; type-level annotation giúp chia sẻ base path và media type. Nếu cần thay đổi header theo từng request, dùng `@RequestHeader` hoặc WebClient filter thay vì hardcode giá trị động trong annotation.

## 5. Ánh xạ method arguments thành HTTP request

HTTP Service Client hỗ trợ các tham số được đánh dấu bằng annotation Spring Web. Các tham số này được phân tích khi tạo proxy và chuyển thành request values lúc method được gọi.

### 5.1. Path variable

~~~java
@GetExchange("/orders/{orderId}")
Mono<Order> getOrder(
    @PathVariable("orderId") String orderId);
~~~

Với `orderId="A-100"`, proxy mở rộng URI template thành `/orders/A-100`. Nên ghi rõ tên trong `@PathVariable("orderId")` để không phụ thuộc compiler parameter-name metadata.

Có thể dùng một `Map<String, ?>` để cung cấp nhiều path variables khi contract thực sự cần:

~~~java
@GetExchange("/customers/{customerId}/orders/{orderId}")
Mono<Order> getOrder(
    @PathVariable Map<String, ?> pathVariables);
~~~

### 5.2. Query parameter

~~~java
@GetExchange("/orders")
Flux<Order> findOrders(
    @RequestParam("status") String status,
    @RequestParam("page") int page,
    @RequestParam("size") int size);
~~~

Lời gọi `findOrders("PAID", 0, 20)` tạo query string tương ứng:

~~~http
GET /orders?status=PAID&page=0&size=20
~~~

`@RequestParam` cũng hỗ trợ collection, map và `MultiValueMap` cho query parameter nhiều giá trị. Giá trị không phải String được chuyển đổi sang dạng văn bản.

Khi `Content-Type` là `application/x-www-form-urlencoded`, `@RequestParam` được encode thành form body thay vì query string. Vì vậy cần khai báo `contentType` đúng ở method hoặc type level.

### 5.3. Request header

~~~java
@GetExchange("/orders/{id}")
Mono<Order> getOrder(
    @PathVariable("id") String id,
    @RequestHeader("X-Request-Id") String requestId);
~~~

Header có thể là một giá trị, collection, map hoặc `MultiValueMap`. Dùng header parameter cho dữ liệu thay đổi theo từng method call như request ID, tenant key hoặc locale.

Header cố định cho mọi request nên cấu hình ở WebClient:

~~~java
WebClient webClient = builder
    .defaultHeader("X-Client-Name", "order-service")
    .build();
~~~

### 5.4. Request body

~~~java
@PostExchange(
    url = "/orders",
    contentType = MediaType.APPLICATION_JSON_VALUE)
Mono<Order> create(@RequestBody CreateOrder request);
~~~

`@RequestBody` có thể nhận object để codec serialize hoặc một reactive Publisher như `Mono<T>`/`Flux<T>`:

~~~java
@PostExchange(
    url = "/orders/bulk",
    contentType = MediaType.APPLICATION_NDJSON_VALUE)
Mono<Void> importOrders(
    @RequestBody Flux<CreateOrder> orders);
~~~

Publisher request body cho phép truyền dữ liệu theo stream và giữ backpressure. Không `collectList()` một stream lớn chỉ để gửi HTTP; hãy truyền Publisher trực tiếp nếu remote API chấp nhận framing tương ứng.

### 5.5. Cookie và multipart

Cookie:

~~~java
@GetExchange("/profile")
Mono<Profile> profile(
    @CookieValue("SESSION") String sessionId);
~~~

Multipart:

~~~java
@PostExchange(
    url = "/documents",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<DocumentReceipt> upload(
    @RequestPart("description") String description,
    @RequestPart("file") Resource file);
~~~

`@RequestPart` hỗ trợ String, Resource, object được encode thành part, `HttpEntity`, Spring `Part` và reactive Publisher của các kiểu part phù hợp. Đối với file lớn, dùng Resource/Publisher và cấu hình upload streaming có giới hạn; tránh đọc toàn bộ file vào `byte[]` nếu không cần.

`@CookieValue` ở HTTP service interface có nghĩa là thêm cookie vào request outbound. Nó không phải API đọc cookie của request inbound trên server controller.

### 5.6. URI và HTTP method động

Một method có thể nhận `URI` để override URL được khai báo trong annotation:

~~~java
@GetExchange("/orders/{id}")
Mono<Order> getOrder(
    URI uri);
~~~

Hoặc nhận `HttpMethod` để override HTTP method của annotation:

~~~java
@HttpExchange("/resource")
Mono<String> exchange(
    HttpMethod method,
    @RequestBody(required = false) String body);
~~~

Đây là lựa chọn nâng cao. Nếu URL/method động làm contract interface khó hiểu, dùng một method riêng hoặc WebClient trực tiếp sẽ rõ hơn.

### 5.7. Request attributes và custom argument resolver

`@RequestAttribute` cung cấp request attribute nội bộ cho client adapter; nó chỉ được hỗ trợ bởi một số adapter như `RestClient` và `WebClient`, không phải HTTP header gửi tới remote server.

Nếu domain có kiểu tham số riêng, có thể triển khai `HttpServiceArgumentResolver` và đăng ký qua `HttpServiceProxyFactory.Builder.customArgumentResolver(...)`. Resolver chuyển object đó thành path/query/header/body values. Chỉ thêm resolver khi có nhiều interface thực sự dùng chung quy ước; với một endpoint đơn lẻ, annotation tiêu chuẩn thường dễ hiểu hơn.

Các method parameters không được truyền `null` trừ khi annotation hỗ trợ `required=false` hoặc kiểu tham số được xác định là optional. Hãy khai báo optional rõ ràng và kiểm tra cách nó được encode thành request.

## 6. Chọn reactive return type

Vì `WebClientAdapter` là `ReactorHttpExchangeAdapter`, HTTP Service Client có thể dùng return types đồng bộ hoặc reactive. Trong ứng dụng WebFlux, nên ưu tiên `Mono` và `Flux` để không block event-loop.

| Return type | Ý nghĩa |
| --- | --- |
| `Mono<T>` | Một response body object hoặc không có giá trị |
| `Flux<T>` | Stream các phần tử trong response body |
| `Mono<Void>` | Thực hiện request, tiêu thụ/giải phóng response body nếu có và chỉ báo completion |
| `Mono<HttpHeaders>` | Trả response headers sau khi body được giải phóng |
| `Mono<ResponseEntity<Void>>` | Trả status và headers, không giữ body |
| `Mono<ResponseEntity<T>>` | Trả status, headers và body đã decode |
| `Mono<ResponseEntity<Flux<T>>>` | Trả status/headers trước, body vẫn là stream để caller tiêu thụ |
| `HttpHeaders`, `T`, `ResponseEntity<T>` | Kiểu đồng bộ; adapter có thể phải chờ/block để trả kết quả |

### 6.1. Mono cho response đơn

~~~java
@GetExchange("/{id}")
Mono<CatalogItem> getById(
    @PathVariable("id") String id);
~~~

Dùng khi endpoint trả một resource. Nếu remote server trả 404 hoặc 500, mặc định WebClient phát exception; `Mono` sẽ kết thúc bằng error signal thay vì phát object rỗng.

### 6.2. Flux cho response nhiều phần tử

~~~java
@GetExchange
Flux<CatalogItem> findAll(
    @RequestParam("category") String category);
~~~

Dùng khi body là một danh sách JSON hoặc stream tương thích với codec. `Flux<T>` decode phần tử theo demand, giúp caller xử lý từng phần tử và giữ backpressure. Nếu caller gọi `collectList()`, dữ liệu được gom vào memory; chỉ làm vậy khi kích thước kết quả có giới hạn phù hợp.

### 6.3. ResponseEntity khi cần status và headers

~~~java
@PostExchange
Mono<ResponseEntity<CatalogItem>> create(
    @RequestBody CreateCatalogItem request);
~~~

`ResponseEntity` hữu ích khi cần đọc `Location`, `ETag`, rate limit headers hoặc status code. Với `Mono<ResponseEntity<T>>`, body được decode trước khi entity phát ra.

### 6.4. ResponseEntity với body streaming

~~~java
@GetExchange(value = "/events",
             accept = MediaType.TEXT_EVENT_STREAM_VALUE)
Mono<ResponseEntity<Flux<ServerSentEvent<CatalogEvent>>>> events();
~~~

Outer `Mono` nhận status và headers; inner `Flux` tiếp tục đọc stream. Caller phải subscribe/consume body để giải phóng response và connection. Nếu chỉ cần body stream, `Flux<T>` thường đơn giản hơn.

### 6.5. Vì sao tránh kiểu đồng bộ trong reactive flow?

WebClient adapter hỗ trợ kiểu trả về đồng bộ, nhưng caller phải đợi kết quả để nhận object. Nếu gọi method đồng bộ trong event-loop hoặc reactive chain, có thể block thread và giảm throughput.

Không viết:

~~~java
CatalogItem item = catalogClient.getByIdBlocking("42");
return Mono.just(item);
~~~

Ưu tiên:

~~~java
return catalogClient.getById("42")
    .map(this::toView);
~~~

`block()` phù hợp trong test, command-line boundary hoặc code đồng bộ được thiết kế rõ ràng; không dùng nó trong WebFlux controller/service đang xử lý request.

## 7. Tạo WebClientAdapter và HttpServiceProxyFactory

Đây là bước kết nối interface với một WebClient đã cấu hình.

~~~java
WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.test")
    .defaultHeader(
        HttpHeaders.ACCEPT,
        MediaType.APPLICATION_JSON_VALUE)
    .build();

WebClientAdapter adapter = WebClientAdapter.create(webClient);

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(adapter).build();

CatalogHttpService catalogClient =
    factory.createClient(CatalogHttpService.class);
~~~

Các bước:

1. Tạo `WebClient` với base URL và các cấu hình cần thiết.
2. Gọi `WebClientAdapter.create(webClient)` để tạo adapter reactive.
3. Tạo `HttpServiceProxyFactory` bằng `builderFor(adapter)`.
4. Gọi `createClient(CatalogHttpService.class)` để lấy proxy triển khai interface.
5. Inject proxy vào thành phần cần gọi remote API.

`HttpServiceProxyFactory` đọc annotation và tạo implementation runtime cho interface. Không tự viết class triển khai từng method và không tạo một proxy mới cho mỗi HTTP request.

### 7.1. Vòng đời bean

Trong Spring application, tạo proxy một lần dưới dạng singleton bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    CatalogHttpService catalogHttpService(
            WebClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        WebClient webClient = builder
            .baseUrl(baseUrl)
            .build();

        WebClientAdapter adapter =
            WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpService.class);
    }
}
~~~

`WebClient.Builder` do Spring Boot auto-configure có thể được inject và tùy biến trước khi build. WebClient đã build có thể được dùng lại cho nhiều request; builder là đối tượng cấu hình và không nên thay đổi tùy tiện sau khi đã dùng để tạo client.

Cấu hình base URL qua property:

~~~properties
catalog.base-url=https://catalog.example.test
~~~

Không hardcode host production vào interface. Cùng một interface có thể gọi local, test, staging hoặc production bằng cách thay property và client configuration.

### 7.2. Inject vào service

~~~java
@Service
public class CatalogService {

    private final CatalogHttpService catalogClient;

    public CatalogService(CatalogHttpService catalogClient) {
        this.catalogClient = catalogClient;
    }

    public Mono<CatalogView> getCatalogItem(
            String id, String requestId) {

        return catalogClient.getById(id, requestId)
            .map(item ->
                new CatalogView(item.id(), item.name()));
    }
}
~~~

Business service chỉ phụ thuộc interface. Nó không cần biết WebClient, adapter hay factory được cấu hình ở đâu. Khi test business service, có thể mock `CatalogHttpService` trực tiếp.

## 8. Tùy biến WebClient trước khi tạo proxy

Interface mô tả contract của endpoint; WebClient điều khiển cách request được thực hiện. Các filter và connector setting áp dụng cho mọi method proxy dùng chung client đó.

### 8.1. Default headers và codec

~~~java
WebClient webClient = builder
    .baseUrl(baseUrl)
    .defaultHeader("X-Client-Name", "checkout-service")
    .codecs(codecs ->
        codecs.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Default header phù hợp cho client identity hoặc Accept chung. Codec configuration phù hợp khi API trả payload lớn hoặc cần custom serializer. Giới hạn buffer phải phù hợp với response thực tế; không tăng không giới hạn chỉ để tránh `DataBufferLimitException`.

### 8.2. ExchangeFilterFunction

Dùng filter cho hành vi xuyên suốt request, ví dụ correlation ID, metrics, tracing hoặc authentication:

~~~java
ExchangeFilterFunction requestIdFilter =
    (request, next) -> {
        ClientRequest updated = ClientRequest.from(request)
            .header("X-Client-Name", "checkout-service")
            .build();

        return next.exchange(updated);
    };

WebClient webClient = builder
    .baseUrl(baseUrl)
    .filter(requestIdFilter)
    .build();
~~~

Filter có thể đọc Reactor Context nếu cần truyền request metadata theo subscription. Đừng log toàn bộ request headers hoặc body trong filter; chúng có thể chứa Authorization, cookie và PII. Chỉ log trường đã allowlist.

### 8.3. Authentication và OAuth2

Có thể gắn filter xác thực vào WebClient để token được cấp/refresh theo chính sách. Với OAuth2, ưu tiên tích hợp Spring Security reactive authorized client thay vì tự ghép token vào từng method interface.

Interface chỉ cần mô tả phần API request:

~~~java
@GetExchange("/me")
Mono<UserProfile> currentUser();
~~~

Token được thêm ở WebClient filter/authorized client manager. Cách này giúp credential lifecycle nằm trong cấu hình client có kiểm soát, không bị lặp ở mọi method.

### 8.4. Timeout, connection pool và TLS

Timeout không phải một thuộc tính của `@HttpExchange`. Cấu hình ở HTTP connector/WebClient:
- Connect timeout giới hạn thời gian thiết lập TCP/TLS connection.
- Response/read timeout giới hạn thời gian chờ dữ liệu theo chính sách client.
- `Mono.timeout(...)` có thể giới hạn thời gian cho một operation ở mức reactive chain.
- Connection pool giới hạn số kết nối đồng thời và thời gian giữ connection.
- TLS trust, client certificate và proxy được cấu hình ở connector.

Không dùng một timeout duy nhất cho mọi API nếu latency profile khác nhau. Một request tìm kiếm nhanh, một upload file lớn và một stream SSE có yêu cầu timeout khác nhau.

## 9. Xử lý lỗi HTTP từ remote service

Mặc định, WebClient xem các status 4xx và 5xx là lỗi và phát `WebClientResponseException`. Vì HTTP Service Client chạy qua WebClientAdapter, hành vi status mặc định của underlying WebClient vẫn được áp dụng.

Ví dụ:

~~~java
catalogClient.getById("missing", "req-404")
    .onErrorResume(
        WebClientResponseException.NotFound.class,
        error -> Mono.empty());
~~~

Không nên biến mọi lỗi thành `Mono.empty()`. Cần phân biệt:
- 404 có thể là resource không tồn tại theo nghiệp vụ.
- 400 thường là request client không hợp lệ.
- 401/403 là vấn đề xác thực hoặc quyền.
- 429 có thể retry sau khoảng thời gian server chỉ định.
- 5xx và lỗi kết nối có thể là lỗi transient hoặc dependency outage.

### 9.1. Giữ status và headers khi cần

Dùng `Mono<ResponseEntity<T>>` khi cần status và headers:

~~~java
catalogClient.create(request)
    .flatMap(response -> {
        URI location = response.getHeaders().getLocation();
        CatalogItem item = response.getBody();

        return saveRemoteReference(location, item);
    });
~~~

Theo mặc định, 4xx/5xx có thể bị chuyển thành exception trước khi method trả `ResponseEntity`. Nếu 404 là một kết quả bình thường cần giữ dưới dạng `ResponseEntity` với body null, có thể cấu hình custom status handling hoặc dùng `NotFoundWebClientAdapterDecorator` của Spring cho WebClient adapter.

### 9.2. Tùy biến status handler

WebClient builder có thể đăng ký default status handler cho mọi lời gọi qua client:

~~~java
WebClient webClient = builder
    .baseUrl(baseUrl)
    .defaultStatusHandler(
        HttpStatusCode::isError,
        response -> response.createException())
    .build();
~~~

Ví dụ trên minh họa vị trí cấu hình; nó giữ hành vi exception mặc định của WebClient. Trong ứng dụng thật, có thể decode một error DTO ổn định rồi map thành exception domain riêng. Nếu error body không theo contract hoặc decode thất bại, hãy có fallback và không làm lộ nội dung nhạy cảm của remote service.

### 9.3. Retry có chọn lọc

Không retry mọi exception một cách tự động. Retry:
- Lỗi transient như connect reset hoặc 503 nếu chính sách cho phép.
- Chỉ operation idempotent, hoặc POST có idempotency key.
- Có giới hạn số lần và backoff.
- Có timeout tổng thể để không kéo dài request vô hạn.
- Giữ cùng request/correlation ID qua các lần retry.

Ví dụ một GET có thể retry lỗi transient:

~~~java
catalogClient.getById("42", requestId)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransient));
~~~

`isTransient` là policy do ứng dụng định nghĩa theo exception/status thực tế. Không retry 400, 401 hoặc 403 một cách mù quáng; retry POST tạo resource mà không có idempotency protection có thể tạo dữ liệu trùng.

## 10. Kiểm thử HTTP Service Client

Có hai lớp test hữu ích:

1. **Unit test caller:** mock interface proxy để xác nhận business service xử lý kết quả và lỗi đúng.
2. **HTTP client integration test:** dùng mock HTTP server để xác nhận annotation thực sự tạo method, path, query, header, body và decode response đúng.

Mock interface không chứng minh mapping annotation đúng. Với client dùng trong production, nên có ít nhất một bộ HTTP contract test.

### 10.1. MockWebServer

`MockWebServer` của OkHttp mở một HTTP server local, nhận request thật và cho phép test enqueue response. Nó giúp test `WebClientAdapter` mà không gọi internet hoặc phụ thuộc dịch vụ bên ngoài.

Các test nên kiểm tra:
- Method và path chính xác.
- Query parameter được encode.
- Request header được gửi.
- Request DTO được serialize.
- Response JSON được decode.
- Status 201 và `Location` được giữ trong `ResponseEntity`.
- 4xx/5xx phát lỗi như cấu hình.

## 11. Ví dụ hoàn chỉnh: Spring Boot 4.0.9 và Java 17+

Project sau có thể chạy độc lập. Ứng dụng tạo một `CatalogHttpService` proxy; test khởi chạy MockWebServer và trỏ property `catalog.base-url` tới server local.

### 11.1. Cấu trúc thư mục

~~~text
http-service-client/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/catalog/
│   ├── CatalogClientApplication.java
│   ├── CatalogItem.java
│   ├── CreateCatalogItem.java
│   ├── CatalogHttpService.java
│   └── CatalogClientConfiguration.java
└── src/test/java/com/example/catalog/
    └── CatalogHttpServiceTest.java
~~~

### 11.2. pom.xml

Spring Boot 4.0.9 và Java 17+ được dùng cho ví dụ. MockWebServer chỉ nằm trong test scope.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-service-client</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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

### 11.3. application.properties

~~~properties
catalog.base-url=https://catalog.example.test
~~~

Trong production, cấu hình base URL qua environment hoặc secret/config management. Test sẽ override property bằng URL do MockWebServer cấp.

### 11.4. CatalogClientApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogClientApplication.class, args);
    }
}
~~~

### 11.5. DTO

`CatalogItem.java`:

~~~java
package com.example.catalog;

public record CatalogItem(
    String id,
    String name,
    String category
) {}
~~~

`CreateCatalogItem.java`:

~~~java
package com.example.catalog;

public record CreateCatalogItem(
    String name,
    String category
) {}
~~~

DTO là contract dữ liệu mà client hiểu. Nếu remote API thay đổi field hoặc kiểu dữ liệu, cần versioning/compatibility test thay vì để thay đổi ngầm phá caller.

### 11.6. CatalogHttpService.java

~~~java
package com.example.catalog;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@HttpExchange(
    url = "/api/catalog",
    accept = MediaType.APPLICATION_JSON_VALUE
)
public interface CatalogHttpService {

    @GetExchange("/{id}")
    Mono<CatalogItem> getById(
        @PathVariable("id") String id,
        @RequestHeader("X-Request-Id") String requestId);

    @GetExchange
    Flux<CatalogItem> findByCategory(
        @RequestParam("category") String category);

    @PostExchange(
        contentType = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<CatalogItem>> create(
        @RequestBody CreateCatalogItem request);

    @DeleteExchange("/{id}")
    Mono<Void> delete(
        @PathVariable("id") String id);
}
~~~

Interface mô tả bốn operation:
- GET một item theo ID và gửi request ID.
- GET danh sách theo category bằng query parameter.
- POST một item và nhận status/header/body.
- DELETE một item, chỉ cần biết khi request hoàn tất.

Caller không cần biết đường dẫn đầy đủ hay cách decode JSON; tất cả được tập trung trong contract.

### 11.7. CatalogClientConfiguration.java

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    CatalogHttpService catalogHttpService(
            WebClient.Builder builder,
            @Value("${catalog.base-url}") String baseUrl) {

        WebClient webClient = builder
            .baseUrl(baseUrl)
            .build();

        WebClientAdapter adapter =
            WebClientAdapter.create(webClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpService.class);
    }
}
~~~

Đây là phần tích hợp quan trọng:
- WebClient Builder nhận base URL từ property.
- Adapter nối WebClient với HTTP service infrastructure.
- Factory tạo proxy cho interface.
- Spring quản lý proxy như một bean để các service khác inject.

Không tạo factory trong mỗi method call. Một proxy bean có thể phục vụ nhiều request đồng thời; connection pool và reactive execution thuộc underlying WebClient.

### 11.8. CatalogHttpServiceTest.java

~~~java
package com.example.catalog;

import java.io.IOException;
import java.net.URI;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CatalogHttpServiceTest {

    private static final MockWebServer SERVER = startServer();

    @Autowired
    CatalogHttpService catalog;

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        }
        catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> SERVER.url("/").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        SERVER.shutdown();
    }

    @Test
    void getByIdMapsPathAndHeader() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "id": "42",
                  "name": "Keyboard",
                  "category": "hardware"
                }
                """));

        CatalogItem item = catalog
            .getById("42", "request-001")
            .block(Duration.ofSeconds(3));

        assertNotNull(item);
        assertEquals("42", item.id());
        assertEquals("Keyboard", item.name());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/api/catalog/42", request.getPath());
        assertEquals(
            "request-001",
            request.getHeader("X-Request-Id"));
        assertEquals(
            "application/json",
            request.getHeader("Accept"));
    }

    @Test
    void queryParameterAndFluxResponseAreMapped() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("""
                [
                  {"id":"1","name":"Keyboard","category":"books"},
                  {"id":"2","name":"Mouse","category":"books"}
                ]
                """));

        var items = catalog.findByCategory("books")
            .collectList()
            .block(Duration.ofSeconds(3));

        assertNotNull(items);
        assertEquals(2, items.size());
        assertEquals("Keyboard", items.get(0).name());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals(
            "/api/catalog?category=books",
            request.getPath());
    }

    @Test
    void postMapsJsonBodyAndReturnsLocation() throws Exception {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(201)
            .addHeader("Content-Type", "application/json")
            .addHeader("Location", "/api/catalog/99")
            .setBody("""
                {
                  "id": "99",
                  "name": "Keyboard",
                  "category": "hardware"
                }
                """));

        var response = catalog.create(
            new CreateCatalogItem("Keyboard", "hardware"))
            .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(201, response.getStatusCode().value());
        assertEquals(
            URI.create("/api/catalog/99"),
            response.getHeaders().getLocation());
        assertNotNull(response.getBody());
        assertEquals("99", response.getBody().id());

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("POST", request.getMethod());
        assertEquals("/api/catalog", request.getPath());
        assertTrue(request.getHeader("Content-Type")
            .startsWith("application/json"));

        String json = request.getBody().readUtf8();
        assertTrue(json.contains("\"name\":\"Keyboard\""));
        assertTrue(json.contains("\"category\":\"hardware\""));
    }

    @Test
    void notFoundStatusBecomesWebClientException() {
        SERVER.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/problem+json")
            .setBody("""
                {"title":"Not Found","status":404}
                """));

        WebClientResponseException error = assertThrows(
            WebClientResponseException.class,
            () -> catalog.getById("missing", "request-404")
                .block(Duration.ofSeconds(3)));

        assertEquals(404, error.getStatusCode().value());
    }

    @Test
    void deleteCompletesAfterNoContentResponse() throws Exception {
        SERVER.enqueue(new MockResponse().setResponseCode(204));

        catalog.delete("42").block(Duration.ofSeconds(3));

        RecordedRequest request =
            SERVER.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("DELETE", request.getMethod());
        assertEquals("/api/catalog/42", request.getPath());
    }
}
~~~

Các test kiểm tra request/response thực qua HTTP:
- `@PathVariable` tạo đúng path.
- `@RequestHeader` gửi đúng header.
- `@RequestParam` tạo query string.
- `Flux<CatalogItem>` decode JSON array.
- `@RequestBody` serialize DTO thành JSON.
- `Mono<ResponseEntity<T>>` giữ status và Location.
- Status 404 mặc định phát `WebClientResponseException`.
- `Mono<Void>` hoàn tất sau khi nhận 204.

`block()` chỉ xuất hiện trong test để lấy kết quả đồng bộ cho assertion. Production code nên compose `Mono`/`Flux` thay vì block.

### 11.9. Chạy test

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Test tự khởi động MockWebServer và đóng nó sau khi hoàn tất. Khi chạy ứng dụng bình thường, property `catalog.base-url` phải trỏ tới HTTP service thật.

## 12. So sánh cách gọi proxy và WebClient trực tiếp

Cả hai cách đều dùng chung WebClient connector, codec và filter. Sự khác nhau chủ yếu là nơi khai báo request.

HTTP Service interface:

~~~java
catalog.getById("42", requestId);
~~~

WebClient trực tiếp:

~~~java
webClient.get()
    .uri("/api/catalog/{id}", "42")
    .header("X-Request-Id", requestId)
    .retrieve()
    .bodyToMono(CatalogItem.class);
~~~

Proxy giúp endpoint contract có tên, dễ inject và mock. WebClient trực tiếp cho phép caller điều khiển từng bước request/response. Có thể dùng cả hai trong một ứng dụng: interface cho API ổn định, WebClient trực tiếp cho operation cần `exchangeToMono`/`exchangeToFlux` hoặc logic protocol đặc thù.

### 12.1. Không mất khả năng tùy biến WebClient

Tạo proxy không có nghĩa là từ bỏ:
- `ExchangeFilterFunction`.
- Custom codecs và `maxInMemorySize`.
- TLS, proxy, connection pool và connector.
- Default headers/cookies.
- Metrics, observations và tracing.
- OAuth2 authorized client filter.
- Default status handlers.

Tất cả cấu hình trên WebClient được dùng bởi các method của interface proxy dựa trên adapter đó.

## 13. Nhiều HTTP service và HTTP Service Groups

Một ứng dụng thường gọi nhiều downstream host. Không nên dùng một base URL duy nhất cho mọi interface nếu chúng thuộc các hệ thống khác nhau.

Một cách thủ công là tạo mỗi nhóm client riêng:
- `CatalogHttpService` dùng WebClient tới catalog host.
- `BillingHttpService` dùng WebClient tới billing host.
- `IdentityHttpService` dùng WebClient có OAuth2 filter và timeout riêng.

Mỗi proxy có thể dùng factory/adapter khác nhau nhưng vẫn giữ contract interface độc lập.

Từ Spring Framework 7.0, có thêm HTTP Service Groups để đăng ký nhiều interface thành proxy bean theo nhóm. Một nhóm thường chia sẻ cùng client setup và `HttpServiceProxyFactory`; có thể khai báo bằng `@ImportHttpServices` hoặc registrar. Cách này giảm cấu hình lặp khi ứng dụng có nhiều interface và nhiều host. Với ứng dụng nhỏ, tạo bean thủ công như ví dụ ở trên vẫn dễ theo dõi.

## 14. Những điểm cần lưu ý về contract

### 14.1. Client và server có thể chia sẻ interface, nhưng phải cân nhắc coupling

Spring cũng hỗ trợ `@HttpExchange` trên interface được `@Controller` implement ở phía server. Điều đó có thể hữu ích với API nội bộ khi client và server cần chia sẻ contract.

Tuy nhiên, chia sẻ interface cũng tạo coupling giữa hai ứng dụng:
- Thay đổi method có thể buộc client/server deploy cùng nhịp.
- DTO có thể không phù hợp với cả hai bounded context.
- Annotation client và validation/server concern có thể khác nhau.
- Public API thường cần versioning và compatibility độc lập.

Không nên mặc định dùng chung Java interface cho mọi public API. Có thể chia sẻ OpenAPI/schema hoặc contract test mà không chia sẻ toàn bộ code.

### 14.2. `@HttpExchange` và `@RequestMapping` không có cùng mục đích

`@HttpExchange` mô tả một operation HTTP cụ thể cho client interface. `@RequestMapping` ở server có thể biểu diễn nhiều điều kiện mapping hơn như method, path, params, headers, consumes và produces. Spring cho phép dùng `@HttpExchange` cho server controller method trong một số trường hợp, nhưng client interface không phải một controller tự động được đăng ký.

### 14.3. Tên parameter phải rõ

Nên viết:

~~~java
@GetExchange("/{id}")
Mono<CatalogItem> get(
    @PathVariable("id") String id);
~~~

Tránh phụ thuộc tên parameter được compiler giữ lại. Khi refactor method hoặc build với compiler option khác, annotation có tên tường minh giúp contract ổn định.

### 14.4. Body response phải được tiêu thụ

- `Mono<T>` decode một object.
- `Flux<T>` tiêu thụ response body theo stream.
- `Mono<Void>` không trả body nhưng response content vẫn được giải phóng.
- `Mono<ResponseEntity<Flux<T>>>` trả headers trước, caller chịu trách nhiệm consume stream.

Không bỏ một response Publisher chưa subscribe. Điều đó có thể giữ connection/buffer hoặc khiến request chưa thực sự được thực hiện vì reactive pipeline là lazy.

## 15. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tạo interface nhưng quên tạo proxy bean | Không inject được HTTP service | Tạo WebClientAdapter, factory và `createClient(...)` |
| Dùng `@HttpExchange` như thể nó tự gọi HTTP | Không có request nào được gửi | Cần adapter và `HttpServiceProxyFactory` |
| Đặt base URL production trong annotation | Khó đổi môi trường và test | Đặt base URL trên WebClient từ property |
| Thiếu `@PathVariable` hoặc tên không khớp | URI không được expand như mong muốn | Khai báo tên placeholder tường minh |
| Dùng `@RequestParam` nhưng tưởng nó là JSON body | Query/form encoding không đúng | Dùng `@RequestBody` cho JSON; cấu hình form content type khi cần |
| Chọn `T` đồng bộ trong reactive request path | Có thể block caller/event-loop | Dùng `Mono<T>` hoặc `Flux<T>` |
| Chọn `Mono<T>` cho response nhiều phần tử | Không biểu diễn đúng cardinality | Dùng `Flux<T>` hoặc DTO wrapper nếu API trả một object chứa list |
| Mong `ResponseEntity` tự bỏ qua mọi 404 | Mặc định status handler có thể phát exception | Custom status handler hoặc adapter decorator có chủ đích |
| Catch mọi exception rồi trả `Mono.empty()` | Che mất lỗi 401/500 và làm mất nguyên nhân | Map theo status/domain error cụ thể |
| Retry mọi POST | Tạo resource trùng khi server đã xử lý lần đầu | Idempotency key và retry policy rõ |
| Log toàn bộ WebClient request | Lộ token, cookie, PII hoặc body | Allowlist log field và redact credential |
| Tạo factory cho từng method call | Tốn cấu hình, khó quản lý lifecycle | Đăng ký proxy singleton bean |
| Dùng chung một WebClient cho mọi trust boundary | Credential/filter có thể bị gửi nhầm host | Client riêng cho từng host/policy |
| Chỉ mock interface trong test | Không kiểm tra annotation mapping thật | Thêm MockWebServer HTTP integration tests |
| Không cấu hình timeout | Request có thể giữ tài nguyên quá lâu | Timeout connector và operation phù hợp |
| Không consume `Flux` response | Request lazy hoặc connection chưa được giải phóng | Subscribe/compose body trong caller |

## 16. Quy trình debug khi proxy gọi sai API

1. Xác nhận đúng interface class được tạo proxy và bean được inject.
2. Kiểm tra base URL từ property/profile hiện tại.
3. Kiểm tra type-level `@HttpExchange` và method-level exchange annotation.
4. Kiểm tra tên path variable, query parameter, request header và Content-Type.
5. Kiểm tra `WebClient.Builder` có filter/default header/codec nào can thiệp request không.
6. Kiểm tra `RecordedRequest` ở MockWebServer để biết request thực sự được gửi.
7. Nếu response lỗi, xem status và exception type của WebClient; không chỉ đọc message.
8. Nếu body không decode, kiểm tra response Content-Type, JSON schema và codec configuration.
9. Nếu request treo, kiểm tra subscription, timeout, remote response body và connection pool.
10. Nếu chỉ lỗi ở production, so sánh base URL, TLS, proxy, DNS và authentication config giữa các profile.

Dùng HTTP wire logging có kiểm soát trong test/staging. Không bật log body/Authorization header rộng rãi trong production.

## 17. Checklist production

- [ ] Mỗi interface đại diện cho một downstream API có contract rõ.
- [ ] Type-level base path và method-level path được khai báo nhất quán.
- [ ] Path variable, query, header, cookie và body có annotation/name rõ ràng.
- [ ] Return type phản ánh đúng cardinality và reactive lifecycle.
- [ ] WebClientAdapter và HttpServiceProxyFactory được tạo một lần trong cấu hình.
- [ ] Proxy được đăng ký thành bean và inject qua constructor.
- [ ] Base URL, TLS, credentials và timeout đến từ cấu hình môi trường.
- [ ] WebClient filter chỉ thêm header tới đúng trust boundary.
- [ ] Status 4xx/5xx được map thành domain error phù hợp.
- [ ] Retry chỉ áp dụng cho lỗi transient và operation an toàn.
- [ ] Response body stream luôn được consume hoặc giải phóng.
- [ ] Logging không ghi raw credential, cookie hoặc request body.
- [ ] HTTP integration tests xác nhận method/path/query/header/body/status.
- [ ] Có test cho 404, 5xx, timeout và malformed response theo nhu cầu.
- [ ] Có compatibility/versioning strategy cho remote DTO/API.
- [ ] Dùng HTTP Service Groups khi số lượng interface/client configuration đủ lớn để cần quản lý theo nhóm.

## 18. Bài tập thực hành

**Bài 1 – GET proxy.** Tạo `CatalogHttpService` với `@GetExchange("/{id}")`. Dùng MockWebServer xác nhận path variable và JSON response.

**Bài 2 – Query.** Tạo `findByCategory` nhận `@RequestParam`; kiểm tra query string và decode response thành `Flux<CatalogItem>`.

**Bài 3 – Header.** Truyền `X-Request-Id` bằng `@RequestHeader`. Xác nhận giá trị ở RecordedRequest.

**Bài 4 – POST.** Tạo method nhận `@RequestBody`, trả `Mono<ResponseEntity<T>>`. Kiểm tra JSON body, 201 và Location.

**Bài 5 – DELETE.** Trả `Mono<Void>` và xác nhận response 204 được tiêu thụ đúng.

**Bài 6 – Error mapping.** Gửi 404 và 503 từ mock server. Map 404 thành domain not-found; giữ 503 là dependency failure.

**Bài 7 – Filter.** Thêm `ExchangeFilterFunction` gắn client name và correlation ID. Kiểm tra header trong mock server.

**Bài 8 – Timeout.** Cấu hình response timeout ngắn; dùng mock server delay để xác nhận timeout error được map đúng.

**Bài 9 – Streaming.** Khai báo `Flux<CatalogEvent>` cho NDJSON/SSE. Kiểm tra caller tiêu thụ stream theo demand.

**Bài 10 – Nhiều host.** Tạo Catalog và Billing interface, mỗi interface dùng WebClient base URL và authentication policy riêng.

## 19. Tài liệu tham khảo chính thức

1. Spring Framework 7.0.8 – REST Clients và HTTP Service Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
2. Spring Framework 7.0.8 – `WebClient` và reactive client: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
3. Spring Framework Javadoc – `WebClientAdapter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/support/WebClientAdapter.html
4. Spring Framework Javadoc – `HttpServiceProxyFactory`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/invoker/HttpServiceProxyFactory.html
5. Spring Framework Javadoc – `HttpExchange` và method annotations: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/service/annotation/HttpExchange.html
6. Spring Framework – WebClient filters: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
7. Spring Framework – WebClient exchange and response handling: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
8. Spring Boot 4.0 – Calling REST Services: https://docs.spring.io/spring-boot/4.0/reference/io/rest-client.html
9. Reactor Core – Reference Guide: https://projectreactor.io/docs/core/release/reference/

**Tự đánh giá cuối:** `@HttpExchange` mô tả điều gì, và thành phần nào tạo implementation cho interface? Vì sao `WebClientAdapter` vẫn cần WebClient được cấu hình? Khi nào chọn `Mono<ResponseEntity<T>>` thay vì `Mono<T>`? Vì sao `Flux<T>` phù hợp với response stream và caller phải consume body? Nếu kiểm tra được request thật qua MockWebServer, bạn đã xác nhận contract interface đang được ánh xạ đúng thành HTTP.
