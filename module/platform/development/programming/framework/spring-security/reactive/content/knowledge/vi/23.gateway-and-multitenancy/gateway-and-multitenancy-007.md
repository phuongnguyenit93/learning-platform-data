# Ngăn truy cập chéo tenant khi truy vấn tài nguyên và kiểm tra quyền

## Mục tiêu học tập

Bài thuộc phần **Gateway và nhiều tenant** của **Spring Security reactive (Spring WebFlux)**. Sau khi học, bạn có thể:

- Phân biệt **requested tenant** đến từ path/host/header với **authorized tenant** đã được kiểm tra dựa trên JWT identity, active membership và quyền nghiệp vụ.
- Giải thích **cross-tenant access**, **Broken Object Level Authorization (BOLA/IDOR)**, tenant ID spoofing, confused deputy, cache leakage và lỗi chỉ tin Gateway.
- Thiết lập logic cấp quyền gồm các điều kiện đồng thời: xác minh JWT, HTTP scope, tenant claim, membership còn hiệu lực, tenant của resource, owner/ACL và trạng thái resource.
- Dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **@EnableReactiveMethodSecurity**, **@PreAuthorize**, **@AuthenticationPrincipal Jwt** đúng reactive stack.
- Thực hiện đọc và cập nhật tài nguyên theo composite key **(tenant_id, document_id)**; phân biệt điều kiện ở middleware với điều kiện trong SQL/R2DBC/ACL.
- Thiết kế API Gateway không tin các header X-Tenant-Id/X-User-Id/X-Roles do client tự gửi, đồng thời bảo vệ downstream khi Gateway bị bypass.
- Chạy một ví dụ **Java 17 + Spring Boot 3.5** với tenant alpha/beta, document ID trùng nhau, permission per-tenant, HTTP GET/PATCH và kiểm thử WebTestClient với mockJwt.
- Lập kế hoạch bảo vệ search/count/export, Redis/cache, PostgreSQL RLS, background jobs, multi-issuer identity và security regression tests.

> **Phạm vi:** Ứng dụng nhiều **business tenants** (alpha, beta) cùng dùng **một issuer JWT** tin cậy. Nếu từng tenant có issuer riêng, xem mục multi-issuer. Ví dụ dùng Map in-memory để học cơ chế, **không thay cho database production**. Không có Special Note bổ sung.

## 1. Tenant routing không đồng nghĩa tenant authorization

Một HTTP request:

~~~http
GET /api/tenants/alpha/documents/doc-001 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Chuỗi alpha ở URL chỉ nói người gọi **muốn truy cập tenant nào**, không chứng minh họ thuộc tenant alpha. Gateway biết định tuyến nhưng có thể không biết owner của document doc-001 hay quyền còn hiệu lực của người dùng.

Luồng cần có:

~~~text
Client → API Gateway → Spring WebFlux Resource Server
                         |
                         ├─ JWT valid? (signature, iss, aud, exp/nbf)
                         ├─ Operation scope? (documents.read/write)
                         ├─ Token cho phép requestedTenant?
                         ├─ Membership hiện tại còn active và đúng action?
                         └─ Truy vấn document theo tenant + ID + owner/ACL
                              |
                              ├─ Sai/thiếu quyền → 401/403/404
                              └─ Đủ quyền       → DTO tối thiểu
~~~

Các khái niệm:

| Tên | Nguồn | Mức độ tin cậy |
|---|---|---|
| Requested tenant | Path, subdomain hoặc header từ request | Chỉ là selector **chưa tin cậy** |
| JWT subject | sub của token đã verify | Định danh trong phạm vi issuer |
| JWT tenant_ids | Claim do trusted issuer ký | Danh sách tenant được token cho phép; có thể stale |
| Active membership | Database/PDP của hệ thống | Quyền mới nhất theo tenant và action |
| Resource tenant_id | Row/data store tin cậy | Phải khớp requested tenant đã authorize |
| Owner/ACL | Dữ liệu server-side | Quyền trên **từng object** |
| X-Tenant-Id/X-Roles | Header do client có thể gửi | **Không tự là bằng chứng quyền** |
| Forwarded/X-Forwarded-* | Metadata reverse proxy | Không chứng minh tenant membership |

### 1.1. Quy tắc cấp quyền phải là phép AND

~~~text
ALLOW(user, tenant, action, resource) =
    VALID_JWT(user, expected_issuer, expected_audience)
    AND HAS_SCOPE(user, action)
    AND TOKEN_ALLOWS_TENANT(user, tenant)
    AND ACTIVE_MEMBER(user, tenant)
    AND TENANT_PERMISSION(user, tenant, action)
    AND RESOURCE_TENANT(resource) == tenant
    AND (OWNER(resource) == user OR VALID_ACL(user, resource, action))
    AND RESOURCE_STATE_ALLOWS(action)
~~~

Nếu một điều kiện sai thì **deny by default**. Chỉ có scope không có nghĩa được đọc mọi tenants. Chỉ là member tenant không có nghĩa được đọc private documents của người khác trong cùng tenant.

### 1.2. Hai ranh giới authorization khác nhau

**Cross-tenant:** Alice có token chỉ cho tenant alpha nhưng thử beta/doc-003. Phải từ chối ngay trước khi truy vấn beta.

**Cross-object trong tenant:** Alice thuộc alpha, có quyền documents.read nhưng thử alpha/doc-002 của Bob. Đây là **BOLA/IDOR**, vẫn phải từ chối theo owner/ACL.

OWASP API Security Top 10 2023 coi Broken Object Level Authorization là rủi ro hàng đầu. ID có dạng UUID khó đoán **không thay thế** kiểm tra quyền ở server.

### 1.3. Cùng document ID ở hai tenants

~~~text
alpha / doc-001 → owner Alice
beta  / doc-001 → owner Bob
~~~

Không dùng lookup hoặc cache key chỉ gồm doc-001. Dùng **TenantDocumentKey(tenant,id)**, SQL WHERE tenant_id + id, index/constraint composite và tenant-aware cache keys. Điều này vẫn cần thiết ngay cả khi hiện tại IDs là globally unique: policy phải rõ ràng để tránh lỗi khi tích hợp/import data.

## 2. JWT, principal và scope

Ví dụ payload minh họa, **không phải token đã được ký hợp lệ**:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["tenant-documents-api"],
  "sub": "alice",
  "tenant_ids": ["alpha"],
  "scope": "documents.read documents.write",
  "exp": 1893456000
}
~~~

Resource Server phải kiểm tra signature/JWKS, issuer, audience, expiration/nbf trước khi Spring Security tạo authenticated principal. Không decode Base64 payload rồi tin claims; không nhận scope/role/tenant từ header chưa được bảo vệ.

| Claim | Ý nghĩa | Không thay thế |
|---|---|---|
| iss | Trusted issuer | Object ownership |
| aud | Resource API token hướng đến | Tenant membership |
| sub | Identity trong issuer | Business permission |
| scope/scp | Quyền loại operation | Tenant + ACL |
| tenant_ids | Token tenant allowlist | Membership trạng thái hiện tại |
| exp/nbf | Thời gian hợp lệ | Quyền đã bị revoke sau issuance |

Trong Spring Security JWT Resource Server, scope có dạng:

~~~json
{"scope":"documents.read documents.write"}
~~~

được ánh xạ thành authorities:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Ở WebFlux, dùng **hasAuthority("SCOPE_documents.read")** để kiểm tra scope chứ không dùng hasRole("documents.read"), bởi prefix ROLE_ khác SCOPE_.

### 2.1. Tenant membership có thể thay đổi giữa hai access tokens

Một JWT có tenant_ids beta nhưng tài khoản Alice vừa bị thu hồi khỏi beta. Nếu chỉ nhìn JWT, backend có thể tiếp tục cho truy cập đến khi token hết hạn. Với tài nguyên nhạy cảm, dùng **active membership store**, policy engine, access token ngắn hạn, token version hoặc revocation checks theo SLA thu hồi quyền.

Cùng một user có thể có quyền write alpha, read beta. Không cho global ROLE_EDITOR tự cấp write toàn bộ tenants.

### 2.2. Requested tenant là input, không phải Authentication

Sai:

~~~java
// PHẢN VÍ DỤ: X-Tenant-Id chưa đáng tin.
String tenant = exchange.getRequest()
    .getHeaders().getFirst("X-Tenant-Id");
return repository.findByTenantId(tenant);
~~~

Đúng hơn: nhận tenant từ path như một đối tượng cần xét quyền, lấy **Jwt đã verify** qua @AuthenticationPrincipal và kiểm tra tenant đó thuộc token allowlist lẫn active membership. Chỉ sau đó repository mới nhận tenant đã authorize.

Nếu hệ thống dùng subdomain alpha.api.example.test, host cũng chỉ là routing selector. Map hostname qua trusted tenant registry, normalize path/host nhất quán, vẫn phải kiểm tra membership.

## 3. Gateway là defense-in-depth

Gateway có thể:

1. Terminate TLS/mTLS, route và canonicalize path/host.
2. Validate JWT hoặc chuyển token cho backend Resource Server validate lại.
3. Strip/overwrite các identity headers do client có thể spoof (X-User-Id, X-Roles, X-Tenant-Id).
4. Giới hạn routes, request sizes, timeouts và rate limit theo identity/tenant đã được authorize.
5. Gắn signed internal identity context hoặc mTLS giữa Gateway và backend nếu cần, với integrity, expiry và allowlist.
6. Chặn direct backend access trong network nếu thiết kế dựa vào Gateway boundary.
7. Log correlation ID mà không log raw JWT/Authorization header hay document contents.

Nhưng Gateway thường không biết doc-001 đang thuộc tenant nào, row owner hay ACL nào vừa bị revoke. **Downstream service phải tự enforce resource-level checks**.

### 3.1. Trusted proxies không phải trusted tenant claims

Spring Cloud Gateway WebFlux có Forwarded và X-Forwarded HTTP headers filters; cấu hình trusted-proxies cho phép kiểm soát những proxies được tin về routing headers. Điều này **không** tự làm X-Tenant-Id hoặc X-User-Id đáng tin.

Nếu Gateway đưa trusted identity vào headers, phải loại bỏ headers gốc của client và ngăn bypass trực tiếp, dùng mTLS/signed context; đừng giao toàn bộ authZ cho một header plaintext. Một lựa chọn rõ ràng hơn là Resource Server backend verify JWT và tra membership tự thân.

### 3.2. Khi Gateway rewrite URL

Ví dụ đổi /t/alpha/... sang /api/tenants/alpha/.... Phải test URL encoding, duplicate slashes, case, dot-segments, Unicode và Host header spoofing để Gateway/Backend không hiểu khác tenant. Map về một canonical **internal tenant ID**, tránh dùng display name cho authorization.

### 3.3. Service token có quyền mạnh tạo confused deputy

Một worker có client_credentials đọc nhiều tenants. User chỉ thuộc alpha nhưng có thể gửi job export beta. Nếu backend sử dụng quyền worker mà bỏ kiểm tra quyền caller, đây là **confused deputy**. Job phải authorize service identity, tenant, action và (nếu có) user initiating request riêng rẽ.

## 4. Phải scope query ngay tại R2DBC/database

### 4.1. Lỗi chỉ lookup theo ID

~~~java
// PHẢN VÍ DỤ, thiếu tenant:
return repository.findById(documentId);
~~~

Nếu record IDs trùng giữa tenants hoặc repository đọc từ shared table, rất dễ BOLA. Với PostgreSQL/R2DBC dùng tenant predicate:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.tenant_id = :authorized_tenant
  AND d.id = :document_id
  AND (
      d.owner_sub = :verified_subject
      OR EXISTS (
          SELECT 1
          FROM document_acl acl
          WHERE acl.tenant_id = d.tenant_id
            AND acl.document_id = d.id
            AND acl.grantee_sub = :verified_subject
            AND acl.can_read = TRUE
      )
  );
~~~

**authorized_tenant** là requested tenant sau khi membership/policy cho phép. **verified_subject** lấy từ Jwt đã được verify. Dùng **bind parameters**, không nối query input vào SQL strings.

Nếu có multi-issuer identity, dùng (issuer,subject) hoặc internal user ID, không so mỗi email/display name.

### 4.2. Composite schema keys

~~~sql
CREATE TABLE documents (
    tenant_id VARCHAR(80) NOT NULL,
    id VARCHAR(80) NOT NULL,
    owner_sub VARCHAR(200) NOT NULL,
    title TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id)
);

CREATE INDEX documents_owner_idx
ON documents (tenant_id, owner_sub, id);
~~~

Foreign keys của ACL/attachments nên tham chiếu cả **tenant_id và document_id**. Không để attachment beta trỏ nhầm alpha/doc-001.

### 4.3. Conditional update và TOCTOU

Sai:

~~~sql
UPDATE documents SET title = :title WHERE id = :id;
~~~

Đúng hơn:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE tenant_id = :authorized_tenant
  AND id = :document_id
  AND owner_sub = :verified_subject
  AND version = :expected_version
RETURNING id, title, version;
~~~

Nếu editor quyền từ ACL, thêm predicate ACL trong cùng transaction/conditional update. Không check owner bằng GET rồi UPDATE theo id không điều kiện, vì owner/ACL/tenant có thể thay đổi giữa hai thao tác (TOCTOU). Cần version/locking/transaction phù hợp.

### 4.4. Search, list, count, export và pagination

Không SELECT toàn bộ rồi lọc tenant trong Java **sau LIMIT/OFFSET**: page counts có thể sai và có thể lộ metadata. Dùng:

~~~sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND owner_sub = :verified_subject
ORDER BY created_at DESC, id
LIMIT :page_size;
~~~

Tương tự với COUNT, aggregates, Elasticsearch/OpenSearch, files, webhooks, websocket streams, batch update và async exports. Tenant scope phải nằm trong truy vấn/index policy ngay từ đầu.

### 4.5. PostgreSQL Row Level Security

Một lớp bổ sung:

~~~sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
~~~

RLS chỉ là defense-in-depth:

- app.tenant_id phải được set từ **authorized tenant**, không từ X-Tenant-Id raw.
- Khi dùng R2DBC/connection pool, set tenant trong **transaction scope** (ví dụ SET LOCAL trong transaction), không leak qua connections.
- DB owner/superuser có thể bypass RLS, xem FORCE ROW LEVEL SECURITY và database roles.
- RLS không bảo vệ cache, search, object storage hoặc mọi business ACL.
- Chạy tests trên database thật, nhiều concurrent tenants và connection reuse.

Separate schema hoặc DB per tenant có isolation tốt hơn ở vài khía cạnh, nhưng routing tenant→schema/datasource vẫn cần **trusted allowlist**, không lấy raw path nối thành SQL identifier/JDBC URL.

## 5. Reactive context và các hệ thống phụ

### 5.1. Không lưu tenant vào ThreadLocal hoặc singleton mutable state

WebFlux dùng **Reactor Context** và có thể chuyển threads. Một static ThreadLocal currentTenant hay field mutable trong singleton service sẽ dễ gây cross-request contamination.

Cách dễ audit: **Controller nhận (requestedTenant, authenticatedJwt) → Service validate → Repository nhận authorizedTenant explicit**. Nếu dùng Reactor Context cho trusted tenant, chỉ thêm nó sau khi authorize và có tests propagation; không set trusted context từ một raw header.

### 5.2. Cache keys

Không dùng:

~~~text
document:doc-001
~~~

Vì alpha và beta cùng có doc-001. Dùng ít nhất:

~~~text
tenant:alpha:document:doc-001
tenant:beta:document:doc-001
~~~

Nếu response phụ thuộc ACL/user/field masking, cache key hoặc cache strategy còn phải gắn identity/policy version; hoặc cache server-side raw object rồi kiểm tra quyền trước khi serialize. Invalidate khi membership, owner hay ACL thay đổi; private HTTP responses thường cần Cache-Control private/no-store phù hợp.

### 5.3. Background job và audit

Một scheduled export không có ServerWebExchange/Authentication của user. Phải dùng service identity và tenant scope rõ ràng:

~~~text
trusted job tenant=alpha
  -> authorize service to export alpha
  -> select alpha-scoped data
  -> write output under alpha namespace
  -> emit alpha-scoped event
  -> audit tenant + service + job ID
~~~

Không đưa Bearer token, email, raw document contents vào shared logs/traces. Nếu cho tenants đọc logs/audit dashboards, quyền truy cập dashboard cũng phải tenant-scoped.

### 5.4. Multi-issuer khác business multi-tenancy

Business tenant alpha/beta có thể dùng chung issuer. Khi thực sự có nhiều JWT issuers, Spring Security reactive có **JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)**. Chỉ cho trusted issuer allowlist, **không** nhận arbitrary iss rồi tự tạo decoder/JWKS, vì có thể dẫn đến arbitrary trust/SSRF.

Nếu hai issuers đều có sub alice, chúng là hai identities khác nhau. Membership key phải gồm (issuer,sub,tenant) hoặc map đến internal user ID đã xác minh.

## 6. Lab Java 17: Scope + tenant claim + active membership + owner

Demo là một Spring Boot 3.5.16 WebFlux Resource Server, có hai endpoints:

- GET /api/tenants/{tenant}/documents/{id}: yêu cầu SCOPE_documents.read và membership documents:read, rồi owner hoặc tenant-scoped documents:read:any.
- PATCH /api/tenants/{tenant}/documents/{id}: yêu cầu SCOPE_documents.write và membership documents:write, rồi **owner**.
- GET /api/health: public.

Dữ liệu:

| Tenant | Document | Owner | Title |
|---|---|---|---|
| alpha | doc-001 | alice | Alpha Alice document |
| alpha | doc-002 | bob | Alpha Bob document |
| beta | doc-001 | bob | Beta Bob document |
| beta | doc-003 | alice | Beta Alice document |

Membership server-side:

| Tenant | User | Quyền |
|---|---|---|
| alpha | alice | documents:read, documents:write |
| alpha | bob | documents:read |
| beta | alice | documents:read |
| alpha | auditor | documents:read, documents:read:any |

Chú ý **doc-001 xuất hiện ở cả alpha và beta**. Auditor chỉ có quyền đọc bất kỳ document trong alpha, không tự được đọc beta.

### 6.1. Project

~~~text
tenant-isolation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/TenantIsolationApplication.java
    │   └── resources/application.yml
    └── test/java/example/TenantIsolationTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'tenant-isolation'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - tenant-documents-api
~~~

Các issuer/JWKS URLs **chỉ minh họa**; để xác minh JWT thật cần IdP thật, correct issuer/JWKS/audience. Khi đã cung cấp cả issuer-uri và jwk-set-uri, decoder vẫn validate issuer và tải keys khi cần nhưng không nhất thiết phải discovery ở startup. Test offline dùng mockJwt không truy cập IdP.

### 6.2. Code chạy độc lập trong Spring Boot

**src/main/java/example/TenantIsolationApplication.java**

~~~java
package example;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class TenantIsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(TenantIsolationApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            // Chỉ phù hợp Bearer-header API không dùng cookie auth.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/tenants/*/documents/*")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.PATCH,
                    "/api/tenants/*/documents/*")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }

    public record TenantDocumentKey(String tenant, String id) {}
    public record TenantUserKey(String tenant, String sub) {}
    public record TenantMember(
        boolean active, Set<String> permissions) {}
    public record DocumentRecord(
        String tenant, String id, String ownerSub, String title) {}
    public record DocumentView(String id, String title) {}
    public record RenameRequest(String title) {}

    @Service
    public static class DocumentService {

        // DỮ LIỆU LAB: production dùng R2DBC/PDP thực sự.
        private final Map<TenantUserKey, TenantMember> members =
            Map.of(
                new TenantUserKey("alpha", "alice"),
                    new TenantMember(true, Set.of(
                        "documents:read", "documents:write")),
                new TenantUserKey("alpha", "bob"),
                    new TenantMember(true, Set.of("documents:read")),
                new TenantUserKey("beta", "alice"),
                    new TenantMember(true, Set.of("documents:read")),
                new TenantUserKey("alpha", "auditor"),
                    new TenantMember(true, Set.of(
                        "documents:read", "documents:read:any"))
            );

        private final ConcurrentMap<TenantDocumentKey, DocumentRecord>
            documents = new ConcurrentHashMap<>(Map.of(
                new TenantDocumentKey("alpha", "doc-001"),
                    new DocumentRecord("alpha", "doc-001",
                        "alice", "Alpha Alice document"),
                new TenantDocumentKey("alpha", "doc-002"),
                    new DocumentRecord("alpha", "doc-002",
                        "bob", "Alpha Bob document"),
                new TenantDocumentKey("beta", "doc-001"),
                    new DocumentRecord("beta", "doc-001",
                        "bob", "Beta Bob document"),
                new TenantDocumentKey("beta", "doc-003"),
                    new DocumentRecord("beta", "doc-003",
                        "alice", "Beta Alice document")
            ));

        private ResponseStatusException denied() {
            return new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        private ResponseStatusException hidden() {
            return new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        private Mono<TenantMember> requireMember(
            Jwt jwt, String tenant, String action) {

            return Mono.defer(() -> {
                if (jwt == null || jwt.getSubject() == null
                    || jwt.getSubject().isBlank() || tenant == null
                    || !tenant.matches("[a-z][a-z0-9-]{0,39}")) {
                    return Mono.error(denied());
                }

                // Jwt đã verify ở resource server; sai schema → deny.
                Object raw = jwt.getClaim("tenant_ids");
                if (!(raw instanceof Collection<?> ids)
                    || ids.stream().anyMatch(
                        item -> !(item instanceof String))
                    || !ids.contains(tenant)) {
                    return Mono.error(denied());
                }

                // Quyền hiện tại server-side quan trọng hơn token cũ.
                TenantMember member = members.get(
                    new TenantUserKey(tenant, jwt.getSubject()));

                if (member == null || !member.active()
                    || !member.permissions().contains(action)) {
                    return Mono.error(denied());
                }

                return Mono.just(member);
            });
        }

        private DocumentView view(DocumentRecord doc) {
            return new DocumentView(doc.id(), doc.title());
        }

        @PreAuthorize("hasAuthority('SCOPE_documents.read')")
        public Mono<DocumentView> read(
            String tenant, String id, Jwt jwt) {

            return requireMember(jwt, tenant, "documents:read")
                .flatMap(member -> Mono.justOrEmpty(
                    documents.get(new TenantDocumentKey(tenant, id)))
                    .filter(doc ->
                        Objects.equals(
                            doc.ownerSub(), jwt.getSubject())
                        || member.permissions().contains(
                            "documents:read:any"))
                    .map(this::view)
                    .switchIfEmpty(Mono.error(hidden())));
        }

        @PreAuthorize("hasAuthority('SCOPE_documents.write')")
        public Mono<DocumentView> rename(
            String tenant, String id, Jwt jwt,
            RenameRequest request) {

            return requireMember(jwt, tenant, "documents:write")
                .flatMap(member -> Mono.defer(() -> {
                    if (request == null
                        || request.title() == null
                        || request.title().isBlank()
                        || request.title().length() > 120) {
                        return Mono.error(
                            new ResponseStatusException(
                                HttpStatus.BAD_REQUEST, "Invalid title"));
                    }

                    AtomicReference<DocumentRecord> updated =
                        new AtomicReference<>();
                    TenantDocumentKey key =
                        new TenantDocumentKey(tenant, id);

                    // Atomic condition within one map key for demo.
                    // Production: UPDATE WHERE tenant+id+owner+version.
                    documents.computeIfPresent(key, (k, old) -> {
                        if (!Objects.equals(
                                old.ownerSub(), jwt.getSubject())) {
                            return old;
                        }
                        DocumentRecord next = new DocumentRecord(
                            old.tenant(), old.id(),
                            old.ownerSub(), request.title());
                        updated.set(next);
                        return next;
                    });

                    return Mono.justOrEmpty(updated.get())
                        .map(this::view)
                        .switchIfEmpty(Mono.error(hidden()));
                }));
        }
    }

    @RestController
    public static class DocumentController {

        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/api/health")
        public Mono<Map<String, String>> health() {
            return Mono.just(Map.of("status", "ok"));
        }

        @GetMapping("/api/tenants/{tenant}/documents/{id}")
        public Mono<DocumentView> read(
            @PathVariable String tenant,
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
            return service.read(tenant, id, jwt);
        }

        @PatchMapping("/api/tenants/{tenant}/documents/{id}")
        public Mono<DocumentView> rename(
            @PathVariable String tenant,
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody Mono<RenameRequest> body) {
            return body.flatMap(request ->
                service.rename(tenant, id, jwt, request));
        }
    }
}
~~~

### 6.3. Giải thích các rào chắn

**JWT Resource Server:** Spring Security decoder kiểm tra signature/issuer/audience/expiry. Token invalid/không có thường trả 401.

**Operation scope:** HTTP GET cần SCOPE_documents.read, PATCH cần SCOPE_documents.write. Mọi path/method khác deny all.

**Method security:** @PreAuthorize trên service giúp ngăn một caller khác qua Spring proxy bỏ qua HTTP rule. Reactive method trả Mono, đọc Authentication từ Reactor Context.

**Token allowlist:** requireMember kiểm tra tenant_ids Collection chứa requested tenant, đúng kiểu, subject không null/blank. Không tự fallback default tenant.

**Current membership:** Server store phải có active member với documents:read hoặc documents:write của đúng tenant. Trong demo là Map, production là DB/PDP.

**Object isolation:** TenantDocumentKey(tenant,id) làm composite lookup. Owner kiểm tra bằng JWT sub; auditor chỉ được read:any trong alpha. Không có global admin bypass.

**Write:** computeIfPresent kiểm tra owner và update dưới critical section của map key; production dùng conditional SQL trong transaction. Membership active có thể thay giữa hai calls, production cần freshness/invalidation và chính sách transaction.

**Response minimization:** DTO chỉ id/title, không xuất member roles/owner/tenant nội bộ nếu không cần.

**Header spoofing:** X-Tenant-Id/X-Roles không được đọc để cấp quyền, nên attacker không đổi tenant bằng header.

**CSRF:** Demo disable CSRF chỉ hợp lý cho Bearer-header API không có browser cookie/session authentication. Nếu dùng session cookie, cần CSRF/Origin/SameSite phù hợp, không copy disable vô điều kiện.

### 6.4. Chạy và quan sát

~~~bash
gradle bootRun
~~~

Với wrapper: ./gradlew bootRun (Linux/macOS) hoặc gradlew.bat bootRun (Windows).

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/tenants/alpha/documents/doc-001
~~~

Kỳ vọng health HTTP 200 và JSON:

~~~json
{"status":"ok"}
~~~

GET document **không token** kỳ vọng HTTP 401. Để gọi API protected thành công cần thay issuer/JWKS demo bằng IdP thật và dùng token đúng audience, scope, tenant_ids, subject. Không thể tạo access token hợp lệ từ placeholder idp.example.test. Đừng dán raw tokens vào issue, public logs hoặc shell history.

## 7. WebTestClient negative tests không cần IdP

Spring Security Test hỗ trợ **mockJwt()** để inject JWT Authentication vào mock WebFlux security context. Nó giúp kiểm tra **authorization** của scope, tenant, membership và owner, nhưng **không kiểm tra chữ ký JWT, issuer, audience hoặc expiry**. Các phần đó cần test decoder thật với signed JWT/JWKS riêng.

**src/test/java/example/TenantIsolationTest.java**

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TenantIsolationTest {

    @Autowired
    WebTestClient client;

    private WebTestClient as(
        String sub, List<String> tenants, String... authorities) {

        var granted =
            new SimpleGrantedAuthority[authorities.length];

        for (int i = 0; i < authorities.length; i++) {
            granted[i] =
                new SimpleGrantedAuthority(authorities[i]);
        }

        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", sub)
                .claim("tenant_ids", tenants))
            .authorities(granted));
    }

    @Test
    void publicHealthWorks() {
        client.get().uri("/api/health")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void noTokenReturns401() {
        client.get().uri(
            "/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceReadsOwnAlphaDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("doc-001");
    }

    @Test
    void noReadScopeReturns403() {
        as("alice", List.of("alpha"))
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeIsNotReadScope() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void alphaTokenCannotAccessBeta() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantClaimWithoutMembershipIsInsufficient() {
        as("charlie", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotReadBobsDocumentInSameTenant() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-002")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void unknownDocumentAlsoReturns404() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/not-there")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void sameIdInDifferentTenantsDoesNotLeak() {
        // doc-001 alpha của Alice, beta của Bob.
        as("alice", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void aliceCanReadOwnBetaDocumentWithBetaToken() {
        as("alice", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void alphaAuditorCanReadAlphaBobDocument() {
        as("auditor", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-002")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void alphaAuditorCannotReadBeta() {
        as("auditor", List.of("beta"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void spoofedTenantHeaderDoesNotChangeAuthorizedPath() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/alpha/documents/doc-001")
            .header("X-Tenant-Id", "beta")
            .header("X-Roles", "SUPER_ADMIN")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void spoofedHeaderDoesNotOpenBeta() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .get().uri("/api/tenants/beta/documents/doc-003")
            .header("X-Tenant-Id", "alpha")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void patchRequiresWriteScope() {
        as("alice", List.of("alpha"), "SCOPE_documents.read")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Try update"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void bobReadOnlyMembershipCannotWrite() {
        as("bob", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-002")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Try update"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCannotWriteBobsDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-002")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "No access"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void aliceCannotWriteBetaWithAlphaToken() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/beta/documents/doc-003")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "No access"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void aliceCanWriteOwnDocument() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                "Updated by Alice"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Updated by Alice");
    }

    @Test
    void blankTitleReturns400() {
        as("alice", List.of("alpha"), "SCOPE_documents.write")
            .patch().uri("/api/tenants/alpha/documents/doc-001")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new TenantIsolationApplication.RenameRequest(
                ""))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void unknownTenantIsNotAutoProvisioned() {
        as("alice", List.of("unknown"), "SCOPE_documents.read")
            .get().uri("/api/tenants/unknown/documents/doc-001")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc ./gradlew test / gradlew.bat test khi có wrapper. Có **22 test methods**, dự kiến pass với toolchain tương thích; **mã chưa được thực thi trong khi soạn bài**. Tests không cần IdP vì dùng mock WebFlux Authentication, nhưng chưa chứng minh JWT decoder thật, SQL RLS, cache và Gateway an toàn.

### 7.1. Tại sao cần những tests âm tính?

- 401 cho request không có token.
- 403 cho thiếu scope, requested tenant không có trong JWT claim, membership server không tồn tại hoặc thiếu quyền write.
- 404 cho wrong owner và document không tồn tại, theo policy che existence.
- **Cùng document ID giữa alpha/beta** để phát hiện repository key bị thiếu tenant.
- Auditor read-any chỉ **alpha**, không được beta.
- Header X-Tenant-Id/X-Roles bị spoof không thay identity/tenant đã authorize.
- PATCH có 200 cho owner hợp lệ, và 403/404 cho sai permission/owner/tenant.
- Public health 200 để tránh test suite chỉ chứng minh hệ thống từ chối mọi request.

Test patch thay title in-memory, các tests khác không phụ thuộc title gốc nên không cần cố định thứ tự chạy.

### 7.2. Cần test tích hợp bổ sung trước production

1. Dùng JWT thật có chữ ký từ test JWKS; thử sai signature, iss, aud, expired/nbf.
2. Chạy R2DBC/Testcontainers PostgreSQL, tạo cùng document ID ở hai tenants.
3. Mutation test bỏ tenant predicate để chứng minh regression tests phát hiện BOLA.
4. Revoke membership DB khi token còn hạn, request sau phải bị deny.
5. Thử stale ACL và owner transfer trong concurrent transactions.
6. Search/count/export/bulk phải giữ tenant predicate giống GET detail.
7. Cache Redis warm từ alpha không được phục vụ beta.
8. RLS connection pool SET LOCAL không leak tenant giữa subscriptions.
9. Gateway strip spoofed identity headers, chặn direct-to-backend bypass.
10. Kiểm tra background job/service credentials và tenant scoped outputs.

## 8. 401, 403 và 404 trong multi-tenant API

| Trạng thái | Mục đích | Ví dụ |
|---|---|---|
| **401** | Không có identity hợp lệ | Missing/invalid JWT |
| **403** | Có identity nhưng thiếu quyền | Scope thiếu, tenant claim không chứa requested tenant, membership bị revoke |
| **404** | Object không có/không được thấy | Document ID không có, document owner khác trong tenant đã authorize |
| **200** | Tất cả rào chắn thành công | Alice đọc alpha/doc-001 |

Nếu cần chống **tenant enumeration**, một số APIs có thể trả 404 cho tenant không thuộc caller thay vì 403. Chính sách HTTP phải thống nhất và kiểm tra không tiết lộ tenant/object existence qua error body, timing, counts hoặc audit endpoints. Logging nội bộ vẫn nên ghi lý do denial an toàn.

## 9. Lỗi phổ biến

**1. Chỉ kiểm tra scope:** documents.read không cho phép đọc mọi tenants.

**2. Chỉ lấy tenant từ path/header:** Đó là selector chưa trusted.

**3. Có membership nhưng bỏ owner/ACL:** Người dùng cùng tenant vẫn có thể đọc tài liệu riêng của người khác (BOLA).

**4. Repository chỉ dùng findById:** ID collision và lookup chéo tenant.

**5. Lọc tenant sau LIMIT:** Page counts sai, lộ metadata.

**6. Chỉ authZ ở Gateway:** Gateway không biết ACL row và có thể bị bypass.

**7. Tin X-Forwarded-* là identity:** Forwarded headers chỉ phục vụ network routing.

**8. Tin X-Tenant-Id/X-Roles do client gửi:** Dễ spoof, cần strip/verify trusted context.

**9. Token membership stale:** Dùng server-side active entitlement check cho revocation cần nhanh.

**10. Global admin không được scope theo tenant:** Dễ privilege escalation.

**11. Thiếu JWT audience validator:** Có thể nhận token cho resource server khác.

**12. Dùng mỗi sub khi nhiều issuers:** Hai issuers có thể trùng sub; dùng issuer+sub.

**13. Tạo issuer decoder từ raw token claim bất kỳ:** Nguy cơ arbitrary trust/SSRF.

**14. Tenant path nối thẳng thành schema/DB URI:** Injection/misrouting; phải dùng allowlist mapping.

**15. GET-check rồi UPDATE chỉ theo ID:** TOCTOU, cần conditional update/transaction.

**16. Cache key chỉ có document ID:** Có thể phục vụ beta từ cached alpha.

**17. Search/count/export không tenant scoped:** Rò dữ liệu dù detail endpoint đúng.

**18. ThreadLocal tenant trong Reactor:** Context trộn khi threads/concurrency đổi.

**19. Service token mạnh bỏ qua user permission:** Confused deputy.

**20. Chỉ test happy path 200:** Không chứng minh cross-tenant denial.

**21. mockJwt đồng nghĩa test chữ ký:** Sai; mock bypass decoder.

**22. Tắt CSRF trong app có session cookies:** Cần threat model riêng cho browser auth.

**23. Trả entity nguyên vẹn:** Có thể lộ owner/tenant/private fields; dùng DTO.

**24. Log JWT, token, document body:** Rò credentials/PII qua traces và logs.

**25. Tenant ID normalization lệch giữa hops:** Có thể bypass khi gateway/backend parse khác nhau.

**26. Foreign keys thiếu tenant:** ACL/attachment trỏ chéo tenants.

**27. RLS không set tenant đúng transaction:** Connection pool có thể rò context.

**28. Unknown tenant fallback default:** Fail closed, không auto-provision theo request.

## 10. Checklist triển khai

1. JWT issuer/JWKS, audience, signature và expiry được verify?
2. Tenant selector trong request luôn untrusted cho đến khi authorize?
3. Tenant ID canonical và map qua trusted registry?
4. SCOPE_documents.read/write tách theo method và fallback deny?
5. JWT tenant_ids có schema check và thiếu/sai → deny?
6. Active membership/permission theo tenant và subject hiện tại?
7. Role admin/read:any được scope theo tenant và audit?
8. Resource query luôn có tenant_id + id + owner/ACL?
9. DB composite primary/foreign keys, indexes đúng?
10. Conditional UPDATE/DELETE có tenant/owner/version/transaction?
11. List/count/search/export/batch/attachments scoped?
12. Cache keys, policy versions và invalidation chống cross-tenant leak?
13. Gateway strip headers identity spoofed và chặn bypass?
14. Trusted proxy metadata không bị dùng như authority?
15. Multi-issuer identity key issuer+sub/internal user ID?
16. Service-to-service/background jobs có tenant-aware policy?
17. Reactive context không phụ thuộc mutable global/ThreadLocal?
18. HTTP statuses 401/403/404 thống nhất theo threat model?
19. CSRF phù hợp browser cookie vs stateless Bearer?
20. Sensitive logs/traces/metrics không chứa raw tokens/data?
21. Có negative tests wrong tenant/owner/scope/membership và same ID?
22. Có integration tests signed JWT, DB/RLS, cache, Gateway và concurrent requests?
23. Có chính sách revoke ACL/membership và cache invalidation?
24. Trước khi thêm endpoint mới có security review tenant/data access?

## 11. Câu hỏi tự kiểm tra

**1.** Request có path beta đã chứng minh caller thuộc beta chưa?

**Đáp án:** Chưa. Đó là requested tenant; cần verified JWT + membership + permission.

**2.** Alice có documents.read trong alpha, được đọc document Bob không?

**Đáp án:** Không nếu thiếu explicit ACL/read:any được cấp cho alpha.

**3.** JWT còn beta trong tenant_ids sau khi membership bị revoke thì sao?

**Đáp án:** Server-side membership check phải deny; JWT claim có thể stale.

**4.** Vì sao query phải có tenant_id và id?

**Đáp án:** Có thể có cùng document ID ở nhiều tenants; composite predicate ngăn trả sai row.

**5.** Gateway đã validate JWT có thể cho downstream bỏ object authorization không?

**Đáp án:** Không. Gateway không biết row owner/ACL và có thể có bypass.

**6.** X-Tenant-Id đến từ client có tin để cấp quyền không?

**Đáp án:** Không. Cần trusted identity proof, gateway strip headers và backend recheck.

**7.** JWT scope được Spring map thành gì?

**Đáp án:** Mặc định documents.read thành SCOPE_documents.read.

**8.** Khi nào dùng 401/403/404 trong demo?

**Đáp án:** 401 chưa authenticated; 403 thiếu scope/membership/tenant; 404 sai owner hoặc document không có.

**9.** mockJwt đã test JWS signature/aud chưa?

**Đáp án:** Chưa. Phải test signed token/JWKS/decoder riêng.

**10.** RLS có thay thế membership policy ở Spring không?

**Đáp án:** Không. RLS là DB defense-in-depth, vẫn cần caller authorization, pool context và cache/search checks.

**11.** Hai issuers đều có sub alice thì sao?

**Đáp án:** Không đồng nhất identity; dùng issuer+sub hoặc trusted internal mapping.

**12.** Vì sao cache document:doc-001 không đủ?

**Đáp án:** Alpha/beta có thể cùng ID; cache phải tenant-aware và xét authorization dimensions.

**13.** Service token có quyền mọi tenants thì người dùng alpha yêu cầu export beta được không?

**Đáp án:** Không tự động. Phải authorize cả caller lẫn service operation để tránh confused deputy.

## Tài liệu chính thức

- Spring Security — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — Reactive HTTP Authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security — mockJwt for WebFlux tests: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.5 — issuer-uri, jwk-set-uri and audiences properties: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- Spring Cloud Gateway WebFlux — Trusted proxies and Forwarded headers: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html
- OWASP API1:2023 Broken Object Level Authorization: https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP REST Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
