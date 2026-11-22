# Quyền được chụp tại thời điểm phát token và thay đổi quyền sau đó

## 1. Vì sao JWT vẫn có quyền sau khi quản trị viên đã thu hồi role?

Trong hệ thống **Spring Security OAuth 2.0/OIDC Resource Server**, Authorization Server (AS) có thể phát hành một JWT access token chứa các quyền/scope đã được cấp tại thời điểm phát hành. Resource Server dùng chữ ký và các bộ kiểm tra token để xác thực token, sau đó ánh xạ scope thành **GrantedAuthority** của request.

Ví dụ JWT payload minh họa:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iat": 1910000000,
  "exp": 1910001200
}
~~~

Ở thời điểm token được cấp, người dùng còn quyền sửa đơn hàng. Sau đó quản trị viên thu hồi quyền sửa trong identity/authorization store. **JWT cũ không tự thay đổi**, vì nội dung của nó đã được ký. Nếu API chỉ kiểm tra signature, thời hạn và scope lấy từ token, token này có thể vẫn được chấp nhận cho thao tác sửa đến khi hết hạn hoặc bị cơ chế thu hồi bổ sung chặn.

Đây là sự khác biệt giữa hai thời điểm:

- **Issuance time:** Authorization Server quyết định có cấp token hay không và đưa claims nào vào token.
- **Request time:** Resource Server kiểm tra token và thực hiện chính sách truy cập tài nguyên ở thời điểm client gửi request.

**Điều cốt lõi:** một chữ ký JWT hợp lệ chứng minh token phù hợp với key của issuer được tin cậy và nội dung chưa bị thay đổi sau khi ký. Nó **không chứng minh** quyền hoặc membership trong các hệ thống bên ngoài JWT vẫn giữ nguyên đến hiện tại.

## 2. Cái gì thực sự là snapshot?

Khi phát hành JWT, Authorization Server có thể ghi các dữ liệu:

| Claim | Mục đích | Có tự làm mới sau phát hành không? |
|---|---|---|
| **iss** | Định danh bên phát hành | Không |
| **sub** | Định danh subject trong phạm vi issuer | Không |
| **aud** | Đối tượng nhận/resource được dự kiến | Không |
| **scope** hoặc **scp** | Các phạm vi quyền được cấp cho token | **Không** |
| **roles** hoặc **groups** | Vai trò hoặc nhóm nếu issuer có claim tùy biến | **Không** |
| **permissions** | Quyền chi tiết nếu issuer có claim tùy biến | **Không** |
| **tenant_id** | Ngữ cảnh tenant nếu profile có | Không |
| **iat** | Thời điểm token được phát hành | Không |
| **exp** | Mốc hết hạn của token | Không |
| **jti** | Định danh token, nếu có | Không |

Một JWT được ký là dữ liệu bất biến đối với client. Muốn thay đổi scope trong token, AS phải **phát hành một token mới**, hoặc API phải áp dụng thêm policy ngoài nội dung token.

Không phải mọi JWT access token đều có claim **roles**, **groups** hay **permissions**. Đây thường là các claim tùy biến. Scope có ý nghĩa OAuth 2.0 riêng: biểu diễn phạm vi quyền **được cấp cho access token/client** theo grant, không nhất thiết là danh sách toàn bộ vai trò của người dùng trong database.

### Scope, role và quyền thao tác một tài nguyên không giống nhau

Ví dụ người dùng có role quản trị đơn hàng trong hệ thống nội bộ nhưng client chỉ xin được scope đọc:

~~~text
Current user role:       ORDER_MANAGER
Allowed client grants:   orders.read, orders.write
Actual token scope:      orders.read
Specific order policy:   chỉ được sửa order thuộc tenant của user
~~~

Resource Server không được coi role, grant và scope là một giá trị duy nhất. Một token chỉ có **orders.read** không được quyền ghi chỉ vì database vừa cấp thêm role; ngược lại, token có **orders.write** cũng không nên vượt qua kiểm tra membership hiện hành nếu hệ thống yêu cầu thu hồi role có hiệu lực tức thời.

## 3. Timeline khi thu hồi quyền sau lúc token được cấp

Giả sử một timeline giả định theo giờ UTC:

| Thời điểm | Sự kiện | Tác động |
|---|---|---|
| 09:00 | AS cấp access token có **orders.read**, **orders.write**, hết hạn lúc 09:20 | JWT mang snapshot của grant tại 09:00 |
| 09:05 | Admin thu hồi quyền sửa đơn hàng của user | Kho quyền hiện hành không còn quyền write |
| 09:06 | Client gửi JWT cũ tới PUT /api/orders/42 | Token vẫn chứa scope write |
| 09:06 | API chỉ kiểm tra scope của JWT | Có thể cho phép, nếu token vẫn hợp lệ |
| 09:06 | API kiểm tra thêm membership/permission hiện hành | Có thể từ chối thao tác |
| 09:20 | JWT hết hạn | Decoder từ chối token theo thời hạn |
| Sau 09:20 | Client xin token mới | AS cần đánh giá lại quyền/grant theo chính sách hiện hành |

~~~mermaid
sequenceDiagram
    participant Admin
    participant AS as Authorization Server
    participant Client
    participant RS as Resource Server
    participant DB as Quyền hiện hành

    Client->>AS: Xin access token
    AS->>DB: Đọc role và grant
    DB-->>AS: orders.write được cấp
    AS-->>Client: JWT scope=orders.write, exp=T+20m
    Admin->>DB: Thu hồi quyền orders.write
    Note over Client,RS: JWT cũ đã ký vẫn giữ scope ban đầu
    Client->>RS: PUT /api/orders/42 cùng JWT cũ
    RS->>RS: Verify signature, iss, aud, exp
    RS->>RS: Tạo authority SCOPE_orders.write
    RS->>DB: Kiểm tra quyền hiện hành nếu policy yêu cầu
    DB-->>RS: Không còn quyền sửa
    RS-->>Client: Từ chối theo domain authorization
~~~

**Cửa sổ stale** là khoảng thời gian sau khi quyền bị thay đổi mà một hệ thống vẫn có thể chấp nhận quyết định quyền cũ. Với JWT scope-only, cửa sổ đó thường liên quan **thời hạn còn lại của token**, tolerance về đồng hồ và khả năng thu hồi bổ sung.

Lưu ý: AS cũng có thể cache role cũ và tiếp tục cấp token mới với scope cũ. Khi ấy chỉ giảm access-token lifetime **không đủ**. Hệ thống còn phải bảo đảm lần phát hành mới sử dụng trạng thái grant phù hợp.

## 4. Những gì Spring Security thực sự làm với JWT scopes

Trong Servlet Resource Server, các bước điển hình:

~~~text
HTTP Authorization: Bearer <JWT>
          |
          v
BearerTokenAuthenticationFilter
          |
          v
BearerTokenAuthenticationToken (chưa xác thực)
          |
          v
JwtAuthenticationProvider
          |
          v
JwtDecoder: kiểm tra signature + JWT validators
          |
          v
JwtAuthenticationConverter
          |
          v
JwtAuthenticationToken (đã xác thực)
  GrantedAuthority: SCOPE_orders.read
  GrantedAuthority: SCOPE_orders.write
          |
          v
AuthorizationFilter / method security
~~~

Mặc định phù hợp, **JwtGrantedAuthoritiesConverter** ánh xạ scope trong các claim như **scope** hoặc **scp** thành authority có tiền tố **SCOPE_**.

Ví dụ:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

thường tương ứng:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Với cấu hình:

~~~java
.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Spring Security kiểm tra authority được tạo từ **JWT đã xác thực của request**. Nó **không mặc nhiên gọi Authorization Server, database hay role service** để hỏi liệu quyền write vừa bị thu hồi hay chưa.

Một nhầm lẫn thường gặp là cho rằng mỗi request qua JwtDecoder sẽ tự đồng bộ toàn bộ quyền hiện tại. Trên thực tế, decoder xử lý **tính hợp lệ của credential** và validators đã cấu hình; việc đồng bộ current authorization phải có thiết kế riêng.

### Quy ước SCOPE_ khác ROLE_

- **hasAuthority("SCOPE_orders.write")** kiểm tra một authority được phát sinh từ OAuth scope.
- **hasRole("ADMIN")** thường sử dụng authority có tiền tố **ROLE_** theo convention Spring Security.
- Claim tùy biến **roles: ["ADMIN"]** không mặc nhiên được ánh xạ thành ROLE_ADMIN bởi converter scope mặc định.

Nếu provider có role claim riêng, có thể tùy biến **JwtAuthenticationConverter** để chuyển sang authorities sau khi token đã được xác minh. Nhưng **mapping nhiều role hơn từ JWT không làm role snapshot tự cập nhật**.

## 5. Cấu hình Resource Server xác thực token trước khi phân quyền

Ví dụ Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Security chain minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Cấu hình trên thể hiện **authorization dựa trên token scope**, không phải realtime entitlement lookup.

Để chấp nhận access token an toàn, Resource Server cần hợp đồng rõ:

1. Issuer được tin là ai?
2. JWT được xác minh bằng JWS algorithm và key source nào?
3. Token có còn hạn và đúng **audience** của API không?
4. Đó có thực sự là **access token**, không phải OIDC ID token hay JWT mục đích khác?
5. Scope/authority có phù hợp endpoint không?
6. Có cần **quyền hiện hành đối với resource cụ thể** không?

Chỉ đặt **issuer-uri** không mặc nhiên hoàn thành mọi audience hay token-purpose validation. Những quy tắc này có thể cấu hình trong **JwtDecoder** và các **OAuth2TokenValidator<Jwt>** phù hợp.

### Ví dụ thêm audience validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com/realms/shop";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Incorrect audience",
                                null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    defaults, audience));
    return decoder;
}
~~~

Ví dụ này minh họa tầng **authentication/token validation**. Khi dùng **setJwtValidator**, phải giữ các kiểm tra về issuer, thời gian và những điều kiện token profile cần thiết, bởi thao tác này thay bộ validators của decoder.

**Không nên đặt toàn bộ quyết định quyền nghiệp vụ vào JWT decoder.** Quyền sửa order phụ thuộc trạng thái và membership có thể thay đổi theo từng request; thường phù hợp hơn ở method/domain authorization. Chỉ đặt freshness/revocation check tại decoder khi đó là chính sách authentication rõ ràng được thiết kế và có nguồn trạng thái đáng tin.

## 6. Cách 1: kết hợp scope JWT với quyền hiện hành tại request time

Giải pháp cho hệ thống nhạy cảm với thay đổi quyền là để token scope làm **giới hạn trên** của grant, đồng thời kiểm tra quyền hiện hành:

~~~text
allow =
    token hợp lệ cho đúng API
    AND token có scope cần thiết
    AND principal còn quyền hiện hành
    AND principal có quyền trên resource cụ thể
~~~

Ví dụ user bị thu hồi role write:

~~~text
JWT cũ:
  scope = orders.read orders.write

Role store hiện tại:
  user không còn EDIT_ORDER

HTTP:
  PUT /api/orders/42

Kết luận:
  Chữ ký JWT có thể hợp lệ
  Token vẫn có SCOPE_orders.write
  Nhưng domain policy trả DENY
~~~

### Method security trong Spring Security

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Dùng kết hợp scope và policy bean:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderCommandService {

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') " +
        "and @orderPermission.canEdit(authentication, #orderId)")
    public void updateOrder(
            @P("orderId") String orderId,
            OrderPatch patch) {

        // Thực hiện update trong transaction/domain service.
        // OrderPatch là kiểu DTO của ứng dụng.
    }
}
~~~

Policy bean kiểm tra current entitlement:

~~~java
import java.net.URI;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderPermission")
public class OrderPermission {

    private final MembershipService membershipService;

    public OrderPermission(MembershipService membershipService) {
        this.membershipService = membershipService;
    }

    public boolean canEdit(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        URI issuer = jwt.getIssuer();
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            return false;
        }

        // MembershipService là component domain do ứng dụng định nghĩa.
        // Tìm principal bằng (issuer, subject), xét đúng order và tenant.
        return membershipService.hasCurrentEditPermission(
                issuer.toString(), subject, orderId);
    }
}
~~~

Hai đoạn Java trên chỉ minh họa extension point: **OrderPatch**, **MembershipService**, repository và transaction cần được triển khai theo domain thực tế.

Điều cần chú ý:

- Authentication phải do Resource Server xác thực, không lấy **sub** từ JWT chỉ decode Base64URL.
- Với multi-issuer, dùng **(iss, sub)** thay vì chỉ lấy username, email hoặc subject.
- Membership lookup phải ràng buộc vào **resource và tenant** liên quan, không chỉ role tổng quát.
- **@PreAuthorize** hoạt động khi đã bật method security và lời gọi đi qua Spring proxy. Khi dùng tham số trong SpEL, cần bảo đảm tên tham số truy cập được, ví dụ annotation **@P("orderId")** như trên.
- Không tự cho rằng kiểm tra quyền trước khi update sẽ loại bỏ mọi race. Với dữ liệu cạnh tranh, vẫn cần transaction, locking/version hoặc cách enforcement bảo đảm đúng tại thời điểm ghi.
- Nếu domain check dùng cache, revocation có hiệu lực theo **độ mới của cache**, không nhất thiết ngay tại lúc database cập nhật.

### Khi cấp thêm quyền thì sao?

JWT cũ không có **orders.write**, nhưng database vừa cấp quyền write. Biểu thức **scope AND current policy** vẫn từ chối token cũ vì thiếu scope. Client cần được cấp access token mới với grant phù hợp. Đây là hành vi có chủ đích của mô hình **token scope là upper bound**: việc cấp role mới không âm thầm nâng quyền một bearer credential đã phát hành trước đó.

Nếu yêu cầu sản phẩm là “quyền mới có hiệu lực ngay mà không cần token mới”, cần thiết kế authorization theo một contract khác, chẳng hạn token chỉ mang identity và một scope rất thô, trong khi quyết định action hoàn toàn phụ thuộc PDP hiện hành. Không tự bỏ qua scope mà không xem giới hạn grant do Authorization Server đặt ra.

## 7. Cách 2: access token JWT thời hạn ngắn

Một chiến lược đơn giản là giảm thời hạn của access token:

~~~text
Token lifetime = 5 phút
Admin thu hồi quyền sau khi token vừa được cấp

Nếu Resource Server chỉ dùng scope trong JWT:
  quyền cũ vẫn có thể được sử dụng
  trong phần thời gian còn lại của token
  (và các ảnh hưởng clock-skew/tolerance có liên quan)
~~~

**Short-lived JWT giới hạn cửa sổ stale chứ không tự làm quyền đổi ngay.**

Ưu điểm:

- Resource Server có thể xác minh JWT offline.
- Độ trễ xử lý thấp, ít phụ thuộc mạng.
- Token bị đánh cắp cũng có khoảng sử dụng ngắn hơn.

Đánh đổi:

- Client phải xin access token mới thường xuyên hơn.
- Authorization Server phải chịu tải refresh/cấp token.
- Thu hồi một quyền ngay lập tức không được bảo đảm.
- Nếu AS vẫn lấy role cũ từ cache hoặc giữ grant cũ trong refresh process, token mới có thể vẫn chứa scope không nên cấp.

### Refresh token không tự vô hiệu hóa access token cũ

Trong OAuth 2.0, **refresh token** được client gửi tới AS để xin access token mới; Resource Server không dùng refresh token để xác thực request nghiệp vụ.

Khi role bị thu hồi:

- AS có thể đánh giá lại scope/grant khi cấp access token mới.
- AS có thể hủy hoặc hạn chế refresh grant.
- Tuy nhiên, access token JWT đã phát hành vẫn có thể tiếp tục hợp lệ về mật mã cho đến **exp** hoặc đến khi Resource Server thực thi cơ chế từ chối bổ sung.

Đặc biệt, **logout**, **revoke refresh token** và **revoke mọi access token đã phát hành** không tự đồng nghĩa nhau.

## 8. Cách 3: opaque access token và introspection

Thay vì access token dạng JWT tự chứa claims, AS có thể cấp **opaque token**. Resource Server dùng **RFC 7662 Token Introspection** để hỏi endpoint đáng tin về trạng thái và metadata:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1910001200
}
~~~

Một cấu hình Spring Boot minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
~~~

Đây là kết nối introspection: Resource Server có thể hỏi AS về token qua một kênh đã được xác thực. Nhưng cần phân biệt ba mô hình AS có thể triển khai:

| Chính sách introspection của AS | Kết quả khi role bị thu hồi |
|---|---|
| Trả scope gắn với token tại issuance time | Scope cũ có thể vẫn xuất hiện dù **active=true** |
| Đánh dấu các access token liên quan **active=false** | API từ chối ở lần introspection mới |
| Tính lại quyền/metadata theo chính sách hiện hành | API có thể nhận được quyền mới nhất theo hợp đồng AS |

**Introspection không tự bảo đảm role luôn được tính lại.** Điều đó là trách nhiệm contract với Authorization Server. Nếu response có **active=true**, API vẫn phải kiểm tra audience, token type/purpose, scope và quyền nghiệp vụ.

### Cache introspection có thể làm stale

Nếu API cache response **active=true** trong 60 giây, AS đã revoke token nhưng API vẫn có thể nhìn kết quả cũ cho đến cache expiry hoặc invalidation. Vì vậy:

~~~text
Actual revocation delay
  = AS cập nhật token state
    + API/proxy introspection cache staleness
    + event/replication delay (nếu có)
~~~

Cần xác định max cache TTL, cơ chế invalidation và hành vi khi introspection endpoint không sẵn sàng. Đừng ghi “thu hồi ngay” trong yêu cầu hệ thống khi thực tế policy chấp nhận 60 giây stale.

## 9. Cách 4: access-token denylist theo jti

JWT có thể có **jti** để nhận diện một token:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": "orders-api",
  "jti": "token-93a6",
  "scope": "orders.read orders.write",
  "exp": 1910001200
}
~~~

Nếu cần thu hồi một token trước expiration, API có thể duy trì denylist:

~~~text
Key: (issuer, jti)
Value: revoked
Expiry: token exp + thời gian tolerance phù hợp
~~~

Khi request đến:

~~~mermaid
flowchart TD
    A["Request với JWT"] --> B["Xác minh chữ ký, issuer, audience, time"]
    B --> C{"JWT hợp lệ?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Tra denylist (iss, jti)"]
    D --> E{"Token bị thu hồi?"}
    E -- "Có" --> X
    E -- "Không" --> F["Xét scope + quyền domain"]
    F --> G{"Đủ quyền?"}
    G -- "Có" --> H["Cho phép"]
    G -- "Không" --> Y["Từ chối phân quyền"]
~~~

Cần thiết kế:

- AS có phát **jti** đủ riêng biệt theo issuer/token family không?
- Revocation áp dụng cho **một token**, **một session**, **một user** hay **toàn bộ client**?
- Mọi Resource Server có cùng dữ liệu denylist hoặc thấy sự kiện thu hồi đúng hạn không?
- Khi denylist store unavailable, có từ chối thao tác nhạy cảm hay không?
- Có cơ chế xóa entry sau khi token hết hạn không?
- Có tránh ghi raw access token trong storage/log không?

Denylist một **jti** không tự thu hồi mọi access token của người dùng. Nếu admin chỉ thay đổi một role, cần quyết định token nào bị ảnh hưởng hoặc dùng cơ chế cấp quyền hiện hành thay vì phải liệt kê mọi jti.

Điểm đánh đổi: dùng denylist tạo một **stateful validation dependency** ở Resource Server, dù JWT vẫn tự chứa và được ký.

## 10. Cách 5: authorization version và tokens-valid-after

Một cách giảm nhu cầu liệt kê từng token là AS ghi version của authorization policy/grant:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "authz_version": 17,
  "scope": "orders.write",
  "exp": 1910001200
}
~~~

Khi admin thu hồi quyền:

~~~text
authz_version trong JWT = 17
current version tại policy store = 18

=> token cũ không còn đáp ứng freshness policy.
~~~

**authz_version là claim tùy biến**, không phải trường bắt buộc của OAuth 2.0 hoặc JWT. Nó chỉ có ý nghĩa nếu AS và API cùng cam kết semantics.

Pseudocode:

~~~java
// PSEUDOCODE: chưa bao gồm tenant/grant key, null/type handling,
// caching, fail-closed và race-condition policy.
boolean currentVersionAllows(Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();
    Integer tokenVersion = jwt.getClaim("authz_version");
    Integer latest = versionStore.loadCurrent(issuer, subject);
    return tokenVersion != null && tokenVersion.equals(latest);
}
~~~

Cần xác định version theo **(issuer, subject)**, hoặc hẹp hơn theo tenant/client/grant nếu muốn thu hồi đúng phạm vi, và tăng version một cách nguyên tử khi policy đổi. Resource Server cần đọc latest version hoặc dùng cache có giới hạn stale.

Một biến thể khác là so sánh **iat** với thời điểm **permissionsChangedAt/tokensValidAfter** đáng tin. Biến thể này cần xử lý clock skew, độ phân giải timestamp, sự kiện đồng thời và replication. Bản thân **iat** không chứng minh token có quyền mới nhất; chỉ khi so với một mốc thay đổi policy hiện hành, nó mới có thể phục vụ freshness check.

## 11. Cách 6: policy decision point tại request time

Nếu nghiệp vụ có **RBAC, ABAC**, tenant, ownership, approval workflow hoặc trạng thái tài nguyên phức tạp, Resource Server có thể hỏi một **Policy Decision Point (PDP)** hay domain authorization service.

Input quyết định có thể gồm:

~~~text
Authenticated principal = (issuer, subject)
Client ID = shop-web
Token scopes = orders.write
Action = EDIT_ORDER
Resource ID = order-42
Tenant = tenant-blue
Current resource state = DRAFT
Context = giờ, channel, risk signal, ...
~~~

PDP trả:

~~~json
{
  "allow": false,
  "reason": "membership_revoked"
}
~~~

Điều kiện:

1. JWT phải được xác thực trước khi đưa principal/claims tới PDP.
2. PDP phải tra **nguồn quyền đáng tin** và được bảo vệ giữa các service.
3. Cache decision cần key đủ chặt theo principal, action, resource, tenant và các yếu tố policy quan trọng.
4. Cần timeout và failure mode (thường **fail-closed** cho thao tác nhạy cảm).
5. Nếu response **allow** được cache, quyền vẫn có thể stale đến khi TTL hết hoặc cache bị invalidated.

Trong Spring Security, có thể tích hợp ở **AuthorizationManager**, method-security expressions hoặc service/domain policy. Không cần một JWT servlet filter tự viết chạy song song với Resource Server để làm việc này.

## 12. Cache và độ trễ thu hồi quyền

Ngay cả khi domain authorization có truy vấn quyền hiện hành, nhiều tầng có thể cache:

- Access token tự chứa claims.
- Cached introspection response.
- Membership cache trong Resource Server.
- JWT/session state ở gateway.
- Authorization policy decision cache.
- Cache từ identity broker/AS.
- Event-driven replicas của permission store.

Ví dụ:

~~~text
09:05:00 Admin thu hồi role.
09:05:01 Primary DB đã cập nhật.
09:05:03 Authorization event đang đến các replicas.
09:05:30 API cache allow-decision hết hạn.
09:05:31 Request mới bắt đầu bị chặn.
~~~

Độ trễ hiệu lực thu hồi trong ví dụ là **hàng chục giây**, không phải ngay tại lúc DB commit.

Nếu tổ chức yêu cầu “quyền bị thu hồi trong tối đa 10 giây”, cần xác định cơ chế duy trì guarantee đó, thay vì chỉ mô tả “API có cache quyền”.

### Cache key đúng phạm vi

Cần tránh cache:

~~~text
key = user-42
value = allow
~~~

nếu thực tế quyết định phụ thuộc action, tenant, resource, client hay scope.

Một key hợp lý hơn có thể gồm:

~~~text
issuer + subject + tenant + action + resource + policy_version
~~~

Nhưng key càng chi tiết càng tốn dung lượng; phải cân bằng với risk policy và quy mô hệ thống. Nếu muốn tránh stale permission, có thể không cache **allow** cho thao tác nhạy cảm hoặc dùng TTL rất ngắn.

### Event-driven invalidation

Một authorization store có thể phát sự kiện:

~~~json
{
  "type": "PermissionChanged",
  "issuer": "https://auth.example.com",
  "subject": "user-42",
  "tenant": "tenant-blue",
  "authzVersion": 18
}
~~~

Các API invalid cache khi nhận sự kiện. Tuy nhiên events có thể đến muộn, xử lý lặp hoặc đảo thứ tự. Cần version/sequence, reconciliation và xử lý sự kiện bị bỏ lỡ. Không coi publish event thành công là đồng nghĩa mọi API đã ngừng tin quyết định cũ.

## 13. Quyền mới được cấp sau khi token phát hành

Quyền mới cũng chịu hiệu ứng snapshot.

~~~text
10:00 Token phát hành với scope = orders.read
10:05 Admin cấp quyền orders.write
10:06 Client gọi PUT /api/orders/42 bằng JWT cũ
~~~

Nếu API yêu cầu **SCOPE_orders.write**, token cũ vẫn thiếu scope này. Domain store có thể đã cấp role write, nhưng scope trong token chưa tăng.

Với policy:

~~~text
allow = token_scope_has_write AND current_permission_has_write
~~~

kết quả vẫn là **deny**. Client cần lấy **access token mới** với grant write được AS cho phép.

Tuy nhiên “được cấp role mới” không đồng nghĩa AS sẽ tự thêm scope mới: còn phụ thuộc **client permissions**, **user consent**, **grant policy**, **audience** và việc AS đã nhận role update hay chưa.

Cần phân biệt:

- **Role hiện tại của user/client.**
- **Scope client được phép yêu cầu.**
- **Scope đã được AS cấp cho access token cụ thể.**
- **Quyền hành động tại Resource Server.**

Nếu muốn quyền mới có hiệu lực mà không cấp token mới, phải thiết kế policy riêng cho phép quyết định động trong giới hạn grant; không tùy tiện bỏ qua phạm vi mà token được cấp.

## 14. User token và client-credentials token

Access token không phải lúc nào cũng đại diện người dùng cuối. Với **client_credentials**, token có thể đại diện cho một service:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "inventory-sync",
  "client_id": "inventory-sync",
  "aud": "orders-api",
  "scope": "orders.sync",
  "exp": 1910001200
}
~~~

Khi admin thu hồi quyền của service **inventory-sync**, token JWT cũ vẫn có thể mang **orders.sync** cho tới khi nó không còn được chấp nhận.

Một số quyết định:

- Principal type: user, service hay delegation?
- Có cần kiểm tra trạng thái client hiện hành không?
- Client secret/credential bị thu hồi có đồng thời làm access token cũ inactive không?
- Scope trong service token được phép dùng endpoint nào?
- Nếu service bị disable thì kiểm tra bằng introspection/version/PDP hay TTL ngắn?

Không dùng **sub** như một user ID mặc định; subject cần được diễn giải theo issuer và token profile.

**DPoP** hoặc **mTLS sender-constrained token** giúp hạn chế sử dụng token bởi bên không sở hữu khóa ràng buộc. Nhưng proof-of-possession **không làm role claim tự cập nhật** sau khi bị thu hồi.

## 15. Multi-tenant và object-level authorization

Một JWT có thể ghi:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-blue",
  "roles": ["ORDER_MANAGER"]
}
~~~

Nếu user bị xóa khỏi **tenant-blue** sau khi token được phát hành, claim tenant/role vẫn có thể mang giá trị cũ.

Resource Server cần kiểm tra:

1. Token hợp lệ và dành cho **orders-api**.
2. Có **orders.write** đối với endpoint sửa.
3. **(iss, sub)** ánh xạ đến local principal nào?
4. Principal còn membership trong tenant hiện hành không?
5. Order thực sự thuộc tenant nào, ai là owner và trạng thái có cho phép sửa không?
6. Permission check và thao tác ghi có nằm trong boundary bảo đảm tính nhất quán phù hợp không?

Không được chỉ nhìn **tenant_id** trong JWT để suy ra user có quyền sửa mọi order trong tenant đó. Tenant claim và permission có thể phản ánh trạng thái khi phát token, còn tài nguyên đã thay đổi sau đó.

## 16. Logout, khóa tài khoản và đổi mật khẩu

Nhiều sự kiện quản trị có liên quan nhưng tác động đến access token khác nhau:

| Sự kiện | Tác động trực tiếp | JWT access token đã cấp có tự mất hiệu lực? |
|---|---|---|
| User logout khỏi browser/app | Session/client state thay đổi | **Không mặc định** |
| Refresh token bị revoke | Ngăn hoặc giới hạn việc xin access token mới | **Không mặc định** |
| User bị disable | Trạng thái account thay đổi | Không, nếu API chỉ verify JWT offline |
| User đổi password | Credential đăng nhập thay đổi | Không mặc định |
| Admin thu hồi role | Authorization store thay đổi | Không mặc định |
| Access token hết hạn theo **exp** | JWT không còn hợp lệ về thời gian | Có, khi decoder kiểm tra thời hạn |
| Token **jti** nằm trong denylist | API có thêm chính sách từ chối | Có, nếu check được áp dụng nhất quán |
| Introspection trả **active=false** | AS xem token không còn active | Có, khi API dùng kết quả mới và không chấp nhận cache cũ |
| Current permission bị thu hồi | Domain policy trả deny | Từ chối thao tác theo policy động |

Vì thế, nếu yêu cầu là “khóa tài khoản ngay lập tức ngăn mọi thao tác quản trị”, cần thiết kế rõ **account-state check**, **revocation** hoặc **version freshness**, không chỉ gửi logout event và chờ access token tự thay đổi.

### Key rotation không phải cách thu hồi một role

Thay signing key hoặc xóa public JWK khỏi JWKS có thể ảnh hưởng **rất nhiều token** cùng dùng một khóa. Đây không phải cơ chế thích hợp để thu hồi một role của một user bình thường.

**Key rotation** thuộc vòng đời khóa mật mã. **Token revocation/current entitlement** thuộc vòng đời quyền và phiên/grant. Hai bài toán phải được tách biệt. Trường hợp private signing key bị lộ cần xử lý khẩn cấp riêng.

## 17. Authentication failure hay authorization failure?

Khi token không còn được chấp nhận, Response của Resource Server thường là lỗi **authentication**; khi token hợp lệ nhưng thiếu quyền, thường là lỗi **authorization**:

| Tình huống | Điểm từ chối | HTTP điển hình |
|---|---|---|
| Thiếu Bearer credential ở endpoint cần xác thực | Authentication entry point | 401 |
| JWT hết hạn hoặc signature sai | JwtDecoder | 401, thường **invalid_token** |
| JWT sai issuer/audience/token purpose | Jwt validators | 401 |
| JWT nằm trong denylist, được xem là token bị thu hồi | Token acceptance policy | Thường 401 |
| JWT hợp lệ nhưng thiếu **orders.write** | Authorization | Thường 403, có thể **insufficient_scope** |
| JWT có scope nhưng không còn membership tenant | Domain authorization | Thường 403, tùy policy |
| User bị disable, kiểm tra ở authentication | Token/account policy | Thường 401 |
| User bị disable, kiểm tra ở domain authorization | Domain policy | Thường 403 |

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

và:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Response chính xác phụ thuộc **BearerTokenAuthenticationEntryPoint**, **BearerTokenAccessDeniedHandler** và các handler do ứng dụng cấu hình. Không nên trả về nội dung JWT, raw Authorization header hoặc chi tiết bí mật của role database trong body lỗi.

## 18. Chọn giải pháp theo yêu cầu về độ mới quyền

| Thiết kế | Cửa sổ quyền cũ | Chi phí / phụ thuộc | Trường hợp có thể phù hợp |
|---|---|---|---|
| JWT scope + TTL tương đối dài | Có thể đến expiry | Thấp, xác minh offline | Quyền ít thay đổi, tác động thấp |
| JWT TTL ngắn + AS tính lại quyền khi refresh | Giới hạn bởi TTL, clock skew và độ mới AS | Nhiều lần xin token | Giới hạn stale mà không tra DB mỗi request |
| JWT scope + live domain authorization | Theo độ mới store/cache permission | DB/PDP lookup | Tenant, ownership, role thay đổi thường xuyên |
| JWT + denylist **(iss, jti)** | Theo độ trễ ghi/đọc denylist | Shared store và invalidation | Revoke access token cụ thể |
| JWT + authorization version | Theo độ mới version lookup | Shared version store | Invalidate nhóm token theo subject/grant/tenant |
| Opaque + introspection | Theo AS semantics và cache TTL | Network/cache phụ thuộc AS | Cần token status tập trung |
| Policy Decision Point ở request time | Theo freshness store/decision cache | Phụ thuộc PDP | Authorization phức tạp, cần hiệu lực nhanh |

Ví dụ lựa chọn theo tính chất nghiệp vụ:

- **Đọc danh mục sản phẩm:** JWT scope và token lifetime có thể đủ.
- **Đọc dữ liệu đơn hàng:** thêm kiểm tra ownership/tenant.
- **Chỉnh sửa đơn hàng:** thêm kiểm tra current membership và trạng thái order.
- **Phê duyệt giao dịch quan trọng:** có thể cần current authorization, token freshness và kiểm tra ngữ cảnh bổ sung.
- **Khóa tài khoản khẩn cấp:** yêu cầu SLA revocation rõ ràng, không chỉ chờ JWT hết hạn.

Không có một lifetime hoặc TTL tối ưu cho mọi ứng dụng; cần chọn theo risk model, SLA thu hồi và khả năng hạ tầng.

## 19. Thiết kế kiểm thử: phân biệt token snapshot và quyền hiện hành

Những tình huống cần mô tả rõ khi xây chính sách (đây **không phải kết quả test đã chạy**):

| Input / hành động | Kỳ vọng nếu chỉ dựa vào JWT scope | Kỳ vọng nếu thêm quyền hiện hành |
|---|---|---|
| JWT còn hạn, có write, membership còn write | Có thể cho phép | Cho phép nếu đúng resource |
| JWT còn hạn, có write, membership vừa bị thu hồi | **Có thể vẫn cho phép** | Từ chối |
| JWT còn hạn, chỉ có read, user vừa được cấp write | Từ chối PUT | Vẫn từ chối nếu yêu cầu token có scope write |
| JWT hết hạn nhưng membership còn write | Từ chối | Từ chối |
| JWT sai audience nhưng role đúng | Phải từ chối khi có audience validation | Phải từ chối |
| ID token cùng issuer, có role admin | Không được nhận làm access token | Không được nhận |
| JWT có write, order chuyển trạng thái LOCKED | Có thể không biết nếu chỉ xét scope | Từ chối theo domain rule |
| JWT có write, jti mới bị revoke | Cần check revocation bổ sung | Từ chối nếu token policy có denylist |
| Opaque active=true nhưng role bị thu hồi | Phụ thuộc AS introspection contract | Từ chối nếu current policy chặn |
| Two tenants cùng subject string ở hai issuer | Nguy cơ nhầm nếu tra sub đơn lẻ | Phân biệt principal bằng (iss, sub) |
| Multiple API instances cache quyền khác nhau | Có thể thấy hành vi không nhất quán | Cần bounded staleness/invalidation |

Khi thiết kế integration tests, phải phân biệt test **authorization mock** với test **JWT decoder và Resource Server filter** thật. Spring Security Test có post-processor tạo JWT authentication giả để test quyền, nhưng đó không tự chứng minh issuer, chữ ký hoặc audience validation ở production.

Trong STEP 4, mục này chỉ mô tả tình huống và trách nhiệm; không thực thi bộ kiểm thử hay đánh giá nội dung.

## 20. Chẩn đoán sự cố “thu hồi quyền rồi mà API vẫn cho phép”

Một luồng điều tra:

~~~text
[1] JWT được phát hành trước hay sau lúc thu hồi?
            |
            v
[2] JWT còn hạn và có scope nào?
            |
            v
[3] API có thực sự kiểm tra audience, issuer, token type?
            |
            v
[4] JwtAuthenticationToken có authorities gì?
            |
            v
[5] Endpoint chỉ hasAuthority hay còn domain policy?
            |
            v
[6] Domain policy đang tra quyền từ source nào?
            |
            v
[7] Có cache / stale replica / event delivery delay?
            |
            v
[8] Nếu token mới vẫn có quyền cũ, AS đang dùng grant nào?
            |
            v
[9] Revocation/denylist/version check có được thực thi?
~~~

Một số triệu chứng:

| Triệu chứng | Gợi ý nguyên nhân |
|---|---|
| Access token cũ vẫn có **SCOPE_orders.write** | Scope snapshot trong JWT |
| Token mới vẫn được cấp scope write sau khi role bị revoke | AS giữ grant cũ, cache role cũ hoặc chưa đồng bộ policy |
| API A từ chối, API B vẫn cho phép | Authorization contract hoặc cache khác nhau |
| Introspection trả inactive nhưng API vẫn cho phép | Cache hoặc request path không sử dụng introspection |
| Domain policy đã viết nhưng vẫn sửa được | Method security không chạy, self-invocation, sai resource/tenant, race |
| Vừa cấp thêm role nhưng JWT cũ vẫn 403 | Token chưa có scope mới |
| Thu hồi role chỉ có hiệu lực sau 30 giây | Cache TTL, replicas hoặc event delay |
| Logout xong access token cũ vẫn hoạt động | Chưa có access-token revocation policy |

Nên ghi **request ID, mã lỗi, issuer được cấu hình, policy name và decision reason đã chuẩn hóa**. Không log nguyên Bearer token, JWT signature, Authorization header, refresh token hoặc secret từ introspection.

## 21. Những hiểu lầm và anti-pattern cần tránh

| Hiểu lầm / cách làm sai | Vấn đề | Hướng thiết kế |
|---|---|---|
| “JWT còn hạn thì role còn hiệu lực.” | JWT không kết nối sống tới role store | TTL/revocation/current policy |
| “JwtDecoder sẽ tự cập nhật quyền từ AS.” | Decoder mặc định xác minh token/validators | Xây current entitlement policy riêng |
| “hasAuthority là live role lookup.” | Nó đọc authorities của Authentication | Thêm method/domain authorization nếu cần |
| “Revoke refresh token là đủ để chặn access token cũ.” | Access token JWT cũ vẫn có thể hợp lệ | Xác định chính sách revoke access token |
| “Opaque introspection luôn cập nhật scope.” | Phụ thuộc AS semantics/caching | Hợp đồng AS rõ và bounded cache |
| “Khi cấp role mới, token cũ phải tự có scope mới.” | Token đã ký, scope không tự thay | Xin token mới hoặc thiết kế dynamic policy |
| “Có tenant_id trong JWT tức là có quyền với mọi order trong tenant.” | Membership/resource state có thể khác | Object-level authorization |
| “User bị disable nghĩa là JWT signature sai.” | Signature và account state là hai vấn đề | Token/account freshness checks |
| “Thu hồi role thì rotate signing key.” | Ảnh hưởng các user/token khác | Denylist/version/permission policy |
| “Dùng JWT filter riêng để tải role mỗi request.” | Chồng chéo Resource Server authentication | Giữ JWT authentication chuẩn, kiểm tra dynamic authorization ở đúng layer |
| “Chỉ cần một cache allow-key theo user.” | Kết quả quyền phụ thuộc action/resource/tenant | Key cache theo policy context |
| “Nếu permission DB lỗi thì cứ cho phép.” | Có thể biến outage thành bypass quyền | Fail-closed cho thao tác nhạy cảm |
| “DPoP giải quyết scope cũ.” | Sender binding không cập nhật quyền | Kết hợp với revocation/current authorization |
| “Chỉ kiểm tra sub, không cần issuer.” | Subject có phạm vi issuer | Dùng (iss, sub) đã xác thực |

## 22. Hợp đồng phối hợp giữa Authorization Server và Resource Server

Một thiết kế đáng tin phải thống nhất **ngữ nghĩa quyền**, không chỉ trường tên **scope**.

**Authorization Server cần công bố/quy định:**

1. Dựa trên role/grant nào để cấp scope?
2. Có phát JWT hay opaque access token?
3. Thời hạn token và clock skew contract?
4. Khi quyền thay đổi, access token cũ bị revoke/inactive hay giữ nguyên?
5. Có làm mới grant khi cấp token qua refresh không?
6. Có hỗ trợ **jti**, revoke token, version claim hoặc introspection không?
7. Introspection **active** và scope phản ánh trạng thái phát hành hay quyền hiện tại?
8. Có cache/replication delay tối đa được cam kết không?

**Resource Server cần quy định:**

1. Issuer/JWKS/introspection nào được tin cậy?
2. Audience, thuật toán và access-token profile nào được chấp nhận?
3. Scope được chuyển thành authorities thế nào?
4. Endpoint nào có thể dựa vào token scope snapshot?
5. Endpoint nào bắt buộc kiểm tra membership/resource hiện hành?
6. SLA thu hồi quyền và TTL của cache là bao nhiêu?
7. Khi revocation/PDP/DB unavailable thì xử lý thế nào?
8. Authentication error khác authorization error như thế nào?
9. Các audit log có bảo vệ dữ liệu nhận dạng/token không?
10. Có thống nhất behavior khi cấp **thêm** quyền sau khi token được phát hành không?

**SLA rõ ràng** giúp chọn kiến trúc: “role bị thu hồi sẽ chặn thao tác sửa đơn hàng trong tối đa 15 giây” là một yêu cầu kỹ thuật có thể triển khai/đánh giá; câu “quyền sẽ tự cập nhật” là không đủ cụ thể.

## 23. Nguyên tắc ghi nhớ

~~~text
T_issue:
  Authorization Server phát JWT
  Scope/roles ghi trong JWT = dữ liệu tại thời điểm phát hành

T_request:
  Resource Server nhận JWT
  Scope/roles trong JWT không tự thay đổi

Snapshot-only policy:
  allow = valid_token
          AND token_scope
          AND endpoint_rule

Hybrid current-state policy:
  allow = valid_token
          AND token_scope
          AND current_entitlement
          AND resource_policy
~~~

Các nguyên tắc trọng tâm:

1. **Quyền/scope trong JWT là snapshot của lần cấp token.** Role database có thể thay đổi sau đó.
2. **Quyền bị thu hồi không tự biến mất khỏi JWT cũ.** Token phải hết hạn hoặc bị từ chối bởi một cơ chế bổ sung.
3. **JwtAuthenticationConverter không tự tìm quyền mới.** Nó chuyển claims đã được xác thực thành authorities của request.
4. **Cấp thêm quyền cũng không tự thêm scope vào JWT cũ.** Token mới phải được cấp đúng grant, hoặc hệ thống phải có contract dynamic authorization khác.
5. **JWT lifetime ngắn giảm stale window**, nhưng không bảo đảm revocation tức thời và không sửa AS nếu tiếp tục cấp token sai.
6. **Opaque introspection, denylist, versioning và domain/PDP lookup** đều có ưu/nhược điểm; phải mô tả semantics và cache.
7. **Authentication và authorization là hai quyết định riêng.** Một token có chữ ký đúng và còn hạn vẫn có thể bị từ chối do quyền hiện tại.
8. **Principal, tenant và object ownership cần được kiểm tra đúng phạm vi**; không dựa mỗi sub/role claim.
9. **Hiệu lực thu hồi có SLA** cần được xây bằng cơ chế đo được, không phải bằng kỳ vọng token tự đồng bộ.
10. **Giữ Resource Server làm đường xác thực chính**, đặt policy quyền động tại extension point phù hợp thay vì viết một JWT filter song song.

**Kết luận:** nếu sản phẩm chấp nhận quyền cũ còn hiệu lực trong cửa sổ xác định, JWT scope + lifetime phù hợp có thể là một lựa chọn hiệu quả. Nếu việc thu hồi role cần tác động ngay hoặc gần ngay, Resource Server phải có nguồn trạng thái đáng tin ở request time hoặc cơ chế thu hồi token đã phát hành. Bản thân JWT không thể tự phản ánh một thay đổi quyền xảy ra **sau thời điểm nó được ký**.

## 24. Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access token, scope, refresh token và grant. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** cách dùng Bearer token, invalid_token và insufficient_scope. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** các claim iat, exp, iss, sub, jti. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** active và metadata access token. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7009 — OAuth 2.0 Token Revocation:** cơ chế thu hồi token theo giao thức. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 8725 — JWT Best Current Practices:** kiểm tra issuer, audience và tránh nhầm loại token. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** yêu cầu với JWT access token. https://www.rfc-editor.org/rfc/rfc9068
- **Spring Security — OAuth 2.0 Resource Server JWT:** signature, issuer và ánh xạ scope thành authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Opaque Token Resource Server:** introspection và xác thực opaque access token. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security — Method Security:** EnableMethodSecurity và PreAuthorize. https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
