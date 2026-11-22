# Bọc OpaqueTokenIntrospector để thêm kiểm tra theo hợp đồng

Trong **Spring Security OAuth 2.0/OIDC Resource Server** ở Servlet stack, access token có thể là một chuỗi **opaque**: Resource Server không tự xác minh chữ ký JWT từ chuỗi token, mà gọi **OAuth 2.0 Token Introspection Endpoint** của Authorization Server để biết token có đang hoạt động và có những thuộc tính nào. Spring Security biểu diễn thao tác đó qua interface **`OpaqueTokenIntrospector`**.

Tuy nhiên, một kết quả introspection thành công với `active=true` **chưa tự bảo đảm token phù hợp với mọi API**. Cùng một Authorization Server có thể cấp token cho Orders API, Payments API, nhiều OAuth clients hoặc nhiều tenants. Orders API có thể cần thêm những yêu cầu theo hợp đồng:

- Token phải **dành cho Orders API**, chẳng hạn claim `aud` có `orders-api`.
- Nếu introspection response công bố `iss`, issuer phải đúng giá trị được thỏa thuận với API.
- Chỉ các OAuth clients nằm trong danh sách được duyệt mới có quyền gọi loại API này.
- Token phải có tenant phù hợp; claim `tenant_id` không được trống hoặc sai kiểu.
- Nếu hợp đồng bắt buộc thời điểm hết hạn, token phải có `exp` hợp lệ.
- Một số claims hoặc scopes phải có **cấu trúc và ngữ nghĩa đúng**, trước khi được ánh xạ thành principal/authorities.

Cách mở rộng phù hợp là **bọc (decorate) một `OpaqueTokenIntrospector` đáng tin**: gọi delegate để thực hiện introspection chuẩn, sau đó chỉ trả về `OAuth2AuthenticatedPrincipal` khi các điều kiện bổ sung đều đạt. Nếu không đạt, wrapper ném exception phù hợp và **không tạo principal đáng tin cho request**.

Bài này tập trung vào thiết kế wrapper, cấu hình bean với Spring Security, kiểm tra cấu trúc claims, xử lý lỗi *fail closed*, giữ nguyên authorities và nguyên tắc không nhầm token validation với authorization nghiệp vụ.

> **Thông điệp cốt lõi:** Introspection xác nhận trạng thái token theo Authorization Server. Wrapper xác nhận token đáp ứng **hợp đồng của Resource Server này**. Sau đó, HTTP/method authorization vẫn phải quyết định **caller được làm gì với tài nguyên nào**.

## 1. Vì sao Resource Server cần introspection?

Với JWT tự chứa, Resource Server có thể dùng `JwtDecoder` và public key/JWKS để xác minh token cục bộ. Với opaque token, chuỗi token không có cấu trúc claims mà Resource Server được phép suy luận độc lập.

Ví dụ bearer request:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 5m7y1rs9H9yT0vDb4cWkNQ
```

Chuỗi sau `Bearer` là một **credential**. Resource Server không thể nhìn chuỗi đó rồi tự biết user, scopes, tenant hay thời gian hết hạn. Nó có thể gọi introspection endpoint của Authorization Server qua kết nối và thông tin xác thực đã được cấu hình.

Ví dụ HTTP introspection theo RFC 7662 ở mức minh họa:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <INTROSPECTION_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
```

Đối với một token active, phản hồi *có thể* trông như sau:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iss": "https://login.example.test/realms/shop",
  "tenant_id": "shop-a",
  "iat": 1794715200,
  "exp": 1794718800
}
```

Với token inactive, RFC 7662 cho phép phản hồi tối giản:

```json
{
  "active": false
}
```

**Không phải mọi Authorization Server đều trả đủ toàn bộ claims trong ví dụ active.** Trừ `active`, các thành phần khác phụ thuộc khả năng introspection, loại token, quyền của caller và hợp đồng triển khai. Nếu Orders API đòi `aud`/`tenant_id` thì Authorization Server phải được cấu hình cung cấp chúng một cách nhất quán; không được giả định RFC 7662 buộc mọi AS phải phát hành các claims đó.

### 1.1. Introspection response khác JWT payload

Trong nhánh opaque, những thuộc tính mà `OpaqueTokenIntrospector` nhận được là **dữ liệu từ introspection response của AS đáng tin**, không phải payload JWT mà API tự parse.

Một token có thể trông giống JWT (ba phần ngăn bởi dấu chấm) nhưng hệ thống vẫn chọn **introspection** vì policy yêu cầu xác thực trạng thái online. Khi ấy chỉ nhìn hình thức token không đủ để quyết định có được bypass introspection hay không.

### 1.2. Tại sao `active=true` chưa đủ?

Giả sử AS cấp token active cho Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read",
  "client_id": "shop-web"
}
```

Nếu Orders API chỉ chấp nhận mọi token active cùng issuer, nó có thể nhận sai token của tài nguyên khác. Một wrapper có thể đòi `aud` chứa `orders-api` để tránh *token substitution* giữa các Resource Servers.

Đây là ví dụ **kiểm tra hợp đồng**; ngoài audience, API có thể yêu cầu một client allowlist, tenant hoặc token type, tùy AS cam kết trả về gì.

## 2. Vị trí của wrapper trong Servlet filter chain

Sơ đồ luồng xử lý:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer opaque token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken chưa xác thực"]
    C --> D["OpaqueTokenAuthenticationProvider"]
    D --> E["ContractCheckingOpaqueTokenIntrospector"]
    E --> F["Delegate: Nimbus/Spring OpaqueTokenIntrospector"]
    F --> G["Authorization Server introspection endpoint"]
    G --> H{"Token active và introspection hợp lệ?"}
    H -- "Không" --> X["Xác thực thất bại"]
    H -- "Có" --> I["OAuth2AuthenticatedPrincipal từ delegate"]
    I --> J{"Kiểm tra aud/iss/client_id/tenant/exp ..."}
    J -- "Không" --> X
    J -- "Có" --> K["Trả lại principal hợp lệ theo contract"]
    K --> L["BearerTokenAuthentication + authorities"]
    L --> M["SecurityContext / AuthorizationFilter"]
    M --> N{"Scope và quyền endpoint đủ?"}
    N -- "Không" --> O["Thường 403"]
    N -- "Có" --> P["Controller / service: quyền trên bản ghi"]
    X --> Q["Thường 401 hoặc lỗi phù hợp theo exception flow"]
```

Điểm quan trọng trong chuỗi này:

1. `BearerTokenAuthenticationFilter` lấy chuỗi bearer token theo cấu hình của Spring Security.
2. `OpaqueTokenAuthenticationProvider` nhờ `OpaqueTokenIntrospector` xác minh token.
3. Delegate introspector gọi Authorization Server, xử lý trạng thái `active`, trả `OAuth2AuthenticatedPrincipal` hoặc ném exception.
4. Wrapper kiểm tra thêm các thuộc tính **đã được delegate nhận từ nguồn tin cậy**.
5. Nếu wrapper trả principal, Spring Security mới xây dựng `BearerTokenAuthentication` và các authorities để dùng tiếp.
6. `AuthorizationFilter`/method security quyết định route, scope và quyền dữ liệu.

Wrapper nằm ở **ranh giới authentication/token validation**. Nó không nên thay thế những chính sách yêu cầu HTTP path, order ID hoặc trạng thái một bản ghi cụ thể.

## 3. Hợp đồng của `OpaqueTokenIntrospector`

Spring Security sử dụng interface có ý tưởng như sau:

```java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

Tham số `token` là chuỗi bearer credential. Kết quả trả về là `OAuth2AuthenticatedPrincipal`, chứa những thông tin Spring Security sẽ tin sau khi introspection thành công.

Các API cần biết:

| Thành phần | Chức năng |
|---|---|
| `OpaqueTokenIntrospector` | Xác thực token và trả principal khi token được chấp nhận |
| `OAuth2AuthenticatedPrincipal` | Truy cập tên principal, attributes và `GrantedAuthority` |
| `OpaqueTokenAuthenticationProvider` | Dùng introspector để xác thực `BearerTokenAuthenticationToken` |
| `BearerTokenAuthentication` | Authentication được dựng từ opaque token đã chấp nhận |
| `BadOpaqueTokenException` | Báo token không hợp lệ/chưa đáp ứng điều kiện xác thực |
| `OAuth2IntrospectionException` | Biểu diễn lỗi trong quá trình introspection, tùy nguyên nhân |
| `DefaultOAuth2AuthenticatedPrincipal` | Implementation có thể dùng khi cần dựng principal mới với attributes/authorities được kiểm soát |

Tên implementation delegate phụ thuộc phiên bản thư viện. Nhiều dự án Spring Security 5.x/6.x sử dụng `NimbusOpaqueTokenIntrospector`. Các phiên bản mới hơn có thể cung cấp API builder/implementation khác như `SpringOpaqueTokenIntrospector`. **Chính interface `OpaqueTokenIntrospector` là điểm mở rộng ổn định cần thiết cho wrapper**; mã tạo delegate cần đối chiếu phiên bản đang dùng.

### 3.1. Wrapper theo nguyên tắc decorator

Thay vì tự viết HTTP request, parse JSON, Basic authentication và kiểm tra `active` từ đầu, wrapper **ủy quyền cho delegate**:

```java
public final class DelegatingExampleIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public DelegatingExampleIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        // Kiểm tra bổ sung theo hợp đồng ở đây.
        return principal;
    }
}
```

Wrapper ở ví dụ trên chưa thêm policy, nhưng thể hiện đúng thiết kế:

- Giữ delegate làm nguồn kiểm tra token.
- Không giả tạo `active=true`.
- Không trả principal khi delegate đã ném lỗi.
- Không tự đổi quyền chỉ để request được phép đi qua.

## 4. Xác định hợp đồng introspection của Orders API trước khi viết code

Giả sử Orders API và Authorization Server đã thống nhất:

```text
Trusted introspection endpoint:
  https://login.example.test/realms/shop/protocol/openid-connect/token/introspect

Token state:
  active = true (delegate xử lý)

API audience:
  aud must contain "orders-api"

Issuer:
  iss must equal "https://login.example.test/realms/shop"
  (AS cam kết trả claim iss trong introspection response)

Allowed OAuth clients:
  client_id in ["shop-web", "trusted-orders-worker"]

Tenant:
  tenant_id must equal "shop-a"
  (API instance này phục vụ riêng shop-a)

Time:
  exp must exist and be in the future
  nbf, if supplied, must not be in the future
  (AS cam kết định dạng NumericDate/Instant tương thích)

Authorization after authentication:
  GET /api/orders/** requires SCOPE_orders.read
  POST /api/orders/** requires SCOPE_orders.write

Business authorization:
  caller chỉ thao tác Orders mà tenant/ownership/ACL cho phép
```

Đây là **hợp đồng minh họa**; các điều kiện issuer/tenant/expiration không phải mặc định bắt buộc của mọi introspection server. Nếu AS chỉ trả `active`, `scope` và `sub`, ta phải **thỏa thuận bổ sung dữ liệu với AS** hoặc dùng cơ chế ràng buộc tài nguyên khác, chứ không tự gán những claims còn thiếu để “đạt” policy.

### 4.1. Vì sao audience là điều kiện quan trọng?

Có thể một OAuth client dùng nhiều APIs:

```text
client_id = shop-web

Access token A:
  aud = orders-api

Access token B:
  aud = payments-api
```

Nếu chỉ kiểm tra `client_id=shop-web`, Orders API có thể chấp nhận token B vốn dành cho Payments API. **`client_id` là định danh ứng dụng gọi; `aud` là nơi token được phép sử dụng.** Không dùng hai trường đó thay nhau.

### 4.2. Vì sao không hardcode tenant cho API đa tenant?

Ví dụ một API instance phục vụ cả `shop-a` và `shop-b`. Nếu wrapper yêu cầu `tenant_id=shop-a`, mọi token hợp lệ của shop-b sẽ bị từ chối ngay tại authentication.

Khi Resource Server đa tenant, rule ở wrapper có thể chỉ yêu cầu `tenant_id` có mặt, đúng kiểu và nằm trong danh sách/quan hệ tin cậy. **Quyền của người gọi với từng order thuộc tenant nào** vẫn cần kiểm tra ở service. Không biến một object-level policy thành điều kiện token-wide nếu policy phụ thuộc tài nguyên đang được truy cập.

## 5. Wrapper đầu tiên: kiểm tra audience sau introspection

Một ví dụ tối giản:

```java
public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object audience = principal.getAttribute("aud");

        boolean matched =
            audience instanceof String text &&
                expectedAudience.equals(text);

        if (audience instanceof Collection<?> values) {
            matched = values.stream()
                .anyMatch(expectedAudience::equals);
        }

        if (!matched) {
            throw new BadOpaqueTokenException(
                "Access token is not intended for this API"
            );
        }

        return principal;
    }
}
```

Imports:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

Cách xử lý:

1. Delegate được gọi trước; nếu `active=false` hoặc introspection thất bại, wrapper **không tiếp tục**.
2. Wrapper đọc `aud` từ principal mà delegate trả về.
3. Cho phép dạng một chuỗi `"orders-api"` hoặc một tập/list giá trị có phần tử `"orders-api"`.
4. Nếu không tìm thấy audience mong đợi, ném `BadOpaqueTokenException`.
5. Chỉ trả principal **nguyên vẹn** khi token hợp lệ theo chính sách.

**Không sửa `aud` thành `orders-api` khi claim sai.** Điều đó sẽ biến token của API khác thành token được chấp nhận sai mục đích.

### 5.1. Nếu `aud` thiếu?

Với chính sách này, `aud=null` sẽ khiến `matched=false` và token bị từ chối. Đó là **fail closed**.

Nhưng cần nhớ RFC 7662 không buộc AS nào cũng trả audience. Nếu Orders API cần kiểm tra audience, phải thiết lập hợp đồng rõ rằng introspection response luôn cung cấp một giá trị audience đáng tin, hoặc dùng cơ chế cấp token hướng tài nguyên được AS bảo đảm bằng cách khác.

### 5.2. Nếu `aud` là kiểu lạ?

Ví dụ:

```json
{"aud": {"resource": "orders-api"}}
```

Wrapper không cố đoán object có nghĩa gì, mà từ chối vì không phù hợp hợp đồng. **Không dùng `String.valueOf(...)` để hợp thức hóa mọi kiểu dữ liệu**; với claim dùng bảo mật, chỉ nên chấp nhận những biểu diễn đã được thống nhất.

## 6. Wrapper đầy đủ: issuer, audience, client, tenant và expiry

Ví dụ tiếp theo xây một implementation **chủ đích chặt** cho Orders API instance chỉ phục vụ tenant `shop-a`.

Giả định hợp đồng introspection:

- `active` đã được delegate xác minh.
- `iss` là chuỗi URI hoặc `URI` và phải đúng issuer.
- `aud` là chuỗi hoặc collection strings.
- `client_id` là chuỗi thuộc allowlist.
- `tenant_id` là chuỗi đúng tenant.
- `exp` là `Instant`, numeric epoch seconds hoặc kiểu ngày được delegate chuẩn hóa.
- `nbf` là optional; nếu có phải hợp lệ về thời gian.

```java
public final class ContractCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;
    private final Set<String> allowedClientIds;
    private final String expectedTenant;
    private final Clock clock;

    public ContractCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience,
            Set<String> allowedClientIds,
            String expectedTenant,
            Clock clock) {

        this.delegate = Objects.requireNonNull(delegate);
        this.expectedIssuer = Objects.requireNonNull(expectedIssuer);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
        this.allowedClientIds = Set.copyOf(allowedClientIds);
        this.expectedTenant = Objects.requireNonNull(expectedTenant);
        this.clock = Objects.requireNonNull(clock);

        if (this.allowedClientIds.isEmpty()) {
            throw new IllegalArgumentException(
                "At least one OAuth client must be configured"
            );
        }
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate bắt buộc thực hiện introspection trước.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Map<String, Object> attributes = principal.getAttributes();

        String issuer = readText(attributes.get("iss"));
        if (!expectedIssuer.equals(issuer)) {
            reject("Issuer does not match the API contract");
        }

        if (!containsAudience(
                attributes.get("aud"), expectedAudience)) {
            reject("Audience does not match the API contract");
        }

        String clientId = readText(attributes.get("client_id"));
        if (!allowedClientIds.contains(clientId)) {
            reject("OAuth client is not allowed");
        }

        String tenant = readText(attributes.get("tenant_id"));
        if (!expectedTenant.equals(tenant)) {
            reject("Tenant does not match the API contract");
        }

        Instant expiration = readInstant(attributes.get("exp"));
        if (expiration == null ||
                !clock.instant().isBefore(expiration)) {
            reject("Token has no valid expiration");
        }

        Object rawNotBefore = attributes.get("nbf");
        if (rawNotBefore != null) {
            Instant notBefore = readInstant(rawNotBefore);

            if (notBefore == null ||
                    clock.instant().isBefore(notBefore)) {
                reject("Token is not yet valid");
            }
        }

        // Giữ nguyên name, claims và authorities của delegate.
        return principal;
    }

    private static String readText(Object value) {
        if (value instanceof String text) {
            return text;
        }
        if (value instanceof URI uri) {
            return uri.toString();
        }
        return null;
    }

    private static boolean containsAudience(
            Object rawAudience, String expected) {

        if (rawAudience instanceof String text) {
            return expected.equals(text);
        }

        if (rawAudience instanceof Collection<?> values) {
            return values.stream().anyMatch(expected::equals);
        }

        return false;
    }

    private static Instant readInstant(Object rawValue) {
        if (rawValue instanceof Instant instant) {
            return instant;
        }

        if (rawValue instanceof Date date) {
            return date.toInstant();
        }

        if (rawValue instanceof Long seconds) {
            return Instant.ofEpochSecond(seconds);
        }

        if (rawValue instanceof Integer seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }

        // Không tự đoán chuỗi thời gian hoặc kiểu số không cam kết.
        return null;
    }

    private static void reject(String reason) {
        throw new BadOpaqueTokenException(reason);
    }
}
```

Imports:

```java
import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.util.Collection;
import java.util.Date;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

### 6.1. Đọc đúng phạm vi của ví dụ

Đây là một **hợp đồng minh họa**, không phải danh sách claims bắt buộc theo mọi RFC.

- `expectedIssuer`: Chỉ kiểm tra khi AS cam kết trả issuer. Trusted introspection URL được cấu hình riêng và bảo vệ bằng TLS/credentials.
- `expectedAudience`: Ngăn token được cấp cho API khác.
- `allowedClientIds`: Chặn client chưa được thỏa thuận dùng API này; **không thay audience**.
- `expectedTenant`: Chỉ phù hợp với instance phục vụ tenant cố định.
- `exp`: Ví dụ chủ động **yêu cầu** expiry. Một AS có thể chỉ trả active; khi đó cần hợp đồng khác thay vì tự đặt `exp`.
- `nbf`: Nếu AS trả `nbf`, kiểm tra thời điểm bắt đầu hiệu lực.

`readInstant(...)` cố ý giới hạn các kiểu mà hợp đồng chấp nhận. Nếu implementation delegate trả thêm kiểu khác, cần thiết kế converter rõ ràng thay vì bắt mọi giá trị rồi đoán. Giá trị `exp` theo RFC 7662 được mô tả bằng kiểu integer epoch seconds; việc delegate chuyển thành `Instant` hoặc kiểu khác phụ thuộc implementation.

### 6.2. Đồng hồ và clock skew

Ví dụ dùng `clock.instant()` để quyết định hiệu lực:

```java
Clock systemClock = Clock.systemUTC();
```

Nếu hệ thống cần dung sai nhỏ giữa đồng hồ AS và Resource Server, quy tắc cần được định nghĩa rõ. Ví dụ **hợp đồng cho phép 30 giây skew** có thể áp:

```java
Duration skew = Duration.ofSeconds(30);
Instant now = clock.instant();

boolean notExpired =
    expiration != null &&
    now.isBefore(expiration.plus(skew));

boolean started =
    notBefore == null ||
    !now.plus(skew).isBefore(notBefore);
```

Đây chỉ là minh họa logic dung sai; khi đưa vào wrapper, phải vẫn **từ chối `exp` thiếu hoặc sai kiểu** nếu contract bắt buộc, đồng thời làm rõ semantics inclusive/exclusive tại ranh giới.

**Không đặt skew quá rộng** để che lỗi NTP. Hơn nữa, introspection là online: AS có thể đã đánh giá thời gian và trả `active=false`. Wrapper không nên “hồi sinh” token inactive vì ứng dụng chấp nhận một dung sai lớn hơn.

### 6.3. Tại sao không bắt exception của delegate rồi trả principal?

Sai nghiêm trọng:

```java
try {
    return delegate.introspect(token);
} catch (Exception ex) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "anonymous-fallback",
        Map.of("scope", "orders.read"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
}
```

Đoạn trên là **ví dụ không an toàn**, không được dùng. Introspection endpoint lỗi mạng hoặc trả inactive **không phải là lý do để tạo principal hợp lệ**. Cách đúng: để exception lan truyền theo cơ chế xác thực hoặc xử lý lỗi hạ tầng mà vẫn **fail closed**.

### 6.4. Vì sao wrapper trả nguyên principal?

Khi các điều kiện đạt, `return principal;` giữ nguyên:

- `principal.getName()`.
- `principal.getAttributes()`.
- `principal.getAuthorities()`.

Điều này giúp giữ sự nhất quán của delegate, tránh vô tình làm mất `SCOPE_...` hoặc thêm quyền không có trong AS. Nếu cần ánh xạ quyền/attributes, xem phần thiết kế riêng dưới đây và bảo đảm có hợp đồng với AS.

## 7. Đăng ký wrapper thành bean trong Spring Boot

Các dependencies thông dụng:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Ví dụ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/realms/shop/protocol/openid-connect/token/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Biến môi trường `INTROSPECTION_CLIENT_SECRET` chỉ là minh họa. Không hardcode secret production trong source hoặc ghi nó vào log. Thông tin `client-id` / `client-secret` ở đây là **credentials của Resource Server để gọi introspection endpoint**, không phải `client_id` của ứng dụng đã xin access token.

### 7.1. Bean tạo delegate và bọc hợp đồng

Ví dụ với `NimbusOpaqueTokenIntrospector` ở các phiên bản Spring Security còn cung cấp constructor này:

```java
@Configuration
public class OpaqueTokenSecurityConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                String resourceServerClientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                String resourceServerSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                resourceServerClientId,
                resourceServerSecret
            );

        return new ContractCheckingOpaqueTokenIntrospector(
            delegate,
            "https://login.example.test/realms/shop",
            "orders-api",
            Set.of("shop-web", "trusted-orders-worker"),
            "shop-a",
            Clock.systemUTC()
        );
    }
}
```

Imports:

```java
import java.time.Clock;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

**Phiên bản thư viện:** `NimbusOpaqueTokenIntrospector` là implementation quen thuộc trong Spring Security 5.x/6.x, nhưng một số phiên bản mới dùng/deprecate API khác. Nếu dependency của dự án không có constructor trong ví dụ, hãy dùng builder/implementation introspector phù hợp **với phiên bản thực tế** và vẫn truyền nó vào cùng wrapper. Không tự viết HTTP introspection từ đầu chỉ vì API builder thay đổi.

### 7.2. Vì sao bean tùy chỉnh ảnh hưởng auto-configuration?

Spring Boot có thể auto-configure introspector từ `spring.security.oauth2.resourceserver.opaquetoken.*`. Khi ứng dụng đăng ký bean `OpaqueTokenIntrospector` của riêng mình, auto-configuration thường **back off**, và **bean do ứng dụng tạo trở thành nguồn introspection thực tế**.

Vì vậy đừng chỉ khai báo:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

rồi cho rằng bean tự tạo đã nhận các giá trị đó nếu nó không bind các properties. Ví dụ trên sử dụng `@Value` để lấy chúng.

Trong hệ thống có Spring configuration phức tạp, cần tránh tạo **vòng phụ thuộc bean** bằng cách cố inject chính `OpaqueTokenIntrospector` vào bean cùng kiểu mà nó đang xây. Hãy tạo delegate tách biệt hoặc dùng tên/qualifier rõ ràng.

## 8. Kết nối introspector với Servlet `SecurityFilterChain`

Một cấu hình tham khảo:

```java
@Configuration
public class ApiSecurityFilterConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Ở đây, nhánh `opaqueToken(...)` dùng `OpaqueTokenIntrospector` được cấu hình. Khi bean wrapper trả `OAuth2AuthenticatedPrincipal` thành công, provider tạo Authentication để HTTP authorization đánh giá authorities.

Không nên đặt rule quá rộng như:

```java
.requestMatchers("/api/**").authenticated()
```

rồi nghĩ chỉ cần wrapper kiểm tra `aud`/`tenant_id` là đủ. Token hợp lệ nhưng không có quyền `orders.write` vẫn phải bị từ chối với POST cần quyền ghi.

### 8.1. Dùng DSL để chỉ định introspector tường minh

Trong một số cấu hình, có thể truyền introspector trực tiếp cho nhánh opaque token:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(opaque ->
        opaque.introspector(contractIntrospector)
    )
)
```

`contractIntrospector` là object được tạo/cấp vào cấu hình một cách hợp lệ. Đoạn này hữu ích khi có nhiều bean hoặc cần kiểm soát rõ introspector dùng cho chain cụ thể.

**Khi có nhiều `SecurityFilterChain`**, cần xác nhận request thực sự được chọn vào chain có cấu hình opaque token. `securityMatcher(...)` xác định phạm vi cả chain, còn `requestMatchers(...)` xác định rules ở trong chain đó.

## 9. Introspection client credentials khác OAuth caller client_id

Đây là điểm rất dễ nhầm:

| Thông tin | Chủ thể | Dùng để làm gì? |
|---|---|---|
| `opaquetoken.client-id` trong Spring config | Resource Server | Xác thực khi gọi introspection endpoint |
| `opaquetoken.client-secret` trong Spring config | Resource Server | Bí mật xác thực introspection endpoint |
| Claim `client_id` trong introspection result | OAuth client đã xin/có token, theo AS | Có thể dùng làm policy về ứng dụng gọi |
| Claim `aud` | Resource Server/API mà token hướng đến | Kiểm tra token có dành cho Orders API không |
| Claim `sub` | Principal liên quan token | User/service identity tùy grant/profile |

Ví dụ Resource Server gọi introspection với credentials `orders-api-introspection`, AS trả:

```json
{
  "active": true,
  "client_id": "shop-web",
  "aud": ["orders-api"]
}
```

**Không có mâu thuẫn**: hai client IDs thuộc hai vai trò khác nhau.

Một lỗi thường gặp là wrapper so sánh claim `client_id` với client ID dùng để authenticate introspection request. Điều đó sẽ từ chối token hợp lệ từ ứng dụng `shop-web`, hoặc dẫn tới việc mở policy theo một giá trị không đúng mục đích.

## 10. Kiểm tra `iss` khi introspection response có hoặc không có issuer

Trong JWT, claim `iss` thường là issuer của token. Với introspection RFC 7662, `iss` là một thuộc tính có thể được trả, nhưng **không phải mọi AS đều trả issuer**.

Nếu AS cam kết công bố issuer:

```java
String issuer = readText(principal.getAttribute("iss"));
if (!expectedIssuer.equals(issuer)) {
    throw new BadOpaqueTokenException("Unexpected issuer");
}
```

Đây là chính sách hợp lệ.

Nếu AS **không trả issuer** nhưng endpoint introspection đã được xác thực qua URL/TLS và credentials riêng, Resource Server không thể tự dựng một claim issuer theo ý mình rồi gọi đó là validation. Hãy cân nhắc:

1. Thống nhất AS trả issuer cho token active.
2. Sử dụng một introspection endpoint riêng theo tenant/realm đã tin cậy, với contract rằng response chỉ áp cho token của realm đó.
3. Dùng cơ chế AS hỗ trợ để ràng buộc token với issuer/resource.
4. Không mở acceptance cho issuer khác chỉ vì claim thiếu.

**Không trộn token của nhiều AS vào một introspector chung** mà không có trusted issuer resolution phù hợp. Việc routing tới AS dựa trên dữ liệu token chưa xác thực phải nằm trong allowlist/logic đã quản trị.

## 11. Audience và ràng buộc tài nguyên

Nếu token active chỉ dành cho Payments API:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "payments.read"
}
```

Orders API phải từ chối nếu chính sách yêu cầu `aud` chứa `orders-api`. Bởi vì `active=true` chỉ nói token còn hoạt động trong ngữ cảnh AS, không nói nó được dùng tại mọi Resource Server.

### 11.1. Dạng chuỗi và dạng danh sách

Theo contract, `aud` có thể là:

```json
"aud": "orders-api"
```

hoặc:

```json
"aud": ["orders-api", "inventory-api"]
```

Hàm `containsAudience(...)` trong ví dụ hỗ trợ cả hai. Nếu AS trả danh sách với kiểu khác như một object, wrapper từ chối, trừ khi AS định nghĩa chuyển đổi chính thức.

### 11.2. Nhiều audiences không có nghĩa chấp nhận token cho mọi API

Một token đa audience có thể dùng ở nhiều tài nguyên mà AS cho phép. Nhưng Orders API vẫn phải kiểm tra **chính nó nằm trong audience**. Đừng tự sửa `aud` hoặc lấy `client_id` làm audience chỉ vì tất cả tokens đều thuộc một OAuth client.

### 11.3. Scope và audience là hai ràng buộc độc lập

Một token có `scope=orders.read` nhưng `aud=payments-api` vẫn không được dùng ở Orders API. Một token có `aud=orders-api` nhưng không có `orders.read` cũng không được gọi endpoint đọc yêu cầu scope đó.

Wrapper kiểm tra audience; `authorizeHttpRequests(...)` và service kiểm tra quyền thao tác và đối tượng.

## 12. Kiểm tra client_id: allowlist có giới hạn

Một số API chỉ phục vụ ứng dụng doanh nghiệp đã duyệt:

```text
allowed clients:
  shop-web
  trusted-orders-worker
```

Một wrapper có thể kiểm tra:

```java
String clientId = readText(principal.getAttribute("client_id"));

if (!allowedClientIds.contains(clientId)) {
    throw new BadOpaqueTokenException("Client not allowed");
}
```

Nhưng cần nhớ:

- `client_id` chỉ đáng dùng khi introspection response của AS đáng tin cam kết ý nghĩa đó.
- Allowlist là **quy tắc của Resource Server**, không lấy từ bearer request body/query.
- Client ID không thay audience.
- Client ID không chứng minh end user là owner của một order.
- Với nhiều tenants, một client có thể được phép ở tenant A nhưng không ở B; kiểm tra ràng buộc theo cặp client–tenant nếu contract yêu cầu.

### 12.1. Không dùng client allowlist thay OAuth scope

Nếu `shop-web` là client hợp lệ nhưng token chỉ được cấp `profile`, caller vẫn không có `orders.write`. Allowlist kiểm tra **ứng dụng**; scope/authority kiểm tra **năng lực được token cấp**.

### 12.2. Trường hợp Client Credentials

Token theo client credentials có thể đại diện service principal:

```json
{
  "active": true,
  "client_id": "trusted-orders-worker",
  "sub": "service-order-sync",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Nếu policy yêu cầu chỉ một tập service clients được phép đồng bộ, wrapper có thể là một lớp bảo vệ. Nhưng object-level policy vẫn phải giới hạn **tập orders thuộc integration/tenant được phép**, không cho service đọc toàn bộ dữ liệu chỉ vì client nằm trong allowlist.

## 13. Kiểm tra tenant: claim validation khác quyền đối tượng

Giả sử AS trả:

```json
{
  "active": true,
  "tenant_id": "shop-a",
  "aud": ["orders-api"]
}
```

Với một Orders API chỉ phục vụ `shop-a`, wrapper có thể đòi exact tenant match. Nhưng với Orders API phục vụ nhiều tenants, policy nên khác:

```java
Object rawTenant = principal.getAttribute("tenant_id");

if (!(rawTenant instanceof String tenant) ||
        tenant.isBlank()) {
    throw new BadOpaqueTokenException("Invalid tenant_id");
}
```

Sau đó object policy xác minh user/service được đọc order cụ thể.

```text
Token:
  tenant_id = shop-a
  scope = orders.read

Request:
  GET /api/tenants/shop-b/orders/order-99

Wrapper:
  token có tenant hợp lệ? Có thể có

Service policy:
  caller có quyền shop-b/order-99? Không
```

Không nên sửa `tenant_id=shop-b` chỉ vì URL yêu cầu shop-b. Path/query do caller gửi là dữ liệu yêu cầu, **không phải bằng chứng quyền**.

### 13.1. Khi membership thay đổi

Một opaque token active có thể được introspection trả claims theo trạng thái AS, nhưng không mặc định nghĩa là mọi quyền tenant cập nhật trong database nghiệp vụ đã được phản ánh. Hệ thống nhạy cảm có thể cần tra membership/assignment hiện hành, đặc biệt khi quyền bị thu hồi.

Đừng dùng wrapper token-wide để thay toàn bộ logic ràng buộc owner/tenant của từng bản ghi.

## 14. Kiểm tra thời hạn với `exp` và `nbf`

RFC 7662 mô tả:

- `exp`: thời điểm token hết hạn, dưới dạng NumericDate (nếu trả).
- `iat`: thời điểm token phát hành (nếu trả).
- `nbf`: token chưa được phép sử dụng trước thời điểm này (nếu trả).

AS thường chịu trách nhiệm quyết định `active`. Nhưng trong một hợp đồng chặt, Resource Server có thể muốn bổ sung rule “token phải có `exp`” hoặc xác minh `nbf` nếu AS công bố.

### 14.1. Không được giả định `exp` luôn có

Một response:

```json
{
  "active": true,
  "scope": "orders.read"
}
```

không trái nguyên tắc RFC 7662 chỉ vì không có `exp`. Nếu ứng dụng bắt buộc expiry, đó là **quy định thêm** phải được Authorization Server hỗ trợ.

Không nên tự đặt `exp=now+1h` cho token thiếu expiry để làm wrapper chấp nhận. Điều đó tạo claim mà AS không xác nhận.

### 14.2. Khi bắt buộc `exp`, hãy fail closed

```java
Instant expires = readInstant(principal.getAttribute("exp"));

if (expires == null || !clock.instant().isBefore(expires)) {
    throw new BadOpaqueTokenException("Missing or expired exp");
}
```

Nếu đồng hồ giữa AS và RS có lệch nhỏ, có thể định nghĩa clock skew hợp lý. Nhưng skew không được làm wrapper nhận token mà delegate đã xác định inactive. **Trạng thái `active=false` phải luôn bị từ chối**.

### 14.3. `iat` không thay `exp`

Một token phát hành cách đây 10 phút vẫn có thể còn hạn hoặc hết hạn tùy AS. Claim `iat` chỉ là thời điểm cấp token, không tự chứng minh TTL.

Nếu API cần giới hạn tuổi token theo `iat`, phải định nghĩa rõ policy riêng và đồng hồ/dung sai, không suy ra từ tên claim.

## 15. Kiểm tra kiểu token và profile

Introspection response có thể chứa:

```json
"token_type": "Bearer"
```

Theo RFC 7662, `token_type` là token type nếu AS công bố. Một số hệ thống còn có thuộc tính riêng để mô tả access token hoặc refresh token.

Resource Server cần **chấp nhận token phù hợp với loại và mục đích nó hỗ trợ**. Nếu AS có thể introspect refresh token hoặc tokens dành cho mục đích khác, hợp đồng phải ngăn dùng chúng như bearer access token ở API.

Một rule minh họa khi AS cam kết `token_type=Bearer`:

```java
Object rawType = principal.getAttribute("token_type");

if (!(rawType instanceof String type) ||
        !"Bearer".equalsIgnoreCase(type)) {
    throw new BadOpaqueTokenException("Unsupported token type");
}
```

**Không nên áp rule này mù quáng cho mọi AS**: có AS không trả token_type trong response hoặc dùng profile riêng. Phải hiểu đặc tả mà hệ thống thực sự triển khai.

Không dùng OIDC ID token thay access token chỉ vì cùng issuer và chứa subject. Resource Server cần xác minh token có mục đích dành cho API, đặc biệt qua audience và AS contract.

## 16. Mapping scopes và authorities: giữ nguyên hay tùy chỉnh?

Sau introspection thành công, `OAuth2AuthenticatedPrincipal` có:

```java
principal.getAttributes();
principal.getAuthorities();
principal.getName();
```

Trong cấu hình phổ biến, Spring Security có thể tạo authorities như:

```text
SCOPE_orders.read
SCOPE_orders.write
```

từ response `scope` theo cách implementation quy định.

**Wrapper kiểm tra contract không nên tự ý cấp thêm quyền**. Ví dụ sai:

```java
List<GrantedAuthority> elevated = List.of(
    new SimpleGrantedAuthority("ROLE_ADMIN")
);

return new DefaultOAuth2AuthenticatedPrincipal(
    principal.getName(),
    principal.getAttributes(),
    elevated
);
```

Nếu AS chỉ cấp scope đọc, việc wrapper gán `ROLE_ADMIN` không có căn cứ là **privilege escalation**.

### 16.1. Khi cần chuẩn hóa claims trước khi ánh xạ quyền

Giả sử AS dùng claim riêng:

```json
{
  "active": true,
  "permissions": ["orders:read", "orders:export"]
}
```

Để ánh xạ thành authorities, cần một **chính sách có hợp đồng**:

- `orders:read` tương ứng authority nào?
- Có yêu cầu audience/tenant hay client type không?
- Claim `permissions` có phải do AS tin cậy trả không?
- Có cho phép role admin hay chỉ scope API?
- Có phải giữ nguyên authorities của delegate không?

Một ví dụ **chỉ thêm attribute hiển thị đã được xác thực**, không cấp quyền mới:

```java
Map<String, Object> attributes =
    new LinkedHashMap<>(principal.getAttributes());

Object tenant = attributes.get("tenant_id");

if (tenant instanceof String text && !text.isBlank()) {
    attributes.put("internal_tenant_code", text);
}

OAuth2AuthenticatedPrincipal enriched =
    new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        attributes,
        principal.getAuthorities()
    );
```

Imports:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
```

Đoạn này chỉ minh họa cách dựng principal mới khi **cần thật sự** thêm một alias nội bộ. Với wrapper chỉ kiểm tra, tốt nhất là `return principal;`. Không biến alias thành bằng chứng một claim đã được AS phát hành độc lập.

### 16.2. Khi muốn thay tên principal

Trong opaque Resource Server, `OAuth2AuthenticatedPrincipal.getName()` có thể dựa trên thông tin subject/username từ AS tùy implementation. Nếu cần identity ổn định, hãy xác định hợp đồng `sub`/issuer/tenant hoặc mapping account trong hệ thống. Không tự dùng username hay email để hợp nhất identities từ nhiều issuers chỉ vì chúng giống nhau.

Đối với object authorization, có thể cần cặp định danh `(issuer, subject)`, không chỉ principal name.

## 17. Wrapper không thay HTTP authorization

Khi wrapper đã chấp nhận token:

```text
active = true
iss đúng
aud chứa orders-api
client_id được phép
tenant hợp lệ
exp hợp lệ
```

request vẫn cần điều kiện HTTP:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().denyAll()
)
```

Một token có scope `orders.read` không được gọi POST nếu POST yêu cầu `orders.write`. Ngược lại, token có `orders.write` không tự có quyền đọc nếu chính sách của API tách hai scopes.

### 17.1. Object-level authorization vẫn bắt buộc

Ví dụ user-123 có token hợp lệ cho Orders API và `SCOPE_orders.read`, nhưng muốn đọc đơn của user-456.

Wrapper **không có order ID/DB resource context** để quyết định ownership. Service phải kiểm tra:

```text
canReadOrder(actor, order):
  actor has SCOPE_orders.read
  AND actor tenant is allowed
  AND (
       actor is owner
       OR share ACL permits
       OR assigned support policy permits
  )
```

Không đưa DB query theo request vào một introspector token-wide chỉ để kiểm tra đơn hàng cụ thể; như vậy một token có thể hợp lệ cho endpoint khác nhưng bị từ chối ở authentication vì rule sai cấp.

## 18. Lỗi từ delegate và từ wrapper phải được phân biệt

Những thất bại thường gặp:

| Trường hợp | Thành phần phát hiện | Ý nghĩa |
|---|---|---|
| `active=false` | Delegate introspector | Token không còn active hoặc không được AS xác nhận |
| Invalid introspection credentials | Delegate/HTTP layer | Resource Server không xác thực được với AS |
| AS timeout/TLS/DNS failure | Delegate/HTTP layer | Hạ tầng introspection không sẵn sàng |
| `aud` không chứa `orders-api` | Wrapper | Token không dành cho API |
| `client_id` không nằm trong allowlist | Wrapper | Client không thỏa contract |
| `tenant_id` thiếu hoặc sai | Wrapper | Token không thỏa ràng buộc tenant |
| `exp` thiếu khi bắt buộc | Wrapper | Contract đòi expiry không được đáp ứng |
| Token qua introspection, thiếu `SCOPE_orders.read` | AuthorizationFilter | Caller không đủ quyền thao tác |
| Token có scope, không được xem order-42 | Service/method security | Caller không đủ quyền đối tượng |

### 18.1. `BadOpaqueTokenException`

Khi wrapper xác định token **không đáp ứng contract xác thực**, có thể dùng:

```java
throw new BadOpaqueTokenException(
    "Audience does not match the API contract"
);
```

Spring Security sẽ xử lý exception trong chuỗi authentication theo cách cấu hình của provider, entry point và handlers. Trong nhiều Resource Server, lỗi token không hợp lệ dẫn đến `401 Unauthorized` với bearer error như `invalid_token`.

Ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Mã HTTP/header chính xác phụ thuộc exception propagation và cấu hình. Không nên kết luận mọi lỗi introspection đều luôn trở thành cùng một response.

### 18.2. Lỗi network và lỗi token là hai loại khác nhau

Nếu AS trả `active=false`, có cơ sở xem token không hoạt động. Nếu AS timeout, Resource Server **không có đủ thông tin để xác thực token**, nhưng đó không tự chứng minh token đã bị AS thu hồi.

Hệ thống vẫn phải **fail closed**. Trong quan sát nội bộ nên phân biệt:

```text
AUTH_TOKEN_INACTIVE
AUTH_CONTRACT_WRONG_AUDIENCE
AUTH_CONTRACT_INVALID_TENANT
INTROSPECTION_TIMEOUT
INTROSPECTION_TLS_ERROR
INTROSPECTION_CREDENTIAL_FAILURE
```

Không bắt rộng mọi exception rồi trả một principal giả. Cũng không trả nguyên stack trace, URL nội bộ nhạy cảm hoặc introspection credentials trong response cho client.

## 19. Không tạo vòng gọi introspection vô hạn

Một lỗi cấu hình phổ biến là wrapper dùng chính bean introspector mà nó thay thế:

```java
@Bean
OpaqueTokenIntrospector myIntrospector(
        OpaqueTokenIntrospector introspector) {
    return token -> introspector.introspect(token);
}
```

Nếu bean wiring tạo vòng phụ thuộc hoặc self-reference, ứng dụng có thể không khởi động hoặc hoạt động sai. Cách đúng là tạo **delegate cụ thể** bằng implementation tin cậy rồi truyền nó vào wrapper; hoặc khai báo bean delegate riêng có qualifier rõ ràng:

```java
@Bean("baseIntrospector")
OpaqueTokenIntrospector baseIntrospector(...) {
    // Khởi tạo implementation của Spring Security theo phiên bản.
}

@Bean
@Primary
OpaqueTokenIntrospector contractIntrospector(
        @Qualifier("baseIntrospector")
            OpaqueTokenIntrospector delegate) {
    return new ContractCheckingOpaqueTokenIntrospector(
        delegate, ISSUER, AUDIENCE, CLIENTS, TENANT, Clock.systemUTC()
    );
}
```

Đoạn thứ hai minh họa *wiring*, dùng hằng số giả định `ISSUER`, `AUDIENCE`, `CLIENTS`, `TENANT` và phần thân delegate cần được hiện thực theo cấu hình dự án. `@Primary` chỉ cần khi có nhiều bean cùng kiểu và muốn xác định một bean mặc định; nên dùng DSL/qualifier rõ ràng nếu các SecurityFilterChains dùng policies khác nhau.

## 20. Không cho token tự xác định URL introspection

Giả sử client gửi bearer token:

```text
token = https://attacker.example.test/token/abc
```

hoặc token có cấu trúc mà attacker lồng một URL vào chuỗi. Resource Server **không được lấy URL từ token** để gọi introspection tùy ý. Điều đó có thể gây SSRF hoặc tin một AS không được cấu hình.

Introspection URI phải là **configuration tin cậy**. Với nhiều issuers/tenants, việc chọn endpoint phải dựa trên allowlist/mapping đã được quản trị, không gọi URL từ dữ liệu chưa xác thực.

### 20.1. TLS và credentials

Introspection endpoint thường yêu cầu Resource Server chứng minh danh tính của nó với AS (ví dụ HTTP Basic với client credentials, private_key_jwt, mTLS hoặc cơ chế khác tùy AS). Cần:

- HTTPS với xác minh chứng chỉ hợp lệ.
- Secrets được cấp từ secret manager/env được kiểm soát, không hardcode.
- Quyền của introspection client chỉ đủ thực hiện introspection.
- Không log Authorization Basic header hoặc token gửi introspection.
- Timeout, connection pooling, retry/backoff có kiểm soát.
- Chính sách egress/network rõ ràng.

**Không dùng OAuth client secret của frontend/mobile app** làm secret introspection. Public client không thể bảo vệ một secret như server-side client; introspection authentication cần cấu hình phù hợp với AS.

## 21. Timeout, retry và tính sẵn sàng

Opaque introspection thường phụ thuộc mạng ở luồng xác thực. Nếu mỗi request đều cần một lần roundtrip:

```text
Client → Orders API → AS introspection → Orders API → Controller
```

độ trễ hoặc outage của AS có thể ảnh hưởng trực tiếp đến Orders API.

Các chiến lược vận hành:

| Chiến lược | Lợi ích | Rủi ro / điều kiện |
|---|---|---|
| HTTP connect/read timeout | Tránh request treo quá lâu | Timeout quá ngắn gây false failures |
| Connection pooling | Giảm chi phí kết nối | Phải quản lý lifecycle, giới hạn kết nối |
| Retry có giới hạn | Giúp vượt sự cố thoáng qua | Có thể làm AS quá tải nếu retry đồng loạt |
| Circuit breaker | Bảo vệ hạ tầng khi AS lỗi kéo dài | Khi breaker mở vẫn phải fail closed |
| Rate limiting | Giảm lạm dụng bearer requests | Cần không cản trở traffic hợp lệ |
| Observability | Xác định lỗi network vs invalid token | Không log secrets |

Không “tối ưu availability” bằng cách cấp quyền tạm thời khi AS không truy cập được. Một token chưa được introspect thành công **chưa thể coi là authenticated**.

## 22. Có nên cache introspection không?

Caching có thể giảm latency và tải lên AS, nhưng làm thay đổi ý nghĩa “kiểm tra trạng thái token hiện tại”.

Ưu điểm:

- Giảm introspection calls cho cùng bearer token.
- Giảm độ trễ endpoint.
- Giảm phụ thuộc mạng với AS trong khoảng cache hợp lệ.

Nhược điểm bảo mật:

- Token bị revoked sau một lần introspection có thể vẫn được chấp nhận cho đến khi cache hết hạn.
- Membership/tenant/permissions thay đổi ở AS có thể chưa được phản ánh.
- Cache chứa dữ liệu nhạy cảm từ tokens.
- Key cache không an toàn có thể làm lộ bearer token.

### 22.1. Nguyên tắc trước khi bật cache

1. Chỉ cache sau khi delegate và contract wrapper **đã chấp nhận** token.
2. Xác định TTL tối đa nhỏ hơn các hạn token/contract liên quan.
3. Đánh giá yêu cầu độ trễ phát hiện revocation.
4. Không dùng raw bearer token làm key trong logs/metrics.
5. Bảo vệ cache và dữ liệu principal; cân nhắc hash/HMAC lookup key, tránh log key có thể phục hồi bearer token.
6. Invalidate theo policy nếu quyền/tenant thay đổi.
7. Khi AS outage, **không tự mở rộng cache TTL vô hạn** để tiếp tục chấp nhận credentials cũ.

Vị trí cache cũng quan trọng:

```text
Bearer token
  -> cache đã kiểm tra contract?
  -> delegate introspection khi cache miss
  -> wrapper checks
  -> result
```

Nếu cache **trước wrapper**, mỗi cache hit phải vẫn chạy contract checks, đặc biệt khi expected audience/tenant/client allowlist có thể thay đổi. Nếu cache sau wrapper, cache lưu kết quả đã qua policy nhưng phải xử lý policy version/invalidation khi contract đổi.

### 22.2. Revocation và short-lived tokens

Một lý do chọn opaque introspection là có thể hỏi AS về `active`. Nếu cache rất lâu, lợi ích revocation online bị giảm. Cần thỏa thuận mục tiêu phát hiện revocation và chọn TTL theo rủi ro API.

Không có một TTL “đúng” chung cho mọi tổ chức. Những API thanh toán hoặc tác vụ quản trị có thể cần ràng buộc chặt hơn API chỉ đọc tài liệu ít nhạy cảm.

## 23. Không biến claims từ introspection thành quyền ngoài hợp đồng

Một lỗi nguy hiểm:

```java
if (principal.getAttribute("client_id") != null) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        principal.getAttributes(),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
    );
}
```

Claim `client_id` tồn tại **không chứng minh mọi client là admin**. Authority mapping cần tương ứng với permissions/scopes mà AS cấp và policy doanh nghiệp.

Một rule khác sai:

```java
if (principal.getAttribute("aud") == null) {
    attributes.put("aud", "orders-api");
}
```

Nếu API yêu cầu `aud` và AS không trả claim, phải sửa hợp đồng hoặc từ chối token. Việc tự điền audience biến một kiểm tra bảo mật thành điều kiện luôn đúng.

Tương tự, không tự sửa `exp` khi token đã hết hạn, không gán `tenant_id` theo request path và không điền `sub=admin` khi missing.

## 24. Kiểm tra wrapper bằng unit test độc lập

Ưu điểm của decorator là dễ kiểm tra với một delegate giả **không cần gọi mạng thật**.

Giả sử wrapper đơn giản chỉ kiểm tra audience:

```java
@Test
void acceptsMatchingAudience() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of(
                "sub", "user-123",
                "aud", List.of("orders-api")
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        );

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(delegate, "orders-api");

    OAuth2AuthenticatedPrincipal result =
        introspector.introspect("test-token");

    assertEquals("user-123", result.getName());
}
```

Trường hợp audience sai:

```java
@Test
void rejectsWrongAudience() {
    OpaqueTokenIntrospector delegate = token ->
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-123",
            Map.of(
                "sub", "user-123",
                "aud", List.of("payments-api")
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_payments.read")
            )
        );

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(delegate, "orders-api");

    assertThrows(
        BadOpaqueTokenException.class,
        () -> introspector.introspect("test-token")
    );
}
```

Imports minh họa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
```

**Các unit tests này không gọi AS introspection endpoint và không chứng minh token thật active.** Chúng chỉ kiểm tra hành vi wrapper khi delegate trả một principal được giả lập.

### 24.1. Test delegate ném exception phải giữ fail-closed

```java
@Test
void doesNotRecoverFromInactiveToken() {
    OpaqueTokenIntrospector inactiveDelegate = token -> {
        throw new BadOpaqueTokenException("Inactive token");
    };

    OpaqueTokenIntrospector introspector =
        new AudienceCheckingIntrospector(
            inactiveDelegate, "orders-api");

    assertThrows(
        BadOpaqueTokenException.class,
        () -> introspector.introspect("inactive-token")
    );
}
```

Điểm cốt lõi là wrapper **không trả principal khi delegate đã từ chối**.

### 24.2. Các kịch bản cần thể hiện trong thiết kế test

| Introspection/delegate | Hợp đồng wrapper | Kỳ vọng |
|---|---|---|
| Delegate ném `BadOpaqueTokenException` (inactive) | Không kiểm tra tiếp | Từ chối |
| Delegate ném lỗi network | Không tự chuyển thành success | Fail closed |
| Active, aud đúng | Các điều kiện còn lại đúng | Chấp nhận |
| Active, aud chỉ dành Payments API | Sai audience | Từ chối |
| Active, thiếu aud khi contract bắt buộc | Sai audience | Từ chối |
| Active, client_id ngoài allowlist | Sai client | Từ chối |
| Active, tenant sai/thiếu | Sai tenant | Từ chối |
| Active, exp thiếu nhưng contract buộc có | Sai expiry | Từ chối |
| Active, exp quá hạn | Sai thời gian | Từ chối |
| Active, tất cả contract checks đạt, thiếu scope đọc | Wrapper chấp nhận; HTTP authorization từ chối | Thường 403 |
| Active, đúng scope đọc, order thuộc user khác | Wrapper chấp nhận; service policy từ chối | 403/404 tùy policy |

### 24.3. Integration test có contract AS thật

Ngoài unit tests, khi có môi trường test, cần xác minh:

- Spring Boot dùng **đúng bean introspector wrapper**, không vô tình dùng auto-config delegate khác.
- Introspection HTTP request được xác thực bằng đúng credentials của Resource Server.
- Một response `active=false` bị từ chối.
- Một response `active=true` nhưng `aud` sai bị từ chối.
- Authorities sau wrapper vẫn là những authorities được AS/mapper cấp.
- Endpoint dùng `hasAuthority(...)` đúng.
- Error path không lộ bearer token/secret.
- Timeout/TLS failure không tạo Authentication.
- Request public và protected đi qua đúng `SecurityFilterChain`.

Có thể dùng HTTP stub server thay AS thật để mô phỏng response introspection, nhưng cần nhớ stub không thể thay thế việc kiểm tra policy và cấu hình production.

## 25. Introspection có thể trả thời gian sai kiểu hoặc claim không ổn định

Ví dụ một AS trả:

```json
{
  "active": true,
  "tenant_id": 42,
  "aud": "orders-api",
  "exp": "1900000000"
}
```

Nếu hợp đồng yêu cầu:

```text
tenant_id: String
exp: integer NumericDate
```

thì response này **không đúng hợp đồng**. Đừng tùy tiện chuyển số tenant và chuỗi exp sang kiểu mong đợi mà không thỏa thuận.

Một implementation có thể chuyển đổi claims trước khi wrapper nhìn chúng. Nhưng thay vì suy ra từ JSON mẫu, cần dựa trên dữ liệu thực tế mà `OAuth2AuthenticatedPrincipal.getAttributes()` trả về và contract thư viện/AS.

### 25.1. Chuyển kiểu có chủ đích

Nếu issuer chính thức cam kết tenant ID có thể là số nguyên hoặc chuỗi với cùng ý nghĩa, có thể chuyển một cách chặt chẽ. Ví dụ:

```java
String tenantCode(Object raw) {
    if (raw instanceof String text && !text.isBlank()) {
        return text;
    }
    if (raw instanceof Integer number) {
        return number.toString();
    }
    return null;
}
```

Nhưng với định danh có leading zero hoặc số quá lớn, chuyển kiểu có thể làm mất thông tin. Với claims dùng để phân quyền, tốt nhất issuer phát hành **một định dạng ổn định**.

### 25.2. Converter không được sửa sai policy

Nếu claim `aud` là `payments-api`, không thể “normalize” thành `orders-api`. Nếu `exp` quá hạn, không thể tăng expiry. Nếu AS không trả tenant, không thể tự gán tenant từ URL rồi coi là đã xác thực.

**Chuyển đổi kiểu** chỉ hợp lệ khi bảo toàn đúng ngữ nghĩa dữ liệu mà AS cam kết.

## 26. Multi-tenant và multi-issuer khi bọc introspector

Một hệ thống có thể chấp nhận token của hai realms:

```text
Issuer A:
  https://login.example.test/realms/shop

Issuer B:
  https://login.example.test/realms/partners
```

Mỗi issuer có thể có introspection endpoint, credentials, audience, client rules và tenant semantics riêng. **Không nên dùng một endpoint hoặc policy chung quá rộng** chỉ vì chúng cùng thuộc một máy chủ đăng nhập.

Một kiến trúc có thể:

1. Chọn giữa **những issuers đã được allowlist** thông qua một resolver đáng tin.
2. Dùng introspection client credentials phù hợp issuer/realm.
3. Delegate tới đúng introspection endpoint.
4. Chạy contract wrapper của issuer/resource.
5. Trả principal có identity đủ rõ, tránh trộn subject giữa hai issuers.
6. Áp authorization theo resource và tenant.

Nếu hai realms cùng có `sub=user-123`, đó có thể là hai accounts độc lập. Khi xét quyền sở hữu, identity thường cần cặp **(issuer, subject)** hoặc mapping nội bộ tin cậy.

Không cho caller tự định nghĩa một `introspection_uri` mới rồi yêu cầu Resource Server tin response từ đó.

## 27. Phân biệt lỗi cấu hình, lỗi contract và lỗi authorization

Một bảng chẩn đoán:

| Dấu hiệu | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| Mọi token trả 401 ngay sau khi thêm wrapper | AS không trả claim mà wrapper mới bắt buộc | So hợp đồng introspection với dữ liệu AS thực trả |
| Chỉ client mới bị 401 | `client_id` không trong allowlist | Kiểm tra client registration/policy |
| Token của Payments API gọi Orders API bị 401 | Audience bị từ chối đúng | Không mở audience để “sửa” |
| Token active nhưng 401 do tenant | Tenant token không đáp ứng contract | Xem API instance phục vụ tenant nào |
| Đột ngột lỗi timeout/5xx | AS hoặc mạng introspection gặp vấn đề | TLS/DNS/egress/timeout, không bỏ xác thực |
| Token qua wrapper nhưng GET bị 403 | Thiếu `SCOPE_orders.read` | Kiểm tra scope-to-authority |
| Token qua HTTP rule nhưng order bị 403/404 | Không đủ quyền trên object | Kiểm tra owner/tenant/share/assignment |
| Một pod nhận, pod khác từ chối | Cấu hình policy/allowlist/AS endpoint khác nhau | So rollout và cấu hình instances |
| Token bị thu hồi nhưng vẫn dùng được | Cache introspection quá lâu hoặc sai invalidation | Xem TTL/revocation design |

Không thể suy ra chỉ từ một mã HTTP rằng AS đã revoked token. Cần log/metrics nội bộ có phân loại, nhưng không lộ secrets.

## 28. Một runbook khi triển khai wrapper mới

### Bước 1 — Ghi lại hợp đồng trước khi code

Xác định field nào AS trả ổn định, field nào là optional, field nào cần kiểm tra ở Resource Server. Đặc biệt: `active`, `aud`, `iss`, `exp`, `client_id`, `tenant_id`, `scope`.

### Bước 2 — Giữ nguyên delegate introspection tin cậy

Không viết một implementation đơn giản luôn trả principal. Delegate phải kiểm tra `active`, HTTP security và AS response theo implementation.

### Bước 3 — Thêm một rule token-wide mỗi lần

Ví dụ đầu tiên kiểm tra audience; sau đó client allowlist; tiếp theo tenant. Nếu AS thiếu claim, cần **quyết định contract** chứ không âm thầm điền giá trị.

### Bước 4 — Tách authentication khỏi authorization

Một token qua wrapper không tự có quyền đọc/ghi hoặc xem mọi đối tượng. Thêm `requestMatchers(...)` và service authorization phù hợp.

### Bước 5 — Quan sát lỗi an toàn

Ghi category:

```text
request_id=req-123
authn=FAILED
component=contract_introspector
reason=INVALID_AUDIENCE
configured_audience=orders-api
route=/api/orders/{id}
```

Không log chuỗi bearer token hay HTTP Basic secret.

### Bước 6 — Kiểm tra rollout nhiều instances

Đảm bảo mọi instances cùng dùng expected issuer/audience, client allowlist, tenant policy và version của wrapper. Không để một instance fail open hoặc dùng delegate không có kiểm tra.

### Bước 7 — Tính đến hiệu năng và availability

Định nghĩa timeouts, retry có giới hạn, metrics, AS capacity, circuit breaker fail closed và caching/revocation policy phù hợp.

### Bước 8 — Kiểm tra sự cố AS

Nếu AS trả inactive hoặc mạng lỗi, API không chấp nhận token. Giữ loại lỗi nội bộ đủ rõ để xử lý vận hành.

## 29. Những sai lầm cần tránh

### Sai lầm A — `active=true` là cho phép mọi API

`active=true` không có nghĩa token dành cho Orders API. Nếu contract yêu cầu, phải kiểm tra audience/resource binding.

### Sai lầm B — Tự thay delegate bằng một principal giả

Không bỏ request introspection hoặc tự phát authorities khi AS không phản hồi. Đây là *fail open*.

### Sai lầm C — Bắt mọi exception rồi chấp nhận

Một lỗi network không chứng minh token hợp lệ. Cần từ chối khi chưa xác thực được.

### Sai lầm D — Dùng introspection credentials thay claim `client_id`

Chúng thuộc hai vai trò khác nhau. Resource Server có client credentials để gọi AS; người dùng hoặc ứng dụng gọi API có `client_id` riêng trong token.

### Sai lầm E — Kiểm tra `client_id` rồi bỏ `aud`

Client có thể xin tokens cho nhiều APIs. Client allowlist không thay audience.

### Sai lầm F — Hardcode tenant trên Resource Server đa tenant

Một token hợp lệ của tenant khác bị từ chối không cần thiết. Hãy xác định token-wide contract và object-level policy theo thiết kế.

### Sai lầm G — Cấp ROLE_ADMIN khi có một claim bất kỳ

Không tự tăng authorities. Chỉ ánh xạ quyền được AS cấp và được policy cho phép.

### Sai lầm H — Cache token active không giới hạn

Có thể chấp nhận token revoked quá lâu. TTL và invalidation là quyết định bảo mật, không chỉ hiệu năng.

### Sai lầm I — Log raw bearer token để debug

Token là credential có thể được sử dụng lại. Log ID request/điều kiện lỗi thay vì chuỗi token.

### Sai lầm J — URL introspection lấy từ token

Có thể gây SSRF và tin AS của attacker. Endpoint phải đến từ cấu hình tin cậy.

### Sai lầm K — Dùng wrapper để kiểm tra owner của một order ID

Wrapper token-wide không phù hợp cho object-specific authorization. Quyền trên order thuộc service/domain layer.

### Sai lầm L — Xem response 401 và 403 là như nhau

401 thường là authentication/token failure; 403 là đã xác thực nhưng không đủ quyền endpoint/object. Cần kiểm tra đúng lớp.

### Sai lầm M — Tắt validation khi AS nâng cấp

Nếu AS thay đổi format `aud`, `exp` hoặc `tenant_id`, cần review contract và code chuyển đổi, không bỏ kiểm tra để giảm lỗi.

### Sai lầm N — Dùng một contract cho nhiều issuers khác nghĩa claims

Claim `tenant_id` của issuer A không nhất thiết cùng namespace với issuer B. Mapping và policy phải rõ theo issuer.

## 30. Một ví dụ tách ba chính sách cho endpoint

Giả sử endpoint:

```http
GET /api/orders/order-42
Authorization: Bearer <OPAQUE_TOKEN>
```

**Chính sách 1 — Token contract (wrapper):**

```text
delegate.introspect(token) succeeds
AND aud contains orders-api
AND iss matches trusted issuer, if contract requires iss
AND client_id allowed
AND tenant_id well formed
AND exp valid when contract requires it
```

**Chính sách 2 — HTTP action authorization:**

```text
Authentication has SCOPE_orders.read
```

**Chính sách 3 — Object authorization:**

```text
order-42 belongs to an allowed tenant
AND (caller is owner OR is permitted through ACL/support assignment)
```

Ba chính sách giải quyết ba kiểu sai khác nhau:

- Token của API khác.
- Token đúng API nhưng không có quyền đọc.
- Token đúng quyền đọc nhưng request nhắm vào đơn không thuộc caller.

Cấu trúc này giúp triển khai least privilege và phân tích sự cố nhất quán.

## 31. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình introspection và tùy biến `OpaqueTokenIntrospector`.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): hợp đồng interface introspection.
- [Spring Security API — NimbusOpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/NimbusOpaqueTokenIntrospector.html): implementation delegate cho những phiên bản hỗ trợ.
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): attributes, principal name và authorities.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, cấu trúc introspection request/response, protected resources và thông tin trả về.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token transport, authentication/authorization errors.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token hướng đến resource thích hợp.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, scopes và phân quyền.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): quyền trên từng đối tượng API.

**Kết luận:** Bọc `OpaqueTokenIntrospector` bằng một decorator giúp Resource Server **giữ nguyên introspection chuẩn của Authorization Server** và bổ sung các ràng buộc như audience, issuer, client, tenant, thời gian hoặc profile theo hợp đồng. Wrapper phải **fail closed** khi delegate hoặc rule thất bại, giữ nguyên quyền nếu không có lý do và hợp đồng để thay đổi, không log bearer credentials, không dùng claims tự tạo để hợp thức hóa token sai. Sau khi token được xác thực, HTTP/method authorization và service-level object policy vẫn quyết định caller được thao tác **endpoint và đối tượng nào**.
