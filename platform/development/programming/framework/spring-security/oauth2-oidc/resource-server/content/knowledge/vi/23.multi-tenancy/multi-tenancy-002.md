# AuthenticationManagerResolver trong ứng dụng Servlet

Khi một **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** chỉ tin một Authorization Server, cấu hình JWT tương đối trực tiếp: đặt `issuer-uri`, xác minh chữ ký và các claims, sau đó phân quyền theo scope/role. Nhưng một ứng dụng phục vụ **nhiều tenant** có thể cần tiếp nhận access token từ **nhiều issuer**, mỗi issuer dùng JWKS, audience, naming convention và chính sách riêng. Một số hệ thống còn phải chọn cách xác thực theo **đường dẫn hoặc host tenant** đã được đăng ký.

Trong **Spring Security Servlet stack**, `AuthenticationManagerResolver<HttpServletRequest>` là điểm mở rộng cho phép **chọn `AuthenticationManager` phù hợp với từng HTTP request**, thay vì bắt toàn bộ API dùng một authentication manager duy nhất. Với Bearer Resource Server, Spring Security cung cấp `JwtIssuerAuthenticationManagerResolver` cho trường hợp **nhiều JWT issuer đáng tin cậy**.

Ví dụ:

~~~text
Orders API
  ├── Tenant A -> https://id.example.test/realms/acme
  ├── Tenant B -> https://id.partner.test/tenant/blue
  └── Tenant C -> https://login.example.test/realms/gamma

Mỗi Bearer token:
  -> xác định profile xác thực được phép
  -> dùng AuthenticationManager/JwtDecoder đúng tenant
  -> xác minh JWT + issuer + audience + token lifetime
  -> ánh xạ scope/role theo profile
  -> kiểm tra quyền đối với tài nguyên tenant thực tế
~~~

Điều quan trọng là **chọn nơi xác thực** không giống **tin nội dung token**: issuer, tenant ID hoặc host được đọc từ request **có thể chưa được xác minh** tại thời điểm resolver ra quyết định. Resolver chỉ được dùng thông tin ấy để **chọn trong tập cấu hình đã được tin cậy**, còn manager đã chọn bắt buộc phải xác minh token và áp dụng các ràng buộc cần thiết.

> **Nguyên tắc cốt lõi:** **`AuthenticationManagerResolver` chọn cơ chế xác thực; nó không tự xác thực token và không tự cấp quyền tenant.** Không tạo `JwtDecoder` bằng một `iss`/JWKS URL tùy ý do Client cung cấp. Chỉ chọn trong tập issuer/tenant đã được kiểm duyệt, luôn kiểm tra issuer, audience, thời hạn và chữ ký ở manager tương ứng, rồi kiểm tra **tenant/resource authorization** ở lớp nghiệp vụ.

## 1. Bài toán nhiều tenant: những gì phải tách biệt?

Giả sử một Orders API phục vụ nhiều doanh nghiệp:

| Tenant | Issuer của access token | Audience cho Orders API | Ví dụ scope | Định danh user |
| --- | --- | --- | --- | --- |
| Acme | `https://id.example.test/realms/acme` | `orders-api-acme` | `orders.read` | `(iss, sub)` |
| Blue | `https://id.partner.test/tenant/blue` | `orders-api-blue` | `orders.read` | `(iss, sub)` |
| Gamma | `https://login.example.test/realms/gamma` | `orders-api-gamma` | `orders.read` | `(iss, sub)` |

Một JWT hợp lệ do Acme phát hành **không mặc nhiên có quyền** gọi endpoint của Blue. Tương tự, hai issuer có thể cùng dùng chuỗi `sub = "user-842"` nhưng đại diện hai người khác nhau.

### 1.1. Có nhiều kiểu “tenant”

Từ “tenant” có thể chỉ những khái niệm không đồng nhất:

1. **Issuer tenant**: mỗi tổ chức dùng Authorization Server hoặc issuer riêng.
2. **Resource tenant**: dữ liệu/đơn hàng được phân vùng theo tổ chức.
3. **Client tenant**: Client registration hoặc ứng dụng gọi API thuộc một tổ chức.
4. **Route tenant**: URL/host chỉ định không gian làm việc của một tổ chức.
5. **Business membership**: user có thể thuộc nhiều tổ chức, vai trò khác nhau ở từng tổ chức.

Một hệ thống có thể dùng **một issuer chung cho mọi resource tenant**. Khi đó `JwtIssuerAuthenticationManagerResolver` có thể không giúp chia tách dữ liệu vì mọi token đều có cùng `iss`. Cần kiểm tra `tenant_id` hoặc membership **ở business authorization**, không cố tạo nhiều issuer giả để giải quyết tenancy.

### 1.2. Authentication khác authorization

Hai câu hỏi tách biệt:

- **Authentication:** access token có thực sự do một issuer tin cậy phát hành, được ký bằng khóa đúng, còn hiệu lực và dành cho API này không?
- **Authorization:** subject/client đã xác thực có quyền `orders.read` trên **Order 42 thuộc Blue** không?

Ngay cả khi `JwtIssuerAuthenticationManagerResolver` chọn đúng issuer Blue và manager xác minh JWT thành công, API vẫn phải kiểm tra scope, role, tenant membership, owner/assignment và trạng thái đơn.

## 2. `AuthenticationManagerResolver<HttpServletRequest>` là gì?

Interface trong Spring Security:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;

AuthenticationManagerResolver<HttpServletRequest> resolver;
~~~

Về khái niệm, nó có một thao tác:

~~~java
AuthenticationManager resolve(HttpServletRequest request);
~~~

**Input** là request Servlet hiện tại; **output** là một `AuthenticationManager` thích hợp để xử lý credential của request. Interface này **không trả `Authentication`**, không xác minh JWS và không làm một truy vấn quyền dữ liệu.

### 2.1. Vai trò trong Bearer Resource Server Servlet

~~~mermaid
flowchart TD
    A["HTTP request có Authorization: Bearer ..."]
    B["SecurityFilterChain / BearerTokenAuthenticationFilter"]
    C["BearerTokenResolver trích Bearer token"]
    D["AuthenticationManagerResolver<HttpServletRequest>"]
    E{"Chọn manager được phép?"}
    F["Authentication failure / từ chối"]
    G["AuthenticationManager tương ứng tenant"]
    H["JwtAuthenticationProvider + JwtDecoder"]
    I{"Chữ ký, iss, aud, exp/nbf hợp lệ?"}
    J["JwtAuthenticationToken + authorities"]
    K["authorizeHttpRequests / method security"]
    L["Policy dữ liệu: tenant, owner, assignment"]
    M["Cho phép xử lý tài nguyên"]

    A --> B --> C --> D --> E
    E -->|Không| F
    E -->|Có| G --> H --> I
    I -->|Không| F
    I -->|Có| J --> K --> L --> M
~~~

Phần resolver **chọn manager**. `AuthenticationManager` (ví dụ `ProviderManager` có `JwtAuthenticationProvider`) chịu trách nhiệm gọi decoder/provider để xác minh token. Sau đó mới có authenticated principal và authorities cho authorization.

Thứ tự xử lý nội bộ có thể khác chi tiết theo version/filter setup, nhưng ranh giới tin cậy cần giữ: **không tạo authenticated principal trước khi token được xác minh**.

### 2.2. So với cấu hình một JWT issuer

Single issuer:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
~~~

Multi-issuer:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver))
~~~

Ở cấu hình thứ hai, resolver quyết định manager. Đây không phải việc thêm một dòng bên cạnh cấu hình JWT đơn và hy vọng Spring Security tự biết manager nào dùng cho request. Cần làm rõ **một đường authentication chính** cho filter chain và kiểm thử nó thực sự chạy.

### 2.3. Không nhầm Servlet với WebFlux

| Servlet stack | Reactive WebFlux stack |
| --- | --- |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationManagerResolver<HttpServletRequest>` | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `JwtAuthenticationProvider` | `JwtReactiveAuthenticationManager` |

Không đưa `ReactiveAuthenticationManagerResolver` vào `HttpSecurity` của Servlet và không dùng blocking Servlet manager trong WebFlux chỉ vì cả hai đều gọi “authentication”.

## 3. Hai chiến lược phổ biến để chọn tenant

### Chiến lược A — Dựa vào issuer của JWT

Issuer trong JWT sau khi xác minh:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "sub": "user-842",
  "aud": ["orders-api-acme"],
  "scope": "orders.read"
}
~~~

Với nhiều issuer, resolver có thể **đọc `iss` chưa được xác minh chỉ để chọn một manager**. Manager được chọn lại phải xác minh chữ ký, `iss` và những claims bắt buộc. Spring Security có `JwtIssuerAuthenticationManagerResolver` cho use case này.

**Ưu điểm:** không nhất thiết cần URL riêng cho từng issuer; Client trình token và framework chọn manager phù hợp.

**Rủi ro cần kiểm soát:** `iss` ở giai đoạn chọn là dữ liệu caller có thể sửa. **Tuyệt đối không** tin một issuer URL bất kỳ, tự tải metadata/JWKS từ URL đó rồi chấp nhận chữ ký như một issuer của API. Phải có allowlist/trusted issuer registry.

### Chiến lược B — Dựa vào route/host tenant đã đăng ký

Ví dụ:

~~~text
GET /api/tenants/acme/orders/42
GET /api/tenants/blue/orders/17
~~~

Resolver dùng một mã tenant trong route để chọn cấu hình đã đăng ký. Manager Acme chỉ chấp nhận issuer/audience Acme; manager Blue chỉ chấp nhận issuer/audience Blue.

**Ưu điểm:** binding giữa route tenant và issuer rõ ràng, dễ kiểm thử token Acme không được dùng cho đường Blue.

**Rủi ro:** route/host có thể bị caller chọn; nó **chỉ là selector**, không phải bằng chứng caller thuộc tenant. Vẫn phải xác minh token theo manager tương ứng và kiểm tra membership/quyền tài nguyên.

### 3.1. Chọn chiến lược nào?

| Yêu cầu | Chọn issuer từ JWT | Chọn route/host tenant |
| --- | --- | --- |
| Một endpoint chung nhận token từ nhiều issuer | Thích hợp | Cần quy ước route/host |
| Mỗi tenant có URL riêng | Có thể | Thường dễ hiểu hơn |
| Cần token issuer A bị từ chối ở route B | Cần kiểm tra route-to-issuer sau authentication | Có thể được ràng buộc ngay ở manager |
| Một issuer phục vụ nhiều business tenants | Không tự phân biệt tenant dữ liệu | Có thể chọn tenant, vẫn cần membership |
| Quản lý danh sách issuer mới động | Cần trusted registry an toàn | Cần tenant configuration registry an toàn |
| Rủi ro SSRF/discovery | Cao nếu tin `iss` tùy ý | Vẫn có nếu route/header dùng trực tiếp làm JWKS URL |

Một ứng dụng có thể kết hợp cả hai theo quy tắc rõ ràng, chẳng hạn route tenant được chọn từ URL và sau đó JWT issuer phải khớp issuer được đăng ký của route ấy. Nhưng không nên triển khai hai nguồn tenant **không có điều kiện tương thích**.

## 4. `JwtIssuerAuthenticationManagerResolver`: cách chuẩn cho nhiều issuer đáng tin

Khi mỗi tenant có issuer độc lập và danh sách issuer được duyệt trước, Spring Security cung cấp:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id.example.test/realms/acme",
        "https://id.partner.test/tenant/blue",
        "https://login.example.test/realms/gamma");
~~~

Đoạn này sử dụng factory `fromTrustedIssuers(...)` của các phiên bản Spring Security 6 hỗ trợ API đó. Nếu dự án dùng phiên bản cũ hơn, đối chiếu API tương ứng theo phiên bản, nhưng vẫn phải giữ nguyên nguyên tắc **chỉ issuer đáng tin**.

### 4.1. Cấu hình một `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers
        .AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerSecurityConfiguration {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://id.example.test/realms/acme",
            "https://id.partner.test/tenant/blue");
    }

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver issuerResolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

Ví dụ chỉ có **hai trusted issuers**, còn tenant Gamma ở bảng đầu nhằm minh họa rằng cấu hình có thể mở rộng. Nếu JWT của Gamma đến nhưng không có trong allowlist, request **không được xác thực**.

**Tại sao `anyRequest().denyAll()`?** Nó chặn những URL thuộc `/api/**` chưa được cấp rule. Nếu ứng dụng có đường ngoài `/api/**`, phải có SecurityFilterChain khác hoặc fallback policy; riêng chain này không bảo vệ chúng.

Ví dụ giả định `/api/**` là REST API **chỉ dùng Bearer token trong Authorization header** và không xác thực bằng session/cookie. Vì vậy CSRF được tắt **theo threat model đó**, không phải vì multi-tenant hoặc JWT tự làm CSRF biến mất. Nếu API dùng cookie authentication, phải thiết kế CSRF khác.

### 4.2. Điều gì xảy ra khi token đến?

Token Acme:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["orders-api-acme"],
  "sub": "user-842",
  "scope": "orders.read"
}
~~~

Quy trình khái niệm:

1. Bearer filter nhận chuỗi JWT.
2. `JwtIssuerAuthenticationManagerResolver` đọc issuer để chọn **một manager trong tập trusted issuers**.
3. Manager được thiết lập cho Acme xác minh JWT bằng cấu hình issuer/keys của Acme.
4. Nếu token bị sửa chữ ký hoặc issuer không khớp với decoder, authentication thất bại.
5. Nếu token hợp lệ, authority như `SCOPE_orders.read` được tạo theo converter và rule HTTP được xét.
6. Service vẫn kiểm tra caller có quyền trên **Order 42 của tenant Acme** hay không.

Đọc `iss` ở bước 2 **không phải kết quả xác thực**; giá trị đó chỉ giúp chọn một cơ chế xác minh phù hợp. Không được gán role hoặc user nội bộ từ `iss`/`sub` trước bước 3–4.

### 4.3. Trusted issuer không thay audience validation

Giả sử issuer Acme còn phát access token cho `billing-api`:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Token có thể **được ký đúng bởi Acme**, nhưng **không dành cho Orders API**. Việc chọn trusted issuer không tự chứng minh `aud` đúng. Phải bổ sung per-issuer audience validation hoặc có cơ chế resource binding đáng tin khác.

**Đừng giả định chỉ `issuer-uri` đồng nghĩa có kiểm tra mọi audience tùy ý của ứng dụng.** Trong Spring Security, issuer/standard timestamp validation và audience policy là các điều kiện cần được cấu hình, xác nhận theo phiên bản và contract.

## 5. Trust boundary: claim `iss` chưa xác minh có thể được dùng đến mức nào?

Một JWT compact thường có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Trước khi xác minh chữ ký, payload là **dữ liệu attacker có thể thay đổi**. Vì vậy một token giả có thể tự khai:

~~~json
{
  "iss": "https://attacker.example.test/jwks",
  "sub": "admin",
  "scope": "orders.write"
}
~~~

Nếu ứng dụng viết:

~~~java
// SAI NGUY HIỂM — không dùng issuer URL tùy ý để tự tin cậy.
String issuer = parseWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
// ... dùng decoder mới như thể issuer vừa được chấp thuận ...
~~~

nó có thể bị **issuer trust injection**. Ngoài rủi ro xác thực token do bên không được phép phát, việc tự gọi metadata/JWKS URL do caller cung cấp còn có thể dẫn tới **SSRF**, kết nối tới mạng nội bộ, DNS rebinding, timeout hoặc cạn tài nguyên.

### 5.1. Chỉ cho phép dùng claim chưa xác minh như “lookup key”

Một thiết kế đúng có thể:

~~~text
Unverified iss = "https://id.example.test/realms/acme"
  -> lookup trong trusted registry do server quản lý
  -> tìm manager Acme đã được phê duyệt
  -> decoder xác minh chữ ký + expected issuer + expected audience
  -> authentication mới được tin
~~~

Nếu `iss` không có trong registry, resolver phải **không chấp nhận** token. Không tự ghi issuer mới vào registry chỉ từ request.

### 5.2. Những điều kiện nên có với trusted issuer registry

- Issuer URI được duyệt bằng một **quy trình cấu hình/onboarding tenant**, không qua request chưa xác thực.
- Issuer được đối chiếu **chính xác** theo contract, kể cả scheme/path/trailing slash.
- JWKS/metadata URL nằm trong tập endpoint đáng tin; hạn chế redirect, IP nội bộ và DNS rủi ro theo kiến trúc.
- HTTPS/TLS được kiểm tra.
- Có timeout, pool, cache và giới hạn số manager/decoder được tạo.
- Thay đổi issuer/keys có thể được cập nhật/revoked theo quy trình.
- Không log nguyên access token hoặc Client secret để debug.

Một trường `X-Issuer` do browser gửi **không tự là nguồn tin đáng tin**. Nếu dùng header chọn tenant, nó chỉ được làm selector vào registry, rồi vẫn cần đối chiếu token với tenant/issuer đã chọn.

## 6. Cơ chế discovery/JWKS khi dùng issuer resolver

Với cách dùng `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`, Spring Security có thể **khởi tạo decoder/manager theo nhu cầu của từng issuer** thay vì yêu cầu mọi issuer hoạt động ngay khi ứng dụng khởi động. Đây thường được gọi là **lazy initialization**.

### 6.1. Ưu điểm

- API có thể khởi động khi một issuer tenant ít dùng đang tạm không sẵn sàng, tùy cách cấu hình.
- Chỉ các tenant thực sự có request mới phải thực hiện discovery/key retrieval lúc đầu.
- Có thể chia manager/decoder theo issuer thay vì một cấu hình chung.

### 6.2. Đánh đổi

- **Request đầu tiên** của tenant có thể chịu độ trễ discovery/JWKS.
- Nếu AS/JWKS của tenant không sẵn sàng, request đó có thể thất bại dù API đã khởi động.
- Khi key rotation, decoder phải tìm khóa phù hợp từ JWKS/caches.
- Tenant hiếm dùng có thể tạo tình huống “chỉ tenant này bị 401/5xx” do trust/metadata/network.

**Không tự coi lazy discovery là fail-open.** Nếu không lấy được dữ liệu tin cậy để xác minh chữ ký, token không được chấp nhận. Một JWKS cache còn hợp lệ có thể hỗ trợ xác minh offline theo policy; không được bỏ signature validation khi AS down.

### 6.3. Khi cần tránh discovery runtime

Một hệ thống có thể cấu hình **JWKS URI cố định và expected issuer/audience** cho từng tenant, xây `NimbusJwtDecoder` theo các giá trị đã phê duyệt. Cách này hữu ích khi:

- Không muốn phụ thuộc discovery URL trong request đầu.
- AS không cung cấp discovery metadata chuẩn.
- Cần tùy chỉnh timeout, thuật toán, validators và authority mapping.
- Muốn kiểm soát cấu hình thông qua registry thay vì dựa vào endpoint được suy ra.

Nhưng dù dùng JWKS URI cố định, **vẫn phải kiểm tra issuer và audience**; một public key URL không đồng nghĩa toàn bộ token ký bằng khóa ấy dành cho API.

## 7. Tự xây resolver theo route tenant trong Servlet

Ví dụ này đi sâu hơn: mỗi đường `/api/tenants/{tenant}/...` dùng manager đã đăng ký cho tenant đó. Nó minh họa **`AuthenticationManagerResolver<HttpServletRequest>`** thay vì issuer resolver có sẵn.

### 7.1. Hợp đồng route–issuer–audience

| Route prefix | Tenant | Expected issuer | Expected audience |
| --- | --- | --- | --- |
| `/api/tenants/acme` | Acme | `https://id.example.test/realms/acme` | `orders-api-acme` |
| `/api/tenants/blue` | Blue | `https://id.partner.test/tenant/blue` | `orders-api-blue` |

**Tenant trong path chỉ chọn manager**. Token vẫn phải được xác minh đúng issuer/audience. Chưa có token hoặc token của tenant khác không được phép vào route vì tên tenant xuất hiện trong URL.

### 7.2. Tạo `JwtDecoder` với validator cho audience

~~~java
import java.util.List;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class TenantJwtDecoderFactory {

    public static NimbusJwtDecoder create(
            String issuer,
            String jwkSetUri,
            String expectedAudience) {

        // Các giá trị truyền vào phải đến từ trusted registry/config.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();
            if (audiences != null
                    && audiences.contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for this resource server",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }

    private TenantJwtDecoderFactory() {}
}
~~~

Hàm sử dụng `JwtValidators.createDefaultWithIssuer(issuer)` để áp dụng validators chuẩn theo issuer/thời gian của Spring Security, sau đó bổ sung audience theo expected resource. Nếu một hệ thống cần token type/profile, thuật toán chữ ký, `azp`, tenant claim hoặc clock skew riêng, phải khai báo thêm theo contract **không thay thế** các validators cơ bản.

**Nguồn cấu hình:** `issuer`, `jwkSetUri` và `expectedAudience` ở factory phải đến từ cấu hình server/trusted tenant registry. Không lấy `jwkSetUri` từ query string hoặc issuer chưa được phê duyệt.

### 7.3. Tạo `AuthenticationManager` cho mỗi tenant

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationProvider;

public final class TenantAuthenticationManagerFactory {

    public static AuthenticationManager create(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder =
            TenantJwtDecoderFactory.create(
                issuer, jwkSetUri, audience);

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return new ProviderManager(provider);
    }

    private TenantAuthenticationManagerFactory() {}
}
~~~

`JwtAuthenticationProvider` nhận `BearerTokenAuthenticationToken` từ Bearer authentication flow và dùng decoder để xác minh token rồi tạo `JwtAuthenticationToken`. `ProviderManager` dùng provider đã cấu hình.

**Đây là một cơ chế cấu hình**, không nhất thiết phải tự viết khi `JwtIssuerAuthenticationManagerResolver` đáp ứng đúng bài toán. Custom factory có ích khi mỗi tenant có audience/JWKS/rules khác nhau.

### 7.4. Resolver chọn manager từ đường Servlet

~~~java
import jakarta.servlet.http.HttpServletRequest;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;

@Configuration
public class TenantRouteResolverConfiguration {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
    tenantRouteAuthenticationManagerResolver() {

        Map<String, AuthenticationManager> managers =
                new LinkedHashMap<>();

        managers.put(
            "/api/tenants/acme",
            TenantAuthenticationManagerFactory.create(
                "https://id.example.test/realms/acme",
                "https://id.example.test/realms/acme/protocol/openid-connect/certs",
                "orders-api-acme"));

        managers.put(
            "/api/tenants/blue",
            TenantAuthenticationManagerFactory.create(
                "https://id.partner.test/tenant/blue",
                "https://id.partner.test/tenant/blue/jwks",
                "orders-api-blue"));

        // Không có tenant hợp lệ -> tuyệt đối không cấp Authentication.
        AuthenticationManager rejectUnknownTenant =
            authentication -> {
                throw new BadCredentialsException(
                    "Unknown tenant route");
            };

        Map<String, AuthenticationManager> trustedManagers =
            Map.copyOf(managers);

        return request -> {
            // getServletPath thường không chứa context path.
            String path = request.getServletPath();
            for (Map.Entry<String, AuthenticationManager> entry
                    : trustedManagers.entrySet()) {
                String prefix = entry.getKey();
                if (path.equals(prefix)
                        || path.startsWith(prefix + "/")) {
                    return entry.getValue();
                }
            }
            return rejectUnknownTenant;
        };
    }
}
~~~

Các URL/JWKS ở đây chỉ **minh họa**, không phải thông tin kết nối thật. Đối với production, nên đưa trusted manager registrations vào configuration/registry được quản trị, không viết secrets trong source.

**Điểm quan trọng về đường dẫn:**

- `getServletPath()` thường không chứa context path, nhưng cách xử lý có thể chịu ảnh hưởng Servlet mappings/gateway rewrites.
- Kiểm tra `path.equals(prefix) || path.startsWith(prefix + "/")` để tránh prefix collision: `/api/tenants/acme-evil` không được coi là Acme.
- URL encoding, ký tự phân tách, trailing slash, matrix variables, proxy normalization và Servlet firewall cần được kiểm thử theo deployment.
- Với route phức tạp, nên dùng **Spring Security RequestMatcher được cấu hình tường minh** thay vì parser tự viết cho tên tenant tùy ý.
- Mã tenant trong URL vẫn là **untrusted selector**; manager được chọn phải xác minh JWT đúng nguồn và audience.

**Không trả `null` cho tenant không biết rồi hy vọng framework mặc định từ chối bằng một lỗi đẹp.** Ở ví dụ này có một manager fail-closed ném `BadCredentialsException`. Có thể thiết kế một exception handler phù hợp để trả 401/404 theo contract, nhưng tuyệt đối không trả manager “cho phép tất cả”.

### 7.5. Nối resolver vào `SecurityFilterChain`

~~~java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers
        .AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class TenantRouteResourceServerSecurity {

    @Bean
    SecurityFilterChain tenantApi(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .securityMatcher("/api/tenants/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

Đây là **một biến thể thay thế** cách dùng `JwtIssuerAuthenticationManagerResolver` ở mục 4, không phải hai cấu hình cùng được đăng ký trong một ứng dụng để cùng xử lý một URL. Nếu cần chạy chung nhiều chain, phải đặt `securityMatcher` và `@Order` tường minh, tránh bean converter/resolver cạnh tranh.

### 7.6. Mỗi tenant phải có policy JWT độc lập

Nếu route `/api/tenants/blue/orders` nhận JWT của Acme, manager Blue:

1. Xác minh chữ ký bằng keys tin cậy của Blue.
2. Kiểm tra `iss` của Blue.
3. Kiểm tra `aud` là `orders-api-blue`.
4. Kiểm tra `exp`/`nbf`.
5. Chỉ sau đó tạo authentication và xét scope.

JWT Acme không được chấp nhận ở Blue dù chuỗi `scope` giống nhau. **Chữ ký được xác minh bằng keys Blue thôi có thể vẫn chưa đủ**, ví dụ nếu hai tenant dùng chung signing infrastructure; `iss` và `aud` vẫn phải được đối chiếu.

## 8. Multi-tenant validation: issuer, audience, token type và claims

### 8.1. Issuer phải khớp chính xác

Nếu expected issuer:

~~~text
https://id.example.test/realms/acme
~~~

thì:

~~~text
https://id.example.test/realms/acme/
https://id.example.test/realms/blue
http://id.example.test/realms/acme
~~~

không tự được coi là cùng issuer. Chỉ áp dụng normalize khi hợp đồng IdP và API cho phép; thông thường so theo issuer URI chính thức mà AS công bố.

### 8.2. Audience là ranh giới Resource Server

Token có thể hợp lệ tại issuer nhưng được cấp cho Billing API:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Orders API phải từ chối token này nếu hợp đồng yêu cầu `aud = orders-api-acme`. **Scope trùng không thay audience**.

### 8.3. Token type/profile

OIDC **ID token** thường dành cho OIDC Client, không phải Bearer access token của API. Nếu cùng issuer có nhiều loại JWT, Resource Server có thể cần token type/`typ`/claims profile validation theo chuẩn/contract. Đừng nhận ID token thay access token chỉ vì chữ ký hợp lệ hoặc chứa `sub` và `email`.

### 8.4. `azp`/`client_id` và client allowlist

Một số AS trả `client_id`, `azp` hoặc client-specific claims theo token profile. Các claim này có thể giúp hạn chế Client nào được gọi một API tenant, nhưng **không dùng chúng thay `aud`** hoặc resource authorization nếu hợp đồng không quy định tương đương. OAuth2 Client ID được cấp token không tự cho Client quyền đọc đơn của mọi tenant.

### 8.5. Subject không duy nhất toàn hệ thống

Ví dụ:

~~~text
(iss=acme, sub=user-842) -> local user 42
(iss=blue, sub=user-842) -> local user 91
~~~

Nếu API dùng `sub` đơn độc làm khóa toàn cục, có thể liên kết nhầm tài khoản hoặc làm lộ dữ liệu. Cặp `(iss, sub)` là một khóa liên kết phổ biến khi issuer/subject có hợp đồng ổn định. Với Client Credentials, `sub` có thể đại diện service Client và không được coi là user sở hữu đơn.

### 8.6. Claims tenant không được tin khi chưa xác minh

Một JWT có thể chứa:

~~~json
{
  "tenant_id": "acme",
  "roles": ["TENANT_ADMIN"]
}
~~~

Chỉ khi JWT được decoder chấp nhận **và** claims thuộc đúng issuer/profile, mới được dùng chúng làm dữ kiện authorization. Ngay cả như vậy, `tenant_id` trong token không nhất thiết bảo đảm user còn là thành viên tenant tại thời điểm request; chính sách quyền động có thể cần tra cứu membership hiện tại.

## 9. Tenant chọn từ hostname: rủi ro ở đâu?

Một kiến trúc khác dùng:

~~~text
https://acme.api.example.test/orders/42
https://blue.api.example.test/orders/42
~~~

Resolver có thể chọn manager dựa trên host đã được map vào tenant registry, nhưng **Host header của HTTP có thể bị Client giả mạo** nếu gateway/server không kiểm soát. `X-Forwarded-Host` càng không nên tin tùy ý nếu không có reverse proxy được tin cậy và cấu hình forward headers đúng.

### 9.1. Không xây JWKS URL bằng Host header chưa kiểm chứng

Sai:

~~~java
// SAI: host là dữ liệu request, không thể làm trust anchor.
String host = request.getHeader("Host");
String jwksUrl = "https://" + host + "/.well-known/jwks.json";
JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUrl).build();
~~~

Attacker có thể kiểm soát host/URL trong những deployment và gây SSRF hoặc làm API tin khóa của nguồn không được phép.

Thay vào đó:

~~~text
Host sau trusted proxy validation
  -> map host đúng chuỗi vào trusted tenant registration
  -> lấy issuer/JWKS/audience cấu hình trước
  -> chọn manager
  -> decoder xác minh JWT
  -> kiểm tra membership/resource tenant
~~~

### 9.2. Header chọn tenant chỉ là selector

`X-Tenant-Id: acme` có thể hữu ích cho một gateway hoặc ứng dụng quản lý workspace, nhưng header do caller gửi **không được dùng để tự cấp quyền**. Nếu API chấp nhận:

~~~http
X-Tenant-Id: blue
Authorization: Bearer <valid-token-for-acme>
~~~

phải từ chối hoặc chỉ xử lý khi **token và membership** cho phép Blue theo contract. Không đổi Authentication sang Blue chỉ vì header nói vậy.

## 10. Nhiều issuer nhưng chung một signing key?

Một số tổ chức vận hành nhiều logical tenants trên một Authorization Server hoặc dùng chung JWKS signing infrastructure. Khi đó **chữ ký hợp lệ không đủ phân biệt tenant**.

Giả sử cùng một public key xác minh được cả JWT Acme và Blue:

~~~text
JWT Acme: iss=.../acme, aud=orders-api-acme
JWT Blue: iss=.../blue, aud=orders-api-blue
~~~

Nếu decoder chỉ xác minh chữ ký mà **không kiểm tra expected issuer/audience**, token Acme có thể được chấp nhận ở Blue. Đó là lý do `JwtValidators.createDefaultWithIssuer(...)` và audience validator trong ví dụ custom manager là các điều kiện bắt buộc theo hợp đồng.

Nếu một issuer chung phát token cho nhiều resource tenants:

~~~text
iss = https://identity.example.test
aud = orders-api
tenant_id = acme hoặc blue
~~~

thì một manager duy nhất có thể đã đủ ở authentication. Phân tách tenant dữ liệu phải dựa vào `tenant_id` được xác minh và quyền membership/owner. **Không cố tạo multi-issuer resolver khi bài toán thực sự là multi-tenant authorization**.

## 11. Phân quyền theo tenant: scope không đủ để cấp quyền đối tượng

JWT có `scope = "orders.read"`. Resource Server tạo:

~~~text
SCOPE_orders.read
~~~

HTTP rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Rule này chỉ xác nhận caller được thực hiện **loại thao tác đọc**. Nó không chứng minh rằng user:

- Thuộc tenant ở URL.
- Có quyền xem đơn 42.
- Là chủ đơn hoặc nhân viên hỗ trợ được phân công.
- Có quyền đọc dữ liệu nhạy cảm của tenant khác.

### 11.1. Bảo vệ ngay tại truy vấn dữ liệu

Một service có thể sử dụng tenant đã được **xác minh/buộc bởi policy** và subject/user mapping:

~~~java
@Service
public class OrderQueryService {

    private final OrdersRepository orders;
    private final TenantAccessPolicy policy;

    public OrderQueryService(
            OrdersRepository orders,
            TenantAccessPolicy policy) {
        this.orders = orders;
        this.policy = policy;
    }

    public OrderDto getOrder(
            Authentication authentication,
            String tenant,
            String orderId) {

        policy.assertCanRead(authentication, tenant, orderId);
        return orders.findVisibleByTenantAndId(
                tenant, orderId);
    }
}
~~~

`OrdersRepository`, `TenantAccessPolicy` và `OrderDto` là các lớp nghiệp vụ minh họa, không có sẵn trong Spring. Trong production, cần thiết kế data access/giao dịch tránh **time-of-check/time-of-use** khi quyền/đơn thay đổi, và bảo đảm query database có điều kiện tenant/owner phù hợp.

### 11.2. Tenant ở URL là dữ liệu caller chọn

Ví dụ user được quyền ở Acme:

~~~http
GET /api/tenants/blue/orders/42
Authorization: Bearer <valid-acme-token>
~~~

Kể cả nếu route manager từ chối token ngay ở authentication, API vẫn cần business policy vì một token của issuer chung hoặc service token có thể hợp lệ cho **nhiều tenant**. Không bỏ `TenantAccessPolicy` chỉ vì route resolver đang hoạt động.

### 11.3. Role theo tenant phải có ngữ cảnh

Nếu user có `ROLE_ADMIN` tại Acme nhưng chỉ là reader tại Blue, một authority toàn cục `ROLE_ADMIN` có thể bị dùng sai. Nên:

- Chỉ dùng global authorities khi thực sự mang quyền toàn cục.
- Kiểm tra membership/role theo tenant được yêu cầu.
- Nếu token có tenant-specific claims, validate schema và namespace cụ thể.
- Ánh xạ roles theo **issuer + tenant** với allowlist, không tin mọi chuỗi role tự phát từ IdP.

## 12. Nhiều tenant và `JwtAuthenticationConverter`

Mỗi issuer có thể trả scope khác nhau:

~~~json
{"scope": "orders.read orders.write"}
~~~

hoặc:

~~~json
{"scp": ["orders.read", "orders.write"]}
~~~

Spring Security mặc định hỗ trợ những claim scope phổ biến, nhưng một số AS dùng cấu trúc role riêng như `realm_access.roles` hay `permissions`. Khi mỗi tenant có schema khác nhau, có thể cấu hình **`JwtAuthenticationConverter` riêng trong `JwtAuthenticationProvider` của tenant**.

### 12.1. Converter chỉ đọc claims đã xác minh

Ví dụ cấu hình scope chuẩn:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter scopeAuthorities =
        new JwtGrantedAuthoritiesConverter();
scopeAuthorities.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopeAuthorities);
converter.setPrincipalClaimName("sub");

provider.setJwtAuthenticationConverter(converter);
~~~

Đoạn code thuộc bước **cấu hình `JwtAuthenticationProvider provider`** trong factory. Converter chỉ nên map các claim thuộc đúng token profile của tenant sau khi decoder đã chấp nhận JWT. Không cho một claim `roles=["ADMIN"]` từ issuer không đáng tin trở thành quyền của Orders API.

### 12.2. Không gộp scopes giống tên giữa các issuer mà quên contract

`SCOPE_orders.read` của Acme và của Blue có thể được hiểu giống nhau **ở HTTP action level**, nhưng quyền dữ liệu vẫn cần ràng buộc tenant. Nếu issuer partner định nghĩa `orders.read` theo nghĩa khác, API phải có một mapping contract/adapter rõ, không tự coi hai chuỗi trùng chữ là cùng quyền.

### 12.3. `Authentication.getName()` với nhiều issuer

Mặc định JWT Resource Server thường dùng `sub` làm name. Nếu hai issuers cùng có `sub="user-842"`, logging hoặc service không nên dùng mỗi `authentication.getName()` làm global user ID.

Có thể:

- Sử dụng `(iss, sub)` khi ánh xạ sang local account.
- Dùng converter riêng và đặt principal name thành internal user ID nếu hệ thống đã có trusted link.
- Lưu issuer trong audit context.
- Không dùng email/username làm khóa định danh toàn cục trừ khi có contract mạnh.

## 13. Một issuer mới được đăng ký động: làm sao tránh mở trust boundary?

Trong SaaS, tenant có thể được onboard sau khi API đã khởi chạy. Có thể cần cập nhật trusted issuer list hoặc manager registry.

**Sai lầm:** nhận bất kỳ `iss` mới nào từ request rồi coi đó là tenant hợp lệ.

**Luồng đúng hơn:**

1. Admin/onboarding service được xác thực yêu cầu đăng ký tenant.
2. Hệ thống kiểm tra quyền của admin và ràng buộc tổ chức.
3. Xác minh issuer metadata/JWKS qua policy URL, TLS, allowed hosts/ports và quy trình chấp thuận.
4. Định nghĩa expected audience, allowed algorithms, authority mapping, token profile và tenant ID.
5. Lưu cấu hình vào **trusted tenant registry**.
6. Cập nhật manager/decoder cache theo cơ chế an toàn với concurrent requests.
7. Chạy test tích hợp và quan sát lỗi.
8. Chỉ sau khi tenant được cho phép mới nhận token issuer đó.

### 13.1. Dùng predicate trusted issuers

Trong các phiên bản Spring Security cung cấp overload predicate, có thể có mô hình:

~~~java
// Minh họa: registry chỉ được cập nhật bởi luồng quản trị tin cậy.
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        issuer -> trustedTenantRegistry.isAllowedIssuer(issuer));
~~~

`trustedTenantRegistry` là thành phần **ứng dụng xây dựng**, không phải class Spring có sẵn. Nó phải truy vấn/cached từ một nguồn cấu hình đáng tin, không tự thêm issuer khi lookup miss. Nếu kiểm tra registry gây I/O blocking, cần thiết kế cache/bound thời gian phù hợp vì đây là Servlet request authentication path.

### 13.2. Cache manager và decoder có kiểm soát

Khởi tạo decoder/JWKS client cho **mỗi request** vừa chậm vừa có thể mở đường resource exhaustion. Thay vì:

~~~java
// Không nên khởi tạo decoder mới cho mỗi request.
return request -> createManager(
    issuerFromRequest(request));
~~~

hãy:

- Dùng issuer resolver có caching theo khả năng framework.
- Hoặc giữ `Map<TrustedTenantKey, AuthenticationManager>`/registry trong bộ nhớ theo config version.
- Khởi tạo manager theo tenant có giới hạn, chặn concurrent duplicate initialization.
- Bảo đảm có cơ chế vô hiệu/đổi manager khi tenant bị thu hồi hoặc metadata thay đổi.
- Giới hạn tenant count/JWKS fetch và timeout để chống DoS.

**Một manager đã cache không đồng nghĩa trust là vĩnh viễn.** Khi tenant bị hủy quyền hoặc issuer không còn đáng tin, hệ thống phải có kế hoạch loại issuer/manager khỏi registry và chặn request tiếp theo phù hợp chính sách.

### 13.3. Atomic update khi nhiều request đồng thời

Nếu registry thay đổi trong lúc request đang chạy, nên dùng dữ liệu immutable/snapshot hoặc cơ chế cập nhật thread-safe:

~~~text
config version 17 -> trusted issuers {Acme, Blue}
config version 18 -> trusted issuers {Acme, Gamma}
~~~

Không thay đổi một `HashMap` mutable chia sẻ giữa threads mà không đồng bộ. Các request đã bắt đầu trong giai đoạn chuyển đổi cần behavior có chủ đích, đặc biệt khi Blue bị revoked.

## 14. So với nhiều `SecurityFilterChain`

Có hai cách thiết kế hay bị nhầm:

### 14.1. Một chain, nhiều manager

~~~text
SecurityFilterChain /api/**
  -> AuthenticationManagerResolver
     -> manager Acme
     -> manager Blue
     -> manager Gamma
~~~

Phù hợp khi **HTTP rules tương đối chung**, nhưng authentication khác theo issuer/tenant.

### 14.2. Nhiều chain, mỗi chain một authentication profile

~~~text
@Order(1) /api/tenants/acme/** -> JwtDecoder Acme
@Order(2) /api/tenants/blue/** -> JwtDecoder Blue
@Order(3) /api/**              -> denyAll/fallback
~~~

Phù hợp khi **HTTP rules/CSRF/authentication transport** khác nhau đáng kể, số tenant ít và route phân tách rõ. Với hàng trăm tenants đăng ký động, tạo hàng trăm filter chains có thể phức tạp; resolver thường dễ quản lý hơn.

**Không tự động hiểu một chain áp dụng cho mọi URL.** `securityMatcher` và thứ tự `@Order` có thể khiến một request không đi vào chain dự kiến; các đường chưa có chain phải được xử lý theo fallback/default deny.

### 14.3. Ví dụ fallback chain

Nếu route tenant chain chỉ match `/api/tenants/**`, một chain khác có thể chặn phần còn lại:

~~~java
@Bean
@Order(99)
SecurityFilterChain denyUnknownPaths(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Đây là **một tùy chọn thiết kế** khi ứng dụng chỉ phục vụ API được liệt kê. Nếu có Actuator/public website/oauth2 login, cần xây rule riêng theo yêu cầu sản phẩm. Không dùng fallback này một cách máy móc rồi khóa nhầm health check cần thiết.

## 15. JWT Resource Server khác OAuth2/OIDC Client

Một ứng dụng có thể vừa là OAuth2 Client để đưa user đăng nhập qua OIDC, vừa là Resource Server để nhận access token. Nhưng hai vai trò khác nhau:

| Vai trò | API/khái niệm thường dùng | Nhiệm vụ |
| --- | --- | --- |
| OAuth2/OIDC Client | `oauth2Login()`, `ClientRegistration`, `OidcUser` | Đưa browser qua login, quản lý authorized client/session |
| Resource Server | `oauth2ResourceServer()`, `JwtDecoder`, `AuthenticationManagerResolver` | Xác minh Bearer access token để bảo vệ API |
| Authorization Server | Token endpoint, JWKS, issuer, signing keys | Phát hành token và công bố metadata |

`AuthenticationManagerResolver<HttpServletRequest>` của bài này phục vụ **lựa chọn authentication manager cho Bearer Resource Server Servlet**. Nó không tự biến API thành OIDC Client, không sinh authorization code và không thay quản lý session/login cookie.

**ID token** của OIDC Client thường có audience là Client ID và phục vụ xác thực login ở Client. Nó không phải credential mặc định được chấp nhận ở Orders API. Với mỗi tenant, hãy xác định đúng **access token profile**.

## 16. Opaque token và kết hợp nhiều kiểu token

Multi-tenancy không nhất thiết chỉ dùng signed JWT. Một số tenants dùng **opaque access token** và introspection.

Ví dụ:

~~~text
Tenant Acme -> signed JWT -> JwtAuthenticationProvider
Tenant Blue -> opaque access token -> OpaqueTokenAuthenticationProvider
~~~

Về kiến trúc, `AuthenticationManagerResolver<HttpServletRequest>` có thể chọn manager khác nhau, nhưng cần hợp đồng rõ:

1. Route/issuer/tenant được chọn từ **trusted registry**.
2. Manager JWT dùng `JwtDecoder` để xác minh JWS và claims.
3. Manager opaque dùng `OpaqueTokenIntrospector` để kiểm tra `active`, audience/resource binding và metadata.
4. Mỗi provider tạo principal/authorities phù hợp.
5. Authorization và resource policy thống nhất phía API.

Không đoán loại token đáng tin chỉ bằng việc chuỗi có hai dấu chấm. Một token opaque có thể có hình dạng riêng, còn JWT cũng có thể được kiểm tra qua introspection theo hợp đồng.

### 16.1. Đừng “thử JWT, thất bại thì chấp nhận opaque”

Một fallback thiếu kiểm soát:

~~~text
JWT signature invalid
  -> thử introspection bất kỳ
  -> nếu một AS nói active thì chấp nhận
~~~

có thể phá ranh giới issuer/resource. Nếu hỗ trợ hai token profiles, phải có quy tắc selection, trusted AS, audience và mục đích token rõ ràng. Một token JWT sai chữ ký **không tự được chuyển thành credential của tenant khác**.

### 16.2. Introspection credentials theo tenant

Nếu Blue dùng introspection, Resource Server có thể cần `client-id`/`client-secret` riêng để gọi endpoint. Đây là credential của **Orders API đối với AS Blue**, không phải OAuth2 Client ID trong token. Secrets phải được giữ trong secret manager và quay vòng theo từng tenant.

## 17. Error handling: 401, 403 và lỗi phụ thuộc

| Tình huống | Lớp phát hiện | Kết quả mong muốn |
| --- | --- | --- |
| Request protected không Bearer token | Bearer filter/entry point | Thường **401 Unauthorized** |
| JWT `iss` không thuộc trusted allowlist | Issuer resolver | Không xác thực |
| JWT issuer thuộc allowlist nhưng chữ ký sai | JWT decoder/provider | Không xác thực, thường 401 |
| JWT đúng issuer/chữ ký nhưng audience sai | JWT validator | Không xác thực, thường 401 |
| JWT hết hạn | JWT validator | Không xác thực, thường 401 |
| Route Acme nhưng token Blue | Route manager/validator | Không xác thực |
| Token hợp lệ nhưng thiếu `orders.read` | HTTP/method authorization | Thường **403 Forbidden** |
| Token hợp lệ có scope nhưng không thuộc tenant/order | Business policy | 403/404 theo contract |
| Unknown tenant route | Resolver/fallback policy | Fail closed, status theo exception handler |
| Discovery/JWKS timeout | Authentication dependency | Không tạo authentication hợp lệ |
| Introspection AS down | Opaque authentication dependency | Không tạo authentication hợp lệ |

**Không gán một mã HTTP duy nhất cho mọi lỗi discovery/network.** Framework và exception handling có thể chuyển dependency exception thành 401 hoặc 5xx tùy trường hợp. Điều bắt buộc về bảo mật là **không thực hiện thao tác được bảo vệ khi authentication không hoàn tất**.

### 17.1. Bearer entry point và access denied handler

Spring Security Resource Server có:

~~~java
BearerTokenAuthenticationEntryPoint entryPoint =
    new BearerTokenAuthenticationEntryPoint();

BearerTokenAccessDeniedHandler deniedHandler =
    new BearerTokenAccessDeniedHandler();
~~~

`BearerTokenAuthenticationEntryPoint` thường xử lý authentication failure với 401/Bearer challenge. `BearerTokenAccessDeniedHandler` thường xử lý quyền thiếu với 403, có thể kèm `insufficient_scope` theo RFC 6750. Chúng không thay validators và không sửa tenant binding.

### 17.2. Không tiết lộ cấu trúc tenant nội bộ qua lỗi

Ví dụ error response cho Client:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The supplied access token could not be accepted."
}
~~~

Không trả raw JWT, signing keys, secret introspection, đường mạng nội bộ hay toàn bộ danh sách issuer cho một caller chưa xác thực. Nếu cần debug, dùng log có kiểm soát và correlation ID.

### 17.3. `WWW-Authenticate`

Theo Bearer protocol (RFC 6750), response có thể mang:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

hoặc khi token đã xác thực nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Khi tùy chỉnh JSON error handler, không làm mất Bearer challenge nếu contract/protocol cần. Lỗi thiếu tenant membership đôi khi thuộc quyền nghiệp vụ thay vì thiếu OAuth scope; tránh suy diễn mọi 403 đều chỉ do thiếu `scope`.

## 18. Kiểm thử resolver: từ unit tới JWT có chữ ký thật

**Một test `MockMvc` dùng `SecurityMockMvcRequestPostProcessors.jwt()` có thể bỏ qua cả resolver và JWT decoder**, vì nó đặt authentication giả lập cho request. Test ấy hữu ích để kiểm tra HTTP authorization sau khi đã có Authentication, **không chứng minh lựa chọn manager theo tenant hoặc xác minh chữ ký**.

Cần ít nhất ba mức kiểm thử:

1. **Unit test resolver**: request route/host/issuer chỉ chọn đúng manager từ trusted registry.
2. **Integration test HTTP Bearer**: token được ký thật qua decoder/manager, issuer/audience/expiry đúng/sai.
3. **Business authorization test**: scope/owner/tenant và side effects.

### 18.1. Unit test route resolver

Ví dụ JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;

class RouteResolverTest {

    @Test
    void selectsTheSameRegisteredManagerForAcmeRoutes() {
        AuthenticationManagerResolver<HttpServletRequest> resolver =
            new TenantRouteResolverConfiguration()
                .tenantRouteAuthenticationManagerResolver();

        var first = new MockHttpServletRequest(
                "GET", "/api/tenants/acme/orders/42");
        first.setServletPath("/api/tenants/acme/orders/42");

        var second = new MockHttpServletRequest(
                "GET", "/api/tenants/acme/orders/99");
        second.setServletPath("/api/tenants/acme/orders/99");

        AuthenticationManager firstManager =
                resolver.resolve(first);
        AuthenticationManager secondManager =
                resolver.resolve(second);

        assertNotNull(firstManager);
        assertSame(firstManager, secondManager);
    }
}
~~~

Test này chỉ xác nhận **hai route Acme chọn cùng manager** và manager tồn tại; nó **chưa xác minh** manager ấy thực sự là Acme theo expected issuer/audience, token Blue bị từ chối hoặc unknown route bị chặn. Phải bổ sung các case negative và integration test.

Đối với production test, factory tạo decoder có thể cần mock/config test riêng thay vì khởi tạo các client JWK ngoài môi trường test; mục tiêu không phải liên hệ IdP production.

### 18.2. Ma trận JWT thật và route

| # | Route | Token test | Kỳ vọng |
| --- | --- | --- | --- |
| T1 | `/api/tenants/acme/orders/42` | JWT Acme, đúng chữ ký/issuer/audience, `orders.read` | Xác thực; còn cần data policy |
| T2 | `/api/tenants/blue/orders/42` | JWT Blue, đúng issuer/audience, `orders.read` | Xác thực; còn cần data policy |
| T3 | Route Acme | JWT Blue dù có `orders.read` | Bị từ chối ở authentication |
| T4 | Route Blue | JWT Acme | Bị từ chối ở authentication |
| T5 | Route Acme | JWT tự ký bằng khóa không thuộc Acme | Bị từ chối |
| T6 | Route Acme | JWT do Acme ký nhưng `aud=billing-api` | Bị từ chối |
| T7 | Route Acme | JWT đã hết hạn | Bị từ chối |
| T8 | Route Acme | JWT hợp lệ thiếu `orders.read` | Authentication thành công, authorization 403 |
| T9 | Route Acme | JWT hợp lệ, đủ scope, order thuộc Blue | Business policy từ chối |
| T10 | `/api/tenants/unknown/orders` | JWT bất kỳ | Không có fallback manager chấp nhận |
| T11 | Route `acme-evil` | JWT Acme | Không match nhầm prefix Acme |
| T12 | Route Acme | Header Host giả | Không tự đổi issuer/JWKS tin cậy |
| T13 | Issuer không thuộc allowlist | JWT do attacker ký | Resolver từ chối, không tự discovery tùy ý |
| T14 | Route Acme | Không có Bearer token | Không vào protected endpoint |
| T15 | Route Acme | JWT Acme, DB membership lỗi | Không cho qua business action khi chưa kiểm tra được quyền |

### 18.3. Dựng mock JWKS và ký JWT thật

Một integration test nên:

1. Tạo **hai cặp khóa RSA/EC test-only**, một cho Acme và một cho Blue.
2. Dựng WireMock/MockWebServer làm endpoint JWKS cho từng tenant.
3. Tạo JWT có chữ ký thật, `kid`, `iss`, `aud`, `sub`, `exp` và `scope` đúng profile test.
4. Cấu hình tenant resolver dùng **JWKS mock**, không gọi IdP thật.
5. Gửi HTTP request với `Authorization: Bearer <signed-JWT>` qua `MockMvc` hoặc test server.
6. Kiểm tra T1–T15 và xác nhận không có thao tác nghiệp vụ khi bị từ chối.

**Đừng nhúng private key production vào test repo.** Sử dụng key chỉ phục vụ test, có vòng đời rõ và không thể dùng để phát token của môi trường thật.

### 18.4. Những gì `jwt()` của Spring Security Test kiểm tra

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/tenants/acme/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Đây là **snippet thân test** với imports, MockMvc, controller và service fixtures phù hợp. `jwt()` giả lập authentication, có thể phù hợp để test rule `hasAuthority` hoặc business method. **Không dùng kết quả 200 của test này để kết luận resolver, JWT signature, JWKS, issuer hay audience hoạt động đúng**.

### 18.5. Test 401 và 403 riêng biệt

Một kế hoạch:

~~~text
No token -> authentication entry point
Invalid issuer/signature/audience -> authentication failure
Valid token, missing SCOPE_orders.read -> authorization denied
Valid token, scope allowed, wrong owner/tenant -> data policy denied
~~~

Đừng chỉ kiểm tra response status; test một thao tác hủy đơn cần xác nhận **OrderService.cancel không được gọi, database không đổi, event không được phát** khi request bị chặn.

## 19. Kiểm thử bằng code: introspection/issuer registry và dependency outage

### 19.1. Khi tenant được thêm hoặc thu hồi

Kiểm tra:

~~~text
Issuer mới chưa được duyệt
  -> mọi JWT của issuer đó bị từ chối

Issuer được duyệt
  -> chỉ JWT hợp lệ, đúng aud/profile mới được chấp nhận

Issuer bị thu hồi
  -> request tiếp theo không được dùng manager cũ như trust hợp lệ
~~~

Nếu hệ thống cập nhật registry runtime, test concurrent requests trong lúc cập nhật, đồng thời bảo đảm không có race condition cho issuer bị revoked.

### 19.2. Khi JWKS/AS down

Kiểm tra:

- API khởi động có phụ thuộc discovery tất cả issuers không?
- Tenant chưa từng được sử dụng có thể bị ảnh hưởng ở request đầu thế nào?
- Nếu cache còn public key hợp lệ, decoder có tiếp tục xác minh token được không?
- Key rotation và unknown `kid` có dẫn tới JWKS refresh hay fail closed?
- Lỗi mạng có khiến hệ thống vô tình cho phép `permitAll()` không?
- Có retry storm khi nhiều request cùng gặp JWKS lỗi không?

**Kết quả bắt buộc:** request không có đủ bằng chứng xác thực tin cậy **không được thực hiện protected operation**. Có thể trả 401 hoặc 5xx theo exception strategy; nhưng không chuyển outage thành bypass authentication.

### 19.3. Theo dõi độ trễ và scale

Trong Servlet stack, JWT decoding và network calls cho JWK discovery thường dùng tài nguyên request threads/HTTP client tương ứng. Khi có nhiều issuers và request đầu, hãy theo dõi:

- Discovery/JWKS latency và failure rate theo tenant.
- Cache hit/miss và số lượng managers được tạo.
- Thread pool, HTTP connection pool, timeouts.
- Decoder validation failures phân loại theo issuer/audience/expired/signature.
- Unexpected-issuer attempts (không log raw token).
- Quyền bị từ chối theo tenant và endpoint.

**Tránh tạo manager mới trên mọi request.** Cache có kiểm soát giúp giảm overhead nhưng phải có chiến lược cập nhật khi issuer mất trust.

## 20. Logging/audit trong ứng dụng nhiều tenant

Một hệ thống phục vụ nhiều tổ chức cần audit đủ để phân tích “ai đã truy cập dữ liệu của tenant nào”, nhưng không được làm lộ credential.

Có thể ghi sau khi xác minh:

~~~text
request_id
route_tenant
verified_issuer
verified_subject hoặc internal_user_id (theo chính sách PII)
verified_client_id nếu hợp đồng có
http_method
normalized_route
authorization_outcome
resource_tenant
policy_reason_category
~~~

**Không log:**

- Nguyên `Authorization` header hoặc JWT.
- Signing private key, introspection client secret.
- Claims chưa xác minh như thể chúng là danh tính đáng tin.
- Email/PII nhạy cảm không cần thiết.
- Unbounded issuer/tenant input làm metric label gây cardinality explosion.

### 20.1. Issuer ở resolver chưa phải verified issuer

Khi `JwtIssuerAuthenticationManagerResolver` đọc `iss` để chọn manager, một log:

~~~text
requested_issuer=<unverified value>
~~~

có thể dùng cho security diagnostics nếu đã sanitize và rate limit; **không** gọi nó là `authenticated_issuer` cho đến khi decoder chấp nhận token. Phân biệt input chưa đáng tin với identity đã xác thực.

### 20.2. Tenant từ URL chưa phải membership

Một log “user truy cập tenant Blue” phải dựa trên cả route tenant và kết quả authorization. Chỉ vì URL chứa Blue không có nghĩa caller là thành viên Blue. Audit nên lưu **outcome**: denied ở authentication, denied ở authorization hay allowed.

## 21. Những lỗi thường gặp khi triển khai

### 21.1. Tin mọi issuer mà JWT tự khai

Sai:

~~~text
JWT iss bất kỳ
  -> API tải discovery/JWKS từ URL đó
  -> token do issuer ấy ký thì chấp nhận
~~~

Cách này mở issuer trust boundary và có nguy cơ SSRF. Dùng trusted issuers/registry được quản trị.

### 21.2. Không kiểm tra audience theo tenant

Token được ký đúng bởi issuer Acme nhưng dành cho Billing API **không** được gọi Orders API. Thêm audience validator hoặc resource binding tương đương.

### 21.3. Resolver chỉ đọc tenant trong header rồi cấp quyền

`X-Tenant-Id: blue` do caller gửi chỉ là input; nó không tự chứng minh membership hoặc audience. Chọn manager từ trusted registry rồi xác minh token và data policy.

### 21.4. Chỉ dùng `sub` làm ID người dùng toàn cục

Hai issuers có thể dùng cùng `sub`. Sử dụng `(iss, sub)` cho external identity, ánh xạ sang internal user ID khi cần.

### 21.5. Nhầm AuthN thành AuthZ

`AuthenticationManagerResolver` không thay quyền sở hữu Order 42. Cần kiểm tra tenant, owner, assignment và scope.

### 21.6. Tạo decoder mới cho từng request

Có thể tạo tải discovery/JWKS không cần thiết và làm cạn tài nguyên. Cache manager/decoder theo trusted issuer/tenant cùng invalidation.

### 21.7. Dùng cùng manager cho route tenant mà quên issuer

Nếu route Blue dùng decoder không có issuer validator, JWT Acme có thể bị chấp nhận trong những mô hình key chia sẻ. Mỗi manager phải kiểm tra issuer/audience phù hợp.

### 21.8. Dùng access token từ OIDC login Client như ID token

ID token không được dùng thay access token của Resource Server. Phải kiểm tra đúng token profile và audience API.

### 21.9. Bật CSRF disable chỉ vì “đa tenant JWT”

Chỉ có thể tắt CSRF cho chain **không xác thực bằng ambient browser credential**, sau khi đánh giá threat model. Cookie JWT stateless vẫn có CSRF risk.

### 21.10. Một `SecurityFilterChain` không bao phủ mọi URL

`securityMatcher("/api/**")` không bảo vệ `/admin/**` hoặc `/internal/**` nếu không có chain khác. Dùng fallback policy và test path boundaries.

### 21.11. Dùng Host/Forwarded headers không đáng tin để tìm JWKS

Rủi ro SSRF và issuer confusion. Chỉ dùng host sau trusted proxy validation làm key vào registration đã được duyệt.

### 21.12. Coi `jwt()` MockMvc là test multi-issuer authentication

`jwt()` thường bỏ qua decoder/resolver. Cần signed-token integration test.

### 21.13. Đổi issuer registry nhưng không làm mới cache

Manager cũ có thể tiếp tục tin issuer vừa bị thu hồi. Cần cấu hình version/invalidation và xử lý concurrency có chủ đích.

### 21.14. Có `ROLE_ADMIN` ở tenant này thì làm admin mọi tenant

Đây là lỗi ranh giới authorization; role cần namespace/binding đúng tenant và resource policy.

### 21.15. Lỗi JWKS thì tự bỏ xác thực để giữ availability

Fail open nguy hiểm. Khi không thể xác minh token, không thực hiện protected operation. Tối ưu availability bằng issuer/JWKS infrastructure, caching và timeout an toàn.

### 21.16. Multiple issuer resolver cho hệ thống chỉ có một issuer

Nếu một issuer phục vụ nhiều resource tenants, vấn đề có thể nằm ở tenant claim/membership/authorization, không phải authentication manager selection. Đừng tăng độ phức tạp không cần thiết.

## 22. Checklist thiết kế và bàn giao

1. Tenant nghĩa là issuer riêng, resource tenant, route tenant hay một kết hợp?
2. Có thực sự cần nhiều authentication managers không, hay một issuer với resource authorization là đủ?
3. Issuer/tenant registry có được quản lý từ nguồn tin cậy không?
4. Resolver có bao giờ tin `iss`, host hoặc header chưa xác minh như một trust anchor không?
5. Có dùng `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` khi phù hợp không?
6. Với custom resolver, manager có kiểm tra chữ ký/issuer/audience/time riêng không?
7. Có kiểm tra access token profile thay vì nhận OIDC ID token không?
8. `JwtAuthenticationProvider` có converter authority đúng schema của từng issuer không?
9. External identity có dùng `(iss, sub)` để tránh collision không?
10. Tenant-specific role/membership có được kiểm tra theo resource tenant không?
11. Route prefix, URL encoding, host và forwarded headers có được test không?
12. Unknown tenant/issuer có fail closed không?
13. Có fallback SecurityFilterChain bảo vệ các đường chưa match không?
14. Decoder/manager có được cache với giới hạn/refresh phù hợp không?
15. Khi issuer bị revoke, cache/trust state có cập nhật kịp không?
16. JWKS/discovery outage có dẫn tới bypass authentication không?
17. Client Credentials/service token có policy riêng với user token không?
18. Những request thiếu scope có bị 403 và request token invalid có bị từ chối ở authentication không?
19. Test signed JWT có bao gồm cross-tenant token substitution không?
20. Các request bị từ chối có bảo đảm không gây database/event side effect không?

## 23. Bài tập tình huống

**Tình huống A:** API tin Acme và Blue. Token giả tự khai `iss=https://attacker.example.test`, có JWT được attacker ký. Resolver nên làm gì?

**Không chọn manager cho issuer này** nếu issuer không nằm trong trusted registry. Không dùng URL attacker để tải JWKS và tự thêm issuer mới.

**Tình huống B:** JWT của Acme có chữ ký hợp lệ nhưng `aud=["billing-api"]`. Orders API có được nhận nếu scope có `orders.read`?

**Không.** Audience phải phù hợp Orders API theo hợp đồng; scope trùng tên không khắc phục audience sai.

**Tình huống C:** Request `/api/tenants/blue/orders/42` mang token đã xác minh của Acme. Route resolver chọn manager nào?

**Manager Blue** theo route. Manager đó phải từ chối token Acme do issuer/audience (và có thể signing keys) không phù hợp. Không fallback sang manager Acme chỉ để request thành công.

**Tình huống D:** Một issuer chung phát JWT cho cả Acme và Blue, token có `tenant_id`. Có nhất thiết dùng `JwtIssuerAuthenticationManagerResolver`?

**Không.** Nếu authentication issuer chung, có thể dùng một manager và kiểm tra tenant membership/owner ở authorization. Multi-tenant resource không đồng nghĩa multi-issuer.

**Tình huống E:** Hai issuers cấp `sub="user-842"`. Có thể dùng `authentication.getName()` một mình làm khóa người dùng toàn hệ thống không?

**Không mặc định.** Phải dùng issuer + subject hoặc ánh xạ sang internal user ID có ràng buộc tin cậy.

**Tình huống F:** Trình duyệt gửi `X-Tenant-Id: blue` nhưng token chỉ dành cho Acme. Header có đủ để chuyển user sang Blue?

**Không.** Header có thể là selector nhưng không cấp quyền; cần token contract và business membership.

**Tình huống G:** `JwtIssuerAuthenticationManagerResolver` đọc issuer trước khi xác minh token. Như vậy có vi phạm bảo mật không?

**Không nhất thiết**, nếu issuer chỉ là **khóa chọn từ allowlist**, manager tương ứng tiếp tục xác minh chữ ký, issuer và các claims. Sẽ nguy hiểm nếu claim chưa xác minh được dùng làm trust anchor tùy ý.

**Tình huống H:** Token hợp lệ, scope đủ, nhưng Order 42 thuộc tenant khác. Resolver đã chạy thành công, API có được trả đơn?

**Không.** Resolver chỉ chọn manager; quyền dữ liệu phải kiểm tra tenant/owner/assignment.

**Tình huống I:** Unit test `mockMvc.with(jwt())` trả 200 với scope `orders.read`. Điều đó có chứng minh resolver chọn đúng JWKS Acme không?

**Không.** Test mock authentication có thể bỏ qua resolver/decoder. Cần ký JWT thật bằng test key và đi qua filter chain, decoder, manager.

**Tình huống J:** JWT issuer thuộc allowlist, nhưng JWKS đang down khi tenant gọi API lần đầu. Có nên tự chấp nhận token dựa vào payload và scope không?

**Không.** Nếu không có key tin cậy/cached verifier hợp lệ để xác minh chữ ký, authentication phải thất bại an toàn.

**Tình huống K:** Tenant Blue đã bị hủy đăng ký nhưng manager Blue vẫn nằm trong cache. Hệ thống cần chú ý điều gì?

Cần **revoke trust trong registry và invalidation/version manager cache** theo policy; không để cache tiếp tục chấp nhận issuer không còn được phép.

**Tình huống L:** JWT từ hai issuers đều có scope `orders.read`. Có thể kết luận user ở tenant nào cũng xem được mọi đơn?

**Không.** Scope cho biết loại thao tác; quyền trên resource còn phụ thuộc tenant membership, subject, owner và các policy nghiệp vụ.

---

## Kết luận

Trong **Spring Security OAuth2 Resource Server dùng Servlet**, `AuthenticationManagerResolver<HttpServletRequest>` giúp chọn **`AuthenticationManager` theo request**, hữu ích khi một API phục vụ nhiều tenant với **các issuer, signing keys, audience hoặc authentication profile khác nhau**. Nếu bài toán chỉ là nhiều trusted JWT issuers, `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` cung cấp cách cấu hình gọn. Nếu cần ràng buộc tenant theo URL/host hoặc cấu hình đặc thù, một custom resolver có thể chọn các `JwtAuthenticationProvider`/`JwtDecoder` đã được đăng ký trước.

Ranh giới bảo mật không được thay đổi: **issuer/tenant trước xác minh chỉ là dữ liệu để chọn manager, không phải bằng chứng danh tính**; chỉ trusted registry được xác định issuer/JWKS. Manager phải xác minh chữ ký, issuer, audience, thời hạn và token profile; sau đó HTTP/method security cùng business policy phải kiểm tra scope, role, **tenant membership, owner và quyền trên từng tài nguyên**. Kiểm thử cả positive và negative paths, đặc biệt token của tenant A dùng ở route B, issuer không đáng tin, audience sai và JWKS outage. **Resolver chọn cách xác thực; quyền thực tế vẫn phải được chứng minh và thực thi tại Resource Server.**
