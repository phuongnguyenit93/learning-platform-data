# Cookie phiên xác thực: thiết kế và bảo vệ session trong browser

## 1. Cookie phiên xác thực là gì?

**Cookie phiên xác thực** là cookie browser lưu giữ một định danh hoặc credential đại diện cho phiên đăng nhập. Khi người dùng đăng nhập thành công, server tạo session và gửi cookie qua response HTTP. Browser lưu cookie theo các thuộc tính được khai báo, rồi tự động đính kèm cookie vào những request phù hợp với domain, path, scheme, thời hạn và chính sách cookie.

Một ví dụ điển hình:

~~~http
Set-Cookie: __Host-session=RANDOM_OPAQUE_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị cookie nên là một định danh phiên ngẫu nhiên, khó đoán và không chứa password, thông tin cá nhân hay quyền truy cập được mã hóa theo cách có thể giải mã ở client. Server dùng định danh đó để tìm session, xác minh trạng thái đăng nhập, user, thời hạn và quyền hiện tại.

Cookie phiên là một **bearer credential**: ai sở hữu giá trị hợp lệ có thể có khả năng sử dụng phiên tương ứng. Vì vậy, bảo vệ cookie phải bao gồm TLS, thuộc tính cookie phù hợp, chống XSS/CSRF, quản lý vòng đời session, thu hồi phía server và tránh rò rỉ qua log hoặc URL.

Bài học thuộc chương **Authentication browser** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web; nghiên cứu Same-Origin Policy, CORS, XSS, CSRF, clickjacking, CSP, Trusted Types và security headers. Bài này tập trung vào cookie dùng cho phiên xác thực: cách server phát hành, browser lưu/gửi, thuộc tính bảo vệ, chống session fixation, xử lý CSRF, hết hạn, logout và kiểm tra hành vi thực tế.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả vòng đời cookie phiên từ đăng nhập tới logout.
2. Phân biệt cookie với session state được lưu ở server.
3. Thiết lập Set-Cookie với Secure, HttpOnly, SameSite, Path và Domain phù hợp.
4. Giải thích host-only cookie, domain cookie và giới hạn của Path.
5. Dùng prefix __Host- và __Secure- để áp đặt một số điều kiện cấu hình.
6. Phân biệt thời hạn cookie với thời hạn session phía server.
7. Ngăn session fixation bằng cách xoay session ID sau xác thực và thay đổi quyền.
8. Thiết kế idle timeout, absolute timeout và thu hồi session.
9. Hiểu SameSite, CORS và CSRF giải quyết các vấn đề khác nhau.
10. Xóa cookie đúng scope và revoke session phía server khi logout.
11. Đánh giá third-party cookie restrictions và cookie partitioning.
12. Kiểm tra cookie/session bằng DevTools và HTTP logs an toàn.

## 2. Cookie và session server là hai thành phần khác nhau

Cookie là dữ liệu browser lưu và gửi trong request. Session là trạng thái xác thực/phiên mà server quản lý. Hai thành phần thường phối hợp như sau:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Authentication server
    participant S as Session store
    B->>A: POST /login (thông tin đăng nhập)
    A->>A: Xác minh thông tin và chính sách đăng nhập
    A->>S: Tạo session với ID ngẫu nhiên
    S-->>A: Session được lưu
    A-->>B: Set-Cookie: session=opaque-id
    B->>A: GET /account (Cookie tự động được gửi)
    A->>S: Tra cứu và xác minh session
    S-->>A: User, trạng thái, quyền, thời hạn
    A-->>B: Response theo quyền hiện tại
~~~

Cookie thường chỉ chứa session ID. Server lưu các thông tin như user ID, thời điểm đăng nhập, thời điểm hoạt động gần nhất, trạng thái MFA, quyền hoặc metadata cần thiết trong session store.

### 2.1. Vì sao không lưu toàn bộ session trong cookie?

Cookie có giới hạn kích thước và được gửi trong các request phù hợp. Đưa profile, role, danh sách quyền hoặc dữ liệu lớn vào cookie làm tăng request size và dễ gây lỗi khi dữ liệu thay đổi.

Cookie cũng có thể bị người dùng quan sát qua browser tools. Nếu dùng cookie stateless có chữ ký, server vẫn phải kiểm tra tính hợp lệ, expiry, audience và khả năng thu hồi; không được tin payload chỉ vì client gửi lại.

### 2.2. Session ID là bearer credential

Nếu attacker lấy được session ID còn hiệu lực, họ có thể mạo danh người dùng cho tới khi session hết hạn hoặc bị thu hồi, tùy kiến trúc. Do đó:

- Sinh session ID bằng bộ sinh số ngẫu nhiên mật mã.
- Dùng entropy đủ lớn và không tuần tự.
- Không mã hóa user ID đơn giản rồi dùng làm session ID.
- Không ghi session ID nguyên vẹn vào log.
- Chỉ truyền qua HTTPS.
- Thu hồi session khi logout, khóa tài khoản hoặc phát hiện rủi ro.

### 2.3. Session store

Server có thể lưu session trong database, Redis hoặc hệ thống quản lý session khác. Lựa chọn phụ thuộc tải, thời hạn, tính sẵn sàng và yêu cầu thu hồi.

Session store phải có chính sách TTL, backup/replication phù hợp và quyền truy cập hạn chế. Không để client tự quyết định session còn hợp lệ chỉ bằng một timestamp hoặc role trong cookie.

## 3. Vòng đời cookie phiên xác thực

Một vòng đời thường gồm:

1. Người dùng gửi thông tin đăng nhập qua HTTPS.
2. Server xác minh password/passkey/MFA và trạng thái tài khoản.
3. Server hủy hoặc vô hiệu hóa session ID trước xác thực nếu có.
4. Server sinh session ID mới và lưu session.
5. Server gửi Set-Cookie với thuộc tính bảo vệ.
6. Browser lưu cookie và tự gửi trong request phù hợp.
7. Server kiểm tra session và authorization cho từng request.
8. Session hết hạn, bị revoke hoặc người dùng logout.
9. Server vô hiệu hóa session; response hết hạn cookie phía browser.

Không coi việc browser còn giữ cookie là bằng chứng session phía server vẫn còn hiệu lực. Cookie có thể tồn tại sau khi session đã bị revoke hoặc hết hạn.

## 4. Set-Cookie: server phát hành cookie

Server tạo cookie bằng response header Set-Cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

Mỗi cookie nên được phát hành bằng một Set-Cookie header riêng. Không nối nhiều cookie thành một header phân cách bằng dấu phẩy, vì Expires có thể chứa dấu phẩy và cách parse sẽ sai.

JavaScript browser không thể tự đặt header Set-Cookie trong response. Cookie được browser xử lý theo response và chính sách cookie của nó.

### 4.1. Set-Cookie không đọc được qua Fetch

Set-Cookie là forbidden response-header name. JavaScript không thể đọc nó bằng:

~~~js
const response = await fetch("/login");
console.log(response.headers.get("Set-Cookie")); // null
~~~

Browser có thể xử lý Set-Cookie dù script không đọc được header. Với cross-origin Fetch, việc nhận và lưu cookie còn phụ thuộc credentials mode, CORS credentials policy và cookie privacy policy.

### 4.2. Browser tự gửi Cookie

Khi cookie phù hợp với request, browser tạo request header:

~~~http
Cookie: __Host-session=opaque-random-value
~~~

Trang không thể tự đặt Cookie request header bằng Fetch hoặc XMLHttpRequest trong browser. Cookie được chọn từ cookie store theo quy tắc của browser.

### 4.3. Cookie không phải dữ liệu tùy ý của ứng dụng

Cookie có giới hạn về kích thước, số lượng và chính sách eviction riêng theo browser. Không dùng cookie làm database hoặc nơi lưu payload lớn. Chỉ giữ session identifier và preference nhỏ, không nhạy cảm khi thật sự cần.

## 5. Secure: chỉ gửi cookie qua kết nối an toàn

Thuộc tính Secure yêu cầu browser chỉ gửi cookie qua secure transport theo quy tắc cookie:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong production, cookie phiên xác thực cần có Secure. Kết hợp HTTPS và cấu hình TLS hợp lệ để bảo vệ request/response trên đường truyền.

### 5.1. Secure không thay TLS configuration

Secure không tạo certificate, không sửa hostname sai và không tự mã hóa endpoint HTTP. Server vẫn cần HTTPS, certificate hợp lệ, redirect an toàn và HSTS phù hợp.

### 5.2. Không fallback về HTTP

Nếu endpoint HTTPS lỗi certificate hoặc proxy, không chuyển cookie phiên sang HTTP để “đăng nhập vẫn chạy”. Sửa TLS, DNS, proxy hoặc endpoint. Hạ cấp transport có thể làm lộ bearer credential.

### 5.3. Local development

Browser có quy tắc đặc biệt cho localhost/loopback và secure context trong môi trường phát triển. Không lấy ngoại lệ local làm cấu hình production. Nên dùng HTTPS local với certificate dev được trust có kiểm soát để kiểm thử đầy đủ thuộc tính Secure.

## 6. HttpOnly: hạn chế JavaScript đọc session cookie

HttpOnly ngăn JavaScript truy cập cookie qua document.cookie:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cookie không có HttpOnly, script cùng origin có thể đọc cookie qua document.cookie nếu cookie phù hợp với URL và không bị giới hạn khác.

HttpOnly rất quan trọng cho session cookie vì giảm khả năng XSS đánh cắp trực tiếp giá trị session ID.

### 6.1. HttpOnly không chặn mọi hành động của XSS

Nếu XSS chạy trong origin, script độc vẫn có thể gửi request tới API. Browser có thể tự đính kèm HttpOnly cookie phù hợp, và script có thể đọc response mà user hiện tại được phép đọc.

Vì vậy, HttpOnly giảm rủi ro đánh cắp cookie trực tiếp nhưng không thay:
- Output encoding và safe DOM APIs.
- CSP và Trusted Types khi phù hợp.
- Authorization server-side.
- CSRF defense.
- Giới hạn quyền và thời gian sống của session.

### 6.2. JavaScript không thể xóa HttpOnly cookie

document.cookie không thể đọc hoặc xóa cookie HttpOnly. Server cần gửi Set-Cookie hết hạn đúng tên và scope. Browser settings/DevTools của người dùng vẫn có thể quản lý cookie.

Không dùng HttpOnly như cam kết rằng cookie bị ẩn khỏi chính người điều khiển browser.

## 7. SameSite: kiểm soát gửi cookie trong ngữ cảnh cross-site

SameSite điều khiển việc browser gửi cookie trong một số ngữ cảnh request cross-site. Các giá trị chính:

| Giá trị | Hành vi khái quát |
| --- | --- |
| Strict | Chỉ gửi trong ngữ cảnh same-site theo quy tắc browser; có thể không gửi khi người dùng đi từ link bên ngoài vào site. |
| Lax | Cho phép cookie trong same-site context và một số top-level cross-site safe navigation theo quy tắc browser. |
| None | Cho phép cookie trong cross-site context nếu các điều kiện browser yêu cầu được đáp ứng; hiện đại cần Secure. |

Ví dụ:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Lax thường là điểm bắt đầu phù hợp cho session cookie ứng dụng web thông thường. Chọn Strict nếu UX và luồng đăng nhập cho phép; chỉ dùng None khi thật sự cần cookie cross-site và đã có CSRF defense phù hợp.

### 7.1. Same-site khác same-origin

Origin gồm scheme, host và port. Site là khái niệm dựa trên scheme và registrable domain theo quy tắc cookie/browser. Hai subdomain có thể khác origin nhưng vẫn same-site.

Ví dụ:
- https://app.example.test
- https://auth.example.test

Hai URL khác origin vì host khác nhau, nhưng có thể được xem là same-site theo quy tắc schemeful site. Vì vậy SameSite không thay allowlist Origin khi bảo vệ endpoint nhạy cảm.

### 7.2. SameSite=None cần Secure

Cookie cross-site thường cần:

~~~http
Set-Cookie: federated-session=value; Path=/; Secure; HttpOnly; SameSite=None
~~~

Browser có thể chặn third-party cookies hoặc áp dụng privacy policy khác dù cookie có SameSite=None; Secure. Không giả định cấu hình này bảo đảm cookie luôn được gửi trong iframe hoặc context bên thứ ba.

### 7.3. Default SameSite

Nếu không khai báo SameSite, browser hiện đại thường áp dụng hành vi mặc định tương đương Lax theo chính sách của chúng; một số chi tiết tương thích có thể khác. Đối với session cookie, nên khai báo rõ thuộc tính thay vì phụ thuộc implicit default.

## 8. Domain: host-only cookie và domain cookie

Nếu Set-Cookie không có Domain, cookie là host-only và chỉ được gửi tới host đã đặt cookie:

~~~http
Set-Cookie: session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu response đến từ app.example.test, host-only cookie chỉ áp dụng cho host đó.

Nếu khai báo Domain:

~~~http
Set-Cookie: session=opaque-id; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

cookie có thể được gửi tới domain đó và các subdomain phù hợp. Điều này mở rộng phạm vi tin cậy tới nhiều host.

### 8.1. Ưu tiên host-only cho session

Nếu không cần chia sẻ session giữa subdomain, bỏ Domain. Host-only cookie giảm số host có thể nhận credential.

Một subdomain bị chiếm quyền hoặc cấu hình sai có thể làm tăng rủi ro khi cookie được chia sẻ ở domain cha. Không dùng Domain rộng chỉ để tiện đăng nhập giữa nhiều app.

### 8.2. Dấu chấm đầu Domain không tạo khác biệt

Trong cách xử lý cookie hiện đại, Domain=example.test và Domain=.example.test được xem tương đương; dấu chấm đầu không tạo một phạm vi bảo mật riêng.

### 8.3. Không thể đặt cookie cho public suffix

Browser từ chối Domain thuộc public suffix như các hậu tố dùng chung theo Public Suffix List. Server không thể tạo cookie cho phạm vi quá rộng như một public suffix để chia sẻ credential giữa các site không liên quan.

## 9. Path: định tuyến cookie, không phải ranh giới bảo mật

Path giới hạn URL path mà browser gửi cookie tới:

~~~http
Set-Cookie: admin-session=value; Path=/admin; Secure; HttpOnly; SameSite=Lax
~~~

Cookie trên được gửi cho request path phù hợp với /admin theo quy tắc path-match.

Tuy nhiên, Path không phải cơ chế cô lập bảo mật giữa các ứng dụng cùng host. Script ở cùng origin có thể có khả năng truy cập cookie không HttpOnly theo quy tắc document.cookie; các ứng dụng cùng origin cũng chia sẻ nhiều quyền origin.

Không dựa vào Path để bảo vệ session admin khỏi một ứng dụng không tin cậy chạy cùng origin. Dùng origin/subdomain tách biệt và authorization server-side.

### 9.1. Xóa cookie phải đúng Path

Nếu cookie được tạo với Path=/admin, xóa cookie bằng Path=/ có thể tạo một cookie khác cùng tên thay vì xóa cookie cũ. Response xóa phải khớp Domain/host-only scope và Path của cookie cần loại bỏ.

## 10. Prefix __Host- và __Secure-

Browser hiện đại hỗ trợ cookie name prefix để áp đặt một số điều kiện khi chấp nhận cookie.

### 10.1. __Host-

Cookie bắt đầu bằng __Host- phải đáp ứng các điều kiện chính:
- Được đặt từ secure origin theo yêu cầu prefix.
- Có thuộc tính Secure.
- Có Path=/.
- Không có Domain.

Ví dụ:

~~~http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix này giúp cookie host-only, không bị subdomain đặt cookie cùng tên cho parent domain và áp dụng toàn host.

### 10.2. __Secure-

Cookie bắt đầu bằng __Secure- phải được đặt trong secure context và có thuộc tính Secure theo quy tắc browser:

~~~http
Set-Cookie: __Secure-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

__Secure- không bắt buộc Path=/ hoặc cấm Domain như __Host-. Nếu phù hợp kiến trúc, __Host- thường tạo ràng buộc phạm vi chặt hơn cho session cookie.

### 10.3. Prefix không thay kiểm tra server

Prefix được browser hỗ trợ áp dụng khi xử lý cookie. Server vẫn cần kiểm tra session, quyền, CSRF và cấu hình TLS. Với browser cũ hoặc client không phải browser, không coi prefix là cơ chế authorization.

## 11. Thời hạn cookie và thời hạn session

Cookie có hai cơ chế thời hạn phổ biến:

- Session cookie: không khai báo Expires hoặc Max-Age; browser giữ theo vòng đời session browser.
- Persistent cookie: có Expires hoặc Max-Age; browser có thể lưu qua lần đóng/mở browser tới khi hết hạn hoặc bị xóa.

Ví dụ persistent cookie:

~~~http
Set-Cookie: remember-device=value; Max-Age=2592000; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Max-Age tính bằng giây; nếu đồng thời có Expires, Max-Age thường được ưu tiên theo cookie rules.

### 11.1. Session cookie không đồng nghĩa server session còn sống tới khi đóng browser

Server có thể đặt TTL ngắn hơn. Session có thể hết hạn do idle timeout, absolute timeout, revoke hoặc chính sách bảo mật ngay cả khi browser vẫn giữ cookie.

Ngược lại, session cookie có thể được browser khôi phục qua session restore tùy browser. Không dựa vào việc đóng cửa sổ để thu hồi phiên phía server.

### 11.2. Cookie expiry không thay server expiry

Nếu cookie có Max-Age 30 ngày nhưng session server hết hạn sau 20 phút không hoạt động, request sau 20 phút phải bị server từ chối. Client không được quyết định session còn sống chỉ dựa trên cookie expiry.

### 11.3. Remember me là một thiết kế riêng

“Remember me” thường cần credential dài hạn hoặc refresh mechanism riêng, có rotation, revoke và phát hiện reuse. Không đơn giản đặt session cookie chính thành sống một năm.

Tách session ngắn hạn khỏi persistent login token nếu kiến trúc yêu cầu. Token dài hạn phải có scope, rotation, storage và revocation strategy phù hợp.

## 12. Sinh session ID an toàn

Session ID cần được tạo bằng cryptographically secure random generator phía server. Không dùng:
- Timestamp hoặc số tăng dần.
- User ID hoặc email.
- Hash của password có thể dự đoán.
- Random generator không phù hợp bảo mật.
- Giá trị cố định dùng chung cho mọi user.

Một ví dụ Node.js tạo token ngẫu nhiên:

~~~js
import { randomBytes } from "node:crypto";

const sessionId = randomBytes(32).toString("base64url");
~~~

32 byte ngẫu nhiên cung cấp entropy lớn cho một session identifier. Server lưu hash hoặc giá trị định danh theo thiết kế session store; nếu lưu hash, cần có quy trình lookup và rotate tương ứng.

Không log sessionId. Nếu cần correlation, tạo request ID riêng không có quyền truy cập session.

## 13. Session fixation và rotation

**Session fixation** xảy ra khi attacker khiến nạn nhân sử dụng một session ID mà attacker đã biết hoặc kiểm soát, rồi chờ nạn nhân đăng nhập để session đó trở thành authenticated.

Phòng vệ cốt lõi là xoay session ID sau khi xác thực thành công.

Luồng an toàn:
1. Browser có thể có session anonymous trước đăng nhập.
2. User gửi thông tin xác thực.
3. Server xác minh password/MFA/passkey.
4. Server vô hiệu hóa anonymous/pre-auth session ID cũ nếu phù hợp.
5. Server tạo session ID mới ngẫu nhiên.
6. Server gắn trạng thái authenticated vào session mới.
7. Server gửi Set-Cookie chứa ID mới.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Server
    B->>S: Request với anonymous session A
    S->>S: Xác thực thông tin đăng nhập
    S->>S: Revoke session A
    S->>S: Tạo authenticated session B
    S-->>B: Set-Cookie session=B
    B->>S: Request tiếp theo với session B
~~~

### 13.1. Xoay session sau thay đổi quyền

Cân nhắc rotate session khi:
- Đăng nhập thành công.
- Hoàn tất MFA hoặc nâng cấp assurance level.
- Chuyển từ anonymous sang authenticated.
- Thay đổi quyền quan trọng hoặc chuyển tenant.
- Thực hiện thao tác nhạy cảm cần tái xác thực.

Không rotate tùy tiện ở mọi request nếu làm hỏng concurrent request; thiết kế grace/transition có kiểm soát và revoke session cũ đúng lúc.

### 13.2. Không giữ session ID cũ sau login

Nếu server chỉ thêm flag authenticated vào session ID cũ, attacker biết ID trước đó có thể chiếm phiên sau khi user đăng nhập. Hãy tạo ID mới và vô hiệu hóa ID cũ.

## 14. Idle timeout và absolute timeout

Session cần thời hạn phía server. Hai giới hạn thường dùng:

| Timeout | Ý nghĩa |
| --- | --- |
| Idle timeout | Session hết hạn sau một khoảng không có hoạt động hợp lệ. |
| Absolute timeout | Session hết hạn sau tổng thời gian tối đa kể từ khi tạo hoặc xác thực, dù vẫn có hoạt động. |

Ví dụ policy minh họa:
- Idle timeout: 20 phút với ứng dụng nhạy cảm.
- Absolute timeout: 8 giờ.
- Re-authentication: yêu cầu xác thực lại trước thao tác rủi ro cao.

Các con số phải dựa trên threat model, UX, quy định và loại dữ liệu; không có một giá trị phù hợp mọi ứng dụng.

### 14.1. Hoạt động nào reset idle timeout?

Server cần định nghĩa request nào được xem là hoạt động hợp lệ. Không để một background polling vô hạn tự giữ session sống mãi nếu người dùng không tương tác.

Không cập nhật last-activity trước khi xác thực request hoặc khi request không hợp lệ. Kẻ tấn công không nên kéo dài session bằng request không có quyền.

### 14.2. Absolute timeout không thể bị kéo dài bởi activity

Absolute timeout giới hạn tổng thời gian phiên. Nếu mỗi request reset absolute expiry, nó trở thành idle timeout thứ hai và mất mục tiêu giới hạn session dài hạn.

Khi hết absolute timeout, yêu cầu đăng nhập lại hoặc re-authentication theo policy.

## 15. Thu hồi session phía server

Session phải có trạng thái revoke/expired. Các sự kiện có thể yêu cầu thu hồi:
- Người dùng logout.
- Người dùng đổi password hoặc reset credential.
- Admin khóa tài khoản.
- Phát hiện credential bị lộ hoặc hành vi đáng ngờ.
- MFA bị reset.
- Người dùng chọn “đăng xuất khỏi tất cả thiết bị”.
- Policy yêu cầu thu hồi khi quyền hoặc tenant thay đổi.

Nếu server dùng session store, xóa hoặc đánh dấu session revoked. Nếu dùng token stateless, cần chiến lược revoke như denylist, version counter, key rotation hoặc token lifetime ngắn tùy kiến trúc.

### 15.1. Logout một thiết bị và logout mọi thiết bị

Logout hiện tại thường revoke session đang dùng. “Logout all devices” cần tìm và revoke mọi session/refresh token thuộc user, có thể dựa vào session registry hoặc token version.

Không giả định xóa cookie trên một browser sẽ thu hồi cookie ở thiết bị khác.

### 15.2. Session rotation và concurrent requests

Khi rotate session, nhiều request đồng thời có thể vẫn mang ID cũ. Server cần xử lý transition một cách nhất quán, nhưng không giữ ID cũ hợp lệ quá lâu hoặc cho phép nó tiếp tục thực hiện thao tác nhạy cảm.

Thiết kế grace window nếu thật sự cần, giới hạn scope và thời gian, đồng thời đảm bảo session cũ không thể dùng để đăng nhập lại hoặc nâng quyền.

## 16. Logout đúng cách

Logout cần là thao tác thay đổi trạng thái và thường nên dùng POST, có CSRF protection phù hợp:

~~~http
POST /logout HTTP/1.1
Cookie: __Host-session=opaque-id
Origin: https://app.example.test
X-CSRF-Token: csrf-token-value
~~~

Server:
1. Xác thực session và CSRF.
2. Revoke session phía server.
3. Hết hạn cookie bằng Set-Cookie đúng tên/scope.
4. Dọn dữ liệu client nhạy cảm theo policy.
5. Trả kết quả logout rõ ràng.

Response ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json
~~~

### 16.1. Xóa cookie không thay revoke

Nếu chỉ hết hạn cookie mà server vẫn chấp nhận session ID cũ, bản sao credential bị đánh cắp vẫn có thể dùng được. Revoke phía server là bước bắt buộc.

### 16.2. Xóa đúng Domain và Path

Cookie được xác định bởi tên cùng phạm vi Domain/host-only và Path. Response xóa cần khớp scope cookie ban đầu. Cookie host-only dùng __Host- không có Domain và Path=/, giúp quy trình xóa đơn giản hơn.

Nếu có cookie trùng tên ở nhiều Path hoặc Domain, có thể cần gửi nhiều Set-Cookie để xóa từng cookie đã phát hành. Tránh tạo các cookie cùng tên khác scope một cách không cần thiết.

### 16.3. Logout không nên dùng GET

GET được thiết kế cho thao tác an toàn theo ngữ nghĩa HTTP. Dùng GET để logout có thể bị kích hoạt bởi link, crawler, prefetch hoặc CSRF. Dùng POST và kiểm tra CSRF/Origin theo kiến trúc.

## 17. CSRF và cookie phiên

Cookie được browser tự động gửi trong request phù hợp. Điều này tạo tiện ích cho session nhưng cũng là nền tảng của Cross-Site Request Forgery (CSRF): một trang khác có thể khiến browser gửi request tới ứng dụng đã đăng nhập.

Ví dụ, user đang đăng nhập app.example.test rồi truy cập trang độc hại. Trang độc có thể thử gửi form hoặc điều hướng tới endpoint thay đổi trạng thái. Nếu cookie được gửi và server không xác minh request, hành động có thể xảy ra dù attacker không đọc response.

### 17.1. SameSite là lớp phòng vệ, không phải toàn bộ CSRF defense

SameSite Lax/Strict giảm việc cookie được gửi trong một số cross-site context. Tuy nhiên:
- Cùng site nhưng khác origin vẫn có thể là same-site.
- Luồng SSO/callback có thể cần xử lý đặc biệt.
- Browser policy có thể khác.
- Một số request same-site từ subdomain bị chiếm quyền vẫn đáng lo.

Với thao tác nhạy cảm, kết hợp CSRF token, Origin validation hoặc Fetch Metadata theo threat model.

### 17.2. CSRF token

Server có thể phát CSRF token gắn với session và yêu cầu client gửi lại trong header hoặc form body cho request thay đổi trạng thái. Token phải được kiểm tra phía server và không được chấp nhận chỉ vì client gửi một giá trị bất kỳ.

Với cookie HttpOnly, frontend không cần đọc session cookie để gửi CSRF token; token có thể được cung cấp qua response body hoặc cơ chế an toàn khác gắn với session.

### 17.3. Origin và Referer validation

Server có thể kiểm tra Origin của request thay đổi trạng thái, và dùng Referer như fallback theo policy phù hợp. So sánh exact origin, không dùng substring matching.

Không chấp nhận thiếu Origin một cách tùy tiện trên endpoint browser-only nhạy cảm. Đối với native client hoặc luồng đặc biệt, thiết kế cơ chế xác thực riêng.

### 17.4. CORS không thay CSRF defense

CORS chủ yếu quyết định JavaScript cross-origin có được đọc response hay không. Một request đơn giản có thể được gửi mà không cần preflight. Vì vậy, server không thể chỉ bật CORS allowlist rồi coi cookie-authenticated endpoint đã chống CSRF.

## 18. CORS và Fetch credentials

Nếu frontend và API khác origin, Fetch mặc định dùng credentials: "same-origin". Muốn gửi cookie cross-origin, cần cấu hình:

~~~js
const response = await fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

Server cần trả origin cụ thể và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng Access-Control-Allow-Origin: * khi response có credentials. Cookie vẫn chịu SameSite, Secure, Domain, Path, third-party cookie restrictions và partitioning.

### 18.1. Set-Cookie cross-origin

Browser có thể xử lý Set-Cookie trong cross-origin response nếu credentials mode và các chính sách liên quan cho phép. JavaScript vẫn không đọc được Set-Cookie header.

Nếu cookie bị chặn bởi third-party cookie policy, thêm Access-Control-Allow-Credentials không buộc browser lưu/gửi cookie.

### 18.2. CORS không phải session sharing

Cho phép CORS từ một origin không tự động chia sẻ cookie. Cookie Domain/host scope và credentials mode quyết định cookie có được gửi hay không; CORS quyết định script có thể đọc response theo policy hay không.

## 19. Third-party cookies và partitioning

Browser ngày càng hạn chế cookie trong third-party context để giảm tracking. Một cookie được dùng trong iframe hoặc request cross-site có thể bị chặn dù server đã đặt SameSite=None; Secure.

Nếu sản phẩm cần embedded login hoặc tích hợp cross-site:
- Ưu tiên luồng top-level redirect khi phù hợp.
- Tránh phụ thuộc third-party cookie không ổn định.
- Kiểm tra browser privacy settings thực tế.
- Cân nhắc Storage Access API khi use case và browser hỗ trợ.
- Đánh giá CHIPS/Partitioned cookies nếu cần trạng thái riêng theo top-level site.

### 19.1. Partitioned cookies (CHIPS)

Cookie có thuộc tính Partitioned có thể được lưu trong partition gắn với top-level site trên browser hỗ trợ. Ví dụ minh họa:

~~~http
Set-Cookie: widget-session=value; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
~~~

Cookie partitioned không phải cookie chia sẻ toàn cục giữa mọi website. Cùng embedded origin có thể có cookie state riêng khi được nhúng dưới các top-level site khác nhau.

Kiểm tra browser support và yêu cầu thuộc tính liên quan. Không dùng Partitioned như cách thay authentication hoặc authorization.

### 19.2. Storage partitioning không phải session isolation đầy đủ

Partitioning thay đổi cách browser phân vùng một số state theo top-level site. Server vẫn phải xác minh session và quyền; không suy luận rằng cookie partitioned tự giải quyết mọi CSRF hoặc tracking issue.

## 20. Cookie prefix và chống cookie tossing

Subdomain không tin cậy có thể cố đặt cookie cùng tên với Domain cha nếu cookie policy cho phép. Điều này có thể tạo cookie trùng tên hoặc cookie tossing trong một số ứng dụng xử lý header không cẩn thận.

Biện pháp:
- Ưu tiên host-only cookie.
- Dùng prefix __Host- cho session cookie nếu phù hợp.
- Không dùng Domain rộng nếu không cần.
- Server xử lý duplicate cookie names một cách xác định và từ chối trạng thái mơ hồ nếu cần.
- Không chọn session chỉ bằng cách lấy giá trị đầu tiên/cuối cùng không có policy rõ.

Prefix __Host- yêu cầu Secure, Path=/ và không có Domain trong browser hỗ trợ, giảm khả năng subdomain tạo cookie cùng tên cho parent scope.

## 21. Cookie session và XSS

XSS có thể chạy JavaScript trong origin của ứng dụng. Nếu session cookie không có HttpOnly, script có thể đọc giá trị qua document.cookie trong phạm vi được phép.

Khi cookie có HttpOnly:
- Script không đọc trực tiếp được session ID.
- Browser vẫn tự gửi cookie trong Fetch/navigation/WebSocket phù hợp.
- Script độc có thể thực hiện hành động trong quyền của user nếu server không có kiểm soát bổ sung.
- Response mà user được phép đọc vẫn có thể bị exfiltrate.

Phòng vệ:
- HttpOnly cho session cookie.
- Secure và SameSite phù hợp.
- CSP, Trusted Types và safe DOM APIs.
- Output encoding và kiểm soát third-party scripts.
- Authorization và kiểm tra nghiệp vụ ở server.
- Re-authentication cho thao tác rủi ro cao.
- Giới hạn thời gian sống và revoke session.

Không dùng CSRF token như cách chữa XSS. XSS thường có khả năng lấy token CSRF từ DOM hoặc gọi API theo session hiện tại tùy thiết kế.

## 22. Cookie session và HTTPS/TLS

Session cookie là bearer credential nên cần bảo vệ trên đường truyền. Dùng HTTPS cho toàn bộ luồng đăng nhập và ứng dụng, không chỉ endpoint login.

Các biện pháp:
- Redirect HTTP sang HTTPS trước khi phát hành session.
- Đặt Secure cho cookie.
- Dùng HSTS phù hợp với domain/subdomain sau khi đánh giá rollout.
- Không có mixed content trong API call.
- Kiểm tra TLS certificate và hostname.
- Không để reverse proxy downgrade request tới client.
- Chỉ tin forwarded scheme headers từ proxy được cấu hình tin cậy.

### 22.1. TLS termination tại reverse proxy

Nếu TLS kết thúc ở load balancer, proxy có thể chuyển request nội bộ tới backend. Backend phải biết request public ban đầu là HTTPS thông qua cấu hình proxy trust.

Không tin X-Forwarded-Proto do client bất kỳ gửi trực tiếp. Nếu backend nghĩ request là HTTP, nó có thể tạo redirect hoặc Set-Cookie không đúng. Cấu hình trusted proxy rõ ràng và kiểm tra response thực tế.

### 22.2. HSTS và Secure cookie

Secure cookie yêu cầu browser gửi qua secure transport. HSTS giúp browser ghi nhớ rằng host phải được truy cập qua HTTPS. Hai cơ chế bổ trợ nhưng không thay thế nhau.

HSTS không sửa certificate lỗi và Secure cookie không tự bật HSTS.

## 23. Session cookie và cache

Cookie xác thực không tự động ngăn browser hoặc proxy cache response chứa dữ liệu riêng tư. API và trang nhạy cảm cần cache policy phù hợp.

Ví dụ:

~~~http
Cache-Control: no-store
~~~

Có thể dùng cho response chứa dữ liệu nhạy cảm mà không muốn lưu trong HTTP cache. Không nhầm no-cache với no-store: no-cache yêu cầu revalidation khi dùng lại; no-store yêu cầu không lưu theo HTTP caching rules.

Cache Storage do ứng dụng/service worker quản lý là cơ chế riêng. Không cache response cá nhân vào Cache Storage nếu không có yêu cầu offline, namespace theo user và cleanup rõ ràng.

## 24. Xử lý session hết hạn

Khi server nhận cookie nhưng session đã hết hạn hoặc bị revoke, trả kết quả xác thực phù hợp, thường là 401 cho API. Không chỉ dựa vào cookie expiry để quyết định.

Frontend nên:
- Xóa state UI nhạy cảm.
- Dừng polling/WebSocket.
- Chuyển tới luồng đăng nhập hoặc hiển thị session expired.
- Giữ draft chưa gửi nếu có thể và an toàn.
- Không retry vô hạn request 401.
- Không log cookie/session ID.

Server có thể gửi Set-Cookie hết hạn khi phát hiện session không hợp lệ, nhưng cần đảm bảo scope khớp cookie đã phát hành.

## 25. Multi-tab và nhiều session

Nhiều tab cùng origin thường dùng chung cookie store của browser profile. Khi một tab đăng xuất hoặc server revoke session, các tab khác có thể vẫn đang hiển thị dữ liệu cũ cho tới khi request tiếp theo phát hiện session invalid.

Thiết kế:
- Backend xác minh session trên mỗi request.
- BroadcastChannel hoặc cơ chế tương đương có thể báo logout cho tab khác để UX cập nhật.
- Không dùng message giữa tab làm bằng chứng authorization.
- Dừng WebSocket và background activity khi session bị revoke.
- Xử lý request đang chạy trong lúc logout.
- Không lưu dữ liệu nhạy cảm trong UI state lâu hơn cần thiết.

BroadcastChannel là tín hiệu đồng bộ phía client; server vẫn là nguồn sự thật về session.

## 26. Session theo thiết bị và quản lý phiên

Ứng dụng có thể cung cấp trang “Thiết bị đang đăng nhập” với thông tin:
- Tên thiết bị/browser ở mức khái quát.
- Thời điểm đăng nhập gần nhất.
- Thời điểm hoạt động gần nhất.
- Vị trí ước lượng nếu có cơ sở và người dùng được thông báo.
- Session hiện tại hay session khác.
- Hành động revoke session.

Không thu thập fingerprint quá mức chỉ để nhận diện thiết bị. Nếu cung cấp “logout all devices”, server phải revoke session/token liên quan và thông báo cho kết nối realtime đang mở.

## 27. Debug cookie phiên bằng DevTools

Trong Chrome/Chromium, có thể kiểm tra cookie ở DevTools → Application → Storage → Cookies. Tên tab/menu thay đổi theo browser/version.

Kiểm tra:
1. Cookie name và domain/host-only.
2. Path.
3. Expires/Max-Age.
4. Secure.
5. HttpOnly.
6. SameSite.
7. Partitioned nếu browser hỗ trợ.
8. Cookie có bị blocked/rejected vì policy hay không.
9. Request nào thực sự gửi cookie trong Network → Cookies/Request Headers.
10. Response Set-Cookie có warning hoặc blocked reason không.

Không sao chép giá trị session cookie vào ticket, screenshot, chat hoặc log. Chỉ ghi thuộc tính và trạng thái cần điều tra.

### 27.1. Console không đọc được HttpOnly

document.cookie không hiển thị cookie HttpOnly. Đây là hành vi mong đợi. DevTools Application panel có thể hiển thị cookie cho người kiểm soát browser.

Không kết luận cookie chưa được tạo chỉ vì document.cookie không có tên cookie đó.

### 27.2. Kiểm tra SameSite thực tế

Dùng hai origin/site test do bạn kiểm soát. Quan sát cookie trong:
- Navigation top-level.
- Fetch same-origin.
- Fetch cross-origin với credentials include.
- Iframe cross-site.
- Request từ subdomain cùng site.

Ghi nhận browser version và privacy settings. Không suy luận từ một browser rằng mọi browser có hành vi giống nhau.

## 28. Thực hành A — Tạo và kiểm tra session cookie

Trong ứng dụng lab HTTPS:
1. Đăng nhập bằng tài khoản test.
2. Server tạo session ID ngẫu nhiên.
3. Response gửi cookie __Host-session với Path=/, Secure, HttpOnly và SameSite=Lax.
4. Mở DevTools → Application → Cookies.
5. Kiểm tra thuộc tính cookie.
6. Mở Network và xác minh request authenticated gửi cookie.
7. Thử document.cookie và quan sát cookie HttpOnly không xuất hiện.

Không dùng session cookie production cho bài lab.

## 29. Thực hành B — Session fixation và rotation

Tạo luồng lab có anonymous session trước đăng nhập. Ghi nhận session ID trước login ở server test log bằng fingerprint không thể dùng để xác thực.

Đăng nhập thành công và xác minh:
- Server tạo ID mới.
- ID cũ bị revoke.
- Request sau login chỉ dùng session mới.
- Session cũ không thể truy cập endpoint authenticated.

Không in session ID thật ra Console hoặc lưu vào screenshot. Dùng fingerprint hash ngắn chỉ phục vụ kiểm tra.

## 30. Thực hành C — SameSite và CSRF

Dùng hai site lab:
- App có cookie session.
- Trang test khác site.

Thử request GET và POST thay đổi trạng thái trong môi trường giả lập. So sánh SameSite Strict, Lax và None; quan sát cookie được gửi hay không.

Sau đó triển khai CSRF token và Origin validation ở server. Xác minh request không có token hoặc có Origin không hợp lệ bị từ chối. Không thực hiện với tài khoản thật hoặc website bên thứ ba.

## 31. Thực hành D — Logout và revoke

Đăng nhập trên hai browser tab cùng profile:
1. Xác minh cả hai tab dùng cùng session.
2. Logout ở tab thứ nhất bằng POST có CSRF protection.
3. Server revoke session và hết hạn cookie.
4. Tab thứ hai gọi API tiếp theo.
5. Xác minh server trả 401/đóng kết nối realtime và UI chuyển trạng thái phù hợp.
6. Thử dùng session ID cũ trong môi trường lab và xác minh server từ chối.

Không ghi giá trị cookie vào báo cáo.

## 32. Checklist review Cookie phiên xác thực

- [ ] Session cookie chứa định danh ngẫu nhiên, không chứa password hoặc PII.
- [ ] Session ID được sinh bằng CSPRNG và có entropy đủ lớn.
- [ ] Cookie phiên production có Secure.
- [ ] Cookie phiên có HttpOnly.
- [ ] SameSite được khai báo rõ theo luồng ứng dụng.
- [ ] Ưu tiên host-only cookie; chỉ đặt Domain khi thật sự cần chia sẻ.
- [ ] Dùng Path=/ cho cookie __Host-.
- [ ] Dùng prefix __Host- khi browser support và kiến trúc phù hợp.
- [ ] Không dựa vào Path để cô lập ứng dụng cùng origin.
- [ ] Cookie expiry và server session timeout được quản lý riêng.
- [ ] Có idle timeout và absolute timeout phù hợp.
- [ ] Rotate session ID sau login và thay đổi mức quyền.
- [ ] Revoke session phía server khi logout, khóa tài khoản hoặc reset credential.
- [ ] Logout dùng POST và có CSRF defense.
- [ ] Xóa cookie đúng tên, Domain/host-only scope và Path.
- [ ] Không log Cookie, Set-Cookie, session ID hoặc bearer token.
- [ ] Không đặt session credential trong URL/query string.
- [ ] Bảo vệ endpoint thay đổi trạng thái khỏi CSRF.
- [ ] Không coi CORS hoặc SameSite là biện pháp CSRF duy nhất.
- [ ] Xác minh Origin/Fetch Metadata cho endpoint nhạy cảm khi phù hợp.
- [ ] Backend xác thực và authorization trên mọi request.
- [ ] Revalidate quyền cho session dài hạn và kết nối realtime.
- [ ] Kiểm tra third-party cookie restrictions và partitioning nếu dùng iframe/SSO.
- [ ] Cache response nhạy cảm theo policy phù hợp.
- [ ] Kiểm tra TLS, HSTS và trusted proxy configuration.
- [ ] Kiểm tra hành vi thực tế trên browser mục tiêu.
- [ ] Dùng profile và tài khoản test; không đưa cookie vào screenshot/ticket.

## 33. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Cookie là toàn bộ session.” | **Sai** | Cookie thường chỉ chứa session ID; server quản lý session state. |
| “Session cookie hết hạn khi server session hết hạn.” | **Sai** | Browser cookie và server session có thời hạn riêng. |
| “Đóng browser luôn revoke session.” | **Sai** | Session phía server có thể vẫn tồn tại hoặc browser khôi phục session cookie. |
| “HttpOnly khiến cookie không thể xem trong DevTools.” | **Sai** | HttpOnly chặn JavaScript trang; DevTools có thể quản lý/hiển thị cookie. |
| “HttpOnly ngăn XSS thực hiện request authenticated.” | **Sai** | Browser vẫn tự gửi cookie; XSS có thể gọi API trong session. |
| “Secure tự bật HTTPS cho website.” | **Sai** | Secure chỉ điều khiển gửi cookie theo secure transport. |
| “SameSite Strict và same-origin là một.” | **Sai** | Site và origin là hai khái niệm khác nhau. |
| “SameSite đủ chống mọi CSRF.” | **Sai** | Cần đánh giá same-site subdomain, luồng đặc biệt và CSRF token/Origin. |
| “CORS chặn mọi request CSRF.” | **Sai** | CORS chủ yếu kiểm soát đọc response; request vẫn có thể được gửi. |
| “Domain=.example.test an toàn hơn Domain=example.test.” | **Sai** | Dấu chấm đầu không tạo khác biệt phạm vi trong browser hiện đại. |
| “Path=/admin cô lập cookie khỏi app khác cùng origin.” | **Sai** | Path không phải ranh giới bảo mật giữa ứng dụng cùng origin. |
| “Cookie có Max-Age 30 ngày nghĩa session sống 30 ngày.” | **Sai** | Server có thể hết hạn hoặc revoke session sớm hơn. |
| “Xóa cookie là logout an toàn.” | **Sai** | Server phải revoke session để credential bị sao chép mất hiệu lực. |
| “Đổi session ID sau login là không cần thiết.” | **Sai** | Rotation chống session fixation. |
| “Prefix __Secure- giống __Host-.” | **Sai** | __Host- còn yêu cầu Path=/ và không có Domain. |
| “SameSite=None bảo đảm cookie bên thứ ba luôn được gửi.” | **Sai** | Browser privacy policy có thể chặn third-party cookie. |
| “Cookie session nên chứa role và quyền để server khỏi tra cứu.” | **Sai** | Quyền cần được xác minh theo trạng thái tin cậy; cookie là credential phía client. |
| “CSP thay HttpOnly và CSRF token.” | **Sai** | Các cơ chế bảo vệ những lớp rủi ro khác nhau. |

## 34. Tổng kết

Cookie phiên xác thực là credential browser tự động gửi trong request phù hợp. Cookie nên mang một session identifier ngẫu nhiên, còn server quản lý danh tính, quyền, thời hạn và trạng thái thu hồi. Secure bảo vệ việc gửi qua transport an toàn; HttpOnly hạn chế JavaScript đọc cookie; SameSite giảm một số request cross-site; Domain, Path và prefix quyết định phạm vi cookie.

Các thuộc tính cookie không thay thế vòng đời session an toàn. Server cần rotate ID sau đăng nhập để chống fixation, áp dụng idle/absolute timeout, xác minh quyền ở từng request và revoke session khi logout hoặc có sự kiện bảo mật. Logout phải vừa thu hồi session phía server vừa hết hạn cookie đúng scope.

Cookie được browser tự động gửi nên ứng dụng cần phòng vệ CSRF. SameSite, CSRF token, Origin/Fetch Metadata validation và CORS có vai trò khác nhau; không dùng một cơ chế để thay toàn bộ các cơ chế còn lại. Với embedded/third-party use case, cần kiểm tra browser privacy policy và partitioning thay vì giả định cookie luôn được gửi.

Ba nguyên tắc cần nhớ:

1. **Cookie chỉ mang credential tối thiểu:** dùng session ID ngẫu nhiên, host-only khi có thể, Secure, HttpOnly và SameSite phù hợp; không đưa secret vào URL hoặc log.
2. **Server quản lý vòng đời phiên:** rotate sau login/nâng quyền, áp dụng idle và absolute timeout, revoke khi logout hoặc credential thay đổi; xóa cookie đúng Domain/Path.
3. **Phòng vệ theo từng lớp:** SameSite giảm một số CSRF context, CSRF token/Origin validation bảo vệ thao tác thay đổi trạng thái, HttpOnly giảm đọc cookie bằng script và authorization vẫn nằm ở backend.

Khi review cookie phiên, hãy hỏi: **cookie có chứa gì, browser gửi nó tới host/path/context nào, thuộc tính Secure/HttpOnly/SameSite đã phù hợp chưa, session ID có được rotate sau login không, server có timeout và revoke không, logout đã xử lý cả server lẫn browser chưa, và request thay đổi trạng thái có CSRF defense không?** Trả lời các câu hỏi này giúp giữ phiên đăng nhập tiện dụng mà vẫn kiểm soát được rủi ro chiếm đoạt session.
