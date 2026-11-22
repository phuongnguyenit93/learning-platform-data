# Ranh giới giữa xác minh token và quyết định cho phép truy cập

## 1. Một token hợp lệ không phải giấy phép truy cập mọi tài nguyên

Giả sử An đăng nhập qua OAuth2, nhận access token có chữ ký hợp lệ, chưa hết hạn và scope `documents.read`. An yêu cầu:

~~~http
GET /api/tenants/north/documents/42
Authorization: Bearer <access-token>
~~~

Spring Security Resource Server xác minh được token rồi tạo `Authentication`. Có được trả Document #42 ngay không? **Không**. Document có thể thuộc tenant south, do Bình sở hữu, chưa chia sẻ với An, bị khóa hoặc nằm trong project riêng.

Hai câu hỏi phải được giải đáp riêng:

1. **Xác minh token (validation/authentication):** credential này có nguồn phát đáng tin, chữ ký hoặc trạng thái hợp lệ, đúng issuer, đúng audience của API, chưa hết hạn, đúng loại token và đáp ứng chính sách token?
2. **Quyết định cho phép (authorization):** actor/client đã được xác minh có được thực hiện action READ/WRITE/DELETE trên **đúng resource, tenant và trạng thái hiện hành**?

Token validation thành công là nền tảng cho quyết định quyền, **không thay thế** object-level authorization. Trong Spring Security, JwtDecoder/opaque introspection xử lý xác minh token; HTTP/method security kiểm quyền chức năng; service/repository mới thường biết owner, ACL, membership và trạng thái tài nguyên.

Bài học thuộc nhóm **Quyền từ OAuth2** này đào sâu ranh giới trên, bao gồm OAuth2 access/ID/refresh tokens, JWT vs opaque, issuer/audience, `SCOPE_` mapping, client credentials, multi-tenant, concurrency, lỗi API và chiến lược kiểm thử.

## 2. Sơ đồ luồng xác thực và phân quyền

~~~text
Browser / mobile / service client
                |
                | Authorization: Bearer <access-token>
                v
Spring Security authentication
  JWT decoder: signature + iss + aud + exp + nbf + type...
  HOẶC opaque introspection: active + metadata đáng tin
                |
                v
Authentication (verified subject/client + authorities)
                |
                v
HTTP authorization: method/path/scope
                |
                v
Service authorization:
  verified tenant membership
  role/action
  resource owner/ACL/project/status
                |
                v
Scoped query / guarded UPDATE/DELETE
                |
                v
DTO / commit / authorized side effect
~~~

Một yêu cầu có thể thất bại tại nhiều điểm:
- JWT sai chữ ký, issuer, audience, expiry → authentication failure, thường 401.
- JWT hợp lệ nhưng thiếu WRITE scope → authorization failure, thường 403.
- Token và WRITE scope hợp lệ nhưng object của tenant khác → object denial, có thể 404 để tránh lộ sự tồn tại.
- Quyền đúng nhưng trạng thái LOCKED → business rule denial.
- Introspection hoặc policy backend unavailable → không suy ra ALLOW; chặn action và xử lý lỗi.

**Đừng dùng kết quả tầng trước như một cách bỏ qua tầng sau.** Token accepted không đồng nghĩa scope đủ; scope đủ không đồng nghĩa owner; owner cũng không tự vượt qua trạng thái khóa.

## 3. Các actor trong OAuth2

| Thành phần | Vai trò | Không tự đảm nhận |
|---|---|---|
| Authorization Server (AS) | Cấp token, JWKS/introspection và metadata | Mọi object ACL của Resource Server |
| OAuth2 Client | Ứng dụng yêu cầu/sử dụng access token | Tự chứng minh client ID là owner |
| Resource Server (RS) | API xác minh token và bảo vệ dữ liệu | Phát token chỉ nhờ cấu hình decoder |
| Resource Owner | Chủ thể có liên quan quyền dữ liệu theo OAuth flow | Luôn phải có human user trong client credentials |
| PEP | Nơi chặn và thực thi quyền | Cho side effect khi không có ALLOW |
| PDP/domain policy | Đánh giá subject, tenant, action, resource và context | Tin dữ liệu owner/role do client tự khai |

Một authorization server có thể cấp scope `documents.read` cho một client. Nó **không tự động** cung cấp danh sách document thuộc An và Bình nếu ACL nằm trong database của API.

Có hệ thống nhúng fine-grained entitlements vào access token; khi đó token phải mang đúng audience/object/action và resource server vẫn cần kiểm expiry/revocation/consistency theo policy. Không có công thức “AS đã ký thì mọi resource đều phải cho”.

## 4. Access token, OIDC ID token và refresh token khác nhau

| Token | Audience/mục đích chính | Nơi sử dụng |
|---|---|---|
| OAuth2 **access token** | Dành cho Resource Server/API | API endpoint nhận Bearer |
| OpenID Connect **ID token** | Dành cho OIDC client/relying party | Chứng minh sự kiện đăng nhập cho client |
| **Refresh token** | Dành cho quá trình lấy token mới | Client/Authorization Server theo grant |

ID token và access token **đều có thể là JWT**. Việc token gồm ba đoạn Base64URL không nói đó là loại nào.

~~~text
ID token:
  iss = https://idp.example.test/issuer
  aud = frontend-client
  sub = user-72

Access token:
  iss   = https://idp.example.test/issuer
  aud   = documents-api
  sub   = user-72
  scope = documents.read
~~~

Nếu resource server chỉ kiểm signature mà bỏ audience/type, OIDC ID token có thể bị chấp nhận nhầm làm API Bearer credential. Với hệ tuân **RFC 9068 JWT Access Token Profile**, JWT access token có yêu cầu `typ=at+jwt` hoặc `application/at+jwt`, ngoài issuer, audience, expiry và các claims khác. Không phải mọi issuer đều phát theo RFC 9068; phải xác định profile của issuer thực, không ép generic JWT thành RFC 9068 nếu authorization server không hỗ trợ.

**Không gửi refresh token hoặc ID token đến documents-api** chỉ vì client đã đăng nhập thành công.

## 5. Decode khác validate JWT

Các bước có độ tin cậy khác nhau:

~~~text
Base64URL decode JWT header/payload
  -> chỉ đọc JSON, chưa đáng tin

Parse claims
  -> nhận diện field, chưa chứng minh nguồn phát

Verify signature và thuật toán tin cậy
  -> nội dung khớp signing key đáng tin

Validate issuer/audience/time/token type
  -> token đúng profile và dành cho API

Authorize request và resource
  -> actor được làm action hiện tại trên object này?
~~~

Attacker có thể tự tạo payload:

~~~json
{
  "sub": "admin",
  "scope": "documents.write",
  "tenant": "finance"
}
~~~

Nếu server chỉ decode rồi tạo `ROLE_ADMIN`, đó là tin dữ liệu attacker viết. Sử dụng `JwtDecoder`/introspection đáng tin và chỉ ra quyết định sau authentication.

Chữ ký hợp lệ không chứng minh user là owner Document #42; cũng không bảo đảm token chưa bị đánh cắp. Nó chỉ cung cấp một thuộc tính của token theo trust/crypto configuration.

## 6. Danh sách kiểm JWT access token cần có

| Điều kiện | Nguyên nhân | Từ chối khi |
|---|---|---|
| Signature/MAC | Xác minh token không bị sửa, key đáng tin | Chữ ký không hợp lệ |
| Signing algorithm | Không tin alg do header tự khai | `none` hoặc alg ngoài allowlist |
| Key/JWKS/`kid` | Chọn key trong trust store issuer | Key lạ hoặc không thuộc issuer |
| `iss` | Nguồn phát token được phép | Issuer không tin cậy |
| `aud` | Token dành cho Resource Server hiện tại | Access token cho API khác |
| `exp` | Token hết hạn | Thời gian đã vượt expiry |
| `nbf` | Thời điểm bắt đầu hiệu lực | Token chưa hiệu lực |
| `iat` | Thời điểm phát hành hợp lý nếu policy yêu cầu | Token bất thường hoặc quá cũ |
| `typ`/token kind | Không nhầm loại JWT | ID token thay access token |
| `sub` hoặc client identity | Subject/workload theo token profile | Thiếu identity bắt buộc |
| `active`/revocation | Tình trạng token theo AS/RS | Token bị revoke |
| Sender constraints | Ràng buộc presenter nếu sử dụng | Token dùng không đúng holder |

Không cho JWT cung cấp `jku`/`x5u` arbitrary URL rồi tải key tùy ý. `kid` chỉ có ý nghĩa trong issuer/JWKS mà server tin. Kiểm chính xác `alg`, key rotation và issuer metadata.

**Issuer đúng chưa đủ nếu audience sai.** Default Resource Server validation thường bao gồm signature, exp, nbf và issuer khi cấu hình issuer; application-specific audience/type có thể cần validators bổ sung.

## 7. Audience ngăn token substitution giữa các API

~~~text
documents-api:
  aud = "documents-api"
  GET /api/documents/42

payments-api:
  aud = "payments-api"
  POST /api/payments
~~~

An có access token do cùng issuer phát, signature đúng, chưa hết hạn, nhưng aud=payments-api. Gửi đến documents-api phải **fail token validation**. Nếu API bỏ `aud`, token từ API dễ lấy có thể bị dùng trên API nhạy cảm (token substitution/confused deputy).

Một token có nhiều audience cần policy rõ: API chỉ nhận tokens chứa audience riêng đúng contract, không chấp nhận một chuỗi bất kỳ. Một aud có nhiều giá trị cũng không tự cấp mọi scope hoặc resource grant.

Mẫu sai:

~~~java
boolean trusted = jwt.getIssuer().toString()
        .equals("https://idp.example.test/issuer");
return trusted; // Thiếu audience, expiry, type, object checks.
~~~

Đây là **anti-pattern**, không phải validator sử dụng trong production. Dùng library/framework xác minh token đầy đủ.

## 8. Resource Server Servlet với Spring Security

Ví dụ cấu hình HTTP cho JWT:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentApiSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
        return http.build();
    }
}
~~~

**Mã tích hợp Spring Servlet**, cần dependencies Resource Server/Jose, authentication setup, JWT decoder/issuer và controllers thật. Không phải file Java 17 standalone.

Quy trình:
1. `BearerTokenAuthenticationFilter` lấy Bearer token.
2. JWT provider/decoder xác minh token theo validators.
3. Authentication được tạo, authorities theo converter.
4. `AuthorizationFilter`/HTTP rules kiểm scope theo path/method.
5. Service vẫn phải kiểm tenant/owner/ACL Document #42.

Với Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
~~~

Đây là URI ví dụ; application phải biết audience/type/claims profile thật. Không tự giả định `issuer-uri` đã kiểm toàn bộ domain authorization.

**Cảnh báo CSRF:** nếu API có session/cookie/HTTP Basic browser authentication, cần CSRF policy phù hợp. Đừng sao chép việc tắt CSRF chỉ vì thấy Resource Server.

## 9. JwtDecoder với audience validation rõ

Một class tích hợp Servlet có thể thêm `aud` validator:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceRequired = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "Required audience not present", null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audienceRequired));
        return decoder;
    }
}
~~~

Application configuration:

~~~yaml
app:
  security:
    issuer: https://idp.example.test/issuer
    audience: documents-api
~~~

**Đây là class Spring tích hợp**, không dùng standalone `javac`. Issuer/audience là trusted config, không lấy từ header hoặc một claim chưa xác minh.

Giữ `JwtValidators.createDefaultWithIssuer(issuer)` khi thêm audience, tránh vô tình thay mọi default validators bằng chỉ một predicate aud. Nếu cần RFC 9068, dùng token-type/profile validator phù hợp với Spring Security version (6.5/7.x có khác biệt liên quan `typ`), không coi generic JWT default đủ cho mọi issuer.

Không đưa public/private signing keys hoặc secrets vào source. Decoder/JWKS trust và algorithms phải được cấu hình chính xác.

## 10. Scopes được chuyển thành GrantedAuthority

JWT:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

Spring Security Resource Server mặc định thường chuyển scopes thành:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Vì vậy:

~~~java
.hasAuthority("SCOPE_documents.read")
~~~

kiểm đúng chuỗi authority. `hasRole("documents.read")` sẽ tìm `ROLE_documents.read`, **không giống** `SCOPE_documents.read`.

Lưu ý:
- Custom `roles:["ADMIN"]` không tự thành `ROLE_ADMIN` nếu chưa có converter.
- Scope token không chứng minh owner hay ACL của từng tài liệu.
- `hasAnyAuthority(a,b)` là OR; không dùng nó để yêu cầu cả hai.
- Token access scope và tenant role là những concepts khác nhau.

## 11. JwtAuthenticationConverter không thay object policy

Có thể cấu hình rõ claim và prefix:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter documentJwtConverter() {
    JwtGrantedAuthoritiesConverter granted =
            new JwtGrantedAuthoritiesConverter();
    granted.setAuthoritiesClaimName("scope");
    granted.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
~~~

Gắn vào Resource Server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
        jwt.jwtAuthenticationConverter(documentJwtConverter())))
~~~

**Snippet tích hợp**, cần ghép vào Spring configuration đầy đủ. Converter hoạt động sau JWT validation; nó ánh xạ claims thành authorities, **không** tự tra owner/ACL Document #42.

Nếu role chứa tenant-specific permission, đừng biến role của tenant north thành `ROLE_ADMIN` global rồi áp dụng ở south. Role token có thể stale khi membership bị thu hồi, cần revocation SLA hoặc kiểm lại trong service.

## 12. Các tầng Spring Security và trách nhiệm

| Component | Công việc |
|---|---|
| `BearerTokenAuthenticationFilter` | Lấy Bearer token trong Servlet request |
| `JwtAuthenticationProvider` | Yêu cầu decoder và tạo Authentication |
| `JwtDecoder/NimbusJwtDecoder` | Verify JWT và configured validators |
| `OpaqueTokenAuthenticationProvider` | Introspect token/tạo Authentication |
| `SecurityContextHolder` | Giữ Authentication trong Servlet processing |
| `AuthorizationFilter/AuthorizationManager` | Quyết định HTTP authorization |
| `@PreAuthorize` | Chặn method invocation theo policy |
| Domain service/repository | Quyền tenant, owner, ACL, trạng thái |
| Guarded transaction | Bảo vệ mutation/concurrency khi action chạy |

**Authentication.isAuthenticated() không chứng minh quyền xem mọi object**. Nó biểu thị trạng thái xác thực, còn functional/resource authorization phải kiểm riêng.

WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveSecurityContextHolder` và Reactor publishers. Không copy Servlet `HttpSecurity` sang WebFlux.

## 13. Opaque token và OAuth2 introspection

Một access token có thể là chuỗi opaque, không phải JWT mà RS tự đọc được. Resource Server hỏi AS qua introspection endpoint (RFC 7662):

~~~text
Resource Server                         Authorization Server
     |  Bearer token                           |
     +-- introspect(token, client credentials)->|
     |<-- active=true, scope, sub, aud... ------+
     |
     v
Authentication nếu token đáp ứng contract
     |
     v
Scope + domain/object authorization
~~~

Spring Boot Servlet:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/introspect
          client-id: documents-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Secret lấy từ environment/secret manager, không hard-code. `active=true` có thể giúp RS biết AS coi token active. Spring Security thường map scopes introspection thành `SCOPE_...`. Tuy nhiên:
- Active không tự chứng minh aud của API nếu resource profile cần kiểm riêng.
- Active không chứng minh An sở hữu Document #42.
- Introspection timeout/5xx không được biến thành allow.
- Cache kết quả introspection có thể kéo dài thời gian revoke được thực thi.

**Opaque access token không phải quyền tự động.** Nó chỉ có con đường token validation khác JWT local.

## 14. Có thể introspect token có định dạng JWT

JWT có thể được gửi tới introspection endpoint nếu kiến trúc muốn AS xác nhận active/revoked trên mỗi request. Spring opaque-token integration có thể introspect một chuỗi Bearer bất kể nó là opaque hay có dạng JWT.

So sánh:

| Điểm | JWT local | Introspection |
|---|---|---|
| Xác thực token | Signature, configured validators/JWKS | AS trả active và attributes đáng tin |
| Phụ thuộc network lúc request | Thường ít hơn khi key đã cache | Thường có nếu không cache |
| Revoke | Cần TTL/revocation/version mechanism | Có thể phản ánh AS status nhanh hơn |
| Object owner/ACL | **Vẫn phải kiểm** | **Vẫn phải kiểm** |
| Cache | JWKS/decision theo contract | Active result có stale window |

Không khẳng định “JWT không thể revoke”, cũng không khẳng định introspection tự mang nghĩa revoke tức thì nếu result được cache lâu.

## 15. 401, 403, 404: lỗi phát sinh ở tầng nào?

| Tình huống | Phân loại | HTTP thường phù hợp |
|---|---|---|
| Không có token trên protected API | Unauthenticated | 401/challenge |
| Token sai chữ ký/issuer/aud/exp | Invalid token | 401 |
| Opaque token active=false | Invalid token | 401 |
| Token valid nhưng thiếu scope write | Authorization/insufficient_scope | 403 |
| Scope đúng nhưng object ở tenant khác | Object authorization denial | 403 hoặc 404 chống enumeration |
| Scope và ACL đúng, resource LOCKED | Business state | 403/409 tùy API |
| Introspection/PDP unavailable | Technical error | 5xx/503, không thực thi |

RFC 6750 định nghĩa Bearer challenge và các error codes như `invalid_token`, `insufficient_scope`. Cách map 403/404 ở object denial phụ thuộc disclosure policy của ứng dụng.

Không trả raw JWT claims, tên owner, tenant khác, ACL graph hoặc stack trace để giải thích lỗi cho caller trái quyền. Audit nội bộ có thể lưu reason code/policy version, bảo vệ riêng.

## 16. Token hợp lệ vẫn có thể dẫn đến BOLA/IDOR

JWT hợp lệ:

~~~json
{
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

Document:
~~~text
id=42
tenant=south
owner=binh
shares=[]
~~~

Một endpoint:

~~~java
Document document =
        documentRepository.findById(42L).orElseThrow();
return mapper.toView(document);
~~~

dù được bảo vệ bằng `hasAuthority("SCOPE_documents.read")` vẫn có thể làm lộ tài liệu của Bình nếu không có object policy. Đây là **Broken Object Level Authorization**.

Một công thức đầy đủ hơn:

~~~text
ALLOW_READ =
    verifiedAccessTokenForThisApi
    AND tokenScopeAllowsRead
    AND activeTenantMembership(subject, requestedTenant)
    AND document.tenantId == requestedTenant
    AND (
        document.owner == subject
        OR validShareReadGrant(subject, document)
        OR permittedProjectMembership(subject, document)
    )
    AND resourceStateAllowsRead
~~~

Đừng coi `SCOPE_all` hay `ROLE_ADMIN` là ngoại lệ mở mọi tenant mặc định. Global support/break-glass nếu cần phải định nghĩa scope, authentication, audit và restrictions riêng.

## 17. Query theo ID phải có tenant và ACL/owner

Owner-only SQL:

~~~sql
SELECT d.id, d.title, d.status
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

Có share READ:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.status = 'ACTIVE'
  AND (
      d.owner_subject_key = :verified_subject
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.tenant_id = d.tenant_id
            AND g.document_id = d.id
            AND g.subject_key = :verified_subject
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

ID, tenant và status nằm **ngoài ngoặc OR**. Nếu viết `(id AND tenant AND owner) OR share`, nhánh grant có thể bỏ qua tenant/ID do ưu tiên `AND` cao hơn `OR`.

Tenant và subject phải lấy từ identity/membership đã xác minh, không từ request body/header tự khai. List, count, search, export, file download cũng cần lọc trong query, không chỉ một endpoint detail.

## 18. Multi-issuer: sub phải có namespace

Hai issuers có thể đều phát `sub="123"`:

~~~text
issuerA / sub 123 -> Alice
issuerB / sub 123 -> Bob
~~~

Nếu ACL chỉ lưu `user_id=123`, Bob có thể hưởng quyền Alice. Dùng `(validated issuer, subject)` làm identity key hoặc map sang internal actor ID unique.

Email/name cũng không đảm bảo identity ổn định khi có account linking, đổi email hoặc nhiều IdP. Account linking cần quy trình xác minh và audit, không tự gộp chỉ vì trùng email.

Trong client credentials, `sub`/`client_id` có thể đại diện workload chứ không phải end-user. Policy service account phải khác policy user nếu quyền nghiệp vụ khác.

## 19. Tenant role khác OAuth scope

An:
~~~text
tenant north: EDITOR
tenant south: READER
~~~

JWT custom claim chỉ chứa:

~~~json
{
  "sub": "an",
  "roles": ["EDITOR"]
}
~~~

Nếu converter biến `EDITOR` thành `ROLE_EDITOR` global, request WRITE đến south có thể được cho qua coarse role gate sai scope. Cần:
1. Roles claim scoped theo tenant và được issuer xác minh.
2. Hoặc service tra membership active theo subject + tenant hiện tại.
3. Hoặc token scope cho một tenant, validate tenant với resource.
4. Và luôn check object owner/ACL/status.

Tenant trong path hoặc `X-Tenant-ID` là **target do client chọn**, không chứng minh membership. Issuer không đương nhiên là tenant resource.

## 20. Ví dụ Spring Data JPA service an toàn

Repository owner-only:

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantIdAndOwnerSubjectKey(
            Long id, String tenantId, String ownerSubjectKey);
}
~~~

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final VerifiedActorResolver actors;
    private final DocumentRepository documents;
    private final DocumentMapper mapper;

    public DocumentQueryService(
            VerifiedActorResolver actors,
            DocumentRepository documents,
            DocumentMapper mapper) {
        this.actors = actors;
        this.documents = documents;
        this.mapper = mapper;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public DocumentView read(Long documentId, String requestedTenant) {
        VerifiedActor actor = actors.requireTenantMember(
                requestedTenant, "DOCUMENT_READ");

        Document document = documents
                .findByIdAndTenantIdAndOwnerSubjectKey(
                    documentId, actor.tenantId(), actor.subjectKey())
                .orElseThrow(ResourceNotFoundException::new);
        return mapper.toView(document);
    }
}
~~~

**Mã tích hợp**, cần các domain components, entity và Spring configuration thật. `@EnableMethodSecurity` phải bật; self-invocation có thể bypass proxy method security.

Ranh giới:
- JWT validated trước khi service được gọi.
- `@PreAuthorize` kiểm scope chức năng.
- Resolver lấy issuer/sub từ Authentication đã xác minh và kiểm membership.
- Repository lọc đúng tenant/object.
- Mapper tạo DTO sau khi query có scope.

Khi hỗ trợ share/grant cần dùng query owner OR valid grant, không bỏ object check.

## 21. @PreAuthorize kiểm scope không đủ cho WRITE

Mẫu lỗi:

~~~java
@PreAuthorize("hasAuthority('SCOPE_documents.write')")
public void rename(long documentId, String title) {
    repository.updateTitleById(documentId, title);
}
~~~

JWT đúng và WRITE scope không chứng minh owner/ACL của document ID. API có thể ghi trái quyền.

Mô hình:
~~~text
HTTP    -> verify token + audience + coarse WRITE scope
Service -> verified actor/tenant + role/action + owner/ACL
DB      -> guarded UPDATE/DELETE trên đúng document
Audit   -> authorization decision + mutation execution outcome
~~~

Nếu check owner trước, owner có thể đổi giữa check và use (TOCTOU); guarded mutation hoặc lock/version protocol cần thiết cho action nhạy cảm.

## 22. Guarded UPDATE tại thời điểm mutation

Ví dụ owner-only:

~~~sql
UPDATE documents
SET title = :title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND owner_subject_key = :verified_subject
  AND status = 'ACTIVE'
  AND version = :expected_version;
~~~

Kết quả 0 affected rows → không có record nào thỏa guard, không được trả success giả. Khả năng: ID không tồn tại, sai tenant, không owner, locked, version stale.

Nếu WRITE qua ACL ở bảng khác hoặc remote PDP, owner guard chưa đủ. Cần `EXISTS`/transaction/lock/version/revocation protocol theo consistency contract; `@Transactional` đơn lẻ không tự khóa remote ACL.

**Token được xác minh ở T1 không chứng minh permission chưa đổi ở T2**. Với grant bị revoke, service phải kiểm theo thời điểm action có hiệu lực mà sản phẩm đã định nghĩa.

## 23. Token TTL và quyền hiện thời là hai đồng hồ

~~~text
T0: Access token được phát
     scope=documents.write, exp=T0+15 phút
T1: An được grant WRITE document 42
T2: Admin revoke grant
T3: An dùng token chưa hết hạn
~~~

Ở T3 chữ ký/issuer/aud/exp và scope có thể còn hợp lệ. Nhưng ACL đã bị revoke. Nếu policy yêu cầu quyền cập nhật ngay, object authorization phải DENY.

Phân biệt:
- Expiration của token.
- Revocation của session/refresh token.
- ACL/membership expiry, `revoked_at`.
- Cache ALLOW TTL.
- Policy revision rollout.
- Concurrent transaction state.

Short-lived access tokens giảm cửa sổ, introspection có thể xác minh active status nhanh hơn, nhưng không thay query owner/ACL hoặc chứng minh mọi cache đã được invalidated.

## 24. Client credentials: access token đại diện workload

Client credentials flow thường có token đại diện service/client, không phải một human user. Ví dụ export worker có scope `invoices.export` và aud=billing-api.

API phải kiểm:
- Client/workload identity được xác minh.
- Audience, scope và accepted grant/profile.
- Workload được truy cập tenant nào, tài nguyên nào.
- Hạn mức, mục đích, audit, service identity.
- Các sender constraints (mTLS/DPoP) nếu có.

Không tự hiểu `jwt.getSubject()` là user ID có quyền đối với mọi record. Nếu có token exchange/on-behalf-of, phải verify actor chain và audience; `X-Acting-User` header tự khai không đủ.

## 25. Multi-issuer và trust policy

Với nhiều authorization servers:
- Trusted issuers phải nằm trong allowlist/registry có quản trị.
- Keys, algorithms, issuer và audience gắn với trust profile tương ứng.
- Không chọn arbitrary JWKS URL do token tự yêu cầu.
- Identity key cần namespace issuer+subject.
- Claims roles của issuer A không tự cấp tenant B.
- Không tin `iss` chỉ nhờ decode, phải xác minh trước khi xem nó là identity.

Spring Security Servlet có thể hỗ trợ `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` theo version, còn reactive có counterparts. Không copy Servlet classes sang WebFlux.

## 26. Bearer token là quyền dựa trên possession

Ai cầm Bearer token phù hợp có thể trình bày nó với API trong scope được cấp. Do đó:
- Dùng TLS, hạn chế tokens trong URLs.
- Không log Authorization header, raw JWT, refresh token.
- Bảo vệ token storage khỏi XSS/leak.
- Cấp scope tối thiểu và TTL hợp lý.
- Dùng revocation/session version khi cần.
- Cân nhắc sender-constrained tokens (mTLS/DPoP) cho môi trường thích hợp.
- Không forward token sang service có audience khác; cân nhắc token exchange.

**Token không bị sửa không có nghĩa token không bị đánh cắp.** Và token possession vẫn không tự chứng minh resource owner.

## 27. API gọi downstream: audience phải đúng từng nơi

Service A nhận token `aud=api-a`. Khi gọi service B, nếu token chỉ dành cho A thì B phải từ chối ngay cả khi signature đúng.

Sai:
~~~text
API A receives valid aud=api-a
   -> forwards original access token to API B
API B validates signature but ignores aud
   -> accepts and accesses resource
~~~

Giải pháp: token exchange/OBO cho aud=api-b, client credentials cho B theo scope riêng, hoặc trusted identity propagation với validation và audit. Spring helper truyền Bearer token không tự bảo đảm consent/audience.

## 28. Token thiếu thuộc tính: không được suy đoán ALLOW

Token có thể chỉ gồm issuer, subject, audience và read scope, **không có**:
- Tenant membership hiện thời.
- Owner/ACL/group permission.
- Resource classification/status.
- Subscription/limit/expiry nghiệp vụ.

Khi thiếu, Resource Server có thể tra DB/PIP/PDP tin cậy hoặc dùng embedded entitlement có version/expiry theo thiết kế. Khi backend permission lỗi thì phải fail-closed, không cho truy cập “tạm” chỉ vì token có scope.

Tránh SQL optional guard:

~~~sql
WHERE id=:id
  AND (:tenant IS NULL OR tenant_id=:tenant)
~~~

Vì tenant null có thể làm predicate bỏ kiểm tenant. Với object authorization, thiếu tenant là denial/error, không phải “mở rộng tìm kiếm”.

## 29. Decision tree cho READ document

~~~text
GET /api/tenants/north/documents/42
          |
          v
Access token validated for documents-api?
 no -> 401
 yes
          |
          v
Has SCOPE_documents.read?
 no -> 403
 yes
          |
          v
Active tenant membership in north?
 no -> deny
 yes
          |
          v
Document belongs to north and owner/share READ permits?
 no -> 403/404
 yes
          |
          v
State and field classification permit READ?
 no -> deny
 yes
          |
          v
Return allowed DTO, not arbitrary entity fields
~~~

List/search/export/download cũng phải scope đúng query và field projection. Một scope READ không tự cho phép xem salary/secret fields nếu object policy yêu cầu lọc riêng.

## 30. Java 17 độc lập: token hợp lệ chưa chắc được truy cập

Ví dụ sau **chạy bằng JDK 17**, không cần Spring. `ValidatedToken` đại diện token **đã được tầng xác thực đáng tin kiểm chữ ký/claims**; demo chỉ mô phỏng kết quả xác minh, không tự cài thuật toán JWT.

Tạo file `TokenAccessBoundaryDemo.java`:

~~~java
import java.util.Set;

public class TokenAccessBoundaryDemo {
    enum Action { READ, WRITE }

    record ValidatedToken(
            boolean signatureAndClaimsValid,
            String issuer,
            String subject,
            String audience,
            Set<String> scopes) { }

    record Document(
            long id, String tenant, String ownerKey, boolean locked) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    static boolean tokenAccepted(
            ValidatedToken token, String audience) {
        return token != null
                && token.signatureAndClaimsValid()
                && token.issuer() != null
                && !token.issuer().isBlank()
                && token.subject() != null
                && !token.subject().isBlank()
                && audience.equals(token.audience())
                && token.scopes() != null;
    }

    static boolean scopeAllows(ValidatedToken token, Action action) {
        String needed = action == Action.READ
                ? "documents.read" : "documents.write";
        return token.scopes().contains(needed);
    }

    static String authorize(
            ValidatedToken token,
            String requestedTenant,
            Document document,
            Action action,
            Set<Grant> grants,
            Set<String> activeMemberships) {

        if (!tokenAccepted(token, "documents-api")) {
            return "INVALID_TOKEN";
        }
        if (action == null || !scopeAllows(token, action)) {
            return "INSUFFICIENT_SCOPE";
        }

        String subjectKey = token.issuer() + "|" + token.subject();
        if (requestedTenant == null || requestedTenant.isBlank()
                || document == null || document.id() <= 0
                || grants == null || activeMemberships == null
                || !requestedTenant.equals(document.tenant())
                || !activeMemberships.contains(
                    requestedTenant + "|" + subjectKey)) {
            return "DENIED_RESOURCE_SCOPE";
        }

        if (document.locked() && action == Action.WRITE) {
            return "DENIED_RESOURCE_STATE";
        }

        boolean owner = subjectKey.equals(document.ownerKey());
        boolean grant = grants.contains(new Grant(
                document.tenant(), document.id(), subjectKey, action));
        return owner || grant
                ? "ALLOW" : "DENIED_OBJECT_PERMISSION";
    }

    public static void main(String[] args) {
        ValidatedToken an = new ValidatedToken(
                true, "issuerA", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken wrongAudience = new ValidatedToken(
                true, "issuerA", "an", "payments-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken readOnly = new ValidatedToken(
                true, "issuerA", "an", "documents-api",
                Set.of("documents.read"));

        ValidatedToken badSignature = new ValidatedToken(
                false, "issuerA", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        ValidatedToken otherIssuer = new ValidatedToken(
                true, "issuerB", "an", "documents-api",
                Set.of("documents.read", "documents.write"));

        Document ownerDoc =
                new Document(42, "north", "issuerA|an", false);
        Document sharedDoc =
                new Document(43, "north", "issuerA|binh", false);
        Document southDoc =
                new Document(42, "south", "issuerA|an", false);
        Document lockedDoc =
                new Document(44, "north", "issuerA|an", true);

        Set<String> members = Set.of(
                "north|issuerA|an", "north|issuerB|an");
        Set<Grant> grants = Set.of(
                new Grant("north", 43, "issuerA|an", Action.READ));

        System.out.println("owner-read=" + authorize(
                an, "north", ownerDoc, Action.READ, grants, members));
        System.out.println("shared-read=" + authorize(
                an, "north", sharedDoc, Action.READ, grants, members));
        System.out.println("shared-write=" + authorize(
                an, "north", sharedDoc, Action.WRITE, grants, members));
        System.out.println("wrong-audience=" + authorize(
                wrongAudience, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("read-scope-write=" + authorize(
                readOnly, "north", ownerDoc, Action.WRITE, grants, members));
        System.out.println("bad-signature=" + authorize(
                badSignature, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("cross-tenant=" + authorize(
                an, "north", southDoc, Action.READ, grants, members));
        System.out.println("same-sub-other-issuer=" + authorize(
                otherIssuer, "north", ownerDoc,
                Action.READ, grants, members));
        System.out.println("locked-write=" + authorize(
                an, "north", lockedDoc, Action.WRITE, grants, members));
        System.out.println("revoked-membership=" + authorize(
                an, "north", ownerDoc, Action.READ, grants, Set.of()));
    }
}
~~~

Chạy:

~~~bash
javac TokenAccessBoundaryDemo.java
java TokenAccessBoundaryDemo
~~~

Stdout chính xác:

~~~text
owner-read=ALLOW
shared-read=ALLOW
shared-write=DENIED_OBJECT_PERMISSION
wrong-audience=INVALID_TOKEN
read-scope-write=INSUFFICIENT_SCOPE
bad-signature=INVALID_TOKEN
cross-tenant=DENIED_RESOURCE_SCOPE
same-sub-other-issuer=DENIED_OBJECT_PERMISSION
locked-write=DENIED_RESOURCE_STATE
revoked-membership=DENIED_RESOURCE_SCOPE
~~~

Kết quả cho thấy:
1. Token có chữ ký/claims hợp lệ, aud đúng, READ scope + membership + owner → ALLOW.
2. READ grant cho document 43 không cho WRITE.
3. Wrong audience và bad signature đều bị chặn tại token gate.
4. READ-only token không được WRITE ngay cả khi là owner.
5. Sai tenant, khác issuer dù trùng `sub`, locked resource và revoked membership đều từ chối độc lập với validity của token.

**Giới hạn:** Boolean `signatureAndClaimsValid` chỉ là fixture mô phỏng đã được tầng xác thực xác minh; tuyệt đối không nhận boolean này từ client. Demo không implement signature/exp/nbf/JWKS/introspection, không mô phỏng DB concurrency. Dùng Spring Security JwtDecoder/introspection thật trong ứng dụng.

## 31. Spring Security Test: mock JWT không chứng minh chữ ký được verify

Spring Security Test hỗ trợ `jwt()` cho MockMvc. Ví dụ:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentsScopeTests {
    @Autowired
    MockMvc mvc;

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/42")
                  .with(jwt().authorities()))
           .andExpect(org.springframework.test.web.servlet.result
                   .MockMvcResultMatchers.status().isForbidden());
    }
}
~~~

**Snippet Spring Test** cần imports được đặt trên các dòng hợp lệ trong file Java, MockMvc, Security Test, endpoint và filter chain thật. Test helper có thể inject Authentication mà không verify chữ ký của raw Bearer JWT; vì vậy chỉ dùng để test scope/authorization policy, không dùng làm bằng chứng signature/issuer/audience validation.

Test validation thật bằng bearer request qua configured decoder với test issuer/JWKS/keys:
- Signature sai và thuật toán không cho phép.
- Issuer/audience sai.
- Expired/nbf tương lai, loại token không đúng.
- Key rotation, `kid` không thuộc trust store.
- Introspection `active=false` và backend unavailable.
- Scope conversion, audience và resource-specific authorization tích hợp.

## 32. Ma trận test hai ranh giới

| Token/permission | Token accepted? | Scope gate? | Object policy? | Kết quả |
|---|---|---|---|---|
| JWT đúng aud, READ scope, owner | PASS | PASS | PASS | ALLOW |
| JWT có chữ ký đúng, aud API khác | FAIL | Không xét | Không xét | 401 |
| JWT signature invalid | FAIL | Không xét | Không xét | 401 |
| JWT expired | FAIL | Không xét | Không xét | 401 |
| OIDC ID token aud frontend | FAIL | Không xét | Không xét | 401 |
| JWT hợp lệ thiếu WRITE scope | PASS | FAIL | Không xét | 403 |
| JWT WRITE scope nhưng object của người khác | PASS | PASS | FAIL | 403/404 |
| JWT admin north truy cập document south | PASS | Coarse có thể PASS | FAIL | DENY |
| JWT có READ scope, ACL revoked | PASS | PASS | FAIL | DENY |
| JWT có READ scope, membership revoked | PASS | PASS | FAIL | DENY |
| JWT WRITE scope, document locked | PASS | PASS | FAIL | DENY/conflict |
| Opaque active=false | FAIL | Không xét | Không xét | 401 |
| Opaque active=true, thiếu scope | PASS nếu checks khác đạt | FAIL | Không xét | 403 |
| Introspection timeout | Không xác minh được | Không xét | Không xét | Fail closed |
| Hai issuer trùng sub | PASS nếu issuer tin | Tùy | Namespace | Không nhầm owner |
| Client credentials token | PASS nếu profile hợp lệ | Tùy | Workload policy | Không mặc định user owner |
| Trùng local document ID ở hai tenant | PASS | Có thể PASS | Tenant guard | Không rò dữ liệu |
| aud=api-a gửi đến API-B | FAIL tại B | Không xét | Không xét | 401 |
| Permission backend outage | PASS | Có thể PASS | Không xác minh được | Không side effect |

Bên cạnh HTTP response cần assert database state/outbox/file unchanged sau denied. Một kết quả 403 không đủ nếu service đã ghi DB rồi mới từ chối.

## 33. Debug lỗi theo đúng tầng

- **401 khi đổi issuer:** kiểm `issuer-uri` và trusted keys, không tự bật `permitAll`.
- **401 chỉ ở service B:** kiểm aud token có dành cho B không, không thêm role.
- **401 vì token expired:** client dùng refresh/re-login theo flow an toàn.
- **403 vì thiếu `SCOPE_...`:** kiểm token scope và converter, không tự gán ADMIN.
- **403/404 vì object ACL:** kiểm tenant/owner/grant, không blame JWT.
- **409 vì version stale:** concurrency, không phải authentication.
- **503 vì introspection timeout:** fail closed, không cho token “active mặc định”.

Không log raw JWT để debug; dùng reason codes an toàn, correlation ID và policy revision. Đừng trả tên tenant/owner thật cho caller ngoài quyền.

## 34. JWT trong cookie: lưu ý CSRF và browser

JWT truyền qua explicit Bearer header và JWT lưu trong cookie tự động gửi có threat model khác:
- Bearer-only stateless API, frontend chủ động gửi header, không có cookie/session fallback: CSRF có thể không áp theo cách giống cookie auth.
- JWT/session trong cookie, refresh-cookie endpoints hoặc HTTP Basic browser-managed credentials: CSRF vẫn có thể là rủi ro.
- CORS allowlist không thay CSRF/authentication/object authorization.

Đừng mặc định tắt CSRF chỉ vì token là JWT. Cách browser gửi credential quan trọng hơn định dạng token.

## 35. Logging, privacy và error disclosure

Không ghi:
- Raw access/refresh/ID tokens.
- Cookie/session, Authorization header, signed URL.
- Introspection client secret, private keys.
- Full token claims/ACL chứa PII không cần thiết.
- Owner/tenant ngoài quyền của caller.
- Exceptions chứa internal URLs hoặc credentials trong response.

Có thể lưu mã phân loại:
- `AUTHN_INVALID_AUDIENCE` / `AUTHN_EXPIRED_TOKEN`.
- `AUTHZ_INSUFFICIENT_SCOPE` / `AUTHZ_RESOURCE_DENIED`.
- Policy revision, request/decision ID, masked actor/tenant alias.
- Enforcement outcome và commit/rollback.

Audit store là dữ liệu nhạy cảm; người dùng support xem audit cần quyền riêng theo tenant/case, không chỉ biết request ID.

## 36. Các sai lầm thường gặp

**1. Base64 decode JWT rồi tin claims.** Chưa verify. Dùng JwtDecoder/introspection.

**2. Chỉ verify chữ ký, bỏ audience.** Token API khác được nhận sai. Kiểm aud.

**3. Dùng OIDC ID token gọi API.** Sai mục đích. Kiểm type/audience.

**4. Nghĩ `authenticated()` nghĩa là mọi endpoint được phép.** Cần scope/role/action.

**5. Nghĩ `SCOPE_documents.read` cho đọc mọi ID.** BOLA. Cần owner/ACL/tenant.

**6. Dùng `hasRole("documents.read")` cho OAuth scope.** Sai prefix. Dùng SCOPE_ authority.

**7. Custom roles claim tự động thành ROLE_.** Cần converter chính xác.

**8. Role ADMIN tenant A thành quyền global ở B.** Cần tenant-scoped policy.

**9. Dùng sub không có issuer namespace.** Identity collision.

**10. Dùng `findById` không scoped rồi trả DTO.** Thiếu object check.

**11. `@PreAuthorize` rồi UPDATE ID trần.** TOCTOU/IDOR.

**12. JWT còn hạn nên bỏ revoked ACL.** Token TTL khác permission freshness.

**13. Introspection timeout rồi assume active.** Fail-open.

**14. Client credentials token coi như end-user token.** Nhầm workload identity.

**15. Forward aud=api-a token vào API-B.** Token substitution.

**16. Test `jwt()` mock rồi kết luận token crypto hoạt động.** Mock không thay real decoder.

**17. Log Bearer token để debug.** Rò credential/replay.

**18. Bật `permitAll` để sửa 403.** Sửa sai tầng và mở quyền.

## 37. Checklist triển khai Resource Server

- [ ] Phân biệt access token, ID token và refresh token.
- [ ] Token được validate bằng decoder/introspection đáng tin, không parse claims raw.
- [ ] Kiểm signature/key/algorithm, iss, aud, exp, nbf và token type/profile.
- [ ] Issuer/JWKS trust allowlist rõ, không tải arbitrary URL từ JWT header.
- [ ] Scope/custom roles mapping chính xác thành authorities.
- [ ] HTTP methods/action có yêu cầu scope phù hợp, fallback deny.
- [ ] Multi-tenant role không bị gộp thành global admin.
- [ ] Tenant và subject key được xác minh từ Authentication/membership.
- [ ] Resource ID+tenant+owner/ACL/status lấy từ nguồn server.
- [ ] List/count/export/download cũng áp query-time scope.
- [ ] WRITE/DELETE có guarded operation, version/lock/revocation protocol.
- [ ] Client credentials/workload tokens có policy riêng.
- [ ] Downstream API validate audience của chính nó.
- [ ] Introspection timeout/active=false và PDP error fail closed.
- [ ] Token/session/ACL revocation có hiệu lực và SLA được xác định.
- [ ] Error 401/403/404/5xx không leak token, owner hoặc tenant.
- [ ] Test token validators bằng issuer/test keys, không chỉ mock jwt().
- [ ] Test wrong audience, expired, scope missing, cross-tenant, ACL revoked.
- [ ] Denied request không mutate DB, file hay queue.
- [ ] Đối chiếu Spring Security API/typ validators khi nâng version.

**Kết luận:** Xác minh token trả lời **“credential này có đáng tin và dành cho API này không?”**; phân quyền trả lời **“actor/client đã được xác minh có được làm hành động này trên đúng tài nguyên, tenant và trạng thái hiện tại không?”**. Hai ranh giới phải tách biệt. Token hợp lệ không tự bảo đảm quyền đối tượng; scope không thay owner/ACL checks; chữ ký không thay revocation. Sự kết hợp của audience validation, tenant/object scoping, guarded mutations, fail-closed và kiểm thử cả hai tầng mới giúp Resource Server an toàn.

## Tài liệu tham khảo

- [Spring Security — Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature, issuer, audience và scope mapping.
- [Spring Security — Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, active status, revocation.
- [Spring Security — Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và WebFlux.
- [Spring Security — Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): Bearer credential và downstream propagation.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và method authorization.
- [Spring Security — OAuth2 Migration](https://docs.spring.io/spring-security/reference/migration/servlet/oauth2.html): typ validation thay đổi theo version.
- [RFC 6750 — Bearer Token Usage](https://datatracker.ietf.org/doc/html/rfc6750): Bearer errors, challenges và security.
- [RFC 7662 — Token Introspection](https://datatracker.ietf.org/doc/html/rfc7662): active status và metadata.
- [RFC 9068 — JWT Profile for Access Tokens](https://datatracker.ietf.org/doc/html/rfc9068): access token type, issuer, audience.
- [RFC 8725 — JWT Best Current Practices](https://datatracker.ietf.org/doc/html/rfc8725): algorithms, audience và token confusion.
- [OWASP API Security Top 10 — BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object-level checks.
