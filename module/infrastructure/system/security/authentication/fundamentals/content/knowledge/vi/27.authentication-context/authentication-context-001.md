# Ngữ cảnh xác thực (Authentication Context)

> **Chương:** Authentication context  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Mô hình hóa và sử dụng ngữ cảnh xác thực như bằng chứng có nguồn gốc, thời điểm, phương thức và mức bảo đảm rõ ràng; giúp ứng dụng quyết định khi nào phiên hiện tại đủ tin cậy và khi nào phải xác thực lại hoặc step-up.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích authentication context là gì và phân biệt nó với credential, identity profile, session, access token và authorization context.
2. Mô tả các thuộc tính quan trọng: subject, issuer, authentication time, phương thức, yếu tố, mức bảo đảm, nguồn phát hành và ràng buộc với phiên.
3. Phân biệt thời điểm xác thực với thời điểm phát hành token, thời điểm tạo session và thời điểm request được gửi.
4. Đọc và diễn giải các thông tin ngữ cảnh trong OIDC như auth_time, acr, amr, iss, sub và sid theo hợp đồng với issuer.
5. Hiểu cách SAML biểu diễn ngữ cảnh xác thực qua AuthnContextClassRef, AuthnInstant và các thuộc tính liên quan.
6. Thiết kế chính sách assurance và freshness cho các thao tác khác nhau, không suy ra mức bảo đảm chỉ từ số lượng yếu tố.
7. Lưu, truyền và kiểm tra context ở server-side; không tin cờ xác thực do client tự khai.
8. Thiết kế step-up, xử lý recovery, chống downgrade/replay và kiểm thử các ranh giới tin cậy của authentication context.

## 1. Authentication context là gì?

**Authentication context (ngữ cảnh xác thực)** là tập thông tin có cấu trúc mô tả một chủ thể đã được xác thực như thế nào, vào thời điểm nào, bởi thành phần nào và theo mức bảo đảm nào.

Một lần đăng nhập không chỉ có kết quả đúng/sai. Để ra quyết định an toàn, ứng dụng thường cần biết thêm:

- Chủ thể nào đã được xác thực?
- Kết quả đến từ issuer hoặc hệ thống xác thực nào?
- Người dùng đã dùng phương thức gì: mật khẩu, passkey, chứng chỉ, OTP hay kết hợp nhiều phương thức?
- Có bao nhiêu yếu tố độc lập và chúng có đáp ứng chính sách không?
- Xác thực diễn ra lúc nào?
- Có xác minh user presence hoặc user verification không?
- Phương thức có chống phishing không?
- Kết quả có được ràng buộc với transaction, thiết bị, khóa hoặc phiên cụ thể không?
- Ngữ cảnh có còn đủ mới cho thao tác đang yêu cầu không?

Ví dụ, hai người dùng cùng đăng nhập thành công nhưng ngữ cảnh khác nhau:

- Người A dùng mật khẩu và mã OTP qua TOTP.
- Người B dùng passkey với user verification trên authenticator.
- Người C dùng phiên IdP cũ và được SSO mà không xác thực lại trong lần truy cập ứng dụng hiện tại.

Cả ba có thể được ứng dụng tạo session, nhưng mức chống phishing, thời điểm xác thực và điều kiện step-up có thể khác nhau. Nếu ứng dụng chỉ lưu authenticated=true, nó đã bỏ mất thông tin cần thiết để áp chính sách phù hợp.

### Authentication context không phải là gì?

- **Không phải credential:** context mô tả bằng chứng đã dùng; nó không phải mật khẩu, OTP seed, private key hay passkey secret.
- **Không phải identity profile:** tên, email, phòng ban và ảnh đại diện mô tả thuộc tính người dùng, không chứng minh cách họ vừa xác thực.
- **Không phải session:** session là trạng thái truy cập duy trì giữa các request; context là một phần dữ liệu có thể được gắn vào session.
- **Không phải access token:** token là credential được trình tới resource server; token có thể mang một số claim về authentication context.
- **Không phải authorization decision:** context cung cấp dữ liệu cho policy; quyền cuối cùng còn phụ thuộc resource, action, subject, tenant và trạng thái nghiệp vụ.

## 2. Vì sao ứng dụng cần authentication context?

Nếu mọi lần đăng nhập thành công đều được coi như nhau, ứng dụng dễ cấp quyền quá rộng hoặc giữ quyền cao quá lâu.

Authentication context giúp ứng dụng:

- Yêu cầu xác thực mạnh hơn trước khi đổi mật khẩu, email khôi phục hoặc authenticator.
- Giới hạn thao tác nhạy cảm nếu phiên được tạo bằng fallback yếu hơn.
- Kiểm tra xác thực có đủ mới hay không trước khi phê duyệt giao dịch.
- Phân biệt phiên đăng nhập bằng passkey với phiên dùng mật khẩu hoặc recovery.
- Đưa ra quyết định step-up khi rủi ro tăng.
- Áp chính sách nhất quán giữa nhiều ứng dụng hoặc resource server.
- Điều tra sự cố bằng cách biết credential nào và issuer nào đã tạo ra phiên.

### Ví dụ chính sách theo hành động

| Hành động | Ngữ cảnh có thể chấp nhận | Vì sao |
| --- | --- | --- |
| Xem nội dung công khai | Phiên hợp lệ, không yêu cầu xác thực gần đây. | Hậu quả thấp. |
| Xem hồ sơ cá nhân | Phiên authenticated hợp lệ, còn hạn. | Dữ liệu riêng tư cần chủ thể đã xác minh. |
| Đổi email khôi phục | Xác thực lại gần đây bằng phương thức đủ mạnh. | Thay đổi này ảnh hưởng khả năng lấy lại tài khoản. |
| Thêm/gỡ passkey | Step-up theo policy, xác minh đúng tài khoản và transaction. | Thao tác có thể chuyển quyền kiểm soát tài khoản. |
| Cấp quyền quản trị | Assurance cao, xác thực mới và kiểm tra quyền quản trị riêng. | Hậu quả khi bị lạm dụng rất lớn. |
| Duyệt giao dịch giá trị cao | Context đủ mạnh, mới và gắn đúng transaction. | Giảm rủi ro replay hoặc phê duyệt nhầm. |

Đây là ví dụ thiết kế, không phải bảng assurance dùng chung cho mọi tổ chức. Policy cần dựa trên tài sản, hậu quả, đối tượng sử dụng và năng lực của hệ thống xác thực.

## 3. Các thành phần của một authentication context

Không có một object schema duy nhất bắt buộc cho mọi ứng dụng. Một mô hình nội bộ thường có các nhóm thuộc tính sau:

| Nhóm | Thuộc tính ví dụ | Mục đích |
| --- | --- | --- |
| Chủ thể | issuer, subject, tenant | Xác định danh tính theo namespace đáng tin cậy. |
| Nguồn | authenticationAuthority, clientId, protocol | Cho biết hệ thống/ứng dụng đã tạo kết quả. |
| Thời gian | authenticatedAt, issuedAt, expiresAt | Đánh giá độ mới và vòng đời. |
| Phương thức | methods, factors, authenticatorTypes | Mô tả credential và yếu tố đã dùng. |
| Mức bảo đảm | assuranceLevel, acr, policyId | Ánh xạ kết quả sang policy nội bộ. |
| Thuộc tính bảo vệ | phishingResistant, userVerified, senderConstrained | Mô tả các đặc tính đã được xác minh. |
| Ràng buộc | transactionId, sessionId, credentialId | Gắn bằng chứng với đúng transaction/session/credential. |
| Trạng thái | recoveryUsed, stepUp, revoked | Phản ánh ngữ cảnh đặc biệt và trạng thái hiệu lực. |

Không phải trường nào cũng cần được lưu hoặc đưa vào token. Chỉ giữ dữ liệu cần thiết cho policy, audit và vận hành; tránh lưu dấu vết thiết bị quá chi tiết hoặc thông tin nhạy cảm không cần thiết.

### Ví dụ minh họa

~~~text
AuthenticationContext
  issuer: "https://login.example.edu"
  subject: "learner-42"
  tenant: "university-a"
  method: ["webauthn"]
  factors: ["possession", "local-user-verification"]
  authenticatedAt: 2026-11-22T08:30:00Z
  assuranceLevel: "ORG_AAL2_PHISHING_RESISTANT"
  phishingResistant: true
  userVerified: true
  recoveryUsed: false
  sessionRef: "server-side-session-reference"
~~~

Tên mức assurance ở trên là profile nội bộ giả định. Không có nghĩa mọi passkey tự động đạt cùng một AAL hoặc mọi hệ thống đều dùng nhãn này. Ứng dụng phải biết bằng chứng thực tế và quy tắc mapping của issuer.

## 4. Phân biệt authentication event, context, session và token

Bốn khái niệm liên quan nhưng khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Authentication event** | Sự kiện xác thực xảy ra tại một thời điểm. | Người dùng hoàn tất passkey lúc 08:30. |
| **Authentication context** | Mô tả có cấu trúc về sự kiện và bằng chứng. | Passkey, user verification, issuer, assurance và thời gian. |
| **Session** | Trạng thái truy cập được duy trì giữa các request. | Cookie session của Learning Portal. |
| **Access token** | Credential dùng để gọi resource server. | Token có audience learning-api và scope progress:read. |

Một session có thể tồn tại lâu hơn khoảng thời gian mà xác thực ban đầu còn đủ mới cho thao tác nhạy cảm. Một access token mới có thể được phát hành bằng refresh token mà không có tương tác xác thực mới. Vì vậy, không suy ra authentication context mới chỉ từ việc session hoặc token vừa được tạo.

### Ví dụ về thời gian

~~~text
08:30  Người dùng xác thực bằng passkey
08:31  Ứng dụng tạo local session
08:45  Authorization server cấp access token mới
09:20  Người dùng yêu cầu đổi email khôi phục
~~~

Tại 09:20, authenticatedAt vẫn có thể là 08:30. Token được cấp lúc 08:45 không làm cho người dùng vừa xác thực lại. Nếu policy yêu cầu xác thực trong 5 phút gần nhất, hệ thống cần step-up thay vì nhìn vào thời điểm phát hành token.

## 5. Authentication context và các yếu tố xác thực

Context cần mô tả yếu tố thực sự đã được xác minh. Các nhóm yếu tố thường gặp:

- **Knowledge:** thứ người dùng biết, như mật khẩu hoặc PIN được hệ thống xác minh.
- **Possession:** thứ người dùng sở hữu/kiểm soát, như authenticator, khóa bảo mật hoặc private key.
- **Inherence:** đặc điểm sinh trắc được authenticator cục bộ xác minh, như vân tay hoặc khuôn mặt.

Không phải mọi tín hiệu đều là một yếu tố độc lập. Ví dụ:

- Mật khẩu và câu hỏi bảo mật có thể cùng thuộc nhóm knowledge.
- OTP qua SMS và OTP qua TOTP đều cần đánh giá cách bảo vệ kênh/secret; không tự động có nghĩa là hai yếu tố độc lập.
- Sinh trắc học trên thiết bị thường mở khóa private key cục bộ; server không nhận dữ liệu vân tay/khuôn mặt và không nên coi mẫu sinh trắc là credential gửi qua mạng.
- Hai bước UI không đồng nghĩa MFA nếu chúng không kiểm tra các yếu tố độc lập theo policy.

### Đếm yếu tố không đủ để xác định assurance

Một luồng có hai yếu tố vẫn có thể dễ bị phishing nếu attacker thu thập và chuyển tiếp được cả hai. Mức bảo đảm còn phụ thuộc:

- Cách authenticator được đăng ký và ràng buộc với tài khoản.
- Chất lượng và tính độc lập của yếu tố.
- Khả năng chống phishing và replay.
- Bảo vệ kênh, thiết bị và private key.
- Cách xác minh ở server.
- Quy trình khôi phục và thay thế authenticator.

Context nên lưu phương thức/đặc tính đã được xác minh, không chỉ một cờ mfa=true.

## 6. Authentication time, token issue time và session time

Thời gian là một phần quan trọng của context. Cần phân biệt:

- **Authentication time:** thời điểm người dùng thực sự hoàn thành xác thực theo ngữ nghĩa của giao thức.
- **Token issue time:** thời điểm token được phát hành.
- **Session creation time:** thời điểm ứng dụng tạo session.
- **Request time:** thời điểm API nhận request.
- **Step-up time:** thời điểm hoàn thành lần xác thực tăng cường gần nhất.

Các mốc này không thể thay thế lẫn nhau.

### Trong OIDC

- **auth_time:** thời điểm xác thực người dùng, nếu được yêu cầu hoặc được cung cấp theo profile.
- **iat:** thời điểm ID token được phát hành.
- **exp:** thời điểm ID token hết hạn.
- **max_age:** tham số authorization request yêu cầu OP xác thực lại nếu lần xác thực trước đã quá cũ.

Ví dụ, một ID token có iat mới vì được cấp sau refresh hoặc flow mới, nhưng auth_time vẫn phản ánh lần xác thực trước. Client cần kiểm tra auth_time khi policy yêu cầu freshness.

### Sai lệch đồng hồ

Các hệ thống phân tán có thể lệch thời gian. Cần đồng bộ clock và định nghĩa clock skew nhỏ, có giới hạn. Không nới cửa sổ thời gian quá rộng để che lỗi đồng hồ vì attacker có thể tận dụng token/assertion đã cũ.

### Freshness policy

Một policy có thể định nghĩa:

~~~text
SensitiveActionPolicy
  maximumAuthenticationAge: 5 minutes
  acceptedAssurance: "ORG_AAL2"
  requirePhishingResistance: true
  requireUserVerification: true
  requireSameSubject: true
~~~

Các giá trị chỉ là ví dụ. Với mỗi thao tác, ứng dụng cần tính tuổi xác thực từ thời điểm đáng tin cậy, kiểm tra assurance và ràng buộc đúng subject; không chỉ kiểm tra session còn active.

## 7. OIDC: acr, amr, auth_time và các claim liên quan

OpenID Connect có một số claim giúp RP hiểu ngữ cảnh xác thực. Ý nghĩa và giá trị cụ thể cần được diễn giải theo OIDC Core, profile áp dụng và thỏa thuận với OP.

| Claim | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **iss** | Issuer của ID token. | Phải khớp chính xác issuer được RP tin cậy. |
| **sub** | Subject identifier. | Định danh trong phạm vi issuer; thường dùng cặp iss + sub. |
| **auth_time** | Thời điểm xác thực người dùng. | Dùng cho freshness; khác iat. |
| **acr** | Authentication Context Class Reference. | Mã lớp/ngữ cảnh xác thực theo profile hoặc thỏa thuận với OP. |
| **amr** | Authentication Methods References. | Danh sách phương thức xác thực được dùng; giá trị có ngữ nghĩa theo registry/profile/issuer. |
| **sid** | Session identifier trong một số profile/extension. | Có thể hỗ trợ liên kết phiên và logout; không phải định danh người dùng thay sub. |
| **nonce** | Giá trị ràng buộc ID token với authentication request. | RP phải kiểm tra khớp transaction đã lưu. |

### acr không phải thang điểm toàn cầu

Hai OP có thể phát hành cùng chuỗi acr nhưng định nghĩa assurance khác nhau. Ngược lại, hai OP có thể dùng chuỗi khác nhau cho mức tương đương.

RP cần một **mapping được thống nhất**:

| Giá trị acr từ OP | Mapping nội bộ ví dụ | Điều kiện |
| --- | --- | --- |
| urn:example:loa:1 | LOW | Chỉ cho thao tác ít rủi ro. |
| urn:example:loa:2 | STANDARD_MFA | Phải có profile xác định yếu tố và chính sách. |
| urn:example:loa:3 | HIGH_PHISHING_RESISTANT | Chỉ chấp nhận nếu OP cam kết phương thức và kiểm soát tương ứng. |

Các URI trong bảng là giá trị giả định. Không thể lấy tên loa:3, aal2 hay high rồi tự coi đó là mức assurance tương đương NIST hoặc tiêu chuẩn khác nếu chưa có mapping được xác minh.

### amr không thay thế validation

RP có thể thấy các giá trị phổ biến như pwd, otp, hwk hoặc các giá trị theo profile. Tuy nhiên, phải biết OP định nghĩa chúng thế nào, có chứng minh yếu tố độc lập không và kết quả có được bảo vệ bởi chữ ký ID token hay không. Không dùng một chuỗi do client tự gửi để gán phương thức xác thực.

## 8. SAML: AuthnContext và AuthnInstant

Trong SAML, ngữ cảnh xác thực thường được biểu diễn trong AuthnStatement:

- **AuthnInstant:** thời điểm xác thực.
- **AuthnContextClassRef:** lớp/ngữ cảnh xác thực được IdP khẳng định.
- **AuthnContextDeclRef/Decl:** tham chiếu hoặc mô tả ngữ cảnh chi tiết nếu được sử dụng.
- **SessionIndex:** chỉ mục phiên IdP, có thể liên quan tới Single Logout.
- **Subject/NameID:** chủ thể được xác thực theo federation contract.

SP phải xác minh chữ ký, issuer, audience, destination, recipient, thời hạn, InResponseTo và chống replay trước khi sử dụng ngữ cảnh trong assertion.

### Mapping AuthnContext

Giống acr trong OIDC, AuthnContextClassRef không tự có cùng ý nghĩa ở mọi IdP. Tổ chức cần thống nhất:

- Class URI nào đại diện cho phương thức nào.
- Có yêu cầu MFA không.
- Có yêu cầu chống phishing không.
- Thời điểm AuthnInstant được tính theo cách nào.
- IdP có bảo đảm user verification hoặc hardware protection không.
- Giá trị nào được chấp nhận cho từng ứng dụng.

Không coi assertion hợp lệ về chữ ký là assurance cao nếu AuthnContext không đáp ứng policy.

## 9. Assurance level và cách diễn giải

**Assurance level** mô tả mức tin cậy mà hệ thống có thể đặt vào một lần xác thực theo một bộ yêu cầu. Các khung như NIST SP 800-63B định nghĩa Authentication Assurance Level (AAL) dựa trên yêu cầu về authenticator, yếu tố, chống replay, chống phishing và bảo vệ quy trình.

Một số nguyên tắc:

- AAL không đơn giản là số lượng màn hình hoặc số lần nhập mã.
- MFA là điều kiện quan trọng ở một số mức, nhưng chưa đủ để kết luận mọi yêu cầu AAL đã đạt.
- Phương thức chống phishing cần được đánh giá theo đặc tính giao thức/authenticator.
- Quy trình recovery và thay authenticator có thể làm thay đổi mức tin cậy.
- Context từ IdP chỉ có thể ánh xạ sang assurance nội bộ khi hai bên hiểu và kiểm chứng cùng một profile.

### Ví dụ phân loại nội bộ

| Mức nội bộ | Diễn giải ví dụ | Thao tác có thể cho phép |
| --- | --- | --- |
| LOW | Một phương thức cơ bản, ít bằng chứng chống phishing. | Nội dung công khai hoặc chức năng rủi ro thấp. |
| STANDARD | Xác thực tài khoản theo policy thông thường. | Tác vụ cá nhân có rủi ro vừa phải. |
| MFA | Đã hoàn tất các yếu tố độc lập theo policy. | Thao tác nhạy cảm vừa phải, tùy freshness. |
| PHISHING_RESISTANT | Phương thức có ràng buộc chống phishing đã được xác minh. | Có thể đáp ứng yêu cầu cao hơn nếu còn mới và đúng subject. |
| HIGH_ASSURANCE | Đáp ứng profile chặt chẽ của tổ chức/tiêu chuẩn đã chọn. | Quyền đặc quyền theo policy riêng. |

Đây là nhãn minh họa, không phải tuyên bố tương đương AAL1/AAL2/AAL3. Nếu tổ chức dùng NIST AAL hoặc khung khác, phải đánh giá theo đầy đủ yêu cầu của khung đó và ghi rõ profile.

## 10. Context gắn với session và access token

Một ứng dụng có thể giữ authentication context trong session server-side, hoặc nhận một phần context qua token/assertion đã được xác minh.

### Server-side session

Ưu điểm:

- Dễ cập nhật hoặc thu hồi context.
- Có thể lưu trạng thái step-up, recovery và thời điểm xác thực.
- Không cần đưa mọi chi tiết vào cookie hoặc access token.

Yêu cầu:

- Session ID phải được bảo vệ và xoay tại ranh giới xác thực.
- Context phải gắn với subject và session đúng.
- Client không được tự sửa thuộc tính context.
- Cache/session store phải cập nhật nhất quán khi step-up hoặc revoke.

### Token

Token có thể mang claim như auth_time, acr, amr, iss, sub hoặc claim riêng theo profile. Khi dùng token:

- Chỉ tin claim sau khi xác minh chữ ký hoặc introspection.
- Kiểm tra issuer, audience, thời hạn và loại token.
- Hiểu token được phát hành cho resource nào.
- Không giả định access token và ID token có cùng claim hoặc cùng ngữ nghĩa.
- Không dùng token cũ để chứng minh freshness mới.
- Không chuyển claim assurance qua service khác nếu không giữ được nguồn và ngữ nghĩa.

### Không nhầm token mới với xác thực mới

Refresh token có thể tạo access token mới mà không yêu cầu người dùng tương tác. Vì vậy iat mới không đồng nghĩa auth_time mới. Resource server cần dựa vào claim/metadata xác thực đã được xác minh và policy, không suy ra từ thời điểm token được nhận.

## 11. Step-up authentication dựa trên context

Step-up là yêu cầu người dùng cung cấp bằng chứng mạnh hơn hoặc mới hơn khi hành động cần mức assurance cao hơn context hiện tại.

### Quy trình khái quát

1. API nhận request cho một hành động nhạy cảm.
2. Server xác định subject và context từ session/token đã xác minh.
3. Policy engine đánh giá assurance, phương thức, freshness, transaction binding và risk.
4. Nếu context đủ, tiếp tục kiểm tra quyền nghiệp vụ.
5. Nếu context chưa đủ, server yêu cầu step-up qua IdP hoặc authenticator đã đăng ký.
6. Kết quả step-up được xác minh, ràng buộc đúng subject và transaction.
7. Server cập nhật context, thời điểm xác thực và trạng thái phiên; xoay session ID nếu cần theo policy/framework.
8. API đánh giá lại policy trước khi thực hiện hành động.

~~~mermaid
flowchart TD
    R["Request thao tác nhạy cảm"] --> C["Lấy authentication context đáng tin"]
    C --> P{"Đủ assurance và freshness?"}
    P -->|"Có"| A["Kiểm tra quyền trên resource/action"]
    P -->|"Không"| S["Yêu cầu step-up"]
    S --> V["Xác minh kết quả mới"]
    V --> Q{"Đúng subject, transaction\nvà policy?"}
    Q -->|"Không"| X["Từ chối"]
    Q -->|"Có"| U["Cập nhật context và session"]
    U --> A
    A --> D{"Đủ quyền nghiệp vụ?"}
    D -->|"Có"| O["Thực hiện hành động"]
    D -->|"Không"| F["403 / từ chối quyền"]
~~~

### Step-up phải gắn với đúng hành động

Nếu người dùng step-up cho thao tác đổi email nhưng kết quả có thể được replay để thêm passkey hoặc duyệt giao dịch, context có thể bị dùng sai mục đích. Với thao tác có tác động cao, cần ràng buộc bằng transaction identifier, action, resource hoặc confirmation phù hợp.

Một lần step-up không tự cấp quyền cho mọi hành động trong tương lai. Context chỉ đáp ứng các policy có yêu cầu tương ứng và trong cửa sổ freshness đã định nghĩa.

## 12. Provenance: nguồn gốc và tính toàn vẹn của context

Authentication context chỉ hữu ích nếu ứng dụng biết **ai đã khẳng định thông tin đó và bằng chứng đã được xác minh ra sao**.

Các nguồn có thể tin cậy:

- Kết quả xác thực nội bộ do authentication service ghi nhận.
- ID token đã xác minh từ issuer được cấu hình.
- SAML assertion đã xác minh từ IdP được tin cậy.
- Session context server-side được tạo từ authentication event hợp lệ.
- Introspection response từ authorization server được xác thực và bảo vệ.

Các nguồn không đủ tin cậy nếu đứng riêng:

- JSON body do browser gửi, ví dụ mfaPassed=true.
- Header tự khai X-User, X-Auth-Level từ client công khai.
- User-Agent, IP hoặc device label do client khai.
- Email hoặc tên hiển thị.
- Cờ trong localStorage/sessionStorage.
- Thời điểm token được refresh mà không có bằng chứng xác thực mới.

### Ghi provenance

Một context nội bộ nên có thể truy ngược:

- Issuer hoặc authentication authority.
- Authentication event ID.
- Client/RP đã nhận kết quả.
- Protocol/profile và mapping policy version.
- Thời điểm xác thực và thời điểm ghi nhận.
- Subject/tenant mà kết quả áp dụng.
- Kết quả validation và các ràng buộc transaction.

Không cần lưu toàn bộ raw assertion hoặc raw token trong session/log. Lưu reference/audit ID và dữ liệu tối thiểu; raw credential có thể chứa thông tin nhạy cảm và tạo thêm rủi ro khi bị lộ.

## 13. Mô hình hóa context trong Java

Ví dụ sau thể hiện một object nội bộ bất biến ở mức khái niệm. Đây không phải schema chuẩn của OIDC/SAML và không nên nhận trực tiếp từ browser.

~~~java
import java.time.Instant;
import java.util.Set;

public record AuthenticationContext(
        String issuer,
        String subject,
        String tenantId,
        Set<String> methods,
        Set<String> factors,
        String assuranceLevel,
        Instant authenticatedAt,
        boolean phishingResistant,
        boolean userVerified,
        boolean recoveryUsed,
        String authenticationEventId
) {
    public AuthenticationContext {
        if (issuer == null || issuer.isBlank()) {
            throw new IllegalArgumentException("issuer is required");
        }
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        methods = Set.copyOf(methods);
        factors = Set.copyOf(factors);
    }
}
~~~

Các điểm cần lưu ý:

- Object được tạo sau khi server xác minh kết quả authentication.
- issuer và subject phải được lấy từ nguồn đã xác minh.
- methods và factors phải được ánh xạ theo hợp đồng với authenticator/IdP.
- phishingResistant không được đặt chỉ vì tên phương thức có chữ passkey; cần biết profile, binding và kết quả validation.
- assuranceLevel là kết quả mapping policy nội bộ, không phải nhãn do client tự gửi.
- authenticatedAt là thời điểm xác thực theo ngữ nghĩa giao thức, không phải thời điểm tạo object.
- Không lưu secret, OTP, private key hoặc raw biometric data trong object.

### Kiểm tra freshness

~~~java
import java.time.Duration;
import java.time.Instant;

public final class AuthenticationPolicy {

    private AuthenticationPolicy() {
    }

    public static boolean isFresh(
            AuthenticationContext context,
            Instant now,
            Duration maximumAge
    ) {
        if (context == null || context.authenticatedAt() == null) {
            return false;
        }

        Instant oldestAccepted = now.minus(maximumAge);

        return !context.authenticatedAt().isBefore(oldestAccepted)
                && !context.authenticatedAt().isAfter(now.plusSeconds(60));
    }
}
~~~

Đây là ví dụ đơn giản. Triển khai thực tế cần xử lý clock skew có giới hạn, giá trị thời gian bất hợp lý, expiry, revoked context, policy theo issuer và các yêu cầu assurance/phương thức. Không dùng một hàm freshness duy nhất thay cho toàn bộ policy engine.

## 14. Rủi ro khi context bị hiểu sai hoặc bị giả mạo

| Rủi ro | Cách xảy ra | Biện pháp |
| --- | --- | --- |
| **Context spoofing** | Client gửi mfa=true, acr=high hoặc role tự khai. | Chỉ lấy context từ token/assertion/session đã xác minh. |
| **Stale authentication** | Session còn sống nhưng lần xác thực đã quá cũ. | Kiểm tra authenticatedAt theo action policy và step-up. |
| **Token refresh confusion** | Token mới được coi là xác thực mới dù chỉ refresh. | Phân biệt iat với auth_time. |
| **Assurance mapping error** | Coi acr/AuthnContext của mọi IdP là tương đương. | Mapping theo issuer/profile được thống nhất. |
| **MFA inflation** | Coi hai bước cùng một loại yếu tố là MFA độc lập. | Kiểm tra factor independence và authenticator properties. |
| **Downgrade** | Attacker ép fallback/recovery yếu nhưng session vẫn được đánh dấu assurance cao. | Giữ context thấp hơn, step-up hoặc giới hạn quyền. |
| **Issuer confusion** | Context từ issuer/tenant khác được gắn vào subject hiện tại. | Kiểm tra issuer, audience, tenant và subject binding. |
| **Session fixation** | Context authenticated được gắn vào session ID attacker đã biết. | Xoay session ID tại ranh giới xác thực. |
| **Replay** | Assertion/step-up result cũ được dùng lại. | Nonce, transaction binding, expiry và replay detection. |
| **Context leakage** | Log chứa token, assertion hoặc dữ liệu thiết bị quá chi tiết. | Minimize data, redact secret và giới hạn quyền truy cập log. |
| **Confused deputy** | Service downstream dùng context cho sai audience/action. | Giữ audience, actor, subject và delegation semantics. |

### Recovery không tự động tương đương xác thực mạnh

Nếu người dùng khôi phục tài khoản bằng email hỗ trợ hoặc quy trình thủ công, ứng dụng không nên tự gán context như thể họ vừa dùng passkey chống phishing. Recovery có thể khôi phục quyền truy cập, nhưng cần ghi rõ recoveryUsed, phương thức và mức assurance tương ứng.

Sau recovery, có thể yêu cầu đăng ký authenticator mới, thông báo kênh cũ, thu hồi phiên cũ và step-up trước thao tác nhạy cảm. Không để quy trình recovery trở thành đường nâng quyền dễ hơn đăng nhập chính.

## 15. Ví dụ thực tế: nền tảng học tập

Learning Platform có ba loại hành động:

- Học viên xem nội dung và tiến độ.
- Giảng viên cập nhật điểm và nhận xét.
- Quản trị viên thay đổi vai trò, email khôi phục và cấu hình tenant.

### Ngữ cảnh khi đăng nhập

Một học viên xác thực qua OIDC bằng passkey. RP xác minh ID token, issuer, audience, nonce và thời gian. Context nội bộ được tạo với subject theo issuer, phương thức WebAuthn và assurance mapping đã thống nhất với IdP. RP xoay session ID và lưu context trong session server-side.

### Xem tiến độ

Học viên gọi API xem tiến độ. API xác minh session/access token, subject và scope. Context đăng nhập còn hợp lệ; API kiểm tra học viên đã ghi danh khóa học trước khi trả dữ liệu.

### Cập nhật điểm

Giảng viên mở chức năng cập nhật điểm. Policy yêu cầu:

- Subject là giảng viên đang hoạt động.
- Có quyền với lớp và khóa học cụ thể.
- Context đạt assurance yêu cầu.
- Authentication time đủ mới.
- Có user verification hoặc phương thức step-up phù hợp theo profile.

Nếu context cũ hơn giới hạn, ứng dụng yêu cầu step-up. Sau khi IdP trả kết quả mới, RP xác minh issuer, subject, auth_time, acr/amr theo mapping, cập nhật context và đánh giá lại quyền.

### Đổi email khôi phục của quản trị viên

Đây là thao tác có thể ảnh hưởng khả năng kiểm soát tài khoản. Ứng dụng yêu cầu phương thức chống phishing theo policy, xác thực gần đây, xác nhận transaction và thông báo qua kênh đã đăng ký trước. Context từ một lần recovery yếu hoặc phiên SSO cũ không đủ điều kiện.

Ví dụ cho thấy context giúp phân biệt người dùng đã đăng nhập, người dùng có quyền nghiệp vụ và người dùng vừa chứng minh mức xác thực đủ mạnh cho hành động cụ thể.

## 16. Kiểm thử authentication context

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Context hợp lệ từ issuer tin cậy | Xác minh token/assertion và tạo context. | Context gắn đúng issuer, subject và policy mapping. |
| Client gửi mfa=true | Thay body/header ở request. | Server bỏ qua cờ tự khai. |
| ID token có iss sai | Dùng token từ issuer khác. | Không tạo context. |
| ID token có audience sai | Dùng token dành cho RP khác. | Từ chối. |
| auth_time quá cũ | Tạo context cũ rồi gọi thao tác nhạy cảm. | Step-up hoặc từ chối theo policy. |
| iat mới nhưng auth_time cũ | Mô phỏng access/ID token được phát hành lại sau refresh. | Không coi là xác thực mới. |
| acr chưa được mapping | Dùng giá trị lạ hoặc issuer chưa onboard. | Không tự nâng assurance; từ chối hoặc áp mức thấp theo policy. |
| amr không đáp ứng policy | Thiếu yếu tố hoặc giá trị không rõ ngữ nghĩa. | Không đánh dấu MFA/phishing-resistant. |
| Recovery đã sử dụng | Tạo context có recoveryUsed. | Không tự nâng lên assurance của passkey; áp recovery policy. |
| Context sai subject | Step-up trả subject khác với session hiện tại. | Từ chối và không gắn context. |
| Context sai tenant | Issuer/subject hợp lệ nhưng tenant không khớp. | Từ chối. |
| Replay step-up transaction | Gửi lại response đã sử dụng. | Replay detection từ chối. |
| Session fixation | Giữ session ID trước login và dùng lại sau login. | ID mới được cấp; ID cũ không có context authenticated. |
| Token refresh | Xin token mới không có tương tác người dùng. | Authentication time giữ nguyên theo nguồn tin cậy. |
| Clock skew | Thời gian tương lai/quá xa so với policy. | Từ chối hoặc xử lý trong clock-skew window giới hạn. |
| Context bị thu hồi | Revoke session/credential/issuer mapping. | Request tiếp theo không được hưởng context cũ. |
| Downstream service | Chuyển context sang API khác audience. | API chỉ chấp nhận context/token dành cho chính nó. |
| Log/trace | Gửi token và context qua hệ thống quan sát. | Không log secret/raw token; dữ liệu context được tối thiểu hóa. |

## 17. Checklist thiết kế

- [ ] Đã định nghĩa authentication context và phân biệt với identity, credential, session, token và authorization.
- [ ] Context có issuer/source, subject, tenant và authentication event reference.
- [ ] Phân biệt authentication time, token issue time, session creation time và request time.
- [ ] Có policy freshness cho từng nhóm thao tác.
- [ ] Có mapping được phê duyệt cho OIDC acr/amr và SAML AuthnContext.
- [ ] Không coi tên acr hoặc số lượng yếu tố là assurance toàn cầu.
- [ ] Đã xác minh factor independence, user verification và phishing resistance theo profile.
- [ ] Context chỉ được tạo từ nguồn server-side hoặc assertion/token đã xác minh.
- [ ] Không tin cờ xác thực/role do client tự gửi.
- [ ] Context gắn với đúng subject, issuer, tenant, session và transaction.
- [ ] Có step-up cho thao tác cần assurance hoặc freshness cao hơn.
- [ ] Recovery/fallback có context riêng và không tự nâng assurance.
- [ ] Đã xoay session ID tại ranh giới xác thực và thay đổi đặc quyền.
- [ ] Có cơ chế revoke, logout và cập nhật context trong hệ thống phân tán.
- [ ] Không log password, OTP, private key, raw token, cookie hoặc biometric data.
- [ ] Có kiểm thử stale context, issuer/audience mismatch, replay, downgrade và context spoofing.

## 18. Tự kiểm tra

**Câu 1.** Authentication context mô tả điều gì?

**Đáp án:** Nó mô tả chủ thể được xác thực như thế nào, vào lúc nào, bởi nguồn nào và theo mức bảo đảm/điều kiện nào. Nó là dữ liệu để policy đánh giá, không phải credential hoặc quyết định quyền hoàn chỉnh.

**Câu 2.** Vì sao không thể dùng iat thay cho auth_time?

**Đáp án:** iat là thời điểm token được phát hành; auth_time là thời điểm xác thực người dùng. Token mới có thể được cấp qua refresh mà không có tương tác xác thực mới.

**Câu 3.** Hai yếu tố nhập liên tiếp có luôn là MFA không?

**Đáp án:** Không. Cần xem chúng có thuộc các nhóm yếu tố độc lập, được xác minh đúng và đáp ứng policy hay không. Hai mật khẩu hoặc hai bước cùng một nhóm knowledge không tự động là MFA.

**Câu 4.** Vì sao acr cần mapping theo issuer?

**Đáp án:** Giá trị và ý nghĩa assurance có thể do OP/profile định nghĩa. Cùng một chuỗi ở hai issuer không đảm bảo có cùng mức bảo vệ.

**Câu 5.** amr có thể được client tự gửi để chứng minh passkey không?

**Đáp án:** Không. RP chỉ tin amr từ ID token đã xác minh hoặc nguồn tin cậy khác, và phải hiểu ngữ nghĩa theo hợp đồng với OP.

**Câu 6.** Session còn hạn có nghĩa authentication context còn đủ mới không?

**Đáp án:** Không. Session timeout và freshness là hai policy khác nhau. Một phiên còn active vẫn có thể cần step-up trước thao tác nhạy cảm.

**Câu 7.** Recovery thành công có tự động tạo context phishing-resistant không?

**Đáp án:** Không. Context phải ghi rõ phương thức recovery và assurance thực tế. Recovery có thể cho phép truy cập lại nhưng không tương đương passkey chống phishing.

**Câu 8.** Vì sao context phải gắn với subject và tenant?

**Đáp án:** Để ngăn kết quả xác thực của người hoặc tenant này bị áp vào phiên của người/tenant khác. Trong federation, identity thường được xác định bằng issuer + subject.

**Câu 9.** Khi step-up hoàn tất, chỉ cần lưu mfa=true là đủ không?

**Đáp án:** Không. Cần lưu nguồn, subject, thời điểm, phương thức, assurance mapping, transaction và trạng thái xác minh; policy phải đánh giá đúng hành động.

**Câu 10.** Resource server nên làm gì nếu context không đủ assurance hoặc quá cũ?

**Đáp án:** Yêu cầu step-up hoặc từ chối theo policy trước khi thực hiện hành động. Không tự nâng assurance, không tin cờ client và vẫn kiểm tra quyền nghiệp vụ riêng.

## Ghi nhớ

**Authentication context** mô tả bằng chứng xác thực: chủ thể, issuer, phương thức/yếu tố, thời điểm, assurance và các ràng buộc liên quan. Nó giúp ứng dụng biết một phiên đã được tạo bằng cách nào và có đủ mới, đủ mạnh cho hành động hiện tại hay không.

Hãy phân biệt authentication time với token issue time, acr với mapping assurance nội bộ, amr với bằng chứng factor đã được xác minh, và context với authorization. Chỉ tin context từ nguồn có provenance; gắn nó với đúng issuer, subject, tenant, session và transaction. Recovery/fallback không tự nâng assurance; thao tác nhạy cảm cần step-up khi context thiếu hoặc quá cũ. **Một lần đăng nhập thành công không phải giấy phép vĩnh viễn cho mọi hành động: policy phải đánh giá đúng bằng chứng và thời điểm của lần xác thực.**
