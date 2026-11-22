# MFA, hai bước đăng nhập và sự độc lập của các yếu tố xác thực

> **Phạm vi:** Spring Security – Authentication, chủ đề **Nhiều yếu tố**. Bài này tập trung vào bản chất của multi-factor authentication (MFA), sự khác nhau giữa xác minh **hai bước** và xác minh **hai yếu tố độc lập**, thiết kế luồng đăng nhập/step-up, các nguy cơ triển khai và cách tích hợp trong Spring Security. Ví dụ dành cho Java 17+, Spring Boot 3.x / Spring Security 6.x; phần hỗ trợ MFA tích hợp sẵn được ghi rõ là **Spring Security 7.x**, thường đi với Spring Boot 4.x.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **two-step verification (2SV)**, **two-factor authentication (2FA)** và **MFA**.
2. Phân loại bằng chứng **điều biết (knowledge)**, **điều sở hữu (possession)** và **đặc điểm sinh trắc (inherence)**; chứng minh vì sao hai lần xác thực chưa chắc có hai yếu tố.
3. Đánh giá **tính độc lập thực tế**: yếu tố có khác loại hay không, có thể bị đánh cắp bởi cùng một sự cố hay không, có bị vượt qua bởi luồng khôi phục, thiết bị, email, SMS hoặc phiên đăng nhập không.
4. Thiết kế bước một/bước hai có **session binding**, thời hạn, retry limit, one-time verification, chuyển trạng thái đúng và không cấp quyền nhạy cảm trước khi đủ bằng chứng.
5. Hiểu lợi ích của **FIDO2/WebAuthn** có kiểm tra nguồn gốc (origin/RP ID) so với OTP nhập tay dễ bị phishing relay; chọn cách step-up theo rủi ro.
6. Nhận biết khác biệt phiên bản Spring Security: **6.x phải thiết kế/ghép MFA phù hợp**; **7.x** có `FactorGrantedAuthority` và `@EnableMultiFactorAuthentication`.
7. Xây dựng test xác minh cả **số lần** lẫn **tính độc lập** và **nguồn phát sinh bằng chứng**, không chỉ test OTP đúng/sai.

## 1. Authentication và MFA giải quyết vấn đề gì?

**Authentication (xác thực)** là quá trình kiểm tra bằng chứng để kết luận một chủ thể thực sự đang kiểm soát một danh tính hoặc authenticator được đăng ký. **Authorization (phân quyền)** quyết định danh tính đã xác thực được phép làm gì ở tài nguyên hiện tại. MFA nâng độ tin cậy của bước authentication; nó không tự cấp `ROLE_ADMIN` hay bỏ qua quy tắc quyền của API.

Ví dụ: một ứng dụng có tài khoản `lan`, được gán `ROLE_ACCOUNTANT` và sở hữu một TOTP authenticator. Khi đăng nhập:

```text
Browser của lan
    │ 1) Nhập username + password (yếu tố KNOWLEDGE)
    ▼
Spring Security / AuthenticationManager
    │ 2) Verify password, xác định user lan
    │    CHƯA cho truy cập chức năng cần MFA
    ▼
Pending MFA challenge (server-side)
    │ 3) Yêu cầu authenticator đã đăng ký
    ▼
Ứng dụng TOTP / security key / passkey
    │ 4) Cung cấp bằng chứng yếu tố thứ hai
    ▼
MFA verifier
    │ 5) Verify, ràng buộc với cùng lan và challenge
    │ 6) Chống replay, kiểm tra hiệu lực, số lần thử
    ▼
Hoàn tất Authentication phù hợp / nâng mức bảo đảm phiên
    │ 7) Session fixation protection và lưu trạng thái cần thiết
    ▼
Authorization
    ├─ User có ROLE_ACCOUNTANT và yêu cầu MFA đã đạt → cho phép
    └─ Thiếu quyền tài nguyên / session bị thu hồi → từ chối
```

Không được dùng một biến do browser gửi như `mfaPassed=true` làm căn cứ hoàn tất bước hai. Bằng chứng phải được **server hoặc một verifier tin cậy kiểm chứng**, liên kết với cùng user/session/request và thời điểm.

### Authentication không đồng nghĩa “đã đủ MFA”

Một `Authentication.isAuthenticated() == true` trong Spring Security thường cho biết **cơ chế authentication hiện tại đã thành công**; giá trị đó không tự chứng minh đã có hai yếu tố độc lập. Trong ứng dụng chỉ dùng password, `UsernamePasswordAuthenticationToken` sau khi xác minh password cũng có thể là authenticated. Vì vậy API đòi MFA phải có **authorization rule** hoặc MFA gate cụ thể, không chỉ kiểm tra `authenticated()`.

## 2. Hai bước (2SV) khác hai yếu tố (2FA/MFA)

**Two-step verification (2SV)** là cách sắp xếp UX: người dùng làm **hai thao tác / hai lần nhập**. Nó không tự nói các bằng chứng thuộc bao nhiêu nhóm.

**2FA** là trường hợp MFA với **hai loại yếu tố độc lập**. MFA nói chung có **ít nhất hai yếu tố thuộc các nhóm khác nhau**, hoặc một authenticator đa yếu tố được thiết kế/kiểm định để yêu cầu đồng thời nhiều yếu tố. Điều quan trọng là **bản chất bằng chứng**, không phải số màn hình, số form, số OTP hay số lần người dùng bấm nút.

| Quy trình | Số bước | MFA không? | Vì sao |
|---|---:|---|---|
| Password, sau đó hỏi PIN gửi sẵn mà người dùng nhớ | 2 | **Không** | Password và PIN đều là điều biết |
| Password rồi câu hỏi bảo mật (“trường học đầu tiên?”) | 2 | **Không** | Cả hai là điều biết, còn dễ đoán/khai thác |
| Password nhập hai lần ở hai trang | 2 | **Không** | Vẫn chỉ một yếu tố knowledge |
| Password + TOTP từ authenticator đã đăng ký | 2 | **Có thể là MFA** | Password là knowledge; khóa TOTP đã đăng ký đại diện possession; phụ thuộc thiết kế lưu khóa/chống compromise |
| Password + security key FIDO2 | 2 | **Có, khi thực sự dùng hai yếu tố riêng** | Knowledge + chứng minh sở hữu private key và kiểm tra origin/RP ID |
| Password + SMS OTP | 2 | **Có thể tính hai loại yếu tố nhưng yếu hơn** | Kênh số điện thoại/SIM có nguy cơ SIM swap, intercept, phishing; NIST xếp PSTN OOB là restricted |
| Password + email code/link | 2 | **Không nên coi tự động là MFA mạnh** | Mailbox có thể chỉ được bảo vệ bằng cùng password; NIST 800-63B-4 **không cho dùng email làm out-of-band authenticator** cho yêu cầu theo chuẩn |
| Đăng nhập bằng passkey có user verification (PIN/sinh trắc tại authenticator) | Có thể 1 lần tương tác | **Có thể là authenticator đa yếu tố** | Proof sở hữu khóa và hoạt động xác minh người dùng tại authenticator; cần kiểm tra WebAuthn flags/chính sách |
| Password + địa chỉ IP doanh nghiệp | 2 điều kiện | **Không** | IP là tín hiệu ngữ cảnh/giới hạn network, không phải yếu tố xác thực danh tính |
| Password + CAPTCHA | 2 bước | **Không** | CAPTCHA là biện pháp chống bot, không phải bằng chứng sở hữu authenticator |
| Hai lần push approve trên cùng app đã bị chiếm | 2 lần | **Không thêm yếu tố độc lập** | Hai thao tác chỉ tái sử dụng cùng một bề mặt bị chiếm |

**Cẩn thận với thuật ngữ “OTP”:** một OTP có thể là *số bảo mật gửi qua SMS/email*, *TOTP dựa trên secret trong app*, hoặc *hardware OTP*. Chúng có threat model khác nhau. Số sáu chữ số không tự nói đó là yếu tố sở hữu độc lập, không tự chống phishing và không tự chứng minh một thiết bị riêng.

## 3. Ba nhóm yếu tố xác thực và nguồn chứng minh

### 3.1. Điều người dùng biết — Knowledge

Ví dụ: password, PIN dùng để đăng nhập từ xa, passphrase.

- **Rủi ro:** bị đoán, phishing, credential stuffing, keylogger, reuse hoặc social engineering.
- **Kiểm chứng đúng:** server so khớp với password hash thích hợp (Argon2id/bcrypt/PBKDF2 theo policy), có giới hạn đoán mật khẩu; không lưu plain text.
- **Hai password khác nhau vẫn chỉ là một nhóm:** attacker có thể chiếm cả hai từ password manager, phishing hoặc malware.

Cần phân biệt PIN **được gửi đến server để đăng nhập** (knowledge factor) với PIN **chỉ dùng tại thiết bị để mở khóa private key** (activation secret cho một multi-factor cryptographic authenticator). Cách triển khai sau có thể là một phần của authenticator đa yếu tố; không chỉ nhìn chữ “PIN” để kết luận.

### 3.2. Điều người dùng sở hữu — Possession

Ví dụ: security key FIDO2, private key/certificate được bảo vệ, hardware OTP, authenticator app có bí mật TOTP đã đăng ký, thiết bị OOB được xác minh.

- **Bằng chứng:** chứng minh có quyền sử dụng khóa/thiết bị đã được liên kết đúng tài khoản. Không chỉ kiểm tra một chuỗi “deviceId” do client khai.
- **Rủi ro:** thất lạc, bị malware điều khiển, SIM swap, đánh cắp seed TOTP, sao chép khóa, push fatigue, recovery yếu, token bị relay.
- **Đăng ký an toàn:** ràng buộc authenticator với local user sau phiên có bảo đảm phù hợp; bảo vệ enrollment/change/remove factors.

TOTP được gõ trên cùng chiếc điện thoại dùng để đăng nhập **không tự khiến kết hợp vô hiệu MFA**: nó vẫn có thể cung cấp một bí mật sở hữu đã đăng ký riêng. Nhưng nếu password và seed TOTP đều nằm trong cùng một nơi bị malware chiếm, **độc lập chống tấn công thực tế giảm đáng kể**. Phải phân biệt “khác loại yếu tố” với “không có chung điểm thất bại”.

### 3.3. Đặc điểm người dùng — Inherence

Ví dụ: fingerprint, face recognition hoặc iris khi được một authenticator đáng tin kiểm tra.

- **Điểm tinh tế:** ảnh chụp khuôn mặt browser upload hoặc sự kiện JavaScript “fingerprint passed” **không tự là bằng chứng an toàn** cho server. Cần dựa vào authenticator/API tin cậy có challenge, chữ ký và kết quả xác minh được ràng buộc.
- Trong FIDO2/WebAuthn, biometric thường **được kiểm tra cục bộ** để unlock khóa và không cần gửi dữ liệu sinh trắc về Spring backend.
- Khó thu hồi/đổi biometric sau khi rò dữ liệu; thiết kế lưu trữ và privacy phải cẩn trọng.

### 3.4. Location, risk score và behavioral signals

Địa lý, device fingerprint, IP allowlist, thời gian truy cập bất thường, lịch sử hành vi là **risk signals** hữu ích để tăng yêu cầu bảo mật hoặc từ chối request. Theo NIST 800-63B-4 và cách phân loại của OWASP, những tín hiệu này **không tự thay thế bằng chứng yếu tố xác thực riêng**. “Password + đang ở văn phòng” không phải MFA.

## 4. “Độc lập” có những tầng nào?

Câu hỏi thiết kế không chỉ là “có hai nhãn factor khác nhau không?”, mà phải xem **cùng một kẻ tấn công có thể vượt qua cả hai bằng cùng một lần compromise hay không**.

### 4.1. Độc lập về **loại bằng chứng**

Password và PIN đều knowledge. Password và TOTP có hai loại factor danh nghĩa. Password với security key có knowledge + cryptographic possession. Với một multi-factor passkey, cần xem cơ chế **user verification (UV)** (PIN/biometric) và xác thực private key: không phải mọi assertion WebAuthn đều bảo đảm UV.

### 4.2. Độc lập về **bí mật và thiết bị lưu trữ**

Nếu password và seed TOTP cùng được export sang một bản backup không mã hóa, một cuộc xâm nhập backup có thể phá cả hai. Nếu password manager và TOTP app cùng nằm trên điện thoại bị root/malware, tấn công thiết bị có thể lấy cả password lẫn OTP. Việc phân loại knowledge/possession không loại bỏ rủi ro dùng chung bề mặt.

Phương án mạnh hơn cho tài khoản quản trị là một **hardware-backed WebAuthn credential** (khóa không export, user verification phù hợp) hoặc một thiết bị được quản lý với boundary rõ ràng. Không phải mọi passkey đều device-bound: **synced passkeys** có cách backup/đồng bộ khác nhau; cần kiểm tra yêu cầu assurance và chính sách doanh nghiệp.

### 4.3. Độc lập về **kênh truyền và session**

Một OTP SMS được hiển thị trong notification của cùng điện thoại đã bị chiếm không độc lập với session do attacker điều khiển. Một website giả có thể hỏi password và OTP, rồi chuyển cả hai real-time cho website thật (adversary-in-the-middle). OTP nhập tay có thể là MFA nhưng **không phishing-resistant**.

FIDO2/WebAuthn đúng chuẩn ràng buộc phản hồi xác thực với **origin và RP ID**, giúp chống đưa assertion của domain thật sang domain giả. Cần xác minh challenge, RP ID hash, origin, chữ ký, user presence/user verification flags theo policy. Không tự coi các phép kiểm tra đó là optional.

### 4.4. Độc lập về **account recovery**

Một hệ thống yêu cầu password + security key khi đăng nhập, nhưng hỗ trợ “Tôi mất khóa” chỉ bằng cách trả lời một câu hỏi bảo mật hoặc nhận email link tới mailbox dùng chung password — attacker có thể đi đường vòng. MFA bị suy yếu bởi **luồng reset, thay thiết bị, thêm yếu tố và helpdesk**. Đây là một trong những điểm dễ bị bỏ qua nhất khi kiểm thử.

### 4.5. Độc lập về **danh tính**

Hai bằng chứng thuộc hai người khác nhau không tạo MFA cho một user. Ví dụ password của `lan` nhưng OTP seed thuộc `minh`. Server phải đối chiếu **cùng local account ID**, đúng authenticator đã đăng ký cho account, đúng challenge/session và thời điểm.

## 5. Xếp hạng phương thức theo nguy cơ cụ thể

| Phương thức | Lợi ích | Nguy cơ giới hạn | Lựa chọn thường hợp lý |
|---|---|---|---|
| Password + WebAuthn security key | Hai loại factor, origin binding/phishing resistance | Mất khóa, khâu enrollment/recovery, thiết bị không hỗ trợ | Quản trị viên, thao tác có tác động cao |
| Multi-factor passkey với user verification | Trải nghiệm thuận tiện, cryptographic, origin bound | Đồng bộ/khôi phục passkey, mức bảo đảm thiết bị, kiểm tra UV | Passwordless có policy rõ ràng |
| Password + app TOTP | Triển khai phổ biến, offline sau enrollment | OTP relay phishing, seed bị sao chép, replay, time drift | Chọn khi chưa thể triển khai WebAuthn |
| Password + push app có number matching | Thuận tiện và có thể ràng buộc phiên | MFA fatigue, phone malware, push proxy | Có rate limits và xác nhận giao dịch |
| Password + SMS OTP | Khả dụng với nhiều người dùng | SIM swap, intercept, roaming, phishing; PSTN OOB restricted | Fallback có risk assessment, không làm yếu đường chính |
| Password + email OTP | Thao tác đơn giản | Mailbox có thể dùng cùng password, bị forward, account recovery yếu; NIST không công nhận email OOB | Không coi là phương thức MFA đáp ứng chuẩn NIST; thường dùng cho email verification/recovery theo policy |
| Password + password thứ hai | Dễ giải thích cho UI | Không phải MFA, cùng nhóm knowledge | Không dùng để đáp ứng yêu cầu MFA |
| Password + device cookie | Có thể giúp nhận diện thiết bị quen | Cookie có thể bị copy, không chứng minh possession độc lập | Chỉ là risk signal, không thay bằng chứng thiết bị |

**Không suy diễn AAL chỉ từ số yếu tố.** NIST SP 800-63B-4 còn quy định loại authenticator, sự bảo vệ secret, replay resistance, reauthentication, phishing resistance và các yêu cầu vận hành. Một website có hai ô OTP không tự đạt AAL2. Đặc biệt, email **bị cấm làm out-of-band authentication theo NIST 800-63B-4**, dù trong tài liệu triển khai ứng dụng một email code đôi khi được trình bày như bước hai; phải phân biệt UX với tuân thủ chuẩn.

## 6. Mô hình trạng thái: đừng cấp toàn quyền khi chỉ xong bước một

Một luồng web thường có các trạng thái:

```text
ANONYMOUS
    │ verify password
    ▼
PRIMARY_VERIFIED / MFA_PENDING
    │ temporary server-side challenge (short TTL)
    │ ├─ wrong OTP / replay / timeout → deny, throttling
    │ └─ verify registered second authenticator, same user
    ▼
MFA_COMPLETE
    │ rotate session ID / issue final Authentication
    │ authorization still checks roles and resources
    ▼
ACCESS_TO_ALLOWED_ENDPOINTS
```

**MFA_PENDING không được coi là đã hoàn tất MFA.** Có hai mô hình hợp lệ nhưng phải rõ ràng:

1. **Chưa tạo full SecurityContext:** Sau password, lưu một server-side challenge có TTL và một session trung gian bị giới hạn; chỉ khi step two thành công mới tạo Authentication đầy đủ và chuyển phiên. Phù hợp khi tất cả endpoint cần MFA.
2. **Cho phép phiên đã xác thực bước một với quyền giới hạn:** Ứng dụng đã có Spring `Authentication` từ password, nhưng các endpoint nhạy cảm yêu cầu một điều kiện **MFA-complete** khác. Có thể phục vụ trang cơ bản, song tuyệt đối không mở `/admin/**` chỉ với `authenticated()`.

Đừng tạo `ROLE_ADMIN` hoặc copy toàn bộ authorities vào một “partial principal” rồi dùng sai rules. Khi MFA hoàn tất, **authorization còn phải kiểm tra role/tenant/ownership** tại endpoint.

### 6.1. Dữ liệu challenge nên chứa gì?

Một bản ghi server-side ví dụ:

```text
challenge_id       = random, unguessable
local_user_id      = immutable ID (not email)
session_binding    = server-generated session reference
primary_verified_at= ...
expected_method_id = authenticator already bound to user
purpose            = "LOGIN_MFA" / "STEP_UP_PAYMENT"
expires_at         = short, enforced on server
attempts_left      = bounded
consumed_at        = null until success
risk_context       = policy-derived, not client-supplied
```

Session/challenge ID cũng phải được bảo vệ khỏi session fixation. Không lấy `userId` từ request body để chuyển sang người khác, không có query `?mfaPassed=true`, không chấp nhận OTP của authenticator chưa hề đăng ký. Nếu dùng Redis/DB trên nhiều node, cập nhật `consumed_at` hoặc trạng thái success **nguyên tử** để tránh hai request cùng tiêu thụ challenge.

### 6.2. Những điều phải xác minh ở bước hai

1. Challenge có tồn tại, còn hạn, chưa dùng và thuộc **cùng user/same purpose** được xác thực ở bước một.
2. Authenticator tương ứng đã được đăng ký cho user đó, chưa bị thu hồi.
3. Bằng chứng được **verifier** kiểm tra thực sự: TOTP/HOTP secret, chữ ký WebAuthn hoặc kết quả IDP `acr/amr` đã được xác minh; không tin dữ liệu tự báo từ client.
4. Giới hạn đoán mã, retry theo user/challenge/IP và signal rủi ro. Mã sáu số cần chống brute force.
5. Replay bị chặn. Với TOTP, không chấp nhận cùng một mã/step lại lần thứ hai trong thời gian mã còn hiệu lực; thực thi theo cách atomic trên nhiều node.
6. Giữ đúng thứ tự: chỉ sau thành công mới cấp `mfa_complete` và lưu Authentication/session phù hợp; tạo audit event.
7. Nếu thất bại/timeout/đăng xuất/đổi account, challenge cũ bị thu hồi. Không chuyển trạng thái từ MFA_PENDING sang MFA_COMPLETE bằng một đường error/fallback.

Không **đặt tên** một custom header `X-MFA-Verified: true` rồi tin nó từ browser. Nếu có upstream IdP/gateway bảo đảm MFA, cần thiết lập ranh giới tin cậy riêng và chống header spoofing, kiểm tra chữ ký/chính sách và liên hệ với subject hiện tại.

## 7. TOTP: ví dụ một yếu tố sở hữu có thể bị phishing

TOTP (RFC 6238) tạo mã thời gian dựa trên một **secret đã đăng ký** và time step (thường khoảng 30 giây). Client authenticator và server cùng biết secret, tính HMAC rồi rút gọn thành OTP số. Server phải bảo vệ seed, cho phép sai lệch đồng hồ nhỏ theo policy, giới hạn retry, chống replay và kiểm tra user binding.

```text
Password được xác minh ở server → điều KNOWLEDGE
TOTP app có secret đã đăng ký  → bằng chứng POSSESSION
Hai kết quả cùng thuộc local_user_id = 42
                       │
               MFA policy có thể đạt
```

Nhưng mã TOTP **không được ràng buộc với origin web**. Một phishing site có thể thu password và mã `123456`, rồi gửi chúng tới trang thật ngay khi mã còn hạn. Vì vậy **Password + TOTP có thể là MFA nhưng không mặc nhiên phishing-resistant**.

Không làm các việc sau:

- Lưu seed TOTP cùng password plaintext, gửi seed về client sau khi enrollment, hoặc ghi QR enrollment vào log.
- Chấp nhận cùng OTP đã dùng trong time step còn hiệu lực để đăng nhập nhiều lần.
- Tăng cửa sổ time drift quá rộng để “đỡ phiền”.
- Cho khách hàng đổi số điện thoại/TOTP secret chỉ bằng chính mã được gửi tới thiết bị đang bị nghi mất quyền kiểm soát.
- Xem việc user nhập đúng một OTP sáu số là đủ để đổi quyền admin/tenant nếu transaction yêu cầu bằng chứng và consent mạnh hơn.

Với một authenticator TOTP đã bị xâm nhập seed, vòng đời bảo mật là **thu hồi binding và đăng ký lại**, không chỉ đổi password.

### 7.1. SMS, email và hai điểm nhạy cảm

NIST SP 800-63B-4 xếp **PSTN out-of-band** (SMS/voice) vào nhóm **restricted authenticator**, vì rủi ro chuyển số SIM, port-out, mạng viễn thông, tấn công social engineering; tổ chức cần risk assessment và lựa chọn không hạn chế khi cần.

NIST SP 800-63B-4 quy định **email không được dùng làm out-of-band authenticator**, bởi mailbox có thể chỉ được mở bằng password, có nguy cơ interception và chuyển hướng. Email **vẫn có vai trò** trong xác minh địa chỉ, thông báo sự kiện tài khoản và một số quy trình recovery; không đồng nghĩa hợp lệ như yếu tố MFA cần bảo đảm cao.

Điều này giải thích vì sao **password + email OTP** tuy nhìn giống hai bước, không nên mặc nhiên được quảng bá là hai yếu tố mạnh và không đáp ứng yêu cầu email-OOB của NIST. Nếu Spring Security hỗ trợ password + email-delivered OTT, đó là năng lực **quy trình**, không tự chứng nhận tính độc lập hay AAL.

## 8. FIDO2/WebAuthn, passkeys và phishing resistance

WebAuthn/FIDO2 sử dụng **public-key cryptography**: authenticator giữ private key, server lưu public key/credential ID và xác minh một assertion có chữ ký trên challenge. Thông tin origin và RP ID được kiểm tra để ngăn kẻ tấn công dùng một website giả lấy bằng chứng dùng được ở website thật.

Các bước ở mức khái niệm:

```text
Server phát random challenge cho account/chính phiên
     ↓
Browser gọi WebAuthn API cho RP ID chính xác
     ↓
Authenticator xác minh user presence và/hoặc user verification
     ↓
Private key ký dữ liệu có challenge + authenticator data
     ↓
Server verify signature, challenge, origin, rpIdHash,
        flags UP/UV (đúng policy), credential ownership
     ↓
Server hoàn tất factor, áp dụng authorization và session policy
```

**UP** (user presence) và **UV** (user verification) không phải cùng một điều. Một passkey/authenticator có thể được dùng khi chỉ có UP; khi cần assurance kiểu multi-factor cryptographic authenticator, chính sách phải yêu cầu UV phù hợp. Browser **không** gửi vân tay nguyên bản đến Spring backend trong flow WebAuthn chuẩn.

**Synced passkeys** thường cải thiện UX, nhưng cần hiểu cơ chế backup, đồng bộ và khôi phục khi đánh giá yêu cầu doanh nghiệp. Không tự nói “mọi passkey đều hardware-bound”, cũng không gọi mọi assertion WebAuthn là hai yếu tố mà chưa xem UV và authenticator policy.

Phần lớn các hệ thống có thể chọn passkeys/WebAuthn phishing-resistant làm hướng mặc định, rồi dùng TOTP hoặc phương thức khác làm fallback có rủi ro được chấp nhận. Bảo vệ enrollment, recovery và backup keys quan trọng không kém việc verify chữ ký lúc login.

## 9. Spring Security 7.x: MFA tích hợp qua FactorGrantedAuthority

**Chú ý phiên bản:** `FactorGrantedAuthority` xuất hiện từ **Spring Security 7.0**, không phải API chung cho mọi bản 6.x. Ví dụ này dành cho Spring Security 7.x (thường là Spring Boot 4.x), Servlet. Không copy vào dự án Spring Boot 3.x/Spring Security 6.x và mong lớp import tồn tại.

### 9.1. Mô hình authority biểu thị phương thức xác thực

Tài liệu Spring Security 7 nêu các authorities như:

- `FactorGrantedAuthority.PASSWORD_AUTHORITY` → tên string `FACTOR_PASSWORD`.
- `FactorGrantedAuthority.OTT_AUTHORITY` → `FACTOR_OTT` (one-time-token mechanism).
- `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` → `FACTOR_WEBAUTHN`.
- `FactorGrantedAuthority.X509_AUTHORITY` → `FACTOR_X509`.

Framework chỉ biết **cơ chế nào vừa được thực hiện** theo các authentication flows. Việc có hai authorities trong `Authentication` chưa đủ chứng minh chúng thật sự độc lập trước threat model. Ví dụ `FACTOR_OTT` qua email có giới hạn an toàn như mục 7.1. **Không cho client tự đặt bất kỳ `FACTOR_*`** trong headers, JWT claims không được xác minh hoặc request body.

### 9.2. Ví dụ cấu hình toàn ứng dụng cần password + OTT

Các thành phần sau minh họa **cơ chế tích hợp của Spring Security 7.x**:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

**Điều kiện để ứng dụng hoàn chỉnh:** ngoài class trên, Spring Boot phải có `UserDetailsService` / credential store phù hợp, trang login hoặc UI mặc định, `OneTimeTokenService` dùng shared store khi nhiều node, **`OneTimeTokenGenerationSuccessHandler`** để thực sự gửi token qua một kênh có chính sách an toàn, và các routes cần bảo vệ. Một config 25 dòng **không tự cấu hình mail, factor registration hoặc compliance**.

Ví dụ dùng password + OTT để minh họa **API của Spring**. Nó **không khẳng định** password + OTT qua email đạt yêu cầu MFA của NIST. Đối với hệ thống yêu cầu phishing-resistant MFA, nên chọn WebAuthn đã đăng ký đúng, hoặc phương thức đáp ứng assurance mục tiêu; khi chuyển từ OTT sang WebAuthn cần cấu hình credential repositories, relying-party/origin và authenticator lifecycle.

Framework áp dụng kiểm tra factor authorities vào authorization rules: một người có `ROLE_ADMIN` nhưng chưa có cả `FACTOR_PASSWORD` và `FACTOR_OTT` không được đi vào `/admin/**` theo chính sách toàn cục trên. Cách framework dẫn người dùng tới cơ chế còn thiếu không thay thế kiểm tra quyền; cần test từng tuyến và tùy chỉnh UX.

### 9.3. Khi chỉ một số endpoint cần MFA

Không phải ứng dụng nào cũng yêu cầu cả hai yếu tố ở mọi trang. Spring Security 7 hỗ trợ tạo `AuthorizationManagerFactory` với yêu cầu factor tùy tuyến và thời gian. Ví dụ lấy từ mẫu API chính thức (đặt trong class cấu hình phù hợp):

```java
var mfa = AuthorizationManagerFactories.multiFactor()
    .requireFactors(
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY)
    .build();

http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
    .requestMatchers("/account/security/**").access(mfa.authenticated())
    .anyRequest().authenticated());
```

Đoạn này là **snippet** trong một `SecurityFilterChain`, không phải file Java độc lập. Cần import `org.springframework.security.config.annotation.authorization.AuthorizationManagerFactories` cùng `FactorGrantedAuthority`; cấu hình hỗ trợ MFA theo documentation (ví dụ `@EnableMultiFactorAuthentication(authorities = {})`) và đủ cơ chế login cho các factor. Đừng vừa áp dụng global MFA requirement vừa kỳ vọng `/public` bỏ qua factor nếu rule đã bị tăng yêu cầu trên toàn cục.

**Quy tắc UX:** `/admin/**` cần `ROLE_ADMIN` **và** đúng các factor được yêu cầu; `/account/security/**` cần auth và MFA; các trang thường có thể cần xác thực cơ bản. Dù đã pass MFA, tài nguyên nhạy cảm vẫn cần kiểm tra role, owner, tenant và các permission hiện hành.

### 9.4. Tính mới của từng factor và step-up

Spring Security 7 có timestamp gắn với `FactorGrantedAuthority` (`getIssuedAt()`), và tài liệu chính thức mô tả các authorization rules yêu cầu factor phải còn **mới** (fresh). Một password được nhập lúc 08:00 không nên tự đủ cho thao tác chuyển tiền lúc 17:00, ngay cả khi session vẫn sống.

Không tự viết một authority name `FACTOR_PASSWORD` cứng trong database rồi coi đó là bằng chứng đã xác thực lại. Cần authority do cơ chế xác thực đúng sinh ra, theo session, từ verifier tin cậy, với thời gian và chính sách phù hợp.

## 10. Spring Security 6.x / Spring Boot 3.x: thiết kế MFA gate đúng

Trong hệ thống đang dùng Spring Security **6.x**, không dựa vào `@EnableMultiFactorAuthentication` của 7.x. Bạn có thể tích hợp một Identity Provider hỗ trợ MFA và áp dụng assurance policy cho phiên đăng nhập, hoặc thiết kế luồng **password → pending challenge → verify TOTP/WebAuthn → MFA complete** bằng các components của Spring Security.

### 10.1. Hai cách tích hợp

**Cách A — Upstream IdP/SSO thực hiện MFA:**

```text
Ứng dụng → OIDC Login → IdP
      IdP xác minh password + WebAuthn/TOTP theo chính sách
        ↓
OIDC ID Token được xác minh theo issuer/audience/nonce/time
        ↓
Ứng dụng kiểm tra acr/amr/auth_time theo hợp đồng issuer
        ↓
Ứng dụng thiết lập local session với assurance phù hợp
        ↓
Authorization cho endpoint nhạy cảm
```

`amr` (Authentication Methods References) và `acr` (Authentication Context Class Reference) không phải những string mang giá trị bảo đảm phổ quát cho mọi nhà cung cấp. Ứng dụng phải **xác minh token từ IdP tin cậy**, hiểu chính xác `acr`/`amr` provider hứa gì, và kiểm tra `auth_time`/max-age khi cần step-up. Không tin một `amr=["mfa"]` tự khai từ browser hoặc email domain. Không đồng nhất `email_verified` với MFA.

**Cách B — Local application thực hiện bước hai:**

- `AuthenticationManager`/provider kiểm chứng password hoặc yếu tố đầu tiên.
- Server tạo pending challenge cho **cùng user** (hoặc session đã xác thực sơ cấp có quyền giới hạn).
- Endpoint `POST /mfa/verify` thực hiện verify yếu tố thứ hai với secret/public key đã đăng ký, TTL, replay/attempt controls.
- Chỉ sau khi thành công mới phát trạng thái `mfaComplete` / security context có độ bảo đảm phù hợp.
- `AuthorizationManager` / method security áp dụng chính sách “cần MFA còn mới” với `/admin/**` hoặc giao dịch tài chính.
- Khi user logout, đổi account, bị khóa hoặc bị gỡ factor, cần thu hồi challenge/session theo policy.

**Không bật `permitAll()` cho API nhạy cảm chỉ để trang step-two truy cập được.** Chỉ endpoints cần thiết cho login/verification và tài nguyên tĩnh được phép truy cập trong trạng thái pending; mọi đường còn lại phải bị chặn đúng.

### 10.2. Ví dụ authorization gate của Spring Security 6.x

Đoạn này minh họa phần **chặn route nhạy cảm**, không làm nhiệm vụ verify OTP. `MfaProofService` bên dưới là thành phần nghiệp vụ **do ứng dụng phải tự cài đặt** và ràng buộc trạng thái với user/session/phương thức đã được server xác minh.

```java
package com.example.security;

import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
class MfaGateConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            MfaProofService mfaProofs) throws Exception {

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(
                (Supplier<Authentication> getAuth,
                 RequestAuthorizationContext context) -> {
                    Authentication current = getAuth.get();
                    boolean allowed = current != null
                        && current.isAuthenticated()
                        && !(current instanceof AnonymousAuthenticationToken)
                        && current.getAuthorities().stream().anyMatch(
                            a -> "ROLE_ADMIN".equals(a.getAuthority()))
                        && mfaProofs.isFreshAndIndependent(
                            current.getName(),
                            context.getRequest());
                    return new AuthorizationDecision(allowed);
                })
            .anyRequest().authenticated());

        return http.build();
    }
}
```

Interface cho service của ứng dụng:

```java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

public interface MfaProofService {
    // Chỉ trả true khi server đã verify đủ factor đúng tài khoản,
    // còn mới, và đã gắn bằng chứng với session hiện tại.
    boolean isFreshAndIndependent(
        String authenticatedLocalUsername,
        HttpServletRequest request);
}
```

**Đọc ví dụ đúng phạm vi:** Cấu hình trên là một phần của dự án Spring Boot 3/Spring Security 6 có các authentication mechanisms khác và một bean triển khai `MfaProofService`. Nó không tự tạo login page, password verifier, TOTP store hoặc WebAuthn provider. Nếu không có implementation của service, ví dụ chưa chạy như một ứng dụng hoàn chỉnh. Không copy nguyên config để thay thế toàn bộ security chain hiện có mà bỏ các rules khác.

Tránh cài đặt `isFreshAndIndependent(...)` như:

```java
// SAI: client tự chứng nhận hoàn thành MFA
return "true".equals(request.getHeader("X-MFA-Completed"));
```

Đúng phải tra trạng thái **được server lưu/trusted upstream xác minh** với khóa phiên/user, kiểm tra freshness và những phương thức thật sự đã xác thực; trong môi trường nhiều node cần shared store hoặc session replication/đúng session binding. Ngoài ra, nếu dùng cookie session, không quên CSRF và session fixation protections.

### 10.3. Phân biệt authenticated, MFA-complete và quyền nghiệp vụ

Trong mô hình Spring Security 6.x cho phép primary login, request tới `/profile` có thể được phục vụ khi `authenticated()` thành công. Nhưng `/admin/**` phải qua gate `isFreshAndIndependent` và role check. Nếu hệ thống quy định **mọi resource** đều yêu cầu MFA, thiết kế filter/authorization tương ứng để không có route đi tắt.

Cẩn thận với các **URL variants** (`/admin`, `/admin/`, encoded path, forward/include, handler mapping) và method security. Chỉ bảo vệ `/admin/**` mà quên `/admin` hoặc endpoint phụ cùng quyền có thể tạo bypass. Với truy cập dữ liệu nhạy cảm, ưu tiên áp dụng policy ở tầng service hoặc domain authorization để bảo vệ cả các lời gọi không đi qua một URL cụ thể.

## 11. Java 17 độc lập: kiểm tra các yếu tố có độc lập và còn mới không

Chương trình này minh họa **mô hình quyết định** sau khi các bằng chứng đã được server xác minh. Đây không phải verifier mật khẩu, TOTP hoặc chữ ký thật; chỉ cho thấy cách loại bỏ bằng chứng sai user, quá cũ, chưa được verifier xác thực, và hai lần xác thực cùng một loại.

Lưu file `MfaIndependenceDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.EnumSet;
import java.util.List;

public class MfaIndependenceDemo {

    enum Factor { KNOWLEDGE, POSSESSION, INHERENCE }

    record Evidence(
        String userId,
        Factor factor,
        Instant verifiedAt,
        boolean serverVerified
    ) {}

    static boolean hasFreshMfa(
            String expectedUser,
            Instant now,
            List<Evidence> evidence) {

        EnumSet<Factor> distinct = EnumSet.noneOf(Factor.class);
        for (Evidence proof : evidence) {
            if (!proof.serverVerified()) {
                continue;
            }
            if (!expectedUser.equals(proof.userId())) {
                continue;
            }
            if (proof.verifiedAt().isAfter(now)
                    || proof.verifiedAt().isBefore(
                        now.minus(Duration.ofMinutes(5)))) {
                continue;
            }
            distinct.add(proof.factor());
        }
        return distinct.size() >= 2;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-01-01T12:00:00Z");

        Evidence password = new Evidence(
            "user-42", Factor.KNOWLEDGE, now, true);
        Evidence pin = new Evidence(
            "user-42", Factor.KNOWLEDGE, now, true);
        Evidence totp = new Evidence(
            "user-42", Factor.POSSESSION, now, true);
        Evidence staleTotp = new Evidence(
            "user-42", Factor.POSSESSION,
            now.minus(Duration.ofMinutes(10)), true);
        Evidence otherUsersTotp = new Evidence(
            "user-99", Factor.POSSESSION, now, true);
        Evidence unverifiedTotp = new Evidence(
            "user-42", Factor.POSSESSION, now, false);

        System.out.println("Password + PIN: " +
            hasFreshMfa("user-42", now, List.of(password, pin)));
        System.out.println("Password + TOTP: " +
            hasFreshMfa("user-42", now, List.of(password, totp)));
        System.out.println("Stale TOTP: " +
            hasFreshMfa("user-42", now, List.of(password, staleTotp)));
        System.out.println("Different user: " +
            hasFreshMfa("user-42", now, List.of(password, otherUsersTotp)));
        System.out.println("Unverified proof: " +
            hasFreshMfa("user-42", now, List.of(password, unverifiedTotp)));
    }
}
```

Biên dịch/chạy (JDK 17+):

```bash
javac MfaIndependenceDemo.java
java MfaIndependenceDemo
```

Stdout chính xác:

```text
Password + PIN: false
Password + TOTP: true
Stale TOTP: false
Different user: false
Unverified proof: false
```

**Giải thích và giới hạn quan trọng:**

- `EnumSet` loại bỏ trùng loại factor, vì thế password + PIN không đạt. Code không đếm số lần gõ.
- `serverVerified` trong demo chỉ là giả định **đã kiểm tra ngoài hàm này**. Ở production, tuyệt đối không nhận boolean này từ client rồi đặt `true`.
- Tất cả bằng chứng phải thuộc đúng `expectedUser` và được xác minh trong khoảng năm phút (con số **minh họa** chính sách step-up, không phải TTL tiêu chuẩn của NIST).
- Mô hình không đủ để đánh giá **độ độc lập kỹ thuật** giữa password manager và authenticator TOTP trên cùng thiết bị; cần review enroll/recovery, secret storage, phishing và authenticator provenance riêng.
- Không dùng `EnumSet.size()>=2` thay cho một verifier/authorization service production; không có database, cryptographic authentication, session binding, replay protection hoặc role check trong demo.

## 12. Step-up authentication: MFA theo hành động và độ mới

MFA có thể yêu cầu khi login, hoặc chỉ **step-up** trước hành động rủi ro cao. Ví dụ:

- Xem báo cáo công khai trong ứng dụng: authenticated session cơ bản đủ theo chính sách.
- Xem dữ liệu lương, thay đổi quyền, xuất toàn bộ dữ liệu: yêu cầu MFA.
- Chuyển tiền, thêm phương thức thanh toán, đổi email khôi phục, đăng ký security key: yêu cầu **MFA mới được xác minh gần đây**, và có thể yêu cầu confirmation ràng buộc với giao dịch.

Dù session đã từng hoàn tất MFA sáng nay, hành động lúc tối có thể cần xác thực lại. Ví dụ chính sách “factor gần nhất trong vòng 5 phút” phải dùng timestamp từ **kết quả verifier**, không dùng thời gian client tự gửi. Khi request có nguy cơ cao, có thể yêu cầu **transaction binding** (số tiền/đích giao dịch hiển thị và xác nhận), không chỉ “nhập OTP bất kỳ”.

Với ứng dụng sử dụng OIDC IdP, có thể yêu cầu `max_age` hoặc `acr_values` theo hợp đồng provider và kiểm tra `auth_time`/`acr`/`amr` trong ID Token đã xác minh để thực hiện step-up. Cần kiểm tra IdP có thực sự tuân thủ request, claim mapping có ý nghĩa gì và có xác thực lại hay chỉ tái sử dụng session cũ. Không coi sự hiện diện của claim là bảo đảm chung cho mọi issuer.

### Session lifecycle

- Sau khi hoàn tất MFA, thay đổi session ID theo policy để chống session fixation.
- Session logout, khóa account, thu hồi authenticator hoặc password reset có thể yêu cầu vô hiệu hóa trạng thái MFA cũ.
- Nếu có nhiều tab hoặc thiết bị, trạng thái MFA phải ràng buộc đúng session/account và không bị mượn của người khác.
- Nếu thay đổi user giữa bước một và hai, phải hủy challenge cũ.
- Với stateless JWT, không tự bổ sung `mfa=true` phía frontend. Nếu IdP/AS phát token có mức assurance, Resource Server phải xác minh chữ ký, issuer, audience, hạn dùng, chính sách freshness và các quyền nghiệp vụ; rủi ro claim cũ còn sống tới `exp` cần được giải quyết.

## 13. Đăng ký, thay đổi, mất thiết bị và recovery

Một hệ thống login MFA mạnh nhưng cho **thêm/yêu cầu reset yếu tố** chỉ bằng email chưa bảo vệ có thể vẫn bị account takeover.

### 13.1. Enrollment

1. User đã đăng nhập bằng bằng chứng đủ mạnh; để thêm security key hay TOTP, yêu cầu reauthentication/step-up tùy mức rủi ro.
2. Server tạo enrollment challenge/secret riêng, **chưa có hiệu lực** trước khi chứng minh authenticator mới đã được kiểm soát.
3. Với TOTP: hiển thị QR một lần qua HTTPS, kiểm tra mã đầu tiên, bảo vệ seed, lưu secret encrypted và giới hạn exposure.
4. Với WebAuthn: verify registration challenge, origin, RP ID, credential ID, attestation/UV nếu chính sách cần. Public key mới phải gắn đúng user hiện tại.
5. Audit và thông báo về kênh đã đăng ký trước khi thay đổi; không để thêm factor mới tự động nâng quyền hay né step-up đang cần.

### 13.2. Đổi và gỡ factor

- Yêu cầu local authenticated session có bảo đảm đủ, reauthentication với một yếu tố còn tin cậy hoặc quy trình recovery có kiểm soát.
- Không cho người nắm session đánh cắp tự thay email/số điện thoại rồi gửi OTP về đó để vượt yếu tố thứ hai.
- Khi gỡ authenticator, thu hồi challenge và session/trạng thái liên quan theo policy; thông báo độc lập tới chủ tài khoản.
- Nếu gỡ yếu tố cuối cùng làm tài khoản mất cách đăng nhập, phải chuẩn bị phương thức thay thế hoặc recovery được kiểm soát.

### 13.3. Recovery

Cân nhắc **backup codes** CSPRNG được hiển thị một lần, lưu hash, giới hạn số lượng/attempt và tiêu thụ nguyên tử, cùng với **khóa bảo mật dự phòng**. Helpdesk recovery cho tài khoản quản trị cần quy trình xác minh chặt, dual control nếu phù hợp và audit.

**Không coi việc trả lời câu hỏi bảo mật đơn giản hay kiểm soát một mailbox yếu là MFA**. Recovery có thể là ngoại lệ nghiệp vụ, nhưng phải được thiết kế theo rủi ro, thông báo sau thay đổi, giảm quyền tạm thời hoặc trì hoãn tác vụ nhạy cảm nếu cần.

## 14. Các kiểu tấn công và cách kiểm soát

| Tấn công | Kịch bản | Biện pháp chính |
|---|---|---|
| Credential stuffing | Password bị lộ ở dịch vụ khác | MFA độc lập, rate limit, cảnh báo, password policies |
| Real-time phishing / AiTM | Site giả lấy password rồi chuyển TOTP tới site thật | WebAuthn/FIDO2 origin binding; anti-phishing, session protection |
| OTP brute force | Đoán mã 6 số qua API | Throttle theo user/challenge/IP, TTL ngắn, lock/retry policy |
| OTP replay | Dùng lại mã trong time step | Lưu timestep/consumed state, cập nhật atomic, từ chối replay |
| SIM swap | Attacker chuyển số điện thoại | Tránh SMS cho rủi ro cao, risk signals, delay/notification khi đổi số |
| Push fatigue | Attacker gửi rất nhiều push approvals | Number matching, hiển thị ngữ cảnh, rate limit, cấm auto approve |
| Phishing MFA backup code | Lừa user nhập recovery code | Cảnh báo, mã dùng một lần, recovery flows an toàn, WebAuthn |
| Factor enrollment hijack | Attacker đã có password tự thêm authenticator | Bắt buộc step-up/reauth trước enrollment |
| Session theft | Đánh cắp cookie sau khi MFA hoàn tất | Secure/HttpOnly/SameSite, TLS, session binding, expiry, monitoring |
| OAuth/OIDC assurance spoof | Backend tin claim MFA do client đưa vào | Verify token/signature/issuer/audience/acr-amr policy |
| “Two password” bypass | UI có hai bước nhưng cùng knowledge | Đánh giá loại factor độc lập, không đếm form |
| Fallback downgrade | App cho “bỏ qua MFA” khi dịch vụ OTP lỗi | Fail closed ở route nhạy cảm; recovery được kiểm soát riêng |
| Wrong-account factor | OTP của user B hoàn tất session user A | Challenge bind user ID/authenticator/session và atomic consume |

**MFA không phải lớp bảo vệ duy nhất:** XSS có thể lấy session, malware có thể điều khiển thiết bị, tấn công phishing nâng cao có thể lấy session cookie sau khi MFA hợp lệ. Vẫn cần hạn chế quyền, CSP, cookie/session security, authorization, giám sát bất thường và các biện pháp giảm thiểu chiếm đoạt phiên.

## 15. Ma trận kiểm thử ứng dụng

### 15.1. Định nghĩa và sự độc lập

| Test | Trạng thái mô phỏng | Kỳ vọng |
|---|---|---|
| Password thành công | Chỉ yếu tố knowledge được xác minh | Không vào route yêu cầu MFA |
| Password + PIN | Hai bước nhưng hai yếu tố knowledge | **Không đạt MFA** |
| Password + security question | Cùng knowledge, dù câu trả lời đúng | Không đạt |
| Password + TOTP hợp lệ, cùng user | Knowledge + possession đã xác minh | Đạt theo chính sách OTP, nhưng không gọi là phishing-resistant |
| Password + TOTP user khác | OTP thuộc authenticator khác owner | Từ chối |
| Password + mã TOTP chưa từng được đăng ký | Dù mã hợp lệ ở client giả | Từ chối |
| Password + email OTP | Quy trình hai bước nhưng kênh mail yếu | Không quảng bá là phương pháp đáp ứng NIST email-OOB |
| Password + IP doanh nghiệp | IP là risk signal | Không nâng thành MFA |
| Password + WebAuthn đúng challenge/origin/UV | Hai yếu tố đủ theo policy | Đạt trong phạm vi assurance đã thiết kế |
| WebAuthn sai RP ID/origin/chữ ký | Không phải assertion hợp lệ | Từ chối |
| WebAuthn chỉ UP khi policy yêu cầu UV | Chưa đạt verification yêu cầu | Từ chối |

### 15.2. Trạng thái, replay và tài khoản

- Password thành công nhưng chưa làm bước hai → `/admin`, `/payment` hoặc API nhạy cảm vẫn bị chặn; không có bearer JWT mang quyền MFA từ frontend.
- Hoàn tất factor thứ hai đúng **user khác** hoặc **session khác** → phải từ chối; không dùng lại challenge.
- OTP sai nhiều lần → giảm `attempts_left`, throttle/lock challenge theo chính sách, không leak rằng account đã tồn tại.
- Dùng lại cùng OTP trong cửa sổ thời gian hợp lệ → từ chối replay; test trên **hai server nodes** cùng lúc.
- Challenge hết hạn hoặc đã consumed → không thành công, dù code TOTP sau đó đúng.
- Sau MFA thành công: chỉ đúng owner, roles/permissions hiện tại được cấp; session fixation protection được kích hoạt.
- Bước MFA bị hủy giữa chừng, user logout hoặc login sang account khác → trạng thái pending cũ bị thu hồi.
- Gỡ authenticator/khóa account/thu hồi session → trạng thái MFA cũ không được cấp quyền ngoài policy.
- Session chỉ có một factor nhưng code authorization dùng `authenticated()` → test phải phát hiện bypass.
- Factor từ request header `X-MFA=true`, query `?mfa=1`, JWT chưa xác minh → phải bị từ chối.
- Factor được verify từ phiên 6 giờ trước nhưng endpoint yêu cầu freshness 5 phút → yêu cầu step-up.

### 15.3. Recovery và downgrade

- Attacker nắm password nhưng không có authenticator: thử chức năng “đổi phone”, “tắt MFA”, “reset MFA” → không qua được chỉ với password.
- Helpdesk/admin recovery: có audit, notifications, dual control hoặc workflow phù hợp rủi ro; không có đường `skipMfa` public.
- Service TOTP/WebAuthn mất kết nối: route nhạy cảm **không fail open**; phục hồi qua phương án chính thức.
- Backup code chỉ dùng một lần và không dễ đoán; cùng mã không được dùng hai lần đồng thời.
- Không tự hạ từ passkey/WebAuthn sang SMS/email cho account nhạy cảm mà không có chính sách/step-up tương ứng.

## 16. Checklist đưa MFA vào sản xuất

1. **Xác định threat model**: tài sản bảo vệ, loại người dùng, phishing/session compromise, yêu cầu assurance và độ nhạy giao dịch.
2. **Phân biệt 2SV/2FA**: không đếm bước, không tính password+PIN hoặc password+CAPTCHA thành MFA.
3. **Chọn authenticators đúng yêu cầu**: ưu tiên phishing-resistant WebAuthn cho tài khoản nhạy cảm; TOTP nếu chấp nhận rủi ro phishing; thận trọng SMS, không dùng email OOB như NIST-compliant MFA.
4. **Kiểm tra nguồn bằng chứng**: verifier chứng minh authenticator đã đăng ký cho **cùng user**, còn hiệu lực, không bị thu hồi.
5. **Bảo vệ từng giai đoạn**: pending state với TTL/attempt limit, session binding, CSRF, atomic consume; không cấp privilege trước khi hoàn tất.
6. **Không dựa vào client flags**: chỉ có server-side proof hoặc signed/trusted upstream claims được verify theo policy; không cho client tự đặt factor authorities.
7. **Authorization theo quyền và độ mới**: step-up cho admin/payment/security settings, kiểm tra roles/tenant/ownership riêng.
8. **Đăng ký và recovery chặt chẽ**: bảo vệ thêm/gỡ/reset factor như tác vụ nhạy cảm; thông báo và audit.
9. **Bảo vệ phiên**: TLS, Secure/HttpOnly/SameSite cookies, session rotation, timeout, logout/revocation, giảm XSS/CSRF.
10. **Đo hoạt động và thử tấn công**: replay, brute force, push fatigue, phishing, SIM swap, cross-account, multi-node race, downgrade và mất hệ thống verifier.
11. **Xác nhận đúng phiên bản framework**: không dùng Spring Security 7 `FactorGrantedAuthority` trong dự án Spring Security 6.x; kiểm tra dependencies/API và tài liệu version cụ thể.
12. **Đánh giá độc lập toàn hệ thống**: secret storage, device compromise, shared mailbox, IdP recovery, helpdesk và backup code có thể tạo cùng điểm thất bại.

## 17. Tự đánh giá

**Câu 1.** Người dùng nhập password rồi PIN ở hai trang khác nhau. Có phải MFA không?  
**Trả lời:** Không. Hai bước đều dùng loại yếu tố **knowledge**.

**Câu 2.** Password + TOTP từ app có bảo vệ chống mọi phishing không?  
**Trả lời:** Không. Đây thường là knowledge + possession nhưng mã nhập tay có thể bị site giả chuyển tiếp ngay sang site thật.

**Câu 3.** Tại sao password + email OTP không nên mặc nhiên được coi là MFA mạnh?  
**Trả lời:** Mailbox có thể chỉ phụ thuộc cùng password và cùng thiết bị; NIST SP 800-63B-4 không cho dùng email làm OOB authenticator. Email có thể hữu ích để verify/recovery nhưng không thay thế authenticator độc lập phù hợp assurance.

**Câu 4.** Phát hiện user đã login bằng password có `Authentication.isAuthenticated()==true`. Đã đủ cho `/admin` yêu cầu MFA?  
**Trả lời:** Chưa. Cần xác minh một yếu tố độc lập, cùng user/session, còn mới và quyền admin hiện tại.

**Câu 5.** User passkey dùng fingerprint ở thiết bị. Dữ liệu fingerprint có được gửi về Spring backend không?  
**Trả lời:** Không trong WebAuthn chuẩn; authenticator thực hiện user verification cục bộ và tạo assertion có chữ ký; backend kiểm tra challenge/origin/RP ID/chữ ký/UV theo policy.

**Câu 6.** Hai request cùng TOTP hợp lệ chạy đồng thời ở hai API nodes nên xử lý thế nào?  
**Trả lời:** Chỉ một lần được chấp nhận theo chính sách replay; trạng thái consumed/timestep/attempt cần cập nhật nguyên tử trong shared store.

**Câu 7.** Spring Security 7 dùng `FACTOR_PASSWORD` + `FACTOR_OTT` thì hệ thống đã đạt NIST AAL2 chưa?  
**Trả lời:** Không thể kết luận từ tên authorities. Phải đánh giá loại authenticator, độc lập, email/SMS restrictions, enrollment, replay, session và toàn bộ yêu cầu chuẩn.

**Câu 8.** MFA hoàn tất lúc sáng, buổi tối chuyển khoản có cần nhập lại không?  
**Trả lời:** Tùy chính sách step-up/freshness/transaction binding; với tác vụ nhạy cảm nên đánh giá thời điểm xác thực và yêu cầu factor mới khi cần.

## Tài liệu tham khảo

- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): yếu tố độc lập, MFA fatigue, phishing, enrollment, recovery, reset và thay đổi factors.
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html): nhóm authenticator, yêu cầu MFA/OOB, email không phải OOB authenticator, PSTN restricted, phishing resistance, replay.
- [Spring Security 7 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): `FactorGrantedAuthority`, `@EnableMultiFactorAuthentication`, rules và step-up.
- [Spring Security — FactorGrantedAuthority Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html): các factor authorities và timestamp.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` và policy.
- [Spring Security — One-Time Token Login](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html): cơ chế OTT, không đồng nghĩa bằng chứng độc lập hay NIST AAL.
- [W3C — Web Authentication Level 3](https://www.w3.org/TR/webauthn-3/): WebAuthn challenge, RP ID, origin, UP/UV, authenticator assertions.
- [RFC 6238 — TOTP](https://www.rfc-editor.org/rfc/rfc6238): thời gian và cơ chế mã một lần TOTP.
