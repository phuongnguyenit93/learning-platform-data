# Thiết bị đã biết — Tín hiệu thiết bị trong ngữ cảnh xác thực

> **Chương:** Authentication context  
> **Chủ đề:** Thiết bị đã biết  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách hệ thống nhận biết thiết bị từng được sử dụng hoặc đăng ký, phân biệt tín hiệu thiết bị với yếu tố xác thực, và dùng ngữ cảnh thiết bị để hỗ trợ đánh giá rủi ro mà không biến nhận diện thiết bị thành quyền truy cập mặc định.

## 1. Thiết bị đã biết là gì?

**Thiết bị đã biết (known device)** là thiết bị hoặc môi trường client mà hệ thống có đủ tín hiệu để liên hệ với một lần sử dụng, đăng ký hoặc xác minh trước đó. Khi người dùng đăng nhập lại từ thiết bị này, hệ thống có thể nhận thấy một số thuộc tính tương đồng với dữ liệu đã lưu, chẳng hạn cookie ghi nhớ, khóa thiết bị đã đăng ký, chứng chỉ thiết bị hoặc tín hiệu quản lý thiết bị doanh nghiệp.

Ví dụ, Mai thường đăng nhập vào cổng học tập bằng laptop cá nhân. Sau lần đăng nhập thành công và xác minh bổ sung, ứng dụng có thể ghi nhận một thiết bị đã đăng ký. Lần sau, trình duyệt gửi cookie ghi nhớ hoặc chứng minh quyền sở hữu khóa đã đăng ký. Hệ thống dùng thông tin đó như một tín hiệu ngữ cảnh để quyết định có cần MFA bổ sung hay không.

**Thiết bị đã biết không tự động có nghĩa là người đang dùng thiết bị là đúng chủ tài khoản.** Laptop có thể được cho mượn, bị đánh cắp, dùng chung, cài mã độc hoặc bị chiếm phiên. Thiết bị quen thuộc có thể làm giảm một phần bất định về môi trường, nhưng không thay thế credential, xác thực người dùng, kiểm tra phiên hay authorization.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích ý nghĩa và giới hạn của trạng thái known device.
2. Phân biệt thiết bị đã biết, thiết bị tin cậy, thiết bị được quản lý và authenticator.
3. Nhận diện các cách ghi nhớ thiết bị: cookie, khóa mật mã, chứng chỉ và device-management signal.
4. Thiết kế quy trình đăng ký, xác minh, đổi tên, thu hồi và hết hạn thiết bị.
5. Dùng tín hiệu thiết bị trong risk-based authentication mà không bỏ qua policy xác thực.
6. Hiểu rủi ro của fingerprinting, tracking, cookie theft, device spoofing và thiết bị dùng chung.
7. Tích hợp known device với MFA, passkey, session, tenant và recovery.
8. Xây dựng kiểm thử cho thiết bị mới, thiết bị mất, tín hiệu giả và trạng thái thiết bị bị thu hồi.

## 2. Known device, trusted device và managed device

Các nhãn này không nên được dùng thay thế cho nhau:

| Khái niệm | Ý nghĩa | Bằng chứng thường có | Giới hạn |
| --- | --- | --- | --- |
| **Known device** | Hệ thống nhận ra thiết bị hoặc môi trường từng xuất hiện | Cookie, khóa đã đăng ký, dấu hiệu tương đồng | Có thể bị sao chép, giả mạo hoặc dùng chung. |
| **Trusted device** | Thiết bị được cấp trạng thái tin cậy theo policy | Enrollment đã xác minh, khóa ràng buộc, phê duyệt | Trạng thái tin cậy có thời hạn và có thể bị thu hồi. |
| **Managed device** | Thiết bị nằm dưới hệ thống quản lý của tổ chức | MDM/UEM, compliance state, device certificate | Quản lý không chứng minh người dùng cụ thể đang thao tác. |
| **Authenticator** | Thành phần giữ credential và thực hiện xác thực | Passkey, security key, authenticator app, certificate key | Phải xác minh đúng ceremony và policy. |
| **Device fingerprint** | Tập thuộc tính dùng để ước lượng client/device | Browser, OS, screen, network và các tín hiệu khác | Không ổn định, có thể giả mạo, có thể xâm phạm riêng tư. |

Một thiết bị có thể đã biết nhưng không được quản lý. Một thiết bị được quản lý có thể mới đối với ứng dụng. Một thiết bị có thể giữ passkey nhưng ứng dụng không nhất thiết có đủ bằng chứng để gọi toàn bộ thiết bị là trusted.

**Tên trạng thái phải phản ánh bằng chứng thực tế.** Nếu hệ thống chỉ có cookie đã từng xuất hiện, nên gọi đó là remembered browser hoặc recognized browser; không nên quảng bá nó như thiết bị đã được xác minh bằng phần cứng.

## 3. Thiết bị đã biết là tín hiệu ngữ cảnh, không phải yếu tố xác thực độc lập

Authentication context mô tả hoàn cảnh và thuộc tính của lần xác thực: thời điểm, phương thức, thiết bị, vị trí tương đối, mức rủi ro và các điều kiện policy. Known device là một tín hiệu có thể đóng góp vào ngữ cảnh đó.

Một tín hiệu thiết bị thường trả lời: **“Client này có giống một môi trường đã thấy trước đây không?”** Nó không tự trả lời:
- Ai đang cầm thiết bị?
- Người đó có kiểm soát account hợp pháp không?
- Thiết bị có bị malware hoặc remote-control không?
- Session hiện tại có bị đánh cắp không?
- Người dùng đã hoàn tất yếu tố MFA bắt buộc chưa?

Không nên cộng known device như một yếu tố độc lập trong MFA chỉ vì cookie tồn tại. Nếu cookie và session cùng bị đánh cắp từ một browser profile, chúng có thể bị chiếm cùng lúc. Tính độc lập của yếu tố phải được đánh giá theo cách credential được tạo, lưu và sử dụng.

| Tín hiệu | Có thể hỗ trợ điều gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| Cookie ghi nhớ còn hợp lệ | Browser đã từng hoàn tất flow ghi nhớ | Người dùng hiện tại là chủ tài khoản. |
| Device fingerprint tương đồng | Môi trường client có đặc điểm giống lần trước | Thiết bị là duy nhất hoặc không bị giả mạo. |
| Device certificate hợp lệ | Client giữ private key tương ứng với chứng chỉ | Người đang dùng thiết bị là một cá nhân cụ thể. |
| Passkey assertion hợp lệ | Authenticator đã ký challenge cho RP theo WebAuthn | Mọi dữ liệu trên thiết bị đều sạch hoặc được quản lý. |
| MDM compliance signal | Thiết bị đáp ứng trạng thái quản lý được báo cáo | Mọi ứng dụng và phiên trên thiết bị đều an toàn. |

## 4. Các cách nhận biết thiết bị

Không có một kỹ thuật duy nhất phù hợp cho mọi ứng dụng. Các cách thường gặp có mức bảo đảm, khả năng triển khai và rủi ro riêng.

### 4.1. Remembered-device cookie

Sau khi người dùng đăng nhập và hoàn tất xác minh theo policy, server tạo một giá trị ngẫu nhiên dài hạn có thời hạn, gửi bằng cookie và lưu digest hoặc bản tham chiếu ở server. Lần sau cookie được gửi lại, server có thể liên hệ browser với bản ghi thiết bị đã ghi nhớ.

Ưu điểm là dễ triển khai trên web. Giới hạn là cookie là bearer secret: nếu bị đánh cắp, attacker có thể sao chép nó sang môi trường khác. Cookie có thể bị xóa, trình duyệt có thể đổi profile, hoặc browser update có thể làm tín hiệu khác đi.

### 4.2. Khóa thiết bị hoặc public-key binding

Trong một flow đăng ký, client tạo cặp khóa hoặc sử dụng authenticator đã có. Server lưu public key và một định danh credential. Khi cần xác nhận thiết bị, server phát challenge mới; client ký challenge bằng private key. Server kiểm tra chữ ký, challenge, audience, expiry và trạng thái credential.

Cách này có thể cung cấp bằng chứng sở hữu khóa mạnh hơn cookie. Tuy nhiên, cần xác định private key được bảo vệ ở đâu, có thể export/sync không, ai có thể kích hoạt nó và quy trình revoke ra sao. Chữ ký hợp lệ chứng minh quyền kiểm soát khóa trong ceremony, không tự chứng minh người dùng đang dùng thiết bị là ai.

### 4.3. Device certificate

Trong môi trường doanh nghiệp, thiết bị có thể được cấp chứng chỉ client X.509. Server kiểm tra certificate chain, EKU, subject/SAN, thời hạn và trạng thái thu hồi. Chứng chỉ có thể hỗ trợ mTLS hoặc xác minh thiết bị thuộc tổ chức.

Chứng chỉ thiết bị cần inventory, CA governance, bảo vệ private key, rotation và revocation. Certificate hợp lệ không tự cấp quyền ứng dụng; server vẫn ánh xạ thiết bị tới principal/device record và kiểm tra user account, tenant, role.

### 4.4. MDM/UEM và device posture

Hệ thống quản lý thiết bị có thể cung cấp trạng thái như enrolled, compliant, encrypted, OS version hoặc jailbreak/root detection. Ứng dụng chỉ nên tin signal từ connector/service đã xác minh, có thời điểm và scope rõ ràng. Không nhận một trường do browser tự khai như deviceCompliant=true.

Device posture có thể cũ hoặc không sẵn có. Policy cần kiểm tra freshness, nguồn, tenant, device ID và cách xử lý outage. Một thiết bị compliant vào buổi sáng có thể đã thay đổi trạng thái vào buổi chiều.

### 4.5. Fingerprinting

Fingerprinting tổng hợp thuộc tính browser, OS, timezone, fonts, screen, network hoặc tín hiệu khác để tạo một ước lượng về tính liên tục của client. Nó hữu ích như một tín hiệu rủi ro phụ trợ nhưng không phải định danh mật mã. Thuộc tính có thể thay đổi sau update, privacy settings, browser reset hoặc VPN; attacker cũng có thể mô phỏng một phần.

Không dùng fingerprint đơn lẻ để bỏ MFA, khóa account hoặc cấp quyền nhạy cảm. Cần cân nhắc tracking xuyên dịch vụ, tính minh bạch, cơ sở xử lý dữ liệu và tối thiểu hóa thông tin thu thập.

## 5. Quy trình đăng ký thiết bị đã biết

Thiết bị chỉ nên được ghi nhớ sau khi hệ thống xác minh rằng người yêu cầu có quyền gắn thiết bị đó với account. Nếu attacker đã chiếm một phiên yếu và có thể tự thêm thiết bị tin cậy, mọi lần đăng nhập sau có thể trở nên dễ dàng hơn cho attacker.

Một quy trình điển hình:

1. Người dùng đăng nhập bằng phương thức được policy chấp nhận.
2. Nếu cần, yêu cầu MFA hoặc step-up trước khi ghi nhớ thiết bị.
3. Hiển thị rõ lựa chọn “Ghi nhớ thiết bị này” và giải thích tác động/thời hạn.
4. Tạo device record với ID nội bộ ngẫu nhiên.
5. Tạo cookie ghi nhớ hoặc hoàn tất public-key/device-key enrollment.
6. Gắn device record với account, tenant scope, loại bằng chứng và thời điểm.
7. Ghi audit và thông báo qua kênh liên hệ đã xác minh.
8. Cho phép người dùng xem, đổi tên và thu hồi thiết bị trong trang bảo mật.

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Browser / Device
    participant A as Authentication Service
    participant D as Device Registry
    U->>B: Đăng nhập và chọn ghi nhớ thiết bị
    B->>A: Authentication result + request enrollment
    A->>A: Kiểm tra account, MFA/step-up và policy
    A->>B: Challenge hoặc device enrollment instruction
    B->>A: Proof / cookie registration response
    A->>A: Xác minh transaction và bằng chứng
    A->>D: Tạo device record gắn account
    A-->>U: Xác nhận thiết bị đã được ghi nhớ
~~~

### Không ghi nhớ thiết bị từ một request chưa xác thực

Không tạo trusted-device record chỉ vì client gửi một UUID hoặc fingerprint. Enrollment phải gắn với phiên đã xác thực và giao dịch có thời hạn. Nếu policy yêu cầu step-up, chỉ ghi nhận sau khi step-up hoàn tất.

### Ghi nhớ có phạm vi

Thiết bị có thể được ghi nhớ cho một account, một tenant hoặc một ứng dụng. Không tự động chia sẻ trạng thái trusted giữa các tenant hoặc giữa các dịch vụ độc lập. Cùng một browser có thể dùng nhiều account; device record cần thể hiện scope rõ ràng.

## 6. Device registry: dữ liệu cần lưu

Server nên giữ một bản ghi thiết bị có trạng thái và provenance rõ ràng. Ví dụ schema khái niệm:

~~~json
{
  "deviceId": "dev-opaque-4821",
  "accountId": "account-1742",
  "tenantId": "tenant-campus",
  "label": "Laptop cá nhân",
  "recognitionMethod": "PUBLIC_KEY",
  "credentialReference": "device-key-93",
  "firstSeenAt": "2026-11-22T09:00:00Z",
  "lastSeenAt": "2026-11-22T10:15:00Z",
  "enrolledAt": "2026-11-22T09:05:00Z",
  "expiresAt": "2027-02-22T09:05:00Z",
  "lastVerifiedAt": "2026-11-22T10:15:00Z",
  "status": "ACTIVE",
  "riskState": "NORMAL"
}
~~~

Đây là ví dụ minh họa. Tùy cơ chế, bản ghi có thể lưu digest của cookie, public key, certificate fingerprint hoặc tham chiếu tới MDM device ID. Không lưu raw private key, raw cookie secret hoặc dữ liệu fingerprint chi tiết nếu không cần.

Các trường có ý nghĩa:
- **deviceId:** định danh nội bộ opaque, không phải bí mật xác thực.
- **accountId:** account đã xác minh khi enrollment.
- **tenantId:** scope nếu trạng thái chỉ có ý nghĩa trong tenant.
- **recognitionMethod:** loại bằng chứng thực tế, tránh gọi mọi loại là hardware-bound.
- **credentialReference:** tham chiếu khóa/chứng chỉ/cookie record; không phải private key.
- **firstSeenAt/lastSeenAt:** lịch sử quan sát, không phải bằng chứng trust.
- **enrolledAt/lastVerifiedAt:** thời điểm đăng ký và xác minh gần nhất.
- **expiresAt:** thời điểm trạng thái hết hiệu lực theo policy.
- **status:** active, revoked, expired hoặc pending.
- **riskState:** tín hiệu đánh giá rủi ro; không thay thế trạng thái credential.

## 7. Remembered-device cookie an toàn

Nếu dùng cookie để ghi nhớ browser, hãy xem cookie như một credential bearer có thời hạn.

Các nguyên tắc:
- Sinh giá trị ngẫu nhiên bằng CSPRNG, entropy đủ cao.
- Lưu digest/HMAC hoặc token reference ở server thay vì lưu raw cookie value.
- Gắn cookie với account/device record và mục đích riêng.
- Dùng Secure, HttpOnly và SameSite phù hợp.
- Đặt thời hạn hữu hạn và hỗ trợ revoke phía server.
- Không đưa account ID, email hoặc quyền vào cookie.
- Không tái sử dụng session cookie làm remembered-device cookie.
- Không log raw cookie hoặc URL chứa cookie.
- Khi đăng nhập, kiểm tra device record còn active, chưa hết hạn và không bị thu hồi.

Ví dụ:

~~~http
Set-Cookie: __Host-remembered_device=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=7776000
~~~

Thời hạn 90 ngày ở ví dụ chỉ để minh họa. Thời hạn thực tế phải dựa trên rủi ro, loại ứng dụng, khả năng người dùng thu hồi và policy. Cookie tồn tại trên browser không có nghĩa server phải tiếp tục tin nó; server có thể revoke sớm.

### Tách cookie thiết bị khỏi session cookie

Session cookie duy trì phiên hiện tại. Remembered-device cookie ghi nhớ một browser/device để hỗ trợ đánh giá lần đăng nhập sau. Hai cookie có vòng đời, scope và quyền khác nhau. Nếu dùng chung một giá trị, việc logout hoặc đánh cắp session có thể vô tình làm mất hoặc lạm dụng trạng thái ghi nhớ.

## 8. Challenge-response với khóa thiết bị

Một thiết kế dựa trên public key có thể tránh việc coi cookie là bằng chứng duy nhất:

1. Device enrollment tạo cặp khóa.
2. Private key được lưu trong secure storage hoặc authenticator theo khả năng nền tảng.
3. Server lưu public key và gắn với account/device record.
4. Khi cần xác minh, server tạo challenge ngẫu nhiên, ngắn hạn, gắn với transaction, device ID, audience và purpose.
5. Client ký challenge bằng private key.
6. Server kiểm tra chữ ký, challenge, thời hạn, trạng thái credential và binding.
7. Server đánh dấu challenge đã dùng để chống replay.

~~~text
Server -> Device:
  challenge = random(256 bits)
  transaction = login-transaction-882
  purpose = KNOWN_DEVICE_PROOF
  expiresAt = short-lived

Device:
  signature = Sign(privateKey, canonical(challenge, transaction, purpose))

Server:
  Verify(publicKey, signature)
  Check transaction + expiry + one-time use
  Check device record ACTIVE
~~~

Không ký một chuỗi tùy ý do client tự chọn rồi coi đó là bằng chứng thiết bị. Protocol phải định nghĩa canonical bytes, algorithm, key type, challenge binding và replay behavior. Không chấp nhận chữ ký cũ hoặc challenge được dùng lại.

### Khóa có đồng bộ không?

Một số credential có thể được đồng bộ giữa thiết bị thông qua hệ sinh thái nền tảng; một số khóa có thể gắn với phần cứng/thiết bị. Policy phải biết loại bằng chứng mình nhận được. Nếu private key có thể sync, proof chứng minh quyền kiểm soát credential có thể đến từ thiết bị khác trong cùng hệ sinh thái; không nên khẳng định nó chứng minh chính chiếc laptop ban đầu đang hiện diện.

## 9. Fingerprint và giới hạn nhận dạng thiết bị

Fingerprint thường tạo một điểm tương đồng từ nhiều thuộc tính. Nó không phải hardware identity và không phải proof of possession.

Rủi ro:
- browser update làm thay đổi user agent hoặc rendering behavior;
- privacy protection làm giảm hoặc giả lập một số thuộc tính;
- VPN, proxy và mạng di động thay đổi IP;
- nhiều người dùng chung một máy có fingerprint giống nhau;
- attacker có thể sao chép hoặc mô phỏng một phần tín hiệu;
- thu thập quá nhiều thuộc tính có thể tạo tracking xuyên website;
- dữ liệu fingerprint có thể vô tình trở thành dữ liệu cá nhân hoặc nhạy cảm theo luật áp dụng.

Dùng fingerprint như một thành phần risk score với trọng số phù hợp, không làm credential. Tránh chặn người dùng hợp lệ chỉ vì một thuộc tính thay đổi. Nếu cần nhận diện bền vững, cân nhắc khóa thiết bị hoặc chứng chỉ có quản trị thay vì tăng mức thu thập fingerprint.

## 10. Risk-based authentication với known device

Một hệ thống có thể kết hợp nhiều tín hiệu để quyết định hành động xác thực:

- device record active và vừa được xác minh;
- device certificate hoặc public-key proof hợp lệ;
- trạng thái MDM/compliance còn fresh;
- account có lịch sử đăng nhập phù hợp;
- IP/network risk và vị trí tương đối;
- browser/session integrity;
- hành vi bất thường;
- mức nhạy cảm của tài nguyên và hành động.

Ví dụ policy minh họa:

| Tình huống | Quyết định có thể cân nhắc |
| --- | --- |
| Thiết bị đã đăng ký, proof mới hợp lệ, account bình thường | Cho tiếp tục theo authentication policy cơ bản. |
| Cookie ghi nhớ hợp lệ nhưng chưa có proof mạnh | Dùng làm tín hiệu hỗ trợ; vẫn yêu cầu yếu tố bắt buộc. |
| Thiết bị mới, đăng nhập rủi ro thấp | Yêu cầu xác minh theo policy và có thể ghi nhớ sau thành công. |
| Thiết bị mới, hành vi hoặc mạng bất thường | Step-up, trì hoãn hoặc review. |
| Thiết bị đã revoke hoặc certificate revoked | Từ chối proof thiết bị; yêu cầu phương thức khác. |
| Device posture không có hoặc đã cũ | Không suy ra compliant; áp dụng fallback theo rủi ro. |
| Hành động quản trị/tài chính | Yêu cầu assurance mạnh, kể cả trên known device. |

Không dùng điểm risk như phép thay thế xác minh chữ ký hoặc kiểm tra MFA bắt buộc. Risk engine có thể yêu cầu thêm bằng chứng hoặc từ chối; không thể biến proof không hợp lệ thành hợp lệ.

## 11. Known device và MFA

Known device có thể giảm số lần yêu cầu MFA nếu policy cho phép, nhưng phải hiểu bằng chứng nào được dùng và rủi ro còn lại.

Ví dụ:
- Cookie ghi nhớ đơn thuần: có thể giảm friction ở rủi ro thấp, nhưng dễ bị sao chép.
- Khóa thiết bị có challenge-response: cung cấp proof of possession tốt hơn cookie, nhưng không nhất thiết xác minh người dùng đang hiện diện.
- Passkey với User Verification: có thể xác minh người dùng cục bộ theo semantics WebAuthn và ràng buộc RP ID/origin.
- Device certificate + user authentication: có thể kết hợp chứng minh thiết bị và người dùng nếu policy yêu cầu hai điều kiện riêng.

**Không coi “thiết bị quen thuộc” là yếu tố thứ hai mặc định.** Một cookie ghi nhớ và session cookie có thể cùng bị lấy từ một browser profile. Nếu attacker chiếm thiết bị hoặc session, cả hai tín hiệu có thể bị chiếm cùng lúc.

### Step-up theo hành động

Ngay cả trên thiết bị đã biết, có thể yêu cầu xác thực mới khi:
- thêm hoặc xóa passkey;
- đổi email/số điện thoại khôi phục;
- thay đổi MFA;
- xem hoặc xuất dữ liệu nhạy cảm;
- cấp quyền quản trị;
- thay đổi thông tin thanh toán;
- thực hiện thao tác không thể đảo ngược.

## 12. Thiết bị dùng chung và nhiều account

Một máy tính gia đình, kiosk hoặc máy phòng lab có thể được nhiều người dùng. Nếu ứng dụng ghi nhớ thiết bị ở cấp browser mà không scope theo account, người dùng sau có thể thừa hưởng trạng thái của người trước.

Cần:
- scope device record theo account và tenant khi phù hợp;
- không coi browser chung là thiết bị cá nhân đáng tin;
- tránh lưu remembered-device cookie lâu trên kiosk/public computer;
- cung cấp lựa chọn “không ghi nhớ thiết bị này”;
- xóa cookie/local state khi logout trên thiết bị công cộng theo policy;
- cho phép account xem và revoke các thiết bị đã đăng ký;
- không dùng fingerprint để suy đoán cùng thiết bị đồng nghĩa cùng người dùng.

Nếu cùng một thiết bị dùng nhiều account, mỗi account cần có quan hệ và policy riêng. Không chia sẻ device trust giữa các account chỉ vì browser fingerprint giống nhau.

## 13. Mất thiết bị, bị đánh cắp và thu hồi

Trạng thái known/trusted cần có vòng đời. Khi người dùng báo mất laptop hoặc điện thoại:
1. Xác minh yêu cầu thu hồi theo quy trình account recovery.
2. Đánh dấu device record là revoked hoặc lost.
3. Vô hiệu cookie ghi nhớ và credential/device key liên quan.
4. Thu hồi device certificate ở CA nếu có.
5. Thu hồi session và refresh token có thể bị ảnh hưởng.
6. Gỡ hoặc đánh dấu thiết bị trong MDM/UEM nếu tổ chức quản lý.
7. Thông báo qua kênh đã xác minh.
8. Ghi audit và theo dõi lần proof tiếp theo từ thiết bị đó.

Không chỉ xóa thiết bị khỏi danh sách UI. Server phải từ chối mọi proof tiếp theo bằng credential đã revoke. Nếu thiết bị bị mất nhưng session còn hiệu lực, cần xử lý session song song.

### Revoke không nhất thiết xóa audit record

Có thể giữ metadata tối thiểu về thiết bị đã revoke để điều tra và ngăn tái sử dụng, theo retention policy. Không giữ cookie secret hoặc private key chỉ để audit. Bản ghi cần trạng thái, thời điểm, lý do và actor thu hồi.

## 14. Expiry, revalidation và thay đổi thiết bị

Thiết bị đã biết không nên được tin vô thời hạn. Policy có thể yêu cầu:
- expiry sau một thời gian không hoạt động;
- revalidation định kỳ;
- step-up khi device proof đã cũ;
- đăng ký lại sau OS reinstall, browser reset hoặc thay đổi phần cứng;
- revoke khi account đổi credential hoặc phát hiện compromise;
- kiểm tra MDM posture gần thời điểm truy cập;
- giới hạn số thiết bị active cho account theo nhu cầu.

Đổi tên thiết bị không cần tạo credential mới, nhưng thay khóa, certificate hoặc browser cookie có thể cần re-enrollment. Không tự động chuyển trạng thái trusted sang một thiết bị khác chỉ vì user agent hoặc IP giống nhau.

## 15. Tenant và device trust

Trong hệ thống đa tenant, cùng một thiết bị có thể được phép truy cập tenant A nhưng không được phép tenant B. Trạng thái device trust phải có scope rõ.

Các lựa chọn:
- **Account-scoped:** device gắn với account; mỗi request vẫn kiểm tra membership tenant.
- **Tenant-scoped:** device được đăng ký cho account trong một tenant cụ thể.
- **Organization-managed:** MDM/certificate chứng minh thiết bị thuộc tổ chức; tenant mapping được cấu hình và kiểm tra độc lập.

Không nhận tenant ID từ cookie hoặc header rồi tự động coi thiết bị trusted trong tenant đó. Server cần xác định tenant theo flow đã xác minh và kiểm tra membership. Một thiết bị managed của tổ chức cũng không có nghĩa mọi user trên thiết bị đều có quyền truy cập mọi tenant.

## 16. Thiết kế API và server-side verification

Ví dụ API để ghi nhớ thiết bị sau đăng nhập:

~~~http
POST /account/security/devices
Authorization: Bearer <authenticated-session>
Content-Type: application/json

{
  "label": "Laptop cá nhân",
  "recognitionMethod": "PUBLIC_KEY"
}
~~~

Server cần xác định account từ session đã xác minh, kiểm tra reauthentication/step-up, tạo challenge hoặc cookie credential, và chỉ tạo record sau khi bằng chứng được kiểm tra.

Ví dụ response:

~~~json
{
  "deviceId": "dev-opaque-4821",
  "status": "ACTIVE",
  "recognitionMethod": "PUBLIC_KEY",
  "enrolledAt": "2026-11-22T10:15:00Z",
  "expiresAt": "2027-02-22T10:15:00Z"
}
~~~

Không trả credential secret hoặc private key. Nếu dùng cookie, cookie được phát bằng Set-Cookie với attributes phù hợp; không trả raw cookie value trong JSON để JavaScript tự lưu.

Giả mã kiểm tra thiết bị:

~~~java
DeviceDecision evaluateKnownDevice(
        DeviceProof proof,
        AuthenticatedPrincipal principal,
        LoginTransaction transaction) {

    DeviceRecord device =
        deviceRepository.findActive(proof.deviceId(), principal.accountId())
            .orElseThrow(UnknownDeviceException::new);

    transactionPolicy.requireActive(transaction);
    transactionPolicy.requirePurpose(transaction, "KNOWN_DEVICE_PROOF");

    if (device.isExpired(clock.instant()) || device.isRevoked()) {
        throw new UntrustedDeviceException();
    }

    proofVerifier.verifySignature(
        device.publicKey(),
        proof.signature(),
        transaction.challenge(),
        transaction.canonicalContext());

    transactionStore.consumeOnce(transaction.id());

    deviceRepository.updateLastVerifiedAt(
        device.id(), clock.instant());

    return riskPolicy.evaluateDeviceContext(
        principal, device, proof, transaction);
}
~~~

Đây là giả mã minh họa, không phải giao thức hoàn chỉnh. Production cần xác định canonical bytes, algorithm allowlist, challenge entropy, transaction binding, replay cache, key storage, clock policy và concurrency. Không chỉ dựa vào deviceId do client gửi; phải xác minh proof bằng credential gắn với bản ghi server.

## 17. Logging, telemetry và quyền riêng tư

Có thể ghi:
- account ID nội bộ;
- device ID opaque;
- recognition method;
- thời điểm enrollment/verification/revoke;
- trạng thái credential và kết quả policy;
- reason code và correlation ID;
- tenant scope đã xác minh;
- MDM posture source và timestamp khi thực sự cần.

Không log:
- raw remembered-device cookie;
- private key hoặc secret;
- session cookie/access/refresh token;
- raw fingerprint vector hoặc ảnh/video/biometric template;
- dữ liệu thiết bị chi tiết vượt quá mục đích.

Fingerprinting có thể theo dõi người dùng xuyên website hoặc thiết bị. Cần minh bạch, tối thiểu hóa, giới hạn retention và đánh giá pháp lý/quyền riêng tư. Nếu chỉ cần phát hiện thiết bị mới, hãy cân nhắc dùng cookie hoặc credential có mục đích rõ thay vì thu thập hàng chục thuộc tính browser.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Tin fingerprint là định danh duy nhất | Attacker có thể spoof; user hợp lệ bị nhận nhầm | Dùng như risk signal, không phải credential. |
| Ghi nhớ thiết bị trước MFA | Attacker có thể đăng ký thiết bị khi chỉ có yếu tố yếu | Yêu cầu policy/step-up trước enrollment. |
| Dùng session cookie làm remembered cookie | Đánh cắp session đồng thời chiếm trạng thái thiết bị | Tách credential, scope và vòng đời. |
| Cookie không có expiry hoặc revoke | Cookie bị đánh cắp có thể sống lâu | TTL hữu hạn và server-side revoke. |
| Tin deviceId do client khai | Client có thể giả device record khác | Xác minh proof gắn public key/cookie record. |
| Coi known device là MFA factor | Giảm MFA sai policy | Đánh giá tính độc lập và assurance thật. |
| Dùng trạng thái trusted toàn cục | Rò quyền giữa account/tenant | Scope rõ và kiểm tra membership. |
| Không revoke khi mất thiết bị | Thiết bị bị đánh cắp vẫn được nhận diện | Revoke record, key, certificate, session và token liên quan. |
| Không kiểm tra freshness của MDM signal | Dùng trạng thái compliant cũ | Timestamp, max age và policy khi signal stale. |
| Không xử lý browser dùng chung | Người sau thừa hưởng remembered state | Account scoping, kiosk policy và clear flow. |
| Tin client gửi deviceCompliant=true | Có thể giả mạo posture | Chỉ tin connector/device service đã xác thực. |
| Theo dõi fingerprint quá mức | Tracking và rủi ro quyền riêng tư | Data minimization, purpose limitation và retention. |

## 19. Kiểm thử known-device lifecycle

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Đăng nhập hợp lệ, step-up đạt, người dùng chọn ghi nhớ | Tạo device record gắn đúng account. |
| Client gửi device ID chưa đăng ký | Không được coi là known device. |
| Client tự khai deviceCompliant=true | Bỏ qua claim không được xác thực. |
| Cookie ghi nhớ hợp lệ nhưng session không hợp lệ | Không tạo phiên đăng nhập chỉ từ remembered cookie. |
| Cookie hết hạn | Device proof bị từ chối hoặc yêu cầu xác minh lại. |
| Cookie đã revoke ở server | Từ chối dù browser còn cookie. |
| Device-key challenge hợp lệ | Xác minh proof và consume challenge một lần. |
| Chữ ký challenge sai | Từ chối, không cập nhật lastVerifiedAt. |
| Challenge cũ hoặc replay | Từ chối. |
| Hai request cùng challenge đồng thời | Chỉ một request được chấp nhận. |
| Device certificate hết hạn hoặc revoked | Từ chối proof thiết bị. |
| MDM posture stale | Không coi thiết bị compliant; áp dụng fallback policy. |
| Thiết bị bị báo mất | Revoke device credential và session/token liên quan. |
| User đổi password/passkey | Áp dụng policy revalidation/revoke phù hợp. |
| Cùng browser dùng hai account | Không chia sẻ device trust giữa account. |
| Thiết bị dùng chung/kiosk | Không ghi nhớ lâu hoặc áp dụng policy kiosk. |
| Fingerprint thay đổi sau browser update | Không khóa account chỉ dựa trên thay đổi đơn lẻ. |
| IP đổi do VPN/mạng di động | Không coi riêng IP đổi là bằng chứng device mới/attacker. |
| Tenant A revoke device | Không tự động thay đổi tenant B ngoài policy account-wide. |
| Logout local | Session bị revoke; remembered-device record xử lý độc lập theo policy. |
| Known device thực hiện hành động quản trị | Vẫn yêu cầu assurance/step-up bắt buộc. |
| Device registry không khả dụng | Không fail open cho hành động nhạy cảm. |

## 20. Bài tập tình huống

Một ứng dụng doanh nghiệp có nút “Tin cậy thiết bị này trong 90 ngày”. Sau khi người dùng nhập password, ứng dụng đặt cookie ghi nhớ và bỏ MFA trong 90 ngày. Cookie không được lưu trạng thái phía server; logout chỉ xóa session cookie. Người dùng có thể đổi browser fingerprint bằng một extension, còn thiết bị công cộng trong phòng lab thường được nhiều người sử dụng.

**Yêu cầu phân tích:**

1. Vì sao cookie ghi nhớ không đủ để chứng minh người dùng hiện tại là chủ tài khoản?
2. Điều gì xảy ra nếu attacker sao chép cookie sang máy khác?
3. Tại sao ghi nhớ sau password nhưng trước MFA có thể tạo đường vòng?
4. Thiết kế server-side device record và revoke như thế nào?
5. Có nên dùng fingerprint để giữ trạng thái tin cậy 90 ngày không?
6. Thiết bị công cộng cần policy khác gì thiết bị cá nhân?
7. Khi nào vẫn cần MFA hoặc step-up dù thiết bị đã biết?

**Hướng phân tích:** Cookie là bearer secret, cần CSPRNG, Secure/HttpOnly/SameSite, TTL và digest/server-side record. Chỉ ghi nhớ sau khi authentication policy đạt, có thể yêu cầu step-up. Device record scope theo account, có trạng thái và revoke; logout session không nhất thiết xóa device record nhưng phải có tùy chọn revoke thiết bị. Fingerprint chỉ là risk signal, không phải proof. Kiosk không nên giữ remembered cookie lâu. Hành động nhạy cảm vẫn yêu cầu assurance phù hợp.

## 21. Checklist review

- [ ] Known device được mô tả là tín hiệu ngữ cảnh, không phải danh tính hoặc MFA factor mặc định.
- [ ] Phân biệt known, trusted, managed device và authenticator.
- [ ] Recognition method được ghi rõ: cookie, public key, certificate, MDM hoặc fingerprint.
- [ ] Enrollment chỉ diễn ra sau authentication/step-up đủ tin cậy.
- [ ] Device record gắn account và tenant scope đã xác minh.
- [ ] Cookie ghi nhớ là bearer secret riêng, ngẫu nhiên, opaque, có TTL và server-side revoke.
- [ ] Session cookie và remembered-device cookie tách biệt.
- [ ] Device-key proof dùng challenge mới, transaction binding và chống replay.
- [ ] Certificate/MDM signal được xác minh nguồn, trạng thái và freshness.
- [ ] Fingerprint chỉ hỗ trợ risk assessment; không dùng đơn lẻ để bỏ MFA hoặc khóa account.
- [ ] Thiết bị dùng chung/kiosk có policy không ghi nhớ hoặc thời hạn ngắn.
- [ ] Có giao diện xem, đổi tên và revoke thiết bị.
- [ ] Mất thiết bị xử lý cả device credential, certificate, session và token liên quan.
- [ ] Tenant/account switching không làm rò trạng thái trusted.
- [ ] Có fallback và recovery không yếu hơn mục tiêu bảo mật.
- [ ] Có kiểm thử cookie theft, device spoofing, challenge replay, multi-account và multi-instance.
- [ ] Log không chứa cookie, private key, session token hoặc fingerprint/raw biometric không cần thiết.
- [ ] Data minimization, transparency, retention và vendor governance được xác định.

## 22. Ghi nhớ

**Thiết bị đã biết là một tín hiệu về tính liên tục của môi trường client, không phải bằng chứng chắc chắn về người đang sử dụng hoặc quyền truy cập.** Cookie ghi nhớ thuận tiện nhưng có thể bị sao chép; fingerprint không ổn định và có thể giả mạo; khóa thiết bị hoặc chứng chỉ cung cấp proof mạnh hơn nhưng vẫn cần kiểm tra scope, trạng thái, freshness và người dùng.

Một thiết kế an toàn cần enrollment sau xác thực đủ tin cậy, device record có vòng đời và khả năng thu hồi, risk policy minh bạch, bảo vệ quyền riêng tư và fallback phù hợp. Khi review, hãy hỏi: **Hệ thống biết thiết bị bằng bằng chứng nào? Bằng chứng đó có thể bị sao chép hoặc đồng bộ không? Ai được phép ghi nhớ thiết bị? Cookie/khóa có thể revoke ở mọi instance không? Thiết bị dùng chung được xử lý ra sao? Hành động nào vẫn bắt buộc MFA dù thiết bị đã biết?**
