# Introspection endpoint

Một API nhận access token từ client, nhưng **làm sao biết token còn được authorization server chấp nhận, được cấp cho API nào và có phạm vi quyền gì?** Nếu token là JWT có chữ ký, resource server có thể xác minh nhiều thuộc tính bằng khóa công khai và claims. Nếu token là **opaque token** không có cấu trúc công khai, resource server thường phải hỏi hệ thống phát hành. **OAuth 2.0 Token Introspection** là cơ chế chuẩn cho cuộc trao đổi đó.

**Introspection endpoint** do **authorization server (AS)** cung cấp để một bên được phép, thường là **resource server (RS)**, gửi token cần kiểm tra và nhận metadata, quan trọng nhất là trường boolean **`active`**. Nó giúp API đánh giá token còn được chấp nhận hay đã hết hạn, bị thu hồi, không được phát hành hoặc không phù hợp với bối cảnh. Nhưng **`active=true` không có nghĩa được truy cập mọi API và mọi dữ liệu**.

Đây là bài học trong chương **OAuth2 roles** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung tập trung vào vai trò các bên trong OAuth 2.0/OIDC, JWT và opaque token, cách AS phát hành và RS xác minh token, kiểm tra scope/audience, caching, thu hồi, lưu trữ và phòng chống token bị đánh cắp hoặc phát lại.

> **Nguyên tắc:** Introspection cho biết **trạng thái và metadata token từ AS qua kênh tin cậy**. Resource server vẫn chịu trách nhiệm về audience, scope, principal, tenant và quyền trên tài nguyên.

## 1. Introspection nằm ở đâu trong bốn vai trò OAuth 2.0?

OAuth 2.0 xác định bốn vai trò logic:

| Vai trò | Trách nhiệm | Quan hệ với introspection |
| --- | --- | --- |
| **Resource owner** | Chủ thể có thể cấp quyền truy cập dữ liệu bảo vệ, thường là user | Thường không gọi introspection trực tiếp |
| **Client** | Ứng dụng được cấp authorization grant và dùng access token để gọi API | Gửi token tới RS, thường **không cần** tự introspect |
| **Authorization server (AS)** | Phát hành token, quản lý grant/trạng thái, cung cấp khóa/metadata | **Cung cấp introspection endpoint** |
| **Resource server (RS)** | API bảo vệ tài nguyên và xét quyền truy cập | **Gọi introspection** khi cơ chế token yêu cầu |

Các vai trò **không bắt buộc là bốn máy chủ riêng**. Một gateway có thể đóng vai RS để kiểm tra access token cho các backend; AS và RS cũng có thể nằm trong một hệ thống. Điều quan trọng là **ranh giới tin cậy và trách nhiệm**, không phải số lượng process.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource owner (user)
    participant C as OAuth client
    participant AS as Authorization server
    participant RS as Resource server
    U->>C: Dùng ứng dụng
    C->>AS: Hoàn thành OAuth grant
    AS-->>C: Opaque/JWT access token
    C->>RS: GET /orders + Bearer token
    RS->>AS: POST introspection + xác thực RS
    AS->>AS: Kiểm tra token, grant, hạn và policy
    AS-->>RS: active + metadata được phép
    RS->>RS: Check audience, scope, tenant, ownership
    RS-->>C: 200 / 401 / 403
~~~

Introspection là trao đổi **back-channel giữa các thành phần server được tin**. Không nên thiết kế cho trình duyệt tự gọi introspection bằng client secret của RS, vì secret của RS không được đặt trong JavaScript/public client.

## 2. RFC 7662 định nghĩa endpoint này như thế nào?

**RFC 7662 — OAuth 2.0 Token Introspection** định nghĩa endpoint HTTP trả JSON chứa:

- **`active`**: trường boolean bắt buộc, cho biết token đang được AS xem là hoạt động trong ngữ cảnh truy vấn;
- Metadata tùy chọn: `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss`, `jti`;
- Trường mở rộng theo hợp đồng, ví dụ `tenant_id`, `permissions` hoặc confirmation metadata cho token ràng buộc bên gửi.

**Không có URL cố định bắt buộc** như `/oauth2/introspect` trong RFC. Một AS có thể chọn URL khác và công bố qua metadata tin cậy, chẳng hạn `introspection_endpoint` trong OAuth 2.0 Authorization Server Metadata (RFC 8414).

### 2.1. HTTP request minh họa

Giả sử Orders API được AS đăng ký quyền introspect token:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-resource-server-credentials>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<opaque-access-token>&token_type_hint=access_token
~~~

Giải thích:

1. RFC 7662 dùng HTTP **POST**, với form body `application/x-www-form-urlencoded`.
2. Tham số **`token`** là credential cần kiểm tra, **không phải** client secret của RS.
3. **`token_type_hint`** chỉ là gợi ý về loại token, không phải bằng chứng. AS có thể xử lý trường hợp hint sai theo chuẩn.
4. Header Basic trong ví dụ xác thực **resource server với AS**; cách thực tế có thể là client secret, mTLS, private_key_jwt hoặc phương pháp được AS hỗ trợ.
5. **HTTPS** bảo vệ token, RS credentials và metadata; cần xác minh certificate/host của AS.

Đừng gửi token cần introspect trong **query string** hoặc log nguyên body. Nếu dùng Basic, không log `Authorization`; secret chỉ nên được lưu ở backend/secret manager.

### 2.2. Response khi token active

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "orders-web",
  "token_type": "Bearer",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "iss": "https://auth.example.com",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900
}
~~~

Đây là response **minh họa**, không phải schema bắt buộc đầy đủ cho mọi AS. `active=true` là kết luận của **AS theo chính sách và ngữ cảnh truy vấn**, không chỉ là kiểm tra `now < exp`. AS có thể xét token có tồn tại, grant có bị thu hồi, token còn hạn hay người gọi có được nhận thông tin hay không.

### 2.3. Response khi token inactive

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"active": false}
~~~

Token không tồn tại, sai, hết hạn, bị thu hồi hoặc không phù hợp với bên đang introspect đều có thể nhận kết quả `active=false`. **Không suy đoán chính xác nguyên nhân từ trường này.** AS hạn chế metadata của token inactive để giảm nguy cơ endpoint trở thành **token oracle**.

### 2.4. `active=false` khác RS xác thực introspection thất bại

| Tình huống | Kết quả thường gặp | Diễn giải |
| --- | --- | --- |
| RS hợp lệ, token không active | HTTP `200` và `active=false` | Request introspection xử lý được, nhưng token không được chấp nhận |
| RS hợp lệ, token active | HTTP `200` và `active=true` | API cần tiếp tục kiểm tra quyền |
| Credential của RS sai | HTTP `401` hoặc lỗi client authentication | **Không phải** câu trả lời về trạng thái token |
| RS không được phép introspect token/resource đó | Lỗi/hạn chế theo policy AS | Không tiết lộ thông tin token của bên khác |
| AS timeout/5xx | Lỗi hạ tầng/dịch vụ | RS không được tự suy ra token active |

Phản hồi client nhận từ **resource server** khi token không được chấp nhận (thường `401 invalid_token`) là một lớp HTTP khác với kết quả **RS hỏi AS**.

## 3. Introspection cho opaque token và JWT

### 3.1. Opaque access token

Opaque token có thể là một chuỗi ngẫu nhiên:

~~~text
access_token = "opaque-6mQ...P8w"
~~~

Resource server không cần và thường **không thể giải mã cấu trúc nội bộ**. Nó gửi token tới endpoint introspection đáng tin để lấy trạng thái và metadata đã được cấp quyền xem.

Lợi ích:

- AS có thể thu hồi hoặc thay đổi trạng thái token tập trung;
- Token thường ngắn, không cần nhúng danh sách user/tenant/permissions lớn;
- RS không cần triển khai xác minh JWS cho định dạng opaque;
- Có thể áp policy grant, client, session và revocation hiện hành.

Đổi lại, API cần bảo vệ đường mạng/credential tới AS, kiểm soát latency, availability, timeout, rate và cache.

### 3.2. JWT access token

JWT access token đã ký có thể được RS xác minh **offline** bằng JWS signature, algorithm allowlist, khóa issuer, `iss`, `aud`, `exp`, `nbf`, token type và scope. **JWT không bắt buộc phải introspect ở mọi request.**

Một hệ thống **có thể introspect JWT** nếu yêu cầu kiểm tra trạng thái thu hồi/grant hiện hành. Khi đó:

1. AS phải introspect đúng token đang được hỏi, không trộn với token khác;
2. RS phải tin kênh/AS và kiểm tra metadata theo hợp đồng;
3. Nếu policy yêu cầu cả JWT validation và introspection, **không bỏ qua một kiểm tra chỉ vì cái kia thành công**;
4. Khi kết quả mâu thuẫn, áp chính sách deny-by-default, không mở rộng quyền;
5. Audience, scope và quyền trên tài nguyên vẫn cần kiểm tra.

| Tiêu chí | JWT verify offline | Introspection |
| --- | --- | --- |
| Đọc trạng thái token | Claims và chữ ký với khóa tin cậy | AS trả kết luận và metadata |
| Gọi AS mỗi API request | Thường không | Có thể có, trừ cache |
| Biết token đã revoke nhanh | Cần denylist/lookup/version hoặc TTL ngắn | Dễ phản ánh AS hơn nếu cache ngắn |
| Tính sẵn sàng | Ít phụ thuộc AS sau khi có keys | Phụ thuộc AS hoặc cache được kiểm soát |
| Rủi ro bảo mật chính | Sai algorithm/key/issuer/audience/type | Lộ RS secret, metadata, stale cache, fail-open |
| Token trên client | JWT payload có thể đọc | Opaque thường không thể diễn giải |

**Opaque không tự đồng nghĩa thu hồi tức thời**: nếu RS cache `active=true` quá lâu, revocation vẫn có độ trễ. Tương tự JWT có thể bị vô hiệu trước `exp` khi kiến trúc có cơ chế stateful bổ sung.

## 4. `active` bảo đảm gì và không bảo đảm gì?

**`active` là quyết định của AS** trong ngữ cảnh request introspection; không nên giản lược thành:

~~~text
SAI: active = now < exp

KHÁI NIỆM:
active = token tồn tại
      && token/grant còn được AS chấp nhận
      && token nằm trong khoảng hiệu lực
      && trạng thái thu hồi và policy cho phép
      && bên introspect được phép nhận kết quả tương ứng
~~~

Đây là mô tả ý tưởng, không phải thuật toán bắt buộc của RFC 7662.

Tại RS vẫn cần hỏi:

- **`aud`** có bao gồm chính resource server này không?
- **`scope`** có cho phép gọi chức năng, ví dụ `orders.read`, không?
- **`sub`/`client_id`** là user-delegated hay app-only token theo profile?
- **Tenant, membership và ownership** của order có khớp principal không?
- Nếu token dùng **DPoP/mTLS sender binding**, caller có chứng minh sở hữu khóa/chứng chỉ đúng không?

**`active=true` không phải quyết định cuối cùng về object-level authorization.**

## 5. Diễn giải metadata theo hợp đồng AS–RS

| Trường | Ý nghĩa nếu có | Cách sử dụng |
| --- | --- | --- |
| `active` | Boolean trạng thái | Chỉ tiếp tục khi đúng `true` |
| `scope` | Chuỗi các scope được cấp | Kiểm tra `orders.read`, không tin scope client đã yêu cầu |
| `client_id` | Client liên quan đến token | Không suy ra user hoặc quyền toàn hệ thống |
| `token_type` | Loại token, ví dụ Bearer | Kiểm tra theo contract, không tự coi là access-vs-refresh discriminator |
| `sub` | Subject/principal | Có thể là user hoặc service tùy grant/profile |
| `aud` | Audience/resource dự kiến | Phải phù hợp API đang nhận |
| `iss` | Issuer của token | Ràng buộc AS đã được tin |
| `exp`, `nbf`, `iat` | NumericDate epoch seconds | Thời hạn, bắt đầu hiệu lực, phát hành |
| `jti` | ID của token | Audit/denylist/correlation, không mặc nhiên one-time |
| `tenant_id` custom | Ngữ cảnh tenant | Không phải claim chuẩn mọi OAuth; cần kiểm tra tài nguyên |
| `cnf` | Confirmation metadata khi token sender-constrained | Kiểm tra khóa/chứng chỉ thực sự |

**RFC 7662 không yêu cầu mọi active response chứa đủ `iss`, `aud`, `scope`, `exp`.** Vì vậy, trước khi tích hợp cần thống nhất **metadata contract**: những trường bắt buộc cho API, kiểu (chuỗi/mảng/số), issuer/profile, cách diễn giải quyền và hành vi khi thiếu trường.

### 5.1. Scope không phải role toàn cục

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "user-42",
  "tenant_id": "tenant-acme",
  "aud": "orders-api"
}
~~~

Trong ví dụ, RS có thể xét đọc order của Acme, nhưng **không được** suy ra được phép sửa order (`orders.write`) hoặc đọc dữ liệu Globex. Nếu AS trả `roles=["admin"]` theo extension, role phải có **ngữ cảnh tenant và semantics rõ**; không tự chuyển thành platform-wide `ROLE_ADMIN`.

### 5.2. Caller introspection khác audience của token

Orders API dùng credential riêng `orders-api-introspection` để gọi AS. Credential đó chứng minh **ai đang hỏi**, không chứng minh **token được hỏi dành cho Orders API**.

~~~text
Introspection caller: orders-api-rs
Token audience:       payments-api

caller được xác thực != token được cấp cho Orders API
~~~

AS cần hạn chế metadata của token dành cho RS khác; RS vẫn phải áp audience binding theo hợp đồng, **không chấp nhận token do API khác nhận** chỉ vì `active=true`.

### 5.3. Tenant trong introspection metadata

Một token active có `tenant_id=tenant-acme` và `scope=orders.read`. Request:

~~~http
GET /tenants/tenant-globex/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <opaque-token>
~~~

RS phải từ chối nếu request nhắm Globex nhưng token chỉ cho Acme. Không chỉ so path: query tài nguyên phải gắn tenant từ nguồn đã xác minh:

~~~sql
SELECT *
FROM orders
WHERE id = :order_id
  AND tenant_id = :verified_tenant_id;
~~~

Đây là cách giảm **Broken Object Level Authorization (BOLA/IDOR)**. `:verified_tenant_id` không được lấy từ `X-Tenant-Id` do client tự khai rồi coi là quyền.

## 6. Bảo vệ introspection endpoint

**Endpoint này nhận credential thật và có thể trả principal/claims nhạy cảm**. Không nên thiết kế endpoint public mà ai cũng gửi token vào rồi xem được user, email, tenant hoặc group list.

### 6.1. Xác thực resource server

Cơ chế tùy AS:

- HTTP Basic dùng client ID/secret của RS khi được AS cho phép;
- mTLS hoặc private_key_jwt theo client authentication contract;
- Credential/token chuyên dùng để truy vấn introspection nếu AS hỗ trợ;
- Chính sách mạng, certificate trust và rate limiting bổ sung.

**Credential của RS không được đưa xuống SPA/mobile**; lưu trong secret manager, luân phiên theo policy và dùng HTTPS xác minh hostname/chứng chỉ của AS.

### 6.2. Phân quyền caller: RS nào được xem token nào?

AS cần giới hạn truy cập metadata:

1. Chỉ cho RS đã đăng ký xem token thuộc **audience/resource** được phép hoặc disclosure policy tương ứng.
2. Tránh trả profile/PII không cần thiết.
3. Token inactive nên trả ít metadata để tránh token oracle.
4. Refresh token và token types khác phải có chính sách truy vấn riêng.
5. Theo dõi caller, tần suất, kết quả, nhưng không log raw token.

**Xác thực thành công một introspection client không cho quyền xem mọi token mọi tenant.**

### 6.3. Không cho URL introspection do caller quyết định

RS nên dùng **AS URL cố định hoặc được lấy từ metadata/registry tin cậy**. Không gửi Bearer token tới URL được cung cấp trong JWT chưa xác minh, `jku`, query parameter hoặc arbitrary HTTP redirect. Điều này vừa ngăn token exfiltration vừa hạn chế SSRF.

### 6.4. Bảo mật lỗi và input

Không trả chi tiết như “token của user nào”, “token nào bị revoke”, hoặc “client nào sở hữu token” cho caller không đủ quyền. Kiểm soát kích thước token/request, parser, rate và thời gian xử lý để hạn chế brute-force và DoS.

## 7. Đường xử lý an toàn tại RS

~~~mermaid
flowchart TD
    A["RS nhận Bearer access token"] --> B{"Cần introspection?"}
    B -->|Không| C["Validate JWT offline theo policy"]
    B -->|Có| D["POST trusted AS URL\nqua HTTPS + RS auth"]
    D --> E{"Response tin cậy\nactive=true?"}
    E -->|Không| R["Từ chối token hoặc báo lỗi dịch vụ"]
    E -->|Có| F{"Audience, scope, type,\nissuer, time khớp contract?"}
    F -->|Không| R
    F -->|Có| G{"Tenant, user/service,\nresource ownership đủ quyền?"}
    G -->|Không| H["403 / 404 theo policy"]
    G -->|Có| OK["Thực thi thao tác"]
~~~

Không dùng nội dung introspection response để tạo quyền trước khi kiểm tra **nguồn và kết quả**; cũng không dùng header `X-User-Id` từ client để bỏ qua bước gọi AS.

## 8. Caching introspection: hiệu năng và độ trễ thu hồi

Introspect mọi request có thể tăng độ trễ và tải cho AS. Cache `active=true` giúp giảm tải, nhưng **mở ra cửa sổ chấp nhận trạng thái cũ**:

~~~text
10:00:00  AS trả active=true cho token T, exp=10:15
10:00:01  RS cache metadata 60 giây
10:00:20  AS revoke token T
10:00:30  RS còn có thể dùng cached active=true
10:01:01  Cache hết TTL; RS hỏi lại -> active=false
~~~

Nếu hệ thống yêu cầu thu hồi gần thời gian thực, cần TTL ngắn, invalidation, introspection không cache cho thao tác nhạy cảm hoặc kiểm tra grant/session hiện hành.

### 8.1. Giới hạn TTL

Một policy đơn giản có thể chọn:

\[
\mathrm{TTL}_{cache}
=\min\left(\mathrm{TTL}_{policy},
            \max(0,\mathrm{exp}-\mathrm{now})\right)
\]

Nếu response thiếu `exp`, không tự cache vô hạn; dùng TTL policy rất ngắn hoặc không cache. **Không sử dụng metadata sau `exp`**, lưu ý clock skew và định dạng NumericDate.

| Mô hình cache | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Không cache | Kiểm tra AS gần như mỗi request | Latency và availability của AS |
| Positive cache ngắn | Giảm tải vừa phải | Stale active trong TTL |
| Cache dài | Hiệu năng cao | Revocation/membership thay đổi chậm có hiệu lực |
| Negative cache ngắn | Hạn chế lookup token ngẫu nhiên | Stale inactive nếu token đổi trạng thái |
| Push invalidation | Phản ánh revoke nhanh hơn | Event delay/loss, ordering, fallback |

### 8.2. Không dùng raw token làm log/cache label

Nếu cần correlation, có thể dùng fingerprint:

~~~text
cacheKey = HMAC_SHA256(K_cache, raw_access_token)
~~~

`K_cache` phải được bảo vệ và **khác token signing key, client secret**. Cache cần phân vùng theo issuer/RS caller context nếu AS trả metadata khác nhau tùy RS. Không đưa token thô, token prefix hoặc fingerprint không được bảo vệ vào telemetry phổ biến.

### 8.3. Cache chỉ metadata cần thiết

Introspection metadata có thể chứa `sub`, scope, tenant và dữ liệu người dùng. Giới hạn retention/TTL/quyền đọc, bảo vệ cache, tránh phân phát response cho các RS khác hoặc browser. **Cache active response không phải cache kết luận “mọi tài nguyên đều được phép”.**

## 9. AS timeout hoặc không khả dụng: fail closed

Khi AS không phản hồi, RS **không biết token có còn active hay không**. Một lỗi network không có nghĩa `active=true`.

~~~java
// SAI - anti-pattern:
try {
    return introspect(token);
} catch (Exception ignored) {
    return allowRequest(); // FAIL OPEN: token giả/revoked có thể đi qua
}
~~~

Thiết kế đúng hơn:

1. **Không cấp quyền** khi thiếu bằng chứng credential hợp lệ.
2. Với AS timeout/5xx, có thể trả lỗi dịch vụ tạm thời (`503`) thay vì báo token sai; với token thực sự inactive thường là `401` ở API.
3. Timeout/retry có giới hạn, circuit breaker, backpressure; không nhân tải AS vô hạn.
4. Chỉ dùng cache chưa hết TTL **khi chính sách cho phép**; không tự kéo dài TTL vì AS outage.
5. Với thao tác nhạy cảm, ưu tiên fail closed và thông báo không lộ dữ liệu.

Log request ID, latency, cache hit/miss và error category thay vì raw credentials.

## 10. Spring Boot/Spring Security: Opaque Token Resource Server

Với **Spring Boot 3 / Spring Security 6**, cấu hình phổ biến:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: <secret-from-secure-configuration>
~~~

Đây là **placeholder**; secret thật phải lấy từ secret manager hoặc cấu hình được bảo vệ, không commit Git. Nếu AS yêu cầu mTLS/private_key_jwt thay Basic, cần cấu hình client phù hợp.

### 10.1. Chặn request thiếu scope

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersOpaqueResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Spring Security thường chuyển scope được AS trả thành `SCOPE_` authorities, ví dụ `scope=orders.read` thành `SCOPE_orders.read`. Phải kiểm tra response thực tế của AS và phiên bản Spring. `hasRole("orders.read")` tìm `ROLE_orders.read` mặc định, **không** khớp `SCOPE_orders.read`.

**Snippet chỉ minh họa**: sản phẩm thật còn cần contract issuer/audience/type, CORS/CSRF theo kiến trúc, timeout, caching, tenant/resource authorization, error handling và audit.

### 10.2. Java policy sau khi introspection đã được xác thực

Ví dụ domain-level kiểm tra metadata tin cậy. `VerifiedIntrospection` là record do ứng dụng định nghĩa, **không phải model tự động của Spring**:

~~~java
import java.time.Instant;
import java.util.Set;

record VerifiedIntrospection(
    boolean active,
    String issuer,
    Set<String> audiences,
    Set<String> scopes,
    String subject,
    String tenantId,
    Instant expiresAt
) {}

enum AccessDecision {
    ALLOW, INVALID_TOKEN, FORBIDDEN
}

public final class OrdersTokenPolicy {
    private static final String ISSUER = "https://auth.example.com";
    private static final String AUDIENCE =
        "https://api.example.com/orders";

    public static AccessDecision canRead(
            VerifiedIntrospection token,
            String requestedTenant,
            String resourceTenant,
            Instant now) {
        // Chỉ nhận metadata từ introspector đáng tin, KHÔNG
        // nhận JSON/headers do client tự gửi.
        if (token == null || !token.active()
                || !ISSUER.equals(token.issuer())
                || token.audiences() == null
                || !token.audiences().contains(AUDIENCE)
                || token.expiresAt() == null
                || !now.isBefore(token.expiresAt())) {
            return AccessDecision.INVALID_TOKEN;
        }

        if (token.scopes() == null
                || !token.scopes().contains("orders.read")
                || token.tenantId() == null
                || !token.tenantId().equals(requestedTenant)
                || !token.tenantId().equals(resourceTenant)) {
            return AccessDecision.FORBIDDEN;
        }

        return AccessDecision.ALLOW;
    }
}
~~~

Ứng dụng thật còn cần xác minh subject, membership, principal type, sender binding, các chính sách dữ liệu. Nếu AS không trả `aud` hoặc `iss` mà API yêu cầu, **không lấy giá trị từ input client để lấp chỗ trống**: cấu hình AS/RS contract hoặc từ chối.

### 10.3. Không nhầm role và scope

~~~text
Introspection: active=true, scope=orders.read, tenant_id=acme
API request:   GET /tenants/globex/orders/42

Token active?             Có
Scope orders.read?        Có
Tenant/resource match?    Không
Kết luận:                TỪ CHỐI
~~~

Role `tenant-admin` có thể chỉ áp dụng cho một tenant, không phải `ROLE_ADMIN` toàn hệ thống. Resource server phải kiểm tra owner/tenant thật trong database, kể cả token active.

## 11. Kết hợp JWT offline với introspection

Một JWT có chữ ký RS256 đúng, `exp` còn 15 phút và `scope=orders.read` có thể vẫn được RS xác minh offline, trong khi user vừa bị xóa khỏi organization.

~~~text
JWT signature:   valid
iss/aud/exp:     valid
scope:           orders.read
membership:      revoked ở AS
~~~

Nếu hệ thống cần phản ánh quyền gần thời gian thực, RS có thể introspect JWT hoặc kiểm tra grant/membership tại một nguồn tin cậy. Những nguyên tắc bắt buộc:

- Không coi signature hợp lệ là bằng chứng membership bất biến.
- Không coi `active=true` là bỏ qua scope/audience/object policy.
- Không dùng cache dài nếu yêu cầu revoke nhanh.
- Nếu policy yêu cầu **cả JWT verification và introspection**, áp cả hai; kết quả mâu thuẫn nên fail closed.

AS có thể chỉ hỗ trợ introspection cho loại token được đăng ký; client/RS phải tuân hợp đồng thay vì tự giả định JWT nào cũng introspect được.

## 12. Introspection khác revocation, token endpoint và UserInfo

| Endpoint/giao thức | Mục đích | Không tự làm |
| --- | --- | --- |
| **Introspection — RFC 7662** | Hỏi trạng thái/metadata token | Không **thu hồi** token chỉ vì được hỏi |
| **Revocation — RFC 7009** | Yêu cầu AS vô hiệu hóa token/grant theo policy | Không chứng minh mọi RS cache đã cập nhật ngay |
| **Token endpoint — OAuth 2.0** | Đổi authorization code/refresh token lấy access token | Không phải introspection |
| **JWKS endpoint** | Cung cấp public keys để verify JWS | Không chứa trạng thái từng access token |
| **OIDC UserInfo endpoint** | Trả claims về user khi client có access token thích hợp | Không phải cơ chế introspection tổng quát |

Resource server thông thường **không dùng refresh token để gọi business API**; refresh token dành cho token endpoint của AS. Nếu introspection hỗ trợ nhiều token types, AS phải giới hạn quyền RS được truy vấn từng loại.

### 12.1. Refresh token rotation và reuse

Với refresh token rotation, token cũ bị vô hiệu hóa sau khi đổi sang token mới. Sử dụng lại token cũ có thể là replay hoặc retry/concurrency; AS cần xử lý token family theo policy. **`active=true` của một access token không suy ra mọi refresh token liên quan còn hợp lệ**, và revoke refresh token không tự làm JWT access token đã phát hết hạn ngay nếu RS chỉ verify offline.

## 13. DPoP và mTLS: `active=true` chưa chứng minh sender

Với **sender-constrained access token**, RS không chỉ hỏi AS token có active mà còn phải xác nhận caller sở hữu khóa/chứng chỉ tương ứng.

### 13.1. DPoP-bound access token

Một introspection response theo hợp đồng có thể có:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": "orders-api",
  "cnf": {
    "jkt": "<public-key-thumbprint>"
  }
}
~~~

RS phải xác minh **DPoP proof** theo RFC 9449: chữ ký, `htm`, `htu`, `iat`, `jti` chống replay, `ath`, nonce khi yêu cầu và public key thumbprint khớp `cnf.jkt`. **Không chấp nhận DPoP-bound token như Bearer thuần chỉ vì `active=true`.**

### 13.2. mTLS-bound access token

Introspection metadata có thể chứa `cnf` như certificate thumbprint `x5t#S256` theo profile. RS phải xác minh certificate đã được trình qua kênh thích hợp hoặc thông tin xác thực đáng tin từ gateway; không tin header `X-SSL-Client-Cert` do client tự khai.

**Introspection trả trạng thái token; DPoP/mTLS xác minh người gửi có khóa/chứng chỉ cần thiết.** Hai kiểm tra bổ sung, không thay thế nhau.

## 14. Logging, privacy và token oracle

Introspection response có thể chứa `sub`, client ID, tenant, scope, hạn token và dữ liệu nhạy cảm. Tránh:

- Log raw request body có `token=<secret>` ở AS, RS, proxy và APM;
- Log `Authorization: Basic ...` chứa credential của RS;
- Trả toàn bộ introspection response xuống browser “để debug”;
- Dùng access token làm trace ID, metric label, cache key hiện trực tiếp;
- Lưu claims/user identifiers vô thời hạn trong analytics.

Nên log request ID, AS/issuer alias, RS/client alias, outcome, latency, cache hit/miss và error category. Nếu cần liên kết cùng token, dùng **HMAC fingerprint với khóa audit riêng**, quản lý TTL/retention/quyền đọc.

### 14.1. Response caching

Introspection response chứa thông tin credential; AS nên dùng cache directives phù hợp, ví dụ:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

Nếu RS chủ động cache kết quả **trong cơ chế nội bộ đã bảo vệ**, phải giới hạn TTL và tính bảo mật riêng. Không coi HTTP shared cache giữa nhiều RS là nơi phù hợp để lưu metadata của mọi user/token.

## 15. Phân biệt lỗi HTTP ở từng lớp

| Nguyên nhân | Nơi phát hiện | Phản hồi/hành động |
| --- | --- | --- |
| Client không gửi access token | RS | `401 Unauthorized` theo Bearer policy |
| Token inactive | AS trả `active=false` | RS từ chối, thường `401 invalid_token` |
| RS credential gọi introspection sai | AS | Lỗi xác thực introspection client, sửa cấu hình |
| AS timeout/5xx | Mạng/AS | RS không cấp quyền khi chưa verify; có thể trả lỗi dịch vụ |
| Token active nhưng audience sai | RS/AS | RS từ chối |
| Token active nhưng thiếu scope | RS | Thường `403 insufficient_scope` |
| Scope đủ nhưng tài nguyên tenant khác | Business policy | `403` hoặc `404` để tránh lộ tồn tại |
| Metadata thiếu trường bắt buộc | RS | Fail closed, kiểm tra AS/profile |
| Cache active sau revoke | RS caching | TTL/invalidation/revocation policy cần sửa |

Bearer challenge cho token không được chấp nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
~~~

Bearer challenge cho scope thiếu:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
  scope="orders.write"
~~~

Scope được quảng bá là yêu cầu cho endpoint, **không phải lời hứa** AS sẽ cấp scope cho bất kỳ client/user nào xin.

## 16. Các sai lầm thường gặp

| Ngộ nhận | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`active=true` cho mọi API.” | Có thể sai audience, thiếu scope | Check audience/type/scope/resource |
| “Introspection public ai cũng gọi.” | Token oracle, lộ metadata | Xác thực/ủy quyền RS và giới hạn disclosure |
| “Token sai thì AS introspection trả 401.” | Request hợp lệ thường được trả `200 active=false` | Phân biệt token state vs caller auth |
| “Introspection tự revoke token.” | Chỉ truy vấn | Dùng revocation endpoint/policy riêng |
| “Opaque khỏi check audience.” | Token API khác vẫn có thể active | Resource binding phải rõ |
| “JWT nào cũng bắt buộc introspect.” | JWT có thể verify offline | Chỉ introspect khi profile/thu hồi yêu cầu |
| “Cache kết quả active vô hạn.” | Stale token sau revoke/exp | TTL ngắn, không vượt `exp` |
| “AS outage thì allow cho hệ thống chạy.” | Fail open, bỏ bảo mật | Fail closed, báo lỗi dịch vụ |
| “Đưa RS secret xuống SPA để introspect.” | Public client lộ secret | Backend-to-backend với credential được bảo vệ |
| “DPoP token active thì bỏ proof.” | Không kiểm tra sender | Verify proof/certificate binding |
| “ID token và access token cùng issuer thay thế được.” | Audience/mục đích khác nhau | Dùng access token đúng API |

## 17. Kiểm thử bắt buộc

| Test case | Kỳ vọng |
| --- | --- |
| RS auth hợp lệ, opaque token active đúng audience/scope | RS tiếp tục xét quyền dữ liệu |
| Token không tồn tại | AS trả `active=false`; RS từ chối |
| Token hết `exp` | RS từ chối |
| Token revoke | RS từ chối khi kiểm tra lại theo TTL/policy |
| `token_type_hint` sai | AS không tin hint như bằng chứng |
| RS client secret sai | AS từ chối introspection client |
| RS không được quyền xem token RS khác | Không rò metadata |
| `active=true`, `aud` sai | RS từ chối |
| `active=true`, `scope` thiếu | RS trả `403`/deny theo policy |
| Thiếu `aud` mà contract yêu cầu | Fail closed |
| ID token được gửi tới API | Từ chối type/audience |
| App-only token bị coi là user-delegated | Từ chối/áp đúng profile |
| Acme token đọc order Globex | Không lộ record |
| AS timeout | Không được fail open |
| Positive cache còn active sau revoke | Test cửa sổ stale và TTL/invalidation |
| Cache TTL vượt `exp` | Không dùng cached result quá hạn |
| Negative cache quá lâu sau activation | Phát hiện sai lệch, TTL phù hợp |
| Introspection endpoint bị spam token ngẫu nhiên | Rate/size/auth limits hoạt động |
| Token có ký tự đặc biệt | Form URL encode đúng |
| Raw token/Basic secret xuất hiện trong log | Test thất bại; redact |
| JWT offline hợp lệ | Verify signature, issuer, audience, time, scope |
| DPoP-bound token thiếu proof | Từ chối |
| mTLS-bound token sai certificate | Từ chối |
| Gateway forward identity header giả | Backend chỉ trust nguồn/assertion đã xác thực |

Thử bằng **test token/credential riêng**, không ghi token thật vào bug report, logs hoặc Git. Integration tests phải đi qua HTTP introspection client, Spring Security filter chain và resource authorization; mock principal đơn thuần không kiểm chứng endpoint thực sự an toàn.

## 18. Các tình huống phân tích

**Tình huống A — Token revoke nhưng RS vẫn cho truy cập.** RS cache `active=true` trong 10 phút, token bị revoke sau 1 phút.

**Phân tích:** độ trễ đến từ cache; cân nhắc TTL ngắn, invalidation hoặc kiểm tra trạng thái hiện hành cho thao tác nhạy cảm.

**Tình huống B — Payments API thấy token active nhưng từ chối.** Token có `aud=orders-api` và `scope=orders.read`.

**Phân tích:** từ chối là đúng, vì token dành cho Orders API. Introspection không mở rộng audience.

**Tình huống C — Frontend muốn gọi introspection trực tiếp.** Nhóm định nhúng `client_secret` của RS vào JavaScript.

**Phân tích:** không được làm vậy. Giữ introspection backend-to-backend, frontend chỉ nhận thông tin UX thật sự cần.

**Tình huống D — AS không hoạt động.** Backend có catch-all: “nếu introspection lỗi thì cho qua”.

**Phân tích:** đây là fail-open nghiêm trọng. Cần fail closed, timeout/circuit breaker và lỗi dịch vụ phù hợp.

**Tình huống E — Người dùng đổi organization.** Token active chỉ có `tenant_id=acme` nhưng request cần Globex.

**Phân tích:** cần token/grant phù hợp và kiểm tra ownership. `active` không đồng nghĩa membership mọi tenant.

**Tình huống F — DPoP proof không khớp.** Introspection trả active cùng `cnf.jkt` nhưng request không có proof.

**Phân tích:** từ chối; trạng thái token không chứng minh caller giữ private key.

## 19. Checklist production

1. **Phân biệt OAuth2 roles:** resource owner, client, AS và RS; xác định ai có quyền introspect.
2. **Chọn mô hình token:** JWT offline, opaque introspection hoặc kết hợp theo revocation/latency/privacy.
3. **Dùng trusted endpoint:** AS URL, issuer metadata/registry, HTTPS và certificate validation, chống SSRF.
4. **Xác thực RS với AS:** secret/mTLS/private_key_jwt được bảo vệ và hạn chế quyền.
5. **Giới hạn metadata:** caller chỉ thấy token phù hợp audience/type và claims thật sự cần.
6. **Validate response:** `active` boolean, issuer, audience, token type, scope và schema theo contract; thiếu field cần thiết thì fail closed.
7. **Phân quyền business:** principal type, tenant, membership, ownership và trạng thái tài nguyên.
8. **Cache có TTL:** không vượt `exp`, tuân yêu cầu thu hồi và positive/negative cache policy.
9. **Xử lý AS outage:** không fail open, timeout/retry/circuit breaker và availability.
10. **Tách introspection khỏi revocation/refresh:** hiểu RFC 7662, RFC 7009 và token endpoint.
11. **Xử lý sender constraint:** DPoP proof, mTLS binding và chống replay khi áp dụng.
12. **Redact logs:** không raw token/Basic secret/user PII không cần; bảo vệ fingerprint và metadata.
13. **Kiểm thử negative:** inactive/expired/revoked/wrong audience, thiếu scope, client auth sai, cache stale, AS outage và cross-tenant.
14. **Giám sát:** latency, error rate, cache hit/miss, denial, AS capacity và rủi ro lộ credential.

## 20. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, `active`, metadata, bảo mật endpoint.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): bốn vai trò, token endpoint và grant.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery và `introspection_endpoint`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token, khác introspection.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và validation.
- [RFC 9701 — JWT Response for OAuth Token Introspection](https://www.rfc-editor.org/rfc/rfc9701): extension introspection response dạng JWT khi hỗ trợ.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ bearer/refresh token.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens và proof.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection trong Java/Spring.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): phân quyền trên object.

**Ghi nhớ:** **Introspection endpoint là điểm authorization server trả trạng thái và metadata token cho resource server được phép qua kênh bảo vệ.** `active=true` chứng minh token được AS chấp nhận theo ngữ cảnh truy vấn, **không cấp toàn bộ quyền**. API vẫn kiểm tra audience, scope, token type, tenant và ownership; caching phải tôn trọng thời hạn và yêu cầu revocation. Với JWT hay opaque, bảo vệ credential, vai trò OAuth 2.0 và chống replay/sender-binding vẫn thuộc trách nhiệm toàn bộ kiến trúc.
