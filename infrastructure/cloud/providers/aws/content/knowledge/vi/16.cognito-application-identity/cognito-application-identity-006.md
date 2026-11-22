# MFA, chính sách mật khẩu và bảo vệ luồng xác thực

> **Chương:** Danh tính ứng dụng với Cognito  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS qua Region/AZ, IAM, VPC, compute, lưu trữ, database, tích hợp và serverless; thực hành chọn dịch vụ, triển khai ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Cognito User Pools**, **Identity Pools**, app clients, IAM, managed login và IdP bên ngoài trong hệ thống xác thực.
2. Thiết kế MFA **OFF / OPTIONAL / ON** theo yêu cầu sản phẩm và luồng onboarding.
3. Giải thích **TOTP, SMS MFA, email MFA**, cũng như sự khác biệt giữa MFA, passwordless OTP và passkeys.
4. Xây dựng **password policy**, chống dùng lại mật khẩu, giới hạn mật khẩu tạm và recovery an toàn.
5. Hiểu Cognito challenge flows, OAuth/OIDC token/session lifecycle và các API quản lý MFA.
6. Đánh giá **threat protection, adaptive authentication, compromised credentials** và **AWS WAF**.
7. Bảo vệ Java API bằng việc kiểm tra JWT, token_use, client_id, scopes và quyền nghiệp vụ.
8. Quan sát lỗi đăng nhập, lập runbook vận hành và dự toán phí Cognito/SMS/SES/WAF.

## 1. Vì sao mật khẩu chưa đủ bảo vệ ứng dụng?

Khách hàng đăng nhập bằng username/password là một lựa chọn phổ biến, nhưng có những nguy cơ:

- Người dùng **dùng lại mật khẩu** đã bị lộ từ website khác.
- Kẻ tấn công thử danh sách email/mật khẩu bằng **credential stuffing**.
- **Phishing** đánh cắp mật khẩu và thậm chí cả mã OTP nếu user nhập vào trang giả.
- **Password reset** không an toàn có thể trở thành đường chiếm tài khoản.
- Người dùng mất thiết bị MFA, SIM hoặc email dẫn tới tự khóa tài khoản nếu thiếu recovery.
- Access/refresh token có thể bị đánh cắp **sau khi** một phiên MFA hợp lệ.

**Multi-factor authentication (MFA)** bổ sung bằng chứng xác thực, nhưng không thay quyền truy cập trong API, bảo vệ token, chống bot hay kiểm soát việc reset mật khẩu.

~~~mermaid
flowchart TB
    U["Người dùng"] --> APP["Web / Mobile App"]
    APP --> COG["Amazon Cognito User Pool"]
    COG --> A["Yếu tố đầu: password / flow phù hợp"]
    A --> Q{"Có yêu cầu MFA?"}
    Q -->|"Có"| M["TOTP / SMS / Email challenge"]
    Q -->|"Không"| T["Cấp token sau khi xác thực"]
    M -->|"Thành công"| T
    M -->|"Sai/hết hạn"| FAIL["Từ chối hoặc thử lại có giới hạn"]
    T --> API["Backend Java / API Gateway"]
    API --> V["Kiểm tra JWT, scope, object permissions"]
    V --> DATA[("RDS / DynamoDB / S3")]
~~~

Đây là luồng cơ bản **local password + MFA**. Với **passkeys/WebAuthn** hoặc **federated IdP**, yêu cầu xác thực có cấu trúc khác.

## 2. User Pool, Identity Pool, app client và IAM

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Cognito User Pool** | Tài khoản người dùng ứng dụng, sign-up, sign-in, MFA, password policy, OIDC/OAuth tokens. | Khách hàng của website thương mại điện tử. |
| **Cognito app client** | Cấu hình auth flows, callback URLs, OAuth scopes, token validity, client secret khi phù hợp. | Một SPA, một mobile app, một server-side app. |
| **Cognito managed login** | Giao diện đăng nhập được Cognito cung cấp. | Trang login và MFA được AWS quản lý. |
| **Cognito Identity Pool** | Cấp **temporary AWS credentials** qua IAM roles khi ứng dụng cần gọi AWS APIs trực tiếp. | Mobile app upload trực tiếp S3 theo quyền giới hạn. |
| **AWS IAM** | Quyền quản trị và quyền workload gọi AWS APIs. | ECS task role truy cập DynamoDB. |
| **External IdP** | Đăng nhập do Entra ID, Okta, social provider, SAML/OIDC xử lý. | Nhân viên sign-in bằng danh tính công ty. |

**User Pool access token không phải AWS access key.** Cognito xác nhận user và phát JWT, còn API backend phải kiểm tra token và áp dụng business authorization. IAM role của backend quản lý quyền AWS resources.

### 2.1. Đặc biệt với federated users

MFA trong Cognito User Pools chủ yếu áp dụng cho **local users**. Với federated SAML/OIDC users, quá trình password/MFA diễn ra tại **upstream IdP**. Cognito không tự thêm một bước local TOTP/SMS sau federated login theo cách local user pool MFA hoạt động.

Bởi vậy bật required MFA trong Cognito không phải phương án thay thế Conditional Access/MFA của Entra ID hoặc Okta.

### 2.2. Public client và confidential client

- **SPA/mobile** là public clients: không nhúng **client secret** trong JavaScript/mobile package; ưu tiên **Authorization Code + PKCE** khi dùng OAuth.
- **Server-side web/BFF** có thể giữ secret nếu thực sự cần và có backend secrets storage an toàn.
- **M2M client credentials** đại diện cho workload, không phải người dùng và không qua user MFA.

## 3. Ba trạng thái MFA của Cognito

Cognito User Pool dùng **MfaConfiguration**:

| Giá trị API | Tác dụng | Lưu ý |
| --- | --- | --- |
| **OFF** | Không yêu cầu user-pool MFA. | Có thể phù hợp passwordless/passkey theo thiết kế riêng. |
| **OPTIONAL** | User có thể đăng ký/bật MFA; những user đã cấu hình có thể được challenge. | Managed login không tự mời tất cả user setup; app cần UX. |
| **ON** | User local password-based flows phải hoàn thành MFA theo điều kiện hỗ trợ. | Phải có onboarding và recovery trước khi bật. |

MFA required giúp tăng bảo mật nhưng có thể **chặn những user chưa có factor** hoặc chưa hoàn tất setup. Để áp dụng an toàn:

1. Kiểm kê app clients/auth flows đang sử dụng.
2. Cấu hình TOTP/SMS/email factor được hỗ trợ.
3. Kiểm thử các account mới, account cũ, user chưa xác minh attribute.
4. Xây dựng màn hình setup và hướng dẫn khi user không có thiết bị.
5. Chuẩn bị kênh recovery độc lập.
6. Có cách đo failure rate và quy trình rollback.

### 3.1. Optional MFA và adaptive authentication

Theo hướng dẫn Cognito, **risk-based adaptive MFA** dùng **MFA = OPTIONAL** kết hợp **threat protection**. Khi rủi ro tăng, Cognito có thể yêu cầu MFA tùy action configured; bắt buộc MFA toàn user pool và MFA theo risk là hai mục tiêu khác nhau.

### 3.2. User MFA preference

Một user có thể có nhiều phương thức khả dụng nhưng có **phương thức đang bật/preferred**. Cách Cognito challenge phụ thuộc pool settings, user attribute, auth flow và user preference. Không suy “bật cả TOTP, SMS, email” nghĩa user phải nhập ba mã mỗi lần.

Ứng dụng tùy biến có thể hỗ trợ user đổi MFA preference bằng **SetUserMFAPreference** và access token hợp lệ. Admin dùng **AdminSetUserMFAPreference** với IAM credentials và audit.

## 4. TOTP, SMS MFA và email MFA

| Phương thức | Ý tưởng | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| **TOTP** | Authenticator app sinh mã thời gian từ secret. | Không cần gửi SMS/email mỗi lần. | Device loss, clock skew, phishing mã. |
| **SMS MFA** | Gửi mã qua điện thoại. | Dễ tiếp cận. | SIM swap, SMS delay, roaming, phí nhắn tin. |
| **Email MFA** | Gửi mã vào hộp thư. | Dễ triển khai trải nghiệm cho người đã có email. | Email compromise, deliverability, phụ thuộc SES/plan. |
| **Passkey với user verification** | WebAuthn dựa trên khóa và xác minh người dùng ở authenticator. | Chống phishing tốt hơn OTP trong cấu hình phù hợp. | Khả năng hỗ trợ browser/device và quy trình recovery. |

### 4.1. TOTP

Các bước chung:

1. User sign-in tới điểm cần setup.
2. Ứng dụng gọi **AssociateSoftwareToken** nhận secret thiết lập.
3. Hiển thị QR code hoặc mã nhập tay trong UI an toàn.
4. User nhập mã do authenticator tạo.
5. App gọi **VerifySoftwareToken**.
6. Khi cần, hoàn tất challenge MFA_SETUP bằng **RespondToAuthChallenge** và đặt MFA preference.

**Không log secret TOTP, mã OTP hay session challenge.** Không dùng QR provisioning làm hình public hoặc ảnh chia sẻ trong ticket.

### 4.2. SMS MFA

SMS gửi qua các kênh Cognito hỗ trợ, như Amazon SNS hoặc **AWS End User Messaging SMS**, tùy cấu hình pool. Cần kiểm tra:

- Sender/origination identity và yêu cầu đăng ký ở từng quốc gia.
- SMS sandbox và số điện thoại được phép nhận.
- Số điện thoại theo định dạng quốc tế như **E.164**.
- Thời gian giao hàng, nhà mạng, retry và quota.
- Phí SMS theo đích, chống abuse gây tốn tiền.

Nếu SMS đến chậm không nên lập tức tắt MFA hoặc bỏ qua challenge. App phải cho retry trong giới hạn và hiển thị hướng dẫn fallback/recovery.

### 4.3. Email MFA

**Email MFA yêu cầu Cognito Essentials hoặc Plus và Amazon SES resources do bạn cấu hình**. Kiểm tra SES sender identity, domain verification, quota, Region và email delivery logs. Gói thấp hơn không mặc định có tính năng này.

Không nhầm **email MFA** (email là yếu tố thứ hai sau password) với **email OTP passwordless** (email là yếu tố đầu).

### 4.4. MFA và phishing

TOTP/SMS/email OTP vẫn có nguy cơ người dùng nhập mã vào website giả. Với rủi ro cao, đánh giá **WebAuthn/passkeys có user verification** vì origin binding giúp tăng khả năng chống phishing. Tuy nhiên cần hiểu ràng buộc của Cognito WebAuthn: passkey không dùng như yếu tố thứ hai sau password theo cơ chế hỗ trợ hiện hành.

## 5. TOTP challenge flow và các API

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant C as Cognito
    participant T as Authenticator
    U->>A: Username + password
    A->>C: InitiateAuth
    C-->>A: MFA_SETUP / challenge tương ứng
    A->>C: AssociateSoftwareToken
    C-->>A: SecretCode
    A-->>U: Hiển thị secret / QR an toàn
    U->>T: Thêm tài khoản
    T-->>U: TOTP code
    U->>A: Nhập mã
    A->>C: VerifySoftwareToken
    C-->>A: SUCCESS / Session
    A->>C: RespondToAuthChallenge nếu flow yêu cầu
    C-->>A: AuthenticationResult khi hoàn tất
~~~

### 5.1. Phân biệt các API

| API | Vai trò |
| --- | --- |
| **InitiateAuth / AdminInitiateAuth** | Bắt đầu authentication; trả tokens hoặc ChallengeName + Session. |
| **RespondToAuthChallenge / AdminRespondToAuthChallenge** | Trả lời SMS/TOTP/email/password challenge. |
| **AssociateSoftwareToken** | Đăng ký secret TOTP; chưa đồng nghĩa setup thành công. |
| **VerifySoftwareToken** | Xác minh TOTP được đăng ký. |
| **SetUserMFAPreference** | User quản lý preferred factor qua access token. |
| **AdminSetUserMFAPreference** | Admin thay MFA preferences qua IAM credentials. |
| **GetUser / AdminGetUser** | Đọc thông tin người dùng theo mô hình quyền phù hợp. |

Một response minh họa:

~~~json
{
  "ChallengeName": "SOFTWARE_TOKEN_MFA",
  "Session": "EXAMPLE_TEMPORARY_SESSION",
  "ChallengeParameters": {
    "USER_ID_FOR_SRP": "example-user"
  }
}
~~~

Đây là **dữ liệu giả định**, không chứa credentials thực. App phải đọc **ChallengeName** được Cognito trả về; không mặc định lúc nào cũng là SOFTWARE_TOKEN_MFA.

Các challenge names khác có thể gặp: **SMS_MFA**, **EMAIL_OTP**, **MFA_SETUP**, **SELECT_MFA_TYPE**, **NEW_PASSWORD_REQUIRED**. Tùy luồng/feature, challenge và response parameters khác nhau; cần đối chiếu tài liệu SDK/Cognito tại thời điểm triển khai.

### 5.2. Bắt buộc tách trạng thái “còn challenge” và “đăng nhập thành công”

Nếu InitiateAuth trả ChallengeName/Session nhưng **chưa có AuthenticationResult**, không tạo session ứng dụng hoặc coi user đã xác thực. Chỉ sau khi hoàn tất challenge và token được phát hành hợp lệ mới cho phép backend kiểm tra quyền.

### 5.3. Các lỗi thường gặp

- Mã TOTP hết hạn, điện thoại sai giờ.
- User đăng ký thiết bị khác hoặc mất secret.
- Session auth challenge hết hiệu lực.
- OTP bị nhập sai nhiều lần và bị Cognito giới hạn.
- User thiếu verified attribute thích hợp.
- Pool bật yêu cầu MFA nhưng app client chưa hỗ trợ màn hình MFA_SETUP.

Không xây “bypass MFA sau ba lần lỗi” để thuận tiện cho support. Dùng quy trình admin-assisted recovery có xác minh danh tính.

## 6. MFA khác passwordless OTP và passkeys

| Kiểu đăng nhập | Yếu tố đầu | Yếu tố bổ sung | Điểm khác |
| --- | --- | --- | --- |
| Password + TOTP | Password | TOTP app | Hai yếu tố riêng. |
| Password + SMS/email MFA | Password | SMS/email OTP | MFA theo kênh thông điệp. |
| Passwordless email OTP | Email OTP | Không nhất thiết có factor khác | OTP là **first factor**. |
| Passwordless SMS OTP | SMS OTP | Không nhất thiết có factor khác | Không tự thành MFA chỉ vì có mã. |
| Passkey/WebAuthn | Authenticator + user verification theo cấu hình | Không phải password + passkey thứ hai | Có thể đáp ứng MFA trong một lần xác minh khi được hỗ trợ. |

### 6.1. Tương thích với MFA required

Theo tài liệu AWS hiện hành, không thể đặt **MFA required** trong một pool cho phép **EMAIL_OTP hoặc SMS_OTP** làm passwordless first auth factors. Khi MFA required, choice-based sign-in bị giới hạn ở các password factors phù hợp, **ngoại trừ WebAuthn với cấu hình MFA bằng user verification**.

### 6.2. WebAuthn/passkey có thể đáp ứng MFA theo cấu hình mới

Với **WebAuthnConfiguration.FactorConfiguration = MULTI_FACTOR_WITH_USER_VERIFICATION**, một passkey có user verification có thể đáp ứng yêu cầu nhiều yếu tố ở **first-factor**, trong những trường hợp hỗ trợ. Passkey **không** được dùng như challenge bổ sung thứ hai sau password sign-in trong Cognito.

Điểm cần test: feature plan Essentials/Plus, app clients, browser/OS, user verification, relying party domain, recovery khi mất thiết bị và các trạng thái required/optional.

### 6.3. Không cấu hình một yếu tố làm cả hai

Một user chỉ có email mà ứng dụng dùng email OTP passwordless, sau đó cũng muốn dùng email làm MFA thứ hai: **đó không phải hai yếu tố độc lập**. Cognito có logic ngăn những tổ hợp MFA/first factors không phù hợp; ứng dụng cần chọn mô hình rõ ràng từ đầu.

## 7. Chính sách mật khẩu trong User Pool

Các thuộc tính phổ biến của **Policies.PasswordPolicy**:

- **MinimumLength**.
- **RequireUppercase**, **RequireLowercase**.
- **RequireNumbers**, **RequireSymbols**.
- **TemporaryPasswordValidityDays**.
- **PasswordHistorySize** khi gói hỗ trợ.

~~~json
{
  "Policies": {
    "PasswordPolicy": {
      "MinimumLength": 14,
      "RequireUppercase": true,
      "RequireLowercase": true,
      "RequireNumbers": true,
      "RequireSymbols": true,
      "TemporaryPasswordValidityDays": 7,
      "PasswordHistorySize": 10
    }
  }
}
~~~

Đây là **fragment cấu hình ví dụ**; không phải request sẵn để gửi lên API.

### 7.1. Password policy mạnh không chỉ là ký tự đặc biệt

Một mật khẩu dài nhưng dùng lại tại nhiều dịch vụ vẫn có rủi ro lớn. Khuyến nghị:

1. Khuyến khích passphrase dài, độc nhất và password manager.
2. Cho phép paste/autofill trong form đăng nhập.
3. Dùng MFA phù hợp với rủi ro.
4. Tránh hiện thông báo tiết lộ user existence trong reset/login.
5. Không log mật khẩu hoặc truyền qua HTTP plaintext.
6. Với gói **Plus**, xem compromised-credentials detection khi auth flows hỗ trợ.

### 7.2. Password history

**Essentials/Plus** hỗ trợ ngăn dùng lại password, với giới hạn hiện hành có thể ngăn tái sử dụng mật khẩu hiện tại và tối đa 23 mật khẩu trước đó (tổng tối đa 24 theo tài liệu). Không đồng nhất policy chống reuse với kiểm tra password đã lộ trên Internet; hai chức năng khác nhau.

### 7.3. Temporary password

**TemporaryPasswordValidityDays** áp dụng cho mật khẩu tạm được admin đặt, thường liên quan **AdminCreateUser** và challenge **NEW_PASSWORD_REQUIRED**.

Hết hạn mật khẩu tạm không đồng nghĩa tất cả mật khẩu vĩnh viễn của user tự hết hạn theo cùng thời gian. Support có thể phải cấp/reset lại mật khẩu tạm theo luồng admin được phép.

### 7.4. Federated users

Người dùng đã xác thực tại upstream IdP không sử dụng password policy của Cognito như một chính sách bắt buộc cho mật khẩu tại IdP. Quản lý password/MFA của họ tại IdP và thiết kế federation trust phù hợp.

## 8. Account recovery: không dùng lại đúng kênh MFA

Đây là một điểm bảo mật và UX rất quan trọng. **Cognito không gửi mã self-service password reset đến cùng email hoặc số điện thoại được user dùng làm MFA preferred**.

| Preferred MFA | Kênh khôi phục nên có | Tình huống rủi ro |
| --- | --- | --- |
| **SMS** | Verified email. | User chỉ đăng ký phone, chưa có email. |
| **Email** | Verified phone/SMS. | User chỉ đăng ký email hoặc bị mất số. |
| **TOTP** | Verified email/phone theo thiết kế. | Mất cả thiết bị TOTP và kênh liên hệ. |
| **Passkey** | Credentials khác/khôi phục được thiết kế riêng. | Thiết bị bị mất, re-enrollment bị lợi dụng. |

### 8.1. AccountRecoverySetting

~~~json
{
  "AccountRecoverySetting": {
    "RecoveryMechanisms": [
      {
        "Name": "verified_email",
        "Priority": 1
      },
      {
        "Name": "verified_phone_number",
        "Priority": 2
      }
    ]
  }
}
~~~

**Priority 1** là cao nhất. Cognito vẫn phải chọn kênh hợp lệ tùy MFA preference và verified attributes; không bảo đảm email sẽ được dùng trong mọi tài khoản nếu email đang là MFA.

Chỉ cho phép admin reset:

~~~json
{
  "AccountRecoverySetting": {
    "RecoveryMechanisms": [
      {
        "Name": "admin_only",
        "Priority": 1
      }
    ]
  }
}
~~~

Không trộn **admin_only** với các kênh self-service khác.

### 8.2. Self-service password reset

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant APP as Ứng dụng
    participant C as Cognito
    U->>APP: Quên mật khẩu
    APP->>C: ForgotPassword
    C-->>U: Gửi code qua recovery channel đủ điều kiện
    U->>APP: Code + password mới
    APP->>C: ConfirmForgotPassword
    C-->>APP: Thành công / lỗi
    APP-->>U: Đăng nhập lại
~~~

Không mặc định mọi người dùng đều có đủ kênh để self-service reset. Có thể gặp **InvalidParameterException** khi thiếu recovery channel hợp lệ. Quy trình hỗ trợ cần yêu cầu xác minh danh tính thực tế, không đơn giản dựa vào email được nhập trên form.

### 8.3. Mất điện thoại: admin-assisted recovery

1. Xác thực danh tính chủ tài khoản qua kênh bảo mật được tổ chức phê duyệt.
2. Xem các dấu hiệu account takeover trước khi thay MFA.
3. Admin có IAM quyền tối thiểu thực hiện thay đổi user attributes/MFA settings cần thiết.
4. Ghi audit ai thay đổi, lý do và thời gian.
5. Hướng dẫn user đăng ký factor mới.
6. Thu hồi các sessions/tokens nếu nghi đã bị chiếm đoạt.

**Không tạo API công khai cho phép vô hiệu MFA chỉ bằng một email hoặc SMS code dễ bị chiếm đoạt.**

## 9. OAuth/OIDC và Cognito tokens

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant APP as Web/BFF
    participant C as Cognito managed login
    participant API as Java backend
    B->>APP: Đăng nhập
    APP-->>B: Redirect authorize + state + nonce + PKCE
    B->>C: Password/MFA hoặc passkey phù hợp
    C-->>B: Authorization code tới callback
    B->>APP: Callback code và state
    APP->>C: Token endpoint với code_verifier / client auth
    C-->>APP: Access/ID/Refresh tokens
    APP->>API: Bearer access token / session phù hợp
    API-->>APP: Response sau JWT + authorization
~~~

### 9.1. Các token

| Token | Mục đích | Không được làm |
| --- | --- | --- |
| **ID token** | Chứa thông tin user theo OIDC, dùng ở client phù hợp. | Dùng thay access token làm bảo đảm quyền API. |
| **Access token** | Dùng truy cập resource/API với scopes/claims hợp lệ. | Coi là quyền vĩnh viễn hoặc AWS IAM credentials. |
| **Refresh token** | Nhận tokens mới trong thời gian session còn hợp lệ. | Gửi vào URL, frontend logs, analytics, hoặc API nghiệp vụ thường xuyên. |

Backend phải xác minh **signature/JWKS, issuer, expiry, token_use**, token binding theo app client (**client_id** hoặc audience theo token type), scopes/groups và quyền dữ liệu/tenant.

### 9.2. Authentication response và challenge

~~~json
{
  "ChallengeName": "SMS_MFA",
  "Session": "EXAMPLE_SESSION_NOT_REAL",
  "ChallengeParameters": {
    "CODE_DELIVERY_DELIVERY_MEDIUM": "SMS"
  }
}
~~~

Khi nhận **ChallengeName**, app phải hoàn tất challenge. Chưa có AuthenticationResult nghĩa user chưa hoàn thành sign-in.

Một response thành công có thể trả:

~~~json
{
  "AuthenticationResult": {
    "AccessToken": "EXAMPLE_ACCESS_JWT",
    "IdToken": "EXAMPLE_ID_JWT",
    "RefreshToken": "EXAMPLE_REFRESH",
    "TokenType": "Bearer",
    "ExpiresIn": 3600
  }
}
~~~

Những tokens trong ví dụ là placeholder. Không đưa token thật vào bài viết, ticket hoặc CloudWatch logs.

### 9.3. OAuth protections

- Dùng HTTPS, callback URL allowlist chính xác.
- **state** chống CSRF/login swapping; **nonce** cho OIDC khi cần.
- **PKCE** cho public clients.
- Không đặt client secret trong SPA/mobile.
- Tránh open redirect, không chấp nhận callback wildcard thiếu kiểm soát.
- Trong browser, ưu tiên token/session storage ít bị XSS; BFF có thể dùng HttpOnly/Secure/SameSite cookies theo thiết kế CSRF.
- Access token phải có scope đúng, backend phải kiểm tra object-level authorization, không chỉ Cognito groups.

## 10. Refresh token rotation, revocation và logout

### 10.1. Refresh token rotation

~~~json
{
  "RefreshTokenRotation": {
    "Feature": "ENABLED",
    "RetryGracePeriodSeconds": 10
  }
}
~~~

Đây là fragment cấu hình app client. Khi bật refresh token rotation:

- Mỗi refresh thành công có thể nhận refresh token mới.
- **REFRESH_TOKEN_AUTH** không dùng với app clients đã bật rotation; dùng **GetTokensFromRefreshToken** hoặc OAuth token endpoint theo luồng hỗ trợ.
- Token mới chỉ còn **phần thời hạn chưa hết** của refresh window ban đầu, không kéo dài vô hạn.
- Cần xử lý race giữa nhiều tabs và retries, giữ token bảo mật.
- Grace period nhỏ cho phép retry hợp lý nhưng cũng có rủi ro nếu token bị lộ.

### 10.2. Thu hồi token

Cognito có các cơ chế như **RevokeToken**, **GlobalSignOut**, **AdminUserGlobalSignOut** hoặc tính năng session management theo feature plan.

**Cảnh báo quan trọng:** JWT self-contained vẫn có thể qua kiểm tra **chữ ký + exp** trong một custom backend dù token đã bị thu hồi. Cognito APIs nhận token có thể từ chối token revoked, nhưng Java resource server cần có cơ chế kiểm soát session/revocation riêng nếu cần logout hiệu lực ngay trên tất cả API.

Managed login có cookie phiên tại Cognito. Sign-out ở API và xóa managed login session cookie là hai khía cạnh cần điều phối; không mặc định revoke refresh token luôn xóa browser cookie ở mọi IdP/hosted login.

## 11. Phân biệt xác thực và phân quyền

Một người dùng có thể đăng nhập đúng và vượt MFA nhưng **không có quyền xem đơn hàng của người khác**.

- **Authentication:** user là ai, đã hoàn tất yêu cầu sign-in chưa?
- **Authorization:** user được thao tác trên resource/tenant nào?
- **IAM authorization:** AWS workload/role có quyền gọi dịch vụ AWS nào?
- **Data authorization:** bản ghi RDS/DynamoDB/S3 object có thuộc user/tenant đó không?

Ví dụ API **GET /orders/987** không chỉ nhìn claim **cognito:groups = customer**, mà còn phải xác nhận order 987 **thuộc current user** hoặc quyền agent hợp lệ.

~~~mermaid
flowchart LR
    TOK["Cognito access token"] --> JWT["Validate iss/exp/signature/token_use/client_id"]
    JWT --> SCOPE{"Scope đủ?"}
    SCOPE -->|"Không"| DENY["403 Forbidden"]
    SCOPE -->|"Có"| OBJ{"Order thuộc tenant/user?"}
    OBJ -->|"Không"| DENY
    OBJ -->|"Có"| DB["Đọc dữ liệu qua IAM backend role"]
~~~

**MFA thành công không cho phép backend bỏ qua authorization**. IAM role của ECS/Lambda/EC2 có thể cho code gọi DynamoDB, nhưng ứng dụng vẫn phải bảo vệ từng tenant record.

## 12. Threat protection, adaptive authentication và credential risk

**Threat protection** (trước đây được gọi bằng tên advanced security features) thuộc **Cognito Plus feature plan**.

| Thành phần | Mục tiêu | Phạm vi |
| --- | --- | --- |
| **Compromised credentials** | Phát hiện mật khẩu bị lộ/phổ biến ở flows được Cognito quan sát. | Phụ thuộc kiểu sign-in/reset, không đồng nhất SRP. |
| **Adaptive authentication** | Đánh giá risk từ IP, device, user agent, vị trí và tín hiệu khác. | Local username/password/SRP/custom flows theo khả năng hỗ trợ. |
| **User activity logs** | Điều tra sự kiện authentication, risk assessments. | Cần bật, export và bảo vệ dữ liệu hợp lý. |
| **IP allow/block exceptions** | Điều khiển lựa chọn traffic theo IP/CIDR trong full-function mode. | Có giới hạn với federated sign-in, refresh và risk logic. |

### 12.1. Compromised credentials không hoạt động như nhau ở mọi flow

- Với **USER_PASSWORD_AUTH** và **ADMIN_USER_PASSWORD_AUTH**, Cognito nhận password và có thể đánh giá compromised credentials theo tính năng.
- Với **USER_SRP_AUTH**, Cognito không nhận plaintext password trực tiếp nên compromised-credentials detection **không thể thực hiện giống** password auth lúc sign-in.
- Với **federated login**, chính IdP xử lý mật khẩu/MFA.
- Với **M2M client credentials**, không có user password để feature này đánh giá.

Đừng bật tính năng rồi tuyên bố tất cả password trong mọi auth flow đều đã được kiểm tra bị lộ.

### 12.2. Adaptive MFA theo mức rủi ro

Cognito có thể áp hành động **Allow/Audit, Require MFA hoặc Block**, dựa trên risk level và cấu hình. Nếu app dùng **MFA OPTIONAL**, hệ thống có thể yêu cầu yếu tố bổ sung khi risk tăng.

Một flow tham khảo:

~~~mermaid
flowchart LR
    SIGNIN["User sign-in"] --> SCORE["Threat protection risk scoring"]
    SCORE --> LOW["Low risk -> Allow/Audit"]
    SCORE --> MID["Medium risk -> MFA theo policy"]
    SCORE --> HIGH["High risk -> Block/notification"]
    MID --> TOK["Tokens khi challenge thành công"]
    LOW --> TOK
~~~

Đây là **policy minh họa**, không phải mặc định AWS. Các risk responses và điều kiện phụ thuộc cấu hình của pool/app client.

### 12.3. Audit trước khi enforce

AWS khuyến nghị dùng **Audit-only** trong một giai đoạn để thu metrics, xem false positives và hành vi thực tế; tài liệu nêu thực hành theo dõi tối thiểu khoảng **hai tuần** trước full-function. Kế hoạch:

1. Bật Plus/threat protection trong môi trường thử.
2. Bật Audit và theo dõi sign-in risk logs.
3. Phân tích shared IP/NAT, VPN, vị trí thay đổi, thiết bị hợp lệ.
4. Thiết kế mức xử lý risk và notification.
5. Thử với tài khoản thật có consent và kịch bản mạng khác.
6. Chuyển Full-function có rollback/monitoring và support.

**Threat protection không phải rate limiter chống DDoS.** Nó đánh giá từng request và có thể trả risk score; cần AWS WAF/rate controls khi bị bot flood.

## 13. AWS WAF, bot controls và chống enumeration

Cognito User Pool hỗ trợ tích hợp **AWS WAF web ACL** cho những endpoint/user pool phù hợp. Các rule có thể:

- Hạn chế số requests theo IP/dải IP hoặc key được WAF hỗ trợ.
- Chặn nguồn xấu đã biết qua IP sets/managed rules.
- Áp CAPTCHA/challenge/bot controls nếu tính năng và luồng hỗ trợ.
- Ghi logs và phân tích requests bị chặn.

| Kiểu tấn công | Lớp bảo vệ phù hợp |
| --- | --- |
| Credential stuffing số lượng lớn | WAF rate/bot rules, Cognito MFA, threat protection. |
| Mật khẩu bị lộ | Compromised credentials Plus, password reset, MFA. |
| Sign-in vị trí lạ | Adaptive risk, MFA/challenge/notification. |
| User enumeration | PreventUserExistenceErrors khi flow hỗ trợ và thông điệp UX nhất quán. |
| User đăng nhập thành công nhưng đọc sai tenant | Java authorization và data access checks. |
| Spam SMS/email OTP | Throttling, WAF, messaging cost alerts và OTP retries limits. |

Không đặt rate limits quá chặt cho người dùng ở chung **carrier NAT/company proxy**, tránh false positives. Bật WAF không có nghĩa tự động chặn mọi cuộc tấn công phân tán; cần review metrics và điều chỉnh.

### 13.1. Không tiết lộ sự tồn tại tài khoản

Với login/reset, những thông điệp như “Email này chưa từng đăng ký” có thể giúp attacker thu thập usernames. Cấu hình **PreventUserExistenceErrors** ở app client theo khả năng hỗ trợ và thiết kế lời nhắn tổng quát (chẳng hạn “Nếu thông tin hợp lệ, chúng tôi sẽ gửi hướng dẫn”).

Phải duy trì kênh hỗ trợ người dùng hợp lệ, không để lỗi chung chung khiến user không có cách sửa thông tin đăng ký.

## 14. Kiến trúc tham khảo cho ứng dụng Java/AWS

~~~mermaid
flowchart TB
    U["Browser / Mobile App"] --> WAF["Cognito managed login + WAF"]
    WAF --> C["Cognito User Pool: password / MFA / risk"]
    C --> TOK["OIDC / OAuth tokens"]
    TOK --> API["API Gateway / ALB"]
    API --> JAVA["Spring Boot API hoặc Lambda Java"]
    JAVA --> VALID["JWT signature + iss + token_use + client_id + scopes"]
    VALID --> AUTH["RBAC / ABAC / object-level authorization"]
    AUTH --> DB[("DynamoDB / RDS")]
    JAVA -.-> IAM["Task / Lambda execution IAM role"]
    C -.-> LOG["CloudTrail, risk logs, CloudWatch"]
~~~

**Tách ba lớp quyền:**

1. User Pool xác thực và cấp token.
2. Backend xác minh token và quyết định user được làm gì.
3. Backend IAM role cho phép thực thi các thao tác AWS tương ứng.

### 14.1. App clients theo môi trường

Tách **dev/staging/prod**, sử dụng callback URLs và domain riêng, không dùng user thật của production để gửi OTP test. Nếu quy trình yêu cầu user pool chung, phải quản lý ownership, MFA rollout và IAM rất chặt.

### 14.2. Bảo mật OTP/secret

Không ghi vào logs:

- Password, refresh token, access/ID token nguyên văn.
- TOTP secret, QR provisioning URI.
- SMS/email OTP code hoặc Session authentication value.
- Client secret, IAM access keys.
- Nội dung user attributes không cần thiết như phone/email đầy đủ.

Ghi **correlation ID, error type, app client ID rút gọn, auth flow, challenge type, duration, status** theo data classification để điều tra mà không lộ credentials.

## 15. Mẫu chính sách triển khai theo mức rủi ro

| Nhóm tài khoản | Password policy | MFA | Threat/risk | Recovery |
| --- | --- | --- | --- | --- |
| Khách hàng phổ thông | Password mạnh, khuyến khích password manager. | OPTIONAL, hỗ trợ TOTP và phương thức phù hợp. | WAF + audit; Plus risk nếu có ngân sách/lý do. | Verified email/phone khác factor hoặc support. |
| Nhân viên chăm sóc khách hàng | Password và SSO policy công ty. | MFA bắt buộc tại IdP hoặc User Pool local theo mô hình. | Risk-based sign-in và audit. | Helpdesk xác minh danh tính. |
| Admin quyền cao | Chính sách mạnh và session lifetime ngắn phù hợp. | Ưu tiên phishing-resistant MFA/SSO nếu khả dụng. | Block risky sessions, alert nhạy cảm. | Admin process 2 người kiểm soát khi cần. |
| Machine-to-machine | Không dùng user password khi không cần. | Không áp user MFA. | OAuth client credentials, secret rotation, IAM/WAF phù hợp. | Rotation/revocation credential. |

**Không có một cấu hình duy nhất tối ưu cho mọi hệ thống.** Phải cân bằng bảo mật, khả năng tiếp cận, điều kiện người dùng, chi phí và khả năng hỗ trợ.

## 16. Java Spring Boot: xác minh access token đúng cách

Một Java API không nên tin JWT chỉ vì chuỗi nhìn giống ba phần được ngăn bởi dấu chấm. API phải xác minh token từ **Cognito User Pool dự kiến**, thời hạn, loại token, app client và permissions.

### 16.1. Tại sao ID token không dùng thay access token?

Cognito User Pool phát ID token và access token với mục đích khác nhau:

- **ID token:** phục vụ xác nhận danh tính cho ứng dụng client; thường có **aud** chỉ app client.
- **Access token:** phục vụ authorization tới resource/API; trong mô hình Cognito phổ biến có **token_use = access**, claim **client_id** và scope.
- **Refresh token:** dùng yêu cầu token mới; không đưa tới protected API như bearer access token.

Bài toán thường gặp: backend Java chỉ check chữ ký JWT nhưng không check token_use nên vô tình nhận cả ID token và access token. Một token hợp lệ về mặt chữ ký **không mặc nhiên hợp lệ để gọi mọi API**.

### 16.2. Dependency cần thiết

Với Spring Boot 3.x và Spring Security 6.x, backend có thể dùng các starter:

~~~xml
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
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
~~~

Phần này là snippet Maven của một project Spring Boot, không phải POM đầy đủ. Kiểm tra version dependencies và compatibility đúng project.

### 16.3. Security configuration minh họa

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CognitoSecurityConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = System.getenv("COGNITO_ISSUER");
        String clientId = System.getenv("COGNITO_CLIENT_ID");

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> appTokenValidator = jwt -> {
            boolean expectedToken = "access".equals(
                jwt.getClaimAsString("token_use"));
            boolean expectedClient = clientId.equals(
                jwt.getClaimAsString("client_id"));

            if (expectedToken && expectedClient) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected token use or app client",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                appTokenValidator
            )
        );
        return decoder;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders/read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Đây là ví dụ học tập**, không phải mã production hoàn chỉnh. Nó cho thấy:

1. Lấy **issuer** và **app client ID** từ environment/config tin cậy.
2. Dùng JWKS của issuer để kiểm tra signature.
3. Dùng validators chuẩn kiểm tra expiry, not-before, issuer theo phiên bản Spring Security.
4. **Tự kiểm tra token_use và client_id** cho access tokens của Cognito.
5. Kiểm tra **scope** ở API endpoint.
6. Tiếp tục kiểm tra **object-level authorization** ở service/data layer.

Ví dụ environment:

~~~text
COGNITO_ISSUER=https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE
COGNITO_CLIENT_ID=examplepublicclientid
~~~

Các giá trị là placeholder; không có credentials thật. Khi sử dụng token từ nhiều app clients, thay phép so sánh clientId đơn bằng **allowlist được quản lý** theo mô hình trust. Nếu API dùng **client_credentials** từ confidential clients, kiểm tra scopes/audience/client binding theo token thực tế.

### 16.4. Scope authorization khác business authorization

Ví dụ **SCOPE_orders/read** chỉ nói token có quyền gọi nhóm API tương ứng. Không cho phép đọc mọi đơn hàng. Endpoint **GET /api/orders/123** còn phải:

- Trích user identity từ access token hợp lệ, thường **sub**.
- Tìm order 123 trong database.
- Kiểm tra owner/tenant hoặc vai trò được ủy quyền.
- Chỉ trả bản ghi khi quyền nghiệp vụ đúng.

**MFA không cấp quyền “xem mọi đơn hàng”; IAM role của Java backend cũng không cấp user permission trên dữ liệu.**

### 16.5. JWT key rotation và JWKS caching

Cognito có thể xoay keys để ký JWT. Thư viện JWT resource server nên tải/cached **JWKS** theo cơ chế đáng tin cậy, hỗ trợ key ID mới thay vì hard-code một public key mãi mãi. Cần xử lý outage/network tới JWKS endpoint, caching và timeout an toàn; không bỏ signature validation vì key lookup lỗi.

**Không dùng JWT decode không xác minh chữ ký** trong production. Giải mã Base64 chỉ giúp xem payload, không xác nhận token được Cognito cấp.

## 17. AWS CLI chỉ đọc để khảo sát Cognito

Các lệnh sau **không tạo, sửa, xóa user pool, reset password, gửi OTP hoặc invoke auth**. Cần AWS CLI với IAM read permissions và đúng Region/account. Không dùng tài khoản production của người khác nếu không được phép truy cập.

### 17.1. Xác nhận danh tính AWS

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Không nhầm **AWS caller identity** của CLI với **Cognito user** đang đăng nhập website; đây là hai hệ thống danh tính khác nhau.

### 17.2. Liệt kê user pools

~~~bash
aws cognito-idp list-user-pools \
  --max-results 20 \
  --region ap-southeast-1 \
  --query "UserPools[].{Id:Id,Name:Name,Created:CreationDate}"
~~~

Với môi trường có nhiều pools, cần xử lý pagination. Một User Pool được định danh bởi Region + UserPoolId; nếu CLI đang dùng sai Region, bạn có thể không tìm thấy pool dù pool tồn tại.

### 17.3. Xem MFA, password policy, recovery, feature plan

~~~bash
aws cognito-idp describe-user-pool \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1 \
  --query "UserPool.{Id:Id,Name:Name,MFA:MfaConfiguration,Policies:Policies,Recovery:AccountRecoverySetting,Tier:UserPoolTier,AddOns:UserPoolAddOns,Status:Status}"

aws cognito-idp get-user-pool-mfa-config \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

Các trường cần xem:

| Trường | Ý nghĩa |
| --- | --- |
| **MfaConfiguration** | OFF, OPTIONAL, ON. |
| **SoftwareTokenMfaConfiguration** | Trạng thái TOTP của pool. |
| **SmsMfaConfiguration** | Cấu hình SMS MFA theo loại pool. |
| **EmailMfaConfiguration** | Cấu hình email MFA khi feature plan hỗ trợ. |
| **WebAuthnConfiguration** | Các tùy chọn passkey/user verification nếu có. |
| **PasswordPolicy** | Độ dài, yêu cầu ký tự, expiry password tạm, history. |
| **AccountRecoverySetting** | Kênh ưu tiên/điều kiện recovery. |
| **UserPoolTier** | Feature plan như Lite/Essentials/Plus theo dữ liệu returned. |

Chú ý lệnh **describe-user-pool** có thể trả thêm email/SMS config, Lambda trigger ARNs và resource details. Khi chia sẻ output trong ticket phải loại bỏ thông tin nội bộ không cần.

### 17.4. Xem app clients và xác định auth flows

~~~bash
aws cognito-idp list-user-pool-clients \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --max-results 20 \
  --region ap-southeast-1

aws cognito-idp describe-user-pool-client \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --client-id EXAMPLECLIENTID \
  --region ap-southeast-1 \
  --query "UserPoolClient.{Name:ClientName,Id:ClientId,Flows:ExplicitAuthFlows,OAuthFlows:AllowedOAuthFlows,CallbackURLs:CallbackURLs,PreventExistence:PreventUserExistenceErrors,RefreshRotation:RefreshTokenRotation,AccessTTL:AccessTokenValidity,IdTTL:IdTokenValidity}"
~~~

**Không in toàn bộ app client details vào nơi công khai**, vì confidential app client có thể chứa thông tin cần bảo vệ như client secret. Chọn query lọc trường là thói quen tốt.

### 17.5. Xem threat protection/risk configuration

~~~bash
aws cognito-idp describe-risk-configuration \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

Lệnh này có thể yêu cầu Cognito Plus/threat protection hoặc quyền phù hợp để xem đầy đủ cấu hình. **AccessDenied** không có nghĩa feature tự động bị tắt; kiểm tra IAM/plan/Region và error code thật.

### 17.6. Xem WAF liên kết với user pool

~~~bash
aws wafv2 get-web-acl-for-resource \
  --resource-arn arn:aws:cognito-idp:ap-southeast-1:111122223333:userpool/ap-southeast-1_EXAMPLE \
  --region ap-southeast-1
~~~

Cần IAM quyền AWS WAF/Cognito và có thể phụ thuộc Region/web ACL associations thực tế. Nếu không có WAF, phải phân biệt “chưa liên kết” với “caller không có quyền xem”.

### 17.7. Đọc user MFA preference có hạn chế riêng

Quản trị viên được ủy quyền có thể dùng **AdminGetUser** để kiểm tra user status và MFA settings. Nhưng kết quả có thể chứa **email, phone, attributes/PII**. Không chạy hàng loạt hoặc dán nguyên dữ liệu người dùng vào log/ticket. Mọi truy vấn admin phải được ghi nhận với lý do nghiệp vụ và kiểm soát quyền.

### 17.8. Những lệnh cố ý không chạy trong bài

Các thao tác sau **làm thay đổi bảo mật hoặc dữ liệu** và không nằm trong bài đọc cấu hình:

~~~text
aws cognito-idp set-user-pool-mfa-config
aws cognito-idp update-user-pool
aws cognito-idp admin-set-user-mfa-preference
aws cognito-idp admin-reset-user-password
aws cognito-idp admin-disable-user
aws cognito-idp update-user-pool-client
~~~

Đây là tên lệnh để nhận diện thao tác có tác dụng thay đổi; **không thực thi** khi chỉ làm nhiệm vụ kiểm tra. Với production, dùng IaC có review, migration plan, kiểm thử rollback và audit.

## 18. Giám sát và audit xác thực

### 18.1. Quan sát ở đúng lớp

| Lớp | Tín hiệu quan trọng | Ý nghĩa |
| --- | --- | --- |
| Cognito sign-in | Thành công/thất bại/challenge outcomes theo event logs hỗ trợ. | Người dùng có đăng nhập được không? |
| Threat protection (Plus) | Risk level, compromised credentials, blocked/required MFA, event feedback. | Có tấn công/account takeover không? |
| SES/SMS delivery | Tin nhắn gửi/chậm/bị từ chối, bounce, sandbox, quota. | User có nhận code không? |
| WAF | Allowed/blocked/challenged requests, rate patterns. | Bot/credential stuffing hoặc false positives? |
| CloudTrail | Thay đổi cấu hình pool/app client, IAM/admin actions trong phạm vi logging. | Ai thay đổi chính sách, MFA hoặc user? |
| Java API | JWT validation failures, 401/403, object-level authorization outcomes. | Token hợp lệ nhưng quyền API có đúng không? |
| Cost Explorer/Budgets | MAU/tier, SMS/email/WAF/CloudWatch/Lambda trigger usage. | Chi phí tăng do người dùng hay bị abuse? |

**CloudTrail không phải bản ghi mặc định đầy đủ mọi lần user nhập OTP hoặc mọi password**. Không log password/OTP/token để bù thiếu audit. Chọn cơ chế user activity logs/threat protection logs khi tính năng hỗ trợ và đặt retention/IAM phù hợp.

### 18.2. KPI/SLO gợi ý

- **Sign-in success rate** trên số authentication attempts hợp lệ.
- **MFA completion rate** theo challenge type, tách lỗi của user và delivery system.
- **Password recovery success rate**: người dùng hoàn thành reset mà không cần escalated support.
- **Time to sign in**: p50/p95 từ lúc bắt đầu đến lúc có session.
- **Suspicious sign-in rate** theo risk level và kênh, không log PII không cần.
- **OTP delivery time**, undelivered/bounced codes.
- **Lockout/helpdesk tickets** sau khi tăng MFA required.
- **Cost per successfully authenticated monthly user** hoặc theo active users phù hợp.

Nếu yêu cầu bảo mật làm tỷ lệ account recovery thất bại tăng mạnh, có thể tồn tại **khuyết tật thiết kế kênh khôi phục**, không hẳn người dùng nhập sai.

### 18.3. Alert/runbook

| Tín hiệu | Hành động đầu tiên |
| --- | --- |
| SMS OTP delivery failures tăng | Kiểm tra sandbox, sender/registration, Region, quota, delivery route. |
| Email MFA code không đến | Kiểm tra SES identities/quota, bounce/deliverability, pool plan và message settings. |
| Risk blocks tăng sau policy update | Kiểm tra Audit vs Full function, false positives, WAF/NAT/VPN traffic. |
| ForgotPassword InvalidParameterException tăng | Kiểm tra verified recovery attributes và xung đột kênh MFA. |
| 401 tăng sau release frontend | Kiểm tra token_use, issuer/client_id, callback/PKCE và JWKS. |
| 403 từ Java API tăng | Phân biệt thiếu scope với object-level permission, không vội tắt authorization. |
| Chi phí SMS tăng bất thường | Xem OTP spam, rate controls, WAF, số lượt gửi và billing by destination. |

Không tạo alert quá nhạy cho mọi OTP nhập sai; user có thể gõ nhầm. Quan sát tỷ lệ và xu hướng, kết hợp bất thường theo IP/thiết bị và mức độ tác động.

## 19. Chi phí Cognito và các dịch vụ liên quan

Không có một đơn giá chung cho mọi kịch bản Cognito. Phải tính cả feature plan và các dịch vụ phụ trợ:

| Khoản phí | Tác nhân chi phí | Tối ưu |
| --- | --- | --- |
| **Cognito User Pools** | Gói Lite/Essentials/Plus và **Monthly Active Users (MAU)** theo điều kiện định giá. | Chọn tier theo yêu cầu thực, không bật Plus chỉ vì muốn MFA TOTP. |
| **SMS/End User Messaging** | Số tin và quốc gia nhận, sender identity/registration theo chính sách. | TOTP/passkey nếu phù hợp, WAF chống spam, theo dõi retry. |
| **Amazon SES** | Email OTP/MFA/recovery, bounces và data transfer theo pricing. | Kiểm soát deliverability, gửi đúng luồng, phát hiện abuse. |
| **AWS WAF** | Web ACL, rules, requests, managed/bot control features. | Rule phù hợp workload, tránh trả phí rule không cần. |
| **CloudWatch/Logs** | Logs ingest/storage/queries, metrics, alarms. | Structured logs, retention, không log payload nhạy cảm. |
| **Lambda triggers** | Runtime execution, requests, logs, network, retry. | Giảm logic không cần và tối ưu cold start/calls. |
| **API Gateway/ALB/app backend** | HTTP requests, compute, data transfer. | Caching khi hợp lý, scale và rate control đúng. |
| **Data residency/Regions** | Vị trí pool, SES/SMS integration, dữ liệu và network. | Thiết kế Region/DR có chủ đích. |

### 19.1. Khi nào cần Plus plan?

**Threat protection** (compromised credentials, adaptive auth/risk) cần **Plus** theo tài liệu hiện hành. **Email MFA, password reuse prevention, passwordless/passkeys** có hỗ trợ từ **Essentials** trở lên theo điều kiện.

Không nâng Plus chỉ để dùng **TOTP MFA** nếu các yêu cầu khác không cần Plus, nhưng phải đọc pricing/tier capabilities chính thức theo Region và thời điểm.

### 19.2. Credential stuffing có thể tạo hóa đơn

Một bot gửi hàng chục nghìn sign-in/OTP requests có thể:

- Làm tăng rate-limit errors.
- Tạo email/SMS messages và delivery charges.
- Tăng WAF/CloudWatch requests/logs.
- Tạo support incidents khi user bị lockout.
- Làm méo adoption/business metrics.

Cần budget alerts, WAF, challenge/rate rules, abuse monitoring và message limits. **Budgets alert không phải hard cost cap** tự chặn mọi chi phí.

## 20. Khắc phục sự cố MFA và password recovery

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Bật MFA required nhưng user không login được. | Chưa setup factor, app không xử lý MFA_SETUP, kênh MFA thiếu. | Pool MFA config, user preferences, challenge response, onboarding. |
| TOTP code luôn sai. | Điện thoại sai giờ, secret chưa verify, nhập nhầm account. | Associate/VerifySoftwareToken state, clock, Session validity. |
| Không nhận SMS. | Sandbox, origination registration, quota, số không E.164, delivery delays. | Cognito SMS settings, SNS/End User Messaging delivery logs. |
| Không nhận email MFA. | Lite plan, chưa cấu hình SES, sender chưa verify, quota/bounce/spam. | UserPoolTier, EmailMfaConfiguration, SES status. |
| User có email MFA nhưng ForgotPassword lỗi. | Email là preferred MFA và không có recovery phone đủ điều kiện. | AccountRecoverySetting, phone_number_verified, support flow. |
| User có SMS MFA nhưng reset password qua SMS không được. | Cognito không dùng cùng phone làm MFA và recovery. | Thêm verified email fallback hoặc admin recovery. |
| Optional MFA nhưng managed login không mời setup. | Optional không tự đưa UX đăng ký MFA. | Tạo settings/enrollment UI bằng Cognito APIs. |
| User nhận email OTP nhưng app chờ SMS_MFA. | Parser hard-code ChallengeName hoặc auth mode sai. | Đọc ChallengeName từ response, kiểm tra client flow. |
| Passwordless OTP không chạy khi Required MFA. | Ràng buộc first-factor/MFA của Cognito. | AllowedFirstAuthFactors và WebAuthn exceptions. |
| Federated user không nhận local TOTP MFA. | MFA federated được giao cho external IdP. | SAML/OIDC IdP policy và sign-in path. |
| Cognito trả 403 sau bật WAF. | Web ACL rule chặn request hợp lệ. | WAF sampled requests/logs, rate rules, IP/NAT. |
| Threat protection chặn nhân viên VPN. | Risk logic nhận vị trí/thiết bị bất thường, false positive. | Audit logs, enforcement settings, allow/block exceptions. |
| API trả 401 dù token nhìn có vẻ đúng. | Sai issuer/exp/token_use/client_id/signature/JWKS. | JWT validator và app client mapping. |
| API trả 403 sau khi user login thành công. | Thiếu scope/group hoặc không có object-level permission. | Authorization rules và business data ACL. |
| Logout không chặn JWT cũ ở API tự quản. | Offline signature+exp validation không biết revocation. | Token/session architecture, TTL, revocation-aware mechanism. |
| MFA mã nhiều lần sai làm account bị lock. | Cognito backoff/lockout sau nhiều failures. | Retry policy, user support, không bypass security. |

### 20.1. Cây chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A["User không hoàn thành sign-in"] --> B{"Có nhận ChallengeName?"}
    B -->|"Không"| C["Kiểm tra app client, password/auth flow, WAF, risk block"]
    B -->|"Có"| D{"App xử lý đúng challenge?"}
    D -->|"Không"| E["Cập nhật parser/UI cho TOTP/SMS/Email/MFA_SETUP"]
    D -->|"Có"| F{"User có nhận/verify factor?"}
    F -->|"Không"| G["Kiểm tra SES/SMS/TOTP, time/session, user attrs"]
    F -->|"Có"| H{"Cognito cấp AuthenticationResult?"}
    H -->|"Không"| I["Xem lockout, risk response, lỗi challenge"]
    H -->|"Có"| J["Kiểm tra JWT validation / API scopes / tenant permissions"]
~~~

### 20.2. Các bẫy vận hành

- Không tắt MFA toàn pool để hỗ trợ một user duy nhất.
- Không biến user-password reset thành thao tác tự động không có kiểm tra danh tính.
- Không log password/OTP/token để điều tra.
- Không bỏ validation JWT vì frontend báo lỗi.
- Không dùng WAF allowlist rộng vô thời hạn khi xử lý false positives.
- Không coi **Cognito sign-in success** là bằng chứng mọi API đã được ủy quyền đúng.

## 21. Tình huống thực tế và lời giải

### Tình huống A — Triển khai TOTP cho nhân viên

**Yêu cầu:** Nhân viên nội bộ có quyền quản lý đơn hàng; công ty muốn mỗi lần local password sign-in đều có yếu tố thứ hai.

**Thiết kế:** Đánh giá MFA = **ON**, bật TOTP, onboarding bằng AssociateSoftwareToken/VerifySoftwareToken, hướng dẫn user thiết lập authenticator, hỗ trợ recovery có xác minh danh tính và giữ log admin changes. Nếu doanh nghiệp đã dùng Entra ID/Okta, có thể phù hợp hơn để yêu cầu phishing-resistant MFA ngay tại IdP.

**Kiểm thử:** User mới, user cũ, mất điện thoại, TOTP sai, Session hết hạn, administrator reset, ứng dụng không hoàn tất challenge.

### Tình huống B — Khách hàng chỉ có email

**Yêu cầu:** User đăng ký bằng email, app bật email MFA, recovery policy chỉ cho phép email.

**Vấn đề:** Email đang dùng làm MFA không được dùng làm self-service password reset qua cùng kênh theo Cognito. User có nguy cơ bị khóa.

**Thiết kế:** Thu thập và xác minh **phone number** làm recovery alternate, hoặc có admin-assisted process. Nếu không thể thu thập phone, cân nhắc **TOTP MFA** thay email và khôi phục bằng email theo policy đúng; thử toàn bộ sign-in/recovery trước rollout.

### Tình huống C — Chặn credential stuffing

**Yêu cầu:** Login failures tăng mạnh từ nhiều IP, một số cặp password đúng.

**Thiết kế:** Bật WAF rate/bot protections, MFA, Plus threat protection nếu cần, kiểm tra password flows để compromised-credentials check thực sự áp dụng, kích hoạt risk alerts và giới hạn thông báo user existence.

**Không nên:** Chặn một IP quốc gia rộng hoặc bật Block trên mọi risk level không có audit, làm ảnh hưởng user hợp lệ.

### Tình huống D — Java API nhận ID token làm bearer

**Yêu cầu:** Frontend login thành công nhưng dùng ID token thay access token để gọi Java API. Backend chỉ check signature.

**Vấn đề:** ID token là token dành cho identity client; backend có thể đang chấp nhận sai loại token.

**Thiết kế:** Java API kiểm tra **token_use=access**, issuer, client binding, exp, scope và business ownership. Frontend dùng đúng access token hoặc BFF session mechanism, không dùng ID token cho resource authorization.

### Tình huống E — Risk-based MFA trong Plus

**Yêu cầu:** Product muốn khách hàng ít bị hỏi MFA ở lần đăng nhập bình thường, nhưng khi thiết bị/vị trí lạ thì yêu cầu MFA.

**Thiết kế:** **MFA OPTIONAL**, Plus threat protection, audit-only trước, thu thập đủ telemetry và configure risk actions (MFA/block/notification) có support fallback. Kiểm thử false positives với VPN và carrier NAT.

### Tình huống F — User mất thiết bị sau phishing

**Yêu cầu:** User nghi password bị lộ và điện thoại TOTP bị mất.

**Thiết kế:** Support xác minh danh tính qua quy trình bảo mật, đánh giá suspicious activity, thu hồi refresh/session tokens phù hợp, reset password/re-enroll MFA, xác minh lại recovery methods và thông báo user theo policy. Không dùng email/SMS không đủ kiểm chứng làm đường bypass MFA tùy tiện.

## 22. Bài tập thực hành có đáp án gợi ý

**Bài 1 — Xây policy bảo mật cho hệ thống giao dịch.** Hệ thống có local users, một ứng dụng SPA và Spring Boot API. Hãy thiết kế app client, MFA, recovery, token validation.

**Gợi ý:** Public app client + Authorization Code/PKCE, MFA policy theo risk, TOTP, recovery alternate, JWT access-token validation ở API, quyền theo object/tenant. Không nhúng client secret vào SPA.

**Bài 2 — Password history.** Team muốn cấm user dùng lại 10 passwords trước và phát hiện password rò rỉ khi sign-in.

**Gợi ý:** Essentials/Plus cho reuse prevention, nhưng **compromised-credentials detection cần Plus** và chỉ hoạt động với những authentication flows hỗ trợ.

**Bài 3 — ForgotPassword lỗi với user dùng SMS MFA.** User có verified phone nhưng không có verified email.

**Gợi ý:** Không thể dùng cùng phone cho SMS MFA và reset; cần email verified alternate hoặc admin recovery.

**Bài 4 — Login email MFA không giao code.** Pool đang Lite và email gửi qua default path.

**Gợi ý:** Email MFA yêu cầu Essentials/Plus và SES do khách hàng cấu hình; nâng plan và thiết lập SES sender/quota có kiểm soát, kiểm tra deliverability và chi phí.

**Bài 5 — Federated user bị bỏ qua local MFA.** User login qua corporate SAML IdP.

**Gợi ý:** Bật MFA ở IdP, không mặc định Cognito local pool sẽ thêm factor sau federation; kiểm tra SAML/OIDC integration và IdP policy.

**Bài 6 — WAF block quá mức.** Sau khi bật rate rule, nhiều user cùng office public IP bị 403.

**Gợi ý:** Xem WAF sampled/log requests, điều chỉnh key/rate/exceptions theo risk, giám sát hiệu quả bảo vệ mà không tắt WAF hoàn toàn.

**Bài 7 — Passkey trong pool MFA required.** Product muốn passwordless passkey mà vẫn đáp ứng nhiều yếu tố.

**Gợi ý:** Xem **WebAuthnConfiguration.FactorConfiguration=MULTI_FACTOR_WITH_USER_VERIFICATION**, feature plan và browser support; không coi passkey là yếu tố thứ hai sau password.

**Bài 8 — Logout mà JWT vẫn dùng được.** Custom Java API verify signature và expiration offline.

**Gợi ý:** Revocation của Cognito không được kiểm tra bởi JWT library chỉ verify signature/exp; cần thiết kế session/revocation-aware authorization hoặc access token lifetimes phù hợp.

**Bài 9 — Đánh giá chi phí OTP.** Số lượng SMS tăng gấp 5 mà số successful logins chỉ tăng 10%.

**Gợi ý:** Kiểm tra bot/retry/OTP abuse, WAF, SMS requests by destination, delivery failures, login success rate; tối ưu **cost per successful user sign-in**.

**Bài 10 — Required MFA gây lockout sau release.** Hơn 20% user cũ không có TOTP hoặc verified phone.

**Gợi ý:** Khôi phục deployment policy có kiểm soát, bổ sung onboarding/enrollment UI, hướng dẫn recovery và thử trước khi bật required lại. Không bỏ qua MFA trên từng request.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Cognito User Pool khác Identity Pool thế nào?  
**Đáp án:** User Pool xác thực người dùng ứng dụng và cấp tokens; Identity Pool có thể cấp temporary AWS credentials dựa trên danh tính.

**Câu 2.** MfaConfiguration có những giá trị chính nào?  
**Đáp án:** **OFF, OPTIONAL, ON**.

**Câu 3.** MFA OPTIONAL có tự khiến managed login mời mọi user setup MFA không?  
**Đáp án:** Không. Ứng dụng cần cung cấp UX đăng ký nếu muốn user tự bật MFA.

**Câu 4.** Ba phương thức message/software MFA phổ biến?  
**Đáp án:** **TOTP, SMS MFA, email MFA**.

**Câu 5.** Email MFA có cần Essentials/Plus và SES không?  
**Đáp án:** Có, theo điều kiện Cognito hiện hành.

**Câu 6.** Một mã email OTP làm yếu tố đăng nhập duy nhất có tự là MFA không?  
**Đáp án:** Không. Nó là passwordless **first-factor**.

**Câu 7.** Passkey có thể làm second factor sau password sign-in trong Cognito không?  
**Đáp án:** Không theo mô hình hiện hành; passkey có user verification có thể tự đáp ứng MFA requirement trong first-factor khi bật WebAuthn setting phù hợp.

**Câu 8.** Vì sao cần VerifySoftwareToken sau AssociateSoftwareToken?  
**Đáp án:** Associate tạo secret; Verify xác nhận user thực sự kiểm soát authenticator và biết mã hợp lệ.

**Câu 9.** User chọn SMS MFA có thể dùng cùng phone để ForgotPassword không?  
**Đáp án:** Không. Cần recovery channel thay thế hoặc admin.

**Câu 10.** TemporaryPasswordValidityDays có làm mọi password thường hết hạn định kỳ không?  
**Đáp án:** Không. Nó áp dụng mật khẩu tạm của luồng admin-created/set.

**Câu 11.** Password reuse prevention thuộc gói nào?  
**Đáp án:** **Essentials/Plus** theo tính năng hiện hành.

**Câu 12.** Compromised-credentials detection thuộc gói nào?  
**Đáp án:** **Plus threat protection**, với các flow được hỗ trợ.

**Câu 13.** Vì sao SRP không được compromised-credentials sign-in check như USER_PASSWORD_AUTH?  
**Đáp án:** SRP không gửi plaintext password cho Cognito theo luồng đó.

**Câu 14.** Adaptive MFA nên cấu hình MFA ON hay OPTIONAL?  
**Đáp án:** **OPTIONAL** theo hướng dẫn Cognito threat protection risk-based MFA.

**Câu 15.** Bật Cognito local MFA có tự yêu cầu MFA cho SAML users không?  
**Đáp án:** Không; federated IdP chịu trách nhiệm xác thực/MFA.

**Câu 16.** WAF và threat protection làm cùng một việc không?  
**Đáp án:** Không. WAF quản lý request/bot/rate protections; threat protection đánh giá sign-in risk và password compromise theo các khả năng khác.

**Câu 17.** Access token có dùng thay AWS access key được không?  
**Đáp án:** Không. User Pool tokens không phải IAM credentials.

**Câu 18.** Java backend cần kiểm tra gì trên Cognito access JWT?  
**Đáp án:** Signature/JWKS, issuer, expiration, token_use, client binding, scopes và quyền nghiệp vụ.

**Câu 19.** Vì sao một token bị Cognito revoke vẫn có thể được custom JWT library chấp nhận?  
**Đáp án:** Library chỉ verify chữ ký/expiry không tự kiểm tra revocation state.

**Câu 20.** Thay MFA preference của user có thể dùng API nào?  
**Đáp án:** **SetUserMFAPreference** theo access token user, hoặc **AdminSetUserMFAPreference** với admin IAM permissions.

**Câu 21.** Khi MFA required, tại sao onboarding phải có bước enrollment?  
**Đáp án:** Người dùng chưa có factor hợp lệ có thể không hoàn tất các lần login yêu cầu MFA.

**Câu 22.** Cost drivers quan trọng của login/MFA?  
**Đáp án:** Cognito tier/MAU, SMS, SES email, WAF, CloudWatch, Lambda triggers và backend/network.

## 24. Tổng kết và checklist vận hành

**MFA, password policy và bảo vệ authentication flow** là một hệ thống liên kết; thiết kế từng phần riêng lẻ có thể tạo lỗ hổng hoặc khóa user.

Checklist trước production:

1. **Phân loại danh tính:** local, federated, human users, machine-to-machine; không áp một kiểu MFA cho tất cả.
2. **MFA policy:** OFF/OPTIONAL/ON theo risk và UX; required phải có onboarding.
3. **Method:** TOTP, SMS/email khi điều kiện giao hàng/plan hợp lệ; passkey user verification theo feature/flow.
4. **Password:** độ dài, complexity, password managers, reuse prevention nếu khả dụng.
5. **Recovery:** có kênh **khác MFA preferred** hoặc admin process có xác minh danh tính.
6. **Tokens:** Authorization Code + PKCE, client secret đúng nơi, JWT validation, scope và object authorization.
7. **Session:** refresh token rotation, revocation, sign-out, bảo vệ browser/session cookies.
8. **Threat protection:** Plus plan, hiểu giới hạn SRP/federation, audit trước enforcement.
9. **WAF:** rate/bot rules có test, tránh false positives và spam OTP.
10. **Observability:** MFA completion, recovery success, risk events, OTP delivery, logs với quyền và retention phù hợp.
11. **Chi phí:** quản lý MAU/tier, SMS/email/WAF/CloudWatch, theo dõi abnormal traffic.
12. **Kiểm thử:** signup, setup, lost factor, password reset, policy update, app client mismatch, token revocation, federated login và rollback.
13. **Bảo mật vận hành:** IAM least privilege, CloudTrail audit, không log credentials, policy change review.
14. **Độ tin cậy:** quy trình hỗ trợ user và phản ứng sự cố, không bỏ qua MFA khi hệ thống liên quan bị lỗi.

Bảo mật tốt không chỉ là buộc mọi người nhập thêm mã. Cần làm cho **đăng nhập hợp lệ khả dụng**, **đăng nhập bất thường khó thành công**, **khôi phục tài khoản đáng tin cậy** và **quyền truy cập dữ liệu được kiểm tra liên tục** trong toàn bộ kiến trúc AWS.

### Tài liệu AWS chính thức tham khảo

- [Amazon Cognito User Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html) — nền tảng quản lý danh tính ứng dụng.
- [Adding MFA to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html) — MFA modes, preferences, passwordless và passkeys.
- [TOTP software token MFA](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-totp.html) — đăng ký và verify authenticator.
- [SMS and email message MFA](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-sms-email-message.html) — OTP delivery và điều kiện.
- [User pool feature plans](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html) — Lite, Essentials, Plus.
- [Passwords, account recovery, and policies](https://docs.aws.amazon.com/cognito/latest/developerguide/managing-users-passwords.html) — mật khẩu, recovery và lịch sử mật khẩu.
- [Threat protection](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-settings-threat-protection.html) — adaptive auth và compromised credentials.
- [Working with adaptive authentication](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pool-settings-adaptive-authentication.html) — risk signals và responses.
- [Associate AWS WAF with a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-waf.html) — request-level protection.
- [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html) — refresh rotation và session lifetime.
- [Token revocation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html) — sign out và revocation.
- [Cognito pricing](https://aws.amazon.com/cognito/pricing/) — chi phí feature plan và MAU.



