# Xử lý token không hoạt động, lỗi mạng và nhà cung cấp không sẵn sàng với Spring Security Reactive Opaque Token

> **Module:** Spring Security - reactive  
> **Chủ đề cha:** Resource Server Opaque  
> **Phạm vi:** Spring WebFlux Resource Server xác thực Bearer token bằng OAuth 2.0 Token Introspection (RFC 7662).  
> **Mục tiêu:** Phân biệt token `active=false` với lỗi HTTP/mạng của introspection endpoint; thiết kế **fail closed**, timeout, retry, circuit breaker, caching và status/error contract; triển khai ví dụ Java 17+ với `ReactiveOpaqueTokenIntrospector` và kiểm thử những tình huống xấu.

## 1. Bài toán: một access token nhưng nhiều kiểu thất bại

Ứng dụng WebFlux `reports-api` nhận:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.com
Authorization: Bearer opaque-random-token
~~~

Token không cần có cấu trúc JWT. Resource Server gửi token đến **trusted introspection endpoint** của Authorization Server để hỏi trạng thái và claims. Tại đây, các trường hợp sau nhìn có vẻ đều “không đăng nhập được”, nhưng nguyên nhân và phương án xử lý hoàn toàn khác:

1. **Token thực sự không hoạt động:** không tồn tại, hết hạn, bị revoke hoặc resource server không được biết token → introspection response hợp lệ có `"active": false`.
2. **Token hoạt động nhưng không có quyền:** `"active": true`, nhưng `scope` thiếu `reports.read` hoặc sai tenant/owner.
3. **Introspection service lỗi:** DNS fail, connection refused, connect/read timeout, TLS handshake error, HTTP 502/503/504, JSON không đúng hợp đồng.
4. **Client credential của Resource Server sai:** introspection endpoint trả **HTTP 401/403** cho **chính request introspection**.
5. **Service đang quá tải:** nhiều request đồng thời, rate limit 429, retries khuếch đại lượng truy vấn hoặc IdP downtime diện rộng.

**Quy tắc bảo mật:** Khi không thể chứng minh token đang hợp lệ, **không tạo Authentication thành công**. “IdP không phản hồi” **không** đồng nghĩa “token active=true”; không dùng tài khoản anonymous/fallback principal để tiếp tục xử lý dữ liệu riêng tư.

## 2. Opaque Token và JWT có thể dùng cùng introspection

Opaque access token thường là chuỗi khó đoán, không chứa dữ liệu người dùng có thể đọc tại API. OAuth 2.0 RFC 7662 cho phép Resource Server gửi token và nhận metadata về `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`, v.v. khi IdP cho phép.

Spring Security gọi tính năng này là “opaque token” vì cơ chế xác minh **qua mạng**; trên thực tế, token có thể là JWT nhưng vẫn được introspect để kiểm tra trạng thái/revocation với nhà phát hành. Resource Server **không nên tự giải mã JWT rồi tin claims** nếu chính sách của hệ thống yêu cầu xác thực live với endpoint introspection.

| Tiêu chí | Opaque introspection | Offline JWT signature |
| --- | --- | --- |
| Cách xác thực | Gọi Authorization Server qua HTTP | Xác minh JWS bằng trusted public key/JWKS |
| Revocation | Có thể biết trạng thái mới theo từng lần introspect | Không tự biết thu hồi trước `exp` |
| Phụ thuộc IdP mỗi request | Có nếu không cache | Không cho từng request nếu có key cache |
| Nguy cơ khi IdP outage | Authentication mới bị ảnh hưởng | Có thể tiếp tục kiểm chứng JWT bằng key trusted trong cache |
| Dữ liệu quyền | Do introspection response cung cấp | Từ claims đã xác minh chữ ký |
| Caching | Phải cân nhắc stale/revocation | Key caching khác token-active caching |

Không tự thay từ introspection sang “parse JWT local” khi IdP outage để né downtime. Đó là **thay đổi trust contract**, có thể bỏ qua lệnh revoke và thiếu kiểm tra audience/claim-profile.

## 3. Luồng Request → Introspection → Authentication

~~~mermaid
flowchart TD
    A["GET /api/reports + Bearer"] --> B["SecurityWebFilterChain"]
    B --> C["OpaqueTokenReactiveAuthenticationManager"]
    C --> D["ReactiveOpaqueTokenIntrospector"]
    D --> E{"IdP trả loại kết quả nào?"}
    E -->|"HTTP 200, active=false"| F["Token không hợp lệ: 401"]
    E -->|"HTTP 200, active=true"| G["Tạo OAuth2AuthenticatedPrincipal"]
    E -->|"Timeout, 429, 5xx, mạng lỗi"| H["Không xác thực: fail closed"]
    E -->|"Introspection request 401"| I["Sai credentials/config Resource Server"]
    G --> J{"Scope/tenant/owner cho phép?"}
    J -->|"Không"| K["403 / 404 theo API contract"]
    J -->|"Có"| L["Controller / domain service"]
    H --> M["Thông báo lỗi phụ thuộc theo chính sách, có thể thiết kế 503"]
    I --> M
~~~

**Có hai kết nối HTTP khác nhau:**

- **Client → Resource Server:** dùng `Authorization: Bearer <access-token>`.
- **Resource Server → Introspection Endpoint:** gửi token dưới dạng form parameter `token=...`, và thường dùng **client ID/secret của Resource Server** để xác thực với IdP.

HTTP status của hai kết nối **không được nhập làm một**. Một response 401 từ introspection endpoint là thất bại xác thực client gọi introspection; trong khi một token đã bị revoke thường trả **200 + active=false**.

## 4. RFC 7662: active=false là một response thành công ở tầng HTTP

Request introspection dạng chuẩn:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-access-token>&token_type_hint=access_token
~~~

Đây là minh họa protocol; không đưa token hoặc Basic credential thật vào README, screenshots hay log. Tùy IdP, client authentication có thể dùng phương thức khác được thỏa thuận.

Với token đang hoạt động:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "alice",
  "scope": "reports.read reports.export",
  "client_id": "report-frontend",
  "aud": "reports-api"
}
~~~

Với token không hoạt động:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

Theo **RFC 7662 §2.2**, khi token không hoạt động, không tồn tại hoặc Resource Server không được xem token đó, Authorization Server **phải trả `active=false`** cho introspection request được xác thực hợp lệ. RFC khuyến nghị không tiết lộ thêm lý do token không active. Không trả cho client bên ngoài thông tin chi tiết kiểu “token bị revoke lúc 10:02 bởi admin”.

**Không diễn giải ngược:** nếu HTTP 200 nhưng body thiếu `active`, malformed JSON hoặc `active` là kiểu dữ liệu sai, đó là response **không hợp lệ**, không được coi là token active. Nếu body là `{"active":"true"}` (chuỗi), không nên tự coi tương đương boolean true trừ khi một cơ chế tương thích đã được đánh giá rõ ràng.

## 5. HTTP 401 tại introspection endpoint có nghĩa gì?

RFC 7662 §2.3 nêu: nếu Resource Server dùng OAuth2 client credentials để xác thực tới introspection endpoint và credential này không hợp lệ, endpoint trả HTTP 401.

Phân biệt rõ:

| Nơi thấy lỗi | Ví dụ | Ý nghĩa có thể |
| --- | --- | --- |
| **Introspection endpoint trả HTTP 200** | `{"active":false}` | Access token không hoạt động hoặc Resource Server không được biết token |
| **Introspection endpoint trả HTTP 401** | `invalid_client` | Client ID/secret/method của Resource Server sai/hết hạn |
| **Introspection endpoint trả HTTP 403** | Không đủ quyền gọi introspection | Resource Server account không được phép hỏi trạng thái token |
| **Introspection endpoint trả HTTP 429** | Rate limit | Bị giới hạn tải, chưa xác minh trạng thái token |
| **Introspection endpoint trả HTTP 502/503/504** | IdP/gateway lỗi | Không có kết quả xác minh đáng tin |
| **Client của API nhận HTTP 401** | `WWW-Authenticate: Bearer` | Authentication thất bại ở Resource Server; không phản ánh nguyên văn status upstream |
| **Client của API nhận HTTP 403** | Thiếu `SCOPE_reports.read` | Authentication có thể đã thành công nhưng authorization không đủ |

**Không tự chuyển mọi upstream HTTP 401 thành “token của end-user đã hết hạn”.** Phải kiểm tra resource-server introspection credentials, OAuth2 client-auth method, secret rotation, endpoint URL và chính sách IdP. Ngược lại, cũng không gắn `active=true` khi credentials introspection sai chỉ để tránh hệ thống bị gián đoạn.

## 6. Phân loại lỗi trước khi áp dụng retry

| Nhóm | Tín hiệu | Retry tự động? | Quyết định bảo mật |
| --- | --- | --- | --- |
| Token inactive | Valid 200, `active=false` | **Không** | Từ chối authentication |
| Token malformed / thiếu Bearer | Không parse được inbound header | **Không** | 401 |
| Token active nhưng scope thiếu | `active=true`, scope không đủ | **Không** | 403 |
| Upstream 401/403 | Sai client credentials/quyền introspection | **Không retry nóng** | Fail closed, alert cấu hình |
| DNS/connect refused | Lỗi kết nối | Retry rất giới hạn nếu policy cho phép | Fail closed |
| Timeout | Không nhận response trong budget | Retry rất giới hạn, có total deadline | Fail closed |
| HTTP 429 | Rate limited | Chỉ theo Retry-After/budget, tránh storm | Fail closed |
| HTTP 5xx | IdP outage hoặc proxy lỗi | Có thể bounded retry cho lỗi transient | Fail closed |
| Body JSON sai/thiếu active | Lỗi protocol/schema | Thường không, cần alert | Fail closed |
| TLS certificate error | Không tin endpoint | **Không** | Fail closed, sửa TLS/trust |
| Circuit breaker OPEN | IdP được đánh giá không khả dụng | Không gọi mạng từng request | Fail closed |

Retry một **POST introspection** thường không gây thay đổi dữ liệu theo giao thức, nhưng vẫn tạo tải, cost và rate limit. Không tự retry theo mọi exception hoặc retry cho `active=false`. Thử lại hữu ích chỉ khi dự đoán lỗi transient, có **giới hạn tổng thời gian**, concurrency và backoff/jitter.

## 7. Mức tối thiểu: cấu hình Spring Boot

Một Resource Server Reactive xác thực opaque token có thể bắt đầu bằng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: resource-server-client
          client-secret: <read-from-secret-store>
~~~

Cấu hình trên là minh họa; không commit client-secret thật trong YAML. Spring Boot có thể auto-configure `ReactiveOpaqueTokenIntrospector` khi có WebFlux/OAuth2 Resource Server và properties này.

Filter HTTP:

~~~java
@Bean
SecurityWebFilterChain chain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/health").permitAll()
            .pathMatchers("/api/reports").hasAuthority(
                "SCOPE_reports.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults()))
        .build();
}
~~~

Đây là **snippet** (thiếu imports/class); project runnable được trình bày từ mục 11. Khi introspection trả `active=true` và scope string, Spring thường map mỗi scope thành authority prefix `SCOPE_`. Khi active=false, không được cấp principal.

Đừng mặc định introspection client chịu được outage tốt chỉ vì cấu hình ngắn. Khi latency/SLO quan trọng, cần timeout, observability, bulkhead, circuit breaker và chính sách HTTP response được thiết kế/test.

## 8. Fail closed không đồng nghĩa mọi lỗi phải cùng một HTTP status

**Quyết định bảo mật:** mọi đường lỗi introspection khiến request **không** được authenticated. Nhưng cách phản hồi cho client có thể phụ thuộc cấu hình Spring Security và error handling:
- Token không hợp lệ (`active=false`): **401 Unauthorized** và Bearer challenge phù hợp.
- Token active nhưng thiếu scope: **403 Forbidden**.
- Introspection service down: có thể trả một **5xx** hoặc một lỗi authentication khác theo pipeline/config; đừng khẳng định Spring Security mặc định luôn trả 503.
- Nếu API muốn **503 Service Unavailable** cho outage, phải triển khai đường ánh xạ lỗi **rõ ràng** ở authentication/error boundary, kiểm thử end-to-end và đảm bảo không biến exception thành `Authentication` thành công. Có thể thêm `Retry-After` chỉ nếu hệ thống có thời gian khôi phục đáng tin.
- Upstream 401 do secret sai: lỗi cấu hình nội bộ; không nên trả client secret/IdP error body ra internet.

**Tại sao phân biệt?** 401 có thể khiến mobile/browser cố “đăng nhập lại” vô ích; 503 cho biết dependency chưa sẵn sàng và có thể retry sau. Nhưng **khác mã lỗi không được làm khác nguyên tắc từ chối truy cập**. Thiết kế contract nhất quán với API gateway, Spring Security authentication entry point, metrics và clients.

Tránh một `onErrorResume(ex -> Mono.just(previousPrincipal))` ở introspector. Đây là kiểu **fail open** nguy hiểm nhất: IdP outage làm quyền bị revoke trước đó có thể được khôi phục lại.

## 9. Timeout: giới hạn độ trễ của Resource Server

Một request API chờ introspection sẽ giữ tài nguyên trong lúc phụ thuộc mạng. Nếu IdP chậm 30 giây, user có thể thấy ứng dụng “treo” dù controller rất nhanh.

Thiết kế latency budget ví dụ (không phải giá trị áp dụng cho mọi hệ thống):

~~~text
API total timeout budget:                1500 ms
Introspection connect timeout:             250 ms
Introspection response/read timeout:       800 ms
Reactor overall introspection deadline:   1000 ms
Remaining time:                           ~500 ms (routing/response)
~~~

Trong production, xác định budget bằng số liệu p95/p99, throughput, SLO và failure budget. Đừng tùy tiện đặt timeout 10 ms khiến hệ thống liên tục từ chối các token hợp lệ.

Có hai tầng:
- **HTTP client timeout:** connect timeout và response timeout của Reactor Netty hoặc WebClient connector.
- **Reactive deadline:** `Mono.timeout(Duration)` bao toàn bộ công việc introspection.

Timeout của Reactor **cancel subscription** khi hết giờ nhưng không đảm bảo mọi thao tác upstream đã ngừng ngay lập tức ở tầng network/proxy. Nên kết hợp HTTP client timeouts, connection pool limits và total request budgets.

## 10. Retry và circuit breaker trong authentication path

Retry hợp lý cần:
1. Chỉ retry lỗi mạng transient hoặc 5xx/429 có policy; **không** retry `BadOpaqueTokenException`.
2. Ít lần (ví dụ một retry), exponential backoff + jitter, tổng deadline.
3. Có giới hạn đồng thời, connection pool và bulkhead để tránh hàng nghìn request đồng loạt đổ vào IdP sau outage.
4. Đo tỷ lệ lỗi, số retry, service time và circuit state, không log raw Bearer token.
5. Khi breaker mở, **từ chối xác thực** ngay; tuyệt đối không cho phép user cũ đi qua.
6. Recovery qua half-open probes có quota nhỏ; chỉ cho token active được xác nhận bởi response hợp lệ.

~~~mermaid
flowchart TD
    A["Introspect token"] --> B{"Circuit OPEN?"}
    B -->|"Có"| X["Dependency unavailable → fail closed"]
    B -->|"Không"| C["Call IdP với bounded timeout"]
    C --> D{"Kết quả"}
    D -->|"active=false"| E["401; không retry"]
    D -->|"active=true"| F["Authn OK, kiểm tra scope/tenant"]
    D -->|"Transient 5xx/timeout"| G{"Còn retry budget?"}
    G -->|"Có"| H["Backoff/jitter + retry trong total deadline"]
    H --> C
    G -->|"Không"| X
    D -->|"401 client credentials"| I["Config alert, không retry nóng, fail closed"]
~~~

Không phải cứ gắn `retryWhen` là resilient. Tại auth path, một retry storm có thể làm authorization server chết nhanh hơn. Khi dùng Resilience4j/Spring Cloud Circuit Breaker, phải kiểm tra compatibility với Reactor và **loại trừ token inactive khỏi failure-rate breaker** nếu đó là authentication result bình thường, không phải dependency outage.

## 11. Dự án Java 17+ WebFlux minh họa

Project có ba nhóm chức năng:

- Inbound `SecurityWebFilterChain` bảo vệ API bằng opaque Bearer.
- `ReactiveOpaqueTokenIntrospector` thực hiện introspection và wrapper timeout, giữ nguyên lỗi token inactive.
- Kiểm thử: unit tests wrapper và WebTestClient test route/authorities. **Không dùng mock auth để khẳng định HTTP introspection đã chạy thành công.**

Bài dùng Spring Boot `3.3.13` và Spring Security 6.3.x để cố định ví dụ API constructor có sẵn ở nhánh đó. Dòng Spring Boot 3.3 đã hết OSS support; production phải dùng phiên bản còn hỗ trợ. Sang Spring Security 6.5+, API builder `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` được khuyến nghị; constructor cũ có thể bị deprecate. Đây là lựa chọn **phù hợp phiên bản**, không nên copy signature mù quáng giữa 6.3 và 7.x.

~~~text
opaque-introspection-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── OpaqueApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GuardedIntrospector.java
    │   │   └── ReportsController.java
    │   └── resources/application.yml
    └── test/java/demo/opaque/
        ├── GuardedIntrospectorTest.java
        └── OpaqueHttpSecurityTest.java
~~~

### 11.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>opaque-introspection-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
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
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
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

Không dùng `spring-boot-starter-web` vì lab là WebFlux. `spring-security-test` cho phép WebTestClient dùng `mockOpaqueToken()`; hỗ trợ test route nhưng **bỏ qua network introspection**.

### 11.2. OpaqueApplication.java

~~~java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
~~~

### 11.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  introspection:
    uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
    client-id: ${INTROSPECTION_CLIENT_ID:lab-api-client}
    client-secret: ${INTROSPECTION_CLIENT_SECRET:lab-placeholder-secret}
    overall-timeout: 800ms
~~~

`.invalid` là hostname dành cho ví dụ, **không tồn tại**. Project startup và unit tests không cần liên hệ endpoint đó, nhưng một Bearer token HTTP thật sẽ không thể được xác minh qua hostname giả; phải cấu hình IdP thật hoặc mock introspection server cho integration test.

Trong production, sử dụng secret manager/encrypted settings, HTTPS, server certificate validation và IdP introspection client credentials riêng, không dùng chung secret login của frontend. Không log Authorization inbound hoặc client-secret outbound.

## 12. SecurityConfig.java: Resource Server và introspector Bean

~~~java
package demo.opaque;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${lab.introspection.uri}") String uri,
            @Value("${lab.introspection.client-id}") String id,
            @Value("${lab.introspection.client-secret}") String secret,
            @Value("${lab.introspection.overall-timeout}")
            Duration timeout) {

        // API constructor thuộc Spring Security 6.3.x của lab.
        var delegate = new SpringReactiveOpaqueTokenIntrospector(
            uri, id, secret);

        return new GuardedIntrospector(delegate, timeout);
    }
}
~~~

**Những gì code này bảo đảm:**
- Bearer token được xử lý bởi OAuth2 Resource Server, không dùng login form/HTTP Basic/session credentials.
- Chỉ scope `reports.read` được gọi GET /api/reports; vẫn cần kiểm tra object/tenant trong use case thật.
- `ReactiveOpaqueTokenIntrospector` là Spring Bean thay cấu hình mặc định của Boot; không có hai competing beans.
- Phần wrapper giới hạn tổng thời gian introspection và **không chuyển lỗi thành principal**.
- `NoOpServerSecurityContextRepository` không lưu Authentication Bearer thành session.
- CSRF tắt **chỉ ở header-only Bearer API**; nếu sau này chấp nhận cookie/session/Basic auto-sent thì phải xem lại CSRF.

**Những gì code chưa tự làm:** circuit breaker, request coalescing, distributed cache, custom HTTP mapping 503, idempotency của nghiệp vụ, custom connect timeout. Các nội dung này là bước production hardening, cần triển khai và test riêng, không tuyên bố đã có chỉ nhờ wrapper.

## 13. GuardedIntrospector.java: deadline và giữ nguyên lỗi inactive

~~~java
package demo.opaque;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeoutException;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class GuardedIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;

    public GuardedIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline) {
        this.delegate = Objects.requireNonNull(delegate);
        this.deadline = Objects.requireNonNull(deadline);
        if (deadline.isZero() || deadline.isNegative()) {
            throw new IllegalArgumentException("deadline must be positive");
        }
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> delegate.introspect(token))
            .timeout(deadline)
            .onErrorMap(TimeoutException.class,
                ex -> new IntrospectionUnavailableException(
                    "Token introspection deadline exceeded", ex));
    }
}

final class IntrospectionUnavailableException extends RuntimeException {
    IntrospectionUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

**Tại sao sử dụng `Mono.defer`?** Mỗi subscription thực sự gọi delegate introspection đúng lúc, thay vì kích hoạt side effects đồng bộ trong giai đoạn assembly. Chỉ dùng `Mono.just(principal)` khi delegate đã xác minh token; không có fallback principal khi lỗi.

**Tại sao chỉ map TimeoutException?** Mục tiêu test minh họa phân biệt **deadline hết** với `BadOpaqueTokenException` (token inactive). Wrapper không làm biến dạng lỗi token không hợp lệ. Một số network/HTTP errors có thể đã được Spring introspector gói trong `OAuth2IntrospectionException`; các lỗi đó vẫn để stream fail, **không** tạo successful Authentication. Trong production muốn metrics/retry/status cụ thể cần phân loại exception hierarchy và root causes theo phiên bản đang dùng.

`IntrospectionUnavailableException` không tự động có nghĩa HTTP 503. Security filters có thể gói/lập lại lỗi authentication; mapping response phải được thêm/test tại authentication failure boundary hoặc gateway. Chỉ có **kết quả bảo mật fail closed** là kết luận có thể tin từ code trên.

## 14. ReportsController.java: chỉ trả dữ liệu khi đã authenticated

~~~java
package demo.opaque;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(Map.of("subject", principal.getName()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "report", "Visible with reports.read scope"));
    }
}
~~~

Khi token được introspect thành công và scope đúng, `GET /api/reports` sẽ trả JSON có key `report`. Controller không nhìn thấy token raw, không tự kết luận active từ chuỗi token, và không gắn principal từ cache chưa verify.

Trong API thật, service phải thêm authorization theo tenant/owner/action, kiểm tra payload và transaction cho các thao tác thay đổi dữ liệu. Scope `reports.read` không có nghĩa đọc toàn bộ báo cáo của mọi tổ chức.

## 15. Unit tests: phân biệt active, inactive và timeout

Đây là các tests **thực sự kiểm tra wrapper**, không gọi IdP thật. Tạo stub `ReactiveOpaqueTokenIntrospector` trả:
- `Mono.just(verifiedPrincipal)` cho active;
- `Mono.error(new BadOpaqueTokenException(...))` cho inactive;
- `Mono.never()` cho timeout;
- `Mono.error(new OAuth2IntrospectionException(...))` cho lỗi HTTP/protocol/network giả lập.

File `src/test/java/demo/opaque/GuardedIntrospectorTest.java`:

~~~java
package demo.opaque;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class GuardedIntrospectorTest {

    private OAuth2AuthenticatedPrincipal activePrincipal() {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "scope", "reports.read"),
            AuthorityUtils.createAuthorityList("SCOPE_reports.read"));
    }

    @Test
    void activeTokenReturnsVerifiedPrincipal() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.just(activePrincipal());

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("active"))
            .assertNext(principal ->
                assertEquals("alice", principal.getName()))
            .verifyComplete();
    }

    @Test
    void inactiveTokenRemainsAuthenticationFailure() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.error(
                new BadOpaqueTokenException("inactive token"));

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("inactive"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void neverRespondingProviderHitsDeadline() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.never();

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(50));

        StepVerifier.create(guarded.introspect("slow"))
            .expectError(IntrospectionUnavailableException.class)
            .verify();
    }

    @Test
    void providerProtocolFailureCannotProducePrincipal() {
        ReactiveOpaqueTokenIntrospector stub =
            token -> Mono.error(
                new OAuth2IntrospectionException(
                    "upstream introspection failure"));

        var guarded = new GuardedIntrospector(
            stub, Duration.ofMillis(200));

        StepVerifier.create(guarded.introspect("upstream-error"))
            .expectError(OAuth2IntrospectionException.class)
            .verify();
    }

    @Test
    void missingDeadlineIsRejectedAtConstruction() {
        org.junit.jupiter.api.Assertions.assertThrows(
            IllegalArgumentException.class,
            () -> new GuardedIntrospector(
                token -> Mono.empty(), Duration.ZERO));
    }
}
~~~

**Các assertions chứng minh:** active mới cho principal đi qua; inactive không bị đổi thành success; timeout đi tới exception riêng; lỗi introspection khác cũng không biến thành principal; deadline sai bị reject. Chúng **không chứng minh** HTTP request tới Authorization Server đã đúng Basic auth/form data, cũng không chứng minh status mapping 503.

Khi provider trả `active=false` trên mạng, `SpringReactiveOpaqueTokenIntrospector` chịu trách nhiệm phát signal token invalid. Unit test trên giả lập signal đó qua `BadOpaqueTokenException`. Muốn kiểm tra RFC 7662 response parse thật, cần fake HTTP IdP ở mục 19.

## 16. WebTestClient: phân quyền Resource Server không cần mạng

`mockOpaqueToken()` tạo `BearerTokenAuthentication` giả cho test request. **Nó bỏ qua introspection**, nên không chứng minh IdP đã trả active=true.

File `src/test/java/demo/opaque/OpaqueHttpSecurityTest.java`:

~~~java
package demo.opaque;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueHttpSecurityTest {

    @Autowired WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingBearerIsUnauthorized() {
        client.get().uri("/api/me")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void mockActiveUserCanReadOwnSubject() {
        client.mutateWith(mockOpaqueToken()
                .attributes(map -> map.put("sub", "alice")))
            .get().uri("/api/me")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void tokenWithInsufficientScopeIsForbidden() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")))
            .get().uri("/api/reports")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void tokenWithReportsScopeMayReadReports() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.report").exists();
    }

    @Test
    void unlistedRouteIsDenied() {
        client.mutateWith(mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/secret-admin")
            .exchange().expectStatus().isForbidden();
    }
}
~~~

**Phân biệt test:**
- `GuardedIntrospectorTest` tập trung vào Reactor error/timeout behaviors.
- `OpaqueHttpSecurityTest` tập trung vào HTTP routes/authorities, nhưng mock bypass network.
- Fake IdP integration test cần đo GET/POST trên actual WebFlux security chain mà **không dùng mockOpaqueToken**, để chứng minh inactive/active/upstream errors tác động tới endpoint thật.

Có tổng cộng **5 + 6 = 11 test methods** trong ví dụ. Bài không giả định Maven đã được chạy tại máy người đọc; nếu pin version/HTTP test behavior khác cần xác minh lại.

## 17. Chạy project và kỳ vọng

Tại thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

Kỳ vọng các tests chứng minh **không có fallback authentication** và kiểm tra scope đúng. Với `application.yml` trỏ tới `.invalid`, test mock không gọi nhà cung cấp; lỗi DNS chỉ xuất hiện nếu chạy **request chứa Bearer thật** mà không thay endpoint.

Chạy application:

~~~bash
mvn spring-boot:run
~~~

Request health:

~~~bash
curl -i "http://localhost:8080/public/health"
~~~

Expected JSON:

~~~json
{"status":"up"}
~~~

Request private không token:

~~~bash
curl -i "http://localhost:8080/api/reports"
~~~

Kỳ vọng 401. Nếu muốn request private có token hợp lệ, phải cấu hình introspection endpoint thật; không có token demo hardcoded trong project này.

**Không dùng `curl -k` ở môi trường thật** để bỏ TLS validation, và không đưa `Authorization: Bearer ...` vào shell history, Jenkins logs hay screenshots công khai.

## 18. Kiểm thử RFC 7662 với fake IdP

Để kiểm tra toàn bộ đường HTTP, hãy dựng một fake introspection server trong integration tests (WireMock, MockWebServer hoặc test HTTP server) đáp ứng các kịch bản sau, dùng endpoint/chứng chỉ do test kiểm soát:

| Fake IdP trả | Mong muốn từ Resource Server |
| --- | --- |
| 200 `{"active":true,"sub":"alice","scope":"reports.read"}` | Authentication thành công và route cho phép khi đủ scope |
| 200 `{"active":false}` | Authentication từ chối, **401** |
| 200 `{"active":true,"scope":"profile"}` | Authn hợp lệ nhưng route reports trả **403** |
| 200 malformed JSON | Không xác thực; lỗi dependency/protocol, không 200 |
| 200 missing active | Không xác thực; không giả định active |
| 401 upstream `invalid_client` | Không xác thực; cấu hình/secret lỗi, alert |
| 403 upstream | Không xác thực; quyền introspection thiếu |
| 429 upstream | Không xác thực, retry giới hạn theo policy |
| 500/502/503/504 upstream | Không xác thực, timeout/retry/breaker theo policy |
| Connect timeout/read timeout | Không xác thực, deadline và metrics |
| TLS wrong certificate | Không xác thực, không disable verification |
| Upstream return active=true sau revoked token | Theo kết quả endpoint hiện tại và cache policy; cần xác minh IdP contract |

**Đừng chỉ dùng** `mockOpaqueToken()` trong mọi integration tests, vì nó tạo principal trước khi introspection chạy. Gửi Bearer thật vào ứng dụng, cấu hình `introspection-uri` đến fake server, kiểm tra số request và HTTP response. Nếu muốn 503 cho outage, thêm custom error-handling policy và assert **chính xác 503** tại đây.

Khi kiểm thử, không ghi raw token trong test logs ở CI; dùng giá trị dummy sinh trong test và sanitize khi chụp request/response.

## 19. Timeout HTTP client chuyên biệt

Wrapper `Mono.timeout` bao tổng deadline, nhưng production cũng nên thiết lập HTTP connection/read timeouts. Với Spring WebFlux/Netty, cấu hình ở một `WebClient` riêng cho introspection:

~~~java
// Snippet mở rộng cho Spring Security phiên bản có constructor
// SpringReactiveOpaqueTokenIntrospector(String, WebClient).
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

HttpClient httpClient = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 250)
    .responseTimeout(Duration.ofMillis(800));

WebClient idpClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .defaultHeaders(h -> h.setBasicAuth(clientId, clientSecret))
    .build();

var delegate = new SpringReactiveOpaqueTokenIntrospector(
    introspectionUri, idpClient);
~~~

Đây là **snippet tùy chọn**, đặt trong configuration Bean, cần import `java.time.Duration` và inject `clientId`/`clientSecret`; không phải một file Java độc lập. Spring Security **6.3.x** có constructor `(String,WebClient)`. Không gắn Basic client credentials vào WebClient dùng chung khác; chỉ dùng client chuyên biệt tới endpoint IdP đã allowlist.

Nếu dùng phiên bản mới hơn có builder supporting WebClient customization, đọc javadoc phiên bản thực tế. Tránh hai request timeout policies xung đột vô ý. Sửa latency budget từ số đo, không copy con số 250/800 ms vào mọi production.

## 20. Caching active/inactive: đánh đổi hiệu năng và revocation

Introspection liên tục tạo tải lên IdP; caching có thể giảm latency nhưng gây stale authorization.

**Positive caching:** nếu lưu `active=true`, token đã revoke vẫn có thể được nhận **tới hết TTL cache**, ngay cả khi IdP đã trả inactive nếu gọi mới. Nếu hệ thống yêu cầu revoke tức thời, **không cache active** hoặc dùng push revocation/signal invalidation đáng tin. Nếu chấp nhận độ trễ revoke vài giây, ghi rõ business SLA.

**Negative caching:** lưu `active=false` trong thời gian rất ngắn có thể giảm token spray/abuse, nhưng cần giới hạn size và tránh attacker lấp bộ nhớ bằng vô số token ngẫu nhiên. Không cache một kết quả network failure như `active=false` rồi nhầm đó là kết luận của IdP.

Một cache key cần được cô lập theo issuer/tenant/resource/client context. Không lưu raw Bearer token làm key trong logs hoặc cache dashboard; có thể dùng keyed HMAC digest của token với secret riêng và tránh biến giá trị digest thành credential có thể tái sử dụng. Cache phải có eviction và protected storage.

**Cache TTL hợp lý:** không vượt quá `exp` của token khi có, trừ khi có contract đặc biệt; cân nhắc ít hơn revoke SLA và lifetime token. Token có thể không có exp trong introspection response — cần policy TTL chặt. Không có default “5 phút là an toàn” cho mọi ứng dụng.

**Không dùng stale-while-revalidate để cho private request tiếp tục** khi live introspection down, trừ khi business/security chủ động cho phép một mode degraded đã được đánh giá, với giới hạn rõ và không trái yêu cầu revoke. Lab này chọn **fail closed tuyệt đối**.

## 21. Circuit breaker, bulkhead và rate limiting

Một IdP outage trên vài phút có thể khiến Resource Server:
- Hàng nghìn requests cùng chờ timeout;
- Connection pool đầy;
- Retries đồng thời tạo “retry storm”;
- Nhiều instances cùng đánh sập IdP khi nó vừa hồi phục.

Thiết kế production:
1. **Bulkhead/concurrency limit:** giới hạn introspection calls đồng thời.
2. **Short total timeout:** không giữ request vô hạn.
3. **Circuit breaker:** tạm ngưng gọi IdP khi 5xx/timeout ở mức cao.
4. **Half-open probes:** lượng nhỏ có kiểm soát để phát hiện hồi phục.
5. **Jitter/backoff:** tránh thundering herd.
6. **Rate limit per client/IP** ở API edge để hạn chế token spray.
7. **Metrics:** p50/p95/p99 latency, active vs inactive, upstream 4xx/5xx, timeouts, breaker state, concurrency.
8. **Alerts:** secret invalid/rotated, 5xx rate, sustained 429, latency tăng, unavailable duration.
9. **Recovery tests:** IdP outage rồi trở lại; không còn circuit stuck OPEN, không vô tình phát lại token revoked.

**Không coi token inactive là lỗi hệ thống để mở circuit.** Nó là negative authentication result hợp lệ. Nếu 80% token đầu vào là ngẫu nhiên/không tồn tại, circuit breaker không được chặn toàn bộ người dùng thật chỉ vì `active=false` tăng.

## 22. HTTP contract và trải nghiệm client khi IdP outage

Đối với clients, cần một hợp đồng rõ:

- **401**: client chưa authenticated hoặc token inactive. Có thể hướng dẫn refresh/re-auth theo OAuth2 client flow nếu đúng.
- **403**: token active và Authentication thành công nhưng scope/role hoặc object policy không cho phép. Không refresh vô ích chỉ vì 403.
- **503**: **phương án thiết kế** cho dependency unavailable với retry/backoff ở client; không phải guarantee của Spring mặc định. Cần test custom exception mapping và upstream status sanitization.
- **429**: khi API tự áp rate limit; khác 429 của introspection endpoint. Không leak raw provider body.
- **5xx khác**: lỗi nội bộ nếu chưa có mapping rõ; vẫn phải fail closed.

Ví dụ response outage **khi API đã chủ động cài custom 503 mapping**, không phải tự động có từ project lab:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Authentication dependency unavailable","status":503}
~~~

Response này không chứa client secret, raw token, issuer internal URL hoặc nguyên nhân chứng chỉ chi tiết. Gắn trace ID từ hệ thống để vận hành tra log nội bộ. `Retry-After` chỉ đặt khi có lịch/budget hợp lý; tránh yêu cầu mọi client retry đồng loạt.

**Không để error status đánh lừa:** Nếu hệ thống gửi 401 cho outage vì default error handling, đó không tự chứng minh token `active=false`; metrics/logs an toàn phải giữ khác biệt giữa `INVALID_TOKEN` và `INTROSPECTION_UNAVAILABLE`.

## 23. Quan sát và ghi log an toàn

Không bao giờ log:
- Giá trị `Authorization: Bearer ...` inbound;
- Form parameter `token=...` gửi introspection;
- `Authorization: Basic ...` client credentials của Resource Server;
- Raw introspection response có claims/PII quá mức cần thiết;
- Refresh tokens, session cookies hoặc downstream credentials.

Có thể ghi:
- Trace/correlation ID không đoán được;
- Kết quả **loại** (active/inactive/error/timeouts);
- HTTP upstream status sau khi sanitize;
- IdP alias nội bộ, không phải secret;
- Duration, timeout category, breaker state, route ID;
- Metric tags cardinality thấp (không tag raw token, user ID hoặc `sub` làm high-cardinality).

Một event log ví dụ:

~~~json
{
  "traceId": "trace-example",
  "idpAlias": "corporate-idp",
  "result": "INTROSPECTION_TIMEOUT",
  "durationMs": 801,
  "resource": "reports-api"
}
~~~

Đây là log minh họa, không phải stdout của lab. Cần cấu hình masking ở HTTP client wiretap/APM/proxy/traces để không rò token qua auto-instrumentation.

## 24. Phân biệt request idempotency và authentication retries

Introspection POST là bước hỏi trạng thái, thường không tạo side effect nghiệp vụ; có thể retry bounded trên lỗi transient. Nhưng API request gốc có thể là `POST /orders/approve` hoặc chuyển tiền. Nếu client gặp 503/timeout, nó **không** được mặc định retry POST vô điều kiện: cần idempotency key và contract của nghiệp vụ.

Tương tự, nếu Resource Server gọi IdP xong rồi controller đã chạy nhưng downstream response mất kết nối, client retry có thể làm side effect lặp lại. Không nhập khái niệm “retry introspection” với “retry cả HTTP request nghiệp vụ”.

Khi lỗi authentication xảy ra **trước controller**, không được ghi dữ liệu. Test các đường failure bảo đảm service không được gọi, nhưng nếu có side effect eager ở custom filters/tracing hoặc code tự subscribe thì vẫn cần audit. Spring security không thể thu hồi side effect ở code đã chạy trước authentication nếu bạn đặt sai thứ tự filter.

## 25. Chẩn đoán sự cố theo lớp

| Triệu chứng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Mọi token đều thành inactive | IdP có thực sự trả active=false? | Issuer/endpoint/resource client permissions |
| Chỉ một token bị từ chối | active=false hay scope thiếu? | Refresh/re-auth/revoke đúng flow |
| Upstream HTTP 401 | Introspection client ID/secret/auth method | Rotate/config credentials, **không** blame user token |
| Upstream HTTP 403 | Client không đủ quyền introspect | IdP policy/resource server permissions |
| Lỗi DNS/connect timeout | DNS, proxy, network route | Bounded timeout, network health |
| TLS handshake failure | Certificate/truststore/mTLS | Sửa trust/cert, không disable TLS |
| HTTP 429 | IdP rate limit, token spray/retries | Concurrency cap, retry policy, budget |
| HTTP 502/503/504 | Provider/gateway outage | Breaker, degraded policy fail closed, alert |
| 200 nhưng JSON malformed | IdP regression/schema mismatch | Fail closed, integration contract tests |
| Token active nhưng HTTP 403 tại API | Scope/role/tenant authorization | Kiểm tra GrantedAuthorities/domain checks |
| Token active=false nhưng API 200 | Fail-open fallback/cache stale/mock test | Loại fallback, kiểm tra integration thực |
| API response 503 khi provider đã hồi phục | Breaker/health routing stuck | Half-open probe, reset theo policy |
| Latency tăng vọt | Timeout quá dài, không có bulkhead | Tune budget + pool + per-instance concurrency |
| Tests mockOpaqueToken luôn pass | Test bypass introspection | Thêm fake IdP + Bearer thật |
| Token bị revoke nhưng vẫn pass | Positive cache TTL quá dài | Giảm TTL, invalidation hoặc no-cache |

**Debug an toàn:** phân biệt status của **introspection request** với status của **client-facing API response**, đối chiếu metric/time/trace nhưng không in raw secrets. Giải lỗi cấu hình ở đúng lớp; không tắt authentication hoặc cho phép mọi token khi IdP khó truy cập.

## 26. Câu hỏi tự kiểm tra

1. Vì sao `HTTP 200 {"active":false}` không phải lỗi HTTP?
2. Tại sao HTTP 401 từ introspection endpoint không nhất thiết nghĩa user token đã hết hạn?
3. Khi provider down, tại sao `Mono.empty()` hay fallback principal không an toàn?
4. Opaque introspection khác offline JWT verification thế nào trong bài toán revocation/outage?
5. Nếu token active=true nhưng thiếu `reports.read`, vì sao client thường nhận 403?
6. Tại sao `mockOpaqueToken()` không chứng minh access token thật được IdP xác nhận?
7. Vì sao timeout Reactor nên đi kèm HTTP connect/read timeouts?
8. Khi circuit breaker OPEN, có thể chấp nhận cached principal từ request cũ không?
9. Khi nào caching active=true vi phạm yêu cầu “revoke ngay”?
10. Vì sao cache error network như active=false có thể làm sai chẩn đoán?
11. Lỗi 429 của IdP khác 429 do API tự rate limit ở điểm nào?
12. Vì sao không retry vô hạn khi IdP trả 503/timeout?
13. Khi API response 503, client có nên retry mọi POST nghiệp vụ không?
14. Làm cách nào phân biệt 401/403/503 mà không lộ token/secret?
15. Nếu introspection credential vừa rotate, cần theo dõi gì để tránh downtime dài?
16. Vì sao một JWT format cũng có thể được xác thực bằng opaque introspection?
17. Tại sao việc xử lý `active=false` không được đưa vào bộ đếm breaker failure của IdP?
18. Khi provider timeout, tại sao “fail closed” quan trọng hơn cố duy trì 200?

## 27. Bài tập thực hành

**A — Inactive token:** Fake IdP trả 200 `{"active":false}`; gửi request HTTP Bearer thật qua WebTestClient, kỳ vọng 401. Đừng dùng `mockOpaqueToken()`.

**B — Credentials sai:** Fake IdP trả 401 cho introspection request; xác minh API không cho phép request, log an toàn đánh dấu `INTROSPECTION_CLIENT_AUTH_FAILURE`, không kết luận token user revoked.

**C — Network timeout:** Cho fake IdP không phản hồi; đo deadline và xác nhận controller không chạy. Thử mapping 503 riêng nếu là API contract của nhóm.

**D — Outage 5xx:** Fake IdP trả 503; kiểm tra bounded retries và circuit breaker; không có đường success.

**E — Scope:** Fake IdP trả active=true và scope `profile`; route báo cáo phải từ chối 403. Đổi scope sang `reports.read` thì có thể 200.

**F — Cache revocation:** Cache active=true ngắn hạn, revoke token, quan sát khoảng stale. Xác định SLA chấp nhận hoặc tắt positive caching.

**G — Negative cache:** Gửi nhiều token random tạo inactive; giới hạn cache size/TTL để tránh memory abuse.

**H — No fail-open:** Cố tình viết wrapper dùng `onErrorReturn(principalOld)`, viết test chứng minh lỗ hổng, rồi thay bằng fail closed.

**I — Metrics/tracing:** Theo dõi inactive vs 401 introspection credentials vs 5xx/timeout, không chứa token trong log.

**J — Recovery:** Cho IdP downtime rồi hồi phục, kiểm tra breaker half-open, không retry storm, và revoked token không bất ngờ hoạt động.

### Checklist triển khai

- [ ] Tôi phân biệt `active=false` với lỗi mạng/provider.
- [ ] Tôi biết upstream HTTP 401 có thể là lỗi introspection client credentials.
- [ ] Tôi chỉ cấp Authentication khi introspection xác nhận active=true.
- [ ] Tôi không có fallback allow-anonymous hoặc stale principal trên auth failure.
- [ ] Tôi giới hạn timeout và concurrency, áp retry/circuit breaker đúng error category.
- [ ] Tôi biết Spring mặc định không cam kết HTTP 503 cho outage nếu chưa custom/test.
- [ ] Tôi không cache active token trái revocation SLA.
- [ ] Tôi phân biệt 401 authentication, 403 authorization và 5xx dependency.
- [ ] Tôi không nhầm `mockOpaqueToken` với integration introspection thật.
- [ ] Tôi kiểm tra JWT/opaque token theo trust contract, không “parse JWT để bypass IdP”.
- [ ] Tôi không log inbound/outbound tokens/Basic client credentials.
- [ ] Tôi kiểm thử inactive, timeout, 429, 5xx, TLS, schema lỗi và recovery.

## 28. Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html): WebFlux resource server, introspection config, principal, scope mapping.
- [Spring Security — SpringReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html): constructor, builder và custom WebClient.
- [Spring Security — OpaqueTokenReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): authentication manager.
- [Spring Security — Testing Reactive Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockOpaqueToken()` và giới hạn test.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active/false response, introspection POST, error responses, caching/privacy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authorization header và error response.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client, timeout, filters.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): timeout, onErrorResume và mapping.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): bounded retry.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege và object authorization.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS cho IdP/API credentials.

**Kết luận:** Với Spring Security Reactive Resource Server Opaque, một introspection response hợp lệ `{"active":false}` là **kết luận token không hoạt động**; còn timeout, 429/5xx, TLS lỗi hoặc client credentials sai là **không thể xác minh**. Cả hai đều phải **fail closed**, nhưng phân biệt rõ trong metrics, alert và HTTP contract. Dùng `ReactiveOpaqueTokenIntrospector` với timeout/budget, retry giới hạn, breaker/bulkhead và cache theo revocation SLA; không cấp principal từ kết quả cũ khi IdP không xác nhận. Test **cả mock route security và fake HTTP introspection** để chứng minh hệ thống không vô tình cho token không hoạt động hoặc unknown token đi qua khi nhà cung cấp gặp sự cố.