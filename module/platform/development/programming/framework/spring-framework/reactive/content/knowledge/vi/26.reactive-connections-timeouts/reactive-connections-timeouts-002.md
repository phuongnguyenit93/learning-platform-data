# Cấu hình HttpClient và tài nguyên dùng chung

**Ngữ cảnh:** Spring Framework Reactive → **Kết nối và thời hạn**.

`WebClient` là API HTTP client ở tầng Spring; `ClientHttpConnector` kết nối API đó với transport cụ thể. Với Reactor Netty, connector dùng `reactor.netty.http.client.HttpClient` để quản lý socket, TLS, event loop, connection pool, timeout và các thao tác I/O. Khi cần tinh chỉnh transport, hãy cấu hình một `HttpClient` rồi gắn nó vào `ReactorClientHttpConnector`.

Chủ đề này có hai phần gắn liền với nhau:

- **Cấu hình kết nối:** địa chỉ, connection pool, timeout, TLS, proxy, redirect, HTTP/2 và quan sát hoạt động.
- **Tài nguyên dùng chung:** event-loop threads, connection provider/pool, DNS resolver và vòng đời khởi động/tắt của chúng.

Nguyên tắc quan trọng: **tài nguyên transport có tuổi thọ dài hơn một request**. Hãy chia sẻ chúng giữa các request và client cùng chính sách. Tạo pool/event loop mới cho từng request sẽ làm tăng thread, socket, bộ nhớ và chi phí kết nối.

## 1. WebClient, connector và HttpClient

Ba lớp có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `WebClient` | API cấp ứng dụng để tạo HTTP request, encode/decode body và compose publisher | `retrieve().bodyToMono(Book.class)` |
| `ClientHttpConnector` | Cầu nối giữa WebClient và HTTP runtime | `ReactorClientHttpConnector` |
| Reactor Netty `HttpClient` | Cấu hình transport: pool, event loop, TLS, proxy, timeout | `HttpClient.create()` |

Luồng xử lý:

```text
Application service
       |
       v
WebClient request specification
       |
       v
WebClient ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
ReactorClientHttpConnector
       |
       v
Reactor Netty HttpClient
       |
       +-- ConnectionProvider / pool
       +-- LoopResources / event loops
       +-- DNS resolver
       +-- TCP / TLS / HTTP
       |
       v
Remote service
```

`WebClient` tập trung vào contract HTTP và reactive body. `HttpClient` tập trung vào network runtime. Ví dụ, `defaultHeader` thuộc cấu hình WebClient; `CONNECT_TIMEOUT_MILLIS` thuộc cấu hình Netty transport.

Không phải WebClient nào cũng dùng Reactor Netty. Spring có connector cho JDK HttpClient, Jetty và các implementation khác. Các API trong bài này áp dụng khi ứng dụng dùng Reactor Netty.

## 2. Tạo HttpClient và gắn vào WebClient

Cấu hình tối thiểu:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

WebClient webClient = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
```

`HttpClient.create()` tạo client Reactor Netty với tài nguyên mặc định. `responseTimeout` đặt giới hạn đọc response ở tầng transport. `ReactorClientHttpConnector` làm cho WebClient sử dụng HttpClient đó.

Trong Spring Boot, thường inject builder đã auto-configure:

```java
@Configuration
class PartnerClientConfiguration {

    @Bean
    WebClient partnerClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(Duration.ofSeconds(5));

        return builder
                .baseUrl("https://partner.example.com")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

Ví dụ cần các import và cấu hình component scan phù hợp. Builder do Boot cung cấp có thể mang theo codec, observation và customizer của ứng dụng. Khi tự tạo một builder hoàn toàn mới, đừng mặc định rằng nó có mọi tùy biến của Boot.

`HttpClient` được thiết kế theo kiểu fluent và các thao tác cấu hình trả về một instance đã cấu hình. Hãy cấu hình ở startup rồi chia sẻ instance; không tạo lại client trong mỗi method service.

## 3. Tài nguyên transport dùng chung là gì?

Một HTTP client không chỉ là một object Java nhỏ. Reactor Netty cần các tài nguyên nền:

- **Event-loop group:** nhóm thread xử lý I/O bất đồng bộ, đăng ký socket và callback network.
- **ConnectionProvider:** quản lý pool kết nối, việc acquire/release và hàng đợi request đang chờ connection.
- **DNS resolver:** phân giải hostname thành địa chỉ IP.
- **TLS/native resources:** thư viện native hoặc SSL context khi transport/security provider sử dụng.
- **Timers và scheduler nội bộ:** phục vụ timeout, eviction và hoạt động nền.

Mô hình:

```text
JVM / ApplicationContext
        |
        +------------------------------+
        |                              |
        v                              v
 Shared LoopResources           Shared ConnectionProvider
        |                              |
        +---------------+--------------+
                        |
             +----------+----------+
             |          |          |
             v          v          v
          Client A   Client B   WebFlux server
             |          |          |
             v          v          v
          requests   requests   incoming requests
```

Reactor Netty mặc định sử dụng global resources trong `HttpResources`. Event loop được chia sẻ giữa client và server Reactor Netty trong cùng JVM; connection pool được quản lý theo remote origin. Đây là mô hình được khuyến nghị cho phần lớn ứng dụng vì event loop cố định và chia sẻ có chi phí thấp hơn việc tạo nhiều nhóm riêng.

**Chia sẻ event loop không có nghĩa mọi client dùng chung một pool connection cho mọi host.** Connection pool được tổ chức theo remote host/port và chính sách provider. Các client có thể dùng chung provider nhưng mỗi origin có pool riêng.

## 4. Global resources và Spring Boot

Khi dùng Reactor Netty mặc định, `HttpClient.create()` tham gia global resources. Các tài nguyên này thường tồn tại đến khi JVM kết thúc.

Spring Framework cho phép khai báo `ReactorResourceFactory` để gắn vòng đời global Reactor Netty resources với Spring `ApplicationContext`:

```java
@Configuration
class ReactorResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        return new ReactorResourceFactory();
    }
}
```

Mặc định `ReactorResourceFactory` dùng global resources. Khi ApplicationContext đóng, factory quản lý việc dừng tài nguyên theo lifecycle của Spring. Điều này hữu ích với ứng dụng có thể start/stop context nhiều lần trong cùng JVM, ví dụ container hoặc môi trường kiểm thử.

Spring Boot cũng có cơ chế chia sẻ tài nguyên server/client. Khi server dùng Reactor Netty và client dùng cùng transport, client được tạo từ `WebClient.Builder` auto-configured của Boot có thể chia sẻ tài nguyên với server. Nếu cung cấp `ReactorResourceFactory` bean tùy chỉnh, cấu hình đó được áp dụng cho cả server và client theo cơ chế auto-configuration.

Không tự gọi `HttpResources.disposeLoopsAndConnections()` từ một service hoặc khi một WebClient bị hủy. Lệnh này dừng global resources mà các client/server khác có thể vẫn đang sử dụng.

## 5. Khi nào cần resource riêng?

Global resources là lựa chọn mặc định hợp lý. Chỉ tách tài nguyên khi có lý do vận hành cụ thể:

- Một upstream có lưu lượng lớn cần pool độc lập để không chiếm hết connection của các upstream khác.
- Client có lifecycle khác ứng dụng, ví dụ module được tạo và dừng động.
- Ứng dụng chạy nhiều context độc lập trong cùng JVM và cần cô lập tài nguyên.
- Một transport cần cấu hình event loop hoặc pool riêng vì đặc tính tải.
- Một client dùng proxy/TLS/network path đặc biệt cần quota và quan sát riêng.

Mỗi resource group riêng làm tăng số thread, pool, socket, timer và độ phức tạp shutdown. Không tạo một event-loop group riêng cho từng bean WebClient nếu không có yêu cầu đo đạc chứng minh điều đó cần thiết.

Có hai lựa chọn:

1. Dùng global resources và cấu hình client/pool phù hợp.
2. Dùng `ReactorResourceFactory` với `setUseGlobalResources(false)`, sau đó đảm bảo mọi client/server thuộc nhóm đó sử dụng cùng factory.

## 6. ConnectionProvider và connection pool

`HttpClient.create()` mặc định dùng connection pool dùng chung. Sau khi request hoàn tất, một connection còn sử dụng được có thể được trả lại pool và tái sử dụng cho request sau tới cùng origin.

Tạo provider riêng:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("partner-pool")
                .maxConnections(80)
                .pendingAcquireMaxCount(160)
                .pendingAcquireTimeout(Duration.ofSeconds(5))
                .maxIdleTime(Duration.ofSeconds(30))
                .maxLifeTime(Duration.ofMinutes(5))
                .evictInBackground(Duration.ofSeconds(60))
                .build();

HttpClient httpClient = HttpClient.create(provider);
```

Các giá trị là ví dụ để minh họa. Cần chọn dựa trên latency, concurrency, upstream quota, số origin và thời gian xử lý thực tế. Default của Reactor Netty có thể thay đổi theo phiên bản; hãy xem đúng version được Spring Boot BOM quản lý.

### 6.1. Các giới hạn pool quan trọng

| Thuộc tính | Ý nghĩa | Câu hỏi khi cấu hình |
|---|---|---|
| `maxConnections` | Số connection tối đa trong mỗi pool | Upstream chịu được bao nhiêu kết nối đồng thời? |
| `pendingAcquireMaxCount` | Số yêu cầu tối đa được xếp hàng chờ connection | Backlog tối đa trước khi từ chối là bao nhiêu? |
| `pendingAcquireTimeout` | Thời gian tối đa chờ acquire connection | Bao lâu thì request phải thất bại khi pool bận? |
| `maxIdleTime` | Tuổi thọ idle tối đa trước khi connection đủ điều kiện bị loại | Upstream/proxy đóng connection idle sau bao lâu? |
| `maxLifeTime` | Tuổi thọ tổng tối đa của connection | Có cần xoay vòng connection định kỳ? |
| `evictInBackground` | Chu kỳ kiểm tra/evict connection trong nền | Có cần dọn connection hết hạn khi pool ít request? |

Pool giới hạn số socket đồng thời. Khi pool đầy, request mới có thể nằm trong hàng đợi pending. Nếu hàng đợi đầy hoặc chờ quá lâu, acquire thất bại thay vì giữ lượng request không giới hạn.

Không tăng `maxConnections` chỉ để loại bỏ lỗi timeout. Nếu upstream đã quá tải, mở thêm socket có thể làm tình hình nặng hơn. Hãy quan sát active, idle, pending, acquire time và latency upstream trước khi điều chỉnh.

### 6.2. maxIdleTime và maxLifeTime

`maxIdleTime` giới hạn thời gian connection nằm yên trong pool. Khi đặt giá trị này, nên chọn nhỏ hơn hoặc bằng idle timeout của server/proxy đích để giảm khả năng lấy lại một connection mà phía kia đã đóng.

`maxLifeTime` giới hạn tổng tuổi thọ connection, kể cả khi connection được sử dụng thường xuyên. Nó giúp xoay vòng kết nối và tránh giữ một connection quá lâu trong các môi trường có load balancer hoặc DNS/service discovery thay đổi.

Hai thuộc tính khác nhau: connection có thể còn mới nhưng đã idle quá lâu, hoặc vẫn được dùng liên tục nhưng đã sống quá tuổi thọ tối đa.

### 6.3. FIFO, LIFO và eviction

Pool có thể chọn connection idle theo chiến lược:

- **FIFO:** lấy connection idle lâu nhất (least recently used).
- **LIFO:** lấy connection vừa được sử dụng gần đây nhất (most recently used).

LIFO có thể để connection cũ nằm lâu hơn trong pool; eviction giúp loại các connection đã vượt tiêu chí idle/lifetime. Hãy xem đặc tính server và load balancer trước khi chọn chiến lược.

`evictInBackground` bật kiểm tra định kỳ. Khi tắt, điều kiện hết hạn vẫn có thể được đánh giá trong các lần acquire/release; background eviction hữu ích khi muốn dọn pool ngay cả lúc ít request.

### 6.4. HTTP/2 không giống HTTP/1.1 pool

HTTP/2 hỗ trợ multiplex nhiều stream trên một connection. Do đó, số connection không đồng nghĩa số request đồng thời như HTTP/1.1. Reactor Netty có allocation strategy và pool behavior riêng cho HTTP/2.

Nếu bật HTTP/2, hãy quan sát cả connection và active/pending stream. Không bê nguyên con số max connection của HTTP/1.1 sang HTTP/2 rồi coi đó là giới hạn concurrency chính xác.

## 7. Các loại timeout phải tách biệt

Một request có thể chờ ở nhiều giai đoạn. Dùng một con số timeout cho tất cả thường làm khó xác định nguyên nhân:

```text
Request
  |
  +--> DNS resolution
  |
  +--> Acquire connection from pool
  |
  +--> TCP connect
  |
  +--> TLS handshake
  |
  +--> Send request
  |
  +--> Wait/read response
  |
  +--> Decode body / finish application workflow
```

| Timeout | Bảo vệ giai đoạn nào? | Ví dụ lỗi |
|---|---|---|
| DNS query timeout | Phân giải hostname | Resolver không phản hồi |
| Pending acquire timeout | Chờ connection trong pool | Pool bão hòa |
| Connect timeout | Thiết lập TCP connection | Remote host không nhận kết nối |
| TLS handshake timeout | Thương lượng TLS | Handshake bị treo |
| Proxy connect timeout | Thiết lập tunnel qua proxy | Proxy không phản hồi |
| Response timeout | Khoảng chờ dữ liệu response theo semantics transport | Upstream im lặng |
| Whole-operation timeout | Toàn bộ publisher của nghiệp vụ | Request + decode + xử lý vượt SLA |

### 7.1. Pending acquire timeout

Đặt trên `ConnectionProvider`:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("orders")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(4))
                .build();
```

Đây là thời gian chờ connection được trả lại pool. Nó không phải thời gian chờ server trả response sau khi đã có connection.

### 7.2. TCP connect timeout

Dùng Netty `ChannelOption.CONNECT_TIMEOUT_MILLIS`:

```java
HttpClient httpClient = HttpClient.create()
        .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                3_000);
```

Timeout này áp dụng cho việc thiết lập connection. Nó không bao gồm toàn bộ thời gian xử lý của server sau khi connection đã mở.

### 7.3. TLS handshake timeout

Có thể cấu hình qua `secure`:

```java
HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(10)));
```

TLS handshake có timeout riêng. Nếu upstream ở xa hoặc handshake có đặc tính đặc biệt, chọn giá trị theo network và SLA. Không tắt xác minh certificate để chữa lỗi handshake; hãy sửa trust store, hostname hoặc certificate chain.

### 7.4. Response timeout

`responseTimeout` đặt giới hạn đọc response ở tầng Reactor Netty:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));
```

Có thể đặt mặc định cho mọi request của client hoặc ghi đè cho một request cần thời gian khác. Đây không phải timeout tổng của mọi xử lý ứng dụng; nó có semantics riêng ở tầng response I/O.

Với stream liên tục, hãy hiểu timeout response có thể áp dụng cho khoảng im lặng giữa các lần đọc. Một stream có heartbeat đều đặn có thể tiếp tục lâu hơn tổng thời gian của một request thông thường.

### 7.5. Timeout toàn bộ operation

Dùng Reactor `timeout` khi cần giới hạn toàn bộ publisher từ đầu tới cuối:

```java
Mono<Order> order = webClient.get()
        .uri("/orders/{id}", id)
        .retrieve()
        .bodyToMono(Order.class)
        .timeout(Duration.ofSeconds(8));
```

Timeout operator áp dụng cho toàn bộ chuỗi publisher đang được compose. Khi quá hạn, nó hủy subscription nguồn và phát lỗi timeout. Nếu cần phân biệt rõ pool/connect/read timeout, hãy cấu hình timeout cụ thể của transport bên cạnh deadline nghiệp vụ.

Không cộng máy móc mọi timeout thành SLA nếu chúng không nằm nối tiếp trong mọi đường thực thi. Thiết kế một deadline tổng và phân bổ ngân sách cho từng giai đoạn.

## 8. ReadTimeoutHandler và WriteTimeoutHandler

Có thể thêm handler Netty khi cần timeout ở mức read/write operation:

```java
HttpClient httpClient = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(
                        new ReadTimeoutHandler(10))
                .addHandlerLast(
                        new WriteTimeoutHandler(10)));
```

Các handler này giám sát hoạt động I/O ở channel. Chúng không đồng nghĩa với `responseTimeout` hoặc timeout tổng nghiệp vụ. Một stream hợp lệ nhưng tạm thời không phát dữ liệu có thể bị read timeout nếu policy không phù hợp.

Không gắn handler timeout quá ngắn cho mọi client rồi ngạc nhiên khi stream/SSE hoặc upload lớn bị ngắt. Hãy chọn theo pattern I/O và có thể dùng cấu hình riêng cho từng client.

## 9. TLS, certificate và hostname verification

`HttpClient.secure` bật TLS cho HTTPS hoặc tùy biến SSL context. Ví dụ:

```java
HttpClient httpClient = HttpClient.create()
        .secure(ssl -> ssl
                .handshakeTimeout(Duration.ofSeconds(10)));
```

Trong production:

- Giữ certificate chain validation và hostname verification.
- Dùng trust store đúng khi upstream dùng CA nội bộ.
- Cấu hình client certificate/key store nếu upstream yêu cầu mutual TLS.
- Xoay vòng certificate và secret theo lifecycle được quản lý.
- Theo dõi thời hạn certificate trước khi hết hạn.
- Không ghi private key, token hoặc TLS secret vào log.

Không dùng trust manager chấp nhận mọi certificate để bỏ qua lỗi SSL. Cách đó biến lỗi cấu hình thành lỗ hổng MITM.

Nếu có nhiều upstream với trust policy khác nhau, tạo connector/client riêng cho từng trust boundary. Không gắn một trust policy quá rộng vào client dùng cho mọi host.

## 10. Proxy, redirect và compression

### 10.1. Proxy

Reactor Netty hỗ trợ HTTP proxy. Ví dụ:

```java
HttpClient httpClient = HttpClient.create()
        .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal")
                .port(8080)
                .connectTimeoutMillis(5_000)
                .nonProxyHosts("localhost|127\\\\.0\\\\.0\\\\.1"));
```

Đây là ví dụ cấu hình proxy; cú pháp biểu thức non-proxy host phụ thuộc API và phiên bản Netty. Bảo vệ credential proxy, không log mật khẩu, và kiểm tra chính sách proxy cho HTTPS CONNECT.

Proxy connect timeout khác TCP connect timeout tới origin. Khi dùng proxy, đường kết nối có thêm một hop và có thể phát sinh thêm DNS, TLS hoặc timeout.

### 10.2. Redirect

Có thể bật redirect:

```java
HttpClient httpClient = HttpClient.create()
        .followRedirect(true);
```

Reactor Netty có thể theo redirect HTTP tiêu chuẩn; cũng có predicate tùy chỉnh cho policy cụ thể. Redirect có thể thay đổi host, path hoặc scheme. Kiểm tra cách credential/header nhạy cảm được xử lý khi redirect sang origin khác; không gửi Authorization/cookie sang host không tin cậy.

### 10.3. Compression

```java
HttpClient httpClient = HttpClient.create()
        .compress(true);
```

Compression có thể giảm byte truyền trên mạng nhưng tiêu tốn CPU để nén/giải nén và ảnh hưởng kích thước sau giải nén. Cân nhắc payload, CPU, latency và upstream support. Không nén dữ liệu đã nén hoặc payload nhỏ nếu lợi ích không đáng kể.

## 11. Event loop và LoopResources

Reactor Netty dùng event loop để thực hiện network I/O non-blocking. Một nhóm worker thread được chia sẻ giữa các client/server trong JVM theo global resources mặc định.

Một event-loop thread có thể phục vụ nhiều connection. Vì vậy:

- Không gọi `block()` trong event loop.
- Không thực hiện file I/O hoặc JDBC blocking trực tiếp trong callback.
- Không chạy xử lý CPU nặng lâu trên event loop.
- Dùng driver reactive hoặc chuyển legacy blocking call sang scheduler phù hợp.
- Đừng tăng số event-loop thread chỉ để bù cho code blocking.

Nếu cần event loop riêng, có thể tạo `LoopResources`:

```java
LoopResources loops =
        LoopResources.create("partner-http");

HttpClient httpClient = HttpClient.create()
        .runOn(loops);
```

`LoopResources` cũng là resource có lifecycle. Nếu tự tạo, phải dispose khi ứng dụng kết thúc. Không gọi dispose trong mỗi request hoặc khi chỉ một WebClient ngừng dùng nó nếu client khác còn chia sẻ cùng loops.

Số thread event loop không nên được chọn tùy tiện. Đo CPU, số connection, độ trễ callback và mức blocking trước khi thay đổi.

## 12. ReactorResourceFactory với tài nguyên độc lập

Khi không muốn tham gia global resources, Spring cung cấp `ReactorResourceFactory` để quản lý pool và event loop theo lifecycle của ApplicationContext.

Ví dụ cấu hình custom resource factory:

```java
@Configuration
class IsolatedReactorResources {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory =
                new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(() ->
                ConnectionProvider.builder("partner-isolated")
                        .maxConnections(60)
                        .pendingAcquireMaxCount(120)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(5))
                        .maxIdleTime(Duration.ofSeconds(30))
                        .maxLifeTime(Duration.ofMinutes(5))
                        .evictInBackground(
                                Duration.ofSeconds(60))
                        .build());

        factory.setLoopResourcesSupplier(() ->
                LoopResources.create("partner-isolated"));

        return factory;
    }
}
```

Factory tạo và quản lý các resource độc lập. Supplier chỉ được dùng khi factory không tham gia global resources. Không tự tạo thêm provider hoặc loops ngoài factory nếu mục tiêu là có một lifecycle thống nhất.

Để WebClient sử dụng factory đó:

```java
@Bean
WebClient partnerClient(
        WebClient.Builder builder,
        ReactorResourceFactory reactorResourceFactory) {

    ReactorClientHttpConnector connector =
            new ReactorClientHttpConnector(
                    reactorResourceFactory,
                    httpClient -> httpClient
                            .option(
                                    ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                    3_000)
                            .responseTimeout(
                                    Duration.ofSeconds(5)));

    return builder
            .baseUrl("https://partner.example.com")
            .clientConnector(connector)
            .build();
}
```

Nếu nhiều client phải chia sẻ cùng resource group, hãy inject cùng factory vào từng connector. Nếu server cũng thuộc group này, cấu hình server sử dụng cùng factory. Khi context đóng, factory quản lý việc dừng resource.

Đây là lựa chọn nâng cao. Nếu chỉ cần một vài timeout cho WebClient, global resources mặc định thường đơn giản hơn.

## 13. Connection pool và tài nguyên riêng theo upstream

Có thể có một client cho từng upstream nhưng vẫn dùng chung event loop:

| Upstream | Client | Pool policy | Lý do |
|---|---|---|---|
| Catalog | `catalogClient` | 40 connections, acquire 3s | Nhiều request đọc ngắn |
| Payment | `paymentClient` | 12 connections, acquire 2s | Quota upstream thấp |
| Reporting | `reportClient` | 8 connections, response 30s | Query dài |
| Internal API | `internalClient` | Default shared pool | Cùng latency và quota |

Một cách triển khai là tạo các `ConnectionProvider` riêng nhưng dùng chung `LoopResources` hoặc global event loops. Tuy nhiên, pool riêng làm tăng số socket và pending queue. Chỉ tách khi có quota, SLA hoặc isolation requirement rõ.

Không tạo một pool theo từng tenant nếu số tenant lớn và mỗi pool ít hoạt động; điều đó gây phân mảnh và tăng chi phí. Thay vào đó, dùng pool theo upstream/policy, còn tenant identity nằm trong request header/context.

## 14. HTTP/2, keep-alive và connection health

HTTP/1.1 keep-alive cho phép nhiều request tuần tự tái sử dụng một connection. HTTP/2 cho phép nhiều stream đồng thời trên một connection.

Khi cấu hình:

- Kiểm tra protocol negotiation và ALPN với TLS.
- Quan sát active connection và active stream.
- Dùng pool/allocation strategy phù hợp với HTTP/2.
- Đặt idle timeout phù hợp với server/load balancer.
- Với HTTP/2, có thể cấu hình PING health check để phát hiện connection không phản hồi khi idle timeout được bật.
- Không coi TCP keepalive và HTTP/2 PING là cùng một cơ chế.

TCP keepalive là probe ở tầng TCP, thường có thời gian mặc định dài tùy OS. HTTP/2 PING là frame của giao thức HTTP/2. Cả hai có thể hỗ trợ phát hiện kết nối stale nhưng giải quyết ở tầng khác nhau.

## 15. Warmup và first-request latency

Reactor Netty khởi tạo một số tài nguyên theo nhu cầu. Request đầu tiên có thể chịu thêm chi phí tạo event loop, DNS resolver hoặc load native library.

Có thể warm up client:

```java
HttpClient httpClient = HttpClient.create();

httpClient.warmup().block();
```

Trong ứng dụng thực tế, đặt warmup ở startup hook có lifecycle rõ ràng, không gọi trong mỗi request. Warmup khởi tạo một số tài nguyên nền; DNS resolution và kết nối tới origin vẫn có thể xảy ra khi request đầu tiên thực sự được gửi.

Không warmup bằng cách gọi một API nghiệp vụ có side effect. Nếu muốn kiểm tra readiness của upstream, hãy dùng health check riêng với timeout và policy phù hợp.

## 16. Metrics và quan sát pool

Reactor Netty hỗ trợ metrics cho connection pool và HTTP client. Có thể bật metrics trên provider:

```java
ConnectionProvider provider =
        ConnectionProvider.builder("partner")
                .maxConnections(40)
                .metrics(true)
                .build();
```

Khi tích hợp Micrometer, theo dõi các chỉ số phù hợp như:

- Active connections.
- Idle connections.
- Pending connections.
- Pending acquire time.
- Total connections và pool size.
- Request latency, response status và transport errors.
- Connect timeout, response timeout, pool acquire timeout.
- Số connection bị đóng/evict và số lần retry.

Tên metric và tag cụ thể phụ thuộc phiên bản Reactor Netty và registry. Tránh gắn URL đầy đủ, user ID hoặc query nhạy cảm làm metric tag vì cardinality và dữ liệu cá nhân.

Một pool có nhiều pending request nhưng active connections luôn ở max có thể là dấu hiệu upstream chậm hoặc pool quá nhỏ. Một pool có nhiều active connections nhưng latency thấp có thể chỉ là concurrency bình thường. Luôn kết hợp metrics client với latency/error của upstream và giới hạn quota.

## 17. Shutdown và dispose đúng ownership

Quy tắc shutdown phụ thuộc resource thuộc ai:

| Resource | Cách quản lý |
|---|---|
| Global Reactor Netty resources | Để JVM hoặc Spring-managed `ReactorResourceFactory` quản lý |
| Custom `ConnectionProvider` | Dispose provider khi chủ sở hữu kết thúc |
| Custom `LoopResources` | Dispose loops khi chủ sở hữu kết thúc |
| `ReactorResourceFactory` | Spring lifecycle start/stop quản lý resources |
| WebClient bean dùng shared global resources | Không dispose global pool từ bean/service tùy tiện |

Nếu tự tạo provider:

```java
provider.disposeLater().block();
```

Ví dụ này chỉ phù hợp ở ranh giới shutdown imperative, không gọi trong event loop hoặc request handler. Trong Spring, ưu tiên factory/lifecycle bean để đóng tài nguyên theo thứ tự và chờ shutdown phù hợp.

Gọi `HttpResources.disposeLoopsAndConnections()` sẽ ảnh hưởng tất cả client/server dùng global resources. Đừng gọi nó chỉ vì một client không còn cần nữa.

Với pool riêng, cần ngừng nhận request mới, cho request đang chạy hoàn tất trong grace period, rồi dispose. Nếu shutdown quá sớm, request đang dùng pool có thể thất bại.

## 18. Ví dụ Java 17+ chạy được: pool riêng và event loop dùng chung

Ví dụ sau dựng một server Reactor Netty local và một WebClient. Server và client dùng chung một `LoopResources` để minh họa event-loop sharing; outbound client dùng `ConnectionProvider` riêng với giới hạn và timeout. Chương trình gửi hai request rồi dispose đúng các resource do nó sở hữu.

Cấu trúc project:

```text
http-client-resource-demo/
├── pom.xml
└── src/main/java/demo/HttpClientResourceDemo.java
```

### 18.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>http-client-resource-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 18.2. HttpClientResourceDemo.java

```java
package demo;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.client.HttpClient;
import reactor.netty.http.server.HttpServer;
import reactor.netty.resources.ConnectionProvider;
import reactor.netty.resources.LoopResources;

public class HttpClientResourceDemo {

    public static void main(String[] args) {
        LoopResources loops =
                LoopResources.create("lesson-http");

        ConnectionProvider pool =
                ConnectionProvider.builder("lesson-outbound")
                        .maxConnections(8)
                        .pendingAcquireMaxCount(16)
                        .pendingAcquireTimeout(
                                Duration.ofSeconds(3))
                        .maxIdleTime(Duration.ofSeconds(20))
                        .maxLifeTime(Duration.ofMinutes(2))
                        .evictInBackground(
                                Duration.ofSeconds(30))
                        .build();

        DisposableServer server = HttpServer.create()
                .runOn(loops)
                .host("127.0.0.1")
                .port(0)
                .route(routes -> routes.get(
                        "/ping",
                        (request, response) ->
                                response.sendString(Mono.just("pong"))))
                .bindNow();

        HttpClient nettyClient = HttpClient.create(pool)
                .runOn(loops)
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        3_000)
                .responseTimeout(Duration.ofSeconds(3));

        WebClient webClient = WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(nettyClient))
                .build();

        try {
            String baseUrl =
                    "http://127.0.0.1:" + server.port();

            String first = webClient.get()
                    .uri(baseUrl + "/ping")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            String second = webClient.get()
                    .uri(baseUrl + "/ping")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block();

            System.out.println("first=" + first);
            System.out.println("second=" + second);
        }
        finally {
            server.disposeNow();
            pool.disposeLater().block();
            loops.disposeLater().block();
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.HttpClientResourceDemo
```

**Standard output:**

```text
first=pong
second=pong
```

Giải thích:

1. `LoopResources` tạo event-loop group có tên riêng.
2. Server và outbound HttpClient được cấu hình dùng cùng loops trong demo.
3. `ConnectionProvider` tạo pool outbound với giới hạn 8 connection và hàng đợi pending tối đa 16.
4. `HttpClient` dùng provider đó, thêm connect timeout và response timeout.
5. `ReactorClientHttpConnector` gắn HttpClient vào WebClient.
6. Hai request gọi cùng origin; pool có thể tái sử dụng connection nếu connection còn hợp lệ.
7. `finally` dừng server, dispose pool rồi dispose event-loop group mà chương trình sở hữu.
8. `block()` chỉ nằm trong `main` của demo để lấy output đồng bộ; không dùng trong WebFlux handler/service.

Ví dụ này minh họa API và ownership của resource. Ứng dụng Spring Boot production thường ưu tiên global resources hoặc `ReactorResourceFactory` để Spring quản lý lifecycle thay vì tự dispose thủ công trong code nghiệp vụ.

## 19. Kiểm thử cấu hình HttpClient

Kiểm thử cần bao gồm behavior transport và lifecycle, không chỉ kiểm tra bean được tạo:

- Local server trả response bình thường.
- Server chậm hơn response timeout.
- Host/port không thể kết nối để kiểm tra connect timeout.
- Pool nhỏ và nhiều request đồng thời để kiểm tra pending acquire.
- Server đóng connection idle để xác nhận maxIdleTime/eviction.
- TLS certificate hợp lệ, hết hạn hoặc sai hostname.
- Proxy hoạt động và non-proxy host được xử lý đúng.
- Redirect sang cùng host và host khác.
- HTTP/2 multiplexing nếu ứng dụng sử dụng HTTP/2.
- ApplicationContext đóng thì resource factory dừng resources.
- Client khác vẫn hoạt động khi một client không còn được dùng, nếu resource dùng chung.
- Metrics phản ánh active/idle/pending và timeout đúng.

Dùng mock server hoặc test container để điều khiển response delay, close connection và TLS. Test pool saturation cần giới hạn concurrency và timeout có chủ đích; tránh phụ thuộc vào thời gian scheduling không ổn định.

Không chỉ test happy path. Nhiều lỗi production đến từ pool pending queue đầy, stale idle connection, DNS change, TLS rotation hoặc shutdown trong lúc request đang chạy.

## 20. Lỗi thường gặp

1. **Tạo HttpClient/ConnectionProvider cho từng request.** Làm tăng socket, thread và pool; tạo client ở startup rồi reuse.
2. **Tạo nhiều LoopResources không cần thiết.** Event loop nên được chia sẻ theo resource group và lifecycle rõ.
3. **Tăng maxConnections vô hạn.** Có thể làm upstream quá tải và tiêu thụ socket/file descriptor; đặt quota theo năng lực hệ thống.
4. **Để pending queue không giới hạn.** Backlog có thể chiếm memory và làm latency tăng; đặt pendingAcquireMaxCount.
5. **Nhầm pendingAcquireTimeout với connect timeout.** Một timeout chờ pool; timeout kia chờ TCP connect.
6. **Nhầm responseTimeout với timeout toàn operation.** Cấu hình deadline publisher riêng nếu cần SLA tổng.
7. **Chọn maxIdleTime lớn hơn idle timeout của upstream.** Có thể lấy lại connection stale; cân nhắc bằng hoặc nhỏ hơn timeout phía server.
8. **Không cấu hình eviction khi cần dọn pool lúc ít traffic.** Connection hết hạn có thể chỉ được phát hiện khi acquire/release nếu không có background eviction.
9. **Dispose global resources khi một client dừng.** Các client/server khác có thể mất khả năng hoạt động.
10. **Không dispose custom provider/loops.** Có thể giữ thread và socket sau khi module/context đã dừng.
11. **Dispose resource dùng chung quá sớm.** Request đang chạy hoặc client khác sẽ thất bại.
12. **Dùng một pool riêng cho mỗi tenant.** Dễ phân mảnh tài nguyên khi tenant nhiều; tổ chức pool theo upstream/policy.
13. **Coi HTTP/2 maxConnections là max request concurrency.** HTTP/2 multiplex nhiều stream trên connection.
14. **Chặn event loop bằng block hoặc JDBC.** Làm chậm tất cả connection được phục vụ bởi thread đó.
15. **Tắt TLS verification để chữa certificate error.** Tạo lỗ hổng bảo mật; sửa trust chain/hostname.
16. **Không đặt timeout cho TLS handshake hoặc proxy.** Một giai đoạn kết nối có thể treo lâu hơn ngân sách request.
17. **Đặt ReadTimeoutHandler quá ngắn cho SSE.** Stream hợp lệ nhưng im lặng có thể bị ngắt.
18. **Không quan sát pending acquire metrics.** Pool saturation bị nhầm với upstream chậm hoặc DNS lỗi.
19. **Bật wiretap trong production mà không kiểm soát dữ liệu.** Có thể log headers/body nhạy cảm và tăng CPU/I/O.
20. **Warmup bằng một request có side effect.** Startup không nên tạo giao dịch nghiệp vụ ngoài ý muốn.
21. **Tạo connector mới nhưng quên resource ownership.** Xác định factory/provider/loops nào quản lý lifecycle.
22. **Dùng một custom ReactorResourceFactory cho một client nhưng server/client khác vẫn dùng resource group khác.** Muốn chia sẻ custom resource phải cấu hình tất cả thành phần liên quan cùng factory.
23. **Cho rằng disposeLater tự hoàn tất nếu không subscribe.** Đây là publisher; ở shutdown imperative phải chờ hoàn tất hoặc để Spring lifecycle quản lý.
24. **Dùng defaults từ tài liệu Reactor Netty phiên bản khác.** Spring Boot quản lý phiên bản dependency; đọc đúng reference/Javadoc của version thực tế.

## 21. Checklist production

Trước khi triển khai, hãy xác nhận:

- **Transport:** WebClient đang dùng Reactor Netty, Jetty hay JDK connector?
- **Resource mode:** global shared resources hay resource group riêng?
- **Ownership:** ai tạo và ai đóng ConnectionProvider/LoopResources?
- **Sharing:** các client/server nào dùng chung provider và event loop?
- **Pool:** max connections, pending queue, acquire timeout, idle/lifetime eviction đã dựa trên tải và quota?
- **Timeout:** DNS, pool acquire, TCP connect, TLS handshake, proxy, response và whole-operation deadline đã tách?
- **TLS:** trust store, hostname verification, client certificate và rotation đã đúng?
- **Proxy/redirect:** credential và host boundary có an toàn?
- **HTTP protocol:** HTTP/1.1 hay HTTP/2; concurrency được tính theo connection hay stream?
- **Blocking:** event loop không chạy code blocking/CPU nặng?
- **Warmup:** có cần giảm first-request latency và có làm readiness đúng cách?
- **Metrics:** active/idle/pending, acquire latency, connect/response timeout, status và request latency đã quan sát?
- **Shutdown:** request đang chạy có grace period; resource shared không bị dispose từ owner sai?
- **Testing:** pool saturation, timeout, TLS, proxy, stale connection và context shutdown đã được kiểm thử?

**Ghi nhớ:** `HttpClient` quyết định cách Reactor Netty kết nối ra ngoài; `ConnectionProvider` quản lý pool; `LoopResources` quản lý event loop; `ReactorResourceFactory` gắn resource với lifecycle Spring. Dùng global resources cho phần lớn ứng dụng và chia sẻ chúng giữa các client/server tương thích. Chỉ tạo resource riêng khi cần isolation có căn cứ. Đặt giới hạn pool và timeout theo từng giai đoạn, theo dõi pending/active metrics, và đóng resource đúng owner khi ứng dụng dừng.

## Tài liệu tham khảo

- Spring Framework — [WebClient Configuration, Reactor Netty resources and timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Spring Framework — [ReactorResourceFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html).
- Spring Framework — [ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html).
- Spring Boot — [Reactive Web Applications: shared server and client resources](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Project Reactor Netty — [HTTP Client: Connection Pool, Event Loops, TLS and Proxy](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- Project Reactor Netty — [Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration).
