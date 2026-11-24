# Login audit — Ghi nhận và giám sát sự kiện đăng nhập an toàn

> **Chương:** Đăng nhập  
> **Chủ đề:** Login audit  
> **Phạm vi:** Security Authentication Fundamentals — ghi nhận sự kiện xác thực và phiên đăng nhập, bảo toàn dấu vết kiểm toán, phát hiện lạm dụng credential, hỗ trợ điều tra sự cố và bảo vệ dữ liệu cá nhân.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mục đích của login audit và phân biệt audit trail với debug log, application telemetry và business event.
2. Xây dựng taxonomy cho sự kiện đăng nhập thành công, thất bại, MFA, step-up, recovery, credential change và session lifecycle.
3. Thiết kế event schema có thời gian, kết quả, reason code, subject reference, client, device, tenant và correlation ID.
4. Xác định dữ liệu cần ghi, dữ liệu phải loại bỏ và cách giảm thiểu dữ liệu cá nhân.
5. Bảo vệ tính toàn vẹn, khả năng truy cập và vòng đời lưu trữ của audit log.
6. Xây dựng quy tắc phát hiện password spraying, credential stuffing, MFA fatigue, account takeover và bất thường trong session.
7. Thiết kế luồng điều tra và phản ứng dựa trên audit evidence.
8. Kiểm thử tính đầy đủ, độ chính xác, khả năng chống giả mạo và redaction của login audit.

## 1. Login audit là gì?

**Login audit** là việc ghi nhận có cấu trúc các sự kiện liên quan đến quá trình xác thực và vòng đời đăng nhập, để có thể trả lời các câu hỏi: ai hoặc chủ thể nào đã thử đăng nhập, vào lúc nào, qua ứng dụng nào, bằng phương thức nào, kết quả ra sao và hệ thống đã đưa ra quyết định gì.

Audit không chỉ ghi nhận đăng nhập thành công. Những lần thất bại, step-up, MFA challenge, thay đổi credential, recovery, khóa tài khoản, tạo và thu hồi session đều có thể là dấu hiệu quan trọng trong điều tra.

Ví dụ: Một tài khoản có 80 lần đăng nhập thất bại từ nhiều nguồn rồi có một lần đăng nhập thành công trên thiết bị mới. Nếu hệ thống chỉ ghi login success, đội bảo mật sẽ mất chuỗi bằng chứng cho thấy có thể đã xảy ra credential stuffing trước khi attacker truy cập được.

Login audit phục vụ:

- **Accountability:** xác định actor, subject và hệ thống đã thực hiện quyết định;
- **Detection:** phát hiện hành vi đăng nhập bất thường hoặc tấn công diện rộng;
- **Incident response:** dựng lại timeline, phạm vi ảnh hưởng và hành động đã xảy ra;
- **Compliance:** chứng minh việc kiểm soát truy cập theo yêu cầu chính sách hoặc pháp lý;
- **Operations:** tìm lỗi cấu hình, lỗi IdP, sự cố MFA, session và tích hợp;
- **Forensics:** bảo toàn bằng chứng phục vụ điều tra sau sự cố.

Audit có giá trị khi sự kiện được ghi ở đúng điểm thực thi, có ngữ nghĩa nhất quán, được bảo vệ khỏi sửa/xóa trái phép và có thể liên kết với các sự kiện liên quan.

## 2. Phân biệt audit trail, application log và telemetry

Các loại dữ liệu có thể được gửi chung tới nền tảng log, nhưng mục đích và tiêu chuẩn của chúng khác nhau.

| Loại dữ liệu | Mục đích | Ví dụ | Yêu cầu chính |
| --- | --- | --- | --- |
| **Security audit trail** | Bằng chứng về sự kiện và quyết định bảo mật | Login success, MFA failure, credential revoked | Chính xác, có nguồn, có integrity và retention |
| **Application log** | Hỗ trợ vận hành và tìm lỗi ứng dụng | Timeout khi gọi token endpoint | Có ngữ cảnh lỗi, không lộ secret |
| **Telemetry/metrics** | Đo xu hướng và hiệu năng | Login latency, failure rate | Có thể tổng hợp, tránh thu thập định danh quá mức |
| **Business event** | Ghi nhận kết quả nghiệp vụ | Người dùng hoàn tất onboarding | Gắn với nghiệp vụ và transaction |
| **Access log** | Ghi request tới HTTP/API gateway | Method, route, status code | Không tự thay thế audit xác thực |

Một HTTP 200 tại trang callback không chứng minh đăng nhập đã thành công. Một application log ghi “user logged in” cũng chưa đủ nếu không thể xác định quyết định đó được đưa ra sau khi xác minh credential nào và gắn với subject nào.

### Ghi ở phía server có thẩm quyền

Audit quan trọng phải được tạo tại thành phần thực sự đưa ra quyết định: authentication service, OIDC/SAML callback verifier, MFA verifier, session service hoặc identity lifecycle service. Client có thể gửi telemetry hỗ trợ nhưng không được tự khai kết quả xác thực.

Không tin event từ browser kiểu authenticated=true, mfa_passed=true hoặc device_trusted=true nếu chưa có bằng chứng server xác minh. Event phía client có thể hữu ích để đo UX, nhưng phải được đánh dấu nguồn và không dùng làm bằng chứng quyết định bảo mật.

## 3. Phạm vi sự kiện cần ghi nhận

Một taxonomy tốt bao phủ cả luồng đăng nhập và các thay đổi có thể ảnh hưởng tới khả năng đăng nhập sau đó.

| Nhóm | Event gợi ý | Vì sao cần |
| --- | --- | --- |
| **Authentication attempt** | login.started, login.succeeded, login.failed | Dựng chuỗi thử đăng nhập và kết quả |
| **Password** | password.verify.failed, password.changed, password.reset | Phát hiện credential stuffing và thay đổi bất thường |
| **MFA** | mfa.challenge.sent, mfa.challenge.succeeded, mfa.challenge.failed, mfa.factor.added/removed | Phát hiện push fatigue, OTP abuse và factor tampering |
| **Passkey/WebAuthn** | passkey.assertion.succeeded/failed, passkey.registered/removed | Theo dõi credential phishing-resistant |
| **Federation/SSO** | oidc.callback.validated/rejected, saml.response.accepted/rejected | Điều tra lỗi issuer, signature, audience và replay |
| **Step-up** | step_up.requested/succeeded/failed | Biết hành động nào yêu cầu xác thực mới |
| **Recovery** | recovery.started/approved/denied/completed | Phát hiện takeover qua quy trình khôi phục |
| **Account protection** | account.locked/unlocked, risk.blocked | Biết hệ thống đã áp dụng biện pháp bảo vệ nào |
| **Session** | session.created/refreshed/revoked/expired | Liên kết login với truy cập sau đó |
| **Credential lifecycle** | credential.added/removed/revoked, password_reset | Theo dõi thay đổi khả năng xác thực |
| **Administrative action** | admin.login, admin.step_up, admin.factor.reset | Theo dõi thao tác đặc quyền |

Không phải mọi hệ thống đều cần từng event name trên. Hãy xác định taxonomy phù hợp và giữ ngữ nghĩa ổn định giữa các phiên bản.

### Phân biệt attempt, success và session

- **login.started:** một giao dịch đăng nhập được khởi tạo;
- **login.failed:** một lần xác minh hoặc policy evaluation không thành công;
- **login.succeeded:** hệ thống đã xác minh danh tính và chấp nhận đăng nhập;
- **session.created:** một session ứng dụng thực sự được phát hành;
- **session.revoked:** session bị vô hiệu hóa.

Không gộp login success và session creation thành một event nếu hai việc có thể thất bại độc lập. Ví dụ, xác minh OIDC thành công nhưng lỗi tạo session cần được điều tra riêng.

## 4. Thiết kế event schema

Audit event nên có schema nhất quán, version hóa và dễ truy vấn. Tránh chỉ ghi một chuỗi tự do như “Login failed for user”.

### Các trường cơ bản

| Trường | Ý nghĩa |
| --- | --- |
| event_id | ID duy nhất của event |
| event_name | Tên event theo taxonomy |
| event_version | Phiên bản schema |
| occurred_at | Thời điểm sự kiện thực sự xảy ra |
| recorded_at | Thời điểm audit collector ghi nhận |
| outcome | success, failure, denied, challenged hoặc unknown |
| reason_code | Mã lý do nội bộ, ổn định và không chứa secret |
| source_service | Thành phần tạo event |
| environment | production, staging hoặc environment được định danh |
| tenant_id | Tenant được xác định từ context tin cậy |
| subject_ref | Tham chiếu/pseudonym của tài khoản hoặc principal |
| actor_ref | Actor thực hiện thao tác nếu khác subject |
| client_id/app_id | Ứng dụng hoặc OAuth/OIDC client liên quan |
| interaction_id | ID liên kết các bước trong cùng giao dịch |
| correlation_id/trace_id | Liên kết sự kiện giữa service |
| session_ref | Tham chiếu session, không phải cookie/session secret |
| credential_ref | ID tham chiếu credential, không phải credential value |
| device_ref | Tham chiếu thiết bị theo registry |
| auth_context | Phương thức và assurance đã được xác minh |
| risk_decision | Kết quả policy/risk evaluation và version |

### Ví dụ event JSON

`````````json
{
  "event_id": "evt-9f3c21",
  "event_name": "auth.login.failed",
  "event_version": 1,
  "occurred_at": "2026-11-22T06:30:12.481Z",
  "recorded_at": "2026-11-22T06:30:12.503Z",
  "outcome": "failure",
  "reason_code": "INVALID_CREDENTIAL",
  "source_service": "identity-auth",
  "environment": "production",
  "tenant_id": "tenant-42",
  "subject_ref": "usr-ref-7b2a",
  "actor_ref": "usr-ref-7b2a",
  "client_id": "staff-portal",
  "interaction_id": "login-flow-41d8",
  "correlation_id": "trace-a12f",
  "session_ref": null,
  "credential_ref": "cred-ref-91ac",
  "device_ref": "device-ref-82bc",
  "auth_context": {
    "method": "password",
    "factor_count": 1,
    "assurance_policy": "baseline-v3"
  },
  "risk_decision": {
    "result": "allow_retry",
    "policy_version": "login-risk-12"
  }
}
`````````

Ví dụ chỉ minh họa schema. Các reference phải được tạo từ hệ thống và không tiết lộ trực tiếp dữ liệu nhận dạng nếu không cần. Event failure không chứa mật khẩu sai, OTP, token hoặc dữ liệu bí mật người dùng đã nhập.

### occurred_at và recorded_at

Hai timestamp giúp phát hiện event đến trễ hoặc bị buffer:

- occurred_at là thời điểm nguồn ghi nhận hành động;
- recorded_at là thời điểm collector nhận hoặc lưu event.

Đồng bộ đồng hồ giữa các service bằng cơ chế thời gian tin cậy, lưu UTC và giữ độ chính xác phù hợp. Không tự sửa timestamp nguồn mà không giữ thông tin sai lệch; nếu clock drift lớn, ghi nhận tình trạng để điều tra.

## 5. Ghi dữ liệu nào và tuyệt đối không ghi dữ liệu nào?

Audit cần đủ ngữ cảnh để điều tra, nhưng việc thu thập quá nhiều dữ liệu làm tăng rủi ro khi log bị truy cập trái phép.

### Dữ liệu thường hữu ích

- Subject/account reference đã pseudonymize;
- Tenant, application/client và service;
- Event name, outcome, reason code;
- Thời gian xảy ra và thời gian ghi nhận;
- Authentication method và assurance đã xác minh;
- Credential reference, device reference, session reference;
- IP hoặc network context nếu có căn cứ và policy cho phép;
- User agent/platform đã chuẩn hóa ở mức cần thiết;
- Correlation/interaction ID;
- Risk decision, policy version và action bị từ chối;
- Administrative actor và approval reference nếu có.

### Không ghi secret hoặc credential thô

Không ghi:

- Password, password hash hoặc câu trả lời bí mật;
- OTP, TOTP seed, recovery code, backup code;
- Passkey private key, WebAuthn authenticator secret hoặc raw credential material;
- Authorization header, bearer token, access token, refresh token, ID token;
- Session cookie, session ID dạng secret hoặc CSRF token;
- Authorization code, PKCE code verifier;
- SAML assertion/response nguyên bản nếu không có nhu cầu điều tra được phê duyệt và cơ chế bảo vệ đặc biệt;
- Private key, client secret, API key hoặc certificate private material;
- Nội dung form recovery hoặc dữ liệu xác minh danh tính nhạy cảm.

Nếu cần liên kết sự kiện, dùng credential ID, session reference hoặc token fingerprint đã được thiết kế an toàn. Không tự hash token/password để ghi log: hash yếu hoặc có thể đoán vẫn tạo nguy cơ dò tìm và liên kết dữ liệu.

### IP, device và dữ liệu cá nhân

IP, user agent, vị trí, device serial và hostname có thể là dữ liệu cá nhân hoặc nhạy cảm tùy bối cảnh. Chỉ thu thập khi có mục đích bảo mật rõ ràng, giới hạn quyền truy cập và retention. Có thể dùng network prefix, ASN, coarse location hoặc pseudonymous device reference khi đủ cho detection.

Không coi IP là danh tính người dùng. NAT, VPN, proxy, mạng di động và shared device có thể khiến nhiều người dùng chung một địa chỉ hoặc một thiết bị.

## 6. Reason code và thông báo cho người dùng

Reason code nên có ngữ nghĩa ổn định để phân tích và điều tra:

| Reason code | Ý nghĩa nội bộ |
| --- | --- |
| INVALID_CREDENTIAL | Credential không hợp lệ |
| ACCOUNT_DISABLED | Tài khoản bị vô hiệu hóa |
| ACCOUNT_LOCKED | Tài khoản đang bị khóa |
| MFA_REQUIRED | Policy yêu cầu MFA |
| MFA_FAILED | MFA verification thất bại |
| STEP_UP_REQUIRED | Hành động cần xác thực tăng cường |
| STEP_UP_STALE | Lần xác thực trước quá cũ |
| RISK_BLOCKED | Risk policy từ chối |
| ISSUER_MISMATCH | Issuer không khớp trust configuration |
| AUDIENCE_MISMATCH | Token/assertion không dành cho bên nhận |
| NONCE_MISMATCH | Nonce không khớp transaction |
| REPLAY_DETECTED | Credential/challenge/response bị dùng lại |
| DEVICE_NOT_COMPLIANT | Thiết bị không đáp ứng policy |
| RATE_LIMITED | Yêu cầu vượt giới hạn |
| PROVIDER_UNAVAILABLE | IdP hoặc dịch vụ phụ thuộc không khả dụng |
| SESSION_REVOKED | Session đã bị thu hồi |

Reason code trong audit có thể chi tiết hơn thông báo công khai. Ví dụ, giao diện có thể chỉ nói “Không thể đăng nhập bằng thông tin đã cung cấp”, trong khi audit nội bộ phân biệt invalid credential, disabled account hoặc policy denial.

Không tiết lộ cho người dùng chưa xác thực rằng email có tồn tại, tài khoản bị khóa vì lý do gì hoặc factor nào đã được đăng ký nếu điều đó hỗ trợ account enumeration. Tuy vậy, audit nội bộ vẫn cần mã lý do để điều tra.

## 7. Liên kết các sự kiện bằng correlation và identity reference

Một lần đăng nhập thường đi qua nhiều service:

1. Browser bắt đầu login;
2. Authentication service xác minh password/passkey;
3. MFA service kiểm tra yếu tố bổ sung;
4. Risk engine đánh giá context;
5. Session service tạo session;
6. Gateway nhận request đầu tiên sau login.

Nếu mỗi service ghi một ID riêng không liên kết, điều tra sẽ khó dựng lại chuỗi.

### Interaction ID và correlation ID

- **interaction_id:** liên kết các bước thuộc cùng một login/step-up transaction;
- **correlation_id/trace_id:** liên kết request giữa các service;
- **event_id:** định danh duy nhất từng audit event;
- **session_ref:** liên kết login với session và hoạt động tiếp theo;
- **subject_ref:** liên kết sự kiện với principal mà không cần ghi raw identifier.

Correlation ID không phải secret và không thay thế xác thực. Không cho client tùy ý cung cấp một ID rồi dùng nó làm bằng chứng rằng hai sự kiện cùng thuộc một giao dịch; server phải tạo hoặc xác minh context phù hợp.

### Ví dụ chuỗi sự kiện

`````````mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Auth service
    participant M as MFA service
    participant R as Risk engine
    participant S as Session service
    B->>A: Login request
    A-->>A: Audit login.started
    A->>A: Verify credential
    A-->>A: Audit credential verified
    A->>M: Verify MFA challenge
    M-->>A: MFA result
    M-->>M: Audit mfa.succeeded/failed
    A->>R: Evaluate context
    R-->>A: Policy decision
    R-->>R: Audit risk decision
    A->>S: Create session
    S-->>A: Session reference
    S-->>S: Audit session.created
    A-->>B: Login result
`````````

Các event cần dùng cùng interaction ID và correlation ID đã được tạo ở server để hỗ trợ dựng timeline.

## 8. Bảo vệ tính toàn vẹn của audit log

Audit chỉ có giá trị khi attacker hoặc người có quyền vận hành không thể âm thầm sửa/xóa dấu vết.

### Kiểm soát cơ bản

- Gửi event tới hệ thống tập trung qua kênh được xác thực và mã hóa;
- Phân quyền theo least privilege; service chỉ được ghi vào stream phù hợp;
- Tách quyền tạo log, tìm kiếm, export, xóa và quản trị retention;
- Lưu trữ append-only hoặc immutable/WORM khi yêu cầu;
- Theo dõi việc xóa, thay đổi policy và truy cập audit store;
- Mã hóa khi truyền và khi lưu;
- Có backup và kiểm tra khả năng phục hồi;
- Đồng bộ thời gian và theo dõi clock drift;
- Phát hiện event drop, collector outage và queue backlog;
- Ghi audit cho cả thao tác quản trị trên chính hệ thống log.

### Hash chain hoặc chữ ký event

Với yêu cầu assurance cao, có thể dùng hash chain, chữ ký hoặc cơ chế lưu trữ chống sửa để phát hiện thay đổi:

- Mỗi batch có digest;
- Digest liên kết với batch trước;
- Khóa ký được bảo vệ riêng khỏi hệ thống phát event;
- Có checkpoint gửi tới miền lưu trữ độc lập.

Các cơ chế này giúp phát hiện chỉnh sửa, nhưng không tự bảo đảm event ban đầu là đúng. Nếu nguồn tạo event bị compromise, attacker có thể tạo event giả trước khi chúng được ký. Vì vậy vẫn cần bảo vệ nguồn, phân tách quyền và đối chiếu với các hệ thống độc lập.

### Log pipeline cũng là bề mặt tấn công

Nếu collector bị quá tải, mất kết nối hoặc bị cấu hình sai, audit có thể bị thiếu. Cần metric cho:

- Event generated;
- Event accepted;
- Event rejected;
- Queue depth/lag;
- Dropped event count;
- Collector availability;
- Storage write failure;
- Schema validation failure.

Đừng chỉ theo dõi login failure; hãy theo dõi cả việc hệ thống còn ghi nhận được login failure hay không.

## 9. Phân quyền truy cập và bảo vệ audit data

Audit có thể chứa thông tin về hành vi người dùng, IP, thiết bị, tenant và trạng thái tài khoản. Quyền truy cập cần được giới hạn.

### Vai trò gợi ý

| Vai trò | Quyền phù hợp |
| --- | --- |
| Authentication service | Ghi event của chính service |
| SOC/security analyst | Tìm kiếm event theo phạm vi được cấp |
| Incident responder | Truy cập event chi tiết trong incident được phê duyệt |
| Compliance auditor | Đọc báo cáo và bằng chứng theo phạm vi |
| Log platform operator | Vận hành pipeline, không mặc nhiên được đọc mọi dữ liệu |
| Security administrator | Quản lý policy, retention và access; mọi thay đổi được audit |

Không nên để một tài khoản vừa có thể sửa event, xóa bản lưu, thay retention và xóa audit về chính hành động đó. Phân tách nhiệm vụ giúp giảm nguy cơ insider misuse.

Mọi truy vấn nhạy cảm, export, thay đổi quyền và thao tác retention nên được ghi nhận. Báo cáo cho tenant chỉ nên chứa dữ liệu thuộc tenant đó; không để analyst của tenant A tìm thấy subject hoặc IP thuộc tenant B ngoài quyền được cấp.

## 10. Retention, privacy và data minimization

Không có một thời hạn lưu audit phù hợp cho mọi tổ chức. Retention cần cân bằng điều tra, yêu cầu pháp lý, quyền riêng tư, chi phí và mức độ nhạy cảm.

### Xây dựng retention policy

Xác định theo từng loại event:

- Mục đích thu thập;
- Phân loại dữ liệu và độ nhạy cảm;
- Thời hạn cần cho detection và điều tra;
- Yêu cầu pháp lý/hợp đồng;
- Ai có quyền đọc;
- Có cần pseudonymization hoặc aggregation sau một khoảng thời gian không;
- Quy trình legal hold khi có incident;
- Cách xóa an toàn khi hết hạn.

### Phân tầng dữ liệu

Có thể tách:

- **Hot data:** dữ liệu gần đây phục vụ cảnh báo và điều tra nhanh;
- **Warm data:** dữ liệu lịch sử có thể truy vấn chậm hơn;
- **Archive:** dữ liệu cần giữ lâu theo policy hoặc legal hold;
- **Aggregated metrics:** số liệu tổng hợp không cần giữ raw identifier.

Không lưu raw event vô thời hạn chỉ vì dung lượng còn đủ. Ngược lại, không xóa log liên quan incident khi đang có yêu cầu bảo toàn bằng chứng.

### Pseudonymization

Subject reference có thể được tạo bằng mapping service hoặc HMAC với khóa riêng, để analyst liên kết event mà không thấy trực tiếp email/username. Cần quản lý khóa HMAC, rotation và khả năng re-identification có kiểm soát. Hash không khóa của email dễ bị dò bằng dictionary.

## 11. Phát hiện password spraying và credential stuffing

Login audit là nguồn quan trọng để phát hiện tấn công credential.

### Password spraying

Attacker thử một hoặc vài mật khẩu phổ biến trên nhiều tài khoản để tránh lockout theo từng tài khoản.

Dấu hiệu:

- Một IP/network/client thử đăng nhập nhiều subject;
- Mỗi subject chỉ có ít lần thất bại;
- Nhiều failure có cùng time window hoặc pattern;
- Có thể có một vài login success sau chuỗi thất bại.

### Credential stuffing

Attacker thử cặp username/password bị rò rỉ từ dịch vụ khác.

Dấu hiệu:

- Nhiều lần login failure trên nhiều tài khoản;
- Nhiều IP hoặc proxy thay đổi;
- User agent/device pattern lặp lại;
- Một số lần success xen kẽ failure;
- Login từ nguồn lạ sau chuỗi thất bại.

### Quy tắc phát hiện minh họa

`````````sql
SELECT
    source_network,
    COUNT(*) AS failed_attempts,
    COUNT(DISTINCT subject_ref) AS targeted_accounts
FROM auth_audit
WHERE event_name = 'auth.login.failed'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
GROUP BY source_network
HAVING COUNT(*) >= 40
   AND COUNT(DISTINCT subject_ref) >= 15;
`````````

Đây là SQL minh họa; cú pháp interval và tên cột tùy hệ thống. Ngưỡng 40/15 không phải chuẩn chung. Cần hiệu chỉnh theo lưu lượng, NAT, mạng doanh nghiệp, ứng dụng public và hành vi bình thường.

### Không khóa tài khoản chỉ dựa trên IP

Một địa chỉ IP có thể đại diện cho hàng trăm người dùng trong mạng doanh nghiệp hoặc nhà mạng. Lockout cứng theo IP có thể gây denial of service. Kết hợp rate limit, adaptive challenge, risk scoring, credential protection và theo dõi nhiều chiều.

## 12. Phát hiện MFA fatigue và lạm dụng step-up

Attacker có thể gây áp lực bằng cách gửi nhiều push request để người dùng mệt mỏi và bấm approve.

Các event cần liên kết:

- mfa.challenge.sent;
- mfa.challenge.denied;
- mfa.challenge.expired;
- mfa.challenge.approved;
- mfa.factor.added/removed;
- login.failed/succeeded;
- step_up.requested/succeeded/failed.

Dấu hiệu:

- Nhiều challenge gửi tới cùng user trong thời gian ngắn;
- Nhiều lần denied/expired trước một approval;
- Approval xảy ra ngay sau nhiều lần từ chối;
- Challenge phát sinh từ session/device/network không quen thuộc;
- Factor mới được thêm ngay sau login bất thường;
- Sau approval là hành động giá trị cao.

Không ghi OTP hoặc push secret vào log. Ghi challenge reference, delivery channel, outcome, timestamp, request source và action scope.

Biện pháp có thể gồm rate limit, number matching, hiển thị ứng dụng/hành động, hủy challenge cũ, yêu cầu user khởi tạo login và dùng phương thức phishing-resistant.

## 13. Phát hiện account takeover và credential lifecycle abuse

Account takeover thường không dừng ở một lần đăng nhập. Attacker có thể thay đổi credential hoặc recovery factor để giữ quyền truy cập.

### Chuỗi event đáng chú ý

1. Login failure tăng bất thường;
2. Login success từ thiết bị hoặc network mới;
3. MFA factor bị thêm, xóa hoặc reset;
4. Email/phone recovery bị thay đổi;
5. Session mới được tạo hoặc refresh;
6. Access tới dữ liệu nhạy cảm hoặc high-value action;
7. Logout hoặc revoke session cũ.

### Quy tắc tương quan

- Login success ngay sau nhiều failure;
- Recovery completed rồi login từ device mới;
- MFA factor reset và high-value action trong khoảng thời gian ngắn;
- Nhiều thiết bị mới được thêm cho cùng account;
- Một device reference liên tiếp thử nhiều subject;
- Session được tạo sau risk denial hoặc policy override;
- Credential bị revoke nhưng session vẫn tiếp tục hoạt động.

Các quy tắc cần dùng time window, subject reference, device reference và transaction context. Không kết luận takeover chỉ từ một tín hiệu; cần kết hợp bằng chứng và xác minh.

## 14. Phát hiện bất thường theo session và federation

Audit login cần liên kết với session lifecycle và federation events để biết đăng nhập có được dùng tiếp hay không.

### Session

- Session được tạo nhưng không có login success tương ứng;
- Một session reference xuất hiện ở nhiều device context bất thường;
- Session refresh sau khi account/credential bị revoke;
- Session còn active sau deprovisioning;
- Login success nhưng session creation thất bại;
- Session ID rotation không diễn ra sau reauthentication theo policy.

Không ghi session cookie hoặc raw session ID. Dùng session reference riêng không thể dùng để truy cập.

### OIDC/SAML federation

- Issuer hoặc audience mismatch;
- Signature validation failure tăng đột biến;
- State/nonce mismatch;
- SAML response/assertion replay;
- IdP key rotation bất thường;
- Federation connection bị thay đổi ngay trước login success;
- Login từ tenant/issuer không đúng connection.

Các event federation cần giữ issuer ID, provider ID, client/RP reference, transaction ID và reason code; không ghi raw ID token hoặc SAML assertion.

## 15. Từ alert đến incident response

Một alert có ích phải cung cấp đủ dữ liệu để analyst xác định mức độ và bước tiếp theo.

### Quy trình điều tra gợi ý

1. Xác định subject, tenant, client và khoảng thời gian.
2. Lấy timeline login.started, login.failed, login.succeeded và MFA/step-up events.
3. Liên kết session.created với các request sau đăng nhập.
4. Kiểm tra device/network context và credential lifecycle events.
5. Xác định hành động nhạy cảm đã xảy ra hay chưa.
6. Đối chiếu với người dùng/owner qua kênh liên lạc đã đăng ký trước đó.
7. Nếu có dấu hiệu compromise, revoke session/credential, reset factor hoặc disable account theo incident policy.
8. Bảo toàn audit liên quan và mở rộng tìm kiếm tới các subject/device/session khác.
9. Ghi lại quyết định, người thực hiện, thời điểm và lý do.
10. Sau xử lý, theo dõi login và session mới để xác nhận không còn hoạt động bất thường.

### Ví dụ timeline

| Thời điểm | Event | Diễn giải |
| --- | --- | --- |
| 09:00 | 25 login.failed trên 18 subject từ một network | Có thể là password spraying |
| 09:04 | login.succeeded cho một subject bị nhắm tới | Cần xác minh credential compromise |
| 09:05 | mfa.challenge.sent nhiều lần | Có thể là MFA fatigue |
| 09:06 | mfa.challenge.succeeded | Người dùng có thể đã approve một yêu cầu |
| 09:07 | session.created trên device mới | Kiểm tra thiết bị và owner |
| 09:09 | recovery.factor.changed | Rủi ro persistence/account takeover |
| 09:12 | high_value_action.completed | Đánh giá thiệt hại và thu hồi ngay theo policy |

Timeline trên chỉ minh họa một kịch bản. Các event cần được xác minh với nguồn có thẩm quyền trước khi kết luận.

## 16. Alerting và tránh false positive

Detection rule phải được hiệu chỉnh theo hành vi thực tế. Một sự kiện bất thường không luôn là tấn công:

- Nhiều người dùng cùng NAT có thể tạo failure từ một IP;
- Người dùng đổi điện thoại có thể tạo nhiều MFA failure;
- Mạng VPN có thể làm vị trí thay đổi;
- Sự cố IdP có thể tạo failure hàng loạt;
- Deployment lỗi có thể làm state/nonce mismatch;
- Đồng hồ lệch có thể khiến token hết hạn hoặc challenge bị coi là stale.

### Thiết kế alert

- Có mức severity và confidence riêng;
- Có reason code và evidence liên quan;
- Có suppression/deduplication để tránh alert storm;
- Có owner và runbook;
- Có thời gian đánh giá và escalation;
- Không tự động khóa tài khoản hàng loạt chỉ từ một rule chưa được xác minh;
- Theo dõi false positive và false negative.

Đối với hành động tự động như revoke session hoặc suspend account, cần xác định điều kiện, phạm vi, khả năng rollback và audit của quyết định tự động.

## 17. Ví dụ truy vấn điều tra

### Tìm chuỗi đăng nhập của một subject

`````````sql
SELECT
    occurred_at,
    event_name,
    outcome,
    reason_code,
    client_id,
    device_ref,
    session_ref,
    interaction_id
FROM auth_audit
WHERE subject_ref = 'usr-ref-7b2a'
  AND occurred_at >= TIMESTAMP '2026-11-22 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-11-23 00:00:00'
ORDER BY occurred_at;
`````````

### Tìm success sau nhiều failure

`````````sql
WITH attempts AS (
    SELECT
        subject_ref,
        occurred_at,
        event_name,
        COUNT(*) FILTER (
            WHERE event_name = 'auth.login.failed'
        ) OVER (
            PARTITION BY subject_ref
            ORDER BY occurred_at
            RANGE BETWEEN INTERVAL '15 minutes' PRECEDING
                  AND CURRENT ROW
        ) AS recent_failures
    FROM auth_audit
    WHERE event_name IN ('auth.login.failed', 'auth.login.succeeded')
)
SELECT *
FROM attempts
WHERE event_name = 'auth.login.succeeded'
  AND recent_failures >= 8;
`````````

Đây là SQL minh họa; hỗ trợ window frame và FILTER tùy hệ quản trị. Trong môi trường thật cần kiểm tra dữ liệu trùng, event đến trễ, timezone và cách đếm retry.

### Tìm thay đổi factor ngay sau login từ thiết bị mới

`````````sql
SELECT
    l.subject_ref,
    l.occurred_at AS login_time,
    l.device_ref,
    c.occurred_at AS factor_change_time,
    c.event_name AS factor_event
FROM auth_audit l
JOIN auth_audit c
  ON c.subject_ref = l.subject_ref
 AND c.occurred_at >= l.occurred_at
 AND c.occurred_at < l.occurred_at + INTERVAL '30 minutes'
WHERE l.event_name = 'auth.login.succeeded'
  AND c.event_name IN (
      'auth.mfa.factor.added',
      'auth.mfa.factor.removed',
      'auth.recovery.factor.changed'
  );
`````````

Truy vấn này tìm candidate để điều tra; nó không chứng minh hành vi trái phép. Cần xác định device mới dựa trên registry/history và đối chiếu policy.

## 18. Chất lượng dữ liệu và tính đầy đủ của audit

Audit thiếu hoặc sai schema có thể khiến detection bỏ sót tấn công.

### Kiểm soát chất lượng

- Event name nằm trong taxonomy đã đăng ký;
- event_version được khai báo;
- event_id không trùng;
- occurred_at và recorded_at hợp lệ;
- outcome và reason_code dùng giá trị chuẩn;
- subject/tenant/client reference có namespace rõ;
- Correlation ID được truyền qua các service liên quan;
- Secret redaction được thực hiện trước khi event rời service;
- Schema validation failure được đo và cảnh báo;
- Event drop, queue backlog và collector outage được theo dõi.

### Đối chiếu chéo

Có thể đối chiếu:

- Login success với session creation;
- Session revocation với trạng thái session tại session store;
- MFA success với challenge đã phát;
- Credential added với enrollment transaction;
- Recovery completed với approval workflow;
- Admin action với change record;
- Federation success với issuer/connection configuration.

Nếu có login success nhưng không có session.created, cần điều tra xem session creation bị lỗi hay event bị mất. Không tự giả định event thiếu nghĩa là hành động không xảy ra.

## 19. Chỉ số vận hành

Các chỉ số nên được phân loại theo tenant, client, method, outcome và reason code trong giới hạn quyền truy cập.

| Metric | Ý nghĩa |
| --- | --- |
| Login success rate | Tỷ lệ login thành công trên tổng attempt |
| Login failure rate | Tỷ lệ thất bại theo method/client/reason |
| MFA challenge failure rate | Tỷ lệ MFA không hoàn tất hoặc bị từ chối |
| Step-up completion rate | Tỷ lệ hoàn thành step-up |
| New-device login rate | Tỷ lệ login từ device chưa thấy trước đó |
| Account lockout rate | Tỷ lệ account bị khóa theo policy |
| Recovery completion rate | Tỷ lệ recovery hoàn tất |
| Session revocation latency | Thời gian từ revoke tới khi mọi điểm thực thi từ chối |
| Audit event delivery lag | Độ trễ từ occurred_at tới recorded_at |
| Audit event loss rate | Tỷ lệ event bị drop hoặc không được ghi |
| Schema rejection rate | Tỷ lệ event không qua schema validation |
| Detection precision | Tỷ lệ alert được xác nhận có giá trị |

Không đánh giá sức khỏe xác thực chỉ bằng login success rate. Success rate tăng có thể là tốt hơn UX, nhưng cũng có thể do policy bị nới hoặc verifier chấp nhận token sai. Kết hợp metric với security outcome và kiểm thử.

## 20. Checklist triển khai Login audit

- **Event taxonomy:** Có event cho login success/failure, MFA, step-up, recovery, credential và session lifecycle?
- **Authoritative source:** Event được ghi tại server/service thực sự xác minh và quyết định?
- **Schema:** Có event ID, version, timestamps, outcome, reason code, tenant, subject/client reference và correlation?
- **Time:** Dùng UTC, clock sync và phân biệt occurred_at với recorded_at?
- **Secret redaction:** Không ghi password, OTP, token, cookie, private key, authorization code hoặc recovery code?
- **Privacy:** IP, device và personal data có mục đích, quyền truy cập và retention rõ?
- **Integrity:** Transport được bảo vệ, storage append-only/immutable khi cần và quản trị log được audit?
- **Access control:** Quyền đọc/export/delete tách biệt và theo least privilege?
- **Retention:** Có hot/warm/archive, legal hold và xóa an toàn?
- **Correlation:** Có thể liên kết login, MFA, session, recovery và API activity?
- **Detection:** Có rule cho spraying, stuffing, MFA fatigue, takeover và credential lifecycle abuse?
- **False positive:** Có deduplication, tuning, runbook và escalation?
- **Pipeline health:** Theo dõi dropped events, queue lag, collector outage và schema failures?
- **Incident response:** Analyst có thể dựng timeline và revoke session/credential theo quy trình?
- **Testing:** Đã kiểm thử event coverage, redaction, integrity, delivery failure và detection logic?

### Câu hỏi tự kiểm tra

1. Vì sao login audit cần ghi cả thất bại chứ không chỉ thành công?
2. Audit trail khác application log và access log ở mục đích nào?
3. Vì sao không được ghi password, OTP, bearer token hoặc session cookie?
4. occurred_at khác recorded_at như thế nào?
5. interaction_id và correlation_id giúp điều tra điều gì?
6. Password spraying khác credential stuffing ở pattern nào?
7. Những event nào giúp phát hiện MFA fatigue?
8. Vì sao một login success không tự chứng minh session đã được tạo?
9. Hash chain bảo vệ audit log tới đâu và không bảo vệ được điều gì?
10. Cần theo dõi chỉ số nào để biết audit pipeline đang mất event?

## Kết luận

**Login audit biến quá trình đăng nhập thành một chuỗi sự kiện có thể kiểm chứng và điều tra.** Hệ thống cần ghi nhận cả thành công, thất bại, MFA, step-up, recovery, thay đổi credential và vòng đời session tại các điểm thực thi có thẩm quyền. Mỗi event cần schema ổn định, timestamp rõ, reason code, subject/client/device reference và correlation ID; đồng thời phải loại bỏ password, OTP, token, cookie, private key và dữ liệu bí mật. Audit store cần được bảo vệ bằng phân quyền, mã hóa, integrity, retention và giám sát pipeline. Khi liên kết event với detection rules, session history và credential lifecycle, đội bảo mật có thể phát hiện spraying, stuffing, MFA fatigue và account takeover sớm hơn, đồng thời dựng timeline đáng tin cậy khi xảy ra sự cố.
