# Đưa roles, authorities hoặc thông tin nghiệp vụ vào claims có kiểm soát

## 1. Vì sao cần kiểm soát claims?

Trong một hệ thống **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security, Spring Authorization Server và Spring Boot**, access token thường mang các thông tin để Resource Server quyết định một request có được phép truy cập hay không. Ngoài các claim chuẩn như iss, sub, aud, exp, token có thể cần thêm **roles**, **authorities**, **tenant**, **organization** hoặc một số thuộc tính nghiệp vụ.

Ví dụ, API quản lý đơn hàng cần biết:

- Người gọi là ai (sub).
- Token được phát hành bởi Authorization Server nào (iss).
- Token dành cho API nào (aud).
- Token được cấp quyền OAuth nào (scope).
- Người dùng có vai trò nghiệp vụ nào, chẳng hạn ORDER_MANAGER.
- Người dùng thuộc tenant nào để API không đọc nhầm dữ liệu tenant khác.

Đưa thông tin vào token giúp Resource Server có thể ra quyết định mà không phải gọi lại Authorization Server trong mọi request. Nhưng token cũng trở thành **một bản sao quyền hạn tại thời điểm phát hành**. Nếu đưa quá nhiều dữ liệu, lấy nhầm nguồn hoặc để claim cũ tồn tại quá lâu, hệ thống có thể lộ dữ liệu hoặc cấp quyền vượt mức cần thiết.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, mục tiêu là học cách **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot**. Bài này thuộc chương **Token và claims**, tập trung vào nguyên tắc đưa roles, authorities và thông tin nghiệp vụ vào token theo **least privilege**, đúng loại token, đúng audience và có kiểm soát vòng đời.

Sau bài học, bạn có thể:

1. Phân biệt **OAuth scopes**, **Spring Security authorities**, **roles** và **business claims**.
2. Chọn claim cần thiết, nguồn dữ liệu đáng tin cậy và phạm vi audience phù hợp.
3. Dùng OAuth2TokenCustomizer<JwtEncodingContext> để tùy biến JWT access token trong Spring Authorization Server.
4. Hiểu sự khác nhau giữa JWT và opaque/reference access token khi bổ sung claims.
5. Ánh xạ claims thành authorities ở Resource Server và thực thi quyền tại API.
6. Kiểm thử token claims, tenant isolation, token cũ sau khi quyền thay đổi và các trường hợp không được phát hành claim.

**Phạm vi ví dụ:** API minh họa theo Spring Authorization Server 1.5.x và Spring Security 6.x trên Servlet stack. Một số cấu hình có thể khác ở Spring Security 7.x hoặc phiên bản mới hơn; hãy kiểm tra Javadoc và tài liệu tương ứng với dependency của dự án.

## 2. Phân biệt scopes, authorities, roles và business claims

Những khái niệm này liên quan nhưng không thể thay thế tùy tiện cho nhau.

| Khái niệm | Ý nghĩa | Ví dụ | Nguồn thường dùng |
| --- | --- | --- | --- |
| **OAuth scope** | Phạm vi quyền mà client yêu cầu và Authorization Server cấp cho một authorization | orders.read, orders.write | RegisteredClient, authorization request, consent và policy cấp quyền |
| **Spring Security authority** | Quyền mà Spring Security dùng trong quyết định authorization | SCOPE_orders.read, ROLE_ORDER_MANAGER | GrantedAuthority trong Authentication hoặc converter ở Resource Server |
| **Role** | Nhóm quyền nghiệp vụ ở mức tương đối rộng | ORDER_MANAGER, SUPPORT_AGENT | Identity/user directory hoặc hệ thống phân quyền nghiệp vụ |
| **Permission/entitlement** | Quyền chi tiết cho một hành động hoặc tài nguyên | invoice.approve, customer.export | Policy/entitlement service |
| **Business claim** | Thuộc tính mô tả chủ thể hoặc ngữ cảnh nghiệp vụ | tenant_id, organization_id, account_tier | Dữ liệu nghiệp vụ đáng tin cậy, đã kiểm tra quyền truy cập |

Ví dụ, người dùng có role ORDER_MANAGER không đồng nghĩa mọi OAuth client đều được cấp scope orders.write. Scope là quyền được cấp cho **một client và authorization cụ thể**; role là thuộc tính quyền nghiệp vụ của **người dùng**. Authorization Server phải quyết định sự kết hợp này theo policy.

### 2.1. Không biến mọi authority thành scope

Một Authentication có thể chứa:

```text
ROLE_ORDER_MANAGER
ROLE_SUPPORT_AGENT
SCOPE_orders.read
SCOPE_orders.write
MFA_AUTHENTICATED
IP_TRUSTED
```

Không nên lấy tất cả giá trị trên rồi ghi thẳng vào claim scope:

- ROLE_ORDER_MANAGER là role, không phải OAuth scope đã được cấp.
- MFA_AUTHENTICATED có thể là trạng thái xác thực, không phải quyền gọi API.
- IP_TRUSTED có thể chỉ đúng ở thời điểm/đường truyền hiện tại, không nên biến thành quyền lâu dài trong JWT.
- Scope cần tuân thủ authorization grant, client policy và consent; không được nâng scope chỉ vì principal có role cao.

Giữ claim scope theo ngữ nghĩa OAuth. Nếu cần truyền role, dùng claim riêng như roles; nếu cần permission chi tiết, dùng claim riêng có schema rõ ràng.

### 2.2. Ví dụ token access cho API đơn hàng

Một JWT access token minh họa có thể chứa:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f31",
  "aud": ["orders-api"],
  "iat": 1794820200,
  "exp": 1794820800,
  "scope": "orders.read",
  "roles": ["ORDER_MANAGER"],
  "https://claims.example.com/tenant_id": "tenant-42"
}
```

Các giá trị trên chỉ để minh họa. Scope cho biết OAuth permission được cấp; roles và tenant_id là custom claims theo chính sách của hệ thống. API vẫn phải kiểm tra issuer, audience, thời hạn, chữ ký và quyền trên endpoint. Claim tenant_id không thay thế việc kiểm tra dữ liệu thuộc tenant nào trong truy vấn.

## 3. Chọn claim theo nguyên tắc least privilege

Trước khi thêm một claim, hãy trả lời bốn câu hỏi:

1. **Ai cần đọc claim này?** Một Resource Server, nhiều API hay OAuth client?
2. **Quyết định nào phụ thuộc vào claim?** Phân quyền, tenant isolation, hiển thị UI hay chỉ phục vụ telemetry?
3. **Claim có nhạy cảm hoặc thay đổi thường xuyên không?** Có phải PII, dữ liệu hợp đồng, trạng thái tài khoản hoặc thông tin nội bộ?
4. **Claim cần chính xác đến thời điểm nào?** Có thể chấp nhận dữ liệu tại thời điểm token được phát hành hay cần kiểm tra realtime?

Một claim chỉ nên xuất hiện nếu có consumer và mục đích rõ ràng. Đừng đưa toàn bộ hồ sơ người dùng vào JWT với lý do “sau này có thể cần”.

### 3.1. Ma trận lựa chọn dữ liệu

| Dữ liệu | Có nên đưa vào access token? | Điều kiện |
| --- | --- | --- |
| sub ổn định | **Có**, thường là claim chuẩn | Dùng subject không chứa thông tin cá nhân dễ đoán; nhất quán theo issuer |
| scope | **Có**, theo grant được cấp | Không tự mở rộng từ role hoặc client registration |
| Role nghiệp vụ cần API dùng | **Có thể** | Chọn allowlist, giới hạn audience và TTL, có kế hoạch khi role thay đổi |
| Permission chi tiết | **Có thể** | Chỉ khi kích thước token và độ mới dữ liệu phù hợp; không đưa danh sách khổng lồ |
| tenant_id | **Có thể** | Lấy từ membership đã xác minh, ràng buộc với subject và client |
| organization_id | **Có thể** | Chỉ nếu API cần; không tin giá trị client tự gửi |
| Email, số điện thoại, địa chỉ | **Thường tránh** | Chỉ đưa khi API thực sự cần và đã đánh giá PII, consent, retention |
| Mật khẩu, client secret, refresh token, private key | **Không bao giờ** | Đây là credential hoặc bí mật |
| Số dư, hạn mức, trạng thái đơn hàng hiện tại | **Thường không nên** | Thay đổi liên tục; API nên truy vấn nguồn nghiệp vụ |
| Feature flag/UI preference | **Thường không cần** | Không dùng access token như hồ sơ cấu hình giao diện |
| Dữ liệu nhạy cảm về sức khỏe/tài chính | **Tránh** | Nếu bắt buộc, cần threat model, kiểm soát pháp lý và kiến trúc phù hợp |

### 3.2. JWT ký số không có nghĩa là payload được mã hóa

JWT dạng JWS thường có cấu trúc:

```text
base64url(header).base64url(payload).signature
```

Payload có thể được đọc bởi bất kỳ bên nào sở hữu token. Chữ ký bảo vệ tính toàn vẹn và xác thực nguồn phát hành, **không che giấu nội dung**. Vì vậy:

- Không đưa password, secret, private key hoặc refresh token vào claims.
- Hạn chế PII và dữ liệu nội bộ không cần thiết.
- Không đưa dữ liệu mà client không được phép biết chỉ vì token đã ký.
- Nếu cần giữ claims kín giữa AS và Resource Server, cân nhắc opaque/reference token với introspection hoặc một cơ chế token mã hóa được thiết kế và hỗ trợ rõ ràng.

Opaque token cũng là bearer credential; giá trị opaque không làm cho việc truyền/lưu token trở nên vô hại.

## 4. Chọn đúng loại token

Không phải token nào cũng dành cho cùng một đối tượng nhận.

| Loại token | Consumer chính | Claim phù hợp | Điều cần tránh |
| --- | --- | --- | --- |
| **Access token** | Resource Server/API | Scope, audience, subject, roles/permissions/tenant khi API cần | Nhồi hồ sơ người dùng hoặc quyền cho API khác |
| **ID token** | OIDC Client/Relying Party | Claims xác thực người dùng theo OIDC và yêu cầu client | Dùng ID token thay access token hoặc nhét toàn bộ API permissions vào ID token |
| **Refresh token** | Token Endpoint | Thông thường là credential opaque/stateful, không phải hồ sơ claims để API đọc | Đưa dữ liệu nghiệp vụ vào refresh token hoặc gửi nó đến Resource Server |
| **Authorization code** | Token Endpoint | Credential dùng một lần gắn với authorization | Coi code là token gọi API |

Trong bài này, ví dụ chính tập trung vào **JWT access token**. Khi tùy biến JWT, cần kiểm tra token type để không vô tình thêm roles, tenant_id hoặc permission API vào ID token.

## 5. Spring Authorization Server: nơi tùy biến JWT access token

### 5.1. Vai trò của OAuth2TokenCustomizer<JwtEncodingContext>

Spring Authorization Server cho phép tùy biến claims/header khi mã hóa JWT thông qua:

```java
OAuth2TokenCustomizer<JwtEncodingContext>
```

JwtEncodingContext cung cấp ngữ cảnh token đang được tạo, bao gồm các thông tin như:

- getTokenType(): loại token đang được sinh.
- getRegisteredClient(): client registration.
- getPrincipal(): authentication principal trong grant context.
- getAuthorizationGrantType(): loại grant.
- getAuthorizedScopes(): scope đã được cấp cho authorization.
- getAuthorization(): authorization hiện tại nếu có.
- getClaims(): builder để thêm/chỉnh JWT claims.
- getJwsHeader(): builder cho JOSE header.

**Không thêm claims trước khi kiểm tra token type.** JWT customizer có thể được dùng ở những luồng JWT khác nhau tùy cấu hình/generator; chỉ thêm role/business claims khi đang sinh access token theo chính sách đã định.

Authorization context và persistence cũng cần được hiểu đúng:

- **RegisteredClientRepository** cung cấp cấu hình client như grant types, scopes, redirect URIs và token settings.
- **OAuth2AuthorizationService** lưu/tra cứu authorization và token state; OAuth2Authorization giữ registered client ID, principal name, grant type, authorized scopes, attributes và token metadata.
- **OAuth2TokenGenerator** tạo token theo context do authentication provider xây dựng; customizer chỉ bổ sung claims trong lúc mã hóa, không phải nơi tự cấp consent hoặc nâng scope.

Khi đưa roles vào JWT, hãy lấy scope từ authorization context và role từ nguồn phân quyền nghiệp vụ đã xác minh. Không dùng tập scopes được đăng ký trên client để thay thế authorized scopes của grant cụ thể.

### 5.2. Dữ liệu role phải đến từ nguồn đáng tin cậy

Tạo một service chuyên trách để lấy role đã được xác minh:

```java
import java.util.Set;

public interface UserRoleClaimService {
    /**
     * Trả về các role nghiệp vụ đã được xác minh cho subject.
     * Giá trị trả về không chứa tiền tố Spring "ROLE_".
     */
    Set<String> rolesForSubject(String subject);
}
```

Implementation có thể đọc từ user/entitlement store, cache có invalidation hoặc một policy service được quản lý. Không lấy role từ:

- Request parameter, query string hoặc header do người dùng tự gửi.
- Authentication.getDetails() nếu đó là dữ liệu client có thể kiểm soát.
- JWT do client tự đưa vào mà chưa xác minh chữ ký/issuer/audience.
- Tên client hoặc scope rồi suy luận rằng người dùng có role tương ứng.

### 5.3. Ví dụ customizer chỉ thêm role vào access token

Ví dụ dưới đây minh họa cho authorization code và refresh grant của người dùng. Service trả role names đã được kiểm tra; customizer áp dụng allowlist để tránh đưa authorities nội bộ vào token:

```java
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
public class AccessTokenClaimsConfiguration {

    private static final Set<String> EXPOSED_ROLES =
            Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer(
            UserRoleClaimService roleClaimService) {

        return context -> {
            // Không thêm các claim nghiệp vụ này vào ID token.
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            AuthorizationGrantType grantType =
                    context.getAuthorizationGrantType();
            boolean userGrant =
                    AuthorizationGrantType.AUTHORIZATION_CODE.equals(grantType)
                    || AuthorizationGrantType.REFRESH_TOKEN.equals(grantType);
            if (!userGrant) {
                return;
            }

            String subject = context.getPrincipal().getName();
            Set<String> roles = roleClaimService.rolesForSubject(subject).stream()
                    .filter(EXPOSED_ROLES::contains)
                    .collect(Collectors.toUnmodifiableSet());

            if (!roles.isEmpty()) {
                context.getClaims().claim("roles", roles);
            }
        };
    }
}
```

**Đây là mẫu cần điều chỉnh theo principal và policy thực tế của ứng dụng.** Xác nhận rằng principal trong authorization code và refresh grant là user principal mà service mong đợi; không giả định getPrincipal().getName() luôn là user ID ở mọi grant. Với refresh token, kiểm tra cách phiên bản đang dùng xây dựng token context và cách lấy subject ổn định từ authorization. Nếu principal không đại diện user, không truy vấn role theo tên client rồi ghi vào roles.

Ví dụ cố ý **không** thêm claim scope: Spring Authorization Server đã tạo claims token theo authorization context. Đừng ghi đè scope mặc định bằng danh sách role.

### 5.4. Không đưa role người dùng vào client_credentials token

Với client_credentials, principal đại diện client/application, không phải end user. Không nên áp dụng đoạn tra cứu user role như trên. Nếu Resource Server cần quyền máy-máy, hãy thiết kế claim riêng cho client, ví dụ client_permissions, dựa trên **policy của chính RegisteredClient** hoặc entitlement service:

```java
if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
        context.getAuthorizationGrantType())) {
    // Đọc quyền của client từ nguồn tin cậy, dùng RegisteredClient.id
    // hoặc client identity đã xác thực; không gắn role của một user.
}
```

Không biến client_id thành sub của người dùng. Không cấp ROLE_ADMIN cho một service account chỉ vì service đó có scope orders.read.

### 5.5. Không gọi hệ thống chậm tùy tiện trong customizer

Customizer chạy trong đường phát hành token. Nếu mỗi lần tạo token lại gọi một API mạng ngoài để lấy role/tenant, Token Endpoint có thể bị tăng latency hoặc phụ thuộc vào sự cố của hệ thống khác.

Khuyến nghị:

- Dùng nguồn dữ liệu nội bộ có độ tin cậy và SLA phù hợp.
- Cache có TTL ngắn và cơ chế invalidation rõ; không để role cũ tồn tại vô thời hạn.
- Xử lý lỗi entitlement theo nguyên tắc fail-closed đối với claim quyền nhạy cảm.
- Tránh truy vấn lặp nhiều lần trong cùng một token generation.
- Đo latency, lỗi và tỷ lệ token generation bị từ chối; không ghi claims nhạy cảm vào metrics.

## 6. Thêm business claims có kiểm soát

Roles không phải dữ liệu nghiệp vụ duy nhất. API đa tenant có thể cần tenant_id, organization_id hoặc một mã vùng. Nhưng các claim này cần được ràng buộc với **subject, client và authorization**.

### 6.1. Tenant claim phải được xác minh

Giả sử browser gửi:

```http
X-Tenant-Id: tenant-42
```

Header này chỉ là **input do client cung cấp**, không phải bằng chứng người dùng thuộc tenant đó. Authorization Server cần kiểm tra membership hoặc tenant context bằng dữ liệu đáng tin cậy. Một policy service có thể có giao diện:

```java
import java.util.Optional;

public interface TenantClaimService {
    Optional<String> activeTenantFor(String subject, String clientId);
}
```

Khi tạo token, chỉ thêm claim nếu service xác nhận subject được phép dùng tenant đó:

```java
tenantClaimService.activeTenantFor(subject, context.getRegisteredClient().getClientId())
        .ifPresent(tenant ->
                context.getClaims().claim(
                        "https://claims.example.com/tenant_id", tenant));
```

URI claim ở đây là tên custom claim có namespace để giảm va chạm với claim chuẩn hoặc claim do thư viện khác định nghĩa. Trong hệ thống thật, domain namespace cần thuộc quyền kiểm soát của tổ chức.

### 6.2. Không nhầm tenant claim với tenant authorization

Resource Server có thể đọc tenant_id để biết token được phát trong ngữ cảnh tenant nào, nhưng vẫn phải:

1. Xác minh chữ ký/issuer/audience/expiry của token.
2. Lấy tenant claim từ JWT đã được xác minh, không lấy từ request header thay thế.
3. Giới hạn mọi truy vấn dữ liệu theo tenant claim và kiểm tra quyền trên bản ghi.
4. Không cho client tự chọn tenant_id bằng query/body/header rồi bỏ qua membership.
5. Có cách xử lý khi user bị gỡ khỏi tenant hoặc tenant bị khóa.

Claim tenant **không phải** giấy phép truy cập mọi bản ghi thuộc tenant. Nó chỉ là một thuộc tính của token đã được Authorization Server xác minh tại thời điểm phát hành.

### 6.3. Claim nghiệp vụ thay đổi thường xuyên

Không nên đóng gói trạng thái có thể thay đổi từng phút vào access token dài hạn:

- Hạn mức tài chính hiện tại.
- Trạng thái đơn hàng, số dư, tồn kho.
- Feature entitlement thay đổi liên tục.
- Danh sách quyền theo từng resource có hàng chục nghìn phần tử.

Token là snapshot. Khi claim đã ký vào JWT, Resource Server offline không tự biết dữ liệu nguồn đã đổi. Với dữ liệu cần freshness cao, API nên truy vấn business service hoặc dùng authorization/introspection mechanism có TTL/cache được xác định.

## 7. Scope, role và permission trong Resource Server

### 7.1. Scope mặc định của Spring Security

Spring Security Resource Server ánh xạ scope trong JWT (thường claim scope hoặc scp, tùy converter/cấu hình) thành authorities có tiền tố SCOPE_. Ví dụ:

```text
scope: "orders.read orders.write"

Authorities:
SCOPE_orders.read
SCOPE_orders.write
```

Vì vậy có thể dùng:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public List<Order> readOrders() { ... }
```

### 7.2. Role claim không tự ánh xạ thành ROLE_

Nếu access token chứa:

```json
{
  "roles": ["ORDER_MANAGER"]
}
```

Spring Security **không tự động coi** chuỗi ORDER_MANAGER là ROLE_ORDER_MANAGER trong mọi cấu hình mặc định. Bạn phải cấu hình converter để chuyển claim roles thành GrantedAuthority.

Ví dụ converter kết hợp scope mặc định và roles:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ApiJwtAuthenticationConverters {
    private ApiJwtAuthenticationConverters() {}

    public static JwtAuthenticationConverter withRoles() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        Set<String> allowedRoles =
                Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            List<GrantedAuthority> authorities =
                    new ArrayList<>(scopes.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                roles.stream()
                        .filter(allowedRoles::contains)
                        .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                        .forEach(authorities::add);
            }
            return authorities;
        };

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
```

Đoạn converter giữ scope converter mặc định rồi bổ sung role. Regex chỉ là ví dụ giới hạn tên role; Resource Server thực tế cần allowlist các role được phép hiểu, tránh một claim tùy ý biến thành authority mạnh. Không nhận role từ token chưa qua xác minh chữ ký/issuer/audience.

### 7.3. Dùng scope và role cho mục đích khác nhau

Ví dụ cấu hình Resource Server:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/management/**")
                    .hasRole("ORDER_MANAGER")
                .anyRequest().authenticated())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                        jwtAuthenticationConverter)));

        return http.build();
    }
}
```

Trong ứng dụng thật, phải có JwtDecoder/issuer hoặc JWK Set configuration hợp lệ và bảo vệ các endpoint còn lại theo policy. hasRole("ORDER_MANAGER") kiểm tra authority ROLE_ORDER_MANAGER; hasAuthority("SCOPE_orders.write") kiểm tra scope. **Không thay toàn bộ scope bằng role**, và không dùng role cấp cao để bỏ qua mọi kiểm tra tenant/resource ownership.

## 8. JWT access token và opaque/reference token

Spring Authorization Server có thể phát access token theo format phù hợp:

| Đặc điểm | JWT/self-contained | Opaque/reference |
| --- | --- | --- |
| Dữ liệu claims | Nằm trong payload JWT, có thể đọc nếu không mã hóa | Không hiển thị claims trực tiếp từ token value |
| Kiểm tra tại Resource Server | Có thể xác minh chữ ký và claims offline | Thường dùng introspection để hỏi trạng thái/token metadata |
| Độ mới của roles/tenant | Snapshot tại lúc token được phát; JWT offline không tự cập nhật | Có thể nhận dữ liệu mới qua introspection, tùy cache và implementation |
| Chi phí request API | Có thể thấp hơn vì không cần gọi introspection mỗi request | Có chi phí mạng/cache cho introspection |
| Thu hồi tức thời | Khó hơn nếu chỉ xác minh JWT offline | Có thể phản ánh revoke nhanh hơn nếu không cache quá lâu |
| Rủi ro riêng | Claims lộ cho bên sở hữu token; stale permissions | Introspection endpoint và cache trở thành thành phần quan trọng |

Nếu chọn opaque token, Spring Authorization Server có thể tùy biến claims qua OAuth2TokenCustomizer<OAuth2TokenClaimsContext> cho access token opaque. **OAuth2TokenCustomizer<JwtEncodingContext> chỉ tùy biến JWT encoding context**, không nên mặc định cho rằng nó thay đổi claims của mọi token format.

Ví dụ cấu hình reference token trên TokenSettings:

```java
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
        .build();
```

Đây là một phần cấu hình cho RegisteredClient; việc chuyển format đòi hỏi Resource Server có introspection client/credentials và cấu hình tương ứng. Không chỉ đổi một enum rồi giả định mọi API vẫn đọc JWT claims như cũ.

## 9. Claims có thời hạn và có thể lỗi thời

Giả sử user được phát JWT lúc 09:00 với:

```json
{
  "roles": ["ORDER_MANAGER"],
  "https://claims.example.com/tenant_id": "tenant-42",
  "exp": 1794820800
}
```

Đến 09:02, quản trị viên gỡ role ORDER_MANAGER. Nếu Resource Server chỉ xác minh JWT offline, token đã ký vẫn có thể mang role cũ cho tới khi hết hạn.

Các chiến lược xử lý:

1. **Access token TTL ngắn:** giảm thời gian tồn tại của snapshot quyền.
2. **Opaque token + introspection:** API kiểm tra trạng thái token; phải thiết kế cache TTL phù hợp.
3. **Revocation/state check:** bổ sung denylist, authorization version hoặc session/account status check nếu SLA yêu cầu.
4. **Resource-level authorization:** luôn kiểm tra ownership/tenant/trạng thái dữ liệu ở API.
5. **Revoke refresh/authorization:** ngăn việc cấp token mới theo grant cũ khi quyền đã bị rút.

Không có giải pháp nào tự động đúng cho mọi hệ thống. Hãy xác định SLA: “role bị gỡ thì mọi API phải từ chối trong 30 giây” khác hoàn toàn “token mới sẽ không có role đó từ lần refresh tiếp theo”.

### 9.1. Refresh token và custom claims

Khi refresh, access token mới có thể được tạo lại từ ngữ cảnh authorization hiện tại. Nếu customizer truy vấn lại role/tenant từ nguồn dữ liệu, token mới có thể phản ánh **trạng thái mới nhất mà service quan sát được**. Nhưng:

- Không được mở rộng OAuth scopes ngoài authorizedScopes của grant gốc chỉ vì role mới tăng.
- Nếu user đã mất quyền, không nên tiếp tục phát role claim cũ chỉ vì authorization cũ còn tồn tại; cần policy thu hồi/thu hẹp riêng.
- Nếu role service lỗi, không tự cấp một bộ quyền mặc định rộng.
- Refresh token rotation không tự cập nhật/thu hồi các JWT access token cũ đã được phát hành.

Role claim và OAuth scope phải được tính theo **hai quyết định riêng**: scope tuân thủ grant; role/entitlement tuân thủ user/client/business policy.

## 10. Thiết kế schema claims ổn định

### 10.1. Đặt tên và kiểu dữ liệu

| Claim | Kiểu đề xuất | Quy tắc |
| --- | --- | --- |
| roles | Array string | Role names theo allowlist, không chứa ROLE_ nếu converter sẽ thêm prefix |
| permissions | Array string | Chỉ dùng khi cần quyền chi tiết; giới hạn số lượng và schema |
| tenant_id (hoặc claim namespaced) | String | Một tenant đã xác minh, không lấy trực tiếp từ request |
| organization_id | String | ID ổn định, có ràng buộc subject/client |
| authz_version | Integer/string version | Chỉ dùng nếu Resource Server có cơ chế kiểm tra version |
| scope | Chuỗi scope OAuth theo format được dùng | Không thay bằng role list |
| aud | Array string | Audience API nhận token; không phát một token chung cho mọi service nếu không cần |

### 10.2. Tránh claim names đụng nhau

Claim chuẩn như iss, sub, aud, exp, nbf, iat, jti có semantics xác định. Không dùng các tên này cho dữ liệu nghiệp vụ tùy ý. Với custom claims có thể dùng namespace URI do tổ chức kiểm soát:

```json
{
  "https://claims.example.com/tenant_id": "tenant-42",
  "https://claims.example.com/organization_id": "org-19"
}
```

Tên claim là một phần contract giữa Authorization Server và Resource Server. Khi đổi tên/kiểu dữ liệu, cần versioning/migration và test tương thích.

### 10.3. Giữ token nhỏ

JWT quá lớn làm tăng:

- HTTP header size và nguy cơ vượt giới hạn ở proxy/server.
- Băng thông, latency và chi phí truyền qua mọi request.
- Bề mặt lộ dữ liệu khi token bị copy vào log/debug tools.
- Độ phức tạp khi cập nhật schema và đồng bộ nhiều Resource Server.

Không đưa danh sách hàng nghìn permission, toàn bộ profile hoặc dữ liệu JSON lồng sâu vào access token. Nếu cần nhiều dữ liệu, dùng API nghiệp vụ hoặc entitlement service.

## 11. Kiểm thử claims từ Authorization Server tới API

### 11.1. Unit test cho policy chọn role

Policy cần bảo đảm chỉ role được phép xuất hiện:

```java
import java.util.Set;
import java.util.stream.Collectors;

public final class RoleClaimPolicy {
    private static final Set<String> ALLOWED =
            Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

    private RoleClaimPolicy() {}

    public static Set<String> exposedRoles(Set<String> trustedRoles) {
        return trustedRoles.stream()
                .filter(ALLOWED::contains)
                .collect(Collectors.toUnmodifiableSet());
    }
}
```

Test ví dụ với JUnit 5:

```java
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RoleClaimPolicyTest {
    @Test
    void onlyApprovedBusinessRolesAreExposed() {
        Set<String> result = RoleClaimPolicy.exposedRoles(Set.of(
                "ORDER_MANAGER",
                "SUPPORT_AGENT",
                "ROLE_SYSTEM_INTERNAL",
                "DBA"));

        assertThat(result)
                .containsExactlyInAnyOrder("ORDER_MANAGER", "SUPPORT_AGENT");
    }

    @Test
    void unknownRolesDoNotBecomeTokenClaims() {
        assertThat(RoleClaimPolicy.exposedRoles(Set.of("ROOT", "DEBUG")))
                .isEmpty();
    }
}
```

Đây là unit test cho allowlist, không thay thế integration test token generation. Khi tích hợp, cần xác minh customizer thực sự chỉ chạy với access token và Resource Server hiểu claim đúng.

### 11.2. Ma trận kiểm thử tích hợp

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| C01 | Authorization Code user có ORDER_MANAGER | Access token có role đã được allowlist |
| C02 | User có authority nội bộ ROLE_SYSTEM_INTERNAL | Không xuất hiện trong claim roles |
| C03 | User không có role phù hợp | Claim roles vắng mặt hoặc rỗng theo schema đã định |
| C04 | client_credentials | Không đưa role của end user vào token client |
| C05 | ID token được tạo trong OIDC flow | Không nhận các API role claims nếu policy chỉ dành cho access token |
| C06 | Refresh token sau khi role bị gỡ | Token mới phản ánh policy thu hồi/thu hẹp đã thiết kế |
| C07 | User đổi tenant hoặc mất membership | Không cấp tenant claim cũ theo dữ liệu request |
| C08 | Request tự gửi X-Tenant-Id khác | Không thể tự chọn tenant ngoài membership |
| C09 | Client chỉ được scope orders.read | Token không có orders.write dù user có role manager |
| C10 | Token audience là orders-api | API khác từ chối token sai audience |
| C11 | Resource Server nhận roles claim | Converter tạo đúng ROLE_* authorities |
| C12 | Resource Server nhận scope | Scope ánh xạ thành SCOPE_* và endpoint kiểm tra đúng |
| C13 | JWT thiếu claim tenant bắt buộc | API từ chối hoặc áp dụng policy fallback an toàn |
| C14 | Claim có PII không được phép | Không xuất hiện trong JWT |
| C15 | Token format chuyển sang opaque | Custom claims được kiểm tra qua introspection, không giả định đọc JWT |
| C16 | Role service timeout/lỗi | Không phát hành role claim rộng theo default; hành vi fail-closed đã định |
| C17 | JWT cũ sau khi role bị thu hồi | Hành vi thực tế nằm trong SLA đã cam kết |
| C18 | Token vượt kích thước giới hạn | Test phát hiện trước production, schema được rút gọn |
| C19 | Hai user cùng tên hiển thị nhưng khác subject | Claims được tra cứu theo subject ổn định, không nhầm người |
| C20 | Client khác nhau cùng user | Claims được giới hạn theo audience/client policy nếu nghiệp vụ yêu cầu |

### 11.3. Kiểm tra JWT mà không làm lộ token

Trong môi trường test, có thể decode payload để kiểm tra claim, nhưng:

- Chỉ dùng token fixture/test.
- Không đưa JWT production lên website decode công khai.
- Không ghi toàn bộ payload vào CI log nếu có PII/tenant/role nhạy cảm.
- Xác minh chữ ký, issuer, audience, thời hạn bằng Resource Server decoder; decode base64 **không phải** xác minh token.
- Kiểm tra cả response từ Token Endpoint và quyền thật tại API.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Copy mọi GrantedAuthority vào claim | Lộ authority nội bộ hoặc cấp quyền quá rộng | Allowlist, phân loại user/client authorities |
| Dùng role thay scope | Bỏ qua consent/grant hoặc client boundary | Giữ OAuth scopes độc lập với roles |
| Thêm business claim từ request header | User tự chọn tenant/organization | Resolve từ trusted membership/policy service |
| Thêm role vào mọi JWT | ID token/client khác nhận dữ liệu không cần thiết | Kiểm tra token type và audience |
| Dùng claim như dữ liệu realtime | Token cũ giữ trạng thái đã thay đổi | TTL, introspection/state check hoặc truy vấn API |
| Đưa PII/secret vào JWT | Dữ liệu bị đọc khi token bị lộ | Data minimization, opaque token hoặc API lookup |
| Dùng một audience chung cho mọi API | Token bị replay sang API khác | Audience restriction và validation |
| Tự ghi đè scope bằng roles | Làm sai semantics OAuth | Để provider quản lý scopes từ authorization |
| Query role service không giới hạn trong customizer | Token endpoint chậm/phụ thuộc dịch vụ ngoài | Local source/cache có invalidation, timeout/fail-closed |
| Resource Server không map role claim | hasRole luôn fail hoặc quyền không nhất quán | Cấu hình JwtAuthenticationConverter |
| Converter tin mọi role string | Claim tùy ý thành authority | Allowlist/schema validation tại AS và RS |
| Nghĩ JWT có chữ ký là payload bí mật | Lộ claims cho người giữ token | Không đặt dữ liệu bí mật vào JWS payload |
| Nghĩ revoke refresh token thu hồi JWT cũ ngay | API offline vẫn chấp nhận token cũ tới exp | Thiết kế access token revocation/freshness riêng |

## 13. Checklist production

**Thiết kế claim**

- [ ] Mỗi claim có consumer, mục đích, owner và schema được ghi nhận.
- [ ] OAuth scopes, roles, authorities và permissions được phân biệt rõ.
- [ ] Claims chỉ chứa dữ liệu tối thiểu cần cho Resource Server.
- [ ] Role/tenant/organization lấy từ nguồn tin cậy, đã xác minh subject và client context.
- [ ] Claim không chứa password, secret, refresh token, private key hoặc PII không cần thiết.
- [ ] Claim names không đụng registered JWT claims; có namespace/version khi cần.
- [ ] Token có audience phù hợp, TTL và scope tối thiểu.

**Spring Authorization Server**

- [ ] JWT customizer kiểm tra OAuth2TokenType.ACCESS_TOKEN trước khi thêm API claims.
- [ ] Grant type client_credentials được xử lý riêng, không lấy user roles.
- [ ] Không ghi đè scope được cấp bằng danh sách roles.
- [ ] Lỗi role/entitlement service không làm token có thêm quyền theo default.
- [ ] Opaque token dùng customizer/context phù hợp và được test riêng.
- [ ] ID token chỉ chứa claims cần cho OIDC client.

**Resource Server và vận hành**

- [ ] JWT decoder xác minh chữ ký, issuer, audience và thời hạn.
- [ ] Scope được map thành SCOPE_*; roles được map thành ROLE_* theo allowlist.
- [ ] API kiểm tra tenant/resource ownership ngoài việc đọc tenant claim.
- [ ] Có test token cũ sau khi quyền bị thu hồi, refresh và nhiều node.
- [ ] Claims/token size, logging, tracing và PII exposure được kiểm soát.
- [ ] Có chiến lược schema migration khi đổi claim names hoặc types.

## 14. Tài liệu tham khảo

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, token và authorization services.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, authentication providers và customization points.
- [Spring Authorization Server — How-to: Customize JWT Claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): ví dụ dùng OAuth2TokenCustomizer<JwtEncodingContext> để thêm claims/authorities.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và ánh xạ claims thành authorities.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): PreAuthorize, roles và authorities trong method authorization.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token, claims và validation.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims, public/private claim names và semantics JWT.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): least privilege, token leakage và bảo vệ access/refresh tokens.

**Kết luận:** Claims là một phần của **hợp đồng bảo mật giữa Authorization Server và Resource Server**. Hãy giữ scope theo quyền OAuth đã cấp, đưa roles/permissions vào claim riêng chỉ khi API cần, lấy business claims từ nguồn đã xác minh và giới hạn theo subject/client/audience. Trong Spring Authorization Server, tùy biến JWT qua OAuth2TokenCustomizer<JwtEncodingContext> với kiểm tra token type; ở Resource Server, xác minh token rồi ánh xạ claims thành authorities rõ ràng. Token là snapshot có thời hạn, vì vậy quyền thay đổi, thu hồi và tenant isolation luôn cần một chiến lược end-to-end.
