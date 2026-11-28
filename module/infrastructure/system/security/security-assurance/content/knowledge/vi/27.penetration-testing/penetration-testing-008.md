# Báo cáo pentest

**Báo cáo pentest** (*penetration test report*) là tài liệu trình bày **mục tiêu, phạm vi, phương pháp, hoạt động kiểm thử, các phát hiện bảo mật đã được xác minh, bằng chứng, đánh giá rủi ro, giới hạn và hành động khắc phục** của một đợt kiểm thử xâm nhập được ủy quyền. Báo cáo tốt không chỉ là danh sách lỗ hổng, điểm CVSS hoặc ảnh chụp màn hình scanner: nó giúp các bên liên quan hiểu **đã kiểm tra điều gì, đã chứng minh điều gì, chưa kiểm tra được điều gì, rủi ro đối với mục tiêu nghiệp vụ là gì và ai cần làm gì tiếp theo**.

Trong nền tảng học trực tuyến Java, một nhóm pentest có thể phát hiện: giáo viên ở tenant A thay mã lớp trong yêu cầu API và xem được dữ liệu điểm của tenant B. Báo cáo cần mô tả bằng chứng an toàn cho **Broken Object Level Authorization (BOLA)**, các điều kiện để hành vi xảy ra, tác động tới dữ liệu học viên, phạm vi API/worker/storage đã kiểm tra, khả năng tồn tại các đường tương tự, root cause có cơ sở, hướng khắc phục, owner và cách kiểm thử lại. Nếu chỉ viết “IDOR – High – thêm kiểm tra quyền” thì developer, product owner và assessor vẫn không biết **những resource, actors, trạng thái và side effects nào** phải được bảo vệ.

Bài thuộc chương **Penetration testing** của module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu của module là *xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện; học tổ chức chương trình security assurance liên tục trong phát triển và vận hành*. Vì vậy báo cáo pentest được xem là **một mắt xích của security assurance**, kết nối yêu cầu bảo mật và threat model với phép kiểm thử, bằng chứng, remediation, retest, quyết định residual risk và theo dõi liên tục.

**Thông điệp cốt lõi:** Báo cáo pentest phải **có thể truy vết, chính xác trong phạm vi, hành động được, bảo vệ dữ liệu nhạy cảm và trung thực về mức độ bảo đảm**. Một đợt pentest “không phát hiện lỗi nghiêm trọng” không chứng minh hệ thống không có lỗ hổng, nhất là khi có assets bị loại khỏi scope, test bị chặn, credentials hết hạn hoặc thời gian kiểm thử hạn chế.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích mục đích của pentest report trong quy trình security assurance, khác với scanner output, vulnerability inventory và audit certificate.
2. Xác định các nhóm độc giả: ban lãnh đạo, product/risk owner, development, platform/SRE, AppSec, SOC, auditor và supplier.
3. Thu thập dữ liệu đầu vào đúng: ủy quyền, Rules of Engagement (RoE), target inventory, kiến trúc, credentials, test window, test logs, findings và evidence.
4. Viết **executive summary** nêu rõ risk/business impact và ưu tiên, không dùng thuật ngữ quá mức hoặc tuyên bố “an toàn tuyệt đối”.
5. Mô tả **scope/constraints/exclusions/test coverage** để tránh mở rộng kết luận ngoài những gì đã kiểm tra.
6. Ghi phương pháp theo loại kiểm thử và assurance objective, nêu version/phương pháp tham chiếu khi áp dụng, nhưng không biến framework name thành chứng nhận.
7. Phân biệt **observation, candidate finding, confirmed vulnerability, false positive, duplicate, not applicable và insufficient evidence**.
8. Viết một technical finding có ID, affected assets, prerequisites, expected/actual, safe reproduction, evidence, root cause, risk, remediation và retest criteria.
9. Áp dụng severity/priority dựa trên exploit preconditions, likelihood, impact, business context, confidence và existing controls.
10. Hiểu vai trò CVSS/CWE/CVE/OWASP mappings mà không coi score tự động quyết định business risk.
11. Dùng screenshots, redacted requests/responses, logs và artifact references làm bằng chứng có **integrity, provenance, privacy và traceability**.
12. Viết báo cáo cho các case Java/Spring/API, cross-tenant BOLA, async worker, secrets, TLS/cloud configuration và dependency findings.
13. Phân biệt **root-cause remediation, compensating controls, mitigation và risk acceptance** trong phần đề xuất.
14. Thiết kế retest criteria: fix hiện diện ở đúng release/deployed digest, original behavior không còn, positive/negative/side-effect tests đạt.
15. Phân tích các giới hạn: unknown reachability, test data, authentication, asset discovery, scanner health, third-party, multi-region và thời điểm kiểm tra.
16. Xây Claim–Argument–Evidence (CAE), traceability matrix, report QA, review/approval, controlled distribution và phiên bản.
17. Đề xuất action plan, owners, target dates theo policy, exceptions, escalation và monitoring để findings không mất sau khi gửi PDF.
18. Thiết kế dashboard/metrics có mẫu số và trạng thái chính xác, không dùng “zero findings” làm thước đo an toàn tuyệt đối.
19. Tổ chức bài tập viết executive report, technical appendix, evidence record và retest addendum.

## 2. Báo cáo pentest là gì và không phải là gì?

### 2.1. Định nghĩa theo vòng đời assurance

Một báo cáo pentest là **sản phẩm của một engagement kiểm thử có ủy quyền và phạm vi xác định**, bao gồm:
- Mục tiêu/risk scenarios mà nhóm kiểm thử nhắm tới.
- Đối tượng kiểm thử, thời điểm, môi trường, cách truy cập và ranh giới.
- Phương pháp và các loại test đã thực hiện.
- Kết quả tích cực, negative evidence, findings và observations.
- Chứng cứ đủ để xem xét độc lập.
- Đánh giá tác động và độ chắc chắn.
- Kế hoạch xử lý có thể chuyển thành việc triển khai.
- Những giả định, constraints và residual uncertainty.
- Quy trình review, phân phối và kiểm thử lại.

### 2.2. Không tự tương đương những tài liệu khác

| Tài liệu/hoạt động | Mục tiêu điển hình | Giới hạn khi dùng thay pentest report |
|---|---|---|
| **DAST scanner output** | Ghi phát hiện từ tool ở các target đã crawl | Không tự xác minh business logic, impact, asset population |
| **SAST report** | Phân tích code/data flow | Chưa chứng minh exploit preconditions và deployed behavior |
| **SCA/SBOM report** | Inventory components, đối chiếu advisory | Không tự chứng minh một thư viện có exploitable path |
| **Vulnerability register** | Theo dõi findings/owners/trạng thái toàn kỳ | Có thể thiếu reproduction/methodology/scope của engagement |
| **Threat model** | Dự đoán rủi ro và attack paths trước/suốt SDLC | Không chứng minh controls đã được kiểm thử thành công |
| **Audit/compliance report** | Đánh giá một bộ tiêu chí/controls trong kỳ | Không mặc định có bài kiểm thử kỹ thuật kiểu pentest |
| **Red team report** | Mô tả kịch bản đối thủ, detection/response outcomes | Objectives/methods khác; không nhất thiết bao phủ mọi weakness |
| **Incident report** | Điều tra sự kiện đã xảy ra | Pentest giả lập không chứng minh đã có sự cố thật |
| **Retest report** | Kiểm chứng fix cho findings đã biết | Không tự thay một pentest toàn phạm vi mới |
| **Executive summary** | Truyền tải risk/action cho lãnh đạo | Không đủ để developer tái hiện và sửa lỗi |

### 2.3. Vì sao báo cáo đẹp không đồng nghĩa assurance mạnh?

Một báo cáo nhiều hình và bảng severity có thể yếu nếu:
- Không biết image/build nào được kiểm tra.
- Không nêu endpoints/roles/tenants đã cover.
- Chỉ liệt kê scanner alerts chưa triage.
- Không có original evidence hoặc test oracle.
- Không phân biệt high impact với high scanner severity.
- Đưa raw student data/tokens vào appendix.
- Không có owner, acceptance criteria hoặc retest plan.
- Loại unknown/unreachable targets khỏi mẫu số mà không nói.
- Dùng từ “secure” cho toàn hệ thống dù scope hẹp.

**Chất lượng kết luận phụ thuộc chất lượng evidence và định nghĩa phạm vi, không phụ thuộc độ dài hay thiết kế của báo cáo.**

## 3. Đối tượng đọc và câu hỏi cần trả lời

### 3.1. Báo cáo có nhiều lớp

| Độc giả | Câu hỏi chính | Nội dung cần |
|---|---|---|
| **Ban lãnh đạo/CISO** | Rủi ro lớn nhất, tác động và ưu tiên đầu tư? | Executive summary, top risks, roadmap, uncertainty |
| **Product/Business Owner** | Tính năng/dữ liệu/khách hàng nào ảnh hưởng? | Business scenarios, affected workflows, decision points |
| **Risk/Compliance Owner** | Control objectives nào có/không có evidence? | Scope, mapping, residual risk, exceptions, CAE |
| **Developer/Tech Lead** | Reproduce ở đâu và sửa root cause thế nào? | Technical finding details, code/config suggestions, tests |
| **Platform/SRE** | Image/config/cluster/secret nào cần thay? | Affected infrastructure, deployment proof, rollback risk |
| **AppSec/Assessor** | Kết quả đáng tin tới mức nào? | Methods, tools, coverage, evidence, limitations |
| **SOC/Incident Response** | Có dấu hiệu exploitation thật? Cần theo dõi gì? | Attack pattern, logging gaps, detection recommendations |
| **Auditor/External Reviewer** | Có kiểm tra độc lập, lineage và approval không? | Evidence references, method, peer review, statuses |
| **Supplier/Third party** | Vấn đề thuộc thành phần vendor nào và cần hành động? | Redacted product-specific details, safe disclosure |

### 3.2. Cấu trúc “hai tầng”

**Tầng điều hành:** ngắn, rõ, ít chi tiết kỹ thuật; diễn đạt rủi ro, hệ quả, quyết định, ưu tiên, giới hạn và chủ sở hữu.

**Tầng kỹ thuật:** đủ để tái hiện trong môi trường được phép, sửa code/config, lập test; có evidence IDs, assets, requests đã ẩn thông tin nhạy cảm, behavior, confidence và acceptance criteria.

Một báo cáo chỉ có executive summary khó dùng cho remediation; chỉ có log scanner 500 trang khó dùng cho risk governance.

### 3.3. Dùng ngôn ngữ xác suất và phạm vi đúng

Nên viết:
- “Trong 12 routes đã kiểm tra ở staging release R, hai đường cho phép actor ngoài quyền khởi tạo grade-export jobs.”
- “Các controls kiểm tra role tồn tại, nhưng không chứng minh được kiểm tra actor–resource relationship trên export workflow.”
- “Không phát hiện thêm biến thể trong các endpoint/roles thuộc test matrix được thực thi.”

Tránh:
- “Toàn bộ hệ thống có thể bị hack.”
- “Không có vulnerability nào khác.”
- “Đã bảo mật tuyệt đối.”
- “Không có CVE, nên an toàn.”
- “Server trả 403, nên đã khắc phục tất cả.”

## 4. Chu trình tạo báo cáo từ trước tới sau kiểm thử

~~~mermaid
flowchart TD
    A["Engagement charter + written authorization"] --> B["ROE, scope, critical assets, test objectives"]
    B --> C["Methodology + test case coverage matrix"]
    C --> D["Controlled testing + raw evidence"]
    D --> E["Triage + validate findings"]
    E --> F["Risk contextualization + root cause"]
    F --> G["Executive + technical draft"]
    G --> H["Peer QA / evidence and privacy review"]
    H --> I["Stakeholder factual review"]
    I --> J["Approved report + controlled distribution"]
    J --> K["Finding tracker + owners + deadlines"]
    K --> L["Remediation + retest addendum"]
    L --> M["Residual risk + continuous assurance"]
~~~

### 4.1. Đầu vào

- Written authorization và RoE phiên bản được phê duyệt.
- Contact/communications, emergency stop plan.
- Asset/service/deployment inventory.
- Security goals và prioritized threat scenarios.
- Role/tenant/data fixtures và test identities.
- Scan policy/test plan, tools và versions.
- Evidence collected in permitted time window.
- Original observations, verified results, false positives và gaps.
- Relevant architecture, data flows, risk owner/asset owner.

### 4.2. Đầu ra

- Báo cáo đã review/approved, có version và classification.
- Executive summary, scope/method/results.
- Detailed findings và evidence references.
- Risks/owners/prioritized remediation roadmap.
- Explicit exclusions/coverage/assurance limits.
- Machine-readable finding register nếu tổ chức dùng.
- Retest/verification plan và trạng thái findings.
- Changelog/audit trail, secure delivery record.
- Các open questions và follow-up owners.

### 4.3. Báo cáo là tài liệu theo thời điểm

Một pentest diễn ra tháng 11 không tự phản ánh trạng thái tháng 12 sau deploy/new API; một vulnerability đã fix có thể quay lại khi rollback. Vì vậy report nên có:
- Engagement period.
- System versions/target build digests.
- Report issue/revision date.
- Findings as of testing date.
- Retest date/status riêng.
- Historical status log, không sửa ngầm bản gốc.
- Reassessment trigger khi scope/threat đổi.

## 5. Pháp lý, ủy quyền và Rules of Engagement (RoE)

### 5.1. Chỉ mô tả những test được phép

Một report phải trích **thông tin đủ để chứng minh có phép và scope**, không nhất thiết sao chép nguyên hợp đồng/secret:
- Authorizing organization và authority (theo metadata được phép chia sẻ).
- Testing provider/team và contact.
- In-scope IP/hosts/apps/repos/cloud tenants.
- Out-of-scope systems/services/vendor APIs.
- Testing window, rate/throughput constraints.
- Allowed/prohibited techniques.
- Authentication/user roles/test accounts.
- Restrictions: destructive data change, DoS, social engineering, data exfiltration.
- Emergency pause/escalation and responsible parties.
- Data handling/retention/report distribution obligations.
- Change-control/third-party approvals khi áp dụng.

### 5.2. Safe evidence thay vì chứng minh bằng thiệt hại thật

Trong report:
- Dùng synthetic profiles, class/grade fixtures và test buckets.
- Chứng minh lộ một record giả thay vì xuất hàng nghìn hồ sơ.
- Dùng screenshots đã redact, không lưu raw cookies/tokens.
- Mô tả PoC tối thiểu, có thể tái hiện trong lab được phép.
- Không yêu cầu scan làm quá tải production.
- Không thử bypass vendor services ngoài authorization.
- Dừng và escalation nếu phát hiện dấu hiệu incident thực.
- Ghi hủy/cleanup test data và trạng thái môi trường.

### 5.3. Pentest không mặc nhiên gồm mọi hoạt động “hacker”

Ví dụ kiểm thử có thể **không** được phép:
- Phishing nhân viên.
- Truy cập vật lý.
- Password spraying diện rộng.
- DoS/resource exhaustion stress.
- Brute force hoặc khai thác phá hoại.
- Rút dữ liệu thật.
- Nhảy sang third-party network.
- Khai thác production database.
- Thử credential ngoài danh sách.
- Thao tác không thuộc thỏa thuận.

Báo cáo phải nêu **không được kiểm tra** chứ không nói không có rủi ro ở những hạng mục này.

## 6. Scope và asset population

### 6.1. Bốn câu hỏi

1. **What:** những ứng dụng, URLs, APIs, services, clusters, environments, versions, accounts nào?
2. **Who:** actor/role/tenant/test identity nào, business privileges nào?
3. **When:** kiểm thử trong cửa sổ nào, sau/before releases hoặc feature flags nào?
4. **How deep:** scanning only, authenticated flow, business logic, exploit validation, limited internal lateral movement hay không?

Một scope “pentest Learning Platform” quá mơ hồ để bảo vệ kết luận.

### 6.2. Scope matrix minh họa

| Đối tượng | Trong scope? | Kiểm thử được phép | Giới hạn |
|---|---|---|---|
| Learning API staging R | Có | Auth/API business logic, non-destructive testing | Synthetic students/teachers |
| Report worker staging R | Có | Queue/job ownership, output file scope | Bounded job volume |
| Grade download service | Có | Cross-tenant access, signed URL policy | Không tải dữ liệu thật |
| Admin portal staging | Có một phần | Authorization và session | Chỉ approved admin account |
| Production public gateway | Có giới hạn | Non-invasive config/headers/TLS checks | Không fuzz/DoS ngoài ROE |
| Production DB | Không | Không truy cập/scan trực tiếp | Findings qua sanctioned test/lab |
| Third-party email service | Không | Review boundary/config, không pentest vendor | Supplier evidence riêng |
| Legacy report export | Chưa có owner | Không kiểm thử khi chưa authorize | Explicit coverage gap |
| Mobile app release | Không thuộc engagement | Không đánh giá | Không khẳng định được bảo vệ |
| DR/standby region | Chỉ nếu được liệt kê | Theo authorization | Nếu không, note untested |

Các giá trị là **minh họa**, không phải inventory thực.

### 6.3. Tránh nhầm “scope hẹp” và “risk thấp”

Legacy export có thể ngoài scope vì không đủ quyền, nhưng vẫn gây high-impact risk. Báo cáo nên phân biệt:
- **Out of scope by contract:** engagement không được kiểm tra.
- **Not tested despite in scope:** constraint/tool failure.
- **Not applicable:** có bằng chứng requirement không áp dụng.
- **Not discovered:** unknown asset inventory gap.
- **Decommissioned:** có evidence asset không còn hiện diện.
- **Vendor managed:** shared responsibility/third-party limitation.

Không âm thầm loại “unreachable” assets khỏi denominator rồi kết luận 100% coverage.

## 7. Phương pháp pentest và mức độ bao phủ

### 7.1. Methodology không phải certification

Báo cáo có thể tham khảo **OWASP Web Security Testing Guide (WSTG)**, **OWASP API Security Top 10**, **OWASP ASVS**, **NIST SP 800-115**, hoặc các phương pháp pentest có cấu trúc khác để sắp xếp mục tiêu và test cases. Các tài liệu có phạm vi/chức năng khác nhau, cần ghi **phiên bản/những phần được áp dụng** khi công bố mapping. Chỉ nhắc tên OWASP/NIST không chứng minh đã chạy đủ tests hay tuân toàn bộ framework.

### 7.2. Ví dụ nhóm test

| Nhóm | Mục tiêu | Evidence |
|---|---|---|
| Asset discovery trong scope | Xác định reachable endpoints/components | Inventory, API routes, constraints |
| Authentication/session | Xác thực, lifecycle, recovery, cookie/token | Test identities, sessions, negative tests |
| Authorization/tenant isolation | BOLA/BFLA/field-level/workflow permissions | Actor–resource matrix và side effects |
| Input/output handling | SQLi/XSS/template/path/serialization | Safe reproductions và code/context review |
| Server-side integrations | SSRF, redirects, third-party trust | Controlled test endpoints, egress observations |
| Business logic | Rate/limit, step order, approvals, integrity | Workflow assertions |
| File upload/download | Content bounds, private storage, object access | File IDs/storage permissions |
| Crypto/TLS/session transport | Endpoint configuration và trust | TLS config report, approved client tests |
| Cloud/container/API gateway | Effective access policies | IAM/config/runtime scope |
| Secrets and logging | Leakage và audit correctness | Synthetic canaries, redacted logs |
| Availability/resilience | Bounded resource behavior theo ROE | Sandbox/load ceiling evidence |
| Detection/response | Security events/alerts nếu nằm trong scope | Synthetic event correlation |
| Regression | Changes don't reintroduce known weakness | Existing/updated test results |

### 7.3. Độ sâu thực thi

Các trạng thái nên phân biệt:
- **Planned:** có trong test plan.
- **Executed:** test thật được chạy với preconditions.
- **Passed:** expected security behavior trong scope đạt.
- **Failed:** phát hiện violation.
- **Blocked:** thiếu credentials/dependencies.
- **Inconclusive:** kết quả không đủ.
- **Not run:** chưa thực hiện.
- **Not applicable:** có rationale ngoài phạm vi.
- **Restricted:** ROE không cho thử loại nhất định.

Không đếm **Planned/Not Run/Blocked/Inconclusive** thành Passed.

## 8. Kiểm kê test coverage có thể đo

### 8.1. Mục đích

Report cần cho thấy **nhóm đã kiểm tra cái gì** chứ không chỉ những nơi tìm thấy lỗi. Ví dụ:
- 12/15 approved API operations được test có xác thực.
- 3 operations bị blocked do session expiry.
- 2/4 roles có cross-tenant negative tests.
- 1/2 export channels đã kiểm tra downstream file permissions.
- Production DR region excluded by ROE.

Đây là **giả định minh họa**, không được trình bày thành kết quả thật.

### 8.2. Dimensions của coverage

| Dimension | Câu hỏi |
|---|---|
| Assets | Bao nhiêu services/hosts/regions trong target population? |
| Endpoints | Bao nhiêu HTTP methods/routes hoặc RPC operations thực sự tested? |
| Actors | Test accounts có đại diện các roles và permission states? |
| Tenants/resources | Có cặp owner/non-owner/cross-tenant? |
| Workflows | Có API → queue → worker → storage/download? |
| Security requirements | Test nào chứng minh control nào? |
| Techniques | Automated scan, manual logic tests, config checks? |
| Time | Test trước/sau change nào, credential/feature flags nào? |
| Tool health | Có authentication failures, 429, WAF redirects, tool crashes? |
| Data | Synthetic fixtures có hợp lệ và an toàn? |
| Deployment | Image/build/config identity nào đã test? |
| Exceptions | Còn vùng chưa test hoặc blocked không? |

### 8.3. Coverage không chỉ là phần trăm

Một “95% routes coverage” không chứng minh kiểm thử quyền tốt nếu 95% routes đều public health endpoints. **Risk-weighted coverage** cần tập trung các paths nhạy cảm như điểm, bài nộp, role changes, payments và exports, đồng thời công bố mẫu số và excluded assets.

## 9. Report structure đề xuất

### 9.1. Trang đầu/metadata

Tối thiểu:
- Tên hệ thống/engagement và report ID.
- Tổ chức giao việc/nhóm thực hiện theo phân quyền chia sẻ.
- Mức phân loại (confidentiality/classification).
- Version, ngày phát hành, testing period.
- Target environment/release.
- Approver/reviewer và distribution list.
- Contact for high-risk escalation.
- Document change history.

### 9.2. Mục lục chức năng

1. Executive summary.
2. Business context và objectives.
3. Scope, exclusions và assumptions.
4. Written authorization/RoE reference.
5. Methodology, tools và validation methods.
6. Coverage matrix.
7. High-level risk/findings summary.
8. Detailed findings and evidence.
9. Cross-cutting root causes và risk themes.
10. Prioritized remediation roadmap.
11. Remediation ownership và timelines.
12. Retest/verification plan.
13. Residual risk, limitations và unknowns.
14. Claim–Argument–Evidence / control traceability (khi thuộc assurance program).
15. Appendices: sanitized evidence, technical configuration, references.
16. Report version/approval/secure distribution.

### 9.3. Tổng quan và chi tiết phải nhất quán

Nếu executive summary nêu “2 High findings”, technical appendix phải có đúng finding IDs và severity metadata; nếu một finding bị hạ priority sau factual review, sửa mọi chỗ phản ánh con số đó, giữ audit trail thay đổi. Không copy scanner chart cũ làm số liệu mâu thuẫn với danh sách đã triage.

## 10. Executive summary: viết cho quyết định, không viết như scanner log

### 10.1. Mục tiêu của phần tóm tắt

Executive summary trả lời **năm câu hỏi**:
1. Engagement đánh giá những gì, ở môi trường/kỳ nào?
2. Những rủi ro đáng kể nhất đối với mục tiêu nghiệp vụ là gì?
3. Mức tin cậy và giới hạn của bằng chứng là gì?
4. Cần làm việc gì trước, bởi ai và theo thứ tự nào?
5. Có quyết định nào cần lãnh đạo/risk owner phê duyệt?

Phần này thường viết **sau** khi đã triage và kiểm tra technical findings. Không nên bắt đầu bằng bảng 50 CVE rồi đòi executive hiểu ngay.

### 10.2. Mẫu đoạn executive summary

> **Phạm vi:** Đợt đánh giá minh họa kiểm thử Learning API và chức năng xuất điểm trên staging release R trong kỳ T, dùng synthetic teacher/learner accounts thuộc hai tenants và các kiểm thử API/worker được cho phép.
>
> **Phát hiện nổi bật:** Một weakness trong object-level authorization cho phép teacher được xác thực khởi tạo export dữ liệu điểm của lớp không thuộc quyền, ảnh hưởng confidentiality/cross-tenant isolation. Một số controls ghi log và phân quyền tại gateway đã hoạt động trong test cases được thực hiện, nhưng không thay thế authorization tại service và worker.
>
> **Ưu tiên:** Khắc phục per-class/tenant authorization tại API và worker, kiểm tra job/storage side effects, triển khai fixed artifacts và retest trước khi đóng finding. Tạm giới hạn export/monitoring tùy quyết định incident/risk owner trong lúc chờ fix.
>
> **Giới hạn:** Một legacy batch path và production region không nằm trong phạm vi được phép; báo cáo không khẳng định chúng an toàn. Kết quả phản ánh version/time được ghi.
>
> **Yêu cầu quyết định:** Product và Platform owners thống nhất remediation plan và kiểm chứng triển khai; Risk Owner xử lý residual exposure và ngoại lệ nếu có.

Mẫu là **dữ liệu hư cấu**, không phải báo cáo đã thực hiện. Khi dùng thật phải thay R/T, thêm finding IDs, severity, owners, actual evidence và time bounds chính xác.

### 10.3. Nên và không nên

| Nên | Tránh |
|---|---|
| “Rủi ro lộ điểm học viên giữa tenants” | “CWE-639, CVSS 9.x” không có diễn giải |
| “API export cần kiểm tra object-level authorization” | “Backend có vấn đề nghiêm trọng” |
| “Các kết luận giới hạn trong 14 operations đã thử” | “Toàn bộ hệ thống dễ bị tấn công” |
| “Ba findings cần remediation, một cần evidence thêm” | “Tất cả đã được giải quyết” khi mới merge PR |
| “Compensating control tạm cần owner và expiry” | “Bật WAF, xem như fixed” |
| “Không kiểm thử destructive load theo RoE” | “Đã chứng minh hệ thống chịu mọi DoS” |

### 10.4. Một bản tóm tắt có thể không có high severity

Ngay cả khi không tìm thấy confirmed High/Critical findings, vẫn phải:
- Nêu phạm vi và depth.
- Report Medium/Low và improvement opportunities.
- Ghi tool health và untested paths.
- Phân biệt **không phát hiện** với **không tồn tại**.
- Nêu quyết định cần thực hiện về gaps/unknowns.
- Đánh dấu thời điểm kết quả có giá trị.

## 11. High-level risk snapshot và finding summary

### 11.1. Tổng hợp có ngữ nghĩa

Một bảng summary nên có:
- Unique finding ID.
- Short title/weakness class.
- Asset, service và environment.
- Technical status: Confirmed, Under Investigation, False Positive, etc.
- Severity/priority với rationale ngắn.
- Affected workflow/data.
- Root-cause category.
- Owner.
- Recommended action và deadline theo risk policy.
- Retest/closure state nếu báo cáo cập nhật.
- Link tới technical details.

### 11.2. Ví dụ bảng tổng hợp

| ID | Finding | Assets | Severity mẫu | Technical state | Owner | Action |
|---|---|---|---|---|---|---|
| PT-001 | BOLA khi export điểm | Learning API, report worker | High | Confirmed | Backend + Worker | Relation-aware policy và retest |
| PT-002 | Export link có thời gian sử dụng quá dài so với policy | Download service | Medium | Confirmed | Platform + Backend | TTL/revocation design |
| PT-003 | Thư viện parser có advisory | Report image | Under Investigation | Evidence gap | Build owner | Exact package/VEX impact analysis |
| PT-004 | DAST nghi SQLi ở filter | Grade search | Unrated pending | Needs validation | Backend + AppSec | Confirm query semantics |
| PT-005 | Header heuristic sai context | Login redirect | Low (scanner) | False Positive | AppSec | Rationale, no code fix |

Đây là ví dụ minh họa; **không tự gán numeric CVSS, thực tế đã khai thác, hoặc kết quả production**. Một label “High” chỉ là mẫu minh họa của risk rubric nội bộ.

### 11.3. Đếm findings thế nào để không lừa người đọc?

Một finding có thể ảnh hưởng 20 endpoints; một endpoint có thể chứa ba weaknesses. Cần nêu:
- **Unique root-cause findings**.
- **Affected asset instances**.
- **Occurrences/variants**.
- **Candidate scanner alerts vs confirmed findings**.
- **Untriaged/Unknowns**.
- **Technical issues vs accepted risks**.

Không đếm 10 duplicate tool alerts thành 10 independent vulnerabilities; cũng không gộp 10 affected assets thành 1 rồi bỏ qua rollout/remediation trên 9 assets còn lại.

### 11.4. Bảng phân bố severity

Nếu có 1 High, 2 Medium, 1 Low **đã xác nhận**, có thể hiển thị số theo kỳ. Nhưng còn hai untriaged high-potential cases phải được nêu **riêng**, không tự chuyển Low hay loại khỏi mẫu số. Số lượng findings thấp không đồng nghĩa coverage tốt.

## 12. Risk rating: severity, likelihood, impact và uncertainty

### 12.1. Phân biệt mức độ kỹ thuật và ưu tiên xử lý

**Technical severity** có thể mô tả tính nghiêm trọng của weakness trong các điều kiện xác định. **Business priority** còn phụ thuộc dữ liệu, exposure, asset criticality, exploitability, threat intelligence, contractual obligations, remediation time và controls hiện tại.

Ví dụ BOLA có thể không cần authentication bypass mà chỉ cần tài khoản teacher hợp lệ; nếu có thể đọc điểm của tenant khác, impact confidentiality vẫn đáng kể.

### 12.2. Các tín hiệu định lượng/định tính

| Tín hiệu | Câu hỏi |
|---|---|
| **Preconditions** | Có cần tài khoản, role, vị trí mạng hoặc trạng thái đặc biệt? |
| **Attack complexity** | Có cần race/chuỗi bước hiếm hay thao tác đơn giản? |
| **Reachability** | Entry points có Internet-facing, internal, worker/queue? |
| **Data sensitivity** | Điểm, danh tính, token, billing hoặc admin data? |
| **Impact** | Đọc/sửa/xóa dữ liệu, tăng quyền, availability, traceability? |
| **Blast radius** | Một lớp, một tenant, nhiều tenants, toàn fleet? |
| **Confidence** | Bằng chứng behavioral + logs + test fixtures đủ chưa? |
| **Compensating controls** | Có hiệu lực thực và khả năng bypass nào? |
| **Exploit intelligence** | Có dấu hiệu exploitation/known active attacks được xác minh? |
| **Business context** | Dịch vụ critical, uptime, confidentiality promises, obligations? |
| **Fix path** | Có hotfix, mitigation, operational constraints hoặc vendor dependency? |

### 12.3. CVSS là một phần bằng chứng, không phải kết luận thay lãnh đạo

CVSS dùng vector/metrics theo một **phiên bản được chỉ định** để biểu đạt severity kỹ thuật; nếu dùng, cần:
- Ghi CVSS version.
- Vector string và assumptions.
- Chứng cứ cho các metric quan trọng.
- Phân biệt base score với organizational environmental/threat context khi áp dụng theo phiên bản.
- Không tự thay đổi CVSS score để đạt SLA mà không có rationale.
- Không đặt số điểm “chính xác” khi chưa đủ điều kiện xác định.

Một scanner gắn CVSS 9.x cho advisory ở library **không tự chứng minh product exploitable**. SCA matching/VEX/reachability và runtime context cần phân tích riêng.

### 12.4. CWE, CVE và OWASP mapping

- **CWE** thường mô tả một *weakness class* (ví dụ thiếu kiểm tra quyền hoặc unsafe data flow); không đồng nghĩa một incident.
- **CVE** định danh vulnerability được công bố trong một sản phẩm/thành phần khi có ID phù hợp; không phải mọi pentest finding đều có CVE.
- **OWASP Top 10/API Top 10** giúp phân loại nhóm rủi ro hoặc hướng kiểm thử; không thay finding evidence và không nên gán mapping nếu không khớp.
- **CVE/Advisory, package identity và VEX** có giá trị khi finding liên quan component; cần matching và affected version proof.

### 12.5. Confidence nên hiển thị riêng severity

Một scanner heuristic chưa được xác minh có thể gắn severity High nhưng confidence Low. Đừng biến uncertainty thành Low impact hoặc tự ghi Verified. Trạng thái phù hợp là **needs validation** và cân nhắc biện pháp tạm nếu potential impact cao.

### 12.6. Risk matrix minh họa

| Impact \\ Likelihood | Low | Medium | High |
|---|---|---|---|
| **High impact** | Medium/High tùy policy | High | High/Critical tùy policy |
| **Medium impact** | Low/Medium | Medium | High |
| **Low impact** | Low | Low/Medium | Medium |

Ma trận chỉ là ví dụ minh họa **không phải chuẩn chấm điểm phổ quát**. Khi sử dụng phải định nghĩa từng mức, evidence requirement, thẩm quyền override và version của policy.

## 13. Taxonomy findings, statuses và reason codes

### 13.1. Technical verdict

| Verdict | Ý nghĩa | Evidence |
|---|---|---|
| **CONFIRMED / TP** | Requirement/weakness bị vi phạm thật trong scope | Reproduction/test/context |
| **FALSE_POSITIVE** | Scanner/test hypothesis sai cho target/rule đã xác minh | Technical rationale và reviewer |
| **NOT_APPLICABLE** | Control/weakness không áp dụng với artifact/condition đã chứng minh | Scope/config/build |
| **DUPLICATE** | Cùng finding/root cause được theo dõi ở record khác | Parent link, affected variants |
| **NEEDS_VALIDATION** | Chưa đủ chứng cứ xác nhận/bác bỏ | Unknowns, owner, next checks |
| **INCONCLUSIVE** | Test đã chạy nhưng noise/coverage giới hạn kết luận | Test logs, confounders |
| **TOOL_ERROR** | Không có kết quả test hợp lệ | Error/scan health |
| **OBSERVATION** | Defense-in-depth/improvement, chưa chứng minh vulnerability | Policy/impact rationale |

### 13.2. Remediation state

- NEW/OPEN.
- TRIAGED/CONFIRMED.
- FIX_IN_PROGRESS.
- FIX_READY.
- FIX_DEPLOYED_PENDING_RETEST.
- PARTIALLY_FIXED.
- VERIFIED_FIXED.
- REOPENED.
- MITIGATED.
- RISK_ACCEPTED.
- CLOSED với **reason code** tương ứng.

**Technical status** nên lưu tách với **remediation/exception status**. Ví dụ TP có thể có một WAF mitigation và accepted risk tạm, nhưng vẫn là technical weakness chưa vá.

### 13.3. Vì sao không để “Closed” đồng nghĩa mọi trường hợp?

Một closure có thể xảy ra vì:
- Verified remediation.
- Verified false positive.
- Duplicate linked to active master.
- Asset decommissioned được chứng minh.
- Approved risk acceptance theo thời hạn.

Nếu dashboard hiển thị tất cả như “fixed”, tỷ lệ remediation và remaining risk bị sai lệch. Báo cáo cần ghi lý do và người phê duyệt.

### 13.4. Không thay evidence bằng nhãn

Những kết luận không đủ:
- “Không tìm thấy lần nữa.”
- “QA pass.”
- “CVE đã được xử lý.”
- “Vendor xác nhận.”
- “Đã chạy scanner.”
- “Đã có WAF.”
- “Developer chấp nhận.”
- “Ticket completed.”

Mỗi nhãn cần supporting **artifact/test/version/owner/scope** và test oracle tương ứng.

## 14. Mẫu cấu trúc một technical finding

### 14.1. Các trường chính

Một finding đủ để developer hành động và reviewer tái xác minh nên có:

| Trường | Nội dung cần ghi |
|---|---|
| **Finding ID** | Stable reference; link to tracker |
| **Title** | Weakness + business action/target cụ thể |
| **Status** | Confirmed/Needs validation/FP và remediation state tách biệt |
| **Severity/priority** | Rationale + scoring framework/version nếu dùng |
| **Confidence** | Mức chứng cứ xác nhận behavior |
| **Affected assets** | Service, URI/method, component, region/tenant/build |
| **Security requirement** | Expected policy/control objective |
| **Attack preconditions** | Role, authentication, feature, network, data state |
| **Observation** | Actual response/state/side effects |
| **Technical cause** | Root cause đã xác minh hoặc hypothesis đánh dấu rõ |
| **Safe reproduction** | Given–When–Then với synthetic fixtures |
| **Evidence** | Sanitized request/response/log/test/event/screenshot refs |
| **Business impact** | Confidentiality/integrity/availability, data/scope |
| **Likelihood/exposure** | Assumptions và constraints |
| **Remediation** | Root-cause fix và cross-cutting changes |
| **Mitigation** | Compensating controls khi chưa fix kịp |
| **Verification criteria** | Positive/negative/side-effect/regression/deploy checks |
| **Owner/due date** | Theo organizational risk policy |
| **Limitations/unknowns** | Những việc chưa chứng minh |
| **Review/approval** | Reviewer, timestamp, report/record version |

### 14.2. Title chính xác hơn generic title

**Yếu:** “Authorization bug”.

**Tốt hơn:** “Teacher thuộc tenant A tạo được grade-export job cho class thuộc tenant B qua POST /classes/{id}/exports”.

**Yếu:** “SSL issue”.

**Tốt hơn:** “Public TLS listener X chấp nhận cấu hình giao thức không phù hợp baseline Y trong kỳ thử T”.

Title nên cho phép asset owner xác định **vấn đề gì, ở đâu, có tác động nào**, nhưng không chứa secrets hoặc nội dung có thể gây nguy cơ khi report bị rò.

### 14.3. Viết mô tả có thể kiểm chứng

Một mô tả kỹ thuật tốt:
1. Nêu **expected security requirement**.
2. Nêu actor/precondition và affected resource.
3. Nêu phép thử an toàn được chạy.
4. Nêu actual outcome trái policy.
5. Nêu evidence location, timestamp và target identity.
6. Nêu interpretation và limitations.
7. Nêu hướng fix/retest.

### 14.4. Tách observed behavior khỏi suy luận

**Observed:** API trả 202, job record cho class ngoài quyền xuất hiện, file thử được tạo trong test bucket.

**Inferred:** object-level authorization chưa được áp đồng nhất giữa API và worker.

**Unknown:** đường download production có cùng thiếu sót? Có data leak thật trước test hay không? Nếu chưa kiểm tra, không biến inference/unknown thành fact.

### 14.5. Một finding có nhiều occurrences

Nếu cùng root cause xuất hiện trên 12 routes, nên dùng:
- Một parent finding để sở hữu remediation.
- Bảng occurrences và affected service/route/role.
- Một hoặc vài safe reproduction chi tiết đại diện.
- Tests/evidence cho từng affected path/variant cần closure.
- Kết quả **partial** nếu còn path chưa fix.

Không xóa dấu vết occurrences bằng cách “deduplicate” rồi report một endpoint như thể toàn bộ risk chỉ ở đó.

## 15. Viết reproduction và proof-of-concept an toàn

### 15.1. Định dạng Given–When–Then

Một reproduction có thể dùng:

~~~text
Given:
  - Target: Learning API, test environment E, artifact digest D
  - Actor: Teacher A, tenant A, đã đăng nhập bằng test identity
  - Resource: Class B, tenant B, dữ liệu synthetic
  - Business policy: Teacher A không được truy cập Class B

When:
  - Teacher A gửi một yêu cầu export Class B tới route trong scope

Then (expected):
  - Server từ chối theo policy
  - Không sinh job, file, email, signed URL ngoài quyền

Observed:
  - Request được chấp nhận trong phiên kiểm thử đã ghi
  - Export job cho Class B xuất hiện trong test queue
  - Test output được tạo theo evidence IDs

Evidence:
  - Request ID, job ID, test run, anonymized response/status,
    scoped logs, timestamps và build/config identifiers
~~~

Điểm mạnh là **phân biệt preconditions, expected policy và actual result**. Một PoC tốt không chỉ là ảnh một request thành công.

### 15.2. Mẫu HTTP đã được ẩn thông tin

~~~http
POST /api/v1/classes/CLASS-B-TEST/export HTTP/1.1
Host: learning-api.staging.example.invalid
Authorization: Bearer [REDACTED_SYNTHETIC_TOKEN]
Content-Type: application/json
X-Test-Correlation-Id: PT-001-EXAMPLE

{"format":"csv"}
~~~

~~~text
Observed: 202 Accepted (illustrative)
Response: {"jobId":"JOB-SYNTHETIC-001"}
Policy expectation: Deny for Teacher A on Class B
Correlated result: JOB-SYNTHETIC-001 visible in controlled test queue
~~~

Các định danh là **hư cấu**, domain \`example.invalid\` không đại diện service thật; không đưa access tokens còn hiệu lực hoặc dữ liệu bảng điểm thật vào báo cáo. Đây là **mẫu báo cáo**, không phải hướng dẫn chạy thử trên hệ thống không được cấp quyền.

### 15.3. Khi nào PoC không được thực hiện đầy đủ?

Pentest có thể bị giới hạn:
- Không được truy xuất dữ liệu production.
- Không được thử password spraying/DoS.
- Không được tạo hàng loạt jobs/exports.
- Không được truy cập vendor infrastructure.
- Không được tạo persistence hoặc phá dữ liệu.
- Không được thực hiện test ảnh hưởng người dùng.

Khi đó có thể dùng:
- Minimal synthetic fixture.
- Non-destructive behavior.
- Code/config review hỗ trợ.
- Evidence từ approved logs.
- Attack feasibility analysis nêu uncertainty.
- Risk-based partial reproduction trong lab.

**Không “bù” việc thiếu test permission bằng suy đoán đã khai thác thành công.** Report ghi mức độ kiểm chứng (observed, demonstrated under lab conditions, theoretical, untested).

### 15.4. Reproduction phải đủ để sửa, không cần cung cấp bí mật

Một technical appendix có thể có route/method/schema, nhưng nhạy cảm như internal admin endpoints, service tokens hoặc test credentials nên để trong **restricted evidence repository**, chỉ dẫn reference ID/access path theo policy. Những phần có thể bị lạm dụng cần giới hạn người đọc, redaction và distribution control.

### 15.5. Test oracle không được phụ thuộc duy nhất status

- 403 có thể xuất hiện sau khi queue job đã tạo.
- 200 có thể là trang login bị redirect (không phải protected endpoint).
- 404 có thể là deliberate anti-enumeration, không phải endpoint không tồn tại.
- 500 có thể là parser error, không phải chứng cứ SQLi.
- 429 có thể là scanner rate-limited, khiến coverage thiếu.
- Một file không xuất hiện ngay có thể do async delay, không chứng minh không side effect.

Cần **policy-aware test oracle**: state, authorized behavior, data leakage, logs, queue/storage và thời điểm.

## 16. Evidence catalog, integrity và confidentiality

### 16.1. Evidence types

| Evidence | Chứng minh điều gì | Không tự chứng minh |
|---|---|---|
| HTTP request/response | Hành vi trên network path với context | Mọi code path đã an toàn |
| Browser screenshot/video | UI/browser observation | Server-side authorization |
| Test account authorization matrix | Expected role/resource policies | Policy được enforce trên mọi API |
| DB/job/storage query | Side effects trong test window | Không có alternate async path |
| Source/code/config review | Potential root cause/safeguard | Fix đã deploy |
| Scan report/tool logs | Scanner behavior/rule outcomes | Scanner coverage toàn product |
| Build ID/image digest | Định danh artifact | Mọi instance đang chạy artifact |
| Deployment inventory | Runtime version distribution | No dynamic code/config drift |
| TLS/network scan | Endpoint configuration lúc thử | Mọi listener/region có config giống nhau |
| Vendor statement | Supplier assertion theo scope | Bên mua đang dùng đúng affected version |
| SCA/SBOM | Component inventory và advisory mapping | Code path thực sự exploitable |
| Audit/SIEM event | System emitted/collected event | Không có event bị bỏ sót |
| Finding ticket/approval | Governance actions | Technical fix đúng |
| Retest report | Kiểm chứng case đã test | Không có vulnerabilities khác |

### 16.2. Evidence ID và metadata

Đối với mỗi evidence item:
- Evidence ID, finding ID, test case ID.
- System/service/environment/target identity.
- Source path/log query/test run, collector identity.
- Original timestamp và time zone/clock source.
- Source revision/build/image/config khi có.
- Original file digest hoặc storage version khi policy yêu cầu.
- Redaction/transformation record.
- Owner/custodian và quyền truy cập.
- Storage location (access-controlled).
- Retention/disposal policy.
- Completeness/known limitations.
- Reviewer verification/sign-off.

### 16.3. Không làm mất provenance do dán ảnh

Một screenshot được đưa vào report có thể minh họa symptom nhưng thiếu:
- Actor/role đang đăng nhập.
- Endpoint/method và request ID.
- Target version.
- Timestamp.
- Resource ownership.
- Test data provenance.
- Whole sequence của workflow.

Do đó nên liên kết screenshot với **test run/correlation ID và structured evidence**, không dùng ảnh đơn độc cho High risk claim.

### 16.4. Chuỗi bảo quản (chain of custody)

Khi bằng chứng có thể liên quan incident/legal review:
1. Ghi nguồn, người thu, công cụ và lúc thu.
2. Bảo toàn bản gốc theo quyền/truy cập cần thiết.
3. Lưu checksum/digest khi phù hợp.
4. Tạo bản sanitized cho report; ghi transformations.
5. Không cho sửa/xóa không kiểm soát.
6. Theo dõi access/transfer.
7. Đặt retention/hold theo policy và nghĩa vụ liên quan.
8. Kiểm tra object còn lấy lại được khi audit/retest.

Chữ ký hoặc hash chỉ hỗ trợ **integrity của artifact**, không tự bảo đảm nguồn đáng tin, nội dung đúng hay phương pháp kiểm thử đầy đủ.

### 16.5. Data minimization theo loại tài liệu

**Executive:** rủi ro và sản phẩm, không nhúng secrets/raw logs.

**Technical report:** redacted reproductions và links tới protected evidence.

**Evidence vault:** dữ liệu chi tiết cần thiết, IAM chặt, retention và audit.

**External/customer summary:** chỉ thông tin được duyệt, scope rõ và không tiết lộ internal exploit details không cần thiết.

### 16.6. Cấm coi môi trường test là không có privacy risk

Synthetic users có thể dùng email thật để gửi thông báo hoặc cloud logs có IDs của nhân sự. Đảm bảo:
- Không lộ access/refresh tokens.
- Không đính kèm real grades/PII.
- Không xuất internal private keys.
- Không đưa password reset links còn hiệu lực.
- Không dùng test account chung với production.
- Có cleanup và controlled storage.
- Test owner có quyền chứng minh mọi data fixture dùng.

## 17. Từ một lỗ hổng đến attack path và systemic risk

### 17.1. Vì sao chỉ liệt kê CVE/CWE riêng lẻ chưa đủ?

Một lỗ hổng authorization ở API có thể dẫn tới:
1. Actor ngoài quyền tạo job.
2. Job được worker đặc quyền xử lý.
3. File chứa dữ liệu nhạy cảm được tạo.
4. Download URL cho actor không có quyền.
5. Việc truy cập không tạo audit event đúng.
6. Data exposure qua nhiều tenants.

Một báo cáo có thể cần **attack narrative** để lãnh đạo hiểu chain of consequences và để developer không sửa một endpoint rồi bỏ worker/storage.

### 17.2. Sơ đồ attack path minh họa

~~~mermaid
flowchart LR
    A["Teacher A - synthetic"] -->|"Object ID của Class B"| API["Learning API"]
    API --> Q[["Export queue"]]
    Q --> W["Privileged report worker"]
    W --> DB[("Grades DB")]
    W --> S[("Private object store")]
    S --> D["Download flow"]
    API --> L["Audit / monitoring"]
    W --> L
~~~

**Không phải mọi mũi tên đều là vulnerability.** Sơ đồ mô tả data flow và ranh giới. Phải chú thích **mũi tên nào đã test/failed, mũi tên nào chỉ là giả thuyết, mũi tên nào chưa được phép test**.

### 17.3. Attack chain có nhiều findings

Nếu API thiếu object authz, worker tin job thiếu validation và download token không được scoped, có thể tách **ba root-cause findings**. Nếu chúng tạo thành một scenario rủi ro lớn, executive summary nên chỉ ra **mối liên hệ và ưu tiên remediation**. Đừng cộng ba CVSS scores để ra một “chỉ số rủi ro” không có cơ sở.

### 17.4. Blast radius: observed vs potential

- **Observed:** một test teacher đọc một synthetic report của class B.
- **Plausible:** những lớp khác có cùng policy gap cũng có thể bị ảnh hưởng.
- **Unverified:** mọi tenants, mọi regions hoặc dữ liệu production đã bị khai thác.
- **Excluded:** vendor e-mail side effects hoặc legacy exporter chưa được kiểm tra.

Ghi rõ từng lớp. Mở rộng từ một case sang toàn hệ thống phải có **population analysis, code/data relationship, access matrix hoặc evidence tương xứng**.

### 17.5. Đánh giá systemic causes

Từ nhiều findings có thể rút ra:
- Authorization không nhất quán giữa controllers và workers.
- Untrusted client tenantId được chuyển xuyên services.
- Missing central policy/secure API patterns.
- Testing chỉ có positive cases, không có negative cross-tenant cases.
- Không có asset owner cho legacy exporter.
- Scanner không có authenticated roles.
- Audit pipeline bị thiếu correlation IDs.

Những điều này thuộc **control/program improvement**, có thể là finding riêng nếu có yêu cầu bảo mật và evidence, hoặc observation với owner; không trộn tùy tiện thành confirmed vulnerability.

## 18. Technical finding hoàn chỉnh: BOLA trong Learning Platform

### 18.1. Record tổng quan

**Finding ID:** PT-LEARN-001 (minh họa).

**Title:** Giáo viên thuộc tenant A có thể khởi tạo xuất điểm của lớp tenant B do thiếu kiểm tra actor–resource relationship.

**Weakness:** Broken Object Level Authorization / thiếu authorization theo tài nguyên.

**Technical status:** Confirmed trong synthetic test scope giả định.

**Risk priority:** High trong rubric minh họa vì liên quan confidentiality của điểm học viên; không có CVSS score thực hoặc khẳng định exploit ngoài test.

**Target:** Learning API + report worker tại staging release R; artifact digest, test window và config phải được điền từ run thật.

**Affected data:** grade records của lớp ngoài quyền nếu report workflow thành công.

### 18.2. Security requirement

> Mỗi yêu cầu tạo hoặc tải report điểm phải được kiểm tra theo identity đã xác minh, tenant và quan hệ phân công lớp; worker chỉ xử lý job có delegated authority hợp lệ; nếu từ chối, không tạo durable job/file/download và không tiết lộ dữ liệu hay metadata vượt policy.

### 18.3. Safe reproduction

**Given:** Teacher A thuộc tenant A và không được phân công Class B thuộc tenant B; có dữ liệu giả và test authorization matrix.

**When:** Teacher A gọi export endpoint cho Class B qua authenticated test client có quyền thử.

**Expected:** Deny theo API contract, no job/no file/no notification/no downloadable artifact ngoài quyền.

**Observed trong tình huống giả định:** API chấp nhận request, tạo job record; report worker xử lý dữ liệu của Class B trong controlled test storage.

**Evidence:** Request ID, job ID, synthetic resource ownership, redacted response, worker/DB/storage traces, tool/version/time và screenshot (nếu cần). Không có raw grades/tokens thật.

### 18.4. Root cause và phạm vi còn nghi ngờ

Có khả năng API kiểm tra role TEACHER nhưng không kiểm tra actor có được phân công Class B; worker tin client/queue classId. Để ghi **root cause đã xác nhận**, cần code/config/data flow review; nếu mới có black-box observation, ghi **root-cause hypothesis**.

**Unverified paths:** legacy batch export, GraphQL equivalent, direct worker invocation, production release digests hoặc signed download lifetime nếu chưa được phép kiểm tra.

### 18.5. Business impact và điều kiện khai thác

Tác động confidentiality có thể nghiêm trọng khi account teacher hợp lệ xem được thông tin điểm ngoài quyền. Tuy nhiên, **không tự suy** unauthenticated actor cũng khai thác được, không nói số lượng học viên ảnh hưởng hoặc incident đã xảy ra khi chưa có evidence. Nên diễn đạt các constraints và boundaries.

### 18.6. Đề xuất remediation

- Centralize per-object/tenant authorization theo verified principal.
- Đảm bảo DB queries luôn scoped đúng tenant/resource.
- Queue message chỉ chứa trusted scoped job identity/authorization context.
- Worker validate delegated scope, expiry/recheck theo policy.
- Private object storage, signed URL được scope/TTL/revoke theo yêu cầu.
- Audit denial và export actions nhưng không lộ raw data.
- Test cross-role/tenant/object và side effects.
- Code review các sibling endpoints có cùng permission pattern.
- Rollout fix tới API/worker/fleet có records.

### 18.7. Retest acceptance criteria

- Teacher A không thể export Class B.
- Teacher B được phân công Class B vẫn export được.
- Không có unauthorized DB query/job/object/email phát sinh.
- Direct paths và job replay/revocation theo scope đạt yêu cầu.
- Download policy không cho actor ngoài quyền lấy report.
- No sensitive leak trong error/audit logs.
- Fixed build/image digests hiện diện trong affected deployments.
- Retest scanner healthy, đúng identities và routes.
- Reviewer xác nhận evidence/limits; remaining paths có separate tracking.

### 18.8. Kết luận mẫu

> Trong synthetic staging scope được phép, finding PT-LEARN-001 đã tái hiện hành vi export ngoài quyền; dữ liệu bằng chứng hỗ trợ weakness tại một workflow xác định. Cần remediation tại API và worker cùng kiểm chứng artifact/runtime. Kết luận không khẳng định production users đã bị ảnh hưởng hay mọi tenants đều exploitable khi chưa có evidence.

Đây là **mẫu bản báo cáo kỹ thuật**, không phải finding thực tế của dự án.

## 19. Ví dụ kỹ thuật thứ hai: SQL injection warning chưa được xác minh

### 19.1. Vì sao cần giữ trạng thái điều tra?

Một DAST rule thấy API trả 500 với input đặc biệt và gắn SQL injection; nhưng 500 có thể do parser, upstream timeout, rate limit hoặc WAF. Không nên:
- Ghi SQL injection confirmed chỉ từ 500.
- Bác bỏ ngay vì dùng ORM.
- Thử phá hoại/exfiltrate data thật để có PoC.
- Tắt rule để báo cáo sạch.

### 19.2. Finding record ban đầu

~~~text
ID: PT-LEARN-004
Type: Suspected SQL injection
Endpoint: GET /api/v1/classes?sort=...
Status: NEEDS_VALIDATION
Original observation: Intermittent 500 and response timing variation
Known confounders: Network jitter, parser errors, WAF, DB pool pressure
Evidence: request correlation IDs, redacted responses, trace refs
Next steps: code/query review, input binding and allowlist tests in lab
Business impact: NOT YET DETERMINED
~~~

### 19.3. Có hai loại data flow

~~~java
// Anti-pattern minh họa: raw client-controlled field tạo SQL syntax.
String query = "SELECT id, name FROM classes ORDER BY "
        + request.getParameter("sortBy");

// Pattern an toàn hơn cho trường sort: server-side mapping.
String sortColumn = switch (requestedSort) {
    case NAME -> "name";
    case CREATED_AT -> "created_at";
};
String safeQuery = "SELECT id, name FROM classes ORDER BY " + sortColumn;
~~~

Đây chỉ là **minh họa kỹ thuật**; actual fix còn cần query parameterization đối với values, tenant/authorization controls, DB privileges, pagination, query bounds và review của tất cả code paths.

### 19.4. Triage và report update

Sau khi code review/lab integration xác minh:
- Nếu client input thật sự điều khiển SQL syntax → **Confirmed TP**, document evidence, impact và fix.
- Nếu input luôn được map server-side, không thể điều khiển syntax và response lỗi do parser → có thể FP với rationale, nhưng parser/error handling có thể cần ticket riêng.
- Nếu không rõ actual deployed query builder → **Needs Validation**, có owner và deadline.

**Không thay một dấu hỏi bằng severity chính xác giả tạo.**

## 20. Các loại findings khác và cách diễn giải đúng

### 20.1. Cross-site scripting (XSS)

Một test chỉ ghi “giá trị input xuất hiện trong HTML” chưa chứng minh script thực thi. Report cần nêu:
- Stored/reflected/DOM context.
- Source, template, browser sink/renderer.
- HTML text/attribute/JavaScript/URL context.
- Output encoding hoặc sanitizer trong actual config.
- Browser observation bằng synthetic fixture khi được phép.
- Views/roles khác của cùng dữ liệu.
- Tác động tới user session hoặc nội dung theo threat model.
- Fix và test positive/negative theo context.

Một template tự escape đúng có thể làm scanner heuristic FP. Nhưng nếu cùng giá trị được render raw trong admin console thì vẫn là TP ở context đó. Không gộp mọi paths thành “đã fix XSS toàn ứng dụng”.

### 20.2. Server-Side Request Forgery (SSRF)

Với một API tải nội dung từ URL:
- User điều khiển toàn URL hay chỉ chọn trusted partner ID?
- Redirect/DNS/private address protections ở đâu?
- Egress network và workload identity có hạn chế?
- Có gửi credentials/headers sang destination khác?
- URL từ config/tenant có thể bị sửa không?
- Có file/plugin/runtime path khác dùng cùng HTTP client?
- Test có dùng controlled synthetic endpoints và được phép không?

Report nên mô tả trust boundary và chứng cứ network, không hướng dẫn trực tiếp truy cập cloud metadata hoặc internal systems không được cho phép.

### 20.3. Session/authentication

Các phát hiện như token còn hiệu lực sau logout, cookie flags hoặc password recovery cần phân biệt:
- Security requirement nào áp dụng?
- Self-contained token expiry vs revocation semantics đã được phê duyệt?
- Session state thay đổi trong window nào?
- Gateway/IdP/backend nhất quán chưa?
- Cross-browser/device/recovery paths có thuộc scope?
- Bằng chứng sử dụng synthetic identities được thu thế nào?
- Actual behavior có trái policy hay chỉ không phù hợp expectation của tester?

Một “logout trả 200” không chứng minh invalidation; một JWT tự chứa không tự sai nếu system requirement không bắt instant revocation.

### 20.4. Secrets và sensitive data leakage

Nếu pentest thấy token trong response/log:
- Đây là credential thật hay synthetic canary?
- Token đã valid/có authority không? Xác minh qua owner bảo mật, không paste raw secret.
- Data sinks nào chứa bản sao, trong kỳ nào?
- Remediation có revoke/rotate, bỏ logging, review history/artifact, limit access?
- Có incident/privacy assessment tách biệt không?
- Retest kiểm tra no new leakage và old token invalid theo policy?

Chỉ xóa dòng log và chụp screenshot không thấy token nữa **chưa đủ** đóng toàn bộ exposure finding.

### 20.5. TLS/cấu hình hệ thống

Với finding về weak TLS policy, nêu:
- Target FQDN/port và listener, environment, scan time.
- Actual negotiated protocol/cipher/certificate behavior.
- Security baseline cụ thể đã được phê duyệt.
- CDN/ingress/load balancer/backend paths đã/không test.
- Client compatibility/availability sau remediation.
- Warnings về reverse proxy/multi-tenant endpoint.
- Bằng chứng config effective, không chỉ intended config.

Không dùng câu “HTTPS enabled” để chứng minh mọi transport controls đạt.

### 20.6. Cloud IAM và public storage

Nếu report phát hiện object được anonymous read:
- Tài nguyên/test bucket cụ thể, data classification.
- Policy ở org/account/resource levels và effective permissions.
- Actor anonymous/unprivileged và actual response.
- Cross-account/cross-region exposure đã được phép kiểm tra chưa?
- Remediation theo IaC và runtime state.
- Logs/incident impact trước khi fix.
- Negative tests sau sửa, owner/expiry cho exceptions.

Một IaC PR đã merge không chứng minh cloud resource production đã thay; cần runtime effective-state evidence.

### 20.7. Dependency/library advisory trong pentest

Nếu scanner thấy library version có CVE:
- Component identity/version/purl/CPE matching basis.
- Artifact/image digest và release.
- Advisory/source/snapshot time.
- Vendor backport, fork, shaded package, native libs.
- Product-specific impact conditions và reachability context.
- VEX/not-affected rationale khi có.
- Distinguish **vulnerable component presence** với **demonstrated exploit path**.
- Risk owner/remediation/deployment verification.

Không tự gọi một CVE match là “đã khai thác được production” hoặc “false positive” chỉ vì chưa có public network entry point.

### 20.8. Availability/DoS

Nếu RoE cấm kiểm thử tải phá hoại, ghi **not tested/destructive tests excluded**, đề xuất performance/resilience testing an toàn ở lab và review resource bounds. Không kết luận hệ thống chống DoS chỉ từ việc công cụ không gây crash. Nếu có load test được phép, mô tả resource budget, rate, stop conditions, expected/actual và safety controls.

## 21. Root cause và systemic findings

### 21.1. Report nên ưu tiên nguyên nhân, không chỉ symptom

Ví dụ ba endpoints cho phép export ngoài quyền. Symptom là IDOR trên URLs, root cause có thể là:
- “Teacher” role được coi là toàn quyền đọc mọi class.
- Không truyền verified tenant identity đến repository.
- Worker tin classId/tenantId trong queue message.
- Các developers copy một helper thiếu object policy.
- Security tests chỉ kiểm tra happy path.

Remediation nên giải quyết **policy architecture/data access boundary** thay vì chặn ba ID test đã biết.

### 21.2. Root-cause analysis cần mức chắc chắn

**Confirmed root cause:** Source/config/data path review chứng minh tại sao behavior xảy ra.

**Likely root cause:** Hành vi gợi ý, có hỗ trợ nhưng thiếu code/implementation evidence.

**Hypothesis:** Chỉ là giả thuyết cần kỹ thuật xác minh.

Không ghi “gốc lỗi nằm ở controller X” như fact khi chỉ có black-box response và chưa được xem implementation.

### 21.3. Cross-cutting findings

Có thể tạo một mục **systemic assurance gaps** khi có bằng chứng:
- Thiếu secure-by-default authorization middleware/pattern.
- Không có policy tests cho cross-tenant access.
- Shared service credentials quá quyền.
- Không có regression scanner/CI test cho high-risk weakness.
- Asset inventory thiếu exporters/regions.
- Scan platform thường xuyên mất credentials.
- Audit log thiếu correlation và detection coverage.

Những gaps có thể là **control findings** hoặc **observations** tùy security requirements và evidence. Không tô mọi process improvement thành một vulnerability confirmed.

### 21.4. Đánh giá biện pháp bù trừ

Nếu WAF tạm giảm exposure cho SQLi:
- Có blocking rule được bật ở paths/regions cụ thể?
- Có direct backend/internal paths bypass WAF?
- Rule false negatives/positives thế nào?
- Có logging/monitoring và owner?
- Có expiry/trigger và plan sửa code?
- Có operational outage risk?
- Có reviewer/risk authority?

Ghi **Mitigated** khi control có hiệu lực trong scope, nhưng **not fixed** nếu source weakness còn. Điều này tránh báo cáo dễ hiểu sai cho executive.

## 22. Remediation recommendations: cụ thể, ưu tiên, có thể đo

### 22.1. Cấu trúc đề xuất tốt

Mỗi recommendation nên chỉ ra:
1. **Control objective:** điều kiện an toàn cần đạt.
2. **Root cause:** rào cản kỹ thuật hiện tại.
3. **Preferred remediation:** thay đổi code/config/architecture.
4. **Compensating control:** giảm exposure khi chưa sửa xong.
5. **Validation method:** cách chứng minh fix hoạt động.
6. **Affected population:** nơi cần rollout.
7. **Owner/dependency:** ai làm và phụ thuộc team nào.
8. **Risk/priority/deadline:** theo policy và business context.
9. **Rollback/operability:** cách giữ service hoạt động an toàn.
10. **Evidence/closure:** những tệp/log/tests và reviewer cần.

### 22.2. Ví dụ từ câu yếu thành câu tốt

**Yếu:** “Implement proper authorization.”

**Cụ thể hơn:**

> Tại mọi operation tạo/lấy/tải grade report của service được nêu trong finding, xác minh verified principal có quan hệ phân công lớp trong tenant được yêu cầu. Không lấy tenant/role authority từ client-controlled fields. Ràng buộc job và object storage với resource scope đã phê duyệt; worker áp delegated/recheck policy. Thêm positive/negative/cross-tenant/temporal tests và kiểm tra no unauthorized durable side effects. Rollout API và report worker images tới đúng affected fleet; verify deployed digests trước khi closure.

### 22.3. Không đưa “mẫu code” như lệnh vá production

Code snippet trong report chỉ là **gợi ý cơ chế**, không phải patch đã được review cho toàn hệ thống. Dẫn tới threat model, policy, library/framework contracts, compatibility và regression. Tránh tạo cảm giác “paste code này là giải quyết xong”.

### 22.4. Remediation plan theo waves

| Wave | Mục tiêu | Action ví dụ | Điều kiện hoàn tất |
|---|---|---|---|
| **Immediate containment** | Giảm exposure khi chưa sửa xong | Hạn chế export, thu hồi token, tăng monitoring nếu cần | Control effect verified và owner chấp thuận |
| **Root-cause fix** | Loại nguyên nhân đã xác minh | Authorization/data query/queue worker policy | Code + integration/security tests |
| **Release/rollout** | Đưa fix đến assets bị ảnh hưởng | Immutable build, deployment orchestration | Fleet digest/config reconciliation |
| **Retest** | Xác minh original và sibling paths | Targeted/DAST/manual tests | Positive/negative/side-effect tests đạt |
| **Hardening** | Giảm khả năng tái phát | Secure patterns, SAST checks, training | Controls vào SDLC có monitoring |
| **Review and monitor** | Duy trì assurance | Periodic check, drift/rollback triggers | Evidence/owner/report update |

### 22.5. Deadline/SLA không nên bịa

Có thể viết “urgent theo High risk remediation policy” hoặc “trong thời hạn được Risk Owner phê duyệt” nếu chưa biết SLA. Nếu report nêu thời hạn cụ thể, phải lấy từ **engagement/policy/decision có thẩm quyền**, không tự tuyên bố mọi High phải sửa trong X ngày như chuẩn phổ quát.

### 22.6. Ưu tiên theo khả năng giải quyết root cause

Một remediation giải quyết shared policy/library cho 20 routes có thể đáng ưu tiên hơn 20 hotfix riêng lẻ, nhưng cần test các affected paths và tránh single point of failure. Một “quick mitigation” không thay requirement long-term. Report nên nêu dependencies/cross-team effort và rủi ro khi rollout.

## 23. Remediation tracker và acceptance criteria

### 23.1. Tracker nối báo cáo với hoạt động thực tế

Một finding technical report **chưa kết thúc khi gửi đi**. Hãy tạo/cập nhật registry có:
- Finding ID và report version.
- Technical verdict và priority.
- Asset owner và implementer.
- Affected services/versions.
- Risk/impact rationale.
- Approved remediation, dependency và due date.
- Containment/mitigation.
- PR/change ID và build/deployment ID.
- Targeted test/retest run.
- Evidence links và reviewer.
- Partial status/exceptions, residual risk.
- Reopen triggers và audit history.

### 23.2. Trạng thái nên phản ánh verified results

| Stage | Đủ điều kiện? | Không đủ |
|---|---|---|
| Fix proposed | Có proposal/design review | Chưa chứng minh security behavior |
| PR merged | Code đã được merge | Chưa chắc được build/deploy |
| Release built | Artifact chứa code | Chưa chắc cluster đang chạy |
| Deployed | Runtime có artifact mới | Chưa có targeted retest |
| Retest passed | Original/sibling tests phù hợp đạt | Có thể còn fleet gaps |
| Verified Fixed | Evidence+scope/coverage/reviewer đủ | Không tuyên bố toàn system safe |
| Risk Accepted | Residual risk được duyệt riêng | Không biến technical state thành fixed |

### 23.3. Các acceptance criteria chung

- Original weakness không còn tái hiện với preconditions.
- Legitimate behavior vẫn hoạt động (positive controls).
- Negative tests cho roles/tenants/resources trong scope đạt.
- No unauthorized data/queue/storage/vendor side effects.
- Root-cause related paths được xem theo risk.
- Security scanning/baseline tests không còn finding sau khi xác nhận tool healthy.
- Fix nằm trong actual deployed artifact/config.
- Residual unknowns/exceptions được ghi và approved.
- Evidence có tool/run/target/time/provenance.
- Reviewer/owner ký closure theo policy.

### 23.4. Reopen policy phải ghi rõ

- Regression security test fail.
- Old image rollback hoặc active stale instance.
- New privileged route dùng shared weak code.
- WAF/rate limit/security config bị tắt.
- New advisory làm impact assessment đổi.
- Legacy worker mới được phát hiện.
- Supplier update làm mitigation không còn đúng.
- Evidence/FP rationale bị vô hiệu do method/config thay.
- Incident/test phát hiện repeat weakness.

**Closed** không nên làm mất khả năng tìm và xử lý lại finding.

## 24. Retest report và closure addendum

### 24.1. Pentest ban đầu và retest là hai mốc khác nhau

**Original report** phản ánh hệ thống và findings ở một thời điểm. **Retest addendum** nên ghi:
- Retest authorization và scope.
- Fixed/retested target versions và environments.
- Finding IDs từ original report.
- Changes/remediation statements từ owner.
- Exact tests performed; tool/ruleset/version và test window.
- Expected vs actual outcomes, error/skip records.
- Deployment/runtime proof.
- Reviewer và technical status.
- Unverified/excluded paths.
- Residual risks và next actions.

Không âm thầm sửa “High” thành “Resolved” trong bản gốc mà không ghi revision history hoặc trạng thái theo thời gian.

### 24.2. Re-scan khác targeted retest

- **Re-scan:** chạy scanner sau sửa.
- **Targeted retest:** tái kiểm tra hành vi đã tạo finding.
- **Security regression:** kiểm tra variants/sibling paths và không phát sinh lỗi mới.
- **Deployment verification:** fix hiện diện trong đúng image/cluster/region/config.
- **Closure review:** xem evidence và residual risks trước quyết định.

Scanner không còn report do cookie hết hạn hoặc rule disabled không chứng minh remediation.

### 24.3. Retest statuses minh họa

| Status | Điều kiện |
|---|---|
| **VERIFIED_FIXED** | Original finding không còn, test coverage đạt, deploy proof phù hợp |
| **STILL_PRESENT** | Weakness tái hiện trên fixed target |
| **PARTIALLY_FIXED** | Một phần paths/regions/actors còn affected |
| **NOT_RETESTED** | Chưa chạy test |
| **BLOCKED** | Thiếu test account/fixture/permissions |
| **INCONCLUSIVE** | Kết quả nhiễu hoặc không đủ evidence |
| **NOT_APPLICABLE** | Target decommissioned/condition không áp dụng có chứng minh |
| **MITIGATED** | Control tạm hoạt động, root cause có thể còn |
| **RISK_ACCEPTED** | Decision quản trị tách khỏi technical verdict |

### 24.4. Positive/negative/side-effect checks

Một finding BOLA không thể đóng chỉ vì unauthorized request trả 403. Retest cần:
- Unauthorized teacher denied.
- Authorized teacher allowed.
- DB/export job không được tạo trái quyền.
- Worker không tin untrusted queue fields.
- Download URL/storage ownership phù hợp.
- Logs/audit không lộ thông tin.
- Role revoke/async behavior theo approved model.
- Every affected deployment chạy fixed digest.
- Scanner/run khỏe và route coverage đạt.

### 24.5. Production không phù hợp intrusive retest

Nếu ROE không cho pentest toàn production:
- Dùng production-equivalent lab có config/version xác minh.
- Xem build/deploy and effective config proof.
- Chỉ thực hiện limited non-invasive runtime checks được phép.
- Nêu **operating evidence limitations**.
- Không viết “confirmed fixed in production” khi chỉ retest staging và chưa kiểm tra rollout.

## 25. Residual risk, acceptance và exceptions

### 25.1. Một risk có thể được xử lý theo nhiều hướng

- **Remediate:** loại root cause.
- **Mitigate:** giảm likelihood/impact bằng control khác.
- **Transfer/share:** thay đổi trách nhiệm hợp đồng/bảo hiểm không làm risk kỹ thuật mất đi.
- **Accept:** người có thẩm quyền chấp nhận residual risk và conditions.
- **Avoid:** bỏ feature/route/asset, với proof decommission.
- **Investigate:** chưa đủ evidence, không quyết định “safe” giả.

### 25.2. Hồ sơ chấp nhận rủi ro tối thiểu

Một exception/risk acceptance nên có:
- Finding, affected assets và data classification.
- Technical weakness và trạng thái.
- Impact/exploit preconditions và uncertainty.
- Compensating controls đã được kiểm chứng.
- Business rationale và lựa chọn thay thế.
- Risk owner/approver theo policy.
- Scope, expiry/review date và triggers.
- Remediation roadmap hoặc điều kiện kéo dài.
- Legal/contractual obligations khi áp dụng.
- Continuous monitoring requirements.

**Không được coi risk accepted là false positive hoặc verified fixed**, không tự bỏ qua nghĩa vụ phải tuân thủ.

### 25.3. Reporting cho lãnh đạo

Nên có **separate risk decisions list**, với lý do và người chịu trách nhiệm. Nếu ba findings đã mitigated bằng WAF và chấp nhận tới release sau, executive summary vẫn nên nói **ba technical weaknesses còn**, với reduced exposure theo scope được test.

## 26. Traceability: finding → control → test → fix → evidence

### 26.1. Vì sao cần ma trận traceability?

Trong assurance, một pentest chỉ tạo tác dụng dài hạn khi kết quả nối được với:
- Security objectives.
- Threat model/risk scenario.
- Security requirements/controls.
- Dynamic test cases.
- Observed findings.
- Remediation changes.
- Verification and deployed proof.
- Residual risk decision và operating monitoring.

### 26.2. Bảng traceability minh họa

| Control/goal | Test case | Finding | Fix | Retest evidence | State |
|---|---|---|---|---|---|
| Per-object authz for grades | PT-T03 cross-tenant | PT-001 | Object policy API/worker | RETEST-001 + digest check | Pending sample |
| Private report download | PT-T07 unauthorized download | PT-002 | Scoped URL/ACL | RETEST-002 | Pending sample |
| Safe SQL syntax construction | PT-T12 SQL sorting | PT-004 | Server-side allowlist | Query review + DAST | Investigating |
| Scanner route coverage | PT-T30 authenticated crawl | GAP-003 | Update test identities | Coverage report | Pending |
| Audit denial outcome | PT-T19 synthetic denial audit | OBS-004 | Event schema/collector | Trace-to-SIEM test | Planned |

Mọi ID/trạng thái trong bảng chỉ là **minh họa**, không phải chương trình thực đã có results.

### 26.3. “Control exists” khác “control works”

Một policy document yêu cầu authorization là design evidence. Một code review thấy authorization check là implementation evidence. Dynamic tests và production mappings có thể hỗ trợ operating effectiveness trong phạm vi/thời gian. Không dùng một policy PDF làm bằng chứng endpoint thực sự đã deny.

### 26.4. Claim–Argument–Evidence (CAE)

**Claim:**

> Trong phạm vi Learning API export và related report-worker/download flows ở môi trường, artifact digests và kỳ đánh giá xác định, các controls về cross-tenant authorization đã được kiểm tra theo test matrix được phê duyệt; những violations đã ghi PT-001 được tái hiện và chuyển thành remediation plan có owner. Các paths chưa được thử được ghi là limitations, không bao gồm trong kết luận.

**Argument:**
1. Scope/actor/resource mapping có ủy quyền.
2. Test criteria xuất phát từ security policy/threat model.
3. Original evidence đúng actor và target build.
4. Findings được technical triage và review.
5. Risk ratings có business rationale.
6. Remediation addresses root cause và affected population.
7. Retest xác minh behavior và deployment identity khi hoàn tất.
8. Residual gaps/exception được báo với owner.
9. Continuous monitoring gắn với control/asset changes.

**Evidence:** signed engagement scope, test plan, sanitized reproduction, app/DB/worker traces, scanner metadata, source/build/deploy mapping, retest results, risk approvals và reviewer records.

Không được diễn đạt claim đã đạt **nếu retest/evidence còn pending**; report phải phân biệt **kết quả pentest ban đầu** và **bằng chứng sau khắc phục**.

### 26.5. Evidence cho design, implementation và operating effectiveness

| Cấp | Câu hỏi | Evidence chính |
|---|---|---|
| **Design** | Controls được thiết kế đúng threat/business objective? | Requirements, threat model, architecture, policy |
| **Implementation** | Controls được thực thi ở code/config và test target? | Source/config review, integration tests, pentest evidence |
| **Operating** | Controls chạy đúng ở deployed population trong kỳ? | Runtime digests/config, safe probes, logs, repeated monitoring |

Pentest là nguồn evidence mạnh cho **các hành vi đã được thử**, nhưng không tự xác nhận mọi controls vận hành liên tục trên mọi assets.

## 27. Report QA: kiểm tra trước khi phát hành

### 27.1. QA kỹ thuật

Một qualified reviewer cần xác nhận:
- Các findings đã được **technical triage**, không copy scanner alerts thành TP tự động.
- Reproduction/expected/actual phù hợp security requirement.
- Evidence IDs và links tồn tại, đúng artifact/role/time.
- Affected assets, service names và versions chính xác.
- Root cause được đánh dấu confirmed/hypothesis đúng.
- Severity/risk rationale và confidence nhất quán.
- Không có claim vượt test scope.
- Recommendations giải quyết root cause và có acceptance criteria.
- Positive/negative/side-effect tests phù hợp.
- Unknowns và false positives được giải thích.
- Không có severity/metric inconsistencies giữa summary và appendices.
- References CWE/CVE/CVSS đúng đối tượng/phiên bản khi dùng.

### 27.2. QA về quyền truy cập, dữ liệu và trình bày

- Chỉ giữ screenshots có ý nghĩa, đã redact.
- Kiểm tra cả embedded metadata/filename/links có secrets không.
- Không nhúng live passwords/keys/cookies, signed URLs hoặc full PII.
- Access restrictions cho các bản evidence gốc.
- External-facing versions đã được review disclosure scope.
- Header/footer/report classification nhất quán.
- Report ID, issue/revision/version và changelog.
- Contact/escalation và distribution list đúng.
- Nội dung tiếng Việt/thuật ngữ nhất quán, không nhầm “lỗ hổng” với “cảnh báo”.
- Bảng figures và cross-references đúng.
- Appendix không chứa tools payloads nguy hiểm không cần thiết.
- Bảo toàn bản gốc và review history.

### 27.3. Review factual accuracy không đồng nghĩa cho phép bên được test phủ quyết kết quả

Product owner có thể xác minh:
- Tên ứng dụng, asset, business context.
- Deployments/builds và implementation details.
- Severity assumptions.
- Remediation feasibility.
- Test fixture validity.

Nhưng **không nên tự xóa findings đã được xác minh chỉ vì “không muốn báo cáo xấu”**. Nếu hai bên bất đồng, ghi competing interpretation, additional evidence/tests và escalation/reviewer decision theo engagement agreement.

### 27.4. Report sign-off

Một metadata block có thể ghi:
- Prepared by.
- Technical reviewer.
- Security assurance reviewer.
- Business/risk acknowledgment.
- Classification authority.
- Issue date và next scheduled review.
- Delivery receipt/location.

Approval có thể có nghĩa **report được phát hành**, không đồng nghĩa mọi findings đã remediated. Các status phải tách biệt.

## 28. Versioning, redaction và phân phối bảo mật

### 28.1. Report classification

Pentest report có thể tiết lộ:
- Internal topology, ports/routes.
- Security control gaps.
- Credential handling mechanisms.
- Privileged code paths.
- Versions/advisories.
- Exploit conditions và reproduction.
- Screenshots chứa user data.
- Vendor/internal system names.

Vì vậy cần classification (ví dụ Confidential/Restricted theo policy), named recipients, least-privilege access và data retention. **Không mặc định báo cáo được gửi qua chat nhóm, issue tracker công khai hoặc email không bảo mật.**

### 28.2. Phiên bản và changelog

| Version | Ý nghĩa |
|---|---|
| **Draft 0.x** | Chưa review, có thể đổi factual claims |
| **Reviewed 1.0** | Approved original pentest results trong kỳ T |
| **Errata 1.0.x** | Sửa lỗi factual/format với audit trail |
| **Retest addendum R1** | Kết quả kiểm tra sau khắc phục |
| **New engagement 2.0** | Scope/thời kỳ kiểm thử mới, không dùng retest thay tất cả |

Đây là **quy ước minh họa**, có thể thay theo organization. Một errata nên chỉ ra điều đã sửa và vì sao, không ghi đè âm thầm evidence.

### 28.3. External sharing

Nếu báo cáo gửi khách hàng/vendor/assessor:
- Có quyền chia sẻ theo NDA/hợp đồng.
- Cân nhắc bản executive hoặc supplier-specific excerpt thay toàn bộ.
- Scrub PII/secrets/topology không liên quan.
- Preserve technical accuracy và scope.
- Kèm version/test window/known limitations.
- Chọn kênh phát hành có quyền truy cập/audit phù hợp.
- Quy định redisclosure/retention/deletion khi cần.
- Không công bố finding high-impact trước khi liên hệ parties và thực hiện coordinated handling theo policy.

### 28.4. Data lifetime và incident retention

Retention phụ thuộc hợp đồng, quy định, software support lifecycle, incident needs và data sensitivity. Không tự áp số ngày phổ quát. Retest có thể cần evidence cũ để chứng minh thay đổi; incident có thể cần giữ bản gốc theo legal hold. Đồng thời, không nên giữ live tokens/PII vượt mức cần thiết.

## 29. Reporting cho vendor, cloud và third-party scope

### 29.1. Pentest findings ở ranh giới bên thứ ba

Một hệ thống học dùng email/payment/analytics providers có thể tạo finding tại:
- API integration do organization quản lý.
- Supplier product do vendor quản lý.
- Shared configuration/identity boundary.
- Customer tenant settings.
- Supply-chain dependency.

Báo cáo cần nêu **responsibility boundary**. Không tự khẳng định vendor có lỗi vì API của mình gửi dữ liệu sai quyền; cũng không tự cho rằng supplier assertion áp dụng cho mọi phiên bản.

### 29.2. Các yếu tố nên ghi

- Product/vendor name theo classification.
- Actual version/edition/deployment model nếu biết.
- Ownership/control responsibility.
- Điều kiện và phạm vi được phép test.
- Evidence thuộc hệ thống khách hàng hay vendor.
- Supplier report/attestation và thời kỳ.
- Contact/disclosure/incident process.
- Compensating controls phía khách hàng.
- Contractual follow-ups và risk owner.
- Unknowns khi không có vendor implementation evidence.

### 29.3. SaaS opaque architecture

Không có package-level SBOM hoặc source access **không tự chứng minh vendor insecure**. Có thể ghi supplier evidence gap, yêu cầu assurance, contracts, vulnerability disclosure SLAs và customer-side boundary tests theo thẩm quyền. Report không bịa ra packages/attack paths của vendor.

### 29.4. Third-party constraints phải ở executive summary khi material

Nếu một critical workflow phụ thuộc vendor ngoài scope, hạn chế đó có thể ảnh hưởng confidence của cả business security objective. Không giấu trong appendix 200 trang nếu lãnh đạo cần quyết định chấp nhận risk.

## 30. Reporting metrics và dashboard cho pentest

### 30.1. Những metrics có ích

| Metric | Mục tiêu | Giới hạn |
|---|---|---|
| **Unique confirmed findings by priority** | Quan sát remaining technical risk | Severity không bằng business impact |
| **Untriaged/uncertain candidates** | Evidence debt và tiềm năng risk | Không coi Unknown=Low |
| **Risk-weighted coverage** | Những paths critical đã được test? | Weight/rubric cần minh bạch |
| **Test execution outcomes** | Pass/Fail/Blocked/Not Run/Unknown | Plan không bằng executed |
| **Authenticated endpoint coverage** | Thực sự kiểm thử protected routes | 200 login page không đủ |
| **Affected assets per finding** | Remediation blast radius | Một root cause có nhiều instances |
| **Time to triage/verify** | Process effectiveness | Nhanh chưa chắc đúng |
| **Time to deploy fix** | Rollout progress | Merge PR không bằng deployed |
| **Time from deploy to verified retest** | Closure latency | Tool failure không thành pass |
| **Reopened findings** | Regression/rollback detection | Số tăng có thể do observability tốt |
| **Partial remediation backlog** | Assets/paths chưa sửa | Không gộp vào Fixed |
| **Overdue high-risk findings** | Escalation needs | SLA có exceptions riêng |
| **Expired exceptions** | Governance debt | Accepted không phải fixed |
| **Scanner health/coverage** | Độ tin cậy automated evidence | Scanner success không đủ business test |
| **Remediation verified by risk class** | Control-effectiveness tracking | Nêu population/period |
| **Ownerless findings/assets** | Governance/inventory quality | Missing owner không làm risk biến mất |
| **Evidence completeness** | Traceability/provenance | Có link không chứng minh link đúng |
| **Retest failure rate** | Fix quality | Test scope/role cần so sánh |

### 30.2. Dùng mẫu số chính xác

“90% findings đã closed” là mơ hồ nếu:
- Có 100 scanner alerts nhưng chỉ 40 confirmed?
- 30 closed vì false positive?
- 20 risk accepted nhưng chưa fixed?
- 10 duplicate links?
- 15 findings chưa retest?
- Một vulnerability còn ảnh hưởng 200 deployments?
- Có 5 scanner jobs failed?

Nên dùng metrics tách:
- **Confirmed TP → Verified Fixed**.
- **Confirmed TP → Mitigated/Risk Accepted**.
- **Candidate → FP/Unknown/Not Applicable**.
- **Affected instances fixed / total affected instances**.
- **Tested required operations / in-scope required operations**.
- **Scan runs healthy / attempted scans**.

### 30.3. Không so sánh thô pentest này với pentest khác

Pentest A có 10 findings, pentest B có 3 không chứng minh B “an toàn hơn” vì:
- B có scope nhỏ hơn.
- B không có credentials.
- B dành ít thời gian cho business logic.
- A đã test cross-tenant/worker.
- B có WAF chặn scanner.
- Code/runtime architecture khác.
- B có tool/reporting taxonomy khác.

Cần chuẩn hóa **scope, duration, objectives, methods, skill level và test coverage** trước khi so xu hướng.

### 30.4. Nguy cơ KPI sai

Nếu ban lãnh đạo yêu cầu “0 High findings” không quan tâm coverage, team có thể bỏ high-risk scope hoặc relabel severity. Khuyến khích dashboard theo **risk reduction + evidence quality + remediation verification + unknowns** thay vì chỉ số lượng findings thấp.

## 31. Bảng điều phối trách nhiệm (RACI) và sự độc lập

R = Responsible, A = Accountable, C = Consulted, I = Informed; bảng minh họa, không thay phân quyền thực tế.

| Hoạt động | Pentest Team | AppSec/Assurance | Product/Dev Owner | Platform/SRE | Risk/Business Owner |
|---|---|---|---|---|---|
| ROE, scope và test safety | R | A/R | C | C | C |
| Test plan và methodology | A/R | C | C | C | I |
| Thu evidence/reproduction | A/R | C | C | C | I |
| Technical triage/severity | R | A/R | C | C | C |
| Report drafting/QA | R | A/R | C factual | C factual | I |
| Business impact/risk priority | C | R | R | C | A |
| Root-cause remediation | C | C | A/R | R config/deploy | I |
| Production deployment proof | I | C | C | A/R | I |
| Retest và independent closure | R | A/R | C | R deployment | C |
| Risk acceptance/exception | I | C | C | C | A/R |
| Distribution/classification | R | A/R | C | I | C |
| Monitoring/reopen | C | A/R | R application | R runtime | C |

### 31.1. Tách ba loại phê duyệt

- **Approval to test:** authorize engagement, scope, safety.
- **Approval to release report:** technical/quality/privacy review.
- **Approval to accept residual risk:** quyết định governance thuộc đúng Risk Owner.

Chúng **khác nhau**. Reviewer ký phát hành report không tự chấp nhận High vulnerability. Dev owner ký rằng đã merge fix không tự xác nhận pentest closure.

### 31.2. Finding disagreement và escalation

Nếu developer cho rằng finding FP nhưng tester thấy data leak:
1. Cùng xem policy và expected/actual.
2. Kiểm tra actor/resource fixtures.
3. Review anonymized evidence và build/time.
4. Test thêm trong lab được phép.
5. Document rationale hai phía.
6. Escalate to qualified AppSec/risk authority nếu chưa thống nhất.
7. Không bỏ finding khỏi report mà không có decision trail.

## 32. Mẫu YAML quản lý evidence và report metadata

Đây là **record schema minh họa, không phải chuẩn bắt buộc của pentest tools**. Các giá trị là placeholders; chưa có phép thử thật và không được dùng để xác nhận control.

~~~yaml
report:
  report_id: "PT-LEARN-EXAMPLE-2026-01"
  title: "Learning Platform authorized penetration test"
  module: "SECURITY_SECURITY_ASSURANCE"
  classification: "CONFIDENTIAL-EXAMPLE"
  version: "draft-0.1"
  issued_at: "populate-real-issue-time"
  test_period:
    start: "populate-real-start"
    end: "populate-real-end"
  prepared_by: "assign-authorized-tester"
  technical_reviewer: "assign-reviewer"
  distribution: ["authorized-recipients-only"]
engagement:
  authorization_reference: "link-to-approved-ROE"
  scope_reference: "link-to-signed-scope"
  objectives:
    - "Cross-tenant grade confidentiality"
    - "Privileged report export authorization"
    - "Authenticated API and worker paths"
  safety:
    synthetic_data_only: true
    destructive_testing_allowed: false
    production_dos_tests_allowed: false
  known_exclusions:
    - "Legacy batch exporter pending authorization"
    - "Third-party email service"
tested_target:
  service: "learning-api"
  environment: "staging"
  source_revision: "populate-commit"
  image_digest: "populate-image-sha256"
  configuration_reference: "populate-config-id"
  api_spec_version: "populate-openapi-version"
methodology:
  references: ["document-actual-guidance-versions"]
  scan_tools: ["populate-real-tool-and-version"]
  authentication_profiles: ["synthetic-teacher-A", "synthetic-teacher-B"]
  test_cases_executed: ["populate-test-ids"]
  blocked_tests: ["populate-blocked-tests-and-reasons"]
findings:
  - id: "PT-LEARN-001"
    title: "Cross-tenant grade export"
    technical_verdict: "EXAMPLE_NOT_ACTUALLY_TESTED"
    severity: "EXAMPLE_HIGH_NOT_SCORED"
    affected_assets: ["learning-api", "report-worker"]
    business_risk: "Unauthorized access to student grade data"
    original_evidence_refs: ["populate-evidence-id"]
    confidence: "pending-actual-assessment"
    root_cause_status: "hypothesis"
    remediation_owner: "assign-owner"
    remediation_status: "PENDING"
    acceptance_criteria_ref: "link-to-negative-and-positive-tests"
    retest:
      status: "NOT_RUN"
      evidence_refs: []
    residual_risk:
      status: "NOT_DECIDED"
      approver: "assign-authorized-risk-owner"
      expiry: null
evidence_controls:
  storage: "populate-restricted-evidence-location"
  redaction_review: "PENDING"
  retention_policy: "populate-approved-policy"
assurance:
  claim_status: "INSUFFICIENT_EVIDENCE"
  reviewer: "assign-assessor"
  limitations:
    - "Illustrative content, not a live assessment"
  reassess_on:
    - "New authorization-sensitive API route"
    - "Tenant/role/worker policy change"
    - "Image rollback or deployment drift"
    - "Incident or test finding recurrence"
~~~

### 32.1. Mọi phiên bản phải có source of truth

Không nên chỉ lưu YAML ở một folder không có owner. Report control records nên có:
- Immutable reference tới published report version.
- Source/test/evidence IDs.
- Full change history.
- Status transitions.
- Expected vs actual results.
- Linked fixes/PRs/deploy IDs.
- Risk approvals và expiries.
- Restricted access và retention.

### 32.2. Không được biến placeholders thành actual evidence

Các chuỗi “populate...” và “EXAMPLE...” cố ý nhấn mạnh **chưa có kết quả thực**. Khi triển khai, cần thay bằng dữ liệu có kiểm chứng; nếu thiếu, ghi Unknown/Pending thay vì tạo ngày, điểm, versions hoặc test status giả.

## 33. Catalog yêu cầu chất lượng báo cáo pentest

Các mã **PTR-REQ-001…PTR-REQ-030** là **mã minh họa của bài học**, không phải danh mục tiêu chuẩn quốc tế hoặc control ID chính thức. Tổ chức cần định nghĩa actual policy, risk tier, owner và acceptance criteria trước khi áp dụng.

| ID | Yêu cầu | Cách kiểm chứng |
|---|---|---|
| **PTR-REQ-001** | Report có ID/version/issue date/classification | Header và version review |
| **PTR-REQ-002** | Engagement có written authorization | Approved RoE/scope references |
| **PTR-REQ-003** | Test window, target builds/config được ghi | Target identity + timestamps |
| **PTR-REQ-004** | In-scope/out-of-scope assets minh bạch | Service/host/API/region/tenant inventory |
| **PTR-REQ-005** | ROE restrictions và safety được nêu | Allowed/prohibited tests, stop/cleanup records |
| **PTR-REQ-006** | Methodology/tool versions có provenance | Test plan, tool run IDs, rule configs |
| **PTR-REQ-007** | Coverage matrix phân biệt executed/blocked/not run | Actual run evidence và test population |
| **PTR-REQ-008** | Executive summary nêu business risks/decisions | Cross-check với technical findings |
| **PTR-REQ-009** | Findings summary có IDs/owners/states | Referenced detailed records |
| **PTR-REQ-010** | Confirmed finding có expected vs actual | Test oracle/behavior evidence |
| **PTR-REQ-011** | Findings có reproduction an toàn | Given–When–Then, synthetic data |
| **PTR-REQ-012** | Evidence IDs có metadata và access control | Source/time/target/digest, repository QA |
| **PTR-REQ-013** | Reports không lộ tokens/secrets/PII trái policy | Redaction/privacy/security review |
| **PTR-REQ-014** | Severity có rationale/context và score provenance | Impact, preconditions, CVSS vector nếu có |
| **PTR-REQ-015** | Confidence/unknowns được trình bày | TP/FP/Under Investigation taxonomy |
| **PTR-REQ-016** | Root cause là confirmed hay hypothesis rõ ràng | Code/config/test evidence links |
| **PTR-REQ-017** | Recommendations có thể triển khai và đo | Security objective, fixes, acceptance criteria |
| **PTR-REQ-018** | Compensating controls khác permanent remediation | TP/Mitigated/Risk accepted fields |
| **PTR-REQ-019** | Every finding có owner/priority/next action | Tracker links, SLA/escalation |
| **PTR-REQ-020** | Sibling/async paths được đề cập khi liên quan | API/worker/queue/storage tests or explicit gap |
| **PTR-REQ-021** | Report không mở rộng claim ngoài scope | Audit summary vs coverage/exclusions |
| **PTR-REQ-022** | DAST scan health/authorization được chứng minh | Login/session/crawl/error evidence |
| **PTR-REQ-023** | Technical finding và executive stats nhất quán | IDs/count/status cross-check |
| **PTR-REQ-024** | Finding register lưu technical vs remediation status | Status taxonomy và audit trail |
| **PTR-REQ-025** | Retest có fix/deployed-target proof | Commit/build/image/config + result links |
| **PTR-REQ-026** | Closure có reviewer, limits và residual risk | Sign-off và acceptance/reopen triggers |
| **PTR-REQ-027** | Peer QA & factual review có history | Draft/reviewer/changes/changelog |
| **PTR-REQ-028** | Secure distribution/retention/access được quản lý | Named recipients, permissions, archive policy |
| **PTR-REQ-029** | Metrics có population/time/state definitions | Numerator/denominator/exclusions and notes |
| **PTR-REQ-030** | Report nối được security requirements với evidence | CAE/control–test–finding–fix traceability |

### 33.1. Một requirement đầy đủ: PTR-REQ-010

**Statement:** Mọi finding được gắn **CONFIRMED** trong final report phải có expected security requirement, actor/resource/test preconditions, actual result được quan sát, bằng chứng có provenance và scope cụ thể.

**Risk:** một scanner heuristic tạo cảnh báo High nhưng chưa chứng minh violation, gây nhầm ưu tiên và remediation.

**Positive case:** BOLA synthetic test thấy role ngoài quyền tạo export job; record có authorization matrix, request ID, downstream job evidence.

**Negative test:** scanner báo SQLi chỉ từ intermittent 500, thiếu query proof; report phải ghi Needs Validation hoặc technical review thêm, không tự Confirmed.

**Owner:** Pentest lead và AppSec reviewer.

**Evidence:** finding record, original test run, reviewer sign-off và linkage.

### 33.2. Một requirement đầy đủ: PTR-REQ-021

**Statement:** Executive/technical claims không được bao gồm endpoints, regions, roles, vendor components hoặc runtime versions chưa kiểm tra, trừ khi có lập luận và evidence độc lập đủ mạnh cho phép khái quát hóa.

**Acceptance:** khi report kết luận mọi production users an toàn nhưng scan chỉ staging API và bỏ worker/DR region, assurance QA phải flag overclaim, yêu cầu sửa scope, ghi limitations và tạo plan bổ sung.

### 33.3. Một requirement đầy đủ: PTR-REQ-025

**Statement:** Retest addendum không được đánh dấu VERIFIED_FIXED cho finding nếu không có chứng cứ fix ở artifact/deployment trong scope và targeted test trên điều kiện tương ứng.

**Acceptance:** PR merged nhưng image cũ còn chạy → status Partial/Pending; scan tool timeout/401 → Inconclusive; correct fixed digest và positive/negative/side-effect tests đạt → reviewer có thể xác minh closure trong scope.

### 33.4. Requirements không thay kỹ năng đánh giá

Một report có 30 trường đầy đủ vẫn có thể không đúng nếu:
- “Expected” policy bị bịa.
- Scanner test được chạy sai actor.
- Risk score gán không có cơ sở.
- Data leaked thực bị bỏ qua.
- Reviewer ký mà không đọc evidence.
- Runtime đã rollback sang phiên bản khác.

Đo **nội dung/chứng cứ**, không chỉ tick template.

## 34. Ma trận 40 phép kiểm tra chất lượng pentest report

Các mã **PTR-T01…PTR-T40** là kiểm thử **quy trình báo cáo, data quality và assurance**, không phải 40 payload khai thác. Nên chọn theo criticality/report purpose; actual test executions cần được chứng minh bằng evidence.

| Test ID | Kịch bản kiểm tra | Expected |
|---|---|---|
| **PTR-T01** | Report thiếu authorization/ROE reference | Không phát hành như authorized report |
| **PTR-T02** | In-scope host và report target khác nhau | Flag scope/asset discrepancy |
| **PTR-T03** | Test window và report date không rõ | Yêu cầu bổ sung time provenance |
| **PTR-T04** | Artifact version/digest thiếu | Hạn chế claim, bổ sung mapping |
| **PTR-T05** | Endpoint “tested” nhưng không có run evidence | Đánh dấu Not Run/Unknown |
| **PTR-T06** | DAST chỉ crawl login page | Coverage gap, không “no vulnerabilities” |
| **PTR-T07** | Scanner timeout nhưng output zero findings | Tool error, không Pass |
| **PTR-T08** | Finding SQLi dựa duy nhất HTTP 500 | Needs Validation |
| **PTR-T09** | BOLA có actor/resource/tenant matrix và job evidence | Technical TP có supporting proof |
| **PTR-T10** | BOLA request denied nhưng file vẫn tạo | Retest Fail/Partial |
| **PTR-T11** | Positive actor hợp lệ bị trả 503 | Regression/availability issue, không fixed |
| **PTR-T12** | Risk High không có preconditions/impact rationale | Risk review required |
| **PTR-T13** | CVSS có số nhưng thiếu version/vector | Incomplete scoring evidence |
| **PTR-T14** | CWE/CVE được áp nhầm đối tượng | Mapping correction |
| **PTR-T15** | Executive đếm 3 High, appendix chỉ có 2 | Consistency QA fail |
| **PTR-T16** | Duplicate records không có master link | Dedup review, giữ affected paths |
| **PTR-T17** | Finding FP không có technical rationale | Không auto-discard |
| **PTR-T18** | Risk accepted bị ghi “fixed” | Status taxonomy QA fail |
| **PTR-T19** | Scanner 0 alerts nhưng nhiều protected routes 401 | Insufficient coverage |
| **PTR-T20** | Screenshot chứa synthetic token có thể tái dùng | Redact/revoke/handle according policy |
| **PTR-T21** | Raw student grades trong appendix | Data minimization/privacy review fail |
| **PTR-T22** | Evidence ID không truy cập được với reviewer | Evidence completeness gap |
| **PTR-T23** | Evidence timestamp không khớp test period | Investigation, no unsupported claim |
| **PTR-T24** | Screenshot không có actor/target context | Supplement trace/test record |
| **PTR-T25** | Attack chain suy mọi tenants từ một fixture | Observed vs potential distinction |
| **PTR-T26** | Root cause giả định ghi thành “đã xác minh” | Label hypothesis, request source review |
| **PTR-T27** | Proposal “thêm validation” không có acceptance | Actionability QA fail |
| **PTR-T28** | Bản fix đã merge nhưng chưa deploy | Retest status pending |
| **PTR-T29** | Image tag mutable khác digest test | Deployment binding fail |
| **PTR-T30** | Một region vẫn chạy vulnerable image | PARTIALLY_FIXED, không full closure |
| **PTR-T31** | WAF blocks test nhưng code weak | MITIGATED, không FP |
| **PTR-T32** | Rollback sau closure | Reopen trigger/event verified |
| **PTR-T33** | Vendor component ngoài scope nhưng report khẳng định safe | Scope overclaim |
| **PTR-T34** | SaaS không có package SBOM | Supplier evidence gap, không tự bịa package |
| **PTR-T35** | Retest không chạy original reproduction | Not sufficient for verified closure |
| **PTR-T36** | Redacted report và evidence gốc bị ghi đè | Chain-of-custody/change QA fail |
| **PTR-T37** | External sharing không có access approval | Distribution security fail |
| **PTR-T38** | Exception hết hạn còn tính risk mitigated | Governance escalation |
| **PTR-T39** | Dashboard “90% closed” gồm FP/accepted/duplicate | Fix status denominator/semantics |
| **PTR-T40** | New endpoint/role/worker path sau engagement | Trigger new assessment, old report scoped |

### 34.1. Đánh giá độ bao phủ của chính QA

Một report có 40 test cases trong ma trận **không có nghĩa đã chạy 40 tests**. Nên ghi:
- Relevant tests selected.
- Executed / Pass / Fail / Blocked / Not Applicable.
- Reviewer và time.
- Evidence for each result.
- Remediation of QA failures before release.
- Policy-approved exceptions với scope/owner.

### 34.2. Kiểm thử bằng report fixture

Nhóm có thể tạo một **report giả** với những lỗi có chủ ý:
- Scope không nêu staging/production.
- Executive summary ghi số finding sai.
- Một finding “Critical” chỉ có HTTP 500.
- Screenshot chứa synthetic secret.
- Một report đã đóng lỗi dù image chưa deploy.
- Một exception hết hạn.
- 5 routes “tested” không có test runs.
- Reviewer sign-off thiếu.

Cho học viên phát hiện, phân loại, sửa và viết **QA disposition**. Đây là cách huấn luyện khả năng đọc báo cáo như một assessor, không chỉ khả năng viết.

## 35. Mẫu báo cáo pentest rút gọn nhưng có đầy đủ logic

Mọi dữ liệu trong phần này là **giả định phục vụ giảng dạy**, không phải phát hiện của một hệ thống thật.

### 35.1. Cover page

~~~text
Report ID: PT-LEARN-EXAMPLE-01
Title: Báo cáo pentest - Learning Platform
Classification: Confidential - training example
Version: Draft 0.1
Testing window: [Populate actual dates/time zone]
Target: Learning API staging release R, Report Worker release W
Authorized scope: [Reference to approved RoE]
Prepared by: [Authorized testing team]
Reviewed by: [Security assurance reviewer]
Distribution: [Named recipients per policy]
~~~

### 35.2. Executive summary

> Đợt kiểm thử giả định tập trung vào authentication, object-level authorization và xuất dữ liệu điểm học viên giữa hai synthetic tenants. Một finding High minh họa liên quan việc actor Teacher A không được phân công Class B vẫn khởi tạo export job; tác động tiềm năng là lộ dữ liệu điểm qua API–worker–storage. Triage của một cảnh báo SQL injection vẫn chưa đủ bằng chứng để phân loại và không được đếm là confirmed. Những legacy batch operations và third-party services không nằm trong phạm vi đã kiểm tra. Ưu tiên là khắc phục authorization theo quan hệ ở API và worker, kiểm tra file/download scope, triển khai fixed image và retest trong một quy trình có reviewer.

### 35.3. Scope & methodology

- **In scope:** API grade/export operations, synthetic teacher/learner identities, report queue/worker and private storage tại staging; actual route/test list được ghi khi chạy.
- **Excluded:** vendor email service, production destructive tests, legacy batch export chưa được authorize.
- **Methods:** approved authenticated API tests, business-logic negative/positive tests, safe scanner, source/config review nếu được phép, correlation với logs/queue/storage.
- **Constraints:** limited test identities, bounded job execution, no real learner records.
- **Evidence:** tool/test run references, request/response redacted, job/storage correlation IDs.
- **Assessment period:** time bounds cần điền trước phát hành.

### 35.4. Findings summary

| ID | Finding | State | Risk | Action |
|---|---|---|---|---|
| PT-001 | Cross-tenant grade export | Confirmed example | High example | Fix relation-aware authorization |
| PT-002 | Signed URL lifetime | Under investigation | TBD | Verify policy/actual TTL/download scope |
| PT-003 | Suspected SQLi in sorting | Needs validation | TBD | Code/query inspection and lab tests |
| GAP-001 | Legacy batch exporter untested | Evidence gap | Risk review | Assign owner, authorize assessment |

### 35.5. Technical finding PT-001

**Requirement:** actor chỉ tạo/tải report cho class trong phạm vi quyền.

**Preconditions:** synthetic Teacher A, class B outside assignment.

**Expected:** denial, no export job, no data disclosure.

**Observed:** synthetic scenario demonstrates job acceptance for class B (training assumption).

**Evidence needed:** request ID, actor/resource proof, response, job/file assertions, tool/build/time, test log. Không có raw tokens/grades.

**Risk:** confidentiality risk across tenant boundary; không suy số users affected.

**Root-cause hypothesis:** role-only check and worker reliance on queued classId.

**Remediation:** scoped authorization at API and worker, trusted job record, scoped DB access, private report download, audit and tests.

**Retest:** negative actor B, positive assigned teacher, side-effect checks, worker replay/temporal cases when relevant, deployed digest proof.

**Owner:** Learning Backend/Worker, due date theo organizational policy.

**Status:** Open, remediation not yet evidenced.

### 35.6. Assumptions và limitations

- Không có bằng chứng rằng mọi tenants/regions ngoài fixture đã affected.
- Không có bằng chứng production exploit đã xảy ra.
- Legacy export chưa được kiểm tra; không phải “safe”.
- Scanner results chỉ có giá trị với tool/credentials/rules thực đã ghi.
- Retest chưa thực hiện; không ghi “Fixed”.
- Khả năng đọc production evidence phụ thuộc quyền đã được duyệt.

### 35.7. Recommended next steps

1. Assign severity/risk owner và xác nhận asset population.
2. Triage PT-002/PT-003, giữ trạng thái Uncertain cho tới khi đủ evidence.
3. Sửa PT-001 tại API/worker, thêm regression tests.
4. Build/release approved artifact, verify deployed digest.
5. Retest đúng scope/roles và downstream side effects.
6. Record reviewer acceptance hoặc gaps/residual risk.
7. Đánh giá legacy batch exporter khi được cấp quyền.
8. Duy trì monitoring và reopen khi rollback/regression.

### 35.8. Report sign-off

Report reviewer xác nhận **bản báo cáo được chuẩn bị đúng quy trình và phản ánh evidence đã cung cấp**, không có nghĩa tất cả findings đã remediated. Product/Risk Owner nhận báo cáo và giao action; closure/retest dùng quyết định bổ sung.

## 36. Những sai lầm thường gặp khi viết báo cáo pentest

**“Pentest không tìm thấy Critical nên hệ thống an toàn.”** Một kết quả âm tính chỉ có nghĩa không tìm thấy trong scope/method/time, có thể còn unknown assets và false negatives.

**“Càng nhiều CVE/finding thì báo cáo càng tốt.”** Một số lượng lớn scanner alerts không triage dễ gây nhiễu; vài business-critical findings có thể quan trọng hơn hàng trăm low-confidence alerts.

**“Executive summary chỉ cần copy bảng kỹ thuật.”** Lãnh đạo cần hiểu business risk, uncertainty, decision và action owner.

**“Báo cáo dài là báo cáo có bằng chứng mạnh.”** Hình thức không thay test coverage, provenance, accuracy, retest.

**“CVSS score là business risk.”** Context dữ liệu/exposure và controls làm priority thay đổi; version/vector và rationale phải rõ.

**“Tất cả API response 500 là SQL injection.”** Cần verify unsafe query/data flow; parser/network timeout có thể là alternate causes.

**“Không khai thác được một lần nghĩa finding false positive.”** Precondition/role/state/time/coverage có thể thiếu.

**“WAF chặn payload nghĩa source vulnerability đã fix.”** Có thể chỉ mitigated, cần residual risk record.

**“HTTP 403 nghĩa không có unauthorized side effect.”** Queue job/file/email có thể đã tạo trước khi deny.

**“Một response body không có PII nghĩa không có leak.”** Metadata, cache, object storage, logs hoặc worker có thể lộ.

**“Auth login pass nghĩa authorization được kiểm tra.”** Phải có resource relation/tenant/role tests.

**“Methodology có tên OWASP/NIST nghĩa tuân theo toàn bộ framework.”** Nêu đúng mapping, tests executed, versions và limitations.

**“Pentest bao phủ ứng dụng vì scanner crawl được mọi public URLs.”** Protected routes, GraphQL/async/job logic có thể chưa test.

**“Tất cả findings có severity High nên đúng.”** Severity khác technical validity; uncertainty cần giữ riêng.

**“Một PoC đầy đủ phải rút dữ liệu thật.”** Có thể chứng minh bằng synthetic/minimal proof an toàn, theo RoE.

**“Càng nhiều screenshots/raw HTTP logs càng tốt.”** Có thể làm rò secrets, PII hoặc credentials; chỉ giữ evidence cần thiết và kiểm soát access.

**“Dữ liệu staging luôn là giả.”** Cần kiểm tra fixture provenance; staging có thể copy production data.

**“Tôi đã chụp ảnh nên không cần test metadata.”** Screenshot thiếu actor, target, timestamp và route có thể không đủ.

**“Root cause đã biết vì tester đoán.”** Black-box behavior hỗ trợ hypothesis; root cause cần code/config/architectural evidence tương xứng.

**“Một vulnerability ở một tenant chứng minh mọi tenants bị ảnh hưởng.”** Phải tách observed vs potential/unknown và xác định population.

**“Một finding trùng được xóa không cần giữ occurrences.”** Sẽ mất affected paths/owners/tests, dẫn đến closure sai.

**“Không có evidence vendor nghĩa vendor có lỗ hổng.”** Ghi supplier gap và boundary, không bịa technical findings.

**“Fix PR merged nghĩa Verified Fixed.”** Cần build/deploy identity và retest.

**“Scanner không báo sau fix nghĩa all paths fixed.”** Auth/ruleset/target có thể đổi; manual business logic và side effects cần kiểm tra.

**“Rollback không làm tình trạng security thay đổi.”** Old vulnerable artifact có thể tái xuất và trigger reopen.

**“Risk accepted nghĩa không cần report finding.”** Technical weakness vẫn cần record, residual risk, approval và expiry.

**“Report review là risk acceptance.”** Report QA/sign-off và risk owner decision là hai thẩm quyền khác nhau.

**“Mọi finding phải có CVE.”** Nhiều business logic/authorization findings không có CVE riêng.

**“Một weakness trong SCA chứng minh exploitation.”** Advisory matching và product reachability/exposure là các lớp phân tích khác nhau.

**“Một bộ test 40 dòng nghĩa đã chạy 40 test.”** Catalog/plan không phải execution evidence.

**“100% coverage” không có mẫu số.** Nếu thiếu asset inventory hoặc exclusions, tỷ lệ có thể gây hiểu lầm.

**“Bản báo cáo mới nhất thay được lịch sử.”** Cần versioning, original evidence và retest addendum để hiểu thay đổi theo thời gian.

**“Đã fix kỹ thuật nên không cần incident/privacy review.”** Exposure trước khi sửa có thể vẫn phải điều tra theo nghĩa vụ liên quan.

**“Báo cáo chứa toàn bộ reproduction có thể chia sẻ công khai.”** Phải kiểm soát classification, authorized recipients và redaction.

**“Kết quả pentest là giấy chứng nhận bảo mật vĩnh viễn.”** System/threat/deployment thay đổi, cần continuous assurance và test lại theo risk.

## 37. Bài tập thực hành

### Bài tập A — Viết executive summary

Bạn có ba giả định: một finding High về cross-tenant export; hai Medium về signed download và logging; một High-potential candidate chưa đủ evidence. Scope chỉ gồm staging Learning API, test identities và worker, còn legacy batch ngoài scope.

Viết tóm tắt **tối đa hai đoạn** gồm business risk, priorities, limitations, owner/next decision. Không ghi “hệ thống có ba lỗ hổng” nếu candidate chưa verified.

### Bài tập B — Scope và coverage matrix

Một engagement được phép test 40 API operations trong hai services và ba roles. Team đã chạy 30 operations, 5 operations bị blocked do OAuth token hết hạn, 5 chưa chạy; chỉ role Teacher có negative tests. Hãy lập scope/coverage table với mẫu số, test outcomes và limits của kết luận.

### Bài tập C — Chấm severity có rationale

Hai findings: một XSS trong test-only admin page không deploy, một BOLA trên grade export cross-tenant ở API production-equivalent. Chọn technical status và risk priority dựa trên assumptions; không tự đặt numeric CVSS nếu thiếu vector conditions. Ghi điều cần xác minh thêm.

### Bài tập D — BOLA end-to-end

Hệ thống có Learning API, queue, report worker và private storage. Một Teacher A có thể export lớp B ngoài quyền. Viết full technical finding gồm expected/actual, actor/resource fixtures, impact, root cause hypothesis, remediation, test evidence và retest criteria.

### Bài tập E — 403 nhưng queue job vẫn chạy

Sau hotfix, API trả 403 cho unauthorized export nhưng worker tạo file sau vài giây. Báo cáo finding là Fixed, Partially Fixed hay Still Present? Giải thích bằng **downstream evidence**, observation window và owner assignments.

### Bài tập F — SQL injection heuristic

DAST phát hiện HTTP 500 khi query param có ký tự đặc biệt; test có network latency cao. Viết report record với **Needs Validation** và test plan phân biệt parser failure, query construction, WAF và DB behavior. Không đưa payload phá hoại.

### Bài tập G — XSS ở ba contexts

Một user displayName xuất hiện trong HTML text, attribute và inline script ở ba views. Hãy viết ba test cases, encoding requirements, expected results và cách báo observed vs unverified paths.

### Bài tập H — Secrets trong evidence

Một scanner report chứa Authorization header có token còn hiệu lực và screenshot có email/điểm học viên. Đề xuất containment/rotation nếu cần, redaction, evidence vault, distribution controls và event logging. Phân biệt sửa báo cáo với sửa vulnerability gốc.

### Bài tập I — Scope ngoài quyền

Tester tìm thấy linked vendor API endpoint ngoài danh sách được ủy quyền và muốn quét tiếp để chứng minh risk. Viết cách dừng/escalate, cập nhật scope/ROE và ghi limitation mà không tự mở rộng quyền kiểm thử.

### Bài tập J — Retest sau PR merged

Developer merge fix SQLi, scanner staging báo no findings nhưng production vẫn chạy image digest cũ. Viết retest addendum và trạng thái đúng; đề xuất build/deploy proofs và targeted tests.

### Bài tập K — Rollback regression

Một service rollback về vulnerable image do outage. Thiết kế reopen trigger, risk/incident process, actual deployed population review, compensating controls và retest plan.

### Bài tập L — Risk acceptance

Risk Owner muốn accept một High finding trong ba tháng do deadline. Viết risk acceptance record gồm rationale, technical state, scope, data/impact, compensating controls, approver, expiry, monitoring và remediation action. Không đổi status thành FP.

### Bài tập M — CVSS vs business priority

Scanner gắn High severity cho một dependency ở unexposed test-only worker; một business authz issue chưa có CVSS score nhưng ảnh hưởng grade export. Viết cách ưu tiên có context, evidence gaps và vì sao không lấy số CVSS để thay quyết định.

### Bài tập N — Report QA

Một draft có 2 High findings trong appendix nhưng executive summary ghi 4; một screenshot chứa token, một finding không có target version, một retired endpoint được coi là “not applicable” không có proof, và một legacy path bị bỏ khỏi scope mà không ghi. Hãy lập QA defects với severity của lỗi báo cáo, owner và required correction.

### Bài tập O — Traceability và CAE

Lập ma trận **security objective → threat scenario → test → finding → fix → retest → evidence** cho cross-tenant grade export. Viết Claim–Argument–Evidence rõ phiên bản, kỳ và exclusions, không overclaim production chưa test.

### Bài tập P — Tạo YAML metadata

Dùng mẫu YAML của bài, điền dữ liệu giả định nhưng hợp lý. Gắn finding ID với synthetic reproduction, evidence references, remediation owner và retest status. Đảm bảo **PENDING** khi chưa chạy, không giả tạo actual Pass.

### Bài tập Q — Supplier shared responsibility

Một SaaS analytics provider không cung cấp pentest report hoặc package-level BOM; bên sử dụng có thể test customer-side integration. Viết supplier assurance gap, các tests có quyền ở customer boundary, contractual questions, residual risk/owner và limitations.

### Bài tập R — Metrics và mẫu số

Có 120 scanner alerts; 30 confirmed TP, 40 FP, 20 duplicates, 10 Needs Validation và 20 chưa triage. Có 12 confirmed findings đã được sửa code, nhưng chỉ 7 có deployed proof, 5 có targeted retest, 2 có partial rollout. Xây dashboard **không đếm các nhóm giao nhau** hoặc tự suy 5 đã verified. Nêu những con số cần thêm để tính Verified Fixed.

### Bài tập S — Chương trình pentest reporting 90 ngày

Thiết kế 90-day improvement plan:
1. Chọn report template và classification policy.
2. Xây approved RoE/scope registry.
3. Inventory critical services/APIs/roles/tenants.
4. Chuẩn hóa finding taxonomy và risk assessment.
5. Tạo synthetic data và safe reproduction standard.
6. Thiết lập evidence store, redaction và access controls.
7. Định nghĩa review/sign-off theo risk.
8. Kết nối findings tới ticket/asset owners.
9. Thêm deployment digest và retest evidence.
10. Tạo executive dashboard có unknowns và coverage.
11. Diễn tập một BOLA remediation/rollback.
12. Xuất CAE report với limitations/continuous monitoring.

Yêu cầu bài làm có **measurable acceptance criteria, owners và deliverable evidence** cho mỗi giai đoạn.

### Bài tập T — Case study tổng hợp

Một đợt pentest Learning Platform có:
- 22 approved targets, 17 thực sự được test.
- 3 targets có OAuth credentials lỗi, 2 targets bị ROE loại.
- 8 confirmed findings (2 High, 4 Medium, 2 Low).
- 4 suspicious candidates chưa đủ proof.
- 3 High potential findings có overlap với 2 confirmed? Chưa có mapping.
- Một API export finding có 5 affected instances, chỉ 3 đã deploy fix.
- Một report worker ngoài scope chưa được review.
- 2 screenshots chứa synthetic PII có thể nhận diện test users.
- 1 risk accepted exception hết hạn.
- Scanner report mới mất quyền authentication nhưng dashboard ghi no findings.
- Executive summary tuyên bố “toàn hệ thống đã được đánh giá và an toàn”.

Hãy:
1. Viết lại executive claim đúng phạm vi.
2. Xây affected/tested populations với states.
3. Đề xuất technical/evidence/privacy QA findings.
4. Viết action/owner/priority cho 10 việc quan trọng.
5. Thiết kế targeted retest/rollout proof.
6. Tách confirmed/unknown/false positive/risk accepted/partial.
7. Định nghĩa disclosure/distribution approvals.
8. Lập CAE và limits, không suy đã khắc phục hoàn toàn.

## 38. Checklist báo cáo pentest chất lượng

Checklist hỗ trợ kiểm chứng, **không tự chứng nhận hệ thống không có vulnerability**.

### 38.1. Engagement và scope

- [ ] Engagement có written authorization và Rules of Engagement được phê duyệt.
- [ ] Testing period/time zone, report issue version và target build/config rõ.
- [ ] In-scope/out-of-scope assets/services/regions/roles/tenants được liệt kê.
- [ ] Test objectives xuất phát từ security goals/business risks.
- [ ] Allowed/forbidden techniques, rate limits, stop conditions rõ.
- [ ] Third-party/vendor services có ownership/authorization boundary.
- [ ] Data fixtures và account roles được xác minh, không dùng secrets thật tùy tiện.
- [ ] Unknown/unreachable/decommissioned assets có trạng thái/rationale riêng.
- [ ] Test coverage có mẫu số và actual executed paths.
- [ ] Tool errors, auth failures, blocked/not-run tests không thành Pass.

### 38.2. Report và findings

- [ ] Executive summary trình bày business risks, priorities, decisions, limits.
- [ ] Report classification, ID, version và người nhận được quản lý.
- [ ] Summary table khớp detailed finding IDs/states/severity.
- [ ] Technical TP/FP/Unknown/Duplicate/Not Applicable được phân biệt.
- [ ] Severity và priority có context/assumptions, CVSS version/vector khi dùng.
- [ ] Mỗi confirmed finding có expected vs actual security behavior.
- [ ] Reproduction có actor/resource/preconditions/target/time.
- [ ] PoC tối thiểu an toàn, không dựa vào rút dữ liệu thật.
- [ ] Impact có observed/potential/unknown tách rõ.
- [ ] Root cause confirmed/hypothesis được ghi đúng.
- [ ] Affected endpoints/services/versions/instances giữ đủ occurrences.
- [ ] Findings mới từ scan không được tự coi là confirmed.
- [ ] Positive/negative/sibling/async tests được đề cập khi liên quan.
- [ ] Recommendations giải quyết root cause và có test oracle.
- [ ] Technical issue và business incident/privacy obligations không bị gộp.

### 38.3. Evidence và assurance

- [ ] Evidence references có unique IDs, source, collector, timestamps.
- [ ] Scanner/tool versions, rulesets, credential profiles và scan policy có provenance.
- [ ] Evidence được bảo toàn integrity và controlled original/redacted copies.
- [ ] Không có live cookies, keys, tokens, raw student data trong report chia sẻ.
- [ ] Screenshots/logs có actor/target/build context và link tới test run.
- [ ] Methodology references đúng phạm vi/phiên bản, không phóng đại coverage.
- [ ] Có Claim–Argument–Evidence/requirements traceability khi dùng cho assurance.
- [ ] Design/implementation/operating effectiveness được phân biệt.
- [ ] Claim giới hạn theo scope/build/time/roles/regions và evidence có sẵn.
- [ ] Findings/data liên quan third party có supplier evidence boundary rõ.
- [ ] Những điều chưa xác minh có owner/next action.
- [ ] Reviewer/approver có thẩm quyền và report QA/change log đầy đủ.

### 38.4. Remediation, retest và quản trị

- [ ] Findings có owner, risk priority, deadlines theo policy.
- [ ] Containment/mitigation khác permanent remediation và risk acceptance.
- [ ] Accepted risk/exception có authority, scope, review period, expiry.
- [ ] PR/fix linked tới immutable artifact/build/deployment proof.
- [ ] Retest addendum ghi target/time/tool/expected/actual và limitations.
- [ ] Original vulnerability và sibling paths được retest phù hợp.
- [ ] Positive legitimate action vẫn hoạt động sau fix.
- [ ] Unauthorized DB/queue/file/vendor side effects được xem khi liên quan.
- [ ] Actual production fleet/regions/worker images được reconcile trong scope.
- [ ] Partially Fixed/Not Retested/Blocked không thành Verified Fixed.
- [ ] Rollback/regression/new API/incident có reopen triggers.
- [ ] Scan health, asset coverage và remaining findings được monitor.
- [ ] Report distribution/retention và next review được quản lý.
- [ ] Dashboard metrics có population, states, exclusions và period.
- [ ] Không có kết luận “100% secure” khi còn missing evidence hoặc scope gaps.

## 39. Ghi nhớ

1. **Báo cáo pentest là tài liệu evidence-based của một đợt kiểm thử có ủy quyền, mục tiêu và phạm vi xác định**, không phải bản sao scanner logs.
2. **Executive summary** cần diễn giải risk và quyết định nghiệp vụ; **technical findings** cần đủ steps/evidence cho remediation và retest.
3. **Authorization, RoE, safety, target/build identity, scope và exclusions** là phần cấu thành của độ tin cậy báo cáo.
4. **Pentest là quan sát theo thời điểm và phạm vi**, không chứng minh mọi assets/versions đều không có lỗ hổng.
5. Một finding tốt có **requirement, actor/preconditions, expected/actual, safe reproduction, root-cause confidence, evidence, impact, fix, owner và retest criteria**.
6. **Technical validity khác severity/priority/risk acceptance**; true positive, false positive, unknown, mitigated và verified fixed không được dùng thay nhau.
7. **CVSS/CWE/CVE/OWASP** giúp phân loại/chuẩn hóa nhưng không thay business context, code/runtime evidence và thẩm quyền quyết định.
8. **Minimal PoC và protected evidence** tốt hơn dữ liệu thật bị xuất tràn lan; phải bảo vệ secrets/PII, redaction, integrity, retention và quyền truy cập.
9. **Attack narrative** hữu ích khi nhiều boundaries như API → queue → worker → storage, nhưng phải phân biệt observed/potential/unverified.
10. **Remediation** cần giải quyết nguyên nhân, **mitigation** giảm risk, **risk acceptance** là quyết định riêng; tất cả đều có owner và evidence.
11. **Retest không chỉ là scanner xanh**: phải chứng minh fixed artifact được triển khai, targeted negative/positive/side-effect tests đạt và exclusions được khai báo.
12. **Claim–Argument–Evidence** giúp truy vết security requirement → test → finding → fix → verification → residual risk, tách design, implementation và operating effectiveness.
13. **Report QA, versioning và controlled distribution** cần thiết vì báo cáo chứa thông tin nhạy cảm và có thể được nhiều bên dùng để quyết định.
14. **Metrics phải có mẫu số đúng**, tách confirmed/untriaged, fixed/mitigated/accepted và scan healthy/failed; ít findings không đồng nghĩa ít risk.
15. **Continuous assurance sau pentest** yêu cầu remediation tracking, retest, monitoring, asset/credential/role/config changes và reopen khi rollback hoặc phát hiện mới.













