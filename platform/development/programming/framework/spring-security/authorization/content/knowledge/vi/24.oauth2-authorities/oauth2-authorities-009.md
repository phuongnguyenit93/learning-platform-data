# Không tin claim do client tự gửi hoặc token chưa được xác minh

## 1. Vấn đề cốt lõi: một chuỗi nói “admin” không làm người gọi thành admin

Ứng dụng Spring Security nhận một request:

~~~http
PATCH /api/tenants/finance/documents/42
Authorization: Bearer <access-token>
X-User-Id: ceo
X-Role: ADMIN
X-Tenant-Id: finance
Content-Type: application/json

{
  "ownerId": "ceo",
  "roles": ["ADMIN"],
  "approved": true,
  "title": "New title"
}
~~~

Kẻ gọi có thể sửa bất kỳ giá trị nào trong phần **URL, headers và body do họ kiểm soát**. Các chuỗi `ceo`, `ADMIN`, `finance` hoặc `approved=true` chỉ là **lời khai**, không phải bằng chứng. Một JWT mà client đính kèm cũng chưa đáng tin cho tới khi Resource Server thực sự xác minh chữ ký hoặc introspection, issuer, audience, thời hạn, loại token và các điều kiện ứng dụng.

Quy tắc quan trọng nhất:

> **Không tạo principal, role, tenant membership hay quyết định ALLOW từ claim do client tự gửi hoặc nội dung token chưa được xác minh.** Chỉ dùng danh tính đã xác thực, dữ liệu quyền từ nguồn đáng tin và thuộc tính resource đọc ở server để quyết định action thực tế.

Bài học thuộc nhóm **Quyền từ OAuth2**; trọng tâm là trust boundary giữa browser/client, OAuth2 Authorization Server, Spring Security Resource Server và domain authorization. Kể cả JWT đã được ký hợp lệ, API vẫn phải kiểm owner/ACL/tenant của đối tượng mà caller muốn truy cập.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:
- Phân biệt **claim**, **bằng chứng xác thực** và **quyết định quyền**.
- Phát hiện privilege escalation khi lấy `role`/`isAdmin` từ HTTP request.
- Hiểu vì sao Base64URL decode JWT không phải chữ ký verification.
- Cấu hình Spring Security JWT Resource Server với issuer, audience, thời gian và signing-key trust.
- Hiểu các nguy cơ `alg=none`, algorithm confusion, `kid`/`jku` và token-type confusion.
- Chuyển **claims đã xác minh** thành `GrantedAuthority` mà không biến role tenant A thành quyền toàn cục ở tenant B.
- Phân biệt OAuth2 access token với OIDC ID token, opaque token và client-credentials workload identity.
- Thiết kế resolver actor/tenant và query-time owner/ACL checks.
- Bảo vệ trust boundary khi sử dụng gateway, reverse proxy, background jobs hoặc microservices.
- Kiểm thử cả JWT decoder thật và HTTP/resource authorization, không nhầm mocks với cryptographic verification.
- Xử lý missing/invalid claims theo nguyên tắc **fail closed**.

## 3. Bảng phân loại nguồn dữ liệu theo độ tin cậy

| Dữ liệu | Nguồn | Có thể dùng trực tiếp để ALLOW? |
|---|---|---|
| `userId` từ JSON body | Caller tự viết | **Không** |
| `X-Role: ADMIN` | Header tự gửi | **Không** |
| `tenantId` trong path | Tenant caller yêu cầu | **Không**, phải xác minh membership |
| `isOwner=true` trong form | Caller tự khai | **Không** |
| Nội dung JWT sau Base64URL decode | Token chưa verify | **Không** |
| `iss`/`sub` đọc từ JWT header/payload chưa verify | Chuỗi chưa đáng tin | **Không** |
| `Jwt` do Resource Server decoder đã xác minh và converter tạo | Authentication pipeline đáng tin | **Đầu vào tin cậy**, chưa tự là quyền object |
| `Authentication.getAuthorities()` do provider tin cậy tạo | Verified authentication context | **Có thể kiểm coarse action**, chưa đủ cho ACL/tenant nếu thiếu scope |
| Tenant membership từ DB có kiểm soát | Trusted PIP/repository | Có thể dùng theo policy/freshness |
| Resource owner/tenant/status từ DB | Trusted resource data | Có thể dùng sau khi gắn đúng resource/transaction |
| Claim trong token từ issuer đã tin nhưng stale | Bằng chứng có thời hạn | Cần xem lại revocation/freshness |
| Header từ reverse proxy được bảo vệ bằng trust boundary | Gateway có xác thực và loại header giả | Chỉ trong contract xác minh chặt |
| Correlation ID do client gửi | Metadata vận hành | Không bao giờ là entitlement |

**Claim không tự xấu**: claim là dữ liệu về subject/token. Giá trị claim chỉ có cấp độ tin cậy phù hợp sau khi cơ chế truyền/issuer/validator được kiểm và sau đó **được diễn giải đúng ngữ nghĩa**. Claim `scope=documents.read` có thể chứng minh token được cấp scope chức năng, nhưng không chứng minh người gọi sở hữu Document #42.

## 4. Threat model: attacker kiểm soát được phần nào?

Giả định attacker có thể:
1. Gửi HTTP request bất kỳ, thay URL/path/query/body/headers.
2. Tự tạo một chuỗi có ba phần trông như JWT rồi Base64URL-encode claims mong muốn.
3. Thay phần payload của JWT đã ký mà không có signing key.
4. Dùng JWT **thật** nhưng dành cho API khác hoặc thuộc issuer khác.
5. Dùng ID token của OIDC client thay access token.
6. Phát lại access token bị đánh cắp hoặc hết quyền nhưng chưa expired.
7. Thử request đến nhiều document IDs/tenant IDs.
8. Tạo header giống header mà gateway nội bộ thường thêm.
9. Gửi chuỗi `kid`/`jku` độc hại trong token header.
10. Dùng role claim được cấp cho tenant A để thử truy cập tenant B.

Mục tiêu phòng thủ là giữ một đường duy nhất từ **credential verification** đến **trusted principal**, rồi kiểm quyền trên **đúng action–resource–tenant**. Không cho request tự viết các trường “đã được xác minh”.

### Ví dụ tấn công trực tiếp

~~~http
POST /api/users/promote
Authorization: Bearer <regular-user-token>
Content-Type: application/json

{
  "targetUserId": "attacker",
  "role": "SUPER_ADMIN",
  "performedBy": "security-admin",
  "approved": true
}
~~~

Server chỉ được hiểu `role=SUPER_ADMIN` là **thay đổi được yêu cầu**, không phải quyền phê duyệt thay đổi. Người thực hiện phải lấy từ Authentication đã verify; quyền `ROLE_SECURITY_ADMIN`, MFA/approval/tenant policy phải được kiểm server-side.

## 5. JWT gồm header, payload và signature nhưng decode không phải verify

Một JWS compact JWT thường có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Header/payload có thể được decode bằng Base64URL **không cần biết secret hoặc public key**. Do đó:
- Đọc `sub`, `roles` hoặc `scope` bằng cách decode chỉ tạo ra **chuỗi chưa đáng tin**.
- Người gửi có thể thay JSON rồi encode lại mà không có signature hợp lệ.
- Bước bắt buộc là verify signature theo thuật toán/key đáng tin **và** kiểm claims/profile cho API.
- JWT dạng JWE có mã hóa và cấu trúc khác; encrypted không tự có nghĩa “đã có quyền”. Cần xác thực/decrypt theo profile rồi vẫn authorize.

Ví dụ payload giả mạo:

~~~json
{
  "iss": "https://idp.example.test",
  "sub": "admin",
  "aud": "documents-api",
  "scope": "documents.read documents.write",
  "roles": ["SUPER_ADMIN"]
}
~~~

Nếu Spring application tạo `UsernamePasswordAuthenticationToken` chỉ bằng payload raw, attacker có thể thành admin. Hãy để `JwtDecoder` hoặc introspection implementation trong Spring Security tạo nguồn identity sau validation, không tự dựng principal từ một JWT string do user đính kèm.

### Dạng code sai cần nhận diện

~~~java
// SAI: không có chữ ký/issuer/audience/time verification.
String[] sections = bearerToken.split("\\.");
String json = new String(
        java.util.Base64.getUrlDecoder().decode(sections[1]),
        java.nio.charset.StandardCharsets.UTF_8);
// Tạo role từ json ở đây là privilege escalation.
~~~

Đây là **anti-pattern minh họa**, không phải code nên chạy trong production. Parser có thể crash khi token malformed; tệ hơn là chấp nhận claims giả nếu dựa vào decode.

## 6. Có chữ ký hợp lệ vẫn chưa chắc token đáng tin cho API này

Một Resource Server có thể verify signature mà vẫn sai:
- Public key thuộc issuer **không** nằm trong trust registry.
- Token có `aud=payments-api` nhưng được gửi tới `documents-api`.
- `exp` đã hết hoặc `nbf` còn ở tương lai.
- JWT là OIDC ID token dành cho frontend client.
- Token dùng thuật toán không được API cho phép.
- Token không thỏa loại token/profile đang áp dụng.
- Token bị revoke theo contract.
- Token đại diện **client credentials**, không có human user.
- Scope/token role được ký đúng nhưng đã hết hiệu lực nghiệp vụ do ACL hoặc membership bị thu hồi.

Vì vậy cần hai lớp rõ:

~~~text
TOKEN ACCEPTED =
  trusted issuer/key
  AND permitted cryptographic algorithm
  AND valid signature/active status
  AND valid exp/nbf and required temporal rules
  AND expected audience and token type/profile
  AND required token schema

ALLOW ACTION =
  TOKEN ACCEPTED
  AND action permission/scope
  AND verified subject or client identity
  AND verified tenant membership
  AND resource policy (owner/ACL/status)
  AND current business constraints
~~~

Không rút gọn công thức thứ hai thành `TOKEN ACCEPTED` hoặc `scope.contains("admin")`.

## 7. Cấu hình thuật toán: không tin "alg" do token tự chỉ định

Header JWT có thể ghi:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

hoặc một signing algorithm không thuộc allowlist ứng dụng. Các lỗ hổng lịch sử gồm:
- `alg=none` và thư viện không verify signature.
- Nhầm `RS256` với `HS256` rồi dùng RSA public key như HMAC secret.
- Cho token tự điều khiển algorithm thay vì server cấu hình trust.
- Dùng một key cho nhiều algorithm không đúng profile.

Theo **RFC 8725 JSON Web Token Best Current Practices**, library/application phải giới hạn thuật toán hỗ trợ và đối chiếu algorithm thực thi với header đã khai, không chấp nhận thuật toán bất kỳ do token đề xuất.

Với Spring Security, cấu hình `NimbusJwtDecoder`/`NimbusReactiveJwtDecoder` để tin đúng issuer/JWKS và algorithms phù hợp. Kiểm thử bằng token ký khác thuật toán dự kiến; request phải bị từ chối. Không tự hiện thực JWS verification bằng regex hoặc so chuỗi.

## 8. kid, jku, x5u: header không đáng tin có thể gây SSRF/injection

JWT header còn có các trường:
- `kid`: key ID dùng để chọn key.
- `jku`: URL của JWK Set.
- `x5u`: URL certificate chain.

**Không** lấy trực tiếp `jku`/`x5u` do caller gửi rồi yêu cầu server tải public key từ URL đó. Attacker có thể chỉ tới host do họ kiểm soát hoặc địa chỉ nội bộ (**SSRF**) và khiến API verify token bằng key của attacker.

Đúng hơn:
1. Khai trusted issuer và JWK Set URI/metadata từ cấu hình tin cậy.
2. Chỉ chọn `kid` trong bộ keys gắn với issuer đã được cho phép.
3. Cấu hình allowlist algorithm và thời hạn cache/key rotation.
4. Không cho token điều khiển arbitrary outbound network requests.
5. Sanitize/giới hạn `kid` nếu đi vào log, query hoặc cache key.
6. Test `kid` bất thường, JWKS không có key, keys rotated và issuer unreachable.

RFC 8725 có mục **Do Not Trust Received Claims**, đặc biệt cảnh báo `kid` injection và `jku/x5u` SSRF. Một token header có thể hữu ích cho trình xác minh, nhưng **chưa phải trusted configuration**.

## 9. iss, aud, exp, nbf, typ phải được kiểm theo contract

| Field | Ý nghĩa | Sai lầm |
|---|---|---|
| `iss` | Issuer phát token | Chỉ đọc string rồi coi issuer trusted |
| `aud` | Recipient/API dự kiến | Token API A dùng ở API B |
| `exp` | Expiration time | Cho token hết hạn |
| `nbf` | Not-before time | Chấp nhận trước thời điểm hiệu lực |
| `iat` | Issued-at, dùng khi policy cần | Không phát hiện token quá cũ |
| `typ` | JWT kind/profile | Dùng ID token thay access token |
| `sub` | Subject theo issuer | Va chạm giữa các issuers |
| `scope`/`scp` | OAuth2 permissions | Nhầm scope với object ownership |
| `azp`/`client_id` | Authorized party/client theo profile | Giả định mọi token có human user |
| `jti` | Token identifier nếu issuer dùng | Nghĩ jti tự chống replay nếu không kiểm |

Token profile thực tế quyết định field nào bắt buộc. Ví dụ **RFC 9068 JWT Access Token Profile** yêu cầu loại access token và các field theo profile. Không phải mọi access token đều có định dạng JWT, và không phải mọi JWT đều tuân RFC 9068.

**Audience rất quan trọng:** nếu một issuer phát tokens cho nhiều APIs, RS phải xác minh `aud` chứa đúng API của mình. Không có aud hoặc aud sai → từ chối token ngay cả khi signature đúng.

## 10. Access token khác OIDC ID token và refresh token

| Token | Mục đích | Không dùng làm |
|---|---|---|
| **OAuth2 access token** | Gọi Resource Server có audience phù hợp | Giấy phép vượt ACL của mọi object |
| **OIDC ID token** | Chứng minh sự kiện user authentication cho OAuth client | Bearer access token cho API |
| **Refresh token** | Xin access token mới qua Authorization Server | Token gọi resource endpoint |

OIDC ID token và JWT access token có thể có `iss`, `sub` và chữ ký tương tự. Nhưng `aud` thường khác. API không nên kiểm “token là JWT hợp lệ” rồi chấp nhận ID token của SPA. Cần accepted token profile riêng.

Client credentials token có thể xác thực **service client**, không phải user. Nếu code đọc `sub` rồi luôn tạo một “human user” không có kiểm, có nguy cơ gán nhầm quyền dữ liệu.

## 11. Spring Security Resource Server là điểm bắt đầu đáng tin

Trong Spring Servlet, ví dụ:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentsSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .requestMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

**Spring integration snippet**: cần Spring Security Resource Server/Jose dependencies, JWT decoder/issuer, controllers, CSRF/session policy phù hợp. Không phải Java 17 standalone.

Security pipeline lấy Bearer credential, dùng trusted decoder, tạo `JwtAuthenticationToken`/Authentication và kiểm authorities. Không tự xử lý request header `X-User-Id` hoặc tự decode JWT trong controller để xác định người gọi.

Cấu hình Spring Boot có thể bắt đầu với:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
~~~

URI là ví dụ. Default decoder thường validate signature/timestamps/issuer và map scopes; **application-specific audience/token-type rules phải được kiểm theo cấu hình/version**. Đừng kết luận mọi validator đã bật chỉ vì app khởi động thành công.

## 12. Cấu hình audience validator và giữ default validators

Một ví dụ Spring Security Servlet:

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
                            "Audience not accepted", null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults, audienceRequired));
        return decoder;
    }
}
~~~

Properties:

~~~yaml
app:
  security:
    issuer: https://idp.example.test/issuer
    audience: documents-api
~~~

Đây là **code tích hợp**, issuer/audience phải đến từ trusted server config, **không lấy từ HTTP header hoặc payload token chưa verified**. Việc dùng `JwtValidators.createDefaultWithIssuer(issuer)` rồi bổ sung audience tránh lỗi thay hẳn validators nền bằng một predicate aud-only.

Nếu hệ sử dụng RFC 9068, kiểm thêm accepted `typ`/access-token profile theo Spring Security version. Spring Security 6.5 và 7.x có khác biệt API liên quan token-type handling; đối chiếu Javadoc/dependency đang chạy, không tự tắt validation để xử lý một token từ issuer sai profile.

## 13. JwtAuthenticationConverter: ánh xạ claim sau xác minh, không trước

Spring Security thường biến `scope` hoặc `scp` thành `GrantedAuthority` có prefix `SCOPE_`. Ví dụ token hợp lệ chứa:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

Sau validation, Authentication có thể có:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Từ đó `hasAuthority("SCOPE_documents.read")` phù hợp; `hasRole("documents.read")` lại kiểm `ROLE_documents.read`, không đúng. Không biến raw client JSON `roles:["ADMIN"]` thành GrantedAuthority.

Nếu issuer có custom authority claim, có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorityConverter =
            new JwtGrantedAuthoritiesConverter();
    authorityConverter.setAuthoritiesClaimName("scope");
    authorityConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authorityConverter);
    return converter;
}
~~~

**Snippet tích hợp**, ghép qua `oauth2ResourceServer(...jwt(jwt -> jwt.jwtAuthenticationConverter(...)))` hoặc configuration tương ứng. Nó chỉ ánh xạ claims **đã được issuer xác minh** thành authorities, chưa quyết định object ownership.

Một claim có chữ ký hợp lệ vẫn có thể **hết freshness**: role hoặc group membership có thể đã thay đổi sau khi token phát. Quyền cần revoke nhanh nên tra current membership/ACL hoặc dùng authz revision/TTL rõ.

## 14. Header/body "isAdmin" là dữ liệu được yêu cầu, không phải bằng chứng

Mẫu code nguy hiểm:

~~~java
@PostMapping("/documents/{id}/share")
public void share(@PathVariable long id,
                  @RequestBody ShareRequest request) {
    if (request.isAdmin()) {
        grants.shareWithEveryone(id);
    }
}
~~~

Nếu `isAdmin` do caller truyền, caller chỉ cần đổi JSON thành true.

Một request model nên mô tả **điều người dùng muốn làm**, ví dụ:
~~~java
public record ShareRequest(
        String targetUserId, String permission) { }
~~~

Code server lấy actor từ Authentication đã được Spring xác minh, xác định requested action SHARE và kiểm quyền owner/tenant/service policy trước khi tạo grant. Không cho client chỉ định `performedBy`, `ownerId` hay `approved=true` rồi xem là permission proof.

Một owner field trong create request đôi khi được business cho phép chọn (ví dụ tạo tài liệu thay mặt team). Dù vậy nó chỉ là **giá trị đề nghị**, cần policy approve/delegation; không phải claim quyền đang có.

## 15. Authentication từ Spring: đọc đúng nguồn, đúng thời điểm

Với Spring MVC Resource Server, sau khi security filter chain xác minh JWT, một handler có thể lấy Jwt principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MyIdentityController {

    @GetMapping("/api/me")
    String me(@AuthenticationPrincipal Jwt jwt) {
        return jwt.getIssuer().toString() + "|" + jwt.getSubject();
    }
}
~~~

**Snippet tích hợp**: chỉ dùng trên route đã được bảo vệ bằng resource server; kiểm null/issuer theo token profile. Trả subject/issuer cho chính caller ở `/api/me` có thể hợp lý, nhưng không trả toàn bộ token claims/secret trong public response.

Điểm quan trọng: `Jwt` nhận qua Spring-authenticated principal có nguồn từ **đường xác minh**. Ngược lại, một đoạn code tự `new Jwt(...)` từ request body không tự biến token thành đáng tin. Type Java giống nhau không thay trust provenance.

Khi dùng service, ưu tiên nhận `Authentication`/verified actor từ security context hoặc method parameter; không truyền `String userId` do controller đọc header raw rồi đặt tên biến `verifiedUserId`.

## 16. Request tenant phải được xác minh, không tin X-Tenant-ID

Giả sử An có role EDITOR ở tenant north nhưng chỉ VIEWER ở tenant south. Request:

~~~http
POST /api/tenants/south/documents/42
Authorization: Bearer <token-of-an>
X-Tenant-ID: south
X-Role: EDITOR
~~~

Chỉ có thể coi `south` là **tenant target**, không phải membership proof. Server phải:
1. Lấy validated issuer+subject từ Spring Authentication.
2. Chuẩn hóa tenant target (path/header được validate).
3. Tra membership ACTIVE của actor trong tenant target.
4. Xác định role/permission **trong tenant đó**.
5. Lấy resource tenant/owner/status từ database.
6. Kiểm action WRITE với owner/ACL và trạng thái.
7. Ghi bằng scoped query/transaction guard.

Nếu JWT có custom claim `roles:["EDITOR"]` nhưng không có tenant context, đừng map thành `ROLE_EDITOR` toàn cục để áp lên mọi tenant. Một token đã ký không tự thêm thông tin phạm vi mà issuer không cấp.

## 17. Claim subject có thể trùng giữa nhiều issuers

~~~text
Issuer A, sub=123 -> Alice
Issuer B, sub=123 -> Bob
~~~

Nếu ACL chỉ lưu `subject=123`, Bob có thể được hưởng quyền Alice. Identity key nên là `(validatedIssuer, subject)` hoặc internal principal ID được ánh xạ từ cặp này. Đừng dùng email làm khóa chính không cần thiết vì email có thể thay đổi, trùng/tái sử dụng.

Khi multi-issuer:
- Trusted issuers nằm trong allowlist/registry có quản trị.
- Mỗi issuer có JWKS/algorithms/decoder riêng theo trust contract.
- Token audience của từng API vẫn phải đúng.
- Không tự xác nhận issuer chỉ vì string `iss` được decode.
- Account linking phải có xác minh và audit, không auto-link vì trùng tên/email.
- Role của issuer A không tự là role ở tenant B.

Spring Security có các cơ chế multi-tenancy/issuer resolver tùy Servlet/Reactive version. Điểm bất biến: **chỉ lấy identity sau khi token được verify bởi issuer đáng tin**.

## 18. Opaque token: introspection cũng phải nằm trong trust boundary

Không phải OAuth2 access token nào cũng là JWT. Với opaque token, Resource Server có thể gọi Authorization Server qua endpoint introspection (RFC 7662):

~~~text
Resource Server
    |
    | authenticated token introspection request
    v
Authorization Server
    |
    | active, scope, sub, aud, exp...
    v
Resource Server maps trusted result to Authentication
    |
    v
HTTP + service + resource authorization
~~~

Ví dụ Spring Boot Servlet:

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

Đây là cấu hình minh họa, secret từ environment/KMS/secret manager chứ không lưu vào source.

Cẩn thận:
- `active=true` có giá trị theo issuer/introspection contract, không phải “được quyền mọi object”.
- Kiểm audience/required metadata khi Resource Server cần.
- Không cho client tự gửi JSON `{"active":true}` thay response thật của AS.
- Introspection phải được xác thực qua TLS và client credentials đúng.
- AS unavailable/timeout → không được mặc định token active.
- Nếu cache introspection result, định nghĩa TTL và revocation SLA.

Chỉ đọc raw JSON từ một endpoint hoặc object do caller chỉ định không có nghĩa là introspection đáng tin. Nguồn HTTPS và mutual trust phải nằm trong cấu hình server, không do token/header quyết định.

## 19. Gateway và reverse proxy: header nội bộ cũng có thể bị giả mạo

Một hệ thống có API gateway xác thực JWT rồi thêm:

~~~http
X-Authenticated-User: an
X-Authenticated-Issuer: issuerA
X-Authenticated-Tenant: north
X-Authenticated-Roles: EDITOR
~~~

Nếu backend service nhận các header này **trực tiếp từ internet** hoặc gateway không xóa header do client gửi trước khi gắn header của mình, attacker có thể giả user/role.

Hai kiến trúc hợp lệ tùy môi trường:

**A. Mỗi service tự verify Bearer token** với issuer/audience phù hợp và thực hiện domain authorization. Dễ xác định trust boundary; cần quản lý JWKS/key rotation và policies thống nhất.

**B. Gateway verify rồi truyền authenticated identity** qua một kênh service-to-service đã được bảo vệ:
- Chỉ gateway có quyền gọi backend, không có đường bypass.
- mTLS hoặc service identity/cryptographically authenticated context.
- Gateway strip/overwrite mọi identity headers từ public request.
- Backend xác minh rằng request thực sự đến từ gateway được tin.
- Identity propagation có issuer, subject, tenant scope, expiry, audience và provenance rõ.
- Không coi header từ một proxy bất kỳ là đủ, kể cả chạy “mạng nội bộ”.
- Có integration tests gọi trực tiếp backend với forged headers; phải bị từ chối.

**Zero trust** đòi kiểm danh tính tại mỗi trust boundary thích hợp. Một header `X-Role` không tự là signed assertion dù tên trông chuyên nghiệp.

## 20. Forwarded headers không phải authority

`X-Forwarded-For`, `X-Forwarded-Host`, `Forwarded` và các header tương tự có thể hữu ích cho routing/client IP khi qua reverse proxy đã được tin. Nhưng chúng **không chứng minh role, user, token issuer hoặc owner**.

Nếu hệ thống giới hạn admin API theo IP, phải có cấu hình trusted proxies, header stripping, ingress auth và policy rõ. Client có thể tự gửi `X-Forwarded-For: 127.0.0.1` nếu network boundary cho phép.

Header `Origin` cũng không phải authentication:
- Browser dùng Origin/CORS để điều khiển script cross-origin.
- Non-browser client có thể tự tạo Origin.
- CORS allowlist không cấp admin role.
- CSRF token không xác minh object owner.

Đừng gom mọi header “security-looking” thành trusted claims.

## 21. Scope OAuth2 không chứng minh owner hoặc ACL

Token hợp lệ chứa:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "an",
  "scope": "documents.read documents.write"
}
~~~

An gọi `GET /documents/42`. Document #42 ở tenant south và thuộc Bình. HTTP rule `hasAuthority("SCOPE_documents.read")` có thể PASS nhưng object check phải DENY.

Policy ví dụ:

~~~text
ALLOW_READ =
    validAccessTokenForDocumentsApi
    AND hasScope("documents.read")
    AND activeMember(subject, requestedTenant)
    AND resource.tenant == requestedTenant
    AND (
        subjectIsOwner(resource)
        OR activeShareReadGrant(subject, resource)
        OR activeProjectReadPermission(subject, resource)
    )
    AND resourceStateAllowsRead
~~~

Một raw `ownerId` do request body chứa **không được** dùng thay `resource.owner` lấy từ DB. Nếu project cần break-glass/system admin, phải định nghĩa policy ngoại lệ có chứng thực/giám sát riêng, không suy từ `X-Is-Admin: true`.

Đây là trọng tâm OWASP **Broken Object Level Authorization (BOLA)**: mỗi endpoint nhận object ID phải xác minh actor được thực hiện action trên object ấy.

## 22. Query DB phải gắn verified actor và resource scope

Owner-only:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND d.owner_subject_key = :verified_subject;
~~~

Với share READ:

~~~sql
SELECT d.id, d.title
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

Điều kiện `id`, `tenant` và `status` phải áp lên **cả hai nhánh owner/ACL**. Nếu viết `id AND tenant AND owner OR share` thiếu ngoặc, nhánh OR có thể vượt tenant.

Nguồn tham số:
- `:verified_subject` từ authenticated issuer/sub hoặc internal principal ID.
- `:verified_tenant` từ membership resolver đã xác minh, không phải header đơn thuần.
- `:id` là target có thể do client chọn nhưng phải gắn với tenant/ACL.
- `:now` là server time, không tin client clock.

**Không thay object authorization bằng việc khó đoán ID.** Dùng UUID không khiến IDOR/BOLA biến mất nếu caller lấy được ID của người khác.

## 23. Spring service: dùng Authentication, không nhận claim tự khai

Một service method có thể được bảo vệ bằng method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final VerifiedActorResolver actorResolver;
    private final DocumentRepository repository;

    public DocumentService(
            VerifiedActorResolver actorResolver,
            DocumentRepository repository) {
        this.actorResolver = actorResolver;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public DocumentView read(String requestedTenant, Long documentId) {
        VerifiedActor actor =
                actorResolver.requireActiveTenantMember(requestedTenant);

        Document document = repository
                .findReadableByIdAndTenant(
                    documentId, actor.tenantId(), actor.subjectKey())
                .orElseThrow(ResourceNotFoundException::new);

        return new DocumentView(document.getId(), document.getTitle());
    }
}
~~~

**Snippet Spring integration**, các class `VerifiedActorResolver`, `VerifiedActor`, `DocumentRepository`, `DocumentView` và exception là domain types phải triển khai. `@EnableMethodSecurity` phải bật. Bean `actorResolver` cần lấy identity từ authenticated context, không đọc `X-User-Id`.

Thứ tự:
1. JWT/opaque token được xác thực.
2. `@PreAuthorize` kiểm coarse scope.
3. Resolver kiểm active tenant membership.
4. Repository query scoped theo resource.
5. Trả DTO giới hạn trường được phép.

Self-invocation qua `this.read(...)` có thể bypass method interceptor trong proxy mode; test phải gọi qua Spring-managed proxy. Non-HTTP adapters (worker, message consumer) cũng cần service policy boundary thích hợp.

## 24. WRITE/DELETE cần bảo vệ tại thời điểm mutation

Ngay cả khi token hợp lệ và owner được kiểm ở T1, quyền có thể thay đổi ở T2 trước DB UPDATE ở T3.

~~~text
T1: token valid, owner=an -> ALLOW WRITE
T2: tài liệu đổi owner hoặc grant WRITE bị revoke
T3: repository.updateById(42) chạy không có guard
~~~

Đây là time-of-check/time-of-use (TOCTOU). Với owner-only write, nên dùng guarded SQL:

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

Kết quả affected rows = 0 nghĩa là **không thành công**, không trả 200/204 giả. Nếu WRITE được cấp qua ACL bảng khác, cần predicate `EXISTS`/transaction/lock/revision protocol phù hợp; `@Version` trên document một mình không tự kiểm grant ở nơi khác.

Không dùng `jwt.getClaim("isAdmin")` rồi bỏ mutation guard. Claim hợp lệ cũng có thể stale hoặc không có object scope.

## 25. Token role và ACL có thể thay đổi sau khi token phát

Giả sử:
~~~text
T0: AS phát token còn hạn 15 phút
    role=EDITOR, scope=documents.write

T1: Admin thu hồi quyền WRITE Document 42
T2: User gọi API bằng token chưa expired
~~~

JWT có thể còn hợp lệ theo chữ ký/issuer/exp. Nhưng domain grant đã mất; tùy policy, request phải DENY. Cần phân biệt:
- Token lifetime.
- Permission/membership/ACL lifetime.
- Authorization cache TTL.
- Revocation propagation/consistency SLA.
- Policy version.

Giải pháp có thể gồm short-lived access tokens, introspection, ACL/version lookups, revocation lists hoặc decision cache invalidation. Không hứa revoke tức thì trong khi server tiếp tục dùng cached ALLOW lâu.

**“Signed by trusted issuer” không đồng nghĩa “mọi claim có giá trị vĩnh viễn”.**

## 26. JWT trong cookie, CSRF và CORS

Nếu JWT nằm trong cookie được browser tự gửi, endpoint vẫn có thể bị CSRF nếu browser mang ambient credential tới một request giả mạo. Nếu Bearer token chỉ được frontend chủ động gửi qua `Authorization` header cho một stateless API, CSRF threat model có thể khác.

Không lập luận:
- “JWT đã ký nên không cần CSRF” — sai nếu cookie tự mang token.
- “CORS deny evil site nên không bị CSRF” — CORS không chặn mọi request được gửi.
- “Có CSRF token nghĩa là có role ADMIN” — token CSRF không phải identity.
- “Origin app.example nghĩa là user có quyền document” — Origin không phải ACL proof.

Chống XSS, CSRF, credential theft, token validation và domain authorization là các lớp khác nhau, có thể cần đồng thời.

## 27. Trust boundary trong WebFlux Reactive

Với Spring WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Đây là **WebFlux integration snippet**, cần ReactiveJwtDecoder/issuer config, OAuth2 Resource Server dependencies và business service checks. Servlet `SecurityContextHolder` ThreadLocal không thay thế `ReactiveSecurityContextHolder`/Reactor Context.

Lưu ý:
- `Mono<Authentication>` của reactive authorization phải được framework cấp, không lấy identity từ request body.
- Tránh `block()` trên event-loop để kiểm token/ACL.
- Không cache current principal trong mutable singleton hoặc shared `Mono.cache()` làm rò user giữa requests.
- Khi message/worker dùng async khác request, dùng workload/verified delegation contract, không tin string `requestedUser`.
- `ServerWebExchange` attributes và Reactor Context là **vật chứa dữ liệu theo request/subscription**, không tự tạo tính tin cậy của claim.

## 28. Server-issued context không nên nhận nhầm từ client

Một controller có thể nhận:

~~~http
X-Requested-Tenant: north
X-Acting-User: admin
X-Policy-Override: allow
X-Request-Id: req-999
~~~

Các header này không làm user thành admin. Nếu server cần hỗ trợ impersonation/support:
- Có explicit admin/act-as capability được kiểm bởi trusted Authentication.
- Có approval, reason, TTL, audit và scope.
- Resource access vẫn được bảo vệ.
- Header intent được coi là **yêu cầu giả lập**, không là proof.

Correlation ID giúp trace sự cố nhưng **không được** dùng làm bằng chứng quyền. Header mà client tự đặt tên “Verified” vẫn không được tin nếu không có trusted gateway contract.

## 29. Java 17 độc lập: lời khai giả không đổi được quyền

Đoạn chương trình sau **chạy với JDK 17**, không cần Spring. Nó mô phỏng một trust boundary bằng bảng token → verified identity do **server sở hữu**. Các chuỗi như `bearer-an` chỉ là fixture để thấy code không dùng `clientClaimedSubject`, `clientClaimedRole` hoặc `clientClaimedTenant` làm permission proof. **Đây không phải JWT cryptographic verification**, không dùng token marker hard-code trong sản phẩm.

Tạo file `ClaimTrustBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class ClaimTrustBoundaryDemo {
    enum Action { READ, WRITE }

    record RawRequest(
            String bearerRef,
            String clientClaimedSubject,
            String clientClaimedRole,
            String clientClaimedTenant,
            String targetTenant,
            long targetId,
            Action action) { }

    record VerifiedToken(
            String issuer,
            String subject,
            String audience,
            Set<String> scopes) { }

    record Document(
            long id, String tenant,
            String ownerKey, boolean locked) { }

    record Membership(
            String subjectKey,
            String tenant,
            Set<Action> allowedActions) { }

    record Grant(
            String tenant, long documentId,
            String subjectKey, Action action) { }

    // Chỉ là stub server-owned. Production dùng JwtDecoder/introspection.
    static final class TrustedTokenVerifier {
        private final Map<String, VerifiedToken> issued = Map.of(
            "bearer-an",
            new VerifiedToken("issuerA", "an", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "bearer-binh",
            new VerifiedToken("issuerA", "binh", "documents-api",
                    Set.of("documents.read")),
            "bearer-carol",
            new VerifiedToken("issuerA", "carol", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "wrong-aud",
            new VerifiedToken("issuerA", "an", "payments-api",
                    Set.of("documents.read", "documents.write")),
            "wrong-iss",
            new VerifiedToken("issuerB", "an", "documents-api",
                    Set.of("documents.read", "documents.write")),
            "no-scope",
            new VerifiedToken("issuerA", "an", "documents-api",
                    Set.of("documents.read"))
        );

        VerifiedToken verify(String marker) {
            return issued.get(marker);
        }
    }

    static final Set<Membership> MEMBERSHIPS = Set.of(
        new Membership(
            "issuerA|an", "north", Set.of(Action.READ)),
        new Membership(
            "issuerA|binh", "north", Set.of(Action.READ)),
        new Membership(
            "issuerA|carol", "north",
            Set.of(Action.READ, Action.WRITE))
    );

    static final Set<Grant> GRANTS = Set.of(
        new Grant("north", 47, "issuerA|an", Action.READ)
    );

    static String check(
            TrustedTokenVerifier verifier,
            RawRequest request,
            Document document) {

        if (request == null || request.action() == null) {
            return "DENY_INVALID_INPUT";
        }

        VerifiedToken token = verifier.verify(request.bearerRef());
        if (token == null
                || !"issuerA".equals(token.issuer())
                || !"documents-api".equals(token.audience())
                || token.subject() == null
                || token.scopes() == null) {
            return "DENY_UNVERIFIED_TOKEN";
        }

        String neededScope = request.action() == Action.READ
                ? "documents.read" : "documents.write";
        if (!token.scopes().contains(neededScope)) {
            return "DENY_SCOPE";
        }

        if (document == null
                || document.id() != request.targetId()
                || request.targetTenant() == null
                || !request.targetTenant().equals(document.tenant())) {
            return "DENY_RESOURCE_SCOPE";
        }

        String subjectKey =
                token.issuer() + "|" + token.subject();
        boolean memberCanAct = MEMBERSHIPS.stream().anyMatch(m ->
            m.subjectKey().equals(subjectKey)
            && m.tenant().equals(request.targetTenant())
            && m.allowedActions().contains(request.action())
        );
        if (!memberCanAct) {
            return "DENY_TENANT_ROLE";
        }

        if (document.locked() && request.action() == Action.WRITE) {
            return "DENY_LOCKED";
        }

        boolean owner = subjectKey.equals(document.ownerKey());
        boolean shared = GRANTS.contains(new Grant(
                document.tenant(), document.id(),
                subjectKey, request.action()));
        return owner || shared ? "ALLOW" : "DENY_OBJECT";
    }

    public static void main(String[] args) {
        TrustedTokenVerifier verifier =
                new TrustedTokenVerifier();

        Document own = new Document(
                42, "north", "issuerA|an", false);
        Document binh = new Document(
                43, "north", "issuerA|binh", false);
        Document shared = new Document(
                47, "north", "issuerA|binh", false);
        Document locked = new Document(
                44, "north", "issuerA|carol", true);
        Document south = new Document(
                45, "south", "issuerA|an", false);

        System.out.println("owner-read=" + check(
            verifier, new RawRequest(
                "bearer-an", "admin", "SUPER_ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("forged-admin-write=" + check(
            verifier, new RawRequest(
                "bearer-an", "admin", "SUPER_ADMIN", "north",
                "north", 42, Action.WRITE), own));

        System.out.println("spoofed-owner=" + check(
            verifier, new RawRequest(
                "bearer-an", "binh", "ADMIN", "north",
                "north", 43, Action.READ), binh));

        System.out.println("shared-read=" + check(
            verifier, new RawRequest(
                "bearer-an", "an", "VIEWER", "north",
                "north", 47, Action.READ), shared));

        System.out.println("unsigned-or-unknown=" + check(
            verifier, new RawRequest(
                "made-up-jwt", "admin", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("wrong-audience=" + check(
            verifier, new RawRequest(
                "wrong-aud", "an", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("wrong-issuer=" + check(
            verifier, new RawRequest(
                "wrong-iss", "an", "ADMIN", "north",
                "north", 42, Action.READ), own));

        System.out.println("missing-write-scope=" + check(
            verifier, new RawRequest(
                "no-scope", "an", "ADMIN", "north",
                "north", 42, Action.WRITE), own));

        System.out.println("cross-tenant=" + check(
            verifier, new RawRequest(
                "bearer-an", "an", "ADMIN", "south",
                "north", 45, Action.READ), south));

        System.out.println("locked-write=" + check(
            verifier, new RawRequest(
                "bearer-carol", "carol", "ADMIN", "north",
                "north", 44, Action.WRITE), locked));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ClaimTrustBoundaryDemo.java
java ClaimTrustBoundaryDemo
~~~

Stdout chính xác:

~~~text
owner-read=ALLOW
forged-admin-write=DENY_TENANT_ROLE
spoofed-owner=DENY_OBJECT
shared-read=ALLOW
unsigned-or-unknown=DENY_UNVERIFIED_TOKEN
wrong-audience=DENY_UNVERIFIED_TOKEN
wrong-issuer=DENY_UNVERIFIED_TOKEN
missing-write-scope=DENY_SCOPE
cross-tenant=DENY_RESOURCE_SCOPE
locked-write=DENY_LOCKED
~~~

Giải thích:
1. Request khai `subject=admin` và `role=SUPER_ADMIN`, nhưng token verified là issuerA|an; An READ được document của mình **không nhờ lời khai giả**.
2. An chỉ có READ tenant permission dù token có WRITE scope: `forged-admin-write` bị chặn.
3. An khai `clientClaimedSubject=binh` không biến An thành owner của document 43.
4. An có READ share grant đúng document 47, nên shared-read ALLOW.
5. Token marker không có trong trusted verifier ⇒ không xác thực, dù client khai admin.
6. Wrong audience/issuer bị chặn tại token boundary.
7. Token thiếu WRITE scope bị chặn trước object checks.
8. Document thuộc south khi target north → bị chặn.
9. Document locked chặn WRITE ngay cả khi Carol có scope và tenant permission.

**Giới hạn rất quan trọng:** Verifier trong demo là bảng fixture do server giữ, chỉ để mô phỏng trusted token identity. Production phải dùng cryptographically verified JwtDecoder hoặc OAuth2 introspection với TLS và required validators. Không để attacker chọn hoặc sửa server-issued lookup table, không nhận một boolean `verified=true` từ body. Các kết quả không thay thế framework integration tests.

## 30. Test token validation thật, đừng chỉ mock Jwt

Spring Security Test có `jwt()` helper rất tiện để tạo mock Authentication khi kiểm HTTP/method authorization:

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
class ScopeAuthorizationTests {
    @Autowired MockMvc mvc;

    @Test
    void noReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/documents/42")
                .with(jwt().authorities()))
            .andExpect(
                org.springframework.test.web.servlet.result
                    .MockMvcResultMatchers.status().isForbidden());
    }
}
~~~

**Snippet Spring Test** cần dependencies Spring Boot Test/Security Test, endpoint/filter chain đúng. Mocks có thể bypass đường JWT decoding thật, nên test chỉ chứng minh authority/service behavior trong fixture, **không chứng minh chữ ký, issuer, audience hoặc exp được kiểm**.

Để kiểm token verification, dùng signed test tokens và test issuer/JWKS hoặc mock decoder kiểm validators:
- Token signature đúng/sai, thuật toán outside allowlist.
- `kid` không có trong trusted JWKS, malicious `jku/x5u`.
- Wrong issuer/audience; expired/nbf future.
- OIDC ID token thay OAuth access token.
- Token thuộc issuer khác với cùng sub.
- Scopes claims sai type/missing, unusual whitespace.
- Opaque introspection active=false, malformed và endpoint timeout.
- Response thiếu verification proof không tạo Authentication.
- Đường controller không thể bypass security filter chain.

Khi test endpoint, **kiểm cả database/outbox/side effect không bị thay đổi** với denied requests, chứ không chỉ status code.

## 31. Ma trận test ranh giới tin cậy

| Request/token | Trusted identity? | Coarse action? | Resource policy? | Kỳ vọng |
|---|---|---|---|---|
| Valid JWT + owner + correct tenant | Có | Đạt | Đạt | ALLOW |
| Body `isAdmin=true`, user thường | User thường | Không đổi | Theo policy thật | Không tự nâng quyền |
| Header `X-Role=ADMIN`, user thường | User thường | Không đổi | Theo policy thật | DENY nếu thiếu quyền |
| URL tenant khác | Identity vẫn hợp lệ | Có thể Đạt | Membership/tenant FAIL | DENY |
| JWT chỉ Base64URL decode, không verify | **Không** | Không xét | Không xét | 401 |
| Payload JWT bị sửa, signature invalid | **Không** | Không xét | Không xét | 401 |
| JWT đúng chữ ký, wrong issuer | **Không** | Không xét | Không xét | 401 |
| JWT đúng issuer, wrong audience | **Không** | Không xét | Không xét | 401 |
| JWT expired hoặc nbf future | **Không** | Không xét | Không xét | 401 |
| ID token dành cho frontend gửi tới API | **Không** | Không xét | Không xét | 401 |
| JWT thiếu WRITE scope | Có | FAIL | Không xét | 403 |
| JWT có WRITE scope, role tenant chỉ READ | Có | HTTP có thể Đạt | Tenant role FAIL | DENY |
| JWT READ scope, object owner khác, không grant | Có | Đạt | FAIL | 403/404 |
| JWT READ scope, resource thuộc tenant khác | Có | Đạt | FAIL | 403/404 |
| JWT WRITE scope, resource LOCKED | Có | Đạt | FAIL | DENY/conflict |
| Opaque token active=false | Không | Không xét | Không xét | 401 |
| Introspection timeout | Không xác minh được | Không xét | Không xét | Fail closed |
| Client credentials, không có human user | Workload | Tùy scope | Workload policy | Không gán user owner |
| Header identity giả đi thẳng backend | Không đáng tin | Không xét | Không xét | Chặn tại gateway/backend |
| Token revocation xảy ra sau khi phát | Có thể JWT còn hạn | Có thể Đạt | Membership/ACL recheck | DENY theo revocation SLA |
| JWT issuer B trùng sub với issuer A | B nếu trusted | Tùy scope | Namespace khác | Không nhầm owner |
| Token audiences cho API A gửi API B | Không ở B | Không xét | Không xét | 401 |

Test cả boundary protection, không chỉ validator:
- Bypass gateway bằng direct backend request.
- Self-invocation method security.
- Queue/job dùng actor từ message body mà không verify delegation.
- Cache key không phân biệt user, tenant, action và resource.
- Chính sách đồng thời revoke grant khi request đang thực thi.
- Policy backend lỗi mà code vô tình return true.

## 32. Phân biệt 401, 403, 404 và lỗi kỹ thuật

| Lỗi | Ý nghĩa | HTTP thường dùng |
|---|---|---|
| Missing/invalid Bearer token | Authentication không được xác lập | 401/challenge |
| JWT wrong issuer/audience/signature/time | Credential không hợp lệ | 401 |
| Token hợp lệ nhưng thiếu scope/role | Authorization denial | 403 |
| Token và scope đúng, resource ngoài scope | Object-level denial | 403/404 theo chính sách chống lộ |
| Resource version stale | Concurrency/business | 409 hoặc mã phù hợp |
| Decoder/introspection không khả dụng | Technical authn failure | 5xx/503, không thực thi |
| PDP/ACL DB không khả dụng | Technical authz failure | 5xx/503, không thực thi |

RFC 6750 mô tả Bearer token errors như `invalid_token` và `insufficient_scope`. Không đem raw exception message, token string hoặc ACL graph trả cho client.

Một lỗi sai issuer không được chữa bằng cấp ROLE_ADMIN. Một lỗi object ACL không được chữa bằng bỏ audience validator. Phân tích đúng tầng giúp tránh thay security controls thành `permitAll()` vì thấy 401/403.

## 33. Logs, telemetry và bảo vệ thông tin cá nhân

Không log:
- Raw `Authorization: Bearer`, access/refresh/ID token.
- Cookie/session token, query parameter chứa credential.
- Full Jwt claims/Authentication object từ request.
- Signing private keys, JWKS secrets hoặc introspection credentials.
- Owner, ACL, tên tài liệu bí mật, tenant ngoài quyền.
- Exception stack trace trong response công khai.

Có thể log có kiểm soát:
- Event `AUTHN_INVALID_SIGNATURE`, `AUTHN_INVALID_AUDIENCE`.
- `AUTHZ_INSUFFICIENT_SCOPE`, `AUTHZ_RESOURCE_DENIED`.
- Policy version/decision ID, request correlation ID.
- Opaque actor alias nếu cần, tenant/resource type theo quyền audit.
- HTTP endpoint/service and enforcement outcome.

Audit store cũng phải được bảo vệ bằng least privilege, retention và kiểm soát export; correlation ID không phải quyền đọc audit. Không log toàn bộ header chỉ để chứng minh caller đã cố spoof `X-Role`; nếu cần incident logging, sanitize/limit và che token/PII.

## 34. Những sai lầm phổ biến

**1. Tin `roles` hoặc `isAdmin` từ JSON body.** Client có thể đổi. Dùng Authentication đã verify và trusted policy.

**2. Tin `X-User-Id`/`X-Role` từ request public.** Header không được ký. Chỉ dùng trusted gateway propagation có chống bypass/forgery.

**3. Decode Base64URL JWT rồi cấp role.** Decode không verify. Dùng JwtDecoder/introspection.

**4. Chỉ verify signature mà bỏ issuer/audience/type/expiry.** Token có thể dành API khác hoặc không còn hiệu lực.

**5. Chấp nhận `alg=none` hoặc algorithm do token quyết định.** Giới hạn algorithms và keys đã tin.

**6. Tải `jku/x5u` URL tùy ý.** SSRF/key injection. Chỉ dùng trusted JWKS.

**7. Tin `kid` là đường dẫn/SQL sạch.** Header attacker-controlled cần validate/limit.

**8. Nhận OIDC ID token như OAuth access token.** Sai loại và audience. Áp token profile.

**9. Nghĩ `SCOPE_documents.read` là quyền đọc mọi document.** BOLA. Cần tenant/owner/ACL.

**10. Roles tenant A thành global `ROLE_ADMIN`.** Rò cross-tenant. Scope roles đúng tenant.

**11. Chỉ dựa `sub` không có issuer namespace.** Collision multi-issuer.

**12. Dùng `Authentication.isAuthenticated()` thay policy.** Chỉ xác định trạng thái xác thực.

**13. Dùng JWT còn hạn để bỏ membership revoke.** Token validity khác permission freshness.

**14. Introspection timeout rồi coi active=true.** Fail-open.

**15. `@PreAuthorize` xong UPDATE theo ID trần.** Thiếu mutation guard/TOCTOU.

**16. Test bằng `jwt()` mock rồi kết luận crypto pass.** Cần validator integration tests.

**17. Cache token/Authentication ở singleton.** Có thể lẫn identity giữa requests.

**18. Forward token aud=serviceA sang serviceB.** B phải validate own audience hoặc dùng token exchange.

**19. Mọi 403 đều được sửa bằng `permitAll()`.** Mở quyền thay vì sửa nguyên nhân.

**20. Log full Bearer token để debug.** Rò credential và replay risk.

## 35. Checklist trước khi merge code

- [ ] Không có authorization grant nào dựa vào `X-Role`, `X-User-Id`, `isAdmin`, `ownerId` hay `approved` do client tự khai.
- [ ] Raw token được xác thực trước khi xây principal/authorities.
- [ ] Decoder/introspector trust đúng issuer, keys, algorithms và token profile.
- [ ] `iss`, `aud`, `exp`, `nbf` và loại access token được validate theo contract.
- [ ] JWT header `kid/jku/x5u` không cho phép injection/SSRF hoặc key substitution.
- [ ] Access token được phân biệt ID token/refresh token.
- [ ] Scope/role claims đã verified mới được map thành GrantedAuthority.
- [ ] Tenant roles không bị dùng global ngoài scope.
- [ ] Multi-issuer identity có namespace issuer+subject.
- [ ] Request tenant được xác minh qua active membership.
- [ ] Owner/ACL/resource state từ server DB/PIP đáng tin.
- [ ] READ/list/export/count và WRITE/DELETE đều áp object policy.
- [ ] Guarded transactions chống stale permission/TOCTOU phù hợp.
- [ ] Opaque token introspection không fail-open khi timeout/active=false.
- [ ] Gateway strip/overwrite client identity headers, backend không bị bypass.
- [ ] Downstream service validate audience, không blind-forward credentials.
- [ ] Client credentials workload được phân biệt human user.
- [ ] JWT trong cookie và Bearer-only có CSRF threat model phù hợp.
- [ ] Security context per request/subscription, không cache identity sai scope.
- [ ] Unit test claim forgery và object owner/tenant.
- [ ] Integration test real JWT validation, không chỉ mock `jwt()`.
- [ ] Kiểm 401/403/404/5xx đúng và không có side effect khi denied.
- [ ] Không log token/PII/secret ngoài nhu cầu; audit store có phân quyền.
- [ ] Security regression tests cho key rotation, revoke và policy outage.

**Kết luận:** Client có thể viết bất kỳ chữ `ADMIN`, `owner` hoặc `verified` nào vào HTTP request; điều đó không tự tạo quyền. JWT payload có thể decode được nhưng vẫn **chưa đáng tin** nếu chưa xác minh cryptographic trust, issuer, audience, thời gian và loại token. Sau khi Spring Security xác thực token, application mới có một actor/client identity được tin cậy **cho bước phân quyền tiếp theo**: scope, tenant role, owner/ACL và trạng thái tài nguyên vẫn phải được kiểm độc lập. Thiết kế ranh giới này cùng fail-closed, scoped queries, guarded mutations và tests giúp ngăn privilege escalation và BOLA dù attacker giả mạo claims rất thuyết phục.

## Tài liệu tham khảo

- [Spring Security — OAuth2 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decode/verify, issuer, JWKS, authorities và audience.
- [Spring Security — OAuth2 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và WebFlux.
- [Spring Security — OAuth2 Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và active status.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và method policy.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithms, issuer/audience, token typing, kid/jku/x5u và claim trust.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token profile và token type.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials và errors.
- [RFC 7662 — OAuth2 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active status và metadata.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): kiểm quyền với object ID.
- [OWASP — JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): key, token handling, claim validation và revocation.
