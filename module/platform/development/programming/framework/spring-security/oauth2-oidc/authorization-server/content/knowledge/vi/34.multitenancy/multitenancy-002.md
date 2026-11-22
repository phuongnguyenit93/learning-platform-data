# Cấu hình và phân giải issuer theo khả năng hỗ trợ đa tenant

> **Chương: Đa tenant.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Trọng tâm là mô hình nhiều tenant dùng chung một host nhưng có **issuer riêng**, cách Spring Authorization Server phân giải issuer từ request, cách định tuyến component theo tenant và cách bảo đảm dữ liệu, signing key, client registration và authorization không bị dùng chéo.

## 1. Issuer là ranh giới danh tính của Authorization Server

Issuer Identifier là định danh của Authorization Server/OpenID Provider. Với OIDC, claim `iss` trong ID Token phải xác định OP đã phát hành token; với OAuth 2.0, metadata công bố issuer và các protocol endpoints tương ứng.

Trong hệ thống một tenant, issuer thường cố định:

~~~text
https://login.example.vn
~~~

Khi phục vụ nhiều tenant, tổ chức có thể cần issuer độc lập cho từng tenant:

| Tenant | Issuer | Client ID có thể trùng? |
|---|---|---|
| Công ty A | `https://auth.example.vn/acme` | Có, nếu registration được cô lập |
| Công ty B | `https://auth.example.vn/contoso` | Có, nếu registration được cô lập |
| Đối tác C | `https://auth.example.vn/partner-c` | Có, nếu registration được cô lập |

Issuer không chỉ là URL hiển thị. Nó được dùng trong discovery metadata, ID Token, access token theo cấu hình, validation của Resource Server và trust relationship của client. Chọn tenant sai có thể khiến client nhận token từ sai miền tin cậy hoặc khiến một tenant truy cập client, authorization, consent hay signing key của tenant khác.

**Nguyên tắc:** tenant phải được phân giải từ một định danh đã được hệ thống kiểm soát, rồi dùng cùng định danh đó để chọn issuer, dữ liệu, khóa ký và policy. Không chọn tenant bằng cách tin một trường tenant tùy ý trong request body.

## 2. Ba mô hình multi-tenancy thường gặp

Không phải mọi ứng dụng đa tenant đều cần nhiều issuer. Hãy chọn mô hình theo ranh giới bảo mật và contract mà client cần.

| Mô hình | Issuer | Cách tách tenant | Phù hợp khi |
|---|---|---|---|
| Dedicated deployment/domain | Một issuer riêng cho mỗi deployment/host | Hạ tầng và dữ liệu tách riêng | Tenant lớn, yêu cầu isolation cao hoặc cấu hình khác biệt |
| Shared host, path-based issuer | Mỗi tenant có issuer path riêng, ví dụ /acme | Request path phân giải issuer | Nhiều tenant dùng chung runtime nhưng cần discovery, key và client registry riêng |
| Shared issuer, tenant claim | Một issuer chung cho tất cả | Tenant là claim/context trong authorization và API policy | Tenant chỉ là phạm vi dữ liệu/permission bên trong cùng miền danh tính |

Bài này tập trung vào mô hình **shared host, path-based issuer** mà Spring Authorization Server hỗ trợ trực tiếp qua `multipleIssuersAllowed(true)`.

### 2.1. Shared issuer không đồng nghĩa nhiều issuer

Nếu tất cả người dùng cùng tin cậy issuer `https://auth.example.vn` và access token mang claim `tenant_id`, hệ thống vẫn có **một issuer**. Khi đó tenant isolation phải được thực hiện trong user store, authorization, scopes, claims, Resource Server và database queries.

Ngược lại, nếu mỗi tenant có issuer `https://auth.example.vn/acme` hoặc `https://auth.example.vn/contoso`, client có thể discovery và pin một OP riêng cho tenant. Mỗi issuer cần metadata, JWK Set và token validation phù hợp.

Không trộn hai mô hình bằng cách chỉ thay claim tenant rồi kỳ vọng ID Token issuer tự thay đổi.

## 3. Phân giải issuer bằng path component

Spring Authorization Server 1.5.8 hỗ trợ nhiều issuer trên cùng host thông qua path component của issuer identifier. Ví dụ:

~~~text
https://auth.example.vn/acme
https://auth.example.vn/contoso
~~~

Các endpoint của tenant nằm dưới issuer base:

| Protocol endpoint | Tenant acme | Tenant contoso |
|---|---|---|
| Issuer | https://auth.example.vn/acme | https://auth.example.vn/contoso |
| Authorization | /acme/oauth2/authorize | /contoso/oauth2/authorize |
| Token | /acme/oauth2/token | /contoso/oauth2/token |
| JWK Set | /acme/oauth2/jwks | /contoso/oauth2/jwks |
| Revocation | /acme/oauth2/revoke | /contoso/oauth2/revoke |
| Introspection | /acme/oauth2/introspect | /contoso/oauth2/introspect |
| OIDC Provider Configuration | /acme/.well-known/openid-configuration | /contoso/.well-known/openid-configuration |

Ví dụ request discovery:

~~~http
GET /acme/.well-known/openid-configuration HTTP/1.1
Host: auth.example.vn
Accept: application/json
~~~

Metadata trả về phải công bố:

~~~json
{
  "issuer": "https://auth.example.vn/acme",
  "authorization_endpoint": "https://auth.example.vn/acme/oauth2/authorize",
  "token_endpoint": "https://auth.example.vn/acme/oauth2/token",
  "jwks_uri": "https://auth.example.vn/acme/oauth2/jwks",
  "revocation_endpoint": "https://auth.example.vn/acme/oauth2/revoke",
  "introspection_endpoint": "https://auth.example.vn/acme/oauth2/introspect"
}
~~~

Đây là ví dụ minh họa. URL public phải nhất quán với reverse proxy, TLS termination và issuer được resolve trong ứng dụng.

### 3.1. OIDC Provider Configuration và OAuth AS Metadata

OIDC Provider Configuration thường được discovery tại:

~~~text
/{tenant}/.well-known/openid-configuration
~~~

OAuth 2.0 Authorization Server Metadata có quy tắc well-known riêng, ví dụ:

~~~text
/.well-known/oauth-authorization-server/{tenant}
~~~

Client phải dùng đúng metadata protocol mà nó hỗ trợ. Không lấy issuer từ một metadata document rồi lấy JWK Set từ host khác không nằm trong trust contract.

### 3.2. Đường đi của một request theo issuer

~~~mermaid
flowchart TD
    A[HTTP request tới issuer path] --> B[Spring Authorization Server resolve issuer]
    B --> C{Issuer có trong tenant registry?}
    C -->|Không| D[Fail closed]
    C -->|Có| E[AuthorizationServerContextHolder]
    E --> F[Delegating protocol component]
    F --> G[RegisteredClientRepository]
    F --> H[OAuth2AuthorizationService]
    F --> I[OAuth2AuthorizationConsentService]
    F --> J[JWKSource]
    G --> K[(Tenant A data / keys)]
    H --> K
    I --> K
    J --> L[Tenant A signing key set]
~~~

Issuer được resolve một lần trong protocol request và được dùng để chọn các component của cùng tenant. Nếu lookup không tìm thấy tenant, request phải dừng ở bước registry; không được đi tiếp với component mặc định.

## 4. Bật nhiều issuer trong Spring Authorization Server

Mặc định, hỗ trợ nhiều issuer trên cùng host bị tắt. Bật bằng `AuthorizationServerSettings.builder().multipleIssuersAllowed(true)`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .multipleIssuersAllowed(true)
                .build();
    }
}
~~~

Điểm cần lưu ý:

- **Không gọi** `.issuer("https://auth.example.vn")` trong cấu hình multi-issuer này. Cấu hình issuer cố định buộc Authorization Server dùng một issuer, làm mất ý nghĩa resolve issuer theo request.
- `multipleIssuersAllowed(true)` chỉ bật khả năng sử dụng nhiều issuer. Nó không tự tạo tenant, database, client registry, signing key hay authorization store cho từng tenant.
- Ứng dụng vẫn phải xây dựng các component biết tenant và từ chối issuer không được đăng ký.
- Với deployment single-tenant, cấu hình issuer cố định vẫn hợp lý.

Issuer được xác định trong context của request Authorization Server. Trong quá trình xử lý protocol endpoint, ứng dụng có thể lấy context bằng `AuthorizationServerContextHolder`.

## 5. Lấy issuer hiện tại bằng AuthorizationServerContextHolder

Spring Authorization Server cung cấp:

- `AuthorizationServerContext`: chứa issuer và authorization server settings của request hiện tại.
- `AuthorizationServerContextHolder`: truy cập context hiện tại trong quá trình xử lý request.

Ví dụ:

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException("Authorization Server issuer is unavailable");
}

String issuer = context.getIssuer();
~~~

Trong một request có issuer `https://auth.example.vn/acme`, context cần phân giải issuer đó để các component chọn cấu hình tenant acme.

**Không tự tạo issuer từ header không tin cậy.** Reverse proxy chỉ được phép ghi `Forwarded`/`X-Forwarded-*` nếu application chỉ nhận traffic từ proxy tin cậy và proxy đã xóa giá trị do client gửi. Nếu issuer phụ thuộc host/path, cần chuẩn hóa public URL và xác minh route trước khi dùng làm tenant key.

### 5.1. Không dùng request context ngoài vòng đời request

`AuthorizationServerContextHolder` là context của request hiện tại. Không mặc định context sẽ tự đi theo khi xử lý async, gửi message hoặc chạy background job.

Nếu tác vụ nền cần tenant, truyền tenant ID/issuer đã xác minh như một tham số tường minh, tra lại trong tenant registry và kiểm tra trạng thái tenant. Không lấy tenant từ thread cũ hoặc giữ context trong một singleton.

## 6. Tenant registry: allowlist issuer hợp lệ

Mỗi issuer cần được đăng ký trước trong một registry do ứng dụng kiểm soát. Registry ánh xạ **issuer đầy đủ, canonical** sang bộ component của tenant.

Ví dụ model:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

record TenantComponents(
        RegisteredClientRepository clients,
        OAuth2AuthorizationService authorizations,
        OAuth2AuthorizationConsentService consents,
        JWKSource<SecurityContext> jwkSource) {
}
~~~

Registry minh họa:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.Assert;
import org.springframework.util.StringUtils;

@Component
final class TenantComponentRegistry {

    private final Map<String, TenantComponents> tenants =
            new ConcurrentHashMap<>();

    public void register(String issuer, TenantComponents components) {
        Assert.hasText(issuer, "issuer must not be blank");
        Assert.notNull(components, "tenant components must not be null");

        TenantComponents previous = tenants.putIfAbsent(issuer, components);
        Assert.state(previous == null, "issuer is already registered");
    }

    public TenantComponents current() {
        AuthorizationServerContext context =
                AuthorizationServerContextHolder.getContext();

        Assert.state(context != null
                        && StringUtils.hasText(context.getIssuer()),
                "Current Authorization Server issuer is unavailable");

        // Exact full-issuer lookup: unknown issuer must fail closed.
        TenantComponents components = tenants.get(context.getIssuer());
        Assert.state(components != null,
                "No tenant is registered for the requested issuer");

        return components;
    }
}
~~~

Ví dụ dùng full issuer làm key, tránh so khớp hậu tố đơn giản như `endsWith("acme")`, vốn có thể tạo nhầm tenant khi identifier có cấu trúc gần giống. Nếu cần map từ tenant slug sang issuer, thực hiện ở bước onboarding và lưu mapping canonical, unique.

### 6.1. Vì sao registry là allowlist?

Registry vừa định tuyến component vừa là allowlist issuer hợp lệ. Nếu issuer không có trong registry, request phải thất bại rõ ràng. Không tạo datasource, JWK URL hoặc tenant context mới chỉ vì request gửi một path bất kỳ.

Không nên triển khai kiểu:

~~~java
// Không an toàn: biến dữ liệu request thành nguồn để tạo kết nối hoặc URL.
String issuer = request.getRequestURL().toString();
String jwksUrl = issuer + "/oauth2/jwks";
~~~

Cách này dễ mở đường cho issuer spoofing, SSRF, host-header poisoning hoặc tạo tenant ngoài chính sách.

## 7. Những component cần tenant-aware trong Spring Authorization Server

Hướng dẫn multi-tenancy của Spring Authorization Server xác định bốn component cốt lõi cần delegate theo issuer:

| Component | Trách nhiệm | Cần tách theo tenant vì |
|---|---|---|
| `RegisteredClientRepository` | Lưu/tìm OAuth client registration | Client ID, redirect URI, auth method, scopes và settings thuộc tenant |
| `OAuth2AuthorizationService` | Lưu/tìm authorization và token | Authorization code, access/refresh token và grant không được lẫn tenant |
| `OAuth2AuthorizationConsentService` | Lưu consent của user/client | Consent của tenant A không được áp dụng ở tenant B |
| `JWKSource<SecurityContext>` | Cung cấp signing keys/JWK Set | Token của mỗi issuer cần được ký/xác minh theo key policy tương ứng |

Các component khác cũng có thể cần tenant awareness tùy hệ thống: user lookup/authentication, tenant-specific login/consent page, audit, rate limiting, branding, password/MFA policy, session store, email/SMS provider và token customizer.

### 7.1. Delegating component

Mỗi interface cốt lõi có thể được triển khai bằng một composite/delegating adapter. Adapter lấy tenant hiện tại từ registry rồi chuyển lời gọi đến implementation cụ thể.

Ví dụ cho `RegisteredClientRepository`:

~~~java
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

final class TenantAwareRegisteredClientRepository
        implements RegisteredClientRepository {

    private final TenantComponentRegistry registry;

    TenantAwareRegisteredClientRepository(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        registry.current().clients().save(registeredClient);
    }

    @Override
    public RegisteredClient findById(String id) {
        return registry.current().clients().findById(id);
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return registry.current().clients().findByClientId(clientId);
    }
}
~~~

Adapter JWKSource:

~~~java
import com.nimbusds.jose.KeySourceException;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSelector;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import java.util.List;

final class TenantAwareJWKSource implements JWKSource<SecurityContext> {

    private final TenantComponentRegistry registry;

    TenantAwareJWKSource(TenantComponentRegistry registry) {
        this.registry = registry;
    }

    @Override
    public List<JWK> get(
            JWKSelector selector,
            SecurityContext context) throws KeySourceException {
        return registry.current().jwkSource().get(selector, context);
    }
}
~~~

Với `OAuth2AuthorizationService`, delegate `save`, `remove`, `findById` và `findByToken`. Với `OAuth2AuthorizationConsentService`, delegate `save`, `remove` và `findById`. Mọi phương thức phải dùng cùng tenant context và không có fallback sang store mặc định.

### 7.2. Không chỉ tách repository

Nếu RegisteredClient được tách nhưng OAuth2AuthorizationService dùng chung mà không có tenant discriminator, token của một tenant vẫn có thể bị tìm trong tenant khác. Tương tự, nếu JWKSource dùng chung private key và consent store không phân vùng, issuer khác nhau nhưng trust boundary vẫn bị trộn.

Hãy kiểm tra toàn bộ đường đi: client authentication → authorization lookup → consent → token generation/signing → JWK publication → introspection/revocation → Resource Server validation.

## 8. Chiến lược cô lập persistence theo tenant

Có ba lựa chọn phổ biến. Chọn theo mức isolation, số tenant, chi phí vận hành và khả năng backup/restore.

| Chiến lược | Cách triển khai | Ưu điểm | Trade-off |
|---|---|---|---|
| Database riêng | Mỗi tenant có DataSource/database riêng | Isolation mạnh, backup/restore độc lập | Nhiều connection pool và migration |
| Schema riêng | Cùng DB server nhưng schema riêng | Cân bằng isolation và vận hành | Phải route schema/connection an toàn |
| Shared tables + tenant key | Thêm tenant/issuer discriminator vào mọi bảng và unique key | Ít hạ tầng, dễ mở rộng số tenant | Mọi query, index và transaction phải tenant-aware |

Spring Authorization Server cung cấp JDBC implementations như `JdbcRegisteredClientRepository`, `JdbcOAuth2AuthorizationService` và `JdbcOAuth2AuthorizationConsentService`. Có thể tạo một instance cho mỗi tenant và delegate theo issuer.

Ví dụ cấu hình component theo DataSource riêng:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

TenantComponents createTenantComponents(
        DataSource dataSource,
        JWKSource<SecurityContext> tenantJwkSource) {

    JdbcTemplate jdbc = new JdbcTemplate(dataSource);

    RegisteredClientRepository clients =
            new JdbcRegisteredClientRepository(jdbc);

    OAuth2AuthorizationService authorizations =
            new JdbcOAuth2AuthorizationService(jdbc, clients);

    OAuth2AuthorizationConsentService consents =
            new JdbcOAuth2AuthorizationConsentService(jdbc, clients);

    return new TenantComponents(
            clients, authorizations, consents, tenantJwkSource);
}
~~~

Đây là factory minh họa; cần inject đúng schema/migration và transaction manager của tenant. Không tạo DataSource từ tenant slug chưa xác minh.

### 8.1. Shared table cần composite uniqueness

Nếu nhiều tenant dùng chung bảng, mọi record phải mang tenant/issuer ID đã xác minh. Unique constraints và index cần bao gồm tenant key ở những nơi định danh chỉ unique trong tenant:

- `(tenant_id, client_id)` cho client registration.
- `(tenant_id, authorization_id)` hoặc khóa tương đương cho authorization.
- `(tenant_id, registered_client_id, principal_name)` cho consent.
- `(tenant_id, token_lookup_digest)` cho token lookup nếu dùng digest.
- Tenant discriminator trong mọi update/delete/select.

Không chỉ thêm tenant_id vào Java object mà quên predicate trong SQL. Một query thiếu tenant filter có thể tạo cross-tenant data leak.

### 8.2. Tenant context và transaction

Tenant phải được resolve trước khi repository được gọi và giữ nhất quán trong toàn transaction. Không thay tenant giữa một request. Nếu transaction async hoặc event-driven, truyền tenant ID tường minh và tái xác minh.

Với schema-per-tenant, tránh thay search_path hoặc schema context trên connection pooled mà không reset trong finally. Một connection được trả pool với schema cũ có thể khiến request tiếp theo đọc/ghi nhầm tenant.

## 9. Signing key và JWK Set riêng theo issuer

Mỗi issuer nên có key policy rõ ràng. Cách ly JWK Set theo tenant giúp:

- Tenant A không công bố public key của tenant B.
- ID Token và JWT access token được ký bằng key thuộc issuer phát hành.
- Key rotation và compromise có thể xử lý theo tenant.
- RP discovery đúng issuer và tải JWK Set tương ứng.

JWK Set endpoint cần delegate tới JWKSource của tenant hiện tại. Không chọn key chỉ dựa vào `kid` do client gửi; kid chỉ dùng để tìm key bên trong tập key của issuer đã resolve.

### 9.1. Cùng key hay key riêng?

Dùng key riêng cho mỗi tenant thường giảm blast radius và giúp tách trust. Dùng chung signing key có thể đơn giản hóa vận hành nhưng làm giảm isolation: compromise một key có thể ảnh hưởng mọi issuer chia sẻ key đó. Nếu chủ động chia sẻ, cần threat model, key governance và client trust policy rõ ràng.

Không sinh key pair ngẫu nhiên mới mỗi lần application restart. Key phải được lưu bền vững trong KMS/HSM/keystore, có kid, thuật toán, trạng thái active/retired và kế hoạch rollover. Tất cả pod phải dùng cùng key set cho cùng tenant.

### 9.2. Token claims và issuer

Khi phát JWT/ID Token cho tenant, claim iss phải là issuer của tenant hiện tại. Token của acme không được mang issuer contoso. RP/Resource Server cần validate exact issuer và chữ ký bằng JWK Set của issuer đó.

Không lấy iss từ user attribute, request body hoặc claim upstream chưa xác minh. Issuer là thuộc tính do Authorization Server kiểm soát.

## 10. Thêm tenant tĩnh và tenant động

### 10.1. Tenant tĩnh lúc khởi động

Nếu số tenant nhỏ và thay đổi hiếm, có thể khai báo cấu hình từng tenant, tạo DataSource/repository/JWKSource tương ứng lúc startup rồi đăng ký vào registry. Ưu điểm là cấu hình được review/deploy cùng ứng dụng. Nhược điểm là mỗi lần thêm tenant có thể cần thay đổi cấu hình hoặc rollout.

### 10.2. Tenant động lúc runtime

Nếu tenant được onboard thường xuyên, cần một TenantProvisioningService có workflow riêng:

1. Nhận yêu cầu onboard từ admin/control plane đã xác thực.
2. Kiểm tra tenant ID/slug chưa tồn tại và phù hợp naming policy.
3. Tạo canonical issuer từ public base URL đã cấu hình và tenant slug hợp lệ.
4. Tạo database/schema và chạy migration.
5. Tạo client repository, authorization service và consent service.
6. Provision signing key/JWK Set trong KMS/HSM hoặc key store.
7. Đăng ký đầy đủ component vào registry một cách atomic.
8. Kiểm tra discovery metadata và health của tenant.
9. Chuyển tenant sang trạng thái active sau khi mọi component sẵn sàng.

Không thêm issuer vào registry trước khi database và signing key đã sẵn sàng. Nếu một phần provisioning thất bại, tenant phải ở trạng thái pending/failed và không nhận authorization request.

### 10.3. Deactivate và remove tenant

Khi ngừng tenant, cần xác định policy cho client, token, consent, signing key, backup và retention. Không chỉ xóa registry entry trong khi request đang chạy.

Quy trình có thể gồm: ngừng nhận authorization/token request mới, drain request đang chạy, disable client registrations, revoke/expire token theo policy, lưu audit/backup, cập nhật discovery routing và cuối cùng mới retire key/data theo retention. Việc xóa tenant là thao tác quản trị có tác động lớn, cần kiểm soát quyền và audit.

## 11. Phân giải tenant ở Resource Server

Authorization Server multi-issuer chỉ là một phần của hệ thống. Resource Server phải xác minh token theo đúng issuer, signing keys, audience và policy.

Nếu Resource Server nhận JWT từ một tập issuer đã biết, Spring Security hỗ trợ `JwtIssuerAuthenticationManagerResolver` để chọn authentication manager theo claim issuer. Cấu hình trusted issuers là allowlist:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtIssuerAuthenticationManagerResolver resolver =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                    "https://auth.example.vn/acme",
                    "https://auth.example.vn/contoso");

    http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resolver));

    return http.build();
}
~~~

Ví dụ này minh họa issuer allowlist. Production còn cần kiểm tra audience, expiry, algorithm, tenant-specific authorities và resource policy.

**Không** tự tải JWK Set từ iss bất kỳ trong JWT chưa xác minh. Nếu cho phép issuer động, phải tra issuer trong tenant repository/allowlist trước khi tạo decoder hoặc gọi URL; nếu không có thể tạo SSRF hoặc tin token do attacker kiểm soát.

### 11.1. Resolve và propagate tenant

Spring Security phân biệt hai việc:

- **Resolve tenant:** xác định tenant từ issuer đã xác minh hoặc request context được tin cậy.
- **Propagate tenant:** đưa tenant context đã xác minh tới authorization/data access downstream.

Nếu tenant được xác định từ JWT claim, Resource Server chỉ nên dùng claim sau khi chữ ký và issuer đã được validate. Nếu tenant được xác định từ hostname/path, API phải dùng cùng mapping và bảo đảm token issuer/audience không mâu thuẫn với route.

Tenant context cần được đưa vào service/repository policy, không chỉ lưu trong một header nội bộ có thể bị client giả mạo.

### 11.2. JWT và opaque token

Một tenant có thể dùng JWT trong khi tenant khác dùng opaque token/introspection. Khi lựa chọn strategy tại request-time, Spring Security có `AuthenticationManagerResolver<HttpServletRequest>` để chọn `JwtAuthenticationProvider` hoặc `OpaqueTokenAuthenticationProvider`.

Không quyết định token format chỉ bằng cách kiểm tra chuỗi có dấu chấm. Hãy dùng tenant registry/config đã được kiểm soát và validator đúng cho issuer đó.

## 12. Bảo vệ ranh giới tenant

Các lỗi multi-tenant thường đến từ một component được cấu hình đúng nhưng một component khác dùng context mặc định hoặc shared state.

| Ranh giới | Điều cần bảo vệ | Negative case |
|---|---|---|
| Issuer resolution | Exact issuer và route canonical | /acme-evil không được match /acme |
| Client registration | Client lookup trong tenant hiện tại | Client acme không xác thực ở contoso |
| Authorization/token store | Token lookup/save/remove có tenant context | Token tenant A không được revoke/introspect từ B |
| Consent | Consent theo tenant + client + principal | Consent acme không được tái sử dụng ở contoso |
| JWKSource | Key set theo issuer | Token acme không verify bằng key riêng của contoso |
| User identity | Local user/tenant membership | User thuộc tenant A không tự có membership B |
| Resource Server | Issuer, audience, scope và tenant policy | Token đúng chữ ký nhưng sai audience/tenant bị từ chối |
| Cache | Cache key có issuer/tenant | Client/token metadata không bị cache chéo |
| Audit/log | Gắn tenant đã xác minh, redact secret | Không ghi token và không gán nhầm tenant |
| Admin plane | Onboard/deactivate tenant có authorization | Caller không thể tự tạo issuer ngoài allowlist |

### 12.1. Không fallback về tenant mặc định

Nếu issuer không có component, request phải thất bại. Không fallback sang repository/JWKSource của tenant mặc định. Fallback có thể biến lỗi định tuyến thành truy cập dữ liệu tenant khác.

### 12.2. Cache key phải chứa tenant identity

Nếu cache RegisteredClient, authorization, consent, JWK hoặc user profile, key cache cần chứa tenant/issuer. Ví dụ cache key chỉ là client_id=portal-web có thể trả registration của tenant acme cho request contoso nếu cả hai tenant có cùng client ID.

### 12.3. Host và forwarded header

Nếu tenant được route bằng subdomain, chỉ tin Host/Forwarded headers từ proxy/load balancer đã xác thực. Proxy phải strip header client tự gửi rồi tạo header chuẩn. Cấu hình allowed hosts, TLS và canonical external URL; không để attacker đổi X-Forwarded-Host để thay issuer.

## 13. Ma trận kiểm thử multi-issuer

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Gọi OIDC discovery của acme | Metadata issuer và endpoints đều thuộc acme |
| 2 | Gọi OIDC discovery của contoso | Metadata issuer và endpoints đều thuộc contoso |
| 3 | multipleIssuersAllowed chưa bật | Không coi path tenant là multi-issuer đã hỗ trợ |
| 4 | Cấu hình đồng thời issuer cố định | Phát hiện cấu hình single-issuer, không deploy như multi-tenant |
| 5 | Issuer path không nằm registry | Từ chối, không fallback |
| 6 | Path /acme-evil gần giống /acme | Không match nhầm tenant |
| 7 | Client ID trùng ở hai tenant | Mỗi tenant lookup registration riêng |
| 8 | Client acme dùng ở issuer contoso | Client authentication thất bại |
| 9 | Authorization code acme gửi tới token endpoint contoso | Không đổi được code |
| 10 | Refresh token acme gửi tới contoso | Không refresh được |
| 11 | Revoke token acme qua issuer contoso | Không thay đổi authorization acme |
| 12 | Introspection token acme qua contoso | Không tiết lộ trạng thái token acme |
| 13 | Consent acme được tìm từ contoso | Không trả consent |
| 14 | JWK endpoint acme | Chỉ công bố JWK Set của acme |
| 15 | JWK endpoint contoso | Chỉ công bố JWK Set của contoso |
| 16 | Token acme verify bằng JWK contoso | Chữ ký/issuer validation thất bại |
| 17 | Token acme có issuer contoso giả | Resource Server từ chối |
| 18 | Token đúng issuer nhưng sai audience | Resource Server từ chối |
| 19 | JWT issuer không nằm allowlist | Authentication thất bại, không fetch JWK URL tùy ý |
| 20 | X-Forwarded-Host do client giả mạo | Không làm thay đổi issuer public |
| 21 | Cache registration cùng client ID khác tenant | Không trả dữ liệu chéo |
| 22 | Cache JWK cùng kid khác tenant | Không dùng nhầm key |
| 23 | Tenant dynamic đang provisioning | Không nhận request trước khi component sẵn sàng |
| 24 | Provisioning thất bại giữa chừng | Tenant không active và không được route |
| 25 | Hai admin onboard cùng slug | Unique constraint ngăn tạo tenant trùng |
| 26 | Deactivate tenant trong khi có request | Drain/deny theo lifecycle policy, không route sang tenant khác |
| 27 | Pod A và pod B cùng issuer | Cùng registry/config/key/store cho tenant |
| 28 | Background job không có request context | Phải truyền tenant tường minh; không lấy tenant mặc định |
| 29 | Shared table query thiếu tenant predicate | Test phát hiện cross-tenant read/write |
| 30 | Database/schema pool tái sử dụng connection | Schema context được reset, không rò tenant |
| 31 | User acme đăng nhập ở contoso | Không có membership thì bị từ chối |
| 32 | Token acme mang scope không có ở contoso | Không cấp quyền dựa trên scope của tenant khác |
| 33 | Signing key rotation ở acme | Không ảnh hưởng JWK/key của contoso |
| 34 | KMS/database tenant acme unavailable | Request acme fail closed; contoso vẫn theo isolation policy |
| 35 | Backup/restore một tenant | Khôi phục đúng data, issuer, key và metadata của tenant đó |

### 13.1. Các assertion quan trọng

Integration test cần xác minh:

- Issuer trong metadata và token đúng với path/tenant.
- AuthorizationServerContextHolder trả issuer mong đợi trong từng protocol request.
- Bốn component cốt lõi delegate tới đúng tenant.
- Không có fallback khi issuer không được đăng ký.
- Client ID trùng giữa hai tenant không gây nhầm registration.
- Token, consent, JWK, cache và user mapping không rò chéo.
- Resource Server xác minh exact issuer, audience và authorities.
- Dynamic onboarding chỉ active sau khi tất cả component sẵn sàng.
- Multi-pod request có cùng kết quả với cùng issuer.
- Reverse proxy không thể bị lợi dụng để giả mạo issuer.

## 14. Troubleshooting và checklist production

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Metadata trả issuer gốc, thiếu tenant path | Cấu hình issuer cố định hoặc proxy/path không được nhận diện | Bỏ issuer cố định trong multi-issuer; kiểm tra public route |
| Mọi tenant dùng cùng client registry | Chưa có delegating RegisteredClientRepository | Route theo AuthorizationServerContext issuer |
| Token tenant A được tìm ở tenant B | AuthorizationService shared sai cách hoặc thiếu tenant discriminator | Tách service hoặc sửa query/tenant predicate |
| JWK Set của tenant không đúng | JWKSource không tenant-aware hoặc cache key thiếu issuer | Delegate JWKSource theo issuer và cô lập cache |
| Unknown tenant trả dữ liệu default | Component fallback sang tenant mặc định | Fail closed và thêm negative tests |
| Một pod resolve issuer khác pod còn lại | Forwarded headers, host/path hoặc config lệch | Chuẩn hóa proxy và đồng bộ deployment |
| Resource Server fetch JWK từ URL lạ | Tin iss chưa xác minh hoặc dynamic issuer không allowlist | Dùng trusted issuer registry |
| Client ID trùng gây xác thực nhầm | Lookup không chạy trong tenant context | Kiểm tra context và unique key theo tenant |
| Schema cũ dùng nhầm connection tenant | Không reset schema/connection pool | Quản lý transaction và reset schema an toàn |
| Dynamic tenant active nhưng token endpoint lỗi | Đăng ký component trước khi DB/key sẵn sàng | Provisioning state machine và atomic activation |

### 14.1. Checklist production

- [ ] Chọn rõ mô hình dedicated issuer, path-based multi-issuer hoặc shared issuer + tenant claim.
- [ ] Với path-based multi-issuer, bật `multipleIssuersAllowed(true)`.
- [ ] Không cấu hình issuer cố định khi cần resolve nhiều issuer từ request.
- [ ] Issuer canonical và tenant mapping nằm trong allowlist do server quản lý.
- [ ] Unknown issuer fail closed, không fallback sang tenant mặc định.
- [ ] RegisteredClientRepository, OAuth2AuthorizationService, OAuth2AuthorizationConsentService và JWKSource đều tenant-aware.
- [ ] Chọn database riêng, schema riêng hoặc shared table có tenant discriminator/composite constraints.
- [ ] Signing key/JWK Set và key rotation được quản lý theo tenant.
- [ ] Cache key chứa tenant/issuer.
- [ ] Resource Server validate exact issuer, audience, signature, expiry và tenant authorities.
- [ ] Không fetch JWK từ issuer URL tùy ý trong token chưa xác minh.
- [ ] Proxy/Host/Forwarded headers được giới hạn theo trust boundary.
- [ ] Tenant context không bị mất trong async/background processing.
- [ ] Dynamic onboarding/deactivation có state machine, audit và atomic activation.
- [ ] Có negative tests chống cross-tenant token, client, consent, cache và user access.
- [ ] Có backup/restore và incident runbook theo tenant.
- [ ] Metrics/log có tenant ID đã xác minh nhưng không chứa token/secret.

**Câu hỏi tự đánh giá**

1. Khác nhau giữa shared issuer có claim tenant_id và path-based multiple issuers là gì?
2. Vì sao issuer là một phần của trust boundary chứ không chỉ là URL?
3. Spring Authorization Server bật multiple issuers bằng cấu hình nào?
4. Vì sao cấu hình issuer cố định làm mất khả năng resolve issuer theo request?
5. AuthorizationServerContextHolder cung cấp thông tin gì và có giới hạn vòng đời ra sao?
6. Vì sao tenant registry nên tra cứu exact full issuer thay vì suffix match?
7. Bốn component cốt lõi nào phải tenant-aware?
8. Nếu RegisteredClientRepository tách tenant nhưng OAuth2AuthorizationService không tách thì rủi ro gì?
9. Vì sao JWK Set nên được quản lý theo issuer?
10. Database riêng, schema riêng và shared tables khác nhau thế nào về isolation?
11. Vì sao cache key chỉ dùng client ID có thể gây cross-tenant leak?
12. Resource Server chọn decoder theo issuer như thế nào và tại sao cần trusted issuer allowlist?
13. Vì sao không được fetch JWK URL từ iss bất kỳ trong JWT chưa xác minh?
14. Khi tenant được onboard động, lúc nào mới được chuyển sang active?
15. Làm thế nào để bảo đảm request nhiều pod luôn chọn cùng tenant store?
16. Khi deactivate tenant, vì sao không nên chỉ xóa registry entry ngay lập tức?

## Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): multipleIssuersAllowed, issuer path, AuthorizationServerContextHolder, component registry và bốn multi-tenant components.
- [Spring Authorization Server — AuthorizationServerSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.Builder.html): multipleIssuersAllowed(boolean) và lưu ý issuer cố định.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent và JWKSource components.
- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): resolve/propagate tenant, trusted issuer và AuthenticationManagerResolver.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer và Provider Configuration metadata.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer và well-known metadata endpoint.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): issuer, audience và validation JWT access token.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ authorization server, issuer, token và trust boundary.
