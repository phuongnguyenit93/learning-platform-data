# Remember device

> **Chương:** Đăng nhập  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Ghi nhớ thiết bị hoặc browser đã được xác minh để giảm các lần yêu cầu MFA lặp lại, đồng thời giữ kiểm soát xác thực, thời hạn, thu hồi và quyền riêng tư.

## 1. Remember device là gì?

**Remember device (ghi nhớ thiết bị)** là tính năng cho phép ứng dụng lưu một dấu hiệu có thời hạn để nhận ra browser, ứng dụng hoặc thiết bị đã được người dùng xác minh trước đó. Trong luồng đăng nhập, hệ thống có thể dùng dấu hiệu này như một tín hiệu ngữ cảnh để giảm số lần yêu cầu MFA bổ sung khi rủi ro thấp và chính sách cho phép.

Ví dụ, một nhân viên đăng nhập bằng mật khẩu và passkey/MFA trên laptop cá nhân. Sau khi xác thực thành công, người dùng chọn “Ghi nhớ thiết bị này”. Lần sau, ứng dụng có thể nhận ra browser đã đăng ký và không yêu cầu thêm một bước MFA cho một số thao tác thông thường. Nếu người dùng đăng nhập từ browser mới, thay đổi recovery method hoặc thực hiện hành động quản trị, hệ thống vẫn có thể yêu cầu xác thực bổ sung.

Điểm quan trọng: **remember device không phải một phương thức xác thực độc lập và không chứng minh chắc chắn người đang sử dụng browser là chủ tài khoản**. Cookie ghi nhớ có thể bị xóa, sao chép hoặc đánh cắp. Nó chỉ cung cấp tín hiệu rằng một dấu hiệu đã được cấp sau lần xác thực trước đang xuất hiện lại.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt remember device với remember me, session persistence và device authentication.
- Thiết kế dấu hiệu thiết bị có entropy cao, thời hạn và khả năng thu hồi.
- Biết khi nào có thể giảm MFA prompt và khi nào phải yêu cầu step-up.
- Bảo vệ device marker trong browser và ứng dụng native.
- Quản lý đăng ký, gia hạn, thu hồi, thiết bị dùng chung và thiết bị bị mất.
- Nhận diện rủi ro cookie theft, replay, CSRF, XSS, device transfer và theo dõi người dùng.
- Kiểm thử hành vi remember device cùng các chính sách xác thực và recovery.

## 2. Remember device khác gì với các khái niệm gần nhau?

| Khái niệm | Mục đích | Trạng thái được lưu | Có thay thế xác thực không? |
|---|---|---|---|
| **Remember device** | Nhận ra browser/thiết bị đã được xác minh để điều chỉnh challenge | Device marker, device record hoặc bằng chứng khóa | Không |
| **Remember me** | Giữ đăng nhập lâu hơn để người dùng không phải đăng nhập lại thường xuyên | Session cookie hoặc refresh/session token | Không; nó duy trì phiên đã xác thực |
| **Session persistence** | Duy trì phiên qua lần đóng/mở browser hoặc ứng dụng | Session identifier và trạng thái phiên | Không; server vẫn kiểm tra phiên |
| **Device authentication/binding** | Chứng minh client kiểm soát khóa hoặc thiết bị đã liên kết | Public key và bằng chứng chữ ký | Có thể là một phần của authentication theo giao thức |
| **Trusted device trong MDM** | Xác định thiết bị đáp ứng chính sách bảo mật doanh nghiệp | Trạng thái quản lý và posture | Không; vẫn cần xác thực người dùng |

Remember me và remember device đôi khi xuất hiện cạnh nhau trên màn hình đăng nhập, nhưng chúng có ý nghĩa khác. Remember me thường kéo dài phiên. Remember device thường ghi nhận một browser/thiết bị đã hoàn thành một bước xác minh để điều chỉnh những lần challenge tiếp theo.

Một ứng dụng có thể cung cấp cả hai, nhưng cần giải thích rõ lựa chọn nào lưu trạng thái đăng nhập và lựa chọn nào chỉ ghi nhớ thiết bị.

## 3. Mô hình tin cậy của remember device

Khi người dùng chọn ghi nhớ, hệ thống thường tạo một device marker ngẫu nhiên và liên kết nó với tài khoản phía server. Ở lần đăng nhập sau, browser gửi marker; server tra cứu trạng thái và quyết định có dùng nó làm tín hiệu giảm challenge hay không.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authentication service
    participant D as Device registry
    U->>B: Đăng nhập và hoàn tất MFA
    B->>A: Yêu cầu ghi nhớ thiết bị
    A->>A: Kiểm tra xác thực vừa hoàn tất và chính sách
    A->>D: Tạo device record + marker verifier
    D-->>A: Device record đã lưu
    A-->>B: Set cookie device marker
    Note over B,D: Lần đăng nhập sau
    B->>A: Login request + device cookie
    A->>D: Tra marker và trạng thái
    D-->>A: Active / expired / revoked
    A->>A: Đánh giá risk context và chính sách MFA
    A-->>B: Tiếp tục, step-up hoặc từ chối
~~~

Luồng này không có nghĩa marker tự xác thực người dùng. Người dùng vẫn phải hoàn tất phương thức đăng nhập bắt buộc. Marker chỉ có thể giúp quyết định liệu có cần thêm một challenge hay không, trong phạm vi đã được chính sách cho phép.

### Ba thành phần

1. **Device marker ở client:** một giá trị ngẫu nhiên được browser/app giữ và gửi lại.
2. **Device record ở server:** liên kết marker với tài khoản, thời điểm tạo, hết hạn, trạng thái và thông tin tối thiểu.
3. **Policy engine:** quyết định có thể giảm challenge hay cần MFA/step-up dựa trên marker cùng các tín hiệu khác.

Không nên lưu một cờ trusted=true trong localStorage rồi tin cờ đó ở server. Client có thể sửa dữ liệu cục bộ. Trạng thái tin cậy phải được xác minh bằng dữ liệu server-side hoặc bằng chứng mật mã hợp lệ.

## 4. Đăng ký thiết bị sau khi xác thực

Chỉ tạo remember-device marker sau khi người dùng đã hoàn tất xác thực ở mức phù hợp. Không cấp marker chỉ vì họ mở trang đăng nhập, nhập email hoặc vượt qua một bước yếu.

Quy trình đăng ký có thể gồm:

1. Người dùng đăng nhập bằng credential được chấp nhận.
2. Hoàn tất MFA hoặc step-up theo chính sách.
3. Ứng dụng giải thích thiết bị/browser nào sẽ được ghi nhớ và trong bao lâu.
4. Người dùng chủ động chọn ghi nhớ, trừ khi tổ chức có chính sách thiết bị được quản lý riêng đã công bố.
5. Server tạo marker bằng bộ sinh số ngẫu nhiên mật mã.
6. Server lưu verifier hoặc digest của marker cùng device record.
7. Server gửi marker qua cookie hoặc vùng lưu trữ bảo vệ phù hợp.
8. Hệ thống ghi audit và thông báo khi chính sách yêu cầu.

### Không đăng ký trong một luồng chưa được xác minh

Nếu attacker chiếm một phiên yếu và có thể tự đánh dấu thiết bị của họ là trusted, họ có thể giảm các challenge tiếp theo. Vì vậy, thao tác đăng ký hoặc thêm thiết bị cần freshness của xác thực và có thể yêu cầu một yếu tố đã được đăng ký từ trước.

### Hiển thị rõ thiết bị

Nên cho người dùng thấy thông tin dễ hiểu như:

- Tên thiết bị do người dùng đặt hoặc mô tả browser/OS ở mức cần thiết.
- Thời điểm được ghi nhớ và lần cuối xuất hiện.
- Thời hạn còn lại hoặc chính sách hết hạn.
- Nút thu hồi thiết bị.

Không hiển thị fingerprint chi tiết, địa chỉ IP đầy đủ hoặc dữ liệu nội bộ không cần thiết. Tên thiết bị có thể do người dùng đặt nên không dùng nó làm bằng chứng xác thực.

## 5. Thiết kế device marker

Device marker thường là một bearer-like secret: ai lấy được marker có thể làm browser trông giống thiết bị đã ghi nhớ. Vì vậy marker cần khó đoán, được bảo vệ và có thể thu hồi.

### Sinh marker

- Dùng CSPRNG của nền tảng.
- Có entropy đủ cao, ví dụ 256 bit ngẫu nhiên.
- Không nhúng account ID, email, timestamp hoặc dữ liệu có thể đoán vào marker.
- Không tạo marker từ hash của user-agent, IP hoặc fingerprint.
- Không dùng một marker chung cho nhiều tài khoản.

Ví dụ minh họa:

~~~typescript
import { randomBytes, createHash } from "node:crypto";

function createDeviceMarker() {
  const raw = randomBytes(32).toString("base64url");
  const verifier = createHash("sha256").update(raw).digest("hex");
  return { raw, verifier };
}
~~~

Ví dụ dùng API crypto phía server. Không tự viết bộ sinh ngẫu nhiên. Marker thô chỉ được trả về client qua kênh an toàn; server lưu verifier/digest để so sánh khi nhận lại.

### Lưu phía server

Một bản ghi có thể gồm:

| Trường | Mục đích |
|---|---|
| device_record_id | ID nội bộ của bản ghi |
| account_id | Tài khoản liên kết |
| marker_verifier | Digest/HMAC của marker, không lưu marker thô |
| created_at | Thời điểm đăng ký |
| last_seen_at | Lần cuối marker xuất hiện |
| idle_expires_at | Hạn do không hoạt động, nếu có |
| absolute_expires_at | Hạn tối đa cố định |
| revoked_at | Thời điểm thu hồi |
| label | Tên hiển thị tùy chọn |
| device_metadata | Metadata tối thiểu, không phải định danh chắc chắn |

Nếu dùng HMAC thay digest thuần, bảo vệ khóa HMAC trong secret manager/KMS và có kế hoạch xoay khóa. Cần thiết kế cách tìm record và xác minh marker mà không làm lộ secret trong log.

### Không lưu marker trong URL

Không đặt marker trong query string, fragment được đồng bộ hoặc link email. URL có thể xuất hiện trong history, log proxy, analytics, referrer hoặc ảnh chụp màn hình. Cookie bảo vệ phù hợp thường là lựa chọn tốt hơn cho browser.

## 6. Cookie cho remember device trên browser

Cookie marker cần có thuộc tính phù hợp:

~~~http
Set-Cookie: __Host-device_marker=<random-value>; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax
~~~

Đây là ví dụ cookie host-only dùng tiền tố __Host-, Secure, HttpOnly, SameSite và thời hạn 30 ngày. Giá trị, thời hạn, SameSite và phạm vi path phải được chọn theo kiến trúc thực tế. Cookie __Host- yêu cầu Secure, Path=/ và không có thuộc tính Domain.

### Ý nghĩa thuộc tính

- **Secure:** browser chỉ gửi cookie qua HTTPS.
- **HttpOnly:** JavaScript không đọc trực tiếp marker.
- **SameSite:** giới hạn việc gửi cookie trong một số ngữ cảnh cross-site; lựa chọn Lax/Strict/None phụ thuộc luồng ứng dụng.
- **Path/Domain:** giới hạn phạm vi gửi cookie; cookie __Host- không có Domain và dùng Path /.
- **Max-Age/Expires:** giới hạn thời gian lưu ở browser; server vẫn phải kiểm tra expiry của device record.

HttpOnly giảm khả năng script đọc cookie nhưng không ngăn XSS gửi request cùng origin. SameSite giúp giảm một số rủi ro CSRF nhưng không thay thế CSRF protection cho các thao tác thay đổi trạng thái.

### Browser profile mới hoặc private browsing

Cookie có thể bị xóa khi người dùng:

- Xóa dữ liệu trang web.
- Dùng cửa sổ private/incognito.
- Tạo browser profile mới.
- Cài lại browser hoặc hệ điều hành.
- Dùng thiết bị khác hoặc browser khác.

Khi đó hệ thống nên coi browser là chưa được ghi nhớ và áp dụng luồng xác thực thông thường. Không nên cố tái nhận diện bằng fingerprint xâm lấn chỉ để tránh một lần MFA.

## 7. Lưu trữ trong ứng dụng native

Ứng dụng di động hoặc desktop có thể lưu marker trong vùng lưu trữ bảo vệ của nền tảng, chẳng hạn Keychain hoặc Keystore. Cần tránh lưu marker dài hạn trong file cấu hình, log, clipboard hoặc vùng backup không được kiểm soát.

Các điểm cần xem xét:

- Dùng secure storage theo hướng dẫn của nền tảng.
- Ràng buộc marker với app/account và thời hạn.
- Xem xét hành vi backup, restore và đồng bộ thiết bị.
- Xóa marker khi logout, gỡ tài khoản hoặc thu hồi theo chính sách.
- Không hardcode marker hoặc khóa dùng chung trong binary.
- Bảo vệ deep link/callback và không đưa marker vào URL.

Secure storage làm tăng bảo vệ khi thiết bị hoạt động bình thường, nhưng không bảo đảm thiết bị không bị root, jailbreak, malware hoặc chiếm quyền. Marker vẫn phải được server kiểm tra và có khả năng thu hồi.

## 8. Remember device và MFA policy

Mục đích phổ biến của remember device là giảm MFA prompt lặp lại. Tuy nhiên, quyết định bỏ qua challenge phải được giới hạn rõ.

### Có thể giảm challenge khi nào?

Một chính sách có thể cho phép giảm MFA bổ sung khi:

- Người dùng vừa hoàn tất MFA hoặc phương thức xác thực đủ mạnh.
- Device marker hợp lệ, còn hạn và chưa bị thu hồi.
- Không có sự kiện credential/recovery đáng ngờ.
- Request không thuộc hành động đặc quyền hoặc yêu cầu step-up bắt buộc.
- Các yêu cầu authentication tối thiểu khác vẫn được đáp ứng.

### Không nên bỏ qua MFA khi nào?

- Tài khoản quản trị hoặc hành động đặc quyền yêu cầu MFA chống phishing.
- Người dùng đổi mật khẩu, email/điện thoại khôi phục hoặc yếu tố MFA.
- Thêm passkey, API key hoặc thiết bị mới có quyền cao.
- Giao dịch giá trị cao hoặc truy cập dữ liệu nhạy cảm.
- Có tín hiệu session theft, credential stuffing hoặc thiết bị bị xâm nhập.
- Marker hết hạn, bị thu hồi, không xác minh được hoặc xuất hiện trong ngữ cảnh bất thường.

Remember device không được hạ thấp assurance bắt buộc của tổ chức hoặc tiêu chuẩn áp dụng. Nếu chính sách yêu cầu MFA cho mỗi lần truy cập hoặc mỗi giao dịch, marker không được dùng để bỏ qua yêu cầu đó.

### Ma trận quyết định minh họa

| Tình huống | Device marker | Hành động |
|---|---|---|
| Đăng nhập thông thường, thiết bị đã ghi nhớ, không có dấu hiệu bất thường | Hợp lệ | Xác minh credential; có thể giảm MFA bổ sung theo chính sách |
| Browser mới hoặc cookie bị xóa | Không có | Áp dụng MFA/step-up theo luồng chuẩn |
| Marker hết hạn hoặc revoked | Không hợp lệ | Không giảm challenge; xác thực theo chính sách |
| Marker hợp lệ nhưng recovery vừa thay đổi | Có | Step-up bằng yếu tố đã đăng ký trước hoặc review |
| Hành động quản trị nhạy cảm | Có hoặc không | Yêu cầu xác thực mạnh/freshness theo chính sách |
| Thiết bị báo mất hoặc có bằng chứng compromise | Có | Thu hồi marker và session liên quan |
| Risk engine không khả dụng | Không rõ | Dùng fallback an toàn; không bỏ qua MFA bắt buộc |

## 9. Hết hạn, gia hạn và thu hồi

Device marker không nên tồn tại vô thời hạn. Một chính sách thường kết hợp:

- **Absolute expiry:** giới hạn tổng thời gian từ lúc đăng ký.
- **Idle expiry:** thu hồi hoặc hết hạn nếu marker không xuất hiện trong một khoảng thời gian.
- **Rotation:** thay marker sau một số sự kiện hoặc theo chu kỳ, nếu hệ thống hỗ trợ an toàn.
- **Revocation:** vô hiệu hóa ngay khi có sự cố hoặc người dùng yêu cầu.

### Gia hạn có điều kiện

Không tự động kéo dài absolute expiry mỗi khi cookie xuất hiện. Nếu dùng sliding idle expiry, cần đặt trần absolute expiry và chỉ cập nhật khi request đủ điều kiện. Request tự động nền hoặc polling không nhất thiết chứng minh người dùng đang sử dụng thiết bị.

Có thể yêu cầu xác thực lại trước khi gia hạn dài hạn. Việc gia hạn phải kiểm tra record còn active, tài khoản còn hoạt động và không có sự kiện thu hồi.

### Thu hồi khi nào?

- Người dùng chọn “Không còn tin cậy thiết bị này”.
- Thiết bị bị mất, bán, chuyển giao hoặc dùng chung.
- Phát hiện marker bị sao chép hoặc dùng bất thường.
- Người dùng đổi credential hoặc recovery method sau sự cố.
- Tài khoản bị khóa, đình chỉ hoặc offboard.
- Quản trị viên thu hồi theo chính sách tổ chức.
- Hệ thống thay đổi khóa/định dạng marker và cần vô hiệu hóa bản cũ.

### Thu hồi một thiết bị và mọi thiết bị

Giao diện nên hỗ trợ thu hồi từng device record và “đăng xuất/thu hồi mọi thiết bị” khi cần. Thu hồi marker không tự động hủy session cookie hoặc refresh token đã phát hành; cần mapping và chính sách thu hồi riêng cho các tài sản đó.

## 10. Rủi ro và cách phòng vệ

| Rủi ro | Cách xảy ra | Kiểm soát |
|---|---|---|
| Marker theft | Malware, backup hoặc log lấy được cookie | Secure, HttpOnly, redaction, expiry và revoke |
| Marker replay | Attacker gửi lại marker đã sao chép | Marker chỉ là tín hiệu; risk checks, rotation hoặc device binding |
| Cookie fixation | Attacker cố gắn marker do họ kiểm soát vào phiên nạn nhân | Sinh marker phía server sau xác thực mạnh; không nhận marker do client tự chọn |
| XSS | Script độc hại thực hiện request dưới origin | CSP, output encoding, dependency hygiene; HttpOnly giảm đọc cookie |
| CSRF | Browser tự gửi cookie trong request cross-site | SameSite và CSRF token/origin checks cho thao tác thay đổi trạng thái |
| Device transfer | Người dùng bán hoặc cho mượn thiết bị | Thu hồi, logout, timeout và nhắc người dùng xóa thiết bị |
| Shared device | Người sau sử dụng marker/phiên người trước | Không ghi nhớ mặc định, profile tách biệt, logout và cleanup |
| Recovery abuse | Attacker dùng recovery để đăng ký marker mới | Step-up bằng yếu tố cũ, thông báo và thời gian chờ phù hợp |
| False trust | Hệ thống coi marker là bằng chứng danh tính | Tách marker khỏi authentication và authorization |
| Tracking | Marker bền vững được dùng theo dõi qua thời gian | Phạm vi first-party, retention ngắn và mục đích rõ |

### Marker bị đánh cắp

Nếu marker là cookie bearer, attacker có thể làm request trông như browser đã ghi nhớ. Vì vậy marker không được tự cấp quyền đăng nhập. Khi phát hiện lộ marker:

1. Thu hồi device record phía server.
2. Thu hồi session/token liên quan nếu có thể xác định.
3. Yêu cầu xác thực lại theo chính sách.
4. Kiểm tra lịch sử sử dụng và hành động nhạy cảm.
5. Thông báo cho người dùng qua kênh đã xác minh.

### Remember device không chống được XSS

HttpOnly ngăn JavaScript đọc trực tiếp cookie nhưng script XSS vẫn có thể gửi request cùng origin trong ngữ cảnh người dùng. Nếu ứng dụng dùng marker để bỏ qua MFA, XSS có thể lợi dụng trạng thái đó để thực hiện request. Cần phòng chống XSS và giữ authorization/step-up cho hành động quan trọng.

## 11. Device binding mạnh hơn marker như thế nào?

Device marker thông thường chứng minh browser đang trình một giá trị đã cấp trước đó. **Device binding** có thể yêu cầu client chứng minh quyền kiểm soát khóa riêng tương ứng với public key đã đăng ký.

Luồng challenge-response:

1. Server gửi nonce ngẫu nhiên, dùng một lần và có thời hạn.
2. Client ký nonce cùng request context bằng khóa riêng.
3. Server xác minh chữ ký bằng public key đã lưu.
4. Server kiểm tra nonce, thời hạn, account/session và mục đích.
5. Nếu hợp lệ, kết quả có thể tăng độ tin cậy rằng client kiểm soát khóa đã đăng ký.

Device binding chống việc chỉ sao chép một marker đơn thuần tốt hơn, nhưng vẫn có giới hạn: malware có thể yêu cầu thiết bị ký, khóa có thể bị lộ, thiết bị có thể bị chiếm quyền và người dùng có thể chuyển thiết bị. Cần chọn cơ chế theo nền tảng và không tự thiết kế giao thức mật mã.

### Không đồng nhất device binding với passkey

Passkey là credential xác thực dựa trên public-key và được dùng trong giao thức WebAuthn/FIDO. Một passkey có thể đồng bộ giữa các thiết bị theo hệ sinh thái; nó không nhất thiết là khóa chỉ tồn tại trên một thiết bị vật lý. Remember device là trạng thái ứng dụng dùng để nhận ra ngữ cảnh đã ghi nhớ. Hai cơ chế có thể phối hợp nhưng có mục đích và vòng đời khác nhau.

## 12. Thiết bị dùng chung và thiết bị công cộng

Không nên chọn “Ghi nhớ thiết bị này” trên:

- Máy tính thư viện hoặc phòng lab.
- Máy kiosk/quầy dịch vụ.
- Máy mượn của đồng nghiệp.
- Thiết bị gia đình dùng chung nếu không có profile người dùng tách biệt.
- Thiết bị công cộng hoặc không được kiểm soát.

Ứng dụng nên giải thích rằng việc ghi nhớ chỉ phù hợp với thiết bị cá nhân mà người dùng kiểm soát. Trên thiết bị dùng chung:

- Không đặt checkbox ghi nhớ ở trạng thái bật sẵn.
- Dùng session ngắn và logout rõ ràng.
- Xóa cookie/device marker khi kết thúc tác vụ theo chính sách.
- Không lưu refresh token hoặc dữ liệu nhạy cảm không cần thiết.
- Có thể yêu cầu người dùng xác thực riêng cho mỗi phiên.

Xóa cookie phía browser không xóa record phía server ngay lập tức; server cần expiry/cleanup và cơ chế thu hồi.

## 13. Quyền riêng tư và trải nghiệm người dùng

Device marker có thể trở thành định danh ổn định của browser. Nếu được dùng ngoài mục đích bảo mật, nó có thể hỗ trợ theo dõi hành vi. Do đó:

- Chỉ dùng marker cho mục đích xác thực/risk policy đã công bố.
- Không chia sẻ marker giữa các website hoặc tổ chức không liên quan.
- Không kết hợp fingerprint chi tiết khi marker ngẫu nhiên đã đủ cho mục đích.
- Đặt thời hạn và xóa record không còn cần.
- Giới hạn quyền truy cập device registry và audit.
- Cho phép người dùng xem, đặt tên và thu hồi thiết bị.
- Thông báo khi có thiết bị mới được ghi nhớ hoặc khi marker bị thu hồi, nếu phù hợp.

### Cân bằng tiện lợi và an toàn

MFA prompt quá thường xuyên có thể khiến người dùng mệt mỏi và dễ chấp nhận challenge theo thói quen. Remember device có thể giảm ma sát, nhưng nếu thiết kế quá rộng, attacker có thêm cơ hội tận dụng marker bị đánh cắp.

Một trải nghiệm tốt nên:

- Nói rõ thiết bị nào sẽ được ghi nhớ.
- Cho biết khoảng thời gian hoặc chính sách hết hạn.
- Để người dùng chủ động chọn trên thiết bị cá nhân.
- Có cách thu hồi dễ tìm.
- Không hứa “không cần MFA nữa”; nói rõ hành động rủi ro cao vẫn có thể cần xác minh.

## 14. Tình huống thực hành: giảm MFA prompt cho nhân viên

**Bối cảnh:** Công ty yêu cầu nhân viên xác thực mạnh khi đăng nhập. Nhiều nhân viên thường dùng laptop cá nhân, nhưng một số thao tác như xem lịch hoặc đọc tài liệu không nhạy cảm. Các thao tác quản trị và xuất dữ liệu vẫn cần MFA chống phishing.

### Chính sách

1. Sau lần đăng nhập mạnh thành công, người dùng có thể chọn ghi nhớ browser cá nhân trong 30 ngày.
2. Server cấp marker ngẫu nhiên, lưu verifier và device record.
3. Browser nhận cookie Secure, HttpOnly, SameSite phù hợp.
4. Lần đăng nhập tiếp theo, server xác minh marker và đánh giá risk context.
5. Với thao tác thông thường, có thể giảm challenge bổ sung nếu các yêu cầu tối thiểu vẫn đạt.
6. Với quản trị, thay recovery method hoặc export dữ liệu, hệ thống vẫn yêu cầu step-up.
7. Người dùng có thể xem danh sách thiết bị và thu hồi bất kỳ lúc nào.

### Khi laptop bị mất

- Người dùng báo mất qua kênh hỗ trợ đã xác minh.
- Quản trị viên thu hồi device record và session liên quan.
- Hệ thống vô hiệu hóa marker phía server.
- Refresh token và token grant liên quan được xử lý theo chính sách.
- Người dùng đăng nhập trên thiết bị khác và xác thực lại.
- Hệ thống kiểm tra các sự kiện sau thời điểm mất.

### Kết quả mong đợi

Remember device giảm prompt trong ngữ cảnh ít rủi ro, trong khi chính sách xác thực mạnh cho hành động quan trọng vẫn được giữ. Nếu marker bị đánh cắp, nó không đủ để tự đăng nhập hoặc cấp quyền; hệ thống có thể thu hồi và yêu cầu step-up.

## 15. Ví dụ logic kiểm tra marker

Pseudocode phía server:

~~~typescript
async function evaluateRememberedDevice(accountId, rawMarker, now) {
  if (!rawMarker) {
    return { recognized: false, reason: "missing" };
  }

  const verifier = hashDeviceMarker(rawMarker);
  const record = await deviceRegistry.findByVerifier(accountId, verifier);

  if (!record) {
    return { recognized: false, reason: "unknown" };
  }
  if (record.revokedAt) {
    return { recognized: false, reason: "revoked" };
  }
  if (now >= record.absoluteExpiresAt) {
    return { recognized: false, reason: "expired" };
  }
  if (record.idleExpiresAt && now >= record.idleExpiresAt) {
    return { recognized: false, reason: "idle_expired" };
  }

  return {
    recognized: true,
    deviceRecordId: record.id,
    reason: "active_marker",
  };
}
~~~

Đây là pseudocode minh họa. hashDeviceMarker phải dùng cách xử lý secret phù hợp; record lookup cần giới hạn theo account; cập nhật last-seen phải kiểm tra trạng thái active một cách an toàn. Kết quả recognized=true chỉ là một tín hiệu cho policy engine, không phải kết quả xác thực hoặc quyền truy cập.

### Quyết định cuối cùng

~~~typescript
function decideAdditionalChallenge(deviceResult, risk, actionPolicy) {
  if (actionPolicy.requiresPhishingResistantMfa) {
    return "require_phishing_resistant_mfa";
  }
  if (!deviceResult.recognized) {
    return "follow_standard_authentication_policy";
  }
  if (risk.requiresStepUp || risk.confirmedCompromise) {
    return "step_up_or_deny";
  }
  return "may_skip_additional_mfa_if_policy_allows";
}
~~~

Không được hiểu nhánh cuối là bỏ qua mọi authentication. Nó chỉ nói rằng policy có thể không yêu cầu thêm một challenge MFA trong ngữ cảnh đã xác định; credential đăng nhập, session validation và authorization vẫn bắt buộc.

## 16. Kiểm thử remember device

Kiểm thử trong môi trường được phép, với tài khoản và browser thử nghiệm:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Đăng ký sau khi MFA thành công | Marker được tạo và liên kết đúng tài khoản |
| Đăng ký trước khi hoàn tất xác thực | Bị từ chối |
| Marker ngẫu nhiên không tồn tại | Không nhận diện thiết bị |
| Marker bị sửa một ký tự | Không khớp verifier |
| Marker hết absolute expiry | Không giảm challenge |
| Marker quá idle timeout | Không giảm challenge theo chính sách |
| Marker đã revoked | Bị từ chối dù browser vẫn gửi cookie |
| Cookie bị xóa | Thiết bị được xem là chưa ghi nhớ |
| Cookie bị sao chép sang browser khác | Không tự cấp quyền; risk/binding policy được áp dụng |
| Marker xuất hiện với tài khoản khác | Không nhận diện chéo tài khoản |
| Thiết bị báo mất | Marker và session liên quan được thu hồi theo chính sách |
| Recovery method vừa thay đổi | Step-up hoặc giới hạn theo chính sách |
| Hành động quản trị yêu cầu MFA | Remember device không bỏ qua yêu cầu bắt buộc |
| XSS chạy cùng origin | HttpOnly ngăn đọc trực tiếp cookie nhưng ứng dụng vẫn phải phòng request trái phép |
| CSRF cross-site | SameSite và CSRF/origin protection hoạt động đúng |
| Browser private mode | Không dựa vào marker không được lưu bền |
| Thiết bị dùng chung | Không ghi nhớ mặc định; logout và cleanup hoạt động |
| Hai request đồng thời gia hạn | Không làm sống lại record đã revoked hoặc expired |
| Logout | Session được hủy; marker xử lý theo lựa chọn/chính sách rõ ràng |
| Tài khoản bị đình chỉ | Marker không giúp vượt qua trạng thái tài khoản |
| Risk engine không khả dụng | Fallback không bỏ qua MFA bắt buộc |

### Chỉ số vận hành

- Tỷ lệ đăng nhập có marker hợp lệ.
- Tỷ lệ MFA prompt giảm được mà không làm tăng sự cố.
- Tỷ lệ marker hết hạn, bị thu hồi và bị báo lộ.
- Tỷ lệ false recognition và thiết bị hợp lệ bị nhận nhầm là mới.
- Số lượng thiết bị được ghi nhớ trên mỗi tài khoản.
- Tỷ lệ step-up trên thiết bị đã ghi nhớ.
- Thời gian từ báo mất thiết bị đến thu hồi marker/session.
- Tỷ lệ người dùng thu hồi thiết bị và lý do hỗ trợ phổ biến.

Không tối ưu chỉ theo số MFA prompt được giảm. Cần theo dõi sự cố account takeover, session theft, recovery abuse và trải nghiệm người dùng.

## 17. Checklist thiết kế remember device

- [ ] Remember device được mô tả là tín hiệu nhận diện, không phải phương thức xác thực độc lập.
- [ ] Phân biệt remember device với remember me và session persistence.
- [ ] Chỉ đăng ký sau khi hoàn tất xác thực đủ mạnh và có consent phù hợp.
- [ ] Marker được sinh bằng CSPRNG với entropy cao, không chứa dữ liệu đoán được.
- [ ] Server lưu verifier/digest hoặc HMAC, không lưu marker thô.
- [ ] Cookie browser dùng Secure, HttpOnly, SameSite và scope phù hợp.
- [ ] Marker không được đặt trong URL, log hoặc analytics.
- [ ] Có idle expiry, absolute expiry, rotation khi phù hợp và revocation.
- [ ] Device marker không tự đăng nhập, không thay thế credential và không cấp authorization.
- [ ] MFA bắt buộc cho quản trị/hành động nhạy cảm không bị bỏ qua.
- [ ] Thay đổi credential/recovery, session theft và thiết bị bị mất kích hoạt đánh giá lại.
- [ ] Có danh sách thiết bị và khả năng thu hồi từng thiết bị hoặc tất cả thiết bị.
- [ ] Ứng dụng native dùng secure storage và xử lý backup/restore phù hợp.
- [ ] Thiết bị công cộng/dùng chung không được ghi nhớ mặc định.
- [ ] Có CSRF/XSS protection và kiểm thử marker replay/cookie theft.
- [ ] Dữ liệu thiết bị được tối thiểu hóa, giới hạn retention và bảo vệ quyền riêng tư.
- [ ] Có fallback khi cookie bị xóa, browser không hỗ trợ hoặc risk service lỗi.

## Ghi nhớ

Remember device giúp nhận ra browser hoặc thiết bị đã hoàn tất xác thực trước đó để giảm các challenge lặp lại trong ngữ cảnh rủi ro thấp. Marker thường là một giá trị ngẫu nhiên được lưu trong cookie hoặc secure storage và có record tương ứng phía server.

Marker có thể bị xóa, sao chép hoặc đánh cắp; nó không chứng minh người đang sử dụng là chủ tài khoản và không được thay thế password, passkey, MFA, session validation hay authorization. Hãy đăng ký sau xác thực mạnh, đặt thời hạn, hỗ trợ thu hồi, yêu cầu step-up cho hành động quan trọng và bảo vệ dữ liệu thiết bị như một tín hiệu nhạy cảm.
