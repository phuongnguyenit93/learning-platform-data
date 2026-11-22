# WebClient và vai trò ClientHttpConnector trong Spring WebFlux

## 1. WebClient giải quyết việc gì?

Spring WebFlux cung cấp **WebClient** để gọi HTTP service theo mô hình reactive. API của nó có dạng fluent, dựa trên Reactor, hỗ trợ request/response bất đồng bộ, streaming và composition bằng Mono/Flux.

Ví dụ một service lấy thông tin sản phẩm từ catalog:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

Đoạn code mô tả request và cách giải mã response. Nó không tự nói HTTP request được gửi bằng thư viện mạng nào. Phần thực hiện I/O nằm dưới một abstraction khác: **ClientHttpConnector**.

WebClient tách hai mối quan tâm:

- **Lớp API và xử lý HTTP của Spring:** xây URI, method, headers, body, filters, xử lý status, encode/decode dữ liệu và trả Mono/Flux.
- **Lớp transport:** mở kết nối, DNS, TCP, TLS, connection pool, proxy, gửi/nhận bytes, timeout và chuyển response từ HTTP client nền thành abstraction của Spring.

Nhờ sự phân tách này, cùng một đoạn code WebClient có thể dùng với Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient hoặc Apache HttpComponents mà không phải viết lại nghiệp vụ gọi API.

## 2. ClientHttpConnector là gì?

ClientHttpConnector là interface trong package org.springframework.http.client.reactive. Nó là abstraction để một HTTP client nền kết nối tới origin server và cung cấp cơ chế gửi ClientHttpRequest, nhận ClientHttpResponse.

Contract cốt lõi:

~~~java
Mono<ClientHttpResponse> connect(
        HttpMethod method,
        URI uri,
        Function<? super ClientHttpRequest, Mono<Void>> requestCallback
);
~~~

Ba tham số quan trọng:

- **HttpMethod:** GET, POST, PUT, PATCH, DELETE...
- **URI:** địa chỉ đích đã được WebClient xây dựng.
- **requestCallback:** callback chuẩn bị và ghi request thông qua ClientHttpRequest; callback trả Mono<Void> báo quá trình ghi request đã hoàn tất.

Giá trị trả về là Mono<ClientHttpResponse>. Connector chịu trách nhiệm nối API request/response chuẩn của Spring với API cụ thể của thư viện HTTP bên dưới.

### 2.1. Connector thực hiện những việc nào?

Một connector thực tế thường phải phối hợp:

1. Tạo hoặc lấy connection phù hợp từ transport.
2. Phân giải hostname và thiết lập kết nối mạng khi cần.
3. Thực hiện TLS handshake cho HTTPS.
4. Áp dụng connection pool, proxy và cấu hình protocol của HTTP client.
5. Ghi method, URI, headers và body do Spring cung cấp.
6. Nhận status, headers và response body.
7. Chuyển dữ liệu về ClientHttpResponse và DataBuffer để WebClient xử lý tiếp.
8. Truyền lỗi kết nối, lỗi TLS, timeout và cancellation qua reactive publisher.

Connector **không** quyết định nghiệp vụ rằng status 404 có nghĩa là sản phẩm không tồn tại, cũng không tự chọn DTO Product để giải mã JSON. Những việc đó thuộc WebClient, codec và code ứng dụng.

### 2.2. Connector không phải codec

Phân biệt:

| Thành phần | Trách nhiệm |
| --- | --- |
| WebClient | API fluent để xây request và compose response |
| ExchangeFunction | Thực hiện một HTTP exchange qua filter chain |
| ExchangeFilterFunction | Logic trước/sau exchange như auth header, correlation ID, logging |
| ClientHttpConnector | Adapter giữa Spring HTTP abstraction và HTTP client nền |
| ClientHttpRequest / ClientHttpResponse | Request/response abstraction của Spring |
| HttpMessageWriter / HttpMessageReader | Encode/decode body theo media type |
| DataBuffer | Đơn vị buffer dữ liệu request/response trong Spring |

Ví dụ WebClient gửi JSON: codec serialize Java object thành DataBuffer trước khi connector ghi dữ liệu ra transport. Khi response về, connector cung cấp response body dạng DataBuffer; codec đọc JSON và chuyển thành Product.

Thay connector không đồng nghĩa phải thay JSON codec. Cũng không nên đưa logic parse DTO vào connector tùy chỉnh.

## 3. Luồng xử lý từ WebClient tới mạng và quay lại

~~~text
Application service
       |
       v
WebClient request spec
(method, URI, headers, body)
       |
       v
ExchangeFilterFunction chain
(authentication, tracing, metrics)
       |
       v
ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
Underlying HTTP client
(Reactor Netty / JDK / Jetty / Apache)
       |
       v
DNS, TCP, TLS, pool, HTTP I/O
       |
       v
ClientHttpResponse + DataBuffer stream
       |
       v
HTTP message readers / codecs
(JSON, String, byte[], SSE...)
       |
       v
Mono<T> / Flux<T>
       |
       v
Application
~~~

Có thể hiểu ngắn gọn:

- WebClient biết **muốn gửi request gì**.
- ClientHttpConnector biết **dùng HTTP transport nào để gửi**.
- Codec biết **chuyển body giữa Java object và HTTP bytes**.
- Reactor biểu diễn quá trình bằng Publisher để caller compose và cancel.

Một request có thể chưa chạy tại thời điểm xây Mono. Với cold publisher thông thường, I/O bắt đầu khi có subscription.

## 4. Các ClientHttpConnector phổ biến

Spring Framework hỗ trợ nhiều implementation. Spring Boot có thể tự chọn connector theo dependency có trên classpath.

| Connector | HTTP client nền | Khi phù hợp |
| --- | --- | --- |
| ReactorClientHttpConnector | Reactor Netty HttpClient | WebFlux reactive stack, connection pool, Netty resources và cấu hình transport phong phú |
| JdkClientHttpConnector | java.net.http.HttpClient | Muốn dùng JDK HTTP client có sẵn từ Java 11, giảm phụ thuộc transport ngoài |
| JettyClientHttpConnector | Jetty Reactive HttpClient | Hệ thống đã dùng Jetty hoặc muốn chia sẻ resource của Jetty |
| HttpComponentsClientHttpConnector | Apache HttpComponents HttpClient 5.x | Hệ thống đã chuẩn hóa Apache HTTP client hoặc cần các khả năng của HttpComponents |

Không có connector tốt nhất cho mọi hệ thống. Hãy đánh giá giao thức, proxy, TLS, pool, observability, resource lifecycle, dependency footprint và cách vận hành.

### 4.1. ReactorClientHttpConnector

Đây là connector dựa trên Reactor Netty. Nó có thể nhận một HttpClient đã cấu hình:

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

ClientHttpConnector connector =
        new ReactorClientHttpConnector(httpClient);

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

Đây là lựa chọn phổ biến trong ứng dụng Spring Boot WebFlux vì spring-boot-starter-webflux đưa Reactor Netty vào dependency mặc định.

Các khả năng quan trọng của Reactor Netty:

- ConnectionProvider để quản lý pool.
- Event loop và non-blocking network I/O.
- Connect timeout và response timeout.
- TLS configuration.
- Proxy configuration.
- HTTP/1.1 và HTTP/2 theo cấu hình, transport và server.
- Metrics cho connection và request khi bật observability phù hợp.

### 4.2. JdkClientHttpConnector

Connector này sử dụng java.net.http.HttpClient của JDK:

~~~java
HttpClient jdkClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

ClientHttpConnector connector =
        new JdkClientHttpConnector(jdkClient);

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

JDK HttpClient có sẵn từ Java 11 và hỗ trợ HTTP/1.1, HTTP/2, TLS, proxy và async API. Spring adapter chuyển request/response của nó về ClientHttpConnector abstraction.

Lưu ý: các tùy chọn riêng của Reactor Netty như ConnectionProvider hay ChannelOption không áp dụng trực tiếp cho JDK connector. Cấu hình phải theo API của HTTP client nền tương ứng.

### 4.3. JettyClientHttpConnector

Jetty connector dùng Jetty Reactive HttpClient. Nó hữu ích khi hệ thống đã dùng Jetty và muốn quản lý resource theo cùng nền tảng.

~~~java
HttpClient jettyClient = new HttpClient();
JettyClientHttpConnector connector =
        new JettyClientHttpConnector(jettyClient);
~~~

Đoạn trên minh họa cách tạo connector từ Jetty client; trong ứng dụng thực tế cần cấu hình, start/stop và quản lý resource theo hướng dẫn của phiên bản Jetty đang dùng. Jetty client và JettyResourceFactory có lifecycle riêng; không tạo một client mới cho từng HTTP request.

### 4.4. HttpComponentsClientHttpConnector

Spring có connector cho Apache HttpComponents HttpClient 5.x:

~~~java
ClientHttpConnector connector =
        new HttpComponentsClientHttpConnector();

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

Implementation mặc định tạo và khởi động một CloseableHttpAsyncClient. Khi tự cung cấp client, ứng dụng cần quản lý lifecycle và đóng resource đúng lúc. Không để client async hoặc connection manager tồn tại vô hạn sau khi ApplicationContext đóng.

### 4.5. Boot auto-detect connector

Spring Boot tự chọn ClientHttpConnector theo dependency có trên classpath. Trong Spring Boot 3.5, thứ tự ưu tiên phổ biến là:

1. Reactor Netty.
2. Jetty Reactive Streams client.
3. Apache HttpClient.
4. JDK HttpClient.

Nếu nhiều implementation cùng có mặt, connector có ưu tiên cao hơn sẽ được chọn. spring-boot-starter-webflux mặc định kéo theo Reactor Netty.

Nếu muốn kiểm soát chính xác, khai báo ClientHttpConnector bean riêng hoặc chọn connector qua cấu hình Boot phù hợp. Đừng dựa vào việc "máy đang có dependency nào" để đoán transport production; hãy xác nhận dependency tree và cấu hình runtime.

## 5. WebClient.Builder và cấu hình request

### 5.1. Tạo WebClient

Có hai cách phổ biến:

~~~java
WebClient simple = WebClient.create();

WebClient withBaseUrl =
        WebClient.create("https://catalog.example.com");

WebClient configured = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
~~~

WebClient đã build là immutable. Muốn tạo client khác từ cấu hình cũ, dùng mutate():

~~~java
WebClient catalogClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

WebClient adminClient = catalogClient.mutate()
        .defaultHeader("X-Client-Name", "admin")
        .build();
~~~

Client đầu không bị thay đổi khi tạo client thứ hai.

### 5.2. Dùng WebClient.Builder do Spring Boot cung cấp

Trong ứng dụng Spring Boot, nên inject WebClient.Builder đã được auto-configure:

~~~java
@Service
public class CatalogService {

    private final WebClient webClient;

    public CatalogService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://catalog.example.com")
                .build();
    }
}
~~~

Builder của Boot có thể mang các cấu hình chung như connector, codec và observation. Builder là object có trạng thái: các thay đổi trên một builder ảnh hưởng tới những client được build tiếp theo từ builder đó. Nếu cần nhiều biến thể độc lập, clone builder trước khi thay đổi.

Gọi WebClient.create() vẫn hợp lệ, nhưng cách đó không tự nhận các tùy chỉnh mà Spring Boot đã áp dụng cho WebClient.Builder.

### 5.3. baseUrl, defaultHeader và defaultRequest

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com/v1")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Application", "inventory")
        .defaultRequest(request -> {
            // Có thể bổ sung request metadata chung.
        })
        .build();
~~~

baseUrl giúp tránh lặp host/path prefix. defaultHeader áp dụng header mặc định cho request, trừ khi request cụ thể ghi đè theo quy tắc của builder.

Không đặt access token của người dùng vào defaultHeader trên một singleton client dùng chung cho nhiều user. Credential nên được gắn theo request hoặc lấy từ security context phù hợp để tránh rò token giữa người dùng.

### 5.4. URI builder và query parameter

~~~java
Mono<String> result = client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/products")
                .queryParam("category", "keyboard")
                .queryParam("page", 0)
                .build())
        .retrieve()
        .bodyToMono(String.class);
~~~

URI builder giúp encode path/query đúng cách. Tránh nối chuỗi URL thủ công khi dữ liệu đầu vào có khoảng trắng, dấu tiếng Việt, ký tự & hoặc ký tự dành riêng.

## 6. Cách gửi request và nhận response

### 6.1. retrieve()

retrieve() là cách ngắn gọn khi muốn lấy body và dùng xử lý status mặc định:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

Mặc định, response 4xx/5xx được chuyển thành WebClientResponseException. Có thể thêm onStatus:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> response.createException()
                        .map(NotFoundException::new))
        .bodyToMono(Product.class);
~~~

Đây là snippet minh họa; NotFoundException là exception do ứng dụng định nghĩa.

### 6.2. exchangeToMono()

Khi cần tự điều khiển response theo status, dùng exchangeToMono:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                        .then(Mono.empty());
            }
            return response.createError();
        });
~~~

exchangeToMono cung cấp ClientResponse để xử lý status, headers và body tùy ý. Nếu không đọc body, phải đảm bảo response được release/consume đúng cách để connection có thể được tái sử dụng.

Không giữ ClientResponse rồi trả nó ra ngoài để dùng sau khi callback kết thúc. Hãy decode body trong callback hoặc chuyển sang kiểu dữ liệu sở hữu rõ ràng.

### 6.3. bodyToMono và bodyToFlux

- bodyToMono(Product.class): giải mã một body thành tối đa một object.
- bodyToFlux(Product.class): đọc một chuỗi phần tử từ body dạng streaming, chẳng hạn NDJSON hoặc media type tương thích.
- bodyToMono(String.class): đọc toàn bộ body thành String; không phù hợp với response vô hạn hoặc rất lớn.
- bodyToMono(byte[].class): aggregate body vào mảng byte; cần cân nhắc dung lượng.

Với JSON array nhỏ, có thể dùng Flux hoặc Mono<List<T>> tùy contract. Với dữ liệu lớn hoặc stream liên tục, tránh aggregate toàn bộ response vào bộ nhớ.

### 6.4. Request body

~~~java
Mono<OrderResponse> created = client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("p-1", 2))
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

bodyValue dùng khi đã có object hoặc value sẵn. Với Publisher, dùng body:

~~~java
Flux<OrderResponse> result = client.post()
        .uri("/orders/bulk")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(orderPublisher, OrderRequest.class)
        .retrieve()
        .bodyToFlux(OrderResponse.class);
~~~

Đoạn thứ hai giả định upstream hỗ trợ NDJSON và contract streaming tương ứng. Content-Type phải khớp format mà server chấp nhận.

## 7. Filters: nơi đặt logic chung của WebClient

ExchangeFilterFunction cho phép chèn logic trước và sau HTTP exchange mà không phải lặp code trong từng service method.

### 7.1. Thêm correlation ID

~~~java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            ClientRequest filtered = ClientRequest.from(request)
                    .header("X-Correlation-Id", UUID.randomUUID().toString())
                    .build();

            return next.exchange(filtered);
        };
~~~

Filter tạo ClientRequest mới và chuyển tiếp sang filter tiếp theo. Nếu request đã có correlation ID từ upstream, nên giữ ID đó thay vì luôn tạo ID mới.

### 7.2. Logging request và response metadata

~~~java
ExchangeFilterFunction loggingFilter =
        ExchangeFilterFunction.ofRequestProcessor(request -> {
            log.debug("HTTP {} {}", request.method(), request.url());
            return Mono.just(request);
        });
~~~

Có thể dùng ofResponseProcessor để quan sát status và headers. Không log Authorization, Cookie, token, password hoặc toàn bộ body chứa dữ liệu nhạy cảm.

Nếu filter cần đọc response body để logging, phải chú ý body là stream chỉ đọc một lần. Cần buffer và tái tạo response đúng cách; việc đọc body không kiểm soát có thể làm consumer phía sau không còn dữ liệu.

### 7.3. Thêm filter vào builder

~~~java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(loggingFilter)
        .build();
~~~

Filter được thực hiện theo chuỗi. Một filter có thể sửa request, gọi filter kế tiếp, rồi quan sát hoặc biến đổi response khi publisher trả kết quả.

Không dùng filter làm nơi chứa toàn bộ business logic của endpoint. Hãy giữ filter cho concerns dùng chung như authentication, tracing, metrics hoặc header chuẩn.

## 8. Vai trò của codec và giới hạn bộ nhớ

WebClient sử dụng HTTP message codecs để serialize request và deserialize response. Spring cung cấp codec cho JSON, String, byte[], form data, multipart và các media type phổ biến.

Ví dụ cấu hình Jackson codec và giới hạn buffer:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Spring mặc định giới hạn lượng dữ liệu được buffer trong bộ nhớ cho các codec aggregate; tài liệu Framework 6.2 nêu mức mặc định 256 KB cho default codecs. Khi vượt giới hạn có thể phát DataBufferLimitException.

Tăng giới hạn chỉ khi use case thực sự cần. Với file lớn, streaming upload/download thường tốt hơn việc tăng giới hạn lên hàng trăm MB.

### 8.1. DataBuffer và ownership

Response body là luồng DataBuffer. Khi dùng connector dựa trên Netty, buffer có thể dùng pooled direct memory. Nếu tự đọc/giữ buffer ngoài lifecycle callback, phải hiểu retain/release và quy tắc ownership.

Ưu tiên bodyToMono/bodyToFlux và codec chuẩn để Spring quản lý buffer. Chỉ tự thao tác DataBuffer khi có yêu cầu cụ thể và test cả success, error, cancellation để tránh memory leak.

## 9. Cấu hình transport với Reactor Netty

### 9.1. Connection timeout và response timeout

Các timeout có ý nghĩa khác nhau:

| Timeout | Giới hạn |
| --- | --- |
| Connect timeout | Thời gian thiết lập TCP connection |
| TLS handshake timeout | Thời gian hoàn tất TLS negotiation |
| Response timeout | Thời gian chờ dữ liệu response theo chính sách transport |
| Read timeout | Khoảng thời gian không đọc được dữ liệu theo handler cấu hình |
| Write timeout | Thời gian ghi dữ liệu theo handler cấu hình |
| Mono.timeout(...) | Thời gian publisher của request được phép chạy trước khi bị timeout/cancel |

Không gom tất cả thành một con số timeout. Một request tải file lớn có thể cần thời gian tổng dài nhưng vẫn phải có giới hạn kết nối và idle phù hợp.

### 9.2. ConnectionProvider và pool

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
        .responseTimeout(Duration.ofSeconds(5));

ClientHttpConnector connector =
        new ReactorClientHttpConnector(httpClient);
~~~

Ý nghĩa:

- maxConnections giới hạn số connection được pool quản lý.
- pendingAcquireTimeout giới hạn thời gian chờ lấy connection khi pool hết capacity.
- maxIdleTime giới hạn tuổi idle của connection.
- maxLifeTime giới hạn tuổi tồn tại của connection.
- CONNECT_TIMEOUT_MILLIS đặt giới hạn thiết lập connection.
- responseTimeout đặt timeout đọc response theo semantics Reactor Netty.

Các con số trên chỉ là ví dụ khởi đầu, không phải sizing phù hợp cho mọi tải. Phải dựa vào concurrency, upstream quota, latency, request duration và load test.

Khi tự tạo ConnectionProvider, phải dispose khi ApplicationContext đóng. Trong ứng dụng thông thường, dùng global Reactor Netty resources hoặc resource factory do Spring quản lý sẽ giảm nguy cơ tạo nhiều event-loop/pool riêng không cần thiết.

### 9.3. Không tạo WebClient cho từng request

Không làm:

~~~java
public Mono<Product> find(String id) {
    WebClient client = WebClient.builder().build();
    return client.get().uri("/products/{id}", id)
            .retrieve().bodyToMono(Product.class);
}
~~~

Tạo client mới liên tục làm khó chia sẻ connector, pool, event loop, filter và metrics. Thông thường nên tạo WebClient bean dùng lâu dài cho từng upstream hoặc nhóm cấu hình.

Một WebClient có thể được dùng đồng thời bởi nhiều request vì bản thân WebClient immutable. Tránh lưu trạng thái mutable riêng của user trong object WebClient singleton.

## 10. TLS, proxy, authentication và an toàn mạng

### 10.1. HTTPS và certificate validation

Với endpoint HTTPS, connector thực hiện TLS handshake và kiểm tra certificate theo cấu hình của HTTP client nền. Không tắt certificate validation để "cho request chạy được".

Nếu upstream dùng internal CA, cấu hình trust store/SSL context phù hợp. Cần xác minh hostname và chuỗi certificate, đồng thời có quy trình rotate certificate.

### 10.2. Proxy

Mỗi transport có API proxy riêng. Reactor Netty, JDK HttpClient, Jetty và Apache HttpComponents không dùng chung cấu hình proxy native. Chọn connector theo khả năng cần và cấu hình proxy ở đúng client.

### 10.3. Authorization header

Có thể thêm Bearer token theo request:

~~~java
Mono<Product> result = client.get()
        .uri("/products/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Product.class);
~~~

Không lưu token người dùng vào defaultHeader của WebClient singleton dùng chung nhiều người. Dùng token relay hoặc security context đúng cách, bảo đảm token không xuất hiện trong log.

### 10.4. SSRF và kiểm soát URL đích

Nếu người dùng có thể nhập URL rồi backend dùng WebClient gọi tới URL đó, ứng dụng có thể bị lợi dụng làm SSRF. Kiểm soát scheme, hostname, port và path bằng allowlist; cân nhắc chặn loopback, private IP, link-local và metadata endpoint theo use case.

Không chỉ kiểm tra chuỗi hostname trước khi DNS resolve; cần cân nhắc DNS rebinding và redirect. Không để người dùng tự điều khiển proxy hoặc credential của connector.

## 11. Error handling, retry và cancellation

### 11.1. HTTP status không phải transport error

Có hai nhóm lỗi khác nhau:

- **Transport error:** DNS, connection refused, TLS failure, connect/read timeout, socket reset.
- **HTTP response error:** server trả 400, 401, 404, 429 hoặc 500.

Một response 404 vẫn là HTTP exchange hoàn tất ở tầng transport. retrieve() mặc định chuyển status 4xx/5xx thành WebClientResponseException; exchangeToMono cho phép xử lý status tùy ý.

### 11.2. Retry có điều kiện

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(error ->
                        error instanceof WebClientRequestException));
~~~

Đây là ví dụ chỉ retry lỗi request/transport, không retry mọi 4xx/5xx. Trong production, cần giới hạn retry, jitter, timeout và metric.

Không retry mù quáng POST tạo đơn hàng hoặc thanh toán. Nếu request đã tới server nhưng response bị mất, retry có thể tạo side effect trùng. Dùng idempotency key hoặc contract deduplication nếu nghiệp vụ cho phép retry.

### 11.3. Cancellation

Nếu caller cancel subscription, cancellation được truyền xuống WebClient và connector. Transport có thể hủy request/đọc response và giải phóng tài nguyên tương ứng.

Đừng subscribe() riêng trong service nếu caller cần kiểm soát lifecycle. Hãy trả Mono/Flux để controller, scheduler hoặc component sở hữu công việc quyết định subscription.

## 12. Observability: metrics, tracing và logging

WebClient có thể tích hợp ObservationRegistry/Micrometer để ghi nhận HTTP client observations. Khi bật metrics/tracing đúng cách, có thể quan sát:

- Request count và status.
- Latency.
- Connection pool active/idle/pending.
- Connection errors, timeouts và retry.
- Upstream service name.
- Trace/span ID để nối request qua nhiều service.

Đừng dùng URL đầy đủ hoặc ID duy nhất làm metric tag nếu gây cardinality cao. Không log token, cookie hoặc body nhạy cảm.

Có thể dùng ExchangeFilterFunction để bổ sung correlation ID nghiệp vụ, nhưng tracing framework nên quản lý trace/span lifecycle thay vì tự tạo trace ID độc lập cho mọi request.

## 13. Dự án chạy được: Java 17+ và Spring Boot 3.5.16

Ví dụ này tạo một ứng dụng nhỏ có WebClient gọi một upstream catalog. Để chạy không cần Internet:

- Ứng dụng cung cấp endpoint demo /mock-upstream/products/{id}.
- CatalogClient dùng WebClient và ClientHttpConnector để gọi lại endpoint đó qua HTTP thật.
- Endpoint /catalog/products/{id} trả kết quả của upstream.
- Integration test dùng MockWebServer để kiểm tra request/response qua một connector thực.

Điểm học tập là WebClient API vẫn giữ nguyên trong khi connector quyết định transport. Ứng dụng demo dùng Reactor Netty connector và pool có cấu hình.

### 13.1. Cấu trúc project

~~~text
webclient-connector-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/client/
    │   │   ├── DemoApplication.java
    │   │   ├── Product.java
    │   │   ├── WebClientConfiguration.java
    │   │   ├── CatalogClient.java
    │   │   ├── CatalogController.java
    │   │   └── MockUpstreamController.java
    │   └── resources/application.yml
    └── test/java/example/client/
        └── CatalogClientIntegrationTest.java
~~~

### 13.2. pom.xml

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
    <artifactId>webclient-connector-demo</artifactId>
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

spring-boot-starter-webflux cung cấp WebClient, Reactor Netty và WebFlux. spring-boot-starter-test cung cấp JUnit 5, AssertJ và Spring test. MockWebServer tạo HTTP upstream giả lập để test transport thật mà không gọi dịch vụ bên ngoài.

### 13.3. DemoApplication.java

~~~java
package example.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 13.4. Product.java

~~~java
package example.client;

public record Product(String id, String name) {
}
~~~

### 13.5. WebClientConfiguration.java

~~~java
package example.client;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
                .maxConnections(50)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .build();
    }

    @Bean
    ClientHttpConnector catalogConnector(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
                .create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
                .responseTimeout(Duration.ofSeconds(5));

        return new ReactorClientHttpConnector(httpClient);
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ClientHttpConnector catalogConnector,
            Environment environment) {

        String baseUrl =
                environment.getRequiredProperty("catalog.base-url");

        return builder.clone()
                .baseUrl(baseUrl)
                .clientConnector(catalogConnector)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Giải thích:

- ConnectionProvider quản lý pool riêng cho upstream catalog.
- CONNECT_TIMEOUT_MILLIS giới hạn thời gian thiết lập kết nối.
- responseTimeout đặt giới hạn đọc response theo Reactor Netty.
- ReactorClientHttpConnector nối HttpClient với abstraction Spring.
- WebClient.Builder vẫn phụ trách base URL, headers, codec và API request.
- destroyMethod dispose giải phóng pool khi Spring ApplicationContext đóng.

Trong ứng dụng lớn, cân nhắc chia pool theo upstream hoặc nhóm SLA. Đừng tạo pool mới cho mỗi request.

### 13.6. CatalogClient.java

~~~java
package example.client;

import org.springframework.stereotype.Component;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<Product> findById(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(Product.class);
                    }

                    if (response.statusCode().value() == 404) {
                        return response.releaseBody()
                                .then(Mono.empty());
                    }

                    return response.createError();
                });
    }
}
~~~

CatalogClient xử lý response theo nghiệp vụ:

- 2xx: giải mã JSON thành Product.
- 404: release body và trả Mono.empty().
- Status khác: phát WebClientResponseException qua createError().

Connector không quyết định 404 nghĩa là Mono.empty(); đó là policy của CatalogClient.

### 13.7. CatalogController.java

~~~java
package example.client;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/catalog/products/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {

        return catalogClient.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<Product>notFound().build());
    }
}
~~~

Controller chỉ compose Mono và chuyển kết quả thành HTTP response của ứng dụng. Không gọi block().

### 13.8. MockUpstreamController.java

~~~java
package example.client;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/mock-upstream")
public class MockUpstreamController {

    @GetMapping("/products/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {

        if ("p-1".equals(id)) {
            return Mono.just(ResponseEntity.ok(
                    new Product("p-1", "Keyboard")));
        }

        return Mono.just(
                ResponseEntity.<Product>notFound().build());
    }
}
~~~

Đây là upstream giả lập cùng process để demo không cần Internet. Trong production, base URL sẽ trỏ tới service catalog thật và endpoint mock này nên được bỏ khỏi deployment.

### 13.9. application.yml

~~~yaml
server:
  port: 8080

catalog:
  base-url: http://localhost:8080/mock-upstream
~~~

Ứng dụng mặc định chạy cổng 8080 và WebClient gọi lại endpoint mock-upstream qua HTTP. Test sẽ ghi đè catalog.base-url bằng địa chỉ MockWebServer.

### 13.10. CatalogClientIntegrationTest.java

~~~java
package example.client;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CatalogClientIntegrationTest {

    private static final MockWebServer UPSTREAM = startUpstream();

    private static MockWebServer startUpstream() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.base-url",
                () -> UPSTREAM.url("/").toString());
    }

    @Autowired
    WebTestClient webTestClient;

    @AfterAll
    static void stopUpstream() throws IOException {
        UPSTREAM.shutdown();
    }

    @Test
    void forwardsRequestAndDecodesProduct() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"p-1","name":"Keyboard"}
                        """));

        webTestClient.get()
                .uri("/catalog/products/p-1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("p-1")
                .jsonPath("$.name").isEqualTo("Keyboard");

        RecordedRequest request =
                UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/products/p-1");
        assertThat(request.getHeader("Accept"))
                .contains("application/json");
    }

    @Test
    void mapsUpstream404ToEmptyAndApplication404() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
                .setResponseCode(404)
                .setBody("not found"));

        webTestClient.get()
                .uri("/catalog/products/missing")
                .exchange()
                .expectStatus().isNotFound();

        RecordedRequest request =
                UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getPath())
                .isEqualTo("/products/missing");
    }
}
~~~

Hai test bao phủ hai lớp:

1. WebTestClient gửi request vào ứng dụng qua mock WebFlux exchange.
2. CatalogClient thực hiện HTTP network I/O thật qua ReactorClientHttpConnector tới MockWebServer.
3. MockWebServer ghi nhận method, path và Accept header.
4. Spring codec giải mã JSON thành Product.
5. Status 404 được CatalogClient chuyển thành Mono.empty(), sau đó controller trả 404.

Đây là integration test của WebClient/connector và Spring context, nhưng inbound request của WebTestClient vẫn là mock exchange; phần outbound tới MockWebServer là HTTP thực.

### 13.11. Chạy project

Trong thư mục chứa pom.xml:

~~~bash
mvn test
~~~

Khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Lấy sản phẩm tồn tại:

~~~bash
curl -i http://localhost:8080/catalog/products/p-1
~~~

Response body:

~~~json
{"id":"p-1","name":"Keyboard"}
~~~

Sản phẩm không tồn tại:

~~~bash
curl -i http://localhost:8080/catalog/products/missing
~~~

Kết quả là HTTP 404. Đây là behavior của controller sau khi CatalogClient nhận 404 từ upstream mock.

Nếu test dùng MockWebServer, kết quả mong đợi là:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là kết quả mong đợi khi test pass, không phải stdout của một lần chạy Maven thực tế. Hãy chạy mvn test trong project để xác nhận trên môi trường của bạn.

## 14. Khi nào nên thay connector?

Không thay connector chỉ vì muốn "tăng tốc". Trước khi đổi, xác định vấn đề nằm ở đâu:

- Pool cạn vì maxConnections quá thấp?
- Request chờ pool lâu vì pending acquire?
- DNS hoặc TCP connect chậm?
- TLS handshake chậm?
- Server phản hồi chậm?
- Codec aggregate body quá lớn?
- Filter đang đọc body hai lần?
- Upstream rate limit?
- Event loop bị block do code ứng dụng?

Connector là một phần của đường đi request. Thay connector có thể thay đổi resource model, timeout, proxy, TLS và metrics; nó không tự sửa query chậm, server chậm hoặc retry policy sai.

### 14.1. Dấu hiệu cần điều chỉnh pool

- Pending acquire tăng liên tục.
- Active connections thường xuyên chạm maxConnections.
- Latency tăng khi concurrency tăng.
- Nhiều request chờ lấy connection dù upstream phản hồi nhanh.

Tăng pool có thể tăng tải lên upstream và tiêu tốn socket/file descriptor. Cần phối hợp quota của upstream, số instance và số client thực tế.

### 14.2. Dấu hiệu cần xem timeout

- Connection refused hoặc DNS failure: xem connect timeout và network.
- TLS handshake chậm: xem certificate chain, proxy và TLS setup.
- Response chậm: xem upstream, response timeout và tracing.
- Response streaming lâu: không dùng timeout tổng ngắn như thể đó là request JSON nhỏ.
- Pool acquire timeout: xem connection saturation và pending queue.

## 15. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ WebClient tự mở socket | Không hiểu vai trò transport | Tìm ClientHttpConnector đang được dùng |
| Nghĩ ClientHttpConnector giải mã JSON | Trộn transport với codec | Dùng HttpMessageReader/Writer và ExchangeStrategies |
| Tạo WebClient mỗi request | Không chia sẻ pool/resource hiệu quả | Dùng WebClient bean lâu dài |
| Nghĩ đổi connector không ảnh hưởng vận hành | Timeout, pool, TLS và metrics thay đổi | Test transport và quản lý resource |
| Dùng Reactor Netty ChannelOption cho JDK connector | Cấu hình sai abstraction | Dùng API của HTTP client nền |
| Không dispose custom ConnectionProvider | Rò resource khi context restart | Quản lý lifecycle bằng Spring bean |
| Tạo nhiều event loop/pool không cần thiết | Tốn thread, memory và socket | Chia sẻ global resources hoặc resource factory |
| Tăng maxConnections không có load test | Làm upstream quá tải | Đo pending/active pool và quota upstream |
| Dùng một timeout cho mọi loại request | Cắt stream hợp lệ hoặc chờ quá lâu | Phân biệt connect, response, idle và overall timeout |
| Dùng retrieve() nhưng không xử lý status | 4xx/5xx trở thành WebClientResponseException | onStatus hoặc exchangeToMono |
| Đọc response body trong filter rồi không tái tạo | Consumer phía sau mất body | Tránh consume hoặc clone/rebuild response đúng cách |
| Aggregate file lớn thành byte[] | Tăng heap và có thể OOM | Streaming DataBuffer/Flux |
| Tắt TLS certificate validation | Mở cửa cho MITM | Cấu hình trust store đúng |
| Log Authorization/Cookie | Rò credential | Redact headers và body |
| Retry POST không idempotency | Tạo side effect trùng | Idempotency key và retry policy |
| Gọi block() trong event-loop | Chặn xử lý các request khác | Compose Mono/Flux |
| Tự subscribe() trong service | Mất cancellation/error ownership | Trả Publisher cho caller |
| Cho user tự nhập URL đích | Nguy cơ SSRF | Allowlist scheme/host/port/path |
| Nghĩ WebTestClient mock đã kiểm tra connector | Không có network I/O inbound | Dùng MockWebServer hoặc live HTTP integration test |

## 16. Checklist review WebClient và connector

Trước khi đưa client vào production:

1. WebClient có được tái sử dụng như bean thay vì tạo mỗi request không?
2. Spring Boot đang tự chọn connector nào trên classpath?
3. Có cần override connector vì proxy, TLS, pool hoặc protocol không?
4. Connector có dùng resource lifecycle phù hợp không?
5. Connection pool có maxConnections và pendingAcquireTimeout phù hợp không?
6. Connect, response, read/write và overall timeout đã được phân biệt chưa?
7. Codec maxInMemorySize có phù hợp với response size không?
8. File lớn có được stream thay vì aggregate không?
9. Filters có tránh đọc response body hai lần không?
10. Authorization header và cookie có được bảo vệ khỏi log không?
11. TLS certificate/hostname verification có được giữ bật không?
12. URL đích có được kiểm soát để chống SSRF không?
13. Retry có giới hạn và idempotency phù hợp không?
14. Error status 4xx/5xx có được map theo business contract không?
15. Metrics có quan sát pool, latency, status và timeout không?
16. Test có xác minh method, URI, header, body và transport behavior không?
17. Resource custom có được đóng khi ApplicationContext dừng không?

## 17. Ghi nhớ

- WebClient là fluent reactive HTTP API; ClientHttpConnector là adapter tới HTTP client transport.
- Connector contract nhận method, URI và request callback, rồi trả Mono<ClientHttpResponse>.
- WebClient xử lý request/response semantics, filters và codecs; connector thực hiện transport I/O.
- Spring hỗ trợ Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient và Apache HttpComponents.
- Spring Boot 3.5 auto-detect connector theo dependency, ưu tiên Reactor Netty, Jetty, Apache rồi JDK.
- Dùng builder bean của Boot để giữ codec, connector và observation configuration; clone builder khi cần biến thể độc lập.
- ReactorClientHttpConnector có thể nhận HttpClient đã cấu hình pool, timeout, TLS và proxy.
- ConnectionProvider và event-loop resources cần được chia sẻ/quản lý lifecycle đúng cách.
- Tách connect timeout, response timeout, read/write timeout và Mono.timeout.
- Codec maxInMemorySize bảo vệ memory; stream response lớn thay vì aggregate.
- Filters phù hợp cho tracing, auth header, metrics và logging metadata.
- retrieve() phù hợp flow đơn giản; exchangeToMono phù hợp xử lý status/body tùy chỉnh.
- HTTP status error khác transport error; retry phải xét idempotency.
- Test connector bằng MockWebServer hoặc live HTTP, không suy luận network behavior từ mock exchange.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html)
- [Spring Framework 6.2 — WebClient Configuration, Client Connector, Resources and Timeouts](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — ClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ClientHttpConnector.html)
- [Spring Framework 6.2 — ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html)
- [Spring Framework 6.2 — JdkClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/JdkClientHttpConnector.html)
- [Spring Framework 6.2 — JettyClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/JettyClientHttpConnector.html)
- [Spring Framework 6.2 — HttpComponentsClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/HttpComponentsClientHttpConnector.html)
- [Spring Boot 3.5 — Calling REST Services and WebClient Runtime](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5.16 — ClientHttpConnectorBuilder Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/reactive/ClientHttpConnectorBuilder.html)
