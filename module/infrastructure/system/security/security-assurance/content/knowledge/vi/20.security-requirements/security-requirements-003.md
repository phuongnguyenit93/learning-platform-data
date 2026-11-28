# Requirement về xác thực (Authentication Requirements) trong Security Assurance

## 1. Vì sao xác thực phải bắt đầu từ requirement?

Một ứng dụng hóa đơn SaaS cho phép nhân viên khách hàng đăng nhập bằng email và mật khẩu. Đội phát triển bổ sung MFA và cho rằng “bảo mật đăng nhập đã hoàn thành”. Tuy nhiên, tài khoản support admin vẫn có đường đăng nhập cũ không cần MFA; một session được tạo trước khi người dùng bị vô hiệu hóa vẫn dùng được; và một background worker dùng secret cố định có quyền truy cập nhiều tenant. Chỉ số “98% users đã đăng ký MFA” không cho biết các đường này có được bảo vệ hay không.

Đây là lý do phải viết **requirement về xác thực (authentication requirement)** thay vì chỉ liệt kê sản phẩm hoặc nút bật trong cấu hình. Requirement mô tả **ai cần xác thực, tại ranh giới nào, bằng loại bằng chứng nào, khi nào cần xác minh lại, tình huống lỗi phải xử lý ra sao và điều kiện nào được coi là đạt**.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu học tập là xây dựng cách **đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật. Vì vậy, bài học nối trực tiếp:

**Tài sản và rủi ro → mục tiêu xác thực → requirement có thể kiểm chứng → thiết kế control → thực thi → positive/negative tests → evidence → finding/remediation → residual risk.**

> “Người dùng có thể đăng nhập” chỉ chứng minh một chức năng hoạt động. “Những yêu cầu xác thực đã được đáp ứng trong phạm vi và thời kỳ được nêu” là một kết luận assurance đòi hỏi nhiều loại bằng chứng hơn.

### Tình huống xuyên suốt

Hãy tưởng tượng **Invoice SaaS**, nơi khách hàng doanh nghiệp dùng SSO, một số khách hàng dùng local accounts, nhân viên support có quyền quản trị có điều kiện, nhân viên dịch vụ dùng service identities và hệ thống có các API, background workers, ứng dụng mobile, export/download và partner integrations. Bài sẽ dùng bối cảnh giả định này để viết requirement, phân tích đường lạm dụng và xây phương án kiểm thử.

## 2. Xác thực là gì? Phân biệt với định danh và phân quyền

**Authentication (AuthN)** là quá trình xác minh rằng một thực thể đang tương tác có thể chứng minh quyền kiểm soát đối với yếu tố/bí mật/cơ chế xác thực được ràng buộc với một danh tính hoặc account theo chính sách. Xác thực có thể là người dùng, ứng dụng, workload hoặc thiết bị. Mức đảm bảo phụ thuộc vào phương pháp, cách đăng ký/bảo vệ authenticator, giao thức, trạng thái phiên và khả năng chống tấn công.

Các khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Identity proofing** | Danh tính thực hoặc thuộc tính đã được xác minh tới mức nào lúc đăng ký? | Kiểm tra thuộc tính nhân viên hoặc khách hàng theo yêu cầu nghiệp vụ. |
| **Identification/account discovery** | Hệ thống đang nói tới account/subject nào? | Nhập tên đăng nhập, chọn tổ chức hoặc tenant. |
| **Authentication (AuthN)** | Thực thể có chứng minh quyền kiểm soát authenticator hợp lệ của subject không? | Passkey challenge, mật khẩu kết hợp yếu tố thứ hai, khóa workload. |
| **Federation** | Hệ thống có tin assertion/token từ IdP đúng issuer và điều kiện không? | OIDC login với issuer đã đăng ký. |
| **Authorization (AuthZ)** | Subject đã xác thực có được làm hành động này trên resource này không? | User A được đọc invoice của tenant A nhưng không được đọc tenant B. |
| **Session management** | Trạng thái xác thực được duy trì, hết hạn, làm mới hoặc thu hồi ra sao? | Cookie phiên, token, session revocation. |
| **Auditing/accountability** | Có thể truy nguyên hành động và trạng thái xác thực không? | Audit event login, MFA, reset, privilege escalation. |

**Một access token hợp lệ không chứng minh người dùng có quyền đọc mọi resource.** OAuth scopes và resource authorization có thể cần kiểm tra bổ sung; một ID token dùng cho login cũng không mặc nhiên là access token thích hợp để gọi API.

### Identity assurance và authentication assurance

Một account có thể được xác thực rất mạnh về **quyền sở hữu authenticator** nhưng danh tính được khai báo ban đầu chưa được identity-proofing ở mức cao. Ngược lại, đã xác minh giấy tờ lúc onboarding không bảo đảm login về sau chống được phishing. Requirement phải ghi rõ thuộc tính nào thực sự cần và loại đảm bảo nào đang được đánh giá.

## 3. Xác định security objectives và threat scenarios

Đừng bắt đầu bằng câu “mọi nơi phải bật MFA” mà không biết mục tiêu nào cần giải quyết.

| Threat scenario | Tác nhân hoặc điều kiện | Mục tiêu xác thực | Control và giới hạn cần xét |
| --- | --- | --- | --- |
| **Credential stuffing** | Attacker thử nhiều cặp user/password bị lộ. | Giảm khả năng chiếm account qua mật khẩu. | MFA phù hợp, breached password screening, throttling/risk signals; authz vẫn riêng. |
| **Phishing/AiTM** | Attacker lừa user nhập bí mật/OTP hoặc proxy phiên. | Giảm nguy cơ kẻ khác xác thực thay user. | Phishing-resistant authenticators, origin binding, session controls. |
| **Session theft** | Attacker lấy cookie/token đã phát hành. | Hạn chế thời hạn/lạm dụng credential phiên. | Secure cookie/token handling, rotation, revoke, anomaly response. |
| **Account recovery takeover** | Attacker dùng quy trình reset/khôi phục yếu. | Đường khôi phục không được phá mức đảm bảo của login. | Recovery verification, notification, limits, audit. |
| **Admin path bypass** | Đường login cũ hoặc emergency account không có chính sách. | Mọi privileged path thuộc scope được bảo vệ. | Inventory, enforced strong auth, JIT/PAM và break-glass governance. |
| **Federation confusion** | Chấp nhận token sai issuer/audience/tenant. | Chỉ assertions từ trust configuration hợp lệ. | Issuer, audience, signature, state/nonce/PKCE validation đúng flow. |
| **Replay/misuse token** | Dùng token sai context hoặc sau revoke. | Chỉ chấp nhận chứng cứ xác thực đúng lần/đích/thời hạn. | Nonce/challenge/replay defense, exp/nbf, token scope và revocation. |
| **Service secret leak** | Workload credential nằm trong repo/CI logs. | Workload chứng minh danh tính với credential được quản lý. | Short-lived workload identity, secret rotation, effective permissions. |
| **Tenant account linking error** | Hai khách hàng có email giống nhau. | Không ghép nhầm subject/tenant. | Stable issuer+subject, tenant trust mapping, negative linking tests. |
| **Authentication service failure** | IdP/KMS/risk service timeout. | Bảo vệ truy cập nhạy cảm khi không thể xác minh. | Defined fail-secure behavior, availability/recovery trade-offs. |

### Mẫu requirement theo rủi ro

**RISK-AUTH-01:** Nếu một user credential bị phish, attacker có thể đăng nhập account và xuất hóa đơn Confidential.

**SECURITY OBJECTIVE:** Giảm khả năng xác thực trái phép và giới hạn quyền tiếp tục sử dụng khi credential/session bị compromise.

**YÊU CẦU:** Luồng đăng nhập và hành động rủi ro cao phải sử dụng phương thức xác thực đã duyệt theo mức đảm bảo tương ứng; các đường thay thế, reset, token refresh và session reuse phải được kiểm tra.

**BẰNG CHỨNG:** authentication policy + effective configuration + positive/negative/failure-mode tests + audit và revocation drill.

## 4. Cấu trúc một authentication requirement có thể nghiệm thu

Requirement tốt phải đủ cụ thể để hai reviewer độc lập có thể xác định **PASS, FAIL hoặc chưa đủ bằng chứng**.

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| **ID và mục tiêu** | Requirement này hỗ trợ security objective/risk nào? |
| **Subject population** | Customers, employees, admins, workload identities, API partners? |
| **Access path** | Browser, mobile, CLI, public API, internal API, batch, emergency? |
| **Authenticator/mechanism** | Loại phương pháp và điều kiện bảo vệ nào được phê duyệt? |
| **Assurance condition** | Rủi ro, sensitivity, privilege và context nào yêu cầu mạnh hơn? |
| **Preconditions** | Account enrollment, lifecycle, device/key/state đã được kiểm tra? |
| **Expected outcome** | Khi đúng, sai, quá hạn, thiếu signal hoặc bị thu hồi phải xử lý thế nào? |
| **Limits/thresholds** | Session age, retries, token lifetime, time-to-revoke do ai phê duyệt? |
| **Owner** | Ai thiết kế, triển khai, vận hành, xác minh và quyết định risk? |
| **Verification** | API/config/code inspection, conformance test, negative test, drill? |
| **Evidence** | Environment, version, population, expected/observed, timestamp? |
| **Exceptions** | Trường hợp ngoài scope/legacy có risk approval, hạn và biện pháp bù? |

### Mẫu câu viết chặt

> **AUTH-LOGIN-01:** Đối với mọi interactive login path vào production application được phân loại High Impact, hệ thống **phải** thực thi cơ chế xác thực trong baseline được phê duyệt trước khi tạo authenticated session; đường login cũ hoặc fallback không được bỏ qua policy; thử nghiệm bằng identity chưa đáp ứng yêu cầu **phải bị từ chối**, có audit event phù hợp.

So với “ứng dụng cần MFA”, requirement này nêu **population, scope, trigger, outcome và phép kiểm chứng**, đồng thời không tự ấn định một phương thức phù hợp cho mọi ngữ cảnh.

## 5. Phân loại xác thực theo loại principal và mức rủi ro

Không thể đo và áp dụng cùng một control cho mọi thực thể.

| Principal | Đặc điểm | Requirements cần xem |
| --- | --- | --- |
| **Customer user** | Truy cập dữ liệu/nhật ký nghiệp vụ của tổ chức. | Credential, phishing resistance theo threat, session, account recovery, federation. |
| **Employee/contractor** | Quản lý chức năng nội bộ và truy cập thông tin khách hàng. | Federated login, MFA, device posture khi cần, offboarding. |
| **Privileged administrator** | Có thể thay IAM/policy, keys, data hoặc production config. | Strong auth, privileged session/JIT, secure recovery, break-glass và audit. |
| **Service/workload** | Không có tương tác người, có thể chạy thường xuyên. | Workload identity, certificate/key/secret lifecycle, audience, mutual auth và rotation. |
| **Partner/API client** | Hệ thống bên ngoài gọi APIs. | Client identity, key protection, token audience, scopes, trust contract và revoke. |
| **Automation/CI/CD** | Truy cập artifact registry, cloud control plane hoặc deploy production. | Ephemeral identities, least privilege, supply-chain provenance, secret hygiene. |
| **Device** | Một tín hiệu ngữ cảnh hoặc yếu tố ràng buộc. | Device identity/posture validity và cách quyết định khi signal thiếu. |

### Đừng gắn “MFA bắt buộc” vào service principal

MFA là khái niệm chủ yếu gắn với người dùng interactive. Với workload, requirement đúng thường liên quan **mTLS, asymmetric client authentication, workload identity, token short lifetime, audience binding và key/secret custody**, thay vì dựng một “OTP ảo” cho bot.

### Contextual authentication

Có thể yêu cầu mức xác thực mạnh hơn cho **sensitive action** như thay phương thức MFA, thêm người quản trị, xuất dữ liệu hàng loạt, đổi recovery settings hoặc chuyển tiền. Nhưng người đã vượt step-up vẫn cần **authorization độc lập theo resource/action**.

## 6. Xác định mức đảm bảo: không nhầm IAL, AAL và FAL

Trong các tài liệu chuyên môn về digital identity, thường phân biệt:

- **Identity Assurance Level (IAL):** mức tin cậy đối với quy trình xác minh/thiết lập danh tính.
- **Authenticator Assurance Level (AAL):** mức tin cậy đối với quy trình và phương pháp xác thực.
- **Federation Assurance Level (FAL):** mức đảm bảo của giao thức/chuỗi tin cậy khi truyền thông tin danh tính giữa các bên.

Các thuật ngữ này có thể xuất hiện trong bộ hướng dẫn NIST SP 800-63. Khi có yêu cầu tuân thủ cụ thể, phải dùng **đúng phiên bản tài liệu, định nghĩa, điều kiện và profile được tổ chức phê duyệt**; không suy “có MFA = AAL2/AAL3” chỉ từ tên tính năng.

### Xác định mức assurance theo risk

1. Định nghĩa resource/action, dữ liệu và mức hậu quả nếu giả mạo.
2. Mô tả attacker capabilities: phishing, malware, OTP interception, stolen token, insider.
3. Phân loại user populations và lựa chọn kiến trúc (local/federated/workload).
4. Xác định mục tiêu đảm bảo và các constraints bắt buộc trong scope.
5. Chọn authenticators/protocol/configuration phù hợp.
6. Viết requirements gồm **recovery, enrollment, lifecycle và fallback**, không chỉ login.
7. Chỉ kết luận đáp ứng level sau khi có evidence cho tất cả điều kiện cần của profile áp dụng.

## 7. Authentication factors, MFA và mức chống phishing

Các nhóm yếu tố thường gồm **something you know** (bí mật biết), **something you have** (thiết bị/authenticator) và **something you are** (đặc tính sinh trắc được sử dụng trong hệ thống phù hợp). Phương pháp cần được đánh giá theo cách triển khai, không chỉ nhãn marketing.

| Cơ chế | Thuộc tính thường gặp | Điểm kiểm chứng |
| --- | --- | --- |
| **Password** | Bí mật ghi nhớ, dễ bị phishing/reuse. | Password storage/transport, blocklist, rate limit, reset và reuse exposure. |
| **TOTP/OTP app** | Mã ngắn thay đổi theo thời gian. | Enrollment, secret protection, replay window, phishing/AiTM risk. |
| **SMS OTP** | OTP qua kênh di động. | SIM swap, interception, delivery, fallback và giới hạn của phương thức. |
| **Push approval** | Phản hồi trên app/thiết bị. | Push fatigue, contextual matching, number matching nếu thiết kế yêu cầu. |
| **WebAuthn/FIDO2 passkey/security key** | Public-key challenge-response gắn với relying party/origin; có thể chống phishing khi triển khai đúng. | Registration ceremony, RP ID/origin, challenge, user verification, authenticator lifecycle. |
| **Client certificate/mTLS** | Xác minh danh tính client/workload theo trust model. | Key protection, cert chain/name, rotation, revocation, effective authorization. |
| **Hardware-backed authenticator** | Một số thuộc tính bảo vệ khóa bằng phần cứng. | Attestation/profile và yêu cầu áp dụng; không tự suy mức assurance cao chỉ từ nhãn. |

### MFA không đồng nghĩa phishing-resistant

OTP có thể bị attacker thu thập rồi sử dụng ngay trong phiên proxy. Một số phương thức mật mã như WebAuthn có khả năng ràng buộc xác thực với RP/origin giúp giảm lớp tấn công đó, **nếu server/client triển khai và xác minh đúng**.

### Phân biệt biometric unlock

Sinh trắc học trên thiết bị có thể được dùng để **mở khóa một authenticator cục bộ**; điều đó không nhất thiết có nghĩa ứng dụng nhận hoặc lưu khuôn mặt/vân tay. Requirements cần xác định user verification, device trust và privacy boundary, không mặc định mọi thiết bị có biometric đều mang cùng mức đảm bảo.

## 8. Password requirements: chính sách có thể kiểm chứng

Với những hệ thống vẫn dùng password, requirement nên chú trọng **khả năng chống credential attacks và chất lượng lifecycle** hơn là các quy tắc phức tạp gây tái sử dụng mật khẩu.

### Nhóm yêu cầu

| Nhóm | Requirement minh họa | Cách kiểm chứng |
| --- | --- | --- |
| **Enrollment/change** | Áp dụng quy tắc độ dài, password allowlist/blocklist và xử lý Unicode theo baseline đã duyệt. | Positive/negative tests với input dài, phổ biến, Unicode, whitespace. |
| **Breached secrets** | Từ chối mật khẩu trong danh sách phổ biến hoặc đã lộ theo policy, không gửi password plaintext tới dịch vụ không tin cậy. | Test password blocklist và cách tích hợp kiểm tra an toàn. |
| **Storage** | Password verifier được lưu bằng cơ chế password hashing chuyên dụng có salt và work factor phù hợp, không plaintext hoặc hash nhanh đơn giản. | Security design/code/config inspection, migration tests. |
| **Transport** | Đường gửi credentials được bảo vệ và client không bỏ certificate validation. | TLS scan, invalid certificate tests, error-path checks. |
| **Online guessing** | Có throttling/rate control và risk response theo user/source/context. | Controlled credential stuffing simulation, metrics, false-deny tests. |
| **Change/reset** | Reset được kiểm tra an toàn, token có hạn và single-use theo policy; không tiết lộ secret trong log. | Replay/expired token tests, audit, notification review. |
| **Rotation** | Thay khi có dấu hiệu compromise hoặc yêu cầu hợp lệ; không mặc định đổi định kỳ không có căn cứ. | Breach response, expiration policy, exception review. |
| **Enumeration** | Response/timing/log không tiết lộ account existence không cần thiết. | Known/unknown account tests và rate-aware comparison. |

### Password storage

Các lựa chọn thông dụng gồm **Argon2id, scrypt, bcrypt** với tham số phù hợp nền tảng và chính sách được duyệt. Không dùng SHA-256 đơn thuần để lưu password verifier; phải xét salt, work factor, quản lý tham số, migration và resource exhaustion khi xử lý login.

Không copy các thông số hash hoặc quy tắc độ dài bất kỳ rồi tuyên bố đáp ứng chuẩn. Độ dài, tham số và chính sách cụ thể phụ thuộc baseline, phiên bản hướng dẫn và threat model hiện hành.

### Tạo trải nghiệm phù hợp bảo mật

Cho phép password managers và paste khi có thể, tránh cơ chế buộc người dùng dùng lại một mẫu yếu. UX quá khó có thể làm tăng **password reuse, ghi mật khẩu ra ngoài hoặc sử dụng recovery liên tục**.

## 9. Enrollment và binding authenticator

Nhiều hệ thống chú trọng login nhưng bỏ qua việc **đăng ký authenticator ban đầu hoặc thêm authenticator mới**. Đó có thể là con đường takeover.

### Requirements cần có

1. Chỉ account đã được xác lập đúng quy trình mới được thêm authenticator.
2. Đăng ký authenticator mới yêu cầu chứng cứ hiện tại hoặc step-up phù hợp với rủi ro.
3. Thiết bị, security key hoặc secret được ràng buộc tới **đúng account và tenant**.
4. Challenge có tính mới và thời hạn; verify đúng context, không chấp nhận replay.
5. Khi thêm/xóa/thay authenticator, tạo audit và notification phù hợp.
6. Recovery và re-enrollment không được là đường dễ hơn cho attacker.
7. Mất thiết bị, reset thiết bị, tài khoản bị khóa hoặc thay IdP đều có runbook kiểm soát.

### Case: attacker thêm authenticator

Một user đăng nhập bằng password bị lộ. Endpoint “add passkey” cho phép đăng ký trực tiếp không có kiểm tra mới. Attacker thêm passkey của mình rồi khóa user. Dù lần đăng nhập sau dùng passkey mạnh, **account đã bị chiếm qua enrollment yếu**. Vì vậy cần test **new authenticator enrollment, recovery, deletion và reassociation**.

## 10. WebAuthn/passkeys: requirements thiết kế và negative tests

Passkeys và WebAuthn dùng public-key cryptography; private key thường được bảo vệ ở authenticator/provider, còn server lưu public-key credential và metadata cần thiết. **Server vẫn phải xác minh toàn bộ ceremony**, không chỉ thấy client báo success.

| Giai đoạn | Requirement phải kiểm chứng |
| --- | --- |
| **Registration** | Challenge đủ khó đoán, mới và có hạn; response liên kết đúng session/account và tenant. |
| **RP binding** | RP ID và origin phù hợp những origins/rpIds được cho phép; chống phishing/cross-origin misuse. |
| **Authenticator data** | Xác minh RP ID hash, user presence/user verification flags theo policy, format và signature/attestation khi cần. |
| **Credential storage** | Public key, credential ID, account binding, trạng thái và metadata được lưu an toàn. |
| **Authentication** | Challenge được đối chiếu, signature được kiểm chứng với public key đúng credential, subject binding chính xác. |
| **Replay/mismatch** | Wrong challenge, origin, credential, RP ID, account hoặc expired ceremony bị từ chối. |
| **Credential lifecycle** | Thêm/xóa/disable passkey được bảo vệ, audit và có recovery phù hợp. |
| **Synced passkeys** | Đánh giá yêu cầu device binding, sync và assurance theo loại authenticator/trust; không dựa riêng vào signature counter để chứng minh không clone. |

### Không tự viết WebAuthn parser/protocol

Ứng dụng nên dùng thư viện được duy trì, xác minh cấu hình RP ID, trusted origins, user verification và binding logic ở application level. Với synced passkeys, signature counter có thể không tăng như các thiết bị phần cứng đơn lẻ; thiết kế phải xét loại authenticator và signal bổ sung, không gán mọi trường hợp counter không đổi thành lỗi.

### Recovery là một phần không thể thiếu

Nếu user mất mọi passkey, yêu cầu phục hồi cần cân bằng security và availability, nhưng không thể dùng đường reset chỉ dựa vào email có độ tin cậy thấp trong mọi bối cảnh. Phải xác định risk tier, các bước xác minh, notification, hold/restriction nếu cần và review hành vi gian lận.

## 11. MFA requirements và step-up authentication

MFA có thể được yêu cầu lúc đăng nhập hoặc khi **thực hiện hành động nhạy cảm**. Cần viết rõ phạm vi thay vì chỉ có một cờ “MFA enabled”.

### Ví dụ mapping theo hành động

| Action | Risk | Requirement gợi ý |
| --- | --- | --- |
| Xem dashboard dữ liệu thông thường. | Theo data sensitivity và tenant. | Authentication được duyệt, session hợp lệ. |
| Export toàn bộ invoices. | Data disclosure quy mô lớn. | Authorization cụ thể và recent auth/step-up nếu policy yêu cầu. |
| Thêm global admin. | Privilege escalation. | Strong authentication và dual control/JIT theo governance. |
| Đổi MFA hoặc recovery contacts. | Account takeover persistence. | Reauthentication/step-up và secure notification. |
| Tải backup hoặc dùng KMS Decrypt. | Truy cập dữ liệu nhạy cảm. | Workload/admin identity assurance, privileged authorization và audit. |
| Đăng ký IdP tenant mới. | Federation trust takeover. | Privileged verification, proof of domain/tenant ownership và approval. |

### “Recently authenticated” phải có định nghĩa

Nếu requirement nêu “recent authentication”, cần định nghĩa **tối đa bao lâu**, hành động nào phải step-up, có dùng auth_time/loa hoặc signal tương đương theo protocol không, refresh token có được tính là reauthentication không, và điều kiện nào buộc user xác thực lại.

**Authentication mạnh hơn không phải authorization rộng hơn.** Một user qua MFA vẫn không được phép export invoice của tenant khác.

## 12. Chính sách đăng nhập: retries, throttling và account enumeration

Requirement chống brute-force cần tránh hai cực đoan: **không chặn gì** hoặc **khóa vô thời hạn khiến attacker dễ gây DoS**.

### Thiết kế theo attacker và người dùng hợp lệ

- Giới hạn tốc độ theo account, source, device signal và behavior khi phù hợp.
- Phân biệt một attacker phân tán IP với một user gõ sai.
- Cân nhắc progressive delay, risk-based challenges, notification hoặc hỗ trợ recovery.
- Kiểm soát resource exhaustion của password verifier, email/SMS OTP, recovery endpoint.
- Không để attacker lockout hàng loạt tài khoản bằng những yêu cầu giả.
- Có cơ chế hỗ trợ khách hàng hợp lệ mà không tạo “admin bypass” không được audit.

### Mẫu acceptance criteria

**AUTH-RATE-01:** Với login và recovery endpoints trong scope, hệ thống phải giới hạn online guessing theo policy, ghi các sự kiện bị chặn có provenance, đồng thời các thử nghiệm hợp lệ sau khi kết thúc điều kiện chặn phải hoạt động theo yêu cầu; failure mode không tiết lộ account existence qua response không cần thiết.

**Điểm quan trọng:** số lượng retries, mức delay và ngưỡng cụ thể phải được xác định bởi baseline và risk owner; đừng chép một giá trị chung cho mọi public API mà không kiểm tra usability/DoS.

## 13. Account recovery, reset và credential replacement

**Đường phục hồi** thường là con đường thực tế mà attacker cố khai thác khi primary authentication mạnh.

### Những flow cần trong inventory

- Forgot password và reset qua email/token.
- Khôi phục khi mất MFA/passkey hoặc thay điện thoại.
- Unlock account sau lockout.
- Account linking/merging.
- Thay email hoặc số điện thoại dùng để nhận thông báo.
- Chuyển employee từ IdP này sang IdP khác.
- Break-glass recovery cho tenant admin.
- Chuyển quyền account khi nhân viên rời tổ chức.

### Requirements cần test

| Requirement | Thử nghiệm gợi ý |
| --- | --- |
| Reset token có entropy, hạn dùng và binding phù hợp. | Guess/replay/expired/wrong account tests. |
| Token bị vô hiệu sau khi dùng theo chính sách. | Redeem twice hoặc sau password change. |
| Account recovery không tự bypass strong auth cần thiết. | Thử khôi phục bằng đường yếu đối với privileged account. |
| Thay authenticator tạo security notification. | Kiểm tra recipient/channel và không lộ secret. |
| Sessions/tokens cũ được xử lý sau credential reset. | Verify revocation/rotation với đường truy cập trong scope. |
| Không tiết lộ account tồn tại khi không cần. | Compare known/unknown reset flows. |
| Support recovery có approval, audit và tách nhiệm vụ. | Test support không tự takeover account. |

### Không tin “security question” là yếu tố đủ mạnh

Những câu trả lời như tên trường học hoặc ngày sinh có thể bị đoán, thu thập qua mạng xã hội hoặc đã bị lộ. Không dùng chúng làm bằng chứng duy nhất cho khôi phục account rủi ro cao khi không có controls bổ sung phù hợp.

## 14. Session authentication và vòng đời phiên

Sau khi login thành công, ứng dụng thường không yêu cầu user giải lại challenge cho mỗi request; thay vào đó dùng session/cookie/token. **Vì vậy session management là phần của authentication requirements, không phải chuyện phụ.**

### Session lifecycle

~~~mermaid
flowchart TD
    A["Unauthenticated request"] --> B["Credential / federation authentication"]
    B --> C{"Verification succeeds?"}
    C -- "No" --> D["Deny, limit attempts and audit"]
    C -- "Yes" --> E["Issue bound session with approved properties"]
    E --> F["Evaluate expiry, context and policy at access"]
    F --> G{"High risk or revoked?"}
    G -- "Step-up required" --> H["Reauthenticate / step-up"]
    H --> F
    G -- "Revoked or expired" --> I["Deny, invalidate and audit"]
    G -- "Allowed" --> J["Authorize specific action and resource"]
    J --> F
    E --> K["Logout / offboarding / incident"]
    K --> I
~~~

### Yêu cầu quan trọng

- Sinh session identifiers đủ ngẫu nhiên, không lộ trong URL/query/logs.
- Không tái sử dụng ID phiên trước đăng nhập để tránh session fixation; rotate hoặc issue lại ở boundary phù hợp.
- Cookies mang session phải có **Secure**, **HttpOnly**, **SameSite** phù hợp use case và domain/path scope; chính sách CSRF cần kiểm tra riêng.
- Định nghĩa idle timeout, absolute lifetime, renewal/reauthentication theo rủi ro và profile.
- Xử lý logout, forced logout, password reset, role change, MFA change và offboarding.
- Bảo vệ session store, token signing keys, refresh tokens và cache state.
- Tách session authentication khỏi authorization mỗi resource/action.
- Audit lifecycle events nhưng không log token/cookie plaintext.

### Cookie flags không thay CSRF protection

**SameSite** giúp giảm một số tình huống CSRF nhưng không tự bảo vệ mọi luồng, đặc biệt có cross-site requirements hoặc browser differences. Khi dùng cookie-based authentication, cần xét CSRF protection, origin checks, content-type và endpoint semantics theo architecture thực tế.

## 15. Access tokens, refresh tokens và token validation

Trong nhiều hệ thống OAuth/OIDC, **access token** là credential để truy cập resource server, còn **ID token** là thông tin xác thực dành cho relying party trong ngữ cảnh OIDC. Không tùy tiện hoán đổi hai loại.

| Thành phần | Requirement trọng tâm |
| --- | --- |
| **Token issuer** | Chỉ chấp nhận issuer thuộc trust registry được cấu hình. |
| **Audience** | Token phải dành đúng API/client/resource theo flow. |
| **Signature/algorithm** | Xác minh chữ ký bằng key phù hợp issuer và allowlist algorithm được duyệt; không tin alg từ token để tự chọn xử lý yếu. |
| **Time claims** | Kiểm tra expiration, not-before và các điều kiện thời gian liên quan với clock skew đã duyệt. |
| **Scope/claims** | Không tự coi token có scope là được phép mọi object; claims cần nguồn tin cậy, namespace và validation. |
| **Token substitution** | Không dùng ID token làm API bearer token khi không có thiết kế cho phép; không chấp nhận token sai mục đích. |
| **Refresh lifecycle** | Token rotation, replay detection khi áp dụng, storage, revocation và sessions. |
| **Revocation** | Đo thời gian tới effective deny trên resources, kể cả caches và downstream. |
| **Key rotation** | JWKS/certificate/key trust được kiểm soát và có rollback/migration phù hợp. |
| **Replay/binding** | Dùng sender-constrained tokens hoặc cơ chế tương ứng nếu threat cần, kiểm chứng điều kiện thực thi. |

### Token có chữ ký hợp lệ vẫn có thể sai mục đích

Ví dụ một token do IdP thật phát hành nhưng có **audience = account-management API**, không được dùng để gọi invoice API nếu policy không cho phép. Một token có claim tenantId cũng không nên thay thế server-side tenant/resource authorization.

### Không đưa token vào local storage một cách máy móc

Lựa chọn cookie, memory hoặc nơi lưu khác cần theo architecture, threat model và nền tảng (browser/mobile/server). Phải xét XSS, CSRF, replay, persistence, cross-origin, logout và recovery; không có một câu “mọi app phải dùng localStorage” hoặc “mọi app chỉ được dùng cookie” phù hợp tất cả.

## 16. OIDC/OAuth federation: requirement về trust chain

Một tổ chức SaaS cho phép khách hàng đăng nhập bằng Identity Provider (IdP). Federation có thể giảm nhu cầu quản lý mật khẩu ở ứng dụng, nhưng làm phát sinh trust boundaries giữa **browser/client, relying party (RP), authorization server/IdP, token endpoint và resource server**.

### Luồng khái niệm

~~~mermaid
sequenceDiagram
    participant U as Browser / user
    participant RP as Invoice SaaS client / RP
    participant IDP as Customer-approved IdP
    participant API as Invoice resource server
    U->>RP: Start authentication
    RP->>RP: Create state, nonce and PKCE verifier as applicable
    RP-->>U: Redirect to registered IdP
    U->>IDP: Authenticate with required method
    IDP-->>U: Authorization response
    U->>RP: Return response to registered redirect URI
    RP->>RP: Validate state and correct flow binding
    RP->>IDP: Exchange authorization code with PKCE/client authentication
    IDP-->>RP: Tokens issued for configured client
    RP->>RP: Verify ID token issuer, audience, nonce, signature, times
    RP-->>U: Establish authenticated session
    U->>API: Request invoice action with appropriate access credential
    API->>API: Validate token and authorize resource/action
    API-->>U: Authorized result only
~~~

Sơ đồ minh họa một dạng OIDC Authorization Code flow; các biến thể cần được đánh giá theo profile/protocol áp dụng. Không suy rằng tất cả tokens đều phải được đưa về browser; server-side/BFF và mobile có thiết kế khác.

### Các yêu cầu federation trọng yếu

| ID | Requirement gợi ý | Kịch bản negative |
| --- | --- | --- |
| **AUTH-FED-01** | RP chỉ tin IdP/issuer đã đăng ký cho tenant và client đúng. | Token từ một IdP hợp lệ nhưng không được tenant cho phép. |
| **AUTH-FED-02** | Redirect/callback URI phải khớp cấu hình tin cậy; không dùng open redirect chuyển code/token ngoài scope. | Callback khác domain, redirect lồng hoặc URI tùy ý. |
| **AUTH-FED-03** | Bảo vệ correlation của login transaction bằng state, nonce, PKCE theo flow/profile. | Login CSRF, state mismatch, code substitution, verifier sai. |
| **AUTH-FED-04** | Xác minh token signature, issuer, audience, times và các claim bắt buộc theo profile. | Wrong issuer/audience, expired token, key không tin cậy. |
| **AUTH-FED-05** | Ràng buộc account với subject ổn định trong issuer/tenant context. | Hai IdP cùng subject string/email nhưng là hai người khác. |
| **AUTH-FED-06** | Tenant IdP onboarding và đổi federation config cần authority validation, review và audit. | User thông thường thêm IdP do attacker kiểm soát. |
| **AUTH-FED-07** | Failure của IdP/trust configuration không dẫn tới cho phép đăng nhập yếu ngoài policy. | IdP timeout, key rotation lỗi, federation metadata hỏng. |
| **AUTH-FED-08** | Mapping roles/groups từ claims được kiểm soát, không tự cấp quyền quản trị ngoài quy định. | Claim group tự khai không tạo quyền PlatformAdmin. |

### Account linking theo email là rủi ro

Email có thể thay đổi hoặc tái sử dụng; hai tenants có thể đăng nhập cùng một email nhưng là hai subjects khác nhau. Một khóa liên kết an toàn thường cần **issuer + subject + tenant trust context** cùng quy trình account linking đã phê duyệt; không dựa riêng vào email để quyết định quyền truy cập dữ liệu.

### Token trust cần qua nhiều tầng

OIDC ID token trả lời câu hỏi RP có thể thiết lập danh tính theo trust profile hay không. Khi gọi API, resource server phải kiểm tra **access token đúng audience/issuer/scope và authorization nghiệp vụ**. Chỉ validate ID token ở frontend không chứng minh resource server có kiểm tra quyền.

## 17. SAML/enterprise SSO: những requirement riêng

Một số khách hàng doanh nghiệp dùng SAML federation hoặc hệ thống SSO legacy. Requirements phải theo protocol/profile cụ thể chứ không dùng toàn bộ check của OIDC.

- **Trusted IdP metadata:** entity ID, signing certificate, endpoints và metadata lifecycle.
- **Signature validation:** assertion/response signature theo profile; bảo vệ chống XML signature wrapping và canonicalization misuse.
- **Audience/recipient/destination:** assertion chỉ được chấp nhận đúng Service Provider và endpoint.
- **InResponseTo/transaction binding:** response tương ứng request nếu flow yêu cầu, tránh unsolicited assertion misuse ngoài policy.
- **Time conditions:** NotBefore, NotOnOrAfter và clock skew theo cấu hình được duyệt.
- **Subject/NameID mapping:** không nhầm subject giữa tenants, IdPs hoặc account tái sử dụng.
- **Replay prevention:** quản trị assertion IDs và lifetime.
- **Attribute/role mapping:** claims được validate trước khi cấp quyền.
- **Certificate/metadata rotation:** diễn tập thay khóa, thời gian chồng lấn và xử lý fail securely.
- **Single logout:** hiểu limitations và hành vi session revocation của mỗi hệ thống.

**Không tự viết SAML parser hoặc XML signature validator.** Ưu tiên thư viện duy trì và profile được hỗ trợ; test cần kiểm tra các trường hợp chữ ký hợp lệ nhưng assertion có audience hoặc subject sai, không chỉ trường hợp XML hỏng.

## 18. Workload, machine-to-machine và API client authentication

Không phải mọi tương tác đều có browser. Một invoice worker, CI runner, vendor integration và backup service đều có danh tính cần được xác thực tại boundary riêng.

| Mechanism | Use case | Assurance requirements |
| --- | --- | --- |
| **mTLS client certificate** | Service-to-service hoặc partner kết nối có identity certificate. | Certificate chain, SAN/name mapping, key protection, rotation/revocation và authorization độc lập. |
| **OAuth client credentials** | Backend service nhận access token theo client identity. | Confidential client authentication, scopes/audience, token lifetimes, secrets/keys và revoke. |
| **Workload identity federation** | Pod/VM/CI workload đổi attested identity lấy credential ngắn hạn. | Issuer trust, audience, subject binding, token freshness, policy và pipeline trust. |
| **Managed identity / instance identity** | Service lấy credentials từ platform identity. | Effective policy, metadata endpoint protection, workload/instance boundary. |
| **API key** | Một số đối tác hoặc API legacy. | Random/high entropy, secure distribution/storage, scope, expiration/rotation, denylist và audit; không coi API key đơn thuần là user identity proof. |
| **Signed request protocol** | Yêu cầu xác thực từng message/action. | Canonicalization, signature, key ID, timestamp/nonce, replay defense và domain separation. |

### Requirement không được bỏ qua

1. Mỗi workload principal có **owner, purpose, trust source và allowed audience**.
2. Credential không bị hardcode vào source repository, container image, shared build artifact hoặc log.
3. Thời hạn và rotation phù hợp threat model; có phương án emergency revoke.
4. Verification diễn ra tại **resource boundary**, không chỉ trong private network.
5. Workload identity không tự được phép mọi database/query/tenant; authorization/least privilege vẫn cần.
6. Không sử dụng wildcard privilege nếu không có nhu cầu được phê duyệt và compensating controls.
7. Control failure (IdP timeout, certificate expiry) không mở đường fallback vô danh.
8. Audit và monitoring cho privileged machine access có thể correlation tới workload deployment/version.

### Ví dụ threat

CI runner dùng long-lived cloud access key để deploy và đọc KMS. Nếu dependency build script bị compromise, attacker có thể lấy key rồi truy cập bên ngoài runner. Requirement có thể ưu tiên **ephemeral workload identity ràng buộc đúng pipeline/repository/environment**, quyền tối thiểu, artifact verification và denied-use tests.

## 19. Xác thực tương hỗ: peer identity khác resource permission

**Mutual TLS (mTLS)** cho phép hai phía thiết lập kênh trong đó client có thể chứng minh quyền kiểm soát private key tương ứng certificate được tin cậy. Nhưng cần phân biệt:

- **Certificate trusted:** chain thuộc CA/trust anchor được phê duyệt.
- **Peer identity mapped:** SAN/SPIFFE ID hoặc identifier khác được gắn với workload cụ thể.
- **Peer authorization:** identity đó được gọi operation/resource nào theo policy.
- **Business authorization:** request có được thao tác dữ liệu khách hàng/tenant cụ thể?

Một service có cert hợp lệ từ CA rộng **không nên mặc nhiên có quyền Decrypt, EXPORT hoặc ADMIN**. Các quyền được quyết định theo policy riêng ở đúng boundary.

### Negative tests

- Certificate từ CA ngoài trust store bị từ chối.
- Certificate hợp lệ nhưng SAN/identity không khớp resource/service policy bị từ chối.
- Certificate hết hạn hoặc đã bị thu hồi theo chính sách không được dùng.
- Service A có mTLS hợp lệ vẫn không được gọi admin operation của B.
- Khi certificate rotation, các clients hợp lệ tiếp tục hoạt động theo transition plan mà không tắt verification.

## 20. Tenant identity binding và account linking

Với multi-tenant SaaS, yêu cầu không chỉ “user được xác thực” mà còn **user thuộc tenant nào và danh tính đó được liên kết hợp lệ với quyền nào**.

### Failure modes phổ biến

- RP tin tenantId trong query/header do browser tự gửi để chọn policy.
- Email trùng giữa hai IdP bị coi là một global account.
- Customer admin tự đổi tenant federation URL sang attacker IdP.
- Một login flow hợp lệ được trả callback vào session của tenant khác.
- User bị deprovision ở tenant A nhưng còn liên kết cũ sang tenant B.
- Service account dùng cùng client ID/secret cho mọi tenant nhưng audit không có tenant context.

### Requirement minh họa

**AUTH-TEN-01:** Khi tạo authenticated principal, hệ thống phải ràng buộc subject với **issuer đã đăng ký, tenant association được xác minh và account lifecycle state**. Tenant association không được suy chỉ từ email domain hoặc client-provided tenant ID; mọi thay đổi account link phải có policy và audit.

**AUTH-TEN-02:** Không một identity trust mapping nào được dùng để tự cấp quyền truy cập objects của tenant khác; access tokens và sessions được đánh giá trong correct tenant context.

### Kiểm thử

Tạo hai tenants giả và hai subjects có email giống nhau nhưng issuers khác nhau; đổi issuer, tenant alias, domain, redirect và subject linking. Xác minh không có session crossover, role bleed hoặc account takeover; kết hợp **AuthN test và object-level AuthZ test** để kiểm chứng toàn tuyến.

## 21. Admin authentication, break-glass và privileged sessions

Privileged access có rủi ro lớn vì admin có thể thay cấu hình, tài khoản, secret, KMS, log hoặc dữ liệu khách hàng.

### Những paths phải kiểm kê

- Cloud control plane, Kubernetes API, production database, KMS/HSM administration.
- Support console, super-admin UI, tenant admin provisioning.
- CI/CD deployment control, artifact signing key management.
- Emergency access, break-glass accounts, out-of-band recovery.
- CLI, API, VPN/ZTNA, bastion, remote support tools.

### Requirements trọng yếu

| ID | Requirement | Evidence |
| --- | --- | --- |
| **AUTH-PRIV-01** | Privileged interactive paths dùng phương thức xác thực mạnh theo baseline, không có bypass legacy. | Full inventory, policy readback, invalid-auth tests. |
| **AUTH-PRIV-02** | Privileged elevation cần recency/step-up/JIT/approval theo mức rủi ro. | Session/elevation trace, short-lived grant test. |
| **AUTH-PRIV-03** | Privileged sessions được giới hạn, giám sát và thu hồi khi kết thúc/incident. | Effective revoke test, privileged action audit. |
| **AUTH-PRIV-04** | Break-glass credentials được bảo vệ và chỉ sử dụng theo quy trình, có alert và hậu kiểm. | Restricted inventory, access drill, review records. |
| **AUTH-PRIV-05** | Support/admin không thể tự liên kết account khách hàng hoặc reset MFA ngoài authority. | Dual-control/support recovery tests. |

### Break-glass không đồng nghĩa yếu toàn bộ policy

Emergency access có thể phải hoạt động khi IdP chính bị lỗi. Thiết kế cần tính sẵn sàng **nhưng vẫn giới hạn số accounts, nơi giữ authenticator, kiểm soát truy cập, audit, notification, post-use rotation và khả năng review**. Không gán “except admin” rồi loại toàn bộ emergency path khỏi assurance.

## 22. Mobile, native app và public client requirements

Mobile và desktop native clients thường không giữ được client secret lâu dài như server confidential client. Những flows này cần requirements phù hợp:

- Dùng authorization flow được duyệt cho public client, chẳng hạn code flow với PKCE trong profile phù hợp.
- Redirect/deep-link và callback có kiểm tra để tránh code interception/misrouting.
- Không nhúng OAuth client secret, API key production hoặc signing private key vào application binary.
- Bảo vệ token/key trong OS-provided secure storage khi có thể, xét compromised/rooted device trong threat model.
- Session/token refresh, device loss, sign-out và remote revocation được kiểm chứng.
- Không để debug logging, analytics SDK hoặc crash reports thu tokens hay PII.
- Ràng buộc account switching/tenant switching với session và authorization đúng.
- App update, offline mode và thiết bị cũ có policy rõ.

Một native app không nên chọn flow chỉ vì web frontend đang dùng; client type, ability to keep secrets, OS/browser trust boundary và redirect mechanisms khác nhau. Requirements cần nêu platform và test từng loại client.

## 23. API authentication và authorization boundary

Không phải mọi API cần cùng loại authentication, nhưng mọi **protected endpoint/action** cần có requirement rõ.

| Endpoint | Authentication requirement | Ghi chú |
| --- | --- | --- |
| Public health/status có dữ liệu không nhạy cảm | Có thể anonymous nếu được phê duyệt. | Không tiết lộ internal secrets/metadata. |
| User profile | Authenticated session/token và proper audience. | Authorization theo đúng subject. |
| Invoice read | AuthN + resource/tenant AuthZ. | Authentication chỉ là điều kiện cần. |
| Export job | AuthN và action-specific AuthZ; step-up nếu risk tier yêu cầu. | Job integrity và tenant binding. |
| Admin role modification | Privileged authentication/step-up + authorization. | Change approval, audit, SoD. |
| Partner webhook | Sender authentication/message verification theo contract. | Replay, timestamp, signature và endpoint secret lifecycle. |
| Worker callback | Workload identity và operation-level authorization. | Không dựa riêng vào private IP. |

**AUTH-API-01:** Tất cả protected API routes trong inventory phải từ chối request không có credential hợp lệ, credential sai issuer/audience, credential quá hạn hoặc đã bị thu hồi theo chính sách; mỗi route có owner và có test trực tiếp để phát hiện bypass middleware.

### GraphQL, gRPC, WebSockets

- GraphQL endpoint có thể có một HTTP route nhưng nhiều **fields/mutations/subscriptions**: cần AuthN và AuthZ ở đúng operation.
- gRPC gồm nhiều methods; interceptors và service handlers cần validation đồng nhất.
- WebSockets/SSE cần xác định xác thực tại handshake và kiểm soát quyền trong session lâu dài, khi đổi role, tenant hoặc reconnect.

Một scan endpoint chỉ nhìn URL không thể chứng minh mọi operations đều được bảo vệ.

## 24. API key và webhook authentication

API key đôi khi hữu ích để xác định client application hoặc giới hạn quota, nhưng không tự cung cấp mức đảm bảo tương đương một interactive user đã xác thực và không tự bảo vệ nội dung thông điệp khỏi replay.

### Requirements cho API keys

- Sinh key có entropy phù hợp, phát qua kênh bảo vệ, hiển thị một lần khi cần.
- Lưu/đối chiếu key an toàn, không ghi full key vào log hoặc error.
- Scope theo client, resource/action, environment và rate tier.
- Có owner, expiry/review date, revoke/rotate và incident response.
- Có thể tạo key thay thế trong giai đoạn overlap theo plan, tránh outage không cần thiết.
- Key không được là master credential cho mọi tenant nếu không có căn cứ và controls tương ứng.
- Có test wrong key, revoked key, cross-client/cross-tenant, quota và attribution.

### Webhook signing

Khi xác thực webhook bằng HMAC/chữ ký, cần định nghĩa input được ký (raw bytes/canonical representation), key ID/version, timestamp, replay window, nonce/message ID, xử lý duplicate và fail closed. Đừng verify chữ ký trên nội dung đã bị parse/serialize lại theo cách không khớp chữ ký gốc.

### Phân biệt webhook authenticity và business integrity

Webhook có chữ ký hợp lệ vẫn có thể chứa event bị replay, gửi sai tenant hoặc chuyển trạng thái nghiệp vụ không hợp lệ. Sau khi xác minh sender/message, vẫn cần authorization và idempotency/business validation.

## 25. Thời gian xác thực và chính sách liên tục

Authentication assurance không chỉ ở khoảnh khắc login. Các thay đổi sau có thể ảnh hưởng quyền tin cậy:

- Account bị khóa/disable, employee offboarding hoặc tenant bị suspended.
- Authenticator bị mất, revoke hoặc báo compromise.
- Device posture thay đổi hoặc risk signal phát hiện bất thường.
- Role bị thu hồi hoặc privilege JIT hết hạn.
- Session timeout, credential rotation hoặc token revocation.
- IdP metadata/signing key bị thay, trust relationship bị hủy.
- User thay email/recovery settings hoặc thêm authenticator.

### Phân rã độ trễ thu hồi

Để đánh giá yêu cầu “thu hồi quyền trong cửa sổ đã duyệt”, đo:

**T0:** account/authenticator/role status thay đổi ở nguồn thẩm quyền.

**T1:** thay đổi đã đến hệ thống session/PDP/resource server.

**T2:** thử truy cập ở đúng resource/action không còn thành công.

\[
\text{Effective revocation latency} = T2 - T0
\]

Nên báo phân phối **p50/p95/p99, timed-out/unknown và nhóm access paths không có T2**. Một API trả “revocation successful” không có nghĩa mọi cached tokens, signed URLs hay service sessions đã bị vô hiệu.

### Bảo đảm và tính sẵn sàng phải được cân bằng

Nếu IdP không khả dụng, yêu cầu fail secure thường có nghĩa **không cấp mới phiên nhạy cảm khi không thể xác minh**. Nhưng các phiên đang tồn tại, hệ thống điều khiển quan trọng và emergency operations có thể cần quy tắc availability cụ thể. Requirement phải diễn giải tình huống và security decision rõ, tránh khẩu hiệu “fail closed mọi lúc” dẫn tới thiết kế không thể vận hành.

## 26. Yêu cầu lỗi, fallback và tình huống ngoại lệ

Một control được triển khai đúng khi mọi thành phần hoạt động có thể thất bại khi một dependency bị lỗi.

| Failure mode | Requirement cần định nghĩa | Negative/failure test |
| --- | --- | --- |
| IdP timeout/down | Từ chối cấp phiên mới theo policy; không tự bật local password bypass. | Ngắt IdP trong sandbox/canary và kiểm tra behavior. |
| MFA provider unreachable | Retry/recovery có kiểm soát, không bỏ yếu tố required. | Simulate timeout và fallback abuse. |
| JWT signing key/JWKS stale | Key rotation có procedure; token không có key tin cậy không được accept sai. | Unrecognized key, stale cache và rollback tests. |
| Rate limiter unavailable | Xử lý thiếu throttle theo risk policy và có alert. | Dependency outage + controlled guessing. |
| Session store lost | Quyết định về availability/re-login rõ; không tạo default privileged session. | Store outage và session corruption. |
| Risk engine unavailable | Có chính sách missing signal: deny/restrict/step-up dựa trên requirement. | Unknown/expired signal cases. |
| Device offline | Định nghĩa offline access và tối đa tuổi posture. | Reconnect với stale attestation. |
| Audit collector down | Không được coi “không có sự kiện” là không có attack; có source health alert. | Simulated ingestion loss. |
| Clock drift | Token/challenge time checks theo ngưỡng có cơ sở. | Future/expired tokens và lệch đồng hồ. |
| Federation config drift | Không chấp nhận issuer/redirect mới chưa approved. | Unauthorized metadata change. |

**Fallback là một thiết kế bảo mật**, không phải cách cho user vào bằng mọi giá. Mọi fallback path phải được kiểm thử như primary path và xuất hiện trong inventory.

## 27. UX, accessibility và availability như security requirements

Xác thực quá khó hoặc không có đường phục hồi hợp lệ có thể làm người dùng chia sẻ tài khoản, ghi mật khẩu ra giấy hoặc xin admin cấp quyền ngoại lệ rộng. Do đó assurance nên xem cả **tính sử dụng được**, nhưng không hạ tiêu chí bảo mật tùy tiện.

1. Người dùng có thể sử dụng password manager/passkey khi phù hợp?
2. Có cách tiếp cận tương đương cho người không dùng smartphone hoặc không thể dùng sinh trắc?
3. Quy trình recovery có hỗ trợ người dùng hợp lệ mà vẫn chống takeover?
4. Login/MFA rate limiting có tạo denial-of-service dễ bị attacker kích hoạt không?
5. Khi enterprise IdP lỗi, có runbook và thông báo phù hợp?
6. Những bước xác thực nhạy cảm có giải thích rõ lý do mà không tiết lộ policy internals quá mức?
7. Có test accessibility của login, OTP, recovery và step-up flows?
8. False-deny events có được đo và khắc phục an toàn, không tạo bypass thường trực?

**False permit** (cho phép attacker) và **false deny** (chặn người hợp lệ) là hai lỗi khác nhau. Một system có tỷ lệ deny cao chưa chắc an toàn; có thể đang gây business disruption và thúc đẩy insecure workarounds.

## 28. Logging, monitoring và bằng chứng xác thực

Đối với assurance, hệ thống cần quan sát được **những sự kiện xác thực quan trọng** và **độ tin cậy của chính hệ thống thu evidence**.

### Event classes cần cân nhắc

- Login attempt, success/failure, method category và trusted IdP.
- New authenticator enrollment, modification, removal.
- Password reset, account recovery, unlock và credential replacement.
- MFA/step-up challenge và kết quả.
- Session issuance, rotation, expiry, revoke/logout.
- Privilege elevation, admin/break-glass authentication.
- Workload identity/token/certificate use theo mức phù hợp.
- Federation trust, issuer/client/redirect/role mapping changes.
- Excessive attempts, unusual login risk, blocked requests.
- Auth service, IdP, telemetry source health và security configuration changes.

### Trường evidence gợi ý

| Trường | Vai trò |
| --- | --- |
| **event_id, correlation_id** | Liên kết request, IdP, session và resource outcome. |
| **occurred_at, ingested_at** | Thời gian sự kiện và độ trễ thu thập. |
| **principal_ref, principal_type** | Danh tính tham chiếu đã được bảo vệ, không nhất thiết là email. |
| **tenant_ref, environment** | Scope, tổ chức và môi trường. |
| **auth_method/profile** | Phương thức và policy version thực thi. |
| **decision/outcome/reason_code** | Success, reject, step-up, expired, unknown; không tiết lộ secret. |
| **issuer/client/resource** | Trust source và tài nguyên liên quan. |
| **signal_freshness** | Độ mới của device/risk/identity status khi có requirement. |
| **collector/source/version** | Provenance và kiểm chứng source health. |

### Không ghi secrets vào log

Không lưu password, OTP, recovery token, full bearer token, session cookie, private key, raw biometric hoặc payload không cần thiết. Session IDs có thể được **pseudonymize/hash theo thiết kế** để correlation mà tránh biến evidence store thành kho credential.

### Kiểm tra health của telemetry

Nếu login audit collector im lặng, tỷ lệ failed login giảm còn 0 không phải evidence hệ thống an toàn hơn. Requirement về observability cần heartbeat, schema validation, ingestion lag, integrity, access review và handling khi mất nguồn.

## 29. Requirements phi chức năng liên quan xác thực

Xác thực vừa là security control, vừa ảnh hưởng hiệu năng và availability. Những requirements phi chức năng cần ghi có căn cứ.

| Quality attribute | Ví dụ requirement kiểm chứng được |
| --- | --- |
| **Latency** | Authentication/step-up p95/p99 đạt ngưỡng business được duyệt trong tải xác định. |
| **Availability** | Login provider dependencies và emergency procedures đáp ứng mục tiêu dịch vụ. |
| **Consistency** | Credential revoke hoặc role update có effective propagation trong cửa sổ cho phép. |
| **Scalability** | Rate limiting và authenticator verification không thất bại mất kiểm soát khi burst hợp lệ. |
| **Resilience** | Một provider/region lỗi không tạo bypass hoặc mất kiểm soát sessions. |
| **Privacy** | Authentication telemetry thu tối thiểu và không dùng sai mục đích. |
| **Accessibility** | Người dùng thuộc nhóm mục tiêu có thể hoàn tất authentication/recovery theo tiêu chí thiết kế. |
| **Interoperability** | OIDC/SAML/WebAuthn profiles được test đúng clients/IdPs đã phê duyệt. |
| **Maintainability** | Key/cert/policy rotation có thể làm với controlled rollout, audit, rollback. |
| **Auditability** | Hành động xác thực trọng yếu có log đủ thời kỳ và liên kết evidence. |

Đừng viết “login phải nhanh” hoặc “IdP luôn sẵn” mà không có **test workload, scope, time window, threshold và failure semantics**. Availability của authentication cũng phải được đánh giá khi có tấn công credential stuffing/DoS.

## 30. Catalogue yêu cầu xác thực cho một SaaS đa tenant

Các mã sau là ví dụ **nội bộ**, không phải điều khoản chuẩn hay quy định bắt buộc. Một dự án thật phải chọn yêu cầu dựa trên threat model, phân loại tài sản, loại client, nghĩa vụ và baseline được duyệt.

| ID | Requirement có thể kiểm tra | Acceptance/evidence tối thiểu |
| --- | --- | --- |
| **AUTH-001** | Mọi interactive login paths vào resources trong scope thực thi authentication policy thích hợp. | Path inventory, effective config, thử bypass/legacy login. |
| **AUTH-002** | Critical/privileged access dùng cơ chế strong auth theo mức đảm bảo đã duyệt. | Factor/flow conformance, denied weak paths, exceptions. |
| **AUTH-003** | Local password verifiers được bảo vệ bằng dedicated password hashing và lifecycle an toàn. | Code/config review, safe migration tests. |
| **AUTH-004** | Login/recovery endpoints giới hạn guessing, enumeration và abuse. | Throttle, account-known/unknown tests, false-deny measurements. |
| **AUTH-005** | Authenticator registration, removal và replacement ràng buộc đúng account. | Enrollment/replacement negative tests, audit. |
| **AUTH-006** | Account recovery không tạo đường takeover vượt mức assurance được duyệt. | Recovery takeover tests, support-role review. |
| **AUTH-007** | OIDC login xác minh issuer, audience, state, nonce/PKCE theo flow và keys hợp lệ. | Invalid token/callback tests, RP configuration. |
| **AUTH-008** | SAML assertion validation phù hợp trust profile và không bị signature wrapping/replay. | Wrong audience/recipient, replay tests, library/config review. |
| **AUTH-009** | Account binding giữa IdP và SaaS giữ issuer, subject và tenant trust. | Same-email/different-issuer tests, mapping review. |
| **AUTH-010** | API chỉ nhận credential đúng issuer, audience, times, trust và loại token. | Wrong-audience/expired/bad-signature/API-bypass tests. |
| **AUTH-011** | Resource server thực thi authentication độc lập với client-side UI. | Direct request với token sai/missing. |
| **AUTH-012** | Session issuance chống fixation và session tokens được bảo vệ phù hợp nền tảng. | Pre/post-login session ID test, cookie/transport review. |
| **AUTH-013** | Session idle/absolute lifetime, logout và renewal có policy rõ. | Expired/logout/reuse tests, effective session records. |
| **AUTH-014** | Credential/account offboarding và revocation có effective deny trong cửa sổ đã duyệt. | T0/T1/T2 drill trên browser/API/download. |
| **AUTH-015** | Sensitive actions dùng recent/step-up authentication khi yêu cầu. | Old-auth-time/step-up bypass tests. |
| **AUTH-016** | Auth service failure không tự hạ assurance hoặc mở bypass không kiểm soát. | IdP/MFA/JWKS outage/fallback tests. |
| **AUTH-017** | Workload identities được xác thực với trust, scope và credential lifecycle được duyệt. | Effective IAM/client auth, wrong-principal tests. |
| **AUTH-018** | mTLS identities được gắn đúng workload và không tự cấp business permissions. | Cert SAN/trust tests, denied resource operations. |
| **AUTH-019** | Privileged/admin/break-glass paths có inventory, controls và audit riêng. | Emergency drill, privileged login matrix. |
| **AUTH-020** | API keys/webhook secrets có scope, expiry/rotation và replay protection phù hợp. | Wrong/revoked/replayed request tests. |
| **AUTH-021** | Các thay đổi IdP/trust/role mapping có owner, change control và verification. | Config diff, approval, post-change negative tests. |
| **AUTH-022** | Authentication security events đủ correlation nhưng không chứa raw secrets. | Canary logging tests, audit fields và retention review. |
| **AUTH-023** | Critical authentication telemetry có health monitoring và evidence-gap handling. | Kill-source simulation, unknown status. |
| **AUTH-024** | Mobile/native public clients dùng authorized flow và secure token lifecycle được duyệt. | PKCE/redirect/interception/loss tests. |
| **AUTH-025** | Requirement có owner, test, evidence, version và retest trigger. | Traceability coverage và assurance report. |

### Không gom các yêu cầu có mức độ bắt buộc khác nhau

Yêu cầu cho public anonymous landing page không giống production database administration; requirements cho human users khác workload. Áp cùng một bản checklist không có phân tầng có thể vừa thừa controls vừa bỏ lỗ hổng cần nhất.

### Definition of Done cho một yêu cầu

**Implemented:** code/config đã được triển khai.

**Verified:** tiêu chí được thử bằng methods đã định nghĩa với observed evidence.

**Assured:** scope, population, quality và kỳ đánh giá hỗ trợ kết luận; findings/exceptions/residual risk được phản ánh đầy đủ.

**Accepted risk:** người có thẩm quyền chấp nhận phần chưa đáp ứng; không đồng nghĩa verified PASS.

## 31. Traceability: từ rủi ro đến kiểm thử và evidence

Một bảng requirements có 25 dòng nhưng không có tests có thể chỉ là **intention register**. Security assurance cần khả năng truy vết hai chiều.

~~~mermaid
flowchart LR
    R["Risk / asset / threat"] --> Q["Authentication requirement"]
    Q --> C["Control design and owner"]
    C --> I["Implementation: IdP, app, gateway, workload"]
    I --> T["Positive, negative, failure-mode tests"]
    T --> E["Versioned evidence and assessment"]
    E --> F{"Requirement met?"}
    F -- "No or unknown" --> G["Finding / corrective action / residual risk"]
    G --> T
    F -- "Yes within scope" --> A["Time-scoped assurance conclusion"]
    A --> H["Change triggers / continuous reassessment"]
    H --> R
~~~

| Risk ID | Requirement ID | Control/owner | Test ID | Evidence | Assessed outcome |
| --- | --- | --- | --- | --- | --- |
| R-ACCOUNT-TAKEOVER | AUTH-002 | MFA/passkey policy / IAM owner | AT-02, AT-03 | Policy export, authentication traces | Pending real observation |
| R-FEDERATION-CONFUSION | AUTH-007, AUTH-009 | Trust registry / identity owner | AT-08, AT-09 | Config diff, token validation tests | Pending |
| R-STALE-SESSION | AUTH-014 | Session revocation / app owner | AT-14, AT-15 | T0/T2 canary log, resource outcome | Pending |
| R-WORKLOAD-IMPERSONATION | AUTH-017 | Workload identity / platform owner | AT-20, AT-21 | IAM, mTLS, short-lived token tests | Pending |
| R-CROSS-TENANT-ACCESS | AUTH-009 + AuthZ control riêng | Subject binding + object authz | AT-11, AT-25 | Test result, DB/query authorization evidence | Pending |

Các IDs và outcomes ở đây đều **minh họa**, không phải findings thật. Truy vết phải hỗ trợ câu hỏi ngược: “Test này chứng minh requirement nào? Evidence này thuộc deployment/release nào? Khi requirement đổi, tests nào phải cập nhật?”

## 32. Java/Spring Security: hiện thực một phần requirement trong resource server

Đoạn code sau minh họa **boundary authentication** ở Spring Security resource server dùng JWT. Mục tiêu là thấy rõ **issuer, audience, expiration và route protection** cần được kiểm chứng, không thay thế tài liệu triển khai đầy đủ. Application cần cấu hình issuer/audience từ nguồn tin cậy.

~~~java
// Illustrative Spring Security 6+ configuration.
// Imports, application-specific settings and error handlers omitted.
@Configuration
@EnableMethodSecurity
public class InvoiceApiSecurity {

    @Bean
    SecurityFilterChain invoiceApi(HttpSecurity http)
            throws Exception {
        http.securityMatcher("/api/**");

        // Appropriate only for a stateless bearer-token API
        // that does not authenticate with browser cookies.
        http.csrf(csrf -> csrf.disable());
        http.sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/status")
                .permitAll()
            .anyRequest()
                .authenticated());

        http.oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder(SecuritySettings settings) {
        String issuer = settings.trustedIssuer();
        String audience = settings.invoiceApiAudience();

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTimes =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected token audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTimes, expectedAudience));
        return decoder;
    }
}
~~~

### Những điều đoạn code **chưa** chứng minh

1. **Issuer discovery/JWKS trust:** issuer được cung cấp an toàn? Có bảo vệ certificate/TLS, key rotation và sai cấu hình?
2. **Algorithm policy:** resource server có đúng yêu cầu về loại token, signing algorithms, audience và profile? Cần xem dependency/config và tests.
3. **Cookie/session:** việc disable CSRF trong ví dụ chỉ phù hợp **stateless bearer API không dùng ambient cookie authentication**. Nếu app dùng session cookie hoặc endpoint tương tự, phải thiết kế CSRF protection và security filter chains thích hợp; không copy cờ disable bừa bãi.
4. **API routes khác:** securityMatcher chỉ bao phủ /api/**. Các endpoints ngoài prefix, actuator/admin hoặc websocket cần filter chains và authorization policy độc lập.
5. **Authentication mạnh ở IdP:** API thấy token hợp lệ không chứng minh MFA/passkey ở IdP đạt yêu cầu; nếu cần assurance/reauthentication phải xác minh claims/context và trust contract đúng cách.
6. **Resource authorization:** authenticated() chỉ xác minh đã có một principal; nó không quyết định invoice ID thuộc tenant nào.
7. **Account revocation:** stateless JWT có thể tiếp tục hợp lệ đến expiry nếu không có resource/session revocation strategy phù hợp.
8. **Failure handling:** error codes, logging, observability và rate-limit cần được kiểm tra riêng.

### Layer kiểm tra object/tenant

~~~java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;

    public InvoiceQueryService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceDto read(
            UUID invoiceId,
            VerifiedPrincipal principal) {

        if (principal == null ||
                !principal.mayReadInvoices() ||
                principal.tenantId() == null) {
            throw new AccessDeniedException("Not authorized");
        }

        Invoice invoice = repository
            .findByIdAndTenantId(
                invoiceId, principal.tenantId())
            .orElseThrow(() ->
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND));

        return InvoiceDto.fromAllowedFields(invoice);
    }
}
~~~

Trong dự án thật, **VerifiedPrincipal phải đến từ identity binding đã xác minh**, không được dựng trực tiếp từ tenantId do client gửi. Ví dụ cũng giả định repository trả về dữ liệu tenant-scoped đúng và việc gọi service được bảo vệ theo security architecture. Security review cần test internal callers, async workers, cache/search/export và không chỉ nhìn controller.

### Tests áp dụng cho ví dụ

| Input/case | Expected |
| --- | --- |
| Không có bearer credential khi gọi protected route. | Trả 401 hoặc outcome tương đương theo contract, không data. |
| JWT sai issuer, audience hoặc expired. | Authentication thất bại. |
| JWT hợp lệ nhưng không có quyền invoice.read. | Authorization thất bại ở lớp nghiệp vụ. |
| JWT đúng cho user tenant A, invoice thuộc B. | Không có dữ liệu B, audit phù hợp. |
| Token cũ khi account revoked. | Hành vi đúng revocation strategy và thời hạn đã duyệt. |
| Một route /admin ngoài prefix /api. | Bị policy riêng bảo vệ, không bỏ qua security filter. |
| Browser cookie được thêm vào cùng resource server. | Thiết kế lại CSRF và session controls nếu có ambient credentials. |

## 33. Claim–Argument–Evidence (CAE) cho authentication

Security assurance không chỉ kiểm tra implementation. Nó cần một lập luận nhất quán giữa **claim, reasons và evidence**.

### Claim minh họa

> “Đối với interactive access và workload calls thuộc các production APIs Invoice SaaS được liệt kê trong release R, hệ thống chỉ thiết lập authenticated principal khi credential/IdP assertion được xác minh đúng trust context; các privileged paths áp mức xác thực được duyệt; những negative authentication cases thuộc test suite đã bị từ chối; account/session revocation được kiểm chứng trong phạm vi và thời kỳ đánh giá.”

### Argument

1. **Scope hoàn chỉnh:** mọi relevant login, API, native, admin, service và fallback paths đã được kiểm kê.
2. **Risk-driven requirements:** principal/action/data sensitivity được phân loại; expected auth profiles rõ.
3. **Control design:** IdP, authenticator, session, token, workload credential và recovery có owner/standards.
4. **Implementation evidence:** effective configs, code, route mapping, certificates, keys và production deployment khớp thiết kế.
5. **Verification:** positive, negative, misuse và failure-mode tests chứng minh expected outcomes.
6. **Operational effectiveness:** audit/telemetry, policy change records, revocation drills và access reviews hỗ trợ kết luận trong kỳ.
7. **Residual risk:** exceptions, inconclusive tests và evidence gaps được minh bạch, có người quyết định.

### Evidence matrix

| Assertion | Design evidence | Operating evidence | Giới hạn |
| --- | --- | --- | --- |
| Critical login yêu cầu strong authentication. | Baseline, threat model, flow maps, IdP policy. | Runtime config, weak-method negative tests, session audit. | Đường legacy/backup login ngoài inventory. |
| Federation assertions được xác minh. | OIDC/SAML profile, trust registry. | Wrong issuer/audience/state/replay tests, config snapshots. | Vendor IdP mới chưa kiểm tra. |
| Tenant subject không ghép nhầm. | Identity mapping design, link policy. | Same-email cross-IdP tests, account lifecycle traces. | Legacy account migration. |
| Workload credential scope phù hợp. | Trust model, IAM policy, key lifecycle. | Effective permissions, denied-use tests, rotation audit. | Cached credentials và external integration chưa khám phá. |
| Revocation có hiệu lực. | Session/token revoke strategy và SLA/risk threshold. | T0/T2 drills trên browser/API/worker/download. | Offline sessions hoặc signed URLs còn hạn. |
| Recovery không bypass security. | Recovery design, approval/notification requirements. | Replay/expired/false recovery/support misuse tests. | Một số manual support paths chưa được đánh giá. |
| Log không chứa secrets. | Event schema, redaction/retention policy. | Canary credential test, log/source health checks. | Các downstream collectors cần xem riêng. |

### Evidence có thể bác bỏ claim

Một customer có thể bypass MFA bằng alternate login; một bearer token từ issuer khác được accept; một recovery token dùng lại được; một workload principal hết quyền vẫn gọi KMS; hay một account deprovision vẫn xuất dữ liệu bằng signed link. **Không nên chỉ chọn màn hình cấu hình màu xanh và bỏ qua evidence mâu thuẫn**.

## 34. Kiểm chứng Design Effectiveness và Operating Effectiveness

### Design effectiveness

Review yêu cầu và thiết kế để hỏi:

- Threat scenarios đã bao phủ credential theft, phishing, session theft, reset abuse, federation confusion và workload impersonation?
- Authenticators có phù hợp user/risk contexts, enrollment và recovery có cùng độ đảm bảo cần thiết?
- Login, admin, API, service, mobile và legacy paths có trust boundaries và policy rõ?
- Token/session lifetimes, revoke/expiry/step-up có định nghĩa và khả năng kiểm tra?
- Failure behavior có ngăn bypass nhưng vẫn có kế hoạch recovery?
- Secrets, signing keys và credentials được bảo vệ thế nào?
- Có owner, threat-driven tests và evidence plan cho từng requirement?

### Operating effectiveness

Đánh giá implementation/trạng thái thực:

- Effective IdP configuration/SSO applications đã bật đúng phương thức?
- Routes, reverse proxies và resource servers có xác minh token đúng?
- Tests với invalid token/issuer/audience/state/tenant/replay có được chạy ở đúng release?
- Workload identities và IAM grants không có bypass/excessive rights?
- Recovery, reset và unlock operations có audit và fail behavior?
- Revoke drills trên sessions/tokens/downloads có đạt cửa sổ?
- Audit source có đủ event và health, policy drifts có được phát hiện?
- Findings đã sửa và retest hay mới đóng ticket?

**Design PASS không bằng Operating PASS.** Screenshot đăng ký MFA chỉ hỗ trợ một claim hẹp; một lần login success không chứng minh đường brute-force hoặc reset an toàn.

## 35. Kế hoạch kiểm thử authentication có căn cứ

Trước khi test, định nghĩa **threat, identity, resource, expected result, environment, method, dữ liệu giả, nguồn evidence và giới hạn an toàn**. Thử nghiệm đăng nhập/credential stuffing phải dùng accounts kiểm thử và tốc độ an toàn, không tác động tài khoản khách hàng thật.

| Test ID | Kịch bản | Expected outcome |
| --- | --- | --- |
| **AT-01** | Protected endpoint được gọi không credential. | Reject và không trả dữ liệu. |
| **AT-02** | Interactive user đúng password nhưng thiếu yếu tố required. | Không tạo authenticated session cho protected path. |
| **AT-03** | Fallback/legacy login không có strong auth. | Bị policy chặn hoặc nằm trong approved exception có chứng cứ. |
| **AT-04** | User nhập password phổ biến/bị chặn khi enrollment. | Bị từ chối theo baseline, không leak rule details/secret. |
| **AT-05** | Credential guessing ở giới hạn thí nghiệm. | Throttle/risk response hoạt động; user hợp lệ không bị khóa sai quá mức. |
| **AT-06** | Reset token dùng lần thứ hai hoặc quá hạn. | Reject và audit. |
| **AT-07** | Attacker thử add authenticator khi chưa đủ assurance. | Deny hoặc step-up đúng policy. |
| **AT-08** | OIDC response sai state/nonce/PKCE. | Không tạo session, có error an toàn. |
| **AT-09** | Token sai issuer/audience/signature/expiration. | Reject ở resource server/RP theo profile. |
| **AT-10** | SAML assertion wrong recipient/audience/replayed. | Reject; không account link nhầm. |
| **AT-11** | Hai tenants có cùng email nhưng different issuer/subject. | Session/account association độc lập. |
| **AT-12** | Token ID được gửi vào API yêu cầu access token. | Reject sai loại/mục đích. |
| **AT-13** | Session fixation: attacker biết ID trước login. | ID/state không bị reuse sau authentication boundary. |
| **AT-14** | Logout/password reset rồi dùng session cũ. | Hành vi đáp ứng revocation policy trong cửa sổ quy định. |
| **AT-15** | Deprovision employee rồi thử web/API/CLI/download. | Effective deny trong window; đo T0/T2. |
| **AT-16** | Token refresh bị replay hoặc dùng sai client. | Detect/reject theo refresh token policy. |
| **AT-17** | Admin sensitive action với stale authentication. | Step-up/recent auth được thực thi. |
| **AT-18** | Support role thử reset MFA của super-admin ngoài authority. | Deny hoặc required approval/dual control. |
| **AT-19** | Break-glass usage trong diễn tập. | Chỉ đúng identities, audit/notification/post-use review. |
| **AT-20** | Worker service A dùng identity B hoặc audience sai. | Reject tại trust boundary. |
| **AT-21** | mTLS cert không trusted hoặc SAN sai, nhưng private network đúng. | Reject; không trust chỉ vì IP. |
| **AT-22** | Webhook signature sai/timestamp cũ/replay. | Reject, không apply business action. |
| **AT-23** | IdP/MFA/JWKS/risk service timeout. | Không hạ authentication assurance trái requirement. |
| **AT-24** | Audit source bị ngắt hoặc schema hỏng. | Health alert và evidence gap, không ghi PASS giả. |
| **AT-25** | User authenticated ở A đọc invoice B. | AuthN có thể PASS, nhưng object AuthZ phải DENY. |
| **AT-26** | Mobile public client gọi flow với redirect/code bị thay. | Không cấp token hoặc tạo session trái policy. |
| **AT-27** | Credential/signing cert rotation trên sandbox. | Chính sách trust mới hoạt động; cũ bị loại theo transition plan. |
| **AT-28** | Session cookie bị gửi qua kênh/plaintext hoặc bị lộ trong log. | Cookie/transport/log protections đúng requirement. |
| **AT-29** | Device/risk signal bị stale khi cần step-up. | Reject/restrict/step-up theo missing-signal policy. |
| **AT-30** | Một alternate route không qua middleware authentication. | Đường bị phát hiện và chặn; không được public sai. |

### Kết quả test phải có ý nghĩa

Một test status **PASS** cần expected và observed tương ứng. Nếu thiếu log để xác minh, dùng **INCONCLUSIVE/NOT TESTED** thay vì PASS. Nếu business requirement thay đổi, expected behavior cũng phải được duyệt lại. Không suy từ “đã chạy 30 tests” rằng **mọi đường đăng nhập/API đã được bao phủ**.

### Testing strategy

- **Unit:** token validators, password policy functions, authenticator binding, session logic.
- **Integration:** IdP ↔ RP ↔ resource server; DB/account lifecycle; credential storage.
- **Contract:** tenant federation configuration, callback URIs, partner/webhook signing.
- **End-to-end:** login→step-up→resource action→logout/revoke; recovery/privileged workflows.
- **Negative/adversarial:** wrong issuer, audience, tenant, authenticator, stale session, direct route.
- **Failure injection:** IdP unavailable, key rotation, stale JWKS, telemetry loss, retry pressure.
- **Operational drill:** offboarding, break-glass, credential compromise, rotation/recovery.

## 36. Case study: multi-tenant SaaS có MFA nhưng federation sai

### Kiến trúc giả định

Invoice SaaS có:

1. Tenant A và B sử dụng OIDC từ hai IdPs khác nhau.
2. Cùng một người có thể dùng cùng email tại hai tổ chức nhưng các accounts không liên quan.
3. Browser redirect tới IdP tương ứng tenant đã được cấu hình.
4. API tạo application session và phân quyền sau khi OIDC callback thành công.
5. Background export worker nhận job với tenant context.

### Những phát hiện

| Finding | Quan sát | Nguy cơ |
| --- | --- | --- |
| F-AUTH-01 | Account linking chỉ dựa trên normalized email. | Cross-tenant account confusion khi email trùng. |
| F-AUTH-02 | Redirect/issuer configuration có thể bị một customer user sửa. | Đăng ký IdP giả hoặc điều khiển trust. |
| F-AUTH-03 | API chỉ kiểm tra token signature, không kiểm tra audience. | Token substitution giữa services/clients. |
| F-AUTH-04 | Mật khẩu được reset bằng token dùng nhiều lần trong thời gian sống. | Replay khi link bị lộ. |
| F-AUTH-05 | Logout UI không vô hiệu backend session. | Stolen session còn sử dụng được. |
| F-AUTH-06 | Background worker tin tenantId từ queue payload. | AuthN của user không ngăn cross-tenant export nếu AuthZ/job integrity sai. |

### Tách nguyên nhân theo control

Các vấn đề F-AUTH-01 tới F-AUTH-05 liên quan trực tiếp **identity trust, authentication, credential lifecycle, session management**. F-AUTH-06 liên quan **job integrity/authorization** dù người dùng đã xác thực đúng. Nếu gọi tất cả chỉ là “MFA bug”, team sẽ sửa sai chỗ.

### Đặt requirements điều chỉnh

- **AUTH-FED-05:** stable subject mapping theo issuer/tenant; không dùng email làm khóa toàn cục.
- **AUTH-FED-06:** thay IdP phải được tenant admin có thẩm quyền xác nhận và audit, có negative tests.
- **AUTH-010:** resource server xác minh issuer/audience/expiry và loại token đúng.
- **AUTH-006:** reset token single-use, hạn và binding theo policy.
- **AUTH-014:** logout/revocation có effect trên server-side resource paths.
- **Authorization requirement riêng:** worker chỉ xử lý job đã xác minh từ server, kết nối tới resource/tenant scope đúng.

### Phép thử sau sửa

Tạo hai tenants giả với same-email accounts; dùng tokens đúng/sai issuer/audience; thử federation configuration unauthorized; replay reset token; logout rồi dùng session cũ; gửi forged queue job. Mỗi test cần **expected, observed, timestamp, identity/tenant scope, policy version, release và trace tới finding**.

### Kết luận đúng phạm vi

Nếu tests đạt ở release đã đánh giá, có thể kết luận **những federation và session scenarios thuộc suite được kiểm chứng**. Không thể suy “mọi account chưa từng bị chiếm” chỉ từ thay cấu hình; nếu nghi có data exposure trước khi sửa, cần điều tra usage logs, thời kỳ quan sát và residual risk.

## 37. Evidence quality: dữ liệu nào đủ hỗ trợ assurance?

Các loại evidence nên kết hợp:

| Evidence | Chứng minh gì | Không tự chứng minh gì |
| --- | --- | --- |
| **Security requirement baseline** | Điều kiện phải đạt, scope và owner. | Implementation đang hoạt động. |
| **IdP/RP policy export** | Cấu hình đã khai báo tại thời điểm thu. | Có đường legacy/direct bypass hay không. |
| **App/resource server config** | Đường validation và boundary thiết kế. | Mọi route/runtime instances đã đồng bộ. |
| **Authentication tests** | Expected vs observed trên scenarios đã chọn. | Mọi attack methods hoặc population ngoài suite. |
| **Federation metadata/key history** | Trusted issuers, key lifecycle và thay đổi. | Tài khoản được gắn đúng tenant nếu app mapping sai. |
| **Credential/password review** | Password storage và lifecycle implementation. | Login rate-limit/recovery/incident outcome. |
| **Session/revocation drill** | Effective deny trên paths đã thử. | Mọi client/offline signed URLs đã được thu hồi. |
| **Access/IAM review** | Workload identity và policy quyền. | Tài nguyên không bị lộ qua business logic. |
| **Logs/telemetry** | Hành động và trạng thái được quan sát trong kỳ. | Không có lỗ hổng nếu source thiếu hoặc logging bị tắt. |

### Metadata tối thiểu cho evidence

Evidence ID; requirement/control/test IDs; asset/app/tenant population; environment/region; build/policy version; collection method; source/collector version; time window; expected/observed outcome; reviewer; evidence location/integrity; known limitations; retest link.

### Bảo vệ kho evidence

Authentication evidence rất nhạy cảm: biết authentication flow, issuer, policy, principal IDs và admin paths có thể giúp attacker. Không để raw credentials, OTP hay tokens trong evidence pack; phân quyền, redact, giữ versioning và retention hợp lý. Hash/checksum hỗ trợ phát hiện thay đổi nhưng **không chứng minh nguồn event ban đầu đáng tin**.

## 38. Continuous authentication assurance và các trigger

Authentication controls dễ drift khi **thêm client, thay IdP, đổi redirect URI, xoay signing key, mở API, thêm privileged role hoặc cập nhật SDK/framework**.

### Chu kỳ

~~~mermaid
flowchart TD
    A["Risk, asset and identity inventory"] --> B["Authentication requirements baseline"]
    B --> C["Design: IdP / authenticators / sessions / workload"]
    C --> D["CI: conformance and negative tests"]
    D --> E["Deploy and runtime configuration readback"]
    E --> F["Audit events, revocation drills, policy drift"]
    F --> G{"Requirement verified?"}
    G -- "No / unknown" --> H["Finding, risk and root-cause analysis"]
    H --> I["Remediation + controlled retest"]
    I --> D
    G -- "Yes within scope" --> J["Time-scoped assurance record"]
    J --> K["New tenant, IdP, token, app or threat change"]
    K --> A
~~~

### Reassessment triggers

- New identity provider, tenant SSO connection hoặc trust anchor.
- Authenticator/phishing-resistance baseline hoặc recovery mechanism thay đổi.
- New app, API route, OAuth client, native app hoặc partner integration.
- Token issuer/audience/session/cookie policy thay đổi.
- Signing keys/certificates rotate, revoke hoặc compromise.
- Workload identity/CI/CD credential, cloud role, mTLS CA thay đổi.
- Privileged role mới hoặc expanded support access.
- Incident credential stuffing, phishing, session theft hoặc account takeover.
- Authentication logs missing, collector down, no audit coverage.
- Critical AuthN/AuthZ negative test fail, unexplained authentication bypass.

### Tách coverage khỏi correctness

Automated policy-as-code có thể phát hiện missing MFA flag, insecure redirect, wildcard role hoặc unsigned artifact, nhưng vẫn cần **end-to-end tests và đánh giá nghiệp vụ** để xác minh subject binding, recovery abuse và effective session revocation.

## 39. KPI, KRI và KCI cho Authentication requirements

Một scorecard tốt không nên chỉ công bố “MFA 100%”. Nó cần đo **coverage, effectiveness, revocation, security outcome, usability và quality của bằng chứng** trên các populations khác nhau.

| Metric ID | Định nghĩa/phương pháp | Điều không thể suy ra |
| --- | --- | --- |
| **AUTH-M01 – Protected path coverage** | Protected login/API/admin paths có policy và verified enforcement / toàn bộ eligible paths trong inventory đã đối chiếu. | Không tự chứng minh policy ra quyết định đúng. |
| **AUTH-M02 – Strong authentication enforcement** | Eligible interactive access paths thực thi profile đã duyệt / tổng paths cần profile đó. | Không đo service accounts hoặc phish resistance nếu profile không định nghĩa. |
| **AUTH-M03 – Phishing-resistant adoption** | Identities thuộc nhóm bắt buộc đã dùng method được chấp thuận / identities thuộc nhóm đó. | Enrollment khác runtime enforcement; fallback có thể yếu. |
| **AUTH-M04 – Privileged access protection** | Privileged paths/actions có controls và test đạt / privileged population. | Không đo quyền nghiệp vụ sai hoặc privilege grants quá rộng. |
| **AUTH-M05 – Unowned machine identities** | Machine principals không owner/lifecycle phù hợp / effective machine identities inventory. | Inventory thiếu làm số liệu sai. |
| **AUTH-M06 – Wrong-token rejection** | Invalid issuer/audience/expired/bad-signature cases bị từ chối / tests có ground truth. | Không thể suy mọi token tấn công đã được thử. |
| **AUTH-M07 – Recovery abuse negative tests** | Reset/linking/re-enrollment misuse cases bị chặn / cases thuộc approved suite. | Chỉ suite được thử, không chứng minh mọi support path. |
| **AUTH-M08 – Effective revocation latency** | Phân vị thời gian T0→T2 trên controlled scenarios theo client/resource. | Không dùng API revoke response làm T2. |
| **AUTH-M09 – Authentication failure handling** | IdP/MFA/JWKS outage scenarios đáp ứng policy / attempted failure tests. | Mức availability cần phân tích riêng. |
| **AUTH-M10 – Policy/config drift** | Thay đổi policy/trust ngoài baseline hoặc thiếu approval trong kỳ; phân tầng criticality. | Số thay đổi thấp không chứng minh policy đúng. |
| **AUTH-M11 – Credential compromise response** | Thời gian containment có xác minh và các findings/retests. | Không đồng nghĩa dữ liệu trước incident chưa bị lộ. |
| **AUTH-M12 – Evidence health** | Critical auth telemetry sources có health/freshness đạt / sources thuộc inventory. | Collector heartbeat không chứng minh mọi event đều được ghi. |
| **AUTH-M13 – Test traceability** | Requirements có test đúng và evidence mới trong scope / requirements phải đánh giá. | Có test không chứng minh test đúng hoặc population đầy đủ. |
| **AUTH-M14 – False-deny friction** | User journeys hợp lệ bị chặn sai theo synthetic/real support signals; phân tầng. | Không được tối ưu UX bằng giảm security controls tùy tiện. |
| **AUTH-M15 – Exception expiry** | Số ngoại lệ yếu tố xác thực quá hạn/chưa có owner; theo impact. | Exception đã ký không đồng nghĩa control đạt. |

### Công thức và mẫu số phải rõ

Nếu có 200 application endpoints nhưng inventory chỉ biết 160, báo “160/160 protected = 100%” là không trung thực nếu mục tiêu là toàn bộ 200. Cần:

\[
\text{Known-inventory control coverage}
=\frac{\text{Protected paths among known eligible paths}}
{\text{Known eligible paths}}\times100\%
\]

Đồng thời báo **discovered/unmapped endpoints**, độ tin cậy inventory và những đường chưa đánh giá. Nếu mẫu số bằng 0 hoặc không chắc chắn, trạng thái phù hợp là **N/A/UNKNOWN với lý do**, không là PASS mặc định.

### Baseline và threshold

Mỗi metric cần owner, risk-tier segmentation, methodology, expected threshold và actions khi không đạt. Không tự đặt “99,99%” cho mọi trường hợp nếu chưa định nghĩa population, tính khả thi, threat và business requirements.

## 40. Mẫu YAML cho authentication requirement và evidence plan

Mẫu sau nằm **trong bài học**, không phải cấu hình triển khai IdP hoặc metadata của module. Các đường dẫn và identifiers chỉ mang tính minh họa.

~~~yaml
requirement_id: AUTH-FED-009
title: "Verify tenant-bound federated identity"
status: illustrative_not_assessed
module: SECURITY_SECURITY_ASSURANCE
objective: >
  Prevent account takeover and cross-tenant session confusion
  caused by federated identity misbinding.
scope:
  system: invoice-saas
  environment: production
  clients:
    - browser-relying-party
  subject_populations:
    - enterprise-customer-users
  data_classification: Confidential
threats:
  - "Wrong issuer accepted"
  - "Subject from tenant A mapped into tenant B"
  - "Account linking based only on email"
requirement: >
  The relying party shall create a principal only after validating
  the configured issuer, audience, signature, transaction binding
  and appropriate expiry conditions, and shall bind the identity
  to an authorized tenant using approved account-linking rules.
acceptance_criteria:
  - "Registered IdP for the requested tenant is verified"
  - "Unknown issuer and wrong-audience tokens are rejected"
  - "Same email at unrelated IdPs does not merge accounts"
  - "Unauthorized federation config changes are denied and audited"
  - "No session is established after failed verification"
control_owners:
  identity: "Identity Platform Owner"
  application: "Invoice Application Owner"
  assurance: "Security Assurance Assessor"
verification:
  positive_tests:
    - "approved_issuer_valid_subject_login"
  negative_tests:
    - "wrong_issuer"
    - "wrong_audience"
    - "same_email_different_issuer"
    - "callback_state_mismatch"
    - "unauthorized_idp_registration"
  failure_tests:
    - "idp_unavailable_no_weak_fallback"
  evidence_requirements:
    - "versioned_trust_registry"
    - "policy_and_configuration_readback"
    - "timestamped_test_results"
    - "session_creation_and_deny_audit"
  outcome: "NOT_TESTED_IN_EXAMPLE"
  sample_scope: "To be documented at test execution"
known_limitations:
  - "Legacy tenant migrations require additional checks"
reassessment_triggers:
  - "new_tenant_idp"
  - "issuer_or_signing_key_rotation"
  - "account_linking_logic_change"
  - "federation_incident"
risk:
  current_residual: "NOT_ASSESSED"
  risk_owner: "Customer Identity Risk Owner"
  exception_expiry: null
~~~

### Cách dùng trong assurance program

1. Liên kết requirement ID với threat model và change request.
2. Chốt owner và profile được duyệt trước khi implement.
3. Lập test suite có positive, negative và failure cases.
4. Thu evidence **từ production/release thực hoặc môi trường được xác định**, không coi YAML example là bằng chứng.
5. Báo FAIL/UNKNOWN khi điều kiện không đạt hoặc collector thiếu.
6. Chỉ cập nhật kết luận sau mitigation/retest và risk decision có thẩm quyền.

## 41. Exception, remediation và residual risk

Đường legacy login, support recovery hoặc partner API có thể chưa đáp ứng authentication baseline. Cần quản lý thay vì loại khỏi mẫu số để dashboard đẹp.

### Đặc tả ngoại lệ

| Trường | Nội dung |
| --- | --- |
| **Affected population** | Account/client, application route, tenant, environment và user/workload category. |
| **Requirement not met** | Chính xác điều kiện nào chưa đạt. |
| **Threat and impact** | Phishing, replay, account takeover, data disclosure hay availability. |
| **Existing controls** | Cái gì đang hoạt động và evidence hỗ trợ. |
| **Compensating controls** | Hạn quyền, monitor, network restriction, JIT hoặc manual approval có test. |
| **Owner and approver** | Người thực thi và risk owner đúng thẩm quyền. |
| **Expiry and reassessment** | Ngày hết hạn, trigger incident, policy change hoặc data class change. |
| **Remediation plan** | Chuyển IdP, thêm MFA, thay client, rotate credentials, nâng cấp legacy flow. |
| **Retest criteria** | Những scenarios nào phải PASS để kết thúc exception. |

### Current vs target risk

**Current residual risk** mô tả mức rủi ro với controls thực tế đã triển khai; **target residual risk** là mức dự kiến sau remediation và verification. Việc đã lập kế hoạch cho MFA không làm các tài khoản đang dùng password-only bỗng được bảo vệ bằng MFA.

### Không được chấp nhận rủi ro thay cho nghĩa vụ bắt buộc

Một exception nội bộ không tự miễn trừ các nghĩa vụ hợp đồng/pháp lý/chuẩn bắt buộc. Nếu profile/đối tác yêu cầu phương pháp xác thực cụ thể, tổ chức phải kiểm tra đúng điều kiện và quyền phê duyệt ngoại lệ thực tế; không dùng wording “business approved” để thay bằng chứng.

### Closing findings

Finding “OIDC audience không được validate” chỉ đóng khi code/config đã đổi, release được triển khai, negative wrong-audience tests bị từ chối và telemetry/effective scope được xác minh. Ticket status Done không tự chứng minh remediation thành công.

## 42. Những ngộ nhận khi viết requirement về xác thực

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “SSO nghĩa là bảo mật xác thực đã hoàn thành.” | Phải kiểm tra IdP trust, account linking, session và resource server. |
| “Có MFA là không thể bị phishing.” | Một số MFA/OTP vẫn bị phishing/AiTM; đánh giá phishing resistance theo triển khai. |
| “100% người dùng enrolled MFA nghĩa mọi path đều protected.” | Có thể có legacy, admin, recovery, native và service paths. |
| “Authentication và authorization giống nhau.” | Xác thực xác định principal; quyền trên từng resource/action là kiểm tra khác. |
| “JWT signature đúng là API được phép sử dụng token.” | Cần issuer, audience, times, loại token và AuthZ. |
| “ID token gửi cho API cũng được.” | ID token thường dành cho RP; resource server dùng credential phù hợp API. |
| “Email là định danh toàn cục đáng tin.” | Email có thể thay đổi, tái sử dụng và trùng ở các IdP/tenant. |
| “Passkey mạnh thì không cần bảo vệ enrollment/recovery.” | Attacker có thể takeover bằng thêm authenticator hoặc reset yếu. |
| “Biometric luôn đồng nghĩa server giữ mẫu sinh trắc.” | Có thiết kế dùng biometric chỉ để unlock authenticator cục bộ. |
| “mTLS đủ để service đọc mọi dữ liệu.” | Certificate identity không tự cấp business/tenant authorization. |
| “API key chứng minh người dùng đã qua MFA.” | API key thường chứng minh quyền giữ một shared secret/client credential. |
| “Đăng xuất khỏi UI xóa mọi access token.” | Tokens/sessions/signed URLs có lifecycle riêng. |
| “IdP disable trả success là user đã hết quyền.” | Cần đo effective deny tại resource trong các paths. |
| “Bật rate limit vô hạn càng an toàn.” | Có thể gây account lockout DoS và false denies. |
| “Quy định đổi mật khẩu thường xuyên luôn tốt hơn.” | Phải căn cứ hướng dẫn/baseline/risk; đổi vô cớ có thể tăng password reuse. |
| “Không có failed login nghĩa là không có attack.” | Logs có thể thiếu, detector im lặng hoặc attacker dùng stolen session. |
| “Backup login không cần audit.” | Fallback và break-glass thường có rủi ro rất cao. |
| “Framework đã xử lý mọi route theo mặc định.” | Cần kiểm tra filters, matchers, websocket, admin và direct paths. |
| “Một test đăng nhập thành công chứng minh security.” | Cần negative, misuse, recovery, federation, failure và revocation tests. |
| “Risk acceptance nghĩa là requirement đã PASS.” | Acceptance là quyết định có điều kiện, không thay control effectiveness. |

## 43. Checklist đánh giá Authentication requirements

1. **Scope:** mọi user/admin/workload/client/partner/fallback paths được kiểm kê?
2. **Risk:** credential theft, phishing, account takeover, replay, federation confusion, service impersonation được xét?
3. **Definition:** phân biệt identity proofing, AuthN, federation, AuthZ và session management?
4. **Assurance:** authenticators/profile phù hợp resource sensitivity và yêu cầu áp dụng?
5. **MFA/phishing:** method/fallback/recovery/enrollment có test, không chỉ enrollment dashboard?
6. **Passwords:** verifier storage, blocklist, guessing controls và reset an toàn?
7. **Passkeys:** RP ID/origin, challenge, signature, account binding và lifecycle được kiểm chứng?
8. **OIDC:** issuer, audience, state, nonce, PKCE, redirect, key rotation và token purpose đúng?
9. **SAML:** metadata, signature, recipient/audience, time, replay và mapping đúng?
10. **Tenant:** account linking theo issuer/subject/tenant, không chỉ email?
11. **APIs:** protected routes kể cả GraphQL/gRPC/WebSockets có AuthN và AuthZ riêng?
12. **Workloads:** service principal owner, key/secret lifecycle, mTLS trust và effective scope?
13. **Privileged:** admin/CI/CD/control-plane/break-glass paths có policy và audit?
14. **Sessions:** fixation, cookies, expiry, logout, revoke, stale token, cache và offline access?
15. **Recovery:** reset, unlock, re-enrollment, support access và notifications?
16. **Failure:** IdP/MFA/JWKS/session store/risk-signal outage không tạo bypass?
17. **Usability:** false denies, accessibility và safe support/recovery được xét?
18. **Traceability:** mỗi requirement có threat, owner, control, test, evidence và version?
19. **Tests:** positive, negative, failure-mode, runtime và operational drills đầy đủ?
20. **Evidence:** source, population, environment, time, expected/observed, telemetry health rõ?
21. **Risk:** findings, exceptions, current/target residual risk có owner/expiry?
22. **Change:** thêm IdP, route, issuer, SDK, workload và privileged role có reassessment?

## 44. Bài tập tình huống và gợi ý giải

### Bài tập A — MFA adoption rất cao

SaaS báo 99% nhân viên đã đăng ký MFA nhưng có đường login của ứng dụng admin legacy chấp nhận password-only.

**Gợi ý:** Requirement cần bao phủ **mọi privileged interactive paths**, không chỉ số người đăng ký. Kiểm kê legacy/admin/fallback, kiểm tra effective policy và thử đăng nhập bằng weak method. Nếu chưa nâng cấp được, quản lý exception có expiry, compensating controls và risk decision.

### Bài tập B — OIDC token có chữ ký đúng nhưng sai audience

Một API invoice nhận token hợp lệ do đúng IdP phát hành, nhưng token này có audience dành cho một API khác.

**Gợi ý:** Đây là token substitution. AUTH-010 yêu cầu validate issuer, audience, times, signature, token type và scope; có negative test wrong-audience và đảm bảo resource server không dùng ID token sai mục đích.

### Bài tập C — Hai khách hàng có email giống nhau

Tenant A và B cùng sử dụng email helpdesk@example.invalid qua hai IdPs riêng. SaaS liên kết accounts bằng email nên user A thấy profile B.

**Gợi ý:** Mô hình identity binding phải xét issuer + subject + tenant trust, không chỉ email. Thêm test cross-IdP, thay liên kết account có approval; nếu dữ liệu đã lộ, cần điều tra và đánh giá impact riêng.

### Bài tập D — Passkey mạnh nhưng support reset yếu

Customer admin dùng passkey, nhưng support có thể xóa passkey chỉ khi người gọi biết ngày sinh.

**Gợi ý:** Recovery assurance thấp hơn primary auth. Viết yêu cầu cho support recovery, evidence of account control, privileged approval, notification, hold/cooldown phù hợp và audit; không dựa security question đơn giản làm chứng cứ duy nhất.

### Bài tập E — Service certificate hợp lệ

Service A có mTLS certificate từ CA nội bộ và gọi được endpoint DELETE trên resource của service B dù không có nhiệm vụ.

**Gợi ý:** Peer authentication PASS có thể đúng nhưng authorization FAIL. Requirement cần phân biệt workload identity và resource/action permissions; test least privilege, network/path IAM và event audit.

### Bài tập F — Người đã nghỉ việc vẫn có session

HR deprovision user lúc 09:00, IdP disabled lúc 09:02; một browser session vẫn download data tới 14:00.

**Gợi ý:** Đo T0→T2 trên resource, không chỉ thời gian API disable. Xem session store, access token expiry, signed URLs, downstream service và cửa sổ rủi ro được phê duyệt; cập nhật revocation strategy.

### Bài tập G — Nâng cấp SDK làm mất kiểm tra issuer

Ứng dụng nâng phiên bản JWT library và tắt issuer validation để tránh login errors. All positive login tests vẫn PASS.

**Gợi ý:** Cần negative wrong-issuer tests và policy conformance regression; change gate không chỉ test happy path. Revert/fix theo plan, kiểm tra production impact và risk trong thời kỳ.

### Bài tập H — Webhook signed nhưng bị replay

Một partner gửi signed payment status event. Attacker phát lại message cũ nhiều lần, service tạo nhiều giao dịch.

**Gợi ý:** Chữ ký hợp lệ xác minh nguồn/message theo thiết kế, nhưng cần timestamp/message ID, replay cache, idempotency và business state validation; test replay và duplicate side effects.

### Bài tập I — Rate limiter làm khóa account

Attacker gửi login sai vào một account quan trọng, khiến user hợp lệ bị khóa liên tục.

**Gợi ý:** Cân bằng credential attack mitigation với availability; dùng signals/throttling phù hợp, tạo recovery flow an toàn, đo false denies và điều chỉnh theo threat model thay vì vô hiệu toàn bộ rate limit.

### Bài tập J — Một collector bị dừng

Dashboard tháng này báo 0 authentication failures nhưng IdP audit source đã không ingest ba ngày.

**Gợi ý:** Đây là evidence gap. Có health metrics, timestamp/window, unknown handling; không kết luận 0 attack và cần xem lại các claim đã công bố trong thời kỳ.

### Bài tập K — Đội chỉ có một positive test

Test “user đúng password + OTP có thể đăng nhập” đạt nhưng không thử reset token, fallback, session fixation hay issuer mismatch.

**Gợi ý:** Đây chỉ là bằng chứng functionality của một flow. Bổ sung threat-driven negative, recovery, token trust, revocation và failure tests; coverage phải dựa trên population/requirement IDs.

### Bài tập L — Key rotation gây outage

IdP xoay signing key, API cache JWKS cũ và từ chối mọi token mới; đội vận hành đề xuất tắt signature validation.

**Gợi ý:** Không tắt xác minh chữ ký. Cần key rotation transition plan, JWKS cache refresh theo policy, rollback/circuit handling an toàn, positive/negative tests và monitor trước/sau thay đổi.

## 45. Kết luận: requirement về xác thực là một cam kết có thể chứng minh

Một **authentication requirement** có giá trị phải chỉ rõ **principal, trust boundary, tài nguyên, điều kiện xác thực, phương thức/assurance, lifecycle, failure behavior và bằng chứng nghiệm thu**. Các controls như password policy, MFA, passkeys, OIDC/SAML, mTLS và workload identities chỉ có ý nghĩa khi được áp dụng đúng scope, không có bypass ngoài dự kiến và được kiểm chứng bằng **positive/negative/failure-mode tests**.

Trong **SECURITY_SECURITY_ASSURANCE**, yêu cầu xác thực không thể tách khỏi **rủi ro giả mạo danh tính, chiếm đoạt tài khoản, credential compromise, session theft, recovery abuse, federation confusion và non-human identities**. Nhưng cũng phải phân biệt xác thực với phân quyền: người được xác thực đúng **chưa chắc có quyền** truy cập invoice, tenant hoặc hành động cụ thể.

Security assurance nối **risk → requirement → design → implementation → evidence → assessment → corrective action**, rồi đánh giá lại khi accounts, IdPs, tokens, policies, applications hoặc threat model thay đổi. **Chỉ kết luận yêu cầu xác thực được đáp ứng trong phạm vi, phiên bản và thời kỳ có bằng chứng đủ tin cậy; không mở rộng kết luận từ một màn hình MFA xanh hoặc một lần đăng nhập thành công thành sự bảo đảm cho toàn hệ thống.**
