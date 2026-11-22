# Token storage ở browser, mobile và server

## 1. Vì sao vị trí lưu token quyết định mức độ an toàn?

Token là thông tin xác thực dạng bearer trong nhiều hệ thống: ai lấy được token và gửi nó đúng cách có thể hành động dưới danh tính hoặc quyền mà token đại diện. Chữ ký JWT, HTTPS hay thời hạn ngắn đều không cứu được token nếu ứng dụng lưu nó ở nơi dễ bị đọc, vô tình đưa nó vào log hoặc để một thành phần khác sử dụng sai phạm vi.

Token storage là quyết định về ranh giới tin cậy. Browser có JavaScript và nhiều cơ chế lưu trữ cùng nguồn; mobile có kho bảo mật do hệ điều hành quản lý; server có secret manager, KMS, database và bộ nhớ tiến trình. Mỗi môi trường có mô hình tấn công khác nhau, nên không có một vị trí lưu duy nhất phù hợp cho mọi loại token.

Một thiết kế cần trả lời:

- Token đại diện cho ai: người dùng, ứng dụng, tenant hay workload?
- Token là access token ngắn hạn, refresh token dài hạn, API key hay credential gọi dịch vụ?
- Thành phần nào cần đọc token để gửi request? JavaScript, native app, backend hay worker?
- Kẻ tấn công có thể đọc bộ nhớ, chạy script cùng origin, lấy backup thiết bị, truy cập log hoặc xâm nhập server không?
- Token có được mã hóa khi lưu, giới hạn quyền, xoay vòng, thu hồi và xóa đúng lúc không?
- Khi người dùng logout, mất thiết bị hoặc bị thu hồi quyền, những bản sao token ở đâu phải bị vô hiệu hóa?

Nguyên tắc chung là lưu token ở nơi có ít thành phần nhất có thể truy cập, giữ thời gian tồn tại ngắn nhất đáp ứng nghiệp vụ và giới hạn quyền theo đúng mục đích sử dụng. Không xem việc mã hóa ổ đĩa hoặc mã hóa database là đủ nếu tiến trình không đáng tin vẫn có thể đọc token.

## 2. Phân loại token trước khi chọn nơi lưu

Không nên xử lý mọi chuỗi có tên token như nhau. Khả năng lộ và hậu quả của từng loại khác nhau.

| Loại | Mục đích | Đặc điểm lưu trữ |
|---|---|---|
| Access token | Gọi API tài nguyên | Thường ngắn hạn; chỉ cấp scope/audience cần thiết; có thể giữ trong bộ nhớ khi đang sử dụng |
| Refresh token | Xin access token mới | Giá trị dài hạn, rủi ro cao; cần bảo vệ chặt, rotation và phát hiện reuse |
| ID token | Chứng minh kết quả xác thực cho client | Dùng để xác nhận danh tính; không mặc định dùng thay access token để gọi API |
| API key | Định danh hoặc cấp quyền cho tích hợp | Có thể tồn tại lâu; cần quản lý secret, scope, hạn dùng và rotation |
| Client secret | Xác thực confidential client với authorization server | Chỉ lưu ở môi trường server được kiểm soát; không nhúng vào browser hay mobile app phân phối công khai |
| Service/workload credential | Cho service gọi service hoặc cloud API | Ưu tiên identity và credential ngắn hạn do nền tảng cấp |
| Opaque session token | Tham chiếu tới session phía server | Server giữ trạng thái session; client chỉ giữ một định danh ngẫu nhiên khó đoán |

JWT là một định dạng token, không phải một phương pháp lưu trữ. JWT có thể là access token hoặc ID token; opaque token cũng có thể là access token. Cách lưu phải dựa trên mục đích, độ nhạy, vòng đời và thành phần cần sử dụng token.

Phân biệt thêm hai tình huống ở server:

1. **Server phát hành hoặc xác minh token của chính hệ thống:** có thể chỉ cần khóa ký, cấu hình issuer/audience và trạng thái thu hồi; không nhất thiết lưu từng access token JWT.
2. **Server lưu token người dùng cấp để gọi dịch vụ khác:** ví dụ refresh token OAuth của nhà cung cấp lưu trữ hoặc lịch. Server cần giữ bí mật đó để thực hiện thao tác thay mặt người dùng; thường phải mã hóa bằng khóa được quản lý riêng.

## 3. Threat model cho token storage

Các đường lộ token thường gặp:

| Đường tấn công | Hậu quả | Biện pháp chính |
|---|---|---|
| XSS hoặc script bên thứ ba | Đọc token mà JavaScript truy cập được, hoặc gửi request thay người dùng | Giảm XSS, CSP, kiểm soát dependency; tránh để token dài hạn trong vùng JavaScript đọc được |
| CSRF | Browser tự gửi cookie phiên tới endpoint ngoài ý muốn | SameSite, CSRF token, kiểm tra Origin/Referer và không dùng GET cho thay đổi trạng thái |
| Thiết bị mobile bị mất hoặc bị root/jailbreak | Đọc file, backup hoặc can thiệp tiến trình | Keychain/Keystore, mã hóa, hạn chế backup, token ngắn hạn và phát hiện rủi ro |
| Server hoặc container bị xâm nhập | Đọc token trong memory, file, environment hoặc secret store | Giảm quyền tiến trình, credential ngắn hạn, secret manager, cô lập workload và giám sát |
| Log, trace, crash report | Token bị sao chép sang hệ thống quan sát hoặc hỗ trợ | Redaction tại nguồn, không ghi Authorization/cookie/body nhạy cảm |
| URL, query string hoặc referrer | Token bị lưu trong history, proxy, analytics hoặc Referer | Không truyền bearer token trong URL |
| Backup, đồng bộ và thiết bị dùng chung | Token tồn tại ngoài vòng đời ứng dụng | Quy tắc backup, xóa dữ liệu, logout và thu hồi phía server |
| Clipboard, screenshot, notification | Token hoặc mã xác thực bị lộ cho ứng dụng khác/người quan sát | Không hiển thị token; hạn chế copy; không đặt bí mật trong notification |
| Dependency hoặc extension độc hại | Đọc dữ liệu trong ngữ cảnh ứng dụng | Giảm quyền, kiểm soát chuỗi cung ứng và phân tách origin/process |

Phải xác định đối thủ đang nhắm đến điều gì. Nếu mục tiêu là đánh cắp refresh token để duy trì quyền truy cập, việc chỉ giảm thời gian sống của access token chưa đủ. Nếu mục tiêu là thực hiện giao dịch qua session đang mở, cất token trong HttpOnly cookie không ngăn được XSS gửi request thay người dùng. Nếu server bị chiếm quyền điều khiển hoàn toàn, mã hóa token trong cùng tiến trình thường không ngăn được kẻ tấn công sử dụng token sau khi ứng dụng giải mã.

## 4. Browser: các lựa chọn lưu trữ

Browser cung cấp nhiều cơ chế, nhưng cần phân biệt khả năng tồn tại dữ liệu và khả năng JavaScript đọc dữ liệu.

| Vị trí | Vòng đời và phạm vi | JavaScript cùng origin đọc được? | Đánh giá với token |
|---|---|---|---|
| Biến trong memory | Thường mất khi reload/đóng tab hoặc tiến trình | Có, trong ngữ cảnh đang chạy | Giảm lưu trữ bền vững; XSS đang hoạt động vẫn có thể lấy hoặc sử dụng |
| sessionStorage | Theo origin và tab; thường kết thúc khi tab đóng | Có | Không chống XSS; có thể phù hợp dữ liệu tạm nếu chấp nhận rủi ro |
| localStorage | Bền qua lần mở browser; theo origin | Có | Không phù hợp để giữ refresh token hoặc bí mật dài hạn khi có nguy cơ XSS |
| IndexedDB | Lưu trữ có cấu trúc, bền qua phiên | Có | Không phải kho bí mật; script cùng origin có thể đọc |
| Cache API / service worker storage | Lưu request/response hoặc dữ liệu ứng dụng | Có thể truy cập qua script/service worker cùng origin | Không lưu Authorization hoặc response chứa token nếu không có yêu cầu rõ ràng |
| Cookie HttpOnly | Browser quản lý và tự gửi theo domain/path/attributes | Không đọc trực tiếp bằng JavaScript | Hữu ích cho session cookie/BFF; cần chống CSRF và cấu hình scope |
| Cookie không HttpOnly | Browser gửi theo cookie rules | Có | Không nên dùng cho bearer token nhạy cảm nếu JavaScript không cần đọc |

### 4.1 localStorage và sessionStorage

localStorage tồn tại qua nhiều lần mở browser và có thể được mọi script chạy cùng origin truy cập. Một đoạn XSS, dependency bên thứ ba bị xâm phạm hoặc extension có quyền phù hợp có thể đọc giá trị token rồi gửi ra ngoài. sessionStorage giới hạn vòng đời và phạm vi tab hơn, nhưng vẫn có thể bị JavaScript cùng origin đọc; nó không phải biện pháp chống XSS.

Không nên lưu refresh token dài hạn trong localStorage. Việc mã hóa token bằng một khóa mà JavaScript cũng có thể truy cập thường không giải quyết được vấn đề: script độc hại có thể lấy cả token lẫn khóa, hoặc gọi chính hàm giải mã của ứng dụng.

### 4.2 IndexedDB và Cache API

IndexedDB phù hợp với dữ liệu ứng dụng lớn, có cấu trúc hoặc cần hoạt động offline. Nó không được thiết kế như một kho bí mật chống lại script cùng origin. Cache API và service worker có thể giữ response lâu hơn vòng đời trang; nếu lưu response xác thực hoặc header Authorization, token có thể tồn tại trong cache ngoài dự kiến.

Chỉ lưu dữ liệu cần cho offline và phân loại rõ dữ liệu nào được phép lưu. Tránh cache response chứa access token, refresh token, session secret hoặc thông tin cá nhân nhạy cảm. Có quy trình xóa cache khi logout, đổi tài khoản hoặc thay đổi quyền.

### 4.3 Biến trong memory

Giữ access token trong memory làm giảm thời gian token tồn tại trong các kho lưu trữ bền vững và tránh token tự động còn lại sau khi đóng browser. Tuy nhiên, token vẫn có thể bị đọc bởi XSS đang hoạt động, debugger, extension hoặc script đã chiếm quyền thực thi trong trang.

Mô hình này thường phù hợp hơn việc lưu access token lâu dài ở localStorage khi SPA buộc phải gọi API trực tiếp. Kết hợp access token ngắn hạn, scope tối thiểu, CSP, Trusted Types khi phù hợp, kiểm soát script bên thứ ba và refresh flow an toàn. Nếu reload làm mất token, thiết kế luồng khôi phục session rõ ràng thay vì tự động chuyển refresh token dài hạn sang localStorage.

## 5. Browser: cookie, CSRF và mô hình BFF

Cookie có thuộc tính HttpOnly giúp JavaScript không đọc được giá trị cookie. Secure chỉ gửi cookie qua kết nối HTTPS. SameSite kiểm soát một số trường hợp cookie được gửi trong ngữ cảnh cross-site. Path và Domain giới hạn nơi browser gửi cookie; nên tránh Domain rộng nếu không cần chia sẻ giữa subdomain.

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-session=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Tiền tố __Host- yêu cầu cookie Secure, Path=/ và không có thuộc tính Domain trong các browser hỗ trợ quy tắc này. Dùng session ID ngẫu nhiên, khó đoán; server giữ trạng thái session và có thể thu hồi. Không đặt access token dài hạn trực tiếp vào cookie chỉ vì cookie có HttpOnly.

### 5.1 HttpOnly không loại bỏ mọi rủi ro XSS

HttpOnly ngăn script đọc giá trị cookie, nhưng script XSS vẫn có thể gửi request từ browser trong khi cookie tự động được đính kèm. Vì vậy, XSS vẫn có thể thực hiện hành động dưới session của người dùng, đọc dữ liệu trả về mà trang có quyền truy cập hoặc thay đổi thông tin hiển thị.

HttpOnly chủ yếu giảm khả năng trích xuất cookie để sử dụng ở một thiết bị khác. Cần tiếp tục phòng chống XSS bằng output encoding, sanitization đúng ngữ cảnh, CSP, kiểm soát dependency và tránh API nguy hiểm.

### 5.2 Cookie và CSRF

Cookie được browser tự động gửi theo quy tắc domain/path/SameSite. Điều này tạo nguy cơ CSRF nếu một website khác có thể khiến browser gửi request thay đổi trạng thái tới API.

Các lớp bảo vệ thường gồm:

- Đặt SameSite phù hợp. Lax thường là lựa chọn cân bằng; Strict có thể ảnh hưởng luồng điều hướng từ website khác; None yêu cầu Secure và chỉ dùng khi cần cross-site cookie.
- Dùng CSRF token theo mô hình synchronizer token hoặc double-submit cookie được thiết kế an toàn.
- Kiểm tra Origin, và khi phù hợp kiểm tra Referer, trên request thay đổi trạng thái.
- Không dùng GET cho thao tác thay đổi dữ liệu.
- Cấu hình CORS chính xác; không phản chiếu Origin tùy ý và không cho credentials với wildcard origin.
- Giới hạn cookie bằng Host/Path/SameSite và tránh domain scope rộng.

CORS không phải cơ chế chống CSRF. CORS chủ yếu kiểm soát việc JavaScript ở origin khác có được đọc response hay không; một số request vẫn có thể được gửi dù browser không cho script đọc response.

### 5.3 Backend for Frontend (BFF)

Với ứng dụng browser, mô hình BFF thường là lựa chọn tốt khi muốn giữ access/refresh token phía server. Browser chỉ giữ session cookie HttpOnly; BFF giữ token OAuth ở server và gọi API thay browser.

Luồng cơ bản:

~~~text
Browser
  |  session cookie (HttpOnly, Secure, SameSite)
  v
BFF / application backend
  |  access token / refresh token được lưu phía server
  v
Authorization server và Resource API
~~~

Ưu điểm:

- Token OAuth không được đưa vào JavaScript hoặc storage phía browser.
- BFF có thể áp dụng scope, audience, quota và authorization theo người dùng.
- Có thể thu hồi session phía server mà không phải xóa token ở mọi browser storage.
- Có một điểm kiểm soát log, refresh, timeout và gọi dependency.

BFF cũng có trách nhiệm bảo vệ session cookie và chống CSRF. Không cho endpoint BFF trở thành proxy tùy ý; xác thực quyền trên từng thao tác, giới hạn URL/host được gọi và không để browser chỉ định access token hoặc đích đến tùy ý.

### 5.4 Khi nào SPA giữ access token trực tiếp?

Một SPA có thể phải gọi resource server trực tiếp. Khi đó, cân nhắc:

1. Dùng OAuth Authorization Code Flow với PKCE cho public client; không dùng implicit flow cho ứng dụng mới.
2. Giữ access token ngắn hạn trong memory.
3. Tránh lưu refresh token lâu dài ở localStorage. Nếu nhà cung cấp hỗ trợ refresh token cho browser public client, yêu cầu rotation/reuse detection và đánh giá kỹ chính sách lưu trữ.
4. Giới hạn audience, scope và thời hạn access token.
5. Dùng CORS allowlist chính xác; CORS không thay thế kiểm tra authorization ở API.
6. Giảm XSS và script bên thứ ba; có cơ chế logout và xử lý token hết hạn.

Nếu ứng dụng cần session bền vững và refresh token dài hạn, BFF thường giảm bề mặt lộ token hơn việc lưu refresh token trong JavaScript-accessible storage.

## 6. Mobile: lưu token bằng cơ chế bảo mật của hệ điều hành

Ứng dụng mobile có thể bị phân tích, backup, debug hoặc chạy trên thiết bị đã root/jailbreak. File sandbox giúp cô lập ứng dụng khỏi app khác trong điều kiện bình thường, nhưng không nên coi mọi file trong sandbox là kho bí mật chống được người có quyền cao trên thiết bị.

Lựa chọn phổ biến:

| Nền tảng | Cơ chế | Cách sử dụng |
|---|---|---|
| iOS / iPadOS | Keychain Services | Lưu refresh token hoặc secret; chọn accessibility class phù hợp và giới hạn đồng bộ/backup |
| Android | Android Keystore | Tạo hoặc bảo vệ khóa mã hóa; khóa riêng có thể không xuất được khỏi Keystore |
| Android | Encrypted storage dùng khóa từ Keystore | Mã hóa dữ liệu token; quản lý vòng đời khóa và xử lý khi khóa bị invalidated |
| Cả hai | Bộ nhớ tiến trình | Giữ access token khi đang gọi API; xóa tham chiếu khi logout hoặc session kết thúc |

Không lưu token trong plain SharedPreferences, file JSON, database SQLite không mã hóa, logcat, crash log hoặc file cấu hình. Nếu dùng thư viện secure storage, cần hiểu thư viện thực sự sử dụng Keychain/Keystore như thế nào, có fallback không an toàn hay không, và dữ liệu có bị đưa vào backup hay đồng bộ cloud không.

### 6.1 iOS Keychain

Keychain là dịch vụ hệ điều hành để lưu thông tin nhạy cảm như password, key và token. Khi lưu refresh token:

- Chọn accessibility class phù hợp với việc app cần truy cập khi thiết bị khóa hay không.
- Cân nhắc giới hạn đồng bộ qua iCloud Keychain; token phiên thường không nên vô tình đồng bộ sang thiết bị khác.
- Dùng access control gắn với thiết bị hoặc xác thực người dùng nếu nghiệp vụ yêu cầu.
- Xử lý trường hợp item bị xóa, keychain restore hoặc trạng thái thiết bị thay đổi.
- Không nhúng token hoặc khóa bí mật vào binary, plist hay asset.

Sinh trắc học có thể bảo vệ thao tác truy cập Keychain qua chính sách hệ điều hành. Không nên tự lưu mẫu sinh trắc học hoặc coi kết quả sinh trắc học trong UI là token xác thực cho server.

### 6.2 Android Keystore

Android Keystore có thể tạo khóa và thực hiện thao tác mã hóa mà private key không cần rời khỏi vùng quản lý của hệ điều hành hoặc phần cứng bảo mật nếu thiết bị hỗ trợ. Một mẫu thiết kế là tạo khóa AES trong Keystore, dùng khóa đó mã hóa refresh token rồi lưu ciphertext trong vùng app private storage.

Các lưu ý:

- Kiểm tra mức bảo vệ khóa thực tế; không phải thiết bị nào cũng có StrongBox hoặc phần cứng bảo mật.
- Xử lý key invalidation, thay đổi khóa màn hình, backup/restore và gỡ cài đặt.
- Loại trừ ciphertext hoặc dữ liệu phiên khỏi Android backup nếu không có cơ chế phục hồi an toàn.
- Không lưu khóa mã hóa cạnh ciphertext dưới dạng plaintext.
- Không coi root detection là biện pháp bảo vệ duy nhất; nó có thể bị vượt qua và tạo false positive.

### 6.3 Sinh trắc học và khóa thiết bị

Face ID, Touch ID hoặc Android BiometricPrompt có thể yêu cầu người dùng xác nhận trước khi giải mã hoặc sử dụng một khóa. Sinh trắc học ở đây là lớp kiểm soát truy cập vào khóa cục bộ; server vẫn cần xác thực token, kiểm tra quyền và có thể yêu cầu xác thực tăng cường cho thao tác nhạy cảm.

Nếu thiết bị bị chiếm quyền điều khiển khi app đang mở, kẻ tấn công có thể thao tác trong ngữ cảnh đã được mở khóa. Hãy giới hạn thời gian session, yêu cầu xác thực lại cho thao tác quan trọng và hỗ trợ thu hồi session từ server.

## 7. OAuth trên mobile và public client

Ứng dụng mobile được phân phối tới thiết bị người dùng là public client: người dùng có thể giải nén, phân tích hoặc sửa binary. Không thể giữ client secret trong mobile app như một bí mật đáng tin cậy.

Với đăng nhập OAuth/OIDC, mô hình thường dùng:

1. Mở authorization request bằng system browser hoặc cơ chế trình duyệt được hệ điều hành quản lý.
2. Dùng Authorization Code Flow với PKCE.
3. Xác minh state để liên kết response với phiên bắt đầu đăng nhập; xác minh nonce khi dùng OIDC ID token.
4. Dùng redirect URI đã đăng ký chính xác; ưu tiên Universal Links/App Links hoặc cơ chế redirect được nhà cung cấp hỗ trợ.
5. Đổi authorization code cùng PKCE verifier lấy token.
6. Giữ access token trong memory và refresh token trong Keychain/Keystore hoặc secure storage dựa trên chúng.
7. Xoay vòng refresh token nếu authorization server hỗ trợ; xử lý reuse detection và lỗi token invalid.

Không nhúng client secret vào app, không tự xây OAuth login bằng WebView nhúng nếu nhà cung cấp không cho phép, không truyền code/token qua deep link không được bảo vệ và không ghi token vào analytics. PKCE bảo vệ authorization code khỏi một số kiểu interception; nó không mã hóa token sau khi token đã được cấp.

## 8. Server: lưu secret và token như dữ liệu có giá trị cao

Server có thể cần giữ:

- Client secret hoặc private key để xác thực với authorization server.
- Refresh token của người dùng để gọi dịch vụ bên thứ ba.
- API key của nhà cung cấp.
- Access token tạm thời của workload.
- Session hoặc opaque token do hệ thống tự phát hành.

### 8.1 Ưu tiên secret manager và workload identity

Không commit secret vào Git, Docker image, frontend bundle, file cấu hình chia sẻ hoặc script triển khai. Tránh lưu bí mật lâu dài trong biến môi trường nếu nền tảng có thể cấp secret qua secret manager hoặc workload identity; environment có thể xuất hiện trong process inspection, crash dump hoặc công cụ chẩn đoán.

Ưu tiên:

- Workload identity hoặc managed identity để service nhận credential ngắn hạn mà không cần khóa tĩnh.
- Secret manager/Vault để phân phối secret theo quyền, ghi audit và hỗ trợ rotation.
- KMS/HSM để quản lý khóa mã hóa hoặc khóa ký tách khỏi ứng dụng.
- Credential riêng theo môi trường, service và tenant khi phù hợp; không dùng một API key toàn hệ thống cho mọi chức năng.
- Quyền đọc secret chỉ cấp cho process thực sự cần; tách quyền đọc secret khỏi quyền quản trị secret.

Nếu buộc phải dùng file secret, giới hạn quyền filesystem, không đưa vào image hoặc source control, bảo vệ backup, xoay vòng và xóa an toàn khi thay thế. Không in nội dung secret khi kiểm tra cấu hình.

### 8.2 Mã hóa token khi lưu trong database

Nếu server phải dùng lại token gốc để gọi nhà cung cấp, database không nên lưu plaintext. Dùng envelope encryption:

1. Tạo data encryption key (DEK) cho dữ liệu hoặc nhóm bản ghi.
2. Mã hóa token bằng DEK với thuật toán xác thực như AES-GCM hoặc cơ chế AEAD phù hợp.
3. Mã hóa DEK bằng key encryption key (KEK) được quản lý trong KMS/HSM.
4. Lưu ciphertext, nonce/IV, authentication tag, key version và encrypted DEK.
5. Khi đọc, service có quyền yêu cầu KMS giải mã DEK rồi giải mã token trong bộ nhớ.

Không tự thiết kế thuật toán mã hóa. Dùng thư viện mật mã được duy trì, nonce duy nhất theo yêu cầu thuật toán và kiểm tra authentication tag. Không dùng cùng một key cho mọi mục đích như mã hóa dữ liệu, ký token và HMAC log.

Nên có key version để rotation. Khi xoay KEK, có thể rewrap DEK mà không cần giải mã và mã hóa lại toàn bộ token; khi xoay DEK, cần quy trình đọc bản cũ và ghi bản mới. Bảo vệ cả ciphertext và metadata vì token ID, tenant ID hoặc thời điểm kết nối cũng có thể nhạy cảm.

### 8.3 Khi nào chỉ cần hash token?

Nếu server chỉ cần xác minh một opaque bearer token mà không cần gửi lại token cho dịch vụ khác, có thể lưu hash thay vì giá trị gốc. Khi nhận token, tính hash/HMAC theo thiết kế rồi so sánh với giá trị lưu. Token phải được sinh ngẫu nhiên với entropy cao; không áp dụng cách lưu password thông thường một cách máy móc.

Nếu dùng HMAC với pepper, bảo vệ pepper trong KMS/secret manager và hỗ trợ phiên bản khóa. Hash/HMAC lưu trữ giúp giảm hậu quả khi database bị đọc trái phép. Tuy nhiên, nếu token cần được chuyển tiếp tới nhà cung cấp OAuth, hash một chiều không đủ; phải lưu ciphertext có thể giải mã được.

Với JWT access token được xác minh bằng chữ ký, resource server thường kiểm tra chữ ký, issuer, audience, thời hạn và claims mà không lưu từng token. Nếu cần thu hồi tức thời, có thể dùng token ngắn hạn, denylist theo jti, introspection hoặc session/version state tùy kiến trúc. Không mặc định rằng JWT stateless nghĩa là không cần quản lý vòng đời.

### 8.4 Token trong bộ nhớ server

Ngay cả khi database được mã hóa, token vẫn xuất hiện trong memory khi ứng dụng dùng nó. Giảm thời gian và phạm vi token tồn tại:

- Chỉ đọc token ngay trước khi gọi dependency; không giữ bản sao toàn cục nếu không cần.
- Không cache token lâu hơn thời hạn hoặc chính sách cần thiết.
- Giới hạn quyền đọc heap dump, core dump, profiler, debugger và công cụ APM.
- Không đưa token vào exception message, tracing attribute hoặc metric label.
- Không log request/response chứa Authorization, Set-Cookie, refresh token hoặc API key.
- Hạn chế process permission, container privilege, shell access và khả năng đọc memory của workload khác.
- Xóa hoặc bỏ tham chiếu khi không còn cần; hiểu rằng garbage collection không bảo đảm xóa ngay bản sao byte khỏi memory.

Nếu một server bị chiếm quyền thực thi với cùng quyền ứng dụng, kẻ tấn công có thể sử dụng token trong memory hoặc yêu cầu ứng dụng gọi dịch vụ. Secret manager giảm rủi ro lưu trữ và phân phối; nó không thay thế bảo vệ runtime.

## 9. Server lưu token OAuth của người dùng

Một backend tích hợp lịch, email hoặc lưu trữ có thể nhận refresh token từ authorization server để truy cập dịch vụ thay người dùng. Token đó là bí mật có thể cấp quyền dài hạn và thường phải được mã hóa khi lưu.

Thiết kế nên bao gồm:

1. Liên kết token với user, tenant, provider, client registration và tập scope đã cấp.
2. Lưu ciphertext, key version, thời điểm cấp/hết hạn, trạng thái và metadata cần thiết; không lưu plaintext trong bảng.
3. Phân quyền đọc/giải mã theo service và mục đích; worker chỉ được lấy token của tenant cần xử lý.
4. Refresh theo cơ chế provider hỗ trợ; khi refresh token rotation, lưu token mới nguyên tử trước khi đánh dấu token cũ không còn dùng.
5. Dùng lock hoặc coordination để hai worker không đồng thời refresh cùng một token.
6. Nếu provider báo invalid_grant hoặc phát hiện reuse, đánh dấu kết nối cần xác thực lại và dừng retry mù.
7. Khi người dùng disconnect, thu hồi token phía provider nếu hỗ trợ, xóa hoặc vô hiệu hóa ciphertext, cache và job liên quan.
8. Ghi audit ai đã kết nối, đổi scope, refresh, revoke hoặc truy cập secret; không ghi giá trị token.

Nếu một lần refresh thành công trả refresh token mới, cần cập nhật token và metadata trong một transaction hoặc quy trình có thể phục hồi. Nếu server crash giữa lúc provider xoay token và lúc database được cập nhật, token mới có thể bị mất và token cũ không còn hợp lệ. Cần thiết kế trạng thái refresh pending, khóa phân tán hoặc cơ chế phục hồi theo khả năng provider.

## 10. Vòng đời token: cấp, sử dụng, làm mới và thu hồi

Token storage an toàn phải đi cùng quản lý vòng đời. Lưu đúng chỗ nhưng không xoay vòng, không thu hồi hoặc không xóa khi logout vẫn tạo rủi ro.

### 10.1 Cấp token

- Cấp scope tối thiểu và audience đúng resource server.
- Access token nên có thời hạn phù hợp với mức độ nhạy cảm và khả năng thu hồi.
- Refresh token chỉ cấp khi client và flow cần; gắn với client, user, session hoặc thiết bị.
- Với public client, dùng PKCE và cơ chế refresh token rotation/reuse detection nếu được hỗ trợ.
- Không cấp client secret cho browser hoặc mobile app phân phối công khai.

### 10.2 Sử dụng token

- Gửi bearer token qua Authorization header trên TLS.
- Không gửi token trong query string, URL path, fragment, tên file hoặc cookie không có chính sách rõ.
- Kiểm tra audience, issuer, scope, expiry và trạng thái token ở resource server.
- Không dùng ID token làm access token.
- Không chuyển token của một audience sang API khác chỉ vì chữ ký hợp lệ.
- Tránh ghi token vào log, analytics, crash report, clipboard và thông báo.

### 10.3 Refresh token

Refresh token thường có giá trị cao hơn access token vì nó có thể tạo access token mới. Bảo vệ refresh token chặt hơn:

- Chỉ gửi tới authorization server đúng issuer qua TLS.
- Rotation: mỗi lần dùng thành công, thay token cũ bằng token mới.
- Reuse detection: nếu token cũ đã bị dùng lại sau khi xoay, có thể coi là dấu hiệu bị sao chép và thu hồi token family/session liên quan.
- Giới hạn thời hạn tuyệt đối và thời gian không hoạt động.
- Ràng buộc với client/device hoặc sender-constrained token khi nền tảng hỗ trợ.
- Có giới hạn số session/thiết bị và trang quản lý để người dùng thu hồi.

Rotation cần được triển khai nhất quán giữa server và client. Nếu hai request refresh đồng thời dùng cùng token, một request có thể làm token còn lại bị xem là reuse. Client nên điều phối refresh bằng một luồng duy nhất và lưu kết quả mới một cách nguyên tử.

### 10.4 Logout và thu hồi

Logout phía client cần xóa access token trong memory, refresh token trong secure storage nếu client giữ, session cookie và dữ liệu cache liên quan. Logout phía server cần thu hồi session hoặc refresh token theo chính sách, xóa bản lưu phía server và vô hiệu hóa credential được cấp nếu có thể.

Xóa token ở client không tự động thu hồi token đã bị sao chép. Nếu access token còn hiệu lực, kẻ tấn công có thể tiếp tục dùng nó cho đến khi hết hạn trừ khi resource server có cơ chế thu hồi hoặc kiểm tra trạng thái. Cân nhắc access token ngắn hạn, introspection, denylist, session version hoặc token family revocation theo mức rủi ro.

Với thiết bị bị mất, người dùng cần có khả năng thu hồi riêng session/thiết bị đó mà không nhất thiết phải đăng xuất toàn bộ thiết bị khác. Với credential server-to-server, cần quy trình rotate/revoke có thể thực hiện mà không phải dừng toàn bộ dịch vụ.

## 11. Không để token đi lạc khỏi storage dự kiến

Một token được lưu an toàn vẫn có thể lộ ở nơi khác trong quá trình sử dụng.

### 11.1 URL và trình duyệt

Không đưa bearer token vào query string. URL có thể xuất hiện trong browser history, access log, reverse proxy, analytics, monitoring, screenshot và Referer header. Fragment không gửi lên server theo HTTP request thông thường nhưng vẫn có thể bị JavaScript, extension hoặc lịch sử browser đọc; không dùng fragment như kho bí mật.

### 11.2 Log, trace và telemetry

Thiết lập redaction ở cả client logger, gateway, application, APM và hệ thống tập trung. Che hoặc loại bỏ:

- Authorization và Proxy-Authorization.
- Cookie, Set-Cookie và session ID.
- Access token, refresh token, API key và client secret trong body hoặc header tùy chỉnh.
- Signed URL và query parameter chứa credential.
- Request/response body nhạy cảm.

Không chỉ dựa vào regex tìm chuỗi token sau khi log đã được gửi đi. Tốt hơn là không đưa trường bí mật vào log từ đầu; nếu cần correlation, tạo ID ngẫu nhiên riêng không thể dùng để xác thực.

### 11.3 Clipboard, crash report và backup

Không cho người dùng copy token thô qua clipboard. Crash report có thể chứa memory snapshot, local variable hoặc request context; cấu hình loại trừ secret. Mobile backup cần loại trừ token hoặc chỉ backup dữ liệu đã mã hóa bằng khóa không được backup cùng dữ liệu. Browser storage có thể được đồng bộ hoặc khôi phục theo chính sách của browser/profile.

### 11.4 Header và cache

Không cache request hoặc response chứa credential một cách vô tình. Response có token trong body cần Cache-Control phù hợp; request Authorization phải được redaction ở proxy. Cấu hình CDN không lưu response xác thực nếu endpoint không thực sự công khai và cache key không phân tách an toàn.

## 12. Token storage theo từng môi trường

| Môi trường | Access token | Refresh token / credential dài hạn | Mô hình nên ưu tiên |
|---|---|---|---|
| Browser có BFF | BFF giữ và dùng; browser không cần biết token OAuth | Server lưu trong secret store/database mã hóa | Browser giữ session cookie HttpOnly, Secure, SameSite |
| SPA gọi API trực tiếp | Memory khi cần gọi API | Tránh lưu bền vững; nếu bắt buộc, rotation và đánh giá rủi ro kỹ | Authorization Code + PKCE, scope tối thiểu, access token ngắn hạn |
| iOS native app | Memory trong thời gian sử dụng | Keychain với accessibility phù hợp | Authorization Code + PKCE, external user agent |
| Android native app | Memory trong thời gian sử dụng | Keystore bảo vệ khóa mã hóa token trong app storage | Authorization Code + PKCE, secure storage và backup policy |
| Backend web application | Memory trong lúc gọi resource server | Secret manager hoặc database mã hóa bằng KMS | Session server-side, workload identity khi có thể |
| Worker/service-to-service | Memory ngắn hạn | Managed identity hoặc credential ngắn hạn; secret manager khi cần | Workload identity, audience/scope tối thiểu |

Đây là lựa chọn định hướng. Hệ thống có thể có ràng buộc offline, tích hợp nhà cung cấp hoặc yêu cầu tương thích khiến thiết kế khác đi; khi đó cần ghi rõ threat model và chấp nhận rủi ro nào.

## 13. Ví dụ: SPA dùng BFF và mobile dùng Keychain/Keystore

### 13.1 Browser với BFF

1. Người dùng đăng nhập qua authorization server.
2. BFF xử lý callback, xác minh state/nonce và đổi code ở phía server.
3. BFF lưu refresh token đã mã hóa, liên kết với session và user.
4. Browser nhận cookie session opaque với Secure, HttpOnly, SameSite và scope hẹp.
5. Browser gọi endpoint BFF; BFF kiểm tra session, quyền và CSRF trước khi gọi resource API.
6. BFF refresh token khi cần, cập nhật token mới nguyên tử và không trả token OAuth cho JavaScript.
7. Logout thu hồi session, xử lý refresh token và xóa cookie.

### 13.2 Mobile native

1. App mở system browser và khởi tạo Authorization Code + PKCE.
2. App xác minh state, nhận authorization code qua redirect đã đăng ký và đổi code bằng verifier.
3. Access token ở memory; refresh token được lưu trong Keychain hoặc được mã hóa bằng khóa Keystore.
4. App gửi access token trong Authorization header qua TLS.
5. Khi access token hết hạn, một luồng refresh duy nhất lấy token mới và cập nhật secure storage.
6. Khi logout, app xóa token cục bộ và gọi endpoint revoke/logout nếu có.

Trong cả hai mô hình, server vẫn xác minh token và quyền truy cập trên từng endpoint. Token storage không thay thế authorization, kiểm tra tenant hoặc validation nghiệp vụ.

## 14. Kiểm thử token storage

Kiểm thử không chỉ xác nhận token có thể đọc lại sau khi lưu; cần kiểm tra token có bị lộ, tồn tại quá lâu hoặc còn sử dụng được sau khi thu hồi hay không.

| Nhóm kiểm thử | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Browser XSS exposure | Kiểm tra storage và script cùng origin | Không có refresh token dài hạn trong localStorage; XSS controls được áp dụng |
| Cookie flags | Kiểm tra Set-Cookie trên HTTPS và subdomain | Secure/HttpOnly/SameSite/Path/Domain đúng chính sách |
| CSRF | Gửi request thay đổi trạng thái từ origin khác | Request bị chặn hoặc không có quyền thực hiện |
| CORS | Thử origin không được phép và credentials | Không phản chiếu origin tùy ý |
| Mobile at rest | Kiểm tra file, preferences, database và backup | Không có token plaintext ngoài secure storage |
| Mobile key lifecycle | Thay đổi trạng thái khóa/backup/restore | App xử lý key invalidation và yêu cầu đăng nhập lại an toàn |
| Server secret access | Workload không có quyền đọc secret | Bị từ chối; audit ghi nhận |
| Database disclosure | Đọc trực tiếp bản ghi token | Chỉ thấy ciphertext hoặc hash theo thiết kế |
| Log redaction | Tạo request lỗi có Authorization/cookie | Không có token trong log, trace hoặc crash report |
| Refresh rotation | Dùng token cũ sau khi đã xoay | Reuse detection/thu hồi theo chính sách |
| Concurrent refresh | Hai request refresh đồng thời | Không mất token mới hoặc tạo trạng thái session không nhất quán |
| Logout/revocation | Logout rồi thử dùng token cũ | Session/refresh bị thu hồi; access token bị giới hạn theo chính sách |
| Audience/scope | Dùng token đúng chữ ký nhưng sai audience/scope | Resource server từ chối |
| Expiry | Dùng token hết hạn hoặc trước thời điểm hợp lệ | Resource server từ chối đúng quy tắc |

Với mobile, thực hiện kiểm thử trên thiết bị thật và emulator; xác nhận hành vi backup/restore trên các phiên bản hệ điều hành hỗ trợ. Với browser, kiểm thử cả luồng qua CDN/BFF và ứng dụng thực tế, không chỉ dùng devtools ở local. Với server, kiểm tra quyền IAM/KMS và quy trình rotation trong môi trường staging.

## 15. Giám sát và ứng phó khi token bị lộ

Theo dõi các sự kiện mà không ghi giá trị token:

- Token được cấp, refresh, rotate, revoke và bị từ chối.
- Refresh token reuse hoặc refresh bất thường từ nhiều thiết bị/IP.
- Số session đang hoạt động theo user, client và thiết bị.
- Thay đổi scope, audience, client registration hoặc secret version.
- Truy cập secret manager/KMS bất thường, workload đọc secret ngoài phạm vi.
- Tỷ lệ token invalid, expired, revoked và lỗi introspection.
- Request cùng token/session xuất hiện đồng thời ở vị trí hoặc thiết bị bất thường, nếu có tín hiệu phù hợp.

Khi nghi token bị lộ:

1. Xác định loại token, chủ thể, scope, audience, thời điểm và hệ thống có thể đã nhận token.
2. Thu hồi session, refresh token family, API key hoặc credential liên quan theo phạm vi sự cố.
3. Nếu khóa ký hoặc client secret bị lộ, xoay khóa/secret và cập nhật các service phụ thuộc; đánh giá token đã ký bằng khóa cũ.
4. Xóa hoặc vô hiệu hóa bản lưu token trong database, cache, thiết bị và job chờ xử lý theo khả năng.
5. Kiểm tra log/audit để xác định hành động đã thực hiện; tránh đưa token vào báo cáo sự cố.
6. Cấp lại credential với scope tối thiểu và yêu cầu xác thực lại khi cần.
7. Sửa nguồn rò rỉ: storage, log, pipeline, backup, XSS, quyền IAM hoặc quy trình hỗ trợ.

Không gửi token qua chat, email hoặc ticket để “nhờ kiểm tra”. Nếu cần chia sẻ bằng chứng, dùng token fingerprint hoặc ID sự kiện đã che.

## 16. Các lỗi thiết kế thường gặp

1. **Lưu refresh token trong localStorage:** bất kỳ script cùng origin nào có thể đọc.
2. **Cho rằng sessionStorage chống XSS:** nó chỉ giới hạn phạm vi/vòng đời, không chặn script cùng origin.
3. **Cho rằng HttpOnly loại bỏ XSS:** script vẫn có thể gửi request bằng cookie đang được browser giữ.
4. **Dùng cookie mà không chống CSRF:** browser tự gửi cookie theo quy tắc của nó.
5. **Nhúng client secret trong mobile app:** binary công khai có thể bị phân tích.
6. **Lưu token mobile trong preferences/file plaintext:** backup hoặc truy cập thiết bị có thể làm lộ.
7. **Chỉ mã hóa token bằng khóa lưu cạnh token:** kẻ tấn công đọc được cả hai.
8. **Dùng hash cho token cần gửi lại nhà cung cấp:** hash một chiều không thể khôi phục giá trị gốc.
9. **Mã hóa token database nhưng log plaintext:** token vẫn bị lộ ở hệ thống quan sát.
10. **Không xử lý refresh token rotation đồng thời:** worker/client có thể tự làm mất session hợp lệ.
11. **Logout chỉ xóa local storage:** token bị sao chép vẫn có thể hoạt động.
12. **Tin JWT tự hết hạn là đủ:** access token còn hiệu lực và refresh token có thể duy trì quyền truy cập.
13. **Dùng ID token gọi API:** nhầm mục đích và audience của token.
14. **Dùng một secret chung cho nhiều service:** khó khoanh vùng, xoay vòng và thu hồi.

## 17. Quy trình chọn token storage cho một ứng dụng

Khi thiết kế một luồng xác thực hoặc tích hợp API, thực hiện:

1. Liệt kê từng loại token/credential và chủ thể mà nó đại diện.
2. Xác định thành phần nào thực sự cần đọc token; loại bỏ các bản sao không cần thiết.
3. Xác định threat model của môi trường: XSS/CSRF, thiết bị mất, root, server compromise, backup và log.
4. Chọn storage theo nền tảng: BFF/session cookie cho browser khi phù hợp; memory và Keychain/Keystore cho mobile; secret manager/KMS cho server.
5. Đặt access token ngắn hạn, refresh token rotation, scope/audience tối thiểu và giới hạn session.
6. Thiết kế mã hóa/hash theo nhu cầu: cần gửi lại thì mã hóa có quản lý khóa; chỉ xác minh opaque token thì cân nhắc hash/HMAC.
7. Quy định refresh, concurrent refresh, logout, revocation, device loss và key rotation.
8. Kiểm soát đường lộ phụ: URL, log, trace, crash dump, clipboard, backup, cache và notification.
9. Kiểm thử storage, quyền truy cập, token reuse, revocation và khả năng khôi phục.
10. Thiết lập audit, cảnh báo và quy trình ứng phó khi credential bị lộ.

## 18. Checklist rà soát

- [ ] Đã phân loại access token, refresh token, ID token, API key và service credential.
- [ ] Đã xác định thành phần nào cần đọc từng token và loại bỏ bản sao dư thừa.
- [ ] Browser không lưu refresh token dài hạn trong localStorage hoặc IndexedDB nếu không có threat model và biện pháp được phê duyệt.
- [ ] Cookie phiên có Secure, HttpOnly, SameSite và scope phù hợp; endpoint cookie-auth có CSRF protection.
- [ ] SPA/mobile public client dùng Authorization Code + PKCE; không nhúng client secret.
- [ ] Mobile lưu secret bằng Keychain/Keystore và có chính sách backup/restore, key invalidation.
- [ ] Server dùng workload identity/secret manager; token cần lưu lại được mã hóa bằng khóa quản lý riêng.
- [ ] Token chỉ cần xác minh được lưu hash/HMAC khi phù hợp; token cần dùng lại được lưu ciphertext.
- [ ] Token không xuất hiện trong URL, log, trace, crash report, clipboard hoặc analytics.
- [ ] Có rotation, reuse detection, expiry, logout và revocation.
- [ ] Có xử lý concurrent refresh và cập nhật token mới nguyên tử.
- [ ] Resource server kiểm tra issuer, audience, scope, expiry và quyền trên đối tượng.
- [ ] Có audit và quy trình xử lý khi token/secret bị lộ.

Token storage an toàn là sự kết hợp giữa vị trí lưu, quyền truy cập, thời gian tồn tại và vòng đời thu hồi. Browser cần giảm khả năng JavaScript lấy token; mobile cần tận dụng Keychain/Keystore và quản lý backup; server cần secret manager, mã hóa có quản lý khóa và kiểm soát runtime. Khi mỗi token chỉ tồn tại ở thành phần thực sự cần nó, với quyền tối thiểu và quy trình rotate/revoke rõ ràng, nguy cơ chiếm quyền qua token giảm đáng kể.
