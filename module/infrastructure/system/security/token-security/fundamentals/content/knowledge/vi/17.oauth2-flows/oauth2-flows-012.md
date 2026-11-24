# Choosing flow by client type — Chọn luồng OAuth 2.0 theo loại client

## 1. Chọn flow từ ranh giới tin cậy, không từ tên framework

Trong chương **OAuth2 flows** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, việc chọn OAuth 2.0/OIDC flow quyết định **ai xác thực**, **ai nhận credential**, **ai giữ token**, **ai được phép cấp quyền** và **resource server nào chấp nhận access token**. Một flow đúng tên nhưng dùng sai loại client hoặc sai mô hình triển khai vẫn có thể khiến access token/refresh token bị đánh cắp hay phát lại.

Ví dụ, cùng một sản phẩm `sales-dashboard` có thể có:

- Web application chạy giao diện ở browser nhưng **backend giữ session/token**.
- Single-page application (SPA) chạy toàn bộ logic phía browser.
- Ứng dụng native trên điện thoại hoặc desktop.
- Job backend định kỳ không có người dùng tương tác.
- Thiết bị TV chỉ có remote, không thuận tiện nhập mật khẩu.
- Một service nhận token của Alice và cần gọi service khác **thay mặt Alice**.

Các client này **không nên dùng cùng một flow và cùng cách lưu credential**. Câu hỏi ban đầu không phải “dùng JWT hay opaque token”, mà là **client có thể giữ secret không, có end-user không, có browser an toàn không, và yêu cầu quyền thuộc user hay application?**

> **Quy tắc nền:** Ứng dụng có người dùng tương tác thường dùng **Authorization Code + PKCE** (kèm OIDC khi cần đăng nhập). Workload không có người dùng, hành động bằng quyền chính nó thường dùng **Client Credentials** hoặc một workload-identity/profile tương ứng. Thiết bị hạn chế nhập liệu có thể dùng **Device Authorization Grant**. Gọi downstream thay mặt user cần **delegation/token exchange** nếu hệ thống hỗ trợ — không tự chuyển tiếp token sai audience.

### Sau bài học

Bạn có thể:

1. Phân biệt **public client** và **confidential client** theo khả năng giữ credential, không theo việc có giao diện đẹp hay chạy ở browser.
2. Chọn flow cho SPA, backend web, BFF, native/mobile, desktop/CLI, TV/IoT, machine-to-machine và nhiều service.
3. Hiểu vai trò PKCE, client authentication, redirect URI, state/nonce, consent, scope và audience.
4. Giải thích vì sao implicit grant, password grant và việc chuyển tiếp token tùy tiện không phải lựa chọn mặc định an toàn.
5. Thiết kế refresh-token rotation, revocation, token storage và kiểm tra access token ở resource server.
6. Áp dụng ma trận quyết định và kiểm thử âm/dương cho Java/Spring Security.

## 2. Những câu hỏi phải trả lời trước khi chọn OAuth flow

### 2.1. Client là public hay confidential?

Theo mô hình OAuth, **confidential client** có khả năng bảo vệ credential nhờ chạy trong một môi trường tin cậy, ví dụ backend quản lý secret, private key, certificate hoặc workload identity. **Public client** không thể giữ credential bí mật trước người sử dụng thiết bị hay attacker có quyền đọc mã/bundle, ví dụ SPA, ứng dụng mobile hoặc app desktop phân phối đến người dùng.

| Thuộc tính | Public client | Confidential client |
| --- | --- | --- |
| Thường chạy ở đâu? | Browser SPA, native mobile, desktop/CLI phân phối rộng | Backend, BFF, service hoặc job server-side được kiểm soát |
| Secret nhúng trong app có thật sự bí mật không? | **Không** | Có thể, nếu được bảo vệ đúng |
| Có thể xác thực client bằng một secret bí mật chung? | Không thể dựa vào secret nhúng | Có thể dùng registered client authentication |
| PKCE trong Authorization Code | Thiết yếu với các client public dùng code flow | Nên dùng, bổ sung bảo vệ code interception |
| Vị trí token | Phải cân nhắc rủi ro môi trường client | Có thể lưu server-side với secret manager/token store |
| Mức độ tin request chỉ vì biết `client_id` | Không | Cũng không; phải xác thực client nếu flow yêu cầu |

**Client ID không phải mật khẩu.** `client_id` thường là định danh công khai. Một SPA có `client_secret` viết trong JavaScript **vẫn là public client**, không trở thành confidential client nhờ tên biến `secret`.

**Confidential không đồng nghĩa an toàn tuyệt đối**: secret trên backend có thể lộ từ logs, CI, container image, memory dump hoặc cấu hình sai. Client authentication vẫn phải có secret rotation, TLS, access control, audit và least privilege.

### 2.2. Có resource owner là con người đang tương tác?

- **Có end-user muốn đăng nhập hoặc ủy quyền:** thường bắt đầu bằng Authorization Code + PKCE, OIDC scope `openid` khi cần **authentication**, và API scopes khi cần **authorization**.
- **Không có end-user, service hành động nhân danh chính nó:** cân nhắc Client Credentials. **Không** dựng một user giả rồi lấy password của user đó để chạy scheduler.
- **User đã đăng nhập tại service A, service A muốn thực hiện hành động tại B thay user:** cần đánh giá **on-behalf-of/delegation**. Token Exchange (RFC 8693) hoặc profile được AS hỗ trợ có thể thích hợp.
- **Thiết bị có browser/input hạn chế:** Device Authorization Grant là một lựa chọn khi user có thiết bị khác để xác thực.

### 2.3. Client có thể chuyển hướng browser và nhận callback không?

Authorization Code flow đưa end-user đến authorization endpoint của AS, sau đó AS trả **authorization code** về redirect URI đã được đăng ký. Ứng dụng native có thể dùng browser ngoài và redirect URI thích hợp; SPA thường dùng browser redirect về chính origin của nó; BFF nhận callback ở backend.

Nếu thiết bị không có browser hoặc không tiện nhập, Device Authorization Grant cho phép người dùng mở `verification_uri` trên thiết bị khác rồi nhập `user_code`.

### 2.4. Quyền được cấp là gì và cho resource nào?

Flow không tự trả lời mọi câu hỏi phân quyền. AS cần xác minh client registration, grant type, consent/user policy nếu áp dụng, **scope** và **resource/audience**. Resource server vẫn phải xác minh chữ ký JWT hoặc opaque introspection, `iss`, `aud`, `exp`, scope và quyền object/tenant.

Một token `aud=inventory-api` không được dùng ở `orders-api` chỉ vì cả hai cùng tin một AS. Một `scope=orders.read` cũng không cho Alice quyền đọc mọi đơn hàng thuộc tenant khác.

## 3. Ma trận chọn flow theo loại client

| Loại client / tình huống | Flow hoặc kiến trúc nên đánh giá | Client authentication | Điểm cần bảo vệ |
| --- | --- | --- | --- |
| **Web server-side** có backend giữ credential/session | Authorization Code + PKCE (+ OIDC khi cần đăng nhập) | Confidential client auth tại token endpoint | Callback, CSRF/session, secret, token store |
| **BFF** (browser chỉ giữ cookie phiên, token ở backend) | Authorization Code + PKCE tại BFF | Confidential client auth theo registration | Cookie `HttpOnly`/`Secure`, CSRF, server-side RT |
| **SPA thuần browser**, không có backend giữ secret | Authorization Code + PKCE | Public client, không nhúng client secret | XSS, redirect, state, refresh policy, token exposure |
| **Native mobile** iOS/Android | Authorization Code + PKCE qua **external browser** | Public client | OS redirect dispatch, PKCE, secure storage |
| **Desktop app / CLI có browser** | Authorization Code + PKCE với system browser và loopback/redirect phù hợp | Thường public client | Local callback interception, CSRF/mix-up, credential storage |
| **TV, console, thiết bị input hạn chế** | Device Authorization Grant nếu AS hỗ trợ | Public client theo đăng ký | User-code phishing, polling interval, device code lifetime |
| **Backend batch/service không có user** | Client Credentials | Confidential client auth, workload identity theo profile | Secret/key, audience/scope, token cache |
| **Service A gọi B thay user** | Token Exchange/OBO hoặc delegation profile được AS hỗ trợ | Service A xác thực với AS/STS | Subject/actor, quyền bị giới hạn, audience B |
| **Service A gọi B bằng quyền riêng của A** | Client Credentials hoặc workload federation | Service/machine auth | Tránh dùng app-only quyền cao thay cho user authorization |
| **User đã cấp RT và cần AT mới** | Refresh Token Grant (nếu RT được cấp) | Binding/auth theo loại client | Rotation, replay, đồng bộ nhiều tab/Pod |
| **Xác thực end-user mà không cần gọi API** | Authorization Code + PKCE với OIDC | Tùy client type | Verify ID token đúng client, nonce khi áp dụng, session |

Đây là **ma trận quyết định khởi đầu**, không phải yêu cầu mọi AS đều hỗ trợ toàn bộ flow. Nhà cung cấp IAM có thể giới hạn grant types, yêu cầu sender-constrained tokens, PAR, request object hoặc triển khai các extension. Một client có thể sở hữu **nhiều registration** cho các use case khác nhau nhưng không được dùng nhầm token giữa user, service và resource.

### 3.1. Cây quyết định

~~~mermaid
flowchart TD
    S["Client cần token hoặc OIDC login"] --> U{"Có end-user đang tương tác?"}
    U -->|"Không"| M{"Hành động bằng quyền service?"}
    M -->|"Có"| CC["Client Credentials / workload federation"]
    M -->|"Không, thay user đã xác thực"| EX["Token Exchange / OBO theo AS contract"]
    U -->|"Có"| B{"Có browser/system browser dùng được?"}
    B -->|"Không hoặc input hạn chế"| DEVICE["Device Authorization Grant nếu hỗ trợ"]
    B -->|"Có"| H{"Backend giữ token/secret?"}
    H -->|"Có"| BFF["Authorization Code + PKCE tại backend/BFF"]
    H -->|"Không"| PUBLIC["Authorization Code + PKCE cho public client"]
    PUBLIC --> N{"Native app?"}
    N -->|"Có"| SYS["External user-agent + OS redirect + secure storage"]
    N -->|"Không"| SPA["SPA browser: chống XSS, token/RT policy"]
    BFF --> OIDC["Kèm OIDC nếu cần đăng nhập user"]
    PUBLIC --> OIDC
~~~

Cây trên không thay thế threat modeling. “Có browser” chưa đủ để quyết định redirect URI hợp lệ; “có backend” cũng chưa chứng minh client giữ secret an toàn.

## 4. Web server-side và BFF: Authorization Code + PKCE

Một web application server-side có backend tin cậy nên để **backend** thực hiện authorization code redemption, nhận AT/RT, lưu chúng trong token store và duy trì session ứng dụng bằng cookie. **BFF (Backend for Frontend)** dùng cách tổ chức này để tách browser khỏi bearer tokens dùng gọi API.

### 4.1. Luồng tiêu biểu

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant BR as Browser
    participant BFF as Web Backend / BFF
    participant AS as Authorization Server
    participant RS as orders-api
    U->>BR: Truy cập ứng dụng
    BR->>BFF: GET /orders
    BFF-->>BR: Redirect đến AS với state + PKCE
    BR->>AS: Authorization request
    AS->>U: Login và consent nếu policy yêu cầu
    AS-->>BR: Redirect về registered callback với code + state
    BR->>BFF: GET /callback?code=...&state=...
    BFF->>BFF: Verify state, session và PKCE verifier
    BFF->>AS: POST /token: code + code_verifier + client auth
    AS-->>BFF: AT, ID token nếu OIDC, RT nếu policy
    BFF->>BFF: Validate login, lưu token an toàn, tạo session
    BFF-->>BR: Set-Cookie: application session
    BR->>BFF: GET /orders với session cookie
    BFF->>RS: Authorization: Bearer AT dành cho orders-api
    RS->>RS: Verify token + audience + scope + ACL
    RS-->>BFF: Dữ liệu được phép
    BFF-->>BR: Giao diện / JSON cần thiết
~~~

**Điểm mạnh:** Browser không cần cầm OAuth access/refresh token cho API. Token có thể nằm trong backend encrypted store, giúp giảm rủi ro bị JavaScript trực tiếp đọc và giảm bề mặt lộ từ URL/analytics.

**Giới hạn:** Nếu BFF bị XSS ở trang, script độc hại vẫn có thể **gửi request qua session cookie** thay user; cookie `HttpOnly` không tự chặn XSS-induced actions. Phải dùng CSRF defense phù hợp, cookie `Secure`/`SameSite`, input encoding/CSP khi thích hợp, session expiration và kiểm tra authorization cho từng request.

### 4.2. Confidential client authentication

Backend có thể xác thực bằng `client_secret_basic`, `private_key_jwt`, mTLS hoặc phương thức được AS đăng ký. Secret/private key phải được bảo vệ trong secret manager/HSM/KMS hoặc hệ thống tương đương; không gửi client secret ra browser, local storage, URL hay log.

PKCE vẫn có giá trị cho confidential client vì ràng buộc authorization code với một transaction. Client authentication và PKCE xử lý **rủi ro khác nhau**; không dùng một thứ để tuyên bố thứ kia luôn thừa.

### 4.3. Redirect URI, state và session binding

Backend phải:

- Đăng ký redirect URI chính xác theo AS policy; không lấy URI tùy ý do caller cung cấp.
- Liên kết `state` đủ ngẫu nhiên với một phiên/authorization transaction, so khớp khi nhận callback.
- Tạo `code_verifier` đủ entropy và `code_challenge_method=S256`, giữ verifier phía server theo transaction.
- Chống login CSRF, mix-up giữa nhiều AS/issuer bằng cách xác minh issuer response hoặc ràng buộc issuer/transaction theo profile.
- Xử lý authorization code **dùng một lần**, không gửi lại vô hạn sau timeout.
- Nếu dùng OIDC, xác minh ID token (issuer, audience/client, signature, expiry, nonce nếu đã yêu cầu và các điều kiện profile).

### 4.4. Không đồng nhất “BFF” và “confidential SPA”

Một SPA có JavaScript code gọi `/token` **trực tiếp từ browser** không trở thành confidential client chỉ vì website được phục vụ từ backend. BFF đúng nghĩa đặt **OAuth token handling và API calls liên quan token phía backend**, còn browser giữ một application session. Nếu frontend vẫn được trả AT/RT để tự gọi RS, threat model phải coi phần đó là **public client**.

## 5. SPA thuần browser: Authorization Code + PKCE, không dùng implicit

SPA chạy trong browser là public client. Người dùng hoặc một script độc hại có thể xem JavaScript bundle, storage và network traffic trong môi trường browser. Do đó, **không có client secret thực sự bí mật để nhúng trong SPA**.

### 5.1. Luồng SPA hiện đại

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as Browser SPA
    participant AS as Authorization Server
    participant API as Resource Server
    SPA->>SPA: Tạo state, PKCE verifier/challenge
    SPA->>AS: Browser redirect /authorize?response_type=code...
    AS-->>SPA: Redirect về SPA với code + state
    SPA->>SPA: Xác minh state, callback và code verifier
    SPA->>AS: POST /token với code + code_verifier (không client secret)
    AS-->>SPA: Access token; RT nếu chính sách cho phép
    SPA->>API: Bearer access token đúng audience
    API->>API: Kiểm tra issuer, aud, exp, scope, ACL
~~~

Authorization code được đổi tại token endpoint sau redirect; access token không được chủ động đặt trong fragment response từ authorization endpoint như **implicit grant** cổ điển.

### 5.2. Vì sao không chọn implicit grant?

Implicit grant (`response_type=token`) được thiết kế trong bối cảnh web client cũ, đưa access token trực tiếp qua front-channel authorization response. Thiết kế hiện đại ưu tiên Authorization Code + PKCE vì có một bước đổi code được ràng buộc với verifier và giảm rủi ro token lộ tại authorization response.

**OAuth 2.0 Security Best Current Practice (RFC 9700) khuyến nghị tránh implicit**. Không lập luận rằng “SPA không giữ secret nên phải dùng implicit”: PKCE được xây để public clients có thể dùng code flow mà không dựa vào secret nhúng.

### 5.3. Browser token storage và refresh token

Client-side token storage không có vị trí “bất khả xâm phạm” trước XSS. `localStorage`/`sessionStorage` có thể bị script cùng origin đọc; biến trong memory có thể giảm tồn tại lâu nhưng vẫn có thể bị truy cập khi code JS độc hại chạy trong ứng dụng. Cookie HttpOnly không cho JS đọc trực tiếp nhưng nếu ứng dụng dùng cookie làm session, phải kiểm soát CSRF và hành vi request thay user.

Khi AS cấp refresh token cho SPA, cần hiểu **refresh token rotation hoặc sender constraint/replay detection**, lifetime và logout/revocation policy theo OAuth Security BCP. Không mặc định mọi AS cho phép refresh token ở browser. Có thể dùng BFF nếu cần giữ long-lived credentials ngoài JavaScript.

### 5.4. CORS không phải authorization

SPA có thể gọi token endpoint/API qua CORS khi AS/RS cho phép origin hợp lệ. Nhưng **CORS không thay OAuth token validation**: một non-browser client không bị browser CORS enforcement, và server vẫn phải kiểm tra AT. Không mở `Access-Control-Allow-Origin: *` với credentialed requests một cách tùy tiện, không trả secret chỉ vì request có `Origin` đúng.

## 6. Native mobile và desktop: external browser + PKCE

Ứng dụng mobile, desktop, CLI được phân phối tới người dùng thường là **public client**, ngay cả khi cài đặt từ một app store hay tệp thực thi có chữ ký. Một attacker có thể trích xuất secret từ bundle, patch binary hoặc quan sát môi trường chạy. Vì vậy không dùng client secret cố định nhúng trong ứng dụng làm bằng chứng xác thực bí mật.

### 6.1. Vì sao nên dùng external user-agent?

RFC 8252 (OAuth 2.0 for Native Apps) khuyến nghị native apps sử dụng **external user-agent**, thường là browser hệ thống hoặc cơ chế browser được OS hỗ trợ, thay vì tự nhúng form đăng nhập trong embedded webview do ứng dụng kiểm soát.

Lợi ích:

- User nhập thông tin xác thực vào môi trường browser/identity provider được tách khỏi code ứng dụng.
- AS có thể tận dụng SSO, MFA, passkeys và chính sách đăng nhập của browser.
- Ứng dụng không trực tiếp thu thập mật khẩu của user.
- Cookie và cơ chế bảo vệ phiên của browser hệ thống có thể được sử dụng theo khả năng nền tảng.

**Không dùng embedded webview để đọc mật khẩu hoặc cookie đăng nhập** chỉ để “trải nghiệm liền mạch”. Nếu AS hỗ trợ SDK/native app auth framework, SDK vẫn phải tuân theo nguyên tắc browser ngoài, PKCE và redirect validation.

### 6.2. Redirect URI dành cho native

Các lựa chọn theo RFC 8252 và khả năng OS/AS gồm:

| Kiểu redirect | Ví dụ giả định | Lưu ý bảo mật |
| --- | --- | --- |
| **App-claimed HTTPS URI** | `https://app.example.test/oauth/callback` | OS xác nhận ứng dụng có quyền nhận URI theo cơ chế ứng dụng liên kết domain |
| **Private-use URI scheme** | `com.example.sales:/oauth2redirect` | Scheme có thể bị app khác đăng ký/tranh chấp; PKCE rất quan trọng |
| **Loopback redirect cho desktop** | `http://127.0.0.1:54321/callback` | Local listener, cổng ngẫu nhiên, bind interface loopback, PKCE và state |

Đối với native loopback redirect, OAuth native-app profile cho phép **HTTP trên loopback interface** theo quy tắc riêng, vì browser và client cùng máy; đây **không phải** quyền sử dụng plaintext HTTP tới AS/token endpoint hoặc API trên mạng. Authorization/token endpoints vẫn phải dùng TLS và certificate validation.

Không tự thay đổi redirect URI tùy ý. AS phải kiểm tra URI đã đăng ký và áp **ngoại lệ cổng loopback phù hợp native app profile** nếu hỗ trợ. Ứng dụng nên dùng listener loopback ràng buộc localhost, không mở công khai `0.0.0.0` để nhận code.

### 6.3. Native callback và chống code interception

Một ứng dụng ác ý có thể cố giành quyền xử lý cùng private-use URI scheme. PKCE với `S256` giúp code bị bắt được không dễ đổi thành token nếu attacker không có `code_verifier`.

Native app phải:

1. Sinh `state` và `code_verifier` riêng cho từng authorization transaction; không dùng lại vô hạn.
2. Gửi user tới đúng authorization endpoint của AS được phê duyệt qua external browser.
3. Kiểm tra `state`, expected redirect, issuer/transaction và chống nhận callback từ phiên khác.
4. Đổi code tại token endpoint đúng issuer bằng `code_verifier`, không gửi static secret nhúng.
5. Lưu access/refresh token bằng OS secure storage thích hợp, giới hạn quyền đọc.
6. Gọi API qua TLS/certificate validation, không lấy AT từ ID token.

### 6.4. Desktop CLI: ưu tiên browser + loopback khi có thể

Một CLI do người dùng chạy có thể mở browser hệ thống, nhận callback trên loopback và thực hiện Authorization Code + PKCE. Nếu CLI chạy trong môi trường SSH không có browser hay khả năng mở callback, Device Authorization Grant có thể thích hợp **nếu AS và use case hỗ trợ**. Không nên mặc định CLI thu mật khẩu rồi gửi qua password grant.

CLI lưu token cần kiểm tra permission của file/token cache, không in token trong stdout, shell history, debug output và CI logs. Khi người dùng đăng xuất, phải xóa token cache local và revoke refresh token/grant nếu yêu cầu.

## 7. TV, console và thiết bị hạn chế input: Device Authorization Grant

OAuth 2.0 Device Authorization Grant (RFC 8628) phù hợp khi thiết bị **có kết nối mạng nhưng khó thực hiện interactive browser login**, chẳng hạn TV, console hoặc CLI không có browser tại máy chạy. User dùng điện thoại/laptop khác để mở verification page của AS và hoàn tất xác thực.

### 7.1. Luồng polling chuẩn

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant D as TV / Device Client
    participant AS as Authorization Server
    participant B as Browser trên điện thoại
    D->>AS: POST device_authorization: client_id, scope
    AS-->>D: device_code, user_code, verification_uri, expires_in, interval
    D-->>U: Hiển thị verification_uri và user_code
    U->>B: Mở URI và nhập user_code
    D->>AS: POST /token với device_code (polling)
    AS-->>D: authorization_pending
    B->>AS: User login, kiểm tra thiết bị và consent
    AS-->>B: Hoàn tất ủy quyền
    D->>AS: POST /token theo interval
    AS-->>D: Access token (RT nếu policy cho phép)
    D->>D: Lưu token bằng secure storage có thể có
~~~

Ví dụ phản hồi của device authorization endpoint:

~~~json
{
  "device_code": "<opaque-device-code>",
  "user_code": "K7PD-3HFX",
  "verification_uri": "https://auth.example.test/activate",
  "expires_in": 900,
  "interval": 5
}
~~~

Giá trị trên chỉ minh họa. `device_code` là credential giữa device và AS, không nên hiển thị cho user hoặc đưa vào log; `user_code` được user nhập trên verification page. AS có thể cung cấp `verification_uri_complete` để thiết bị hiển thị QR code dễ sử dụng, nhưng UI cần cảnh báo người dùng xác nhận đúng thiết bị/session.

### 7.2. Token request trong device flow

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=<device-code>&client_id=tv-client
~~~

Khi user chưa xác thực, AS có thể trả `authorization_pending`. Khi client poll quá nhanh, AS có thể trả `slow_down`. RFC 8628 yêu cầu poll theo `interval` (mặc định 5 giây nếu không được trả), tăng khoảng ít nhất 5 giây khi `slow_down`, dừng khi `expired_token`, `access_denied` hoặc thành công.

**Không coi polling lặp trước khi user chấp thuận là replay độc hại**, nhưng không mở hàng trăm concurrent requests hoặc thử mãi sau khi device code hết hạn.

### 7.3. Rủi ro device-code phishing

Attacker có thể hiển thị `user_code` và dụ nạn nhân nhập nó tại AS để cấp token cho **thiết bị của attacker**. Vì thế:

- Trang xác nhận của AS phải cho user thấy client/device đang được ủy quyền, tên resource/scopes và cảnh báo phù hợp.
- User nên chỉ nhập code khi chính mình chủ động bắt đầu login trên thiết bị mong muốn.
- AS giới hạn thời hạn, tốc độ thử user code và consent/risk policy.
- Client phải bảo vệ `device_code`, chặn reuse bất thường và bảo vệ AT/RT sau khi cấp.

Không dùng device flow như đường đi tắt để bỏ MFA/consent hoặc cho một thiết bị kẻ tấn công tự lấy token bằng thao tác của user không hiểu rõ.

## 8. Backend và machine identity: Client Credentials

Nếu service hành động bằng quyền của chính nó, không có end-user đang cấp delegation, **Client Credentials** thường phù hợp hơn browser redirect hoặc Device Grant.

Ví dụ job `inventory-sync` gọi `inventory-api`:

~~~mermaid
sequenceDiagram
    autonumber
    participant JOB as inventory-sync (confidential client)
    participant AS as Authorization Server
    participant API as inventory-api (RS)
    JOB->>AS: POST /token: grant=client_credentials + client auth
    AS->>AS: Kiểm tra client, scope, resource, workload policy
    AS-->>JOB: AT aud=inventory-api, scope=inventory.read
    JOB->>API: Bearer AT
    API->>API: Check issuer, aud, exp, scope, service/tenant policy
    API-->>JOB: Dữ liệu được phép
~~~

Request minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <registered-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
~~~

`Authorization: Basic` biểu diễn `client_secret_basic` nếu AS đăng ký kiểu đó; hệ thống nhạy cảm có thể dùng `private_key_jwt`, mTLS hoặc workload federation theo profile AS. Không giả định mọi confidential client phải dùng Basic, hay một client secret chung của tất cả microservices là an toàn.

### 8.1. Không có user trong client credentials

Client credentials access token thường đại diện cho **service principal/client**, không phải Alice. Một API yêu cầu user-owned order permission phải xác minh đúng principal/grant và không “cho qua” bằng service token có scope trùng tên.

Các quy tắc:

- Cấp scope theo quyền **của service**, tách khỏi user-delegated scopes khi phù hợp.
- Cấp token cho audience cụ thể, ví dụ `inventory-api`.
- Giới hạn TTL; cache token còn hạn, dùng single-flight để tránh nhiều request cấp token đồng thời.
- Không mặc định cấp refresh token trong client credentials (RFC 6749: **SHOULD NOT**).
- Revoke/rotate client secret, certificate, private key khi nghi ngờ lộ; thay client credential không tự thu hồi mọi access token đã phát hành.

### 8.2. Workload identity federation và credential ngắn hạn

Trong cloud/Kubernetes, workload có thể sở hữu một identity assertion ngắn hạn để trao đổi với AS hoặc cloud STS theo profile nhà cung cấp, thay vì giữ long-lived shared client secret trong file cấu hình. **Đây không đồng nghĩa với một OAuth grant chuẩn duy nhất**: cần xem STS hỗ trợ JWT bearer assertion, token exchange, workload federation hoặc cơ chế riêng nào.

AS/STS phải kiểm tra **issuer, audience, subject, token expiry, signature và workload trust policy**, đồng thời chỉ cấp target AT đúng resource/scope. Không gửi Kubernetes service account token bất kỳ đến mọi API rồi cho rằng nó là access token OAuth phổ quát.

### 8.3. Một scheduler “làm thay người dùng” không phải client credentials mặc định

Ví dụ Alice đặt lịch “gửi báo cáo mỗi sáng” khi Alice đã offline. Nếu báo cáo cần **quyền delegated của Alice**, service cần một grant/consent hợp lệ và refresh/token-exchange hoặc cơ chế delegation được AS hỗ trợ. Chỉ dùng app-only token có `reports.admin` có thể vượt quyền Alice. Thiết kế cần nêu rõ task tồn tại khi Alice bị khóa/rút quyền hay không, TTL/refresh revocation và audit subject/actor.

## 9. Service A gọi B thay user: Token Exchange và On-Behalf-Of

Một use case khác client credentials: Alice gọi `orders-api`, rồi orders cần gọi `payments-api` để thực hiện thao tác **thuộc quyền Alice**. Token vào orders có `aud=orders-api`; nó **không được tự động forward** sang payments.

### 9.1. Luồng được kiểm soát

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant O as orders-api / downstream client
    participant AS as AS / STS
    participant P as payments-api
    U->>O: AT1: aud=orders-api, scope=orders.read
    O->>O: Verify AT1 + quyền nghiệp vụ caller
    O->>AS: Xin exchange: AT1, audience=payments-api, scope cần thiết
    AS->>AS: Kiểm tra client, subject/actor, grant và policy
    AS-->>O: AT2: aud=payments-api, scope được cấp
    O->>P: POST /payments với AT2
    P->>P: Verify AT2 + subject/actor + domain policy
    P-->>O: Kết quả hợp lệ hoặc từ chối
~~~

OAuth 2.0 Token Exchange (RFC 8693) cung cấp một framework, nhưng **AS phải hỗ trợ**. Việc client gửi `subject_token` không tự cho phép tạo token mới có scope admin. AS phải ràng buộc actor/client, subject, grant, resource và quyền tương ứng; RS downstream cần xác minh cả token và policy nghiệp vụ.

### 9.2. Token exchange request minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <orders-service-client-authentication>
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&subject_token=<incoming-access-token>&subject_token_type=urn:ietf:params:oauth:token-type:access_token&resource=https%3A%2F%2Fpayments.example.test%2F&scope=payments.create
~~~

Phản hồi có thể chứa access token `aud=payments-api` nếu AS cấp phép, nhưng **không phải mọi AS đều giữ subject/actor claims giống nhau**. RFC 8693 có các khái niệm `act`, subject token, actor token; cần làm rõ hợp đồng token profile, audit và quyền.

### 9.3. Tránh confused deputy

Nếu orders có service token `payments.admin` riêng và API chỉ kiểm tra Alice đã đăng nhập rồi dùng token đó hoàn tiền, orders có thể trở thành **confused deputy**. Phòng vệ:

1. Kiểm tra Alice được phép thực hiện **hành động trên object cụ thể**.
2. Khi downstream phải quyết định theo user, dùng delegation/OBO profile có actor/subject rõ và đúng audience.
3. Tách endpoint/tác vụ **app-only** khỏi **user-delegated**, giới hạn service scopes và audit.
4. Không fallback từ token exchange bị từ chối sang app-only credential mạnh hơn.

### 9.4. Không nhầm token exchange với refresh grant

**Refresh grant** dùng RT gắn grant ban đầu để lấy AT mới theo policy. **Token Exchange** lấy token thuộc một ngữ cảnh và xin token cho một ngữ cảnh/resource khác theo AS/STS policy. Cả hai đều gọi token endpoint trong nhiều triển khai, nhưng khác **mục tiêu, credential, subject/actor semantics và authorization controls**.

## 10. Những grant không nên chọn làm mặc định

### 10.1. Implicit grant

**Không chọn `response_type=token` chỉ vì ứng dụng là SPA hoặc native public client.** Dùng Authorization Code + PKCE, với AS hỗ trợ code flow cho public client và redirect validation đúng.

### 10.2. Resource Owner Password Credentials (ROPC)

Password grant cho client nhận trực tiếp username/password của resource owner để đổi token. Đây là mô hình không phù hợp với xác thực hiện đại: phá ranh giới tin cậy của user với IdP, cản trở MFA/passkeys/federation và tăng nguy cơ client giữ hoặc ghi lộ mật khẩu. **OAuth Security BCP RFC 9700 quy định MUST NOT dùng resource owner password credentials grant**.

Không dùng `grant_type=password` để “đỡ phải redirect” cho SPA, mobile, CLI hoặc service account. Các lựa chọn khác theo client type gồm code + PKCE, device flow và client credentials/workload identity.

### 10.3. Client credentials để giả danh human user

Không nhét một user ID vào request client credentials và nghĩ AS tự động cấp **delegated access token**. Nếu service cần thực hiện quyền của user, phải có grant/delegation policy thật; nếu dùng app-only, RS phải chỉ cấp những quyền **riêng của service**.

### 10.4. Token forwarding toàn tuyến

Không dùng một access token bearer duy nhất qua gateway → orders → payments → shipping mà bỏ kiểm tra `aud` ở mỗi RS. Mỗi resource cần token có audience của chính nó và policy scope thích hợp. Token Exchange hoặc các access tokens riêng cho từng resource thường giảm token-substitution risk.

### 10.5. Tự chế grant thay vì dùng profile có bảo vệ

Một API tự định nghĩa `POST /login {username,password}` rồi trả JWT không tự động là OAuth 2.0/OIDC. Nếu không có chuẩn grant, client registration, AS policy, issuer/JWKS, audience, token lifecycle, revocation và các bảo vệ tương ứng, hệ thống có thể bị token confusion và replay. Custom protocol cần threat modeling và review riêng; không gọi nó là “Authorization Code flow” chỉ vì cuối cùng trả JWT.

## 11. Các lớp bảo vệ áp dụng cho nhiều loại flow

**Chọn đúng grant type mới là bước đầu.** Cùng Authorization Code + PKCE nhưng dùng redirect sai, bỏ kiểm tra issuer hoặc lưu RT ở nơi công khai vẫn có thể bị tấn công.

### 11.1. PKCE, state, nonce và client authentication giải quyết vấn đề khác nhau

| Cơ chế | Áp dụng ở đâu? | Nguy cơ được giảm thiểu | Không thay thế |
| --- | --- | --- | --- |
| **PKCE** `code_challenge` / `code_verifier` | Authorization Code flow | Code bị chặn/đánh cắp khó được đổi bởi bên không có verifier | Client authentication, issuer/redirect/consent policy |
| **state** | Authorization request/callback | Ràng buộc authorization response với transaction, chống CSRF/mix-up theo thiết kế | PKCE, ID-token nonce, access-token validation |
| **nonce** trong OIDC | Authentication request và ID-token validation khi áp dụng | Ràng buộc ID token với authentication transaction, giảm replay/substitution | OAuth state, scope/audience của AT |
| **Client authentication** | Token endpoint/STS với confidential client | Chứng minh client đã đăng ký khi đổi code/refresh/client credentials | User login, API authorization, PKCE |
| **Redirect URI validation** | Authorization endpoint/token endpoint theo flow | Ngăn code bị trả tới URI không được đăng ký | PKCE, state |
| **Issuer identification** | Client processing và token validation | Ngăn nhầm AS/token từ issuer khác | Audience, client ID |
| **Audience restriction** | AS issuance và RS verification | Ngăn token dành cho resource A dùng ở B | Scope, tenant/object ACL |
| **Sender constraint** | DPoP/mTLS access token, khi có | Giảm khả năng dùng token chỉ bị sao chép | TTL, issuer/audience/scope, domain authorization |

**PKCE không biến public client thành confidential client.** Bên nào cũng có thể tự tạo một authorization request với challenge; PKCE bảo vệ **mối liên hệ giữa code và verifier**, chứ không chứng minh public app là phần mềm chính hãng chỉ nhờ `client_id`.

### 11.2. Authorization request an toàn

Ví dụ request được encode trên URL:

~~~http
GET /authorize?response_type=code&client_id=sales-dashboard&redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&scope=openid%20orders.read&state=<random-state>&nonce=<random-nonce>&code_challenge=<s256-pkce-challenge>&code_challenge_method=S256 HTTP/1.1
Host: auth.example.test
~~~

Các placeholder phải được tạo mới theo mỗi authorization transaction và giữ/bảo vệ đúng loại client. `nonce` ở đây phù hợp với OIDC authentication request; OAuth request chỉ xin API access token **không mặc định cần nonce**. Nếu AS hỗ trợ Resource Indicators (RFC 8707), client có thể yêu cầu `resource=https://orders.example.test/`, nhưng AS vẫn phải áp allowlist.

### 11.3. Redirect URI và mix-up giữa nhiều AS

Một ứng dụng sử dụng nhiều IdP có thể bị **authorization server mix-up** nếu nó nhận code từ AS-A rồi gửi đến token endpoint AS-B, hoặc tin response không thuộc transaction đã mở. Ràng buộc authorization transaction với **issuer dự kiến**, client registration, redirect URI, state/PKCE; sử dụng issuer identifier trong authorization response khi AS hỗ trợ RFC 9207 và xác minh metadata/token theo profile.

AS/client cần kiểm tra redirect URI theo đăng ký; tránh wildcard tùy ý và open redirect. Native loopback redirect có ngoại lệ cổng theo RFC 8252 nhưng **không** đồng nghĩa mọi redirect gần giống được phép.

### 11.4. PAR/JAR khi authorization request nhạy cảm

Một số AS hỗ trợ **Pushed Authorization Requests (PAR, RFC 9126)** hoặc **JWT-Secured Authorization Request (JAR, RFC 9101)** để tăng tính toàn vẹn/bảo vệ tham số authorization request trong những thiết kế phù hợp. Đây là các **cơ chế bổ sung**, không thay đổi thực tế rằng browser, native hay backend vẫn cần chọn flow theo khả năng giữ credential và user interaction.

Không tự giả định tất cả AS hỗ trợ PAR/JAR, cũng không coi một signed request object là bằng chứng user đã consent hoặc client được cấp scope vượt registration.

### 11.5. Chặn downgrade và token exfiltration

- Mọi endpoint AS, token endpoint, introspection, JWKS, revocation và resource API cần TLS với certificate/hostname validation.
- Không chuyển bearer/refresh token qua redirect tới host khác hoặc HTTP plaintext.
- Không gửi `code`, `code_verifier`, `client_secret`, `access_token`, `refresh_token` vào logs/traces/analytics.
- Không gọi JWKS URL từ `jku` của token chưa xác minh; issuer/trust configuration phải độc lập với untrusted token content.
- Browser logout cần CSRF protection/cookie policy; native logout cần xóa secure storage và revoke RT/grant khi policy yêu cầu.

### 11.6. OIDC đăng nhập khác OAuth cấp quyền API

OAuth 2.0 tập trung vào **authorization delegation**. OIDC bổ sung lớp **authentication** với ID token và user claims. Một ID token `aud=sales-dashboard` không trở thành access token `aud=orders-api` chỉ vì cả hai đều là JWT ký bởi cùng AS/OP.

Khi sử dụng OIDC:

1. Client xác minh ID token đúng issuer, audience/client, chữ ký, thời gian, nonce khi áp dụng và session semantics.
2. Client dùng access token được cấp **cho đúng API** để gọi RS.
3. RS kiểm tra AT profile, issuer, `aud`, `exp`, scope và quyền domain; không nhận ID token thay AT.
4. `auth_time`/`max_age` liên quan độ mới authentication, không tự thay thế AT TTL hoặc refresh policy.

## 12. Access token format không quyết định OAuth flow

**JWT vs opaque** là lựa chọn **token representation và validation**, không phải grant type. Authorization Code, Client Credentials hoặc Device Grant đều có thể trả JWT access token hoặc opaque access token tùy AS.

| Đặc điểm | JWT access token | Opaque access token |
| --- | --- | --- |
| Format | Thường là JWT ký (JWS) có claims theo profile | Chuỗi không có ý nghĩa tự diễn giải tại client/RS |
| Xác minh ở RS | Public key/JWKS, signature, claims | Introspection hoặc trạng thái tin cậy của AS |
| Audience | RS kiểm tra `aud` trong token đã verify | RS cần metadata/resource binding đáng tin từ AS |
| Thời hạn | `exp` và policy/clock skew | `active`/`exp`/TTL theo introspection contract |
| Thu hồi sớm | Có thể cần denylist/state check nếu verify offline | AS có thể trả `active=false`, lưu ý cache |
| Khi AS outage | Có thể verify bằng keys cache theo policy | Introspection có thể không khả dụng; phải fail closed khi không thể xác minh |

**Không chọn Client Credentials chỉ vì muốn opaque token**, cũng không chọn implicit chỉ vì muốn JWT. Hai trục quyết định độc lập: **flow cấp quyền** và **token validation strategy**.

### 12.1. Access token TTL và refresh-token policy

Access token nên có TTL dựa trên risk, độ trễ thu hồi và tải AS. Một token bị lộ có thể bị replay cho tới hết hạn nếu là bearer AT. Refresh token giúp xin AT mới nhưng là credential có nguy cơ kéo dài phiên; AS có thể yêu cầu **rotation hoặc sender-constrained refresh token**, lifetime và revocation theo client type/risk.

Ví dụ:

~~~text
AT1: aud=orders-api, scope=orders.read, TTL=5 phút
RT1: grant=user-A + client=sales-dashboard, theo AS refresh policy

RT1 --refresh hợp lệ--> AT2 + RT2 (nếu dùng rotation)
RT1 --reuse sau rotation--> có thể bị coi là replay và revoke token family
Logout --> revoke RT/grant, xóa local session/token
~~~

Với `client_credentials`, client thông thường xác thực lại để lấy AT mới; **không mặc định có RT**. Với SPA hoặc native, cần kiểm soát đồng thời refresh bởi nhiều tab/thread/Pod để tránh RT rotation race.

### 12.2. Multi-resource và cache key

Token cache nên phân biệt tối thiểu **issuer, client registration, subject/actor hoặc machine principal, tenant, audience/resource, granted scope, token binding identity** và phiên/grant theo kiến trúc. Không cache một token duy nhất theo `client_id` rồi trả cho cả Alice/Bob hoặc orders/payments.

Một token đúng issuer/chữ ký/scope nhưng sai `aud` vẫn phải bị RS từ chối. Với sender-constrained AT, cache còn phải ràng buộc khóa/certificate đã cấp token; không dùng AT DPoP-bound với DPoP key khác hoặc mTLS-bound token với cert khác.

### 12.3. 401 và 403 không dùng để chọn flow tùy tiện

Khi RS trả `401 invalid_token` do AT hết hạn, client có thể dùng refresh grant hoặc client credentials theo **grant đã đăng ký** để lấy AT mới. Không chuyển từ code flow sang password grant như một cách fallback. Khi RS trả `403 insufficient_scope`, chỉ refresh lại cùng grant/scope chưa chắc giải quyết được; cần AS authorization hợp lệ để cấp quyền thêm.

Nếu RS trả 403 do object-level authorization, client không thể xin `admin` để bỏ kiểm tra domain. Phải tuân thủ quyền chủ thể và chính sách tổ chức.

## 13. Java/Spring Security: ví dụ cho các loại client

Các ví dụ dưới đây minh họa Spring Boot/Spring Security 6.x và những abstraction thông dụng. Tên class/import và cấu hình có thể khác theo phiên bản; cần kiểm tra tài liệu phiên bản triển khai. **Không copy client secret hoặc private key mẫu vào production.**

### 13.1. Web backend / BFF — authorization_code

Khai báo OAuth client registration server-side:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            issuer-uri: https://auth.example.test
        registration:
          sales-dashboard:
            provider: company-as
            client-id: sales-dashboard
            client-secret: EXTERNAL_SECRET_REFERENCE
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
~~~

`EXTERNAL_SECRET_REFERENCE` phải được thay bằng secret được inject an toàn từ secret manager hoặc cơ chế phù hợp, không phải giá trị literal có thể sử dụng. Spring Security OAuth2 Login có thể hỗ trợ login OIDC và authorized-client management:

~~~java
@Configuration
@EnableWebSecurity
class BffSecurity {

    @Bean
    SecurityFilterChain bffChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
~~~

**Quan trọng:** Cấu hình này minh họa **login và local session cleanup**, không tự cho thấy tất cả phiên bản đã bật `S256` PKCE cho confidential client. Phải cấu hình PKCE qua authorization request resolver khi cần và xác minh provider/client settings thực tế. `logout()` xóa session local **không tự revoke RT ở AS**; cần revocation/logout coordination nếu policy yêu cầu. Với browser cookie, giữ CSRF defense phù hợp.

### 13.2. Public SPA — cấu hình registration từ AS, không nhúng secret

Pseudocode client-side:

~~~text
onLogin():
    state = secureRandom()
    verifier = secureRandomCodeVerifier()
    challenge = BASE64URL(SHA256(ASCII(verifier)))
    persistPerTransaction(state, verifier, expectedIssuer)
    redirectExternalBrowserToAuthorize(
        response_type="code",
        client_id="spa-client",
        redirect_uri=registeredSpaRedirect,
        code_challenge=challenge,
        code_challenge_method="S256",
        state=state,
        scope="openid orders.read")

onCallback(code, state):
    validateAndConsumeTransaction(state)
    postTokenEndpointWith(code, code_verifier, client_id)
    validateTokenResponseAndOidcIdTokenWhenApplicable()
    useAccessTokenOnlyForItsAudience()
~~~

Không có `client_secret` trong SPA. `persistPerTransaction` phải tránh trộn nhiều tab/phiên hoặc vô tình lộ verifier qua analytics. AS phải cho phép redirect origin theo registration, cấu hình CORS phù hợp với browser token endpoint khi flow hỗ trợ, và áp token storage/RT policy phù hợp rủi ro XSS.

### 13.3. Backend machine client — client_credentials

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
        registration:
          inventory-worker:
            provider: company-as
            client-id: inventory-worker
            client-secret: EXTERNAL_SECRET_REFERENCE
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
~~~

Java manager:

~~~java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());

    return manager;
}
~~~

Lấy AT:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-worker")
        .principal("inventory-worker-prod")
        .build();

OAuth2AuthorizedClient authorized = manager.authorize(request);
if (authorized == null) {
    throw new IllegalStateException("Client authorization failed");
}

String accessToken = authorized.getAccessToken().getTokenValue();
// Chỉ gửi qua HTTPS tới resource được AS cấp token;
// không log hoặc sử dụng cho một API sai audience.
~~~

`OAuth2AuthorizedClientManager` hỗ trợ client token acquisition/reuse theo configured provider và store, nhưng **không tự bảo đảm** token đúng audience nếu AS không có resource issuance policy. Nó cũng không tự là distributed single-flight cho mọi Pod; cần cache key/coordination phù hợp. Không dùng ví dụ client credentials để biểu diễn quyền của human user.

### 13.4. Resource server — verify AT không phụ thuộc client flow

Một `orders-api` có thể nhận user-delegated AT và/hoặc app-only AT theo endpoint policy, nhưng **luôn phải xác minh token dành cho mình**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

~~~java
@Configuration
@EnableWebSecurity
class OrdersResourceSecurity {

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation("https://auth.example.test")
                .build();

        OAuth2TokenValidator<Jwt> defaultValidator =
                JwtValidators.createDefaultWithIssuer(
                        "https://auth.example.test");

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaultValidator, audienceValidator));
        return decoder;
    }

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll());

        http.oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Ví dụ có thể cần API decoder khác tùy bản Spring Security; chỉ tin metadata/JWKS của **issuer đã cấu hình**, không follow issuer/JWKS URL từ token chưa xác minh. Cần bổ sung token `typ`/profile validation, issuer/audience/time, thuật toán phù hợp, phân biệt user vs app-only principal và object-level authorization. `SCOPE_orders.read` **không** tự cho phép đọc mọi order.

### 13.5. Kiểm tra quyền theo object

~~~java
@Service
class OrderService {
    private final OrderRepository repository;
    private final OrderPolicy policy;

    OrderService(OrderRepository repository, OrderPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    public OrderView get(String id, Authentication caller) {
        Order order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        if (!policy.canRead(caller, order)) {
            throw new AccessDeniedException("Access denied");
        }
        return OrderView.from(order);
    }
}
~~~

`OrderRepository`, `OrderPolicy`, `OrderView` và `OrderNotFoundException` là domain abstractions của ví dụ. `OrderPolicy` phải dựa trên principal đã được xác minh và trạng thái tenant/ownership/trạng thái đơn hàng đáng tin; không chỉ đọc `orderId`/`tenantId` từ request rồi cho phép. User-delegated và app-only token có thể cần **những nhánh authorization policy khác nhau**.

## 14. Lỗi phổ biến khi chọn flow và cách nhận diện

### 14.1. “SPA có secret nên dùng Client Credentials”

SPA được gửi client secret trong JavaScript bundle rồi gọi `grant_type=client_credentials` để lấy AT rộng, sau đó truy cập dữ liệu user.

**Sai ở đâu:** Secret có thể bị trích xuất, client là public, và app-only token có thể cấp quyền vượt user. Sửa bằng Authorization Code + PKCE cho user-delegated access, hoặc BFF nếu cần bảo vệ long-lived credential và dùng confidential client auth ở backend.

### 14.2. “Mobile app cần lấy mật khẩu vì không có backend”

Native app dùng form nội bộ thu mật khẩu Alice rồi gọi password grant. Cách này trao mật khẩu cho client, cản trở MFA/SSO và vi phạm hướng dẫn OAuth Security BCP. Dùng external browser + Authorization Code + PKCE, redirect URI native đúng profile, secure storage và consent/policy từ AS.

### 14.3. “TV không có bàn phím nên dùng device_code và poll liên tục”

Device client poll token endpoint mỗi 100 ms để mong có AT ngay. AS có thể trả `slow_down`, rate limit hoặc coi client bất thường. Dùng interval được cấp, tăng thời gian khi `slow_down`, dừng sau `expired_token`/`access_denied`; UI phải giúp user nhận biết đúng device để tránh device-code phishing.

### 14.4. “Backend có client credentials là được làm thay Alice”

`orders-api` nhận request refund từ Alice và dùng `payments.admin` service AT để hoàn tiền vì service có quyền. Nếu Alice không có quyền refund, service đã trở thành **confused deputy**. Phải kiểm tra caller/domain authorization; khi downstream cần user context thì token exchange/OBO theo policy, không âm thầm nâng quyền.

### 14.5. “Cùng issuer nên có thể forward access token”

Token `aud=orders-api` được gửi sang `payments-api` vì hai service tin `https://auth.example.test`. Nếu payments bỏ qua audience, client có thể dùng token sai mục đích. Mỗi RS kiểm tra expected audience, hoặc xin AT mới cho resource đích.

### 14.6. “OIDC ID token là JWT nên có thể gọi API”

Frontend gửi ID token có `aud=spa-client` làm bearer AT tới `orders-api`. Signature có thể hợp lệ nhưng token được phát hành để **client xác thực user**, không phải API authorization. RS phải từ chối ID token; frontend sử dụng access token `aud=orders-api`.

### 14.7. “RT sống lâu thì AT TTL ngắn luôn an toàn”

AT có TTL 5 phút, RT lưu trong browser storage bị XSS lấy được và không bị rotate/revoke. Attacker liên tục dùng RT để lấy AT mới. Cần kiểm soát nơi lưu, refresh rotation/sender constraint, expiry, revocation và incident response; cân nhắc BFF.

### 14.8. “Bị 401 thì đổi sang grant khác cho tới khi thành công”

Client nhận `invalid_grant` do authorization code đã dùng và thử `grant_type=password`, hoặc sau `insufficient_scope` tự xin client credentials admin token. Đây là **authorization bypass/fallback** nguy hiểm. Retry/recovery phải phù hợp grant ban đầu, không tự chọn quyền mạnh hơn khi flow chính thất bại.

### 14.9. “CORS khóa origin nên API không cần kiểm tra token”

Một API browser-facing bật CORS allowlist và coi request từ allowed origin là được xác thực. Non-browser clients không bị CORS policy của browser; attacker có thể gọi trực tiếp API. RS vẫn phải xác minh bearer token và quyền object; CORS chỉ là bảo vệ browser origin access trong phạm vi của nó.

### 14.10. “Logout chỉ xóa cookie”

Browser xóa session cookie nhưng backend RT còn active, hoặc native app xóa AT nhưng để lại RT. Một phiên/actor có RT vẫn có thể xin AT mới. Phải đóng local session, revoke RT/grant theo policy, phối hợp refresh đang chạy và quản lý AT còn hạn.

## 15. Ma trận kiểm thử flow theo loại client

Một môi trường kiểm thử nên có AS test, JWKS/introspection test, client registrations public/confidential, browser/native/device simulators và hai RS (`orders-api`, `payments-api`). Không sử dụng credential production trong test/capture. **Mỗi kiểm thử âm cần một kiểm thử dương tương ứng**, tránh báo đạt do AS hoặc network luôn từ chối mọi request.

| ID | Loại client / tình huống | Kết quả mong đợi |
| --- | --- | --- |
| F01 | Confidential web client Code + PKCE, correct redirect/state/client auth | Đổi code thành công theo scope/audience được phê duyệt |
| F02 | Web client sai client secret/private-key assertion | AS từ chối client authentication |
| F03 | Web callback có `state` sai hoặc không thuộc transaction | Client từ chối, không đổi code |
| F04 | Authorization code đúng nhưng `code_verifier` sai | AS từ chối token request |
| F05 | Cùng authorization code đổi lần thứ hai | AS từ chối single-use replay |
| F06 | Redirect URI không được đăng ký | AS không phát code cho URI đó |
| F07 | Browser BFF nhận AT/RT từ AS | Token được giữ server-side, không đưa RT vào response frontend |
| F08 | BFF session cookie thiếu CSRF defense ở state-changing endpoint | Kiểm thử phát hiện/cấm request cross-site không hợp lệ |
| F09 | SPA Code + PKCE không dùng client secret | AS cho phép public client đúng registration và PKCE |
| F10 | SPA nhúng `client_secret` trong JavaScript rồi coi đó là confidential | Kiểm thử/review phát hiện secret exposure, không cấp app-only quyền trái policy |
| F11 | SPA thiếu PKCE hoặc dùng method không được policy cho phép | AS từ chối hoặc không cấp theo policy |
| F12 | SPA dùng `response_type=token` implicit khi AS cấm | AS từ chối legacy implicit flow |
| F13 | SPA có refresh-token rotation và hai tab refresh cùng RT | Client coordination; AS phát hiện reuse theo policy |
| F14 | Native external browser + PKCE + redirect hợp lệ | Authorization hoàn tất, callback đúng transaction |
| F15 | Native callback bị app khác chặn, không có PKCE verifier | Không thể đổi code tại AS |
| F16 | Native app dùng loopback redirect và port ngẫu nhiên theo profile | AS xử lý registered loopback URI đúng quy tắc |
| F17 | Native app mở listener loopback trên external interface | Kiểm thử/cấu hình phát hiện và ngăn exposure |
| F18 | Native app hardcode secret trong binary | Không được coi là confidential client chỉ nhờ secret này |
| F19 | Native app dùng embedded webview để thu user password | Không phù hợp kiến trúc; thay bằng external browser |
| F20 | Device grant nhận `authorization_pending` | Poll theo interval, không coi là token issuance thành công |
| F21 | Device grant nhận `slow_down` | Tăng interval đúng RFC 8628 |
| F22 | Device code `expired_token` hoặc `access_denied` | Dừng polling và hiển thị trạng thái phù hợp |
| F23 | Device phishing: attacker dụ user xác nhận session khác | AS/UI hiển thị client/device và giới hạn grant; có cơ chế phòng vệ |
| F24 | Client credentials của service được đăng ký cho inventory | AS cấp AT đúng inventory audience/scope |
| F25 | Service không có client authentication hợp lệ | AS từ chối grant |
| F26 | Client credentials token gửi đến endpoint user-only | RS từ chối nếu policy yêu cầu user-delegated principal |
| F27 | Service xin scope/resource ngoài allowlist | AS từ chối hoặc giới hạn theo policy |
| F28 | AT `aud=orders-api` được forward sang payments | Payments từ chối sai audience |
| F29 | Token Exchange được AS hỗ trợ, subject/actor/resource hợp lệ | Cấp AT downstream đúng quyền và audience |
| F30 | Token Exchange yêu cầu `payments.admin` khi caller không có quyền | AS từ chối privilege escalation |
| F31 | Token Exchange không được AS hỗ trợ | Không fallback sang service admin token trái policy |
| F32 | OIDC ID token được dùng như AT gọi API | RS từ chối token type/audience confusion |
| F33 | JWT AT có chữ ký/issuer đúng nhưng thiếu `aud` theo profile | RS từ chối |
| F34 | JWT AT hết hạn nhưng client vẫn gửi | RS trả invalid token; client recovery theo grant |
| F35 | Opaque AT introspection `active=false` | RS từ chối |
| F36 | Introspection hoặc JWKS TLS lỗi | Fail closed, không cấp quyền thiếu bằng chứng |
| F37 | Token scope đúng nhưng object thuộc tenant khác | RS từ chối theo domain authorization |
| F38 | Refresh token bị revoke/logout nhưng client cố refresh | AS từ chối; client không retry vô hạn |
| F39 | AT DPoP/mTLS-bound dùng với key/cert không khớp | RS từ chối sender binding |
| F40 | Token cache theo `client_id` trộn Alice/Bob hoặc orders/payments | Test phát hiện; phải phân vùng principal/audience |
| F41 | Multi-AS callback có issuer khác transaction | Client từ chối mix-up |
| F42 | Redirect sau token endpoint tới host lạ | Client không tự chuyển credential qua redirect |
| F43 | CLI chạy trong môi trường không có browser, AS hỗ trợ device grant | Có thể hoàn tất device authorization với user trên thiết bị khác |
| F44 | Client Credentials job dùng RT dù AS không cấp RT | Client không giả định RT tồn tại, xin AT mới qua client authentication |
| F45 | Authorization Code flow trả `scope` hẹp hơn request | Client dùng **granted scope**, không tự coi requested scope đã được cấp |
| F46 | User consent scope nhưng thiếu quyền trên bản ghi | RS tiếp tục từ chối theo object/tenant policy |
| F47 | AS cấp token cho nhiều audience ngoài client policy | Test xác định lỗ hổng issuance và yêu cầu giới hạn resource |
| F48 | API Gateway xác minh chung nhưng downstream bỏ `aud` | Kiểm thử route/backend phát hiện cross-resource token substitution |

### 15.1. Cách tách lỗi flow khỏi lỗi xác minh token

Giả sử thử nghiệm F28 nhận 401 vì JWKS fetch sai. Điều đó **không chứng minh** payments đang kiểm tra audience. Hãy chuẩn bị:

~~~json
{
  "access_token_for_orders": {
    "iss": "https://auth.example.test",
    "aud": ["orders-api"],
    "scope": "orders.read"
  },
  "access_token_for_payments": {
    "iss": "https://auth.example.test",
    "aud": ["payments-api"],
    "scope": "payments.read"
  }
}
~~~

Các JSON object là **claims mô tả test**, không phải JWT. Tạo AT test với chữ ký, `exp` và profile đúng để token `aud=payments-api` qua kiểm tra ở payments, còn token `aud=orders-api` phải bị payments từ chối. Sau đó kiểm tra API vẫn thực thi domain ACL.

### 15.2. Kiểm thử concurrency và kết quả không chắc chắn

**Authorization code** phải single-use: hai request đổi cùng code tại AS chỉ được tối đa một winner; client bị mất response không được mong AS luôn trả lại token cũ. **Refresh token rotation** phải xử lý concurrent tabs/Pods bằng single-flight/token store version/CAS; AS vẫn phải phát hiện reuse. **Device polling** nhiều request trước user approval là bình thường, nhưng phải tuân thủ interval/rate limit.

Với token endpoint timeout sau khi AS đã commit, client phải coi kết quả là **unknown outcome** và xử lý theo grant, không retry mù quáng credential single-use hay fallback sang grant quyền cao hơn.

### 15.3. Kiểm tra logs và network

Trong mọi flow, xác minh:

- Không có access token, refresh token, authorization code, PKCE verifier, client secret/private key trong logs, metrics labels, URLs hoặc analytics.
- Browser, native và service đều xác minh TLS certificate/hostname của AS và RS; không dùng `trust-all`.
- Device code không bị in vào log; user code được hiển thị đúng UX và giới hạn thời gian.
- Không forward header `Authorization` tới host/resource chưa được phê duyệt.
- 401/403 không bao gồm raw token hoặc thông tin private về signing keys.

## 16. Bốn bài toán chọn flow có lời giải

### Bài toán A: Trang quản trị có backend và cần phiên người dùng

Một ứng dụng quản trị có backend Java, frontend React, cần login SSO và gọi `orders-api` thay Alice. Đội phát triển muốn SPA tự lấy AT/RT vì “React dễ dùng OAuth SDK”.

**Phân tích:** Ứng dụng có backend giữ credential, nghiệp vụ nhạy cảm và user session. **BFF với Authorization Code + PKCE và OIDC** là một lựa chọn mạnh để browser không trực tiếp giữ RT. Backend lưu AT/RT trong protected store, browser dùng cookie session `HttpOnly`/`Secure`, CSRF defense và backend kiểm tra quyền trước khi gọi API. Nếu chọn SPA trực tiếp vẫn có thể dùng code + PKCE, nhưng cần chấp nhận threat model XSS và refresh policy riêng.

**Không chọn:** Client Credentials cho browser gọi API thay Alice; password grant để lấy mật khẩu user; implicit chỉ vì frontend là React.

### Bài toán B: Ứng dụng mobile offline không có backend riêng

Ứng dụng mobile cần cho user login tại IdP và sync dữ liệu khi online. Developer đề xuất đóng gói `client_secret` trong app và dùng client credentials.

**Phân tích:** Native app là **public client**, secret không thể giữ bí mật trước người dùng/attacker cài app. Chọn **Authorization Code + PKCE qua external browser**, dùng redirect URI native đúng profile, OS secure storage, access token audience hẹp và RT rotation/expiry theo AS nếu cần sync dài hạn. Khi user logout, xóa credential local và revoke RT/grant theo policy. Offline access chỉ phù hợp khi threat model và AS cho phép; không giữ token vô hạn để “hỗ trợ offline”.

**Không chọn:** Nhúng shared client secret hoặc password grant; dùng ID token làm access token cho API.

### Bài toán C: TV cần đăng nhập tài khoản và gọi API

TV không tiện nhập username/password; người dùng có điện thoại. Developer muốn hiển thị mã QR đến một website tùy ý do TV cung cấp.

**Phân tích:** Chọn **Device Authorization Grant** khi AS hỗ trợ. TV nhận `device_code` và `user_code`, hiển thị verification URI **do AS cấp**, user xác nhận trên website IdP thật; TV poll đúng interval. AS cần chống device-code phishing bằng hiển thị client/device/scopes và yêu cầu user xác nhận phiên mà họ chủ động bắt đầu.

**Không chọn:** TV thu mật khẩu trực tiếp, poll mỗi 100 ms, hoặc tin một verification URL do bên thứ ba không được phê duyệt cung cấp.

### Bài toán D: Order service gọi Payment service

Alice gọi orders để hủy một đơn hàng; orders cần yêu cầu payments thực hiện refund. Service đang sở hữu app-only token `payments.admin` cho maintenance.

**Phân tích:** Nếu refund là hành động **của Alice**, phải xác minh Alice được quyền refund order cụ thể và lựa chọn delegation model. Khi payments cần user/actor, dùng **Token Exchange/OBO** qua AS/STS có policy, cấp AT `aud=payments-api` và scope hẹp. App-only service credential chỉ dùng cho tác vụ hệ thống được cho phép riêng, không fallback khi user token exchange bị từ chối.

**Không chọn:** Forward AT `aud=orders-api` sang payments, hoặc dùng `payments.admin` bỏ qua quyền Alice.

## 17. Checklist chọn flow trước khi đưa vào production

### 17.1. Phân loại client đúng

1. **Vị trí chạy:** Token handling nằm trong browser, native app, server/BFF hay workload tự động?
2. **Khả năng giữ secret:** Client có thực sự giữ private key/secret khỏi user và untrusted scripts không? Nếu không, đánh dấu **public**.
3. **Có end-user?** Access token thể hiện quyền delegated user hay app-only service identity?
4. **Khả năng browser:** Có thể dùng external/system browser và nhận redirect URI an toàn? Nếu không, Device Grant có được AS hỗ trợ không?
5. **Multi-hop:** Có cần gọi RS B thay mặt user được xác thực ở RS A? Có token exchange/OBO và actor/subject policy không?

### 17.2. Đặt đúng grant và client authentication

6. **Code + PKCE:** User-interactive public clients có dùng Authorization Code + `S256` PKCE và `state`/OIDC nonce khi áp dụng không?
7. **Confidential client:** Backend có client authentication được đăng ký, secret/key trong protected store, rotation và audit không?
8. **Native redirect:** External browser, URI dispatch/loopback đúng profile, không embedded password webview?
9. **Device polling:** `interval`, `slow_down`, `expires_in`, UX anti-phishing và dừng polling được xử lý?
10. **Machine access:** Client Credentials/workload identity không tự giả danh user, scope/audience hẹp, AT cache an toàn?
11. **Deprecated/insecure flow:** Không dùng implicit hoặc ROPC làm đường mặc định; không fallback sang grant mạnh hơn sau lỗi?

### 17.3. Authorization, token và vòng đời

12. **Issuer và metadata:** AS/token/JWKS endpoints đến từ trust configuration; không tin unverified `iss`/`jku` URL?
13. **Client registration:** Redirect URIs, grants, scopes, client auth method, audience allowlist được quản lý?
14. **Scope/consent:** AS chỉ cấp quyền đã được client/user/admin policy cho phép, token response phản ánh granted scope?
15. **Audience:** Mỗi RS chỉ nhận AT dành cho mình, kể cả khi cùng issuer với service khác?
16. **Token purpose:** API từ chối ID token, refresh token, JWT client assertion thay access token?
17. **RS authorization:** Kiểm tra token signature/introspection, `iss`, `aud`, `exp`, scope, tenant, object ACL, actor/service policy?
18. **Refresh/revocation:** Có rotation hoặc sender constraints theo client type, single-flight và quy trình logout/revoke RT/grant?
19. **AT còn hạn:** Logout hoặc hạ quyền cần hiệu lực trong bao lâu; JWT offline và opaque introspection cache có đáp ứng SLA?
20. **Token storage:** Browser, native secure storage, backend secret store và cache key đã được threat-model hóa?

### 17.4. Network, logs và kiểm thử

21. **TLS:** Certificate/hostname validation hoạt động ở AS, token endpoint, JWKS/introspection/revocation và mọi API hops?
22. **Redirect security:** Không cho credential đi theo redirect cross-origin hoặc downgrade từ HTTPS sang HTTP?
23. **Sender constraint:** Nếu dùng DPoP/mTLS, RS có kiểm tra key/cert binding và proof đúng request?
24. **Logging:** Không ghi raw AT/RT, code, `code_verifier`, client assertion, client secret/private key vào logs/traces?
25. **Tests:** Có test âm/dương cho từng flow, code replay, issuer mix-up, sai audience, domain policy, logout race, device polling và token exchange?

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Một SPA có `client_id` và chuỗi `client_secret` trong JavaScript bundle. Nó là public hay confidential client?

**Trả lời:** **Public client**. Secret nhúng có thể bị trích xuất, không chứng minh danh tính client bí mật. User-interactive SPA thường dùng Authorization Code + PKCE, hoặc chuyển token handling sang BFF nếu kiến trúc cho phép.

**Câu 2.** Một website có backend và React frontend. Chỉ cần backend tồn tại thì token tự động an toàn?

**Trả lời:** Không. Phải xem **token endpoint call, AT/RT storage và API calls thực sự nằm ở đâu**. Nếu browser vẫn giữ RT, phần đó chịu rủi ro public client; BFF đúng nghĩa giữ token ở backend và dùng session cookie với CSRF/XSS controls.

**Câu 3.** Mobile app có thể dùng Client Credentials với một client secret nhúng để đọc dữ liệu của Alice?

**Trả lời:** Không nên. Mobile là public client; Client Credentials là quyền của **service**, không phải user-delegated. Dùng external browser + Authorization Code + PKCE và quyền Alice tại AS/RS.

**Câu 4.** Một CLI chạy trên server không mở được browser thì luôn phải dùng password grant?

**Trả lời:** Không. Nếu cần user grant và AS hỗ trợ, Device Authorization Grant có thể phù hợp; nếu là machine job độc lập thì Client Credentials/workload identity mới đúng. Không thu mật khẩu user làm lối tắt.

**Câu 5.** Authorization Code + PKCE bảo vệ điều gì, và có biến SPA thành confidential client không?

**Trả lời:** PKCE ràng buộc authorization code với verifier của transaction, giảm nguy cơ code interception. Nó **không** biến public client thành confidential, không thay redirect/state/client policy hoặc token storage.

**Câu 6.** Device Grant poll 5 giây/lần và AS trả `slow_down`. Client nên làm gì?

**Trả lời:** Tăng khoảng polling theo RFC 8628 (thêm ít nhất 5 giây), không gửi parallel polling; dừng khi grant bị từ chối/hết hạn hoặc đã cấp token.

**Câu 7.** Một access token là JWT, vậy có phải nó được cấp bằng Authorization Code flow?

**Trả lời:** Không. **JWT/opaque** mô tả token format, không quyết định **grant type**. JWT có thể được cấp bằng client credentials, code flow, device grant hoặc profile khác tùy AS.

**Câu 8.** Service A có app-only token `payments.admin`. Nó có thể dùng để xử lý bất kỳ yêu cầu thanh toán nào của Alice?

**Trả lời:** Không. Nếu thao tác là quyền của Alice, phải kiểm tra user/domain authorization; app-only quyền cao không được dùng để vượt quyền caller. Token Exchange/OBO có thể phù hợp nếu AS/RS hỗ trợ.

**Câu 9.** Access token `aud=orders-api` có thể dùng ở `payments-api` khi cùng issuer và scope trùng tên?

**Trả lời:** Không. Payments phải xác minh expected audience của chính mình; AS có thể cấp token mới đúng resource bằng flow/grant phù hợp.

**Câu 10.** Khi SPA nhận `401 invalid_token` có nên tự động thử `grant_type=password` hoặc client credentials?

**Trả lời:** Không. Client phải phục hồi trong **grant và session policy đã đăng ký**, ví dụ refresh hợp lệ hoặc authorization mới. Không đổi sang flow yếu hơn hoặc quyền rộng hơn để vượt lỗi.

**Câu 11.** Nếu AS cấp `orders.read` nhưng client đã yêu cầu `orders.read orders.write`, RS có thể dùng requested scope không?

**Trả lời:** Không. Chỉ **granted scope** trong token/metadata đã được xác minh có giá trị; RS còn phải kiểm tra ownership/tenant/ACL.

**Câu 12.** ID token OIDC với `aud=sales-dashboard` và `sub=alice` có được gửi làm bearer token đến orders API không?

**Trả lời:** Không. ID token dành cho OIDC client xác thực end-user; RS yêu cầu đúng access-token profile và `aud=orders-api` cùng scope/domain permission.

## 19. Tài liệu chuẩn tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): bốn OAuth roles, client types, authorization grants, scope và token endpoint.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn bảo vệ OAuth hiện đại, tránh ROPC/implicit, chống token theft và replay.
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): bảo vệ authorization code flow bằng code challenge/verifier.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): external browser và redirect URI native.
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device code, user code, polling và `slow_down`.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): xử lý issuer/mix-up trong authorization response.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata của AS và endpoints.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource/audience trong authorization và token issuance.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject/actor token và delegation sang resource downstream.
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests (PAR)](https://www.rfc-editor.org/rfc/rfc9126), [RFC 9101 — JWT-Secured Authorization Request (JAR)](https://www.rfc-editor.org/rfc/rfc9101): bảo vệ authorization request khi AS hỗ trợ.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi bearer AT tới RS, xử lý `invalid_token` và `insufficient_scope`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims, issuer, audience, profile JWT AT.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662), [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): opaque token validation và thu hồi token.
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705), [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC login, nonce, `auth_time` và khác biệt authentication/authorization.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html), [OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html), [Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): integration cho web/BFF, outbound token và inbound token.

**Điểm cần ghi nhớ:** **Chọn OAuth 2.0 flow theo khả năng giữ credential, môi trường browser/native/device và nguồn quyền user/service**, không theo việc token có dạng JWT hay công nghệ frontend đang dùng. **Authorization Code + PKCE** phù hợp cho user-interactive web/SPA/native với cách xử lý token khác nhau theo client type; **Client Credentials** dành cho service hành động bằng quyền riêng; **Device Authorization Grant** cho thiết bị hạn chế input; **Token Exchange/OBO** cho delegation downstream được AS cho phép. Với mọi flow, access token phải có **issuer, audience, scope, thời hạn và purpose đúng**, được vận chuyển/lưu trữ an toàn và được resource server thực thi **object-level authorization** trước khi cho truy cập.
