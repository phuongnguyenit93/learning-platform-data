# WebClient, timeout, hủy yêu cầu và giới hạn số kết nối

Trong **Spring Security OAuth 2.0/OIDC Resource Server dùng WebFlux**, nếu API nhận opaque access token, Resource Server thường gọi **OAuth 2.0 Token Introspection Endpoint** của Authorization Server để kiểm tra token còn hoạt động và lấy các thuộc tính như **sub**, **scope**, **client_id**, **aud**. Với Spring Security reactive, giao diện trung tâm là **ReactiveOpaqueTokenIntrospector**, còn việc gửi HTTP có thể dùng **WebClient** kết hợp **Reactor Netty**.

Điều đáng chú ý là introspection nằm **trên đường đi xác thực của mỗi request**. Khi Authorization Server chậm, một request tới API có thể phải chờ trước cả khi controller bắt đầu xử lý. Sử dụng WebClient nonblocking giúp tránh giữ một Java thread chờ I/O cho mỗi request, nhưng **không loại bỏ giới hạn về sockets, connection pool, pending queue, độ trễ hoặc sức chịu tải của Authorization Server**.

Bài học trả lời bốn câu hỏi liên quan chặt chẽ:

1. **WebClient** tham gia vào luồng introspection phản ứng như thế nào, và nên tùy biến ở đâu?
2. Cần phân biệt **timeout khi chờ connection pool, connect TCP, TLS, nhận response và toàn bộ publisher** ra sao?
3. Khi caller ngắt kết nối hoặc **Mono.timeout** xảy ra, **cancellation** có ý nghĩa gì và không bảo đảm điều gì?
4. Cấu hình **maxConnections**, **pendingAcquireMaxCount**, **pendingAcquireTimeout** thế nào để tránh hàng đợi vô hạn, quá tải và fail-open?

Mục tiêu là một **Resource Server giữ được ranh giới xác thực khi quá tải**: nếu token chưa được xác minh thành công, API không được tự tạo Authentication hợp lệ chỉ để tránh lỗi.

## 1. Vì sao introspection ảnh hưởng trực tiếp tới latency của API?

Client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer example-opaque-access-token
~~~

Trong WebFlux, đường đi logic có thể là:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant W as WebClient / Reactor Netty
    participant A as Authorization Server

    C->>R: Authorization Bearer token
    R->>I: introspect(token)
    I->>W: HTTP POST introspection
    W->>A: token + introspection client credentials
    A-->>W: active=true và metadata
    W-->>I: Response được decode
    I-->>R: Mono OAuth2AuthenticatedPrincipal
    R->>R: Tạo Authentication; kiểm scope, tenant
    R-->>C: Response hợp lệ hoặc lỗi
~~~

**ReactiveOpaqueTokenIntrospector** trả về:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Đây là **Publisher**, không phải kết quả đồng bộ. Spring Security subscribe và compose nó với authentication flow, sau đó mới kiểm authorization.

Các trường hợp cần phân biệt:

- **active=true** từ một AS đáng tin cậy: token có thể được chấp nhận, tiếp tục kiểm scope/audience/tenant.
- **active=false**: token không hoạt động, authentication bị từ chối.
- **AS không phản hồi**: chưa xác minh được token; đây là lỗi timeout/hạ tầng, **không đồng nghĩa active=true**.
- **AS trả lỗi 401 cho introspection client**: có thể sai client credentials hoặc policy gọi introspection; không phải chứng minh Bearer token đã được xác thực.
- **Token active nhưng thiếu scope**: authentication thành công, authorization vẫn có thể trả 403.

### 1.1. Tính nonblocking không tạo năng lực vô hạn

Giả sử Orders API nhận **600 requests/giây** và mỗi request cần một lượt introspection không cache. Authorization Server có thể phải xử lý gần 600 POST introspection mỗi giây chỉ từ API này.

Nếu thời gian mỗi lượt là 200 ms, số outbound requests đồng thời có thể được ước lượng bằng:

~~~text
Concurrent requests ≈ 600 request/s × 0.2 s = 120
~~~

Đây là **ước lượng Little's Law**, chưa tính peak, p99 latency, HTTP protocol, retries và replicas. Nó không tự xác định số connection phải mở.

WebClient giúp không block event-loop threads trong lúc chờ network, nhưng lượng request đang chờ vẫn tiêu thụ trạng thái, buffers, pool slots và khả năng xử lý của upstream.

## 2. Các thành phần liên quan trong WebFlux

| Thành phần | Trách nhiệm |
|---|---|
| **SecurityWebFilterChain** | Bảo vệ request ở Reactive WebFlux |
| **AuthenticationWebFilter** | Chuyển Bearer token thành yêu cầu authentication |
| **OpaqueTokenReactiveAuthenticationManager** | Xác thực opaque token bằng introspector |
| **ReactiveOpaqueTokenIntrospector** | Hợp đồng introspection, trả Mono của principal |
| **SpringReactiveOpaqueTokenIntrospector** | Implementation gọi endpoint introspection |
| **WebClient** | HTTP client nonblocking |
| **ReactorClientHttpConnector** | Nối WebClient với Reactor Netty |
| **HttpClient** của Reactor Netty | Cấu hình network, response timeout, TLS |
| **ConnectionProvider** | Pool active/idle connections và pending acquisition queue |
| **Mono.timeout** | Giới hạn thời gian ở phạm vi publisher |
| **ReactiveSecurityContextHolder** | Truyền ngữ cảnh security trong Reactor |
| **ServerAuthenticationEntryPoint** | Tạo challenge khi request không có authentication hợp lệ |

**Đừng nhầm** WebFlux **ReactiveOpaqueTokenIntrospector** với Servlet **OpaqueTokenIntrospector**, hay dùng blocking RestClient trong reactive event loop.

### 2.1. SpringReactiveOpaqueTokenIntrospector mặc định

Một cấu hình Spring Security hiện đại có thể tạo introspector bằng builder:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            "https://login.example.com/oauth2/introspect")
        .clientId("orders-resource-server")
        .clientSecret("placeholder-not-real-secret")
        .build();
~~~

Builder có trong các phiên bản Spring Security phù hợp, chẳng hạn từ 6.5. Secret thật phải lấy từ nguồn được bảo vệ; **không commit vào source**.

Khi cần điều khiển connection pool, timeout và các cấu hình HTTP riêng, có thể cung cấp một **WebClient đã cấu hình sẵn** cho implementation qua constructor/API mà phiên bản đang chạy hỗ trợ.

## 3. WebClient gửi gì tới Authorization Server?

Theo RFC 7662, introspection request thường là POST:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-resource-server-credentials>

token=<access-token>&token_type_hint=access_token
~~~

Các giá trị trong dấu ngoặc là placeholders. **Client credentials dùng gọi introspection** không phải token mà người dùng gửi tới Orders API.

Một response thành công về token active:

~~~json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Một response về token không còn hoạt động:

~~~json
{
  "active": false
}
~~~

**HTTP 200 của introspection endpoint không đồng nghĩa active=true**, vì RFC 7662 có thể dùng HTTP 200 để trả active=false. Đừng tự viết custom WebClient code kiểm duy nhất response status rồi cấp Authentication.

Introspection URI phải là **một endpoint tin cậy được hệ thống cấu hình**, không lấy từ request parameter, token chưa xác minh hoặc một URL do client tùy ý chỉ định. Nếu không, có thể gây SSRF và lộ token/client secret.

## 4. Các lớp timeout không được trộn lẫn

Một lượt introspection trải qua nhiều bước:

~~~mermaid
flowchart LR
    S[Subscribe Mono] --> P[Chờ connection pool]
    P --> D[DNS resolution]
    D --> T[TCP connect]
    T --> L[TLS handshake]
    L --> Q[Gửi request]
    Q --> R[Chờ / đọc HTTP response]
    R --> J[Decode và map principal]
    J --> F[Authentication result]
~~~

| Timeout | Bảo vệ điều gì? | Thành phần |
|---|---|---|
| **Pending acquire** | Chờ pool cấp connection quá lâu | ConnectionProvider.pendingAcquireTimeout |
| **TCP connect** | Thiết lập socket tới AS chậm | ChannelOption.CONNECT_TIMEOUT_MILLIS |
| **DNS** | Tra cứu tên host chậm | Reactor Netty name resolver configuration |
| **TLS handshake** | Thương lượng TLS không hoàn tất | SSL/TLS provider timeout |
| **Response timeout** | HTTP response bị chậm khi đợi/đọc | HttpClient.responseTimeout |
| **Whole operation** | Tổng thời gian introspection publisher | Mono.timeout(Duration) |
| **Inbound deadline** | Request API còn được caller/gateway chờ bao lâu | Gateway/application policy |

### 4.1. pendingAcquireTimeout

Khi không còn connection có thể dùng và đã đạt **maxConnections**, request có thể đi vào **pending acquire queue**.

~~~java
ConnectionProvider.builder("auth-introspection")
    .pendingAcquireTimeout(Duration.ofMillis(150))
    .build();
~~~

Nếu quá 150 ms chưa được cấp connection, operation sẽ thất bại ở bước lấy connection. Nó có thể **chưa gửi bất kỳ HTTP POST nào tới AS**.

Đừng để pending acquire timeout dài hơn toàn ngân sách của API request, vì khi được cấp connection thì client có thể đã hủy từ lâu.

### 4.2. TCP connect timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800);
~~~

Đây là thời gian thiết lập **TCP connection mới**, không phải timeout cho cả HTTP round trip. Nếu pool có một keep-alive connection còn dùng được, request có thể bỏ qua bước connect mới.

### 4.3. Response timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofMillis(1500));
~~~

Reactor Netty cho phép đặt response timeout mặc định cho HttpClient hoặc override ở request cụ thể. Response timeout **không thay thế** thời gian chờ pool, DNS, connect hoặc tổng deadline.

### 4.4. Overall timeout của Mono

~~~java
return delegate.introspect(token)
    .timeout(Duration.ofMillis(2500));
~~~

Operator **Mono.timeout** giới hạn khoảng từ khi publisher được subscribe tới khi có tín hiệu phù hợp theo semantics Reactor. Khi quá hạn, nó phát **TimeoutException** và yêu cầu hủy upstream subscription.

Khi đặt ngay ngoài toàn bộ **delegate.introspect(token)**, nó có thể bao phủ cả chờ pool, network và response decode. Tuy vậy, cần hiểu publisher được compose, vị trí operator, hoạt động ngoài pipeline và retry/cache có thể thay đổi phạm vi thực tế.

**TimeoutException không chứng minh token bị thu hồi hoặc không hợp lệ.** Đây là lỗi chưa hoàn tất xác minh đúng hạn.

## 5. Ví dụ tính ngân sách thời gian

Giả sử API có ngân sách phản hồi khoảng **4 giây**, còn logic nghiệp vụ và serialization cần một phần đáng kể. Có thể đặt một ngân sách introspection **2,5 giây**.

| Khâu | Giá trị ví dụ |
|---|---:|
| Chờ pool | 150 ms |
| TCP connect | 800 ms |
| Chờ response | 1.500 ms |
| Overall introspection | 2.500 ms |
| Inbound API budget | 4.000 ms |

Đây là **con số minh họa**, không phải khuyến nghị universal cho production.

Các timeout riêng **không cộng tuyến tính** thành một giới hạn cuối cùng, bởi overall timeout bao trùm nhiều giai đoạn. DNS, TLS, queueing và business logic cũng cần được đưa vào end-to-end budget.

Nếu gateway đã cắt kết nối sau 2 giây nhưng Resource Server vẫn chờ introspection 10 giây, tài nguyên có thể tiếp tục bị tiêu tốn trừ khi cancellation được truyền đúng và bên client/transport xử lý kịp.

## 6. ConnectionProvider: tối đa connection và pending queue

**ConnectionProvider** quản lý pooling cho Reactor Netty. Các lựa chọn thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| **maxConnections** | Giới hạn active connections của pool |
| **pendingAcquireMaxCount** | Số lần acquire được chờ thêm |
| **pendingAcquireTimeout** | Thời hạn chờ acquire |
| **maxIdleTime** | Connection idle bao lâu thì đủ điều kiện loại |
| **maxLifeTime** | Tuổi đời tối đa của connection |
| **metrics(true)** | Bật pool metrics qua Micrometer nếu tích hợp |
| **dispose()** | Giải phóng pool do ứng dụng sở hữu |

Ví dụ:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("auth-introspection")
        .maxConnections(32)
        .pendingAcquireMaxCount(64)
        .pendingAcquireTimeout(Duration.ofMillis(150))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(2))
        .metrics(true)
        .build();
~~~

Khi dùng HTTP/1.1 và một remote host, số connection đang active trong pool bị giới hạn tương ứng; requests vượt khả năng xử lý có thể chờ trong pending queue rồi bị timeout hoặc bị từ chối khi queue đầy.

### 6.1. maxConnections không phải giới hạn QPS

Với **maxConnections=32**, bạn không được suy ra API chỉ xử lý tối đa **32 requests/giây**. Một connection có thể được reuse nhiều lần; tốc độ xử lý phụ thuộc latency, keep-alive, pipelining/protocol và capacity upstream.

HTTP/2 có thể cho nhiều streams trên một connection, nên số concurrent requests và số connections không luôn tương đương.

### 6.2. Pool limit không phải giới hạn toàn cụm

Nếu có bốn replicas, mỗi replica dùng pool 32 connections tới cùng AS, tổng connections toàn cụm có thể lớn hơn 32 nhiều lần. Một pool thường được quản lý theo remote destination/provider; không nên xem maxConnections của một process là **global concurrency limit** của toàn hệ thống.

Cần phối hợp với rate limit, load balancing, capacity của AS và số replicas.

### 6.3. Hàng đợi vô hạn gây điều gì?

Nếu queue vô hạn, một đợt traffic tăng có thể tạo nhiều request đang chờ dù client đã hết kiên nhẫn. Hệ thống tiêu tốn bộ nhớ, latency và tài nguyên tracing.

Cấu hình **pendingAcquireMaxCount hữu hạn** giúp quá tải trở thành lỗi có thể quan sát. **pendingAcquireTimeout ngắn** giúp tránh giữ công việc khi ngân sách của request đã hết.

Không “chữa” timeout bằng cách tăng maxConnections/queue vô hạn. Một AS đã quá tải có thể càng chậm khi nhận thêm thousands concurrent connections.

## 7. Cấu hình Spring Boot/WebFlux với WebClient riêng cho introspection

Ví dụ sau có bốn lớp:

1. Bean **ConnectionProvider** dùng riêng cho AS.
2. **HttpClient** thiết lập TCP/response timeout.
3. Singleton **WebClient** có credentials introspection.
4. **SpringReactiveOpaqueTokenIntrospector** sử dụng WebClient và overall timeout.

Các ví dụ dùng API Spring Security hiện đại có constructor **SpringReactiveOpaqueTokenIntrospector(String, WebClient)**. Cần đối chiếu API thực tế nếu dự án đang dùng release line cũ.

### 7.1. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: example-inject-via-secret-manager
~~~

**Không sử dụng literal client secret thật trong Git.** Hãy nạp từ secret manager hoặc environment được bảo vệ. Đoạn trên chỉ minh họa tên properties.

### 7.2. Java configuration đầy đủ

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
@EnableWebFluxSecurity
public class ReactiveIntrospectionConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider introspectionConnectionProvider() {
        return ConnectionProvider.builder("auth-introspection")
            .maxConnections(32)
            .pendingAcquireMaxCount(64)
            .pendingAcquireTimeout(Duration.ofMillis(150))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(2))
            .metrics(true)
            .build();
    }

    @Bean("introspectionWebClient")
    WebClient introspectionWebClient(
            ConnectionProvider introspectionConnectionProvider,
            Environment environment) {

        HttpClient httpClient = HttpClient
            .create(introspectionConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 800)
            .responseTimeout(Duration.ofMillis(1500));

        String clientId = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.client-id");
        String clientSecret = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.client-secret");

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .defaultHeaders(headers ->
                headers.setBasicAuth(clientId, clientSecret))
            .codecs(codecs ->
                codecs.defaultCodecs().maxInMemorySize(64 * 1024))
            .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Qualifier("introspectionWebClient") WebClient webClient,
            Environment environment) {

        String uri = environment.getRequiredProperty(
            "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri");

        ReactiveOpaqueTokenIntrospector delegate =
            new SpringReactiveOpaqueTokenIntrospector(uri, webClient);

        return token -> delegate.introspect(token)
            .timeout(Duration.ofMillis(2500));
    }

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange()
                    .authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

### 7.3. Giải thích những quyết định trong ví dụ

**Pool riêng:** tên auth-introspection cho phép theo dõi kết nối đi tới AS riêng với payment/reporting/notification HTTP clients.

**Basic authentication:** WebClient dùng **setBasicAuth(clientId, clientSecret)** cho những request introspection được thực hiện qua client chuyên biệt này. **Không tái sử dụng WebClient đã gắn default Basic credentials cho URI do người dùng cung cấp**.

**Transport timeout:** Reactor Netty HttpClient đặt connect và response timeout. Điều này không tự tạo overall deadline cho mọi thứ.

**Response size limit:** introspection JSON thường nhỏ. **64 KiB** là ví dụ giới hạn buffer, cần điều chỉnh theo contract thật. Nếu upstream trả body khổng lồ, client nên từ chối/ghi lỗi chứ không tiêu thụ vô hạn.

**Overall timeout:** decorator quanh Mono giúp chặn thời gian chờ kéo dài, bao gồm trường hợp bị kẹt ở những bước chưa bị timeout chuyên biệt giới hạn.

**Spring bean lifecycle:** pool dùng **destroyMethod="dispose"**, được giải phóng khi ApplicationContext đóng. Không dispose sau từng request.

**Version caveat:** builder/constructor của SpringReactiveOpaqueTokenIntrospector và một số API Reactor Netty thay đổi theo Spring Security/Boot release line. Với Spring Security hiện đại, constructor nhận WebClient có tài liệu API; với phiên bản cũ, tra đúng Javadoc và không ghép khác major versions.

### 7.4. Vì sao không đặt client secret trực tiếp trong source?

Introspection credentials cho phép Resource Server tự chứng minh quyền hỏi trạng thái token tại AS. Nếu bị lộ, attacker có thể lạm dụng introspection endpoint tùy AS policy.

Không ghi raw **Authorization: Basic**, client secret hoặc Bearer token vào logs. Bảo vệ chúng bằng secret manager, rotate và giới hạn quyền gọi introspection của client chỉ cho resources cần thiết.

### 7.5. WebClient riêng không nhất thiết có event-loop threads riêng

Một custom ConnectionProvider không có nghĩa tự tạo một Reactor Netty event-loop group riêng. Theo Spring Framework, HttpClient mặc định dùng Reactor Netty shared resources. Thường nên dùng shared event loops hợp lý, trừ khi có lý do rõ ràng để tách resource lifecycle.

Nếu chủ động cấu hình non-global resources, ứng dụng phải quản lý việc shutdown; đừng dispose tài nguyên global đang dùng bởi server và các clients khác.

## 8. Vòng đời của pool: dùng lại, không tạo mỗi request

Một anti-pattern:

~~~java
// SAI: tạo client/pool mới trong mỗi lượt introspection.
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    ConnectionProvider pool =
        ConnectionProvider.builder("temporary-pool").build();
    // Tạo WebClient và bỏ quên pool khi return...
    throw new UnsupportedOperationException("Anti-pattern");
}
~~~

Nếu tạo một pool mới cho mỗi request, không thể tận dụng keep-alive, tăng số sockets/handshakes và có thể leak resources.

Cách đúng là **singleton WebClient/ConnectionProvider** được khởi tạo qua DI và tái sử dụng:

~~~text
Application starts
   -> tạo ConnectionProvider
   -> tạo HttpClient
   -> tạo WebClient
   -> tạo ReactiveOpaqueTokenIntrospector

Mỗi request
   -> subscribe introspect(token)
   -> mượn connection từ pool
   -> gửi/nhận HTTP
   -> release connection nếu còn dùng được

Application stops
   -> dispose custom ConnectionProvider
~~~

**Không gọi dispose() trong doFinally của mỗi request.** Pool được chia sẻ; dừng pool khi còn request khác sẽ tạo lỗi hàng loạt.

## 9. Cancellation trong Reactor là tín hiệu gì?

Trong Reactive Streams, **cancel()** do subscriber gửi để thông báo **không cần nhận thêm dữ liệu từ upstream**. Nó khác với Publisher hoàn tất bình thường hoặc phát lỗi.

| Tín hiệu | Ý nghĩa |
|---|---|
| **onComplete** | Dòng xử lý kết thúc bình thường |
| **onError** | Publisher kết thúc bằng lỗi |
| **cancel** | Subscriber không còn muốn nhận tín hiệu |
| **Mono.timeout** | Có thể cancel upstream rồi phát TimeoutException downstream |

Một request WebFlux có thể tạo pipeline:

~~~text
Inbound request
 -> SecurityWebFilterChain
 -> OpaqueTokenReactiveAuthenticationManager
 -> ReactiveOpaqueTokenIntrospector
 -> WebClient
 -> Reactor Netty outbound connection
~~~

Nếu client đóng kết nối hoặc một operator yêu cầu cancel, tín hiệu **có thể lan upstream** trong một pipeline được compose đúng.

### 9.1. Những nguyên nhân cancellation

- Browser đổi trang hoặc client dừng request.
- API Gateway hết deadline và ngắt kết nối.
- **Mono.timeout** của introspection.
- Reactive operator chọn kết quả khác hoặc dừng đợi.
- Test chủ động gọi cancel.
- Application code hủy Subscription.

Tuy nhiên, một disconnect không bảo đảm bạn sẽ thấy cancellation ngay ở mọi vị trí. Kết quả phụ thuộc cách server connector, streaming và operators nối nhau.

### 9.2. Cancel không bảo đảm Authorization Server dừng xử lý

Giả sử WebClient đã gửi xong HTTP POST introspection. Khi Resource Server cancel, transport có thể đóng request/channel hoặc hủy một stream, nhưng **AS đã nhận request vẫn có thể tiếp tục tra token và trả kết quả**.

Với HTTP/2, hủy stream không nhất thiết đóng toàn bộ TCP connection. Với HTTP/1.1, một connection đang có response dang dở có thể không được reuse an toàn và bị đóng; chi tiết phụ thuộc client/transport.

**Không xem cancel là bằng chứng đã tiết kiệm toàn bộ CPU/database work phía AS**. Muốn bảo vệ AS, vẫn cần pool bounds, rate limiting, retries có kiểm soát và timeout ở upstream.

### 9.3. Cancellation khi còn ở pending queue

Nếu request đang chờ mượn connection và chưa gửi HTTP, cancellation có thể khiến nó rời khỏi pending queue. Đây là lợi ích quan trọng của reactive cancellation, nhưng cần kiểm qua transport integration tests và không suy ra toàn bộ trạng thái từ một metric duy nhất.

## 10. Đặt doFinally/doOnCancel ở đâu để quan sát đúng?

Một decorator có thể đo signal kết thúc mà không log token:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

class ObservedIntrospector implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    ObservedIntrospector(ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .doFinally(upstreamSignal ->
                recordSignal("upstream", upstreamSignal))
            .timeout(Duration.ofSeconds(3))
            .doOnError(error ->
                recordErrorType(error.getClass().getSimpleName()))
            .doFinally(outerSignal ->
                recordSignal("outer", outerSignal));
    }

    private void recordSignal(String stage, SignalType signal) {
        // Tích hợp metric/log an toàn; KHÔNG đưa raw token vào tag.
    }

    private void recordErrorType(String errorClass) {
        // Ghi tên loại lỗi đã sanitize, không ghi credentials.
    }
}
~~~

Vì vị trí operator khác nhau, một lần **overall timeout** có thể được nhìn như:

~~~text
Mono bên trong timeout: doFinally(CANCEL)
Mono bên ngoài timeout: doFinally(ON_ERROR)
~~~

Cùng một lần timeout có thể xuất hiện hai loại tín hiệu ở **hai điểm quan sát khác nhau**. Không cộng chúng thành hai sự cố độc lập mà không có correlation ID.

### 10.1. Không tự subscribe bên trong introspector

~~~java
// SAI: tách HTTP request khỏi lifecycle xác thực.
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    delegate.introspect(token)
        .subscribe(principal -> writeToCache(principal));
    return Mono.empty();
}
~~~

Sai vì caller không nhận đúng kết quả, lỗi có thể bị nuốt và cancellation không được truyền như mong muốn.

Dùng composition:

~~~java
return delegate.introspect(token)
    .map(principal -> validateAndMap(principal));
~~~

Trong ví dụ này, **validateAndMap** phải kiểm metadata/authorities theo hợp đồng đáng tin cậy và không tự tạo principal từ raw token.

### 10.2. Không gọi block() trên reactive event loop

~~~java
// SAI trong pipeline WebFlux.
OAuth2AuthenticatedPrincipal principal =
    delegate.introspect(token).block();
~~~

Một blocking call trong event loop có thể làm chậm các requests không liên quan và đôi khi bị Reactor từ chối. Ưu tiên Mono/Flux composition và HTTP client nonblocking.

Nếu bắt buộc tích hợp thư viện blocking, cần một adapter và bounded scheduler/bulkhead phù hợp; nhưng **không sử dụng blocking introspection client** chỉ vì muốn có kết quả đồng bộ.

## 11. Connection pool không thay thế backpressure toàn ứng dụng

ConnectionProvider hạn chế connections và hàng đợi lấy connection, nhưng nó không tự giới hạn:

- Tổng inbound HTTP requests.
- Số Mono instances đang đợi authentication.
- Số replicas đồng thời gọi cùng AS.
- Mức tải từ các ứng dụng khác.
- Số retries phát sinh.
- Memory/CPU dành cho decoding/authorization.

Để thiết kế giới hạn hoàn chỉnh, kết hợp:

1. **Gateway rate limit**, đặc biệt với traffic unauthenticated.
2. **Bounded concurrency/bulkhead** tại resource server khi cần.
3. **Pool active/pending bounds**.
4. **Short pending acquire timeout**.
5. **Overall introspection deadline**.
6. **Circuit breaker** và retry policy đúng loại lỗi.
7. Monitoring saturation và capacity của AS.

### 11.1. Khi pending queue đầy

~~~mermaid
flowchart TD
    R[Inbound Bearer request] --> P{Có connection sẵn hoặc được tạo?}
    P -->|Có| A[POST introspection]
    P -->|Không| Q{Pending queue còn chỗ?}
    Q -->|Có| W[Chờ pendingAcquireTimeout]
    Q -->|Không| E[Pool acquisition bị từ chối]
    W -->|Được cấp kịp| A
    W -->|Quá hạn| T[Pool acquire timeout]
    A --> O[active true/false hoặc lỗi AS]
    E --> F[Không tạo Authentication; ghi nhận overload]
    T --> F
~~~

**Không coi pool acquisition failure như token invalid**, vì request có thể chưa gửi đi. Nhưng đồng thời **không được xác thực thành công** khi không có introspection result.

### 11.2. Tải bất thường từ token giả

Một attacker có thể gửi nhiều chuỗi Bearer ngẫu nhiên để Resource Server liên tục gọi AS. Rate limiting phải được thiết kế từ những tín hiệu đáng tin ở biên (IP/network, connection, gateway, client registration nếu đã xác thực), **không tin sub/scope do token chưa xác minh tự khai**.

## 12. Retry và timeout có thể tự gây bão tải

Retry có thể hợp lý khi lỗi mạng thoáng qua, nhưng **retry mọi exception trong introspection là nguy hiểm**.

| Kết quả/lỗi | Retry mặc định? |
|---|---|
| active=false, token invalid | **Không** |
| Token hết hạn hoặc bị thu hồi | **Không** |
| HTTP 401/403 tại introspection endpoint do client credentials sai | **Không**, sửa cấu hình |
| Claim/audience không phù hợp | **Không** |
| Malformed token request | **Không** |
| Temporary TCP failure/timeout | Có thể có retry rất hạn chế |
| AS 502/503/504 | Có thể theo chính sách, tránh khuếch đại tải |
| Pool exhausted | Không retry tức thì vô hạn |
| Client đã hủy request | Không có ý nghĩa retry cho request đó |

Nếu retry 3 lần và mỗi attempt timeout 2 giây, tổng thời gian có thể vượt budget của API. Vì vậy:

- Giới hạn số lần.
- Chọn đúng loại lỗi transport/upstream.
- Có backoff/jitter nếu hợp lý.
- Đặt overall timeout **bao quanh cả retries**.
- Không tự retry **active=false**.
- Không log raw token trong retry hooks.
- Có circuit breaker và rate limit bảo vệ AS.

**Retry không biến token giả thành token thật.**

## 13. Circuit breaker nhưng không fail-open

Khi AS chậm/không sẵn sàng, circuit breaker có thể giúp giảm lượng request outbound. Tuy nhiên:

~~~text
Circuit open / AS unavailable
 -> Không có introspection result đáng tin
 -> Không tạo authenticated principal
 -> Phản hồi lỗi theo policy
~~~

Không dùng:

~~~java
// SAI: giả định token hợp lệ khi introspection lỗi.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(fakeAdminPrincipal));
~~~

Lỗi mạng không phải sự ủy quyền. Nếu có chính sách cache cho những token đã được xác thực trước đó, phải quy định rõ TTL, revocation lag, key protection và điều kiện dùng cache trong outage.

## 14. Cache giúp giảm tải nhưng thay đổi khả năng thu hồi token

Một lợi ích của introspection là AS có thể thay đổi kết quả token thành **active=false** ngay sau revocation.

Không cache:

~~~text
Request 1 -> AS active=true -> xác thực
Token bị revoke
Request 2 -> AS active=false -> từ chối
~~~

Cache active=true trong 5 phút:

~~~text
Request 1 -> AS active=true -> lưu cache
Token bị revoke
Request 2 -> cache active=true -> có thể vẫn chấp nhận
Cache hết hạn
Request 3 -> AS active=false -> từ chối
~~~

Do đó cache không chỉ là tối ưu performance; nó **thay đổi security semantics**. Cần xác định:

- Revocation latency tối đa được chấp nhận.
- TTL không vượt token expiration.
- Token dành cho thao tác nhạy cảm hay không.
- Có cơ chế invalidation đồng bộ từ AS không.
- Cache có phân biệt issuer/audience/resource/tenant đúng không.
- Cache key/raw token và metadata được bảo vệ ra sao.

### 14.1. Cache cũng ảnh hưởng cancellation

Một shared/cached Mono có thể còn subscription khác khi một caller hủy. Khi đó upstream HTTP request vẫn có lý do tiếp tục, thậm chí nếu caller đầu tiên đã rời đi.

Vì vậy không đoán cancellation behavior nếu dùng **cache()**, **share()** hoặc request deduplication; phải test chính xác composition và TTL.

## 15. Metrics cần có khi triển khai

Theo Reactor Netty, pool metrics có thể được xuất qua Micrometer, ví dụ:

~~~text
reactor.netty.connection.provider.total.connections
reactor.netty.connection.provider.active.connections
reactor.netty.connection.provider.idle.connections
reactor.netty.connection.provider.pending.connections
reactor.netty.connection.provider.max.connections
reactor.netty.connection.provider.pending.connections.time
reactor.netty.connection.provider.max.pending.connections
~~~

Tên/tag thực tế phụ thuộc version và integration. Nên có **pool name ổn định** và metric theo outcome của introspection.

| Metric ứng dụng | Ý nghĩa |
|---|---|
| **introspection.duration** | Độ trễ toàn bộ publisher |
| **introspection.valid** | AS chấp nhận token |
| **introspection.invalid_token** | AS từ chối token |
| **introspection.timeout** | Timeout riêng từng lớp nếu phân biệt được |
| **introspection.transport_error** | DNS/TLS/TCP hoặc HTTP client failure |
| **introspection.pending** | Số lượt chờ lấy connection |
| **introspection.cancelled** | Reactive subscriber cancellation |
| **introspection.rejected** | Pool/bulkhead từ chối do tải |
| **introspection.upstream_5xx** | AS có lỗi hạ tầng |

**Không dùng token value, user email, sub hay Authorization header làm metric labels.** Đây là dữ liệu nhạy cảm và có cardinality cao. Chỉ log request correlation ID, logical endpoint name, duration và lỗi đã được sanitize.

### 15.1. p95/p99 quan trọng hơn average

Một response timeout và pool size dựa chỉ trên latency trung bình dễ thất bại khi AS có tail latency cao. Đo p50/p95/p99, peak traffic và pending queue time; dùng chúng để chọn timeout và kích thước pool.

Không bật wiretap logging HTTP chứa introspection form body và credentials trong production mà không có biện pháp che giấu nghiêm ngặt.

## 16. HTTP/1.1, HTTP/2 và connection reuse

Với HTTP/1.1, nhiều concurrent HTTP requests thường cần nhiều connections khi mỗi connection đang bận một response.

Với HTTP/2, một TCP/TLS connection có thể mang nhiều concurrent streams. Khi đó:

- maxConnections không trực tiếp bằng max concurrent introspection requests.
- HTTP/2 stream limits và upstream settings có thể trở thành nút thắt.
- Cancellation có thể hủy stream mà không đóng connection.
- Load tests cần dùng cùng HTTP protocol với production.

Không dùng con số connection concurrency từ HTTP/1.1 để suy ra khả năng xử lý HTTP/2 nếu chưa test.

### 16.1. maxIdleTime và upstream load balancer

Nếu AS/load balancer đóng connection idle sau 30 giây, đặt client maxIdleTime quá lớn có thể làm tăng lỗi khi reuse connection đã đóng bởi peer.

Reactor Netty khuyên cân nhắc client idle timeout bằng hoặc ngắn hơn upstream idle timeout. Ví dụ **20 giây** là một điểm thử, không phải quy tắc chung.

### 16.2. maxLifeTime và lifecycle

maxLifeTime giúp connections không tồn tại vô hạn, hữu ích khi xem xét network changes. Nhưng nó không tự bảo đảm DNS/TLS rotation được nhận ngay lập tức. Cần test khi AS đổi IP, certificates hoặc load balancer topology.

## 17. Điều gì xảy ra khi caller ngắt kết nối?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as WebFlux Resource Server
    participant W as WebClient
    participant A as Authorization Server

    B->>R: GET /api/orders/42
    R->>W: Subscribe introspection
    W->>A: POST /introspect
    B--xR: Client disconnect
    R--xW: Cancel upstream nếu pipeline truyền tín hiệu
    Note over W,A: Outbound có thể dừng hoặc đóng stream
    Note over A: AS có thể đã xử lý request
~~~

Những nguyên tắc:

- Return **Mono**; không **subscribe()** thủ công trong introspector.
- Không **block()** trên Reactor event loop.
- Dùng timeout/cancellation metrics đúng điểm quan sát.
- Không xem cancellation là revoked token.
- Không mặc định AS chắc chắn hủy công việc.
- Nếu đã dùng caching/shared Mono, một subscriber cancel không đồng nghĩa upstream bị cancel.
- Kiểm resource cleanup bằng integration test, không chỉ dựa vào Java code trông có vẻ reactive.

## 18. StepVerifier: kiểm timeout và cancellation ở cấp Reactor

Dùng **reactor-test** và JUnit 5 để kiểm operator semantics.

### 18.1. Timeout tạo lỗi

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTest {

    @Test
    void neverCompletingPublisherTimesOut() {
        Mono<String> slow =
            Mono.<String>never().timeout(Duration.ofMillis(50));

        StepVerifier.create(slow)
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }
}
~~~

Test này kiểm **Mono.timeout**, không tự kiểm TCP socket hay HTTP connection pool. Để giảm flaky behavior, có thể dùng virtual time hoặc điều khiển clock phù hợp trong Reactor Test khi thiết kế test.

### 18.2. Cancellation được truyền cho Publisher

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class CancellationTest {

    @Test
    void cancelReachesUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Mono<String> publisher = Mono.<String>never()
            .doOnCancel(() -> cancelled.set(true));

        StepVerifier.create(publisher)
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }
}
~~~

Test chứng minh **Reactor signal cancellation**, không chứng minh remote AS đã đóng job hoặc socket đã được reuse/close đúng. Những điều đó cần kiểm bằng HTTP test server và Reactor Netty metrics.

## 19. Kiểm thử WebClient với HTTP stub

Dùng test HTTP server như MockWebServer, WireMock hoặc Reactor Netty test server thay cho Authorization Server production.

Các trường hợp quan trọng:

1. **active=true** cùng scope phù hợp → Authentication thành công.
2. **active=false** → bị từ chối, không tạo principal.
3. **AS trả HTTP 401** cho introspection client → không fail-open.
4. **AS trì hoãn response** quá responseTimeout → client lỗi.
5. **AS trì hoãn** quá overall timeout → outer Mono phát TimeoutException.
6. **Request đồng thời vượt maxConnections** → xuất hiện pending acquisition.
7. **Pending queue quá lớn** → acquisition bị từ chối.
8. **Chờ pending quá lâu** → pendingAcquireTimeout.
9. **Client cancel** khi outbound request còn pending → quan sát cleanup/cancellation.
10. **TLS hostname/certificate sai** → request bị từ chối.
11. **Body quá lớn hoặc JSON sai** → không tạo principal.
12. **AS trả active=true nhưng thiếu audience bắt buộc** → custom policy từ chối.

Cần điều khiển delay và concurrency của stub có chủ đích. Đừng viết test kỳ vọng request số 33 chắc chắn queued nếu scheduling, keep-alive hoặc HTTP/2 khiến thứ tự thay đổi.

### 19.1. WebTestClient kiểm Resource Server, không thay transport tests

Trong WebFlux, **WebTestClient** được gắn Spring Security filters có thể kiểm các status:

| Tình huống | Kết quả thông thường |
|---|---|
| Không Bearer token | **401** |
| Token introspection active=false | **401 invalid_token** |
| Token active=true và đủ scope | Request đi tới handler |
| Token active=true nhưng thiếu scope | **403** |
| Introspection timeout | Lỗi, không được authentication |
| Pool exhausted | Lỗi hạ tầng, không fail-open |

**mockOpaqueToken()** trong Spring Security Test thường tạo Authentication giả để test authorization; nó **bỏ qua WebClient introspection thật**. Vì vậy nó không chứng minh timeout, TLS, queue hoặc connection pool. Cần integration test với fake HTTP AS để kiểm đường đi network.

## 20. 401, 403 và lỗi hạ tầng introspection

Một cách phân loại:

| Kết quả | Có đủ thông tin để authenticate? | Ứng xử |
|---|---|---|
| Không token | Không | Bearer challenge, thường 401 |
| AS trả active=false | Không | Invalid token, thường 401 |
| Active=true, thiếu scope | Có, nhưng không đủ quyền | 403 khi rule áp dụng |
| Active=true, sai tenant | Có thể đã xác thực | Domain policy 403/404 |
| DNS/TCP/TLS timeout | Chưa xác minh được | Lỗi hạ tầng, không fail-open |
| Pool pending timeout | Chưa hoàn tất introspection | Lỗi quá tải/hạ tầng |
| WebClient response timeout | Chưa có kết quả tin cậy | Lỗi timeout |
| Client cancel | Chưa chắc có response để trả | Dừng downstream work theo lifecycle |
| AS 5xx | Chưa có kết quả xác minh | Monitor upstream; không tạo principal |
| Introspection client 401/403 | AS không cho client introspect | Sửa credentials/policy |

**Không khẳng định mọi TimeoutException mặc định sẽ trả HTTP 401 hay 503.** Status phụ thuộc exception conversion và handler của application/Spring Security version. Điều bắt buộc là token không được coi là hợp lệ nếu introspection chưa thành công.

### 20.1. Không biến mọi lỗi transport thành invalid_token

**active=false** là câu trả lời về token. **Network timeout** là câu trả lời rằng quá trình xác minh không thành công trong budget.

Cả hai đều không cho quyền, nhưng cần log/metric/error policy khác nhau. Nếu custom handler hiển thị lỗi, không tiết lộ raw token, client secret, hostname nội bộ hoặc stack trace cho caller.

## 21. Ví dụ sự cố: AS chậm khiến pool đầy

Giả sử mỗi Resource Server replica có:

~~~text
maxConnections = 32
pendingAcquireMaxCount = 64
pendingAcquireTimeout = 150 ms
responseTimeout = 1500 ms
overallTimeout = 2500 ms
~~~

Nếu AS mất 2 giây để trả mỗi response:

1. Các connections đang hoạt động bị giữ lâu.
2. Requests mới xếp vào pending queue.
3. Một phần pending requests bị timeout sau 150 ms hoặc bị từ chối do queue đầy.
4. Các requests có connection có thể chạm response timeout.
5. Một số callers có thể cancel do gateway deadline.
6. Authentication không hoàn tất cho những requests lỗi; chúng không được cấp quyền.
7. Pool metrics cho thấy active/pending tăng; upstream latency hoặc lỗi 5xx cần được phân tích.

**Không chỉ tăng maxConnections từ 32 lên 5.000**. Làm vậy có thể khiến AS bị áp nhiều sockets hơn và sụp nhanh hơn. Cần đánh giá capacity, traffic bursts, cache/retry, rate limits và p99 latency.

## 22. Anti-pattern cần nhận diện

**Tạo WebClient và ConnectionProvider mới cho mỗi Bearer request.** Điều này phá connection reuse, tăng handshake và gây resource leak.

**Dùng block() trong ReactiveOpaqueTokenIntrospector.** Blocking event loop làm latency tăng và có thể gây lỗi runtime.

**Không có timeout ở lớp network lẫn toàn publisher.** Một request có thể giữ connection hoặc pending slot quá lâu.

**Chỉ có overall timeout mà không có pool bounds.** Requests có thể dồn quá nhiều trong burst trước khi timeout.

**Giữ pending queue vô hạn.** Request đã hết deadline vẫn làm tăng bộ nhớ/chờ.

**Retry mọi exception.** Retry active=false và invalid_token không giúp gì; retry khi AS quá tải có thể khuếch đại sự cố.

**Fail-open khi introspection lỗi.** Không bao giờ tạo principal ADMIN hoặc active=true vì network timeout.

**Tự subscribe để gọi AS ngoài pipeline.** Làm mất cancellation/error propagation của security flow.

**Dùng raw token trong log hoặc metric tags.** Làm lộ Bearer credential, tăng high-cardinality telemetry.

**Tin introspection URI do client đưa.** Có thể gây SSRF và lộ client credentials.

**Coi HTTP 200 của AS là token active.** Phải kiểm JSON active; HTTP 200 có thể chứa active=false.

**Coi cancel là remote rollback.** AS có thể đã nhận và xử lý request.

**Dùng WebClient chứa Basic credential cho các URL tùy ý.** Chỉ dùng cho trusted AS endpoint.

**Không dispose custom pool khi shutdown.** Tài nguyên sockets/connections có thể rò rỉ.

**Nhầm timeout với token revocation.** Hai sự kiện đều có thể không cho access nhưng cần giải thích khác nhau.

## 23. Checklist thiết kế và triển khai

### Bước 1 — Xác định hợp đồng introspection

Chỉ dùng Authorization Server/URI tin cậy, HTTPS, credentials được bảo vệ, các claims bắt buộc như **active, aud, scope** và chính sách token type/tenant.

### Bước 2 — Đo yêu cầu latency

Ước lượng peak QPS và p95/p99 introspection latency. Phân bổ overall timeout nhỏ hơn request budget trong hệ thống.

### Bước 3 — Tạo WebClient chuyên biệt

Cấu hình fixed endpoint, client credentials, response body size, HttpClient timeouts, ConnectionProvider bounds. Không dùng URL client-supplied.

### Bước 4 — Giới hạn active/pending

Dùng maxConnections, pendingAcquireMaxCount và pendingAcquireTimeout hữu hạn; cân đối với tất cả replicas và AS capacity.

### Bước 5 — Xử lý cancellation đúng

Return Mono được compose; không block/subscribe trong filter/introspector. Theo dõi doFinally/doOnCancel đúng vị trí và test cleanup.

### Bước 6 — Thiết kế lỗi fail-closed

Token inactive, timeout, pool exhausted hoặc upstream outage đều **không tạo Authentication thành công**. Phân loại lỗi cho monitoring và phản hồi thích hợp.

### Bước 7 — Chỉ cache/retry theo policy

Cache phải đáp ứng revocation lag và token expiration. Retry phải phân loại transient lỗi, có backoff và overall deadline.

### Bước 8 — Tích hợp observability

Theo dõi pool active/pending, duration, timeout classes, cancellation, AS 5xx và circuit-breaker state mà không log credentials.

### Bước 9 — Kiểm bằng HTTP test server

Dùng stub AS để mô phỏng response delay, active=false, malformed response, 401 client credentials, overload và cancellation. WebTestClient kiểm authentication/authorization end-to-end.

### Bước 10 — Rà soát khi scale deployment

Tăng số replicas hoặc thay AS/gateway/TLS/HTTP protocol có thể thay đổi connection capacity và latency. Cần đánh giá lại pool và timeout trên môi trường thực.

## 24. Câu hỏi tự kiểm tra

**1. WebClient nonblocking có nghĩa AS chậm không ảnh hưởng API?**

Không. Nó không giữ một thread blocking cho mỗi request, nhưng pool, pending queue, memory và end-to-end latency vẫn bị ảnh hưởng.

**2. responseTimeout có bao phủ pendingAcquireTimeout không?**

Không. Chúng giới hạn những giai đoạn khác nhau.

**3. Mono.timeout có thể giới hạn toàn lần introspection không?**

Có nếu đặt bao quanh publisher tương ứng. Nó phát TimeoutException và yêu cầu hủy upstream khi quá hạn.

**4. Cancel có bảo đảm AS dừng xử lý HTTP POST không?**

Không. AS có thể đã nhận request và tiếp tục xử lý dù client ngừng chờ.

**5. maxConnections=32 có nghĩa tối đa 32 requests/giây không?**

Không. Đây là số active connections theo pool, không phải QPS; HTTP/2 còn có stream multiplexing.

**6. maxConnections của một replica có phải giới hạn toàn cụm?**

Không. Các replicas có pool riêng và các clients khác vẫn gọi cùng AS.

**7. Vì sao không nên có pending queue vô hạn?**

Vì requests có thể chờ rất lâu, hết deadline và tiêu tốn memory mà không có kết quả hữu ích.

**8. Có thể retry active=false cho đến khi AS trả true không?**

Không. active=false là kết quả token không hợp lệ, không phải lỗi mạng tạm thời.

**9. Có nên cache active=true?**

Chỉ theo TTL, token expiration, revocation lag và security policy đã xác định.

**10. StepVerifier kiểm cancellation có chứng minh socket đã đóng không?**

Không. StepVerifier chỉ kiểm Reactor signals; cần network integration tests.

**11. Token trông giống JWT có thể được introspect bằng opaque strategy không?**

Có. Khi Resource Server chọn introspection, cơ chế xác thực vẫn phụ thuộc AS response, cùng chịu timeout/cancellation/pool limits.

**12. Timeout có được coi là invalid_token không?**

Không. Timeout chỉ cho biết Resource Server chưa có kết quả xác minh tin cậy trong thời hạn.

## Kết luận

Với **Spring Security WebFlux Resource Server**, opaque-token introspection thường là một HTTP operation reactive qua **WebClient/Reactor Netty**. Mỗi lượt xác thực phụ thuộc vào **connection pool, network, Authorization Server latency và vòng đời Reactor subscription**.

Thiết kế đáng tin cậy gồm:

- **WebClient singleton** chỉ gọi endpoint introspection được tin cậy.
- **Timeout chuyên biệt** cho pending acquire, TCP connect và response, cộng **overall Mono.timeout** cho request budget.
- **ConnectionProvider có giới hạn** maxConnections và pending queue thay vì tạo kết nối/hàng đợi vô hạn.
- **Cancellation propagation** bằng Publisher composition, nhưng không giả định AS đã dừng xử lý sau cancel.
- **Fail-closed khi introspection không thành công**, không tạo principal từ token chưa xác thực.
- **Metrics, bounded retries/cache và HTTP integration tests** để đánh giá hiệu năng, revocation và quá tải.

**Không nên chỉ tăng pool size để chữa upstream chậm, dùng block()/subscribe() sai vị trí, retry invalid_token hay nhầm timeout với việc token bị thu hồi.** Những phân biệt này là nền tảng để giữ an toàn và khả dụng khi Resource Server phải phụ thuộc vào introspection service.

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html)
- [Spring Framework — WebClient Configuration and Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty — HTTP Client, Connection Pool and Timeouts](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Reactor Test StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
