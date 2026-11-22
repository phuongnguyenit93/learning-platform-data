# id_token_hint, client_id, post_logout_redirect_uri và state

> **Chương:** OIDC Logout  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi kỹ thuật:** OpenID Connect RP-Initiated Logout 1.0 Final (2022), Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x trên Servlet stack. Đối chiếu API theo patch version thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cách Relying Party (RP) yêu cầu OpenID Provider (OP) đăng xuất End-User bằng RP-Initiated Logout.
2. Tìm đúng `end_session_endpoint` từ OpenID Provider Discovery và phân biệt nó với OAuth2 Token Revocation Endpoint.
3. Hiểu vai trò, mức yêu cầu và cách kiểm tra của bốn tham số: `id_token_hint`, `client_id`, `post_logout_redirect_uri` và `state`.
4. Phân biệt ID Token hint với access token, refresh token, OAuth2 `redirect_uri`, authorization `state` và OIDC `nonce`.
5. Hiểu cách OP xác minh ID Token hint, client identity, session hiện tại và post-logout redirect target.
6. Thiết kế redirect allowlist để chống open redirect, phishing và logout request forgery.
7. Cấu hình OIDC Logout Endpoint trong Spring Authorization Server và đăng ký post-logout redirect URI cho từng RegisteredClient.
8. Dùng `OidcClientInitiatedLogoutSuccessHandler` trong Spring Security OAuth2 Client để RP điều hướng browser tới OP.
9. Kết hợp local logout, OP session logout, front-channel/back-channel notifications và token revocation thành quy trình rõ ràng.
10. Viết kiểm thử cho ID Token sai/expired, client mismatch, URI không đăng ký, state mismatch, session không còn tồn tại và nhiều RP cùng đăng nhập.

**Thông điệp:** `id_token_hint` giúp OP nhận diện user/client/session; `client_id` xác định client và phải khớp ID Token nếu cả hai cùng xuất hiện; `post_logout_redirect_uri` là đích quay lại đã đăng ký; `state` giúp RP tương quan callback. Bốn tham số có vai trò khác nhau và không thay thế lẫn nhau.

## 2. Bài toán: logout ở RP chưa chắc logout ở OP

Giả sử user đăng nhập ba ứng dụng: `booking-web`, `expense-portal` và `support-console`. Cả ba dùng chung OpenID Provider `https://auth.example.test`. User đã đăng nhập một lần và OP giữ browser session cookie.

Khi user bấm Logout ở `booking-web`:

1. RP có thể xóa session/cookie local của chính ứng dụng.
2. Browser vẫn còn session cookie tại OP.
3. Nếu user truy cập `expense-portal`, OP có thể SSO mà không hỏi mật khẩu.
4. User nghĩ mình đã logout hoàn toàn nhưng thực tế chỉ logout khỏi một RP.

RP-Initiated Logout cho phép RP chuyển browser đến Logout Endpoint của OP để yêu cầu OP kết thúc phiên End-User.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User / Browser
    participant RP as Booking RP
    participant OP as OpenID Provider
    participant RP2 as Expense RP

    U->>RP: Bấm Logout
    RP->>RP: Kết thúc local session
    RP-->>U: Redirect tới OP Logout Endpoint
    U->>OP: id_token_hint + post_logout_redirect_uri + state
    OP->>OP: Xác minh hint/client/session/redirect
    OP->>U: Xác nhận logout nếu cần
    U-->>OP: Đồng ý
    OP->>OP: Kết thúc OP session
    OP-->>RP2: Logout notification nếu đã cấu hình
    OP-->>U: Redirect về RP với state
    U->>RP: Callback post-logout
    RP->>RP: Kiểm tra state và hiển thị kết quả
~~~

**RP-Initiated Logout không đồng nghĩa thu hồi mọi OAuth2 token.** OP session, RP local session, access token, refresh token và session của RP khác là các trạng thái liên quan nhưng riêng biệt.

## 3. Thành phần và endpoint

| Thuật ngữ | Vai trò |
| --- | --- |
| RP (Relying Party) | Ứng dụng OIDC sử dụng authentication do OP cung cấp |
| OP (OpenID Provider) | Hệ thống xác thực user và phát hành ID Token |
| End-User | Người dùng đang đăng nhập |
| Logout Endpoint | Endpoint OP nhận RP-Initiated Logout request |
| `end_session_endpoint` | Metadata field công bố URL Logout Endpoint |
| `id_token_hint` | ID Token do OP cấp cho RP, dùng làm gợi ý nhận diện user/session |
| `client_id` | OAuth2 Client Identifier tại OP |
| `post_logout_redirect_uri` | URL RP yêu cầu browser quay về sau logout |
| `post_logout_redirect_uris` | Danh sách URI đã đăng ký được OP cho phép |
| `state` | Giá trị opaque RP dùng tương quan request và callback |
| `sid` | Session identifier trong OIDC session/logout profiles nếu được phát hành |

### 3.1. RP-Initiated Logout là redirect qua User Agent

RP thường điều hướng browser tới OP để browser mang OP session cookie hiện tại:

1. RP lấy `end_session_endpoint` từ OpenID Provider Configuration hoặc discovery tin cậy.
2. RP tạo Logout Request.
3. Browser điều hướng tới OP bằng HTTP GET hoặc POST.
4. OP xác minh request và xử lý phiên End-User.
5. OP có thể hỏi user xác nhận logout khỏi OP.
6. OP gửi logout notifications tới RP đã đăng ký cơ chế phù hợp.
7. OP redirect browser về RP nếu redirect target hợp lệ.

OIDC RP-Initiated Logout yêu cầu OP hỗ trợ cả GET và POST. RP MAY chọn một trong hai phương thức.

### 3.2. Lấy Logout Endpoint từ Discovery

OP công bố `end_session_endpoint` trong OpenID Provider metadata khi hỗ trợ RP-Initiated Logout và Discovery:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.test/connect/logout"
}
~~~

Đây là JSON minh họa. URL cụ thể phụ thuộc `AuthorizationServerSettings` và deployment. RP không nên tự ghép issuer với `/connect/logout` vì endpoint có thể đổi path/host/proxy route. Hãy dùng metadata đã xác minh của đúng OP.

### 3.3. Không nhầm các endpoint

| Endpoint | Mục đích |
| --- | --- |
| `authorization_endpoint` | Bắt đầu OAuth2/OIDC authorization |
| `token_endpoint` | Đổi code/refresh token lấy token |
| `end_session_endpoint` | Yêu cầu OP logout End-User |
| `revocation_endpoint` | Thu hồi access/refresh token theo RFC 7009 |
| `introspection_endpoint` | Hỏi trạng thái token theo RFC 7662 |
| Back-Channel Logout URI | RP nhận Logout Token server-to-server nếu hỗ trợ |

RP logout không tự thay revocation. Nếu cần thu hồi refresh token, phải triển khai Token Revocation riêng theo policy.

## 4. Bốn tham số chính

| Tham số | Mức yêu cầu | Ai tạo? | Mục đích |
| --- | --- | --- | --- |
| `id_token_hint` | RECOMMENDED | RP giữ ID Token do OP cấp | OP nhận diện End-User, client và session |
| `client_id` | OPTIONAL | RP | Xác định client; nếu kèm ID Token hint, OP MUST kiểm tra khớp |
| `post_logout_redirect_uri` | OPTIONAL | RP | Đích browser quay về sau logout |
| `state` | OPTIONAL | RP | Tương quan logout request và callback |

Các từ khóa `RECOMMENDED`, `OPTIONAL`, `MUST` và `SHOULD` mang nghĩa normative theo OIDC RP-Initiated Logout 1.0.

### 4.1. Ví dụ GET request

~~~http
GET /connect/logout?id_token_hint=eyJ...ID_TOKEN...&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

### 4.2. Ví dụ POST request

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=eyJ...ID_TOKEN...&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

GET dùng URI Query String Serialization; POST dùng Form Serialization. Không gửi client secret trong Logout Request.

## 5. id_token_hint — nhận diện user và session

### 5.1. Định nghĩa và mục đích

`id_token_hint` là ID Token **đã được OP phát hành trước đó cho RP**, gửi tới Logout Endpoint như gợi ý về phiên đăng nhập hiện tại của End-User với client.

OP có thể dùng nó để xác định:

- Subject/user.
- Client/RP đã nhận ID Token.
- Session liên quan, nếu ID Token có `sid`.
- Authorization/registration context để xác minh redirect target.

`id_token_hint` là **RECOMMENDED**, đặc biệt khi RP muốn redirect browser về sau logout.

### 5.2. Gửi đúng loại token

Gửi ID Token do chính OP phát hành cho RP. Không thay bằng:

- OAuth2 access token.
- Refresh token.
- Authorization code.
- JWT tự ký bởi RP.
- ID Token từ issuer khác.
- ID Token của user/client khác.

Access token chứng minh quyền truy cập Resource Server; ID Token là identity assertion dành cho RP. Logout Endpoint cần ID Token hint theo OIDC RP-Initiated Logout.

### 5.3. OP phải xác minh ID Token hint

Khi `id_token_hint` hiện diện, OP **MUST** xác minh mình là issuer của ID Token.

OP cần xác minh token được chính mình phát hành và kiểm tra quan hệ client/session theo protocol. Không chỉ decode JWT payload rồi tin `sub`. Chữ ký/nguồn phát hành, client identity và session context phải được xác minh.

### 5.4. ID Token hint đã hết hạn có bị từ chối?

Đây là điểm quan trọng: OIDC RP-Initiated Logout quy định OP **SHOULD** chấp nhận ID Token khi RP được xác định qua `aud` và/hoặc `sid` có session hiện tại hoặc session gần đây tại OP, **ngay cả khi `exp` đã qua**.

Lý do: ID Token hint dùng nhận diện phiên cần logout; user có thể logout sau khi ID Token hết hạn nhưng OP session vẫn còn.

- Không mặc định từ chối hint chỉ vì `exp` đã qua.
- OP vẫn phải xác minh token do mình phát hành.
- Token hết hạn không tự chứng minh user còn session.
- Nếu `sid` không khớp session hiện tại/recent session, OP SHOULD coi request đáng ngờ và MAY từ chối.
- OP có thể hỏi user xác nhận khi hint không gắn với session hiện tại.

Đây là semantics riêng cho logout hint, không áp dụng cho access token gọi API.

### 5.5. Hint không thay xác nhận logout

ID Token hint giúp OP nhận diện phiên, không chứng minh user đã đồng ý logout khỏi OP.

OP SHOULD hỏi End-User có muốn logout khỏi OP hay không. OP MUST hỏi nếu không có `id_token_hint` hoặc ID Token không thuộc session OP hiện tại với RP và/hoặc user đang đăng nhập. Nếu user trả lời yes, OP MUST logout End-User.

### 5.6. Bảo vệ ID Token hint

- Không ghi raw ID Token vào application log.
- Không đưa token vào analytics/tracing.
- Bảo vệ session/cookie nơi RP lưu ID Token.
- Với GET, token có thể xuất hiện trong URL, browser history và proxy logs; cân nhắc POST.
- Không dùng hint để xác thực user cho chức năng khác.
- Chỉ giữ token trong thời gian cần thiết theo retention policy.

## 6. client_id — xác định OAuth2 Client

### 6.1. Định nghĩa

`client_id` là OAuth 2.0 Client Identifier hợp lệ tại OP. Tham số này OPTIONAL.

Nó hữu ích khi:

- RP chỉ rõ client đang yêu cầu logout.
- RP gửi `post_logout_redirect_uri` nhưng không gửi `id_token_hint`.
- OP cần client identifier để giải mã ID Token được mã hóa đối xứng.
- Deployment có nhiều client/tenant và cần xác định registration.

### 6.2. Khi có cả client_id và id_token_hint

Đây là quy tắc MUST: khi hai tham số cùng xuất hiện, OP MUST xác minh client identifier khớp với client đã dùng khi phát hành ID Token.

Ví dụ hợp lệ:

~~~text
id_token_hint = ID_TOKEN_ISSUED_TO_booking-bff
client_id     = booking-bff
~~~

Ví dụ không hợp lệ:

~~~text
id_token_hint = ID_TOKEN_ISSUED_TO_booking-bff
client_id     = expense-portal
~~~

Nếu OP chấp nhận cặp sai, client khác có thể cố dùng ID Token của RP này để điều khiển logout/redirect của RP kia.

### 6.3. client_id không phải client_secret

`client_id` là định danh công khai. Không gửi `client_secret` tới Logout Endpoint trong query hoặc form body.

Logout Endpoint xử lý browser session và ID Token hint; nó không phải Token Endpoint. Không dùng HTTP Basic client authentication của Token Endpoint để thay cơ chế OIDC logout.

### 6.4. Khi không có id_token_hint

`client_id` thường giúp xác định RP khi `post_logout_redirect_uri` được gửi mà không có hint. Tuy nhiên, biết một client ID không có nghĩa OP được phép redirect tới URL bất kỳ.

Nếu không có `id_token_hint` cùng `post_logout_redirect_uri`, OP MUST NOT redirect trừ khi có phương tiện khác xác nhận tính hợp pháp của redirect target. Client ID đã đăng ký và URI exact-match có thể là một phần của cơ chế đó tùy implementation; không coi client ID tự thân là bí mật hay bằng chứng user/session.

## 7. post_logout_redirect_uri — đích quay về sau logout

### 7.1. Định nghĩa

`post_logout_redirect_uri` là URI RP yêu cầu browser điều hướng về sau khi OP hoàn tất logout. Tham số OPTIONAL.

Khi sử dụng:

- URI MUST được đăng ký trước với OP qua `post_logout_redirect_uris` hoặc cơ chế đăng ký khác.
- URI SHOULD dùng HTTPS.
- HTTP có thể được cho phép trong điều kiện hạn chế với confidential client và khi OP cho phép.
- Native app có thể dùng alternate scheme phù hợp.
- OP MUST so khớp chính xác URI request với một URI đã đăng ký.
- OP MUST không redirect nếu validation thất bại.

### 7.2. Exact match, không wildcard

Giả sử client đăng ký:

~~~text
https://app.example.test/logout/callback
~~~

URI này khớp chính xác. Các URI sau không tự động khớp:

~~~text
https://app.example.test/logout/callback/
https://app.example.test/logout/callback?next=/admin
https://app.example.test.evil.test/logout/callback
http://app.example.test/logout/callback
~~~

OP phải exact-match theo URI đã đăng ký, không prefix-match hoặc wildcard hostname. Không dùng `startsWith` trên host để kiểm tra vì hostname giả mạo có thể vượt qua.

### 7.3. Đăng ký post-logout URI trong SAS

~~~java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-registration")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .postLogoutRedirectUri(
        "https://app.example.test/logout/callback")
    .scope("openid")
    .scope("profile")
    .build();
~~~

Đây là fragment registration; cần các import/bean tương ứng và không lưu client secret plaintext. `RegisteredClient.Builder.postLogoutRedirectUri` có từ SAS 1.1.

### 7.4. post_logout_redirect_uri khác redirect_uri

| Tham số | Dùng tại | Mục đích |
| --- | --- | --- |
| `redirect_uri` | Authorization Request | Nơi OP trả authorization response/code |
| `post_logout_redirect_uri` | Logout Request | Nơi OP đưa browser về sau logout |

Hai URI có thể cùng origin nhưng là registration riêng. Không dùng `redirectUri` của Authorization Code Flow thay thế post-logout URI.

### 7.5. Không có id_token_hint nhưng có redirect URI

OIDC RP-Initiated Logout quy định:

- `id_token_hint` được RECOMMENDED khi yêu cầu post-logout redirect.
- Nếu không có hint, OP MUST có phương tiện khác xác nhận redirect target hợp pháp.
- OP MUST không redirect nếu URI không exact-match URI đã đăng ký.
- Khi request validation thất bại, OP MUST không redirect về RP.

Không fallback sang URL do query parameter tùy ý cung cấp.

## 8. state — tương quan request và callback

### 8.1. Định nghĩa

`state` là giá trị opaque OPTIONAL do RP tạo để tương quan Logout Request với callback. Nếu request có state và OP redirect browser về RP, OP trả lại chính giá trị đó qua tham số `state`.

OP không cần hiểu nội dung; RP phải tự quản lý và xác minh.

### 8.2. Tạo state an toàn

Nên tạo chuỗi ngẫu nhiên khó đoán (ví dụ 256 bit từ secure random), encode Base64URL và lưu bản gốc gắn với browser session/transaction có TTL.

Không đưa vào state:

- Refresh/access token.
- Client secret.
- Session cookie.
- Dữ liệu cá nhân không cần thiết.
- URL redirect tùy ý chưa kiểm tra.

### 8.3. Xác minh state ở RP

1. Tạo random state.
2. Lưu state gắn với session/transaction.
3. Redirect tới OP.
4. OP xử lý logout và echo state.
5. RP lấy state callback.
6. So khớp chính xác với giá trị đã lưu.
7. Consume state sau khi dùng hoặc khi hết TTL.
8. Chỉ hoàn tất callback nếu state khớp.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    RP->>RP: Generate random state S
    RP->>RP: Store S with TTL
    RP-->>B: Redirect to OP with state S
    B->>OP: Logout Request
    OP->>OP: Validate and end session
    OP-->>B: Redirect with state S
    B->>RP: GET /logout/callback?state=S
    RP->>RP: Compare callback state with stored state
    alt State matches
        RP->>RP: Consume state and finish
    else Missing, mismatch or replay
        RP->>RP: Reject callback correlation
    end
~~~

### 8.4. state logout khác state login

OIDC Authorization Code Flow cũng có `state`, nhưng login và logout là hai transaction khác nhau. Không dùng lại state của login request cho logout. Mỗi logout request cần correlation value riêng, TTL ngắn và một lần sử dụng.

### 8.5. OP echo state không có nghĩa OP ký state

OP trả state về nguyên giá trị, nhưng không ký hoặc xác minh state thay RP. RP vẫn cần random state, HTTPS, session binding và one-time validation.

## 9. GET và POST

### 9.1. GET

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

GET dễ triển khai nhưng query parameters có thể xuất hiện trong browser history, reverse proxy/access logs, APM và URL telemetry. Không log query của Logout Endpoint hoặc phải redaction tham số nhạy cảm.

### 9.2. POST

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=ID_TOKEN_VALUE&client_id=booking-bff&post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

POST đặt tham số trong form body. OP MUST hỗ trợ POST và GET; RP MAY dùng một trong hai. POST giảm việc đưa ID Token hint lên URL nhưng body vẫn có thể bị proxy/APM log nếu không redaction.

### 9.3. CSRF local logout là cơ chế riêng

CSRF token bảo vệ local logout endpoint của RP không phải OIDC state và không cần gửi sang OP. Không tắt CSRF cho local logout chỉ vì đã có `state` trong RP-Initiated Logout.

## 10. OP xử lý Logout Request

### 10.1. Các bước xác minh

1. Parse GET query hoặc POST form.
2. Nếu có `id_token_hint`, xác minh OP là issuer của token.
3. Nếu có cả `client_id` và hint, kiểm tra client match.
4. Xác định End-User/session từ token và session registry.
5. Kiểm tra `post_logout_redirect_uri` thuộc allowlist client.
6. Nếu không có hint, xác định client bằng cơ chế hợp lệ và yêu cầu confirmation khi cần.
7. Chỉ redirect nếu target được xác minh.
8. Kết thúc OP session theo kết quả xử lý/consent.
9. Gửi logout notifications tới RP đã đăng ký cơ chế phù hợp.
10. Redirect về RP sau khi xử lý notifications nếu target hợp lệ.

### 10.2. Logout có tính idempotent

OIDC RP-Initiated Logout quy định việc RP yêu cầu logout khi OP không còn coi user đang đăng nhập tại RP đó không tự thân là lỗi. Ví dụ user đã logout ở tab khác, OP session timeout hoặc RP retry sau timeout.

### 10.3. Khi OP phải hỏi user?

- OP SHOULD hỏi End-User có muốn logout khỏi OP không.
- OP MUST hỏi nếu không có `id_token_hint`.
- OP MUST hỏi nếu ID Token không thuộc session OP hiện tại với RP và/hoặc End-User đang đăng nhập.
- Nếu user trả lời yes, OP MUST logout End-User.

### 10.4. Khi OP không được redirect?

OP MUST không thực hiện post-logout redirect nếu URI không exact-match, validation thất bại hoặc không có hint và không có phương tiện khác xác nhận redirect target. OP có thể hiển thị trang lỗi/confirmation, nhưng không redirect tới URL chưa xác minh.

## 11. Phân biệt các lớp session và token

| Trạng thái | Cách kết thúc | RP-Initiated Logout có tự xử lý? |
| --- | --- | --- |
| RP local session | Invalidate HTTP session/cookie | RP tự xử lý |
| OP browser session | Logout Endpoint | Có, đây là mục đích chính |
| Các RP khác | Front-/Back-Channel Logout hoặc Session Management | OP thông báo nếu hỗ trợ |
| Access token JWT | Expiry/denylist/introspection/revocation | Không tự động |
| Refresh token | RFC 7009 revocation hoặc policy riêng | Không tự động |
| Remember-me cookie | Local logout handler | RP/OP tự xử lý |

### 11.1. Local logout trước hay sau OP logout?

OIDC để RP quyết định có local logout trước khi redirect tới OP hay không.

**Local logout trước:** user lập tức mất session RP. Nếu user từ chối OP logout, RP local vẫn đã logout.

**Local logout sau:** có thể chờ OP hoàn tất, nhưng browser đóng hoặc redirect thất bại có thể khiến local session còn tồn tại.

Một lựa chọn thường thực tế là invalidate local session ngay, giữ ID Token hint cần thiết trong transaction logout, rồi redirect browser tới OP. Nếu user từ chối OP logout, RP local vẫn đã kết thúc theo ý định ban đầu.

### 11.2. OP logout không tự revoke access token

Nếu RS xác minh JWT cục bộ, token có thể tiếp tục hợp lệ tới `exp`. Logout OP session không tự sửa JWT hoặc xóa token khỏi RS.

Nếu yêu cầu logout phải ngăn API access sớm, hãy dùng token revocation, opaque token + introspection, denylist/event strategy hoặc access token TTL ngắn. Đây là policy riêng.

### 11.3. RP-Initiated khác Front-/Back-Channel Logout

- **RP-Initiated:** user bấm logout ở RP, RP yêu cầu OP logout.
- **Front-Channel:** OP điều hướng browser tới logout URI của RP.
- **Back-Channel:** OP gọi logout URI server-to-server với Logout Token.

RP A gọi OP Logout Endpoint không bảo đảm RP B tự xóa session nếu B không triển khai notification phù hợp.

## 12. Spring Authorization Server: bật OIDC Logout Endpoint

### 12.1. Bật OIDC

SAS không bật OIDC mặc định. Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Đây là fragment. Ứng dụng đầy đủ cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, issuer/JWK nếu phát JWT và application SecurityFilterChain cho user login.

Có thể tùy chỉnh riêng `logoutEndpoint` qua OIDC configurer nếu cần. Khi bật OIDC mặc định, các OIDC endpoints được cấu hình theo version/framework.

### 12.2. Cấu hình path

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .oidcLogoutEndpoint("/connect/logout")
        .build();
}
~~~

Path mặc định thường là `/connect/logout` trong SAS 1.x. Nếu đổi path, bảo đảm OIDC Provider Configuration công bố `end_session_endpoint` tương ứng và proxy route đúng.

### 12.3. Đăng ký URI cho client

~~~java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(
        AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri(
        "https://app.example.test/login/oauth2/code/booking")
    .postLogoutRedirectUri(
        "https://app.example.test/logout/callback")
    .scope("openid")
    .scope("profile")
    .build();
~~~

`RegisteredClient.Builder.postLogoutRedirectUri` có từ SAS 1.1. Nếu dùng JDBC repository, schema/serialization phải lưu và đọc lại registration đúng cách.

### 12.4. Các thành phần chính

SAS 1.5.x cung cấp:

- `OidcLogoutEndpointConfigurer`: cấu hình endpoint và extension points.
- `OidcLogoutEndpointFilter`: nhận logout request.
- `OidcLogoutAuthenticationConverter`: chuyển request thành authentication token.
- `OidcLogoutAuthenticationProvider`: xác minh request.
- `OidcLogoutAuthenticationSuccessHandler`: xử lý logout thành công và response/redirect.
- `OidcLogoutAuthenticationValidator`: validator mặc định cho tham số logout, bao gồm post-logout redirect URI.
- `SessionRegistry`: tra session của End-User.

Không tự tạo controller nhận redirect URL rồi gọi redirect trực tiếp. Cách đó bỏ qua validation RegisteredClient và tạo open redirect.

### 12.5. Tùy chỉnh endpoint

`OidcLogoutEndpointConfigurer` có extension points cho converter, provider, success handler và failure handler:

~~~java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(logout ->
        logout
            .logoutRequestConverter(customLogoutRequestConverter)
            .authenticationProvider(customLogoutProvider)
            .logoutResponseHandler(customSuccessHandler)
            .errorResponseHandler(customFailureHandler)
    )
);
~~~

Đây là fragment bên trong AS configurer. Custom component phải giữ protocol validation và redirect allowlist; không thay success handler chỉ để redirect tới URL tùy ý.

### 12.6. Tùy chỉnh validation

`OidcLogoutAuthenticationProvider.setAuthenticationValidator(...)` cho phép bổ sung logic qua `OidcLogoutAuthenticationContext`.

~~~java
oidc.logoutEndpoint(logout ->
    logout.authenticationProviders(providers ->
        providers.forEach(provider -> {
            if (provider instanceof OidcLogoutAuthenticationProvider oidcProvider) {
                oidcProvider.setAuthenticationValidator(context -> {
                    OidcLogoutAuthenticationToken request =
                        context.getAuthentication();

                    RegisteredClient registeredClient =
                        context.getRegisteredClient();

                    // Bổ sung policy cần thiết.
                    // Nếu validation thất bại, ném OAuth2AuthenticationException.
                });
            }
        })
    )
);
~~~

Đây là khung minh họa. Default validator đã kiểm tra post-logout redirect URI. Chỉ override khi có yêu cầu thực sự và phải giữ những kiểm tra cần thiết. Validator MUST ném `OAuth2AuthenticationException` khi validation thất bại.

## 13. SessionRegistry trong SAS

### 13.1. Vai trò

`OidcLogoutAuthenticationProvider` sử dụng `SessionRegistry` để tìm `SessionInformation` gắn với End-User đang yêu cầu logout. OIDC Authorization Endpoint cũng cần tracking các session đã xác thực.

### 13.2. SessionRegistryImpl và HttpSessionEventPublisher

Nếu không đăng ký bean, SAS dùng default `SessionRegistryImpl`. Nếu ứng dụng đăng ký `SessionRegistryImpl` riêng, nên thêm `HttpSessionEventPublisher` để registry nhận lifecycle events và xóa session metadata đã hủy.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
class SessionRegistryConfiguration {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

Nếu dùng concurrent session control, chia sẻ cùng SessionRegistry giúp session management và logout nhìn thấy trạng thái thống nhất.

### 13.3. Multi-instance deployment

`SessionRegistryImpl` mặc định là registry trong bộ nhớ của một instance. Trong hệ thống nhiều node, cần shared session registry/store hoặc session clustering phù hợp.

Nếu login vào node A nhưng logout request được route tới node B, node B có thể không tìm thấy SessionInformation. Cần kiểm thử logout khi failover/rolling deployment; sticky session không thay thế thiết kế shared state nếu hệ thống yêu cầu failover.

## 14. RP sử dụng Spring Security OAuth2 Client

### 14.1. OidcClientInitiatedLogoutSuccessHandler

Spring Security cung cấp `OidcClientInitiatedLogoutSuccessHandler` để RP chuyển browser tới OP sau khi local logout thành công.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
class RelyingPartySecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        LogoutSuccessHandler handler = oidcLogoutSuccessHandler(registrations);

        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout ->
                logout.logoutSuccessHandler(handler));

        return http.build();
    }

    private LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        handler.setPostLogoutRedirectUri("{baseUrl}");
        return handler;
    }
}
~~~

`{baseUrl}` là placeholder được Spring Security thay bằng base URL ứng dụng khi xử lý request. URL thực tế phải nằm trong allowlist đã đăng ký ở OP. Với nhiều host/domain, không để Host header không tin cậy quyết định callback URL.

### 14.2. Handler làm gì?

Trong OAuth2 Login/OIDC session, handler có thể:

- Lấy ID Token từ OIDC authentication.
- Đọc provider metadata để tìm OP Logout Endpoint.
- Tạo redirect với `id_token_hint`.
- Thêm `post_logout_redirect_uri` nếu được cấu hình.
- Điều hướng browser tới OP bằng GET theo mặc định.

Spring Security **6.5 trở lên** hỗ trợ POST redirect strategy bằng `FormPostRedirectStrategy` nếu ứng dụng muốn gửi form POST. Ở các phiên bản cũ hơn, cần tự triển khai redirect strategy tương đương hoặc dùng GET.

### 14.3. Đăng ký URI ở cả hai phía

RP cấu hình:

~~~java
handler.setPostLogoutRedirectUri("{baseUrl}");
~~~

OP RegisteredClient phải có URI tương ứng với public base URL thực tế, ví dụ:

~~~java
.postLogoutRedirectUri("https://app.example.test")
~~~

Nếu handler sinh `https://app.example.test` nhưng OP chỉ đăng ký `https://app.example.test/logout/callback`, request không khớp. Chọn callback rõ ràng và đăng ký chính xác.

### 14.4. state với Spring handler

OIDC Logout định nghĩa `state` OPTIONAL và yêu cầu OP echo lại. Nếu ứng dụng cần state rõ ràng, phải đảm bảo handler/flow tạo, lưu và xác minh state theo policy.

Không giả định mọi version `OidcClientInitiatedLogoutSuccessHandler` tự cung cấp đầy đủ state transaction. Có thể mở rộng success handler hoặc triển khai redirect strategy với random state được lưu gắn session/transaction.

### 14.5. Form POST redirect

~~~java
import org.springframework.security.web.FormPostRedirectStrategy;

OidcClientInitiatedLogoutSuccessHandler handler =
    new OidcClientInitiatedLogoutSuccessHandler(clientRegistrationRepository);

handler.setPostLogoutRedirectUri("{baseUrl}");
handler.setRedirectStrategy(new FormPostRedirectStrategy());
~~~

Đây là fragment; kiểm tra class/package theo Spring Security version. OP phải hỗ trợ POST. POST không thay thế HTTPS, URI validation hay state correlation.

## 15. Quy trình logout hoàn chỉnh

~~~mermaid
flowchart TD
    START["User bấm Logout"]
    TOKEN["RP lấy ID Token hint từ OIDC session"]
    STATE["Tạo và lưu state nếu cần callback"]
    LOCAL["Invalidate local session + clear cookie"]
    DISC["Dùng end_session_endpoint từ metadata"]
    REQ["Gửi id_token_hint, client_id, redirect URI, state"]
    OP["OP xác minh hint/client/session/redirect"]
    CONF{"OP cần confirmation?"}
    ASK["Hỏi user logout khỏi OP?"]
    DEC{"User đồng ý?"}
    ENDOP["Kết thúc OP session"]
    NOTIFY["Gửi logout notifications nếu hỗ trợ"]
    REDIR["Redirect URI đã đăng ký kèm state"]
    CALLBACK["RP xác minh state"]
    DONE["Hoàn tất"]
    CANCEL["OP session có thể còn"]

    START --> TOKEN --> STATE --> LOCAL --> DISC --> REQ --> OP --> CONF
    CONF -->|"Có"| ASK --> DEC
    CONF -->|"Không"| ENDOP
    DEC -->|"Có"| ENDOP --> NOTIFY --> REDIR --> CALLBACK --> DONE
    DEC -->|"Không"| CANCEL
    CONF -->|"Không cần hỏi"| ENDOP
~~~

Sơ đồ mô tả một lựa chọn UX; thứ tự local logout có thể thay đổi theo ứng dụng. OP chỉ redirect sau khi xử lý notifications và validation theo protocol.

### 15.1. Không có post_logout_redirect_uri

OP có thể hiển thị trang logout hoàn tất. RP cần UX fallback, không tự điều hướng tới URL từ query không tin cậy và không khẳng định mọi RP khác đã logout nếu không có notification/acknowledgement.

### 15.2. OP session đã hết hạn

RP vẫn có thể gửi ID Token hint để OP xác định user/client. Request logout có tính idempotent; việc không còn session không nhất thiết là lỗi. OP có thể hiển thị trang kết quả hoặc confirmation tùy trạng thái.

## 16. Bảo mật state, redirect và ID Token hint

### 16.1. Open redirect

Nếu OP chấp nhận `post_logout_redirect_uri=https://attacker.example/phishing` mà không so allowlist, attacker có thể khiến browser rời OP tới trang giả mạo.

Phòng vệ:

- Đăng ký từng URI rõ ràng.
- Exact match.
- Không wildcard host/path.
- Không prefix-match.
- Không cho client tự sửa allowlist qua query.
- Không redirect khi token/client/URI validation thất bại.

### 16.2. Logout CSRF và forced logout

Logout request không có hint hợp lệ có thể bị lợi dụng để buộc user logout khỏi OP, gây denial of service. Spec yêu cầu OP hỏi confirmation khi thiếu hint hoặc hint không thuộc session hiện tại theo các điều kiện đã nêu.

RP cũng phải bảo vệ local logout endpoint theo CSRF policy. Thường dùng POST cho thao tác logout local và giữ CSRF protection của Spring Security.

### 16.3. ID Token hint là dữ liệu nhạy cảm

ID Token hint bị lộ có thể tiết lộ subject/client/session context và bị replay để khởi tạo logout request. Không log raw token, không dùng nó như credential API, xác minh issuer/client/session và redirect.

### 16.4. state và callback CSRF

RP chỉ hoàn tất callback khi state khớp transaction đang chờ và chưa được sử dụng. Không dùng state tĩnh như `logout` hoặc `success`. State phải random, TTL ngắn, one-time và session-bound.

### 16.5. Query string và logging

GET request có ID Token hint có thể lộ query trong access log. Redact `id_token_hint` và `state`, tắt query capture hoặc lọc tại proxy/APM, cân nhắc POST form redirect và không lưu raw request trong audit.

## 17. Kiểm thử RP-Initiated Logout

### 17.1. Ma trận kiểm thử tham số

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| ID Token hint hợp lệ | Hint do OP phát, đúng RP/session | OP xác định đúng user/session |
| Hint từ issuer khác | Token không do OP hiện tại phát | OP từ chối sử dụng hint |
| Hint bị sửa chữ ký | JWT tampered | Validation thất bại |
| Hint hết hạn, session gần đây | exp qua nhưng aud/sid có recent session | OP SHOULD chấp nhận theo spec |
| Hint hết hạn, session không liên quan | sid không khớp current/recent | OP SHOULD coi suspect, MAY từ chối |
| client_id khớp hint | Cả hai cùng client | Xử lý bình thường |
| client_id mismatch | Token booking-bff, client_id expense-portal | OP MUST từ chối cặp mismatch |
| Không có client_id | Có hint hợp lệ | OP xác định client từ token |
| Không có hint, có client_id | Client đã đăng ký | Xác định client và confirmation khi cần |
| URI đã đăng ký | Exact match | Có thể redirect sau logout |
| URI không đăng ký | Host/path khác | Không redirect |
| URI prefix giống | Domain attacker dùng prefix | Không redirect |
| Không hint + URI | Không có phương tiện xác minh khác | MUST không redirect |
| State có mặt | State random | OP echo chính xác |
| State mismatch ở RP | Callback state khác | RP từ chối correlation |
| State replay | Dùng lại state cũ | RP từ chối |
| Không post_logout_redirect_uri | Logout hợp lệ | OP hiển thị kết quả/fallback |
| GET request | Query serialization | OP xử lý |
| POST request | Form serialization | OP xử lý |
| Local logout | User logout tại RP | RP session bị invalidate |
| OP logout | User đồng ý | OP session kết thúc |
| User không đồng ý | Confirmation decline | Không giả định OP session đã kết thúc |
| Multiple RPs | OP session dùng nhiều client | Notification theo cơ chế đã đăng ký |
| Refresh/access token | OP session logout | Không mặc định token bị revoke |

### 17.2. MockMvc test cho redirect URI

~~~java
@Test
void unregisteredPostLogoutRedirectUriMustNotRedirect() throws Exception {
    mockMvc.perform(get("/connect/logout")
            .param("id_token_hint", validIdTokenHint)
            .param("client_id", "booking-bff")
            .param(
                "post_logout_redirect_uri",
                "https://attacker.example/callback")
            .param("state", "random-state"))
        .andExpect(result ->
            assertThat(result.getResponse().getRedirectedUrl())
                .isNotEqualTo("https://attacker.example/callback"));
}
~~~

Đây là test body minh họa; cần `@SpringBootTest`/`@AutoConfigureMockMvc`, session/RegisteredClient, ID Token và filter chain thật. Không chỉ kiểm tra status; xác nhận không redirect ra host ngoài allowlist.

### 17.3. Test client mismatch

Tạo ID Token được phát hành cho `booking-bff` rồi gửi:

~~~http
GET /connect/logout?id_token_hint=TOKEN_FOR_BOOKING&client_id=expense-portal
~~~

Kỳ vọng:

- OP phát hiện mismatch.
- Không xử lý như thể token được phát cho `expense-portal`.
- Không redirect tới URI của client kia.
- Không lộ thông tin user/session qua error response.

### 17.4. Test state ở RP

- Tạo random state và lưu transaction.
- Callback đúng state: thành công, state bị consume.
- Callback sai state: reject.
- Callback không state khi transaction yêu cầu: reject.
- State replay: reject.
- State hết TTL: reject.
- State không chứa token/secret/URL tùy ý.

### 17.5. Test local và OP session độc lập

1. Login vào RP và OP.
2. Logout local RP nhưng chưa gọi OP.
3. Xác nhận RP local session không còn.
4. Mở RP thứ hai; nếu OP session còn, OP có thể SSO.
5. Thực hiện RP-Initiated Logout.
6. Xác nhận OP session kết thúc sau khi user đồng ý.
7. Kiểm tra logout notifications tới RP thứ hai nếu đã cấu hình.
8. Kiểm tra access/refresh token theo revocation strategy riêng.

## 18. Vận hành và troubleshooting

### 18.1. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách kiểm tra |
| --- | --- | --- |
| OP trả 404 tại `/connect/logout` | OIDC chưa bật hoặc path khác | OIDC configurer/AuthorizationServerSettings |
| Discovery không có `end_session_endpoint` | OIDC discovery/logout chưa cấu hình | Provider Configuration endpoint |
| Không redirect về RP | URI chưa đăng ký hoặc mismatch | RegisteredClient.postLogoutRedirectUris |
| Client mismatch | client_id không khớp ID Token hint | Token audience/client registration |
| Hint expired bị từ chối | Session không được nhận diện hoặc behavior version | SAS version/session store |
| User vẫn login ở OP | Chỉ local logout hoặc user từ chối OP logout | OP session cookie/confirmation |
| State mismatch | State bị mất, đổi, hết hạn hoặc session khác | Correlation store/TTL/proxy |
| Redirect về host lạ | Open redirect validator yếu | Exact-match allowlist |
| RP handler không tìm endpoint | ClientRegistration thiếu discovery metadata | OIDC provider configuration |
| Nhiều node logout không đồng nhất | SessionRegistry local | Shared session/registry |
| GET token xuất hiện trong log | Query capture ở proxy/APM | Redaction hoặc POST |
| RP2 vẫn còn session | Chưa cấu hình front/back-channel notification | Logout registration |
| API vẫn nhận JWT sau logout | Logout không revoke JWT | Introspection/denylist/TTL |
| Handler redirect sai host | `{baseUrl}` dựng từ untrusted headers | Public base URL/forwarded headers |
| POST không hoạt động | Proxy/filter chỉ cho GET | Method routing/form serialization |

### 18.2. Runbook khi logout không quay về RP

1. Lấy `end_session_endpoint` từ OIDC metadata đúng issuer.
2. Kiểm tra Logout Endpoint bật và route public HTTPS.
3. Đọc request params ở dạng redacted.
4. Xác minh ID Token hint thuộc issuer/client đúng.
5. Kiểm tra client_id khớp ID Token nếu cả hai có.
6. Kiểm tra post_logout_redirect_uri exact-match RegisteredClient.
7. Kiểm tra OP có yêu cầu confirmation và user đã đồng ý chưa.
8. Kiểm tra OP notifications hoàn tất trước redirect.
9. Kiểm tra browser callback nhận state nguyên vẹn.
10. Kiểm tra RP state store, TTL và session binding.

Không khắc phục bằng wildcard URI hoặc tắt validator.

### 18.3. Metrics và audit

| Metric | Mục đích |
| --- | --- |
| Logout request count theo client | Biết client nào dùng logout |
| ID Token hint validation failures | Phát hiện issuer/client/session mismatch |
| client_id mismatch count | Phát hiện request sai/abuse |
| Redirect URI validation failures | Phát hiện open redirect attempts/cấu hình sai |
| Confirmation accepted/declined | Theo dõi OP logout UX |
| SessionRegistry lookup miss | Phát hiện stale session/cluster issue |
| RP callback state mismatch | Phát hiện correlation/CSRF problem |
| Front/back-channel notification failures | Theo dõi propagation |
| Logout endpoint 4xx/5xx | Availability/protocol issue |
| Access token still active after logout | Phân biệt logout và revocation |

Không log raw ID Token hint, state, session cookie hoặc access/refresh token. Audit có thể ghi client ID, correlation ID, redirect registration identifier và outcome đã được bảo vệ.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Gửi access token làm id_token_hint | OP không nhận diện đúng OIDC session | Dùng ID Token do OP cấp |
| Bỏ hint trong mọi request | OP khó xác định session; redirect cần xác minh khác | Gửi hint khi có |
| Tin client_id dù hint thuộc client khác | Client/session confusion | MUST kiểm tra client match |
| Dùng redirect_uri Authorization Code cho logout | Sai registration contract | Đăng ký post-logout URI riêng |
| Cho redirect URI tùy ý | Open redirect/phishing | Exact-match allowlist |
| Prefix-match domain | Host giả mạo vượt qua | So URI chính xác |
| Dùng state cố định | Callback forgery/replay | Random state, session-bound, one-time |
| Nghĩ OP ký state | RP không kiểm tra callback | RP tự verify state |
| Nghĩ logout OP tự revoke JWT | API vẫn nhận token local | Revocation/denylist/introspection |
| Nghĩ logout RP tự logout mọi RP | OP session vẫn còn | RP-Initiated + notification mechanisms |
| Từ chối mọi expired hint | Logout recent session có thể thất bại | Recent-session semantics |
| Log toàn bộ query logout | Lộ ID Token/state | Redaction/POST |
| Tắt CSRF local logout | Logout CSRF | Bảo vệ local logout endpoint |
| Không kiểm soát baseUrl | Redirect mismatch/host poisoning | Public base URL tin cậy |
| Chỉ test HTTP response | Không chứng minh session kết thúc | Test local/OP/SessionRegistry |
| Chỉ dùng in-memory registry trong cluster | Node khác không thấy session | Shared session/registry |
| Custom handler bỏ validator | Open redirect | Giữ validation và test |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `id_token_hint` là gì?  
**Đáp án:** ID Token trước đó OP cấp cho RP, dùng làm hint để OP nhận diện End-User/client/session cần logout.

**Câu 2.** Có thể dùng access token thay id_token_hint không?  
**Đáp án:** Không. RP-Initiated Logout định nghĩa ID Token hint; access token dùng authorization tới Resource Server.

**Câu 3.** ID Token hint đã hết hạn có luôn bị từ chối không?  
**Đáp án:** Không. OP SHOULD chấp nhận nếu aud/sid xác định current/recent session, ngay cả khi exp đã qua; OP vẫn xác minh issuer và session context.

**Câu 4.** Nếu có cả client_id và id_token_hint, điều kiện bắt buộc là gì?  
**Đáp án:** OP MUST xác minh client_id khớp client đã dùng khi phát hành ID Token.

**Câu 5.** post_logout_redirect_uri có được dùng wildcard không?  
**Đáp án:** Không theo cơ chế chuẩn; OP MUST exact-match URI đã đăng ký.

**Câu 6.** Không có ID Token hint nhưng có post-logout URI, OP có luôn redirect được không?  
**Đáp án:** Không. OP MUST có phương tiện khác xác nhận redirect target hợp pháp.

**Câu 7.** state do ai xác minh?  
**Đáp án:** RP tạo/lưu và kiểm tra callback state; OP echo lại nguyên giá trị.

**Câu 8.** OP phải hỗ trợ GET và POST không?  
**Đáp án:** Có. RP-Initiated Logout 1.0 yêu cầu OP MUST hỗ trợ cả hai.

**Câu 9.** Logout Endpoint có tự thu hồi access token JWT không?  
**Đáp án:** Không. Token revocation/introspection/denylist/TTL là cơ chế riêng.

**Câu 10.** SAS dùng thành phần nào để tra session logout?  
**Đáp án:** `OidcLogoutAuthenticationProvider` dùng `SessionRegistry` để tra `SessionInformation`.

**Câu 11.** Spring Security OAuth2 Client có handler nào hỗ trợ RP-Initiated Logout?  
**Đáp án:** `OidcClientInitiatedLogoutSuccessHandler`.

**Câu 12.** Vì sao không dùng redirect_uri cho post-logout callback?  
**Đáp án:** redirect_uri dành cho Authorization Response; post_logout_redirect_uri là registration/parameter riêng.

## 21. Checklist production

- [ ] OP công bố `end_session_endpoint` trong OIDC Provider metadata.
- [ ] Logout Endpoint dùng HTTPS và hỗ trợ GET + POST.
- [ ] RP lấy endpoint từ discovery đã xác minh issuer.
- [ ] RP gửi ID Token hint đúng OP/client khi có.
- [ ] OP xác minh ID Token hint do chính mình phát hành.
- [ ] OP xử lý expired hint theo current/recent session semantics.
- [ ] client_id khớp client phát hành ID Token nếu cả hai cùng có.
- [ ] post_logout_redirect_uri được đăng ký riêng cho client.
- [ ] OP exact-match URI, không wildcard/prefix-match.
- [ ] Không redirect khi URI validation thất bại.
- [ ] Khi thiếu hint, có phương tiện xác nhận redirect target hợp lệ.
- [ ] state random, session-bound, TTL ngắn và one-time.
- [ ] RP xác minh state callback trước khi hoàn tất.
- [ ] Local logout có CSRF protection.
- [ ] ID Token hint/state không bị ghi raw vào log.
- [ ] Có UX xử lý OP confirmation/decline.
- [ ] SessionRegistry hoạt động đúng trong multi-instance.
- [ ] Front/back-channel logout cấu hình nếu cần logout các RP khác.
- [ ] Token revocation thiết kế riêng nếu API cần ngừng nhận token sớm.
- [ ] Có tests cho hint issuer/expiry, client mismatch, redirect mismatch, state replay và session lookup.
- [ ] Có runbook và metrics cho logout propagation.

## 22. Tài liệu tham khảo và kết luận

- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [RP-Initiated Logout — Section 2: Logout Request Parameters](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#RPLogout)
- [RP-Initiated Logout — Section 2.1: OP Discovery Metadata](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#OPMetadata)
- [RP-Initiated Logout — Section 3: Redirection to RP After Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#Redirection)
- [RP-Initiated Logout — Section 4: Validation and Error Handling](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html#Validation)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OidcLogoutEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html)
- [Spring Authorization Server — OidcLogoutAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html)
- [Spring Authorization Server — RegisteredClient.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClient.Builder.html)
- [Spring Authorization Server — SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Security 6.4 — OidcClientInitiatedLogoutSuccessHandler API](https://docs.spring.io/spring-security/site/docs/6.4.8/api/org/springframework/security/oauth2/client/oidc/web/logout/OidcClientInitiatedLogoutSuccessHandler.html)

**Kết luận:** `id_token_hint` giúp OP xác định user/client/session; `client_id` bổ sung nhận diện client và MUST khớp ID Token hint nếu cả hai cùng xuất hiện; `post_logout_redirect_uri` là callback đã đăng ký và phải exact-match; `state` là giá trị opaque RP dùng kiểm tra tương quan callback. Khi triển khai với Spring Authorization Server, cần bật OIDC Logout Endpoint, đăng ký URI riêng trên RegisteredClient và duy trì SessionRegistry chính xác. RP có thể dùng `OidcClientInitiatedLogoutSuccessHandler` hoặc flow tương đương có kiểm tra state/redirect rõ ràng. Cuối cùng, phải tách local logout, OP session logout, logout notifications và OAuth2 token revocation để không tạo cảm giác đã logout hoàn toàn trong khi access/refresh token hoặc session của ứng dụng khác vẫn còn hiệu lực.

