# Cookie compromise: ứng phó khi cookie phiên bị lộ hoặc bị chiếm đoạt

> **Chương:** Ứng phó sự cố  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Cookie compromise** là sự cố trong đó cookie chứa session identifier hoặc credential có thể bị người không được phép sử dụng. Nếu cookie còn hiệu lực và server chấp nhận nó, kẻ tấn công có thể thực hiện request dưới danh tính của người dùng mà không cần biết mật khẩu. Đây là một dạng chiếm đoạt phiên (session hijacking).

Ứng phó phải bắt đầu bằng việc ngăn session bị lộ tiếp tục được sử dụng. Xóa cookie trong browser chỉ làm sạch một bản lưu ở client; nếu server vẫn chấp nhận session identifier cũ thì người đã sao chép nó vẫn có thể replay. Vì vậy, **thu hồi session ở server là hành động containment quan trọng nhất**. Sau đó mới xóa cookie phía browser, yêu cầu xác thực lại, điều tra nguyên nhân và khôi phục dịch vụ.

Phạm vi xử lý phụ thuộc loại bí mật bị lộ. Một session cookie bị đánh cắp thường cần revoke session tương ứng hoặc toàn bộ session của tài khoản. Nếu signing key, refresh-token family hoặc kho session bị lộ, phạm vi có thể mở rộng sang nhiều tài khoản và cần rotate key hoặc vô hiệu hóa hàng loạt credential. Không xoay mọi khóa một cách máy móc khi chỉ có bằng chứng một cookie riêng lẻ bị sao chép; hãy dựa trên phạm vi lộ lọt đã xác minh.

Bài này trình bày runbook từ phát hiện, phân loại, bảo toàn bằng chứng, containment, eradication, recovery đến post-incident review. Nội dung tập trung vào cookie xác thực, session ID, refresh token, session fixation, XSS, CSRF, cookie scope, browser storage và các tín hiệu audit.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện dấu hiệu cookie hoặc session bị replay.
2. Phân biệt cookie theft, session fixation, CSRF, XSS và credential compromise.
3. Xác định session, tài khoản, thiết bị và tài nguyên có thể bị ảnh hưởng.
4. Bảo toàn bằng chứng mà không ghi cookie hoặc token thô vào log.
5. Thu hồi một session, tất cả session của tài khoản hoặc toàn bộ session hệ thống theo phạm vi sự cố.
6. Xử lý opaque session, JWT access token và refresh-token rotation đúng cách.
7. Quyết định khi nào cần rotate signing key, encryption key hoặc các secret khác.
8. Xóa cookie phía browser với đúng tên, Path và Domain scope sau khi revoke phía server.
9. Xử lý session fixation, logout, đổi mật khẩu và thay đổi quyền.
10. Điều tra nguyên nhân gốc như XSS, TLS thiếu, log leakage, cookie scope rộng hoặc thiết bị bị malware.
11. Khôi phục an toàn, xác thực lại người dùng và theo dõi dấu hiệu replay sau containment.
12. Thiết kế hardening, monitoring và diễn tập incident response cho cookie/session.

## 1. Cookie compromise là sự cố gì?

### 1.1 Cookie xác thực có thể hoạt động như bearer credential

Một cookie session thường chứa một giá trị khó đoán để server tra cứu session tương ứng:

~~~http
Cookie: __Host-session=RANDOM_SESSION_IDENTIFIER
~~~

Nếu server chấp nhận giá trị này như bằng chứng phiên hợp lệ, bất kỳ ai sở hữu giá trị đó và có thể gửi request phù hợp đều có thể sử dụng session. Cookie thường không yêu cầu người gửi chứng minh họ là browser ban đầu.

Vì vậy, khi session cookie bị sao chép, attacker có thể replay nó từ một browser hoặc máy khác. Họ có thể không cần password, MFA code hoặc thao tác đăng nhập mới cho đến khi session bị thu hồi hoặc hết hạn.

### 1.2 Phân biệt các loại sự cố liên quan

| Tình huống | Điều gì xảy ra | Hành động trọng tâm |
|---|---|---|
| Cookie/session theft | Attacker sao chép session cookie còn hiệu lực | Revoke session, điều tra kênh lộ lọt |
| Session replay | Cookie bị lộ được dùng lại từ client khác | Tìm các request cùng session, revoke và kiểm tra hành động |
| Session fixation | Attacker khiến nạn nhân đăng nhập bằng session ID mà attacker đã biết | Regenerate session ID sau xác thực, revoke ID cũ |
| XSS | Script không tin cậy chạy trong origin ứng dụng | Chặn XSS, đánh giá session abuse dù cookie có HttpOnly |
| CSRF | Browser tự gửi cookie hợp lệ khi nạn nhân truy cập trang attacker | CSRF defenses, kiểm tra request; không mặc định là cookie bị đánh cắp |
| Credential compromise | Password, MFA hoặc recovery credential bị lộ | Reset/revoke credential, kiểm tra đăng nhập và session |
| Signing key compromise | Khóa ký token bị lộ | Rotate key, từ chối token ký bằng key bị lộ, đánh giá phạm vi toàn hệ thống |

Các tình huống có thể xảy ra đồng thời. Ví dụ, XSS có thể cho attacker thực hiện hành động bằng session của nạn nhân mà không đọc được cookie HttpOnly. Điều đó là session abuse, dù không có bằng chứng cookie value đã bị exfiltrate.

### 1.3 HttpOnly không ngăn mọi hành vi khi có XSS

HttpOnly ngăn JavaScript đọc cookie qua document.cookie. Nó giảm một con đường đánh cắp cookie, nhưng XSS vẫn có thể gửi request cùng origin bằng cookie mà browser tự đính kèm.

Do đó:

- HttpOnly giúp giảm khả năng đọc trộm session ID bằng script.
- HttpOnly không ngăn script độc hại thao tác trong phiên đang mở.
- CSP, output encoding, safe DOM sinks và Trusted Types vẫn quan trọng.
- Khi có XSS trong origin xác thực, phải điều tra các hành động được thực hiện trong session trong khoảng thời gian bị ảnh hưởng.

### 1.4 SameSite không phải cơ chế chống replay

SameSite kiểm soát khi browser gửi cookie trong một số ngữ cảnh cross-site. Nó giúp giảm CSRF, nhưng không ngăn người đã có cookie value gửi request trực tiếp từ client khác.

Không coi SameSite=Lax hoặc Strict là biện pháp thu hồi cookie bị đánh cắp. Server-side revocation vẫn cần thiết.

## 2. Mô hình cookie và session cần hiểu trước khi ứng phó

### 2.1 Cookie là dữ liệu phía browser; session thường nằm ở server

Với opaque session:

~~~text
Browser
  |
  | Cookie: session_id
  v
Application server
  |
  | Lookup session_id
  v
Session store
  |
  +--> user_id
  +--> created_at
  +--> expires_at
  +--> auth_level
  +--> revoked_at
  +--> session metadata
~~~

Cookie chỉ mang một identifier. Server quyết định identifier đó còn hợp lệ hay không. Khi session store đánh dấu revoked, mọi request tiếp theo dùng cùng identifier phải bị từ chối, kể cả attacker đã sao chép cookie trước đó.

### 2.2 Cookie scope gồm Domain, Path, Secure và SameSite

| Thuộc tính | Tác dụng | Lưu ý bảo mật |
|---|---|---|
| Domain | Xác định host/domain được gửi cookie | Bỏ Domain để tạo host-only cookie; tránh chia sẻ session với subdomain không cần thiết |
| Path | Giới hạn path request gửi cookie | Không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host |
| Secure | Chỉ gửi cookie qua secure transport theo quy tắc browser | Production cần HTTPS toàn bộ |
| HttpOnly | Không expose cookie cho JavaScript qua document.cookie | Không ngăn XSS gửi request đã xác thực |
| SameSite | Hạn chế gửi cookie trong cross-site context | Giảm CSRF; không ngăn replay cookie đã bị lấy |
| Max-Age/Expires | Thời hạn cookie phía browser | Không thay thế session expiry và revocation phía server |

### 2.3 Ưu tiên host-only cookie cho session

Cookie xác thực nên có scope hẹp. Nếu không cần chia sẻ với subdomain, bỏ thuộc tính Domain.

Ví dụ production:

~~~http
Set-Cookie: __Host-session=RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix __Host- yêu cầu Secure, Path=/ và không có Domain trong browser hỗ trợ prefix này. Nó giúp ngăn subdomain đặt cookie cùng tên với scope Domain rộng hơn. Hãy kiểm tra tương thích browser mục tiêu và luôn giữ các thuộc tính thực tế đúng yêu cầu.

__Secure- yêu cầu cookie được đặt với Secure, nhưng không áp đặt Path=/ và không cấm Domain như __Host-.

### 2.4 SameSite chọn theo flow đăng nhập

- Strict hạn chế cookie trong cross-site navigation; có thể ảnh hưởng link từ website khác hoặc luồng liên kết ngoài.
- Lax thường là lựa chọn cân bằng cho session cookie ứng dụng web.
- None cho phép gửi trong cross-site context và yêu cầu Secure; nếu cần, phải có CSRF defenses mạnh và đánh giá third-party cookie restrictions.

SameSite=None phải đi cùng Secure. Nếu browser từ chối cookie vì thiếu Secure, session có thể không được lưu như ứng dụng mong đợi.

Chọn chính sách theo luồng thực tế, kiểm thử login redirect, SSO và payment return. Không hạ SameSite chỉ để làm một flow chạy mà không hiểu tác động CSRF.

### 2.5 Session ID phải khó đoán và được rotate

Session identifier cần được tạo bằng CSPRNG với entropy đủ lớn. Ví dụ Node.js:

~~~js
import { randomBytes } from "node:crypto";

const sessionId = randomBytes(32).toString("base64url");
~~~

Không dùng Math.random(), timestamp, user ID hoặc giá trị có thể dự đoán.

Tạo session ID mới sau:

- Đăng nhập thành công.
- Hoàn tất MFA hoặc nâng authentication assurance.
- Thay đổi quyền hoặc chuyển sang vai trò nhạy cảm.
- Thay đổi thông tin xác thực quan trọng.
- Phục hồi tài khoản sau sự cố.

Session ID cũ phải bị revoke để ngăn session fixation và giảm nguy cơ tiếp tục sử dụng identifier đã biết.

## 3. Dấu hiệu phát hiện cookie compromise

### 3.1 Dấu hiệu từ authentication và session logs

Tín hiệu cần điều tra:

- Cùng một session fingerprint xuất hiện đồng thời từ các network khác nhau trong thời gian bất thường.
- Session tiếp tục được dùng sau logout hoặc sau khi server đã ghi nhận revoke.
- Session có hành vi mới ngay sau khi người dùng mở link, tải file hoặc truy cập trang có dấu hiệu XSS.
- Một phiên thực hiện hành động nhạy cảm mà người dùng không nhận ra.
- Refresh token bị dùng lại sau khi token family đã rotate.
- Session hoạt động sau thời gian idle hoặc absolute expiry theo policy.
- Nhiều session mới được tạo sau một đợt phishing hoặc malware alert.
- Tài khoản có thay đổi email, MFA, recovery method hoặc quyền mà chủ tài khoản không thực hiện.

### 3.2 Impossible travel chỉ là tín hiệu, không phải bằng chứng

IP geolocation không chính xác tuyệt đối. VPN, mobile carrier, corporate proxy, NAT và roaming có thể làm địa chỉ IP thay đổi nhanh. Một IP khác hoặc quốc gia khác không đủ để kết luận cookie đã bị đánh cắp.

Kết hợp nhiều yếu tố: thời gian, session reuse, hành động, thiết bị, auth events, user report và threat intelligence. Không khóa tài khoản chỉ vì một IP thay đổi nếu chưa có policy và ngữ cảnh hỗ trợ.

### 3.3 Phân tích session reuse

Có thể lưu metadata an toàn:

- Session ID fingerprint bằng HMAC.
- Account ID nội bộ.
- Thời điểm tạo, refresh, revoke và hết hạn.
- IP đã rút gọn hoặc được xử lý theo privacy policy.
- User-Agent đã chuẩn hóa.
- Authentication method và assurance level.
- Các hành động nhạy cảm.
- Request ID/correlation ID.

Không lưu raw Cookie header, raw session ID hoặc refresh token vào application log, analytics, trace hay ticket. Người có quyền đọc log không nên có khả năng replay session từ log đó.

### 3.4 Dấu hiệu từ hạ tầng

Điều tra các nguồn:

- CDN, reverse proxy và WAF access logs.
- Authentication service và session store audit.
- Application logs và admin audit trails.
- Error monitoring quanh thời điểm nghi vấn.
- CSP violation reports nếu có dấu hiệu XSS.
- Endpoint security/EDR khi thiết bị người dùng bị nghi nhiễm malware.
- Secret manager audit nếu nghi signing key hoặc database credential bị truy cập.

Đồng bộ thời gian giữa hệ thống để dựng timeline chính xác. Ghi timezone và độ lệch đồng hồ nếu có.

## 4. Phân loại mức độ và phạm vi ảnh hưởng

### 4.1 Câu hỏi phân loại ban đầu

Trong giờ đầu, xác định:

1. Có bằng chứng cookie/session value bị lộ hay mới chỉ có hành vi đáng ngờ?
2. Sự cố chỉ ảnh hưởng một tài khoản hay nhiều tài khoản?
3. Cookie là opaque session, access token, refresh token hay token chứa quyền?
4. Session vẫn còn hiệu lực không?
5. Có hành động trái phép, dữ liệu bị xem hoặc bị thay đổi không?
6. Có lộ XSS, signing key, database, log hoặc thiết bị đầu cuối không?
7. Attacker còn truy cập được origin, endpoint hoặc session store không?
8. Có cần tạm dừng một chức năng để chặn tiếp tục khai thác không?

### 4.2 Gợi ý phân loại severity

| Mức | Ví dụ | Phản ứng khuyến nghị |
|---|---|---|
| Critical | Signing key hoặc session store bị lộ; replay diện rộng; tài khoản đặc quyền bị chiếm | Kích hoạt incident command, revoke/rotate diện rộng, cô lập nguồn lộ |
| High | Session theft được xác nhận; có truy cập dữ liệu hoặc thao tác trái phép | Revoke session/tài khoản liên quan, điều tra data access, yêu cầu re-auth |
| Medium | Một session đáng ngờ, chưa xác nhận replay hoặc data access | Revoke session nghi vấn, giám sát tăng cường và xác minh người dùng |
| Low / Informational | Cookie sai cấu hình hoặc cảnh báo chưa có dấu hiệu khai thác | Khắc phục theo change process, theo dõi và kiểm tra lại |

Đây là gợi ý phân loại, không thay thế incident severity matrix của tổ chức. Tác động tới dữ liệu, khách hàng, nghĩa vụ pháp lý và quyền đặc biệt có thể làm tăng mức độ.

### 4.3 Xác định blast radius

Lập danh sách:

- Tài khoản và session ID fingerprint bị ảnh hưởng.
- Thời điểm bắt đầu sớm nhất có thể bị lộ.
- Các cookie name, Domain, Path và origin liên quan.
- Access/refresh token family nếu có.
- Signing key hoặc encryption key có thể liên quan.
- Hệ thống downstream chấp nhận credential đó.
- Dữ liệu hoặc hành động có thể bị truy cập.
- Các phiên bản ứng dụng và browser có cấu hình yếu.

Không mở rộng thu thập dữ liệu cá nhân quá mức cần thiết. Chỉ giữ dữ liệu phục vụ điều tra và theo retention policy.

## 5. Runbook ứng phó sự cố

### 5.1 Giai đoạn 0 — Kích hoạt và phân công

Khi có alert hoặc user report:

- Tạo incident ID và ghi thời điểm phát hiện.
- Chỉ định incident lead, người xử lý identity/session và người điều tra nguồn lộ.
- Ghi rõ giả thuyết ban đầu và bằng chứng hiện có.
- Chọn kênh trao đổi nội bộ được phê duyệt.
- Giữ một timeline chung có timezone.
- Xác định ai có quyền revoke session hàng loạt hoặc rotate key.

Không gửi cookie value, token hoặc ảnh chụp DevTools chứa credential qua chat, email hoặc ticket thông thường.

### 5.2 Giai đoạn 1 — Containment: chặn credential bị lạm dụng

Ưu tiên theo phạm vi:

**Một session bị nghi lộ**

1. Tìm session theo account và fingerprint.
2. Đánh dấu session revoked trong session store.
3. Từ chối request mới dùng session đó.
4. Gửi lệnh logout/reauth cho client nếu có cơ chế push, nhưng không phụ thuộc vào nó.
5. Yêu cầu người dùng xác thực lại trên một session mới.

**Một tài khoản bị ảnh hưởng**

1. Revoke tất cả session đang hoạt động của tài khoản.
2. Revoke refresh token family liên quan.
3. Tăng yêu cầu xác thực cho lần đăng nhập tiếp theo.
4. Kiểm tra thay đổi password, email, MFA và recovery method.
5. Xem xét tạm khóa tài khoản nếu attacker vẫn có khả năng điều khiển.

**Nhiều tài khoản hoặc key chung bị lộ**

1. Kích hoạt quy trình incident diện rộng.
2. Vô hiệu hóa mọi credential chịu ảnh hưởng.
3. Nếu signing key bị lộ, từ chối token được ký bằng key đó và triển khai key mới.
4. Nếu session store/database bị lộ, đánh giá toàn bộ session và dữ liệu liên quan.
5. Tạm dừng endpoint hoặc flow đang bị khai thác nếu cần để ngăn phát sinh session mới.
6. Theo dõi lỗi đăng nhập và tải hệ thống trong quá trình revoke diện rộng.

Không chỉ gửi Set-Cookie để xóa cookie ở browser rồi coi incident đã được containment. Cookie đã sao chép vẫn có thể được replay nếu server chưa revoke.

### 5.3 Giai đoạn 2 — Bảo toàn bằng chứng

Trước khi xóa log hoặc reset hệ thống:

- Xuất auth/session audit logs theo khoảng thời gian liên quan.
- Bảo toàn CDN/WAF/reverse proxy logs.
- Ghi lại session fingerprint, request ID, account và timestamp.
- Lưu các thay đổi account, MFA, password và role.
- Bảo toàn alert từ EDR, SIEM và error monitoring.
- Ghi người thu thập, nguồn, thời điểm và checksum của artifact theo quy trình evidence handling.
- Giới hạn quyền truy cập bằng chứng và ghi audit trail.

Không thu thập cookie thô từ browser của nạn nhân nếu không có quy trình forensic được phê duyệt. Không đưa credential vào ticket hoặc log để "chứng minh" nó đã bị lộ.

### 5.4 Giai đoạn 3 — Điều tra nguyên nhân gốc

Kiểm tra các đường lộ phổ biến:

- XSS hoặc DOM injection trong origin có session.
- Script bên thứ ba, extension hoặc dependency bị compromise.
- Cookie thiếu Secure hoặc ứng dụng còn endpoint HTTP.
- Cookie Domain quá rộng và subdomain bị chiếm.
- Session/token xuất hiện trong URL, Referer, analytics hoặc logs.
- Reverse proxy log toàn bộ Cookie header.
- Backup, crash dump, browser profile hoặc endpoint malware.
- Session fixation do không rotate ID sau login.
- Refresh token không rotate hoặc không phát hiện reuse.
- Signing key hoặc session store credential bị truy cập.
- CSRF dẫn tới hành động trái phép mà attacker không cần đọc cookie.

Đánh giá xem cookie value thực sự bị exfiltrate hay attacker chỉ dùng browser của nạn nhân để gửi request. Hai tình huống có thể dẫn tới hành động giống nhau nhưng biện pháp khắc phục khác nhau.

### 5.5 Giai đoạn 4 — Eradication: loại bỏ nguồn lộ

Ví dụ:

- Vá XSS bằng contextual output encoding, safe DOM APIs, sanitizer và CSP/Trusted Types.
- Gỡ hoặc cập nhật script/dependency bị compromise.
- Thu hẹp cookie Domain và loại bỏ endpoint HTTP.
- Xóa cookie/token khỏi log pipeline và backup mới.
- Sửa reverse proxy/WAF để không log Cookie hoặc Authorization header.
- Sửa session fixation bằng regenerate session ID.
- Bật refresh token rotation và reuse detection.
- Rotate signing key nếu key thực sự bị lộ.
- Xử lý malware/extension compromise trên endpoint theo quy trình IT/security.

Không chỉ xóa dấu vết mà bỏ nguyên nhân. Nếu XSS còn tồn tại, session mới được cấp có thể lại bị lạm dụng.

### 5.6 Giai đoạn 5 — Recovery

Chỉ khôi phục sau khi containment và eradication đạt điều kiện:

1. Xác nhận session cũ không còn được chấp nhận.
2. Xác nhận key/token cũ đã bị vô hiệu hóa theo phạm vi.
3. Phát hành session mới sau xác thực phù hợp.
4. Yêu cầu MFA/step-up authentication nếu rủi ro cao.
5. Kiểm tra quyền tài khoản và recovery methods.
6. Xác minh dữ liệu, giao dịch và thay đổi account.
7. Theo dõi replay, login anomaly và refresh-token reuse.
8. Kiểm tra tỷ lệ lỗi login, logout và API trong giai đoạn sau triển khai.

Không tự động reset password cho mọi trường hợp nếu chỉ có một session cookie bị lộ và không có bằng chứng password compromise. Tuy nhiên, nếu credential hoặc MFA/recovery channel có thể bị lộ, xử lý chúng theo incident scope.

### 5.7 Giai đoạn 6 — Kết thúc và post-incident review

- Ghi timeline từ phát hiện tới containment.
- Ghi số tài khoản/session bị ảnh hưởng.
- Ghi dữ liệu hoặc hành động trái phép đã xác nhận và phần chưa thể xác định.
- Ghi các key/token đã rotate hoặc revoke.
- Ghi root cause và control thất bại.
- Đánh giá nghĩa vụ thông báo khách hàng/cơ quan quản lý theo quy định và quy trình pháp lý của tổ chức.
- Tạo action items có owner và deadline.
- Cập nhật detection rule, runbook và diễn tập.

Không đóng incident chỉ vì alert đã hết. Cần xác nhận không còn credential cũ được chấp nhận và nguồn lộ đã được xử lý.

## 6. Thu hồi session ở server

### 6.1 Opaque session: revoke theo session ID

Với session store, một record có thể có:

~~~json
{
  "sessionFingerprint": "hmac-fingerprint",
  "userId": "user-123",
  "createdAt": "2026-11-22T08:00:00Z",
  "lastSeenAt": "2026-11-22T09:00:00Z",
  "expiresAt": "2026-11-22T17:00:00Z",
  "revokedAt": null,
  "authLevel": "mfa"
}
~~~

Server kiểm tra session tồn tại, chưa revoked và chưa hết hạn trên mỗi request cần xác thực. Có thể dùng cache ngắn hạn, nhưng phải có cơ chế invalidation đủ nhanh cho incident response.

### 6.2 Revoke một session

~~~js
async function revokeSession(sessionId) {
  const fingerprint = fingerprintSessionId(sessionId);

  await sessionStore.update(
    { sessionFingerprint: fingerprint },
    {
      revokedAt: new Date(),
      revokeReason: "suspected-cookie-compromise"
    }
  );
}
~~~

Không ghi sessionId thô. fingerprint nên là HMAC bằng audit key riêng, không dùng plain hash nếu session ID có entropy thấp hoặc cần chống dò offline.

Trong triển khai thật, HMAC key dùng để tạo fingerprint phải được quản lý ổn định qua các lần restart bằng secret manager/KMS và có quy trình rotation. Không tạo key ngẫu nhiên mới mỗi lần khởi động nếu session store còn tồn tại, vì server sẽ không tra cứu được fingerprint cũ. Có thể tách key dùng cho lookup và key dùng cho audit correlation.

### 6.3 Revoke tất cả session của một tài khoản

~~~js
async function revokeAllUserSessions(userId, reason) {
  await sessionStore.updateMany(
    { userId, revokedAt: null },
    {
      revokedAt: new Date(),
      revokeReason: reason
    }
  );
}
~~~

Nếu ứng dụng dùng session version hoặc account auth epoch, có thể tăng version để làm vô hiệu toàn bộ session cũ. Cần bảo đảm mọi service kiểm tra version mới và cache không giữ quyết định cũ quá lâu.

### 6.4 Kiểm tra revocation trên mỗi request

Logic khái quát:

~~~js
async function authenticateRequest(request) {
  const sessionId = readSessionCookie(request);

  if (!sessionId) {
    return { authenticated: false };
  }

  const fingerprint = fingerprintSessionId(sessionId);
  const session = await sessionStore.findByFingerprint(fingerprint);

  if (
    !session ||
    session.revokedAt ||
    new Date(session.expiresAt).getTime() <= Date.now()
  ) {
    return { authenticated: false };
  }

  return {
    authenticated: true,
    userId: session.userId,
    sessionFingerprint: fingerprint
  };
}
~~~

Ví dụ chỉ minh họa luồng. Trong mô hình này, session store index theo HMAC fingerprint; không lưu raw session ID trong audit record. Production phải validate session format, giới hạn thời gian, kiểm tra auth level và xử lý race condition giữa revoke với request đang chạy. Nếu thiết kế lưu hash/fingerprint thay vì raw ID, mọi đường lookup và revoke phải dùng cùng một phép biến đổi.

### 6.5 Request đang chạy tại thời điểm revoke

Revoke thường ngăn request mới, nhưng một request đã được xác thực trước thời điểm revoke có thể vẫn đang chạy. Với thao tác nhạy cảm:

- Kiểm tra session/version ngay trước commit nếu kiến trúc hỗ trợ.
- Dùng transaction và idempotency cho thao tác tài chính.
- Hủy job nền gắn với session khi có thể.
- Kiểm tra audit event sau thời điểm revoke.
- Xác định rõ SLA tối đa từ lúc revoke đến khi mọi node nhận trạng thái mới.

## 7. Xử lý JWT và refresh token

### 7.1 JWT access token không tự thu hồi chỉ bằng cách xóa cookie

Nếu server chỉ kiểm tra chữ ký và expiry của JWT mà không truy vấn trạng thái session, token đã phát hành có thể còn hợp lệ cho tới exp. Xóa cookie khỏi browser không làm token đã sao chép mất hiệu lực.

Các lựa chọn:

- Access token lifetime ngắn.
- jti denylist hoặc token revocation store.
- Account/session version được kiểm tra khi xác thực.
- Introspection endpoint cho token opaque.
- Rotate signing key khi key bị lộ, đồng thời vô hiệu token cũ theo policy.

Mỗi lựa chọn có trade-off về độ trễ, tính sẵn sàng và khả năng revoke.

### 7.2 Chỉ rotate signing key khi có căn cứ

Nếu một session cookie chứa JWT bị đánh cắp nhưng signing key vẫn an toàn, revoke token/session theo jti, session version hoặc denylist nếu hệ thống hỗ trợ. Rotate signing key sẽ ảnh hưởng diện rộng và có thể làm logout mọi user.

Nếu signing key bị lộ:

1. Xác định key ID (kid) và các token được ký bằng key đó.
2. Phát hành key mới qua secret/key management process.
3. Ngừng tin key bị lộ; không giữ nó trong accepted key set chỉ để tránh logout nếu attacker có thể tiếp tục ký token.
4. Vô hiệu hóa token đã ký bằng key cũ.
5. Cập nhật mọi verifier/service và cache.
6. Kiểm tra token refresh, service-to-service và downstream systems.
7. Audit việc truy cập secret manager và nguồn lộ key.

Nếu dùng asymmetric signing, private signing key bị lộ là tình huống nghiêm trọng; public key không phải secret nhưng trust configuration vẫn cần cập nhật để từ chối key ID cũ.

### 7.3 Refresh token rotation và reuse detection

Mỗi lần dùng refresh token, server phát hành token mới và vô hiệu token cũ. Nếu token cũ bị dùng lại, có thể là dấu hiệu token family đã bị sao chép.

Phản ứng thường gồm:

- Đánh dấu refresh-token family bị compromise.
- Revoke token family và session liên quan.
- Yêu cầu đăng nhập lại.
- Ghi audit event với token fingerprint, không ghi raw token.
- Kiểm tra thời điểm và client đã dùng token cũ.
- Xem xét yêu cầu xác thực lại/MFA.

Không chỉ rotate token mà vẫn chấp nhận token cũ trong thời gian dài nếu mục tiêu là phát hiện replay.

### 7.4 Cookie có thể chứa refresh token

Nếu refresh token nằm trong HttpOnly cookie, server cần revoke token family hoặc grant tương ứng. Clear cookie ở client chỉ ngăn browser đó gửi tiếp; attacker đã sao chép token vẫn có thể sử dụng nếu server còn chấp nhận.

## 8. Xóa cookie phía browser sau khi revoke

### 8.1 Revoke server trước, expire cookie sau

Response có thể yêu cầu browser xóa cookie:

~~~http
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Với cookie thường, tên, Domain và Path phải khớp scope cookie cần xóa. Cookie host-only và cookie Domain-scoped có thể là các cookie khác nhau dù cùng tên.

Với __Host-session, không thêm Domain và giữ Path=/. Hãy kiểm tra cookie prefix constraints của browser mục tiêu.

### 8.2 Path không phải security boundary

Path giúp browser chọn cookie gửi theo URL path, nhưng không nên dùng Path để cô lập các ứng dụng không tin cậy trên cùng host. Ứng dụng cùng origin vẫn có thể tương tác qua nhiều cơ chế browser khác. Dùng origin/site riêng khi cần cô lập mạnh hơn.

### 8.3 document.cookie không thể xóa HttpOnly cookie

JavaScript không thể đọc hoặc xóa cookie HttpOnly bằng document.cookie. Server cần gửi Set-Cookie với expiry phù hợp. Không yêu cầu người dùng chạy JavaScript console để xóa session.

### 8.4 Clear-Site-Data có phạm vi rộng

Một response có thể dùng:

~~~http
Clear-Site-Data: "cookies"
~~~

Header này có thể xóa cookie trong phạm vi domain được browser áp dụng, bao gồm tác động tới subdomain tùy cách triển khai. Đây là biện pháp mạnh và có thể làm người dùng đăng xuất khỏi nhiều ứng dụng cùng site.

Chỉ dùng sau khi đánh giá blast radius, hỗ trợ browser và yêu cầu recovery. Nó không thay thế server-side revocation vì cookie đã bị sao chép ở nơi khác vẫn có thể được replay.

### 8.5 Logout phải invalidate session ở server

Một endpoint logout nên:

1. Xác thực session hiện tại.
2. Revoke session trong server store.
3. Revoke refresh token family nếu session sở hữu family đó.
4. Trả Set-Cookie expire đúng scope.
5. Không tiết lộ session identifier trong response/log.
6. Trả trạng thái thành công an toàn, kể cả session đã hết hạn hoặc đã revoke.

## 9. Điều tra các nguyên nhân gốc thường gặp

### 9.1 XSS trong origin có cookie xác thực

Kiểm tra:

- Stored, reflected và DOM-based XSS.
- innerHTML, outerHTML, insertAdjacentHTML và document.write.
- Template escape sai context.
- URL/script sink và event handler string.
- Dependency hoặc third-party script.
- CSP violation và report.
- Trusted Types enforcement nếu được dùng.

Nếu có XSS, xác định attacker có thể thực hiện hành động nào dù cookie HttpOnly. Revoke session liên quan, vá XSS và đánh giá dữ liệu bị truy cập hoặc thay đổi.

### 9.2 Cookie Domain quá rộng

Cookie Domain=.example.com có thể được gửi tới nhiều subdomain phù hợp. Nếu một subdomain cũ, CNAME hoặc tenant bị takeover, phạm vi ảnh hưởng có thể lớn hơn dự kiến.

Khắc phục:

- Ưu tiên host-only cookie.
- Dùng __Host- prefix cho session khi tương thích.
- Tách nội dung user-generated và app nhạy cảm sang site riêng.
- Kiểm tra DNS, CNAME và subdomain inventory.
- Thu hồi session nếu cookie có thể đã được gửi tới host bị compromise.

### 9.3 Thiếu Secure hoặc HTTP endpoint còn hoạt động

Secure cookie không được browser gửi qua HTTP theo quy tắc thông thường. Nhưng nếu ứng dụng vẫn cho phép HTTP, attacker có thể khai thác downgrade, mixed content hoặc redirect không an toàn tùy cấu hình.

Khắc phục:

- Chuyển toàn bộ ứng dụng sang HTTPS.
- Bật HSTS sau khi xác minh subdomain và rollout.
- Redirect HTTP sang HTTPS ở edge.
- Không phục vụ form/login/session endpoint qua HTTP.
- Kiểm tra cookie Secure ở response thật, không chỉ config code.

### 9.4 Cookie hoặc token lọt vào URL

Không đặt session ID hoặc refresh token trong query string, path hay fragment để xác thực. URL có thể xuất hiện trong browser history, Referer, analytics, reverse proxy logs và screenshot.

Nếu phát hiện token trong URL:

1. Revoke mọi token đã xuất hiện.
2. Xác định log, analytics và third-party nào đã nhận URL.
3. Xóa hoặc hạn chế truy cập log theo retention policy.
4. Vá flow để dùng cookie/header phù hợp.
5. Thêm Referrer-Policy phù hợp cho dữ liệu nhạy cảm, nhưng không coi nó thay thế việc bỏ token khỏi URL.

### 9.5 Logs, traces và support tooling

Kiểm tra log middleware có ghi toàn bộ request headers không. Redact Cookie, Set-Cookie, Authorization và token fields trước khi ghi log. APM/tracing cũng có thể thu thập header hoặc body.

Đối với sự cố đã xảy ra, xác định ai có quyền đọc log và liệu credential đã được copy sang hệ thống khác. Chỉ xóa bản ghi theo quy trình evidence/legal hold; tránh phá hủy bằng chứng cần điều tra.

### 9.6 Endpoint bị malware hoặc extension độc hại

Nếu thiết bị người dùng bị compromise, cookie có thể bị lấy từ browser profile hoặc dùng trực tiếp trong browser. Phối hợp endpoint security để cô lập/clean thiết bị, revoke session và kiểm tra đăng nhập mới sau khi thiết bị sạch.

Không yêu cầu người dùng gửi browser profile, cookie database hoặc raw cookie qua email. Thu thập forensic artifact theo quy trình endpoint response được phê duyệt.

## 10. Hardening cookie và session sau sự cố

### 10.1 Cookie cấu hình tối thiểu

Ví dụ cho session cookie trên một ứng dụng HTTPS:

~~~http
Set-Cookie: __Host-session=RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Đánh giá thêm:

- Max-Age/Expires ngắn phù hợp với rủi ro.
- Idle timeout và absolute timeout ở server.
- Không có Domain nếu không cần chia sẻ subdomain.
- Cookie value không chứa PII hoặc quyền nghiệp vụ.
- Không dùng session ID trong URL.
- Không ghi cookie vào logs.

### 10.2 Idle timeout và absolute timeout

Idle timeout kết thúc session sau một khoảng không có hoạt động phù hợp. Absolute timeout giới hạn tổng tuổi session kể cả khi người dùng hoạt động liên tục.

Thời gian nên dựa trên sensitivity, risk và UX. Với thao tác nhạy cảm, yêu cầu re-authentication hoặc step-up MFA thay vì chỉ dựa vào session còn sống.

### 10.3 Rotate session ID sau authentication và privilege change

Sau login, MFA, password change hoặc role elevation:

- Tạo ID mới bằng CSPRNG.
- Gắn ID mới với user/session context.
- Revoke ID cũ.
- Cập nhật cookie.
- Audit sự kiện rotate.
- Không cho phép session ID do client tự chọn.

### 10.4 CSRF defense nhiều lớp

Cookie tự động được browser gửi nên session-based app cần CSRF defense phù hợp:

- SameSite=Lax/Strict theo flow.
- CSRF token gắn với session hoặc cơ chế double-submit được thiết kế đúng.
- Kiểm tra Origin/Referer cho unsafe methods khi phù hợp.
- Fetch Metadata như Sec-Fetch-Site để bổ sung policy.
- Re-auth/step-up cho hành động nhạy cảm.
- Không dùng GET để thay đổi trạng thái.

SameSite là defense-in-depth. XSS trong same-origin có thể vượt qua nhiều CSRF defense phía client; server vẫn cần kiểm soát quyền và input.

### 10.5 Không bind session cứng vào IP hoặc User-Agent

IP và User-Agent hữu ích cho detection, nhưng có thể thay đổi hợp lệ hoặc bị giả mạo. Binding cứng có thể khóa người dùng di động và không ngăn attacker dùng cùng mạng/proxy.

Dùng tín hiệu để tăng risk score, yêu cầu re-auth hoặc alert; không coi IP/UA là bằng chứng mật mã về thiết bị.

### 10.6 Session inventory và user controls

Cung cấp trang quản lý session có:

- Danh sách thiết bị/phiên ở mức mô tả an toàn.
- Thời điểm tạo và hoạt động gần nhất.
- Nút revoke một session.
- Nút logout all sessions.
- Cảnh báo đăng nhập mới và thay đổi MFA.
- Không hiển thị session ID hoặc raw cookie.

## 11. Lab: mô phỏng server-side session revocation

Lab Node.js dưới đây tạo một session giả lập trong bộ nhớ, phát cookie demo, xác thực request và revoke session khi logout. Mục tiêu là chứng minh rằng cookie đã sao chép vẫn bị từ chối sau khi server đánh dấu session revoked.

Lab không có đăng nhập thật, không sử dụng tài khoản người dùng và không đọc cookie của browser ngoài localhost. Cookie trong lab bỏ Secure để có thể chạy trên HTTP localhost; production phải bật Secure và HTTPS.

### 11.1 Cấu trúc thư mục

~~~text
cookie-compromise-lab/
  server.mjs
~~~

### 11.2 Tạo server.mjs

~~~js
import { createServer } from "node:http";
import { randomBytes, createHmac } from "node:crypto";

const sessions = new Map();
const auditKey = randomBytes(32);
const cookieName = "lab_session";
const maxAgeSeconds = 1800;

function fingerprint(sessionId) {
  return createHmac("sha256", auditKey)
    .update(sessionId)
    .digest("hex")
    .slice(0, 20);
}

function readCookie(req, name) {
  const raw = req.headers.cookie || "";
  const matches = raw.split(";").map(part => part.trim())
    .filter(part => part.startsWith(name + "="));

  // Từ chối cookie trùng tên để tránh parsing ambiguity trong lab.
  if (matches.length !== 1) return null;

  return matches[0].slice(name.length + 1);
}

function sendJson(res, status, body, headers = {}) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    ...headers
  });
  res.end(JSON.stringify(body));
}

function authenticate(req) {
  const sessionId = readCookie(req, cookieName);
  if (!sessionId) return null;

  const sessionFingerprint = fingerprint(sessionId);
  const session = sessions.get(sessionFingerprint);
  if (!session) return null;
  if (session.revokedAt) return null;
  if (session.expiresAt <= Date.now()) return null;

  return { sessionFingerprint, session };
}

const server = createServer((req, res) => {
  const url = new URL(req.url || "/", "http://localhost:3000");

  if (req.method === "POST" && url.pathname === "/lab/login") {
    const sessionId = randomBytes(32).toString("base64url");

    const session = {
      userId: "demo-user",
      createdAt: Date.now(),
      expiresAt: Date.now() + maxAgeSeconds * 1000,
      revokedAt: null
    };

    sessions.set(fingerprint(sessionId), session);

    console.log("[session-created]", {
      fingerprint: fingerprint(sessionId),
      userId: session.userId
    });

    return sendJson(res, 201, {
      authenticated: true,
      note: "Demo session created; raw cookie is not logged."
    }, {
      "Set-Cookie":
        cookieName + "=" + sessionId +
        "; Path=/; HttpOnly; SameSite=Lax; Max-Age=" + maxAgeSeconds
    });
  }

  if (req.method === "GET" && url.pathname === "/lab/me") {
    const auth = authenticate(req);

    if (!auth) {
      return sendJson(res, 401, { authenticated: false });
    }

    return sendJson(res, 200, {
      authenticated: true,
      userId: auth.session.userId,
      expiresAt: new Date(auth.session.expiresAt).toISOString()
    });
  }

  if (req.method === "POST" && url.pathname === "/lab/logout") {
    const auth = authenticate(req);

    if (auth) {
      auth.session.revokedAt = Date.now();

      console.log("[session-revoked]", {
        fingerprint: auth.sessionFingerprint,
        reason: "logout"
      });
    }

    return sendJson(res, 200, {
      authenticated: false,
      revoked: Boolean(auth)
    }, {
      "Set-Cookie":
        cookieName + "=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    });
  }

  if (req.method === "POST" && url.pathname === "/lab/revoke-all") {
    let count = 0;

    for (const session of sessions.values()) {
      if (session.userId === "demo-user" && !session.revokedAt) {
        session.revokedAt = Date.now();
        count += 1;
      }
    }

    return sendJson(res, 200, {
      revokedSessions: count
    });
  }

  if (req.method === "GET" && url.pathname === "/lab/admin") {
    const auth = authenticate(req);

    if (!auth) {
      return sendJson(res, 401, { error: "Session is invalid or revoked" });
    }

    return sendJson(res, 200, {
      result: "Authorized demo operation",
      userId: auth.session.userId
    });
  }

  return sendJson(res, 404, { error: "Not found" });
});

server.listen(3000, "localhost", () => {
  console.log("Cookie compromise lab: http://localhost:3000");
});
~~~

### 11.3 Chạy lab

Từ thư mục cookie-compromise-lab:

~~~bash
node server.mjs
~~~

Mở một terminal khác. Dùng cookie jar riêng cho lab:

~~~bash
curl -i -c cookie-before-revoke.txt -X POST http://localhost:3000/lab/login
~~~

Kiểm tra session:

~~~bash
curl -i -b cookie-before-revoke.txt http://localhost:3000/lab/me
~~~

Endpoint trả authenticated=true. Giả lập việc cookie bị sao chép bằng cách giữ nguyên cookie jar trước revoke trong môi trường lab. Không làm thao tác này với cookie thật.

### 11.4 Revoke session và thử replay

Gửi logout với cookie jar:

~~~bash
curl -i -b cookie-before-revoke.txt -c cookie-after-logout.txt -X POST http://localhost:3000/lab/logout
~~~

Dùng cookie jar cũ để mô phỏng attacker vẫn giữ bản sao cookie:

~~~bash
curl -i -b cookie-before-revoke.txt http://localhost:3000/lab/me
~~~

Kết quả mong đợi là HTTP 401. Server từ chối session vì record đã có revokedAt, dù cookie value vẫn còn trong cookie jar cũ.

Đây là điểm cốt lõi của containment: server-side revocation vô hiệu credential đã sao chép.

### 11.5 Thử revoke all

Tạo session demo mới rồi gọi:

~~~bash
curl -i -X POST http://localhost:3000/lab/revoke-all
~~~

Các cookie demo trước đó của user demo-user đều bị từ chối ở /lab/me. Endpoint revoke-all không có authentication vì lab chạy cục bộ; tuyệt đối không triển khai endpoint tương tự công khai mà không có authorization và audit.

### 11.6 Dọn lab

- Dừng server bằng Ctrl+C.
- Xóa hai cookie jar demo nếu không cần nữa.
- Không dùng cookie jar của ứng dụng thật trong bài thực hành.
- Không expose server lab ra mạng LAN hoặc Internet.

## 12. Checklist containment theo thời gian

### 12.1 15 phút đầu

- [ ] Mở incident record và ghi thời điểm phát hiện.
- [ ] Xác định session/account nghi bị compromise.
- [ ] Revoke session nghi vấn ở server.
- [ ] Nếu có dấu hiệu nhiều session, revoke toàn bộ session của account.
- [ ] Nếu key/store bị lộ, kích hoạt quy trình diện rộng.
- [ ] Bảo toàn auth/session audit logs.
- [ ] Không copy raw cookie/token vào ticket hoặc chat.
- [ ] Kiểm tra hành động nhạy cảm gần thời điểm lộ.

### 12.2 Trong giờ đầu

- [ ] Xác định nguồn lộ có thể xảy ra.
- [ ] Kiểm tra XSS, Domain scope, TLS, logs, endpoint malware và refresh-token reuse.
- [ ] Xác định session/token family và downstream services bị ảnh hưởng.
- [ ] Thu hồi refresh token hoặc key nếu có căn cứ.
- [ ] Yêu cầu xác thực lại theo risk.
- [ ] Tạm dừng feature dễ bị khai thác nếu cần.
- [ ] Phân công owner cho evidence, containment và communication.

### 12.3 Trong ngày đầu

- [ ] Vá nguyên nhân gốc và kiểm thử regression.
- [ ] Xác nhận mọi node/service từ chối credential cũ.
- [ ] Kiểm tra session mới được phát hành an toàn.
- [ ] Đánh giá dữ liệu bị xem/sửa/xuất.
- [ ] Xác định nghĩa vụ thông báo và retention.
- [ ] Theo dõi replay và refresh-token reuse.
- [ ] Chuẩn bị recovery support cho người dùng.

### 12.4 Sau sự cố

- [ ] Hoàn tất timeline và evidence index.
- [ ] Đo thời gian phát hiện, containment và recovery.
- [ ] Kiểm tra cookie attributes trên response thực tế.
- [ ] Kiểm tra session rotation, expiry và revocation.
- [ ] Kiểm tra log redaction ở proxy/APM/SIEM.
- [ ] Cập nhật alert và playbook.
- [ ] Diễn tập lại tình huống cookie replay.
- [ ] Theo dõi action item đến khi đóng.

## 13. Chẩn đoán và lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Người dùng logout nhưng attacker vẫn truy cập | Chỉ xóa cookie phía client, session chưa revoke | Invalidate session ở server |
| Set-Cookie expire nhưng session cũ còn dùng được | Cookie đã được attacker copy | Revoke server-side; cookie clearing không đủ |
| Chỉ một subdomain bị compromise nhưng nhiều app bị ảnh hưởng | Cookie Domain quá rộng | Thu hẹp scope, host-only cookie, kiểm tra subdomain |
| HttpOnly bật nhưng vẫn có hành động trái phép | XSS gửi request same-origin bằng cookie tự động | Vá XSS, revoke session và điều tra action logs |
| SameSite=Lax nhưng session bị replay từ máy khác | SameSite không chống bearer-token replay | Revoke token/session |
| JWT còn hợp lệ sau logout | Verifier không kiểm tra revocation/version | jti denylist, session version, introspection hoặc expiry ngắn |
| Rotate signing key gây logout toàn bộ | Key rotation có phạm vi global | Đánh giá blast radius và chuẩn bị rollout/re-auth |
| Revoke session nhưng một số node vẫn chấp nhận | Cache hoặc replication delay | Invalidation, version check và đo revoke propagation |
| Xóa cookie không thành công | Domain/Path không khớp hoặc HttpOnly | Gửi Set-Cookie đúng scope từ server |
| Session ID xuất hiện trong logs | Proxy/APM ghi raw Cookie header | Redact pipeline, đánh giá ai đã truy cập log |
| IP đổi liên tục gây false positive | VPN, NAT, mobile network hoặc roaming | Kết hợp nhiều tín hiệu, không dùng IP đơn lẻ |
| Refresh token cũ vẫn dùng được | Rotation không revoke token cũ hoặc reuse detection thiếu | Revoke token family và kiểm thử replay |
| Session fixation sau login | Không rotate ID sau authentication | Tạo ID mới và revoke ID trước login |
| Clear-Site-Data đăng xuất nhiều ứng dụng | Phạm vi cookie rộng hơn dự kiến | Dùng có kiểm soát; ưu tiên clear đúng cookie scope |

## 14. Ma trận kiểm thử sau khắc phục

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| C01 | Session hợp lệ truy cập endpoint bảo vệ | HTTP 200 |
| C02 | Session đã revoked replay lại | HTTP 401/unauthenticated |
| C03 | Session hết hạn replay lại | HTTP 401/unauthenticated |
| C04 | Logout rồi gửi lại cookie cũ | Server từ chối |
| C05 | Revoke all account sessions | Mọi session cũ của account bị từ chối |
| C06 | Đăng nhập mới sau revoke | Server phát session ID mới |
| C07 | Session ID trước login được dùng lại | Bị từ chối sau rotation |
| C08 | Cookie không có Secure trên production HTTPS | Test cấu hình thất bại |
| C09 | Session cookie có HttpOnly | document.cookie không đọc được cookie |
| C10 | Session cookie có SameSite policy đã chọn | Cross-site behavior đúng thiết kế |
| C11 | Cookie host-only | Không gửi tới subdomain khác |
| C12 | Cookie __Host- | Secure, Path=/ và không có Domain |
| C13 | Cookie trùng tên ở nhiều Path | Server xử lý ambiguity an toàn |
| C14 | Raw Cookie header đi qua proxy log | Log đã redacted |
| C15 | JWT jti bị revoke | Verifier từ chối token |
| C16 | Signing key bị rotate | Token ký bằng key bị compromise bị từ chối |
| C17 | Refresh token cũ được replay | Token family bị revoke theo policy |
| C18 | Session version tăng | Token/session version cũ bị từ chối |
| C19 | XSS thử đọc HttpOnly cookie | Script không đọc được giá trị cookie |
| C20 | XSS gửi request cùng origin | Detection/mitigation vẫn hoạt động; HttpOnly không được coi là đủ |
| C21 | CSRF request từ site khác | Request bị chặn bởi defense đã thiết kế |
| C22 | Request sau logout đang chạy | Hành động nhạy cảm có kiểm tra trạng thái trước commit nếu yêu cầu |
| C23 | Session store replication delay | Revoke propagation nằm trong SLA |
| C24 | Cookie clear sai Path/Domain | Test phát hiện cookie cũ còn tồn tại |
| C25 | User logout/login account khác | Không giữ session hoặc dữ liệu account trước |
| C26 | Incident evidence export | Không có raw cookie/token trong artifact |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao xóa cookie ở browser không đủ xử lý cookie compromise?

**Đáp án:** Attacker có thể đã sao chép cookie. Nếu server vẫn chấp nhận session ID, attacker vẫn replay được. Cần revoke session ở server.

**Câu 2.** HttpOnly có ngăn XSS thực hiện request đã xác thực không?

**Đáp án:** Không. HttpOnly ngăn JavaScript đọc cookie qua document.cookie, nhưng browser vẫn tự gửi cookie trong request phù hợp.

**Câu 3.** SameSite có ngăn cookie bị replay từ máy khác không?

**Đáp án:** Không. SameSite chủ yếu kiểm soát gửi cookie trong cross-site context; nó không vô hiệu bearer credential đã bị sao chép.

**Câu 4.** Khi nào cần revoke tất cả session của tài khoản?

**Đáp án:** Khi có bằng chứng account compromise, phạm vi session không xác định, refresh-token family bị lộ hoặc risk policy yêu cầu. Nếu chỉ một session bị ảnh hưởng và có thể xác định chắc chắn, có thể revoke session đó rồi tăng giám sát.

**Câu 5.** Khi nào cần rotate signing key?

**Đáp án:** Khi signing key bị lộ hoặc có căn cứ rằng attacker có thể ký token giả. Chỉ lộ một JWT/session cookie không tự động chứng minh signing key bị compromise.

**Câu 6.** Session fixation được ngăn bằng cách nào?

**Đáp án:** Tạo session ID mới sau authentication hoặc thay đổi privilege, đồng thời revoke ID cũ và không chấp nhận ID do client tự chọn.

**Câu 7.** Vì sao không log raw session ID?

**Đáp án:** Log có thể bị nhiều người/hệ thống truy cập. Raw session ID trong log trở thành credential có thể replay; dùng fingerprint HMAC để correlation.

**Câu 8.** Refresh token reuse là tín hiệu gì?

**Đáp án:** Có thể cho thấy token cũ đã bị sao chép hoặc client retry sai. Hệ thống rotation cần phát hiện reuse và revoke family theo policy.

**Câu 9.** Clear-Site-Data có thay thế server revocation không?

**Đáp án:** Không. Header chỉ yêu cầu browser xóa dữ liệu trong phạm vi áp dụng; bản cookie đã sao chép vẫn có thể được attacker dùng.

**Câu 10.** Vì sao IP/UA không nên là session binding cứng?

**Đáp án:** Chúng có thể thay đổi hợp lệ và bị giả mạo. Dùng như tín hiệu risk, không phải bằng chứng mật mã về client.

## 16. Checklist hardening và readiness

### Cookie và browser

- [ ] Session cookie có Secure trong production.
- [ ] Session cookie có HttpOnly.
- [ ] Chọn SameSite theo flow và CSRF threat model.
- [ ] Ưu tiên host-only cookie, bỏ Domain khi không cần.
- [ ] Dùng __Host- prefix khi phù hợp.
- [ ] Path không được coi là ranh giới cô lập bảo mật.
- [ ] Không đặt session/token trong URL.
- [ ] Không dùng document.cookie để quản lý HttpOnly session.

### Session server

- [ ] Session ID dùng CSPRNG với entropy đủ lớn.
- [ ] Rotate ID sau login/MFA/privilege change.
- [ ] Revoke ID cũ khi rotate.
- [ ] Có idle timeout và absolute timeout.
- [ ] Revoke một session và tất cả session theo account.
- [ ] Có session version hoặc revocation store phù hợp.
- [ ] Đo thời gian propagation giữa các node.
- [ ] Logout invalidates server-side session.

### Token và secret

- [ ] Access token lifetime phù hợp.
- [ ] Có jti/session version/introspection nếu cần revoke.
- [ ] Refresh token rotation và reuse detection.
- [ ] Signing key được quản lý trong secret manager/KMS.
- [ ] Có quy trình key rotation khẩn cấp.
- [ ] Key compromise dẫn tới từ chối token ký bằng key bị lộ.
- [ ] Không rotate secret không liên quan nếu chưa có căn cứ.

### Detection và incident response

- [ ] Auth/session audit log có correlation ID.
- [ ] Không log Cookie, Set-Cookie hoặc Authorization thô.
- [ ] Session fingerprint dùng HMAC với key riêng.
- [ ] Alert cho replay, impossible travel kết hợp tín hiệu khác và refresh-token reuse.
- [ ] Có runbook revoke session và global revoke.
- [ ] Bảo toàn evidence trước khi cleanup theo legal/evidence policy.
- [ ] Có quy trình đánh giá data access và user notification.
- [ ] Có post-incident action owner và deadline.

**Ghi nhớ:** Cookie compromise là sự cố credential/session. Thu hồi ở server làm mất hiệu lực bản cookie đã sao chép; xóa cookie ở browser chỉ dọn bản lưu tại client. Phải xác định chính xác session, token family và key nào bị ảnh hưởng, bảo toàn bằng chứng không chứa credential thô, loại bỏ nguồn lộ rồi xác minh replay cũ không còn thành công.

## Tài liệu tham khảo

- [RFC 6265bis — Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/)
- [MDN — HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Session Hijacking Attack](https://owasp.org/www-community/attacks/Session_hijacking_attack)
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [OWASP — Cross Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP — JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [MDN — Clear-Site-Data header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- [MDN — Cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies#cookie_prefixes)

