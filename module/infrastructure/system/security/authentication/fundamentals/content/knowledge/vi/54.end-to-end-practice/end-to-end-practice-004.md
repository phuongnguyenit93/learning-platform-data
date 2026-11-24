# Thiết kế session

**Session** là cơ chế duy trì ngữ cảnh xác thực giữa nhiều yêu cầu độc lập. Sau khi người dùng đăng nhập thành công, hệ thống cần nhận biết các yêu cầu tiếp theo thuộc về cùng một phiên, xác định phiên còn hợp lệ hay đã hết hạn, áp dụng đúng quyền và cho phép người dùng kết thúc hoặc thu hồi phiên khi cần.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, session nối kết quả xác minh credential với các hành động sau đăng nhập. Một thiết kế session an toàn phải bảo vệ danh tính, mức bảo đảm xác thực, ranh giới tin cậy và trạng thái thu hồi. Nó cần hoạt động nhất quán khi người dùng đổi mật khẩu, bật MFA, mất thiết bị, đăng nhập trên nhiều trình duyệt, chuyển vùng dịch vụ hoặc yêu cầu đăng xuất.

Session ID thường là một giá trị ngẫu nhiên, khó đoán, được trình duyệt gửi lại trong cookie. Giá trị đó là bearer credential: bất kỳ ai lấy được session ID còn hiệu lực có thể có khả năng sử dụng phiên. Vì vậy, bảo vệ session cũng quan trọng như bảo vệ mật khẩu hoặc access token. Session không được chứa mật khẩu, seed MFA hay dữ liệu bí mật không cần thiết; nó chỉ nên giữ định danh và ngữ cảnh tối thiểu cần cho quyết định truy cập.

## 1. Phân biệt identity, authentication, session và authorization

Bốn khái niệm này liên quan nhưng không thay thế nhau:

- **Identity:** chủ thể mà hệ thống nhận biết, ví dụ người dùng user-482 hoặc workload billing-worker.
- **Authentication:** quá trình kiểm tra bằng chứng để xác định chủ thể. Mật khẩu, passkey, chứng chỉ và MFA có thể tham gia quá trình này.
- **Session:** ngữ cảnh có thời hạn cho phép hệ thống liên kết các yêu cầu sau xác thực với kết quả xác thực và trạng thái liên quan.
- **Authorization:** quyết định chủ thể được phép thực hiện hành động nào trên tài nguyên nào, tại thời điểm nào.

Đăng nhập thành công không có nghĩa người dùng được phép thực hiện mọi hành động trong suốt vòng đời session. Quyền có thể thay đổi; tài khoản có thể bị khóa; vai trò có thể bị thu hồi; phiên có thể phải xác thực lại trước thao tác nhạy cảm. Mỗi yêu cầu cần được kiểm tra theo chính sách hiện hành và ngữ cảnh phù hợp.

### 1.1. Session không đồng nghĩa với cookie

Cookie là cơ chế trình duyệt lưu và gửi dữ liệu theo domain/path và các thuộc tính được cấu hình. Session là khái niệm về trạng thái xác thực hoặc ngữ cảnh ứng dụng.

Một cookie có thể chứa session ID opaque trỏ đến trạng thái lưu ở máy chủ. Một cookie khác có thể chứa token tự chứa được ký. Ngược lại, một session có thể được xác định bằng header hoặc cơ chế của ứng dụng native. Vì vậy, cần đánh giá nội dung, quyền và vòng đời của dữ liệu xác thực thay vì chỉ nhìn tên cookie.

### 1.2. Session khác access token và refresh token

| Thành phần | Vai trò | Đặc điểm |
|---|---|---|
| Session ID | Tham chiếu đến phiên của ứng dụng | Thường opaque, ngẫu nhiên, được gửi trong cookie hoặc header |
| Access token | Mang quyền truy cập đến API/resource server | Có scope/audience/thời hạn; có thể là JWT hoặc opaque token |
| Refresh token | Xin access token mới | Thường sống lâu hơn access token và cần rotation/reuse detection |
| ID token | Assertion về kết quả xác thực trong OIDC | Dành cho client nhận biết sự kiện đăng nhập; không phải access token |
| Cookie | Cơ chế lưu và gửi dữ liệu phía browser | Có thuộc tính domain, path, Secure, HttpOnly, SameSite |

Một ứng dụng có thể dùng session phía máy chủ để giữ trạng thái đăng nhập và dùng access token ngắn hạn để gọi API. Đây là kiến trúc kết hợp. Cần xác định rõ thành phần nào chịu trách nhiệm timeout, logout, thu hồi và xác thực lại.

## 2. Chọn mô hình session

Không có một mô hình duy nhất phù hợp cho mọi ứng dụng. Hãy chọn theo kiểu client, số lượng dịch vụ, nhu cầu thu hồi, khả năng vận hành và mức rủi ro.

### 2.1. Session phía máy chủ (opaque session)

Ứng dụng tạo một session ID ngẫu nhiên, gửi cho client và lưu trạng thái phiên trong kho dữ liệu phía máy chủ. Mỗi yêu cầu mang session ID; ứng dụng tra cứu trạng thái và quyết định có chấp nhận hay không.

**Ưu điểm:**

- Thu hồi một phiên có thể có hiệu lực khi trạng thái được cập nhật và các điểm xác minh nhìn thấy thay đổi.
- Có thể lưu trạng thái đăng nhập, mức bảo đảm, thời điểm xác thực, thiết bị và phiên bản chính sách.
- Client chỉ giữ một định danh opaque, không cần tự giải mã dữ liệu phiên.
- Phù hợp với web application dùng browser cookie.

**Chi phí và rủi ro:**

- Cần kho session có tính sẵn sàng và khả năng mở rộng.
- Mỗi yêu cầu có thể cần truy vấn cache hoặc database.
- Cần xử lý nhất quán khi nhiều instance cùng cập nhật hoặc thu hồi phiên.
- Nếu session store bị lộ, session ID còn hiệu lực vẫn có thể bị sử dụng nếu không có thêm lớp bảo vệ.

### 2.2. Token tự chứa (self-contained token)

Một token như JWT chứa claim được ký, bên xác minh có thể kiểm tra chữ ký và claim mà không cần truy vấn kho session ở mỗi yêu cầu.

**Ưu điểm:**

- Xác minh phân tán có thể giảm phụ thuộc vào kho trạng thái trung tâm.
- Token có thể được dùng giữa nhiều dịch vụ theo audience và scope đã định.
- Bên xác minh có thể kiểm tra bằng public key được phân phối.

**Chi phí và rủi ro:**

- Thu hồi tức thời khó hơn nếu bên xác minh không tra cứu trạng thái bên ngoài.
- Claim trong JWS thường có thể đọc được; chữ ký không phải mã hóa.
- Thay đổi quyền hoặc trạng thái tài khoản có thể không phản ánh ngay trong token đã phát hành.
- Cần quản lý khóa ký, JWKS, thời hạn, issuer, audience và thuật toán.
- Token bearer bị đánh cắp có thể được dùng đến khi hết hạn hoặc bị cơ chế thu hồi phát hiện.

JWT không phải session store. Không nên nhét toàn bộ hồ sơ người dùng hoặc dữ liệu nhạy cảm vào token chỉ để tránh truy vấn dữ liệu.

### 2.3. Kiến trúc kết hợp

Một mô hình phổ biến là browser giữ cookie session opaque; backend lưu session; backend gọi API bằng access token ngắn hạn hoặc token nội bộ. Backend-for-Frontend (BFF) có thể giữ token ở phía máy chủ và chỉ phát hành cookie session cho browser.

Mô hình này giúp tránh đưa access token dài hạn vào JavaScript, nhưng BFF trở thành thành phần cần bảo vệ, mở rộng và kiểm thử. Phải có CSRF defense cho các thao tác dùng cookie, kiểm soát origin và bảo vệ session cookie.

### 2.4. Bảng chọn mô hình

| Nhu cầu | Mô hình thường phù hợp | Điều cần kiểm soát |
|---|---|---|
| Web app truyền thống | Opaque server-side session | Cookie, CSRF, session store, fixation |
| SPA có backend riêng | BFF và opaque session | Cookie, CSRF, token giữ phía backend |
| API cho nhiều client | OAuth access token | Audience, scope, expiry, sender constraint/revocation |
| Microservices nội bộ | Workload identity và token ngắn hạn | Xác thực service-to-service, audience, key rotation |
| Cần thu hồi phiên nhanh | Server-side state hoặc token introspection | Độ trễ lan truyền thu hồi |
| Cần xác minh offline | Token tự chứa thời hạn ngắn | Giới hạn quyền, key lifecycle và rủi ro token bị đánh cắp |

Quyết định phải được ghi trong kiến trúc và runbook. Không nên để mỗi nhóm tự chọn một cách lưu token hoặc session mà không có quy tắc chung.

## 3. Mô hình dữ liệu session

Một session nên lưu đủ thông tin để quyết định truy cập và quản lý vòng đời, nhưng không sao chép toàn bộ hồ sơ danh tính.

Một bản ghi có thể gồm:

| Trường | Mục đích |
|---|---|
| session_id_hash | Định danh phiên bằng giá trị đã băm/HMAC |
| subject_id | Người dùng hoặc workload sở hữu phiên |
| created_at | Thời điểm tạo phiên |
| authenticated_at | Thời điểm xác thực gần nhất đủ điều kiện |
| last_seen_at | Thời điểm hoạt động gần nhất |
| idle_expires_at | Mốc hết hạn do không hoạt động |
| absolute_expires_at | Mốc hết hạn tuyệt đối |
| auth_methods | Phương thức đã dùng, ví dụ passkey và MFA |
| assurance_level | Mức bảo đảm được xác minh |
| auth_time | Thời điểm xác thực theo ngữ nghĩa giao thức |
| device_label | Nhãn thiết bị do ứng dụng quản lý, không phải bằng chứng danh tính |
| session_version | Phiên bản hoặc epoch để phát hiện trạng thái cũ |
| status | active, revoked, expired hoặc trạng thái nội bộ tương đương |
| revoked_at | Thời điểm thu hồi nếu có |
| revocation_reason | Lý do được chuẩn hóa, không chứa secret |

Không cần lưu toàn bộ User-Agent hoặc IP như một thuộc tính nhận dạng đáng tin cậy. Có thể lưu một phần metadata đã giảm thiểu để phát hiện bất thường theo chính sách quyền riêng tư. User-Agent dễ bị giả mạo; IP có thể thay đổi do mạng di động, VPN hoặc proxy.

### 3.1. Session ID cần khó đoán

Session ID phải được sinh bằng CSPRNG, có entropy đủ lớn (thường ít nhất 128 bit, nhiều hệ thống chọn 256 bit) và không mang thông tin người dùng, email, quyền hoặc thời gian tạo có thể đoán được.

Ví dụ về cấu trúc opaque:

~~~text
s_7xQw...random-value...
~~~

Đây chỉ là minh họa; không dùng chuỗi ví dụ làm session ID thực. Không tự tạo session ID bằng số thứ tự database, timestamp, username hoặc hash của thông tin công khai.

Có thể lưu hash hoặc HMAC của session ID trong session store để giảm tác động nếu database bị đọc trái phép. Khi đó, hệ thống phải có cách tra cứu hiệu quả và quản lý khóa HMAC phù hợp. Dù chọn lưu dạng nào, session ID gửi cho client vẫn phải được giữ bí mật và không được ghi vào log.

### 3.2. Session không phải nơi lưu credential

Không lưu password, seed TOTP, private key, mã khôi phục hoặc client secret trong session. Nếu cần giữ thông tin xác thực tạm thời cho một giao dịch, dùng một state riêng có TTL ngắn, giới hạn mục đích và đánh dấu tiêu thụ một lần.

Không đưa dữ liệu cá nhân không cần thiết vào session. Giữ một subject ID ổn định và tra cứu thuộc tính hiện hành khi cần kiểm tra quyền.

## 4. Vòng đời session

Một session nên được mô hình hóa như một state machine để mọi hành động chuyển trạng thái đều có điều kiện rõ ràng.

~~~mermaid
stateDiagram-v2
    [*] --> Anonymous
    Anonymous --> PendingAuth: Bắt đầu đăng nhập
    PendingAuth --> Authenticated: Xác minh đầy đủ
    PendingAuth --> Anonymous: Hủy hoặc thất bại
    Authenticated --> StepUpRequired: Hành động cần assurance cao hơn
    StepUpRequired --> Authenticated: Xác minh bổ sung thành công
    StepUpRequired --> Revoked: Thất bại hoặc bị từ chối
    Authenticated --> Expired: Idle hoặc absolute timeout
    Authenticated --> Revoked: Logout / khóa tài khoản / sự cố
    Expired --> [*]
    Revoked --> [*]
~~~

Các trạng thái nội bộ có thể chi tiết hơn, nhưng không được nhầm lẫn trạng thái pending với authenticated. Chỉ chuyển sang authenticated sau khi toàn bộ bước xác thực bắt buộc hoàn tất.

### 4.1. Tạo session sau xác thực

Một luồng đăng nhập an toàn thường gồm:

1. Nhận yêu cầu đăng nhập và tạo transaction/challenge có TTL.
2. Xác minh credential theo chính sách: mật khẩu, passkey, chứng chỉ hoặc phương thức được phép.
3. Thực hiện MFA hoặc step-up nếu cần.
4. Xác định subject và mức bảo đảm của lần xác thực.
5. Tạo session ID mới bằng CSPRNG.
6. Lưu trạng thái session với thời hạn, phương thức xác thực, assurance và phiên bản chính sách.
7. Gửi cookie/session handle qua kênh TLS với thuộc tính bảo mật.
8. Hủy transaction đăng nhập đã dùng và các challenge không còn hợp lệ.
9. Ghi sự kiện audit không chứa session ID hoặc credential.

Không chuyển một session anonymous do client tự cung cấp thành authenticated mà vẫn giữ nguyên ID. Phải tạo ID mới để chống session fixation.

### 4.2. Gia hạn session

Có thể cập nhật thời gian idle khi có hoạt động hợp lệ. Tuy nhiên, không nên gia hạn vô hạn chỉ vì browser gửi request nền hoặc heartbeat. Xác định loại hoạt động nào được tính là hoạt động của người dùng và đặt absolute timeout độc lập.

Nếu gia hạn session ID theo chu kỳ, cần xử lý request đồng thời và cookie cũ đang trên đường truyền. Cơ chế grace period nếu có phải ngắn, giới hạn và không cho phép phiên cũ tiếp tục sau khi đã thu hồi hoàn toàn.

### 4.3. Hết hạn và thu hồi

Session có thể kết thúc vì:

- Người dùng đăng xuất.
- Idle timeout hoặc absolute timeout.
- Quản trị viên khóa tài khoản.
- Mật khẩu hoặc credential bị thay đổi theo chính sách.
- MFA/passkey bị thu hồi hoặc thiết bị bị mất.
- Phát hiện rủi ro hoặc hành vi đáng ngờ.
- Người dùng chọn đăng xuất mọi thiết bị.
- Ứng dụng hoặc tenant bị vô hiệu hóa.

Khi thu hồi, cập nhật trạng thái server-side và làm cho các điểm xác minh nhìn thấy thay đổi trong giới hạn đã cam kết. Xóa cookie phía client là cần thiết cho trải nghiệm nhưng không đủ để vô hiệu hóa bản sao cookie bị đánh cắp.

## 5. Chống session fixation và chiếm đoạt session

Session fixation xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết hoặc kiểm soát. Sau khi nạn nhân đăng nhập, session đó trở thành phiên đã xác thực. Kẻ tấn công có thể dùng lại ID đã biết để truy cập.

### 5.1. Luân chuyển ID tại ranh giới tin cậy

Tạo session ID mới sau các sự kiện quan trọng:

- Đăng nhập thành công.
- Hoàn tất MFA hoặc step-up làm thay đổi mức bảo đảm.
- Chuyển từ anonymous sang authenticated.
- Nâng quyền hoặc chuyển sang vai trò quản trị.
- Hoàn tất luồng account recovery.
- Thay đổi credential hoặc thiết bị tin cậy nếu chính sách yêu cầu.

Khi đổi ID, vô hiệu hóa ID cũ và chuyển dữ liệu cần thiết sang phiên mới theo thao tác nguyên tử. Không để cả ID cũ và ID mới cùng có quyền tương đương vô thời hạn.

### 5.2. Phòng chống session hijacking

Session hijacking là việc kẻ tấn công lấy được session handle và dùng nó để mạo danh người dùng. Các biện pháp chính:

- Chỉ truyền cookie/session handle qua HTTPS.
- Đặt Secure, HttpOnly và SameSite phù hợp.
- Không để session ID trong URL, query string, referrer hoặc log.
- Giới hạn TTL và scope của phiên.
- Xoay session ID ở các ranh giới quan trọng.
- Thu hồi nhanh khi phát hiện rò rỉ hoặc thiết bị mất.
- Bảo vệ browser khỏi XSS bằng output encoding, CSP và giảm bề mặt script.
- Kiểm tra CSRF với các thao tác thay đổi trạng thái.
- Không dựa vào IP hoặc User-Agent như cơ chế xác thực duy nhất.

HttpOnly ngăn JavaScript đọc cookie trực tiếp trong trình duyệt hỗ trợ thuộc tính này, nhưng không ngăn mã XSS thực hiện hành động dưới quyền người dùng. Vì vậy vẫn cần chống XSS và kiểm soát hành động nhạy cảm.

## 6. Thiết kế cookie session cho browser

Cookie là lựa chọn phổ biến để browser gửi session handle tự động. Thuộc tính cookie quyết định phạm vi và điều kiện gửi.

### 6.1. Thuộc tính quan trọng

| Thuộc tính | Tác dụng | Khuyến nghị |
|---|---|---|
| Secure | Chỉ gửi cookie qua kết nối bảo mật theo quy tắc browser | Bật cho session cookie production |
| HttpOnly | Không cho JavaScript đọc cookie | Bật cho cookie chứa session handle |
| SameSite | Hạn chế gửi cookie trong một số ngữ cảnh cross-site | Dùng Lax hoặc Strict tùy luồng; None cần Secure |
| Path | Giới hạn đường dẫn gửi cookie | Thường dùng / cho session toàn ứng dụng |
| Domain | Mở rộng cookie đến domain/subdomain | Không đặt nếu không cần chia sẻ |
| Max-Age / Expires | Thời gian tồn tại phía browser | Phù hợp với chính sách; server vẫn phải tự hết hạn |

Với session cookie, ưu tiên cookie host-only bằng cách không đặt Domain. Prefix __Host- có thể tăng ràng buộc trong browser hỗ trợ: cần Secure, Path=/ và không có Domain. Ví dụ:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị trong ví dụ là placeholder. Không dùng giá trị thật trong tài liệu, ticket hoặc log.

### 6.2. Chọn SameSite theo hành trình

- Strict hạn chế cookie trong điều hướng cross-site mạnh hơn, nhưng có thể làm gián đoạn một số luồng quay lại từ liên kết hoặc nhà cung cấp định danh.
- Lax thường là lựa chọn cân bằng cho web app thông thường và cho phép một số điều hướng top-level an toàn.
- None cho phép gửi trong ngữ cảnh cross-site và phải đi cùng Secure; chỉ dùng khi luồng thực sự cần.

Luồng OIDC hoặc SAML có thể quay về ứng dụng qua redirect hoặc POST cross-site. Cookie dùng để ràng buộc transaction có thể cần cấu hình khác cookie session chính. Không hạ SameSite của toàn bộ session cookie chỉ để làm callback hoạt động; hãy kiểm tra giao thức, dùng state/nonce/PKCE và cookie transaction riêng có TTL ngắn nếu cần.

### 6.3. Domain và subdomain

Cookie với Domain=example.com có thể được gửi đến nhiều subdomain theo quy tắc browser. Nếu một subdomain bị chiếm hoặc có ứng dụng ít tin cậy, phạm vi cookie mở rộng có thể tạo rủi ro. Dùng host-only cookie khi có thể; tách ứng dụng có mức tin cậy khác nhau trên domain phù hợp.

Path không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host. Không dùng Path để thay thế phân tách domain hoặc kiểm soát quyền truy cập.

## 7. Chống CSRF cho session dựa trên cookie

Browser tự động gửi cookie phù hợp với request. Điều này tạo nguy cơ Cross-Site Request Forgery (CSRF): một trang bên ngoài có thể khiến browser gửi request đến ứng dụng đang đăng nhập mà người dùng không chủ ý thực hiện.

### 7.1. Nguyên tắc

- Không dùng GET cho thao tác thay đổi trạng thái.
- Dùng CSRF token cho request thay đổi dữ liệu.
- Kiểm tra Origin hoặc Referer khi phù hợp.
- Dùng SameSite như một lớp phòng vệ bổ sung.
- Kiểm tra Fetch Metadata như Sec-Fetch-Site nếu nền tảng hỗ trợ.
- Không cho phép CORS credential rộng với origin tùy ý.
- Yêu cầu step-up hoặc xác nhận giao dịch cho hành động có rủi ro cao.

### 7.2. Synchronizer token

Với session phía máy chủ, ứng dụng có thể tạo CSRF token ngẫu nhiên gắn với session và lưu ở server. Token được gửi đến form hoặc response hợp lệ, rồi client gửi lại trong hidden field hoặc custom header. Server so sánh token với trạng thái session.

CSRF token không phải session ID và không nên dùng thay thế session handle. Token cần gắn với phiên, có entropy đủ lớn, không xuất hiện trong URL và được kiểm tra ở mọi endpoint thay đổi trạng thái.

### 7.3. Double-submit cookie

Một thiết kế double-submit đặt CSRF token trong cookie và yêu cầu client gửi cùng giá trị ở header hoặc body. Server so sánh hai giá trị. Nên dùng biến thể có chữ ký hoặc ràng buộc với session để tránh các vấn đề khi kẻ tấn công có thể đặt cookie từ subdomain hoặc lợi dụng cookie injection.

Không coi việc chỉ bật SameSite là biện pháp CSRF duy nhất. Cần kiểm tra luồng đăng nhập, callback liên kết danh tính và mọi endpoint thay đổi trạng thái.

## 8. Chống XSS và bảo vệ dữ liệu session

XSS cho phép script không tin cậy chạy trong origin của ứng dụng. Dù cookie có HttpOnly, script vẫn có thể gửi request bằng session của nạn nhân và đọc dữ liệu mà ứng dụng trả về.

Các biện pháp cần kết hợp:

- Output encoding theo ngữ cảnh HTML, attribute, JavaScript và URL.
- Tránh đưa dữ liệu người dùng vào DOM bằng API nguy hiểm.
- Dùng Content Security Policy phù hợp, hạn chế inline script và nguồn script.
- Kiểm soát dependency và script bên thứ ba.
- Không lưu access token hoặc session handle trong localStorage nếu có lựa chọn kiến trúc an toàn hơn.
- Hạn chế dữ liệu nhạy cảm trong response và cache phía browser.
- Yêu cầu step-up cho hành động đặc biệt nhạy cảm.

CSRF và XSS là hai nhóm rủi ro khác nhau. CSRF lợi dụng browser tự gửi credential; XSS chạy mã trong origin tin cậy và có thể thao tác trực tiếp với ứng dụng. Phòng vệ cần xử lý cả hai.

## 9. Idle timeout, absolute timeout và xác thực lại

Một session không nên tồn tại vô thời hạn. Timeout cần cân bằng trải nghiệm, rủi ro và loại hành động.

### 9.1. Idle timeout

Idle timeout kết thúc phiên khi không có hoạt động hợp lệ trong một khoảng thời gian. Mốc này thường được cập nhật khi có request được chấp nhận và được xem là hoạt động theo chính sách.

Không để request nền, polling hoặc heartbeat tự gia hạn phiên vô hạn. Phân biệt hoạt động của người dùng với hoạt động tự động của ứng dụng.

### 9.2. Absolute timeout

Absolute timeout giới hạn tổng tuổi thọ của phiên kể từ lúc xác thực, kể cả người dùng liên tục hoạt động. Khi đạt giới hạn, yêu cầu xác thực lại.

Absolute timeout giúp giới hạn thời gian một session bị đánh cắp có thể tồn tại mà không cần kẻ tấn công tiếp tục đánh cắp credential. Mốc này không được reset chỉ vì idle timeout được gia hạn.

### 9.3. Reauthentication và freshness

Một số hành động cần xác thực gần đây hoặc mức bảo đảm cao hơn, ví dụ:

- Đổi mật khẩu hoặc thay email khôi phục.
- Thêm/gỡ passkey, MFA hoặc thiết bị tin cậy.
- Xem hoặc thay đổi dữ liệu thanh toán.
- Tạo API key hoặc cấp quyền quản trị.
- Thực hiện thao tác nhạy cảm với dữ liệu khách hàng.
- Khôi phục tài khoản hoặc thay đổi phương thức recovery.

Có thể lưu auth_time, phương thức xác thực và assurance level trong session. Trước hành động nhạy cảm, so sánh độ mới của lần xác thực với yêu cầu chính sách và thực hiện step-up nếu cần. Không chỉ kiểm tra session còn active.

### 9.4. Ví dụ chính sách timeout

Các giá trị dưới đây chỉ minh họa; tổ chức cần đánh giá theo mức rủi ro, thiết bị, môi trường và yêu cầu nghiệp vụ.

| Loại phiên | Idle timeout minh họa | Absolute timeout minh họa | Kiểm soát bổ sung |
|---|---:|---:|---|
| Người dùng thông thường | 30 phút | 12 giờ | MFA theo chính sách; reauth cho hành động nhạy cảm |
| Tài khoản quản trị | 10 phút | 4 giờ | MFA chống phishing; step-up và audit |
| Phiên kiosk dùng chung | 5 phút | 30 phút | Xóa dữ liệu cục bộ và kết thúc phiên rõ ràng |
| Workload/service | Theo TTL credential/token | Theo chu kỳ cấp lại | Danh tính workload, scope và rotation |

Không sao chép các con số ví dụ vào production mà không phân tích rủi ro và kiểm thử trải nghiệm.

## 10. Logout và thu hồi phiên

Logout phải làm cho phiên không còn được chấp nhận ở phía máy chủ và dọn trạng thái phía client.

### 10.1. Logout cục bộ

Một luồng logout server-side có thể gồm:

1. Xác thực request logout và kiểm tra CSRF nếu dùng cookie.
2. Đánh dấu session là revoked hoặc xóa bản ghi theo thiết kế.
3. Thu hồi refresh token hoặc credential gắn với session nếu có.
4. Xóa cookie bằng Set-Cookie có cùng tên, Path và Domain phù hợp.
5. Hủy state phía client và xóa dữ liệu cache nhạy cảm.
6. Ghi audit event với subject, session reference đã che, thời điểm và lý do.

Chỉ xóa cookie trên browser không thu hồi bản sao cookie mà kẻ tấn công đã lấy. Server-side state phải thay đổi.

### 10.2. Đăng xuất một thiết bị hay mọi thiết bị

Mỗi thiết bị/trình duyệt nên có session riêng. Giao diện quản lý tài khoản có thể hiển thị nhãn thiết bị, thời điểm hoạt động gần nhất và vị trí gần đúng nếu chính sách quyền riêng tư cho phép. Người dùng có thể thu hồi một phiên hoặc tất cả phiên.

Không dùng User-Agent làm định danh duy nhất vì có thể giống nhau hoặc bị giả mạo. Dùng session ID nội bộ và metadata có giới hạn.

### 10.3. Logout trong SSO

Đăng xuất khỏi một ứng dụng không nhất thiết kết thúc session tại Identity Provider hoặc các ứng dụng khác. Trong môi trường SSO, cần phân biệt:

- **Local logout:** kết thúc session tại ứng dụng hiện tại.
- **IdP logout:** kết thúc session tại nhà cung cấp danh tính.
- **Single Logout (SLO):** điều phối kết thúc session giữa các bên tham gia theo giao thức và khả năng hỗ trợ.

Không giả định SLO luôn hoàn tất tức thời hoặc mọi client đều tham gia. UI cần mô tả đúng phạm vi đăng xuất. Ứng dụng phải xử lý callback logout có xác minh, tránh CSRF và bảo đảm local session đã bị thu hồi ngay cả khi IdP bên ngoài tạm thời không khả dụng.

### 10.4. Access token đã phát hành

Logout khỏi session không tự động làm mọi access token đã phát hành mất hiệu lực. Nếu API xác minh JWT offline, token có thể tiếp tục được chấp nhận đến khi hết hạn trừ khi có cơ chế thu hồi bổ sung.

Các lựa chọn gồm token lifetime ngắn, introspection, denylist theo jti, account/session version hoặc sender-constrained token. Cần chọn dựa trên độ trễ thu hồi chấp nhận được và chi phí vận hành.

## 11. Refresh token và session liên tục

Refresh token thường có tuổi thọ dài và quyền cấp access token mới, vì vậy cần được bảo vệ chặt.

### 11.1. Rotation

Với refresh token rotation, mỗi lần dùng token hiện tại để lấy token mới, authorization server phát hành token mới và vô hiệu hóa token cũ. Nếu token cũ được dùng lại, có thể là dấu hiệu token đã bị sao chép.

Cần lưu quan hệ token family và xử lý reuse detection theo giao thức. Khi phát hiện tái sử dụng, có thể thu hồi cả family và yêu cầu người dùng xác thực lại. Thao tác tiêu thụ token cũ và phát hành token mới phải nguyên tử để hai request đồng thời không cùng thành công ngoài chính sách.

### 11.2. Ràng buộc với client hoặc thiết bị

Nếu hệ thống hỗ trợ, sender-constrained token như mTLS hoặc DPoP có thể giảm rủi ro token bị đánh cắp và dùng từ client khác. Cơ chế này không loại bỏ mọi rủi ro: kẻ tấn công chiếm được cả token và khóa ràng buộc vẫn có thể sử dụng; cần bảo vệ private key và xác minh proof đúng cách.

### 11.3. Lưu token ở client

- Browser: cân nhắc BFF để token ở phía máy chủ; dùng cookie HttpOnly cho session và CSRF defense.
- SPA thuần: nếu phải giữ token phía client, đánh giá rủi ro XSS, thời gian sống, scope và cách bảo vệ; tránh coi localStorage là kho an toàn.
- Native mobile: dùng secure storage do nền tảng cung cấp và bảo vệ khóa thiết bị; không nhúng client secret chung.
- Service-to-service: ưu tiên workload identity và token ngắn hạn, tránh secret tĩnh dùng chung.

## 12. Quản lý nhiều session và thiết bị

Một người dùng có thể đăng nhập đồng thời trên laptop, điện thoại và trình duyệt khác. Thiết kế cần có chính sách cho số lượng phiên, khả năng thu hồi và hành vi bất thường.

### 12.1. Tách session theo thiết bị

Mỗi lần đăng nhập tạo session riêng với session reference nội bộ. Có thể lưu nhãn thiết bị do người dùng đặt, thời gian tạo, hoạt động gần nhất và phương thức xác thực. Không lưu fingerprint thiết bị quá mức cần thiết hoặc xem nó như bằng chứng danh tính tuyệt đối.

### 12.2. Giới hạn số phiên

Nếu cần giới hạn số phiên đồng thời, xác định rõ khi vượt giới hạn thì:

- Từ chối phiên mới.
- Thu hồi phiên cũ nhất.
- Yêu cầu người dùng chọn phiên cần kết thúc.
- Áp dụng khác nhau cho tài khoản đặc quyền và tài khoản thông thường.

Thao tác tạo phiên và thu hồi phiên cũ cần có transaction hoặc cơ chế đồng bộ để nhiều đăng nhập đồng thời không vượt giới hạn.

### 12.3. Thu hồi theo sự kiện bảo mật

Các sự kiện sau có thể yêu cầu thu hồi một hoặc nhiều session:

- Người dùng đổi hoặc reset mật khẩu.
- MFA hoặc passkey bị gỡ.
- Thiết bị bị mất hoặc đánh cắp.
- Quản trị viên vô hiệu hóa tài khoản.
- Phát hiện credential stuffing hoặc session hijacking.
- Thay đổi quyền quan trọng.
- Tài khoản được khôi phục sau sự cố.

Không phải mọi thay đổi hồ sơ đều cần logout tất cả thiết bị. Chính sách cần phân biệt thay đổi không nhạy cảm với thay đổi làm giảm độ tin cậy của credential hoặc danh tính.

## 13. Session trong kiến trúc phân tán

Khi ứng dụng chạy nhiều instance hoặc nhiều vùng, session state phải được chia sẻ và thu hồi nhất quán.

### 13.1. Session store dùng chung

Có thể dùng database, distributed cache hoặc dịch vụ session chuyên dụng. Cần xác định:

- TTL của bản ghi và cách đồng bộ với idle/absolute timeout.
- Khả năng replication và failover.
- Mức nhất quán cần cho trạng thái revoked.
- Cách xử lý cache stale và invalidation.
- Quyền truy cập giữa các service.
- Mã hóa dữ liệu lưu và audit truy cập.
- Cách restore mà không kích hoạt lại session đã thu hồi.

TTL ở cache không nên là cơ chế duy nhất quyết định session hợp lệ. Ứng dụng phải kiểm tra thời hạn và trạng thái trong dữ liệu có thẩm quyền.

### 13.2. Độ trễ thu hồi

Nếu một vùng vẫn dùng cache cũ, session đã thu hồi ở vùng khác có thể tiếp tục hoạt động. Cần đặt mục tiêu thời gian lan truyền thu hồi, phát sự kiện invalidation, dùng version/epoch hoặc tra cứu nguồn có thẩm quyền cho hành động nhạy cảm.

Với hành động rủi ro cao, nếu không xác minh được trạng thái thu hồi mới nhất, có thể tạm từ chối hoặc yêu cầu xác thực lại. Không nên âm thầm chấp nhận cache cũ vô thời hạn.

### 13.3. Session version hoặc security epoch

Một cách thiết kế là lưu session_version hoặc security_epoch ở cấp tài khoản. Session được tạo với phiên bản hiện hành. Khi cần thu hồi mọi phiên, hệ thống tăng epoch. Điểm xác minh so sánh phiên bản session với phiên bản hiện tại.

Cách này giảm nhu cầu cập nhật từng bản ghi nhưng vẫn cần phân phối phiên bản nhất quán. Nếu cache epoch bị stale, thu hồi có thể chậm. Cần kết hợp TTL cache, event invalidation hoặc kiểm tra trực tiếp cho hành động quan trọng.

### 13.4. Không để trạng thái cũ ghi đè thu hồi

Một race condition thường gặp: request A đọc session active; request B thu hồi session; sau đó request A ghi lại bản session cũ với trạng thái active. Kết quả là phiên bị hồi sinh.

Giải pháp gồm cập nhật có điều kiện theo version, transaction, compare-and-set, tombstone hoặc mô hình trạng thái chỉ chuyển theo hướng không thể hồi sinh. Mọi cập nhật phải kiểm tra trạng thái hiện hành trước khi ghi.

## 14. Chống race condition và xử lý request đồng thời

Một browser có thể gửi nhiều request gần như cùng lúc: API call, refresh, heartbeat và logout. Các request có thể đến các instance khác nhau và hoàn thành không theo thứ tự.

### 14.1. Refresh đồng thời

Nếu hai request dùng cùng refresh token đồng thời, hệ thống cần xác định chỉ một request được tiêu thụ thành công. Dùng transaction hoặc compare-and-swap để đánh dấu token đã dùng và phát hành token mới. Request còn lại phải bị xử lý theo chính sách reuse detection, không được tạo thêm hai nhánh token family hợp lệ.

### 14.2. Logout đồng thời với request nghiệp vụ

Khi logout xảy ra, request đang xử lý có thể đã vượt qua kiểm tra session trước thời điểm thu hồi. Với hành động nhạy cảm, có thể cần kiểm tra phiên gần thời điểm commit hoặc ràng buộc giao dịch với session version. Cần xác định rõ điểm tuyến tính hóa: thời điểm nào được coi là session đã bị thu hồi đối với thao tác đang chạy.

Không thể luôn hủy ngược một giao dịch đã commit. Vì vậy, hãy thiết kế điểm kiểm tra quyền gần nơi thực hiện side effect và ghi audit cho các hành động quan trọng.

### 14.3. Gia hạn và cập nhật last_seen

Nhiều request cùng cập nhật last_seen_at có thể gây ghi đè giá trị mới bằng giá trị cũ nếu dùng đồng hồ hoặc dữ liệu stale. Dùng phép cập nhật max hoặc logic nguyên tử. Không để một request đến trễ kéo dài session vượt absolute timeout.

### 14.4. Đồng hồ và thời gian

Dùng nguồn thời gian đồng bộ và thống nhất cách so sánh UTC. Tránh dựa vào đồng hồ client. Xác định sai số clock skew cho token và session, nhưng không mở rộng cửa sổ hiệu lực quá mức. Lưu thời gian tạo, idle và absolute expiry rõ ràng; kiểm tra thời hạn ở server.

## 15. Liên kết session với OIDC, SAML và IdP ngoài

Khi dùng federation, kết quả xác thực từ IdP cần được ràng buộc với browser transaction và session của ứng dụng.

### 15.1. OIDC Authorization Code Flow

Một luồng điển hình:

1. Ứng dụng tạo transaction và lưu state, nonce, PKCE verifier cùng thời hạn ngắn.
2. Browser được chuyển đến authorization endpoint.
3. IdP xác thực người dùng và trả authorization code về redirect URI đã đăng ký.
4. Ứng dụng kiểm tra state, đổi code bằng PKCE verifier.
5. Ứng dụng xác minh ID token: chữ ký, issuer, audience, thời hạn, nonce và claim cần thiết.
6. Ứng dụng tạo session ID mới, lưu subject và auth context.
7. Transaction được đánh dấu đã dùng và xóa.

State chống CSRF/ràng buộc response với transaction; nonce ràng buộc ID token với yêu cầu xác thực; PKCE bảo vệ authorization code. Chúng không thay thế session ID và không được dùng lại vô hạn.

### 15.2. Ánh xạ thời điểm và mức bảo đảm

Ứng dụng cần xác định claim nào cho biết thời điểm xác thực, phương thức và mức bảo đảm. Không suy diễn rằng mọi ID token đều chứng minh MFA hoặc phishing resistance. Nếu IdP không cung cấp bằng chứng đủ tin cậy, ứng dụng phải áp dụng chính sách thận trọng và step-up tại nơi cần.

### 15.3. SAML và callback

SAML assertion có thể được gửi qua browser POST binding. Cần xác minh chữ ký, issuer, audience, recipient, destination, thời hạn, InResponseTo và trạng thái replay theo cấu hình giao thức. Sau khi assertion hợp lệ, tạo session mới của ứng dụng và đánh dấu request/response đã dùng.

Không lưu nguyên assertion lâu hơn cần thiết hoặc ghi assertion vào log. Cookie transaction có thể cần cấu hình SameSite riêng cho callback cross-site; kiểm thử đúng browser và binding đang sử dụng.

### 15.4. Session của IdP và session ứng dụng

Session của IdP và session của ứng dụng là hai trạng thái riêng. Người dùng có thể logout khỏi ứng dụng nhưng vẫn còn session tại IdP, nên lần truy cập sau có thể đăng nhập lại mà không hỏi credential. Nếu nghiệp vụ yêu cầu logout toàn cục, cần triển khai giao thức logout phù hợp và xử lý trường hợp callback thất bại.

## 16. Khôi phục tài khoản và thay đổi credential

Session hiện tại cần được xem xét khi có sự kiện account recovery hoặc thay đổi credential. Nếu người dùng mất thiết bị MFA, quy trình recovery có thể thay đổi mức tin cậy của tài khoản.

Sau recovery thành công, chính sách có thể yêu cầu:

- Thu hồi session trên thiết bị bị mất.
- Thu hồi refresh token và authenticator cũ.
- Tăng security epoch để kết thúc các phiên cũ.
- Yêu cầu đăng nhập lại bằng yếu tố mới.
- Giới hạn tạm thời một số thao tác nhạy cảm.
- Thông báo cho kênh liên hệ đã xác minh.
- Ghi audit event với bằng chứng và người phê duyệt.

Đổi mật khẩu không nhất thiết luôn phải kết thúc mọi phiên trong mọi sản phẩm, nhưng quyết định phải rõ ràng. Với sự cố nghi ngờ chiếm tài khoản hoặc reset mật khẩu do hỗ trợ, thu hồi toàn bộ session thường là lựa chọn an toàn hơn.

## 17. Ví dụ cấu hình cookie và session phía máy chủ

Ví dụ dưới đây minh họa các thuộc tính bảo mật cần có. Tên property và API cụ thể phụ thuộc framework và phiên bản.

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: "__Host-session"
        secure: true
        http-only: true
        same-site: "lax"
        path: "/"
      timeout: 30m
~~~

Cấu hình này chỉ minh họa cookie và timeout idle phía framework. Ứng dụng vẫn cần absolute timeout, session store, CSRF defense, rotation khi đăng nhập và thu hồi phía máy chủ.

### 17.1. Pseudocode cho đăng nhập và luân chuyển session

~~~java
LoginResult authenticate(LoginRequest request) {
    AuthenticationResult auth = authenticator.verify(request);

    if (!auth.isSuccessful()) {
        audit.record("login_failed", auth.safeContext());
        throw new AuthenticationException();
    }

    // Không tái sử dụng session ID trước đăng nhập.
    sessionStore.revoke(request.preAuthSessionId());

    String newSessionId = secureRandomSessionId();
    SessionRecord session = new SessionRecord(
        newSessionId,
        auth.subjectId(),
        auth.authenticatedAt(),
        auth.methods(),
        auth.assuranceLevel(),
        idleExpiry(),
        absoluteExpiry(),
        "ACTIVE"
    );

    sessionStore.create(session);
    audit.record("login_succeeded", session.safeAuditContext());

    return LoginResult.withCookie(newSessionId);
}
~~~

Đây là pseudocode mô tả luồng, không phải API framework có thể biên dịch nguyên trạng. secureRandomSessionId() phải dùng CSPRNG; safeAuditContext() không được chứa session ID hoặc secret. Tạo session mới và vô hiệu hóa session trước đó cần được thực hiện an toàn trước khi gửi cookie.

### 17.2. Pseudocode cho xác minh mỗi request

~~~java
SessionContext resolveSession(String presentedSessionId) {
    if (presentedSessionId == null || presentedSessionId.isBlank()) {
        throw new UnauthenticatedException();
    }

    SessionRecord session = sessionStore.findByPresentedId(presentedSessionId);

    if (session == null || !session.isActive()) {
        throw new UnauthenticatedException();
    }

    Instant now = clock.instant();

    if (!now.isBefore(session.idleExpiresAt())
            || !now.isBefore(session.absoluteExpiresAt())) {
        sessionStore.expireIfCurrent(session.id(), session.version());
        throw new UnauthenticatedException();
    }

    if (!accountState.isEnabled(session.subjectId())
            || !sessionVersion.isCurrent(session)) {
        sessionStore.revokeIfCurrent(session.id(), session.version());
        throw new UnauthenticatedException();
    }

    return SessionContext.from(session);
}
~~~

Trong triển khai thực, cần kiểm soát truy vấn đồng thời, trạng thái thu hồi, clock, lỗi session store và cập nhật idle timeout. Không được coi lỗi đọc trạng thái session là bằng chứng session hợp lệ.

### 17.3. Pseudocode cho logout

~~~java
void logout(String presentedSessionId, CsrfContext csrf) {
    csrf.requireValid();

    SessionRecord session = sessionStore.findByPresentedId(presentedSessionId);

    if (session != null) {
        sessionStore.revokeIfCurrent(session.id(), session.version());
        refreshTokenStore.revokeFamily(session.refreshTokenFamilyId());
        audit.record("logout", session.safeAuditContext());
    }

    response.clearCookie("__Host-session", "/", true, true);
}
~~~

Logout phải xử lý cả trường hợp session đã hết hạn hoặc không tìm thấy. Việc xóa cookie cần dùng đúng tên và thuộc tính path/domain đã phát hành. Pseudocode cần được điều chỉnh theo framework, giao thức CSRF và cách quản lý refresh token thực tế.

## 18. Kế hoạch kiểm thử end-to-end

Một bài kiểm thử session cần bao gồm cả luồng thành công, luồng từ chối, sự kiện bảo mật và tương tác giữa nhiều request.

| Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|
| Đăng nhập | Credential hợp lệ và MFA đúng | Tạo session mới và cookie bảo mật |
| Đăng nhập | Mật khẩu đúng nhưng MFA sai | Không tạo session authenticated |
| Fixation | Client gửi session ID trước đăng nhập | ID được thay thế sau xác thực |
| Session ID | ID thiếu, sai định dạng hoặc không tồn tại | Bị từ chối, không tiết lộ thông tin |
| Cookie | HTTP hoặc cookie thiếu Secure ở production | Không phát hành session cookie không an toàn |
| CSRF | Request thay đổi trạng thái thiếu token | Bị từ chối |
| CSRF | Origin không được phép | Bị từ chối theo policy |
| XSS/logging | Request chứa dữ liệu nhạy cảm và gây lỗi | Không ghi session ID hoặc token vào log |
| Idle timeout | Không có hoạt động hợp lệ quá thời hạn | Session hết hạn |
| Absolute timeout | Người dùng hoạt động liên tục vượt tuổi thọ tối đa | Yêu cầu xác thực lại |
| Step-up | Hành động đặc quyền với auth_time quá cũ | Yêu cầu xác thực bổ sung |
| Logout | Logout rồi phát lại cookie cũ | Session bị từ chối |
| Thu hồi | Quản trị viên khóa tài khoản | Các session liên quan bị thu hồi theo SLA |
| Đa thiết bị | Thu hồi một thiết bị | Session của thiết bị đó bị từ chối; phiên khác theo policy |
| Refresh | Hai request dùng cùng refresh token đồng thời | Chỉ một lần tiêu thụ hợp lệ; reuse được phát hiện |
| Phân tán | Thu hồi tại một instance, request đến instance khác | Trạng thái thu hồi lan truyền trong giới hạn |
| Race | Request cũ ghi lại session sau logout | Session không được hồi sinh |
| Recovery | Người dùng reset credential | Session và authenticator cũ được xử lý theo policy |
| SSO | Callback OIDC/SAML có state hoặc nonce sai | Không tạo session |
| Backup | Restore session store cũ | Session đã thu hồi không được kích hoạt lại |

### 18.1. Kiểm thử nhiều request đồng thời

Dùng test harness để gửi đồng thời các thao tác refresh, logout, cập nhật last_seen và request nghiệp vụ. Xác minh trạng thái cuối không phụ thuộc vào thứ tự hoàn thành của thread.

Các invariant quan trọng:

- Session revoked không thể trở lại active.
- Refresh token đã tiêu thụ không thể được sử dụng lần thứ hai.
- Absolute expiry không được kéo dài bởi request đến trễ.
- Logout được phản ánh ở mọi điểm xác minh trong SLA.
- Một session ID cũ không được chấp nhận sau rotation.
- Một transaction OIDC/SAML không được dùng lại.

### 18.2. Kiểm thử browser thực tế

Cookie behavior có thể khác nhau theo browser, phiên bản và ngữ cảnh điều hướng. Kiểm tra:

- HTTPS và redirect.
- SameSite trong luồng login thông thường.
- Callback OIDC/SAML qua redirect hoặc POST.
- Cookie host-only và subdomain.
- Xóa cookie khi logout.
- Tab mở lâu, browser restart và session expiry.
- Browser back/forward cache và dữ liệu nhạy cảm trong response.
- Nhiều tab cùng refresh hoặc logout.

Không chỉ kiểm thử bằng HTTP client đơn giản vì client đó có thể không mô phỏng chính sách cookie của browser.

## 19. Các lỗi thiết kế thường gặp

**Giữ nguyên session ID sau đăng nhập.** Điều này mở đường cho session fixation. Luân chuyển ID khi chuyển trạng thái tin cậy.

**Chỉ xóa cookie khi logout.** Bản sao cookie bị đánh cắp vẫn có thể dùng được nếu server chưa thu hồi session.

**Chỉ dùng idle timeout.** Phiên hoạt động liên tục có thể tồn tại quá lâu. Cần absolute timeout.

**Chỉ dùng absolute timeout.** Người dùng có thể bỏ quên một phiên không hoạt động trong thời gian dài. Cần idle timeout phù hợp.

**Dùng SameSite thay cho mọi CSRF defense.** Một số luồng cần cross-site cookie và browser có hành vi khác nhau. Dùng CSRF token, kiểm tra origin và thiết kế cookie theo transaction.

**Cho rằng HttpOnly ngăn được XSS.** HttpOnly hạn chế đọc cookie; script độc hại vẫn có thể thực hiện request trong origin. Cần chống XSS.

**Lưu access token trong localStorage mà không đánh giá XSS.** Script cùng origin có thể đọc dữ liệu. Cân nhắc BFF hoặc cơ chế lưu trữ phù hợp với client.

**Dùng JWT dài hạn để tránh session store.** Token khó thu hồi tức thời và claim có thể cũ. Giới hạn lifetime, scope và bổ sung cơ chế thu hồi khi cần.

**Cache trạng thái active quá lâu.** Phiên bị thu hồi có thể tiếp tục được chấp nhận ở instance khác. Đặt SLA invalidation và kiểm tra trạng thái có thẩm quyền cho hành động nhạy cảm.

**Dùng IP hoặc User-Agent làm khóa phiên.** Các giá trị này thay đổi và dễ giả mạo. Chúng chỉ là tín hiệu rủi ro bổ sung.

**Không xử lý race condition.** Refresh hoặc request cũ có thể hồi sinh trạng thái đã thu hồi. Dùng transaction, version và update có điều kiện.

**Đồng nhất logout ứng dụng với logout IdP.** SSO có nhiều session độc lập. Cần định nghĩa phạm vi và triển khai giao thức logout phù hợp.

## 20. Checklist thiết kế session

Trước khi đưa một luồng xác thực vào vận hành, hãy xác nhận:

- [ ] Đã chọn mô hình opaque session, token tự chứa hoặc kiến trúc kết hợp và ghi rõ lý do.
- [ ] Session ID được sinh bằng CSPRNG, có entropy đủ lớn, không mang thông tin nhận dạng và không xuất hiện trong log.
- [ ] Session chỉ được tạo sau khi xác thực đầy đủ; ID được luân chuyển khi đăng nhập và thay đổi mức tin cậy.
- [ ] Cookie session có Secure, HttpOnly, SameSite phù hợp, Path và Domain tối thiểu.
- [ ] Có CSRF defense cho mọi request thay đổi trạng thái dùng cookie.
- [ ] Có biện pháp chống XSS và không dựa vào HttpOnly như biện pháp duy nhất.
- [ ] Có idle timeout, absolute timeout và quy tắc reauthentication/step-up.
- [ ] Logout thu hồi trạng thái server-side và xóa cookie đúng thuộc tính.
- [ ] Có chính sách session riêng theo thiết bị và khả năng thu hồi một hoặc mọi phiên.
- [ ] Thay đổi mật khẩu, MFA, passkey, account recovery và khóa tài khoản có quy tắc thu hồi rõ ràng.
- [ ] Refresh token có rotation, reuse detection và xử lý request đồng thời.
- [ ] JWT có lifetime, audience, issuer, thuật toán và cơ chế thu hồi phù hợp.
- [ ] Session store có quyền tối thiểu, TTL, backup và khả năng khôi phục an toàn.
- [ ] Thu hồi lan truyền giữa các instance trong giới hạn đã cam kết.
- [ ] Có version/epoch hoặc cơ chế tương đương để tránh session stale hồi sinh.
- [ ] OIDC/SAML callback xác minh state, nonce, PKCE hoặc các ràng buộc giao thức tương ứng.
- [ ] Có kiểm thử browser, concurrency, failover, logout và recovery.
- [ ] Audit event ghi đủ thông tin điều tra mà không chứa session ID, token hoặc secret.

## 21. Kết luận

Thiết kế session là thiết kế vòng đời của quyền truy cập sau xác thực. Hệ thống phải biết phiên thuộc về ai, được tạo bằng phương thức nào, mức bảo đảm ra sao, còn hiệu lực đến khi nào và cách kết thúc phiên trên mọi điểm xác minh.

Một thiết kế vững chắc dùng session ID khó đoán, luân chuyển tại ranh giới tin cậy, bảo vệ cookie và chống CSRF/XSS, áp dụng idle cùng absolute timeout, yêu cầu step-up cho hành động nhạy cảm và thu hồi server-side. Khi chạy phân tán, cần xử lý cache stale, race condition và sự kiện thu hồi để session cũ không thể sống lại. Với SSO và token, phải phân biệt session ứng dụng, session IdP, access token và refresh token. Chỉ khi các thành phần này có trách nhiệm và vòng đời rõ ràng, hệ thống mới duy trì được trải nghiệm đăng nhập liên tục mà vẫn kiểm soát được danh tính và quyền truy cập.

