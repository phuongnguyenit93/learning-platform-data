# introspection-uri, client-id, client-secret và xác thực Resource Server

Trong hệ thống **Spring Security OAuth 2.0 / OIDC Resource Server**, một API có thể nhận access token mà bản thân API **không thể hoặc không cần tự giải mã, xác minh chữ ký JWT**. Thay vì tự kiểm tra token bằng public key/JWKS, Resource Server gửi token tới **Authorization Server** qua một endpoint **token introspection**, nhận thông tin trạng thái và các thuộc tính được phép sử dụng để xác thực request.

Trong Spring Boot, ba thuộc tính cấu hình quan trọng là:

- `introspection-uri`: URL của **endpoint introspection** mà Resource Server gọi.
- `client-id`: định danh **của Resource Server hoặc một client chuyên dùng cho introspection**, tùy đăng ký tại Authorization Server.
- `client-secret`: bí mật chứng minh danh tính của introspection client khi nó gọi endpoint; đây **không phải access token của người dùng**.

Ba thuộc tính nằm trong nhánh:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Các biến môi trường trong ví dụ là placeholders: **phải được cấp thông qua secret manager/cấu hình triển khai**, không commit credential thật vào repository.

**Mục tiêu bài học:** hiểu đúng hai chiều xác thực diễn ra với opaque access token, biết phân biệt thông tin định danh của caller và credential của Resource Server, cấu hình Spring Security an toàn, đọc trạng thái `active`/`scope`, xử lý token bị từ chối và thiết kế hoạt động khi introspection endpoint gặp sự cố.

> **Ngữ cảnh minh họa:** OAuth Authorization Server tại `https://login.example.com`, Orders API tại `https://api.example.com`, audience nếu được công bố là `orders-api` và scope `orders.read`. Ví dụ Java dùng Spring Boot 3.x và Spring Security 6.x ở Servlet stack. Mọi URL, client ID và mã token trong tài liệu đều là giá trị ví dụ.

## 1. Opaque token là gì, và vì sao Resource Server phải introspect?

**Opaque access token** là token mà Resource Server không cần biết cấu trúc bên trong. Nó có thể chỉ là chuỗi ngẫu nhiên:

```text
Authorization: Bearer K1cJ4H9vYp2Noa...REDACTED
```

Resource Server không thể tự suy ra user, scope, audience hay thời hạn từ chuỗi này. Nó phải hỏi một nguồn có thẩm quyền: **Authorization Server**, nơi quản lý việc phát hành và trạng thái token.

Ví dụ một access token dạng opaque không nhất thiết có ba đoạn `header.payload.signature` giống JWT. Nhưng cũng cần lưu ý:

- **Opaque hay JWT là cách Resource Server xử lý token**, không đơn thuần được quyết định bằng hình thức chuỗi. Một token trông giống JWT vẫn có thể được Resource Server gửi introspection nếu hệ thống thiết kế theo mô hình đó.
- Trong Spring Security, cấu hình `opaquetoken` sử dụng **OpaqueTokenIntrospector** chứ không đi qua `JwtDecoder` như cấu hình `jwt`.
- Nếu Authorization Server trả `active=false`, token phải bị từ chối, kể cả client khẳng định token còn thời hạn.
- Nếu Authorization Server trả `active=true`, API **vẫn phải kiểm tra** các thuộc tính và quyền phù hợp với hợp đồng của resource, không tự suy luận rằng mọi thao tác đều được phép.

### 1.1. Token introspection giải quyết bài toán nào?

Với JWT tự xác minh, API có thể kiểm tra chữ ký và claims bằng public JWK đã tin cậy mà không cần gọi AS cho mọi request. Với opaque token, API thường phụ thuộc vào kết quả introspection để biết:

1. Token có đang **active** không?
2. Token được cấp cho **client nào**?
3. Token đại diện cho **subject** nào, nếu có?
4. Scope hoặc authorities nào được cấp?
5. Có hạn dùng/issuer/audience/tenant metadata nào cần kiểm tra?
6. Token có đủ điều kiện để được sử dụng tại **Orders API** hay không?

Một token bị thu hồi có thể nhanh chóng cho kết quả `active=false` khi introspection được gọi lại. Tuy vậy mức độ cập nhật phụ thuộc Authorization Server, cache, replication và thời điểm revoke. **Đừng mặc định introspection luôn tức thì trong mọi kiến trúc**.

### 1.2. Cùng tên “client” nhưng là hai vai trò khác nhau

Trong một luồng phổ biến có **ít nhất hai client identity**:

| Vai trò | Ví dụ | Nơi sử dụng |
|---|---|---|
| **OAuth application client** | `storefront-web` | Xin access token từ Authorization Server, đưa token vào request tới API |
| **Introspection client / Resource Server credential** | `orders-api-introspector` | Orders API dùng `client-id` và `client-secret` để xác thực **khi gọi introspection endpoint** |

Một số triển khai cho phép các vai trò dùng cùng đăng ký client, nhưng **không nên giả định chúng luôn là một**. Để thực hiện least privilege và audit dễ dàng, thường nên dùng credential riêng cho Resource Server hoặc nhóm tài nguyên có quyền introspect token tương ứng.

## 2. Hai bước xác thực khác nhau trong cùng một request

Có hai đường truyền quan trọng:

```mermaid
sequenceDiagram
    autonumber
    participant Caller as OAuth Client / API Caller
    participant RS as Orders API Resource Server
    participant AS as Authorization Server
    Caller->>RS: GET /api/orders/42; Authorization: Bearer ACCESS_TOKEN
    RS->>AS: POST /oauth2/introspect qua HTTPS
    Note over RS,AS: Resource Server xác thực với client-id/client-secret
    Note over RS,AS: Body chứa token cần kiểm tra
    AS->>AS: Kiểm tra token và quyền introspect của client
    AS-->>RS: active=true + attributes / active=false
    RS->>RS: Chuyển attributes thành Authentication và authorities
    RS->>RS: Kiểm tra scope, audience, tenant, object policy
    alt Token active và đủ quyền
        RS-->>Caller: Trả dữ liệu hoặc thực thi thao tác
    else Token inactive hoặc không đủ quyền
        RS-->>Caller: Từ chối theo loại lỗi
    end
```

### 2.1. Caller xác thực với Resource Server bằng Bearer token

HTTP request từ caller đến API:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FROM_AUTHORIZATION_SERVER
Accept: application/json
```

Điểm đáng nhớ:

- `ACCESS_TOKEN_FROM_AUTHORIZATION_SERVER` là **bearer credential của request**.
- Client không biết và **không được biết** `client-secret` của Resource Server.
- API không được coi thông tin `sub`, `roles`, `tenant_id` gửi trong request body/header là kết quả xác thực thay cho introspection.
- Token chỉ là dữ liệu đầu vào cho đến khi introspection và các validators/policy của API chấp nhận.

### 2.2. Resource Server xác thực với Authorization Server

Khi introspect token, Orders API thực hiện outbound request:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_CLIENT_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_FROM_CALLER&token_type_hint=access_token
```

Đây là minh họa giao thức, **không chứa credential thật**. Khi dùng HTTP Basic, client ID/secret được mã hóa Base64 theo quy tắc của giao thức HTTP Basic và OAuth; **Base64 không bảo mật dữ liệu**. Kết nối phải sử dụng HTTPS và kiểm tra chứng chỉ TLS.

Theo RFC 7662:

- `token` là tham số **bắt buộc** cần introspect.
- `token_type_hint` là **gợi ý tùy chọn**; Authorization Server có thể bỏ qua nếu không hữu ích.
- Authorization Server phải bảo vệ endpoint introspection, xác thực caller phù hợp và áp chính sách về thông tin mà caller được phép biết.
- Giao thức định nghĩa JSON response có trường `active` boolean.

Client authentication **không chỉ có HTTP Basic**. Tùy Authorization Server và hồ sơ triển khai, introspection endpoint có thể hỗ trợ `client_secret_post`, `private_key_jwt`, mutual TLS hoặc cơ chế khác. Bộ cấu hình đơn giản `client-id/client-secret` của Spring Resource Server thường phù hợp với mô hình client credentials truyền bằng HTTP Basic; nếu AS yêu cầu một phương thức khác, cần cấu hình HTTP client/introspector riêng phù hợp, **không đổi sang phương thức kém an toàn chỉ cho tiện**.

### 2.3. Hai loại token/credential không được nhầm

```text
INBOUND — caller -> API
  Authorization: Bearer <access-token>
                |
                v
OUTBOUND — API -> introspection endpoint
  Authorization: Basic <id-and-secret-of-introspection-client>
  body: token=<the-access-token-to-check>
```

Đừng đưa `client-secret` của Resource Server vào header `Authorization: Bearer` khi gọi Orders API. Đừng đưa access token của caller làm “mật khẩu OAuth client” để kết nối tới introspection endpoint. Mỗi giá trị có vai trò và trust boundary riêng.

## 3. RFC 7662: phản hồi introspection gồm những gì?

RFC 7662 quy định **OAuth 2.0 Token Introspection**, trong đó trường `active` là trọng tâm.

### 3.1. Token active

Ví dụ phản hồi:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "storefront-web",
  "token_type": "Bearer",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000,
  "iat": 1999996400,
  "nbf": 1999996400,
  "tenant_id": "tenant-a"
}
```

Ý nghĩa:

| Trường | Cách hiểu | Hành động của Resource Server |
|---|---|---|
| **`active`** | Authorization Server thông báo token có còn active theo chính sách của nó không | **Phải true** mới xét tiếp |
| `scope` | Danh sách scope được cấp cho token, thường dạng chuỗi cách nhau bởi space | Ánh xạ thành authorities và kiểm tra theo endpoint |
| `client_id` | **OAuth client mà access token được cấp cho** | Có thể dùng chính sách client allowlist; **không phải** introspection client-id trong config |
| `token_type` | Loại token được issuer công bố | Kiểm tra nếu hợp đồng yêu cầu |
| `sub` | Subject của token nếu có | Xác định user/service theo grant/profile, không mặc định luôn là user |
| `aud` | Resource Server/audience được phép dùng token, khi AS cung cấp | Kiểm tra `orders-api` nếu hợp đồng yêu cầu |
| `iss` | Issuer của token nếu AS cung cấp | Đối chiếu issuer tin cậy khi hợp đồng yêu cầu |
| `exp` | Hạn dùng NumericDate | Kiểm tra nhất quán với `active` và chính sách API |
| `iat`, `nbf` | Thời điểm cấp / bắt đầu hiệu lực | Dùng cho các điều kiện tuổi, thời gian nếu có |
| `tenant_id` | Thuộc tính tùy chỉnh | Chỉ sử dụng theo hợp đồng AS–RS, và vẫn cần quyền ở tài nguyên |

**Không phải mọi trường ngoài `active` đều bắt buộc trong mọi phản hồi introspection.** RFC 7662 mô tả các trường tùy chọn; hồ sơ AS và yêu cầu của Resource Server quyết định trường nào phải hiện diện. Nếu API cần `aud` để tránh nhận token cấp cho dịch vụ khác, hãy đảm bảo AS cung cấp thông tin tin cậy tương ứng; nếu thiếu, **không tự giả định token dành cho API này**.

### 3.2. Token inactive

Một phản hồi thường gặp:

```json
{
  "active": false
}
```

Theo RFC 7662, phản hồi của token không active thường được giới hạn để không tiết lộ chi tiết về token ngoài ý muốn. `active=false` có thể nghĩa:

- Token chưa từng tồn tại hoặc giá trị không hợp lệ.
- Token đã hết hạn.
- Token bị thu hồi.
- Token không được phép introspect trong ngữ cảnh này.
- AS áp chính sách không công bố token cho caller introspection cụ thể.

Không nên trả lại cho API caller lý do nội bộ quá chi tiết như “token này thuộc tenant X” hoặc “đã bị admin Y thu hồi”. Với Resource Server, kết quả xử lý thường là **token không hợp lệ** và request bị từ chối.

### 3.3. `active=true` không có nghĩa có đủ quyền trên tất cả tài nguyên

Một access token active có thể chỉ có:

```json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "storefront-web",
  "sub": "customer-42"
}
```

Với request `POST /api/orders/42/cancel` cần `orders.cancel`, API phải từ chối vì **thiếu scope**, bất kể token active.

Tương tự, với `GET /api/orders/99`, token có `orders.read` nhưng subject không sở hữu đơn hàng 99 cũng phải bị từ chối tại object policy.

## 4. Ý nghĩa chính xác của ba thuộc tính cấu hình

### 4.1. `introspection-uri`: endpoint kiểm tra token

Ví dụ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
```

`introspection-uri` là **URL HTTP(S) do Authorization Server cung cấp cho RFC 7662 introspection**, không phải:

- URL cấp access token `/oauth2/token`.
- URL người dùng đăng nhập `/authorize`.
- `issuer-uri` dùng JWT issuer discovery.
- JWKS endpoint `/jwks` hoặc `/.well-known/jwks.json`.
- API endpoint của Orders Resource Server.

Đường dẫn thực tế có thể khác nhau theo nhà cung cấp: `/oauth2/introspect`, `/protocol/openid-connect/token/introspect` hoặc route riêng. Phải lấy từ **tài liệu/metadata đáng tin của Authorization Server**, không đoán hoặc lấy từ giá trị URL do caller tự cung cấp.

**HTTPS là yêu cầu mặc định cho môi trường thật.** Việc gửi access token trong body và client secret qua kết nối không bảo vệ có thể làm lộ cả credential của caller lẫn Resource Server.

### 4.2. `client-id`: danh tính dùng để introspect

Ví dụ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
```

Giả sử biến môi trường chứa `orders-api-introspector`. Authorization Server biết đây là một client được cấp quyền truy cập introspection endpoint.

Một số điểm:

- Đây là **client ID được cấu hình trong Resource Server**, không phải `client_id` trong phản hồi introspection.
- Nó có thể được đăng ký riêng theo API, môi trường và nhóm quyền.
- Chỉ những Resource Server/instance được phép mới dùng identity tương ứng.
- AS có thể áp chính sách chỉ cho introspect token thuộc resource, audience hoặc client nhất định.
- Không dùng một client ID quá rộng làm “toàn quyền đọc mọi token” nếu không cần.

Trong OAuth, `client_id` thường là **định danh**, không phải bí mật. Bản thân client ID không chứng minh được quyền gọi introspection endpoint; cần client authentication hoặc cơ chế bảo vệ khác do AS yêu cầu.

### 4.3. `client-secret`: chứng minh quyền truy cập endpoint

`client-secret` là credential được cấp cho introspection client và dùng khi Resource Server xác thực với AS.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Phải bảo vệ như một mật khẩu ứng dụng:

- Không hardcode giá trị thật trong `application.yml` đã commit.
- Không log hoặc in ra stdout khi ứng dụng khởi động.
- Không đưa vào JavaScript/frontend hoặc mã mobile app.
- Không lộ qua exception, URL/query string, metrics labels, traces hay HTTP access log.
- Giới hạn quyền đọc trong secret manager, Kubernetes Secret mount hoặc runtime secret injection.
- Hỗ trợ rotation và phân phối secret cho các instance phù hợp.
- Sử dụng HTTPS tới endpoint, xác minh hostname và certificate chain.

**Không nên tái sử dụng cùng secret cho những mục đích khác**, chẳng hạn ký JWT HS256, kết nối database hoặc OAuth client khác. Nếu secret bị lộ, phạm vi ảnh hưởng liên quan đến những quyền mà introspection client đó đang nắm.

### 4.4. Không phải mọi Authorization Server đều dùng client secret

Một AS có thể yêu cầu client authentication mạnh hơn, ví dụ **mTLS** hoặc **private_key_jwt**. Trong mô hình đó, ba thuộc tính `introspection-uri/client-id/client-secret` có thể **không đủ** hoặc không phải cấu hình phù hợp.

Cần tuân theo phương thức authentication mà AS hỗ trợ và đã đăng ký cho RS. Việc dùng secret-based Basic là ví dụ phổ biến, không phải điều kiện bắt buộc duy nhất của RFC 7662.

## 5. Cấu hình Spring Boot Resource Server cho opaque token

### 5.1. Các dependencies

Ví dụ Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC và Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Không cần tích hợp login UI/OIDC client chỉ để Orders API introspect bearer access token. Đừng nhầm **OAuth2 Client ứng dụng web** với **OAuth2 Resource Server**. Resource Server chỉ cần công cụ xác thực access token và policy cho API.

### 5.2. Cấu hình đầy đủ qua YAML và secret injection

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Ở runtime, cung cấp hai biến môi trường tương ứng từ secret manager hoặc hệ thống triển khai. Không dùng chuỗi placeholder như credential thật.

Spring Boot còn hỗ trợ **environment binding** để bạn cung cấp trực tiếp các thuộc tính, ví dụ:

```text
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_INTROSPECTION_URI
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_ID
SPRING_SECURITY_OAUTH2_RESOURCESERVER_OPAQUETOKEN_CLIENT_SECRET
```

Đây là dạng tên biến môi trường tương ứng với property prefix của Spring Boot; cần tuân theo cách deployment hiện tại inject giá trị, không đặt bí mật trong manifest được quản lý như mã nguồn công khai.

### 5.3. Bật opaque token Resource Server trong SecurityFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ý nghĩa:

1. `BearerTokenAuthenticationFilter` lấy bearer token từ request.
2. Authentication manager chuyển token tới provider dành cho opaque token.
3. Provider sử dụng `OpaqueTokenIntrospector` để hỏi Authorization Server.
4. Khi kết quả được chấp nhận, Spring Security tạo `Authentication` chứa principal và authorities.
5. `AuthorizationFilter` dùng `SCOPE_orders.read`, `SCOPE_orders.write` để xét quyền chức năng.
6. Service/domain tiếp tục kiểm tra quyền trên từng đơn hàng, tenant và trạng thái nghiệp vụ.

**Phạm vi chain:** `securityMatcher("/api/**")` chỉ bao phủ URL dưới `/api/**`. Những URL khác cần chính sách security chain phù hợp; đừng để endpoint nội bộ ngoài matcher mặc nhiên không được bảo vệ.

### 5.4. `STATELESS` liên quan gì tới introspection?

`SessionCreationPolicy.STATELESS` thể hiện API không dựa vào HTTP session để lưu authentication giữa các request. Caller thường phải gửi bearer access token **trên mỗi request**.

Điều đó không có nghĩa AS chắc chắn được gọi qua network trên mỗi request trong mọi trường hợp: việc có cache hay không còn phụ thuộc introspector/cấu hình. Với introspection mặc định, thường phải gọi endpoint để xác định token, trừ khi bạn chủ động thêm cơ chế caching ở nơi thích hợp.

Đồng thời, `STATELESS` không phải lý do duy nhất để tắt CSRF. Quyết định CSRF còn phụ thuộc API có nhận **cookie/browser credentials tự gửi** hay các cơ chế xác thực khác không. Nếu hệ thống hỗn hợp session/cookie và bearer, phải đánh giá toàn bộ security chains.

## 6. Spring Security tạo Authentication từ introspection thế nào?

Trong mô hình JWT:

```text
JwtDecoder
  → JwtAuthenticationProvider
  → JwtAuthenticationToken
```

Trong mô hình opaque token:

```text
OpaqueTokenIntrospector
  → OpaqueTokenAuthenticationProvider
  → BearerTokenAuthentication
```

Đối tượng principal thường triển khai `OAuth2AuthenticatedPrincipal`, cho phép đọc attributes/authorities do introspector trả về sau khi token được chấp nhận.

### 6.1. Lấy Authentication hiện tại

```java
package com.example.orders.api;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/me")
    public Map<String, Object> currentCaller(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
            .map(a -> a.getAuthority())
            .toList();

        return Map.of(
            "principalName", authentication.getName(),
            "authorities", authorities
        );
    }
}
```

Đây là endpoint **minh họa**. Trong hệ thống production, không nên mặc định trả toàn bộ authorities/attributes cho mọi caller; chỉ lộ thông tin tối thiểu cần thiết.

### 6.2. Principal và attributes trong opaque token

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

@GetMapping("/api/subject")
public Map<String, String> subject(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

    String sub = principal.getAttribute("sub");
    return Map.of("sub", sub != null ? sub : "not-present");
}
```

Mã này giả định được đặt trong controller thích hợp và endpoint đã được bảo vệ. Nếu principal/claim thiếu, ứng dụng cần xử lý theo hợp đồng thay vì mặc định coi một chuỗi `not-present` là danh tính hợp lệ để phân quyền.

**Lưu ý:** `authentication.getName()` phụ thuộc cách introspector xây principal và thông tin được issuer trả về; không nên mặc định luôn tương đương end-user ID. Với `client_credentials`, chủ thể có thể là service, client hoặc identifier khác theo AS.

### 6.3. Scope được chuyển thành authority

Với phản hồi introspection:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

Spring Security thường biểu diễn các scope thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó:

```java
.hasAuthority("SCOPE_orders.read")
```

là cách kiểm tra quyền phổ biến.

Không tự nhận rằng mọi field như `roles`, `groups`, `permissions` được chuyển thành `ROLE_*` hay `PERMISSION_*`. Nếu muốn map claims tùy chỉnh, cần thiết kế cơ chế introspector hoặc converter tương ứng theo hợp đồng AS.

## 7. Điểm khác giữa client-id trong config và client_id trong introspection response

Có hai chuỗi trông giống nhau nhưng ý nghĩa hoàn toàn khác:

```yaml
# Identity mà Orders API dùng để gọi introspection endpoint
spring.security.oauth2.resourceserver.opaquetoken.client-id:
  orders-api-introspector
```

Và:

```json
{
  "active": true,
  "client_id": "storefront-web"
}
```

| Giá trị | Ai sở hữu? | Tác dụng |
|---|---|---|
| `orders-api-introspector` | Resource Server / introspection client | Chứng minh quyền **hỏi trạng thái token** tại Authorization Server |
| `storefront-web` | OAuth client nhận token | Metadata về **client mà token đã được phát hành cho** |

Bên cạnh đó:

- `sub` có thể đại diện user hoặc service.
- `aud` xác định Resource Server mà token được dự định sử dụng.
- `scope` xác định quyền đã cấp cho token.
- `iss` xác định Authorization Server, khi được cung cấp/kiểm chứng.

Không dùng `client_id` của token để xây HTTP Basic credentials cho introspection. Không dùng `client-id` của Resource Server làm bằng chứng token thuộc user/client nào.

### 7.1. Những câu hỏi nhận diện quan trọng

Khi API nhận introspection response, nên hỏi:

1. Token này có thực sự active không?
2. Issuer, audience hoặc resource contract có xác định được token được cấp cho **Orders API** không?
3. Token được cấp cho OAuth client nào và có nằm trong danh sách được phép với chức năng nhạy cảm không?
4. Subject là user hay service; có được hỗ trợ bởi endpoint này không?
5. Scope nào được cấp và còn cần thêm quyền tenant/ownership nào?
6. Các thuộc tính có mặt là **dữ liệu AS xác nhận** hay thông tin tùy ý do caller cung cấp?

Một phản hồi `active=true` **không loại bỏ** việc kiểm tra những điều kiện còn lại.

## 8. Introspection credential hoạt động theo nguyên tắc least privilege

### 8.1. Một đăng ký client riêng cho Orders API

Một cách triển khai hợp lý:

```text
Authorization Server
  |
  +-- Introspection client: orders-api-introspector
  |     - Được phép gọi token introspection endpoint
  |     - Chỉ được introspect token cho orders-api theo policy AS
  |     - Có secret hoặc phương thức client authentication riêng
  |
  +-- Introspection client: billing-api-introspector
        - Chỉ có quyền introspect token cho billing-api
        - Có credential riêng
```

Cách này giảm phạm vi lộ thông tin nếu credential của Orders API bị đánh cắp. Nó cũng tạo audit rõ: request introspection nào do Resource Server nào thực hiện.

RFC 7662 cho phép AS bảo vệ endpoint và giới hạn thông tin trả về; **không phải mọi Authorization Server đều tự có sẵn phân quyền introspection theo audience**. Cần kiểm tra cấu hình nhà cung cấp và chính sách triển khai thực tế.

### 8.2. Nếu nhiều Resource Server chia sẻ một client-secret?

Rủi ro gồm:

- Một RS bị lộ secret có thể sử dụng credential đó để gọi introspection thay các RS khác.
- Audit khó phân biệt nguồn thực sự của từng request.
- Rotation secret tác động tới nhiều môi trường/dịch vụ.
- AS có thể trả nhiều metadata hơn mức một RS cần.
- Việc thu hồi credential trở nên khó tổ chức vì quá nhiều bên phụ thuộc.

Nên ưu tiên client identity/secret được cấp **theo ranh giới tin cậy thực tế**, tách ít nhất development, staging, production và tách API nếu quyền truy cập token khác nhau.

### 8.3. Không đưa secret cho caller

Client phía browser/mobile chỉ gửi **access token hợp lệ** cho Orders API. Nó không cần biết và không được nhận:

```text
ORDERS_INTROSPECTION_CLIENT_SECRET
```

Nếu một API yêu cầu frontend gửi introspection secret, đó thường là **nhầm ranh giới bảo mật nghiêm trọng**. Tính bảo mật của secret chỉ có thể duy trì khi nó nằm trong backend/server-controlled environment.

## 9. HTTPS và bảo vệ dữ liệu khi gọi introspection

Trong request introspection có hai dạng credential nhạy cảm: **access token của caller** trong body và **credential của Resource Server** trong client authentication.

Bởi vậy:

- Dùng `https://...`, kiểm tra hostname và certificate chain.
- JVM/container phải có truststore/CA phù hợp với môi trường.
- Nếu có private CA, cấp CA được phê duyệt cho đúng workload thay vì tắt TLS validation.
- Không cấu hình `trustAllCertificates`, `InsecureTrustManager` hoặc hostname verifier luôn cho phép để “hết lỗi”.
- Không tự động follow redirect tới host lạ chứa request body/Authorization header có credential.
- Giới hạn DNS/egress để RS chỉ liên hệ introspection endpoint được phép.
- Tránh log HTTP request body có tham số `token` và header `Authorization: Basic ...`.

### 9.1. Phân biệt các lớp tin cậy

| Lớp | Cần xác minh | Nếu sai |
|---|---|---|
| **TLS tới AS** | Certificate, host, CA, scheme HTTPS | Resource Server không bảo vệ được token/credential trên đường truyền |
| **Client authentication** | `client-id/client-secret` hoặc phương thức khác | AS không cho phép introspection, thường từ chối request |
| **Introspection response** | JSON đúng, `active=true`, claims theo hợp đồng | Token không được chấp nhận hoặc phải từ chối vì thiếu metadata |
| **API authorization** | Scope, audience/resource, client/subject/tenant/ownership | Request bị từ chối dù token active |

Kết nối TLS hợp lệ tới một endpoint không đúng môi trường cũng không phải là “thành công”. Ví dụ API production cấu hình nhầm URI introspection staging có thể trả dữ liệu sai hoặc luôn xem token production không active. Phải gắn endpoint với **đúng issuer/môi trường**.

### 9.2. Kiểm tra với curl mà không lộ secret

Một ví dụ minh họa cú pháp, chỉ dùng trong môi trường được phép:

```bash
curl --fail-with-body --request POST \
  --url "https://login.example.com/oauth2/introspect" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --user "ORDERS_INTROSPECTION_CLIENT_ID" \
  --data-urlencode "token=REDACTED_TEST_TOKEN"
```

Trong lệnh này, `--user` chỉ đưa client ID để curl có thể **yêu cầu mật khẩu** tương tác, thay vì viết secret sau dấu `:` vào command history. Nếu chạy trong CI/container không tương tác, phải dùng phương thức quản lý credential do tổ chức phê duyệt và tránh để secret xuất hiện trong danh sách process, log hoặc artifact.

Đây **không phải** lệnh có thể chạy trực tiếp với client ID/test token giả; nó là khung thao tác kiểm tra POST form và Basic client authentication. Nếu phiên bản curl không hỗ trợ `--fail-with-body`, có thể dùng `--fail` và xem status/header qua công cụ khác.

Trong thực tế còn cần xác minh AS cho phép introspection client cụ thể và output `active` phù hợp. Không gửi token production thật tới dịch vụ debug bên ngoài hoặc log CI.

## 10. Mô hình xác thực trong Spring Security

### 10.1. Tên các thành phần

Luồng Servlet thông thường:

```text
HTTP request: Authorization: Bearer opaque-access-token
        |
        v
BearerTokenAuthenticationFilter
        |
        v
BearerTokenAuthenticationToken (chưa được xác thực)
        |
        v
AuthenticationManager
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
OpaqueTokenIntrospector.introspect(token)
        |
        +--> HTTPS POST tới Authorization Server
        |
        +--> active=false / lỗi -> Authentication không thành công
        |
        +--> active=true + attributes / authorities
        |
        v
BearerTokenAuthentication
        |
        v
SecurityContext
        |
        v
AuthorizationFilter / Method Security
        |
        v
Object-level business policy
```

**Không có `JwtDecoder` trong đường xác thực opaque mặc định**. Nếu bạn thấy một cấu hình chỉ có `oauth2ResourceServer().jwt()` trong khi AS phát hành opaque token, API sẽ cố xử lý token như JWT và thường không xác thực được.

### 10.2. Authentication không thay Authorization

`OpaqueTokenIntrospector` trả về principal và authorities sau introspection. Nó không quyết định một user được xem bản ghi order ID nào.

Ví dụ token active, có `SCOPE_orders.read`, nhưng caller yêu cầu đơn hàng của tenant khác:

```text
Authentication        : hợp lệ
Functional authorization: có SCOPE_orders.read
Object authorization  : DENY (khác tenant/owner)
```

Service/domain vẫn phải kiểm tra tenant, ownership, trạng thái tài nguyên và client policy. Nếu thiếu kiểm tra object, API có thể mắc **BOLA/IDOR** dù mọi access token đều được introspect đúng.

## 11. Xác thực token active, quyền và metadata còn lại

### 11.1. `active` nên được hiểu như thế nào?

RFC 7662 cho phép Authorization Server tính `active` từ những điều kiện mà nó quản lý, chẳng hạn tồn tại, thời hạn hoặc trạng thái thu hồi. Resource Server tin kết quả **trong ngữ cảnh caller được phép introspect**, không tự suy diễn trạng thái token từ hình thức chuỗi.

Không chấp nhận nếu:

- Response thiếu `active` hoặc `active` không phải giá trị boolean theo hợp đồng.
- `active=false`.
- Không thể xác thực được introspection client.
- Kết nối TLS không được xác minh.
- Response không thể parse hoặc endpoint không đáng tin.
- Các điều kiện bổ sung bắt buộc của API không được thỏa.

### 11.2. Scope mapping

Theo RFC 7662, `scope` thường là string phân cách bằng dấu cách:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

Spring Security có thể ánh xạ thành `SCOPE_orders.read` và `SCOPE_orders.write`.

Tuy nhiên nếu provider sử dụng định dạng role/custom claim khác, đừng mặc định Spring sẽ biến mọi field thành authorities. Cần có adapter mapping rõ ràng khi hợp đồng metadata của AS không phù hợp cơ chế mặc định.

### 11.3. Kiểm tra audience và issuer

**Opaque token không đồng nghĩa bỏ kiểm tra phạm vi resource.**

Nếu introspection response có:

```json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read"
}
```

Orders API không nên nhận token đó chỉ vì có scope trùng tên; `aud` xác định token được phát hành cho API khác.

Cần thống nhất AS–RS:

- AS trả `aud`/`iss`/`token_type` theo hợp đồng hay không?
- Nếu không có `aud`, AS có **bảo đảm quyền introspection client chỉ với token dành cho Orders API** không?
- Client `orders-api-introspector` có thể introspect token thuộc resource khác không?
- Nếu có nhiều issuer/tenant, RS làm sao xác định đúng AS và chính sách?
- Nếu thuộc tính bắt buộc thiếu hoặc không đúng kiểu, sẽ **fail closed** như thế nào?

Không âm thầm bỏ audience validation vì introspection response chỉ có `active` và `scope`. Nếu resource isolation là yêu cầu, phải thiết kế nguồn bằng chứng tin cậy cho nó ở AS/RS.

## 12. Thêm ràng buộc audience ở custom OpaqueTokenIntrospector

Spring Boot hỗ trợ tự cấu hình introspector dựa trên ba thuộc tính nêu trên. Khi cần kiểm tra thêm metadata, ứng dụng có thể tạo một bean `OpaqueTokenIntrospector` tùy chỉnh.

Ví dụ dưới đây dùng `NimbusOpaqueTokenIntrospector`, một implementation quen thuộc trong dòng Spring Security 6.x; **API triển khai có thể thay đổi ở phiên bản mới**, vì vậy kiểm tra dependencies/phương thức builder tương ứng khi áp dụng. Mục đích là minh họa **decorator**: gọi introspection chuẩn trước, sau đó kiểm tra hợp đồng audience.

```java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class OrdersIntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String introspectionClientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String introspectionClientSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                introspectionClientId,
                introspectionClientSecret
            );

        return token -> {
            // Delegate chịu trách nhiệm HTTP introspection và active status.
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Object rawAudience = principal.getAttribute("aud");
            boolean forOrdersApi = false;

            if (rawAudience instanceof String singleAudience) {
                forOrdersApi = "orders-api".equals(singleAudience);
            } else if (rawAudience instanceof Collection<?> audiences) {
                forOrdersApi = audiences.contains("orders-api");
            }

            if (!forOrdersApi) {
                throw new BadOpaqueTokenException(
                    "Introspected token is not for orders-api"
                );
            }

            return principal;
        };
    }
}
```

Giải thích:

1. `NimbusOpaqueTokenIntrospector` gửi token tới URI cấu hình và xác thực với client ID/secret phù hợp.
2. Nếu token không active, delegate sẽ không trả principal xác thực thành công.
3. Khi nhận principal, wrapper đọc attribute `aud`.
4. Nếu `aud` không chỉ ra `orders-api` theo cấu trúc đã thỏa thuận, wrapper từ chối token.
5. Sau đó `OpaqueTokenAuthenticationProvider` mới chuyển principal thành Authentication.

**Giới hạn của ví dụ:** nó giả định AS trả `aud` dưới dạng string hoặc collection. Hợp đồng thật có thể yêu cầu kiểm tra `iss`, `exp`, `client_id`, token type, tenant và policy thêm. Không nên chọn từ chối/cho phép theo thuộc tính mà AS không cam kết.

**Lưu ý về tự cấu hình:** khi ứng dụng tự đăng ký bean `OpaqueTokenIntrospector`, Spring Boot có thể dùng bean đó thay vì auto-configured introspector. Vì vậy custom implementation phải **giữ đầy đủ phần kiểm tra active, client authentication, TLS và error handling**, không chỉ trả principal “hợp lệ” khi thấy chuỗi token đúng định dạng.

### 12.1. Không dựng principal từ token text mà bỏ introspection

Một anti-pattern:

```java
// KHÔNG làm như sau trong hệ thống thực:
return token -> new DefaultOAuth2AuthenticatedPrincipal(
    "someone",
    Map.of("scope", "orders.admin"),
    List.of(new SimpleGrantedAuthority("SCOPE_orders.admin"))
);
```

Đây là ví dụ **cố ý sai**: nó bỏ qua AS, chấp nhận mọi bearer token và cấp quyền. Một custom introspector phải dựa vào kết quả introspection đáng tin hoặc cơ chế xác minh khác được thiết kế rõ ràng, không tự “dịch token string thành quyền”.

## 13. Tùy chỉnh authorities và principal cho opaque token

Không phải Authorization Server nào cũng trả scope và role theo cùng một cấu trúc. Nếu AS trả:

```json
{
  "active": true,
  "sub": "customer-42",
  "scope": "orders.read",
  "permissions": ["orders.export"],
  "tenant_id": "tenant-a"
}
```

và Orders API muốn thêm `PERMISSION_orders.export`, có thể thiết kế wrapper introspector đọc `permissions`, xây lại principal giữ attributes đã xác minh và hợp nhất authorities.

Một cách tiếp cận khái niệm:

```text
Introspection response đã tin cậy
       |
       +--> scope -> SCOPE_orders.read
       |
       +--> permissions được cho phép -> PERMISSION_orders.export
       |
       +--> principal sub, tenant_id
       |
       v
OAuth2AuthenticatedPrincipal với authorities đúng hợp đồng
       |
       v
BearerTokenAuthentication
```

Yêu cầu an toàn:

- Không biến mọi chuỗi `ADMIN` hoặc `SUPERUSER` thành role toàn hệ thống.
- Giới hạn quyền theo resource/tenant.
- Giữ authorities scope cơ bản khi thêm quyền tùy chỉnh.
- Từ chối hoặc bỏ qua giá trị permissions sai kiểu ngoài hợp đồng.
- Không dùng username/email tùy ý làm định danh nghiệp vụ nếu có `issuer+subject` ổn định hơn.
- Không cấp quyền khi introspection fail hoặc thiếu metadata bắt buộc.

Với phương thức introspection tùy biến, hãy dùng abstraction của Spring Security theo phiên bản thư viện để trả về `OAuth2AuthenticatedPrincipal` có danh sách `GrantedAuthority` rõ ràng. Không ghi client secret/token vào attributes để controller đọc.

## 14. Trạng thái lỗi: 401, 403 và lỗi dịch vụ introspection

Một vấn đề vận hành quan trọng là phân biệt **lỗi bearer token của caller** với **lỗi credential hoặc mạng của Resource Server**.

| Tình huống | Xảy ra ở đâu? | Cách diễn giải |
|---|---|---|
| Không có Bearer token ở API bảo vệ | HTTP inbound | Caller chưa cung cấp credential; thường trả `401` |
| Introspection trả `active=false` | AS xác nhận token không active | Token không được chấp nhận; thường `401 invalid_token` |
| Token active nhưng thiếu `orders.read` | AuthorizationFilter / policy | Caller đã xác thực nhưng thiếu scope; thường `403` |
| Token active, scope đủ nhưng khác owner/tenant | Domain service | Từ chối `403` hoặc `404` theo chính sách |
| Introspection trả HTTP `401` cho client Basic | RS → AS | Có thể sai introspection client-id/secret hoặc phương thức auth; **không** coi đó là token inactive |
| Introspection endpoint timeout/`5xx` | RS → AS | Lỗi phụ thuộc hạ tầng; **không** xác thực token bằng suy đoán |
| TLS certificate không tin cậy | RS → AS | Lỗi kênh xác thực; không được bỏ TLS validation |
| JSON malformed/missing active | AS/proxy response | Không đủ bằng chứng để xác thực; từ chối |
| Rate limit `429` từ AS | RS → AS | Cần xử lý capacity/backoff; không coi token automatically valid |

### 14.1. HTTP Basic 401 không phải bearer 401

Giả sử Resource Server gọi introspection với secret sai:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
```

Đây là **Authorization Server từ chối xác thực Resource Server**. Nó khác với Orders API trả `401` cho caller khi access token inactive.

Nếu trộn hai loại này, vận hành có thể đổ lỗi “user gửi token sai” trong khi mọi token đều thất bại vì secret introspection đã hết hiệu lực. Cần log phân loại **lỗi outbound client authentication** mà không ghi secret.

### 14.2. Sai khác giữa 401 và 403 ở inbound API

Ví dụ thiếu token/invalid token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Ví dụ token active nhưng thiếu scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Header/challenge cụ thể tùy cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` của Spring Security. Nếu token hoàn toàn không có, bearer challenge có thể khác so với invalid-token challenge; không mặc định tất cả lỗi 401 có cùng thông điệp.

### 14.3. Lỗi AS không hoạt động nên trả 401 hay 503?

Đây là **quyết định chính sách ứng dụng và mapping lỗi**, không phải quy tắc tự động cố định.

- Nếu không thể introspect token, RS **không có bằng chứng để authenticate** caller.
- Không được fallback sang `permitAll`, “active=true” mặc định hoặc dùng một client-secret tạm trong code.
- Có thể ánh xạ lỗi phụ thuộc AS sang `503 Service Unavailable` khi hạ tầng không sẵn sàng, đồng thời giữ lỗi token thực sự ở `401`.
- Cần hiểu hành vi mặc định và exception mapping của phiên bản Spring Security/HTTP client đang dùng; không tự tuyên bố framework luôn trả một status cố định cho timeout.

Mục tiêu là **fail closed về quyền truy cập** đồng thời có thông tin vận hành phân biệt lỗi caller và lỗi hệ thống.

## 15. Nguy cơ SSRF và nhầm endpoint introspection

`introspection-uri` phải là một URL **do ứng dụng hoặc tổ chức cấu hình và cho phép**, không được suy ra tùy ý từ:

- HTTP header của caller.
- Query parameter `introspection_url`.
- Một claim chưa được xác minh trong access token.
- Hostname do client tự cung cấp.
- Metadata chưa kiểm chứng từ một issuer ngoài allowlist.

Nếu API cho client chọn URI mà server sẽ POST token tới, nó tạo nguy cơ **SSRF** và **rò bearer token/introspection credentials** sang endpoint của kẻ tấn công.

Trong multi-issuer/multi-tenant, cần định tuyến token tới đúng AS bằng cấu hình tin cậy, không “thử token lần lượt với mọi AS” một cách vô kiểm soát. Việc gửi access token thuộc issuer A tới introspection endpoint của issuer B còn có thể lộ thông tin cho bên không được phép nhận token.

### 15.1. Mỗi môi trường một introspection client

Ví dụ:

| Môi trường | `introspection-uri` | Client identity |
|---|---|---|
| Development | `https://login.dev.example.com/oauth2/introspect` | `orders-api-introspector-dev` |
| Staging | `https://login.staging.example.com/oauth2/introspect` | `orders-api-introspector-staging` |
| Production | `https://login.example.com/oauth2/introspect` | `orders-api-introspector-prod` |

Mỗi môi trường nên có secret/credential riêng, chính sách TLS và phạm vi token riêng; không dùng một client secret production trên laptop phát triển.

**Nếu issuer có đường dẫn realm/tenant**, endpoint introspection cũng có thể mang đường dẫn đó theo nhà cung cấp, ví dụ `/realms/orders/protocol/openid-connect/token/introspect`. Cần xác nhận URL thực từ provider và ngữ cảnh tenant, không ghép đường dẫn theo phỏng đoán.

## 16. Secret manager, rotation và quyền bảo vệ introspection client

### 16.1. Chuẩn bị credential

Đội quản trị Authorization Server cần đăng ký introspection client với chính sách phù hợp:

1. Gán client ID có nghĩa cho Orders API hoặc nhóm Resource Server cụ thể.
2. Chọn phương thức client authentication (Basic secret, private_key_jwt, mTLS...).
3. Cấp quyền chỉ introspect các token cần thiết, nếu AS hỗ trợ policy đó.
4. Sinh và lưu secret bằng cơ chế quản lý bí mật của tổ chức.
5. Giao thông tin endpoint, audience/resource và claim contract cho đội Resource Server.
6. Ghi rõ kế hoạch rotation, thời hạn và quy trình khôi phục khi credential lỗi.
7. Bật logging/audit của endpoint ở mức an toàn, không ghi token/raw client-secret.

### 16.2. Rotation secret không được làm gián đoạn mọi request

Một lộ trình thường gặp:

```text
T0: Resource Server dùng secret A
T1: Authorization Server tạo secret B (nếu cho phép overlap)
T2: Phân phối B an toàn tới tất cả RS instances
T3: Chuyển RS sang B và xác nhận introspection thành công
T4: Thu hồi A sau khi tất cả instances đã chuyển
```

Nếu AS không hỗ trợ nhiều secret cùng hoạt động, cần một kế hoạch triển khai an toàn khác với cửa sổ chuyển đổi/phục hồi được kiểm soát.

Không ghi cả secret A và B vào app logs để “debug”. Theo dõi bằng ID/version của secret hoặc thông tin cấu hình không nhạy cảm.

### 16.3. Credential bị lộ khác access token bị lộ

Nếu **client-secret của introspection client** bị lộ, kẻ tấn công có thể giả làm Resource Server ở **introspection endpoint** trong phạm vi quyền client được cấp. Điều này không tự đồng nghĩa kẻ đó có thể ký JWT mới hoặc cấp access token mới; phạm vi ảnh hưởng phụ thuộc quyền và mô hình AS.

Nếu **bearer access token** bị lộ, người nắm token có thể cố dùng nó tại API trong thời gian nó còn active, trừ khi bị sender-constrained hoặc các cơ chế bảo vệ khác.

Cả hai đều nghiêm trọng nhưng cần **quy trình ứng cứu khác nhau**: revoke/rotate introspection credential và kiểm tra audit quyền introspection, hoặc revoke access token và điều tra truy cập dữ liệu.

## 17. Hiệu năng: một request API có thể cần một request introspection

Một ưu điểm của JWT tự xác minh là RS thường có thể xác minh offline bằng public key đã cache. Với opaque token, introspection thường tạo network dependency:

```text
N API requests per second
          |
          v
N introspection calls per second (nếu không cache)
          |
          v
Authorization Server capacity, network latency, TLS, rate limits
```

Nếu Orders API nhận 2.000 RPS và mỗi request đều introspect, AS có thể phải xử lý lượng truy vấn tương tự **trừ khi có cache hoặc cơ chế tối ưu cụ thể**.

### 17.1. Cache introspection: nhanh nhưng có nguy cơ stale

Caching theo token có thể giảm latency và tải AS. Tuy vậy:

- Token đã bị revoke vẫn có thể được chấp nhận cho đến khi cache entry hết hạn.
- `exp` cần được tôn trọng; cache không được sống lâu hơn hạn hợp lệ còn lại.
- Cache key/token là dữ liệu nhạy cảm; tránh lộ plaintext trong metrics, dump hay log.
- Cần giới hạn kích thước và chống memory exhaustion do token ngẫu nhiên.
- Các thuộc tính role/tenant có thể thay đổi trong lúc entry còn cache.
- Hệ thống có yêu cầu revocation gần tức thì có thể không cho phép cache dài.

Một nguyên tắc thiết kế cache:

```text
cacheTtl <= min(
    configuredMaxCacheTtl,
    remainingTimeToExp,
    acceptableRevocationDelay
)
```

Đây là **hướng dẫn chính sách**; nếu introspection không cung cấp `exp`, RS phải có quy tắc fail closed hoặc TTL phù hợp với rủi ro, không giả định token còn hạn vô hạn.

**Mặc định đừng tuyên bố Spring Security tự cache introspection response.** Khi thêm cache bằng decorator hoặc giải pháp hạ tầng, cần thiết kế và test rõ tác động với revocation.

### 17.2. Timeouts và circuit breaker

Để tránh treo toàn bộ thread HTTP:

- Đặt timeout kết nối/đọc phù hợp với SLA của API và AS.
- Giới hạn concurrency của calls tới introspection endpoint.
- Dùng retry có điều kiện, backoff/jitter khi hợp lý; không retry bão gây quá tải AS.
- Có circuit breaker để bảo vệ capacity, **nhưng khi breaker mở không tự chấp nhận token**.
- Giám sát latency/timeout/error rate theo loại lỗi.
- Thiết kế readiness/dependency strategy khi AS không sẵn sàng.

Không dùng 401 của client authentication làm lỗi có thể retry vô hạn; cần phân loại và khắc phục secret/policy. Các thông số kỹ thuật như timeout/cache tùy introspector/HTTP client phiên bản và không nên giả định property mặc định nào áp dụng cho mọi project.

## 18. Khi nào chọn opaque token thay vì JWT tự xác minh?

| Tiêu chí | Opaque token + introspection | Signed JWT + local validation |
|---|---|---|
| Cách xác thực token | RS gọi AS/introspection endpoint | RS tự xác minh chữ ký qua khóa đáng tin |
| Network dependency khi xác thực | Thường có, trừ cache/cách thiết kế khác | Thường không cần per-request network |
| Cập nhật trạng thái revocation | Có thể phản ánh khi introspect lại | JWT local validation thường chấp nhận tới `exp` nếu không có cơ chế revoke riêng |
| Secret của AS cần đưa cho RS? | Không cần JWT signing private key; nhưng cần credential introspection nếu AS yêu cầu | Chỉ public key/JWKS với chữ ký bất đối xứng |
| Thông tin token ở phía caller | Chuỗi có thể không đọc được ý nghĩa | Payload JWS có thể đọc được bằng Base64URL, không được mã hóa |
| Áp policy tại AS | Có thể tập trung tại introspection, tùy AS | Cần claim/validation và các nguồn policy bổ sung |
| Latency và availability | Phụ thuộc AS và mạng | Tối ưu cho xác minh cục bộ |
| Vận hành nhiều Resource Server | Quản lý client credentials/AS capacity | Quản lý public keys, issuer, rotation |

Không có lựa chọn nào luôn tốt nhất. Opaque + introspection phù hợp khi cần quản lý trạng thái token tập trung, hạn chế lộ claims trong token hoặc AS cung cấp cơ chế xác minh trực tuyến. JWT local phù hợp khi cần giảm phụ thuộc AS cho mỗi request nhưng phải quản lý revocation/claims freshness riêng.

**Quan trọng:** introspection không tự giải quyết mọi bài toán authorization. Dù token active, Resource Server vẫn phải áp quyền chức năng và quyền đối tượng.

## 19. Những vấn đề riêng với OAuth scope và OIDC

### 19.1. OAuth access token khác OIDC ID token

OIDC ID token chứng minh kết quả đăng nhập cho **OIDC client**, còn access token dùng để gọi **Resource Server**.

Một AS có thể hỗ trợ introspection cho nhiều loại token, nhưng Orders API phải yêu cầu đúng **access token** theo contract; không chấp nhận ID token hoặc refresh token như bearer access token chỉ vì một endpoint introspection trả metadata.

Nếu introspection response có `token_type` hoặc metadata phân loại, áp dụng kiểm tra phù hợp. Cần làm rõ với AS rằng `active=true` được trả cho access token dùng tại API này, không cho token dùng ở mục đích khác.

### 19.2. Client Credentials không có người dùng cuối

Ví dụ introspection của token máy:

```json
{
  "active": true,
  "client_id": "nightly-worker",
  "sub": "nightly-worker",
  "scope": "orders.export",
  "aud": ["orders-api"],
  "exp": 2000000000
}
```

`sub` có thể đại diện service/client, không phải end-user. Resource Server cần áp **client allowlist**, tenant và job policy; không dùng cùng quy tắc customer ownership cho mọi token.

### 19.3. Không coi scope là quyền trên mọi bản ghi

Một token có `scope=orders.read` vẫn không được đọc order thuộc customer khác nếu API không cấp quyền đó. Cần kết hợp:

```text
active token
AND trusted AS
AND resource/audience is orders-api
AND SCOPE_orders.read
AND actor can read this order
AND tenant and business rules allow
```

Nếu thiếu bước object authorization, ứng dụng có thể gặp BOLA dù opaque token được introspect đúng.

## 20. Kiểm thử cấu hình introspection

### 20.1. Unit test cấp service/policy

Có thể mô phỏng `OAuth2AuthenticatedPrincipal` và authorities để test logic phân quyền. Test này không gọi AS và không kiểm tra HTTP Basic/TLS; nó chỉ kiểm tra mapping/authorization.

### 20.2. Spring Security Test với opaque token giả

Spring Security Test hỗ trợ `opaqueToken()` cho MockMvc, giúp tạo authentication thử nghiệm:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

mvc.perform(get("/api/orders/42")
    .with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")
    )))
    .andExpect(status().isOk());
```

Đây là **đoạn minh họa**, giả định endpoint/order test được phép đọc và test class đã cấu hình `MockMvc`, data fixtures và dependencies phù hợp.

**Giới hạn:** `opaqueToken()` tạo SecurityContext/principal trong test; nó **không chứng minh** app đã gửi POST tới AS, Basic credentials đúng, TLS được xác minh hay `active=false` được xử lý đúng.

### 20.3. Integration test với fake introspection server

Một bộ test thật sự cho Resource Server có thể dùng một HTTP test server mô phỏng endpoint introspection, nhưng chỉ trong môi trường test biệt lập. Ví dụ các trường hợp:

| Đầu vào | Introspection mock | Mong đợi |
|---|---|---|
| Bearer token hợp lệ | `200 {"active":true,"scope":"orders.read","aud":["orders-api"]}` | Request qua auth, tiếp tục object policy |
| Bearer token bị thu hồi | `200 {"active":false}` | Request không authenticated thành công |
| Token còn active thiếu scope | `200 {"active":true,"scope":"orders.read"}` | POST endpoint yêu cầu `orders.write` bị chặn |
| Token active sai audience | `200 ... "aud":["billing-api"]` | Bị validator/decorator từ chối |
| Client ID/secret introspection sai | `401` từ mock AS | Không chấp nhận token |
| AS trả lỗi `500` | Server-side error | Fail closed, phân loại lỗi dependency |
| AS timeout | Không có phản hồi | Không cấp quyền và không treo thread vô hạn |
| TLS certificate không tin cậy | TLS handshake fail | Không bypass TLS |
| Response malformed / thiếu `active` | JSON sai hợp đồng | Không coi là active |
| Tenant/owner của order sai | Token active và scope đủ | Domain policy vẫn từ chối |

Để test **HTTP thật**, gửi header `Authorization: Bearer <TEST_TOKEN>` đến Spring Security filter chain thực, cấu hình fake AS có endpoint và client auth được kiểm soát, kiểm tra request gửi đi và response; không dùng `opaqueToken()` làm bằng chứng per-request introspection.

### 20.4. Kiểm tra HTTP Basic client authentication

Ở fake AS, nên xác nhận:

- Có client authentication theo phương thức đã đăng ký.
- Client ID đúng.
- Secret đúng nhưng không xuất hiện trong logs/assertion output.
- Request có `Content-Type: application/x-www-form-urlencoded`.
- Body có `token` đúng test token.
- Response `active` được xử lý theo boolean.
- Một caller không được cấp quyền introspection bị từ chối.
- Outbound TLS trust và timeout có cấu hình phù hợp với môi trường thật.

Khi mock secret, dùng giá trị thử nghiệm vô hại, không sao chép secret production vào fixture.

## 21. Các lỗi vận hành thường gặp

### 21.1. Resource Server trả 401 với mọi token dù AS vừa phát hành

Có thể là:

- `introspection-uri` trỏ sai host/realm/môi trường.
- AS không nhận client ID/secret hoặc introspection client chưa được cấp quyền.
- Request dùng sai client authentication method.
- Token audience/issuer không phù hợp với introspection policy của AS.
- Spring cấu hình `jwt()` thay vì `opaqueToken()`.
- Custom introspector/validator từ chối metadata bắt buộc.

Cần xem **log server-side an toàn** từ RS và AS, phân biệt token inactive với client authentication error. Không in token thật hoặc secret để “so sánh”.

### 21.2. Curl trên laptop thành công, Java container thất bại

Thường do:

- JVM truststore thiếu private CA.
- Container/pod không có egress/DNS tới AS.
- Proxy của container khác laptop.
- SNI/hostname certificate mismatch.
- Network policy/firewall chỉ chặn workload.
- URL được cấu hình trong pod khác với lệnh kiểm tra trên laptop.

Cần kiểm tra từ **môi trường mạng/TLS tương đương với pod thực sự**, không bật `--insecure` để bỏ qua vấn đề.

### 21.3. Hôm qua API hoạt động, sau rotation secret thì mọi request lỗi

Kiểm tra:

1. Secret mới đã được AS kích hoạt chưa?
2. Secret đã được phân phối cho **mọi instance** chưa?
3. Có pod cũ/rollout lỗi vẫn giữ secret bị revoke không?
4. Client ID có bị thay nhầm cùng secret không?
5. Có cấu hình basic authentication hoặc token endpoint khác mà ứng dụng đang dùng nhầm không?

Không nên khắc phục bằng cách chuyển API sang `permitAll()`; hãy khôi phục introspection authentication đúng.

### 21.4. Token active nhưng API trả 403

Một số lý do:

- Scope không chứa authority endpoint yêu cầu.
- Prefix `SCOPE_` không được chuyển đổi đúng.
- Introspection response không có trường role/permission mà custom converter đòi.
- Client không được phép truy cập chức năng dù scope có mặt.
- Tenant/ownership/resource policy từ chối.

Đây có thể là **authorization failure** hợp lệ, không nhất thiết là lỗi `introspection-uri`.

### 21.5. AS rate limit nhiều request sau khi tăng traffic

Opaque introspection tạo phụ thuộc tải. Cần quan sát:

- Số introspection call/sec theo RS/client.
- Latency p50/p95/p99 và timeout.
- Tỷ lệ token inactive vs hoạt động.
- AS rate limits/client quotas.
- Cache/revocation tradeoff.
- Retry storm, số HTTP connections và concurrency.

Không tăng cache TTL tùy tiện nếu nghiệp vụ cần revocation gần tức thì.

## 22. Checklist triển khai theo môi trường

| Kiểm tra | Development | Staging | Production |
|---|---|---|---|
| `introspection-uri` đúng issuer/realm | Bắt buộc | Bắt buộc | Bắt buộc |
| HTTPS certificate/SAN/truststore hợp lệ | Có | Có | Có |
| Client ID/secret riêng và đủ quyền introspect | Có | Có | Có |
| Secret được inject an toàn, không commit/log | Có | Có | Có |
| Không trộn token dev/staging/prod | Có | Có | Có |
| Kết quả `active=false` bị từ chối | Có | Có | Có |
| Scope ánh xạ thành authorities đúng hợp đồng | Có | Có | Có |
| Audience/resource policy được thực thi | Có | Có | Có |
| Client/subject/tenant/object policy được thực thi | Có | Có | Có |
| AS errors, timeout, rate limit fail closed | Có | Có | Có |
| Kế hoạch rotation client credentials | Có | Có | Có |
| Giám sát outage, latency, lỗi Basic credentials | Có | Có | Có |
| Không lộ raw token trong logs/traces | Có | Có | Có |
| Cache TTL phù hợp nhu cầu revocation | Có | Có | Có |

Bảng này là **các điều kiện cần thực thi**, không phải kết quả đo/đánh giá sẵn ở bất kỳ môi trường nào.

## 23. Một ví dụ quyết định xuyên suốt

Giả sử người dùng có token `T1`, Orders API dùng introspection client `orders-api-introspector`.

**Bước 1 — Request đến Orders API**

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer T1
```

**Bước 2 — Orders API introspect**

Orders API gửi `T1` qua HTTPS trong form body tới endpoint `https://login.example.com/oauth2/introspect`; đồng thời xác thực bằng client ID/secret **của chính Orders API**.

**Bước 3 — AS trả trạng thái**

```json
{
  "active": true,
  "client_id": "storefront-web",
  "scope": "orders.read",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
```

**Bước 4 — Spring tạo Authentication**

```text
Principal:
  subject = customer-42
  client_id = storefront-web
  tenant_id = tenant-a

GrantedAuthorities:
  SCOPE_orders.read
```

**Bước 5 — Service kiểm tra order 42**

Cơ sở dữ liệu cho biết order 42 thuộc customer-42 và tenant-a, trạng thái cho phép đọc. Khi đó có thể trả dữ liệu nếu mọi điều kiện nghiệp vụ khác đạt.

Nếu cùng token được dùng cho order 99 thuộc tenant-b, **scope vẫn đúng** nhưng service phải từ chối. Nếu `active=false`, request bị từ chối **trước** bước object policy. Nếu `client-secret` introspection sai, AS từ chối Orders API và API phải fail closed, không đoán token hợp lệ từ chuỗi `T1`.

Đây là sự phân tách ba trách nhiệm:

```text
Bearer credential từ caller
         |
         v
Resource Server xác thực với Authorization Server
(introspection-uri + client-id/client-secret)
         |
         v
Authorization Server xác nhận token active
         |
         v
Spring tạo Authentication với authorities
         |
         v
API và service thực thi quyền chức năng + object policy
```

## 24. Ghi nhớ

- **`introspection-uri`** là endpoint RFC 7662 của Authorization Server; Resource Server gọi nó để hỏi trạng thái access token.
- **`client-id` và `client-secret` trong nhánh `opaquetoken`** là credential để **Resource Server xác thực với introspection endpoint**, không phải access token của caller.
- **`client_id` trong response** thường chỉ OAuth client đã được cấp token; nó có ý nghĩa khác với `client-id` trong cấu hình Resource Server.
- Caller gửi `Authorization: Bearer <access token>` tới API; API dùng **client authentication riêng** khi hỏi AS.
- **`active=true` là điều kiện nền tảng nhưng chưa đủ**: API còn kiểm tra scope, audience/resource, client/subject, tenant, ownership và nghiệp vụ.
- **`active=false` hoặc lỗi introspection không thể được diễn giải thành “cho phép”**; phải fail closed.
- **TLS phải được xác minh** vì introspection request mang cả token và credential của RS.
- Spring Security Servlet dùng `OpaqueTokenIntrospector` và `OpaqueTokenAuthenticationProvider`; kết quả thường là `BearerTokenAuthentication` với `OAuth2AuthenticatedPrincipal`, khác luồng `JwtDecoder`.
- Opaque introspection tạo phụ thuộc network/AS, cần thiết kế timeout, capacity, cache và revocation tradeoff.
- Bảo vệ introspection secret, tách quyền theo API/môi trường, rotate và giám sát cẩn thận.
- Unit/MockMvc `opaqueToken()` không tự kiểm thử HTTP introspection thật; cần integration test bằng fake AS nếu muốn kiểm tra Basic/TLS/active/network.

## 25. Tài liệu chuẩn và tham chiếu

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): endpoint, authentication/authorization của caller introspection, request/response và trường `active`.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client authentication, scope và token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token trong `Authorization` header và lỗi `invalid_token` / `insufficient_scope`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata có thể công bố introspection endpoint và các phương thức client authentication được hỗ trợ.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): cấu hình và kiến trúc opaque token introspection cho Servlet.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bearer authentication, SecurityContext và authorization.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): quyền endpoint và scope authorities.

**Kết luận:** Trong Resource Server dùng opaque token, **access token của caller và credential introspection của API là hai danh tính khác nhau ở hai kết nối khác nhau**. Cấu hình đúng `introspection-uri`, `client-id`, `client-secret` giúp Spring Security hỏi đúng Authorization Server bằng danh tính được cấp quyền; phản hồi introspection chỉ cung cấp cơ sở để xác thực token. Quyền được truy cập tài nguyên vẫn cần được quyết định bằng **scope, audience, subject/client và chính sách nghiệp vụ của Resource Server**.
