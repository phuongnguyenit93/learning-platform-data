# Độ trễ, tính sẵn sàng và khả năng phản ánh thu hồi token

## 1. Vì sao opaque token tạo ra một bài toán vận hành riêng?

Trong **Spring Boot + Spring Security OAuth 2.0 Resource Server**, một API thường nhận Bearer access token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Có hai hướng xác minh phổ biến:

- **JWT verification:** Resource Server kiểm tra chữ ký JWS bằng public key tin cậy và xác minh các claims của access token. Khi đã có khóa trong cache, nó thường không cần gọi Authorization Server (AS) trên mỗi request.
- **Opaque token introspection:** Resource Server xem token là một chuỗi chưa biết nội dung, gửi nó tới **introspection endpoint** để hỏi AS token có còn active và mang những thuộc tính gì.

Opaque token introspection hấp dẫn khi hệ thống yêu cầu **khả năng phản ánh thu hồi (revocation)**. Nhưng cách này làm nảy sinh ba câu hỏi:

1. **Độ trễ:** request phải chờ một HTTP round trip tới AS bao lâu?
2. **Tính sẵn sàng:** nếu AS timeout, 429 hoặc 5xx, Resource Server xử lý thế nào?
3. **Độ mới của thông tin:** sau khi token bị revoke, còn bao nhiêu request có thể tiếp tục được chấp nhận?

Nếu thêm **cache kết quả introspection**, latency và tải lên AS có thể giảm, nhưng trạng thái `active`, scope và các thuộc tính có thể **không còn mới**. Đây là một đánh đổi cần thiết kế, không phải chỉ bật một property là giải quyết tất cả.

Bài này tập trung vào **Spring Security Servlet Resource Server** dùng `OpaqueTokenIntrospector`; đồng thời so sánh với JWT để hiểu rõ latency, availability và revocation. Các con số timeout/TTL trong ví dụ là giá trị minh họa, không phải cấu hình khuyến nghị chung.

## 2. OAuth 2.0 Token Introspection theo RFC 7662

### 2.1. Resource Server hỏi trạng thái token như thế nào?

Một opaque token có thể trông như chuỗi ngẫu nhiên:

~~~text
n5bP2u9XwQ7s1VtK3mA8...
~~~

Resource Server không tự giải mã `sub`, `scope` hoặc `exp` từ chuỗi này. Nó gửi token tới introspection endpoint mà AS cung cấp.

Ví dụ request theo **RFC 7662**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <RESOURCE_SERVER_INTROSPECTION_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>&token_type_hint=access_token
~~~

`token_type_hint` là tham số **tùy chọn**. Thông tin xác thực của Resource Server khi gọi introspection (ví dụ HTTP Basic) là **credential riêng**, không phải Bearer token của người dùng và không được đưa vào frontend.

AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read profile",
  "client_id": "shop-web",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://id.example.test/realms/shop",
  "exp": 2000000000
}
~~~

Đây là dữ liệu minh họa. Trong RFC 7662, `active` là trường quyết định trạng thái; các trường khác tùy loại token và hợp đồng AS. Không phải provider nào cũng trả `aud`, `iss`, `exp` hoặc `tenant_id`.

Khi token không active, phản hồi hợp lệ có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**Không suy ra token active chỉ vì introspection trả HTTP 200.** HTTP response biểu thị introspection request đã được xử lý; JSON `active` mới biểu thị trạng thái token.

### 2.2. Introspection endpoint 401 khác API endpoint 401

Nếu Resource Server dùng client ID/secret sai, AS có thể trả **401** cho chính HTTP POST introspection. Đó là lỗi **client authentication của Resource Server với AS**, không phải bằng chứng bearer token của caller bị revoke.

Có hai HTTP exchanges độc lập:

~~~text
Exchange A: API client -> Resource Server
Exchange B: Resource Server -> AS introspection
~~~

Cần phân biệt:

| Kết quả từ AS | Ý nghĩa đáng tin | Hướng xử lý |
|---|---|---|
| HTTP 200, `active:true` | Token được AS xác nhận active tại thời điểm hỏi | Xây principal và kiểm tra authorization |
| HTTP 200, `active:false` | AS không xác nhận token active | Từ chối Bearer token |
| HTTP 401/403 của introspection endpoint | Credential/policy truy cập introspection của RS có vấn đề | Điều tra cấu hình, không tự coi token revoked |
| HTTP 429 | AS rate-limit introspection | Giới hạn tải, backoff có kiểm soát |
| HTTP 5xx | AS lỗi hạ tầng | Không cấp quyền bằng suy đoán |
| Connect/read timeout | Không có quyết định mới từ AS | Fail closed hoặc báo lỗi hạ tầng |

Trong Spring Security, status cuối trả về caller còn phụ thuộc exception mapping. Không khẳng định mọi network failure chắc chắn được map thành `401 invalid_token`; cần tách lỗi token với lỗi dịch vụ.

### 2.3. Revocation và introspection là hai hành động khác nhau

**RFC 7009** mô tả yêu cầu thu hồi token; **RFC 7662** mô tả cách kiểm tra token.

~~~mermaid
flowchart TD
    A["Client hoặc admin yêu cầu revoke"] --> B["Authorization Server"]
    B --> C["AS cập nhật trạng thái token/grant"]
    C --> D["Introspection endpoint"]
    E["Resource Server"] -->|"Hỏi lại token"| D
    D -->|"active=false"| E
    E --> F["Từ chối request tiếp theo"]
~~~

Giữa lệnh revoke và introspection tiếp theo có thể có độ trễ đồng bộ hoặc cache. Opaque token **không tự đảm bảo revoke tức thì**; AS phải thực sự phản ánh thay đổi qua endpoint.

## 3. Spring Security xử lý opaque token ở đâu?

Trong Servlet stack, đường đi thông thường:

~~~mermaid
sequenceDiagram
    participant Client as API Client
    participant Filter as BearerTokenAuthenticationFilter
    participant Provider as OpaqueTokenAuthenticationProvider
    participant Introspector as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant Authz as AuthorizationFilter
    Client->>Filter: GET + Authorization Bearer token
    Filter->>Provider: BearerTokenAuthenticationToken
    Provider->>Introspector: introspect(token)
    Introspector->>AS: HTTP POST introspection
    AS-->>Introspector: active + token attributes
    alt active=false
        Introspector-->>Provider: authentication failure
        Provider-->>Client: thường 401
    else active=true
        Introspector-->>Provider: OAuth2AuthenticatedPrincipal
        Provider-->>Filter: BearerTokenAuthentication
        Filter->>Authz: SecurityContext đã có Authentication
        Authz-->>Client: Controller hoặc 403
    end
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| `BearerTokenAuthenticationFilter` | Trích Bearer token từ HTTP header |
| `OpaqueTokenAuthenticationProvider` | Gọi introspector để xác thực |
| `OpaqueTokenIntrospector` | Abstraction kiểm tra token qua AS hoặc implementation khác |
| `SpringOpaqueTokenIntrospector` | Implementation dùng endpoint introspection |
| `OAuth2AuthenticatedPrincipal` | Principal chứa attributes và authorities |
| `BearerTokenAuthentication` | Authentication được tạo khi token hợp lệ |
| `AuthorizationFilter` | Kiểm tra quyền endpoint sau authentication |

Spring Security mặc định thường chuyển scopes trong introspection response thành authorities với prefix `SCOPE_`. Chẳng hạn `scope = "orders.read profile"` tạo `SCOPE_orders.read` và `SCOPE_profile`.

Không áp dụng máy móc `@AuthenticationPrincipal Jwt` cho chế độ opaque. Principal mặc định thường là `OAuth2AuthenticatedPrincipal` ngay cả khi chuỗi token có hình dạng JWT nhưng được kiểm tra qua introspection.

## 4. Cấu hình tối thiểu cho Spring Boot

### 4.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 4.2. Cấu hình introspection

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Endpoint và client ID là ví dụ, còn client secret lấy từ environment/secret manager. Không commit secret vào repository, không đưa vào browser, không ghi trong log. AS phải cấp quyền introspection phù hợp cho client này.

### 4.3. Cấu hình filter chain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

`oauth2ResourceServer(...opaqueToken(...))` thiết lập introspection pipeline. Không cần tự viết một filter đọc `Authorization` hoặc gọi introspection ở mỗi controller.

Nếu API dùng Bearer header và stateless authentication, hãy cấu hình session/CSRF theo threat model. Không tự tắt CSRF của những endpoint đang dùng cookie/session chỉ để chạy ví dụ.

### 4.4. Đọc principal ở controller

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        return Map.of("name", principal.getName());
    }
}
~~~

Đoạn này giả định endpoint yêu cầu xác thực và name không null theo hợp đồng. Với machine-to-machine token, principal name không nhất thiết là user ID; cần kiểm tra profile của AS.

## 5. Độ trễ: introspection ở request path

### 5.1. Ngân sách latency

Khi **không cache**, một request Bearer thường phải chờ network:

~~~text
Client
  |
  v
Resource Server
  |
  +-- BearerTokenAuthenticationFilter
  |
  +-- Introspection HTTPS POST
  |     +-- DNS/TLS/proxy
  |     +-- network RTT
  |     +-- AS đọc token store / grant state
  |     +-- AS trả JSON
  |
  +-- tạo Authentication + authorities
  +-- endpoint authorization
  +-- business logic và database
  |
  v
HTTP response
~~~

Một mô hình khái niệm:

~~~text
T_response = T_security_local
           + T_introspection
           + T_authorization
           + T_business
           + T_network_response
~~~

Đây không phải công thức đo chính xác cho mọi ứng dụng, nhưng nó giúp nhận ra một HTTP call phụ thuộc AS có thể chi phối latency ngay cả khi controller rất nhanh.

Không cộng đơn giản p95 của từng thành phần rồi gọi đó là p95 tổng; các percentile không nhất thiết xảy ra đồng thời. Hãy đo end-to-end p50, p95, p99 và tạo span riêng cho introspection.

### 5.2. Những nguồn gây chậm

| Nguyên nhân | Tác động |
|---|---|
| API và AS ở xa nhau | Tăng round-trip time |
| TLS/DNS/connect mới liên tục | Tăng overhead |
| Không có connection pooling | Khó tái sử dụng kết nối |
| HTTP proxy/service mesh | Thêm hop, timeout và retry policy |
| AS có token store chậm | Tăng thời gian lookup trạng thái |
| AS bị rate limit hoặc peak traffic | Tăng latency và lỗi |
| Nhiều Resource Servers cùng introspect | Tổng tải lên AS lớn |
| Cache miss hàng loạt | Gây burst |
| Retry không giới hạn | Tăng tail latency và khuếch đại tải |

Với Servlet stack, một outbound introspection call đồng bộ giữ tài nguyên request-handling trong lúc chờ. Không thể giải quyết lâu dài bằng cách tăng số worker threads vô hạn.

### 5.3. Tải tăng theo RPS

Nếu API nhận 500 request/giây cần Bearer authentication, không cache có thể tạo xấp xỉ 500 introspection calls/giây tới AS. Nếu một user action đi qua 4 microservices và cả 4 đều introspect token, tổng số cuộc gọi có thể còn lớn hơn.

Tính toán năng lực cần dựa vào:

- Peak requests/second, không chỉ average.
- Fan-out giữa các microservices.
- Thời gian xử lý token store ở AS.
- Network latency và connection count.
- Số lần retry khi outage.
- Tỷ lệ token được dùng lặp.
- Phân bố token hợp lệ so với token-spray ngẫu nhiên.

Một benchmark khi không tải không chứng minh hệ thống chịu được peak p99.

## 6. Tính sẵn sàng: AS trở thành dependency trực tiếp

### 6.1. Khi AS không trả lời

Với opaque introspection không cache, Resource Server thường không thể tự xác minh token. AS outage làm các protected endpoints bị ảnh hưởng, dù Orders API và database của nó vẫn khỏe.

~~~mermaid
flowchart TD
    A["Request Bearer token"] --> B["Resource Server"]
    B --> C["Introspection"]
    C --> D{"AS trả quyết định?"}
    D -->|"active=true"| E["Authorization"]
    D -->|"active=false"| F["Reject token"]
    D -->|"Timeout/5xx"| G["Không có xác nhận tin cậy"]
    G --> H["Fail closed hoặc lỗi dịch vụ"]
~~~

**Fail closed:** không chấp nhận một token chỉ vì trước đó nó có vẻ hợp lệ hoặc vì AS đang outage. Nếu có cache dương với TTL cứng, việc dùng entry còn hạn phải là **quyết định chính sách đã được chấp nhận trước**, không phải fallback vô hạn.

### 6.2. Phân biệt lỗi nghiệp vụ và hạ tầng

| Tình huống | Có dữ liệu từ AS? | Cách hiểu |
|---|---|---|
| `active:false` | Có | Token không active theo AS |
| `active:true`, thiếu scope | Có | Authentication thành công, authorization từ chối |
| Connect timeout | Không | Không xác định được trạng thái mới |
| Read timeout | Không đầy đủ | Không có kết quả introspection tin cậy |
| Introspection HTTP 401 | Có lỗi endpoint | Có thể RS client credentials không đúng |
| Introspection HTTP 429 | AS giới hạn tải | Không phải token mặc nhiên bị revoke |
| Introspection HTTP 5xx | AS lỗi | Không phải quyết định active/inactive |

Status cuối trả API client phụ thuộc exception mapping. Không biến mọi lỗi mạng thành `invalid_token` hoặc tự trả `200 OK` để giấu outage. Metric/log nội bộ phải phân loại rõ.

### 6.3. Retry, circuit breaker, bulkhead

Có thể xem xét:

- **Timeout:** không giữ thread chờ vô hạn.
- **Retry với backoff/jitter:** chỉ cho lỗi transient, số lần và deadline tổng có giới hạn.
- **Circuit breaker:** tránh gọi dồn đến AS đang sự cố.
- **Bulkhead/concurrency limit:** không để introspection chiếm hết outbound connections hoặc Servlet threads.
- **Rate limiting:** bảo vệ cả API và AS trước lượng Bearer token sai bất thường.
- **Load shedding:** từ chối có kiểm soát khi authentication dependency vượt năng lực.

Không retry `active:false`: đó là một quyết định về token, không phải transient failure. Nếu circuit breaker đang open, **không** được coi tất cả token là active.

## 7. Cấu hình timeout phù hợp SLO

Tài liệu Spring Security Servlet hiện hành mô tả default connect và socket timeout cho introspection thường là **30 giây mỗi loại**. Default có thể thay đổi theo phiên bản; với API có yêu cầu latency thấp, cần cấu hình tường minh.

Các loại timeout không giống nhau:

- **Connect timeout:** chờ thiết lập kết nối.
- **Read/socket timeout:** chờ dữ liệu trả về.
- **Connection-pool acquisition timeout:** chờ lấy connection trong pool, nếu có.
- **Overall deadline:** giới hạn toàn bộ authentication/API request kể cả retries.

Timeout 1 giây hoặc 2 giây trong ví dụ dưới đây chỉ minh họa cách cấu hình, không phải giá trị áp dụng cho mọi network.

### 7.1. Tạo `OpaqueTokenIntrospector` với HTTP client riêng

Các phiên bản Spring Security hỗ trợ constructor `SpringOpaqueTokenIntrospector(String, RestOperations)`. Khi cung cấp `RestOperations`, client này **phải tự thiết lập client authentication với introspection endpoint**.

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;

@Configuration
public class IntrospectionHttpConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String clientId,
            @Value("${app.security.introspection.client-secret}") String secret) {

        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(1_000); // milliseconds
        factory.setReadTimeout(2_000);    // milliseconds

        RestTemplate http = new RestTemplate(factory);

        // RestOperations trong constructor này phải tự xác thực client.
        http.getInterceptors().add(
            new BasicAuthenticationInterceptor(clientId, secret));

        return new SpringOpaqueTokenIntrospector(uri, http);
    }
}
~~~

YAML:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

`app.security.*` là property do ứng dụng tự định nghĩa. Nếu dùng `spring.security.oauth2.resourceserver.opaquetoken.*` qua Spring Boot, có thể tránh tự tạo bean khi không cần customization.

`SimpleClientHttpRequestFactory` chỉ minh họa timeout đơn giản. Với production cần connection pool, proxy, custom trust store, mTLS hoặc tracing, chọn `ClientHttpRequestFactory` phù hợp. Không gắn interceptor chuyển Bearer token của user vào HTTP client infrastructure này.

### 7.2. Builder mặc định

Ở Spring Security 6.5+ có thể dùng:

~~~java
OpaqueTokenIntrospector remote =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            "https://id.example.test/oauth2/introspect")
        .clientId("orders-api-introspector")
        .clientSecret(secretFromSecretManager)
        .build();
~~~

`secretFromSecretManager` là biến do hệ thống cung cấp, không phải giá trị hard-coded. Khi dùng builder này mà không tùy chỉnh client, hành vi HTTP theo phiên bản thư viện.

Một số Spring Security phiên bản mới còn cung cấp `RestClientOpaqueTokenIntrospector` dựa trên `RestClient` (ví dụ API từ 7.1). Không dùng class mới trong project Spring 6.x khi dependency không có. Với **WebFlux**, dùng reactive introspector và HTTP client tương ứng.

## 8. Khả năng phản ánh revoke: không cache so với cache

### 8.1. Không cache: hỏi lại tại request tiếp theo

Giả sử:

~~~text
t0: API introspects token T -> active=true
t1: admin revoke T
t2: AS ghi nhận và đồng bộ revoke
t3: request mới với T tới API
t4: API introspects T -> active=false
t5: request bị từ chối
~~~

Nếu AS đã cập nhật trạng thái ở `t2` và Resource Server hỏi lại ở `t4`, token bị từ chối. Nhưng:

- Request đã được authorize trước revoke có thể vẫn hoàn thành.
- AS có thể có replication delay.
- Một số trạng thái disable user/grant không tự làm token inactive ngay.
- Gateway hoặc AS có thể có caches riêng.
- Introspection có thể đi tới node chưa nhận sự kiện revoke.

Vì vậy “opaque token revoke tức thì” không phải guarantee tuyệt đối của định dạng token.

### 8.2. Cache tạo khoảng trạng thái `active` cũ

Nếu API cache `active:true`:

~~~text
t0: introspection active=true -> cache entry C
t1: token bị revoke
t2: request mới -> cache hit C -> có thể vẫn được chấp nhận
t3: C hết hạn -> introspection lần nữa
t4: AS đã biết revoke -> active=false
~~~

Cache dương làm giảm số lần gọi AS nhưng **kéo dài revocation exposure window**.

Mô hình gần đúng:

~~~text
Exposure window ≈
    AS propagation delay
  + RS positive-cache staleness
  + các cache khác trên đường đi
  + request/transaction đã được phép trước revoke
~~~

Đây là phân tích rủi ro, không phải hard bound nếu AS không cam kết consistency/latency. TTL 10 giây tại RS không tự cam kết revoke-to-deny không quá 10 giây trong toàn hệ thống.

### 8.3. Thu hồi token khác thay đổi quyền

AS có thể trả `active:true` nhưng scope/role của user đã thay đổi:

- Nếu AS giữ snapshot quyền tại lúc phát hành token, introspection vẫn có thể trả quyền cũ đến `exp`.
- Nếu AS cập nhật dynamic entitlement khi introspect, kết quả có thể phản ánh thay đổi mới.
- Nếu Resource Server cache principal, scope/attributes cũng có thể bị stale.

**`active:true` không chứng minh user có quyền hiện thời trên mọi bản ghi.** API vẫn có thể cần kiểm tra tenant, owner, local ACL hoặc entitlement từ nguồn dữ liệu đáng tin của chính nó.

## 9. So sánh các chiến lược

| Chiến lược | Latency | Khi AS outage | Revocation freshness |
|---|---|---|---|
| Opaque introspection không cache | Thường có remote call mỗi request | Phụ thuộc trực tiếp AS | Tốt nhất theo trạng thái AS tại lần hỏi |
| Opaque + positive cache ngắn | Nhiều request có thể cache hit | Entry còn hạn có thể dùng theo policy | Chậm theo TTL và propagation |
| Opaque + positive cache dài | Latency/tải thấp hơn khi hit | Dùng cache được lâu hơn | Khoảng stale có thể lớn |
| Opaque + event invalidation đáng tin | Có thể nhanh và giảm tải | Phụ thuộc AS + event infrastructure | Tốt nếu delivery/reconciliation đúng |
| JWT verify offline | Thường chỉ crypto local khi có JWKS | Có thể tiếp tục với key cache | Không tự biết revoke trước `exp` |
| JWT format nhưng kiểm tra bằng introspection | Giống opaque introspection | Phụ thuộc AS | Theo introspection policy |

**Opaque không luôn tốt hơn JWT, cũng không ngược lại**. Chọn theo latency budget, dependency availability, revocation requirements, token profile và độ phức tạp vận hành.

## 10. Cache kết quả introspection: những quyết định bắt buộc

### 10.1. Cache gì?

Một cache dương có thể lưu:

- Principal và attributes từ introspection.
- Authorities ánh xạ từ `scope`.
- Thời điểm có quyết định active.
- Thời điểm quyết định cache hết hiệu lực.

Không tự cache raw token trong log, metrics hoặc Redis key. Opaque token là **bearer credential**; ai lấy được token có thể thử sử dụng nó.

### 10.2. Dùng cache key không tiết lộ token

Một lựa chọn:

~~~text
cache_key = HMAC-SHA256(server_secret, access_token)
~~~

HMAC key cần đủ ngẫu nhiên, lưu trong secret manager và giới hạn quyền truy cập. HMAC chỉ giúp định danh cache entry mà không phơi raw token; **nó không xác minh token**.

Nếu dùng shared cache giữa nhiều replicas, thiết kế thêm namespace, HMAC key rotation, access control của cache và giới hạn nội dung được lưu. Public key cache JWKS không giống cache token status của introspection.

### 10.3. TTL phải bị ràng buộc bởi `exp` nếu có

Nếu AS trả `exp`, thời gian sống cache dương không nên vượt token expiry:

~~~text
valid_until = min(
    introspection_time + positive_cache_ttl,
    token_expiration_time
)
~~~

`exp` là một claim tùy chọn trong RFC 7662. Nếu provider không trả `exp`, một chính sách thận trọng là **không cache dương** hoặc chỉ cache theo một contract token lifetime bảo đảm từ nguồn đáng tin.

Cache 15 giây không làm token có thêm 15 giây hiệu lực sau khi `exp`. Dù token vẫn chưa hết hạn, nó có thể đã bị revoke trong thời gian cache.

### 10.4. Negative caching

Cache `active:false` rất ngắn có thể giảm tải khi client gửi lại cùng token sai liên tục. Nhưng cần cân nhắc:

- Token-spray với vô số chuỗi khác nhau có thể tạo cache key cardinality cao.
- Một AS node bị stale có thể tạo negative result không mong đợi.
- Network failure **không được** chuyển thành `active:false` và cache như một quyết định revoke.
- Cache size, TTL và invalidation phải bị giới hạn.

Không nhất thiết bật negative cache; rate limiting và bounded outbound calls có thể là giải pháp phù hợp hơn.

## 11. Ví dụ decorator cache dương TTL ngắn

Spring Security có extension point `OpaqueTokenIntrospector`. Có thể bọc một introspector remote bằng một decorator để tạo cache theo chính sách ứng dụng.

Ví dụ dưới đây chỉ cache positive result có claim `exp` đọc được, dùng HMAC token key và TTL tối đa 10 giây. Không cache exception hoặc token inactive.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

~~~java
package com.example.orders.security;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ShortTtlCachedIntrospector
        implements OpaqueTokenIntrospector {

    private static final Duration TTL = Duration.ofSeconds(10);

    private final OpaqueTokenIntrospector delegate;
    private final SecretKeySpec cacheKeySecret;
    private final Cache<String, Entry> cache =
        Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(TTL)
            .build();

    public ShortTtlCachedIntrospector(
            OpaqueTokenIntrospector delegate,
            byte[] hmacSecret) {

        if (hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                "Cache HMAC secret must contain at least 32 bytes");
        }

        this.delegate = delegate;
        this.cacheKeySecret =
            new SecretKeySpec(hmacSecret.clone(), "HmacSHA256");
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        Instant now = Instant.now();
        String key = keyedHash(token);
        Entry cached = cache.getIfPresent(key);

        if (cached != null) {
            if (now.isBefore(cached.validUntil())) {
                return cached.principal();
            }
            cache.invalidate(key);
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token); // remote call / active check

        Instant exp = expiration(principal);

        if (exp != null && !exp.isAfter(now)) {
            throw new BadOpaqueTokenException("Token expired");
        }

        // Không cache khi AS không trả exp hoặc exp sai kiểu.
        if (exp == null) {
            return principal;
        }

        Instant until = now.plus(TTL);
        if (exp.isBefore(until)) {
            until = exp;
        }

        if (until.isAfter(now)) {
            cache.put(key, new Entry(principal, until));
        }

        return principal;
    }

    private static Instant expiration(
            OAuth2AuthenticatedPrincipal principal) {
        Object raw = principal.getAttribute("exp");

        if (raw instanceof Instant instant) {
            return instant;
        }
        if (raw instanceof Number seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        return null;
    }

    private String keyedHash(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(cacheKeySecret);

            byte[] hashed =
                mac.doFinal(token.getBytes(StandardCharsets.UTF_8));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(hashed);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "Cannot build cache lookup key", ex);
        }
    }

    private record Entry(
        OAuth2AuthenticatedPrincipal principal,
        Instant validUntil
    ) {}
}
~~~

Đây là **mẫu minh họa**, không phải thư viện cache production hoàn chỉnh. Khi triển khai thật, cần thêm:

- Cấu hình clock skew và policy expiry phù hợp.
- Defensive copy nếu attributes/principal mutable.
- Bảo vệ cache và bí mật HMAC.
- Coalescing cùng token khi nhiều thread đồng thời cache miss.
- Observability hit/miss/stale.
- Quy tắc invalidation khi role/policy thay đổi.
- Test revoke-to-deny và key rotation của cache-secret.
- Đánh giá việc dùng cache dương cho endpoints có độ nhạy khác nhau.

Code dùng **Caffeine local per process**. Những replicas khác có cache riêng, nên cùng token có thể được introspect ở thời điểm khác nhau.

### 11.1. Nối decorator vào Spring Security

~~~java
package com.example.orders.security;

import java.util.Base64;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class CachedIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret,
            @Value("${app.security.cache-key-base64}") String keyBase64) {

        OpaqueTokenIntrospector remote =
            SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new ShortTtlCachedIntrospector(
            remote,
            Base64.getDecoder().decode(keyBase64));
    }
}
~~~

YAML:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
    cache-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_BASE64}
~~~

`INTROSPECTION_CACHE_HMAC_KEY_BASE64` phải là Base64 của một secret ngẫu nhiên đủ dài và được bảo vệ. Đây là một **cấu hình thay thế** cho bean introspector riêng ở phần timeout; không đăng ký cả hai `OpaqueTokenIntrospector` beans mà không wiring rõ.

Nếu cần **vừa HTTP timeout riêng vừa cache**, dùng một remote `SpringOpaqueTokenIntrospector` đã cấu hình RestOperations ở phần 7 làm delegate của `ShortTtlCachedIntrospector`.

**Lưu ý:** khi tự cung cấp `OpaqueTokenIntrospector` bean, Spring Boot thường nhường cho bean đó; lúc này ứng dụng phải tự bảo đảm client authentication, timeout, caching và các validation theo contract.

## 12. Vì sao cache principal cũng có thể giữ quyền cũ?

Khi introspection trả:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

Resource Server ánh xạ thành principal/authorities. Nếu admin gỡ scope `orders.write` ở AS nhưng token vẫn active, một cache entry cũ có thể tiếp tục giữ `SCOPE_orders.write`.

Ngay cả không cache tại RS, AS có thể giữ scope snapshot của token đến `exp`. Vì vậy cần phân biệt:

- **Token revocation:** AS làm token inactive.
- **Claim/entitlement update:** AS có phản ánh thay đổi ngay qua introspection không?
- **Local authorization:** API có cần kiểm tra quyền dữ liệu hiện tại không?

Với thao tác nhạy cảm, không để một principal cache dương thay thế kiểm tra owner/tenant/ACL trong database.

## 13. Có nên cache trên mọi endpoint?

Không nhất thiết.

### 13.1. Endpoint ít nhạy cảm, đọc nhiều

Với `GET /api/catalog` và scope `catalog.read`, tổ chức có thể cho phép cache introspection TTL rất ngắn để giảm latency và tải AS, **nếu** chấp nhận rõ revocation window tương ứng.

### 13.2. Endpoint phê duyệt hoặc tài chính

Với:

~~~http
POST /api/orders/42/approve
Authorization: Bearer <ACCESS_TOKEN>
~~~

có thể cần:

- Không dùng positive cache hoặc luôn thực hiện online active check.
- Kiểm tra local entitlement mới nhất.
- Kiểm tra trạng thái approval/owner/tenant ngay trong transaction.
- Step-up authentication hoặc token lifetime ngắn nếu policy yêu cầu.
- Policy fail closed khi không xác minh được trạng thái.

Một introspector cache được bật toàn cục có thể ảnh hưởng mọi endpoint trong chain. Nếu chia chains theo mức độ nhạy cảm, cần thiết kế `securityMatcher`/`@Order` đúng: Spring Security chọn **chain đầu tiên khớp request**. Tránh một chain tổng quát có cache bắt toàn bộ endpoints trước chain đặc biệt.

## 14. Audience, scope và quyền nghiệp vụ sau introspection

`active:true` chưa đủ nếu API còn yêu cầu token được cấp cho chính nó. AS có thể trả:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "payments.read"
}
~~~

Orders API cần kiểm tra audience theo hợp đồng, thay vì tin mọi token active. Nhưng `aud` không bắt buộc trong mọi introspection response, nên phải thống nhất profile với Authorization Server; không tự giả định provider luôn trả `aud`.

### 14.1. Bọc introspector để kiểm tra audience

~~~java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public AudienceCheckingIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object aud = principal.getAttribute("aud");

        boolean valid =
            "orders-api".equals(aud)
            || (aud instanceof Collection<?> values
                && values.contains("orders-api"));

        if (!valid) {
            throw new BadOpaqueTokenException(
                "Access token not intended for Orders API");
        }

        return principal;
    }
}
~~~

Đây là **contract riêng** yêu cầu `aud` trong introspection response; token thiếu `aud` sẽ bị từ chối. Nếu issuer không cung cấp `aud`, cần thiết kế một ràng buộc resource khác được AS bảo đảm, không tự bỏ policy trong môi trường nhiều APIs.

Khi kết hợp cache, nên dùng:

~~~text
Remote introspection
   -> validate required token attributes/audience
   -> optional positive cache với TTL được phê duyệt
   -> OpaqueTokenAuthenticationProvider
~~~

Không cache principal chưa qua contract validation. Khi business policy đổi, cần xem xét invalidation của cache đang giữ quyết định cũ.

### 14.2. Scope không thay thế quyền tenant

Nếu token active và có `SCOPE_orders.read` nhưng order 42 thuộc tenant khác, API vẫn cần từ chối. Một chính sách tham khảo:

~~~text
ALLOW_READ_ORDER =
    token active
    AND intended for Orders API
    AND SCOPE_orders.read
    AND local entitlement allows READ
    AND order belongs to allowed tenant/owner
~~~

Method security/service có thể bổ sung những điều kiện này; không dùng header `X-Tenant` hoặc query parameter do client tự gửi để cấp quyền.

## 15. Availability khi bật cache

Nếu AS outage:

~~~text
Token A: cache hit và chưa hết TTL -> có thể tiếp tục theo policy
Token B: cache miss -> không thể introspect -> fail closed
~~~

Sự khác biệt này là một hệ quả của cache, **không** phải bằng chứng rằng Resource Server vẫn có thể xác thực mọi token khi AS offline.

Đặc biệt cần tránh:

- **Stale-if-error vô thời hạn:** dùng positive result đã hết TTL khi AS down.
- **Stale-while-revalidate không có giới hạn:** tiếp tục chấp nhận token đã revoke trong lúc retry.
- **Fail open mặc định:** nếu HTTP client timeout thì coi `active:true`.
- **Chuyển network exception thành `active:false` rồi negative-cache:** đánh đồng lỗi hạ tầng với token invalid.

Nếu phải thiết kế stale fallback cho một use case đặc biệt, cần threat model, giới hạn thời gian cứng, cách phát hiện revoke và test chứng minh không mở quyền ngoài hợp đồng.

## 16. Cảnh giác token-spray và request amplification

Attacker không cần access token hợp lệ để gây nhiều introspection calls. Mỗi chuỗi ngẫu nhiên trong header Bearer có thể kích hoạt HTTP POST tới AS.

Các biện pháp:

1. Rate limiting ở edge/API.
2. Thời gian connect/read có giới hạn.
3. Outbound concurrency limit để tránh nghẽn pool/thread.
4. Retry budgets, không retry `active:false`.
5. Bounded cache size cho cả positive và negative entries.
6. Cảnh báo đột biến unique token attempts.
7. Phối hợp AS rate limits và capacity.
8. Không ghi token thô trong logs của gateway hoặc HTTP client.

Không tạo cache key từ toàn bộ token trong hệ logging/metrics hoặc biến `Authorization` thành tag có cardinality cao.

## 17. Metrics và tracing cần theo dõi

| Quan sát | Ý nghĩa |
|---|---|
| Introspection requests/sec | Tải AS do Resource Servers tạo |
| Introspection latency p50/p95/p99 | Tail latency authentication |
| Connect/read timeouts | Network/AS không đáp ứng SLO |
| Introspection HTTP 401/403 | Có thể là lỗi client auth/config |
| Introspection HTTP 429/5xx | Rate limit hoặc sự cố AS |
| `active:false` count | Token inactive được phát hiện |
| Positive-cache hit/miss | Mức độ giảm remote calls |
| Cache age/TTL | Độ stale mà API đang chấp nhận |
| Concurrent outbound calls | Nguy cơ nghẽn tài nguyên |
| End-to-end API p95/p99 | Ảnh hưởng thực tế tới client |
| Revoke-to-deny latency | Độ trễ từ revoke đến request bị từ chối |
| 401/403 theo policy | Phân biệt invalid token và thiếu scope |

Đây là các **chỉ số nên instrument**, không có nghĩa Spring Security luôn expose sẵn đúng metric names. Có thể dùng tracing span riêng cho POST introspection, nhưng phải redact request body chứa token và Authorization header chứa client secret.

### 17.1. Theo dõi request path

~~~text
HTTP GET /api/orders
  -> BearerTokenAuthenticationFilter
     -> OpaqueTokenIntrospector
        -> POST /oauth2/introspect
  -> AuthorizationFilter
  -> OrdersController
  -> Database
~~~

Nếu latency spike, trace giúp biết thời gian bị giữ tại AS hay business logic. Không bật full HTTP wire logging ở production khi nó có thể ghi token/secret.

## 18. Ma trận kiểm thử

| Test case | Điều cần xác minh |
|---|---|
| Token active, đúng scope | Authentication thành công và authorization cho phép |
| `active:false` | Resource Server từ chối token |
| Token không có | Endpoint protected trả challenge phù hợp |
| Token active nhưng thiếu scope | Thường 403 |
| Token active nhưng sai audience | Từ chối theo contract |
| Connect timeout | Không fail open |
| Read timeout | Không fail open; có metric phân biệt |
| AS trả 401 do client secret sai | Phát hiện lỗi infrastructure/config |
| AS trả 429 | Không retry vô hạn |
| AS trả 500 | Không chấp nhận token chưa xác minh |
| Cache hit trước revoke | Quan sát thời gian cache còn cho phép |
| Cache hết TTL sau revoke | Hỏi AS và từ chối khi `active:false` |
| Cache entry có `exp` đã qua | Không sử dụng entry dù TTL chưa hết |
| Introspection không trả `exp` | Không cache dương nếu policy yêu cầu exp |
| AS cập nhật scope | Cache principal không kéo dài quá cửa sổ đã cam kết |
| Nhiều replicas | Mỗi cache local có thể khác trạng thái |
| Token-spray nhiều giá trị lạ | Cache/RPS/memory vẫn có giới hạn |
| User đổi tenant/ACL | Service vẫn từ chối quyền không hợp lệ |
| Request được authorize ngay trước revoke | Đánh giá hành vi in-flight theo policy |

Khi viết integration tests, có thể sử dụng **mock introspection HTTP server** trong môi trường test để trả lần lượt `active:true` và `active:false`, chủ động tạo timeout hoặc HTTP 500. Cần kiểm tra qua Spring Security filter chain thật, không chỉ gọi controller với mock principal.

### 18.1. Không nhầm test authorities với test introspection

Một test MockMvc đã inject `Authentication` có thể chứng minh quy tắc `hasAuthority`, nhưng **không chứng minh HTTP introspection được gọi, timeout hoạt động hoặc cache TTL phản ánh revoke**.

Nên tách:

- Unit test cho decorator cache và audience validation.
- HTTP client test với introspection mock endpoint.
- Integration test qua `BearerTokenAuthenticationFilter`.
- Load/chaos test cho AS outage và tail latency.
- Revoke-to-deny test theo SLO của tổ chức.

## 19. Bài tập revoke-to-deny

Giả sử:

~~~text
Opaque introspection enabled
Positive cache TTL = 15 seconds
AS propagation delay = nonzero
Token exp = còn 20 phút
API endpoint = GET /api/orders/42
~~~

Dòng thời gian giả định:

~~~text
10:00:00  API introspects T -> active=true, ghi cache
10:00:03  Admin revoke T
10:00:04  Request với T đến API -> có thể cache hit
10:00:15  Cache entry hết TTL
10:00:16  API introspects T lần nữa
~~~

Nếu AS đã nhận revoke ở `10:00:16` thì request bị từ chối. Nếu AS vẫn trả active true do replication lag, một cache entry mới có thể tiếp tục làm chậm revoke-to-deny.

Vì vậy **TTL 15 giây không bảo đảm toàn hệ thống phản ánh revoke trong không quá 15 giây**. Cần xác định:

1. Khi nào AS ghi nhận revoke?
2. Introspection node nào phục vụ request và consistency ra sao?
3. Có cache khác trong gateway/AS không?
4. Resource Server dùng local/shared cache ở đâu?
5. Có invalidate theo event không và nếu mất event thì sao?
6. Request in-flight có được hoàn thành không?
7. Business operation có kiểm tra entitlement hiện thời trước khi commit không?

Revocation freshness là **đặc tính end-to-end**, không chỉ một TTL tại Resource Server.

## 20. Runbook chẩn đoán sự cố

### 20.1. API chậm, database bình thường

Kiểm tra:

- Latency p95/p99 của POST introspection.
- Cache hit/miss và outbound call count.
- Connect/read timeout và connection pool.
- DNS/TLS/proxy/service mesh.
- AS token store latency/rate limits.
- Retry amplification và số replicas cùng gọi AS.
- Correlation giữa peak RPS và lỗi introspection.

Không tăng timeout vô hạn. SLO của API và deadline tổng phải phù hợp ngân sách authentication.

### 20.2. Nhiều 401 sau secret rotation

Phân biệt `active:false` với lỗi credential của Resource Server. Kiểm tra client ID/secret, authentication method, TLS và quyền introspection. Không mặc định yêu cầu người dùng đăng nhập lại nếu AS đang từ chối **client authentication của API**.

### 20.3. Token đã revoke vẫn gọi được

Kiểm tra:

- AS có thực sự revoke access token T đang được dùng không?
- AS introspection có phản ánh revoke chưa?
- API có cache `active:true` chưa hết TTL không?
- Có gateway/AS cache khác không?
- Có request in-flight từ trước khi revoke không?
- Có security chain nào verify JWT offline hoặc bypass opaque introspection không?
- Có service method nào bỏ qua authorization không?

Nếu contract yêu cầu revoke nhanh, không tự kéo dài cache TTL hoặc bật stale-while-revalidate để che sự cố.

### 20.4. AS trả active true nhưng API 403

Điều này có thể đúng: token hợp lệ nhưng thiếu `SCOPE_orders.read`, hoặc local entitlement/owner/tenant policy từ chối. Kiểm tra scope mapping và authorization, không tự thêm scope vào principal nếu AS không cấp.

## 21. Những nhầm lẫn cần tránh

### “Opaque token luôn được revoke ngay lập tức”

Không. AS phải cập nhật và trả trạng thái mới; RS phải hỏi lại; replication và cache có thể làm trễ.

### “Introspection 200 nghĩa token hợp lệ”

Không. HTTP 200 với `{"active":false}` là một kết quả hoàn toàn hợp lệ.

### “AS introspection trả 401 nghĩa user token chắc chắn sai”

Không. Có thể credential Resource Server dùng gọi AS không hợp lệ.

### “Cache dương vừa giữ latency thấp vừa bảo đảm revoke tức thì”

Không nếu không có cơ chế invalidation/consistency bổ sung với contract rõ. Cache càng lâu, nguy cơ stale càng lớn.

### “AS down thì có thể chấp nhận token cũ vô hạn”

Đó là fail open. Chỉ được dùng entry trong giới hạn được phê duyệt; quá hạn thì phải có quyết định tin cậy mới.

### “Opaque token không cần scope/audience check”

`active:true` không tự cho phép truy cập mọi API/tài nguyên. Cần kiểm tra audience theo hợp đồng, scope và tenant/ownership.

### “JWT luôn hiệu quả hơn opaque”

JWT offline giảm network dependency nhưng không tự phản ánh revoke sớm. Opaque introspection giải quyết nhu cầu khác với chi phí mạng.

### “Cache JWKS dùng chung cho opaque introspection”

Không. JWKS cache chứa public signing keys của JWS; opaque cache chứa quyết định `active`/principal đã introspect.

### “Không cần rate limit vì token sai sẽ bị từ chối”

Sai. Token sai vẫn có thể kích hoạt remote introspection và gây tải AS.

## 22. Ma trận chọn chiến lược

| Yêu cầu chính | Cách tiếp cận |
|---|---|
| Revoke mới nhất theo AS là ưu tiên số một | Introspection mỗi request, không positive cache |
| RPS cao và cho phép một cửa sổ stale nhỏ | Positive cache TTL ngắn, cap theo `exp` |
| Cần khả năng chịu lỗi AS tốt hơn | Nâng availability AS, tối ưu HTTP timeout/bulkhead, fail closed |
| Muốn giảm tải nhưng revoke rất nhanh | Đánh giá push invalidation + reconciliation |
| Thao tác cực nhạy cảm | Online active check và local entitlement/transaction policy |
| Cần authentication chủ yếu offline | JWT signature validation, bổ sung revocation strategy nếu cần |
| Token có format JWT nhưng AS yêu cầu introspection | Dùng opaque mode nếu AS hỗ trợ |
| Nhiều Resource Servers / replicas | Thiết kế cache local/shared và AS capacity |
| AS không trả audience | Thống nhất resource-specific contract/validation thay thế |
| Có lượng token-spray | Rate limit, bounded cache và outbound concurrency |
| Cần audit revoke-to-deny | Test timing từ AS đến RS, không đo chỉ riêng TTL |

## 23. Ghi nhớ

- **Opaque token introspection** đưa quyết định token active/inactive về Authorization Server. Nó có thể phản ánh thu hồi tốt hơn JWT verification offline nếu được gọi lại và AS cập nhật trạng thái đúng.
- **Mỗi remote introspection call** là một khoản latency và một dependency availability. Theo dõi p95/p99, RPS, timeouts và rate limits.
- **Không cache** cho trạng thái mới nhất theo AS nhưng phụ thuộc trực tiếp vào endpoint trên mỗi request cần xác minh.
- **Positive cache** giảm tải/latency nhưng tạo **revocation window**. Giới hạn TTL, `exp`, size và xác định rõ các bước invalidation.
- **Không fail open** khi mất AS. Phân loại rõ token inactive với HTTP client timeout/5xx hoặc sai introspection credential.
- `active:true` không thay thế **audience, scope, entitlement và tenant/owner/ACL**.
- Spring Security Servlet cho phép tùy chỉnh qua **`OpaqueTokenIntrospector`**, HTTP client và decorator cache; phải giữ nguyên trust contract.
- Revocation freshness phụ thuộc **AS, các cache, propagation, request timing và business authorization**, không chỉ một giá trị TTL.

### Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [Spring Security API — RestClientOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html)
- [Spring Security Reference — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)

