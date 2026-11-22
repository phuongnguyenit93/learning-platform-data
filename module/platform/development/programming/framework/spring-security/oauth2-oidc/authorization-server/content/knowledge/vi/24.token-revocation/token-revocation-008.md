# Kết hợp TTL, introspection hoặc cơ chế bổ sung để thực thi thu hồi

## Mục tiêu bài học

Trong chương **Revocation** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài này nghiên cứu cách biến một thao tác **thu hồi token** thành một quyết định từ chối có hiệu lực tại **Resource Server**. Bối cảnh là thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**.

Có một khác biệt quyết định:

> **Authorization Server ghi nhận token đã bị thu hồi không có nghĩa mọi Resource Server sẽ lập tức từ chối token.** Kết quả phụ thuộc định dạng token, cách API kiểm tra token, cache, độ trễ đồng bộ và thời gian sống còn lại.

Với **opaque/reference access token**, Resource Server thường hỏi **Token Introspection Endpoint** để biết token còn active hay không. Với **JWT access token** tự chứa, Resource Server có thể chỉ xác minh chữ ký và các claims như `iss`, `aud`, `exp` mà không liên lạc với Authorization Server. Khi đó, trạng thái revoke trong database của Authorization Server không tự động truyền vào việc kiểm chữ ký.

Sau bài học, bạn có thể:

- Phân biệt **TTL/expiration**, **revocation**, **introspection**, **denylist**, **session epoch** và **refresh token rotation**.
- Hiểu yêu cầu RFC 7009 và RFC 7662; không coi HTTP 200 từ Revocation Endpoint là bằng chứng API đã ngừng nhận JWT.
- Chọn chiến lược thu hồi cho opaque token, JWT tự chứa, refresh token và ID Token/phiên đăng nhập theo mục tiêu bảo mật.
- Cấu hình Spring Authorization Server với `OAuth2AuthorizationService`, `OAuth2TokenRevocationEndpointConfigurer`, `OAuth2TokenIntrospectionEndpointConfigurer` và `TokenSettings`.
- Cấu hình Spring Security Resource Server kiểm token bằng introspection hoặc JWT cộng kiểm tra trạng thái thu hồi.
- Thiết kế TTL và cache để xác định **thời gian tối đa còn chấp nhận token sau sự kiện revoke**.
- Phối hợp thu hồi refresh token, access token, authorization grant, client credential và phiên người dùng.
- Thiết kế cơ chế bổ sung như revoked-`jti` store, grant/session version, event propagation và kiểm tra quyền động.
- Kiểm thử restart, cache, nhiều instance/region, mất kết nối, race condition và sự cố khóa ký.

**Tình huống xuyên suốt:** Một ứng dụng `employee-portal` đăng nhập và nhận JWT access token sống 15 phút cùng refresh token sống 14 ngày. Người dùng bấm “Đăng xuất tất cả thiết bị”. Authorization Server đã revoke refresh token; nhưng `inventory-api` vẫn chấp nhận JWT cũ nếu chỉ verify chữ ký và `exp`. Chúng ta sẽ xây chính sách để đo và giảm khoảng thời gian này.

## 1. Phân biệt hết hạn tự nhiên và thu hồi chủ động

### 1.1. TTL không phải revocation

**TTL (time-to-live)** là thời gian token được phép tồn tại theo policy. Trong JWT, thời điểm hết hạn thường biểu diễn bằng claim `exp`. Token tự hết hiệu lực khi đến hạn, kể cả không có thao tác revoke.

**Revocation** là quyết định của Authorization Server hoặc quản trị viên rằng token/authorization không còn được dùng **trước hạn tự nhiên**: ví dụ user logout, mất thiết bị, phát hiện lộ refresh token, khóa tài khoản, thay đổi mật khẩu hoặc quyền truy cập.

| Tình huống | Hết hạn tự nhiên | Thu hồi |
|---|---|---|
| Token sống 5 phút, đã qua `exp` | Không sử dụng được | Không cần sự kiện revoke |
| JWT còn 12 phút, user logout | Vẫn chưa hết hạn | Cần cơ chế Resource Server biết trạng thái revoke để từ chối ngay |
| Refresh token sống 14 ngày, bị revoke ngày thứ 2 | Chưa hết hạn | Token Endpoint phải từ chối refresh tiếp theo |
| Client bị disable, JWT đã cấp còn 10 phút | `exp` chưa tới | Offline JWT validator không tự biết client bị disable |
| Key ký bị compromise | `exp` có thể còn lâu | Cần incident response, không thể chỉ chờ TTL nếu rủi ro cao |

**Thu hồi có hai mặt:** ngăn **cấp token mới** (đặc biệt qua refresh token) và ngăn **sử dụng token đã cấp** tại API. Một hệ thống chỉ thực hiện mặt thứ nhất không đạt yêu cầu “logout tức thời khỏi mọi API”.

### 1.2. Những token có vòng đời khác nhau

- **Access token:** credential gửi tới Resource Server. Cần kiểm `exp`, audience, scope, issuer và có thể cần kiểm trạng thái revoke.
- **Refresh token:** credential dùng ở Token Endpoint để xin access token mới. Cần lưu/truy xuất trạng thái và gắn với client, authorization/grant; rotation/reuse detection có thể thu hồi cả token family.
- **ID Token:** chứng thực đăng nhập cho OIDC Client; không phải access token dùng gọi API. Thu hồi access/refresh token không có nghĩa một ID Token đã phát sẽ tự biến mất khỏi mọi client.
- **Authorization grant/consent:** trạng thái ủy quyền lâu dài hoặc phiên đã được chấp thuận; có thể ảnh hưởng việc phát token mới.
- **Login/session cookie:** trạng thái phiên trình duyệt; xóa cookie hay logout ứng dụng không tự đảm bảo access token đã phát bị từ chối ở Resource Server.

Thiết kế “logout” phải định nghĩa rõ sẽ vô hiệu hóa lớp nào, ở đâu và trong bao lâu.

## 2. Hợp đồng Token Revocation theo RFC 7009

RFC 7009 định nghĩa endpoint cho client yêu cầu Authorization Server hủy một token không còn cần thiết.

### 2.1. Request hợp lệ

Client gửi HTTP POST qua HTTPS, body `application/x-www-form-urlencoded`. Tham số `token` là **bắt buộc**, `token_type_hint` là **tùy chọn**, chỉ hỗ trợ tối ưu tra cứu:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS_BASE64>

token=<REFRESH_TOKEN_SAMPLE>&token_type_hint=refresh_token
~~~

`<REFRESH_TOKEN_SAMPLE>` là placeholder, không phải credential thật. Cấu hình Authorization Server có thể đổi path; ví dụ này dùng đường dẫn `/oauth2/revoke` thường gặp trong Spring Authorization Server.

RFC 7009 yêu cầu xác thực confidential client và kiểm token được cấp cho client tương ứng trước khi thu hồi. Không cho caller tùy ý revoke token của client khác chỉ vì biết giá trị token. Public client phải được xử lý theo chính sách xác thực/binding và hỗ trợ của framework; đừng dùng client ID không được chứng thực để cho phép revoke tùy ý trên toàn hệ thống.

### 2.2. Response thành công không xác nhận token trước đó tồn tại

RFC 7009 mục 2.2 quy định HTTP **200 OK** khi thu hồi thành công **hoặc** client gửi token không hợp lệ/không còn tồn tại:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

Body thường rỗng, client không cần đọc body để biết thành công. Điều này hạn chế token-existence oracle.

Phân biệt:

| Tình huống | Kết quả ở Revocation Endpoint |
|---|---|
| Token thuộc client, đang active | 200 nếu revoke thành công |
| Token đã revoke trước đó | 200 |
| Token không hợp lệ/không tìm thấy, request caller hợp lệ | 200 |
| Client authentication thất bại | OAuth2/client authentication error, không trả 200 giả |
| Token của client khác hoặc kiểm tra quyền thất bại | Không cấp quyền cho caller; trả lỗi phù hợp sau kiểm soát bảo mật |
| Token type thực không được hỗ trợ revoke | Có thể trả `unsupported_token_type` theo RFC 7009 |
| Service unavailable (503) | Client phải giả định token **vẫn có thể tồn tại**, chỉ retry theo `Retry-After`/backoff |

Không biến `token_type_hint=refresh_token` thành bằng chứng token thực sự là refresh token. Nếu hint không đúng, server vẫn phải thực hiện lookup hợp lệ theo chuẩn.

### 2.3. Cascade revocation không phải một giả định bất biến

Theo RFC 7009:
- Implementation **MUST** hỗ trợ revoke refresh token.
- Implementation **SHOULD** hỗ trợ revoke access token.
- Nếu revoke refresh token và server hỗ trợ access-token revocation, server **SHOULD** cũng vô hiệu hóa access token phát ra từ cùng authorization grant.
- Nếu revoke access token, server **MAY** revoke refresh token liên quan.

**MUST/SHOULD/MAY không đồng nghĩa mọi triển khai có cùng cascade policy.** Phải xem và kiểm thử hành vi thực tế theo phiên bản Spring Authorization Server, token format, authorization store và các token còn sống. Đặc biệt, dù metadata của access token đã bị invalidated tại Authorization Server, **Resource Server offline JWT không tự thấy metadata đó**.

## 3. Ba tầng cần phối hợp để việc thu hồi có hiệu lực

Mô hình gồm:

1. **Tầng ra quyết định:** ai được phép revoke token, lý do và phạm vi revoke.
2. **Tầng lưu trạng thái:** Authorization Server lưu token/authorization invalidated; event/denylist/session version nếu áp dụng.
3. **Tầng thực thi:** Token Endpoint từ chối refresh; Resource Server từ chối access token đã bị thu hồi theo phương thức validation được chọn.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User/Admin/Client
    participant AS as Authorization Server
    participant DB as Authorization Storage
    participant R as Resource Server
    U->>AS: Revoke refresh/access token
    AS->>DB: Mark invalidated (và cascade theo policy)
    DB-->>AS: Commit
    AS-->>U: 200 OK
    U->>R: API call với access token cũ
    alt R dùng introspection
        R->>AS: POST /oauth2/introspect
        AS->>DB: Check active / invalidated / exp
        AS-->>R: active=false
        R-->>U: 401 invalid_token
    else R chỉ verify JWT offline
        R->>R: Verify JWS + iss + aud + exp
        R-->>U: Có thể vẫn 200 nếu JWT chưa hết hạn
    end
~~~

Đây là lý do không thể cam kết “revoke tức thì” chỉ dựa trên việc endpoint trả 200. Cần xác định mỗi Resource Server đang chạy nhánh nào.

## 4. Chọn token format: JWT tự chứa và opaque/reference

Trong Spring Authorization Server, `TokenSettings.accessTokenFormat(...)` quyết định định dạng access token của RegisteredClient:

- `OAuth2TokenFormat.SELF_CONTAINED`: thường JWT, được ký bằng `JwtGenerator`.
- `OAuth2TokenFormat.REFERENCE`: opaque access token, thường được tạo bởi `OAuth2AccessTokenGenerator`.

### 4.1. Bảng so sánh

| Tiêu chí | JWT self-contained, verify offline | Opaque/reference + introspection |
|---|---|---|
| Quyết định chấp nhận token | Resource Server verify chữ ký/claims | Authorization Server trả `active` qua introspection |
| Nhìn thấy revoke mới tại AS | **Không tự động** | Khi request tới introspection nhận trạng thái mới |
| Độ trễ API | Thấp, không cần gọi AS mỗi request | Có thể tăng do network/AS/DB |
| Phụ thuộc AS lúc API gọi | Thường không | Có, trừ cache introspection |
| Cửa sổ hiệu lực token sau revoke | Có thể đến `exp` nếu không có kiểm tra phụ | Phụ thuộc cache, propagation và AS availability |
| Claim exposure | JWT payload có thể decode được (không được coi là bí mật) | Chuỗi token không tự chứa claim, metadata chỉ qua AS |
| Hiệu năng lớn | Tốt cho API traffic cao | Cần capacity planning, rate limiting và cache phù hợp |
| Thu hồi có độ trễ nhỏ | Cần denylist/state check/introspection | Có thể thực thi với cache nhỏ hoặc introspect trực tiếp |

**Opaque không tự động “revoke ngay” nếu Resource Server cache `active=true` quá lâu.** Ngược lại, JWT có thể được introspect thay vì verify offline nếu mục tiêu là kiểm trạng thái server-side.

### 4.2. Chọn theo rủi ro

- API nội bộ đọc dữ liệu ít nhạy cảm, chịu được vài phút: JWT TTL ngắn, verify offline, có thể chấp nhận residual window.
- API tài chính/quản trị, logout/disable phải có hiệu lực nhanh: opaque+introspection, hoặc JWT+online revocation check/denylist.
- API lưu lượng rất lớn, SLA latency chặt: JWT TTL ngắn cộng cache/version/event phù hợp; phải cân bằng consistency và rủi ro.
- Dữ liệu cực nhạy cảm với điều kiện thay đổi mỗi request: token validity không đủ; cần thêm **authorization check động** cho quyền tại API.

## 5. TTL: giảm cửa sổ bị lợi dụng, không phải xóa token từ xa

TTL là tuyến phòng thủ đầu tiên và đơn giản nhất với token tự chứa. Nếu access token sống 5 phút, sau khi revoke refresh token, JWT cũ có thể còn được API offline chấp nhận tối đa gần 5 phút kể từ khi cấp, cộng tolerance clock skew theo validator.

### 5.1. Công thức thực tế

Gọi:
- `t_revoke`: thời điểm sự kiện thu hồi được xác nhận.
- `exp`: thời điểm hết hạn access token.
- `skew`: dung sai đồng hồ mà Resource Server chấp nhận.
- `L`: độ trễ đồng bộ trạng thái/cập nhật policy, nếu có.

Với **offline JWT không kiểm revoke**:

~~~text
Residual window (xấp xỉ) =
    max(0, exp - t_revoke + accepted_clock_skew)
~~~

Nếu token vừa được cấp, residual window gần bằng access-token TTL cộng clock skew. Nếu token đã gần hết hạn, cửa sổ ngắn hơn.

Ví dụ:

| TTL access token | Revoke sau khi cấp | Không kiểm online | Kết quả dự kiến |
|---|---|---|---|
| 15 phút | Sau 2 phút | Residual gần 13 phút (+skew) | JWT cũ còn có thể dùng |
| 5 phút | Sau 2 phút | Residual gần 3 phút (+skew) | Cửa sổ ngắn hơn |
| 60 giây | Sau 20 giây | Residual gần 40 giây (+skew) | Cần traffic Token Endpoint lớn hơn |

Các con số chỉ minh họa, không phải SLA hứa hẹn. Nếu validator có chính sách clock skew, cache, network delay hoặc bug, thực tế có thể khác.

### 5.2. Cấu hình TTL bằng TokenSettings

Ví dụ đăng ký confidential client trong Spring Authorization Server:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
~~~

Gắn `tokenSettings` vào `RegisteredClient`. Ví dụ là đoạn cấu hình, không phải ứng dụng hoàn chỉnh. `reuseRefreshTokens(false)` bật rotation theo chính sách của framework, cần kiểm thử persistence và trường hợp hai request refresh đồng thời.

**Không điều chỉnh `expires_in` trong Token Response bằng success handler để “đổi TTL”.** TTL thật do token generator/provider và token settings quyết định; nếu sửa riêng response, client và Resource Server có thể hiểu thời hạn khác nhau.

### 5.3. Trade-off TTL quá ngắn

TTL ngắn giảm thời gian token lộ có thể bị dùng, nhưng:
- Tăng lưu lượng xin token/refresh.
- Dễ gây token stampede khi nhiều worker cùng refresh.
- Tăng phụ thuộc vào Authorization Server/KMS/DB.
- Có thể ảnh hưởng mobile/offline clients.
- Nếu refresh token bị đánh cắp, chỉ rút TTL access token không đủ ngăn attacker tiếp tục xin token.

Cần đi kèm refresh token rotation, client authentication/sender-constraining và rate control.

## 6. Introspection: kiểm tra trạng thái token tại thời điểm sử dụng

RFC 7662 định nghĩa `POST /oauth2/introspect`. Authorization Server trả `active=true` khi token còn hoạt động và caller được phép biết token đó; trả `active=false` cho token hết hạn, bị revoke, không tồn tại hoặc caller không được phép biết trạng thái.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <RESOURCE_SERVER_CREDENTIAL>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN_SAMPLE>&token_type_hint=access_token
~~~

Kết quả sau revoke:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

Một Resource Server được cấu hình introspection sẽ dựa vào trạng thái mới của AS thay vì chỉ verify chữ ký offline.

### 6.1. Cấu hình Spring Security Resource Server opaque token

Ở **Resource Server**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: ${INVENTORY_INTROSPECTION_SECRET}
~~~

Credential phải lấy từ secret manager; không commit secret thật vào repository. Introspection caller phải được xác thực và phân quyền theo token audience/resource/tenant, không cấp quyền tra mọi token cho mọi API.

### 6.2. Có thể introspect JWT không?

**Có.** Spring Security OAuth2 Resource Server opaque-token support có thể gửi cả chuỗi JWT tới introspection endpoint. Tên cấu hình `opaquetoken` phản ánh **chiến lược xác minh từ xa**, không bắt buộc token thực sự là opaque.

Điều này hữu ích khi bạn muốn sử dụng JWT nhưng Resource Server cần nhìn thấy trạng thái revoke gần real-time. Authorization Server phải quản lý trạng thái của JWT đủ để introspection nhận diện token, và mỗi JWT cần được xác minh/đối chiếu với authorization đã lưu. Không giả định AS có thể introspect mọi JWT tự do phát hành ở nơi khác.

### 6.3. Introspection cache là điểm quyết định SLA

Giả sử Resource Server đã cache:

~~~json
{
  "active": true,
  "exp": 1794861000,
  "scope": "inventory.read"
}
~~~

Nếu cache còn hiệu lực 30 giây, API có thể tiếp tục chấp nhận token trong 30 giây sau revoke, dù AS đã trả `active=false` khi được gọi trực tiếp.

Ước lượng:

~~~text
Observed revocation delay <=
    state propagation delay
    + remaining positive introspection-cache TTL
    + processing/network delays
~~~

Đây là **ước lượng kiến trúc**, không phải bound tuyệt đối khi có clock drift, network partitions hoặc cache không tuân thủ TTL.

Các nguyên tắc:
- Cache `active=true` không dài hơn `exp` của token.
- Chọn positive cache TTL theo mục tiêu revoke SLA; ví dụ mục tiêu dưới 30 giây thì cache 5–10 giây có thể dành chỗ cho propagation/jitter.
- Không dùng cache vô hạn.
- Cache key phải tách issuer, token identity và caller/resource context để không tái sử dụng response của API khác.
- Có thể chủ động purge cache bằng event, nhưng vẫn cần TTL fallback.
- Cẩn trọng negative caching khi token/client vừa thay đổi trạng thái; nhất quán với nghiệp vụ và rủi ro.
- Không log raw token khi cache key dùng hash/fingerprint.

### 6.4. AS unreachable: fail-open hay fail-closed?

Khi Resource Server cần introspection mà AS/DB unavailable, đây là lỗi **không xác định trạng thái**, không phải bằng chứng token active. Với API bảo mật cao, nên **fail closed**: từ chối hoặc trả lỗi dịch vụ phù hợp thay vì chấp nhận token chưa được xác thực.

Cache `active=true` còn hạn có thể được dùng nếu chính sách rõ ràng cho phép thời gian stale ngắn; cần xem đó là quyết định rủi ro. Không biến outage thành cơ chế “mọi bearer token đều hợp lệ”.

## 7. Revocation Endpoint và trạng thái trong Spring Authorization Server

### 7.1. Các thành phần chuẩn

Spring Authorization Server 1.x hỗ trợ:

- `OAuth2TokenRevocationEndpointFilter`: nhận request revoke.
- `OAuth2TokenRevocationAuthenticationConverter`: parse request.
- `OAuth2TokenRevocationAuthenticationProvider`: xử lý revoke.
- `OAuth2AuthorizationService`: tìm và lưu authorization/token state.
- `OAuth2Authorization.Token`: lưu metadata như invalidation; `isActive()` xét hạn và trạng thái invalidated.
- `OAuth2TokenRevocationEndpointConfigurer`: hook converter/provider/success/error handler.

Cấu hình mặc định thường đủ để revoke token theo framework. **Không tự viết controller `/oauth2/revoke` làm bản sao** nếu không có yêu cầu rõ ràng và kiểm thử đầy đủ RFC 7009.

### 7.2. Cấu hình endpoint và issuer

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenEndpoint("/oauth2/token")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .build();
}
~~~

Đây là Bean minh họa; API cấu hình/đường dẫn cần khớp phiên bản sử dụng. Public issuer/endpoint phải dùng HTTPS và phản ánh đúng ingress/reverse proxy. Không đặt issuer là tên pod nội bộ.

Ví dụ khung SecurityFilterChain:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(
        HttpSecurity http) throws Exception {

    var server = OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(server.getEndpointsMatcher())
        .with(server, authServer -> authServer
            .tokenRevocationEndpoint(revocation -> {
                // Giữ converter/provider/response handlers mặc định.
            })
            .tokenIntrospectionEndpoint(introspection -> {
                // Áp policy caller-to-token khi cần.
            }))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Ví dụ chưa cung cấp các Bean còn lại (`RegisteredClientRepository`, `OAuth2AuthorizationService`, JWK/encoder, login chain). Không trộn import thuộc Spring Authorization Server 1.x với các class cùng tính năng được tích hợp ở Spring Security đời khác.

### 7.3. Persistence phải dùng chung nhiều instance

`OAuth2AuthorizationService` cần lưu trạng thái token và metadata invalidated một cách bền vững. Nếu production dùng `InMemoryOAuth2AuthorizationService` riêng từng node:

- Node A có thể revoke, nhưng node B vẫn giữ bản authorization chưa revoke.
- Introspection qua load balancer có thể trả active khác nhau theo node.
- Restart làm mất trạng thái và khả năng xử lý refresh token.
- Các endpoint Token/Revocation/Introspection không thống nhất về authorization.

Production nên dùng persistent/shared storage thích hợp, chẳng hạn JDBC service được cấu hình migration, isolation, backup và truy cập đồng nhất. Nếu tự triển khai repository/service, phải hỗ trợ `findByToken(...)`, `save(...)`, invalidation metadata, concurrency và lookup cả refresh/access token theo các kiểu mà provider thực tế sử dụng.

### 7.4. Phân biệt state ở AS và quyết định ở RS

Ví dụ kiểm tra một access token đã được lưu:

~~~java
OAuth2Authorization authorization =
        authorizationService.findByToken(tokenValue, OAuth2TokenType.ACCESS_TOKEN);

if (authorization == null || authorization.getAccessToken() == null) {
    // Token không được Authorization Server nhận diện.
    return;
}

OAuth2Authorization.Token<OAuth2AccessToken> stored =
        authorization.getAccessToken();

boolean activeAtAuthorizationServer = stored.isActive();
boolean revoked = stored.isInvalidated();
~~~

Đoạn Java minh họa đọc state, không phải controller/endpoint đầy đủ. Cần bảo vệ `tokenValue` khỏi log. Giá trị `activeAtAuthorizationServer=false` chỉ có ý nghĩa với thành phần thực sự **tra state của AS**; một Resource Server chỉ verify JWS/JWT offline sẽ không tự gọi đoạn code này.

### 7.5. Cascade refresh/access token phải được test

Ở các phiên bản Spring Authorization Server được kiểm chứng, provider revocation có thể invalidated refresh token cùng access token liên quan trong authorization. Nhưng **đừng suy luận hành vi cascade xuyên mọi token family, grants hoặc custom OAuth2AuthorizationService**. Cần kiểm thử trực tiếp:

1. Phát access token A1 và refresh token R1.
2. Revoke R1 bằng đúng client đã nhận token.
3. Gọi refresh R1 → phải thất bại.
4. Introspect A1 → kỳ vọng inactive nếu cascade policy đã chọn.
5. Gọi Resource Server với A1 → kiểm tra thực tế RS có từ chối hay vẫn chấp nhận JWT offline.
6. Kiểm tra A1 có thể được phát cho audience khác, hoặc nhiều tokens cùng grant, theo storage model.
7. Nếu policy chỉ revoke R1 mà không revoke A1, phải tài liệu hóa residual TTL và rủi ro.

## 8. JWT offline + revoked-jti denylist

Nếu API cần JWT self-contained để giữ latency thấp nhưng vẫn cần chặn một số access token trước `exp`, có thể xây **denylist** theo `iss` và `jti`.

### 8.1. Cách hoạt động

1. Authorization Server phát JWT có `jti` duy nhất, `iss`, `aud` và `exp`.
2. Khi revoke, hệ thống ghi một record đã revoke vào shared store với `iss`, `jti` và thời điểm hết hạn.
3. Resource Server sau khi xác minh JWS + claims chuẩn sẽ tra denylist.
4. Nếu có record revoke còn hiệu lực → từ chối token.
5. Record được TTL cleanup sau khi không còn token hợp lệ cần chặn.

~~~mermaid
flowchart LR
    C[Client sends JWT] --> V[Verify signature/issuer/audience/exp]
    V -->|Invalid| X[401]
    V -->|Valid| J[Lookup iss + jti in denylist]
    J -->|Found| X
    J -->|Not found| P[Evaluate scope/authorization]
    P -->|Allowed| OK[API response]
    P -->|Denied| Y[403]
    R[Revocation service] --> E[Durable revoke event]
    E --> S[(Shared revoked-JTI store)]
    S --> J
~~~

Denylist phải được **cập nhật từ đường revoke/admin event đáng tin cậy**. Chỉ thêm validator ở Resource Server mà không có cơ chế ghi denylist từ AS sẽ không có tác dụng. `jti` không thay thế chữ ký; Resource Server vẫn phải xác minh JWT trước khi tin `iss`/`jti`.

### 8.2. Interface do ứng dụng định nghĩa

~~~java
import java.time.Instant;

// Đây là interface của ứng dụng, KHÔNG phải API Spring có sẵn.
public interface RevokedJwtStore {

    // issuer + token ID (jti) đã được chuẩn hóa/trust sau signature validation.
    boolean isRevoked(String issuer, String jti);

    // Ghi record kèm expiration để dọn khi token không thể còn hợp lệ.
    void revoke(String issuer, String jti, Instant expiresAt);
}
~~~

Production cần triển khai bằng storage chia sẻ (Redis/DB hoặc store tương đương), có authentication, encryption-in-transit, persistence/HA, consistent reads và TTL. Không dùng một `ConcurrentHashMap` local riêng cho mỗi pod nếu muốn revoke có hiệu lực đa instance.

### 8.3. Ví dụ Spring Security JwtDecoder với revocation validator

Đây là ví dụ **phía Resource Server**. Nó yêu cầu source JWKS tin cậy, issuer, audience và shared revoked-jti store được cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(RevokedJwtStore revokedJwtStore) {
    String issuer = "https://auth.example.com";
    String jwks = issuer + "/oauth2/jwks";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> notRevoked = jwt -> {
        String jti = jwt.getId();
        if (jti == null || jti.isBlank()
                || revokedJwtStore.isRevoked(issuer, jti)) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Token unavailable", null));
        }
        return OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    standard, audience, notRevoked));

    return decoder;
}
~~~

**Lưu ý bắt buộc:**
- `RevokedJwtStore` là interface tự định nghĩa; thiếu implementation/Bean thì ví dụ không chạy được.
- JWKS URI phải lấy từ metadata/cấu hình thực tế, không giả định mọi issuer dùng `/oauth2/jwks`.
- Không lấy issuer từ JWT chưa xác minh để tự chọn arbitrary JWKS/DB domain.
- `JwtValidators.createDefaultWithIssuer(...)` xử lý kiểm tra chuẩn; audience check được bổ sung rõ ràng.
- Không log token/JTI ra response; thông điệp lỗi nên ngắn/generic.
- Với policy **denylist bắt buộc**, nếu shared store không truy vấn được, phải có **fail-closed** hoặc chính sách degrade được phê duyệt, không mặc định trả “not revoked”.
- Nếu không có `jti` thì ví dụ từ chối; hệ thống phải kiểm token contract, không thêm logic cho phép token thiếu ID.
- Bản ví dụ không có adapter ghi revocation event; phải triển khai **writer** ở AS/revocation service và kiểm thử end-to-end.

### 8.4. Dọn denylist và tính toán TTL

Denylist chỉ cần giữ record trong khoảng token còn có thể được chấp nhận. Với JWT có `exp` và clock-skew tolerance, retention cần bao phủ:

~~~text
denylist retention >=
    max(0, exp - revoke_time)
    + accepted_clock_skew
    + propagation/safety margin
~~~

Nếu xóa record trước khi JWT hết hạn, token có thể được chấp nhận lại. Nếu ghi record sau khi đã trả 200 nhưng propagation chậm, vẫn có cửa sổ sử dụng sau revoke; hệ thống phải đo độ trễ này và bảo đảm nhất quán đọc/ghi theo SLA.

### 8.5. Trade-off

Denylist làm JWT validation không còn hoàn toàn offline, trừ khi Resource Server có cache local hoặc nhận event từ store. Cache giúp giảm I/O nhưng lại tăng cửa sổ stale sau revoke. Đây là lựa chọn có chủ đích, không phải cơ chế bảo mật miễn phí.

## 9. Session version, revocation epoch và kiểm tra quyền động

Denylist theo từng `jti` phù hợp khi revoke một số token xác định. Với logout all devices, disable user hoặc invalidate toàn bộ token của tenant, có thể cân nhắc **version/epoch**.

### 9.1. Revocation epoch

Khi phát JWT, AS thêm metadata đáng tin cậy, ví dụ:
- `auth_time`: thời điểm phiên được xác thực.
- `session_id`/`sid`: định danh phiên.
- `token_version`: version của token family/session.
- `iat`: thời điểm token được phát.

Khi user chọn “logout all”:
1. Hệ thống tăng `token_version` hoặc đặt `valid_after` cho user/session ở shared store.
2. Resource Server so sánh version/token `iat` với trạng thái server-side.
3. Nếu token cũ hơn mốc hiện hành, từ chối.

Ví dụ tư duy:

~~~text
Token của user42 có token_version = 7
User logout-all -> policy store token_version = 8
Resource Server:
    if jwt.token_version < current_token_version: reject
~~~

`token_version` là claim **tự định nghĩa**, không phải claim OAuth2/OIDC chuẩn bắt buộc. Việc tra phiên bản hiện hành vẫn cần state/caching; nếu API chỉ tin version trong JWT mà không hỏi giá trị hiện tại, không đạt được revocation.

### 9.2. Session-bound tokens

Nếu lưu `sid` hoặc session ID:
- Có thể revoke một phiên thiết bị mà không ảnh hưởng tất cả phiên người dùng.
- Có thể dùng state của authorization grant để xác định refresh token family.
- Cần bảo vệ tránh correlation/PII exposure.
- Nếu token không mang `sid` từ khi phát hành, không thể chỉ thêm state trong DB rồi mong JWT cũ có claim này.

### 9.3. Quyền nghiệp vụ cần kiểm tra động

Ví dụ user bị gỡ quyền Approver, nhưng JWT cũ còn claim `roles=["APPROVER"]`. Nếu API chỉ tin claim, quyền đó tồn tại tới expiry trừ khi có supplementary check.

Giải pháp có thể gồm:
- TTL ngắn cho quyền nhạy cảm.
- Policy Decision Point (PDP)/authorization database lookup theo request nguy cơ cao.
- Resource permission version trong token, so với shared policy version.
- Event invalidate cache quyền.
- Step-up authentication cho hành động nhạy cảm.

**Phân biệt token validity với authorization:** token đúng chữ ký và chưa revoke không đồng nghĩa user còn quyền với tài nguyên cụ thể vào lúc API xử lý request.

## 10. Refresh token rotation, revoke grant và quan hệ access token

### 10.1. Thu hồi refresh token ngăn điều gì?

Sau khi refresh token R1 được invalidated:
- Token Endpoint không được cấp access token mới từ R1.
- Nếu bật rotation, refresh token cũ sau lần sử dụng hợp lệ có thể bị vô hiệu hóa và token mới phải được lưu.
- Client phải thực hiện authorization lại hoặc dùng credential/grant khác theo chính sách.

**Không suy ra rằng access token A1 đã phát sẽ mất hiệu lực tại mọi API.** Nếu A1 là JWT self-contained và Resource Server không kiểm trạng thái, A1 vẫn có thể được chấp nhận tới `exp`.

### 10.2. Token family và reuse detection

Refresh token rotation có thể tạo chuỗi R1 → R2 → R3. Nếu attacker dùng lại R1 sau khi R1 đã bị rotate, server có thể coi đây là tín hiệu replay và thu hồi token family/authorization tùy policy.

Điều cần kiểm thử:

| Trường hợp | Kỳ vọng |
|---|---|
| R1 active, refresh thành công | Access token mới; R2 nếu rotation bật |
| R1 bị revoke | Refresh R1 thất bại |
| R1 đã rotate rồi dùng lại | Bị từ chối, kích hoạt replay policy nếu áp dụng |
| Hai request refresh đồng thời | Không có hai nhánh token family hợp lệ ngoài chính sách |
| R2 bị revoke | R2 không refresh; scope cascade được kiểm tra |
| Access token A1 của R1 chưa hết `exp` | API offline JWT vẫn có thể nhận nếu không kiểm revoke |
| User logout-all | Revoke mọi authorization phù hợp + access-token enforcement strategy |

### 10.3. Không xóa record tùy tiện nếu cần audit/revocation

Xóa toàn bộ `OAuth2Authorization` có thể làm Token Endpoint/Introspection không tìm được token (thường inactive), nhưng có thể làm mất thông tin phục vụ audit, replay detection hoặc incident response. Ưu tiên dùng invalidation/revocation API và retention policy theo nghiệp vụ; xóa hẳn sau khi đã hết thời gian cần truy vết.

### 10.4. Client Credentials

Với `client_credentials`, client thường có thể xin access token mới bất cứ khi nào client authentication còn hợp lệ. Revoke một access token **không chặn client xin token khác** nếu credential vẫn active và grant được cho phép.

Nếu cần đình chỉ dịch vụ M2M:
- Disable/revoke RegisteredClient hoặc credential theo policy.
- Thu hồi token đang active/authorization state.
- Có cơ chế Resource Server kiểm invalidation trước `exp` nếu cần ngăn ngay.
- Giám sát token issuance để không phát lại sau khi disable.

## 11. Logout, OIDC session và các token liên quan

Logout ứng dụng thường bao gồm nhiều hành động độc lập:

| Thành phần | Có tự bị revoke khi user logout? |
|---|---|
| Browser app session cookie | Có thể bị xóa theo logout của ứng dụng, nhưng không tự làm token ở API hết hạn |
| Refresh token của client | Cần revoke nếu muốn dừng refresh session |
| Access token opaque | Cần AS mark invalidated và RS introspect/cache ngắn |
| Access token JWT | Cần chờ TTL hoặc có introspection/denylist/epoch |
| OIDC ID Token | Đã phát cho client; có expiry riêng, không phải API access token |
| Authorization consent | Có thể là grant/consent lâu dài; logout không nhất thiết hủy consent |
| Phiên SSO tại Authorization Server | Có thể còn tồn tại nếu chỉ logout local app |
| DPoP/mTLS-bound token | Sender-constraining vẫn cần policy revoke/expiry riêng |

OIDC RP-Initiated Logout, Back-Channel Logout hoặc Front-Channel Logout có vai trò thông báo/điều phối phiên đăng nhập giữa các ứng dụng. Chúng **không thay thế RFC 7009 hoặc Resource Server access-token revocation enforcement**.

Trước khi hứa “Logout all devices”, cần xác định có cả:
- Danh sách authorization/refresh sessions để revoke.
- Cách xác định access token liên quan.
- Cơ chế chặn token tại mọi API.
- Mục tiêu propagation SLA và hành vi khi node unavailable.
- Test đồng bộ trên web, mobile và background jobs.

## 12. Cache, sự kiện thu hồi và hệ thống phân tán

### 12.1. Mô hình event-driven

Khi revoke đã được commit trong store:
1. Transaction ghi invalidation/epoch/denylist.
2. Outbox hoặc cơ chế event đáng tin cậy phát sự kiện revoke (không chứa raw token).
3. Gateway/Resource Server nhận event, cập nhật state hoặc purge cache.
4. API tiếp tục kiểm trạng thái từ shared store hoặc local cache versioned.
5. Nếu event bị mất, TTL/sync/reconciliation giúp hội tụ.

~~~mermaid
flowchart TD
    A[Revoke request or admin policy event] --> B[AuthorizationService transaction]
    B --> C[(Revocation state DB)]
    B --> D[Transactional outbox]
    D --> E[Message broker]
    E --> F[RS A invalidates local cache]
    E --> G[RS B invalidates local cache]
    E --> H[Gateway updates policy cache]
    C --> I[Online introspection / revoked-JTI store]
    I --> F
    I --> G
~~~

Đừng phát event trước khi lưu thành công state rồi trả 200, vì event có thể tới sớm, gây inconsistent read. Nếu không có transactional outbox, cần cơ chế retry, idempotency, replay và monitoring độ trễ.

### 12.2. Idempotency và ordering

- Revoke cùng token nhiều lần không làm token active trở lại.
- Event lặp phải được xử lý idempotent.
- Event tới đảo thứ tự không được ghi đè trạng thái phiên bản mới bằng version cũ.
- Khi user bị disable rồi enable, cần định nghĩa rõ token cũ có hồi sinh hay không; **mặc định không hồi sinh token đã revoke**.
- Nếu store có TTL, không xóa denylist record sớm hơn `exp`.
- Mọi instance phải cùng policy version/issuer/tenant mapping.

### 12.3. Cửa sổ stale cache là giới hạn kiến trúc

Nếu ứng dụng đặt mục tiêu “revoke dưới 2 giây” nhưng RS cache introspection 5 phút thì cấu hình tự mâu thuẫn. Xác định:
- Target maximum revocation latency, theo mức nhạy cảm.
- TTL token và cache.
- Propagation/consistency SLA giữa các region.
- Chi phí kiểm online trên critical path.
- Fail-open/fail-closed khi state backend không truy vấn được.

Độ trễ phải **được đo từ thời điểm revoke commit đến thời điểm mọi RS bắt đầu từ chối token**, không chỉ đo từ request tới AS trả 200.

## 13. Thiết kế chiến lược theo nhu cầu

| Nhu cầu | Phương án | Điểm cần kiểm soát |
|---|---|---|
| API tốc độ cao, risk thấp, revoke có thể trễ vài phút | JWT ngắn hạn + revoke refresh token | Residual access TTL, key rotation, grant policy |
| API nhạy cảm, revoke gần tức thời | Opaque token + introspection trực tiếp/cached rất ngắn | AS/DB HA, latency, fail-closed, caller permission |
| Muốn JWT nhưng revoke nhanh | JWT + denylist `jti`/session epoch check | Shared store, event propagation, stale cache, jti contract |
| Logout-all | Revoke authorization/refresh sessions + session version/denylist | Áp dụng tới mọi RS và device |
| Client secret bị compromise | Disable credential/client + revoke associated grants/tokens | Đang tồn tại JWT offline vẫn cần RS enforcement |
| Người dùng bị gỡ quyền | Dynamic authorization/policy version, có thể revoke tokens | Không chỉ dựa vào scope/roles cũ trong JWT |
| Rủi ro replay token bị lộ | Sender-constrained tokens như DPoP/mTLS + TTL/revocation | Không thay thế revoke khi private key cũng bị lộ |
| Hệ thống outage không được cấp quyền sai | Introspection/denylist fail-closed | Availability, degraded-mode policy, error handling |
| Hệ thống nhiều region | Event + shared state + bounded caches | Consistency, ordering, replay, reconciliation |

**Không có một công thức áp dụng mọi hệ thống.** TTL càng ngắn càng giảm residual window, nhưng tăng load và phụ thuộc Token Endpoint. Kiểm online đem lại trạng thái mới nhưng làm tăng latency/cost và phụ thuộc dịch vụ. Event-driven giảm call nhưng cần vận hành consistency và recovery.

## 14. Kiểm thử revocation end-to-end

### 14.1. Ma trận tình huống

| Test | Kỳ vọng |
|---|---|
| Revoke refresh token hợp lệ bằng đúng client | 200; refresh tiếp theo thất bại |
| Revoke lại cùng token hoặc token unknown | 200, không tiết lộ tồn tại |
| Revoke bằng client sai credential | 401 hoặc OAuth2 client-auth error tương ứng |
| Revoke token thuộc client khác | Bị từ chối đúng security policy |
| Revoke R1 và introspect A1 cùng grant | Kết quả theo cascade đã cam kết, phải test |
| Revoke A1 nhưng refresh token còn active | Có thể phát token mới nếu policy không cascade; phải tài liệu hóa |
| Opaque A1 sau revoke, introspection không cache | `active=false` |
| Opaque A1 sau revoke, RS cache 10s | Thời gian còn chấp nhận token không vượt budget đã định |
| JWT A1 sau revoke, RS chỉ verify offline | Có thể vẫn được nhận trước `exp` (test minh họa giới hạn) |
| JWT A1 sau revoke, RS có denylist | Trả 401 khi state đã propagation |
| JWT A1 sai issuer/audience/exp | Trả 401 dù không bị revoke |
| Disable client M2M | Không phát token mới; token cũ bị chặn theo policy |
| Refresh token rotation và replay | R1 cũ bị từ chối; token family xử lý theo policy |
| User logout-all | Mọi session/token thuộc policy không còn được API nhận sau SLA |
| AS/DB unavailable khi API introspect | Fail-closed hoặc degraded mode được phê duyệt |
| Event revoke bị gửi lặp, đảo thứ tự | State không hồi sinh |
| RS restart/scale-out | Revoke state không mất vì không chỉ lưu local memory |
| Multi-region failover | Region mới từ chối token đã revoke theo SLA |

### 14.2. Test RFC 7009 bằng MockMvc

Giả sử app test có confidential RegisteredClient `employee-portal`, `CLIENT_SECRET_BASIC`, token hợp lệ trong `OAuth2AuthorizationService` và endpoint `/oauth2/revoke`.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenRevocationContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void revokeKnownRefreshTokenReturnsSuccess() throws Exception {
        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("employee-portal", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "TEST_REFRESH_TOKEN")
                .param("token_type_hint", "refresh_token"))
            .andExpect(status().isOk());
    }

    @Test
    void unknownTokenStillReturnsSuccessForValidCaller() throws Exception {
        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("employee-portal", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "UNKNOWN_TEST_VALUE"))
            .andExpect(status().isOk());
    }
}
~~~

Đây là **mẫu assertions**, chưa phải test chạy độc lập: phải tạo fixture RegisteredClient, encoder, authorization record và import JUnit/MockMvc/Spring Security Test. Với case revoke known token cần assertions **sau response**: gọi refresh grant thất bại, tra `OAuth2AuthorizationService` hoặc introspection xác nhận state, rồi gọi Resource Server để kiểm thực thi. Test chỉ đợi 200 **không chứng minh revoke đã có hiệu lực**.

### 14.3. Test Resource Server JWT

Với JWT access token:
1. Phát token A1 còn hạn, có `jti`, `iss`, `aud` và `exp`.
2. Gọi API với A1: 200 khi đủ scope.
3. Revoke A1/authorization tại AS, xác nhận persistence.
4. Gọi API offline JWT-only: ghi nhận A1 **có thể vẫn được chấp nhận**; đây là limitation cần quyết định.
5. Bật denylist validator hoặc introspection, đảm bảo revocation record/event được ghi.
6. Gọi lại API với A1: 401 sau propagation, không vượt latency budget.
7. Kiểm tra token không bị revoke tiếp tục hoạt động.
8. Cho `exp` qua hạn; validator từ chối ngay cả khi denylist bị xóa đúng TTL.
9. Thử wrong audience, wrong issuer, wrong signature; đều bị từ chối.
10. Restart các replica và xác nhận state vẫn còn.

### 14.4. Test Resource Server opaque

1. Phát opaque token O1, introspection báo `active=true`.
2. Gọi API O1 thành công.
3. Revoke O1 hoặc refresh token liên quan theo policy.
4. Introspect lại: `active=false` sau khi state đã commit.
5. Gọi API O1; xác nhận 401 sau cache TTL đã chọn.
6. Kiểm network timeout, 503, body malformed và credential introspection sai; không fail-open.
7. Load test nhiều concurrent introspection request và rate limit theo caller.

### 14.5. Đo SLO thu hồi

Đề xuất test metric:

~~~text
revocation_effective_at =
    first_timestamp_when_every_relevant_resource_server_rejects_token

revocation_latency =
    revocation_effective_at - revocation_commit_timestamp
~~~

Trong production, không cần lưu raw token để đo; có thể dùng synthetic test token, token fingerprint/id nội bộ với quyền hạn và retention chặt. Cần đo p95/p99 và worst-case trong rolling deployment/network partitions, không chỉ một test local.

## 15. Những lỗi phổ biến khi triển khai

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Revocation Endpoint trả 200 nhưng API vẫn 200 | JWT verify offline, không kiểm revoke | TTL ngắn hơn hoặc introspection/denylist/epoch |
| Refresh R1 không dùng được nhưng A1 vẫn vào API | Chỉ ngăn cấp token mới | Thiết kế access-token enforcement |
| Opaque token đã revoke nhưng API còn nhận | Introspection cache active lâu | Giảm TTL cache, purge event, đo SLA |
| Một replica nhận revoke, replica khác không biết | In-memory authorization/denylist | Shared persistent store, propagation & HA |
| JWT denylist bị xóa trước token expiry | Record TTL quá ngắn | Giữ qua `exp` + clock skew + safety margin |
| JWT vẫn hợp lệ khi disable client | RS offline không kiểm client status | Session/client epoch hoặc introspection |
| JWT validator từ chối mọi token do DB outage | Fail-closed nhưng availability thấp | Thiết kế HA, circuit breaker, policy degraded mode |
| Event revoke bị mất | Chỉ dựa fire-and-forget | Durable outbox, retries, reconciliation |
| Access token bị revoke nhưng client xin token mới | Grant/credential vẫn active | Disable client/revoke grant theo scope sự cố |
| Delete JWK làm mọi token fail | Dùng key rotation như revoke | Chỉ dùng emergency rotation khi compromise, theo incident plan |
| `active=false` vẫn để lộ thông tin | Introspection thêm error details/claims | Response tối giản theo RFC 7662 |
| User logout local app nhưng vẫn SSO/refresh | Thiếu liên kết giữa app session và AS | Thiết kế OIDC logout + revoke grant/refresh |
| Client Credentials worker liên tục lấy token mới | Revoke một token nhưng client còn quyền | Disable client/policy, rotate compromised credential |
| Resource Server cache không phân vùng caller | Chia sẻ state giữa tenant/issuer | Cache key có issuer, resource/tenant, token |
| Scope/roles cũ còn quyền sau khi user bị gỡ role | Claims trong JWT stale | Dynamic authorization, epoch hoặc TTL ngắn |
| Token revocation HTTP 503 bị coi là thành công | Nhầm outage với 200 | Retry/backoff, cảnh báo và state xác nhận |

## 16. Bài tập thực hành

**Bối cảnh:** Hệ thống bán hàng có:
- `employee-portal`: Authorization Code + OIDC, access token JWT TTL 15 phút, refresh token TTL 14 ngày.
- `inventory-worker`: Client Credentials, JWT TTL 5 phút.
- `billing-api`: API nhạy cảm yêu cầu revoke có hiệu lực trong vòng 10 giây.
- `reporting-api`: API lưu lượng cao cho phép residual window tối đa 5 phút.

**Yêu cầu:**

1. Mô tả luồng cấp và revoke access/refresh token cho từng client; nêu rõ token nào có thể sống sau logout.
2. Chọn phương án cho `billing-api`: introspection với cache rất ngắn hoặc JWT + shared denylist/epoch.
3. Chọn phương án cho `reporting-api`: JWT TTL ngắn, verify offline hoặc phương án bổ sung theo risk.
4. Cấu hình `TokenSettings` phù hợp, không sửa `expires_in` bằng response handler.
5. Cấu hình `OAuth2AuthorizationService` dùng shared persistence và kiểm tra `isActive()`/`isInvalidated()`.
6. Test Revocation Endpoint RFC 7009: 200 cho token hợp lệ/unknown, lỗi credential khác và xử lý `token_type_hint`.
7. Với opaque token, cấu hình Resource Server introspection và xác nhận `active=false` sau revoke.
8. Với JWT, implement `RevokedJwtStore`, event writer và Resource Server validator; đo độ trễ event/cache.
9. Bổ sung logic cho logout-all bằng revoke grant/refresh session hoặc session version.
10. Test refresh rotation/replay, client disable, role removal và key compromise riêng.
11. Chạy hai Resource Server replica và hai Authorization Server replica; thử restart, outage và event duplicate.
12. Viết runbook `logout-all` và `compromised-client-secret`, gồm SLA, metric, rollback và owner.

**Tiêu chí hoàn thành:** không nhầm HTTP 200 từ Revocation Endpoint với thực thi tại API; billing từ chối token đã revoke trong 10 giây theo test, reporting tuân TTL/risk đã chọn; refresh token đã revoke không phát token mới; lỗi/outage không làm quyền truy cập bị mở rộng.

## 17. Checklist trước khi production

- [ ] Phân biệt TTL, revocation, introspection, authorization và logout.
- [ ] RFC 7009 request POST qua HTTPS với `token` bắt buộc, `token_type_hint` chỉ là hint.
- [ ] Response 200 cho token hợp lệ đã revoke và unknown token, không tạo token-existence oracle.
- [ ] Client authentication và token ownership được kiểm tra, không để caller revoke token của client khác.
- [ ] Revocation Endpoint/Introspection Endpoint ở đúng public issuer và có TLS.
- [ ] AuthorizationService persistent/shared, invalidation metadata được lưu bền vững.
- [ ] Cascade access/refresh grant được kiểm thử theo policy và framework version.
- [ ] Có câu trả lời rõ ràng cho access JWT đã phát vẫn còn hạn sau revoke.
- [ ] Access token TTL và refresh token TTL phù hợp rủi ro, có refresh rotation khi cần.
- [ ] Nếu dùng introspection, cache TTL nhỏ hơn revoke SLA và không vượt `exp`.
- [ ] Nếu dùng JWT denylist, writer/event propagation và reader validator đều hiện diện.
- [ ] Denylist record retention bao phủ `exp`, clock skew và safety margin.
- [ ] Nếu dùng session/version epoch, Resource Server kiểm trạng thái version hiện hành.
- [ ] Resource Server validate chữ ký, issuer, audience, expiry và scope/permission, không chỉ trạng thái revoke.
- [ ] Không dùng key rotation bình thường như cơ chế revoke token đơn lẻ.
- [ ] Có policy khi AS/introspection/denylist backend unavailable; không tự fail-open.
- [ ] Sự kiện thu hồi idempotent, có retry/replay, ordering và reconciliation.
- [ ] Token/cache state không rò qua logs, metrics, headers hoặc error descriptions.
- [ ] Đã test end-to-end từ revoke commit tới API 401 trên mọi replica.
- [ ] Đã đo p95/p99 revocation latency và kiểm chứng theo SLO.
- [ ] Có runbook cho logout, compromise, disable client và mất signing key.
- [ ] Không nhận định việc hoàn thành bài đồng nghĩa hệ thống đã qua security QA/production readiness.

## Tổng kết

**TTL** giới hạn thời gian token có thể được chấp nhận nhưng không thực hiện thu hồi chủ động. **Revocation Endpoint** theo RFC 7009 thay đổi trạng thái token/authorization tại Authorization Server và ngăn các thao tác tương lai như refresh; **Resource Server** phải có cách thấy trạng thái đó mới từ chối access token đã phát trước hạn.

Với **opaque/reference token**, introspection theo RFC 7662 là cách trực tiếp để kiểm trạng thái nhưng cache và network quyết định độ trễ. Với **JWT tự chứa**, Resource Server kiểm chữ ký offline không tự biết token bị revoke: cần TTL đủ ngắn hoặc bổ sung introspection, revoked-`jti` denylist, session epoch, dynamic authorization check và event/cache invalidation. Mỗi cơ chế đổi lấy một mức latency, availability và chi phí vận hành khác nhau.

Trong hệ thống production, thành công không được đo bằng “API revoke trả 200”, mà bằng **token đã bị thu hồi có bị mọi Resource Server từ chối trong thời gian đã cam kết hay không**, ngay cả sau restart, khi cache còn dữ liệu cũ hoặc trong rolling deployment.

## Tài liệu tham khảo

1. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation request, 200 response, token_type_hint, cascade policy và implementation notes về self-contained token.
2. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): `active`, caller authorization, privacy, caching và TLS.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Revocation/Introspection configurers và các hook chuẩn.
4. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationService`, `OAuth2Authorization`, `TokenSettings` và token formats.
5. [Spring Authorization Server 1.5.8 — OAuth2TokenRevocationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationProvider.html): provider chuẩn xử lý revoke.
6. [Spring Authorization Server 1.5.8 — OAuth2Authorization.Token API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Token.html): `isActive()`, `isInvalidated()` và metadata token.
7. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection cho opaque token và cả JWT nếu cần online validation.
8. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, signature/issuer validation và custom validators.
9. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): `exp`, `iat`, `jti` và JWT claims.
10. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): token sender-constraining, refresh rotation và replay/compromise handling.
11. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): JWT algorithm, issuer/audience và validation.
12. [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): giao thức logout OIDC ở Client/OP, khác với access-token revocation.

