# Authentication control — Kiểm soát xác thực và bằng chứng tuân thủ
 
> **Chương:** Compliance  
> **Chủ đề:** Authentication control

**Authentication control** là tập hợp chính sách, quy trình, công nghệ và bằng chứng kiểm soát nhằm bảo đảm chỉ chủ thể phù hợp mới có thể chứng minh danh tính và thiết lập quyền truy cập vào hệ thống. Trong bối cảnh compliance, tổ chức cần chứng minh rằng các cơ chế xác thực được thiết kế phù hợp với rủi ro, được triển khai nhất quán, được vận hành liên tục và có thể kiểm tra độc lập.

Authentication control không chỉ là bật MFA hoặc đặt quy tắc password. Phạm vi bao gồm vòng đời danh tính và credential, enrollment, login, step-up, federation, session, recovery, privileged access, service identity, revocation, monitoring và xử lý ngoại lệ. Một control có thể được viết rất tốt trên tài liệu nhưng vẫn không hiệu quả nếu tài khoản dùng chung tồn tại, recovery bypass yếu, session không bị thu hồi hoặc bằng chứng vận hành không được lưu.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, giúp người học hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Trọng tâm compliance là chuyển yêu cầu kiểm soát thành control objective có thể kiểm chứng, gắn owner và phạm vi, thu thập evidence an toàn, đánh giá design/operating effectiveness và xử lý gap có trách nhiệm.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích authentication control và phân biệt authentication, authorization, identity governance và compliance evidence.
2. Xây dựng control objective, control activity, owner, scope, frequency và evidence.
3. Ánh xạ yêu cầu xác thực vào framework/standard phù hợp mà không nhầm mapping với chứng nhận tuân thủ.
4. Đánh giá password, MFA, passkey, certificate, federation, session và recovery theo rủi ro.
5. Thiết kế kiểm soát riêng cho privileged account, workforce, customer và workload identity.
6. Kiểm tra enrollment, account lifecycle, access review, revocation và exception management.
7. Phân biệt design effectiveness và operating effectiveness.
8. Thu thập evidence có nguồn gốc, timestamp, scope và integrity mà không lưu secret.
9. Thiết kế test of control, sampling, walkthrough và remediation tracking.
10. Tránh các anti-pattern như shared account, MFA bypass, stale access, recovery yếu và evidence chỉ mang tính hình thức.

## 2. Authentication control trong hệ thống quản trị

Authentication trả lời câu hỏi chủ thể chứng minh quyền kiểm soát credential như thế nào. Authorization quyết định chủ thể được làm gì trên resource. Identity governance quản lý việc tạo, thay đổi, xem xét và chấm dứt danh tính/quyền. Compliance đánh giá các hoạt động đó có đáp ứng tiêu chí và được chứng minh bằng evidence hay không.

| Khái niệm | Câu hỏi | Ví dụ kiểm soát |
| --- | --- | --- |
| Authentication | Ai đang chứng minh danh tính? | MFA, passkey, certificate |
| Authorization | Chủ thể được làm gì? | Role, permission, resource policy |
| Identity governance | Ai được cấp và giữ account/quyền? | Joiner-mover-leaver, access review |
| Session management | Quyền truy cập đã xác thực tồn tại bao lâu? | TTL, rotation, revocation |
| Compliance | Control có đáp ứng tiêu chí và vận hành hiệu quả? | Policy, test, evidence, audit trail |

Một tổ chức không thể chứng minh kiểm soát xác thực chỉ bằng ảnh chụp màn hình trang cấu hình MFA. Cần chứng minh policy áp dụng cho đúng population, account thực tế được bảo vệ, ngoại lệ được phê duyệt, recovery không bypass và việc vận hành được giám sát.

## 3. Từ yêu cầu compliance đến control objective

Yêu cầu trong luật, hợp đồng, framework hoặc chính sách nội bộ thường được viết ở mức mục tiêu. Tổ chức cần chuyển chúng thành hoạt động có thể quan sát và kiểm tra.

### 3.1. Cấu trúc một control

Một control description tốt nên xác định:

- **Control ID:** mã duy nhất;
- **Objective:** kết quả bảo mật cần đạt;
- **Risk addressed:** rủi ro nếu không có control;
- **Scope:** hệ thống, tenant, user population, environment và account class;
- **Owner:** người chịu trách nhiệm thiết kế/vận hành;
- **Operator:** nhóm thực hiện hoạt động;
- **Frequency/trigger:** định kỳ hoặc theo sự kiện;
- **Procedure:** các bước thực hiện;
- **Evidence:** bằng chứng được tạo;
- **Exception path:** cách phê duyệt và theo dõi ngoại lệ;
- **Test procedure:** cách kiểm tra design và operation;
- **Retention:** thời hạn lưu evidence theo policy.

### 3.2. Ví dụ control objective

**Objective:** Tài khoản có quyền truy cập dữ liệu nhạy cảm phải sử dụng phương thức xác thực đáp ứng mức assurance đã được phê duyệt.

**Control activity:** IAM service áp dụng policy theo account class và resource sensitivity; privileged account yêu cầu phishing-resistant MFA; việc thêm hoặc gỡ authenticator yêu cầu reauthentication và audit.

**Evidence:** Policy version, danh sách account trong scope, trạng thái authenticator đã giảm thiểu dữ liệu, event enrollment, exception approvals và kết quả test định kỳ.

### 3.3. Control phải có thể kiểm chứng

Câu “mọi tài khoản phải an toàn” quá rộng. Cần chuyển thành các mệnh đề có thể kiểm tra, ví dụ:
- Tài khoản nhân viên đang hoạt động có owner và trạng thái employment phù hợp;
- Tài khoản đặc quyền được bảo vệ bằng MFA theo policy;
- Account rời tổ chức bị disable trong SLA;
- Recovery transaction chỉ dùng một lần;
- Session bị thu hồi sau sự kiện compromise theo quy trình;
- Ngoại lệ có approver, lý do và ngày hết hạn.

## 4. Control framework và cách ánh xạ

Các framework cung cấp tiêu chí để tổ chức xây dựng hoặc đánh giá control. Không phải framework nào cũng áp dụng cho mọi tổ chức, và một mapping không tự chứng minh compliance.

| Framework/nguồn yêu cầu | Chủ đề liên quan tới authentication | Cách sử dụng |
| --- | --- | --- |
| NIST SP 800-63 series | Identity proofing, authenticator, federation và lifecycle | Thiết kế assurance và technical requirements |
| NIST SP 800-53 | Account management, identification/authentication, authenticator management, audit | Xây dựng control catalog và assessment procedure |
| ISO/IEC 27001:2022 và 27002 | Access control, identity management, authentication information, access rights | ISMS risk treatment và control operation |
| SOC 2 Trust Services Criteria | Logical access, credential protection, access removal và monitoring | Chứng minh control theo phạm vi engagement |
| PCI DSS | User identification, authentication, MFA và access control trong môi trường cardholder data | Áp dụng theo scope và phiên bản PCI được đánh giá |
| CIS Controls/Benchmarks | Account, access, secure configuration và audit | Baseline kỹ thuật và hardening |
| Quy định bảo vệ dữ liệu/hợp đồng | Bảo vệ account và dữ liệu cá nhân | Xác định nghĩa vụ theo jurisdiction và contract |

### 4.1. Mapping không đồng nghĩa compliance

Một control nội bộ có thể hỗ trợ nhiều tiêu chí, nhưng auditor vẫn cần kiểm tra phạm vi, cách triển khai, bằng chứng và thời gian vận hành. Một dòng mapping trong spreadsheet không chứng minh rằng control hoạt động.

### 4.2. Xác định phiên bản và phạm vi

Khi dùng framework, ghi rõ:
- Tên và phiên bản;
- Control/criterion reference;
- Applicability;
- Hệ thống/tenant thuộc scope;
- Shared responsibility với cloud/IdP/vendor;
- Rationale nếu control không áp dụng;
- Evidence source và test method.

Không trộn yêu cầu từ nhiều phiên bản mà không ghi nguồn. Với tiêu chuẩn có cập nhật, xác nhận phiên bản được hợp đồng, assessor hoặc cơ quan quản lý yêu cầu.

### 4.3. Không tuyên bố chứng nhận thay tổ chức

Việc triển khai một số control không tự làm tổ chức “đạt ISO”, “đạt SOC 2” hoặc “đạt PCI”. Chứng nhận/attestation phụ thuộc phạm vi, đánh giá độc lập, thời kỳ, bằng chứng và các tiêu chí khác ngoài authentication.

## 5. Risk-based control design

Control cần tương xứng với rủi ro. Một tài khoản đọc nội dung công khai không có cùng yêu cầu với tài khoản quản trị hệ thống identity hoặc service account có quyền truy cập dữ liệu hàng loạt.

### 5.1. Các yếu tố đánh giá

- Mức nhạy cảm và giá trị dữ liệu;
- Quyền và blast radius của account;
- Khả năng tác động tài chính/vận hành;
- Threat model và khả năng phishing/credential theft;
- Loại chủ thể: workforce, customer, partner, workload;
- Thiết bị và môi trường truy cập;
- Khả năng recovery và support;
- Nghĩa vụ pháp lý, hợp đồng và framework;
- Khả năng giám sát, phát hiện và thu hồi.

### 5.2. Phân lớp account

| Account class | Ví dụ | Control direction |
| --- | --- | --- |
| Workforce standard | Nhân viên thông thường | MFA theo policy, lifecycle và access review |
| Privileged | Admin, security operator | Phishing-resistant MFA, PAM/JIT, approval, audit |
| Customer | Học viên, khách hàng | Assurance theo sensitivity và fraud risk |
| Partner/vendor | Tài khoản bên thứ ba | Federation hoặc account riêng, scope và expiry |
| Workload/service | API service, worker | Workload identity, short-lived credential, mTLS |
| Emergency | Break-glass | Credential độc lập, scope hẹp, dual control và review |

### 5.3. Không dùng một policy cho mọi account

Một policy duy nhất có thể quá yếu cho admin hoặc quá cứng cho user ít rủi ro. Policy nên phân loại account và action, nhưng không được tạo ngoại lệ không kiểm soát.

## 6. Password và authenticator control

### 6.1. Password storage

Kiểm soát cần xác minh:
- Password được lưu bằng password hashing/KDF thích hợp, có salt riêng;
- Không lưu plaintext hoặc reversible encryption khi không có yêu cầu kiến trúc đặc biệt;
- Có kiểm soát password yếu/bị lộ theo policy;
- Reset token được bảo vệ và có TTL/one-time use;
- Không ghi password vào log, trace, analytics hoặc support ticket;
- Có rate limiting và monitoring cho authentication abuse.

### 6.2. Password policy

Policy cần dựa trên tiêu chuẩn được tổ chức chọn và threat model. Tránh áp dụng quy tắc thay đổi password định kỳ vô điều kiện nếu không có căn cứ; ưu tiên độ dài, password screening, MFA, phát hiện compromise và reset khi có dấu hiệu cần thiết. Không tuyên bố một cấu hình cụ thể là bắt buộc cho mọi framework.

### 6.3. Authenticator lifecycle

Mỗi authenticator cần:
- Được đăng ký sau proofing phù hợp;
- Gắn với principal cụ thể;
- Có trạng thái active/revoked/lost;
- Có owner hoặc account owner;
- Có event enrollment và removal;
- Có quy trình thay thế và revoke;
- Có review theo risk.

### 6.4. Secret management

Credential bí mật phải có quyền truy cập tối thiểu, mã hóa khi lưu/truyền, rotation theo policy và quy trình xử lý compromise. Không đưa secret vào evidence package.

## 7. MFA và phishing-resistant authentication

MFA là một control quan trọng nhưng không phải mọi MFA đều có khả năng chống phishing như nhau.

### 7.1. MFA control objective

- Xác định account/action nào bắt buộc MFA;
- Kiểm tra MFA được enforce server-side;
- Xác định factor được chấp nhận;
- Quản lý enrollment và recovery;
- Ghi nhận bypass/exception;
- Kiểm thử session sau MFA và step-up;
- Theo dõi factor removal/replacement.

### 7.2. Phân biệt loại factor

SMS OTP, email OTP, TOTP và push thông thường có thể bị phishing hoặc relay. Passkey/WebAuthn và security key có thể chống phishing nhờ ràng buộc RP/origin khi triển khai đúng. Certificate/mTLS có thể bảo vệ service authentication nếu private key, peer identity và channel validation được cấu hình đúng.

Không đánh dấu một account là phishing-resistant chỉ vì nó có hai yếu tố.

### 7.3. Privileged access

Với admin và thao tác có blast radius lớn, cân nhắc:
- Phishing-resistant MFA;
- Security key dự phòng;
- Privileged access workstation;
- Just-in-time elevation;
- Approval/dual control;
- Reauthentication gần thời điểm thao tác;
- Session recording/audit phù hợp;
- Break-glass có kiểm soát.

### 7.4. Bằng chứng MFA

Evidence nên cho biết policy được áp dụng, account nằm trong scope và event xác thực đạt yêu cầu. Không cần thu thập OTP, biometric template hoặc private key để chứng minh MFA.

## 8. Passkey và WebAuthn control

Passkey là public-key credential. RP lưu public key và credential metadata; private key được bảo vệ bởi authenticator/platform.

### 8.1. Control cần có

- RP ID và origin allowlist được cấu hình chính xác;
- Challenge ngẫu nhiên, có TTL và one-time consumption;
- Server xác minh type, origin, RP ID hash, signature và flags;
- User verification được yêu cầu theo policy;
- Credential ID gắn với đúng principal;
- Enrollment cần reauthentication/step-up phù hợp;
- Credential removal và lost-device revocation có audit;
- Recovery không yếu hơn mức assurance được yêu cầu.

### 8.2. Synced passkey và device-bound

Synced passkey phụ thuộc bảo mật account đồng bộ và recovery của nền tảng. Device-bound credential có thể giảm một số rủi ro đồng bộ nhưng tăng nguy cơ lockout. Compliance evidence cần ghi loại policy được chấp nhận, không giả định mọi passkey có cùng đặc tính.

### 8.3. Evidence an toàn

Có thể lưu credential reference đã pseudonymize, registration timestamp, state, UV policy result và verifier version. Không lưu private key, biometric data hoặc assertion raw nếu không có nhu cầu đã được đánh giá.

## 9. Certificate và workload identity control

Certificate authentication thường dùng cho mTLS, smart card, thiết bị hoặc workload. Control cần quản lý cả PKI lifecycle và authorization mapping.

### 9.1. PKI lifecycle

- CA và trust anchor được quản lý;
- Enrollment có identity proofing;
- Subject/SAN/EKU/key usage phù hợp;
- Private key được bảo vệ;
- Certificate có expiry và rotation;
- Revocation được xử lý;
- Certificate inventory có owner;
- Certificate compromise có incident procedure.

### 9.2. Workload identity

Service nên dùng identity riêng, credential ngắn hạn và audience/scope giới hạn. Không dùng shared API key vô thời hạn cho mọi service. mTLS chứng minh workload peer và bảo vệ kênh; backend vẫn cần authorization trên action/resource.

### 9.3. Evidence

Evidence có thể gồm certificate inventory, issuance/revocation event, CA configuration review, rotation report và test kết nối với certificate revoked. Không đính kèm private key hoặc secret.

## 10. Federation, SSO và identity linking

Federation chuyển kết quả xác thực từ IdP sang relying party. Trust phải dựa trên cấu hình issuer, key, audience và protocol validation.

### 10.1. OIDC

RP cần xác minh signature, issuer, audience, nonce, expiry và token type theo flow. ID token dành cho client OIDC; access token dành cho resource server. Claim như acr/amr/auth_time chỉ có ý nghĩa theo hợp đồng và mapping đã định nghĩa.

### 10.2. SAML

SP cần kiểm tra signature, issuer, audience restriction, recipient/destination, time conditions và replay. AuthnContext phải được ánh xạ rõ với assurance policy; không tin một URI chỉ vì tên có vẻ mạnh.

### 10.3. Identity linking

Không tự động liên kết account chỉ vì email trùng. Cần xác minh quyền kiểm soát identity hiện có và identity mới, giữ mapping issuer + subject, có audit và quy trình unlink/recovery.

### 10.4. Shared responsibility

IdP bên thứ ba có thể chịu trách nhiệm một phần về authentication. Relying party vẫn phải xác minh token/assertion, kiểm tra account state, tenant membership, authorization và xử lý deprovisioning theo hợp đồng.

## 11. Session và token control

Authentication thành công thường tạo session hoặc token có thể tồn tại lâu hơn thao tác login.

### 11.1. Session requirements

- Session identifier đủ entropy và được rotate sau authentication/privilege change;
- Cookie có Secure, HttpOnly và SameSite phù hợp;
- Idle timeout và absolute lifetime được định nghĩa;
- Logout/revocation có hiệu lực;
- Session được liên kết với principal và authentication context;
- Step-up cập nhật assurance đúng cách;
- Session fixation và CSRF được kiểm soát.

### 11.2. Token requirements

- Issuer, audience, signature, expiry và token type được xác minh;
- Scope/claims tối thiểu;
- Access token TTL phù hợp;
- Refresh token rotation/reuse detection;
- Key rotation và revocation policy;
- Không đưa token vào URL hoặc log;
- Sender-constrained token khi threat model yêu cầu.

### 11.3. Evidence

Lưu policy/version, cấu hình TTL, kết quả kiểm thử revocation, session event aggregate và exception. Không lưu token/cookie thật trong audit evidence.

## 12. Account lifecycle và access governance

Authentication control không thể tách khỏi việc quản lý account từ lúc tạo đến khi chấm dứt.

### 12.1. Joiner-mover-leaver

- Joiner: account được tạo từ nguồn HR/CRM/tenant authority có thẩm quyền;
- Mover: thay đổi role/tenant/team kéo theo review quyền;
- Leaver: account, session, token, API key và certificate bị thu hồi theo SLA.

### 12.2. Dormant và orphan account

Phát hiện account không còn owner, account không hoạt động quá thời hạn, service account không có người chịu trách nhiệm hoặc account vendor đã hết hợp đồng. Dormant account không nhất thiết phải xóa ngay, nhưng cần policy disable/review và retention.

### 12.3. Access review

Owner phải xác nhận account và quyền còn cần thiết. Review nên bao gồm:
- Principal và owner;
- Account class;
- Tenant/role;
- Privileged group;
- Authenticator state;
- Last activity và exception;
- Decision: retain, modify, suspend hoặc revoke.

### 12.4. Shared account

Shared account làm giảm accountability và gây khó chứng minh ai thực hiện action. Tránh dùng account chung cho người dùng. Nếu một trường hợp kỹ thuật bắt buộc, cần owner, checkout, secret rotation, attribution và exception approval; ưu tiên workload identity riêng.

## 13. Privileged access và emergency account

Privileged account có tác động lớn nên cần control mạnh hơn account thông thường.

- MFA chống phishing theo policy;
- Tài khoản admin tách khỏi account dùng hằng ngày;
- JIT elevation và thời hạn ngắn;
- Approval/dual control cho action quan trọng;
- Audit đầy đủ;
- Session/token revocation;
- Review định kỳ;
- Break-glass account riêng và được diễn tập.

Break-glass không phải ngoại lệ vô thời hạn. Mỗi lần dùng phải có reason, actor, approver nếu policy yêu cầu, timestamp, scope, action và post-use review.

## 14. Recovery và exception management

Recovery là điểm thường làm suy yếu authentication control.

### 14.1. Recovery control

- Identity proofing phù hợp risk;
- Recovery token/code có entropy, TTL, subject/purpose binding;
- One-time consumption và replay protection;
- Helpdesk role/approval/dual control;
- Notification tới channel đã xác minh;
- Session/token cũ được xử lý;
- Credential cũ bị revoke khi mất/compromise;
- Audit evidence không chứa secret.

### 14.2. Exception

Mỗi exception cần:
- Lý do và risk assessment;
- Hệ thống/account trong scope;
- Control thay thế;
- Owner và approver;
- Ngày bắt đầu và expiry;
- Kế hoạch khắc phục;
- Monitoring bổ sung;
- Review và đóng exception.

Không cho phép “temporary exception” không có ngày hết hạn hoặc không có owner.

### 14.3. Compensating control

Nếu một yêu cầu không thể thực hiện ngay, compensating control cần giảm cùng rủi ro ở mức có thể giải thích. Ví dụ, giới hạn network không tự động tương đương MFA; một control bù phải được đánh giá theo threat model, scope và bằng chứng.

## 15. Logging, monitoring và audit trail

Authentication control cần có telemetry đủ để phát hiện và tái dựng sự kiện, nhưng không được lưu credential secret.

### 15.1. Event nên ghi

- Authentication success/failure và reason class;
- Authenticator enrollment/removal/revocation;
- Password reset và recovery outcome;
- MFA challenge/step-up;
- Token issue/refresh/revoke;
- Session create/renew/revoke;
- Privileged login/elevation;
- Federation/IdP issuer và context;
- Admin/helpdesk action;
- Policy change và exception approval.

### 15.2. Integrity và access

Audit log nên có quyền ghi/đọc tách biệt, bảo vệ integrity, timestamp đáng tin cậy, retention và alert khi logging bị gián đoạn. Truy cập log nhạy cảm cũng cần audit.

### 15.3. Không log secrets

Không ghi password, OTP, recovery code, access/refresh token, session cookie, private key hoặc full secret-bearing assertion. Dùng reference/pseudonymized identifier và evidence link có authorization.

### 15.4. Monitoring

Theo dõi brute force, spraying, credential stuffing, MFA fatigue, token reuse, session anomaly, recovery abuse, certificate expiry/revocation và admin activity. Alert cần owner, severity, runbook và disposition.

## 16. Privacy và data minimization trong evidence

Evidence cho audit có thể chứa dữ liệu cá nhân. Chỉ thu thập thông tin cần thiết để chứng minh control.

- Dùng aggregate hoặc pseudonymous reference khi có thể;
- Giới hạn raw email, phone, IP và device details;
- Có access control và audit cho evidence store;
- Xác định retention và deletion;
- Không đính kèm token/secret;
- Mask dữ liệu trong screenshot/export;
- Phân biệt evidence của auditor với dữ liệu vận hành chi tiết;
- Có quy trình legal hold nếu được yêu cầu.

Pseudonymization không phải anonymization. Nếu tổ chức vẫn có thể liên kết reference với cá nhân, dữ liệu có thể vẫn là dữ liệu cá nhân theo quy định áp dụng.

## 17. Design effectiveness và operating effectiveness

Đây là hai góc đánh giá khác nhau.

### 17.1. Design effectiveness

Control được thiết kế có đủ khả năng giảm rủi ro không?

Ví dụ:
- Policy yêu cầu MFA cho privileged account;
- Recovery có proofing và one-time token;
- Session có expiry và revocation;
- Account lifecycle có SLA;
- Exception có owner và expiry.

Một policy có thể hợp lý trên giấy nhưng không được áp dụng vào hệ thống thật.

### 17.2. Operating effectiveness

Control có thực sự vận hành như thiết kế trong thời kỳ được đánh giá không?

Ví dụ:
- Lấy population admin trong kỳ và xác minh MFA;
- Kiểm tra mẫu leaver account bị disable đúng SLA;
- Kiểm tra event enrollment/recovery;
- Kiểm tra session revoke thực sự có hiệu lực;
- Xem xét access review đã được owner hoàn tất;
- Kiểm tra exception hết hạn được đóng.

### 17.3. Evidence phải bao phủ thời kỳ

Một screenshot tại ngày audit có thể chứng minh cấu hình tại thời điểm đó, nhưng không tự chứng minh control đã vận hành trong cả kỳ. Cần evidence theo thời gian, change history, event record và sample test.

## 18. Evidence design và chain of custody

Một evidence package cần cho người đánh giá biết:
- Control nào đang được chứng minh;
- Nguồn tạo evidence;
- Thời điểm và thời kỳ;
- Population/scope;
- Query/filter hoặc phương pháp trích xuất;
- Ai thu thập và ai review;
- Evidence có bị thay đổi không;
- Các limitation hoặc missing data.

### 18.1. Ví dụ evidence

| Control objective | Evidence phù hợp |
| --- | --- |
| MFA cho privileged account | Population admin, policy version, enrollment/status aggregate, sample login event |
| Credential lifecycle | Enrollment/revocation events, account owner inventory |
| Leaver deprovisioning | HR termination sample và IAM disable timestamp |
| Recovery protection | Recovery policy, test report, sample audit event đã redacted |
| Session revocation | Revocation test result, propagation metrics |
| Certificate lifecycle | Certificate inventory, expiry/rotation/revocation report |
| Access review | Review population, owner decision, remediation record |
| Exception governance | Exception register, approval, expiry và closure |

### 18.2. Screenshot không đủ một mình

Screenshot có thể minh họa cấu hình nhưng dễ thiếu context, timestamp, population và lịch sử. Kết hợp export có nguồn, audit log, configuration version, test result và reviewer sign-off.

### 18.3. Evidence integrity

Dùng kho evidence có access control, versioning/retention và checksum hoặc cơ chế integrity phù hợp. Ghi lại ai xuất, khi nào và từ hệ thống nào. Không chỉnh sửa nội dung evidence mà không lưu nguồn và biến đổi.

## 19. Kiểm thử control và sampling

Một test of control cần có objective, population, sample method, procedure, expected result, exception criteria và conclusion.

### 19.1. Population

Ví dụ population:
- Tất cả privileged account trong kỳ;
- Tất cả recovery transaction;
- Tất cả leaver account;
- Tất cả certificate hết hạn/revoked;
- Tất cả exception đang active;
- Tất cả session revoke event thuộc incident.

Population phải đầy đủ và được đối chiếu với nguồn authoritative. Nếu population không đầy đủ, kết luận test bị giới hạn.

### 19.2. Sampling

Chọn mẫu theo risk và tiêu chí đánh giá. Có thể dùng random sampling, targeted sample cho privileged/high-risk hoặc test toàn bộ khi population nhỏ. Ghi rõ sample size, selection method và lý do; không chọn mẫu chỉ gồm trường hợp dễ chứng minh.

### 19.3. Test procedure

1. Xác định control objective và period.
2. Lấy population từ nguồn được phê duyệt.
3. Kiểm tra tính đầy đủ/chính xác của population.
4. Chọn sample và ghi phương pháp.
5. Thực hiện walkthrough và inspect evidence.
6. Đối chiếu expected result với thực tế.
7. Ghi exception và impact.
8. Đánh giá nguyên nhân gốc.
9. Giao remediation owner và due date.
10. Retest và đóng finding khi có bằng chứng.

## 20. Ví dụ control register

| ID | Control objective/activity | Owner | Frequency | Evidence |
| --- | --- | --- | --- | --- |
| IAM-AUTH-01 | Workforce account có nguồn cấp và owner được phê duyệt | IAM | Theo event | Provisioning record |
| IAM-AUTH-02 | Privileged account dùng phishing-resistant MFA | Security/IAM | Continuous + quarterly review | Policy, account population, test |
| IAM-AUTH-03 | Recovery token one-time, TTL và purpose-bound | Product/IAM | Per transaction + quarterly test | Design, test report, audit |
| IAM-AUTH-04 | Leaver account/session/credential bị revoke theo SLA | IAM/HR Ops | Theo event + monthly sample | HR/IAM timestamps |
| IAM-AUTH-05 | Workload credential ngắn hạn và có rotation | Platform | Continuous + periodic review | Inventory, issuance/rotation logs |
| IAM-AUTH-06 | Session/token có expiry và revocation | Application owner | Continuous + test | Config, revocation test |
| IAM-AUTH-07 | Access review cho privileged identity | Control owner | Quarterly hoặc theo policy | Review sign-off |
| IAM-AUTH-08 | Exception có approval, expiry và monitoring | Risk owner | Per exception + monthly review | Exception register |
| IAM-AUTH-09 | Authentication event được audit và bảo vệ | Security Operations | Continuous | Log config, access audit |
| IAM-AUTH-10 | Identity provider trust và federation mapping được review | IAM Architecture | Change-driven + periodic | Trust config, change record |

Đây là ví dụ cấu trúc, không phải bộ control bắt buộc. Tổ chức cần điều chỉnh owner, frequency và evidence theo risk, framework, contract và operating model.

## 21. Pseudocode đánh giá authentication control

~~~text
assess_authentication_control(control, period):
    require control.owner is assigned
    require control.scope is defined
    require control.objective is testable

    design = inspect_control_design(control)
    require design.addresses_documented_risk

    population = collect_authoritative_population(
        control.scope,
        period
    )
    validate_population_completeness(population)

    sample = select_sample_by_documented_method(population)
    results = []

    for item in sample:
        evidence = collect_minimized_evidence(item, control)
        result = test_expected_control_activity(
            item = item,
            evidence = evidence,
            criteria = control.expected_result
        )
        results.append(result)

    exceptions = identify_failures(results)
    assess_root_cause_and_impact(exceptions)
    record_test_conclusion(
        design_effectiveness = design.result,
        operating_effectiveness = summarize(results),
        limitations = population.limitations
    )
    assign_remediation_owner(exceptions)
~~~

Pseudocode mô tả quy trình đánh giá. Thực tế cần independence phù hợp giữa người vận hành và người kiểm tra, sampling method được phê duyệt, evidence retention, access audit và quy tắc xử lý finding.

## 22. Những lỗi compliance thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ có policy, không có evidence | Không chứng minh được vận hành | Lưu event, sample và test result |
| Mapping framework theo tên | Claim sai phạm vi | Ghi control reference, version và rationale |
| MFA chỉ bật cho một nhóm nhỏ không xác định | Population bị bỏ sót | Xác định scope và đối chiếu account inventory |
| Shared admin account | Không quy trách nhiệm | Named identity, PAM và exception có kiểm soát |
| Recovery yếu hơn login | Bypass assurance | Recovery proofing và approval phù hợp |
| Không revoke session khi leaver | Access tồn tại sau chấm dứt | Lifecycle automation và SLA test |
| Screenshot duy nhất | Evidence thiếu thời kỳ/population | Kết hợp config history, logs và sampling |
| Exception không expiry | Bypass trở thành vĩnh viễn | Owner, expiry, compensating control và review |
| Log chứa token/OTP | Evidence store thành kho credential | Redaction và evidence minimization |
| Không kiểm tra service identity | Workload access không được quản lý | Inventory, short-lived credential và mTLS |
| Không review IdP trust | Federation trust cũ hoặc quá rộng | Trust inventory và change review |
| Không kiểm thử revocation | Credential/session cũ vẫn dùng được | Integration test và propagation SLA |
| Không ghi test limitation | Kết luận bị phóng đại | Scope, sample và missing evidence rõ ràng |

## 23. Checklist production và audit readiness

1. **Scope:** Account, system, tenant, data và environment thuộc phạm vi đã được xác định?
2. **Risk:** Control objective gắn với threat/risk cụ thể?
3. **Ownership:** Mỗi control có owner, operator và reviewer?
4. **Policy:** Password, MFA, passkey, certificate và federation policy được phê duyệt?
5. **Enrollment:** Credential được đăng ký theo proofing và authorization phù hợp?
6. **Privileged access:** Admin có phishing-resistant MFA, JIT/approval và audit?
7. **Lifecycle:** Joiner-mover-leaver, dormant và orphan account được xử lý?
8. **Recovery:** Token/code có TTL, purpose, subject binding và one-time use?
9. **Session/token:** Expiry, rotation, revocation và reuse detection được kiểm thử?
10. **Federation:** Issuer, audience, key, claim mapping và deprovisioning được quản lý?
11. **Workload:** Service identity có owner, scope, expiry và rotation?
12. **Exceptions:** Có risk rationale, approver, compensating control và expiry?
13. **Logging:** Event đủ để điều tra nhưng không chứa secret?
14. **Privacy:** Evidence được tối thiểu hóa, phân quyền và retention?
15. **Design effectiveness:** Control design giải quyết rủi ro đã xác định?
16. **Operating effectiveness:** Có evidence chứng minh control chạy trong toàn kỳ?
17. **Population:** Nguồn population đầy đủ và có thể tái lập?
18. **Sampling:** Method, size và selection rationale được ghi?
19. **Findings:** Gap có impact, root cause, owner, due date và retest?
20. **Framework mapping:** Phiên bản, reference và applicability được xác định?
21. **Shared responsibility:** Trách nhiệm của tổ chức, cloud, IdP và vendor được phân định?
22. **Audit trail:** Thay đổi policy, approval, access review và evidence access có audit?
23. **Testing:** Có test negative, replay, bypass, recovery, revocation và failure mode?
24. **Governance:** Có periodic review, management sign-off và improvement process?

## 24. Bài tập tình huống

Một nền tảng học tập nhiều tenant chuẩn bị đánh giá kiểm soát truy cập. Tổ chức có policy yêu cầu MFA cho admin nhưng không có danh sách population admin được kiểm chứng. Một số tài khoản dùng chung vẫn tồn tại. Password reset qua email không revoke session cũ. Service account dùng API key không expiry. Helpdesk có thể thêm passkey nếu người gọi cung cấp tên và email. Đội compliance chỉ lưu screenshot cấu hình MFA tại ngày đánh giá.

**Yêu cầu:**

1. Xác định ít nhất **mười rủi ro/gap** trong design và operation.
2. Viết control objective cho privileged authentication, recovery, service identity và session revocation.
3. Xác định population và evidence cần thu thập để chứng minh MFA cho toàn bộ admin.
4. Thiết kế test of control với sample và expected result.
5. Đề xuất cách xử lý shared account, API key dài hạn và helpdesk override.
6. Thiết kế evidence package có source, period, owner, integrity và privacy controls.
7. Phân biệt design effectiveness với operating effectiveness.
8. Xây dựng remediation plan có owner, due date, compensating control và retest.
9. Giải thích vì sao screenshot MFA không đủ để kết luận toàn bộ authentication control hiệu quả.

**Gợi ý đối chiếu:** Cần population admin đầy đủ; account cá nhân và attribution; recovery assurance; session revocation; workload identity có expiry; helpdesk proofing/approval; evidence theo thời kỳ và sample test; ghi rõ scope và limitation.

## 25. Ghi nhớ

- **Authentication control** là chính sách, quy trình, công nghệ và evidence bảo vệ việc chứng minh danh tính.
- Compliance cần control objective có scope, owner, frequency, procedure, evidence và test method.
- Framework mapping không đồng nghĩa chứng nhận hoặc kết luận compliance.
- Control cần dựa trên risk và phân lớp workforce, customer, privileged, partner, workload và emergency account.
- Password, MFA, passkey, certificate, federation, session và recovery đều thuộc vòng đời kiểm soát.
- Recovery và exception không được trở thành đường bypass yếu hơn policy chính.
- Account lifecycle, access review, revocation và workload identity phải được kiểm chứng.
- Design effectiveness khác operating effectiveness; screenshot tại một thời điểm không chứng minh cả kỳ.
- Evidence cần nguồn, timestamp, scope, integrity và quyền truy cập; tuyệt đối không chứa secret.
- Sampling, test result, finding, remediation và retest phải có thể tái lập.
- Privacy và data minimization áp dụng cả với audit evidence.
- Mọi claim về framework phải nêu phiên bản, phạm vi và shared responsibility.

Authentication control có giá trị compliance khi **tổ chức xác định rõ rủi ro cần kiểm soát, triển khai hoạt động phù hợp trên đúng population, chứng minh được việc vận hành trong thời kỳ đánh giá và xử lý minh bạch mọi ngoại lệ**. Bằng chứng phải đủ để kiểm tra nhưng không trở thành nơi lưu trữ credential hoặc dữ liệu cá nhân quá mức.
