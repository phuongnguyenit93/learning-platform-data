# 32.6. Timeout, connection pool và kiểm soát tải tới provider

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, cấu hình đúng issuer, client ID, client secret, scope và redirect URI mới giải quyết phần giao thức. Khi vận hành production, ứng dụng còn phụ thuộc vào **độ trễ mạng**, **connection pool**, **timeout**, **sức chịu tải của OpenID Provider/Authorization Server** và cách ứng dụng xử lý lỗi.

Một hệ thống có thể đăng nhập nhanh với 10 người nhưng đứng khi 2.000 nhân viên đồng loạt vào ca; một refresh request có thể timeout khi Authorization Server (AS) đã rotate refresh token; hoặc một đợt key rotation khiến hàng loạt Pods cùng tải JWKS.

Bài học này hướng dẫn thiết kế những giới hạn vận hành mà vẫn bảo đảm các bất biến OAuth/OIDC.

Sau bài, bạn có thể:

- Phân biệt browser authorization redirect với HTTP calls từ backend.
- Nhận diện token, refresh, client credentials, UserInfo, JWKS, discovery và revocation requests.
- Phân biệt connection-acquire, connect, response/read, TLS, overall và idle timeouts.
- Thiết kế HTTP pool có max connections, per-route quota, bounded pending queue và idle eviction.
- Tính tải tổng của nhiều Pods và provider quota.
- Wire HTTP client đúng vào Spring Security OAuth2 Login và Refresh Token provider.
- Cấu hình Reactor Netty/WebClient cho WebFlux.
- Áp rate limit, bulkhead, circuit breaker, backoff và jitter có kiểm soát.
- Tránh blind retry với authorization code và rotating refresh token.
- Theo dõi p95/p99, pool saturation, 429, refresh failures và secret-safe logs.
- Kiểm thử provider chậm, pool cạn, fake 429/503 và hệ thống fail closed.

---

## 1. Bản đồ các outbound requests

~~~mermaid
flowchart LR
    Browser["Browser"] -->|"302 redirect"| Authorize["OP /authorize"]
    Browser -->|"Callback code + state"| Portal["Spring Security Portal"]
    Portal -->|"POST code / refresh"| Token["OP /token"]
    Portal -->|"GET claims nếu cần"| UserInfo["OP /userinfo"]
    Portal -->|"GET signing keys"| JWKS["OP /jwks"]
    Portal -->|"GET provider metadata"| Discovery["OIDC discovery"]
    Portal -->|"Bearer access token"| API["Orders API"]
~~~

Không phải mọi mũi tên đều do cùng HTTP client thực hiện.

| Operation | Bên thực hiện | Khi nào | Hậu quả khi chậm |
|---|---|---|---|
| Authorization endpoint | Browser | Bắt đầu login | Người dùng chờ OP |
| Authorization Code token exchange | Backend Portal | Callback | Servlet thread/HTTP connection bị giữ |
| Refresh Token grant | Backend Portal | Token gần hết hạn | Downstream API calls chậm |
| Client Credentials grant | Backend job | Xin service token | Job và API calls chậm |
| UserInfo | Backend nếu có UserInfo | Sau OIDC token validation theo flow | Login chậm |
| JWKS | Backend JWT/OIDC decoder | Cache miss/rotation | ID token verification chậm |
| OIDC discovery | Backend theo config/version | Startup/config | Startup/readiness chậm |
| Revocation | Backend theo workflow | Logout/token cleanup | Remote revoke chậm |

### 1.1. Authorization redirect không sử dụng token connection pool

`OAuth2AuthorizationRequestRedirectFilter` thường trả:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.com/authorize?client_id=...&state=...
~~~

Browser gọi OP. Tăng backend token pool không làm OP login page hiển thị nhanh hơn.

### 1.2. Token endpoint là backend request nhạy cảm

~~~http
POST /token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-auth>

grant_type=authorization_code&code=...&redirect_uri=...
~~~

Request này cần timeout, pool và policy retry đúng grant. Không log authorization code hoặc client authentication.

### 1.3. Không chỉ có token endpoint

UserInfo, JWKS và metadata discovery có thể dùng HTTP transports khác, không tự kế thừa HTTP client đã cấu hình cho token grant.

## 2. Phân biệt từng loại timeout

Một HTTP request đi qua nhiều giai đoạn:

~~~text
Wait for rate/bulkhead permit
  -> Wait for pooled connection
  -> DNS
  -> TCP connect
  -> TLS handshake
  -> Send request
  -> Wait for response headers
  -> Read body
  -> Parse/validate tokens
~~~

| Loại | Giới hạn | Khi cấu hình thiếu |
|---|---|---|
| Pool acquire timeout | Chờ lấy free connection | Queue/threads bị giữ |
| Connect timeout | Thiết lập TCP | Kết nối tới host lỗi chờ lâu |
| TLS handshake timeout | Bắt tay TLS | TLS stalls |
| Response/read timeout | Đợi response/data theo client semantics | Server đã kết nối nhưng xử lý chậm |
| Overall deadline | Tổng operation từ đầu đến cuối | Các giai đoạn cộng dồn vượt SLO |
| Idle timeout | Giữ connection rảnh trong pool | Tích tụ idle/stale sockets |
| Max connection lifetime | Tuổi connection | Connection tồn tại quá lâu |
| Authorization request TTL | Thời gian state chờ browser callback | Callback cũ được nhận quá lâu hoặc user hết hạn sớm |

### 2.1. Connect timeout không phải response timeout

Kết nối TCP có thể thành công sau 100 ms nhưng AS xử lý token 30 giây. `connect-timeout=2s` không giới hạn thời gian xử lý request này.

### 2.2. Pool-acquire timeout cần ngắn và có bounds

Pool tối đa 30 active connections; request thứ 31 phải đợi. Nếu queue vô hạn, ứng dụng có thể treo hàng nghìn Servlet threads.

### 2.3. Response timeout không luôn là total request deadline

Một số HTTP clients chỉ giới hạn thời gian chờ response/inactivity. Cần hiểu semantics cụ thể của Apache HC5, Reactor Netty hoặc client đang dùng.

### 2.4. Tổng thời gian không tự là phép cộng bảo đảm

~~~text
acquire = 500ms
connect = 2s
response = 4s
~~~

Không được tự khẳng định operation luôn dưới 6,5 giây: DNS, TLS, retries, body processing và application logic có thể cần budget riêng.

### 2.5. State TTL hoàn toàn khác HTTP timeout

User có thể cần vài phút để nhập MFA và consent, trong khi backend token request nên có timeout vài giây. Không đặt OAuth state TTL bằng HTTP response timeout.

### 2.6. Cấu hình minh họa

~~~yaml
app:
  oidc-http:
    pool-acquire-timeout: 500ms
    connect-timeout: 2s
    response-timeout: 4s
    max-total-connections: 80
    max-per-route: 30
    idle-timeout: 30s
    max-life-time: 5m
~~~

**`app.oidc-http` là custom configuration**, không phải properties mà Spring Security tự áp dụng. Cần binding vào đúng HTTP client.

## 3. Chọn timeout theo SLO

Không tồn tại một con số tốt cho tất cả providers.

Cần đo:

- Token endpoint p50, p95, p99.
- JWKS/UserInfo latency.
- DNS/TLS/proxy latency.
- 429/5xx rates.
- Servlet request thread capacity.
- Ingress/load balancer timeouts.
- Provider SLA, client quota và login SLO.

### 3.1. Ví dụ ngân sách

| Tham số | Giá trị giả định | Tác dụng |
|---|---:|---|
| Pool acquire | 0,5 s | Không xếp hàng vô hạn |
| TCP connect | 2 s | Fail kết nối sớm |
| Response | 4 s | Giới hạn provider chậm |
| Callback outbound total | Theo SLO, ví dụ vài giây | Deadline tổng nếu cần |
| Idle eviction | 30 s | Dọn idle connections |
| Max lifetime | 5 phút | Làm mới connection có kiểm soát |
| Pending state TTL | Vài phút | User đủ thời gian login/MFA |

Giá trị minh họa, không phải mặc định dùng ở production.

### 3.2. Timeout quá ngắn

Tăng false failures, gây người dùng bấm login lại, tạo thêm token requests và refresh storms.

### 3.3. Timeout quá dài

Giữ thread/connection quá lâu, tăng p99 latency, queue backlog và có thể vượt timeout của ingress trước khi backend dừng xử lý.

### 3.4. Chọn theo độ trễ thực

Đừng tăng timeout chỉ để không còn thấy timeout logs. Nếu p99 OP đã vượt SLO, cần giảm tải, tối ưu đường mạng hoặc làm việc với provider.

## 4. Connection pool và giới hạn tài nguyên

Pool giảm chi phí mở TCP/TLS connection mới:

~~~text
No reuse:
  request A -> TCP/TLS -> response -> close
  request B -> TCP/TLS -> response -> close

With keepalive:
  request A -> TCP/TLS -> response -> idle
  request B -> reuse connection -> response
~~~

### 4.1. Những tham số quan trọng

1. Maximum total connections.
2. Maximum connections per route/host.
3. Maximum pending acquire count.
4. Pool acquire timeout.
5. Idle eviction.
6. Maximum connection lifetime.
7. DNS/TLS/proxy policy.
8. Response body/stream closure.
9. Metrics active/idle/pending connections.

### 4.2. Pool lớn không làm provider xử lý nhanh hơn

Tăng pool từ 40 lên 200 có thể khiến OP bị overload hoặc trả 429 nhiều hơn, nhất là khi nhiều Pods cùng tăng.

### 4.3. Pool cần lifecycle dùng chung

Không tạo HTTP client/connection manager mới cho mỗi callback. Dùng singleton bean có shutdown/cleanup rõ ràng.

### 4.4. Connection leak

Nếu response body không được consume/close, connection có thể không quay về pool, khiến acquire timeout tăng dù OP vẫn khỏe.

### 4.5. Per-route quotas

Khi một transport phục vụ OP A và OP B, per-route limit có thể giúp một host không chiếm hết connections. Nếu tenant isolation rất quan trọng, cân nhắc dedicated pools hoặc bulkheads.

## 5. Tính concurrency theo tải

Little's law giúp ước lượng:

\[
L \approx \lambda \times W
\]

- \(L\): concurrent requests trung bình.
- \(\lambda\): request rate mỗi giây.
- \(W\): latency trung bình tính bằng giây.

Ví dụ 80 requests/giây và latency 0,25 giây:

~~~text
80 × 0.25 = 20 in-flight requests trung bình
~~~

Khi OP chậm p99 lên vài giây, concurrency thực tế có thể tăng mạnh; cần headroom và bounded queue.

### 5.1. Tổng capacity toàn cluster

6 Pods, mỗi Pod có 30 connections tới cùng OP:

~~~text
Cluster potential = 6 × 30 = 180 connections
~~~

Nếu provider quota chỉ 100, cluster có thể vượt dù từng Pod không sai.

### 5.2. HPA làm thay đổi quota consumption

Khi autoscale từ 4 lên 12 replicas, số pools và discovery/JWKS warm-up cũng tăng. Đừng xem pool limit per Pod là cluster-wide rate limiter.

### 5.3. Rate, concurrency, pool và queue là bốn đại lượng

- Rate: requests/giây.
- Concurrency: operations đồng thời.
- Pool: physical/logical HTTP connections.
- Queue: requests chờ permit/connection.

Mỗi giới hạn phục vụ mục đích khác nhau.

## 6. Các cơn bão tải đặc trưng

### 6.1. Login storm

Đầu ca, nhiều users quay về callback cùng lúc; token endpoint nhận burst authorization-code POST.

### 6.2. Refresh storm

Tokens cấp gần cùng thời điểm, cùng hết hạn và refresh đồng loạt.

### 6.3. Client Credentials cold start

Nhiều jobs hoặc Pods mới cùng xin service token dù token có thể được reuse.

### 6.4. JWKS stampede

OP rotate signing key, nhiều Pods cùng gặp `kid` mới và tải JWKS.

### 6.5. Metadata discovery storm

Rolling deployment khởi tạo registrations từ issuer metadata cùng lúc.

### 6.6. UserInfo amplification

Nếu flow cần UserInfo, mỗi login có thể thêm HTTP GET mang access token. Phải tính tải này riêng.

## 7. Rate limiting, bulkhead và bounded queue

~~~mermaid
flowchart TD
    D["Login / refresh demand"] --> RL["Rate limiter"]
    RL --> BH["Bulkhead concurrency cap"]
    BH --> Q["Bounded queue"]
    Q --> HP["HTTP pool"]
    HP --> OP["OpenID Provider"]
    RL --> X["Controlled rejection"]
    BH --> X
    Q --> X
~~~

### 7.1. Rate limiter

Giới hạn request rate theo client registration, tenant, IP/session hoặc loại grant. Không dùng policy quá đơn giản khiến callbacks hợp lệ sau MFA bị chặn mà không có UX/retry plan.

### 7.2. Bulkhead

Dành tối đa một số concurrent calls cho OP; khi OP chậm, không làm toàn bộ Portal cạn worker threads.

### 7.3. Bounded queue

Không cho backlog tăng không giới hạn. Khi quá tải, fail nhanh có kiểm soát phù hợp SLO.

### 7.4. Circuit breaker

Khi provider liên tục timeout/5xx, breaker có thể giảm outbound requests và hỗ trợ recovery. Breaker không cho phép tạo OIDC Authentication khi token chưa được xác minh.

### 7.5. Load shedding

Một số chức năng có thể trả 503 hoặc trang đăng nhập tạm unavailable. Không redirect login vô hạn hoặc chấp nhận ID token chưa verify để tăng availability.

## 8. Servlet: Apache HttpClient 5 pooled transport

Với Spring Framework 6.x / Spring Boot 3.x và Apache HttpClient 5, có thể tạo connection pool chung:

~~~xml
<dependency>
    <groupId>org.apache.httpcomponents.client5</groupId>
    <artifactId>httpclient5</artifactId>
</dependency>
~~~

### 8.1. Cấu hình bean

~~~java
import java.time.Duration;

import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io
        .PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;

@Configuration
public class ProviderHttpConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient providerApacheClient() {

        var manager =
                PoolingHttpClientConnectionManagerBuilder
                        .create()
                        .setMaxConnTotal(80)
                        .setMaxConnPerRoute(30)
                        .build();

        var requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(500))
                .setResponseTimeout(
                        Timeout.ofSeconds(4))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(
                        TimeValue.ofSeconds(30))
                .build();
    }

    @Bean
    ClientHttpRequestFactory providerRequestFactory(
            CloseableHttpClient providerApacheClient) {

        var factory =
                new HttpComponentsClientHttpRequestFactory(
                        providerApacheClient);

        factory.setConnectTimeout(
                Duration.ofSeconds(2));

        return factory;
    }
}
~~~

### 8.2. Ý nghĩa

- `maxConnTotal`: giới hạn toàn pool.
- `maxConnPerRoute`: giới hạn tới từng route.
- `connectionRequestTimeout`: chờ connection trong pool.
- `responseTimeout`: đợi response theo Apache HC5 semantics.
- `setConnectTimeout`: thời gian TCP connect.
- `evictIdleConnections`: loại connection rảnh.
- `destroyMethod`: close khi shutdown.

### 8.3. Kiểm tra version

HTTP client/timeouts APIs có thể thay đổi giữa minor versions. Dùng libraries tương thích BOM và integration test xác nhận timeout thực sự áp dụng.

### 8.4. Max idle và max lifetime khác nhau

Idle eviction dựa thời gian rảnh. Max lifetime giới hạn tuổi connection bất kể mức độ sử dụng và có thể cấu hình trên connection manager tùy phiên bản.

### 8.5. Pool không giới hạn RPS

30 connections có thể xử lý hàng trăm requests/giây nếu mỗi request rất nhanh. Cần rate limiter riêng khi OP có quota.

## 9. Wire timeout vào Authorization Code token client

Tạo `RestTemplate` bất kỳ chưa đủ. Đối với Spring Security 6.x hỗ trợ RestTemplate-based implementation, có thể cấu hình `DefaultAuthorizationCodeTokenResponseClient`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.web.client.RestTemplate;

import org.springframework.security.oauth2.client.endpoint
        .DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.http
        .OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter
        .OAuth2AccessTokenResponseHttpMessageConverter;

@Bean
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        authorizationCodeTokenClient(
                ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate(List.of(
            new FormHttpMessageConverter(),
            new OAuth2AccessTokenResponseHttpMessageConverter()));

    rest.setErrorHandler(new OAuth2ErrorResponseErrorHandler());
    rest.setRequestFactory(providerRequestFactory);

    var client =
            new DefaultAuthorizationCodeTokenResponseClient();
    client.setRestOperations(rest);

    return client;
}
~~~

### 9.1. Giữ OAuth2 converters

Token endpoint nhận form POST và trả OAuth token JSON gồm `access_token`, `token_type`, `expires_in` và có thể `refresh_token`.

### 9.2. Giữ OAuth error handler

`invalid_grant`, `invalid_client` và những OAuth errors cần được parse như grant errors, không biến tất cả thành một lỗi HTTP generic.

### 9.3. Cấu hình vào `oauth2Login()`

~~~java
@Bean
SecurityFilterChain portalSecurity(
        HttpSecurity http,
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                tokenClient) throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .tokenEndpoint(endpoint -> endpoint
                            .accessTokenResponseClient(tokenClient)))
            .build();
}
~~~

Các imports cho `HttpSecurity`, `SecurityFilterChain` và `@Bean` dùng từ Spring Security/Spring Context như thông thường.

### 9.4. RestClient-based alternative

Các Spring Security versions mới có `RestClientAuthorizationCodeTokenResponseClient`. Khi chọn implementation đó, cấu hình RestClient request factory và OAuth error handling bằng API tương thích version đang chạy.

### 9.5. Giới hạn của wiring này

Nó áp cho login authorization-code token exchange, **không tự áp** vào refresh token, UserInfo, JWKS hoặc discovery.

## 10. Refresh token client cần cấu hình riêng

~~~java
@Bean
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenClient(
                ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate(List.of(
            new FormHttpMessageConverter(),
            new OAuth2AccessTokenResponseHttpMessageConverter()));

    rest.setErrorHandler(new OAuth2ErrorResponseErrorHandler());
    rest.setRequestFactory(providerRequestFactory);

    var client =
            new DefaultRefreshTokenTokenResponseClient();
    client.setRestOperations(rest);
    return client;
}
~~~

Các imports cho `OAuth2RefreshTokenGrantRequest`, `DefaultRefreshTokenTokenResponseClient` thuộc `org.springframework.security.oauth2.client.endpoint`.

### 10.1. Wire vào authorized client manager

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository repository,
        OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
                refreshTokenClient) {

    var provider = OAuth2AuthorizedClientProviderBuilder
            .builder()
            .authorizationCode()
            .refreshToken(config -> config
                    .accessTokenResponseClient(refreshTokenClient))
            .build();

    var manager =
            new DefaultOAuth2AuthorizedClientManager(
                    registrations, repository);

    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Các lớp manager/builder/repository dùng Spring Security OAuth2 Client packages.

### 10.2. Servlet vs background

`DefaultOAuth2AuthorizedClientManager` hoạt động với Servlet request context. Scheduled jobs nên cân nhắc `AuthorizedClientServiceOAuth2AuthorizedClientManager` và service store.

### 10.3. Không retry refresh POST mù quáng

Refresh token có thể rotate R1 thành R2; response timeout không chứng minh AS chưa xử lý request.

## 11. UserInfo có HTTP transport riêng

`OidcUserService` có thể dùng `DefaultOAuth2UserService` gọi UserInfo theo flow.

~~~java
@Bean
OidcUserService oidcUserService(
        ClientHttpRequestFactory providerRequestFactory) {

    RestTemplate rest = new RestTemplate();
    rest.setRequestFactory(providerRequestFactory);

    var oauth2UserService = new DefaultOAuth2UserService();
    oauth2UserService.setRestOperations(rest);

    var oidc = new OidcUserService();
    oidc.setOauth2UserService(oauth2UserService);

    return oidc;
}
~~~

Tùy project/version cần imports từ `org.springframework.security.oauth2.client.userinfo` và `org.springframework.security.oauth2.client.oidc.userinfo`.

Wire vào login:

~~~java
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(endpoint -> endpoint
                .oidcUserService(oidcUserService)));
~~~

### 11.1. UserInfo không luôn được gọi

Điều này phụ thuộc OIDC scopes, claims, OP metadata và cấu hình.

### 11.2. Không giảm latency bằng cách bỏ claims bắt buộc

Nếu ứng dụng cần UserInfo groups để authorize, không tự gán role hoặc membership khi UserInfo timeout.

### 11.3. UserInfo mang access token

Chỉ gửi Bearer token tới endpoint được trust. Không lấy UserInfo URL từ browser query hoặc tự follow redirects sang host không đáng tin cậy.

### 11.4. Đừng log UserInfo response

UserInfo có thể chứa PII. Hạn chế body/logging và retention.

## 12. Discovery metadata và JWKS

Với issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://login.example.com
~~~

Framework có thể tải metadata để biết authorization/token/JWKS endpoints, tùy version và khởi tạo ClientRegistration.

### 12.1. Discovery ở startup

Nhiều Pods khởi động cùng lúc có thể cùng truy metadata, làm tăng startup latency và provider load.

### 12.2. JWKS cache và signing key rotation

ID token validation cần public signing keys. Khi key `kid` mới xuất hiện, decoder có thể fetch JWKS. Nhiều Pods cùng cache miss tạo stampede.

### 12.3. Không kế thừa token timeout mặc định

Token exchange client và JWKS decoder có thể dùng HTTP transports khác. Xác định integration hook/cache/timeouts theo version thực tế.

### 12.4. Fail closed khi không verify được ID token

Không bỏ signature, issuer hoặc audience validation khi JWKS unavailable.

### 12.5. Chống SSRF

Không cho user gửi issuer/JWKS URL arbitrary để backend tự discovery. Dynamic tenants phải dùng trusted allowlist/approval.

## 13. WebFlux: Reactor Netty connection pool

Một WebClient dùng Reactor Netty có thể được cấu hình:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Bean(destroyMethod = "dispose")
ConnectionProvider oidcConnections() {
    return ConnectionProvider.builder("oidc")
            .maxConnections(40)
            .pendingAcquireMaxCount(100)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .build();
}

@Bean
WebClient oidcWebClient(ConnectionProvider oidcConnections) {
    HttpClient client = HttpClient.create(oidcConnections)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
            .responseTimeout(Duration.ofSeconds(4));

    return WebClient.builder()
            .clientConnector(
                    new ReactorClientHttpConnector(client))
            .build();
}
~~~

### 13.1. `maxConnections`

Giới hạn số connections, không nhất thiết là số concurrent HTTP/2 streams.

### 13.2. `pendingAcquireMaxCount`

Giới hạn số requests chờ connection, tránh backlog vô hạn.

### 13.3. Cấu hình vào Reactive OAuth2 clients

Reactive token clients như `WebClientReactiveAuthorizationCodeTokenResponseClient` và `WebClientReactiveRefreshTokenTokenResponseClient` cần configured WebClient theo API/version và phải được wire vào `ServerHttpSecurity.oauth2Login()` hoặc `ReactiveOAuth2AuthorizedClientManager`.

**Tạo bean WebClient không tự làm các Spring Security OAuth2 flows dùng nó.**

### 13.4. Reactive không đồng nghĩa không cần concurrency limit

Event loops không giữ Servlet threads nhưng pending Monos, connections và memory vẫn có giới hạn.

### 13.5. Kiểm soát flatMap concurrency

~~~java
Flux.fromIterable(tasks)
        .flatMap(task -> invokeProvider(task), 20);
~~~

`invokeProvider` là application-specific reactive operation. Không dùng infinite concurrency khi bulk calling provider.

### 13.6. Không tự `block()` trên event loop

Nếu token client blocking, dùng kiến trúc phù hợp; tránh làm nghẽn Reactor event loop.

## 14. Retry: phải xét semantics của OAuth grant

| Operation | Retry policy |
|---|---|
| Discovery GET | Bounded retry/backoff khi phù hợp |
| JWKS GET | Bounded retry + caching/throttled refresh |
| UserInfo GET | Cân nhắc bounded retry, chỉ đúng host |
| Authorization Code POST | Không blind retry khi outcome unknown |
| Refresh Token POST | Không blind retry, đặc biệt có rotation |
| Client Credentials POST | Bounded retry nếu AS policy cho phép |
| Introspection | Theo AS/Resource Server contract |
| Revocation | Theo AS contract |

### 14.1. Authorization code là single-use

~~~text
Client gửi C1.
AS xử lý C1, cấp token và đánh dấu used.
Response mất.
Client timeout.
Client retry C1 -> có thể invalid_grant.
~~~

Không thể dùng generic POST retry như một GET idempotent.

### 14.2. Refresh token rotation

~~~text
Client gửi R1.
AS cấp A2/R2, vô hiệu R1.
Response mất.
Client timeout, không biết R2.
Client retry R1 -> invalid_grant hoặc reuse detection.
~~~

Không retry R1 vô hạn; có thể phải yêu cầu reauthorization theo policy.

### 14.3. Không retry OAuth logic errors

`invalid_grant`, `invalid_client`, `unauthorized_client` không được sửa bằng exponential backoff đơn thuần.

### 14.4. Bounded retry vẫn cần budget

Đối với GET/discovery, áp max attempts, total time budget và jitter để không khuếch đại provider outage.

### 14.5. Kiểm tra proxy/service mesh retries

Application có thể đã tắt retry, nhưng service mesh lại replay POST token grant. Cần kiểm soát end-to-end network policy.

## 15. Provider 429 và `Retry-After`

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/json

{"error":"temporarily_unavailable"}
~~~

### 15.1. Không retry đồng loạt

500 callbacks cùng đợi đúng 3 giây rồi retry có thể tạo một burst còn lớn hơn.

### 15.2. Backoff với jitter

Ví dụ các lần chờ được phép retry:

~~~text
Lần 1: khoảng 200–400ms
Lần 2: khoảng 500–900ms
Lần 3: khoảng 1200–2000ms
~~~

Kết hợp `Retry-After`, total deadline và grant safety; đây không phải chính sách cố định cho mọi token request.

### 15.3. Phân biệt có thể retry và nên retry

Một GET read-only có thể an toàn về semantics nhưng vẫn nên fail fast khi provider overload nặng.

### 15.4. Không gửi raw provider lỗi ra browser

Thông báo chung và correlation ID; không tiết lộ client secrets hoặc token response.

## 16. Refresh storms và single-flight

Nhiều token cùng expiry có thể khiến AS bị quá tải.

### 16.1. Token reuse

`OAuth2AuthorizedClientManager` có thể dùng lại access token còn hạn; không xin token mới cho mọi outbound API request.

### 16.2. Clock skew

Refresh sớm giảm nguy cơ API 401 nhưng phải giới hạn concurrency. Không dùng access token expired khi OP không sẵn sàng.

### 16.3. Concurrent R1 usage

~~~text
Request A load A1/R1
Request B load A1/R1
A refresh -> A2/R2
B refresh R1 -> invalid_grant
B failure handler có thể xóa nhầm A2/R2
~~~

### 16.4. Strategies

- Single-flight per principal + registration.
- Distributed lock khi nhiều instances.
- Optimistic locking/CAS khi lưu authorized client.
- Failure removal chỉ nếu version vẫn khớp stale record.
- Bounded concurrent refresh.
- Reauthorization policy khi AS đã invalidate R1.

### 16.5. Không mặc định manager atomic trên cả cluster

Spring Security manager điều phối grants/storage, nhưng concurrency đa instance là trách nhiệm kiến trúc/store.

## 17. Client Credentials và startup load

Background jobs có thể cùng xin token khi deploy:

~~~text
Pod A startup -> client_credentials
Pod B startup -> client_credentials
Pod C startup -> client_credentials
~~~

### 17.1. Dùng manager phù hợp non-web

`AuthorizedClientServiceOAuth2AuthorizedClientManager` không cần Servlet request và phù hợp background jobs.

### 17.2. Reuse token

Token service còn hạn nên được cache theo registration/principal/resource policy.

### 17.3. Stagger/jitter

Khi nhiều Pods cùng startup, khởi tạo có jitter giúp tránh đồng loạt token requests/JWKS loads.

### 17.4. Không trộn service và user tokens

Một `client_credentials` token không tự đại diện End-User. Không dùng nó để vượt user ownership/tenant rules ở API.

## 18. Multi-tenant và nhiều providers

### 18.1. Per-provider budgets

Nếu tenant Acme dùng OP A, Globex dùng OP B, việc OP A chậm không nên chiếm toàn bộ pool hoặc worker threads cần cho OP B.

### 18.2. Tenant fairness

Một tenant ồ ạt login có thể chiếm hết shared OP quota. Cân nhắc per-tenant rate/concurrency policies.

### 18.3. Issuer trust không thể bỏ qua

Khi timeout/429, không fallback sang issuer khác không được allowlist.

### 18.4. Token destination isolation

Không gửi access token, refresh token hoặc client secret tới provider endpoint do browser chỉ định.

### 18.5. Pool và cache namespace

Dynamic registration/authorized-client store cần tránh collision giữa issuers, principals, tenants và registration IDs.

## 19. Observability: đo những gì?

### 19.1. HTTP latencies

Theo dõi p50/p95/p99:

- Code token exchange.
- Refresh token exchange.
- Client Credentials token calls.
- UserInfo.
- JWKS/discovery.
- Callback backend processing.

### 19.2. Pool saturation

- Active connections.
- Idle connections.
- Pending acquire count.
- Connection acquisition timeout.
- Connect/response timeout rates.
- Evictions/leaks.
- Per-route usage.

### 19.3. Error categories

~~~text
provider_alias=company-op
registration_id=company
operation=refresh_token
result=failed
category=response_timeout
duration_ms=4080
correlation_id=...
~~~

### 19.4. Không trộn lỗi

`access_denied` do consent/policy khác `invalid_grant`; HTTP 503/429 khác network timeout. Metrics/alerts cần phân loại.

### 19.5. Token request ratios

- Token endpoint calls per login.
- Access-token reuse rate.
- Refresh attempts/success rate.
- `invalid_grant` frequency.
- Circuit breaker open rate.
- Rate limiter rejects.
- Retries per grant.

### 19.6. Bảo vệ dữ liệu metrics

Không dùng raw `sub`, email, `state`, authorization code hoặc token làm metric labels; tránh cardinality và privacy issues.

## 20. Logging và tracing an toàn

Log tối thiểu:

~~~text
event=oidc_token_exchange
registration_id=corporate
grant=authorization_code
result=failed
error_category=pool_acquire_timeout
duration_ms=501
trace_id=...
~~~

Không log:

~~~text
authorization_code
code_verifier
client_secret
access_token
refresh_token
id_token
raw Authorization header
raw session cookie
full callback query string
~~~

### 20.1. HTTP wire logs đặc biệt nguy hiểm

Token POST có secrets trong form/body/headers. Cần redaction, hạn chế access và retention.

### 20.2. Correlation ID khác OAuth state

Đừng dùng raw `state` để trace public vì state là giao thức bảo mật liên quan login correlation.

### 20.3. Tracing theo phase

Tách thời gian chờ pool, token HTTP call, UserInfo và JWKS khi instrumentation hỗ trợ.

## 21. Fail-closed khi provider unavailable

### 21.1. User chưa authenticated

Nếu callback token exchange thất bại hoặc ID token chưa verify, không tạo successful Authentication/session.

### 21.2. User đã có session hợp lệ

Có thể phục vụ chức năng không cần provider call theo session/authorization policy, nhưng không dùng quyền đã bị revoke hoặc expired token tùy ý.

### 21.3. Refresh không được

Nếu access token đã expired và R1 không refresh được, downstream API call cần fail hoặc reauthorization. Không gửi expired token rồi bỏ API checks.

### 21.4. UserInfo fail

Nếu roles/permissions phụ thuộc UserInfo, không tự gán role cao hơn khi thiếu dữ liệu.

### 21.5. JWKS fail

Không bỏ JWT signature/issuer validation. Fail closed.

### 21.6. Circuit breaker open

Thông báo OP tạm unavailable; không redirect login vô hạn.

## 22. Proxy, ingress, service mesh và TLS

Một deployment có thể đi qua:

~~~text
Browser -> Ingress -> Portal -> Mesh/Proxy -> OP
~~~

### 22.1. Align timeouts

Ingress timeout 5 giây nhưng token response timeout 30 giây có thể khiến server giữ resources sau khi browser đã bỏ request.

### 22.2. Proxy retries

Không để mesh tự retry HTTP POST code/refresh với unknown outcome.

### 22.3. DNS/TLS

Connect failure có thể do DNS, truststore, expired certificate, SNI hoặc proxy. Không disable hostname/certificate verification để giải quyết outage.

### 22.4. Connection pool qua proxy

Per-route limit có thể tính theo proxy route thay vì logical OP host. Đo actual transport semantics.

## 23. Kiểm thử timeout bằng fake OP

Fake OP trong test có thể cung cấp:

~~~text
GET  /.well-known/openid-configuration
GET  /jwks
POST /token
GET  /userinfo
~~~

### 23.1. Chậm hơn response timeout

~~~text
Configured response timeout = 500ms
Fake OP token delay = 2s
Expected:
  request fails within bounded budget
  no successful OIDC Authentication
  no authorized client newly saved
  no blind retry of code/refresh POST
~~~

### 23.2. Pool acquire exhaustion

~~~text
max connections = 2
acquire timeout = 200ms
fake OP holds two token requests for 2s
third request must fail/wait bounded
~~~

Assert active/pending metrics và cleanup sau đó, không chỉ HTTP status.

### 23.3. 429

Fake OP trả 429/Retry-After. Kiểm tra classification/backoff nếu operation cho phép retry và tổng số attempts không vượt budget.

### 23.4. JWKS 503

Không chấp nhận ID token chưa verify khi không có public key cần thiết.

### 23.5. UserInfo timeout

Kiểm tra behavior theo authentication/optional claims policy.

### 23.6. Rotation lost response

Fake AS xử lý R1 thành R2 nhưng cố ý mất response. Kiểm tra application không gửi R1 vô hạn.

### 23.7. Recovery

Sau outage, pool active/pending quay về bình thường, breaker half-open rồi closed theo policy và không leak connections.

## 24. Kiểm thử token reuse giảm tải

Với authorized client đã lưu:

~~~text
registration = corporate
principal = alice
access_token = A1
expires_at = 11:00
now = 10:00

100 sequential manager.authorize() calls
Expected:
  A1 reused
  refresh-token HTTP calls = 0
~~~

### 24.1. Test fixed clock

Dùng `Clock.fixed(...)` để tránh flaky test tại expiry boundary.

### 24.2. Kiểm tra token endpoint call count

Đừng nhầm manager/provider invocation với HTTP request. Chỉ khi cần refresh mới gọi token endpoint.

### 24.3. Test lưu A2/R2

Khi fake AS refresh R1 trả A2/R2, assert manager result **và load lại từ authorized client store** đều có token mới.

### 24.4. Concurrency

Dùng threads/latches để mô phỏng hai requests cùng dùng R1. Kiểm tra single-flight/version/CAS không làm mất R2.

## 25. Runbook xử lý login chậm

### Bước 1: Xác định giai đoạn

User đang ở OP login page hay đã quay về callback Portal?

### Bước 2: Xem p95/p99 theo endpoint

Token endpoint, JWKS, UserInfo hay discovery chậm?

### Bước 3: Kiểm tra pool saturation

Active/pending count và acquire timeouts có tăng không?

### Bước 4: Kiểm tra 429/5xx

Có provider rate limit, deployment hoặc autoscale spike không?

### Bước 5: Phân loại grant

Authorization Code, Refresh Token hay Client Credentials? Có retry nguy hiểm không?

### Bước 6: Kiểm tra proxy/mesh

Ingress timeout, service mesh retries, DNS/TLS trust.

### Bước 7: Reproduce trong staging

Dùng fake OP delayed/429/503. Không stress production OP nếu chưa có phê duyệt.

### Bước 8: Điều chỉnh từng biến

Không đồng thời tăng pool, tăng timeout và retries: dễ khuếch đại overload và khó xác định nguyên nhân.

## 26. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Token exchange chậm | OP latency/capacity | Endpoint p99/429 |
| Pool pending queue tăng | Hết connections | Active/idle/leaks |
| Connect timeout | Network, DNS, proxy | Egress/TLS |
| Read timeout | OP xử lý chậm | Response metrics |
| Refresh mỗi request | Token cache/store không reuse | Manager/provider |
| Refresh invalid_grant sau timeout | Rotation race/unknown outcome | Single-flight/CAS |
| JWKS fetch storm | Key rotation/cache miss | Decoder cache |
| UserInfo slow | Timeout HTTP client khác | UserInfo service wiring |
| New Pods login fail | Discovery startup load | Rolling rollout |
| OP 429 sau autoscale | Cluster quota vượt | Global rate limits |
| API 403 nhưng app refresh | Owner/scope denial | Không retry 403 |
| WebFlux pending memory tăng | Unbounded concurrency | ConnectionProvider/flatMap |
| Redirect login loop | Failure handler retry sai | Controlled UX |
| Duplicate code POST | Proxy/client retry | Disable unsafe retries |
| Timeout config không có tác dụng | HTTP client chưa wire đúng | Fake OP test |
| Token trong logs | Wire logging bật | Redaction |

## 27. Những hiểu nhầm phổ biến

**“Connect timeout là tổng HTTP timeout.”** Không, còn pool acquire, TLS, response/read và deadline.

**“Pool càng lớn càng tốt.”** Không. Có thể làm OP overload hơn.

**“Một RestTemplate timeout tự áp cho mọi Spring Security HTTP call.”** Không. Phải wire từng integration point.

**“Authorization endpoint redirect dùng backend token pool.”** Không; browser thường gọi OP authorization endpoint.

**“POST token timeout thì cứ retry.”** Không. Authorization code single-use và refresh token rotation có unknown outcome.

**“R1 timeout luôn có thể retry R1.”** Không. AS có thể đã rotate R1 sang R2.

**“JWKS lỗi thì bỏ signature verification tạm.”** Không. Fail closed.

**“WebFlux không cần pool/queue.”** Không. Resources vẫn hữu hạn.

**“429 có Retry-After thì retry mọi grant.”** Không, phải xét grant semantics và retry budget.

**“Pool 50 nghĩa cả cluster có 50 connections.”** Không; mỗi Pod có pool của riêng mình.

## 28. Tình huống thực hành

### A. Đầu ca có 2.000 callbacks

Provider nhận burst token exchanges.

**Phân tích:** đo OP p99, pool saturation, cluster concurrency, quota; giới hạn bulkhead và bounded queue.

### B. Token còn hạn nhưng refresh liên tục

**Phân tích:** kiểm tra `OAuth2AuthorizedClientManager`/store và token reuse.

### C. R1 timeout rồi bị invalid_grant

**Phân tích:** AS có thể đã rotate; không retry mù quáng, thiết kế reauthorization.

### D. Signing key rotation

**Phân tích:** cache/JWKS fetch stampede; giữ signature verification.

### E. UserInfo chậm dù token client timeout thấp

**Phân tích:** phải configure UserInfo HTTP client.

### F. Tenant A chiếm toàn bộ quota

**Phân tích:** per-tenant rate/concurrency fairness.

### G. Service mesh retry POST

**Phân tích:** mesh policy có thể nhân đôi grant requests.

### H. WebFlux memory tăng

**Phân tích:** bounded pool acquire, concurrency và cancellation.

### I. Token endpoint 429 sau scale-out

**Phân tích:** tổng quota cluster, jitter/RateLimiter.

### J. Ingress timeout trước backend

**Phân tích:** align deadlines; không giữ Servlet threads quá lâu.

## 29. Câu hỏi tự kiểm tra

**1. Authorization endpoint được browser hay backend gọi?** Thường browser theo redirect.

**2. Token endpoint được gọi khi nào?** Code exchange, refresh hoặc grant khác.

**3. Connect timeout có giới hạn toàn bộ request không?** Không.

**4. Pool acquire timeout là gì?** Giới hạn chờ free connection.

**5. Vì sao giới hạn pending queue?** Tránh backlog/threads/memory tăng vô hạn.

**6. Tăng pool có làm 429 tăng không?** Có thể.

**7. Vì sao tính quota toàn cluster?** Vì mỗi replica có pool riêng.

**8. Token còn hạn có cần refresh mỗi request không?** Không.

**9. Có nên blind retry code grant POST?** Không.

**10. R1 timeout có thể đã bị AS rotate không?** Có.

**11. JWKS unavailable có thể bỏ signature validation?** Không.

**12. Một RestTemplate bean tự dùng ở mọi OAuth calls?** Không.

**13. WebFlux có cần ConnectionProvider bounded?** Có.

**14. HTTP 429 xử lý thế nào?** Giảm tải, bounded backoff/jitter theo operation.

**15. `invalid_grant` và response timeout có giống nhau không?** Không.

**16. Metric nào phản ánh pool saturation?** Active/pending connections, acquire timeouts.

**17. Có log refresh token để debug không?** Không.

**18. UserInfo timeout có tự lấy từ token client không?** Không chắc, cần wire riêng.

**19. Non-web job nên dùng manager nào?** Thường `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**20. OP outage có được tạo session OIDC chưa verify?** Không.

## Ghi nhớ

- **OAuth2/OIDC Client gọi nhiều endpoints**: token, refresh, UserInfo, JWKS và discovery; browser authorization redirect là phần khác.
- **Pool acquire, connect, response/read và overall deadlines là các giới hạn khác nhau**, cần đặt theo SLO thực.
- **Connection pools cần max total/per-route, bounded pending, idle/lifetime policies**, và tổng quotas toàn cluster.
- **HTTP client được cấu hình timeout phải được wire đúng vào Spring Security token, refresh, UserInfo và JWKS/discovery components**, không chỉ tạo một bean.
- **Không blind retry authorization code hay rotating refresh token POST** sau timeout; AS có thể đã consume code hoặc rotate R1 sang R2.
- **Rate limiting, bulkhead, circuit breaker, jitter và load shedding cần đi cùng nhau** mà không bỏ OAuth/OIDC validation.
- **Token reuse, single-flight refresh, JWKS caching và rollout phân đợt giảm provider load**, nhưng không cho phép expired/unverified tokens.
- **WebFlux cũng cần bounded pool và concurrency**, dù không blocking như Servlet.
- **Metrics phải đo p95/p99, pool saturation, 429/5xx, refresh errors và request counts**, không log credentials.
- **Fake OP/load tests phải xác minh timeout enforcement, fail-closed và recovery**, không stress OP production tùy tiện.
