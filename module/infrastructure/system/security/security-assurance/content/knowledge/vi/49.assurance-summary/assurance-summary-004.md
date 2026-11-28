# Checklist audit: kiểm tra Security Assurance dựa trên bằng chứng

**Checklist audit** là danh mục câu hỏi và phép xác minh có cấu trúc, giúp người đánh giá kiểm tra **các yêu cầu bảo mật đã được thiết kế, triển khai và vận hành hiệu quả trong một phạm vi, thời kỳ xác định hay chưa**. Một checklist tốt không dừng ở việc đánh dấu ô “Có/Không”; với mỗi câu hỏi, nó liên kết **tiêu chí áp dụng → đối tượng cần kiểm tra → phương pháp → evidence → kết luận → người chịu trách nhiệm → hành động tiếp theo**.

Bài học thuộc chương **Tổng kết security assurance** trong module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu của module là **xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật**, từ phân tích rủi ro, yêu cầu, security controls đến kiểm thử, audit, xử lý findings và chương trình assurance liên tục trong phát triển/vận hành.

> **Nguyên tắc quan trọng nhất:** Một ô checklist được đánh dấu “PASS” chỉ có giá trị khi có bằng chứng phù hợp, đáng tin cậy, đủ phạm vi và đúng thời gian. **Có chính sách, dashboard xanh, kết quả scan sạch hoặc ticket Done không tự đồng nghĩa control đang hiệu quả.**

Checklist ở đây là **khung thực hành để thiết kế một cuộc audit phù hợp ngữ cảnh**. Nó không thay thế chuẩn mực kiểm toán, nghĩa vụ pháp lý, hợp đồng, chính sách tổ chức hoặc quyết định của auditor có thẩm quyền. Các mã, tình huống, dữ liệu, ngày và ngưỡng trong ví dụ đều là **giả định cho mục đích học tập**.

---

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Thiết lập mục đích, scope, thời kỳ, tiêu chí, mức độ bảo đảm và chủ thể tham gia audit.
2. Chuyển security objectives thành **audit questions** và **test procedures** có thể lặp lại.
3. Sử dụng checklist theo các nhóm governance, risk, inventory, IAM, dữ liệu, hạ tầng, SDLC, logging, incident, recovery và nhà cung cấp.
4. Phân biệt chứng cứ về **thiết kế**, **triển khai** và **hiệu quả vận hành** của security control.
5. Kiểm tra chất lượng bằng chứng: **relevance, sufficiency, completeness, provenance, integrity, timeliness, reliability, independence**.
6. Chọn phương pháp kiểm tra toàn bộ population hoặc sampling; nêu rõ giới hạn suy luận.
7. Phân loại **PASS / FAIL / PARTIAL / UNKNOWN / EXCEPTED / NOT APPLICABLE** mà không làm sai trạng thái kỹ thuật.
8. Lập working papers, ghi findings, root-cause hypothesis, CAP, retest và closure có truy vết.
9. Đưa ra kết luận audit có phạm vi, bằng chứng, phản chứng, residual risk và giới hạn rõ ràng.
10. Dùng kết quả audit để cải thiện chương trình **continuous security assurance**, thay vì chỉ nộp hồ sơ một lần.

## 2. Checklist audit dùng cho quyết định nào?

Một cuộc audit có thể nhằm nhiều mục tiêu khác nhau:

| Mục tiêu | Câu hỏi chính | Ví dụ đầu ra |
|---|---|---|
| **Design assessment** | Control có được thiết kế phù hợp threat và requirement? | Review policy, architecture, control mapping |
| **Implementation assessment** | Thiết kế có được triển khai đúng scope và phiên bản? | Configuration, runtime checks, test evidence |
| **Operating effectiveness** | Control có được thực hiện nhất quán trong kỳ đánh giá? | Event history, samples, reconciliations, workflow records |
| **Compliance audit** | Các tiêu chí pháp lý/hợp đồng/standard áp dụng có được đáp ứng? | Evidence theo từng nghĩa vụ, findings và conclusion |
| **Readiness/internal review** | Tổ chức đã sẵn sàng để được đánh giá hoặc phát hành chưa? | Gap register, remediation roadmap và readiness decision |
| **Follow-up audit** | Các finding trước đây đã được sửa và kiểm chứng? | CAP status, retest, verified closure, unresolved risk |
| **Continuous assurance review** | Bằng chứng còn cập nhật khi hệ thống thay đổi? | Control-monitoring coverage, exceptions, evidence-health trends |

**Không được trộn các mục tiêu mà không công bố rõ.** Ví dụ một readiness review nội bộ phát hiện thiếu evidence không tự trở thành báo cáo chứng nhận tuân thủ; một cuộc kiểm tra cấu hình tại ngày T không chứng minh hiệu quả vận hành xuyên suốt 12 tháng.

### 2.1. Những khái niệm phải phân biệt

- **Audit criteria:** điều kiện bắt buộc dùng để đánh giá, lấy từ policy, standard, contract hoặc quy định có hiệu lực.
- **Audit scope:** đối tượng, môi trường, chức năng, tài sản, thời kỳ và những giới hạn đã thống nhất.
- **Audit procedure:** các bước người đánh giá thực hiện để thu và kiểm tra evidence.
- **Audit evidence:** dữ liệu có nguồn, phương pháp và thời điểm đủ để hỗ trợ kết luận.
- **Audit finding:** sai lệch hoặc vấn đề được mô tả theo criteria, condition, evidence và impact.
- **Audit conclusion:** nhận định từ tổng thể phát hiện/bằng chứng, với giới hạn và thẩm quyền thích hợp.
- **Security assurance:** lập luận có bằng chứng về các mục tiêu bảo mật; audit là một nguồn hỗ trợ, không phải toàn bộ assurance.
- **Risk acceptance:** quyết định quản trị rủi ro có thẩm quyền, không biến lỗi control thành đạt chuẩn kỹ thuật.

## 3. Quy tắc sử dụng checklist: không tick ô khi chưa có căn cứ

Mỗi câu hỏi nên có một **audit test card** tối thiểu:

| Trường | Câu hỏi |
|---|---|
| Check ID | Mã duy nhất để tham chiếu finding và test |
| Objective / requirement | Control/security property cần được chứng minh? |
| Scope & population | Kiểm tra tài sản, quyền, event, change hay dữ liệu nào? |
| Audit period | Kiểm tra tại mốc hay trong cả kỳ? |
| Procedure | Quan sát, inquiry, inspection, reperformance hay technical test nào? |
| Evidence references | Dữ liệu gốc, source, query, run ID, ngày, version? |
| Result | PASS, FAIL, PARTIAL, UNKNOWN, EXCEPTED, NOT APPLICABLE? |
| Impact/priority | Tác động rủi ro nếu không đạt hoặc không có bằng chứng? |
| Owner & response | Ai cung cấp evidence, ai chịu action và quyết định? |
| Finding/exception/CAP | Kết nối vấn đề, risk decision và hạn |
| Reviewer & limitations | Ai kiểm tra lại và phần nào chưa thể kết luận? |

### 3.1. Cách phân loại kết quả

| Trạng thái | Điều kiện sử dụng | Lưu ý |
|---|---|---|
| **PASS** | Đủ bằng chứng phù hợp, đạt criteria trên population và thời kỳ đã ghi | Không suy rộng ra ngoài scope |
| **FAIL** | Có bằng chứng đáng tin cho thấy criteria bắt buộc bị vi phạm | Mở finding, đánh giá tác động và chủ thể xử lý |
| **PARTIAL** | Một phần scope/tiêu chí đã kiểm tra; phần khác chưa đạt hoặc chưa đủ | Phải giải thích từng phần; không biến thành PASS tổng thể |
| **UNKNOWN / NOT DEMONSTRATED** | Không đủ nguồn, thiếu population, lỗi collector hoặc test chưa thực hiện | Không mặc định an toàn hoặc chắc chắn không đạt |
| **EXCEPTED** | Có sai khác với ngoại lệ được phê duyệt đúng scope, thời kỳ và điều kiện | **Không phải PASS của control kỹ thuật** |
| **NOT APPLICABLE** | Requirement không áp dụng theo quy tắc và căn cứ được ghi rõ | Không dùng để né một control khó kiểm tra |
| **PENDING RETEST** | Biện pháp sửa đã thực hiện nhưng chưa xác minh hiệu quả | Không được gắn VERIFIED CLOSED |

**Ví dụ:** 98/100 server đáp ứng encryption baseline, 2 chưa thu được trạng thái vì collector lỗi. Không thể ghi “100% PASS” hoặc tự xác nhận hai server vi phạm. Kết luận đúng là 98 PASS, 2 UNKNOWN; claim bao phủ toàn bộ 100 server **chưa được chứng minh**.

### 3.2. Phân biệt quan sát và suy luận

Một bảng điều khiển hiển thị 0 alert là **quan sát về alert được ghi nhận**, không phải bằng chứng “không có tấn công”. Một file policy đã phê duyệt hỗ trợ **design/requirement evidence**, không chứng minh runtime đã áp dụng. Một báo cáo vulnerability scan không có finding chỉ có ý nghĩa đối với **asset, method, credential, thời điểm, rule coverage** của lần scan đó.

## 4. Lập kế hoạch audit và chốt phạm vi

Trước khi mở checklist kỹ thuật, hãy hoàn thành các kiểm tra sau.

### A — Audit charter và governance

- [ ] **A-01:** Mục tiêu audit được mô tả bằng một câu có thể kiểm chứng, không dùng “kiểm tra toàn bộ bảo mật”.
- [ ] **A-02:** Tiêu chí và nguồn yêu cầu có **mã/phiên bản** (policy, control framework, contract, luật áp dụng nếu có).
- [ ] **A-03:** Audit period gồm ngày bắt đầu/kết thúc, múi giờ và khoảng quan sát; phân biệt point-in-time với operating period.
- [ ] **A-04:** Phạm vi tổ chức, business process, service, account, region, tenant và data classification được nêu rõ.
- [ ] **A-05:** Out-of-scope và các phụ thuộc nằm ngoài phạm vi được ghi nhận kèm **hạn chế đối với kết luận**.
- [ ] **A-06:** Audit owner, auditor/reviewer, control owners, service owners và risk authority có tên vai trò và đầu mối.
- [ ] **A-07:** Năng lực, quyền truy cập, tính độc lập và xung đột lợi ích của người đánh giá được xem xét phù hợp nhiệm vụ.
- [ ] **A-08:** Phương pháp thu evidence, sampling, kiểm thử kỹ thuật và quyền thực hiện được thống nhất trước fieldwork.
- [ ] **A-09:** Quy tắc phân loại finding, severity/priority, deadline phản hồi và escalation đã được phê duyệt.
- [ ] **A-10:** Có kế hoạch bảo vệ evidence nhạy cảm, lưu giữ, truy cập, redaction và xử lý dữ liệu cá nhân.
- [ ] **A-11:** Có lịch trao đổi với chủ thể được đánh giá, cách xác minh facts, xử lý disagreement và sign-off.
- [ ] **A-12:** Audit scope và control matrix được review theo rủi ro trước khi thu nhiều dữ liệu.

**Evidence gợi ý:** audit charter, scope statement, criteria register, audit plan, role/delegation record, access authorization, fieldwork schedule. **Điểm chặn:** nếu chưa biết phải kiểm tra asset nào, người đánh giá chưa thể khẳng định population bao phủ đủ.

### 4.1. Mẫu scope statement

> **Audit ID AUD-EX-04** đánh giá hiệu quả vận hành của IAM privileged access, security logging, vulnerability remediation và change approval đối với dịch vụ **OrdersHub** tại hai production regions trong kỳ 01/07–30/09/2026. Các control được đánh giá theo policy nội bộ phiên bản đã liệt kê; kết luận chỉ áp dụng cho dịch vụ, account, asset population và thời kỳ đã xác minh. Các dịch vụ của bên thứ ba không có quyền kiểm tra trực tiếp sẽ được đánh giá qua trách nhiệm được phân chia và evidence có giới hạn, không mặc nhiên được xem là đạt.

Tên dịch vụ, mã và thời kỳ là dữ liệu giả định, không phải một phạm vi audit thực.

## 5. Đối chiếu inventory trước khi kết luận coverage

Một control có thể hoạt động trên mọi asset **được biết đến** mà vẫn bỏ sót tài sản không được đăng ký. Vì vậy inventory là một trong những kiểm tra ưu tiên cao.

### B — Asset, identity và population

- [ ] **B-01:** Danh mục production services được đối chiếu với runtime/deployment inventory.
- [ ] **B-02:** Cloud accounts/projects/subscriptions, regions và DR environments thuộc phạm vi được liệt kê đầy đủ.
- [ ] **B-03:** Resource mới, bị xóa, autoscaling hoặc không có tag vẫn được xem xét đúng kỳ.
- [ ] **B-04:** Danh mục human identities, service identities, privileged roles và break-glass paths phù hợp requirement.
- [ ] **B-05:** Data stores, APIs, batch/worker flows và third-party integrations có owner và phân loại dữ liệu.
- [ ] **B-06:** Có phương pháp đối chiếu **nguồn inventory độc lập** hoặc reconciliation phù hợp.
- [ ] **B-07:** Công cụ scan/collector có quyền đọc mọi account/resource cần kiểm tra; lỗi quyền, pagination, rate limit được xử lý.
- [ ] **B-08:** Có số lượng **expected, observed, missing, excluded** cho population của từng control.
- [ ] **B-09:** Quy tắc chọn sampling unit và kích thước mẫu được ghi cùng mục đích.
- [ ] **B-10:** Asset thiếu owner hoặc owner không còn hiệu lực được ghi là governance gap, không bị ẩn bằng tên nhóm chung.
- [ ] **B-11:** Có đối chiếu thay đổi inventory trong kỳ, không chỉ snapshot cuối kỳ.
- [ ] **B-12:** Phần chưa được thu thập được ghi **UNKNOWN**, có evidence owner chịu trách nhiệm khắc phục.

**Test gợi ý:** so số account trong cloud organization với CSPM, đối chiếu CI/CD và service catalog, lấy mẫu runtime service, đối chiếu IdP với IAM roles. **Không nên chỉ tin một export** nếu chính export đó có thể thiếu tài sản.

## 6. Mapping từ risk và policy đến security controls

Mọi dòng checklist phải có **lý do tồn tại**. Tổ chức cần biết control xử lý rủi ro nào và thế nào là đạt.

### C — Risk, requirements và control design

- [ ] **C-01:** Có security objectives cụ thể cho confidentiality, integrity, availability, authentication, authorization và các thuộc tính áp dụng.
- [ ] **C-02:** Risk register ghi threat/failure scenarios, tài sản, owner, tác động, likelihood hoặc phương pháp rủi ro được duyệt.
- [ ] **C-03:** Security requirements được xác định từ risk, chính sách và nghĩa vụ áp dụng; có phiên bản và owner.
- [ ] **C-04:** Control catalog ánh xạ **requirement → control → implementation → test/evidence**.
- [ ] **C-05:** Control objective và PASS/FAIL criteria có thể kiểm chứng, không chỉ mô tả “đảm bảo an toàn”.
- [ ] **C-06:** Threat model/data-flow và trust boundaries đã được review; thay đổi mới có delta assessment khi cần.
- [ ] **C-07:** Đã phân biệt preventive, detective, corrective controls và kiểm tra không dựa duy nhất vào một lớp.
- [ ] **C-08:** Shared controls có trách nhiệm giữa application, platform, identity, logging và nhà cung cấp rõ ràng.
- [ ] **C-09:** Mức rủi ro còn lại, giả định, dependency và giới hạn control có chủ thể quản trị.
- [ ] **C-10:** Có phương thức ghi những control không áp dụng và căn cứ, tránh tự động tạo ngoại lệ không cần thiết.
- [ ] **C-11:** Policy/control thay đổi giữa kỳ được version hóa, đánh giá tác động và cập nhật audit criteria.
- [ ] **C-12:** Reviewer có thể lần theo từng claim tới ít nhất một bằng chứng phù hợp, thay vì chỉ đường link trống.

**Lưu ý:** nếu control mapping chỉ được tạo bằng cách liên kết ngẫu nhiên một báo cáo scanner tới mọi yêu cầu, chương trình đang mắc anti-pattern **thu thập evidence hình thức**.

## 7. Checklist IAM, xác thực và phân quyền

### D — Identity and Access Management

- [ ] **D-01:** Quy trình joiner–mover–leaver có owner, thời hạn và bằng chứng cấp/đổi/thu hồi quyền.
- [ ] **D-02:** Cấp quyền dựa trên nhu cầu công việc, approval hợp lệ và nguyên tắc least privilege.
- [ ] **D-03:** Human privileged access thuộc scope dùng cơ chế xác thực mạnh theo requirement; kiểm tra cả đường thay thế.
- [ ] **D-04:** Human, service và emergency identities được phân loại riêng; không áp dụng tiêu chí MFA của human một cách máy móc cho machine identities.
- [ ] **D-05:** Direct grants, nested groups, inherited roles và quyền trên shared resources được xét khi kiểm tra quyền thực tế.
- [ ] **D-06:** Quyền admin/break-glass có điều kiện kích hoạt, log, thời hạn và review sau sử dụng.
- [ ] **D-07:** Access review có **population đầy đủ**, reviewer đúng quyền, quyết định và bằng chứng thực thi thu hồi.
- [ ] **D-08:** Service principals/workload identities có scope, rotation/credential management và monitoring phù hợp.
- [ ] **D-09:** Session/token validation bao gồm chữ ký, audience, expiry, revocation và trust boundaries áp dụng.
- [ ] **D-10:** Backend enforce tenant-/object-level authorization, không tin dữ liệu identity do client tự khai báo.
- [ ] **D-11:** Các đường API/worker/export/download và support tooling không tạo bypass ngoài gateway.
- [ ] **D-12:** Có **positive và negative tests** cho role hợp lệ, role bị từ chối, cross-tenant và quyền bị thu hồi.
- [ ] **D-13:** Privileged actions và thay đổi IAM được ghi audit event với source coverage.
- [ ] **D-14:** Finding IAM được sửa và retest trên đúng môi trường/đường truy cập.

**Evidence gợi ý:** role matrix, policy diff, IdP config, runtime access tests, role membership snapshots, joiner–leaver tickets, approval logs, negative tests và exception register.

**Phản biện cần thử:** một UI ẩn nút Export không chứng minh API backend chặn truy cập trái quyền. Một screenshot “MFA enabled” không chứng minh tài khoản emergency hoặc phương thức đăng nhập phụ đã được bao phủ.

## 8. Checklist dữ liệu, quyền riêng tư và mật mã

### E — Data Protection, Privacy và Cryptographic Controls

- [ ] **E-01:** Có data inventory, owner, classification và bản đồ luồng dữ liệu cho hệ thống trong scope.
- [ ] **E-02:** Có căn cứ và giới hạn mục đích xử lý/thu thập/chia sẻ dữ liệu theo yêu cầu áp dụng.
- [ ] **E-03:** Quyền truy cập dữ liệu và export được cưỡng chế tại đúng trust boundary, có negative tests.
- [ ] **E-04:** Dữ liệu nhạy cảm được bảo vệ khi truyền theo cấu hình/protocol đã phê duyệt; không bỏ qua đường nội bộ quan trọng.
- [ ] **E-05:** Mã hóa at rest và quyền dùng khóa được xác minh trên storage, database, backups và replicas thuộc scope.
- [ ] **E-06:** KMS keys có owner, phạm vi quyền, luồng rotate/revoke và cơ chế phục hồi thích hợp.
- [ ] **E-07:** Secrets không bị đưa vào source repository, CI logs, container image hoặc hồ sơ audit chia sẻ rộng.
- [ ] **E-08:** Log và telemetry không ghi dữ liệu nhạy cảm ngoài yêu cầu; có masking/minimization.
- [ ] **E-09:** Retention, deletion, export artifacts và backup lifecycle có tiêu chí và evidence vận hành.
- [ ] **E-10:** Dữ liệu gửi nhà cung cấp/bên thứ ba được kiểm soát bằng hợp đồng, cấu hình và access evidence phù hợp.
- [ ] **E-11:** Quy trình xử lý yêu cầu liên quan dữ liệu cá nhân hoặc quyền riêng tư được phân vai và theo dõi theo nghĩa vụ áp dụng.
- [ ] **E-12:** Có thử decrypt/restore hoặc key dependency khi một thay đổi crypto có thể ảnh hưởng khả năng phục hồi.
- [ ] **E-13:** Không có giả định “storage private” chỉ từ một region snapshot khi claim áp dụng toàn môi trường.
- [ ] **E-14:** Có phản ứng và assessment khi dữ liệu có thể bị lộ, không kết luận vô hại chỉ vì cấu hình hiện đã sửa.

**Evidence gợi ý:** data-flow, classification decisions, IAM/KMS policy exports, TLS configuration review, lifecycle config, authorized negative tests, backup restore result, privacy workflow.

## 9. Checklist kiến trúc, cloud, network và cấu hình

### F — Infrastructure and Security Architecture

- [ ] **F-01:** Kiến trúc và trust boundaries phản ánh runtime hiện tại, không chỉ sơ đồ phiên bản đầu.
- [ ] **F-02:** Internet exposure, ingress/egress, API gateways và network segments có baseline được phê duyệt.
- [ ] **F-03:** Các cổng/dịch vụ quản trị không mở ngoài phạm vi đã đánh giá, kể cả đường hỗ trợ khẩn cấp.
- [ ] **F-04:** IaC, image, container, host và cloud config có security baseline, owner và version.
- [ ] **F-05:** Policy-as-code/admission có test trường hợp hợp lệ và vi phạm; có cơ chế phát hiện bypass.
- [ ] **F-06:** Runtime configuration được đối chiếu với baseline và lịch sử change; drift được xử lý.
- [ ] **F-07:** Cloud account/region mới tự động hoặc theo quy trình được đưa vào monitoring/inventory.
- [ ] **F-08:** Container/workload identities, runtime privileges và isolation được kiểm tra theo rủi ro.
- [ ] **F-09:** Endpoint/host hardening và patch management có evidence đúng tài sản thuộc population.
- [ ] **F-10:** Storage/network/IAM policies có positive/negative test khi thay đổi trust boundary.
- [ ] **F-11:** Infrastructure changes và vendor-managed dependencies có owner và evidence phân chia trách nhiệm.
- [ ] **F-12:** Có kiểm tra shared services như DNS, IdP, KMS, CI runners và khả năng common-mode failure.
- [ ] **F-13:** Các trường hợp ngoại lệ baseline có đúng phạm vi, thời hạn và compensating control được chứng minh.
- [ ] **F-14:** Những finding cấu hình đã được sửa không chỉ ở repo mà ở đúng runtime/DR targets.

**Evidence gợi ý:** architecture diff, IaC review, cloud config snapshots và change history, runtime asset checks, network policy tests, CSPM coverage, hardening assessments.

## 10. Checklist SDLC, change và release assurance

### G — Secure Development and Release

- [ ] **G-01:** Có yêu cầu bảo mật và abuse cases cho tính năng có ảnh hưởng dữ liệu/quyền/trust boundary.
- [ ] **G-02:** Threat modeling/delta threat review được cập nhật cho thay đổi có ảnh hưởng trọng yếu.
- [ ] **G-03:** Code review và approval có bằng chứng phù hợp rủi ro, không chỉ dấu “merge”.
- [ ] **G-04:** Dependencies, artifacts, images và build pipeline được kiểm tra nguồn/provenance ở mức cần thiết.
- [ ] **G-05:** SAST, dependency/config scans có scope, version, rule settings, exception và limitations.
- [ ] **G-06:** DAST hoặc security testing có phép thử theo kịch bản, phạm vi/authorization rõ.
- [ ] **G-07:** Unit/integration/security regression bao gồm **positive, negative và critical edge cases**.
- [ ] **G-08:** CI/CD gates không bị bypass trái quy trình; emergency bypass có log, thẩm quyền và review.
- [ ] **G-09:** Change risk xét impact, asset, data, IAM, shared dependencies, blast radius và rollback.
- [ ] **G-10:** Release risk xét **rủi ro tương tác giữa nhiều thay đổi**, mixed-version và dependency.
- [ ] **G-11:** Release manifest, build digest và candidate được gắn với kết quả test và approval.
- [ ] **G-12:** Kết quả test candidate cũ không tự được dùng cho candidate mới khi có thay đổi liên quan.
- [ ] **G-13:** Rollout/canary, feature flags, guardrails và stop conditions được xác định theo risk scenario.
- [ ] **G-14:** Rollback/forward fix đã xét an toàn dữ liệu, key, IAM và compatibility, không chỉ có script.
- [ ] **G-15:** Post-release verification kiểm tra runtime version/config trên các region/account trong scope.
- [ ] **G-16:** Có phân biệt “deployed”, “technically healthy”, “security verified”, “accepted” và “closed”.
- [ ] **G-17:** Những blocker chưa xử lý có quyết định GO/NO-GO đúng thẩm quyền, không tự được miễn do deadline.

**Evidence gợi ý:** change/release records, review histories, threat models, test reports, artifact digests, SBOM khi phù hợp, pipeline configuration, deployment logs, canary metrics, rollback rehearsal, post-release reviewer decisions.

**Anti-pattern:** số lượng unit tests PASS không chứng minh authorization, data migration, logging và DR đều đạt.

## 11. Checklist vulnerability management, kiểm thử và xác minh phát hiện

### H — Vulnerability, Testing and Remediation

- [ ] **H-01:** Tài sản cần vulnerability assessment được xác định từ inventory và criticality.
- [ ] **H-02:** Scan có quyền, target, version, credential và scope được xác minh; ghi tài sản không được scan.
- [ ] **H-03:** Phát hiện được triage theo ngữ cảnh khai thác, data exposure, blast radius và security requirements.
- [ ] **H-04:** Có phân biệt false positive được xác minh với rủi ro chưa đủ bằng chứng.
- [ ] **H-05:** Penetration test hoặc kiểm thử có authorization, scope, rules of engagement và quản lý dữ liệu an toàn.
- [ ] **H-06:** Các finding có criteria, condition, evidence, impact, owner, severity/priority và lifecycle status.
- [ ] **H-07:** CAP xử lý root cause thích hợp, không chỉ làm biến mất một biểu hiện.
- [ ] **H-08:** Deadline/CAP milestones phù hợp risk policy và được theo dõi khi quá hạn.
- [ ] **H-09:** Compensating controls trong thời gian sửa có design, deployment và operating evidence.
- [ ] **H-10:** Retest trên đúng artifact, environment và **toàn population bị ảnh hưởng** được chứng minh.
- [ ] **H-11:** Negative tests xác nhận lỗi không còn tái hiện; positive/regression tests bảo vệ luồng hợp lệ.
- [ ] **H-12:** Finding chỉ được đóng khi closure criteria đạt và có reviewer phù hợp.
- [ ] **H-13:** Các trường hợp “không tái hiện” được phân tích về môi trường, quyền, dữ liệu, scope; không tự xem là fixed.
- [ ] **H-14:** Finding tái diễn hoặc xuất hiện ở release khác có liên kết root-cause và assurance review.
- [ ] **H-15:** Có lịch sử phát hiện, thời kỳ ảnh hưởng và evidence thất bại, không xóa vì dashboard sau sửa đã xanh.

**Evidence gợi ý:** scan manifests, raw findings, permission/credential diagnostics, signed test report, ticket history, code/config diff, deployment record, retest output, independent review.

## 12. Checklist security logging, detection và incident response

### I — Logging, Detection and Incident

- [ ] **I-01:** Sự kiện bắt buộc theo control được định nghĩa: authn, privileged access, configuration change, export/download, security action.
- [ ] **I-02:** Có danh mục tất cả **expected log sources** theo account/region/service và owner.
- [ ] **I-03:** Audit event chứa đủ actor, action, object, outcome, timestamp và correlation theo nhu cầu, không lộ secret.
- [ ] **I-04:** Có bằng chứng source-to-destination ingestion, không chỉ app ghi log tại nguồn.
- [ ] **I-05:** Parser/normalization hoạt động với schema mới và không làm mất trường trọng yếu.
- [ ] **I-06:** SIEM/detection rules được kiểm thử bằng event hợp lệ/vi phạm phù hợp phạm vi an toàn.
- [ ] **I-07:** Pipeline health có heartbeat, lag, dropped events, retry và cảnh báo khi mất nguồn.
- [ ] **I-08:** Retention, integrity, access control và khả năng tìm kiếm log theo yêu cầu được xác minh.
- [ ] **I-09:** Độ đồng bộ thời gian/timezone và sự khác biệt giữa event time và ingestion time được xét.
- [ ] **I-10:** Alert có triage owner, mức ưu tiên, SLA/escalation và bằng chứng phản ứng.
- [ ] **I-11:** Incident response plan có vai trò, runbook, diễn tập và cơ chế ghi bài học.
- [ ] **I-12:** Các incident trong kỳ có điều tra, containment, recovery, root-cause/CAP và quyết định liên quan.
- [ ] **I-13:** Khi log mất 12 giờ, kỳ đó được ghi **historical evidence gap**, không biến thành PASS sau khi pipeline hồi phục.
- [ ] **I-14:** Threat/detection coverage được xem lại sau release, thay đổi log schema hoặc incident mới.

**Evidence gợi ý:** taxonomy, source inventory, collector status, synthetic event test, raw log, parser version, alert test, incident timeline, IR tabletop/exercise records.

**Cảnh báo:** dashboard ghi “0 security incidents” có thể phản ánh thiếu nguồn hay thiếu detection. Audit phải kiểm tra **khả năng quan sát** trước khi diễn giải số 0.

## 13. Checklist business continuity, backup và disaster recovery

### J — Resilience and Recovery Assurance

- [ ] **J-01:** Business Impact Analysis (BIA) và dịch vụ quan trọng có owner, dependencies và kịch bản phù hợp.
- [ ] **J-02:** RTO/RPO và recovery requirements được xác nhận bởi đúng business owner/authority.
- [ ] **J-03:** Backup jobs, schedules, retention, dữ liệu và vị trí lưu được kiểm tra theo scope.
- [ ] **J-04:** Backup có security controls: encryption, access, immutability hoặc bảo vệ theo requirement.
- [ ] **J-05:** Có **restore test** kiểm tra dữ liệu, ứng dụng, IAM/KMS và tính nhất quán, không chỉ backup job success.
- [ ] **J-06:** Failover/failback dependencies, DNS, credentials, keys và vendor services được kiểm tra theo kịch bản.
- [ ] **J-07:** DR site/artifacts/config không bỏ sót khi release thay schema, signing keys hoặc API contract.
- [ ] **J-08:** Rehearsal đo thời gian và dữ liệu theo kịch bản, điều kiện môi trường và limitations.
- [ ] **J-09:** Các sai lệch so với recovery objectives có finding/CAP, owner, hạn và retest.
- [ ] **J-10:** Thử nghiệm phục hồi được bảo đảm an toàn, không gây ảnh hưởng ngoài phạm vi được phép.
- [ ] **J-11:** Continuity plan có communication, escalation và vai trò khi hệ thống thực bị gián đoạn.
- [ ] **J-12:** Các thay đổi trọng yếu kích hoạt review lại khả năng phục hồi và evidence.

**Evidence gợi ý:** BIA, RTO/RPO approvals, backup reports, restore logs, key compatibility tests, DR exercise results, CAP/retest. Một RTO giả định không được chấp nhận như chuẩn phổ quát; phải dùng mục tiêu nghiệp vụ được duyệt.

## 14. Checklist third-party và shared responsibility

### K — Vendor, Cloud and External Services

- [ ] **K-01:** Vendor/third-party inventory có dịch vụ, dữ liệu, owner nội bộ và mức quan trọng.
- [ ] **K-02:** Shared responsibility được mô tả theo sản phẩm/dịch vụ/hợp đồng, không dùng một mô hình chung cho mọi provider.
- [ ] **K-03:** Security requirements về dữ liệu, incident notification, access, retention, subcontractors và audit rights đã được xác định khi áp dụng.
- [ ] **K-04:** Vendor evidence có scope, thời kỳ, exceptions, reviewer và điều kiện sử dụng rõ ràng.
- [ ] **K-05:** Certification/audit report của vendor không tự được coi là evidence cho cấu hình khách hàng.
- [ ] **K-06:** Quyền IAM, secrets, APIs và data transfers giữa hệ thống khách hàng và vendor được kiểm tra.
- [ ] **K-07:** Dependency availability và concentration/common-mode risk được xem xét.
- [ ] **K-08:** Có người trong tổ chức chịu trách nhiệm theo dõi findings, risk acceptance và review sau khi vendor thay đổi.
- [ ] **K-09:** Vendor evidence thiếu hoặc bị giới hạn được ghi UNKNOWN/limitation, không tự PASS theo danh tiếng nhà cung cấp.
- [ ] **K-10:** Exit/transition plan và quản lý dữ liệu sau khi kết thúc hợp đồng được xem xét khi có yêu cầu.

**Evidence gợi ý:** vendor register, security assessment, contracts, assurance reports, data-flow, shared responsibility matrix, integration tests, tickets và exception records.

## 15. Checklist chất lượng bằng chứng và audit trail

Một checklist có nhiều dòng PASS vẫn không đáng tin nếu evidence bị mất nguồn, quá cũ hoặc không đúng phiên bản.

### L — Evidence quality và provenance

- [ ] **L-01:** Mỗi claim có criteria, scope, kỳ đánh giá và evidence refs liên quan trực tiếp.
- [ ] **L-02:** Raw evidence được giữ hoặc có thể truy xuất, không chỉ bản tổng hợp đã lọc.
- [ ] **L-03:** Dữ liệu có source system, collection method, query/tool version, run ID và UTC timestamp.
- [ ] **L-04:** Có kiểm tra nguồn đủ tài sản, tài khoản, quyền, region, endpoint và event types trong population.
- [ ] **L-05:** Collector có health/permission/lag monitoring; lỗi API, rate limit và pagination không bị che.
- [ ] **L-06:** Source data và report đúng release/build/config với claim đánh giá.
- [ ] **L-07:** Nếu kết luận cả kỳ, có evidence theo thời gian hoặc phương pháp sampling được giải thích.
- [ ] **L-08:** Có kiểm tra accuracy của query/rule với positive/negative fixtures và peer review.
- [ ] **L-09:** Evidence transformations, filters, redactions và exclusions được lưu, không bỏ dữ liệu trái kết luận.
- [ ] **L-10:** Integrity/retention/access control cho evidence được kiểm tra theo mức nhạy cảm.
- [ ] **L-11:** Các nguồn dùng để cross-check có thực sự độc lập hoặc điểm lỗi chung được nêu rõ.
- [ ] **L-12:** Findings, test FAIL và counterevidence được giữ trong hồ sơ, không chỉ những lần chạy PASS.
- [ ] **L-13:** Evidence có owner và reviewer, cùng limitations/uncertainty rõ.
- [ ] **L-14:** Có triggers làm evidence mất hiệu lực: change, release, new account, incident, rule defect, threat mới.
- [ ] **L-15:** Evidence gap được gán action với deadline, không bị coi là “not applicable” thiếu căn cứ.
- [ ] **L-16:** Report dùng references và redacted summary; không phát tán secret hoặc dữ liệu khách hàng không cần thiết.

### 15.1. Ví dụ câu hỏi phản biện

Một báo cáo nói “mọi object storage private” dựa trên 80 tài sản được scan. Hãy hỏi: **có bao nhiêu storage resource trong inventory độc lập, có account/region mới không, trạng thái ngoài giờ quét thế nào, object-level policy có được xét và scan có bỏ resource không có tag không?**

Nếu không biết các thông tin này, một con số 80/80 PASS **chưa đủ** cho claim về mọi storage.

### 15.2. Khác biệt giữa integrity và accuracy

Checksum/hash có thể hỗ trợ xác nhận file không thay đổi kể từ khi ghi. Nó **không** chứng minh collector đã lấy đúng dữ liệu hoặc report không bỏ sót một cloud account. Cần đánh giá **cả nguồn và quá trình thu thập**, không chỉ file cuối.

## 16. Checklist working papers và phương pháp chọn mẫu

Working papers là dấu vết để người khác **tái hiểu**, kiểm tra lại hoặc phản biện một kết luận audit.

### M — Fieldwork và sampling

- [ ] **M-01:** Có working paper ID, audit check ID, requirement và mục tiêu phép thử.
- [ ] **M-02:** Population có nguồn, thời điểm xây dựng, tổng số và đơn vị lấy mẫu.
- [ ] **M-03:** Phương pháp sampling được mô tả: toàn bộ, random, stratified, risk-based hoặc judgmental.
- [ ] **M-04:** Sample size được giải thích phù hợp mục tiêu; có nhóm high-risk khi cần.
- [ ] **M-05:** Không suy rộng thống kê từ mẫu judgmental như thể được chọn ngẫu nhiên.
- [ ] **M-06:** Test procedure có expected/actual, phương pháp, source và người thực hiện.
- [ ] **M-07:** Inquiry với nhân viên được corroborate bằng record khi cần, không coi lời xác nhận là evidence duy nhất.
- [ ] **M-08:** Mọi exception, test FAIL và missing item trong mẫu được ghi cùng cách follow-up.
- [ ] **M-09:** Có cross-reference từ working paper đến finding, CAP và conclusion.
- [ ] **M-10:** Reviewer ghi review notes, ngày, lý do chấp nhận/challenged và công việc còn lại.
- [ ] **M-11:** Kết quả có scope và limitations; không từ 20 mẫu suy chắc toàn bộ 20.000 đối tượng đạt.
- [ ] **M-12:** Có cơ chế bảo vệ working papers, quyền chia sẻ và lưu theo thời hạn áp dụng.

### 16.1. Ví dụ phương pháp sampling

Một kỳ có 1.200 yêu cầu cấp quyền. Auditor chọn 25 yêu cầu được gắn nhãn emergency và phát hiện 4 trường hợp thiếu approval. Vì đây là **mẫu theo rủi ro**, có thể kết luận tồn tại vấn đề đáng quan tâm ở **những đối tượng đã thử**, cần mở rộng kiểm tra hoặc đánh giá toàn bộ emergency population; không được mặc định “4/25 = 16% tất cả 1.200 yêu cầu đều vi phạm”.

Sampling chỉ hữu ích nếu reviewer biết **đã chọn mẫu như thế nào và để trả lời câu hỏi gì**.

## 17. Checklist findings, CAP và xác minh closure

### N — Findings and Corrective Action

- [ ] **N-01:** Finding ghi rõ **criteria, condition, evidence, scope, cause hypothesis và impact**.
- [ ] **N-02:** Risk priority và deadline tuân theo phương pháp được phê duyệt; không dựa đơn thuần màu trên dashboard.
- [ ] **N-03:** Có remediation owner thực sự có quyền/nguồn lực sửa, cùng người chịu risk.
- [ ] **N-04:** Management response thể hiện đồng ý/không đồng ý, bằng chứng, kế hoạch và thời hạn.
- [ ] **N-05:** Dispute của finding được xử lý bằng evidence và review độc lập theo quy trình, không xóa finding âm thầm.
- [ ] **N-06:** CAP ghi action cụ thể, root cause, phụ thuộc, owner và milestone.
- [ ] **N-07:** Khi trì hoãn sửa, có compensating controls và risk decision đúng thẩm quyền theo chính sách.
- [ ] **N-08:** Có closure criteria trước khi retest, gắn đúng condition của finding.
- [ ] **N-09:** Evidence sửa xác nhận đúng artifact, asset/region và runtime, không chỉ PR merge.
- [ ] **N-10:** Retest chạy kịch bản gốc và các biến thể liên quan theo root cause.
- [ ] **N-11:** Positive/regression tests xác nhận fix không phá chức năng hoặc control liên quan.
- [ ] **N-12:** Independent verifier hoặc reviewer phù hợp kiểm tra kết quả trước khi đóng.
- [ ] **N-13:** Partial fix, non-reproducible và UNKNOWN không tự chuyển VERIFIED CLOSED.
- [ ] **N-14:** Historical gaps (ví dụ mất log trong quá khứ) vẫn được lưu dù control hiện đã chạy.
- [ ] **N-15:** Finding tái diễn hoặc có tác động chung tới nhiều hệ thống được đánh giá rủi ro cộng gộp.
- [ ] **N-16:** Closure evidence, quyết định và risk register/assurance case đều được cập nhật.

**Anti-pattern quan trọng:** “Ticket Done” hoặc “scan clean” không thay thế retest. Nếu một lỗ hổng ở sáu workload mới sửa được ba, conclusion cần nói **partially remediated** thay vì đánh dấu cả finding đã đóng.

## 18. Checklist exception và residual risk

### O — Risk Acceptance and Exceptions

- [ ] **O-01:** Các deviations khỏi control baseline được nhận diện, không gọi là tuân thủ chỉ vì chưa bị phát hiện.
- [ ] **O-02:** Exception có mã, requirement/control, lý do và **allowed deviation cụ thể**.
- [ ] **O-03:** Có phạm vi in-scope/out-of-scope theo asset, role, environment, data, thời kỳ và release khi cần.
- [ ] **O-04:** Có risk assessment, residual risk và assumptions được lưu.
- [ ] **O-05:** Người phê duyệt có quyền phù hợp mức tác động và không vượt nghĩa vụ bên ngoài.
- [ ] **O-06:** Compensating controls có owner, design/effectiveness evidence và monitoring.
- [ ] **O-07:** Ngày hiệu lực/hết hạn, timezone, milestones và review triggers rõ ràng.
- [ ] **O-08:** Gia hạn là quyết định mới hoặc amendment hợp lệ, không tự động sao chép.
- [ ] **O-09:** Tài sản/region/identity mới không tự hưởng exception nếu vượt phạm vi duyệt.
- [ ] **O-10:** Trạng thái EXCEPTED và technical FAIL được báo riêng khi control chưa đáp ứng.
- [ ] **O-11:** Khi compensating control thất bại hoặc threat thay đổi, có escalation và risk re-review.
- [ ] **O-12:** Có kế hoạch trở về baseline, CAP và evidence xác minh kết thúc ngoại lệ.
- [ ] **O-13:** Risk acceptance không được dùng để che lấp evidence gap chưa được trình bày.
- [ ] **O-14:** Rủi ro cộng gộp từ nhiều exception cùng nguyên nhân/dependency được xem xét.

## 19. Checklist continuous assurance sau audit

Một cuộc audit hữu ích phải làm rõ **điều gì cần tiếp tục được giám sát**, không chỉ tạo ra report một lần.

### P — Continuous Assurance

- [ ] **P-01:** Các control trọng yếu có owner, criteria, population, bằng chứng và lịch test theo risk.
- [ ] **P-02:** Có preventive, detective và corrective controls ở các điểm cần thiết.
- [ ] **P-03:** Monitoring theo sự kiện/chu kỳ phù hợp tốc độ thay đổi, không tự gọi “real-time” khi chỉ quét hàng ngày.
- [ ] **P-04:** Có source health, freshness/completeness checks và chế độ UNKNOWN khi mất dữ liệu.
- [ ] **P-05:** Policy-as-code/evaluator được kiểm thử bằng tình huống đúng, sai và thiếu nguồn.
- [ ] **P-06:** Drift và asset/identity mới được phát hiện, gán owner và phân loại rủi ro.
- [ ] **P-07:** Findings tự động được liên kết tới risk/control, CAP, exception và retest.
- [ ] **P-08:** Auto-remediation được giới hạn blast radius, có guardrails, rollback và audit trail.
- [ ] **P-09:** Evidence được giữ có version, history, reviewer và trigger đánh giá lại.
- [ ] **P-10:** Audit findings được chuyển thành cải tiến kiểm soát, không chỉ “đóng ticket”.
- [ ] **P-11:** Có owner theo dõi các phát hiện quá hạn, exception sắp hết hạn và control mất nguồn.
- [ ] **P-12:** Chương trình có đánh giá lại assumptions khi threat, release, architecture hoặc nghĩa vụ thay đổi.

### 19.1. Checklist phải giúp quyết định ưu tiên

Nếu dashboard cho thấy 95% control “green” nhưng 5% còn lại liên quan quyền quản trị của toàn cloud organization, không nên xếp rủi ro thấp chỉ bằng tỷ lệ trung bình. Phân tích cần dựa vào **criticality, scenario, blast radius, thời gian phơi nhiễm và hiệu quả của biện pháp bảo vệ**.

## 20. Quy trình làm audit từ đầu đến cuối

Sơ đồ minh họa:

~~~mermaid
flowchart TD
    A["Scope + criteria + risk-based plan"] --> B["Inventory và owner verification"]
    B --> C["Control/claim/evidence matrix"]
    C --> D["Fieldwork: test, sampling, source checks"]
    D --> E{"Evidence adequate?"}
    E -- "Không" --> F["UNKNOWN / evidence gap + owner"]
    E -- "Có" --> G{"Criteria achieved?"}
    G -- "Không" --> H["Finding + impact + management response"]
    G -- "Có" --> I["Scoped PASS + limitations"]
    F --> J["Evidence remediation and reassessment"]
    H --> K["CAP / exception / risk decision"]
    K --> L["Retest + independent closure"]
    J --> D
    I --> M["Consolidated audit conclusion"]
    L --> M
    M --> N["Continuous monitoring + next audit triggers"]
~~~

### 20.1. Trước fieldwork

1. Chốt audit charter, thời kỳ, policy/control version và yêu cầu bên ngoài thực sự áp dụng.
2. Đối chiếu asset/identity inventory; tìm phần thiếu owner.
3. Xác định risk-prioritized controls, sampling và procedures.
4. Phân công người cung cấp evidence, reviewer và đầu mối escalation.
5. Chuẩn bị môi trường thử và được cấp quyền nếu test kỹ thuật có thể ảnh hưởng hệ thống.

### 20.2. Trong fieldwork

1. Thu evidence theo đúng procedure, giữ nguồn và metadata.
2. Kiểm tra population completeness, collector health và quality gates.
3. Thực hiện walkthrough, inspection, reperformance hoặc test phù hợp.
4. Ghi expected/actual, findings, phản chứng và những phần chưa chứng minh.
5. Xác minh facts với chủ thể được đánh giá mà không để việc xác minh facts biến thành loại bỏ evidence bất lợi.
6. Cập nhật working paper và review notes theo version.

### 20.3. Sau fieldwork

1. Tổng hợp kết luận theo từng control và tác động rủi ro.
2. Ghi management response, người xử lý và CAP.
3. Kiểm tra ngoại lệ và risk decisions có đúng quyền.
4. Phát hành báo cáo qua quy trình có thẩm quyền.
5. Theo dõi retest và audit closure.
6. Kết nối evidence, findings và các trigger đánh giá lại với assurance program liên tục.

## 21. Mẫu audit checklist dạng YAML

Mẫu dưới đây là **cấu trúc thực hành**, không phải schema bắt buộc và không phải kết quả audit thật. Các trường FAILED/UNKNOWN được cố ý thể hiện để nhấn mạnh không tự động biến thiếu bằng chứng thành PASS.

~~~yaml
security_assurance_audit:
  audit_id: AUD-EX-04
  service: OrdersHub
  module: SECURITY_SECURITY_ASSURANCE
  mode: SIMULATED_TRAINING
  audit_type: internal_security_assurance_review

  scope:
    environments: [production]
    regions: [region-a, region-b]
    period_from_utc: "2026-07-01T00:00:00Z"
    period_to_utc: "2026-09-30T23:59:59Z"
    inventory_ref: "restricted/inventory/ordershub"
    out_of_scope:
      - "Other unrelated business services"
    limitation: "Vendor internals evaluated only via available evidence"

  criteria:
    policy_version_ref: "restricted/policies/security-baseline-v4"
    control_catalog_ref: "restricted/controls/catalog-v4"
    risk_methodology_ref: "restricted/risk/methodology"

  governance:
    audit_lead_role: INTERNAL_AUDIT_REVIEWER
    service_owner_role: ORDER_SERVICE_OWNER
    control_owner_role: SECURITY_CONTROL_OWNER
    risk_authority_role: AUTHORIZED_BUSINESS_RISK_OWNER

  checks:
    - id: B-02
      requirement_id: ASSET-INV-01
      target: "All production cloud accounts and regions"
      procedure: "Reconcile cloud organization and asset inventory"
      expected_population: 4
      observed_population: 3
      status: UNKNOWN
      evidence_refs:
        - "restricted/evidence/AUD-EX-04/inventory-export"
      gap: "One production account missing"
      action_owner_role: CLOUD_INVENTORY_OWNER

    - id: D-03
      requirement_id: IAM-PRIV-MFA-01
      target: "Privileged interactive human identities"
      procedure: "Check IdP enforcement and approved login-path tests"
      status: PARTIAL
      evidence_refs:
        - "restricted/evidence/AUD-EX-04/iam-policy"
        - "restricted/evidence/AUD-EX-04/login-tests"
      limitation: "Emergency login path not yet tested"
      action_owner_role: IAM_CONTROL_OWNER

    - id: I-04
      requirement_id: LOG-AUDIT-01
      target: "Admin events for every required production source"
      procedure: "Trace synthetic events end-to-end into SIEM"
      status: FAIL
      evidence_refs:
        - "restricted/evidence/AUD-EX-04/source-test"
      finding_ref: FIND-04
      action_owner_role: LOGGING_PLATFORM_OWNER

    - id: N-10
      requirement_id: REMEDIATE-VERIFY-01
      target: "Finding FIND-02 on all affected workloads"
      procedure: "Deployment verification and independent retest"
      status: PENDING_RETEST
      evidence_refs:
        - "restricted/changes/PR-88"
      limitation: "PR merged; runtime retest not available"
      action_owner_role: REMEDIATION_OWNER

  audit_summary:
    readiness_for_positive_conclusion: NOT_DEMONSTRATED
    blocking_items:
      - "I-04: audit log ingestion failed"
      - "B-02: production inventory incomplete"
    approval_status: NOT_SIGNED
    next_step: "Collect missing evidence, remediate and retest"
~~~

### 21.1. Cách dùng mẫu

Mỗi check cần gắn evidence thật nếu triển khai ngoài lab; ID và path giả định không tự chứng minh gì. **Trường status nên là kết quả của evaluation**, không phải giá trị điền trước rồi đi tìm tài liệu hợp thức hóa. Người kiểm tra cần đọc raw data, kiểm tra quyền truy cập, phiên bản, thời kỳ và các kết quả trái chiều.

## 22. Mẫu working paper và issue log

### 22.1. Working paper cho một kiểm tra cụ thể

~~~yaml
working_paper:
  id: WP-AUD-04-I-04
  check_id: I-04
  control_id: LOG-AUDIT-01
  claim: "All required privileged action events reach SIEM"
  period: "2026-Q3"
  population:
    expected_sources: 8
    tested_sources: 8
    missing_sources: 0
  method: "Synthetic event per source and source-to-SIEM lookup"
  test_result:
    passed: 6
    failed: 2
    status: FAIL
  observed:
    - "Two application sources did not deliver expected events"
  evidence_refs:
    - "restricted/evidence/AUD-EX-04/raw-synthetic-events"
    - "restricted/evidence/AUD-EX-04/siem-query-results"
  limitations:
    - "Historical event loss period still being investigated"
  finding_ref: FIND-04
  prepared_by_role: SECURITY_TESTER
  reviewed_by_role: INDEPENDENT_ASSURANCE_REVIEWER
  review_status: PENDING
~~~

**Điểm cần lưu ý:** evidence rằng sáu nguồn gửi log thành công **không giúp tổng control PASS** khi hai nguồn bắt buộc còn thất bại.

### 22.2. Finding record rút gọn

Một finding nên có:
- **Criteria:** chuẩn hoặc requirement nào bị sai lệch?
- **Condition:** quan sát thực tế là gì, ở đâu và khi nào?
- **Evidence:** nguồn, phiên bản, query/test và raw record?
- **Cause:** nguyên nhân đã được xác minh hay chỉ là giả thuyết?
- **Effect/risk:** tác động và trường hợp có thể xảy ra?
- **Owner/management response:** ai thực hiện, đồng ý/không đồng ý và vì sao?
- **Corrective action:** làm gì, deadline, phụ thuộc và owner?
- **Closure criteria:** bằng chứng retest nào cần trước khi đóng?
- **Status/history:** OPEN, ACTION IN PROGRESS, PENDING RETEST, VERIFIED CLOSED, EXCEPTED theo quy trình.

Tránh đặt status CLOSED ngay khi PR được merge. Đội engineering có thể xác nhận **implemented**, nhưng người reviewer phải kiểm tra liệu control đã hoạt động đúng trên scope và thời kỳ được đánh giá hay chưa.

## 23. Tình huống xuyên suốt: audit dịch vụ OrdersHub

Toàn bộ thông tin trong mục này là **giả định**, không đại diện doanh nghiệp hoặc audit thật.

### 23.1. Phạm vi

OrdersHub là ứng dụng xử lý đơn hàng đa tenant. Kỳ được đánh giá là quý III/2026. Có bốn cloud accounts production thuộc hai regions, một IdP, tám ứng dụng phát audit event và một pipeline SIEM. Tổ chức muốn xem xét:

1. Phân quyền user và service account.
2. Audit logging của hành động đặc quyền.
3. Việc sửa vulnerability trên các workload quan trọng.
4. Approval của production changes.
5. Backup/restore và kế hoạch ứng phó sự cố.

### 23.2. Evidence pack mô phỏng

| Ref | Dữ liệu | Giới hạn |
|---|---|---|
| E-01 | Policy/control catalog được duyệt | Chứng minh thiết kế, chưa chứng minh vận hành |
| E-02 | Cloud inventory report có 3/4 accounts | Population chưa đủ |
| E-03 | IdP export: 140 tài khoản đặc quyền, 138 có MFA | Chưa đối chiếu account thứ tư và emergency paths |
| E-04 | Access-review dashboard ghi 100% completed | Chưa chứng minh quyết định thu hồi thực sự áp dụng |
| E-05 | Runtime negative test cho 12/14 API routes PASS | Hai route chưa thử |
| E-06 | Log pipeline synthetic test: 6/8 ứng dụng nhận event | Hai nguồn FAIL |
| E-07 | Vulnerability patch PR merged ở repo | Chưa có deployment/retest tất cả workload |
| E-08 | Change register 20/20 tickets đã approved | Chưa đối chiếu với các thay đổi runtime ngoài workflow |
| E-09 | Restore drill thành công với backup cũ | Chưa thử key/schema sau release mới |
| E-10 | Hai ngoại lệ có approval và còn hiệu lực | Cần kiểm tra scope, conditions và expiry |
| E-11 | Một exception khác hết hạn tháng 8 | Không còn là ngoại lệ hợp lệ cho tháng 9 |
| E-12 | SIEM incident timeline thiếu log ba ngày | Historical evidence gap phải được giữ |
| E-13 | CAP ghi “logging fixed” và dashboard xanh hôm nay | Không chứng minh log ba ngày cũ đã được khôi phục |
| E-14 | Role support có quyền cross-tenant metadata, chưa có business justification | Cần risk/control review và tests |

### 23.3. Điền checklist theo evidence

| Check | Phát hiện | Đánh giá hợp lý | Hành động |
|---|---|---|---|
| B-02 | Inventory thiếu một account | **UNKNOWN / coverage gap** | Thu inventory và rà lại control scope |
| D-03 | MFA kết quả chưa đủ population | **PARTIAL / NOT DEMONSTRATED** toàn production | Kiểm tra account thứ tư và emergency |
| D-07 | Dashboard review 100% | **NOT DEMONSTRATED** về thu hồi quyền | Lấy quyết định và runtime change records |
| D-10 | API test 12/14 routes | **PARTIAL** | Kiểm tra hai route còn thiếu theo risk |
| I-04 | Synthetic log FAIL ở hai nguồn | **FAIL** | CAP và retest end-to-end |
| H-10 | PR merge, chưa retest | **PENDING RETEST** | Deployment proof và independent retest |
| G-09 | 20 approvals | **PARTIAL** cho change compliance | Đối chiếu ngoài workflow |
| J-05 | Restore bản cũ PASS | **NOT DEMONSTRATED** cho recovery release mới | Targeted restore/key test |
| O-07 | Ngoại lệ hết hạn | **FAIL** nếu sai khác vẫn tồn tại và không có quyết định hợp lệ | Escalate, xử lý hoặc xem xét phê duyệt mới |
| L-07 | Thiếu ba ngày log quá khứ | **Historical evidence gap** | Impact assessment, không viết lại kết quả cũ |

Một bảng như vậy **không phải kết luận mọi control đều FAIL**. Một số control có bằng chứng FAIL trực tiếp; phần khác chỉ **thiếu nguồn hoặc thiếu độ bao phủ**. Phân biệt này giúp CAP đi đúng nguyên nhân.

### 23.4. Ví dụ finding đầy đủ

> **FIND-04 — Security event ingestion incomplete.**  
> **Criteria:** control LOG-AUDIT-01 yêu cầu mọi nguồn ứng dụng thuộc danh mục phải gửi các hành động đặc quyền đến SIEM trong kỳ đánh giá.  
> **Condition:** thử synthetic cho 8 nguồn thấy 6 nguồn có event ở SIEM, 2 nguồn không có; timeline còn ghi một khoảng ba ngày thiếu log.  
> **Evidence:** E-06, E-12 và các nguồn kiểm tra có ID/time tương ứng.  
> **Risk:** giảm khả năng phát hiện và điều tra thao tác có đặc quyền; không thể xác nhận audit trail đầy đủ trong khoảng mất nguồn.  
> **Root cause:** chưa xác minh, cần điều tra collector/parser và cấu hình ứng dụng.  
> **Owner:** Logging control owner phối hợp application/platform/SOC owners.  
> **CAP:** sửa đúng nguyên nhân, giám sát mất nguồn, retest từ nguồn đến SIEM; đánh giá tác động của lịch sử mất log.  
> **Closure:** reviewer xác minh đầy đủ source population, test và monitoring PASS; lịch sử ba ngày vẫn ghi limitation nếu không khôi phục được.

Một báo cáo audit tốt không tạo **ảo giác rằng log quá khứ có thể được chứng minh đầy đủ** chỉ vì log hiện tại chạy lại.

## 24. Tổng hợp kết quả và báo cáo audit

### 24.1. Mẫu cấu trúc audit report

~~~text
SECURITY ASSURANCE AUDIT REPORT
1. Audit ID, period, criteria và version
2. Mục đích, phạm vi, out-of-scope và authority
3. Executive summary: major risks, material gaps, conclusion
4. Phương pháp kiểm tra, sampling, source/provenance
5. Control/claim/evidence matrix và kết quả
6. Significant findings, exceptions và counterevidence
7. Management response, CAP và người chịu trách nhiệm
8. Residual risks, limitations và evidence gaps
9. Retest/follow-up plan và trigger đánh giá lại
10. Reviewer/decision sign-off và audit trail
11. Evidence index + working papers
~~~

### 24.2. Mẫu executive summary minh họa

> **Audit AUD-EX-04** xem xét một số control trọng yếu của OrdersHub trong quý III/2026. Bằng chứng mô phỏng cho thấy hai trong tám ứng dụng không đưa audit events tới SIEM theo phép thử; có khoảng trống lịch sử ba ngày; inventory một cloud account chưa được thu; và một số kết quả access review, patch, restore chưa có bằng chứng vận hành đủ để kết luận bao phủ toàn production. Các vấn đề được tách thành **FAIL có evidence** và **NOT DEMONSTRATED do coverage gap**.  
> **Kết luận:** Chưa có cơ sở đưa ra một nhận định tích cực cho toàn bộ control objectives thuộc phạm vi; cần CAP, kiểm tra bổ sung, retest và đánh giá lại. Kết luận chỉ dựa trên evidence pack mô phỏng, **không phải kết luận của audit thực hoặc chứng nhận theo một tiêu chuẩn**.

**Đừng viết:** “Hệ thống hoàn toàn không an toàn”, vì không phải mọi control đều đã được kiểm chứng. Cũng **đừng viết:** “98% an toàn” vì không có mô hình cho phép suy từ tỷ lệ ô xanh sang xác suất an toàn.

## 25. Ưu tiên findings và theo dõi rủi ro

Không phải mọi dòng chưa PASS có cùng mức độ.

| Nhóm | Ví dụ | Ưu tiên xử lý |
|---|---|---|
| **Phản chứng về control trọng yếu** | Cross-tenant data read, admin policy quá rộng, logging bắt buộc FAIL | Đánh giá tác động, containment/incident và CAP phù hợp |
| **Evidence gap có thể che blocker** | Thiếu cloud account, scanner không có quyền, route chưa test | Ưu tiên khôi phục visibility và đánh giá rủi ro |
| **Quá hạn nghĩa vụ/phê duyệt** | Exception hết hạn, mandatory review chưa làm | Escalate đúng authority và xử lý sai khác |
| **Finding chưa verified fixed** | PR merged nhưng production chưa retest | Kiểm tra đúng artifact/scope, closure evidence |
| **Cải tiến hình thức** | Tên report chưa chuẩn, trường metadata nhỏ thiếu | Khắc phục theo mức tác động thực tế |

### 25.1. Viết corrective action có thể đo

Yếu: “Nâng cao an toàn và cải thiện logging.”

Tốt hơn:

> “Logging platform owner cập nhật parser cho download event phiên bản V, đối chiếu đủ 8/8 nguồn; thực hiện synthetic test có event IDs đến SIEM và test alert, ghi thời gian nguồn mất; independent reviewer kiểm tra closure criteria. Khoảng log lịch sử không khôi phục được phải được nêu riêng trong risk/audit records.”

Không đặt SLA tùy ý: deadline cần được tổ chức quyết định theo risk, nghĩa vụ và khả năng khắc phục.

### 25.2. Sau remediation còn gì?

1. Xác nhận fix đã triển khai.
2. Retest finding gốc trên đủ population.
3. Chạy positive/regression tests khi cần.
4. Rà lại root cause và các control cùng phụ thuộc.
5. Cập nhật assurance claim, risk register và audit record.
6. Không xóa evidence FAIL lịch sử; lưu quyết định theo đúng thời điểm.

## 26. Những anti-pattern khi dùng audit checklist

| Anti-pattern | Vì sao nguy hiểm | Phương án sửa |
|---|---|---|
| **Checkbox compliance** | Tick đủ nhưng không có evidence | Test card gắn criteria, expected/actual và nguồn |
| **Policy PDF = control PASS** | Mới chứng minh thiết kế | Triển khai và operating evidence |
| **Một screenshot cho cả quý** | Không chứng minh trạng thái liên tục | History, event/source health và sampling hợp lý |
| **Inventory tự chứng nhận đầy đủ** | Asset ngoài inventory bị bỏ qua | Independent reconciliation, missing population |
| **Không có alert nghĩa là an toàn** | Collector/logic có thể bị lỗi | Synthetic tests, positive/negative evaluator fixtures |
| **Lấy mẫu thuận tiện rồi suy toàn bộ** | Selection bias | Ghi phương pháp và giới hạn suy luận |
| **Mọi compliance score dùng chung denominator** | Che nhóm control/asset rủi ro cao | Kết quả theo criticality, population, scope |
| **EXCEPTED được cộng PASS** | Biến risk acceptance thành technical compliance | Trạng thái tách biệt và residual risk |
| **Ticket Done = finding fixed** | Không chứng minh runtime và closure | Deployment proof + retest reviewer |
| **Chỉ giữ test cuối PASS** | Mất lịch sử và phản chứng | Versioned working papers, raw evidence |
| **Scanner xanh khi mất quyền** | False negative | Collector-health và UNKNOWN status |
| **Một vendor report cho mọi control** | Shared responsibility bị bỏ qua | Scope, period, exception và customer configuration |
| **Reviewer tự duyệt mọi công việc của mình** | Xung đột lợi ích | Phân tách nhiệm vụ hoặc review bù trừ |
| **Bắt audit bằng việc gom file** | Thiếu claim/criteria, tốn công | Risk/requirement-driven evidence plan |
| **Kết luận vượt scope** | Một region PASS thành “global compliant” | Ghi rõ tested region/version/period |
| **Không theo dõi sau audit** | Findings và rủi ro tái diễn | CAP, retest, control monitoring |
| **Lộ secrets trong hồ sơ** | Audit làm tăng rủi ro | Data minimization, redaction, RBAC và retention |
| **Không xét cumulative risk** | Nhiều findings nhỏ có thể tạo chung attack path | Threat/dependency aggregation |

## 27. Bài tập thực hành

### Bài tập A — Xây audit charter cho hệ thống đa tenant

Một ứng dụng SaaS có API, storage, IAM, pipeline logging và các tenant khách hàng. Đội dự định audit “mọi thứ về bảo mật” trong hai tuần.

1. Viết lại **mục đích, scope, out-of-scope, thời kỳ, tiêu chí và người có thẩm quyền**.
2. Chọn ít nhất 5 security objectives dựa trên data classification và criticality.
3. Tạo audit matrix 12 check IDs thuộc ít nhất 5 nhóm.
4. Nêu bằng chứng thiết kế, triển khai và vận hành cho ít nhất 3 checks.
5. Thiết kế cơ chế không làm lộ dữ liệu khách hàng khi thu evidence.
6. Đưa ra điều kiện đánh giá lại khi release hoặc cloud account mới xuất hiện.

### Bài tập B — Dashboard ghi 100% PASS

Audit nhận dashboard có 100% MFA và 100% access reviews. Nhưng một cloud account chưa onboard, emergency logins không nằm trong test và bốn quyết định thu hồi quyền chưa có evidence thực hiện.

1. Xác định population và data-quality gaps.
2. Phân biệt từng phần PASS, FAIL, UNKNOWN hoặc PENDING VERIFICATION.
3. Viết working paper và procedure kiểm tra quyền thực.
4. Nêu ít nhất ba counterevidence có thể làm thay đổi kết luận.
5. Viết finding/evidence gap với owner, CAP và criteria.

### Bài tập C — Vulnerability scan sạch

Một báo cáo scan trên release mới không còn CVE; production có 5 workload nhưng chỉ 3 đã deploy image mới, region DR còn version cũ.

1. Vì sao “scan sạch” chưa chứng minh đã sửa toàn production?
2. Nêu các dữ liệu cần về SBOM, digest, asset population và scanner coverage.
3. Viết một finding và closure criteria.
4. Thiết kế retest cho runtime và regression.
5. Chọn đúng trạng thái PARTIAL, UNKNOWN, PENDING RETEST hay VERIFIED CLOSED ở từng phần.

### Bài tập D — Audit security logging

Có 8 ứng dụng quan trọng, hai nguồn mất dữ liệu 72 giờ. Hiện tại SIEM đã nhận log và dashboard xanh.

1. Những gì có thể chứng minh về **trạng thái hiện tại**?
2. Những gì không thể khẳng định về 72 giờ lịch sử?
3. Chọn evidence quality gates, synthetic tests và sampling thích hợp.
4. Nêu chủ thể chịu incident/impact assessment và CAP.
5. Viết executive summary không làm đẹp kết luận.

### Bài tập E — Ngoại lệ và risk acceptance

Hai service có ngoại lệ được duyệt trì hoãn patch đến ngày D, có network restrictions và giám sát. Sau D có một service chưa vá; một service khác mở thêm host mới ngoài scope.

1. Kiểm tra thẩm quyền, hạn, scope và compensating control.
2. Trạng thái của từng service/host là PASS, EXCEPTED hay FAIL?
3. Cần evidence nào để xác minh việc trì hoãn còn được chấp nhận?
4. Thiết kế escalation, CAP và retest.
5. Vì sao không được tự gia hạn hoặc gộp exception vào PASS?

### Bài tập F — Audit pack có nhiều file

Nhóm nộp 200 ảnh, 40 PDF và biểu đồ compliance score 99%. Tuy nhiên không có kiểm kê nguồn, nhiều ảnh không có thời điểm và không ai giữ raw data.

1. Chỉ ra ít nhất 8 vấn đề về relevance, sufficiency và provenance.
2. Viết evidence contract có 10 trường trở lên.
3. Đề xuất cách ưu tiên audit procedures theo rủi ro thay vì số file.
4. Phân biệt UNKNOWN do thiếu nguồn với FAIL có bằng chứng.
5. Đề xuất metrics để cải tiến continuous assurance.

## 28. Rubric tự chấm cho một checklist audit hoàn chỉnh

Một rubric tham khảo 100 điểm:

| Tiêu chí | Điểm | Dấu hiệu chất lượng |
|---|---:|---|
| **Audit charter, scope và criteria** | 15 | Rõ kỳ, hệ thống, version, authority, out-of-scope |
| **Asset/population completeness** | 15 | Có đối chiếu nguồn, missing coverage và owner |
| **Control–risk–claim mapping** | 15 | Hỏi đúng security objective, acceptance criteria |
| **Evidence quality và methodology** | 20 | Nguồn, method, sampling, timeframe, counterevidence |
| **Technical/security test coverage** | 15 | Positive/negative, runtime, logging, DR, release |
| **Findings, CAP và retest** | 10 | Criteria, condition, root cause hypothesis, owner, closure |
| **Conclusion và residual risk** | 5 | Không suy rộng, giữ UNKNOWN/EXCEPTED, đúng authority |
| **Evidence hygiene và liên tục cải tiến** | 5 | Bảo vệ dữ liệu, version, reassessment triggers |
| **Tổng** | **100** | Không có blocker bị che bằng một điểm trung bình |

**Không sử dụng rubric này để kết luận hệ thống “an toàn 90%”**. Nó chỉ là công cụ sư phạm đánh giá **chất lượng hồ sơ audit do người học tạo**, không phải phép đo xác suất bị tấn công hoặc mức tuân thủ một tiêu chuẩn bên ngoài.

## 29. Checklist nhanh cho buổi rà soát trước audit

Khi chỉ có một buổi để kiểm tra độ sẵn sàng, ưu tiên 15 câu hỏi sau:

- [ ] **01.** Có mục tiêu, criteria, scope, period và owner rõ ràng chưa?
- [ ] **02.** Có biết toàn bộ service, account, region, identity, data flow thuộc scope chưa?
- [ ] **03.** Những risk/security objectives trọng yếu đã được nối tới control và evidence chưa?
- [ ] **04.** Control có PASS/FAIL criteria cụ thể, không chỉ “chính sách tồn tại” chưa?
- [ ] **05.** Evidence đúng release/config, thời điểm và kỳ vận hành chưa?
- [ ] **06.** Có thể đi từ claim tới raw evidence và phương pháp test chưa?
- [ ] **07.** Các nguồn scan/log/inventory có health/coverage checks chưa?
- [ ] **08.** Positive/negative tests bao phủ role, tenant, đường API rủi ro cao chưa?
- [ ] **09.** Access reviews có bằng chứng thực hiện quyết định thu hồi chưa?
- [ ] **10.** Findings/patch đã deploy và verified fixed, không chỉ PR merged chưa?
- [ ] **11.** Security logging và alerts đã thử end-to-end chưa?
- [ ] **12.** Backup/DR có bằng chứng restore phù hợp chứ không chỉ job xanh chưa?
- [ ] **13.** Exceptions có đúng phạm vi, thời hạn và thẩm quyền, không bị cộng PASS chưa?
- [ ] **14.** Audit findings có management response, CAP, owner, retest và escalation chưa?
- [ ] **15.** Kết luận dự kiến có ghi rõ FAIL, UNKNOWN, limitations và risk decisions chưa?

Nếu một câu hỏi quan trọng được trả lời “chưa biết”, **đó chính là một đầu việc cần xác minh**, không phải lý do đánh dấu PASS để hoàn tất bảng.

## 30. Tổng kết

**Checklist audit** trong security assurance là **phương pháp tổ chức kiểm tra có truy vết**: mỗi security requirement phải có control, đối tượng áp dụng, cách kiểm tra, evidence và kết luận trong phạm vi được phép. Một checklist có giá trị khi giúp auditor tìm được **điều đang không đạt, điều chưa biết, điều được chấp nhận có điều kiện và bằng chứng cần bổ sung**, thay vì chỉ tạo một tỷ lệ màu xanh.

Chuỗi tổng kết của module **SECURITY_SECURITY_ASSURANCE** là:

**Security objectives / Risk → Requirements & control criteria → Audit scope và population → Claim–Argument–Evidence → Test/sampling/source quality → Findings & management response → CAP / exception / risk decision → Independent retest → Scoped audit conclusion → Continuous assurance.**

Khi hoàn tất, người học phải trả lời được: **đang kiểm tra điều gì; theo yêu cầu và thời kỳ nào; trên toàn bộ đối tượng hay một mẫu; dữ liệu có nguồn, độ tin cậy và giới hạn gì; phát hiện nào đang mở; ai chịu trách nhiệm khắc phục; ai có quyền quyết định rủi ro; và điều gì sẽ khiến kết luận phải xem lại**.

Mục tiêu không phải một checklist dài nhất, mà là **một checklist đủ đúng để hỗ trợ quyết định bảo mật trung thực và có bằng chứng**.
