# Tùy chỉnh introspector để bổ sung dữ liệu người dùng hoặc quyền

> **Module:** Spring Security – reactive  
> **Nhóm kiến thức:** Resource Server Opaque  
> **Trọng tâm:** Tùy chỉnh `ReactiveOpaqueTokenIntrospector` của Spring WebFlux theo mô hình **delegate introspection → kiểm tra token hợp lệ → bổ sung thông tin danh bạ/role từ nguồn đáng tin → tạo principal mới**, không phá hỏng scope và không mở lỗ hổng nâng quyền.  
> **Công nghệ ví dụ:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Reactor, WebTestClient.

## 1. Tình huống: token hợp lệ nhưng thông tin chưa đủ

Một API WebFlux bảo vệ báo cáo nhận opaque access token:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer opaque-access-token
```

Authorization Server (AS) có Introspection Endpoint theo RFC 7662. Resource Server kiểm tra token qua endpoint này, ví dụ AS trả:

```json
{
  "active": true,
  "sub": "alice",
  "client_id": "frontend-web",
  "scope": "reports.read profile.read",
  "aud": ["reports-api"],
  "exp": 1794003600
}
```

Response đã cho API biết: token còn `active`, subject là `alice`, client được cấp token, scopes, audience và thời hạn. Nhưng **nó chưa cho biết** tên hiển thị, phòng ban hay role nghiệp vụ (`REPORT_READER`, `REPORT_ADMIN`) đang được hệ thống quản trị nội bộ lưu.

Bạn muốn API có thể:

- Hiển thị `display_name` và `department` trong phản hồi hồ sơ người dùng.
- Quyết định `hasRole("REPORT_ADMIN")` dựa vào **danh bạ nội bộ đáng tin**, chứ không dựa vào header `X-Role: ADMIN` do người dùng tự gửi.
- **Giữ nguyên** các authorities `SCOPE_reports.read` mà Spring Security đã tạo từ thông tin của AS.
- Không cấp roles cho một token `active=false`, sai audience, thiếu `sub` hoặc subject không tồn tại trong danh bạ.
- Giữ toàn bộ xử lý **reactive** (`Mono`/`flatMap`), không `.block()` trên Netty event loop.
- Kiểm thử token thật đi qua WebFlux Bearer filter bằng **delegate giả trong test**, không cần một IdP thật.

Đó chính là mục đích hợp lý của custom `ReactiveOpaqueTokenIntrospector`.

### 1.1. Một sơ đồ đủ để nhớ

```text
API request: Authorization: Bearer <opaque-token>
        |
        v
WebFlux SecurityWebFilterChain / Opaque Token authentication
        |
        v
Custom ReactiveOpaqueTokenIntrospector
        |
        +--> delegate: SpringReactiveOpaqueTokenIntrospector
        |       |
        |       +--> POST Authorization Server /introspect
        |       |       client authentication + token
        |       +--> AS trả active=true và claims
        |       +--> active=false / invalid => AUTHENTICATION FAIL
        |
        +--> kiểm tra aud/sub từ validated introspection result
        |       |
        |       +--> sai/missing => FAIL CLOSED
        |
        +--> UserDirectory.findBySubject(sub) (reactive, trusted)
        |       |
        |       +--> displayName, department, authorized roles
        |       +--> subject lạ => FAIL CLOSED theo policy ví dụ
        |
        +--> DefaultOAuth2AuthenticatedPrincipal
                attributes = original + display_name + department
                authorities = original scopes + trusted roles
        |
        v
BearerTokenAuthentication / AuthorizationWebFilter
        |
        +--> SCOPE_reports.read? / ROLE_REPORT_ADMIN?
        +--> 403 nếu thiếu quyền; 200 nếu đủ
```

**Quy tắc quan trọng nhất:** gọi `delegate.introspect(token)` **trước**, chỉ enrich `OAuth2AuthenticatedPrincipal` mà delegate đã xác nhận. Không viết một introspector bỏ qua AS và cấp `ROLE_ADMIN` chỉ vì token bắt đầu bằng chuỗi nào đó; đó là **authentication bypass**, không phải “custom claims”.

### 1.2. Kết quả học tập

Sau bài, bạn có thể:

1. Phân biệt `ReactiveOpaqueTokenIntrospector`, `SpringReactiveOpaqueTokenIntrospector`, `NimbusReactiveOpaqueTokenIntrospector` (cũ, deprecated) và `OpaqueTokenIntrospector` Servlet.
2. Hiểu token introspection theo RFC 7662 và `active`, `scope`, `sub`, `aud`, `client_id`, `exp`.
3. Dùng `delegate.introspect(token).flatMap(...)` để gọi nguồn dữ liệu reactive.
4. Bổ sung attributes mà **không ghi đè** claims chuẩn của AS; bổ sung `SimpleGrantedAuthority("ROLE_...")` mà **không làm mất** `SCOPE_...`.
5. Chọn fail-closed khi thiếu subject/không có quyền hoặc nguồn quyền gặp sự cố.
6. Tích hợp `ServerHttpSecurity.oauth2ResourceServer(...opaqueToken(...))` trên WebFlux.
7. Viết dự án Maven Java 17+ chạy được với test offline: kiểm tra enrichment trực tiếp, 401/403, scope, role, audience, inactive token và Reactor laziness.
8. Biết giới hạn của tests: fake introspection cho phép kiểm thử business policy nhưng không chứng minh HTTP client credentials/RFC 7662 endpoint đã hoạt động thật.

## 2. Opaque token không có nghĩa token là JWT

**Opaque access token** thường là chuỗi mà Resource Server **không thể tự xác minh** hoặc không nên suy diễn nội dung. Token có thể trông ngẫu nhiên:

```text
q4g2aKxP...redacted...
```

Resource Server hỏi **Authorization Server**: “Token này có `active` không, và có các thuộc tính nào?” thông qua OAuth 2.0 Token Introspection (RFC 7662).

Request khái niệm (không dùng secret thật):

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <base64-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

token=opaque-access-token
```

Trên mạng thật: HTTPS, client authentication hợp lệ theo provider và form-url-encoding đúng chuẩn. AS có thể trả:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read",
  "aud": ["reports-api"],
  "client_id": "frontend-web"
}
```

Nếu token không hợp lệ hoặc đã bị revoke:

```json
{"active": false}
```

**Không biến `active=false` thành một principal hợp lệ.** `SpringReactiveOpaqueTokenIntrospector` mặc định xử lý kết quả introspection và từ chối token không active; custom wrapper phải giữ nguyên contract đó.

### 2.1. Introspection có thể áp dụng cho chuỗi có dạng JWT

Spring Security Opaque Token support không buộc token phải là chuỗi ngẫu nhiên; ngay cả một access token có format JWT, API vẫn có thể dùng **introspection** để kiểm tra trạng thái active/revocation theo policy. Trong trường hợp này vẫn dùng `ReactiveOpaqueTokenIntrospector`, không tự thay bằng `ReactiveJwtDecoder` rồi vô tình bỏ qua yêu cầu kiểm tra trạng thái AS.

Không “Base64 decode rồi tin claims” từ JWT chưa verify để bổ sung roles, đặc biệt nếu introspection chỉ trả `active=true`. Nếu có use case kết hợp claims từ token với introspection, phải xác minh nguồn claims, chữ ký và ràng buộc `sub/aud/iss` hoặc theo profile đã thống nhất.

### 2.2. Response không phải lúc nào cũng có cùng claims

RFC 7662 yêu cầu `active` trong response; các trường khác phụ thuộc provider/scope/contract. Không mặc định rằng mọi AS đều trả `aud`, `sub`, `email` hay `roles`. Nếu API của bạn **cần** subject/audience để bảo vệ dữ liệu, hãy chọn policy thiếu claim rõ ràng: **từ chối** token, hoặc cấu hình AS để cung cấp dữ liệu tương đương từ nguồn đáng tin, không đoán mặc định một subject.

Trong project này, **policy chủ ý yêu cầu** `sub` là một chuỗi không rỗng và `aud` chứa `reports-api`. Nếu AS thực dùng dạng `aud` khác, bạn cần chuẩn hóa theo contract đã kiểm chứng trước khi triển khai.

## 3. Các interface và class cần dùng

| Thành phần | Package | Nhiệm vụ |
| --- | --- | --- |
| `ReactiveOpaqueTokenIntrospector` | `org.springframework.security.oauth2.server.resource.introspection` | Interface `Mono<OAuth2AuthenticatedPrincipal> introspect(String)` |
| `SpringReactiveOpaqueTokenIntrospector` | Cùng package introspection | Delegate dùng endpoint AS và xác minh `active` |
| `NimbusReactiveOpaqueTokenIntrospector` | Cùng package introspection | Implementation cũ **deprecated** trong Spring Security 6.5 |
| `OAuth2AuthenticatedPrincipal` | `org.springframework.security.oauth2.core` | `getName()`, `getAttributes()`, `getAuthorities()` |
| `DefaultOAuth2AuthenticatedPrincipal` | `org.springframework.security.oauth2.core` | Tạo principal với attributes và authorities mới |
| `GrantedAuthority` | `org.springframework.security.core` | Đại diện một quyền, như `SCOPE_reports.read` hoặc `ROLE_REPORT_ADMIN` |
| `SimpleGrantedAuthority` | `org.springframework.security.core.authority` | Tạo authority theo tên đã được backend tin cậy |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Cấu hình reactive security filters |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Chuỗi filter cho WebFlux |
| `OAuth2AuthenticationException` | `org.springframework.security.oauth2.core` | Thất bại authentication do chính sách OAuth2 |
| `Mono` | `reactor.core.publisher` | Tín hiệu giá trị, empty hoặc error |

Interface chính:

```java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Đây là **shape API để đọc hiểu**, không cần định nghĩa lại nếu đã dùng Spring Security dependency. Trong Servlet MVC, `OpaqueTokenIntrospector.introspect(...)` trả object trực tiếp; **không copy** đoạn Servlet sang WebFlux rồi dùng `.block()`.

### 3.1. Principal và authorities sau introspection

Spring Security có thể tạo authorities mặc định từ `scope` của introspection result, mỗi scope được gắn prefix `SCOPE_`:

```text
Introspection response:
    "scope": "reports.read profile.read"

Spring GrantedAuthorities:
    SCOPE_reports.read
    SCOPE_profile.read
```

Nếu danh bạ nội bộ xác nhận user `alice` có role REPORT_READER, custom introspector nên tạo:

```text
SCOPE_reports.read       <-- giữ nguyên từ trusted introspection
SCOPE_profile.read       <-- giữ nguyên từ trusted introspection
ROLE_REPORT_READER       <-- thêm từ trusted directory
```

**Không nhầm `ROLE_REPORT_READER` với `SCOPE_reports.read`**. `hasRole("REPORT_READER")` theo convention sẽ kiểm tra authority `ROLE_REPORT_READER`; `hasAuthority("SCOPE_reports.read")` kiểm tra đúng tên authority của scope. Một role nội bộ không tự cấp thêm scope mà AS chưa cấp.

### 3.2. Không tự ép kiểu scope bừa bãi

Một số implementation chuyển `scope` thành **danh sách chuỗi**, không còn là chuỗi space-separated ban đầu. Nếu dùng `principal.getAttribute("scope")` rồi cast ngay `String`, code có thể lỗi `ClassCastException` tùy provider/converter. Để **giữ scope authorities**, an toàn và đơn giản nhất là sao chép `principal.getAuthorities()` **đã được delegate xây dựng** thay vì tự parse lại claim.

Khi thật sự cần custom mapping `groups` từ introspection response, hãy kiểm tra runtime type có phải collection/list/string và giá trị có thuộc allowlist hay không, rồi unit test các dạng thiếu/null/sai type. Không ép `roles` từ JSON client body thành authorities.

## 4. Cách tùy chỉnh đúng: decorator thay vì thay thế bước xác thực

Một custom introspector an toàn thường là **decorator**:

```java
public final class EnrichingOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final UserDirectory directory;

    public EnrichingOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            UserDirectory directory) {
        this.delegate = delegate;
        this.directory = directory;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(this::enrichValidatedPrincipal);
    }

    private Mono<OAuth2AuthenticatedPrincipal> enrichValidatedPrincipal(
            OAuth2AuthenticatedPrincipal principal) {
        // Xem project đầy đủ ở mục 10.
        return directory.findBySubject(principal.getAttribute("sub"))
            .map(user -> new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                principal.getAuthorities()));
    }
}
```

**Đây chỉ là đoạn mô tả kiến trúc, KHÔNG phải file Java chạy độc lập.** Bản đầy đủ ở mục 10 giải quyết `sub` null/sai kiểu, audience, missing user, bổ sung fields, bổ sung role và kiểu của `Collection<GrantedAuthority>`.

Đường đi cần luôn là:

1. `delegate.introspect(token)` phải thành công.
2. Kiểm tra thêm những constraints Resource Server cần.
3. Chỉ dùng `sub`/tenant từ **trusted introspection result** làm khóa tìm user.
4. Lấy roles từ **trusted directory** và chỉ cho phép roles nằm trong policy của API.
5. Copy attributes/authorities, **không mutate** objects của delegate hoặc global cache.
6. Trả **principal mới**; khi lỗi, propagate error thay vì tạo anonymous/admin.

### 4.1. map hay flatMap?

- Chỉ chuyển đổi dữ liệu đồng bộ (không I/O), ví dụ thêm một authority từ verified claim: `.map(principal -> enriched)`.
- Cần gọi một reactive repository, user directory, UserInfo HTTP endpoint hoặc service khác trả `Mono<UserProfile>`: `.flatMap(principal -> directory.findBySubject(...).map(...))`.

```java
// Đúng: kết nối hai thao tác async vào cùng reactive chain.
return delegate.introspect(token)
    .flatMap(principal ->
        directory.findBySubject(principal.getName())
            .map(user -> enrich(principal, user)));
```

Sai:

```java
// Sai trong Netty event loop, có thể gây blocking:
UserProfile user = directory.findBySubject(subject).block();

// Sai: subscribe tách lifecycle; chưa chắc principal đã được enrich.
directory.findBySubject(subject).subscribe(user -> cacheUser(user));
return delegate.introspect(token);
```

`flatMap` đảm bảo lỗi AS, lỗi directory và cancellation được truyền qua publisher; Spring Security không xác thực thành công trước khi enrichment hoàn tất.

### 4.2. Tại sao cần fail-closed?

Tình huống:

| Tình trạng | Hành vi ví dụ | Lý do |
| --- | --- | --- |
| Introspection `active=false` | **Từ chối** | Không chấp nhận revoked/expired token |
| AS timeout/401/5xx | **Không cấp authentication** | Không thể chứng minh token active |
| Token active nhưng thiếu `sub` | **Từ chối** | Không có identity đáng tin để map local roles |
| Token active nhưng audience sai | **Từ chối** | Không dành cho Resource Server này |
| Subject không có trong trusted directory | **Từ chối** theo policy project | Tránh tự mặc định cấp vai trò |
| Directory unavailable | **Không cấp role**, fail closed | Quyền nội bộ chưa thể xác minh |
| Token hợp lệ, user tồn tại, thiếu role | **Authenticate nhưng không cấp role đó** | 403 ở endpoint yêu cầu role |
| Token hợp lệ, user có role và scope phù hợp | **Thành công** | Quyền hai nguồn đã được kiểm tra |

Tùy kiến trúc, user thiếu trong directory có thể được xử lý như một principal chỉ có scopes mà **không có roles**, nếu API của bạn chỉ cần claims từ AS và đã thiết kế policy đó. Bài này cố ý chọn **require-known-user** để làm rõ ranh giới quyền. Không đánh đồng “fail closed” với việc mọi lỗi repository luôn phải chuyển thành HTTP 401: lỗi hạ tầng nội bộ có thể được biểu diễn thành 5xx hoặc 503 theo exception mapping; **điều bắt buộc** là không cấp quyền khi chưa xác minh đủ dữ liệu.

## 5. Từ đâu lấy dữ liệu user và role?

Các nguồn thường gặp:

| Nguồn | Dữ liệu dùng làm gì? | Điều cần kiểm soát |
| --- | --- | --- |
| **Introspection response đã kiểm tra active** | Subject, scope, client ID, audience, expiration | Trusted AS endpoint, client authentication, TLS |
| **User directory nội bộ** (R2DBC/LDAP service) | Display name, department, current roles | Authorization source, mapping theo subject/tenant, caching |
| **OIDC UserInfo endpoint** | Profile claims của user khi AS cho phép | Token audience/scopes, `sub` phải khớp, trusted HTTPS |
| **Authorization service nghiệp vụ** | Tenant role, object-level permission | Context tenant/resource, versioning/revocation, latency |
| **JWT access token introspected** | Claims theo token profile | Không tự trust payload chưa được xác minh |
| **HTTP `X-Role`, query `?role=ADMIN` từ client** | **Không được dùng** cấp quyền | Untrusted input |
| **Dữ liệu frontend localStorage** | **Không đáng tin** cho server authorization | User có thể tự sửa |

**Đặt khóa đúng:** `sub` thường chỉ duy nhất trong **một issuer/tenant cụ thể**. Với multi-issuer/multi-tenant SaaS, hãy dùng khóa tổng hợp như `issuerId + tenantId + sub`, không trộn `alice` của hai tenants. Tên hiển thị/email không phải identity key đáng tin để map role vì có thể đổi hoặc trùng.

### 5.1. Chỉ bổ sung dữ liệu, không ghi đè claims có ý nghĩa bảo mật

Nếu delegate trả:

```json
{
  "sub": "alice",
  "scope": ["reports.read"],
  "aud": ["reports-api"]
}
```

Custom decorator có thể thêm:

```json
{
  "display_name": "Alice Tran",
  "department": "finance"
}
```

Nhưng **không được** đổi `scope` sang `admin`, `aud` sang API khác, `sub` sang một user khác hoặc `active` sang true. Chỉ thêm metadata cần thiết; dữ liệu nhạy cảm của employee profile nên được tối thiểu hóa theo endpoint, không trả toàn bộ principal/token attributes ra browser.

### 5.2. Chỉ cấp roles nằm trong trust policy

Một cách mapping rõ ràng:

```text
Directory role "REPORT_READER" -> ROLE_REPORT_READER
Directory role "REPORT_ADMIN"  -> ROLE_REPORT_ADMIN
Introspection scope "admin"    -> SCOPE_admin
```

Với endpoint quản trị, nên cân nhắc yêu cầu **cả SCOPE_admin lẫn ROLE_REPORT_ADMIN**, không chỉ một trong hai. Như vậy role local không cho phép token chỉ được AS cấp `profile.read` đi vào chức năng admin. Dự án demo áp dụng **AND** cả hai điều kiện.

## 6. Cấu hình Spring Security WebFlux reactive

Khi chưa cần custom enrich, Spring Boot có thể cấu hình opaque token Resource Server bằng:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: reports-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Đây là cách cấu hình **delegate mặc định** cho app. Resource Server cần client credentials để gọi introspection endpoint; đó là credentials giữa Resource Server và AS, **không phải** password đăng nhập của end user.

Để bổ sung claims và roles, có thể tự định nghĩa `@Bean ReactiveOpaqueTokenIntrospector`:

```java
// Snippet trong @Configuration, xem bản đầy đủ mục 10.
@Bean
ReactiveOpaqueTokenIntrospector introspector(UserDirectory directory) {
    ReactiveOpaqueTokenIntrospector delegate =
        SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(introspectionUri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

    return new EnrichingOpaqueTokenIntrospector(
        delegate, directory, "reports-api");
}
```

Spring Security 6.5 khuyến nghị builder `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...)`. Constructor ba string cũ đã đánh dấu deprecated, và class `NimbusReactiveOpaqueTokenIntrospector` cũng deprecated; **không copy tutorial cũ một cách máy móc**.

DSL reactive:

```java
@Bean
SecurityWebFilterChain security(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(opaque ->
                opaque.introspector(introspector)))
        .build();
}
```

**Chú ý:** `ServerHttpSecurity` và `SecurityWebFilterChain` thuộc WebFlux; `HttpSecurity` và `SecurityFilterChain` là Servlet. Khi gọi `.opaqueToken(opaque -> opaque.introspector(custom))`, cấu hình này **ghi đè** auto-configured introspector cho security chain, vì vậy bạn phải chắc chắn delegate trong custom bean thật sự thực hiện introspection hoặc trust validation theo policy.

## 7. Một ví dụ Java 17 thuần về giữ scope và thêm role

Trước khi sử dụng Reactor/Spring, ta mô hình hóa nguyên tắc cộng authorities **mà không làm mất các quyền đã được xác thực**.

File `AuthorityMergeDemo.java`:

```java
import java.util.Set;
import java.util.TreeSet;

public final class AuthorityMergeDemo {

    static Set<String> merge(Set<String> introspectedScopes,
                             Set<String> trustedDirectoryRoles) {
        Set<String> authorities = new TreeSet<>();

        for (String scope : introspectedScopes) {
            authorities.add("SCOPE_" + scope);
        }
        for (String role : trustedDirectoryRoles) {
            authorities.add("ROLE_" + role);
        }
        return authorities;
    }

    public static void main(String[] args) {
        System.out.println(merge(
            Set.of("reports.read"), Set.of("REPORT_READER")));
        System.out.println(merge(
            Set.of("admin"), Set.of("REPORT_ADMIN")));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac AuthorityMergeDemo.java
java AuthorityMergeDemo
```

**Stdout chính xác** (TreeSet sắp xếp từ điển):

```text
[ROLE_REPORT_READER, SCOPE_reports.read]
[ROLE_REPORT_ADMIN, SCOPE_admin]
```

**Giới hạn:** Đây chỉ là mô hình set union; chương trình **không introspect token** và tự nó không đủ để xác thực người gọi. Trong WebFlux thật, các scopes đầu vào phải xuất phát từ **delegate introspection thành công**, roles từ **directory có thẩm quyền**, và cần checks audience/subject. Project tiếp theo thực hiện đúng các bước đó.

## 8. Thiết kế project runnable và chiến lược kiểm thử

Ta xây một API Spring Boot **3.5.16**, Java 17+, Spring Security 6.5.x. Đây là baseline học có version xác định; production mới nên chọn nhánh Boot/Security còn được hỗ trợ theo chính sách cập nhật của tổ chức.

### Các endpoint

| Endpoint | Điều kiện | Kết quả |
| --- | --- | --- |
| `GET /health` | Public | 200 `OK` |
| `GET /api/profile` | Token active, aud đúng, sub tồn tại trong directory | Trả sub/displayName/department |
| `GET /api/reports` | `SCOPE_reports.read` | 200 `reports OK`, hoặc 403 |
| `GET /api/admin` | **`SCOPE_admin` AND `ROLE_REPORT_ADMIN`** | 200 `admin OK`, hoặc 403 |
| Unknown path | Deny all | Thường 403 nếu authenticated |

Với mọi endpoint protected, token không active, sai audience, thiếu sub, user không tồn tại hoặc delegate báo lỗi sẽ **không được authentication**. Trạng thái HTTP cụ thể của lỗi phụ thuộc handler; các tests sử dụng OAuth2AuthenticationException cho negative cases để kiểm tra 401.

### Những gì tests chứng minh

- **Unit `StepVerifier`**: decorator vẫn gọi delegate trước, không nâng quyền khi chưa introspect, bảo toàn scope, thêm role đúng từ directory, kiểm tra audience và subject, không sửa principal gốc, xử lý lỗi và lazy subscription.
- **HTTP `WebTestClient`**: với Bearer header, Spring WebFlux security thật nhận principal đã enrich rồi áp scope/role, trả 200/401/403 theo policy.
- **Không chứng minh**: cấu hình client credentials và endpoint introspection thật đã hoạt động. HTTP suite dùng delegate giả, **không** tạo/mở một IdP. Muốn end-to-end production cần thêm mock introspection HTTP server hoặc IdP sandbox.

### Cấu trúc file

```text
reactive-opaque-enrichment/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── Application.java
    │   │   ├── UserDirectory.java
    │   │   ├── InMemoryUserDirectory.java
    │   │   ├── EnrichingOpaqueTokenIntrospector.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/demo/opaque/
        ├── DemoIntrospectionFixtures.java
        ├── EnrichingIntrospectorTests.java
        └── HttpOpaqueTokenTests.java
```

## 9. Maven và ứng dụng

### 9.1. pom.xml

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
    <artifactId>reactive-opaque-enrichment</artifactId>
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

`spring-boot-starter-webflux` chọn reactive stack; `spring-boot-starter-oauth2-resource-server` cung cấp opaque token Resource Server. Không cần OAuth2 Client starter nếu service **chỉ xác minh Bearer inbound** mà không tự xin token downstream.

### 9.2. src/main/resources/application.yml

```yaml
app:
  opaque:
    introspection-uri: https://id.example.test/oauth2/introspect
    client-id: reports-api-introspection
    client-secret: demo-secret-not-for-production
    audience: reports-api

server:
  port: 8080
```

**Quan trọng:** `id.example.test` và `demo-secret-not-for-production` là giá trị giả công khai. Chúng cho phép project khởi động và tests offline nhưng **không cho phép introspect token qua mạng**. Để chạy thật, thay URL, client authentication và secret bằng IdP sandbox/secret manager, HTTPS và contract audience đúng. Không lưu secret production trong YAML, source code hoặc image container.

### 9.3. src/main/java/demo/opaque/Application.java

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

## 10. Nguồn user/role và custom introspector

### 10.1. src/main/java/demo/opaque/UserDirectory.java

```java
package demo.opaque;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface UserDirectory {

    Mono<UserProfile> findBySubject(String subject);

    record UserProfile(
        String displayName,
        String department,
        Set<String> roles) {}
}
```

`UserDirectory` là abstraction cho database/R2DBC/LDAP gateway hoặc user-role service đáng tin. Method trả `Mono<UserProfile>`, không block. `UserProfile` dùng Java record (Java 17 có sẵn).

### 10.2. src/main/java/demo/opaque/InMemoryUserDirectory.java

```java
package demo.opaque;

import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class InMemoryUserDirectory implements UserDirectory {

    private static final Map<String, UserProfile> USERS = Map.of(
        "alice", new UserProfile(
            "Alice Tran", "finance", Set.of("REPORT_READER")),
        "bob", new UserProfile(
            "Bob Le", "sales", Set.of("REPORT_READER")),
        "admin", new UserProfile(
            "Admin Kim", "finance",
            Set.of("REPORT_READER", "REPORT_ADMIN"))
    );

    @Override
    public Mono<UserProfile> findBySubject(String subject) {
        return Mono.justOrEmpty(USERS.get(subject));
    }
}
```

Đây là danh bạ **demo**, không phải cơ chế phân quyền production. Quyền `REPORT_ADMIN` được xác định từ store do backend quản lý, không từ tham số do frontend cung cấp. Trong production cần tenant/issuer-aware subject keys, role lifecycle/revocation, audit và persistence phù hợp. Nếu dùng R2DBC, query theo subject đã được validate, không ghép SQL string thủ công.

### 10.3. src/main/java/demo/opaque/EnrichingOpaqueTokenIntrospector.java

```java
package demo.opaque;

import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class EnrichingOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final Set<String> PERMITTED_ROLES =
        Set.of("REPORT_READER", "REPORT_ADMIN");

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final UserDirectory directory;
    private final String expectedAudience;

    public EnrichingOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            UserDirectory directory,
            String expectedAudience) {
        this.delegate = delegate;
        this.directory = directory;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        // Delegate PHẢI xác nhận active/valid trước khi lấy quyền nội bộ.
        return delegate.introspect(token)
            .flatMap(this::enrichValidatedPrincipal);
    }

    private Mono<OAuth2AuthenticatedPrincipal> enrichValidatedPrincipal(
            OAuth2AuthenticatedPrincipal principal) {

        Object rawSubject = principal.getAttribute("sub");
        if (!(rawSubject instanceof String)) {
            return Mono.error(invalid("Missing string subject"));
        }
        String subject = (String) rawSubject;
        if (subject.isBlank()) {
            return Mono.error(invalid("Blank subject"));
        }

        Object audience = principal.getAttribute("aud");
        if (!audienceMatches(audience)) {
            return Mono.error(invalid("Token audience is not this API"));
        }

        return directory.findBySubject(subject)
            .switchIfEmpty(Mono.error(
                invalid("Subject is unknown to local directory")))
            .map(profile -> {
                Map<String, Object> attributes =
                    new LinkedHashMap<>(principal.getAttributes());

                // Chỉ THÊM các claims từ directory.
                // Không ghi đè sub, aud, scope, active, exp, client_id.
                attributes.put("display_name", profile.displayName());
                attributes.put("department", profile.department());

                Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(principal.getAuthorities());

                for (String role : profile.roles()) {
                    if (!PERMITTED_ROLES.contains(role)) {
                        throw new IllegalStateException(
                            "Directory contains an unexpected role");
                    }
                    authorities.add(new SimpleGrantedAuthority(
                        "ROLE_" + role));
                }

                return (OAuth2AuthenticatedPrincipal)
                    new DefaultOAuth2AuthenticatedPrincipal(
                        principal.getName(), attributes, authorities);
            });
    }

    private boolean audienceMatches(Object claim) {
        if (claim instanceof String) {
            return expectedAudience.equals(claim);
        }
        if (claim instanceof Collection<?>) {
            return ((Collection<?>) claim).contains(expectedAudience);
        }
        return false;
    }

    private static OAuth2AuthenticationException invalid(String reason) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", reason, null));
    }
}
```

**Vì sao từng chi tiết quan trọng?**

1. `delegate.introspect(token)` là bước xác thực token bởi AS hoặc delegate tin cậy. Nếu `active=false`, revoked hoặc introspection request lỗi, `flatMap` **không chạy**.
2. `sub` phải là `String` không rỗng; không dùng `principal.getName()` như fallback vô điều kiện nếu AS không đảm bảo identity key. Trong test, `sub` phải trùng directory.
3. `aud` phải chứa `reports-api`. Nhiều provider có `aud` dạng string hoặc list, nên helper hỗ trợ hai dạng; thiếu `aud` bị từ chối theo chính sách của API demo.
4. `directory.findBySubject(subject)` chạy **reactive**. `switchIfEmpty` từ chối subject không tồn tại; lỗi directory không bị nuốt để cấp quyền giả.
5. `new LinkedHashMap<>(principal.getAttributes())` giúp **copy**, không thay đổi attributes của delegate hay người dùng khác.
6. `new LinkedHashSet<>(principal.getAuthorities())` **giữ các SCOPE_ authorities**, đồng thời loại duplicates.
7. Roles chỉ được nhận từ directory và nằm trong `PERMITTED_ROLES`. Role không hợp lệ gây lỗi thay vì tự tạo `ROLE_...` bất kỳ.
8. `DefaultOAuth2AuthenticatedPrincipal(principal.getName(), attributes, authorities)` giữ principal identity gốc, thêm fields/roles đã kiểm soát.
9. Không cache JWT/opaque token trong class, không đưa raw token vào logs hay profile response.
10. Lỗi validation được biểu diễn bằng `OAuth2AuthenticationException` với mã `invalid_token`, giúp Spring Security từ chối Bearer authentication phù hợp.

**Ghi chú production:** Một subject từ AS khác hoặc tenant khác có thể trùng `alice`. Thay `findBySubject` bằng `findByIssuerTenantSubject` hoặc mapping tương đương đã xác minh trước khi triển khai nhiều issuers. Bổ sung account disabled, employee status, organization affiliation, token audience/client_id policy nếu nghiệp vụ yêu cầu.

## 11. Cấu hình SecurityWebFilterChain và API

### 11.1. src/main/java/demo/opaque/SecurityConfiguration.java

```java
package demo.opaque;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.opaque.introspection-uri}") String uri,
            @Value("${app.opaque.client-id}") String clientId,
            @Value("${app.opaque.client-secret}") String clientSecret,
            @Value("${app.opaque.audience}") String audience,
            UserDirectory directory) {

        ReactiveOpaqueTokenIntrospector delegate =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

        return new EnrichingOpaqueTokenIntrospector(
            delegate, directory, audience);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/profile").authenticated()
                .pathMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/admin")
                    .access((authentication, context) ->
                        authentication.map(auth -> {
                            boolean hasScope = auth.getAuthorities().stream()
                                .anyMatch(a -> a.getAuthority()
                                    .equals("SCOPE_admin"));
                            boolean hasRole = auth.getAuthorities().stream()
                                .anyMatch(a -> a.getAuthority()
                                    .equals("ROLE_REPORT_ADMIN"));
                            return new AuthorizationDecision(
                                hasScope && hasRole);
                        }))
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // API demo chỉ nhận Bearer chủ động, không dùng browser cookie.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

Điểm nổi bật:

- Chính `SpringReactiveOpaqueTokenIntrospector` gọi endpoint AS với client credentials.
- `EnrichingOpaqueTokenIntrospector` **wrap** delegate, không thay thế token validation bằng một directory lookup vô điều kiện.
- `.oauth2ResourceServer(...opaqueToken(...introspector(...)))` chỉ định rõ custom introspector cho WebFlux chain. Đừng nhầm với `.jwt()` của Resource Server JWT.
- `/api/reports` cần OAuth2 scope do AS cấp (authority `SCOPE_reports.read`).
- `/api/admin` cần **đồng thời** `SCOPE_admin` và `ROLE_REPORT_ADMIN`: có role local thôi không đủ nếu client chưa được AS cấp admin scope.
- Rule public health chỉ truy cập controller **khi request không chứa Bearer token lỗi**; request có Bearer sai đôi khi vẫn bị authentication filter từ chối ngay cả trên path public.
- `httpBasic` và `formLogin` tắt để API này không dùng user-password/browser redirect.
- `csrf.disable()` **chỉ đúng trong mô hình API stateless Bearer Authorization header chủ động**. Nếu chung app có session cookie, form hoặc Basic browser tự gửi, phải thiết kế CSRF riêng; không sao chép cấu hình này nguyên vẹn.

### 11.2. src/main/java/demo/opaque/ApiController.java

```java
package demo.opaque;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ProfileView(
        String sub,
        String displayName,
        String department) {}

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/profile")
    public Mono<ProfileView> profile(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new ProfileView(
            principal.getAttribute("sub"),
            principal.getAttribute("display_name"),
            principal.getAttribute("department")));
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }
}
```

Dữ liệu API profile chỉ chứa ba trường cần thiết. Nó **không xuất** toàn bộ attributes, access token, introspection response, client secret hoặc các quyền nội bộ không cần thiết. `@AuthenticationPrincipal` lấy principal từ **Spring Security authentication context**, không từ query/header không được tin cậy. Các tên field mới `display_name`/`department` do decorator tạo.

## 12. Test fixtures: delegate giả nhưng cùng contract

Project cố tình không phụ thuộc một AS thực trong tests. Class test fixture mô phỏng **kết quả delegate đã xác thực**, gồm token có scope/audience đúng hoặc không, và delegate báo inactive token. Việc mô phỏng này **không thay thế** test HTTP introspection request/response với AS.

### 12.1. src/test/java/demo/opaque/DemoIntrospectionFixtures.java

```java
package demo.opaque;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

final class DemoIntrospectionFixtures {

    private DemoIntrospectionFixtures() {}

    static OAuth2AuthenticatedPrincipal active(
            String sub, List<String> scopes, String audience) {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("sub", sub);
        attributes.put("scope", scopes);
        attributes.put("aud", List.of(audience));
        attributes.put("active", Boolean.TRUE);

        List<GrantedAuthority> authorities = new ArrayList<>();
        for (String scope : scopes) {
            authorities.add(new SimpleGrantedAuthority("SCOPE_" + scope));
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            sub, attributes, authorities);
    }

    static OAuth2AuthenticationException invalid(String detail) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token", detail, null));
    }

    static ReactiveOpaqueTokenIntrospector delegate() {
        return token -> Mono.defer(() -> {
            return switch (token) {
                case "alice-read" -> Mono.just(
                    active("alice", List.of("reports.read"), "reports-api"));
                case "alice-noscope" -> Mono.just(
                    active("alice", List.of(), "reports-api"));
                case "alice-admin-scope" -> Mono.just(
                    active("alice", List.of("admin"), "reports-api"));
                case "bob-profile" -> Mono.just(
                    active("bob", List.of("profile.read"), "reports-api"));
                case "admin-full" -> Mono.just(
                    active("admin", List.of("reports.read", "admin"),
                        "reports-api"));
                case "admin-profile-only" -> Mono.just(
                    active("admin", List.of("profile.read"), "reports-api"));
                case "wrong-audience" -> Mono.just(
                    active("alice", List.of("reports.read"), "payments-api"));
                case "unknown-user" -> Mono.just(
                    active("unknown", List.of("reports.read"), "reports-api"));
                case "missing-sub" -> Mono.just(
                    new DefaultOAuth2AuthenticatedPrincipal(
                        "anonymous-sub",
                        Map.of("aud", List.of("reports-api"),
                            "active", Boolean.TRUE),
                        List.of()));
                default -> Mono.error(invalid(
                    "Token is inactive or absent"));
            };
        });
    }
}
```

Lưu ý: `"alice-read"`, `"admin-full"` chỉ là **tên token test** do fake delegate hiểu. Với ứng dụng thật, opaque token là bí mật ngẫu nhiên do AS cấp; **không** tạo production introspector bằng `switch(token)` như trên. Lỗi từ fake delegate mô phỏng token invalid để test deny behavior, không thay việc kiểm tra `active=false` thực tế của `SpringReactiveOpaqueTokenIntrospector`.

## 13. Unit tests: enrichment đúng, không nâng quyền

### 13.1. src/test/java/demo/opaque/EnrichingIntrospectorTests.java

```java
package demo.opaque;

import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EnrichingIntrospectorTests {

    private final UserDirectory directory =
        new InMemoryUserDirectory();

    private ReactiveOpaqueTokenIntrospector subject() {
        return new EnrichingOpaqueTokenIntrospector(
            DemoIntrospectionFixtures.delegate(),
            directory, "reports-api");
    }

    private static Set<String> authorities(
            OAuth2AuthenticatedPrincipal principal) {
        return principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void activeAliceGetsDisplayNameAndDepartment() {
        StepVerifier.create(subject().introspect("alice-read"))
            .assertNext(principal -> {
                assertEquals("alice", principal.getName());
                assertEquals("Alice Tran",
                    principal.getAttribute("display_name"));
                assertEquals("finance",
                    principal.getAttribute("department"));
            })
            .verifyComplete();
    }

    @Test
    void scopeAuthorityIsPreservedWhenRoleIsAdded() {
        StepVerifier.create(subject().introspect("alice-read"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_reports.read"));
                assertTrue(granted.contains("ROLE_REPORT_READER"));
                assertFalse(granted.contains("ROLE_REPORT_ADMIN"));
            })
            .verifyComplete();
    }

    @Test
    void trustedAdminGetsDirectoryRoleAndOriginalScopes() {
        StepVerifier.create(subject().introspect("admin-full"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_admin"));
                assertTrue(granted.contains("SCOPE_reports.read"));
                assertTrue(granted.contains("ROLE_REPORT_ADMIN"));
                assertEquals("Admin Kim",
                    principal.getAttribute("display_name"));
            })
            .verifyComplete();
    }

    @Test
    void havingAdminScopeDoesNotInventAdminDirectoryRole() {
        StepVerifier.create(subject().introspect("alice-admin-scope"))
            .assertNext(principal -> {
                Set<String> granted = authorities(principal);
                assertTrue(granted.contains("SCOPE_admin"));
                assertFalse(granted.contains("ROLE_REPORT_ADMIN"));
            })
            .verifyComplete();
    }

    @Test
    void inactiveTokenNeverCallsUserDirectory() {
        AtomicBoolean called = new AtomicBoolean();
        UserDirectory spy = sub -> {
            called.set(true);
            return Mono.empty();
        };

        ReactiveOpaqueTokenIntrospector subject =
            new EnrichingOpaqueTokenIntrospector(
                token -> Mono.error(
                    DemoIntrospectionFixtures.invalid("inactive")),
                spy, "reports-api");

        StepVerifier.create(subject.introspect("invalid"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
        assertFalse(called.get());
    }

    @Test
    void wrongAudienceIsRejectedBeforeDirectoryLookup() {
        StepVerifier.create(subject().introspect("wrong-audience"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void missingSubjectIsRejected() {
        StepVerifier.create(subject().introspect("missing-sub"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void unknownDirectorySubjectFailsClosed() {
        StepVerifier.create(subject().introspect("unknown-user"))
            .expectError(OAuth2AuthenticationException.class)
            .verify();
    }

    @Test
    void delegateAttributesAreNotMutated() {
        OAuth2AuthenticatedPrincipal original =
            DemoIntrospectionFixtures.active(
                "alice", List.of("reports.read"), "reports-api");

        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                token -> Mono.just(original),
                directory, "reports-api");

        StepVerifier.create(decorated.introspect("opaque"))
            .assertNext(enriched -> {
                assertTrue(enriched.getAttributes()
                    .containsKey("display_name"));
                assertFalse(original.getAttributes()
                    .containsKey("display_name"));
                assertTrue(authorities(original)
                    .contains("SCOPE_reports.read"));
                assertFalse(authorities(original)
                    .contains("ROLE_REPORT_READER"));
            })
            .verifyComplete();
    }

    @Test
    void directoryFailurePropagatesWithoutGrantingRights() {
        UserDirectory failed = sub ->
            Mono.error(new IllegalStateException(
                "Directory is unavailable"));
        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                DemoIntrospectionFixtures.delegate(),
                failed, "reports-api");

        StepVerifier.create(decorated.introspect("alice-read"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void delegateIsSubscribedOnlyWhenPipelineIsSubscribed() {
        AtomicInteger subscriptions = new AtomicInteger();
        ReactiveOpaqueTokenIntrospector lazyDelegate = token ->
            Mono.defer(() -> {
                subscriptions.incrementAndGet();
                return Mono.just(
                    DemoIntrospectionFixtures.active(
                        "alice", List.of("reports.read"),
                        "reports-api"));
            });
        ReactiveOpaqueTokenIntrospector decorated =
            new EnrichingOpaqueTokenIntrospector(
                lazyDelegate, directory, "reports-api");

        Mono<OAuth2AuthenticatedPrincipal> pipeline =
            decorated.introspect("alice-read");
        assertEquals(0, subscriptions.get());

        StepVerifier.create(pipeline)
            .expectNextCount(1)
            .verifyComplete();
        assertEquals(1, subscriptions.get());
    }
}
```

Có **11 unit tests**, chạy bằng JUnit 5 + Reactor `StepVerifier` mà không cần Spring ApplicationContext. Các bài này chứng minh:

- Chỉ sau delegate thành công mới lấy quyền nội bộ.
- User Alice được thêm display name/department và `ROLE_REPORT_READER`.
- `SCOPE_reports.read` vẫn còn nguyên; role `REPORT_ADMIN` không được tạo cho Alice.
- Chỉ có scope `admin` không tạo được `ROLE_REPORT_ADMIN` nếu directory không cấp role.
- Token sai audience, thiếu subject, subject lạ và directory error đều không thể lấy principal được phép.
- Original principal và authorities **không bị mutate**.
- Publisher lazy: chưa subscribe thì delegate lazy chưa thực thi, giúp tránh side effects nằm ngoài reactive pipeline.

## 14. HTTP tests: Bearer authentication qua WebFlux thật

Bộ test HTTP dùng Spring ApplicationContext, WebTestClient và **custom `ReactiveOpaqueTokenIntrospector` được @Primary trong test**. Điều đó giúp request có `Authorization: Bearer alice-read` đi qua **Spring Security Bearer filter + custom decorator + authorization policies**, không cần gọi AS. Khác với `mockOpaqueToken()`, tests này thực sự chạy mã introspector do chúng ta viết (nhưng delegate là fake).

### 14.1. src/test/java/demo/opaque/HttpOpaqueTokenTests.java

```java
package demo.opaque;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(HttpOpaqueTokenTests.TestIntrospectionConfiguration.class)
class HttpOpaqueTokenTests {

    @TestConfiguration
    static class TestIntrospectionConfiguration {

        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector fakeForHttpTests(
                UserDirectory directory) {
            return new EnrichingOpaqueTokenIntrospector(
                DemoIntrospectionFixtures.delegate(),
                directory, "reports-api");
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec get(
            String path, String bearerToken) {
        return client.get().uri(path)
            .headers(headers -> {
                if (bearerToken != null) {
                    headers.setBearerAuth(bearerToken);
                }
            })
            .exchange();
    }

    @Test
    void healthIsPublic() {
        get("/health", null)
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void profileWithoutTokenIs401() {
        get("/api/profile", null)
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void invalidOpaqueTokenIs401() {
        get("/api/profile", "inactive")
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIs401UnderFailClosedPolicy() {
        get("/api/profile", "unknown-user")
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingSubIs401() {
        get("/api/profile", "missing-sub")
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        get("/api/profile", "wrong-audience")
            .expectStatus().isUnauthorized();
    }

    @Test
    void aliceProfileIncludesTrustedDirectoryData() {
        get("/api/profile", "alice-read")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("alice")
            .jsonPath("$.displayName").isEqualTo("Alice Tran")
            .jsonPath("$.department").isEqualTo("finance");
    }

    @Test
    void bobProfileIsIsolatedFromAlice() {
        get("/api/profile", "bob-profile")
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("bob")
            .jsonPath("$.displayName").isEqualTo("Bob Le")
            .jsonPath("$.department").isEqualTo("sales");
    }

    @Test
    void reportsReadScopeAllowsReports() {
        get("/api/reports", "alice-read")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void localRoleCannotReplaceMissingScope() {
        get("/api/reports", "alice-noscope")
            .expectStatus().isForbidden();
    }

    @Test
    void profileReadScopeCannotReadReports() {
        get("/api/reports", "bob-profile")
            .expectStatus().isForbidden();
    }

    @Test
    void onlyAdminScopeButNotAdminDirectoryRoleIs403() {
        get("/api/admin", "alice-admin-scope")
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleWithoutAdminScopeIs403() {
        get("/api/admin", "admin-profile-only")
            .expectStatus().isForbidden();
    }

    @Test
    void bothAdminScopeAndAdminDirectoryRoleAllowAccess() {
        get("/api/admin", "admin-full")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void httpBasicDoesNotReplaceOpaqueBearer() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedEvenWithValidToken() {
        get("/api/private", "admin-full")
            .expectStatus().isForbidden();
    }
}
```

Có **16 HTTP tests**:

- Không bearer, invalid token, unknown user, missing sub, wrong audience đều bị từ chối.
- Alice/Bob có profile dữ liệu **tách biệt**, không thấy user data của nhau.
- `SCOPE_reports.read` điều khiển quyền đọc báo cáo, không thể bị thay bằng role local.
- Admin phải có **cả** `SCOPE_admin` và `ROLE_REPORT_ADMIN`.
- Basic không thay thế Bearer; unknown route vẫn bị `denyAll`.

**Tổng suite: 27 tests** = 11 unit `StepVerifier` + 16 WebTestClient. Đây là số phương thức `@Test` trong hai file test, không phải tuyên bố rằng Maven đã thực thi trong môi trường biên soạn.

### 14.2. Tại sao không chỉ dùng mockOpaqueToken()?

Spring Security cung cấp `SecurityMockServerConfigurers.mockOpaqueToken()`, thích hợp kiểm thử security authorization/controller bằng một principal giả. Nhưng nó **có thể bypass** introspector, vì vậy không đủ để chứng minh `EnrichingOpaqueTokenIntrospector` đã gọi delegate hoặc xử lý missing sub/audience. Bộ test ở đây tạo **fake delegate** nhưng vẫn chạy custom decorator, cho phạm vi kiểm thử tốt hơn về enrichment.

Các tests này **vẫn không chứng minh** AS trả `active=false` đã được HTTP client xử lý, TLS và Basic authentication của introspection endpoint đúng, hoặc hoạt động khi AS timeout. Đó là nhiệm vụ của integration tests riêng với AS sandbox hoặc fake introspection HTTP server.

## 15. Chạy Maven và thực hành curl

Yêu cầu JDK 17+, Maven phù hợp và mã đặt đúng thư mục/package.

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

**Kỳ vọng** khi bộ ví dụ và dependencies tương thích: Maven Surefire chạy **27 tests** với `BUILD SUCCESS`. Đây là kết quả mong đợi theo mã, **không phải khẳng định đã thực thi Maven**. Nếu gặp lỗi, xem `target/surefire-reports` và sửa đúng phiên bản/API thay vì bỏ test.

Sau khi khởi động:

```bash
curl -i http://localhost:8080/health
```

Dự kiến `HTTP 200`, body `OK`.

```bash
curl -i http://localhost:8080/api/profile
```

Dự kiến HTTP **401** vì thiếu Bearer.

Thử một chuỗi không được IdP thật cấp:

```bash
curl -i -H "Authorization: Bearer anything" \
  http://localhost:8080/api/profile
```

Vì URL `id.example.test` là giả, introspection không thể xác minh token. Request **không được** cho vào API thành công; status chi tiết tùy failure handling khi AS không thể kết nối, có thể khác 401 chuẩn của token invalid.

Để thực hành có auth thành công qua HTTP thật:

1. Triển khai/cấu hình AS sandbox có introspection endpoint HTTPS và client credentials riêng cho Resource Server.
2. Đảm bảo AS cấp opaque access token và introspection trả `active=true`, `sub`, `aud` (hoặc claims tương đương theo contract), `scope`.
3. Thay `app.opaque.introspection-uri`/client-id/client-secret/audience bằng nguồn tin cậy; không commit secret production.
4. Dùng token do AS thật cấp để gọi `/api/profile`, `/api/reports`, `/api/admin`.
5. Ghi nhận status 200/401/403; thử revoked token, scope thiếu, audience sai và user không tồn tại trong directory.
6. Kiểm thử thay đổi local role của user đang có token để xác nhận policy refresh/caching dự kiến.
7. Nếu tổ chức dùng nhiều tenants/issuers, áp directory key composite đúng trước khi phát hành hệ thống.

### 15.1. Một request không làm thay đổi token trên AS

Enrichment làm thay đổi **principal trong Resource Server request**, không ghi ngược claims vào token hay thay đổi scope/role đã được cấp trên AS. Access token không tự có thêm `admin` chỉ vì directory user là admin. Muốn thay đổi scope/token issuance phải thay chính sách đăng ký/consent/grant ở AS và cấp token mới theo flow thích hợp.

## 16. Tùy chọn bổ sung qua UserInfo API và những cạm bẫy

Có thể thay local directory bằng một **trusted UserInfo endpoint** khi contract và scopes cho phép. Nguyên tắc vẫn là:

```text
AS introspection active=true
   |
   +--> xác minh sub/audience/client binding
   |
   +--> gọi trusted UserInfo với access token thích hợp
   |
   +--> KIỂM TRA UserInfo.sub == introspection.sub
   |
   +--> chỉ bổ sung profile fields (name/email/...)
   |
   +--> roles chỉ từ nguồn có thẩm quyền cho authorization
```

Đoạn **minh họa, không phải file runnable độc lập** trong class có `WebClient userInfoClient` tin cậy:

```java
return delegate.introspect(token)
    .flatMap(principal ->
        userInfoClient.get()
            .uri("/userinfo")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .bodyToMono(UserInfo.class)
            .filter(info ->
                info.sub().equals(principal.getAttribute("sub")))
            .switchIfEmpty(Mono.error(
                new IllegalStateException("UserInfo sub mismatch")))
            .map(info -> addSafeProfileFields(principal, info)));
```

`UserInfo` và `addSafeProfileFields` là types/methods **minh họa**, chưa định nghĩa trong project. Cần token audience/scopes phù hợp UserInfo, secure WebClient base URL, timeout, TLS, errors và response validation. **Không dùng một arbitrary user-profile HTTP URL** do requester đưa để lấy roles rồi tạo `ROLE_ADMIN`.

Nếu chỉ cần display name cho trang profile, cân nhắc truy vấn sau authentication ở service phù hợp thay vì mỗi API request đều phát sinh UserInfo call. Nếu cần roles cho authorization, đặt việc tra cứu trước khi quyết định truy cập, hoặc dùng một `ReactiveAuthorizationManager` domain-specific có trust/latency contract rõ ràng.

### 16.1. Có nên tin claim roles từ introspection?

Nếu AS là **nguồn thẩm quyền về roles**, bạn có thể map từ introspection response sang authorities, không cần directory riêng. Nhưng cần xác minh claim format, namespace, tenant, client ID, issuer contract và role allowlist. Nếu AS chỉ cung cấp scope, còn local ERP quản lý roles mới nhất, hãy để directory quyết định role. **Không tự hợp nhất role từ hai nguồn với quy tắc OR mở rộng quyền** khi chưa rõ bên nào có thẩm quyền cho từng hành động.

### 16.2. Có nên dùng method security thay cho mapping ở introspector?

Nếu quyền được kiểm tra **theo resource object**, ví dụ “Alice có được xem báo cáo #381 của phòng ban finance?”, mapping `ROLE_REPORT_READER` chỉ là bước đầu. Cần thêm business authorization trong service hoặc `ReactiveAuthorizationManager`/method security, dựa trên resource/tenant của database. Không nhồi mọi quyền trên hàng triệu objects vào token principal; nên giữ principal nhỏ, ổn định và kiểm tra ownership khi truy cập.

## 17. Vận hành và bảo mật introspection + enrichment

### 17.1. Latency và availability

Với opaque token mặc định, **mỗi request** có thể cần một cuộc gọi AS introspection. Thêm UserDirectory nữa nghĩa là có thể có **hai I/O calls** trước controller. Điều đó ảnh hưởng:

- End-to-end p95/p99 latency.
- Thời gian phản hồi khi AS/directory chậm.
- Kết nối HTTP/pool timeout, retry và backpressure.
- Load lên AS/directory khi traffic tăng.
- Hành vi khi partial failure.

Thiết kế asynchronous, giới hạn timeout và retry có kiểm soát. Không retry vô hạn `invalid_token`, 401/403 hoặc lỗi nghiệp vụ; retry 5xx/timeouts với backoff và budget phù hợp. Nếu directory outage và local roles bắt buộc, **không cho phép admin** theo fallback.

### 17.2. Cache, revoke và freshness của roles

Caching introspection hoặc enriched principal có thể giảm latency nhưng làm chậm hiệu lực token revocation/role removal. Cần:

- Cache key không đoán được; không đưa raw token vào logs, metrics hoặc analytics.
- TTL không vượt quá `exp` của token và policy revocation/role freshness; đôi khi cần TTL ngắn hơn rất nhiều.
- Không dùng cache key chỉ theo `sub` nếu cùng user có nhiều access tokens với scopes/audiences khác nhau.
- Multi-tenant cache isolation và version/invalidation khi đổi role.
- Không cache `active=true` vô hạn; cân nhắc fail-closed khi AS không sẵn sàng.
- Tách cache của introspection result và directory roles nếu có semantics khác.

Không coi JWT (nếu introspection một JWT access token) là tự có “revoke realtime”: mỗi system có cache/distribution delay riêng.

### 17.3. User identity, tenant và dữ liệu nhạy cảm

Đừng map `sub` của issuer A sang hồ sơ của issuer B. Email/username có thể đổi và không phải tenant-aware identity key. Với API multi-tenant, xây key `issuer + tenant + sub` và thực thi row-level ownership. Đưa display name/department vào principal chỉ nếu cần; **không tự động serialize toàn bộ principal vào JSON**.

Audit có thể ghi subject/tenant ID đã được ẩn danh hợp lý, outcome, scope/role *tên quyền*, correlation ID và nguyên nhân chung, **không ghi Bearer token, client_secret, introspection Basic auth hoặc raw profile PII**.

### 17.4. Active check không được thay bằng local lookup

Một user có trong directory không chứng minh một Bearer token của họ còn hiệu lực. Revoked token, sai client, sai audience hoặc thiếu scope vẫn phải bị từ chối. Mọi luồng phải giữ thứ tự delegate trước. Khi token `active=false`, AS có thể trả rất ít metadata, không nên cố extract subject từ token random rồi tìm directory để “cứu” request.

### 17.5. Error mapping

- **Missing Bearer:** thường HTTP 401 với `WWW-Authenticate: Bearer`.
- **Introspection báo inactive/invalid:** Authentication thất bại, thường HTTP 401.
- **Token active nhưng thiếu `SCOPE_reports.read`:** đã authenticate, authorization fail, thường HTTP 403.
- **Token active nhưng admin thiếu role local hoặc admin scope:** HTTP 403.
- **Directory/AS timeout hoặc backend outage:** không cho truy cập; trả 5xx/503 hay error đã chuẩn hóa theo architecture/exception translation, không khẳng định mọi failure đều là 401.
- **Browser báo CORS:** kiểm tra CORS headers trên cả response 401/403/5xx, đó là một lớp khác.

Trong Spring Security, có thể tùy biến `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` và error mapping; luôn giữ nội dung lỗi không rò credentials/PII.

## 18. Những lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Custom introspector trả principal từ database mà không gọi delegate | Authentication bypass/revoked token vẫn dùng được | Delegate introspection trước, chỉ enrich sau khi active |
| Lấy `X-Role` hoặc `?role=ADMIN` để add ROLE_ADMIN | Privilege escalation | Role chỉ từ AS/directory đã tin cậy |
| `.map(principal -> directory.findBySubject(...))` | Tạo `Mono<Mono<...>>`, không lấy user | Dùng `flatMap` khi gọi nguồn async |
| `.block()` trong introspector | Chặn Netty event-loop | Compose `Mono`, non-blocking repository |
| `.subscribe()` rồi trả principal ngay | Race, lỗi bị mất, quyền chưa xác định | Trả một publisher kết hợp toàn chuỗi |
| Thay `principal.getAuthorities()` bằng chỉ local roles | Mất `SCOPE_...` từ AS | Copy authorities gốc trước khi add |
| Cast scope trực tiếp thành String | Sai type tùy converter | Giữ authorities delegate hoặc normalize type |
| Ghi đè `sub`, `aud`, `exp`, `scope` | Thay đổi identity/trust constraints | Chỉ thêm metadata mới, không đổi claims gốc |
| User không có directory record nhưng mặc định REPORT_READER | Cấp quyền sai | Fail-closed hoặc policy only-scopes có chủ đích |
| Dùng `sub` không có issuer/tenant | Trộn users từ nhiều issuers | Composite identity key theo trust registry |
| Dùng displayName/email làm user key | Đổi tên, trùng email, takeover | Dùng stable subject ID đã validate |
| Chỉ check active, bỏ qua aud/client binding | Accept token cho API khác | Validate audience theo contract AS |
| Tin directory error rồi fallback admin | Privilege escalation | Deny và báo lỗi hạ tầng |
| Dùng `NimbusReactiveOpaqueTokenIntrospector` API cũ | Deprecated và khó bảo trì | `SpringReactiveOpaqueTokenIntrospector` builder |
| Dùng Servlet `OpaqueTokenIntrospector` trong WebFlux | Sai stack | ReactiveOpaqueTokenIntrospector |
| Bật `.jwt()` trong khi muốn AS introspection | Không kiểm tra revoke như yêu cầu | Dùng `.opaqueToken(...)` |
| Dùng `mockOpaqueToken()` rồi nói đã test decorator | Test bypass introspector | Unit decorator + WebTestClient với fake delegate |
| Dùng role local thay admin scope | Bypass consent/scope | Check cả `SCOPE_admin` và `ROLE_REPORT_ADMIN` |
| Cache theo subject cho mọi token | Scope/audience/token mix-up | Cache per-token/policy, TTL ngắn, tenant isolation |
| Raw opaque token in log | Credential leak | Redact Authorization/secret/token |
| WebClient UserInfo dùng URL từ request | SSRF, token exfiltration | Chỉ trusted endpoint fixed base URI |
| Không verify UserInfo.sub | Gộp profile user khác | So với introspection-sub đã trusted |
| Timeout AS nhưng trả principal cũ vô hạn | Revoked token có thể được sử dụng | Fail-closed hoặc policy cache TTL giới hạn |
| Enriched principal có quá nhiều PII | Privacy breach | Chỉ attributes cần dùng |

## 19. Bài tập tự kiểm tra

**Câu 1.** `ReactiveOpaqueTokenIntrospector.introspect` trả gì?  
**Đáp án:** `Mono<OAuth2AuthenticatedPrincipal>` cho token đã được xác minh hợp lệ; báo error nếu token invalid theo contract.

**Câu 2.** Vì sao phải gọi delegate trước khi lấy roles?  
**Đáp án:** Danh bạ biết user không chứng minh token còn active. Delegation bảo đảm AS đã xác minh token rồi mới cấp local roles.

**Câu 3.** Một token active của Alice có `scope=reports.read`. Danh bạ thêm `ROLE_REPORT_READER`. API `hasAuthority("SCOPE_reports.read")` còn hoạt động không?  
**Đáp án:** Có nếu custom principal **giữ nguyên authorities** của delegate.

**Câu 4.** `SCOPE_admin` có giống `ROLE_REPORT_ADMIN` không?  
**Đáp án:** Không. Một cái do AS cấp theo OAuth2 scope, một cái từ trusted directory; endpoint nhạy cảm có thể yêu cầu cả hai.

**Câu 5.** Kết quả introspection không có sub nhưng có `active=true`; API phải xử lý sao?  
**Đáp án:** Nếu API cần xác định user để map role/identity, từ chối token và yêu cầu AS cung cấp stable subject theo contract; không đoán subject từ email hoặc header.

**Câu 6.** `active=false` và directory có Alice với ROLE_REPORT_ADMIN; có được authenticate không?  
**Đáp án:** Không. Delegate từ chối token trước, không chạy enrichment.

**Câu 7.** Vì sao sử dụng `flatMap` thay vì `map` khi gọi R2DBC directory?  
**Đáp án:** Vì directory trả `Mono<UserProfile>`; flatMap ghép publisher, không tạo nested Mono và giữ lỗi/cancellation.

**Câu 8.** Tại sao phải kiểm tra audience dù introspection active?  
**Đáp án:** Token có thể active nhưng dành cho Resource Server khác; audience check ngăn token substitution.

**Câu 9.** Vai trò của `DefaultOAuth2AuthenticatedPrincipal`?  
**Đáp án:** Đóng gói principal name, attributes và authorities mới một cách nhất quán sau enrichment.

**Câu 10.** `mockOpaqueToken()` kiểm tra actual introspection HTTP và `active=false` không?  
**Đáp án:** Không. Nó tạo mock Authentication; để test decorator phải gọi custom class hoặc cài fake delegate vào WebFlux chain.

**Câu 11.** Directory outage có cho phép dùng quyền cached vô hạn không?  
**Đáp án:** Không. Phải có TTL/role revocation/failure policy; với policy fail-closed của project, không cấp role khi directory không sẵn sàng.

**Câu 12.** `client_credentials` của introspection là thông tin gì?  
**Đáp án:** Credentials của Resource Server được AS cho phép gọi introspection endpoint, khác với access token của end user và khác login password.

**Câu 13.** Vì sao phải giữ `sub` và `scope` gốc?  
**Đáp án:** Chúng là dữ liệu identity/authorization từ trusted AS; ghi đè từ directory có thể thay đổi danh tính/quyền không hợp lệ.

**Câu 14.** Chỉ có role local REPORT_ADMIN nhưng token không có admin scope, endpoint demo `/api/admin` ra sao?  
**Đáp án:** 403. Policy yêu cầu **AND** `SCOPE_admin` + `ROLE_REPORT_ADMIN`.

**Câu 15.** Dùng `ReactiveJwtDecoder` để parse opaque token được không?  
**Đáp án:** Không đúng yêu cầu introspection. Opaque token không bảo đảm format JWT và có thể cần AS để biết trạng thái active/revoked.

**Câu 16.** Tại sao không cache theo key `sub` duy nhất?  
**Đáp án:** Cùng subject có nhiều tokens với scope/audience/client/expiration khác nhau; cache theo subject có thể trộn quyền.

**Câu 17.** Nếu user profile có thông tin nhạy cảm, có nên cho `/api/profile` trả toàn bộ attributes?  
**Đáp án:** Không. Chỉ trả những trường được phép, hạn chế PII và kiểm tra consent/privacy.

**Câu 18.** Trong multi-issuer system, `sub=alice` có luôn là cùng một người không?  
**Đáp án:** Không. Dùng issuer/tenant-qualified subject key và registry tin cậy.

## 20. Checklist triển khai

- [ ] Chỉ dùng `ReactiveOpaqueTokenIntrospector` trong Spring WebFlux, không dùng Servlet introspector.
- [ ] Delegate thực hiện introspection với AS đáng tin và kiểm tra `active=true`.
- [ ] Client introspection credentials, TLS và AS endpoint nằm trong secure configuration.
- [ ] Không cấp quyền trước khi delegate thành công.
- [ ] Kiểm tra identity `sub` và audience/client-binding phù hợp business API.
- [ ] Nguồn roles là backend trusted directory hoặc trusted AS claims, không phải frontend-provided data.
- [ ] Giữ scopes/authorities gốc khi thêm roles; không ghi đè claims chuẩn.
- [ ] Chỉ add role names trong policy/allowlist; test không có privilege escalation.
- [ ] Mọi I/O trong enrichment dùng `Mono.flatMap`, không `.block()`/`.subscribe()` tùy tiện.
- [ ] Xử lý empty/directory error bằng fail-closed hoặc policy đã được duyệt.
- [ ] Kiểm tra admin bằng scopes của AS **và** roles local nếu threat model yêu cầu.
- [ ] Có tests active/inactive, missing-sub/audience, unknown subject và role/scope differentiation.
- [ ] Có API tests Bearer 200/401/403 và HTTP mock introspection integration trước production.
- [ ] Không tự giả định `mockOpaqueToken()` test đã chạy decorator.
- [ ] Secrets/token/PII không xuất hiện trong logs, errors hay serialized principal.
- [ ] TTL/cache không làm vô hiệu việc revoke token/role nhanh theo policy.
- [ ] Tenant/issuer-aware subject identity, resource ownership checks và least privilege.
- [ ] Timeout, retries/backoff, rate limits, observability và fallback được thiết kế theo fail-closed.
- [ ] Môi trường production dùng version Spring Boot/Security còn được hỗ trợ.

## 21. Tóm tắt và tài liệu chính thức

**Mô hình cần nhớ:**

```text
Resource Server opaque Bearer
  -> SpringReactiveOpaqueTokenIntrospector(delegate)
      -> AS introspection active=true
  -> validate sub/aud constraints
  -> trusted UserDirectory (reactive)
  -> DefaultOAuth2AuthenticatedPrincipal
      attrs = original + safe display metadata
      authorities = original scopes + trusted local roles
  -> AuthorizationWebFilter checks scopes AND/OR roles by endpoint policy
  -> HTTP 401 invalid token, HTTP 403 insufficient authority, HTTP 200 allowed
```

**Đúc kết:** Custom introspector là một lớp **bổ sung identity/authorization data sau khi xác thực token**, không phải cách tạo token, không thay OAuth2 Authorization Server và không được tạo quyền từ dữ liệu chưa tin cậy. Với WebFlux, mọi bước phải nằm trong cùng reactive chain để request chỉ được xác thực khi delegate, constraints và directory lookup đã hoàn thành đúng.

**Tài liệu tham khảo:**

- Spring Security 6.5 – Reactive OAuth2 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 – ReactiveOAuth2 introspection API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 – SpringReactiveOpaqueTokenIntrospector API/builder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 – DefaultOAuth2AuthenticatedPrincipal: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
- Spring Security – Reactive OAuth2 tests, mockOpaqueToken: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- IETF RFC 7662 – OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- IETF RFC 6749 – OAuth2 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
