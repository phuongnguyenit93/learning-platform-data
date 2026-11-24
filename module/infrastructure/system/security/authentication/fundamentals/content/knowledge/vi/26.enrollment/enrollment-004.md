# Đăng ký yếu tố MFA — Enrollment an toàn cho tài khoản

## 1. Đăng ký yếu tố MFA là gì?

**Đăng ký yếu tố MFA** (*MFA factor enrollment*) là quá trình liên kết một authenticator mới với một tài khoản để hệ thống có thể dùng nó trong những lần xác thực tiếp theo. Authenticator có thể là ứng dụng tạo mã TOTP, khóa bảo mật FIDO2, passkey, ứng dụng push, thiết bị giữ khóa mật mã hoặc một kênh OTP được chính sách cho phép.

Ví dụ: một nhân viên đã đăng nhập cổng công ty bằng passkey muốn thêm khóa bảo mật dự phòng. Server yêu cầu xác thực lại bằng yếu tố hiện có, tạo một WebAuthn challenge dành riêng cho tài khoản và giao dịch, rồi trình duyệt yêu cầu authenticator tạo credential. Server xác minh phản hồi, lưu credential ID cùng public key và chỉ sau đó mới đánh dấu yếu tố mới là active. Chủ tài khoản nhận thông báo rằng một khóa bảo mật vừa được thêm.

Trong chương **Enrollment** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần thiết kế quá trình enrollment có ranh giới tin cậy rõ ràng, xác minh quyền sở hữu authenticator, chống phishing, replay, lạm dụng đăng nhập và chiếm quyền tài khoản.

Đăng ký yếu tố là một **thay đổi bảo mật quan trọng**. Nếu attacker chiếm được một phiên đăng nhập yếu rồi thêm authenticator của họ, họ có thể duy trì quyền truy cập sau khi chủ tài khoản đổi mật khẩu. Vì vậy, server phải xác minh người yêu cầu có quyền thay đổi tài khoản, xác minh yếu tố mới thực sự hoạt động và quản lý việc thu hồi/thay thế một cách an toàn.

## 2. MFA và các nhóm yếu tố

MFA (*Multi-Factor Authentication*) yêu cầu bằng chứng từ ít nhất hai nhóm yếu tố độc lập:

| Nhóm yếu tố | Bản chất | Ví dụ |
| --- | --- | --- |
| **Điều biết** (*something you know*) | Bí mật người dùng ghi nhớ. | Mật khẩu, passphrase, PIN được xác minh từ xa. |
| **Điều có** (*something you have*) | Quyền kiểm soát thiết bị hoặc vật mang credential. | Khóa bảo mật, authenticator TOTP, thiết bị giữ khóa riêng. |
| **Đặc điểm cá nhân** (*something you are*) | Đặc trưng sinh trắc được authenticator xác minh. | Vân tay hoặc nhận diện khuôn mặt trên thiết bị. |

Hai mật khẩu không phải MFA vì cùng thuộc nhóm điều biết. Mật khẩu cộng một câu hỏi bảo mật cũng không tạo ra hai yếu tố độc lập. PIN hoặc sinh trắc dùng cục bộ để mở khóa passkey thường là bước xác minh người dùng tại authenticator; server nhận bằng chứng mật mã chứ không nhận PIN hay dữ liệu sinh trắc thô.

### Phân biệt yếu tố với kênh liên hệ

Số điện thoại hoặc email là thuộc tính liên hệ. Khi hệ thống gửi OTP tới địa chỉ đó và người dùng nhập lại mã, hệ thống đang kiểm tra quyền truy cập kênh tại thời điểm đó. Điều này không tự chứng minh danh tính pháp lý, cũng không làm cho SMS/email trở thành phương thức chống phishing.

Chính sách phải phân loại rõ mức bảo đảm của từng phương thức:

| Phương thức | Đặc tính | Giới hạn chính |
| --- | --- | --- |
| SMS OTP | Mã gửi tới số điện thoại đã đăng ký. | SIM swap, chuyển tiếp, phishing và phụ thuộc nhà mạng. |
| Email OTP | Mã gửi tới hộp thư. | Phụ thuộc bảo mật email; có thể trùng với kênh khôi phục. |
| TOTP | Mã thời gian từ secret dùng chung. | Có thể bị phishing và chuyển tiếp trong thời gian mã còn hiệu lực. |
| Push approval | Yêu cầu phê duyệt trên ứng dụng. | Có thể bị MFA fatigue; cần xác nhận ý định và giới hạn yêu cầu. |
| FIDO2/passkey | Bằng chứng khóa công khai gắn với RP ID/origin. | Cần enrollment, bảo vệ thiết bị và recovery đúng cách. |
| Client certificate | Chứng minh kiểm soát private key tương ứng với chứng chỉ. | Cần PKI, bảo vệ khóa, kiểm tra chain và vòng đời chứng chỉ. |

Không phải mọi yếu tố đều có cùng khả năng chống phishing. Nếu hệ thống yêu cầu mức bảo đảm cao, ưu tiên passkey/WebAuthn hoặc khóa bảo mật FIDO2 được triển khai đúng; không để một nhánh dự phòng yếu làm mất mức bảo đảm chung.

## 3. Enrollment là một giao dịch có ranh giới tin cậy

Một luồng enrollment thường có người dùng, browser/app, dịch vụ quản lý tài khoản, authenticator, kho credential và hệ thống thông báo:

~~~mermaid
flowchart LR
    U["Người dùng"]
    C["Browser / ứng dụng<br/>client không đáng tin tuyệt đối"]
    S["Enrollment service<br/>xác minh quyền và giao dịch"]
    P[("Tài khoản + session<br/>chính sách bảo mật")]
    E[("Enrollment transaction<br/>challenge, purpose, expiry")]
    V[("Authenticator registry<br/>credential và trạng thái")]
    A["Authenticator<br/>TOTP / passkey / push"]
    N["Notification service"]
    U --> C
    C <--> S
    S <--> P
    S <--> E
    S <--> V
    C <--> A
    S --> N
    N --> U
~~~

Server quyết định tài khoản nào được thay đổi, giao dịch enrollment nào đang hoạt động và yếu tố mới có được phép kích hoạt hay không. Client chỉ vận chuyển dữ liệu; không được tự đặt trạng thái MFA, account ID, tenant hoặc quyền của yếu tố.

Mỗi giao dịch enrollment cần được ràng buộc với:

- **Principal và tenant:** lấy từ session đã xác minh, không tin ID do client tự gửi.
- **Mục đích:** thêm TOTP, đăng ký passkey, liên kết thiết bị push hoặc xác minh kênh OTP.
- **Session khởi tạo:** session phải active, có quyền quản lý credential và đạt yêu cầu step-up.
- **Challenge/transaction ID:** ngẫu nhiên, không đoán được, dùng một lần và có thời hạn.
- **Authenticator type:** phương thức cụ thể mà người dùng đã chọn; không dùng chung challenge giữa nhiều loại.
- **Trạng thái:** pending, verified, active, expired, cancelled hoặc revoked.
- **Attempt counter:** giới hạn thử và gửi lại để chống brute force/DoS.

## 4. Xác minh quyền trước khi thêm yếu tố

### 4.1. Tài khoản đã có yếu tố

Với tài khoản đã đăng nhập, server cần kiểm tra session còn hợp lệ, principal còn active và người dùng có quyền quản lý authenticator. Việc thêm, xóa hoặc thay thế yếu tố thường cần **reauthentication/step-up gần thời điểm thao tác**.

Yêu cầu step-up mạnh hơn khi:

- Session đã tồn tại lâu hoặc được khôi phục từ thiết bị.
- Có dấu hiệu đăng nhập bất thường, thiết bị mới hoặc rủi ro cao.
- Người dùng thêm yếu tố đầu tiên, xóa yếu tố cuối cùng hoặc thay kênh khôi phục.
- Tài khoản có quyền quản trị hoặc truy cập dữ liệu nhạy cảm.
- Người dùng yêu cầu tắt phương thức chống phishing hoặc chuyển sang phương thức yếu hơn.

Chỉ nhập lại mật khẩu không phải lúc nào cũng đủ. Nếu mật khẩu có thể đã bị phishing, cần xác minh bằng yếu tố hiện có mạnh hơn hoặc quy trình recovery có bảo đảm tương đương.

### 4.2. Tài khoản mới chưa có MFA

Tài khoản mới cần một quy trình bootstrap đáng tin cậy để gắn yếu tố đầu tiên. Ví dụ:

- Lời mời đăng ký có thời hạn, ràng buộc với địa chỉ/người nhận đã được xác minh.
- Quản trị viên cấp phát qua quy trình nội bộ có kiểm soát.
- Người dùng xác minh kênh liên hệ đã được tổ chức phê duyệt, sau đó đăng ký passkey/MFA theo policy.
- Thiết bị được provision trước bằng quy trình quản lý thiết bị và danh tính.

Xác minh email chỉ chứng minh quyền truy cập hộp thư tại thời điểm đó. Nó không tự chứng minh danh tính pháp lý hoặc quyền sở hữu tài khoản công ty. Nếu hộp thư đã bị chiếm, attacker có thể dùng bootstrap yếu để đăng ký yếu tố của họ.

### 4.3. Chống CSRF và IDOR

Với ứng dụng web dùng cookie, endpoint bắt đầu, xác minh và hủy enrollment phải bảo vệ CSRF. Có thể dùng CSRF token gắn với session/giao dịch, kiểm tra Origin/Referer theo policy và cookie SameSite phù hợp. Không dùng GET để thêm hoặc xóa yếu tố.

Không tin account ID hoặc tenant ID do browser gửi. Server lấy principal từ session đã xác minh và kiểm tra quyền trên từng request. Nếu client thay ID để gắn authenticator của attacker vào tài khoản nạn nhân, đó là lỗi IDOR/account substitution.

## 5. Vòng đời một enrollment

Một luồng enrollment an toàn chia thành các giai đoạn:

1. **Initiate:** người dùng yêu cầu thêm yếu tố; server xác minh session, quyền và step-up.
2. **Create pending transaction:** server tạo transaction ID/challenge gắn với account, tenant, session, purpose và expiry.
3. **Provision:** server và authenticator trao đổi dữ liệu theo giao thức của phương thức đã chọn.
4. **Prove possession/control:** người dùng gửi mã hoặc phản hồi mật mã chứng minh đã thiết lập được authenticator.
5. **Verify:** server kiểm tra challenge, nguồn gốc, thời hạn, replay và policy.
6. **Activate:** server ghi credential và chuyển trạng thái active bằng thao tác nguyên tử.
7. **Notify and recover:** thông báo chủ tài khoản, cung cấp recovery method phù hợp và cập nhật danh sách yếu tố.

~~~mermaid
stateDiagram-v2
    [*] --> Pending: Tạo giao dịch
    Pending --> Verified: Bằng chứng hợp lệ
    Pending --> Expired: Hết thời hạn
    Pending --> Cancelled: Người dùng hủy
    Verified --> Active: Commit credential
    Verified --> Expired: Không hoàn tất commit
    Active --> Revoked: Thu hồi
    Expired --> [*]
    Cancelled --> [*]
    Revoked --> [*]
~~~

**Pending không phải active.** Yếu tố đang chờ xác minh không được dùng để đăng nhập, thỏa MFA hoặc khôi phục tài khoản. Nếu người dùng đóng tab, hết hạn hoặc xác minh thất bại, server phải đóng giao dịch và dọn dữ liệu pending theo chính sách.

### Các bất biến quan trọng

- Giao dịch chỉ thuộc một principal, tenant, purpose và session khởi tạo.
- Challenge được tạo bằng CSPRNG và chỉ tiêu thụ một lần.
- Một credential không được gắn đồng thời trái phép với nhiều tài khoản.
- Kích hoạt chỉ xảy ra sau khi server xác minh bằng chứng.
- Retry và request đồng thời không được kích hoạt hai lần hoặc bỏ qua attempt limit.
- Lỗi hạ tầng không được làm enrollment chuyển active theo kiểu fail-open.

## 6. Đăng ký TOTP authenticator

TOTP tạo mã ngắn hạn từ secret dùng chung và thời gian. Server sinh secret, người dùng thêm secret vào ứng dụng authenticator rồi nhập mã để chứng minh đã thiết lập đúng.

### Quy trình

1. Server xác minh session và step-up.
2. Sinh secret ngẫu nhiên riêng cho giao dịch, lưu trong bản ghi pending.
3. Tạo provisioning URI/QR và hiển thị qua HTTPS trong đúng session.
4. Người dùng quét QR hoặc nhập secret vào authenticator.
5. Authenticator hiển thị mã TOTP; người dùng nhập mã vào ứng dụng.
6. Server xác minh mã bằng secret pending, cửa sổ thời gian giới hạn và attempt limit.
7. Nếu hợp lệ, server lưu secret theo cơ chế bảo vệ phù hợp và kích hoạt binding.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant S as Enrollment server
    participant A as Authenticator app
    U->>B: Chọn thêm TOTP
    B->>S: Initiate trong session đã step-up
    S->>S: Sinh secret và pending transaction
    S-->>B: Provisioning QR qua HTTPS
    B-->>U: Hiển thị QR
    U->>A: Quét QR
    A-->>U: Sinh mã hiện tại
    U->>B: Nhập mã xác minh
    B->>S: Mã + transaction ID
    S->>S: Kiểm tra mã, expiry, attempts và replay
    S->>S: Kích hoạt credential nguyên tử
    S-->>B: Enrollment thành công
~~~

### Yêu cầu bảo mật

- Secret phải được sinh bằng CSPRNG, đủ entropy và duy nhất cho từng binding.
- QR/secret chỉ hiển thị cho người đã xác minh quyền thay đổi tài khoản.
- Không ghi provisioning URI, QR, secret hoặc OTP vào log, analytics, crash report hay ticket hỗ trợ.
- Chỉ kích hoạt sau khi mã hợp lệ được xác minh; việc hiển thị QR không chứng minh người dùng đã thêm secret.
- Cửa sổ thời gian phải đủ xử lý lệch đồng hồ nhưng không quá rộng.
- Giới hạn số lần nhập và gửi lại mã; cân nhắc không chấp nhận cùng time-step code đã tiêu thụ.
- Secret cần được bảo vệ khi lưu, ví dụ mã hóa bằng khóa quản lý an toàn, vì server phải có khả năng xác minh mã sau này.
- Khi thu hồi binding, vô hiệu hóa ở server và áp dụng session/token revocation policy liên quan.

TOTP có thể bị phishing: attacker giả trang đăng nhập, lấy mật khẩu và OTP rồi chuyển tiếp tới dịch vụ thật trong thời gian mã còn hiệu lực. Vì vậy TOTP bổ sung lớp bảo vệ nhưng không chống phishing mạnh như WebAuthn.

## 7. Đăng ký passkey và khóa bảo mật FIDO2

Passkey/WebAuthn dùng cặp khóa mật mã. Authenticator giữ private key; server lưu credential ID và public key. Khi đăng ký, server tạo challenge và kiểm tra phản hồi từ authenticator.

### Registration ceremony

1. Server xác minh người yêu cầu có quyền thêm passkey.
2. Tạo challenge ngẫu nhiên, gắn với principal, session và giao dịch pending.
3. Gửi PublicKeyCredentialCreationOptions gồm RP ID, user handle, challenge và chính sách user verification/attestation.
4. Browser gọi WebAuthn API; authenticator tạo credential và trả registration response.
5. Server dùng thư viện WebAuthn đáng tin cậy để xác minh challenge, origin, RP ID hash, cờ user presence/user verification và attestation theo policy.
6. Kiểm tra credential ID chưa bị gắn trái phép; lưu public key và metadata.
7. Commit credential thành active và thông báo chủ tài khoản.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as RP / server
    participant B as Browser
    participant K as Authenticator
    U->>R: Thêm passkey sau step-up
    R->>R: Tạo challenge gắn với account
    R-->>B: PublicKeyCredentialCreationOptions
    B->>K: navigator.credentials.create()
    K->>K: Tạo cặp khóa, xác minh người dùng cục bộ
    K-->>B: Credential ID + public key + attestation data
    B->>R: Registration response
    R->>R: Verify challenge, origin, RP ID, flags, attestation
    R->>R: Lưu public key và activate
    R-->>U: Passkey đã được thêm
~~~

### Kiểm tra cần thiết

- Challenge phải khớp giao dịch pending và chưa được dùng.
- Origin phải thuộc allowlist; RP ID hash phải khớp RP ID cấu hình.
- User presence và user verification phải đáp ứng policy.
- Attestation được xử lý theo policy: có hệ thống chấp nhận none; hệ thống yêu cầu thiết bị cụ thể cần xác minh attestation chain/metadata tương ứng.
- Server chỉ lưu public key và credential metadata, không lưu private key của passkey.
- Không giả định mọi passkey đồng bộ chỉ tồn tại trên một thiết bị hoặc signature counter luôn tăng.

Passkey có thể chống phishing tốt nhờ ràng buộc RP ID/origin, nhưng enrollment vẫn có thể bị chiếm nếu attacker kiểm soát session đủ quyền. Step-up bằng yếu tố hiện có, transaction binding, thông báo và recovery an toàn vẫn cần thiết.

## 8. Đăng ký push authenticator

Push MFA dùng ứng dụng đã liên kết với tài khoản để nhận yêu cầu xác minh. Đăng ký thiết bị push cần chứng minh thiết bị mới thực sự được kiểm soát bởi người có quyền thay đổi tài khoản.

Một quy trình thường có:

1. Người dùng cài ứng dụng authenticator chính thức và bắt đầu liên kết thiết bị từ session đã step-up.
2. Ứng dụng tạo khóa thiết bị hoặc registration credential theo giao thức.
3. Server tạo challenge/transaction và gửi thông tin liên kết có thời hạn.
4. Ứng dụng chứng minh quyền kiểm soát khóa hoặc registration token.
5. Server xác minh thiết bị, gắn public key/device binding với principal và kích hoạt.
6. Người dùng đặt nhãn thiết bị; server thông báo việc thêm authenticator.

Không coi push đã gửi hoặc đã nhận là phê duyệt. Để giảm MFA fatigue:

- Giới hạn số push request và áp dụng cooldown.
- Dùng number matching hoặc xác nhận ý định khi phù hợp.
- Hiển thị ngữ cảnh đủ để người dùng nhận ra yêu cầu bất thường.
- Có nút từ chối/báo cáo yêu cầu không do mình khởi tạo.
- Không cho phép push enrollment chỉ dựa vào một phiên cũ hoặc một mã xác minh yếu.

## 9. Đăng ký SMS và email OTP

Khi hệ thống cho phép SMS/email làm phương thức xác minh bổ sung, cần xác minh quyền nhận mã trên kênh mới trước khi kích hoạt.

### Luồng đăng ký

1. Người dùng nhập số điện thoại hoặc email mới.
2. Server chuẩn hóa và kiểm tra định dạng, giới hạn gửi mã.
3. Sinh OTP ngẫu nhiên, gắn với account, purpose và transaction; lưu verifier cùng thời hạn.
4. Gửi OTP tới kênh mới.
5. Người dùng nhập mã; server kiểm tra đúng, chưa hết hạn, chưa dùng và còn attempt.
6. Kích hoạt binding nếu policy cho phép và thông báo chủ tài khoản.

### Giới hạn

- SMS có thể bị SIM swap, chuyển tiếp hoặc phishing.
- Email phụ thuộc bảo mật hộp thư; nếu hộp thư cũng là kênh recovery duy nhất thì rủi ro tập trung.
- OTP ngắn cần rate limit theo account, transaction, nguồn và thiết bị.
- Không tiết lộ liệu email/số điện thoại đã tồn tại ở tài khoản khác.
- Không cho thay đổi kênh liên hệ và dùng chính kênh vừa đổi để tự chứng minh quyền sở hữu tài khoản cũ.

Số điện thoại/email là kênh nhận mã, không phải bằng chứng danh tính pháp lý. Hãy đánh giá mức bảo đảm của chúng trong toàn bộ policy MFA và recovery.

## 10. Recovery codes và yếu tố dự phòng

Người dùng có thể mất thiết bị hoặc không còn truy cập authenticator. Vì vậy, quy trình enrollment nên chuẩn bị phương thức dự phòng ngay khi bật MFA.

Recovery codes có thể được thiết kế như sau:

- Sinh một tập mã ngẫu nhiên đủ entropy; mỗi mã dùng một lần.
- Hiển thị sau khi enrollment thành công và yêu cầu người dùng lưu ở nơi an toàn.
- Server lưu verifier/hash phù hợp thay vì bản rõ nếu có thể.
- Khi dùng, tiêu thụ mã nguyên tử để không thể replay.
- Khi tạo bộ mới, vô hiệu hóa toàn bộ mã cũ.
- Thông báo khi recovery code được sử dụng hoặc bộ mã được tạo lại.

Recovery code là credential dự phòng, không nên yếu hơn đáng kể so với mức bảo vệ tài khoản. Không lưu mã trong email cùng tài khoản, ảnh chụp không bảo vệ hoặc file dùng chung. Không dùng câu hỏi bảo mật dễ tra cứu để vô hiệu hóa MFA.

Phương thức dự phòng khác có thể là passkey thứ hai, khóa bảo mật dự phòng hoặc recovery flow có xác minh danh tính và phê duyệt. Mỗi phương thức phải có mức bảo đảm, giới hạn và audit rõ.

## 11. Thay thế, thêm và xóa yếu tố

Enrollment không kết thúc khi yếu tố đầu tiên được thêm. Người dùng cần quản lý vòng đời authenticator:

### Thêm yếu tố dự phòng

- Yêu cầu xác thực lại bằng yếu tố đang hoạt động.
- Tạo giao dịch riêng cho authenticator mới.
- Xác minh quyền kiểm soát trước khi active.
- Thông báo chủ tài khoản và cập nhật inventory.

### Thay thiết bị

Nếu người dùng còn yếu tố hợp lệ, xác thực lại rồi đăng ký thiết bị mới. Sau khi yếu tố mới đã hoạt động, người dùng có thể thu hồi thiết bị cũ. Không xóa yếu tố cũ trước khi yếu tố mới được xác minh, trừ khi có căn cứ sự cố buộc phải thu hồi ngay.

### Xóa yếu tố

- Yêu cầu step-up đủ mạnh.
- Kiểm tra tài khoản còn phương thức đăng nhập/recovery phù hợp.
- Không cho xóa yếu tố cuối cùng nếu điều đó làm tài khoản mất khả năng xác thực theo policy.
- Với tài khoản nhạy cảm, có thể cần phê duyệt bổ sung hoặc thời gian chờ cho thay đổi rủi ro cao.
- Gửi thông báo và ghi audit event.

### Khi nghi bị chiếm

Thu hồi authenticator lạ, session/token liên quan, kiểm tra thay đổi email/điện thoại khôi phục và các credential mới được tạo. Đặt lại credential gốc nếu có dấu hiệu lộ; sau đó enrollment lại bằng recovery flow đáng tin cậy.

## 12. Tấn công nhắm vào MFA enrollment

| Rủi ro | Kịch bản | Biện pháp giảm thiểu |
| --- | --- | --- |
| **Enrollment hijacking** | Attacker chiếm session yếu rồi thêm authenticator của họ. | Step-up bằng yếu tố hiện có, đánh giá rủi ro, thông báo và thu hồi session. |
| **CSRF** | Trang ngoài kích hoạt thao tác thêm/xóa yếu tố qua cookie nạn nhân. | CSRF token, Origin/Referer, SameSite và kiểm tra quyền server. |
| **IDOR/account substitution** | Client thay account/tenant ID để gắn credential sai chủ. | Lấy principal từ session; kiểm tra quyền từng request. |
| **QR/secret leakage** | TOTP secret bị lộ qua log, screenshot hoặc hỗ trợ. | Không log/cache, chỉ hiển thị trong phiên đúng và xác minh trước kích hoạt. |
| **OTP brute force** | Attacker thử nhiều mã xác minh. | TTL ngắn, attempt limit, rate limit đa chiều và giám sát. |
| **Replay** | Gửi lại OTP hoặc WebAuthn response đã dùng. | Challenge/mã dùng một lần, consume nguyên tử và TTL. |
| **MFA fatigue** | Push liên tục để nạn nhân phê duyệt nhầm. | Cooldown, number matching, ngữ cảnh và báo cáo yêu cầu lạ. |
| **Recovery bypass** | Kênh email/câu hỏi bảo mật yếu dùng để đăng ký yếu tố mới. | Recovery assurance phù hợp, mã dự phòng mạnh và audit. |
| **Delete-last-factor** | Attacker xóa yếu tố cuối cùng sau khi chiếm session. | Step-up, yêu cầu phương thức thay thế, cảnh báo và trì hoãn theo rủi ro. |
| **Race condition** | Hai request đồng thời kích hoạt hoặc tiêu thụ cùng challenge. | Transaction nguyên tử, unique constraint và state transition kiểm soát. |
| **Downgrade** | Attacker ép người dùng chuyển sang SMS/email yếu hơn. | Assurance floor, phê duyệt thay đổi và không fallback âm thầm. |
| **Support impersonation** | Attacker giả làm nhân viên để yêu cầu helpdesk thêm yếu tố. | Quy trình xác minh độc lập, dual control và audit hỗ trợ. |

**Fallback là một phần của MFA policy.** Nếu hệ thống quảng bá passkey chống phishing nhưng khi passkey lỗi lại cho phép đăng nhập chỉ bằng mật khẩu, attacker sẽ nhắm vào nhánh yếu nhất. Mỗi phương thức dự phòng cần được đánh giá theo cùng threat model.

## 13. Mã giả: đăng ký TOTP với trạng thái pending

Đoạn mã sau mô tả thứ tự xử lý và các bất biến. Đây là mã giả, không phải triển khai production:

~~~text
beginTotpEnrollment(session):
    account = requireValidSession(session)
    require account.active
    require canManageAuthenticators(account, session)
    require recentStepUpWithExistingFactor(account, session)
    require abusePolicyAllows(account)

    tx = createPendingTransaction(
        accountId = account.id,
        tenantId = account.tenantId,
        sessionId = session.id,
        purpose = "enroll_totp",
        secret = secureRandomTotpSecret(),
        expiresAt = shortExpiry()
    )

    return showProvisioningQrOnce(tx.secret)

confirmTotpEnrollment(session, transactionId, code):
    account = requireValidSession(session)
    tx = loadPendingTransaction(transactionId)
    require tx.accountId == account.id
    require tx.tenantId == account.tenantId
    require tx.sessionId == session.id
    require tx.purpose == "enroll_totp"
    require tx.notExpired and not tx.consumed
    require tx.attemptsRemaining

    if not verifyTotp(tx.secret, code, allowedTimeWindow):
        incrementAttemptsAtomically(tx)
        return genericFailure()

    atomically:
        consumeTransaction(tx)
        storeProtectedTotpBinding(account.id, tx.secret, status="active")

    notifyAccountOwner("MFA method added")
    return enrollmentSuccess()
~~~

Triển khai thực tế cần dùng thư viện TOTP đáng tin cậy, mã hóa secret khi lưu, giới hạn thử, chống replay và race condition. QR chỉ hiển thị đúng một lần trong giao dịch phù hợp; không ghi secret vào log. Nếu database commit thất bại, không báo thành công hoặc để bản ghi active một phần.

## 14. Kiểm thử enrollment

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Session hợp lệ, step-up đạt | Có thể bắt đầu transaction pending. |
| Session hết hạn hoặc account bị khóa | Không bắt đầu/hoàn tất enrollment. |
| Client đổi account ID/tenant ID | Server từ chối hoặc bỏ qua giá trị client; không gắn sai principal. |
| TOTP sai hoặc hết hạn | Không active; tăng attempt counter. |
| TOTP đúng nhưng transaction đã dùng | Từ chối replay. |
| QR đã hiển thị nhưng chưa xác minh | Yếu tố vẫn pending, không được dùng cho đăng nhập. |
| WebAuthn origin/RP ID/challenge sai | Từ chối registration response. |
| Push mới chỉ được gửi | Chưa active cho tới khi thiết bị chứng minh binding và người dùng hoàn tất bước cần thiết. |
| OTP gửi tới số/email mới nhưng chưa nhập đúng | Kênh chưa được kích hoạt. |
| Hai request confirm cùng transaction đồng thời | Chỉ một request commit được. |
| Recovery code đã sử dụng | Từ chối lần dùng tiếp theo. |
| Người dùng xóa yếu tố cuối cùng | Chặn hoặc yêu cầu phương thức dự phòng đủ tin cậy. |
| Lỗi database/IdP khi xác minh | Không kích hoạt yếu tố theo kiểu fail-open. |
| Thêm yếu tố mới thành công | Ghi audit và gửi thông báo không chứa secret. |

### Kiểm thử trải nghiệm và vận hành

- Người dùng hiểu cách lưu recovery codes trước khi kết thúc thiết lập.
- Có thể hủy transaction pending và bắt đầu lại khi challenge/QR hết hạn.
- Hỗ trợ viên không xem được TOTP secret, OTP hoặc recovery code.
- Giao diện hiển thị rõ phương thức, nhãn thiết bị và thời điểm đăng ký.
- Thông báo không chứa QR, secret, OTP hoặc token.
- Log phân biệt thành công, thất bại, hết hạn, bị giới hạn và lỗi hệ thống mà không ghi bí mật thô.

## 15. Checklist thiết kế MFA enrollment

- [ ] Xác định yếu tố, mức assurance và khả năng chống phishing cần đạt.
- [ ] Xác minh principal và quyền thay đổi credential trước khi enrollment.
- [ ] Yêu cầu reauthentication/step-up theo độ nhạy cảm và rủi ro.
- [ ] Ràng buộc transaction với account, tenant, session, purpose và expiry.
- [ ] Tạo secret/challenge bằng CSPRNG và chống replay.
- [ ] Chỉ chuyển active sau khi server kiểm chứng bằng chứng từ authenticator.
- [ ] TOTP secret, QR, OTP và recovery code không xuất hiện trong log/analytics.
- [ ] WebAuthn kiểm tra challenge, origin, RP ID, user presence/verification và attestation theo policy.
- [ ] Push/SMS/email có rate limit, xác nhận ý định và kiểm soát kênh.
- [ ] Có recovery codes hoặc phương thức dự phòng đủ mạnh, dùng một lần và được bảo vệ.
- [ ] Fallback không làm giảm mức assurance tối thiểu một cách âm thầm.
- [ ] Thêm/xóa/thay yếu tố có audit, thông báo và khả năng thu hồi.
- [ ] Kiểm thử CSRF, IDOR, replay, race condition, timeout và lỗi phụ thuộc.
- [ ] Có chính sách session/token sau khi thêm hoặc thu hồi yếu tố.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao server không nên đánh dấu TOTP active ngay khi hiển thị QR?

**Gợi ý:** QR chỉ chứa secret provisioning; chưa chứng minh người dùng đã thêm đúng secret vào authenticator. Cần xác minh mã hợp lệ trước khi kích hoạt.

**Câu 2.** Vì sao thêm passkey cần step-up dù người dùng đã đăng nhập?

**Gợi ý:** Session hiện tại có thể đã cũ hoặc bị chiếm. Thêm passkey tạo đường đăng nhập mới nên cần chứng minh người yêu cầu có quyền thay đổi tài khoản.

**Câu 3.** TOTP khác WebAuthn thế nào về chống phishing?

**Gợi ý:** TOTP có thể bị chuyển tiếp trong thời gian mã còn hiệu lực; WebAuthn ràng buộc bằng chứng với origin/RP ID và chống phishing tốt hơn khi triển khai đúng.

**Câu 4.** Nếu người dùng mất thiết bị MFA, có nên tắt MFA chỉ bằng email username không?

**Gợi ý:** Không. Cần recovery flow đủ tin cậy, chống lạm dụng, audit và thông báo.

**Câu 5.** Vì sao pending enrollment phải gắn với account lấy từ server?

**Gợi ý:** Ngăn client thay account/tenant để gắn yếu tố của attacker vào tài khoản nạn nhân.

**Câu 6.** Vì sao phải kiểm thử hai request xác nhận đồng thời?

**Gợi ý:** Nếu consume challenge và commit credential không nguyên tử, hai request có thể cùng vượt qua hoặc tạo binding trùng.

**Câu 7.** Vì sao SMS/email OTP không nên được mô tả là phương thức chống phishing?

**Gợi ý:** Mã có thể bị người dùng nhập vào trang giả và chuyển tiếp; kênh còn phụ thuộc bảo mật nhà mạng/hộp thư.

## 17. Ghi nhớ

**MFA enrollment là quá trình liên kết credential mới với tài khoản và phải được bảo vệ như một thao tác thay đổi bảo mật.** Server cần xác minh chủ tài khoản, yêu cầu step-up phù hợp, tạo transaction pending gắn với đúng principal/tenant/session, kiểm chứng quyền kiểm soát authenticator rồi mới kích hoạt nguyên tử. TOTP, passkey, push và SMS/email có mức assurance và khả năng chống phishing khác nhau; recovery codes, thay thiết bị, xóa yếu tố, fallback và thông báo đều thuộc vòng đời enrollment. Thiết kế tốt ngăn attacker tự thêm yếu tố của họ, đồng thời giúp người dùng hợp lệ duy trì và khôi phục quyền truy cập an toàn.
