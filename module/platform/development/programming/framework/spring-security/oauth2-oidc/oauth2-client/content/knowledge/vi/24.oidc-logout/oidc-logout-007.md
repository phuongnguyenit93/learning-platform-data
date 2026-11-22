# 24.7. OIDC Back-Channel Logout: khái niệm, logout token và phiên liên quan

## 1. Vấn đề: đăng xuất ở Identity Provider nhưng ứng dụng vẫn còn phiên

Trong **Spring Security OAuth 2.0 OIDC Client**, một ứng dụng Spring Boot thường đóng vai trò **Relying Party (RP)**: nó cho người dùng đăng nhập qua **OpenID Provider (OP)**, sau đó duy trì phiên đăng nhập riêng ở ứng dụng bằng `HttpSession`, `WebSession` hoặc một cơ chế session phù hợp.

Ví dụ, Alice đăng nhập vào ba ứng dụng sử dụng cùng một OP:

~~~text
                       OpenID Provider
                      (SSO login session)
                        /     |     \
                       /      |      \
                  Portal    Reports   Billing
                   RP A      RP B      RP C
                   |          |         |
                Session A  Session B  Session C
~~~

Khi Alice đăng xuất trực tiếp tại OP, **phiên ở Portal, Reports và Billing không nhất thiết tự biến mất**. Mỗi RP có session cookie, local security context và vòng đời session riêng. OP không thể đơn giản xóa cookie của từng RP trên các domain khác nhau.

**OpenID Connect Back-Channel Logout 1.0** giải quyết bài toán này bằng giao tiếp **server-to-server**:

1. OP biết những RPs có phiên liên quan đến người dùng.
2. Khi OP quyết định logout, OP gửi một HTTP POST trực tiếp đến endpoint logout đã đăng ký của từng RP.
3. POST chứa một **Logout Token** có chữ ký, mô tả người dùng hoặc phiên OP cần đăng xuất.
4. RP xác minh token và tìm các **local sessions** tương ứng.
5. RP kết thúc những phiên đó mà không đòi trình duyệt người dùng đang mở.

Bài học tập trung vào **khái niệm**, **Logout Token**, **`sid` / `sub`**, **ánh xạ phiên**, tích hợp Spring Security Servlet/Reactive và các lưu ý bảo mật/vận hành.

### Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt local logout, RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout.
- Diễn giải HTTP POST `logout_token` và các JWT claims bắt buộc theo chuẩn.
- Phân biệt `sid` của OP với local `JSESSIONID` / `SESSION` của RP.
- Hiểu vì sao cần **OIDC session registry** để liên kết phiên OP với phiên ứng dụng.
- Cấu hình `oidcLogout().backChannel(...)` trong Spring Security Servlet và Reactive theo API tương ứng.
- Xử lý các vấn đề session store, cookie name, multi-instance, multi-tenant và token revocation.
- Thiết kế validation, idempotency, monitoring và integration tests không làm lộ token.

> **Phạm vi phiên bản:** Các ví dụ tập trung vào API back-channel logout của những phiên bản Spring Security có hỗ trợ `oidcLogout().backChannel(...)`, chẳng hạn nhánh Spring Security 6.5 và 7.x. Tên class/API và cách cấu hình phụ thuộc Servlet hoặc Reactive stack. Hãy dùng tài liệu ứng với phiên bản Spring Security được BOM của dự án quản lý; không copy class từ một major version khác khi thiếu compatibility.

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Vai trò |
| --- | --- |
| **OP (OpenID Provider)** | Hệ thống xác thực người dùng và phát hành ID Token |
| **RP (Relying Party)** | Ứng dụng OIDC Client tin vào ID Token đã được xác minh |
| **SSO session** | Phiên tại OP giúp user đăng nhập vào nhiều RPs |
| **RP local session** | Phiên riêng của ứng dụng, ví dụ `HttpSession` / `WebSession` |
| **`sub` (subject)** | Định danh người dùng theo issuer của OP |
| **`sid` (OP session ID)** | Định danh phiên tại OP, giúp chọn chính xác phiên liên quan |
| **Logout Token** | JWT do OP ký, yêu cầu RP kết thúc phiên được mô tả |
| **Back-Channel Logout URI** | Endpoint RP đăng ký cho OP gửi Logout Token qua HTTP POST |
| **OIDC Session Registry** | Bộ nhớ ánh xạ OP session/subject/client sang local RP sessions |
| **`registrationId`** | ID cấu hình Spring Security `ClientRegistration` |
| **`aud`** | Audience của Logout Token, phải tương ứng client ID của RP |

### 2.1. OP session không phải RP session

Ví dụ:

~~~text
OP:
  issuer = https://id.example.net/realms/company
  sub    = user-123
  sid    = op-session-9b1e

RP Portal:
  registrationId = company
  clientId       = portal-web-client
  JSESSIONID     = rp-session-a731

RP Reports:
  registrationId = company
  clientId       = reports-web-client
  JSESSIONID     = rp-session-f028
~~~

**`sid` không phải giá trị cookie `JSESSIONID`**. OP phát `sid` theo logic phiên của mình; RP có một local session ID riêng. Registry liên kết hai miền định danh.

Không được xóa `HttpSession` bằng cách coi giá trị `sid` trong Logout Token là trực tiếp `JSESSIONID`.

### 2.2. `sub` phải được hiểu cùng issuer

`sub="user-123"` từ:

~~~text
https://id.example.net/realms/company
~~~

không mặc nhiên là cùng tài khoản với `sub="user-123"` từ:

~~~text
https://login.partner.example.org
~~~

Khi tìm phiên để logout, phải ràng buộc **issuer, audience/client registration và subject/session**, không chỉ dùng một chuỗi username hoặc email.

## 3. Back-Channel Logout khác các kiểu logout khác như thế nào?

| Cơ chế | Ai khởi tạo? | Luồng liên lạc | Mục tiêu |
| --- | --- | --- | --- |
| **Local Logout** | RP hoặc user tại RP | Browser gửi request tới RP | Kết thúc local session của RP |
| **RP-Initiated Logout** | RP | Browser được chuyển đến `end_session_endpoint` của OP | Yêu cầu OP kết thúc session SSO |
| **Front-Channel Logout** | OP | OP dùng browser/iframe/redirect gọi các RPs | Kết thúc các RP sessions qua user agent |
| **Back-Channel Logout** | OP | **OP gửi HTTP POST server-to-server** đến RP | Kết thúc RP sessions bằng Logout Token |

### 3.1. Vì sao back-channel hữu ích?

Back-channel không cần trình duyệt có tab RP đang mở. OP có thể gửi yêu cầu logout ngay cả khi user:

- Đã đóng tab Portal nhưng cookie Portal còn hiệu lực.
- Chỉ đăng xuất ở một hệ thống khác dùng cùng OP.
- Bị quản trị viên kết thúc phiên OP.
- Được xử lý chính sách global logout.

Nhưng **không có nghĩa back-channel tuyệt đối luôn giao hàng thành công**. Nếu RP không truy cập được từ OP, network bị gián đoạn hoặc session registry mất dữ liệu, logout có thể bị trì hoãn/thất bại.

### 3.2. Những hạn chế của back-channel

Back-channel **không**:

- Trực tiếp xóa cookie đang nằm trong browser của người dùng.
- Tự gửi một thông báo realtime đến SPA đang mở.
- Tự revoke mọi Access Token/Refresh Token đã cấp.
- Tự kết thúc mọi session của các ứng dụng không đăng ký nhận back-channel.
- Thay thế một cơ chế local logout hoặc token expiration policy.
- Tự kiểm tra mọi quyền của Resource Server.

Thông thường, RP **invalidate server-side session**. Cookie cũ còn ở browser sẽ trở nên vô dụng; request kế tiếp bị yêu cầu xác thực lại. Nếu sản phẩm muốn cập nhật giao diện ngay, có thể bổ sung một cơ chế thông báo frontend được thiết kế riêng.

## 4. OP và RP phải công bố/đăng ký khả năng back-channel

### 4.1. OP Discovery Metadata

OP có thể công bố:

~~~json
{
  "issuer": "https://id.example.net/realms/company",
  "backchannel_logout_supported": true,
  "backchannel_logout_session_supported": true
}
~~~

Hai trường quan trọng:

- `backchannel_logout_supported`: OP có hỗ trợ cơ chế này hay không; mặc định là `false` khi không công bố.
- `backchannel_logout_session_supported`: OP có thể phát `sid` trong Logout Token và tương ứng trong ID Token hay không; nếu không, việc logout dựa trên `sub` có thể là cơ chế còn lại.

**Không mặc định có `sid`** nếu OP không hỗ trợ session-based logout. Trước khi bật tính năng, kiểm tra chính xác metadata của issuer và hợp đồng/provider console.

### 4.2. RP đăng ký backchannel_logout_uri

RP cần khai báo **URI tuyệt đối** mà OP có thể gửi HTTP POST:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

Theo chuẩn, metadata client registration gồm:

~~~json
{
  "backchannel_logout_uri":
    "https://portal.example.net/logout/connect/back-channel/company",
  "backchannel_logout_session_required": false
}
~~~

`backchannel_logout_session_required` biểu thị RP **có bắt buộc OP cung cấp `sid`** khi logout hay không. Không tự đặt `true` nếu OP chỉ hỗ trợ logout dựa trên `sub`.

URI phải trỏ đúng **RP deployment** và **Spring Security registrationId**; việc khai báo URI với OP có thể thực hiện trong admin console hoặc Dynamic Client Registration. Đừng nhầm `backchannel_logout_uri` là thuộc tính YAML tiêu chuẩn tự động cấu hình OP chỉ bằng việc thêm vào `spring.security.oauth2.client.registration.*`.

### 4.3. Network reachability là điều kiện thật

OP cần **gọi được RP endpoint** qua kênh back-channel:

~~~text
OP server network
    |
    | HTTPS POST
    v
Ingress / reverse proxy / WAF
    |
    v
Spring Boot RP endpoint
~~~

Nếu RP chỉ chạy trên `localhost` laptop, một OP bên ngoài Internet thường **không** truy cập được địa chỉ đó. Nếu RP ở private network, cần đường kết nối tin cậy phù hợp (private connectivity, gateway, firewall allowlist...), không mở endpoint tùy tiện mà không có xác thực Logout Token.

Trong production, sử dụng HTTPS, kiểm tra TLS và rate limiting; tránh trả raw diagnostic secrets qua response.

## 5. Dòng chảy end-to-end của Back-Channel Logout

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant RP as Spring Security RP
    participant Registry as OIDC Session Registry
    participant OP as OpenID Provider
    User->>Browser: Mở /dashboard
    Browser->>RP: Request chưa login
    RP-->>Browser: Redirect tới OP
    Browser->>OP: OIDC Authorization Code Flow
    OP-->>Browser: Callback code/state
    Browser->>RP: /login/oauth2/code/company
    RP->>OP: Token Endpoint, đổi code
    OP-->>RP: ID Token có iss/sub/sid, Access Token
    RP->>RP: Xác minh OIDC và tạo local session
    RP->>Registry: Lưu liên kết OP session -> RP session
    RP-->>Browser: Set-Cookie JSESSIONID; redirect
    User->>OP: Logout tại OP hoặc admin revoke session
    OP->>RP: POST /logout/connect/back-channel/company
    Note over OP,RP: logout_token = signed JWT
    RP->>RP: Validate chữ ký, iss, aud, exp, events, sid/sub...
    RP->>Registry: Tìm local sessions theo sid hoặc iss+sub+aud
    Registry-->>RP: Các local session IDs liên quan
    RP->>RP: Invalidate đúng sessions, chạy logout hooks phù hợp
    RP-->>OP: HTTP 200 khi thành công
    Browser->>RP: Request tiếp theo với cookie cũ
    RP-->>Browser: Không còn authenticated session
~~~

Điểm then chốt: **OP không cần local RP cookie**. RP đã lưu một ánh xạ giữa phiên OP và local session **tại lúc OIDC Login thành công**. Khi nhận Logout Token, RP mới có đủ thông tin để chọn phiên.

### 5.1. Hai giai đoạn dữ liệu

Giai đoạn login:

~~~text
(issuer, audience/client, sub, sid)
            |
            v
     Local session ID
~~~

Giai đoạn logout:

~~~text
Verified Logout Token
     iss + aud + sid/sub
            |
            v
    Query OIDC Session Registry
            |
            v
  Invalidate matching local sessions
~~~

Nếu không có bản ghi mapping tương ứng, RP **không được đoán** session cần xóa dựa trên email hoặc chuỗi token chưa xác minh. Một request logout hợp lệ nhưng không còn phiên phù hợp vẫn có thể được coi là đã hoàn tất.

## 6. HTTP request của Back-Channel Logout

### 6.1. OP gửi POST, không dùng browser redirect

Theo OpenID Connect Back-Channel Logout, OP gửi:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.net
Content-Type: application/x-www-form-urlencoded
Accept: */*

logout_token=SIGNED_LOGOUT_JWT_PLACEHOLDER
~~~

`logout_token` là **form parameter** có giá trị JWT (JWS/JWE theo cấu hình), không phải Access Token trong Authorization header.

**Không nhầm**:

~~~http
GET /logout?sid=op-session-123
~~~

với Back-Channel Logout chuẩn. Một request GET có `sid` trong query string không chứng minh người gửi là OP và **không được dùng để invalidate session**.

### 6.2. Endpoint mặc định trong Spring Security

Với registration ID `company`:

~~~text
POST https://portal.example.net/logout/connect/back-channel/company
~~~

Path mặc định được Spring Security trình bày dưới dạng:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

`registrationId` là **key của `ClientRegistration`**, không phải client ID thật, username, subject hay sid. OP phải được cấu hình để gọi đúng path mà ứng dụng triển khai.

### 6.3. Response theo chuẩn

Khi logout thành công:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

Chuẩn yêu cầu HTTP `200 OK` khi thành công; OP cũng nên chấp nhận `204 No Content` do một số frameworks dùng 204 khi không có body.

Nếu logout request sai/không hợp lệ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_request"}
~~~

Đây là response minh họa. Không phản hồi raw JWT, token, stack trace hoặc nội dung nhạy cảm cho caller. Trường hợp mất mạng, timeout hoặc không thể xử lý session sẽ cần chính sách recovery/retry riêng; đừng báo thành công giả nếu logout chưa được thực hiện theo contract.

### 6.4. Đã logout rồi thì sao?

Nếu OP gửi lại thông báo hợp lệ cho một session đã bị xóa, hành vi **idempotent** là coi mục tiêu logout đã đạt. Không khôi phục session hoặc coi đó là lý do để xóa nhầm một session mới cùng email.

Replay detection theo `jti` vẫn có thể được sử dụng để giới hạn replay; cần quyết định xử lý duplicate sao cho an toàn và phù hợp đáp ứng của OP.

## 7. Logout Token là gì?

**Logout Token** là một **JWT được OP ký**, tương tự hình thức ID Token nhưng **mục đích khác**: nó mang một sự kiện yêu cầu RP kết thúc các phiên liên quan.

Thông thường JWS có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Logout Token **không phải**:

- ID Token để đăng nhập.
- OAuth2 Access Token để gọi Resource Server.
- Refresh Token để đổi lấy Access Token mới.
- Session cookie của trình duyệt.
- Authorization Code trả về khi login.

### 7.1. JWT header minh họa

~~~json
{
  "alg": "RS256",
  "typ": "logout+jwt",
  "kid": "op-key-2026-01"
}
~~~

`typ=logout+jwt` được **khuyến nghị** để phân biệt Logout Token với các JWT khác. Theo chuẩn, đây không phải yêu cầu tuyệt đối cho mọi deployment legacy; đừng tự tạo giả định rằng các OP hợp lệ trước đây luôn có header `typ`.

`alg` phải là thuật toán ký được phép theo OIDC/client registration. **Không chấp nhận `alg=none`**, không dùng một thuật toán do payload không đáng tin tự quyết định. `kid` hỗ trợ xác định public signing key từ JWKS issuer đã tin cậy, không phải lời mời tải key từ URL bất kỳ trong JWT header.

### 7.2. JWT claims minh họa

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "sub": "user-123",
  "aud": "portal-web-client",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-event-7c3d52",
  "sid": "op-session-9b1e",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

**Đây chỉ là payload mẫu**, không phải JWT đã ký, cũng không có hiệu lực để logout phiên thật. Trong thực tế, OP phải phát JWT bằng signing key của issuer. Các timestamps minh họa có thể không còn phù hợp thời điểm chạy; `exp` phải được validation so với đồng hồ hiện tại.

### 7.3. Ý nghĩa từng claim

| Claim | Bắt buộc? | Vai trò |
| --- | --- | --- |
| `iss` | Có | Đúng OP issuer đã đăng ký |
| `aud` | Có | RP OAuth2 client ID nhận Logout Token |
| `iat` | Có | Thời điểm JWT được phát hành |
| `exp` | **Có theo bản 1.0 incorporating errata set 1** | Hạn cuối chấp nhận Logout Token |
| `jti` | Có | ID duy nhất của Logout Token, hỗ trợ chống replay |
| `events` | Có | Chỉ định sự kiện OIDC back-channel logout |
| `sub` | Tùy chọn độc lập | Định danh người dùng, cần khi không có sid |
| `sid` | Tùy chọn độc lập | Định danh OP session cụ thể |
| `nonce` | **Bị cấm** | Logout Token **không được chứa `nonce`** |

Điều kiện kết hợp: Logout Token **phải có ít nhất một trong `sub` hoặc `sid`**, và có thể có cả hai.

**Lưu ý phiên bản chuẩn:** một số tài liệu/triển khai dựa trên bản Final 2022 không liệt kê `exp` trong cùng cách như bản **incorporating errata set 1 (2023)**. Khi xây validator mới, dựa trên bản errata mới và kiểm tra mức tương thích OP/Spring Security theo deployment, không âm thầm bỏ yêu cầu expiration.

### 7.4. Claim `events` phải đúng

Logout Token phải chứa một object `events` với member:

~~~json
{
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Nếu JWT có `iss`, `sub` và signature hợp lệ nhưng **không có event back-channel logout**, nó **không phải** một Logout Token hợp lệ để xóa session.

### 7.5. Tại sao `nonce` bị cấm?

OIDC ID Token có thể chứa `nonce` để ràng buộc authentication response với authorization request. Back-Channel Logout lại là **sự kiện từ OP đến RP không thông qua login authorization request**, vì thế việc dùng `nonce` trong Logout Token không phù hợp.

Chuẩn cấm `nonce` còn để giảm nguy cơ **JWT confusion**: kẻ tấn công thử dùng Logout Token như ID Token trong authentication flow, hoặc ngược lại.

**Không** so sánh `nonce` của Logout Token với nonce login rồi “coi khớp là hợp lệ”; trường này không được xuất hiện.

## 8. Quy tắc validation Logout Token

Đây là bước **bắt buộc trước khi thay đổi session**. Không xử lý logout chỉ vì payload được base64url decode thành JSON có vẻ đúng.

### 8.1. Quy trình validation theo chuẩn

1. **Đọc form parameter `logout_token`** từ HTTP POST đúng endpoint.
2. Nếu token được mã hóa theo hợp đồng JWE, **giải mã** bằng key/algorithm được phép; kiểm tra policy nếu client đã đàm phán ID Token encryption.
3. Xác minh **JWS signature** bằng key của **đúng OP issuer** đã được đăng ký.
4. Chỉ chấp nhận `alg` hợp lệ theo OP/client configuration; reject `alg=none`, sai algorithm, key/issuer không tin cậy.
5. Kiểm tra `iss` **khớp issuer** của registration nhận sự kiện.
6. Kiểm tra `aud` chứa **client ID** của RP đúng registration, không phải chỉ chứa registrationId.
7. Kiểm tra `iat` và `exp` hợp lệ, token chưa hết hạn, xử lý clock skew hợp lý.
8. Yêu cầu `jti` hợp lệ; nếu triển khai replay cache, kiểm tra chưa xử lý ID đó trong cửa sổ tương ứng.
9. Kiểm tra `events` chứa chính xác member back-channel logout có JSON object.
10. Kiểm tra **ít nhất một** `sub` hoặc `sid` hiện diện.
11. **Từ chối nếu có claim `nonce`**.
12. Ràng buộc `iss` / `sub` / `sid` với thông tin session OIDC đã lưu theo đúng provider/client.
13. **Chỉ khi mọi kiểm tra cần thiết đều qua**, mới xác định phiên và thực thi logout.

### 8.2. Những trường hợp phải từ chối

| Input | Vì sao không hợp lệ |
| --- | --- |
| JWT không có chữ ký hoặc `alg=none` | Không chứng minh OP phát sự kiện |
| Chữ ký sai hoặc `kid` không thuộc issuer | Không xác minh được nguồn |
| `iss` là OP khác | Không được chạm session thuộc issuer này |
| `aud` là client ID khác | Token không dành cho RP này |
| Thiếu `events` logout event | Có thể là loại JWT khác |
| Thiếu cả `sub` lẫn `sid` | Không xác định được đối tượng logout |
| Có `nonce` | Logout Token không được chứa nonce |
| `exp` đã hết hạn | Không còn trong cửa sổ hiệu lực |
| `iat` bất hợp lý ngoài policy | Có nguy cơ stale/future token |
| JWE/alg/key không được phép | Sai hợp đồng mã hóa/ký |
| `jti` replay theo policy reject | Nguy cơ yêu cầu bị phát lại |

### 8.3. Không dùng Token Endpoint introspection thay JWT validation

Logout Token là JWT **sự kiện logout**. Không được coi nó như Bearer Access Token để gọi introspection endpoint mà bỏ qua kiểm tra signature/claims theo OIDC Back-Channel Logout spec.

Nếu dùng thư viện/framework Spring Security có sẵn, hãy để nó thực hiện validation theo contract, thay vì tự viết parser kiểm tra vài trường rồi gọi session.invalidate().

### 8.4. Pseudocode của validator

~~~java
// PSEUDOCODE — đây KHÔNG phải bộ JWT decoder đầy đủ.
void onBackChannelLogout(SignedJwt incoming, ClientRegistration expected) {
    VerifiedLogoutToken event =
        strictOidcLogoutTokenValidator.verify(incoming, expected);

    // verify() phải bảo đảm chữ ký, issuer, audience, time,
    // events, sid/sub và không có nonce theo spec.
    List<SessionReference> sessions =
        sessionRegistry.findMatchingSessions(
            event.issuer(),
            expected.getClientId(),
            event.subject(),
            event.sessionId());

    // Chỉ kết thúc sessions đã được correlate hợp lệ.
    sessionTerminator.terminate(sessions);
}
~~~

`SignedJwt`, `VerifiedLogoutToken`, `SessionReference`, `strictOidcLogoutTokenValidator`, `sessionRegistry` và `sessionTerminator` trong đoạn này là **khái niệm ứng dụng minh họa**, không phải API Spring Security cần copy vào project.

**Ưu tiên API `oidcLogout().backChannel(...)` của Spring Security** để có validation và session coordination thay vì tự xây endpoint.

## 9. `sid` và `sub` xác định phiên nào phải kết thúc?

### 9.1. Logout Token có `sid`

Giả sử Alice đã đăng nhập Portal từ hai trình duyệt:

| Browser | OP issuer | OP `sid` | RP local `JSESSIONID` |
| --- | --- | --- | --- |
| Laptop | company OP | `op-laptop-7a` | `rp-portal-a11` |
| Điện thoại | company OP | `op-phone-9b` | `rp-portal-b22` |

OP phát Logout Token:

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "aud": "portal-web-client",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-laptop-only",
  "sid": "op-laptop-7a",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

RP tìm session có **issuer + audience + sid** tương ứng, rồi invalidate `rp-portal-a11`. Session ở điện thoại không tự bị xóa nếu khác `sid`.

### 9.2. Logout Token không có `sid` nhưng có `sub`

Ví dụ:

~~~json
{
  "iss": "https://id.example.net/realms/company",
  "aud": "portal-web-client",
  "sub": "user-123",
  "iat": 1790000000,
  "exp": 1790000120,
  "jti": "logout-user-123-all",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Theo ý nghĩa chuẩn, khi **không có `sid`**, OP yêu cầu RP logout **tất cả phiên của end-user đó** thuộc issuer/client tương ứng. Vì vậy laptop và điện thoại có thể đều bị invalidate.

### 9.3. Nếu có cả `sid` và `sub`

RP cần ràng buộc session với **đúng issuer, client, sid và identity** thay vì dùng một `sid` không được kiểm tra với user. Việc match sai có thể gây logout nhầm người dùng.

Với Spring Security, logic registry dùng `sid` để chọn phiên khi được cung cấp và `sub` khi không có `sid`; chú ý đến ánh xạ provider session đã ghi khi login.

### 9.4. Bảng phạm vi tác động

| Logout Token | Diễn giải | Phạm vi ở RP |
| --- | --- | --- |
| Chỉ `sid` | Logout OP session được chỉ ra | Các local sessions match session ID đó trong đúng issuer/client |
| Chỉ `sub` | Logout end-user | Các local sessions của subject đó trong đúng issuer/client |
| Cả `sub` và `sid` | Xác định cả user và session | Không được vượt phạm vi match hợp lệ |
| Không có cả hai | Không hợp lệ | Reject |
| `sub` của issuer khác | Không thuộc RP session này | Reject hoặc không match theo validation/policy |

**Không so sánh `sid` với cookie session ID từ browser của một request hoàn toàn khác**. Back-channel đến từ OP server, không có browser session gốc để so sánh.

## 10. OIDC Session Registry: cây cầu giữa OP và local session

Khi login thành công, RP cần ghi dữ liệu liên hệ:

~~~text
Local RP Session:
  id = rp-session-a11
  user = Alice
  registration = company

OIDC Login:
  issuer = https://id.example.net/realms/company
  clientId = portal-web-client
  sub = user-123
  sid = op-laptop-7a

Registry:
  (issuer, clientId, sub, sid) -> rp-session-a11
~~~

### 10.1. Vì sao không lấy session theo email?

Email có thể thay đổi, không phải lúc nào được xác minh, có thể trùng giữa issuers hoặc được tái sử dụng. Dùng email để logout tất cả sessions rất dễ tạo nhầm lẫn multi-tenant.

Để liên kết danh tính OIDC, thường ưu tiên **issuer + subject** đã được xác minh. Nếu OP phát `sid`, dùng **issuer + audience/client + sid** cho session-specific matching.

### 10.2. Session registry không thay session store

Hai loại dữ liệu khác nhau:

~~~text
OIDC Session Registry:
  OP sid/sub/iss/aud -> local session id

HttpSession/WebSession Store:
  local session id -> SecurityContext, attributes, CSRF data...
~~~

Registry biết **phiên nào cần logout**. Session store cho phép framework **invalidate phiên đó**. Trong Servlet, `HttpSession` không phải một đối tượng có thể tự truy xuất ngẫu nhiên chỉ bằng session ID từ mọi chỗ; Spring Security có cơ chế gọi logout nội bộ trong đúng context phiên để thực hiện local logout handlers.

### 10.3. Hết phiên tự nhiên cũng phải xóa mapping

Nếu local session timeout, user local logout hoặc admin invalidate session, registry cần được cập nhật. Nếu không, mapping cũ sẽ tích tụ và có thể gây sai hành vi hoặc dùng nhiều memory.

Trong Servlet, Spring Security đề xuất đăng ký `HttpSessionEventPublisher` để xử lý sự kiện invalidation/destroy và loại bỏ `OidcSessionInformation` không còn dùng.

### 10.4. Khi chạy nhiều instances

~~~text
                 Load balancer
                  /         \
              Node A       Node B
            Registry A    Registry B
                 \         /
                Shared Session Store
~~~

Nếu Registry A và Registry B chỉ nằm trong memory, OP gửi logout đến Node B có thể không tìm thấy session được Node A ghi. **Dùng shared HttpSession/Redis thôi chưa đủ** nếu OIDC Session Registry vẫn phân tán riêng không nhất quán.

Trong môi trường cluster, xem xét **custom `OidcSessionRegistry`** (Servlet) hoặc **`ReactiveOidcSessionRegistry`** (Reactive), lưu mapping vào storage phù hợp và kiểm soát concurrency.

## 11. Cấu hình Spring Security Servlet Back-Channel Logout

### 11.1. Dependency minh họa

Với Spring Boot 3.x / Spring Security 6.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Spring Boot 4.x có starter/module organization khác; dùng dependency tương ứng theo BOM của dự án. Để dùng `oidcLogout().backChannel(...)`, phải dùng phiên bản Spring Security **thực sự cung cấp API này**.

### 11.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-oidc:
            issuer-uri: https://id.example.net/realms/company
~~~

`company` là **registrationId**; `company-oidc` là **provider config ID**; `OIDC_CLIENT_ID` là **audience** mà OP cần đưa vào Logout Token dành cho RP.

Ứng dụng phải cấu hình URI back-channel chính xác trong **OP registration**:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

**Chỉ cấu hình OIDC Login ở Spring Boot không tự khiến OP gửi Back-Channel Logout**. OP phải hỗ trợ và được đăng ký endpoint.

### 11.3. SecurityFilterChain Servlet

Theo tài liệu Spring Security Servlet, có thể cấu hình:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.OidcBackChannelLogoutHandler;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcBackChannelSecurityConfig {

    @Bean
    OidcBackChannelLogoutHandler oidcLogoutHandler() {
        return new OidcBackChannelLogoutHandler();
    }

    @Bean
    HttpSessionEventPublisher sessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Phiên bản/API:** đoạn minh họa theo `oidcLogout().backChannel(...)` và `OidcBackChannelLogoutHandler` trong Spring Security Servlet documentation. Package/import của các class có thể thay đổi giữa major versions; trong dự án thực, dùng Javadoc/IDE dependency đúng phiên bản. Ví dụ không tạo controller thủ công cho logout endpoint.

`oidcLogout` cần `oauth2Login` được cấu hình. Đây là **thành phần OAuth2/OIDC Login**, không phải `logoutSuccessHandler` của RP-Initiated Logout.

### 11.4. Endpoint mặc định

Với registration `company`, Spring Security triển khai endpoint:

~~~text
POST /logout/connect/back-channel/company
~~~

OP gọi endpoint và gửi form `logout_token`. Filter/handler Spring Security xử lý verification và session termination.

Nếu ứng dụng có nhiều `SecurityFilterChain`, phải đảm bảo chain có `oidcLogout().backChannel(...)` match đúng endpoint. Đừng cho một chain API khác chặn request trước, khiến OP nhận redirect đến login page hoặc 401 không phù hợp.

### 11.5. Vì sao cần HttpSessionEventPublisher?

Khi `HttpSession#invalidate()` xảy ra do logout hoặc timeout, Spring Security cần nhận lifecycle events để loại bỏ các `OidcSessionInformation` records không còn liên quan.

Nếu registry giữ mapping đã hết hạn, có thể xảy ra memory leak, tìm nhầm phiên hoặc gây thêm công việc khi nhận back-channel events.

## 12. Vấn đề cookie `JSESSIONID` và Spring Session `SESSION`

### 12.1. Cookie là tên phụ thuộc session configuration

Trong servlet container, local session thường dùng cookie:

~~~http
Cookie: JSESSIONID=rp-session-opaque
~~~

Khi dùng Spring Session, cookie name mặc định thường là:

~~~http
Cookie: SESSION=rp-session-opaque
~~~

Tài liệu Spring Security Back-Channel Logout nhấn mạnh cơ chế correlation của handler mặc định dùng `JSESSIONID`, và cần cấu hình khi deployment dùng cookie name khác. **Đừng mặc định local session cookie trong hạ tầng mình là JSESSIONID chỉ vì ứng dụng dùng Servlet**.

### 12.2. Cấu hình handler tương ứng cookie name

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.authentication.logout.OidcBackChannelLogoutHandler;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionRegistry;

@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler(
        OidcSessionRegistry registry) {

    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(registry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Đoạn này là **phương án thay thế bean no-arg** ở phần 11, không khai báo cả hai để Spring chọn tùy ý. Kiểm tra package của `OidcSessionRegistry`/handler theo version Spring Security. `"SESSION"` chỉ phù hợp nếu cookie thực sự được cấu hình tên đó.

### 12.3. Vì sao handler cần biết cookie name?

Spring Security phải đưa request logout nội bộ vào **đúng local session** tương ứng với `OidcSessionInformation`. Nếu internal logout request dùng sai cookie name, session resolver không nhận ra session cần invalidate.

Hậu quả: OP nhận response nhưng RP session có thể không bị kết thúc như mong muốn. Vì vậy hãy kiểm thử **browser dùng session cookie thật** và **OP back-channel event thật** trong topology triển khai, không chỉ unit test parser JWT.

### 12.4. Không gửi `JSESSIONID` của browser cho OP

Trong back-channel, OP dùng Logout Token dựa trên `sid`/`sub`, không cần cookie của RP user browser. Không chuyển local cookie value vào Logout Token, provider URL hoặc logs để “giúp OP xác định phiên”.

## 13. Tùy biến OidcSessionRegistry trên Servlet

Trong một instance đơn, in-memory registry có thể đáp ứng demo. Với nhiều instances, đăng ký một implementation lưu mapping chung.

### 13.1. Hợp đồng ý tưởng

`OidcSessionRegistry` của Spring Security cần hỗ trợ:

- `saveSessionInformation(OidcSessionInformation info)`.
- `removeSessionInformation(String clientSessionId)`.
- `removeSessionInformation(OidcLogoutToken token)` để tìm/xóa các sessions match logout event.

Ví dụ **pseudocode cấu trúc**, không phải class đã chạy sẵn:

~~~java
import org.springframework.security.oauth2.client.oidc.session.OidcLogoutToken;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionInformation;
import org.springframework.security.oauth2.client.oidc.session.OidcSessionRegistry;

public final class DatabaseOidcSessionRegistry
        implements OidcSessionRegistry {

    private final OidcSessionMappingRepository repository;

    public DatabaseOidcSessionRegistry(
            OidcSessionMappingRepository repository) {
        this.repository = repository;
    }

    @Override
    public void saveSessionInformation(OidcSessionInformation info) {
        repository.save(info);
    }

    @Override
    public OidcSessionInformation removeSessionInformation(
            String clientSessionId) {
        return repository.removeByClientSessionId(clientSessionId);
    }

    @Override
    public Iterable<OidcSessionInformation> removeSessionInformation(
            OidcLogoutToken token) {
        if (token.getSessionId() != null) {
            return repository.removeByIssuerAudienceAndSid(token);
        }
        return repository.removeByIssuerAudienceAndSubject(token);
    }
}
~~~

`OidcSessionMappingRepository` và các phương thức `removeByIssuerAudienceAndSid(...)` / `removeByIssuerAudienceAndSubject(...)` là **interface/application methods phải tự cài đặt**. Spring Security docs chỉ minh họa ý tưởng tương tự; không có một JPA repository tương ứng được tạo tự động.

### 13.2. Quy tắc truy vấn registry

Một schema logic:

~~~text
oidc_session_mapping
  local_session_id
  issuer
  client_id / audience
  subject
  op_session_id (sid, nullable)
  created_at
  expires_at
  version
~~~

Truy vấn với `sid`:

~~~sql
-- SQL MẪU: cần index/transaction và parameter binding.
SELECT local_session_id
FROM oidc_session_mapping
WHERE issuer = :issuer
  AND client_id = :audience
  AND op_session_id = :sid;
~~~

Truy vấn khi **không có `sid`**:

~~~sql
SELECT local_session_id
FROM oidc_session_mapping
WHERE issuer = :issuer
  AND client_id = :audience
  AND subject = :sub;
~~~

Không viết:

~~~sql
-- PHẢN VÍ DỤ: bỏ issuer/client gây logout chéo.
DELETE FROM oidc_session_mapping WHERE subject = :sub;
~~~

vì `sub` chỉ ổn định trong scope issuer và có thể tồn tại ở nhiều registrations khác nhau.

### 13.3. Tính nhất quán

Khi OP gửi logout vào nhiều nodes, một registry chung phải hỗ trợ:

- Truy vấn nhanh theo issuer/audience/sid hoặc issuer/audience/sub.
- Cập nhật/xóa có tính idempotent.
- Không cho session IDs bị gán lại tùy ý.
- Cleanup khi local session hết hạn.
- Atomic/transactional behavior phù hợp.
- Kiểm tra quyền truy cập dữ liệu ánh xạ session.
- Không lộ raw `sid` / session ID trên log, dashboard công khai.

Trong distributed session store, chỉ xóa bản ghi mapping **chưa chắc đã invalidate local session**. Tầng session termination vẫn phải thực hiện chính sách logout framework đã thiết kế.

## 14. Spring Security Reactive/WebFlux Back-Channel Logout

OIDC Back-Channel Logout cũng được hỗ trợ trên Reactive stack ở các phiên bản Spring Security phù hợp.

### 14.1. Phân biệt class Servlet và Reactive

| Chức năng | Servlet | Reactive |
| --- | --- | --- |
| Security DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Back-channel handler | `OidcBackChannelLogoutHandler` | `OidcBackChannelServerLogoutHandler` |
| Registry | `OidcSessionRegistry` | `ReactiveOidcSessionRegistry` |
| Repository behavior | Đồng bộ | `Mono` / `Flux` |
| Session cookie mặc định | Thường `JSESSIONID` | Tùy WebFlux/Spring Session, thường `SESSION` |

**Không trộn handler Servlet vào Reactive `SecurityWebFilterChain`** hoặc dùng Reactive registry interface cho Servlet DAO nếu không có adapter phù hợp.

### 14.2. Reactive dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 14.3. SecurityWebFilterChain minh họa

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.OidcBackChannelServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutConfig {

    @Bean
    OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
        return new OidcBackChannelServerLogoutHandler();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là ví dụ theo Reactive OIDC Logout documentation ở phiên bản có API `oidcLogout`. Đừng thêm `HttpSessionEventPublisher` của Servlet chỉ vì thấy trong ví dụ Spring MVC; reactive session lifecycle được quản lý bởi các thành phần khác.

### 14.4. Reactive handler với cookie name phù hợp

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.oidc.session.ReactiveOidcSessionRegistry;
import org.springframework.security.web.server.authentication.logout.OidcBackChannelServerLogoutHandler;

@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler(
        ReactiveOidcSessionRegistry sessionRegistry) {

    OidcBackChannelServerLogoutHandler handler =
        new OidcBackChannelServerLogoutHandler(sessionRegistry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Đây là **bean thay thế** bean no-arg trong ví dụ reactive trên. Chỉ dùng `SESSION` nếu môi trường WebFlux/Spring Session thực sự phát cookie đó; không mặc định áp dụng cho mọi phiên bản.

### 14.5. Registry Reactive phải non-blocking

Một implementation `ReactiveOidcSessionRegistry` có thể lưu mapping vào R2DBC/Reactive Redis hoặc backend tương thích:

~~~text
saveSessionInformation(info) -> Mono<Void>
removeSessionInformation(clientSessionId) -> Mono<OidcSessionInformation>
removeSessionInformation(logoutToken) -> Flux<OidcSessionInformation>
~~~

Đây là **mô tả contract**, không phải lời khuyên tự gọi `subscribe()`. Implementations nên trả reactive pipeline để framework quản lý transaction/completion; không `block()` trên event-loop để gọi một JDBC repository đồng bộ.

### 14.6. Đừng nhầm Reactive Back-Channel Logout với WebClient OAuth2 filter

`ServerOAuth2AuthorizedClientExchangeFilterFunction` giúp **WebClient gửi Access Token đến API**.

`OidcBackChannelServerLogoutHandler` giúp **RP nhận Logout Token từ OP và kết thúc local session**.

Hai thành phần có thể cùng xuất hiện trong một ứng dụng WebFlux nhưng giải quyết **hai hướng HTTP và hai loại token khác nhau**.

## 15. Local session termination trong Servlet diễn ra thế nào?

Spring Security lưu thông tin phiên trong `OidcSessionRegistry`. Khi OP gửi Logout Token hợp lệ, handler cần chấm dứt đúng `HttpSession`.

Trong Servlet API, không có API portable tổng quát cho phép lấy arbitrary `HttpSession` bằng ID và tự gọi `invalidate()` từ bên ngoài request context. Spring Security giải quyết bằng cơ chế **gọi logout nội bộ tương ứng với session**:

~~~text
Back-channel event đã verify
    |
    v
OidcSessionRegistry
    |
    +-- localSessionId = A
    +-- localSessionId = B
    |
    v
Spring Security internal logout operations
    |
    +-- Tái tạo đúng session context
    +-- Chạy LogoutHandlers tương ứng
    +-- Invalidate HttpSession
    +-- Dọn mapping
~~~

### 15.1. Vai trò của CSRF và internal logout

Local browser logout endpoint trong Spring Security thường có CSRF protection. OP back-channel request **không có CSRF token browser**, vì nó không phải một thao tác bắt đầu từ browser session.

Spring Security có cơ chế handler tương ứng cho loại request được xác minh bằng **signed Logout Token**, đồng thời cần một đường logout nội bộ hoạt động đúng với session.

**Không giải quyết bằng `csrf.disable()` cho toàn ứng dụng.** Việc tắt CSRF toàn cục có thể tạo lỗ hổng cho những browser requests khác. Dùng back-channel support của framework và chỉ tùy biến đúng endpoint/policy khi thật sự cần.

### 15.2. Không tự gọi controller local `/logout` bằng một request vô danh

Một thao tác tự viết như:

~~~text
OP POST -> /backchannel
         -> HTTP client gọi /logout?sid=...
~~~

không có cơ sở để local `/logout` biết browser session nào cần invalidate nếu chưa có mapping/validated context. Dùng `OidcBackChannelLogoutHandler` / session registry thay vì tự xây logout proxy với query parameters.

## 16. Back-Channel Logout có revoke OAuth2 tokens không?

Đây là một nhầm lẫn nghiêm trọng:

**Kết thúc RP session ≠ thu hồi Access Token / Refresh Token đã phát hành.**

Ví dụ:

~~~text
RP HttpSession: INVALIDATED

Access Token đã cấp:
  exp còn 10 phút
  Resource Server có thể vẫn chấp nhận

Refresh Token đã lưu:
  có thể còn trong persistent authorized client service
  phải xét policy revoke/cleanup riêng
~~~

### 16.1. Chuẩn nói gì về Refresh Token?

OpenID Connect Back-Channel Logout 1.0 khuyến nghị:

- Refresh Tokens **không có quyền `offline_access`** gắn với session đang logout **nên được thu hồi**.
- Refresh Tokens được cấp với quyền `offline_access` **thường không nên bị thu hồi tự động** chỉ vì logout session, vì đây có thể là quyền offline được người dùng cấp riêng.

Đây là hướng dẫn protocol; Authorization Server và client implementation thực tế có thể có behavior và chính sách khác. Đừng tự cho rằng Spring Security xóa toàn bộ `OAuth2AuthorizedClient` persistent store và đã gọi revocation endpoint sau mỗi back-channel request.

### 16.2. Xóa local authorized client khác revoke ở OP

| Hành động | Hiệu lực |
| --- | --- |
| `HttpSession.invalidate()` | Kết thúc local browser session |
| Xóa entry trong `OAuth2AuthorizedClientService` | RP không còn tải token từ entry đó |
| Gọi token revocation endpoint theo RFC 7009 | Yêu cầu Authorization Server thu hồi token nếu provider hỗ trợ |
| Invalidate OP SSO session | OP không tiếp tục xem browser đã đăng nhập theo session đó |
| Resource Server từ chối token | Phụ thuộc expiration, introspection, revocation hoặc policy API |

Không dùng câu “Back-Channel Logout đã thu hồi mọi JWT Access Token” làm cam kết bảo mật. Một self-contained JWT đã phát hành có thể vẫn được Resource Server chấp nhận cho đến khi hết hạn, trừ khi có revocation strategy/token introspection/session binding bổ sung.

### 16.3. Connection và offline access

Ứng dụng có thể có một “kết nối Google Calendar” hoặc “kết nối hệ thống ERP” với Refresh Token offline trong database, độc lập với browser session. Khi nhận back-channel logout, cần quyết định theo product policy:

- Chỉ chấm dứt browser session.
- Có xóa delegated authorized client gắn session không?
- Offline access có tiếp tục hợp lệ không?
- Nếu user bấm “Disconnect account”, có revoke token không?

**OIDC logout và disconnect OAuth2 integration là hai thao tác khác nhau**. Không thu hồi offline access không phù hợp chỉ vì một OP session đã kết thúc, nhưng cũng không bỏ qua revocation khi policy yêu cầu.

## 17. Multi-provider và multi-tenant: không logout nhầm khách hàng

Giả sử RP hỗ trợ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: portal-company-client
            authorization-grant-type: authorization_code
          partner:
            provider: partner-oidc
            client-id: portal-partner-client
            authorization-grant-type: authorization_code
        provider:
          company-oidc:
            issuer-uri: https://id.company.example.net
          partner-oidc:
            issuer-uri: https://login.partner.example.org
~~~

Đây là **YAML minh họa nguyên tắc mapping**, không phải cấu hình chạy độc lập hoàn chỉnh: một OIDC confidential client thực tế còn cần client secret/method, redirect URI và scopes, hoặc provider metadata tương ứng.

Hai logout endpoints:

~~~text
/logout/connect/back-channel/company
/logout/connect/back-channel/partner
~~~

### 17.1. Kiểm tra audience theo client ID, không theo registrationId

Logout Token gửi vào:

~~~text
/logout/connect/back-channel/company
~~~

phải chứa `aud` dành cho **portal-company-client**, không phải chỉ một chuỗi `company` trùng đường dẫn.

Một attacker không được phép gửi token ký hợp lệ cho partner registration vào company endpoint để xóa sessions của company.

### 17.2. Issuer tách trust boundary

Ngay cả khi cả hai OP đều có user `sub="123"`:

~~~text
company issuer + subject 123 != partner issuer + subject 123
~~~

Registry phải dùng issuer đã validation. Không dùng email hoặc tên đăng nhập làm khóa logout toàn cục.

### 17.3. Một OP nhiều client IDs

Một công ty có Portal và Billing cùng tin vào một OP nhưng đăng ký bằng **hai client IDs riêng**. Logout Token của Portal không được tự dùng để kết thúc Billing sessions nếu OP chưa gửi event dành cho Billing hoặc hệ thống không có chính sách logout tổng thể hợp lệ.

### 17.4. Tenant từ URL không được quyết định key trust tùy ý

Không nên xây:

~~~text
POST /backchannel/{tenantId}
  -> lấy jwks_uri từ query của caller
  -> parse JWT và xóa session
~~~

Nếu `jwks_uri` hoặc issuer do request quyết định không có allowlist, attacker có thể cung cấp key của chính mình rồi ký JWT giả. Trust material phải xuất phát từ **ClientRegistration/issuer đã đăng ký**, không từ JWT header hoặc query string chưa xác minh.

## 18. Replay, thời hạn và chống DoS

### 18.1. `jti` hỗ trợ chống replay

Mỗi Logout Token có `jti` duy nhất. Nếu hạ tầng muốn phát hiện sự kiện lặp lại, có thể lưu:

~~~text
key = hash(issuer | audience | jti)
ttl = khoảng thời gian hợp lệ + clock skew theo policy
~~~

`jti` store cần TTL, tránh tăng không giới hạn. Không log nguyên JWT hoặc dùng raw `jti` của người dùng làm public metric label.

Theo spec, kiểm tra replay `jti` thuộc nhóm kiểm tra có thể thực hiện thêm; không nên diễn giải thành yêu cầu mọi Spring Security deployment mặc định có distributed replay cache.

### 18.2. Duplicate event và idempotency

Nếu OP retry do timeout trong khi RP đã invalidate session, RP không nên xóa nhầm một session khác hoặc tạo lỗi vận hành nghiêm trọng.

**Một sự kiện logout hợp lệ lặp lại khi local session đã kết thúc có thể được xử lý thành công** theo semantics idempotent. Nếu có replay cache, phân biệt duplicate event lành tính với replay đáng ngờ trong monitoring mà không thay đổi session identity.

### 18.3. Short-lived Logout Token

Chuẩn khuyến nghị Logout Tokens có expiration ngắn, thường tối đa vài phút (khuyến nghị tốt nhất khoảng hai phút trong security considerations), để giảm thời gian attacker có thể sử dụng một token đã bị bắt.

RP phải kiểm tra `exp` và `iat`, có clock skew hạn chế, **không chấp nhận vô hạn** vì “OP clock đôi khi lệch”.

### 18.4. Rate limiting

Endpoint back-channel có thể được gọi qua Internet, nên cần:

- Request body size limits.
- HTTP method và Content-Type đúng.
- Rate limiting phù hợp trust network và retry policy OP.
- TLS, WAF rules thận trọng không chặn OP hợp lệ.
- Giới hạn JWT parsing/validation workload.
- Metrics từ chối signature/issuer/audience sai, không log token.

Không phụ thuộc IP allowlist **thay cho** validation Logout Token. IP có thể thay đổi hoặc đi qua proxy; chữ ký và claim validation vẫn là bắt buộc.

## 19. Reverse proxy, base URL và HTTP ingress

Một deployment thực tế:

~~~text
https://portal.example.net
    |
    v
Load balancer (TLS termination)
    |
    v
Spring Boot instance ở private port 8080
~~~

### 19.1. OP phải dùng public HTTPS URL

RP đăng ký:

~~~text
https://portal.example.net/logout/connect/back-channel/company
~~~

**Không** đăng ký `http://localhost:8080/...` với OP cloud trừ khi OP ở cùng environment đặc biệt cho phép.

### 19.2. Proxy rewrite có thể làm endpoint không match

Nếu proxy thêm prefix:

~~~text
Public: /portal/logout/connect/back-channel/company
Internal: /logout/connect/back-channel/company
~~~

hãy kiểm tra OP đăng ký đúng public URI, proxy chuyển tiếp đúng path và SecurityFilterChain vẫn match endpoint nội bộ.

### 19.3. Không redirect OP POST đến browser login

Vì OP là server caller không có browser session, response:

~~~http
HTTP/1.1 302 Found
Location: /oauth2/authorization/company
~~~

thường chỉ ra rằng endpoint bị security matcher chặn hoặc cấu hình back-channel chưa hiệu lực. Điều này **không phải** một lần logout thành công. Sửa routing/filter-chain, không cố cho OP đi qua browser authorization flow.

## 20. Observability: theo dõi event mà không ghi Logout Token

Một event log an toàn có thể chứa:

~~~text
event=oidc_backchannel_logout
issuer_alias=company-oidc
registration_id=company
outcome=success
match_mode=sid
matched_sessions=1
correlation_id=internal-evt-44ef
~~~

Đây là **format minh họa**, không phải log tự động của Spring Security. Không ghi:

- Raw `logout_token` hoặc JWT signature.
- Local session ID/cookie `JSESSIONID` hoặc `SESSION`.
- Raw `sid`/`sub` nếu không có lý do và chính sách privacy.
- Client Secret, ID Token, Access Token, Refresh Token.
- Toàn bộ HTTP body hoặc request headers không được redaction.

### 20.1. Metrics có ích

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Event hợp lệ nhận được theo issuer/registration | OP đang phát sự kiện |
| Tỷ lệ reject JWT signature/issuer/aud | Có thể là misconfiguration hoặc request độc hại |
| Số event hợp lệ nhưng không match session | Session đã hết hạn, registry mất mapping hoặc sự kiện đến chậm |
| Tỷ lệ session invalidation thành công | Tính tin cậy của back-channel integration |
| Lỗi database/session store | Logout có thể không hoàn tất trong cluster |
| Node lệch registry khi scale-out | Cần shared registry |
| HTTP 302/401/403 tại back-channel endpoint | Có khả năng route/CSRF/security chain sai |
| Latency xử lý event | Giám sát nguy cơ OP timeout/retry |

**Không dùng session IDs hoặc jti ngẫu nhiên làm metric labels** ở hệ thống có cardinality lớn. Dùng buckets/classes và correlation logs theo quyền truy cập.

### 20.2. Dữ liệu audit nhạy cảm

Back-channel logout có thể liên quan tới user termination, account lock hoặc admin action. Audit log cần đủ để điều tra nhưng vẫn phải tuân theo chính sách dữ liệu cá nhân/retention. Một event được gửi từ OP không chứng minh user đã trực tiếp nhấn nút “Logout”; có thể là admin hoặc chính sách bảo mật.

## 21. Ma trận kiểm thử giao thức

**Không dùng Logout Token được tạo bằng cách chỉ Base64url JSON và bỏ chữ ký** để mô phỏng một trường hợp thành công. Test thành công phải dùng JWT được ký bằng **test issuer key** mà client tin cậy trong môi trường kiểm thử, có issuer/audience đúng.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Logout Token ký đúng, `sid` khớp một session | Chỉ session đó bị invalidate |
| Logout Token ký đúng, chỉ có `sub` | Tất cả local sessions phù hợp issuer/client/sub bị kết thúc |
| Logout Token có cả `sub` và `sid` hợp lệ | Chỉ kết thúc session đúng cả identity/session |
| Token thiếu cả `sub` và `sid` | Reject 400 |
| Token có `nonce` | Reject |
| Token thiếu `events` logout event | Reject |
| Token `iss` sai | Reject, không xóa sessions |
| Token `aud` của client khác | Reject, không xóa sessions của client khác |
| Chữ ký sai hoặc `alg=none` | Reject |
| `exp` hết hạn hoặc `iat` bất hợp lý | Reject theo validation policy |
| Token sai `jti` format/thiếu `jti` | Reject |
| Token hợp lệ nhưng local session đã hết hạn | Idempotent success/không xóa session khác |
| OP gửi lại event sau timeout | Không tạo tác dụng phụ sai; replay handling theo policy |
| Local session `JSESSIONID` / Spring Session `SESSION` | Handler dùng đúng cookie name để invalidate |
| User có hai `sid` trên hai thiết bị | Logout một `sid` không xóa thiết bị còn lại |
| Cùng `sub` ở hai issuers | Không logout nhầm issuer |
| Cùng OP nhưng hai client IDs | Không logout nhầm client |
| Hai pods dùng registry memory độc lập | Test phát hiện mapping thiếu |
| Shared registry/session store | Event đến node B vẫn invalidate session node A |
| OP unreachable hoặc request timeout | Có cảnh báo và chính sách retry |
| API không hỗ trợ OIDC login | Không bật nhầm `oidcLogout` trên OAuth2 Client Credentials app |
| Spring Session mất mapping | Không báo hoàn tất sai khi không invalidate được theo policy |

### 21.1. Unit test khác integration test

Unit test có thể kiểm tra một mapping repository:

~~~text
findByIssuerAudienceSid(iss, aud, sid)
  -> đúng các local session IDs

findByIssuerAudienceSub(iss, aud, sub)
  -> đúng các sessions của end-user
~~~

Nhưng unit test mapping **không chứng minh** JWT signature validation, Spring Security filter wiring hoặc actual `HttpSession.invalidate()`.

Integration test cần chạy luồng OIDC Login (hoặc tạo trạng thái session registry đúng contract) rồi gửi HTTP POST ký bằng test issuer key, sau đó kiểm tra request có cookie session cũ không còn authenticated.

### 21.2. Test HTTP invalid request an toàn

Ví dụ gửi một **token giả không hợp lệ** để xác nhận endpoint không chấp nhận:

~~~bash
curl -i -X POST \
  "https://portal.example.net/logout/connect/back-channel/company" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "logout_token=INVALID_TEST_TOKEN"
~~~

**Chỉ chạy trên test/staging được phép**, không dùng production Logout Token thật trong shell history. Kết quả mong đợi là request **bị từ chối** mà không logout bất kỳ user nào. HTTP status cụ thể phụ thuộc filter chain/handler khi request chưa được parse thành JWT; để xác nhận giao thức đầy đủ, dùng test issuer ký JWT hợp lệ.

### 21.3. Kiểm thử thực tế logout từ OP

Một bài test end-to-end tốt:

1. Browser A login vào RP qua test OP, lưu cookie A.
2. Browser B login cùng user bằng OP session khác, lưu cookie B.
3. RP ghi mapping `sidA -> sessionA` và `sidB -> sessionB`.
4. OP phát Logout Token chỉ chứa `sidA`.
5. RP trả HTTP success theo contract.
6. Browser A request protected route và bị yêu cầu authentication lại.
7. Browser B vẫn authenticated nếu OP session B chưa bị logout.
8. OP phát token `sub-only` cho user, RP kết thúc các sessions còn lại phù hợp.
9. Đảm bảo sessions của issuer/client khác không bị xóa.

### 21.4. Kiểm tra token lifecycle ngoài session

Trong integration test, cần phân biệt:

~~~text
Browser session invalidated        -> expected
Stored Refresh Token still exists  -> có thể, tùy policy
Resource Server accepts Access Token -> có thể tới expiration
~~~

Kiểm tra explicitly những gì sản phẩm cam kết về revoke/cleanup; đừng dùng “đã redirect về login” để khẳng định mọi OAuth2 credentials bị vô hiệu.

## 22. Những sai lầm triển khai phổ biến

### 22.1. Dùng ID Token thay Logout Token

ID Token của user đã login không phải thông báo logout do OP gửi. Một JWT có `iss` và `sub` không đủ; phải có chữ ký và claims/sự kiện Logout Token đúng chuẩn.

### 22.2. Nhận `sid` rồi xóa HttpSession theo cùng giá trị

`sid` là **OP session ID**, `JSESSIONID`/`SESSION` là **RP session ID**. Phải tra registry đã ghi lúc login.

### 22.3. Chỉ dùng `sub` để logout không kiểm tra issuer/client

Một OP khác có thể có cùng `sub`. Bỏ `iss` hoặc `aud` dễ xóa nhầm toàn bộ phiên của người dùng khác/tenant khác.

### 22.4. Tự decode JWT rồi tin payload

Base64url decoding chỉ lấy JSON, **không xác minh signature**. Không gọi session invalidation trước khi verified Logout Token.

### 22.5. Không kiểm tra `events` và `nonce`

Đây là cách tạo lỗ hổng **cross-JWT confusion**. Logout Token phải có đúng event và không được chứa nonce.

### 22.6. Mặc định Logout Token `aud` bằng `registrationId`

Trong Spring, `registrationId="company"` có thể khác `clientId="portal-web-client"`. JWT `aud` phải phù hợp client ID/trust context đúng.

### 22.7. Tắt CSRF toàn ứng dụng để OP gửi POST

Back-channel có quy trình nhận request riêng. Tắt CSRF của mọi browser endpoints có thể tạo lỗ hổng không liên quan; dùng Spring Security OIDC Logout support và cấu hình chính xác.

### 22.8. Không cấu hình URI trong OP console

Spring Security endpoint có chạy nhưng OP không biết phải gọi đến đâu. Cần đăng ký `backchannel_logout_uri` thật, không chỉ thêm `oidcLogout()` trong code.

### 22.9. OP gọi localhost hoặc private IP không reach được

OP cần network route đến endpoint RP. Dùng public/trusted ingress phù hợp và TLS; không cho rằng browser truy cập được nghĩa là OP server cũng truy cập được.

### 22.10. Dùng cookie name sai

RP dùng Spring Session `SESSION` nhưng handler dùng `JSESSIONID`, dẫn đến không xác định được local session khi internal logout. Dùng `setSessionCookieName(...)` theo deployment.

### 22.11. Chia session store nhưng không chia OIDC registry

Redis-backed sessions không tự chia sẻ in-memory `OidcSessionRegistry` giữa pods. Phải thiết kế registry cluster-safe hoặc routing/affinity tương thích và kiểm thử.

### 22.12. Coi logout đồng nghĩa revoke toàn bộ OAuth2 tokens

RP session invalidation không mặc nhiên làm JWT Access Token ngừng hoạt động ở API. Cần TTL, revocation/introspection và chính sách Refresh Token riêng.

### 22.13. Log Logout Token để debug

JWT có thể chứa `sub`/`sid`/issuer, chữ ký và data nhạy cảm. Không log raw token, query/body hoặc session cookie.

### 22.14. Cho browser gọi endpoint với query `sid=...`

Đây không phải Back-Channel Logout hợp lệ; attacker có thể DoS/logout người khác nếu thiếu xác minh chữ ký. Endpoint phải nhận HTTP POST với `logout_token` được verify.

### 22.15. Không phân biệt OP session với offline OAuth2 connection

`offline_access` có vòng đời khác browser session. Không tự xóa tất cả offline Refresh Tokens của user chỉ vì back-channel event, nếu sản phẩm/OP policy không yêu cầu.

### 22.16. Trả 302 tới OP thay vì phản hồi server-to-server

OP là caller server; 302 sang login page cho thấy endpoint bị security filter chặn hoặc routing sai. Back-channel endpoint cần xử lý JWT và trả HTTP success/failure theo protocol.

## 23. Troubleshooting theo dấu hiệu

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| OP không gửi POST | Chưa bật back-channel ở OP hoặc chưa đăng ký URI | Kiểm tra Discovery và client registration |
| OP gửi 404 | Endpoint path/registrationId/proxy rewrite sai | Kiểm tra `/logout/connect/back-channel/{registrationId}` |
| OP nhận 302 tới login | Chưa cấu hình `oidcLogout` hoặc sai SecurityFilterChain | Kiểm tra filter chain matching |
| OP nhận 403 | CSRF/method/security chain chặn | Dùng handler/back-channel support, không tắt CSRF toàn cục |
| OP nhận 400 | JWT malformed, signature/iss/aud/claims sai | Xem error category an toàn và provider contract |
| JWT hợp lệ nhưng RP vẫn authenticated | Sai registry, cookie name, session store hoặc internal logout | Kiểm tra mapping và session lifecycle |
| Logout một thiết bị làm logout mọi thiết bị | OP gửi `sub-only` hoặc mapping sid sai | Kiểm tra `sid` support và token payload đã verify |
| Logout theo `sid` không tìm phiên | ID Token login không có sid, registry không lưu hoặc session expired | Kiểm tra OP metadata và registry |
| Node A logout đúng, node B không | Registry memory không chia sẻ | Shared registry/multi-node integration |
| Cookie còn thấy trong browser | Back-channel không thao tác trực tiếp với browser cookie | Kiểm tra request kế tiếp có còn authenticated không |
| JWT exp cũ nhưng được nhận | Validation/clock skew sai | Enforce `exp`/`iat`/signature |
| Một OP logout nhầm tenant khác | Registry truy vấn chỉ theo sub | Ràng buộc issuer/audience/sid/sub |
| Sau logout API vẫn chấp nhận Access Token | Resource Server token chưa hết hạn/chưa revoke | Xem API token lifecycle, không quy lỗi cookie |
| Refresh Token còn tồn tại | Offline policy hoặc store không cleanup | Xác định policy `offline_access`/revocation |
| OP retry nhiều lần | RP timeout/lỗi mạng/response không hợp lệ | Giám sát endpoint latency, idempotency |
| Session registry phình lớn | Không cleanup session expired | Event publisher/session lifecycle, TTL |
| Đăng nhập OIDC hoạt động nhưng logout không | OIDC login không đồng nghĩa back-channel đã bật | Xác nhận cả hai phía và integration tests |

### 23.1. Các câu hỏi điều tra đúng thứ tự

~~~text
1. OP có backchannel_logout_supported = true?
2. RP đã đăng ký backchannel_logout_uri đúng public HTTPS URL?
3. OP network có gọi được RP endpoint?
4. SecurityFilterChain nào nhận POST này?
5. Logout Token có chữ ký và claims hợp lệ?
6. iss, aud map đúng ClientRegistration?
7. sid/sub match phiên đã ghi trong OIDC registry?
8. Registry có dùng chung giữa pods không?
9. RP session store có thể invalidate đúng local session không?
10. Cookie name trong internal logout có chính xác không?
11. Request tiếp theo với cookie cũ còn authenticated không?
12. Product có yêu cầu revoke/cleanup OAuth2 tokens ngoài session?
~~~

Không dùng việc in JWT/session cookie ra log để trả lời những câu hỏi này. Hãy dùng metadata được kiểm soát và correlation ID.

## 24. Tình huống thực tế

### Tình huống A — Người dùng logout ở một ứng dụng khác

Alice đang mở Portal, đồng thời logout ở OP từ ứng dụng Billing.

**Kết quả mong đợi:** OP phát Back-Channel Logout Token cho Portal; Portal invalidate local session tương ứng. Khi Alice tải trang Portal lần tiếp theo, session cũ không còn quyền truy cập.

### Tình huống B — Chỉ logout laptop, giữ điện thoại

OP có hai sessions `sid=laptop` và `sid=phone` của cùng `sub`. OP phát token có `sid=laptop`.

**Kết quả mong đợi:** RP kết thúc local session ánh xạ laptop, không tự xóa phone nếu không có OP event tương ứng.

### Tình huống C — Global logout theo người dùng

OP không phát `sid` mà gửi Logout Token có `sub=user-123`.

**Kết quả mong đợi:** RP kết thúc tất cả local sessions của user đó trong **đúng issuer/client audience**, kể cả nhiều thiết bị.

### Tình huống D — Hai IdP cùng subject

Company OP và Partner OP đều có subject `user-123`.

**Kết quả mong đợi:** token của Company không logout session đăng nhập bằng Partner vì issuer và audience khác nhau.

### Tình huống E — Spring Session Redis dùng `SESSION`

Ứng dụng chuyển từ container session sang Spring Session, nhưng OIDC handler vẫn giả định `JSESSIONID`.

**Cách xử lý:** cấu hình `OidcBackChannelLogoutHandler.setSessionCookieName("SESSION")` (hoặc Reactive handler tương ứng) và kiểm thử kết thúc session thật.

### Tình huống F — OP gọi vào node không giữ registry

User login vào Node A. OP gửi logout đến Node B sau load balancer; Node B không có in-memory mapping.

**Cách xử lý:** custom shared `OidcSessionRegistry` / `ReactiveOidcSessionRegistry` hoặc kiến trúc session affinity có kiểm thử; không coi Redis shared sessions tự giải quyết registry.

### Tình huống G — Resource Server tiếp tục chấp nhận token

RP session đã logout nhưng Access Token trước đó còn hạn và API dùng self-contained JWT.

**Giải pháp:** đây là câu chuyện Access Token expiration/revocation; dùng policy token TTL ngắn, introspection hoặc revoke/denylist nếu cần theo kiến trúc, không tự kết luận back-channel hỏng.

### Tình huống H — OP gửi Logout Token sai audience

Issuer đúng nhưng `aud=billing-client`; request được gửi vào registration `company` của Portal.

**Kết quả:** RP phải từ chối, không xóa Portal sessions vì token không dành cho client này.

### Tình huống I — Attacker tự tạo JSON có sub

Attacker gửi `logout_token` chỉ là JWT self-signed hoặc không ký, có `sub` của Alice.

**Kết quả:** RP reject; **không** xóa session. Signature, issuer, audience và logout event là các điều kiện bắt buộc.

### Tình huống J — Provider thiếu sid trong ID Token

OP nói hỗ trợ Back-Channel Logout nhưng không hỗ trợ session-specific `sid`, chỉ phát `sub`.

**Giải pháp:** thống nhất RP metadata `backchannel_logout_session_required=false`; chấp nhận semantics logout theo subject, không cố đoán sid.

### Tình huống K — Một request logout được gửi lại

OP timeout khi nhận response, rồi retry cùng Logout Token. Session RP đã bị invalidate.

**Kết quả:** cơ chế logout xử lý idempotent và không xóa session mới/khác. Nếu có jti replay tracking, phân loại hợp lý để monitoring.

### Tình huống L — Portal đóng vai trò OP cho ứng dụng downstream

Portal là RP đối với Company OP, nhưng cũng phát hành phiên đăng nhập cho downstream applications.

**Thiết kế:** sau khi nhận back-channel logout hợp lệ, có thể cần phát sự kiện logout tiếp cho downstream RPs theo kiến trúc. Không chỉ invalidating phiên Portal nếu sản phẩm cam kết global SSO logout.

## 25. Checklist trước production

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| OP có hỗ trợ back-channel? | Discovery metadata và provider documentation |
| OP có hỗ trợ `sid`? | `backchannel_logout_session_supported` và ID Token behavior |
| RP có đăng ký endpoint? | `backchannel_logout_uri` đúng HTTPS public route |
| RP có bật `oidcLogout().backChannel(...)`? | Đúng SecurityFilterChain, dependency/version |
| `oauth2Login` đã cấu hình? | Back-channel không phải tính năng của Client Credentials |
| Logout Token được verify? | Signature, alg, iss, aud, iat, exp, jti, events, sid/sub, nonce absent |
| Mapping có đúng owner? | issuer + client + sid/sub -> local session |
| Cookie name đúng? | `JSESSIONID` hoặc `SESSION` theo hạ tầng |
| Registry có chia sẻ multi-node? | Custom registry khi cluster yêu cầu |
| Session store có thực sự invalidate? | Integration test với browser cookie cũ |
| Session lifecycle có cleanup? | Event publisher/TTL/invalidation |
| OP POST có bị CSRF/chain chặn không? | Test 200/400, không tắt CSRF toàn cục |
| Rate limit/DoS/replay? | Body limits, TTL, optional jti cache, monitoring |
| Các client IDs có tách tenant? | aud/iss verification và registry isolation |
| Access/Refresh Token lifecycle? | Phân biệt session logout với revocation/offline access |
| Log có an toàn? | Không token/JSESSIONID/sub/sid raw không cần thiết |
| OP callback/endpoint đi qua proxy? | TLS, path, forwarding headers, reachability |
| Có test hai thiết bị? | `sid` scoped vs `sub` all-sessions |
| Có test multi-instance? | Logout đến node bất kỳ vẫn chấm dứt đúng session |

## 26. Tài liệu tham khảo

- OpenID Connect Back-Channel Logout 1.0 — **incorporating errata set 1 (2023)**: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OpenID Connect Back-Channel Logout 1.0 — bản Final 2022 (đối chiếu lịch sử): https://openid.net/specs/openid-connect-backchannel-1_0-final.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security 6.5 — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/logout.html
- Spring Security 6.5 — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/logout.html
- Spring Security — `OidcBackChannelLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/OidcBackChannelLogoutHandler.html
- Spring Security — `OidcSessionRegistry` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/session/OidcSessionRegistry.html
- Spring Security — `OidcBackChannelServerLogoutHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/OidcBackChannelServerLogoutHandler.html
- Spring Security — `ReactiveOidcSessionRegistry` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/session/ReactiveOidcSessionRegistry.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009

## 27. Tổng kết

~~~text
Người dùng đăng nhập OIDC
  -> OP phát ID Token (có iss, sub, sid nếu hỗ trợ)
  -> RP xác minh login và tạo HttpSession/WebSession
  -> RP ghi OIDC Session Registry:
       OP issuer + client + sid/sub -> RP local session

Người dùng hoặc quản trị viên logout tại OP
  -> OP gửi POST backchannel_logout_uri
       Content-Type: application/x-www-form-urlencoded
       logout_token = signed JWT
  -> RP kiểm tra:
       signature + alg + iss + aud + iat + exp + jti
       events backchannel logout
       sub hoặc sid
       KHÔNG có nonce
  -> RP tìm local sessions trong registry
       sid: đúng OP session cụ thể
       sub-only: mọi sessions của user trong đúng issuer/client
  -> Spring Security chạy logout/invalidation
  -> RP phản hồi HTTP 200 khi thành công
  -> Cookie cũ ở browser không còn truy cập authenticated session

Không đánh đồng:
  Logout Token != ID Token != Access Token
  OP sid != RP JSESSIONID / SESSION
  Local session invalidation != Access/Refresh Token revocation
~~~

**Năm điểm cần ghi nhớ:**

1. **Back-Channel Logout là giao tiếp OP → RP bằng HTTP POST server-to-server**, không cần browser tab đang mở. RP nhận `logout_token`, không phải một query parameter chứa session ID.
2. **Logout Token phải được xác minh theo OIDC Back-Channel Logout**, gồm chữ ký, issuer, audience, thời gian, `jti`, `events`, ít nhất `sub` hoặc `sid` và **không có `nonce`**. ID Token và Access Token không được dùng thay Logout Token.
3. **`sid` chọn phiên OP cụ thể, `sub` khi không có sid có thể logout mọi phiên của user** trong phạm vi đúng issuer và client. Cần registry liên kết OP identity với RP local sessions.
4. **Spring Security cung cấp `oidcLogout().backChannel(...)` cho Servlet và Reactive**, nhưng phải cấu hình đúng cookie name, registry, session lifecycle, network endpoint và OP registration, đặc biệt trong cluster.
5. **Đăng xuất phiên không mặc nhiên thu hồi OAuth2 tokens.** Refresh Token, offline access, Access Token TTL và Resource Server validation cần chính sách riêng nếu sản phẩm yêu cầu kết thúc mọi quyền truy cập.

Hiểu rõ sự khác nhau giữa **Logout Token**, **OP Session ID** và **RP local session** giúp xây dựng Single Sign-Out đáng tin cậy, tránh xóa nhầm phiên giữa users/tenants, đồng thời giữ ranh giới bảo mật khi kết thúc phiên từ bên ngoài trình duyệt.
