# Alert authentication — Thiết kế cảnh báo bảo mật cho hoạt động xác thực
 
> **Chương:** Monitoring và audit  
> **Chủ đề:** Alert authentication

**Alert authentication** là cảnh báo được tạo khi một hoặc nhiều tín hiệu xác thực cho thấy có nguy cơ bảo mật, vi phạm policy hoặc sự cố vận hành cần người có trách nhiệm đánh giá. Alert có thể xuất phát từ login thất bại bất thường, password spraying, MFA fatigue, token replay, refresh-token reuse, session ở thiết bị lạ, thay đổi recovery factor, enrollment passkey đáng ngờ hoặc lỗi diện rộng của identity provider.

Một alert không đồng nghĩa với một incident đã được xác nhận. Nó là thông tin có cấu trúc để người trực hiểu điều gì đã xảy ra, vì sao đáng chú ý, phạm vi ảnh hưởng, mức độ tin cậy và hành động tiếp theo. Alert tốt giúp phát hiện sớm và phản ứng nhất quán; alert kém tạo nhiễu, gây alert fatigue, làm lỡ tín hiệu quan trọng hoặc kích hoạt biện pháp tự động gây khóa nhầm người dùng.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối authentication, password, MFA, passkey, token, session, account recovery, risk-based authentication và audit. Trọng tâm là thiết kế alert từ telemetry đáng tin cậy, kết hợp nhiều tín hiệu, phân loại severity, deduplicate và route đúng người, hỗ trợ điều tra mà vẫn bảo vệ dữ liệu cá nhân.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt authentication alert, metric, event, finding và confirmed incident.
2. Xác định nguồn telemetry và điều kiện chất lượng dữ liệu trước khi tạo alert.
3. Thiết kế rule cho brute force, spraying, credential stuffing, MFA fatigue, token/session anomaly và account recovery abuse.
4. Kết hợp baseline, risk signal, context và correlation để giảm false positive.
5. Xây dựng severity, confidence, priority, deduplication, grouping và suppression.
6. Thiết kế alert payload có đủ thông tin điều tra mà không chứa secret hoặc PII không cần thiết.
7. Tạo routing, escalation, runbook và workflow acknowledgement/closure.
8. Phân biệt sự cố authentication của người dùng với outage hoặc misconfiguration của IdP.
9. Đánh giá khả năng phát hiện bằng precision, recall, MTTD, MTTA, MTTR và alert fatigue.
10. Kiểm thử rule, notification, automation và failure mode trước khi đưa vào production.

## 2. Alert, event, metric và incident

Các khái niệm liên quan nhưng có vai trò khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Event** | Sự kiện đã xảy ra trong hệ thống | Password rejected, MFA denied |
| **Metric** | Số đo tổng hợp từ event trong cửa sổ thời gian | 120 failed attempts trong 5 phút |
| **Detection rule** | Logic đánh giá event/metric/context | Nhiều account bị thử từ một source |
| **Alert** | Thông báo có cấu trúc khi rule thỏa điều kiện | Suspected password spraying |
| **Finding** | Kết quả điều tra hoặc phân tích có bằng chứng | 18 account bị thử, 2 login success |
| **Incident** | Sự kiện bảo mật được xác nhận cần phối hợp xử lý | Account admin bị chiếm |
| **Case/ticket** | Hồ sơ theo dõi công việc và quyết định | Case điều tra IDP-2026-041 |

Một event đơn lẻ có thể không đáng cảnh báo. Nhiều event kết hợp với metric, baseline và identity context có thể tạo alert. Người phân tích xác minh alert và có thể kết luận benign activity, false positive, policy violation hoặc incident.

### 2.1. Alert không phải verdict

Rule phát hiện một pattern đáng ngờ, không chứng minh ý định attacker. Ví dụ, 20 lần đăng nhập thất bại có thể là brute force, password manager lỗi hoặc một đợt người dùng vừa đổi password. Alert cần cung cấp bằng chứng và context để người trực đánh giá.

### 2.2. Alert không thay thế control

Alert cho biết hành vi đáng chú ý. Rate limit, MFA, session revocation, account suspension và authorization policy là các control thực thi. Có thể kết hợp alert với automated response, nhưng hành động phải có confidence, phạm vi và rollback phù hợp.

## 3. Mô hình pipeline cảnh báo xác thực

Một pipeline điển hình thu thập event từ nhiều thành phần, chuẩn hóa, phát hiện, làm giàu context rồi route alert.

~~~mermaid
flowchart LR
    A["Login / MFA / Passkey"] --> E["Authentication events"]
    B["IdP / Token / Session"] --> E
    C["Recovery / Credential lifecycle"] --> E
    D["Gateway / Backend"] --> E
    E --> N["Normalize + validate"]
    N --> S["Stream / event store"]
    S --> R["Detection rules + correlation"]
    R --> X["Enrich identity / tenant / risk"]
    X --> Q["Deduplicate + severity"]
    Q --> T["Alert manager"]
    T --> O["On-call / SOC / IAM team"]
    O --> I["Triage + incident response"]
~~~

### 3.1. Nguồn event

- Identity provider và authentication service;
- Login endpoint và gateway;
- MFA provider, push service và TOTP verifier;
- WebAuthn/passkey registration và assertion verifier;
- Token issuance, refresh, introspection và revocation;
- Session creation, renewal, logout và revocation;
- Password reset, account recovery và factor lifecycle;
- Certificate authority, mTLS và workload identity;
- Risk engine, rate limiter và bot protection;
- Audit trail của quản trị viên và helpdesk.

### 3.2. Nguồn authoritative

Với mỗi loại event, xác định hệ thống có thẩm quyền ghi kết quả cuối. Gateway và IdP có thể cùng ghi một login attempt; nếu cộng cả hai như hai attempt, metric và alert sẽ sai. Dùng attempt ID/correlation ID để liên kết stage, đồng thời chọn một nguồn authoritative cho final outcome.

### 3.3. Telemetry health

Pipeline cần có metric riêng cho event loss, queue lag, producer failure, consumer lag, schema rejection và clock skew. Khi telemetry không đầy đủ, dashboard không được hiển thị “không có tấn công” chỉ vì không nhận được event.

## 4. Định nghĩa alert rule

Một detection rule thường gồm:

- **Input:** event type hoặc metric cần quan sát;
- **Scope:** principal, tenant, client, source, method hoặc environment;
- **Window:** khoảng thời gian;
- **Condition:** ngưỡng, tỷ lệ hoặc pattern;
- **Context:** baseline, risk signal và trạng thái account;
- **Severity/confidence:** mức độ và độ tin cậy;
- **Grouping key:** cách gom các event thành alert;
- **Action:** route, notify, throttle hoặc yêu cầu điều tra;
- **Lifecycle:** mở, cập nhật, acknowledge, resolve và close.

Rule phải được viết sao cho người vận hành có thể giải thích tại sao alert xuất hiện. Tránh điều kiện mơ hồ như “nhiều login lỗi” nếu không định nghĩa cửa sổ, scope và nguồn dữ liệu.

### 4.1. Count-based rule

Ví dụ: ít nhất N failed attempts trên cùng một principal trong W phút. Rule này phù hợp với brute force tập trung, nhưng cần xét account size, shared device và password manager.

### 4.2. Rate-based rule

Ví dụ: failure rate vượt baseline của client hoặc tenant với một số attempt tối thiểu. Chỉ dùng tỷ lệ mà không có absolute floor có thể tạo alert khi chỉ có một request thất bại.

### 4.3. Cardinality/pattern rule

Ví dụ: một source thử nhiều principal trong 10 phút hoặc nhiều source cùng nhắm một principal. Đây là cách phát hiện spraying và distributed guessing.

### 4.4. Sequence/correlation rule

Ví dụ: nhiều login failure, tiếp theo là success từ device mới, rồi tạo refresh token hoặc thêm authenticator. Chuỗi sự kiện có mức rủi ro cao hơn một event riêng lẻ.

## 5. Các nhóm authentication alert phổ biến

| Nhóm alert | Tín hiệu điển hình | Rủi ro cần đánh giá |
| --- | --- | --- |
| Brute force | Nhiều failure trên một principal | Đoán password/credential |
| Password spraying | Một source thử nhiều principal | Né lockout theo account |
| Credential stuffing | Failure và success trên nhiều account | Credential bị lộ từ dịch vụ khác |
| Account enumeration | Nhiều identifier và response probing | Thu thập danh sách account |
| MFA fatigue | Nhiều push bị từ chối hoặc timeout | Ép người dùng approve |
| MFA bypass | Login success không có factor theo policy | Lỗi flow hoặc compromise |
| Passkey anomaly | Enrollment/revocation bất thường | Thêm credential của attacker |
| Token anomaly | Refresh reuse, wrong audience hoặc token replay | Token theft hoặc client lỗi |
| Session anomaly | Session mới từ context rủi ro | Session hijack hoặc account takeover |
| Recovery abuse | Nhiều recovery request hoặc helpdesk override | Chiếm account qua recovery |
| Privileged authentication | Admin login hoặc step-up bất thường | Tác động lớn tới hệ thống |
| Certificate/workload | Cert lạ, hết hạn hoặc identity mismatch | Workload impersonation |
| IdP/provider health | Timeout, latency hoặc error spike | Outage/misconfiguration |

Không phải tất cả đều là tấn công. Ví dụ certificate hết hạn có thể là lỗi vận hành; alert cần route tới IAM/platform team thay vì tự động xử lý như credential compromise.

## 6. Alert brute force và password spraying

### 6.1. Brute force

Rule có thể xem số failure trên một principal trong cửa sổ ngắn, số source/device, loại credential và kết quả thành công sau chuỗi thử. Không dùng số lần sai đơn lẻ để tự động khóa account vì attacker có thể cố tình gây DoS.

### 6.2. Password spraying

Spraying thường có ít lần thử trên mỗi account nhưng nhiều account khác nhau. Theo dõi:
- Unique principal refs theo source và time window;
- Failure count trên mỗi principal;
- Source/ASN/device diversity;
- Tỷ lệ account chưa từng thấy;
- Success sau chuỗi failure;
- Các pattern lặp theo nhiều tenant.

### 6.3. Distributed spraying

Attacker có thể phân tán request qua proxy hoặc botnet. Rule chỉ nhóm theo IP sẽ bỏ sót. Kết hợp client fingerprint có giới hạn, network/ASN, principal pattern, thời gian và risk context. Không dùng fingerprint như định danh chắc chắn hoặc thu thập quá mức.

## 7. Alert credential stuffing và account enumeration

### 7.1. Credential stuffing

Tín hiệu có thể gồm nhiều principal, nhiều failure xen kẽ success, client automation, network reputation thấp và các lần đăng nhập từ thiết bị mới. Một login thành công sau nhiều failure cần được correlation với hành vi sau login, chẳng hạn thêm MFA factor, tạo API key hoặc thay email.

### 7.2. Account enumeration

Nhiều identifier được thử qua login/reset/registration có thể là enumeration. Theo dõi số principal reference duy nhất, tỷ lệ unknown principal, endpoint distribution và response pattern. Không lưu raw email trong alert payload nếu pseudonymous reference đủ cho triage ban đầu.

### 7.3. Success sau failure

Success-after-failure là tín hiệu cần context, không phải bằng chứng compromise. So sánh device, network, geo estimate, MFA result, session age và hành động sau đăng nhập. Với account đặc quyền, có thể tăng severity hoặc yêu cầu step-up theo policy.

## 8. Alert MFA fatigue và authenticator abuse

MFA fatigue có thể biểu hiện qua nhiều push request bị từ chối, bỏ qua hoặc hết hạn. Attacker có thể lặp prompt để làm người dùng mệt mỏi và approve nhầm.

### 8.1. Tín hiệu

- Nhiều challenge trong thời gian ngắn cho một principal;
- Nhiều push denied/timeout;
- Push approval sau chuỗi denied;
- Login từ source/device mới;
- Challenge không tương ứng với login attempt đã được khởi tạo;
- Nhiều account cùng nhận push bất thường.

### 8.2. Hành động

- Throttle challenge generation;
- Dùng number matching và hiển thị context nếu nền tảng hỗ trợ;
- Tạm dừng push cho account bị nhắm tới theo policy;
- Gửi thông báo qua kênh đã xác minh;
- Yêu cầu phishing-resistant step-up;
- Thu hồi session nếu có dấu hiệu compromise.

Không tự động coi mọi push timeout là tấn công. Mobile notification có thể bị trì hoãn hoặc thiết bị offline.

## 9. Alert passkey, certificate và credential lifecycle

### 9.1. Passkey enrollment

Alert khi:
- Một account thêm nhiều passkey trong thời gian ngắn;
- Passkey được thêm sau recovery hoặc login rủi ro;
- Thay đổi authenticator trên account admin;
- Credential mới được đăng ký từ thiết bị chưa từng thấy;
- Một credential bị gỡ ngay sau khi thêm credential khác.

Context cần có actor, subject, session, authentication assurance, credential reference và approval.

### 9.2. Certificate/workload identity

Alert khi certificate mới được cấp cho workload nhạy cảm, SAN/SPIFFE ID không khớp inventory, certificate bị revoke nhưng vẫn được dùng, hoặc rotation thất bại. Phân biệt cert expiry/misconfiguration với private key compromise.

### 9.3. Password/recovery changes

Chuỗi password reset, email/phone change, recovery factor removal và session revocation trong thời gian ngắn có thể chỉ ra account takeover. Correlate actor, source, step-up result và thông báo người dùng.

## 10. Token và session anomaly alert

Các alert có thể theo dõi:
- Refresh token reuse sau rotation;
- Token audience hoặc issuer không hợp lệ;
- Token được sử dụng từ context bất thường;
- Nhiều session mới cho principal đặc quyền;
- Session tiếp tục hoạt động sau revoke;
- Logout/revocation không lan tới resource server;
- Access token được dùng sau khi membership bị thu hồi;
- Sender-constrained token proof không hợp lệ.

Không gửi token hoặc cookie vào alert. Dùng token family ID, session reference hoặc keyed pseudonym. Token invalid do client clock skew hoặc cấu hình audience sai có thể là lỗi vận hành; route theo failure class và phạm vi.

## 11. Baseline, threshold và risk context

### 11.1. Baseline theo nhóm

Baseline nên được phân nhóm theo:
- Authentication method;
- Tenant size/tier;
- Client application và version;
- Giờ trong ngày/ngày trong tuần;
- User population và mùa vụ;
- Account privilege level;
- Provider/region;
- Loại endpoint và flow.

Không áp một ngưỡng absolute cho tenant nhỏ và tenant lớn. Cần kết hợp absolute floor với relative deviation.

### 11.2. Threshold kết hợp

Một rule có thể yêu cầu đồng thời:
- Số attempt tối thiểu;
- Failure rate vượt baseline;
- Unique principals hoặc source diversity;
- Một risk signal bổ sung;
- Không phải provider outage diện rộng.

Kết hợp điều kiện giúp giảm false positive nhưng không nên tạo rule quá phức tạp, không thể giải thích hoặc khó kiểm thử.

### 11.3. Cold start và thay đổi hành vi

Tenant mới, client mới hoặc thay đổi policy có ít baseline. Dùng threshold bảo thủ, canary rollout và review sau thay đổi. Không coi dữ liệu thiếu là tín hiệu bình thường.

### 11.4. Confidence

Confidence phản ánh độ tin cậy của detection evidence, không đồng nghĩa severity. Ví dụ một event có tác động rất lớn nhưng confidence thấp vẫn cần triage ưu tiên, trong khi một pattern chắc chắn nhưng ít tác động có thể severity thấp hơn.

## 12. Severity, priority và confidence

Ba thuộc tính này nên tách biệt:

- **Severity:** mức tác động tiềm tàng nếu hành vi là thật;
- **Confidence:** mức tin cậy rằng rule phát hiện đúng pattern;
- **Priority:** thứ tự cần xử lý dựa trên severity, confidence, exposure và thời gian.

| Mức severity | Ví dụ | Response gợi ý |
| --- | --- | --- |
| Critical | Admin compromise có bằng chứng, token/session đang bị sử dụng trái phép | Kích hoạt incident response ngay |
| High | Spraying có success trên account nhạy cảm hoặc recovery abuse rõ | On-call security/IAM triage khẩn |
| Medium | MFA fatigue, nhiều account bị nhắm hoặc token reuse đáng ngờ | Điều tra nhanh, áp dụng control có chọn lọc |
| Low | Một principal có failure tăng nhẹ nhưng chưa có corroborating signal | Dashboard/queue theo dõi |
| Informational | Authenticator enrollment hợp lệ hoặc cert sắp hết hạn | Ghi nhận và vận hành |

Không có ngưỡng severity phổ quát. Tổ chức cần định nghĩa SLA, owner và escalation theo mức độ quan trọng của account/dữ liệu.

## 13. Correlation và entity context

Một alert mạnh thường cần kết hợp nhiều event liên quan. Entity có thể gồm:
- Principal/user;
- Tenant/organization;
- Client application;
- Device reference;
- Source network/ASN;
- Session/token family;
- Authenticator/credential reference;
- Workload/service identity;
- Resource hoặc action nhạy cảm.

### 13.1. Correlation window

Chuỗi login failure, success, factor enrollment và data export có thể diễn ra trong vài phút hoặc vài giờ. Chọn cửa sổ phù hợp với attack scenario; không gom các event không liên quan chỉ vì cùng email hoặc IP.

### 13.2. Entity resolution

Một user có thể có nhiều email, device hoặc session. Dùng internal subject ID và pseudonymous reference được quản lý. Không suy luận hai người là cùng một principal chỉ vì dùng chung IP hoặc thiết bị.

### 13.3. Attack story

Alert nên mô tả chuỗi sự kiện theo timeline, ví dụ: 15 login failures từ network mới, một success với MFA, thêm passkey mới sau 2 phút, rồi tạo refresh-token family. Timeline giúp analyst đánh giá nhanh và biết cần kiểm tra gì tiếp.

## 14. Deduplication, grouping và suppression

Nếu một rule phát alert mỗi phút cho cùng một principal, on-call có thể nhận hàng trăm notification cho một sự kiện.

### 14.1. Deduplication key

Một grouping key có thể gồm:
- Rule ID/version;
- Principal reference hoặc tenant;
- Attack pattern;
- Source/network group;
- Time bucket hoặc incident correlation ID.

Không đưa raw email, token hay session cookie vào grouping key.

### 14.2. Grouping

Gom nhiều event tương đồng vào một alert và cập nhật count, first_seen, last_seen, affected_principals và evidence references. Không gộp các tenant hoặc principal khác nhau nếu việc đó làm mất phạm vi ảnh hưởng.

### 14.3. Suppression

Suppression giảm notification lặp, nhưng event vẫn phải được lưu và count cập nhật. Có thể suppression theo rule/entity trong thời gian ngắn; alert mới có severity cao hơn hoặc pattern khác phải vượt suppression.

### 14.4. Maintenance window

Maintenance window có thể giảm alert do rollout hoặc test đã được phê duyệt. Cần scope, owner, start/end time và audit. Không tắt toàn bộ authentication monitoring chỉ vì có bảo trì IdP.

## 15. Alert payload và privacy

Alert cần đủ thông tin để triage mà không trở thành nơi lưu credential hoặc dữ liệu cá nhân quá mức.

### 15.1. Trường khuyến nghị

- Alert ID và rule ID/version;
- First seen, last seen và detection time;
- Severity, confidence và priority;
- Event type/failure class;
- Principal/tenant/device/source pseudonymous reference;
- Count, rate, window và baseline deviation;
- Authentication method và failure stage;
- Success-after-failure hoặc correlated action;
- Affected service/provider;
- Evidence references tới event store có kiểm soát;
- Runbook link/reference và owner team.

### 15.2. Không đưa vào alert

- Password, OTP, recovery code;
- Access token, refresh token hoặc cookie;
- Private key hoặc client secret;
- Full WebAuthn assertion nếu không cần;
- Raw email/phone/IP nếu pseudonymous reference đủ;
- Nội dung message hoặc profile cá nhân không liên quan.

### 15.3. Điều tra có kiểm soát

Nếu analyst cần danh tính thật hoặc raw source data, họ truy cập secured event store qua quyền phù hợp, có purpose và audit. Alert notification trên chat/email chỉ nên chứa metadata tối thiểu.

## 16. Routing, acknowledgement và escalation

Alert phải đến đúng người có thể xử lý.

### 16.1. Routing theo loại

- Identity provider outage → IAM/platform operations;
- Credential stuffing hoặc account takeover → Security operations;
- Passkey/certificate enrollment anomaly → IAM/security engineering;
- Tenant-specific access issue → tenant owner/support theo quyền;
- Telemetry pipeline failure → observability/data platform;
- Privileged account alert → on-call security hoặc incident commander theo policy.

### 16.2. Acknowledgement

Acknowledgement cho biết một người đã nhận trách nhiệm xử lý, không có nghĩa alert đã được xác minh hoặc giải quyết. Hệ thống cần ghi actor, timestamp và owner.

### 16.3. Escalation

Nếu alert không được acknowledge trong SLA, route tới backup/on-call lead. Nếu severity tăng hoặc xuất hiện bằng chứng compromise mới, escalation phải cập nhật dù alert ban đầu đã được acknowledge.

### 16.4. Notification channel

Email, chat, pager hoặc ticket đều có thể được dùng. Kênh có thể không phù hợp để gửi PII hoặc evidence nhạy cảm. Dùng link tới console có authentication, authorization và audit.

## 17. Alert lifecycle

Một lifecycle có thể được mô hình hóa như sau:

~~~mermaid
stateDiagram-v2
    [*] --> New: Rule fired
    New --> Grouped: Deduplicate
    Grouped --> Assigned: Route to owner
    Assigned --> Acknowledged: Analyst accepts
    Acknowledged --> Investigating: Triage
    Investigating --> Escalated: Higher risk / SLA
    Investigating --> Resolved: Benign or control applied
    Escalated --> Investigating: Incident team takes over
    Resolved --> Closed: Evidence and disposition recorded
    Closed --> [*]
~~~

### 17.1. Disposition

Khi đóng alert, ghi một disposition rõ:
- True positive / confirmed incident;
- True positive / policy violation without compromise;
- Benign positive / expected activity;
- False positive / rule error;
- Duplicate / grouped into another case;
- Insufficient evidence / monitoring gap.

Không dùng “closed” mà không ghi lý do, vì dữ liệu disposition cần thiết để cải thiện rule.

### 17.2. Reopen

Nếu cùng entity có evidence mới hoặc một alert đã resolve nhưng hành vi tiếp diễn, có thể reopen hoặc tạo alert liên kết. Không xóa lịch sử trạng thái cũ.

## 18. Triage và runbook

Runbook nên trả lời các câu hỏi cụ thể:
1. Rule nào phát hiện và version nào đang chạy?
2. Event nào tạo alert và nguồn nào là authoritative?
3. Có bao nhiêu principal, tenant, device và source bị ảnh hưởng?
4. Có success sau failure không?
5. Có session, token, factor hoặc recovery change sau login không?
6. Có provider outage, deployment hoặc policy change cùng thời điểm?
7. Account có đặc quyền hoặc dữ liệu nhạy cảm không?
8. Cần revoke session/token, step-up, throttle hay chỉ theo dõi?
9. Ai có thẩm quyền thực hiện containment?
10. Bằng chứng nào cần bảo toàn và thời gian retention ra sao?

### 18.1. Containment có chọn lọc

Tùy evidence, có thể:
- Throttle source/client;
- Yêu cầu step-up;
- Revoke một session/token family;
- Tạm disable một credential;
- Bắt đầu recovery flow;
- Tạm ngăn một action nhạy cảm;
- Thu hồi workload certificate nếu bị compromise.

Không tự động khóa toàn bộ account hoặc tenant chỉ từ một alert có confidence thấp. Cần đánh giá blast radius và khả năng gây DoS.

### 18.2. Bảo toàn evidence

Lưu event reference, timestamps, rule version, actor, decision và action. Không copy token/cookie vào ticket. Nếu cần forensic artifact, lưu trong kho có quyền truy cập và chain of custody phù hợp.

## 19. Automated response và guardrails

Một số alert có thể kích hoạt response tự động, nhưng mức tự động hóa cần tương xứng với confidence và tác động.

| Confidence / impact | Hành động tự động phù hợp |
| --- | --- |
| Low confidence, low impact | Tạo alert, enrich context, không thay đổi account |
| Medium confidence | Throttle/challenge theo source hoặc request |
| High confidence, bounded scope | Revoke session/token cụ thể hoặc yêu cầu step-up |
| Confirmed compromise | Kích hoạt playbook containment theo quyền đã phê duyệt |

### 19.1. Guardrails

- Idempotent action và request reference;
- Scope rõ principal/session/tenant/resource;
- TTL cho temporary control;
- Approval hoặc dual control cho hành động có blast radius lớn;
- Rollback/recovery path;
- Audit đầy đủ;
- Rate limit cho automation;
- Kill switch có kiểm soát;
- Không gửi secret qua notification.

### 19.2. Không để alert tự phê duyệt hành động

Detection rule không phải approver. Với việc khóa account admin, revoke key dùng chung hoặc disable tenant, cần approval theo policy trừ khi emergency playbook đã được phê duyệt trước.

## 20. Phân biệt security alert và operational alert

Authentication có thể thất bại vì attacker hoặc vì hệ thống không hoạt động.

| Dấu hiệu | Có thể là security | Có thể là operational |
| --- | --- | --- |
| Failure spike | Spraying/stuffing | Deployment lỗi |
| MFA timeout | Push fatigue | Notification provider outage |
| Token invalid | Replay/wrong audience abuse | Clock skew/JWKS rotation lỗi |
| Certificate rejected | Private key/cert misuse | Cert hết hạn do quên rotation |
| Login latency | Resource exhaustion/DoS | IdP/database overload |
| Session revoke failure | Attacker giữ session | Event bus/cache outage |

### 20.1. Correlate với change event

Kết hợp authentication alert với deployment, configuration change, certificate rotation, IdP health và network incident. Nếu failure bắt đầu ngay sau release, điều đó không chứng minh lỗi release nhưng là context cần điều tra.

### 20.2. Tách alert channel

Security operations và platform operations có thể dùng queue khác nhau nhưng cần liên kết case khi một sự cố ảnh hưởng cả bảo mật lẫn availability. Tránh route mọi lỗi token tới SOC nếu nguyên nhân rõ là IdP outage.

## 21. Alert quality và vận hành detection

Đo chất lượng alert để biết rule có hữu ích không.

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Precision** | Tỷ lệ alert được xác nhận là có giá trị trong tổng alert đã triage |
| **Recall** | Tỷ lệ scenario/incident mô phỏng hoặc đã biết được phát hiện |
| **False positive rate** | Tỷ lệ alert không cần hành động bảo mật |
| **MTTD** | Thời gian từ hoạt động đáng ngờ tới phát hiện |
| **MTTA** | Thời gian tới khi người trực acknowledge |
| **MTTR** | Thời gian xử lý/containment theo định nghĩa tổ chức |
| **Alert volume** | Số alert theo rule/team/time |
| **SLA breach** | Alert không được xử lý đúng hạn |
| **Duplicate rate** | Tỷ lệ notification lặp cho cùng pattern |
| **Action success rate** | Tỷ lệ automated response thực hiện đúng |
| **User friction** | Challenge, support ticket hoặc login disruption do rule |

### 21.1. Precision và recall

Một rule quá nhạy có thể bắt được nhiều tình huống nhưng tạo nhiều false positive. Rule quá chặt có thể giảm noise nhưng bỏ sót attack low-and-slow. Dùng simulation, red-team scenario đã được cho phép và incident review để đánh giá cả hai.

### 21.2. Alert fatigue

Dấu hiệu gồm notification bị bỏ qua, acknowledge chậm, suppression quá rộng và analyst thường xuyên đóng alert mà không xem evidence. Cải thiện bằng grouping, context enrichment, rule tuning và owner rõ ràng, không đơn giản tắt alert.

### 21.3. Rule lifecycle

Mỗi rule cần owner, purpose, version, data source, test cases, severity mapping, rollout plan và review date. Thay đổi threshold cần audit. Có thể chạy shadow mode trước khi bật notification hoặc automated response.

## 22. Pseudocode detection và alert lifecycle

~~~text
evaluate_authentication_alerts(event):
    require event_schema_is_valid(event)
    require telemetry_source_is_trusted(event)
    normalize_event_time_and_identity_refs(event)

    if duplicate_event(event.id):
        return IGNORE_DUPLICATE

    update_attempt_and_entity_windows(event)
    update_bounded_metrics(event)

    if telemetry_health_is_degraded():
        create_operational_alert_if_needed()
        mark_security_detection_confidence_limited()

    candidates = run_versioned_detection_rules(event.context)

    for candidate in candidates:
        enriched = enrich_with_authorized_context(candidate)
        confidence = calculate_evidence_confidence(enriched)
        severity = assess_potential_impact(enriched)
        priority = prioritize(severity, confidence, exposure)

        alert = build_minimized_alert(
            rule = candidate.rule,
            evidence_refs = enriched.event_refs,
            severity = severity,
            confidence = confidence,
            priority = priority
        )

        if existing_group(alert.dedup_key):
            update_grouped_alert(alert)
        else:
            create_alert(alert)
            route_to_owner(alert)

        if response_policy_allows_automation(alert):
            execute_scoped_idempotent_action(alert)
            record_action_and_result(alert)

    return DETECTION_COMPLETE
~~~

Đây là pseudocode khái niệm. Triển khai cần xử lý event-time windows, distributed state, idempotency, race, authorization của enrichment query, rule versioning, notification retry, partial failure và audit. Automated response cần kiểm tra scope trước khi thực thi.

## 23. Ví dụ alert payload

~~~json
{
  "alert_id": "alrt_01JQ9F2A",
  "rule_id": "AUTH-SPRAY-004",
  "rule_version": 3,
  "title": "Possible password spraying",
  "severity": "high",
  "confidence": "medium",
  "priority": "P2",
  "first_seen": "2026-11-22T08:15:00Z",
  "last_seen": "2026-11-22T08:19:00Z",
  "window_seconds": 300,
  "tenant_ref": "tenant_ref_42",
  "source_ref": "network_ref_19",
  "affected_principal_count": 37,
  "failed_attempt_count": 61,
  "success_after_failure_count": 1,
  "auth_method": "password",
  "failure_class": "credential_rejected",
  "evidence_refs": ["evt_ref_1", "evt_ref_2"],
  "owner_team": "security-operations",
  "runbook_id": "RB-AUTH-07",
  "status": "new"
}
~~~

Payload là ví dụ minh họa. Nó dùng reference đã pseudonymize và không chứa email, password, OTP, token hoặc session cookie. Analyst cần quyền phù hợp để mở evidence reference chi tiết.

## 24. Kiểm thử authentication alert

Kiểm thử trong staging với event giả lập, test account và provider sandbox. Không tạo password spray hoặc MFA fatigue trên người dùng production.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Brute force | Nhiều failure trên một principal | Rule phát hiện theo window và scope |
| Password spraying | Một source thử nhiều principal | Alert có affected principal count |
| Distributed spraying | Pattern phân tán qua nhiều source | Rule correlation không chỉ phụ thuộc IP |
| Credential stuffing | Failure xen kẽ success trên nhiều account | Alert tăng confidence khi có corroborating signal |
| Enumeration | Nhiều identifier bị probe | Alert theo endpoint/pattern |
| MFA fatigue | Push denied/timeout lặp | Alert có challenge count và principal reference |
| MFA outage | Provider timeout trên diện rộng | Operational alert, không nhầm credential attack |
| Passkey enrollment | Thêm authenticator bất thường sau recovery | Correlation alert |
| Token reuse | Refresh token family reuse | Alert theo token family reference |
| Wrong audience | Token bị gửi sai backend | Security/policy alert theo source và service |
| Session after revoke | Session tiếp tục hoạt động sau revoke | Alert về revocation propagation |
| Recovery abuse | Nhiều recovery request hoặc helpdesk override | Alert theo principal/tenant/case |
| Privileged login | Admin login từ device/context mới | Step-up hoặc triage theo policy |
| Certificate anomaly | Workload dùng certificate revoked | Alert và route IAM/platform |
| Provider outage | IdP latency/error tăng đồng loạt | Operational alert có provider context |
| Duplicate event | Producer gửi event lặp | Không tạo nhiều alert độc lập |
| Grouping | Nhiều event cùng pattern | Một alert được cập nhật count/evidence |
| Suppression | Pattern lặp trong suppression window | Notification gộp nhưng event vẫn lưu |
| Severity change | Evidence mới nâng impact | Alert được nâng priority/escalate |
| Telemetry loss | Event pipeline drop hoặc lag | Operational alert và confidence bị giới hạn |
| Clock skew | Event time bất thường | Đánh dấu chất lượng dữ liệu |
| Enrichment failure | Identity service không truy cập được | Alert ghi rõ context chưa đầy đủ |
| Privacy | Payload được gửi qua chat/email | Chỉ có pseudonymous reference |
| Automation | Revoke session theo rule đã duyệt | Action scoped, idempotent và audit |
| False positive | Người dùng quên password hàng loạt | Baseline/context giúp giảm escalation |
| Closure | Analyst đóng alert | Disposition, actor và evidence được lưu |

### 24.1. Bất biến bảo mật

- Alert có rule ID/version, evidence reference và timestamp;
- Severity, confidence và priority được phân biệt;
- Duplicate event không tạo notification vô hạn;
- Suppression không xóa event hoặc che alert severity cao hơn;
- Payload không chứa credential hoặc secret;
- Enrichment chỉ truy cập dữ liệu mà analyst/service được phép;
- Automated response có scope, idempotency, TTL, audit và rollback;
- Telemetry degraded được thể hiện rõ;
- Alert closure có disposition và người chịu trách nhiệm.

## 25. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi mọi failed login là incident | Alert fatigue | Correlation, baseline và severity |
| Một event tạo nhiều alert | On-call bị spam | Deduplication và grouping |
| Severity đồng nhất với confidence | Ưu tiên sai | Tách impact, confidence và priority |
| Rule không có owner | Alert bị bỏ quên | Owner, SLA và escalation |
| Alert không có evidence | Analyst phải tự tìm từ đầu | Event references và context enrichment |
| Payload chứa token/PII | Rò credential/dữ liệu cá nhân | Minimize và pseudonymize |
| Suppression quá rộng | Bỏ sót pattern mới | Scope/time bound và severity override |
| Tự khóa account theo count | Attacker gây DoS | Risk-based response và scoped throttle |
| IdP outage bị coi là attack | Route sai đội, chậm khắc phục | Operational/security classification |
| Không version rule | Không tái hiện được quyết định | Rule version và audit |
| Automated response không idempotent | Revoke/disable lặp hoặc sai | Idempotency key và state check |
| Không có rollback | Người dùng bị gián đoạn kéo dài | TTL, recovery path và owner |
| Enrichment tin dữ liệu client | Context bị giả mạo | Authoritative source và authorization |
| Không theo dõi pipeline health | Alert im lặng khi mất event | Telemetry health alert |
| Đóng alert không disposition | Không cải thiện detection | Bắt buộc closure reason |

## 26. Checklist production

1. **Scope:** Đã liệt kê các authentication flow, event source và account quan trọng?
2. **Event quality:** Attempt/event ID, timestamp, outcome và reason code có chuẩn hóa?
3. **Authoritative source:** Có tránh đếm trùng giữa gateway, IdP và backend?
4. **Rule design:** Có condition, scope, window, context và test case rõ?
5. **Detection coverage:** Có brute force, spraying, stuffing, MFA fatigue, token/session và recovery abuse?
6. **Baseline:** Threshold phù hợp tenant, client, method và mùa vụ?
7. **Confidence:** Có corroborating signal và phân biệt confidence với severity?
8. **Grouping:** Dedup key không chứa secret/PII; alert group giữ evidence và phạm vi?
9. **Suppression:** Có time bound, owner và severity override?
10. **Payload:** Có đủ evidence nhưng không chứa password, OTP, token, cookie hoặc private key?
11. **Routing:** Alert đến đúng SOC, IAM, platform hoặc tenant owner?
12. **SLA:** Có acknowledgement, escalation, runbook và closure disposition?
13. **Automation:** Action có scope, idempotency, TTL, approval và rollback?
14. **Privacy:** Raw identity/source chỉ truy cập qua kho có quyền và audit?
15. **Operational context:** IdP outage, deployment và certificate rotation được correlate?
16. **Telemetry health:** Event loss, queue lag, schema rejection và clock skew được giám sát?
17. **Quality:** Có precision, recall, MTTD, MTTA, MTTR, duplicate rate và alert fatigue review?
18. **Testing:** Có simulation, shadow mode, false-positive review và regression?
19. **Governance:** Mỗi rule có owner, version, purpose và review date?
20. **Incident readiness:** Có playbook containment và bảo toàn evidence?

## 27. Bài tập tình huống

Một nền tảng học tập gửi alert cho mọi lần login thất bại. Mỗi lần password sai tạo một notification; MFA push timeout cũng được tính như login failure; IdP outage làm hàng nghìn alert xuất hiện. Một alert chỉ ghi email người dùng và số lần lỗi, không có tenant, device, source, method hoặc evidence. Một automation khóa account sau 10 failures. Đội trực thường xuyên bỏ qua notification.

**Yêu cầu:**

1. Xác định ít nhất **tám vấn đề** trong detection, payload, routing và automated response.
2. Thiết kế taxonomy event và rule riêng cho brute force, spraying, MFA fatigue và IdP outage.
3. Đề xuất severity, confidence, priority và grouping key.
4. Thiết kế alert payload có pseudonymous reference và evidence link.
5. Đề xuất routing, acknowledgement, escalation và disposition.
6. Thay automation khóa account bằng response có scope và confidence phù hợp.
7. Xây dựng test cho duplicate, suppression, provider outage, telemetry loss và false positive.
8. Chọn các metric để đánh giá chất lượng alert sau 30 ngày.

**Gợi ý đối chiếu:** Alert cần dựa trên attempt/event chuẩn hóa; outage là operational alert; grouping theo principal/source/rule; tách severity và confidence; không gửi raw email qua notification; không hard-lock chỉ theo count; cần owner, runbook, disposition và quality metrics.

## 28. Ghi nhớ

- **Alert authentication** là tín hiệu cần triage, không tự động là incident đã xác nhận.
- Alert tốt cần event đáng tin cậy, rule có thể giải thích, context đủ, evidence reference và owner rõ.
- Phát hiện brute force, spraying, stuffing, MFA fatigue, token/session anomaly và recovery abuse cần correlation thay vì một threshold duy nhất.
- Severity đo tác động; confidence đo độ tin cậy; priority xác định thứ tự xử lý.
- Deduplication, grouping và suppression giảm notification lặp nhưng không được xóa event hoặc che pattern nghiêm trọng.
- Payload phải tối thiểu hóa PII và tuyệt đối không chứa password, OTP, token, cookie hoặc private key.
- Phân biệt security alert với IdP/provider outage và deployment/misconfiguration.
- Automated response cần scope, confidence, idempotency, TTL, approval và rollback.
- Alert lifecycle cần acknowledgement, escalation, investigation, disposition và audit.
- Đo precision, recall, MTTD, MTTA, MTTR, duplicate rate và alert fatigue để cải thiện detection.

Authentication alert có giá trị khi **tín hiệu đủ đáng tin để giải thích điều gì bất thường, đúng người nhận được giao trách nhiệm và response tương xứng với bằng chứng cùng tác động**. Một hệ thống cảnh báo trưởng thành vừa phát hiện hành vi xâm nhập, vừa phân biệt sự cố vận hành và bảo vệ người dùng khỏi các biện pháp phản ứng quá mức.
