# Phân biệt đăng xuất cục bộ, hết hạn token và thu hồi token tại nhà cung cấp danh tính

**Module:** Spring Security – reactive (Spring WebFlux)  
**Phần:** Phiên và đăng xuất  
**Phạm vi:** WebSession trong ứng dụng, OAuth 2.0 access/refresh token, OpenID Connect (OIDC), nhà cung cấp danh tính (*Identity Provider*, IdP), và sự phối hợp giữa chúng.

Khi người dùng bấm **Đăng xuất**, có ít nhất ba loại trạng thái có thể tồn tại độc lập:

1. **Phiên cục bộ của ứng dụng**: session cookie và `SecurityContext` cho website Spring WebFlux.
2. **Thời hạn hiệu lực của token**: `exp`/`nbf` trên JWT, hoặc trạng thái hết hạn do Authorization Server quản lý đối với opaque access token/refresh token.
3. **Trạng thái tại Identity Provider (IdP)**: phiên đăng nhập SSO, authorization grant, refresh token hoặc access token đã bị thu hồi, và tín hiệu đăng xuất OIDC tới các ứng dụng liên quan.

**Ba sự kiện này không tương đương.** Một ứng dụng có thể xóa session nhưng access token đã phát vẫn dùng được tại API cho đến khi hết hạn hoặc bị API từ chối theo chính sách; token hết hạn không tự làm người dùng “logout” khỏi trang có WebSession còn hợp lệ; và thu hồi refresh token tại IdP không chắc khiến một JWT access token đã phát bị từ chối ngay ở mọi resource server đang xác minh chữ ký offline.

Bài này đưa ra sơ đồ, bảng so sánh, code Java 17+ chạy được, cấu hình WebFlux và ma trận kiểm thử để người học không đánh đồng các lớp đăng xuất.

## 1. Phân loại đúng trước khi cấu hình

| Cơ chế/sự kiện | Ai quản lý trạng thái? | Ảnh hưởng trực tiếp | Những gì **không** tự động xảy ra |
| --- | --- | --- | --- |
| **Đăng xuất cục bộ** (*local logout*) | Ứng dụng Spring WebFlux; `ServerSecurityContextRepository`, `WebSession` | Xóa ngữ cảnh bảo mật của ứng dụng, có thể vô hiệu hóa WebSession/cookie tương ứng | Không mặc nhiên thu hồi access/refresh token tại IdP; không đóng phiên SSO của IdP; không logout mọi app |
| **Access token hết hạn** | Thời hạn đã phát hành + resource server kiểm tra token | API không nên chấp nhận token sau hiệu lực, lưu ý clock skew | Không tự xóa WebSession, refresh token, session SSO hoặc các access token khác |
| **Refresh token hết hạn/không còn dùng được** | Authorization Server/IdP + client giữ token | Không thể lấy access token mới bằng refresh token đó | Access token đã được phát có thể vẫn hợp lệ tới `exp` hoặc đến khi policy khác từ chối |
| **Thu hồi token** (*OAuth2 revocation*) | Authorization Server/IdP qua endpoint thu hồi (RFC 7009) | Vô hiệu hóa token/grant trong phạm vi provider hỗ trợ | Không bảo đảm JWT offline ở resource server lập tức nhận được tín hiệu; không đồng nghĩa browser session tại app đã xóa |
| **OIDC RP-Initiated Logout** | Ứng dụng (*Relying Party*, RP) và OpenID Provider (OP) | RP đưa user-agent tới `end_session_endpoint` của OP để kết thúc phiên OP theo luồng hỗ trợ | Không mặc định gọi RFC 7009 để thu hồi tất cả token; không chắc mọi RP khác được logout |
| **OIDC Back-Channel Logout** | OP gửi Logout Token qua kênh server-to-server tới RP | RP nhận và xác minh tín hiệu để kết thúc các session tương ứng | Không phải bearer access token revocation; cần IdP và RP hỗ trợ/cấu hình đúng |
| **Logout tất cả thiết bị** | Kiến trúc phối hợp IdP, nhiều app, session store, resource server | Có thể bao phủ nhiều session và grant theo chính sách đã thiết kế | Không có một nút/API Spring Security mặc định nào làm mọi bên đồng bộ tuyệt đối |

**Câu hỏi đầu tiên khi nhận yêu cầu “logout”:** Hệ thống phải chặn truy cập ở đâu và trong thời gian bao lâu? Chỉ cửa sổ trình duyệt hiện tại, mọi session của một người dùng, mọi client OAuth, refresh token, hay tất cả access token chưa hết hạn trên mọi API? Câu trả lời quyết định kỹ thuật và bộ test.

## 2. Kiến trúc nhiều bên: trình duyệt, ứng dụng, API và IdP

```text
   Browser / Mobile App                    Identity Provider (OP/AS)
  +---------------------+                  +--------------------------+
  |  Cookie SESSION     |<-- OIDC login -->| SSO browser session      |
  |  Access Token?      |                  | Authorization grants     |
  |  Refresh Token?     |                  | Revocation / introspect  |
  +----------+----------+                  +-------------+------------+
             |                                           |
             | HTTPS                                     | JWT keys / introspection
             v                                           v
  +---------------------+                  +--------------------------+
  | Spring WebFlux App  |--- API request ->| Resource Server / API    |
  | WebSession          |                  | JWT offline validation   |
  | SecurityContext     |                  | hoặc introspection       |
  | OAuth2 Client       |                  | kiểm tra scope/role      |
  +---------------------+                  +--------------------------+
```

Một triển khai có thể gộp nhiều vai trò vào một process, nhưng nên **tách tư duy**:

- **Ứng dụng website/RP** giữ session cục bộ để người dùng không phải chạy OAuth2/OIDC login trên mọi request UI.
- **Authorization Server/OP/IdP** phát, làm mới, thu hồi token và có thể giữ session SSO riêng trong browser.
- **Resource Server** kiểm tra access token để cho phép API, bằng xác minh JWT theo `iss`/`aud`/`exp`/signature hoặc introspection. Nó có thể **không biết** người dùng vừa logout tại một website khác.
- **Client OAuth2** giữ hoặc sử dụng access/refresh token theo quyền đã được cấp; cách client cất token là một quyết định kiến trúc riêng.

Trong Spring Security Reactive, `oauth2Login()` hỗ trợ **RP đăng nhập qua OP**, còn `oauth2ResourceServer()` hỗ trợ **API nhận Bearer access token**. Hai khái niệm không nên được đặt chung một sơ đồ “logout = xóa JWT khỏi session”.

### Ví dụ một tình huống gây hiểu nhầm

- 10:00: Alice mở website, OIDC login; web app tạo `WebSession A`. IdP cấp access JWT hết hạn lúc 10:15 và refresh token R.
- 10:05: Alice bấm Logout **chỉ tại web app**. `WebSession A` bị vô hiệu hóa.
- 10:06: Một chương trình khác đang giữ access JWT được cấp trước đó vẫn có thể gọi API nếu API xác minh JWT **offline** và chưa có kiểm tra revoke/denylist riêng.
- 10:07: Alice mở website lại; nếu phiên SSO tại OP còn sống, OIDC có thể giúp đăng nhập lại rất nhanh, thậm chí không cần nhập password.
- 10:08: Nếu IdP thu hồi refresh token R, client không thể lấy access token mới bằng R; nhưng JWT hiện hành có thể vẫn được chấp nhận tới hạn hoặc khi resource server có tín hiệu thu hồi.
- 10:15: JWT đã đến `exp` theo ví dụ; resource server phải từ chối ngoài mức dung sai thời gian cấu hình.

Mốc thời gian ở đây là ví dụ, không phải độ trễ bảo đảm. **Cần test độc lập** trạng thái website, IdP, refresh endpoint và API.

## 3. Local logout trong Spring Security WebFlux

### 3.1. Mặc định làm gì?

Trong mô hình form login/WebSession, Spring Security Reactive cung cấp endpoint logout:

- `GET /logout` thường hiển thị trang xác nhận đăng xuất, **không** mặc nhiên thực thi logout khi CSRF được bật.
- `POST /logout` có **CSRF token** phù hợp sẽ kích hoạt `LogoutWebFilter`. Spring Security xử lý dọn `SecurityContext` và CSRF state theo cấu hình, rồi thường redirect về trang đăng nhập.
- Muốn chắc chắn **vô hiệu hóa cả WebSession đang hoạt động**, cấu hình `WebSessionServerLogoutHandler` cùng `SecurityContextServerLogoutHandler` qua `DelegatingServerLogoutHandler`.

Tài liệu WebFlux nhấn mạnh điều cuối: xóa security context và vô hiệu hóa **toàn bộ session** là hai hành động nên xem xét riêng; đừng mặc định logout luôn thực hiện mọi biện pháp tùy chỉnh mà ứng dụng mong đợi.

### 3.2. Chuỗi xử lý local logout

```text
Browser đã login: Cookie SESSION=abc
        |
        | POST /logout + valid _csrf
        v
Spring Security LogoutWebFilter
        |
        +-- SecurityContextServerLogoutHandler
        |     dọn SecurityContext tại ServerSecurityContextRepository
        |
        +-- WebSessionServerLogoutHandler
        |     vô hiệu hóa WebSession hiện tại
        |
        +-- ServerLogoutSuccessHandler
              redirect /login?logout (hoặc đích tùy biến)
        |
        v
Browser GET /private/me bằng cookie cũ
        |
        v
Không còn Authentication trong session -> redirect login / yêu cầu xác thực
```

Đây là **đăng xuất cục bộ**. Nó không gửi một request HTTP nào tới `/revoke` của IdP trừ khi bạn chủ động thêm quy trình OAuth2, và không thể “xóa” access token đang nằm ở một thiết bị khác.

### 3.3. Cookie và CSRF

Đăng xuất là thao tác thay đổi trạng thái. Nếu cho phép `GET /logout` thực hiện logout và không có bảo vệ, một trang ngoài có thể dùng image/link để ép browser logout; Spring Security WebFlux mặc định xử lý logout thực sự qua POST khi CSRF được bật. Không disable CSRF chỉ để chạy được lệnh curl đơn giản.

Cookie `SESSION` là một credential: cần HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp và chính sách domain/path đúng; xử lý session fixation, timeout, session store và logout trên nhiều instance. Xóa cookie phía client không nhất thiết xóa dữ liệu session ở backend nếu session store vẫn còn; vô hiệu hóa session là biện pháp phía server đáng tin hơn. Ngược lại, invalidating WebSession không xóa bản sao dữ liệu do frontend cố ý giữ trong localStorage/IndexedDB.

**Logout một phiên khác Logout mọi phiên:** Nếu Alice đăng nhập từ Chrome và điện thoại, xử lý `POST /logout` trong Chrome thường chỉ vô hiệu hóa session của Chrome. Muốn “đăng xuất khỏi mọi thiết bị”, ứng dụng cần lưu/chỉ mục session theo user và có cơ chế invalidation/reauth riêng, hoặc phối hợp với IdP và các client liên quan.

## 4. Access token hết hạn: hết quyền gọi API, không phải “đã logout browser”

### 4.1. JWT có các mốc thời gian

JWT access token thường có:

- `iat`: thời điểm phát hành, hữu ích cho chính sách nhưng **không** đủ để xác minh token;
- `nbf`: token chưa có hiệu lực trước thời điểm này;
- `exp`: token hết hạn sau thời điểm này;
- `iss`: issuer được tin cậy;
- `aud`: tài nguyên/đối tượng nhận token phù hợp;
- `sub`: chủ thể; `scope`/`scp` hoặc claims quyền theo chính sách.

Resource server phải kiểm tra **chữ ký, thuật toán, issuer, audience, thời gian** và policy quyền. Đừng chỉ decode payload Base64 rồi nhìn `exp` mà coi là xác minh bảo mật. Spring Security WebFlux có `oauth2ResourceServer(oauth -> oauth.jwt(...))` và `ReactiveJwtDecoder` cho việc này.

**Tình huống:** Nếu API kiểm JWT đã ký *offline* dựa trên JWKS/public key, việc IdP đổi trạng thái revoke trong database của mình không tự thay đổi chữ ký/claim của JWT đã phát. API có thể tiếp tục chấp nhận token đó tới `exp` (cộng mức dung sai clock skew nếu được cấu hình), trừ khi nó kiểm trạng thái thu hồi qua introspection/denylist/phiên bản token hoặc phương thức khác.

### 4.2. Clock skew không phải “gia hạn phiên” theo ý người dùng

Đồng hồ server có thể chênh nhau. Spring Security hỗ trợ `JwtTimestampValidator` và dung sai `clockSkew` để giảm 401 sai tại ranh giới `exp`/`nbf`. Nhưng dung sai làm tăng cửa sổ chấp nhận quanh thời điểm kết thúc: phải đặt theo yêu cầu và đồng bộ NTP, không mặc định token sẽ bị chặn **đúng từng mili-giây** sau con số `exp` ở mọi hệ thống.

Nếu client nhận `401 invalid_token` khi access token hết hạn, OAuth2 client có thể dùng **refresh token còn hợp lệ** để xin access token mới, rồi thử lại request theo policy. Điều đó **không có nghĩa logout thất bại** nếu session người dùng đã được thiết kế là còn hoạt động; đó là vòng đời token. Tuy nhiên, nếu sản phẩm yêu cầu “logout = không thể lấy access token mới”, phải chặn cả quyền refresh.

### 4.3. Refresh token và access token khác nhau

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Trình cho resource server để gọi API | Trình cho Authorization Server để xin access token mới |
| Nơi sử dụng | HTTP `Authorization: Bearer ...` tại API | `token_endpoint` theo flow phù hợp |
| Độ dài hiệu lực | Thường tương đối ngắn theo policy | Thường dài hơn nhưng có expiry, rotation, revoke, inactivity policy |
| Hệ quả khi hết hạn | API từ chối access token cũ; có thể refresh | Không thể dùng refresh token ấy để lấy token mới |
| Hệ quả khi bị thu hồi | Phụ thuộc khả năng API kiểm revoke | Thường chặn cấp token mới bằng refresh token đã bị revoke |
| Lưu trữ | Bảo vệ nghiêm ngặt, giảm exposure | Bảo vệ nghiêm ngặt hơn; không ghi log hoặc lưu trong JS nếu kiến trúc tránh được |

**Refresh-token rotation** tạo refresh token mới khi sử dụng và có thể vô hiệu hóa token cũ; token reuse detection là chính sách của IdP. Không gửi refresh token tới resource server; không dùng ID token (OIDC) thay cho access token để gọi API. `id_token` xác nhận phiên đăng nhập OIDC cho client trong ngữ cảnh phù hợp, có hạn riêng; hết `id_token` không đồng nghĩa mọi ứng dụng vừa logout.

## 5. Revocation tại IdP: RFC 7009 và phạm vi tác động

OAuth 2.0 Token Revocation (RFC 7009) quy định endpoint ở Authorization Server để **client yêu cầu vô hiệu hóa token**. Ví dụ cấu trúc yêu cầu (URL, token và client credentials đều là giả):

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.invalid
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token>&token_type_hint=refresh_token
```

Phải dùng HTTPS ngoài môi trường local. Gọi thật bằng client đã được IdP cấp quyền và xác thực theo cơ chế yêu cầu. Không dùng `curl -u client:secret` của production ở shell history hay gắn token thật trong tutorial.

Theo RFC 7009:

- Authorization Server **MUST** hỗ trợ revocation refresh token và **SHOULD** hỗ trợ access token revocation.
- Request revocation thành công có thể vô hiệu hóa token được chỉ định và các token/grant liên quan theo policy IdP; có sự khác nhau giữa revoke access token và revoke refresh token.
- Endpoint thường trả **HTTP 200 ngay cả khi token không tồn tại/đã bị thu hồi**, để tránh tiết lộ token có tồn tại không. Vì vậy response 200 **không chứng minh** tất cả resource server đã từ chối token.
- Có thể có độ trễ lan truyền trạng thái thu hồi giữa các server. Cần test tại resource server thực với SLA nhất quán phù hợp.

### 5.1. Thu hồi refresh token khác thu hồi access token

Giả sử client có refresh token R và access JWT A, cả hai đang hợp lệ:

- Khi **revoke R**: client không thể dùng R để lấy access token mới. Theo chính sách nhà cung cấp, các access token dựa trên cùng grant **có thể** cũng bị vô hiệu hóa phía IdP.
- Khi **revoke A**: IdP ghi nhận A bị thu hồi nếu cơ chế hỗ trợ; chính sách có thể đồng thời revoke refresh token liên quan.
- Nếu API kiểm JWT A **offline** mà không hỏi trạng thái revocation, API có thể vẫn chấp nhận A trong thời hạn được ký. Đây là một **giới hạn thực thi ở resource server**, không phải “RFC 7009 vô dụng”.
- Nếu API kiểm **introspection trên mỗi request** và IdP trả `active=false`, API sẽ từ chối A theo kết quả introspection (lưu ý cache, mạng và SLA).

Vì vậy phải nêu rõ yêu cầu bảo mật: “Không cấp token mới” hay “không chấp nhận token đã cấp ngay lập tức”. Hai yêu cầu có mức chi phí, độ trễ và cơ chế khác nhau.

### 5.2. Introspection theo RFC 7662 và revoke

Resource Server có thể gọi introspection endpoint (RFC 7662) để hỏi token còn `active` hay không. Spring Security WebFlux hỗ trợ opaque token qua `ReactiveOpaqueTokenIntrospector`; tên “opaque” nói về **cách xác minh bằng introspection**, không nhất thiết bắt buộc chuỗi token phải không có cấu trúc JWT. Resource Server có thể chuyển cả JWT tới IdP để introspect nếu provider hỗ trợ và policy yêu cầu cập nhật revocation.

Ưu/nhược điểm:

| Phương án kiểm token | Điểm mạnh | Rủi ro/chi phí |
| --- | --- | --- |
| Xác minh JWT chữ ký offline | Độ trễ thấp, ít phụ thuộc IdP khi phục vụ request | Không biết revoke ngay nếu không có kênh bổ sung |
| Introspection theo request | Có thể thấy trạng thái `active=false` gần thời gian thực | Thêm latency, tải lên IdP, phụ thuộc network; cache kết quả tạo cửa sổ trễ |
| JWT + denylist `jti` hoặc session/token version | Có thể chặn token cụ thể theo policy | Cần kho trạng thái chung, TTL đúng và kiểm tra nhất quán |
| Access token rất ngắn hạn + refresh rotation/revoke | Giới hạn cửa sổ lộ token | Nhiều round trip refresh; không có chặn tuyệt đối ngay lập tức |
| Push event/revocation notification đến resource servers | Có thể giảm độ trễ revoke nếu tích hợp tốt | Cần xử lý mất event, race, retries, cache invalidation và fallback |

**Không cache introspection `active=true` vô hạn.** Một cache TTL dài có thể biến “thu hồi ngay” thành “còn hiệu lực tới khi cache hết hạn”. Đồng thời không tự động `permitAll` khi introspection server lỗi: quyết định *fail closed* dựa trên risk model, phản hồi lỗi phù hợp và giám sát, không bỏ kiểm token.

## 6. Đăng xuất OIDC tại IdP khác thu hồi OAuth token

### 6.1. RP-Initiated Logout: trình duyệt được chuyển đến OP

Trong OpenID Connect, RP (ứng dụng web) có thể yêu cầu OP kết thúc phiên đăng nhập thông qua **end-session endpoint** nếu OP hỗ trợ. Khi cấu hình `oauth2Login()` và logout handler phù hợp, ứng dụng sẽ chuyển browser tới OP; OP xử lý logout theo chính sách của mình, sau đó có thể đưa browser về `post_logout_redirect_uri` được cấp phép.

**Điểm rất dễ nhầm:** Redirect logout OIDC tới OP **không phải** request RFC 7009 revoke token, và cũng không bảo đảm tất cả JWT access token đã cấp lập tức vô hiệu ở mọi API. Nó nhằm xử lý **phiên đăng nhập phía OP** và trải nghiệm SSO.

Trong Spring Security Reactive, class thích hợp là:

```java
OidcClientInitiatedServerLogoutSuccessHandler
```

Chú ý hậu tố **`Server`** của WebFlux. Tên `OidcClientInitiatedLogoutSuccessHandler` không có Server thuộc **Servlet**. Trong WebFlux, handler thường lấy `end_session_endpoint` từ OIDC discovery metadata của `issuer-uri`, với `ReactiveClientRegistrationRepository` và client registration phù hợp.

**Fragment cấu hình WebFlux (cần các bean/properties OAuth2 Client thật, không độc lập chạy được):**

```java
@Bean
SecurityWebFilterChain oidcChain(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository registrations) {

    var oidcLogout =
        new OidcClientInitiatedServerLogoutSuccessHandler(registrations);
    oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/signed-out").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
        .build();
}
```

Cần import `OidcClientInitiatedServerLogoutSuccessHandler` từ package `org.springframework.security.oauth2.client.oidc.web.server.logout`, `ReactiveClientRegistrationRepository`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer` và `@Bean`. Đoạn code giả định IdP cung cấp discovery và có end-session endpoint; `post_logout_redirect_uri` phải được OP cho phép. Trong hệ thống sau proxy, xác định `{baseUrl}` đúng scheme/host/path và chỉ tin forwarded headers từ proxy đáng tin cậy, nếu không sẽ có redirect sai hoặc nguy cơ open redirect.

Để chạy OAuth2 Client thực, cần `spring-boot-starter-oauth2-client`, client id/secret hoặc PKCE theo loại client và issuer URI **thật**; đó là hệ thống nhiều bên, không thể chạy chỉ bằng config fragment trên mà không có IdP. Bài thực hành độc lập ở phần 8 chỉ dùng local form login để không đòi tài khoản/secret bên ngoài.

### 6.2. Back-Channel Logout: OP chủ động báo RP

Nếu OP cần báo các RP rằng user đã logout ở OP hoặc một ứng dụng khác, OIDC **Back-Channel Logout** cho phép OP gửi Logout Token tới một endpoint của RP qua server-to-server. RP phải:

1. Xác minh chữ ký và các claims bắt buộc của **Logout Token** (không nhầm với access token); kiểm tra issuer, audience, thời gian, event và token replay theo tiêu chuẩn.
2. Tìm những session cục bộ tương ứng với `sid` hoặc `sub`/client.
3. Vô hiệu hóa đúng session theo chính sách, phân biệt một phiên OP với mọi phiên của một người dùng.
4. Bảo đảm cookie/session registry và việc đồng bộ nhiều instance hoạt động.

Spring Security Reactive có hỗ trợ OIDC back-channel theo phiên bản, thông qua `oidcLogout(...).backChannel(...)` và cơ chế `ReactiveOidcSessionRegistry`. Tuy nhiên **phải kiểm tra Spring Security version thực tế và tên cookie**: tài liệu Spring nêu ràng buộc ở một số cấu hình back-channel với `JSESSIONID` trong khi Spring Session có thể dùng `SESSION`, cần chỉnh handler/cấu hình tương ứng. **Không mặc định** chỉ bật `oauth2Login()` là mọi RP sẽ được IdP logout tự động.

Back-channel logout và front-channel/browser redirect khác nhau về kênh truyền, độ tin cậy, khả năng hoạt động khi browser đóng, và việc phối hợp giữa RP/OP. Cả hai khác hoàn toàn với RFC 7009 revocation access/refresh token.

## 7. Minh họa Java 17 độc lập: ba trục thời gian tách biệt

Để hiểu kết quả một cách *deterministic*, ta mô phỏng local session, access JWT offline và refresh token tại IdP bằng biến riêng. Đây **không** phải library token validation thật: mô phỏng bỏ qua chữ ký/issuer/audience và không nên dùng ra quyết định bảo mật.

Lưu `LogoutAxesDemo.java`:

```java
import java.time.Instant;

public class LogoutAxesDemo {
    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T10:00:00Z");
        Instant expiresAt = issuedAt.plusSeconds(900);

        boolean localSessionActive = true;
        boolean refreshTokenActiveAtIdp = true;

        Instant t1 = issuedAt.plusSeconds(300);
        localSessionActive = false; // Người dùng logout tại website

        System.out.println("local-session-active=" + localSessionActive);
        System.out.println("jwt-time-valid-after-local-logout="
            + t1.isBefore(expiresAt));

        refreshTokenActiveAtIdp = false; // IdP revoke refresh token
        System.out.println("can-refresh=" + refreshTokenActiveAtIdp);
        System.out.println("jwt-time-valid-after-refresh-revocation="
            + t1.isBefore(expiresAt));

        Instant t2 = expiresAt.plusSeconds(1);
        System.out.println("jwt-time-valid-after-exp="
            + t2.isBefore(expiresAt));
    }
}
```

Chạy:

```bash
javac LogoutAxesDemo.java
java LogoutAxesDemo
```

Stdout **chính xác**:

```text
local-session-active=false
jwt-time-valid-after-local-logout=true
can-refresh=false
jwt-time-valid-after-refresh-revocation=true
jwt-time-valid-after-exp=false
```

Giải thích: sau khi xóa WebSession, điều kiện thời gian của JWT **chưa thay đổi**; sau revoke refresh token, điều kiện thời gian của JWT đã phát **vẫn chưa thay đổi**; sau `exp` thì điều kiện thời gian không còn hợp lệ. Trong resource server thật, JWT còn phải qua signature, issuer/audience, `nbf`, quyền, denylist/introspection và clock skew. Đừng dùng `Instant.isBefore(exp)` của demo để “xác thực JWT”; nó chỉ minh họa sự độc lập giữa ba trục.

## 8. Ứng dụng Spring Boot WebFlux chạy được: local logout đúng cách

Ứng dụng mẫu tập trung vào **lớp cục bộ**; IdP và JWT ở phần 9 là cấu hình/kiến trúc riêng vì cần Authorization Server thật. Nhờ vậy, người học có thể chạy đủ vòng đời session mà không giả lập việc đã thu hồi token bên ngoài.

### 8.1. Cấu trúc dự án

```text
reactive-local-logout/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/logout/
    │   │   ├── LocalLogoutApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── PageController.java
    │   └── resources/application.properties
    └── test/java/demo/logout/
        └── LocalLogoutTests.java
```

Dùng **Java 17+**, Maven 3.9+, Spring Boot `3.5.7` trong ví dụ. Phiên bản là mốc xây bài thực hành, không phải yêu cầu production phải ghim bản đó; thực tế hãy chọn bản vá còn hỗ trợ.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-local-logout</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Đừng thêm `spring-boot-starter-web` (Servlet MVC) khi bài yêu cầu WebFlux; hai starter trong cùng project có thể làm Boot chọn Servlet stack. Local logout trong ví dụ dùng **SecurityWebFilterChain**, không dùng `HttpSecurity` của Servlet.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-local-logout
server.port=8080
```

### 8.2. Main class

`src/main/java/demo/logout/LocalLogoutApplication.java`:

```java
package demo.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocalLogoutApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: dọn SecurityContext và invalidate WebSession

`src/main/java/demo/logout/SecurityConfig.java`:

```java
package demo.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .roles("USER").build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var logoutHandlers = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler()
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/goodbye").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/private/me").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.logoutHandler(logoutHandlers))
            .build();
    }
}
```

Điểm cần nhớ:

- `formLogin(...)` tạo trang đăng nhập mặc định `GET /login` và xử lý `POST /login`; đây là **phiên cục bộ** dựa trên WebSession, không phải OIDC logout.
- `SecurityContextServerLogoutHandler` xóa ngữ cảnh đã lưu qua security context repository.
- `WebSessionServerLogoutHandler` vô hiệu hóa WebSession hiện tại; khi dùng chung với handler trên, chúng giải quyết cả dữ liệu bảo mật lẫn session.
- `httpBasic(...disable())` để browser nhận redirect login form thay vì HTTP Basic challenge, làm demo session rõ hơn.
- `PasswordEncoderFactories` hash password demo trước khi đưa vào memory store; không dùng `{noop}` cho user thật. Không hard-code tài khoản production.
- **Không** tắt CSRF. WebFlux mặc định yêu cầu token hợp lệ khi gửi `POST /login` và `POST /logout` trong kiểu ứng dụng dùng cookie/session.
- `anyExchange().denyAll()` ngăn các route chưa khai báo bị mở vô tình. Nếu có API Bearer, nên tách chain/matcher và quy tắc session phù hợp, không copy config form login sang toàn bộ API.

### 8.4. Controller

`src/main/java/demo/logout/PageController.java`:

```java
package demo.logout;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(value = "/goodbye", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> goodbye() {
        return Mono.just("goodbye");
    }

    @GetMapping(value = "/private/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> privateMe() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "signed-in:" + name);
    }
}
```

Mọi request `/private/me` đều dùng `Authentication` của subscription hiện tại. Không dùng biến `static currentUser` vì nhiều người dùng có thể gọi đồng thời. Không có route kiểm JWT hoặc gọi IdP trong demo: đây là **điểm cố ý** giúp chứng minh local logout không đồng nghĩa tác động lên token ngoài ứng dụng.

## 9. Chạy và kiểm tra local logout từ trình duyệt

Từ thư mục project:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Đợi Netty khởi động trên 8080. Trong cửa sổ trình duyệt ẩn danh mới:

1. Mở `http://localhost:8080/private/me`; vì chưa đăng nhập nên browser chuyển sang `/login`.
2. Nhập `alice / alice123` trên form mặc định. Sau login thành công, trang protected trả `signed-in:alice`; mở DevTools/Network xem chuỗi redirect và `SESSION` cookie.
3. Mở `http://localhost:8080/logout` bằng GET: đây là trang xác nhận logout, không phải thao tác logout ngay khi CSRF bật. Khi vẫn ở trang xác nhận, thử mở tab khác vào `/private/me`; phiên vẫn được xác thực.
4. Xác nhận logout bằng form POST chứa hidden CSRF token do Spring Security cung cấp. Ứng dụng sẽ dọn ngữ cảnh và invalidate WebSession.
5. Mở lại `/private/me` bằng cookie cũ/tab cũ; phải yêu cầu login lại, không trả `signed-in:alice`.
6. Trong một browser/profile khác, đăng nhập Bob; thao tác logout của Alice **không được** kết thúc phiên Bob, vì local logout chỉ ảnh hưởng session hiện tại.

Nếu bước 5 vẫn thấy tên Alice, kiểm tra liệu một IdP SSO hoặc login automation đang **đăng nhập lại tự động** hay bạn thực sự đang dùng session cũ còn hiệu lực. Đối với app demo local form login, không có IdP nên cần đối chiếu cookie và SecurityContext, không chỉ xem URL.

Trong môi trường production hãy dùng HTTPS, session store phù hợp nếu có nhiều instance, và dọn cookie/CSRF state theo chính sách. Đừng “sửa” logout bằng `GET /logout` đổi thành side effect không có CSRF.

## 10. WebTestClient kiểm chứng local logout và hai phiên độc lập

Một test chỉ thấy redirect sau `POST /logout` chưa đủ: cần **gọi lại resource protected bằng cookie cũ** và thấy không còn quyền. Đồng thời đảm bảo đăng xuất một session **không** làm mất session của người khác.

Ví dụ test bên dưới dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`: Spring tạo server HTTP thật trên cổng ngẫu nhiên, và `WebTestClient` gửi credential/cookie như browser thực. Vì trang login/logout được Spring Security sinh, test lấy hidden `_csrf` từ HTML form. Đây là cách để test đúng cơ chế CSRF, không bỏ qua nó.

`src/test/java/demo/logout/LocalLogoutTests.java`:

```java
package demo.logout;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LocalLogoutTests {

    @Autowired
    WebTestClient client;

    private static String updatedSessionCookie(
            EntityExchangeResult<?> response, String earlier) {
        ResponseCookie cookie = response.getResponseCookies()
            .getFirst("SESSION");
        return cookie != null ? cookie.getValue() : earlier;
    }

    private static String csrfToken(String html) {
        assertNotNull(html, "Missing HTML form");
        Matcher tag = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>")
            .matcher(html);
        assertTrue(tag.find(), "No hidden _csrf field");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "No CSRF token value");
        return value.group(1);
    }

    private String signIn(String username, String password) {
        EntityExchangeResult<String> loginPage =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String cookie = updatedSessionCookie(loginPage, null);
        assertNotNull(cookie, "No login WebSession cookie");
        String csrf = csrfToken(loginPage.getResponseBody());

        EntityExchangeResult<byte[]> loggedIn =
            client.post().uri("/login")
                .cookie("SESSION", cookie)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", username)
                    .with("password", password)
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = loggedIn.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        // Login thành công -> trang chủ hoặc URL protected đã lưu.
        assertTrue(!location.contains("error"), "Login failed");
        return updatedSessionCookie(loggedIn, cookie);
    }

    @Test
    void anonymousVisitorIsRedirectedToLogin() {
        client.get().uri("/private/me")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void formLoginCreatesUsableLocalSession() {
        String alice = signIn("alice", "alice123");
        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void getLogoutIsOnlyAConfirmationPage() {
        String alice = signIn("alice", "alice123");

        client.get().uri("/logout")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void postLogoutWithoutCsrfIsRejected() {
        String alice = signIn("alice", "alice123");

        client.post().uri("/logout")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void logoutInvalidatesOnlyCurrentSession() {
        String alice = signIn("alice", "alice123");
        String bob = signIn("bob", "bob123");

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");

        client.get().uri("/private/me")
            .cookie("SESSION", bob)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:bob");

        // Lấy form xác nhận logout với chính WebSession của Alice.
        EntityExchangeResult<String> confirmation =
            client.get().uri("/logout")
                .cookie("SESSION", alice)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        alice = updatedSessionCookie(confirmation, alice);
        String token = csrfToken(confirmation.getResponseBody());

        client.post().uri("/logout")
            .cookie("SESSION", alice)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("_csrf", token))
            .exchange()
            .expectStatus().is3xxRedirection();

        // Cookie/session cũ của Alice không được dùng truy cập lại.
        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));

        // Phiên Bob độc lập vẫn còn hợp lệ.
        client.get().uri("/private/me")
            .cookie("SESSION", bob)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:bob");
    }
}
```

Chạy:

```bash
mvn test
```

Với class bên trên, kỳ vọng **5 bài test** có thể pass nếu môi trường, phiên bản và cookie name đúng như ví dụ. Đây là mã mẫu để người đọc tự chạy, **không phải xác nhận đã chạy trên dự án thật**. Thời gian Maven, log và session ID là dữ liệu không cố định.

**Giới hạn test HTML:** Regex chỉ là công cụ lấy hidden token trên trang generated trong demo, không phải parser HTML production; nếu dùng trang login tùy chỉnh, cần đổi cách trích token phù hợp. Nếu chính sách đặt tên session cookie không phải `SESSION`, cần cập nhật test và ứng dụng tương ứng. Test không chứng minh revoke JWT/refresh token ở IdP vì demo **không có IdP**.

### 10.1. Tiêu chí thực sự đạt local logout

- Trước logout, protected endpoint trả body gắn với user đúng.
- GET logout chỉ hiển thị confirmation, không làm mất quyền.
- POST logout **không có CSRF** bị từ chối và session vẫn được dùng được.
- POST logout **có CSRF** thành công.
- Request protected sau logout dùng lại cookie cũ không còn được xác thực.
- Một browser/session độc lập không bị ảnh hưởng.

Chỉ xóa cookie ở browser và thấy UI biến mất **không** chứng minh security context đã được vô hiệu hóa phía server.

## 11. Cấu hình minh họa cho Resource Server kiểm token

Đây là **hai phương án thay thế** cho resource server, không phải hai đoạn code cần bật đồng thời trong ứng dụng local form-login ở phần 8.

### 11.1. JWT được xác minh offline

Nếu resource server nhận JWT:

```java
@Bean
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Cấu hình issuer ví dụ:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.invalid/issuer
```

Đây là fragment phụ thuộc `spring-boot-starter-oauth2-resource-server`, issuer thực và key/discovery hợp lệ. Spring Security dùng `ReactiveJwtDecoder` để kiểm chữ ký/`iss`/`exp`/`nbf`; cần xác nhận `aud` và scope/role theo API cụ thể. Khi IdP revoke refresh token, đừng mặc định decoder JWT offline biết về việc đó.

### 11.2. Opaque token / introspection

Nếu API cần hỏi IdP về trạng thái mỗi token:

```java
@Bean
SecurityWebFilterChain introspectingApi(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

Ví dụ properties cần cấu hình ở resource server **riêng**:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.invalid/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_WITH_SECRET_FROM_VAULT
```

Các host/secret trên là **minh họa không hoạt động**; đừng copy và coi là ứng dụng runnable không cần IdP. Production dùng secret manager/biến môi trường và HTTPS; không commit client secret vào git. Resource Server thông thường dựa vào `ReactiveOpaqueTokenIntrospector` để gọi introspection và ánh xạ scope thành authority. Nếu IdP trả `active=false`, request Bearer tương ứng phải bị từ chối. Trong hệ thống thực còn cần benchmark latency, timeout/retry policy, cache TTL và giới hạn tải lên IdP.

**Không suy ra:** “Đã bật `opaqueToken()` thì logout cục bộ sẽ thu hồi token.” API introspection là **bước kiểm token ở resource server**, còn revocation là **tác vụ ghi trạng thái tại authorization server**; chúng phải được nối với nhau bằng kiến trúc.

## 12. Ma trận kiểm chứng xuyên hệ thống

Để chứng minh ba loại “logout” thực sự khác nhau, test nên giữ **bốn biến quan sát**: session của ứng dụng, access token ở API, refresh grant ở IdP và phiên đăng nhập SSO của IdP.

| Kịch bản | Session tại web app | Access token tại API | Refresh token tại IdP | OP/SSO session |
| --- | --- | --- | --- | --- |
| Người dùng login bình thường | Có | Có thể còn hiệu lực | Có thể dùng | Có, nếu login qua OIDC |
| **Chỉ local logout** | Không còn (phiên được chọn) | Có thể vẫn dùng được | Có thể vẫn dùng được | Có thể vẫn còn |
| Access JWT đến `exp` | Không tự đổi | Bị từ chối sau hết hạn theo validator/dung sai | Có thể vẫn dùng | Không tự đổi |
| Refresh token bị revoke | Không tự đổi | JWT offline đã phát có thể vẫn dùng đến hạn | Không thể refresh bằng token đã revoke | Không tự đổi |
| RP-Initiated OIDC logout | RP local logout theo flow | Không bảo đảm invalidate mọi access token | Phụ thuộc provider/chính sách | OP xử lý logout |
| OIDC Back-Channel Logout đến RP | RP hủy các session được chỉ định | Không tự sửa JWT trên mọi API | Không tự động nghĩa là revoke | OP đã khởi tạo event |
| Revoke + introspection `active=false` | Không tự đổi | API từ chối token được introspect theo policy | Phụ thuộc grant/token | Không tự đổi |
| “Logout mọi nơi” được thiết kế riêng | Phải hủy các session được quản lý | Cần chặn mọi token theo policy | Cần revoke grants/refresh | Cần logout OP/SSO và phối hợp RP |

Bảng dùng các từ **“có thể” / “phụ thuộc”** một cách có chủ ý: các giao thức không tự bảo đảm tính đồng bộ tuyệt đối giữa những hệ thống độc lập.

### 12.1. Bộ test tối thiểu khi có IdP thật

1. **Local:** Login bằng OIDC, lấy cookie session; POST logout đúng CSRF; truy cập trang protected bằng cookie cũ phải bị từ chối.
2. **SSO:** Sau local logout, thử bắt đầu OIDC login lại và quan sát IdP có hỏi credential hay dùng SSO session còn tồn tại. Đây là test **trạng thái OP**, không phải test token expiry.
3. **Access token:** Giữ một token trước logout, gọi API thật trước/sau local logout; ghi rõ việc vẫn được chấp nhận có phù hợp thiết kế hay không.
4. **Expiration:** Tạo token TTL test ngắn, gọi API sau `exp` và sau clock skew cho phép; kiểm tra 401/`invalid_token`, không chỉ nhìn thời gian trong payload.
5. **Refresh:** Dùng refresh token cũ trước và sau revoke; sau revoke không được cấp access token mới bằng token ấy. Nếu dùng rotation, test reuse detection.
6. **RFC 7009:** Gọi revocation endpoint của provider bằng client xác thực phù hợp; không coi HTTP 200 là đủ; kiểm tra introspection/refresh endpoint/API sau đó.
7. **OIDC RP-initiated:** Test `end_session_endpoint`, `post_logout_redirect_uri` allowlist và trường hợp OP không hỗ trợ logout.
8. **OIDC back-channel:** Gửi Logout Token **được OP ký hợp lệ** qua test provider, kiểm chứng session tương ứng bị hủy; token giả/sai `aud`/`sid`/replay phải bị từ chối.
9. **Hai thiết bị/ba app:** Xác minh session của app khác bị kết thúc **chỉ khi chính sách hứa hẹn**; không giả định local logout tự logout toàn mạng.
10. **Sự cố IdP:** Kiểm tra revocation/introspection timeout, error và cache: fail-closed/khả dụng theo risk model, không tự mở API khi IdP lỗi.

Đối với hệ thống phân tán, ghi nhận propagation latency (P50/P95/P99 nếu có SLA) và cửa sổ rủi ro tối đa. **“Ngay lập tức”** là mục tiêu cần đo và thiết kế cụ thể, không phải tính chất miễn phí của nút Logout.

## 13. Những lỗi thường gặp

### 13.1. Chỉ xóa cookie mà không invalidating session phía server

Nếu frontend xóa cookie nhưng backend vẫn giữ session ID hợp lệ, một bản sao cookie bị đánh cắp có thể tiếp tục được sử dụng trong cửa sổ sống của session. Hãy vô hiệu hóa server-side WebSession/SecurityContext và xử lý cookie/CSRF theo policy; đừng coi chuyển route về `/login` là chứng cứ đã logout.

### 13.2. Chỉ gọi `SecurityContextHolder.clearContext()` theo mô hình Servlet

WebFlux dùng `ReactiveSecurityContextHolder` và `ServerSecurityContextRepository` theo pipeline, không dựa vào ThreadLocal cục bộ. Dùng `LogoutWebFilter`/`ServerLogoutHandler` phù hợp và test qua HTTP; không tự gọi clear trong controller mà quên lưu/truyền thay đổi cho request kế tiếp.

### 13.3. Nghĩ token có `exp` là đã bị thu hồi

Expiry được kiểm tra theo thời gian. Revocation là quyết định/chỉ mục trạng thái của IdP. Hai sự kiện khác nhau: token có thể bị revoke **trước** `exp`; token hết hạn có thể chưa từng bị revoke. Cần xác định resource server biết trạng thái revoke bằng cách nào.

### 13.4. Revoke refresh token rồi coi access JWT cũ vô hiệu khắp nơi

Không mặc nhiên. JWT offline có thể được chấp nhận tới `exp` nếu không có denylist, introspection hoặc signal bổ sung. Muốn gần real-time revocation cần thiết kế resource servers và chấp nhận chi phí độ trễ/trạng thái.

### 13.5. Cho rằng logout IdP cũng xóa session của mọi RP

Không chắc. OP logout qua browser không đảm bảo gửi được tín hiệu cho mọi app; RP có thể giữ session độc lập. Back-channel/front-channel và session registry phải được hỗ trợ, đồng bộ, bảo vệ khỏi replay và test đúng từng RP.

### 13.6. Dùng GET để thay đổi trạng thái logout

Một link GET dễ bị cross-site trigger và làm yếu CSRF protection. Với app cookie/session, giữ `POST /logout` + CSRF; nếu muốn nút/link trên UI, submit form POST với token hợp lệ.

### 13.7. Lưu refresh/access token trong log, query string hoặc localStorage tùy tiện

Bearer token là credential: ai có token có thể sử dụng theo phạm vi của nó. Tránh log full token; dùng secret vault, storage bảo vệ, mã hóa at rest nếu phù hợp và hạn chế quyền. Với web app, xem xét BFF/session cookie an toàn thay vì để refresh token dài hạn trong JavaScript nếu yêu cầu bảo mật cao.

### 13.8. Nhầm ID token với access token

`id_token` giúp RP xác minh authentication OIDC, không được mặc định gửi như access token tới API. Hết hạn ID token không tự có nghĩa access token bị revoke, và revoke OAuth token không nhất thiết xóa OP session.

### 13.9. Cache introspection vô hạn hoặc bỏ check khi IdP offline

Cache `active=true` có thể tạo cửa sổ chấp nhận token đã revoke. Nếu IdP offline, không được âm thầm bypass authentication để giữ trải nghiệm; phải có chính sách downtime rõ, giám sát và test fail-closed thích hợp.

### 13.10. Không phân biệt logout “thiết bị này” và “mọi nơi”

Mỗi loại logout cần một hợp đồng khả thi: session ID hiện tại, toàn bộ session của user, grants/token của client này, hay toàn bộ session OP. Đừng hiển thị “Đăng xuất khỏi tất cả thiết bị” nếu phía server chỉ xóa một cookie.

## 14. Quy trình thiết kế logout cho ứng dụng thực tế

1. **Lập bản đồ vai trò:** Web app WebFlux là OAuth2 Client/RP hay Resource Server, IdP nào phát token, session store ở đâu, có ứng dụng khác dùng cùng OP không.
2. **Xác định phạm vi lời hứa:** “Đăng xuất phiên này”, “kết thúc SSO” hay “thu hồi mọi access/refresh token”; mô tả UI và security policy tương ứng.
3. **Quản lý session cục bộ:** Dùng `LogoutWebFilter` và handlers để dọn SecurityContext, vô hiệu hóa WebSession; POST + CSRF, cookie secure, session timeout.
4. **Quản lý OAuth2 token:** Nắm quyền sở hữu token của client, storage, TTL, rotation và revoke khi người dùng logout nếu policy yêu cầu; không cố revoke token không thuộc client/người dùng/authorization grant của mình.
5. **Phối hợp OP:** Với OIDC RP, cân nhắc RP-Initiated Logout; nếu yêu cầu OP chủ động logout RP, cấu hình back-channel và registry phù hợp, kiểm tra token/session correlation.
6. **Cơ chế API từ chối token:** JWT offline chấp nhận cửa sổ TTL hoặc bổ sung introspection/denylist/version; opaque/introspection cần timeout và cache policy rõ. Không đưa JWT vào `NoOpServerSecurityContextRepository` rồi nghĩ đã thu hồi nó ở IdP.
7. **Kiểm thử liên hệ thời gian:** Trước/sau local logout, trước/sau `exp`, trước/sau revoke, thời điểm OP logout, ở nhiều app/thiết bị và khi IdP unreachable.
8. **Đo và quan sát:** Thu thập event metadata an toàn (không token secrets), request ID, outcome, lý do 401/403; theo dõi độ trễ đồng bộ revocation.
9. **Tài liệu hóa giới hạn:** Ghi rõ trường hợp access JWT còn hiệu lực tới `exp`, session ở app khác có thể chưa mất, và bao lâu hệ thống cam kết chặn truy cập.
10. **Rà soát bảo mật định kỳ:** Nâng Spring Security/Boot, kiểm tra cookie/session/CSRF, OIDC endpoints, JWKS rotation, refresh policies và secret handling.

## 15. Câu hỏi tự đánh giá

**Câu 1.** Alice logout khỏi website WebFlux nhưng một JWT access token còn 5 phút vẫn gọi API được. Có nhất thiết là bug Spring Security không?  
**Không.** Có thể website chỉ invalidated local WebSession, trong khi API xác minh JWT offline. Đây là kết quả của **chính sách/kiến trúc**; nếu yêu cầu chặn ngay, thiết kế introspection/denylist hoặc cơ chế khác.

**Câu 2.** Hết `exp` của access token có tự xóa cookie `SESSION` ở website không?  
**Không.** Session ứng dụng là trạng thái khác, có timeout, revocation và bảo mật riêng.

**Câu 3.** Revoke refresh token ở IdP có ý nghĩa gì chắc chắn nhất?  
Client không được dùng **refresh token đã thu hồi** để lấy access token mới. Hiệu lực với access token đã cấp phụ thuộc IdP/resource server và cơ chế kiểm tra.

**Câu 4.** Vì sao HTTP 200 từ revocation endpoint không bảo đảm một API đã ngừng chấp nhận JWT?  
RFC 7009 phản hồi 200 cả khi token không còn hợp lệ, và resource server xác minh JWT offline có thể chưa biết trạng thái revoke.

**Câu 5.** RP-Initiated Logout có tương đương RFC 7009 revocation không?  
**Không.** Một bên phối hợp kết thúc **phiên SSO ở OP** qua browser redirect, bên kia yêu cầu AS **vô hiệu hóa token/grant**.

**Câu 6.** OIDC Back-Channel Logout giải quyết vấn đề gì?  
OP chủ động gửi Logout Token đã xác minh để RP tìm và hủy **session tương ứng**, kể cả khi browser không gọi logout trực tiếp tới RP. Không có nghĩa mặc định invalidate mọi JWT.

**Câu 7.** Vì sao GET `/logout` không nên tự làm mất session?  
Vì cross-site GET dễ bị kích hoạt ngoài ý muốn; POST với CSRF phù hợp giảm nguy cơ logout CSRF.

**Câu 8.** Làm sao chứng minh logout cục bộ thực sự hiệu lực?  
Đăng nhập, đọc protected resource, POST logout có CSRF, rồi gọi lại protected resource với **cookie cũ** và nhận redirect login/401 thay vì nội dung cũ.

**Câu 9.** Nếu đã dùng `WebSessionServerLogoutHandler` thì các tab/browser khác của Alice có bị logout hết không?  
**Không tự động.** Nó invalidates **WebSession hiện tại**; global logout cần session index/coordinator theo thiết kế.

**Câu 10.** Introspection `active=false` và JWT `exp` khác nhau ra sao?  
`active=false` là kết quả kiểm tra trạng thái tại AS theo token/grant; `exp` là giới hạn thời gian trong claim token mà RS có thể kiểm tra offline. Chính sách, latency và nguồn dữ liệu khác nhau.

### Tài liệu chính thức

- Spring Security Reactive, *Logout*: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security Reactive, *CSRF and Logout*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Reactive, *OIDC Logout (Local, RP-Initiated, Back-Channel)*: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security Reactive, *OAuth2 Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security Reactive, *Opaque Token Introspection*: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security API, `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html
- IETF RFC 7009, *OAuth 2.0 Token Revocation*: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662, *OAuth 2.0 Token Introspection*: https://www.rfc-editor.org/rfc/rfc7662
- OpenID Connect, *RP-Initiated Logout*: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect, *Back-Channel Logout*: https://openid.net/specs/openid-connect-backchannel-1_0.html

**Tóm lại:** Local logout xóa **ngữ cảnh và phiên của ứng dụng**; access/refresh token expiry giới hạn **thời gian sử dụng credential**; IdP revocation và OIDC logout tác động lên **trạng thái cấp token hoặc phiên SSO** theo giao thức và chính sách nhà cung cấp. Muốn “logout có hiệu lực toàn hệ thống” cần phối hợp các bên, thiết kế cách Resource Server nhận tín hiệu revoke và test kết quả thực tế ở từng ranh giới.