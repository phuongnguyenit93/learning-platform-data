# RestClient, RestTemplate và WebClient theo kiểu ứng dụng trong Spring Boot

## 1. Tình huống và mục tiêu

Một ứng dụng Spring Boot thường cần **gọi HTTP tới dịch vụ khác**: lấy giá sản phẩm từ catalog, gọi hệ thống thanh toán, lấy dữ liệu từ đối tác, kết nối API nội bộ hoặc tải một luồng sự kiện. Spring Framework cung cấp ba HTTP client quen thuộc:

- **RestClient**: HTTP client **đồng bộ (blocking/synchronous)**, API **fluent** hiện đại, phù hợp phong cách Java imperative.
- **RestTemplate**: HTTP client **đồng bộ**, API theo phương thức template truyền thống. Hữu ích khi duy trì hệ thống cũ; đối với mã mới nên cân nhắc RestClient.
- **WebClient**: HTTP client **non-blocking, reactive**, API fluent tạo luồng `Mono` hoặc `Flux`. Phù hợp ứng dụng Spring WebFlux, nhiều lời gọi I/O đồng thời và luồng dữ liệu bất đồng bộ.

**Điểm quyết định không phải “API nào mới nhất?” mà là “kiểu ứng dụng và mô hình thực thi nào cần dùng?”.** Một Spring MVC app dùng JDBC/JPA và xử lý theo luồng request imperative thường có lợi từ RestClient. Một WebFlux app vận hành trên event loop nên dùng WebClient, không gọi RestClient/RestTemplate trực tiếp trên event loop. Trong ứng dụng MVC vẫn có thể dùng WebClient, nhưng việc dùng nó không tự biến controller/JPA/blocking business code thành reactive.

Bài học này cung cấp bảng lựa chọn theo kiến trúc, cơ chế thực thi, ví dụ **Java 17+ Spring Boot 3.5.16 Maven** có thể chạy độc lập, xử lý lỗi/timeouts, pooling, JSON, bảo mật, tests và lộ trình chuyển đổi. Các fragment tách riêng được ghi rõ; mã demo hoàn chỉnh không cần kết nối Internet tới một dịch vụ thứ ba vì dùng một upstream giả lập local.

**Phạm vi version:** các API/tên package trong ví dụ lấy theo **Spring Boot 3.5.x / Spring Framework 6.2.x**. Ở các thế hệ Spring Framework mới hơn, trạng thái deprecation và một số package/configuration property có thể thay đổi; khi nâng major version phải đọc đúng tài liệu phiên bản thay vì sao chép nguyên cấu hình của Boot 3.5.

## 2. Phân biệt HTTP server và HTTP client

Trong một request từ browser:

```text
Browser -> Spring Boot /api/orders/7
              |
              | ứng dụng muốn biết sản phẩm #7
              v
          HTTP client
              |
              +--> GET http://catalog-service/products/7
              |          |
              |          v
              |      HTTP server của catalog
              |
              v
          Xử lý kết quả -> trả browser
```

Spring Boot chạy trên Tomcat/Jetty/Undertow/Reactor Netty ở **vai trò server**. RestClient, RestTemplate hoặc WebClient chạy ở **vai trò client** để tạo request tới upstream. Mô hình server và client là hai lựa chọn có liên quan nhưng **không buộc phải trùng**:

- Server **Spring MVC trên Tomcat** có thể gọi RestClient, RestTemplate hoặc WebClient.
- Server **Spring WebFlux trên Reactor Netty** nên dùng WebClient cho HTTP I/O non-blocking.
- Batch/scheduled job không có inbound HTTP server vẫn có thể dùng RestClient hoặc WebClient tùy phong cách thực thi.
- Server Spring MVC không cần chuyển sang WebFlux chỉ vì muốn tận dụng WebClient để gom nhiều lời gọi outbound.

Đừng nhầm **`spring-boot-starter-web`** với “HTTP client starter”. Nó chủ yếu bật Spring MVC và server nhưng cũng mang Spring Web và các HTTP client APIs đồng bộ. `spring-boot-starter-webflux` mang WebFlux APIs, bao gồm `WebClient` và thông thường Reactor Netty client/server.

## 3. Bảng lựa chọn theo kiểu ứng dụng

| Ngữ cảnh | Gợi ý ưu tiên | Vì sao | Điều cần tránh |
| --- | --- | --- | --- |
| Spring MVC, controller/service thông thường, JDBC/JPA | **RestClient** | Đồng bộ, dễ đọc, API fluent, phù hợp thread-per-request | Dùng WebClient chỉ để `.block()` mỗi request mà không có lợi ích |
| Dự án MVC cũ đang ổn định với `RestTemplate` | **Giữ RestTemplate rồi chuyển dần khi cần** | Không phá hàng loạt code đã kiểm thử | Bắt thay toàn bộ cùng lúc mà không có lợi ích đo được |
| Spring WebFlux reactive từ đầu đến cuối | **WebClient** | Non-blocking, kết hợp `Mono/Flux`, cancellation/backpressure | Gọi RestClient/RestTemplate blocking trực tiếp trên event loop |
| MVC gọi hai dịch vụ độc lập song song | RestClient với concurrency có quản trị **hoặc** WebClient và `Mono.zip` | Tránh chờ tuần tự; chọn theo khả năng quản trị và code hiện có | Tạo hàng trăm thread hoặc gọi `block()` ở từng request WebClient nối tiếp |
| Scheduled job thao tác từng bản ghi tuần tự | **RestClient** | Mã imperative đơn giản, điều khiển thời điểm dễ | Dùng reactive chain quá phức tạp không có nhu cầu |
| Pipeline lấy nhiều trang/luồng sự kiện | **WebClient** | `Flux`, streaming, non-blocking | Gom stream vô hạn bằng `collectList().block()` |
| API gateway/aggregator reactive | **WebClient** | Kết hợp nhiều HTTP requests trong reactive pipeline | Chèn JDBC/JPA blocking hoặc `Thread.sleep` trên event loop |
| Cần tương thích layer cũ và nhiều interceptors `RestTemplate` | RestTemplate hiện tại, có thể tạo **RestClient từ RestTemplate** | Hỗ trợ migration từng phần | Đổi underlying HTTP transport mà không kiểm thử |
| Đội không dùng Reactor, nhu cầu đồng bộ đơn giản | **RestClient** | Ít mô hình trừu tượng hơn | Dùng `Mono` chỉ vì trông hiện đại |
| Cần hợp đồng API typed interface | `@HttpExchange` + adapter RestClient/WebClient | Tách interface khỏi client implementation | Giả định interface đồng nghĩa mọi phương thức đều non-blocking |

Đây là định hướng, không phải luật cứng. Nếu ứng dụng MVC tải hàng nghìn tài nguyên mạng đồng thời, WebClient có thể hợp lý. Nếu WebFlux bắt buộc dùng một thư viện blocking không có lựa chọn khác, phải cô lập phần blocking trên scheduler thích hợp, nhưng đó là **biện pháp thích nghi**, không phải bằng chứng rằng RestClient đã non-blocking.

## 4. Cơ chế thực thi thực tế

### 4.1. RestClient và RestTemplate: lời gọi đồng bộ

```text
Servlet request thread
    |
    | controller
    |  -> restClient.get()...retrieve().body(...)
    |  -> chờ HTTP response upstream
    |  -> nhận Product
    |  -> tiếp tục xử lý
    |
HTTP response gửi về browser
```

Khi gọi ở thread hiện tại, chương trình **đợi kết quả** trước khi thực hiện câu lệnh tiếp theo. JVM có thể dùng các cơ chế I/O bên dưới khác nhau, nhưng API phía ứng dụng vẫn là **blocking synchronous**. Với servlet request thread pool, nhiều request đồng thời đang chờ upstream có thể sử dụng nhiều worker threads, vì thế phải cấu hình timeouts, pool size, bulkhead và giới hạn concurrency.

### 4.2. WebClient: khai báo pipeline, thực thi theo subscription

```text
WebFlux request / MVC async handler
    |
    | webClient.get()...retrieve().bodyToMono(Product.class)
    |             |
    |             +-- tạo mô tả thao tác (Mono)
    |                      |
    |                   subscription
    |                      |
    |            non-blocking network I/O
    |                      |
    |              Product / error / cancel
    |                      |
    v                      v
  downstream operators -> HTTP response
```

`WebClient` là một giao diện non-blocking; **`Mono` thường là lazy/cold**. Khi gọi `bodyToMono` chỉ tạo Publisher; I/O thường bắt đầu khi có subscription (framework subscribe khi controller trả Mono). Đừng tự gọi `.subscribe()` bên trong controller rồi lập tức trả response: làm vậy tách xử lý lỗi/hủy request khỏi vòng đời HTTP, khó quản trị concurrency.

**Non-blocking không có nghĩa “không có thread nào”.** Kết nối mạng vẫn chạy trên event loop/threads phù hợp. Lợi ích là không giữ một request thread chờ I/O theo cùng cách đồng bộ và có thể phối hợp nhiều upstream calls với số threads hợp lý. Nên kiểm soát kết nối, rate, backpressure và tài nguyên khác.

### 4.3. Nguy cơ `.block()`

```java
// Trong reactive event-loop: KHÔNG làm.
Product product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .block();
```

Đoạn trên là **snippet cảnh báo** (biến `webClient`, `id` phải tồn tại). Trong WebFlux/Reactor non-blocking thread, `block()` có thể bị Reactor từ chối bằng lỗi và/hoặc phá khả năng mở rộng. Trong một worker thread imperative ngoài event loop, `block()` **có thể hoạt động**, nhưng nếu mục tiêu chỉ là synchronous HTTP thì `RestClient` thường rõ nghĩa và đơn giản hơn.

Spring Framework còn hỗ trợ synchronous usage của WebClient cho ứng dụng imperative, nhưng khi không có nhu cầu kết hợp reactive, hãy ưu tiên API đúng kiểu. Không gọi liên tiếp `block()` trên từng Mono nếu thực sự muốn các request chạy song song.

## 5. RestClient: HTTP client fluent đồng bộ

`RestClient` được đưa vào Spring Framework 6.1. Trong Spring Framework 6.2/Boot 3.5, đây là lựa chọn thường phù hợp cho HTTP calls **mới** ở ứng dụng imperative.

### 5.1. Cấu hình và gọi GET

```java
RestClient client = RestClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

Product product = client.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

Đây là **snippet** cần `RestClient`, `Product`, `MediaType` trong một class/phương thức thích hợp. Khi chạy, `body(Product.class)` là thao tác terminal làm request được gửi và đợi response rồi deserialize thành Java object. Không phải chỉ gọi `retrieve()` là đủ; nó trả `ResponseSpec` để tiếp tục khai báo cách đọc response.

`RestClient.Builder` hỗ trợ `baseUrl`, `defaultHeader`, `requestInterceptor`, `requestFactory`, message converters và nhiều tùy chọn khác. Trong Spring Boot, nên **inject auto-configured builder** thay vì luôn dùng `RestClient.create()`, vì builder đã được Boot chuẩn bị với observability/customizers và HTTP client factory phù hợp.

### 5.2. POST JSON

```java
CreateOrderRequest request = new CreateOrderRequest(7, 3);

OrderDto created = client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(request)
        .retrieve()
        .body(OrderDto.class);
```

Đây là **snippet** giả định các DTO và `client` đã tồn tại. Serialization/deserialization dùng Spring HTTP message converters; trong Boot web starter thường có Jackson. Đừng tự ghép JSON từ chuỗi nếu có DTO rõ kiểu, và đừng đưa dữ liệu người dùng chưa validate vào URL string nối tùy tiện.

### 5.3. Headers, status và entity

```java
ResponseEntity<Product> response = client.get()
        .uri("/products/{id}", 42)
        .header("X-Request-ID", requestId)
        .retrieve()
        .toEntity(Product.class);

HttpStatusCode status = response.getStatusCode();
String upstreamEtag = response.getHeaders().getETag();
Product body = response.getBody();
```

Snippet trên cần imports `ResponseEntity`, `HttpStatusCode`, `Product` và biến `requestId`. Khi cần cả status/header/body, `toEntity` tốt hơn việc chỉ đọc body. Khi muốn kiểm tra response không có body, có `toBodilessEntity()`.

### 5.4. Error handling

Với `retrieve()`, status lỗi 4xx/5xx mặc định dẫn đến exception theo Spring HTTP client, không phải trả một `Product` rỗng im lặng. Có thể sử dụng `onStatus`:

```java
Product product = client.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new IllegalArgumentException(
                            "Không tìm thấy sản phẩm từ upstream");
                })
        .body(Product.class);
```

Đây là snippet custom mapping. Ở ứng dụng thực, nên tạo domain exception (ví dụ `ProductNotFoundException`), giữ đúng thông tin request context và không đẩy toàn bộ body lỗi chứa dữ liệu nhạy cảm ra response/public log.

### 5.5. Chọn underlying HTTP transport

RestClient là **API facade** trên các HTTP request factories. Bạn có thể chọn JDK HttpClient hoặc Apache HttpComponents khi cần pool, proxy, TLS, HTTP/2 support hoặc tuning cụ thể. **Không suy luận pool size/timeouts chỉ từ tên RestClient**; phụ thuộc request factory và client library mà Spring Boot phát hiện.

Một RestClient đã build có thể dùng lại giữa nhiều threads. Không tạo một client mới với connection pool mới **mỗi request**; thường build bean singleton cho mỗi upstream.

## 6. RestTemplate: cách đồng bộ truyền thống và lý do vẫn gặp

`RestTemplate` xuất hiện lâu trước RestClient. Nó cung cấp các phương thức:

```java
Product product = restTemplate.getForObject(
        "https://catalog.example.com/products/{id}",
        Product.class, 42);

ResponseEntity<Product> response = restTemplate.getForEntity(
        "https://catalog.example.com/products/{id}",
        Product.class, 42);
```

Đây là snippet, giả định `restTemplate` đã được cấu hình. Các phương thức khác bao gồm `postForObject`, `postForEntity`, `exchange`, `execute` và thao tác PUT/DELETE.

### 6.1. Vì sao RestTemplate không “sai”?

- Có nhiều hệ thống production đã dùng lâu, có tests, interceptors và error handlers phù hợp.
- Cơ chế Spring `HttpMessageConverter` và `ClientHttpRequestFactory` vẫn hỗ trợ synchronous HTTP requests.
- Khi code cũ ổn định, migration phải cân nhắc regression risk.
- Với Spring Framework 6.2, tài liệu liệt kê RestTemplate là synchronous client, nhưng ưu tiên RestClient cho mã mới; ở Spring Framework các phiên bản mới hơn, trạng thái API có thể thay đổi.

**Sai lầm** là nhầm RestTemplate với **reactive** vì Spring Framework cũng có WebFlux. RestTemplate là synchronous, gọi nó trực tiếp trên Reactor event loop sẽ block.

### 6.2. Inject RestTemplateBuilder thay vì giả định có RestTemplate bean

Spring Boot thường **không cung cấp sẵn một bean `RestTemplate` duy nhất**; Boot cung cấp `RestTemplateBuilder` để bạn tạo `RestTemplate` với client factory, converters và customizations đã cấu hình:

```java
@Bean
RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
    return builder
            .connectTimeout(Duration.ofSeconds(2))
            .readTimeout(Duration.ofSeconds(3))
            .build();
}
```

Đây là snippet `@Bean` trong `@Configuration`, cần imports `RestTemplateBuilder` ở Boot 3.5 là `org.springframework.boot.web.client.RestTemplateBuilder`, cùng `RestTemplate` và `Duration`. Với Boot 3.5, dùng `connectTimeout`/`readTimeout`; các phương thức cũ `setConnectTimeout`/`setReadTimeout` đã được đánh dấu deprecated trong một số bản Boot 3.x mới.

### 6.3. `exchange()` để điều khiển HTTP method/headers

```java
HttpHeaders headers = new HttpHeaders();
headers.setBearerAuth(accessToken);
HttpEntity<Void> entity = new HttpEntity<>(headers);

ResponseEntity<Product> response = restTemplate.exchange(
        "https://catalog.example.com/products/{id}",
        HttpMethod.GET,
        entity,
        Product.class,
        42);
```

Đoạn này minh họa truyền bearer token. **Không** dùng token thật trong code source/hardcode; token phải được lấy an toàn và bảo vệ trong logs/traces.

### 6.4. Lộ trình migration sang RestClient

Trong Spring Framework 6.2 có thể tạo RestClient từ một RestTemplate đang có để **tận dụng phần infrastructure đã cấu hình**:

```java
RestTemplate legacy = /* RestTemplate đã có */ ;
RestClient modern = RestClient.create(legacy);

Product product = modern.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .body(Product.class);
```

Đây là snippet migration, **`legacy` phải có base URI hoặc URI tuyệt đối thích hợp**. Nếu không cấu hình base URL ở RestTemplate cũ, hãy dùng URL tuyệt đối hoặc thiết lập RestClient builder rõ ràng. Không giả định đổi API sẽ giữ nguyên mọi behavior: cần test request factory, interceptors, error mapping, URI encoding, redirect, authentication và timeouts.

Phương pháp chuyển dần: chọn một service gọi outbound, thay method cũ, so sánh HTTP requests/responses, tests; sau đó mới quyết định có đổi hạ tầng/builder hay không. Không bắt buộc rewrite mọi RestTemplate ở một đợt.

## 7. WebClient: non-blocking, reactive và hỗ trợ streaming

`WebClient` thuộc `org.springframework.web.reactive.function.client.WebClient`, được cấu hình tốt nhất qua `WebClient.Builder` do Spring Boot cung cấp khi WebFlux có trên classpath.

### 7.1. GET trả `Mono<T>`

```java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Product.class);
```

Đây là snippet, **chưa khởi động HTTP request ngay khi tạo Mono**. Framework có thể subscribe khi một WebFlux controller trả `Mono<Product>`; trong service có thể dùng `map`, `flatMap`, `timeout`, `onErrorResume` để thiết kế pipeline.

### 7.2. POST bất đồng bộ

```java
Mono<OrderDto> created = webClient.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest(7, 3))
        .retrieve()
        .bodyToMono(OrderDto.class);
```

Snippet này cần DTO và WebClient đã cấu hình. `bodyValue` phù hợp với một body đã có sẵn; với streaming body/Publisher có các overload `body(...)` khác.

### 7.3. Ghép hai request độc lập

```java
Mono<Product> left = webClient.get()
        .uri("/products/{id}", 1)
        .retrieve().bodyToMono(Product.class);

Mono<Product> right = webClient.get()
        .uri("/products/{id}", 2)
        .retrieve().bodyToMono(Product.class);

Mono<List<Product>> both = Mono.zip(left, right)
        .map(pair -> List.of(pair.getT1(), pair.getT2()));
```

Đây là snippet; khi `both` được subscribe, hai requests độc lập có thể được chạy **đồng thời** thay vì chờ từng response tuần tự. Không đảm bảo “nhanh gấp đôi” vì upstream latency, connection pool và network contention. `zip` chờ hai Monos phát giá trị; nếu một Mono error, pipeline error; nếu một Mono hoàn tất rỗng, kết quả zip cũng có thể không phát list. Thiết kế fallback/optional semantics tường minh.

### 7.4. Xử lý status và body theo trường hợp

```java
Mono<Product> found = webClient.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                        new IllegalArgumentException("Product not found")))
        .bodyToMono(Product.class);
```

Snippet trên làm lỗi 404 thành domain exception. Với WebClient, khi cần đọc body khác nhau theo status, dùng `exchangeToMono`:

```java
Mono<Product> found = webClient.get()
        .uri("/products/{id}", 42)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            return response.createException().flatMap(Mono::error);
        });
```

Đoạn này minh họa `exchangeToMono`. Không dùng API `exchange()` cũ mà bỏ quên consume/release body vì có thể dẫn đến connection/memory leaks. `exchangeToMono`/`exchangeToFlux` giúp framework quản lý vòng đời response body khi callback hoàn tất.

### 7.5. Stream nhiều items với `Flux`

```java
Flux<Product> stream = webClient.get()
        .uri("/products/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .retrieve()
        .bodyToFlux(Product.class);
```

Đây là snippet, **không có endpoint `/products/stream` trong demo bên dưới**. Nó mô tả tình huống service hỗ trợ SSE/stream và trả JSON event phù hợp. Khi dùng streaming, tránh `collectList()` vô hạn hoặc `block()` trên event loop; giới hạn concurrency, timeout và memory/buffer một cách thực tế.

### 7.6. WebClient không buộc server phải là WebFlux

Trong ứng dụng Spring MVC, WebClient có thể hoạt động như một outbound HTTP client. MVC có thể xử lý controller trả `Mono<T>` với cơ chế asynchronous request processing nếu có các thư viện reactive cần thiết. Tuy nhiên:

- Servlet server vẫn là Tomcat/Jetty/Undertow tùy config; không tự đổi sang Reactor Netty.
- Spring MVC controller khác WebFlux reactive handler về mô hình xử lý request.
- Nếu business logic gọi JDBC/JPA blocking bên trong `map`/`flatMap` trên event loop, nó vẫn **blocking** và có thể hại hiệu năng.
- Lựa chọn WebClient phải xuất phát từ yêu cầu non-blocking/composition/streaming, không phải nhu cầu “có dependency WebFlux”.

## 8. Spring Boot auto-configuration: nên inject builder nào?

### 8.1. Các builders

| API | Builder do Boot cung cấp | Khi nào có | Cách dùng |
| --- | --- | --- | --- |
| RestClient | `RestClient.Builder` | Spring Web client support trên classpath và Boot auto-configuration phù hợp | Inject builder, `baseUrl(...).build()` |
| RestTemplate | `RestTemplateBuilder` | Spring Web/RestTemplate support trên classpath và Boot auto-configuration | Inject builder, `rootUri(...).build()` |
| WebClient | `WebClient.Builder` | Spring WebFlux/WebClient support trên classpath và Boot auto-configuration | Inject builder, `baseUrl(...).build()` |

Builders có thể **stateful**, còn clients đã build thường được tái sử dụng an toàn. Khi một builder bị thay đổi, các clients build sau đó có thể mang cấu hình mới. Tách cấu hình từng upstream (base URL, auth, timeout, pool) và dùng `clone()` của builder khi muốn tạo nhiều biến thể độc lập.

### 8.2. Hai starters cùng classpath

Ví dụ demo dùng cả:

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Ở Spring Boot 3.5, nếu cả MVC và WebFlux starter cùng có, Boot thông thường chọn **Servlet web application (Spring MVC)**; WebClient vẫn dùng cho outbound calls. Muốn xây server reactive thật, nên tạo project **chỉ với WebFlux starter**, trừ khi có một lý do cấu hình đặc biệt. Không thêm WebFlux starter chỉ để “bật reactive” rồi cho rằng JPA trở thành reactive.

### 8.3. Cấu hình timeout của Spring Boot 3.5

Spring Boot **3.5** có các property liên quan HTTP client:

```properties
# HTTP clients đồng bộ: RestClient và RestTemplate
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s

# Reactive HTTP client connector (WebClient)
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

Các property trên được Boot áp dụng qua HTTP client/request-factory auto-configuration khi phù hợp. Chúng **không phải timeout cho inbound Tomcat request**, cũng không thay `WebClient` pipeline timeout như `.timeout(Duration)` khi cần giới hạn toàn thao tác. **Tên property khác giữa các major versions**: không tự thay bằng `spring.http.clients.*` của tài liệu Boot mới rồi kỳ vọng chạy trên Boot 3.5.

### 8.4. Một bean client cho từng upstream

Trong hệ thống có catalog, payments, identity và search services, nên tạo **các bean/client có tên rõ** hoặc service wrappers rõ ràng:

- Mỗi client có base URL, TLS/auth, timeout/pool policy tương ứng.
- Không nhúng bearer token/user cookie chung vào một singleton client nếu giá trị thay đổi theo request mà không có cơ chế propagation an toàn.
- Dùng cấu hình môi trường cho endpoint upstream, không hardcode host production trong class.
- Với reactive streaming cần riêng connection pool/response buffer policy khi workload khác biệt.
- Bảo toàn instrumentation của Boot (metrics, tracing, interceptors) khi tùy chỉnh builder.

## 9. Ví dụ runnable: cùng một API qua RestClient, RestTemplate và WebClient

Ví dụ dùng **Java 17**, **Maven**, **Spring Boot 3.5.16**. Để demo hoàn toàn tự chứa, chương trình tạo một endpoint “upstream” ngay tại `http://localhost:8080/upstream/products/{id}`, sau đó ba loại HTTP client gọi lại qua **HTTP loopback** như gọi một microservice riêng. Đây là **mô phỏng học tập**, không khuyến nghị cho production vì gọi qua HTTP tới chính server của mình tạo thêm overhead và có thể deadlock khi cạn worker threads.

Các endpoints:

- `GET /upstream/products/7`: đóng vai catalog service, trả `Product` JSON.
- `GET /demo/rest-client/7`: RestClient outbound call rồi trả JSON.
- `GET /demo/rest-template/7`: RestTemplate outbound call rồi trả JSON.
- `GET /demo/web-client/7`: trả `Mono<Product>` từ WebClient cho Spring MVC async handling.
- `GET /demo/web-client-parallel`: WebClient lấy hai products song song bằng `Mono.zip`.

Không cần chạy database, Docker, frontend hay API key để thực hiện ví dụ. Các phần có hostname production bên dưới đều là minh họa, không được dùng làm giá trị truy cập thật.

### 9.1. Cấu trúc thư mục

```text
http-clients-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/httpclients/
    │   │   ├── HttpClientsDemoApplication.java
    │   │   ├── Product.java
    │   │   ├── UpstreamController.java
    │   │   ├── OutboundClientsConfig.java
    │   │   ├── OutboundProductService.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/httpclients/
            └── ClientsSmokeTest.java
```

### 9.2. POM Maven đầy đủ

```xml
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

    <groupId>com.example</groupId>
    <artifactId>http-clients-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
```

**Vì sao có cả hai starters?** `starter-web` chạy **Servlet MVC/Tomcat**, đưa vào RestClient/RestTemplate và JSON converter. `starter-webflux` cung cấp `WebClient`, `Mono` và HTTP client connector. Khi có cả hai, ứng dụng demo vẫn là MVC theo quy tắc auto-configuration Boot 3.5. Ở ứng dụng MVC chỉ dùng RestClient, có thể bỏ dependency WebFlux hoàn toàn; ở ứng dụng WebFlux thuần, có thể bỏ starter-web.

### 9.3. Main class

Tệp `src/main/java/com/example/httpclients/HttpClientsDemoApplication.java`:

```java
package com.example.httpclients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpClientsDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` quét các classes cùng package `com.example.httpclients` và subpackages. Đừng đặt controllers/config ngoài phạm vi scan nếu chưa cấu hình.

### 9.4. DTO `Product.java`

```java
package com.example.httpclients;

public record Product(long id, String name, long price) {
}
```

`record` là Java 17 language feature có sẵn, được Jackson deserialize từ JSON khi starter web có module phù hợp. Giá ở đây là số nguyên demo, **không phải một thiết kế tiền tệ production**; giá tiền thật cần định nghĩa currency, đơn vị nhỏ nhất, rounding và validation.

### 9.5. Upstream giả lập `UpstreamController.java`

```java
package com.example.httpclients;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/upstream/products")
public class UpstreamController {

    @GetMapping("/{id}")
    public Product get(@PathVariable long id) {
        if (id <= 0) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found");
        }
        return new Product(id, "Product-" + id, id * 1000L);
    }
}
```

Khi gọi `GET /upstream/products/7`, body JSON có ý nghĩa:

```json
{"id":7,"name":"Product-7","price":7000}
```

Thứ tự thuộc tính JSON không phải hợp đồng của API, nhưng **các giá trị** phải khớp. Với `id=0`, upstream trả HTTP **404**. Với ID hợp lệ, controller tự tạo DTO, không gọi DB hay service bên ngoài.

### 9.6. Client bean config `OutboundClientsConfig.java`

```java
package com.example.httpclients;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundClientsConfig {

    @Bean
    RestClient productRestClient(
            RestClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .build();
    }

    @Bean
    RestTemplate productRestTemplate(
            RestTemplateBuilder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .rootUri(baseUrl)
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .build();
    }

    @Bean
    WebClient productWebClient(
            WebClient.Builder builder,
            @Value("${demo.upstream.base-url}") String baseUrl) {
        return builder
                .baseUrl(baseUrl)
                .build();
    }
}
```

**Điểm cần hiểu:**

- `RestClient.Builder`, `RestTemplateBuilder` và `WebClient.Builder` đều được Spring Boot hỗ trợ auto-configuration; code **inject builder** và tạo client thành bean, không tạo lại trong controller.
- `baseUrl` áp dụng cho URI tương đối của RestClient/WebClient.
- `RestTemplateBuilder.rootUri(baseUrl)` áp dụng cho các URI String bắt đầu bằng `/`, như dùng trong `getForObject` ở ví dụ kế tiếp.
- `RestTemplateBuilder.connectTimeout`/`readTimeout` chỉ minh họa cấu hình riêng; timeout cho RestClient/WebClient đã có trong `application.properties` theo Boot 3.5.
- `Duration` là kiểu Java chuẩn. `@Value` đọc từ cấu hình môi trường. Khi thay baseURL sang service thật, phải kiểm thử HTTPS, DNS, auth và pool.

### 9.7. Service gọi cả ba kiểu `OutboundProductService.java`

```java
package com.example.httpclients;

import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class OutboundProductService {

    private final RestClient restClient;
    private final RestTemplate restTemplate;
    private final WebClient webClient;

    public OutboundProductService(
            RestClient productRestClient,
            RestTemplate productRestTemplate,
            WebClient productWebClient) {
        this.restClient = productRestClient;
        this.restTemplate = productRestTemplate;
        this.webClient = productWebClient;
    }

    public Product viaRestClient(long id) {
        return restClient.get()
                .uri("/upstream/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Product.class);
    }

    public Product viaRestTemplate(long id) {
        return restTemplate.getForObject(
                "/upstream/products/{id}",
                Product.class,
                id);
    }

    public Mono<Product> viaWebClient(long id) {
        return webClient.get()
                .uri("/upstream/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(Product.class);
    }

    public Mono<List<Product>> viaWebClientParallel() {
        Mono<Product> first = viaWebClient(1);
        Mono<Product> second = viaWebClient(2);

        return Mono.zip(first, second)
                .map(pair -> List.of(pair.getT1(), pair.getT2()));
    }
}
```

Phân biệt **return type**:

- `viaRestClient` và `viaRestTemplate` trả `Product` trực tiếp, vì chúng chờ xong HTTP call.
- `viaWebClient` trả `Mono<Product>`, **không gọi `block()`**.
- `viaWebClientParallel` trả một `Mono<List<Product>>` được tạo từ **hai requests độc lập**. Chúng chỉ được gửi khi có subscription.
- Không có logic retry tự động trong các method này; 404 sẽ trở thành lỗi/exception theo client.

Với nhiều beans cùng kiểu RestClient/WebClient trong dự án thật, nên đặt `@Qualifier` đúng bean thay vì dựa vào parameter name. Trong demo chỉ có một bean mỗi kiểu, nên Spring inject rõ ràng.

### 9.8. Controller `DemoController.java`

```java
package com.example.httpclients;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final OutboundProductService products;

    public DemoController(OutboundProductService products) {
        this.products = products;
    }

    @GetMapping("/demo/rest-client/{id}")
    public Product restClient(@PathVariable long id) {
        return products.viaRestClient(id);
    }

    @GetMapping("/demo/rest-template/{id}")
    public Product restTemplate(@PathVariable long id) {
        return products.viaRestTemplate(id);
    }

    @GetMapping("/demo/web-client/{id}")
    public Mono<Product> webClient(@PathVariable long id) {
        return products.viaWebClient(id);
    }

    @GetMapping("/demo/web-client-parallel")
    public Mono<List<Product>> parallel() {
        return products.viaWebClientParallel();
    }
}
```

Spring MVC hỗ trợ reactive return types như `Mono` bằng cơ chế async integration nếu reactive libraries đã có trong app. **RestClient và RestTemplate vẫn chạy đồng bộ trên Servlet request thread**; chỉ endpoint WebClient trả Mono để MVC subscribe và hoàn tất response bất đồng bộ. Đây là khác biệt dễ quan sát khi kết hợp hai starters.

### 9.9. `application.properties`

```properties
server.port=8080
spring.application.name=http-clients-demo

# Chạy local; thay bằng host service thực tế khi triển khai.
demo.upstream.base-url=http://localhost:8080

# Spring Boot 3.5: timeout cho synchronous HTTP clients.
spring.http.client.connect-timeout=2s
spring.http.client.read-timeout=3s

# Spring Boot 3.5: timeout cho WebClient connector.
spring.http.reactiveclient.connect-timeout=2s
spring.http.reactiveclient.read-timeout=3s
```

Đây là **một file cấu hình độc lập**. Khi triển khai thực tế, đưa base URL ra environment variable hoặc config server; tuyệt đối không để username/password/token trong file mã nguồn. Khi đổi `server.port`, nhớ đổi cả `demo.upstream.base-url` của demo tự gọi local. Nếu server đang chạy qua container, `localhost` bên trong container không tự trỏ tới service khác.

### 9.10. Build, chạy, kiểm tra bằng curl

Điều kiện: đã cài **JDK 17+** và Maven, cổng 8080 còn trống.

```bash
mvn clean package
java -jar target/http-clients-demo-1.0.0.jar
```

Từ terminal thứ hai:

```bash
curl -s http://localhost:8080/upstream/products/7
curl -s http://localhost:8080/demo/rest-client/7
curl -s http://localhost:8080/demo/rest-template/7
curl -s http://localhost:8080/demo/web-client/7
```

Cả bốn calls thành công đều có nội dung tương đương:

```json
{"id":7,"name":"Product-7","price":7000}
```

Thứ tự JSON keys có thể khác tùy serializer; điều được kiểm tra là `id=7`, `name="Product-7"` và `price=7000`.

Kiểm tra WebClient kết hợp song song:

```bash
curl -s http://localhost:8080/demo/web-client-parallel
```

Response JSON về **mặt dữ liệu**:

```json
[
  {"id":1,"name":"Product-1","price":1000},
  {"id":2,"name":"Product-2","price":2000}
]
```

Trong ví dụ source không có artificial delay, nên **không có cam kết** rằng endpoint parallel sẽ nhanh hơn rõ rệt trên máy local. Cái được kiểm thử là cả hai remote Mono được tổ hợp, và thứ tự kết quả giữ theo `zip(first,second)`.

Thử upstream không tồn tại:

```bash
curl -i http://localhost:8080/upstream/products/0
curl -i http://localhost:8080/demo/rest-client/0
curl -i http://localhost:8080/demo/rest-template/0
curl -i http://localhost:8080/demo/web-client/0
```

Upstream trả **404**. Các client gặp 404 và mặc định báo lỗi qua exception/reactive error; **status bên ngoài endpoint `/demo/...` có thể trở thành 500** nếu bạn chưa có `@ControllerAdvice` ánh xạ domain exception. Đây là dụng ý để minh họa rằng **client error của upstream không tự động trở thành status tương tự của API frontend**. Trong ứng dụng thật, phải thiết kế error mapping (mục 11).

Với PowerShell, dùng `curl.exe` thay cho alias `curl` nếu cần. Với cổng khác 8080, đổi cả server port và upstream base URL trong config, sau đó sửa URL gọi kiểm thử.

## 10. Kiểm thử integration không cần dịch vụ ngoài

Để kiểm tra cả ba client trên một HTTP server thật với **random port**, thêm file `src/test/java/com/example/httpclients/ClientsSmokeTest.java`:

```java
package com.example.httpclients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ClientsSmokeTest {

    @LocalServerPort
    int port;

    @Test
    void threeClientsReadSameData() {
        String baseUrl = "http://localhost:" + port;

        Product a = RestClient.create(baseUrl).get()
                .uri("/upstream/products/{id}", 3)
                .retrieve()
                .body(Product.class);

        Product b = new RestTemplate().getForObject(
                baseUrl + "/upstream/products/{id}",
                Product.class,
                3);

        Product c = WebClient.create(baseUrl).get()
                .uri("/upstream/products/{id}", 3)
                .retrieve()
                .bodyToMono(Product.class)
                .block(Duration.ofSeconds(5));

        assertNotNull(a);
        assertEquals(new Product(3, "Product-3", 3000), a);
        assertEquals(a, b);
        assertEquals(a, c);
    }
}
```

Test này **gọi HTTP trên một port thực**, không mock toàn bộ mạng. `@LocalServerPort` cho cổng do Spring Boot test tự chọn, tránh xung đột port 8080. Nó dựng client trực tiếp với base URL random-port để kiểm tra **APIs/client functionality và serialization**; các singleton beans trong demo vẫn được cấu hình theo `application.properties`, nên test **không phải** test riêng mọi custom timeout/bean settings của `OutboundClientsConfig`.

Trong **JUnit test thread bình thường** có thể dùng `.block(Duration)` như ở trên để lấy kết quả và assert; **không** sao chép thao tác blocking này vào Spring WebFlux event loop. Đối với WebFlux service tests thật, nên dùng `StepVerifier` hoặc WebTestClient phù hợp.

Chạy:

```bash
mvn test
```

Khi chạy thành công, Maven báo tất cả tests pass (số tests/summary tùy plugin). Không cần ghi đè `server.port` trên môi trường để test random port.

### Các chiến lược test thường dùng

- **Unit**: mock wrapper/service interface, không cần request HTTP thật.
- **MockRestServiceServer**: hỗ trợ test `RestTemplate` và `RestClient.Builder` với request/response kỳ vọng, không cần socket.
- **WebClient với mock ExchangeFunction/MockWebServer/WireMock**: giả lập phản hồi HTTP lỗi, timeout, headers, malformed JSON, retry mà không gọi dịch vụ bên thứ ba.
- **Integration**: `@SpringBootTest(RANDOM_PORT)`, Testcontainers/WireMock hoặc stub service thực với port ngẫu nhiên.
- **Contract**: kiểm tra request schema, headers, auth và error mapping với upstream thật theo phiên bản API.
- **Performance**: đo connection pool, p95 latency, concurrency, cancellation và retry storms.

Không dùng API public không kiểm soát làm bài test ổn định của CI. Với HTTP client lỗi network, test offline giúp phát hiện regression nhanh và đáng tin hơn.

## 11. Status codes, ngoại lệ và mapping lỗi

### 11.1. Phân biệt “server trả lỗi” và “không kết nối được”

| Trường hợp | HTTP có response? | RestClient / RestTemplate | WebClient |
| --- | --- | --- | --- |
| Upstream 200 + JSON hợp lệ | Có | DTO/value | `Mono<DTO>` phát value |
| Upstream 204 No Content | Có, không body | Có thể `null`/entity không body | `Mono.empty()` cho body |
| Upstream 404 | Có | `RestClientResponseException` và các subclasses tùy API | `WebClientResponseException.NotFound` |
| Upstream 503 | Có | Exception 5xx với status/body | `WebClientResponseException.ServiceUnavailable` |
| DNS/connect refused | Không có HTTP response hợp lệ | `ResourceAccessException` hoặc wrapped I/O exception | `WebClientRequestException` |
| Timeout đọc response | Có thể chưa nhận HTTP response hoàn chỉnh | I/O/timeout exception | Timeout/network error trong pipeline |
| JSON không phù hợp DTO | Có response nhưng decode thất bại | HTTP message conversion error | Codec/decoding error |

Các exception cụ thể phụ thuộc phiên bản và underlying transport. Không gộp mọi thứ thành “upstream 500” và không expose stack trace/raw response bí mật ra browser.

### 11.2. Trả lỗi domain có kiểm soát

Ở application layer nên tách:

- **Upstream trả 404**: resource có thể thật sự không tồn tại, map thành domain `NotFound` hoặc response thích hợp.
- **Upstream trả 401/403**: auth giữa services sai/hết hạn; không đổ lỗi này thành “người dùng cuối không có quyền” nếu không tương đương.
- **Upstream trả 429**: rate limited; cân nhắc `Retry-After`, backoff và giới hạn retry.
- **Upstream 500/502/503/504**: lỗi tạm thời hoặc server-side; có thể cần fallback/circuit breaker.
- **Timeout/connect refused**: downstream unavailable; thường map thành `503`/`504` theo hợp đồng gateway, có log correlation.
- **Invalid JSON**: upstream contract/schema mismatch; cần metric, alert, không giả thành 404.

Trong Spring MVC, có thể dùng `@RestControllerAdvice` + `@ExceptionHandler` để trả một response error chuẩn. Với Spring Boot 3.5, `ProblemDetail` là một cách biểu diễn lỗi theo RFC 9457, nhưng muốn dùng phải chủ động thiết kế mapping; không auto-map mọi WebClient/RestClient exception thành đúng ProblemDetail nghiệp vụ.

### 11.3. Ví dụ mapping riêng ở RestClient

```java
try {
    return restClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .body(Product.class);
}
catch (HttpClientErrorException.NotFound ex) {
    throw new ProductMissingException(id);
}
catch (RestClientResponseException ex) {
    throw new UpstreamUnavailableException(
            ex.getStatusCode().value(), ex);
}
```

Đây là **snippet minh họa**, các exception domain do ứng dụng định nghĩa. RestClient phiên bản/underlying factory có thể dùng các subtype khác; thực tế nên test các loại lỗi từ 404/429/5xx. Đừng catch quá rộng rồi vô tình nuốt lỗi programming hoặc mapping request.

### 11.4. WebClient và `onErrorResume`

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorResume(WebClientResponseException.NotFound.class,
                ex -> Mono.empty());
```

Snippet trên cố ý biến 404 thành **không có sản phẩm** (`Mono.empty()`). Nó chỉ đúng nếu logic business coi 404 là optional; với endpoint cần Product bắt buộc, hãy chuyển sang domain error. Không bật `onErrorResume(ex -> Mono.empty())` cho **mọi lỗi**, vì như vậy che downtime và lỗi kết nối.

### 11.5. Các lỗi có thể được retry?

Retry không mặc định an toàn:

- GET idempotent có thể retry khi kết nối tạm lỗi/503/429 (theo chính sách).
- POST tạo giao dịch có thể tạo **bản ghi trùng** nếu upstream xử lý xong nhưng connection bị đứt trước khi client thấy response.
- Nếu retry thao tác đổi trạng thái, cần idempotency key, transaction semantics rõ và xác nhận với upstream.
- Retry phải có **giới hạn attempts + backoff + jitter**, phù hợp `Retry-After` khi có.
- Không retry vô hạn 401, 403, 400, 404 hoặc lỗi schema.
- Có deadline tổng thể, circuit breaker, bulkhead và metrics. Retry quá nhiều có thể làm upstream đang lỗi càng quá tải.

Ví dụ Reactor có `retryWhen(Retry.backoff(2, Duration.ofMillis(200)))`, nhưng **đừng copy trực tiếp** nếu chưa lọc exception/status và xác minh request idempotent. `Retry` sẽ **resubscribe** pipeline: không chỉ “lặp xử lý kết quả”; nó có thể gửi lại HTTP request.

## 12. Timeout, connection pooling và concurrency

### 12.1. Timeout là tập các giới hạn khác nhau

| Loại | Mục đích | Gợi ý |
| --- | --- | --- |
| Connection timeout | Không chờ kết nối TCP/TLS mãi | Thường ngắn, tính theo network |
| Response/read timeout | Không đợi response/read vô hạn | Tùy SLA upstream |
| Total operation deadline | Giới hạn toàn lời gọi gồm retry/backoff | Không chỉ là socket read timeout |
| Pool acquire timeout | Không đợi lấy kết nối rảnh vô hạn | Quan trọng khi connection pool bão hòa |
| Idle/keep-alive timeout | Giải phóng kết nối nhàn rỗi hợp lý | Phù hợp proxy/upstream idle timeouts |
| Request-level timeout (Reactor) | Kết thúc pipeline sau một khoảng | Ví dụ `.timeout(Duration)` |
| Circuit breaker timeout | Ngăn downstream treo dây chuyền | Cần phối hợp với các timeout còn lại |

**Ví dụ budget:** upstream mục tiêu 300 ms, API gateway có deadline 2 s. Nếu client đặt read timeout 30 s và retry 5 lần, gateway có thể trả timeout trước khi business code nhận ra. Timeouts/retry budget phải nhất quán xuyên suốt chuỗi dịch vụ.

### 12.2. WebClient `timeout` và cancellation

```java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", 42)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));
```

Đây là snippet. `timeout` của Reactor báo error nếu publisher không phát đúng thời hạn; timeout có thể dẫn đến cancellation của subscription và HTTP request khi connector hỗ trợ. **Không cam kết** mọi xử lý upstream đã bị hủy: server bên kia có thể vẫn tiếp tục thực hiện thao tác.

### 12.3. Connection pool có giới hạn

Dù dùng RestClient hay WebClient, **pool của HTTP transport** khác với pool thread. Khi có 500 requests đồng thời, không phải lúc nào bạn có 500 TCP connections: client có thể tái sử dụng connection, queue requests, hoặc dùng HTTP/2 multiplexing. Quan sát:

- active/idle/pending connections;
- pool max connections, pool acquire timeout;
- HTTP/1.1 keep-alive vs HTTP/2 multiplexing;
- DNS/TLS handshake, idle evictions;
- timeouts ở reverse proxy và load balancer;
- memory buffering, max response size và streaming pressure.

Không nên tự tạo một `HttpClient`/`WebClient`/`RestClient` mới kèm pool riêng cho mỗi incoming request. Điều đó có thể tăng số sockets, TLS handshakes, GC và làm khó observability. Xây client bean dùng lại, cấu hình pooling có kiểm soát.

### 12.4. Chặn request queue và concurrency vượt khả năng upstream

WebClient non-blocking vẫn có thể làm upstream quá tải nếu `flatMap` tạo quá nhiều requests. Có thể giới hạn concurrency:

```java
Flux<Product> products = Flux.range(1, 100)
        .flatMap(this::fetchProduct, 8);
```

Đây là snippet ở trong class có method `Mono<Product> fetchProduct(int id)`; `8` là concurrency tối đa đang được `flatMap` điều phối, không phải guarantee tối đa sockets của toàn hệ thống. Kết quả có thể không giữ thứ tự input; dùng `flatMapSequential` nếu cần thứ tự với chi phí phù hợp.

Trong MVC dùng RestClient, có thể dùng giới hạn executor/bulkhead/virtual threads phù hợp Java runtime, nhưng chỉ tăng threads không tạo thêm năng lực DB hay upstream.

### 12.5. Reactive code chứa blocking I/O

Khi không thể tránh một thư viện blocking trong WebFlux:

```java
Mono<Product> adapted = Mono.fromCallable(
                () -> legacyRestClient.getProduct(42))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **snippet chuyển đổi bất đắc dĩ**, không phải cách được khuyên dùng thay WebClient. `legacyRestClient` là abstraction đồng bộ đã tồn tại; phải import Reactor `Schedulers`. BoundedElastic dành cho tác vụ blocking có giới hạn và queue; không “biến I/O thành non-blocking” hoặc bảo đảm scale vô hạn. Đầu tiên hãy ưu tiên client reactive thực sự khi ứng dụng cần reactive end-to-end.

## 13. JSON, generics, encoding và response body lớn

### 13.1. Đọc danh sách typed

Với `List<Product>`, không dùng `List.class` rồi kỳ vọng generic type được bảo toàn. Sử dụng `ParameterizedTypeReference`:

```java
List<Product> products = restClient.get()
        .uri("/products")
        .retrieve()
        .body(new ParameterizedTypeReference<List<Product>>() {});
```

```java
Mono<List<Product>> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToMono(
                new ParameterizedTypeReference<List<Product>>() {});
```

Hai ví dụ trên **chỉ là snippets**; upstream `/products` chưa tồn tại trong demo mục 9. Với RestTemplate, `exchange` có overload nhận `ParameterizedTypeReference<List<Product>>`.

### 13.2. Đặt Content-Type và Accept đúng

`Content-Type` mô tả **format body request gửi đi**; `Accept` mô tả **response type mong đợi**. Ví dụ POST JSON:

```java
client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(order)
        .retrieve()
        .toBodilessEntity();
```

Đoạn này yêu cầu server chấp nhận request body JSON và không cần đọc response body. Đừng dùng `toBodilessEntity()` nếu business code cần ID/order status từ body.

### 13.3. Response lớn và streaming

- RestClient/RestTemplate có thể xử lý streaming theo APIs thích hợp, nhưng cần quản lý body stream và đóng resources đúng cách.
- WebClient `bodyToFlux` hợp với streaming, nhưng codec mặc định có giới hạn in-memory buffering cho một số kiểu decode.
- Nếu endpoint trả payload 100 MB, tránh `bodyToMono(byte[].class)` nếu memory budget không đủ.
- Khi xử lý download, dùng stream/body extraction APIs phù hợp và bảo đảm đóng tài nguyên.
- Với WebClient, không dùng `collectList()` trên Flux vô hạn hoặc unbounded source.

Khi gặp `DataBufferLimitException`, đừng tăng `maxInMemorySize` lên hàng GB theo bản năng. Kiểm tra response schema và chuyển sang streaming/giới hạn size. Với dữ liệu nhạy cảm, bảo vệ logs và không ghi toàn bộ request/response body ở debug.

## 14. TLS, proxy, credentials và bảo mật khi gọi HTTP outbound

### 14.1. SSL/TLS

HTTP client gọi `https://...` phải xác minh **certificate chain, hostname và TLS policy**. Khi upstream dùng CA nội bộ/mTLS, dùng truststore/keystore được quản lý; Spring Boot hỗ trợ SSL bundles và các customization của HTTP client. Không dùng “trust all certificates”, tắt hostname verification hoặc `curl -k` trong production.

`RestClientSsl` của Spring Boot 3.5 có thể giúp áp SSL bundle vào RestClient.Builder trong cấu hình cụ thể. WebClient với Reactor Netty sử dụng connector/TLS setup tương ứng; không sao chép nguyên cấu hình Servlet SSL server vào outbound client rồi kỳ vọng client tự tin CA mới.

### 14.2. Auth cho service-to-service

Có thể dùng `Authorization: Bearer <token>`, mTLS hoặc client credentials OAuth2 tùy kiến trúc. Token cần:

- Lấy/refresh đúng thời hạn, không hardcode vào POM/properties.
- Không ghi token trong URL/query, exception message hay HTTP client debug logs.
- Phân biệt token **user** và token **service account**; không tùy tiện forward token của incoming request sang mọi upstream.
- Cấu hình propagation của trace/request ID và security identity theo policy.
- Khi gặp 401/403, không retry vô hạn và không chuyển lỗi upstream thành quyền người dùng cuối sai.

### 14.3. SSRF: không cho user quyết định URL tùy ý

**Server-Side Request Forgery** xảy ra khi backend bị điều khiển tạo HTTP request đến địa chỉ không được phép, ví dụ cloud metadata service, loopback, mạng quản trị hoặc file nội bộ. Cần:

- Ưu tiên base URL **được cấu hình cố định** cho mỗi service.
- Validate scheme/hostname/path được phép, không nhận absolute URL tùy ý từ client.
- Giới hạn redirects và kiểm tra DNS/IP ranges khi threat model yêu cầu.
- Không cho request tự chuyển từ public host sang private/internal IP qua redirect/DNS rebinding.
- Áp egress firewall/network policy và HTTP client IP filtering phù hợp.
- Không cho user nhập `http://169.254.169.254/...` hoặc `http://127.0.0.1:...` làm “API URL” rồi fetch bằng quyền server.

Trong demo local, gọi `localhost:8080` có chủ đích để tự chứa; trong production, user input **không được** override `demo.upstream.base-url`.

### 14.4. CORS không áp dụng cho Java server-to-server client

Spring CORS policy chủ yếu kiểm soát JavaScript chạy trong browser. Một Spring RestClient/WebClient gọi dịch vụ khác từ backend **không bị browser CORS policy chặn**. Nếu outbound HTTP call từ backend thất bại, hãy kiểm tra DNS/TLS/proxy/firewall, auth, path và status, không “sửa CORS” ở upstream trừ khi đó là yêu cầu trình duyệt riêng.

### 14.5. Proxy môi trường và DNS

- Corporate HTTP proxy có thể yêu cầu authentication, allowlist và cấu hình per-client.
- Ứng dụng chạy container/Kubernetes phải gọi đúng service DNS/port; `localhost` bên trong pod thường chỉ chính pod/container, không trỏ sang service khác.
- Reverse proxy/load balancer giữa services có connect/read/idle timeouts riêng.
- DNS caching và TLS connection reuse ảnh hưởng latency khi load lớn.
- Khi có mTLS mesh, xác định nơi TLS được terminate, certificate identities và retry policy ở mesh để tránh “retry chồng retry”.

## 15. Observability, tracing và debug ngoài production

### 15.1. Metrics và tracing

Dùng builders auto-configured của Boot để giữ các customizers/observability integrations nếu đã bật Micrometer/Actuator/Tracing. Nên theo dõi:

- outbound request count theo client/service, method, status class;
- p50/p95/p99 latency, timeout và error rate;
- connection pool active/pending/idle và pending acquire latency;
- DNS/TLS handshake errors, 429/503 rates, retry counts và circuit breaker state;
- correlation/trace IDs qua các hops.

Tránh dùng raw URL chứa customer ID/token làm metric tags (cardinality explosion, lộ dữ liệu). Dùng URL template/route name và giới hạn tags.

### 15.2. Debug một request bị lỗi

1. Xác định **client loại nào** và underlying request factory/connector.
2. Ghi method, host, path template, status, latency và correlation ID; che credentials.
3. Dùng `curl -i` tới upstream **từ cùng network environment** để xác nhận DNS/TLS/route.
4. Tách HTTP error response (4xx/5xx) khỏi connection/timeout error.
5. Kiểm tra timeouts ở client, gateway và upstream; kiểm tra retries có nhân request không.
6. Với WebClient, kiểm tra có subscription thực hay chưa; không nhầm một `Mono` được tạo với request đã gửi.
7. Quan sát kết nối/pool, event loop và blocking operations.
8. Với JSON decode error, lưu schema/status/body sample **đã lọc dữ liệu nhạy cảm**.

### 15.3. Không log full body vô điều kiện

Ghi toàn bộ payload của payment/auth/user profiles có thể vi phạm chính sách bảo mật. Khi cần debug, log những trường được duyệt, dùng sampling, masking, correlation ID và retention policy. Error response từ đối tác có thể chứa PII, secrets hoặc nội dung không đáng tin.

## 16. Lộ trình từ RestTemplate sang RestClient, hoặc từ MVC sang reactive

### 16.1. Migration RestTemplate → RestClient

Một lộ trình kiểm soát rủi ro:

1. Kiểm kê mọi nơi dùng `RestTemplate` và `RestTemplateBuilder`; phân loại các custom interceptors, converters, error handlers, request factories.
2. Chọn một call đơn giản GET, xác định request method/URL/headers, timeout, auth và response semantics.
3. Có integration test/mock server so sánh response; không chỉ kiểm tra “mã biên dịch”.
4. Dùng `RestClient.create(existingTemplate)` khi hợp lý hoặc inject `RestClient.Builder` để tận dụng Boot configuration.
5. Chuyển dần sang `get().uri().retrieve().body()`, ánh xạ lỗi cẩn thận.
6. Quan sát hiệu năng, redirects, pool, content negotiation và retry behavior.
7. Không thay transport/mTLS/proxy cùng lúc với refactor API nếu không bắt buộc.
8. Khi toàn bộ calls đã chuyển, bỏ beans/dependency/config cũ không còn dùng.

### 16.2. Spring MVC → WebFlux không chỉ là đổi client

Chuyển một REST controller trả `Product` sang `Mono<Product>` **không đủ** để trở thành kiến trúc reactive:

- Server/routing/web stack cần đúng WebFlux runtime.
- Repository và downstream operations cũng nên non-blocking; R2DBC/reactive drivers khi phù hợp.
- Blocking libraries cần được thay hoặc cô lập trên scheduler có giới hạn.
- Error handling, transactions, context propagation, security và testing phải cập nhật.
- Team cần hiểu reactive stream semantics: laziness, subscription, backpressure, cancellation.

Nếu phần lớn hệ thống là JPA/JDBC và yêu cầu concurrency vừa phải, Spring MVC + RestClient vẫn có thể là lựa chọn đúng. Không dùng “reactive” làm mục tiêu độc lập với yêu cầu hiệu năng và đội ngũ.

### 16.3. Giải pháp HTTP Service Clients (`@HttpExchange`)

Khi nhiều calls tới cùng downstream cần typed interfaces, Spring Framework hỗ trợ declarative HTTP interfaces có thể backed bởi **RestClient** (blocking) hoặc **WebClient** (reactive). Ví dụ interface:

```java
@HttpExchange("/products")
interface CatalogApi {
    @GetExchange("/{id}")
    Product get(@PathVariable long id);
}
```

Đây là **snippet minh họa**, chưa là chương trình độc lập; cần imports annotation Spring Web, cấu hình `HttpServiceProxyFactory` và `RestClientAdapter`. Với WebClient adapter, method return type reactive phù hợp (ví dụ `Mono<Product>`). HTTP interface giúp tách contract khỏi nơi tạo HTTP call, nhưng **không tự thay đổi blocking semantics** của adapter phía dưới.

## 17. Những lỗi thực hành rất thường gặp

| Triệu chứng | Khả năng cao | Cách sửa |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: RestTemplate` | Boot auto-configure builder, không tạo một RestTemplate bean sẵn | Tạo `@Bean RestTemplate` qua `RestTemplateBuilder` |
| `NoSuchBeanDefinitionException: WebClient.Builder` | Chưa có `spring-webflux`/starter phù hợp hoặc auto-config không hoạt động | Kiểm tra dependency và application context |
| Inject `RestClient.Builder` không có | Spring Web/Boot version quá cũ hoặc auto-config bị thay | Xác nhận Boot 3.5 và starter/classpath |
| `WebClient` trả Mono nhưng HTTP request không chạy | Chưa subscribe/return reactive publisher | Return Mono từ controller hoặc compose theo subscription |
| `block() is not supported` | Gọi blocking operation trên Reactor non-blocking thread | Trả Mono/Flux, bỏ `block()` |
| WebFlux throughput thấp dù dùng WebClient | Có JDBC/RestTemplate/blocking trong pipeline | Dùng non-blocking driver hoặc boundedElastic giới hạn |
| RestClient POST không gửi request | Chỉ gọi `retrieve()`, chưa có terminal `body/toEntity` | Gọi terminal operation thích hợp |
| 404 upstream thành 500 frontend | Không map exception của HTTP client thành domain error | Dùng `onStatus`/`@ControllerAdvice` |
| Requests treo quá lâu | Timeout thiếu hoặc cấu hình trên client sai | Set connection/read/total deadlines, đo connector |
| Duplicate POST sau retry | Retry non-idempotent | Idempotency key và chính sách retry có điều kiện |
| Connection pool exhausted | Concurrency không giới hạn, leak body/response, client tạo liên tục | Reuse singleton client, consume/release body, bulkhead |
| 200 nhưng DTO null/empty | HTTP 204/body rỗng, schema mismatch | Xác nhận status/content-type, thiết kế Optional/Mono.empty |
| `DataBufferLimitException` | Response lớn, codec buffer vượt giới hạn | Streaming, giới hạn payload, điều chỉnh codec hợp lý |
| Mixed Spring starters khiến server là MVC | Boot thường ưu tiên MVC khi có cả MVC+WebFlux | Xác định web application type đúng |
| Test random-port nhưng outbound bean gọi 8080 | App demo base URL hardcode 8080 | Inject base URL động trong test hoặc test clients trực tiếp |
| 401 khi gọi service | Token thiếu/expired hoặc audience sai | Kiểm tra service-to-service auth, không mở CORS |
| SSLHandshakeException | Trust/cert/hostname/TLS mismatch | Dùng trusted CA/SSL bundle, không trust-all |
| Timeout chỉ khi qua Kubernetes | DNS/service port/network policy/mesh retries | Test cùng network, kiểm tra mesh/gateway |
| Dùng RestClient mỗi request | Mất pooling/customizations, overhead | Build một bean per upstream |
| Metrics có hàng triệu URL tags | Raw URLs gồm IDs trong tags | Dùng route templates, giảm cardinality |

## 18. Câu hỏi tự kiểm tra

1. **Khi nào chọn RestClient?** Với ứng dụng imperative như MVC/JPA/batch cần HTTP calls đồng bộ và muốn API fluent rõ ràng.
2. **RestTemplate có trở thành non-blocking nếu server dùng WebFlux không?** Không. API RestTemplate vẫn synchronous.
3. **WebClient có thể chạy trong MVC không?** Có. Thêm WebFlux client APIs, không nhất thiết chuyển server sang WebFlux.
4. **`bodyToMono(Product.class)` có lập tức gọi HTTP không?** Thông thường không; Mono lazy và cần subscription.
5. **`retrieve().body(Product.class)` của RestClient có blocking không?** Có, đây là operation đồng bộ chờ response.
6. **Spring Boot tự tạo bean RestTemplate để inject không?** Thông thường không; Boot auto-configure `RestTemplateBuilder` để bạn tạo bean.
7. **Tại sao không gọi WebClient `.block()` trong WebFlux controller?** Chặn event loop, có thể ném lỗi và làm giảm concurrency.
8. **Vì sao một WebClient request có thể 404 nhưng MVC endpoint trả 500?** Outbound exception không tự map thành response domain; cần error handler rõ.
9. **Dùng `flatMap(...,8)` có nghĩa max 8 sockets không?** Không. Đó là giới hạn publisher concurrency ở operator; pool/network là tầng khác.
10. **Có nên retry POST payment khi timeout không?** Chỉ khi thiết kế idempotency và semantics rõ; nếu không có thể tạo giao dịch trùng.
11. **Vì sao RestClient bean singleton thường tốt hơn tạo trong controller?** Giữ cấu hình, pooling, TLS, tracing và giảm overhead.
12. **Vì sao WebClient không thay thế mọi blocking library trong app?** Nó chỉ non-blocking phần outbound HTTP; DB/CPU/SDK khác vẫn có thể blocking.
13. **RestClient khác RestTemplate quan trọng nhất ở đâu?** Cùng synchronous, khác style API và đường mở rộng; RestClient fluent hiện đại.
14. **Phân biệt connect timeout và total pipeline timeout?** Connect timeout giới hạn kết nối; total deadline có thể bao gồm connect, response, retry/backoff.
15. **`localhost` bên trong container có trỏ sang service khác không?** Không, thường trỏ vào network namespace của chính container/pod.
16. **Java backend gọi cross-origin API có bị browser CORS chặn không?** Không; CORS browser policy không áp dụng cho server-to-server HTTP client.
17. **Thêm cả starter-web và starter-webflux có buộc server dùng Netty không?** Không; Boot 3.5 thường chọn MVC/Servlet khi có cả hai.
18. **Đổi RestTemplate sang RestClient có tự sửa timeout và redirect không?** Không. Phải xác nhận hạ tầng underlying HTTP client.
19. **HTTP error status và connection error giống nhau không?** Không. Một bên đã có HTTP response, bên kia có thể chưa connect/không nhận được response.
20. **Mono.zip hai requests có được lợi ích gì?** Cho phép ghép các publishers độc lập để chờ kết quả, thường thực thi đồng thời khi subscribe.

## 19. Checklist đưa HTTP client vào production

- [ ] Xác định service dùng **imperative MVC/JPA** hay **reactive WebFlux**.
- [ ] Ưu tiên RestClient cho mã đồng bộ mới; giữ RestTemplate có kiểm soát ở legacy; dùng WebClient cho non-blocking/reactive/streaming.
- [ ] Tạo client beans dùng lại theo upstream, inject Boot auto-configured builder.
- [ ] Base URL, port, proxy và credentials lấy từ cấu hình/secret, không hardcode production.
- [ ] Cấu hình **connect/read/total timeouts**, đồng bộ với gateway/upstream SLA.
- [ ] Kiểm soát connection pool, max concurrency, backpressure và bulkhead.
- [ ] Phân biệt HTTP 4xx/5xx với network/timeout/decode errors; map thành domain errors rõ.
- [ ] Retry có giới hạn/backoff/jitter; chỉ retry idempotent requests hoặc có idempotency key phù hợp.
- [ ] Trả `Mono/Flux` trong WebFlux; không `block()` hoặc `subscribe()` tùy tiện trong controller.
- [ ] Với MVC + WebClient, đo lợi ích thật; không tự nhận cả app đã reactive.
- [ ] Xác thực TLS/CA/hostname; dùng secret manager/SSL bundle cho mTLS nếu cần.
- [ ] Giới hạn SSRF, redirects và egress; không cho user input quyết định absolute URL tùy ý.
- [ ] Có tests cho success, 404, 429, 503, timeout, connection refused và invalid JSON.
- [ ] Có metrics/traces, request IDs và log redaction; không ghi access tokens hay PII vào logs.
- [ ] Đo p95/p99 latency, connection pool utilization và retry rates trong tải thực.
- [ ] Nếu nâng Boot/Spring Framework major, kiểm tra trạng thái RestTemplate và tên HTTP client properties theo version.

## 20. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Calling REST Services](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html): RestClient, RestTemplate, WebClient, builders, client detection, timeouts và SSL bundles.
- [Spring Framework 6.2 — REST Clients](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient/RestTemplate, response handling và HTTP Interfaces.
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): reactive HTTP client, lifecycle và configuration.
- [Spring Framework — WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): error handling và body extraction.
- [Spring Framework — WebClient exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): `exchangeToMono` và `exchangeToFlux`.
- [Spring Framework — WebClient synchronous use](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html): vì sao `block()` có thể dùng trong synchronous contexts nhưng không phù hợp event loop.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, random port và integration tests.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, laziness, threading và error handling.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): service-to-service OAuth2 và token lifecycle.

**Kết luận:** chọn HTTP client theo **mô hình thực thi của ứng dụng**, không chỉ theo tên thư viện. **RestClient** là lựa chọn rõ ràng cho code đồng bộ mới; **RestTemplate** giúp duy trì hệ thống đồng bộ cũ và chuyển dần; **WebClient** dành cho reactive/non-blocking, streaming và tổ hợp nhiều HTTP calls. Dù chọn client nào, độ tin cậy production vẫn phụ thuộc **timeouts, pooling, giới hạn concurrency, error mapping, retry idempotency, TLS và observability**.