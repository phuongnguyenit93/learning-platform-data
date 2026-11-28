# Khai thác có kiểm soát – Xác minh khả năng khai thác trong penetration testing bằng bằng chứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **khai thác có kiểm soát (controlled exploitation)** trong penetration testing, phân biệt với vulnerability discovery, scanner validation, threat modeling, red teaming, incident simulation và tấn công thực tế.
- Xây dựng **mục tiêu kiểm chứng có giới hạn**: điều gì cần chứng minh, ở tài sản nào, bằng điều kiện tối thiểu nào, khi nào dừng và mức tác động nào tuyệt đối không được vượt.
- Viết và đánh giá **Rules of Engagement (RoE)** gồm authorization, scope, thời hạn, phương pháp được phép, account/credential, dữ liệu thử nghiệm, safety boundaries, on-call và emergency stop.
- Chọn cách xác nhận rủi ro **ít xâm nhập nhất**: configuration evidence, safe negative test, synthetic data, test account, non-sensitive marker hoặc controlled lab reproduction thay vì cố lấy dữ liệu thật hoặc tăng tác động.
- Thiết kế **proof threshold** để chứng minh weakness/attack path mà không cần gây thiệt hại, duy trì persistence hay mở rộng quyền vượt phạm vi.
- Xử lý những tình huống nhạy cảm như cross-tenant authorization, privilege boundary, file upload, SSRF, command injection, authentication/session, cloud IAM và workflow nhiều bước theo phương pháp an toàn.
- Tổ chức monitoring, stop conditions, containment, rollback, evidence handling, chain of custody và escalation khi phát hiện hành vi bất thường.
- Chuyển kết quả từ một PoC sang **risk assessment, security requirement, finding, remediation, retest và assurance claim** có phạm vi.
- Xây dựng kế hoạch kiểm thử và bằng chứng bằng Java 17/Spring Boot/JUnit cho các negative authorization test trên fixture vô hại; biết giới hạn của từng test.
- Vận hành continuous assurance khi code, deployment, identity, trust boundary hoặc threat intelligence thay đổi.

## 1. Khai thác có kiểm soát là gì?

**Khai thác có kiểm soát** là việc thực hiện một bước xác minh kỹ thuật đối với một điểm yếu **trong phạm vi đã được cấp quyền**, với ranh giới rõ về thời gian, kỹ thuật, dữ liệu và mức tác động, nhằm thu bằng chứng đủ tin cậy cho một security claim hoặc finding.

Mục tiêu **không phải gây thiệt hại tối đa**. Mục tiêu là trả lời câu hỏi rủi ro cụ thể với **bằng chứng tối thiểu nhưng đủ sức thuyết phục**, ví dụ:

> Một customer thuộc tenant A có thể truy cập báo cáo do tenant B sở hữu hay không, khi truy cập qua API đã được chỉ định?

Trong môi trường kiểm thử được cho phép, ta có thể tạo hai tenant và hai báo cáo **giả**, gửi một request chéo tenant và đánh giá response cùng database/audit side effects. Không cần đọc báo cáo khách hàng thật hoặc thử nhiều tài khoản bên ngoài scope.

### 1.1. Khai thác thành công không đồng nghĩa đã đạt mục tiêu assurance

Một PoC có thể cho thấy một hành vi:
- Gọi API trả dữ liệu không đúng tenant.
- Một route cho phép thay đổi cấu hình khi không đủ quyền.
- Một input đạt điều kiện lỗi theo advisory.
- Một credential có quyền rộng hơn yêu cầu.
- Một rule gateway có đường bypass trong lab.

Nhưng muốn kết luận có rủi ro thực tế, phải xác định:
- Asset/deployment/version nào có điểm yếu?
- Điều kiện khai thác và quyền attacker cần là gì?
- Proof có xảy ra trên đúng trust boundary không?
- Tác động tới dữ liệu, tính toàn vẹn hoặc vận hành ra sao?
- Compensating controls có hiệu lực ở các đường khác không?
- Những phần nào **chưa được kiểm**?
- Bằng chứng có thể đối chiếu, không chứa secret/data thật ngoài cần thiết không?

Trong dịch vụ **SECURITY_SECURITY_ASSURANCE**, controlled exploitation là một phương pháp **kiểm chứng bằng chứng**, phục vụ chuỗi **risk → objective → requirement → control → test → evidence → finding → remediation/retest**, không phải mục tiêu độc lập.

### 1.2. Điều không phải controlled exploitation

- Thử vào hệ thống ngoài scope “để xem có bị ảnh hưởng không”.
- Dùng credential lấy từ rò rỉ mà chưa có phê duyệt xử lý.
- Truy xuất hàng loạt PII chỉ để chứng minh data exposure.
- Giữ quyền truy cập lâu dài, đặt backdoor/persistence.
- Thử phá hoại dữ liệu, làm cạn tài nguyên hoặc gián đoạn hoạt động để tăng bằng chứng.
- Mở rộng sang tenant/host bên thứ ba vì một redirect hoặc route tình cờ xuất hiện.
- Tự “sửa” hệ thống hoặc xóa logs/finding trong quá trình kiểm chứng.
- Chạy tool active scan/exploit ở production mà không biết side effects hay không có stop plan.

**Một kỹ thuật có thể hợp lệ trong lab nhưng không được phép ở production.** Authorization, environment và RoE quyết định giới hạn.

## 2. Phân biệt detection, validation, exploitation và impact

| Cấp độ | Câu hỏi | Ví dụ evidence | Giới hạn |
| --- | --- | --- | --- |
| **Discovery** | Có dấu hiệu cấu hình/phiên bản dễ bị ảnh hưởng? | Scanner alert, package/version, header | Chưa xác minh behavior |
| **Triage** | Finding có đúng asset và risk scenario? | Inventory, advisory applicability, code path | Có thể còn uncertainty |
| **Validation** | Control/behavior có sai theo requirement? | Negative test, policy check, response diff | Không luôn chứng minh exploitability thực |
| **Controlled exploitation** | Có thể đi qua trust boundary tới kết quả ngoài quyền, trong giới hạn đã duyệt? | Synthetic marker/fixture/side-effect test | Chỉ chứng minh scenario đã thực hiện |
| **Impact assessment** | Hậu quả tiềm năng cho confidentiality/integrity/availability? | Data classification, threat model, scope | Không cần gây tác động thật |
| **Retest** | Fix đã chặn scenario trên đúng artifact/deployment? | Same test/fixture và actual-state evidence | Không chứng minh mọi variant đều đã hết |
| **Continuous monitoring** | Control còn hiệu lực khi environment đổi? | Policy/drift/change records | Không thay security testing |

Trong nhiều trường hợp, **validation bằng test an toàn là đủ** để xác nhận finding; không cần chuyển sang một exploit sâu hơn. Quy tắc chuẩn là **bằng chứng tối thiểu đủ chứng minh**, không phải “luôn đi đến mức privilege cao nhất”.

## 3. Nền tảng bắt buộc: authorization và Rules of Engagement

### 3.1. Authorization phải cụ thể

RoE hoặc engagement authorization cần nêu:
- **Asset owner** và người có thẩm quyền cho phép, approval reference.
- Hệ thống/host/domain, IP/port, route, cloud account và region được phép.
- Production, staging, sandbox hay isolated lab.
- Start/end time và timezone; điều kiện gia hạn.
- Identity/test accounts, roles, tenants và credentials được cấp.
- Loại kiểm thử được phép: read-only, negative authorization, limited active, manual PoC, controlled lab reproduction.
- Hành vi cấm: phá dữ liệu, brute-force, persistence, malware deployment, stress/DoS, exfiltration, third-party pivot.
- **Proof ceiling:** lượng dữ liệu, số record, số request và tác dụng phụ tối đa được duyệt.
- Rate/concurrency/resource budget, schedule, maintenance windows.
- Cơ chế phân biệt test traffic với abuse, source IP/correlation ID, liên hệ SOC.
- Stop/kill switch và người có quyền yêu cầu dừng.
- Recovery, backup/restore, rollback và incident handoff.
- Cách lưu/che dữ liệu nhạy cảm trong evidence.
- Quy trình xử lý khi phát hiện vấn đề ngoài scope hoặc rủi ro nghiêm trọng.

**Một ticket “pentest approved” mơ hồ không đủ** nếu không xác định kỹ thuật/phạm vi tác động. Với hệ thống liên quan bên thứ ba, cloud provider, payment hoặc dữ liệu nhạy cảm, cần kiểm tra nghĩa vụ hợp đồng/pháp lý và approval cần thiết theo tổ chức.

### 3.2. Ma trận quyền minh họa

| Hoạt động | Isolated lab | Staging synthetic | Production |
| --- | --- | --- | --- |
| Đọc configuration/test evidence | Theo lab policy | Có phê duyệt | Theo quyền được cấp |
| Negative authZ test với fixture | Có thể thực hiện | Thường phù hợp khi duyệt | Chỉ test đã được owner duyệt |
| Active scanner | Có thể kiểm soát | Kiểm soát traffic/side effects | Không tự động cho phép |
| Gọi state-changing endpoint | Dữ liệu reset được | Chỉ fixture/cleanup plan | Cần approval riêng và safety limits |
| PoC tác động dịch vụ/privilege | Theo lab risk | Hạn chế và kiểm soát | Mặc định không thực hiện ngoài approval rõ |
| Đọc PII/secret thật | Không cần | Không dùng thật | Không mở rộng truy xuất để “chứng minh” |
| Persistence/lateral movement | Chỉ khi bài lab cho phép | Thường loại trừ | Không thực hiện nếu RoE không cho |
| Third-party endpoints | Không | Mock/sandbox | Ngoài scope trừ khi có authorization độc lập |

Đây là **ví dụ chính sách**, không tự tạo permission. Mọi thao tác đều phải khớp authorization thực tế.

### 3.3. Trong tình huống chưa rõ

- **Không thử trước rồi xin phép sau.**
- Dừng ở quan sát an toàn, ghi limitation hoặc yêu cầu scope review.
- Không tự nâng privileges bằng cách dùng test account của người khác.
- Không “lách” WAF, hệ thống giám sát hoặc các guardrails khi chưa có phê duyệt riêng.
- Nếu cần chứng minh hơn giới hạn ban đầu, trình owner/risk assessor mở rộng RoE trước.
- Khi phát hiện dữ liệu thật, **ngừng truy xuất**, bảo toàn bằng chứng tối thiểu, báo qua kênh đã duyệt.

## 4. Threat model và proof threshold

### 4.1. Xác định mục tiêu kiểm chứng

Một scenario nên có:
1. **Asset/entry point:** service, route, protocol, API version, worker/job.
2. **Attacker model:** anonymous, authenticated user, tenant A, limited service identity.
3. **Weakness hypothesis:** thiếu authZ object level, trust header từ client, resource isolation sai.
4. **Preconditions:** session/token, feature flag, network reachability, fixture state.
5. **Security objective:** confidentiality/integrity/availability/identity/data protection.
6. **Expected control:** server-side authorization, scoped query, no unauthorized side effect.
7. **Minimum proof:** một fixture request không hợp lệ dẫn tới marker chỉ định, hoặc denial đúng.
8. **Stop boundary:** sau khi có đủ proof, không tiếp tục lấy records/tăng quyền.
9. **Verification evidence:** request ID, response, sanitized logs, DB/job observation và timestamp.
10. **Limits/uncertainty:** paths/roles/regions chưa test và những giả định.

### 4.2. Proof threshold (ngưỡng chứng minh)

Đặt **mức bằng chứng cần thiết trước khi thử** để tránh bị cuốn vào việc thử ngày càng sâu:

| Mức | Mục tiêu | Ví dụ hợp lệ trong lab |
| --- | --- | --- |
| **P0 – Evidence only** | Xác minh control/config/phiên bản | Effective policy, trusted scanner finding |
| **P1 – Harmless behavior** | Xác minh validation/deny behavior | Wrong-role request nhận deny đúng |
| **P2 – Synthetic boundary proof** | Chứng minh trust boundary có thể bị vượt | Tenant A nhìn thấy marker giả của tenant B |
| **P3 – Limited state-change proof** | Chứng minh unauthorized mutation trên fixture | Một giá trị giả bị sửa, có rollback/DB audit |
| **P4 – Higher-impact proof** | Có thể ảnh hưởng service/dữ liệu/quyền thật | Không thực hiện nếu RoE không cấp phép rõ |

**Chọn mức thấp nhất đủ hỗ trợ claim.** Nếu P2 đã chứng minh lỗi cross-tenant, không cần truy xuất 10.000 hồ sơ thật. Với finding nghiêm trọng, có thể dừng ở P0/P1 nếu higher impact gây rủi ro, ghi uncertainty và bổ sung phân tích code/config.

### 4.3. Threat paths và trust boundaries

~~~mermaid
flowchart LR
    U["Test user tenant A"] --> GW["Authorized gateway"]
    GW --> API["report-api"]
    API --> AUTH["Server-side access policy"]
    AUTH --> DB["Synthetic tenant A/B records"]
    API --> Q["Export queue"]
    Q --> WRK["Export worker"]
    WRK --> STORE["Synthetic test storage"]
    P["Pen test assessor"] -. "P0/P1/P2 approved proofs" .-> GW
    LOG["Audit and monitoring"] -. "Correlated events" .-> API
    LOG -. "Observed side effects" .-> WRK
~~~

Không nên chỉ nhìn HTTP status: một denied HTTP request vẫn có thể tạo job hoặc side effect trước khi trả lỗi. Trong bài test kiểm chứng, phải quan sát **API, queue, storage và audit** khi threat path bao gồm các thành phần đó.

## 5. Quyết định có cần exploit hay không

### 5.1. Các câu hỏi trước bước chủ động

- Finding đã đủ chứng cứ chỉ qua vendor advisory/actual package version chưa?
- Có test configuration/server-side control nào ít ảnh hưởng hơn không?
- Có thể tái hiện trong isolated lab hoặc staging với synthetic fixtures không?
- Một request có thể làm thay đổi dữ liệu/queue/cache không?
- Điều kiện exploit có gây crash, lockout, egress, scan storm hoặc external callback không?
- Có cách chứng minh bằng **one-record marker** thay vì data extraction không?
- Có người trực vận hành giám sát và quyền dừng ngay không?
- RoE có cho phép đúng loại test, target/route/account/tenant không?
- Evidence cần để triage/risk thật sự là gì?
- Nếu thất bại, recovery có sẵn và đã được duyệt chưa?

Nếu thiếu một tiền đề quan trọng, không tự động tiếp tục; đánh dấu **INCONCLUSIVE/NEEDS_AUTHORIZATION** và bổ sung evidence.

### 5.2. Decision tree

~~~mermaid
flowchart TD
    F["Finding / exploitability hypothesis"] --> A{"Authorization và scope hợp lệ?"}
    A -- "Không" --> STOP["Dừng và xin phê duyệt"]
    A -- "Có" --> S{"Cần exploit để chứng minh?"}
    S -- "Không" --> E["Configuration/code/advisory evidence"]
    S -- "Có" --> L{"Có lab/synthetic proof ít tác động?"}
    L -- "Có" --> T["Thiết kế minimal bounded test"]
    L -- "Không" --> R["Owner/risk review, re-scope or INCONCLUSIVE"]
    T --> MON["Precheck + runtime monitoring"]
    MON --> X{"Tác động trong proof ceiling?"}
    X -- "Không" --> STOP
    X -- "Có" --> RUN["Single controlled attempt"]
    RUN --> OBS["Collect minimal evidence"]
    OBS --> C{"Proof đạt hoặc stop trigger?"}
    C -- "Có" --> HALT["Dừng; không escalation ngoài RoE"]
    C -- "Chưa" --> R
    E --> REPORT["Scoped risk finding/report"]
    HALT --> REPORT
    R --> REPORT
~~~

## 6. Phân loại hoạt động theo mức độ rủi ro

| Nhóm | Ví dụ proof | Tác động cần quản lý |
| --- | --- | --- |
| Read-only configuration | TLS policy, session cookie, effective IAM | Metadata/secret exposure |
| Negative authorization | Wrong-role/tenant synthetic request | Disclosure nếu control lỗi |
| Input boundary | Invalid schema/type/size với payload nhỏ | Errors, log noise, resource usage |
| State transition | Duplicate approval hoặc revoked entitlement trên fixture | Data integrity, queue/jobs |
| File processing | Một file giả, kích thước giới hạn | Parser failures, storage/compute |
| Outbound HTTP/SSRF boundary | Approved internal mock endpoint làm destination | Egress/trust boundary, không gọi external target |
| Authentication/session | Expired/revoked test session | Rate limit/lockout, logs |
| Cloud permissions | Read IAM simulation/effective policy and deny tests | Privilege scope; không khai thác account thật |
| Infrastructure/service restart | Không cần cho thông thường | Availability và change control |
| Privilege escalation/persistence | Chỉ simulated lab proof nếu phục vụ học tập | Mặc định loại khỏi engagement standard |

Các kỹ thuật có khả năng gây gián đoạn, phá dữ liệu hoặc lan truyền không phù hợp với một bài thực hành thông thường. Khi rủi ro cao, ưu tiên **architecture review, configuration tests, mock service hoặc manual proof** thay vì thử ảnh hưởng thật.

## 7. Safe proof design: chứng minh bằng một marker vô hại

### 7.1. Một synthetic object

Giả sử trong test database tạo:
- Tenant `TENANT_A`, user `user-a`.
- Tenant `TENANT_B`, user `user-b`.
- Report `report-b-synthetic` có nội dung `SYNTHETIC_MARKER_B_001`, **không phải dữ liệu thật**.
- Object ownership và expected access matrix đã được owner xác nhận.

Scenario:
- User A được phép gọi API với session test của A.
- Điều chỉnh **chỉ object ID test được owner cấp** trong request đã approved để tham chiếu `report-b-synthetic`.
- Expected: deny hoặc conceal existence theo policy; không trả marker của B.
- Nếu response hoặc downstream export có marker của B, đã có proof về cross-tenant control failure trong test scope.

**Dừng sau khi quan sát đủ một proof.** Không tăng số lượng IDs, không thử account thật hoặc export toàn bộ records.

### 7.2. Proof không cần dữ liệu thật

| Security claim | Proof tối thiểu | Không cần làm |
| --- | --- | --- |
| Tenant isolation | Deny hoặc one-marker test trên synthetic resource | Đọc customer records |
| Export authorization | No-job/no-file side effect khi requester thiếu quyền | Tải bulk export thật |
| Role-based access | Wrong-role request bị deny | Dùng admin account không thuộc scope |
| Audit integrity | Unauthorized action bị log đúng metadata đã chuẩn hóa | Gây sự cố để đo logs |
| Sensitive data minimization | Synthetic secret field không xuất hiện | Truy cập real secrets |
| Webhook replay policy | Synthetic request ID bị từ chối khi duplicate | Replay thông điệp thật |
| Storage access scope | Test object/prefix chỉ đọc được bởi role được cấp | Liệt kê bucket dữ liệu thật |
| Process isolation | Policy/test harness deny forbidden action | Chạy code tăng quyền trên production |

### 7.3. Giới hạn PoC

- Đánh dấu test data bằng namespace/marker rõ.
- Đặt maximum requests, maximum records và time window.
- Không giữ sensitive responses; dùng redacted evidence hoặc hashed references nếu phù hợp.
- Không thực hiện credential dumping, persistence hoặc lateral movement trừ khi có một engagement chuyên biệt cho phép rõ và safety plan riêng.
- Không tận dụng một weakness để mở rộng discovery vượt assets được duyệt.
- Nếu có data disclosure thật ngoài dự kiến, **ngừng, ghi metadata tối thiểu, báo owner và bảo vệ evidence**, không tiếp tục thu thập.

## 8. Test accounts, identities và authorization context

### 8.1. Bộ identity cho một case study web/API

| Persona | Quyền theo policy | Mục đích |
| --- | --- | --- |
| Anonymous | Không truy cập protected resources | Authentication boundary |
| User A tenant A | Xem report thuộc A | Positive fixture |
| User B tenant B | Xem report thuộc B | Negative cross-tenant fixture |
| Support no-case | Không xem report khách hàng | Privilege boundary |
| Support with approved case | Chỉ report/case/time được phép | Conditional authorization |
| Auditor | Xem metadata kiểm toán, không payload | Field-level authorization |
| Export worker | Chỉ job/prefix được gán | Service-to-service authorization |
| Admin test | Chỉ các controls đã approved | Privileged workflow review |

### 8.2. Không dùng thông tin do client tự khai làm quyền

Một client có thể gửi tenant ID, role hoặc resource owner trong path/query/header. Server phải xác định quyền từ **trusted principal và business policy**, không tin một header do client sửa. Test controlled exploitation nên kiểm:
- Principal từ token/session được xác thực thật.
- Resource thuộc tenant/owner đã biết từ fixture.
- Request claim/headers có thể sai nhưng server vẫn deny.
- Denied request không tạo side effect tại DB/queue/storage.
- Cùng scenario được kiểm với API v1/v2 hoặc internal path khi trong scope.

### 8.3. Có thể test authentication flow đến đâu?

- Invalid/expired token, revoked role, cross-tenant fixtures: có thể kiểm có giới hạn trong environment đã được duyệt.
- MFA/reset/account lockout: cần test accounts và rate/budget để tránh khóa người dùng thật.
- Password guessing/stuffing: không là mặc định của controlled exploitation, yêu cầu authorization riêng; ưu tiên policy/lockout simulation.
- Cloud/service identities: dùng test principal và deny tests; không mượn compromised production secret.

## 9. Đảm bảo an toàn vận hành

### 9.1. Pre-flight checklist

- [ ] Scope, RoE và authorization đã xác nhận còn hiệu lực.
- [ ] Tài sản, owner, environment, release ID và test route chính xác.
- [ ] Threat scenario và **proof threshold** được review.
- [ ] Synthetic fixtures/test credentials được cấp và có expiry.
- [ ] Không có target/redirect/callback ngoài scope.
- [ ] Hạn mức traffic, time, concurrency, memory/CPU phù hợp.
- [ ] Không có operation phá dữ liệu/truy cập thông tin thật.
- [ ] On-call/SOC và incident contact có sẵn.
- [ ] Monitoring nguồn telemetry là healthy.
- [ ] Có rollback/restore/cleanup path đã kiểm.
- [ ] Có stop conditions và ai được quyền dừng.
- [ ] Evidence capture bảo vệ khỏi PII/token leak.

### 9.2. Stop conditions

Dừng nếu:
- Route phản hồi dữ liệu người dùng thật ngoài fixture.
- Tool/test đang vượt request/time/data budget.
- Tăng latency/5xx, resource saturation, queue backlog hoặc service alert.
- Account bị khóa, session có identity lạ, token/secret bị lộ.
- Request redirect sang hệ thống bên thứ ba ngoài scope.
- Job/file/email/payment thật được tạo không như plan.
- Recovery/cleanup không thực hiện được.
- Thấy dấu hiệu actor khác đang khai thác hoặc incident.
- Người phụ trách vận hành hoặc system owner yêu cầu dừng.

**Không cần chờ đủ bằng chứng** nếu đã gặp stop trigger. Bảo vệ hệ thống và báo cáo event đúng kênh ưu tiên hơn hoàn thành PoC.

### 9.3. “Kill switch” và liên hệ

Một runbook nên có:
- Scan/test run ID, operator, on-call contact.
- Stop command hoặc khả năng ngừng test runner/traffic ở nguồn, không ảnh hưởng production pipeline khác.
- Biện pháp revoke test account/token, block synthetic traffic nếu cần.
- Cách tắt synthetic job/queue consumer được dùng trong lab.
- Khi nào liên hệ security incident response.
- Người phê duyệt restart engagement sau điều tra.
- Nơi ghi timeline, affected resources và recovery evidence.

Không cài “kill switch” dưới dạng backdoor hoặc cơ chế có quyền truy cập ngoài policy. Stop mechanism phải thuộc hạ tầng điều khiển hợp lệ của engagement.

## 10. Thu thập evidence nhưng không tạo rò rỉ mới

Bằng chứng cần đủ để reviewer phân biệt **đã quan sát được điều gì** với **đã suy luận ra điều gì**.

| Thành phần | Nên có | Tránh |
| --- | --- | --- |
| Test identity | Persona/test-account reference | Raw password/token |
| Target | Service, route, environment, deployment ID/digest | Nội dung host ngoài scope |
| Preconditions | Synthetic fixture state, role, tenant | PII thật hoặc credentials |
| Test action | Method, sanitized request/parameter diff | Payload gây ảnh hưởng ngoài cần thiết |
| Response | Status, allowed fields, synthetic marker, request ID | Toàn bộ response nhạy cảm |
| Side effects | DB/job/storage audit row IDs trong sandbox | Dump dữ liệu bulk |
| Operational | Rate, timestamp, alerts, stop state | Logs chứa secret để public |
| Result | PASS/FAIL/INCONCLUSIVE và confidence | Claim “đã chiếm toàn bộ hệ thống” vô căn cứ |
| Review | Tester, reviewer, tool/build metadata | Self-attestation không có source |

### 10.1. Chain of custody

Đối với phát hiện có ảnh hưởng lớn:
1. Dùng timestamp nhất quán (UTC) và stable test IDs.
2. Gắn request/response/log samples với test run/deployment.
3. Giữ bản gốc tại evidence store có access control, encryption và retention phù hợp.
4. Tạo bản sanitized cho issue tracker/engineering review.
5. Có checksum/signature hoặc cơ chế bảo đảm integrity của evidence nếu policy yêu cầu.
6. Ghi ai đã truy cập, sửa/redact và phê duyệt kết luận.
7. Không chỉnh sửa raw evidence làm mất khả năng giải thích hành vi ban đầu.

### 10.2. Khi vô tình nhìn thấy sensitive data thật

- Ngừng truy xuất và không sao chép thêm.
- Ghi **số lượng/loại dữ liệu tối thiểu**, không giữ payload khi không cần.
- Theo incident/privacy procedure của tổ chức.
- Bảo vệ và giới hạn access của mọi evidence đã thu.
- Thu hồi/revoke credentials nếu lộ theo quy trình.
- Đánh giá thông báo/trách nhiệm pháp lý với đội chuyên trách, không tự kết luận.

Dữ liệu thật không phải điều kiện tiên quyết để chứng minh vulnerability nếu có cách dùng synthetic fixture/metadata.

## 11. Một quy trình controlled exploitation có thể kiểm toán

### 11.1. Các giai đoạn

~~~mermaid
flowchart TD
    ROE["Written authorization + RoE"] --> SCOPE["Assets, scenarios, proof ceiling"]
    SCOPE --> PREP["Synthetic fixtures, accounts, monitoring, rollback"]
    PREP --> PRE["Prechecks: identity, deployment, source health"]
    PRE --> TEST["One bounded proof attempt"]
    TEST --> WATCH{"Stop trigger / effect beyond ceiling?"}
    WATCH -- "Có" --> STOP["Stop, contain, notify, preserve minimal evidence"]
    WATCH -- "Không" --> OBS["Observe expected vs actual and side effects"]
    OBS --> ENOUGH{"Evidence đủ để kết luận?"}
    ENOUGH -- "Có" --> CLOSE["Stop further exploitation; record finding"]
    ENOUGH -- "Không" --> REVIEW["Reviewer/owner approve additional scope or INCONCLUSIVE"]
    CLOSE --> RISK["Impact/risk triage + remediation"]
    RISK --> RETEST["Retest on fixed deployment"]
    RETEST --> ASSURANCE["Assurance claim with limitations"]
~~~

### Giai đoạn A – Lập claim và kiểm tra phạm vi

- Mô tả asset, route, authorization context và security objective.
- Nêu requirement, expected behavior và bằng chứng cần có.
- Xác nhận approved RoE, scope, thời hạn và limits.
- Xác định proof level P0/P1/P2/P3 được phép; không tự tăng level nếu proof chưa đủ.
- Lập danh mục excluded operations, external targets và required emergency contacts.

### Giai đoạn B – Chuẩn bị fixture và safety controls

- Thiết lập synthetic tenants, roles, resources và reset procedure.
- Xác nhận test account không có quyền ngoài yêu cầu.
- Gắn build ID/digest, gateway version và feature flags của target.
- Chụp baseline về trạng thái test DB/queue/storage nếu có state-changing workflow.
- Xác minh logs/audit/APM/SOC có thể thấy test run ID.
- Đặt request/data/time budget và cảnh báo vượt ngưỡng.

### Giai đoạn C – Thực hiện proof tối thiểu

- Gửi **một test case được phê duyệt** với input đã chọn.
- Không tự mở rộng scan hoặc thử brute force các identifiers.
- Ghi expected vs actual behavior; kiểm side effects nếu liên quan.
- Nếu đã vượt trust boundary theo proof threshold, **dừng**.
- Nếu tool/network/session lỗi, phân loại NOT_RUN/INCONCLUSIVE, không đoán FAIL/PASS.
- Nếu có data thật hoặc stop trigger, không tiếp tục và thông báo.

### Giai đoạn D – Phân loại và báo cáo

- Confirmation: evidence có hỗ trợ hypothesis không?
- Reproducibility: có thể kiểm tra lại trên fixture mà không tăng tác động?
- Exploit prerequisites: cần quyền/điều kiện nào?
- Coverage limitations: phiên bản, endpoint, roles/tenants/regions chưa kiểm.
- Root cause: authorization, trusted boundary, config, patch hoặc business workflow.
- Risk: likelihood/exposure/impact và control effectiveness.
- Owner/remediation/acceptance/retest plan.

### Giai đoạn E – Retest và assurance

- Sửa trên source/config/identity policy phù hợp.
- Triển khai artifact mới với digest được ghi.
- Lặp **test scenario cũ**, giữ expected behavior và fixture.
- Kiểm tra có bypass đường khác hay không theo test plan.
- So sánh before/after evidence và xác minh actual runtime.
- Đóng finding khi acceptance đạt; không đóng chỉ vì scanner không báo.

## 12. Các loại weakness và phương pháp proof tối thiểu

### 12.1. Authorization và broken object-level access

**Hypothesis:** Actor A có thể đọc hoặc thao tác object B ngoài phạm vi.

**Minimum proof:** Trên lab có hai tenants giả, gửi một request tới fixture do tenant B sở hữu, quan sát deny theo policy. Nếu marker B xuất hiện, finding confirmed **trong scope đó**; không cần tìm thêm object IDs hoặc xem record thật.

**Evidence:** request ID, actor identity, object owner from fixture, expected policy, sanitized response và no-side-effect result.

**Limitations:** Không tự suy kết quả này đúng cho mọi HTTP methods, bulk endpoint, workers hoặc cache; tạo scenarios bổ sung theo risk.

### 12.2. Authentication/session

**Hypothesis:** Expired/revoked credential vẫn được ứng dụng chấp nhận.

**Minimum proof:** Dùng synthetic test token/session được IdP cấp cho test environment, đặt trạng thái expired/revoked theo fixture và gọi một endpoint vô hại.

**Evidence:** token metadata đã redacted, issuer/audience policy version, expected deny, response và audit.

**Không cần:** lấy token của user khác, đoán mật khẩu thật hoặc tạo account lockout.

### 12.3. Input handling/injection

**Hypothesis:** Input không tin cậy có thể thay đổi ý nghĩa xử lý hoặc đi qua validation.

**Minimum proof:** Static/config review, parameterization check và các test inputs **không phá hủy** trong sandbox. Nếu có test behavior bất thường, không tự tăng payload tới mức truy xuất dữ liệu, thực thi lệnh hoặc gây lỗi lớn.

**Evidence:** expected schema/validation response, sanitized error, code path hoặc effective config, reviewer finding.

**Không cần:** chạy payload thực thi tùy ý trên production để “chứng minh RCE”. Với điểm yếu có khả năng nguy hiểm cao, chứng cứ từ isolated lab và architecture review có thể đủ để yêu cầu remediation.

### 12.4. File upload và xử lý dữ liệu

**Hypothesis:** File vượt format/size/type policy hoặc được lưu ngoài tenant boundary.

**Minimum proof:** Một synthetic file định dạng kiểm thử nhỏ, upload trong sandbox với quyền đúng/sai; kiểm validation, storage key, resource owner và cleanup.

**Evidence:** fixture hash, request, response, storage metadata. Không upload nội dung độc hại hoặc tập tin phá hoại vào hệ thống thật.

### 12.5. Outbound request/SSRF boundary

**Hypothesis:** Server-side component có thể gọi destination không thuộc allowlist.

**Minimum proof:** Dùng **mock endpoint nội bộ của môi trường lab được cấp quyền**, kiểm log/correlation ở mock và egress allow/deny policies. Không gọi metadata service, cloud credentials endpoints hoặc internal targets ngoài scope.

**Evidence:** mock request ID, effective egress policy, deny/allow test, destinations thuộc allowlist.

### 12.6. Misconfiguration/IAM

**Hypothesis:** Một service identity có quyền rộng hơn requirement.

**Minimum proof:** Effective IAM policy review + authorization simulation/deny tests trên tài nguyên giả. Không cần thực hiện privileged mutation hoặc truy xuất secrets để chứng minh wildcard permissions.

**Evidence:** policy diff, test principal, simulated resource and decision, ownership mapping.

### 12.7. Business workflow

**Hypothesis:** Một user có thể bỏ qua approval/state transition.

**Minimum proof:** Tạo synthetic workflow ở trạng thái `DRAFT`, `SUBMITTED`, `APPROVED` theo fixture và thực hiện một thao tác out-of-order được phê duyệt. Quan sát expected deny và DB/job/audit.

**Evidence:** state transition matrix, event logs, side effects, retest.

### 12.8. Availability-related weakness

Nếu một giả thuyết đòi hỏi tạo tải hoặc crash để xác minh, **không mặc định thử**. Ưu tiên code/design analysis, giới hạn tài nguyên, load model và isolated performance lab. Stress/DoS production đòi RoE riêng và bảo đảm continuity; không thuộc proof mặc định.

## 13. Multi-step attack paths và giới hạn chaining

Một chuỗi có thể gồm:

~~~text
Weakness A: API tin tenant ID từ client
  -> Weakness B: export job chỉ kiểm tra lúc enqueue
  -> Weakness C: worker không kiểm lại resource ownership
  -> Potential impact: cross-tenant export

Controlled proof boundary:
  - Synthetic tenant A/B
  - One report fixture and one test job
  - No production data
  - No real credential harvesting
  - No persistence or privilege beyond scope
  - Stop once unauthorized job/file behavior is established
~~~

### 13.1. Vì sao một finding đơn lẻ đôi khi chưa đủ?

- Một endpoint có thể trả `202 Accepted` nhưng worker sau đó deny.
- Một gateway có thể deny nhưng internal service route khác vẫn reachable.
- Một user có thể đổi client-side tenant selector nhưng server query đã scope đúng.
- Header cho phép arbitrary data không đồng nghĩa backend có thể thực thi lệnh.
- Scanner có thể report outdated version nhưng vendor đã backport patch.

Nếu impact phụ thuộc bước thứ hai, có thể kiểm **trạng thái đầu ra vô hại** trong sandbox, nhưng không tự leo thang sang tài sản khác.

### 13.2. Chaining yêu cầu phê duyệt theo từng trust boundary

| Chặng | Tài sản/boundary | Bằng chứng có thể thu | Điều kiện dừng |
| --- | --- | --- | --- |
| Request từ user A | Gateway/API | Principal, route, expected policy | Nếu sai identity/scope |
| Tạo export job | API/queue | Synthetic job created/not created | Khi có proof về unauthorized action |
| Worker xử lý job | Queue/worker | Mock storage/audit event | Nếu vượt synthetic fixture |
| Download artifact | Object storage | Test object marker/access decision | Không tải real customer data |
| Privileged/admin escalation | Boundary khác | Phân tích design, separate scoped test | Không tự tiếp tục ngoài RoE |

Một proof chain bị giới hạn **không cần chạm hết mọi thành phần** nếu đã có đủ evidence xác nhận root cause/impact. Những phần chưa làm phải được ghi rõ limitations.

## 14. Risk assessment sau controlled exploitation

### 14.1. Các yếu tố cần ghi

- **Vulnerable behavior:** actual vs expected.
- **Exploit prerequisites:** anonymous/authenticated, role, configuration, user interaction.
- **Attack surface:** Internet/internal/partner, direct vs gateway, region.
- **Reachability:** path tested, path suspected, path not observed.
- **Technical impact:** confidentiality, integrity, availability; dữ liệu/privilege class.
- **Business impact:** tenant isolation, payment/report accuracy, privacy, continuity.
- **Existing controls:** authN, authZ, WAF, segmentation, logging và rate-limit.
- **Control effectiveness:** có test/monitoring evidence hay chỉ được khai báo?
- **Exploit intelligence:** có published exploit/active exploitation đáng tin không, theo thời điểm?
- **Uncertainty:** chưa test trên production, configs khác, giả định fixtures, side effects.
- **Remediation feasibility:** fix version, config/policy change, mitigating controls.

Không lấy một response bất thường rồi suy rằng attacker có thể chiếm toàn bộ hệ thống. Severity/risk phải dựa vào **bằng chứng đã đạt, preconditions và impact hợp lý**, tránh phóng đại hoặc đánh giá thấp.

### 14.2. Khi nào ghi CONFIRMED, SUSPECTED, INCONCLUSIVE?

| Kết quả | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **CONFIRMED** | Proof cho thấy behavior sai theo acceptance trong scope | Synthetic marker B được user A nhận |
| **SUSPECTED** | Có tín hiệu nhưng chưa đủ xác minh | Scanner rule báo endpoint có pattern rủi ro |
| **FALSE_POSITIVE** | Nhận định ban đầu không đúng theo evidence | WAF response tưởng là app error |
| **NOT_APPLICABLE** | Preconditions không có trong scope đã chứng minh | Feature đã tắt và không reachable trong deployment |
| **MITIGATED** | Control đã giảm risk, weakness có thể vẫn còn | Route disabled và bypass tests đạt |
| **FIXED_AWAITING_RETEST** | Code/config đã sửa nhưng runtime chưa verify | PR merge chưa deploy |
| **VERIFIED_CLOSED** | Bản sửa đã triển khai và test lại đạt | Negative test trước đó FAIL nay PASS |
| **INCONCLUSIVE** | Thiếu authorization, fixture, runtime hoặc evidence | Test aborted khi session mất |
| **NOT_RUN** | Không thực thi kiểm chứng | Out-of-scope hoặc chưa được duyệt |

Ngoại lệ/risk acceptance là quyết định quản trị riêng, không biến finding CONFIRMED thành FIXED.

### 14.3. Kết luận có thể chỉ là “không xác định”

Nếu RoE không cho phép tiếp tục và P0/P1 không đủ chứng minh exploitability, hãy ghi **INCONCLUSIVE** với những gì đã biết:
- Vulnerable version/unsafe config có evidence.
- Có preconditions hoặc paths chưa kiểm.
- Vì safety, chưa thực hiện active proof.
- Risk vẫn được assessed theo best available evidence.
- Đề xuất remediation/compensating controls hoặc request mở rộng test trong lab.

Không mạo hiểm hệ thống thật chỉ để thay một từ “suspected” thành “confirmed”.

## 15. Java 17: policy kiểm soát truy cập tài nguyên đa tenant

Ví dụ phục vụ **test fixture**, không phải exploit để dùng trên hệ thống bên ngoài. Một service báo cáo cần kiểm server-side ownership, permission và trạng thái tài khoản **trước khi** đọc dữ liệu hoặc enqueue job.

### 15.1. Authorization policy tối giản

~~~java
import java.util.Objects;
import java.util.Set;

public final class ReportAccessPolicy {

    public record Principal(
            String userId,
            String tenantId,
            boolean active,
            Set<String> permissions) {}

    public record Report(
            String reportId,
            String ownerTenantId,
            String ownerUserId,
            boolean deleted) {}

    public enum Decision {
        ALLOW, DENY
    }

    public Decision mayRead(Principal principal, Report report) {
        if (principal == null || report == null
                || !principal.active() || report.deleted()
                || blank(principal.userId())
                || blank(principal.tenantId())
                || blank(report.reportId())
                || blank(report.ownerTenantId())
                || principal.permissions() == null) {
            return Decision.DENY;
        }

        if (!principal.permissions().contains("report:read")) {
            return Decision.DENY;
        }

        if (!Objects.equals(principal.tenantId(),
                report.ownerTenantId())) {
            return Decision.DENY;
        }

        // Ví dụ policy: tenant match chưa đủ;
        // chính owner của report mới được đọc.
        if (!Objects.equals(principal.userId(),
                report.ownerUserId())) {
            return Decision.DENY;
        }

        return Decision.ALLOW;
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

### 15.2. Những điểm cần hiểu

- Permission `report:read` **không thay** object ownership.
- Tenant từ client header/path **không được tin** để quyết định quyền; `Principal` phải lấy từ authentication đã được kiểm chứng.
- Nếu policy có delegated access/support case, phải bổ sung điều kiện riêng **có expiry, approval và audit**, không thêm một role bypass vô hạn.
- Đoạn code chỉ quyết định authorization; **data query cũng phải scope đúng** để tránh SQL/result cache leak.
- Authorization phải được enforce trước mutation, queue enqueue hoặc signed URL generation.
- Denied operation không được tạo hidden side effects.
- Ứng dụng thực tế cần kiểm revocation/session lifetime, data classification, service identity và race conditions.
- `Principal.permissions()` phải đến từ trust source được kiểm, không client-supplied string.

### 15.3. Positive/negative tests bằng JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Set;
import org.junit.jupiter.api.Test;

class ReportAccessPolicyTest {

    private final ReportAccessPolicy policy = new ReportAccessPolicy();

    private final ReportAccessPolicy.Report reportA =
            new ReportAccessPolicy.Report(
                    "report-a", "tenant-A", "user-a", false);

    private ReportAccessPolicy.Principal user(
            String id, String tenant, boolean active,
            String... permissions) {
        return new ReportAccessPolicy.Principal(
                id, tenant, active, Set.of(permissions));
    }

    @Test
    void ownerWithPermissionCanReadOwnReport() {
        var p = user("user-a", "tenant-A", true, "report:read");
        assertEquals(ReportAccessPolicy.Decision.ALLOW,
                policy.mayRead(p, reportA));
    }

    @Test
    void crossTenantUserCannotReadSyntheticReport() {
        var p = user("user-b", "tenant-B", true, "report:read");
        assertEquals(ReportAccessPolicy.Decision.DENY,
                policy.mayRead(p, reportA));
    }

    @Test
    void sameTenantButDifferentOwnerIsDeniedInThisPolicy() {
        var p = user("user-other", "tenant-A", true, "report:read");
        assertEquals(ReportAccessPolicy.Decision.DENY,
                policy.mayRead(p, reportA));
    }

    @Test
    void permissionMissingDeniesEvenSameOwner() {
        var p = user("user-a", "tenant-A", true);
        assertEquals(ReportAccessPolicy.Decision.DENY,
                policy.mayRead(p, reportA));
    }

    @Test
    void inactiveAccountCannotRead() {
        var p = user("user-a", "tenant-A", false, "report:read");
        assertEquals(ReportAccessPolicy.Decision.DENY,
                policy.mayRead(p, reportA));
    }

    @Test
    void nullPrincipalMustDeny() {
        assertEquals(ReportAccessPolicy.Decision.DENY,
                policy.mayRead(null, reportA));
    }
}
~~~

Các tests thể hiện **control mong đợi**, không mô phỏng việc truy cập trái phép vào một website ngoài scope và không tự chứng minh API/web/worker thực đã áp policy. Cần integration tests với authenticated endpoint và dữ liệu test để kiểm runtime behavior.

## 16. Spring Boot/MockMvc: test negative case trên synthetic fixtures

Mục tiêu: xác minh rằng API endpoint gọi đúng policy và không làm lộ report B. Dùng Spring Security Test với test JWT **trong test runner**, không thu thập token thật.

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ControlledTenantBoundaryTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void approvedFixtureOwnerCanReadReportA() throws Exception {
        mockMvc.perform(get("/api/reports/{id}", "report-a")
                .with(jwt()
                        .jwt(t -> t.subject("user-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reportId").value("report-a"));
    }

    @Test
    void userAIsDeniedForSyntheticReportB() throws Exception {
        mockMvc.perform(get("/api/reports/{id}",
                        "report-b-synthetic")
                .with(jwt()
                        .jwt(t -> t.subject("user-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void spoofedTenantHeaderDoesNotGrantAccess() throws Exception {
        mockMvc.perform(get("/api/reports/{id}",
                        "report-b-synthetic")
                .header("X-Tenant-ID", "tenant-B")
                .with(jwt()
                        .jwt(t -> t.subject("user-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn thực tế cần ghi trong bài kiểm chứng:**
- Đây là test code minh họa cho **application có controller, security config và fixtures phù hợp**; không phải chương trình Spring Boot chạy độc lập.
- `jwt()` của MockMvc tạo test authentication; nó **không chứng minh** JWT signature/issuer/audience được xác minh như tại gateway/production IdP. Cần một nhóm integration token-validation tests khác.
- Status `403` minh họa policy; một ứng dụng có thể dùng `404` để không tiết lộ object existence. Acceptance criteria cần thống nhất trước.
- Phải tạo fixture report A/B đúng owner; nếu ID không tồn tại, denial có thể đến từ `404 not found`, gây false proof.
- Cần thêm test với `export-worker`/queue, cache, DB side effects và signed URLs nếu claim bao gồm những trust boundaries này.
- Một PASS của MockMvc **không đủ chứng minh production** đã triển khai đúng policy/configuration/release.
- Các test không nên ghi raw JWT hoặc nội dung customer data vào CI artifact.

## 17. Security requirements dành cho controlled exploitation

Những ID dưới đây là **ví dụ đào tạo**, không phải điều khoản của một chuẩn bên ngoài. Yêu cầu thật phải gắn vào asset, risk, security objectives và approved policy của từng tổ chức.

| ID | Requirement có thể kiểm chứng | Acceptance evidence |
| --- | --- | --- |
| **CE-REQ-01** | Mọi hoạt động khai thác phải có authorization/RoE hợp lệ đúng asset, thời gian và loại test | Engagement approval + current scope |
| **CE-REQ-02** | Mỗi scenario phải có hypothesis, expected behavior, proof level và stop boundary trước khi chạy | Signed/reviewed test plan |
| **CE-REQ-03** | Ưu tiên dùng non-invasive proof và synthetic fixtures; không truy xuất dữ liệu thật khi không cần | Fixture inventory + data handling record |
| **CE-REQ-04** | Scanner/test runner không được tự theo redirect, host, tenant hoặc resource ngoài scope | Scope negative tests |
| **CE-REQ-05** | Tác vụ state-changing phải có approved rollback/cleanup/side-effect observation | State baseline, cleanup evidence |
| **CE-REQ-06** | Proof attempt phải giới hạn rate, duration, record count và tác động theo ceiling | Limits/monitoring logs |
| **CE-REQ-07** | Stop triggers phải có khả năng ngắt run và escalation tới on-call | Runbook + stop drill |
| **CE-REQ-08** | Không được dùng real secrets/PII ngoài scope làm bằng chứng; evidence phải sanitized | Data-handling/redaction tests |
| **CE-REQ-09** | Negative authorization phải kiểm role/tenant/resource với fixture rõ owner | Persona matrix + deny test |
| **CE-REQ-10** | Denied operations không được tạo unauthorized DB/queue/storage side effects | Integration side-effect observations |
| **CE-REQ-11** | Scanner/tool/runner failure, session loss và scope mismatch phải phân loại NOT_RUN/INCONCLUSIVE | Failure-injection tests |
| **CE-REQ-12** | Findings phải ghi preconditions, proof, impact, confidence và limitations, không phóng đại | Reviewed finding record |
| **CE-REQ-13** | Evidence phải gắn deployment/commit/digest, role, test ID, timestamp và reviewer | Evidence register |
| **CE-REQ-14** | Confirmed high-risk finding phải có owner, treatment và remediation target theo policy | Finding/backlog record |
| **CE-REQ-15** | Risk acceptance/exception phải có authority, scope, expiry và monitoring; không biến technical finding thành fixed | Exception review |
| **CE-REQ-16** | Retest phải lặp scenario failure trên đúng fixed artifact/runtime, gồm side effects khi cần | Before/after result |
| **CE-REQ-17** | Engagement phải có recovery và incident handoff nếu test gây unexpected impact | Incident runbook/record |
| **CE-REQ-18** | Độ bao phủ phải báo riêng tested/not-run/blocked/inconclusive theo risk scenarios | Coverage report |
| **CE-REQ-19** | Mọi access đối với evidence nhạy cảm phải tuân data classification, retention và audit | Evidence access review |
| **CE-REQ-20** | Source/route, identity policy, CI/deployment, threat intelligence thay đổi phải kích hoạt reassessment | Change-trigger history |
| **CE-REQ-21** | Một proof đủ không được tiếp tục privilege escalation hoặc exfiltration ngoài RoE | Test-step audit + stop reason |
| **CE-REQ-22** | Đánh giá phải tách technical observation, inferred impact và accepted residual risk | Assessor sign-off |
| **CE-REQ-23** | PoC từ vendor/public advisory chỉ được đánh giá trong môi trường được cấp phép và với safety assessment | Approved technique review |
| **CE-REQ-24** | Khả năng scan/control thất bại không được tạo “security PASS” giả | Negative quality-gate tests |

### Ví dụ traceability

~~~text
RISK CE-R01:
  Customer of tenant A may read report of tenant B
  -> OBJECTIVE: Confidentiality / tenant isolation
  -> REQUIREMENT: CE-REQ-09 + CE-REQ-10
  -> CONTROL: Server-side resource authorization + scoped data query
  -> SCENARIO: User A accesses report-b-synthetic in staging
  -> PROOF CEILING: One synthetic marker, no real data
  -> TEST: Negative API request + DB/queue side-effect check
  -> EVIDENCE: Persona, fixture, sanitized response, run ID, digest
  -> FINDING: Unauthorized synthetic marker received, if observed
  -> REMEDIATION: Ownership check and data query scoping
  -> RETEST: Same fixture against fixed deployed artifact
  -> ASSURANCE: Scoped PASS/FAIL/INCONCLUSIVE with limitations
~~~

Security assurance không chỉ quan tâm PoC có “chạy được” mà còn đánh giá **quy trình thử có an toàn, kết luận có hợp lý và evidence có tái kiểm tra được** hay không.

## 18. Test plan: positive, negative và failure scenarios

Bộ test dưới đây là **kế hoạch tham khảo**, không phải bằng chứng đã thực thi. Những scenarios có rủi ro vận hành cần chạy trong isolated lab/sandbox hoặc được loại khỏi scope production.

| Test ID | Tình huống | Expected result |
| --- | --- | --- |
| **CE-T01** | Không có authorization | Không thực hiện proof |
| **CE-T02** | Authorization hết hạn | Dừng, xin approval mới |
| **CE-T03** | Target host/route ngoài scope | Runner/test bị chặn |
| **CE-T04** | Redirect tới domain bên thứ ba | Không tự theo |
| **CE-T05** | Test account sai tenant hoặc role | Dừng, điều chỉnh fixture |
| **CE-T06** | Synthetic resource thuộc đúng owner | Positive scenario được allow theo policy |
| **CE-T07** | User A đọc synthetic report B | Deny, không marker của B |
| **CE-T08** | Client spoof `X-Tenant-ID` | Không mở rộng quyền |
| **CE-T09** | Cùng tenant nhưng owner khác | Kết quả theo object-level policy |
| **CE-T10** | Role revoked trong fixture | Deny trong window yêu cầu |
| **CE-T11** | Support case hết hạn | Deny, audit event |
| **CE-T12** | API deny export của report B | Không tạo job/file |
| **CE-T13** | Async worker nhận job không hợp lệ | Từ chối/contain theo policy |
| **CE-T14** | Signed test file URL hết hạn | Không truy cập được |
| **CE-T15** | Một state-changing lab test có rollback | Fixture trở về baseline và có audit |
| **CE-T16** | Request budget đạt giới hạn | Runner dừng |
| **CE-T17** | Tool timeout/crash | INCONCLUSIVE/NOT_RUN, không PASS |
| **CE-T18** | Monitoring source down | Dừng/escalate theo RoE |
| **CE-T19** | Session token expired giữa run | Test không tự thành PASS |
| **CE-T20** | Response vô tình chứa data thật | Stop, protect evidence, notify |
| **CE-T21** | Worker tạo job/email ngoài sandbox | Stop/recover theo runbook |
| **CE-T22** | Một harmless marker xác nhận boundary violation | Dừng proof, ghi confirmed finding |
| **CE-T23** | PoC muốn tăng level từ P1 lên P3 | Cần review/authorization riêng |
| **CE-T24** | Scanner finding false positive sau validation | Có rationale/evidence/reviewer |
| **CE-T25** | Vulnerable version present nhưng route không reachable trong scope | Ghi risk/uncertainty, không tự tuyên bố fixed |
| **CE-T26** | Test PASS staging, production dùng digest khác | Không suy kết quả sang production |
| **CE-T27** | Finding fixed trong PR nhưng chưa deploy | Không VERIFIED_CLOSED |
| **CE-T28** | Fixed artifact, retest same negative case đạt | Có thể VERIFIED_CLOSED theo scope |
| **CE-T29** | Exception approved nhưng chưa fix | Finding vẫn open/mitigated |
| **CE-T30** | Exception expired/revoked | Không dùng để vượt policy |
| **CE-T31** | Evidence thiếu deployment/identity/time | INCONCLUSIVE |
| **CE-T32** | Test report chứa credential/token | Evidence hygiene failure |
| **CE-T33** | Partial lab proof không xác minh được production assumptions | Claim giới hạn, uncertainty rõ |
| **CE-T34** | Public exploit PoC có behavior ngoài RoE | Không chạy, thay bằng safe verification |
| **CE-T35** | Không có side effects nhưng HTTP deny sai | Finding theo acceptance, cần review response |
| **CE-T36** | Response 403 nhưng job đã enqueue trước deny | FAIL authZ/side-effect requirement |
| **CE-T37** | Một route được fix, legacy route vẫn vulnerable | Không đóng claim toàn service |
| **CE-T38** | Rollback về vulnerable artifact sau retest | Reopen finding/reassess |
| **CE-T39** | Emergency stop trigger khi 5xx/latency tăng | Dừng và báo on-call |
| **CE-T40** | RoE cấm data exfiltration nhưng PoC đòi đọc dữ liệu | Chọn safe alternative hoặc INCONCLUSIVE |

### 18.1. Test tiers

- **Static/design evidence:** control logic, IAM policy, gateway scope, threat model.
- **Unit:** authorization decision và edge cases.
- **Integration:** API + database/queue/storage fixture.
- **Dynamic non-invasive:** safe request/response/negative tests.
- **Bounded proof:** synthetic marker một lần, trong lab được phép.
- **Operational:** stop/rollback/source-health drills.
- **Release/retest:** actual artifact, configuration và deployment binding.
- **Governance:** authorization, approval, retention và exception policy.

Không mặc định “càng nhiều payload càng tốt”. Đo **chất lượng bằng chứng của từng requirement**, không đếm số lượng request hay số tool đã chạy.

## 19. Mẫu hồ sơ controlled exploitation và evidence register

### 19.1. YAML record minh họa

Tất cả giá trị `<...>` là placeholder. Những trạng thái/timestamps trong ví dụ **không phải kết quả thực nghiệm**.

~~~yaml
engagement_id: PENTEST-EXPLOIT-007
module: SECURITY_SECURITY_ASSURANCE
topic: Khai thác có kiểm soát
assessment:
  status: PLANNED
  reviewer: "<APPROVED_ASSESSOR>"
  assessed_at: "<ISO_8601_UTC>"
  objectives: ["tenant-isolation", "report-confidentiality"]
  risk_ids: ["CE-R01"]
  requirement_ids: ["CE-REQ-09", "CE-REQ-10"]
authorization:
  approval_ref: "<ENGAGEMENT_AUTHORIZATION>"
  system_owner: "<ASSET_OWNER>"
  risk_owner: "<RISK_OWNER>"
  tester_identity: "<AUTHORIZED_TESTER>"
  approved_window:
    starts_at: "<ISO_8601_UTC>"
    expires_at: "<ISO_8601_UTC>"
  allowed_targets:
    - "https://staging.example.test/api/reports/{id}"
  excluded_targets:
    - "<PRODUCTION_OR_THIRD_PARTY_HOSTS>"
  allowed_methods: ["GET"]
  excluded_operations:
    - "real-customer-data-access"
    - "credential-extraction"
    - "persistence"
    - "resource-exhaustion"
  proof_ceiling:
    level: P2_SYNTHETIC_BOUNDARY
    max_requests: 5
    max_synthetic_records: 1
    no_bulk_export: true
  monitor_ref: "<APP_HEALTH_AND_AUDIT_DASHBOARD>"
  stop_runbook_ref: "<EMERGENCY_STOP>"
  recovery_ref: "<FIXTURE_CLEANUP_AND_RESTORE>"
target:
  environment: isolated-staging
  region: "<REGION>"
  service: report-api
  route: "GET /api/reports/{id}"
  source_commit: "<SOURCE_COMMIT>"
  deployment_id: "<DEPLOYMENT_ID>"
  artifact_digest: "<IMAGE_OR_JAR_DIGEST>"
  gateway_config_ref: "<POLICY_VERSION>"
scenario:
  id: CE-T07
  actor_ref: "test-user-tenant-A"
  fixture_ref: "report-b-synthetic"
  expected: "DENY_WITHOUT_SYNTHETIC_MARKER"
  threat_scenario: "<CROSS_TENANT_ACCESS_PATH>"
  proof_method: "single approved synthetic request"
  preconditions_ref: "<TEST_ACCOUNT_AND_FIXTURE_VALIDATION>"
execution:
  run_id: "<TEST_RUN_ID>"
  started_at: "<ISO_8601_UTC>"
  finished_at: "<ISO_8601_UTC>"
  tool_and_version: "<TEST_RUNNER_VERSION>"
  session_health_ref: "<AUTHENTICATION_SENTINEL>"
  requests_sent: "<COUNT>"
  stop_reason: "<PROOF_ACHIEVED_OR_SAFETY_ABORT>"
observations:
  sanitized_request_ref: "<REDACTED_REQUEST>"
  sanitized_response_ref: "<REDACTED_RESPONSE>"
  data_side_effect_ref: "<TEST_DB_CHECK>"
  queue_side_effect_ref: "<TEST_JOB_CHECK>"
  audit_event_ref: "<CORRELATED_AUDIT_EVENT>"
  evidence_integrity_ref: "<HASH_OR_PROTECTED_STORE_REF>"
  observed_behavior: "<OBSERVED_ONLY>"
result:
  technical_status: "<CONFIRMED_FAIL_PASS_INCONCLUSIVE>"
  confidence: "<JUSTIFIED_CONFIDENCE>"
  impact_assessment_ref: "<RISK_RATIONALE>"
  limitations:
    - "<UNTESTED_METHODS_OR_DEPLOYMENTS>"
    - "<LIMITED_TO_SYNTHETIC_FIXTURE>"
  finding_ref: "<FINDING_ID_IF_ANY>"
  remediation_owner: "<TEAM_OWNER>"
  retest_ref: "<RETEST_ID_IF_ANY>"
  exception_ref: "<APPROVED_EXCEPTION_IF_APPLICABLE>"
security_and_privacy:
  secret_redaction_checked: "<TRUE_OR_FALSE>"
  retention_policy_ref: "<POLICY>"
  evidence_access_group: "<RESTRICTED_AUDIENCE>"
reassessment_triggers:
  - "API/object authorization policy changed"
  - "New route, tenant, service or deployment added"
  - "Identity/workload permissions or queue handling changed"
  - "Finding fixed, regression suspected or incident raised"
~~~

### 19.2. Điều làm evidence register đáng tin

- Phân biệt **authorization scope** với **execution scope**.
- Giữ technical result tách khỏi risk decision và exception.
- Liên kết evidence tới **đúng deployed artifact/digest**.
- Nêu proof ceiling và stop reason để đánh giá thử nghiệm có vượt hạn không.
- Có expected behavior được xác định trước.
- Ghi actual observed behavior và side effects, tránh viết conclusion như observation.
- Có reviewer/approval, evidence retention và source health.
- Có limitations để người đọc không suy quá phạm vi.

### 19.3. Một finding report có thể tái hiện

~~~text
Finding: CE-FIND-007
Title: Cross-tenant report read authorization failure
Affected scope: report-api / staging / deployment D
Threat actor: authenticated test user in tenant A
Prerequisite: one synthetic report in tenant B
Expected: deny and no tenant-B marker
Observed: synthetic marker B in the authorized test response
Proof ceiling: one fixture record, 1 request, no real customer data
Evidence: sanitized request/response, audit ID, fixture ownership
Impact rationale: tenant confidentiality boundary failure for tested path
Uncertainty: API versions, other methods, prod configs not tested
Owner: report-api team
Remediation: enforce resource ownership via trusted principal
Retest: same fixture after fixed artifact deployment
Decision: CONFIRMED in staging; not universal production claim
~~~

Đây chỉ là **mẫu minh họa**, không phải một incident đã diễn ra.

## 20. Báo cáo findings, severity và thứ tự ưu tiên

### 20.1. Cấu trúc finding

| Trường | Ví dụ nội dung |
| --- | --- |
| Title | Mô tả weakness và impacted boundary, không giật gân |
| Scope | Asset/route/method/role/region/deployment |
| Preconditions | Identity, access, config và fixture |
| Expected security requirement | Trách nhiệm của control cụ thể |
| Observed behavior | Điều tester thấy, không phải suy diễn |
| Minimum proof | Marker/side-effect test trong RoE |
| Technical impact | Đường dữ liệu/quyền/tài sản có thể bị ảnh hưởng |
| Business impact | Confidentiality, integrity, availability và risk context |
| Likelihood/exploitability | Prerequisites, exposure và relevant intelligence |
| Existing controls | Các controls được verified, không chỉ khai báo |
| Evidence | Sanitized request/response, logs, policy/deploy IDs |
| Limitations | Paths, versions, regions chưa test |
| Fix guidance | Requirement/control behavior cần đạt |
| Retest | Kế hoạch và acceptance criteria |
| Owner/priority | Người chịu trách nhiệm và target theo policy |

### 20.2. Không phóng đại exploit impact

**Chưa phù hợp:** “Đã chiếm quyền toàn bộ tổ chức” khi tester chỉ chứng minh một endpoint trả một synthetic record của tenant khác trong staging.

**Phù hợp hơn:** “Trong staging deployment D và route GET cụ thể, một customer identity thuộc tenant A nhận được synthetic marker của tenant B; đây là lỗi kiểm soát quyền theo object/tenant trong phạm vi test. Các routes khác và production cần đánh giá/kiểm chứng riêng.”

Risk vẫn có thể cao do asset criticality/affected design, nhưng **claim phải phân biệt observed và inferred**.

### 20.3. Root cause và risk treatment

Remediation có thể gồm:
- Server-side object/tenant authorization.
- Trusted claims validation, scoped DB queries và deny-by-default.
- Worker/job authorization checks và signed URL scope.
- Feature disable, network isolation, rate limiting hoặc monitoring như temporary mitigations.
- Least-privilege policies cho service identity.
- Security tests trong CI và release guardrails.
- Đánh giá toàn bộ routes/versions/callers cùng shared root cause.
- Exception/risk acceptance có hạn nếu chưa sửa được, với owner và monitoring.

Không gọi một WAF rule hoặc approved exception là “fixed” nếu weakness vẫn còn bên dưới.

## 21. Retest: từ proof thất bại tới bằng chứng fix

### 21.1. Retest cần lặp cái gì?

- Cùng security requirement, actor và trust boundary.
- Cùng fixture ownership và expected deny/allow.
- Đúng source commit, artifact/build digest và deployed instance.
- Cùng request method/route và relevant configuration.
- Backend side effects: DB/queue/storage/audit khi root cause có liên quan.
- Negative cases: wrong tenant/role/expired delegation/spoofed headers.
- Positive cases: owner hợp lệ vẫn sử dụng chức năng bình thường.
- Regressions: legacy endpoint, worker, role mới, cache, delegation.

### 21.2. Khi nào có thể đóng finding?

1. Vulnerable behavior đã được xác định đúng.
2. Fix triển khai trên **actual target** thuộc claim.
3. Retest original failure scenario đạt.
4. Không phát sinh undesired side effects.
5. Có evidence fresh và liên kết deployment.
6. Reviewer xác minh kết luận.
7. Các related paths hoặc residual gaps được ghi và quản lý.

**Không đủ:** PR merge, unit tests pass, scanner không tìm thấy alert trong một scan có session lỗi, WAF block scanner, hoặc chỉ có screenshot từ một version không rõ.

### 21.3. Khi chưa thể sửa

Nếu remediation cần thời gian:
- Hạn chế exposure/disable feature theo owner decision nếu được phép.
- Thiết kế compensating controls có **bypass tests** và monitoring.
- Đánh giá residual risk, uncertainty và obligations.
- Risk owner phê duyệt ngoại lệ có scope/time/expiry và exit plan nếu policy cho phép.
- Giữ finding open/mitigated; không tự đổi thành VERIFIED_CLOSED.
- Tái đánh giá ngay khi control fail, exploit intelligence tăng hoặc deployment đổi.

### 21.4. Reopen sau regression

Nếu rollback hoặc thay configuration khiến behavior xuất hiện lại:
- Tạo current finding/incident reference liên kết lịch sử.
- Thu thập actual-state evidence và affected deployments.
- Điều chỉnh release gate/regression tests.
- Không giữ trạng thái fixed chỉ vì phiên bản trước từng PASS.
- Đưa thay đổi trust boundary vào re-assessment triggers.

## 22. Metrics đánh giá chất lượng controlled exploitation

Không tối ưu theo số exploit thành công. Một engagement tốt tập trung **evidence quality, risk coverage và safety**.

| Metric | Câu hỏi | Cảnh báo |
| --- | --- | --- |
| Authorized scenario coverage | Bao nhiêu approved scenarios đã thực thi? | Không biết expected population |
| Proof threshold adherence | Bao nhiêu tests dừng đúng mức? | Vượt ceiling vì tò mò |
| High-risk scenario verification | Critical paths có evidence đạt? | Bỏ sót authZ/tenant boundaries |
| Inconclusive rate | Có nhiều tests thiếu session/scope/data? | Tool/policy readiness thấp |
| Evidence completeness | Có expected/actual/deploy/time/reviewer? | Claim khó kiểm tra lại |
| Data hygiene | Có raw secrets/PII trong report? | Pentest tự tạo privacy risk |
| Operational safety | Có stop/rollback/incident events? | Không thấy logs không đồng nghĩa an toàn |
| Finding reproducibility | Reviewer có kiểm chứng bằng fixture? | Flaky/unsupported assertions |
| Remediation-to-retest time | Bao lâu xác nhận fix? | Finding kéo dài không owner |
| Recurrence after fix | Same weakness tái xuất hiện? | Control design chưa triệt để |
| Exception hygiene | Active/expired/renewed đúng authority? | Ngoại lệ che technical debt |
| Scope changes | Engagement/release assumptions bị thay đổi? | Dùng evidence cũ sai version |

### 22.1. Coverage không phải “đã chạy 1.000 requests”

Định nghĩa một obligation theo:
`(risk scenario, asset, entry point, role/tenant context, proof threshold, deployment)`.

Kết quả nên là:
- **VERIFIED_PASS:** control được kiểm chứng đúng trong scope.
- **CONFIRMED_FAIL:** behavior không đạt expectation; có evidence.
- **INCONCLUSIVE:** dữ liệu/test không đủ, hoặc dừng vì safety.
- **NOT_RUN:** chưa thực hiện do scope/authorization/tài nguyên.
- **EXCLUDED_APPROVED:** có rationale scope và owner; không tính PASS.
- **STALE:** evidence của bản cũ/identity/route đã đổi.

#### Ví dụ

Một engagement có 20 eligible scenarios:
- 9 VERIFIED_PASS.
- 4 CONFIRMED_FAIL.
- 3 INCONCLUSIVE.
- 2 NOT_RUN.
- 2 STALE.

~~~text
Valid executed = 9 + 4 = 13
Execution coverage = 13 / 20 × 100 = 65%
Assurance PASS coverage = 9 / 20 × 100 = 45%
Confirmed failures = 4
Unresolved/untested/stale = 7
~~~

Tỷ lệ **65% executed** không phải tỷ lệ secure. Nếu một trong 4 FAIL là critical cross-tenant disclosure, release cần xử lý theo risk policy dù 9 scenarios khác PASS. Nếu inventory không đầy đủ, cả hai tỷ lệ có **denominator limitations**.

## 23. Case study 1 – Chứng minh lỗi cross-tenant export trong sandbox

### 23.1. Bối cảnh

Một nền tảng báo cáo dùng Java/Spring Boot, PostgreSQL, Kafka và object storage. User thuộc tenant có thể request export báo cáo. Application có hai endpoints:
- `GET /api/reports/{id}` trả dữ liệu báo cáo.
- `POST /api/reports/{id}/export` tạo async export job.

Một penetration test trước đó ghi nhận: khi user A gọi export report B, API có thể trả `202 Accepted`. Chưa rõ worker có thực sự tạo file hay phát hiện quyền sai. Do hệ thống chứa dữ liệu tài chính, hệ thống chỉ cho phép xác minh trên **staging, synthetic test accounts và synthetic reports**.

### 23.2. Approved scope

~~~yaml
engagement: CE-REPORT-001
environment: staging
allowed_test_resources:
  - tenant-A/test-user-a
  - tenant-B/report-b-synthetic
  - staging-queue/export-test
  - staging-bucket/synthetic-only
allowed_actions:
  - one approved cross-tenant export request
  - observe test-job creation status
  - inspect synthetic-only storage marker
proof_level: P2_SYNTHETIC_BOUNDARY
excluded:
  - production tenant data
  - bulk exports
  - privileged admin actions
  - any third-party callback
stop_when:
  - synthetic unauthorized job or file is observed
  - unexpected real data/credential appears
  - service health degrades
~~~

Đây là minh họa RoE; một record thật phải có approver, timestamps, contact, request budget và reference tới chính sách.

### 23.3. Threat hypothesis và acceptance

**Hypothesis:** API/worker không kiểm tra quyền sở hữu report tại đủ các trust boundaries, nên user A có thể khiến worker xuất file của tenant B.

**Expected behavior:**
- Wrong-tenant request bị deny theo policy (ví dụ `403` hoặc `404`).
- Không tạo export job cho report B.
- Không sinh signed download URL cho tài sản của tenant B.
- Không ghi file B vào storage accessible bởi A.
- Audit event ghi attempt và identity/scope mà không lộ secret.

**Minimum proof:** một test request với synthetic report B; không cần download dữ liệu thật, không cần enumerate reports.

### 23.4. Evidence cần lấy trước test

- Fixture owner mapping: user A/tenant A và report B/tenant B.
- Authentication test session hiện hành, không chứa secret trong report.
- Artifact digest/deployment ID, route version và gateway configuration.
- Baseline queue/storage state, request budget và test ID.
- Logs/correlation ID để phân biệt event của test.
- Effective worker identity/IAM scope nếu liên quan.

### 23.5. Các kết quả có thể xảy ra

| Quan sát | Diễn giải | Bước tiếp |
| --- | --- | --- |
| API deny và không có job/file | Control đạt tại path test | Ghi PASS theo scope |
| API trả 202 nhưng worker deny, không file | API contract có thể sai nhưng end-to-end confidentiality chưa bị phá ở path đó | Review requirement/abuse và event evidence |
| API trả 202 và job tạo file chứa marker B | Confirmed cross-tenant export impact trong sandbox | Dừng, preserve minimal evidence, finding |
| API trả 202 nhưng không thể kiểm worker/queue | INCONCLUSIVE về end-to-end impact | Bổ sung observability/approved check |
| API trả dữ liệu thật ngoài fixture | Safety stop, incident/data procedure | Không mở rộng kiểm thử |
| User A session expired, trả 401 | Chưa test authorization đúng persona | Renew fixture/session; không coi PASS |

### 23.6. Remediation với defense in depth

- API kiểm server-side principal/resource ownership trước enqueue.
- Query lấy report bắt buộc scope theo tenant/owner.
- Job chứa resource identity và authorization context có trust boundary rõ; không tin client-supplied fields.
- Worker thực thi chính sách phù hợp, nhất là nếu quyền có thể bị revoke trước lúc job chạy.
- Object storage prefix và signed URL bind đúng tenant/resource/time.
- Audit/telemetry cho denied access và suspicious export behavior.
- Add regression tests cho v1/v2, role, tenant, worker và download.
- Review IAM policy để worker không có quyền rộng ngoài yêu cầu.

### 23.7. Retest và kết luận

Retest trên deployment mới:
1. Validate fixture/report B còn tồn tại.
2. Positive test A→A vẫn hoạt động.
3. Negative A→B bị deny đúng policy.
4. Queue không có unauthorized job B.
5. Object storage không có export file B sinh ra từ attempt.
6. Worker/audit event đúng scope và không chứa secret.
7. Retest với revoked access/legacy route nếu trong remediation claim.
8. Reviewer xác nhận old failure không tái hiện.

**Scoped claim phù hợp:** “Trên staging release digest D, các fixture scenarios A→A và A→B qua API export cùng observed async paths đáp ứng acceptance. Production region khác hoặc integrations chưa kiểm được ghi limitations.” Không suy ngay “mọi cross-tenant vulnerability đã hết”.

## 24. Case study 2 – SSRF boundary proof dùng mock destination

### 24.1. Bối cảnh

Một ứng dụng có chức năng fetch metadata từ URL do user nhập. Threat model lo ngại server-side HTTP client có thể gọi đến network destination không được duyệt. Hệ thống production có internal services và cloud metadata endpoints; pentest **không** được phép tiếp cận những đích đó.

### 24.2. Test plan được phê duyệt

- Tạo **hai endpoints giả lập trong isolated lab**:
  - `allowed-mock` nằm trong approved destination allowlist.
  - `blocked-mock` là endpoint test **không thuộc allowlist** nhưng vẫn thuộc lab được cấp quyền.
- Gắn correlation ID, không truyền secrets.
- Cấu hình ứng dụng chạy bằng service identity hạn chế, không có production credentials.
- Ghi effective egress/IAM policy và DNS behavior trong lab.
- Chỉ kiểm allow/deny và log tại mocks; không sử dụng internet/production internal targets.
- Dừng sau một allow/deny proof, không scan IP ranges.

### 24.3. Acceptance criteria

| Scenario | Expected | Evidence |
| --- | --- | --- |
| Application fetch approved mock URL | Allow trong budget | Mock request log + API result |
| Application fetch blocked mock URL | Deny trước kết nối hoặc egress policy block | API decision + blocked mock no-hit |
| Client cố thay hostname/redirect ngoài policy | Policy giữ ranh giới | Effective URL/redirect validation test |
| DNS resolution thay địa chỉ trong lab | Control không tin string-only allowlist | Resolved-destination policy result |
| HTTP client timeout/malformed input | Fail safely, không secret leak | Error handling và resource limits |
| Outbound request vô tình hướng production | Safety abort | Incident/stop record |

### 24.4. Diễn giải kết quả

Nếu blocked mock nhận request, finding có thể là “egress destination policy không enforce theo approved test”. Nó **chưa chứng minh** hệ thống đã truy xuất internal metadata secrets. Tác động tiềm tàng phải đánh giá từ architecture, privileges, data classification và reachable network **mà không gọi những đích nhạy cảm**.

### 24.5. Remediation

- Destination allowlist theo chính sách, canonicalization và redirect policy.
- Check resolved addresses, hạn chế redirect và DNS rebinding theo threat model.
- Workload network egress restrictions và least privilege.
- URL parsing/schema validation, timeouts và request-size limits.
- Không phản hồi internal response body cho client ngoài policy.
- Integration tests với mock destinations, sai hostname, redirect và failure handling.
- Runtime monitoring khi URL-fetcher cố gọi destination không được phép.

**Bài học:** một vulnerability liên quan server-side request có thể kiểm chứng bằng mock trong lab thay vì thử truy xuất metadata endpoint hoặc di chuyển vào mạng thật. Proof phải dừng ở mức đã được duyệt.

## 25. Case study 3 – Privilege risk từ CI và service identity

### 25.1. Bối cảnh

CI pipeline build, ký artifact và deploy service. Một review phát hiện:
- PR validation job có thể truy cập một số variables dùng cho release.
- CI identity có quyền ghi artifact repository và đọc rộng object storage.
- Security requirement đòi separation of duties giữa untrusted PR và trusted release.

Nhóm pentest muốn chứng minh “có thể lấy credential rồi sửa production artifact”. RoE chỉ cho **review permission boundaries và chạy test jobs vô hại trên sandbox**.

### 25.2. Cách kiểm chứng phù hợp

- Review effective CI workflow permissions, secret exposure rules và branch trust model.
- Xác minh bằng test job sandbox **không truy cập secret thật**, chỉ yêu cầu denied action trên test resource.
- Dùng role/policy simulator hoặc isolated test principal để đánh giá scope.
- Kiểm log/audit cho test identity và expected denied permission.
- Đối chiếu provenance/signing workflow của release với trust policy.
- Nếu privilege excessive được chứng minh bằng policy, ghi finding; **không cần exfiltrate credential hoặc sửa production artifact**.

### 25.3. Điều kiện dừng

- Không chạy code không được phép trong privileged release job.
- Không đọc environment variables có secret.
- Không gọi production artifact mutation.
- Không cố bypass CI approvals bằng thủ thuật không nằm RoE.
- Nếu vô tình thấy token/secret, bảo vệ evidence và theo incident procedure.

### 25.4. Mitigation và retest

- Tách PR/untrusted workflows khỏi release credentials và privileged runners.
- Gắn cloud workload identity với approved repository/ref/workflow và audience.
- Nguyên tắc least privilege theo artifact destination và environment.
- Protect branch/release approvals, isolate cache and build provenance.
- Regression tests: untrusted test identity bị deny với protected resources.
- Observe audit events và alert cho unexpected privileged requests.

### 25.5. Giới hạn kết luận

Phát hiện “policy cho phép quyền quá rộng” có thể là **design/implementation control failure** mà không cần thực hiện action nguy hiểm. Tác động tới production cần được đánh giá theo risk scenario, không khẳng định đã compromise production nếu test không làm việc đó.

## 26. Bài tập thực hành

### Bối cảnh

Một nền tảng tài chính đa tenant gồm:
- React frontend và Java/Spring Boot APIs.
- OIDC identity, role-based access và support-case delegation.
- PostgreSQL lưu báo cáo, Kafka export worker và object storage.
- Deployment ở hai regions, release container images theo digest.
- API endpoint cho phép user yêu cầu export của report ID.
- Staging có test tenants và data giả lập.
- Team Security nhận scanner alert nghi vấn BOLA ở export route.
- Product owner cấm xem dữ liệu khách hàng thật, cấm active test ngoài staging và cấm third-party callbacks.

### Nhiệm vụ

1. Xác định claim nào cần chứng minh và phân biệt discovery, validation với controlled exploitation.
2. Viết RoE cho một test stage: target, scope, owner, time window, roles, allowed methods, excluded actions, budget, stop/recovery.
3. Vẽ DFD với trust boundaries user/gateway/API/DB/queue/worker/storage.
4. Chọn proof threshold thấp nhất đủ hỗ trợ giả thuyết BOLA.
5. Thiết kế fixture user A/B, report A/B và marker vô hại.
6. Nêu expected behavior của request A→A và A→B, bao gồm HTTP và side effects.
7. Giải thích vì sao chỉ có response `202` hoặc `403` chưa xác nhận end-to-end impact.
8. Lập test plan ít nhất 12 scenarios, gồm wrong owner, revoked role, wrong tenant header, case expiry, worker job và download URL.
9. Thiết kế monitoring/stop conditions khi scan/test tạo job không mong đợi.
10. Mô tả evidence nào cần thu mà không đưa PII/token vào report.
11. Tạo một YAML engagement/evidence record theo mẫu ở mục 19.
12. Phân biệt technical observation và inferred business impact.
13. Chọn mapping từ risk → requirement → control → test → evidence → finding.
14. Đề xuất remediation ở API, worker, DB query và storage.
15. Viết acceptance criteria cho retest trên fixed release digest.
16. Giải thích tại sao PASS trong staging region A không tự thành production region B PASS.
17. Xử lý tình huống proof vô tình nhận customer data thật: stop, containment, record và communication.
18. Xử lý tình huống approved exception hết hạn nhưng fix chưa triển khai.
19. Định nghĩa metrics về proof ceiling adherence, evidence completeness và high-risk scenario coverage.
20. Viết scoped assurance claim, ghi uncertainty, limitations và reviewer.

### Bảng gợi ý

| Đề bài | Hướng đáp án |
| --- | --- |
| Controlled exploitation | Một synthetic marker test thay vì bulk extraction |
| Authorization | Written scope và exact proof ceiling |
| Data safety | Fixture dữ liệu giả, redaction, stop khi thấy PII |
| Side effects | Queue/storage/audit observation |
| Exploitability | Expected vs actual + prerequisites |
| Impact | Dựa trên loại dữ liệu và boundary, không phóng đại |
| Retest | Same failure scenario on fixed artifact |
| Scope | Đúng route/persona/tenant/region/deployment |
| Exception | Risk owner/scope/expiry và technical finding open |
| Evidence | Trusted IDs, logs, sanitized responses, reviewer |

### Câu hỏi nâng cao

Một hệ thống trả về `403` khi test user A đọc report B. Đội test cho rằng “không có BOLA”. Nhưng job export của B vẫn được tạo trong Kafka, worker sau đó sinh file B trên synthetic storage. Vậy kết luận nào đúng?

**Định hướng:** HTTP denial **không chứng minh** control end-to-end đạt. Nếu job/file được tạo từ unauthorized request trong scope, có một finding về **side-effect authorization failure** dù response trả 403. Cần record actual observed effect, stop tại proof ceiling, review root cause và retest cả API lẫn worker. Không cần tải file thật hay mở rộng sang các customer records.

## 27. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| “Pentest có quyền làm mọi thứ.” | Authorization luôn có scope và limits | Written RoE |
| “Exploit càng sâu càng có bằng chứng.” | Thêm tác động không cần thiết | Minimum sufficient proof |
| “Đã xác minh một điểm yếu thì phải pivot tiếp.” | Vượt proof ceiling/trust boundary | Dừng hoặc xin phê duyệt riêng |
| “Không có real customer data thì PoC không thuyết phục.” | Synthetic marker đủ cho nhiều cases | Controlled fixtures |
| “Scanner alert luôn là vulnerability confirmed.” | False positives và scope khác | Triage/validation |
| “Một 403 là chứng minh toàn bộ authZ.” | Worker/DB/cache có thể có side effect | End-to-end negative test |
| “PR merge là fixed.” | Chưa deploy/verify runtime | Artifact-bound retest |
| “WAF block nghĩa backend code an toàn.” | Chỉ là một boundary | Service-side policy tests |
| “Cứ kiểm production mới đáng tin.” | Có thể gây sự cố dữ liệu thật | Lab/staging và scoped runtime verification |
| “Không có stop trigger thì không cần kill switch.” | Test có thể gây unexpected impact | Operational safety plan |
| “Chứng minh impact bằng cách dump toàn bộ dữ liệu.” | Tạo privacy harm và vượt RoE | One-marker proof và risk inference |
| “Có thể dùng credential ai gửi cho mình.” | Không biết authority/scope | Authorized test identities |
| “Có privilege thì cứ thử admin endpoint.” | Không phải mọi quyền được phép kiểm | Dedicated approved scenario |
| “Không có log là không có exploit.” | Telemetry có thể down | Source health và side-effect evidence |
| “Evidence screenshot tự đủ.” | Thiếu request/deploy/fixture context | Reproducible minimal record |
| “Vuln staging = chắc chắn prod giống hệt.” | Artifact/config/region có thể khác | Actual-state mapping |
| “Có exception là lỗ hổng đã fixed.” | Risk acceptance không sửa control | Track separate states |
| “Không thấy lỗi sau patch nghĩa đã verified.” | Có thể không chạy original test | Same-scenario retest |
| “Known exploit online là đủ lý do chạy.” | Có thể phá hoại và vượt scope | Safety review, lab |
| “Lateral movement mặc định trong pentest.” | Mỗi trust boundary cần authorization | Explicit permissions |
| “Số lượng exploit là KPI pentest.” | Khuyến khích tăng impact | Evidence/risk coverage/safety |
| “Một test PASS chứng minh không có lỗi ở mọi nơi.” | Scope hẹp | Assumptions và limitations |
| “Unknown = PASS vì không tái hiện.” | Có thể thiếu fixtures/session | INCONCLUSIVE |
| “PoC có thể giữ backdoor để retest.” | Persistence trái safety principle | Tái kiểm tra bằng approved fixture |
| “Ghi raw token để reviewer xác thực.” | Tạo credential leak | Redact, protected metadata |

## 28. Checklist cuối cùng

### 28.1. Trước khi thực hiện

- [ ] Authorization/RoE hợp lệ; owner, time window, targets, allowed methods rõ.
- [ ] Có threat hypothesis và security requirement cụ thể.
- [ ] Proof level/ceiling và stop conditions được duyệt.
- [ ] Synthetic fixtures và test identities có expiry.
- [ ] Không có real customer data hoặc third-party scope ngầm.
- [ ] Tool/runner/config, deployment và version được ghi.
- [ ] Monitoring source health và on-call channel sẵn sàng.
- [ ] Request/record/time/rate budgets có hạn.
- [ ] Recovery/cleanup được kiểm.
- [ ] Evidence capture/redaction/retention được chuẩn bị.

### 28.2. Trong khi thực hiện

- [ ] Target/redirect/identity không ra ngoài scope.
- [ ] Inputs và synthetic resources đúng test plan.
- [ ] Không truy cập secret/PII thật ngoài cần thiết.
- [ ] Quan sát response và backend side effects khi relevant.
- [ ] Dừng ngay khi đủ proof, không leo thang vô ích.
- [ ] Dừng nếu có unexpected service/data impact.
- [ ] Log test ID/correlation, timestamp, request budget.
- [ ] Tách observed behavior khỏi suy diễn.
- [ ] Không đổi production configuration nếu RoE không cho.
- [ ] Handoff incident theo runbook nếu stop trigger xảy ra.

### 28.3. Khi báo cáo

- [ ] Evidence gắn asset, actor, fixture, route, method và deployment digest.
- [ ] Có expected behavior, actual behavior và proof threshold.
- [ ] Có attack prerequisites, reachability, impact và uncertainty.
- [ ] Có source-health/monitoring limitations nếu cần.
- [ ] Có sanitized evidence refs, không gửi raw tokens/PII.
- [ ] Scope và paths chưa kiểm được ghi rõ.
- [ ] Findings có owner, priority và remediation plan.
- [ ] Exceptions/risk acceptance có authority/expiry tách biệt.
- [ ] Reviewer và confidence có căn cứ.
- [ ] Phân biệt PASS/FAIL/INCONCLUSIVE/NOT_RUN.

### 28.4. Khi retest và đóng

- [ ] Fix đã triển khai trên đúng artifact/deployment/runtime.
- [ ] Original failure scenario được chạy lại trên fixtures.
- [ ] Positive và negative behavior đều đạt acceptance.
- [ ] DB/queue/storage/audit side effects đã kiểm.
- [ ] Legacy routes, worker và regions cần thiết trong scope đã cover.
- [ ] Không còn stop/safety event chưa xử lý.
- [ ] Reviewer xác nhận finding verified closed nếu đủ.
- [ ] Nếu rollback, risk và finding được đánh giá lại.
- [ ] Evidence/access/retention được giữ theo policy.
- [ ] Change triggers cho future reassessment được ghi.

## Ghi nhớ

- **Khai thác có kiểm soát là xác minh rủi ro trong phạm vi được ủy quyền**, với ngưỡng chứng minh và mức tác động giới hạn; không đồng nghĩa tấn công sâu nhất có thể.
- **Written RoE**, proof ceiling, synthetic data, monitor/stop conditions và recovery là điều kiện tiên quyết, không phải phụ lục tùy chọn.
- Chọn **minimum sufficient proof**: một marker giả, một negative authorization test hoặc một effective-policy observation có thể đủ, không cần truy xuất dữ liệu thật.
- Tách **discovery, validation, controlled exploitation, impact inference và remediation retest**; mỗi lớp chứng minh điều khác nhau.
- Một HTTP response **403/202** không tự chứng minh control end-to-end: cần kiểm DB, queue, worker, storage và audit side effects khi threat scenario liên quan.
- Evidence phải liên kết **asset, route, role/tenant, fixture, deployment/digest, observed behavior, timestamps, tool/reviewer, limitations** và bảo vệ secrets/PII.
- **CONFIRMED** chỉ nói điều đã quan sát trong scope; **INCONCLUSIVE** là lựa chọn đúng khi thiếu authorization, safety hoặc data, thay vì tự mở rộng proof.
- Risk assessment phải xét prerequisites, likelihood, exposure, impact và control effectiveness, không phóng đại từ một finding đơn lẻ.
- Finding chỉ đóng khi **actual fix đã deploy và retest scenario trước đó thất bại**; approved exception hoặc WAF không tự biến weakness thành fixed.
- Trong **SECURITY_SECURITY_ASSURANCE**, xuyên suốt vòng đời là **risk → objective → requirement → control → controlled proof → evidence → finding → remediation/retest → continuous reassessment**, có thể kiểm toán và truy trách nhiệm.
