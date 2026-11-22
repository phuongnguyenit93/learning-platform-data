# OpaqueTokenAuthenticationProvider và BearerTokenAuthentication

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một API nhận Bearer access token không nhất thiết phải xử lý nó như JWT. Với **opaque token**, Resource Server thường xác thực token bằng cách liên hệ **Authorization Server** thông qua **OAuth 2.0 Token Introspection** (RFC 7662) thay vì tự đọc claims và kiểm chữ ký JWS.

Hai lớp trung tâm trong luồng **Servlet Resource Server** là:

- **OpaqueTokenAuthenticationProvider**: một **AuthenticationProvider** dùng **OpaqueTokenIntrospector** để xác thực access token và tạo kết quả Authentication.
- **BearerTokenAuthentication**: loại **Authentication thành công** mà provider tạo theo mặc định sau khi token được introspection chấp nhận; nó giữ **OAuth2AuthenticatedPrincipal**, access token và các **GrantedAuthority**.

Tên gần giống còn có **BearerTokenAuthenticationToken**. Đây lại là **yêu cầu xác thực đầu vào**, được tạo từ chuỗi Bearer token mà client gửi. Nó chưa chứng minh token hợp lệ.

Sự khác biệt rất quan trọng: **đưa token vào AuthenticationManager không phải đã xác thực; introspection thành công và có một Authentication phù hợp mới thiết lập danh tính có thể sử dụng cho authorization**. Bài học này đi từ HTTP filter tới provider, introspection endpoint, object model, Spring Boot configuration, custom policy, kiểm thử và vận hành an toàn.

## 1. Opaque token là gì?

Bearer access token là credential mà client gửi tới API, thường qua header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.com
Authorization: Bearer mV6tR2nQp9xL8fA4
~~~

Chuỗi token trên chỉ là **ví dụ giả định**, không phải credential thật. **Bearer** nghĩa là bên nắm token có thể sử dụng nó trong phạm vi được cấp, nên token cần được giữ kín và truyền qua HTTPS.

**Opaque token** là token mà Resource Server không được giả định có cấu trúc để tự giải mã và xác minh. Nó có thể là chuỗi ngẫu nhiên tham chiếu trạng thái lưu tại Authorization Server, hoặc là giá trị có cấu trúc nhưng Resource Server vẫn được thiết kế sử dụng introspection.

Resource Server cần hỏi một nguồn tin cậy:

- Token có **active** không?
- Token thuộc chủ thể nào (**sub**)?
- Token được cấp cho client nào (**client_id**)?
- Token có những **scope** nào?
- Token có dành cho resource/audience của API này không?
- Có metadata thời hạn, issuer, tenant hoặc chính sách đặc thù nào?

### 1.1. JWT Resource Server và opaque Resource Server

| Khía cạnh | JWT/JWS | Opaque token/introspection |
|---|---|---|
| Cơ chế xác thực phổ biến | **JwtDecoder**, chữ ký và validators | **OpaqueTokenIntrospector**, hỏi Authorization Server |
| AuthenticationProvider | **JwtAuthenticationProvider** | **OpaqueTokenAuthenticationProvider** |
| Authentication thành công | **JwtAuthenticationToken** | **BearerTokenAuthentication** mặc định |
| Principal mặc định | **Jwt** | **OAuth2AuthenticatedPrincipal** |
| Nguồn claims/attributes | JWT đã được xác minh | Introspection response được tin cậy |
| Scope authority | Thường **SCOPE_*** | Thường **SCOPE_*** |
| Khả năng phát hiện revocation | Cần thêm chính sách khi verify offline | AS có thể trả **active=false** |
| Phụ thuộc mạng | Có thể dùng cached public key | Thường gọi introspection endpoint khi chưa có kết quả cache hợp lệ |

Tên **opaqueToken()** trong Spring Security nói về **chiến lược xác thực bằng introspection**. Một token trông giống JWT vẫn có thể đi theo con đường này, nếu ứng dụng được cấu hình introspect thay vì verify JWT cục bộ.

## 2. Phân biệt ba đối tượng có tên gần giống

| Đối tượng | Vai trò | Token đã được xác thực chưa? |
|---|---|---|
| **BearerTokenAuthenticationToken** | Authentication request được tạo từ chuỗi token client gửi | **Chưa** |
| **OpaqueTokenAuthenticationProvider** | Thành phần kiểm token bằng OpaqueTokenIntrospector | Thực hiện quá trình xác thực |
| **BearerTokenAuthentication** | Kết quả Authentication mặc định sau introspection thành công | **Đã xác thực** theo kết quả và chính sách được cấu hình |

### 2.1. BearerTokenAuthenticationToken là request object

Khi một Servlet request mang Bearer token được xử lý, **BearerTokenAuthenticationFilter** trích token rồi tạo một đối tượng yêu cầu xác thực:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;

BearerTokenAuthenticationToken request =
    new BearerTokenAuthenticationToken("example-opaque-token");
~~~

Ở lớp này, **getToken()** trả về **String** raw token đầu vào. Việc gọi constructor không gửi introspection request và không gắn bất kỳ sự tin cậy nào cho token.

Không được tạo authority **ROLE_ADMIN** từ chuỗi chưa xác thực chỉ vì đối tượng này triển khai giao diện Authentication.

### 2.2. OpaqueTokenAuthenticationProvider là người xử lý

**OpaqueTokenAuthenticationProvider** triển khai **AuthenticationProvider**. Nó nhận request token, nhờ **OpaqueTokenIntrospector** xác minh token rồi tạo Authentication thông qua **OpaqueTokenAuthenticationConverter**.

Một mô hình rút gọn:

~~~text
BearerTokenAuthenticationToken(rawToken)
    -> OpaqueTokenAuthenticationProvider
    -> OpaqueTokenIntrospector.introspect(rawToken)
    -> OAuth2AuthenticatedPrincipal (chỉ khi token hợp lệ)
    -> OpaqueTokenAuthenticationConverter
    -> BearerTokenAuthentication mặc định
~~~

Nếu introspection không xác nhận token, provider **không trả một Authentication thành công** cho token đó.

### 2.3. BearerTokenAuthentication là kết quả

**BearerTokenAuthentication** là kết quả thường được đặt vào SecurityContext sau khi token được xác thực. Nó lưu:

- **OAuth2AuthenticatedPrincipal** làm principal mặc định.
- **OAuth2AccessToken** dưới dạng token/credential đã xác thực.
- **GrantedAuthority** được suy ra từ metadata/mapper tin cậy.
- **Token attributes** từ introspection response.

Tên **BearerTokenAuthentication** không bảo đảm tất cả trường tùy biến như **aud**, **tenant_id**, **permissions** đã được kiểm đủ cho nghiệp vụ. Những policy đó vẫn phải được thiết kế.

## 3. Luồng xử lý Servlet từ request tới SecurityContext

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager / ProviderManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant S as SecurityContext và Authorization

    C->>F: GET /api/orders/42 + Bearer token
    F->>F: Tạo BearerTokenAuthenticationToken
    F->>M: authenticate(request)
    M->>P: authenticate(BearerTokenAuthenticationToken)
    P->>I: introspect(raw token)
    I->>AS: POST /introspect qua HTTPS với client authentication
    AS-->>I: active=true và token metadata
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>M: BearerTokenAuthentication
    M-->>F: Authentication thành công
    F->>S: Lưu Authentication trong SecurityContext
    S->>S: Kiểm scope, role và quyền theo bản ghi
    S-->>C: Response theo authorization policy
~~~

Sơ đồ thể hiện các bước logic của Spring Security **Servlet**. Chi tiết internal filter, exception handling và những authority framework bổ sung có thể phụ thuộc phiên bản.

1. **BearerTokenAuthenticationFilter** lấy token từ request theo quy tắc Bearer.
2. Filter tạo **BearerTokenAuthenticationToken**, gửi đến **AuthenticationManager**.
3. **ProviderManager** chọn provider thích hợp; với opaque-token Resource Server là **OpaqueTokenAuthenticationProvider**.
4. Provider gọi **OpaqueTokenIntrospector**.
5. Introspector thông thường gọi Authorization Server qua HTTPS.
6. Nếu token hợp lệ, introspector trả **OAuth2AuthenticatedPrincipal**.
7. Provider chuyển kết quả thành **BearerTokenAuthentication** mặc định.
8. Filter đưa Authentication vào **SecurityContext** theo lifecycle request.
9. HTTP/method/domain authorization đánh giá authorities và quyền trên tài nguyên cụ thể.

### 3.1. Vì sao chỉ có token trong header chưa đủ?

Header **Authorization: Bearer** có thể chứa:

- Token thật, còn hiệu lực và đúng audience.
- Token không tồn tại hoặc đã bị thu hồi.
- Token hết hạn.
- Token dành cho một API khác.
- Một chuỗi ngẫu nhiên do attacker tự viết.
- Một JWT thật nhưng không được phép dùng với Resource Server này.

Filter nhận token không biết tình huống nào đúng. **Provider + introspector** mới có trách nhiệm thiết lập kết quả xác thực. Không được bỏ qua bước này rồi coi các claims do client tự khai là đáng tin.

## 4. API của OpaqueTokenAuthenticationProvider

Lớp nằm trong package:

~~~text
org.springframework.security.oauth2.server.resource.authentication
~~~

Các API chính:

| API | Chức năng |
|---|---|
| **OpaqueTokenAuthenticationProvider(OpaqueTokenIntrospector)** | Tạo provider với introspector |
| **supports(Class<?> authentication)** | Cho biết provider có thể xét một loại Authentication request |
| **authenticate(Authentication authentication)** | Thực hiện introspection, kiểm token và tạo Authentication |
| **setAuthenticationConverter(OpaqueTokenAuthenticationConverter)** | Tùy biến cách tạo Authentication sau introspection |

### 4.1. supports không có nghĩa token active

Ví dụ:

~~~java
OpaqueTokenAuthenticationProvider provider =
    new OpaqueTokenAuthenticationProvider(introspector);

boolean supported =
    provider.supports(BearerTokenAuthenticationToken.class);
~~~

**supported** chỉ nói provider có khả năng xử lý loại request, không phải token nào cũng được phép dùng. Không có introspection nào được chứng minh chỉ bằng supports().

### 4.2. authenticate mới gọi quá trình xác thực

Một cách mô tả contract:

~~~text
authenticate(Authentication request):
    rawToken = lấy từ BearerTokenAuthenticationToken
    principal = introspector.introspect(rawToken)
    result = converter.convert(rawToken, principal)
    return result
~~~

Đây là **pseudocode**, không phải mã nguồn Spring Security. Nếu introspector thất bại, provider báo lỗi thông qua authentication exception path, không trả một principal hợp lệ.

### 4.3. setAuthenticationConverter được dùng khi nào?

**OpaqueTokenAuthenticationConverter** là extension point để chuyển token cùng principal được introspection xác nhận thành một đối tượng **Authentication**. Hợp đồng:

~~~java
Authentication convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal
);
~~~

Một ứng dụng có thể dùng custom converter nếu cần một loại Authentication riêng hoặc logic identity mapping đặc thù. Nhưng:

- Converter chỉ nên dùng **principal đã được introspection xác thực**.
- Nó không thay thế quá trình introspection.
- Nó không được tự nâng mọi token active thành ROLE_ADMIN.
- Nếu trả loại Authentication khác, controller không nên ép kiểu **BearerTokenAuthentication** một cách mặc định.

Trên các Spring Security version hỗ trợ, provider cho phép:

~~~java
provider.setAuthenticationConverter(customAuthenticationConverter);
~~~

Ở đây **customAuthenticationConverter** là một đối tượng được ứng dụng triển khai theo hợp đồng; đoạn code chỉ minh họa API extension point. Với Spring Boot, thường thuận tiện hơn khi khai báo converter/introspector phù hợp trong configuration thay vì đăng ký provider thủ công.

## 5. OpaqueTokenIntrospector là ranh giới tin cậy

Giao diện nằm trong package:

~~~text
org.springframework.security.oauth2.server.resource.introspection
~~~

Hình thức rút gọn:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

Ý nghĩa:

- Nhận **raw token** chưa được xác nhận.
- Dùng cơ chế đáng tin cậy để xác minh, thông thường gọi RFC 7662 introspection endpoint.
- Trả về **OAuth2AuthenticatedPrincipal** khi token được chấp nhận.
- Báo lỗi nếu token không hợp lệ hoặc không thể introspect theo contract.

Một implementation khác có thể kiểm token trong kho dữ liệu/tập đăng ký token nội bộ đáng tin cậy, nhưng phải giữ cùng nguyên tắc xác minh.

### 5.1. Các implementation phổ biến

| Implementation | Khi nào dùng? |
|---|---|
| **SpringOpaqueTokenIntrospector** | Default HTTP introspection client trong nhiều cấu hình Spring Security |
| **RestClientOpaqueTokenIntrospector** | Dùng RestClient, phù hợp khi tùy chỉnh HTTP client, timeout, headers |
| **Custom OpaqueTokenIntrospector** | Thêm audience validation, domain permission mapping, cache hoặc nguồn token đặc thù |
| **OpaqueTokenAuthenticationConverter** | Tạo kết quả Authentication từ principal được introspect |

Một ví dụ builder cho các bản Spring Security hỗ trợ:

~~~java
OpaqueTokenIntrospector trusted =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri("https://login.example.com/oauth2/introspect")
        .clientId("orders-resource-server")
        .clientSecret("example-secret-only")
        .build();
~~~

Đây là placeholder, **không đặt client secret thật trong mã nguồn**. Builder này có trong các bản Spring Security tương ứng, chẳng hạn 6.5+; với bản cũ hơn cần dùng constructor/API được phiên bản đó hỗ trợ.

## 6. RFC 7662: request và response introspection

Authorization Server thường cung cấp introspection endpoint riêng, ví dụ:

~~~text
https://login.example.com/oauth2/introspect
~~~

Đây là một trust endpoint được **Resource Server cấu hình trước**, không lấy từ giá trị do token/client tự chỉ định.

### 6.1. Request HTTP minh họa

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic <encoded-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

**token** là tham số chính; **token_type_hint** là gợi ý tùy chọn theo RFC 7662. Client authentication bảo vệ quyền gọi introspection. Phải sử dụng HTTPS, kiểm chứng certificate/hostname và bảo vệ thông tin xác thực Resource Server.

### 6.2. Token đang active

Response JSON minh họa:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "client_id": "web-client",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "iss": "https://login.example.com/realms/shop",
  "exp": 1893456000,
  "tenant_id": "tenant-a"
}
~~~

Các trường ngoài **active** phụ thuộc hợp đồng với Authorization Server. Không bắt buộc mọi introspection endpoint phải trả đủ **aud**, **iss**, **sub**, **tenant_id** hoặc mọi dữ liệu giống JWT.

**active=true** cho biết Authorization Server coi token hoạt động theo chính sách của nó; Resource Server vẫn cần áp điều kiện về audience, scope, token type, tenant hoặc nghiệp vụ nếu chính sách API yêu cầu.

### 6.3. Token không active

~~~json
{
  "active": false
}
~~~

Token không hoạt động phải bị từ chối. Một response inactive tối giản không nói rõ vì sao token không hợp lệ; đó có thể là token không tồn tại, đã hết hạn hoặc bị thu hồi.

Không tiếp tục gán principal từ metadata cũ hoặc tin token chỉ vì client gửi **sub** cùng request.

### 6.4. Introspection không tự đồng nghĩa audience validation

Một ứng dụng có thể chỉ cần response active + scope theo hợp đồng Authorization Server; ứng dụng khác phải kiểm **aud = orders-api**. Nếu đối tượng được phục vụ có yêu cầu audience chặt chẽ, phải kiểm result có thông tin đầy đủ hoặc dùng cơ chế resource binding tin cậy của AS.

Nếu introspection endpoint không trả **aud**, nhưng policy bắt buộc audience, phải giải quyết contract với issuer. Không im lặng bỏ điều kiện chỉ để token đi qua.

## 7. BearerTokenAuthentication có cấu trúc gì?

**BearerTokenAuthentication** là một implementation của Authentication, kế thừa **AbstractOAuth2TokenAuthenticationToken<OAuth2AccessToken>**.

| Thành phần | Giá trị/ý nghĩa |
|---|---|
| **getPrincipal()** | Mặc định một **OAuth2AuthenticatedPrincipal** |
| **getName()** | Tên principal, thường gắn với **sub** nếu có |
| **getAuthorities()** | Tập **GrantedAuthority** |
| **getTokenAttributes()** | Map token metadata từ introspection |
| **getToken()** | Một **OAuth2AccessToken** đã được xác thực, không phải raw String |
| **getCredentials()** | Credential gắn với Authentication; phải bảo vệ |
| **isAuthenticated()** | Cho biết Authentication đã được chấp nhận |

Một kết quả có thể được hình dung:

~~~text
BearerTokenAuthentication
  authenticated: true
  principal: OAuth2AuthenticatedPrincipal
  name: user-123
  authorities:
    - SCOPE_orders.read
    - SCOPE_orders.write
  tokenAttributes:
    sub: user-123
    aud: [orders-api]
    scope: orders.read orders.write
    tenant_id: tenant-a
  token: OAuth2AccessToken
~~~

Ở những release Spring Security hiện đại, bộ authorities có thể chứa thêm authority framework như **FACTOR_BEARER**. Điều này phụ thuộc version/cấu hình và **không tự thay thế scope/role nghiệp vụ**.

### 7.1. getToken() của hai loại Authentication khác nhau

Hai tên dễ nhầm:

~~~text
BearerTokenAuthenticationToken.getToken()
    -> String raw token

BearerTokenAuthentication.getToken()
    -> OAuth2AccessToken
~~~

**OAuth2AccessToken** có thể chứa token value. Không đưa object này ra HTTP response, không log credentials và không lưu nó trong tracing/metrics labels.

### 7.2. getTokenAttributes()

Dữ liệu introspection được lưu trong một Map:

~~~java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

Map<String, Object> attributes = authentication.getTokenAttributes();
Object subject = attributes.get("sub");
Object tenant = attributes.get("tenant_id");
~~~

Kiểu của các giá trị có thể khác nhau tùy cách introspector chuyển response: String, Collection, Instant hoặc kiểu khác. Không ép kiểu tùy tiện nếu claim không có contract ổn định.

### 7.3. Principal và getName()

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal =
    (OAuth2AuthenticatedPrincipal) authentication.getPrincipal();

String subject = principal.getAttribute("sub");
String principalName = authentication.getName();
~~~

Khi **sub** hiện diện, name thường phản ánh subject. Nếu không có sub, cách xác định name phụ thuộc implementation. Trong hệ thống multi-issuer, định danh người dùng an toàn thường là **issuer + sub**, không chỉ sub hoặc email.

## 8. Controller truy cập Authentication sau introspection

Trong Spring MVC, controller có thể nhận BearerTokenAuthentication hoặc principal đã được xác thực.

### 8.1. BearerTokenAuthentication được inject

~~~java
import java.util.Map;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, String> me(BearerTokenAuthentication authentication) {
        return Map.of("subject", authentication.getName());
    }
}
~~~

Ví dụ giả định name không null và endpoint chỉ nhận request được xác thực theo opaque strategy. Một ứng dụng thực tế có thể cần kiểm claim bắt buộc và dùng DTO.

### 8.2. @AuthenticationPrincipal

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/identity")
    Map<String, String> identity(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        String sub = principal.getAttribute("sub");
        return Map.of("subject", sub);
    }
}
~~~

Ví dụ cũng giả định introspection response có **sub**. Nếu issuer không luôn gửi sub, phải định nghĩa cách xử lý/null validation phù hợp.

Nếu dùng **custom OpaqueTokenAuthenticationConverter** trả loại Authentication khác, controller không nên phụ thuộc cứng vào BearerTokenAuthentication. Khi cần abstraction, inject **Authentication** hoặc principal theo contract thực tế.

### 8.3. Đừng trả toàn bộ token attributes

Một introspection response có thể chứa client_id, tenant_id, permissions, token value hoặc metadata nhạy cảm. Không tự return **authentication.getTokenAttributes()** nguyên vẹn cho client chỉ vì đã xác thực. Cần giới hạn field, kiểm quyền và tránh lộ thông tin nội bộ.

## 9. Cấu hình Spring Boot opaque Resource Server

Một cấu hình thông dụng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: replace-through-secret-manager
~~~

Hai giá trị client-id/client-secret là minh họa; trong ứng dụng thật hãy nạp qua biến môi trường hoặc secret manager. Không commit secret thật.

- **opaquetoken** là property group của Spring Boot.
- **introspection-uri** là endpoint tin cậy của Authorization Server.
- **client-id/client-secret** là credentials của Resource Server dùng gọi introspection.
- Không cần **issuer-uri/jwk-set-uri** của JWT để introspect theo chiến lược này.
- Nếu API cần audience/issuer validation trên kết quả introspection, phải cấu hình policy phù hợp; không giả định mọi JWT validator được tái sử dụng tự động.

### 9.1. SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OpaqueApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Trong chain này, request được xác thực bằng introspection trước khi các rule phụ thuộc authority kiểm quyền. **permitAll** là quyết định authorization cho endpoint public, không tự vô hiệu hóa mọi filter.

Nếu định nghĩa SecurityFilterChain riêng, kiểm cả phạm vi **securityMatcher**, thứ tự chain và những route không được chain nào bảo vệ. **anyRequest** trong một chain hẹp không tự bao phủ mọi endpoint ứng dụng.

### 9.2. Dependencies

| Spring Boot | Starter Resource Server thường dùng |
|---|---|
| **3.x** | **spring-boot-starter-oauth2-resource-server** |
| **4.x** | **spring-boot-starter-security-oauth2-resource-server** |

Opaque introspection cần module Resource Server và dependencies liên quan. **spring-security-oauth2-jose** không phải điều kiện bắt buộc chỉ để introspect opaque token, khác với JWT signature verification. Hãy dùng Spring Boot dependency management để tránh ghép sai major Spring Security versions.

## 10. Scope được ánh xạ thành GrantedAuthority

Introspection response thường có:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "sub": "user-123"
}
~~~

Trong cấu hình mặc định, Spring Security chuyển các scope thành authorities có tiền tố **SCOPE_**:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Vì vậy có thể bảo vệ endpoint:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

**Scope** không đồng nghĩa **role**:

- **hasAuthority("SCOPE_orders.read")** kiểm scope authority.
- **hasRole("ADMIN")** theo mặc định kiểm **ROLE_ADMIN**.
- Claim **roles: ["ADMIN"]** trong introspection metadata không mặc nhiên tạo ROLE_ADMIN.
- Các scope OIDC như **openid**, **profile**, **email** không tự là quyền nghiệp vụ.

Bên cạnh scope, Resource Server vẫn cần kiểm **tenant**, ownership và các điều kiện domain đối với đơn hàng cụ thể.

### 10.1. Authority trong Spring Security mới

Một số bản Spring Security gần đây thêm authority framework liên quan đến authentication factor, ví dụ **FACTOR_BEARER**, cho kết quả introspection thành công. Khi kiểm quyền, không nên assert rằng Authentication chỉ có duy nhất SCOPE_orders.read; có thể có authority khác mang ý nghĩa hệ thống.

**FACTOR_BEARER không phải quyền đọc/ghi nghiệp vụ**, cũng không biến token active thành quyền trên mọi API.

## 11. Tùy biến introspector để kiểm audience

Một ứng dụng có thể yêu cầu introspection result chứa audience **orders-api**. Nếu issuer thực sự cung cấp claim đó, có thể **bọc introspector tin cậy** để thêm validation:

~~~java
import java.util.Collection;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector introspector() {
        OpaqueTokenIntrospector trusted = SpringOpaqueTokenIntrospector
            .withIntrospectionUri(
                "https://login.example.com/oauth2/introspect")
            .clientId("orders-resource-server")
            .clientSecret("replace-through-secret-manager")
            .build();

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                trusted.introspect(token);

            Object aud = principal.getAttribute("aud");
            boolean allowed = "orders-api".equals(aud)
                || (aud instanceof Collection<?> values
                    && values.contains("orders-api"));

            if (!allowed) {
                throw new BadOpaqueTokenException(
                    "Introspected token not intended for orders-api");
            }
            return principal;
        };
    }
}
~~~

Ví dụ dùng placeholder client credentials; **không hardcode secret thật**. Thực tế có thể inject credentials qua Spring configuration/secret manager.

Điểm quan trọng:

1. **trusted.introspect(token)** phải chạy trước.
2. **aud** được kiểm trên principal đã được introspection chấp nhận.
3. Nếu aud bắt buộc nhưng bị thiếu, ví dụ từ chối theo fail-closed policy.
4. Nếu AS không trả aud, cần thiết kế một cơ chế resource binding đáng tin khác, không tự nới điều kiện.
5. Custom **@Bean OpaqueTokenIntrospector** thường thay thế auto-configuration của Boot; không giả định property tự áp mọi policy vào bean mới.

Có thể chọn **RestClientOpaqueTokenIntrospector** thay SpringOpaqueTokenIntrospector khi cần kiểm soát HTTP client/timeout theo API phù hợp với version.

## 12. Tùy biến permissions mà giữ scope mặc định

Nếu Authorization Server trả:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read",
  "permissions": ["orders.approve"]
}
~~~

Ứng dụng có thể cần authority **PERM_orders.approve** ngoài **SCOPE_orders.read**. Một decorator cho introspector giúp bổ sung policy mà không bỏ xác thực gốc:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class PermissionsIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    PermissionsIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);
        Set<GrantedAuthority> granted =
            new LinkedHashSet<>(principal.getAuthorities());

        Object raw = principal.getAttribute("permissions");
        if (raw instanceof Collection<?> values) {
            for (Object value : values) {
                // Minh họa allowlist một permission nghiệp vụ.
                if ("orders.approve".equals(value)) {
                    granted.add(new SimpleGrantedAuthority(
                        "PERM_orders.approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(), principal.getAttributes(), granted);
    }
}
~~~

**Không** dùng decorator này trên một delegate giả chỉ trả principal cho mọi token. Trong production delegate phải thực hiện introspection đáng tin cậy.

Cũng không nên tự map tất cả quyền bất kỳ từ JSON thành ROLE_ADMIN. Phải có hợp đồng rõ: issuer nào được cấp permission, permission thuộc resource/tenant nào và role có bị giới hạn thời gian không.

## 13. Khi nào cần custom OpaqueTokenAuthenticationConverter?

**OpaqueTokenAuthenticationConverter** chạy sau introspection và chuyển **raw token + OAuth2AuthenticatedPrincipal** thành Authentication.

Nó phù hợp khi:

- Cần một loại Authentication/domain principal riêng.
- Cần chuẩn hóa metadata principal theo application contract.
- Cần bổ sung authorities từ một nguồn tin cậy khác.
- Cần mở rộng kết quả xác thực theo cơ chế Spring Security hỗ trợ.

Nếu chỉ cần thêm authority từ introspection attributes, decorator **OpaqueTokenIntrospector** thường đơn giản hơn.

Một custom converter **không được**:

- Trả authenticated principal cho raw token chưa introspect.
- Gán ROLE_ADMIN cho mọi token active.
- Lấy thông tin quyền từ request body/header không được xác minh.
- Phát tán raw token vào log/response.
- Bỏ qua token type/issuer/audience contract của API.

Default converter thường trả **BearerTokenAuthentication**. Custom converter có thể trả Authentication khác; lúc đó controller cần được viết dựa trên interface hoặc kiểu principal phù hợp.

## 14. Unit test OpaqueTokenAuthenticationProvider

Có thể kiểm provider mà không cần gọi Authorization Server thật bằng một introspector **test double**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class OpaqueTokenProviderTest {

    @Test
    void successfulIntrospectionProducesAuthenticatedPrincipal() {
        OpaqueTokenIntrospector introspector = token -> {
            if (!"test-active-token".equals(token)) {
                throw new BadOpaqueTokenException("Token inactive");
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of("sub", "user-123",
                       "scope", List.of("orders.read")),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );
        };

        OpaqueTokenAuthenticationProvider provider =
            new OpaqueTokenAuthenticationProvider(introspector);

        Authentication result = provider.authenticate(
            new BearerTokenAuthenticationToken("test-active-token")
        );

        assertInstanceOf(BearerTokenAuthentication.class, result);
        assertTrue(result.isAuthenticated());
        assertEquals("user-123", result.getName());
        assertTrue(result.getAuthorities().stream().anyMatch(
            a -> "SCOPE_orders.read".equals(a.getAuthority())));
    }
}
~~~

Điều bài test chứng minh:

- Provider nhận **BearerTokenAuthenticationToken**.
- Provider gọi introspector.
- Khi introspection thành công, kết quả mặc định là **BearerTokenAuthentication**.
- Authorities có thể bao gồm scope mong đợi.

Nó **không chứng minh TLS, client credentials hoặc endpoint production đang hoạt động**. Test double chỉ dùng trong test, tuyệt đối không làm introspector production.

### 14.1. Token inactive phải bị từ chối

Thử một introspector test double ném **BadOpaqueTokenException**:

~~~java
OpaqueTokenIntrospector introspector = token -> {
    throw new BadOpaqueTokenException("Token inactive");
};
~~~

Khi provider xử lý BearerTokenAuthenticationToken, nó không được tạo một Authentication thành công. Trong test thật cần kiểm exception type/HTTP response phù hợp với version và cấu hình exception handling.

### 14.2. Cần thêm test HTTP introspection thật với server giả lập

Dùng một HTTP stub server ở môi trường test cho endpoint introspection để kiểm:

- Phương thức POST và request parameters đúng.
- Introspection client authentication được gửi đúng.
- active=true được map thành principal/authorities.
- active=false bị từ chối.
- 401/403 từ introspection endpoint không tạo principal.
- Timeout, 5xx và TLS error không làm Resource Server fail-open.
- Response thiếu aud, scope hoặc claim bắt buộc được xử lý đúng chính sách.

## 15. MockMvc và opaqueToken() không tự test provider

Spring Security Test có **opaqueToken() request post-processor** giúp kiểm authorization mà không cần gọi endpoint introspection.

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Trong test class đã cấu hình MockMvc và endpoint phù hợp.
@Test
void readScopeAllowsOrderEndpoint() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )))
        .andExpect(status().isOk());
}
~~~

Test này phù hợp để kiểm **SecurityFilterChain và authorities**, nhưng thường **bỏ qua OpaqueTokenAuthenticationProvider và HTTP introspection thật** vì đã inject Authentication mô phỏng.

Một kết quả 200 còn phụ thuộc controller và dữ liệu test. Nếu handler trả 404 hoặc gặp domain policy khác, test cần fixture phù hợp.

### 15.1. Ma trận test gợi ý

| Trường hợp | Authentication | Authorization | Kết quả thông thường |
|---|---|---|---|
| Không token, endpoint private | Không có | Không đủ | 401 |
| Token active=false | Thất bại | Không được cấp quyền | 401 |
| Token active=true, scope orders.read | Thành công | Đủ quyền đọc | Controller được gọi |
| Token active=true, không có orders.read | Thành công | Thiếu scope | 403 |
| Token active=true, aud khác API | Custom audience policy từ chối | Không đi vào business handler | 401 theo flow |
| Token active=true, đủ scope, tenant khác | Thành công | Domain policy từ chối | 403 hoặc 404 |
| Introspection bị timeout | Không thể xác thực đáng tin cậy | Không được cấp quyền | Lỗi tùy exception handling; không fail-open |
| Introspection sai client-secret | Upstream từ chối | Không được cấp quyền | Cần sửa credentials/configuration |
| Token đã bị thu hồi | AS trả active=false | Bị từ chối | 401 |

Các mã HTTP mang tính thường gặp, không phải một cam kết cho mọi cấu hình Spring Security. Lỗi hạ tầng có thể ra 5xx hoặc được mapping khác.

## 16. Introspection và bảo mật vận hành

### 16.1. URL introspection phải được cấu hình tin cậy

Không để request hoặc token quyết định endpoint introspection. Nếu cho token tự chọn URL, attacker có thể gây **SSRF**, gửi raw token/credentials đến host do họ kiểm soát hoặc khiến server gọi địa chỉ nội bộ.

Nguồn tin cậy phải xuất phát từ cấu hình issuer/Authorization Server, hoặc allowlist/routing đa tenant có quản trị rõ.

### 16.2. Bảo vệ token và client credentials

- Sử dụng HTTPS và kiểm certificate chain/hostname.
- Giữ client-secret trong secret manager hoặc cấu hình bảo vệ; rotate khi cần.
- Không log Authorization: Bearer, Authorization: Basic, raw token, introspection response nhạy cảm.
- Không đưa token vào URL query string hoặc tracing labels.
- Thiết lập timeout, connection pooling, giới hạn outbound traffic và response size.
- Phân biệt DNS/TLS/upstream outage với token inactive.
- Không dùng cấu hình trust-all certificates để tạm sửa lỗi môi trường.

### 16.3. Fail closed khi AS lỗi

Một request có token không thể introspect **không được xem như đã xác thực chỉ vì token trông giống chuỗi hợp lệ**. Khi Authorization Server không sẵn sàng, Resource Server có thể báo lỗi, áp dụng retry hợp lý hoặc dùng cache hợp lệ theo policy, nhưng không được tự sinh principal thành công.

## 17. Hiệu năng, cache và revocation

Vì introspection thường cần network call, nó có trade-off:

| Yếu tố | Hệ quả |
|---|---|
| **Latency** | Thêm thời gian round trip trước khi xử lý controller |
| **Throughput** | Số lượt introspection tăng theo lượng request API |
| **Availability** | Resource Server phụ thuộc khả dụng của AS/introspection service |
| **Revocation** | AS có thể trả active=false ngay sau thu hồi |
| **Caching** | Giảm latency nhưng có thể kéo dài thời gian một token bị thu hồi vẫn được chấp nhận |

Nếu cache kết quả **active=true**, cần chính sách rõ về TTL, thời hạn token và mức trễ thu hồi cho phép. Không cache vô thời hạn và không dùng cached active result quá hạn.

Một số hướng vận hành:

1. Theo dõi latency, tỷ lệ lỗi, timeout và số introspection calls.
2. Cấu hình HTTP client pooling và timeout hợp lý.
3. Giới hạn cache TTL theo exp còn lại và yêu cầu revocation.
4. Có rate limiting để tránh bão token ngẫu nhiên.
5. Không coi upstream timeout là active=true.
6. Kiểm token revocation bằng những test thay đổi active giữa các request.

Không giả định Spring Security mặc định có một cơ chế caching phù hợp mọi chính sách; kiểm theo introspector/cấu hình thật.

## 18. JWT cũng có thể đi qua opaqueToken()

Một ứng dụng có thể nhận access token **dạng JWT** nhưng chọn xác thực nó bằng **introspection** thay vì dùng JwtDecoder. Ví dụ khi cần hỏi AS mỗi request để biết token đã bị thu hồi hay chưa.

Trong trường hợp ấy:

~~~text
Bearer JWT (chuỗi có dấu chấm)
  -> BearerTokenAuthenticationFilter
  -> OpaqueTokenAuthenticationProvider
  -> OpaqueTokenIntrospector
  -> BearerTokenAuthentication mặc định
~~~

Điều quyết định loại Authentication không phải chỉ là hình thức raw token mà còn là **cơ chế xác thực được cấu hình**.

Nếu introspection response chỉ trả active mà không trả những claim API cần, đừng tự parse JWT chưa xác minh rồi dùng claims ấy để cấp quyền. Cần có chiến lược trust/validation bổ sung rõ, hoặc yêu cầu AS trả metadata phù hợp.

## 19. Servlet và Reactive WebFlux

Bài học tập trung vào Spring Security **Servlet/MVC**:

~~~text
SecurityFilterChain
BearerTokenAuthenticationFilter
AuthenticationManager / ProviderManager
OpaqueTokenAuthenticationProvider
OpaqueTokenIntrospector
BearerTokenAuthentication
~~~

Với **WebFlux**, Spring Security sử dụng các đối tượng reactive tương ứng:

- **SecurityWebFilterChain**.
- **ReactiveOpaqueTokenIntrospector**.
- **OpaqueTokenReactiveAuthenticationManager** và các thành phần reactive khác.

Không copy nguyên cấu hình **HttpSecurity** hoặc đưa HTTP introspection blocking vào Reactor event loop mà không xét mô hình execution. Với WebFlux, sử dụng các API reactive chính thức theo version.

## 20. Những sai lầm dễ gặp

### 20.1. Coi BearerTokenAuthenticationToken đã được xác thực

Đây chỉ là request authentication object. Không dùng raw token này để tạo quyền mà chưa qua introspection.

### 20.2. Tự tạo BearerTokenAuthentication từ JSON request

Nếu một controller đọc thông tin client gửi rồi dựng principal/authorities, nó đã bỏ qua ranh giới xác thực. Chỉ dùng result từ trusted introspector.

### 20.3. Custom introspector luôn trả principal

~~~java
// SAI: minh họa implementation bypass xác thực.
OpaqueTokenIntrospector unsafe = token ->
    new DefaultOAuth2AuthenticatedPrincipal(
        "admin",
        Map.of("sub", "admin"),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
~~~

Mã này chấp nhận mọi chuỗi token, hoàn toàn không gọi AS. Chỉ có thể dùng một test double được giới hạn rõ trong unit test, **không được dùng production**.

### 20.4. active=true thành quyền toàn hệ thống

Token còn hiệu lực không đồng nghĩa đủ scope, đúng audience, đúng tenant hay có quyền truy cập mọi bản ghi.

### 20.5. Coi roles trong response tự thành ROLE_*

Spring Security mặc định chủ yếu ánh xạ scope thành **SCOPE_***. Nếu API dùng roles/permissions tùy biến phải ánh xạ có chủ đích và kiểm domain policy.

### 20.6. Bỏ các quyền scope khi custom mapping

Nếu tạo principal mới chỉ chứa ROLE_ADMIN, có thể làm mất những SCOPE_* cần cho endpoint. Khi bổ sung quyền, nên giữ những authorities đã được nguồn tin cậy cấp và policy cho phép.

### 20.7. Opaque token nghĩa là không có expiration

AS có thể xác nhận active dựa trên thời hạn, revocation và chính sách khác. Không suy ra opaque token là vĩnh viễn. Metadata **exp** có thể có hoặc không; nếu dùng cache phải kiểm hạn hiệu lực.

### 20.8. Bỏ qua token error để tăng availability

Khi introspection lỗi network/TLS, không được tự cho phép truy cập; đây là lỗi hạ tầng xác thực cần xử lý fail-closed.

### 20.9. Ghi raw token vào log

Bearer token là credential có thể bị tái sử dụng. Không log getToken().getTokenValue(), credentials hoặc nguyên Authentication. Chỉ log request ID và metadata an toàn theo chính sách.

### 20.10. Confuse 401 với 403

Token inactive thường dẫn tới **401**. Token active nhưng không đủ SCOPE_orders.read thường dẫn tới **403**. Hai tình huống cần xử lý khác nhau, không nên “sửa” 403 bằng permitAll.

## 21. Quy trình end-to-end: Orders API

Giả sử hợp đồng:

~~~text
Trusted AS:        https://login.example.com
Introspection URI: https://login.example.com/oauth2/introspect
Required audience: orders-api
Read scope:        orders.read
Domain policy:     đúng tenant và quan hệ sở hữu
~~~

Client gửi:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <opaque-access-token>
~~~

**Bước A — Nhận token.** BearerTokenAuthenticationFilter trích raw token và tạo BearerTokenAuthenticationToken. Chưa có principal tin cậy.

**Bước B — Chọn provider.** ProviderManager chuyển request đến OpaqueTokenAuthenticationProvider.

**Bước C — Introspect.** Provider gọi introspector. Introspector gửi token tới Authorization Server đáng tin cậy. Nếu active=false hoặc request không xác thực được, không được tạo Authentication thành công.

**Bước D — Kiểm token policy.** Nếu response có audience và policy bắt buộc **orders-api**, API kiểm audience. Tương tự issuer/client/token type nếu hợp đồng yêu cầu.

**Bước E — Tạo Authentication.** Provider dùng converter mặc định tạo BearerTokenAuthentication với principal/authorities như SCOPE_orders.read.

**Bước F — Kiểm HTTP authorization.** SecurityFilterChain yêu cầu **SCOPE_orders.read**. Nếu thiếu authority, request bị chặn.

**Bước G — Kiểm domain authorization.** Service kiểm đơn hàng số 42 thuộc tenant/chủ thể được phép. Scope hợp lệ không thay thế quyền trên bản ghi.

**Bước H — Trả response.** Chỉ sau các lớp kiểm tra trên API mới xử lý dữ liệu và trả kết quả.

Đây là chuỗi **raw Bearer token → introspection bởi nguồn tin cậy → Authentication thành công → authority/domain authorization**.

## 22. Câu hỏi tự kiểm tra

**1. BearerTokenAuthenticationToken có phải BearerTokenAuthentication không?**

Không. Loại đầu là **request chưa xác thực**, loại sau là **kết quả thành công mặc định** của opaque Resource Server.

**2. OpaqueTokenAuthenticationProvider có phải HTTP client introspection không?**

Nó là **AuthenticationProvider**, sử dụng **OpaqueTokenIntrospector**. Introspector implementation thường mới là thành phần gửi HTTP request tới AS.

**3. OpaqueTokenIntrospector trả về gì khi thành công?**

**OAuth2AuthenticatedPrincipal** với token attributes và authorities phù hợp. Nếu token không hợp lệ phải báo lỗi, không trả principal thành công.

**4. BearerTokenAuthentication.getToken() có trả raw String như BearerTokenAuthenticationToken.getToken() không?**

Không. Kết quả thành công trả **OAuth2AccessToken**; request token trả String raw token. Cả hai phải được bảo vệ.

**5. active=true có đồng nghĩa được gọi mọi endpoint không?**

Không. API vẫn kiểm audience, scope, roles/permissions và quyền theo tài nguyên.

**6. Vì sao opaque token active nhưng API trả 403?**

Có thể do token không có authority **SCOPE_orders.read** hoặc bị domain authorization từ chối.

**7. Nếu một JWT được gửi vào opaqueToken() thì sao?**

Nó có thể được introspect như một chuỗi token; kết quả vẫn thường là BearerTokenAuthentication. Không tự đổi sang JwtDecoder chỉ vì raw token có dấu chấm.

**8. Có nên cache active=true không?**

Chỉ theo chính sách revocation/expiration rõ và TTL giới hạn. Cache quá lâu có thể chấp nhận token đã bị thu hồi.

**9. Khi AS unavailable có thể bỏ qua introspection không?**

Không. Nếu không có bằng chứng token hợp lệ theo policy, không được tạo authenticated principal.

**10. Custom authentication converter luôn trả BearerTokenAuthentication?**

Không. Converter có thể trả kiểu Authentication khác, nên code phụ thuộc loại cụ thể phải được kiểm.

## Kết luận

Trong Spring Security Servlet Resource Server, **BearerTokenAuthenticationToken** là authentication request chứa chuỗi token, **OpaqueTokenAuthenticationProvider** xác minh token qua **OpaqueTokenIntrospector**, và **BearerTokenAuthentication** là kết quả Authentication thành công mặc định.

**OpaqueTokenIntrospector** cung cấp ranh giới tin cậy, thường bằng RFC 7662 introspection endpoint của Authorization Server. Khi token được chấp nhận, Spring Security có thể ánh xạ scope thành **SCOPE_*** và dùng **OAuth2AuthenticatedPrincipal** để đưa attributes vào SecurityContext. Sau đó, API vẫn phải kiểm audience, scope, tenant và quyền nghiệp vụ.

Không được tự tạo Authentication từ raw token, không coi active=true là quyền toàn hệ thống, không tiết lộ access token/credentials, và không fail-open khi introspection gặp lỗi.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — OpaqueTokenAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html)
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security API — BearerTokenAuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html)
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — OpaqueTokenAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenAuthenticationConverter.html)
- [Spring Security API — SpringOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
