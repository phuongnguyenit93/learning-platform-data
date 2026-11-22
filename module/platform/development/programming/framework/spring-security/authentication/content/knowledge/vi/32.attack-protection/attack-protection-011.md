# Phishing, xác thực bổ sung và giới hạn của các cơ chế dựa trên bí mật có thể nhập lại

## 1. Mục tiêu học tập

Phishing là hành vi đánh lừa người dùng tương tác với một trang, ứng dụng hoặc bên xác thực giả mạo để đánh cắp thông tin, khiến họ chấp thuận đăng nhập trái phép hoặc chuyển giao phiên đăng nhập. Trong hệ thống có mật khẩu và OTP, một trang giả có thể **thu thập giá trị người dùng nhập** rồi lập tức chuyển tiếp tới hệ thống thật.

Ba vấn đề cần tách rời:

1. **Phishing:** kẻ tấn công mạo danh website/ứng dụng hoặc quy trình hỗ trợ để lấy credential hay chiếm session.
2. **Xác thực bổ sung (step-up/reauthentication):** yêu cầu bằng chứng đăng nhập mới hơn hoặc mạnh hơn trước một hành động nhạy cảm. Step-up có thể là nhập lại mật khẩu, thêm OTP hoặc dùng passkey, nhưng **không phải hình thức nào cũng chống phishing**.
3. **Giới hạn của bí mật có thể nhập lại:** password, PIN được nhập vào website, SMS OTP, TOTP hay recovery code là các giá trị có thể được sao chép/chuyển tiếp. Tính ngắn hạn hoặc chỉ dùng một lần giảm cửa sổ lạm dụng nhưng **không tự chống relay theo thời gian thực**.

Sau bài này bạn cần:
- Phân biệt phishing truyền thống, phishing qua reverse proxy thời gian thực và đánh cắp session.
- Giải thích tại sao password+TOTP thường là MFA nhưng **không phải phishing-resistant MFA**.
- Hiểu nguyên lý WebAuthn/FIDO2 passkey dựa trên `origin`/`RP ID` và ranh giới bảo mật của nó.
- Xác định khi nào cần reauthentication/step-up và bằng chứng cần kiểm tra ở server.
- Thiết kế kiểm soát phiên, chống downgrade, recovery, enrollment và giám sát.
- Hiểu ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+ thể hiện **reauthentication bằng password**, đồng thời hiểu rõ vì sao ví dụ đó *không* phải MFA hoặc phishing-resistant.

**Tư tưởng cốt lõi:** nhiều yếu tố xác thực hơn thường giảm khả năng chiếm tài khoản, nhưng **khả năng chống phishing là thuộc tính của giao thức và cách ràng buộc bên xác thực**, không phải chỉ số lượng màn hình yêu cầu nhập mã.

## 2. Phishing hoạt động thế nào?

### 2.1. Trang đăng nhập giả

Một email giả dạng bộ phận IT đưa người dùng tới `https://login-example.attacker.example` có giao diện tương tự `https://login.example.org`. Nếu người dùng nhập password vào trang giả, attacker có thể dùng password trên website thật.

~~~text
Người dùng                      Trang giả                      Website thật
    |                               |                                |
    | nhấp link mạo danh             |                                |
    |------------------------------>|                                |
    | nhập username/password        |                                |
    |------------------------------>| lấy credential                 |
    |                               |---- đăng nhập bằng password -->|
    |                               |                                |
    |                               |       (có thể bị chặn bởi MFA)  |
~~~

Biện pháp như password manager chỉ autofill trên domain chính xác, huấn luyện nhận diện website giả, bảo vệ email và phát hiện domain lừa đảo đều hữu ích, nhưng không nên buộc người dùng là **lớp bảo vệ duy nhất**.

### 2.2. Phishing thời gian thực qua reverse proxy

Trường hợp nguy hiểm hơn: website giả chuyển tiếp request/response tới website thật ngay trong phiên. Người dùng nhập password, rồi nhập OTP vào trang giả; attacker chuyển tiếp từng giá trị lập tức trước khi hết hạn.

~~~text
Browser nạn nhân          Website giả / relay              RP hoặc IdP thật
      |                           |                               |
      | username + password       |                               |
      |-------------------------->|---- chuyển tiếp ------------->|
      |<--------------------------|<--- yêu cầu OTP ---------------|
      | OTP mới (6 số)            |                               |
      |-------------------------->|---- chuyển tiếp nhanh ------->|
      |                           |<--- session/token ------------|
      |                           |                               |
      |                           └── có thể chiếm phiên nếu lấy   |
      |                               được session artifact phù hợp|
~~~

Một OTP có TTL 30 giây và single-use **vẫn có thể bị relay ngay lần đầu**. “Dùng một lần” không có nghĩa “chỉ dùng ở trình duyệt của nạn nhân”. Sau khi đăng nhập, attacker có thể cố lấy session cookie hoặc token, tùy kiến trúc và kiểm soát của hệ thống.

Đây là phân tích mô hình đe dọa để **phòng thủ**, không phải hướng dẫn triển khai hạ tầng phishing. Hệ thống thực phải bảo vệ mật khẩu, OTP, session và cả luồng recovery/enrollment.

### 2.3. Phishing có thể chuyển hướng sang mục tiêu khác

Phishing không chỉ nhằm lấy password:
- Lừa người dùng nhập OTP hoặc recovery code.
- Gửi hàng loạt push approval để người dùng bấm đồng ý theo thói quen.
- Lừa người dùng đăng ký thiết bị MFA/passkey của attacker vào account.
- Dụ người dùng cấp quyền OAuth consent cho một client độc hại.
- Gửi link “khôi phục tài khoản” dẫn tới quy trình reset không đáng tin.
- Chiếm cookie/session sau khi người dùng đăng nhập qua một bước xác thực hợp lệ.

Vì vậy chính sách chống phishing phải áp dụng **sau login** và tại các thao tác thiết lập phương thức xác thực, không chỉ ở `POST /login`.

## 3. Bí mật có thể nhập lại là gì?

“Bí mật có thể nhập lại” ở đây là **chuỗi hoặc câu trả lời có thể được người dùng gõ/copy vào một giao diện**, ví dụ:
- password hoặc passphrase;
- mã SMS/voice OTP;
- mã từ ứng dụng TOTP;
- recovery/backup code;
- mã xác nhận email;
- câu trả lời câu hỏi bảo mật;
- một số mã PIN được ứng dụng website yêu cầu nhập trực tiếp.

Những giá trị này có thể bị **quan sát, sao chép và trình tới verifier khác** nếu website giả thu thập chúng. Sự khác biệt là PIN mở khóa authenticator **cục bộ** cho WebAuthn thường không được gửi cho RP; không đánh đồng PIN đó với PIN nhập vào form website.

### Bảng so sánh cơ chế

| Cơ chế | Vai trò phổ biến | Có thể bị nhập vào website giả? | Phishing-resistant theo thiết kế? |
|---|---|---|---|
| Password/passphrase | Something you know | Có | **Không** |
| SMS OTP | Kênh ngoài băng/possession theo policy | Có | **Không** |
| Email OTP | Mã trong inbox | Có | **Không**; độ độc lập yếu nếu email cùng account/recovery |
| TOTP app | OTP dựa trên secret và thời gian | Có | **Không** |
| HOTP / hardware OTP display | OTP dựa trên counter hoặc thiết bị | Có | **Không** nếu user nhập mã |
| Recovery code | Cứu hộ tài khoản | Có | **Không** |
| Password + TOTP | Hai yếu tố độc lập nếu cấu hình đúng | Có | **MFA, nhưng không chống phishing thời gian thực** |
| Push “Approve” đơn giản | Xác nhận qua ứng dụng | Không phải chuỗi nhập lại, nhưng dễ bị lừa duyệt | **Không mặc nhiên** |
| Push number matching | Ghép prompt và số thử thách giúp giảm fatigue | Người dùng vẫn có thể bị social engineering/relay | **Không mặc nhiên đạt tiêu chí phishing resistance** |
| FIDO2/WebAuthn passkey | Khóa công khai ràng buộc với RP ID | Private key không được gửi để nhập lại | **Có thể phishing-resistant** khi triển khai xác minh origin/RP ID đúng |
| Client-authenticated TLS có channel binding | Chứng minh khóa gắn với kênh TLS | Không đơn giản copy một chuỗi | **Có thể phishing-resistant** khi thiết kế đúng |

**Không thể xác nhận chỉ từ tên sản phẩm “MFA” rằng nó chống phishing.** Phải biết authenticator output có bị nhập tay/copy được không và giao thức có ràng buộc với verifier/challenge/kênh tương ứng hay không.

## 4. MFA, reauthentication, step-up và phishing resistance

### 4.1. MFA thực sự cần các yếu tố độc lập

Các nhóm yếu tố truyền thống:
1. **Something you know:** mật khẩu/PIN.
2. **Something you have:** authenticator/cert/key đã đăng ký.
3. **Something you are:** sinh trắc học dùng để mở khóa/kiểm tra tại authenticator.

Nhập lại password hai lần là **cùng một yếu tố**, không thành MFA. Password cộng một PIN khác cũng có thể vẫn chỉ là “something you know” nếu không chứng minh possession/biometric độc lập. IP, vị trí, cookie nhớ thiết bị, CAPTCHA hoặc câu hỏi “bạn có chắc không?” là tín hiệu/rào cản bổ sung, **không tự trở thành yếu tố MFA**.

TOTP app thông thường chứng minh possession của thiết bị chứa secret TOTP; khi kết hợp password có thể là MFA. Nhưng mã TOTP hiển thị và được người dùng nhập vào website, nên mã có thể bị chuyển tiếp tới website thật.

### 4.2. Reauthentication và step-up không đồng nghĩa

- **Reauthentication:** yêu cầu chứng minh lại danh tính, thường vì session cũ hoặc hành động nhạy cảm. Ví dụ nhập lại password.
- **Step-up authentication:** nâng độ đảm bảo khi rủi ro tăng, ví dụ từ password sang WebAuthn, hoặc từ session bình thường sang thao tác vừa được xác nhận bằng yếu tố mạnh.
- **Phishing-resistant authentication:** giao thức chống việc trình authenticator output cho một verifier giả mạo mà không phụ thuộc vào sự cảnh giác của người dùng.

Một lần nhập lại password có thể làm `auth_time` mới hơn (freshness) nhưng **không nâng thành MFA**, càng không tự chống phishing. Một lần thêm TOTP có thể nâng từ password-only sang MFA nhưng vẫn không chống relay thời gian thực.

### 4.3. Freshness, assurance và intent là ba chiều khác nhau

| Khía cạnh | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Freshness** | Lần xác thực mạnh gần nhất cách đây bao lâu? | `auth_time` trong 5 phút |
| **Assurance / factors** | Đã dùng cơ chế nào, có đáp ứng policy cần thiết không? | Passkey có UV, hoặc password+TOTP |
| **Intent / transaction binding** | Người dùng đã xác nhận đúng hành động cụ thể chưa? | Xác nhận thay email từ A sang B |

Một token/signal nói user đã đăng nhập gần đây **không tự chứng minh** họ đã xác nhận nội dung chuyển tiền. Đối với giao dịch rủi ro cao, cần ràng buộc approval với `transactionId`, số tiền/đích hoặc nội dung thay đổi theo policy, và bảo vệ khỏi việc sửa payload sau approval.

## 5. Tại sao OTP còn hạn vẫn bị phishing?

Ví dụ: người dùng nhìn thấy mã TOTP `123456` (chuỗi chỉ để minh họa, không phải OTP hợp lệ) rồi nhập vào website giả. Website giả chuyển mã tới verifier thật trước khi mã hết hạn. Nếu hệ thống thật chỉ xác minh mã, **nó không biết mã vừa được nhập ở website nào**.

Các kiểm soát có ích nhưng **không giải quyết trọn vẹn relay**:
- TTL ngắn và one-time consumption ngăn reuse sau khi tiêu thụ, nhưng không ngăn attacker dùng token trước.
- Giới hạn số lần thử/rate limit chống brute force mã ngắn, không ngăn mã thật đã bị lừa lấy.
- OTP gắn user/session giảm token substitution, nhưng nếu kẻ tấn công đang relay cả session luồng đó thì cần thêm bảo vệ ràng buộc verifier.
- TLS tới website thật bảo vệ đường truyền giữa hai bên hợp lệ, nhưng nạn nhân có thể đang kết nối HTTPS **đến chính website giả**.
- CAPTCHA có thể giảm automation, không bảo đảm người dùng không nhập mã vào website giả.

Theo **NIST SP 800-63B-4**, authenticator output đòi người dùng nhập tay (đặc biệt OTP/out-of-band) **không được coi là phishing-resistant**, bởi output không được ràng buộc mật mã với đúng verifier/session đang xác thực.

### Mã OTP một lần có ích ở đâu?

OTP vẫn có giá trị thực tế, đặc biệt nếu một password đã bị lộ ngoài website. Nó tăng rào cản so với password-only, giúp giới hạn replay *sau* khi mã đã được sử dụng, và hỗ trợ legacy workflows. Vấn đề không phải “OTP vô dụng”, mà là **không được cam kết OTP chống phishing thời gian thực**.

## 6. Tại sao WebAuthn/FIDO2 passkey khác mã nhập tay?

WebAuthn dùng **khóa công khai gắn với Relying Party ID (RP ID)**. Authenticator giữ private key, browser phối hợp với authenticator tạo một assertion có chữ ký cho challenge mới. Server dùng **public key đã đăng ký** để kiểm tra.

~~~text
Đăng ký credential:
  Browser ở https://login.example.org
     → navigator.credentials.create()
     → authenticator tạo credential cho RP ID example.org
     → server lưu credential ID + public key

Đăng nhập:
  Browser lấy challenge mới từ RP
     → navigator.credentials.get()
     → authenticator chọn private key gắn đúng RP ID
     → tạo assertion chứa authenticatorData + signature
     → RP verify challenge/origin/rpIdHash/signature/flags
~~~

### 6.1. Verifier name binding

NIST gọi cách này là **verifier name binding**: authenticator output được ràng buộc mật mã với định danh verifier, thông thường là domain đã được xác thực. Một website lừa đảo trên domain khác không thể đơn giản yêu cầu authenticator tạo assertion hợp lệ cho RP ID của website thật, nếu browser/authenticator và server thực thi đúng quy tắc WebAuthn.

### 6.2. Phải kiểm tra đúng ở server

WebAuthn không an toàn chỉ bằng việc gọi `navigator.credentials.get()`. Server còn phải kiểm tra:
1. `clientDataJSON.type = webauthn.get`.
2. `challenge` đúng request, mới, chưa hết hạn và chưa dùng.
3. `clientDataJSON.origin` thuộc allowlist scheme/host/port chính xác.
4. `authenticatorData.rpIdHash` đúng SHA-256 của expected RP ID.
5. UP/UV flags phù hợp chính sách, nhất là khi cần user verification.
6. Credential ID tồn tại, thuộc đúng account và chưa bị thu hồi.
7. Signature hợp lệ bằng **stored public key**, không lấy key từ request tùy ý.
8. Account/session/authorization vẫn đáp ứng policy.

**Lưu ý:** một passkey với user verification phù hợp có thể đáp ứng nhiều yếu tố trong một ceremony; nhưng không được tuyên bố mọi loại WebAuthn assertion tự động là “MFA” mà không xem flags, chính sách và assurance.

### 6.3. Giới hạn vẫn tồn tại

Phishing resistance ở **authentication ceremony** không đồng nghĩa toàn bộ ứng dụng miễn nhiễm tấn công:
- XSS trên origin thật có thể hành động trong session hoặc đánh cắp dữ liệu có quyền đọc.
- Cookie/session token có thể bị lấy cắp và replay nếu thiếu bảo vệ.
- Account recovery yếu có thể cho attacker thay passkey.
- Trang đăng ký passkey bị lỗi authorization có thể cho người khác thêm credential.
- Malware/thiết bị bị chiếm hoặc trình quản lý passkey bị compromise vẫn tạo rủi ro.
- OAuth consent phishing có thể thuyết phục user cấp quyền cho ứng dụng khác dù password/passkey không lộ.

Do đó cần bảo vệ **origin, session, account lifecycle, authorization và recovery**, không dừng ở thay mật khẩu bằng passkey.

## 7. Channel binding và chứng chỉ: một hướng chống phishing khác

Ngoài verifier name binding của WebAuthn, NIST nêu **channel binding**: authenticator output được ràng buộc mật mã với kênh bảo vệ đã thiết lập với verifier. Client-authenticated TLS trong cấu hình phù hợp là ví dụ.

Ví dụ ở hạ tầng doanh nghiệp: client có private key/chứng chỉ được cấp tin cậy, TLS client authentication chứng minh khả năng giữ khóa và ràng buộc bằng thông điệp/đàm phán của kênh TLS. Một chuỗi OTP lấy từ website giả **không thay thế** chứng minh bằng private key này.

Tuy nhiên:
- mTLS giữa **gateway và backend** không tự chứng minh **end-user browser** đã thực hiện một yếu tố phishing-resistant.
- Truyền `X-Client-Cert` từ browser công khai không phải mTLS; chỉ tin kết quả từ proxy đã được bảo vệ và sanitize.
- Mật mã mạnh không tự giải quyết cấp quyền sai, recovery yếu hoặc phiên bị chiếm.
- Cấu hình chứng chỉ, xác minh chain, revocation, rotation và client identity mapping là trách nhiệm vận hành.

## 8. Khi nào nên yêu cầu xác thực bổ sung?

Không phải mọi request cần chạy một ceremony mạnh. Step-up nên được quyết định theo **rủi ro của hành động và trạng thái xác thực**.

| Tình huống | Kiểm soát gợi ý |
|---|---|
| Đọc trang cá nhân ít nhạy cảm | Session hợp lệ, kiểm tra quyền |
| Xem lịch sử giao dịch nhạy cảm | Fresh authentication hoặc assurance phù hợp |
| Đổi email/số điện thoại recovery | Reauthentication gần thời điểm đổi + passkey/MFA theo risk |
| Đổi password hoặc tắt MFA | Fresh, mạnh, có audit/thông báo và cơ chế recovery an toàn |
| Thêm/xóa passkey hoặc authenticator | Step-up, kiểm tra account binding, chống CSRF |
| Tạo API key/refresh token lâu hạn | Fresh strong auth, giới hạn scope và audit |
| Xóa tài khoản, chuyển tiền, thanh toán giá trị cao | Xác thực mạnh và có thể **transaction-specific approval** |
| Login từ thiết bị/địa điểm bất thường | Risk-based step-up; tránh xác nhận bằng cách dễ bị giả mạo |
| Đổi quyền quản trị, cấp quyền tenant | Kiểm tra quyền admin + fresh phishing-resistant auth khi phù hợp |

Cần định nghĩa policy chính xác:
- Hành động/route nào yêu cầu.
- Yêu cầu cơ chế gì (`PASSWORD_REENTRY`, `MFA`, `PHISHING_RESISTANT`).
- Freshness tối đa; ví dụ 5 phút chỉ là một **giá trị minh họa**.
- Bằng chứng lưu ở đâu, ràng buộc với user/session/tenant nào.
- Hết hạn và thu hồi thế nào khi logout, đổi account, thay credential, compromise hoặc session rotation.
- Cần ràng buộc với giao dịch cụ thể hay chỉ session.

### Step-up không được dựa vào header tự khai

Sai:

~~~http
POST /api/admin/change-email HTTP/1.1
X-MFA-Verified: true
X-Auth-Strength: high
~~~

Bất kỳ HTTP client nào có thể đặt header tùy ý. Đúng: server hoặc IdP đáng tin phải **thực sự xác minh** yếu tố, rồi đưa proof vào session/token đã được bảo vệ, có nguồn, thời điểm và assurance được kiểm chứng. Nếu qua gateway, phải có trust boundary/mTLS và làm sạch headers từ Internet.

## 9. Bằng chứng xác thực bổ sung phải có tính ràng buộc

Một bản ghi evidence phía server có thể gồm:

~~~json
{
  "subjectId": "account-42",
  "sessionIdBinding": "server-internal-binding",
  "method": "WEBAUTHN",
  "phishingResistant": true,
  "verifiedAt": "2030-01-01T10:00:00Z",
  "expiresAt": "2030-01-01T10:05:00Z",
  "transactionId": null
}
~~~

Đây là **cấu trúc mô tả**, không phải dữ liệu client có quyền tự viết vào cookie/plain JSON. Các trường `method` và `phishingResistant` chỉ được đánh dấu dựa trên kết quả ceremony/protocol **đã được xác minh ở server**, không dựa vào tham số `method=WEBAUTHN` do browser gửi.

Phải phân biệt:
- **Server-side session proof:** application server giữ evidence và xác thực session; dùng với CSRF, session fixation protection, timeout và logout.
- **Signed identity token / OIDC ID Token:** các claim như `auth_time`, `acr`, `amr` có thể mang thông tin assurance, **chỉ sau khi signature/issuer/audience/nonce đã được kiểm tra** và có hợp đồng ngữ nghĩa rõ với IdP.
- **Frontend state:** `localStorage`, boolean trong JS, form hidden input chỉ là dữ liệu có thể thay đổi, không phải proof của yếu tố.

Một proof gần đây không nhất thiết là **transaction approval**. Nếu cần xác nhận “chuyển số tiền X tới tài khoản Y”, nên ràng buộc xác nhận với đúng nội dung đã trình cho người dùng và chống sửa dữ liệu sau khi xác nhận.

## 10. Tích hợp với IdP/OIDC: hiểu `auth_time`, `acr`, `amr`

Nếu Spring Security dùng `oauth2Login()` hoặc `oidcLogin` thông qua IdP, ứng dụng thường **không tự kiểm tra password**. IdP là nơi quyết định MFA/step-up và xuất bằng chứng có thể được RP tin theo hợp đồng.

- `auth_time`: thời điểm xác thực người dùng theo OIDC.
- `acr`: authentication context class reference, chỉ có ý nghĩa theo **hợp đồng chính sách IdP**.
- `amr`: authentication methods references, mô tả phương pháp; giá trị và khả năng xuất phụ thuộc provider.
- `max_age`: yêu cầu IdP đảm bảo tuổi xác thực tối đa theo cơ chế OIDC.
- `prompt=login`: có thể yêu cầu giao diện đăng nhập lại, nhưng không tự nói phương pháp mạnh lên.
- `acr_values`: gợi ý/yêu cầu context tùy provider; **không có đảm bảo mọi IdP đều đáp ứng**.

**Đúng quy trình:** sau redirect, Spring/OIDC client xác minh response và ID Token; application kiểm tra claim được tin cậy đã cho biết mức assurance đúng yêu cầu. Nếu IdP không cung cấp `acr` đáng tin hoặc không hỗ trợ step-up, app **không tự suy “đã có MFA” từ màn hình đăng nhập**.

Tình huống:
1. User đang có session OAuth2 Login.
2. User chọn đổi email recovery.
3. App yêu cầu IdP thực hiện authentication gần đây với phương pháp chống phishing theo profile IdP.
4. IdP xử lý ceremony và trả ID Token/claims phù hợp.
5. App xác minh response, `auth_time`, `acr`/policy, subject khớp user hiện tại; chỉ sau đó mới cho phép thay đổi.

**Cảnh báo:** không chỉ so sánh `acR == "high"` nếu chuỗi này chưa có định nghĩa assurance tương ứng; một IdP có thể dùng chuỗi tùy ý cho mức xác thực khác nhau. Đồng thời phải ngăn account switching trong khi step-up và quản lý session khi IdP trả subject khác.

## 11. Spring Security: đặt step-up ở đâu trong kiến trúc?

Spring Security 6.x cho Servlet cung cấp:
- `SecurityFilterChain` để yêu cầu authentication/authorization theo route.
- `AuthenticationManager`/`AuthenticationProvider` để xác minh credential.
- `SecurityContext` để giữ principal đã đăng nhập.
- `AuthorizationManager<RequestAuthorizationContext>` để kiểm tra điều kiện truy cập tùy chỉnh.
- CSRF/session management và `AuthenticationSuccessHandler` cho login browser.
- `.webAuthn(...)` ở Spring Security 6.5 cho passkey login khi thêm dependency phù hợp.

**Nhưng:** `authenticated()` chỉ nói request có authentication hợp lệ; nó **không nói đăng nhập bằng MFA hay passkey**, và không tự cung cấp một quy tắc “đã step-up trong 5 phút”. Policy này phải lấy evidence từ server-side verification hoặc IdP được tin.

### Pipeline gợi ý

~~~text
Browser → Spring Security session (user đã login)
   |
   | POST /sensitive/action
   v
SecurityFilterChain
   |
   +--> Authentication còn hợp lệ?
   |
   +--> Authorization: user có quyền nghiệp vụ?
   |
   +--> Step-up proof phía server:
   |      subject trùng?
   |      assurance đủ mạnh?
   |      timestamp còn mới?
   |      session/transaction binding đúng?
   |
   +--> nếu không đủ → yêu cầu reauthentication/step-up
   |
   +--> sau khi đủ → service kiểm tra resource/tenant và commit action
~~~

Việc kiểm tra step-up **không thay thế** quyền nghiệp vụ hoặc kiểm soát IDOR/BOLA. Một user đã dùng passkey vẫn không thể tự cấp quyền admin hoặc sửa tài khoản người khác.

## 12. Ví dụ Java 17 độc lập: phân biệt freshness, MFA và phishing resistance

Mẫu sau không làm xác thực thật; nó là **một chương trình chính sách mô phỏng**, chạy được với JDK 17 và cho stdout cố định. Mục đích là chống lỗi diễn giải “đã yêu cầu mã = đã chống phishing”.

File `AssurancePolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;

public final class AssurancePolicyDemo {
    enum Method {
        PASSWORD,
        TOTP,
        SMS_OTP,
        WEBAUTHN_WITH_UV
    }

    record Evidence(
            String subject,
            Instant verifiedAt,
            Set<Method> methods) {
    }

    static boolean isMfa(Evidence evidence) {
        boolean password = evidence.methods().contains(Method.PASSWORD);
        boolean secondFactor = evidence.methods().contains(Method.TOTP)
                || evidence.methods().contains(Method.SMS_OTP);

        // A properly verified passkey with user verification may be
        // a multi-factor cryptographic authenticator.
        return (password && secondFactor)
                || evidence.methods().contains(Method.WEBAUTHN_WITH_UV);
    }

    static boolean isPhishingResistant(Evidence evidence) {
        return evidence.methods().contains(Method.WEBAUTHN_WITH_UV);
    }

    static boolean allowedForSensitiveAction(
            Evidence evidence,
            String subject,
            Instant now) {

        if (!evidence.subject().equals(subject)) return false;

        Duration age = Duration.between(evidence.verifiedAt(), now);
        return !age.isNegative()
                && age.compareTo(Duration.ofMinutes(5)) < 0
                && isPhishingResistant(evidence);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2030-01-01T10:00:00Z");

        Evidence passwordTotp = new Evidence(
                "alice",
                now.minusSeconds(60),
                Set.of(Method.PASSWORD, Method.TOTP));

        Evidence passkey = new Evidence(
                "alice",
                now.minusSeconds(60),
                Set.of(Method.WEBAUTHN_WITH_UV));

        Evidence stalePasskey = new Evidence(
                "alice",
                now.minusSeconds(600),
                Set.of(Method.WEBAUTHN_WITH_UV));

        System.out.println("password-totp-mfa=" + isMfa(passwordTotp));
        System.out.println("password-totp-resistant="
                + isPhishingResistant(passwordTotp));
        System.out.println("password-totp-accepted="
                + allowedForSensitiveAction(passwordTotp, "alice", now));
        System.out.println("passkey-accepted="
                + allowedForSensitiveAction(passkey, "alice", now));
        System.out.println("stale-passkey-accepted="
                + allowedForSensitiveAction(stalePasskey, "alice", now));
        System.out.println("wrong-subject-accepted="
                + allowedForSensitiveAction(passkey, "bob", now));
    }
}
~~~

Lệnh:

~~~bash
javac AssurancePolicyDemo.java
java AssurancePolicyDemo
~~~

**Stdout chính xác:**

~~~text
password-totp-mfa=true
password-totp-resistant=false
password-totp-accepted=false
passkey-accepted=true
stale-passkey-accepted=false
wrong-subject-accepted=false
~~~

Đây chỉ là **policy model**. Trong production, một string `WEBAUTHN_WITH_UV` trong HTTP request không phải bằng chứng. Class `Evidence` chỉ được dựng từ kết quả WebAuthn authenticator assertion/IdP token đã kiểm tra đầy đủ, gắn account và phiên. Nếu ứng dụng hỗ trợ mTLS hoặc cơ chế phishing-resistant khác, cần cập nhật predicate dựa trên **proof thực**, không tin danh sách string từ client.

## 13. Demo Spring Boot 3.x + Spring Security 6.x: reauthentication bằng password

Ví dụ này minh họa **freshness và session proof**, không phải MFA. Password được nhập lại trước `POST /demo/change-email`; khi đúng, server lưu dấu thời gian ở session và chỉ cho truy cập route demo trong 5 phút.

**Giới hạn bảo mật cần đọc trước:** một password có thể bị phishing và relay; một session bị chiếm sau khi step-up cũng có thể bị lạm dụng trong thời hạn proof; endpoint demo **không thay email thật**. Production dùng một WebAuthn step-up ceremony hoặc assurance của IdP được tin cậy nếu cần phishing resistance. Không gắn nhãn `phishingResistant=true` cho ví dụ nhập lại mật khẩu.

### 13.1. Cấu trúc project

~~~text
reauth-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/reauth/
    │   ├── ReauthDemoApplication.java
    │   ├── StepUpProof.java
    │   ├── FreshPasswordAuthorizationManager.java
    │   ├── SecurityConfiguration.java
    │   └── StepUpController.java
    ├── resources/
    │   ├── application.yml
    │   └── templates/step-up.html
    └── ...
~~~

### 13.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reauth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 13.3. `application.yml`

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  user:
    password: ${DEMO_USER_PASSWORD}
~~~

Cung cấp password qua biến môi trường khi chạy demo; không commit password thật hay dùng credential test ở môi trường mở Internet.

### 13.4. `ReauthDemoApplication.java`

~~~java
package com.example.reauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReauthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReauthDemoApplication.class, args);
    }
}
~~~

### 13.5. `StepUpProof.java`: thông tin chỉ lưu phía session server

~~~java
package com.example.reauth;

import java.io.Serializable;
import java.time.Instant;

public record StepUpProof(
        String username,
        Instant verifiedAt
) implements Serializable {
    public static final String SESSION_KEY = "demo.reauth.proof";
}
~~~

Một session attribute không phải JWT và không được nhận từ body/header do client tự gửi. Bản ghi proof này **chỉ có mức `password re-entry`**, không có trường giả vờ rằng đây là MFA. Khi triển khai đa instance, session store phải có tính toàn vẹn, TTL và kiểm soát truy cập phù hợp.

### 13.6. `FreshPasswordAuthorizationManager.java`

~~~java
package com.example.reauth;

import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

public final class FreshPasswordAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private static final Duration MAX_AGE = Duration.ofMinutes(5);

    @Override
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        if (current == null || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        HttpSession session = context.getRequest().getSession(false);
        Object stored = session == null
                ? null : session.getAttribute(StepUpProof.SESSION_KEY);

        if (!(stored instanceof StepUpProof proof)) {
            return new AuthorizationDecision(false);
        }

        Instant now = Instant.now();
        Duration age = Duration.between(proof.verifiedAt(), now);

        boolean allowed = proof.username().equals(current.getName())
                && !age.isNegative()
                && age.compareTo(MAX_AGE) < 0;

        return new AuthorizationDecision(allowed);
    }
}
~~~

**Điểm mạnh của cấu trúc này:** bằng chứng không đến từ header do client tự khai, có subject và thời hạn, route nhạy cảm dùng `AuthorizationManager` của Spring Security. **Giới hạn:** kiểm tra chỉ yêu cầu password đã nhập lại, không chứng minh MFA, không chứng minh user đang ở domain thật và chưa ràng buộc với nội dung giao dịch cụ thể.

### 13.7. `SecurityConfiguration.java`

~~~java
package com.example.reauth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        var user = User.withUsername("alice")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        var defaultSuccess =
                new SavedRequestAwareAuthenticationSuccessHandler();
        var fresh = new FreshPasswordAuthorizationManager();

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers(HttpMethod.POST,
                                "/demo/change-email").access(fresh)
                        .anyRequest().authenticated())
                .formLogin(form -> form.successHandler(
                        (request, response, authentication) -> {
                            var session = request.getSession(false);
                            if (session != null) {
                                session.removeAttribute(
                                        StepUpProof.SESSION_KEY);
                            }
                            defaultSuccess.onAuthenticationSuccess(
                                    request, response, authentication);
                        }))
                .build();
    }
}
~~~

- `DaoAuthenticationProvider` kiểm tra password bằng `PasswordEncoder`, không so sánh plaintext string.
- `formLogin` tạo login page mặc định. Success handler xóa proof cũ để **login mới không kế thừa step-up cũ**, rồi sử dụng hành vi redirect mặc định.
- `POST /demo/change-email` yêu cầu recent proof; không chỉ `authenticated()`.
- CSRF mặc định **vẫn bật** đối với POST; session fixation và logout được Spring quản lý. Không tắt CSRF chỉ để tránh gửi token trong form.
- Các route còn lại cần đăng nhập; đây là demo local chứ chưa có policy account/tenant/roles production.
- Hệ thống production còn phải invalid proof khi đổi credential, revoke account, session/security events hoặc thay assurance.

### 13.8. `StepUpController.java`: recheck password hiện tại

~~~java
package com.example.reauth;

import java.time.Instant;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class StepUpController {

    private final AuthenticationManager manager;

    public StepUpController(AuthenticationManager manager) {
        this.manager = manager;
    }

    @GetMapping("/step-up")
    public String form() {
        return "step-up";
    }

    @PostMapping("/step-up")
    public String verifyAgain(
            @RequestParam("password") String password,
            Authentication current,
            HttpServletRequest request) {

        try {
            Authentication checked = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            current.getName(), password));

            if (!checked.isAuthenticated()
                    || !checked.getName().equals(current.getName())) {
                return "redirect:/step-up?error";
            }

            // This is recent PASSWORD proof only, not MFA.
            request.getSession(true).setAttribute(
                    StepUpProof.SESSION_KEY,
                    new StepUpProof(current.getName(), Instant.now()));
            return "redirect:/me";
        } catch (AuthenticationException ex) {
            return "redirect:/step-up?error";
        }
    }

    @GetMapping("/me")
    @ResponseBody
    public Map<String, Object> me(Authentication authentication) {
        return Map.of("username", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }

    @PostMapping("/demo/change-email")
    @ResponseBody
    public Map<String, String> simulateSensitiveAction() {
        // Illustrates authorization only; NO email is changed.
        return Map.of("result", "recent password proof accepted");
    }
}
~~~

**Giới hạn của đoạn code:** Endpoint POST `/step-up` cần **rate limiting**, anti-automation, logging an toàn, generic errors và cơ chế session/cookie phù hợp khi triển khai thật. Demo không xử lý quy trình reset password, chống phishing, MFA hay business transaction. Không dùng password nhập lại trong request này như bằng chứng WebAuthn.

### 13.9. `templates/step-up.html`

File `src/main/resources/templates/step-up.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Xác minh lại bằng mật khẩu</title>
</head>
<body>
  <h1>Xác minh lại bằng mật khẩu</h1>
  <p>Ví dụ này chỉ yêu cầu nhập lại mật khẩu,
     không phải MFA và không chống phishing.</p>
  <p th:if="${param.error}">Không thể xác minh. Vui lòng thử lại.</p>
  <form th:action="@{/step-up}" method="post">
    <label for="password">Mật khẩu hiện tại</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Xác minh lại</button>
  </form>
</body>
</html>
~~~

Hidden CSRF token do Spring Security cấp và kiểm chứng, không phải bằng chứng MFA. Không cho frontend tự đưa `verifiedAt` hoặc `method` vào session. Trang production phải dùng HTTPS, CSP, chống XSS/clickjacking và không có third-party scripts không đáng tin.

### 13.10. Chạy thử và kết quả dự kiến

Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD='local-demo-password-only'
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "local-demo-password-only"
mvn spring-boot:run
~~~

Đây là password test cho môi trường localhost, **không được dùng ở Internet hoặc commit vào source**.

Các bước:
1. Truy cập `http://localhost:8080/login`, login user `alice` bằng password demo.
2. Trước khi step-up, một POST hợp lệ về CSRF tới `/demo/change-email` trả **403 Forbidden** vì chưa có recent proof.
3. Mở `/step-up`, nhập đúng password hiện tại. Controller xác minh lại qua `AuthenticationManager` và lưu `StepUpProof` server-side.
4. POST `/demo/change-email` trong 5 phút, với session + CSRF hợp lệ, trả JSON dạng:

~~~json
{"result":"recent password proof accepted"}
~~~

5. Sau ít nhất 5 phút kể từ `verifiedAt`, cùng action bị **403**. Password sai không cấp proof.
6. Logout hoặc login mới phải không được tái dùng proof cũ. Thử cả phiên trình duyệt khác.

Không có lệnh `curl` giản đơn vì form login/step-up dùng CSRF token và session cookie; thao tác bằng browser hoặc integration test `MockMvc` giữ đúng trạng thái. **Demo chỉ chứng minh freshness của password**, không có bất kỳ cam kết nào về chống phishing trong ví dụ này.

## 14. Chuyển từ demo reauthentication sang phishing-resistant step-up

Không đủ để đổi `new StepUpProof(username, Instant.now())` thành `method="WEBAUTHN"`. Phải **thay nguồn phát hành proof**:

1. User đang có session, muốn thực hiện hành động nhạy cảm.
2. Server yêu cầu WebAuthn assertion mới cho đúng RP ID, tạo challenge CSPRNG gắn session/user và TTL.
3. Browser dùng `navigator.credentials.get({publicKey: ...})` với credential đã đăng ký.
4. Server kiểm tra challenge, `clientDataJSON.type`, origin, RP ID hash, UP/UV, credential ID, signature và account mapping bằng thư viện WebAuthn đã được kiểm thử.
5. **Chỉ khi verification thành công** mới lưu evidence `method=WEBAUTHN`, `verifiedAt`, `subject`, `session binding`.
6. AuthorizationManager yêu cầu **đúng method/assurance, freshness và session**, không chỉ timestamp.
7. Nếu thay đổi khoản thanh toán/email, cân nhắc proof gắn với `transactionId` và nội dung hành động.

Spring Security 6.5 cung cấp passkey login với `webAuthn` DSL và `webauthn4j-core`. Cấu hình cơ bản:

~~~java
// Đoạn minh họa dùng bên trong HttpSecurity Servlet:
http
    .formLogin(org.springframework.security.config.Customizer.withDefaults())
    .webAuthn(webAuthn -> webAuthn
        .rpId("example.org")
        .allowedOrigins("https://login.example.org"));
~~~

Cấu hình trên **bật passkey registration/login**; nó **không tự triển khai step-up cho mọi endpoint** hay tự phát proof `WEBAUTHN` như trong phần 13. Muốn có step-up assertion trong một session đã login, phải dùng một integration/ceremony được hỗ trợ đúng theo phiên bản hoặc thiết kế thêm challenge/verification/repository/phân quyền. Không tự viết xác minh chữ ký WebAuthn bằng cách parse JSON tùy ý.

Nếu dùng IdP, ứng dụng nên yêu cầu step-up ở IdP và xác minh `acr`/`auth_time`/subject sau callback. Không cho website client tự tuyên bố đã thực hiện WebAuthn.

## 15. Bảo vệ phiên đăng nhập và cookie sau MFA

Phishing-resistant login bảo vệ **nghi thức xác thực**, nhưng ứng dụng thường dùng session cookie hoặc access token làm **bearer credential** sau khi login. Ai đánh cắp được session hợp lệ vẫn có thể dùng quyền của session nếu thiếu biện pháp bổ sung.

Phòng thủ:
- HTTPS/TLS, cookie `Secure`, `HttpOnly`, `SameSite` phù hợp, path/domain hạn chế.
- Chống XSS, CSRF và clickjacking; CSP và kiểm soát script/tài nguyên bên thứ ba.
- Session fixation protection khi login, idle/absolute timeout và logout server-side.
- Token/session revocation khi phát hiện compromise hoặc thay password/credential.
- Short-lived step-up evidence, reset sau logout/login mới và nhạy cảm với account change.
- Đối với thao tác giá trị cao, hỏi lại yếu tố mạnh và xác nhận nội dung hành động thay vì chỉ tin session chung.
- Không log `Cookie`, `Authorization`, raw OTP, recovery code hoặc session ID.
- Với SPA và OAuth, giảm nguy cơ token ở JS/storage và đánh giá mô hình Backend-for-Frontend (BFF).

**Không đánh đồng:** mã OTP nhập tay dễ bị phishing và session cookie bị đánh cắp là **hai rủi ro khác nhau**. WebAuthn có thể giảm một rủi ro nhưng không thay tất cả kiểm soát bảo vệ session.

## 16. Enrollment, recovery và fallback là điểm yếu thường bị bỏ qua

### 16.1. Thêm thiết bị mới có thể nguy hiểm hơn đăng nhập

Nếu attacker đã có session chưa đủ an toàn và có thể đăng ký MFA/passkey của họ vào account nạn nhân, những lần đăng nhập tiếp theo có thể bị chiếm quyền mà không cần password cũ. Vì vậy add/remove authenticator cần:
- Fresh reauthentication/step-up đủ mạnh;
- Xác minh account binding, không tin user ID ở form;
- CSRF, audit và thông báo tới liên hệ đã xác minh;
- Session/credential revocation sau thay đổi bất thường;
- Chặn việc xóa phương thức mạnh cuối cùng mà không có quy trình recovery được kiểm soát.

### 16.2. Recovery không được hạ cấp vô điều kiện

Một hệ thống quảng bá “phishing-resistant MFA” nhưng cho bất kỳ ai chỉ biết email và OTP SMS tắt passkey rồi đăng nhập có thể không đạt mức bảo đảm tổng thể mong muốn.

Chính sách recovery nên:
- dùng các yếu tố/đường xác minh phù hợp mức rủi ro;
- giới hạn số lần thử, có audit/notification và thời gian trì hoãn nếu cần;
- kiểm tra thay đổi SIM, email account takeover, link scanner;
- không tự động bỏ MFA khi user bấm “Tôi không có thiết bị” mà không có quy trình xác minh độc lập;
- đưa tài khoản vào trạng thái review hoặc áp dụng giới hạn giao dịch sau recovery rủi ro cao.

### 16.3. Downgrade qua giao thức cũ

Một hệ thống có WebAuthn trên website mới nhưng để:
- HTTP Basic password-only legacy API;
- một mobile endpoint không cần MFA;
- password login/admin fallback yếu;
- OIDC login flow không đảm bảo `acr` sau step-up;

thì attacker sẽ chọn **đường yếu nhất**. Inventory mọi entry point, ngắt giao thức lỗi thời và áp dụng cùng mức assurance cho hành động nhạy cảm, bất kể kênh.

## 17. Hành vi người dùng và thiết kế sản phẩm hỗ trợ chống phishing

Biện pháp kỹ thuật nên đi cùng UX:
- Hướng dẫn đăng nhập qua bookmark/app tin cậy; password manager thường không tự điền trên domain giả.
- Hiển thị domain/tên hệ thống chính xác và không dùng URL rút gọn trong email bảo mật khi không cần thiết.
- Không yêu cầu người dùng chia sẻ OTP/recovery code qua chat/support.
- Phân biệt push approval do user khởi tạo với prompt đột ngột; dùng number matching nếu triển khai push, giới hạn fatigue.
- Hiển thị thông tin thiết bị mới/session mới và hỗ trợ thu hồi.
- Cho người dùng xem và quản lý passkey/MFA methods, có backup an toàn.
- Gửi thông báo cho hành động nhạy cảm (thay password, email, yếu tố xác thực).
- Không coi “đã vượt CAPTCHA” là bằng chứng chính chủ.
- Giảm false positives cho accessibility và người dùng dùng shared device, đồng thời giữ kiểm soát chống automation.

**Đào tạo người dùng có giá trị, nhưng không thay giao thức chống phishing.** Mục tiêu là giảm phụ thuộc vào việc người dùng phát hiện một trang mạo danh có giao diện giống hệt.

## 18. Tình huống trước và sau khi nâng cấp xác thực

### Tình huống A: mật khẩu đơn lẻ

~~~text
Password bị nhập ở trang giả
   → attacker có password
   → đăng nhập thật có thể thành công
~~~

Phòng thủ cơ bản: password manager, mật khẩu duy nhất, sàng lọc breached passwords, rate limiting, thông báo đăng nhập, MFA.

### Tình huống B: password + TOTP

~~~text
Password và OTP bị nhập ở trang giả
   → attacker relay cả hai gần thời gian thực
   → vẫn có khả năng chiếm session
~~~

Tốt hơn password-only khi password lộ riêng lẻ, nhưng không miễn nhiễm phishing theo thời gian thực. Cần bảo vệ yếu tố bổ sung, session và hướng tới WebAuthn.

### Tình huống C: passkey WebAuthn đúng cấu hình

~~~text
Website giả khác RP ID
   → browser/authenticator không tạo assertion
      hợp lệ cho domain RP thật qua website giả
   → attacker không đơn giản relay một OTP đã nhập tay
~~~

Vẫn cần origin/RP ID validation, bảo vệ session sau login, account recovery và chống XSS.

### Tình huống D: step-up trước đổi email

~~~text
Session thông thường (đã login)
   → yêu cầu đổi email
   → server cần fresh strong authentication
   → verify bằng WebAuthn/IdP assurance
   → account & target contact policy
   → commit thay đổi, audit & notify
~~~

Nếu hệ thống chỉ yêu cầu nhập lại password, đó là **fresh password evidence**; dù bước này giảm rủi ro một số session bị để quên, nó **không tạo phishing resistance**.

## 19. Ma trận kiểm thử bảo mật

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Password đúng trên website giả | Không coi password là proof phishing-resistant |
| Password + TOTP đúng nhưng bị relay | Có nguy cơ thành công; phát hiện/giảm rủi ro và chuyển sang WebAuthn |
| TOTP hết hạn hoặc đã dùng | Từ chối, single-use và TTL đúng |
| OTP sai liên tiếp | Rate limit/attempt cap, log an toàn |
| Password re-entry thành công | Chỉ tạo **fresh password proof**, không gán MFA |
| Reauth proof của account khác | Không được dùng cho account hiện hành |
| Reauth proof hết hạn | Sensitive route trả 403/step-up required |
| Đăng nhập mới khi session cũ còn proof | Proof cũ bị xóa/không dùng lại |
| Logout rồi dùng lại cookie cũ | Không tạo session hợp lệ |
| Client gửi `X-MFA-Verified:true` | Không được cấp quyền |
| Trình giả mạo gửi `acr=high` trong query | Không được tin; kiểm tra trusted IdP token |
| OIDC subject thay đổi sau step-up | Không gắn proof vào account cũ |
| OIDC `acr` không đáp ứng policy | Không cho hành động nhạy cảm |
| OIDC token sai issuer/audience/nonce | Từ chối trong luồng OIDC |
| WebAuthn challenge cũ/sai | Từ chối assertion |
| WebAuthn origin/RP ID hash sai | Từ chối |
| WebAuthn signature bị sửa | Từ chối |
| WebAuthn không có UV khi policy yêu cầu | Từ chối |
| Credential bị thu hồi hoặc account disabled | Từ chối |
| Login bằng password-only khi route yêu cầu phishing-resistant | Không cho qua chỉ vì session authenticated |
| Account recovery bằng đường yếu | Không được tự hạ mức assurance của toàn bộ policy |
| Session cookie bị lộ sau MFA | Có cơ chế revoke/detect/reauth trước action nhạy cảm |
| Thao tác đổi email của tenant khác | Authorization/object-level policy từ chối |
| Thay đổi nội dung giao dịch sau approval | Proof transaction-bound không còn hợp lệ |
| Login từ IP/device mới | Risk-based step-up và logging đúng |
| XSS/clickjacking ở origin thật | CSP, chống XSS/CSRF/frame và test độc lập |
| Credential/MFA recovery code xuất hiện trong log | Bị redaction, không trả lại secret cho client |

**Test cần phân biệt các tầng:** JUnit kiểm thử policy thuần; `MockMvc` kiểm tra endpoint/CSRF/session; integration test với IdP và WebAuthn library kiểm tra cryptographic ceremony. Không suy ra “đã chống phishing” chỉ vì mock principal có authority `MFA` hoặc API trả 200.

## 20. Các lỗi thường gặp

1. **Đánh đồng MFA và phishing resistance:** password+TOTP có thể là MFA nhưng dễ bị relay.
2. **Coi mã OTP ngắn hạn là không thể đánh cắp:** attacker có thể dùng ngay mã thật trong khoảng TTL.
3. **Dùng hai password rồi gọi là hai yếu tố:** vẫn là cùng loại factor.
4. **Coi number matching push mặc định là WebAuthn:** chống fatigue tốt hơn, nhưng không tự có cryptographic verifier binding.
5. **Tin một cờ `mfa=true` từ frontend/header:** phải được phát hành sau verification thật, ở server/IdP tin cậy.
6. **Dùng `authenticated()` thay kiểm tra assurance:** không phân biệt password-only/passkey.
7. **Tin `acr` khi không có contract với IdP:** ngữ nghĩa tùy provider; phải kiểm tra token và profile.
8. **Không kiểm tra `auth_time`/freshness:** một session nhiều ngày trước có thể vượt action nhạy cảm.
9. **Không ràng buộc step-up với subject/session:** evidence của account A bị áp dụng cho B.
10. **Không thu hồi step-up proof sau logout/login mới:** proof cũ có thể bị sử dụng lại.
11. **Coi reauth bằng password là chống phishing:** password vẫn là bí mật có thể nhập ở website giả.
12. **Không dùng CSRF ở browser POST reauth:** attacker có thể lạm dụng phiên/ngữ cảnh.
13. **Đưa credential/OTP vào logs:** hệ thống quan sát trở thành điểm rò rỉ.
14. **Bỏ qua quyền nghiệp vụ sau step-up:** proof mạnh không có nghĩa user được sửa dữ liệu của account khác.
15. **Bật passkey nhưng recovery yếu:** attacker chiếm account bằng đường không cần passkey.
16. **Tin website `https` bất kỳ là domain thật:** website giả cũng có thể có chứng chỉ HTTPS hợp lệ cho domain giả.
17. **Bỏ qua RP ID/origin trong WebAuthn verifier:** phá mô hình phishing resistance.
18. **Dùng WebAuthn passwordless login làm bằng chứng step-up tự động:** cần kiểm tra ceremony, thời gian và account binding theo policy.
19. **Coi MFA ngăn trộm session:** MFA chủ yếu bảo vệ authentication; session vẫn cần bảo vệ.
20. **Không kiểm tra hành động đã được duyệt:** fresh authentication không phải bằng chứng đã chấp thuận mọi transaction.
21. **Không đo false positives khi tăng step-up:** làm người dùng khó thao tác hoặc phải chuyển sang đường recovery yếu.
22. **Để legacy endpoint bypass MFA:** mọi entry point nhạy cảm cần policy nhất quán.

## 21. Checklist production

- [ ] Đã kiểm kê các authentication entry points (web, mobile, admin, API, IdP, legacy).
- [ ] Phân loại rõ password, SMS/TOTP, push và WebAuthn theo assurance, không theo nhãn marketing.
- [ ] Có cơ chế phishing-resistant cho tài khoản/hành động rủi ro cao khi cần.
- [ ] WebAuthn kiểm tra challenge, origin, RP ID, signature, UP/UV và account binding.
- [ ] MFA enrollment, removal, reset và account recovery có step-up/audit/notification.
- [ ] Không tự cấp quyền từ `mfa=true` hoặc `acr` chưa được xác minh.
- [ ] IdP `auth_time`, `acr`, `amr` có hợp đồng ngữ nghĩa và được kiểm tra.
- [ ] Freshness và assurance đều được enforced **trên server**, gắn đúng subject/session.
- [ ] Sensitive business actions có authorization theo tenant/object riêng.
- [ ] Step-up proof có TTL, bị invalid khi logout/login/revoke/credential compromise.
- [ ] Giao dịch nhạy cảm được phê duyệt đúng nội dung và chống sửa sau approval khi cần.
- [ ] Cookie/session/TLS/CSP/CSRF/XSS được bảo vệ, có session fixation defense.
- [ ] OTP có TTL, attempt limits, single-use, chống spam, không log.
- [ ] Rate limiting và detection cho phishing follow-up, OTP abuse, MFA fatigue.
- [ ] Phát hiện session takeover sau khi MFA, có cảnh báo và quy trình revoke.
- [ ] Không bypass assurance qua legacy Basic, password fallback hoặc recovery không kiểm soát.
- [ ] Đã kiểm thử âm tính: wrong domain, replay, wrong subject, stale proof, fake headers, weak recovery.
- [ ] Hướng dẫn user và support không yêu cầu gửi password/OTP/recovery code.

## 22. Ghi nhớ

**MFA trả lời “có bao nhiêu loại bằng chứng độc lập”; phishing resistance trả lời “giao thức có ngăn gửi bằng chứng cho verifier giả mạo không”.** Đây là hai câu hỏi khác nhau.

- Password, SMS OTP, email OTP, TOTP và recovery code là những bí mật hoặc output có thể nhập lại và chuyển tiếp.
- OTP một lần/TTL ngắn chống một số hình thức lạm dụng, nhưng không tự ngăn **relay theo thời gian thực**.
- Reauthentication bằng password giúp tăng freshness, **không phải MFA và không chống phishing**.
- WebAuthn/FIDO2 dùng khóa công khai ràng buộc RP ID/origin và challenge để giảm tấn công phishing vào ceremony, nếu server xác minh đúng.
- Cần phân quyền, giới hạn phiên, step-up thực, kiểm soát enrollment/recovery và protection sau login.
- Spring Security là nền tảng cho authentication/authorization/session, nhưng assurance/step-up policy phải được thiết kế, phát hành evidence và kiểm tra một cách đáng tin.

## 23. Tài liệu tham khảo

1. [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): phishing resistance, verifier name binding, channel binding, OTP và MFA.
2. [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): MFA factors, OTP, push fatigue, phishing-resistant passkeys và recovery.
3. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, risk-based authentication, generic errors và session.
4. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session hijack, cookie protection và timeout.
5. [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html): login abuse và MFA phòng thủ.
6. [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/): origin, RP ID, registration, assertion và các kiểm tra giao thức.
7. [Spring Security 6.5 — Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): tích hợp WebAuthn trong Spring Security.
8. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` và rules cho endpoint.
9. [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter`, handlers và SecurityContext.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `auth_time`, `acr`, `amr`, `max_age` và authentication request/ID Token claims.
