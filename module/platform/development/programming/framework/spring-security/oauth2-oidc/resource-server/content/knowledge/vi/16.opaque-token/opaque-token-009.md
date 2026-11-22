# Ánh xạ scope từ phản hồi introspection sang quyền

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, access token không nhất thiết phải là JWT mà API có thể đọc và kiểm tra chữ ký tại chỗ. Một Authorization Server (AS) có thể phát hành **opaque access token**: đối với Resource Server, đó chỉ là một chuỗi credential. Để biết token còn hoạt động và đã được cấp quyền gì, Resource Server gọi **OAuth 2.0 Token Introspection Endpoint** theo RFC 7662.

Phản hồi introspection thường cung cấp các thuộc tính như `active`, `sub`, `client_id`, `aud`, `exp` và đặc biệt là **`scope`**. Spring Security có thể biến từng OAuth scope đã được xác thực qua introspection thành một **`GrantedAuthority`** với tiền tố mặc định `SCOPE_`. Các luật như `hasAuthority("SCOPE_orders.read")` hoặc `@PreAuthorize("hasAuthority('SCOPE_orders.write')")` nhờ đó hoạt động với opaque token mà không cần API biết token có cấu trúc nội bộ ra sao.

Điều quan trọng cần hiểu: **`active: true` chỉ cho biết token được Authorization Server xem là còn hoạt động; nó không tự trao mọi quyền cho mọi API**. Resource Server vẫn chịu trách nhiệm xác định token dành cho tài nguyên nào, scope nào phù hợp với thao tác, và người gọi có quyền trên đối tượng nghiệp vụ cụ thể hay không.

Bài học đi theo chuỗi **introspection response → principal → `GrantedAuthority` → authorization** và trình bày các biến thể của `scope`, cấu hình mặc định, tùy biến mapping, lỗi thường gặp, kiểm thử và những giới hạn vận hành.

## 1. Bức tranh toàn cảnh: từ opaque token đến quyền truy cập

Một client có access token được cấp bởi Authorization Server và muốn đọc đơn hàng ở Orders API:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as Orders Resource Server
    participant AS as Authorization Server
    C->>API: GET /api/orders/123 + Bearer opaque-token
    API->>AS: POST /introspect (token + RS credentials)
    AS->>AS: Kiểm tra token và chính sách hiệu lực
    AS-->>API: active=true, scope="orders.read", aud="orders-api", sub=...
    API->>API: Chuyển orders.read -> SCOPE_orders.read
    API->>API: Tạo Authentication với authorities
    API->>API: Kiểm tra hasAuthority("SCOPE_orders.read")
    API->>API: Kiểm tra owner/tenant của order 123
    API-->>C: 200 nếu cả xác thực và phân quyền đều đúng
```

Phân vai:

| Thành phần | Chịu trách nhiệm | Không nên làm thay phần khác |
|---|---|---|
| **Client** | Xin access token với scopes phù hợp, gửi Bearer credential | Không được tự quyết scope đã cấp |
| **Authorization Server** | Phát hành token, quản lý hiệu lực và trả introspection metadata | Không tự quyết quyền trên mọi bản ghi trong Orders API nếu không có hợp đồng |
| **Introspection endpoint** | Cho Resource Server biết token active và metadata đáng tin theo hợp đồng | Không phải endpoint public cho mọi caller vô danh |
| **`OpaqueTokenIntrospector`** | Gọi endpoint, xử lý phản hồi, tạo principal | Không thay thế HTTP/domain authorization |
| **`GrantedAuthority`** | Biểu diễn quyền trong Authentication của Spring Security | Không tự có ý nghĩa OAuth hay ownership nếu ứng dụng chưa quy ước |
| **HTTP/method authorization** | Quyết định scope/authority nào được dùng endpoint | Không tự xác định owner và tenant của record |
| **Business service** | Áp quyền tài nguyên, tenant, trạng thái và quy tắc nghiệp vụ | Không tin payload từ client để thay metadata token đã xác thực |

Một token có thể hợp lệ nhưng chỉ được cấp `orders.read`; request ghi cần `orders.write` vẫn bị từ chối. Một token có đủ `orders.read` vẫn không tự cho phép đọc đơn hàng của người dùng khác.

## 2. Token introspection theo RFC 7662

### 2.1. Request tới introspection endpoint

Đường dẫn và cơ chế xác thực của AS do hệ thống quy định. Ví dụ một request HTTP theo RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=opaque-value-from-authorization-header
```

Đây là **mẫu giao thức** chứ không phải thông tin đăng nhập thật. Spring Security thường đảm nhiệm việc gọi introspection endpoint khi cấu hình opaque Resource Server; ứng dụng không cần tự dựng HTTP request cho mỗi controller.

Trong triển khai thực tế:

- Chỉ gọi introspection endpoint đáng tin, qua **HTTPS/TLS**.
- Resource Server dùng một phương thức xác thực client được Authorization Server cho phép, ví dụ HTTP Basic với client ID/secret, hoặc phương thức khác theo hợp đồng.
- Bảo vệ client secret bằng secret manager hoặc cấu hình an toàn; không ghi vào Git hay log.
- Không chuyển chuỗi bearer token vào URL/query string hoặc log request.
- Cân nhắc timeout, sự cố mạng và lượng request vì introspection có thể nằm trên đường nóng của mỗi HTTP request.

### 2.2. Phản hồi introspection active

Phản hồi minh họa:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "iat": 1893456000,
  "exp": 1893459600
}
```

Các thời điểm chỉ minh họa. Trong RFC 7662:

- `active` là thuộc tính **bắt buộc** của response, cho biết trạng thái active theo AS.
- `scope` là một **chuỗi scope cách nhau bằng dấu cách**, tương tự cách biểu diễn scope trong OAuth 2.0.
- `client_id`, `sub`, `aud`, `iss`, `exp`, `iat`, `nbf` và các thuộc tính khác có thể xuất hiện tùy AS và chính sách tiết lộ metadata.
- Không phải mọi AS đều trả mọi trường cho mọi Resource Server; phản hồi có thể được giới hạn theo người gọi introspection.

Các scope `orders.read` và `orders.write` là **giá trị được AS xác nhận đã cấp**, khác với việc client từng gửi tham số `scope=orders.write` khi xin token. Resource Server phải quyết định quyền dựa trên dữ liệu đã được xác thực từ AS, không dựa trên request xin scope của client.

### 2.3. Phản hồi token không active

Ví dụ:

```json
{
  "active": false
}
```

Theo RFC 7662, đối với token không active, endpoint thường chỉ cần trả `active: false` mà không tiết lộ thêm metadata. Điều này tránh cho bên introspect suy ra thông tin về token không có quyền biết.

Resource Server **không được** tạo một authenticated principal có quyền từ token như vậy, ngay cả khi client gửi thêm scope ở header tùy biến:

```http
Authorization: Bearer invalid-token
X-Scope: orders.write
```

`X-Scope` trong ví dụ là dữ liệu do caller kiểm soát, không thuộc hợp đồng xác thực; nó không thể biến token `active=false` thành một token được phép ghi.

### 2.4. Introspection không nhất thiết cho biết token là chuỗi “vô nghĩa”

Opaque Resource Server trong Spring Security có nghĩa **API xác thực bằng introspection** thay vì tự xác minh JWT bằng `JwtDecoder`. Credential thực tế có thể là:

- Một reference token ngẫu nhiên mà chỉ AS biết bản ghi tương ứng.
- Một JWT nhưng Resource Server chọn yêu cầu AS kiểm tra trạng thái/thu hồi.
- Một token có định dạng riêng của nhà cung cấp.

Vì vậy, khi nói “opaque token”, ta nhấn mạnh **cách Resource Server xử lý**, không mặc định kết luận token không thể chứa dữ liệu có cấu trúc. Nếu AS dùng token JWT nhưng introspection endpoint nhận nó, Resource Server vẫn có thể dùng tuyến opaque thay vì tự decode.

## 3. Scope trong phản hồi introspection có ý nghĩa gì?

Scope là một khái niệm của OAuth 2.0: một tập chuỗi biểu diễn **phạm vi truy cập được cấp cho access token**. Ý nghĩa các chuỗi như `orders.read` và `payments.refund` do Authorization Server và Resource Server thống nhất.

Ví dụ hợp đồng:

| Scope được AS cấp | Chức năng Orders API cho phép | Authority mặc định |
|---|---|---|
| `orders.read` | Xem đơn hàng mà chủ thể được phép đọc | `SCOPE_orders.read` |
| `orders.create` | Tạo đơn mới theo business policy | `SCOPE_orders.create` |
| `orders.update` | Cập nhật đơn hợp lệ, đúng owner/tenant | `SCOPE_orders.update` |
| `orders.cancel` | Yêu cầu hủy đơn theo trạng thái và quyền | `SCOPE_orders.cancel` |
| `orders.delete` | Xóa tài nguyên theo quy định | `SCOPE_orders.delete` |

Đây là **tên scope giả định**. Spring Security không tự tạo `orders.cancel` chỉ vì endpoint dùng POST hoặc vì tài nguyên có trạng thái `CANCELLED`.

### 3.1. Scope là chuỗi phân biệt chữ hoa/thường

Theo OAuth, scope token là các giá trị phân biệt chữ hoa/thường. Những giá trị sau **không tự tương đương**:

```text
orders.read
Orders.Read
orders.READ
```

Spring Security kiểm tra `GrantedAuthority#getAuthority()` bằng tên mà policy yêu cầu. Nếu token được cấp `Orders.Read` thì converter mặc định có thể tạo `SCOPE_Orders.Read`; rule `hasAuthority("SCOPE_orders.read")` sẽ không khớp.

Không tự lower-case mọi scope trừ khi hợp đồng issuer và API quy định ánh xạ đó rõ ràng; việc chuẩn hóa không nhất quán có thể mở quyền sai.

### 3.2. Scope không có hierarchy tự động

OAuth không quy định:

```text
orders.write -> bao hàm orders.read
orders.admin -> bao hàm toàn bộ orders.*
```

Spring Security cũng không tự hiểu dấu chấm trong tên scope là quan hệ cha-con. Nếu API yêu cầu `SCOPE_orders.read` thì token chỉ có `SCOPE_orders.write` không mặc nhiên thỏa. Muốn cho phép một trong hai quyền, policy phải ghi rõ, ví dụ `hasAnyAuthority("SCOPE_orders.read", "SCOPE_orders.write")`.

### 3.3. Scope khác audience, subject và tenant

Một token có thể có:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "aud": ["payments-api"],
  "iss": "https://idp.example.com/realms/shop"
}
```

Dù scope đọc đơn hàng hiện diện, Orders API **không được** bỏ qua việc token đang dành cho `payments-api`. Kiểm tra audience trả lời “token dành cho API nào”; scope trả lời “được làm loại thao tác gì”.

Tương tự:

- `sub` cho biết chủ thể theo ngữ nghĩa của AS, không mặc định là user tương tác.
- `client_id` cho biết client được cấp token, không tự đại diện role admin.
- `tenant_id` (claim mở rộng) cần nguồn tin cậy và business policy riêng.
- `scope` không chứa danh sách tất cả order IDs mà chủ thể được xem, trừ khi hệ thống thiết kế một hợp đồng cực kỳ cụ thể.

## 4. Mapping mặc định của Spring Security: `scope` → `SCOPE_...`

Trong Spring Security Servlet Resource Server sử dụng opaque-token introspection, đường xử lý thường gặp là:

```mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["OpaqueTokenAuthenticationProvider"]
    C --> D["OpaqueTokenIntrospector"]
    D --> E["HTTPS introspection endpoint"]
    E --> F{"active có đúng và<br/>response hợp lệ?"}
    F -->|"Không"| X["Authentication thất bại / 401"]
    F -->|"Có"| G["OAuth2AuthenticatedPrincipal<br/>attributes + authorities"]
    G --> H["BearerTokenAuthentication"]
    H --> I["SecurityContextHolder"]
    I --> J{"hasAuthority('SCOPE_orders.read')?"}
    J -->|"Không"| Y["Authorization thất bại / 403"]
    J -->|"Có"| K["Controller / domain authorization"]
```

Spring Security opaque-token support mặc định **trích xuất `scope` từ introspection response và ánh xạ thành authorities với tiền tố `SCOPE_`**. Với response:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

ta mong đợi Authentication của request có:

```text
GrantedAuthority("SCOPE_orders.read")
GrantedAuthority("SCOPE_orders.write")
```

Các authorities là đối tượng Spring Security, không phải các claim được AS gửi kèm tiền tố `SCOPE_`. AS chỉ cần trả scope raw theo hợp đồng:

```text
orders.read orders.write
```

**Đừng tự thêm `SCOPE_` vào từng scope do AS phát hành** khi đang dùng mapping mặc định. Nếu AS trả `SCOPE_orders.read`, quy tắc mapping có thể tạo `SCOPE_SCOPE_orders.read` và policy `hasAuthority("SCOPE_orders.read")` không khớp.

### 4.1. Một scope khác một authority

Ví dụ phản hồi:

```json
{
  "active": true,
  "scope": "orders.read orders.create reports.read"
}
```

Mapping mặc định tạo ba authorities:

```text
SCOPE_orders.read
SCOPE_orders.create
SCOPE_reports.read
```

Một endpoint chỉ yêu cầu `SCOPE_orders.read` không tự cho phép `reports.read`, và ngược lại. Việc có nhiều authorities trong Authentication chỉ là thông tin đầu vào cho authorization rules; không có cơ chế cấp quyền mọi route vì token có ít nhất một scope.

### 4.2. Scope trống hoặc không tồn tại

Response:

```json
{
  "active": true,
  "sub": "user-842"
}
```

Nếu không có scope và introspector không gán authority tùy biến, Authentication có thể **được xác thực** nhưng **không có bất kỳ `SCOPE_orders.read` nào**. Khi đó:

```java
.hasAuthority("SCOPE_orders.read")
```

phải từ chối. Đừng vì `active=true` mà tự thêm `SCOPE_orders.read` để “cho API hoạt động”. Nếu API bắt buộc mọi access token phải chứa scope, có thể bổ sung kiểm tra hợp đồng và từ chối token thiếu scope.

### 4.3. `scope` dạng chuỗi, `scp` dạng mảng và biến thể nhà cung cấp

Trong RFC 7662, `scope` là **chuỗi các giá trị scope phân cách bằng dấu cách**. Ví dụ:

```json
{
  "active": true,
  "scope": "orders.read orders.update"
}
```

Một số nhà cung cấp khác dùng response:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.update"]
}
```

hoặc:

```json
{
  "active": true,
  "permissions": ["order:read", "order:write"]
}
```

Hai biến thể sau **không phải yêu cầu mapping mặc định của RFC 7662**. Không nên mặc định `OpaqueTokenIntrospector` sẽ tự hiểu mọi field `scp`, `roles` hoặc `permissions` của mọi IdP. Khi dùng field khác, nhóm phát triển phải:

1. Xác nhận field được IdP xác thực và trả về chỉ cho Resource Server có quyền.
2. Thống nhất ngữ nghĩa, định dạng và giá trị có thể xuất hiện.
3. Chọn custom introspector/authority mapping phù hợp.
4. Kiểm tra kết quả `GrantedAuthority` thực tế, không đoán từ tên field.

Phải tránh biến một claim bất kỳ từ response thành role quyền cao nếu chưa được quy định rõ là nguồn cấp quyền.

## 5. Cấu hình opaque Resource Server trên Spring Boot

Ví dụ dùng Spring Boot 3.x/Spring Security Servlet:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

`INTROSPECTION_CLIENT_SECRET` phải được cung cấp bởi cấu hình an toàn ở môi trường triển khai; không ghi secret thật vào file được commit. URL là ví dụ, cần thay bằng endpoint đúng của AS.

Khi cấu hình này được Spring Boot hỗ trợ và không bị một bean custom thay thế, Boot có thể tự cung cấp `OpaqueTokenIntrospector` phù hợp. Spring Security sử dụng introspector trong nhánh `opaqueToken()` để xác thực Bearer credential.

Ví dụ phân quyền:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Chỉ minh họa cho API thuần Bearer header, không dùng
            // cookie/session làm credential của request thay đổi trạng thái.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/health")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Cách hoạt động:

1. `BearerTokenAuthenticationFilter` lấy token từ `Authorization: Bearer ...`.
2. `OpaqueTokenAuthenticationProvider` gọi `OpaqueTokenIntrospector`.
3. Introspector gửi token đến endpoint đáng tin, kiểm tra phản hồi theo cơ chế của thư viện.
4. Principal trả về chứa attributes và authorities; scope mặc định thành `SCOPE_...`.
5. Spring Security tạo `BearerTokenAuthentication` và đưa vào `SecurityContext`.
6. `authorizeHttpRequests` kiểm tra authority theo method/path.
7. Business service kiểm tra quyền với đơn hàng cụ thể.

**Lưu ý:** cấu hình `csrf().disable()` ở đây chỉ hợp lý với API thực sự dùng bearer token trong header do client chủ động gửi, không dựa vào cookie/session browser tự đính kèm. Khi app có cookie login hoặc state-changing browser requests theo cơ chế khác, CSRF cần được thiết kế riêng.

### 5.1. HTTP rule không tự gọi introspection

Đoạn:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

chỉ kiểm tra authorities đã có trong `Authentication`. Nó **không tự gửi token đến IdP**. Phần gửi token và tạo Authentication do `opaqueToken()` cùng `OpaqueTokenIntrospector` phụ trách. Nếu chain đang dùng `jwt()`, nó có thể xử lý token theo `JwtDecoder` thay vì introspection, trừ khi ứng dụng tùy chỉnh rõ.

### 5.2. Không bật đồng thời JWT/opaque chỉ để “thử xem token nào chạy”

Spring Security có hai đường Bearer authentication chính cho Resource Server: JWT decoder và opaque introspector. Cần **chọn chiến lược theo hợp đồng token**; không giả định cứ bật cả hai là framework sẽ tự fallback an toàn khi một parser thất bại.

Nếu API cần nhiều token profile, nên định tuyến qua thiết kế xác thực được kiểm soát, giữ issuer/audience/token type checks ở mỗi nhánh. Một cơ chế “JWT không hợp lệ thì thử introspection ở nhánh lỏng hơn” có thể gây lỗi downgrade/cross-protocol confusion.

## 6. `BearerTokenAuthentication` và các đối tượng có thể đọc

Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal`, chứa introspection attributes và authorities. Authentication sau khi xác thực thường là `BearerTokenAuthentication`.

Một số kiểu liên quan:

```text
OpaqueTokenIntrospector
    |
    v
OAuth2AuthenticatedPrincipal
  - getName()
  - getAttributes()
  - getAttribute(name)
  - getAuthorities()
    |
    v
BearerTokenAuthentication
  - getPrincipal()
  - getAuthorities()
  - getCredentials()
  - getName()
```

API thường chỉ cần `Authentication` hoặc `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` thay vì phụ thuộc vào class implementation của introspector.

### 6.1. Lấy authorities trong controller

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentAccessController {

    @GetMapping("/api/me/authorities")
    public List<String> currentAuthorities(Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
    }
}
```

Nếu introspection trả `scope: "orders.read orders.update"`, kết quả từ API minh họa có thể là:

```json
[
  "SCOPE_orders.read",
  "SCOPE_orders.update"
]
```

Đây là endpoint dành cho minh họa/quan sát. Trong production, không nhất thiết nên công khai toàn bộ thông tin quyền; nếu có, phải bảo vệ route phù hợp và tránh trả về metadata nhạy cảm khác từ introspection.

### 6.2. Đọc attributes từ OAuth2AuthenticatedPrincipal

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
public Map<String, String> currentActor(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String subject = principal.getAttribute("sub");
    String clientId = principal.getAttribute("client_id");

    return Map.of(
        "name", principal.getName(),
        "subject", subject != null ? subject : "",
        "clientId", clientId != null ? clientId : ""
    );
}
```

Ví dụ chỉ chọn vài field để minh họa; không trả nguyên `principal.getAttributes()` vì có thể có metadata nhạy cảm của token. Kiểu dữ liệu thực tế của attributes phụ thuộc introspection endpoint và cách thư viện chuyển đổi. `Authentication.getName()` hoặc `principal.getName()` không mặc định là email, và với client credentials không nên suy ra là người dùng.

**JWT khác opaque:** `@AuthenticationPrincipal Jwt` phù hợp ở nhánh JWT, nhưng không mặc định phù hợp khi `BearerTokenAuthentication` chứa `OAuth2AuthenticatedPrincipal`. Muốn code business dùng chung, chuyển cả hai loại principal sang một kiểu actor nội bộ đã kiểm chứng.

### 6.3. `GrantedAuthority` trong Authentication không thay đổi metadata token

Nếu một authority converter thêm `ROLE_ORDER_MANAGER` thì token/response introspection vẫn giữ nguyên. Converter chỉ tạo biểu diễn **quyền bên trong Spring Security**, không gửi yêu cầu nâng scope tới AS, không đổi `scope` và không cấp credential mới cho client.

## 7. `hasAuthority`, `hasRole` và giới hạn của quyền

Spring Security dùng chuỗi trong `GrantedAuthority#getAuthority()` để so với rule. Ví dụ:

```java
.hasAuthority("SCOPE_orders.read")
```

tìm authority chính xác `SCOPE_orders.read`.

Trong khi:

```java
.hasRole("ADMIN")
```

thường tìm `ROLE_ADMIN` theo convention role prefix của Spring Security. Vì vậy:

```java
.hasRole("orders.read")            // thường tìm ROLE_orders.read
.hasAuthority("SCOPE_orders.read") // kiểm tra OAuth scope mapping
```

Hai kiểm tra trên không tương đương. Khi muốn kiểm tra OAuth scope được mapping mặc định, dùng `hasAuthority("SCOPE_...")` là cách diễn đạt rõ ràng.

### 7.1. Đừng coi `scope` là `role`

Một IdP có thể phát hành:

```json
{
  "active": true,
  "scope": "orders.read",
  "roles": ["ADMIN"]
}
```

Đây là hai nguồn dữ liệu khác nhau. `roles` không tự trở thành `ROLE_ADMIN` trong opaque support mặc định trừ khi application có mapping rõ. Nếu một extension ánh xạ role, phải kiểm tra:

- Claim `roles` có thực sự được Authorization Server xác nhận dành cho Resource Server này không?
- Role này thuộc domain/tenant nào?
- Giá trị `ADMIN` là quyền admin của cả API hay chỉ một client/realm?
- Có cần kết hợp với OAuth scope cho thao tác nhạy cảm không?

Không xây rule “mọi user có role ADMIN trong IdP được refund tất cả payments” nếu app chưa định nghĩa và bảo vệ phạm vi đó.

### 7.2. Quyền trên từng object vẫn phải kiểm tra

Token có:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "tenant_id": "tenant-a"
}
```

Database:

```text
Order ORD-123:
  owner=user-842
  tenant=tenant-a

Order ORD-999:
  owner=user-901
  tenant=tenant-b
```

`SCOPE_orders.read` cho phép **loại chức năng đọc**, không đồng nghĩa được xem mọi order. Service cần kiểm tra owner, tenant và trạng thái thực tế. Nếu chỉ có `hasAuthority` mà không có kiểm tra object-level, API có nguy cơ BOLA (*Broken Object Level Authorization*).

## 8. Method Security sử dụng cùng authorities

Sau khi bật method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

có thể dùng:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String id) {
        return readWithBusinessChecks(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.update')")
    public OrderDto updateOrder(String id, UpdateOrderCommand command) {
        return updateWithBusinessChecks(id, command);
    }
}
```

Các kiểu `OrderDto`, `UpdateOrderCommand` và các method nội bộ là phần domain minh họa. `@PreAuthorize` được đánh giá trước khi method đi vào logic nghiệp vụ (khi lời gọi đi qua proxy), nhưng service vẫn phải kiểm tra owner/tenant và trạng thái order.

`@EnableMethodSecurity` không phân biệt authorities này đến từ JWT, opaque token hay hệ thống khác: nó đọc `Authentication` trong `SecurityContextHolder`. Vì thế cùng một `@PreAuthorize` có thể dùng cho cả hai nhánh, miễn là **mapping quyền và semantics đã được thiết kế nhất quán**.

**Lưu ý proxy:** với Spring AOP proxy thông thường, self-invocation có thể bỏ qua method-security interceptor. Không xem annotation là đảm bảo cho mọi lời gọi nội bộ nếu chúng không qua proxy hoặc domain authorization boundary.

## 9. Tùy biến introspection mà vẫn giữ scope mặc định

Có thể AS trả một số metadata bổ sung, ví dụ:

```json
{
  "active": true,
  "scope": "orders.read",
  "permissions": ["order:approve"],
  "sub": "manager-842",
  "aud": ["orders-api"]
}
```

Ứng dụng muốn giữ `SCOPE_orders.read` và thêm authority nội bộ `PERMISSION_order:approve` khi AS xác nhận một permission đã được duyệt.

Spring Security cho phép cung cấp **`OpaqueTokenIntrospector` riêng**. Một cách tổ chức là **ủy quyền cho introspector chuẩn**, giữ nguyên principal/authorities đã được nó xác minh rồi bổ sung mapping hạn chế.

### 9.1. Bọc introspector chuẩn thay vì thay mọi xử lý

Ví dụ Java với `NimbusOpaqueTokenIntrospector` (một implementation phổ biến trong Spring Security 6.x; class/builder có thể thay đổi theo phiên bản):

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PermissionEnrichingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public PermissionEnrichingIntrospector(OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate chịu trách nhiệm xác thực token qua AS.
        OAuth2AuthenticatedPrincipal principal = delegate.introspect(token);

        // Giữ nguyên SCOPE_... authorities từ introspection chuẩn.
        Collection<GrantedAuthority> authorities =
            new ArrayList<>(principal.getAuthorities());

        // Chỉ nhận quyền đã được hợp đồng quy định.
        Object raw = principal.getAttribute("permissions");
        if (raw instanceof Collection<?> permissions) {
            for (Object permission : permissions) {
                if ("order:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_order:approve"));
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            List.copyOf(authorities)
        );
    }
}
```

Các đặc điểm:

1. **Delegate introspection trước**, không lấy thông tin scope từ token raw chưa xác thực.
2. **Giữ `principal.getAuthorities()`** nên `SCOPE_orders.read` không biến mất.
3. Chỉ ánh xạ permission cụ thể `order:approve`, không cho mọi giá trị tùy ý thành quyền admin.
4. Không thay đổi attributes, danh tính hoặc token tại Authorization Server.
5. Trả về một `OAuth2AuthenticatedPrincipal` phù hợp cho `BearerTokenAuthentication`.

Đây là **mẫu minh họa mapping từ metadata IdP đã tin cậy**, không phải lời khuyên cấp quyền phê duyệt đơn cho mọi AS. Trước khi triển khai, hợp đồng phải xác nhận `permissions` trong introspection response là nguồn tin cậy, do AS quản trị và ràng buộc đúng audience/tenant.

### 9.2. Cấu hình delegate và wrapper

Ví dụ tạo introspector từ thông tin cấu hình:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.security.introspection-uri}") String uri,
            @Value("${app.security.introspection-client-id}") String clientId,
            @Value("${app.security.introspection-client-secret}") String secret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, clientId, secret);

        return new PermissionEnrichingIntrospector(delegate);
    }
}
```

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Đoạn mã sử dụng constructor của `NimbusOpaqueTokenIntrospector` được cung cấp trong các dòng Spring Security 6.x phổ biến; khi ứng dụng sử dụng một phiên bản mới hơn hoặc thay bằng `SpringOpaqueTokenIntrospector`, cần chọn API/builder được phiên bản đó hỗ trợ. Ý tưởng **delegate + wrapper** không phụ thuộc tên class cụ thể.

Khi application khai báo một bean `OpaqueTokenIntrospector`, Spring Boot thường nhường việc auto-config introspector cho bean đó. Cần đảm bảo security chain thực sự dùng custom bean:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        OpaqueTokenIntrospector introspector) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

Ví dụ này nối explicit introspector vào `SecurityFilterChain`; imports và cách cấu hình những phần khác của security vẫn theo application thực tế. Nếu app có nhiều chains, cần kiểm tra đúng chain và introspector được dùng ở route cụ thể.

### 9.3. Khi muốn đổi tất cả scopes thành prefix khác

Giả sử IdP trả:

```json
{
  "active": true,
  "scope": "orders.read"
}
```

và ứng dụng cố ý tạo authority `RIGHT_orders.read` thay vì `SCOPE_orders.read`. Việc này đòi mapping tùy chỉnh; các rule cũng phải đổi tương ứng:

```java
.hasAuthority("RIGHT_orders.read")
```

Nếu chỉ đổi converter nhưng quên đổi `hasAuthority("SCOPE_orders.read")`, request có token hợp lệ có thể trả 403 vì authority không trùng. Thông thường **giữ tiền tố `SCOPE_` là lựa chọn rõ ràng và ít bất ngờ** đối với Resource Server.

Không được đổi prefix để che việc IdP trả thiếu scope; prefix là chi tiết biểu diễn trong Spring Security, không phải chứng cứ cấp quyền.

## 10. IdP trả `scp` hoặc format khác: mapping rõ hợp đồng

Một số nhà cung cấp không trả `scope` theo RFC 7662, mà trả `scp` dạng list. Ví dụ:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.update"],
  "aud": ["orders-api"]
}
```

Nếu introspector mặc định chỉ mapping `scope`, Authentication có thể không có `SCOPE_orders.read` mặc dù `scp` hiện diện. Một custom wrapper có thể đọc `scp` **sau khi introspection thành công**, tạo authorities phù hợp.

Mẫu khái niệm:

```java
Object rawScp = principal.getAttribute("scp");
Collection<GrantedAuthority> authorities =
    new ArrayList<>(principal.getAuthorities());

if (rawScp instanceof Collection<?> scopes) {
    for (Object item : scopes) {
        if (item instanceof String scope
                && (scope.equals("orders.read")
                    || scope.equals("orders.update"))) {
            authorities.add(new SimpleGrantedAuthority("SCOPE_" + scope));
        }
    }
}
```

Mẫu này cần nằm bên trong một `OpaqueTokenIntrospector` wrapper đã gọi delegate và chỉ áp khi AS được tin cậy thực sự sử dụng `scp` với ngữ nghĩa scope. `principal` trong code là kết quả từ `delegate.introspect(token)`, **không** phải JSON do client cung cấp.

### 10.1. Tránh gộp scope mù quáng từ nhiều claim

Nếu AS trả đồng thời:

```json
{
  "active": true,
  "scope": "orders.read",
  "scp": ["orders.delete"]
}
```

phải biết:

- Claim nào là authoritative?
- Hai claim mang cùng nghĩa hay khác ngữ cảnh?
- `scp` được giới thiệu để tương thích với token profile nào?
- Có được phép **cộng** quyền từ cả hai nguồn không?

Nếu app mù quáng hợp nhất, một field không được dự định cấp quyền cho API có thể vô tình cấp `SCOPE_orders.delete`. Chỉ hợp nhất khi AS và API đã quy định rõ semantics; nếu không, chọn một nguồn được kiểm soát và từ chối response không nhất quán theo policy.

### 10.2. Khi scope là mảng trong trường `scope`

Một số AS trả:

```json
{
  "active": true,
  "scope": ["orders.read", "orders.write"]
}
```

Đây không phải biểu diễn `scope` dạng chuỗi theo RFC 7662. Không giả định mọi implementation introspector chấp nhận hoặc chuẩn hóa nó. Có thể:

- Điều chỉnh cấu hình AS để trả chuỗi chuẩn.
- Dùng một client/wrapper hỗ trợ format đặc thù với ràng buộc nghiêm ngặt.
- Từ chối response sai hợp đồng nếu hệ thống yêu cầu tuân thủ chuẩn.

Không chuyển tùy ý mọi JSON array thành quyền mà không kiểm tra kiểu, allowed values và audience.

### 10.3. Scope có dấu cách, dấu phẩy, dấu hai chấm

Trong một response chuẩn:

```json
{ "scope": "orders.read orders.write" }
```

**Dấu cách** phân tách scope tokens. `orders.read` và `orders.write` là hai giá trị; dấu chấm nằm trong tên scope.

Response:

```json
{ "scope": "orders.read,orders.write" }
```

không phải hai scope phân tách bằng dấu phẩy theo biểu diễn RFC 7662; nếu một IdP dùng dấu phẩy, cần quy ước parsing riêng, không tự giả định converter mặc định sẽ tách đúng. Ngược lại, scope như `orders:read` hoàn toàn có thể là **một tên scope hợp lệ** nếu AS/API thống nhất.

## 11. Audience và issuer: active scope chưa đủ để tin token

Giả sử hệ thống có Orders API và Payments API cùng dùng một Authorization Server. Introspection trả:

```json
{
  "active": true,
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
```

Orders API vẫn phải từ chối theo hợp đồng audience. **Một access token active và có scope giống tên quyền của Orders API không tự biến thành token dành cho Orders API**.

### 11.1. Khác biệt giữa JWT decoder và opaque introspector

Với JWT, ứng dụng thường dùng `JwtValidators.createDefaultWithIssuer(...)` và audience validator. Với opaque introspection, API nhận metadata từ AS; cơ chế kiểm tra `aud`, `iss`, thời gian và token type phụ thuộc **hợp đồng introspection và implementation**.

Không được giả định mọi custom `OpaqueTokenIntrospector` tự động áp các property `spring.security.oauth2.resourceserver.jwt.issuer-uri` hay `jwt.audiences`. Chúng thuộc cấu hình JWT decoder, không tự áp vào opaque introspection chain.

Nếu Resource Server yêu cầu `aud=orders-api`, cần:

- AS/introspection endpoint xác nhận token chỉ được introspect cho resource phù hợp; hoặc
- Resource Server kiểm tra `aud` từ metadata đáng tin theo hợp đồng; hoặc
- Kết hợp hai điều kiện theo chính sách.

Nếu AS không trả audience nhưng API cần ràng buộc audience, phải **bổ sung hợp đồng với AS**, không tự bỏ audience check chỉ để request thành công.

### 11.2. Wrapper kiểm tra audience

Ví dụ logic kiểm tra audience sau introspection:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object rawAudience = principal.getAttribute("aud");
        boolean allowed =
            (rawAudience instanceof String value
                && requiredAudience.equals(value))
            || (rawAudience instanceof Collection<?> values
                && values.contains(requiredAudience));

        if (!allowed) {
            throw new BadOpaqueTokenException(
                "Introspected token audience is not accepted");
        }
        return principal;
    }
}
```

Giả định AS có thể trả `aud` bằng chuỗi hoặc collection; logic **fail closed** nếu thiếu audience hoặc không khớp. Trong thực tế cần xét audience URI/định danh đúng hợp đồng, token type/issuer và các claim quan trọng khác. `BadOpaqueTokenException` biểu diễn token không được chấp nhận trong nhánh introspection, để framework xử lý như authentication failure.

Lưu ý code kiểm tra audience **sau** khi delegate đã xác thực token qua AS. Không lấy `aud` từ chuỗi opaque token raw, không gọi một JWT parser trên chuỗi rồi coi claim chưa xác minh là đáng tin.

### 11.3. Client credentials không luôn có user subject

Với token cấp cho một backend service:

```json
{
  "active": true,
  "client_id": "nightly-order-job",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

AS có thể không trả `sub` theo cùng ngữ nghĩa người dùng tương tác, tùy token profile và giao thức. Cần định nghĩa actor là **service principal/client identity** trong trường hợp client credentials, thay vì mặc định “không có `sub` nghĩa là anonymous” hoặc “`client_id` có scope read thì được xem mọi order của mọi tenant”.

## 12. Giữ phân quyền nghiệp vụ sau khi mapping authority

Sau khi introspection và mapping, controller/service nhận `Authentication` với các authorities tin cậy trong phạm vi hợp đồng. Nhưng business service vẫn phải kiểm tra quyền đối với đối tượng.

Giả sử token:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-842",
  "iss": "https://idp.example.com/realms/shop",
  "tenant_id": "tenant-a",
  "aud": ["orders-api"]
}
```

Một actor nội bộ:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

Ví dụ service method khi được gọi sau HTTP authority check:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public OrderDto readOrder(Authentication authentication, String orderId) {
    OAuth2AuthenticatedPrincipal principal =
        (OAuth2AuthenticatedPrincipal) authentication.getPrincipal();

    CurrentActor actor = new CurrentActor(
        principal.getAttribute("iss"),
        principal.getAttribute("sub"),
        principal.getAttribute("tenant_id")
    );

    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean sameTenant = order.getTenantId().equals(actor.tenantId());
    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer())
        && order.getOwnerSubject().equals(actor.subject());

    if (!sameTenant || !isOwner) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

`Order`, `OrderDto`, `repository`, `mapper` và các exceptions là thành phần domain minh họa. Trong ứng dụng thật, nên đóng gói việc chuyển từ principal sang actor vào adapter an toàn, kiểm tra thiếu claim/kiểu principal và chỉ chấp nhận metadata từ introspection endpoint tin cậy.

Không dùng request body/header do client cung cấp như `X-Tenant-ID` để **thay thế** tenant đã được xác thực. Nếu client được chọn tenant hoạt động, cần kiểm tra tenant được chọn có thuộc tập quyền thực sự của principal theo hợp đồng.

### 12.1. Có thể kiểm tra quyền ngay trong query

Với API nhiều tenant, thay vì đọc mọi order rồi mới kiểm tra:

```java
repository.findByIdAndOwnerIssuerAndOwnerSubjectAndTenantId(
    orderId,
    actor.issuer(),
    actor.subject(),
    actor.tenantId());
```

Query scoped by actor giúp không tải nhầm row của người khác. Dù áp dụng cách nào, `SCOPE_orders.read` chỉ chặn loại thao tác không được cấp; owner/tenant là **business authorization** riêng.

### 12.2. Scope không tự cập nhật các quyền đã thay đổi

Tùy AS, introspection có thể phản ánh trạng thái token đã thu hồi nhanh hơn JWT xác minh offline. Nhưng ngay cả khi response luôn `active=true`, quyền trên order vẫn có thể đã thay đổi trong database từ khi token được cấp.

Nếu business policy thay đổi theo thời gian (owner đổi, order bị khóa, tài khoản bị tạm dừng), service phải dựa trên **trạng thái có thẩm quyền tại thời điểm thao tác**, không chỉ một claim đã cấp trước đó.

## 13. 401, 403 và `insufficient_scope`

Có hai lớp thất bại cần phân biệt:

| Tình huống | Lớp bị từ chối | Kết quả HTTP phổ biến |
|---|---|---|
| Không có Bearer token trên route protected | Authentication | 401 |
| Introspection trả `active:false` | Authentication | 401 |
| Introspection endpoint xác thực token thất bại | Authentication | 401, tùy loại lỗi |
| Token active nhưng audience không hợp lệ theo policy | Authentication/token contract | 401 |
| Token active, scope chỉ `orders.read` nhưng POST cần `orders.create` | Authorization | 403 |
| Token active, scope đúng nhưng user không sở hữu order | Business authorization | 403 hoặc 404 theo chính sách |
| Introspection endpoint không truy cập được (timeout/5xx) | Hệ thống xác thực không có dữ liệu tin cậy | Không được tự động cho phép; status/lỗi phụ thuộc thiết kế fail-closed |

Với Bearer token theo RFC 6750, khi thiếu scope phù hợp, response có thể chứa:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.create"
```

Spring Security có các handler cho Bearer authentication/access-denied; header và body thực tế phụ thuộc cấu hình và trường hợp. Không mặc định mọi 403 đều có đủ các trường như ví dụ, và không xuất thông tin token raw/secret trong error.

### 13.1. Token active nhưng không có scope: không phải token đủ quyền

Ví dụ AS trả:

```json
{
  "active": true,
  "sub": "user-842"
}
```

Resource Server có thể xác thực principal nhưng thiếu `SCOPE_orders.read`, dẫn tới 403 ở route yêu cầu scope. Nếu hợp đồng bắt buộc token luôn có scope, có thể coi response thiếu `scope` là sai token profile và từ chối sớm bằng custom introspector. Chọn chính sách nhất quán với AS và tránh “fallback cấp read”.

### 13.2. Introspection lỗi mạng: không được tự gán authorities

Anti-pattern:

```java
// KHÔNG LÀM: fallback cấp quyền khi introspection lỗi.
try {
    return introspector.introspect(token);
} catch (Exception unavailable) {
    return new DefaultOAuth2AuthenticatedPrincipal(
        "fallback-user",
        Map.of(),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));
}
```

Nếu AS tạm không phản hồi, API không có bằng chứng token còn active. Tự tạo principal có `SCOPE_orders.read` có thể mở quyền cho token đã bị thu hồi hoặc token giả. Hướng an toàn thường là **fail closed**, có timeout và cơ chế báo lỗi phù hợp để vận hành.

Có thể cân nhắc cache kết quả introspection theo chính sách rủi ro, nhưng đó là **quyết định về khoảng thời gian tin cậy và thu hồi**, không phải cách tạo quyền từ không có chứng cứ.

## 14. Vận hành: hiệu năng, caching và thời điểm thu hồi

Với introspection, mỗi request có thể tạo một chuyến đi tới AS nếu không có cache. Điều này ảnh hưởng độ trễ, tải và khả năng chịu lỗi.

### 14.1. Lợi ích và đánh đổi

| Cách xử lý | Lợi ích | Đánh đổi |
|---|---|---|
| Introspect mỗi request | Thường phản ánh nhanh trạng thái token mới nhất của AS | Thêm mạng/độ trễ và phụ thuộc AS |
| Cache introspection ngắn hạn | Giảm tải và latency | Token vừa bị thu hồi có thể vẫn được xem active trong cache |
| JWT signature verification local | Ít phụ thuộc mạng sau khi có key, dễ scale | Trạng thái thu hồi không tự cập nhật nếu chỉ kiểm tra chữ ký/claim |
| Cache kết quả quyền quá lâu | Hiệu năng tốt ở trạng thái bình thường | Authority/tenant/scope có thể stale và mở quyền sau khi bị thu hồi |

Nếu dùng cache, cần xác định:

- Cache được key theo **token thật** mà không log raw token; nếu dùng hash làm key, cần phương án phù hợp tính nhạy cảm và khả năng đoán token.
- Không cache `active=true` vượt qua giới hạn `exp` của token (nếu có) và policy thu hồi.
- Có thể cần TTL âm ngắn cho `active=false` để tránh quá tải, nhưng chính sách phải xét tình huống phát hành/hội tụ token.
- Các response và attributes nhạy cảm có được bảo vệ trong bộ nhớ/cache store hay không?
- Khi AS báo token revoked, trong bao lâu mọi instance dừng nhận?
- Trong sự cố mạng, hệ thống dùng cached metadata còn hợp lệ theo policy hay fail closed?

Không mặc định `OpaqueTokenIntrospector` của mọi phiên bản Spring Security có cache kết quả introspection tự động với TTL giống nhau. Cấu hình cache tùy biến phải được xác định và vận hành riêng.

### 14.2. Authenticated principal không nên lưu xuyên request

`SecurityContextHolder` thường đặt Authentication trong phạm vi request/thread hiện tại. Không lưu một `BearerTokenAuthentication` hoặc collection authorities vào biến static/singleton và dùng cho mọi request sau.

Với stateless bearer API, mỗi request phải được xác thực theo credential hiện tại (hoặc kết quả cache hợp lệ theo policy), rồi kiểm tra HTTP authorization. Một người dùng có nhiều access token với scopes khác nhau có thể có **authorities khác nhau trong từng request**, dù `sub` giống nhau.

### 14.3. Không ghi raw token trong log

Bearer token là credential có thể bị dùng lại nếu bị lộ. Không ghi:

```text
Authorization: Bearer opaque-secret-token-...
token=opaque-secret-token-...
client_secret=...
```

Thay vào đó, log metadata vận hành không nhạy cảm như correlation ID, endpoint introspection đã cấu hình, latency, HTTP status upstream, kết quả authentication/authorization (đã lọc) và identifiers nội bộ được phép.

Introspection response có thể chứa thông tin định danh, email, tenant hoặc role; không ghi tràn lan toàn bộ JSON response hoặc `principal.getAttributes()`.

### 14.4. Giới hạn tin cậy của Introspection endpoint

`active:true` đáng tin khi:

1. Resource Server gọi **đúng endpoint AS được cấu hình tin cậy** qua TLS.
2. Cơ chế xác thực Resource Server với AS được bảo vệ.
3. Response được nhận từ kết nối tin cậy và kiểm tra lỗi định dạng theo thư viện.
4. AS chỉ trả metadata đáng tin cho Resource Server đủ quyền.
5. Audience/issuer/token type/scope và các policy bắt buộc được áp dụng theo hợp đồng.

Nếu một proxy/tự viết wrapper thay thế response mà không chứng minh nguồn dữ liệu, mọi authority mapping phía sau có thể biến thành lỗ hổng nâng quyền. Không coi `scope` do client gửi dưới dạng header hay form field là tương đương `scope` do AS trả về.

## 15. Kiểm thử mapping scope và HTTP authorization

Để kiểm chứng hệ thống, nên phân biệt:

1. **Contract test với introspection:** HTTP response từ AS được diễn giải đúng; `active`, `scope`, `aud` và lỗi được xử lý.
2. **Mapping test:** principal sau introspection có đúng authorities, gồm prefix `SCOPE_` hay không.
3. **Authorization test:** rule HTTP/method yêu cầu đúng scope; thiếu scope bị từ chối.
4. **Business authorization test:** owner/tenant và trạng thái dữ liệu được kiểm soát.

### 15.1. Unit test cho custom authority wrapper

Một test minh họa về việc **giữ scope mặc định khi thêm permission**:

```java
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

import static org.assertj.core.api.Assertions.assertThat;

class PermissionEnrichingIntrospectorTest {

    @Test
    void preservesScopeAndAddsWhitelistedPermission() {
        OpaqueTokenIntrospector stub = token ->
            new DefaultOAuth2AuthenticatedPrincipal(
                "user-842",
                Map.of(
                    "sub", "user-842",
                    "scope", "orders.read",
                    "permissions", List.of("order:approve", "unknown-value")
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector decorated =
            new PermissionEnrichingIntrospector(stub);

        OAuth2AuthenticatedPrincipal principal =
            decorated.introspect("test-token");

        assertThat(principal.getAuthorities())
            .extracting(authority -> authority.getAuthority())
            .contains(
                "SCOPE_orders.read",
                "PERMISSION_order:approve")
            .doesNotContain("PERMISSION_unknown-value");
    }
}
```

Test này chứng minh **logic wrapper**, không chứng minh AS thực sự trả `scope` chuẩn hoặc token có `active:true`. Stub đã trả sẵn `SCOPE_orders.read` nên test không chạy mapping mặc định từ HTTP introspection response. Cần test mức tích hợp riêng cho delegate/HTTP.

### 15.2. Test phản hồi introspection thực tế

Có thể dùng mock HTTP server cho introspection endpoint trong môi trường test, cấu hình `NimbusOpaqueTokenIntrospector` hoặc implementation tương ứng trỏ tới endpoint đó. Các response test:

| Mock introspection response | Điều cần xác nhận |
|---|---|
| `{"active":true,"scope":"orders.read"}` | Principal có `SCOPE_orders.read`, không có `SCOPE_orders.write` |
| `{"active":true,"scope":"orders.read orders.write"}` | Hai authorities chính xác |
| `{"active":true}` | Không tự thêm scope authority |
| `{"active":false}` | Không có authenticated principal, token bị từ chối |
| `{"active":true,"aud":["payments-api"],"scope":"orders.read"}` | Custom audience policy từ chối Orders API |
| `{"active":true,"scp":["orders.read"]}` | Chỉ có mapping theo hợp đồng nếu custom mapper được cấu hình |
| Response HTTP 401 từ AS vì client credentials sai | Authentication/introspection thất bại, không fallback cấp quyền |
| Endpoint timeout/5xx | Không coi token active nếu không có bằng chứng đáng tin |

Kết quả cụ thể của HTTP status ở phía client khi AS không khả dụng còn phụ thuộc cách API xử lý infrastructure failures. Điều bắt buộc về bảo mật là **không tự tạo quyền cho token chưa xác minh**.

### 15.3. Test HTTP route cần authority đúng

Spring Security Test có thể mô phỏng Authentication để kiểm tra riêng tầng authorization:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersScopeAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsReadAuthority() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsMissingReadAuthority() throws Exception {
        mockMvc.perform(get("/api/orders/ORD-123")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_other.read"))))
            .andExpect(status().isForbidden());
    }
}
```

Ví dụ giả định test context có controller và dữ liệu cần để GET trả 200 khi đủ quyền; business policy có thể từ chối hoặc trả 404 tùy fixture. `opaqueToken().authorities(...)` là request post processor của Spring Security Test để **giả lập principal/authorities**, không gửi request thật tới AS. Vì vậy test này không chứng minh bộ introspector thực sự ánh xạ `scope` từ HTTP response.

Để kiểm tra toàn pipeline, phải gửi Bearer token trong request và dùng một mock introspection endpoint hoặc test double tại đúng boundary, xác nhận việc chọn introspector, xử lý `active` và mapping quyền.

### 15.4. Test đủ quyền theo method

| Request | Scope được trả qua introspection | Quyền mong đợi |
|---|---|---|
| GET `/api/orders/123` | `orders.read` | HTTP scope check cho qua |
| GET `/api/orders/123` | `orders.write` | Không tự cho qua nếu API cần read chính xác |
| POST `/api/orders` | `orders.create` | HTTP scope check cho qua |
| POST `/api/orders` | `orders.read` | Từ chối do thiếu create |
| PUT `/api/orders/123` | `orders.update` | HTTP scope check cho qua |
| DELETE `/api/orders/123` | `orders.update` | Từ chối do thiếu delete |
| GET `/api/orders/999` | `orders.read` nhưng khác tenant | Domain authorization từ chối |
| Mọi route protected | `active:false` | Authentication từ chối trước authorization |

“Cho qua HTTP scope check” không có nghĩa controller chắc chắn trả 200/201; vẫn còn validation payload, ownership và các điều kiện nghiệp vụ.

## 16. Những lỗi thường gặp và cách nhận diện

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Introspection trả scope read nhưng API luôn 403 | Rule kiểm tra `orders.read` thay vì `SCOPE_orders.read` | Dùng đúng authority prefix |
| Token được cấp scope nhưng authorities rỗng | AS trả `scp`/`permissions` thay vì `scope` | Thống nhất response chuẩn hoặc custom mapping |
| API chỉ cần read nhưng AS trả scope có `SCOPE_` trong giá trị | Mapping tạo `SCOPE_SCOPE_...` | Phát scope raw hoặc sửa hợp đồng converter |
| Chỉ có `active:true` mà route vẫn 403 | Token không có scope authority yêu cầu | Kiểm tra scopes được cấp thực tế |
| Một scope đổi chữ hoa/thường dẫn tới 403 | Authority so khớp chuỗi chính xác | Thống nhất tên scope trong AS/API |
| Có `orders.write` mà GET cần read vẫn 403 | Không có hierarchy scopes mặc định | Định nghĩa chính sách rõ hoặc cấp cả hai scopes |
| Có `ROLE_ADMIN` trong rule nhưng AS chỉ trả `scope=admin` | OAuth scope không tự thành role authority | Dùng `SCOPE_admin` hoặc role converter riêng |
| Token active/scope đúng nhưng audience không dành cho API | Cross-resource token use | Kiểm tra `aud` theo hợp đồng |
| JWT token trông đúng nhưng opaque API trả 401 | AS không nhận/không xem token active, hoặc credentials introspection sai | Kiểm tra contract endpoint, issuer, client authentication |
| Custom introspector trả principal trống quyền | Wrapper đã thay vì giữ `getAuthorities()` | Delegate trước và giữ authorities mặc định |
| Custom wrapper tự thêm `ROLE_ADMIN` từ chuỗi bất kỳ | Authority escalation do mapping thiếu allowlist | Chỉ map nguồn/giá trị đã được xác nhận |
| Chỉ có `@WithMockUser` test thành công | Test chưa chạy HTTP introspection và mapping | Test riêng introspector/delegate |
| Token active/scope đúng nhưng không xem được order người khác | Domain policy từ chối | Đây thường là hành vi đúng |
| Thay đổi quyền ở IdP nhưng API còn nhận quyền cũ | Cache introspection hoặc token còn hiệu lực | Xem TTL, revocation semantics và business policy |
| Introspection endpoint lỗi, API fallback cấp read | Fail-open nguy hiểm | Fail closed; không tạo principal có quyền khi chưa xác minh |
| API dùng `jwt()` nhưng mong introspection mapping | Chọn sai authentication route | Cấu hình `opaqueToken()` với introspector phù hợp |
| CORS preflight bị 401 | Browser OPTIONS không có Bearer như request thật | Cấu hình CORS/filter đúng, vẫn giữ auth cho request thực |

### 16.1. 403 không phải lúc nào cũng là lỗi mapping

Khi gặp 403, nên phân biệt:

1. Principal có `SCOPE_orders.read` không?
2. Rule `hasAuthority` dùng đúng chuỗi không?
3. Request match đúng `SecurityFilterChain` và rule method/path nào?
4. Method security có điều kiện thêm không?
5. Business service có từ chối vì owner/tenant hoặc trạng thái không?

Không tự thêm `permitAll()` hoặc `authenticated()` rộng hơn chỉ để làm mất 403. Cần tìm đúng lớp từ chối.

### 16.2. Quan sát cấu hình không lộ bí mật

Khi debug, có thể bật log mức phù hợp của Spring Security trong môi trường kiểm soát và quan sát:

```text
request correlation id
introspection endpoint (không gồm token/credentials)
latency / timeout / HTTP status upstream
authenticated principal type
granted authority names được phép ghi nhận
matched security chain / route policy
authorization decision (allow/deny)
```

Không đưa Bearer header, token raw, client secret hoặc toàn bộ response introspection vào log. Vì scope/role cũng có thể nhạy cảm ở một số hệ thống, chỉ ghi khi thực sự cần và có chính sách bảo vệ dữ liệu.

## 17. Checklist thiết kế hợp đồng introspection → authorities

Trước khi triển khai production, Authorization Server và Resource Server cần thống nhất:

1. **Đường introspection và authentication:** endpoint URL, TLS, client authentication method, secret rotation, quyền introspect.
2. **Scope format:** `scope` dạng chuỗi cách nhau bằng dấu cách theo RFC 7662 hay extension `scp`/`permissions`? Nếu extension thì ai quản trị và semantics ra sao?
3. **Scope catalog:** tên chính xác `orders.read`, `orders.create`, `orders.update`, v.v.; scope nào được cấp cho client nào?
4. **Issuer/audience:** token active có được cấp đúng cho API không, introspection trả metadata nào để kiểm chứng?
5. **Principal model:** `sub` và `client_id` thể hiện user hay service; tenant/actor được ánh xạ thế nào?
6. **Authority mapping:** giữ `SCOPE_` hay dùng prefix khác? Có thêm role/permission không, lấy từ nguồn nào?
7. **Error policy:** `active:false`, thiếu scope, sai audience, timeout và error từ AS dẫn đến xử lý nào?
8. **Revocation/caching:** thời gian hiệu lực của cache, exp/TTL, độ trễ thu hồi tối đa chấp nhận được.
9. **Authorization:** rule HTTP/method nào cần authority nào? Điều kiện owner/tenant nằm ở đâu?
10. **Testing:** response chuẩn/nonstandard, missing scope, nhiều scopes, active false, audience sai, token hết hạn và network failure.
11. **Observability:** nhìn thấy mapping/decision mà không làm lộ token hoặc thông tin nhạy cảm.
12. **Multi-instance:** tất cả Resource Server và gateway có cùng hợp đồng mapping, cache và revocation semantics không?

### 17.1. Mô hình ra quyết định

```mermaid
flowchart TD
    A["Nhận Authorization: Bearer token"] --> B["OpaqueTokenIntrospector gọi AS đáng tin"]
    B --> C{"active và response hợp lệ?"}
    C -->|"Không"| X["Từ chối authentication"]
    C -->|"Có"| D{"aud / iss / token profile phù hợp?"}
    D -->|"Không"| X
    D -->|"Có"| E["Đọc scope chuẩn hoặc extension đã được thống nhất"]
    E --> F["Mapping thành GrantedAuthority: SCOPE_..."]
    F --> G{"HTTP/method có required authority?"}
    G -->|"Không"| Y["Từ chối authorization"]
    G -->|"Có"| H{"Owner / tenant / state hợp lệ?"}
    H -->|"Không"| Y
    H -->|"Có"| I["Cho thực hiện thao tác"]
```

Đây là mô hình logic; **việc kiểm tra audience/issuer có thể được thực hiện bởi AS theo hợp đồng hoặc bởi một wrapper tin cậy ở Resource Server**. Không được suy ra `opaqueToken()` mặc định tự kiểm tra mọi thuộc tính mở rộng mà hệ thống cần.

## 18. Kết luận

```text
OAuth access token
    |
    v
Authorization: Bearer opaque-token
    |
    v
Token introspection qua kênh đáng tin
    |
    +-- active=false -> không có Authentication đáng tin
    |
    +-- active=true, scope="orders.read orders.write"
                |
                v
       OAuth2AuthenticatedPrincipal
                |
                v
       GrantedAuthority:
         SCOPE_orders.read
         SCOPE_orders.write
                |
                v
       BearerTokenAuthentication
                |
                v
       HTTP/method authorization
                |
                v
       Business owner/tenant/state checks
```

**OAuth `scope` trong phản hồi introspection là dữ liệu quyền được Authorization Server xác nhận; Spring Security `GrantedAuthority` là biểu diễn quyền dùng để áp quy tắc ở Resource Server.** Trong cấu hình opaque token thông thường, mỗi scope được ánh xạ thành authority có tiền tố `SCOPE_`, nên `scope: "orders.read"` đáp ứng luật `hasAuthority("SCOPE_orders.read")`.

Khi AS trả biến thể như `scp` hoặc `permissions`, cần custom mapping **có chủ đích và giới hạn nguồn tin cậy**, không tự động cấp mọi quyền từ JSON bất kỳ. Quan trọng hơn, **`active:true` không thay thế audience, scope authorization và quyền nghiệp vụ trên từng object**. API phải từ chối token không active, token sai đối tượng nhận và request thiếu authority, đồng thời kiểm tra owner/tenant ngay cả khi scope đã đúng.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope`, client authentication và metadata token.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): scope và việc cấp access token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials, 401/403 và `insufficient_scope`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): tài nguyên/audience của access token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token, hữu ích khi so với opaque/introspection.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình introspection và ánh xạ `scope` thành `SCOPE_`.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer token authentication.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, matcher và chính sách HTTP.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và authorization ở service.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): interface introspection.
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): Authentication cho opaque bearer token.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): quyền trên từng object của API.
