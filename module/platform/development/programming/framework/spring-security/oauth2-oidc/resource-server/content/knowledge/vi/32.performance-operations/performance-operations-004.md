# Nhóm kết nối, timeout và giới hạn lời gọi đến nhà phát hành

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, API thường phải liên lạc với Authorization Server (AS), hay còn gọi là **nhà phát hành token (issuer)**, để lấy thông tin tin cậy và kiểm tra token. Những lời gọi này nằm trên đường xử lý request hoặc trên đường khởi tạo/luân chuyển khóa. Nếu không giới hạn kết nối, thời gian chờ và concurrency, một issuer chậm có thể làm cạn connection pool, giữ request quá lâu và ảnh hưởng toàn bộ Resource Server.

Các request outbound phổ biến gồm:

- **OIDC discovery:** lấy metadata từ endpoint well-known để biết issuer, JWKS URI và các endpoint khác.
- **JWKS retrieval:** tải public signing keys để xác minh chữ ký JWT. Với JWT Resource Server, việc này thường được cache; không nhất thiết gọi issuer ở mọi request.
- **Token introspection:** gửi opaque Access Token đến endpoint introspection để hỏi token còn active hay không. Đây thường là lời gọi online trong quá trình xác thực, trừ khi ứng dụng có cache.
- **Token endpoint hoặc token exchange:** thường thuộc OAuth Client/BFF hoặc một luồng delegation riêng. Một Resource Server thuần xác minh token không cần gọi token endpoint cho từng API request.

Mục tiêu vận hành là bảo đảm mỗi loại lời gọi có **connection pool phù hợp, timeout có giới hạn, concurrency có trần, retry có ngân sách và chính sách lỗi an toàn**. Cần phân biệt cache JWKS với cache introspection, vì hai loại cache có tác động bảo mật khác nhau.

Bài học thuộc chương **Hiệu năng và vận hành**, dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, WebFlux/Servlet và Reactor Netty** làm bối cảnh.

## 1. Resource Server gọi issuer ở những thời điểm nào?

Luồng JWT và opaque token khác nhau:

~~~text
JWT Access Token
Client
  |
  | Authorization: Bearer <JWT>
  v
Resource Server
  |
  +-- JWT có kid phù hợp với key đã cache?
  |       |
  |       +-- Có --> xác minh chữ ký offline
  |       |
  |       +-- Không --> lấy/refresh JWKS từ issuer
  |
  +-- kiểm tra iss, aud, exp, nbf, scope...
  |
  v
API response

Opaque Access Token
Client
  |
  | Authorization: Bearer <opaque>
  v
Resource Server
  |
  +-- gọi introspection endpoint
  |       |
  |       +-- active=true --> tạo Authentication
  |       +-- active=false --> từ chối
  |       +-- timeout/unavailable --> không xác minh được
  |
  v
API response
~~~

### 1.1. JWT: không gọi JWKS cho mỗi request

Với JWT Resource Server, JwtDecoder xác minh chữ ký bằng public key lấy từ JWK Set URI. Các key được cache bởi thư viện JWT decoder/JWK source theo cấu hình và phiên bản. Khi key đã có trong cache, việc xác minh một JWT thông thường có thể diễn ra cục bộ mà không cần gọi issuer.

Lời gọi JWKS thường xuất hiện khi:

- Resource Server khởi động hoặc thực hiện discovery/lấy key theo cách triển khai.
- Cache key hết hạn hoặc cần refresh.
- JWT có kid chưa có trong cache.
- Issuer xoay signing key.
- Một lần tải key trước đó thất bại và decoder cần thử lại theo cơ chế của nó.

Vì vậy, số API request mỗi giây không nhất thiết bằng số JWKS request mỗi giây. Tuy nhiên, nhiều request đồng thời mang kid lạ hoặc một đợt key rotation có thể tạo burst tới issuer.

### 1.2. Opaque token: introspection thường nằm trên đường xác thực

Opaque token không thể được Resource Server tự giải mã để xác minh chữ ký và claim. Resource Server thường gọi introspection endpoint để nhận metadata như active, scope, sub, aud và thời hạn. Nếu mỗi incoming request đều introspect, tải lên issuer tăng gần theo số request có token, trừ khi có cache hoặc cơ chế batching do hệ thống tự thiết kế.

Introspection là một dependency online. Khi AS không phản hồi, Resource Server không có bằng chứng mới để kết luận token active. Không được biến lỗi mạng thành active=true hoặc cấp Authentication mặc định.

### 1.3. Discovery không giống JWKS

OIDC discovery trả metadata của issuer, trong đó có jwks_uri. Metadata discovery thường được thực hiện khi cấu hình/khởi tạo provider hoặc khi ứng dụng cần refresh metadata, tùy cách cấu hình. JWKS retrieval lấy tập public keys ở URI đó. Không cần tải discovery document ở mọi API request.

Có thể cấu hình issuer-uri để Spring Security tự khám phá metadata, hoặc khai báo jwk-set-uri tĩnh và tự cấu hình kiểm tra issuer. Dù dùng cách nào, URI tin cậy phải đến từ cấu hình được quản trị, không lấy từ token hoặc request của client.

## 2. Vì sao cần connection pool riêng?

Connection pool tái sử dụng TCP/TLS connections thay vì tạo handshake mới cho từng lời gọi. Nó giảm chi phí DNS/TCP/TLS và giới hạn số kết nối đồng thời tới issuer.

~~~text
Resource Server instances
       |
       +-- JWT key retrieval client
       |       |
       |       +-- pool JWKS
       |
       +-- opaque introspection client
       |       |
       |       +-- pool introspection
       |
       +-- business downstream clients
               |
               +-- pool cho từng nhóm dịch vụ
~~~

Tách pool theo **mục đích và trust boundary** giúp:

- Lời gọi introspection không chiếm hết connection của JWKS.
- Một downstream chậm không làm nghẽn mọi outbound traffic.
- Mỗi issuer có thể có giới hạn và timeout khác nhau.
- Quan sát được connection acquisition, active connections và pending requests theo dependency.
- Cấu hình TLS, proxy, mTLS hoặc credential phù hợp từng endpoint.

Không nhất thiết phải tạo một pool cho từng URL nhỏ nếu chúng cùng host và cùng policy; nhưng không nên dùng một pool vô hạn hoặc một pool chung không kiểm soát cho tất cả dependency.

## 3. Các giới hạn cần đặt trong một pool

| Giới hạn | Ý nghĩa | Khi thiếu |
| --- | --- | --- |
| Max connections | Số kết nối tối đa được mở. | Có thể mở quá nhiều socket và gây áp lực lên issuer. |
| Pending acquire max | Số request tối đa chờ lấy connection. | Hàng đợi tăng không giới hạn. |
| Pending acquire timeout | Thời gian chờ lấy connection rảnh. | Request chờ pool vô thời hạn. |
| Max idle time | Tuổi nhàn rỗi tối đa của connection. | Giữ connection stale sau khi proxy/server đóng. |
| Max life time | Tuổi tồn tại tối đa của connection. | Connection sống quá lâu qua thay đổi mạng/certificate. |
| Idle eviction | Chu kỳ loại bỏ connection hết hạn/nhàn rỗi. | Connection cũ có thể tồn tại lâu hơn policy. |
| Per-host/per-route cap | Giới hạn riêng cho một host. | Một issuer có thể chiếm toàn bộ capacity. |

Pool có giới hạn không tự tạo ra throughput. Khi tất cả connections bận, request mới phải chờ hoặc bị từ chối sau pending-acquire timeout. Đây là hành vi mong muốn khi hệ thống quá tải: **queue phải có giới hạn và thời gian chờ phải hữu hạn**.

### 3.1. Max connections và concurrency

Giả sử mỗi Resource Server instance có pool issuer với 20 connections. Nếu có 8 instance, lý thuyết có thể có tới 160 connections tới issuer, chưa tính các client khác. Cần tính tổng trên toàn cụm, không chỉ một JVM.

HTTP/2 có thể multiplex nhiều streams trên một TCP connection. Do đó số connection không bằng số request đồng thời; giới hạn stream, flow control và capacity của server cũng quan trọng. Cần đo theo giao thức và connector thực tế.

### 3.2. Pending acquire phải có trần

Nếu pool có 20 connections và 10.000 request cùng muốn introspect, không nên để 9.980 request xếp hàng trong heap. Đặt max pending acquire count, pending acquire timeout, giới hạn concurrency/bulkhead ở tầng gọi và rate limit phù hợp.

Khi capacity hết, trả lỗi dependency overload/timeout theo error contract. Không giữ request và memory vô hạn để chờ issuer hồi phục.

### 3.3. Idle time và connection lifetime

maxIdleTime nên được cân nhắc cùng idle timeout của load balancer/proxy/issuer. Nếu client giữ connection nhàn rỗi lâu hơn server cho phép, lần sử dụng tiếp theo có thể gặp connection reset. maxLifeTime giúp xoay connection theo chu kỳ, hữu ích khi có proxy, DNS changes hoặc certificate rotation.

Không chọn giá trị chỉ dựa trên ví dụ. Đo connection churn, TLS handshake cost và timeout ở hạ tầng thực tế.

## 4. Cấu hình pool và timeout bằng Reactor Netty

Với WebFlux và reactive HTTP client, có thể cấu hình ConnectionProvider cho Reactor Netty:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class IssuerHttpClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider issuerConnectionProvider() {
        return ConnectionProvider.builder("issuer-pool")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofSeconds(2))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient issuerWebClient(
            ConnectionProvider issuerConnectionProvider) {

        HttpClient httpClient =
            HttpClient.create(issuerConnectionProvider)
                .option(
                    ChannelOption.CONNECT_TIMEOUT_MILLIS,
                    2_000)
                .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Các giá trị 32 connections, 64 pending requests và timeout trong ví dụ chỉ để minh họa. Hãy tính lại từ concurrency, số instance, latency của issuer, giới hạn server và SLA của API.

### 4.1. Phân biệt pool acquire, connect và response timeout

Trong ví dụ:

- pendingAcquireTimeout giới hạn thời gian chờ một connection từ pool.
- CONNECT_TIMEOUT_MILLIS giới hạn việc thiết lập TCP connection.
- responseTimeout đặt giới hạn chờ response theo semantics của Reactor Netty.
- Một publisher timeout(Duration) có thể đặt deadline tổng cho operation.

Các timeout này bảo vệ các giai đoạn khác nhau. Một request có thể hết thời gian ở bước acquire trước khi có TCP connection; hoặc đã kết nối nhưng chờ issuer trả response. Khi điều tra, ghi rõ timeout phát sinh ở tầng nào.

### 4.2. Cấu hình TLS handshake

Reactor Netty cho phép cấu hình TLS qua HttpClient.secure(...). Nếu cần giới hạn handshake, có thể cấu hình handshakeTimeout theo API của phiên bản Reactor Netty đang dùng. Nếu introspection dùng mTLS, certificate/key material và trust configuration phải được quản lý như credential, không đặt trong source code.

### 4.3. Quản lý lifecycle của pool

ConnectionProvider là tài nguyên sống cùng application context. Dispose khi ứng dụng shutdown để đóng pool và giải phóng tài nguyên. Không tạo một ConnectionProvider mới cho mỗi request hoặc mỗi lần decode token.

## 5. Cấu hình client Servlet có pooling

Với Servlet Resource Server, decoder/introspector thường dùng RestOperations. Một lựa chọn là cung cấp RestTemplate dựa trên Apache HttpClient 5 với connection manager có giới hạn.

Ví dụ cấu hình theo Spring Framework 6 và Apache HttpClient 5:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IssuerRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient issuerHttpClient() {
        ConnectionConfig connectionConfig =
            ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager connectionManager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(32)
                .setMaxConnPerRoute(16)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        RequestConfig requestConfig =
            RequestConfig.custom()
                .setConnectionRequestTimeout(
                    Timeout.ofSeconds(2))
                .setResponseTimeout(Timeout.ofSeconds(3))
                .build();

        return HttpClients.custom()
            .setConnectionManager(connectionManager)
            .setDefaultRequestConfig(requestConfig)
            .evictExpiredConnections()
            .build();
    }

    @Bean
    RestTemplate issuerRestTemplate(
            CloseableHttpClient issuerHttpClient) {
        return new RestTemplate(
            new HttpComponentsClientHttpRequestFactory(
                issuerHttpClient));
    }
}
~~~

Đây là ví dụ pool và timeout cho client Servlet; API builder cụ thể cần khớp phiên bản Apache HttpClient 5/Spring Framework trong dự án. setMaxConnTotal và setMaxConnPerRoute đặt giới hạn pool; setConnectionRequestTimeout giới hạn thời gian chờ connection từ pool; connect/socket/response timeout kiểm soát các giai đoạn I/O.

Không thay bằng SimpleClientHttpRequestFactory rồi giả định đã có connection pooling. Factory đơn giản có thể đặt connect/read timeout nhưng không cung cấp cùng cơ chế pool của Apache HttpClient.

## 6. Nối HTTP client vào JWT decoder hoặc opaque introspector

### 6.1. Reactive JWT decoder

Spring Security cho phép cung cấp WebClient cho NimbusReactiveJwtDecoder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveJwtConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(WebClient issuerWebClient) {
        return NimbusReactiveJwtDecoder
            .withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
            .webClient(issuerWebClient)
            .build();
    }
}
~~~

issuerWebClient cần dùng pool và timeout đã cấu hình. URI JWKS là cấu hình tin cậy của server. Cần tiếp tục xác minh issuer, audience, timestamp và các claim cần thiết; giới hạn mạng không thay thế validation token.

### 6.2. Servlet JWT decoder

Với NimbusJwtDecoder, có thể cung cấp RestOperations được cấu hình timeout/pooling:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.web.client.RestTemplate;

@Configuration
public class ServletJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(RestTemplate issuerRestTemplate) {
        return NimbusJwtDecoder
            .withJwkSetUri(
                "https://identity.example.test/oauth2/jwks")
            .restOperations(issuerRestTemplate)
            .build();
    }
}
~~~

Tên builder method và khả năng cấu hình phụ thuộc phiên bản Spring Security; dùng API tương ứng với dependency đã khóa trong dự án. Nếu decoder được tạo bằng auto-configuration, hãy xác nhận cách thay decoder/transport không làm mất issuer, audience và timestamp validators.

### 6.3. Opaque token introspection

Introspection client cần URI cố định của AS, client authentication dành riêng cho Resource Server, connection pool/timeout riêng hoặc capacity được chia rõ, TLS trust và mTLS nếu AS yêu cầu, và không ghi token được introspect hoặc client secret vào log.

Trong Servlet stack, NimbusOpaqueTokenIntrospector có thể được cấu hình với RestOperations tùy API version. Trong Reactive stack, dùng ReactiveOpaqueTokenIntrospector/implementation reactive với WebClient đã cấu hình. Kiểm tra constructor/API đúng minor version; không bọc một HTTP client blocking vào reactive pipeline.

## 7. Pool riêng cho JWKS và introspection

Hai loại traffic có profile khác nhau:

| Đặc điểm | JWKS | Introspection |
| --- | --- | --- |
| HTTP operation | Thường GET public key set. | Thường POST token cần kiểm tra. |
| Tần suất | Thường theo cache/refresh/key rotation. | Có thể theo mỗi request có opaque token. |
| Payload nhạy cảm | Public key set, không phải token người dùng. | Request chứa Access Token; response chứa claims/metadata. |
| Cache | Cache key set theo thư viện/policy. | Positive/negative cache có tác động trực tiếp tới revocation. |
| Timeout | Phải đủ cho key retrieval/rotation nhưng có thể ngắn. | Phải phù hợp authentication latency budget. |
| Failure | Key mới không lấy được thì token cần key đó không xác minh được. | Không introspect được thì không thể khẳng định token active. |

Tách pool hoặc ít nhất tách concurrency budget giúp một đợt introspection traffic không làm JWKS refresh bị đói connection, và ngược lại.

## 8. Timeout theo ngân sách request

Giả sử API có SLA 800 ms. Nếu authentication introspection dùng hết 700 ms, controller còn rất ít thời gian xử lý. Cần phân bổ deadline:

~~~text
Incoming request deadline: 800 ms
   |
   +-- pool acquire:       <= 50 ms
   |
   +-- issuer connect/TLS: <= 150 ms (khi cần kết nối mới)
   |
   +-- introspection:      <= 250 ms
   |
   +-- authorization + app logic + response: phần còn lại
~~~

Đây là ví dụ phân bổ, không phải con số khuyến nghị chung. Nếu kết nối đã được reuse, connect/TLS không chạy ở mỗi request. Nếu JWKS key đã cache, request JWT có thể không cần network tới issuer.

### 8.1. Timeout không nên lớn hơn deadline còn lại

Một downstream call nên nhận **remaining budget** của request. Nếu request còn 100 ms mà client đặt timeout 3 giây, request có thể tiếp tục chạy sau khi caller đã bỏ cuộc. Dùng deadline propagation hoặc tính remaining duration trước khi gọi dependency.

### 8.2. Timeout tầng transport và timeout publisher

Có thể kết hợp pool acquire timeout, connect timeout, TLS handshake timeout, response/read timeout và publisher deadline. Timeout ngoài cùng bảo vệ use case; timeout bên trong bảo vệ tài nguyên transport. Chúng nên nhất quán và có thứ tự hợp lý. Ví dụ pool acquire timeout 5 giây trong khi tổng request deadline 1 giây là cấu hình không hữu ích.

## 9. Giới hạn concurrency và bulkhead

Pool giới hạn số connection, nhưng nhiều publisher vẫn có thể chờ hoặc chạy xử lý ở tầng khác. Một **bulkhead** giới hạn số lời gọi đang hoạt động cho một dependency.

~~~text
Incoming requests
      |
      v
Introspection bulkhead (max 40 in-flight)
      |
      +-- permit available --> call issuer
      |
      +-- no permit ---------> reject quickly / overload response
~~~

Với reactive code, có thể dùng operator giới hạn concurrency hoặc một semaphore/bulkhead reactive không blocking. Ví dụ:

~~~java
Flux<OAuth2AuthenticatedPrincipal> principals =
    Flux.fromIterable(tokens)
        .flatMap(introspector::introspect, 20);
~~~

Đoạn này minh họa concurrency limit khi xử lý một tập token. Nó không phải cách tự động bọc mọi request WebFlux; với endpoint đơn lẻ, dùng bulkhead/resilience policy ở client/service boundary.

### 9.1. Vì sao không chỉ dựa vào pool?

Nếu pool có 32 connections và 50.000 requests chờ, pool vẫn có thể giữ một hàng đợi rất lớn trừ khi pending count/time được giới hạn. Bulkhead giới hạn số công việc được phép tiến tới dependency; pending queue có trần riêng.

### 9.2. Giới hạn trên từng instance và toàn cụm

Nếu mỗi instance cho phép 40 introspection calls và deployment có 20 instances, AS có thể nhận tới 800 calls đồng thời. Khi scale out, tổng concurrency tăng theo số instance. Cần tính capacity toàn cụm, xem AS có giới hạn request/connections riêng không, dùng gateway/rate limiter tập trung nếu cần quota toàn hệ thống và tránh autoscaling khiến số lời gọi vượt khả năng issuer.

## 10. Rate limit và backpressure

**Concurrency limit** giới hạn số lời gọi đồng thời; **rate limit** giới hạn số lời gọi trong một khoảng thời gian. Hai điều này bổ sung cho nhau.

Ví dụ:

- Tối đa 40 introspection calls đang chạy.
- Tối đa 200 calls/giây từ một Resource Server deployment.
- Tối đa 20 calls/giây tới một issuer tenant riêng.

Con số thực tế phải dựa trên quota AS và load test. Nếu AS trả 429 Too Many Requests, tôn trọng Retry-After nếu có, đồng thời giảm tốc độ/áp backoff. Không lập tức retry hàng loạt khi nhận 429.

Reactive backpressure giúp điều tiết publisher có thể kiểm soát, nhưng không tự giới hạn mọi HTTP request đang đến server. Cần ingress rate limit, concurrency gate và bounded queue ở đúng ranh giới.

## 11. JWKS cache, key rotation và request amplification

JWKS cache giúp JWT validation không phải gọi issuer ở mỗi request. Nhưng cache cần tương thích với key rotation:

~~~text
Issuer publishes keys:
  K1 (old) + K2 (new)
       |
       v
Resource Server fetches JWKS and caches K1,K2
       |
       v
Issuer starts signing with K2
       |
       v
Resource Server validates JWT kid=K2 locally
       |
       v
Issuer eventually retires K1 after overlap window
~~~

### 11.1. Overlap khi xoay khóa

Issuer nên công bố khóa mới trước khi bắt đầu ký bằng khóa đó và giữ khóa cũ đủ lâu cho token đã phát hành. Resource Server cần có khả năng refresh JWKS khi gặp key mới.

Không xóa key cũ ngay khi bắt đầu dùng key mới nếu vẫn còn JWT hợp lệ được ký bằng key cũ.

### 11.2. kid lạ có thể tạo burst

Nếu mỗi request chứa JWT với một kid không tồn tại, decoder có thể thử refresh JWKS. Một attacker có thể lợi dụng điều này để gây request amplification tới issuer nếu không có cache, rate limit hoặc cơ chế kiểm soát refresh phù hợp.

Biện pháp:

- Dùng decoder/JWK source có cache và hành vi refresh đã hiểu rõ.
- Giới hạn outbound concurrency và pool pending queue.
- Theo dõi số JWKS fetch và tỷ lệ unknown kid.
- Cân nhắc rate limit/negative caching ở lớp phù hợp nếu thư viện/kiến trúc hỗ trợ.
- Không tự fetch JWKS bằng một request tùy ý mỗi lần decode.

Không tự viết cache key chỉ theo token string hoặc bỏ qua kid; phải tuân theo JWK selection và signature verification.

### 11.3. Cache TTL và stale keys

Cache quá ngắn làm tăng traffic tới issuer; cache quá dài có thể kéo dài thời gian nhận biết key bị thay thế/thu hồi. Chọn TTL và refresh behavior theo key rotation policy, thời hạn token, yêu cầu incident response và khả năng issuer.

Không nhầm cache public JWKS với cache token active. Cache JWKS lưu public verification material; cache introspection có thể khiến token đã revoke vẫn được coi active cho đến khi cache hết hạn.

## 12. Introspection cache và revocation window

Opaque token thường được introspect online. Để giảm tải, ứng dụng có thể cache kết quả theo token fingerprint/secure cache key. Tuy nhiên, cache positive result làm chậm phát hiện revocation.

~~~text
10:00:00  Introspection: active=true, exp=10:10
10:01:00  AS revokes token
10:01:05  Resource Server vẫn có cached active result
10:02:00  Cache entry expires
10:02:01  Introspection mới: active=false
~~~

Trong ví dụ, revocation có thể mất gần một phút để lan tới Resource Server. Đây là trade-off cần được chấp thuận theo risk policy.

### 12.1. Giới hạn TTL positive cache

TTL nên không vượt quá giá trị nhỏ nhất giữa positive cache TTL do ứng dụng cấu hình, thời gian còn lại tới exp trừ safety margin (nếu introspection trả exp đáng tin) và revocation propagation window được nghiệp vụ cho phép.

Nếu response không có exp, không tự giả định token sống vô hạn; dùng policy TTL có giới hạn hoặc không cache.

### 12.2. Cache key không lưu raw token trong log

Không đưa token vào cache key logs, metrics labels hoặc distributed tracing. Có thể dùng HMAC/hash có secret quản lý phù hợp để tạo cache key ổn định; tránh dùng raw token làm key có thể bị lộ qua diagnostics.

### 12.3. Negative caching

Cache active=false trong một khoảng ngắn có thể giảm lặp introspection cho token invalid. TTL cần ngắn và có giới hạn vì token có thể được cấp mới hoặc trạng thái thay đổi theo AS. Không cache lỗi timeout thành inactive lâu dài nếu điều đó khiến hệ thống từ chối token hợp lệ sau khi AS hồi phục.

## 13. Retry, circuit breaker và chính sách lỗi

Retry có thể giúp vượt qua lỗi mạng ngắn, nhưng cũng có thể khuếch đại tải khi issuer đang quá tải.

| Tình huống | Hướng xử lý |
| --- | --- |
| DNS/connect reset tạm thời | Có thể retry ít lần với backoff/jitter. |
| HTTP 429 | Tôn trọng Retry-After, giảm tốc độ. |
| HTTP 5xx | Retry có giới hạn nếu operation an toàn và còn deadline. |
| HTTP 4xx do credential/config sai | Không retry vô hạn; báo lỗi cấu hình. |
| Introspection timeout | Không coi token active; fail closed. |
| JWKS timeout khi key đã cache | Có thể tiếp tục xác minh token dùng key đã tin cậy/cached theo decoder policy. |
| JWKS timeout với kid mới chưa biết | Không xác minh được chữ ký; từ chối request cần key đó. |
| Circuit breaker open | Fail fast theo dependency policy; không bỏ qua xác minh. |

### 13.1. Retry budget

Ví dụ một lần retry sau 100 ms backoff có thể hợp lý với transient connection error. Nhưng ba lần retry trong một request có deadline 500 ms có thể không còn thời gian cho application logic. Hãy tính:

~~~text
totalBudget >=
  attempts * perAttemptTimeout
  + sum(backoff)
  + localProcessingBudget
~~~

Đây là mô hình ước lượng; thời gian thực còn phụ thuộc pool acquire, DNS, TLS và response.

### 13.2. Circuit breaker không được fail open

Circuit breaker có thể ngừng gọi issuer trong khi dependency đang lỗi để bảo vệ tài nguyên. Khi breaker open:

- Opaque token không được introspect thành công: không tạo Authentication.
- JWT có key đã cache vẫn có thể xác minh cục bộ theo trust/cache policy.
- JWT cần key mới mà không thể lấy JWKS: không được bỏ qua signature check.
- Không trả principal mặc định để giữ availability.

**Availability không được đạt bằng cách chấp nhận token chưa xác minh.**

### 13.3. Không retry lỗi nghiệp vụ hoặc credential

Client authentication sai ở introspection endpoint, URI issuer sai, TLS trust sai hoặc response malformed là lỗi cấu hình/tích hợp. Retry liên tục chỉ làm log và tải issuer tăng. Alert và sửa cấu hình.

## 14. Tách failure domain theo issuer

Một ứng dụng có thể tin cậy nhiều issuer/tenant. Không để một issuer chậm làm cạn capacity của các issuer khác:

~~~text
Resource Server
    |
    +-- issuer-A pool + bulkhead + timeout
    |
    +-- issuer-B pool + bulkhead + timeout
    |
    +-- issuer-C pool + bulkhead + timeout
~~~

Mỗi issuer cần trust configuration riêng: issuer ID, metadata/JWKS/introspection URI, client credential nếu introspection, TLS trust và capacity budget.

Không chọn issuer endpoint từ iss trong token rồi gọi URL tùy ý mà không có trust registry. Nếu multi-issuer được hỗ trợ, dùng resolver/registration đã cấu hình và kiểm tra issuer nằm trong allowlist trước khi truy cập network.

## 15. Multi-tenant và bảo vệ endpoint issuer

Nếu mỗi tenant có issuer riêng:

- Giới hạn số issuer được đăng ký.
- Cache metadata/JWKS theo issuer đã tin cậy.
- Giới hạn tổng pool và pool per issuer.
- Giới hạn số lần discovery khi tenant mới xuất hiện.
- Không tự discovery từ URL do user gửi.
- Có cơ chế evict metadata/pool khi tenant bị xóa.
- Kiểm tra TLS hostname và issuer identity.

Một endpoint nhận issuerUrl từ request rồi fetch discovery document có thể trở thành SSRF. Trust registry phải quyết định issuer nào được phép; URL do caller cung cấp chỉ có thể là khóa tra cứu tới registration đã tồn tại, không phải quyền tự do gọi mạng.

## 16. Spring Boot configuration và ranh giới trách nhiệm

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_SECRET_MANAGER
~~~

Đây là minh họa các endpoint/cấu hình. Trong một ứng dụng, chọn JWT hoặc opaque token theo cách xác thực được hỗ trợ; không nhất thiết khai báo cả hai cho cùng một filter chain. Với Boot, property namespace và auto-configuration cần khớp đúng phiên bản; custom decoder/introspector có thể thay đổi cách Boot áp các property.

Các property trên **không tự mô tả toàn bộ connection pool budget**. Khi cần pool/timeouts chi tiết, cung cấp HTTP client/decoder/introspector tùy chỉnh theo stack Servlet hay Reactive.

## 17. Timeout và pool không được phá hỏng TLS

Khi cấu hình issuer client:

- Giữ certificate chain validation.
- Giữ hostname verification.
- Dùng truststore/CA được quản trị.
- Với mTLS introspection, dùng client certificate đúng registration.
- Xoay client certificate và đóng/refresh pool khi cần để connection mới dùng credential mới.
- Không tắt TLS verification để khắc phục lỗi handshake.

Một connection đã được thiết lập có thể tiếp tục dùng session/certificate context cũ sau khi cấu hình certificate thay đổi, tùy connector. Kế hoạch rotation phải xác định lúc nào reload SSL context và evict/close connections cũ.

## 18. Observability: đo lời gọi đến issuer

Nên có metrics riêng theo issuer và operation:

| Metric | Ý nghĩa |
| --- | --- |
| Request count | Số JWKS/discovery/introspection calls. |
| Latency histogram | p50/p95/p99 của từng operation. |
| Timeout count | Timeout theo acquire/connect/TLS/response/deadline. |
| Connection active/idle | Mức sử dụng pool. |
| Pending acquire | Số request đang chờ connection. |
| Acquire timeout/rejection | Pool đã quá tải. |
| HTTP status | 2xx, 4xx, 429, 5xx. |
| Retry count | Mức độ transient failure và retry amplification. |
| Circuit breaker state | Closed/open/half-open. |
| JWKS refresh/unknown kid | Key rotation và cache behavior. |
| Introspection cache hit/miss | Hiệu quả cache và tải thực lên AS. |

Không ghi raw Access Token, Refresh Token, Authorization header, client secret, toàn bộ introspection response hoặc token claims nhạy cảm. Metric label không nên chứa token, subject ID hoặc URL động có cardinality lớn.

### 18.1. Phân biệt lỗi issuer với lỗi Resource Server

Một request 401 có thể do token sai; 503 có thể do issuer không sẵn sàng; 500 có thể là lỗi mapping hoặc ứng dụng. Hãy giữ exception category và dependency name trong log/trace nội bộ để phân tích, nhưng trả thông tin vừa đủ cho client.

## 19. Kiểm thử connection pool và timeout

Unit test cho publisher không đủ để kiểm tra pool, TLS, HTTP status, connection reuse và pending acquire. Dùng HTTP stub server như MockWebServer hoặc WireMock để điều khiển issuer response và delay.

### 19.1. Ma trận kiểm thử

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| JWKS trả nhanh, key đã cache | JWT decode không tạo request JWKS cho mỗi API call. |
| JWT có kid mới | Decoder refresh JWKS theo policy và xác minh chữ ký. |
| JWKS endpoint chậm | Fetch timeout; token cần key mới không được chấp nhận. |
| JWKS trả 500 | Lỗi dependency được phân loại, không bỏ signature check. |
| Nhiều unknown kid đồng thời | Outbound concurrency/pool pending có giới hạn. |
| Introspection trả active=true | Principal được tạo theo claims và authorization policy. |
| Introspection trả active=false | Authentication thất bại. |
| Introspection timeout | Không tạo principal; lỗi dependency được quan sát. |
| Pool hết connections | Request chờ có giới hạn rồi fail/reject. |
| Issuer trả 429 | Client tôn trọng rate-limit/backoff policy. |
| Issuer trả 401 do client secret sai | Không retry vô hạn; alert cấu hình. |
| Circuit breaker open | Fail fast, không fail open authentication. |
| Introspection positive cache | Cache hit giảm calls nhưng TTL nằm trong revocation budget. |
| Token bị revoke | Cache invalidation/expiry phản ánh theo SLA đã chọn. |
| Issuer certificate không tin cậy | TLS validation thất bại. |
| mTLS certificate rotation | Connection mới dùng certificate/context đúng. |

### 19.2. Test pool saturation

Tạo stub issuer giữ response trong một khoảng thời gian có kiểm soát. Gửi nhiều lời gọi đồng thời vượt maxConnections và pendingAcquireMaxCount. Xác nhận active connections không vượt pool max, pending acquisitions không vượt queue max, request chờ lâu hơn pending timeout bị fail, connection được trả về pool hoặc dispose đúng khi response hoàn tất, và một issuer pool bị bão hòa không làm pool độc lập khác bị cạn.

Không dùng Thread.sleep làm cơ chế đồng bộ trong test; dùng latch ở test harness, controllable response hoặc publisher test utilities.

### 19.3. Test timeout và cancellation

Với reactive client, xác nhận timeout tạo lỗi dự kiến và upstream HTTP exchange bị dispose/cancel theo khả năng connector. Với servlet client, xác nhận thread/request được giải phóng sau timeout; lưu ý một số blocking I/O có thể không ngắt được ngay khi thread bị interrupt.

### 19.4. Test không gọi issuer ở mỗi JWT request

Gửi nhiều JWT hợp lệ có cùng key sau lần JWKS fetch đầu tiên. Đếm số request tới stub JWKS server. Kết quả cần phù hợp cache/refresh policy của decoder, không tăng một request cho mỗi API call. Không hardcode một TTL mặc định nếu thư viện/version đang dùng có cấu hình khác.

## 20. Tính capacity sơ bộ

Little's Law có thể giúp ước lượng số request đồng thời trung bình:

~~~text
in_flight ≈ arrival_rate × average_latency
~~~

Ví dụ:

- 100 introspection calls/giây.
- Latency trung bình 100 ms (0,1 giây).

~~~text
in_flight ≈ 100 × 0.1 = 10
~~~

Đây là concurrency trung bình theo giả định ổn định. Capacity thực tế cần headroom cho p95/p99 latency, burst, retry, connection churn và số instance. Không chọn pool max đúng bằng giá trị trung bình.

### 20.1. Tính toàn cụm

Nếu 10 instances, mỗi instance có 20 connections, tổng connection cap có thể lên tới 200. Cộng thêm các service khác cùng gọi issuer. Phải phối hợp quota với đội vận hành AS; connection pool per instance không tự đảm bảo quota toàn hệ thống.

### 20.2. Capacity khi issuer chậm

Khi latency tăng từ 100 ms lên 2 giây mà arrival rate giữ 100 calls/s:

~~~text
in_flight ≈ 100 × 2 = 200
~~~

Nếu pool chỉ có 32 connections, pending queue có thể tăng nhanh. Pool acquire timeout và bulkhead sẽ từ chối một phần request sớm, giúp bảo vệ heap và các dependency khác. Đây là lý do cần load test với latency tăng, không chỉ test issuer hoạt động bình thường.

## 21. Checklist triển khai

1. **Liệt kê endpoint issuer:** discovery, JWKS, introspection và token endpoint nếu có luồng client/delegation.
2. **Phân biệt JWT và opaque:** xác định lời gọi nào xảy ra online và lời gọi nào được cache.
3. **Cấu hình trust cố định:** issuer/JWKS/introspection URI, TLS và client credentials.
4. **Dùng HTTP client đúng stack:** Servlet dùng client blocking có pool; WebFlux dùng WebClient/reactive connector.
5. **Đặt pool cap:** max connections, per-route cap, pending queue count và pending timeout.
6. **Đặt timeout từng tầng:** acquire, connect, TLS, response/read và deadline tổng.
7. **Tách failure domain:** pool/bulkhead/concurrency theo issuer và operation.
8. **Giới hạn retries:** backoff/jitter, Retry-After, retry budget và idempotency khi có side effect.
9. **Giữ fail closed:** introspection/JWKS không sẵn sàng không trở thành bằng chứng token hợp lệ.
10. **Định nghĩa cache policy:** JWKS rotation riêng; introspection TTL theo revocation window.
11. **Đo telemetry:** pool utilization, pending acquire, latency, timeout, 429/5xx, refresh và cache hit.
12. **Kiểm thử tải và lỗi:** issuer chậm, pool saturation, key rotation, unknown kid, 429, 5xx, TLS failure và certificate rotation.

**Ghi nhớ:** JWT Resource Server thường xác minh offline bằng public key đã cache; issuer chỉ cần được gọi khi discovery/JWKS cần tải hoặc refresh. Opaque Resource Server thường introspect token online nên tải phụ thuộc trực tiếp vào request rate và cache policy. Hãy dùng **connection pool có giới hạn, pending queue hữu hạn, timeout theo từng tầng, bulkhead và retry budget**. Cache JWKS và cache introspection có trade-off khác nhau; circuit breaker hoặc timeout không bao giờ được biến thành xác thực thành công khi chưa có bằng chứng token hợp lệ.

## Tài liệu tham khảo

- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Security — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html).
- [Project Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html).
- [Project Reactor Netty — Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool).
- [Apache HttpClient 5 — Connection Management](https://hc.apache.org/httpcomponents-client-5.4.x/current/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManager.html).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
