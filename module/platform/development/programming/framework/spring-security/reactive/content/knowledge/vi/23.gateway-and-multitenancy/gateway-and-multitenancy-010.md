# Ranh giới giữa bảo mật HTTP, phân quyền nghiệp vụ và chính sách hạ tầng

> **Chủ đề:** Spring Security – reactive  
> **Nhóm:** Gateway và nhiều tenant  
> **Bài học:** Ranh giới giữa bảo mật HTTP, phân quyền nghiệp vụ và chính sách hạ tầng.  
> **Baseline thực hành:** Java 17+, Spring Boot 3.5.16, Spring Cloud 2025.0.3 (Gateway Server WebFlux 4.3.x), Spring Security 6.5.x. Đây là baseline để học APIs, **không phải release train production được khuyên dùng vào tháng 11/2026** vì các nhánh 3.5/2025.0 đã hết OSS support.

## 1. Bài toán: JWT hợp lệ, tại sao vẫn có thể rò dữ liệu?

Một SaaS có hai tổ chức: tenant `acme` sở hữu báo cáo `r1` của `alice` và `r2` của `carol`; tenant `beta` có báo cáo **cùng ID** `r1` của `bob`. Khách hàng gọi:

```http
GET /api/tenants/acme/reports/r1 HTTP/1.1
Host: api.example.test
Authorization: Bearer <valid-JWT-for-alice-acme>
```

Spring Cloud Gateway xác thực JWT và thấy scope `reports.read`. Nếu backend nhận `reportId=r1` rồi truy vấn:

```sql
-- Sai: không ràng tenant hoặc actor.
SELECT * FROM reports WHERE id = :reportId;
```

nó có thể chọn bản ghi thuộc Beta hoặc một người khác. Đây là **BOLA/IDOR** (*Broken Object Level Authorization / Insecure Direct Object Reference*). Token hợp lệ chứng minh claim do nhà phát hành tin cậy cấp, **không chứng minh quyền đọc một bản ghi cụ thể**.

Kiến trúc đúng:

```text
Client
  |
  | HTTPS + Bearer JWT + tenant trong URL (tenant candidate)
  v
+----------------------------------------------------------+
| GATEWAY: HTTP SECURITY                                   |
| Verify JWT signature/exp/nbf/iss/aud                     |
| Method/path allowlist + coarse scope SCOPE_reports.read |
| Route cố định, strip spoofed headers, quota/throttling   |
+----------------------------------------------------------+
  |
  | Forward JWT tới trusted backend, không forward X-User giả.
  v
+----------------------------------------------------------+
| DOMAIN API: RESOURCE / TENANT AUTHORIZATION              |
| Re-verify JWT (defense in depth)                         |
| pathTenant == verifiedJwt.tenant_id                       |
| activeMembership(jwt.sub, tenant)                         |
| report.tenant_id == tenant AND actorCanRead(report)       |
+----------------------------------------------------------+
  |
  | Tenant-scoped repository query
  v
+----------------------------------------------------------+
| INFRASTRUCTURE / DATA                                    |
| NetworkPolicy, mTLS, TLS, DB RLS, encryption, quotas     |
| Key rotation, secrets, observability, audit              |
+----------------------------------------------------------+
```

**Cần cả ba ranh giới:**
- Gateway quyết định request có được vào **nhóm HTTP API**.
- Domain service quyết định actor có được chạm **đúng tenant và object** hay không.
- Infrastructure giới hạn đường kết nối, sức chứa, cách ly và bảo vệ dữ liệu; nó không tự hiểu ownership.

### Sau bài này bạn có thể

1. Phân biệt authentication với HTTP authorization, domain authorization và infrastructure policies.
2. Đặt JWT/issuer/audience/scope, tenant/membership/owner và mTLS/NetworkPolicy/quotas đúng tầng.
3. Nhận biết spoofed `X-Tenant-Id`, `X-User-Id`, `Forwarded`, cache key thiếu tenant và SQL không lọc tenant.
4. Dùng `SecurityWebFilterChain` độc lập tại Gateway và Reports API WebFlux.
5. Lấy `@AuthenticationPrincipal Jwt` để kiểm tra `tenant_id`/membership/owner ở reactive service.
6. Viết hai Maven projects và 24 unit/HTTP tests chứng minh không truy cập chéo tenant.
7. Giải thích HTTP `401`, `403`, `404`, `429` và `503` theo tầng.
8. Biết chính xác giới hạn của `mockJwt()` và loại integration tests còn cần trước production.

## 2. Ma trận trách nhiệm của từng tầng

| Quyết định | Tầng chính | Nguồn sự thật | Kết quả lỗi |
| --- | --- | --- | --- |
| TLS, mTLS certificate hợp lệ? | Ingress/infra | PKI, truststore | TLS failure |
| JWT chữ ký/time/issuer/audience hợp lệ? | Gateway **và** backend Resource Server | AS/JWKS trusted | 401 |
| HTTP URL/method, OAuth scope được phép? | WebFlux security | Verified JWT authorities, route policy | 403 |
| User còn thuộc tenant được yêu cầu? | Domain service | Membership DB/directory | 403/404 |
| User có quyền trên report này? | Domain service | Owner/ACL/sharing/business state | 403/404 |
| Query có bị lẫn dữ liệu tenant? | Repository/DB | Tenant predicate, RLS | No rows/denied |
| Backend có public ingress không? | Infrastructure | Firewall/NetworkPolicy/mTLS | Connection blocked |
| Tenant vượt quota/rate không? | Gateway/platform | Quota theo verified identity | 429/503 |
| Key/secret/cert được rotate thế nào? | Infra/SRE | Secrets manager, CA | Incident/availability |
| Ai đã đọc object nào? | Domain audit | Actor, tenant, resource, decision | Audit event |

Một security rule `hasAuthority("SCOPE_reports.read")` chỉ bảo vệ **nhóm API**. Một RLS policy chỉ so tenant cũng chưa chặn Alice đọc report của Carol cùng tenant. Một mTLS service identity cũng không chứng minh quyền của end user.

### 2.1. Authentication, authorization và authentication context

- **Authentication:** AS đã ký JWT? `iss`, `aud`, `exp`, `nbf`, signature/algorithm đúng không? Spring tạo `Authentication` cho `sub=alice`.
- **HTTP authorization:** Request GET và `SCOPE_reports.read` có đủ để đi vào nhóm route không?
- **Domain authorization:** Alice có membership active ở Acme, và bản ghi Acme/r1 có owner/ACL cho Alice?
- **Infra:** Workload nào kết nối được backend/DB, quota và khóa TLS được vận hành ra sao?

Dữ liệu của Spring Security WebFlux nằm trong **Reactor Context**, không được giả định một ThreadLocal Servlet cố định. Dùng `@AuthenticationPrincipal Jwt` trong controller và reactive composition ở service.

## 3. Tenant identity: thứ gì tin được?

```text
Path:           /api/tenants/acme/reports/r1
X-Tenant-Id:    beta                 <- attacker có thể đặt
X-User-Id:      bob                  <- attacker có thể đặt
Host:           acme.api.example.test
Forwarded:      host=beta.example.test
Verified JWT:   sub=alice, tenant_id=acme, scope=reports.read
DB membership:  (alice, acme) active=true
DB record:      (tenant=acme, id=r1, owner=alice)
```

**Path/Host/header là input/candidate, không phải proof of rights.** `X-Tenant-Id`/`X-User-Id`/`X-Roles` có thể bị bất kỳ client HTTP nào tự khai nếu không có cơ chế bảo vệ đặc biệt. `Host` và `X-Forwarded-Host` cần trusted domain/ingress rules; đừng dùng chúng để đổi tenant quyền hoặc downstream URI tùy ý.

**Verified JWT** chỉ đáng tin sau khi qua Spring Security Resource Server decoder đúng issuer, key, allowed algorithm, audience và thời gian. `tenant_id` được AS cấp có thể stale khi user bị rút khỏi tenant, nên **membership** cần được kiểm tra ở authoritative store. Report tenant và owner phải được kiểm tra với dữ liệu thực.

Trong mô hình một JWT cho một active tenant:

```text
JWT verified
AND SCOPE_reports.read
AND pathTenant.equals(jwt.tenant_id)
AND membershipActive(jwt.sub, pathTenant)
AND report.tenant_id == pathTenant
AND ownerOrAclAllows(jwt.sub, report)
```

Nếu user có nhiều tenants hoặc nhiều issuers, thiết kế claim/permission riêng chứ không mặc nhiên tin mọi `tenant_ids` do frontend cung cấp.

### 3.1. BOLA và cache key

```text
(acme, r1) -> Alice's report
(acme, r2) -> Carol's report
(beta, r1) -> Bob's report
```

Một cache chỉ theo ID `r1` có thể trả nhầm tenant. Cache key ít nhất phải gồm **tenant + resource type + resource ID**; nếu kết quả phụ thuộc người dùng/ACL còn cần actor, policy version hoặc caching ở tầng dữ liệu raw được cách ly. Tránh `@Cacheable(key="#reportId")` trên authorized responses trong SaaS nếu không review tenant/actor isolation.

### 3.2. Forwarded headers và trusted proxies

`X-Forwarded-For` có thể bị client giả để vượt rate limits theo IP. `X-Forwarded-Host` có thể gây sai route/tenant/redirect nếu tin mù quáng. Spring Cloud Gateway 4.3 WebFlux dùng namespace `spring.cloud.gateway.server.webflux.*`; các tính năng Forwarded/X-Forwarded được kiểm soát bằng `trusted-proxies`. **Không** đặt `trusted-proxies: .*` để tin toàn bộ Internet. Hãy giới hạn đúng proxy được phép, strip incoming untrusted headers và kiểm tra mỗi hop.

## 4. Gateway: HTTP security và điều không thể làm thay domain

Gateway thuận tiện để:

- Bắt HTTPS, kiểm tra JWT Bearer, issuer/audience/signature/time.
- Chặn sớm method/path/scope chưa được phép.
- Định tuyến tới downstream URI cố định/trusted service discovery.
- Strip identity headers không đáng tin, CORS/size limits.
- Rate limiting/quotas/WAF/DDoS, correlation IDs và access logs đã redact.

Gateway **không** nên giữ toàn bộ owner/ACL của triệu reports trong edge filter. Những quyết định dữ liệu biến đổi theo từng bản ghi thuộc service nghiệp vụ.

Ví dụ coarse rule:

```java
.authorizeExchange(ex -> ex
    .pathMatchers("/health").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
        .hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll())
```

Rule trên không xét tenant claim và không query membership. Nếu backend chỉ `permitAll("/api/**")` vì “Gateway đã kiểm tra”, một đường gọi trực tiếp từ worker, internal mesh, SSRF hoặc cấu hình ingress sai sẽ bypass toàn bộ identity enforcement. Vì vậy backend **tự xác thực JWT** và áp domain policies, ngay cả khi network/mTLS đã có.

### 4.1. Header sanitation không tạo quyền

Trong Gateway route, dùng `RemoveRequestHeader=X-Tenant-Id`, `RemoveRequestHeader=X-User-Id` và `RemoveRequestHeader=X-Roles`. Backend **không phụ thuộc** những headers này; JWT verified và domain store mới là nguồn quyết định. Không dùng:

```java
// SAI: mọi caller có thể giả HTTP header này.
String user = request.getHeaders().getFirst("X-User-Id");
String tenant = request.getHeaders().getFirst("X-Tenant-Id");
```

Nếu Gateway **phải** forward user identity, dùng một cơ chế nội bộ có cryptographic integrity/delegation, strip untrusted headers từ client và bảo vệ hop Gateway→backend. Một `X-Verified-User` raw string không tương đương signed internal identity token.

### 4.2. TokenRelay không đồng nghĩa forward Bearer

Spring Cloud Gateway có OAuth2 `TokenRelay`, thường cho OAuth2 Client/login session/authorized client. Demo này là Gateway **Resource Server nhận trực tiếp Bearer JWT** và chuyển cùng token tới API có audience phù hợp. Không cần bật TokenRelay ở đây. Nếu dùng BFF/session thì phải thiết kế OAuth2 Login, CSRF, cookie, authorized-client storage, token exchange và downstream audience theo mô hình đó. **Không thay access token bằng OIDC ID token** khi gọi Resource Server.

## 5. Domain: phân quyền nghiệp vụ có trạng thái

Domain API phải kiểm tra:

1. JWT đã verify, `sub` và `tenant_id`.
2. `{tenant}` trong URI khớp tenant claim.
3. User còn membership active trong tenant.
4. Object được truy vấn theo **tenant + report ID**, owner/ACL cho phép user.
5. Sharing/delegation/tenant role/feature flag/record status theo business rules.
6. DTO trả ra chỉ gồm dữ liệu đã được phép.

SQL minh họa:

```sql
SELECT r.tenant_id, r.id, r.title
FROM reports AS r
JOIN memberships AS m
  ON m.tenant_id = r.tenant_id
 AND m.subject_id = :subject
 AND m.active = TRUE
WHERE r.tenant_id = :tenant
  AND r.id = :report_id
  AND r.owner_sub = :subject;
```

Dùng bind parameters của R2DBC, không nối chuỗi SQL; `subject` từ verified identity, `tenant` từ route đã so với trusted claim/membership. Nếu report được chia sẻ, thêm ACL join để mở quyền có kiểm soát; **không bỏ owner check tùy tiện**.

### 5.1. 403 hay 404?

- JWT không có/invalid: **401** HTTP authentication.
- JWT valid nhưng thiếu scope: **403** HTTP authorization.
- JWT tenant khác path hoặc thiếu membership: **403** theo policy demo.
- Actor là member nhưng report thuộc người khác hoặc không tồn tại: **404**, giảm object enumeration.
- Rate limit: **429**; infra/DB outage: **503/5xx**, không cấp quyền ngầm.

Một API có thể chọn 404 cho cả tenant không có quyền để che resource existence; phải thống nhất policy, tests và không trả title/owner vào body lỗi.

## 6. Infra: phòng vệ, không phải business authorization

| Control | Bảo vệ | Không thay được |
| --- | --- | --- |
| TLS/mTLS | Kênh truyền và workload credentials | Quyền user trên report |
| NetworkPolicy | Không cho Internet gọi API trực tiếp | Tenant membership |
| WAF/DDoS | Giảm abuse, request-size limits | JWT issuer verification |
| Rate limiter | Quota tenant/IP/client | Object ACL |
| Circuit breaker/bulkhead | Cách ly lỗi downstream | Domain state |
| Secrets/KMS/PKI | Key/cert/secret rotation | Tenant claim binding |
| Database RLS | Row filter theo tenant | Owner/ACL của users cùng tenant |
| Audit/tracing | Điều tra event và hành vi | Enforcement |

Rate limit **trước** authentication có thể theo IP/proxy xác định đáng tin, còn per-tenant quota **sau** authentication dùng verified tenant/subject/client. Không tin raw XFF/X-Tenant-Id để cấp quota cao.

### 6.1. PostgreSQL RLS là lớp phòng vệ bổ sung

```sql
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON reports
USING (tenant_id = current_setting('app.tenant_id', true));
```

Đây là **minh họa chưa đủ cho production**. Phải set `app.tenant_id` **sau** authorization, scope theo đúng transaction/connection (cân nhắc `SET LOCAL`), chống rò tenant context qua pool, dùng DB user không có `BYPASSRLS` và test table owner/`FORCE RLS`. Nếu chỉ lọc tenant, Alice vẫn có thể đọc Carol trong cùng tenant; owner/ACL vẫn cần ở domain.

### 6.2. Egress, service identity và SSRF

Gateway route destination phải do deploy config/trusted registry quản lý. **Không** lấy URI target từ `X-Backend-Url` hoặc query param rồi proxy Bearer token — nguy cơ SSRF và token exfiltration. Với microservices, dùng mTLS/NetworkPolicy cho Gateway→API, không để API port public. Workload identity của Gateway không được mặc nhiên tương đương quyền user admin.

## 7. Hai Spring Boot apps độc lập

Ta xây:

```text
tenant-boundaries-demo/
├── gateway/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/gateway/
│       │   ├── GatewayApplication.java
│       │   ├── GatewaySecurity.java
│       │   └── GatewayHealthController.java
│       └── resources/application.yml
└── reports-api/
    ├── pom.xml
    └── src/
        ├── main/
        │   ├── java/demo/reports/
        │   │   ├── ReportsApplication.java
        │   │   ├── ApiSecurity.java
        │   │   ├── ReportService.java
        │   │   └── ReportController.java
        │   └── resources/application.yml
        └── test/java/demo/reports/
            ├── ReportServiceTests.java
            └── ReportsHttpSecurityTests.java
```

Gateway chạy `localhost:8080`, backend `localhost:8081`. Cả hai xác minh Bearer JWT với **cùng issuer/audience**, còn backend kiểm tra tenant/owner. IdP `id.example.test` trong YAML là **host giả**; tests dùng mock JWT nên không gọi tới IdP. Để HTTP end-to-end thực phải thay các endpoints và cung cấp JWT thật từ sandbox. HTTP loopback **chỉ demo**, production bắt buộc private transport/TLS/mTLS phù hợp.

Boot `3.5.16` tương thích Spring Cloud `2025.0.3`, nhưng Spring Cloud 2025.0.x kết thúc OSS support vào 30/06/2026. Với production cuối 2026, chọn train còn được hỗ trợ (ví dụ Boot 4.x/Cloud 2025.1.x tương thích) và migration tests; không ghép Spring Cloud 2025.1 với Boot 3.5 tùy ý.

## 8. Gateway Maven

### 8.1. gateway/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
  <groupId>demo</groupId>
  <artifactId>tenant-gateway</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>2025.0.3</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.cloud</groupId>
      <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

Spring Cloud 2025.0.x đổi starter Gateway WebFlux thành **`spring-cloud-starter-gateway-server-webflux`**, thay tên cũ đã deprecated `spring-cloud-starter-gateway`. Gateway Server WebFlux dùng Netty/Project Reactor; không phải Servlet WAR hoặc MVC Gateway.

### 8.2. gateway/src/main/resources/application.yml

```yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/demo
          jwk-set-uri: https://id.example.test/realms/demo/jwks
          audiences: reports-api
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: reports-api
              uri: http://127.0.0.1:8081
              predicates:
                - Path=/api/tenants/**
              filters:
                - RemoveRequestHeader=X-Tenant-Id
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Roles
                - RemoveRequestHeader=X-Authenticated-User
```

**Giải thích:**

- `issuer-uri` và `jwk-set-uri` là nguồn tin cậy cấu hình bởi operator, giúp verify JWT issuer + public keys. Chúng không được lấy từ JWT issuer URL chưa trust hoặc user input.
- `audiences` yêu cầu JWT được phát cho `reports-api`. Token valid signature nhưng sai audience vẫn không được chấp nhận.
- Prefix `spring.cloud.gateway.server.webflux.routes` là prefix mới, không dùng nhầm `spring.cloud.gateway.routes` của các ví dụ đời cũ.
- Destination URI cố định, không nhận arbitrary backend URL từ client.
- Các `RemoveRequestHeader` ngăn forwarded raw user/tenant/role headers. Backend vẫn phải bỏ qua chúng dù route này bị bypass.
- Giữ nguyên `Authorization` trong flow demo để API tự verify Bearer; không gửi credential tới unrelated origins.
- Chưa bật `TokenRelay` vì không dùng OAuth2 Client login/session. Forwarding received Bearer và OAuth2 TokenRelay là hai use cases khác nhau.
- Không bật `trusted-proxies: .*`; khi có proxy trước Gateway phải cấu hình allowlist cụ thể.

### 8.3. gateway/src/main/java/demo/gateway/GatewayApplication.java

```java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 8.4. gateway/src/main/java/demo/gateway/GatewaySecurity.java

```java
package demo.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurity {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Chỉ API Bearer stateless: không dùng login session cookie.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

`hasAuthority("SCOPE_reports.read")` chỉ là route-level requirement. Gateway không xác minh membership hoặc owner. `csrf.disable()` chỉ dành cho API thuần Bearer header do client chủ động gửi, **không áp dụng mặc định** cho browser BFF/session login vì browser credentials tự động có CSRF threat model khác.

### 8.5. gateway/src/main/java/demo/gateway/GatewayHealthController.java

```java
package demo.gateway;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GatewayHealthController {
    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("gateway OK");
    }
}
```

Endpoint public health không nằm trong `Path=/api/tenants/**` Gateway route. Production cần thiết kế liveness/readiness, không lộ thông tin IdP/DB/secrets.

## 9. Reports API Maven và JWT security độc lập

### 9.1. reports-api/pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
  <groupId>demo</groupId>
  <artifactId>tenant-reports-api</artifactId>
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
```

### 9.2. reports-api/src/main/resources/application.yml

```yaml
server:
  port: 8081
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/demo
          jwk-set-uri: https://id.example.test/realms/demo/jwks
          audiences: reports-api
```

Reports API tự validate Bearer JWT, không chấp nhận headers identity do Gateway hoặc Internet tự khai. JWT thật chỉ hoạt động khi thay IdP/JWKS giả bằng provider sandbox tin cậy.

### 9.3. reports-api/src/main/java/demo/reports/ReportsApplication.java

```java
package demo.reports;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
```

### 9.4. reports-api/src/main/java/demo/reports/ApiSecurity.java

```java
package demo.reports;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/tenants/*/reports/*")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // API Bearer, không dùng browser session trong demo.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Defense in depth:** Backend vẫn kiểm tra JWT/scope nếu đường gọi trực tiếp bypass Gateway; không dùng `permitAll("/api/**")` chỉ vì trước nó có Gateway.

## 10. Reports API domain service và controller

### 10.1. reports-api/src/main/java/demo/reports/ReportService.java

```java
package demo.reports;

import java.util.Map;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public final class ReportService {

    public record ReportView(
        String tenant, String id, String title) {}

    private record StoredReport(
        String tenant, String id, String ownerSub, String title) {}

    // Chỉ in-memory demo; production dùng R2DBC/directory,
    // kiểm tra tenant-aware identity và membership ACTIVE.
    private static final Map<String, Set<String>> MEMBERS = Map.of(
        "acme", Set.of("alice", "carol"),
        "beta", Set.of("bob")
    );

    // Report ID r1 trùng nhau ở hai tenants.
    private static final Map<String, StoredReport> REPORTS = Map.of(
        "acme|r1", new StoredReport(
            "acme", "r1", "alice", "Acme quarterly report"),
        "acme|r2", new StoredReport(
            "acme", "r2", "carol", "Carol private report"),
        "beta|r1", new StoredReport(
            "beta", "r1", "bob", "Beta quarterly report")
    );

    public Mono<ReportView> read(
            String pathTenant, String reportId, Jwt verifiedJwt) {

        return Mono.defer(() -> {
            String tokenTenant =
                verifiedJwt.getClaimAsString("tenant_id");
            if (tokenTenant == null ||
                    !pathTenant.equals(tokenTenant)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "Tenant claim mismatch"));
            }

            String subject = verifiedJwt.getSubject();
            if (subject == null || subject.isBlank() ||
                    !MEMBERS.getOrDefault(
                        pathTenant, Set.of()).contains(subject)) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN, "No active membership"));
            }

            StoredReport report =
                REPORTS.get(pathTenant + "|" + reportId);
            if (report == null ||
                    !pathTenant.equals(report.tenant()) ||
                    !subject.equals(report.ownerSub())) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
            }

            return Mono.just(new ReportView(
                report.tenant(), report.id(), report.title()));
        });
    }
}
```

**Giải thích quan trọng:**

1. `verifiedJwt` đến từ Spring Security `@AuthenticationPrincipal Jwt` đã verify chữ ký trong runtime thật. Unit tests sẽ dùng fixture nhưng không thay đổi production trust boundary.
2. So sánh `pathTenant` với `tenant_id` trusted từ JWT. Bất kỳ `X-Tenant-Id` header nào đều không được dùng.
3. Kiểm tra membership từ authoritative store. JWT tenant claim có thể stale khi user bị revoke khỏi tổ chức.
4. Lookup report theo key **tenant+report ID**, rồi owner. Không fetch/cached theo ID một mình.
5. Nếu record không tồn tại hoặc actor khác owner, dùng 404 theo domain policy; không tiết lộ record title.
6. `Mono.defer` đưa logic vào reactive subscription; với R2DBC, dùng `flatMap`/bound SQL params, không gọi `.block()`.
7. Static MEMBERS/REPORTS chỉ dùng cho ví dụ; production cần role/ACL, issuer-qualified `sub`, tenant membership status, caching/invalidation và audit.

### 10.2. reports-api/src/main/java/demo/reports/ReportController.java

```java
package demo.reports;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("api OK");
    }

    @GetMapping("/api/tenants/{tenant}/reports/{reportId}")
    public Mono<ReportService.ReportView> report(
            @PathVariable String tenant,
            @PathVariable String reportId,
            @AuthenticationPrincipal Jwt principal) {
        return service.read(tenant, reportId, principal);
    }
}
```

Controller không đọc `?user=` hoặc `X-User-Id` để tạo identity. `Jwt` là authenticated principal được Spring WebFlux Resource Server filter cung cấp trong Reactor Context. Controller trả DTO nhỏ, không dump raw JWT hoặc full DB record.

## 11. Unit tests: domain policy qua StepVerifier

### 11.1. reports-api/src/test/java/demo/reports/ReportServiceTests.java

```java
package demo.reports;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.server.ResponseStatusException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportServiceTests {

    private final ReportService service = new ReportService();

    private static Jwt jwt(String subject, String tenant) {
        // JWT Java fixture: không phải token ký thật.
        return Jwt.withTokenValue("unit-test-token")
            .header("alg", "none")
            .subject(subject)
            .claim("tenant_id", tenant)
            .build();
    }

    private void fails(
            String tenant, String id, Jwt jwt, HttpStatus status) {
        StepVerifier.create(service.read(tenant, id, jwt))
            .expectErrorMatches(error ->
                error instanceof ResponseStatusException ex &&
                ex.getStatusCode() == status)
            .verify();
    }

    @Test
    void aliceReadsOwnAcmeReport() {
        StepVerifier.create(
                service.read("acme", "r1", jwt("alice", "acme")))
            .assertNext(view -> {
                assertEquals("acme", view.tenant());
                assertEquals("r1", view.id());
                assertEquals("Acme quarterly report", view.title());
            })
            .verifyComplete();
    }

    @Test
    void bobReadsBetaReportWithSameId() {
        StepVerifier.create(
                service.read("beta", "r1", jwt("bob", "beta")))
            .assertNext(view ->
                assertEquals("Beta quarterly report", view.title()))
            .verifyComplete();
    }

    @Test
    void tenantMismatchIsForbidden() {
        fails("beta", "r1", jwt("alice", "acme"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void unknownMemberIsForbidden() {
        fails("acme", "r1", jwt("eve", "acme"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void aliceCannotReadCarolReport() {
        fails("acme", "r2", jwt("alice", "acme"),
            HttpStatus.NOT_FOUND);
    }

    @Test
    void unknownReportIsNotFound() {
        fails("acme", "missing", jwt("alice", "acme"),
            HttpStatus.NOT_FOUND);
    }

    @Test
    void tenantClaimAloneDoesNotCreateMembership() {
        fails("beta", "r1", jwt("alice", "beta"),
            HttpStatus.FORBIDDEN);
    }

    @Test
    void missingTenantClaimIsForbidden() {
        Jwt missing = Jwt.withTokenValue("unit-test-token")
            .header("alg", "none")
            .subject("alice")
            .build();
        fails("acme", "r1", missing, HttpStatus.FORBIDDEN);
    }
}
```

Có **8 `@Test` methods**. Hai report IDs giống nhau ở Acme/Beta giúp phát hiện một class bug phổ biến: query hoặc cache chỉ dùng report ID. `alg=none` chỉ là header trên **Jwt Java object fixture**, không đi qua decoder. Nó **không** phải policy cho phép Resource Server chấp nhận unsigned JWT; production JWT decoder phải verify signature và allowed algorithms.

## 12. HTTP tests: WebTestClient scope + tenant + owner

### 12.1. reports-api/src/test/java/demo/reports/ReportsHttpSecurityTests.java

```java
package demo.reports;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReportsHttpSecurityTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient as(
            String subject, String tenant, String authority) {
        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .subject(subject)
                .claim("tenant_id", tenant))
            .authorities(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("api OK");
    }

    @Test
    void withoutBearerIs401() {
        client.get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void aliceScopeTenantAndOwnerAllowRead() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("acme")
            .jsonPath("$.id").isEqualTo("r1")
            .jsonPath("$.title").isEqualTo("Acme quarterly report");
    }

    @Test
    void bobBetaGetsDifferentDataWithSameReportId() {
        as("bob", "beta", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("beta")
            .jsonPath("$.title").isEqualTo("Beta quarterly report");
    }

    @Test
    void missingReadScopeIs403() {
        as("alice", "acme", "SCOPE_profile.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jwtTenantDifferentFromPathIs403() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void forgedTenantHeaderCannotOverrideJwt() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .header("X-Tenant-Id", "beta")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void forgedUserHeaderCannotActAsBob() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/beta/reports/r1")
            .header("X-User-Id", "bob")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownMembershipIs403() {
        as("eve", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void sameTenantOtherOwnerGets404() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/r2")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void absentReportGets404() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/tenants/acme/reports/missing")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void forgedRoleHeaderCannotReplaceScope() {
        as("alice", "acme", "SCOPE_profile.read")
            .get().uri("/api/tenants/acme/reports/r1")
            .header("X-Roles", "ROLE_ADMIN")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void basicAuthCannotReplaceJwt() {
        client.get().uri("/api/tenants/acme/reports/r1")
            .headers(h -> h.setBasicAuth("alice", "secret"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownPathIsDefaultDenied() {
        as("alice", "acme", "SCOPE_reports.read")
            .get().uri("/api/internal")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postMethodIsDefaultDenied() {
        as("alice", "acme", "SCOPE_reports.read")
            .post().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenWithoutTenantClaimIs403() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
            .get().uri("/api/tenants/acme/reports/r1")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Có **16 WebTestClient tests**; project Reports API có **24 tests** tổng cộng. Bài test `mockJwt()` tạo authenticated principal giả nên **bypass JWT signature/JWKS/issuer/time validation**. Nó kiểm tra URL security, `SCOPE_` và business authorization, **không phải** kiểm thử chữ ký thật. Gateway route/TLS/RLS cũng không được kiểm thử trong suite này.

Để kiểm thử cryptographic JWT cần signed-token tests với `NimbusJwtEncoder`/`NimbusReactiveJwtDecoder` hoặc IdP/JWKS sandbox, và để kiểm thử proxy thật cần Gateway+mock downstream integration.

## 13. Chạy Maven và request thử

Hai projects độc lập từ thư mục `tenant-boundaries-demo`:

```bash
cd reports-api
mvn clean test
cd ../gateway
mvn clean test
```

Với dependencies và môi trường tương thích, reports-api **dự kiến** chạy 24 tests pass. Gateway chưa có test class riêng, `mvn test` kiểm tra Maven lifecycle/compilation. **Các tests này chưa được chạy Maven khi biên soạn Knowledge**; kết quả chỉ là kỳ vọng dựa trên mã. Kiểm tra log Surefire và dependency tree nếu có lỗi thay vì tự tuyên bố hoàn thành thực nghiệm.

Khởi động API (Terminal 1):

```bash
cd reports-api
mvn spring-boot:run
```

Khởi động Gateway (Terminal 2):

```bash
cd gateway
mvn spring-boot:run
```

Kiểm tra public health và thiếu token:

```bash
curl -i http://localhost:8081/health
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/tenants/acme/reports/r1
curl -i http://localhost:8081/api/tenants/acme/reports/r1
```

Dự kiến `/health` trả HTTP 200 với body `api OK` hoặc `gateway OK`, protected route không Bearer trả 401 tại cả hai.

### 13.1. Gửi JWT thật qua Gateway

YAML dùng `https://id.example.test/realms/demo` và `/jwks` **là địa chỉ minh họa**, không tồn tại IdP tại đó. Để chạy end-to-end:

1. Cấu hình Authorization Server sandbox phát JWT access tokens có issuer/audience/JWKS đúng.
2. Đổi `issuer-uri`/`jwk-set-uri` ở **cả Gateway và API**.
3. Cấp JWT có `sub=alice`, `tenant_id=acme`, scope `reports.read`, `aud` chứa `reports-api`, thời hạn hợp lệ và JWS signature đúng.
4. Truy cập Gateway:

```bash
# Chỉ sử dụng access token sandbox thật đã được AS cấp.
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/tenants/acme/reports/r1
```

Nếu các điều kiện đều đúng, API dự kiến trả:

```json
{"tenant":"acme","id":"r1","title":"Acme quarterly report"}
```

Thử thay path thành `/api/tenants/beta/reports/r1` với **cùng token Alice Acme**: Gateway có thể cho qua vì đúng scope coarse, nhưng domain service phải trả **403**. Đây chính là ranh giới của đề bài.

**Không dùng HTTP loopback kiểu demo ở production.** Dùng TLS/mTLS/private network, không commit tokens/secrets vào repo hoặc ticket. Token trong command line/shell history có thể bị lộ; chỉ dùng sandbox và hủy token phù hợp.

## 14. Khi có nhiều tenants hoặc nhiều issuers

### 14.1. Một user thuộc nhiều tenants

Có thể chọn:

| Token model | Tenant context | Điều cần kiểm tra |
| --- | --- | --- |
| Token một active tenant | `tenant_id` trong verified JWT | Path match + DB membership |
| Token có danh sách tenants | Verified `tenant_ids` | User chọn candidate + active membership |
| Token không có tenant | Verified subject + directory | Lookup policy mỗi request |
| Client credentials M2M | Verified service ID + tenant grants | Service không mặc nhiên được mọi tenants |
| Issuer mỗi tenant | Trusted issuer registry | Per-issuer audience/key/tenant mapping |

Demo dùng một active tenant để đơn giản. Trong model danh sách, không chỉ check `list.contains(tenant)` vì membership có thể bị revoke. Nếu làm tenant switching, phải có workflow chọn tenant có thẩm quyền/token issuance và UI rõ, không tin một `X-Tenant-Id` arbitrary.

### 14.2. JwtIssuerReactiveAuthenticationManagerResolver

Spring Security reactive hỗ trợ multi-issuer:

```java
// Snippet @Configuration, không phải class độc lập của demo.
JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-acme.example.test",
        "https://idp-beta.example.test");

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
```

Import từ `org.springframework.security.oauth2.server.resource.authentication`. `fromTrustedIssuers` dùng **allowlist tin cậy**. JWT `iss` chưa verify chỉ được dùng để chọn giữa các issuers đã được duyệt, **không** được tạo decoder/tải JWKS từ URL tùy ý của token hoặc query param.

Cần chú ý per-issuer **audience** và token profile validators, cùng tenant/member authorization ở domain. Resolver không tự biết resource owner hoặc đảm bảo audience của business API. Dynamic tenant onboarding phải theo trust registry được review/approved.

### 14.3. Opaque tokens

Nếu AS cấp opaque token, API dùng `ReactiveOpaqueTokenIntrospector`/RFC 7662 introspection thay vì JWT decoder. Token format khác không xóa ranh giới: HTTP authentication vẫn phải đi trước; domain phải tự xác định membership và permission trên object sau khi token được xác minh.

## 15. Khi quyền di chuyển khỏi HTTP request

- `POST/PATCH/DELETE`: enforce tenant membership, owner/ACL và method-specific permission ngay trong service.
- Search/pagination/export: filter toàn bộ tập dữ liệu và counts theo tenant, không leak aggregates.
- Cache: key tenant/resource và actor/ACL context khi response được cá nhân hóa.
- Cron/scheduler/queue: không có inbound `ServerWebExchange`; phải dùng verified service identity hoặc delegation context có integrity.
- Events: tenant ID trong payload của producer chưa authenticated là untrusted; bảo vệ message provenance.
- SSE/WebSocket: kiểm tra subscription/channel tenant authorization, không chỉ handshake.
- Object storage/presigned URLs: tenant/owner/access/expiry được kiểm tra trước khi cấp URL.

Nếu policy chỉ sống trong Gateway, những đường thực thi không qua Gateway sẽ **mất authorization**. Business service là nơi thực thi quyết định lâu dài theo domain.

## 16. Vận hành khi một thành phần lỗi

| Failure | Hành vi an toàn | Không được làm |
| --- | --- | --- |
| JWKS/AS unreachable, chưa verify JWT | Deny/appropriate error; fail closed | Skip signature |
| JWT audience sai | 401 | Chấp nhận vì scope đúng |
| Membership DB outage | Không cấp quyền, trả 5xx/503 theo policy | Mặc định user là member |
| Redis rate limiter down | Áp chính sách fail-open/fail-closed đã review theo endpoint | Vô hiệu mọi authorization |
| User bị revoke | Invalidate authz cache/giảm TTL | Giữ ROLE_ADMIN vô thời hạn |
| API public ingress bị mở nhầm | Backend JWT/domain checks vẫn áp; sửa network | Tin X-User-Id |
| Gateway route target do caller điều khiển | Reject, audit | Proxy token tới arbitrary host |
| DB RLS context không hợp lệ | No rows/deny | Dùng superuser bypass RLS |
| Cross-tenant cache collision | Stop/evict/audit exposure | Tiếp tục dùng key id-only |

Fail-open của một **availability control** (ví dụ một số rate limits) không cho phép **business authorization fail-open**. Quota, privacy và tenant isolation đều cần runbook/failure injection riêng.

## 17. Logging và audit

Log nên khác ở Gateway (route/status/latency/trace) và domain (actor, tenant, resource, decision). Ví dụ schema an toàn:

```json
{
  "requestId": "req-314",
  "layer": "domain",
  "route": "reports-api",
  "actorAlias": "hashed-actor",
  "tenantAlias": "hashed-tenant",
  "resourceType": "report",
  "decision": "DENY",
  "reasonCategory": "OBJECT_NOT_OWNED",
  "httpStatus": 404
}
```

Chỉ là **schema minh họa**, không phải log đã được tạo. Không log raw Bearer JWT, refresh tokens, secrets, key material hoặc report body nhạy cảm. Tránh user/tenant/report ID unbounded làm metric labels (cardinality/PII). Correlation ID không phải identity; một `X-Request-Id` caller tự đặt không được cho quyền gì.

## 18. Negative tests bắt buộc trước production

1. Real signed JWT: wrong key/issuer/audience/exp/nbf/alg, ID token không thay access token.
2. Gateway route: method allowlist, header sanitation, no open proxy, token không đến unrelated hosts.
3. Domain: wrong tenant path, missing membership, same-tenant non-owner, repeated IDs across tenants.
4. DB RLS: thiếu tenant predicate vẫn deny; pooled connections không rò context; DB role không BYPASSRLS.
5. Network/mTLS: direct backend blocked từ Internet; compromised service vẫn không bypass JWT domain policies.
6. Caching: tenant-qualified keys; revoke membership/role có invalidation.
7. Concurrency: hai tenants cùng report ID, parallel requests không trộn Reactor Context.
8. Failure injection: JWKS/IdP/DB/Redis outages, timeouts, 401/403/404/429/503 và no unsafe fallback.
9. Exports, searches, bulk update, queues, WebSocket channels và admin routes đều có BOLA coverage.

`mockJwt()` tests giúp chứng minh **domain policy** nhưng không chứng minh actual JWT signature validation; phải bổ sung crypto/JWKS/IdP integration tests trước production. Không báo mọi thứ PASS chỉ vì WebTestClient mockJwt pass.

## 19. Câu hỏi tự kiểm tra

**1. Gateway verify JWT và scope rồi thì có được bỏ object ACL ở API không?** Không, JWT scope không chứa quyền từng report.

**2. Vì sao không tin `X-Tenant-Id` do client gửi?** Header untrusted, dễ spoof/đổi tenant.

**3. Hai tenants có cùng ID `r1` thì cache theo ID một mình có an toàn không?** Không, dễ rò dữ liệu chéo tenant.

**4. Token tenant Acme gọi URL tenant Beta thì làm gì?** Từ chối 403 theo demo, bất kể caller ghi header nào.

**5. JWT còn hạn nhưng user đã mất membership?** Domain phải deny theo state mới nhất, không mặc định token còn hạn là đủ.

**6. NetworkPolicy chỉ cho Gateway gọi API đã đủ chưa?** Chưa, không giải quyết quyền theo user/report.

**7. `401` vs `403`?** 401 khi authentication không hợp lệ/thiếu; 403 khi đã authenticated nhưng thiếu permission hoặc CSRF/policy khác.

**8. Tại sao trả 404 khi Alice truy cập report của Carol?** Che object existence và tránh lộ record.

**9. Rate-limit theo tenant dựa vào nguồn nào?** Verified identity/tenant, không raw header.

**10. `trusted-proxies: .*` có an toàn không?** Không, tin mọi forwarded source có thể dẫn đến spoof IP/host.

**11. RLS tenant-only có ngăn cùng tenant xem dữ liệu nhau không?** Không, phải có owner/ACL.

**12. `mockJwt()` có verify RSA signature không?** Không, nó bypass decoder.

**13. Vì sao Gateway và API cùng verify JWT?** Defense in depth và chống gọi trực tiếp bypass Gateway.

**14. `TokenRelay` có cần với mọi incoming Bearer JWT không?** Không, TokenRelay chủ yếu cho OAuth2 Client authorized-token flow.

**15. CORS có thay object authorization không?** Không, CORS là browser cross-origin policy.

**16. Cron job có giữ authentication từ request bằng biến static được không?** Không; dùng service identity/delegation có integrity.

**17. Có thể tạo decoder cho mọi `iss` trong token không?** Không, chỉ trusted issuer allowlist.

**18. Nếu membership DB hỏng, nên mặc định cho truy cập để giữ uptime?** Không, fail closed.

## 20. Checklist triển khai

- [ ] Gateway và backend xác minh JWT signature, iss/aud/time và scope theo trust model.
- [ ] HTTP path/method allowlist, default deny, không có arbitrary downstream URI.
- [ ] Header spoofing được chặn; backend không tin X-Tenant/X-User/X-Roles.
- [ ] Forwarded/trusted proxy config theo allowlist, không wildcard trust.
- [ ] Tenant candidate từ URL so khớp verified tenant, membership active.
- [ ] Object owner/ACL check trong domain service, không chỉ gateway filter.
- [ ] SQL/R2DBC query ràng tenant+actor; bind parameters, không cache key id-only.
- [ ] RLS/DB roles/pooling được test độc lập, không BYPASSRLS.
- [ ] mTLS/NetworkPolicy/private backend ingress, secrets management và rotation.
- [ ] Rate limits/quotas theo verified tenant, không tin spoofed XFF.
- [ ] 401/403/404/429/503 có policy, lỗi không lộ private data.
- [ ] CSRF/CORS/BFF/TokenRelay được thiết kế đúng nếu có browser session.
- [ ] Async jobs, events, exports, search, SSE/WebSocket cũng áp tenant authorization.
- [ ] Multi issuer: trust registry, per-issuer audience, tenant mapping.
- [ ] Có negative tests cross-tenant/same tenant owner, spoofed headers, wrong scope.
- [ ] Có real JWT, Gateway proxy, RLS và network integration tests trước production.
- [ ] Audit domain-level actor/tenant/resource/outcome, redact tokens/PII.
- [ ] Phiên bản Boot/Cloud production còn được hỗ trợ và regression suite hoàn chỉnh.

## 21. Kết luận và nguồn chính thức

**Ghi nhớ một câu:** Gateway quyết định ai được vào **nhóm HTTP endpoint**; domain quyết định user được làm gì với **tenant và resource thực**; infrastructure quyết định **đường kết nối, cách ly và giới hạn tài nguyên**. Không lớp nào thay thế lớp kia.

```text
HTTP security:      verified JWT + route/method/scope policy
Business policy:    verified identity + tenant membership + object ACL
Infrastructure:     trusted networks + mTLS + RLS + quotas + secrets
```

Nếu chỉ có Gateway, SQL thiếu tenant hoặc cache key thiếu tenant vẫn rò dữ liệu. Nếu chỉ có RLS tenant, user cùng tenant vẫn có thể đọc data của nhau. Nếu chỉ có mTLS, service identity chưa chứng minh end-user rights. **Nhiều tenant an toàn đòi đủ ba ranh giới và negative tests.**

**Tài liệu:**

- Spring Security 6.5 – Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 – WebTestClient OAuth2 mockJwt: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security – Reactive Multi-tenancy: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- Spring Security 6.5 – JwtIssuerReactiveAuthenticationManagerResolver API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
- Spring Cloud Gateway 4.3 – WebFlux starter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html
- Spring Cloud Gateway – HttpHeadersFilters/trusted proxies: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html
- Spring Cloud Gateway – RemoveRequestHeader: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html
- Spring Cloud 2025.0 release notes (starter/prefix migration): https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes
- Spring Cloud 2025.0.3 release/support: https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/
- Spring Cloud supported versions: https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions
- OWASP API Security Top 10 – Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- RFC 6750 – OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 – JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
