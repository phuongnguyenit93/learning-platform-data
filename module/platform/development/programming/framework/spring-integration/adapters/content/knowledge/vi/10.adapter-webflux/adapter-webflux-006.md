# WebClient và cấu hình connection trong Spring Integration WebFlux

## 1. Vì sao cấu hình WebClient và connection quan trọng?

Trong một luồng tích hợp, ứng dụng có thể nhận đơn hàng qua Kafka, lấy giá vận chuyển qua HTTP, ghi kết quả xuống database rồi phát thông báo JMS/AMQP. Nếu mỗi message tự tạo HTTP connection hoặc không có timeout, ứng dụng sẽ tiêu tốn tài nguyên, tăng độ trễ và dễ bị nghẽn khi API đối tác chậm.

**WebClient** là HTTP client của Spring WebFlux; nó dùng API phản ứng để xây dựng HTTP request và đọc response. **Connection** là tài nguyên mạng do HTTP transport (thường là Reactor Netty) quản lý. Hai khái niệm có trách nhiệm khác nhau:

- `WebClient` cấu hình URL, HTTP method, headers, body, codec, filters và cách nhận response.
- `HttpClient` của Reactor Netty cấu hình TCP, DNS, TLS, response timeout, proxy và các thông số transport.
- `ConnectionProvider` quản lý **connection pool**, bao gồm giới hạn kết nối đang sử dụng, việc chờ lấy kết nối và tái sử dụng connection.
- Spring Integration dùng WebClient trong WebFlux **outbound channel adapter** hoặc **outbound gateway** để chuyển `Message<?>` thành HTTP request. Outbound gateway còn đưa response thành reply message để flow xử lý tiếp.

Bài học nằm trong chương **Adapter WebFlux** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và `MessageChannel`; các tình huống file, SFTP, HTTP, JMS, AMQP, Kafka và database đều có thể cần một bước gọi HTTP như vậy. Cấu hình connection quyết định phần quan trọng của **hợp đồng message, xử lý lỗi và vòng đời kết nối**.

~~~mermaid
flowchart LR
    A["Kafka / JMS / File / Service"] --> B["Message<QuoteRequest>"]
    B --> C["MessageChannel"]
    C --> D["WebFlux outbound gateway"]
    D --> E["WebClient: URI / headers / codecs"]
    E --> F["Reactor Netty HttpClient"]
    F --> G["ConnectionProvider / TCP / TLS"]
    G -->|"HTTP request"| H["API đối tác"]
    H -->|"HTTP response"| G
    G --> F
    F --> E
    E --> D
    D --> I["Reply Message<QuoteResponse>"]
~~~

**Giới hạn cần nhớ:** WebClient hỗ trợ non-blocking I/O, nhưng `QueueChannel`, poller, JDBC blocking, một handler đồng bộ hay broker phía sau có cách điều phối và giới hạn tải riêng. Có WebClient không có nghĩa toàn bộ IntegrationFlow tự trở thành reactive hoặc đã có backpressure xuyên mọi hệ thống.

## 2. Những lớp cấu hình và trách nhiệm của chúng

| Lớp | API / thành phần | Điều cần cấu hình |
|---|---|---|
| Logic tích hợp | `IntegrationFlow`, `MessageChannel`, `WebFlux.outboundGateway` | Hợp đồng request-reply, payload, reply và error flow |
| HTTP client | `WebClient.Builder`, `WebClient` | Base URL, default headers, filters, codecs, client connector |
| HTTP transport | `ReactorClientHttpConnector`, `HttpClient` | Connect/response timeout, protocol, TLS, proxy |
| Pool kết nối | `ConnectionProvider` | `maxConnections`, `pendingAcquireTimeout`, `maxIdleTime`, `maxLifeTime` |
| Resource lifecycle | Reactor Netty resources, `ReactorResourceFactory` | Shared event loops/pool, startup và shutdown |
| Vận hành | Micrometer/Actuator, tracing, logs | Active/idle/pending connections, request latency, timeout |

`WebClient` được thiết kế để **dùng lại** giữa nhiều request. Một khi đã `build()`, cấu hình client là immutable; có thể dùng `mutate()` để tạo một biến thể, nhưng không cần tạo WebClient mới cho mỗi message. WebClient **không đồng nghĩa với một socket**: một instance có thể dùng nhiều connection; nhiều instance có thể chia sẻ transport resources.

## 3. Dependency và cấu hình WebClient mặc định

Với Spring Boot, nên để BOM/dependency management của Boot quản lý các phiên bản Spring Integration, WebFlux và Reactor Netty tương thích:

~~~groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-integration-webflux` cung cấp các WebFlux adapter/gateway. `spring-boot-starter-webflux` thường bao gồm WebClient, reactor-netty và codec JSON. Ứng dụng chỉ dùng **outbound** HTTP không bắt buộc tạo controller WebFlux inbound.

Ví dụ cấu hình cơ bản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PartnerClientConfiguration {

    @Bean
    public WebClient partnerWebClient(WebClient.Builder builder) {
        return builder.build();
    }
}
~~~

`WebClient.Builder` auto-configured của Boot là điểm khởi đầu tốt: có thể sử dụng các customizers và tài nguyên HTTP do Boot quản lý. Reactor Netty mặc định dùng các tài nguyên dùng chung, trong đó có event loops và connection pooling. Chỉ tách thành pool riêng khi có yêu cầu như giới hạn kết nối từng nhóm đối tác, deadline khác nhau hoặc cần cô lập tải. Nếu ứng dụng có đồng thời Spring MVC và WebFlux, kiểm tra loại web application được Boot chọn; sự hiện diện của WebClient không chứng minh server đang chạy WebFlux.

## 4. Connection pool: acquire, reuse, release

Connection pool giảm chi phí TCP/TLS handshake cho những request liên tiếp. Một HTTP exchange có thể:

~~~mermaid
sequenceDiagram
    participant Flow as IntegrationFlow
    participant Client as WebClient
    participant Pool as ConnectionProvider
    participant Server as Partner API
    Flow->>Client: Yêu cầu HTTP
    Client->>Pool: Acquire connection
    alt Có idle connection hợp lệ
        Pool-->>Client: Reuse connection
    else Còn capacity tạo connection
        Pool->>Server: DNS / TCP / TLS
        Server-->>Pool: Connected
        Pool-->>Client: New connection
    else Pool đầy
        Note over Pool: Chờ pending acquire nếu còn chỗ
        Pool-->>Client: Connection hoặc timeout / overflow
    end
    Client->>Server: HTTP request
    Server-->>Client: HTTP response
    Client->>Pool: Release hoặc close connection
    Client-->>Flow: Reply hoặc error
~~~

| Tùy chọn | Ý nghĩa | Gợi ý vận hành |
|---|---|---|
| `maxConnections` | Số connection tối đa trong một pool tới remote endpoint liên quan | Theo độ đồng thời thực tế, SLA và giới hạn đối tác |
| `pendingAcquireMaxCount` | Số lần acquire thêm được xếp hàng chờ | Giới hạn backlog thay vì queue không giới hạn |
| `pendingAcquireTimeout` | Thời gian tối đa chờ lấy connection | Nhỏ hơn deadline tổng của thao tác |
| `maxIdleTime` | Connection idle đủ thời gian sẽ đủ điều kiện đóng | Phù hợp idle timeout của server/proxy |
| `maxLifeTime` | Tuổi thọ connection trước khi đủ điều kiện thay mới | Hạn chế giữ socket quá lâu |
| `evictInBackground` | Chạy dọn các connection đủ điều kiện theo chu kỳ | Giảm idle connection tồn dư |

`maxConnections(30)` **không** có nghĩa tối đa 30 HTTP request/giây. Với HTTP/1.1 keep-alive, connection có thể được trả về pool rồi dùng cho request khác. Với HTTP/2, một connection có thể multiplex nhiều stream, nên không thể suy ra throughput trực tiếp từ số socket. Các giá trị mặc định của pool có thể thay đổi theo phiên bản hoặc hệ thống; hãy xem tài liệu Reactor Netty ứng với phiên bản chạy thật.

Khi pool bão hòa, request có thể **chưa ra khỏi ứng dụng** mà đã phải chờ trong pending acquire queue. Nếu hàng chờ đầy hoặc hết `pendingAcquireTimeout`, lỗi xảy ra ngay ở bước lấy connection, trước TCP handshake và trước khi server nhận request.

## 5. Cấu hình WebClient với ConnectionProvider riêng

Ví dụ dưới đây tạo pool riêng để gọi API đối tác, có giới hạn kết nối và timeout. Các con số chỉ minh họa; production cần chọn từ tải đo được, ngân sách latency và giới hạn bên nhận.

~~~java
package com.example.integration;

import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class PartnerWebClientConfiguration {

    // Spring gọi dispose() khi ApplicationContext đóng.
    @Bean(destroyMethod = "dispose")
    public ConnectionProvider partnerConnectionProvider() {
        return ConnectionProvider.builder("partner-api-pool")
            .maxConnections(30)
            .pendingAcquireMaxCount(60)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(25))
            .maxLifeTime(Duration.ofMinutes(3))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean("partnerWebClient")
    public WebClient partnerWebClient(
            WebClient.Builder builder,
            @Qualifier("partnerConnectionProvider") ConnectionProvider pool) {
        HttpClient transport = HttpClient.create(pool)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
            .responseTimeout(Duration.ofSeconds(5));

        return builder
            .clientConnector(new ReactorClientHttpConnector(transport))
            .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
            .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024))
            .build();
    }
}
~~~

**Đọc cấu hình:**

1. `ConnectionProvider.builder(...)` tạo pool có tên riêng để nhận diện trong logs/metrics.
2. `maxConnections(30)` đặt giới hạn connection; `pendingAcquireMaxCount(60)` giới hạn số yêu cầu chờ lấy connection.
3. `pendingAcquireTimeout(2s)` là thời gian đợi pool cấp connection. Đó **không phải** TCP connect timeout.
4. `maxIdleTime`, `maxLifeTime` và `evictInBackground` quản lý tuổi connection; connection đang thực thi request không tự bị đóng ngay chỉ vì quá một ngưỡng idle.
5. `CONNECT_TIMEOUT_MILLIS` giới hạn TCP handshake; nó không bao gồm toàn bộ thời gian DNS, lấy connection từ pool hay chờ server phản hồi.
6. `responseTimeout(5s)` đặt giới hạn chờ response ở tầng Reactor Netty; không đại diện cho toàn bộ deadline nghiệp vụ gồm retry, queue và downstream.
7. `ReactorClientHttpConnector` nối transport đã cấu hình vào WebClient. Các codec của WebClient tiếp tục quản lý việc đọc/ghi HTTP body.
8. `maxInMemorySize(1 MiB)` giới hạn buffering cho các codecs mặc định, tránh giải mã một body quá lớn vào bộ nhớ mà không có ràng buộc.

Pool tùy chỉnh phải được **dispose lúc dừng ứng dụng**. `destroyMethod = "dispose"` giải quyết vòng đời của pool này, nhưng event loops dùng chung có thể vẫn do Spring Boot/Reactor Netty quản lý riêng.

## 6. Gắn WebClient vào Spring Integration WebFlux outbound gateway

Hãy giả định API đối tác có `POST /api/quote`, nhận `{"orderId":"ORD-1001","weightKg":2}` và trả JSON báo phí. Gateway cần đưa response thành message để bước tiếp theo lưu hoặc xử lý.

~~~java
package com.example.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.webflux.dsl.WebFlux;
import org.springframework.messaging.MessageChannel;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableIntegration
public class PartnerQuoteFlow {
    public record QuoteRequest(String orderId, int weightKg) { }
    public record QuoteResponse(
        String orderId, long shippingFeeVnd, String currency) { }

    @Bean
    public MessageChannel pricingRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteFlow(
            @Qualifier("pricingRequests") MessageChannel requests,
            @Qualifier("partnerWebClient") WebClient webClient,
            @Value("${partner.api.quote-url}") String url) {
        return IntegrationFlow.from(requests)
            .handle(WebFlux.outboundGateway(url, webClient)
                .httpMethod(HttpMethod.POST)
                .expectedResponseType(QuoteResponse.class)
                .mappedRequestHeaders(
                    HttpHeaders.CONTENT_TYPE, "X-Correlation-Id"))
            .channel("pricingResponses")
            .get();
    }

    @ServiceActivator(inputChannel = "pricingResponses")
    public void acceptQuote(QuoteResponse quote) {
        System.out.printf("Quote for %s: %d %s%n",
            quote.orderId(), quote.shippingFeeVnd(), quote.currency());
    }
}
~~~

Khai báo địa chỉ theo môi trường:

~~~yaml
# application.yml của ứng dụng gọi đối tác
partner:
  api:
    quote-url: "http://localhost:9090/api/quote"
~~~

Một service hoặc listener Kafka/JMS có thể inject `@Qualifier("pricingRequests") MessageChannel` rồi gửi:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.messaging.support.MessageBuilder;

boolean dispatched = pricingRequests.send(
    MessageBuilder.withPayload(
        new PartnerQuoteFlow.QuoteRequest("ORD-1001", 2))
        .setHeader(HttpHeaders.CONTENT_TYPE,
            MediaType.APPLICATION_JSON_VALUE)
        .setHeader("X-Correlation-Id", "req-001")
        .build());
~~~

`dispatched == true` chỉ phản ánh hợp đồng của channel. **Nó không chứng minh API đối tác đã trả HTTP 200, đã xử lý nghiệp vụ hay handler `acceptQuote` đã chạy.** Phản hồi WebClient có thể được xử lý bất đồng bộ; phải quan sát reply channel và error flow.

URL ở gateway là URL tuyệt đối. Nếu đồng thời đặt `WebClient.baseUrl(...)`, URL tuyệt đối không tự động nối với base URL. Hãy chọn một chiến lược nhất quán và không để client gọi URI tùy ý lấy từ payload không tin cậy.

### 6.1. Dựng mock API để thử local

Tạo **ứng dụng WebFlux riêng** chạy cổng 9090, với các record cùng schema JSON:

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class QuoteMockController {
    record QuoteRequest(String orderId, int weightKg) { }
    record QuoteResponse(String orderId, long shippingFeeVnd,
                         String currency) { }

    @PostMapping(path = "/api/quote",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<QuoteResponse> quote(@RequestBody Mono<QuoteRequest> body) {
        return body.map(request -> new QuoteResponse(
                request.orderId(), request.weightKg() * 12_000L, "VND"))
            .delayElement(Duration.ofMillis(150));
    }
}
~~~

~~~yaml
# application.yml riêng cho mock service
server:
  port: 9090
~~~

Kiểm tra mock trước khi gọi qua flow:

~~~bash
curl -i -X POST http://localhost:9090/api/quote \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"ORD-1001","weightKg":2}'
~~~

Body minh họa: `{"orderId":"ORD-1001","shippingFeeVnd":24000,"currency":"VND"}`. Tiếp đó gửi vào `pricingRequests`, đợi reply message xuất hiện trên `pricingResponses`. Không dùng thứ tự log so với `send()` để khẳng định kết nối HTTP đồng bộ hay bất đồng bộ tuyệt đối.

## 7. Phân biệt các loại timeout

Một thao tác có thể chờ **pool → DNS → TCP → TLS → gửi body → server xử lý → nhận response → handler downstream**. Các timeout tương ứng không thể thay thế cho nhau.

| Giới hạn | Vị trí | Điều không bao gồm |
|---|---|---|
| `pendingAcquireTimeout` | Chờ một slot trong connection pool | TCP/TLS và HTTP response |
| `CONNECT_TIMEOUT_MILLIS` | TCP connect | Chờ pool, DNS, thời gian xử lý của server |
| DNS resolver timeout | Phân giải hostname | Đợi slot trong pool, HTTP status |
| TLS handshake timeout | Thiết lập TLS | Xử lý nghiệp vụ bên ngoài |
| `responseTimeout` | Chờ phản hồi ở tầng Reactor Netty | Tổng thời gian queue + retry + downstream |
| Reactor `timeout(Duration)` | Deadline trên publisher được bao lại | Tự động rollback request đã xử lý từ xa |
| Spring Integration `replyTimeout` | Chờ reply messaging gateway | Connect timeout của WebClient |
| Proxy/ingress timeout | Proxy hoặc HTTP server phía trước | Logic nghiệp vụ sau khi client đã rời |

Ví dụ ngân sách end-to-end 8 giây: không thể đặt pending acquire 10 giây, connect 10 giây, response 30 giây rồi retry 5 lần và kỳ vọng toàn bộ thao tác tối đa 8 giây. Phải định nghĩa deadline tổng, chia ngân sách cho các chặng và dừng retry khi không còn thời gian.

Với SSE/streaming response, một `responseTimeout` quá ngắn có thể đóng kết nối hợp lệ nếu server phát event thưa; cần thiết kế heartbeat, idle timeout và giới hạn thời gian subscription phù hợp.

## 8. Vòng đời tài nguyên: connection reuse và shutdown

### 8.1. Dùng lại WebClient và connection

Không khởi tạo một `WebClient` cộng với `ConnectionProvider` mới cho từng message. Làm thế có thể tạo quá nhiều pool/event loops, tăng số socket, tránh được reuse và gây khó cleanup khi ứng dụng shutdown.

~~~java
// Ví dụ cần tránh trong mỗi lần xử lý event:
// new ReactorClientHttpConnector(
//     HttpClient.create(ConnectionProvider.builder("new-pool").build()))

// Nên inject @Qualifier("partnerWebClient") WebClient do Spring quản lý
// vào cấu hình outbound gateway hoặc service dùng chung.
~~~

`WebClient` là client immutable và có thể sử dụng đồng thời. Kết nối HTTP/1.1 keep-alive thường được tái sử dụng sau khi response hoàn tất, nếu server/proxy không yêu cầu đóng và transport xác định connection còn hợp lệ.

### 8.2. Tài nguyên dùng chung của Reactor Netty

Theo Spring Framework, Reactor Netty mặc định có global `HttpResources` gồm event loops và connection pool. Spring Boot hỗ trợ quản lý các resource tương ứng qua `ReactorResourceFactory`; trong ứng dụng reactive, client được tạo từ Boot-configured builder có thể chia sẻ tài nguyên với server.

Một `ConnectionProvider` **riêng** có vòng đời riêng. Ví dụ `@Bean(destroyMethod = "dispose")` chỉ dispose pool đó; không nên dispose global event loops tùy tiện khi những client/server khác vẫn dùng. Ứng dụng mở/đóng nhiều `ApplicationContext` trong cùng JVM cần đặc biệt quan tâm resource cleanup.

Nếu cần cô lập cả event loop lẫn connection pool, Spring Framework hỗ trợ `ReactorResourceFactory` và constructor `ReactorClientHttpConnector(resourceFactory, mapper)`; đây là cấu hình nâng cao cần quản lý lifecycle ở cấp ứng dụng.

### 8.3. Idle connection và race condition

Server, proxy hoặc load balancer có thể đóng một kết nối keep-alive nhàn rỗi mà client chưa nhận ra. Khi client tái sử dụng kết nối đó, có thể xuất hiện lỗi do remote đóng socket. `maxIdleTime` và background eviction giảm nguy cơ giữ kết nối cũ, nhưng **không loại bỏ mọi race condition**.

Cần tìm hiểu idle timeout thực tế của đối tác/proxy và cân nhắc retry đối với thao tác an toàn hoặc có idempotency. Không coi lỗi connection reuse là bằng chứng request nghiệp vụ chắc chắn chưa được xử lý.

## 9. Codec, maxInMemorySize và mapping headers

### 9.1. Giới hạn buffer khi giải mã JSON

HTTP message readers/codecs giữ một lượng dữ liệu trong bộ nhớ khi cần giải mã response. Trong các cấu hình WebFlux mặc định phổ biến, giới hạn buffering thường là **256 KiB**. Nếu vượt giới hạn, WebClient có thể phát `DataBufferLimitException`.

~~~java
WebClient client = builder
    .codecs(configurer -> configurer.defaultCodecs()
        .maxInMemorySize(2 * 1024 * 1024))
    .build();
~~~

Ví dụ này tăng giới hạn lên 2 MiB. Không đặt giới hạn vô hạn để giải quyết file lớn: memory pressure tăng theo số request đồng thời. Với response lớn, nên chọn API streaming, có giới hạn kích thước, concurrency và quản lý `DataBuffer`/resource đúng quy tắc.

### 9.2. Headers: chọn những gì cần ra ngoài

`Content-Type` mô tả request body; `Accept` mô tả response format client muốn đọc. `Authorization`, `X-Correlation-Id` và idempotency key có ý nghĩa khác. Trong Spring Integration, dùng `mappedRequestHeaders(...)` và `mappedResponseHeaders(...)` để kiểm soát metadata đi qua ranh giới HTTP.

Không đưa toàn bộ `MessageHeaders` nội bộ thành HTTP headers: `replyChannel`, `errorChannel` hoặc thông tin bảo mật của hệ thống nguồn không phải dữ liệu đối tác nên nhận. Header do client gửi vào cũng không thay thế authentication.

~~~java
.handle(WebFlux.outboundGateway(url, webClient)
    .httpMethod(HttpMethod.POST)
    .expectedResponseType(QuoteResponse.class)
    .mappedRequestHeaders(
        HttpHeaders.CONTENT_TYPE,
        HttpHeaders.ACCEPT,
        "X-Correlation-Id"))
~~~

Token ứng dụng nên được đặt trong WebClient filter hoặc OAuth2 client configuration, với giá trị lấy từ secret store/config được bảo vệ. Không hardcode token thật vào repository và không forward token của người dùng sang dịch vụ khác nếu chưa có cơ chế delegation hợp lệ.

## 10. HTTPS, TLS, DNS, proxy và bảo mật kết nối

### 10.1. HTTPS và mTLS

Trong production, ưu tiên HTTPS và kiểm tra chứng chỉ cùng hostname của server. Nếu đối tác yêu cầu mTLS, ứng dụng cần client certificate/private key và trust configuration phù hợp; cần có kế hoạch xoay vòng chứng chỉ.

Không dùng `InsecureTrustManagerFactory` hoặc tắt hostname verification để “sửa nhanh” lỗi TLS. Các trường hợp `PKIX path building failed`, certificate hết hạn hoặc hostname mismatch cần sửa truststore, certificate hay URL đúng nguồn.

### 10.2. Proxy và DNS

DNS có thể lỗi trước cả TCP connect. Reactor Netty hỗ trợ cấu hình resolver riêng; proxy doanh nghiệp có thể thay đổi cách client tới đích. Ví dụ kết nối qua HTTP proxy:

~~~java
import reactor.netty.transport.ProxyProvider;

HttpClient http = HttpClient.create(pool)
    .proxy(proxy -> proxy
        .type(ProxyProvider.Proxy.HTTP)
        .host("proxy.internal.example")
        .port(3128));
~~~

Đây chỉ là đoạn cấu hình minh họa. Trong môi trường thật, cần xác định thông tin xác thực proxy, HTTPS CONNECT, non-proxy hosts, DNS policy và firewall. Việc có kết nối tới proxy chưa chứng minh đích cuối cùng sẵn sàng.

### 10.3. URL động và SSRF

Nếu gateway dùng URI tạo trực tiếp từ payload/header bên ngoài, người dùng có thể khiến WebClient gọi các địa chỉ không được phép, gồm dịch vụ metadata, IP nội bộ hoặc máy chủ do kẻ tấn công chỉ định. Hãy ánh xạ `partnerId` vào **allowlist** URL đã cấu hình; giới hạn scheme HTTPS, hostname/port, redirect và quyền egress của môi trường.

`WebClient.baseUrl` là tiện ích định tuyến URI, **không phải** cơ chế ngăn SSRF.

## 11. Xử lý lỗi và retry

| Loại lỗi | Dấu hiệu thường gặp | Hành động |
|---|---|---|
| Pool đầy | Pending acquire tăng, timeout/overflow | Giới hạn concurrency, xem lại pool/queue |
| Connect/DNS/TLS | Refused, timeout, handshake/trust failure | Kiểm tra network, firewall, DNS, certificate |
| Chờ response | `responseTimeout` | Deadline và retry có điều kiện |
| HTTP `400/401/403` | Request hay credentials không hợp lệ | Sửa dữ liệu hoặc xác thực, không retry vô hạn |
| HTTP `429` | Đối tác giới hạn tốc độ | Giảm tải, backoff, tôn trọng Retry-After nếu hợp lệ |
| HTTP `502/503/504` | Đối tác/proxy tạm lỗi | Retry giới hạn, circuit breaker |
| Decode response | JSON/schema/media type không phù hợp | Sửa contract hoặc phiên bản codec |
| `DataBufferLimitException` | Response quá lớn so với codec limit | Giới hạn payload, streaming hoặc nâng mức có kiểm soát |

Trong WebFlux outbound gateway, lỗi có thể xuất hiện khi HTTP exchange được thực thi bất đồng bộ. Không mặc định mọi lỗi HTTP ném ra ngay tại `MessageChannel.send(...)`. Cần thiết kế `errorChannel`, error flow/advice hoặc đường lỗi tương ứng với kiểu endpoint và channel, kiểm chứng bằng thử nghiệm các loại lỗi.

### 11.1. Retry không được gây trùng nghiệp vụ

HTTP POST có thể **đã được đối tác xử lý** dù client timeout trước khi đọc response. Retry mù quáng có thể tạo đơn, tính phí hoặc sinh vận đơn hai lần. Với tác vụ có side effects, cần:

1. Dùng idempotency key ổn định cho cùng một yêu cầu; bên nhận lưu và đối chiếu key.
2. Chỉ retry lỗi tạm thời theo hợp đồng, có giới hạn lần thử, exponential backoff, jitter và deadline tổng.
3. Có circuit breaker hoặc rate limiter khi đối tác quá tải; không mở thêm kết nối vô hạn.
4. Lưu yêu cầu chưa hoàn tất bằng outbox/broker bền vững nếu không được phép mất event sau restart.
5. Quy định ACK/commit của nguồn Kafka/JMS sau các mốc xử lý phù hợp, có tính tới khả năng gửi trùng.
6. Tránh retry cùng một request ở quá nhiều lớp: WebClient, IntegrationFlow advice, listener và scheduler có thể cộng dồn lần gửi.

`ConnectionProvider` giải quyết **tài nguyên mạng**, không giải quyết độ tin cậy đầu-cuối của message. Các bảo đảm delivery, idempotency và transaction phải được thiết kế riêng.

## 12. Quan sát và tối ưu connection pool

Không có một giá trị `maxConnections` tối ưu cho mọi ứng dụng. Cần biết tốc độ request, thời gian đối tác giữ kết nối, giới hạn remote và mức đồng thời thực tế. Khi thấy throughput thấp, đừng vội tăng pool trước khi đo.

Những chỉ số hữu ích:

- **Active/idle/pending connections** và thời gian chờ acquire: pool có thật sự bão hòa?
- **HTTP latency p50/p95/p99**, lỗi 4xx/5xx, timeout: remote hay network đang chậm?
- **DNS, TCP connect, TLS errors**, số lần connection close/reuse: sự cố kết nối nào đang chiếm ưu thế?
- **In-flight messages và queue depth** trong IntegrationFlow: bottleneck nằm trước hay sau HTTP?
- **Retry rate** và tỷ lệ timeout: có retry storm đang gây tăng tải không?
- **Memory, event-loop và thread usage**: có blocking handler hay buffering quá lớn không?

Reactor Netty có tích hợp Micrometer metrics; muốn thu thập cần bật cấu hình và có registry/dependency phù hợp với phiên bản. Không mặc định mọi metric đã được expose chỉ vì có WebClient. Tránh dùng URL chứa token, user ID hoặc correlation ID làm tags có cardinality lớn hoặc làm lộ dữ liệu.

Khi tăng `maxConnections`, luôn đánh giá cùng `pendingAcquireMaxCount`, `pendingAcquireTimeout`, response timeout, remote rate limit, connection reuse và concurrency trong flow. Nếu remote đã quá tải, tạo thêm connection thường làm lỗi nhiều hơn thay vì tăng throughput.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Tạo WebClient mỗi request giúp an toàn thread” | WebClient immutable, dùng chung được; tạo pool liên tục lãng phí tài nguyên |
| “`maxConnections(30)` là 30 HTTP request/giây” | Đây là giới hạn connection, không phải throughput theo giây |
| “`pendingAcquireTimeout` là TCP connect timeout” | Một cái chờ pool, một cái giới hạn TCP handshake |
| “`responseTimeout` là deadline toàn bộ nghiệp vụ” | Chưa bao gồm queue, retry và downstream |
| “`send() == true` là đối tác đã ghi thành công” | Chỉ theo hợp đồng gửi message của channel |
| “Dùng WebClient thì mọi flow đều non-blocking” | JDBC, poller, queue, handler vẫn có thể blocking |
| “Tăng `maxInMemorySize` vô hạn để đọc file lớn” | Tăng nguy cơ hết bộ nhớ; cần streaming và giới hạn tải |
| “Connection pool tự đóng global event loops khi rảnh” | Vòng đời provider và event loops được quản lý riêng |
| “HTTPS nội bộ không cần xác minh certificate” | Vẫn phải kiểm tra trust và hostname đúng |
| “Retry POST sau timeout luôn an toàn” | Remote có thể đã hoàn thành; cần idempotency |

## 14. Bài thực hành

1. Chạy mock API `localhost:9090` và IntegrationFlow ở mục 6. Gửi `QuoteRequest`, kiểm tra JSON response và reply message `pricingResponses`.
2. Giảm `maxConnections` xuống 1 hoặc 2 trong môi trường test, gửi nhiều request đồng thời vào mock có độ trễ. Quan sát pending acquire và các lỗi timeout/overflow.
3. Dừng mock service rồi gửi message; phân biệt `connection refused` và connect timeout trong logs/error flow.
4. Tăng độ trễ mock vượt `responseTimeout(5s)`. Xác định request có thể đã tới server hay chưa và điều kiện retry an toàn.
5. Trả JSON lớn hơn `maxInMemorySize`; tái hiện `DataBufferLimitException` rồi lựa chọn tăng limit có kiểm soát hoặc streaming.
6. Thêm `X-Correlation-Id` vào message và HTTP request. Đối chiếu logs hai phía mà không ghi token và payload nhạy cảm.
7. Dùng HTTPS với certificate hợp lệ; thử certificate/hostname không phù hợp trong môi trường test để hiểu handshake failure.
8. Thêm nguồn Kafka/JMS vào flow và giả lập HTTP timeout. Thiết kế thời điểm ACK/commit và idempotency key.
9. Thử dùng chung một bean WebClient nhiều lần, sau đó tạo biến thể bằng `mutate()`; xác minh cấu hình client gốc không bị thay đổi.
10. Đóng `ApplicationContext` và quan sát pool riêng có được dispose; nếu ứng dụng mở/đóng context nhiều lần, kiểm tra sự tồn dư thread/socket.

**Câu hỏi vận dụng:** hệ thống nhận 200 đơn hàng mỗi giây; mỗi HTTP call thường mất 300 ms nhưng có lúc kéo dài vài giây. Pool bắt đầu đầy và pending queue tăng. Bạn cần đo những gì để quyết định giữa tăng `maxConnections`, giới hạn concurrency, thay đổi timeout, thêm queue/outbox hoặc thương lượng rate limit với đối tác? Vì sao chỉ tăng số connection là chưa đủ?

## 15. Tài liệu tham khảo

- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient builder, HTTP connector, codec limit và resources.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): quản lý và chia sẻ Reactor Netty resources.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connection pool, timeout, TLS, proxy, metrics.
- [Spring Integration Reference — WebFlux Support](https://docs.spring.io/spring-integration/reference/webflux.html): WebFlux outbound adapter/gateway và WebClient.
- [Spring Integration API — WebFlux Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/webflux/dsl/WebFlux.html): overload `outboundGateway(uri, webClient)` và `outboundChannelAdapter(uri, webClient)`.
- [Spring Framework — WebClient Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): xử lý HTTP response status và error.

> **Ghi nhớ:** WebClient định nghĩa HTTP contract, HttpClient quản lý transport, và ConnectionProvider quyết định acquire/reuse connections. Trong Spring Integration WebFlux, cả ba cần được thiết kế cùng MessageChannel, reply/error flow, timeout từng giai đoạn, giới hạn tải, TLS, metrics và idempotency.
