# Tùy biến giao diện, consent và claims theo tenant

> **Chương: Đa tenant.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài tập trung vào cách tạo trải nghiệm đăng nhập riêng cho từng tenant, hiển thị consent đúng thương hiệu và mục đích, đồng thời phát hành claims phản ánh đúng tenant context.

## 1. Mục tiêu: một Authorization Server, nhiều trải nghiệm và policy

Một Authorization Server phục vụ nhiều tenant có thể dùng chung runtime và host nhưng mỗi tenant cần:

- Tên tổ chức, logo, màu sắc, ngôn ngữ, liên kết hỗ trợ và điều khoản riêng.
- Trang đăng nhập thể hiện đúng tenant và phương thức xác thực được bật.
- Consent screen cho biết ứng dụng nào đang yêu cầu quyền, quyền nào được yêu cầu và dữ liệu nào sẽ được truy cập.
- Claims trong access token, ID Token và UserInfo phản ánh đúng tenant membership và policy của tenant đó.

Ví dụ:

| Thuộc tính | Tenant Acme | Tenant Contoso |
|---|---|---|
| Issuer | **https://auth.example.vn/acme** | **https://auth.example.vn/contoso** |
| Tên hiển thị | Acme Corporation | Contoso Group |
| Logo | Logo Acme đã duyệt | Logo Contoso đã duyệt |
| Ngôn ngữ mặc định | vi-VN | en-US |
| Scope nội bộ | **orders.read**, **orders.write** | **invoices.read**, **reports.export** |
| Claim tenant | **tenant_id=acme** | **tenant_id=contoso** |
| Consent policy | Theo client và principal của Acme | Theo client và principal của Contoso |

Giao diện có thể khác nhau nhưng protocol contract vẫn phải tuân thủ OAuth 2.0/OIDC. Một tenant không được nhận client registration, consent, user profile, authorities hoặc signing key của tenant khác.

## 2. Tách ba lớp: presentation, consent và token claims

| Lớp | Dữ liệu chính | Nguồn tin cậy | Không dùng để |
|---|---|---|---|
| Presentation | Tên, logo, theme, locale, support URL | Tenant configuration đã được duyệt | Quyết định quyền truy cập API |
| Consent | Client, requested scopes, granted scopes, principal | RegisteredClient và OAuth2AuthorizationConsent của đúng tenant | Cấp role tùy ý hoặc sửa authorization request |
| Token claims | Issuer, subject, tenant ID, scope, authorities được phép | AuthorizationServerContext, local user và tenant policy | Sao chép mù claims từ browser hoặc IdP ngoài |

Không dùng màu sắc, logo hay tenant display name làm bằng chứng bảo mật. Việc hiển thị scope trên consent page cũng không có nghĩa scope đó đã được cấp. Chỉ các scope được Authorization Server chấp thuận mới được đưa vào authorization/token context.

### 2.1. Luồng tổng thể

~~~mermaid
flowchart TD
    A["Request tới issuer của tenant"] --> B["Resolve issuer và tenant đã đăng ký"]
    B --> C{"Tenant active?"}
    C -->|Không| X["Từ chối request"]
    C -->|Có| D["Load tenant presentation và policy"]
    D --> E["Login UI theo tenant"]
    E --> F["Xác thực principal"]
    F --> G["Authorization Endpoint kiểm tra client và scopes"]
    G --> H{"Cần consent?"}
    H -->|Có| I["Consent UI theo tenant/client/scope"]
    H -->|Không| J["Tiếp tục authorization"]
    I --> J
    J --> K["Resolve local identity và tenant authorities"]
    K --> L["Token customizer theo loại token"]
    L --> M["Phát local access token / ID Token"]
~~~

## 3. Tenant context phải được xác minh và giữ xuyên suốt flow

Với Spring Authorization Server hỗ trợ path-based issuer, protocol request có thể lấy issuer hiện tại từ **AuthorizationServerContextHolder.getContext()**. Đây là nguồn phù hợp khi đang xử lý authorization endpoint, token endpoint, UserInfo hoặc JWK endpoint.

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException("Issuer context is unavailable");
}

String issuer = context.getIssuer();
Tenant tenant = tenantRegistry.requireByIssuer(issuer);
~~~

AuthorizationServerContextHolder là request context của protocol processing. Không giả định context này còn tồn tại tự động trên application routes như **/login** hoặc **/oauth2/consent** sau khi browser đã được redirect.

### 3.1. Giữ tenant context qua login redirect

Khi authorization request yêu cầu đăng nhập, browser có thể được chuyển từ issuer path sang login page dùng chung. Ở request login page, ứng dụng cần biết authorization transaction ban đầu thuộc tenant nào.

Thiết kế an toàn:

1. Khi nhận authorization request, resolve issuer bằng cơ chế multi-issuer của Authorization Server và xác minh issuer nằm trong tenant registry.
2. Lưu interaction context phía server, gắn với browser session và authorization transaction. Context gồm tenant ID, issuer, thời hạn, correlation ID và trạng thái.
3. Khi render login page, đọc context đã lưu và kiểm tra session, expiry, tenant active.
4. Sau login, chỉ tiếp tục transaction gốc. Không nhận tenant mới từ query string hoặc hidden form field.
5. Xóa interaction context khi flow kết thúc, bị hủy hoặc hết hạn.

Không dùng một biến session đơn như **CURRENT_TENANT** nếu người dùng có thể mở nhiều tab login đồng thời; tab thứ hai có thể ghi đè tenant của tab thứ nhất. Dùng transaction-scoped context có TTL và xử lý concurrent flows.

### 3.2. Không lấy tenant từ Host hoặc query parameter tùy ý

Host, X-Forwarded-Host, path, query parameter và form field có thể bị giả mạo nếu không được kiểm soát ở trust boundary. Nếu tenant được phân giải từ host/path, chỉ chấp nhận canonical route do reverse proxy tin cậy tạo ra và kiểm tra với registry. Không dùng **?tenant=acme** hoặc hidden field **tenant_id=acme** làm căn cứ chọn database, policy hay issuer.

## 4. Mô hình dữ liệu presentation theo tenant

Tạo cấu hình presentation riêng, được quản lý trong tenant registry hoặc configuration store. Không nhồi theme vào access token.

~~~java
import java.net.URI;
import java.util.Locale;

record TenantPresentation(
        String tenantId,
        String displayName,
        String logoAssetPath,
        String themeKey,
        Locale defaultLocale,
        URI supportUri,
        URI privacyPolicyUri,
        URI termsUri) {
}
~~~

Ví dụ cấu hình:

~~~yaml
tenants:
  acme:
    display-name: "Acme Corporation"
    logo-asset-path: "/assets/tenants/acme/logo.svg"
    theme-key: "blue"
    default-locale: "vi-VN"
    support-uri: "https://support.example.vn/acme"
    privacy-policy-uri: "https://example.vn/acme/privacy"
    terms-uri: "https://example.vn/acme/terms"
  contoso:
    display-name: "Contoso Group"
    logo-asset-path: "/assets/tenants/contoso/logo.svg"
    theme-key: "slate"
    default-locale: "en-US"
    support-uri: "https://support.example.vn/contoso"
    privacy-policy-uri: "https://example.vn/contoso/privacy"
    terms-uri: "https://example.vn/contoso/terms"
~~~

Theme key nên là giá trị trong allowlist như **blue**, **slate**, **green**; không nhận CSS tùy ý từ request hoặc tenant admin không có quyền. Logo nên được lưu trong asset store/CDN đã kiểm soát, có kiểm tra content type, kích thước và nguồn. Các URL hỗ trợ/điều khoản phải được validate theo scheme và host policy.

### 4.1. Tách branding khỏi authorization policy

Presentation service có thể trả tên, logo, màu, locale và liên kết hỗ trợ. Authorization policy service mới quyết định tenant active, user membership, client allowed, MFA requirement và granted scopes.

Không cho admin chỉ có quyền chỉnh logo có thể thay đổi scope allowlist, redirect URI, signing key hoặc claim mapping. Dùng permission riêng cho branding, client registration và security policy.

## 5. Tùy biến login page

Spring Security hỗ trợ custom login page thông qua **formLogin().loginPage(...)**. Với Authorization Server, HTML request cần đăng nhập có thể được chuyển tới login entry point cấu hình trong filter chain của ứng dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .permitAll());

    return http.build();
}
~~~

Controller **/login** load TenantPresentation từ interaction context đã được xác minh rồi đưa các giá trị đã kiểm tra vào model:

~~~java
record LoginPageModel(
        String tenantName,
        String logoPath,
        String themeKey,
        String supportUrl,
        String localeTag) {
}
~~~

View dùng tenantName, logoPath, themeKey để render. themeKey chỉ được ánh xạ tới class CSS có sẵn; không đưa raw CSS vào style attribute. Nếu tenant có nhiều phương thức login, hiển thị đúng provider/password/MFA options đã được cấu hình cho tenant đó.

### 5.1. Các nguyên tắc cho login UI

- Không tiết lộ tenant có user/email nào tồn tại qua thông báo lỗi khác nhau.
- Không echo username, password, OTP hoặc token vào HTML.
- Bảo vệ CSRF cho form login; dùng POST và cookie/session policy phù hợp.
- Dùng CSP, output encoding và escaping cho mọi tenant-provided text.
- Không cho returnUrl hoặc continue redirect tới host tùy ý.
- Không load script/CSS từ URL do tenant tùy ý khai báo.
- Khi tenant bị deactivate, chặn login và authorization mới theo policy.

## 6. Tùy biến consent page trong Spring Authorization Server

Spring Authorization Server cho phép chỉ định custom consent URI bằng **authorizationEndpoint(...).consentPage(...)**.

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.with(authorizationServer, server ->
        server.authorizationEndpoint(endpoint ->
                endpoint.consentPage("/oauth2/consent")));
~~~

Khi cần consent, Authorization Endpoint redirect resource owner tới URI đã cấu hình. Theo API documentation của Spring Authorization Server 1.5.8, query string của custom consent page có:

| Parameter | Ý nghĩa |
|---|---|
| client_id | Client identifier của request |
| scope | Các scope được yêu cầu, phân tách bằng dấu cách |
| state | Token bảo vệ consent transaction/CSRF |

state ở consent page là state của bước consent do Authorization Server tạo; không nhầm với state ban đầu do OAuth client gửi trong Authorization Request.

### 6.1. Điểm cần chú ý với path-based multi-issuer

Giá trị consentPage trong configurer là URI cấu hình tĩnh. Redirect mặc định được tài liệu hóa chỉ mang client_id, scope, state; nó không hứa sẽ thêm tenant slug vào query. Vì vậy, với issuer như **https://auth.example.vn/acme** và **https://auth.example.vn/contoso**, không được suy tenant chỉ từ client_id hoặc một tham số do browser gửi.

Nếu dùng một consent page chung:

1. Gắn tenant đã xác minh với authorization interaction ở phía server trước khi chuyển sang custom consent route.
2. Khi render consent, kiểm tra interaction context còn hiệu lực, thuộc browser session/principal hiện tại và khớp state của consent transaction.
3. Lấy tenant từ context đã lưu và tenant registry.
4. Tạo form action tới authorization endpoint của đúng issuer, kết hợp canonical issuer với **AuthorizationServerSettings.getAuthorizationEndpoint()**.
5. Khi POST, để Authorization Server xác minh lại state, client, principal và requested scopes.

Có thể dùng interaction store server-side hoặc một routing strategy được kiểm soát. Không coi tenant query parameter hoặc hidden input là bằng chứng. Nếu không có cơ chế giữ transaction tenant an toàn, hãy dùng default consent page trong protocol path hoặc hoàn thiện tenant-aware consent handoff trước khi bật custom page.

### 6.2. Form consent phải POST về đúng authorization endpoint

Một form consent phải gửi HTTP POST tới authorization endpoint của tenant hiện tại. Form cần giữ nguyên client_id, state và các scope mà user chọn. Ví dụ Thymeleaf minh họa:

~~~html
<form method="post" th:action="${authorizationEndpoint}">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <label th:each="scope : ${requestedScopes}">
        <input type="checkbox"
               name="scope"
               th:value="${scope.name}"
               th:checked="${scope.previouslyGranted}">
        <span th:text="${scope.displayName}"></span>
        <small th:text="${scope.description}"></small>
    </label>

    <button type="submit">Chấp thuận quyền đã chọn</button>
</form>
~~~

Đây là template minh họa; authorizationEndpoint phải được tạo từ issuer/tenant interaction đã xác minh. Controller không được lấy URL POST trực tiếp từ query parameter. Hãy kiểm tra converter và form fields của phiên bản Spring Authorization Server đang dùng trong integration test; không tự bỏ state hoặc thay POST bằng GET.

## 7. Hiển thị client và scope dễ hiểu

Consent page cần cho người dùng biết **ai đang yêu cầu quyền** và **quyền đó cho phép điều gì**.

Thông tin client nên được lấy từ RegisteredClient thuộc repository của tenant hiện tại:

- clientName: tên ứng dụng đã đăng ký.
- clientId: dùng để đối chiếu, không nhất thiết phải hiển thị toàn bộ.
- Scope được client đăng ký và scope thực tế đang được yêu cầu.
- Redirect URI/domain có thể hiển thị dưới dạng thông tin nguồn gốc đã được kiểm tra, nếu UX/policy yêu cầu.

Có thể lưu thêm client presentation trong repository riêng, khóa bằng (tenant_id, client_id), gồm icon đã duyệt, publisher, mô tả, privacy URL và support URL. Không tin client_name, logo URL hoặc privacy URL truyền trong query string.

### 7.1. Scope catalog theo tenant

Một scope code có thể có cách diễn giải khác nhau theo tenant hoặc product. Dùng catalog đã duyệt:

~~~java
record ScopePresentation(
        String scope,
        String displayName,
        String description,
        String dataCategory,
        String riskLevel,
        String purpose) {
}
~~~

Ví dụ:

| Scope | Tên hiển thị | Mô tả |
|---|---|---|
| orders.read | Xem đơn hàng | Cho phép ứng dụng xem đơn hàng thuộc tenant |
| orders.write | Quản lý đơn hàng | Cho phép tạo hoặc cập nhật đơn hàng |
| invoices.read | Xem hóa đơn | Cho phép ứng dụng đọc hóa đơn được cấp quyền |
| reports.export | Xuất báo cáo | Cho phép tạo bản xuất báo cáo theo policy |

Không suy diễn quyền từ tên scope. Scope catalog phải khớp scope thực tế đã đăng ký và policy của Resource Server.

### 7.2. Requested, previously granted và newly requested

Consent UI nên phân biệt:

- **Requested scopes:** scope trong authorization request hiện tại.
- **Previously granted scopes:** scope user đã cấp cho client này trong tenant này.
- **Newly requested scopes:** scope mới mà user cần xem xét.
- **Selected scopes:** subset mà user chọn cấp trong lần này.

OAuth2AuthorizationConsentService.findById(registeredClientId, principalName) có thể được dùng để lấy consent hiện tại. Trong multi-tenant, service phải được delegate theo issuer/tenant; không truy vấn consent store dùng chung mà thiếu tenant discriminator.

Không đánh dấu scope là đã chấp thuận chỉ vì client từng yêu cầu nó. Chỉ consent được lưu mới là nguồn để xác định previously granted scopes.

## 8. Lưu consent theo tenant và principal

OAuth2AuthorizationConsent biểu diễn authorities mà resource owner đã cấp cho một RegisteredClient. Các trường cốt lõi gồm:

| Trường | Ý nghĩa |
|---|---|
| registeredClientId | ID nội bộ của RegisteredClient |
| principalName | Tên principal/resource owner |
| authorities | Scope hoặc authority đã được chấp thuận |

Trong kiến trúc multi-issuer, consent store phải được cô lập theo tenant. Nếu hai tenant có cùng client_id hoặc cùng principal name, consent của tenant A không được làm tenant B bỏ qua consent.

Các nguyên tắc:

- Dùng tenant-aware OAuth2AuthorizationConsentService.
- Unique key trong shared table phải bao gồm tenant discriminator.
- Khi đọc consent, xác minh client thuộc tenant hiện tại.
- Khi ghi consent, chỉ lưu subset scope mà user thực sự chọn.
- Khi client scope bị thu hẹp hoặc tenant policy thay đổi, có quy trình xử lý consent cũ.
- Có thể yêu cầu consent lại khi scope nhạy cảm tăng hoặc policy thay đổi.

## 9. Claims theo tenant trong access token và ID Token

Spring Authorization Server cho phép tùy biến JWT claims bằng OAuth2TokenCustomizer<JwtEncodingContext>. Context cung cấp token type, principal, RegisteredClient, authorized scopes và AuthorizationServerContext. Nhờ đó customizer có thể lấy issuer/tenant hiện tại từ context và gọi tenant policy service.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tenantClaimsCustomizer(
        TenantRegistry tenantRegistry,
        TenantClaimsService tenantClaimsService) {

    return context -> {
        String issuer = context.getAuthorizationServerContext().getIssuer();
        Tenant tenant = tenantRegistry.requireByIssuer(issuer);

        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            TenantAuthorities authorities =
                    tenantClaimsService.authoritiesFor(
                            tenant.id(), context.getPrincipal());

            context.getClaims().claim("tenant_id", tenant.id());
            context.getClaims().claim("tenant_roles", authorities.roles());
        }

        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            LocalProfile profile =
                    tenantClaimsService.profileFor(
                            tenant.id(), context.getPrincipal());

            context.getClaims().claim("tenant_id", tenant.id());

            if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
                context.getClaims().claim("name", profile.displayName());
            }

            if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)
                    && profile.emailVerified()) {
                context.getClaims().claim("email", profile.email());
                context.getClaims().claim("email_verified", true);
            }
        }
    };
}
~~~

TenantRegistry, TenantClaimsService, TenantAuthorities và LocalProfile là kiểu nghiệp vụ do ứng dụng định nghĩa. Customizer chỉ dùng issuer trong JwtEncodingContext và local membership đã được kiểm tra; không lấy tenant ID từ request parameter hoặc principal attribute chưa xác minh.

### 9.1. Access token và ID Token có mục đích khác nhau

| Claim/data | Access token | ID Token |
|---|---|---|
| tenant_id | Khi Resource Server cần tenant context | Khi RP cần biết user đang ở tenant nào |
| Tenant roles/permissions | Chỉ khi API cần authorization claim | Thường không cần |
| name, email | Tránh nếu API không cần | Theo OIDC scope và consent |
| Logo, theme, support URL | Không nên đưa vào | Không nên đưa vào |
| Issuer, subject, audience, expiry | Do AS phát hành theo token contract | Do OP phát hành theo OIDC contract |

Không đưa toàn bộ tenant profile hoặc PII vào mọi token. JWT là bearer credential; token có thể bị lưu trong browser, log hoặc telemetry của client. Chỉ phát claims cần thiết cho consumer tương ứng.

### 9.2. Không ghi đè claims chuẩn

Tenant customizer không được ghi đè claims do Authorization Server sở hữu như iss, sub, aud, iat, exp, nonce, azp, auth_time, at_hash hoặc c_hash. Local subject phải ổn định theo issuer và local identity policy.

Nếu có nhiều nhu cầu custom claim, hợp nhất logic vào một OAuth2TokenCustomizer<JwtEncodingContext> có dispatch theo token type và service; tránh khai báo nhiều bean cùng generic type gây xung đột hoặc không rõ thứ tự.

## 10. Tùy biến UserInfo theo tenant

OIDC UserInfo endpoint là protected resource và yêu cầu access token Bearer. Spring Authorization Server cho phép cấu hình userInfoMapper để tạo OidcUserInfo theo authorization, tenant và scope.

Ví dụ skeleton:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            String issuer = AuthorizationServerContextHolder.getContext().getIssuer();
            Tenant tenant = tenantRegistry.requireByIssuer(issuer);

            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();
            LocalProfile profile = profileService.load(
                    tenant.id(), context.getAuthorization().getPrincipalName());

            Map<String, Object> claims = new HashMap<>();
            claims.put("sub", profile.subject());

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.displayName());
            }

            if (scopes.contains(OidcScopes.EMAIL) && profile.emailVerified()) {
                claims.put("email", profile.email());
                claims.put("email_verified", true);
            }

            return new OidcUserInfo(claims);
        };
~~~

Đăng ký mapper trong OIDC configurer của Authorization Server:

~~~java
authorizationServer.oidc(oidc ->
        oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)));
~~~

Đây là skeleton; ứng dụng cần kiểm tra null và lỗi tenant/profile theo policy. UserInfo mapper phải xác định tenant từ request context đã xác minh, lấy profile trong đúng tenant và chỉ trả claims phù hợp với scope/policy. sub trong UserInfo phải khớp subject của ID Token cho cùng user/issuer.

Có thể chọn thêm claims theo tenant nếu client có use case, nhưng phải định nghĩa contract và consent rõ. Không trả internal roles, support metadata hay PII chỉ vì chúng có trong database.

## 11. Tổ chức cấu hình theo tenant

Một cấu trúc service có thể tách thành:

| Component | Trách nhiệm |
|---|---|
| TenantRegistry | Tra cứu tenant theo canonical issuer và trạng thái |
| TenantPresentationService | Tên, logo, theme, locale, legal/support links |
| TenantInteractionContextStore | Giữ tenant đã xác minh qua login/consent redirect |
| TenantClientPresentationService | Display metadata của client trong tenant |
| TenantScopeCatalog | Mô tả scope và phân loại mức nhạy cảm |
| TenantConsentPolicy | Quyết định consent cần thiết, re-consent và policy |
| TenantClaimsService | Local profile, membership, authorities và claim allowlist |
| TenantAwareAuthorizationConsentService | Lưu/đọc consent theo tenant |
| TenantAwareTokenCustomizer | Thêm claims theo token type và issuer |

Không để một singleton mutable thay đổi currentTenant theo từng request. Mỗi service nhận tenant ID đã xác minh như tham số hoặc lấy từ request context đúng vòng đời.

### 11.1. Cấu hình tĩnh và động

Với số tenant ít, presentation/scope catalog có thể nạp lúc startup. Với tenant onboard động, cần workflow có xác thực:

1. Admin/control plane đã xác thực tạo tenant configuration.
2. Validate theme key, logo asset, locale và external URLs.
3. Validate scope catalog chỉ chứa scope đã được policy cho phép.
4. Provision presentation, consent policy và claims mapping.
5. Publish configuration version.
6. Chỉ active khi issuer và các component multi-tenant cốt lõi đã sẵn sàng.
7. Audit thay đổi và có rollback/version history.

Thay đổi branding không nên cần đổi signing key. Thay đổi authorization policy hoặc claim mapping cần review và kiểm thử riêng.

## 12. Bảo mật giao diện và claims

### 12.1. Presentation security

- Escape mọi nội dung tenant/client trong template.
- Chỉ dùng CSS theme key từ allowlist.
- Không render HTML tùy ý từ tenant configuration.
- Validate logo URL/asset và giới hạn host, content type, size.
- Bật CSP, frame protection, secure cookie, HSTS và TLS theo deployment.
- Không hiển thị thông tin nhạy cảm trong query string.
- Không đưa client secret, token hoặc raw authorization request vào model/view.

### 12.2. Consent security

- Chỉ render client đã được lookup trong RegisteredClientRepository của tenant hiện tại.
- client_id, scope, state từ query là input cần kiểm tra, không phải dữ liệu đã được authorize.
- Giữ nguyên state, dùng HTTP POST và gửi về authorization endpoint đúng tenant.
- Chỉ chấp nhận subset scope nằm trong requested scopes và RegisteredClient allowlist.
- Không cho form gửi scope tùy ý để mở rộng quyền.
- Từ chối/reject phải đi qua consent protocol của Spring Authorization Server, không tự phát authorization code.
- Không dùng redirect_uri từ consent form làm action.

### 12.3. Claims security

- Claims được lấy từ local user store và tenant membership đã xác minh.
- Scope/consent quyết định profile claims nào được phát.
- Resource Server vẫn phải validate issuer, audience, signature, expiry và authorities.
- Không tin tenant_id trong token trước khi token được validate.
- Không cho client tự gửi tenant claim để ghi đè token.
- Không phát PII/role vượt quá mục đích của consumer.

## 13. Ma trận kiểm thử giao diện, consent và claims

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Mở login của Acme | Logo, tên, theme và locale Acme |
| 2 | Mở login của Contoso | Không có branding của Acme |
| 3 | Tenant không active | Login/authorization mới bị từ chối |
| 4 | Tenant theme key lạ | Dùng theme an toàn hoặc từ chối config |
| 5 | Logo URL ngoài allowlist | Không tải asset |
| 6 | Tenant name chứa HTML/script | Render escaped, không XSS |
| 7 | Hai tab login hai tenant | Interaction context không ghi đè nhau |
| 8 | Login page request không có transaction | Không suy tenant từ query/Host tùy ý |
| 9 | Consent cho client thuộc Acme | Hiển thị client metadata của Acme |
| 10 | Cùng client ID tồn tại ở hai tenant | Mỗi consent hiển thị metadata đúng tenant |
| 11 | Client ID không tồn tại | Từ chối, không hiển thị client do query tự khai |
| 12 | Scope requested có trong allowlist | Hiển thị mô tả scope đúng |
| 13 | Scope không được RegisteredClient cho phép | Authorization request bị từ chối |
| 14 | Scope nhạy cảm mới | Hiển thị risk/purpose và yêu cầu consent |
| 15 | Scope đã được grant trước | Hiển thị rõ previously granted |
| 16 | User chỉ chọn một phần scopes | Chỉ lưu subset được chấp thuận |
| 17 | User từ chối consent | Không phát authorization code |
| 18 | Consent form gửi GET | Bị từ chối; chỉ nhận POST |
| 19 | Consent state bị sửa | Authorization endpoint từ chối |
| 20 | Consent form post tới issuer tenant khác | Không cấp authorization |
| 21 | Consent page thiếu tenant interaction | Fail closed, không fallback |
| 22 | Consent store Acme được query từ Contoso | Không trả consent chéo |
| 23 | Access token Acme | tenant_id và authorities thuộc Acme |
| 24 | Access token Contoso | Không chứa authorities Acme |
| 25 | ID Token có scope profile | Chỉ có profile claims được phép |
| 26 | ID Token không có scope email | Không trả email claims |
| 27 | Email chưa verified | Không đánh dấu email_verified=true |
| 28 | Customizer nhận refresh token | Không thêm claims chỉ dành cho JWT access/ID Token |
| 29 | ID Token customizer | Không ghi đè iss/sub/aud/exp/nonce |
| 30 | UserInfo bằng access token Acme | Profile và sub của Acme |
| 31 | UserInfo bằng token Contoso | Không đọc profile Acme |
| 32 | UserInfo sub khác ID Token sub | RP test phát hiện và từ chối |
| 33 | Tenant role bị thu hồi | Token mới không còn role; token cũ theo revocation/expiry policy |
| 34 | Thay đổi branding khi nhiều pod chạy | Mọi pod dùng cùng presentation version |
| 35 | Claims config lỗi hoặc thiếu | Không phát claim mặc định cấp quyền rộng |

### 13.1. Integration test cần kiểm tra end-to-end

Một flow test hoàn chỉnh nên:

1. Gửi authorization request tới issuer Acme với client và scopes hợp lệ.
2. Xác minh login page dùng presentation Acme.
3. Xác thực user thuộc Acme.
4. Xác minh consent page hiển thị đúng client, requested scopes và mô tả Acme.
5. Chấp thuận một subset scope rồi POST về authorization endpoint Acme.
6. Đổi authorization code tại token endpoint Acme.
7. Decode và validate local access token/ID Token: issuer, audience, subject, scope và tenant claims.
8. Gọi UserInfo bằng access token và kiểm tra profile thuộc Acme.
9. Lặp lại với Contoso và xác minh không có client, consent, theme hoặc claim rò chéo.

## 14. Troubleshooting, checklist production và câu hỏi tự đánh giá

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Login page luôn dùng theme mặc định | Không giữ tenant interaction qua redirect | Bổ sung server-side interaction context |
| Login page hiển thị nhầm tenant khi mở nhiều tab | Dùng một session attribute currentTenant | Dùng transaction-scoped context |
| Consent page không biết issuer | Custom consent URI tĩnh, query không có tenant | Giữ tenant binding phía server và kiểm tra state |
| Consent form quay về issuer gốc | Action dùng endpoint mặc định không có tenant path | Build action từ canonical issuer đã xác minh |
| Client name trên consent sai | Lookup từ query hoặc global client registry | Lookup RegisteredClient theo tenant |
| Previously granted scopes sai | Consent service không tenant-aware | Delegate store theo issuer |
| User chọn scope nhưng token không có | Scope bị giới hạn bởi policy/consent | Kiểm tra granted scopes và token context |
| Token chứa role tenant khác | Claims service không nhận tenant ID hoặc cache thiếu tenant | Tenant-aware lookup/cache key |
| ID Token có email dù không yêu cầu | Customizer không kiểm tra authorized scopes | Gate claims theo scope và policy |
| UserInfo trả profile sai tenant | Mapper dùng principalName toàn cục | Resolve tenant và local identity trong cùng context |
| Customizer ghi đè claim chuẩn | Copy map claims không lọc | Dùng allowlist và giữ reserved claims |
| Tenant theme thay đổi không đồng bộ | Cache không có version/invalidation | Versioned config và cache invalidation |

### 14.1. Checklist production

- [ ] Presentation, consent policy và claims policy là các component riêng.
- [ ] Tenant được resolve từ issuer/transaction context đã xác minh.
- [ ] Login và consent UI giữ tenant context theo từng transaction, hỗ trợ nhiều tab.
- [ ] Không lấy tenant từ query, hidden input hoặc forwarded header không tin cậy.
- [ ] Branding config dùng allowlist theme/assets/URLs và output escaping.
- [ ] Consent page tra RegisteredClient từ repository của tenant hiện tại.
- [ ] Consent hiển thị requested, previously granted và newly requested scopes rõ ràng.
- [ ] Form consent dùng POST, giữ state và gửi tới authorization endpoint đúng issuer.
- [ ] Consent store được tenant-aware.
- [ ] Token customizer kiểm tra token type, issuer, principal, authorized scopes và tenant membership.
- [ ] Access token và ID Token chỉ chứa claims cần thiết cho consumer.
- [ ] Không ghi đè claims chuẩn của Authorization Server.
- [ ] UserInfo chỉ trả claims theo scope/consent/policy và đúng tenant.
- [ ] Cache key bao gồm tenant ID/issuer và có version/invalidation.
- [ ] Có negative tests chống cross-tenant UI, consent, claims và UserInfo.
- [ ] Có audit cho thay đổi branding, scope catalog, consent policy và claim mapping.
- [ ] Log/trace không chứa token, state thô hoặc PII không cần thiết.

**Câu hỏi tự đánh giá**

1. Vì sao presentation, consent và token claims phải là ba lớp riêng?
2. Khi xử lý protocol request, lấy issuer hiện tại từ đâu?
3. Vì sao AuthorizationServerContextHolder không tự động có mặt ở custom login page?
4. Làm thế nào giữ tenant context khi người dùng mở nhiều tab authorization?
5. Vì sao không dùng tenant_id query parameter làm căn cứ chọn tenant?
6. consentPage(...) của Spring Authorization Server nhận những query parameters nào?
7. state ở consent page có giống state do OAuth client gửi ban đầu không?
8. Form consent phải POST tới endpoint nào và cần giữ các trường nào?
9. Làm thế nào lấy client name an toàn cho consent page?
10. Khác nhau giữa requested scopes và previously granted scopes là gì?
11. Vì sao consent store phải tenant-aware khi client ID có thể trùng giữa tenant?
12. OAuth2TokenCustomizer<JwtEncodingContext> có thể lấy tenant context từ đâu?
13. Vì sao access token và ID Token không nên chứa cùng một tập claims?
14. Khi nào nên đưa tenant_id vào access token?
15. Vì sao không copy toàn bộ upstream/local claims vào JWT?
16. UserInfo mapper cần kiểm tra tenant, scope và subject như thế nào?
17. Làm thế nào phát hiện lỗi rò theme, consent hoặc profile giữa hai tenant?

## Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization endpoint configurer, consent page và extension points.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): consentPage(String) và form contract.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, clientName, OAuth2AuthorizationConsent và OAuth2TokenContext.
- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): issuer context và tenant-aware component registry.
- [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): ID Token customizer và UserInfo mapper.
- [Spring Authorization Server 1.5.8 — How-to: Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): access token claim customization và token type check.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): custom login page và form authentication.
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection cho browser-based forms.
