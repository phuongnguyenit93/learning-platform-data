# Failed login metric — Đo lường và giám sát đăng nhập thất bại
 
> **Chương:** Monitoring và audit  
> **Chủ đề:** Failed login metric

**Failed login metric** là nhóm chỉ số đo số lượng, tỷ lệ, tần suất và phân bố các lần xác thực không thành công trong một khoảng thời gian. Các chỉ số này giúp đội vận hành nhận biết credential stuffing, password spraying, brute force, account enumeration, lỗi cấu hình identity provider, sự cố MFA và trải nghiệm đăng nhập đang suy giảm.

Một con số “đăng nhập thất bại” riêng lẻ không đủ để kết luận có tấn công. Người dùng có thể gõ sai password, quên đổi password sau khi reset, dùng thiết bị cũ, gặp lỗi đồng hồ TOTP hoặc bị gián đoạn mạng. Ngược lại, attacker có thể phân tán một lượng nhỏ request qua nhiều IP và nhiều account để tránh ngưỡng cảnh báo đơn giản. Vì vậy, metric cần định nghĩa event rõ ràng, phân biệt lỗi xác thực với lỗi hệ thống, phân tích theo nhiều chiều và kết hợp với baseline, context cùng các tín hiệu độc lập.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối authentication, password, MFA, passkey, token, session, account lockout, risk-based authentication và audit. Trọng tâm là xây dựng metric có thể hành động, phát hiện bất thường mà không tạo false alarm hoặc làm lộ dữ liệu cá nhân, và kiểm chứng rằng telemetry phản ánh đúng hoạt động xác thực.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Định nghĩa chính xác một failed login event và phân biệt nó với lỗi ứng dụng hoặc lỗi mạng.
2. Xây dựng count, rate, ratio và unique-principal metric theo cửa sổ thời gian.
3. Phân tích failed login theo principal, client, source network, tenant, authentication method và failure reason.
4. Phát hiện brute force, password spraying, credential stuffing và distributed low-and-slow attempts.
5. Thiết kế baseline, threshold, alert severity và suppression có kiểm soát.
6. Phân biệt hành vi người dùng hợp lệ với tín hiệu tấn công bằng context và correlation.
7. Bảo vệ identifier, IP, credential và dữ liệu MFA trong log/metric.
8. Xử lý cardinality, sampling, event loss, duplicate và clock skew trong telemetry phân tán.
9. Kết nối metric với incident response, rate limiting, MFA và account protection.
10. Xây dựng dashboard, test plan và production checklist cho failed login monitoring.

## 2. Failed login event là gì?

Failed login event là một sự kiện trong đó một authentication attempt không đạt kết quả xác thực theo policy. Trước khi đếm, hệ thống phải định nghĩa attempt bắt đầu và kết thúc ở đâu.

Ví dụ, người dùng gửi username/password và password verification không khớp. Một lần xác thực khác có thể thất bại ở MFA sau khi password đúng. Hai trường hợp đều liên quan đến đăng nhập, nhưng ý nghĩa bảo mật và cách xử lý khác nhau.

### 2.1. Phân biệt attempt, event và request

- **HTTP request:** một request tới endpoint login hoặc identity service.
- **Authentication attempt:** một giao dịch xác thực logic do người dùng/client khởi tạo.
- **Authentication event:** kết quả hoặc bước trong attempt, như password rejected, MFA challenge failed hoặc login succeeded.
- **Session creation:** sự kiện tạo session sau khi các điều kiện xác thực đã đạt.

Một attempt có thể sinh nhiều request/event do retry, redirect, MFA challenge hoặc mạng không ổn định. Nếu đếm mọi HTTP request như một lần đăng nhập, metric có thể phóng đại hoạt động và gây alert sai.

### 2.2. Định nghĩa failure

Một attempt được tính là failed login khi hệ thống xác định authentication không thành công theo outcome cuối cùng hoặc theo một failure stage đã định nghĩa.

Cần phân biệt:
- Password không khớp;
- Account không đủ điều kiện đăng nhập;
- MFA bị từ chối hoặc hết hạn;
- Passkey assertion không hợp lệ;
- Certificate không được tin cậy;
- Token/session không hợp lệ trong flow đăng nhập tương tác; refresh-token rejection nên có metric riêng;
- Authentication provider không khả dụng;
- Request bị rate limit hoặc challenge trước khi credential được kiểm tra. Đây là control/rejection event, không tự động được tính là credential failure.

Không gom tất cả vào một loại “wrong password”. Việc phân loại giúp biết failure đến từ attacker, người dùng, policy hay hạ tầng.

## 3. Vì sao phải đo failed login?

Failed login metric có nhiều mục tiêu khác nhau:

- Phát hiện hành vi đoán password hoặc thử credential bị lộ;
- Nhận biết password spraying trên nhiều account;
- Phát hiện account enumeration và credential stuffing;
- Theo dõi sự cố MFA, passkey, certificate hoặc IdP;
- Phân biệt tấn công với lỗi triển khai hoặc outage;
- Đánh giá tác động của thay đổi UX/authentication policy;
- Theo dõi hiệu quả rate limit, bot mitigation và step-up;
- Cung cấp bằng chứng điều tra và audit.

Metric là công cụ quan sát và ra quyết định. Nó không thay thế authentication control, authorization, rate limiting hoặc incident response.

## 4. Các metric nền tảng

Không nên dùng một chỉ số duy nhất. Một bộ metric cơ bản có thể gồm:

| Metric | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **Failed attempts** | Số attempt thất bại | Theo dõi volume |
| **Successful attempts** | Số attempt thành công | Làm mẫu số và so sánh |
| **Failure rate** | Tỷ lệ attempt thất bại | Theo dõi thay đổi chất lượng xác thực |
| **Unique failed principals** | Số principal khác nhau có failure | Nhận biết spraying/distributed activity |
| **Failures per principal** | Số failure trên một principal | Nhận biết brute force nhắm mục tiêu |
| **Failures per source** | Số failure theo IP/network/client | Nhận biết nguồn có hoạt động bất thường |
| **MFA failure rate** | Tỷ lệ MFA challenge thất bại | Theo dõi MFA abuse hoặc usability |
| **Provider error rate** | Tỷ lệ lỗi do IdP/auth service | Phân biệt outage với credential failure |
| **Lockout/throttle count** | Số lần bị throttling/lock policy | Đo tác động control và nguy cơ DoS |
| **Time to detect** | Thời gian từ hành vi đầu tiên đến alert | Đánh giá khả năng giám sát |

### 4.1. Failed attempt count

Trong cửa sổ thời gian W:

\[
F_W = \sum_{e \in W} \mathbf{1}(e.outcome = failed)
\]

Trong đó mỗi e phải là một authentication attempt đã được chuẩn hóa, không phải mọi request HTTP.

### 4.2. Failure rate

\[
FailureRate_W =
\frac{FailedAttempts_W}
{FailedAttempts_W + SuccessfulAttempts_W}
\]

Có thể biểu diễn dưới dạng phần trăm bằng cách nhân 100. Nếu mẫu số bằng 0, metric phải là no_data hoặc null, không tự đặt thành 0%.

Mẫu số nên chỉ gồm các authentication attempt đã có kết quả success hoặc failure. Provider outage, timeout, malformed request và request bị throttle trước khi xác minh credential cần được theo dõi bằng metric riêng để không làm sai failure rate của người dùng.

### 4.3. Failures per principal

\[
FailuresPerPrincipal(p,W) =
\sum_{e \in W,\ e.principal=p}
\mathbf{1}(e.outcome=failed)
\]

Metric này hữu ích để phát hiện nhiều lần thử vào cùng một account. Tuy nhiên, account chưa xác định hoặc identifier không tồn tại cũng cần được xử lý theo pseudonymous reference để đo enumeration mà không tiết lộ raw identifier.

### 4.4. Unique failed principals

\[
UniqueFailedPrincipals_W =
\left|\{p \mid \exists e \in W,\ e.principal=p,\ e.outcome=failed\}\right|
\]

Số principal khác nhau tăng nhanh có thể chỉ ra password spraying hoặc credential stuffing. Cần diễn giải cùng tổng volume, source diversity và tỷ lệ thành công.

## 5. Định nghĩa cửa sổ thời gian và đơn vị đếm

Metric chỉ có ý nghĩa khi cửa sổ và đơn vị đếm được định nghĩa nhất quán.

### 5.1. Cửa sổ thường dùng

- 1 phút: phát hiện burst hoặc bot tốc độ cao;
- 5 phút: phát hiện brute force ngắn hạn;
- 15 phút: phát hiện pattern theo source/account;
- 1 giờ: theo dõi spraying và xu hướng vận hành;
- 24 giờ: theo dõi baseline theo ngày;
- 7 ngày hoặc 30 ngày: xu hướng dài hạn, mùa vụ và thay đổi policy.

Không dùng một cửa sổ duy nhất cho mọi hành vi. Brute force có thể diễn ra nhanh, còn low-and-slow spraying có thể kéo dài nhiều giờ hoặc ngày.

### 5.2. Event time và ingest time

- event_time: thời điểm authentication attempt thực sự xảy ra;
- ingested_at: thời điểm telemetry pipeline nhận event.

Phân tích hành vi nên ưu tiên event time đã chuẩn hóa UTC. Ingest time giúp phát hiện trễ pipeline. Nếu chỉ dùng ingest time, queue delay hoặc batch delivery có thể tạo burst giả.

### 5.3. Deduplication

Một request có thể retry hoặc gửi lại do timeout. Dùng event_id hoặc attempt_id ổn định để deduplicate. Không loại bỏ hai attempt thực sự khác nhau chỉ vì chúng có cùng principal và timestamp gần nhau.

### 5.4. Attempt cuối cùng và stage event

Nếu password sai thì attempt kết thúc ngay. Nếu password đúng nhưng MFA sai, attempt cũng thất bại nhưng failure stage là MFA. Một attempt có nhiều MFA push notification không nên tự động bị tính thành nhiều login attempt; cần metric riêng cho challenge/push events.

## 6. Phân loại failure reason

Phân loại failure là điều kiện để metric hữu ích.

| Failure class | Ví dụ reason code | Ý nghĩa |
| --- | --- | --- |
| Credential rejected | INVALID_CREDENTIAL | Password hoặc secret không đúng |
| Unknown principal | PRINCIPAL_NOT_FOUND | Identifier không ánh xạ account |
| Account policy | ACCOUNT_DISABLED, ACCOUNT_LOCKED | Account không được phép đăng nhập |
| MFA rejected | MFA_DENIED, OTP_INVALID | Bằng chứng MFA không hợp lệ |
| MFA expired | MFA_EXPIRED | Challenge hết hạn |
| Passkey validation | WEBAUTHN_INVALID_ASSERTION | Assertion sai challenge/origin/signature |
| Certificate validation | CERT_REVOKED, CERT_UNTRUSTED | Certificate không được chấp nhận |
| Token validation | TOKEN_EXPIRED, TOKEN_AUDIENCE_INVALID | Token sai hoặc hết hạn trong flow |
| Risk policy | RISK_BLOCKED, STEP_UP_REQUIRED | Policy yêu cầu thêm bằng chứng hoặc chặn |
| Rate limit | THROTTLED | Request bị giới hạn |
| Provider/system | IDP_UNAVAILABLE, AUTH_BACKEND_ERROR | Lỗi hạ tầng, không phải credential sai |
| Client/protocol | MALFORMED_REQUEST, UNSUPPORTED_FLOW | Request hoặc giao thức không hợp lệ |

### 6.1. Tách credential failure và system failure

Nếu identity provider bị outage, failure rate có thể tăng mạnh dù không có attacker. Dashboard cần có system_error_rate hoặc provider availability riêng. Không tính timeout của database hoặc lỗi JWKS như password failure.

### 6.2. Tách unknown principal khỏi invalid credential

Hai reason code này hữu ích cho phân tích nội bộ, nhưng không nên hiển thị riêng ra public response nếu account enumeration là rủi ro. Metric pipeline có thể giữ classification đã kiểm soát trong vùng bảo mật.

### 6.3. Chuẩn hóa reason code

Các service cần dùng vocabulary chung. Không để một backend ghi BAD_PASSWORD, service khác ghi 401, và service thứ ba ghi free-text message không thể nhóm. Version hóa schema và duy trì mapping khi đổi implementation.

## 7. Dimensions để phân tích

Metric tổng thể giúp thấy volume, nhưng dimensions giúp tìm pattern.

| Dimension | Câu hỏi phân tích |
| --- | --- |
| Authentication method | Password, TOTP, passkey, certificate hay federation? |
| Failure stage | Password, MFA, token validation hay policy? |
| Principal reference | Một hay nhiều account đang bị nhắm tới? |
| Source network | Một IP/ASN hay nhiều nguồn? |
| Client application | Web, mobile, API client hay legacy app? |
| Tenant | Một tổ chức hay nhiều tổ chức? |
| Device/risk context | Thiết bị mới, managed hay suspicious? |
| Provider | Một IdP hoặc region có lỗi không? |
| Endpoint | Login, refresh, MFA challenge hay recovery? |
| Geography | Có thay đổi bất thường theo vùng ở mức ước lượng? |
| User agent family | Một automation pattern hay nhiều browser? |

Không phải dimension nào cũng nên làm metric label trực tiếp. Các giá trị có cardinality cao như user ID, email, IP hoặc raw user agent có thể làm hệ thống metrics quá tải và tăng rủi ro privacy. Dùng aggregation, top-N query, secured event store hoặc pseudonymous reference phù hợp.

## 8. Phân tích theo principal và source

### 8.1. Nhiều failure trên một principal

Có thể chỉ ra:
- Người dùng quên password;
- Password manager đang gửi credential cũ;
- Attacker brute force một account;
- Bot đang thử một danh sách password vào một account.

Cần xem thêm source diversity, device history, MFA outcome và lịch sử gần đây.

### 8.2. Nhiều principal từ một source

Có thể chỉ ra:
- Password spraying;
- Credential stuffing;
- Bot hoặc proxy;
- Shared NAT, văn phòng hoặc campus network;
- Một ứng dụng nội bộ bị lỗi cấu hình.

Không tự động block cả IP nếu nhiều người dùng hợp lệ chia sẻ NAT. Kết hợp ASN, network reputation, request pattern và client identity.

### 8.3. Một principal từ nhiều source

Có thể chỉ ra:
- Người dùng đổi Wi-Fi/mobile network;
- VPN hoặc corporate proxy;
- Attacker phân tán request;
- Session hoặc credential bị chia sẻ.

Phân tích theo thời gian, device context, authentication method và risk signals; không dùng IP như danh tính thiết bị.

### 8.4. Low-and-slow

Attacker có thể thử một password trên nhiều account với tần suất thấp để tránh threshold per-account. Metric cần đo cả unique principals, source distribution và pattern theo cửa sổ dài hơn.

## 9. Phát hiện các kiểu tấn công

| Pattern | Dấu hiệu metric | Tín hiệu bổ sung |
| --- | --- | --- |
| Brute force | Nhiều failure trên một principal trong thời gian ngắn | Một source/device, password attempts dày |
| Password spraying | Một hoặc vài password thử trên nhiều principal | Nhiều account, cùng source hoặc cùng pattern |
| Credential stuffing | Failure và success xen kẽ trên nhiều account | Nguồn automation, credential reuse patterns |
| Distributed guessing | Failure phân tán trên nhiều source | ASN/device/network diversity bất thường |
| Account enumeration | Nhiều identifier được thử, nhiều unknown principal | Response/timing probes |
| MFA fatigue | Nhiều challenge/push bị từ chối hoặc timeout | Một principal, repeated push requests |
| Legacy protocol abuse | Failure tăng trên endpoint cũ | Client/protocol không còn được hỗ trợ |
| Service misconfiguration | Failure đồng loạt từ một client/workload | Release/config change, provider error |

### 9.1. Không suy ra attack chỉ từ volume

Một trường học bắt đầu ngày học có thể tạo nhiều login cùng lúc. Một đợt password reset có thể làm tăng failure do password manager cũ. Metric phải được so sánh với baseline theo giờ/ngày, tenant, client và mùa vụ.

### 9.2. Failure xen kẽ success

Một chuỗi failure sau đó success không nhất thiết là compromise, nhưng có thể cho thấy attacker cuối cùng đoán đúng hoặc dùng credential bị lộ. Theo dõi success_after_failures, đặc biệt khi source/device mới hoặc hành vi sau login bất thường.

## 10. Baseline và threshold

### 10.1. Baseline theo ngữ cảnh

Baseline có thể được xây dựng theo:
- Giờ trong ngày và ngày trong tuần;
- Tenant và quy mô người dùng;
- Authentication method;
- Client application/version;
- Region/availability zone;
- Số lượng active users;
- Sự kiện sản phẩm như đầu kỳ học hoặc ngày payroll.

Không so sánh tenant có 100 người dùng với tenant có 100.000 người dùng bằng cùng một absolute threshold.

### 10.2. Absolute và relative threshold

Có thể kết hợp:
- Absolute count: tối thiểu N failure trong W phút;
- Rate: failure rate vượt ngưỡng;
- Deviation: tăng X lần so với baseline;
- Unique principal count: nhiều account khác nhau bị ảnh hưởng;
- Source concentration/diversity: nguồn tập trung hoặc phân tán;
- Success-after-failure: có đăng nhập thành công sau chuỗi thử.

Một alert tốt thường yêu cầu đủ volume tối thiểu để tránh noise và mức tăng bất thường so với baseline.

### 10.3. Không đặt threshold chỉ từ cảm tính

Dùng dữ liệu lịch sử, staging load test và incident simulation để chọn threshold. Theo dõi false positive/false negative và hiệu chỉnh theo từng authentication flow. Mọi thay đổi threshold nên có owner, lý do, version và audit.

### 10.4. Cold start

Tenant hoặc client mới có ít dữ liệu baseline. Dùng global baseline bảo thủ, absolute floor và policy theo risk; không coi “chưa có lịch sử” là “không có rủi ro”.

## 11. Alert severity và hành động

Metric cần gắn với hành động cụ thể.

| Mức | Ví dụ | Hành động |
| --- | --- | --- |
| Informational | Failure tăng nhẹ nhưng trong baseline | Dashboard, không cần page |
| Low | Một principal có nhiều failure | Throttle nhẹ, theo dõi |
| Medium | Một source thử nhiều principal | Risk challenge, rate limit, điều tra |
| High | Spraying/stuffing có volume và pattern rõ | Tăng bảo vệ, chặn nguồn có chọn lọc, thông báo security |
| Critical | Failure kèm success bất thường, compromise signal hoặc admin target | Incident response, revoke session/credential liên quan, step-up/deny |

Không nên tự động khóa toàn bộ account chỉ từ một metric tổng. Điều đó có thể tạo denial of service. Chọn hành động theo confidence, scope và tác động.

### 11.1. Alert suppression

Suppression giúp tránh alert lặp liên tục, nhưng không được che một pattern mới hoặc làm mất bằng chứng. Có thể gộp theo principal/source/tenant trong thời gian ngắn, nhưng vẫn giữ count và event references.

### 11.2. Escalation

Alert cần owner, severity, runbook, thời hạn phản hồi và tiêu chí đóng. Nếu alert không dẫn tới quyết định hoặc hành động, cần xem lại chất lượng metric.

## 12. Dashboard failed login

Một dashboard vận hành hữu ích nên trả lời:
- Volume đang tăng hay giảm?
- Tỷ lệ failure thay đổi ở đâu?
- Có bao nhiêu principal duy nhất bị ảnh hưởng?
- Failure tập trung ở password, MFA, passkey hay provider?
- Một source nhắm nhiều account hay nhiều source nhắm một account?
- Có success sau chuỗi failure không?
- Thay đổi bắt đầu sau deployment hoặc IdP config nào?
- Control đã throttle/challenge/block bao nhiêu request?

### 12.1. Bố cục gợi ý

| Panel | Nội dung |
| --- | --- |
| Overview | Failed/successful attempts và failure rate theo thời gian |
| Failure reason | Phân bố reason code/stage |
| Principal impact | Unique principals, top affected pseudonymous refs |
| Source analysis | Top network/source và source diversity |
| Authentication method | Password/MFA/passkey/certificate/SSO |
| Tenant/client | Tenant và client có spike |
| Provider health | IdP latency, timeout và error rate |
| Controls | Throttle, challenge, deny và lockout count |
| Correlation | Success after failures, suspicious session creation |

### 12.2. Không hiển thị PII rộng rãi

Dashboard chung nên dùng aggregate và pseudonymous references. Raw email, phone, IP hoặc user-agent chi tiết chỉ dành cho điều tra viên có quyền và mục đích hợp lệ.

## 13. Telemetry event schema

Một event chuẩn hóa có thể có cấu trúc:

~~~json
{
  "event_id": "evt_01JQ9F2A",
  "attempt_id": "att_01JQ9F29",
  "event_time": "2026-11-22T08:15:00Z",
  "ingested_at": "2026-11-22T08:15:01Z",
  "event_type": "authentication_attempt",
  "outcome": "failure",
  "failure_class": "credential_rejected",
  "failure_reason": "INVALID_CREDENTIAL",
  "principal_ref": "principal_hmac_7f3a",
  "tenant_ref": "tenant_42",
  "client_id": "web-portal",
  "auth_method": "password",
  "failure_stage": "primary_credential",
  "source_network_ref": "network_ref_19",
  "device_ref": "device_ref_88",
  "provider": "first_party",
  "risk_action": "none",
  "policy_version": "auth-policy-12"
}
~~~

Đây là schema minh họa, không phải yêu cầu bắt buộc. Chỉ đưa vào những field cần cho detection và audit. Không ghi password, OTP, recovery code, access token, refresh token, session cookie hoặc private key.

### 13.1. Event identity

event_id duy nhất cho telemetry event; attempt_id liên kết các stage thuộc cùng authentication attempt. Không dùng email hoặc raw username làm event ID.

### 13.2. Pseudonymous principal reference

Có thể tạo reference bằng keyed HMAC trên canonical identifier hoặc internal subject ID. HMAC key cần được bảo vệ và có kế hoạch rotation. Không dùng hash không khóa của email làm pseudonym vì attacker có thể dò dictionary. Giới hạn quyền truy cập mapping từ pseudonym về danh tính thật.

### 13.3. Schema version

Có schema_version hoặc contract version để consumer hiểu field semantics. Khi đổi failure reason hoặc event definition, cần cập nhật dashboard, alert và query cùng lúc.

## 14. Privacy và data minimization

Authentication telemetry có thể tiết lộ thói quen, thiết bị, vị trí gần đúng và danh tính người dùng. Thu thập quá nhiều làm tăng rủi ro khi log store hoặc analytics bị lộ.

### 14.1. Nguyên tắc

- Thu thập field tối thiểu đủ phát hiện và điều tra;
- Ưu tiên aggregate/pseudonymized reference;
- Không log bí mật xác thực;
- Giới hạn raw IP và identifier theo mục đích;
- Giới hạn retention và quyền truy cập;
- Tách dashboard vận hành khỏi dữ liệu điều tra chi tiết;
- Audit truy cập vào dữ liệu nhạy cảm;
- Xác định chính sách xóa và legal hold.

### 14.2. IP và geography

IP là dữ liệu nhạy cảm trong nhiều bối cảnh và có thể chỉ vị trí egress, không phải vị trí thật của người dùng. Nếu chỉ cần phát hiện pattern, có thể dùng network/ASN reference hoặc vùng tổng quát. Không suy ra GPS từ IP.

### 14.3. Không ghi credential

Tuyệt đối tránh ghi:
- Password hoặc password fragment;
- OTP/TOTP;
- Recovery code;
- Authorization header;
- Access/refresh token;
- Session cookie;
- Private key hoặc secret;
- WebAuthn challenge/response đầy đủ nếu có thể liên kết hoặc replay theo cách không cần thiết.

Nếu cần lưu metadata giao thức, chỉ lưu field đã giảm thiểu và không chứa material có thể dùng để xác thực.

## 15. Cardinality và thiết kế metrics backend

Prometheus-like metrics thường dùng label có tập giá trị giới hạn. Nếu thêm email, user ID hoặc IP trực tiếp làm label, cardinality có thể tăng rất lớn, làm tăng chi phí và khiến hệ thống metrics suy giảm.

### 15.1. Label phù hợp

Ví dụ:
- auth_method: password, totp, webauthn, certificate;
- failure_class: credential, mfa, token, provider, policy;
- client_type: web, mobile, api;
- environment: prod, staging;
- tenant_tier: standard, enterprise nếu số giá trị nhỏ;
- provider: một tập IdP đã định nghĩa.

### 15.2. Không dùng label cardinality cao

Tránh label:
- Email;
- Username;
- Raw IP;
- Session ID;
- Token ID;
- Arbitrary user-agent;
- Resource ID tự do.

Chi tiết theo principal/source nên nằm trong secured event store, log analytics hoặc query có giới hạn, không phải metric time series có label không giới hạn.

### 15.3. Top-N và sketch

Để phân tích unique principal hoặc source ở quy mô lớn, có thể dùng approximate distinct sketch (ví dụ HyperLogLog) hoặc query aggregation. Approximation cần được ghi rõ; không dùng kết quả gần đúng làm bằng chứng duy nhất cho hành động khóa account.

### 15.4. Sampling

Sampling có thể giảm chi phí event store, nhưng metric count chính xác cần được cập nhật trước hoặc độc lập với sampling. Không tính tổng failed login từ một tập log đã sample mà không hiệu chỉnh.

## 16. Distributed telemetry và chất lượng dữ liệu

Một hệ thống phân tán có thể gửi event từ gateway, identity service, MFA provider và backend. Cùng một attempt có thể được ghi ở nhiều nơi.

### 16.1. Tránh đếm trùng

Chọn một nguồn authoritative cho kết quả cuối của authentication attempt. Các event stage khác vẫn hữu ích để phân tích, nhưng phải liên kết bằng attempt_id và không cộng thành nhiều failed attempts.

### 16.2. Late/out-of-order events

Event có thể đến sai thứ tự do queue retry hoặc network delay. Sắp xếp theo event time và version/stage semantics; giữ ingest time để theo dõi pipeline lag.

### 16.3. Event loss

Theo dõi telemetry drop, queue lag, producer errors và consumer lag. Một dashboard failed login bằng 0 trong lúc pipeline hỏng không có nghĩa không có login failure.

### 16.4. Clock skew

Đồng hồ lệch có thể làm sai cửa sổ, burst và correlation. Dùng đồng bộ thời gian, lưu UTC và phát hiện timestamp bất thường. Không dùng timestamp client không đáng tin làm nguồn duy nhất.

### 16.5. Correlation across services

Dùng correlation ID/trace ID để nối gateway, IdP và backend. Trace ID phục vụ quan sát, không phải danh tính hoặc bằng chứng authorization. Không cho client kiểm soát correlation metadata để ghi đè audit identity.

## 17. Metric và account lockout/rate limiting

Failed login metric có thể kích hoạt control nhưng phải tránh lockout DoS.

### 17.1. Progressive controls

Có thể tăng dần:
- Rate limit theo account reference;
- Rate limit theo source/network/client;
- Progressive delay;
- CAPTCHA hoặc risk challenge;
- Yêu cầu step-up;
- Tạm từ chối một nguồn có confidence cao;
- Revoke session khi có bằng chứng compromise.

### 17.2. Tránh hard lock chỉ theo số lần sai

Attacker có thể gửi nhiều password sai để khóa account nạn nhân. Cần phân biệt:
- Throttle request;
- Challenge request;
- Tạm ngăn source;
- Account lock do policy;
- Account suspension do compromise.

Các hành động khác nhau có tác động và recovery khác nhau.

### 17.3. Control feedback

Ghi risk_action hoặc control outcome để biết metric đã kích hoạt điều gì. Theo dõi false positive, user friction, support tickets và tỷ lệ challenge thành công để điều chỉnh.

## 18. Kết hợp với các tín hiệu khác

Failed login là một tín hiệu, không phải verdict.

Có thể kết hợp:
- Login success sau nhiều failure;
- MFA push denied/approved bất thường;
- Device mới hoặc device posture thay đổi;
- Impossible travel hoặc network mới;
- Refresh token reuse;
- Password reset/recovery gần thời điểm login;
- API behavior bất thường sau login;
- Account đặc quyền hoặc thao tác nhạy cảm;
- Nhiều account có cùng pattern credential failure.

### 18.1. Không đếm trùng evidence

Một request bị rate limit có thể đồng thời tạo throttled, risk_blocked và login_failed event. Cần xác định metric nào đo attempt, metric nào đo control action và metric nào đo policy decision. Không cộng tất cả thành ba failed logins.

### 18.2. Risk score

Có thể tạo score từ volume, rate, unique principals, source diversity và corroborating signals. Score cần calibration và explainability. Không để một metric duy nhất tự động quyết định khóa account hoặc revoke tất cả session.

## 19. Pseudocode chuẩn hóa và cập nhật metric

~~~text
process_authentication_result(event):
    require valid_event_schema(event)
    require event.event_time_is_acceptable
    require event.event_id is unique

    normalized = normalize_auth_event(event)
    if duplicate(normalized.event_id):
        return DUPLICATE_IGNORED

    if normalized.type == AUTHENTICATION_STAGE:
        store_stage_event(normalized)
        update_attempt_state(normalized.attempt_id)
        return STAGE_RECORDED

    if normalized.type != AUTHENTICATION_ATTEMPT_FINAL:
        return NON_LOGIN_EVENT

    if normalized.outcome == FAILURE:
        increment_counter(
            auth_attempts_total,
            labels = bounded_labels(normalized)
        )
        increment_counter(
            auth_failures_total,
            labels = bounded_failure_labels(normalized)
        )
        update_window_aggregates(
            principal_ref = pseudonymize(normalized.principal),
            source_ref = normalize_network_ref(normalized.source),
            tenant_ref = normalized.tenant_ref,
            event_time = normalized.event_time
        )
    else if normalized.outcome == SUCCESS:
        increment_counter(auth_attempts_total, bounded_labels(normalized))
        increment_counter(auth_successes_total, bounded_labels(normalized))
        correlate_with_recent_failures(normalized)

    evaluate_alert_rules()
    return METRIC_UPDATED
~~~

Pseudocode mô tả logic. Triển khai cần transaction/idempotency, event-time windowing, bounded labels, late-event handling, queue retry, sampling semantics và bảo vệ pseudonymization key.

## 20. Ví dụ phân tích metric

Giả sử trong 5 phút một tenant có:
- 1.000 authentication attempts;
- 180 failures;
- 820 successes;
- 140 principal khác nhau có failure;
- 90% failure thuộc password stage;
- 70% failure đến từ một số network mới;
- Có 6 success sau chuỗi failure trên account chưa từng thấy thiết bị.

Ta tính:

\[
FailureRate = \frac{180}{1000} \times 100 = 18\%
\]

Một tỷ lệ 18% có thể cao so với baseline tenant đó, nhưng chưa đủ để kết luận compromise. Unique principals cao và network mới có thể phù hợp với spraying; success-after-failures cùng device mới làm tăng mức đáng chú ý. Cần xem client version, giờ hoạt động, thay đổi password policy, IdP health và liệu đây có phải sự kiện bắt đầu kỳ học.

### 20.1. Ví dụ khác: outage

Nếu 500 failures trong 5 phút chủ yếu có reason IDP_UNAVAILABLE, nhiều tenant và client cùng bị ảnh hưởng, provider latency tăng đồng thời và không có pattern theo principal/source, đây có thể là outage. Alert cần chuyển tới đội vận hành identity provider thay vì mặc định coi là brute force.

### 20.2. Ví dụ low-and-slow

Nếu 300 account khác nhau mỗi account có một failure trong 24 giờ, tổng volume không cao theo cửa sổ 1 phút. Metric unique principals theo cửa sổ dài và pattern source/device có thể phát hiện spraying mà burst threshold bỏ qua.

## 21. Kiểm thử failed login metric

Kiểm thử trong staging bằng account và credential giả lập. Không chạy password spray hoặc brute force trên hệ thống production.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Invalid password | Một attempt password sai | Tăng failed attempt đúng một lần |
| Unknown principal | Identifier không tồn tại | Được phân loại nội bộ, không lộ public response |
| MFA failure | Password đúng, MFA sai | Đếm failure stage MFA, không đếm trùng attempt |
| MFA push | Nhiều push trong một attempt | Challenge event riêng, không nhân số login attempt |
| Passkey failure | Assertion sai challenge/origin | Ghi failure class WebAuthn |
| Certificate failure | Cert hết hạn/revoked | Phân biệt certificate/policy failure |
| Provider outage | IdP timeout | Tăng provider error metric, không gán wrong password |
| Duplicate event | Cùng event_id gửi hai lần | Chỉ đếm một lần |
| Multiple stages | Một attempt có nhiều stage event | Chỉ một final attempt count |
| Retry | Client retry do timeout | Dedup theo attempt/event contract |
| Brute force pattern | Nhiều failure một principal | Alert theo per-principal window |
| Password spraying | Một source thử nhiều principal | Alert theo unique principal/source |
| Distributed low-and-slow | Ít failure mỗi account, nhiều account | Phát hiện qua long window/unique principal |
| Success after failures | Login success sau chuỗi failure | Correlate và nâng risk theo context |
| Shared NAT | Nhiều user hợp lệ chung source | Không block toàn source chỉ từ volume |
| Account lockout DoS | Attacker tạo failure cho victim | Control không dễ khóa account nạn nhân |
| Clock skew | Event timestamp lệch | Phát hiện/đánh dấu quality; không tạo burst giả |
| Late event | Event đến trễ | Cập nhật đúng event-time window |
| Event loss | Queue/consumer drop event | Telemetry health cảnh báo metric không đầy đủ |
| Cardinality | Identifier/IP đa dạng rất lớn | Metrics labels vẫn bounded |
| Privacy | Dashboard tổng hợp | Không lộ raw email/phone/token |
| Retention | Event hết thời hạn | Purge/pseudonymization theo policy |
| Threshold change | Baseline hoặc threshold cập nhật | Version và audit được ghi |
| Sampling | Event detail bị sample | Counter chính xác vẫn được giữ |
| Tenant imbalance | Tenant lớn và nhỏ | Threshold/baseline theo quy mô phù hợp |

### 21.1. Bất biến bảo mật và dữ liệu

- Một authentication attempt cuối cùng chỉ được tính một lần;
- Provider/system failure không bị phân loại thành invalid password;
- MFA stage event không làm phóng đại login attempt;
- Metric không chứa raw credential hoặc token;
- High-cardinality identifier không trở thành label time series;
- Pipeline drop/lag được quan sát độc lập;
- Metric zero không được hiểu là no failures khi telemetry unhealthy;
- Alert không tự động khóa account chỉ từ volume;
- Event và metric có schema, time window và reason semantics được version hóa.

## 22. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đếm mọi HTTP 401 là failed login | API authorization failure bị tính nhầm | Dùng authentication event semantics |
| Đếm mọi retry thành attempt mới | Volume bị phóng đại | Attempt ID và deduplication |
| Gộp provider outage với wrong password | Alert tấn công giả | Failure class riêng |
| Chỉ đo tổng volume | Bỏ sót spraying/distributed pattern | Principal/source/tenant dimensions |
| Chỉ dùng per-IP threshold | Bỏ sót distributed attack và block nhầm NAT | Multi-dimensional detection |
| Chỉ dùng per-account lockout | Attacker gây DoS | Progressive controls và risk-based policy |
| Label metric chứa email/IP | Cardinality và privacy risk | Bounded labels, pseudonymous event store |
| Tính rate khi denominator bằng 0 | NaN hoặc số liệu sai | No-data/null semantics |
| Bỏ qua event time | Queue delay tạo burst giả | UTC event-time windowing |
| Không theo dõi telemetry lag | Metric 0 giả khi pipeline hỏng | Pipeline health metrics |
| Alert threshold cố định | False positive theo mùa vụ/tenant | Baseline và threshold theo context |
| Không phân biệt MFA challenge | Đếm một login thành nhiều failures | Attempt/stage model |
| Dùng raw logs để tính counter sau sampling | Mất count | Counter độc lập với sampling |
| Không audit threshold changes | Khó giải thích alert drift | Version, owner và change audit |

## 23. Checklist production

1. **Event definition:** Failed login được định nghĩa ở attempt level hay request level?
2. **Outcome:** Có phân biệt success, failure, challenge, throttle và provider error?
3. **Stage:** Password, MFA, passkey, certificate và federation có reason code riêng?
4. **Deduplication:** Retry, duplicate và multi-stage event có được liên kết đúng?
5. **Time:** Event time UTC, ingest lag, clock skew và late event được xử lý?
6. **Metrics:** Có count, rate, unique principal, per-principal/source và success-after-failures?
7. **Dimensions:** Method, stage, tenant, client, provider và network được phân tích?
8. **Baseline:** Threshold phản ánh quy mô, mùa vụ và giờ hoạt động?
9. **Detection:** Có rule cho brute force, spraying, stuffing, low-and-slow và MFA fatigue?
10. **False positive:** Shared NAT, mobile network, password reset và client lỗi được xét?
11. **Controls:** Rate limit, challenge, step-up và revoke có severity/owner rõ?
12. **DoS resistance:** Failed login metric không dễ bị dùng để khóa account nạn nhân?
13. **Privacy:** Identifier được pseudonymize; raw IP/PII có access/retention?
14. **Cardinality:** Metrics labels có bounded vocabulary?
15. **Pipeline:** Queue lag, dropped event, sampling và consumer health có metric riêng?
16. **Dashboard:** Có panel về volume, reason, principal, source, provider và control outcome?
17. **Audit:** Alert, threshold, policy version và hành động được ghi?
18. **Testing:** Đã test duplicate, outage, spraying, NAT, late event và telemetry loss?

## 24. Bài tập tình huống

Một nền tảng học tập có 20.000 người dùng. Sau khi cập nhật login service, dashboard ghi nhận failed login tăng gấp bốn lần trong 15 phút. Metric hiện tại chỉ đếm HTTP 401 từ gateway. Một số request là password sai, một số là MFA challenge hết hạn, một số do IdP timeout. Client mobile có retry khi mạng yếu. Cùng lúc đó, một nhóm account quản trị có login success sau nhiều failure từ thiết bị mới.

**Yêu cầu:**

1. Chỉ ra ít nhất **tám nguyên nhân** khiến metric hiện tại sai lệch hoặc chưa đủ để kết luận.
2. Thiết kế schema attempt/stage/final outcome và reason code.
3. Định nghĩa failed count, failure rate, unique principals và per-source metric.
4. Đề xuất cách deduplicate mobile retry và multi-stage MFA.
5. Thiết kế dashboard phân biệt provider outage với credential attack.
6. Xây dựng alert cho brute force, spraying và success-after-failures.
7. Đề xuất rate limit/challenge mà không gây lockout DoS.
8. Xác định dữ liệu cần giữ cho điều tra và dữ liệu phải tránh ghi.

**Gợi ý đối chiếu:** Không dùng HTTP 401 làm định nghĩa duy nhất; chuẩn hóa authentication attempt; phân biệt provider failure, password failure và MFA stage; dùng event ID/attempt ID; theo dõi unique principal/source và baseline; điều tra admin success trên device mới; không khóa account chỉ từ volume.

## 25. Ghi nhớ

- **Failed login metric** đo authentication attempt thất bại theo một định nghĩa thống nhất; không phải mọi HTTP error đều là login failure.
- Cần đo count, rate, unique principal, per-principal/source, MFA failure và provider error riêng.
- Phân biệt password rejection, unknown principal, MFA failure, policy block và system outage.
- Dùng attempt ID, event ID, event time UTC và deduplication để tránh đếm trùng.
- Phân tích theo principal, source, tenant, client, method và failure stage để nhận ra brute force, spraying và low-and-slow.
- Baseline và threshold cần theo quy mô, mùa vụ và authentication context; volume đơn lẻ không chứng minh attack.
- Không để metric tự động gây account lockout dễ bị lạm dụng DoS; chọn throttle/challenge/step-up theo confidence.
- Bảo vệ privacy bằng data minimization, pseudonymous reference, bounded metric labels và retention.
- Theo dõi telemetry health để metric bằng 0 không bị nhầm là không có failure.
- Alert cần owner, runbook, severity và feedback để giảm false positive.

Failed login monitoring có giá trị khi **mỗi con số phản ánh đúng một authentication attempt, mỗi failure có nguyên nhân đủ rõ để hành động và dữ liệu quan sát được bảo vệ đúng mức**. Kết hợp metric với baseline, context, pipeline health và các tín hiệu xác thực khác giúp phát hiện tấn công mà không biến lỗi đăng nhập thông thường thành sự cố giả.
