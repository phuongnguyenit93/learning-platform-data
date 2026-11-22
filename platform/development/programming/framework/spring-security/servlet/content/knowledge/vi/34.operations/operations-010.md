# Thay đổi khóa, quyền, tài khoản và quy trình thu hồi truy cập trong Spring Security Servlet

## 1. Mục tiêu và bối cảnh vận hành

Trong Spring Security Servlet, một request có thể được xác thực bằng **HttpSession**, HTTP Basic, JWT Bearer, opaque token, OAuth2 login, API key hoặc một identity assertion từ gateway. Việc đổi khóa, giảm quyền hoặc disable tài khoản **không tự động làm mọi phương tiện truy cập đã phát hành trước đó hết hiệu lực**. Hệ thống phải có quy trình xác minh rằng truy cập thực sự được thu hồi trong thời gian cho phép.

Ví dụ: administrator gỡ ROLE_ADMIN khỏi alice trong database. Nếu alice còn một HttpSession lưu Authentication cũ với ROLE_ADMIN, hoặc một JWT access token chưa hết hạn mang quyền admin, thì một endpoint chỉ xét authority trong Authentication cũ **có thể vẫn cho phép**. Tương tự, đổi mật khẩu không đương nhiên hủy tất cả cookie session, refresh token hay API key.

Mục tiêu bài học:
- Phân biệt **khóa ký JWT**, TLS/mTLS key, OAuth2 client secret, API key và mật khẩu.
- Nắm quy trình **signing-key rotation, JWKS overlap, kid và key retirement**, đặc biệt phân biệt rotation định kỳ với compromised key.
- Hiểu **role/permission/scope**, tài khoản enabled/disabled, quyền theo tài nguyên và độ trễ quyền thay đổi có hiệu lực.
- Phân biệt **session invalidation**, **refresh-token revocation**, **JWT access-token revocation**, **opaque introspection** và account deprovisioning.
- Thiết kế runbook thay đổi, quy trình thu hồi khẩn cấp, rollback, kiểm thử và audit.
- Vận dụng Spring Security 6 trên Servlet stack, hiểu giới hạn của JWT stateless; chạy ví dụ Java 17 để thấy quyền và trạng thái account ảnh hưởng truy cập như thế nào.

**Nguyên tắc vận hành:** Một thay đổi chỉ được xem là thành công khi các luồng thực sự cấp truy cập đã cập nhật, không phải chỉ khi database hoặc giao diện quản trị hiện trạng thái mới.

## 2. Những đối tượng có vòng đời riêng

| Đối tượng | Chức năng | Thay đổi ảnh hưởng đến đâu? |
| --- | --- | --- |
| **JWT signing key / JWK** | Ký và xác minh JWT access token | Authorization Server, JWKS, Resource Server JwtDecoder và cache khóa |
| **TLS/mTLS certificate** | Bảo vệ kênh truyền, định danh server/service | Truststore, keystore, certificate chain, certificate reload, TLS termination |
| **OAuth2 client secret** | Client xác thực với Authorization Server | Client registration, service config, secret manager, token endpoint |
| **API key** | Credential gọi API hoặc nhận diện service | Lookup store, scopes, issuer, consumers, expiration/revocation |
| **Password** | Credential đăng nhập | Identity provider, password encoder, password reset flow |
| **Role/GrantedAuthority** | Cấp quyền ở Spring Security | Authentication/authorities mapper, session, token claims, authorization rules |
| **Permission/scope** | Quyền với hành động/API | JWT scopes, server-side ACL, method security và policy engine |
| **User/service account** | Chủ thể truy cập | IAM directory, enabled/locked, ownership, sessions, grants, credentials |
| **HttpSession / cookie** | Duy trì đăng nhập web ở server | Session repository trên một hoặc nhiều nodes, SSO, remember-me |
| **Access token** | Truy cập tài nguyên tại Resource Server | JWT validation, introspection hoặc revocation layer |
| **Refresh token** | Xin access token mới tại Authorization Server | AS revocation store, rotation, token family và client |
| **Delegated grant** | Cho ứng dụng/service hoạt động theo quyền đã cấp | OAuth2 consent/grant, client authorization, third-party access |

**Đổi một loại không tự động đổi loại khác.** Đổi key TLS không thu hồi JWT. Đổi password không tự xóa session. Xóa role trong database không đảm bảo mọi phiên đã cập nhật authorities. Revoke refresh token không nhất thiết làm access token cũ lập tức không dùng được.

## 3. Luồng HTTP và các điểm kiểm soát

~~~text
Client / Browser / Service
    |
    | Cookie / Authorization: Bearer / Basic / API key
    v
Gateway / Reverse Proxy / SSO
    |
    v
Spring Security FilterChainProxy
    |
    +-- SecurityContextHolderFilter
    +-- Authentication filter
    |     BasicAuthenticationFilter
    |     UsernamePasswordAuthenticationFilter
    |     BearerTokenAuthenticationFilter
    |
    +-- Provider / JwtDecoder / OpaqueTokenIntrospector
    |     xác minh password, token hoặc kết quả introspection
    |
    +-- SecurityContext: Authentication + GrantedAuthority
    |
    +-- AuthorizationFilter / @PreAuthorize
    |     roles, scopes, policy
    v
Controller -> Service -> ACL / Repository
~~~

Các thay đổi có thời điểm tác động khác nhau:
1. **Rotate key:** ảnh hưởng khi decoder/verifier lấy khóa và xác minh **chữ ký** JWT.
2. **Giảm quyền:** ảnh hưởng khi provider/authorization layer tải **quyền mới**. Authorities từ JWT/session cũ có thể vẫn như cũ.
3. **Disable account:** có thể ngăn **login mới** qua UserDetailsService, nhưng một JWT stateless hoặc session đang tồn tại không nhất thiết kiểm tra lại isEnabled.
4. **Revoke token:** phải có nơi lưu và nơi kiểm tra revocation; nếu API không hỏi nơi ấy thì thao tác revoke không có tác dụng tại API.
5. **Invalidate session:** ngăn reuse cookie-session ở request tiếp theo theo semantics của session store, nhưng không thu hồi Bearer token độc lập.
6. **Thay ACL của tài nguyên:** service phải đánh giá quyền trên resource hiện tại, không chỉ role toàn cục.

Những giới hạn này phải được ghi trong **security contract** của ứng dụng.

## 4. JWT signing-key rotation: quy trình không gián đoạn

### 4.1. Các khái niệm

Với JWT ký bằng khóa bất đối xứng, **Authorization Server** giữ private signing key; **Resource Server** dùng public verification key được công bố trong **JWKS**. Header JWT có thể chứa **kid**:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-b",
  "typ": "JWT"
}
~~~

**kid là gợi ý chọn khóa, không phải bằng chứng tin cậy.** JWT vẫn phải được xác minh bằng khóa thuộc JWKS/trust configuration được quản lý, thuật toán được phép và các validators cho **iss**, **exp**, **nbf**, **aud** phù hợp. Không lấy kid hay URL JWK do client tùy ý gửi làm nguồn tạo trust.

### 4.2. Các bước thay khóa định kỳ

1. **Inventory:** xác định issuer, JWKS URI, signing algorithms, Resource Servers đang tin issuer, TTL lớn nhất của token, clock skew, JWK cache/cập nhật, client environments, owners.
2. **Generate new key** bằng KMS/HSM hoặc bí mật được lưu an toàn. Giới hạn quyền truy cập private key, không commit vào repository và không đưa vào ticket/log.
3. **Publish public key mới** trong JWKS, vẫn giữ public key cũ. Kiểm tra Resource Servers đã nhìn thấy new kid.
4. **Switch signing** ở Authorization Server sang private key mới. Token mới phải có kid mới và chữ ký hợp lệ.
5. **Overlap verification:** trong thời gian hợp lệ, Resource Server chấp nhận token ký bởi key cũ và key mới theo chính sách.
6. **Chờ token cũ hết hạn**: tính từ thời điểm cuối cùng còn ký bằng key cũ cộng max access-token lifetime, clock skew và JWK caching thực tế. Không suy đoán mọi token đều 15 phút.
7. **Retire old public key** khỏi trusted set khi policy cho phép; xác minh mọi node đã cập nhật, rồi quản lý private key cũ theo retention/deletion policy.
8. **Kiểm thử và audit** toàn bộ thay đổi, bao gồm key mới, key cũ trong overlap, key cũ sau retire, unknown kid, wrong algorithm/signature và JWKS outages.

~~~text
Thời gian ------------->

Trusted JWKS:   [A] -------- [A + B] ------------ [B]
Signing key:    [A] -------- [B] ---------------- [B]

JWT ký A:        issued ---- valid until exp ----- expired
JWT ký B:                     issued ------------- valid
~~~

**Quy tắc chồng lấn:** không retire public key cũ trước khi các token hợp lệ được ký bằng key ấy hết hạn, trừ khi **chủ động thu hồi khẩn cấp** hoặc đã có cơ chế thay thế có kiểm soát. Key rotation định kỳ có mục tiêu an toàn **và** duy trì khả dụng.

### 4.3. Khóa bị lộ thì không được giữ overlap thông thường

Nếu private signing key đã bị hoặc nghi bị lộ, attacker có thể tạo JWT giả có chữ ký hợp lệ. Giữ public key ấy trong trusted JWKS để tránh gián đoạn sẽ tiếp tục mở cửa cho token giả.

Runbook khẩn cấp:
- Kích hoạt incident response, xác định phạm vi key, issuer, các API chịu ảnh hưởng và thời gian có thể bị lộ.
- Ngừng ký bằng key cũ, tạo/sử dụng key mới chưa bị ảnh hưởng.
- **Rút key compromised khỏi trusted verification set** ở mọi Resource Server/gateway theo kế hoạch khẩn cấp, đồng thời xử lý caches và refresh.
- Thông báo client rằng token cũ có thể bị từ chối và cần đăng nhập/xin token mới qua hệ thống an toàn.
- Revoke sessions, refresh tokens hoặc client credentials khác khi incident scope cho thấy cần.
- Theo dõi 401 spike, unknown kid, JWKS refresh, token validation errors và các access pattern bất thường.
- Lưu bằng chứng, điều tra, khắc phục và hậu kiểm.

**Không rollback bằng cách chấp nhận lại key đã bị lộ.** Khắc phục availability bằng phương án phát hành lại token/key an toàn, không bỏ containment.

## 5. Key rotation không tự thu hồi mọi JWT

Khi Resource Server dùng JWT offline validation, nó có thể giữ public key cũ trong cache và xác minh access token đã phát hành trước đó. Vì thế:
- Token còn hạn, ký đúng, issuer/audience hợp lệ vẫn có thể được chấp nhận trong overlap.
- Nếu rút key cũ khỏi trust set nhưng một số nodes còn giữ JWKS cache cũ, revocation latency có thể khác dự kiến.
- Revoke refresh token không làm access token đã cấp thành invalid nếu API không kiểm tra revocation state.
- Key rotation thường không phải biện pháp phù hợp để revoke **một user** vì tác động rộng đến nhiều token khác.

Các cách kiểm soát access token trước exp:
- TTL ngắn nếu chấp nhận cửa sổ quyền cũ tồn tại trong thời gian đó.
- **jti denylist** cho token có ID riêng, tra state dùng chung ở mọi RS.
- **account epoch/token version**, kiểm tra với server-side state mỗi request hoặc theo cache TTL đã được phê duyệt.
- Opaque token **introspection** với AS (và chính sách cache).
- Authorization service/gateway kiểm tra account active và ACL/permission đang có.
- Khi compromise diện rộng, rút signing key khỏi trust nhanh theo incident runbook.

Không có cơ chế nào miễn phí: lookup state làm tăng latency và phụ thuộc availability; cache làm tăng revocation delay; TTL quá ngắn tăng traffic refresh. Cần đo và phê duyệt trade-off.

## 6. Đổi client secret, API key, TLS/mTLS key

| Credential | Lộ trình định kỳ | Điểm nguy hiểm |
| --- | --- | --- |
| OAuth2 client secret | Tạo secret mới, cập nhật client, xác nhận token request, revoke old secret | AS có thể không hỗ trợ song song hai secrets; cần cutover đồng bộ |
| API key | Tạo key mới, chuyển consumers, giám sát, revoke key cũ | Key dùng chung nhiều clients khiến khó biết owner và khó revoke |
| TLS certificate | Cấp chứng chỉ mới, cài chain/truststore, reload, test mTLS/TLS, retire old cert | SAN/chain/trust anchor bị lệch giữa các nodes |
| Signing private key | Generate, publish public JWK, switch signing, overlap, retire | Compromised key không được giữ overlap bình thường |
| Password | Reset theo chính sách, buộc xác thực lại nếu cần | Session, refresh/access token và API key không đương nhiên bị hủy |

**Bí mật phải đặt trong secrets manager/KMS/HSM phù hợp**, không commit vào Java source, YAML version-controlled, image hoặc log. API keys nên được xử lý ở backend bằng cơ chế so sánh bền vững an toàn, quản lý owner, scope và expiry; tránh hardcode plaintext.

Nếu một OAuth2 AS chỉ chấp nhận một client secret tại một thời điểm, cần lên lịch cutover và kế hoạch availability thay vì giả định có thể luôn dùng cả secret cũ và mới. Với **compromised secret**, không re-enable secret cũ để rollback.

## 7. Thay đổi role, permission, scope và ACL

Spring Security dùng **GrantedAuthority** để biểu diễn quyền:
- **hasRole("ADMIN")** thường yêu cầu **ROLE_ADMIN**.
- **hasAuthority("SCOPE_reports.read")** khớp đúng chuỗi authority.
- Resource Server JWT có thể ánh xạ scope/scp claim sang authorities prefix **SCOPE_** theo converter.
- Method security **@PreAuthorize** đọc Authentication hiện hành; không tự biết database mới cập nhật quyền.
- Resource ownership/tenant ACL vẫn phải được thực thi trong business layer.

**Thay đổi nguồn quyền khác với thay đổi Authentication đã tạo.** Ví dụ alice bị xóa ROLE_ADMIN khỏi IAM, nhưng:
- Trong HttpSession cũ còn **UsernamePasswordAuthenticationToken** mang ROLE_ADMIN.
- Trong JWT cũ còn claim role/scope đã được AS ký trước khi gỡ quyền.
- Ở một policy cache, kết quả check cũ còn sống.
- User còn quyền tương đương qua nhóm kế thừa hoặc một delegated grant khác.

Quy trình giảm quyền:
1. Xác minh người yêu cầu/phê duyệt, identity + tenant + resource và before/after permissions.
2. Kiểm tra group hierarchy, inherited privileges, alternate service credentials và delegated access.
3. Cập nhật nguồn quyền canonical; ghi lại actor, lý do, thời điểm.
4. Xác định **cơ chế làm mới quyền**: invalidate session, revoke tokens, account epoch, policy cache invalidation hoặc dynamic ACL.
5. Kiểm thử user bị giảm quyền trên các endpoints nhạy cảm **bằng cả session/token cũ**.
6. Kiểm tra người được giữ quyền vẫn thao tác bình thường.
7. Theo dõi 403/401, data authorization, cache lag, thực hiện hậu kiểm.

**Không tái cấp quyền đã rút vì security incident chỉ để “chữa” lỗi 403.** Phải phân biệt lỗi cấu hình và quyết định an ninh.

### 7.1. Độ trễ có hiệu lực

| Cơ chế | Nguồn quyền | Khi nào đổi quyền có hiệu lực? |
| --- | --- | --- |
| Form login + HttpSession | Authentication được giữ trong session | Có thể cần xóa/refresh session hoặc policy check động |
| HTTP Basic + UserDetailsService | Provider tải user mỗi lần xác thực, tùy cache | Khi nguồn user/authority được đọc lại |
| JWT access token stateless | Claims đã ký trong token + converter | Token cũ giữ claims đến exp, trừ khi có kiểm tra revocation/ACL ngoài |
| Opaque token | Kết quả introspection từ AS | Tùy trạng thái AS và cache introspection |
| API key | Key store và permission mapping | Tùy lookup/cache |
| Service authorization theo ACL | DB/policy engine | Tùy transaction, replica và cache |

Đội vận hành cần thống nhất **revocation SLO**, chẳng hạn “sau khi disable account, request nhạy cảm bằng credential cũ bị từ chối không quá N giây”. Không có N cố định của Spring Security; N phải xuất phát từ threat model và khả năng hệ thống.

## 8. Disabled, locked, expired và deleted account

Tài khoản có thể:
- **Disabled:** bị cấm xác thực do offboarding hoặc quyết định quản trị.
- **Locked:** bị khóa tạm do brute-force hoặc security incident.
- **Expired credentials:** cần thay credentials trước khi đăng nhập theo policy.
- **Deleted/deprovisioned:** danh tính được loại khỏi nguồn IAM, nhưng retention/audit và ownership tài nguyên vẫn cần xử lý.

Các trạng thái **isEnabled()**, **isAccountNonLocked()**, **isAccountNonExpired()**, **isCredentialsNonExpired()** của **UserDetails** được một số AuthenticationProviders dùng khi kiểm tra **đăng nhập mới**. Nhưng một **Bearer JWT Resource Server** không mặc nhiên gọi UserDetailsService mỗi request, và một session đã xác thực có thể không cập nhật isEnabled nếu không có logic bổ sung.

### 8.1. Quy trình offboarding

1. Xác minh identity ID, tenant/issuer, các tài khoản phụ và người phê duyệt.
2. Disable nguồn IAM hoặc service identity, chặn cấp credentials mới.
3. Revoke refresh tokens, OAuth2 grants, delegated authorizations và remembered devices phù hợp.
4. Invalidate HttpSessions của user ở mọi app và session store liên quan; xử lý remember-me tokens/SSO cookies.
5. Kiểm soát JWT access tokens đã phát hành: TTL, denylist, epoch, introspection hoặc policy check theo cam kết thu hồi.
6. Revoke API keys, personal access tokens, SSH/certificate credentials, service integrations do user sở hữu.
7. Loại role/group/ACL, quyền dữ liệu, quyền tenant, shared secret và delegated access.
8. Kiểm tra các jobs đang chạy, scheduled jobs, queue consumers và data ownership cần chuyển giao.
9. Dùng credentials/session/token cũ để test truy cập bị từ chối trên tất cả nodes/ingress.
10. Lưu audit chứng minh các bước hoàn thành, không log raw secret/token.

**Chỉ xóa record user là không đủ.** Token cũ, session cache hoặc một external gateway có thể vẫn chấp nhận danh tính ấy.

## 9. Các lớp thu hồi truy cập

### 9.1. HttpSession và cookie

Với web form login/OIDC login, SecurityContext có thể được lưu trong session. Để thu hồi:
- Xóa/invalidate sessions server-side tại repository đúng và trên cluster.
- Nếu dùng Spring Session/shared store, xác minh session-index mapping, TTL và kết quả trên mọi node.
- Kiểm tra logout local app có đồng bộ với IdP/SSO logout nếu nghiệp vụ yêu cầu.
- Thu hồi persistent remember-me hoặc các session khác.
- Cân nhắc request đã bắt đầu trước khi invalidate: không thể mặc nhiên tua ngược hành động đã thực thi.

**Logout thành công trên một browser không có nghĩa mọi thiết bị đã bị logout.** Admin disable account và remote session revocation cần cơ chế riêng.

### 9.2. JWT access token

JWT tự chứa claims và được ký. Khi API chỉ kiểm tra chữ ký, iss, aud và exp, nó **không biết** account đã bị disable hay jti bị revoke nếu không có kiểm tra server-side bổ sung.

Có thể dùng:
- **jti denylist** lưu token bị thu hồi cho tới exp, với state store phân tán.
- **Token version/account epoch** so với record canonical để từ chối token epoch cũ.
- Short TTL + refresh control với chấp nhận revocation window.
- Introspection thay vì JWT offline, hoặc thêm policy/introspection check phù hợp.
- Dynamic account/authorization check ở service cho endpoints nhạy cảm.

Không bao giờ tin claim **jti, sub, roles, kid** từ một chuỗi JWT chỉ mới Base64-decoded mà **chưa được xác minh chữ ký và các validators**. Mã kiểm tra revocation phải chạy sau khi token đã được xác thực.

### 9.3. Refresh token, OAuth2 grants và OIDC logout

Refresh token thuộc quyền quản lý của **Authorization Server**. Revoke refresh token thường ngăn lấy access token mới, nhưng không buộc mọi Resource Server ngừng nhận access token cũ.

Nếu hỗ trợ refresh-token rotation, cần xử lý reuse detection và token-family revocation theo IdP. OIDC front-channel/back-channel logout có thể giúp kết thúc phiên ở nhiều clients nhưng **không tồn tại mặc định ở mọi triển khai**.

Web app login qua OIDC có thể phải xóa **cả local session và IdP session**. Đăng xuất ở app và đăng xuất SSO toàn cục là hai hành vi khác nhau cần có contract rõ ràng.

### 9.4. Password reset

Đổi password có thể chặn xác thực mới bằng password cũ. Nó **không mặc định** hủy session cookie, token Bearer, API key hay một authorization grant khác. Với password compromise, runbook cần thêm xóa sessions, revoke refresh tokens/grants, kiểm tra hoạt động bất thường và áp dụng MFA/step-up theo chính sách.

## 10. Spring Security Servlet: cấu hình Resource Server JWT

Trong Spring Boot 3.x, Java 17, dependency liên quan gồm **spring-boot-starter-security** và **spring-boot-starter-oauth2-resource-server**. Cấu hình ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/training
~~~

**example.test chỉ là placeholder**, phải dùng issuer thật và metadata/JWKS tin cậy trước khi chạy. JwtDecoder cần xác minh token bằng key và thuật toán được phép; issuer/expiry được hỗ trợ bởi validation tiêu chuẩn, **audience đúng API cần được kiểm tra theo contract** nếu không có sẵn validator phù hợp.

Ví dụ SecurityFilterChain (trích đoạn, không phải file standalone):

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/reports/**")
                        .hasAuthority("SCOPE_reports.read")
                    .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .build();
}
~~~

**STATELESS** có nghĩa API không dùng HttpSession để giữ Authentication cho requests tiếp theo. Nó **không tự thu hồi JWT cũ** sau account disable. Cấu hình CSRF phải được đánh giá theo phương thức xác thực thực tế: nếu browser dùng cookie/session để gửi credential tự động, không tắt CSRF máy móc.

### 10.1. Audience validator

Đoạn minh họa dưới đây cần đặt trong @Configuration với đầy đủ imports, Java 17/Spring Security 6. Việc cấu hình issuer/audience qua environment chỉ là cách lấy giá trị; không hardcode issuer production trong source.

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = System.getenv("JWT_ISSUER");
    String audience = System.getenv("JWT_AUDIENCE");
    if (issuer == null || issuer.isBlank()
            || audience == null || audience.isBlank()) {
        throw new IllegalStateException(
                "JWT_ISSUER and JWT_AUDIENCE must be configured");
    }

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceRule = token ->
            token.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token", "Wrong audience", null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    standard, audienceRule));
    return decoder;
}
~~~

**Lưu ý:** đây là trích đoạn cấu hình JwtDecoder, không có đầy đủ imports/class. Nó minh họa validator **audience** và **issuer**, không có account/jti revocation. Nếu thêm validator truy vấn user-status/token-version store, phải xác định timeout, cache, fail-closed, hiệu lực trên mọi nodes và kiểm thử bằng token đã ký thật.

## 11. Ví dụ Java 17 chạy được: thay quyền, tài khoản, token, key

Ví dụ này là **policy simulator** thuần Java, không phải implementation JWT thật. Nó cho thấy **quyết định truy cập** thay đổi khi server cập nhật quyền, account state, revocation, epoch và trusted key ID.

**Đặc biệt:** record Token dưới đây không có chữ ký mật mã và do chương trình tự tạo. Trong API production, không bao giờ chấp nhận subject, kid, jti hoặc quyền do client tự khai báo rồi cho chạy logic này. Mọi token phải qua JwtDecoder/issuer/audience validation hoặc introspection tin cậy trước.

### 11.1. AccessLifecycleDemo.java

~~~java
import java.util.HashSet;
import java.util.Set;

public final class AccessLifecycleDemo {
    private AccessLifecycleDemo() {
    }

    // Dữ liệu mô phỏng đã tin cậy, KHÔNG phải JWT thật.
    record Token(
            String jti,
            String subject,
            String kid,
            int epoch,
            long expiresAt,
            Set<String> permissionsAtIssue) {
    }

    static final class Account {
        boolean enabled = true;
        int epoch = 1;
        final Set<String> permissions =
                new HashSet<>(Set.of("reports.read", "reports.export"));
    }

    static final class Policy {
        final Account account = new Account();
        final Set<String> revokedIds = new HashSet<>();
        final Set<String> trustedKeys =
                new HashSet<>(Set.of("key-A"));
        String signingKey = "key-A";

        Token issue(String jti, long exp) {
            return new Token(
                    jti, "alice", signingKey, account.epoch, exp,
                    Set.copyOf(account.permissions));
        }

        String decide(Token token, String action, long now) {
            // Production phải xác minh chữ ký/issuer/aud trước.
            if (!trustedKeys.contains(token.kid())) {
                return "DENY_KEY";
            }
            if (now >= token.expiresAt()) {
                return "DENY_EXPIRED";
            }
            if (!account.enabled) {
                return "DENY_DISABLED";
            }
            if (token.epoch() != account.epoch) {
                return "DENY_EPOCH";
            }
            if (revokedIds.contains(token.jti())) {
                return "DENY_REVOKED";
            }
            if (!account.permissions.contains(action)) {
                return "DENY_PERMISSION";
            }
            return "ALLOW";
        }
    }

    public static void main(String[] args) {
        Policy p = new Policy();
        long now = 100;

        Token first = p.issue("jti-001", 500);
        System.out.println("01 read=" +
                p.decide(first, "reports.read", now));
        System.out.println("02 export=" +
                p.decide(first, "reports.export", now));

        p.account.permissions.remove("reports.export");
        System.out.println("03 downgraded=" +
                p.decide(first, "reports.export", now) +
                "; oldClaimExport=" +
                first.permissionsAtIssue().contains("reports.export"));

        p.revokedIds.add(first.jti());
        System.out.println("04 revoked=" +
                p.decide(first, "reports.read", now));

        Token second = p.issue("jti-002", 500);
        System.out.println("05 newToken=" +
                p.decide(second, "reports.read", now));

        p.account.enabled = false;
        System.out.println("06 disabled=" +
                p.decide(second, "reports.read", now));

        p.account.enabled = true;
        p.account.epoch++;
        System.out.println("07 epochChanged=" +
                p.decide(second, "reports.read", now));

        p.trustedKeys.add("key-B");
        p.signingKey = "key-B";
        Token third = p.issue("jti-003", 500);
        System.out.println("08 rotated=" +
                p.decide(third, "reports.read", now));

        p.trustedKeys.remove("key-A");
        System.out.println("09 oldKeyRetired=" +
                p.decide(second, "reports.read", now));

        System.out.println("10 expired=" +
                p.decide(third, "reports.read", 500));
    }
}
~~~

### 11.2. Biên dịch, chạy và stdout chính xác

Dùng JDK 17, lưu code vào file **AccessLifecycleDemo.java**:

~~~bash
javac AccessLifecycleDemo.java
java AccessLifecycleDemo
~~~

Program in ra:

~~~text
01 read=ALLOW
02 export=ALLOW
03 downgraded=DENY_PERMISSION; oldClaimExport=true
04 revoked=DENY_REVOKED
05 newToken=ALLOW
06 disabled=DENY_DISABLED
07 epochChanged=DENY_EPOCH
08 rotated=ALLOW
09 oldKeyRetired=DENY_KEY
10 expired=DENY_EXPIRED
~~~

Phân tích:
- **01/02:** token đầu tiên còn hạn, account active và quyền server còn đủ.
- **03:** server gỡ reports.export nên từ chối, dù token snapshot từ thời điểm phát hành vẫn chứa reports.export.
- **04:** token ID bị denylist nên không thể đọc, dù token chưa hết hạn.
- **05:** token thứ hai chưa bị revoke vẫn đọc được.
- **06:** disable account làm quyết định truy cập bị từ chối ngay trong **policy simulator**.
- **07:** tăng account epoch khiến token cũ không còn phù hợp, kể cả sau enable account.
- **08:** thêm key B vào trusted set, đổi signingKey sang B và phát hành token mới.
- **09:** retire key A; token cũ bị từ chối tại bước kiểm tra key ID.
- **10:** token có exp=500 bị từ chối khi now=500.

**Không sử dụng demo làm security filter thật:** trustedKeys chỉ là Set<String>, không thực hiện **cryptographic signature verification**; Account và revokedIds chỉ có trong một JVM, không là distributed store; subject được hardcode, không có authentication proof. Trong production phải kết nối các cơ chế đáng tin vào Spring Security authentication/authorization và kiểm soát state consistency trên mọi node.

## 12. Hiệu lực trên hệ thống nhiều node và cache

Để đảm bảo “revoke trong N giây”, phải hiểu độ trễ:
- Ghi account disabled/role removed vào IAM/source store.
- Đồng bộ event đến application databases, replicas hoặc policy services.
- Xóa HttpSessions trong shared repository.
- Refresh/cập nhật JWT public keys và JWK caches.
- Cập nhật jti denylist/token-version store trên mọi Resource Server.
- Invalidating authorization/permission caches của gateway và microservices.
- Thời gian các requests đang xử lý dở hoàn thành.

Một cache TTL 10 phút **không đáp ứng revoke trong 30 giây** nếu thiếu invalidation mechanism. Nhưng kiểm tra state mỗi request có thể tạo bottleneck và tăng phụ thuộc. Đội vận hành phải chọn SLO/reliability và xử lý outages rõ ràng.

**Fail closed:** nếu trạng thái revocation là bắt buộc để bảo vệ API nhạy cảm, lỗi lookup không nên được hiểu là “token được phép”. Có thể áp dụng degraded-mode có phê duyệt cho đường ít nhạy cảm, nhưng không tự động bỏ qua revocation check để tăng availability.

**Long-running jobs:** task đã được lập lịch có thể còn hành động dưới service identity sau khi user bị disable. Cần lưu actor ID, tenant/resource, thực thi authorization theo policy tại lúc chạy, idempotency và audit; không giả tạo authenticated token từ username do caller nhập.

## 13. Runbook vận hành thông thường

### 13.1. Trước thay đổi

Document rõ:
- Phạm vi: issuer, audience, key ID, account ID, client ID, tenants, endpoints, systems.
- Loại thay đổi: rotation định kỳ, key compromised, account offboarding, role downgrade, client-secret revoke.
- Người yêu cầu, người duyệt, owner của hệ thống và người trực ca.
- SLO cho thu hồi truy cập, thời điểm cutover/overlap nếu được phép.
- TTL và cache/repository dependencies, khả năng rollback an toàn.
- Đề xuất kế hoạch test positive/negative, quan sát, cảnh báo.

**Không triển khai rotation khi chưa biết ai đang dùng key/secret cũ.** Một client nằm ngoài inventory có thể bị gián đoạn hoặc tiếp tục dùng credential đã bị thu hồi.

### 13.2. Trong thay đổi

1. Dùng kênh quản lý secrets chính thức, không sao chép private keys hoặc password qua chat.
2. Với rotation bình thường: publish new trust trước cutover signing/consumers.
3. Với compromise: containment nhanh, ngăn tiếp tục dùng credential bị lộ.
4. Với role/account revoke: cập nhật nguồn identity, thu hồi tokens/sessions/grants/caches theo contract.
5. Kiểm thử canary và từng node/region; không chỉ kiểm tra dashboard IAM báo “disabled”.
6. Theo dõi 401/403/login/refresh errors, JWKS validation, token usage và access-denied events.
7. Nếu outage, kiểm tra nguyên nhân và rollback **chỉ khi không tái cấp credential/privilege đã bị thu hồi vì incident**.

### 13.3. Sau thay đổi

- Dùng credential cũ thực hiện negative tests để chứng minh bị từ chối đúng policy.
- Dùng credential mới/identity có quyền để chứng minh luồng hợp lệ vẫn hoạt động.
- Xác minh session store, AS refresh-token store, denylist/epoch và gateway caches.
- Kiểm tra scheduled jobs, service integrations, delegated grants và owner của dữ liệu.
- Lưu audit time, actor, action, scope, verification result, ticket/reference và các hệ thống đã xác minh.
- Không log raw access token, refresh token, private key, password, authorization header hay cookie.

## 14. Thu hồi khẩn cấp khi nghi chiếm đoạt

**Containment:** xác định ảnh hưởng, dừng cấp thêm credentials, disable account/service, revoke tokens/sessions/grants, chặn key compromised ở verifiers và giới hạn endpoints rủi ro cao.

**Investigation:** kiểm tra thời điểm và phạm vi key exposure, IAM changes, IP/device signals, token usage theo ID đã được xác minh, quyền đã thực thi, job nền và dữ liệu có thể bị truy cập.

**Recovery:** phát hành key/credential mới, kiểm tra toàn bộ clients/Resource Servers đã cập nhật, re-enable account chỉ sau khi có xác minh và phê duyệt, triển khai MFA/step-up nếu cần.

**Review:** đo time-to-detect, time-to-disable, time-to-revoke, cache propagation, token/session lifetime và cập nhật playbook. Một system còn chấp nhận token cũ sau revocation SLO là vấn đề cần sửa, không chỉ một cảnh báo.

Không xóa audit trail khi xóa account nếu retention policy cần lưu sự kiện cho điều tra; phải thực hiện masking/minimization theo chính sách dữ liệu.

## 15. Ma trận kiểm thử cho key, quyền, tài khoản và revoke

| Ca | Kỳ vọng |
| --- | --- |
| Token JWT ký key mới, đúng issuer/aud/exp/scope | Được chấp nhận tại API có quyền phù hợp |
| Key cũ còn trong overlap bình thường, token chưa hết hạn | Được chấp nhận nếu policy cho phép |
| Key cũ đã retire | Token cũ bị từ chối sau khi verifiers/caches cập nhật |
| Key compromised đã bị thu hồi | Tất cả verifiers từ chối token từ key bị ảnh hưởng |
| Unknown kid, sai chữ ký/alg, sai issuer/aud/exp | 401; không tin arbitrary key |
| User active, đúng role, tài nguyên thuộc user | 200 và body đúng chủ sở hữu |
| User thiếu role/scope hoặc mất ACL | 403 hoặc policy response tương ứng; không lộ dữ liệu |
| ROLE_ADMIN vừa bị gỡ, session cũ còn sống | Quyền admin bị chặn theo revocation SLO |
| Account bị disable, login mới | Bị từ chối theo mechanism |
| Account disabled, JWT chưa hết hạn | Bị chặn **nếu** contract yêu cầu và có stateful revocation |
| Refresh token bị revoke | Không thể xin token mới qua AS |
| jti được đưa vào denylist | Token đó bị từ chối trên mọi Resource Server |
| Account epoch tăng | Token epoch cũ bị từ chối khi policy check |
| API key/client secret đã retire | Credential cũ không còn xác thực thành công |
| Session bị invalidated | Cookie-session không còn truy cập endpoint bảo vệ |
| IdP/JWKS/revocation store lỗi | Hành vi fail-closed hoặc degraded-policy được thiết kế |
| Nhiều nodes/regions, cache latency | Kết quả đạt revocation SLO ở mọi node |

**Kiểm thử theo tầng:** unit test policy, integration test decoder và token ký thật, HTTP test qua Spring Security FilterChainProxy, end-to-end qua gateway/IdP/session store và test quyền theo đối tượng. MockMvc với **.with(jwt())** hoặc **@WithMockUser** tạo Authentication giả, **không xác minh key rotation/signature hoặc revocation của token thực**.

Ví dụ test authorization MockMvc (trích đoạn, cần controller và imports tương ứng):

~~~java
mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other.read"))))
    .andExpect(status().isForbidden());
~~~

Để kiểm tra signing key rotation, cần test JwtDecoder thật với token ký bằng cặp khóa test và JWKS controlled. Kiểm tra key A trước cutover, A+B trong overlap, retire A, unknown kid, bad signature và caching. Để kiểm tra revoke account, phải kiểm tra state store dùng chung và tuyến HTTP thật; chỉ sửa mock principal trong test không chứng minh account disable hoạt động.

## 16. Metrics, logging và audit

Cần quan sát:
- 401/403 theo endpoint/issuer/client/kid đã được xác minh nếu có và an toàn.
- JWKS fetch/refresh errors, key cache age và số tokens còn sử dụng old kid sau retire.
- OAuth2 token refresh failures, invalid_client, invalid_grant, login errors.
- Số sessions bị invalidated và errors của distributed session store.
- Revocation denylist/epoch lookup latency, outage và propagation.
- Thời gian từ lúc account disabled/role downgrade đến lúc request cũ bị từ chối trên từng node.
- Tỷ lệ quyền admin vẫn được sử dụng sau khi downgrade; access-to-resource ownership anomalies.
- Các event từ user đã offboard, jti revoked, API key đã thu hồi.

Ví dụ audit event minh họa, không phải sự kiện đã thực hiện:

~~~json
{
  "event": "ACCESS_REVOKED",
  "identity": "tenant-A:alice",
  "changeType": "ACCOUNT_DISABLED",
  "actor": "iam-operator-17",
  "approvedChange": "CHG-123",
  "verifiedSystems": ["idp", "web-session", "api"],
  "result": "VERIFIED"
}
~~~

Chỉ ghi trạng thái VERIFIED khi đã có **bằng chứng kiểm thử**. Audit phải có access control, retention và không chứa raw tokens, passwords, client secrets, session cookies hoặc private keys.

## 17. Những sai lầm phổ biến

1. **Đổi password là logout mọi thiết bị.** Không mặc định: session/JWT/refresh token có thể vẫn hoạt động.
2. **Xóa user là thu hồi JWT ngay.** Sai nếu Resource Server chỉ xác minh token cục bộ và không kiểm tra account status.
3. **Gỡ role cập nhật mọi Authentication đã có.** Không; HttpSession/JWT có thể mang authorities cũ.
4. **Revoke refresh token thu hồi access token tức thì.** Không nhất thiết; RS cần cơ chế riêng.
5. **Rotate key mới rồi xóa key cũ ngay trong mọi trường hợp.** Rotation định kỳ thường cần overlap theo TTL.
6. **Key compromised vẫn giữ overlap để không gián đoạn.** Nguy hiểm: attacker vẫn có thể ký token giả.
7. **kid là bằng chứng chữ ký.** Sai; kid chỉ giúp chọn key trong trusted set.
8. **JWT có chữ ký đúng là đủ quyền.** Sai nếu issuer/aud/exp/scope/account/ACL không hợp lệ.
9. **Mock JWT test pass nghĩa là đã kiểm tra revocation.** Sai; test mock bỏ qua xác minh signed token thật.
10. **Một node báo revoke thành công là toàn cluster thành công.** Sai nếu session/JWK/permission caches không đồng bộ.
11. **Logout local browser thu hồi mọi token thiết bị khác.** Không mặc định.
12. **Khôi phục key đã bị lộ để rollback incident.** Không an toàn.
13. **In raw token vào log để debug.** Tạo kênh rò rỉ thứ hai.
14. **403 lúc nào cũng là quyền bị rút.** Có thể do CSRF hoặc policy khác; cần kiểm tra chain và nguyên nhân.
15. **Chỉ xem IAM database để xác nhận.** Không đủ; phải test request tới các hệ thống thật.

## 18. Checklist triển khai an toàn

- [ ] Có inventory keys, token issuers, client credentials, APIs, owners, TTL và caches.
- [ ] Phân biệt key rotation định kỳ với security incident; runbook riêng.
- [ ] Private signing key và client secret không nằm trong source, logs, tickets.
- [ ] JWT được kiểm tra chữ ký, thuật toán, issuer, thời hạn và audience đúng API.
- [ ] Biết publish/switch/overlap/retire JWK theo timeline và đo cache refresh.
- [ ] Có quy trình OAuth2 client secret, API key, TLS/mTLS certificate riêng.
- [ ] Role/permissions được quản lý tại nguồn canonical và áp least privilege.
- [ ] Có kiểm tra ownership/tenant/ACL, không chỉ JWT scope tổng quát.
- [ ] Có SLO cho revoke account và quyền nhạy cảm.
- [ ] Có cơ chế invalidate sessions/remember-me và revoke refresh tokens/grants.
- [ ] Với JWT stateless, có chính sách TTL/revocation state/epoch rõ ràng.
- [ ] Thu hồi credential khác thuộc user, delegated access và scheduled jobs.
- [ ] Có tests token cũ/mới, invalid signature/kid/aud, role downgrade, account disabled, revoke jti.
- [ ] Có kiểm thử nhiều nodes/regions và cache/revocation store failures.
- [ ] Có canary, alert, phê duyệt và rollback không khôi phục key/privileges đã bị thu hồi vì compromise.
- [ ] Audit chứa bằng chứng xác minh, không chứa raw secrets/tokens.

## 19. Câu hỏi tự kiểm tra

1. **Đổi signing key có tự thu hồi token cũ không?** Không nếu verifier vẫn tin key cũ và token chưa hết hạn.
2. **Vì sao rotation định kỳ cần overlap?** Để token đã ký bằng key cũ có thời gian hết hạn an toàn.
3. **Khi private signing key bị lộ có được giữ overlap không?** Không nên; cần containment và rút trust khẩn cấp.
4. **Disable user trong UserDetailsService có chặn JWT stateless sẵn có?** Không mặc định; cần kiểm tra trạng thái/revoke tại Resource Server hoặc nơi kiểm soát phù hợp.
5. **Gỡ ROLE_ADMIN tự cập nhật HttpSession cũ?** Không mặc định; có thể cần invalidate/refresh session hay check quyền động.
6. **Thu hồi refresh token có làm JWT access token hết hạn ngay không?** Không nhất thiết.
7. **Denylist jti nên lưu đâu trong cluster?** Trong state store tin cậy dùng chung với TTL/consistency phù hợp.
8. **JWT ký đúng nhưng audience cho API khác có nên được nhận?** Không.
9. **Vì sao .with(jwt()) không phải test key rotation?** Nó mock Authentication, không kiểm tra chữ ký/JWKS thật.
10. **Offboarding thành công cần bằng chứng gì?** Login mới, refresh, session/token cũ và mọi alternate credentials đều bị xử lý theo revocation contract.
11. **Revocation store bị lỗi thì sao?** Phải tuân theo fail-closed/degraded policy đã phê duyệt, không tự mở quyền.
12. **Vì sao không rollback bằng compromised key?** Vì như thế khôi phục khả năng attacker tạo token giả.

**Kết luận:** Trong Spring Security Servlet, thay đổi khóa, quyền và tài khoản chỉ hoàn tất khi **mọi con đường truy cập cũ được kiểm soát theo vòng đời và mục tiêu thu hồi đã định**. Hãy quản lý JWKS/signing-key rotation, JWT/opaque token, HttpSession, refresh token, roles, account state và resource authorization như các lớp riêng; test cả token/session cũ trên nhiều nodes; audit chính xác và có runbook containment cho sự cố thực tế.
