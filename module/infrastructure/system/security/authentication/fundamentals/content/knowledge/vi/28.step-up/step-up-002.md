# Trigger step-up — Khi nào cần yêu cầu xác thực tăng cường?

> **Chương:** Step-up  
> **Chủ đề:** Trigger step-up

**Step-up authentication** là việc yêu cầu người dùng chứng minh lại danh tính bằng phương thức hoặc mức bảo đảm cao hơn trước khi tiếp tục một hành động cụ thể. Một session đang hoạt động có thể đủ để đọc nội dung thông thường, nhưng chưa đủ để thay đổi email khôi phục, thêm passkey, xuất dữ liệu nhạy cảm, phê duyệt thanh toán hoặc thực hiện thao tác quản trị. Hệ thống cần nhận biết thời điểm rủi ro hoặc mức nhạy cảm của hành động vượt quá mức xác thực hiện tại và kích hoạt step-up.

**Trigger step-up** là quy tắc quyết định *khi nào* cần nâng mức xác thực, dựa trên hành động, ngữ cảnh phiên, thời điểm xác thực gần nhất, tín hiệu rủi ro và yêu cầu chính sách. Trigger tốt phải gắn với một mục đích rõ ràng, có thể giải thích và kiểm thử; kết quả step-up phải gắn với đúng người dùng, phiên, hành động và khoảng thời gian được phép.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential, password, MFA, passkey, certificate, token, session, SSO và recovery. Người học sẽ thiết kế trigger dựa trên độ nhạy của hành động và thay đổi rủi ro, phân biệt reauthentication với step-up, xác minh authentication context và ngăn việc dùng lại kết quả step-up cho giao dịch khác.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích step-up authentication và phân biệt với đăng nhập mới, reauthentication và MFA enrollment.
2. Xác định trigger từ hành động nhạy cảm, tuổi của lần xác thực, thay đổi thiết bị, tín hiệu bất thường và chính sách tổ chức.
3. Phân loại hành động theo mức tác động và yêu cầu assurance tương ứng.
4. Thiết kế policy server-side kết hợp action, session context, risk signal và authentication method.
5. Yêu cầu xác thực mới qua password, MFA, passkey hoặc phương thức phù hợp với rủi ro.
6. Kiểm tra kết quả step-up theo auth_time, acr, amr hoặc trạng thái nội bộ đã xác minh.
7. Ràng buộc kết quả step-up với đúng session, purpose, resource và thời hạn.
8. Xử lý từ chối, timeout, yếu tố dự phòng, retry và tình huống không thể hoàn tất step-up.
9. Xây dựng test plan cho trigger, bypass, replay và race condition.

## 2. Step-up giải quyết vấn đề gì?

Một session không nên được xem là có cùng mức tin cậy trong toàn bộ vòng đời. Người dùng có thể đã đăng nhập từ nhiều giờ trước bằng password, nhưng hiện tại muốn thay đổi phương thức khôi phục hoặc xuất dữ liệu của cả tổ chức. Session vẫn hợp lệ, song bằng chứng xác thực có thể quá cũ hoặc không đủ mạnh cho hành động đó.

Step-up cho phép hệ thống yêu cầu thêm bằng chứng đúng lúc mà không buộc người dùng đăng nhập lại cho mọi thao tác.

### 2.1. Ví dụ

- Người dùng đọc tài liệu khóa học: session thông thường có thể đủ.
- Người dùng xem bảng điểm cá nhân: có thể yêu cầu session còn mới theo policy.
- Giảng viên xuất toàn bộ bảng điểm: cần xác thực gần đây và MFA/passkey theo policy.
- Quản trị viên thêm một tài khoản quản trị khác: cần phương thức chống phishing và xác nhận quyền hiện tại.
- Người dùng đổi email khôi phục hoặc thêm passkey: cần xác thực lại trước khi thay đổi credential.
- Hệ thống phát hiện session từ thiết bị hoặc vị trí bất thường: có thể yêu cầu step-up hoặc chặn hành động tùy rủi ro.

### 2.2. Vì sao không yêu cầu MFA ở mọi request?

Yêu cầu xác thực quá thường xuyên gây mệt mỏi, khiến người dùng chấp nhận prompt một cách máy móc, làm giảm khả năng phát hiện yêu cầu giả mạo và tăng tải hỗ trợ. Ngược lại, không có trigger khiến session cũ hoặc bị đánh cắp có thể thực hiện hành động nhạy cảm.

Mục tiêu là **yêu cầu đúng mức xác thực tại đúng thời điểm, cho đúng hành động**. Không dùng một điểm rủi ro tổng quát thay thế việc phân loại tác động nghiệp vụ.

## 3. Phân biệt step-up, reauthentication và MFA

Các khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Authentication** | Thiết lập danh tính khi bắt đầu truy cập | Đăng nhập bằng passkey |
| **MFA** | Dùng nhiều yếu tố/phương thức theo mô hình xác thực | Password và security key |
| **Reauthentication** | Xác thực lại để chứng minh người dùng vẫn kiểm soát credential | Nhập lại password trước khi đổi email |
| **Step-up** | Nâng mức xác thực hoặc độ mới của bằng chứng cho một hành động | Yêu cầu passkey UV trước khi cấp quyền admin |
| **Credential enrollment** | Thêm phương thức xác thực mới vào account | Đăng ký passkey thứ hai |
| **Transaction confirmation** | Xác nhận một giao dịch cụ thể và nội dung của nó | Xác nhận người nhận và số tiền |

Reauthentication có thể chỉ lặp lại cùng phương thức, trong khi step-up có thể yêu cầu phương thức mạnh hơn, MFA hoặc assurance class cao hơn. Một prompt nhập lại password không tự động tạo ra phishing resistance hoặc MFA.

MFA cũng không tự động đồng nghĩa step-up thành công. Hệ thống phải biết phương thức đã dùng, mức assurance được xác minh và hành động đang yêu cầu.

## 4. Những nhóm trigger chính

Trigger nên đến từ một hoặc nhiều nhóm sau. Hệ thống cần kết hợp chúng với policy và ngữ cảnh thay vì yêu cầu người dùng step-up chỉ vì một tín hiệu yếu đơn lẻ.

### 4.1. Trigger theo độ nhạy của hành động

Đây thường là nhóm trigger dễ giải thích và ổn định nhất:

- Thay đổi password, email, số điện thoại hoặc recovery channel;
- Thêm, gỡ hoặc thay đổi passkey, MFA authenticator, security key hay certificate;
- Tạo API key, personal access token hoặc credential tích hợp;
- Liên kết/gỡ liên kết IdP hoặc tài khoản bên ngoài;
- Xem, xuất hoặc tải dữ liệu cá nhân/nhạy cảm;
- Phê duyệt thanh toán, hoàn tiền hoặc thay đổi thông tin nhận tiền;
- Thay đổi role, quyền quản trị, tenant owner hoặc policy bảo mật;
- Thực hiện hành động có tính không thể đảo ngược hoặc ảnh hưởng nhiều người.

Hành động có tác động lớn nên có trigger rõ trong policy. Không chỉ dựa vào giao diện: API phải tự xác định action nhạy cảm và yêu cầu step-up ngay cả khi được gọi trực tiếp.

### 4.2. Trigger theo độ mới của authentication

Một session có thể vẫn còn hiệu lực nhưng lần xác thực gần nhất đã quá lâu đối với hành động đang thực hiện.

Ví dụ:

- Quản trị viên phải xác thực trong 5 phút gần nhất trước khi thay đổi policy;
- Người dùng phải xác thực lại trước khi thay recovery email;
- Giao dịch có giá trị cao yêu cầu step-up trong một cửa sổ ngắn;
- Phiên hỗ trợ khách hàng cần reauthentication trước khi xem dữ liệu định danh.

Giá trị thời gian phải dựa trên risk assessment và tiêu chuẩn nội bộ. Không có một thời hạn chung phù hợp mọi sản phẩm. Cần phân biệt:

- **Session age:** thời gian từ khi session được tạo;
- **Authentication age:** thời gian từ lần người dùng thực sự xác thực;
- **Step-up age:** thời gian từ lần hoàn tất step-up cho purpose cụ thể.

Refresh access token hoặc cập nhật last_seen không làm cho authentication trở nên mới hơn. Không thay auth_time bằng iat của access token hoặc ID token mới được phát hành.

### 4.3. Trigger theo thay đổi ngữ cảnh

Các tín hiệu có thể cho thấy session đang được dùng trong điều kiện khác thường:

- Thiết bị mới hoặc thiết bị chưa được đăng ký;
- Browser profile, hệ điều hành hoặc client context thay đổi đáng kể;
- IP/network thay đổi bất thường theo bối cảnh;
- Đăng nhập từ vị trí địa lý không phù hợp với hoạt động gần đây;
- Session chuyển từ mạng đáng tin cậy sang mạng có rủi ro cao;
- Thiết bị không còn tuân thủ yêu cầu quản lý của tổ chức;
- Session có dấu hiệu bị chia sẻ hoặc sử dụng đồng thời bất thường.

Đây là tín hiệu rủi ro, không phải bằng chứng danh tính chắc chắn. IP có thể đổi vì mạng di động, VPN, NAT hoặc roaming; user-agent có thể bị giả mạo. Không nên khóa tài khoản hoặc ép step-up liên tục chỉ vì địa chỉ IP thay đổi.

### 4.4. Trigger theo hành vi bất thường

Ví dụ:

- Tải dữ liệu với tốc độ hoặc số lượng khác xa hành vi bình thường;
- Thực hiện nhiều thao tác nhạy cảm trong thời gian ngắn;
- Thay đổi nhiều credential/recovery setting liên tiếp;
- Tạo nhiều API key hoặc invitation;
- Thử truy cập nhiều tenant/resource không liên quan;
- Hoạt động sau một cảnh báo compromise hoặc password reset.

Hành vi bất thường cần được đánh giá theo loại account, công việc và lịch sử có liên quan. Một giảng viên tải nhiều bảng điểm trong thời điểm kết thúc học kỳ có thể là hành vi hợp lệ; một tài khoản học viên tải cùng lượng dữ liệu có thể đáng ngờ.

### 4.5. Trigger theo thay đổi trạng thái danh tính

Step-up hoặc từ chối hành động có thể được yêu cầu khi:

- Password vừa được reset;
- MFA/passkey vừa được thêm hoặc gỡ;
- Recovery channel vừa thay đổi;
- Tài khoản vừa được khôi phục sau suspension;
- Người dùng vừa liên kết một IdP mới;
- Tenant membership hoặc role vừa thay đổi;
- Có cảnh báo credential compromise.

Trong một số trường hợp, step-up không đủ. Nếu tài khoản đang bị suspend hoặc có bằng chứng compromise, phải chặn và đi vào quy trình recovery/incident response thay vì chỉ yêu cầu thêm MFA.

### 4.6. Trigger theo chính sách tổ chức hoặc pháp lý

Tổ chức có thể yêu cầu:

- MFA cho mọi tài khoản quản trị;
- Phương thức chống phishing cho thao tác quản trị quan trọng;
- Reauthentication khi truy cập dữ liệu thuộc nhóm được bảo vệ;
- Step-up khi làm việc ngoài thiết bị/mạng được quản lý;
- Authentication context cụ thể theo hợp đồng IdP hoặc quy định áp dụng.

Policy phải có owner, phạm vi, lý do và quy trình thay đổi. Không để mỗi ứng dụng tự diễn giải mức assurance theo cách khác nhau.

## 5. Phân loại hành động và yêu cầu assurance

Một ma trận action-to-assurance giúp các nhóm phát triển áp dụng policy nhất quán.

| Nhóm hành động | Tác động nếu bị lạm dụng | Trigger gợi ý |
| --- | --- | --- |
| Đọc nội dung thông thường | Thấp | Session hợp lệ |
| Cập nhật hồ sơ không nhạy cảm | Trung bình | Session hợp lệ; step-up khi ngữ cảnh rủi ro cao |
| Xem dữ liệu cá nhân nhạy cảm | Cao | Authentication gần đây hoặc MFA theo policy |
| Xuất dữ liệu số lượng lớn | Cao | Step-up, giới hạn export và audit |
| Đổi password/recovery channel | Rất cao | Reauthentication mạnh; thông báo và cooldown nếu phù hợp |
| Thêm/gỡ passkey hoặc MFA | Rất cao | Step-up với credential hiện có; không chỉ tin session |
| Tạo API key hoặc certificate | Cao/rất cao | MFA/passkey, giới hạn scope, hiển thị secret một lần |
| Cấp role quản trị | Rất cao | Phương thức chống phishing, approval và audit |
| Phê duyệt giao dịch giá trị cao | Rất cao | Step-up và xác nhận nội dung giao dịch |
| Khôi phục account | Rất cao | Recovery proofing và kiểm soát riêng; không bypass bằng step-up thông thường |

Các nhãn thấp/trung bình/cao là ví dụ để thiết kế policy, không phải phân loại pháp lý. Mỗi tổ chức cần đánh giá hậu quả, khả năng đảo ngược, phạm vi dữ liệu và threat model của mình.

### 5.1. Phương thức cần yêu cầu

Không phải mọi phương thức đều có cùng mức bảo đảm:

- **Password:** chứng minh người dùng biết bí mật; có thể bị phishing hoặc reuse.
- **OTP qua SMS/email:** dễ triển khai nhưng có rủi ro phishing, SIM swap, chuyển tiếp hoặc chiếm hộp thư.
- **TOTP:** giảm phụ thuộc SMS nhưng mã vẫn có thể bị phishing/relay theo thời gian.
- **Push approval:** cần chống push fatigue và ưu tiên number matching/context display.
- **Passkey/WebAuthn:** có thể chống phishing nhờ ràng buộc RP ID/origin; kiểm tra user verification theo policy.
- **Security key:** phù hợp thao tác đặc quyền khi được enrollment và xác minh đúng.
- **Client certificate:** chứng minh quyền kiểm soát private key trong ngữ cảnh TLS; cần kiểm tra chain, purpose và principal.

Yêu cầu step-up phải nói rõ loại phương thức hoặc mức assurance chấp nhận. Không ghi chung “MFA required” nếu một OTP qua SMS và một security key được xem như tương đương trong policy của hệ thống.

## 6. Đánh giá rủi ro: kết hợp hành động và ngữ cảnh

Một policy step-up thường có hai trục:

1. **Inherent risk:** mức rủi ro vốn có của hành động, bất kể ai thực hiện;
2. **Contextual risk:** tín hiệu về session, thiết bị, vị trí, hành vi và trạng thái account tại thời điểm đó.

Hành động cấp quyền admin có inherent risk cao nên luôn cần step-up. Một hành động đọc thông tin thông thường có thể chỉ cần step-up khi contextual risk tăng đáng kể.

~~~mermaid
flowchart TD
    A["Request tới action/resource"] --> B["Xác thực session và account state"]
    B --> C["Phân loại inherent action risk"]
    C --> D["Đánh giá context: auth age, device, behavior, network"]
    D --> E{"Đủ assurance hiện tại?"}
    E -->|"Có"| F["Kiểm tra authorization"]
    E -->|"Không"| G["Tạo step-up challenge cho purpose"]
    G --> H{"Step-up đạt policy?"}
    H -->|"Không / hết hạn"| I["Từ chối hoặc yêu cầu recovery/support"]
    H -->|"Có"| J["Gắn proof với session + action + TTL"]
    J --> F
    F --> K{"Được phép?"}
    K -->|"Có"| L["Thực hiện action và audit"]
    K -->|"Không"| M["Deny"]
~~~

### 6.1. Không dùng risk score như quyết định duy nhất

Risk engine có thể trả về điểm hoặc mức low/medium/high, nhưng quyết định cần được ràng buộc với policy cụ thể. Ví dụ:

- Hành động admin luôn yêu cầu passkey/security key dù risk score thấp;
- Tải dữ liệu cá nhân cần auth_time gần đây;
- Đăng nhập từ thiết bị lạ có thể yêu cầu step-up, nhưng tài khoản đang suspended phải bị chặn;
- Một IP bất thường không tự động chứng minh compromise.

Không cho một điểm risk thấp ghi đè yêu cầu assurance bắt buộc của action. Cũng không để một tín hiệu yếu đơn lẻ tạo ra step-up vô hạn hoặc khóa tài khoản.

### 6.2. Tín hiệu rủi ro phải có nguồn và độ tin cậy

Mỗi signal nên có source, timestamp, độ tin cậy và thời hạn sử dụng. Device posture từ MDM có thể đáng tin hơn user-agent; vị trí suy ra từ IP có thể không chính xác. Dữ liệu cũ không nên tiếp tục ảnh hưởng quyết định như thể nó vừa xảy ra.

### 6.3. Chế độ fail

Khi risk service hoặc device posture provider không khả dụng, policy phải quy định:

- Hành động bắt buộc assurance cao: fail closed hoặc chuyển sang phương thức xác minh thay thế đã được duyệt;
- Hành động rủi ro thấp: có thể tiếp tục theo baseline policy;
- Không tự động hạ assurance chỉ vì dịch vụ đánh giá rủi ro bị lỗi;
- Ghi nhận degraded mode và cảnh báo vận hành.

## 7. Trigger theo độ mới của authentication

Độ mới cần dựa trên thời điểm xác thực thực sự, không phải thời điểm token được refresh.

### 7.1. Ba mốc thời gian

| Mốc | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| **auth_time** | Lần người dùng được xác thực tại OP/IdP | iat của token |
| **session_created_at** | Thời điểm RP tạo session | Lần step-up gần nhất |
| **step_up_at** | Thời điểm hoàn tất step-up cho một purpose | last_seen hoặc access-token refresh |

Nếu user đăng nhập lúc 09:00, refresh access token lúc 14:00 và thực hiện hành động nhạy cảm lúc 15:00, auth_time vẫn có thể là 09:00. Không được coi token mới phát hành lúc 14:00 là bằng chứng người dùng vừa xác thực.

### 7.2. Max authentication age

Policy có thể quy định authentication không được cũ hơn một khoảng thời gian:

~~~text
if now - session.auth_time > policy.max_auth_age:
    require_step_up(reason = "AUTHENTICATION_TOO_OLD")
~~~

Giá trị max_auth_age cần gắn với action và assurance. Với thao tác quản trị, có thể là vài phút; với dữ liệu ít nhạy cảm, có thể không cần giới hạn riêng. Các con số phải được quyết định theo rủi ro và trải nghiệm.

### 7.3. Xác thực lại tại IdP

Với OIDC, RP có thể yêu cầu xác thực gần đây bằng max_age hoặc yêu cầu authentication context theo hợp đồng với OP. Sau callback, RP vẫn phải kiểm tra auth_time, acr/amr và các claim liên quan. Chỉ gửi tham số yêu cầu không chứng minh IdP đã thực hiện step-up.

Với SAML, SP có thể yêu cầu AuthnContext hoặc ForceAuthn theo profile/khả năng IdP; sau đó xác minh AuthnContext và thời điểm xác thực trong assertion. Không giả định mọi IdP diễn giải cùng một context URI giống nhau.

## 8. Trigger khi thêm hoặc thay đổi credential

Các thao tác thay đổi credential có rủi ro đặc biệt: nếu attacker đã chiếm session, họ có thể thêm phương thức do mình kiểm soát rồi tiếp tục truy cập sau khi nạn nhân đổi password.

### 8.1. Thêm passkey

Yêu cầu step-up bằng credential đã có trước khi tạo WebAuthn challenge. Challenge phải gắn với account, session và purpose “add passkey”. Sau khi xác minh registration response, thông báo tới kênh đã đăng ký. Không cho phép passkey vừa được tạo tự xác minh chính thao tác thêm nó.

### 8.2. Thay MFA authenticator

Gỡ authenticator cũ hoặc thay số điện thoại phải yêu cầu phương thức hiện tại hoặc recovery proofing đủ mạnh. Nếu người dùng mất thiết bị, đi vào recovery flow có kiểm soát; không cho helpdesk bypass chỉ bằng thông tin công khai.

### 8.3. Đổi password và recovery channel

Trước khi đổi password/email/phone, yêu cầu reauthentication hoặc step-up. Sau thay đổi, thu hồi hoặc đánh giá lại session, refresh token và authenticator theo policy. Gửi thông báo tới kênh cũ nếu còn tin cậy và áp dụng cooldown khi hành động có nguy cơ bị chiếm dụng.

### 8.4. Liên kết IdP hoặc tài khoản

Yêu cầu xác thực lại tài khoản hiện tại trước khi liên kết IdP mới. Kết quả từ IdP mới chỉ chứng minh subject tại issuer đó; RP phải kiểm tra subject chưa gắn với account khác và yêu cầu xác nhận. Không liên kết chỉ vì email trùng.

## 9. Trigger theo session và thiết bị

Session context cung cấp tín hiệu về lần xác thực, client và trạng thái thiết bị. Cần xác định tín hiệu nào đủ tin cậy để kích hoạt step-up.

### 9.1. Session mới hoặc session bị thay đổi

Có thể yêu cầu step-up khi:

- Session vừa được tạo từ recovery;
- Session được khôi phục sau thời gian dài;
- Session credential có dấu hiệu bị sao chép;
- Thiết bị mới thực hiện hành động có tác động lớn;
- Session được tạo bằng phương thức yếu hơn yêu cầu của action;
- Session có trạng thái hoặc version không đồng nhất.

### 9.2. Device posture

Thiết bị quản lý có thể cung cấp trạng thái mã hóa, lock screen, OS patch hoặc compliance. Nếu policy yêu cầu thiết bị đạt chuẩn, step-up trên một thiết bị không tuân thủ có thể không đủ; cần chặn action hoặc yêu cầu chuyển sang thiết bị được quản lý.

### 9.3. IP và vị trí

Không gắn cứng session với IP. Hãy dùng thay đổi IP/vị trí như tín hiệu cùng các bằng chứng khác, có ngưỡng và thời gian hợp lý. Ví dụ “impossible travel” chỉ là chỉ báo, vì VPN, proxy và dữ liệu định vị sai có thể tạo false positive.

## 10. Trigger theo hành vi và giao dịch

Đối với hành động có tác động tài chính hoặc dữ liệu lớn, trigger nên gắn với chính giao dịch đang được thực hiện.

### 10.1. Transaction confirmation

Step-up xác nhận người dùng hiện diện và kiểm soát credential, nhưng chưa chắc bảo vệ nội dung giao dịch khỏi bị thay đổi sau khi xác nhận. Nếu cần xác nhận nội dung, challenge phải gắn với các thuộc tính quan trọng:

- Người nhận hoặc tài khoản đích;
- Số tiền/đơn vị tiền tệ;
- Loại hành động;
- Tài nguyên hoặc phạm vi dữ liệu;
- Mã giao dịch duy nhất;
- Thời điểm và thời hạn.

Nếu nội dung thay đổi sau khi người dùng xác nhận, challenge cũ phải mất hiệu lực và cần xác nhận lại. Với thanh toán hoặc phê duyệt quan trọng, cân nhắc transaction signing/confirmation phù hợp thay vì chỉ yêu cầu OTP chung.

### 10.2. Export dữ liệu

Khi xuất dữ liệu, step-up có thể là điều kiện cần nhưng chưa đủ. Kết hợp:

- Authorization theo tenant, lớp học và loại dữ liệu;
- Giới hạn số bản ghi, tốc độ và định dạng;
- Audit người yêu cầu, thời điểm và phạm vi;
- Watermark hoặc kiểm soát tải xuống nếu phù hợp;
- Kiểm tra session và auth_time ngay trước khi tạo export job;
- Revoke/cancel job nếu account bị suspend trong lúc xử lý.

### 10.3. Hành động nhiều bước

Nếu quy trình gồm tạo yêu cầu rồi phê duyệt, step-up có thể cần ở bước phê duyệt hoặc ngay trước commit. Không chỉ kiểm tra ở đầu quy trình rồi để một phiên dài hạn tiếp tục thực hiện mọi bước mà không đánh giá thay đổi.

## 11. Policy engine và quyết định step-up

Trigger nên được mô tả thành policy rõ ràng, có thể version hóa, audit và kiểm thử.

### 11.1. Đầu vào của policy

- Principal và account state;
- Tenant, client/application và resource;
- Action hoặc transaction type;
- Session ID/reference và trạng thái;
- auth_time, auth_method, acr/amr hoặc assurance nội bộ;
- step_up_at, step_up_purpose và expiry;
- Device posture, network/context và risk signals;
- Yêu cầu assurance tối thiểu của action;
- Phương thức dự phòng được phép.

### 11.2. Đầu ra của policy

Policy có thể trả:

- **ALLOW:** bằng chứng hiện tại đủ và authorization tiếp tục;
- **STEP_UP:** yêu cầu một assurance/method cụ thể;
- **DENY:** account/action không được phép hoặc có rủi ro không thể xử lý bằng step-up;
- **RECOVERY_REQUIRED:** credential/account cần được khôi phục hoặc điều tra;
- **REVIEW_REQUIRED:** cần approval/human review.

Không gộp DENY với STEP_UP. Nếu user không thuộc tenant hoặc account bị suspended, yêu cầu MFA thêm không làm hành động trở nên hợp lệ.

### 11.3. Ví dụ policy

~~~text
policy: publish_grades
  action_risk: HIGH
  required_assurance: PHISHING_RESISTANT
  max_auth_age: 5 minutes
  allowed_methods:
    - passkey_with_user_verification
    - managed_security_key
  require_current_tenant_membership: true
  require_account_active: true
  on_step_up_failure: DENY

policy: view_course_material
  action_risk: LOW
  required_assurance: BASELINE_SESSION
  max_auth_age: none
  on_contextual_risk: STEP_UP_OR_DENY_BY_SIGNAL
~~~

Đây là ví dụ minh họa, không phải giá trị chuẩn cho mọi hệ thống. Policy thực tế cần xác định chính xác phương thức, nguồn assurance, timeout và cách xử lý lỗi.

## 12. Gắn kết quả step-up với đúng hành động

Một step-up thành công không nên trở thành giấy phép chung cho mọi hành động trong thời gian dài. Kết quả cần được ràng buộc:

- Principal/subject;
- Session hoặc authentication transaction;
- Tenant/client;
- Purpose/action;
- Resource hoặc transaction reference khi cần;
- Assurance/method đã đạt;
- auth_time/step_up_at;
- Thời hạn hiệu lực;
- Trạng thái consumed/revoked.

### 12.1. Purpose binding

Ví dụ, step-up để thêm passkey không tự động cho phép xuất bảng điểm hoặc thay recovery email. Nếu người dùng đổi action trong khi challenge đang chờ, server phải đánh giá lại policy và có thể tạo challenge mới.

### 12.2. One-time action grant

Với thao tác rất nhạy cảm, kết quả step-up có thể cấp một grant dùng một lần gắn với transaction ID. Server tiêu thụ grant nguyên tử khi thực hiện action. Điều này giảm nguy cơ người dùng hoàn tất một challenge rồi attacker dùng lại kết quả cho một request khác.

### 12.3. Không tin client báo đã step-up

Client có thể hiển thị màn hình “verified”, nhưng server phải xác minh bằng chứng do IdP/authenticator phát hành và cập nhật trạng thái server-side. Không nhận một boolean như step_up=true từ browser/app làm bằng chứng.

## 13. Step-up trong OIDC và SAML

Khi dùng federation, RP có thể yêu cầu IdP thực hiện xác thực gần đây hoặc mức assurance cụ thể. RP vẫn phải kiểm tra kết quả trả về.

### 13.1. OIDC

Các tham số thường liên quan:

- **max_age:** yêu cầu thời điểm xác thực gần nhất không cũ hơn khoảng quy định;
- **prompt=login:** yêu cầu OP tương tác đăng nhập theo semantics của OIDC;
- **acr_values:** yêu cầu một authentication context class;
- **auth_time:** claim dùng để kiểm tra độ mới khi được yêu cầu;
- **acr/amr:** context và phương thức xác thực được OP báo cáo.

RP cần hiểu mapping với từng OP. Một OP có thể không hỗ trợ context cụ thể hoặc có thể trả context thấp hơn; RP phải từ chối action nếu policy không đạt. Không coi prompt=login là bằng chứng MFA hoặc phishing resistance.

### 13.2. SAML

SAML có thể dùng AuthnRequest với ForceAuthn hoặc RequestedAuthnContext theo profile. SP kiểm tra AuthnInstant và AuthnContextClassRef trong assertion. Các URI/context phải được hai bên thống nhất; không tự suy luận mức bảo đảm từ tên chuỗi.

### 13.3. Local authentication

Nếu ứng dụng tự quản lý password/MFA/passkey, verifier phải ghi lại kết quả xác thực và thời điểm theo server-side context. Step-up không được dựa vào claim do client tự gửi hoặc một trường last_login cập nhật khi refresh token.

## 14. UX và cách xử lý khi step-up thất bại

Prompt step-up cần nói rõ vì sao hệ thống yêu cầu thêm xác thực và người dùng đang xác nhận hành động nào. Không tiết lộ chi tiết detection có thể giúp attacker né kiểm soát.

### 14.1. Prompt rõ ràng

Ví dụ thông báo:

- “Để thay đổi email khôi phục, hãy xác thực lại bằng passkey.”
- “Bạn cần xác nhận lại danh tính trước khi xuất bảng điểm của trường.”
- “Phiên này đã đăng nhập từ lâu. Hãy xác thực lại trước khi thay đổi quyền quản trị.”

Tránh prompt mơ hồ như “Security check required” mà không có ngữ cảnh hành động.

### 14.2. Không có phương thức được yêu cầu

Nếu người dùng không có security key/passkey phù hợp:

- Cung cấp phương thức thay thế đã được policy phê duyệt;
- Nếu không có phương thức đủ mạnh, chuyển sang recovery/support;
- Không tự hạ yêu cầu assurance chỉ để hoàn tất thao tác;
- Giải thích cách thiết lập phương thức phù hợp sau khi người dùng phục hồi account.

### 14.3. Timeout và hủy

Challenge cần TTL và transaction state. Nếu timeout hoặc người dùng hủy, action không được thực hiện. Nếu người dùng thử lại, tạo transaction mới theo policy; không tái sử dụng challenge đã hết hạn.

### 14.4. Giảm prompt fatigue

- Không trigger lại nhiều lần cho cùng một action khi bằng chứng vẫn còn hiệu lực;
- Dùng single-flight cho challenge đang diễn ra trong cùng session/purpose;
- Không gửi push liên tục; giới hạn số lần và cooldown;
- Hiển thị context/number matching cho push approval;
- Không để attacker dễ dàng tạo step-up prompt vô hạn nhằm gây phiền hoặc ép người dùng bấm chấp thuận.

## 15. Xử lý lỗi, retry và race condition

Step-up thường diễn ra qua nhiều request: bắt đầu challenge, xác minh credential, rồi thực hiện action. Cần bảo vệ tính nhất quán giữa các bước.

### 15.1. Challenge state

Mỗi challenge cần có:

- Challenge ID ngẫu nhiên;
- Subject, session, tenant và client;
- Purpose/action và resource/transaction binding;
- Phương thức/assurance yêu cầu;
- Thời điểm tạo, hết hạn và trạng thái;
- Nonce/challenge của authenticator hoặc IdP transaction;
- Số lần thử và trạng thái consumed.

### 15.2. Atomic consumption

Nếu hai request cùng xác minh một challenge, chỉ một request được tiêu thụ thành công. Nếu challenge dùng để phê duyệt giao dịch, transaction commit phải bảo đảm grant không bị dùng hai lần.

### 15.3. Session thay đổi trong lúc challenge

Nếu session bị revoke, account bị suspend, tenant membership bị xóa hoặc credential bị thay đổi trong khi step-up đang diễn ra, kết quả cũ không được tự động cấp quyền. Trước khi commit action, kiểm tra lại trạng thái principal/session và authorization.

### 15.4. Idempotency

Nếu response của action bị mất sau khi commit, client có thể retry. Cần idempotency key cho nghiệp vụ và lưu kết quả đã thực hiện. Không dùng lại challenge step-up như một cách retry action không giới hạn.

## 16. Threat model cho trigger step-up

| Threat | Mục tiêu attacker | Kiểm soát |
| --- | --- | --- |
| Session hijacking | Dùng session đánh cắp cho action nhạy cảm | Step-up, session risk, sender constraint và revoke |
| Stale authentication | Dùng lần login cũ để thay credential | Max auth age và reauthentication |
| MFA fatigue | Làm người dùng chấp thuận prompt giả | Context display, number matching, rate limit |
| Step-up bypass | Gọi API trực tiếp bỏ qua UI | Enforcement server-side tại action |
| Challenge replay | Dùng lại kết quả step-up | Nonce, purpose binding, TTL và one-time consumption |
| Cross-action reuse | Dùng proof cho action khác | Purpose/resource binding |
| Cross-tenant reuse | Dùng proof của tenant A tại tenant B | Tenant binding và current membership check |
| Risk signal spoofing | Làm giả device/IP/context để hạ yêu cầu | Nguồn tín hiệu tin cậy và policy baseline |
| Prompt DoS | Kích hoạt liên tục để làm phiền người dùng | Rate limit, single-flight, cooldown |
| Recovery bypass | Dùng recovery yếu để vượt step-up mạnh | Recovery assurance riêng, review và audit |
| TOCTOU | Session/role thay đổi sau khi step-up nhưng trước commit | Kiểm tra lại state và authorization ở điểm commit |

## 17. Ví dụ xuyên suốt: giảng viên xuất bảng điểm

Một giảng viên đã đăng nhập vào nền tảng học tập bằng password và MFA. Session còn hiệu lực nhưng authentication đã diễn ra từ nhiều giờ trước. Giảng viên muốn xuất bảng điểm của toàn bộ lớp.

### 17.1. Trigger

API nhận yêu cầu export và đánh giá:

1. Account đang active;
2. Membership của giảng viên trong tenant/lớp còn hiệu lực;
3. Action export có inherent risk cao;
4. auth_time vượt max_auth_age của policy;
5. Session chưa có step-up grant hợp lệ cho purpose export.

Policy trả STEP_UP, yêu cầu passkey có user verification hoặc security key theo cấu hình tổ chức.

### 17.2. Xác minh

1. Server tạo challenge gắn với subject, session, tenant, lớp học và export request.
2. Người dùng xác thực bằng phương thức được yêu cầu.
3. Verifier kiểm tra challenge, origin/RP ID hoặc authentication context từ IdP.
4. Server lưu step-up result với purpose export, thời hạn ngắn và transaction reference.
5. Trước khi tạo export job, server kiểm tra lại session, account, membership và quyền export.
6. Server tiêu thụ grant theo transaction, tạo job và audit phạm vi dữ liệu.

### 17.3. Điều gì xảy ra nếu request thay đổi?

Nếu người dùng thay lớp học, tenant hoặc phạm vi dữ liệu sau khi step-up, grant cũ không còn khớp. Server phải đánh giá lại authorization và yêu cầu challenge mới nếu transaction binding thay đổi.

### 17.4. Điều gì xảy ra nếu account bị khóa giữa chừng?

Nếu account bị suspend sau khi xác minh nhưng trước khi export job commit, server kiểm tra account state ở điểm commit và từ chối. Step-up không ghi đè trạng thái account hoặc membership.

## 18. Pseudocode policy và step-up flow

### 18.1. Quyết định trigger

~~~text
evaluate_action(request, session):
    require session_is_valid(session)
    require account_is_active(session.subject)

    policy = load_policy(
        tenant = request.tenant,
        action = request.action,
        resource = request.resource
    )
    require current_membership_and_authorization(session.subject, request)

    context = load_trusted_risk_context(session, request)
    current_assurance = verified_assurance(session)

    if policy.requires_phishing_resistant_method
       and not current_assurance.is_phishing_resistant:
        return STEP_UP(required_method = policy.allowed_methods)

    if policy.max_auth_age exists
       and now - current_assurance.auth_time > policy.max_auth_age:
        return STEP_UP(required_method = policy.allowed_methods)

    if context.risk_requires_step_up:
        return STEP_UP(required_method = policy.risk_methods)

    return ALLOW_TO_AUTHORIZATION
~~~

### 18.2. Tạo challenge

~~~text
begin_step_up(subject, session, request, policy):
    challenge = secure_random_value()
    create_server_side_transaction(
        challenge_hash = hash(challenge),
        subject = subject,
        session_ref = session.id,
        tenant = request.tenant,
        purpose = request.action,
        resource_ref = request.resource,
        transaction_ref = request.transaction_id,
        required_assurance = policy.assurance,
        allowed_methods = policy.allowed_methods,
        expires_at = now + policy.challenge_ttl,
        status = PENDING
    )
    return challenge_options_for_allowed_method()
~~~

### 18.3. Hoàn tất và thực hiện action

~~~text
complete_step_up_and_execute(challenge_id, proof, request):
    tx = load_challenge_for_update(challenge_id)
    require tx.status == PENDING
    require now < tx.expires_at
    require tx.subject == current_subject()
    require tx.session_ref == current_session()
    require tx.purpose == request.action
    require tx.resource_ref == request.resource
    verify_authenticator_or_idp_proof(proof, tx)
    require verified_assurance(proof) >= tx.required_assurance

    begin transaction
    recheck_account_session_membership_and_authorization(request)
    consume_challenge_once(tx)
    consume_step_up_grant_for_transaction(tx, request)
    execute_idempotent_action(request)
    write_audit_event_without_credentials()
    commit
~~~

Đây là pseudocode khái niệm. Triển khai thực tế cần thư viện xác thực đã được kiểm chứng, xử lý transaction boundary, phân tán session store, khóa đồng thời, rollback và side effect ngoài database. Nếu action gọi hệ thống ngoài, cần outbox/idempotency hoặc cơ chế commit tương ứng.

## 19. Kiểm thử trigger step-up

Test trong môi trường được phép với user, tenant, session và authenticator giả lập.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Baseline | Đọc tài liệu với session hợp lệ | Không yêu cầu step-up ngoài policy |
| Sensitive action | Thay recovery email | Bắt buộc step-up theo policy |
| Auth age | auth_time vượt max age | Trigger step-up |
| Token refresh | Access token vừa refresh nhưng auth_time cũ | Vẫn trigger nếu vượt max age |
| Assurance | Session password-only gọi action yêu cầu phishing resistance | Yêu cầu phương thức phù hợp |
| Wrong method | Người dùng dùng phương thức không nằm allowlist | Không cấp step-up grant |
| Wrong purpose | Challenge cho add-passkey dùng để export data | Từ chối |
| Wrong resource | Challenge cho lớp A dùng cho lớp B | Từ chối |
| Wrong tenant | Grant tenant A dùng ở tenant B | Từ chối |
| Expired challenge | Challenge hết hạn | Từ chối và yêu cầu transaction mới |
| Replay | Dùng lại challenge/grant đã consumed | Từ chối |
| Concurrent consume | Hai request tiêu thụ cùng challenge | Chỉ một request thành công |
| Session revoke | Session bị revoke trong lúc step-up | Không thực hiện action |
| Account suspend | Account bị suspend trước commit | DENY |
| Membership change | Role/tenant membership bị thu hồi giữa flow | DENY tại điểm commit |
| Risk signal | Thiết bị mới có tín hiệu rủi ro phù hợp | Trigger theo policy |
| Weak signal | Chỉ IP thay đổi do mobile network | Không tự động khóa account |
| Risk service outage | Risk engine không khả dụng | Áp dụng fail mode đã định, không tự hạ baseline |
| Prompt fatigue | Nhiều request cùng purpose trong một session | Single-flight/cooldown/rate limit |
| Transaction change | Số tiền/resource thay đổi sau xác nhận | Grant cũ không còn hợp lệ |
| API bypass | Gọi API trực tiếp không qua UI | Server vẫn enforce step-up |
| Logging | Bật audit/trace | Không log OTP, challenge secret, token hoặc private key |

### 19.1. Bất biến bảo mật

- Hành động bắt buộc step-up không thể thực hiện bằng cách bỏ qua giao diện;
- Kết quả step-up chỉ áp dụng cho đúng subject, session, purpose và resource;
- Token refresh không làm auth_time mới hơn;
- Challenge và grant chỉ được tiêu thụ một lần theo policy;
- Session/account/membership được kiểm tra lại trước khi commit;
- Step-up không vượt qua authorization hoặc account suspension;
- Không hạ assurance bắt buộc khi risk service gặp lỗi;
- Không ghi credential hoặc proof nhạy cảm vào log.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ trigger step-up ở UI | API trực tiếp bỏ qua kiểm soát | Enforcement tại server/API |
| Coi mọi MFA là ngang nhau | Phương thức yếu đáp ứng nhầm action mạnh | Allowlist method và assurance rõ |
| Dùng iat thay auth_time | Token refresh làm bằng chứng trông mới | Dùng thời điểm authentication thực |
| Step-up một lần cho mọi action | Proof bị dùng lại ngoài mục đích | Purpose/resource binding |
| Không có TTL hoặc one-time use | Challenge/grant bị replay | TTL, nonce và atomic consumption |
| Không kiểm tra lại authorization | Role bị thu hồi nhưng action vẫn chạy | Recheck tại điểm commit |
| Dùng IP làm điều kiện duy nhất | False positive và dễ né | Kết hợp signal có nguồn và confidence |
| Hạ policy khi IdP/risk service lỗi | Fail-open cho action nhạy cảm | Fail mode rõ và phương thức thay thế |
| Prompt liên tục | MFA fatigue và UX kém | Single-flight, cooldown, risk policy |
| Recovery yếu hơn step-up | Attacker đi đường recovery để bypass | Recovery assurance và review riêng |
| Không gắn giao dịch | Nội dung thay đổi sau xác nhận | Transaction binding/confirmation |
| Tin client báo step-up thành công | Boolean giả mạo | Server-side verification và state |

## 21. Checklist production

1. **Action inventory:** Đã liệt kê các hành động nhạy cảm và hậu quả nếu bị lạm dụng?
2. **Baseline assurance:** Mỗi action yêu cầu mức xác thực nào, có lý do và owner?
3. **Trigger:** Dựa trên action, auth age, session/device, behavior hay account state?
4. **Time semantics:** Phân biệt auth_time, session age và step_up_at?
5. **Method policy:** Phương thức được phép có đáp ứng phishing resistance/user verification khi cần?
6. **Server enforcement:** Mọi API path đều kiểm tra step-up, kể cả request không qua UI?
7. **Context:** Risk signal có nguồn, timestamp, confidence và TTL?
8. **Fail mode:** Risk/IdP outage không làm action nhạy cảm tự hạ assurance?
9. **Purpose binding:** Step-up gắn subject, session, tenant, action, resource và transaction?
10. **Freshness:** Challenge/grant có TTL và giới hạn reuse phù hợp?
11. **Atomicity:** Challenge/grant được consume một lần; race condition được xử lý?
12. **Commit check:** Account, session, membership và authorization được kiểm tra lại trước khi thực hiện?
13. **UX:** Prompt giải thích action, có phương thức thay thế được duyệt và hạn chế prompt fatigue?
14. **Recovery:** Người mất authenticator có recovery flow riêng, đủ assurance và audit?
15. **Monitoring:** Có metric trigger rate, completion, failure, false positive, abuse và latency?
16. **Privacy:** Không log proof, OTP, token hoặc thông tin thiết bị vượt mục đích?
17. **Testing:** Đã test replay, cross-purpose, cross-tenant, bypass, race, stale session và transaction tampering?

## 22. Bài tập tình huống

Một nền tảng học tập yêu cầu MFA khi đăng nhập. Sau khi đăng nhập, mọi session có trường mfa_verified=true trong 30 ngày. Người dùng có thể đổi email khôi phục, thêm passkey, xuất toàn bộ bảng điểm và cấp quyền quản trị mà không xác thực lại. Ứng dụng chỉ kiểm tra step-up ở frontend. Khi access token được refresh, backend cập nhật last_authenticated_at thành thời điểm hiện tại.

**Yêu cầu:**

1. Chỉ ra ít nhất **tám rủi ro** trong trigger, freshness, authorization và session handling.
2. Phân loại bốn hành động nhạy cảm theo inherent risk và yêu cầu assurance.
3. Thiết kế trigger dựa trên action và auth_time thay vì thời điểm refresh token.
4. Xác định phương thức step-up phù hợp cho thêm passkey và cấp quyền quản trị.
5. Thiết kế purpose/resource binding cho thao tác export bảng điểm.
6. Đề xuất enforcement server-side và kiểm tra lại quyền tại điểm commit.
7. Viết test cho challenge replay, cross-action reuse, API bypass và session bị revoke giữa flow.

**Gợi ý đối chiếu:** MFA lúc login không tạo quyền MFA vô thời hạn; refresh token không cập nhật auth_time; mỗi action có assurance riêng; step-up grant gắn purpose/resource/TTL; API phải enforce và recheck account/session/membership trước commit.

## 23. Ghi nhớ

- **Trigger step-up** quyết định khi nào bằng chứng xác thực hiện tại không đủ cho hành động hoặc ngữ cảnh đang diễn ra.
- Trigger ổn định nhất thường xuất phát từ độ nhạy của action; auth age, thiết bị, hành vi và trạng thái account bổ sung ngữ cảnh rủi ro.
- Phân biệt session age, auth_time và step_up_at. Refresh token hoặc hoạt động nền không làm lần xác thực trở nên mới hơn.
- Không phải mọi MFA đều có cùng assurance; action nhạy cảm có thể yêu cầu passkey/security key chống phishing hoặc context cụ thể.
- Step-up phải được enforce server-side và gắn với đúng subject, session, purpose, resource, transaction và TTL.
- Challenge/grant cần one-time consumption, chống replay và xử lý race; account/session/membership/authorization phải được kiểm tra lại trước commit.
- Step-up không thay thế authorization, recovery proofing hoặc xử lý account compromise; có trường hợp phải DENY hoặc chuyển sang recovery.

Trigger step-up an toàn khi hệ thống giải thích được **hành động nào cần thêm bằng chứng, vì sao session hiện tại chưa đủ, phương thức nào đáp ứng policy và kết quả chỉ được dùng trong phạm vi nào**. Điều đó giúp giảm prompt không cần thiết mà vẫn bảo vệ những thao tác có tác động lớn.
