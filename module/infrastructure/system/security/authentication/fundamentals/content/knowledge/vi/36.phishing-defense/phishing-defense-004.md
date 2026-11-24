# Phishing-resistant authenticator — Bộ xác thực chống phishing
 
> **Chương:** Chống phishing  
> **Chủ đề:** Phishing-resistant authenticator

**Phishing-resistant authenticator** là phương thức xác thực được thiết kế để ngăn kẻ tấn công lấy được bằng chứng đăng nhập có thể dùng lại khi lừa người dùng truy cập một trang giả mạo hoặc chuyển tiếp phiên đăng nhập qua máy chủ trung gian. Điểm cốt lõi là bằng chứng xác thực được ràng buộc với đúng relying party (RP), origin hoặc kênh xác thực dự kiến, thay vì chỉ dựa vào một bí mật mà người dùng có thể nhập vào bất kỳ trang web nào.

Passkey và security key dựa trên FIDO2/WebAuthn là những ví dụ phổ biến. Khi người dùng xác thực tại đúng website, authenticator ký một challenge gắn với RP ID; trình duyệt cung cấp origin của trang; server kiểm tra chữ ký, challenge, RP ID hash và các điều kiện giao thức. Một trang phishing ở domain khác không thể yêu cầu authenticator tạo assertion hợp lệ cho RP thật. Certificate-based authentication cũng có thể chống phishing khi private key được dùng trong mutual TLS hoặc giao thức có channel binding được cấu hình đúng.

Không phải mọi phương thức có hai yếu tố, sinh mã dùng một lần hoặc có thông báo push đều chống phishing. SMS OTP, email OTP, TOTP và push approval thông thường có thể bị phishing hoặc relay theo thời gian thực. Mức bảo vệ thực tế còn phụ thuộc vào enrollment, recovery, verifier, domain/origin, quản lý khóa, thiết bị và cách ứng dụng sử dụng kết quả xác thực.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối password, MFA, passkey, certificate, token, session, SSO và recovery. Trọng tâm là hiểu cơ chế ràng buộc RP, lựa chọn authenticator phù hợp, xác minh đúng giao thức và giữ toàn bộ vòng đời danh tính ở mức bảo đảm tương ứng.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích phishing-resistant authentication và phân biệt nó với MFA thông thường.
2. Mô tả cách FIDO2/WebAuthn ràng buộc assertion với RP ID, origin và challenge.
3. Phân biệt passkey đồng bộ, passkey gắn thiết bị và security key vật lý.
4. Giải thích user presence, user verification, authenticator data và chữ ký assertion.
5. Xác định vì sao SMS OTP, email OTP, TOTP và push thông thường có thể bị relay/phishing.
6. Đánh giá certificate-based authentication và điều kiện để private key được ràng buộc với đúng dịch vụ.
7. Thiết kế enrollment, authentication, step-up, recovery và revocation cho authenticator chống phishing.
8. Kiểm tra token/assertion và authentication context trước khi tạo session hoặc cấp quyền.
9. Xây dựng threat model và test plan chống lookalike domain, reverse proxy phishing và credential relay.

## 2. Phishing-resistant authentication giải quyết điều gì?

Phishing thường dụ người dùng nhập password, OTP hoặc thông tin đăng nhập vào một website do attacker kiểm soát. Một số cuộc tấn công dùng reverse proxy để chuyển tiếp request tới website thật, lấy cookie hoặc token sau khi người dùng hoàn tất MFA. Vì người dùng đang tương tác với một trang trông giống dịch vụ thật, các phương thức dựa trên bí mật có thể bị lừa cung cấp bằng chứng hợp lệ.

Một authenticator chống phishing tạo bằng chứng phụ thuộc vào danh tính của RP hoặc kênh xác thực. Người dùng không phải tự nhận biết domain giả bằng mắt trong từng lần đăng nhập; trình duyệt và authenticator tham gia kiểm tra ràng buộc kỹ thuật.

### 2.1. Mục tiêu bảo vệ

- Ngăn credential hoặc assertion của RP thật được tạo cho domain giả;
- Giảm khả năng attacker relay challenge/response qua proxy trung gian;
- Ngăn password hoặc OTP bị thu thập rồi tái sử dụng ở dịch vụ thật;
- Hỗ trợ xác thực mạnh cho quản trị viên và thao tác nhạy cảm;
- Giảm phụ thuộc vào khả năng người dùng nhận diện giao diện giả.

### 2.2. Những gì phương thức này không tự giải quyết

Phishing resistance không tự ngăn:

- Malware hoặc attacker kiểm soát thiết bị người dùng;
- Session cookie bị đánh cắp sau khi đăng nhập;
- Lỗ hổng XSS hoặc lỗi authorization trong ứng dụng thật;
- Người dùng bị lừa tự phê duyệt một hành động trong ứng dụng thật;
- Account recovery yếu hoặc helpdesk bị social engineering;
- Enrollment passkey trái phép khi attacker đã chiếm session;
- Endpoint hoặc RP server bị compromise.

Do đó, cần kết hợp với session protection, endpoint security, authorization, recovery controls và giám sát hành vi.

## 3. Phân biệt phishing-resistant với MFA

MFA mô tả việc kết hợp nhiều yếu tố hoặc phương thức xác thực. Phishing resistance mô tả khả năng chống việc attacker lừa người dùng cung cấp bằng chứng cho một RP giả. Hai khái niệm liên quan nhưng không đồng nghĩa.

| Phương thức | Có thể dùng MFA? | Phishing resistance |
| --- | --- | --- |
| Password đơn lẻ | Không | Không |
| Password + SMS OTP | Có | Không; OTP có thể bị relay hoặc SIM swap |
| Password + email OTP | Có | Không; mailbox và mã có thể bị phishing |
| Password + TOTP | Có | Không; mã TOTP có thể bị proxy phishing theo thời gian thực |
| Push approval thông thường | Có thể | Không mặc định; có thể bị push fatigue hoặc social engineering |
| Push với number matching/context | Có thể | Giảm một số rủi ro nhưng không mặc định tương đương FIDO/WebAuthn |
| Passkey/WebAuthn | Có thể là passwordless hoặc kết hợp với yếu tố kích hoạt local | Có khả năng chống phishing nhờ ràng buộc RP/origin |
| FIDO2 security key | Có thể | Có khả năng chống phishing nhờ ràng buộc RP |
| Client certificate qua mutual TLS | Có thể | Có thể chống phishing khi private key, TLS endpoint và mapping được ràng buộc đúng |

### 3.1. OTP dùng một lần vẫn có thể bị phishing

One-time chỉ có nghĩa mã được thiết kế để không dùng lại theo quy tắc hoặc cửa sổ thời gian. Nó không có nghĩa mã được ràng buộc với domain thật. Attacker có thể mở phiên đăng nhập thật ở phía server, yêu cầu nạn nhân nhập TOTP vào trang giả và chuyển tiếp mã ngay lập tức.

### 3.2. Push không tự động chống phishing

Thông báo “Approve sign-in?” có thể bị spam cho tới khi người dùng bấm đồng ý. Number matching và hiển thị ngữ cảnh giúp giảm push fatigue, nhưng vẫn cần đánh giá cách thiết bị xác minh giao dịch và liệu response có ràng buộc với đúng RP/session hay không.

## 4. Mô hình trust: RP, browser và authenticator

Trong WebAuthn, ba thành phần phối hợp:

- **Relying Party (RP):** website/dịch vụ đăng ký credential và xác minh assertion;
- **Browser/User Agent:** kiểm soát origin của trang và giao tiếp với authenticator;
- **Authenticator:** giữ private key và tạo chữ ký cho challenge theo RP.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant R as RP server
    participant A as Authenticator
    U->>B: Mở website thật
    B->>R: Bắt đầu đăng nhập
    R-->>B: Challenge và RP configuration
    B->>A: Yêu cầu xác thực cho RP ID
    A->>A: Xác minh user presence/verification
    A-->>B: Assertion có chữ ký
    B->>R: Gửi assertion và client data
    R->>R: Kiểm tra challenge, origin, RP ID hash và signature
    R-->>B: Authentication thành công
~~~

Private key không được gửi tới website. Server lưu public key và thông tin credential cần thiết. Trình duyệt lấy origin từ ngữ cảnh trang và authenticator tạo assertion cho RP ID hợp lệ.

### 4.1. Vì sao domain giả không dùng được passkey của domain thật?

Một passkey được đăng ký với RP ID cụ thể, ví dụ domain của dịch vụ. Khi trang giả ở domain khác yêu cầu WebAuthn, browser không cho trang đó sử dụng credential của RP thật. Authenticator cũng đưa RP ID hash vào authenticator data; RP server xác minh giá trị này.

Attacker có thể tạo trang có giao diện giống hệt, nhưng không thể chỉ bằng giao diện khiến authenticator ký assertion cho RP ID thật từ origin giả.

### 4.2. Origin và RP ID

Origin gồm scheme, host và port theo mô hình bảo mật của browser. RP ID thường là domain hiện tại hoặc một domain cha được phép theo quy tắc WebAuthn; không phải URL tùy ý. Server phải cấu hình RP ID và origin allowlist chính xác, tránh chấp nhận origin rộng hơn phạm vi cần thiết.

Không dùng wildcard domain tùy tiện. Nếu nhiều subdomain cùng chia sẻ RP ID, cần hiểu ranh giới trust: compromise một subdomain có thể làm tăng rủi ro cho các ứng dụng cùng phạm vi RP ID.

## 5. FIDO2, WebAuthn và CTAP

**FIDO2** là tập công nghệ xác thực dựa trên public-key. Hai thành phần chính:

- **WebAuthn:** API và giao thức giữa website/browser với authenticator;
- **CTAP (Client to Authenticator Protocol):** giao tiếp giữa client/platform và roaming authenticator như security key.

Authenticator có thể tích hợp trong thiết bị (platform authenticator) hoặc là thiết bị rời (roaming authenticator).

### 5.1. Platform authenticator

Platform authenticator nằm trong hoặc được quản lý bởi thiết bị, ví dụ cơ chế bảo vệ khóa của hệ điều hành. Người dùng có thể kích hoạt bằng biometric hoặc PIN local. Private key được bảo vệ bởi phần cứng/secure environment theo khả năng nền tảng.

### 5.2. Roaming authenticator

Security key vật lý có thể kết nối USB, NFC hoặc BLE tùy thiết bị. Người dùng mang key giữa nhiều máy. Đây là lựa chọn hữu ích cho quản trị viên hoặc môi trường cần key dự phòng tách biệt.

### 5.3. Vai trò của PIN và biometric

PIN/biometric thường dùng để mở khóa hoặc kích hoạt authenticator local. Dữ liệu biometric không được gửi tới RP như một mật khẩu; authenticator báo trạng thái user verification qua flag. Chất lượng bảo vệ phụ thuộc vào implementation của thiết bị, secure hardware và policy nền tảng.

## 6. Passkey: đồng bộ và gắn thiết bị

Passkey là credential dựa trên public-key, được quản lý để người dùng đăng nhập không cần nhập password. Passkey có thể đồng bộ giữa thiết bị qua hệ sinh thái hoặc chỉ gắn với một authenticator/thiết bị.

### 6.1. Synced passkey

Synced passkey có thể được đồng bộ an toàn qua tài khoản của nhà cung cấp nền tảng. Ưu điểm là người dùng đổi hoặc mất một thiết bị vẫn có thể dùng thiết bị khác đã đồng bộ. Bảo đảm phụ thuộc vào bảo mật tài khoản đồng bộ, cơ chế mã hóa, recovery và thiết bị được tin cậy.

Không giả định synced passkey luôn có mức bảo vệ phần cứng hoặc device binding giống nhau giữa các nền tảng. Cần đánh giá threat model và policy của hệ sinh thái.

### 6.2. Device-bound credential

Credential gắn thiết bị có private key không được đồng bộ theo cách người dùng có thể tự khôi phục trên thiết bị khác. Nó có thể phù hợp cho môi trường quản lý chặt, nhưng tăng rủi ro lockout nếu thiết bị hỏng hoặc mất. Cần phương án dự phòng và quy trình recovery.

### 6.3. Security key dự phòng

Với tài khoản nhạy cảm, có thể đăng ký ít nhất hai security key hoặc một passkey chính cùng một key dự phòng. Key dự phòng nên được cất tách biệt và kiểm tra định kỳ. Gỡ key bị mất ở RP ngay cả khi chưa thể xóa private key trên thiết bị.

## 7. User presence và user verification

WebAuthn phân biệt hai khái niệm:

- **User presence (UP):** có thao tác chứng minh người dùng hiện diện, ví dụ chạm security key;
- **User verification (UV):** authenticator xác minh người dùng cục bộ bằng PIN, biometric hoặc phương thức được thiết bị hỗ trợ.

UP không tự chứng minh người đang chạm key là chủ tài khoản. UV tăng bảo đảm rằng người dùng đã qua bước xác minh local. RP có thể yêu cầu UV theo mức nhạy cảm.

### 7.1. UV không phải identity proofing

UV cho biết authenticator đã xác minh người sử dụng thiết bị theo cơ chế local. Nó không chứng minh danh tính pháp lý, chức danh hoặc tenant membership. Những điều đó cần enrollment/identity proofing và authorization riêng.

### 7.2. Không tự diễn giải biometric

RP thường chỉ nhận flag UV, không nhận mẫu vân tay/khuôn mặt. Không kết luận thiết bị sử dụng loại biometric cụ thể nếu giao thức không cung cấp bằng chứng đó.

## 8. WebAuthn registration: enrollment an toàn

Registration gắn một public key credential với account và RP. Đây là thao tác nhạy cảm vì attacker có thể thêm credential của họ nếu đã chiếm session.

### 8.1. Quy trình registration

1. Người dùng đăng nhập bằng phương thức hiện có đủ tin cậy.
2. RP kiểm tra account state và yêu cầu reauthentication/step-up nếu policy cần.
3. RP sinh challenge ngẫu nhiên, lưu transaction có TTL và gắn với account/session.
4. Browser gọi WebAuthn API với RP ID và user context.
5. Authenticator tạo key pair; private key ở authenticator.
6. Browser gửi attestation/registration response tới RP.
7. RP xác minh challenge, origin, RP ID hash, flags và cấu trúc dữ liệu.
8. RP kiểm tra credential ID chưa gắn với principal khác theo policy.
9. RP lưu credential ID, public key và metadata cần thiết.
10. RP thông báo người dùng và ghi audit.

### 8.2. Attestation

Attestation có thể cung cấp thông tin về authenticator model/provenance theo format và policy. Không phải ứng dụng nào cũng cần attestation; nhiều passkey consumer dùng attestation none hoặc anonymized để giảm theo dõi thiết bị.

Attestation không tự chứng minh danh tính người dùng. Nếu yêu cầu authenticator được quản lý, cần xác định attestation trust anchors, metadata, privacy impact và quy trình xử lý thiết bị không được nhận diện.

### 8.3. Chống enrollment hijacking

- Yêu cầu xác thực lại bằng factor đã tồn tại;
- Không cho passkey mới tự xác minh thao tác thêm chính nó;
- Challenge gắn account, session, origin và purpose;
- Gửi thông báo tới kênh đã đăng ký;
- Có audit và cách thu hồi credential mới;
- Với account đặc quyền, cân nhắc approval hoặc cooldown.

## 9. WebAuthn authentication: assertion và validation

Khi đăng nhập, RP sinh challenge mới. Authenticator ký dữ liệu gắn với RP và challenge; server xác minh chữ ký bằng public key đã lưu.

### 9.1. Các thành phần quan trọng

- **challenge:** giá trị ngẫu nhiên, một lần, có TTL;
- **clientDataJSON:** chứa type, challenge, origin và dữ liệu client;
- **authenticatorData:** chứa RP ID hash, flags và sign counter/extension data;
- **signature:** chữ ký bằng private key của credential;
- **credential ID:** xác định credential public key tương ứng;
- **userHandle:** có thể giúp xác định account trong discoverable credential flow.

### 9.2. Các bước server phải xác minh

1. Challenge khớp transaction đang chờ và chưa được dùng;
2. Type đúng là webauthn.get cho assertion;
3. Origin nằm trong allowlist chính xác;
4. RP ID hash khớp RP ID đã cấu hình;
5. Chữ ký hợp lệ với public key đã đăng ký;
6. User presence và user verification đáp ứng policy;
7. Credential ID thuộc account/principal phù hợp;
8. Transaction còn hạn, chưa consumed và gắn với đúng session/client;
9. Sign counter hoặc metadata được xử lý theo đặc tính authenticator.

Sign counter có thể không tăng như mong đợi ở một số synced passkey hoặc authenticator phân tán. Không dùng counter như biện pháp duy nhất để kết luận clone; hiểu profile thiết bị và áp dụng các kiểm tra khác.

### 9.3. Không chỉ kiểm tra chữ ký

Chữ ký hợp lệ nhưng challenge sai, origin không đúng hoặc RP ID hash không khớp vẫn phải bị từ chối. Chữ ký chỉ là một phần của xác minh giao thức.

## 10. Certificate-based authentication

Certificate-based authentication có thể chống phishing khi client chứng minh quyền kiểm soát private key trong một kênh được ràng buộc với đúng server/service.

### 10.1. Mutual TLS

Trong mutual TLS (mTLS), server yêu cầu client certificate trong TLS handshake. Client ký dữ liệu handshake bằng private key tương ứng. Bằng chứng này gắn với kết nối TLS tới server có certificate/hostname cụ thể; một website phishing ở hostname khác không thể đơn giản nhận certificate assertion cho hostname thật nếu trust và hostname verification được cấu hình đúng.

### 10.2. Điều kiện bảo vệ

- Client private key được bảo vệ trong smart card, TPM, HSM hoặc keystore phù hợp;
- Server xác minh certificate chain tới trust anchor được cấu hình;
- Kiểm tra hostname/server identity và TLS handshake;
- Kiểm tra EKU, key usage, subject/SAN và mapping tới principal;
- Có quy trình certificate expiry, CRL/OCSP hoặc revocation policy;
- Không cho certificate từ CA không được tin cậy;
- Bảo vệ private key khỏi export hoặc sao chép nếu policy yêu cầu.

### 10.3. Smart card/PIV

Smart card có thể giữ private key và yêu cầu PIN local để thực hiện thao tác ký. Nó hữu ích trong môi trường enterprise hoặc quản trị. Tuy nhiên, certificate enrollment, PIN reset, card issuance và revocation cần quy trình PKI đáng tin cậy.

### 10.4. Giới hạn

Certificate-based authentication không tự đảm bảo mọi trang đăng nhập đều chống phishing. Nếu ứng dụng xuất private key thành file, dùng một challenge không gắn kênh, chấp nhận CA tùy ý hoặc bỏ qua hostname validation, bảo vệ có thể bị suy yếu. Cần đánh giá đúng giao thức tích hợp và browser/client behavior.

## 11. So sánh authenticator chống phishing

| Đặc tính | Passkey/WebAuthn | Security key | Certificate/mTLS |
| --- | --- | --- | --- |
| Ràng buộc RP/service | RP ID và origin | RP ID và origin | TLS server identity/channel |
| Private key | Authenticator/platform | Thiết bị vật lý | Smart card, TPM, HSM hoặc keystore |
| User verification | Có thể yêu cầu UV | Tùy key và cấu hình | Có thể dùng PIN/smart card policy |
| Phishing resistance | Có khi triển khai đúng | Có khi triển khai đúng | Có khi mTLS/channel binding đúng |
| Recovery | Synced passkey hoặc factor dự phòng | Key dự phòng và quy trình thay | Cấp lại certificate/key qua PKI |
| Vận hành | Browser/platform support | Phân phối và quản lý key | PKI, CA, revocation, client configuration |

Chọn phương thức dựa trên người dùng, thiết bị, mức assurance, khả năng vận hành và recovery. Không có một authenticator phù hợp mọi môi trường.

## 12. Tấn công AiTM và credential relay

Adversary-in-the-middle (AiTM) phishing đặt một proxy giữa người dùng và website thật. Người dùng tương tác với domain attacker; proxy chuyển request tới dịch vụ thật và chuyển response về. Với password và OTP, attacker có thể lấy thông tin hoặc relay mã trong thời gian hợp lệ, sau đó lấy session cookie.

### 12.1. Vì sao TOTP có thể bị relay?

TOTP được tính từ secret và thời gian. Mã không gắn với domain thật hoặc transaction cụ thể. Nếu nạn nhân nhập mã vào proxy trong thời gian còn hiệu lực, attacker có thể chuyển tiếp mã tới website thật.

### 12.2. Vì sao WebAuthn chống relay tốt hơn?

Browser chỉ cho phép trang hợp lệ gọi WebAuthn cho RP ID được phép. Authenticator tạo assertion chứa dữ liệu ràng buộc RP; RP kiểm tra origin và challenge. Proxy ở domain khác không thể yêu cầu passkey thật tạo assertion hợp lệ cho origin attacker.

### 12.3. Những rủi ro vẫn còn

- Attacker kiểm soát browser/endpoint có thể thao túng phiên sau xác thực;
- XSS trên origin thật có thể thực hiện hành động trong phiên;
- Người dùng có thể bị lừa phê duyệt giao dịch trong ứng dụng thật;
- Session token bị đánh cắp sau khi được phát hành;
- Enrollment hoặc recovery yếu có thể thêm credential của attacker.

Do đó, phishing-resistant login cần đi cùng bảo vệ session, CSP/XSS controls, authorization và transaction confirmation.

## 13. Triển khai RP và domain an toàn

Phishing resistance phụ thuộc vào cấu hình domain/origin và verifier:

- Chỉ phục vụ authentication trên HTTPS;
- Cấu hình RP ID hẹp nhất đáp ứng kiến trúc;
- Duy trì origin allowlist chính xác theo scheme/host/port;
- Không chấp nhận origin từ client tùy ý;
- Kiểm tra RP ID hash và challenge ở server;
- Bảo vệ subdomain có cùng RP ID khỏi takeover;
- Không đưa WebAuthn callback qua domain trung gian không được thiết kế;
- Quản lý môi trường staging/test tách khỏi production RP ID khi cần.

### 13.1. Subdomain và shared RP ID

Nếu RP ID là domain cha, các subdomain đủ điều kiện có thể dùng credential cùng phạm vi. Điều này tiện cho nhiều ứng dụng nhưng mở rộng trust boundary. Một subdomain bị takeover có thể làm tăng rủi ro cho các ứng dụng khác cùng RP ID.

Chỉ chia sẻ RP ID khi có lý do kiến trúc, kiểm soát subdomain và kiểm tra origin nghiêm ngặt. Không coi cùng registrable domain là lý do đủ để mọi subdomain cùng tin nhau.

### 13.2. Domain migration

Khi đổi domain, passkey cũ không tự động chuyển sang RP ID mới. Cần kế hoạch migration: duy trì domain cũ an toàn trong thời gian chuyển, xác thực người dùng, đăng ký credential mới cho RP ID mới và thu hồi credential cũ khi phù hợp. Không redirect domain cũ sang domain mới rồi giả định RP binding tự thay đổi.

## 14. Authentication context và OIDC/SAML

Trong hệ thống liên kết danh tính, RP cần biết IdP đã sử dụng phương thức và mức bảo đảm nào. Token/assertion phải được xác minh theo giao thức và claim chỉ được diễn giải theo hợp đồng đã cấu hình.

### 14.1. OIDC

OIDC có thể cung cấp:

- **acr:** authentication context class;
- **amr:** phương thức xác thực được báo cáo;
- **auth_time:** thời điểm xác thực;
- Các yêu cầu như max_age hoặc acr_values tùy khả năng OP.

RP không nên tự suy luận mọi giá trị amr có chứa “mfa” đồng nghĩa với phishing resistance. Cần mapping rõ giữa OP, acr/amr và policy nội bộ; xác minh issuer, audience, signature, nonce và thời gian trước khi tin claim.

### 14.2. SAML

SAML assertion có thể mang AuthnContextClassRef và AuthnInstant. SP cần biết context URI nào biểu thị phương thức chống phishing theo thỏa thuận với IdP. Không chấp nhận một chuỗi context chỉ vì tên có vẻ mạnh.

### 14.3. RP vẫn chịu trách nhiệm authorization

IdP xác thực người dùng, nhưng RP vẫn kiểm tra account state, tenant membership, resource ownership và quyền hiện tại. Phishing-resistant authentication không tự cấp quyền quản trị.

## 15. Enrollment, recovery và lifecycle

Một hệ thống chỉ chống phishing ở bước đăng nhập nhưng cho phép attacker thêm credential qua flow yếu thì vẫn có thể bị chiếm.

### 15.1. Enrollment

- Yêu cầu reauthentication bằng credential hiện có;
- Với hành động nhạy cảm, yêu cầu step-up;
- Challenge gắn account, session, origin và purpose;
- Thông báo khi có authenticator mới;
- Hiển thị credential/device label để người dùng nhận diện;
- Cung cấp thu hồi từng credential;
- Không cho support tự thêm passkey chỉ bằng email.

### 15.2. Recovery

Recovery phải có assurance tương xứng với login. Nếu passkey chống phishing là phương thức chính, recovery chỉ bằng email/SMS có thể trở thành điểm yếu. Cân nhắc security key dự phòng, recovery code, identity proofing hoặc helpdesk có dual control.

### 15.3. Revocation

Khi thiết bị mất hoặc nghi compromise, RP phải revoke credential ID ngay ở server và xử lý session/token liên quan. RP không thể xóa private key khỏi thiết bị từ xa; người dùng có thể cần xóa credential khỏi authenticator hoặc hệ sinh thái đồng bộ.

### 15.4. Account lifecycle

Khi nhân viên rời tổ chức, cần thu hồi passkey registration, certificate, session, token, API key và membership theo policy. Không chỉ tắt password nếu các phương thức khác vẫn còn active.

## 16. Step-up cho hành động nhạy cảm

Phishing-resistant authenticator đặc biệt hữu ích cho:

- Thêm/gỡ authenticator hoặc recovery factor;
- Đổi email, số điện thoại hoặc password;
- Cấp role quản trị;
- Tạo API key hoặc certificate;
- Xuất dữ liệu nhạy cảm;
- Phê duyệt thanh toán hoặc thao tác không thể đảo ngược;
- Liên kết/gỡ liên kết IdP.

RP có thể yêu cầu xác thực gần đây hoặc mức assurance cụ thể. Sau khi nhận kết quả, server phải kiểm tra auth_time, acr/amr hoặc trạng thái WebAuthn đã xác minh; không chỉ tin client báo “đã MFA”.

Kết quả step-up nên gắn với subject, session, purpose, resource/transaction và TTL. Một lần xác thực để thêm passkey không tự động cho phép cấp role admin hoặc xuất dữ liệu.

## 17. Session protection sau phishing-resistant login

Phishing-resistant authentication giảm nguy cơ credential bị lấy qua domain giả, nhưng session sau đăng nhập vẫn có thể bị đánh cắp.

### 17.1. Cookie và token

- Cookie session dùng Secure, HttpOnly và SameSite phù hợp;
- Không đưa access/refresh token vào URL;
- Bảo vệ token trong client storage;
- Dùng CSRF protection cho request thay đổi trạng thái;
- Có TTL, rotation và revocation;
- Thu hồi session khi phát hiện compromise;
- Hạn chế quyền của session mới sau recovery.

### 17.2. XSS và endpoint compromise

WebAuthn không thay thế CSP, output encoding, dependency security hoặc endpoint protection. XSS trên origin thật có thể thực hiện request bằng session người dùng. Malware có thể thao túng browser hoặc đánh cắp dữ liệu sau khi đã đăng nhập.

### 17.3. Transaction confirmation

Với giao dịch nhạy cảm, hiển thị nội dung cần xác nhận và ràng buộc challenge với transaction. Nếu người nhận, số tiền hoặc resource thay đổi sau khi xác nhận, cần challenge mới. Việc chỉ yêu cầu passkey mà không gắn nội dung giao dịch không tự bảo vệ khỏi mọi kiểu transaction manipulation.

## 18. Ví dụ kiến trúc: portal quản trị trường học

Một portal quản trị có dữ liệu học viên và bảng điểm. Tổ chức yêu cầu nhân viên dùng passkey hoặc security key; tài khoản quản trị cần user verification.

~~~mermaid
flowchart TD
    U["Nhân viên"] --> B["Browser trên thiết bị"]
    B --> W["WebAuthn API"]
    W --> A["Platform authenticator / Security key"]
    A -->|"Assertion ký challenge"| B
    B --> R["RP authentication service"]
    R --> V["Verify origin, RP ID hash, challenge, signature, UV"]
    V --> S["Tạo session"]
    S --> P["Authorization policy"]
    P --> D["Tenant, role, resource checks"]
    D --> X["Portal / API"]
    X --> L["Audit và monitoring"]
~~~

### 18.1. Đăng nhập

1. Browser mở domain chính thức của portal qua HTTPS.
2. RP tạo challenge ngẫu nhiên và transaction có TTL.
3. Authenticator yêu cầu user verification theo policy.
4. Browser gửi assertion tới server.
5. Server xác minh challenge, origin, RP ID hash, signature, credential và UV.
6. Server ánh xạ credential vào principal, kiểm tra account active và tạo session.
7. Authorization service kiểm tra tenant membership và role hiện tại.

### 18.2. Cấp quyền quản trị

Khi nhân viên yêu cầu role admin, hệ thống yêu cầu step-up bằng passkey/security key với UV, approval độc lập và thời hạn JIT. Role assignment được audit và các API kiểm tra quyền hiện tại.

### 18.3. Mất security key

Người dùng dùng passkey dự phòng hoặc recovery flow có assurance phù hợp. Admin revoke credential ID bị mất, thu hồi session liên quan nếu cần, thông báo và đăng ký key mới. Email đơn lẻ không được dùng để bỏ qua policy.

## 19. Pseudocode xác minh WebAuthn assertion

~~~text
verify_webauthn_assertion(response, transaction, credential):
    require transaction.status == PENDING
    require now < transaction.expires_at
    require transaction.purpose == AUTHENTICATION

    client_data = parse_client_data_with_size_limits(response.client_data)
    require client_data.type == "webauthn.get"
    require client_data.challenge == transaction.challenge
    require client_data.origin in configured_origin_allowlist

    auth_data = parse_authenticator_data(response.authenticator_data)
    require auth_data.rp_id_hash == sha256(configured_rp_id)
    require auth_data.user_present == true
    if transaction.requires_user_verification:
        require auth_data.user_verified == true

    require response.credential_id == credential.id
    verify_signature(
        credential.public_key,
        auth_data || sha256(response.client_data)
        || response.signature
    )

    atomically_consume(transaction)
    return verified_principal(credential.account)
~~~

Đây là pseudocode khái niệm, không phải triển khai thư viện hoàn chỉnh. Thư viện WebAuthn đã được kiểm chứng cần xử lý đầy đủ CBOR/COSE, extension, attestation/assertion format, algorithm, backup flags, counter semantics và lỗi parser.

## 20. Kiểm thử phishing-resistant authenticator

Kiểm thử trong staging với RP ID, origin, authenticator và account thử nghiệm. Không dùng credential production.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Valid origin | Assertion từ origin chính xác | Được xác minh nếu mọi điều kiện khác hợp lệ |
| Lookalike domain | Trang giả ở domain khác yêu cầu passkey của RP thật | Browser không cung cấp credential của RP thật |
| Wrong origin | clientData origin không nằm allowlist | Server từ chối |
| Wrong RP ID | RP ID hash không khớp | Server từ chối |
| Challenge mismatch | Assertion dùng challenge cũ/sai | Server từ chối |
| Replay | Dùng lại assertion/transaction đã consumed | Server từ chối |
| Signature tampering | Thay đổi authenticator data hoặc signature | Server từ chối |
| Missing UP | Assertion không có user presence khi policy yêu cầu | Server từ chối |
| Missing UV | Action yêu cầu UV nhưng flag không có | Server từ chối |
| Wrong credential | Credential ID thuộc account khác | Server từ chối |
| Enrollment hijack | Session thường cố thêm passkey mới cho account | Yêu cầu reauthentication/step-up |
| Subdomain trust | Origin subdomain không được phép | Server từ chối |
| Domain migration | Passkey cũ được dùng cho RP ID mới | Không tự chấp nhận; chạy migration flow |
| Synced passkey | Credential đồng bộ giữa thiết bị theo policy | Xác minh đúng RP và account |
| Certificate | Client cert từ CA không tin cậy | TLS/client auth từ chối |
| Certificate revoked | Cert bị revoke | Relying party từ chối theo revocation policy |
| AiTM proxy | Password/TOTP bị relay trong test mô phỏng | Phương thức yếu bị nhận diện; WebAuthn assertion không hợp lệ ở origin giả |
| Session theft | Cookie bị sao chép sau login | Session controls/revocation giảm thiểu; không giả định passkey ngăn được |
| Recovery bypass | Email đơn lẻ cố thay passkey | Không vượt policy recovery |
| Step-up purpose | Proof cho add-passkey dùng để export data | Từ chối do purpose mismatch |
| Authorization | Passkey hợp lệ nhưng user không có role | Authentication thành công; authorization DENY |
| Logging | Bật debug/trace | Không log private key, token hoặc dữ liệu nhạy cảm |

### 20.1. Bất biến bảo mật

- Assertion chỉ hợp lệ cho đúng RP ID, origin, challenge và credential;
- Server xác minh signature và flags theo policy, không chỉ decode response;
- Challenge được tiêu thụ một lần;
- User verification được yêu cầu cho action cần mức bảo đảm đó;
- Enrollment/recovery không yếu hơn policy đăng nhập;
- Certificate trust và revocation được kiểm tra đúng;
- Phishing-resistant authentication không tự cấp role hoặc quyền resource;
- Session vẫn có TTL, revocation và bảo vệ riêng.

## 21. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi SMS/TOTP là phishing-resistant | Attacker relay mã theo thời gian thực | Dùng FIDO/WebAuthn hoặc cơ chế channel-bound phù hợp |
| Chỉ kiểm tra chữ ký WebAuthn | Assertion sai origin/challenge có thể lọt nếu thiếu kiểm tra | Xác minh toàn bộ RP ID, origin, challenge và flags |
| RP ID quá rộng | Mở rộng trust sang nhiều subdomain | Chọn RP ID hẹp và quản lý subdomain |
| Không yêu cầu UV cho action nhạy cảm | Chỉ có user presence nhưng policy cần xác minh local | Đặt userVerification required |
| Tin attestation là identity proofing | Nhầm thiết bị với danh tính người dùng | Tách authenticator attestation và identity proofing |
| Không step-up khi thêm passkey | Session bị chiếm có thể cài credential attacker | Reauthentication, purpose binding và notification |
| Recovery chỉ bằng email | Mailbox takeover bypass passkey | Recovery factor độc lập và assurance phù hợp |
| Không revoke credential bị mất | RP vẫn chấp nhận assertion từ key cũ | Revoke credential ID phía server |
| Bỏ qua session protection | Cookie bị đánh cắp sau login vẫn dùng được | Cookie hardening, TTL, rotation và revocation |
| Tin acr/amr không có mapping | RP đánh giá sai assurance từ IdP | Hợp đồng context rõ và xác minh token/assertion |
| Certificate không kiểm tra hostname/CA | Client cert được chấp nhận sai trust boundary | mTLS và PKI validation đúng |

## 22. Checklist production

1. **Threat model:** Phương thức có chống phishing/relay ở đúng RP hay chỉ thêm một mã OTP?
2. **RP identity:** RP ID, origin và HTTPS được cấu hình hẹp, chính xác?
3. **Subdomain:** Có đánh giá shared RP ID và nguy cơ subdomain takeover?
4. **Authenticator:** Platform, synced passkey hay security key phù hợp user/device policy?
5. **User verification:** Action nhạy cảm có yêu cầu UV?
6. **Registration:** Enrollment có reauthentication, challenge binding và notification?
7. **Assertion:** Server xác minh type, challenge, origin, RP ID hash, signature, credential và flags?
8. **Key lifecycle:** Public key/credential ID được lưu và revoke riêng; private key được bảo vệ ở authenticator?
9. **Certificate:** CA, chain, hostname, EKU, revocation và private key protection có đầy đủ?
10. **Federation:** acr/amr/AuthnContext được mapping theo hợp đồng với IdP?
11. **Step-up:** Proof gắn subject, session, purpose, resource và TTL?
12. **Session:** Cookie/token có hardening, expiry, rotation và revocation?
13. **Recovery:** Có backup authenticator/recovery flow đủ mạnh, không tạo bypass?
14. **Account lifecycle:** Offboarding và device loss revoke credential/session/token liên quan?
15. **Authorization:** Authentication không tự cấp tenant membership hoặc role?
16. **Operations:** Có audit, monitoring, key rotation, domain migration và support procedure?
17. **Testing:** Đã test lookalike origin, replay, wrong RP ID, missing UV, enrollment hijack và recovery bypass?

## 23. Bài tập tình huống

Một công ty triển khai MFA bằng password + TOTP cho mọi nhân viên. Một nhóm admin thường xuyên bị reverse proxy phishing; attacker lấy được password, TOTP trong thời gian hiệu lực và session cookie. Công ty muốn chuyển sang passkey nhưng dự định dùng chung RP ID cho mọi subdomain, cho phép helpdesk thêm passkey mới chỉ qua email công ty và giữ session cũ sau khi thay authenticator.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** trong MFA hiện tại, domain design, enrollment, recovery và session lifecycle.
2. Thiết kế triển khai WebAuthn cho portal admin với RP ID/origin phù hợp.
3. Quy định khi nào cần user verification và phương thức dự phòng.
4. Thiết kế enrollment passkey có reauthentication, audit và notification.
5. Đề xuất recovery/helpdesk flow không biến email thành đường bypass.
6. Xác định cách xử lý session/token sau khi thay authenticator hoặc nghi compromise.
7. Viết test cho lookalike domain, wrong origin, RP ID mismatch, replay, enrollment hijack và recovery bypass.

**Gợi ý đối chiếu:** TOTP không chống relay; RP ID không nên rộng hơn trust boundary cần thiết; helpdesk cần proofing/dual control; thêm passkey phải step-up; revoke credential và session cũ theo policy; server xác minh đầy đủ assertion và authorization riêng.

## 24. Ghi nhớ

- **Phishing-resistant authenticator** ràng buộc bằng chứng xác thực với đúng RP/origin hoặc kênh được bảo vệ, làm cho việc relay từ domain giả khó hoặc không thể tạo assertion hợp lệ.
- Passkey và security key dựa trên FIDO2/WebAuthn là ví dụ phổ biến; certificate/mTLS có thể chống phishing khi private key và TLS server identity được ràng buộc đúng.
- MFA không tự động đồng nghĩa phishing resistance. SMS OTP, email OTP, TOTP và push thông thường có thể bị phishing hoặc relay.
- WebAuthn cần kiểm tra challenge, origin, RP ID hash, signature, credential ID và user presence/verification theo policy.
- User verification là xác minh local của authenticator; nó không phải identity proofing và không tự cấp quyền.
- Enrollment, recovery và helpdesk phải có mức bảo đảm tương xứng; nếu yếu hơn login, chúng trở thành đường bypass.
- Phishing-resistant login không ngăn mọi session theft, XSS, malware hoặc authorization flaw; session và application vẫn cần bảo vệ riêng.

Một hệ thống chống phishing tốt không chỉ chọn authenticator mạnh. Nó còn bảo đảm **đúng RP được xác thực, đúng credential được đăng ký, đúng assertion được kiểm tra và mọi đường enrollment, recovery, session cùng authorization đều giữ nguyên ranh giới trust**.
