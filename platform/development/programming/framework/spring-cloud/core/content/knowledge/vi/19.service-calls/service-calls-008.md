# Phân biệt lời gọi blocking và reactive

Một ứng dụng Spring Cloud thường phải gọi các dịch vụ khác qua HTTP hoặc một giao thức mạng tương tự. Có thể thực hiện lời gọi theo mô hình **blocking**: thread gọi chờ cho tới khi nhận kết quả; hoặc theo mô hình **reactive**: ứng dụng mô tả một pipeline bất đồng bộ, thread không phải chờ I/O hoàn tất và kết quả được phát qua `Mono` hoặc `Flux`.

Sự khác nhau này nằm ở cách ứng dụng tổ chức việc chờ và xử lý kết quả. Nó độc lập với câu hỏi dịch vụ được tìm ở đâu. Spring Cloud Discovery cung cấp danh sách instance; Spring Cloud LoadBalancer chọn instance; HTTP client thực hiện request. Một client blocking và một client reactive đều có thể dùng service ID để gọi dịch vụ qua LoadBalancer.

Trong hệ sinh thái Spring, `RestClient` là HTTP client đồng bộ với API fluent; `WebClient` là client non-blocking, reactive và hỗ trợ Reactive Streams backpressure. `RestTemplate` vẫn xuất hiện trong nhiều ứng dụng hiện hữu, nhưng Spring Framework 7.0 đã đánh dấu nó deprecated để chuyển sang `RestClient`. Khi chọn API, cần đối chiếu Spring Boot và Spring Cloud release train mà dự án đang dùng.

Bài học thuộc chương **Gọi dịch vụ** của module **SPRING_CLOUD_CORE**. Người học sẽ hiểu mô hình thực thi, cách tích hợp Spring Cloud LoadBalancer với client blocking/reactive, cách xử lý timeout, lỗi, retry, cancellation và kiểm thử lời gọi dịch vụ trong hệ thống phân tán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích một lời gọi blocking giữ thread trong lúc chờ I/O như thế nào.
2. Mô tả `Mono`, `Flux`, subscription và backpressure trong lời gọi reactive.
3. Phân biệt `RestClient`, `RestTemplate` và `WebClient`.
4. Chọn mô hình gọi phù hợp với Spring MVC, Spring WebFlux và các thư viện mà ứng dụng sử dụng.
5. Tích hợp blocking client và reactive client với Spring Cloud LoadBalancer bằng service ID.
6. Tránh chặn event-loop bằng `.block()` hoặc lời gọi thư viện blocking.
7. Thiết kế timeout, error mapping, retry, cancellation và deadline cho lời gọi downstream.
8. Kết hợp nhiều lời gọi dịch vụ theo thứ tự hoặc đồng thời.
9. Kiểm thử response, lỗi HTTP, timeout và hành vi load balancing.
10. Nhận diện các lỗi vận hành như thread pool cạn, retry storm và gọi nhầm instance.

## 2. Một lời gọi dịch vụ gồm những bước nào?

Giả sử `orders-service` cần lấy tồn kho từ `inventory-service`. Trong môi trường có nhiều instance, client thường không gọi một hostname cố định. Nó dùng service ID logic, sau đó Spring Cloud LoadBalancer phối hợp với discovery để chọn một instance.

~~~mermaid
flowchart TD
    A[Orders service] --> B[HTTP client]
    B --> C{Mô hình thực thi}
    C -->|Blocking| D[RestClient / RestTemplate]
    C -->|Reactive| E[WebClient]
    D --> F[Spring Cloud LoadBalancer]
    E --> F
    F --> G[DiscoveryClient / ServiceInstanceListSupplier]
    G --> H[Chọn instance]
    H --> I[HTTP request qua network]
    I --> J[Inventory instance]
    J --> K[HTTP response]
    K --> B
~~~

Có ba trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `DiscoveryClient` | Đọc các `ServiceInstance` mà registry công bố |
| Spring Cloud LoadBalancer | Chọn instance phù hợp cho request |
| HTTP client | Gửi request, nhận response và chuyển đổi body |

Blocking hay reactive là cách HTTP client phối hợp với thread và kết quả. Nó không quyết định registry nào được dùng hoặc service có bao nhiêu instance.

### 2.1. Service ID thay cho địa chỉ cố định

Một request có thể dùng URL:

~~~text
http://inventory-service/api/items/SKU-100
~~~

`inventory-service` là service ID. Khi client được cấu hình load-balanced, LoadBalancer tìm instance tương ứng, ví dụ:

~~~text
inventory-service
  ├── 10.0.1.12:8080
  ├── 10.0.1.13:8080
  └── 10.0.1.14:8080
~~~

Nếu code gọi trực tiếp `http://10.0.1.12:8080`, nó đã bỏ qua việc chọn instance theo service ID. URL dạng service ID chỉ được phân giải khi client có integration LoadBalancer phù hợp.

## 3. Lời gọi blocking hoạt động như thế nào?

### 3.1. Thread chờ kết quả

Với client blocking, thread gọi thực hiện request rồi chờ cho tới khi nhận response, lỗi hoặc timeout. Trong thời gian chờ network, thread đó không thể xử lý một công việc khác.

Ví dụ:

~~~java
StockResponse response = restClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

Khi phương thức `body(...)` trả về, response đã được đọc và chuyển đổi thành `StockResponse`, hoặc lời gọi đã ném exception. Luồng điều khiển đi tiếp theo kiểu tuần tự thông thường.

### 3.2. Blocking tạo áp lực lên thread pool

Giả sử một request cần gọi downstream trong 800 ms. Nếu 100 request cùng lúc đều chờ một downstream chậm, nhiều thread sẽ bị giữ trong thời gian đó.

Trong Spring MVC với servlet container, thread pool có thể hấp thụ blocking I/O, nhưng số thread vẫn hữu hạn. Nếu mọi thread đều đang chờ downstream, request mới có thể phải xếp hàng hoặc bị từ chối.

Một mô hình đơn giản:

~~~mermaid
flowchart TD
    A[Request 1] --> T1[Servlet thread 1]
    B[Request 2] --> T2[Servlet thread 2]
    C[Request 3] --> T3[Servlet thread 3]
    T1 --> W1[Chờ HTTP response]
    T2 --> W2[Chờ HTTP response]
    T3 --> W3[Chờ HTTP response]
    W1 --> R[Tiếp tục xử lý]
    W2 --> R
    W3 --> R
~~~

Blocking không phải lúc nào cũng xấu. Với tải vừa phải, luồng nghiệp vụ tuần tự và thư viện đồng bộ, nó dễ đọc, dễ debug và dễ tích hợp. Điều quan trọng là đặt timeout, giới hạn concurrency và sizing thread pool phù hợp.

### 3.3. API blocking trong Spring

**`RestClient`** là lựa chọn đồng bộ với API fluent, được giới thiệu trong Spring Framework 6.1. Nó phù hợp cho ứng dụng cần gọi HTTP theo kiểu imperative.

~~~java
RestClient restClient = RestClient.builder()
        .baseUrl("https://inventory.internal")
        .build();

StockResponse stock = restClient.get()
        .uri("/api/items/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**`RestTemplate`** là client đồng bộ kiểu template đã được dùng lâu năm. Nó vẫn có mặt trong nhiều hệ thống Spring Boot cũ. Theo tài liệu Spring Framework 7.0, `RestTemplate` đã deprecated để chuyển sang `RestClient`; với dự án đang dùng Framework 5.x hoặc 6.x, hãy đối chiếu API và lộ trình nâng cấp của phiên bản đó.

~~~java
StockResponse stock = restTemplate.getForObject(
        "http://inventory-service/api/items/{sku}",
        StockResponse.class,
        sku
);
~~~

Không nhầm việc client có API fluent hay template method với chất lượng network. Cả hai đều là lời gọi đồng bộ.

## 4. Lời gọi reactive hoạt động như thế nào?

### 4.1. Trả về publisher thay vì kết quả tức thời

`WebClient` là HTTP client non-blocking, reactive. Phương thức gọi thường trả về `Mono<T>` hoặc `Flux<T>` thay vì trả trực tiếp object.

~~~java
Mono<StockResponse> stockMono = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

`Mono<StockResponse>` biểu diễn một kết quả có thể đến sau, có thể hoàn tất mà không có giá trị hoặc kết thúc bằng lỗi. `Flux<StockResponse>` biểu diễn một chuỗi có thể phát không, một hoặc nhiều phần tử.

| Kiểu | Ý nghĩa |
| --- | --- |
| `Mono<T>` | Không hoặc một giá trị kiểu `T`, sau đó complete hoặc error |
| `Flux<T>` | Không, một hoặc nhiều giá trị kiểu `T`, sau đó complete hoặc error |

### 4.2. Subscription kích hoạt pipeline

Với WebClient, pipeline thường được thực thi khi có subscriber. Tạo `Mono` chỉ mô tả công việc; nó chưa nhất thiết gửi request ngay tại dòng tạo biến.

~~~java
Mono<StockResponse> stockMono = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);

// Request được thực thi khi pipeline được subscribe.
return stockMono;
~~~

Trong controller WebFlux, trả publisher cho framework là cách thông thường:

~~~java
@GetMapping("/items/{sku}/stock")
Mono<StockResponse> getStock(@PathVariable String sku) {
    return inventoryClient.getStock(sku);
}
~~~

Không cần gọi `subscribe()` thủ công trong controller. Framework sẽ subscribe và quản lý kết quả theo lifecycle của request.

### 4.3. Non-blocking I/O và event-loop

Trong WebFlux, các thread xử lý request thường ít hơn mô hình servlet thread-per-request. Event-loop xử lý nhiều kết nối bằng cách đăng ký quan tâm tới sự kiện I/O rồi tiếp tục công việc khác thay vì giữ một thread chờ mỗi socket.

~~~mermaid
sequenceDiagram
    participant App as WebFlux handler
    participant Loop as Event-loop
    participant Net as Network
    participant Remote as Inventory service

    App->>Loop: Tạo và subscribe WebClient pipeline
    Loop->>Net: Gửi request
    Loop-->>App: Trả quyền điều khiển, tiếp tục việc khác
    Net->>Remote: HTTP request
    Remote-->>Net: HTTP response
    Net-->>Loop: I/O completion event
    Loop->>App: Tiếp tục pipeline
    App-->>App: Trả kết quả reactive
~~~

Thread không phải ngồi chờ response trong suốt thời gian network. Điều này giúp tận dụng tài nguyên tốt khi có nhiều lời gọi I/O đồng thời, nhưng không làm downstream tự nhiên nhanh hơn.

### 4.4. Backpressure

Reactive Streams có cơ chế backpressure để subscriber báo lượng dữ liệu nó sẵn sàng nhận. Điều này quan trọng khi response là stream lớn hoặc producer nhanh hơn consumer.

Ví dụ:

~~~java
Flux<ServerSentEvent<StockUpdate>> updates =
        webClient.get()
                .uri("http://inventory-service/api/stock/stream")
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<>() {});
~~~

Consumer có thể xử lý từng phần tử thay vì chờ tải toàn bộ nội dung vào một collection. Tuy nhiên, backpressure chỉ có tác dụng khi các thành phần trong pipeline và transport hỗ trợ truyền tín hiệu demand phù hợp; nó không phải giới hạn kích thước response tự động.

### 4.5. Reactive không có nghĩa là mọi thứ đều chạy song song

Một pipeline reactive có thể thực hiện các bước tuần tự, đồng thời hoặc theo luồng dữ liệu. Việc dùng `Mono` không tự tạo thread mới cho mỗi thao tác. Reactor quyết định thread theo nguồn phát, scheduler và các operator điều phối.

Không nên thêm `subscribeOn` hoặc `publishOn` ở mọi nơi theo thói quen. Chỉ chuyển scheduler khi có lý do cụ thể, ví dụ cần cách ly một thư viện blocking.

## 5. So sánh blocking và reactive

| Tiêu chí | Blocking | Reactive |
| --- | --- | --- |
| Giá trị trả về | Object/`ResponseEntity` trực tiếp | `Mono<T>` hoặc `Flux<T>` |
| Khi chờ I/O | Thread gọi bị giữ | Thread có thể xử lý việc khác |
| Mô hình xử lý | Imperative, tuần tự | Pipeline, callback và tín hiệu |
| Concurrency | Thường dựa trên thread pool | Non-blocking I/O, event-loop và backpressure |
| Xử lý lỗi | Exception tại điểm gọi | Error signal trong publisher |
| Hủy lời gọi | Phụ thuộc interruption và HTTP client | Cancellation signal có thể truyền ngược pipeline |
| Debug | Luồng điều khiển trực tiếp | Cần hiểu subscription, operator và scheduler |
| Phù hợp | Ứng dụng đồng bộ, MVC, thư viện blocking | WebFlux và hệ thống I/O reactive end-to-end |

### 5.1. Không có lựa chọn tốt nhất cho mọi ứng dụng

Chọn blocking khi:

- Ứng dụng dùng Spring MVC và phần lớn thư viện là blocking.
- Tải đồng thời ở mức phù hợp với thread pool.
- Luồng nghiệp vụ đơn giản và dễ bảo trì là ưu tiên.
- Đội ngũ đang dùng các thư viện JDBC hoặc SDK đồng bộ.

Chọn reactive khi:

- Ứng dụng dùng WebFlux và nhiều dependency có API non-blocking.
- Có nhiều kết nối I/O đồng thời hoặc cần streaming.
- Muốn phối hợp nhiều lời gọi bất đồng bộ mà không giữ thread chờ.
- Có khả năng kiểm soát scheduler, cancellation, context và backpressure.

Không chuyển toàn bộ ứng dụng sang WebFlux chỉ vì một downstream cần `WebClient`. Spring MVC có thể dùng WebClient. Ngược lại, nếu ứng dụng WebFlux gọi JPA/JDBC blocking trên event-loop, lợi ích non-blocking có thể bị phá vỡ.

### 5.2. Chi phí của mô hình reactive

Reactive có thể giảm số thread cần giữ trong lúc I/O, nhưng đi kèm chi phí thiết kế:

- Phải hiểu publisher và thời điểm subscription.
- Cần xử lý error signal trong pipeline.
- Phải quan tâm cancellation và timeout.
- Thread-local context không tự truyền như trong mô hình imperative.
- Debug stack trace và operator chain có thể phức tạp hơn.
- Một thư viện blocking có thể làm nghẽn event-loop nếu không được cách ly.

Chọn reactive khi đặc tính tải và hệ sinh thái thư viện có lợi ích rõ ràng, không chỉ vì API trả `Mono`.

## 6. Gọi dịch vụ blocking qua Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cung cấp tích hợp blocking cho `RestClient` và `RestTemplate`. Khi client được đánh dấu `@LoadBalanced`, URL dùng service ID có thể được phân giải thành một `ServiceInstance`.

### 6.1. Dependency

Với Maven, thêm LoadBalancer starter tương thích với Spring Cloud BOM:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Discovery provider tương ứng, ví dụ Eureka hoặc Consul, cần có nếu muốn lấy instance từ registry động. Trong test hoặc local, có thể dùng `SimpleDiscoveryClient` với danh sách instance tĩnh.

### 6.2. Cấu hình RestClient

Trong Spring Boot có hỗ trợ `RestClient.Builder`, khai báo builder load-balanced:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Tạo client dùng builder đó:

~~~java
@Component
class InventoryBlockingClient {

    private final RestClient restClient;

    InventoryBlockingClient(
            @LoadBalanced RestClient.Builder builder
    ) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

`@LoadBalanced` là qualifier để Spring Cloud áp dụng tích hợp LoadBalancer cho builder. `inventory-service` là service ID, không phải DNS hostname thông thường. `BlockingLoadBalancerClient` thực hiện lựa chọn instance trước khi HTTP request được gửi.

Với phiên bản Spring Boot/Spring Cloud cũ chưa hỗ trợ tích hợp `RestClient`, dùng `RestTemplate` theo hướng dẫn đúng release train. Không tự thêm version riêng cho starter; để BOM tương thích quản lý.

### 6.3. RestTemplate trong ứng dụng hiện hữu

Ví dụ cấu hình legacy:

~~~java
@Bean
@LoadBalanced
RestTemplate restTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Sau đó gọi bằng service ID:

~~~java
StockResponse response = restTemplate.getForObject(
        "http://inventory-service/api/items/{sku}",
        StockResponse.class,
        sku
);
~~~

Đây vẫn là blocking call. `@LoadBalanced` bổ sung phân giải service ID và chọn instance; nó không biến `RestTemplate` thành reactive client.

## 7. Gọi dịch vụ reactive qua Spring Cloud LoadBalancer

### 7.1. Cấu hình WebClient.Builder

Với `WebClient`, Spring Cloud LoadBalancer cung cấp integration reactive. Cách thường dùng là builder được đánh dấu `@LoadBalanced`:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryReactiveHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Tạo client:

~~~java
@Component
class InventoryReactiveClient {

    private final WebClient webClient;

    InventoryReactiveClient(
            @LoadBalanced WebClient.Builder builder
    ) {
        this.webClient = builder.build();
    }

    Mono<StockResponse> getStock(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
~~~

Spring Cloud tích hợp `ReactorLoadBalancerExchangeFilterFunction` vào WebClient builder để chọn instance theo service ID. Request trả về `Mono`; caller tiếp tục compose hoặc trả publisher cho framework.

### 7.2. Cấu hình filter function tường minh

Trong trường hợp cần tự cấu hình WebClient, có thể dùng filter function do Spring Cloud cung cấp:

~~~java
@Bean
WebClient loadBalancedWebClient(
        ReactorLoadBalancerExchangeFilterFunction loadBalancerFilter
) {
    return WebClient.builder()
            .filter(loadBalancerFilter)
            .build();
}
~~~

Đây là integration reactive. Không dùng `BlockingLoadBalancerClient` trong WebFlux pipeline để thay thế filter này.

### 7.3. Discovery và LoadBalancer làm việc ở đâu?

Khi `WebClient` gửi request tới `http://inventory-service/...`:

1. Filter LoadBalancer nhận request.
2. Xác định service ID `inventory-service`.
3. Lấy danh sách instance từ `ServiceInstanceListSupplier`, thường dựa trên DiscoveryClient.
4. Chọn một instance theo cấu hình chiến lược.
5. Thay service ID bằng host/port của instance đã chọn.
6. HTTP connector thực hiện I/O non-blocking.
7. Response được chuyển vào reactive pipeline.

Việc chọn instance và việc gửi HTTP là hai bước riêng. Nếu không tìm thấy instance, LoadBalancer không thể tạo request tới một địa chỉ hợp lệ; cần xử lý lỗi tương ứng.

## 8. Không chặn event-loop bằng lời gọi blocking

### 8.1. Vì sao `.block()` nguy hiểm trong WebFlux?

Đoạn mã:

~~~java
StockResponse stock = webClient.get()
        .uri("http://inventory-service/api/items/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class)
        .block();
~~~

chuyển lời gọi reactive thành thao tác chờ đồng bộ. Nếu chạy trên thread non-blocking như Reactor Netty event-loop, nó có thể gây lỗi runtime hoặc làm nghẽn các request khác.

Không gọi `.block()`, `.blockFirst()` hoặc `.blockLast()` trong WebFlux handler hoặc pipeline đang chạy trên non-blocking thread.

### 8.2. Trả publisher tới ranh giới web

Thay vì block:

~~~java
@GetMapping("/items/{sku}/stock")
Mono<StockResponse> getStock(@PathVariable String sku) {
    return inventoryClient.getStock(sku);
}
~~~

Spring WebFlux quản lý subscription và response lifecycle. Lỗi được truyền qua reactive pipeline và có thể được xử lý bằng `onErrorResume`, `onErrorMap` hoặc exception handler phù hợp.

### 8.3. Khi phải gọi thư viện blocking

Nếu một thư viện cũ chỉ có API blocking và chưa thể thay thế, cách ly lời gọi khỏi event-loop:

~~~java
Mono<LegacyResult> callLegacy(LegacyRequest request) {
    return Mono.fromCallable(() -> legacyClient.execute(request))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` phù hợp hơn event-loop cho công việc blocking có giới hạn. Tuy nhiên:

- Cần đặt timeout cho thư viện blocking.
- Cần giới hạn concurrency và kích thước công việc.
- Cần xử lý interruption nếu thư viện hỗ trợ.
- Không tạo một scheduler mới cho mỗi request.
- Không xem việc bọc bằng `Mono.fromCallable` là biến I/O blocking thành non-blocking.

Nếu phần lớn hệ thống phụ thuộc JDBC/JPA và SDK blocking, Spring MVC có thể là lựa chọn đơn giản hơn WebFlux.

## 9. Ghép nhiều lời gọi dịch vụ

Một request nghiệp vụ có thể cần gọi nhiều downstream. Reactive cho phép biểu diễn quan hệ phụ thuộc giữa các lời gọi mà không phải chặn thread chờ từng response.

### 9.1. Lời gọi tuần tự khi có phụ thuộc

Ví dụ cần lấy thông tin đơn hàng trước, sau đó mới lấy tồn kho:

~~~java
Mono<Order> orderMono = orderClient.getOrder(orderId);

return orderMono.flatMap(order ->
        inventoryClient.getStock(order.sku())
                .map(stock -> new OrderView(order, stock))
);
~~~

`flatMap` chỉ gọi inventory sau khi nhận được order. Đây là luồng tuần tự theo dependency dữ liệu.

### 9.2. Lời gọi độc lập có thể chạy đồng thời

Nếu cần lấy giá và tồn kho độc lập:

~~~java
Mono<Price> priceMono = pricingClient.getPrice(sku);
Mono<StockResponse> stockMono = inventoryClient.getStock(sku);

return Mono.zip(priceMono, stockMono)
        .map(tuple -> new ProductView(
                tuple.getT1(),
                tuple.getT2()
        ));
~~~

`Mono.zip` subscribe các publisher và kết hợp kết quả khi chúng hoàn tất. Hai lời gọi I/O có thể tiến hành đồng thời; tổng thời gian thường bị chi phối bởi lời gọi chậm hơn thay vì tổng thời gian của cả hai, nếu transport và downstream cho phép chạy song song.

Nếu một publisher lỗi, `zip` thường kết thúc bằng lỗi đó và hủy các publisher còn lại theo quy tắc reactive. Hãy xác định rõ nghiệp vụ có cần fallback cho một phần kết quả hay không.

### 9.3. Nhiều phần tử với `flatMap`

Khi xử lý danh sách SKU:

~~~java
Flux<StockResponse> stocks =
        Flux.fromIterable(skus)
                .flatMap(inventoryClient::getStock, 8);
~~~

Tham số `8` giới hạn số inner publisher được subscribe đồng thời theo operator này. Không đặt concurrency quá cao nếu downstream hoặc connection pool có giới hạn nhỏ.

Nếu cần giữ thứ tự đầu vào, cân nhắc `concatMap` hoặc operator phù hợp. `flatMap` có thể phát kết quả theo thứ tự hoàn tất, không bảo đảm thứ tự ban đầu.

### 9.4. Blocking composition

Với `RestClient`, code imperative thường gọi tuần tự:

~~~java
Order order = orderClient.getOrder(orderId);
Price price = pricingClient.getPrice(order.sku());
StockResponse stock = inventoryClient.getStock(order.sku());

return new OrderView(order, price, stock);
~~~

Cách này dễ đọc và phù hợp khi lời gọi sau phụ thuộc dữ liệu lời gọi trước. Nếu hai lời gọi độc lập và cần thực thi song song, có thể dùng executor hoặc cơ chế concurrency khác, nhưng phải quản lý thread pool, timeout và lỗi rõ ràng.

## 10. Timeout và deadline

### 10.1. Không chỉ có một loại timeout

Một lời gọi HTTP có thể gồm nhiều giai đoạn:

| Timeout | Phạm vi |
| --- | --- |
| DNS resolution | Phân giải hostname |
| Connection timeout | Thiết lập TCP connection |
| TLS handshake timeout | Hoàn tất bắt tay TLS |
| Connection pool acquire timeout | Chờ connection có sẵn |
| Response/read timeout | Chờ dữ liệu phản hồi |
| Overall deadline | Tổng thời gian nghiệp vụ cho phép |

Một request có thể kết nối thành công nhưng downstream xử lý quá lâu. Ngược lại, có thể timeout ngay ở bước lấy connection từ pool dù server vẫn khỏe.

### 10.2. Timeout cho WebClient pipeline

Có thể giới hạn thời gian tổng của một publisher:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .bodyToMono(StockResponse.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

`timeout` của Reactor giới hạn thời gian chờ tín hiệu publisher. Nó không thay thế cấu hình connect/read/response timeout ở HTTP connector. Trong production, nên cấu hình cả transport timeout và deadline ở tầng nghiệp vụ.

### 10.3. Timeout cho HTTP connector

Nếu dùng Reactor Netty, có thể cấu hình một số timeout ở transport:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Ví dụ này minh họa Reactor Netty. Nếu dùng Jetty hoặc connector khác, API cấu hình sẽ khác. Với WebClient load-balanced, cần gắn connector tùy chỉnh vào builder đang được tích hợp LoadBalancer thay vì vô tình tạo một WebClient không có filter.

### 10.4. Timeout cho RestClient

`RestClient` dùng `ClientHttpRequestFactory` để thực hiện request. Timeout cần được cấu hình ở request factory hoặc HTTP library được chọn.

~~~java
RestClient restClient = RestClient.builder()
        .requestFactory(requestFactoryConfiguredWithTimeouts)
        .build();
~~~

`requestFactoryConfiguredWithTimeouts` đại diện cho factory đã được cấu hình connect/read timeout theo HTTP client cụ thể. Không có một con số timeout chung tự động áp dụng đúng cho mọi factory.

### 10.5. Truyền deadline qua chuỗi service

Nếu `orders-service` có deadline 3 giây, nó không nên cho mỗi downstream 3 giây độc lập. Ví dụ:

- Lấy profile mất 1 giây.
- Lấy inventory được cấp 2 giây.
- Gọi pricing tiếp tục chờ 3 giây.

Tổng thời gian có thể vượt deadline của request gốc. Cần quản lý ngân sách thời gian còn lại và đặt timeout từng bước phù hợp.

## 11. Xử lý lỗi HTTP và lỗi transport

### 11.1. Blocking client

Với `RestClient.retrieve()`, response status 4xx/5xx mặc định được chuyển thành exception thuộc họ `RestClientResponseException` nếu không có status handler tùy chỉnh.

~~~java
try {
    return restClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
}
catch (RestClientResponseException ex) {
    // Xử lý HTTP status và response body theo chính sách.
    throw new InventoryCallException(ex.getStatusCode(), ex);
}
catch (ResourceAccessException ex) {
    // Lỗi transport, kết nối hoặc timeout theo request factory.
    throw new InventoryUnavailableException(ex);
}
~~~

Không trả nguyên response body của downstream cho client bên ngoài nếu body có thể chứa thông tin nội bộ hoặc secret.

### 11.2. Reactive client

Với WebClient, `retrieve()` mặc định chuyển 4xx/5xx thành `WebClientResponseException`. Có thể ánh xạ lỗi:

~~~java
Mono<StockResponse> getStock(String sku) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    HttpStatusCode::is4xxClientError,
                    response -> response.createException()
            )
            .onStatus(
                    HttpStatusCode::is5xxServerError,
                    response -> response.createException()
            )
            .bodyToMono(StockResponse.class)
            .onErrorMap(
                    WebClientRequestException.class,
                    InventoryUnavailableException::new
            );
}
~~~

Đoạn mã minh họa cách phân loại lỗi. Trong dự án thật, có thể dùng một exception nghiệp vụ riêng để giữ status, correlation ID và nguyên nhân gốc mà không làm lộ response body.

### 11.3. Phân loại lỗi

| Nhóm lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| HTTP 4xx | 400, 401, 403, 404 | Thường không retry tự động; kiểm tra request, quyền và tài nguyên |
| HTTP 5xx | 500, 502, 503, 504 | Có thể retry có điều kiện nếu thao tác an toàn |
| Connection failure | DNS, refused, TLS | Phân biệt cấu hình sai với lỗi tạm thời |
| Timeout | Connect hoặc response quá hạn | Giới hạn retry và deadline |
| No instance | LoadBalancer không tìm thấy instance | Kiểm tra discovery và readiness |
| Decode error | Response body sai schema | Ghi nhận contract mismatch, không retry mù quáng |
| Cancellation | Caller hủy request | Giải phóng tài nguyên và dừng công việc có thể dừng |

Không gom mọi lỗi thành HTTP 500 chung chung. Phân loại đúng giúp observability, retry và circuit breaker hoạt động có ý nghĩa.

## 12. Retry, idempotency và circuit breaker

### 12.1. Retry không làm request an toàn hơn

Nếu một POST tạo đơn hàng đã tới server nhưng response bị mất, client không biết thao tác đã thành công hay chưa. Retry có thể tạo đơn hàng thứ hai.

Chỉ retry khi:

- Lỗi có khả năng tạm thời.
- Thao tác idempotent hoặc có idempotency key.
- Còn thời gian trong deadline.
- Số lần retry và backoff được giới hạn.
- Downstream còn khả năng tiếp nhận request.

GET thường dễ retry hơn POST có side effect, nhưng vẫn cần xem semantics nghiệp vụ.

### 12.2. Retry reactive

Ví dụ minh họa với Reactor:

~~~java
Mono<StockResponse> getStockWithRetry(String sku) {
    return inventoryClient.getStock(sku)
            .retryWhen(
                    Retry.backoff(2, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(1))
                            .filter(this::isTransientFailure)
            );
}
~~~

`isTransientFailure` là predicate do ứng dụng định nghĩa. Không retry lỗi xác thực, validation hoặc lỗi decode không thể tự hết.

Backoff giúp giảm áp lực khi downstream lỗi. Với nhiều instance, thêm jitter hoặc chính sách phân tán phù hợp để tránh tất cả client retry cùng một thời điểm.

### 12.3. Retry của LoadBalancer và retry của HTTP client

Spring Cloud LoadBalancer có chính sách retry riêng cho client blocking/reactive tùy integration và dependency. Ngoài ra, ứng dụng có thể có retry ở Reactor, Resilience4j hoặc HTTP client.

Nếu mỗi tầng đều retry 3 lần, số request thực tế có thể nhân lên nhiều lần. Cần chọn một nơi chịu trách nhiệm retry chính, xác định số lần thử tổng và quan sát retry attempt.

Theo tài liệu LoadBalancer hiện hành, retry reactive có thể bật qua `spring.cloud.loadbalancer.retry.enabled`; đường blocking với `RestTemplate` có yêu cầu Spring Retry riêng. Hãy kiểm tra cấu hình đúng client và release train đang dùng trước khi bật.

### 12.4. Circuit breaker

Circuit breaker ngăn ứng dụng tiếp tục gọi downstream đang lỗi liên tục. Khi mở circuit, lời gọi có thể bị từ chối nhanh hoặc dùng fallback thay vì tiếp tục tạo tải.

Retry và circuit breaker giải quyết vấn đề khác nhau:

- Retry xử lý một số lỗi tạm thời bằng cách thử lại.
- Circuit breaker ngăn lời gọi liên tục tới dependency đang suy giảm.
- Timeout giới hạn thời gian chờ.
- Bulkhead giới hạn tài nguyên dành cho dependency.

Không dùng retry vô hạn để thay thế circuit breaker hoặc xử lý sự cố ở downstream.

## 13. Cancellation và vòng đời request

### 13.1. Reactive cancellation

Khi subscriber hủy subscription, cancellation signal có thể được truyền ngược qua pipeline tới WebClient và transport. Client có cơ hội dừng việc đọc/ghi và giải phóng tài nguyên.

Tuy nhiên, cancellation không bảo đảm server chưa thực hiện side effect. Request có thể đã tới server và transaction có thể đã commit trước khi client hủy.

### 13.2. Blocking cancellation

Trong mô hình blocking, thread có thể bị interrupt khi request bị hủy hoặc ứng dụng shutdown, nhưng khả năng hủy request phụ thuộc HTTP client và request factory. Không phải mọi thư viện đều dừng I/O ngay khi thread bị interrupt.

Cần cấu hình timeout và shutdown policy rõ ràng. Không giả định interrupt tự động rollback một thao tác ở remote service.

### 13.3. Tránh tách request khỏi lifecycle

Trong WebFlux, hạn chế gọi `subscribe()` bên trong service chỉ để khởi chạy tác vụ rồi bỏ qua publisher. Làm vậy có thể khiến lỗi không được truyền về caller, request kết thúc nhưng công việc vẫn chạy và cancellation không còn được quản lý theo request.

Thay vào đó, trả publisher hoặc compose publisher vào pipeline. Nếu cần tác vụ nền độc lập, hãy đưa vào một cơ chế job/message queue có lifecycle và retry riêng.

## 14. Context propagation, tracing và logging

### 14.1. Correlation ID

Một lời gọi dịch vụ nên mang trace context hoặc correlation ID để có thể nối log của request từ service này sang service khác. Với tracing instrumentation tương thích, client interceptor/filter có thể truyền trace headers tự động.

Không tự tạo một header mới ở mọi tầng nếu hệ thống đã dùng W3C Trace Context hoặc tracing bridge. Cần thống nhất format và tránh ghi token hoặc dữ liệu cá nhân vào header/log.

### 14.2. ThreadLocal và Reactor Context

Trong imperative code, nhiều framework lưu thông tin như security context hoặc tracing context trong `ThreadLocal`. Trong reactive pipeline, thread có thể thay đổi giữa các operator, nên không thể giả định cùng một thread xử lý toàn bộ request.

Reactor cung cấp `Context` gắn với subscription để truyền dữ liệu xuyên pipeline. Các integration Spring hiện đại có thể hỗ trợ context propagation, nhưng cấu hình và behavior phụ thuộc phiên bản.

Không đọc trực tiếp ThreadLocal ở bất kỳ operator nào rồi giả định giá trị luôn đúng. Dùng cơ chế context propagation mà Spring/Reactor cung cấp.

### 14.3. Metrics

Theo dõi tối thiểu:

- Số request theo downstream/service ID.
- Latency và percentile.
- Tỷ lệ HTTP 4xx/5xx.
- Timeout và connection failure.
- LoadBalancer không tìm thấy instance.
- Retry attempt và circuit breaker state.
- Số kết nối đang dùng và pool pending acquire.
- Cancellation và request bị discard.

Tránh gắn ID đơn hàng, user ID hoặc SKU có cardinality cao làm metric tag. Dùng trace/log cho dữ liệu chi tiết và metric tag có cardinality kiểm soát.

## 15. Kiểm thử lời gọi blocking và reactive

### 15.1. Kiểm thử RestClient

Có thể dùng `MockRestServiceServer` để giả lập HTTP response cho `RestClient.Builder`:

~~~java
RestClient.Builder builder = RestClient.builder();

MockRestServiceServer server =
        MockRestServiceServer.bindTo(builder).build();

RestClient client = builder.build();

server.expect(requestTo("http://inventory.test/api/items/SKU-100"))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-100","available":12}
                """,
                MediaType.APPLICATION_JSON
        ));

StockResponse response = client.get()
        .uri("http://inventory.test/api/items/{sku}", "SKU-100")
        .retrieve()
        .body(StockResponse.class);

assertThat(response.available()).isEqualTo(12);
server.verify();
~~~

Ví dụ dùng Java text block và giả định `StockResponse` là record có trường `available`. Cần thêm dependency test phù hợp với phiên bản Spring Framework.

### 15.2. Kiểm thử WebClient bằng StepVerifier

`StepVerifier` subscribe vào publisher và kiểm tra các tín hiệu:

~~~java
StepVerifier.create(inventoryClient.getStock("SKU-100"))
        .assertNext(response ->
                assertThat(response.available()).isEqualTo(12))
        .verifyComplete();
~~~

Để kiểm thử HTTP thực tế, có thể dùng MockWebServer, WireMock hoặc test server tương ứng. `StepVerifier` kiểm tra publisher; nó không tự tạo HTTP server giả.

### 15.3. Các trường hợp cần có

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| HTTP 200 | Body được decode đúng |
| HTTP 4xx | Lỗi được phân loại, không retry sai |
| HTTP 5xx | Chính sách retry/circuit breaker đúng |
| Connect timeout | Request kết thúc trong thời hạn |
| Response timeout | Không giữ tài nguyên vô hạn |
| No service instance | Lỗi LoadBalancer được xử lý |
| Malformed body | Decode error được quan sát |
| Cancellation | Pipeline dừng và giải phóng tài nguyên |
| Multiple instances | Request được gửi tới instance do LoadBalancer chọn |
| Retry | Tổng số attempt không vượt ngân sách |

### 15.4. Kiểm thử LoadBalancer

Có thể cấu hình `SimpleDiscoveryClient` với hai URI test hoặc dùng provider test tương ứng. Xác minh:

- Service ID được phân giải.
- LoadBalancer chọn instance.
- Scheme và port được giữ đúng.
- Khi không có instance, client nhận lỗi rõ ràng.
- Retry không vượt số lần dự kiến.
- Cache instance list được refresh theo chính sách.

Đừng chỉ mock `DiscoveryClient` rồi kết luận tích hợp LoadBalancer đã đúng. Cần ít nhất một integration test kiểm tra filter/interceptor và URI được chuyển đổi.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| WebFlux request bị chậm dù dùng WebClient | Có lời gọi blocking trên event-loop | Tìm `.block()`, JDBC/JPA hoặc SDK blocking |
| Reactive request không chạy | Publisher chưa được subscribe hoặc không được trả về | Trả publisher cho framework hoặc compose vào pipeline |
| HTTP request gửi hai lần | Nhiều subscription vào cold publisher hoặc retry | Kiểm tra nơi subscribe và retry policy |
| `block()` ném lỗi trên non-blocking thread | Đang chặn event-loop | Trả publisher hoặc cách ly blocking API |
| Không phân giải được service ID | Client chưa tích hợp LoadBalancer hoặc thiếu provider | Kiểm tra starter, qualifier và discovery |
| Request luôn gọi một instance | Cache, policy hoặc cấu hình supplier | Kiểm tra LoadBalancer strategy và instance list |
| Thread pool cạn | Blocking downstream quá lâu hoặc concurrency quá cao | Đặt timeout, giới hạn concurrency và kiểm tra pool |
| Retry tạo tải lớn | Retry lồng nhiều tầng hoặc không có backoff | Xác định một retry budget tổng |
| POST bị tạo dữ liệu trùng | Retry thao tác không idempotent | Dùng idempotency key hoặc không retry |
| Cancellation không dừng side effect | Server đã xử lý trước khi nhận cancellation | Thiết kế idempotency và trạng thái nghiệp vụ |
| Response timeout không hoạt động như mong đợi | Chỉ đặt Reactor timeout mà thiếu transport timeout | Cấu hình cả HTTP connector/request factory |
| Tracing bị mất trong reactive flow | Dựa vào ThreadLocal hoặc thiếu context propagation | Dùng Reactor Context và instrumentation tương thích |

## 17. Quy trình chọn mô hình gọi dịch vụ

Có thể dùng các câu hỏi sau khi thiết kế một client mới:

1. Ứng dụng hiện tại dùng Spring MVC hay WebFlux?
2. Thư viện downstream là blocking hay non-blocking?
3. Số lượng lời gọi đồng thời và latency downstream ra sao?
4. Có cần streaming hoặc backpressure không?
5. Có nhiều lời gọi độc lập cần compose song song không?
6. Timeout, retry và cancellation được quản lý ở tầng nào?
7. Spring Cloud LoadBalancer đã được tích hợp với client đúng mô hình chưa?
8. Có thể kiểm thử HTTP và LoadBalancer trong pipeline không?
9. Có metrics/tracing để xác định dependency gây chậm không?
10. Phiên bản Spring Boot/Spring Cloud có hỗ trợ API client dự định dùng không?

Ví dụ quyết định:

| Bối cảnh | Lựa chọn thường phù hợp |
| --- | --- |
| Spring MVC + JDBC/JPA + HTTP call đồng bộ | `RestClient` |
| Spring MVC nhưng cần một lời gọi streaming/bất đồng bộ | Có thể dùng `WebClient` cho riêng client đó |
| Spring WebFlux + reactive data access + nhiều downstream reactive | `WebClient` |
| Ứng dụng cũ dùng `RestTemplate` | Duy trì có kiểm soát hoặc chuyển dần sang `RestClient` theo version |
| Dùng service ID trong môi trường nhiều replica | Tích hợp Spring Cloud LoadBalancer với client tương ứng |
| Thư viện duy nhất là blocking trong WebFlux | Cách ly trên bounded elastic hoặc cân nhắc MVC |

## 18. Bài tập vận dụng

**Bài tập 1 — So sánh hai client.** Gọi cùng endpoint Inventory bằng `RestClient` và `WebClient`. Đo thời gian, quan sát thread và giải thích khác biệt về cách chờ response.

**Bài tập 2 — Load-balanced blocking call.** Cấu hình `@LoadBalanced RestClient.Builder`, dùng URL `http://inventory-service/...` và xác minh request được gửi tới instance do LoadBalancer chọn.

**Bài tập 3 — Load-balanced reactive call.** Cấu hình `@LoadBalanced WebClient.Builder`, trả `Mono<StockResponse>` từ controller WebFlux và kiểm tra publisher bằng StepVerifier.

**Bài tập 4 — Blocking trong event-loop.** Cố ý gọi một thư viện blocking trong WebFlux handler. Quan sát thread bị giữ; sau đó chuyển lời gọi sang `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` và so sánh.

**Bài tập 5 — Ghép lời gọi.** Gọi Pricing và Inventory độc lập bằng `Mono.zip`; sau đó tạo một luồng khác cần gọi Order trước rồi mới gọi Inventory bằng `flatMap`.

**Bài tập 6 — Timeout.** Cấu hình connect timeout và response timeout. Mô phỏng server chậm và xác minh request không vượt deadline nghiệp vụ.

**Bài tập 7 — Retry và idempotency.** Tạo downstream trả 503 trong một số lần đầu. Thử retry GET và POST; chứng minh POST có thể tạo side effect trùng nếu không có idempotency key.

**Bài tập 8 — Cancellation.** Hủy subscription khi WebClient đang chờ response. Quan sát client connection và trạng thái xử lý ở server; giải thích vì sao cancellation không đồng nghĩa rollback.

**Bài tập 9 — Kiểm thử no instance.** Cấu hình discovery không có instance cho một service ID. Xác nhận LoadBalancer báo lỗi và ứng dụng trả response phù hợp.

**Bài tập 10 — Quan sát production.** Bổ sung metrics latency, timeout, retry và LoadBalancer discard. Kiểm tra tag không có cardinality quá cao.

## 19. Ghi nhớ và nguồn tra cứu

- Blocking client giữ thread gọi trong lúc chờ I/O; `RestClient` và `RestTemplate` là các API đồng bộ.
- `WebClient` trả `Mono`/`Flux`, dùng non-blocking I/O và hỗ trợ Reactive Streams backpressure.
- Reactive pipeline cần subscription; trong WebFlux nên trả publisher cho framework thay vì tự `subscribe()` hoặc `block()`.
- Spring Cloud LoadBalancer tích hợp blocking client qua `BlockingLoadBalancerClient` và reactive WebClient qua `ReactorLoadBalancerExchangeFilterFunction`.
- Service ID được phân giải thành instance; discovery, chọn instance và gửi HTTP là ba trách nhiệm riêng.
- Không gọi API blocking trên event-loop; nếu chưa thể thay thế, cách ly bằng scheduler phù hợp và timeout.
- Cấu hình connect/read/response timeout ở transport; Reactor `timeout` giới hạn thời gian publisher nhưng không thay thế mọi transport timeout.
- Retry cần điều kiện lỗi tạm thời, deadline, backoff và idempotency; tránh retry lồng nhiều tầng.
- Cancellation có thể dừng pipeline nhưng không bảo đảm remote side effect đã được rollback.
- Chọn blocking hay reactive theo toàn bộ dependency stack và đặc tính tải, không chỉ theo kiểu trả về của một API.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Framework – REST Clients (`RestClient`, `WebClient`, `RestTemplate`)](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
2. [Spring Cloud Commons – Spring Cloud LoadBalancer integrations](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
3. [Spring Framework – WebFlux và mô hình non-blocking](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
4. [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
5. [Reactor Core – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
6. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
7. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
