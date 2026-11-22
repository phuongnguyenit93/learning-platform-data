# OAuth2AuthenticatedPrincipal, attributes, name và authorities

Trong **Spring Security OAuth 2.0 Resource Server**, access token dạng **opaque token** thường không được API tự giải mã như JWT. Thay vào đó, Resource Server gửi token đến **token introspection endpoint** của Authorization Server để xác định token có đang hoạt động hay không và nhận metadata cần thiết. Sau bước xác minh đó, Spring Security biểu diễn danh tính và quyền truy cập bằng một đối tượng triển khai **`OAuth2AuthenticatedPrincipal`**.

Đối tượng này có ba khía cạnh quan trọng:

- **`attributes`:** dữ liệu/metadata về token hoặc principal được introspection trả về và introspector chấp nhận.
- **`name`:** tên định danh mà Spring Security trình bày thông qua `getName()`, không nhất thiết đồng nghĩa với username hiển thị, email hoặc `client_id`.
- **`authorities`:** tập `GrantedAuthority` được dùng bởi các quy tắc phân quyền như `hasAuthority("SCOPE_orders.read")`.

Một lỗi phổ biến là thấy response introspection có `"scope": "orders.read"` rồi giả định mọi service sẽ tự có authority `SCOPE_orders.read`, hoặc thấy `sub` rồi coi người gọi có quyền đọc mọi bản ghi. Cần hiểu **ai tạo principal**, **quy tắc chuyển attributes thành authorities**, **getName đến từ đâu** và **quyền nghiệp vụ nào vẫn phải được kiểm tra riêng**.

Bài này tập trung vào **Opaque Token Resource Server** trong Spring Security Servlet, đồng thời so sánh các kiểu principal với JWT Resource Server để tránh ép kiểu sai.

## 1. Vị trí của OAuth2AuthenticatedPrincipal trong luồng opaque token

Client gọi Orders API bằng một access token:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer 6b09f46f-opaque-token-example
~~~

Chuỗi `6b09f46f-opaque-token-example` chỉ là dữ liệu minh họa, không phải token sử dụng được. Resource Server **không** dựa vào hình dạng chuỗi này để suy ra quyền người dùng.

Luồng xử lý thông dụng:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant F as BearerTokenAuthenticationFilter
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter
    participant API as Controller

    C->>F: GET /api/orders + Authorization: Bearer token
    F->>P: BearerTokenAuthenticationToken qua AuthenticationManager
    P->>I: introspect(token)
    I->>AS: HTTP POST introspection (TLS + client authentication)
    AS-->>I: active=true + scope/sub/client_id/exp/...
    I-->>P: OAuth2AuthenticatedPrincipal
    P-->>F: BearerTokenAuthentication
    F->>F: Gắn Authentication vào SecurityContext
    F->>A: Tiếp tục xử lý request
    alt Đủ quyền
        A->>API: Cho request đi tiếp
        API-->>C: Dữ liệu được phép
    else Thiếu quyền
        A-->>C: 403 Forbidden
    end
~~~

Nếu Authorization Server trả `active: false` hoặc introspector không thể xác thực token theo chính sách, **không tạo một principal đáng tin** để request đi tiếp. Thông thường authentication thất bại dẫn tới **401 Unauthorized**. Khi token đã xác thực nhưng không đủ quyền endpoint, thường là **403 Forbidden**.

| Thành phần | Vai trò |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Trích Bearer token và tạo yêu cầu xác thực |
| `BearerTokenAuthenticationToken` | Mang chuỗi token ban đầu; chưa phải principal đã xác thực |
| `AuthenticationManager` | Chuyển yêu cầu đến provider phù hợp |
| `OpaqueTokenAuthenticationProvider` | Gọi introspector, dựng authentication thành công hoặc báo lỗi |
| `OpaqueTokenIntrospector` | Xác minh token với issuer và trả metadata/principal đáng tin theo contract |
| `OAuth2AuthenticatedPrincipal` | Giao diện cho attributes, name, authorities của chủ thể đã được introspection chấp nhận |
| `DefaultOAuth2AuthenticatedPrincipal` | Một triển khai phổ biến của giao diện trên |
| `BearerTokenAuthentication` | Đối tượng `Authentication` kết quả được đặt trong `SecurityContext` |
| `AuthorizationFilter` và method security | Kiểm tra authorities và các chính sách truy cập |

**Không nhầm `OAuth2AuthenticatedPrincipal` với Authorization Server hoặc OAuth2 Client.** Đây là đối tượng **ở phía Resource Server** để biểu diễn principal sau introspection; nó **không phát hành, làm mới hoặc thu hồi token**.

## 2. Introspection response: dữ liệu đầu vào của principal

Theo mô hình OAuth 2.0 Token Introspection (RFC 7662), Resource Server gửi token tới endpoint được issuer cho phép. Ví dụ request nội bộ:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

Credentials dùng để gọi introspection **khác** access token được client gửi đến API. Endpoint, phương thức xác thực và các trường yêu cầu thực tế phụ thuộc Authorization Server.

Một response hoạt động có thể là:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "username": "alice",
  "scope": "orders.read orders.export",
  "token_type": "Bearer",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "tenant_id": "t-7",
  "permissions": ["orders:view", "reports:export"]
}
~~~

Nếu token không hoạt động:

~~~json
{
  "active": false
}
~~~

Không được suy luận rằng **mọi introspection response đều có tất cả trường trong ví dụ**. Theo RFC 7662, `active` là trường quan trọng để báo trạng thái; nhiều metadata còn lại **có thể tùy chọn** hoặc bị ẩn tùy quyền của caller. Một số issuer có claim riêng như `tenant_id` hoặc `permissions`.

### Ba mức dữ liệu cần tách biệt

1. **HTTP JSON introspection response:** dữ liệu thô từ Authorization Server qua endpoint được cấu hình.
2. **`OAuth2AuthenticatedPrincipal.getAttributes()`:** map attributes đã được introspector xử lý và trả cho Spring Security. Kiểu Java có thể đã được chuẩn hóa.
3. **`OAuth2AuthenticatedPrincipal.getAuthorities()`:** authorities được introspector hoặc custom converter tạo ra từ thông tin đã chấp nhận; **không phải toàn bộ JSON attributes**.

Khi introspection trả `active: false`, Resource Server phải từ chối token. Không được “dùng tạm” dữ liệu `scope`/`sub` từ một response không được chấp nhận.

**Bảo vệ kênh introspection:** chỉ gọi endpoint của issuer tin cậy qua TLS, quản lý credentials như secrets, giới hạn timeout và xử lý lỗi fail closed. Không gửi token tới URL do client tự khai báo trong payload hoặc header.

## 3. Giao diện OAuth2AuthenticatedPrincipal có những gì?

Giao diện thuộc module Spring Security OAuth 2.0 Core:

~~~java
import java.util.Collection;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

// Những phương thức khái niệm quan trọng:
Map<String, Object> attributes = principal.getAttributes();
Object subject = principal.getAttribute("sub");
String name = principal.getName();
Collection<? extends GrantedAuthority> authorities =
    principal.getAuthorities();
~~~

`getAttribute(String)` là cách truy cập thuận tiện tới một thuộc tính trong map. Nó không tự xác thực nội dung claim, không bảo đảm thuộc tính hiện diện, và không mặc định ép dữ liệu JSON thành một DTO domain cụ thể.

| API | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `getAttributes()` | `Map<String, Object>` | Metadata đã được introspector cung cấp |
| `getAttribute("sub")` | Generic value, có thể null | Lấy một attribute theo tên |
| `getName()` | `String` | Tên principal do implementation chọn |
| `getAuthorities()` | `Collection<? extends GrantedAuthority>` | Các quyền Spring Security dùng để phân quyền |

**`getName()` không phải bản sao toàn bộ attributes**, và **`getAuthorities()` cũng không phải map claims**. Chúng là ba góc nhìn khác nhau lên một principal.

### Ví dụ sử dụng DefaultOAuth2AuthenticatedPrincipal

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

Map<String, Object> attributes = Map.of(
    "sub", "user-42",
    "client_id", "orders-web",
    "scope", "orders.read"
);

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-42",
        attributes,
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

System.out.println(principal.getName());          // user-42
System.out.println(principal.getAttribute("sub")); // user-42
System.out.println(principal.getAuthorities());    // [SCOPE_orders.read]
~~~

Ví dụ **tự dựng principal** chỉ để mô tả kiểu dữ liệu. Không được tạo principal như vậy trực tiếp từ request JSON chưa được issuer xác minh rồi coi request đã authenticated.

Trong các phiên bản Spring Security thông dụng, `DefaultOAuth2AuthenticatedPrincipal` có constructor nhận **tên**, **attributes** và **authorities**. Ngoài ra có constructor nhận attributes/authorities và chọn name từ thuộc tính thông dụng như `sub`. Không nên giả định cách chọn tên của mọi custom introspector đều giống nhau; cần xem implementation đang sử dụng.

## 4. Attributes: đọc đúng schema và kiểu Java

Attributes thường chứa các trường có kiểu khác nhau:

| Thuộc tính introspection | Dạng JSON có thể gặp | Kiểu Java có thể gặp sau introspector |
| --- | --- | --- |
| `sub` | `"user-42"` | `String` |
| `client_id` | `"orders-web"` | `String` |
| `scope` | `"orders.read orders.export"` | `String` hoặc kiểu được adapter chuẩn hóa |
| `aud` | `["orders-api"]` hoặc string | `Collection<?>` hoặc `String`, tùy implementation |
| `exp`, `iat`, `nbf` | NumericDate (JSON number, đơn vị giây) | `Instant` hoặc numeric type, tùy introspector/converter |
| `permissions` | Mảng string tùy chỉnh | `Collection<?>` |
| `tenant_id` | String tùy hợp đồng | `String` |
| Object tùy chỉnh | JSON object | Thường là `Map<?, ?>` hoặc DTO do adapter tạo |

**JSON number không có nghĩa luôn là Java `Long`.** Với thời gian JWT hoặc introspection metadata, một adapter có thể chuyển NumericDate sang `Instant`. Không nên viết `(Long) principal.getAttribute("exp")` hoặc `(List<String>) principal.getAttribute("aud")` nếu chưa xác nhận schema thực tế của implementation.

Ví dụ đọc attributes an toàn về mặt kiểu:

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.Map;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

void inspect(OAuth2AuthenticatedPrincipal principal) {
    Map<String, Object> attrs = principal.getAttributes();

    Object rawSubject = attrs.get("sub");
    String subject = rawSubject instanceof String s ? s : null;

    Object rawClient = attrs.get("client_id");
    String clientId = rawClient instanceof String s ? s : null;

    Object rawExpiry = attrs.get("exp");
    Instant expiresAt = rawExpiry instanceof Instant i ? i : null;

    Object rawPermissions = attrs.get("permissions");
    if (rawPermissions instanceof Collection<?> permissions) {
        for (Object permission : permissions) {
            if (permission instanceof String p) {
                // Xử lý p theo hợp đồng issuer/API.
            }
        }
    }
}
~~~

Mã ví dụ **không** tự thay thế kiểm tra expiration của introspector; nó chỉ đọc giá trị đã được chấp nhận. Nếu một thư viện đang trả số giây thay vì `Instant`, cần bộ chuyển đổi đã xác định **rõ đơn vị**. Không dựa vào số chữ số để suy đoán seconds/milliseconds.

### Attributes không nhất thiết đều là user profile

`client_id` là thông tin về OAuth 2.0 client; `scope` mô tả quyền token; `exp` liên quan đến thời hạn; `sub` là subject nếu có. Những giá trị này phục vụ các mục đích khác nhau.

Không nên trả toàn bộ `principal.getAttributes()` trong response API chỉ để debug: có thể bao gồm PII, dữ liệu tenant, hoặc metadata không được phép công bố. Chọn các trường cần thiết và chuyển thành DTO theo hợp đồng API.

## 5. Name: getName không nhất thiết là username

Trong Spring Security, `Authentication.getName()` thường là định danh tiện dụng của principal. Với opaque token:

~~~text
BearerTokenAuthentication
          |
          +-- principal: OAuth2AuthenticatedPrincipal
          |      |
          |      +-- getName()
          |      +-- getAttributes()
          |      +-- getAuthorities()
          |
          +-- getName() dựa theo principal tương ứng
~~~

Một implementation `DefaultOAuth2AuthenticatedPrincipal` được tạo từ response introspection có thể dùng `sub` làm name. Nhưng:

- `sub` có thể **không có** trong response introspection của một loại token.
- `username` chỉ là tên hiển thị/đăng nhập, có thể thay đổi hoặc không duy nhất.
- `client_id` mô tả client, không tự động là subject người dùng.
- Custom introspector có thể chọn một tên khác theo hợp đồng.
- Với nhiều issuer, cùng `sub` có thể chỉ ra hai thực thể khác nhau.

Ví dụ chọn tên có chủ đích:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;

var principal = new DefaultOAuth2AuthenticatedPrincipal(
    "internal-user-841",
    Map.of(
        "iss", "https://auth.example.com/realms/shop",
        "sub", "external-user-42",
        "username", "alice"
    ),
    List.of()
);

String name = principal.getName();          // internal-user-841
String subject = principal.getAttribute("sub"); // external-user-42
~~~

Trong ví dụ, `getName()` và `sub` cố ý khác nhau. Hai giá trị không mâu thuẫn: một tên là lựa chọn của principal adapter, một giá trị là claim ban đầu.

### Nguyên tắc nhận diện ổn định

Nếu cần kiểm tra owner, tenant hoặc audit, nên dựa trên **identity đã được xác minh từ issuer** và ánh xạ sang ID nội bộ. Với token chứa `iss` và `sub`, cặp `(iss, sub)` có thể là đầu vào cho identity mapping, nhưng phải xác định issuer đó thực sự là nguồn đã được introspection tin cậy. Không coi string `getName()` là bằng chứng độc lập đủ để truy cập dữ liệu của mọi tenant.

Đối với token Client Credentials, nếu issuer chỉ cung cấp `client_id` mà không có user `sub`, hãy áp dụng một **machine-principal policy** riêng: client nào được gọi API nào, phạm vi tài nguyên nào, tenant nào. Không tự biến client ID thành “người sở hữu” bản ghi của con người.

## 6. Authorities: từ scope introspection tới SCOPE_...

Trong cấu hình opaque token Resource Server thông dụng, introspector tích hợp của Spring Security ánh xạ các scope thành `GrantedAuthority` với tiền tố **`SCOPE_`**.

Response introspection:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read orders.export"
}
~~~

Authorities thường có:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

Như vậy, HTTP authorization có thể dùng:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Chú ý:

1. `scope` trong OAuth 2.0 thường là **string các scope phân tách bằng dấu cách**, không mặc định là JSON array.
2. Prefix `SCOPE_` là cách Spring Security đặt tên authority. Rule yêu cầu `SCOPE_orders.read` khác `orders.read`.
3. Nếu introspector tùy chỉnh tạo principal nhưng không tạo authorities, Spring Security không nhất thiết tự đọc `scope` để ánh xạ lại trong mọi cấu hình. Trách nhiệm mapping nằm ở adapter/converter bạn chọn.
4. Claim `permissions`/`roles` tùy chỉnh **không tự được ánh xạ** thành `ROLE_ADMIN` hoặc `PERMISSION_orders.export`.
5. Có `SCOPE_orders.read` không đồng nghĩa được xem **từng order cụ thể**; cần kiểm tra ownership, tenant hoặc chia sẻ trong service.

### Authority là tên chính xác, không phải nhãn trang trí

Các authority sau khác nhau:

~~~text
SCOPE_orders.read
PERMISSION_orders.read
ROLE_ORDER_READER
orders.read
~~~

`hasAuthority("SCOPE_orders.read")` chỉ khớp đúng authority theo tên đó. Trong các cấu hình thông dụng, `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN`; `hasRole` không đồng nghĩa với kiểm tra mọi scope mang chữ `admin`.

Khi thiết kế mapping, nên xác định rõ namespace nào là **OAuth scopes**, namespace nào là **roles nội bộ** và namespace nào là **permissions của Resource Server**. Không nên thêm tùy tiện authority cấp quản trị chỉ vì một claim có tên gần giống.

## 7. Phân biệt principal trong JWT và opaque token

Hai cấu hình Resource Server có thể nhận cùng HTTP header `Authorization: Bearer ...` nhưng tạo principal khác nhau:

| Đặc tính | JWT Resource Server | Opaque Token Resource Server |
| --- | --- | --- |
| Thành phần xác minh | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Authentication result thông dụng | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Principal thông dụng | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Truy cập dữ liệu | `jwt.getClaims()`, `getSubject()`, `getExpiresAt()` | `principal.getAttributes()`, `getAttribute("sub")` |
| Tên principal | Thường lấy `sub` hoặc converter riêng | Theo `OAuth2AuthenticatedPrincipal.getName()` |
| Authorities | Thường qua `JwtGrantedAuthoritiesConverter` | Từ introspector/custom mapping |
| Cần gọi issuer mỗi request? | Thường không sau khi có khóa phù hợp | Thường có introspection request nếu không cache |

**Không ép kiểu `(Jwt) authentication.getPrincipal()` trong opaque Resource Server.** Một controller viết riêng cho JWT có thể gặp lỗi hoặc không nhận đúng principal sau khi chuyển sang opaque token.

Ví dụ với Spring Security Servlet:

~~~java
import java.util.Collection;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

void inspectAuthentication(Authentication authentication) {
    if (authentication instanceof BearerTokenAuthentication bearer) {
        Object principal = bearer.getPrincipal();
        String name = bearer.getName();
        Collection<? extends GrantedAuthority> authorities =
            bearer.getAuthorities();

        // bearer.getTokenAttributes() cung cấp các attributes.
        // bearer.getToken() chứa access token: không ghi tokenValue vào log.
    }
}
~~~

Khi ứng dụng hỗ trợ nhiều loại token, tầng domain có thể chuẩn hóa danh tính thành một abstraction như `AuthenticatedActor(userId, tenantId, clientId, scopes)` **sau khi authentication thành công**, để tránh để controller/service phụ thuộc quá mạnh vào kiểu JWT hay opaque.

## 8. Cấu hình Spring Boot Servlet Resource Server cho opaque token

Dependency Maven thông dụng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_SECURE_RUNTIME_SECRET
~~~

Đây là cấu hình minh họa. Trong thực tế, lấy secret từ secret manager, biến môi trường hoặc cơ chế cấu hình bí mật được kiểm soát, **không đưa client secret thật vào source control**. Endpoint và credential phải thuộc Authorization Server được cấu hình tin cậy.

Ví dụ Java configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong cấu hình trên, introspection tích hợp tạo principal và authorities theo khả năng phiên bản. Trước khi tin một token, API cần bảo đảm **đúng issuer/introspection endpoint, đúng audience/resource, thời hạn và token purpose** theo hợp đồng. `active: true` một mình không tự bảo đảm token dành cho Orders API.

Đoạn `csrf(...disable())` phù hợp với API **stateless xác thực Bearer token** không sử dụng cookie được trình duyệt tự động gửi như credential. Nếu ứng dụng có session/cookie, cần đánh giá bảo vệ CSRF riêng.

**`permitAll()` không tự tắt Bearer filter.** Nếu một client gửi Bearer token sai đến `/health`, filter vẫn có thể thử xác thực và từ chối trước khi request tới rule `permitAll`. Đây là đặc điểm của việc xử lý token trong security chain, không phải thuộc tính của principal.

## 9. Đọc principal trong Controller và Service

Với opaque token Resource Server, có thể lấy `OAuth2AuthenticatedPrincipal` qua `@AuthenticationPrincipal`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Map<String, String> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        Map<String, String> result = new LinkedHashMap<>();
        result.put("name", principal.getName());

        Object rawSubject = principal.getAttribute("sub");
        if (rawSubject instanceof String subject) {
            result.put("subject", subject);
        }

        Object rawClient = principal.getAttribute("client_id");
        if (rawClient instanceof String clientId) {
            result.put("clientId", clientId);
        }

        return result;
    }
}
~~~

Ví dụ trên chỉ trả một vài trường để minh họa, **không** trả nguyên map attributes. Nếu API cần đảm bảo một giá trị không được null, hãy kiểm tra và xác định chính sách lỗi rõ ràng thay vì giả định introspection luôn cung cấp `sub` hoặc `client_id`.

Một lựa chọn ít phụ thuộc kiểu principal hơn:

~~~java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AuthoritiesController {

    @GetMapping("/api/my-authorities")
    List<String> authorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .toList();
    }
}
~~~

Endpoint này chỉ minh họa cách đọc authorities. Trong production, cần cân nhắc có nên công bố danh sách quyền cho client hay không, nhất là quyền nội bộ hoặc cấu trúc phân quyền nhạy cảm.

### Authorization vẫn phải kiểm tra từng bản ghi

Ví dụ token hợp lệ chứa `SCOPE_orders.read` nhưng người gọi thuộc tenant t-7, còn order 123 thuộc tenant t-8. `hasAuthority("SCOPE_orders.read")` không tự chặn truy cập xuyên tenant. Service vẫn cần kiểm tra:

~~~text
Principal đã introspect và xác minh
          |
          v
Ánh xạ issuer/subject hoặc client identity
          |
          v
Kiểm tra quyền chức năng qua authorities
          |
          v
Kiểm tra tenant membership, owner/share/relationship
          |
          v
Truy vấn dữ liệu được scope đúng tenant
~~~

Không dùng `principal.getName()` hoặc `tenant_id` từ request làm chứng cứ duy nhất để đọc tài nguyên.

## 10. Tùy chỉnh authorities bằng OpaqueTokenIntrospector

Giả sử Authorization Server trả:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "permissions": ["orders:export", "orders:approve"]
}
~~~

Bạn muốn giữ `SCOPE_orders.read` và bổ sung `PERMISSION_orders.export` theo hợp đồng API. Có thể **bọc (decorate)** một introspector đã được cấu hình để xác minh token, sau đó tạo principal mới với authorities bổ sung.

Ví dụ:

~~~java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class OrdersOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public OrdersOpaqueTokenIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Phải thành công tại nguồn introspection đáng tin trước khi mapping.
        OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

        Map<String, Object> attrs =
            new LinkedHashMap<>(verified.getAttributes());

        if (!isExpectedAudience(attrs.get("aud"))) {
            throw new OAuth2IntrospectionException(
                "Token is not intended for Orders API");
        }

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        authorities.addAll(verified.getAuthorities());

        Object raw = attrs.get("permissions");
        if (raw instanceof Collection<?> permissions) {
            for (Object permission : permissions) {
                if ("orders:export".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_orders.export"));
                }
                if ("orders:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_orders.approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            verified.getName(), attrs, authorities);
    }

    private boolean isExpectedAudience(Object aud) {
        if (aud instanceof String name) {
            return "orders-api".equals(name);
        }
        if (aud instanceof Collection<?> audiences) {
            return audiences.contains("orders-api");
        }
        return false;
    }
}
~~~

**Mã này là ví dụ một policy**: API yêu cầu introspection có `aud` hướng đến `orders-api`. Nếu issuer không cung cấp `aud`, code sẽ **fail closed**. Hệ thống thực tế phải thiết kế hợp đồng introspection và kiểm tra audience/issuer/client authorization theo thông tin issuer cung cấp, thay vì chấp nhận bất kỳ response `active: true` nào.

Ngoài ra, `verified.getAuthorities()` trong ví dụ phải là kết quả của một introspector **đã kiểm tra token hợp lệ**. Việc bổ sung permissions chỉ được phép từ claim đáng tin và một **allowlist quyền mà API hiểu**. Không tự lấy mọi string user có thể kiểm soát để tạo `ROLE_ADMIN`.

### Gắn introspector tùy chỉnh vào Resource Server

Một cấu hình minh họa cho các phiên bản còn cung cấp `NimbusOpaqueTokenIntrospector`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Bean
OpaqueTokenIntrospector ordersIntrospector() {
    OpaqueTokenIntrospector base = new NimbusOpaqueTokenIntrospector(
        "https://auth.example.com/oauth2/introspect",
        "orders-resource-server",
        "INJECT_SECURE_SECRET_AT_RUNTIME"
    );
    return new OrdersOpaqueTokenIntrospector(base);
}
~~~

Một số phiên bản Spring Security mới hơn có API/builder introspector khác (ví dụ các triển khai mang tên Spring), và một số class cũ đã hoặc sẽ được đánh dấu deprecated. **Chọn API thực sự có trong phiên bản dependency của dự án**. Đoạn này chỉ minh họa cấu trúc **delegate → policy-aware decorator**; secret thật phải được inject từ kho bí mật/runtime, không ghi cứng như ví dụ.

Trong SecurityFilterChain, có thể gắn introspector bằng DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
    opaque.introspector(ordersIntrospector)
))
~~~

Ở đây `ordersIntrospector` là object/bean đã được tạo và cung cấp đúng cho chain (không phải một biến tự xuất hiện). Nếu ứng dụng đã có `OpaqueTokenIntrospector` bean được auto-wire, không nên tạo cấu hình lặp mà không biết bean nào thực sự được sử dụng.

### Tại sao nên bảo toàn attributes nhưng tạo principal mới?

Trong ví dụ, code sao chép map attributes rồi tạo `DefaultOAuth2AuthenticatedPrincipal` mới:

~~~text
verified principal từ delegate
  getName()        -> giữ nguyên, trừ khi có policy đổi name
  getAttributes()  -> sao chép sang map cho principal mới
  getAuthorities() -> giữ + bổ sung quyền đúng allowlist
~~~

Cách này rõ ràng hơn việc cố sửa trực tiếp collection từ `getAuthorities()` hoặc map từ `getAttributes()`. Không mặc định các collection của implementation được phép mutation, cũng không nên để một component sau authentication âm thầm chỉnh quyền.

### Khi nào phải từ chối token thay vì bỏ qua claim?

Nếu profile quy định `permissions` phải là mảng string, nhưng introspection trả:

~~~json
{
  "active": true,
  "permissions": {"admin": true}
}
~~~

thì một policy nghiêm ngặt có thể **từ chối token** vì sai schema, thay vì lặng lẽ bỏ qua permissions. Cách xử lý phải được xác định bởi API: thiếu quyền tùy chọn có thể tạo authorities rỗng, còn claim bắt buộc sai kiểu có thể là lỗi authentication. Không dùng `toString()` trên object bất kỳ để tạo authority.

## 11. Tùy chỉnh name: username, subject và client identity

Giả sử introspection trả:

~~~json
{
  "active": true,
  "sub": "subject-42",
  "username": "alice",
  "client_id": "orders-web"
}
~~~

Nếu ứng dụng muốn `getName()` trả `alice` để hiển thị:

~~~java
OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

Object username = verified.getAttribute("username");
String displayName = username instanceof String s
    ? s
    : verified.getName();

OAuth2AuthenticatedPrincipal renamed =
    new DefaultOAuth2AuthenticatedPrincipal(
        displayName,
        verified.getAttributes(),
        verified.getAuthorities()
    );
~~~

Đây là **phép đổi tên hiển thị**, không phải chuyển quyền hay thay đổi subject của token. Không dùng username hiển thị làm khóa ownership hoặc identity chính trong hệ thống nhiều tenant.

Trong nhiều hệ thống, tốt hơn là **giữ `getName()` ở định danh ổn định** và đưa `username`/`preferred_username` vào DTO giao diện. Nếu phải đổi name để tương thích hệ thống legacy, hãy bảo đảm toàn bộ code dùng `getName()` hiểu được ý nghĩa mới.

### Nếu không có sub

Với một số machine-to-machine access token, introspection có thể trả `client_id` mà không có user subject. Hãy xác định:

- Đây là principal của **client**, không phải một user được suy luận.
- Client ID nào được tin, trong phạm vi issuer nào.
- Tài nguyên nào được client đó truy cập, trong tenant nào.
- Audiences/scopes và client authorization có đúng contract.

Không tự mặc định `getName() == client_id` nếu introspector không đặt tên đó, và không cho client quyền của một user chỉ vì hai chuỗi trùng nhau.

## 12. Unit test getName, attributes và authorities

Có thể dùng JUnit 5 kiểm tra principal không cần Authorization Server:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

class PrincipalUnitTest {

    @Test
    void exposesAttributesNameAndAuthoritiesSeparately() {
        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "local-user-7",
                Map.of(
                    "sub", "external-sub-42",
                    "client_id", "orders-web",
                    "scope", "orders.read"
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        assertEquals("local-user-7", principal.getName());
        assertEquals("external-sub-42", principal.getAttribute("sub"));
        assertEquals("orders-web", principal.getAttribute("client_id"));
        assertTrue(principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch("SCOPE_orders.read"::equals));
    }
}
~~~

Test này chỉ xác minh **hợp đồng của object được dựng thủ công**. Nó không chứng minh introspection endpoint hoạt động hoặc `active: false` bị từ chối.

### Kiểm tra introspector tùy chỉnh bằng fake delegate

Có thể tạo fake delegate chỉ trả principal cho chuỗi token thử nghiệm, sau đó gọi decorator:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

OpaqueTokenIntrospector fake = token -> {
    if (!"test-active-token".equals(token)) {
        throw new IllegalArgumentException("Unexpected test token");
    }
    return new DefaultOAuth2AuthenticatedPrincipal(
        "user-42",
        Map.of(
            "sub", "user-42",
            "aud", List.of("orders-api"),
            "permissions", List.of("orders:export")
        ),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
};

OpaqueTokenIntrospector decorated =
    new OrdersOpaqueTokenIntrospector(fake);

var principal = decorated.introspect("test-active-token");
// principal.getAuthorities() chứa SCOPE_orders.read và
// PERMISSION_orders.export theo converter ví dụ.
~~~

Đoạn code này chỉ kiểm tra **mapping của decorator**. Fake delegate không đại diện cho kiểm tra network/TLS hoặc token thực. Khi kiểm tra integration, cần một introspection test server/stub HTTP và security chain thật, kiểm soát response active, audience, timeout và lỗi.

## 13. HTTP integration test và Spring Security Test opaqueToken()

Spring Security Test có các request post-processors cho các dạng authentication. Với MockMvc, helper `opaqueToken()` thường cho phép gắn một principal mô phỏng vào request để kiểm tra quyền:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Giả sử có MockMvc và endpoint yêu cầu SCOPE_orders.read.
mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Test dạng này kiểm tra **authorization khi đã có Authentication**, nhưng **thường không gọi introspection endpoint thật** và không chứng minh `OpaqueTokenIntrospector` của production ánh xạ authorities đúng.

Để kiểm tra toàn bộ luồng Bearer:

1. Dùng security chain thật có `oauth2ResourceServer(...opaqueToken(...))`.
2. Gửi request HTTP với header `Authorization: Bearer ...`.
3. Thay introspection network bằng server stub hoặc mock `OpaqueTokenIntrospector` ở mức Spring context.
4. Trả principal có attributes/authorities đúng hoặc ném lỗi tương ứng để mô phỏng token inactive.
5. Khẳng định 401 cho token không hợp lệ, 403 khi thiếu quyền, và response phù hợp khi đủ quyền.
6. Với test tích hợp hơn, xác nhận client gọi endpoint introspection với TLS, authentication và timeout được cấu hình đúng.

### Ma trận tình huống

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Không gửi token đến API yêu cầu authentication | Thường 401 |
| Token có trong request nhưng introspection trả `active: false` | Không tạo principal tin cậy, thường 401 |
| Token active, có `scope: orders.read`, mapping đúng | Có authority `SCOPE_orders.read` |
| Token active, thiếu scope bắt buộc của endpoint | Authentication có thể thành công, authorization thường 403 |
| Token active nhưng `aud` dành cho API khác | Từ chối theo policy audience của Resource Server |
| Introspection mất kết nối/timeout | Fail closed, không được cấp quyền; mã HTTP tùy cách xử lý lỗi |
| Response không có `sub` | Name/identity xử lý theo contract; không tự coi là user đã biết |
| Introspection có `permissions` sai kiểu | Xử lý theo chính sách schema, không tạo authority tùy tiện |
| User có `SCOPE_orders.read` nhưng không sở hữu order | Từ chối bởi object-level authorization |

## 14. Lỗi dễ gặp và cách hiểu đúng

### 14.1. Ép kiểu principal sang Jwt

~~~java
// Sai nếu Authentication của endpoint đang là BearerTokenAuthentication.
Jwt jwt = (Jwt) authentication.getPrincipal();
~~~

Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal`, không phải `Jwt`. Nếu ứng dụng cần chạy cả hai dạng token, hãy chuẩn hóa actor bằng một adapter có kiểm soát thay vì ép kiểu trong mọi controller.

### 14.2. Cho rằng getName luôn là sub

`getName()` là giá trị do principal implementation chọn. Nó có thể dựa trên `sub` nhưng custom introspector có thể dùng tên khác. Nếu cần một ID bất biến, kiểm tra identity contract và dùng issuer/subject hoặc internal user ID được xác minh.

### 14.3. Nhầm attributes với GrantedAuthority

Có `"scope": "orders.read"` trong map **không tự tương đương** với `SCOPE_orders.read` ở `getAuthorities()` khi bạn dùng custom introspector không ánh xạ scope. Spring Security so khớp authorities đã có trong Authentication; không phải mọi biểu thức đều tự parse attributes.

### 14.4. Tự biến roles thành ROLE_ADMIN

Nếu introspection trả claim `roles` theo một schema riêng, không nên lấy mọi giá trị rồi thêm `ROLE_` mà không xem vai trò đó dành cho issuer/resource nào. Có thể vô tình nâng quyền do một vai trò ở hệ thống khác. Cần allowlist và ngữ nghĩa theo audience/tenant.

### 14.5. Coi active=true là toàn bộ authorization

`active: true` nghĩa token đang hoạt động theo phản hồi introspection. Nó **không bảo đảm** token thuộc đúng Orders API, có scope cần thiết, hoặc user sở hữu order. Kiểm tra audience, client, quyền nghiệp vụ và ranh giới tenant phải được thiết kế riêng theo hợp đồng.

### 14.6. Trộn scope với permissions của client khác

Trong OAuth 2.0, access token được cấp theo một tập quyền và đích sử dụng cụ thể. Nếu một issuer cung cấp nhiều nguồn role/permission, không được gộp một cách khiến client chỉ có scope đọc lại nhận quyền ghi hoặc quản trị vượt quá những gì được cấp.

### 14.7. Log getToken().getTokenValue()

`BearerTokenAuthentication.getToken()` chứa access token. **Không ghi token value vào log, gửi vào metrics labels hoặc trả lại qua API**. Khi debug, ưu tiên request ID, issuer đã được xác minh, tình trạng introspection, error category và thông tin danh tính đã được phép ghi.

### 14.8. Giả định introspection luôn nhanh và khả dụng

Với opaque token, Resource Server thường cần gọi network khi xác thực, nên độ trễ và độ sẵn sàng của Authorization Server là một phần của thiết kế. Có thể cân nhắc cache introspection theo chính sách, nhưng phải đánh đổi với yêu cầu thu hồi token nhanh; không được chấp nhận request chưa xác minh chỉ vì endpoint lỗi.

## 15. Mối liên hệ với OAuth 2.0 Client và OIDC

**OpaqueTokenIntrospector** là công cụ của **Resource Server** để kiểm tra access token. Nó khác:

- **OAuth 2.0 Client:** ứng dụng xin access token từ Authorization Server qua grant phù hợp và có thể dùng refresh token nếu được cấp.
- **OIDC Client:** kiểm tra **ID token** để thiết lập thông tin đăng nhập người dùng cho client.
- **Resource Server:** nhận **access token** được gửi đến API và quyết định truy cập tài nguyên.

Một **ID token** không tự biến thành access token hợp lệ cho API chỉ vì nó là JWT chứa `sub` hoặc `email`. Trong opaque token flow, dữ liệu từ introspection chỉ được coi là phù hợp khi token đúng mục đích/audience và policy API.

Đặc biệt, `OAuth2AuthenticatedPrincipal` **không đồng nghĩa** với một `OidcUser` trong OAuth2 Login. Chúng có thể cùng thuộc hệ thống principal của Spring Security nhưng dùng trong các ngữ cảnh khác nhau. Với servlet Resource Server opaque token, đối tượng authentication thông dụng là `BearerTokenAuthentication`.

## 16. Tóm tắt mô hình dữ liệu

~~~text
HTTP Authorization: Bearer <opaque-token>
                  |
                  v
       BearerTokenAuthenticationFilter
                  |
                  v
       OpaqueTokenAuthenticationProvider
                  |
                  v
            OpaqueTokenIntrospector
                  |
                  +----> Authorization Server introspection
                  |      active, sub, scope, client_id, aud, ...
                  v
       OAuth2AuthenticatedPrincipal
                  |
                  +-- attributes: Map<String, Object>
                  +-- name: String (implementation-defined)
                  +-- authorities: Collection<GrantedAuthority>
                  |
                  v
          BearerTokenAuthentication
                  |
                  v
              SecurityContext
                  |
                  v
       Endpoint / method authorization
                  |
                  v
      Tenant / ownership / business policy
~~~

| Câu hỏi | API hoặc khái niệm nên dùng |
| --- | --- |
| Metadata nào được introspection cung cấp? | `principal.getAttributes()` |
| Lấy riêng subject nếu có? | `principal.getAttribute("sub")`, kiểm tra kiểu và null |
| Spring Security gọi principal này là gì? | `principal.getName()` |
| Có scope/role/permission nào được dùng phân quyền? | `principal.getAuthorities()` hoặc `authentication.getAuthorities()` |
| Opaque Resource Server đặt authentication kiểu gì? | Thường `BearerTokenAuthentication` |
| Ai xây principal? | `OpaqueTokenIntrospector` sau khi token được xác minh |
| Muốn thêm authority từ claim riêng? | Introspector/converter tùy chỉnh với allowlist và schema rõ ràng |
| Ai xác minh access token còn active? | Introspection endpoint cùng logic introspector tin cậy |
| Ai cấp/refresh token? | Authorization Server theo luồng OAuth 2.0 của client |
| Ai kiểm tra chủ sở hữu và tenant? | Business policy của Resource Server |

**Điểm cần nhớ:** Trong opaque-token Resource Server, `OAuth2AuthenticatedPrincipal` là **cầu nối giữa kết quả introspection và cơ chế authorization của Spring Security**. `attributes` giữ metadata, `name` định danh principal theo implementation, còn `authorities` là dữ liệu thực sự được Spring Security so khớp khi kiểm tra quyền. Muốn bảo vệ API đúng, phải **xác minh token ở nguồn tin cậy**, **ánh xạ claims có chủ đích**, **không nhầm danh tính với quyền**, và tiếp tục kiểm tra quyền trên từng tài nguyên nghiệp vụ.
