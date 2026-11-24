# Adaptive challenge: điều chỉnh xác thực theo rủi ro

> **Chương:** Risk-based authentication  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào adaptive challenge: dùng ngữ cảnh và tín hiệu rủi ro để quyết định khi nào cho phép tiếp tục, khi nào yêu cầu step-up, khi nào giới hạn hoặc từ chối, đồng thời giữ yêu cầu assurance và quyền truy cập nhất quán.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích risk-based authentication và adaptive challenge; phân biệt risk signal với bằng chứng xác thực danh tính.
2. Nhận diện tín hiệu rủi ro từ tài khoản, thiết bị, mạng, hành vi, phiên và giao dịch.
3. Thiết kế policy kết hợp baseline assurance, mức rủi ro và độ nhạy của hành động.
4. Chọn challenge phù hợp như passkey, security key, TOTP hoặc re-authentication theo khả năng chống phishing và ràng buộc giao dịch.
5. Tránh hạ thấp yêu cầu bảo mật chỉ vì risk score thấp hoặc tín hiệu thiết bị có vẻ quen thuộc.
6. Thiết kế các quyết định ALLOW, STEP_UP, RESTRICT và DENY cùng cách xử lý lỗi, timeout và abuse.
7. Giảm false positive, bảo vệ quyền riêng tư và đánh giá tác động không công bằng của risk signals.
8. Triển khai policy engine/PDP và enforcement/PEP trong Java/Spring, đồng thời xây dựng ma trận kiểm thử.

## 2. Risk-based authentication là gì?

**Risk-based authentication (RBA)** là cách điều chỉnh yêu cầu xác thực dựa trên ngữ cảnh của request và tín hiệu rủi ro. Hệ thống đánh giá một request có dấu hiệu bất thường hoặc có tác động cao đến đâu, sau đó chọn hành động phù hợp.

Ví dụ:

- User đăng nhập từ thiết bị thường dùng, sau đó xem trang hồ sơ thông thường: có thể tiếp tục với phiên hợp lệ hiện tại.
- User đăng nhập từ môi trường mới rồi yêu cầu thay đổi email khôi phục: có thể yêu cầu xác thực lại bằng phương thức mạnh.
- Một session có hành vi bất thường và đang cố thêm authenticator mới: có thể tạm hạn chế thao tác hoặc yêu cầu xác minh bổ sung.
- Credential bị xác nhận compromise hoặc request có dấu hiệu tấn công rõ ràng: có thể từ chối và kích hoạt quy trình bảo vệ tài khoản.

Adaptive challenge là phần policy chọn **challenge nào, cho hành động nào, trong thời hạn nào**. Nó không phải một phép đo danh tính độc lập. Risk score chỉ là đầu vào hỗ trợ quyết định; bằng chứng xác thực vẫn phải được xác minh theo giao thức.

## 3. RBA không thay thế authentication và authorization

Ba câu hỏi cần tách biệt:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** | Chủ thể có chứng minh được quyền kiểm soát authenticator đã đăng ký không? | WebAuthn assertion hợp lệ |
| **Risk assessment** | Request/session có tín hiệu bất thường hoặc mức rủi ro nào? | IP mới, credential stuffing pattern, transaction anomaly |
| **Authorization** | Chủ thể có quyền thực hiện action trên resource này không? | User có quyền sửa hóa đơn thuộc tenant của mình |

Một request có risk thấp không có nghĩa user được quyền truy cập tài nguyên. Một request đã qua step-up cũng không tự động được phép thực hiện mọi hành động. Sau challenge, API vẫn phải kiểm tra principal, audience, scope, tenant, ownership và policy.

Ngược lại, risk cao không nhất thiết có nghĩa danh tính sai. Người dùng hợp lệ có thể đi du lịch, đổi điện thoại hoặc dùng mạng doanh nghiệp mới. Policy cần phản ứng theo mức rủi ro và tác động của hành động, không tự động gán nhãn người dùng là attacker.

## 4. Các chiều rủi ro cần xem xét

Risk engine có thể kết hợp nhiều nhóm tín hiệu:

| Nhóm | Ví dụ | Giới hạn |
|---|---|---|
| **Account** | Tuổi tài khoản, lần recovery gần đây, thay đổi mật khẩu, authenticator mới | Không nên dùng tuổi tài khoản làm bằng chứng danh tính |
| **Credential** | Credential stuffing, mật khẩu bị lộ theo nguồn threat intelligence, số lần thất bại | Không log hoặc lưu mật khẩu để tính risk |
| **Device** | Thiết bị đã đăng ký, trạng thái quản lý, key/device attestation nếu có | Fingerprint có thể thay đổi hoặc bị giả mạo |
| **Network** | IP/ASN mới, proxy/Tor signal, reputation, vị trí ước lượng | IP dùng chung, VPN và roaming gây false positive |
| **Behavior** | Tốc độ thao tác, chuỗi hành động, thời gian, pattern automation | Cần tối thiểu hóa dữ liệu và tránh profiling quá mức |
| **Session** | Session age, auth_time, thay đổi privilege, session anomaly | Session lâu không có nghĩa tự động bị compromise |
| **Transaction** | Giá trị, người nhận mới, thay đổi thông tin thanh toán, hành động không thể đảo ngược | Cần binding với dữ liệu giao dịch server-side |
| **Threat intelligence** | Credential leak, bot source, known malicious infrastructure | Nguồn dữ liệu có độ trễ và sai số |

Không phải tín hiệu nào cũng có giá trị giống nhau trong mọi use case. Một IP mới có thể ít quan trọng khi xem tài liệu công khai, nhưng đáng xem xét hơn khi cùng lúc có recovery mới và yêu cầu chuyển tiền giá trị cao.

## 5. Risk signal không phải identity proof

Một số tín hiệu chỉ mô tả môi trường, không chứng minh người đang thao tác là đúng người:

- IP address không phải danh tính; nhiều người có thể dùng chung NAT hoặc proxy.
- User-Agent dễ giả mạo và không phải secret.
- Device fingerprint không phải bằng chứng mật mã về quyền kiểm soát thiết bị.
- Geolocation chỉ là ước lượng từ mạng hoặc thiết bị; không nên xem như vị trí chính xác.
- Cookie lâu năm có thể bị sao chép; “thiết bị quen thuộc” không đảm bảo session chưa bị đánh cắp.
- Một lần đăng nhập thành công trước đó không chứng minh request hiện tại an toàn.

Tín hiệu thiết bị mạnh hơn có thể đến từ device-bound key, managed-device attestation hoặc sender-constrained credential, nhưng vẫn cần xác minh theo trust model và khả năng chống compromise của endpoint.

Policy nên ghi rõ mỗi tín hiệu là:

1. Bằng chứng giao thức có thể xác minh mật mã.
2. Trạng thái server-side có nguồn authoritative.
3. Tín hiệu rủi ro có độ tin cậy và thời hạn.

Không cộng một fingerprint yếu vào điểm số rồi tuyên bố đã xác minh thiết bị.

## 6. Mô hình quyết định adaptive challenge

Một policy tốt kết hợp **baseline assurance bắt buộc** với risk assessment:

1. Kiểm tra request có credential/session hợp lệ không.
2. Xác định principal, client, resource và action.
3. Tính baseline assurance mà action yêu cầu.
4. Thu thập các risk signals phù hợp và đánh giá độ tin cậy của từng tín hiệu.
5. Xác định risk band và các rule bắt buộc.
6. Chọn ALLOW, STEP_UP, RESTRICT hoặc DENY.
7. Nếu STEP_UP, chọn authenticator đáp ứng baseline và ràng buộc challenge với request.
8. Sau khi challenge thành công, đánh giá lại policy và authorization trước khi thực hiện action.

~~~mermaid
flowchart TD
    A["Incoming request"] --> B["Validate session/token and identify principal"]
    B --> C["Resolve client, resource and action"]
    C --> D["Check mandatory baseline assurance"]
    D --> E["Collect trusted risk signals"]
    E --> F["Evaluate policy and risk band"]
    F --> G{"Decision"}
    G -->|"ALLOW"| H["Continue to authorization"]
    G -->|"STEP_UP"| I["Issue context-bound challenge"]
    G -->|"RESTRICT"| J["Limit action or require review"]
    G -->|"DENY"| K["Reject and record security event"]
    I --> L{"Challenge verified?"}
    L -->|"Yes"| M["Re-evaluate policy and authorization"]
    L -->|"No / expired"| K
    H --> N["Execute only if resource policy allows"]
    M --> N
~~~

Baseline assurance không được hạ chỉ vì risk score thấp. Ví dụ, một thao tác quản trị bắt buộc phishing-resistant MFA thì thiết bị quen thuộc không thể biến mật khẩu đơn thành đủ assurance.

## 7. Các quyết định policy

| Quyết định | Ý nghĩa | Ví dụ |
|---|---|---|
| **ALLOW** | Cho tiếp tục nếu authentication và authorization đều hợp lệ | Đọc dữ liệu ít nhạy cảm, risk thấp |
| **STEP_UP** | Yêu cầu bằng chứng xác thực mạnh hơn hoặc gần thời điểm hơn | Thêm passkey, đổi recovery, thao tác giá trị cao |
| **RESTRICT** | Giới hạn chức năng hoặc yêu cầu review | Cho xem trạng thái nhưng chưa cho chuyển tiền |
| **DENY** | Từ chối request theo rule bắt buộc hoặc rủi ro không chấp nhận | Credential bị thu hồi, proof sai, dấu hiệu compromise rõ |

RESTRICT có thể là:

- Chỉ cho đọc, tạm khóa thay đổi bảo mật.
- Giới hạn số lượng hoặc giá trị giao dịch.
- Yêu cầu thời gian chờ sau recovery.
- Chuyển sang review thủ công.
- Thu hồi phiên hiện tại và yêu cầu đăng nhập lại từ kênh đáng tin.

Không dùng DENY chỉ vì một tín hiệu yếu đơn lẻ nếu điều đó gây khóa nhầm diện rộng. Tuy nhiên, rule bắt buộc như token không hợp lệ, credential bị thu hồi hoặc chữ ký challenge sai phải luôn bị từ chối.

## 8. Risk score và risk band

Một số hệ thống tạo điểm số hoặc risk band như LOW, MEDIUM, HIGH. Điểm số có thể hỗ trợ policy, nhưng không có thang điểm chung đúng cho mọi tổ chức.

Ví dụ minh họa:

~~~text
Risk signals:
  unfamiliar_network       = true
  recent_account_recovery  = true
  known_credential_abuse   = false
  high_value_action        = true

Policy result:
  risk_band = HIGH
  decision  = STEP_UP or RESTRICT
  required_assurance = PHISHING_RESISTANT
~~~

Không xem ví dụ này là ngưỡng production. Ngưỡng cần được hiệu chỉnh bằng dữ liệu, threat model, chi phí false positive/negative và thử nghiệm có giám sát.

### Rule bắt buộc và score

Nên tách:

- **Hard constraints:** token sai chữ ký, session revoked, credential compromise được xác nhận, challenge replay, account disabled. Các điều kiện này không được bù trừ bằng điểm rủi ro thấp.
- **Risk score/band:** tổng hợp tín hiệu có sai số để chọn challenge hoặc restriction.
- **Action baseline:** mức assurance tối thiểu theo độ nhạy của action/resource.

Không dùng phép cộng điểm để cho phép một request vi phạm hard constraint.

## 9. Chọn adaptive challenge phù hợp

Challenge phải đáp ứng mức assurance bắt buộc và phù hợp với rủi ro:

| Phương thức | Đặc điểm | Khi cân nhắc |
|---|---|---|
| **Passkey/WebAuthn** | Có thể chống phishing nhờ ràng buộc origin/RP ID và proof bằng khóa | Step-up cho thao tác nhạy cảm nếu credential và policy đáp ứng |
| **Security key** | Authenticator phần cứng, thường hỗ trợ phishing-resistant WebAuthn | Tài khoản đặc quyền hoặc assurance cao |
| **TOTP** | Mã theo thời gian, dựa trên shared secret | Step-up khi policy chấp nhận; có nguy cơ phishing/relay |
| **Push approval** | Xác nhận qua app đã đăng ký | Cần number matching/context, chống push fatigue |
| **Password re-entry** | Xác nhận lại knowledge factor | Không đủ nếu yêu cầu phishing-resistant MFA |
| **Recovery code** | Mã dự phòng một lần | Recovery theo policy; không mặc định tương đương authenticator mạnh |
| **mTLS/DPoP** | Ràng buộc token với certificate/key của client | Workload/API sender-constraining; không phải challenge tương tác user thông thường |

Không phải cứ thêm một factor là assurance tăng theo cách đơn giản. Hai phương thức có thể phụ thuộc cùng một thiết bị, cùng một kênh hoặc cùng một yếu tố bị compromise. Policy cần đánh giá independence và phishing resistance theo chuẩn/định nghĩa đã chọn.

### Không hạ challenge xuống phương thức yếu hơn

Nếu action yêu cầu phishing-resistant authentication, việc passkey không khả dụng không nên tự động dẫn tới SMS hoặc email code. Có thể:

- Yêu cầu một security key/passkey khác đã đăng ký.
- Chuyển sang recovery có assurance tương đương và review bổ sung.
- Tạm giữ thao tác cho đến khi người dùng có phương thức phù hợp.

Fallback là một phần của threat model. Kẻ tấn công thường nhắm vào đường fallback yếu hơn đường chính.

## 10. Challenge phải được ràng buộc với đúng request

Step-up thành công không nên chỉ là một cờ boolean MFA đã qua. Challenge/grant cần gắn với:

- Principal (issuer + subject/account).
- Session ID/version và client.
- Resource/tenant.
- Action cụ thể.
- Transaction digest/version nếu là giao dịch.
- Assurance/phương thức được chấp nhận.
- Thời điểm xác thực và thời hạn grant.
- Trạng thái đã tiêu thụ hay chưa.

Ví dụ:

~~~text
Step-up context:
  principal = user-104
  session = current-session-version
  client = banking-web
  resource = account-A104
  action = TRANSFER
  transaction_digest = SHA256(canonical_transaction)
  required_assurance = PHISHING_RESISTANT
  expires_at = short-deadline
  consumed = false
~~~

Nếu số tiền, người nhận, currency hoặc transaction version thay đổi sau khi user xác nhận, challenge cũ phải mất hiệu lực.

## 11. Session freshness và re-authentication

Risk policy cần phân biệt:

- **Token issuance time (iat):** thời điểm token được phát hành.
- **Authentication time (auth_time):** thời điểm user thực sự xác thực theo claim/profile.
- **Session creation time:** thời điểm local session được tạo.
- **Step-up time:** thời điểm challenge bổ sung hoàn tất.

Token mới không nhất thiết đồng nghĩa user vừa xác thực lại; token có thể được refresh trong khi authentication event cũ. Với thao tác nhạy cảm, policy nên dựa trên auth_time/step-up event đã xác minh và giới hạn freshness.

Ví dụ:

- Xem trang hồ sơ: session còn hạn có thể đủ.
- Thay đổi mật khẩu hoặc authenticator: yêu cầu re-authentication gần đây.
- Chuyển tiền giá trị cao: step-up mới, transaction binding và kiểm tra quyền tài khoản.
- Tài khoản admin: phishing-resistant method và freshness chặt hơn.

## 12. Context-aware policy không được biến thành device fingerprint authentication

Một thiết bị đã thấy trước đó có thể tăng độ tin cậy của ngữ cảnh, nhưng không phải bằng chứng duy nhất để xác thực:

- Cookie thiết bị có thể bị sao chép.
- Fingerprint có thể thay đổi sau cập nhật browser hoặc privacy settings.
- Nhiều người dùng có thể chia sẻ máy.
- Attacker có thể dùng cùng VPN/proxy hoặc giả User-Agent.
- Thiết bị đã đăng ký có thể bị malware kiểm soát.

Nếu cần ràng buộc thiết bị mạnh, dùng cơ chế proof-of-possession/attestation phù hợp và hiểu rõ trust model. Ngay cả attestation cũng không chứng minh user có quyền trên resource; authorization vẫn là bước riêng.

## 13. Abuse controls cho challenge

Adaptive challenge tự nó có thể bị lạm dụng để gây phiền hoặc khóa tài khoản:

- **MFA fatigue/push bombing:** gửi nhiều push để user vô tình chấp nhận.
- **OTP brute force:** thử nhiều mã trong cửa sổ thời gian.
- **Challenge flooding:** tạo số lượng lớn challenge để tăng tải hoặc gây nhầm lẫn.
- **Recovery abuse:** lợi dụng challenge yếu để thay authenticator.
- **Step-up downgrade:** cố tình chọn fallback yếu hơn.
- **Enumeration:** response khác nhau tiết lộ tài khoản có tồn tại hoặc có phương thức nào.

Kiểm soát:

- Rate limit theo account, session, IP/network và challenge ID; tránh chỉ giới hạn theo IP.
- Giới hạn số challenge pending và thời gian sống.
- Cooldown/backoff và phát hiện push fatigue.
- Number matching hoặc hiển thị context rõ cho push.
- Không tiết lộ quá nhiều thông tin trong error response.
- Ghi nhận challenge issued/approved/denied/expired với correlation ID.
- Có quy trình user báo cáo prompt không do họ khởi tạo.
- Giới hạn số lần fallback và không cho fallback yếu hơn baseline.

Rate limit cần cân bằng để không dễ gây denial-of-service cho người dùng hợp lệ. Khi khóa tạm, cung cấp con đường recovery an toàn và thông báo phù hợp.

## 14. Privacy, fairness và chất lượng risk signal

Risk engine có thể xử lý IP, vị trí ước lượng, device attributes, hành vi và dữ liệu tài khoản. Đây là dữ liệu có thể nhạy cảm hoặc tạo tác động khác nhau giữa nhóm người dùng.

Nguyên tắc:

1. Thu thập tín hiệu cần thiết cho mục đích bảo vệ cụ thể.
2. Không lưu lịch sử vị trí chi tiết nếu chỉ cần một tín hiệu coarse-grained.
3. Đặt retention và quyền truy cập cho risk telemetry.
4. Không dùng thuộc tính nhạy cảm hoặc proxy của chúng làm tín hiệu phân biệt đối xử.
5. Đo false positive/negative theo nhóm và điều kiện sử dụng phù hợp với pháp luật/chính sách.
6. Có cơ chế review/appeal cho người dùng bị chặn nhầm.
7. Giải thích ở mức an toàn: thông báo hành động cần làm mà không tiết lộ rule chống gian lận quá chi tiết.
8. Theo dõi drift khi hành vi người dùng, mạng hoặc threat landscape thay đổi.

Một mô hình có accuracy tổng thể cao vẫn có thể gây tỷ lệ challenge sai khác nhau giữa các nhóm hoặc vùng mạng. Cần đánh giá chất lượng theo tác động thực tế, không chỉ một con số tổng.

## 15. Kiến trúc policy engine: PDP và PEP

Một thiết kế thường tách:

- **Policy Decision Point (PDP):** nhận principal, action, resource, authentication context và risk signals; trả về quyết định cùng yêu cầu assurance/challenge.
- **Policy Enforcement Point (PEP):** thực thi quyết định tại gateway, controller hoặc service.
- **Signal providers:** cung cấp risk signal có nguồn, timestamp, confidence và expiry.
- **Challenge service:** tạo và xác minh challenge gắn context.
- **Session/token service:** kiểm tra trạng thái, freshness và revoke.
- **Audit/telemetry:** ghi decision ID, reason code và kết quả mà không lưu secret.

~~~mermaid
flowchart LR
    REQ["Request"] --> PEP["PEP / API gateway"]
    PEP --> PDP["Policy Decision Point"]
    PDP <-->|"Signals + confidence + age"| SIG["Risk signal providers"]
    PDP <-->|"Session, auth_time, assurance"| SES["Session / identity service"]
    PDP --> DEC["ALLOW / STEP_UP / RESTRICT / DENY"]
    DEC --> PEP
    PEP --> CH["Challenge service"]
    CH --> AUTH["Registered authenticator"]
    PEP --> API["Resource authorization + action"]
    PDP --> AUD["Decision audit"]
    CH --> AUD
~~~

Decision nên có:

- decision_id để correlation.
- decision và reason_codes.
- required_assurance và allowed_methods.
- challenge_purpose/transaction_binding nếu step-up.
- expires_at và policy version.

Không trả toàn bộ rule hoặc fraud threshold cho client; reason code có thể đủ để vận hành và hỗ trợ người dùng.

## 16. Xử lý lỗi và fail-open/fail-closed

Risk service có thể lỗi, chậm hoặc trả về dữ liệu stale. Policy phải xác định trước cách xử lý:

| Tình huống | Hành vi gợi ý |
|---|---|
| Risk service timeout khi đọc dữ liệu ít nhạy cảm | Dùng baseline assurance và policy fallback đã định nghĩa; ghi nhận degraded mode |
| Risk service timeout khi chuyển tiền giá trị cao | Restrict hoặc step-up theo baseline; không mặc định risk thấp |
| Authenticator verification lỗi | Từ chối challenge; không tự cho phép action |
| Signal provider trả dữ liệu stale | Giảm confidence hoặc bỏ tín hiệu theo TTL; không coi stale là bằng chứng mới |
| Challenge service unavailable | Giữ thao tác nhạy cảm; không bypass challenge |
| Session revoked | Deny dù risk score thấp |
| Policy engine không khả dụng | Dùng policy fallback đã phê duyệt theo action; ưu tiên fail-closed với hành động đặc quyền |

**Fail-open** chỉ có thể phù hợp với hành động ít nhạy cảm khi baseline authentication và authorization vẫn được bảo đảm, phạm vi/time window giới hạn và có audit. Fail-open không có nghĩa bỏ qua chữ ký, token validation, session revocation hoặc authorization.

## 17. Java: mô hình hóa risk assessment và quyết định

Ví dụ sau minh họa tách risk signal khỏi baseline assurance và policy decision:

~~~java
enum Assurance {
    PASSWORD_ONLY,
    MFA,
    PHISHING_RESISTANT
}

enum Decision {
    ALLOW,
    STEP_UP,
    RESTRICT,
    DENY
}

record RiskSignals(
    boolean credentialAbuseConfirmed,
    boolean recentRecovery,
    boolean unfamiliarNetwork,
    boolean unusualTransaction,
    Instant observedAt
) {}

record AuthContext(
    String principalId,
    String sessionId,
    String clientId,
    String audience,
    Assurance currentAssurance,
    Instant authenticatedAt
) {}

record AccessIntent(
    String action,
    String resourceId,
    Assurance requiredBaseline,
    boolean highImpact
) {}

record PolicyDecision(
    Decision decision,
    Assurance requiredAssurance,
    Set<String> allowedMethods,
    Set<String> reasonCodes
) {}
~~~

Policy engine:

~~~java
final class AdaptiveAuthenticationPolicy {

    PolicyDecision evaluate(
            AuthContext auth,
            AccessIntent intent,
            RiskSignals risk,
            Instant now) {

        if (risk.credentialAbuseConfirmed()) {
            return decision(
                Decision.DENY,
                intent.requiredBaseline(),
                Set.of(),
                "CONFIRMED_CREDENTIAL_ABUSE"
            );
        }

        boolean riskSignalFresh = risk.observedAt() != null
            && !risk.observedAt().isAfter(now)
            && !risk.observedAt().isBefore(now.minus(Duration.ofMinutes(2)));

        if (!riskSignalFresh && intent.highImpact()) {
            return decision(
                Decision.RESTRICT,
                intent.requiredBaseline(),
                Set.of(),
                "RISK_SIGNAL_MISSING_OR_STALE"
            );
        }

        if (auth.authenticatedAt() == null
                || auth.authenticatedAt().isAfter(now)) {
            return decision(
                Decision.STEP_UP,
                intent.requiredBaseline(),
                methodsFor(intent.requiredBaseline()),
                "AUTHENTICATION_CONTEXT_INVALID"
            );
        }

        if (intent.highImpact()
                && auth.authenticatedAt().isBefore(
                    now.minus(Duration.ofMinutes(5)))) {
            return decision(
                Decision.STEP_UP,
                intent.requiredBaseline(),
                methodsFor(intent.requiredBaseline()),
                "AUTHENTICATION_NOT_FRESH"
            );
        }

        if (strength(auth.currentAssurance())
                < strength(intent.requiredBaseline())) {
            return decision(
                Decision.STEP_UP,
                intent.requiredBaseline(),
                methodsFor(intent.requiredBaseline()),
                "BASELINE_ASSURANCE_NOT_MET"
            );
        }

        if (risk.recentRecovery() && intent.highImpact()) {
            return decision(
                Decision.RESTRICT,
                intent.requiredBaseline(),
                Set.of(),
                "RECENT_RECOVERY_HIGH_IMPACT"
            );
        }

        if (risk.unusualTransaction() && intent.highImpact()) {
            return decision(
                Decision.STEP_UP,
                Assurance.PHISHING_RESISTANT,
                methodsFor(Assurance.PHISHING_RESISTANT),
                "UNUSUAL_HIGH_IMPACT_TRANSACTION"
            );
        }

        if (risk.unfamiliarNetwork() && intent.highImpact()) {
            return decision(
                Decision.STEP_UP,
                intent.requiredBaseline(),
                methodsFor(intent.requiredBaseline()),
                "UNFAMILIAR_NETWORK_HIGH_IMPACT"
            );
        }

        return decision(
            Decision.ALLOW,
            intent.requiredBaseline(),
            Set.of(),
            "BASELINE_AND_POLICY_SATISFIED"
        );
    }

    private int strength(Assurance assurance) {
        return switch (assurance) {
            case PASSWORD_ONLY -> 1;
            case MFA -> 2;
            case PHISHING_RESISTANT -> 3;
        };
    }

    private Set<String> methodsFor(Assurance assurance) {
        return switch (assurance) {
            case PASSWORD_ONLY -> Set.of("PASSWORD");
            case MFA -> Set.of("TOTP", "PUSH_WITH_NUMBER_MATCHING");
            case PHISHING_RESISTANT -> Set.of("WEBAUTHN", "SECURITY_KEY");
        };
    }

    private PolicyDecision decision(
            Decision decision,
            Assurance assurance,
            Set<String> methods,
            String reason) {
        return new PolicyDecision(
            decision,
            assurance,
            methods,
            Set.of(reason)
        );
    }
}
~~~

Đây là policy minh họa, không phải risk model production. Hệ thống thực tế cần xác minh session/token trước khi gọi policy, kiểm tra tuổi và nguồn của từng signal, xử lý signal thiếu/stale, định nghĩa action baseline và tránh coi danh sách phương thức là đảm bảo assurance nếu verifier chưa kiểm tra đầy đủ.

### Enforcement sau challenge

PEP không được thực hiện action chỉ vì challenge endpoint trả về HTTP 200. Nó phải xác minh grant đã ký/lưu server-side, principal/session/action/resource/transaction khớp, chưa hết hạn/chưa tiêu thụ và authorization vẫn cho phép.

## 18. Ma trận kiểm thử adaptive challenge

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Session/token không hợp lệ | DENY, không phụ thuộc risk score |
| Credential compromise được xác nhận | DENY hoặc containment theo incident policy |
| Baseline assurance cao hơn phiên hiện tại | STEP_UP |
| Risk thấp nhưng action yêu cầu phishing-resistant MFA | Vẫn STEP_UP |
| Thiết bị quen thuộc nhưng session đã revoked | DENY |
| IP mới đơn lẻ với hành động ít nhạy cảm | Không tự động khóa tài khoản; áp dụng policy đã định nghĩa |
| Recovery gần đây và yêu cầu thay authenticator | RESTRICT/STEP_UP theo recovery policy |
| Giao dịch bất thường giá trị cao | STEP_UP và transaction binding |
| Challenge cho action A dùng ở action B | Từ chối |
| Challenge của account A dùng ở account B | Từ chối |
| Challenge hết hạn hoặc replay | Từ chối |
| Hai request tiêu thụ cùng grant đồng thời | Chỉ một request thành công |
| Passkey assertion sai origin/RP ID | Từ chối |
| TOTP bị yêu cầu thay cho phishing-resistant baseline | Không hạ cấp |
| Push approval không có number matching khi policy yêu cầu | Từ chối |
| Risk signal stale hoặc thiếu timestamp | Giảm confidence/bỏ tín hiệu theo policy, không mặc định risk thấp |
| Risk service timeout với action nhạy cảm | Restrict/step-up/fail-closed theo policy |
| Risk service timeout với action ít nhạy cảm | Chỉ fallback nếu baseline và authorization vẫn hợp lệ |
| Risk score thấp nhưng user không có quyền resource | Authorization từ chối |
| Transaction amount/beneficiary đổi sau step-up | Grant cũ mất hiệu lực |
| Người dùng báo push không khởi tạo | Có thể từ chối, containment và audit |
| Nhiều challenge liên tiếp | Rate limit/cooldown, không gây push bombing |
| User-Agent/IP thay đổi nhưng proof mật mã hợp lệ | Không tự coi proof vô hiệu chỉ vì tín hiệu đó |
| Policy version thay đổi khi challenge đang pending | Challenge được xử lý theo version/expiry policy rõ ràng |

Kiểm thử cả decision và side effect: không được thực hiện action trước challenge, không tạo session/credential mới khi thất bại, và audit phải ghi đúng decision/reason code mà không lưu secret.

## 19. Tình huống phân tích

### Tình huống A: thiết bị quen thuộc nhưng giao dịch bất thường

An đăng nhập từ laptop đã dùng nhiều tháng. Session hợp lệ, nhưng An thêm người nhận mới và chuyển khoản giá trị cao khác hẳn lịch sử.

**Phân tích:** thiết bị quen thuộc chỉ là một signal. Action có tác động lớn và transaction mới có thể yêu cầu step-up phishing-resistant, transaction binding và kiểm tra giới hạn giao dịch.

### Tình huống B: IP thay đổi khi người dùng đi công tác

Người dùng đăng nhập từ mạng khách sạn ở quốc gia khác. Hệ thống chỉ dựa vào geolocation và khóa tài khoản.

**Phân tích:** vị trí ước lượng có thể sai do VPN, roaming hoặc NAT. Kết hợp nhiều tín hiệu, đánh giá action và cho phép challenge phù hợp; tránh dùng IP như bằng chứng duy nhất.

### Tình huống C: recovery vừa hoàn tất

Một user vừa khôi phục tài khoản bằng quy trình dự phòng, sau đó muốn thêm passkey và đổi email recovery ngay lập tức.

**Phân tích:** recovery gần đây làm tăng rủi ro chiếm quyền bền vững. Có thể yêu cầu xác minh bổ sung, delay/hold hoặc review; không để recovery yếu tự mở đường thêm authenticator.

### Tình huống D: push bombing

Attacker biết mật khẩu và gửi nhiều push approval. User mệt mỏi rồi chấp nhận một yêu cầu không do mình khởi tạo.

**Phân tích:** cần rate limit, number matching, hiển thị context, nút từ chối/báo cáo và phát hiện push fatigue. Push approval không có context rõ không nên là fallback cho thao tác giá trị cao.

### Tình huống E: risk engine gặp sự cố

Risk service timeout khi user thực hiện thao tác đọc hồ sơ và thao tác chuyển tiền.

**Phân tích:** policy fallback có thể khác theo action. Với thao tác ít nhạy cảm, có thể tiếp tục nếu session, baseline và authorization hợp lệ; với chuyển tiền, giữ thao tác hoặc yêu cầu challenge đã được phê duyệt. Không mặc định mọi request đều risk thấp khi service lỗi.

## 20. Quy trình thiết kế và vận hành

Trước khi phát hành adaptive challenge, hãy xác định:

1. Action/resource nào có baseline assurance bắt buộc?
2. Risk signals nào có nguồn, timestamp, confidence và TTL rõ?
3. Signal nào là bằng chứng mật mã, trạng thái server-side hay chỉ là risk context?
4. Hard constraints nào luôn DENY bất kể risk score?
5. Risk band/threshold được hiệu chỉnh bằng dữ liệu và kiểm thử nào?
6. Quyết định ALLOW/STEP_UP/RESTRICT/DENY có reason code và policy version không?
7. Challenge được chọn có đáp ứng baseline, phishing resistance và independence không?
8. Fallback có assurance tương đương hay tạo downgrade path?
9. Step-up grant có gắn principal/session/client/resource/action/transaction và expiry không?
10. Challenge có one-time consumption, replay defense và concurrency control không?
11. Risk service timeout/stale signal được xử lý thế nào cho từng action?
12. Có rate limit, cooldown, push fatigue protection và recovery abuse controls không?
13. Privacy, retention, fairness, false positive và appeal được đánh giá ra sao?
14. Có dashboard theo dõi challenge rate, completion, denial, false positive và account takeover không?
15. Có diễn tập session theft, recovery abuse, push bombing, risk service outage và transaction mutation không?

## 21. Ghi nhớ trọng tâm

- **Risk signal hỗ trợ quyết định, không chứng minh danh tính.** IP, User-Agent và fingerprint không thay thế proof mật mã.
- **Baseline assurance là yêu cầu bắt buộc.** Risk thấp không được hạ mức xác thực tối thiểu của action.
- **Adaptive challenge chọn cách phản ứng phù hợp.** ALLOW, STEP_UP, RESTRICT và DENY phải có semantics rõ ràng.
- **Chọn challenge theo assurance và khả năng chống phishing.** Không để fallback yếu hơn vô hiệu phương thức chính.
- **Step-up phải gắn đúng principal, session, client, resource, action và transaction.** Không dùng một cờ MFA chung cho mọi endpoint.
- **Giao dịch thay đổi thì challenge cũ hết hiệu lực.** Bind canonical digest/version từ dữ liệu server-side.
- **Risk engine có thể sai hoặc ngừng hoạt động.** Cần hard constraints, policy fallback và fail-open/closed theo mức nhạy cảm.
- **Rate limit và anti-fatigue bảo vệ cả hệ thống lẫn người dùng.** Challenge không được trở thành công cụ gây phiền hoặc khóa tài khoản.
- **Privacy và fairness là yêu cầu vận hành.** Giảm dữ liệu, theo dõi false positive và có đường review.
- **Authentication, risk assessment và authorization là ba lớp riêng.** Qua challenge vẫn phải kiểm tra quyền trên resource.

Adaptive challenge hiệu quả khi nó bổ sung đúng bằng chứng còn thiếu cho một hành động cụ thể. Kết hợp baseline assurance, risk signals có nguồn gốc, challenge chống phishing, context binding và authorization riêng sẽ giúp giảm lạm dụng mà vẫn giữ trải nghiệm hợp lý cho người dùng hợp lệ.
