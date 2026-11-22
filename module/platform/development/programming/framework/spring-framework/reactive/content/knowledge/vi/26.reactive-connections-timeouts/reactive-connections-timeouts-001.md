# Chọn connector Reactor Netty, JDK, Jetty hoặc HttpComponents

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Kết nối và thời hạn

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `ClientHttpConnector` trong WebClient và phân biệt HTTP client outbound với server runtime của WebFlux.
2. So sánh Reactor Netty, JDK HttpClient, Jetty và Apache HttpComponents 5 về dependency, connection pool, timeout, HTTP/2 và khả năng cấu hình.
3. Chọn connector theo tải, SLA, dependency và yêu cầu vận hành của hệ thống.
4. Cấu hình connector tường minh bằng `WebClient.Builder.clientConnector` mà vẫn giữ customizer của Spring Boot.
5. Cấu hình connection pool, pending acquire, connect/response timeout, TLS, proxy và redirect.
6. Phân biệt timeout chờ pool, timeout kết nối, timeout đọc response và deadline tổng thể.
7. Quản lý lifecycle của connection provider, HTTP client và executor.
8. Kiểm thử WebClient qua connector thật bằng MockWebServer và Reactor Test.

## 1. ClientHttpConnector là gì?

`WebClient` là API HTTP client reactive của Spring. Nó cung cấp fluent API để tạo request, ghi body, nhận response và chuyển dữ liệu thành `Mono` hoặc `Flux`.

`ClientHttpConnector` là lớp tích hợp ở tầng transport. Nó nối request/response abstraction của Spring với một HTTP client engine cụ thể. Nhờ đó, code nghiệp vụ dùng WebClient không cần thay đổi khi transport bên dưới đổi:

```text
Ứng dụng
   |
   v
WebClient
   |
   v
ClientHttpConnector
   |
   +---- ReactorClientHttpConnector
   +---- JdkClientHttpConnector
   +---- JettyClientHttpConnector
   +---- HttpComponentsClientHttpConnector
   |
   v
HTTP / TLS / connection pool / socket
   |
   v
Remote server
```

Connector ảnh hưởng cách mở và tái sử dụng connection, TLS, proxy, protocol, timeout và tài nguyên nền. Nó không thay đổi contract nghiệp vụ của API remote.

Cần phân biệt hai phía:

- **WebClient connector:** gửi HTTP request từ ứng dụng ra ngoài.
- **WebFlux server runtime:** nhận request từ client đi vào ứng dụng.

Một ứng dụng có thể dùng Reactor Netty làm server nhưng dùng JDK HttpClient cho WebClient outbound. Hai lựa chọn độc lập; đổi connector WebClient không tự đổi server đang phục vụ endpoint.

## 2. So sánh bốn connector

| Connector | Engine | Điểm mạnh | Điều cần cân nhắc |
| --- | --- | --- | --- |
| Reactor Netty | Reactor Netty / Netty | Reactive native, pool và transport tuning chi tiết, tích hợp tự nhiên với Reactor | Thêm dependency Netty; cần cấu hình pool và timeout theo tải. |
| JDK | `java.net.http.HttpClient` | Có sẵn từ JDK 11, ít dependency, hỗ trợ HTTP/2 và TLS | Ít API công khai để điều khiển pool; một số timeout cần đặt ở request/publisher. |
| Jetty | Jetty HttpClient qua Jetty Reactive HttpClient | Hợp với hệ thống đã vận hành Jetty, có cấu hình connection và lifecycle riêng | Cần dependency Jetty tương thích và quản lý start/stop. |
| HttpComponents | Apache HttpComponents 5 Async Client | Connection manager và pooling phong phú, async HTTP engine | Cần Apache 5 async dependency và quản lý lifecycle. |

Không có connector tốt nhất cho mọi ứng dụng. Hãy xét:

- Hệ thống đã dùng engine nào và muốn giảm dependency mới?
- Có cần điều khiển pool theo host hoặc route?
- Có yêu cầu HTTP/2, proxy, mutual TLS hoặc truststore riêng?
- Cần timeout riêng cho acquire, connect, read và write không?
- Muốn tái sử dụng client/connection manager sẵn có hay tạo client riêng?
- Đội vận hành đã có metric, tracing và kinh nghiệm xử lý engine nào?

## 3. Connector mặc định và cấu hình tường minh

Khi dùng `spring-boot-starter-webflux`, Spring Boot cung cấp `WebClient.Builder` đã được customizer cấu hình. Starter WebFlux thông thường đưa Reactor Netty vào classpath, vì vậy đây là lựa chọn phổ biến.

Nếu không chỉ định connector, Spring Framework có thể chọn implementation dựa trên HTTP client có mặt trên classpath. Thay đổi dependency có thể làm thay đổi transport được chọn. Khi transport là quyết định vận hành, cấu hình tường minh:

```java
WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
```

Trong ứng dụng Boot, nên bắt đầu từ builder được inject rồi clone khi cần cấu hình riêng:

```java
@Bean
WebClient catalogWebClient(
        WebClient.Builder builder,
        ClientHttpConnector connector) {

    return builder.clone()
            .baseUrl("https://catalog.example.com")
            .clientConnector(connector)
            .build();
}
```

`clone()` tạo builder riêng mà không sửa prototype builder dùng chung. Cách này giữ các customizer Boot đã đăng ký như codec, observation hoặc filter.

Không gọi `WebClient.create()` tùy tiện trong ứng dụng cần cấu hình tập trung. Builder tạo thủ công có thể bỏ qua customizer, default header, filter, codec và observation của ứng dụng.

## 4. Reactor Netty

### 4.1. Khi nào chọn?

Reactor Netty phù hợp khi ứng dụng đã dùng Reactor/WebFlux và muốn HTTP client reactive native. Nó cung cấp cấu hình chi tiết cho connection pool, pending acquire, connect/response timeout, channel handler, proxy, TLS, redirect, HTTP/2, compression và metric.

Đây là lựa chọn mặc định hợp lý cho nhiều ứng dụng WebFlux, nhất là khi cần tinh chỉnh tải outbound và quan sát pool.

### 4.2. Cấu hình connection pool

```java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
        .maxConnections(100)
        .pendingAcquireMaxCount(500)
        .pendingAcquireTimeout(Duration.ofSeconds(10))
        .maxIdleTime(Duration.ofSeconds(30))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(60))
        .build();
```

- `maxConnections` giới hạn số connection trong pool.
- `pendingAcquireMaxCount` giới hạn số request đang chờ connection.
- `pendingAcquireTimeout` giới hạn thời gian chờ connection khả dụng.
- `maxIdleTime` giới hạn tuổi nhàn rỗi.
- `maxLifeTime` giới hạn tuổi tồn tại tối đa.
- `evictInBackground` bật kiểm tra và loại connection không còn phù hợp theo chu kỳ.

Pool hữu hạn giúp chặn số connection và hàng chờ. Khi pool hết connection và hàng chờ đầy hoặc chờ quá lâu, request có thể thất bại khi acquire. Tăng pool không làm remote server xử lý nhanh hơn; pool quá lớn có thể khiến remote service quá tải.

Chọn giới hạn theo số host/route, concurrency, latency và quota của remote service. Không mặc định 100 là con số phù hợp cho mọi môi trường.

### 4.3. Connect và response timeout

```java
HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
        .responseTimeout(Duration.ofSeconds(10))
        .compress(true);
```

`CONNECT_TIMEOUT_MILLIS` giới hạn thời gian thiết lập TCP connection. `responseTimeout` giới hạn khoảng thời gian giữa các thao tác đọc mạng khi nhận response theo semantics của Reactor Netty; nó không phải deadline tổng thể. `compress(true)` cho phép compression theo negotiation và khả năng của hai đầu.

Nếu cần read/write timeout ở channel, có thể thêm handler trong `doOnConnected`:

```java
HttpClient httpClient = HttpClient.create(provider)
        .doOnConnected(connection ->
                connection.addHandlerLast(new ReadTimeoutHandler(15))
                        .addHandlerLast(new WriteTimeoutHandler(15)));
```

Đây là cấu hình thấp hơn tầng HTTP. Timeout handler tác động lên I/O channel; chọn giá trị phù hợp với streaming và endpoint dài hạn.

### 4.4. Tạo WebClient và quản lý pool

```java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogConnectionProvider() {
    return ConnectionProvider.builder("catalog-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(500)
            .pendingAcquireTimeout(Duration.ofSeconds(10))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .build();
}

@Bean
WebClient catalogWebClient(
        WebClient.Builder builder,
        ConnectionProvider catalogConnectionProvider) {

    HttpClient httpClient = HttpClient.create(catalogConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
            .responseTimeout(Duration.ofSeconds(10));

    return builder.clone()
            .baseUrl("https://catalog.example.com")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
}
```

Spring quản lý lifecycle của custom pool và gọi `dispose` khi bean bị hủy. WebClient được tạo một lần và dùng lại; không tạo pool mới cho từng request.

Nếu dùng Reactor Netty global resources mặc định, nhiều client có thể chia sẻ event loop và connection resources. Không dispose global resources giữa lúc ứng dụng còn request đang chạy. Với custom provider, quản lý lifecycle theo bean/application context.

### 4.5. Proxy, TLS và HTTP/2

Proxy có thể cấu hình trên HttpClient:

```java
HttpClient httpClient = HttpClient.create(provider)
        .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal")
                .port(8080));
```

TLS có thể cấu hình qua SSL context:

```java
HttpClient httpClient = HttpClient.create(provider)
        .secure(ssl -> ssl.sslContext(sslContext));
```

`sslContext` phải dùng trust material hợp lệ, chẳng hạn truststore chứa CA nội bộ. Không tắt certificate hoặc hostname verification để sửa nhanh lỗi TLS.

Reactor Netty có thể cấu hình `HttpProtocol.H2` khi client, TLS/ALPN và server hỗ trợ HTTP/2. Với HTTPS, ALPN thường được dùng để thương lượng protocol. Đặt protocol không bảo đảm server đích hỗ trợ nó.

## 5. JDK HttpClient

### 5.1. Khi nào chọn?

`JdkClientHttpConnector` dùng `java.net.http.HttpClient` có sẵn từ JDK 11. Đây là lựa chọn đáng cân nhắc khi muốn giảm dependency bên thứ ba, ứng dụng đã chuẩn hóa JDK HttpClient, cần HTTP/2/TLS theo khả năng JDK và không cần nhiều tùy chọn pool chuyên biệt của Netty hoặc Apache.

### 5.2. Cấu hình

```java
java.net.http.HttpClient jdkClient =
        java.net.http.HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .version(java.net.http.HttpClient.Version.HTTP_2)
                .followRedirects(
                        java.net.http.HttpClient.Redirect.NORMAL)
                .build();

ClientHttpConnector connector =
        new JdkClientHttpConnector(jdkClient);

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(connector)
        .build();
```

JDK builder cho phép cấu hình connect timeout, HTTP version, redirect, proxy selector, SSL context/parameters, authenticator và executor.

### 5.3. Giới hạn cần biết

JDK HttpClient không cung cấp API công khai tương đương đầy đủ với Reactor Netty ConnectionProvider để đặt max connection toàn cục, max pending acquire hoặc idle eviction. Việc tái sử dụng connection do implementation quản lý.

Connect timeout được đặt trên HttpClient. Request timeout có thể được cấu hình ở `java.net.http.HttpRequest`, nhưng `JdkClientHttpConnector` không cung cấp cùng bộ tùy chọn read/write/pool như Reactor Netty.

Có thể đặt deadline reactive ở tầng WebClient:

```java
Mono<CatalogItem> result = client.get()
        .uri("/items/7")
        .retrieve()
        .bodyToMono(CatalogItem.class)
        .timeout(Duration.ofSeconds(12));
```

`Mono.timeout` hủy subscription khi deadline bị vượt. Đây là deadline cho publisher trong ứng dụng, không thay connect timeout và không phải cấu hình riêng cho socket read. Nếu cần pool tuning sâu hoặc timeout theo từng tầng, cân nhắc engine khác.

## 6. Jetty

### 6.1. Khi nào chọn?

Jetty connector phù hợp khi tổ chức đã vận hành Jetty, muốn tái sử dụng hiểu biết/cấu hình Jetty HttpClient hoặc cần tính năng HTTP client của Jetty.

Spring tích hợp qua `JettyClientHttpConnector` và Jetty Reactive HttpClient. Dependency phải tương thích với dòng Jetty mà phiên bản Spring Framework đang hỗ trợ. Không trộn tùy ý các major version Jetty trong cùng ứng dụng.

### 6.2. Cấu hình client

```java
org.eclipse.jetty.client.HttpClient jettyClient =
        new org.eclipse.jetty.client.HttpClient();

jettyClient.setConnectTimeout(5_000);
jettyClient.setIdleTimeout(15_000);
jettyClient.setMaxConnectionsPerDestination(64);
jettyClient.start();

ClientHttpConnector connector =
        new JettyClientHttpConnector(jettyClient);

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(connector)
        .build();
```

`setConnectTimeout` giới hạn thời gian mở connection; `setIdleTimeout` đặt idle timeout theo semantics của Jetty; `setMaxConnectionsPerDestination` giới hạn connection tới một destination. Gọi `start` trước khi gửi request.

Trong ứng dụng Spring, khai báo bean để quản lý lifecycle:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
org.eclipse.jetty.client.HttpClient jettyHttpClient() {
    org.eclipse.jetty.client.HttpClient client =
            new org.eclipse.jetty.client.HttpClient();

    client.setConnectTimeout(5_000);
    client.setIdleTimeout(15_000);
    client.setMaxConnectionsPerDestination(64);
    return client;
}
```

Inject client đã được Spring quản lý vào connector. Không gọi `stop` sau từng request; client được tái sử dụng và chỉ dừng khi application context đóng.

Tên method và tùy chọn có thể khác giữa các major version. Dùng Javadoc đúng Jetty line mà dependency của ứng dụng chọn.

## 7. Apache HttpComponents 5

### 7.1. Khi nào chọn?

`HttpComponentsClientHttpConnector` tích hợp WebClient với Apache HttpComponents 5 Async Client. Chọn khi ứng dụng đã dùng Apache HttpClient, cần connection manager với giới hạn tổng/theo route, muốn cấu hình connection/TLS/proxy qua hệ sinh thái Apache hoặc cần async engine độc lập với Reactor Netty.

Phải dùng dòng **HttpComponents 5 async** tương thích với Spring Framework. Apache HttpClient 4.x blocking không phải client mà connector này yêu cầu.

### 7.2. Connection manager và timeout

```java
ConnectionConfig connectionConfig = ConnectionConfig.custom()
        .setConnectTimeout(Timeout.ofSeconds(5))
        .build();

PoolingAsyncClientConnectionManager manager =
        PoolingAsyncClientConnectionManagerBuilder.create()
                .setMaxConnTotal(200)
                .setMaxConnPerRoute(50)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

RequestConfig requestConfig = RequestConfig.custom()
        .setResponseTimeout(Timeout.ofSeconds(15))
        .build();

CloseableHttpAsyncClient apacheClient =
        HttpAsyncClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .build();

apacheClient.start();

ClientHttpConnector connector =
        new HttpComponentsClientHttpConnector(apacheClient);
```

`setMaxConnTotal` giới hạn tổng connection; `setMaxConnPerRoute` giới hạn connection theo route; `setConnectTimeout` cấu hình thời gian thiết lập kết nối; `setResponseTimeout` cấu hình response timeout. Gọi `start` trước khi gửi request.

### 7.3. Quản lý lifecycle

`CloseableHttpAsyncClient` phải được start và close đúng lifecycle. Có thể để Spring quản lý:

```java
@Bean(initMethod = "start", destroyMethod = "close")
CloseableHttpAsyncClient apacheAsyncClient() {
    PoolingAsyncClientConnectionManager manager =
            PoolingAsyncClientConnectionManagerBuilder.create()
                    .setMaxConnTotal(200)
                    .setMaxConnPerRoute(50)
                    .build();

    return HttpAsyncClients.custom()
            .setConnectionManager(manager)
            .build();
}

@Bean
ClientHttpConnector apacheConnector(
        CloseableHttpAsyncClient apacheAsyncClient) {
    return new HttpComponentsClientHttpConnector(apacheAsyncClient);
}
```

Nếu ứng dụng tự tạo connection manager/client ngoài Spring, ứng dụng phải đóng chúng khi shutdown. Không tạo async client mới cho mỗi request.

## 8. So sánh timeout theo từng tầng

Từ “timeout” có thể chỉ nhiều khoảng thời gian khác nhau:

| Timeout | Đo khoảng thời gian | Ví dụ cấu hình |
| --- | --- | --- |
| Pool acquire | Chờ lấy connection từ pool | Reactor Netty `pendingAcquireTimeout`; pool manager của Apache có cấu hình tương ứng. |
| Connect | Thiết lập TCP connection tới destination | Reactor Netty `CONNECT_TIMEOUT_MILLIS`; JDK `connectTimeout`; Jetty `setConnectTimeout`; Apache `ConnectionConfig`. |
| TLS handshake | Hoàn tất thương lượng TLS | Phụ thuộc connector/engine và cấu hình SSL. |
| Response/read | Chờ response hoặc dữ liệu đọc tiếp | Reactor Netty `responseTimeout`; Jetty idle timeout; Apache response timeout. |
| Write | Ghi request body ra transport | Tùy engine và channel/request configuration. |
| Overall deadline | Tổng thời gian ứng dụng chờ publisher hoàn tất | Reactor `Mono.timeout`/`Flux.timeout` hoặc deadline ở tầng gọi. |

Một request có thể chờ pool 8 giây, connect 2 giây, rồi đọc response 10 giây. Nếu chỉ đặt timeout chung quá lớn, ứng dụng giữ resource lâu hơn dự định. Nếu đặt từng timeout quá ngắn, upload lớn hoặc response streaming hợp lệ có thể bị ngắt.

Với WebClient, `timeout(Duration)` ở publisher hữu ích để đặt deadline tổng thể. Nó hủy publisher khi vượt hạn, nhưng không thay thế pool acquire timeout, connect timeout hoặc idle/read timeout của engine.

Đối với stream vô hạn như SSE, timeout toàn stream thường không phù hợp. Hãy cân nhắc idle timeout giữa các event, heartbeat và cancellation theo contract của stream.

## 9. TLS, proxy, redirect và HTTP/2

### 9.1. TLS

Connector phải xác minh certificate chain và hostname của remote server. Với CA nội bộ, cấu hình truststore hoặc SSL context chứa CA đã được phê duyệt.

Không dùng trust-all manager hoặc tắt hostname verification trong production. Cách đó làm mất xác thực server và có thể mở đường cho man-in-the-middle.

Nếu cần mutual TLS, client phải có key material/client certificate phù hợp. Cách nạp key/trust store phụ thuộc connector; quản lý secret bằng secret store và không ghi password/private key vào log hoặc source control.

### 9.2. Proxy

Proxy có thể được cấu hình ở engine hoặc JDK HttpClient. Xác định rõ proxy áp dụng cho destination nào, cách xác thực và quy tắc bypass nội bộ. Proxy timeout và DNS resolution có thể tạo độ trễ khác với kết nối trực tiếp.

Không ghi proxy credentials hoặc authorization header vào debug log. Đưa proxy host/port vào cấu hình môi trường thay vì hard-code trong source.

### 9.3. Redirect

Redirect policy quyết định client có tự theo response 3xx hay không. Hãy xem xét số hop, cách chuyển method/body theo status code và nguy cơ chuyển credential hoặc dữ liệu nhạy cảm sang origin khác.

Không mặc định mọi redirect đều an toàn cho POST có body hoặc request mang authorization header.

### 9.4. HTTP/2

HTTP/2 multiplex nhiều stream trên một connection và có flow control riêng. Điều này có thể giảm số connection nhưng không loại bỏ giới hạn concurrency, pool, timeout hoặc backpressure ở ứng dụng.

HTTP/2 cần cả client và server hỗ trợ; HTTPS thường dùng ALPN để thương lượng protocol. Cấu hình connector yêu cầu HTTP/2 không buộc server đích phải hỗ trợ. Theo dõi protocol được thương lượng khi debug.

## 10. Connection pool và tái sử dụng WebClient

Một `WebClient` đã build là immutable và phù hợp để dùng lại giữa nhiều request. Hãy tạo client singleton theo destination hoặc nhóm cấu hình rõ ràng.

Một pool nên có giới hạn số connection tối đa, số request chờ acquire, thời gian chờ acquire, idle time, lifetime và số connection theo host/route nếu engine hỗ trợ.

Nếu remote service chỉ cho phép 40 connection, cấu hình pool 500 có thể làm hệ thống tạo áp lực vượt quota. Nếu pool quá nhỏ, request có thể chờ acquire lâu dù remote server vẫn còn năng lực.

Tách pool theo dependency khi destination có SLA khác nhau. Ví dụ API thanh toán có deadline ngắn và quota thấp; API báo cáo có response lớn và thời gian dài. Dùng chung một pool có thể khiến workload chậm chiếm connection của workload quan trọng.

Không tạo WebClient mới trong mỗi lần gọi service chỉ để đổi URI. Dùng base URL, URI template hoặc client riêng khi cần transport policy khác.

## 11. Quan sát, logging và tài nguyên

Các chỉ số nên quan sát:

| Metric | Ý nghĩa |
| --- | --- |
| Active/idle connections | Số connection đang dùng và nhàn rỗi. |
| Pending acquire | Số request đang chờ connection. |
| Acquire latency | Thời gian lấy connection từ pool. |
| Connect latency | Thời gian thiết lập connection. |
| Response latency | Thời gian nhận response. |
| Timeout count | Số request vượt deadline/timeout ở từng tầng. |
| Connection errors | DNS, connect, TLS hoặc socket error. |
| Retry count | Số lần client thử lại request. |
| Response status | Phân bố 2xx, 4xx và 5xx theo destination. |

Nếu bật wire logging, request/response body có thể chứa token, thông tin cá nhân hoặc payload nghiệp vụ. Chỉ bật có kiểm soát, che dữ liệu nhạy cảm và tắt sau khi chẩn đoán.

Lifecycle theo connector:

- Reactor Netty custom `ConnectionProvider` cần được dispose khi ứng dụng shutdown.
- JDK HttpClient được JDK quản lý; executor tùy chỉnh do ứng dụng cung cấp cần lifecycle riêng.
- Jetty HttpClient cần start trước khi dùng và stop khi context đóng.
- Apache CloseableHttpAsyncClient cần start và close; connection manager đi cùng client cũng phải được giải phóng.

Không đóng client sau từng request vì client/pool được chia sẻ. Ngược lại, không để custom thread pool hoặc connection manager tồn tại sau khi ứng dụng shutdown.

## 12. Chương trình Spring Boot 3.3.5 với Reactor Netty

Ví dụ dùng **Java 17+**, **Maven**, **Spring Boot 3.3.5** và WebFlux. Ứng dụng tạo WebClient singleton tới catalog service, dùng connection pool có giới hạn và timeout riêng. Test dùng MockWebServer để kiểm tra request/response mà không cần gọi dịch vụ Internet.

Cấu trúc:

```text
webclient-connector-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/demo/
│   ├── ConnectorDemoApplication.java
│   ├── CatalogProperties.java
│   ├── CatalogWebClientConfig.java
│   ├── CatalogItem.java
│   └── CatalogClient.java
└── src/test/java/demo/CatalogClientTest.java
```

### 12.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
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
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

### 12.2. application.properties

```properties
catalog.base-url=https://catalog.example.com
```

Trong môi trường triển khai, thay URL bằng cấu hình service discovery hoặc môi trường tương ứng. Không hard-code credential trong file này.

### 12.3. ConnectorDemoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConnectorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConnectorDemoApplication.class, args);
    }
}
```

### 12.4. CatalogProperties.java

```java
package demo;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(URI baseUrl) {}
```

### 12.5. CatalogWebClientConfig.java

```java
package demo;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import io.netty.channel.ChannelOption;

@Configuration
public class CatalogWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
                .maxConnections(100)
                .pendingAcquireMaxCount(500)
                .pendingAcquireTimeout(Duration.ofSeconds(10))
                .maxIdleTime(Duration.ofSeconds(30))
                .maxLifeTime(Duration.ofMinutes(5))
                .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            CatalogProperties properties) {

        HttpClient httpClient = HttpClient
                .create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(10));

        return builder.clone()
                .baseUrl(properties.baseUrl().toString())
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Bean pool có tên riêng để metric và log dễ phân biệt. `destroyMethod = "dispose"` giải phóng custom provider khi Spring context đóng. Builder được clone để cấu hình riêng cho catalog client mà vẫn giữ customizer của Boot.

### 12.6. CatalogItem.java

```java
package demo;

public record CatalogItem(long id, String name) {}
```

### 12.7. CatalogClient.java

```java
package demo;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class CatalogClient {
    private final WebClient client;

    public CatalogClient(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    public Mono<CatalogItem> findById(long id) {
        return client.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(CatalogItem.class)
                .timeout(Duration.ofSeconds(12));
    }
}
```

`retrieve()` mặc định chuyển status 4xx/5xx thành `WebClientResponseException`. `timeout` đặt deadline cho publisher từ lúc subscribe đến khi body được decode. Nó bổ sung cho connect/response timeout của Reactor Netty, không thay thế chúng.

Nếu muốn custom error mapping, có thể thêm `onStatus`:

```java
.retrieve()
.onStatus(status -> status.value() == 429,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("Rate limited")
                .map(RateLimitedException::new))
.bodyToMono(CatalogItem.class)
```

`RateLimitedException` là exception do ứng dụng định nghĩa. Chỉ đọc response body một lần và chuyển nó thành thông tin lỗi đã kiểm soát.

### 12.8. CatalogClientTest.java

```java
package demo;

import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

    @Test
    void sendsRequestAndDecodesJsonResponse() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader(
                            "Content-Type",
                            MediaType.APPLICATION_JSON_VALUE)
                    .setBody("""
                            {"id":7,"name":"Keyboard"}
                            """));

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .clientConnector(new ReactorClientHttpConnector(
                            HttpClient.create()))
                    .build();

            CatalogClient client = new CatalogClient(webClient);

            StepVerifier.create(client.findById(7))
                    .expectNext(new CatalogItem(7, "Keyboard"))
                    .verifyComplete();

            RecordedRequest request =
                    server.takeRequest(1, TimeUnit.SECONDS);

            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/items/7");
            assertThat(request.getHeader("Accept"))
                    .contains(MediaType.APPLICATION_JSON_VALUE);
        }
    }

    @Test
    void mapsServerErrorToWebClientResponseException() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(503)
                    .setBody("temporarily unavailable"));

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .clientConnector(new ReactorClientHttpConnector(
                            HttpClient.create()))
                    .build();

            CatalogClient client = new CatalogClient(webClient);

            StepVerifier.create(client.findById(8))
                    .expectErrorMatches(error ->
                            error instanceof
                                    org.springframework.web.reactive.function.client
                                            .WebClientResponseException exception
                                    && exception.getStatusCode().value() == 503)
                    .verify();
        }
    }
}
```

MockWebServer nhận request như một HTTP server cục bộ và trả response được định trước. Test dùng Reactor Netty connector giống cấu hình ứng dụng, nhưng base URL trỏ tới server test. `StepVerifier` xác nhận kết quả decode và lỗi HTTP 503.

Chạy test:

```bash
mvn test
```

Test đầu xác nhận method GET, path `/items/7`, Accept header và JSON body được decode thành record. Test thứ hai xác nhận response 503 trở thành `WebClientResponseException`. Test không gọi Internet và không phụ thuộc catalog service thật.

## 13. Lỗi thường gặp và cách xử lý

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ connector WebClient là server connector | Thay outbound client nhưng kỳ vọng inbound server đổi theo | Cấu hình client connector và server runtime độc lập. |
| Để connector ngầm chọn trong khi yêu cầu vận hành cần ổn định | Thay classpath có thể đổi implementation | Cấu hình `clientConnector` tường minh. |
| Tạo WebClient mới cho mỗi request | Tăng object và có thể tạo pool/thread resource lặp lại | Tạo bean/client singleton theo destination. |
| Tạo pool không giới hạn hoặc quá lớn | Remote service có thể bị quá tải | Đặt max connections, pending acquire và timeout. |
| Chỉ đặt overall timeout | Request có thể chờ pool/connect quá lâu trước khi thất bại | Đặt timeout riêng cho acquire/connect/response và deadline tổng thể. |
| Nhầm response timeout với deadline tổng thể | Stream có thể tiếp tục lâu khi vẫn có dữ liệu | Chọn idle/read timeout và overall deadline đúng mục đích. |
| Dùng `Mono.timeout` thay toàn bộ socket timeout | Không kiểm soát được từng tầng transport | Kết hợp timeout publisher với cấu hình engine. |
| Dùng JDK connector nhưng kỳ vọng API pool tuning của Netty | Không có tùy chọn tương đương trong JDK public API | Chấp nhận pool do JDK quản lý hoặc chọn engine có pool control cần thiết. |
| Dùng Apache HttpClient 4 với connector HttpComponents 5 | Không tương thích API | Dùng Apache HttpComponents 5 Async Client đúng phiên bản. |
| Trộn nhiều major version Jetty | Lỗi binary hoặc API không tương thích | Đồng bộ Jetty Reactive HttpClient và Jetty core theo line Spring hỗ trợ. |
| Quên start Jetty/Apache async client | Request có thể thất bại vì client chưa chạy | Quản lý init/start và destroy/stop/close bằng Spring bean. |
| Không dispose custom Reactor ConnectionProvider | Giữ connection/tài nguyên sau shutdown | Để Spring gọi dispose khi application context đóng. |
| Dispose global Reactor resources khi app còn chạy | Các client khác có thể bị ảnh hưởng | Chỉ dispose global resources ở lifecycle shutdown đã điều phối. |
| Tắt TLS certificate verification | Kết nối mất xác thực server | Cấu hình truststore/CA đúng, giữ hostname verification. |
| Log wiretap chứa toàn bộ payload | Có thể lộ token hoặc dữ liệu cá nhân | Chỉ bật debug có kiểm soát và che dữ liệu nhạy cảm. |
| Retry mọi POST hoặc upload | Tạo side effect trùng khi server đã xử lý request | Retry theo idempotency contract, giới hạn lần và backoff. |
| Cấu hình HTTP/2 mà không kiểm tra ALPN/server | Client vẫn có thể thương lượng HTTP/1.1 hoặc thất bại | Xác minh protocol được thương lượng và khả năng server. |
| Dùng một pool cho mọi dependency có SLA khác nhau | Workload chậm có thể chiếm connection của workload quan trọng | Tách WebClient/pool theo dependency hoặc nhóm policy. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `ClientHttpConnector` có vai trò gì?  
**Đáp án:** Nó nối WebClient với HTTP client engine thực tế để thực hiện request outbound, quản lý transport và chuyển response về abstraction của Spring.

**Câu 2.** WebClient connector có phải connector của WebFlux server không?  
**Đáp án:** Không. Connector WebClient gửi request ra ngoài; server runtime nhận request đi vào. Hai cấu hình độc lập.

**Câu 3.** Khi nào nên chọn Reactor Netty?  
**Đáp án:** Khi cần reactive native, pool và transport tuning chi tiết, đồng thời ứng dụng đã dùng Reactor/WebFlux.

**Câu 4.** JDK connector có lợi thế gì?  
**Đáp án:** Dùng java.net.http.HttpClient có sẵn từ JDK 11+, giảm dependency và hỗ trợ HTTP/2; đổi lại ít API pool tuning công khai hơn.

**Câu 5.** Jetty và Apache client cần lưu ý lifecycle nào?  
**Đáp án:** Jetty HttpClient cần start/stop; Apache CloseableHttpAsyncClient cần start/close. Quản lý qua Spring bean lifecycle.

**Câu 6.** Pool acquire timeout khác connect timeout thế nào?  
**Đáp án:** Acquire timeout là thời gian chờ lấy connection rảnh trong pool; connect timeout là thời gian thiết lập connection mới tới server.

**Câu 7.** Reactor Netty responseTimeout có phải deadline tổng thể không?  
**Đáp án:** Không. Nó kiểm soát khoảng thời gian đọc mạng theo semantics của Reactor Netty; deadline tổng thể có thể đặt thêm bằng Mono/Flux timeout.

**Câu 8.** Vì sao không nên gọi WebClient.create() tùy tiện trong ứng dụng Boot?  
**Đáp án:** Client tạo thủ công có thể bỏ qua builder customizer, codec, filter và observation mà Boot đã cấu hình.

**Câu 9.** Có nên tắt xác minh TLS để sửa lỗi certificate không?  
**Đáp án:** Không. Hãy cài đúng CA/truststore và xác minh hostname; tắt validation làm mất xác thực server.

**Câu 10.** Có thể retry mọi request khi timeout không?  
**Đáp án:** Không. Server có thể đã xử lý request trước khi client timeout. Chỉ retry khi operation idempotent hoặc có idempotency key và chính sách backoff phù hợp.

## Ghi nhớ

- `ClientHttpConnector` là ranh giới transport outbound của WebClient; nó độc lập với server runtime của WebFlux.
- Reactor Netty phù hợp khi cần reactive native và pool/transport tuning sâu; JDK giảm dependency; Jetty và Apache hữu ích khi hệ thống đã chuẩn hóa các engine đó.
- Cấu hình connector tường minh qua `WebClient.Builder.clientConnector` khi muốn transport ổn định theo môi trường.
- Phân biệt pool acquire, connect, response/read và overall deadline. Một timeout không thay thế các timeout ở tầng khác.
- Tạo WebClient và pool dùng lại; quản lý lifecycle của ConnectionProvider, Jetty HttpClient và Apache async client đúng lúc.
- Giữ TLS verification, cấu hình proxy/HTTP2 có kiểm chứng, theo dõi pool/latency/error và chỉ retry khi semantics cho phép.

### Tài liệu tham khảo

1. [Spring Framework – WebClient Builder](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient.Builder, ClientHttpConnector và cấu hình client.
2. [Spring Framework – ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html): tích hợp Reactor Netty.
3. [Spring Framework – JdkClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/JdkClientHttpConnector.html): tích hợp JDK HttpClient.
4. [Spring Framework – JettyClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/JettyClientHttpConnector.html): tích hợp Jetty Reactive HttpClient.
5. [Spring Framework – HttpComponentsClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/HttpComponentsClientHttpConnector.html): tích hợp Apache HttpComponents async client.
6. [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): pool, timeout, TLS, proxy và HTTP client configuration.
7. [JDK HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/2, connect timeout, proxy, SSL và redirect.
8. [Jetty HttpClient Documentation](https://jetty.org/docs/jetty/12/programming-guide/client/http.html): cấu hình và lifecycle Jetty client.
9. [Apache HttpComponents 5 – Async Client](https://hc.apache.org/httpcomponents-client-5.3.x/asyncclient5/): async client và pooling connection manager.
