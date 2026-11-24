# Browser session

**Browser session** là trạng thái truy cập mà một ứng dụng web duy trì giữa nhiều request của cùng một trình duyệt sau khi người dùng hoặc client đã được xác thực. Thay vì yêu cầu gửi lại password hay passkey ở mọi request, ứng dụng cấp một session credential, thường là cookie chứa session identifier ngẫu nhiên. Browser tự gửi cookie theo quy tắc cookie; server dùng nó để tìm trạng thái session và quyết định request có thể tiếp tục được xử lý hay không.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, federation và account recovery. Browser session là điểm nối giữa một lần authentication và nhiều request web tiếp theo. Thiết kế session không chỉ là tạo cookie: cần quản lý vòng đời, ranh giới origin/site, chống session fixation, theft và CSRF, xử lý nhiều tab, logout, thu hồi và bảo vệ dữ liệu trên thiết bị dùng chung.

Điểm cốt lõi: **cookie session là credential dạng bearer**. Bên nào sở hữu một session cookie còn hiệu lực có thể được server xem như đang đại diện cho principal gắn với session đó. Vì vậy phải tạo identifier đủ ngẫu nhiên, truyền qua HTTPS, đặt cookie an toàn, bảo vệ trạng thái server-side, xoay session khi thay đổi mức tin cậy và thu hồi nó khi logout hoặc account mất quyền.

## 1. Browser session là gì?

HTTP về cơ bản là stateless: mỗi request độc lập và server không mặc định biết request mới đến từ cùng người dùng đã gửi request trước. Ứng dụng web cần một cơ chế duy trì trạng thái giữa các request. Browser session là một cách phổ biến để làm điều đó.

Sau khi authentication thành công, server có thể tạo một session record và gửi cho browser một cookie chứa identifier ngẫu nhiên. Với request tiếp theo, browser tự gửi cookie tới host phù hợp. Server kiểm tra identifier, tra session record, kiểm tra trạng thái và gắn principal đã xác minh vào request context.

Luồng khái quát:

    Browser
       |
       | POST /login + credential + CSRF protection
       v
    Authentication service
       |
       | Verify credential and policy
       v
    Session service / application
       |
       | Create new session record
       | Set-Cookie: opaque session identifier
       v
    Browser
       |
       | GET /account + session cookie
       v
    Application server
       |
       | Resolve session and check active state
       v
    Protected resource

Cookie không phải password hay passkey. Nó là credential đại diện cho session đã được thiết lập. Nếu cookie bị đánh cắp, attacker có thể sử dụng session mà không cần biết credential ban đầu cho tới khi session bị thu hồi hoặc hết hiệu lực.

### 1.1. Browser session và authentication session

Các thuật ngữ có thể được dùng khác nhau giữa sản phẩm:
- **Authentication event:** một lần người dùng chứng minh quyền kiểm soát credential.
- **Authentication session:** ngữ cảnh ghi nhận lần xác thực, thời điểm và mức assurance.
- **Application/browser session:** trạng thái truy cập mà một ứng dụng duy trì cho browser.
- **Identity Provider session:** trạng thái SSO mà IdP duy trì cho browser.
- **HTTP connection:** kết nối mạng cụ thể; không đồng nghĩa với login session.

Một browser có thể đồng thời giữ session của nhiều ứng dụng và một session SSO tại IdP. Logout khỏi một ứng dụng không nhất thiết kết thúc session ở các ứng dụng khác hoặc IdP.

### 1.2. Session cookie là bearer credential

Nếu session identifier được dùng như một bearer secret, server không thể biết người gửi cookie là người đã đăng nhập ban đầu chỉ từ việc cookie đúng. Cookie cần được bảo vệ như credential:
- Không đưa vào URL hoặc nội dung trang.
- Chỉ truyền qua HTTPS.
- Không ghi vào application log, analytics hoặc error report.
- Hạn chế quyền đọc từ JavaScript.
- Thu hồi khi có dấu hiệu lộ hoặc khi session không còn được phép.
- Không tái sử dụng identifier sau khi session kết thúc.

## 2. Stateful và stateless session

Có hai cách tổ chức phổ biến. Chúng có thể được kết hợp trong một hệ thống.

### 2.1. Stateful session

Browser giữ một opaque session ID; server giữ record tương ứng trong database, Redis hoặc session service.

Record có thể chứa:
- Session ID hoặc giá trị hash/reference của nó.
- Subject/account ID và tenant.
- Client/application ID.
- Created-at, last-seen và expiry.
- Authentication time, method và assurance context.
- Trạng thái active, revoked hoặc expired.
- Session version hoặc authorization epoch.
- Metadata thiết bị ở mức cần thiết.

Ưu điểm:
- Thu hồi một session cụ thể tương đối trực tiếp.
- Server có thể cập nhật trạng thái và quyền.
- Browser không cần giữ profile hoặc quyền chi tiết.
- Dễ quản lý danh sách phiên và sign out all sessions.

Chi phí:
- Cần session store có availability và capacity phù hợp.
- Request có thể cần lookup hoặc cache.
- Phải xử lý replication, invalidation và consistency giữa các node.

### 2.2. Stateless token-backed session

Một số ứng dụng giữ token có chữ ký trong cookie. Server xác minh token mà không cần tra session record ở mỗi request.

Ưu điểm:
- Có thể giảm lookup tới session store.
- Phù hợp một số kiến trúc phân tán.
- Token có thể mang các claim cần thiết cho xử lý request.

Hạn chế:
- Thu hồi ngay một token đã phát hành khó hơn nếu không có denylist, version check, introspection hoặc state lookup.
- Claim có thể cũ sau khi role, account hoặc tenant thay đổi.
- Cookie vẫn là bearer credential; chữ ký không ngăn việc sử dụng token bị đánh cắp.
- Cookie payload có thể đọc được nếu chỉ ký mà không mã hóa; không đưa dữ liệu nhạy cảm vào token.
- Phải phân biệt token dành cho browser session với access token dành cho API.

Không nên gọi một JWT trong cookie là an toàn chỉ vì nó có chữ ký. Cần kiểm tra issuer, audience, expiry, type, algorithm, cookie protections và chính sách revoke.

### 2.3. Chọn mô hình theo yêu cầu

| Yêu cầu | Stateful session | Stateless token-backed |
| --- | --- | --- |
| Thu hồi ngay một phiên | Thuận lợi nếu mọi node thấy trạng thái mới. | Cần thêm state/revocation mechanism. |
| Nhiều node/region | Cần store/cache phân tán. | Dễ xác minh offline hơn, nhưng khó cập nhật trạng thái. |
| Thay đổi quyền thường xuyên | Có thể cập nhật session hoặc version. | Cần token mới hoặc state check. |
| Dung lượng cookie | Chỉ cần identifier nhỏ. | Token có thể lớn do claims. |
| Audit và quản lý phiên | Có record tập trung. | Cần thêm registry nếu muốn quản lý từng phiên. |

Không có lựa chọn tốt nhất cho mọi ứng dụng. Quyết định phải dựa trên yêu cầu revoke, độ trễ, availability, dữ liệu được mang trong token và cách authorization được kiểm tra.

## 3. Session identifier và cách tạo an toàn

Session identifier cần khó đoán và không chứa thông tin có ý nghĩa như email, account ID, username hoặc timestamp.

### 3.1. Entropy và random generation

Dùng cryptographically secure random number generator (CSPRNG) của nền tảng. Identifier cần đủ entropy để việc đoán trúng trở nên không thực tế. Tránh:
- Sequential ID hoặc số tăng dần.
- UUID tự tạo bằng random generator yếu.
- Hash của email, account ID hoặc thời gian.
- Giá trị dựa trên IP/user-agent.
- Identifier có cấu trúc tiết lộ account hoặc tenant.

Ví dụ minh họa một session ID ngẫu nhiên:

    session_id = CSPRNG.generate(32 bytes)
    cookie_value = base64url_without_padding(session_id)

Đây là pseudocode. Dùng API CSPRNG chính thức của runtime và encoding chuẩn; không tự viết thuật toán random.

### 3.2. Lưu session ID an toàn

Nếu session store bị đọc, việc lưu raw session ID có thể cho phép người có quyền đọc database sử dụng session. Có thể lưu keyed hash hoặc verifier/reference của identifier để giảm rủi ro:
- Browser giữ secret session ID.
- Server tính keyed hash bằng key được bảo vệ.
- Session store tra cứu theo giá trị hash.
- Key hash có quy trình rotation và migration.
- Không dùng hash không khóa của giá trị entropy thấp làm biện pháp bảo vệ.

Không ghi raw cookie vào log hoặc trace. Audit chỉ cần session reference được thiết kế để tương quan, không phải bearer value.

### 3.3. Không dùng fingerprint làm session secret

IP address, user-agent, timezone, screen size hoặc browser fingerprint có thể thay đổi và có thể bị giả mạo. Chúng không thay thế entropy của session ID. Có thể dùng một số tín hiệu làm risk signal, nhưng không coi fingerprint là bằng chứng danh tính tuyệt đối.

## 4. Cookie attributes và phạm vi gửi cookie

Browser quyết định gửi cookie dựa trên domain, path, scheme, SameSite, thời hạn và các quy tắc khác. Cấu hình sai có thể làm cookie bị gửi tới host không cần thiết hoặc không được gửi trong flow hợp lệ.

### 4.1. Secure

Thuộc tính Secure yêu cầu browser chỉ gửi cookie qua kết nối an toàn theo quy tắc của browser. Session cookie nên được đặt Secure và ứng dụng phải dùng HTTPS xuyên suốt. HSTS có thể giúp browser tự nâng cấp kết nối cho domain đã áp dụng policy.

Secure không bảo vệ cookie khỏi XSS hoặc malware trên thiết bị. Nó bảo vệ việc gửi cookie qua kênh không an toàn.

### 4.2. HttpOnly

HttpOnly ngăn JavaScript thông thường đọc cookie qua document.cookie. Điều này làm giảm khả năng XSS lấy trực tiếp session cookie.

Tuy nhiên, XSS vẫn có thể chạy request cùng origin bằng quyền của trang và lợi dụng session mà browser tự gửi cookie. HttpOnly không thay thế chống XSS, CSP, output encoding và kiểm soát script.

### 4.3. SameSite

SameSite kiểm soát trong những ngữ cảnh cross-site nào browser gửi cookie:
- **Strict:** hạn chế gửi cookie trong các request điều hướng đến từ site khác; bảo vệ CSRF tốt hơn nhưng có thể làm gián đoạn một số liên kết hoặc luồng SSO.
- **Lax:** thường cho phép cookie trong một số top-level safe navigation từ site khác, đồng thời hạn chế nhiều cross-site subrequest.
- **None:** cho phép gửi cookie cross-site theo policy browser và yêu cầu Secure.

SameSite hữu ích nhưng không phải CSRF defense đầy đủ. Cần hiểu khác biệt giữa site và origin, các redirect trong login flow và hành vi browser thực tế. Với OIDC/SAML callback, lựa chọn SameSite phải được kiểm thử theo response mode và kiến trúc; không chọn None rộng rãi chỉ để làm flow chạy.

### 4.4. Domain và host-only cookie

Nếu bỏ thuộc tính Domain, cookie thường là host-only và chỉ được gửi tới host đã đặt cookie. Nếu đặt Domain rộng, cookie có thể được gửi tới các subdomain phù hợp.

Ưu tiên host-only cookie cho session nhạy cảm. Không chia sẻ session cookie với mọi subdomain nếu không có nhu cầu và thiết kế trust rõ. Một subdomain yếu hoặc bị takeover có thể làm tăng rủi ro khi cookie được đặt ở domain cha.

### 4.5. Path

Path giới hạn những path mà browser gửi cookie tới theo quy tắc cookie. Path không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host; ứng dụng cùng origin vẫn có thể có các rủi ro chia sẻ. Không dựa vào Path để cô lập các ứng dụng không tin cậy.

### 4.6. Max-Age và Expires

Max-Age hoặc Expires xác định thời hạn cookie ở browser. Cookie không có thời hạn rõ thường được gọi là session cookie, nhưng browser có thể khôi phục session qua restart hoặc session restore. Vì vậy, không dựa vào việc đóng cửa sổ browser để kết thúc server session.

Server phải thực thi idle và absolute expiration độc lập với cookie expiry. Khi logout, gửi cookie hết hạn với đúng tên và phạm vi đã đặt.

### 4.7. Cookie prefixes

Prefix giúp browser áp dụng một số ràng buộc:
- Cookie có prefix __Host- cần Secure, Path=/ và không có Domain.
- Cookie có prefix __Secure- cần được đặt với Secure.

Ví dụ cấu hình session cookie host-only:

    Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax

Cấu hình cụ thể phụ thuộc flow và browser support. Không đặt session cookie ở Domain rộng nếu không cần.

## 5. Vòng đời browser session

Session cần có trạng thái và chuyển tiếp rõ ràng. Tạo session không phải hành động duy nhất; hệ thống phải xử lý authentication, renewal, idle timeout, absolute timeout, logout, revoke và account lifecycle.

### 5.1. Tạo session sau authentication

Sau khi xác thực thành công:
1. Kiểm tra authentication result và policy.
2. Tạo session identifier mới bằng CSPRNG.
3. Lưu session record với subject, tenant, client và metadata cần thiết.
4. Gắn authentication time, method và assurance context.
5. Gửi cookie với attributes an toàn.
6. Ghi audit event không chứa secret.

Không lấy session ID do client tự gửi trước đăng nhập rồi dùng lại làm session đã xác thực.

### 5.2. Session fixation và session rotation

Session fixation xảy ra khi attacker khiến nạn nhân dùng một session identifier mà attacker đã biết hoặc có thể kiểm soát. Sau khi nạn nhân đăng nhập, attacker dùng lại identifier đó để truy cập.

Phòng chống:
- Tạo session ID mới sau login thành công.
- Rotate session khi nâng quyền hoặc thay đổi trust level.
- Không chấp nhận session ID do URL parameter cung cấp.
- Không cho client tự chọn identifier.
- Vô hiệu hóa identifier cũ sau rotation.
- Kiểm thử session ID trước và sau authentication khác nhau.

Session rotation cũng phù hợp sau re-authentication nhạy cảm, thay đổi password, thêm authenticator hoặc privilege elevation theo policy. Không giữ session ID cũ chỉ để tránh người dùng phải tải lại trang.

### 5.3. Idle timeout

Idle timeout giới hạn thời gian không có hoạt động phù hợp trước khi session bị kết thúc. Cần định nghĩa activity nào được tính:
- Request có authentication hợp lệ.
- Hoạt động của người dùng đã được xác minh.
- Background polling hoặc heartbeat.
- Request tự động do browser/service worker tạo.

Nếu mọi background request đều reset idle timer, session có thể tồn tại vô hạn dù người dùng không còn hiện diện. Chọn activity semantics rõ và tránh để một tab chạy nền giữ session mãi.

### 5.4. Absolute timeout

Absolute timeout giới hạn tổng thời gian session kể từ lúc tạo hoặc lần authentication gốc, kể cả khi có hoạt động liên tục. Nó buộc hệ thống yêu cầu authentication mới sau một khoảng tối đa.

Có thể kết hợp:
- Idle timeout ngắn hơn.
- Absolute timeout dài hơn nhưng hữu hạn.
- Authentication freshness riêng cho action nhạy cảm.
- Step-up khi context/risk thay đổi.

Sliding expiration không nên làm session kéo dài vô hạn nếu policy yêu cầu absolute lifetime.

### 5.5. Session renewal

Có thể cấp cookie/session mới khi gần hết hạn hoặc sau re-authentication. Renewal cần chống race và bảo đảm session cũ không tạo nhánh ngoài ý muốn. Nếu nhiều tab cùng renew, server nên xử lý idempotent hoặc dùng version để tránh một response cũ ghi đè session state mới.

## 6. Browser session và authentication assurance

Session active không đồng nghĩa mọi request đều có mức assurance giống nhau. Authentication time, method và context có thể cũ; một hành động nhạy cảm cần xác thực mới.

Session record có thể tham chiếu:
- auth_time: thời điểm authentication.
- amr: phương thức đã dùng theo vocabulary của issuer.
- acr: authentication context class theo profile.
- Credential reference hoặc authentication transaction ID.
- User verification hoặc phishing-resistant property khi policy ghi nhận.
- Session creation time và last re-authentication time.

Không tự suy ra mức assurance từ tên chuỗi trong amr/acr. Cần mapping đã thỏa thuận với issuer và policy nội bộ.

Ví dụ:
- Xem trang hồ sơ có thể chỉ cần session active.
- Thay email recovery có thể yêu cầu re-authentication bằng authenticator đã đăng ký trước.
- Tạo API key hoặc cấp role admin có thể yêu cầu phishing-resistant step-up và approval riêng.
- Giao dịch tài chính có thể cần transaction confirmation gắn với nội dung giao dịch.

Một session không nên được coi là bằng chứng mới vô hạn chỉ vì cookie vẫn được browser gửi.

## 7. CSRF và browser session

Cookie được browser tự động gửi theo quy tắc cookie. Điều này tạo ra nguy cơ Cross-Site Request Forgery (CSRF): attacker có thể khiến browser đang đăng nhập gửi request tới ứng dụng mà người dùng không chủ ý thực hiện.

### 7.1. Ví dụ CSRF

Người dùng đăng nhập vào portal và giữ session cookie. Attacker đưa người dùng tới trang ngoài chứa form hoặc request nhắm vào endpoint thay đổi email, thêm người dùng hoặc chuyển tiền. Nếu browser gửi cookie và server không xác minh request intent, thao tác có thể được thực hiện dưới session của nạn nhân.

### 7.2. CSRF defenses

Tùy kiến trúc, kết hợp:
- CSRF token gắn với session hoặc request.
- SameSite cookie phù hợp.
- Kiểm tra Origin và/hoặc Referer theo policy.
- Chỉ dùng GET cho thao tác không thay đổi trạng thái.
- Xác minh content type và method theo API contract.
- Step-up/transaction confirmation cho hành động có hậu quả cao.
- Không dựa riêng vào CORS để chống CSRF.

Ví dụ form dùng token do server tạo:

    <form method="post" action="/account/email">
      <input type="hidden" name="csrf_token" value="SERVER_GENERATED_TOKEN">
      <input name="email" type="email">
      <button type="submit">Cập nhật email</button>
    </form>

Token CSRF không phải session credential. Không đưa nó vào URL vì URL có thể xuất hiện trong history, log và Referer.

### 7.3. Origin, site và CORS

Origin gồm scheme, host và port. Site là khái niệm khác, dựa trên scheme và registrable domain theo quy tắc browser. Hai subdomain có thể same-site nhưng khác-origin.

CORS kiểm soát việc JavaScript từ origin khác đọc response theo policy; nó không tự ngăn browser gửi mọi request cross-site. Vì vậy, CORS không thay thế CSRF token hoặc các kiểm soát request intent.

### 7.4. Login CSRF

CSRF có thể xảy ra ngay ở login flow. Attacker có thể khiến browser của nạn nhân đăng nhập vào account do attacker kiểm soát; sau đó nạn nhân tải lên dữ liệu hoặc liên kết thông tin vào account sai. Dùng state/correlation và CSRF protection phù hợp cho login transaction; không chỉ bảo vệ các endpoint sau login.

## 8. XSS và session hijacking

Cross-Site Scripting (XSS) cho phép attacker chạy script trong origin của ứng dụng. Nếu ứng dụng dùng cookie HttpOnly, script thường không đọc trực tiếp được cookie, nhưng vẫn có thể gửi request với cookie tự động đính kèm.

### 8.1. HttpOnly không chặn mọi tác động XSS

XSS có thể:
- Đọc dữ liệu trang mà user được phép xem.
- Thực hiện action dưới session hiện tại.
- Thay nội dung để lừa người dùng nhập credential.
- Gửi dữ liệu ra ngoài nếu CSP/network policy cho phép.
- Thay đổi email, authenticator hoặc quyền nếu authorization/step-up yếu.

Phòng thủ XSS cần output encoding theo context, safe templating, input handling, Content Security Policy, Trusted Types khi phù hợp, dependency hygiene và kiểm thử. Không dựa vào HttpOnly như giải pháp duy nhất.

### 8.2. Session hijacking

Session hijacking là sử dụng session credential của người khác. Nguồn lộ có thể là:
- XSS hoặc malicious browser extension.
- Malware trên endpoint.
- Log, crash report hoặc analytics ghi cookie.
- HTTP không an toàn hoặc TLS termination sai.
- Backup/debug tooling truy cập session store.
- Phishing proxy đánh cắp session sau authentication.
- Thiết bị dùng chung không được logout.

Biện pháp gồm bảo vệ endpoint, TLS/HSTS, cookie flags, redaction, session rotation, short lifetime hợp lý, risk monitoring, re-authentication và revoke nhanh.

### 8.3. Binding với IP hoặc user-agent

IP và user-agent có thể hỗ trợ phát hiện thay đổi bất thường nhưng không phải binding tuyệt đối. Người dùng có thể chuyển từ Wi-Fi sang mobile, đi qua NAT, VPN hoặc proxy; user-agent cũng có thể bị giả mạo. Khóa session ngay khi IP đổi có thể gây false positive và denial of service.

Dùng tín hiệu này như một phần risk assessment. Với token cần chống replay mạnh hơn, cân nhắc sender-constrained mechanism phù hợp thay vì tự tạo fingerprint binding dễ phá vỡ.

## 9. BFF, SPA và nơi lưu token trong browser

Cách ứng dụng lưu token ảnh hưởng trực tiếp tới rủi ro session.

### 9.1. Backend for Frontend (BFF)

Với BFF:
- Browser giữ session cookie opaque của BFF.
- BFF giữ access/refresh token phía server.
- Browser gọi BFF qua cookie session.
- BFF gọi API downstream bằng token có audience/scope phù hợp.
- BFF thực hiện CSRF protection và authorization ở boundary của browser.

Mô hình này giảm việc JavaScript trực tiếp quản lý bearer token. Tuy nhiên, BFF vẫn phải bảo vệ cookie, chống CSRF/XSS, quản lý session và kiểm soát downstream token.

### 9.2. SPA giữ token phía client

Một SPA có thể dùng Authorization Code Flow với PKCE và giữ access token trong memory. Cách lưu token cần được đánh giá:
- localStorage tồn tại lâu và JavaScript cùng origin có thể đọc.
- sessionStorage thường gắn với tab/session storage context nhưng vẫn đọc được bởi JavaScript cùng origin.
- Memory giảm persistence nhưng token vẫn có thể bị lấy hoặc sử dụng khi XSS đang chạy.
- Cookie HttpOnly giảm khả năng đọc trực tiếp từ JavaScript nhưng browser tự gửi cookie nên cần CSRF protection.

Không có nơi lưu nào loại bỏ hoàn toàn rủi ro XSS. Tránh lưu refresh token dài hạn trong localStorage nếu kiến trúc có lựa chọn an toàn hơn. Dùng token lifetime và sender constraint phù hợp, đồng thời bảo vệ origin.

### 9.3. Không nhầm browser session với API token

Cookie session dành cho ứng dụng web và access token dành cho resource server có thể có audience, lifetime và cách thu hồi khác nhau. Không gửi cookie session sang API không cùng trust boundary, không dùng ID Token thay access token và không đưa refresh token vào URL.

## 10. Browser session trong SSO và federation

Trong SSO, browser có thể giữ cookie của IdP và cookie riêng của từng relying party (RP). Khi user truy cập RP, browser được chuyển tới IdP; nếu IdP session còn active, IdP có thể xác thực mà không yêu cầu nhập credential lại.

### 10.1. Hai lớp session

- **IdP session:** chứng minh browser còn phiên đăng nhập tại Identity Provider.
- **RP/application session:** trạng thái ứng dụng riêng được tạo sau khi RP xác minh assertion/token.

Hai session có thể có lifetime, cookie scope, logout và assurance khác nhau. RP không nên coi cookie IdP là cookie của chính mình; browser chỉ gửi mỗi cookie tới domain/path phù hợp.

### 10.2. Re-authentication và max_age

RP có thể yêu cầu authentication mới theo OIDC parameters/policy như prompt hoặc max_age khi cần. RP cần kiểm tra auth_time và context theo profile. Một IdP session còn active không có nghĩa user vừa xác thực lại cho hành động nhạy cảm.

### 10.3. Third-party cookie restrictions

Một số flow front-channel hoặc iframe-based SSO phụ thuộc third-party cookies và có thể bị browser hạn chế. Thiết kế hiện đại nên tránh phụ thuộc vào cookie cross-site không cần thiết, kiểm thử trên browser mục tiêu và dùng redirect/top-level flow hoặc back-channel mechanism phù hợp.

SameSite=None yêu cầu Secure và có thể vẫn bị browser privacy policy chặn trong một số ngữ cảnh. Không giả định mọi browser xử lý third-party cookies giống nhau.

### 10.4. Logout phạm vi nào?

Logout khỏi RP thường thu hồi session của ứng dụng và xóa cookie RP. IdP session có thể còn. Global logout cần cơ chế federation như RP-Initiated Logout, front-channel hoặc back-channel logout theo hỗ trợ của IdP/RP. Không tuyên bố đã logout mọi ứng dụng khi chỉ xóa cookie local.

## 11. Nhiều tab, nhiều cửa sổ và browser profile

Một user có thể mở nhiều tab của cùng ứng dụng. Các tab thường chia sẻ cookie cùng host/path, nhưng state JavaScript và một số storage có thể khác nhau.

### 11.1. Đồng bộ UI giữa các tab

Có thể dùng BroadcastChannel hoặc storage event để thông báo logout, session renewal hoặc account switch. Chỉ gửi event metadata, không gửi session ID, access token, refresh token hoặc CSRF secret qua channel.

Ví dụ:

    const channel = new BroadcastChannel("auth-events");

    // Tab thực hiện logout
    channel.postMessage({ type: "SESSION_ENDED" });

    // Tab còn lại
    channel.onmessage = (event) => {
      if (event.data?.type === "SESSION_ENDED") {
        clearInMemoryUserState();
        stopBackgroundRefresh();
        showSignedOutPage();
      }
    };

Đây chỉ là đồng bộ UI. Server-side session revoke vẫn là nguồn quyết định; tab bỏ lỡ message cũng phải bị từ chối khi gửi request bằng session đã hết hiệu lực.

### 11.2. Race giữa refresh và logout

Một tab có thể refresh session đúng lúc tab khác logout. Response refresh đến muộn có thể ghi state mới vào client sau khi logout.

Cần:
- Auth-state generation/version ở client.
- Logout tăng generation và dừng background refresh.
- Chỉ chấp nhận refresh response nếu generation vẫn khớp.
- Server serialize refresh và revoke theo session/token family.
- Session đã revoked không được tạo lại từ response hoặc retry cũ.
- Xử lý idempotent cho request lặp.

### 11.3. Browser profile và thiết bị dùng chung

Private/incognito window, browser profile khác hoặc thiết bị khác có thể có cookie jar riêng. Logout ở một profile không xóa cookie trong profile khác. Với thiết bị dùng chung, cần hướng dẫn người dùng logout khỏi ứng dụng, đóng profile theo policy và tránh lưu credential trên thiết bị công cộng.

Không dùng “đóng tab” như bằng chứng session đã kết thúc.

## 12. Logout và thu hồi browser session

Logout an toàn phải làm session credential không còn được server chấp nhận, đồng thời dọn trạng thái client.

Quy trình thông thường:
1. Browser gửi request logout bằng method thay đổi trạng thái và CSRF protection.
2. Server xác định session hiện tại.
3. Server ghi nhận revoke/terminated bền vững.
4. Server ngừng chấp nhận session ID cũ trên mọi node.
5. Thu hồi refresh token/grant thuộc session theo policy nếu có.
6. Gửi Set-Cookie hết hạn với đúng tên và phạm vi.
7. Client xóa state trong memory/storage do ứng dụng quản lý và dừng refresh.
8. Ghi audit không chứa secret.

Xóa cookie mà không revoke server session không đủ. Nếu attacker đã sao chép cookie, họ vẫn có thể sử dụng nó từ một browser khác.

### 12.1. Logout thất bại một phần

Nếu server đã revoke nhưng browser không nhận response, cookie có thể còn nhưng server phải từ chối nó. Nếu server không xử lý được request, client có thể xóa local state để tránh sử dụng nhầm, nhưng UI không nên khẳng định server session đã được revoke.

Logout cần idempotent để retry an toàn. Không cho refresh response cũ tạo lại session sau logout.

### 12.2. Back button và cached page

Browser có thể khôi phục nội dung trang từ memory hoặc back-forward cache sau logout. Trang cũ có thể vẫn hiển thị dữ liệu đã render, nhưng API phải từ chối request mới bằng session revoked. Với dữ liệu nhạy cảm:
- Dùng Cache-Control phù hợp, thường là no-store cho response nhạy cảm.
- Xử lý page restore và kiểm tra session trước khi tiếp tục action.
- Xóa dữ liệu riêng tư khỏi UI state.
- Không coi việc redirect về login là authorization control.

## 13. Quản lý nhiều session và account lifecycle

Một account có thể có nhiều session trên điện thoại, laptop, tablet, browser profile và ứng dụng khác nhau. Người dùng cần cách xem và kết thúc session; tổ chức cần khả năng revoke khi có incident.

### 13.1. Session inventory

Có thể hiển thị:
- Tên thiết bị hoặc browser ở mức dễ hiểu.
- Thời điểm tạo và hoạt động gần nhất.
- Vị trí mạng ở mức khái quát nếu có mục đích.
- Ứng dụng/client.
- Phương thức authentication gần nhất.
- Trạng thái active/revoked.
- Tùy chọn logout session cụ thể hoặc tất cả session.

Không hiển thị session ID, cookie hoặc token. Device label và IP chỉ là metadata ước lượng, không phải bằng chứng chắc chắn người dùng ở vị trí đó.

### 13.2. Account disable và credential changes

Khi account bị disable, password reset do compromise hoặc authenticator bị thu hồi, policy cần xác định session nào bị ảnh hưởng:
- Thu hồi tất cả session.
- Thu hồi session của một client.
- Buộc re-authentication.
- Tăng authz/session version.
- Thu hồi refresh token và grant.
- Kiểm tra access token đã phát hành và giới hạn cửa sổ hiệu lực.

Không giả định password change luôn tự động kết thúc mọi browser session. Hành vi phụ thuộc ứng dụng và phải được quy định rõ.

### 13.3. Privilege elevation

Khi user được cấp quyền admin hoặc chuyển tenant, session hiện tại có thể mang state/claims cũ. Có thể yêu cầu session rotation, re-authentication và kiểm tra authorization mới. Không giữ quyền cũ hoặc thêm quyền mới chỉ bằng cách sửa client-side state.

## 14. Browser privacy và dữ liệu session

Session metadata có thể tiết lộ hoạt động, thiết bị, địa chỉ mạng, thời gian làm việc và quan hệ account. Chỉ thu thập dữ liệu cần thiết.

Nguyên tắc:
- Không đưa PII hoặc secret vào session ID.
- Không lưu raw cookie trong log, trace, analytics hoặc crash report.
- Giới hạn retention của session metadata.
- Phân quyền truy cập session inventory.
- Mask IP/device data khi mục đích không cần độ chi tiết đầy đủ.
- Tách tenant và environment.
- Audit thao tác admin xem/revoke session.
- Xóa session record và metadata khi hết mục đích theo retention policy.
- Không dùng browser fingerprint để theo dõi người dùng ngoài mục đích bảo mật đã công bố.

Cookie là dữ liệu nhạy cảm ngay cả khi chỉ chứa identifier ngẫu nhiên. Việc ghi cookie vào telemetry có thể tạo một bản sao bearer credential tồn tại lâu hơn session gốc.

## 15. Threat model cho browser session

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Session fixation** | Attacker khiến nạn nhân dùng session ID attacker biết trước khi login. | Attacker tiếp tục dùng session sau khi nạn nhân xác thực. | Tạo ID mới sau login/privilege change; revoke ID cũ. |
| **Session theft** | Cookie bị lấy qua XSS, malware, log hoặc endpoint. | Attacker truy cập như principal hợp lệ. | Secure, HttpOnly, TLS, redaction, endpoint protection và revoke. |
| **CSRF** | Browser tự gửi cookie tới request attacker kích hoạt. | Thực hiện action trái ý người dùng. | CSRF token, SameSite, Origin check, safe methods. |
| **XSS session abuse** | Script chạy trong origin dùng session tự động. | Đọc dữ liệu hoặc thực hiện action dưới session. | Output encoding, CSP, dependency hygiene, step-up. |
| **Cookie scope too broad** | Domain cookie chia sẻ tới subdomain không tin cậy. | Subdomain yếu có thể tăng nguy cơ lộ/session abuse. | Host-only cookie, __Host- prefix và subdomain inventory. |
| **Weak session ID** | Identifier đoán được hoặc có cấu trúc. | Attacker chiếm session bằng guessing. | CSPRNG, entropy cao và rate limiting. |
| **Stale session** | Account bị disable/revoke nhưng session còn active. | Truy cập tiếp sau khi mất quyền. | Server-side revoke, version check và cache invalidation. |
| **Idle timeout bypass** | Background polling liên tục reset idle timer. | Session kéo dài ngoài ý muốn. | Định nghĩa user activity và absolute timeout. |
| **Refresh/logout race** | Response refresh đến sau logout. | Client khôi phục state đã kết thúc. | Generation/version, serialization và idempotency. |
| **SSO scope confusion** | RP logout nhưng IdP session vẫn active. | Người dùng tưởng đã logout toàn hệ thống. | Hiển thị phạm vi và federation logout khi cần. |
| **Back-button exposure** | Browser phục hồi trang đã render trước logout. | Người dùng khác nhìn thấy dữ liệu cũ. | No-store phù hợp, page restore handling và API checks. |
| **Session logging** | Cookie bị ghi vào log hoặc telemetry. | Log trở thành kho credential. | Redaction trước khi lưu, audit test và access control. |

## 16. Kiến trúc và pseudocode session middleware

Một middleware session cần thực hiện kiểm tra trước khi gắn principal vào request context.

    resolveBrowserSession(request):
        cookie = readExpectedSessionCookie(request)
        require cookie exists
        require cookie.length <= MAX_SESSION_COOKIE_LENGTH

        sessionReference = keyedHash(cookie.value)
        session = sessionStore.lookup(sessionReference)

        require session exists
        require session.status == "active"
        require nowUtc() < session.idleExpiresAt
        require nowUtc() < session.absoluteExpiresAt
        require accountIsAllowed(session.subjectId)
        require session.clientId == expectedApplication

        if session.version != currentSessionVersion(session.subjectId):
            rejectAndClearCookie()

        updateLastSeenAccordingToActivityPolicy(session)
        return verifiedPrincipal(session)

    authorizeBrowserRequest(principal, request):
        require csrfValidWhenCookieAuthChangesState(request)
        require originAllowedWhenRequired(request)
        require endpointPolicyAllows(principal, request)
        require resourceBelongsToAllowedTenant(principal, request.resource)
        return allow

Đây là pseudocode minh họa. Thực tế cần kiểm tra encoding, duplicate cookie names, proxy behavior, clock source, cache consistency, race và error handling. Không trả session store internals cho client.

### 16.1. Error handling

- Cookie thiếu hoặc malformed: xử lý như anonymous.
- Session không tồn tại, revoked hoặc expired: từ chối và xóa cookie nếu phù hợp.
- Session store timeout: áp dụng fail-closed hoặc fallback đã được phê duyệt cho resource đó; không coi lookup thất bại là session hợp lệ.
- Account disabled: từ chối session và kích hoạt revoke theo policy.
- CSRF failure: từ chối state-changing request và ghi reason code.
- Internal error: không lộ session identifier hoặc thông tin account trong response.

### 16.2. Cookie response

Ví dụ response đặt cookie:

    HTTP/1.1 200 OK
    Set-Cookie: __Host-session=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
    Cache-Control: no-store

Ví dụ response xóa cookie:

    HTTP/1.1 204 No Content
    Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
    Cache-Control: no-store

Khi xóa cookie, tên và phạm vi Domain/Path phải khớp cookie ban đầu. Với prefix __Host-, không thêm Domain và giữ Path=/ cùng Secure.

## 17. Kiểm thử browser session

Kiểm thử cần bao phủ cả browser behavior và server-side session state.

| Test case | Kết quả mong đợi |
| --- | --- |
| Login thành công | Server tạo session ID mới, cookie có flags phù hợp. |
| Session ID trước login được gửi lại sau login | Identifier cũ không được dùng; session được rotate. |
| Cookie thiếu hoặc bị sửa | Request protected bị từ chối. |
| Cookie gửi qua HTTP | Browser không gửi cookie Secure; HTTP được redirect/chặn theo policy. |
| JavaScript đọc document.cookie | Không đọc được cookie HttpOnly. |
| Cross-site form POST | CSRF token/Origin/SameSite controls chặn request trái phép. |
| SameSite policy trong OIDC callback | Login flow hoạt động theo response mode đã kiểm thử, không mở CSRF gap. |
| Idle timeout đã qua | Session bị từ chối dù cookie còn trong browser. |
| Absolute timeout đã qua | Session bị từ chối dù có background activity. |
| Logout ở tab A, request từ tab B | Server từ chối session đã revoked. |
| Refresh response đến sau logout | Client không khôi phục session/token state. |
| Account bị disable | Session cũ bị revoke hoặc từ chối theo policy. |
| Role/tenant thay đổi | Quyền cũ không tiếp tục được dùng vượt consistency window. |
| Subdomain không tin cậy | Không nhận session cookie host-only của ứng dụng chính. |
| Browser restore/back button | API vẫn bảo vệ dữ liệu; trang nhạy cảm không tiếp tục thao tác với session cũ. |
| Session store unavailable | Fallback đúng policy; không fail-open ngoài ý muốn. |
| Log/trace collection | Không chứa raw cookie hoặc session secret. |
| Nhiều browser profile | Logout một profile không được mô tả sai là logout mọi profile. |

Kiểm thử trên các browser mục tiêu và các cấu hình privacy khác nhau. Cookie/SameSite behavior có thể khác theo browser version, enterprise policy và third-party cookie restrictions.

## 18. Tình huống thực hành: session vẫn hoạt động sau khi người dùng logout

**Bối cảnh:** Học viên Minh đăng nhập vào cổng học tập trên laptop. Minh mở hai tab. Ở tab thứ nhất, Minh bấm Logout; giao diện chuyển về trang đăng nhập. Tab thứ hai vẫn hiển thị trang hồ sơ đã mở trước đó. Một request nền từ tab thứ hai gửi cookie cũ tới API.

**Phân tích:**

1. Nếu ứng dụng chỉ xóa cookie trong response mà không revoke server-side session, cookie đã sao chép vẫn có thể được sử dụng.
2. Nếu server đã revoke, request mới từ tab thứ hai phải bị từ chối dù tab vẫn giữ state cũ.
3. Trang đã render có thể còn trong memory hoặc back-forward cache; nội dung cũ không chứng minh session còn active.
4. Nếu refresh request đang chạy, response đến muộn có thể làm client vô tình lưu state mới.
5. Logout local không nhất thiết kết thúc IdP SSO session.

**Thiết kế đúng:**

- Server revoke session trước khi trả kết quả logout.
- Mọi node kiểm tra trạng thái session mới nhất theo consistency policy.
- Cookie được xóa với đúng Path/Domain và flags.
- Broadcast event logout để các tab xóa UI state và dừng background refresh.
- Refresh response kiểm tra generation/session version trước khi lưu.
- API từ chối request mới dùng session revoked.
- Response dữ liệu nhạy cảm dùng cache policy phù hợp và xử lý page restore.
- UI mô tả rõ đã logout khỏi ứng dụng hiện tại hay toàn bộ IdP/SSO.

**Câu hỏi:** Nếu tab thứ hai vẫn hiển thị tên Minh sau logout, có nghĩa attacker còn truy cập được không? Chưa thể kết luận chỉ từ UI. Cần kiểm tra session state phía server và thử request protected mới. Nội dung đã render có thể còn trong browser; API phải từ chối request dùng session đã thu hồi.

## 19. Checklist thiết kế browser session

- [ ] Xác định rõ browser session, authentication event, IdP session và HTTP connection khác nhau.
- [ ] Coi session cookie là bearer credential và bảo vệ như secret.
- [ ] Tạo session ID bằng CSPRNG với entropy cao; không nhúng PII hoặc ID tuần tự.
- [ ] Lưu session state hoặc verifier an toàn; không log raw cookie.
- [ ] Dùng HTTPS, Secure, HttpOnly và SameSite theo flow.
- [ ] Ưu tiên host-only cookie; cân nhắc __Host- prefix cho session cookie.
- [ ] Không dựa vào Path như ranh giới bảo mật hoặc Domain rộng nếu không cần.
- [ ] Thực thi idle timeout và absolute timeout ở server.
- [ ] Rotate session ID sau login, privilege elevation và thay đổi trust quan trọng.
- [ ] Vô hiệu hóa session ID cũ sau rotation.
- [ ] Định nghĩa authentication freshness và step-up cho action nhạy cảm.
- [ ] Bảo vệ state-changing request trước CSRF; không dùng GET để thay đổi trạng thái.
- [ ] Hiểu SameSite, site/origin và CORS; không coi CORS là CSRF defense.
- [ ] Chống XSS bằng output encoding, CSP và dependency controls; HttpOnly không đủ.
- [ ] Chọn BFF hoặc SPA token storage theo threat model; tránh lưu refresh token dài hạn trong localStorage.
- [ ] Phân biệt cookie session với access token, ID Token và refresh token.
- [ ] Xử lý multi-tab, refresh/logout race và browser profile đúng phạm vi.
- [ ] Thu hồi server-side session khi logout, account disable hoặc compromise.
- [ ] Xác định tác động của password reset, authenticator revoke và role/tenant changes lên session.
- [ ] Kiểm soát cache/back-forward restore và dữ liệu nhạy cảm trên shared device.
- [ ] Có session inventory, revoke-current/all sessions và audit phù hợp.
- [ ] Kiểm thử cookie flags, fixation, theft, CSRF, XSS, timeout, SSO, race và store outage.

## 20. Câu hỏi tự kiểm tra

**1. Browser session là gì?**  
Là trạng thái truy cập mà ứng dụng duy trì giữa nhiều request của cùng browser sau khi authentication, thường được tham chiếu bằng session cookie.

**2. Vì sao session cookie là bearer credential?**  
Vì server thường chấp nhận cookie như bằng chứng sở hữu session; ai lấy được cookie còn hiệu lực có thể sử dụng session đó.

**3. Stateful và stateless session khác nhau thế nào?**  
Stateful lưu session record phía server và dùng cookie opaque ID; stateless có thể xác minh token có chữ ký mà không tra record mỗi request, nhưng revoke và cập nhật claims khó hơn.

**4. Vì sao phải rotate session ID sau login?**  
Để ngăn session fixation, trong đó attacker biết identifier trước authentication và cố sử dụng lại sau khi nạn nhân đăng nhập.

**5. HttpOnly có chặn XSS hoàn toàn không?**  
Không. Nó hạn chế JavaScript đọc cookie, nhưng XSS vẫn có thể gửi request cùng origin và thực hiện action dưới session hiện tại.

**6. SameSite có thay thế CSRF token không?**  
Không. SameSite là một lớp bảo vệ; cần kết hợp request token, Origin/Referer checks và thiết kế method an toàn theo kiến trúc.

**7. Idle timeout và absolute timeout khác nhau thế nào?**  
Idle timeout dựa trên thời gian không có hoạt động phù hợp; absolute timeout giới hạn tổng tuổi session dù vẫn có request.

**8. Logout có cần revoke session phía server không?**  
Có. Chỉ xóa cookie ở browser không làm cookie đã sao chép trở nên vô dụng.

**9. Logout khỏi ứng dụng có kết thúc IdP SSO session không?**  
Không mặc nhiên. RP và IdP thường có session riêng; cần federation logout nếu muốn kết thúc phạm vi rộng hơn.

**10. Nếu tab cũ vẫn hiển thị dữ liệu sau logout thì sao?**  
Nội dung đã render có thể còn trong memory/cache. Server vẫn phải từ chối request mới bằng session revoked và ứng dụng cần xử lý page restore để tránh lộ dữ liệu.

**Ghi nhớ:** Browser session duy trì trạng thái truy cập sau một lần authentication, thường qua cookie chứa identifier ngẫu nhiên. Hãy bảo vệ cookie, rotate session sau thay đổi trust, thực thi idle/absolute timeout, chống CSRF và XSS, quản lý nhiều tab/SSO, rồi revoke server-side khi logout hoặc account mất quyền. Cookie còn trong browser không có nghĩa session vẫn hợp lệ; trạng thái server và authorization policy mới quyết định request có được chấp nhận hay không.
