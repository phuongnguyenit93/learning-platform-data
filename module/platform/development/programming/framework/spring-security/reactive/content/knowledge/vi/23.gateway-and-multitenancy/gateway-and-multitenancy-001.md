# Phân định bảo mật tại API Gateway và tại dịch vụ phía sau

## 1. Vấn đề và mục tiêu

Trong kiến trúc Spring WebFlux có API Gateway, nhiều microservices và nhiều tenant, một lỗi rất phổ biến là cho rằng: **“Gateway đã xác thực JWT nên downstream có thể tin mọi request.”** Đây là giả định dễ dẫn đến bypass, giả mạo header, token substitution và truy cập dữ liệu chéo tenant.

Ví dụ: user có access token hợp lệ với `tenant=acme` và scope `orders.read`. Người đó gọi:

```http
GET /edge/orders/globex/records/r9 HTTP/1.1
Host: api.example.invalid
Authorization: Bearer <access-token>
X-Tenant: globex
X-User: admin
```

Gateway có thể xác minh token và scope `orders.read`; nhưng quyền đọc record `r9` của tenant `globex` là quyết định **của Orders Service**, nơi quản lý thông tin tenant, owner và database ACL. Backend không thể chỉ tin `X-Tenant` hoặc `X-User` do caller tự cung cấp.

**Chủ đề:** Phân định bảo mật tại API Gateway và tại dịch vụ phía sau.  
**Chương cha:** Gateway và nhiều tenant.  
**Module:** Spring Security - reactive.  
**Stack minh họa:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring Cloud Gateway Server WebFlux 4.3.x (Spring Cloud 2025.0.x).

### Sau bài, bạn có thể

1. Phân tách authentication, coarse-grained authorization và fine-grained/resource authorization.
2. Giải thích tại sao Gateway kiểm tra token **không thay thế** việc backend tự bảo vệ resource, kể cả có network ACL/mTLS.
3. Ngăn header spoofing (`X-User`, `X-Tenant`, `X-Roles`) và gateway bypass.
4. Ràng buộc JWT với trusted issuer, expiry, audience, scope, tenant và owner/record ACL.
5. Hiểu `TokenRelay` khi Gateway làm OAuth2 Client và vì sao token dành cho Gateway không tự dùng được tại downstream.
6. Chọn tenant/issuer từ nguồn đã xác minh, không dựa vào raw `Host`/`X-Forwarded-*`/query.
7. Thiết kế route allowlist, StripPrefix, forwarded header trust và đường kết nối Gateway → backend.
8. Tạo hai ứng dụng reactive Java 17+ độc lập: Gateway và Orders Service.
9. Viết `WebTestClient` integration tests chống JWT invalid, thiếu scope, giả header, cross-tenant, IDOR/BOLA.
10. Đánh giá giới hạn fake JWT decoder test, rồi lập kế hoạch test JWT cryptographic signature/JWKS thật.

## 2. Hai ranh giới tin cậy khác nhau

```text
Client bên ngoài / mobile / browser
            |
         HTTPS/TLS
            |
    [API GATEWAY - EDGE]
    - xác minh token của caller
    - chặn route ngoài allowlist
    - scope/role coarse-grained
    - rate limit, request size, WAF
    - strip untrusted identity headers
    - routing đến trusted destination
            |
        internal TLS/mTLS
            |
    [ORDERS SERVICE - RESOURCE]
    - xác minh JWT độc lập
    - issuer, signature, aud, exp, nbf
    - scope orders.read
    - tenant claim == tenant requested
    - record owner / role / ACL
            |
       Tenant-aware database
```

**Gateway sở hữu kiểm soát cửa vào và đường đi; dịch vụ phía sau sở hữu kiểm soát dữ liệu và quyền nghiệp vụ.**

| Mối quan tâm | Gateway | Orders Service |
|---|---|---|
| TLS và ingress endpoint | Chính | TLS/mTLS nội bộ khi phù hợp |
| Coarse rate limits / WAF / size limits | Chính | Business quotas riêng |
| Bearer authentication của caller | Nên xác minh | Phải xác minh lại nếu nhận Bearer như một trust boundary |
| Audience của Orders token | Kiểm tra theo route | Kiểm tra `aud=orders-api` |
| Scope `orders.read` | Check sớm | Check lại khi vào endpoint |
| Tenant trong path | Routing hint | Đối chiếu với trusted claim |
| Record owner / ACL | Không đủ dữ liệu | Bắt buộc |
| `X-User`/`X-Roles` giả | Loại bỏ | Không dùng làm principal |
| TokenRelay / token exchange | Có thể xử lý | Kiểm tra token nhận |
| Direct backend bypass | Network ACL và topology | Vẫn đòi authentication/authorization |
| DB row-level isolation | Không làm được | Service/repository/DB |
| Audit | Route, status, rate | Principal, tenant, record access decision |
| CORS / CSRF | Tùy browser/session flow | Không bỏ local protections nếu dùng session/cookie |

### 2.1. Authentication không tự là authorization

Authentication kiểm tra caller là ai và credential/token có hợp lệ không. Authorization kiểm tra caller đó có quyền thực hiện **một thao tác cụ thể** hay không.

Một token có `scope=orders.read` là quyền loại thao tác, không tự chứng minh caller được đọc tất cả orders trong mọi tenant. Vì thế một request có thể pass Gateway nhưng bị backend từ chối **403 Forbidden** do tenant hoặc owner mismatch.

### 2.2. Zero trust không có nghĩa “xác thực vô hạn”

Trong kiến trúc zero trust, không cấp quyền chỉ vì request đến từ private subnet. Đánh giá identities, permissions và boundary mỗi hop. Backend có thể dùng chính JWT access token của user hoặc một **signed internal assertion** được Gateway phát với audience/TTL/service identity chặt, nhưng nó phải **xác minh** nguồn thông tin đó. Một header plaintext `X-Authenticated-User` không đủ.

Double JWT verification ở Gateway và backend tốn chút CPU, nhưng mang lợi ích cô lập trust boundaries. Nếu chọn cách thay thế dựa trên mTLS + signed gateway assertions, phải có giao thức rõ, threat model, service ingress controls và backend vẫn enforce record ACL.

## 3. Những kiểu triển khai cần phân biệt

### 3.1. Gateway nhận JWT Bearer và proxy cùng token

```text
Client --Authorization: Bearer T--> Gateway
Gateway --Authorization: Bearer T--> Orders Service
Orders Service --verify T independently--> Record ACL
```

Trong ví dụ, token `T` dành cho `aud=orders-api`. Gateway là lớp kiểm tra trước route Orders và có thể xác minh token theo audience này; backend cũng xác minh token dành cho chính nó.

Đây **không phải TokenRelay GatewayFilter**: request đã có Authorization Bearer header inbound. Gateway không cần đóng vai OAuth2 login client để lấy access token mới. Route được phép chuyển Authorization sang downstream; backend xác minh lại token, không tin token chỉ vì Gateway đã forward.

Kiểm tra behavior của proxy/filters/version thật bằng integration tests. Đừng mặc định mọi proxy giữ nguyên Authorization trong mọi cấu hình.

### 3.2. Gateway làm OAuth2 Login Client cho browser

```text
Browser --session cookie--> Gateway (oauth2Login)
Gateway --access token qua TokenRelay--> downstream
Downstream --verify token and ACL--> data
```

Spring Cloud Gateway Server WebFlux có `TokenRelay` filter, thường dùng với OAuth2 client registration. Ví dụ snippet:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-login
              uri: https://orders.internal.example.invalid
              predicates:
                - Path=/edge/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
```

Khi Gateway đóng vai OAuth2 Client, `TokenRelay` có thể lấy access token hiện tại của user (hoặc token của `clientRegistrationId` được chỉ định) rồi gắn vào outbound request. Nó cần `spring-boot-starter-oauth2-client` và `ReactiveClientRegistrationRepository` đúng. Default authorized-client service có thể dùng in-memory; nhiều replicas cần storage/refresh behavior phù hợp.

**Không nhầm:**
- ID token nói về xác thực user cho OIDC Client, **không phải** access token gửi downstream API.
- Session cookie của browser không phải Bearer token có audience Orders.
- TokenRelay **không tự biến đổi audience**. Nếu access token chỉ có `aud=gateway` mà Orders yêu cầu `aud=orders-api`, hãy dùng token exchange hoặc xin token đúng resource; **không** bỏ audience check của backend.
- Chỉ relay token tới **trusted route destinations**, không tới URL do caller nhập.

### 3.3. Gateway gửi signed internal assertion thay token gốc

Một lựa chọn khác là Gateway xác thực token ngoài, rồi cấp short-lived **signed assertion** cho downstream với `iss=gateway-internal`, `aud=orders-api`, tenant/sub và TTL; kết hợp mTLS. Backend phải verify signature, audience, expiry, trusted gateway identity, chống replay theo contract, rồi apply ACL. Nếu không có chữ ký/mTLS và ingress restrictions, custom `X-User` plaintext là nguy cơ spoof.

## 4. Những tấn công khi phân định trách nhiệm sai

### 4.1. Bỏ security ở backend vì “Gateway đã làm rồi”

Một developer cấu hình `permitAll()` cho `/orders/**` ở downstream. Trong điều kiện bình thường có thể trông như an toàn, nhưng attacker có thể gọi service trực tiếp do:
- Internal pod/workload bị compromise.
- Backend bị expose nhầm bằng load balancer/Ingress.
- Route config mới bỏ qua Gateway.
- Mesh/proxy route drift.
- Một service nội bộ gửi request không qua edge authn.

**Phòng vệ:** backend vẫn làm Resource Server, có route authorization, tenant checks; network policy không cho direct public ingress và mTLS nếu phù hợp. Test direct backend request không token phải bị 401.

### 4.2. Giả mạo identity headers

Header `X-Tenant: acme`, `X-User: admin`, `X-Roles: ROLE_ADMIN` do client gửi **không được dùng để tạo Authentication**. Gateway phải strip untrusted identity headers ở ingress/route; backend tốt nhất lấy principal từ JWT/verified assertion, không đọc chúng để cấp quyền.

Nếu sản phẩm cần truyền identity metadata nội bộ, phải chứng minh header ấy do trusted proxy tạo sau khi loại header từ bên ngoài, channel được xác thực và có policy bảo vệ. Một malformed/double header có thể gây khác biệt parser ở các lớp; test duplicate, case-insensitive và forwarding normalization.

### 4.3. Tenant mismatch và IDOR/BOLA

Client token được ký cho `tenant=acme`, có `SCOPE_orders.read`. Request:

```http
GET /edge/orders/globex/records/r9
Authorization: Bearer <token-acme>
```

Gateway kiểm tra scope và proxy, nhưng backend phải so tenant của **verified token** với tenant của path/resource. Mismatch → từ chối. Ngay cả trong tenant acme, record r2 của bob không được user alice đọc khi owner/ACL không cho phép.

```text
token.scope contains orders.read
AND token.tenant == requestedTenant
AND record.tenant == token.tenant
AND record.owner / ACL permits token.sub
```

Không truy vấn database theo `recordId` toàn cục mà quên tenant predicate. Đối với update/delete cần enforce tenant/owner trong cùng transaction và repository filter, tránh TOCTOU.

### 4.4. Token substitution và audience

Một token active từ AS đúng có thể được cấp cho `aud=payments-api`. Nếu Orders Service chỉ kiểm tra signature mà bỏ audience, nó có thể chấp nhận token không dành cho Orders (**confused deputy**). Bắt buộc xác minh `iss`, `exp`, `nbf`, chữ ký hoặc introspection, audience, scopes và authorization policy của chính service.

Spring Boot 3.5 hỗ trợ `spring.security.oauth2.resourceserver.jwt.audiences` trên Reactive và Servlet; dùng audience property hoặc validator tương đương.

### 4.5. Route confusion / SSRF

Không cho caller chọn upstream destination tùy ý:

```text
GET /edge/proxy?url=http://169.254.169.254/metadata
```

Routes phải lấy từ server config/service registry trusted. Không tự làm `uri(request.getQueryParams().getFirst("url"))`. Kiểm tra trusted scheme, host/port, redirects và egress IP/DNS policy nếu phải gọi dynamic destination. Path rewrite không được sinh ra authority mới từ encoded/untrusted input.

### 4.6. Forwarded headers và tenant resolution

`Host`, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` và `X-Forwarded-Host` có thể bị client tự đặt. Spring Cloud Gateway 2025.0/4.3 có property `spring.cloud.gateway.server.webflux.trusted-proxies` cho forwarded-header trust configuration.

Chỉ tin proxy thực trong ingress topology, không đặt regex wildcard `.*` trên public input. Nếu tenant được chọn theo hostname, xác minh domain/tenant mapping tin cậy và vẫn check token tenant ở downstream. Mọi quyết định issuer/JWKS routing động từ unverified JWT `iss` cũng phải **allowlist trusted issuers** để tránh SSRF.

## 5. Phân biệt kết quả HTTP 401, 403, 404

| Case | Gateway | Backend | Kết quả |
|---|---|---|---|
| Thiếu Bearer | Không proxy | Không nhận | 401 ở Gateway |
| Token malformed/signature sai | Không proxy | Không nhận | 401 |
| Token valid, thiếu coarse scope | Không proxy | Không nhận | 403 |
| Token valid, đủ scope | Proxy | Revalidate issuer/aud/scope/tenant/ACL | 200/403/404 |
| Token tenant acme yêu cầu globex | Có thể proxy | Tenant mismatch → reject | 403 |
| Token acme/alice đọc r2 của bob | Có thể proxy | Owner ACL → reject | 403 |
| Direct backend không Bearer | Bị bypass | Backend reject | 401 |
| Unlisted path | Không route / deny | Không nhận | 403/404 theo config |
| Token dành payments-api | Nếu có aud check, reject | Nếu tới, Orders reject | 401 |
| AS/JWKS unavailable và chưa verify token | Fail closed | Fail closed | Không có protected success |

**401** cho authentication thiếu/không hợp lệ, **403** cho authenticated principal không có permission. Một số business chọn trả 404 khi record không tồn tại hoặc bị ẩn, để giảm enumeration; đó là policy riêng, không có nghĩa được bỏ ACL.

## 6. Kiến trúc dùng Spring Cloud Gateway Server WebFlux

Ví dụ chạy hai Spring Boot applications:

```text
workspace/
  edge-gateway/                      port 9000
    src/main/java/demo/edge/
      EdgeApplication.java
      EdgeSecurity.java
      EdgeHealthController.java
    src/main/resources/application.yml
    src/test/java/demo/edge/
      EdgeBoundaryTests.java

  orders-service/                    port 9001
    src/main/java/demo/orders/
      OrdersApplication.java
      OrdersSecurity.java
      OrderAccess.java
      OrdersController.java
    src/main/resources/application.yml
    src/test/java/demo/orders/
      OrdersBoundaryTests.java
```

Dùng **hai project từ Spring Initializr**, mỗi project có Gradle wrapper/build plugins/repositories/Java toolchain riêng. Ví dụ dùng Spring Boot 3.5.x và Spring Cloud 2025.0.x cho Java 17+, Security 6.5.x/Gateway 4.3.x. **Spring Cloud 2025.0.3 là một release cho Boot 3.5.x, nhưng line này đã hết hỗ trợ OSS vào giữa 2026; production cần chọn baseline còn được vendor hỗ trợ và các security patches phù hợp.** Version demo nhằm minh họa API của module, không phải khuyến cáo dùng nền tảng hết hỗ trợ trong triển khai mới.

### 6.1. Dependencies của edge-gateway

Trong project generated bởi Initializr, dùng snippet `build.gradle` sau:

```groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.3'
    }
}
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Giữ `org.springframework.boot` và `io.spring.dependency-management` plugins từ Initializr; block trên **không** là toàn bộ build.gradle độc lập. Dùng artifact `spring-cloud-starter-gateway-server-webflux` mới thay cho starter tên cũ deprecated. Gateway Server WebFlux cần Netty/WebFlux runtime, không phải Servlet MVC.

### 6.2. Dependencies của orders-service

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Không thêm `spring-boot-starter-web`: trong Boot 3.x khi cả MVC và WebFlux có mặt, Servlet MVC thường được chọn làm inbound stack.

## 7. Gateway Java 17+ code

### 7.1. EdgeApplication.java

```java
package demo.edge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EdgeApplication {
    public static void main(String[] args) {
        SpringApplication.run(EdgeApplication.class, args);
    }
}
```

### 7.2. EdgeSecurity.java

```java
package demo.edge;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class EdgeSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/edge/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/edge/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Giải thích:

- Gateway tự verify inbound JWT qua `oauth2ResourceServer().jwt()`.
- `/edge/orders/**` chỉ cho GET có `SCOPE_orders.read`. Đây là kiểm tra **coarse**, không kiểm tra owner record.
- URL khác bị deny; tránh `permitAll()` trên toàn gateway.
- Không bật HTTP Basic hoặc form login cho bearer-only API.
- Không tắt CSRF vô điều kiện; demo chỉ có GET. Khi có browser session/cookie và unsafe methods, thiết kế CSRF đúng threat model.

### 7.3. EdgeHealthController.java

```java
package demo.edge;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EdgeHealthController {

    @GetMapping("/edge/health")
    public Mono<String> health() {
        return Mono.just("edge-ok");
    }
}
```

### 7.4. edge-gateway application.yml

```yaml
server:
  port: 9000

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/
          audiences:
            - orders-api
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: ${ORDERS_SERVICE_URL:http://127.0.0.1:9001}
              predicates:
                - Path=/edge/orders/**
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=X-User
                - RemoveRequestHeader=X-Tenant
                - RemoveRequestHeader=X-Roles
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveRequestHeader=X-Forwarded-User
```

Cấu hình này dùng prefix **`spring.cloud.gateway.server.webflux.routes`** cho Spring Cloud Gateway 4.3/Cloud 2025.0. Mẫu cũ dùng `spring.cloud.gateway.routes` có thể đã deprecated hoặc không hoạt động đúng trong version này.

`StripPrefix=1`: `/edge/orders/acme/records/r1` → `/orders/acme/records/r1`. Upstream đến `http://127.0.0.1:9001` cho **local demo**; môi trường production phải là trusted service URL qua HTTPS/mTLS/private network.

Các `RemoveRequestHeader` loại những identity headers từ client. Backend demo **không tin** chúng trong mọi trường hợp, kể cả request direct. Không remove `Authorization` vì Orders Service cần access token để tự xác minh. `issuer.example.invalid` là domain giả, không có Authorization Server thật.

`ORDERS_SERVICE_URL` phải được đặt bằng config trusted; không biến thành URL lấy từ query hay header của caller.

## 8. Backend Java 17+ code

### 8.1. OrdersApplication.java

```java
package demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 8.2. orders-service application.yml

```yaml
server:
  port: 9001

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/
          audiences:
            - orders-api
```

**Audience quan trọng:** Orders Service nhận chỉ token hướng tới `orders-api`. Gateway trong demo kiểm tra cùng token phù hợp Orders route, backend validate lần nữa. Nếu trong kiến trúc thật Gateway có audience khác, sử dụng access token riêng cho Orders hoặc token exchange; không yêu cầu backend bỏ audience validation.

### 8.3. OrdersSecurity.java

```java
package demo.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Dù có Gateway, Orders Service là **Resource Server độc lập**: verify token, scope và tiếp tục local ACL. Request tới backend trực tiếp thiếu token phải trả 401.

### 8.4. OrderAccess.java — kiểm tra tenant và owner ở service

```java
package demo.orders;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderAccess {

    private static final Map<String, Map<String, String>> OWNERS =
        Map.of(
            "acme", Map.of("r1", "alice", "r2", "bob"),
            "globex", Map.of("r9", "alice"));

    public record OrderView(
            String tenant, String recordId,
            String owner, String summary) {
    }

    public Mono<OrderView> read(
            String tenant, String recordId, Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant");
        String subject = jwt.getSubject();

        if (tokenTenant == null
                || !tokenTenant.equals(tenant)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant is not permitted"));
        }

        Map<String, String> tenantRecords = OWNERS.get(tenant);
        if (tenantRecords == null
                || !tenantRecords.containsKey(recordId)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Record not found"));
        }

        String owner = tenantRecords.get(recordId);
        if (!owner.equals(subject)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Record access denied"));
        }

        return Mono.just(new OrderView(
            tenant, recordId, owner,
            "Illustrative protected order"));
    }
}
```

Ba kiểm tra khác nhau:

1. `tokenTenant` được lấy từ **JWT đã được Spring Security xác minh**, không từ header `X-Tenant`.
2. Repository lookup chỉ trong tenant được yêu cầu; demo dùng Map, production phải có tenant predicate trong DB.
3. Owner của record phải match `Jwt.sub` hoặc ACL/roles do business policy cho phép.

Nhờ vậy user acme/alice không đọc được globex/r9 hoặc acme/r2 của bob, dù có scope `orders.read`.

**Không phải mọi OAuth2 access token đều có claim tenant**; đó là application-specific contract cần AS cấp tin cậy. Nếu tenant memberships phức tạp, backend tra membership DB/authorization service và enforce policy thay vì tự tin một claim quá rộng. Khi token/role bị thu hồi, cân nhắc TTL và membership revocation.

### 8.5. OrdersController.java

```java
package demo.orders;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrderAccess access;

    public OrdersController(OrderAccess access) {
        this.access = access;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("orders-ok");
    }

    @GetMapping("/orders/{tenant}/records/{recordId}")
    public Mono<OrderAccess.OrderView> read(
            @PathVariable String tenant,
            @PathVariable String recordId,
            @AuthenticationPrincipal Jwt jwt) {
        return access.read(tenant, recordId, jwt);
    }
}
```

Đây là controller WebFlux dùng `Mono`; `Jwt` được inject từ verified resource-server authentication. Không đọc principal từ `request.getHeaders().getFirst("X-User")` và không dùng `.block()`.

Trong ứng dụng thật, bảo vệ read/write/aggregate endpoints, field-level permissions, database isolation, không leak dữ liệu giữa tenants qua cache key/metrics/logs.

## 9. Chạy ứng dụng local

Tạo hai Gradle projects riêng như phần 6. Trong terminal 1 chạy Orders Service:

```bash
./gradlew bootRun
```

Trong terminal 2 chạy Gateway:

```bash
./gradlew bootRun
```

Windows PowerShell tại từng project:

```powershell
.\gradlew.bat bootRun
```

Kiểm tra:

```bash
curl -i http://127.0.0.1:9000/edge/health
curl -i http://127.0.0.1:9001/health
curl -i http://127.0.0.1:9000/edge/orders/acme/records/r1
curl -i http://127.0.0.1:9001/orders/acme/records/r1
```

Dự kiến health HTTP 200 với body lần lượt `edge-ok`/`orders-ok`. Hai protected GET thiếu Bearer phải trả 401. Không có JWT thật để login thành công: issuer `example.invalid` là placeholder không hoạt động; vì vậy chỉ những tests với fake JwtDecoder mới chứng minh policy logic offline.

## 10. Test Gateway với WebTestClient và local Netty stub

File `edge-gateway/src/test/java/demo/edge/EdgeBoundaryTests.java`:

```java
package demo.edge;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(EdgeBoundaryTests.FakeDecoder.class)
class EdgeBoundaryTests {

    static final AtomicInteger PROXIED = new AtomicInteger();
    static final AtomicReference<String> PATH =
        new AtomicReference<>();
    static final AtomicReference<String> USER =
        new AtomicReference<>();
    static final AtomicReference<String> TENANT =
        new AtomicReference<>();
    static final AtomicReference<String> ROLES =
        new AtomicReference<>();
    static final AtomicReference<String> AUTH =
        new AtomicReference<>();

    static final DisposableServer UPSTREAM = HttpServer.create()
        .host("127.0.0.1").port(0)
        .handle((request, response) -> {
            PROXIED.incrementAndGet();
            PATH.set(request.uri());
            USER.set(request.requestHeaders().get("X-User"));
            TENANT.set(request.requestHeaders().get("X-Tenant"));
            ROLES.set(request.requestHeaders().get("X-Roles"));
            AUTH.set(request.requestHeaders()
                .get(HttpHeaders.AUTHORIZATION));
            return response.status(200)
                .sendString(Mono.just("stub-orders-ok"));
        }).bindNow();

    @DynamicPropertySource
    static void upstream(DynamicPropertyRegistry registry) {
        registry.add("ORDERS_SERVICE_URL",
            () -> "http://127.0.0.1:" + UPSTREAM.port());
    }

    @AfterAll
    static void stop() {
        UPSTREAM.disposeNow();
    }

    @TestConfiguration
    static class FakeDecoder {
        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> {
                if ("edge-read".equals(token)) {
                    return Mono.just(jwt(token, "orders.read"));
                }
                if ("edge-no-scope".equals(token)) {
                    return Mono.just(jwt(token, "profile"));
                }
                return Mono.error(new BadJwtException(
                    "Not a trusted test JWT"));
            };
        }

        static Jwt jwt(String value, String scope) {
            Instant now = Instant.now();
            return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://issuer.example.invalid/")
                .claim("aud", List.of("orders-api"))
                .claim("sub", "alice")
                .claim("tenant", "acme")
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(60))
                .expiresAt(now.plusSeconds(600))
                .build();
        }
    }

    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/edge/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("edge-ok");
    }

    @Test
    void missingBearerRejectedBeforeProxy() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .exchange().expectStatus().isUnauthorized();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void invalidBearerRejectedBeforeProxy() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("invalid"))
            .exchange().expectStatus().isUnauthorized();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void missingScopeRejectedAtGateway() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("edge-no-scope"))
            .exchange().expectStatus().isForbidden();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void routingSanitizesIdentityHeaders() {
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("edge-read"))
            .header("X-User", "attacker")
            .header("X-Tenant", "globex")
            .header("X-Roles", "ROLE_ADMIN")
            .header("X-Authenticated-User", "attacker")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("stub-orders-ok");

        assertEquals("/orders/acme/records/r1", PATH.get());
        assertNull(USER.get());
        assertNull(TENANT.get());
        assertNull(ROLES.get());
        assertEquals("Bearer edge-read", AUTH.get());
    }

    @Test
    void unknownEdgePathIsDenied() {
        int before = PROXIED.get();
        client.get().uri("/edge/private")
            .headers(h -> h.setBearerAuth("edge-read"))
            .exchange().expectStatus().isForbidden();
        assertEquals(before, PROXIED.get());
    }
}
```

**6 tests**: public health, missing token, invalid token, thiếu scope, strip headers + path rewrite + Authorization pass-through, unlisted route. Test Gateway dùng một Netty stub ở port loopback động nên **không gọi backend thật** và không cần IdP. Stub nhận fake Bearer `edge-read` để kiểm chứng forwarding; không dùng test pattern này để capture/print production secrets.

**Giới hạn:** FakeDecoder tạo `Jwt` trực tiếp không có chữ ký thật, nên tests không kiểm chứng key/issuer/aud signature. Production dùng Spring Boot JWT decoder từ trusted AS/JWKS và audience property. HTTP tests này xác minh Gateway routing/edge rules/strip headers.

## 11. Test backend độc lập với Gateway

File `orders-service/src/test/java/demo/orders/OrdersBoundaryTests.java`:

```java
package demo.orders;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(OrdersBoundaryTests.FakeDecoder.class)
class OrdersBoundaryTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeDecoder {
        static final String ISS =
            "https://issuer.example.invalid/";

        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> {
                Jwt jwt = switch (token) {
                    case "acme-alice-read" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "alice", "orders.read");
                    case "acme-bob-read" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "bob", "orders.read");
                    case "globex-alice-read" -> jwt(
                        token, ISS, "orders-api",
                        "globex", "alice", "orders.read");
                    case "acme-no-scope" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "alice", "profile");
                    case "bad-audience" -> jwt(
                        token, ISS, "payments-api",
                        "acme", "alice", "orders.read");
                    case "bad-issuer" -> jwt(
                        token, "https://untrusted.example.invalid/",
                        "orders-api", "acme", "alice", "orders.read");
                    default -> null;
                };

                if (jwt == null
                        || !ISS.equals(jwt.getClaimAsString("iss"))
                        || !jwt.getAudience().contains("orders-api")
                        || jwt.getExpiresAt() == null
                        || !jwt.getExpiresAt().isAfter(
                            Instant.now())) {
                    return Mono.error(new BadJwtException(
                        "Invalid test JWT"));
                }
                return Mono.just(jwt);
            };
        }

        static Jwt jwt(
                String value, String issuer, String audience,
                String tenant, String subject, String scope) {
            Instant now = Instant.now();
            return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", issuer)
                .claim("aud", List.of(audience))
                .claim("sub", subject)
                .claim("tenant", tenant)
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(60))
                .expiresAt(now.plusSeconds(600))
                .build();
        }
    }

    @Test
    void healthPublic() {
        client.get().uri("/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("orders-ok");
    }

    @Test
    void directWithoutJwtIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void invalidJwtIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("unknown"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownRecordIsReadable() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("acme")
            .jsonPath("$.recordId").isEqualTo("r1")
            .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void wrongTenantIsForbidden() {
        client.get().uri("/orders/globex/records/r9")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void recordOfOtherOwnerIsForbidden() {
        client.get().uri("/orders/acme/records/r2")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void correctRecordOwnerIsAllowed() {
        client.get().uri("/orders/acme/records/r2")
            .headers(h -> h.setBearerAuth("acme-bob-read"))
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.owner").isEqualTo("bob");
    }

    @Test
    void otherTenantOwnRecordIsAllowed() {
        client.get().uri("/orders/globex/records/r9")
            .headers(h -> h.setBearerAuth("globex-alice-read"))
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.tenant").isEqualTo("globex");
    }

    @Test
    void badAudienceIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("bad-audience"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void badIssuerIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("bad-issuer"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeIsForbidden() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-no-scope"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedIdentityHeadersDoNotChangePrincipal() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .header("X-User", "bob")
            .header("X-Tenant", "globex")
            .header("X-Roles", "ROLE_ADMIN")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void missingRecordReturnsNotFound() {
        client.get().uri("/orders/acme/records/missing")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void unlistedBackendPathIsDenied() {
        client.get().uri("/internal/debug")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }
}
```

**14 tests** bảo vệ downstream: direct bypass thiếu token, issuer/audience, scope, tenant, owner/IDOR, forged headers, unknown record và deny-all. Fake decoder kiểm tra một số claims theo logic test nhưng **không có cryptographic signature verification**; tests chủ yếu xác minh HTTP security chain và policy business. Không triển khai bean `@TestConfiguration` trong production.

### 11.1. Chạy test

Trong mỗi project root:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Tổng cộng **20 test methods** (6 Gateway + 14 Orders Service). Đây là **các trường hợp kiểm thử được viết và rà soát tĩnh**; chưa có xác nhận Gradle đã chạy trong workspace người học.

Để xác minh security properties của Spring Boot trong production, bổ sung integration tests với AS/JWKS test và JWT có chữ ký thật, expired token, wrong issuer/audience, JWK rotation, mTLS, token exchange và Gateway→backend end-to-end. Mock JwtDecoder không thể thay một test xác minh chữ ký thật.

## 12. Mở rộng cho nhiều services/tenants

### 12.1. Gateway đa route cần audience đúng route

```text
/edge/orders/**    -> aud=orders-api
/edge/billing/**   -> aud=billing-api
/edge/hr/**        -> aud=hr-api
```

Cấu hình demo `audiences: orders-api` chỉ phù hợp **Gateway một Orders route**. Khi mở rộng, không đặt một decoder cho phép mọi audiences một cách rộng rồi forward token bừa bãi. Chọn chính sách per route, trusted issuer/audience resolver và token exchange theo Resource Server target. Các backend luôn thực thi audience/scope của riêng mình.

### 12.2. Tenant chọn từ hostname/path chỉ là routing hint

Gateway có thể route `acme.api.example.invalid` sang shard acme, nhưng backend phải đối chiếu token claim hoặc authoritative membership. Nếu tenant được khai báo trong signed JWT, hãy so với tenant của record. Nếu AS không phát tenant claim, tra membership theo `iss+sub` từ database/authorization service.

### 12.3. Multi-issuer resolver

Spring Security Reactive có `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` để xử lý JWT đến từ một tập issuer được phép. Resolver có thể đọc `iss` chưa verified để chọn decoder, nhưng issuer phải thuộc **allowlist** và được verify bằng signature/issuer validation sau đó. Không xây JWKS URLs từ arbitrary claim; đây có thể tạo SSRF.

### 12.4. Service accounts và background jobs

`client_credentials` tokens đại diện ứng dụng, không tự có user tenant membership. Dùng scopes riêng cho batch jobs, audience downstream, tenant allowlist/audit rõ. Không tự gán `tenant=*` hoặc quyền admin cho mọi background jobs để giải quyết lỗi authorization.

## 13. Những việc Gateway không thay backend được

- Row-level và object-level ACL.
- Tenant isolation trong R2DBC/SQL queries.
- Validation business invariants khi update.
- Field-level permissions, PII redaction.
- Revocation/membership business checks có độ trễ thấp.
- Transactional authorization và TOCTOU prevention.
- Hạn chế quy mô thao tác tốn tài nguyên theo account.
- Các truy cập không qua Gateway như queues, internal jobs, RPC.

Một hệ thống nhiều trust paths không thể chỉ dựa vào HTTP Gateway để kiểm soát toàn bộ quyền. Mọi entry point tới data cần có security boundary tương đương.

## 14. Troubleshooting

| Hiện tượng | Nguyên nhân | Hướng sửa |
|---|---|---|
| API trả data tenant khác | Backend bỏ check tenant/owner | Enforce JWT tenant, tenant-aware DB/ACL |
| Backend direct call không token trả 200 | Backend `permitAll` | Cấu hình own Resource Server |
| Header `X-User=admin` nâng quyền | Tin header client | Strip tại ingress, không dùng header làm principal |
| Token aud payments vào orders | Không validate audience | `jwt.audiences=orders-api` và service ACL |
| Gateway 403 nhưng backend direct 200 | Backend thiếu scope policy | `hasAuthority("SCOPE_orders.read")` |
| TokenRelay dùng ID token | Nhầm token types | Chỉ access token có audience phù hợp |
| TokenRelay cần aud downstream khác | Không exchange token | Token exchange theo AS policy |
| Route path sai sau prefix strip | YAML/predicate mismatch | Integration test raw upstream path |
| YAML route không được load | Prefix legacy version | 2025.0 dùng `server.webflux.routes` |
| Basic auth hiện ra ở Bearer API | Default security chain | Cấu hình `oauth2ResourceServer` và disable basic |
| X-Forwarded-Host được tin bừa bãi | Trusted proxy config sai | Ingress strips and trusted-proxies allowlist |
| JWT issuer resolver SSRF | Dùng arbitrary unverified iss | Trusted issuer allowlist |
| CSRF bị tắt cho cookie login | Nhầm bearer-only và browser session | CSRF theo credential model |
| Data cache chia sẻ giữa tenants | Cache key thiếu tenant | Tenant-scoped keys, ownership checks |
| Logs có Bearer token | Log raw headers | Redact Authorization/Cookie/PII |
| Fake decoder tests pass nhưng real JWT fail | Chưa test cryptography | Signed JWT/JWKS integration tests |
| Gateway quá tải khi JWKS/AS chậm | Timeout/caching thiếu | Quotas, deadlines, trusted key caching |
| Headers route mới chưa strip | Strip chỉ ở một route | Test tất cả routes, áp global boundary policy |

## 15. Bài tập có đáp án

### Bài 1. Gateway JWT valid, backend permitAll có ổn không?

**Đáp án:** Không phải mặc định an toàn. Nếu backend bị gọi trực tiếp, các kiểm tra ở Gateway mất tác dụng. Backend vẫn verify token/trusted assertion và ACL.

### Bài 2. Scope orders.read đủ đọc mọi record của acme?

**Đáp án:** Không. Scope là quyền loại thao tác; service còn phải kiểm tra tenant của token, tenant của record và owner/ACL.

### Bài 3. Token acme yêu cầu globex/r9?

**Đáp án:** Reject 403 ở backend sau khi verified token tenant != path tenant, kể cả Gateway đã check scope.

### Bài 4. X-Tenant=acme có giá trị chứng minh membership?

**Đáp án:** Không. Header do caller kiểm soát. Lấy tenant từ verified token/membership DB/trusted assertion.

### Bài 5. X-User=admin có thể được coi là principal?

**Đáp án:** Không nếu là plaintext untrusted. Gateway strip và backend dùng verified Jwt principal. Nếu dùng gateway assertion phải có chữ ký/mTLS/audience và no-bypass.

### Bài 6. Gateway TokenRelay có tự đổi audience?

**Đáp án:** Không. Nó forward access token hiện có; token exchange/xin token downstream nếu cần.

### Bài 7. ID token có dùng làm Bearer token của Orders Service không?

**Đáp án:** Không theo mô hình OAuth2 resource server này. OIDC ID token phục vụ Relying Party xác minh user; downstream API dùng access token có aud/scope đúng.

### Bài 8. Backend có cần TLS nếu Gateway đã HTTPS?

**Đáp án:** Với network threat model phù hợp, HTTPS/mTLS nội bộ giúp bảo vệ credential và workload identity. Gateway HTTPS không tự bảo vệ private hop.

### Bài 9. Valid JWT nhưng aud=payments-api?

**Đáp án:** Orders Service reject; signature hợp lệ không chứng minh token được cấp cho Orders.

### Bài 10. CORS thay authentication được không?

**Đáp án:** Không. CORS là browser policy, clients ngoài browser vẫn gọi được API. Backend phải bảo vệ bằng token/ACL.

### Bài 11. Vì sao không tự tin Host/X-Forwarded-Host?

**Đáp án:** Caller có thể spoof nếu ingress không normalize/trust proxy đúng. Routing hint không phải quyền tenant.

### Bài 12. Vì sao dùng test fake JWT decoder?

**Đáp án:** Để kiểm tra security rules và business ACL offline, không phụ thuộc AS. Muốn chứng minh cryptography/JWK rotation, phải dùng signed test JWT và decoder thật.

### Bài 13. Gateway route đa dịch vụ có thể dùng aud=orders-api cho tất cả?

**Đáp án:** Không. Thiết kế audience policy per downstream, hoặc token exchange; từng service phải validate aud riêng.

### Bài 14. mTLS có tự cấp quyền đọc r1 không?

**Đáp án:** Không. Nó xác thực workload/channel, không chứng minh user-owner/tenant ACL.

### Bài 15. Nếu Gateway header strip chạy sai thì sao?

**Đáp án:** Backend vẫn không tin headers đó, nên không biến chúng thành principal. Cần integration test route thực và chuẩn hóa headers ở ingress.

### Bài 16. Thứ gì cần test khi bypass Gateway?

**Đáp án:** Direct request thiếu token 401, sai token 401, thiếu scope 403, sai tenant/owner 403, đúng tenant/owner 200.

## 16. Checklist production

- [ ] Gateway bảo vệ ingress, paths và upstream allowlist, không dynamic SSRF target.
- [ ] Backend không public ngoài ý muốn; network policy/mTLS/HTTPS nội bộ theo threat model.
- [ ] Backend tự validate trusted issuer, JWT signature/introspection, audience, exp/nbf.
- [ ] Scope kiểm tra cả Gateway lẫn backend nơi cần thiết.
- [ ] Tenant/membership được xác minh, đối chiếu URL và database record.
- [ ] Owner/ACL kiểm tra tại data-owning service, không chỉ Gateway.
- [ ] Loại identity headers giả tại ingress; backend không tin chúng.
- [ ] `Forwarded`/`X-Forwarded-*` chỉ tin trusted proxy, không wildcard công khai.
- [ ] TokenRelay chỉ dùng access token và audience/downstream phù hợp; token exchange khi cần.
- [ ] Không coi ID token/session cookie như Bearer resource token.
- [ ] Không lấy JWKS/issuer URL từ untrusted JWT để gọi bất kỳ host nào.
- [ ] Route rewrite và header sanitation có HTTP integration tests.
- [ ] JWT cryptography, signature/JWKS/expiry/aud test bằng real decoder và signed tokens.
- [ ] Direct service bypass được kiểm thử; chưa authenticated không được data.
- [ ] CORS/CSRF/session của browser được thiết kế theo credential model.
- [ ] Gateway và service có rate limits, timeout, resilience và audit.
- [ ] Logs/traces/APM không lộ Authorization/Cookie/tokens/PII.
- [ ] Tenant-aware cache keys và DB queries có isolation/ACL.
- [ ] Production dùng Boot/Cloud lines còn được hỗ trợ, đã vá CVE.

## 17. Tóm tắt

```text
Gateway:
  Authn + coarse authz + route allowlist
  Strip X-User/X-Tenant/X-Roles
  Rate limit/TLS/proxy trust
  Forward access token đúng resource

Orders Service:
  Verify token độc lập (issuer + aud + signature + exp)
  Check SCOPE_orders.read
  Check signed tenant == requested tenant
  Check record.tenant + owner/ACL
  401/403/404 theo policy

Không nhầm:
  Gateway authenticated != backend authorized
  Internal IP / mTLS != quyền trên record
  TokenRelay != token exchange
  Token active != valid audience
  X-User header != trusted principal
  Jwt test fixture != signature verification
```

**Thông điệp:** Gateway giữ **cửa vào và đường đi**, downstream giữ **tài nguyên, tenant và dữ liệu**. Kết hợp hai ranh giới độc lập giúp hạn chế tác động khi một proxy rule, identity header hoặc route bị cấu hình sai.

## 18. Tài liệu chính thức

- [Spring Cloud Gateway 4.3 — Server WebFlux starter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html)
- [Spring Cloud Gateway — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway 4.3 — TokenRelay](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway 4.3 — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/stripprefix-factory.html)
- [Spring Cloud Gateway 4.3 — HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)
- [Spring Boot 3.5 — Spring Security and JWT Resource Server](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security 6.5 — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — OAuth 2.0 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
