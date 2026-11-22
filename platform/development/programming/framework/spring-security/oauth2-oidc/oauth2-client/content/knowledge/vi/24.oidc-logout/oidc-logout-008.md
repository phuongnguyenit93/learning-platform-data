# 24.8. Tích hợp Back-Channel Logout theo stack và phiên bản hỗ trợ

## 1. Bài toán: người dùng đăng xuất khỏi OpenID Provider nhưng ứng dụng vẫn còn phiên

Một ứng dụng Spring Boot dùng Spring Security OAuth 2.0/OIDC Client để đăng nhập qua OpenID Provider (OP). Sau khi đăng nhập, ứng dụng tạo HTTP session và lưu <code>Authentication</code> của người dùng. Người dùng có thể đóng tab, đổi trình duyệt hoặc đăng xuất ở một ứng dụng khác dùng chung OP.

Nếu người dùng đăng xuất khỏi OP, **phiên ở ứng dụng Client không tự biến mất trong mọi trường hợp**. HTTP session của Client và session SSO của OP là hai trạng thái độc lập. Một Client chỉ biết người dùng đã đăng xuất ở OP nếu có một cơ chế đồng bộ/nhận thông báo thích hợp.

Ví dụ:

~~~text
09:00 Người dùng đăng nhập vào Portal A bằng OP.
09:05 Người dùng đăng nhập vào Portal B, vẫn dùng OP.
09:30 Người dùng đăng xuất ở Portal B và OP kết thúc SSO session.
09:31 Portal A vẫn đang giữ SecurityContext trong HTTP session.
~~~

Nếu Portal A không tham gia cơ chế logout do OP thông báo, request tiếp theo tới Portal A có thể vẫn được xác thực bằng session cookie của Portal A.

**OpenID Connect Back-Channel Logout** giải quyết nhu cầu thông báo theo chiều:

~~~text
OpenID Provider → HTTP POST trực tiếp tới Relying Party / OIDC Client
~~~

OP gửi một **Logout Token** đã ký tới endpoint đã đăng ký. Client xác minh token, tìm những phiên của mình được xác định bởi <code>sid</code> hoặc <code>sub</code>, rồi kết thúc phiên tương ứng.

> **Ý tưởng cốt lõi:** Back-Channel Logout là thông báo **server-to-server** từ OP đến Client. Nó không cần browser đang mở hay cookie phiên của browser đi kèm yêu cầu logout. Chính vì thế, Client phải có **ánh xạ đáng tin cậy giữa phiên ở OP và phiên nội bộ** để tìm đúng những session cần hủy.

Trong Spring Security, cơ chế này được hỗ trợ bằng các thành phần riêng cho **Servlet** và **Reactive WebFlux**. API cấu hình, handler, session registry và một số chi tiết endpoint còn phụ thuộc **phiên bản Spring Security** đang sử dụng.

## 2. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt local logout, RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout.
2. Hiểu nội dung và quy tắc xác minh của một OIDC Logout Token theo Back-Channel Logout 1.0.
3. Cấu hình endpoint Back-Channel Logout trong **Servlet SecurityFilterChain** và **WebFlux SecurityWebFilterChain** khi phiên bản hỗ trợ.
4. Xác định những thay đổi quan trọng từ Spring Security **6.2**, các phiên bản **6.2.x**, **6.5** và **7.x**; không sao chép API giữa các version thiếu kiểm chứng.
5. Đăng ký đúng <code>backchannel_logout_uri</code> và lựa chọn cơ chế <code>sid</code> hoặc <code>sub</code> với OP.
6. Phân biệt <code>HttpSession</code>/<code>WebSession</code>, session cookie, <code>OidcSessionRegistry</code> và <code>OAuth2AuthorizedClientService</code>.
7. Thiết kế back-channel logout khi ứng dụng chạy **nhiều instance**, dùng Spring Session Redis hoặc session store phân tán.
8. Tránh nhầm việc hủy phiên Client với thu hồi access/refresh token tại Authorization Server.
9. Kiểm thử token hợp lệ, sai chữ ký, sai audience, thiếu <code>sid</code>/<code>sub</code>, replay, multi-tenant và lỗi mạng.

## 3. Phân biệt bốn hình thức logout

Trong một ứng dụng OIDC, câu “đã logout” có thể chỉ bốn hành động rất khác nhau.

| Cơ chế | Ai khởi tạo? | Kênh truyền | Tác dụng điển hình |
|---|---|---|---|
| **Local Logout** | Người dùng/browser tại Client | Browser → Client | Hủy HTTP session/SecurityContext nội bộ |
| **RP-Initiated Logout** | Client/Relying Party | Browser redirect hoặc POST tới OP | Yêu cầu OP kết thúc SSO session; có thể trở về Client |
| **Front-Channel Logout** | OP | Qua browser/user agent | OP nhờ browser truy cập logout endpoint của các Client |
| **Back-Channel Logout** | OP | **HTTP server-to-server** | OP gửi Logout Token để Client hủy session tương ứng |

### 3.1. Local Logout

Ví dụ browser gửi:

~~~http
POST /logout HTTP/1.1
Host: portal.example.org
Cookie: JSESSIONID=SESSION_ID_PLACEHOLDER
~~~

Spring Security có thể xóa SecurityContext và invalidate local HTTP session. **Điều này không mặc nhiên kết thúc SSO session tại OP**.

### 3.2. RP-Initiated Logout

Ứng dụng có thể redirect browser đến <code>end_session_endpoint</code> của OP, ví dụ dùng <code>OidcClientInitiatedLogoutSuccessHandler</code> trong Servlet hoặc <code>OidcClientInitiatedServerLogoutSuccessHandler</code> trong WebFlux.

Đây là luồng **Client yêu cầu OP logout**, không phải OP chủ động gọi Back-Channel Logout endpoint của Client.

### 3.3. Front-Channel Logout

OP dựa vào browser để chuyển thông điệp đến Client. Cơ chế có thể phụ thuộc browser vẫn hoạt động, cookie policy, iframe/cross-site restrictions và cách Front-Channel Logout được cấu hình.

### 3.4. Back-Channel Logout

OP gửi trực tiếp:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN_PLACEHOLDER
~~~

Không có cookie của browser trong request này. Đó là lý do Spring Security cần liên kết giữa **Logout Token** của OP và **Client session** nội bộ, thay vì chỉ đọc cookie từ request OP gửi.

**Back-Channel Logout không phải OAuth2 Refresh Token Grant**, không phải một authorization request và cũng không phải HTTP <code>DELETE</code> tới Resource Server.

## 4. Các bên và trạng thái liên quan

Một hệ thống có:

~~~text
Browser / End-User
    |
    | session cookie
    v
Portal / Relying Party (RP)
    |                 |
    | HTTP Session    | OAuth2AuthorizedClient
    | SecurityContext | access/refresh tokens
    v                 v
Session Store       Token Store
    ^
    |
    | OIDC Provider session ↔ Client session mapping
    |
OidcSessionRegistry
    ^
    |
    | Logout Token qua HTTP POST
    |
OpenID Provider (OP)
~~~

### 4.1. Bốn loại định danh không được đánh đồng

| Định danh | Ai tạo/quản lý? | Ví dụ | Vai trò |
|---|---|---|---|
| <code>iss</code> | OpenID Provider | <code>https://idp.example.org/realms/company</code> | Xác định issuer tin cậy |
| <code>sub</code> | OP | <code>user-123</code> | Subject End-User trong phạm vi issuer |
| <code>sid</code> | OP | <code>op-session-7f...</code> | Định danh session tại OP dùng để tương quan logout |
| Client HTTP session ID | Portal/Spring Session | <code>app-session-9d...</code> | Định danh session nội bộ của RP |

<code>sid</code> **không nhất thiết bằng** <code>JSESSIONID</code>, <code>SESSION</code> cookie value hoặc ID của Redis key. Đó là hai không gian phiên khác nhau.

### 4.2. OAuth2AuthorizedClient không phải HTTP session

<code>OAuth2AuthorizedClient</code> chứa token đã được cấp cho một registration/principal. Sau Back-Channel Logout, session nội bộ có thể bị invalidated trong khi access token ở Resource Server còn hiệu lực về mặt thời hạn hoặc token store vẫn còn bản ghi.

Vì vậy cần quyết định **riêng** chính sách dọn authorized client, revoke refresh token và chặn quyền truy cập. Không coi session invalidation là cơ chế thu hồi mọi access token.

## 5. Kiểm tra phiên bản Spring Security trước khi viết code

Không nên nhìn thấy tên <code>OidcLogoutConfigurer</code> ở tài liệu phiên bản mới rồi chép vào project cũ mà không kiểm tra dependency thực tế.

### 5.1. Mốc hỗ trợ chính

| Dòng phiên bản Spring Security | Back-Channel Logout trong Client | Lưu ý triển khai |
|---|---|---|
| **Trước 6.2**, ví dụ 6.1 | Không có DSL Back-Channel Logout tích hợp như trong các tài liệu mới | Cân nhắc nâng phiên bản hoặc tích hợp theo spec bằng lớp tự viết, kiểm tra bảo mật đầy đủ |
| **6.2.x** | Bắt đầu có DSL <code>oidcLogout(...).backChannel(...)</code> cho Servlet và Reactive | API/handler/endpoint mặc định có thể khác ví dụ 6.5/7.x; kiểm tra đúng patch version |
| **6.2.4 trở lên** | Có API <code>logoutUri(...)</code> trong Back-Channel Logout configurer | URI dùng cho thao tác session logout nội bộ; không thay thế việc OP phải đăng ký endpoint public |
| **6.5.x** | Có hướng dẫn Servlet/Reactive và các handler/registry dùng tùy biến session logout | Xem kỹ cookie <code>JSESSIONID</code> so với Spring Session <code>SESSION</code> |
| **7.x** | Tiếp tục có DSL, hướng dẫn OIDC Logout riêng cho Servlet và Reactive | Không giả định mọi constructor/import của 6.x giữ nguyên; ưu tiên tài liệu đúng minor version |

Mốc 6.2 và <code>logoutUri</code> từ 6.2.4 được thể hiện trong Spring Security Java API. Việc **có class DSL** không bảo đảm provider, session registry, internal logout handler và cookie configuration trong ứng dụng của bạn đã vận hành đúng.

### 5.2. Spring Boot version không phải Spring Security version

Spring Boot quản lý phiên bản Spring Security bằng dependency management. Khi một ví dụ nói “Boot 3.x”, chưa đủ để kết luận có tất cả API của Spring Security 6.5. Khi nói “Boot 4.x”, cũng không có nghĩa có thể copy snippet từ 6.2.x.

Hãy xác định **phiên bản Spring Security thực chạy** qua build dependencies, rồi mở tài liệu API/reference của chính phiên bản đó.

### 5.3. Tại sao phải chia theo Servlet và Reactive?

| Hạng mục | Servlet | Reactive WebFlux |
|---|---|---|
| Security builder | <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| Security chain | <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| Session | <code>HttpSession</code> | <code>WebSession</code> |
| Registry ánh xạ OP/RP | <code>OidcSessionRegistry</code> | <code>ReactiveOidcSessionRegistry</code> |
| Handler chuyên biệt | <code>OidcBackChannelLogoutHandler</code> | <code>OidcBackChannelServerLogoutHandler</code> |
| Event khi Servlet session bị hủy | Có thể dùng <code>HttpSessionEventPublisher</code> | Reactive lifecycle/session repository riêng |
| Cấu hình back-channel | <code>http.oidcLogout(...)</code> | <code>http.oidcLogout(...)</code> trên reactive builder |

Tên DSL gần giống nhau, nhưng handler/interface **không thay thế lẫn nhau**. Không truyền Servlet handler vào reactive chain hoặc sử dụng <code>HttpSession</code> trực tiếp trong WebFlux.

## 6. Điều kiện ở OpenID Provider trước khi bật Back-Channel Logout

### 6.1. OP phải hỗ trợ tính năng

OIDC Discovery metadata có thể công bố:

~~~json
{
  "issuer": "https://idp.example.org/realms/company",
  "backchannel_logout_supported": true,
  "backchannel_logout_session_supported": true
}
~~~

Giải thích:

- <code>backchannel_logout_supported=true</code>: OP thông báo có khả năng Back-Channel Logout.
- <code>backchannel_logout_session_supported=true</code>: OP có thể gửi claim <code>sid</code> dùng tương quan session; OP cũng có thể đưa <code>sid</code> vào ID Token.

Nếu metadata không công bố, không được tự giả định provider chắc chắn hỗ trợ. Khả năng hỗ trợ có thể phụ thuộc tenant, realm, Client registration hoặc setting đã bật ở OP.

### 6.2. Client phải đăng ký backchannel_logout_uri

Một Client registration có thể cần các metadata:

~~~json
{
  "client_id": "portal-web",
  "backchannel_logout_uri":
    "https://portal.example.org/logout/connect/back-channel/company",
  "backchannel_logout_session_required": false
}
~~~

<code>backchannel_logout_uri</code> là địa chỉ **OP có thể gọi bằng HTTP server-to-server**; không phải redirect URI của authorization code:

~~~text
Authorization Code callback:
    https://portal.example.org/login/oauth2/code/company

Back-Channel Logout endpoint:
    https://portal.example.org/logout/connect/back-channel/company
~~~

**Hai endpoint phải được đăng ký đúng mục đích.** Thay callback bằng logout endpoint hoặc ngược lại sẽ làm flow lỗi và có thể tạo rủi ro bảo mật.

### 6.3. Có bắt buộc sid không?

<code>backchannel_logout_session_required</code> giúp Client diễn đạt với OP rằng Logout Token phải có <code>sid</code> nếu yêu cầu.

| Policy | Hệ quả |
|---|---|
| <code>true</code> | Chỉ chấp nhận cơ chế có OP session ID nếu provider/cấu hình hỗ trợ; phù hợp yêu cầu logout đúng session |
| <code>false</code> | Có thể xử lý Logout Token không có sid, dùng <code>iss + sub</code> để logout tất cả session liên quan của user cho Client |

Không bật <code>session_required=true</code> nếu OP không hỗ trợ phát <code>sid</code>, rồi kỳ vọng mọi browser session đều được xử lý tự động. Cần kiểm tra khả năng provider và contract thật.

### 6.4. Endpoint phải reachable từ OP

OP thường chạy ở hạ tầng khác với ứng dụng. Nếu RP chỉ có host <code>localhost</code>, private DNS không thể resolve từ OP hoặc inbound firewall chặn đường đi, OP không thể gửi request.

Production thường cần HTTPS, DNS public hoặc private network connectivity đã được thỏa thuận, TLS certificate hợp lệ và route gateway/proxy không chặn nhầm form POST.

Nếu OP hỗ trợ đăng ký endpoint động, cần phòng chống SSRF **ở phía OP** khi OP gọi các URI đã đăng ký. RP cũng nên giới hạn ingress và giám sát traffic, nhưng **không dùng source IP làm cơ chế xác thực duy nhất**.

## 7. OIDC Logout Token: JWT có nhiệm vụ riêng

Logout Token là JWT do OP tạo và ký, dùng thông báo sự kiện **logout**. Nó **không phải**:

- ID Token dùng chứng minh authentication cho login mới.
- Access token dùng gọi Resource Server.
- Refresh token của OAuth2AuthorizedClient.
- Authorization code.
- CSRF token của browser.

Một payload minh họa theo OIDC Back-Channel Logout 1.0 có thể như sau:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "aud": "portal-web",
  "iat": 1794800000,
  "exp": 1794800120,
  "jti": "logout-event-8d74b6",
  "sub": "user-123",
  "sid": "op-session-7f3d4a",
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Những dữ liệu trong JSON chỉ minh họa, không phải JWT hợp lệ chưa có chữ ký. Một header có thể dùng:

~~~json
{
  "alg": "RS256",
  "typ": "logout+jwt",
  "kid": "op-key-2026"
}
~~~

Theo bản đặc tả OIDC Back-Channel Logout 1.0 có **errata set 1**, <code>exp</code> là claim bắt buộc. Một số tài liệu/thư viện cũ theo bản final 2022 có thể hiển thị danh sách khác; khi kiểm tra tương thích cần đối chiếu **phiên bản đặc tả và hành vi của OP/Spring Security** chứ không tự bỏ kiểm tra thời hạn.

### 7.1. Bảng claim

| Claim | Vai trò | Kiểm tra cần thực hiện |
|---|---|---|
| <code>iss</code> | Issuer của OP | Phải khớp issuer tin cậy đã cấu hình cho Client |
| <code>aud</code> | Audience là OIDC Client/RP | Phải chứa Client ID đã đăng ký đúng registration |
| <code>iat</code> | Issued-at time | Kiểm tra theo policy về thời gian và clock skew |
| <code>exp</code> | Expiration time | Token không được hết hạn; bắt buộc theo errata set 1 |
| <code>jti</code> | JWT identifier | Định danh sự kiện, hỗ trợ chống replay/idempotency |
| <code>events</code> | Đánh dấu đây là logout event | Phải có key chính xác cho back-channel logout |
| <code>sub</code> | End-User subject | Dùng tìm sessions của subject theo issuer/client |
| <code>sid</code> | OP session identifier | Dùng tìm session(s) RP tương ứng |
| <code>nonce</code> | **Không được có** | Phải từ chối nếu tồn tại |

<code>sub</code> và <code>sid</code> **mỗi claim đều có thể vắng**, nhưng Logout Token **phải có ít nhất một trong hai**.

### 7.2. events phải có đúng event URI

Mẫu đúng:

~~~json
{
  "events": {
    "http://schemas.openid.net/event/backchannel-logout": {}
  }
}
~~~

Chú ý URI ở đây bắt đầu bằng **<code>http://</code>** theo đặc tả, không phải URL HTTP request do ứng dụng tự gọi và không nên tự đổi thành <code>https://</code>.

Nếu thiếu event này, không được coi JWT là Logout Token chỉ vì có <code>iss</code>, <code>sub</code> và chữ ký hợp lệ.

### 7.3. Tại sao nonce bị cấm?

OIDC ID Token có thể chứa <code>nonce</code> để liên kết authentication response với request đăng nhập. Logout Token **cấm** claim <code>nonce</code> để giảm nguy cơ một JWT dùng cho logout bị nhầm thành ID Token phục vụ login.

Đây là một phần quan trọng của việc tránh **cross-JWT confusion**. Không thiết kế một decoder “chữ ký đúng là chấp nhận mọi JWT của OP” rồi dùng chung cho cả login và logout.

### 7.4. sid khác session ID của ứng dụng

Nếu OP gửi:

~~~json
{
  "sid": "op-session-7f3d4a"
}
~~~

đó là OP session ID. Spring Security phải dựa vào **ánh xạ đã lưu lúc login** để tìm HTTP session ID tương ứng ở Client, chứ không gọi:

~~~text
invalidateHttpSession("op-session-7f3d4a")
~~~

trừ phi ứng dụng đã xây một ánh xạ có kiểm tra đúng; không bao giờ coi OP sid là session cookie value do browser gửi.

## 8. Back-Channel Logout HTTP request và response

Đặc tả dùng **POST** với content type:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

Form body có:

~~~text
logout_token=<signed JWT issued by OP>
~~~

Ví dụ mô tả:

~~~http
POST /logout/connect/back-channel/company HTTP/1.1
Host: portal.example.org
Content-Type: application/x-www-form-urlencoded

logout_token=HEADER.PAYLOAD.SIGNATURE
~~~

Không cần browser cookie hoặc <code>Authorization: Bearer <access_token></code> để chứng minh logout request. **Bằng chứng của sự kiện logout là Logout Token đã ký và được validate**.

### 8.1. Trình tự xử lý ở RP

1. Định tuyến request vào Back-Channel Logout handler dành cho đúng OIDC Client registration.
2. Parse form <code>logout_token</code> có giới hạn kích thước.
3. Xác minh chữ ký bằng key OP tin cậy và validate JWT header/claims.
4. Kiểm tra <code>iss</code>, <code>aud</code>, <code>iat</code>, <code>exp</code>, <code>jti</code>, <code>events</code>, <code>sid</code>/<code>sub</code> và không có <code>nonce</code>.
5. Tìm các Client HTTP sessions được liên kết với OP session/subject và đúng issuer/audience.
6. Invalidate các session tương ứng bằng cơ chế Spring Security/framework hỗ trợ.
7. Dọn các ánh xạ registry và thực thi cleanup token/application state theo policy.
8. Trả HTTP response thích hợp, không tiết lộ nội dung session/user không cần thiết.

### 8.2. Response status và retry

Theo đặc tả, khi Logout Token không hợp lệ, RP phải **từ chối**; HTTP <code>400 Bad Request</code> là trường hợp chuẩn cho validation failure. Khi xử lý thành công, RP nên trả response thành công phù hợp với contract.

Nếu kết nối lỗi tạm thời hoặc RP gặp outage, OP có thể retry theo chính sách. Việc retry **không nên khiến ứng dụng tạo lại session hoặc hủy nhầm phiên khác**.

Một implementation robust thường cần:

- Xử lý lặp idempotent.
- Chống replay theo <code>(iss, aud, jti)</code> khi policy yêu cầu.
- Giới hạn request size và rate.
- Giám sát nhưng không log raw Logout Token.
- Không trả thông tin cụ thể như “user này có ba session” cho caller.

## 9. Luồng tổng thể khi OP chủ động logout

~~~mermaid
sequenceDiagram
    autonumber
    participant Browser as Browser của End-User
    participant RP as Spring Security OIDC Client
    participant Session as Session Store
    participant Registry as OIDC Session Registry
    participant OP as OpenID Provider

    Browser->>RP: OIDC Login callback
    RP->>OP: Authorization Code token exchange
    OP-->>RP: ID Token có iss/sub/(sid)
    RP->>Session: Lưu SecurityContext và HTTP session
    RP->>Registry: Lưu mapping issuer/client/sub/sid ↔ RP session
    RP-->>Browser: Session cookie

    Note over OP: Sau đó OP kết thúc SSO session
    OP->>RP: POST /logout/connect/back-channel/company, logout_token
    RP->>RP: Validate signature, issuer, audience, events, times, jti
    RP->>Registry: Tìm session(s) theo sid hoặc sub
    Registry-->>RP: Client session identifiers phù hợp
    RP->>Session: Invalidate phiên đã được chọn
    RP->>Registry: Xóa mapping phiên đã logout
    RP-->>OP: HTTP success response

    Browser->>RP: Request tiếp theo với cookie cũ
    RP-->>Browser: Không còn authenticated session; yêu cầu login
~~~

**Không có redirect qua browser trong bước OP gửi Logout Token.** Đó là lợi thế quan trọng của Back-Channel Logout đối với những browser đã đóng tab hoặc không thể nhận iframe/front-channel notification.

## 10. Cấu hình Servlet: Spring Security hỗ trợ DSL Back-Channel Logout

Phần dưới minh họa API ở các bản Spring Security có DSL và handler tương ứng, đặc biệt các hướng dẫn **6.5/7.x**. Kiểm tra đúng minor version của dự án trước khi copy class/constructor.

### 10.1. Dependencies cho Servlet OIDC Client

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 10.2. ClientRegistration với issuer-uri

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

**Không có property tự động tên <code>backchannel-logout-enabled</code> trong cấu hình trên.** Việc đăng ký URI tại OP và bật Spring Security DSL là hai thao tác riêng.

<code>openid</code> làm đây là OIDC login. Nếu application chỉ cấu hình OAuth2 Resource Server JWT mà **không có OIDC Login**, DSL Back-Channel Logout của OIDC Client không tự tạo session tương quan để logout.

### 10.3. Bật Back-Channel Logout trên SecurityFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcLogoutSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    HttpSessionEventPublisher sessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

Ví dụ thể hiện:

1. <code>oauth2Login()</code> xử lý browser OIDC Login.
2. <code>oidcLogout(...).backChannel(...)</code> bật Back-Channel Logout DSL.
3. <code>HttpSessionEventPublisher</code> giúp Spring Security nhận sự kiện hủy HTTP session và làm sạch thông tin phiên trong registry theo cơ chế phù hợp.

**Ở các bản hướng dẫn mới**, có thể thêm một bean <code>OidcBackChannelLogoutHandler</code> như mục 10.4 để thực hiện session logout theo cách được tài liệu khuyến nghị. Không sao chép mọi biến thể ví dụ rồi tạo hai handler cùng loại không chủ đích.

### 10.4. Handler dành cho các phiên bản công bố API tương ứng

Theo tài liệu Spring Security ở các bản có <code>OidcBackChannelLogoutHandler</code>:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}
~~~

Class trên là **Servlet handler**, không phải Reactive handler. Trong project thực tế cần dùng import của đúng Spring Security version.

Khi đăng ký handler này theo cơ chế hỗ trợ, Spring Security sử dụng nó để thực hiện per-session logout thay vì yêu cầu tích hợp thủ công với CSRF token của <code>/logout</code> trong những cấu hình cũ hơn.

Nếu version không có class/constructor đó, **không tự tạo class trùng tên hoặc đổi tên class theo phỏng đoán**. Hãy dùng tài liệu API cùng version, hoặc nâng cấp lên bản có hỗ trợ rõ ràng.

### 10.5. Endpoint Back-Channel mặc định

Với registration ID <code>company</code>, endpoint thường là:

~~~text
/logout/connect/back-channel/company
~~~

OP đăng ký URL đầy đủ:

~~~text
https://portal.example.org/logout/connect/back-channel/company
~~~

Không viết controller POST cùng path rồi bỏ qua Spring Security filter để parse JWT thủ công. Nếu sử dụng DSL, framework cần được để xử lý signature/claim validation và session invalidation theo thiết kế.

## 11. Vì sao endpoint back-channel không cần browser authentication?

OP gọi endpoint bằng **server-to-server POST**, không có người dùng đang đăng nhập trên HTTP session.

Do đó cấu hình kiểu:

~~~java
.anyRequest().authenticated()
~~~

không nên biến Back-Channel Logout thành một endpoint mà chỉ browser đã login mới gọi được. Khi DSL được cấu hình đúng và request match filter, Spring Security có xử lý chuyên biệt cho logout protocol.

Nếu dùng nhiều <code>SecurityFilterChain</code>, endpoint cần rơi vào chain có <code>oauth2Login()</code> và Back-Channel Logout filter. Một API chain đứng trước, match <code>/**</code> và yêu cầu Bearer token có thể khiến OP nhận 401 trước khi logout filter chạy.

### 11.1. Ví dụ cấu hình sai chain

~~~text
@Order(1) API chain: matches "/**", oauth2ResourceServer(jwt)
@Order(2) Web chain: oauth2Login + oidcLogout.backChannel

POST /logout/connect/back-channel/company
    → trúng API chain
    → Bearer auth required
    → OP nhận 401
~~~

Cách sửa: giới hạn chain API vào <code>/api/**</code> hoặc một matcher rõ ràng, và giữ đường dẫn <code>/oauth2/authorization/**</code>, <code>/login/oauth2/code/**</code>, <code>/logout/connect/back-channel/**</code> trong web chain có OIDC Client support.

### 11.2. Không tắt CSRF toàn ứng dụng

Back-Channel Logout không phải browser POST dùng session cookie, nên nó cần được xử lý như một **protocol endpoint đã xác minh Logout Token**, không phải một lệnh tùy ý cho user logout.

Đừng khắc phục lỗi 403 ở endpoint bằng:

~~~java
.csrf(csrf -> csrf.disable()) // toàn web app
~~~

Điều này có thể làm yếu đi các form/route dùng cookie-based authentication. Hãy dùng cơ chế Back-Channel Logout handler/DSL và cấu hình CSRF có chủ đích theo tài liệu phiên bản.

## 12. Servlet: OidcSessionRegistry và ánh xạ phiên

Spring Security sử dụng <code>OidcSessionRegistry</code> để liên kết thông tin từ ID Token và OP session với Client HTTP session.

Ví dụ dữ liệu khái niệm:

~~~text
Client registration: company
Issuer:              https://idp.example.org/realms/company
Client ID:           portal-web
Subject:             user-123
OP sid:              op-session-7f3d4a
Client session ID:   app-session-9d2b
~~~

Khi nhận Logout Token:

- Nếu có <code>sid</code>, Spring Security có thể tìm những session của Client tương ứng OP session ID.
- Nếu chỉ có <code>sub</code>, Spring Security có thể tìm tất cả session của user đó cho Client/issuer phù hợp.
- Audience và registration boundary giúp tránh hủy session thuộc một OIDC Client khác.

### 12.1. sid-based và sub-based logout

| Logout Token | Ý nghĩa dự kiến | Phạm vi session |
|---|---|---|
| <code>sid=op-session-A</code> | Logout phiên OP cụ thể | Các session RP được tương quan với OP sid A |
| <code>sub=user-123</code>, không có sid | Logout End-User | Tất cả session RP phù hợp <code>iss + sub + aud/client</code> |
| Có cả <code>sid</code> và <code>sub</code> | Có thể xác minh subject và nhắm đúng session | Theo semantics sid và policy validate consistency |
| Không có sid lẫn sub | Logout Token sai | Phải từ chối |

Nếu một người có hai browser sessions thuộc hai OP sid khác nhau, việc logout bằng sid có thể chỉ ảnh hưởng một nhóm session, còn logout chỉ theo sub có thể ảnh hưởng cả hai.

### 12.2. Registry không phải HttpSession store

<code>OidcSessionRegistry</code> giữ **ánh xạ** để tìm session, còn <code>HttpSession</code>/Spring Session giữ **trạng thái phiên**.

~~~text
OidcSessionRegistry:
    (issuer, client, sub/sid) → HTTP session id(s)

Spring Session Redis:
    HTTP session id → SecurityContext và các session attributes
~~~

Hai hệ thống này phải cùng hoạt động. Nếu Spring Session đã dùng Redis nhưng OIDC registry vẫn in-memory, node B có thể đọc HTTP session nhưng **không có ánh xạ** để biết phải xóa session nào khi OP gửi Logout Token tới B.

## 13. Multi-instance: phải chia sẻ cả session lẫn OIDC registry

Giả sử:

~~~text
Instance A:
    User login, session S123
    OidcSessionRegistry(A): sid X → S123

Instance B:
    OidcSessionRegistry(B): rỗng

Redis Spring Session:
    session S123 tồn tại
~~~

OP gửi Logout Token sid X đến **B**. B có thể kiểm tra chữ ký đúng, nhưng registry của B không biết sid X ứng với S123; session vẫn có thể sống trên Redis.

Đây là lỗi **thiếu shared OIDC session mapping**, không phải lỗi chữ ký JWT hay session store.

### 13.1. Default registry thường nằm trong memory

Theo hướng dẫn Spring Security, registry mặc định có thể lưu các liên kết OP session ↔ RP session **trong memory**. Khi scale-out, cần cân nhắc custom registry lưu tập trung.

Với Servlet, có thể triển khai interface <code>OidcSessionRegistry</code> bằng Spring Data/Redis/JDBC theo đúng API version; các thao tác điển hình gồm:

~~~java
void saveSessionInformation(OidcSessionInformation info);

OidcSessionInformation removeSessionInformation(
    String clientSessionId);

Iterable<OidcSessionInformation> removeSessionInformation(
    OidcLogoutToken token);
~~~

Đây là chữ ký minh họa của interface tương ứng trong các bản tài liệu, không phải implementation hoàn chỉnh để copy-paste.

### 13.2. Schema khái niệm cho shared registry

Một kho mapping có thể biểu diễn:

~~~text
client_session_id
registration_id
issuer
client_id / audience
subject
provider_sid
created_at
session_expires_at
~~~

Cần index theo những khóa dùng cho lookup:

~~~text
(issuer, client_id, provider_sid)
(issuer, client_id, subject)
(client_session_id)
~~~

**Không chỉ lưu theo subject** vì hai issuers/clients có thể có cùng subject string. Không chỉ lưu theo sid vì sid opaque và chỉ cần duy nhất trong ngữ cảnh issuer.

### 13.3. Atomicity và retry

OP có thể gửi lại Logout Token nếu trước đó timeout. Registry implementation nên xử lý:

- Remove idempotent khi session đã bị hủy.
- Tìm/xóa đúng issuer/audience boundary.
- Không tạo lại mapping khi đã logout.
- Giới hạn retention phù hợp với session TTL.
- Concurrency giữa logout, session expiry và login mới.
- Không hủy session vừa đăng nhập mới chỉ vì <code>jti</code> cũ được replay ngoài policy.

Không có distributed transaction chuẩn giữa OP và Redis/DB của RP, nên cần thiết kế recovery khi logout event đến nhưng storage tạm thời mất kết nối.

## 14. Servlet: cookie JSESSIONID so với Spring Session SESSION

Đây là lỗi cấu hình dễ gặp khi chuyển từ session local sang Spring Session.

Theo hướng dẫn Spring Security, handler/session logout mặc định thường dùng cookie name <code>JSESSIONID</code> để liên kết session đã chọn với logout operation.

Tuy nhiên Spring Session có thể mặc định dùng cookie **<code>SESSION</code>**. Khi không khớp tên cookie, thao tác logout nội bộ có thể không tìm thấy session được chỉ định.

### 14.1. Tùy biến cookie name cho handler

Ở những phiên bản có constructor và setter tương ứng:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcLogoutHandler(
    OidcSessionRegistry oidcSessionRegistry) {

    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(oidcSessionRegistry);

    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Đây là một **biến thể thay thế** cho handler default ở mục 10.4, không tạo đồng thời hai bean handler chỉ để thử.

**Cần xác nhận tên cookie thực tế** bằng cấu hình Spring Session và behavior browser; <code>SESSION</code> là ví dụ thường gặp, không phải một giá trị bất biến cho mọi ứng dụng.

### 14.2. Đừng suy luận rằng đổi cookie name là đủ

Để logout hoạt động trên nhiều node, còn cần:

1. Session store dùng chung.
2. OIDC session registry mapping dùng chung.
3. Handler/cookie name khớp.
4. Endpoint OP gọi đến đúng chain.
5. Logout Token validation đúng.
6. Session cleanup và handling failures.

Nếu thiếu registry shared, đổi <code>JSESSIONID</code> thành <code>SESSION</code> vẫn không giúp node B biết session nào liên kết OP sid.

### 14.3. Không gửi session cookie của user ra OP

Request Back-Channel từ OP tới RP **không cần session cookie của browser**. Việc handler nội bộ dùng session cookie để truy cập/invalidated một session là cơ chế **bên trong RP**, không có nghĩa Client phải truyền cookie của browser sang OP.

Không đưa browser session cookie hoặc CSRF token ra response của back-channel endpoint.

## 15. Tùy biến logoutUri: phân biệt endpoint OP gọi và endpoint nội bộ

Trong các phiên bản hỗ trợ <code>backChannel().logoutUri(...)</code>, đây là cấu hình địa chỉ mà Spring Security dùng để **thực hiện thao tác logout đối với session** theo implementation/version.

Ví dụ minh họa:

~~~java
http
    .oidcLogout(oidc -> oidc
        .backChannel(backChannel -> backChannel
            .logoutUri(
                "http://localhost:9000/logout/connect/back-channel/{registrationId}")));
~~~

**Lưu ý quan trọng:**

- <code>logoutUri(...)</code> không mặc nhiên là thao tác đăng ký endpoint public với OP.
- Endpoint public <code>backchannel_logout_uri</code> phải được cấu hình tại OP theo deployment.
- URI nội bộ phải thực sự reachable từ tiến trình RP và route vào logout handler phù hợp.
- Nếu sau proxy/ingress có host/port nội bộ khác public URL, cấu hình cần phản ánh đúng network topology.
- Không xây internal logout URI từ <code>Host</code> hoặc forwarded headers do caller không tin cậy kiểm soát.

Các bản 6.2.x và các bản mới hơn có thể khác default internal logout URI/handler behavior. **Không lấy default từ tài liệu 7.x áp đặt cho 6.2.0**, đặc biệt khi có CSRF/session invalidation ở endpoint nội bộ.

Ở version thiếu handler chuyên biệt, các cơ chế yêu cầu gửi CSRF token về local <code>/logout</code> có thể phức tạp và phụ thuộc session repository. Ưu tiên tích hợp được framework tài liệu hỗ trợ thay vì tắt CSRF toàn cục.

## 16. Cấu hình Reactive WebFlux

Trong WebFlux, cơ chế cùng giao thức nhưng dùng reactive security filter và reactive OIDC registry.

### 16.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Nếu muốn ứng dụng chạy Reactive WebFlux, không thêm <code>spring-boot-starter-web</code> một cách vô ý. Khi cả MVC và WebFlux có mặt, Spring Boot thường ưu tiên Servlet/MVC; lúc đó cấu hình <code>SecurityWebFilterChain</code> có thể không được áp dụng như mong đợi.

### 16.2. SecurityWebFilterChain với oidcLogout

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oidcLogout(oidc -> oidc
                .backChannel(Customizer.withDefaults()))
            .build();
    }
}
~~~

Những thay đổi so với Servlet:

- <code>ServerHttpSecurity</code> thay <code>HttpSecurity</code>.
- <code>SecurityWebFilterChain</code> thay <code>SecurityFilterChain</code>.
- Session là <code>WebSession</code>.
- Security context theo Reactor Context thay vì phụ thuộc Servlet request thread.
- Registry có kiểu reactive.

### 16.3. Reactive back-channel handler

Theo các phiên bản tài liệu hỗ trợ:

~~~java
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelServerLogoutHandler();
}
~~~

Nếu dùng Spring Session với tên cookie khác mặc định:

~~~java
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler(
    ReactiveOidcSessionRegistry sessionRegistry) {

    OidcBackChannelServerLogoutHandler handler =
        new OidcBackChannelServerLogoutHandler(sessionRegistry);

    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Hai snippet là **hai phương án thay thế**, không khai báo hai bean cùng lúc. Cần import classes đúng package/version. Nếu phiên bản Spring Security không có class hoặc constructor tương ứng, hãy dùng API thật của version đó hoặc nâng cấp.

### 16.4. Reactive registry không phải Servlet registry

Reactive type:

~~~text
ReactiveOidcSessionRegistry
    saveSessionInformation(...)
    removeSessionInformation(clientSessionId)
    removeSessionInformation(logoutToken)
~~~

Các method phản ánh công việc tương tự Servlet nhưng trả reactive publisher như <code>Mono</code>/<code>Flux</code> theo API version.

Không triển khai registry reactive bằng thao tác JDBC/Redis **blocking trực tiếp trên Netty event-loop**, hoặc gọi <code>.block()</code> trong request handler. Dùng reactive-compatible store hoặc isolate blocking I/O có kiểm soát.

### 16.5. WebFlux nhiều instance

Hai node dùng Spring Session Redis cho <code>WebSession</code> nhưng vẫn có <code>ReactiveOidcSessionRegistry</code> in-memory thì lỗi tương tự Servlet:

~~~text
Login ở A → A biết OP sid ↔ WebSession S123
Logout Token đến B → B không có mapping
Redis vẫn giữ WebSession S123
~~~

Khi cần cluster-wide logout, triển khai shared reactive registry và shared WebSession store. Đồng thời kiểm tra session cookie name trong handler.

## 17. Session registry và token store: hai trách nhiệm khác nhau

Giả sử sau Back-Channel Logout:

~~~text
Session Registry:
    xóa mapping (iss, aud, sid) → session S123

Spring Session:
    invalidate session S123

OAuth2AuthorizedClientService:
    có thể còn (company, user-123) → A0/R0
~~~

Đây không nhất thiết là bug của Back-Channel Logout handler. Token store có lifecycle riêng.

### 17.1. Những chính sách cleanup có thể có

| Policy | Khi phù hợp | Điều cần cân nhắc |
|---|---|---|
| Chỉ invalidate session | Ứng dụng quản lý token theo session và session data được dọn đúng | Token nằm ở service riêng có thể còn |
| Xóa authorized client theo principal | Token không cần dùng sau logout, một principal chỉ có một authorization state | Có thể ảnh hưởng sessions khác |
| Xóa theo session/device | Cần logout chính xác một phiên, nhiều thiết bị độc lập | Cần storage key thiết kế hỗ trợ per-session |
| Thu hồi refresh token ở OP | Yêu cầu không cho cấp access token mới sau logout | OP cần token revocation endpoint/policy |
| Thu hồi/chặn access token | Ứng dụng có yêu cầu chặn API gần tức thì | JWT tự chứa có thể còn hạn nếu API chỉ kiểm tra chữ ký/exp |

**Back-Channel Logout không tự bảo đảm access token đã cấp bị thu hồi tại mọi Resource Server.**

### 17.2. Logout một session và nhiều sessions cùng principal

Nếu Logout Token có sid A, một phiên cụ thể có thể cần bị hủy. Nhưng <code>OAuth2AuthorizedClientService</code> mặc định thường key theo <code>(registrationId, principalName)</code>, có thể là **một bản token dùng chung của nhiều sessions**.

Xóa toàn bộ record theo principal khi logout một sid có thể làm các phiên còn lại mất token; không xóa có thể giữ refresh token sau logout. Cần quyết định rõ **session-scoped** hay **principal-scoped authorization** và xây storage/cleanup cho đúng.

### 17.3. Không dùng Logout Token làm access token

Logout Token có audience OIDC Client và sự kiện logout; không phải Bearer access token của Reports API. Resource Server không nên chấp nhận một Logout Token chỉ vì nó có chữ ký hợp lệ từ OP.

Ngược lại, không cho access token có <code>sub</code> giống nhau được dùng gọi logout endpoint như một mệnh lệnh hủy phiên; endpoint phải xác minh profile Logout Token đầy đủ.

## 18. Vòng đời logout trong hệ thống nhiều issuer hoặc nhiều ClientRegistration

Một portal có thể cấu hình:

~~~text
registrationId=company-a, clientId=portal-a, issuer=https://op-a.example.org
registrationId=company-b, clientId=portal-b, issuer=https://op-b.example.org
~~~

OP A gửi Logout Token cho <code>portal-a</code>. **Không được** hủy session chỉ vì tìm thấy cùng <code>sub=user-123</code> ở OP B.

Khóa tương quan phải dựa trên những dữ liệu tin cậy:

~~~text
issuer + audience/client + sid

hoặc:

issuer + audience/client + subject
~~~

### 18.1. registrationId trên URL không đủ làm bằng chứng

Đường dẫn:

~~~text
/logout/connect/back-channel/company-a
~~~

chỉ giúp framework chọn ClientRegistration/validator tương ứng. Nó **không chứng minh** token đến từ OP A. Một attacker có thể gửi POST đến URL đó; chữ ký và claims phải được kiểm tra.

### 18.2. Token có nhiều audience

OIDC JWT <code>aud</code> có thể là một chuỗi hoặc một danh sách audience theo profile. Ứng dụng phải xác minh Client ID của registration phù hợp trong audience và thực thi các điều kiện liên quan khi cần, không dùng <code>aud</code> tùy ý để chọn sessions của mọi Client.

### 18.3. Không dựa vào email để tìm session

Một email có thể thay đổi hoặc trùng nhau ở các hệ thống. Với OIDC, cặp <code>(iss, sub)</code> là cơ sở định danh đáng tin hơn. Không logout toàn bộ sessions theo email được khai báo trong JWT không được xác minh hoặc request body.

## 19. Bảo mật endpoint Back-Channel Logout

### 19.1. Xác minh chữ ký và thuật toán

Khi nhận JWT:

- Chỉ tin public signing keys của issuer đã đăng ký.
- Xác minh chữ ký bằng thuật toán được cho phép; không chấp nhận <code>alg=none</code>.
- Kiểm tra <code>kid</code> theo JWK Set đã được tải từ endpoint tin cậy.
- Không tự lấy <code>jku</code>/<code>x5u</code> từ token header để tải key từ URL do attacker chỉ định.
- Kiểm tra <code>iss</code>, <code>aud</code>, thời hạn và logout event.
- Phân biệt Logout Token với ID Token/access token.

Không dùng một đoạn code Base64 decode JWT rồi đọc <code>sub</code> mà không verify signature. Một attacker có thể tự tạo payload <code>sub=admin</code> để ép logout hàng loạt nếu endpoint chấp nhận token chưa xác minh.

### 19.2. Replay và jti

<code>jti</code> là định danh duy nhất của Logout Token. Một cơ chế chống replay có thể lưu:

~~~text
(issuer, audience, jti) → seenUntil=exp
~~~

với TTL giới hạn và storage phù hợp khi nhiều instance.

Theo đặc tả, kiểm tra một <code>jti</code> đã nhận trước đó là bước kiểm tra **tùy chọn**, nhưng với ứng dụng có yêu cầu chống replay cao nên thiết kế rõ.

Không chỉ kiểm tra jti bằng một biến memory trên từng node rồi coi đó là distributed replay protection. Mọi node phải áp dụng nhất quán nếu policy yêu cầu.

Lặp một logout event có thể được xử lý idempotently (session đã mất thì không hủy thêm session khác); chính sách HTTP response cho duplicate cần được kiểm tra với OP để tránh retry loop.

### 19.3. Bảo vệ chống request flood

Back-channel endpoint có thể bị gọi nhiều lần, cả bởi OP hợp lệ hoặc nguồn không tin cậy. Áp dụng:

- Rate limit và bounded input size.
- HTTP timeout cho verify/JWKS lookup/session store.
- Kết nối HTTPS/TLS chuẩn.
- Logging metadata đã làm sạch.
- Alert khi tỷ lệ signature failures hoặc bad requests tăng đột biến.
- Không cho body JSON tùy ý thay thế form <code>logout_token</code> ngoài profile được thỏa thuận.

IP allowlist hoặc mTLS giữa OP và RP có thể **bổ sung** defense-in-depth nếu tích hợp cho phép, nhưng không thay signature/claim validation.

### 19.4. Không mở endpoint “logout bất kỳ user nào”

Một controller kiểu:

~~~java
@PostMapping("/admin/logout-user")
void logout(@RequestParam String subject) {
    // Tìm và xóa mọi session của subject do caller cung cấp
}
~~~

không phải triển khai OIDC Back-Channel Logout. Nó thiếu issuer/audience/event/signature validation và có thể dẫn tới denial of service hoặc session hijacking về nghiệp vụ.

Nếu thật sự phải tự viết endpoint vì phiên bản chưa hỗ trợ, cần tuân thủ **toàn bộ đặc tả validation**, phân vùng identity, chống replay khi cần và session registry an toàn.

## 20. HTTP session, CSRF và cookie: những ranh giới dễ nhầm

### 20.1. Browser không trực tiếp kích hoạt Back-Channel Logout

Một browser có thể biết URL:

~~~text
https://portal.example.org/logout/connect/back-channel/company
~~~

nhưng chỉ gọi POST với chuỗi <code>logout_token</code> tự tạo không đủ điều kiện logout. Token phải được OP tin cậy ký đúng claims.

Vì vậy không dùng browser session cookie làm cơ chế xác thực OP back-channel. Cookie browser có thể không đi cùng server-to-server request.

### 20.2. CSRF vẫn cần cho browser routes

Một ứng dụng Servlet hoặc WebFlux login bằng session cookie vẫn có các POST/PUT/DELETE từ browser cần chống CSRF. Đừng tắt CSRF toàn bộ chỉ để làm Back-Channel Logout hoạt động.

Nếu back-channel handler phiên bản cũ cần nội bộ POST tới <code>/logout</code> với cookie/CSRF token, hãy cấu hình theo tài liệu version hoặc nâng lên handler mới hỗ trợ đúng pattern. Không bỏ qua kiểm tra/logout token để tiện coding.

### 20.3. SameSite không quyết định OP POST tới RP

Cookie SameSite điều chỉnh browser gửi cookie trong yêu cầu cross-site. OP gửi trực tiếp POST back-channel nên **không phụ thuộc browser gửi cookie**. Tuy vậy session cookie/CSRF configuration vẫn liên quan đến logout nội bộ do Spring Security thực hiện theo implementation.

### 20.4. Session event cleanup

Trong Servlet, <code>HttpSessionEventPublisher</code> giúp registry được thông báo khi session invalidated/expired theo lifecycle của servlet container. Với Spring Session Redis, cần kiểm tra event propagation/expiry behavior của session store và tương thích với Spring Security version.

Nếu session đã hết hạn nhưng registry còn mapping, OP có thể gửi logout cho một session không còn tồn tại. Cleanup nên idempotent, có TTL phù hợp và không tạo lại session đã hết.

## 21. Kiến trúc triển khai nhiều instance

Ví dụ kiến trúc:

~~~text
                       OpenID Provider
                              |
                    POST logout_token JWT
                              |
                       Load Balancer
                         /       \
                  Instance A   Instance B
                   (Servlet)    (Servlet)
                       |          |
             Shared OidcSessionRegistry (Redis/DB)
                       |          |
                Shared Spring Session Store
                       |          |
             Optional Authorized Client Store
~~~

Một phiên đăng nhập ở A phải tạo mapping mà B có thể tìm được. Khi OP gửi Logout Token tới B, B phải:

1. Validate Logout Token đúng issuer/client.
2. Tìm session(s) từ shared registry.
3. Invalidate session trong shared store.
4. Xóa mapping đã logout.
5. Áp dụng cleanup token theo policy.

### 21.1. Redis session không đồng nghĩa shared OidcSessionRegistry

Đây là lỗi triển khai rất quan trọng:

~~~text
Spring Session Redis: enabled
OidcSessionRegistry: default in-memory on each node
~~~

Login và callback có thể hoạt động trên mọi node, nhưng logout token đến một node khác không tìm được mapping để hủy session.

Với hệ thống nhiều instance, nên đánh giá custom shared registry và xác nhận storage atomicity/TTL. Không chỉ kiểm thử login rồi tuyên bố Back-Channel Logout đã hoạt động trong cluster.

### 21.2. Rolling deployment

Khi instance A dùng version v1, B dùng version v2, cần đảm bảo:

- Session serialization format tương thích.
- OIDC session registry schema tương thích.
- Registration IDs, issuer/client IDs nhất quán.
- Handler cookie name và internal logoutUri tương thích.
- Token validation behavior không bất ngờ đổi giữa minor versions.
- Không làm mất mapping giữa OP sid và RP session khi deploy mới.

Nếu custom registry không được version hóa, một rolling upgrade có thể khiến B không đọc được mapping do A ghi và làm logout fail silent.

### 21.3. Khi session store mất kết nối

Nếu Logout Token hợp lệ nhưng Redis/DB session store đang outage, ứng dụng không được giả vờ đã invalidate session thành công.

Cần policy rõ:

- Trả lỗi tạm thời phù hợp để OP có thể retry theo contract.
- Ghi trạng thái xử lý/alert nếu có queue/reliable event store.
- Không đưa thông tin user/session nhạy cảm vào response.
- Đảm bảo retry không tạo session mới hoặc xóa sai dữ liệu.
- Có giới hạn retries và cơ chế reconciliation nếu OP không retry.

Không có bảo đảm “exactly once logout” tự động giữa OP và RP. Hãy thiết kế **at-least-once delivery + idempotent handling** nếu yêu cầu khả năng chịu lỗi cao.

## 22. Cấu hình OP và Spring Security phải khớp nhau

Một checklist triển khai:

| Bên | Cấu hình cần khớp |
|---|---|
| OP | <code>backchannel_logout_supported</code> và capability thực tế |
| OP | Đăng ký <code>backchannel_logout_uri</code> của RP |
| OP | Có gửi <code>sid</code> không, <code>backchannel_logout_session_required</code> của Client |
| RP | Đúng registration ID trên endpoint |
| RP | Issuer, Client ID/audience và JWK verification đúng |
| RP | DSL <code>oidcLogout().backChannel()</code> đúng stack/version |
| RP | Handler phù hợp và cookie name đúng |
| RP | Registry ánh xạ phiên tồn tại và chia sẻ theo yêu cầu |
| RP | HTTP session/WebSession store hoạt động |
| RP | Lưu token và cleanup/revocation theo policy |
| Network | OP thực sự reach được URI với TLS và proxy route phù hợp |

### 22.1. Đăng ký Client tại OP không tự cấu hình framework

Khai báo <code>backchannel_logout_uri</code> ở OP không tự thêm filter trong Spring Security. Phải bật feature ở RP và đảm bảo endpoint được route đúng.

### 22.2. Bật DSL ở RP không tự đăng ký với OP

Ngược lại, bật <code>oidcLogout(...).backChannel(...)</code> không làm mọi OP tự gọi endpoint. OP phải hỗ trợ và biết đúng URI.

### 22.3. Kiểm tra bằng sự kiện thật

Login ở Client, logout ở OP/ứng dụng khác rồi quan sát request mới vào Client là cách thử nghiệm end-to-end hữu ích hơn chỉ kiểm tra endpoint trả 200 với một request không có JWT hợp lệ.

## 23. Kiểm thử Back-Channel Logout

### 23.1. Tối thiểu phải có test theo protocol

| Tình huống | Kỳ vọng |
|---|---|
| Logout Token OP ký đúng, issuer/audience đúng | Hủy session tương ứng |
| Logout Token thiếu chữ ký hoặc chữ ký sai | Từ chối |
| JWT dùng <code>alg=none</code> | Từ chối |
| <code>iss</code> sai | Từ chối |
| <code>aud</code> không chứa Client ID đúng | Từ chối |
| <code>events</code> thiếu/sai event URI | Từ chối |
| Có <code>nonce</code> | Từ chối |
| Thiếu cả <code>sub</code> và <code>sid</code> | Từ chối |
| Token hết hạn | Từ chối |
| <code>jti</code> duplicate | Theo replay/idempotency policy đã thiết kế |
| <code>sid</code> của session X | Không hủy nhầm session Y |
| Chỉ có <code>sub</code> | Hủy đúng sessions của subject trong issuer/client scope |
| Valid token cho Client A nhưng endpoint Client B | Không hủy session của B |
| Request lặp sau khi session đã hết | Idempotent, không tạo lại session |
| OP POST đến node khác node đã login | Vẫn hủy session khi registry/store shared |
| Redis/DB outage | Không báo thành công giả; xử lý lỗi/retry an toàn |

### 23.2. Đừng nhầm “mock OIDC login” với test Logout Token

Spring Security Test có thể mô phỏng <code>OidcUser</code> đã authenticated bằng <code>mockOidcLogin()</code> (Reactive) hoặc mock OAuth2/OIDC login theo stack. Những test đó hữu ích cho authorization rules nhưng **không kiểm tra**:

- OP có ký Logout Token đúng không.
- Logout Token decoder có validate issuer/audience/events/nonce không.
- Session registry có mapping chính xác không.
- Back-channel handler có invalidate đúng session trên node khác không.

Đối với test back-channel, nên dùng **test OP/key material riêng** và tạo JWT được ký đúng theo profile, không chỉ đặt <code>sub</code> vào một chuỗi giả rồi mong framework chấp nhận.

### 23.3. Kịch bản integration hai node

1. Khởi chạy instance A và B cùng phiên bản/cấu hình tương thích.
2. Dùng Redis shared session store.
3. Dùng shared <code>OidcSessionRegistry</code> hoặc reactive counterpart.
4. Đăng nhập user ở A, ghi nhận Client session được tạo bằng cách kiểm tra metadata an toàn.
5. Gửi Logout Token hợp lệ từ OP test vào endpoint **ở B**.
6. Kiểm tra request tiếp theo với cookie cũ không còn authenticated.
7. Xác minh các session khác có <code>sid</code> khác vẫn hoạt động nếu policy là sid-based logout.
8. Lặp request logout để kiểm tra idempotency.
9. Test endpoint khi cookie name là <code>SESSION</code>, không phải <code>JSESSIONID</code>.
10. Kiểm tra các bản ghi token/registry sau logout theo retention policy.

### 23.4. Manual test HTTP chỉ có ý nghĩa với token thật từ OP thử nghiệm

Ví dụ request:

~~~bash
curl --request POST \
  --url 'https://portal.example.org/logout/connect/back-channel/company' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'logout_token=SIGNED_LOGOUT_TOKEN_FROM_TEST_OP'
~~~

Chuỗi placeholder trên **không phải JWT hợp lệ**, nên bị từ chối là hành vi đúng. Để test success phải có OP/test fixture ký Logout Token bằng key phù hợp với issuer được RP tin cậy.

Không dùng private key production để tạo test fixture trong môi trường không được phép. Không đưa Logout Token production lên website decode JWT hoặc log console chia sẻ.

## 24. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| OP không gọi endpoint | Chưa đăng ký URI, tính năng bị tắt, OP không hỗ trợ | Kiểm tra metadata và Client settings |
| OP báo không reach được URI | DNS, firewall, TLS, reverse proxy | Kiểm tra network/TLS/ingress |
| Endpoint 404 | Sai path/registration ID, DSL chưa bật, chain không match | Kiểm tra URL và stack/version |
| Endpoint 401 | API chain yêu cầu Bearer token, filter Back-Channel không chạy | Chọn đúng SecurityFilterChain |
| Endpoint 403 | CSRF hoặc internal logout handler/cookie mismatch | Kiểm tra DSL/handler phiên bản, không tắt CSRF global |
| Logout Token bị 400 | Chữ ký/issuer/audience/exp/events/nonce/sub/sid sai | Validate theo spec và OP metadata |
| OP logout nhưng Client session vẫn sống | Registry thiếu mapping hoặc session store không hủy được | Kiểm tra registry/session lookup |
| Chỉ logout được trên node A | Registry in-memory ở A | Chia sẻ OIDC session registry |
| HTTP session ở Redis nhưng logout không tác dụng | Chỉ session shared, OIDC registry vẫn local | Cấu hình cả registry dùng chung |
| Handler không tìm được session | Tên cookie <code>JSESSIONID</code> vs <code>SESSION</code> | Cấu hình <code>setSessionCookieName</code> đúng |
| Logout sid A lại ảnh hưởng user/session khác | Khóa registry sai issuer/audience/sid | Sửa multi-tenant mapping và validation |
| Logout không có sid làm mất mọi phiên user | Đây có thể là semantics sub-based logout | Xác minh policy và khả năng OP phát sid |
| Session đã invalidated nhưng API vẫn nhận access token | Token/Resource Server có lifecycle riêng | Xem revoke/expiry/introspection và token cleanup |
| Lỗi khi rolling deploy | Serializer/registry schema không tương thích | Kiểm tra phiên bản và migration |
| Logout bị lặp sau timeout | OP retry / RP xử lý không idempotent | Replay/idempotency policy |
| Không có <code>OidcBackChannelLogoutHandler</code> class | Project dùng bản Spring Security khác tài liệu | Kiểm tra dependency và docs chính xác |
| Reactive bean/type mismatch | Dùng Servlet handler trong WebFlux | Dùng reactive handler/registry |
| Token có nonce mà được chấp nhận | Validation thiếu điều kiện Logout Token | Sửa validator; nonce bị cấm |

### 24.1. Luồng điều tra đề xuất

~~~text
User logout tại OP
   |
   v
OP có hỗ trợ Back-Channel Logout và đăng ký RP URI?
   |-- Không --> Bật/đăng ký OP capability
   |
   v
OP đã gửi POST tới RP và network nhận được?
   |-- Không --> DNS/TLS/firewall/ingress
   |
   v
POST vào đúng Spring Security chain và endpoint?
   |-- Không --> Matcher/order/version/URI
   |
   v
Logout Token JWT đã được validate?
   |-- Không --> iss/aud/alg/exp/iat/events/sub/sid/nonce
   |
   v
OidcSessionRegistry tìm được Client session?
   |-- Không --> Shared registry/mapping/TTL/tenant
   |
   v
HttpSession/WebSession bị invalidated?
   |-- Không --> Handler/cookie name/session store/CSRF
   |
   v
Request sau đó còn authenticated?
   |-- Có --> Session restore, cache, alternate auth path
   |
   v
Token cleanup và revocation có theo policy?
~~~

## 25. Vận hành, quan sát và kiểm soát độ tin cậy

### 25.1. Metrics nên có

| Metric / log field | Ý nghĩa |
|---|---|
| <code>oidc_backchannel_request_total</code> | Số request từ OP tới endpoint |
| <code>oidc_backchannel_validation_failure_total{reason}</code> | Sai signature, issuer, audience, event, expiry... |
| <code>oidc_backchannel_session_match_count</code> | Số session match theo sid/sub |
| <code>oidc_backchannel_session_invalidate_total</code> | Số session được invalidate |
| <code>oidc_backchannel_registry_lookup_latency</code> | Độ trễ shared registry |
| <code>oidc_backchannel_session_store_failure_total</code> | Lỗi Redis/DB/session repository |
| <code>oidc_backchannel_duplicate_jti_total</code> | Sự kiện trùng nếu có replay cache |
| <code>oidc_backchannel_response_status_total</code> | Theo dõi lỗi trả về cho OP |
| <code>oidc_backchannel_unknown_registration_total</code> | URI với registration ID không tồn tại |

Không đưa raw <code>logout_token</code>, session cookie, <code>sub</code> chưa làm sạch, access/refresh token hoặc private keys vào logs/metrics. Tránh dùng principal raw hoặc <code>jti</code> làm metric label cardinality cao.

### 25.2. Correlation

Có thể lưu:

~~~text
registrationId=company
issuerAlias=company-idp
logoutTokenValidation=success
eventKind=backchannel-logout
sessionMatchCount=1
sessionInvalidation=success
processingMillis=47
requestCorrelationId=...
~~~

Không log nguyên JWT payload chỉ vì muốn biết <code>sid</code>; có thể dùng hash/truncated identifier nội bộ theo chính sách nếu thật sự cần điều tra.

### 25.3. Bounded retry và phản hồi của OP

Nếu RP nhận Logout Token hợp lệ nhưng không thể ghi vào shared session store, nên có policy rõ ràng về retry/queue và phản hồi thất bại. Nếu OP không retry, có thể cần cơ chế đối soát session lạc hậu hoặc giới hạn session TTL.

Tránh thiết kế một request logout xử lý không giới hạn số sessions/không giới hạn thời gian, gây exhaustion khi subject có nhiều sessions.

## 26. Khi phiên bản hoặc OP không hỗ trợ Back-Channel Logout

Không nên hứa tính năng này có sẵn ở **mọi Spring Security version** hoặc **mọi OpenID Provider**.

### 26.1. Nếu Spring Security cũ hơn 6.2

Có ba hướng:

1. **Nâng cấp Spring Security/Spring Boot** tới một dòng được hỗ trợ, có API Back-Channel Logout phù hợp; kiểm tra migration và compatibility.
2. Nếu không thể nâng cấp, **tự tích hợp theo OIDC Back-Channel Logout specification** bằng endpoint validate JWT, trust anchors, registry và session invalidation, với kiểm thử bảo mật nghiêm ngặt.
3. Dùng cơ chế **RP-Initiated Logout, session TTL ngắn và reauthentication policy** khi đáp ứng use case; cần chấp nhận rằng chúng không hoàn toàn tương đương OP-initiated Back-Channel Logout.

Không dùng <code>GET /logout?sub=...</code> public làm workaround.

### 26.2. Nếu OP không hỗ trợ back-channel

Ứng dụng không thể tự tạo một thông báo OP→RP đáng tin chỉ bằng thay đổi Spring Security. Cần phối hợp nhà cung cấp OP hoặc xem alternative:

- RP-Initiated Logout khi người dùng logout tại chính ứng dụng.
- Front-Channel Logout nếu OP hỗ trợ, với các hạn chế của browser.
- Session lifetime ngắn và reauthentication cho hành động nhạy cảm.
- Cơ chế sự kiện security riêng được **xác thực và kiểm tra contract**, nếu hệ thống OP cung cấp chính thức.

Không coi polling <code>UserInfo</code> hoặc thử refresh token liên tục là một thay thế hoàn chỉnh cho Back-Channel Logout.

### 26.3. Nếu chỉ cần revoke token, không cần session logout?

Token Revocation (RFC 7009) là chức năng khác. Có thể thu hồi refresh token mà không có OIDC Back-Channel Logout; ngược lại, có thể nhận Back-Channel Logout và invalidate browser session mà access token đã phát hành vẫn tồn tại cho đến khi hết hạn.

Hãy xác định rõ mục tiêu sản phẩm: **ngăn user tiếp tục dùng portal session**, **ngăn refresh token cấp access token mới**, hay **ngăn Resource Server chấp nhận access token ngay lập tức**. Mỗi mục tiêu có lớp kỹ thuật và chính sách riêng.

## 27. Các bài tập thực hành

### Bài 1 — Phân biệt hai chiều logout

Một browser tại Portal A nhấn “Logout”, Portal A redirect tới <code>end_session_endpoint</code>.

**Câu hỏi:** Đây có phải Back-Channel Logout không?

**Đáp án:** Không. Đây là RP-Initiated Logout. Back-Channel Logout xảy ra khi OP chủ động gửi HTTP POST Logout Token tới RP/Client.

### Bài 2 — User đóng tab browser

Người dùng đã đóng tab Portal A rồi logout khỏi OP bằng Portal B.

**Câu hỏi:** Back-Channel Logout có nhất thiết cần tab Portal A còn mở không?

**Đáp án:** Không. OP gửi thông báo server-to-server, vì vậy vẫn có thể yêu cầu Portal A invalidate phiên nếu có endpoint và session mapping còn hợp lệ.

### Bài 3 — sub và sid

OP gửi Logout Token có <code>sid=op-sid-1</code>, user có hai sessions tương quan <code>op-sid-1</code> và <code>op-sid-2</code>.

**Câu hỏi:** Có nên hủy cả hai không?

**Đáp án:** Với sid-based logout, chỉ hủy những Client sessions tương quan đúng sid, trong issuer/audience scope. Không tự mở rộng sang sid khác.

### Bài 4 — Logout Token không có sid

Logout Token có <code>iss</code>, <code>aud</code>, <code>sub=user-123</code>, nhưng không có <code>sid</code>.

**Câu hỏi:** Hệ quả?

**Đáp án:** Nếu được Client/OP policy cho phép và token hợp lệ, cần logout tất cả Client sessions của End-User được xác định bởi <code>iss + sub</code> trong audience/registration phù hợp, không chỉ một browser session.

### Bài 5 — nonce trong Logout Token

Một token đã ký đúng nhưng có claim <code>nonce</code> được gửi tới back-channel endpoint.

**Câu hỏi:** Có được chấp nhận không?

**Đáp án:** Không. Logout Token không được chứa <code>nonce</code> theo OIDC Back-Channel Logout spec.

### Bài 6 — Sai audience

Token do OP A ký đúng, nhưng <code>aud=another-client</code>; endpoint là <code>/logout/connect/back-channel/company</code> có Client ID <code>portal-web</code>.

**Câu hỏi:** Có được logout user không?

**Đáp án:** Không. JWT không dành cho Client này. Đường dẫn registration ID không thay thế xác minh audience.

### Bài 7 — Redis session nhưng registry local

Instance A xử lý login và lưu OIDC registry trong memory; shared HTTP session ở Redis. OP gửi Logout Token tới B.

**Câu hỏi:** Điều gì có thể xảy ra?

**Đáp án:** B có thể verify token nhưng không biết OP sid/sub đang trỏ tới Client session ID nào. Cần shared OIDC session registry, không chỉ shared HTTP session.

### Bài 8 — Cookie JSESSIONID và SESSION

Ứng dụng chuyển sang Spring Session và browser dùng cookie <code>SESSION</code>, nhưng OIDC session logout handler vẫn nghĩ cookie là <code>JSESSIONID</code>.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án:** Kiểm tra session cookie name của handler, dùng <code>setSessionCookieName("SESSION")</code> khi phiên bản có API tương ứng; đồng thời xác minh shared session/registry và internal logout route.

### Bài 9 — Ghi log JWT

Nhóm vận hành muốn log toàn bộ Logout Token và các cookies để điều tra 400.

**Câu hỏi:** Có an toàn không?

**Đáp án:** Không. Đây là credential/security event data nhạy cảm. Chỉ log metadata đã làm sạch, error code và correlation ID; không log raw JWT/cookie.

### Bài 10 — Session bị hủy nhưng API vẫn nhận access token

Back-Channel Logout thành công và browser session ở Portal đã invalidated. Resource Server vẫn chấp nhận access token JWT chưa hết hạn.

**Câu hỏi:** Có phải Back-Channel Logout tự động không hoạt động?

**Đáp án:** Không nhất thiết. Session invalidation và access token revocation là hai cơ chế độc lập. Cần chính sách revoke/introspection/short-lived token hoặc API authorization riêng nếu muốn chặn ngay.

### Bài 11 — Sai stack

Một project WebFlux sử dụng <code>SecurityWebFilterChain</code>, nhưng developer inject <code>OidcBackChannelLogoutHandler</code> của Servlet.

**Câu hỏi:** Cách sửa?

**Đáp án:** Dùng reactive handler <code>OidcBackChannelServerLogoutHandler</code> và <code>ReactiveOidcSessionRegistry</code> theo API version, thay vì trộn Servlet và Reactive components.

### Bài 12 — Phân tích phiên bản

Dự án đang chạy Spring Security 6.1 và developer chép:

~~~java
http.oidcLogout(oidc -> oidc.backChannel(
    Customizer.withDefaults()));
~~~

**Câu hỏi:** Vì sao có thể không compile?

**Đáp án:** Back-Channel Logout DSL tích hợp được đưa vào từ Spring Security 6.2. Cần xác định phiên bản đang dùng, nâng cấp hoặc triển khai protocol theo cách tương thích, không copy API mới vào classpath cũ.

### Bài 13 — Tích hợp đầy đủ trên hai replica

Hãy thiết kế:

1. OIDC ClientRegistration có issuer/client ID tin cậy.
2. OP bật Back-Channel Logout và đăng ký public <code>backchannel_logout_uri</code>.
3. SecurityFilterChain hoặc SecurityWebFilterChain có <code>oauth2Login()</code> và DSL <code>oidcLogout().backChannel()</code> đúng version.
4. Handler phù hợp stack/cookie name.
5. Shared session store cùng shared <code>OidcSessionRegistry</code> hoặc reactive counterpart.
6. Session mapping phân vùng issuer/audience/subject/sid.
7. Validation JWT đầy đủ và policy <code>jti</code>/replay.
8. Cleanup/revocation token theo yêu cầu sản phẩm.
9. HTTP response/retry/idempotency cho OP.
10. Test callback chéo node và Logout Token từ OP gửi sang node khác.

Giải thích điều gì xảy ra khi OP gửi token hợp lệ trong lúc Redis outage, và vì sao không thể coi kết quả xử lý là thành công nếu phiên vẫn còn hoạt động.

## 28. Tổng kết

- OIDC **Back-Channel Logout** cho phép **OpenID Provider chủ động gửi JWT Logout Token** đến Client bằng HTTP POST, không phụ thuộc browser đang mở.
- Logout Token phải được validate theo **đúng profile logout**, bao gồm chữ ký, issuer, audience, thời gian, event URI, <code>sid</code>/<code>sub</code> và **không có nonce**. <code>exp</code> là claim bắt buộc trong đặc tả có errata set 1.
- Back-Channel Logout dùng <code>logout_token</code> trong form body, không phải access token, ID Token hay refresh token.
- Spring Security có DSL <code>oidcLogout(...).backChannel(...)</code> ở **Servlet và Reactive từ dòng 6.2**, nhưng handler và internal logout URL có thể khác giữa các patch/minor versions.
- Servlet sử dụng <code>OidcSessionRegistry</code>/<code>OidcBackChannelLogoutHandler</code>; WebFlux dùng <code>ReactiveOidcSessionRegistry</code>/<code>OidcBackChannelServerLogoutHandler</code> theo version hỗ trợ.
- Endpoint mặc định thường là <code>/logout/connect/back-channel/{registrationId}</code>, nhưng **OP phải đăng ký URI public** và có thể gọi được nó.
- Khi Logout Token có <code>sid</code>, logout theo OP session; khi chỉ có <code>sub</code>, có thể logout tất cả Client sessions tương ứng subject trong issuer/audience scope.
- **Spring Session Redis không tự đồng bộ OIDC session registry nếu registry vẫn in-memory.** Multi-instance cần chia sẻ cả session store và ánh xạ OP↔RP session.
- Kiểm tra tên cookie <code>JSESSIONID</code> và <code>SESSION</code> khi dùng Spring Session; handler phải biết đúng session cookie để invalidate session.
- Không tắt CSRF toàn bộ ứng dụng hoặc cho phép logout theo <code>sub</code> chưa được validate. Chú ý multiple SecurityFilterChains, issuer/audience boundary và replay.
- Back-Channel Logout **không tự bảo đảm revoke access/refresh tokens** ở Authorization Server hoặc Resource Server. Chính sách session cleanup, authorized-client storage và token revocation phải được thiết kế riêng.
- Test thực tế phải gồm **JWT hợp lệ/sai**, đúng/sai client, nhiều phiên, nhiều node, session store outage và rollback/retention; login chạy được chưa chứng minh logout đã hoạt động.

### Tài liệu tham khảo

- **OpenID Connect Back-Channel Logout 1.0 incorporating errata set 1** — định nghĩa Logout Token, metadata, HTTP POST và JWT validation: https://openid.net/specs/openid-connect-backchannel-1_0.html
- **OpenID Connect Back-Channel Logout 1.0 final (2022)** — bản trước errata, cần chú ý khác biệt về claim khi so sánh tài liệu cũ: https://openid.net/specs/openid-connect-backchannel-1_0-final.html
- **Spring Security Reference — OIDC Logout, Servlet** — Back-Channel Logout DSL, OidcSessionRegistry, handler và cookie name: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- **Spring Security Reference — OIDC Logout, Reactive** — ServerHttpSecurity, ReactiveOidcSessionRegistry, reactive handler: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- **Spring Security API — OidcLogoutConfigurer.BackChannelLogoutConfigurer** — xác minh availability và version của <code>logoutUri</code>: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/client/OidcLogoutConfigurer.BackChannelLogoutConfigurer.html
- **Spring Security Reference — Session Management và Logout** — HTTP session invalidation và logout handlers.
- **Spring Session Reference — Redis HTTP Session/WebSession** — chia sẻ session qua nhiều instance.
- **OpenID Connect Core 1.0** — ID Token, <code>iss</code>, <code>sub</code>, <code>sid</code> trong profile liên quan.
- **OpenID Connect RP-Initiated Logout 1.0** — cơ chế logout bắt đầu từ Client, khác Back-Channel Logout.
- **RFC 7009 — OAuth 2.0 Token Revocation** — thu hồi token, không tương đương hủy local session.
- **RFC 7519 — JSON Web Token (JWT)** và **RFC 8417 — Security Event Token** — JWT claims và security event semantics.
