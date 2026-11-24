# Session cookie

**Session cookie** là cookie trình duyệt dùng để mang một định danh phiên (session identifier) hoặc một credential tham chiếu tới phiên đăng nhập. Trong mô hình phổ biến, cookie không chứa toàn bộ hồ sơ người dùng hay quyền truy cập; nó mang một giá trị ngẫu nhiên, khó đoán để máy chủ tra cứu trạng thái phiên được lưu ở phía server. Khi browser gửi cookie trong request, ứng dụng xác định phiên tương ứng, kiểm tra trạng thái và áp dụng chính sách xác thực/ủy quyền.

Cookie phiên tạo cầu nối giữa các HTTP request vốn độc lập. Tuy nhiên, vì browser tự động gửi cookie theo quy tắc domain, path và SameSite, session cookie cũng là một **bearer credential**: bất kỳ ai lấy được giá trị hợp lệ có thể có khả năng sử dụng phiên đó. Vì vậy, cần bảo vệ cookie trong truyền tải, lưu trữ, phạm vi gửi, vòng đời và xử lý ở server.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập. Trong phạm vi chương **Authentication trong web**, bài này tập trung vào session cookie và cách thiết kế nó an toàn.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt HTTP cookie, session cookie, session ID, server-side session và access token.
2. Mô tả cách browser nhận Set-Cookie, lưu cookie và gửi Cookie trong request tiếp theo.
3. Chọn đúng các thuộc tính Secure, HttpOnly, SameSite, Path, Domain, Max-Age và Expires.
4. Thiết kế session ID có entropy cao, không chứa dữ liệu định danh và được xoay vòng đúng thời điểm.
5. Phòng chống session fixation, session hijacking, cookie theft, CSRF, XSS và cookie tossing.
6. Thiết kế idle timeout, absolute timeout, logout một phiên và logout mọi phiên.
7. Hiểu khác biệt giữa cookie host-only và domain cookie, cũng như giới hạn bảo mật của Path.
8. Tổ chức session store, cache và cơ chế thu hồi phiên trong môi trường nhiều instance.
9. Giải thích tương tác giữa SameSite, SSO/OIDC và luồng xác thực cross-site.
10. Xây dựng checklist và bộ kiểm thử cho session cookie.

## 2. Phân biệt cookie, session và session cookie

Các khái niệm thường được dùng lẫn nhau nhưng không đồng nghĩa:

- **HTTP cookie:** cặp name/value do server đặt bằng header Set-Cookie; browser lưu và gửi lại trong các request phù hợp.
- **Session:** trạng thái tương tác của một người dùng với ứng dụng trong một khoảng thời gian. Trạng thái có thể chứa subject, thời điểm xác thực, mức assurance, quyền tạm thời, CSRF token và dữ liệu workflow.
- **Session ID:** định danh ngẫu nhiên, thường là một chuỗi opaque, dùng để tìm session trong kho lưu trữ.
- **Session cookie:** cookie browser dùng để mang session ID hoặc credential tham chiếu phiên. Theo thuật ngữ cookie, session cookie thường là cookie không có Expires/Max-Age; browser xem nó là cookie phiên browser. Trong thực tế, người ta cũng gọi cookie xác thực dạng persistent là “session cookie”, nên cần nói rõ đang dùng nghĩa nào.
- **Access token:** credential được phát hành để resource server chấp nhận request theo audience/scope/expiry. Nó không tự động là session cookie.
- **Refresh token:** credential dùng để xin access token mới tại authorization server; thường không nên đưa vào browser cookie trừ khi kiến trúc và biện pháp bảo vệ được thiết kế phù hợp.

Trong mô hình server-side session, browser chỉ giữ session ID. Server giữ trạng thái và có thể vô hiệu hóa session ngay bằng cách đánh dấu record revoked hoặc xóa record. Cookie không nên chứa mật khẩu, số điện thoại, email, role, dữ liệu cá nhân hay thông tin nhạy cảm chỉ vì những dữ liệu đó “đã được mã hóa” hoặc “đã được ký”.

### 2.1. Mô hình request

1. Người dùng đăng nhập thành công bằng password, MFA, passkey hoặc cơ chế xác thực được hỗ trợ.
2. Server tạo session mới và sinh session ID ngẫu nhiên.
3. Server trả header Set-Cookie để browser lưu cookie.
4. Browser gửi cookie tự động trong những request khớp chính sách cookie.
5. Server đọc session ID, tìm session, kiểm tra expiry, revoked state và các điều kiện bảo mật.
6. Server gắn principal đã xác thực vào request context rồi tiếp tục authorization.
7. Khi logout hoặc session hết hạn, server vô hiệu hóa session; browser nhận header xóa cookie.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant A as Web Application
    participant S as Session Store
    U->>B: Đăng nhập
    B->>A: POST /login với credential
    A->>A: Xác minh credential và MFA
    A->>S: Tạo session mới, sinh session ID
    S-->>A: Session đã lưu
    A-->>B: Set-Cookie: __Host-sid=...; Secure; HttpOnly; SameSite=Lax
    B->>A: GET /account + Cookie: __Host-sid=...
    A->>S: Tra cứu session ID
    S-->>A: Session active
    A->>A: Xác lập principal, kiểm tra quyền
    A-->>B: Trả tài nguyên được phép
    U->>B: Chọn logout
    B->>A: POST /logout + cookie + CSRF token
    A->>S: Revoke session
    A-->>B: Set-Cookie xóa __Host-sid
~~~

Cookie chỉ giúp browser mang credential giữa các request. Nó không tự chứng minh rằng người gửi là chủ tài khoản; server vẫn phải kiểm tra session state và authorization cho từng request.

## 3. Vòng đời cookie trong HTTP

### 3.1. Server đặt cookie

Server gửi một hoặc nhiều header Set-Cookie. Ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-sid=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Trong ví dụ này, __Host-sid là tên cookie; RANDOM_OPAQUE_VALUE là session ID ngẫu nhiên. Cookie không có Expires hay Max-Age, do đó browser thường xử lý nó như session cookie. Server vẫn phải đặt expiry cho session ở phía server; việc browser đóng cửa sổ hoặc kết thúc session không thay thế được timeout phía server.

### 3.2. Browser gửi cookie

Khi request khớp các quy tắc gửi cookie, browser gửi:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: __Host-sid=RANDOM_OPAQUE_VALUE
~~~

Browser không gửi lại các thuộc tính Secure, HttpOnly, SameSite, Path, Domain, Expires hay Max-Age trong header Cookie. Đây là metadata điều khiển hành vi lưu trữ/gửi cookie, không phải dữ liệu mà ứng dụng nhận lại như một phần của value.

Một request có thể mang nhiều cookie trong cùng header Cookie. Không được giả định một cookie duy nhất luôn tồn tại hoặc thứ tự cookie luôn cố định. Nếu có nhiều cookie cùng tên nhưng khác Path/Domain, parser và framework có thể chọn giá trị khác nhau; thiết kế nên tránh tên cookie trùng lặp trong các scope chồng lấn.

### 3.3. Cookie session và browser restart

Cookie không có Expires/Max-Age thường được browser xem là session cookie. Nhưng một số browser có thể khôi phục session sau restart hoặc restore tabs, nên không thể dùng “đóng browser” làm ranh giới bảo mật duy nhất. Quyết định phiên còn hiệu lực phải nằm ở server, dựa trên idle timeout, absolute timeout, trạng thái revoke và policy tài khoản.

## 4. Các thuộc tính bảo mật quan trọng

| Thuộc tính | Tác dụng | Khuyến nghị |
| --- | --- | --- |
| Secure | Browser chỉ gửi cookie qua kết nối bảo mật HTTPS (ngoại lệ phát triển tùy browser). | Bật cho cookie xác thực; triển khai HTTPS toàn bộ và HSTS. |
| HttpOnly | JavaScript không đọc cookie qua document.cookie. | Bật cho session cookie để giảm khả năng XSS lấy trực tiếp giá trị cookie. |
| SameSite | Kiểm soát việc gửi cookie trong ngữ cảnh same-site/cross-site. | Chọn Lax hoặc Strict theo luồng; dùng None; Secure chỉ khi thật sự cần cross-site. |
| Path | Giới hạn path request mà browser gửi cookie tới. | Thường dùng /; không xem Path như ranh giới bảo mật. |
| Domain | Mở rộng cookie tới host và subdomain phù hợp. | Bỏ qua thuộc tính này để có host-only cookie nếu không cần chia sẻ subdomain. |
| Max-Age | Thời gian sống tối đa tính bằng giây. | Dùng khi cần persistent cookie; server vẫn phải tự enforce session expiry. |
| Expires | Thời điểm hết hạn theo HTTP-date. | Có thể dùng tương thích; Max-Age thường được ưu tiên khi cả hai cùng có mặt. |

### 4.1. Secure

Secure ngăn browser gửi cookie trên kết nối HTTP thông thường. Nếu một phần ứng dụng vẫn chấp nhận HTTP, cookie có thể bị lộ qua mạng khi thiếu Secure hoặc khi có lỗi cấu hình. Dùng HTTPS cho toàn bộ ứng dụng, redirect HTTP sang HTTPS và cấu hình HSTS để giảm nguy cơ downgrade.

Secure không mã hóa cookie ở nơi khác: cookie vẫn cần được bảo vệ trong log, browser profile, extension, backup và kho session phía server.

### 4.2. HttpOnly

HttpOnly ngăn JavaScript truy cập trực tiếp giá trị cookie qua document.cookie. Điều này làm giảm một đường exfiltration khi có XSS. Tuy nhiên, HttpOnly **không ngăn script độc hại gửi request thay mặt người dùng**: browser vẫn tự gắn cookie vào request cùng origin phù hợp. Vì vậy, HttpOnly không thay thế phòng chống XSS, CSRF token, kiểm soát quyền hoặc kiểm tra hành động nhạy cảm.

### 4.3. SameSite

SameSite giúp giảm CSRF bằng cách hạn chế cookie được gửi trong request cross-site:

- **Strict:** chỉ gửi trong ngữ cảnh same-site theo quy tắc browser. Bảo vệ chặt hơn nhưng có thể làm mất session khi người dùng đi từ liên kết bên ngoài vào ứng dụng.
- **Lax:** cho phép một số điều hướng top-level an toàn từ site khác, thường phù hợp với cookie đăng nhập web thông thường. Đây là lựa chọn thực tế phổ biến, nhưng không thay thế CSRF token.
- **None:** cho phép gửi trong ngữ cảnh cross-site; browser yêu cầu Secure. Chỉ dùng khi flow thật sự cần, ví dụ một số mô hình nhúng hoặc liên kết đăng nhập cross-site.

Same-site không đồng nghĩa same-origin. Hai subdomain có thể khác origin nhưng cùng site theo cách browser xác định. Điều này quan trọng khi ứng dụng dùng nhiều subdomain. Đừng coi SameSite là biện pháp duy nhất nếu các subdomain có mức tin cậy khác nhau.

### 4.4. Domain và host-only cookie

Nếu bỏ thuộc tính Domain, cookie thường là host-only: chỉ host đã đặt cookie nhận lại cookie đó. Nếu đặt Domain=example.test, cookie có thể được gửi tới các subdomain phù hợp như app.example.test và admin.example.test.

Chia sẻ cookie tới toàn bộ subdomain làm tăng phạm vi tin cậy. Một subdomain bị chiếm quyền, cấu hình sai hoặc chạy ứng dụng kém tin cậy có thể làm tăng nguy cơ cookie injection, cookie tossing hoặc lạm dụng cookie scope. Với session cookie nhạy cảm, ưu tiên host-only cookie trừ khi có yêu cầu kiến trúc cụ thể.

Dấu chấm đầu trong Domain=.example.test không còn tạo khác biệt chuẩn hóa như cách hiểu cũ; browser hiện đại xử lý theo quy tắc domain cookie. Cần tham khảo chuẩn/browser mục tiêu thay vì dựa vào dấu chấm để tạo cô lập.

### 4.5. Path không phải ranh giới bảo mật

Path=/admin chỉ là quy tắc browser chọn request path để gửi cookie. Nó không thay thế authorization ở server, không bảo vệ cookie trước script có cùng origin và không nên dùng để cô lập hai ứng dụng nhạy cảm. Nếu cần cô lập, dùng host riêng, origin riêng, cookie name riêng và chính sách server-side rõ ràng.

### 4.6. Prefix __Host- và __Secure-

Browser hỗ trợ cookie prefix có thể áp dụng thêm ràng buộc khi nhận cookie:

- Cookie bắt đầu bằng __Secure- phải được đặt trong secure context và có thuộc tính Secure.
- Cookie bắt đầu bằng __Host- phải có Secure, Path=/ và không được có Domain; nhờ đó cookie được giới hạn cho host đặt nó.

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-sid=RANDOM_OPAQUE_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Với prefix __Host-, không thêm Domain=example.test. Prefix là lớp bảo vệ bổ sung do browser thực thi, không thay thế xác minh server-side hay kiểm tra hỗ trợ browser.

## 5. Thiết kế session ID

Session ID là một bearer secret. Ai sở hữu giá trị session ID còn hiệu lực có thể thử sử dụng phiên đó. Do vậy, ID cần khó đoán, không có ý nghĩa nghiệp vụ và không tiết lộ dữ liệu.

### 5.1. Yêu cầu

- Sinh bằng cryptographically secure random number generator (CSPRNG), không dùng timestamp, counter, UUID cấu hình yếu hoặc PRNG thông thường.
- Có entropy cao; mục tiêu thực tế là ít nhất 128 bit ngẫu nhiên, có thể dùng 256 bit để có biên an toàn rộng.
- Được mã hóa biểu diễn bằng chuỗi URL-safe/Base64url hoặc định dạng phù hợp.
- Không chứa username, email, role, tenant, thời điểm đăng nhập hoặc dữ liệu cá nhân.
- Không tái sử dụng ID giữa người dùng, môi trường hoặc session khác nhau.
- Không ghi raw ID vào application log, analytics, URL, referrer hoặc crash report.
- Có expiry và trạng thái server-side rõ ràng.

Ví dụ minh họa: sinh 32 byte ngẫu nhiên từ CSPRNG rồi mã hóa Base64url không padding. Đây là ví dụ biểu diễn; thư viện/framework session đã được kiểm chứng thường an toàn hơn tự viết thuật toán.

### 5.2. Lưu fingerprint thay vì raw session ID

Trong server-side session store, có thể lưu hash/fingerprint của session ID thay vì lưu raw value. Khi browser gửi ID, server tính fingerprint rồi tra cứu record. Vì ID có entropy cao, hash an toàn phù hợp để tránh lưu raw bearer secret trực tiếp trong database. Nếu dùng keyed HMAC, cần quản lý và xoay khóa đúng cách.

Session record có thể chứa:

| Trường | Mục đích |
| --- | --- |
| session_id_hash | Fingerprint để tìm session. |
| subject_id | Tài khoản đã xác thực. |
| created_at | Thời điểm tạo phiên. |
| last_seen_at | Thời điểm hoạt động gần nhất. |
| absolute_expires_at | Hạn cuối không được vượt qua. |
| revoked_at | Thời điểm bị thu hồi, nếu có. |
| auth_time | Thời điểm xác thực gần nhất. |
| assurance_level | Mức assurance đã đạt nếu hệ thống dùng. |
| csrf_secret | Secret dùng tạo/kiểm tra CSRF token nếu triển khai synchronizer pattern. |
| device_label | Nhãn hiển thị đã chuẩn hóa; không phải bằng chứng định danh thiết bị. |

Chỉ lưu dữ liệu cần thiết. Role, trạng thái tài khoản, quyền quản trị hoặc membership có thể thay đổi; không nên dựa mãi vào một bản sao cũ trong session nếu hành động yêu cầu quyền mới nhất. Cân nhắc tra cứu hoặc version hóa quyền đối với thao tác nhạy cảm.

## 6. Tạo, xoay vòng và hủy session

### 6.1. Tạo session sau xác thực

Sau khi xác minh credential thành công, server tạo session mới và gửi cookie. Không chấp nhận session ID do client tự chọn hoặc do người dùng gửi qua query parameter. Không nâng cấp một session ID tiền xác thực thành session đã đăng nhập mà không xoay vòng.

Ví dụ: browser có session ẩn danh để lưu giỏ hàng. Sau khi người dùng đăng nhập, server phải sinh session ID mới, gắn trạng thái đăng nhập với ID mới và hủy/đánh dấu không hợp lệ ID cũ. Nếu giữ nguyên ID, attacker có thể chuẩn bị một ID mà nạn nhân vô tình sử dụng rồi chờ ID đó được nâng lên thành session đã xác thực — đây là session fixation.

### 6.2. Khi nào cần xoay session ID?

Xoay ID sau các thay đổi ranh giới tin cậy quan trọng:

- Đăng nhập thành công.
- Hoàn tất MFA hoặc step-up authentication.
- Thay đổi quyền hoặc nâng role.
- Thay đổi mật khẩu, passkey hoặc credential quan trọng.
- Khôi phục tài khoản.
- Thay đổi mức assurance hoặc thực hiện hành động quản trị có rủi ro cao.

Xoay vòng phải được thực hiện an toàn: tạo ID mới, cập nhật record và hủy ID cũ theo một thao tác nguyên tử hoặc giao thức nhất quán. Tránh khoảng thời gian mà cả ID cũ lẫn ID mới đều có quyền cao không cần thiết. Nếu phải hỗ trợ chuyển tiếp request đang chạy, quy định thời gian overlap rất ngắn và kiểm thử replay.

### 6.3. Hủy session

Logout cần làm hai việc phối hợp:

1. **Server-side:** đánh dấu session revoked hoặc xóa record; request tiếp theo mang cookie cũ phải bị từ chối.
2. **Browser-side:** gửi Set-Cookie để xóa cookie với cùng tên và scope phù hợp.

Ví dụ:

~~~http
Set-Cookie: __Host-sid=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Để xóa cookie thông thường, name/path/domain phải khớp với cookie đã đặt. Với __Host-sid, không có Domain. Chỉ xóa cookie ở browser là chưa đủ: attacker có bản sao cookie vẫn có thể dùng session nếu server chưa revoke.

## 7. Session timeout và quản lý vòng đời

Session cần có ít nhất hai giới hạn thời gian:

- **Idle timeout:** hết hạn sau một khoảng không có hoạt động hợp lệ.
- **Absolute timeout:** hết hạn sau tổng thời gian tối đa kể từ lúc tạo hoặc xác thực, bất kể người dùng có hoạt động liên tục hay không.

Ví dụ minh họa: phiên thông thường có idle timeout 30 phút và absolute timeout 12 giờ; phiên quản trị hoặc thao tác rủi ro cao có thể ngắn hơn. Đây chỉ là giá trị ví dụ, không phải con số bắt buộc cho mọi hệ thống. Chọn theo threat model, loại dữ liệu, môi trường, UX và yêu cầu compliance.

Rolling expiry có thể cập nhật last_seen_at hoặc idle deadline sau hoạt động hợp lệ, nhưng không được vượt qua absolute timeout. Tránh gia hạn session chỉ vì request nền, prefetch hoặc polling không chứng minh người dùng còn hiện diện.

Server phải kiểm tra expiry ở mỗi request phù hợp. Browser session cookie biến mất khi browser đóng không phải cơ chế timeout đáng tin cậy; browser có thể restore session, và attacker có thể đã sao chép cookie trước đó.

### 7.1. Mức rủi ro và re-authentication

Không phải mọi thao tác đều cần cùng một thời gian xác thực. Ví dụ:

- Xem nội dung khóa học: có thể chấp nhận session thông thường.
- Đổi email recovery hoặc mật khẩu: yêu cầu re-authentication hoặc step-up.
- Cấp role, xuất dữ liệu nhạy cảm, sửa điểm: yêu cầu assurance cao hơn và có thể yêu cầu xác thực lại gần thời điểm hành động.
- Thay đổi passkey/MFA hoặc recovery factor: yêu cầu xác minh credential hiện có và thông báo qua kênh đã xác minh.

Không coi cookie đang tồn tại là bằng chứng người dùng vừa xác thực. Lưu auth_time/assurance và kiểm tra độ mới của xác thực khi hành động yêu cầu.

## 8. CSRF và session cookie

Cross-Site Request Forgery (CSRF) xảy ra khi browser gửi request có credential tự động — ví dụ session cookie — tới ứng dụng mà người dùng không chủ ý thực hiện hành động đó. Attacker không cần đọc được response; chỉ cần khiến browser gửi request thay mặt nạn nhân.

### 8.1. Các lớp phòng vệ

- Dùng SameSite=Lax hoặc Strict phù hợp với luồng; đây là defense in depth, không phải biện pháp duy nhất.
- Dùng CSRF token cho thao tác thay đổi trạng thái. Synchronizer token nên gắn với session và không thể đoán.
- Kiểm tra Origin và, khi phù hợp, Referer đối với request thay đổi trạng thái.
- Không thực hiện thay đổi trạng thái qua GET/HEAD. GET phải an toàn và không gây side effect.
- Kiểm soát CORS theo origin cụ thể nếu có cross-origin API; không dùng Access-Control-Allow-Origin: * cùng credential.
- Với hành động nhạy cảm, xác minh ý định và yêu cầu re-authentication/step-up khi cần.

### 8.2. Synchronizer token pattern

Server sinh CSRF token gắn với session, đưa token tới trang/form an toàn và yêu cầu client gửi lại qua hidden field hoặc custom header. Server so sánh token với giá trị đã gắn session. Không đặt CSRF token trong URL vì URL có thể đi vào history, log hoặc Referer.

Ví dụ request:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.test
Cookie: __Host-sid=RANDOM_OPAQUE_VALUE
Content-Type: application/json
X-CSRF-Token: UNPREDICTABLE_SESSION_BOUND_TOKEN

{"email":"new-address@example.test"}
~~~

CSRF token không phải session ID và không thay thế xác thực. Với double-submit cookie pattern, cần bảo vệ chống cookie injection và ràng buộc token bằng chữ ký/session context; không chỉ so sánh hai giá trị do attacker có thể kiểm soát.

### 8.3. SameSite không thay thế CSRF token

Một số luồng cross-site hoặc subdomain có thể vẫn được xem là same-site. Browser có thể thay đổi hành vi mặc định qua phiên bản hoặc policy. Vì vậy, với thao tác nhạy cảm, nên kết hợp SameSite, CSRF token, kiểm tra Origin và authorization. CORS chỉ quyết định browser có cho JavaScript đọc response cross-origin hay không; nó không phải cơ chế chống CSRF tổng quát.

## 9. XSS, session hijacking và cookie theft

### 9.1. XSS

Nếu ứng dụng có XSS, attacker có thể chạy script trong origin tin cậy. HttpOnly ngăn script đọc trực tiếp session cookie, nhưng script vẫn có thể gọi API cùng origin và browser tự gửi cookie. Vì vậy, cần phòng chống XSS bằng output encoding theo context, sanitization có kiểm soát, Content Security Policy (CSP), dependency hygiene và tránh DOM injection nguy hiểm.

Không đưa session ID vào HTML, JavaScript global, URL, localStorage hay sessionStorage chỉ để ứng dụng dễ truy cập. Với web app, cookie HttpOnly kết hợp server-side session/BFF thường giảm việc token xác thực bị JavaScript đọc trực tiếp.

### 9.2. Session hijacking / replay

Nếu attacker lấy được session cookie qua malware, extension độc hại, log, máy dùng chung hoặc lỗi TLS, họ có thể replay cookie từ thiết bị khác. Biện pháp giảm thiểu gồm:

- HTTPS, HSTS, Secure, HttpOnly và cookie scope hẹp.
- Session ID đủ entropy và không xuất hiện trong URL/log.
- Idle/absolute timeout, rotate sau authentication/step-up và revoke nhanh.
- Phát hiện bất thường dựa trên tín hiệu phù hợp và step-up khi cần.
- Quản lý session đa thiết bị, cho phép người dùng xem/thu hồi phiên.
- Không dùng IP hoặc User-Agent làm bằng chứng mạnh duy nhất; chúng có thể thay đổi, dùng chung hoặc bị giả mạo.
- Giới hạn quyền của session theo tenant, scope và policy hiện hành.

Ràng buộc session cứng theo IP có thể gây false positive khi người dùng chuyển mạng hoặc dùng carrier NAT. Nếu dùng device/risk signal, hãy dùng như tín hiệu đánh giá rủi ro, không thay thế credential hoặc authorization.

### 9.3. Session fixation

Attacker cố định trước session ID mà nạn nhân sau đó sử dụng. Khi nạn nhân đăng nhập, ID đó được nâng thành session authenticated. Phòng vệ: chỉ chấp nhận ID do server sinh, xoay ID sau đăng nhập/MFA/step-up và hủy ID trước xác thực. Không nhận session ID từ URL hoặc tham số do người dùng kiểm soát.

### 9.4. Cookie tossing và subdomain compromise

Nếu cookie được đặt cho domain rộng, subdomain không đáng tin có thể đặt cookie cùng tên hoặc tạo tình huống parser nhận nhiều cookie trùng tên. Điều này có thể gây session confusion hoặc cookie tossing. Dùng host-only cookie, prefix __Host-, tên cookie riêng, tránh Domain rộng và kiểm tra cách framework parse cookie trùng tên. Không cho subdomain không cần thiết có quyền đặt cookie xác thực cho parent domain.

## 10. Session store và kiến trúc triển khai

Với server-side session, record có thể được lưu trong database, Redis hoặc một kho session chuyên dụng. Trong môi trường nhiều instance, mọi instance phải nhìn thấy trạng thái session nhất quán đủ cho SLA bảo mật.

### 10.1. Yêu cầu đối với session store

- Bảo vệ truy cập bằng network isolation, authentication, least privilege và encryption at rest khi phù hợp.
- Đặt TTL tương ứng với expiry; nhưng vẫn kiểm tra absolute_expires_at và revoked state.
- Hỗ trợ revoke theo session, user, device, grant hoặc toàn bộ tài khoản.
- Có cơ chế invalidation cache khi session bị revoke hoặc quyền thay đổi.
- Chống race giữa refresh, logout, session rotation và concurrent requests.
- Có backup/retention phù hợp; không giữ session record lâu hơn cần thiết.
- Không log raw session ID hoặc token.
- Phân tách môi trường dev/staging/prod và namespace session rõ ràng.

Sticky session ở load balancer có thể làm triển khai dễ hơn nhưng không giải quyết được mọi vấn đề: request có thể chuyển instance sau failover, logout cần tác động đúng instance và scaling làm thay đổi topology. Session store dùng chung thường dễ quản lý hơn; cần thiết kế availability và consistency phù hợp.

### 10.2. Cookie-based stateless session

Một số framework lưu dữ liệu session trong cookie được ký hoặc mã hóa thay vì lưu record đầy đủ phía server. Chữ ký bảo vệ tính toàn vẹn; encryption có thể bảo vệ nội dung. Tuy nhiên:

- Cookie vẫn là bearer credential và có thể bị replay.
- Giới hạn kích thước cookie và browser có thể làm dữ liệu lớn gây lỗi.
- Thu hồi tức thì khó hơn nếu server không giữ trạng thái; thường cần expiry ngắn, version check hoặc denylist.
- Xoay khóa, key separation, key rotation và chống downgrade cần được thiết kế.
- Không nhét dữ liệu nhạy cảm hoặc quyền dài hạn vào cookie chỉ vì nó đã được ký/mã hóa.

Với quyền quản trị hoặc dữ liệu nhạy cảm, server-side session thường giúp thu hồi và audit rõ ràng hơn.

### 10.3. Session cookie và BFF

Trong Backend-for-Frontend (BFF), browser chỉ giữ session cookie HttpOnly; BFF giữ OAuth access/refresh token ở phía server. Browser gọi BFF bằng cookie; BFF gọi API bằng access token. Mô hình này giảm việc token OAuth xuất hiện trong JavaScript, nhưng không loại bỏ CSRF/XSS: XSS vẫn có thể gọi BFF trong browser, và cookie vẫn cần CSRF protection.

## 11. SSO, OIDC và SameSite

Đăng nhập SSO có thể điều hướng browser giữa relying party (RP) và OpenID Provider (OP). Một số luồng phụ thuộc cookie của OP hoặc cookie liên kết transaction trong ngữ cảnh cross-site. Nếu cookie có SameSite=Strict hoặc Lax, browser có thể không gửi nó trong một số request cross-site; điều này có thể ảnh hưởng callback hoặc embedded flow tùy response mode và browser.

Một số integration cần cookie SameSite=None; Secure, nhưng chỉ dùng khi thật sự cần và phải hiểu tác động của third-party cookie blocking. Browser có thể chặn hoặc partition third-party cookies; đừng thiết kế xác thực dựa trên giả định cookie bên thứ ba luôn sẵn có.

Ưu tiên authorization code flow với PKCE, kiểm tra state, nonce, issuer và redirect URI theo OIDC/OAuth policy. Cookie transaction/nonce phải có scope, lifetime ngắn và gắn với browser transaction. Nếu cần tương thích với browser privacy controls, ưu tiên top-level redirect và mô hình same-site/BFF phù hợp hơn là nới lỏng cookie toàn cục.

## 12. Logout, thu hồi và logout đa thiết bị

Logout phải làm session cookie cũ không còn được chấp nhận ở server. Xóa cookie browser giúp browser ngừng gửi credential trong các request tiếp theo, nhưng bản sao cookie đã bị đánh cắp vẫn có thể được dùng nếu server chưa revoke session.

Các phạm vi cần phân biệt:

- **Logout tab/browser hiện tại:** xóa cookie và revoke session hiện tại.
- **Logout thiết bị hiện tại:** revoke tất cả session liên quan thiết bị đó theo cách ứng dụng định nghĩa.
- **Logout mọi thiết bị:** revoke toàn bộ session của tài khoản.
- **Logout SSO:** phối hợp với OP/RP theo giao thức OIDC; không đồng nghĩa chỉ xóa cookie local.
- **Password reset/credential compromise:** có thể yêu cầu revoke toàn bộ session và refresh token family.

Không nói “đã đăng xuất khỏi mọi nơi” nếu ứng dụng chỉ xóa cookie ở host hiện tại. Với hệ thống nhiều subdomain, service và IdP, cần xác định rõ ranh giới logout.

## 13. Ví dụ cấu hình và pseudocode

### 13.1. Header khuyến nghị cho session cookie thông thường

~~~http
Set-Cookie: __Host-sid=BASE64URL_RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Đây là cấu hình minh họa cho ứng dụng HTTPS trên host riêng. Chỉ bật includeSubDomains khi toàn bộ subdomain được vận hành qua HTTPS và đã đánh giá ảnh hưởng. SameSite=Lax có thể cần điều chỉnh theo luồng SSO; không thay đổi thành None chỉ để “làm cho login chạy” mà không đánh giá rủi ro cross-site.

### 13.2. Pseudocode tạo session

~~~text
onSuccessfulAuthentication(user, authContext):
    oldSession = findPreAuthSessionFromRequest()

    newId = CSPRNG(32 bytes)
    newSession = {
        idFingerprint: hash(newId),
        subjectId: user.id,
        createdAt: now(),
        lastSeenAt: now(),
        absoluteExpiresAt: now() + policy.absoluteLifetime,
        authTime: authContext.authTime,
        assuranceLevel: authContext.assuranceLevel,
        revokedAt: null
    }

    atomically:
        save(newSession)
        revoke(oldSession) if oldSession exists

    setCookie(
        name="__Host-sid",
        value=base64url(newId),
        path="/",
        secure=true,
        httpOnly=true,
        sameSite="Lax"
    )
~~~

Pseudocode chỉ thể hiện logic. Cần dùng session middleware/framework đã được kiểm chứng, cookie serializer an toàn và thao tác store nguyên tử. Không tự viết CSPRNG hoặc cookie parser.

### 13.3. Pseudocode xác thực request

~~~text
authenticateRequest(request):
    rawId = readCookie(request, "__Host-sid")
    if rawId is missing:
        rejectUnauthenticated()

    fingerprint = hash(rawId)
    session = sessionStore.find(fingerprint)

    if session is missing or session.revokedAt is not null:
        rejectUnauthenticated()

    if now() >= session.absoluteExpiresAt:
        revoke(session)
        rejectUnauthenticated()

    if now() - session.lastSeenAt > policy.idleTimeout:
        revoke(session)
        rejectUnauthenticated()

    if accountIsDisabled(session.subjectId):
        revoke(session)
        rejectUnauthenticated()

    updateLastSeenSafely(session)
    return principalFromCurrentAccountState(session.subjectId)
~~~

Các request cần kiểm tra quyền sau khi xác thực. Không lấy role từ cookie do client kiểm soát. Với thao tác nhạy cảm, kiểm tra auth_time/assurance và trạng thái tài khoản mới nhất.

### 13.4. Pseudocode logout

~~~text
logout(currentSession):
    atomicallyRevoke(currentSession.idFingerprint)
    clearCookie(
        name="__Host-sid",
        path="/",
        secure=true,
        httpOnly=true,
        sameSite="Lax",
        maxAge=0
    )
    return loggedOut
~~~

Nếu có session store cache, phát tín hiệu invalidate và bảo đảm mọi instance nhận trạng thái revoke theo SLA. Request đang chạy cần có chính sách nhất quán: thao tác mới phải bị từ chối; hành động đã commit trước thời điểm logout cần được xử lý theo transaction/audit semantics.

## 14. Bài thực hành: thiết kế Session cookie cho StudyHub

**Bối cảnh:** StudyHub là nền tảng học tập có web app, Course API, trang giảng viên và trang quản trị. Browser đăng nhập qua password hoặc passkey; một số tài khoản yêu cầu MFA. Người dùng có thể mở nhiều tab và đăng nhập trên nhiều thiết bị. Trang quản trị có thể sửa điểm và cấp role. Ứng dụng dùng nhiều instance sau load balancer.

Hãy thiết kế session cookie với các yêu cầu:

1. Cookie session không chứa thông tin cá nhân, role hoặc token OAuth.
2. Cookie dùng Secure, HttpOnly, SameSite phù hợp và host-only scope.
3. Session ID được sinh bằng CSPRNG và xoay sau login/MFA/step-up.
4. Server-side session store hỗ trợ expiry, revoke và quản lý nhiều thiết bị.
5. CSRF được bảo vệ trên mọi request thay đổi trạng thái.
6. XSS mitigation không dựa duy nhất vào HttpOnly.
7. Logout phải revoke server-side session và xóa cookie đúng scope.
8. Hành động sửa điểm/cấp role phải kiểm tra quyền hiện hành và độ mới của xác thực.
9. Session cookie không được gửi tới host không thuộc phạm vi cần thiết.
10. Sự cố session store/cache propagation phải có fallback an toàn và giám sát.

### 14.1. Quyết định thiết kế cần ghi lại

- Cookie name, prefix, Secure, HttpOnly, SameSite, Path, Domain, Max-Age/Expires.
- Entropy và cách sinh session ID.
- Cách lưu fingerprint và session record.
- Idle timeout, absolute timeout và re-authentication policy.
- Khi nào rotate session ID; cách hủy ID cũ nguyên tử.
- CSRF token strategy và kiểm tra Origin.
- Cách revoke một session, một thiết bị và toàn bộ tài khoản.
- Cách chia sẻ session store/cache giữa nhiều instance.
- Cách phối hợp với SSO/OIDC nếu có.
- Log/audit fields được phép lưu và dữ liệu tuyệt đối không log.

### 14.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Login thành công | Server tạo session mới, cookie có đúng flags và ID cũ trước xác thực bị revoke. |
| Cookie thiếu Secure | Security test phát hiện cấu hình không đạt. |
| Cookie thiếu HttpOnly | Security test phát hiện cấu hình không đạt với session cookie. |
| Cookie SameSite=None nhưng thiếu Secure | Browser không chấp nhận theo yêu cầu hiện hành; cấu hình bị test từ chối. |
| Cookie có Domain rộng không cần thiết | Test cấu hình phát hiện scope không phù hợp. |
| Cookie dùng __Host- có Domain | Browser từ chối cookie; test cấu hình thất bại. |
| Session ID đoán được hoặc lặp | Test entropy/uniqueness phát hiện lỗi thiết kế. |
| Session ID xuất hiện trong URL hoặc log | Test bảo mật thất bại; pipeline phải redact. |
| Đăng nhập với session ID tiền xác thực | Session ID được xoay và ID cũ bị từ chối. |
| Hoàn tất MFA/step-up | Session ID được xoay hoặc trạng thái assurance được cập nhật an toàn theo policy. |
| CSRF request thiếu token | Request thay đổi trạng thái bị từ chối. |
| CSRF token sai hoặc gắn session khác | Request bị từ chối. |
| GET endpoint thay đổi dữ liệu | Test API phát hiện vi phạm safe-method policy. |
| XSS cố đọc document.cookie | Không đọc được session cookie HttpOnly; test vẫn xác nhận XSS mitigation cần xử lý riêng. |
| XSS gọi API cùng origin | Không giả định HttpOnly chặn được; CSP/output encoding và authorization giảm tác động. |
| Idle timeout đã hết | Cookie cũ bị từ chối dù browser vẫn gửi. |
| Absolute timeout đã hết | Session bị từ chối dù người dùng hoạt động liên tục. |
| Logout local | Cookie bị xóa và server-side session bị revoke. |
| Replay cookie sau logout | Request bị từ chối. |
| Logout một thiết bị | Session của thiết bị đó bị revoke; thiết bị khác tiếp tục theo policy. |
| Logout mọi thiết bị | Mọi session thuộc tài khoản bị revoke. |
| Session store cache còn active sau revoke | Invalidation/TTL đáp ứng SLA; không tiếp tục cấp quyền vượt quá giới hạn. |
| Hai request rotate session đồng thời | Chỉ trạng thái session hợp lệ mới còn hiệu lực; không tạo hai session quyền cao ngoài policy. |
| Cookie trùng tên khác Path | Ứng dụng không chọn nhầm credential; cấu hình tránh scope chồng lấn. |
| Subdomain không tin cậy đặt cookie | Host-only/__Host- và parser không cho phép session confusion. |
| Browser restore session sau restart | Server-side expiry vẫn được thực thi. |
| SSO callback cross-site | Cookie transaction được cấu hình đúng và state/nonce được kiểm tra. |
| Authorization server/session store outage | Hành động nhạy cảm không fail-open; lỗi được ghi nhận và giám sát. |

### 14.3. Câu hỏi tự đánh giá

1. Cookie khác session và session ID ở điểm nào?
2. Vì sao session cookie được xem là bearer credential?
3. Set-Cookie và Cookie header khác nhau thế nào?
4. Vì sao HttpOnly không ngăn XSS gửi request thay mặt người dùng?
5. SameSite=Lax giảm CSRF nhưng vì sao không thay thế CSRF token?
6. Vì sao bỏ Domain thường an toàn hơn cho session cookie?
7. Tại sao Path không phải ranh giới bảo mật?
8. Session fixation xảy ra ở thời điểm nào và vì sao cần rotate ID sau login?
9. Idle timeout khác absolute timeout thế nào?
10. Vì sao browser đóng không phải bằng chứng session đã bị revoke?
11. Cookie stateless được ký có hạn chế gì khi cần logout tức thì?
12. Logout server-side khác xóa cookie ở browser ra sao?

**Tiêu chí hoàn thành:** Người học có thể mô tả request lifecycle, giải thích cookie flags và phạm vi browser gửi cookie, thiết kế session ID/vòng đời an toàn, phòng chống CSRF/fixation/hijacking, tổ chức server-side session store và chứng minh bằng test rằng cookie cũ bị từ chối sau logout/expiry.

## 15. Vận hành, audit và giám sát

Theo dõi các chỉ số:
- Số session active theo user, device, client và tenant.
- Tỷ lệ login tạo session mới, rotate session và revoke session.
- Số session hết hạn do idle/absolute timeout.
- Thời gian từ revoke tới khi mọi instance từ chối cookie cũ.
- Tỷ lệ request bị từ chối do session missing, expired, revoked hoặc CSRF failure.
- Số session rotation conflict và lỗi session store.
- Số cookie cấu hình sai flags theo môi trường.
- Tỷ lệ logout thất bại, pending và retry.
- Số phiên bất thường dẫn tới step-up hoặc revoke.

Audit event có thể lưu subject reference, session fingerprint/reference, client, device label, thời điểm, auth_time, assurance level, kết quả và reason code. Không ghi raw session ID, cookie header, access token, refresh token, mật khẩu hoặc CSRF secret. Phân quyền truy cập audit, đặt retention và cảnh báo truy vấn bất thường.

Định nghĩa SLA cho session revocation giữa các instance. Đo thực tế từ lúc server commit revoke đến khi request mang cookie cũ bị từ chối. Nếu cache invalidation trễ, phải đánh giá tác động theo loại API và chọn TTL/fail-closed policy phù hợp. Không chỉ dựa vào log “logout thành công” của web node đã nhận request.

## 16. Các lỗi thiết kế phổ biến

- **Chỉ xóa cookie ở browser:** session server vẫn active và cookie bị sao chép vẫn có thể replay.
- **Thiếu Secure:** cookie có thể bị gửi qua kết nối không bảo mật.
- **Thiếu HttpOnly:** script có thể đọc trực tiếp session cookie nếu có XSS.
- **Dùng SameSite=None không cần thiết:** mở rộng ngữ cảnh gửi cookie cross-site.
- **Đặt Domain rộng:** tăng phạm vi subdomain có thể nhận/đặt cookie.
- **Dựa vào Path để cô lập ứng dụng:** Path không phải ranh giới bảo mật.
- **Giữ nguyên session ID sau login:** mở đường cho session fixation.
- **Không có absolute timeout:** session có thể kéo dài vô hạn nhờ hoạt động nền.
- **Đưa PII/role vào cookie:** làm tăng dữ liệu lộ và nguy cơ stale authorization.
- **Không kiểm tra CSRF:** browser tự gửi cookie cho request attacker kích hoạt.
- **Tin rằng HttpOnly chặn mọi XSS:** script vẫn có thể gọi endpoint cùng origin.
- **Không xử lý cookie trùng tên:** parser ambiguity có thể làm nhầm session.
- **Không đồng bộ revoke giữa nhiều instance:** logout có thể không có hiệu lực ngay trên toàn hệ thống.
- **Xem browser close là logout:** browser có thể khôi phục session và server chưa revoke.
- **Không kiểm tra authorization sau authentication:** session hợp lệ không có nghĩa được phép thực hiện mọi hành động.

## 17. Tài liệu tham khảo và hướng đọc tiếp

- **RFC 6265 — HTTP State Management Mechanism:** nền tảng về cookie HTTP.
- **RFC 6265bis / HTTPbis cookie specification:** cập nhật quy tắc cookie được browser triển khai; đối chiếu phiên bản chuẩn đang áp dụng.
- **OWASP Session Management Cheat Sheet:** thiết kế session ID, rotation, expiry và logout.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** chiến lược CSRF token, SameSite và Origin validation.
- **OWASP Cross Site Scripting Prevention Cheat Sheet:** phòng chống XSS theo context.
- **MDN — HTTP cookies:** hành vi Set-Cookie, cookie attributes và browser compatibility.
- **OpenID Connect specifications:** hiểu cookie transaction, SSO và logout giữa OP/RP.

Khi áp dụng vào sản phẩm, hãy kiểm tra tài liệu framework/browser và chuẩn hiện hành, vì hành vi cookie có thể thay đổi theo browser privacy policy. Thiết kế cần được kiểm thử trên các browser được hỗ trợ, không chỉ dựa trên một browser local.

**Kết luận:** Session cookie là credential browser tự động gửi, thường tham chiếu tới trạng thái session phía server. Một thiết kế an toàn cần cookie scope hẹp, Secure, HttpOnly, SameSite phù hợp, session ID ngẫu nhiên, rotation đúng thời điểm, CSRF/XSS defense, timeout và revoke server-side. Cookie flags bảo vệ đường vận chuyển và hành vi browser; server-side session validation và authorization mới quyết định request có được chấp nhận hay không.
