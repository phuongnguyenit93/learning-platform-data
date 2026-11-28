# Xử lý finding

**Finding** trong **dynamic testing** là một quan sát hoặc phát hiện có khả năng liên quan đến vấn đề bảo mật, được tạo ra khi công cụ hoặc người kiểm thử tương tác với **ứng dụng, API, dịch vụ, thiết bị hoặc cấu hình đang chạy**. Finding có thể xuất phát từ DAST (Dynamic Application Security Testing), kiểm thử API có xác thực, fuzzing có kiểm soát, kiểm thử phân quyền theo vai trò/tenant, quét TLS và cấu hình dịch vụ, kiểm thử hệ thống bất đồng bộ, hoặc một đợt security assessment thủ công. Một finding chưa tự động đồng nghĩa một vulnerability đã được xác nhận.

Ví dụ, DAST báo **Broken Object Level Authorization (BOLA)** khi giáo viên có thể đổi mã lớp trong URL và nhận thông tin của lớp không thuộc quyền. Đội phát triển không nên chỉ sửa HTTP status cho thành **403** rồi đóng ticket: hệ thống vẫn có thể tạo công việc xuất báo cáo trong queue, worker ghi tệp lên object storage và signed URL vẫn có thể được tải. Muốn kết luận đã xử lý, cần kiểm chứng **security decision, dữ liệu trả về, side effects, phiên bản đã triển khai và đường thực thi khác**. Ngược lại, một scanner có thể báo SQL injection do diễn giải sai response hoặc vì không đủ thông tin; trường hợp này cần phân loại bằng bằng chứng, không sửa code vô nghĩa.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là *xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện; học tổ chức chương trình security assurance liên tục trong phát triển và vận hành*. Vì vậy bài **“Xử lý finding”** thuộc chương **Dynamic testing** tập trung vào khả năng **tiếp nhận, tái hiện an toàn, kiểm chứng, ưu tiên, khắc phục, retest và lưu hồ sơ assurance**, chứ không chỉ thao tác trên một dashboard scanner.

**Chuỗi tư duy:** *Observation → finding record → scope/evidence validation → technical triage → risk/exposure assessment → response owner → remediation/mitigation → independent verification → closure decision → continuous monitoring and reopening.*

> **Nguyên tắc:** **“Scanner không báo nữa” không đồng nghĩa “đã sửa”, “không khai thác thành công trong một lần thử” không đồng nghĩa “false positive”, và “risk accepted” không đồng nghĩa “vulnerability đã biến mất”.**

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích observation, candidate finding, confirmed finding, vulnerability, risk, mitigation, remediation, retest, risk acceptance và evidence gap.
2. Phân biệt kết quả scanner, hành vi thực tế của target, tác động nghiệp vụ và trạng thái xử lý.
3. Xây một workflow nhất quán từ DAST/API scan đến finding được xác minh và đóng có điều kiện.
4. Xác định preflight của phép thử: authorization, rules of engagement, target identity, scanner health, authentication, coverage và phiên bản ứng dụng.
5. Thu evidence có thể tái hiện mà không làm rò dữ liệu học viên, credential, session hoặc hệ thống nhạy cảm.
6. Phân loại true positive, false positive, duplicate, not applicable, insufficient evidence, partially fixed và accepted risk.
7. Đánh giá severity theo exploit conditions, confidence, exposed asset, data classification, business impact và compensating controls.
8. Thiết kế kiểm thử có quyền và an toàn cho API/logic nghiệp vụ, authentication, authorization, SSRF, XSS, injection, session, file upload, cloud access.
9. Phân biệt HTTP response với business outcome, đặc biệt tại queue/worker/cache/storage và luồng bất đồng bộ.
10. Viết yêu cầu khắc phục theo root cause thay vì chỉ chặn một request/payload.
11. Gắn finding với source revision, image/build digest, effective config, deployment population và owner.
12. Thiết kế positive/negative/regression/side-effect/temporal tests để revalidate remediation.
13. Lập hồ sơ Claim–Argument–Evidence cho kết quả xử lý và giới hạn kết luận.
14. Xây scan/retest failure behavior, CI/CD gates và trigger đánh giá lại.
15. Theo dõi SLA, tồn đọng, reopened findings, unknowns và khả năng vận hành của scanner.
16. Diễn giải một case study về data export đa tenant trong hệ thống học Java/Spring và đề xuất response có bằng chứng.

## 2. “Finding” trong dynamic testing là gì?

### 2.1. Observation chưa chắc là vulnerability

Một response bất thường như **HTTP 500**, header bảo mật thiếu hoặc thời gian phản hồi tăng có thể tạo một **observation**. Để gọi đó là vulnerability, cần đánh giá:
- Yêu cầu bảo mật nào bị vi phạm?
- Điều kiện, input, actor, resource và trạng thái hệ thống nào gây ra kết quả?
- Có thể tái hiện không, hoặc có cơ sở kỹ thuật độc lập hỗ trợ?
- Kết quả có trái security policy hay chỉ là chức năng được phép?
- Input nào attacker kiểm soát? Cần quyền gì?
- Exposure/impact thực tế thuộc hệ thống và dữ liệu nào?
- Có alternate explanation (proxy error, WAF page, test data, rate limiting, staging misconfiguration) không?

Ví dụ DAST thấy server trả lỗi khi ký tự đặc biệt xuất hiện. Điều đó có thể chỉ ra error handling yếu, nhưng **chưa đủ chứng minh SQL injection** nếu không có evidence cho thấy input đã thay cấu trúc SQL hoặc tạo hành vi vượt policy.

### 2.2. Các lớp thông tin

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Observation** | Công cụ/người kiểm thử nhìn thấy gì? | Một request trả dữ liệu lớp khác |
| **Finding hypothesis** | Vì sao kết quả có thể là vấn đề? | Có thể thiếu object-level authorization |
| **Validated weakness** | Rule/security requirement nào bị vi phạm? | Teacher A không có quan hệ với lớp B nhưng API cho xem |
| **Risk scenario** | Ai khai thác, nhằm vào gì, hậu quả thế nào? | Lộ điểm học viên giữa tenants |
| **Remediation** | Thay đổi gì để loại nguyên nhân? | Enforce relation-aware policy ở service/data access |
| **Verification** | Bằng chứng gì cho thấy fix đúng nơi và đúng phạm vi? | Negative tests, no side effects, deployed digest |
| **Closure/monitoring** | Ai quyết định, cần theo dõi gì? | Reviewer phê duyệt, trigger reopen khi rollback |

Một finding có thể bị kết luận **False Positive** hoặc **Insufficient Evidence**, nhưng không nên tự ghi nó đã sửa khi thực ra chưa biết thực trạng.

### 2.3. Phạm vi của dynamic testing

**Dynamic testing** quan sát ứng dụng/hệ thống đang hoạt động: request, response, state changes, timings, browser behavior, network/TLS, storage access và service interactions. Các công cụ thường gồm:
- DAST browser/web application scanner.
- API scanner dựa trên OpenAPI/GraphQL/gRPC contract.
- Authenticated negative tests theo actor, role, tenant và resource.
- Fuzzing/protocol robustness tests trong phạm vi có kiểm soát.
- Manual exploratory security testing.
- Runtime cloud/network/service configuration checks.
- End-to-end workflow tests tích hợp queue và storage.
- Security regression tests chạy trong CI/staging.
- Synthetic attack-simulation thuộc phạm vi đã được cho phép.

SAST xem code, SCA xem component inventory/advisory; chúng **bổ trợ**, không thay dynamic reproduction/behavior evidence.

## 3. Các trạng thái finding cần phân biệt

| Trạng thái | Khi nào dùng? | Ý nghĩa đối với assurance |
|---|---|---|
| **NEW / UNTRIAGED** | Vừa có observation hoặc scanner alert | Chưa xác minh |
| **NEEDS_VALIDATION** | Thiếu nguyên nhân/đường tái hiện/scope | Chưa kết luận là vulnerability |
| **CONFIRMED / TRUE_POSITIVE** | Vi phạm security requirement có evidence | Cần xử lý risk |
| **FALSE_POSITIVE** | Tool/test kết luận sai theo rule và scope đã xác minh | Lưu rationale; không xem là một fix |
| **DUPLICATE** | Trùng root cause hoặc cùng record đã theo dõi | Link finding gốc, không xóa visibility |
| **NOT_APPLICABLE** | Requirement hoặc path không thuộc sản phẩm/điều kiện được đánh giá | Ghi scope/source/config |
| **REMEDIATION_IN_PROGRESS** | Có fix/mitigation plan và owner | Chưa verified |
| **FIX_DEPLOYED_PENDING_VERIFICATION** | Có triển khai nhưng chưa retest đủ | Không tính Verified Fixed |
| **PARTIALLY_FIXED** | Một số affected paths/assets đã sửa, số khác còn | Không full-close |
| **MITIGATED** | Control bù trừ giảm rủi ro, weakness có thể còn | Có residual risk và review trigger |
| **RISK_ACCEPTED** | Risk owner chấp nhận rủi ro có thời hạn và thẩm quyền | Không phải kỹ thuật fixed |
| **INSUFFICIENT_EVIDENCE** | Scanner lỗi, coverage yếu hoặc chưa xác minh | Không thành Pass/FP |
| **VERIFIED_FIXED** | Fix vượt qua acceptance criteria trong scope cụ thể | Có evidence và reviewer |
| **CLOSED** | Quyết định workflow hoàn tất với reason code | Phải phân biệt fixed/FP/accepted |
| **REOPENED** | Regression, rollback, finding mới hoặc giả định cũ mất hiệu lực | Quay về điều tra/khắc phục |

Tổ chức có thể chọn tên trạng thái khác, nhưng ý nghĩa **technical validity** và **risk decision** phải được lưu riêng. “Closed” trên công cụ ticket **không tự nói lỗ hổng đã biến mất** nếu reason là risk acceptance.

## 4. Quy trình end-to-end xử lý finding

~~~mermaid
flowchart TD
    A["Scan / tester observation"] --> B["Log event + scan provenance"]
    B --> C{"Target, tool, test có hợp lệ?"}
    C -->|"Không"| U["Unknown / coverage gap / rerun"]
    C -->|"Có"| D["Triage + safe reproduction"]
    D --> E{"Technical verdict"}
    E -->|"False positive"| FP["Rationale + reviewer + reassess trigger"]
    E -->|"Unclear"| U
    E -->|"Confirmed"| R["Threat/risk assessment + severity"]
    R --> O["Owner + action + deadline"]
    O --> M["Fix root cause / mitigate"]
    M --> V["Build/deploy identity + retest"]
    V --> X{"Acceptance criteria đạt?"}
    X -->|"Không"| O
    X -->|"Chưa đủ evidence"| U
    X -->|"Đạt"| Z["Verified + closure review"]
    Z --> P["Continuous monitoring + reopen"]
    FP --> P
    U --> D
~~~

**Các điểm kiểm soát:**
1. **Intake:** finding record có owner, nguồn và identity.
2. **Preflight:** scan/test hợp lệ, không vi phạm rules of engagement.
3. **Technical triage:** phân biệt lỗi thật, tool error, duplicate, FP, not applicable.
4. **Risk prioritization:** ảnh hưởng nghiệp vụ và khả năng khai thác theo context.
5. **Remediation ownership:** fix root cause ở đúng lớp, thẩm quyền quyết định exception rõ.
6. **Retest:** dùng test oracle và tool/coverage phù hợp.
7. **Release/runtime validation:** xác nhận fix thực tế có trong artifact đang chạy.
8. **Independent review:** kết luận có bằng chứng, không overclaim.
9. **Monitoring:** rollback, code/config change hoặc incident trigger mở lại.

Không nên tự động đưa candidate finding vào CLOSED chỉ vì scanner báo “0 findings” ở đợt sau.

## 5. Preflight: phép thử có hợp lệ và đủ dữ liệu không?

### 5.1. Kiểm tra rules of engagement

Trước khi tái hiện, cần xác định:
- Chủ tài sản đã cho phép phép thử nào, trên host/IP/tenant/endpoint nào?
- Môi trường: lab, staging tương đương production hay production có phê duyệt?
- Có giới hạn về rate, concurrency, payload size, thời gian, destructive tests?
- Dữ liệu dùng là synthetic hay dữ liệu thật? Có data minimization?
- Có on-call/contact, stop conditions và rollback plan?
- Có vendor APIs, email, payment, export job hoặc external side effects không?
- Có thể vô tình kích hoạt security monitoring, khóa user hoặc làm tràn queue?
- Có cách cleanup test assets và lưu evidence an toàn không?

**Không triển khai quét phá hoại hoặc kiểm thử gây gián đoạn vào production không được ủy quyền.** Với SSRF, file upload, fuzzing hoặc concurrency, nên dùng đích giả lập và giới hạn tài nguyên.

### 5.2. Kiểm tra scanner health

Một scan run đáng dùng phải ghi:
- Job/run ID, started/finished time và outcome.
- Scanner/engine/plugin/ruleset version; advisory feed khi liên quan.
- Target identity, environment, host/URL, build/config.
- Network reachability, response code distribution và redirect behavior.
- Crawl/API endpoint coverage; requests phát thật, không chỉ discovered.
- Authenticated identity, role, tenant và session validity.
- WAF/rate-limit/429/503, timeouts, skipped endpoints.
- Scan policy, include/exclude rules, rate limits, scope.
- Error summary, partial results và output artifact refs.

Một scanner báo **“no vulnerabilities detected”** sau khi mọi protected routes trả 401 là **coverage gap**, không phải bằng chứng an toàn.

### 5.3. Baseline và thời điểm

Giữ snapshot **trước remediation**:
- Vulnerability/finding ID, initial observation.
- Actors, permissions, fixture state, object IDs đã tổng hợp an toàn.
- Request sequence và relevant headers/cookies đã redact.
- Response body fragment đã minimization.
- Server/audit logs theo request ID.
- Affected build/deployment identity.
- Initial scanner version/rules.
- Expected security behavior và actual deviation.
- Incident/exposure period nếu đã biết.

Không lưu raw access token/password của người dùng thật vào finding ticket. Test identities và tokens chỉ dùng trong môi trường có quyền, có thời hạn/thu hồi theo policy.

### 5.4. Cần đủ bối cảnh mới đánh giá được

Ví dụ dynamic scanner báo **403** ở một endpoint nhưng không biết actor có quyền gì. Chỉ nhìn status không đủ xác định lỗi. Với business logic, phải biết **ngữ cảnh quyền**: user–tenant–class–role–state và expected policy tại thời điểm action.

## 6. Evidence chuẩn cho một finding

### 6.1. “Reproducible” nghĩa là gì?

Một báo cáo hữu ích phải giúp reviewer **thực hiện lại phép thử trong môi trường được phép** và hiểu chính xác kết quả. Tối thiểu nên có:
- **Given:** actor/role/tenant, dữ liệu thử, preconditions, target build/config.
- **When:** request/action/sequence, method/route, relevant parameters được ẩn thông tin nhạy cảm.
- **Then:** expected policy và actual behavior trái policy.
- **Also verify:** DB/cache/queue/storage/email/vendor side effects.
- **Trace:** request ID, event/job ID, timestamps, logs liên quan.
- **Impact:** loại dữ liệu/action bị ảnh hưởng; không phóng đại.
- **Limits:** phần chưa kiểm tra và uncertainty.

### 6.2. Một bằng chứng tốt không nhất thiết là exploit đầy đủ

Với một finding có thể chứng minh bằng response khác biệt, policy matrix và data lineage, không cần tìm cách lấy nhiều dữ liệu hoặc làm tăng thiệt hại. **Minimal proof** có chủ đích thường an toàn hơn mass export.

Báo cáo không nên chứa:
- Cookies/session secrets nguyên bản.
- Real passwords/API keys.
- Full bảng điểm/hồ sơ cá nhân học viên.
- Payload phá hoại không cần thiết.
- Dữ liệu của tenant ngoài phạm vi cho phép.
- URL signed với token còn hạn.
- Full diagnostic dump chứa PII.

### 6.3. Đánh giá chất lượng evidence

| Chiều | Câu hỏi |
|---|---|
| **Relevance** | Evidence có hỗ trợ đúng finding/security requirement không? |
| **Authenticity** | Nó đến từ source/test run nào, có đáng tin không? |
| **Integrity** | Có bị chỉnh sửa ngoài kiểm soát? |
| **Completeness** | Có thiếu response, request sequence, side effects hoặc regions? |
| **Freshness** | Có đúng build/config/kỳ cần đánh giá? |
| **Reproducibility** | Có đủ fixture, role, policy version và bước để retest? |
| **Traceability** | Có link tới finding, test, asset, owner, artifact? |
| **Confidentiality** | Evidence được bảo vệ theo data classification? |
| **Limitations** | Những điều không thể khẳng định được nêu rõ? |

### 6.4. Bản gốc và bản chia sẻ

Giữ original tool output/raw event trong kho có kiểm soát theo policy; chia sẻ **redacted excerpt** với reviewer/engineering. Khi cần chain of custody, ghi source/query/time/filter, person, digest, transformations, access/transfer records. Hash của report chứng minh một khía cạnh integrity của file, **không chứng minh scanner đã kiểm tra đúng target**.

## 7. Technical triage: xác nhận finding và tránh overclaim

### 7.1. Câu hỏi triage

1. Rule/weakness chính xác là gì? CWE/advisory ID nếu áp dụng?
2. Request/test có đến đúng vulnerable path?
3. Actor có xác thực và quyền/trạng thái như expected?
4. Input nào do attacker kiểm soát?
5. Điều kiện khai thác được thỏa mãn trong scope?
6. Hành vi quan sát có trái policy hay là expected?
7. Có lý do khác giải thích response không (cache, proxy, WAF, lỗi dữ liệu)?
8. Có tái hiện trong lab/staging có quyền không?
9. Có code/config review nào hỗ trợ hoặc bác bỏ?
10. Có unauthorized side effect hay chỉ status body khác?
11. Có instance/region/service khác affected?
12. Evidence còn thiếu hoặc risk chưa xác định là gì?

### 7.2. True positive vs false positive vs unknown

**True positive:** Phép thử và analysis chứng minh violation trong đúng điều kiện. Ví dụ user không có quan hệ với lớp B nhưng API cho lấy dữ liệu bảng điểm B.

**False positive:** Scanner suy ra vulnerability từ response/heuristic, nhưng technical analysis chứng minh điều kiện rule nói đến **không tồn tại trong target/scope đã kiểm tra**. Ví dụ reflection heuristic hiểu sai response để kết luận SQL syntax đã bị điều khiển, trong khi actual request bị bind vào query constant và negative behavior test/call-site review xác nhận.

**Unknown/Insufficient evidence:** Không đủ quyền vào route, scan error, test fixture sai, không rõ build, vulnerability khó tái hiện hoặc need more context. Không được gọi FP chỉ vì “test không khai thác được một lần”.

### 7.3. Triage có thể cần độc lập với tác giả fix

Với high-impact finding, developer có thể cung cấp code/context, nhưng reviewer/Assurance cần xác minh behavior và closure theo policy. Nếu nhóm nhỏ không có independent security team, tối thiểu nên có peer review và decision trail, không tự phê duyệt tất cả ngoại lệ.

### 7.4. Duplicate vs similar

Hai scanner findings trên GET grades và POST export có thể cùng root cause “thiếu per-class authorization”, nhưng là **hai affected paths cần verification**. Nếu gộp vào ticket gốc, phải giữ từng endpoint và test outcome. Đừng đánh DUPLICATE để mất coverage.

### 7.5. “Không applicable” phải có chứng minh

Một finding trên code chỉ tồn tại ở test harness không deploy có thể là NOT_APPLICABLE với **production runtime**; nhưng nếu build/test runner có untrusted inputs, vẫn có risk ở **build environment**. Không dùng “test-only” như lời phủ nhận mọi supply-chain risk.

## 8. Risk assessment: severity không chỉ là nhãn scanner

### 8.1. Yếu tố chính

Đánh giá theo:
- Security impact: confidentiality, integrity, availability, accountability.
- Business/data impact: điểm, dữ liệu học viên, chứng chỉ, tài khoản admin.
- Attacker preconditions: unauthenticated, normal user, privileged, internal.
- Exposure: Internet-facing, tenant boundary, worker/internal API, management plane.
- Exploitability/ease/reliability; threat intelligence khi có.
- Blast radius và data volume/cross-tenant impact.
- Asset criticality và compensating controls đã **được kiểm chứng**.
- Uncertainty: scanner confidence/limited evidence.
- Remediation availability và operational trade-offs.
- Security objective và nghĩa vụ pháp lý/hợp đồng nếu áp dụng.

**CVSS** hỗ trợ mô tả severity theo vector, nhưng không tự quyết định priority cho một tổ chức. Có thể dùng risk matrix hoặc cơ chế nội bộ có lý giải.

### 8.2. Cùng weakness, khác impact

| Finding | Context | Risk considerations |
|---|---|---|
| BOLA trong grade export | Exposes cross-tenant learner grades | High confidentiality/business impact |
| XSS trong trang test nội bộ | Isolated synthetic users, no production route | Phải xác minh scope và actual exposure |
| API thiếu header | Browser behavior và sensitive resource context | Có thể ít risk hơn logic authz |
| SSRF trong worker | Có egress tới metadata/management plane? | Cần xem network/cloud identity |
| SQLi vào DB read-only | Vẫn có thể đọc dữ liệu không có quyền | “Read-only” không xóa confidentiality risk |
| Dependency advisory | Component present nhưng vulnerable path/config chưa rõ | SBOM/SCA/VEX/exposure evidence |
| TLS weak protocol | Edge internet vs isolated legacy segment | Cần scope và policy compliance |

### 8.3. Mitigation vs remediation

- **Remediation:** xử lý root cause (ví dụ object-level policy ở service, parameterized query).
- **Mitigation:** giảm risk bằng control tạm/khác (WAF rule, network segregation, feature off, rate limit, credential restriction).
- **Containment:** giới hạn tác động khẩn cấp khi incident/active exploitation.
- **Risk acceptance:** phê duyệt residual risk; không làm weakness biến mất.

Một finding được WAF chặn có thể chuyển trạng thái MITIGATED, **không tự thành FALSE_POSITIVE/VERIFIED_FIXED**.

### 8.4. Ưu tiên với uncertainty cao

Nếu có dấu hiệu lộ điểm liên tenant nhưng chưa xác minh đủ, không tự kết luận “low” vì confidence thấp. Có thể:
- Tạm hạn chế feature theo thẩm quyền.
- Tăng monitoring.
- Tăng quyền ưu tiên cho việc thu evidence.
- Giới hạn data access trong lúc điều tra.
- Ghi rõ trạng thái UNDER_INVESTIGATION và deadline.

## 9. Phân công owner, SLA và điều phối

### 9.1. Các trách nhiệm

- **Finder/tester:** mô tả observation, evidence, scope, safe reproduction.
- **Triage owner/AppSec:** xác minh technical validity, severity, affected paths.
- **Product/Service Owner:** nhận risk context, accountable với component/business path.
- **Developer/Tech Lead:** phân tích root cause và implement remediation.
- **Platform/SRE:** xác nhận build/deployment, IAM, container, region, runtime controls.
- **QA/Security Tester:** xây positive/negative/regression/retest tests.
- **SOC/Incident Response:** điều tra exploitation, log impact và containment khi cần.
- **Privacy/Legal:** tham gia nếu có dữ liệu cá nhân/hợp đồng/notification obligations.
- **Authorized Risk Owner:** quyết định acceptance/exception trong thẩm quyền.
- **Assurance Reviewer:** xác minh Claim–Argument–Evidence và giới hạn closure.

Một người có thể kiêm nhiều vai trò ở nhóm nhỏ, nhưng **separation of duties** và approval cần tương xứng risk.

### 9.2. Các mốc SLA

Tùy chính sách tổ chức:
- Time to acknowledge.
- Time to validate/triage.
- Time to contain (khi cần).
- Time to fix ready.
- Time to deploy fixed artifact.
- Time to retest/verify.
- Time to closure review.
- Time to respond to re-open.
- Exception expiry/review deadline.

Không có một thời hạn chung đúng cho mọi weakness. Nên ghi risk tier, trigger bắt đầu đếm SLA, paused states có lý do, escalation và owner.

### 9.3. Finding không có owner là finding governance

Nếu không tìm ra owner:
1. Gắn tạm với asset/platform registry owner.
2. Escalate theo service inventory.
3. Ghi thời điểm/việc đã làm và risk.
4. Có containment nếu high impact.
5. Sửa asset inventory và ownership mapping.
6. Không đóng finding vì “không biết ai sửa”.

## 10. Chuyển observation thành ticket có thể hành động

### 10.1. Cấu trúc ticket

Một ticket tốt nên có:
- Unique finding ID/fingerprint, source test run.
- Vulnerability/weakness class, affected asset/entry points.
- Evidence đã redact, safe reproduction, expected/actual.
- Severity/priority và risk rationale.
- Affected build/config/environment/tenant scope.
- Root cause hypothesis (tách với đã chứng minh).
- Owner, due date, communication.
- Mitigation/containment khi cần.
- Remediation requirement/acceptance criteria.
- Verification plan và retest owner.
- Related/duplicate findings và affected paths.
- Status/reviewer/approval, residual risk.
- Exclusions, evidence gaps, timestamps.

### 10.2. Ví dụ finding cho Learning API

> **ID:** DYN-FND-042 (minh họa)  
> **Type:** Broken Object Level Authorization – grade export  
> **Asset:** Learning API + report queue/worker; release/build cần điền chính xác  
> **Observation:** Teacher A không thuộc lớp B vẫn tạo được export job cho class B trong synthetic tenant fixture.  
> **Expected:** Deny và không tạo job/file/notification trái quyền.  
> **Actual:** Request được accept, job tạo theo class B.  
> **Evidence:** redacted request IDs, authorization context, job/storage assertions, scan/test run và timestamps.  
> **Risk:** confidentiality của điểm học viên/cross-tenant exposure; cần xác minh actual population.  
> **Owner:** Learning Backend và Report Worker owners.  
> **Remediation:** per-object/tenant policy tại request và worker; scoped repository access; tests.  
> **Verification:** cross-tenant negative tests, positive teacher flow, async side effects, deployed digests và audit.

Các trường **build/release thực tế** phải được thu tại môi trường đánh giá, không bịa thành giá trị đã kiểm chứng.

### 10.3. Viết remediation acceptance thay vì hướng dẫn chung chung

Thay vì “Fix BOLA”, hãy viết:
- Mỗi teacher chỉ được xuất report cho lớp có quan hệ được xác minh trong tenant thích hợp.
- Unauthenticated/learner/teacher ngoài scope bị deny theo policy.
- Worker xác minh job authorization theo delegated/recheck model được phê duyệt.
- No unauthorized DB/queue/file/email side effects.
- Download áp quyền tenant/resource đúng.
- Positive flow vẫn hoạt động.
- Audit actor/resource/decision đúng và không lộ raw grades.
- Production affected digests được cập nhật và retest.

Điều kiện này giúp developer biết **khi nào việc sửa thực sự hoàn tất** và reviewer có test oracle.

## 11. Dynamic findings về authentication và session

### 11.1. Authentication không phải authorization

Một scanner có thể phát hiện:
- Login có cơ chế xác thực yếu hoặc bypass.
- Session token bị chấp nhận khi hết hạn/revoked.
- Cookie thiếu thuộc tính bảo vệ theo security policy.
- Sensitive state change không yêu cầu step-up.
- Password reset hoặc account recovery không xác minh đúng chủ tài khoản.
- Token acceptance không kiểm tra issuer/audience/signature theo policy.
- Multi-factor flow bỏ qua một bước được yêu cầu.

**Authentication** trả lời “actor là ai/được chứng thực ra sao”, **authorization** trả lời “actor được làm gì trên resource nào”. Một kiểm thử login pass không chứng minh resource permissions.

### 11.2. Triage một session finding

Cần:
1. Ghi cookie/token **type và properties**, không copy raw secret.
2. Xác định session lifecycle: login, refresh, revoke, logout, expiry.
3. Phân biệt browser cookie session với bearer token API.
4. Kiểm tra endpoint và trust boundary thực tế.
5. Test trên synthetic identities và temporary sessions.
6. Xem config ở gateway, API, IdP và downstream services.
7. Phân biệt status code với actual action/side effects.
8. Kiểm tra active deployment config/feature flags.
9. Ghi scope giới hạn nếu external IdP không cho xem đầy đủ.
10. Link incident/abuse signals nếu có.

### 11.3. Một số giả định nguy hiểm

- “Có JWT nên hệ thống đã xác thực” — **decode** không đồng nghĩa **verify**.
- “Cookie Secure đủ bảo vệ mọi session” — còn HttpOnly/SameSite/CSRF/session binding và chính sách.
- “Logout trả 200 nghĩa token cũ không dùng được” — cần kiểm tra revocation semantics và thời hạn token.
- “MFA được bật ở IdP” — không tự chứng minh recovery/admin paths đều yêu cầu MFA.
- “Người dùng có role Teacher nên đọc mọi lớp” — phải test object-level authorization.

### 11.4. Test oracle cho session revocation

Ví dụ:
- User đăng nhập hợp lệ và đọc resource thuộc quyền.
- Thu hồi quyền/trạng thái session theo policy.
- Dùng session/token cũ yêu cầu resource nhạy cảm.
- Kỳ vọng denial hoặc scope/expiry behavior đúng thiết kế (không tự áp một semantics cho mọi token).
- Kiểm tra cache/gateway/worker có còn chấp nhận authority cũ trái policy.
- Audit và monitoring ghi event đúng.
- Positive control: user vẫn có thể đăng nhập lại khi được phép.

Nếu một hệ thống dùng short-lived JWT tự chứa và không lập tức revoke mọi token, việc xác minh phải dựa trên **yêu cầu đã được phê duyệt**; không tự xem mọi token tiếp tục valid đến expiry là bypass.

## 12. Finding authorization: BOLA/BFLA và tenant isolation

### 12.1. Đường tấn công phổ biến

- **BOLA/IDOR:** Actor sửa object identifier để truy cập resource người khác.
- **Broken Function Level Authorization:** Role không đúng nhưng gọi được admin action.
- **Property-level authorization:** Actor được đọc object nhưng không được đọc một số fields nhạy cảm.
- **Workflow-level authorization:** Actor thực hiện state transition ngoài thứ tự hoặc thiếu approval.
- **Cross-tenant authorization:** Identity ở tenant A truy vấn object tenant B.
- **Confused deputy:** Worker/service identity có quyền cao thực thi thay actor mà không kiểm tra scope.
- **Stale delegated authority:** Job đang chạy sau khi quyền đổi và vẫn cấp access ngoài policy.

DAST scanner black-box thường không biết **quan hệ actor–object**. Nhiều phát hiện quan trọng chỉ được xác nhận bởi **domain-aware test fixtures**.

### 12.2. Ma trận test role–resource

| Actor | Resource | Expected security outcome |
|---|---|---|
| Teacher A, assigned to class A | Grades A | Allow theo policy |
| Teacher A | Grades B, same tenant but unassigned | Deny |
| Teacher A, tenant A | Grades tenant B | Deny/no cross-tenant disclosure |
| Learner A | Teacher-only export endpoint | Deny |
| Unauthenticated client | Protected grade API | Authentication reject |
| Revoked admin | Privileged report action | Theo revocation/session policy |
| Worker identity | Scoped job B | Chỉ khi source/job/authority hợp lệ |
| External support actor | Bulk export | Giới hạn theo approved support access |

Cần bảo đảm fixtures **không vô tình gán role ADMIN cho cả hai accounts**, nếu không test có thể pass mà không kiểm tra được boundary.

### 12.3. Xem response và side effect

Một permission denial có thể trả **403**, hoặc **404** để không tiết lộ sự tồn tại object. Điều đó tùy policy. Quan trọng:
- Không trả data unauthorized.
- Không thay đổi DB state.
- Không phát queue/job/file trái quyền.
- Không tạo signed URL có quyền tải tệp.
- Không rò metadata qua cache/status/errors.
- Không gửi external notification tiết lộ thông tin.
- Audit ghi rõ action/decision trong quyền xem cho phép.

Một **GET** có thể dùng chung code path với export/cache update; phải kiểm chứng side effects thực thay vì giả định HTTP method an toàn tuyệt đối.

## 13. Java/Spring: ví dụ finding và remediation

### 13.1. Vulnerable implementation: role-only check

~~~java
// Mẫu cố ý thiếu object-level authorization.
public GradeReport exportGrades(
        AuthenticatedPrincipal principal,
        long classId) {

    if (!principal.hasRole("TEACHER")) {
        throw new AccessDeniedException("Forbidden");
    }

    return gradeRepository.getAllGradesForClass(classId);
}
~~~

Nếu role TEACHER có thể xuất mọi lớp theo classId, hệ thống có thể vi phạm quy tắc **chỉ giáo viên được phân công lớp mới được xuất điểm**.

### 13.2. Thiết kế service policy có quan hệ

~~~java
public GradeReport exportGrades(
        AuthenticatedPrincipal principal,
        long classId) {

    CourseClass courseClass = classRepository.findById(classId)
            .orElseThrow(NotFoundException::new);

    if (!gradePolicy.canExport(
            principal.subjectId(),
            principal.tenantId(),
            courseClass.tenantId(),
            courseClass.id())) {
        audit.logDenied(
                principal.subjectId(),
                courseClass.id(),
                "GRADE_EXPORT_NOT_ALLOWED");
        throw new AccessDeniedException("Export not permitted");
    }

    return gradeRepository.findReportByTenantAndClass(
            principal.tenantId(), courseClass.id());
}
~~~

Đây là **mã ý tưởng**, chưa phải implementation có thể sao chép nguyên vào production. Còn cần xét:
- **Principal trust:** lấy từ authentication context đã verify.
- **Policy source:** quan hệ giáo viên–lớp được xác thực, không lấy tùy ý từ request.
- **TOCTOU:** quyền có đổi giữa check và hành động không?
- **DB isolation:** query không bỏ tenant scope, field-level rules.
- **Async path:** worker có quyền riêng và job reference được kiểm soát.
- **Audit reliability:** audit không làm mất event trọng yếu theo policy.
- **Exceptions/error paths:** không trả dữ liệu nhạy cảm qua messages/logs.
- **Cache:** key bao gồm identity/tenant/scope khi cần.
- **Deployment:** fix có trong image/runtime đã kiểm tra.

### 13.3. Integration negative test minh họa

~~~java
@Test
void teacherCannotReadGradesOfUnassignedClass() {
    AuthenticatedPrincipal teacherA =
            fixture.teacherForTenant("tenant-A");
    CourseClass classB =
            fixture.unassignedClassFor(teacherA);

    assertThrows(AccessDeniedException.class,
            () -> gradeService.exportGrades(teacherA, classB.id()));

    assertFalse(reportJobRepository.hasUnauthorizedJob(
            teacherA.subjectId(), classB.id()));
}

@Test
void assignedTeacherCanReadOwnClassGrades() {
    AuthenticatedPrincipal teacherA =
            fixture.teacherForTenant("tenant-A");
    CourseClass classA =
            fixture.assignedClass(teacherA);

    GradeReport report =
            gradeService.exportGrades(teacherA, classA.id());

    assertEquals(classA.id(), report.classId());
}
~~~

Các APIs/fixtures được **giả định** cho bài học. Unit test gọi service chưa thay thế full HTTP/auth-filter, worker, cache, signed download và storage tests. Cần thực thi trên môi trường có quyền với fixture/expected policy rõ.

### 13.4. Kiểm tra không làm mất chức năng hợp lệ

Một fix có thể deny mọi request vì policy không load được. Negative test sẽ “pass”, nhưng hệ thống không usable. Luôn có **positive controls**: actor được phép thực hiện đúng action và nhận dữ liệu hợp lệ, các service dependencies vẫn hoạt động, không có lỗi 5xx ẩn dưới trạng thái deny.

## 14. Xử lý finding về SQL injection

### 14.1. Một 500 error chưa chứng minh SQLi

Một scanner có thể ghi SQLi warning khi query parameter gây 500 hoặc response time thay đổi. Triage cần phân biệt:
- Parser/input validation lỗi.
- Database timeout do tải hệ thống.
- WAF/proxy behavior.
- Query syntax manipulation thực.
- DB-level error/unsafe concatenation.
- Input đã được bind như data.
- Time-based result bị nhiễu bởi network.
- Endpoint không thực hiện query như scanner suy luận.

Nên dùng **safe synthetic inputs và non-destructive assertions** trong lab/staging khi có thể; không cần extract data production để chứng minh.

### 14.2. Anti-pattern trong Java

~~~java
// Không an toàn: user input tham gia tạo SQL syntax.
String query =
        "SELECT id, grade FROM grades WHERE class_id = "
        + request.getParameter("classId");

ResultSet results = connection.createStatement()
        .executeQuery(query);
~~~

Remediation ưu tiên **parameter binding** đối với values:

~~~java
String query = """
        SELECT id, grade
        FROM grades
        WHERE tenant_id = ? AND class_id = ?
        """;

try (PreparedStatement statement =
             connection.prepareStatement(query)) {

    statement.setString(1, principal.tenantId());
    statement.setLong(2, classId);

    try (ResultSet results = statement.executeQuery()) {
        // Mapping fields theo mục đích/authorization.
    }
}
~~~

**Cảnh báo:** một prepared statement vẫn có thể unsafe nếu raw SQL fragment như **ORDER BY + client sort field** bị nối trực tiếp; identifiers cần allowlist mapping. Query cũng phải enforce tenant/object authorization riêng.

### 14.3. Verification cho finding SQLi

- Original sink/source path được tìm và sửa.
- Dynamic SQL syntax không còn nhận raw untrusted fragments.
- Positive data query đúng.
- Inputs chứa quote/special characters được xử lý như values.
- Dynamic identifiers/field names có server-side allowlist.
- Related query builders/sibling paths được review.
- DB role least privilege và query timeouts phù hợp.
- Không lộ SQL/PII/credentials qua error messages.
- Re-scan SAST/DAST phù hợp, scan coverage/target được xác nhận.
- Deploy đúng artifact và có regression test.

Không dùng **HTTP 200/500** đơn lẻ làm test oracle.

## 15. Xử lý finding về XSS, CSRF và browser behavior

### 15.1. XSS cần đúng output context

Một input xuất hiện trong response không đồng nghĩa script đã chạy. Cần kiểm tra:
- Render context: HTML text, attribute, JavaScript, CSS, URL hoặc DOM sink.
- Template auto-escaping tại engine/version cụ thể.
- Stored vs reflected vs DOM-based behavior.
- Browser constraints và data flow từ source tới sink.
- Context-specific output encoding hoặc approved sanitizer.
- CSP và browser isolation như defense in depth, không thay encoding.
- Views khác của cùng dữ liệu: email/admin dashboard/preview.
- Sensitive session/data impact.

Một payload trong text được HTML-escaped đúng có thể là **false positive** theo rule XSS, nhưng raw interpolation trong inline script có thể vẫn là TP. Phải review **từng context**, không suppress toàn template.

### 15.2. CSRF: nhìn vào authentication model

CSRF chủ yếu liên quan **browser-automated credentials** và state-changing requests. Với cookie-authenticated browser sessions, cần test token/origin/SameSite và contract của framework. Với API dùng bearer token chỉ do JS chủ động thêm qua Authorization header, attack preconditions có thể khác. Không gọi mọi POST “CSRF vulnerability” hoặc mọi SameSite cookie “đã an toàn” mà không xác định auth/session behavior.

### 15.3. Regression tests

- Legitimate form/API action hoạt động khi có token/authorization hợp lệ.
- Cross-site/cross-origin request không tạo mutation trái policy.
- Session cookies/CSRF settings áp đúng paths.
- Không có bypass do content type, method override, exception route hoặc redirect.
- XSS synthetic strings không thực thi ở các views trong scope.
- Positive control kiểm tra page không bị disable toàn bộ để “pass”.

## 16. Xử lý SSRF, URL fetch và network-boundary findings

### 16.1. Phân biệt request parameter và đích thực

SSRF warning có thể đến từ user-provided URL đi vào HTTP client. Cần xét:
- Client kiểm soát host, scheme, port, path, DNS resolution hay chỉ một server-approved resource ID?
- Có redirect tự động tới địa chỉ ngoài allowlist không?
- DNS rebinding/IPv4/IPv6/private/link-local destinations được xử lý?
- Egress network policy thật có giới hạn?
- Client có đính kèm Authorization/metadata headers không?
- Cloud workload identity có quyền truy cập metadata/management plane?
- Parser/canonicalization có thống nhất?
- Proxy/gateway có đường bypass?
- URL từ database/config có thể do tenant/admin sửa không?
- Tài sản và authorization scope của URL fetch có đúng không?

### 16.2. Remediation theo trust boundary

Ví dụ:
- Server chọn đích từ mapping **được phê duyệt, không do user sửa**.
- Giới hạn protocol/destination/redirect policy.
- Kiểm tra resolved IP/hostname và policy ở đúng thời điểm.
- Defense in depth bằng network egress restrictions và workload least privilege.
- Resource limits, timeout, response size bounds.
- Không forward sensitive headers tới đích không đáng tin.
- Có audit/network monitoring phù hợp.

Một allowlist thiếu kiểm tra redirect/DNS hoặc network egress chưa được áp vẫn có thể bị bypass. “Chỉ chặn localhost” không đủ là thiết kế chống SSRF toàn diện.

### 16.3. Retest an toàn

Dùng controlled endpoints trong lab, DNS/service fixtures do nhóm sở hữu, quan sát egress destinations và HTTP client behavior. Không yêu cầu scanner truy cập metadata nội bộ, partner API thật hoặc scan cloud tenant ngoài thẩm quyền. Test có positive allowed partner URL và negative disallowed synthetic URL theo policy.

## 17. Xử lý file upload, traversal và resource exhaustion

### 17.1. File upload finding

Các lớp risk:
- Chấp nhận file ngoài type/policy.
- Raw filename ảnh hưởng đường dẫn lưu.
- File/zip decompress gây resource exhaustion.
- Upload được public serve với content-type/content-disposition sai.
- Malware content không có quarantine hoặc scan control theo risk.
- Object access thiếu tenant permissions.
- File path traversal/symlink/race.
- Worker converter có native library vulnerability.
- Metadata/exif/filename làm lộ PII/paths.

### 17.2. Những kiểm tra cần trong triage

- Allowed file types/MIME/magic bytes theo mục đích.
- Size/count/decompression-depth/processing time limits.
- Streaming và bounded memory.
- Unique opaque object IDs thay raw filenames.
- Object storage private by default và scoped download authorization.
- Processing isolation/sandbox của converter.
- Quarantine/scan workflow nếu policy yêu cầu.
- Antivirus/scanner unavailability có fail behavior được định.
- Retention, cleanup và quota.
- Audit allow/deny/failed upload, không ghi raw file contents.

### 17.3. Negative test không gây phá hoại

Dùng controlled oversized files, malformed file fixtures, known harmless test string và synthetic IDs trong sandbox, theo resource budget. Không upload malware thật hoặc làm quá tải dịch vụ ngoài phạm vi được cho phép.

### 17.4. Path traversal không hết chỉ vì normalize()

Một cách kiểm tra directory boundary có thể xử lý **..**, nhưng symlink, TOCTOU và file permissions vẫn quan trọng. Sau sửa cần review semantics của storage layer và thử negative scenarios phù hợp; không đánh false positive chỉ khi nhìn thấy một lệnh normalize().

## 18. Xử lý lỗi async: queue, worker và “denied nhưng vẫn xử lý”

### 18.1. Vì sao dynamic test cần nhìn xa hơn HTTP?

Nhiều hệ thống dùng:
- HTTP endpoint tạo job.
- Transactional outbox hoặc queue.
- Background report worker.
- Object storage.
- Notification vendor.
- CDN/download.
- Retry và reconciliation.

Một API trả **202 Accepted** không có nghĩa export đã hoàn thành. Một API trả **403** cũng không bảo đảm job/file chưa được tạo nếu authorize xảy ra quá muộn.

### 18.2. End-to-end flow

~~~mermaid
flowchart LR
    U["Teacher / learner"] --> G["Gateway"]
    G --> A["Learning API"]
    A --> DB[("Classes/Grades DB")]
    A --> Q[["Export Queue"]]
    Q --> W["Report Worker"]
    W --> OS[("Private Object Storage")]
    OS --> DL["Authorized download"]
    A --> AU["Audit Pipeline"]
    W --> AU
    DL --> AU
~~~

### 18.3. Finding triage theo workflow

| Bước | Quan sát cần có | Side effect/permission concern |
|---|---|---|
| Request | Actor, class/tenant, action | Input/client claims không được tin làm identity |
| Authorization | Policy decision/version | Object/tenant relationship, deny-by-default |
| Job accepted | Job ID, trusted scoped context | Job record không được tạo khi deny |
| Queue processing | Worker identity và job provenance | User không tự publish job có quyền cao |
| Worker authorization | Scope/recheck/delegation TTL | Quyền stale, duplicate/replay |
| Storage write | Object key và tenant scope | Không ghi file ngoài quyền hoặc public |
| Download | Actor/resource/file authorization | Signed URL TTL/revocation theo policy |
| Notification | Recipient/purpose | Không gửi thông báo tiết lộ grade data |
| Audit | Event correlation | Không ghi raw grades/tokens; monitoring health |

### 18.4. Test temporal và replay

Trong môi trường test được ủy quyền:
- User tạo request hợp lệ, sau đó bị thu hồi quyền trước khi worker thực thi.
- Queue gửi lặp job do at-least-once semantics.
- Worker restart sau khi tạo file nhưng trước khi ack.
- Job bị cancel hoặc tenant status thay đổi.
- File được tải sau khi actor mất quyền.
- Client giả job ID/tenantId.
- Load balancer trả response từ instance có policy cũ.

Expected behavior phụ thuộc **delegated authority model** được phê duyệt: có hệ thống cho phép job đã được phê duyệt hoàn thành; hệ thống khác yêu cầu recheck quyền tại execution. Không tự áp một quy tắc cho mọi sản phẩm; phải test đúng policy và ghi assumptions.

### 18.5. “No side effects” phải có observation window

Nếu kiểm tra job table ngay sau HTTP response, worker có thể thực hiện muộn. Test cần bounded timeout hoặc stable completion condition, đối chiếu DB/queue/storage/notification và cleanup. Bằng chứng “không thấy job trong 50 ms” không chứng minh không có side effect trong hệ thống async có eventual consistency.

## 19. False positives trong dynamic testing

### 19.1. Nguyên nhân phổ biến

- DAST diễn giải lỗi HTTP 500 là SQL injection dù parser chỉ có lỗi input.
- Scanner xác định reflected value là XSS dù template encode đúng.
- Header thiếu trên một response 302/404 nhưng policy chỉ yêu cầu trên resource nhạy cảm (cần kiểm tra definition).
- Time-based response khác do network load.
- Dynamic login khiến tool chưa authenticated.
- WAF/challenge page trả content khác và bị xem là exploit result.
- Scanner quét route cũ hoặc host/virtual service không đúng.
- Vulnerability đã được fix ở một build mới nhưng report là stale.
- Response echo test string mà không có unsafe browser execution.
- Rate limiting tạo status/response khác khiến heuristic nhầm.

### 19.2. Rationale FP có căn cứ

Một technical FP decision nên nói:
- **Rule/threat:** Scanner cáo buộc điều gì.
- **Observation:** Payload/response nào dẫn tới kết luận.
- **Alternate cause:** Vì sao observation không chứng minh weakness.
- **Verified behavior:** Code/config/runtime test nào bác bỏ path.
- **Scope:** Target build/endpoint/role/config.
- **Known limitations:** Chưa kiểm tra đường nào.
- **Reviewer và trigger:** Ai xác nhận, khi nào reassess.

Ví dụ, “XSS marker được phản chiếu trong HTML text nhưng đã được entity-escaped bởi template version V; browser test synthetic payload không tạo script execution trong context này, code/template review xác nhận không có raw render tại call site. Các views khác chưa nằm trong quyết định.”

### 19.3. Không được che vulnerability còn thật

WAF chặn SQLi payload nhưng code ghép query vẫn unsafe là **mitigated true positive**, không phải FP. Hệ thống không reachable từ Internet nhưng attacker nội bộ có access vẫn có thể khai thác theo threat model; **network isolation** không tự biến weakness thành false alarm.

## 20. Finding liên quan tool coverage và health

### 20.1. “No findings” khi scan failed

Một scanner có thể:
- Timeout/abort trước khi test API.
- Quên load OpenAPI schema.
- Mất quyền login/session.
- Crawl chỉ được landing page.
- Bị rate limit/WAF chặn.
- Gửi request tới deprecated host.
- Dùng scan profile loại security rules quan trọng.
- Không upload report thành công.
- Có lỗi parser khiến events không vào dashboard.
- Bị rollback tool version hoặc stale policy.

Kết quả này phải là **INSUFFICIENT_EVIDENCE/SCAN_FAILURE**, không phải ZERO FINDINGS.

### 20.2. Health metrics tối thiểu

- Scan run started, completed, failed, skipped.
- Target reachability và identity.
- Auth/login success và protected route coverage.
- Number of routes/operations attempted.
- Response status mix, 401/403/429/5xx trends.
- Rule/plugin enabled count, config version.
- Expected test fixtures triggered.
- Tool engine/reporter ingestion errors.
- Scan freshness và next due date.
- Credential expiration và approvals.
- Evidence link availability.

### 20.3. Dashboard phải tách security và telemetry health

**Không có security findings** chỉ có ý nghĩa khi tool chạy, target đúng, coverage đạt. Nếu không, hiển thị **UNKNOWN / UNHEALTHY / NOT ASSESSED**. Không dùng một màu xanh cho cả “scan không thấy lỗi” và “scan chưa chạy”.

## 21. Root-cause analysis: sửa nguyên nhân, không chỉ triệu chứng

### 21.1. Từ observed behavior tới nơi cần sửa

Dynamic test thường nhìn thấy **triệu chứng ở ranh giới**: dữ liệu lộ, quyền được cấp sai, response không đúng, hệ thống chậm hoặc network request đi ngoài policy. Root cause có thể nằm ở:
- Gateway/security filter chưa áp đúng.
- Service thiếu object authorization.
- Repository query không có tenant scope.
- Cache key/routing làm trộn tenants.
- Queue worker tin message không đáng tin.
- Network/IAM/cloud policy quá rộng.
- Serialization/template chưa encode đúng context.
- Query builder ghép raw identifiers.
- File converter không có resource limit.
- Identity lifecycle/session invalidation chưa áp.
- Error handling/logging tiết lộ thông tin.
- Shared library/framework config ở nhiều services.

### 21.2. Bảng symptom → root cause → fix → proof

| Dynamic symptom | Root cause cần kiểm tra | Remediation gợi ý | Verification |
|---|---|---|---|
| User A xem điểm lớp B | Role-only check, missing tenant relation | Object-level policy + data scoping | Cross-tenant negatives, DB/queue side effects |
| SQLi-like behavior | Raw SQL concatenation | Bind values + allowlist identifiers | Code review, safe input, DAST/SAST |
| Stored XSS | Raw HTML/DOM sink | Context-aware encoding/sanitization | Browser rendering across views |
| SSRF | Arbitrary destination/redirect | Approved destination + egress policy | Controlled endpoints, redirect/egress checks |
| Public report object | Storage policy/signed URL scope | Private storage + authorized download | Anonymous/cross-tenant denial |
| Old token vẫn làm privileged action | Session/permission revocation semantics | Enforce lifecycle policy | Pre/post revocation workflow |
| API trả 403 nhưng worker vẫn export | Authorization sau enqueue hoặc worker tin queue data | Check before durable action + worker-side policy | Job/storage/notification assertions |
| File upload gây tải cao | Bounded processing thiếu | Quota, streaming, isolation, timeout | Safe resilience fixtures |
| Diagnostic log lộ token | Raw request logging | Structured allowlist/redaction + rotate | Synthetic secret canaries, sink inspection |
| Missing audit event | Emission/delivery pipeline gap | Durable audit and monitoring | Synthetic end-to-end event, outage test |

Không dùng “đã đổi một dòng” như căn cứ đóng mọi instances. Hãy liên kết **root-cause class** tới mọi code paths/assets thuộc population.

### 21.3. Fix có thể làm nảy sinh vulnerability khác

Một bản vá nóng có thể:
- Tắt authentication trên health/admin endpoint.
- Chặn mọi request hợp lệ vì deny-by-default không có exception hợp lệ.
- Tạo race mới khi authorize và mutate tách biệt.
- Ghi raw request vào audit log.
- Tăng database load do extra authorization query.
- Dùng signed URL dài hạn không thu hồi.
- Nâng dependency kéo vulnerable transitive package khác.
- Dẫn tới rollback dùng image cũ.

Vì vậy remediation phải có **functional regression + security regression + non-functional tests** theo risk.

### 21.4. Kết luận chính xác khi chỉ có mitigation

Nếu root cause chưa sửa nhưng chặn ingress bằng WAF, cần ghi MITIGATED, operational monitoring, ownership, expiry và residual risk. Có thể giảm priority nhưng không nên thay technical verdict thành FP/Fixed. Nếu nghĩa vụ pháp lý/hợp đồng yêu cầu sửa, risk acceptance cũng không tự làm nghĩa vụ biến mất.

## 22. Remediation workflow có kiểm soát thay đổi

### 22.1. Phân loại loại thay đổi

- **Code fix:** sửa service/controller, template, query, parser.
- **Configuration fix:** security headers, TLS, CORS, cloud IAM, storage.
- **Dependency fix:** version upgrade, backport, rebuild artifact.
- **Architecture fix:** privilege separation, scoped queue workers, network segmentation.
- **Operational mitigation:** disable feature, rotate key, revoke access, rate limit.
- **Incident containment:** tạm ngắt compromised path, preserve evidence.
- **Process fix:** thêm regression rule, owner, change approval hoặc monitoring.

### 22.2. Change record cho finding

Một change record tối thiểu:
- Finding IDs, risk, affected assets.
- Root-cause hypothesis/validated cause.
- Remediation design và reviewer.
- Source revision, PR/change ID.
- Tests expected trước release.
- Migration/configuration/feature flag requirements.
- Backout/rollback và security consequences.
- Build artifact/version/digest.
- Deployment plan và affected population.
- Re-scan plan, acceptance criteria, owner.
- Monitoring/alert changes.
- Residual risk/exception nếu chưa fix đủ.

### 22.3. Emergency fixes

Với active exploitation, response có thể cần **containment trước full verification**. Nhưng cần:
1. Quyền phê duyệt incident/feature shutdown.
2. Đánh giá side effects/availability.
3. Ghi evidence và initial scope trước khi thay đổi nếu an toàn.
4. Áp mitigation và kiểm tra quick negative control.
5. Chuẩn bị root-cause fix.
6. Deploy kiểm soát và test.
7. Retest toàn scope có thời hạn.
8. Hủy exception tạm khi fix hoàn tất.
9. Post-incident review và tracking remaining risk.

Không khẳng định “verified fixed” khi mới có evidence mitigated.

## 23. Re-test sau remediation: những tầng cần chứng minh

### 23.1. Tầng thứ nhất: original finding

Đưa hệ thống về precondition đã tạo lỗi, chạy lại **test tối thiểu có thẩm quyền**, so expected/actual. Nếu scanner dùng cookie cũ và mọi request giờ trả 401, test gốc **chưa kiểm tra**. Cần authenticated context tương đương.

### 23.2. Tầng thứ hai: positive và negative controls

- **Positive:** user hợp lệ vẫn thực hiện được business action.
- **Negative:** user ngoài quyền không thực hiện được.
- **Boundary:** input invalid, extreme nhưng trong resource budget, session expired, tenant mismatch.
- **Sibling path:** cùng weakness tại endpoints liên quan.
- **Temporal:** revoke, delayed queue, rollback, expiry.
- **Side effects:** DB, queue, storage, emails, logs.

### 23.3. Tầng thứ ba: deployment identity

Một test pass ở staging không tự chứng minh production đang chạy fix. Cần source commit → build ID → artifact/image digest → release approval → deployed digest → runtime config mapping. Nếu không thể test xâm lấn production an toàn, có thể sử dụng **production-equivalent tests + deployed config/digest evidence + limited non-destructive probes**, nêu giới hạn.

### 23.4. Tầng thứ tư: monitoring/operating period

Đối với high-risk issues, closure có thể cần quan sát sau rollout:
- Số instance cũ còn chạy.
- Security denial/abuse signals.
- Application/worker error rate.
- Queue lag và duplicate jobs.
- Audit event delivery.
- API response anomalies.
- Config drift/rollback events.

Đừng suy “không có incidents trong tuần” là proof không còn vulnerability nếu logs/detection coverage chưa được chứng minh.

### 23.5. Test outcome không chỉ Pass/Fail

| Outcome | Định nghĩa |
|---|---|
| **PASS** | Test thực thi, đúng target, expected behavior đạt, evidence đủ trong scope |
| **FAIL** | Behavior trái acceptance criteria |
| **BLOCKED** | Precondition/dependency không thỏa, test không thể chạy |
| **NOT_RUN** | Chưa thực thi |
| **ERROR** | Test tool/lab/permission hỏng |
| **INCONCLUSIVE** | Kết quả không đủ chứng minh do nhiễu hoặc limits |
| **NOT_APPLICABLE** | Có lý do rõ kiểm tra không áp dụng |
| **EXCEPTION** | Có quyết định phê duyệt deviation; không tự là PASS |

Không tính BLOCKED/NOT_RUN/ERROR thành PASS chỉ để tăng verification coverage.

## 24. Bản sửa có hiện diện trong production không?

### 24.1. Build-to-runtime chain

~~~mermaid
flowchart LR
    C["Fix commit C"] --> B["CI build B"]
    B --> I["Image / artifact digest D"]
    I --> P["Approved release"]
    P --> K["Cluster / runtime digest D"]
    K --> T["Safe runtime retest + config"]
    T --> E["Closure evidence"]
~~~

Một mutable image tag như latest/prod có thể được thay mà không đổi tên. Với container cần đối chiếu **image digest**; với JAR/VM có thể dùng **artifact checksum/build ID** phù hợp. Nhận diện phải gắn target trong scan report, không suy từ tên môi trường.

### 24.2. Fleet-level coverage

Một hệ thống có:
- Nhiều clusters/regions.
- Canary và blue/green deployments.
- Old pods/VM instances.
- Scheduled jobs/cronjobs.
- DR standby.
- Sidecars và agents.
- Worker với image khác API.
- Rollback reference tới release cũ.

Re-scan một endpoint dễ trúng instance mới trong khi service khác còn vulnerable. **Affected population** và **actual deployed versions** là phần của closure claim.

### 24.3. Rollback cũng là một security change

Khi rollback về image cũ vì availability issue:
- Xác định image cũ từng có confirmed findings nào.
- Risk owner/incident leader quyết định phù hợp.
- Áp controls tạm nếu cần.
- Reopen technical findings đã quay trở lại.
- Ghi incident/change timeline.
- Deploy fixed stable image rồi retest.
- Update inventory và reports.

**Finding closed không đồng nghĩa vulnerability không thể tái xuất.**

## 25. Re-scan policy, scanner changes và coverage

### 25.1. Cùng điều kiện test để so trước/sau

So sánh result chỉ có giá trị khi biết:
- Original/retest scanner engine và rule changes.
- API spec/crawl scope.
- Authentication roles/tenant fixtures.
- Request payload classes.
- Target environment/build.
- Browser/network/proxy configuration.
- Policy version/include-exclude rules.
- Rate limits, WAF behavior.
- Tool errors và sampling.
- Start/end timestamps.

### 25.2. Dùng cả baseline reproduction và scan hiện hành

Một cách tốt:
1. **Reproduce finding cũ** bằng điều kiện tương đương (hoặc giải thích vì sao không thể).
2. **Run updated scan** để kiểm tra variants/new issues với current ruleset.
3. **Review delta**: original finding, new findings, missing rules, changed asset scope.
4. **Manual/domain tests** cho logic nghiệp vụ mà generic scanner khó thấy.
5. **Report limitations** nếu scan coverage khác trước.

Nếu finding ID biến mất do rule renaming, phải map stable fingerprint hoặc giữ evidence, không auto-close.

### 25.3. Failure modes của pipeline

| Failure | Không nên kết luận | Việc cần làm |
|---|---|---|
| Scanner job timeout | “0 vulnerabilities” | Rerun, fix tool health |
| Session hết hạn | “Authz fixed” | Reauthenticate, verify route coverage |
| API URL đổi | “Finding disappeared” | Remap target, check legacy/bypass |
| WAF chặn mọi payload | “Source code fixed” | Separate mitigation from remediation |
| Scanner rule disabled | “No finding” | Restore controls/approval |
| SCA database stale | “No CVE” | Update feed, note time |
| Target 503/unavailable | “Exploit prevented” | Availability regression/Unknown |
| Partial report upload | “Scan passed” | Fix ingestion, integrity check |
| Old image region missed | “Fleet fixed” | Deploy/reconcile, partial finding |

### 25.4. Scan history và historical claims

Store original/retest report refs, scan policy versions và artifact IDs. Khi mới có advisory/rule, cần có khả năng rà lại **old release**; không overwrite toàn bộ lịch sử bằng “latest scan”.

## 26. Claim–Argument–Evidence (CAE) cho finding closure

### 26.1. Claim phải hẹp và có điều kiện

**Claim minh họa:**

> Trong phạm vi các API export, report worker và download paths đã inventoried ở release R, môi trường E và kỳ T, finding F về cross-tenant grade export không còn tái hiện theo các negative/positive/temporal tests đã xác định. Fixed artifact digests được xác nhận tại targets trong scope, và không xuất hiện unauthorized DB/queue/storage/email side effects trong điều kiện kiểm thử. Các legacy paths chưa được kiểm tra được ghi riêng, không thuộc claim này.

Đây là **mẫu cách viết**, không phải kết quả kiểm thử sản phẩm thật.

### 26.2. Argument

1. Finding F đã được xác minh với original reproduction.
2. Threat/security objective và actor–resource policy rõ.
3. Root-cause fix giải quyết sai sót tại đúng control point.
4. Approved code/config/digests được triển khai trong affected population.
5. Re-scan đúng tool/identity/coverage và thành công.
6. Negative tests không tái hiện unauthorized access.
7. Positive tests xác minh business flow hợp lệ.
8. Async/side effects và alternate routes được test theo risk.
9. Evidence bảo toàn provenance/time và không lộ sensitive data.
10. Unknowns/exceptions được tách, reviewer kết luận theo policy.

### 26.3. Evidence cần gắn

- Initial finding/test run và redacted reproduction.
- Risk/asset classification, accepted policy requirements.
- Fix PR/commit/build/deployment records.
- Authenticated API scanner report và coverage metadata.
- Synthetic test cases và results.
- DB/queue/file/audit event evidence.
- IAM/config scope khi có.
- Release/region/image inventory.
- Independent reviewer/closure reason.
- Known limitations, linked findings, residual risk.

### 26.4. Ba cấp effectiveness

| Lớp | Câu hỏi | Evidence |
|---|---|---|
| **Design effectiveness** | Fix thiết kế có ngăn root cause trong threat model không? | Requirements, architecture/policy review |
| **Implementation effectiveness** | Code/config và các tests trên artifact đã build đúng không? | PR, unit/integration/DAST, scan/binary results |
| **Operating effectiveness** | Fix đã chạy ở environment/kỳ/asset population được công bố và duy trì không? | Runtime digests, safe probes, monitoring/drift records |

Một DAST scan pass trên staging chứng minh **một phần implementation**, không chứng minh production operating effectiveness trên mọi regions.

## 27. Mẫu YAML hồ sơ xử lý finding

Mẫu dưới chứa **dữ liệu hư cấu và placeholders**; không dùng làm evidence thật hoặc tự hiểu là đã xác minh. Nó là schema nội bộ minh họa, không phải một format DAST chuẩn.

~~~yaml
finding_id: "DYN-FND-LEARNING-EXAMPLE-042"
title: "Cross-tenant grade export authorization"
source:
  testing_type: "authenticated-api-dynamic-test"
  scan_run: "populate-actual-run-id"
  scanner_name_version: "populate-tool-and-version"
  scan_policy_version: "populate-policy-version"
  api_spec_version: "populate-api-contract"
  observed_at: "populate-timestamp"
  tester: "authorized-security-tester"
target:
  service: "learning-api"
  environment: "production-equivalent-test"
  original_artifact_digest: "populate-original-sha256"
  fixed_artifact_digest: "populate-fixed-sha256"
  deployment_reference: "populate-deploy-record"
  affected_routes:
    - "POST /api/v1/classes/{classId}/export"
    - "GET /api/v1/classes/{classId}/grades"
  related_components:
    - "report-queue"
    - "report-worker"
    - "private-object-storage"
scope:
  actors: ["synthetic-teacher-A", "synthetic-teacher-B"]
  tenants: ["synthetic-tenant-A", "synthetic-tenant-B"]
  exclusions:
    - "Legacy batch export not yet verified"
finding:
  suspected_weakness: "Broken Object Level Authorization"
  technical_status: "CONFIRMED"
  original_evidence: "link-to-redacted-proof"
  expected: "Deny unassigned teacher without export side effects"
  actual: "Unauthorized export job accepted in initial test"
risk:
  data_class: "student-grade-data"
  priority: "populate-approved-risk-rating"
  owner: "Learning Backend service owner"
remediation:
  root_cause: "Role-only policy lacked actor-class relation"
  approved_fix_change: "populate-pr-or-change-id"
  test_plan: "link-to-targeted-tests"
verification:
  re_scan_status: "PENDING"
  authenticated_coverage: "PENDING"
  deployed_digest_reconciled: "PENDING"
  targeted_tests:
    - id: "DYN-T03"
      expected: "Cross-tenant denied, no data disclosed"
      actual: "PENDING"
    - id: "DYN-T14"
      expected: "No unauthorized job or file created"
      actual: "PENDING"
    - id: "DYN-T22"
      expected: "Positive assigned teacher export works"
      actual: "PENDING"
  evidence_locations: []
assessment:
  decision: "INSUFFICIENT_EVIDENCE"
  reviewer: "assign-authorized-reviewer"
  closure_approved: false
  limitations:
    - "Not verified against legacy batch entry point"
  residual_risk_approval: "PENDING"
reassessment_triggers:
  - "New API or worker path"
  - "Authorization policy change"
  - "Rollback or deployment drift"
  - "Scanner coverage failure"
  - "Incident or finding recurrence"
~~~

### 27.1. Giữ technical và governance fields riêng

**technical_status=CONFIRMED** nói finding ban đầu có thật; **verification.re_scan_status=PENDING** nói chưa kiểm tra bản sửa; **assessment.decision=INSUFFICIENT_EVIDENCE** nói chưa đủ kết luận đóng. Đừng dùng một boolean **fixed=true** để che sự khác biệt này.

### 27.2. Xử lý linked finding/duplicates

Một root cause có thể gắn nhiều URLs/roles/services. Dù gộp vào cùng parent ticket, giữ **affected variants** và tests. Khi một variant chưa fix, parent status có thể PARTIALLY_FIXED hoặc needs review; không xóa row đó khỏi population để báo full closure.

## 28. Catalog yêu cầu xử lý finding có thể kiểm chứng

Các mã **DYN-REQ-001…DYN-REQ-030** là **quy ước nội bộ minh họa của bài**, không phải standard/control ID được ban hành bởi OWASP, NIST hay một công cụ DAST.

| ID | Requirement | Acceptance criteria |
|---|---|---|
| **DYN-REQ-001** | Mọi dynamic finding có unique ID và scan/test source | Run ID, target, tool/timestamp, owner |
| **DYN-REQ-002** | Kiểm tra tool health trước triage | Failure/partial reports không thành Pass |
| **DYN-REQ-003** | Dynamic scan có authorization/ROE | Approved target, rate/stop/cleanup records |
| **DYN-REQ-004** | Target identity và build/config rõ | Service/environment/digest/version links |
| **DYN-REQ-005** | Authenticated scan có coverage proof | Actor/session/role/tenant và protected routes |
| **DYN-REQ-006** | Findings có expected vs actual behavior | Reproduction/technical rationale |
| **DYN-REQ-007** | Evidence được redact và lưu có kiểm soát | No raw tokens/grades; provenance/access |
| **DYN-REQ-008** | FP và unknown không trộn với verified | Reviewer/taxonomy tests |
| **DYN-REQ-009** | Severity dựa on contextual risk | Impact/exposure/preconditions/controls |
| **DYN-REQ-010** | Confirmed findings có owner và timeline | SLA, escalation/ack tracking |
| **DYN-REQ-011** | Các affected paths và assets được inventoried | Route/service/region/tenant population |
| **DYN-REQ-012** | Root-cause remediation được review | Requirement, code/config/change evidence |
| **DYN-REQ-013** | Positive control có trong retest plan | Legitimate business action vẫn hoạt động |
| **DYN-REQ-014** | Negative tests cho resource/tenant/role | Unauthorized actor denied/no disclosure |
| **DYN-REQ-015** | Side effects được kiểm tra khi phù hợp | DB/queue/storage/vendor/audit outcomes |
| **DYN-REQ-016** | Async/replay/revocation behavior được đánh giá | Worker/job/TTL/recheck tests theo policy |
| **DYN-REQ-017** | DAST/SAST/SCA/cloud methods đúng weakness | Method selection justification |
| **DYN-REQ-018** | Scanner policy/ruleset/delta có provenance | Tool/config/current scan vs baseline |
| **DYN-REQ-019** | Fix gắn đúng source/build/deployment | Commit/build/image digest/runtime |
| **DYN-REQ-020** | Fleet rollout không còn affected instance | Actual inventory/reconciliation |
| **DYN-REQ-021** | Scan timeout/401/WAF block không thành zero findings | Unknown/error/coverage gate |
| **DYN-REQ-022** | Regression test kiểm tra sibling paths | Root-cause class coverage |
| **DYN-REQ-023** | Mitigation/acceptance giữ technical verdict | Risk approval/expiry/compensation |
| **DYN-REQ-024** | Closure phải có evidence và reviewer | Verified vs accepted/FP reason codes |
| **DYN-REQ-025** | Finding reopens khi rollback/regression | Trigger/event tests |
| **DYN-REQ-026** | Exception và limits được report | Ownership, scope, action/deadline |
| **DYN-REQ-027** | Scan reports có retention/confidentiality | IAM/backup/evidence reference |
| **DYN-REQ-028** | Scan platform health được monitor | Credentials, coverage, job errors, rule drift |
| **DYN-REQ-029** | Metrics dùng đúng populations và states | Reopened/partial/unknown không tính Fixed |
| **DYN-REQ-030** | Continuous assurance được thực hiện | Change/advisory/incident reassessment records |

### 28.1. Một requirement cụ thể

**DYN-REQ-024 — Closure evidence và reviewer**

- **Risk:** kỹ thuật chưa fix nhưng ticket bị đóng do tool báo zero findings.
- **Population:** confirmed high-impact findings thuộc critical services.
- **Trigger:** owner đề nghị Verified Fixed hoặc close.
- **Required:** root-cause fix/change, deployed artifact identity, re-scan/test results with coverage, positive/negative tests, side effects/variants theo finding, known limits.
- **Failure behavior:** missing/failed scan → INSUFFICIENT_EVIDENCE; retest reproduced → STILL_PRESENT; incomplete fleet → PARTIALLY_FIXED.
- **Approval:** reviewer đúng thẩm quyền; risk acceptance là quyết định riêng.
- **Evidence:** immutable run refs, source/deploy versions, actual results, assessment date, owner.
- **Reopen:** rollback/new affected path/security change hoặc incident.

### 28.2. Áp requirements theo risk, không máy móc

Không bắt mọi TLS header finding phải test queue side effects; không dùng SCA để kết luận object authz. Requirements cần được **chọn theo weakness, threat model, relevant trust boundaries và business criticality**.

## 29. Ma trận 40 phép kiểm thử cho finding lifecycle

Các mã **DYN-T01…DYN-T40** là catalog minh họa, không phải bộ test bắt buộc cho mọi finding. Một số test cần dữ liệu giả, sandbox, phạm vi được ủy quyền hoặc phê duyệt riêng. **Test oracle** phải lấy từ requirement/business policy và baseline evidence, không chỉ từ kết quả của scanner.

| Test ID | Scenario | Expected/verification |
|---|---|---|
| **DYN-T01** | Scan API đúng target/build | Report gắn service/environment/digest |
| **DYN-T02** | Scanner token hết hạn | Coverage gap, không Pass |
| **DYN-T03** | Cross-tenant read actor A/resource B | Deny/no data exposure |
| **DYN-T04** | Assigned teacher đọc lớp thuộc quyền | Positive control pass |
| **DYN-T05** | Role TEACHER không được sửa admin permissions | BFLA negative test deny |
| **DYN-T06** | Unauthenticated actor gọi protected API | Reject theo authn policy |
| **DYN-T07** | Token bị revoke trước privileged action | Behavior đúng lifecycle policy |
| **DYN-T08** | Forged tenant/role header | Server không tin unchecked claims |
| **DYN-T09** | SQL input chứa ký tự đặc biệt | Không điều khiển SQL syntax, chức năng đúng |
| **DYN-T10** | Dynamic ORDER BY raw identifier | Reject/untrusted field mapped server-side |
| **DYN-T11** | Stored text render ở HTML context | Không thực thi script ngoài policy |
| **DYN-T12** | Stored data hiển thị trong admin/email view | Encoding/sanitization theo từng sink |
| **DYN-T13** | CSRF trên cookie-authenticated mutation | State không thay đổi trái policy |
| **DYN-T14** | Denied export request | Không unauthorized job/file/notification |
| **DYN-T15** | Worker nhận job ngoài scope | Không thực thi với quyền service quá mức |
| **DYN-T16** | Queue message replay/duplicate | Idempotency/authorization semantics đúng |
| **DYN-T17** | Revoke assignment trước worker execution | Kết quả theo approved delegated/recheck model |
| **DYN-T18** | Private report download bởi tenant khác | Deny, không lộ nội dung/file metadata |
| **DYN-T19** | SSRF request tới synthetic disallowed destination | HTTP client/network policy chặn |
| **DYN-T20** | SSRF redirect ngoài allowlist trong sandbox | Redirect policy/egress test đạt |
| **DYN-T21** | Path traversal/file ID giả | Không truy cập files ngoài scope |
| **DYN-T22** | Valid report export | Positive business flow và audit đạt |
| **DYN-T23** | File upload quá size/độ sâu cho phép | Bounded reject, không DoS trong lab |
| **DYN-T24** | Synthetic secret canary trong error path | Không lộ vào sinks thuộc scope |
| **DYN-T25** | Scanner timeout/job aborted | FAILED/UNKNOWN, không zero findings |
| **DYN-T26** | Scanner tất cả protected routes 401 | Auth/coverage alert và retest |
| **DYN-T27** | API crawl thiếu route nhạy cảm | Coverage gap được báo |
| **DYN-T28** | Scanner rule disabled không được duyệt | Policy deviation detected |
| **DYN-T29** | Tool update đổi finding ID | Stable mapping/review, không auto-close |
| **DYN-T30** | WAF chặn request nhưng source weakness còn | MITIGATED TP, không FP |
| **DYN-T31** | Patch có ở repo nhưng runtime image cũ | Closure bị chặn |
| **DYN-T32** | Một cluster/region còn vulnerable image | PARTIALLY_FIXED / fleet gap |
| **DYN-T33** | Rollback về vulnerable version | Reopen/alert và risk review |
| **DYN-T34** | Negative test pass nhưng positive requests toàn 503 | Fail/inconclusive, không fixed |
| **DYN-T35** | Scanner report có raw token/cookie | Redaction/access policy kiểm soát |
| **DYN-T36** | Finding technical TP có accepted risk | Risk decision riêng, không ghi FP |
| **DYN-T37** | Reporter thiếu build/role/test IDs | Insufficient evidence |
| **DYN-T38** | Fix một endpoint nhưng sibling bypass còn | Partial remediation, retest |
| **DYN-T39** | Critical finding đóng thiếu independent review | Closure governance gate reject |
| **DYN-T40** | New service/API thay access policy | Reassessment trigger/ticket đúng |

### 29.1. Phân loại test theo đối tượng

- **Tool QA:** DYN-T01, T02, T25–T29, T35, T37.
- **Security behavior:** T03–T24, T34, T38.
- **Fix/deployment:** T31–T33.
- **Governance/risk:** T30, T36, T39, T40.

Một phép thử có thể thuộc nhiều nhóm. Không tuyên bố “40/40 pass” nếu nhiều tests không liên quan và chưa từng chạy. Để báo coverage, nêu rõ **selected tests, N/A reasons, actual outcomes và test population**.

### 29.2. Không chỉ kiểm tra response status

Khi finding liên quan data access/transaction, expected results phải gồm:
- HTTP/API response đúng security semantics.
- Không có sensitive data trong response/error.
- Không có unauthorized durable DB mutation.
- Không có job/outbox/file phát sinh trái quyền.
- Không có notification gửi sai người.
- Audit event phù hợp, không lộ secrets.
- Legitimate action vẫn hoạt động.
- Test environment/runtime versions và time window được biết.

### 29.3. Tại sao scanner test và business test tách nhau?

DAST có thể thấy response 403 nhưng không biết report worker vẫn chạy. API/domain test có thể biết job state nhưng không kiểm tra security headers/TLS. Cần kết hợp **scanner findings, behavioral tests và runtime evidence**; mỗi nguồn hỗ trợ một claim khác nhau.

## 30. Case study tổng hợp: xuất bảng điểm đa tenant

### 30.1. Kiến trúc và mục tiêu

Hệ thống học Java có:
- Browser giảng viên.
- API gateway với authentication.
- Learning API/Spring service.
- PostgreSQL lưu lớp/học viên/điểm.
- Queue với export jobs.
- Report worker đóng gói file.
- Private object storage.
- Download endpoint hoặc signed URL.
- Security audit và monitoring.

**Mục tiêu:** chỉ actor được phân công có quyền xuất điểm lớp tương ứng; luồng deny không tạo side effects; download vẫn phải được kiểm soát.

### 30.2. Timeline phát hiện giả định

| Thời điểm | Sự kiện | Evidence cần |
|---|---|---|
| T1 | DAST/API test thấy teacher A tạo job cho class B | Actor/context, request, job ID |
| T2 | Test owner xác minh A không có assignment B | Business policy, DB fixture |
| T3 | AppSec xác nhận BOLA ở export endpoint | Reproduction, trace, impacts |
| T4 | Nhóm API thêm per-class policy | Code/PR/change record |
| T5 | Staging API trả deny đúng | Negative/positive tests |
| T6 | Worker vẫn xử lý replay job B | Queue/storage evidence |
| T7 | Worker-side policy và job signature được sửa | New build/config/digest |
| T8 | Re-scan + end-to-end tests pass theo scope | Test result, scanner metadata |
| T9 | Rollout mọi API/worker images | Actual runtime digests |
| T10 | Reviewer đánh giá evidence và residual gaps | Assessment and decision |

Thời điểm và dữ liệu là **giả định**; không khẳng định một hệ thống cụ thể đã bị khai thác.

### 30.3. Hai finding hay một finding?

Có thể ghi một parent **Cross-tenant grade export** với affected paths API và worker, hoặc tách findings theo technical root cause. Quyết định tùy tracker/policy, nhưng phải giữ:
- API role-only check.
- Worker trust of unverified job/authority.
- Storage download authorization.
- Bằng chứng/test riêng.
- Owners và remediation riêng.
- Claim không mở rộng quá đã kiểm chứng.

Nếu API đã fix nhưng worker chưa, overall finding có thể là **PARTIALLY_FIXED**; không đóng toàn bộ vì HTTP path sạch.

### 30.4. Negative test plan

| Actor/action | Expected API | Expected downstream |
|---|---|---|
| Teacher A export unassigned class B | Deny | No job, file, email |
| Teacher A export class A | Allow/Accepted | Valid scoped job, private file |
| Tenant A actor tải file tenant B | Deny | No data disclosure |
| Forged client tenant header | No authority change | Worker ignores client-supplied scope |
| Unauthorized queue producer sends fake job | Reject per service policy | No worker data access |
| Permission revoked before execution | Defined outcome per approved delegation model | No behavior outside agreed policy |
| Replay same valid job message | Idempotent result | No duplicate unauthorized side effects |
| Worker image old vs new | Detect wrong release | Closure blocked if affected image remains |

### 30.5. Incident/exposure assessment song song

Nếu finding đã dẫn tới lộ dữ liệu thật, root-cause remediation và retest **không tự hoàn thành**:
- Investigate previous unauthorized exports.
- Preserve audit logs/job/file access evidence.
- Identify affected users/tenants and time windows.
- Contain/revoke leaked signed URLs khi cần.
- Privacy/Legal review theo nghĩa vụ áp dụng.
- Mitigate vendor notification/retrieval consequences.
- Document residual uncertainty.

Không lưu full bảng điểm trong evidence hoặc issue tracker chỉ để chứng minh finding.

### 30.6. Kết luận assurance mẫu

> **Đã xác minh trong scope:** các API, queue worker và download paths được liệt kê ở release image digests đã kiểm tra không còn tái hiện cross-tenant export với synthetic actor–resource fixtures; denied requests không tạo unauthorized downstream side effects trong observation window; positive authorized export flow vẫn hoạt động.  
> **Giới hạn:** legacy batch export và các vendor-managed flows chưa có evidence đầy đủ, được ghi thành gaps riêng.  
> **Hành động:** hoàn tất kiểm thử các paths còn lại, duy trì runtime digest reconciliation, theo dõi role/policy drift và mở lại finding khi có regression.

Đây là **mẫu cách viết kết luận**, không phải evidence về production.

## 31. Case study 2: scanner báo SQL injection nhưng tool bị nhiễu

### 31.1. Quan sát

DAST cho rằng tham số query gây SQLi vì request đôi khi trả HTTP 500 và timing chênh lệch. Developer nói “không có SQLi vì ứng dụng dùng ORM”. AppSec chưa có code path và DB logs đầy đủ.

### 31.2. Những câu hỏi quan trọng

- Endpoint thực sự dùng ORM query parameterization hay raw native query?
- Input có tham gia SQL identifiers/sort fragments?
- HTTP 500 đến từ input parser, connection pool, WAF hay DB?
- Network load có tạo chênh timing?
- Scanner có đúng actor/target, test data và version?
- Có response hay behavior khác chứng minh injection không?
- DB permissions và data classification?
- Có sibling route dùng raw query builder?
- Có thể tái hiện an toàn với synthetic data trong lab?

### 31.3. Hành động hợp lý

1. Phân loại **NEEDS_VALIDATION** cho đến khi evidence đủ.
2. Thu request/response và error correlation đã redact.
3. Review source/ORM/native query construction.
4. Run safe integration tests kiểm tra input được bind, không đổi query structure.
5. Test generic scanner theo scope đã duyệt nếu cần.
6. Phân biệt tool FP với một error-handling issue thật.
7. Nếu code raw concatenation có thật, remediation + retest.
8. Nếu query parameterized đúng và heuristic bị nhiễu, FP có rationale/context.
9. Đánh giá BOLA/tenant scoping riêng; SQLi FP không chứng minh cả endpoint an toàn.

### 31.4. Tránh hai cực đoan

- **Auto-FP:** vì scanner thiếu precision nên bác bỏ trước khi kiểm tra.
- **Auto-TP:** vì scanner thấy 500 nên cho rằng attacker đọc được database.

Security assurance yêu cầu evidence đủ để đưa kết luận tương xứng với claim và risk.

## 32. Case study 3: finding đã “sửa” nhưng production chưa đổi

### 32.1. Tình huống

Scanner ở staging xác nhận object storage đã private, nhưng production còn object policy cho public read ở một bucket/region phụ. IaC trên main đã cập nhật; runtime resource tồn tại do manual override.

### 32.2. Triage và closure

- **Design/code evidence:** updated IaC.
- **Implementation test:** staging policy và negative access test pass.
- **Operating evidence:** production effective IAM/bucket policy còn public exposure ở một target.
- **Technical status:** PARTIALLY_FIXED hoặc STILL_PRESENT theo scope, không VERIFIED_FIXED.
- **Actions:** sửa drift/effective policy, rà alternate account/region, verify anonymous and unauthorized access deny, log change/incident impact khi cần.
- **Residual risk:** xử lý theo data sensitivity và thời gian exposure.

Một dashboard CI “green” không thay effective cloud state.

## 33. Case study 4: secret đã xóa khỏi code nhưng còn hiệu lực

### 33.1. Tình huống

Dynamic test/error report phát hiện bearer token trong response/log. Developer bỏ dòng debug, DAST sau sửa không còn thấy token. Nhưng credential cũ vẫn valid và từng được log nhiều ngày.

### 33.2. Việc phải kiểm chứng

- Token/credential đã revoke/rotate theo policy.
- Mọi affected services dùng secret mới an toàn.
- Raw logging bị bỏ ở source, gateway và clients.
- Synthetic canary tests không thấy leak trong sinks thuộc scope.
- Logs/artifacts/history/caches được xem theo retention/incident policy.
- Quyền đọc log và khả năng lạm dụng token được đánh giá.
- Incident impact/notification obligations được xem khi áp dụng.
- Negative/positive tests không để application mất chức năng.
- Closure và exposure uncertainty được báo riêng.

**Không còn thấy token ở response mới chưa đủ chứng minh credential cũ không gây rủi ro.**

## 34. Findings remediation và xử lý sai lệch

### 34.1. Phân loại kết quả kiểm chứng

| Observation sau fix | Technical state | Next action |
|---|---|---|
| Original weakness tái hiện | STILL_PRESENT | Reopen root-cause fix |
| API fix nhưng worker bypass | PARTIALLY_FIXED | Expand scope, fix worker |
| Scanner mất authentication | INSUFFICIENT_EVIDENCE | Repair credentials, retest |
| Tool error/timeout | INSUFFICIENT_EVIDENCE | Fix pipeline, rerun |
| New build pass nhưng prod old digest | DEPLOYMENT_GAP/PARTIAL | Rollout/reconcile |
| WAF blocks nhưng source vulnerable | MITIGATED | Risk/controls review, plan fix |
| Finding hypothesis bác bỏ bằng evidence | FALSE_POSITIVE | Rationale, review/trigger |
| Security requirement không áp dụng trong stated scope | NOT_APPLICABLE | Document scope |
| Root cause fixed, tests/deploy verified | VERIFIED_FIXED | Independent closure decision |
| Vi phạm có thật, risk được duyệt giữ lại | RISK_ACCEPTED | Deadline, compensating controls, monitoring |
| Lỗ hổng tái xuất sau release | REOPENED | Incident/finding lifecycle |

### 34.2. Root-cause remediation hơn “fix scanner”

Một tool báo XSS ở HTML text; developer đổi response để không có payload marker, scanner không báo nữa. Nhưng nếu UI vẫn dùng unsafe innerHTML ở route khác, underlying XSS risk chưa được xử lý. Bản sửa phải giải quyết **unsafe sink/encoding** và được kiểm chứng bởi context-specific tests, không chỉ làm signature không match.

### 34.3. Finding closure checklist riêng cho reviewer

Reviewer nên xác nhận:
1. Technical verdict và affected population có căn cứ.
2. Remediation/mitigation model đúng security requirement.
3. Fix code/config/build identity hiện diện.
4. Re-scan targeted và current scan hợp lệ.
5. Positive/negative/side-effect tests phù hợp risk.
6. Không có blocker/unknown bị tính Pass.
7. Limitations/exceptions có owner.
8. Business/incident impact đã được xử lý hoặc workstream riêng.
9. Evidence bảo vệ và truy xuất được.
10. Reopen/monitoring triggers đã ghi.

### 34.4. Closure không phải xóa rủi ro lịch sử

Đã khắc phục lỗ hổng hiện tại không chứng minh **không ai từng khai thác trước đó**. Một vụ việc có dữ liệu bị lộ cần incident/privacy processes và exposure investigation riêng. Giữ history của findings theo retention policy để phục vụ audit/incident và học cách ngăn recurrence.

## 35. Continuous dynamic testing và finding monitoring

### 35.1. Vòng lặp assurance

~~~mermaid
flowchart TD
    R["Threat / security requirement"] --> T["Dynamic test plan"]
    T --> S["Authorized scan + behavioral tests"]
    S --> F["Validated findings + evidence"]
    F --> M["Risk priority / remediation"]
    M --> V["Retest + deployed proof"]
    V --> C["Closure review"]
    C --> O["Monitor scanner health + controls"]
    O --> H{"System, threat, config changes?"}
    H -->|"Có"| R
    H -->|"Không"| O
~~~

### 35.2. Trigger tái đánh giá

- Thêm API endpoint, GraphQL/gRPC operation hoặc admin route.
- Identity provider/token/session/role/tenant model thay đổi.
- Gateway/WAF/CORS/CSRF/auth policy thay.
- Cache key, queue, worker hoặc file download path đổi.
- Dependency/framework/template/serializer upgrade.
- Database permissions/tenancy/storage policy thay.
- Multi-region deployment/rollout/rollback.
- New data classification/sensitivity hoặc business workflow.
- Vulnerability advisory hoặc penetration testing finding mới.
- Security incident, detection signal hoặc bug bounty report.
- Scanner tool/ruleset/credentials/API schema thay.
- Test scope/discovered assets thay, unknown components tăng.
- Risk acceptance đến hạn, exception expired, SLA quá hạn.

### 35.3. Vai trò của automation

Automation có thể:
- Mở finding từ scanner report.
- Deduplicate bằng stable fingerprints.
- Gắn service owners từ asset registry.
- Route tickets theo severity.
- Chạy scan/retest khi release/change.
- Check missing evidence/expired exceptions.
- Verify image/config drift và reopen.
- Cảnh báo scanner auth/crawl failures.
- Tạo dashboard coverage và SLA.

Nhưng **automation không tự tạo hiểu biết về business authorization**. Nó cần policy definitions và test fixtures đúng; với high-impact findings vẫn phải có review và risk decision theo thẩm quyền.

### 35.4. Lịch chạy không là một bằng chứng đầy đủ

Một scanner chạy mỗi ngày nhưng chỉ crawl landing page không có giá trị assurance cao. Đo **target population, authenticated route coverage, rule health, actual tests, evidence freshness và fix deployment** chứ không chỉ số lượng scan jobs.

## 36. Metrics: đo hiệu quả xử lý finding một cách trung thực

### 36.1. Những số đo hữu ích

| Metric | Mục đích | Điều cần cảnh giác |
|---|---|---|
| **Valid scan coverage** | % targets/routes trong population có scan hợp lệ | Scanner chạy không đồng nghĩa route được test |
| **Authenticated route coverage** | Số protected operations được truy cập với đúng role | HTTP 200 login page không đủ |
| **Time to triage** | Từ finding đến technical verdict có evidence | False positive có thể cần nghiên cứu lâu hơn |
| **Confirmed high-risk open findings** | Remaining security exposure | Số lượng không đo được blast radius |
| **Time to contain** | Từ phát hiện đến giảm tác động khẩn | Contained không là fixed |
| **Time to fix deployed** | Bản sửa chạy trên affected assets | Repo merged không đủ |
| **Time to verified closure** | Fix deployed đến retest/reviewer decision | Closure nhanh không đồng nghĩa đúng |
| **% confirmed findings có targeted retest** | Độ phủ behavior verification | Phải có positive/negative/side-effect testing |
| **% verified closures có runtime digest proof** | Traceability build→deploy | Một digest chưa đại diện toàn fleet |
| **% findings PARTIALLY_FIXED** | Scope chưa được xử lý | Không gộp vào fixed |
| **% INSUFFICIENT_EVIDENCE** | Các unknowns/evidence debt | Cần định nghĩa status nhất quán |
| **Reopened findings** | Regression/rollback/drift | Tăng có thể do detection tốt hơn |
| **Scan tool error rate** | Reliability của nguồn evidence | Không đo error thì “0” không đáng tin |
| **High-risk finding SLA breaches** | Khả năng phản ứng theo policy | Exception có owner khác fixed |
| **Exceptions expired** | Governance debt | Risk accepted không làm lỗ hổng hết hạn |
| **Missing asset/owner rate** | Inventory/ownership quality | Mẫu số cần fleet/repo/asset source độc lập |
| **False-positive reversal rate** | Chất lượng triage | Gắn evidence cho lý do đổi verdict |
| **Remediation regression rate** | Tính bền vững của fix | Cần theo version và affected path |
| **% critical findings có evidence redacted/protected** | Privacy/evidence quality | Redaction không thay provenance |
| **Mean time to verify scanner outage** | Assurance availability | Không nhầm tool uptime với coverage |

### 36.2. Mẫu số phải được công bố

Ví dụ “95% findings đã xử lý” chưa đủ vì:
- Đếm candidate alerts hay confirmed vulnerabilities?
- Một lỗi trên 100 hosts tính 1 finding hay 100 affected instances?
- “Xử lý” nghĩa developer fixed, deployed, retested, accepted risk hay false positive?
- Số scanner failed/unknown là bao nhiêu?
- Có missing tenants/regions/services không?
- Có hết hạn SLA/exception không?
- Có reopened findings đã chuyển status nhưng dashboard vẫn tính closed không?

Các metric phải nói **time window, source, numerator, denominator, state definitions và exclusions**.

### 36.3. KPI không nên khuyến khích thao túng

Một mục tiêu “0 critical findings” có thể khiến team:
- Tắt rule.
- Giảm severity không có rationale.
- Chuyển TP thành FP.
- Đóng ticket trước retest.
- Không đưa scanner lỗi vào dashboard.
- Loại legacy systems khỏi inventory.

Nên phối hợp **risk-weighted open TP, time-to-verify, coverage quality, scanner health, retriage/reopen và exception governance**; review sample quality định kỳ.

## 37. RACI: phân quyền trách nhiệm và review

R = Responsible, A = Accountable, C = Consulted, I = Informed. Bảng sau là **mô hình tham khảo**, cần điều chỉnh theo tổ chức.

| Hoạt động | Developer/Tech Lead | AppSec/Assurance | QA/Tester | Platform/SRE | Product/Risk Owner |
|---|---|---|---|---|---|
| Tiếp nhận finding, kiểm tra source | C | A/R | R | C | I |
| Safe reproduction/scan authorization | C | A | R | R hỗ trợ | C |
| Technical verdict TP/FP/Unknown | C | A/R | R | C | C |
| Business impact/priority | C | R | C | C | A |
| Containment khi có incident | R | R | C | R | A theo thẩm quyền |
| Remediation root cause | A/R | C | R test | R config/deploy | C |
| Build/release artifact mapping | C | C | C | A/R | I |
| Positive/negative/async retest | R | A/R review | R | R verify runtime | C policy |
| Scan tooling/ruleset health | C | A policy | R | R operation | I |
| Closure evidence/approval | C | A/R | R | R | C |
| Risk acceptance/exception | C | C | C | C | A/R theo thẩm quyền |
| Continuous monitoring/reopen | R code | A/R security | R tests | R runtime | C |
| Privacy/legal incident handling | C | C | I | C | A khi được ủy quyền |

### 37.1. Reviewer độc lập

Đối với high-impact findings, reviewer cần:
- Không chỉ tin developer self-attestation.
- Hiểu business policy và attack preconditions.
- Có quyền kiểm tra evidence/target identity.
- Review negative/positive/side-effect tests.
- Xác nhận exclusions và uncertainty.
- Biết ai được quyền chấp nhận residual risk.

Nếu một người kiêm cả developer và security reviewer trong nhóm nhỏ, có thể dùng peer approval, recorded justification và periodic independent review theo risk để giảm xung đột lợi ích.

### 37.2. Vendor và third-party findings

Với hệ thống managed SaaS, bên mua có thể không có quyền chạy intrusive test. Cần:
- Supplier report/attestation đúng product/version/period.
- Incident/advisory notification process.
- Test API boundaries do mình kiểm soát.
- Các contractual access/audit rights khi áp dụng.
- Compensating controls ở tenant/customer side.
- Evidence gaps và residual risk owner.
- Không tự khẳng định đã fix một vendor issue chỉ dựa trên “support ticket closed”.

## 38. Những sai lầm thường gặp

**“Scanner báo finding nghĩa chắc chắn có lỗ hổng.”** Cần verify rule, target, reproduction, expected security policy và false-positive possibilities.

**“Scanner không báo sau sửa nghĩa đã fixed.”** Có thể scanner mất auth/coverage hoặc target khác.

**“HTTP 403 chứng minh không lộ dữ liệu.”** Queue/file/cache/notification vẫn có thể có side effects.

**“Chỉ cần test URL ban đầu.”** Root cause có thể có sibling paths/worker/direct APIs.

**“Không tái hiện một lần nghĩa false positive.”** Preconditions, role, timing, WAF, config và data state có thể khác.

**“Một unit test pass chứng minh production.”** Cần artifact, runtime config, deployment/fleet mapping.

**“WAF chặn attack nghĩa vulnerability đã bị loại.”** Đây có thể là mitigation với residual risk.

**“Đã merge PR là finding được khắc phục.”** Build, rollout, old images và worker chưa chắc đã cập nhật.

**“Scan được mỗi ngày nghĩa coverage tốt.”** Nếu chỉ crawl landing page, confidence thấp.

**“403/429/503 từ scanner đều giống deny đúng.”** Đây có thể là auth/crawl failure hoặc availability issue.

**“No alert nghĩa không có exploitation.”** Logging/detection/source coverage có thể thiếu.

**“Secret không còn trong log mới nên an toàn.”** Credential cũ còn valid có thể cần revoke/rotate và incident review.

**“Một high severity scanner rating đủ ra priority.”** Cần business impact, exposure, preconditions và controls.

**“Một finding duplicate có thể xóa path phụ.”** Duplicate vẫn phải giữ affected cases và verification.

**“False positive và not applicable là một.”** Technical rule invalid và outside-scope có thể cần chứng cứ khác.

**“Risk accepted là fixed.”** Acceptance là governance decision, không thay technical status.

**“Một region sạch nghĩa cả fleet sạch.”** Cần population và runtime image/config reconciliation.

**“Rollback không ảnh hưởng finding đã đóng.”** Old version có thể đưa vulnerability trở lại.

**“Không cần positive control nếu negative test deny.”** Service outage 503 có thể làm test trông sạch.

**“DAST trả 0 findings là zero vulnerabilities.”** DAST có blind spots về business logic, unsupported routes, native dependencies, runtime.

**“Raw logs càng đầy đủ càng tốt.”** Scans/reports có thể chứa PII/tokens; cần data minimization và confidentiality.

**“Risk acceptance xóa obligation.”** Nghĩa vụ pháp lý/hợp đồng không tự hết do exception nội bộ.

**“Chỉ làm remediation khi exploit chứng minh thành công.”** Một weakness có evidence đáng tin vẫn cần triage/risk response, không nên thử destructive exploit để xác nhận.

**“Không cần theo dõi sau closure.”** Changes và rollback có thể làm assumptions/controls lỗi thời.

## 39. Bài tập thực hành

### Bài tập A — Finding hay chỉ observation?

DAST gửi một ký tự đặc biệt vào endpoint và nhận HTTP 500; tool gắn SQL injection Critical. Thiết kế triage plan để phân biệt parser error, WAF, DB error và query syntax manipulation. Nêu điều kiện TP/FP/Unknown và dữ liệu không nên thu từ production.

### Bài tập B — Authorization đa tenant

Teacher A có thể gọi GET grades của tenant B. Viết actor/resource matrix, expected policy, safe reproduction, impacted assets, risk và closure tests. Bổ sung positive control cho teacher đúng lớp.

### Bài tập C — API 403 nhưng worker vẫn tạo file

Sau fix, API trả 403 với request sai quyền. Job record vẫn được tạo và worker xử lý sau 3 giây. Viết finding root cause, observation window, DB/queue/storage/audit assertions và tiêu chí đóng.

### Bài tập D — Scanner mất session

Scanner kết thúc “0 findings”, nhưng 80% protected routes trả 401 và OAuth token hết hạn giữa chừng. Phân loại kết quả scan, cách khôi phục profile, đo coverage và policy không được đánh dấu Pass.

### Bài tập E — XSS contexts

Một input hiển thị an toàn trong HTML text, nhưng raw-injected ở inline JavaScript tại trang admin. Hãy phân loại hai findings, thiết kế context-specific tests và remediation, tránh suppress cả template.

### Bài tập F — SQL injection qua ORDER BY

Ứng dụng đã dùng PreparedStatement cho WHERE nhưng nối query param sort vào SQL syntax. Đề xuất remediation bằng server-side allowlist, negative/positive tests và SAST/DAST evidence.

### Bài tập G — SSRF

Một API import chỉ cho chọn partner ID, nhưng đối tác có HTTP redirect. Xác định actor nào điều khiển destination và trust boundaries, thiết kế allowed/disallowed synthetic endpoints, egress monitoring, redirect policy tests. Không thử truy cập tài nguyên ngoài quyền.

### Bài tập H — Session và recovery

Người dùng logout, API vẫn nhận token cũ trong một số điều kiện. Xác định thiết kế token lifecycle được phê duyệt (self-contained vs revocation), test expected expiry/revoke, gateway/backend consistency và evidence.

### Bài tập I — Secret trong DAST report

Scanner lưu raw Authorization header vào report. Token cũ còn valid; report được chia sẻ rộng. Đề xuất containment, revoke/rotate, evidence handling, scanner configuration fix, retest và incident review.

### Bài tập J — Rollback

Release mới khắc phục BOLA nhưng vì outage, production rollback về vulnerable image. Viết reopen trigger, emergency risk approval/mitigation, monitoring, safe retest, deployment timeline và closure plan sau đó.

### Bài tập K — Cloud storage public access

DAST phát hiện object có thể anonymous read. IaC đã khóa public access nhưng một region vẫn public do drift. Xây technical status, affected population, effective policy tests, containment và evidence.

### Bài tập L — File upload và resource budget

Một scanner phát hiện server chậm khi xử lý file lớn. Thiết kế kiểm thử an toàn trong lab với size/depth/time bounds, monitoring CPU/memory, stop conditions và positive/negative tests. Không tạo DoS ngoài môi trường được cấp phép.

### Bài tập M — SLA và technical states

Có 20 confirmed findings: 8 Fixed Deployed, nhưng chỉ 5 retested; 4 mitigated bằng WAF, 3 risk accepted, 2 partially fixed và 3 scanner jobs failed. Các nhóm có thể giao nhau. Thiết kế dashboard không đếm trùng và không tự coi Fixed Deployed là Verified.

### Bài tập N — Evidence record

Viết YAML finding cho một API issue gồm tool/version, route, actor/role/tenant, original observation, risk, owner, fix, tests, deployed image digest, reviewer và limitations. Không dùng PII/tokens thật.

### Bài tập O — Claim–Argument–Evidence

Một DAST report pass trên staging nhưng production chưa có digest inventory; worker và download chưa được test. Viết claim tối đa có thể bảo vệ, argument/evidence, gaps và next actions, không khẳng định end-to-end fixed.

### Bài tập P — 90-day program

Thiết kế chương trình 90 ngày cho nhóm Java:
1. Chuẩn hóa taxonomy và finding schema.
2. Inventory critical endpoints/services/tenants và owners.
3. Xác định rules of engagement cho DAST/fuzzing.
4. Tạo synthetic actors/role matrices.
5. Tích hợp scan health/coverage dashboard.
6. Viết targeted regression tests cho BOLA/SQLi/XSS.
7. Đưa retest/build/deploy identity vào CI/release workflow.
8. Thiết lập reviewer/exception/risk acceptance.
9. Chuẩn hóa evidence handling và privacy.
10. Diễn tập rollback và finding reopen.
11. Đo false positives, unknowns, verification time và coverage.
12. Xuất báo cáo assurance với scope, limitations và action owners.

### Bài tập Q — Case study hỗn hợp

Một nền tảng có:
- 500 dynamic scanner alerts, 150 đã được xác nhận là TP.
- 130 alerts là FP với rationale có reviewer.
- 80 alerts chưa triage, còn lại duplicates/not applicable/khác.
- Một scan “0 vulnerabilities” thực tế chỉ truy cập login page.
- 30 findings được developer đóng vì PR merged, trong đó 10 regions vẫn chạy old image.
- 4 findings đã mitigated bằng WAF nhưng chưa sửa root cause.
- 6 exceptions hết hạn.
- Một legacy batch worker có quyền đọc mọi bảng điểm.

Hãy:
1. Xây taxonomy/status report và nêu những phép cộng không thể thực hiện từ dữ liệu thiếu.
2. Xác định top 5 risk scenarios cần xử lý.
3. Đưa ra target/identity/coverage checks trước khi tin scanner.
4. Viết remediation plan cho API và worker.
5. Thiết kế positive/negative/side-effect tests.
6. Xác định evidence cần để close từng loại finding.
7. Phân biệt mitigation, accepted risk, FP và verified fix.
8. Đề xuất metrics và next review triggers.

## 40. Checklist xử lý finding trong dynamic testing

Checklist là công cụ kiểm tra quy trình, **không phải tuyên bố rằng tất cả vulnerabilities đã được loại bỏ**.

- [ ] Test/scanner có authorization và rules of engagement rõ.
- [ ] Target asset, environment, endpoint, build/config/version và thời điểm được ghi.
- [ ] Tool/ruleset/scan policy/credentials/coverage được kiểm chứng.
- [ ] Scanner errors, partial runs, auth failures, timeouts được hiển thị riêng.
- [ ] Finding có unique ID, root-cause hypothesis, affected asset và owner.
- [ ] Original observation/expected/actual/reproduction có evidence đã redact.
- [ ] Business policy, trust boundary và actor/resource relationship rõ.
- [ ] Technical validity phân biệt TP/FP/Unknown/Not applicable/Duplicate.
- [ ] Không tự xem failure to exploit hoặc low risk là false positive.
- [ ] Severity/priority dựa vào impact, exposure, conditions, controls và uncertainty.
- [ ] High-risk findings được triage và escalate theo policy.
- [ ] Mitigation/containment khác permanent root-cause fix.
- [ ] Remediation acceptance criteria có thể kiểm thử, không chỉ “fix code”.
- [ ] Fix commit/build/artifact digest và actual deployed versions được đối chiếu.
- [ ] Affected paths/services/roles/tenants/regions/worker jobs được inventoried.
- [ ] Positive controls chứng minh legitimate business actions còn hoạt động.
- [ ] Negative controls cho cross-role/tenant/object, invalid inputs và bypass.
- [ ] Async DB/queue/cache/file/vendor side effects được xem khi liên quan.
- [ ] Temporal/replay/revocation/rollback được kiểm tra theo risk.
- [ ] DAST/SAST/SCA/cloud/config methods được chọn đúng loại weakness.
- [ ] Original reproduction được kiểm tra lại với preconditions phù hợp.
- [ ] New tool/ruleset và scanner drift được ghi, không auto-close finding ID biến mất.
- [ ] Scan “0 findings” chỉ được dùng khi tool healthy và coverage đạt.
- [ ] Re-scan report có run IDs, actual results, warnings và evidence references.
- [ ] Report/ticket không chứa raw session tokens/PII hoặc uncontrolled exports.
- [ ] Unverified legacy/vendor/region paths được ghi exclusions và owners.
- [ ] PARTIALLY_FIXED/MITIGATED/ACCEPTED không tự thành VERIFIED_FIXED.
- [ ] Reviewer phù hợp thẩm quyền và độc lập theo risk phê duyệt closure.
- [ ] Exceptions có scope, residual risk, compensating controls và expiry.
- [ ] Incident/privacy impacts từ vulnerability đã xảy ra được xử lý song song khi cần.
- [ ] Reopen triggers có rollback, code/config/role/threat changes.
- [ ] Scan health, source coverage, tool errors và SLA được monitor liên tục.
- [ ] Dashboard metrics có time window, population và state definitions.
- [ ] Claim–Argument–Evidence nêu rõ điều đã chứng minh và còn chưa biết.
- [ ] Không đưa một status “Closed” thành khẳng định hệ thống không có vulnerability.

## 41. Ghi nhớ

1. **Finding trong dynamic testing là một quan sát cần kiểm chứng** theo security requirement, context và evidence; không phải bản án scanner đưa ra.
2. Chuỗi xử lý là **intake → scan/target validation → technical triage → risk prioritization → ownership → remediation → retest → deployment verification → evidence review → monitoring**.
3. **True Positive, False Positive, Not Applicable, Duplicate và Insufficient Evidence** khác nhau; risk acceptance/mitigation cũng không phải technical fix.
4. **Tái hiện an toàn và có thẩm quyền** giúp xác minh đúng threat mà không làm tổn hại hệ thống, tài khoản hoặc dữ liệu thật.
5. **Authenticated DAST cần coverage**: biết actor/role, tenant, route, scan rules và trạng thái tool; “0 findings” khi scanner thất bại là không có cơ sở.
6. **Root-cause remediation** phải giải quyết các trust boundaries và sibling paths, không chỉ sửa một status code hoặc né payload của scanner.
7. Với BOLA/logic nghiệp vụ, **positive/negative tests và kiểm tra DB/queue/storage side effects** quan trọng hơn một HTTP 403 đơn lẻ.
8. **Fix commit → build/artifact digest → runtime deployed state → targeted retest** là chuỗi evidence để kết luận bản sửa đã thực sự hoạt động.
9. **Mitigated hoặc Risk Accepted** có thể giảm exposure nhưng không đồng nghĩa **Verified Fixed**; những trường hợp đó cần owner, controls và review period.
10. **Scanner failures, missing assets và incomplete evidence** phải báo Unknown/Unhealthy, không được tính Pass.
11. **Claim–Argument–Evidence** tạo kết luận có giới hạn về target, release, policy, thời gian, tests, risk và những điều chưa đánh giá.
12. Sau closure, **continuous assurance** cần monitoring, regression tests, scan coverage, deployment reconciliation, SLA, reassessment và khả năng mở lại khi assumptions thay đổi.










