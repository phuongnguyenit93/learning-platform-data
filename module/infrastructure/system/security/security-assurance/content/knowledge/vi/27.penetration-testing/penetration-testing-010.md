# Retest trong Penetration Testing: Xác minh khắc phục lỗ hổng bằng bằng chứng

## 1. Retest là gì và vì sao không thể bỏ qua?

**Retest** trong kiểm thử xâm nhập (penetration testing) là hoạt động **kiểm tra lại một hoặc nhiều finding đã được báo cáo**, sau khi bên sở hữu hệ thống tuyên bố đã áp dụng biện pháp khắc phục hoặc giảm thiểu, nhằm xác định **điều kiện lỗi gốc còn tồn tại, đã được xử lý hay chỉ thay đổi bề mặt biểu hiện**.

Một cuộc pentest có thể phát hiện lỗi xác thực, phân quyền, xử lý input, quản lý phiên, cấu hình hạ tầng, logic giao dịch hoặc rò rỉ thông tin. Nhưng **báo cáo finding ban đầu chưa cho biết biện pháp sửa có hiệu quả**. Phải có bước kiểm tra lại để hình thành chuỗi bằng chứng khép kín:

**Security objective → Threat scenario → Finding → Root cause → Remediation/mitigation → Retest plan → Execution → Evidence → Residual-risk decision → Closure hoặc tiếp tục xử lý.**

Trong module **SECURITY_SECURITY_ASSURANCE**, retest là một hoạt động quan trọng để đánh giá liệu hệ thống **đáp ứng mục tiêu bảo mật dựa trên bằng chứng** sau khi findings được khắc phục, chứ không phải thao tác đánh dấu ticket đã hoàn thành.

> **Nguyên tắc cốt lõi:** Không tái hiện được một biểu hiện lỗi không đồng nghĩa đã chứng minh root cause được sửa. Tương tự, một pull request đã merge, scanner không báo lại hoặc service trả HTTP 403/404 không tự chứng minh finding đã được khắc phục.

### 1.1. Câu hỏi retest phải trả lời

1. **Finding gốc có còn applicable?** Tài sản, code path, điều kiện khai thác và quyền của attacker còn tồn tại?
2. **Biện pháp sửa thực sự là gì?** Sửa code, thay cấu hình, vá dependency, thay kiến trúc, tắt tính năng hay thêm compensating control?
3. **Đã triển khai ở đâu?** Build, artifact, environment, region, tenant và replicas nào thực sự nhận thay đổi?
4. **Đường khai thác gốc có còn khả thi?** Cần tái hiện an toàn với preconditions tương đương.
5. **Những bypass và biến thể liên quan có còn?** Có đường khác qua cache, worker, export, API version hoặc direct route?
6. **Hành vi hợp lệ có còn hoạt động?** Fix có vô tình từ chối mọi request hoặc gây mất chức năng?
7. **Có rủi ro mới do fix tạo ra?** Regression về authorization, data integrity, availability, logging hoặc thông tin nhạy cảm?
8. **Có đủ bằng chứng để kết luận?** Đúng phạm vi, version, công cụ, thời điểm, account, test oracle và reviewer?
9. **Ai được quyền chấp nhận residual risk?** Pentester không tự thay thẩm quyền risk owner.
10. **Khi nào phải retest lại?** Khi phát hiện bypass, thay framework, rollback hoặc exposure mới.

### 1.2. Ví dụ nhanh

Trong Orders API đa tenant, user tenant A có thể đọc order của tenant B. Dev sửa một method controller.

Có ít nhất năm tình huống:

- Endpoint gốc đã deny nhưng endpoint **/v2/orders** chưa sửa.
- HTTP response trả 404 do order B **không tồn tại** trong test environment, không phải do authorization.
- Staging có patch nhưng production vẫn chạy image cũ.
- Controller deny nhưng worker export vẫn trả dữ liệu B.
- Fix thêm filter đúng tenant nhưng user A tự gửi header X-Tenant-Id của B.

Retest phải **chứng minh ranh giới quyền truy cập thực sự được giữ**, không dừng ở một response code.

## 2. Phân biệt retest với những hoạt động thường bị nhầm

| Khái niệm | Mục tiêu | Giới hạn |
| --- | --- | --- |
| **Initial penetration test** | Tìm và xác nhận vulnerabilities trong phạm vi hợp đồng | Chưa xác minh fix chưa tồn tại |
| **Retest** | Kiểm lại findings cụ thể sau remediation/mitigation | Không mặc định kiểm tra toàn bộ hệ thống |
| **Full reassessment / re-penetration test** | Đánh giá rộng lại security posture sau thay đổi | Tốn công hơn retest targeted |
| **Security regression test** | Chống tái phát một security invariant trong phát triển | Có thể không bao quát attacker pathway khác |
| **DAST rescan** | Quét động lại bằng tool/rule scope xác định | Không thay human validation và business logic tests |
| **SAST/SCA rescan** | Kiểm tra code/dependency theo static rules | Không xác minh mọi runtime trust boundary |
| **Patch verification** | Xác nhận patch/version và hiệu quả theo mục tiêu | Có thể bao gồm retest nhưng không đồng nhất |
| **Vulnerability triage** | Xác định finding thật, applicable, priority | Không chứng minh remediation complete |
| **Compensating-control validation** | Kiểm tra biện pháp bù trừ có giảm exposure | Root cause có thể vẫn còn |
| **Risk acceptance** | Quyết định có thẩm quyền về residual risk | Không biến vulnerability thành fixed |
| **Continuous monitoring** | Theo dõi dấu hiệu compromise/drift | Không tự thay retest targeted |

### 2.1. Retest không tự động là pentest toàn diện lần hai

Nếu một pentest ban đầu phát hiện ba findings, retest được giao có thể chỉ xác minh ba findings đó. Các lỗi mới không thuộc scope hoặc paths chưa từng được đánh giá **không được coi an toàn** chỉ vì retest PASS.

Một retest report cần nêu:

- Findings trong scope.
- Assets, endpoints, roles, tenants và versions.
- Những gì đã được thử.
- Những gì chưa được thử.
- Các changes ảnh hưởng attack surface nằm ngoài scope.
- Khi nào nên có một assessment rộng hơn.

### 2.2. Retest có thể sinh finding mới

Trong khi kiểm tra fix, pentester có thể thấy:

- Bypass thay thế.
- Regressions.
- Một misconfiguration mới.
- Privilege path lộ ra khi đổi workflow.

Phải **báo lại với owner theo rules of engagement**, không âm thầm mở rộng hoạt động sang hệ thống ngoài quyền kiểm tra. Với rủi ro ngoài scope, chuyển thông tin tối thiểu cho người phụ trách, đề xuất authorization bổ sung nếu cần.

### 2.3. Verify fix khác “fix verified on production”

Một test PASS trên staging có thể là:

> **Verified fixed in staging scope** trên artifact có digest cụ thể.

Nó **chưa đủ** cho câu:

> **Production fixed** trên toàn bộ regions/replicas.

Để kết luận production, cần evidence về rollout, runtime identity và test/verification phù hợp.

## 3. Vai trò của retest trong Security Assurance

### 3.1. Retest nằm ở đâu trong assurance lifecycle?

~~~mermaid
flowchart TD
    A["Security objective / requirement"] --> B["Threat model and authorized pentest"]
    B --> C["Confirmed finding + evidence"]
    C --> D["Risk-based priority and owner"]
    D --> E["Root-cause fix or mitigation"]
    E --> F["Define retest scope and acceptance criteria"]
    F --> G["Preflight: target, identity, artifact, safety"]
    G --> H{"Preconditions and approvals valid?"}
    H -- "No" --> X["BLOCKED / gather evidence"]
    H -- "Yes" --> I["Safe targeted retest"]
    I --> J["Positive, negative, bypass and regression checks"]
    J --> K{"Evidence supports closure?"}
    K -- "No" --> L["OPEN / PARTIAL / MITIGATED / INSUFFICIENT"]
    L --> D
    K -- "Yes" --> M["Verified fixed within assessed scope"]
    M --> N["Runtime verification and approved closure"]
    N --> O["Monitoring / re-open triggers"]
~~~

### 3.2. Ba lớp effectiveness

| Lớp | Câu hỏi | Evidence cần |
| --- | --- | --- |
| **Design effectiveness** | Biện pháp sửa có xử lý nguyên nhân và abuse case không? | Root-cause analysis, design review, requirement, threat model |
| **Implementation effectiveness** | Code/config đã thay đổi đúng và bài test đạt không? | Patch diff, code review, build/CI, targeted test result |
| **Operating effectiveness** | Control được triển khai đúng, duy trì hiệu lực ở runtime không? | Production artifact/config identity, audit, canary, periodic verification |

Một retest PASS trên sandbox có thể cung cấp bằng chứng tốt về **implementation**, nhưng không tự chứng minh **operating** của production.

### 3.3. Claim – evidence – argument

Một assurance case rút gọn:

- **Claim:** User A không thể truy cập dữ liệu tenant B qua đường Orders API thuộc scope.
- **Argument:** Access được kiểm tra server-side theo trusted principal và resource ownership; các đường API/cache/export đã được xem xét.
- **Evidence:** Negative cross-tenant tests, positive tenant tests, repository/integration checks, cache/worker checks, deployment digest, security event logs.
- **Limitations:** Support console và API legacy ngoài scope; chưa kiểm chứng đầy đủ third-party integrations.
- **Residual risk:** Những paths excluded còn cần review riêng.

Bằng chứng phải **hỗ trợ đúng claim**, không chỉ tồn tại dưới dạng file.

## 4. Quyền kiểm thử và Rules of Engagement trước retest

### 4.1. Retest vẫn cần phạm vi được ủy quyền

Việc đã pentest trước đây **không có nghĩa có quyền retest mọi nơi, mọi thời điểm**. Cần xác nhận lại:

- Chủ sở hữu và sự cho phép bằng văn bản/quy trình đã thống nhất.
- Tài sản và domain/IP/hostnames cụ thể.
- Environment: lab, staging, canary hoặc production.
- Những endpoints/methods và roles được phép.
- Thời gian kiểm tra.
- Giới hạn request rate, concurrency và bandwidth.
- Có được thực hiện active probes, file upload, business transactions hoặc fault injection không.
- Những hành vi bị cấm: truy cập dữ liệu khách hàng ngoài scope, phá hủy dữ liệu, persistence, làm gián đoạn dịch vụ.
- Test identities, fixture ownership và safe data handling.
- Điểm liên hệ/kill switch/incident escalation.
- Phương án dừng, khôi phục và cleanup.
- Quy định evidence/report confidentiality.

### 4.2. Vì sao retest có thể nguy hiểm hơn tưởng tượng?

Một finding ban đầu có thể là:

- Lỗi upload dẫn tới lưu file ngoài ý muốn.
- Broken authorization ở thao tác refund.
- SSRF tới internal service.
- Query có thể gây database overload.
- Logic bug tạo thanh toán hoặc email.
- Race condition đòi nhiều concurrent requests.

Nếu tái hiện máy móc trên production, retest có thể gây outage, duplicate charge hoặc data exposure. Hãy **chọn phương pháp chứng minh an toàn**, như synthetic data, isolated targets, controlled probes hoặc review effective controls.

### 4.3. Bằng chứng đủ mà không cần exploit phá hoại

Để xác minh:

- SQL injection: test parameterization và truy vấn an toàn trong lab, không cần payload hủy bảng.
- Authorization: dùng hai users/tenants giả, test allow/deny và data invariant.
- SSRF: dùng mock endpoint do tổ chức kiểm soát và egress policy checks.
- File path: dùng sandbox test directory, không đọc host secrets.
- Secret exposure: dùng canary secret/test token có thể revoke, không log credential production.
- Race: dùng sandbox với bounded concurrency và deterministic fixtures.
- DoS: test resilience trong môi trường được phép, giới hạn traffic thay vì thử phá production.

Với finding có độ rủi ro cao, **không có khả năng chạy exploit đầy đủ trên production** không nhất thiết ngăn mọi kết luận; tuy nhiên phải ghi rõ evidence alternatives và limitations.

### 4.4. Stop conditions

Dừng hoặc chuyển incident process khi:

- Có dấu hiệu compromise đang diễn ra.
- Test có khả năng chạm dữ liệu khách hàng thật.
- Bất thường về error rate, latency, CPU/DB saturation.
- Target nhận diện không khớp asset được cho phép.
- Token/test identity bị dùng ngoài scope.
- External callback đi tới nơi không được phê duyệt.
- Có dấu hiệu transaction thật hoặc dữ liệu thật bị ảnh hưởng.
- Ứng dụng phản ứng ngoài dự kiến gây side effect lớn.

Không cố hoàn thành checklist trong khi safety conditions đã thất bại.

## 5. Đầu vào bắt buộc của một lần retest

### 5.1. Hồ sơ finding gốc

| Trường | Tác dụng |
| --- | --- |
| **Finding ID** | Định danh ổn định từ báo cáo gốc |
| **Title/class** | Phân loại yếu điểm: BOLA, SQLi, SSRF, IAM... |
| **Affected asset** | Service/host/route/environment/version |
| **Original severity/priority** | Context rủi ro ban đầu |
| **Threat scenario** | Attacker capability, trust boundary, impact |
| **Original preconditions** | Role, tenant, resource, config, feature flag |
| **Original steps/evidence** | Mô tả có thể tái hiện an toàn |
| **Observed insecure behavior** | Dữ liệu/state/response thực sự đã thấy |
| **Expected secure behavior** | Security invariant mong muốn |
| **Root cause hypothesis** | Tại sao lỗi xảy ra |
| **Control owner/risk owner** | Người sửa và người quản lý residual risk |
| **Scope and limitations** | Những điều pentest trước chưa đánh giá |

Một finding chỉ ghi “Critical: API insecure” không đủ cho retest chính xác. Cần làm rõ requirement và setup cùng owner.

### 5.2. Hồ sơ remediation

- Link tới patch/change record.
- Root-cause analysis và phương án khắc phục.
- Commit/PR hoặc config policy revision.
- Code paths/components bị thay.
- Vendor advisory/dependency fixed version nếu có.
- Build ID, artifact/image digest.
- Deployment target và effective config.
- Feature flags và compensating controls.
- Expected acceptance criteria.
- Regression tests đã được engineering bổ sung.
- Known limitations/risks và pending exceptions.
- Rollback/roll-forward plan.
- Owner xác nhận ready for retest.

**Developer nói “đã sửa” là tín hiệu để retest, không phải bằng chứng kết luận.**

### 5.3. Hồ sơ test environment

- Canonical URL và ownership.
- Trusted TLS/certificate phù hợp.
- Current deployment digest/revision.
- Dependency state: DB, cache, queue, policy engine.
- User identities/roles/tenant memberships.
- Synthetic fixtures.
- Test time window, rate limits.
- Logging/audit và tracing correlation.
- Side-effect guards và sandbox third parties.
- Test tooling versions.
- Access tới evidence store bảo mật.

### 5.4. Retest readiness checklist

Nếu thiếu một yếu tố quan trọng như wrong artifact, missing account, DB trống hoặc feature flag off ngoài dự định, trạng thái đúng là **BLOCKED/NEEDS_PRECONDITION**, không phải PASSED.

## 6. Scope của retest và xác định vùng ảnh hưởng

### 6.1. Ba vòng phạm vi

1. **Original exploit path:** tái kiểm tra điều kiện/đường lỗi được ghi nhận.
2. **Closely related variants:** những endpoints, methods, roles, tenants hoặc inputs cùng root cause.
3. **Adjacent regression/security invariants:** chức năng hợp lệ và control liên quan có bị phá do fix không.

Một targeted retest có thể chỉ được cấp quyền vòng 1; khi đó không được kết luận vòng 2–3 đã an toàn.

### 6.2. Affected population

Ví dụ cùng lỗi có thể tồn tại ở:

- API v1 và v2.
- Gateway public và internal service route.
- Web/mobile backend.
- Tenants thuộc nhiều regions.
- Một số Kubernetes replicas còn build cũ.
- Worker và scheduled job dùng library cũ.
- Multi-cloud deployment có config khác.
- Support/admin console và public endpoints.
- Cached artifacts tạo trước khi fix.

Cần dùng **asset inventory + deployment mapping** để biết closure population.

### 6.3. Parent finding và child exposures

Một parent “authorization middleware không enforce object-level permissions” có thể có nhiều exposures:

- Orders API GET.
- Bulk export endpoint.
- Worker report generation.
- Legacy REST endpoint.
- Cache access.

Sửa một endpoint không đóng tất cả child exposures. Mỗi child có test và runtime scope riêng; parent chỉ đóng khi criteria theo policy được đáp ứng.

### 6.4. Thay đổi lớn có thể cần assessment mới

Nếu remediation:

- Thay toàn bộ identity provider.
- Chuyển DB access layer.
- Đổi authorization service architecture.
- Split/merge services.
- Mở API mới.
- Đổi public ingress/WAF/mesh policies.
- Chuyển từ cookie session sang JWT.
- Thay data flow qua queue và third party.

Thì một retest rất hẹp có thể không đủ; đề xuất **broader security regression/pentest reassessment** với scope được phê duyệt.

## 7. Ưu tiên và thời điểm retest

### 7.1. Vì sao phải risk-based?

Nếu có 300 findings nhưng chỉ 10 có production high-impact exposure, kế hoạch retest phải chú ý:

- Severity kỹ thuật và priority theo bối cảnh.
- Active exploitation hoặc suspected compromise.
- Internet exposure và attacker prerequisites.
- Data classification và business impact.
- Blast radius/shared control plane.
- Fix complexity và khả năng bypass.
- Release/patch window và obligations thực sự áp dụng.
- Compensating controls đã có evidence hay chưa.
- Thời gian finding bị mở.
- Incident và threat intelligence mới.

Không dùng “đã fix xong trước” để mặc định retest trước nếu rủi ro những findings khác lớn hơn.

### 7.2. Retest đồng bộ theo release

Một cách tổ chức:

- PR/merge: developer chạy targeted security regression.
- Staging: pentest/security QA chạy retest theo finding.
- Release gate: kiểm tra evidence và residual risk.
- Production rollout: xác minh artifact/config identity và các safe checks.
- Post-release: theo dõi drift và finding recurrence.
- Periodic: chọn mẫu hoặc targeted revalidation theo policy.

Không phải mọi pentest retest phải nằm trong CI tự động; các finding phức tạp đòi human judgment. Nhưng CI nên đảm nhiệm được **regression cases đã chuẩn hóa**.

### 7.3. Khi finding có active exploitation

Nếu đã có dấu hiệu khai thác thực tế hoặc đang bị compromise:

1. Kích hoạt containment/incident workflow.
2. Bảo toàn bằng chứng liên quan.
3. Giảm exposure theo thẩm quyền.
4. Triển khai fix với testing an toàn theo urgency.
5. Retest targeted trước và sau deployment khi khả thi.
6. Theo dõi related compromise indicators và residual risk.
7. Bổ sung broader assurance khi ổn định.

Không chờ đủ toàn bộ retest suite mới cô lập một đường tấn công đang hoạt động.

### 7.4. Không có SLA cố định cho mọi tổ chức

Thời hạn retest, triage và verify phải dựa trên policy, severity/priority, service SLO và nghĩa vụ áp dụng. Cần định nghĩa clock start/end rõ:

- Remediation ready for retest.
- Retest scheduled.
- Execution completed.
- Evidence reviewed.
- Finding verified/closed.
- Follow-up action due.

Một ngày hoàn thành retest khác với ngày finding đã được fixed trong production.

## 8. Thiết kế retest plan theo một finding

### 8.1. Cấu trúc test case

Mỗi test case nên có:

- Test ID, finding ID và threat/security requirement.
- Test target, artifact/config/feature flag.
- Precondition về account/role/tenant/resource.
- Input/operation trong scope được phép.
- Expected outcome có thể assert.
- Actual outcome, logs và data state.
- Postcondition/side effects.
- Negative/positive/boundary/bypass variants.
- Evidence links và timestamps.
- Test status: PASS/FAIL/BLOCKED/NOT_RUN/INCONCLUSIVE.
- Reviewer/owner và limit.
- Cleanup/recovery.

### 8.2. Test oracle cần mạnh hơn HTTP status

**Test oracle** là cách quyết định hành vi đúng hoặc sai. Ví dụ:

| Finding | Oracle yếu | Oracle có ý nghĩa |
| --- | --- | --- |
| BOLA | Endpoint trả 404 | Order B tồn tại và user B xem được; user A không nhận bất cứ B data nào |
| Privilege escalation | 403 khi gọi admin | User ít quyền không thực hiện được action, policy/audit đúng, admin hợp lệ vẫn được |
| SQL injection | Scanner không báo | Code dùng parameter binding; safe DB test không thay query semantics; permissions đúng |
| SSRF | Request trả 400 | Effective egress/destination policy deny unauthorized targets, không có internal callback |
| Secret leak | Không thấy token trong một log | Log/trace/interceptor sinks có kiểm thử masking theo scope |
| Webhook replay | API trả 409 | Business state chỉ thay đúng một lần; duplicate không có external side effect |
| Path traversal | Response 404 | Không thể đọc resource ngoài authorized storage scope, kể cả alternate path |
| Missing rate limit | Request #N bị chặn | Rule đúng identity/key/scope, không lockout bất thường, không bypass theo route |
| Cloud IAM | Policy file thay | Effective denied action test với principal phù hợp |

### 8.3. Positive, negative và boundary

- **Positive:** principal hợp lệ vẫn làm được hành động được phép.
- **Negative:** actor không đủ quyền/đầu vào không hợp lệ không đạt kết quả trái policy.
- **Boundary:** hết hạn token, role/tenant thay đổi, input kích thước giới hạn.
- **Variant:** route/HTTP method/API version khác, cache hoặc async path.
- **Failure:** policy engine unavailable, worker retry, stale cache.
- **Concurrency:** race nếu root cause liên quan ordering, với bounded test conditions.

Nếu chỉ kiểm tra negative, một service **deny tất cả** có thể PASS giả. Nếu chỉ kiểm tra positive, một service **allow tất cả** cũng có thể PASS giả.

### 8.4. Reproduction method và safety

Một pentest report ban đầu có thể chứa bước tái hiện mà không nên chạy nguyên vẹn tại production. Retest plan có thể chọn:

- Thực hiện lại bằng **synthetic actor/resource**.
- Sử dụng harmless marker cho injection evidence.
- Đối chiếu effective patch/config và controlled integration test.
- Dùng staging/sandbox cho active tests.
- Dùng production safe validation với authority.
- Tách root-cause review và runtime evidence.

Cần ghi nếu retest **không chạy chính xác original exploit** và giải thích bằng chứng thay thế có hỗ trợ claim đến đâu.

## 9. Quy trình retest có kiểm soát: từng bước

### Bước 1 — Nhận handoff từ remediation owner

Yêu cầu:

- Finding/patch IDs.
- Những thay đổi đã thực hiện.
- Root-cause mapping.
- Tested versions và target deployments.
- Unit/integration/security tests đã chạy.
- Known exceptions và residual risks.
- Approval cho phạm vi retest.

Nếu chỉ nhận “đã sửa”, yêu cầu bổ sung thông tin qua quy trình, không tự suy từ branch name.

### Bước 2 — Xác minh scope và safety

- ROE/authorization hiện hành.
- Approved target identity.
- Time window và impact controls.
- Test identities và data.
- No-production-side-effect safeguards.
- Stop contacts và rollback/reset procedures.

### Bước 3 — Xác minh deployed patch/config

- Source commit và build ID.
- Artifact digest/image ID hoặc vendor package build.
- Running workload/config revision.
- Feature flags và authorization policies.
- Các instances/regions thực thuộc scope.
- Gateway/route mapping tới đúng backend.
- Dependencies quan trọng.

Nếu đang test bản cũ, retest sẽ chỉ đo được bản cũ; không được gán kết quả cho patch mới.

### Bước 4 — Xác minh preconditions

- Actor A/B tồn tại với roles/tenants xác định.
- Resource B thật và user B được phép xem B.
- User A không có quyền trên B.
- Endpoint/function thực đang enabled và reachable.
- Các policy conditions giống finding gốc hoặc được ghi khác biệt.
- External integrations ở test sandbox.
- Data fixture được reset.

### Bước 5 — Thực hiện safe retest targeted

- Chạy testcase gốc đã được giới hạn an toàn.
- Lưu actual result và correlation.
- Kiểm tra side effects/state.
- Không tiếp tục destructive action nếu stop condition kích hoạt.

### Bước 6 — Kiểm tra variants và regressions

- Positive/negative cases.
- Alternative endpoints/HTTP methods.
- Cache/search/export/worker/legacy paths.
- State boundary, role changes, retries và failure modes.
- Tests có relevance theo root cause, tránh quét vô hạn ngoài scope.

### Bước 7 — Đánh giá evidence và disposition

- Mức độ fix có thực sự hiệu quả?
- Có thiếu coverage hoặc blocker?
- Có vulnerability path còn mở?
- Compensating control có effective và tồn tại tại runtime?
- Status phải ghi thế nào?
- Có cần escalation/incident response?

### Bước 8 — Báo cáo, remediation tiếp và re-open triggers

- Report rõ phạm vi, version, IDs, tests và actual outcomes.
- Owner/risk owner/reviewer được chỉ rõ.
- Tạo/giữ ticket cho findings chưa fixed.
- Chốt retest follow-up nếu có regression hoặc evidence gap.
- Ghi những conditions cần re-open.
- Không biến risk exception thành trạng thái verified fixed.

## 10. Kiểm tra identity của bản vá và môi trường

### 10.1. Vì sao patch verification là điều kiện cần?

Một lần retest có thể PASS do:

- Test chạy trên một deployment staging đã có patch.
- Feature bị tắt ở staging nhưng bật ở production.
- API request được chuyển tới service khác.
- Legacy replicas vẫn chạy image cũ.
- Config staging deny nhưng production fail-open.
- User account có role không giống finding gốc.
- Database trống nên 404/empty response.
- Scanner quét một hostname không phải target bị ảnh hưởng.

Vì vậy cần chứng minh **đang kiểm tra đúng hệ thống và điều kiện**.

### 10.2. Artifact identity

Với containerized service:

- Commit SHA.
- Build pipeline/run ID.
- OCI image digest.
- SBOM/provenance reference nếu có.
- Deployment manifest revision.
- Runtime imageID/digest.
- Replica count và rollout status.
- Region/namespace/cluster và service route.

Với OS/firmware/vendor patch:

- Product/distribution version.
- Vendor advisory applicability.
- Package build metadata/backport claim.
- Running kernel/firmware version sau reboot khi cần.
- Effective configuration.
- Reboot/restart/change evidence.

**Tag hoặc semantic version tự nó có thể không đủ**, nhất là khi tag bị di chuyển hoặc vendor backport.

### 10.3. Config identity

Security behavior còn phụ thuộc:

- Identity provider issuer/audience.
- Tenant membership/policy revision.
- IAM/network firewall.
- WAF/API gateway rules.
- Feature flags.
- Secrets và credentials.
- Database roles/RLS.
- Session cookies/CORS/CSRF.
- Cache isolation policy.
- Log/audit settings.

Test cùng binary nhưng khác config có thể cho kết quả khác; record phải nêu rõ runtime config scope.

### 10.4. Patch có ở một phần fleet

Nếu 8/10 replicas được vá:

- Có thể retest trên các replicas mới PASS.
- Hai replicas cũ vẫn có thể phục vụ traffic.
- Không kết luận **full production fixed**.
- Dùng trạng thái **PARTIALLY_REMEDIATED/PARTIAL_ROLLOUT**.
- Tracking remaining affected instances và thời gian.
- Retest/verify sau khi fleet được cập nhật.

### 10.5. Staging parity và production verification

| Thành phần | Điều cần so sánh |
| --- | --- |
| API gateway | Route/rewrites, rate limit, direct bypass |
| Identity | Token validation, roles, membership |
| DB | Engine, RLS, service role, test data |
| Cache | Tenant keys, invalidation, redis scope |
| Queue/worker | Event schemas, privileges, retry |
| Network | WAF, ingress/egress, mTLS |
| Artifact | Image digest, sidecars, runtime |
| Feature flags | Default, rollout group và environment |
| Logging/audit | Sensitive-data capture, alert delivery |
| Third party | Sandbox vs real provider behavior |

Một staging PASS vẫn có giá trị nếu giới hạn được ghi, nhưng không tự đại diện production.

## 11. Ma trận retest theo loại vulnerability

| Vulnerability | Precondition quan trọng | Safe targeted retest | Bổ sung cần kiểm tra |
| --- | --- | --- | --- |
| **BOLA/IDOR** | Hai users, hai resources khác ownership | A không lấy resource B, B vẫn đọc B | Cache, bulk/export, API v1/v2, support |
| **BFLA** | Role không có quyền thao tác | Role thấp bị deny, role hợp lệ thành công | Alternative methods, backend direct route |
| **SQL injection** | Query path và input có thể điều khiển | Safe input variation + parameter binding review | Dynamic queries, DB privileges, error handling |
| **XSS** | Context output/browser và stored content | Harmless marker + output-context/browser validation | CSP, other rendering contexts |
| **SSRF** | Server có outbound HTTP sink | Controlled callback to test host + egress verification | Redirects, DNS, IPv6, alternate destinations |
| **Path traversal** | Authorized file storage và requester | Synthetic files trong sandbox, verify containment | Symlinks/race, object ownership, download aliases |
| **Session weakness** | Valid/expired/revoked sessions | Refresh/revoke/expiry behavior, cookies | Recovery, privileged step-up, federation |
| **CSRF** | Browser session và unsafe action | Missing/invalid anti-CSRF context bị deny | SameSite/origin, API alternatives |
| **Webhook replay** | Valid sandbox event, idempotency key | Duplicate không tạo side effect lặp | Out-of-order, wrong tenant, signature errors |
| **Secrets in logs** | Test-only secret/token marker | Scan protected logs/trace for disclosure | Interceptors, error paths, external telemetry |
| **IAM misconfiguration** | Principal và effective policy | Allowed/denied actions trong sandbox | Inherited policies, workload credentials |
| **WAF bypass** | Targeted rule và authorized test context | Controlled benign indicator qua relevant routes | Backend bypass, rule deployment drift |
| **TLS config** | Effective endpoint/cert | Verify negotiated settings và identity | Alternate host, internal route, rotation |
| **Rate limit** | Identity/IP/session tracking model | Bounded burst trong lab, correct limiting | Distributed limiters, reset windows |
| **Data deletion/privacy** | Synthetic subject và retention policy | Request lifecycle, verify scoped state | Backups, replicas, audit/expiry obligations |
| **Dependency CVE** | Applicable version/attack surface | Vendor fix mapping, runtime artifact, safe class test | Transitive/build/runtime scope |
| **Cloud storage exposure** | Test bucket/object and principal | Denied anonymous/cross-role reads | Alternate URLs, public ACL/edge cache |
| **Audit gap** | Controlled security event | Event captured, protected, queryable | Correlation, retention, no raw secrets |

Đây là **ma trận định hướng**, không phải danh sách exploit payload. Actual test phải theo finding, ROE và hệ thống.

## 12. Case study: Retest BOLA trong Orders API nhiều tenant

### 12.1. Hệ thống giả định

Một nền tảng SaaS có:

- Browser/mobile client và API gateway.
- Java/Spring Boot Orders API.
- Identity provider với tenant memberships.
- PostgreSQL, cache Redis.
- Queue và report worker.
- Private export storage.
- Support/admin console.
- Audit pipeline.

Finding ban đầu: principal A thuộc tenant A có thể gửi order ID của tenant B và nhận dữ liệu B qua GET order.

### 12.2. Threat model

- **Asset:** dữ liệu đơn hàng và PII theo data classification.
- **Attacker capability:** authenticated user trong tenant A.
- **Trust boundary:** request resource ID → object-level authorization.
- **Root cause giả định:** query dùng order ID nhưng không dùng verified tenant/resource permission.
- **Impact:** cross-tenant confidentiality breach.
- **Control objective:** mọi resource access phải ràng buộc actor/tenant/resource được xác minh.
- **Fix candidate:** tenant-scoped query và centralized authorization tại service boundary.

### 12.3. Data-flow diagram

~~~mermaid
flowchart LR
    A["Test user A"] --> GW["API Gateway"]
    B["Test user B"] --> GW
    GW --> API["Orders API"]
    API --> AUTH["Verified Principal / Authorization"]
    API --> DB[("PostgreSQL")]
    API --> CACHE[("Redis")]
    API --> Q[("Event Bus")]
    Q --> WORKER["Report Worker"]
    WORKER --> STORE[("Export Storage")]
    API --> AUDIT[("Audit")]
    WORKER --> AUDIT
~~~

Các trust boundaries:

- **TB1:** browser/client → API authentication.
- **TB2:** caller identity → tenant/role membership.
- **TB3:** API → object access tại DB/cache.
- **TB4:** API event → report worker trust.
- **TB5:** export artifact → authorized recipient.
- **TB6:** security decision → audit.

### 12.4. Finding gốc và fix

**Before (rút gọn, không an toàn):**

~~~java
public OrderDto getOrder(UUID orderId) {
    Order order = repository.findById(orderId)
            .orElseThrow(ResourceNotFoundException::new);
    return OrderDto.from(order);
}
~~~

**After (minh họa):**

~~~java
public OrderDto getOrder(
        UUID orderId,
        VerifiedPrincipal caller) {
    permissionService.requireAllowed(
            caller, "orders.read", caller.tenantId());

    Order order = repository
            .findByIdAndTenantId(orderId, caller.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

    return OrderDto.from(order);
}
~~~

Đây **không phải class Spring Boot độc lập có thể biên dịch ngay**; các types, trusted principal resolver và repository semantics cần được triển khai. Việc gọi **findByIdAndTenantId** chỉ đúng nếu actual SQL/filter và trusted tenant source đúng.

### 12.5. Retest acceptance criteria

- User A truy cập order A thành công.
- User B truy cập order B thành công.
- User A không truy cập order B.
- User A không tự nâng quyền bằng cách gửi X-Tenant-Id của B.
- API không tiết lộ data B trong body, headers hoặc link.
- Cache không trả nhầm B sau khi B tạo cache.
- Bulk/search/export không đưa B vào kết quả của A.
- Worker không tin tenant context do client tự khai.
- Authorization fail/timeout không trở thành allow đối với Confidential export.
- Audit ghi denied action theo policy, không log raw tokens.
- Build được retest đúng với deployment target.
- Không còn affected replicas/versions ngoài scope đã khai báo.

### 12.6. Ma trận test

| Test ID | Caller | Resource/operation | Expected | Loại |
| --- | --- | --- | --- | --- |
| **RT-ORD-01** | A | GET order A | 200 và đúng owner/data | Positive |
| **RT-ORD-02** | B | GET order B | 200 và đúng owner/data | Precondition |
| **RT-ORD-03** | A | GET order B | 403/404 theo contract, không B data | Negative |
| **RT-ORD-04** | A | GET order B + forged tenant B header | Deny/no disclosure | Bypass |
| **RT-ORD-05** | Anonymous | GET order A | Unauthorized | Authn |
| **RT-ORD-06** | A | GET cached order B | Deny/no disclosure | Cache |
| **RT-ORD-07** | A | Bulk export mixed A/B | No B data | Data-flow |
| **RT-ORD-08** | Forged queue event | Generate report B for A | Reject/hold | Worker |
| **RT-ORD-09** | Revoked A | GET old order A | Deny theo policy | State |
| **RT-ORD-10** | A; policy engine unavailable | Export Confidential records | Fail-safe, no artifact | Failure |
| **RT-ORD-11** | Valid A | GET order A with feature enabled | Correct behavior/performance | Regression |
| **RT-ORD-12** | Test deployment | Effective build digest | Match approved patch | Evidence |
| **RT-ORD-13** | All target replicas | Running artifact | Patch deployed everywhere | Coverage |
| **RT-ORD-14** | Security audit | Unauthorized attempt | Correct event, no secret | Operating |

### 12.7. Quan trọng: 404 có thể là false PASS

Nếu Order B không tồn tại, user A nhận 404 không chứng minh authorization.

Cần **positive control** trước: user B có thể truy cập B trên đúng environment và phiên bản. Cũng phải xác minh:

- Account A không có membership B.
- Tokens không hết hạn/invalid.
- API path không sai.
- Feature không bị disable.
- Service thực đang phục vụ patch mới.
- Fixture B chưa bị test trước xóa.
- Policy role map đúng.

**Một test không thỏa điều kiện ban đầu phải BLOCKED/INVALID**, không được đánh dấu PASS.

## 13. Java/JUnit: ví dụ retest API qua HTTP

### 13.1. Test setup

Một bộ test kiểm tra qua HTTP có thể dùng Java HttpClient và JUnit 5 với:

- Base URL **được phê duyệt** trong môi trường cô lập.
- Short-lived token của A và B.
- UUID của Order A, Order B.
- Synthetic marker riêng trong dữ liệu B.
- Preflight kiểm tra target scheme/host.
- Không theo redirects tới external target.
- Không in Authorization header hoặc response chứa dữ liệu nhạy cảm.

### 13.2. JUnit 5 ví dụ

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

final class OrdersBolaRetestIT {
    // Placeholder must be replaced by an approved test hostname.
    private static final String APPROVED_HOST = "orders.test.example";

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private String requiredEnv(String name) {
        String value = System.getenv(name);
        assertNotNull(value, name + " is missing");
        assertFalse(value.isBlank(), name + " must not be blank");
        return value;
    }

    private URI base() {
        URI target = URI.create(requiredEnv("RETEST_BASE_URL"));
        assertEquals("https", target.getScheme());
        assertEquals(APPROVED_HOST, target.getHost(),
                "Refuse unapproved retest target");
        assertTrue(target.getPort() == -1 || target.getPort() == 443);
        return target;
    }

    private HttpResponse<String> getOrder(
            String token, UUID id) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                        base().resolve("/api/orders/" + id))
                .timeout(Duration.ofSeconds(10))
                .header("Authorization", "Bearer " + token)
                .GET()
                .build();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void authorizedUsersCanReadTheirOwnedOrders() throws Exception {
        UUID orderA = UUID.fromString(requiredEnv("RETEST_ORDER_A"));
        UUID orderB = UUID.fromString(requiredEnv("RETEST_ORDER_B"));

        HttpResponse<String> responseA =
                getOrder(requiredEnv("RETEST_TOKEN_A"), orderA);
        HttpResponse<String> responseB =
                getOrder(requiredEnv("RETEST_TOKEN_B"), orderB);

        assertEquals(200, responseA.statusCode());
        assertEquals(200, responseB.statusCode());

        // In real tests, parse a typed JSON DTO and assert owner/tenant.
        assertTrue(responseA.body().contains(orderA.toString()));
        assertTrue(responseB.body().contains(orderB.toString()));
    }

    @Test
    void userACannotReadTenantBOrder() throws Exception {
        UUID orderB = UUID.fromString(requiredEnv("RETEST_ORDER_B"));
        String markerB = requiredEnv("RETEST_MARKER_B");

        // Positive control: the foreign order exists for authorized B.
        HttpResponse<String> expectedOwner =
                getOrder(requiredEnv("RETEST_TOKEN_B"), orderB);
        assertEquals(200, expectedOwner.statusCode());
        assertTrue(expectedOwner.body().contains(markerB));

        // Retest original trust boundary with an unauthorized actor.
        HttpResponse<String> unauthorized =
                getOrder(requiredEnv("RETEST_TOKEN_A"), orderB);

        // This example assumes the API contract hides inaccessible orders.
        assertEquals(404, unauthorized.statusCode());
        assertFalse(unauthorized.body().contains(markerB));
    }
}
~~~

### 13.3. Giới hạn và điều kiện nâng cấp ví dụ

- Domain **orders.test.example** chỉ là placeholder, không phải target thực để scan.
- Đoạn mã giả định Java HttpClient, JUnit và API contract cụ thể.
- Test không tự cấp tokens hoặc seed fixtures. Runner/fixture setup cần được thiết kế riêng.
- Target allowlist trong source là **defense-in-depth**; CI và network phải chặn scan ngoài scope.
- Test A không có membership B cần được xác nhận từ trusted fixture setup.
- Test không inspect mọi sensitive fields hay headers; production-grade test nên parse DTO và đối chiếu data classification.
- Nếu policy dùng 403, assertions phải sửa theo API contract; **không nới lỏng vô điều kiện** để nhận mọi response lỗi.
- Khi HTTP request FAIL do network hoặc 401 vì token expired, không được xem đó là retest PASS.
- Không có scanner/exploit nào được thực thi; code là **minh họa cho test design**.

### 13.4. Làm sao dùng CI để chạy regression?

Trong authorized pipeline:

1. Deploy artifact có digest được pin.
2. Seed A/B orders và membership với test-only identities.
3. Verify positive controls trước.
4. Chạy JUnit HTTP tests.
5. Chạy targeted variants: headers, cache, exports.
6. Bảo vệ reports và redacted logs.
7. Collect build/target/policy revision.
8. Fail gate nếu required tests FAIL/BLOCKED/NOT_RUN.
9. Cleanup tokens, fixtures và resources.
10. Post-deploy verify theo release policy.

Không gộp **unit tests**, **integration security tests** và **pentester retest sign-off** làm một kết quả không phân biệt.

## 14. Variants và bypass: trọng tâm của retest hiệu quả

### 14.1. Vì sao thử lại một request là chưa đủ?

Nếu lỗi do architectural root cause, một patch ở lớp presentation có thể chỉ chặn payload gốc. Những paths khác có thể vẫn sử dụng backend insecure.

Ví dụ:

- GET /orders/{id} đã sửa, POST /orders/bulk-read chưa sửa.
- API v2 còn dùng repository method cũ.
- Search endpoint không lọc tenant.
- Redis cache key dùng order ID mà không xét tenant.
- Worker nhận message từ producer chưa authenticated.
- Admin/support console dùng privileged bypass.
- Truy cập backend trực tiếp bỏ qua gateway guard.
- Feature flag hoặc debug route không đồng nhất.
- An older mobile API tiếp tục lộ dữ liệu.

### 14.2. Các chiều biến thể

| Chiều | Câu hỏi |
| --- | --- |
| **Actor** | User thường, tenant admin, service account, support |
| **Resource** | Own, other-user, other-tenant, missing, deleted |
| **Operation** | Read, update, export, search, delete, refund |
| **Protocol/route** | REST v1/v2, GraphQL, gRPC, WebSocket, admin route |
| **State** | Active, revoked, suspended, expired, pending |
| **Channel** | API gateway, internal service, async worker |
| **Cache** | Cold/warm, invalidated, shared key |
| **Region/replica** | Patched/new vs remaining old |
| **Failure** | Auth service timeout, DB/cache down |
| **Concurrency** | Duplicate request, retry, race/TOCTOU |
| **Input** | Type, encoding, boundary size, canonicalization |
| **Config** | Policy version, feature flags, WAF, IAM |

### 14.3. Chọn variants theo root cause

Không cần thử vô hạn. Tập trung:

1. Root cause nằm ở shared layer nào?
2. Thành phần nào có cùng pattern?
3. Có boundary nào cho phép bypass?
4. Có state transition bị bỏ sót?
5. Có data stores/caches làm bỏ qua filter?
6. Fix có thay default behavior ở nơi khác?
7. Test nào cần để tăng confidence đủ theo risk?

Reviewer phải ghi **variant coverage và excluded paths**, tránh tuyên bố “không còn bypass nào” khi chưa có bằng chứng.

## 15. Retest ở cache, worker, export và phân quyền gián tiếp

### 15.1. Cache

Một API kiểm tra authorization sau khi lấy cache có thể trả dữ liệu sai nếu cache key hoặc entry không gắn tenant.

Test:

- User B làm nóng cache của order B.
- User A yêu cầu order B.
- Không có dữ liệu B được tiết lộ.
- Cache miss/hit paths đều giữ permission rule.
- Cache invalidation sau revocation hoặc resource owner change.
- Test trên đúng deployment config/Redis namespace.

### 15.2. Report/export worker

Một service worker thường có DB role rộng. API-side authorization không bảo vệ nếu worker tin event do caller có thể giả.

Test:

- Event được tạo từ trusted authorization decision.
- Worker kiểm tra actor/tenant/resource scope theo thiết kế.
- Forged tenant/event không tạo file trái quyền.
- Duplicate/out-of-order messages không tạo dữ liệu sai.
- Link chỉ cho recipient được phép.
- Expired/revoked download bị deny theo policy.
- Audit nối actor/event/artifact.
- Cleanup không xóa dữ liệu ngoài test scope.

### 15.3. Search và bulk

- Filter resource ownership ở query/search index.
- Pagination không trộn dữ liệu nhiều tenants.
- Aggregation không lộ private statistics theo policy.
- Bulk export không vượt quota và không chỉ lọc trang đầu.
- Background jobs có permission context đáng tin.
- Không gửi raw PII vào logs/error responses.

### 15.4. Direct backend routes

Nếu gateway chặn nhưng backend nhận request trực tiếp, retest cần phân biệt:

- Backend có cơ chế authn/authz riêng hoặc trust-boundary bảo vệ được không?
- Network rules có chặn direct access trong runtime thật không?
- Service-to-service identities có quá quyền không?
- Đường alternate hostname/IP/ingress tồn tại không?

Thử nghiệm network phải nằm trong ROE, không dò quét IP/host ngoài phạm vi.

## 16. Retest các nhóm finding khác nhau

### 16.1. Input injection

Với SQL/command/template injection:

- Review root-cause fix: parameter binding, API choice, context-aware encoding.
- Test safe input variations và expected query/output behavior.
- Xem dynamic query fragments hoặc alternate sinks.
- Kiểm tra least-privilege backend account.
- Xác minh error handling/logging không làm lộ cấu trúc/dữ liệu.
- Không dùng destructive payload để chứng minh trên production.
- Retest theo **security property**, không chỉ chặn một chuỗi payload.

### 16.2. Cross-site scripting (XSS)

- Xác định context: HTML text, attribute, JavaScript, URL, DOM.
- Test harmless marker trong authorized sandbox/browser.
- Xác minh output encoding/safe DOM APIs đúng context.
- Stored content có còn được render ở giao diện khác?
- Content Security Policy là defense-in-depth, không thay fix root cause.
- Review sanitizer defaults và client framework behavior.
- Ghi browser/runtime assumptions và test fixtures.

Không coi “không có popup trong một browser” là bằng chứng XSS không thể xảy ra.

### 16.3. Server-side request forgery (SSRF)

- Kiểm tra server-side destination policy, không chỉ regex URL.
- Thử controlled endpoint trong test-only network.
- Xác minh redirect handling, DNS resolution, IPv4/IPv6 và proxy.
- Egress enforcement có tồn tại trên workload thực?
- HTTP client có gửi credentials tới destination trái phép không?
- Có internal admin/metadata target bị expose qua allowed paths không?
- Test đúng trust boundary; không gọi host không thuộc quyền kiểm tra.

### 16.4. File upload và path traversal

- Xác nhận filenames/storage paths do server quản lý.
- Kiểm tra canonicalization và containment theo storage design.
- Đánh giá symlink/race khi file tree có untrusted writers.
- Verify permission/ownership của file.
- MIME/content validation và antivirus nếu requirement áp dụng.
- Không upload executable payload ngoài sandbox.
- Cleanup artifacts theo run ID.

### 16.5. Session và authentication

- Token invalid/expired/revoked bị deny.
- Token issuer/audience/signature binding đúng.
- MFA/step-up cho privileged operations.
- Session fixation và logout/recovery semantics.
- Password reset/account recovery không bypass checks.
- Old tokens có bị invalidate sau reset theo policy?
- Cookies: Secure, HttpOnly, SameSite theo kiến trúc.
- CSRF defense khi dùng cookie session.
- IdP failure không tự phát token tin cậy.

### 16.6. Cryptography và secrets

- Xác minh patch dùng approved algorithm/mode/config theo policy.
- Key rotation đã cập nhật consumers và xử lý old keys?
- Old compromised credential bị revoke thật?
- TLS hostname/certificate validation vẫn bật.
- Secrets không còn trong logs/telemetry/artifacts.
- Backup/restore có giữ key availability và confidentiality phù hợp?
- Không dùng secrets production cho test nếu có thể tránh.
- Code patch chưa đủ nếu runtime config vẫn cho insecure fallback.

### 16.7. IAM/cloud/Kubernetes

- Effective permissions của principal/role sau fix.
- Unauthorized actions thật sự bị từ chối trong sandbox.
- Policy inheritance và wildcard grants.
- ServiceAccount/workload identity scopes.
- NetworkPolicy/Ingress egress thực sự enforce.
- Image/runtime config có drift khỏi manifest không.
- Kubernetes privileges, capabilities, secret mounts.
- Resource consumers/regions chưa nhận update.
- Cluster/cloud provider shared-responsibility limitations.

### 16.8. Business logic

- Refund/transfer không vượt quyền/số tiền.
- Duplicate/replay không tạo side effect lặp.
- State transitions hợp lệ/không hợp lệ đúng.
- Actor/approval context được kiểm tra tại commit.
- Concurrency không vượt invariant.
- Async status không báo success khi transaction chưa commit.
- Audit log ghi decisions và outcomes đúng.
- Positive business flow không bị phá bởi security fix.

### 16.9. Availability/rate controls

Không kiểm tra kiểu phá hoại trên production. Có thể:

- Bounded burst và timeout tests ở sandbox.
- Kiểm tra quota theo identity/tenant/resource.
- Negative tests với retry/bypass path.
- Verify no global lockout bất công.
- Compare resource usage và latency theo baseline.
- Record coverage limits và khả năng load thật khác lab.

## 17. Compensating controls và remediation một phần

### 17.1. Fix root cause

Ví dụ:

- BOLA: server-side resource authorization.
- SQL injection: parameter binding đúng.
- SSRF: authorized fixed destination + egress.
- Exposed secret: revoke/rotate và chặn leak source.
- Cloud IAM: thu hẹp effective permissions.

Nếu root cause bị loại bỏ trong assessed scope, có thể đề xuất **VERIFIED_FIXED** khi đủ evidence.

### 17.2. Compensating control

Ví dụ:

- WAF rule chặn một exploit form trong lúc chưa sửa code.
- Network ACL chặn external access vào vulnerable service.
- Disable feature dễ khai thác.
- Restrict IAM permissions.
- Increase monitoring và incident containment readiness.

Retest có thể kết luận:

> **MITIGATED:** đường tấn công được giảm bởi control hiệu quả theo tests và scope đã xét, nhưng vulnerability gốc còn tồn tại.

Không ghi “FIXED” chỉ vì đường request ban đầu đã bị WAF chặn nếu backend vẫn vulnerable.

### 17.3. Evidence cho compensating control

| Control | Retest evidence | Không được tự suy |
| --- | --- | --- |
| WAF rule | Effective rule version, allowed/blocked variants | Mọi payload đều bị chặn |
| Network isolation | Negative connectivity tests từ đúng network position | Không có alternate route |
| Feature disable | Runtime config + request behavior | Code vulnerable không còn trong hệ thống |
| IAM restriction | Effective principal denied-action test | Không có inherited/alternate privilege |
| Token rotation | Old credential thật sự bị deny, new works | Mọi stolen sessions đã kết thúc |
| Logging alert | Event delivery + triage process | Exploit được ngăn chặn |
| Rate limiting | Bounded tests cho keys và scope | Không có distributed bypass |
| Database RLS | Queries với low-privilege roles đúng | Service account không có bypass khác |

### 17.4. Partial remediation

Một lỗi được sửa ở GET nhưng còn ở export:

- Tình trạng **PARTIALLY_FIXED**.
- Evidence và affected paths cụ thể.
- Owner/due date cho phần còn lại.
- Interim mitigations và monitoring.
- Không đóng parent finding quá sớm.

Nếu một fix bị deploy 70% fleet, tương tự phải report **partial rollout**.

## 18. Retest phải kiểm tra regressions của bản sửa

### 18.1. Security regression

Một fix có thể khiến:

- User authorized bị deny mọi thứ.
- Admin bypass được mở rộng không chủ ý.
- Policy timeout fail-open.
- Authorization cache không được invalidate.
- Audit events bị mất.
- CSRF protection bị tắt để sửa API.
- TLS validation bị bỏ qua để giải quyết connection issue.
- Secrets xuất hiện trong logs debug.
- Error response tiết lộ object existence.
- Rate limit lockout nhầm nhiều users.

### 18.2. Functional regression

Ví dụ Orders API:

- User A vẫn tạo/đọc đơn hàng của chính mình.
- Tenant admin A vẫn làm đúng authorized reports.
- Refund hợp lệ không bị double processing.
- Search/pagination không mất hoặc trộn dữ liệu.
- Worker retries ổn định.
- API contract không thay đổi ngoài intended design.
- Latency/availability trong guardrails phê duyệt.

### 18.3. Regression matrix

| Change | Positive check | Negative check | Failure/boundary |
| --- | --- | --- | --- |
| Tenant filter | Owner reads own order | Cross-tenant denied | Membership change |
| Token validation | Valid signed token works | Invalid/revoked token rejected | Key rotation |
| WAF | Legitimate operation works | Scoped suspicious request blocked | Rule update/alternate ingress |
| File validation | Approved file upload works | Unsafe path/type rejected | Boundary size/encoding |
| Webhook idempotency | Valid event processed once | Duplicate no second effect | Out-of-order retry |
| New logging redaction | Essential audit remains | Secret not logged | Exception/error traces |
| SSRF allowlist | Approved partner works | Unapproved destination denied | Redirect/DNS change |

### 18.4. Các retest thất bại dù original symptom không còn

Nếu code không còn lộ dữ liệu nhưng mọi chức năng kinh doanh đã hỏng, một kết luận tốt phải nói rõ:

> **Original issue not reproducible under current conditions, but remediation creates blocking regression; closure not approved.**

Không đánh dấu VERIFIED_FIXED toàn diện khi các security hoặc service objectives quan trọng khác bị phá.
## 19. Kết quả retest: phân biệt tình trạng thực thi và kết luận bảo mật

### 19.1. Hai loại trạng thái không được trộn

Một lần retest luôn có ít nhất hai chiều:

1. **Execution status:** phép thử có thực sự chạy đúng điều kiện và có kết quả đáng tin không?
2. **Security disposition:** vulnerability/root cause đã fixed, còn tồn tại, chỉ mitigated hay chưa đủ căn cứ?

Ví dụ:

- Test hoàn tất, cross-tenant request bị deny và preconditions đúng → **EXECUTED** + có thể **VERIFIED_FIXED** trong scope.
- Test nhận 404 vì Order B không tồn tại → **INVALID_PRECONDITION**, **không được** VERIFIED_FIXED.
- Test không truy cập endpoint do deployment lỗi → **BLOCKED**, không có security conclusion.
- Scan chạy xong, WAF chặn path nhưng code còn vulnerable → **MITIGATED**, chưa fixed.
- Test không thấy biểu hiện gốc do feature tạm tắt → **NOT_REPRODUCIBLE_UNDER_CONDITIONS**, cần đánh giá scope/config.
- Code đã sửa nhưng một API version khác còn rò → **PARTIAL**, finding vẫn mở.

### 19.2. Execution statuses

| Trạng thái | Điều kiện | Có đủ bằng chứng security PASS? |
| --- | --- | --- |
| **EXECUTED_VALID** | Preconditions đúng, target xác nhận, test oracle đạt | Có thể, tùy actual result |
| **EXECUTED_FAILED_ASSERTION** | Test chạy nhưng expected secure behavior không đạt | Không |
| **BLOCKED_ENVIRONMENT** | Service/test dependency không khả dụng | Không |
| **BLOCKED_AUTHORIZATION** | Không có quyền retest/scope không hợp lệ | Không |
| **INVALID_PRECONDITION** | Account/resource/version không đúng | Không |
| **NOT_RUN** | Không thực hiện | Không |
| **PARTIALLY_EXECUTED** | Chỉ một phần test matrix chạy | Chỉ cho phần có evidence |
| **INCONCLUSIVE** | Evidence mâu thuẫn hoặc test oracle không phân biệt | Không |
| **DEFERRED_WITH_APPROVAL** | Bước hoãn có thẩm quyền | Không; cần follow-up |

**Không gộp BLOCKED và FAIL:** một sự cố test infrastructure không có nghĩa vulnerability vẫn exploitable; nhưng nó cũng không cho phép closure.

### 19.3. Security dispositions

| Disposition | Nghĩa | Finding state |
| --- | --- | --- |
| **VERIFIED_FIXED** | Root cause/control được xác minh khắc phục trong assessed scope | Có thể đề xuất closure |
| **STILL_VULNERABLE** | Lỗi gốc còn tái hiện hoặc bypass tồn tại | OPEN, remediate |
| **PARTIALLY_FIXED** | Một phần paths/assets fixed, phần còn lại có risk | OPEN hoặc child findings |
| **MITIGATED_NOT_FIXED** | Exposure giảm bởi control bù trừ, root cause còn | OPEN/mitigated theo policy |
| **NOT_REPRODUCIBLE** | Không tái hiện trong điều kiện đã thử, chưa đủ chứng minh fix | REVIEW/INSUFFICIENT |
| **INSUFFICIENT_EVIDENCE** | Preconditions/version/coverage không đủ | Cần test bổ sung |
| **NOT_APPLICABLE** | Có evidence finding không áp dụng trong scope xác định | Review disposition |
| **FALSE_POSITIVE_CONFIRMED** | Finding gốc sai theo bằng chứng, trong scope đã xác minh | Có thể đóng với rationale |
| **REGRESSION_DETECTED** | Fix tạo lỗi security/function quan trọng khác | Block/reopen hoặc new issue |
| **RISK_ACCEPTED** | Residual risk được chấp nhận đúng thẩm quyền | Không đồng nghĩa fixed |

### 19.4. Retest PASS không phải security gate PASS cho toàn release

Một finding đã VERIFIED_FIXED nhưng release vẫn có thể:

- Other open P0/P1 findings.
- Missing audit/monitoring.
- Scanner/test suites bị skip.
- Artifact production không khớp tested build.
- New architecture risk chưa đánh giá.
- Data migration regression chưa xử lý.

Vì vậy cần tách **per-finding retest disposition** khỏi **overall release decision**.

### 19.5. Khi nào được ghi VERIFIED_FIXED?

Một bộ điều kiện thực hành:

- Đúng finding/root cause và affected population.
- Approved scope và safety constraints.
- Target artifact/config/patch identity rõ.
- Preconditions gốc được xác minh đầy đủ.
- Original unsafe condition không còn gây violation.
- Các closely related variants/bypasses theo scope đã kiểm.
- Positive controls vẫn hoạt động.
- Không có blocking security/functional regression.
- Evidence đầy đủ, protected, review được.
- Residual risks/untested paths được khai báo.
- Reviewer có thẩm quyền xác nhận.

Nếu thiếu runtime verification, kết luận có thể giới hạn: **VERIFIED_FIXED_IN_STAGING_SCOPE**, không tuyên bố full production.

## 20. False negative trong retest và cách tránh

### 20.1. Những nguyên nhân gây false PASS

- Order B không tồn tại.
- User A token expired nên mọi request trả 401.
- Test account không có role giống attacker precondition.
- Scanner quét sai host/path.
- App build cũ hoặc khác bản fix.
- Feature flag disable đường code có lỗi.
- WAF ở staging chặn test nhưng production bypass được.
- Test chỉ nhìn status code.
- Input bị application cache/sanitizer xử lý tình cờ.
- Test chỉ exercise một HTTP method.
- Worker chưa chạy, async state chưa observable.
- Một replica cũ chưa được truy cập.
- Load balancer chỉ route test tới patched nodes.
- Payload khác nguyên nhân lỗi nên không đánh giá được.
- Test data không đủ state khiến request bị reject sớm.
- Test retries che một lần có disclosure.
- Test environment thiếu integration thực tế ảnh hưởng exploit path.

### 20.2. Positive control

Đối với BOLA:

1. User B thấy Order B với marker synthetic rõ.
2. User A thấy Order A.
3. User A không có quyền B theo trusted identity fixture.
4. Order B vẫn tồn tại sau test.
5. Request A→B chạy đúng path/artifact.
6. Response không chứa B data.
7. DB/export/cache không tạo side effect sai.
8. Audit outcome đúng policy.

Nếu không chứng minh 1–5, test A→B trả 404 là **inconclusive**.

### 20.3. Negative control

Với một test framework hoặc scanner, có thể giữ một **known intentionally vulnerable fixture trong lab riêng** để chắc chắn công cụ còn phát hiện pattern khi được phép. Đây là rule/suite validation, không phải yêu cầu đặt vulnerability trong production.

### 20.4. Retest một lần có đủ không?

Tùy threat:

- Stateless authn error có thể kiểm chứng bằng nhiều test cases.
- Race condition cần nhiều lịch thực thi có giới hạn và controlled timing.
- Cache/stale policy đòi testing theo time/state.
- Multi-region rollout cần population coverage.
- Intermittent authorization failure cần correlation/incident review.
- SSRF có redirect/DNS variations cần kiểm tra đúng policy.
- Một lần PASS không đủ để khẳng định tuyệt đối không có rare path.

Cần định nghĩa **confidence** theo phương pháp và rủi ro, không lấy số lần chạy tùy tiện để nói chắc chắn.

## 21. Evidence retest: cái gì phải được giữ?

### 21.1. Bộ bằng chứng tối thiểu

| Loại | Bằng chứng | Mục đích |
| --- | --- | --- |
| **Original finding** | ID, report version, original observed effect | Biết điều cần kiểm |
| **Remediation record** | Patch/PR/change root-cause rationale | Biết gì được sửa |
| **Scope/authorization** | ROE, target, time và constraints | Chứng minh kiểm thử hợp lệ |
| **Preconditions** | Test users, roles/tenants, resource ownership | Chống false PASS |
| **Artifact** | Commit, build, digest, runtime revision | Đúng phiên bản |
| **Config** | Auth policy, gateway, feature flag, DB role | Đúng security context |
| **Test design** | Case ID, expected/actual, risk-based variants | Có oracle rõ |
| **Execution** | Tool, command profile, timestamps, request metadata | Tái kiểm tra được |
| **Response** | Redacted HTTP/result/assertion refs | Bằng chứng quan sát |
| **Side effect** | DB state, audit, worker/export/retry outcome | Không chỉ HTTP status |
| **Control** | Effective WAF/network/IAM version và test | Mitigation effectiveness |
| **Coverage** | URLs/roles/tenants/regions/exclusions | Giới hạn kết luận |
| **Reviewer** | Người đánh giá và thời điểm | Accountability |
| **Disposition** | VERIFIED_FIXED/PARTIAL/OPEN/UNKNOWN | Quyết định có căn cứ |
| **Residual risk** | Owner, accepted/deferred work, expiry | Theo dõi risk còn lại |
| **Release** | Deployment verification và link change | Hỗ trợ closure production |

### 21.2. Evidence không nên chứa dữ liệu gì?

Không nên đưa vào báo cáo chung:

- Raw production access/refresh tokens.
- Passwords, recovery factors, private keys.
- Full customer records, data dumps.
- Unredacted HAR/Cookie/Authorization headers.
- Vulnerability exploitation secrets/callback credentials.
- Screenshot chứa PII khi không cần.
- Large private response bodies.
- CI environment secrets hoặc infrastructure admin tokens.

Sử dụng **synthetic data**, redact/tokenize và private evidence refs. Nếu evidence quan trọng buộc chứa thông tin nhạy cảm, lưu có kiểm soát ACL, encryption, retention và audit phù hợp.

### 21.3. Reproducibility

Một reviewer độc lập cần có khả năng hiểu:

- Dùng actor và resource fixtures nào.
- Vì sao actor không có quyền.
- Môi trường/version nào đã được test.
- Expected result là gì.
- Actual result ra sao.
- Những test variants nào đã chạy.
- Điều gì dẫn đến verdict.
- Những gì phải thay trước khi rerun.

Không cần công khai payload nhạy cảm để report tái kiểm tra được; có thể lưu protected test scripts hoặc mô tả kiểm chứng an toàn.

### 21.4. Chất lượng bằng chứng

- **Relevant:** hỗ trợ đúng finding/security claim.
- **Accurate:** actual data/state không bị nhầm environment.
- **Complete within scope:** đủ những variants có ảnh hưởng lớn.
- **Fresh:** đúng deployment hiện tại.
- **Traceable:** finding → patch → test → deployment.
- **Integrity-protected:** logs/reports không bị sửa trái phép.
- **Repeatable:** test có method và fixtures rõ.
- **Confidential:** không tiết lộ secrets/PII.
- **Independent:** reviewer phù hợp risk tier.
- **Transparent uncertainty:** không che BLOCKED/NOT_RUN.

## 22. Mẫu báo cáo retest cho kỹ sư và risk owner

### 22.1. Phần executive summary

Một summary hữu ích nêu:

- Assessment ID và original pentest report.
- Số findings trong scope và severity/priority.
- Bao nhiêu verified fixed, vẫn open, partial, mitigated, blocked.
- Những critical exposure còn lại.
- Scope/target versions và giới hạn.
- Recommended actions, owners, deadlines.
- Có cần incident response hoặc release hold không.

### 22.2. Per-finding section

| Trường | Nội dung |
| --- | --- |
| Finding ID/title | Duy trì định danh gốc |
| Original risk | Severity/impact, preconditions |
| Original affected path | Asset/endpoint/role |
| Fix description | Change record và root cause |
| Test target | Environment, build, config identity |
| Retest objective | Security invariant |
| Test cases | Positive, negative, variants |
| Actual results | Expected/actual, protected refs |
| Test completeness | Executed/blocked/partial |
| Observed residual behavior | Nếu còn |
| Disposition | Fixed/partial/mitigated/unknown |
| Recommendation | Remediate, extend retest, close |
| Reviewer/signoff | Người đánh giá |
| Next trigger | Rollback, new route, policy change |

### 22.3. Không nên nói quá mức

**Câu tốt:**

> Finding PT-014 không còn tái hiện ở Orders API staging trên build đã xác nhận; các testcase object-level authorization cho user A/B và đường cache trong scope đạt. Worker export và production chưa được kiểm tra; kết luận fix chỉ áp dụng cho scope đã nêu.

**Câu yếu:**

> PT-014 không còn tồn tại trong hệ thống.

### 22.4. Ví dụ thông điệp kết quả

> Pentest retest của build đã được kiểm tra xác nhận đường request gốc không còn vi phạm tenant isolation. Tuy nhiên, một phiên bản API legacy nằm ngoài test scope và production rollout chưa có bằng chứng hoàn tất. Đề xuất giữ finding ở trạng thái PARTIALLY_VERIFIED hoặc INSUFFICIENT_PRODUCTION_EVIDENCE cho đến khi bổ sung kiểm tra và phê duyệt kết luận tương ứng.

Một báo cáo tốt giúp người quyết định biết **nên làm gì tiếp**, không chỉ báo đỏ/xanh.

## 23. Ví dụ YAML: Hồ sơ retest cho finding đa tenant

Dữ liệu sau là **mẫu minh họa**, chưa có pentest hoặc test run thật. Các trường evidence vẫn để NOT_RUN, không giả vờ PASS.

~~~yaml
assessment_id: "PENTEST-RETEST-DEMO-010"
module: "SECURITY_SECURITY_ASSURANCE"
chapter: "Penetration testing"
topic: "Retest"
assessment_type: "TARGETED_FINDING_RETEST"
assessment_status: "DRAFT"
original_finding:
  id: "PT-ORDERS-014"
  title: "Cross-tenant order disclosure"
  class: "BROKEN_OBJECT_LEVEL_AUTHORIZATION"
  original_severity: "HIGH_DEMO_ONLY"
  report_reference: "NOT_VERIFIED"
  original_exploitation_evidence: "NOT_IMPORTED"
  root_cause_confirmed: false
scope:
  service: "orders-api"
  environment: "isolated-integration"
  approved_target_host: "orders.test.example"
  authorized_window: "NOT_SCHEDULED"
  test_data_classification: "SYNTHETIC_ONLY"
  allowed_methods:
    - "GET"
  excluded_paths:
    - "production-refund"
    - "third-party-provider-internals"
rules_of_engagement:
  authorization_reference: null
  approved: false
  destructive_testing_allowed: false
  stop_conditions_defined: false
remediation:
  patch_change_id: "NOT_VERIFIED"
  fix_type: "server-side-resource-authorization"
  source_commit: null
  expected_artifact_digest: null
  deployed_artifact_digest: null
  auth_policy_revision: null
identities:
  user_a_tenant: "tenant-a-synthetic"
  user_b_tenant: "tenant-b-synthetic"
  membership_preconditions_verified: false
  order_b_exists_and_is_owned_by_b: "NOT_VERIFIED"
tests:
  - id: "RT-ORD-01"
    purpose: "authorized-user-a-read"
    expected: "ALLOW_OWN_ORDER"
    execution: "NOT_RUN"
  - id: "RT-ORD-02"
    purpose: "authorized-user-b-read"
    expected: "ALLOW_OWN_ORDER"
    execution: "NOT_RUN"
  - id: "RT-ORD-03"
    purpose: "cross-tenant-read-denied"
    expected: "DENY_NO_B_DATA"
    execution: "NOT_RUN"
  - id: "RT-ORD-04"
    purpose: "forged-tenant-header"
    expected: "DENY_NO_B_DATA"
    execution: "NOT_RUN"
  - id: "RT-ORD-06"
    purpose: "cross-tenant-cache"
    expected: "DENY_NO_B_DATA"
    execution: "NOT_RUN"
  - id: "RT-ORD-08"
    purpose: "forged-worker-export"
    expected: "NO_UNAUTHORIZED_ARTIFACT"
    execution: "NOT_RUN"
coverage:
  tested_regions: []
  tested_api_versions: []
  tested_roles: []
  excluded_variants:
    - "legacy-api-not-yet-assessed"
evidence_refs: []
risk:
  owner: "Orders Product Risk Owner"
  residual_risk: "NOT_ASSESSED"
  exception_approved: false
  exception_expiry: null
review:
  pentester: null
  engineering_owner: "Orders API Engineering"
  assurance_reviewer: null
  reviewed_at: null
verdict:
  execution_status: "NOT_RUN"
  security_disposition: "INSUFFICIENT_EVIDENCE"
  original_finding_closed: false
  design_effectiveness: "NOT_VERIFIED"
  implementation_effectiveness: "NOT_VERIFIED"
  operating_effectiveness: "NOT_VERIFIED"
  next_action: "Authorize scope and execute retest with validated fixtures"
~~~

### 23.1. Tại sao không tự gán VERIFIED_FIXED cho template?

Vì chưa có:

- ROE đã ký hoặc authorization trong process.
- Running artifact identity.
- Positive control cho user B.
- Actual request/response/assertion.
- Review variants và bypass.
- Production rollout evidence.
- Reviewer kết luận.

Kết luận hợp lệ là **INSUFFICIENT_EVIDENCE**.

### 23.2. Không nhất thiết dùng YAML trong tổ chức

Có thể dùng:

- Pentest report PDF.
- Vulnerability management tickets.
- GRC/control evidence system.
- SARIF hoặc scanner reports khi phù hợp.
- Structured JSON từ API test runner.
- CI test artifacts với immutable IDs.

Quan trọng là giữ **cùng semantic fields và audit trail**, không phải chọn đúng một định dạng.

## 24. CI/CD hóa retest mà không biến nó thành scanner thay pentester

### 24.1. Retest nào nên tự động?

Phù hợp automation:

- Known BOLA regression với test users/fixtures.
- Authentication/role negative API tests.
- Request validation và safe parser cases.
- Webhook signature/replay business tests.
- Secret redaction/log checks trên synthetic tokens.
- Effective config/API headers.
- Dependency patched artifact identity.
- Cache tenant isolation.
- Export authorization trong isolated integration environment.

Có thể cần manual expert review:

- Multi-step business abuse chains.
- Complex privilege escalation.
- Chained weaknesses qua nhiều trust boundaries.
- Deep cloud lateral movement scenario.
- Social engineering hoặc physical testing.
- Race cần controlled environment và state inspection.
- Vendor-managed internals không thể kiểm thử trực tiếp.

### 24.2. Ví dụ pipeline retest

~~~mermaid
flowchart TD
    A["Finding marked READY_FOR_RETEST"] --> B["Verify patch, scope, authorization"]
    B --> C["Build or identify immutable artifact"]
    C --> D["Deploy isolated test target"]
    D --> E["Seed synthetic identities and resources"]
    E --> F{"Preconditions and target identity valid?"}
    F -- "No" --> X["BLOCKED: collect missing evidence"]
    F -- "Yes" --> G["Run original targeted security regression"]
    G --> H["Run positive, variant and failure tests"]
    H --> I["Capture results + environment + artifact"]
    I --> J{"Execution and assertions valid?"}
    J -- "No" --> K["OPEN / PARTIAL / INCONCLUSIVE"]
    K --> A
    J -- "Yes" --> L["Pentester/security review"]
    L --> M["Risk-based release/closure decision"]
    M --> N["Deploy approved artifact / runtime verify"]
    N --> O["Monitor changes and re-open triggers"]
~~~

### 24.3. CI job skeleton mô tả

~~~yaml
pipeline:
  id: "orders-api-penetration-retest"
  trigger: "finding-ready-for-retest"
  jobs:
    - id: "verify-scope-and-authority"
      must_pass: true
    - id: "identify-patched-artifact"
      must_pass: true
    - id: "deploy-test-target"
      needs: ["identify-patched-artifact"]
    - id: "prepare-test-fixtures"
      needs: ["deploy-test-target"]
    - id: "verify-preconditions"
      needs: ["prepare-test-fixtures"]
      must_pass: true
    - id: "targeted-retest"
      needs: ["verify-preconditions"]
      must_pass: true
    - id: "related-security-regressions"
      needs: ["targeted-retest"]
    - id: "publish-protected-evidence"
      needs: ["related-security-regressions"]
      required_even_on_failure: true
    - id: "cleanup"
      required_even_on_failure: true
  gate:
    required_execution_status: "EXECUTED_VALID"
    require_reviewer: true
    require_artifact_identity: true
    invalid_preconditions_are_pass: false
    scanner_timeout_is_pass: false
    missing_report_is_pass: false
~~~

Đây là **schema mô tả**, không phải YAML executable của GitHub Actions/GitLab/Jenkins. Cần chuyển đổi và kiểm tra các guarantees của provider tương ứng.

### 24.4. Automation phải tách trusted và untrusted workflows

Một PR từ nguồn không tin cậy không nên được cấp:

- Production admin tokens.
- Sign/publish artifact credentials.
- Full internal network reachability.
- Cloud IAM administrator.
- GRC approval permissions.
- Scanner credentials có quyền truy cập dữ liệu thật.

CI job thực thi code của PR có thể bị lạm dụng nếu chạy trong trust boundary không đúng. Cần phân quyền runner, allowlist target và chỉ đưa secrets cho trusted stages có approval.

### 24.5. Gate semantics

Một release gate tốt không chỉ đọc **test command exit code**:

- Đúng required jobs có chạy không?
- Precondition setup có thành công không?
- Test failures có bị retry che không?
- Report có được tạo và parse đầy đủ?
- Tested build có đúng release artifact?
- Có new regressions hoặc blockers?
- Có exception được approval và còn hiệu lực?
- Production post-deploy verification có bắt buộc không?
- Các known affected assets còn ngoài rollout?

**Retest automated PASS** có thể là đầu vào cho pentester review, không tự động thay chữ ký của người có thẩm quyền nếu policy yêu cầu.

## 25. Retest sau khi triển khai production

### 25.1. Post-deployment verification

Tùy risk và ROE, những kiểm tra an toàn có thể gồm:

- Deployed image digest/config revision.
- Runtime package/host version.
- Critical authn/authorization safe negative tests với synthetic identities.
- WAF/network policy effective state.
- Audit event delivery và alert readiness.
- Canary error/latency/business invariant metrics.
- All affected instances/regions patched.
- Không có legacy route vẫn dẫn tới vulnerable instance.
- Cache/queue workers dùng versions/policy mới.
- Known vulnerability indicators giảm khi có chứng cứ phù hợp.

### 25.2. Khi production không cho phép re-enact exploit

Có thể kết hợp:

- Controlled staging exploitation/retest.
- Production artifact/config identity.
- Safe runtime tests với synthetic data.
- Effective network/IAM policy review.
- Operational audit/monitoring evidence.
- Change approval và residual-risk assessment.

Báo cáo phải nêu **mức suy luận**: staging retest + production identity evidence hỗ trợ claim trong assumptions nào, những khác biệt nào chưa kiểm tra.

### 25.3. Canary có thể tạo kết luận sai

Nếu canary 10% traffic chạy patch:

- Retest trên canary PASS.
- 90% traffic còn hướng về vulnerable version.
- Finding chưa fixed cho full production.

Ngoài ra, traffic canary có thể không exercise authorization path; cần targeted safe tests và coverage review.

### 25.4. Rollback tái đưa vulnerability

Nếu đội vận hành rollback vì lỗi availability:

- Có thể quay về bản còn lỗ hổng.
- Finding phải được **reopened/reassessed**.
- Cần safe rollback alternative hoặc roll-forward.
- Thêm mitigation tạm thời theo thẩm quyền.
- Xác nhận effective runtime versions.
- Cập nhật assurance report và risk dashboard.

Không coi một retest PASS cũ là bằng chứng hiện hành sau rollback.

## 26. Retest và thay đổi threat context

### 26.1. Những trigger cần đánh giá lại

- Có exploitation evidence mới.
- Component/service chuyển từ internal sang public.
- Tài sản nâng data classification.
- User/tenant population thay đổi lớn.
- Feature flag bật vulnerability path.
- Vendor patch bị thu hồi.
- Dependency transitively kéo version có lỗi trở lại.
- WAF/NetworkPolicy/IAM rule bị disable.
- API version mới sử dụng code path cũ.
- Cache architecture đổi.
- Incident cho thấy bypass.
- Scanner framework/rules update.
- Infrastructure migration hoặc identity model redesign.

### 26.2. Retest không phải closure vĩnh viễn

Một finding verified fixed tại thời điểm T1 có thể được đưa lại vào risk register khi:

- Có regression.
- Version cũ được deploy lại.
- New exploit variant ảnh hưởng control.
- Shared dependency gỡ mitigation.
- Phạm vi mới không còn phù hợp test gốc.

Giữ historical verdict, nhưng phải có **new assessment** theo state hiện tại; không xóa bằng chứng cũ.

### 26.3. Recurrence khác một vulnerability mới

- **Recurrence:** cùng root cause/pattern xuất hiện lại.
- **New variant:** exploit path mới mà patch trước không bao phủ.
- **Related finding:** common architectural issue, khác affected asset.
- **New issue:** bug riêng không phải một bản tái hiện finding gốc.

Grouping đúng giúp triage, remediation owner và systemic prevention.

## 27. Risk acceptance, exception và tranh luận về verdict

### 27.1. Ai quyết định?

- Pentester/security tester: mô tả evidence, technical feasibility, verified behavior và limitations.
- Engineering owner: giải thích fix, deployment và tests.
- AppSec/security architect: xem root cause, variants và adequacy.
- Risk owner: quyết định residual risk/exception theo thẩm quyền.
- Release owner: quyết định rollout dựa trên policy.
- Assurance reviewer: đánh giá tính thích hợp, đầy đủ và độc lập của evidence.
- Incident response: điều phối nếu có active compromise hoặc test gây sự cố.

**Pentester có thể khuyến nghị**, nhưng không tự quyết “risk accepted” chỉ để đóng report.

### 27.2. Exception cần những trường gì?

- Finding/asset/version/endpoint scope.
- Risk impact/exploitability hiện tại.
- Lý do không thể fix hoặc retest đầy đủ.
- Compensating controls đã được kiểm chứng.
- Owner và approver.
- Approval date, expiry, review triggers.
- Monitoring/incident readiness.
- Fix plan và milestones.
- Evidence references.
- Applicability của obligations không cho phép miễn trừ nếu có.

### 27.3. Khi Dev và Pentester không đồng ý

Ví dụ:

- Dev: “đã đổi code, test unit PASS”.
- Pentester: “đường worker vẫn tạo export sai tenant”.
- Dev: “worker path ngoài finding gốc”.
- Risk owner: “cần biết residual impact và scope”.

Cách xử lý:

1. So sánh original root cause và security requirement.
2. Kiểm tra evidence, artifact/version.
3. Xác định liệu path mới dùng chung root cause hay là finding khác.
4. Tránh đóng issue chỉ vì khác interpretation.
5. Ghi technical disagreement và assumptions.
6. Escalate scope/risk decision đến vai trò đúng.
7. Nếu cần, giữ parent/child findings hoặc đề nghị new authorization.
8. Tái kiểm tra khi có patch bổ sung.

Không sửa severity/priority tùy tiện để đạt KPI.

### 27.4. Không gọi “false positive” chỉ vì fix chạy

**False positive:** finding ban đầu thực sự không phản ánh vulnerability trong scope ban đầu.

**Verified fixed:** finding trước đây đúng và hiện đã khắc phục.

Gắn sai FALSE_POSITIVE sẽ xóa mất lịch sử rủi ro, làm méo metric recurrence và assurance traceability.

## 28. Quan hệ giữa retest và broader pentest/assurance

### 28.1. Có nên chạy full pentest sau retest?

Có thể cần nếu:

- Fix thay kiến trúc lớn.
- Authn/authz model thay toàn bộ.
- New sensitive APIs xuất hiện.
- Shared gateway/control plane thay đổi.
- Có compromise hoặc exploit variant lớn.
- Nhiều findings có cùng systemic root cause.
- Regulated/contractual assessment yêu cầu.
- Một số high-risk paths không thể validate bằng targeted retest.

Không cần mặc định pentest toàn bộ sau mỗi one-line patch nếu risk và scope không đòi.

### 28.2. Phối hợp bằng chứng từ nhiều nguồn

- Code review và SAST: kiểm tra root cause/unsafe patterns.
- SCA: version/dependency applicability.
- DAST/API tests: behavior thực trên running service.
- Pentest retest: human review của exploit condition/variants.
- Config/IaC review: security policy logic.
- Runtime checks: effective IAM/network/version.
- Audit/incident telemetry: operating control evidence.
- Risk/GRC: ownership và exception.

Các sources bổ sung nhau; không một source nào bao trùm mọi security properties.

### 28.3. Kết luận nên nêu scope rõ

Ví dụ:

> Retest PT-014 đã xác minh code path GET order trong Orders API release candidate không còn cho user thuộc tenant A đọc order B, trên synthetic fixtures và service/config version được ghi. Bằng chứng gồm positive/negative HTTP tests, repository review và runtime artifact identity ở staging. Worker export và production rollout chưa thuộc scope; finding cần giữ unresolved scope hoặc child exposure cho tới khi kiểm tra và phê duyệt.

Cách diễn đạt này **có giá trị audit**, không khuếch đại evidence.

## 29. Mẫu mapping finding → requirement → control → retest → closure

| Finding | Security requirement | Fix/control | Retest case | Closure evidence |
| --- | --- | --- | --- | --- |
| Cross-tenant read | Resource owner/tenant binding | Verified principal + scoped query | RT-ORD-01/02/03/04 | Positive/negative + repository/runtime |
| Unauthorized admin function | Function-level authorization | PEP checks role/action | Lower-role/admin tests | Effective policy và audit |
| Raw SQL input | Data không thay SQL structure | Parameterized API | Controlled input/DB tests | Code review + behavior |
| SSRF | Destination policy | Server mapping + egress | Safe mock destination tests | Network/config/HTTP observations |
| Token logging | Secrets không vào logs | Remove raw fields | Canary log/trace scan | Protected log samples |
| Webhook replay | Single business effect | Signature + idempotency | Valid/duplicate/invalid tests | Ledger/state assertions |
| File traversal | Only authorized storage scope | Server-managed file IDs | Synthetic file tests | File access and identity |
| IAM wildcards | Least-privilege effective policy | Restrict roles | Allowed and denied actions | Effective IAM evidence |
| Worker export | Verified tenant scope retained | Event validation/resource authz | Forged event test | No unauthorized artifact |
| WAF temporary mitigation | Unwanted ingress path blocked | Rule + routing controls | Safe targeted rule test | Runtime rule and alternate paths |

**Closure evidence phải khớp loại vulnerability**. Không thể dùng cùng một HTTP status assertion để chứng minh cả SQL injection, tenant authorization, IAM và data retention.
## 30. Metrics và KPI/KRI: đo chất lượng retest thay vì số ticket đã đóng

### 30.1. Vì sao đếm “đã retest” là chưa đủ?

Một nhóm có thể báo “100% findings đã retest” dù:

- Test chạy sai phiên bản.
- Tất cả response 404 vì fixture bị thiếu.
- Retest chỉ chạy trên staging.
- Nhiều paths nằm ngoài scope.
- Vulnerabilities còn được mitigated tạm.
- Exceptions không có expiration.
- Production rollback đưa lỗi quay lại.

Do đó phải đo **evidence-backed closure và residual risk**, không chỉ số lượng test runs.

### 30.2. Metrics hữu ích

| Metric | Câu hỏi | Giới hạn |
| --- | --- | --- |
| **Retest readiness rate** | Bao nhiêu findings có đủ patch/target/fixtures? | Ready không đồng nghĩa fixed |
| **Valid execution rate** | Bao nhiêu retests có preconditions đúng? | Chưa phản ánh security outcome |
| **Verified fixed rate** | Bao nhiêu findings đạt closure criteria trong scope? | Cần tách môi trường/impact |
| **Still-vulnerable rate** | Bao nhiêu findings còn exploitable? | Phụ thuộc coverage và methodology |
| **Partial remediation count** | Có bao nhiêu bypass hoặc assets chưa fixed? | Cần child exposure tracking |
| **Mitigated-not-fixed count** | Có bao nhiêu risks dựa control tạm? | Mitigation có thể hết hiệu lực |
| **Blocked/inconclusive retests** | Evidence gaps có được xử lý? | Không báo thành FAIL security |
| **Time from fix-ready to valid retest** | Retest queue có quá chậm? | Start clock phải rõ |
| **Time to verified closure** | Từ detection/remediation tới verified outcome | Khác time to PR merge |
| **Reopen/recurrence rate** | Findings bị tái hiện sau closure | Dựa trên runtime coverage |
| **Variant/bypass discovery rate** | Fix có tập trung đúng root cause? | Không tối ưu bằng bỏ variants |
| **Retest evidence completeness** | Test có link finding, artifact, fixture, status? | Có file chưa chứng minh hiệu quả |
| **Production verification coverage** | Findings đã xác nhận ở runtime mục tiêu? | Safe checks có coverage giới hạn |
| **Exception age/expiry** | Residual risks có quá hạn? | Exception không đồng nghĩa fixed |
| **Security regression escape** | Fix tạo rủi ro mới không phát hiện sớm? | Cần monitoring và incident linkage |
| **Revalidation after rollback** | Old vulnerable version có quay lại? | Tracking fleet phải đầy đủ |
| **Critical asset coverage** | Retests bao phủ critical services? | Không đánh đồng số lượng assets |

### 30.3. Ví dụ tính metrics

Giả sử 24 findings trong scope một đợt retest:

- 9 **VERIFIED_FIXED**.
- 5 **PARTIALLY_FIXED**.
- 4 **MITIGATED_NOT_FIXED**.
- 3 **INSUFFICIENT_EVIDENCE/BLOCKED**.
- 3 **STILL_VULNERABLE**.

Theo cách đếm này, tỷ lệ verified fixed là **9/24 = 37,5%**.

Không nói “rủi ro đã giảm 37,5%” vì:

- Các findings có impact không bằng nhau.
- 4 mitigated vẫn còn root cause.
- 5 partial có thể chứa một đường public nguy hiểm.
- 3 blocked có thể nằm trên shared identity service.
- Số findings không trực tiếp phản ánh blast radius.

### 30.4. Thời gian cần đo riêng

- **Finding reported at:** báo cáo pentest đầu.
- **Fix started at:** owner bắt đầu xử lý.
- **Ready for retest at:** claim đã sửa trong target scope.
- **Retest started at:** pentester có quyền và fixtures.
- **Valid execution completed at:** test kết thúc với preconditions đúng.
- **Reviewed at:** reviewer xác nhận disposition.
- **Production verified at:** runtime target có evidence.
- **Closed at:** finding được đóng theo policy.

Không rút ngắn time to closure bằng cách đặt closure timestamp bằng ngày PR merge.

### 30.5. KPI dễ bị thao túng

- Mark false positive khi không muốn sửa.
- Loại assets còn vulnerable khỏi scope.
- Đổi status partial thành fixed.
- Đánh dấu PASS khi preconditions sai.
- Không retest bypass variants.
- Giữ mitigation mãi thay permanent fix.
- Không cập nhật khi rollback.
- Kết luận trên staging nhưng gắn nhãn production.
- Đóng finding mà không có reviewer.
- Chỉ kiểm tra findings low risk để tăng tỷ lệ.

Cần kiểm soát audit trail và đo **weighted risk exposure**, không đơn thuần “đóng nhiều ticket”.

## 31. RACI: phân công rõ trách nhiệm retest và closure

### 31.1. Các vai trò

| Vai trò | Trách nhiệm chính |
| --- | --- |
| **Penetration tester / Red Team được ủy quyền** | Thiết kế/thi hành safe retest, xác nhận technical behavior và giới hạn |
| **Application/Engineering owner** | Root-cause fix, unit/integration tests, hỗ trợ fixtures |
| **AppSec/Security architect** | Requirement, threat model, variants và security control design |
| **Vulnerability Management owner** | Finding register, priority, SLA, trạng thái và escalation |
| **QA/Security testing team** | Security regression automation, test stability và evidence |
| **Platform/SRE/Release engineering** | Artifact identity, deployment, runtime config, canary/rollback |
| **Identity/IAM owner** | Principal, roles, token lifecycle, authorization policy |
| **Data/Privacy owner** | Data classification, test data và disclosure constraints |
| **Risk owner** | Chấp nhận residual risk/exception theo thẩm quyền |
| **Security Assurance/Audit** | Independent review của evidence/claim/closure |
| **Incident Response** | Containment khi active exploitation hoặc test gây sự cố |
| **Business/Product owner** | Critical workflows, acceptable regression và business impact |

### 31.2. RACI minh họa

| Hoạt động | Pentester | Engineering | AppSec | Platform | Risk Owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Original finding documentation | **A/R** | C | C | I | I | C |
| Root-cause remediation | C | **A/R** | R | C | I | C |
| Retest scope/ROE | **R** | C | **A** | C | C | C |
| Target/fixture readiness | C | **A/R** | C | R | I | C |
| Safe technical retest | **A/R** | C | R | C | I | C |
| Regression tests | R | **A/R** | C | C | I | C |
| Runtime version/rollout verification | C | C | C | **A/R** | I | C |
| Risk acceptance/exception | C | C | C | C | **A/R** | I |
| Independent evidence conclusion | C | C | C | C | I | **A/R** |
| Report finding closure | R | C | **A/R** | C | I | C |

RACI phải được tổ chức hiệu chỉnh. Đặc biệt, không nên để một người **tự tạo fix, tự kiểm tra, tự phê duyệt exception và tự kết luận độc lập** cho finding rủi ro cao.

### 31.3. Handoff contract giữa Dev và Pentester

Handoff tối thiểu:

~~~text
Finding ID:
Root cause:
Fix / mitigation:
Affected service and versions:
Source commit / artifact digest:
Deployment environment / config revision:
Expected secure behavior:
Original preconditions and synthetic fixtures:
New relevant endpoints / bypass paths:
Known limitations:
Engineering regression tests:
Ready-for-retest owner and time:
Authorized target and ROE reference:
~~~

Một handoff rõ giúp tránh việc retest thất bại vì thiếu account, wrong build hoặc tài liệu không đúng.

## 32. Những sai lầm retest thường gặp

### 32.1. “Đã merge PR nên đã fixed”

**Sai:** code thay đổi nhưng chưa deploy.

**Đúng:** retest trên patched build và verify production rollout nếu closure scope yêu cầu.

### 32.2. “Scanner không thấy nữa nên hết lỗ hổng”

**Sai:** scanner có thể không reach path, rules thay đổi hoặc session expired.

**Đúng:** validate original preconditions, targeted test và root-cause evidence.

### 32.3. “Một 403/404 là đủ”

**Sai:** resource không tồn tại, wrong route hoặc token invalid cũng trả lỗi.

**Đúng:** positive controls, trusted fixture và oracle có kiểm chứng.

### 32.4. “Chỉ chạy lại original payload”

**Sai:** patch chỉ chặn literal payload, variants còn exploitable.

**Đúng:** kiểm tra root cause, bypass variants và safe regression.

### 32.5. “Staging PASS = production fixed”

**Sai:** artifact/config/route khác, old replicas còn phục vụ.

**Đúng:** explicit scope, digest/config, production safe verification.

### 32.6. “WAF block = code fixed”

**Sai:** backend vẫn vulnerable hoặc alternate route bypass WAF.

**Đúng:** MITIGATED_NOT_FIXED, control evidence và fix plan.

### 32.7. “Exception approved = retest PASS”

**Sai:** risk acceptance không phải technical fix.

**Đúng:** RISK_ACCEPTED trong register, residual risk vẫn theo dõi.

### 32.8. “Dev tự retest và tự đóng mọi finding”

**Sai:** xung đột vai trò có thể làm yếu independent review.

**Đúng:** phân mức độc lập theo risk, reviewer/authority rõ.

### 32.9. “Tester phải exploit thật trên production”

**Sai:** có thể tạo outage, data breach hoặc transaction thật.

**Đúng:** approved scope, safe methods, sandbox và evidence alternatives.

### 32.10. “Không thấy lỗi là PASS dù không có account”

**Sai:** app trả login redirect cho tất cả request.

**Đúng:** verify authenticated test session/role và coverage.

### 32.11. “Fix mọi đường không cần test regression”

**Sai:** deny-all có thể khiến negative tests xanh nhưng phá nghiệp vụ.

**Đúng:** positive+negative/boundary tests và business invariant.

### 32.12. “Kiểm thử không có side effect”

**Sai:** requests có thể tạo payment, email, file, queue events hoặc audit overload.

**Đúng:** synthetic data, sandbox providers, run-scoped cleanup.

### 32.13. “Retest được cấp quyền nên mở rộng network scan”

**Sai:** kiểm thử ngoài ROE vi phạm scope và tạo rủi ro.

**Đúng:** đề xuất scope extension khi cần, không tự dò quét.

### 32.14. “Không ghi method/tool version”

**Sai:** reviewer không thể hiểu vì sao scan mới có kết quả khác.

**Đúng:** record tools, versions, tests, targets, timestamps.

### 32.15. “Thay config staging tạm để dễ PASS”

**Sai:** điều kiện khác production; fix có thể chưa hoạt động.

**Đúng:** parity comparison và explicit limitations.

### 32.16. “Một vùng đã patch = toàn bộ fleet fixed”

**Sai:** một số replicas/regions vẫn vulnerable.

**Đúng:** population coverage và child exposures.

### 32.17. “Retry đến khi PASS”

**Sai:** first attempt có unauthorized disclosure nhưng bị bỏ qua.

**Đúng:** giữ toàn bộ attempts và triage race/inconsistency.

### 32.18. “Không có người sở hữu residual risk”

**Sai:** finding bị treo vô thời hạn hoặc đóng tùy tiện.

**Đúng:** risk owner, controls, due date, exception/expiry.

### 32.19. “Đóng false positive cho finding đã sửa”

**Sai:** làm mất lịch sử vulnerability thật.

**Đúng:** VERIFIED_FIXED khác FALSE_POSITIVE.

### 32.20. “Không kiểm tra lại sau rollback”

**Sai:** vulnerable artifact quay lại nhưng dashboard vẫn ghi closed.

**Đúng:** re-open trigger theo deployment/security state.

### 32.21. “Bỏ qua cache và async worker”

**Sai:** controller đã sửa nhưng export vẫn sai tenant.

**Đúng:** test data-flow end-to-end theo root cause.

### 32.22. “Chỉ báo mức severity mà không báo action”

**Sai:** engineering không biết cần fix gì hoặc bằng chứng nào còn thiếu.

**Đúng:** report có priority, owner, test gaps, remediation và retest acceptance.

### 32.23. “Để raw token/PII trong retest report”

**Sai:** evidence tự tạo data leak.

**Đúng:** redact, protect, synthetic data và retention.

### 32.24. “Đồng nhất approved mitigation với operating effectiveness”

**Sai:** biện pháp bù trừ được mô tả nhưng chưa triển khai/kiểm chứng.

**Đúng:** effective-state tests, runtime evidence và monitoring.

## 33. Checklist Retest trước khi đóng pentest finding

### 33.1. Preflight và scope

- [ ] Có original finding ID, report và security requirement.
- [ ] Có root cause và remediation/mitigation record.
- [ ] Có risk priority và appropriate retest urgency.
- [ ] ROE/authorization đang có hiệu lực, đúng target/time.
- [ ] Môi trường, methods, rate, concurrency và stop conditions được xác nhận.
- [ ] Không có unapproved destructive/external side effects.
- [ ] Test identities, roles, tenant memberships và fixtures đã sẵn sàng.
- [ ] Target URI/host/asset owner được xác minh.
- [ ] Artifact/build/config revision đã kiểm tra.
- [ ] Không lấy scanner target từ nguồn untrusted.
- [ ] Có reviewer, technical owner và risk owner.
- [ ] Có kế hoạch cleanup và evidence protection.

### 33.2. Test design và execution

- [ ] Original observed insecure behavior được mô tả đủ rõ.
- [ ] Test objective/expected secure behavior cụ thể.
- [ ] Preconditions có positive control.
- [ ] Có positive functional tests cho hành động hợp lệ.
- [ ] Có negative security tests cho actor/input không hợp lệ.
- [ ] Có boundary/failure cases theo threat model.
- [ ] Có variants/bypass paths theo root cause.
- [ ] Có xem xét legacy/API version/direct route.
- [ ] Có xem xét cache/search/bulk/export/worker nếu liên quan.
- [ ] Có test isolation/tenant ownership phù hợp.
- [ ] Có kiểm tra side effects, data integrity và audit.
- [ ] Không cần exploit phá hoại để chứng minh một claim an toàn.
- [ ] Test run gồm tool versions, timestamps, test IDs, actual outcomes.
- [ ] FAILED/BLOCKED/NOT_RUN/INCONCLUSIVE được giữ đúng trạng thái.
- [ ] Những kết quả retry và intermittent violations đều được giữ.
- [ ] Evidence lưu với protected refs, không chứa raw secrets/PII không cần.
- [ ] Tất cả assets/instances thuộc scope được map vào population.

### 33.3. Review và closure

- [ ] Technical finding disposition phù hợp evidence.
- [ ] Không biến NOT_REPRODUCIBLE thành VERIFIED_FIXED khi thiếu căn cứ.
- [ ] Không biến MITIGATED thành FIXED nếu root cause còn.
- [ ] Không biến FALSE_POSITIVE thành tag cho lỗi đã sửa.
- [ ] Không đóng parent khi có child exposure còn OPEN.
- [ ] Biện pháp sửa không tạo blocking security/functional regression.
- [ ] Có verified version/config và scope của production nếu khẳng định production fixed.
- [ ] Report có limitations, exclusions và confidence.
- [ ] Residual risks có owner, action, due date và exception nếu cần.
- [ ] Report được review độc lập theo policy/risk tier.
- [ ] Release gate không PASS vì scanner thiếu report/timeout.
- [ ] Retest được liên kết với original report, patch, tests và deployment.
- [ ] Có trigger re-open nếu rollback/threat/config/architecture thay đổi.
- [ ] Finding closure được ghi bằng evidence thay vì chỉ ticket comment.
- [ ] Lessons learned được đưa vào regression suite và security requirements.

**Checklist là công cụ kiểm soát quy trình, không thay actual test evidence.**

## 34. Bài tập thực hành

### Bài tập 1 — BOLA: nhận diện false PASS

Một pentest finding cho biết user A đọc order B. Dev thêm tenant filter. Retest trả 404 cho A→B, nhưng không kiểm tra account B.

Hãy:

1. Xác định những preconditions còn thiếu.
2. Thiết kế test chứng minh order B tồn tại.
3. Viết positive/negative matrix.
4. Xác định cần test cache/export/worker không.
5. Chọn disposition phù hợp khi chưa đủ evidence.
6. Mô tả điều kiện để đóng finding trên production.

### Bài tập 2 — SSRF: WAF hay root cause?

Một service cho phép người dùng nhập callback URL. Đội vận hành thêm WAF rule chặn một input pattern, không thay HTTP client code.

Hãy:

- Phân biệt fixed và mitigated.
- Nêu safe test destination thuộc sandbox.
- Review redirect/DNS/IPv6 và egress policy.
- Xác định required evidence.
- Nêu bypass variants có trong ROE.
- Đề xuất permanent fix và exception workflow.

### Bài tập 3 — Chứng minh patch đúng artifact

Staging chạy image digest X và retest PASS; production chạy tag có thể trỏ tới digest Y.

Hãy:

- Đánh giá identity evidence.
- Giải thích vì sao staging result chưa đủ production.
- Đề xuất deployment/registry/runtime checks.
- Nêu trạng thái nếu production chỉ patch 75% replicas.
- Thiết kế post-deploy safe verification.

### Bài tập 4 — Webhook replay

Finding ban đầu: một callback có chữ ký hợp lệ bị replay làm refund hai lần.

Hãy lập retest:

- Synthetic payment/order setup.
- Valid signature positive control.
- Duplicate event negative check.
- Out-of-order state transition.
- Database/ledger assertions.
- Audit correlation.
- Cleanup/rollback plan.
- Closure criteria khi worker xử lý bất đồng bộ.

### Bài tập 5 — CI report bị thiếu

Automated retest job exit 0 nhưng báo cáo security test không tồn tại. Job scanner khác báo 0 findings.

Hãy:

- Tách execution status và security disposition.
- Thiết kế gate fail-closed cho missing report.
- Xác minh tested build/digest và target.
- Xác định owner điều tra.
- Nêu required follow-up trước release.

### Bài tập 6 — Retest root-cause variants

Pentest phát hiện BFLA ở admin operation trong API v1. Dev sửa gateway route v1 nhưng API v2, GraphQL và direct backend route dùng chung privileged handler.

Hãy:

- Thiết kế scope và variants.
- Nêu những tests cần explicit authorization.
- Đánh giá server-side authorization vs gateway controls.
- Tạo parent/child finding structure.
- Nêu khi nào cần broader reassessment.

### Bài tập 7 — Retest không thể thực hiện trên production

Một lỗi query có thể làm hỏng dữ liệu thật; production không cho phép replay.

Hãy đề xuất:

- Controlled sandbox reproduction.
- Code/config/fix evidence.
- Runtime artifact/version mapping.
- Safe production checks.
- Limitations/confidence.
- Residual risk và sign-off.
- Vì sao không nên ghi “fully proven in production” khi chưa đủ scope.

### Bài tập 8 — Dashboard và residual risk

24 findings có kết quả: 9 fixed, 5 partial, 4 mitigated, 3 blocked, 3 still vulnerable.

Hãy:

- Tính verified-fixed rate.
- Nêu vì sao không thể suy ra tỷ lệ risk giảm.
- Đề xuất ưu tiên theo exposure/impact.
- Thiết kế bảng owners/actions.
- Thêm re-open/exception metrics.
- Chỉ rõ bằng chứng còn thiếu.

### Bài tập 9 — Retest sau rollback

Một vulnerability ban đầu fixed, nhưng sau outage team rollback về old image.

Hãy:

- Xác định trigger re-open.
- Verify runtime artifact.
- Đề xuất containment.
- Chọn rollback/roll-forward plan theo policy.
- Thiết kế targeted retest mới.
- Cập nhật risk register và release report.

### Bài tập 10 — Tranh luận kết luận giữa Dev và Pentester

Dev khẳng định finding SQLi fixed do parameterized query, pentester thấy một báo cáo cũ của route legacy vẫn chứa unsafe dynamic query.

Hãy:

- Xác định finding/asset/route scope.
- Phân biệt original root cause và related finding.
- Thiết kế safe tests.
- Đề xuất code review và effective artifact mapping.
- Nêu dispute resolution/risk owner.
- Viết một kết luận không quá mức.

## 35. Câu hỏi tự kiểm tra

1. Retest trong pentest khác initial penetration testing ở đâu?
2. Một security regression test khác pentester retest như thế nào?
3. Vì sao không thể đóng finding chỉ vì PR đã merge?
4. Những trường nào cần có trong original finding record?
5. Vì sao retest cần Rules of Engagement mới hoặc được xác nhận lại?
6. Những hoạt động nào có thể gây side effect nguy hiểm?
7. Có cách nào retest SQL injection mà không dùng payload phá hoại production?
8. Cách phân biệt verified fixed và not reproducible?
9. Vì sao 404 có thể tạo false PASS trong BOLA retest?
10. Positive control trong cross-tenant test cần những gì?
11. Negative test phải xác minh điều gì ngoài HTTP status?
12. Hai dimensions execution status và security disposition khác nhau ra sao?
13. BLOCKED_ENVIRONMENT có chứng minh vulnerability còn không?
14. MITIGATED_NOT_FIXED nghĩa là gì?
15. Khi nào một finding nên PARTIALLY_FIXED?
16. Một finding có nhiều affected services cần closure như thế nào?
17. Vì sao cần test bypass variants mà không chỉ original request?
18. Tại sao root-cause fix có thể không loại hết legacy API vulnerability?
19. Những security regressions nào thường gặp sau authorization fix?
20. Cần chứng minh trusted principal/tenant context bằng cách nào?
21. Tại sao query có tenant filter vẫn có thể bị BOLA?
22. Cache có thể bypass authorization ra sao?
23. Worker export có thể lộ dữ liệu dù API GET fixed không?
24. Vì sao async POST trả 202 chưa chứng minh security invariant?
25. Test SSRF cần chú ý redirects và network egress vì sao?
26. Test path traversal cần quan tâm symlink race thế nào?
27. Retest secrets cần xử lý logs và evidence ra sao?
28. Thế nào là artifact identity khi hệ thống dùng OCI images?
29. Nếu production tag khác digest đã test, cần làm gì?
30. Một phần fleet còn image cũ nên có disposition gì?
31. Vì sao staging PASS không đủ khẳng định production fixed?
32. Cần evidence gì cho WAF compensating control?
33. Một network isolation rule có thể che root-cause vulnerability không?
34. Retest business logic refund cần kiểm tra side effect nào?
35. Khi nào nên retest với concurrent requests?
36. Retest cần thế nào để không làm lộ customer PII?
37. Vì sao report phải ghi exclusions và limitations?
38. Ai là người approve risk acceptance?
39. Ai chịu trách nhiệm technical retest verdict?
40. Ai review independent assurance evidence?
41. Vì sao FALSE_POSITIVE không được dùng cho finding từng đúng và nay đã sửa?
42. Những trường hợp nào làm retest phải reopen?
43. Rollback có thể ảnh hưởng kết luận trước đó thế nào?
44. Tại sao change lớn về identity/architecture có thể cần full reassessment?
45. Retest evidence cần liên kết những IDs nào?
46. Design, implementation và operating effectiveness khác nhau ra sao?
47. Một scanner report không có findings có đủ chứng minh fixed không?
48. Retest nên xử lý scan timeout thế nào?
49. Missing test report nên khiến CI gate có trạng thái gì?
50. Vì sao positive business tests quan trọng không kém negative tests?
51. Một phép thử ở integration environment có thể tạo data leak không?
52. Test fixture cleanup cần đảm bảo điều gì?
53. Làm sao phân biệt retry vì infra flaky với security violation intermittent?
54. Vì sao report cần source artifact và config revision?
55. KPI verified-fixed rate có phản ánh toàn bộ residual risk không?
56. Những metric nào giúp phát hiện retest false PASS?
57. Khi cần containment khẩn, có nên chờ full retest không?
58. Cần làm gì khi pentester thấy path ngoài ROE?
59. Security requirement nào quyết định retest BFLA?
60. Một retest report nên có bao nhiêu mức conclusion, và vì sao?
61. Viết security claim cho protected export và ba negative tests.
62. Tại sao approved exception không đồng nghĩa root cause đã biến mất?
63. Khi API version thay đổi, test scope cũ có còn hợp lệ không?
64. Một test token expired có giúp chứng minh authorization đúng không?
65. Dùng source code review thay dynamic test có thể đủ trong điều kiện nào?
66. Vì sao cần runtime evidence trước khi xác nhận production fixed?
67. Retest có thể tạo finding mới không và xử lý ra sao?
68. Chỉ số recurrence rate có giá trị gì với assurance?
69. Có thể đóng finding bằng evidence của một WAF rule chưa kiểm chứng không?
70. Viết một đoạn retest conclusion có phạm vi, evidence, limitations và next action.

## 36. Tổng kết

**Retest** là hoạt động kiểm tra lại **một finding pentest sau khi remediation hoặc mitigation**, để xác định liệu root cause và những đường khai thác quan trọng trong phạm vi đã thực sự được xử lý hay chưa. Retest đáng tin phải bắt đầu từ **original security requirement/threat scenario**, có **Rules of Engagement**, xác minh **artifact/config/test identities và preconditions**, sử dụng **positive, negative, boundary, bypass, failure và regression tests** phù hợp, sau đó giữ **actual evidence** và mô tả limitations.

Cần phân biệt chặt chẽ:

- **Không tái hiện được** không tự đồng nghĩa **verified fixed**.
- **Mitigation hoặc exception** không đồng nghĩa **root cause đã sửa**.
- **Staging retest PASS** không tự đồng nghĩa **production fixed**.
- **403/404** không đủ nếu resource/identity preconditions sai.
- **PR merged, scanner xanh hoặc updated version** chưa chứng minh control effective.
- **Retest blocked/not run** không phải PASS hoặc FAIL của security property.
- **Partial rollout, bypass path hoặc regression** cần finding và action riêng.
- **Một kết luận trong scope** không chứng minh an toàn cho toàn hệ thống.

Trong **SECURITY_SECURITY_ASSURANCE**, retest tạo giá trị khi duy trì được **traceability từ risk/threat → finding → security control/remediation → test requirement → executed result → deployment identity → verified closure hoặc residual-risk decision**. Kết luận cần minh bạch về **đúng tài sản, phiên bản, môi trường, roles/tenants, test methods, bằng chứng, độ tin cậy và exclusions**, đồng thời có trigger đánh giá lại khi production rollback, dependency, policy, threat hoặc kiến trúc thay đổi.
