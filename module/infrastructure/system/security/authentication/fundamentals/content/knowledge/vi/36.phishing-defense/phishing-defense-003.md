# Credential harvesting (Thu thập trái phép thông tin xác thực)

> **Chương:** Chống phishing  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu cách kẻ tấn công lừa người dùng tiết lộ mật khẩu, OTP, recovery code, token hoặc thông tin phê duyệt; nhận diện ranh giới tin cậy và thiết kế phòng thủ ở email, browser, IdP, ứng dụng, session và quy trình ứng phó.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích credential harvesting và phân biệt nó với credential stuffing, brute force, malware credential theft và session hijacking.
2. Mô tả các kênh và mẫu phishing phổ biến ở mức nhận diện, từ email, SMS, QR, cuộc gọi đến trang đăng nhập giả và OAuth consent phishing.
3. Xác định loại dữ liệu có thể bị thu thập: password, OTP, recovery code, private-key material, session cookie, access token và authorization grant.
4. Phân tích ranh giới tin cậy giữa người dùng, browser, website, IdP, RP, thiết bị và resource server.
5. Giải thích vì sao HTTPS, logo, tên miền gần giống hoặc MFA dạng OTP không đủ để bảo đảm chống phishing.
6. Thiết kế đăng nhập chống phishing bằng passkey/WebAuthn, domain hygiene, password manager, email/web controls và UX an toàn.
7. Phát hiện dấu hiệu credential harvesting qua telemetry, báo cáo người dùng và sự kiện sau đăng nhập.
8. Ứng phó khi credential hoặc session bị lộ bằng cách revoke, reset, kiểm tra recovery, thông báo và điều tra có phạm vi.
9. Xây dựng bài kiểm thử và mô phỏng phishing an toàn, có phê duyệt, không thu thập secret thật.

## 1. Credential harvesting là gì?

**Credential harvesting (thu thập trái phép thông tin xác thực)** là hành vi lừa hoặc ép người dùng cung cấp dữ liệu có thể dùng để xác thực hay tiếp tục một phiên truy cập. Attacker thường giả danh một tổ chức, dịch vụ hoặc người đáng tin cậy để đưa nạn nhân tới một trang, ứng dụng hoặc quy trình giả mạo.

Dữ liệu bị nhắm tới không chỉ là mật khẩu. Nó có thể gồm:

- Username, email hoặc mã nhân viên dùng để xác định tài khoản.
- Password hoặc PIN.
- OTP qua SMS, email, TOTP hoặc push approval.
- Recovery code, backup code và câu trả lời khôi phục.
- Session cookie hoặc bearer token.
- OAuth authorization grant hoặc quyền đã cấp cho một ứng dụng.
- Thông tin đăng ký authenticator, mã QR enrollment hoặc dữ liệu hỗ trợ khôi phục.
- Dữ liệu bí mật dùng để ký hoặc xác thực client, nếu người dùng/quản trị viên bị lừa tiết lộ hoặc cài đặt sai.

Credential harvesting thường là bước đầu của account takeover. Attacker có thể dùng thông tin thu thập được ngay lập tức, bán lại, thử trên dịch vụ khác hoặc kết hợp với malware và social engineering.

### Ví dụ

Một học viên nhận email giả mạo thông báo rằng tài khoản học tập sẽ bị khóa nếu không xác minh. Link trong email mở một trang có logo và màu sắc giống Learning Platform. Học viên nhập email, password và mã OTP. Trang giả chuyển tiếp thông tin đó cho attacker; attacker có thể thử đăng nhập vào dịch vụ thật trong thời gian ngắn.

Trong ví dụ này, database của Learning Platform không cần bị xâm nhập. Người dùng đã tự gửi thông tin tới một điểm cuối không thuộc tổ chức.

### Credential harvesting khác gì credential stuffing?

| Khái niệm | Mô tả | Điểm khác biệt |
| --- | --- | --- |
| **Credential harvesting** | Lừa người dùng tiết lộ credential hoặc token. | Tập trung vào thu thập dữ liệu xác thực từ nạn nhân. |
| **Credential stuffing** | Thử các cặp username/password đã bị lộ ở dịch vụ khác. | Dùng dữ liệu đã có để thử đăng nhập hàng loạt. |
| **Brute force** | Đoán nhiều mật khẩu cho tài khoản. | Tạo credential bằng cách thử nhiều giá trị. |
| **Session hijacking** | Chiếm hoặc sử dụng session/token đã được cấp. | Có thể xảy ra sau khi credential hoặc cookie bị lấy. |
| **Malware credential theft** | Phần mềm độc hại lấy dữ liệu trên thiết bị. | Thu thập từ browser, bộ nhớ, clipboard hoặc hệ thống bị nhiễm. |

Các kỹ thuật có thể nối tiếp nhau. Credential harvesting có thể lấy password và OTP; session hijacking có thể dùng cookie thu được; credential stuffing có thể dùng lại password trên các dịch vụ khác.

## 2. Vòng đời của một cuộc credential harvesting

~~~mermaid
flowchart TD
    A["Chọn tổ chức hoặc nhóm người dùng"] --> B["Tạo thông điệp giả danh hoặc lời dụ"]
    B --> C["Đưa nạn nhân tới kênh/trang không tin cậy"]
    C --> D["Nạn nhân được yêu cầu nhập hoặc phê duyệt"]
    D --> E{"Dữ liệu hoặc quyền bị tiết lộ?"}
    E -->|"Không"| F["Báo cáo hoặc bỏ qua"]
    E -->|"Có"| G["Attacker có credential, token hoặc grant"]
    G --> H["Thử truy cập dịch vụ thật"]
    H --> I["Duy trì phiên hoặc thay đổi recovery"]
    I --> J["Truy cập dữ liệu, lạm dụng quyền hoặc mở rộng"]
~~~

Các giai đoạn giúp đội bảo mật chọn điểm kiểm soát:

1. **Chuẩn bị mục tiêu:** chọn tổ chức, vai trò hoặc nhóm người dùng có quyền truy cập dữ liệu giá trị.
2. **Tạo mồi nhử:** giả danh IT, trường học, ngân hàng, nhà cung cấp, đồng nghiệp hoặc quy trình khẩn cấp.
3. **Phân phối:** dùng email, SMS, ứng dụng nhắn tin, cuộc gọi, QR code, quảng cáo hoặc tài liệu chia sẻ.
4. **Thu thập:** dụ nạn nhân nhập credential, đọc OTP, cung cấp recovery code hoặc cấp quyền cho ứng dụng.
5. **Sử dụng:** đăng nhập, đổi thông tin khôi phục, thêm authenticator, lấy token hoặc tạo phiên.
6. **Duy trì và khai thác:** tiếp tục truy cập, lấy dữ liệu, lừa người khác hoặc dùng tài khoản làm bàn đạp.

Phòng thủ phải bao phủ cả trước khi người dùng nhập dữ liệu và sau khi một credential có thể đã bị lộ. Chỉ chặn một domain phishing không đủ nếu session đã bị đánh cắp hoặc OAuth grant vẫn còn hiệu lực.

## 3. Những kênh thường dùng để thu thập credential

### 3.1 Email phishing

Email giả có thể mạo danh:

- Bộ phận IT yêu cầu xác minh tài khoản.
- Dịch vụ giao nhận, ngân hàng hoặc nhà cung cấp.
- Giảng viên, quản lý hoặc đồng nghiệp.
- Hệ thống cảnh báo đăng nhập hoặc chia sẻ tài liệu.
- Quy trình hóa đơn, bảng lương hoặc phê duyệt.

Dấu hiệu đáng chú ý gồm lời thúc ép bất thường, đe dọa khóa tài khoản, yêu cầu giữ bí mật, link không đúng domain chính thức, file đính kèm ngoài dự kiến hoặc thay đổi đột ngột trong quy trình thanh toán.

Tuy nhiên, email có ngữ pháp tốt, tên hiển thị quen thuộc hoặc chữ ký hợp lệ vẫn có thể là giả mạo hay xuất phát từ tài khoản đã bị chiếm. Không đánh giá chỉ bằng lỗi chính tả.

### 3.2 SMS và ứng dụng nhắn tin

Smishing là phishing qua SMS; các kênh chat cũng có thể phát tán link hoặc mã QR giả. Tin nhắn thường tạo cảm giác cần hành động ngay: giao hàng thất bại, tài khoản bị khóa, khoản phí chưa thanh toán hoặc mã đăng nhập cần xác nhận.

Người dùng nên mở ứng dụng hoặc gõ địa chỉ dịch vụ đã biết thay vì đi theo link trong tin nhắn không mong đợi.

### 3.3 QR phishing (quishing)

QR code có thể che khuất URL đích khỏi người dùng trước khi quét. Mã có thể xuất hiện trên email, poster, tài liệu, bàn làm việc hoặc màn hình chia sẻ.

Biện pháp:

- Hiển thị và kiểm tra domain trước khi mở.
- Không đăng nhập từ trang vừa mở nếu không xác định được dịch vụ và lý do.
- Với thanh toán hoặc xác minh tài khoản, mở ứng dụng chính thức và tìm tác vụ tương ứng.
- Tổ chức nên có quy trình xác minh QR trong tài liệu nội bộ.

### 3.4 Voice phishing và giả danh hỗ trợ

Vishing là phishing qua cuộc gọi hoặc thoại. Kẻ gian có thể giả danh helpdesk, quản trị viên, ngân hàng hoặc người quản lý để yêu cầu đọc OTP, cài phần mềm hỗ trợ, duyệt push hoặc cung cấp recovery code.

Nhân viên hỗ trợ hợp lệ không cần biết password, OTP hay private key của người dùng. Quy trình helpdesk phải cấm yêu cầu người dùng đọc secret và phải có kênh xác minh độc lập.

### 3.5 Trang đăng nhập giả và tài liệu giả

Một trang giả có thể sao chép giao diện, logo và nội dung của dịch vụ thật. Tài liệu chia sẻ hoặc trang xem file cũng có thể yêu cầu đăng nhập lại bằng một form không thuộc nhà cung cấp.

Logo, bố cục, tên hiển thị và nội dung giống nhau không chứng minh domain là thật. Người dùng cần kiểm tra origin/domain trong browser và bắt đầu đăng nhập từ bookmark hoặc ứng dụng chính thức.

## 4. Các loại dữ liệu bị nhắm tới

Credential harvesting có thể thu thập nhiều loại dữ liệu, mỗi loại tạo ra hậu quả khác nhau.

| Dữ liệu | Attacker có thể làm gì | Phòng thủ trọng tâm |
| --- | --- | --- |
| Username/email | Dò tài khoản, ghép với dữ liệu khác, chuẩn bị stuffing. | Giảm account enumeration, bảo vệ directory và dữ liệu cá nhân. |
| Password | Đăng nhập hoặc thử trên dịch vụ khác. | Password hashing, password screening, MFA/passkey, reset khi lộ. |
| OTP | Hoàn tất một lần đăng nhập đang diễn ra. | Phishing-resistant authentication, transaction binding, không đọc OTP cho người khác. |
| Recovery/backup code | Vượt qua hoặc thay thế phương thức xác thực. | One-time use, lưu trữ an toàn, rotate và quy trình recovery mạnh. |
| Session cookie | Tiếp tục phiên đã xác thực mà không cần password. | Secure/HttpOnly/SameSite, session binding phù hợp, revoke nhanh. |
| Access/refresh token | Gọi API hoặc xin access token mới. | Audience/scope giới hạn, rotation, revocation và sender constraint khi phù hợp. |
| OAuth consent/grant | Cho ứng dụng truy cập dữ liệu qua API. | Consent policy, publisher verification, scope review và grant revocation. |
| Authenticator enrollment data | Thêm phương thức do attacker kiểm soát. | Step-up, proof of possession và thông báo thay đổi. |

Một secret bị lộ có thể không đủ để chiếm tài khoản nếu các lớp khác được thiết kế đúng. Nhưng không được giả định mọi loại credential đều có cùng vòng đời hoặc có thể thu hồi theo cùng một cách.

## 5. Ranh giới tin cậy: browser, website, IdP và ứng dụng

Người dùng thường nhìn thấy một trang web, nhưng hệ thống xác thực có nhiều thành phần và ranh giới tin cậy.

~~~mermaid
flowchart LR
    U["Người dùng"] --> B["Browser / thiết bị"]
    B --> R["RP: Learning Platform"]
    B --> P["Trang phishing không tin cậy"]
    R --> I["IdP được tin cậy"]
    I --> R
    R --> API["Resource server"]
    P -. "Thu thập dữ liệu do người dùng nhập" .-> A["Attacker"]
    A -. "Thử credential hoặc token" .-> I
    A -. "Dùng phiên/token bị lộ" .-> API
~~~

### Các ranh giới cần bảo vệ

- **Người dùng → Browser:** người dùng cần xác định trang đang mở và hiểu yêu cầu xác thực.
- **Browser → RP:** origin, TLS, cookie và JavaScript cần được bảo vệ; không tin dữ liệu client tự khai.
- **RP → IdP:** issuer, redirect URI, state, nonce, PKCE và token validation phải đúng.
- **RP → Resource server:** token cần đúng issuer, audience, scope và thời hạn.
- **IdP → RP:** assertion/logout event phải được xác minh và ràng buộc đúng subject/session.
- **Helpdesk → Account recovery:** người hỗ trợ phải tuân thủ quy trình chứng minh danh tính, không được yêu cầu secret.

Một trang giả có thể trông giống RP nhưng không thuộc cùng origin. Đây là lý do origin binding trong WebAuthn có giá trị: authenticator tạo assertion cho RP ID đã đăng ký, không ký một challenge cho domain giả chỉ vì giao diện trông giống nhau.

## 6. Vì sao HTTPS và biểu tượng ổ khóa không chứng minh trang là thật?

HTTPS bảo vệ kênh truyền tới domain đang truy cập và giúp browser xác minh chứng chỉ TLS cho domain đó. Nó không chứng minh domain đó thuộc tổ chức mà người dùng mong muốn.

Attacker có thể đăng ký domain gần giống, có chứng chỉ TLS hợp lệ và vận hành trang giả qua HTTPS. Vì vậy:

- Ổ khóa cho biết kết nối được bảo vệ theo TLS, không xác nhận mục đích hoặc chủ sở hữu nghiệp vụ của website.
- Logo và màu sắc có thể bị sao chép.
- Tên hiển thị trong email có thể bị giả.
- Một subdomain có chứa tên thương hiệu vẫn có thể thuộc domain khác.
- Link rút gọn và QR code làm URL đích khó nhận biết hơn.

Người dùng nên kiểm tra đúng hostname/domain và bắt đầu từ bookmark, ứng dụng chính thức hoặc trang chủ đã biết. Tổ chức cần công bố domain đăng nhập chính thức, bảo vệ domain tương tự và giám sát domain lookalike.

## 7. Adversary-in-the-middle và đánh cắp phiên

Một số cuộc tấn công không chỉ thu password mà còn tìm cách chiếm kết quả xác thực hoặc phiên sau khi người dùng đã vượt qua MFA.

**Adversary-in-the-middle (AiTM)** là tình huống attacker đứng giữa browser và dịch vụ thật, chuyển tiếp tương tác để nạn nhân nhìn thấy một luồng gần giống thật. Trong một số biến thể, attacker có thể thu thập password, OTP và session cookie sau khi xác thực.

Điểm cần hiểu:

- MFA dạng OTP có thể bị relay theo thời gian thực.
- Push approval có thể bị người dùng phê duyệt nhầm.
- Session cookie có thể cho phép tiếp tục phiên nếu server không có biện pháp phát hiện/revoke phù hợp.
- TLS giữa browser và từng đầu cuối không tự loại bỏ rủi ro khi người dùng bị lừa tương tác với một proxy do attacker điều khiển.
- Passkey/WebAuthn có origin/RP ID binding nên chống được lớp phishing/AiTM phổ biến tốt hơn password và OTP, nếu được triển khai đúng.

### Phòng thủ

- Ưu tiên passkey/security key theo WebAuthn cho đăng nhập nhạy cảm.
- Bảo vệ session cookie và giảm thời gian sống phù hợp.
- Phát hiện session bất thường và có khả năng revoke server-side.
- Ràng buộc thao tác nhạy cảm với transaction và xác thực mới khi cần.
- Không cho phép recovery hoặc password fallback làm yếu chính sách.
- Thông báo khi có đăng nhập hoặc thay đổi authenticator bất thường.

Không coi việc đổi IP hoặc browser fingerprint đơn lẻ là bằng chứng chắc chắn AiTM. Cần kết hợp telemetry, context và sự kiện sau đăng nhập.

## 8. OAuth consent phishing và quyền ứng dụng

Credential harvesting không phải lúc nào cũng yêu cầu người dùng nhập password. Attacker có thể dụ người dùng cấp quyền cho một ứng dụng OAuth giả danh công cụ hợp lệ.

Người dùng có thể thấy trang consent thật của IdP, nhưng ứng dụng xin quyền có thể không đáng tin hoặc yêu cầu scope quá rộng. Nếu người dùng chấp thuận, authorization server có thể phát token hợp lệ cho ứng dụng đó.

### Rủi ro

- Ứng dụng đọc email, file, hồ sơ hoặc dữ liệu lịch.
- Token tồn tại sau khi người dùng đóng browser.
- Quyền truy cập có thể kéo dài qua refresh token hoặc grant.
- Việc đổi password không nhất thiết thu hồi mọi OAuth grant đã cấp.

### Kiểm soát

- Hạn chế user consent đối với ứng dụng chưa được phê duyệt.
- Hiển thị rõ publisher, tên ứng dụng, tenant và scope.
- Áp dụng admin consent cho quyền nhạy cảm.
- Giám sát ứng dụng mới, consent bất thường và scope tăng đột ngột.
- Có quy trình revoke grant, refresh token và session liên quan.
- Định kỳ rà soát ứng dụng OAuth đã được cấp quyền.

Người dùng cần xem ứng dụng nào đang xin quyền và dữ liệu nào sẽ được truy cập. Không chấp thuận chỉ vì trang consent nằm trên domain IdP thật.

## 9. Dấu hiệu nhận biết yêu cầu credential đáng ngờ

Không có một dấu hiệu nào luôn đúng, nhưng nhiều tín hiệu kết hợp có thể giúp người dùng dừng lại và xác minh.

| Dấu hiệu | Câu hỏi nên đặt ra |
| --- | --- |
| Yêu cầu đăng nhập từ link bất ngờ | Tôi có thể mở ứng dụng chính thức để kiểm tra thay vì dùng link này không? |
| Đe dọa khóa tài khoản hoặc mất quyền lợi | Có kênh chính thức nào xác nhận hạn chót này không? |
| Yêu cầu đọc OTP hoặc recovery code | Vì sao người khác cần biết mã chỉ dành cho tôi? |
| Push request không do mình khởi tạo | Có ai đang cố đăng nhập bằng tài khoản của tôi không? |
| Domain gần giống thương hiệu | Hostname có đúng domain chính thức không? |
| Yêu cầu cài ứng dụng hỗ trợ từ nguồn lạ | Có ticket và quy trình IT đã xác minh không? |
| OAuth consent xin scope rộng | Ứng dụng có thực sự cần đọc hoặc sửa dữ liệu này không? |
| Yêu cầu thay đổi recovery channel | Tôi có đang ở đúng trang cài đặt chính thức không? |
| Người gửi thúc ép giữ bí mật | Có thể xác minh qua một kênh độc lập không? |

### Quy tắc an toàn cho người dùng

- Không đọc password, OTP, recovery code hoặc private key cho bất kỳ ai.
- Không phê duyệt push mà bản thân không khởi tạo.
- Không đăng nhập từ link bất ngờ; mở ứng dụng hoặc bookmark chính thức.
- Không cài phần mềm điều khiển từ xa theo hướng dẫn từ cuộc gọi chưa xác minh.
- Xác minh yêu cầu khẩn cấp qua số điện thoại hoặc kênh đã biết từ trước.
- Báo cáo thông điệp đáng ngờ qua chức năng report phishing hoặc kênh IT/security chính thức.

## 10. Phòng thủ ở email và domain

Email là kênh phân phối phishing phổ biến. Các kiểm soát xác thực email giúp giảm một số hình thức giả mạo domain, nhưng không giải quyết mọi dạng phishing.

### SPF, DKIM và DMARC

- **SPF:** cho biết máy chủ nào được phép gửi thư cho domain theo policy DNS.
- **DKIM:** gắn chữ ký mật mã vào email để kiểm tra tính toàn vẹn và domain ký.
- **DMARC:** áp chính sách và báo cáo dựa trên alignment giữa domain hiển thị ở From với SPF/DKIM.

Các biện pháp này giúp chống giả mạo domain của tổ chức, nhưng không ngăn:

- Domain lookalike do attacker đăng ký.
- Tài khoản email thật đã bị chiếm.
- Nhà cung cấp hợp lệ bị compromise.
- Thông điệp được gửi từ domain khác nhưng mạo danh thương hiệu.
- Người dùng tự nguyện cấp quyền OAuth cho ứng dụng độc hại.

### Kiểm soát bổ sung

- Triển khai DMARC theo lộ trình giám sát rồi enforcement phù hợp.
- Bảo vệ domain đăng nhập, domain email và domain hỗ trợ.
- Giám sát domain lookalike, certificate transparency và abuse reports.
- Dùng email gateway để phân tích link/attachment và phát hiện impersonation.
- Hiển thị cảnh báo cho email bên ngoài hoặc domain tương tự.
- Duy trì kênh báo cáo phishing đơn giản.
- Có quy trình gỡ bỏ website giả và thông báo cho người dùng.

## 11. Phòng thủ ở browser và ứng dụng web

### Domain và redirect

- Dùng domain đăng nhập ổn định, dễ nhận diện và công bố rõ.
- Tránh nhiều domain login không cần thiết.
- Không cho phép redirect URI tùy ý.
- Dùng allowlist cho callback và post-login redirect.
- Bảo vệ DNS registrar, DNS zone và tài khoản quản lý domain bằng MFA chống phishing.
- Giám sát thay đổi DNS, certificate và cấu hình CDN.

### Web application controls

- Dùng TLS và HSTS phù hợp.
- Đặt cookie session Secure, HttpOnly và SameSite theo luồng ứng dụng.
- Có Content Security Policy (CSP) phù hợp để giảm một số rủi ro script injection.
- Chống XSS vì script chạy trong origin thật có thể lấy dữ liệu mà browser cho phép.
- Không nhúng secret vào URL hoặc query string.
- Redact credential/token khỏi logs, analytics và referrer.
- Kiểm tra origin và CSRF cho thao tác thay đổi trạng thái.
- Không để trang đăng nhập giả nội bộ hoặc môi trường test có thể truy cập công khai mà không kiểm soát.

Các header và cookie giúp giảm một số rủi ro web; chúng không biến một trang có domain giả thành trang đáng tin.

## 12. MFA: lớp bảo vệ hữu ích nhưng không phải mọi phương thức đều chống phishing

MFA làm tăng yêu cầu đối với attacker khi password bị thu thập. Tuy nhiên, khả năng chống phishing khác nhau:

| Phương thức | Lợi ích | Giới hạn |
| --- | --- | --- |
| SMS OTP | Phổ biến, dễ triển khai. | Có thể bị phishing, relay hoặc SIM swap. |
| Email OTP | Dễ tiếp cận nếu email còn bảo vệ tốt. | Email account compromise có thể làm mất cả hai lớp. |
| TOTP | Không cần mạng di động, dùng secret riêng. | Mã có thể bị nhập vào trang giả và relay tức thời. |
| Push approval | Trải nghiệm thuận tiện. | MFA fatigue và phê duyệt nhầm. |
| Number matching | Giảm phê duyệt mù trong một số luồng push. | Không tự tạo origin binding chống AiTM. |
| FIDO2/WebAuthn passkey/security key | Gắn assertion với RP ID/origin, chống phishing tốt. | Cần bảo vệ enrollment, recovery và thiết bị. |

### Thiết kế MFA an toàn

- Ưu tiên phương thức phishing-resistant cho quản trị viên và hành động nhạy cảm.
- Không yêu cầu người dùng đọc OTP cho helpdesk.
- Push phải có thông tin ngữ cảnh và cơ chế từ chối/báo cáo dễ dùng.
- Giới hạn số lần challenge và gửi push.
- Bảo vệ đăng ký, thay thế và xóa authenticator bằng step-up.
- Có quy trình recovery đủ mạnh và audit.
- Không cho phép legacy endpoint bỏ qua MFA.

## 13. Passkey và WebAuthn chống credential harvesting như thế nào?

Với password, người dùng phải nhập một secret có thể bị gửi tới domain giả. Với passkey/WebAuthn, authenticator giữ private key và chỉ tạo chữ ký cho challenge gắn với RP ID/origin phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Website thật
    participant A as Authenticator
    U->>B: Mở domain thật
    B->>RP: Yêu cầu đăng nhập
    RP-->>B: Challenge và RP ID
    B->>A: Yêu cầu xác thực
    A->>A: Kiểm tra RP ID và user verification theo policy
    A-->>B: Assertion được ký
    B->>RP: Assertion
    RP->>RP: Xác minh challenge, origin, RP ID và chữ ký
    RP-->>U: Đăng nhập thành công
~~~

Một trang phishing trên domain khác không thể đơn giản yêu cầu authenticator ký cho RP thật. Đây là ưu điểm cốt lõi so với password và OTP có thể bị relay.

### Các điều kiện triển khai

- RP ID được cấu hình chính xác.
- Browser kiểm tra origin theo WebAuthn.
- Server kiểm tra challenge, credential ID, chữ ký, user presence và user verification theo policy.
- Challenge dùng một lần, có thời hạn và gắn với transaction.
- Registration yêu cầu xác minh đúng tài khoản và quyền kiểm soát hiện tại.
- Credential bị mất hoặc nghi compromise có thể được revoke.
- Recovery không làm giảm mức bảo vệ xuống một đường yếu hơn.

Passkey làm giảm đáng kể rủi ro phishing credential, nhưng không bảo vệ khỏi mọi malware, session theft, thiết bị bị chiếm hoặc quy trình recovery yếu.

## 14. Password manager và domain binding

Password manager có thể giúp giảm việc nhập password vào domain giả vì nhiều công cụ chỉ autofill khi domain/origin phù hợp với thông tin đã lưu.

Khuyến nghị:

- Dùng password manager đáng tin cậy và mật khẩu riêng cho mỗi dịch vụ.
- Không copy/paste password vào trang chưa xác minh.
- Nếu password manager không nhận diện trang login như thường lệ, dừng lại và kiểm tra domain.
- Không lưu recovery code ở nơi chia sẻ công khai.
- Bảo vệ vault bằng passkey hoặc MFA mạnh nếu có.
- Không coi autofill là bảo đảm tuyệt đối; người dùng vẫn có thể tự copy/paste vào trang giả.

Password manager giúp giảm tái sử dụng mật khẩu và cung cấp tín hiệu về domain mismatch. Nó là lớp hỗ trợ, không thay thế phishing-resistant authentication.

## 15. Phát hiện credential harvesting

Đội bảo mật cần kết hợp báo cáo người dùng, telemetry email/web và sự kiện authentication.

### Tín hiệu ở email/web

- Nhiều người nhận báo cáo cùng một thông điệp hoặc domain.
- Domain mới đăng ký có tên gần giống tổ chức.
- Redirect chain bất thường hoặc URL rút gọn.
- Trang login giả được phát hiện qua threat intelligence hoặc browser report.
- Email có sender/display-name mismatch hoặc authentication result bất thường.
- QR code trỏ tới domain không thuộc allowlist.

### Tín hiệu ở authentication

- Login từ thiết bị, IP hoặc ASN mới ngay sau email phishing.
- Password đúng nhưng MFA bị thất bại nhiều lần hoặc có push không mong đợi.
- Nhiều lần xác thực cùng một tài khoản từ vị trí/session bất thường.
- Session mới được tạo rồi thay đổi recovery channel.
- Passkey hoặc authenticator mới được thêm sau login đáng ngờ.
- OAuth app mới được cấp scope rộng.
- Token refresh hoặc API access bất thường sau khi người dùng tương tác với trang giả.

Không một signal đơn lẻ chứng minh credential harvesting. Cần tương quan thời gian giữa email/report, domain, login, session, consent và thay đổi tài khoản.

### Telemetry cần bảo vệ

- Không ghi password, OTP, recovery code, private key hoặc raw token.
- Pseudonymize subject/session identifier khi dùng cho phân tích.
- Giới hạn retention của IP, device và browser telemetry.
- Ghi event ID, source, timestamp, policy version và kết quả xác minh.
- Bảo vệ audit khỏi sửa/xóa trái phép.

## 16. Ứng phó khi người dùng đã nhập credential vào trang giả

Phản ứng nhanh giúp giảm thời gian attacker có thể sử dụng dữ liệu đã thu thập.

### Quy trình cho người dùng

1. Dừng tương tác với trang đáng ngờ và không nhập thêm mã.
2. Báo cáo thông điệp/domain cho IT/security qua kênh chính thức.
3. Từ thiết bị và domain đáng tin, đổi password nếu password đã được nhập.
4. Nếu đã nhập OTP hoặc phê duyệt push, báo ngay để đội bảo mật kiểm tra phiên.
5. Nếu đã cung cấp recovery code, revoke/rotate bộ code đó.
6. Nếu đã cấp OAuth consent, thu hồi grant và báo đội quản trị.
7. Nếu đã cài ứng dụng hoặc công cụ điều khiển từ xa, ngắt kết nối theo hướng dẫn incident response và kiểm tra thiết bị.
8. Theo dõi thông báo đăng nhập, thay đổi recovery và authenticator.

Không đổi password bằng chính link phishing hoặc trên thiết bị đang nghi bị compromise.

### Quy trình cho đội vận hành

1. **Triage:** xác định domain, thời điểm, nhóm người nhận và loại dữ liệu có thể đã bị lộ.
2. **Contain:** chặn domain/URL ở gateway, DNS, browser protection hoặc proxy theo khả năng; lưu bằng chứng cần thiết.
3. **Credential response:** reset password, revoke recovery code và xử lý authenticator bị lộ theo scope.
4. **Session response:** revoke session, refresh token và grant liên quan; đánh giá access token còn hiệu lực.
5. **Account review:** kiểm tra email/phone recovery, passkey, MFA methods, API key, role và OAuth app mới.
6. **Domain takedown:** báo registrar, hosting provider, browser safe-browsing và các kênh abuse phù hợp.
7. **Notify:** thông báo người dùng bị ảnh hưởng qua kênh đã xác minh.
8. **Learn:** cập nhật detection, training, policy và test cases.

Nếu chỉ reset password mà giữ nguyên session cookie bị đánh cắp hoặc OAuth grant độc hại, attacker có thể tiếp tục truy cập.

## 17. Kiểm soát recovery và thay đổi authenticator

Attacker thường tìm đường duy trì quyền truy cập sau khi lấy được credential. Các hành động sau đăng nhập cần được bảo vệ như một phần của authentication lifecycle:

- Thêm hoặc xóa passkey.
- Đổi số điện thoại/email khôi phục.
- Tạo recovery code mới.
- Tắt MFA hoặc chuyển sang phương thức yếu hơn.
- Thêm ứng dụng OAuth.
- Tạo API key hoặc client credential.
- Đổi mật khẩu và đăng xuất các thiết bị khác.

### Policy gợi ý

- Yêu cầu xác thực mới bằng phương thức đủ mạnh.
- Xác minh subject, tenant và transaction.
- Gửi thông báo qua kênh đã đăng ký trước.
- Có thời gian chờ cho thay đổi rủi ro cao khi phù hợp.
- Thu hồi session/token cũ sau sự cố.
- Không cho phép recovery tự nâng assurance hoặc tự gỡ suspension.
- Có quy trình hỗ trợ ngoại lệ với phê duyệt và audit.

## 18. Mô phỏng phishing an toàn và đào tạo

Tổ chức có thể kiểm tra khả năng nhận biết phishing, nhưng phải thiết kế chương trình có trách nhiệm.

### Nguyên tắc

- Có phê duyệt từ chủ sở hữu hệ thống, security và bộ phận liên quan.
- Xác định mục tiêu học tập và phạm vi người tham gia.
- Dùng môi trường hoặc domain mô phỏng được kiểm soát.
- Không thu thập password, OTP, recovery code hoặc token thật.
- Nếu cần đo hành vi, chỉ ghi sự kiện an toàn như mở trang, báo cáo hoặc nhấp vào nút mô phỏng.
- Không dùng kết quả để bêu tên hoặc kỷ luật cá nhân ngoài policy đã công bố.
- Cung cấp hướng dẫn ngay sau mô phỏng và kênh hỗ trợ.
- Xóa dữ liệu mô phỏng theo retention đã định.

### Chỉ số hữu ích

- Tỷ lệ báo cáo thông điệp giả lập.
- Thời gian từ nhận thông điệp tới báo cáo.
- Tỷ lệ người dùng kiểm tra domain.
- Tỷ lệ phê duyệt push không do mình khởi tạo trong bài tập an toàn.
- Tỷ lệ sử dụng passkey hoặc phương thức chống phishing.
- Tỷ lệ hoàn tất đào tạo sau khi có cảnh báo.

Không dùng click rate làm chỉ số duy nhất. Mục tiêu là cải thiện năng lực phát hiện, báo cáo và phản ứng, không phải tạo một cuộc thi bắt lỗi người dùng.

## 19. Ví dụ thực tế: Learning Platform

Learning Platform dùng OIDC với IdP của trường đại học. Học viên nhận một email thông báo giả rằng tài khoản sẽ bị khóa nếu không xác minh trước cuối ngày.

### Diễn biến

1. Email chứa link tới domain gần giống domain đăng nhập chính thức.
2. Học viên mở trang giả và nhập password.
3. Trang yêu cầu thêm OTP, khiến học viên nghĩ đây là MFA bình thường.
4. Attacker thử sử dụng credential và OTP trên dịch vụ thật.
5. Một phiên đăng nhập bất thường được tạo.
6. Attacker cố thay email khôi phục và thêm authenticator mới.

### Các lớp phòng thủ

- Email gateway và DMARC giúp phát hiện một số dạng giả mạo sender.
- Domain monitoring phát hiện domain lookalike.
- Trang login chính thức ưu tiên passkey/WebAuthn.
- Password manager không tự động điền credential cho domain lạ.
- Risk engine nhận diện thiết bị/session mới và chuỗi thay đổi recovery bất thường.
- Policy yêu cầu step-up chống phishing trước khi thêm authenticator hoặc đổi recovery.
- Security team revoke session/token, xử lý password và recovery, điều tra hoạt động sau login.
- Người dùng được thông báo qua kênh chính thức và hướng dẫn báo cáo email.

### Bài học

Một password đúng và một OTP đúng không chứng minh người dùng đang tương tác với website thật. Cần origin-bound authentication, session protection, recovery security và monitoring sau đăng nhập.

## 20. Kiểm thử credential harvesting defense

| Kịch bản | Cách kiểm tra an toàn | Kết quả mong đợi |
| --- | --- | --- |
| Domain lookalike | Dùng domain mô phỏng trong môi trường test và kiểm tra cảnh báo. | Người dùng/controls nhận diện được domain ngoài allowlist. |
| HTTPS trên domain giả | Dùng chứng chỉ test hợp lệ cho domain mô phỏng. | Không coi TLS/ổ khóa là bằng chứng thương hiệu. |
| Email spoofing | Kiểm tra mail từ nguồn không được phép trong lab. | SPF/DKIM/DMARC và gateway xử lý theo policy. |
| Email từ tài khoản bị chiếm giả định | Dùng test account gửi thông điệp mô phỏng. | Detection không chỉ dựa vào sender domain. |
| QR link | Quét QR mô phỏng tới domain test. | URL đích hiển thị và được kiểm tra trước đăng nhập. |
| OTP relay simulation | Mô phỏng luồng test không chứa OTP thật. | Training nhận diện yêu cầu đọc mã; hệ thống ưu tiên phishing-resistant auth. |
| Passkey origin mismatch | Gửi WebAuthn assertion không đúng origin/RP ID trong test. | RP từ chối assertion. |
| Challenge replay | Gửi lại challenge/assertion đã dùng. | Server từ chối theo one-time/expiry policy. |
| Push fatigue | Tạo push test không do người dùng khởi tạo. | Có rate limit, cảnh báo và nút report/deny. |
| OAuth consent quá rộng | Dùng test app xin scope vượt policy. | Consent bị chặn hoặc yêu cầu admin approval. |
| OAuth grant sau incident | Revoke grant mô phỏng đã cấp. | Token/grant không còn được chấp nhận theo cơ chế triển khai. |
| Session cookie exposure drill | Dùng session giả trong môi trường kiểm thử. | Cookie không xuất hiện trong log; revoke server-side hoạt động. |
| Recovery code compromise | Đánh dấu code test là đã lộ. | Code bị revoke/rotate và không dùng lại được. |
| Post-login changes | Tạo chuỗi login lạ rồi thêm authenticator test. | Step-up/hold và audit được kích hoạt. |
| Phishing report | Người dùng gửi mẫu qua kênh báo cáo. | SOC nhận đủ header/URL an toàn và có correlation ID. |
| Domain takedown drill | Chạy tabletop với domain mô phỏng. | Chủ sở hữu, registrar và abuse contacts được xác định. |
| Incident recovery | Mô phỏng password/OTP/token bị lộ. | Password, session, refresh token, grant và authenticator được xử lý đúng scope. |
| Telemetry review | Kiểm tra log sau bài tập. | Không có secret, raw token hoặc recovery code. |

## 21. Checklist triển khai

- [ ] Đã xác định credential/token nào có thể bị thu thập và hậu quả của từng loại.
- [ ] Domain đăng nhập, hỗ trợ và recovery chính thức được công bố rõ.
- [ ] Có bảo vệ domain/DNS registrar và giám sát domain lookalike.
- [ ] SPF, DKIM, DMARC được cấu hình và theo dõi phù hợp.
- [ ] Email gateway và browser controls có kênh báo cáo phishing.
- [ ] Người dùng được hướng dẫn kiểm tra domain và không đọc OTP/recovery code.
- [ ] Trang đăng nhập ưu tiên passkey/WebAuthn cho các trường hợp phù hợp.
- [ ] WebAuthn kiểm tra challenge, origin, RP ID, chữ ký và user verification theo policy.
- [ ] MFA push có chống fatigue, rate limit và thông tin ngữ cảnh.
- [ ] Password manager được khuyến khích; password riêng cho mỗi dịch vụ.
- [ ] OAuth consent có kiểm soát publisher, scope và admin approval.
- [ ] Session cookie được bảo vệ; server có thể revoke session nhanh.
- [ ] Recovery và authenticator changes yêu cầu xác thực phù hợp, notification và audit.
- [ ] Detection tương quan email/report với login, session, consent và post-login changes.
- [ ] Có quy trình revoke password, OTP/recovery code, session, token và OAuth grant theo loại sự cố.
- [ ] Không log password, OTP, private key, cookie, raw token hoặc recovery secret.
- [ ] Phishing simulation có phê duyệt và không thu thập secret thật.
- [ ] Có incident playbook, domain takedown và thông báo người dùng.
- [ ] Đo tỷ lệ báo cáo, false positive, thời gian phát hiện và thời gian containment.

## 22. Tự kiểm tra

**Câu 1.** Credential harvesting là gì?

**Đáp án:** Là hành vi lừa hoặc ép người dùng tiết lộ dữ liệu xác thực như password, OTP, recovery code, token hoặc cấp quyền cho ứng dụng không đáng tin.

**Câu 2.** Vì sao HTTPS không chứng minh một trang đăng nhập thuộc tổ chức thật?

**Đáp án:** HTTPS bảo vệ kết nối tới domain đang truy cập. Attacker cũng có thể có chứng chỉ hợp lệ cho domain lookalike; người dùng vẫn phải xác minh đúng hostname/domain.

**Câu 3.** Credential harvesting khác credential stuffing như thế nào?

**Đáp án:** Harvesting thu thập credential từ người dùng; stuffing dùng các cặp credential đã có để thử đăng nhập hàng loạt vào dịch vụ khác.

**Câu 4.** Vì sao OTP có thể bị đánh cắp dù tài khoản bật MFA?

**Đáp án:** Người dùng có thể nhập OTP vào trang giả hoặc bị lừa đọc mã cho attacker. Một số luồng AiTM có thể relay OTP trong thời gian thực.

**Câu 5.** WebAuthn giúp chống phishing bằng cách nào?

**Đáp án:** Assertion được ràng buộc với RP ID/origin và challenge. Trang giả ở domain khác không thể yêu cầu authenticator tạo chữ ký có thể dùng cho RP thật.

**Câu 6.** OAuth consent phishing có cần lấy password không?

**Đáp án:** Không nhất thiết. Người dùng có thể cấp quyền cho ứng dụng độc hại qua trang consent thật của IdP; attacker sau đó sử dụng grant/token được cấp.

**Câu 7.** Nếu password bị nhập vào trang giả, chỉ đổi password đã đủ không?

**Đáp án:** Chưa chắc. Cần kiểm tra và revoke session cookie, refresh token, OAuth grant, recovery code và authenticator bị thay đổi; điều tra hoạt động sau login.

**Câu 8.** DMARC có ngăn mọi email phishing không?

**Đáp án:** Không. Nó giúp chống giả mạo domain theo alignment policy, nhưng không ngăn domain lookalike, tài khoản gửi thật bị chiếm hoặc ứng dụng OAuth độc hại.

**Câu 9.** Helpdesk có nên yêu cầu người dùng đọc OTP để xác minh danh tính không?

**Đáp án:** Không. OTP là secret dành cho người dùng và hệ thống xác thực; helpdesk phải dùng quy trình xác minh độc lập, không yêu cầu đọc mã.

**Câu 10.** Một chương trình phishing simulation an toàn cần nguyên tắc nào?

**Đáp án:** Có phê duyệt và phạm vi rõ, dùng môi trường kiểm soát, không thu thập password/OTP/token thật, bảo vệ dữ liệu đo lường và tập trung vào học tập, báo cáo, cải thiện quy trình.

## Ghi nhớ

**Credential harvesting** là việc lừa người dùng tiết lộ password, OTP, recovery code, session cookie, token hoặc cấp quyền cho ứng dụng độc hại. Kênh phổ biến gồm email, SMS, QR, cuộc gọi, trang đăng nhập giả và OAuth consent. HTTPS, logo, tên hiển thị và OTP không tự chứng minh người dùng đang tương tác với dịch vụ thật.

Phòng thủ cần bảo vệ domain và email, ưu tiên passkey/WebAuthn có origin binding, kiểm soát OAuth consent, bảo vệ session/recovery, phát hiện sự kiện sau login và cung cấp kênh báo cáo dễ dùng. Khi có lộ lọt, phải xử lý đúng từng loại credential: reset password, revoke session/token/grant, rotate recovery code, kiểm tra authenticator và thông báo qua kênh tin cậy. **Mục tiêu là làm cho một lần người dùng bị lừa không trở thành quyền truy cập lâu dài của attacker, đồng thời giúp người dùng báo cáo và khôi phục an toàn.**
