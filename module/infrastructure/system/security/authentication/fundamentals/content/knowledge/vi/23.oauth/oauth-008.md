# OAuth threat — Mô hình đe dọa và bảo vệ luồng OAuth 2.0

## 1. OAuth threat là gì?

**OAuth threat** là các mối đe dọa nhắm vào quá trình cấp, trao đổi, sử dụng và thu hồi quyền truy cập theo OAuth 2.0. OAuth cho phép một client nhận quyền truy cập giới hạn tới tài nguyên được bảo vệ thông qua authorization server, mà không cần biết mật khẩu của người dùng ở resource server. Vì luồng này đi qua nhiều bên và thường có chuyển hướng trình duyệt, mã ủy quyền, token và các kênh trao đổi khác nhau, lỗi ở một ranh giới tin cậy có thể làm lộ token hoặc cấp quyền sai đối tượng.

Ví dụ: người dùng cho ứng dụng lịch bên thứ ba quyền đọc lịch làm việc. Ứng dụng chuyển người dùng tới authorization server, người dùng đăng nhập và chấp thuận scope, rồi client nhận authorization code và đổi code lấy access token. Nếu redirect URI bị kiểm tra lỏng, kẻ tấn công có thể lấy code. Nếu client không ràng buộc code với giao dịch đã bắt đầu bằng PKCE, code bị chặn có thể bị đổi lấy token. Nếu resource server không kiểm tra audience và scope, token có thể bị dùng ở API hoặc tài nguyên ngoài dự kiến.

Trong chương **OAuth** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, nội dung này kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học cần mô hình hóa ranh giới tin cậy giữa resource owner, client, authorization server và resource server; nhận diện phishing, replay, redirect abuse, token theft và lạm dụng quyền; từ đó thiết kế luồng cấp quyền an toàn.

**OAuth 2.0 là framework ủy quyền (authorization), không tự nó là giao thức xác thực danh tính người dùng.** Nếu ứng dụng cần đăng nhập và nhận thông tin xác thực người dùng, thường sử dụng OpenID Connect (OIDC) trên OAuth 2.0. Không được coi một access token OAuth bất kỳ là bằng chứng đăng nhập hoặc tự giải mã token để suy ra danh tính.

## 2. Các vai trò và tài sản cần bảo vệ

OAuth có bốn vai trò chính:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có quyền cấp quyền truy cập tài nguyên. | Người dùng có lịch làm việc. |
| **Client** | Ứng dụng yêu cầu quyền và dùng token gọi API. | Ứng dụng lịch bên thứ ba. |
| **Authorization Server (AS)** | Xác thực resource owner, thu thập consent và phát hành authorization code/token. | Dịch vụ OAuth của tổ chức. |
| **Resource Server (RS)** | Bảo vệ API/tài nguyên và kiểm tra access token. | Calendar API. |

Các tài sản nhạy cảm gồm:

- Credential người dùng và phiên đăng nhập tại authorization server.
- Authorization code, access token, refresh token và client credential.
- Redirect URI, client ID, client authentication method và metadata của issuer.
- Scope, audience, consent, tenant và liên kết giữa principal với tài nguyên.
- PKCE code verifier/challenge, state, OIDC nonce và các dữ liệu ràng buộc giao dịch.
- Khóa ký token, JWKS, khóa DPoP hoặc chứng chỉ mTLS.

### Ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Resource owner"]
    C["Client application"]
    AS["Authorization server"]
    RS["Resource server / API"]
    B["Browser / user agent"]
    U <--> B
    B <--> AS
    B <--> C
    C <-->|"Code + token endpoint"| AS
    C -->|"Access token"| RS
    RS -->|"Protected resource"| U
    X["Attacker<br/>phishing, redirect, malware,<br/>network/token theft"]
    X -.-> B
    X -.-> C
    X -.-> AS
    X -.-> RS
~~~

Trình duyệt và client thường không phải ranh giới tin cậy tuyệt đối. Authorization server phải xác minh giao dịch và client; resource server phải tự xác minh token và quyền; client phải bảo vệ token; người dùng cần được hiển thị đúng ứng dụng và quyền đang chấp thuận.

## 3. Phân biệt authorization, authentication và OIDC

| Khái niệm | Câu hỏi được trả lời | Bằng chứng thường gặp |
| --- | --- | --- |
| **Authentication** | Người dùng/chủ thể là ai? | Mật khẩu, passkey, MFA, chứng chỉ, phiên IdP. |
| **Authorization** | Chủ thể/client được làm gì trên tài nguyên nào? | Scope, role, policy, consent và access token. |
| **OAuth 2.0** | Client được cấp quyền truy cập tài nguyên ra sao? | Authorization code, access token, refresh token. |
| **OpenID Connect** | Người dùng đã được xác thực như thế nào với RP? | ID token và các claim OIDC được xác minh. |

Access token được phát hành cho resource server hoặc resource/audience đã định. ID token được phát hành trong OIDC cho client để xác minh sự kiện đăng nhập. Một token có thể là JWT hoặc chuỗi opaque; **không được đoán mục đích token chỉ từ định dạng**.

Nếu ứng dụng dùng OAuth để gọi API và đồng thời muốn đăng nhập người dùng, hãy dùng OIDC với các kiểm tra issuer, audience, signature, expiry, nonce và các claim cần thiết. Không dùng endpoint UserInfo hoặc access token sai audience như cách thay thế việc xác minh ID token.

## 4. Luồng Authorization Code và các điểm có thể bị tấn công

Với ứng dụng web/native hiện đại, Authorization Code Flow là lựa chọn cơ bản. PKCE ràng buộc code với client đã khởi tạo giao dịch:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant AS as Authorization server
    participant RS as Resource server
    U->>C: Bắt đầu kết nối
    C->>C: Sinh state, code_verifier, code_challenge
    C-->>U: Mở authorization request
    U->>AS: Client ID, redirect URI, scope, state, challenge
    AS->>U: Xác thực / consent
    U->>AS: Hoàn tất theo policy
    AS-->>C: Redirect với authorization code + state
    C->>C: So khớp state
    C->>AS: Đổi code + code_verifier
    AS->>AS: Kiểm tra code, client, redirect URI, PKCE
    AS-->>C: Access token (và refresh token nếu được cấp)
    C->>RS: API request + access token
    RS->>RS: Kiểm tra token và authorization
    RS-->>C: Protected resource
~~~

Các giá trị có vai trò riêng:

- **state:** ràng buộc authorization response với giao dịch đăng nhập/ủy quyền do client bắt đầu; giúp chống CSRF và response injection.
- **code_verifier/code_challenge (PKCE):** chứng minh bên đổi authorization code là bên giữ verifier đã tạo lúc bắt đầu.
- **nonce (OIDC):** ràng buộc ID token với yêu cầu xác thực OIDC; không thay thế state hoặc PKCE.
- **redirect_uri:** địa chỉ callback đã đăng ký và được so khớp theo chính sách chính xác.

Không tái sử dụng cùng một giá trị cho mọi giao dịch. State, nonce, verifier cần có entropy cao, được lưu gắn với giao dịch và tiêu thụ đúng một lần.

## 5. Redirect URI manipulation và open redirect

Một lỗi nghiêm trọng là authorization server chấp nhận redirect URI quá rộng, chẳng hạn kiểm tra bằng tiền tố hoặc cho phép mọi URL thuộc một domain không được quản lý chặt.

Kịch bản:

1. Client hợp lệ đăng ký callback HTTPS trên host ứng dụng.
2. Authorization server chấp nhận thêm URL gần giống hoặc một open redirect trên domain đó.
3. Attacker tạo request với redirect URI trỏ tới endpoint chuyển tiếp do họ kiểm soát.
4. Người dùng xác thực và authorization code bị gửi tới attacker.
5. Nếu không có PKCE hoặc các ràng buộc khác, attacker có thể đổi code lấy token.

Biện pháp:

- Đăng ký và so khớp redirect URI **chính xác** theo cấu hình client; không dùng wildcard hoặc kiểm tra tiền tố lỏng.
- Không cho redirect URI chứa open redirect hoặc tham số chuyển hướng tới domain tùy ý.
- Với native app, dùng redirect URI pattern phù hợp theo hướng dẫn cho ứng dụng native; ưu tiên claimed HTTPS redirect khi nền tảng hỗ trợ, hoặc loopback/private-use scheme theo profile được phép.
- Không đưa access token vào fragment hoặc query string của redirect URI.
- Dùng PKCE S256 để giảm hậu quả khi authorization code bị chặn.
- Kiểm thử encoded URL, dấu chấm, userinfo, port, subdomain gần giống và các dạng normalization.

Một open redirect ở chính client cũng nguy hiểm: dù authorization server so khớp callback hợp lệ, callback có thể chuyển tiếp code tới URL attacker. Không cho callback nhận tham số redirect tùy ý; nếu cần đích nội bộ, dùng allowlist và state giao dịch.

## 6. CSRF, login CSRF và response injection

Kẻ tấn công có thể khiến trình duyệt nạn nhân gửi hoặc nhận một authorization response không thuộc giao dịch mà nạn nhân đã khởi tạo. Hậu quả có thể là nạn nhân bị đăng nhập vào tài khoản của attacker, consent nhầm quyền hoặc gắn nhầm tài khoản.

**Login CSRF** có thể xảy ra khi client không ràng buộc callback với giao dịch ban đầu. Attacker khởi tạo luồng bằng tài khoản của họ, lấy response rồi khiến nạn nhân hoàn tất callback đó. Nạn nhân tưởng mình đang dùng tài khoản của mình nhưng thực tế thao tác dữ liệu trong tài khoản attacker.

Kiểm soát:

- Sinh state ngẫu nhiên, gắn với browser session/giao dịch và kiểm tra chính xác ở callback.
- Tiêu thụ state một lần; từ chối state thiếu, sai, hết hạn hoặc đã dùng.
- Dùng PKCE; không dựa vào state đơn lẻ để bảo vệ authorization code.
- Trong OIDC, xác minh nonce trong ID token với nonce của giao dịch.
- Ràng buộc callback với client, issuer, redirect URI và giao dịch đã bắt đầu.
- Bảo vệ cookie giao dịch và endpoint callback theo CSRF policy của ứng dụng.

**State không thay thế PKCE.** State giúp nhận biết response có khớp giao dịch của client không; PKCE bảo vệ việc đổi code. Một triển khai an toàn thường cần cả hai khi phù hợp.

## 7. Authorization code interception, injection và replay

Authorization code là credential ngắn hạn, dùng một lần để đổi token. Tuy vậy, nếu code bị lộ qua redirect, log, browser history, proxy hoặc app link, attacker có thể thử đổi nó.

Các nguy cơ:

- **Interception:** attacker lấy code từ callback hoặc kênh chuyển hướng.
- **Injection:** client nhận code không thuộc giao dịch mà nó khởi tạo.
- **Replay:** code đã dùng được gửi lại hoặc bị dùng đồng thời ở hai nơi.
- **Code substitution:** code hợp lệ của client/issuer/giao dịch khác bị đưa vào callback.

Biện pháp:

- PKCE S256 cho public clients và sử dụng rộng rãi cho Authorization Code Flow.
- Authorization code phải ràng buộc với client, redirect URI và PKCE challenge đã đăng ký.
- Code có thời hạn ngắn và chỉ đổi thành công một lần.
- Token endpoint phải xác minh client authentication khi client là confidential client.
- Callback kiểm tra state, issuer và giao dịch tương ứng trước khi đổi code.
- Không log authorization code hoặc token; redaction ở reverse proxy/APM.
- Với nhiều authorization server, dùng issuer identification và ràng buộc giao dịch để chống mix-up.

Không dùng implicit flow để trả access token trực tiếp trong browser redirect. Authorization Code + PKCE giảm việc token xuất hiện trong front channel và là mô hình phù hợp hơn cho client hiện đại.

## 8. PKCE downgrade và triển khai sai

PKCE sử dụng một code_verifier ngẫu nhiên và gửi code_challenge tương ứng trong authorization request. Khi đổi code, client gửi verifier; authorization server tính lại challenge và so sánh.

Với phương thức S256:

~~~text
code_verifier  = BASE64URL(random_bytes)
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
~~~

Các lỗi thường gặp:

- Cho client bỏ PKCE trong trường hợp đáng lẽ phải yêu cầu.
- Chấp nhận phương thức yếu/không phù hợp hoặc tự fallback khi verifier sai.
- Không ràng buộc challenge vào authorization code.
- Dùng verifier cố định, ngắn hoặc tái sử dụng giữa giao dịch.
- Lưu verifier ở nơi dễ bị đọc hoặc gửi nó qua redirect.
- Kiểm tra PKCE ở client nhưng server không xác minh tại token endpoint.

Authorization server phải lưu challenge theo code và xác minh verifier ở token endpoint. Nếu client đã bắt đầu với PKCE, không được cho phép bỏ qua kiểm tra chỉ vì request đổi code thiếu verifier. Public client cần PKCE; confidential client cũng nên dùng PKCE để bổ sung bảo vệ code.

## 9. Authorization server mix-up và issuer confusion

Một client có thể làm việc với nhiều authorization server/issuer. Nếu response của issuer A bị nhầm là response của issuer B, client có thể gửi code tới token endpoint sai hoặc tin token sai trust domain.

Kịch bản mix-up:

1. Client khởi tạo giao dịch tới một trong nhiều issuer.
2. Attacker tác động để callback từ issuer khác xuất hiện trong cùng luồng.
3. Client không xác định rõ issuer của response.
4. Client gửi code tới token endpoint hoặc áp dụng trust configuration sai.

Biện pháp:

- Gắn issuer đã chọn với từng giao dịch authorization.
- Sử dụng issuer identification trong authorization response theo profile/khả năng giao thức và xác minh chính xác.
- Với OIDC, kiểm tra claim iss trong ID token bằng issuer mong đợi; không lấy issuer từ dữ liệu không tin cậy trong token để tự tìm khóa.
- Ràng buộc authorization endpoint, token endpoint, JWKS URI và metadata với nguồn tin cậy.
- Dùng client ID và redirect URI riêng theo issuer khi kiến trúc yêu cầu.
- Không dùng một callback mơ hồ cho nhiều issuer nếu không có cơ chế phân biệt giao dịch an toàn.

## 10. Token leakage và token exfiltration

Access token và refresh token thường là bearer credential. Nếu attacker lấy được token, họ có thể sử dụng token theo scope/audience/thời hạn mà resource server chấp nhận.

Nguồn rò rỉ phổ biến:

- URL, query string, fragment hoặc browser history.
- Access log, reverse proxy, APM, tracing, exception và analytics.
- Local storage hoặc file cấu hình client bị đọc qua XSS/malware.
- Repository, CI/CD logs, build artifact hoặc backup.
- Referrer header khi trang chứa token trong URL điều hướng tới domain khác.
- Debug output, screenshot hoặc ticket hỗ trợ.

Kiểm soát:

- Không truyền access token trong URL; dùng Authorization header qua TLS.
- Redact token, authorization code, refresh token và cookie ở log/APM.
- Bảo vệ token trong client; với web app cân nhắc Backend for Frontend (BFF) giữ token ở server và dùng cookie session an toàn.
- Hạn chế scope/audience, thời hạn và khả năng refresh.
- Không chia sẻ token giữa môi trường dev/staging/production.
- Dùng CSP, output encoding và kiểm soát script để giảm nguy cơ XSS.
- Có khả năng revoke token, refresh-token family hoặc session liên quan khi bị lộ.

**TLS bảo vệ token trên đường truyền nhưng không ngăn token bị lộ ở endpoint.** Nếu browser, máy client, log hoặc backend đã bị xâm nhập, TLS không thể giữ token bí mật tại điểm đó.

## 11. Access token confusion và audience restriction

Resource server không được chấp nhận token chỉ vì chữ ký hợp lệ hoặc token có cấu trúc JWT. Phải kiểm tra token có được phát hành cho **đúng resource server** và chứa quyền phù hợp.

Các lỗi:

- Một token dành cho API A bị chấp nhận ở API B.
- ID token OIDC bị dùng như access token.
- Token từ issuer khác được tin do cùng dùng thuật toán/chữ ký có vẻ hợp lệ.
- Scope quá rộng hoặc resource server không kiểm tra scope.
- Token của tenant A được dùng để truy cập dữ liệu tenant B.
- JWT có audience không rõ hoặc thiếu nhưng server vẫn chấp nhận.

Biện pháp:

- Xác minh issuer, audience/resource, expiry, not-before và chữ ký theo allowlist thuật toán cấu hình.
- Kiểm tra scope/permission tại resource server và authorization theo resource/action.
- Ràng buộc principal với tenant/resource; không chỉ dựa vào claim client gửi.
- Phân biệt ID token, access token và token nội bộ theo loại/issuer/audience.
- Với JWT, kiểm tra claim/type theo profile token đã thống nhất; không chấp nhận token chỉ vì parse được.
- Với opaque token, dùng introspection hoặc cơ chế xác minh được định nghĩa.

### JWT validation pitfalls

Không tự lấy thuật toán từ header JWT để quyết định chính sách. Verifier cần:

- Allowlist thuật toán phù hợp với issuer và key type.
- Chỉ lấy khóa từ JWKS URI tin cậy đã cấu hình/khám phá an toàn.
- Xử lý kid như selector trong tập khóa đã tin; không dùng nó để truy cập file, URL hoặc query tùy ý.
- Không tin jku/x5u do token chưa xác minh tự khai để tải khóa.
- Kiểm tra issuer, audience, thời hạn và token type theo profile.
- Xử lý rotation JWKS có cache, refresh và giới hạn khi issuer không sẵn sàng.

## 12. Refresh token theft, rotation và reuse detection

Refresh token có thể sống lâu hơn access token và cho phép client lấy token mới. Nếu bị đánh cắp, attacker có thể duy trì quyền truy cập sau khi access token ban đầu hết hạn.

Các biện pháp:

- Cấp refresh token chỉ khi client/flow/policy cho phép.
- Bảo vệ refresh token trong kho an toàn; không đặt trong URL hoặc log.
- Dùng refresh token rotation: mỗi lần refresh thành công, token cũ bị vô hiệu hóa và token mới được cấp.
- Phát hiện reuse token cũ đã bị xoay vòng; xử lý thu hồi token family hoặc grant liên quan theo chính sách.
- Ràng buộc token với client, scope, resource và consent.
- Có absolute lifetime, idle lifetime và cơ chế thu hồi.
- Với public client, áp dụng rotation hoặc sender-constrained refresh token theo yêu cầu bảo mật.

Khi hai request refresh đồng thời dùng cùng một refresh token, hệ thống có thể phát hiện reuse giả do race condition. Client cần serialize thao tác refresh; authorization server cần có chính sách xử lý đồng thời rõ ràng, không vô tình cho token cũ hoạt động vô hạn.

## 13. Client impersonation và client authentication

Client ID thường là định danh công khai, **không phải secret**. Confidential client cần xác thực với token endpoint bằng phương thức phù hợp, ví dụ client secret được bảo vệ, private_key_jwt hoặc mTLS. Public client như SPA hoặc native app không thể giữ client secret tĩnh một cách đáng tin cậy.

Các nguy cơ:

- Client secret bị commit vào repository hoặc đóng gói trong JavaScript/mobile app.
- Attacker giả danh confidential client vì server không kiểm tra client authentication.
- Nhiều ứng dụng dùng chung client secret khiến không thể cô lập sự cố.
- Redirect URI và client registration bị thay đổi trái phép.

Biện pháp:

- Phân loại public/confidential client đúng theo khả năng giữ secret.
- Không nhúng client secret vào SPA hoặc binary phân phối cho người dùng.
- Dùng client authentication mạnh cho confidential client theo khả năng của authorization server.
- Tách client registration theo ứng dụng, môi trường và trust boundary.
- Rotation client secret/certificate và thu hồi client credential bị lộ.
- Bảo vệ quyền quản trị client registration, redirect URI, scope và consent.

Native app nên dùng external user-agent (browser hệ thống) cho authorization, PKCE và redirect URI được đăng ký phù hợp; không nhúng mật khẩu người dùng hoặc dựa vào embedded webview tùy chỉnh để thu credential.

## 14. Phishing consent và scope abuse

Một ứng dụng có thể là client hợp lệ nhưng yêu cầu quyền quá rộng hoặc trình bày consent gây hiểu nhầm. Người dùng có thể cấp quyền đọc email, danh bạ hoặc file cho ứng dụng không cần các quyền đó.

Biện pháp tại authorization server:

- Hiển thị rõ tên client đã xác minh, nhà phát hành và scope cụ thể.
- Phân biệt quyền đọc, ghi, quản trị và quyền offline/refresh.
- Không gom nhiều quyền nhạy cảm vào một mô tả chung khó hiểu.
- Giới hạn scope theo client registration và policy; áp dụng incremental authorization khi phù hợp.
- Hỗ trợ người dùng xem và thu hồi grant/consent đã cấp.
- Cảnh báo hoặc yêu cầu phê duyệt quản trị với scope có rủi ro cao.

Biện pháp tại client:

- Chỉ yêu cầu scope cần thiết cho tính năng hiện tại.
- Không mô tả sai lý do cần quyền.
- Bảo vệ màn hình callback và không tự động mở rộng scope.
- Xử lý access denied/consent denied rõ ràng; không lặp prompt gây áp lực người dùng.

Consent không phải là bằng chứng client an toàn. Người dùng có thể bị lừa chấp thuận một ứng dụng độc hại; vì vậy, quy trình đăng ký client, xác minh publisher và giám sát hành vi cũng quan trọng.

## 15. Device Authorization Grant và phishing

Device Authorization Grant (device flow) dành cho thiết bị có hạn chế nhập liệu, như TV hoặc thiết bị không có trình duyệt đầy đủ. Thiết bị hiển thị mã và địa chỉ xác minh; người dùng dùng thiết bị khác để đăng nhập và chấp thuận.

Rủi ro đặc thù là **device code phishing**: attacker khởi tạo device flow trên thiết bị của họ rồi thuyết phục nạn nhân nhập user code tại trang thật. Nếu nạn nhân xác thực và chấp thuận, attacker có thể nhận token cho thiết bị của mình.

Biện pháp:

- Hiển thị rõ thiết bị/ứng dụng đang yêu cầu quyền trên trang xác minh.
- Yêu cầu người dùng kiểm tra thiết bị và scope trước khi chấp thuận.
- User code ngắn hạn, khó đoán đủ mức, giới hạn số lần thử và rate limit.
- Device code có thời hạn, polling interval và quy tắc từ chối rõ ràng.
- Không chấp thuận chỉ vì người dùng đã đăng nhập; phải có consent cho đúng giao dịch.
- Theo dõi các chiến dịch user-code phishing và hành vi polling bất thường.

Người dùng không nên nhập mã thiết bị nhận từ người lạ hoặc thông báo bất ngờ. Authorization server cần thiết kế trang xác minh để làm rõ ai đang yêu cầu quyền và thiết bị nào sẽ nhận token.

## 16. Các grant/flow cần tránh hoặc giới hạn

| Flow/grant | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| **Implicit grant** | Access token đi qua front channel, dễ lộ qua browser/redirect và thiếu bảo vệ code exchange. | Dùng Authorization Code + PKCE cho ứng dụng hiện đại. |
| **Resource Owner Password Credentials (password grant)** | Client nhận trực tiếp mật khẩu người dùng, phá vỡ phân tách credential và không phù hợp MFA/passkey/federation hiện đại. | Không dùng cho hệ thống mới; chuyển sang redirect-based authorization. |
| **Authorization Code không PKCE** | Code bị chặn có thể bị đổi nếu thiếu ràng buộc client. | Bắt buộc PKCE cho public clients và dùng rộng rãi. |
| **Client secret trong SPA/native app** | Secret có thể trích xuất từ code/binary. | Xem là public client; dùng PKCE và cơ chế phù hợp. |
| **Wildcard redirect URI** | Có thể gửi code/token tới callback attacker. | Exact redirect URI matching. |
| **Token trong URL** | Lộ qua history, log, Referer và telemetry. | Truyền token qua header/kênh bảo vệ. |

Không nên thêm flow cũ chỉ vì một SDK hoặc ví dụ cũ còn hỗ trợ. Đánh giá theo hướng dẫn bảo mật OAuth hiện hành và khả năng của authorization server/client.

## 17. Bảo vệ token bằng sender-constrained mechanisms

Bearer token cho phép bên nào nắm giữ token sử dụng nó. **Sender-constrained token** bổ sung bằng chứng rằng request được gửi bởi bên sở hữu một khóa hoặc chứng chỉ liên quan.

### DPoP

Demonstrating Proof of Possession (DPoP) cho phép client tạo proof JWT có chữ ký bằng khóa riêng cho request. Resource server/token endpoint kiểm tra proof theo đặc tả, bao gồm khóa công khai, HTTP method, URI, thời gian, định danh proof và ràng buộc token phù hợp.

DPoP có thể giảm nguy cơ token bị sao chép đơn thuần rồi sử dụng từ nơi khác. Tuy nhiên, nếu attacker lấy được cả private key hoặc điều khiển runtime của client, lợi ích giảm đáng kể. DPoP không thay thế TLS, audience, scope, expiry hay authorization.

### mTLS-bound access token

Access token có thể được ràng buộc với client certificate. Resource server xác minh certificate trên kết nối TLS và kiểm tra token được cấp cho certificate tương ứng. Cơ chế này phù hợp với một số hệ thống service-to-service và workload.

Private key/certificate phải được bảo vệ, rotation và thu hồi. Nếu TLS kết thúc ở proxy, phải có ranh giới tin cậy rõ giữa proxy và backend; không tin header certificate do client tự gửi.

## 18. PAR, JAR và giảm bề mặt authorization request

Authorization request có thể chứa nhiều tham số nhạy cảm: client, redirect URI, scope, state, nonce, PKCE challenge và yêu cầu assurance. Nếu các tham số này nằm trong URL dài qua browser, chúng có thể xuất hiện trong log hoặc bị sửa đổi nếu không ràng buộc đúng.

- **Pushed Authorization Requests (PAR):** client gửi authorization parameters trực tiếp tới authorization server qua back-channel đã xác thực, nhận request URI ngắn hạn rồi đưa URI đó vào front-channel.
- **JWT-Secured Authorization Request (JAR):** đóng gói request parameters trong JWT có chữ ký (và có thể mã hóa theo profile) để bảo vệ tính toàn vẹn/nguồn gốc.
- **Rich Authorization Requests (RAR):** biểu diễn chi tiết quyền truy cập theo ngữ cảnh nghiệp vụ thay vì chỉ dùng scope tổng quát.

Các cơ chế này có thể tăng khả năng ràng buộc request và giảm lộ tham số, nhưng không tự giải quyết mọi threat. Vẫn cần xác minh client, redirect URI, state/PKCE, token và consent; request URI/JAR cũng cần thời hạn, chống replay và quản lý khóa phù hợp.

## 19. Rate limit, abuse detection và vận hành

Authorization server và resource server là mục tiêu của dò quét, brute force, consent abuse, token replay và từ chối dịch vụ.

Các biện pháp:

- Rate limit authorization request, token endpoint, device polling, introspection và revocation endpoint theo client, account, nguồn và hành vi.
- Giới hạn số lần nhập credential, user code, consent hoặc MFA; tránh cơ chế khóa tài khoản dễ bị attacker lạm dụng để DoS.
- Theo dõi nhiều client ID/redirect URI bất thường, tăng đột biến authorization code failure hoặc token exchange failure.
- Phát hiện token được dùng từ nhiều nguồn/ngữ cảnh không hợp lý, nhưng xem IP/UA là tín hiệu rủi ro chứ không phải bằng chứng tuyệt đối.
- Có endpoint revoke grant/token và quy trình thu hồi client credential.
- Giám sát key rotation, JWKS refresh, client secret/certificate expiry và cấu hình redirect URI.
- Không ghi credential, code, access token, refresh token hoặc cookie thô vào log.

### Các sự kiện audit nên có

| Sự kiện | Metadata hữu ích |
| --- | --- |
| Authorization request | Client ID, issuer, redirect URI ID, scope, state outcome, request ID. |
| Consent | User/principal nội bộ, client, scope đã chấp thuận/từ chối, thời điểm. |
| Code exchange | Client ID, key ID nếu có, outcome, PKCE validation result; không ghi code/verifier. |
| Token issuance | Token ID/reference nếu có, subject/client, audience, scope, expiry; không ghi token. |
| Refresh reuse | Client, token family reference, thời gian, nguồn đã giảm thiểu. |
| Revocation | Actor, client/grant/token reference, lý do và thời điểm commit. |
| Validation failure | Mã lỗi, issuer/client, request ID và metadata tối thiểu. |

## 20. Mã giả: xác minh callback và token theo nguyên tắc an toàn

Đoạn mã sau mô tả logic client OIDC/OAuth ở mức khái niệm; không thay thế thư viện giao thức đã được kiểm thử:

~~~text
handleAuthorizationCallback(callback, browserSession):
    tx = loadPendingAuthorizationTransaction(browserSession)
    require tx exists and not expired
    require callback.state exists
    require constantTimeEqual(callback.state, tx.state)
    require callback.issuer matches tx.expectedIssuer

    if callback contains authorizationError:
        consumeTransactionAtomically(tx)
        return handleDeniedOrFailedAuthorization()

    require callback.code exists
    require consumeTransactionAtomically(tx)

    tokenResponse = tokenEndpoint.exchange(
        code = callback.code,
        redirectUri = tx.exactRedirectUri,
        codeVerifier = tx.codeVerifier,
        clientAuthentication = configuredClientAuthentication()
    )

    accessToken = tokenResponse.accessToken
    if thisIsOidcLogin:
        verifyIdToken(
            signature = trustedIssuerKeysOnly,
            issuer = tx.expectedIssuer,
            audience = tx.clientId,
            expiry = trustedClock,
            nonce = tx.nonce
        )

    storeTokensSecurelyAccordingToClientArchitecture()
    createLocalSessionOnlyAfterRequiredValidation()
    return success()
~~~

Ở resource server, quy trình khác:

~~~text
authorizeApiRequest(request):
    token = extractBearerTokenFromAuthorizationHeader(request)
    if token is missing:
        return unauthorized()

    claims = verifyTokenUsingConfiguredIssuerAndKeys(token)
    require claims.issuer == expectedIssuer
    require expectedResourceIn(claims.audience)
    require claims.notExpired and claims.notBeforeSatisfied
    require allowedTokenTypeAndAlgorithm(claims.header, claims)
    require requiredScopesPresent(claims, request.action)
    require tenantAndResourcePolicyAllows(claims.subject, request.resource)
    return executeAuthorizedRequest()
~~~

Không dùng đoạn mã giả để tự viết parser JWT, chữ ký, PKCE hoặc OIDC. Hãy dùng thư viện chuẩn, cấu hình issuer/client/redirect URI tường minh, và kiểm thử negative cases. Việc lưu token phải phù hợp với loại client; không mặc định localStorage là nơi an toàn cho bearer token.

## 21. Tình huống thực tế: authorization code bị chuyển hướng ra ngoài

Một ứng dụng báo cáo yêu cầu scope **reports:read**. Authorization server cho phép redirect URI dạng tiền tố trên host ứng dụng. Trên cùng domain có một endpoint redirect mở cho người dùng, nhận tham số next. Attacker tạo một authorization request trỏ callback qua endpoint này rồi đặt next tới máy chủ của họ.

### Chuỗi sự kiện

| Bước | Sự kiện | Điểm kiểm soát |
| --- | --- | --- |
| 1 | Attacker tạo authorization request với redirect URI gần hợp lệ. | Exact redirect URI matching. |
| 2 | Người dùng đăng nhập và chấp thuận scope. | Consent hiển thị rõ client và quyền. |
| 3 | Authorization server chuyển code tới callback hợp lệ có open redirect. | Loại bỏ open redirect; không dùng callback chuyển tiếp tùy ý. |
| 4 | Endpoint chuyển code tới attacker. | PKCE S256 ràng buộc code với verifier của client. |
| 5 | Attacker thử đổi code lấy token. | Code one-time, client/redirect binding, PKCE và client authentication. |

### Cách khắc phục

- Đăng ký callback chính xác, không dùng wildcard hoặc prefix match.
- Xóa open redirect hoặc giới hạn đích bằng allowlist nội bộ.
- Bắt buộc PKCE S256 và ràng buộc code với đúng client.
- Không để code/token xuất hiện trong log, Referer hoặc telemetry.
- Giám sát callback bất thường và code exchange thất bại.

**Một lớp kiểm soát không thay thế lớp khác.** Exact redirect URI giảm khả năng gửi code sai nơi; PKCE giảm hậu quả khi code bị chặn; state ràng buộc callback với giao dịch; code one-time hạn chế replay.

## 22. Checklist thiết kế OAuth an toàn

- [ ] Phân biệt OAuth authorization với OIDC authentication; không dùng access token như ID token.
- [ ] Dùng Authorization Code Flow với PKCE S256 cho public clients; áp dụng PKCE rộng rãi.
- [ ] So khớp redirect URI chính xác; không dùng wildcard hoặc open redirect.
- [ ] State ngẫu nhiên, gắn với giao dịch, kiểm tra và tiêu thụ một lần.
- [ ] OIDC nonce được kiểm tra trong ID token; không nhầm với state hoặc PKCE.
- [ ] Authorization code ngắn hạn, one-time, ràng buộc client, redirect URI và PKCE.
- [ ] Không dùng implicit grant hoặc password grant cho ứng dụng mới.
- [ ] Public client không chứa client secret; confidential client dùng client authentication phù hợp.
- [ ] Ràng buộc issuer/authorization server với giao dịch để chống mix-up.
- [ ] Resource server xác minh issuer, audience, signature, expiry, token type và scope.
- [ ] Không nhận token từ URL; redaction code/token/cookie ở log và telemetry.
- [ ] Refresh token có rotation/reuse detection hoặc sender constraint theo policy.
- [ ] Có revoke grant/token/client credential và kiểm soát vòng đời consent.
- [ ] Hiển thị client, publisher và scope rõ ràng để giảm consent phishing.
- [ ] Device flow có user code TTL, rate limit và xác nhận thiết bị/quyền rõ ràng.
- [ ] DPoP/mTLS-bound token được cân nhắc cho API có rủi ro cao.
- [ ] PAR/JAR/RAR được dùng khi cần ràng buộc authorization request tốt hơn.
- [ ] Có rate limit, audit, incident response và kiểm thử negative cases.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao OAuth 2.0 không tự chứng minh danh tính người dùng?

**Gợi ý:** OAuth cấp quyền truy cập tài nguyên cho client. Khi cần đăng nhập người dùng, dùng OIDC và xác minh ID token theo issuer, audience, signature, expiry, nonce.

**Câu 2.** State, PKCE và nonce giải quyết những vấn đề khác nhau nào?

**Gợi ý:** State ràng buộc response với giao dịch client và chống CSRF; PKCE ràng buộc code với bên giữ verifier; nonce ràng buộc ID token OIDC với yêu cầu xác thực.

**Câu 3.** Vì sao kiểm tra redirect URI bằng tiền tố là nguy hiểm?

**Gợi ý:** URL có thể đi qua open redirect hoặc host/đường dẫn attacker kiểm soát; cần so khớp chính xác với URI đã đăng ký.

**Câu 4.** Nếu chữ ký JWT hợp lệ, resource server có thể bỏ qua audience không?

**Gợi ý:** Không. Chữ ký chỉ xác minh token được ký bởi khóa tương ứng; audience xác định token dành cho resource nào.

**Câu 5.** Vì sao refresh token rotation cần reuse detection?

**Gợi ý:** Token cũ đã bị xoay vòng mà xuất hiện lại có thể cho thấy token bị sao chép; server có thể thu hồi token family/grant liên quan.

**Câu 6.** Device code phishing khai thác điểm yếu nào?

**Gợi ý:** Nạn nhân nhập user code do attacker cung cấp và chấp thuận quyền cho thiết bị của attacker; trang xác minh phải hiển thị rõ client/thiết bị/scope.

**Câu 7.** Sender-constrained token giảm rủi ro nào và không giải quyết được gì?

**Gợi ý:** Giảm việc chỉ sao chép bearer token rồi dùng từ client khác; không bảo vệ nếu private key hoặc runtime của client bị chiếm.

## 24. Ghi nhớ

**OAuth threat tập trung vào việc bảo vệ ranh giới giữa client, authorization server, resource server và người dùng trong quá trình cấp quyền.** Các rủi ro quan trọng gồm redirect manipulation, CSRF/login CSRF, code interception/replay, PKCE downgrade, issuer mix-up, token leakage, audience confusion, refresh token theft, client impersonation và consent/device-code phishing. Thiết kế an toàn cần Authorization Code + PKCE, redirect URI chính xác, state/nonce đúng mục đích, token validation đầy đủ, scope tối thiểu, bảo vệ và thu hồi token, client authentication phù hợp cùng giám sát vận hành. OAuth cấp quyền; OIDC mới bổ sung lớp xác thực danh tính người dùng. Mỗi token phải được xác minh cho đúng issuer, audience, client và resource trước khi sử dụng.
