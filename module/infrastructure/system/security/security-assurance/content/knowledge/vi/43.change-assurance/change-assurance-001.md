# Security change review: rà soát thay đổi bảo mật có bằng chứng từ thiết kế đến production

**Security change review** là hoạt động đánh giá có cấu trúc nhằm xác định một thay đổi dự kiến hoặc đã xảy ra đối với hệ thống, phần mềm, hạ tầng, dữ liệu, danh tính, cấu hình, quy trình hoặc nhà cung cấp **có làm thay đổi security objectives, threat model, mức rủi ro, phạm vi kiểm soát và nghĩa vụ áp dụng hay không**. Hoạt động này giúp quyết định thay đổi có thể triển khai trong điều kiện nào, cần bổ sung kiểm soát hoặc bằng chứng gì, và bằng cách nào có thể xác nhận các điều kiện bảo mật vẫn được duy trì sau khi triển khai.

Trong chương **Change assurance** thuộc module **SECURITY_SECURITY_ASSURANCE**, Security change review là một mắt xích quan trọng của chương trình đánh giá bảo mật **dựa trên bằng chứng**: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, remediation và theo dõi liên tục trong phát triển và vận hành. Thay đổi không nên được xem là an toàn chỉ vì đã được merge, có ticket được phê duyệt hoặc không thấy cảnh báo ngay sau deployment. Phải có chuỗi truy vết **mục tiêu bảo mật → phạm vi thay đổi → rủi ro/điều kiện mới → control assertions → kiểm thử/evidence → quyết định → triển khai → xác minh trạng thái thực tế → theo dõi drift**.

Một nguyên tắc xuyên suốt: **review theo rủi ro, không theo kích thước diff**. Việc đổi một dòng policy IAM có thể mở đường truy cập root toàn tổ chức; một bản cập nhật hàng nghìn dòng tài liệu không ảnh hưởng đến ranh giới bảo mật có thể được review đơn giản hơn. Tuy nhiên, “thay đổi nhỏ” hay “được tự động hóa” không có nghĩa mặc định ít rủi ro.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Security change review và phân biệt với change approval, code review, architecture security review, threat modeling, security testing, release management và post-change verification.
2. Nhận diện những loại thay đổi phải review: application/API, IAM, network/cloud, container, CI/CD, dữ liệu, encryption keys, logging/detection, backup/DR, third-party và vận hành khẩn cấp.
3. Xác định **change boundary**: hệ thống trước/sau, môi trường, luồng dữ liệu, đặc quyền, trust boundaries, assets và business dependencies.
4. Thiết kế **risk-based triage** theo tác động, exposure, privilege, data classification, criticality, reversibility, exploitability và khả năng quan sát/khôi phục.
5. Viết **security acceptance criteria** và test plan có positive/negative tests, owner, evidence, thời điểm và phạm vi rõ ràng.
6. Đánh giá sự khác biệt giữa **control thiết kế**, **cấu hình đã triển khai**, **effective state** và **operating effectiveness** sau thay đổi.
7. Tổ chức vai trò, trách nhiệm review, segregation of duties, phê duyệt và ngoại lệ có thời hạn phù hợp rủi ro.
8. Áp dụng review vào CI/CD, IaC và GitOps mà không biến scanner PASS thành chứng cứ đầy đủ cho mọi security objective.
9. Lập kế hoạch rollout, canary, monitoring, rollback/fail-forward, data reconciliation và chứng cứ an toàn trước/sau.
10. Xử lý emergency change, production hotfix, thay đổi từ vendor và các thay đổi ngoài pipeline có dấu vết kiểm toán.
11. Xây mẫu **change assurance record**, decision log, evidence manifest và điều kiện đóng theo kiểm chứng production.
12. Đo chất lượng review bằng KPI có mẫu số, chất lượng dữ liệu, change-linked incidents và control drift mà không thưởng cho số lần phê duyệt.

## 2. Security change review là gì và không phải là gì?

### 2.1. Vị trí của hoạt động review

Một thay đổi có thể đi qua nhiều cơ chế khác nhau:

| Hoạt động | Câu hỏi chính | Không nên suy ra |
|---|---|---|
| **Change management** | Ai đề xuất, phê duyệt, lên lịch, triển khai và phục hồi thay đổi? | Change đã được phê duyệt nghĩa là đáp ứng mọi mục tiêu bảo mật |
| **Code review** | Code có đúng, bảo trì được và đáp ứng chuẩn kỹ thuật không? | Code review tự động phát hiện hết thay đổi quyền, dữ liệu, cloud và runtime |
| **Security change review** | Thay đổi ảnh hưởng rủi ro/security controls ra sao và chứng minh điều kiện an toàn bằng gì? | Một form được tick đã kiểm chứng hiệu lực của control |
| **Threat modeling** | Những kịch bản lạm dụng, attacker goals và trust boundary nào xuất hiện/đổi? | Sơ đồ design chứng minh runtime thực hiện đúng |
| **Architecture security review** | Kiến trúc, ranh giới, dependency và control design có hợp lý không? | Tất cả đường thực thi đã được kiểm thử sau deploy |
| **Security testing** | Assertion nào PASS/FAIL ở scenario và scope được kiểm? | Một test PASS đại diện cho mọi biến thể ngoài scope |
| **Deployment/operations validation** | Trạng thái production sau thay đổi có đúng expected state và business/security gates? | Pipeline xanh nghĩa không có thay đổi thủ công sau đó |
| **Audit/security assurance** | Có evidence đủ liên quan, tin cậy, đúng kỳ và scope để kết luận không? | Báo cáo độc lập hay chứng nhận thay thế kiểm chứng service hiện hành |

Security change review **kết nối** các hoạt động trên. Không nên tạo thêm một cổng phê duyệt thủ công cho mọi commit nếu đã có guardrails tự động đáng tin và phương pháp kiểm hậu triển khai. Đồng thời không được bỏ qua review khi thay đổi làm xuất hiện trust boundary hoặc nghĩa vụ mới.

### 2.2. Thay đổi nào được tính?

Không giới hạn ở source code:

- Đổi application logic, API authentication, authorization, business workflows, rate limiting hoặc transaction semantics.
- Thêm role, service account, privileged access, API token, break-glass path hoặc thay đổi federation/SSO.
- Thay IAM/KMS policies, cloud organization controls, network ingress/egress, DNS, TLS, certificate và secrets.
- Đổi container image, base runtime, dependency, build system, artifact provenance, CI/CD permissions.
- Di chuyển hoặc sao chép dữ liệu, thêm data class, region, backup location, retention hay subprocessor.
- Tắt/đổi logging sources, detection rules, SIEM routes, alert thresholds, suppression và investigation access.
- Thay kiến trúc HA/DR, RTO/RPO assumptions, failover, restore keys, network, state migration.
- Thay nhà cung cấp, hợp đồng, API tích hợp, access scope hoặc shared responsibility.
- Thay chính sách nội bộ, incident runbook, điều kiện compliance hoặc cách phê duyệt ngoại lệ.
- Emergency console change, drift ngoài IaC hoặc vendor-managed platform change.

**Một thay đổi không có commit trong repository vẫn có thể làm thay đổi security posture.** Ngược lại, không phải mọi commit đều cần cùng mức review.

### 2.3. Đánh giá điều gì?

Có ba lớp kết luận khác nhau:

1. **Design/plan acceptable:** đề xuất có đủ control design, threat analysis và kế hoạch để được phép thử/triển khai theo phạm vi?
2. **Implementation verified:** artifact/cấu hình/phương án đã được triển khai đúng version, environment, principal, traffic và dependency?
3. **Operational effectiveness validated:** control đã hoạt động đúng ở runtime/qua kỳ theo tiêu chí cần thiết, trong khi monitoring và rollback vẫn sẵn sàng?

Cần tách trạng thái **APPROVED_FOR_DEPLOY** và **VERIFIED_AFTER_DEPLOY**. Approval trước triển khai không phải bằng chứng hệ thống đã an toàn sau triển khai.

### 2.4. Định nghĩa security change success

Một thay đổi được xem là thành công về assurance khi:

- Phạm vi, asset và data-flow thật khớp kế hoạch hoặc khác biệt đã được review.
- Control assertions bắt buộc có bằng chứng đạt trên phạm vi đã phê duyệt.
- Những sai lệch critical được chặn/giảm thiểu và được xử lý bằng quyết định phù hợp.
- Không có dấu hiệu runtime drift, missing telemetry hoặc regression nghiêm trọng chưa được phân loại.
- Người quản lý dịch vụ xác nhận functional acceptance, security reviewer xác minh yêu cầu bảo mật.
- Có kế hoạch giám sát và điều kiện đánh giá lại sau khi traffic, dữ liệu hoặc người dùng tăng.
- Những phát hiện chưa xử lý có owner, thời hạn, residual risk và điều kiện rõ ràng.

**Không có sự cố ngay sau deploy không chứng minh các điều kiện trên đã đạt.**

## 3. Quy trình end-to-end của Security change review

### 3.1. Chu trình tham khảo

~~~mermaid
flowchart TD
    I["Change intake + inventory diff"] --> S["Scope và risk triage"]
    S --> C{"Security impact?"}
    C -- "Thấp, guardrails bao phủ" --> AUTO["Automated baseline review"]
    C -- "Có ranh giới / rủi ro mới" --> DEEP["Security design/threat review"]
    AUTO --> A["Control assertions + evidence plan"]
    DEEP --> A
    A --> G{"Pre-deploy gates PASS?"}
    G -- "Không" --> FIX["Sửa / bổ sung evidence / risk decision"]
    FIX --> A
    G -- "Có" --> DEC["Phê duyệt release theo thẩm quyền"]
    DEC --> DEP["Deploy kiểm soát + canary"]
    DEP --> POST["Runtime validation + observability"]
    POST --> OK{"Acceptance criteria đạt?"}
    OK -- "Không" --> RB["Containment / rollback / fail-forward"]
    RB --> FIX
    OK -- "Có" --> DONE["Verified change closure"]
    DONE --> MON["Monitoring + drift + review trigger"]
    MON --> S
~~~

Trong quy trình này, **security review** không phải một chữ ký vào cuối. Nó hình thành acceptance criteria trước triển khai, rồi dùng evidence sau thay đổi để xác minh và cập nhật kết luận.

### 3.2. Các bước và điểm bàn giao

| Bước | Dữ liệu đầu vào | Đầu ra có thể kiểm chứng |
|---|---|---|
| **1. Intake** | Request, code/config diff, service, business owner | Change ID, scope sơ bộ, thời điểm và loại thay đổi |
| **2. Impact assessment** | Asset/data/identity/network inventory, trust boundary | Rủi ro mới/đổi, nghĩa vụ và controls bị ảnh hưởng |
| **3. Triage** | Criticality, exposure, threat, reversibility, prior findings | Risk tier, review depth, reviewer roles |
| **4. Security review** | Architecture/data-flow/threat delta | Findings, yêu cầu sửa, guardrails, acceptance criteria |
| **5. Pre-deploy verification** | Build, scans, policies, tests, approved exceptions | Evidence gắn commit/artifact/environment, gate result |
| **6. Authorization** | Kết quả controls và residual risk | APPROVED / CONDITIONALLY_APPROVED / DEFERRED / REJECTED theo policy |
| **7. Controlled rollout** | Signed artifact, change window, canary/rollback | Deployment metadata, runtime IDs, change events |
| **8. Post-deploy verification** | Effective state, synthetic event, negative tests | PASS/FAIL/INCONCLUSIVE theo assertion, timestamp và scope |
| **9. Closure và monitoring** | Test result, incidents, service metrics, exception | VERIFIED_CLOSED, remediation, risk acceptance hoặc reopen |

### 3.3. Những mốc thời gian nên giữ

- **Requested_at:** thay đổi được đề xuất.
- **Assessed_at:** impact/threat review hoàn tất.
- **Approval_at:** quyết định release trong phạm vi.
- **Build_at:** artifact được tạo theo pipeline/commit xác định.
- **Deploy_start/finish_at:** khi bắt đầu/kết thúc rollout thực.
- **Runtime_verified_at:** khi effective configuration và test đạt.
- **Monitoring_window_end:** kết thúc thời gian quan sát/canary được định nghĩa.
- **Closure_at:** khi review được đóng theo thẩm quyền.
- **Exception_expires_at:** thời điểm ngoại lệ hết hiệu lực, nếu có.

Thời điểm **deployment hoàn tất** khác thời điểm **security control được chứng minh đạt**. Cần ghi UTC/cách đồng bộ đồng hồ để tránh phân tích timeline sai.

## 4. Change intake và xác định phạm vi thực sự

### 4.1. Tối thiểu phải biết trước khi review

1. **Change ID và mô tả:** thay cái gì, vì sao, kết quả nghiệp vụ mong đợi?
2. **Service/system owner:** ai chịu trách nhiệm và ai có quyền quyết định?
3. **Before/after state:** code/config/policy, architecture hoặc schema trước/sau.
4. **Environment và deployment scope:** dev/test/prod, account, cluster, region, tenant, rollout percentage.
5. **Affected assets/identities:** workloads, users, service accounts, privileged roles, third-party access.
6. **Data flow và classification:** loại dữ liệu, nơi lưu, API, cross-boundary transfer và retention.
7. **Security requirements:** control objectives, baseline, hợp đồng hoặc nghĩa vụ áp dụng.
8. **Dependencies:** IdP, KMS, DNS, network, logging, secrets, backup/DR, vendor services.
9. **Change window và reversibility:** rollback có thực sự khả thi, có state/data migration?
10. **Known findings/exceptions:** thay đổi có chạm rủi ro hoặc quyết định trước không?
11. **Monitoring/evidence readiness:** telemetry nào sẽ chứng minh trạng thái?
12. **Stakeholders và thông báo:** service owner, SOC/IR, data owner, privacy/legal nếu cần.

Không nhất thiết mọi change request phải thành biểu mẫu dài. Có thể điền tự động từ Git, CMDB, service catalog, IaC plan và deployment metadata, rồi yêu cầu con người làm rõ những trường còn thiếu.

### 4.2. Định nghĩa change boundary bằng “before → after”

| Thành phần | Trước thay đổi | Sau thay đổi | Câu hỏi security |
|---|---|---|---|
| Network | API chỉ internal | API accessible qua internet gateway | Có thêm attack surface và auth/throttling/monitoring? |
| IAM | Read-only service role | Có quyền sửa bảng khách hàng | Least privilege, approval và audit có đổi? |
| Data | Metadata không định danh | Thêm email/địa chỉ giao hàng | Data classification, retention, privacy và leakage path? |
| Infra | Một region | Multi-region replication | Keys, access, data residency và failover security? |
| Pipeline | Build bằng runner hạn quyền | Runner có quyền deploy production | Supply-chain trust và separation of duties? |
| Logging | Event admin đầy đủ | Tắt một số audit events để giảm chi phí | Có blind spot và nghĩa vụ lưu log? |
| Vendor | Không có support access | Vendor thêm privileged support session | MFA/PAM, expiry và evidence review? |
| Recovery | Restore thử thành công trong cùng account | DR chuyển account khác | Có quyền KMS, secrets, DNS và log khi restore? |

Nhìn vào **diff ngữ nghĩa** quan trọng hơn số dòng thay đổi. Một thay đổi đổi 1 ký tự từ deny sang allow có thể làm mất một critical control.

### 4.3. Xử lý thay đổi kế thừa và gián tiếp

Một module có thể không sửa IAM trực tiếp nhưng lại thay library xử lý authentication. Một change ở network policy có thể làm dịch vụ backup không tới KMS. Một change ở parser làm log vẫn đến SIEM nhưng mất actor field. Vì vậy, cần xem:

- **Direct effects:** cấu hình hoặc code được thay.
- **Inherited effects:** control bị ảnh hưởng qua platform/service dùng chung.
- **Transitive dependencies:** API, runtime, library, CI/CD, identity, storage.
- **Emergent behavior:** kết hợp các thay đổi độc lập tạo đường truy cập mới.
- **Risk of non-change:** không deploy bản vá có thể nguy hiểm hơn deploy được kiểm soát.

### 4.4. Inventory và unknown là một kết quả review

Nếu không thể xác định production uses một image, credential hoặc API endpoint nào, không nên mặc định “không ảnh hưởng” để bypass review. Có thể:

- Đánh **INCOMPLETE_SCOPE** với owner và hạn bổ sung.
- Xác minh từ deployment manifests, runtime inventory, cloud API và service ownership.
- Triển khai guardrail tạm nếu có dấu hiệu rủi ro cao.
- Không phê duyệt critical boundary change khi chưa biết phạm vi.
- Nếu rủi ro thấp/giới hạn, phê duyệt testing hạn chế theo chính sách chứ không coi là production approved.

## 5. Risk-based classification và mức độ review

### 5.1. Tách “độ phức tạp” khỏi “rủi ro”

Thay đổi lớn có thể an toàn nếu không làm đổi trust boundaries; thay đổi nhỏ có thể rất nguy hiểm. Risk triage nên xét:

| Chiều đánh giá | Câu hỏi |
|---|---|
| **Data sensitivity** | Loại dữ liệu và quyền xử lý nào được thêm/đổi? |
| **Privilege** | Có tạo quyền admin, break-glass, role rộng hay token mới? |
| **Exposure** | Có mở internet, vendor access, trust boundary hoặc route mới? |
| **Business criticality** | Dịch vụ quan trọng với khách hàng/thanh toán/khôi phục không? |
| **Security control delta** | MFA, encryption, logging, monitoring, backup hoặc defense bị giảm hiệu lực? |
| **Threat relevance** | Thay đổi mở attack path đã biết, liên quan incident/findings nào? |
| **Blast radius** | Chỉ một canary hay toàn organization/tenant/multi-region? |
| **Reversibility** | Rollback code có khôi phục dữ liệu, khóa, quyền và trạng thái tương thích? |
| **Observability** | Có đủ signal và synthetic tests để phát hiện regression? |
| **Dependency** | Có IdP/KMS/DNS/vendor làm điều kiện trọng yếu? |
| **Compliance/privacy** | Có nghĩa vụ/region/retention/điều khoản mới cần review? |
| **Prior assurance** | Guardrails đã được kiểm chứng, hay còn findings/unknown? |

Các yếu tố thiếu dữ liệu phải được ghi là **unknown**; không tự gán điểm thấp để thuận tiện go-live.

### 5.2. Risk tiers tham khảo

| Tier | Tình huống điển hình | Độ sâu review |
|---|---|---|
| **Low / standard** | Refactor không đổi public API/trust boundary, dependency update nhỏ đã có automated controls | Tự động kiểm baseline, code review và production smoke/security checks theo policy |
| **Moderate** | Thay API input validation, update permission hạn chế, đổi config của một service | Security reviewer xét delta, test cases và rollback, approval theo ownership |
| **High** | New public API, privileged IAM, dữ liệu nhạy cảm, cross-region, pipeline deploy rights | Threat/diff review sâu, privacy/architecture khi áp dụng, independent review, explicit acceptance |
| **Critical / emergency-impact** | Root/admin boundary, keys/crypto, org-wide policy, removal of security telemetry, untested irreversible migration | Guardrails/hard gates, escalations, strong evidence, change window, two-person review theo policy |

Tier là **phân loại nội bộ minh họa**, không phải danh mục có hiệu lực cho mọi tổ chức. Nếu một điều khoản/hệ thống quy định loại approval hoặc test cụ thể thì cần tuân theo trong scope.

### 5.3. Hard triggers không được che bằng điểm trung bình

Các thay đổi dưới đây có thể đòi review chuyên sâu hoặc chặn triển khai cho đến khi đủ evidence:

- Thay/tắt MFA hoặc privileged access control trên production.
- Tăng public exposure của API có dữ liệu nhạy cảm.
- Thay hiệu lực encryption, key ownership/rotation hoặc khả năng decrypt backup.
- Giảm event audit, retention, integrity hoặc khả năng detection ở hệ thống critical.
- Di chuyển dữ liệu giữa pháp nhân, region, tenant hoặc subprocessor chưa xác định applicability.
- Thay quyền CI/CD, signing, artifact provenance, secret injection.
- Schema/data migration không có cách bảo toàn tính nhất quán hoặc restore.
- Xóa/đổi guardrail platform/organization-wide.
- Có active security incident, known critical control failure hoặc residual risk chưa xử lý trên đường change.
- Emergency rollback không khôi phục đầy đủ state, access và điều kiện security.

**Không có cảnh báo từ scanner không thể vượt qua một hard gate.**

### 5.4. Rủi ro thay đổi và rủi ro không thay đổi

Khi vá một lỗ hổng đang bị khai thác, trì hoãn deploy cũng có rủi ro. Cần so sánh:

- **Risk of deploying:** outage, data corruption, regression, auth outage, mất log.
- **Risk of not deploying:** exploit window, privilege compromise, không đáp ứng deadline.
- **Interim mitigation:** cô lập, giảm quyền, tắt feature, tăng monitoring.
- **Change strategy:** canary, progressive rollout, fail-forward/rollback.
- **Decision authority:** ai chấp thuận rủi ro, trong thời hạn nào.

Review không nên trở thành cơ chế **trì hoãn bản vá quan trọng vì thiếu một checklist không liên quan**; phải giữ những critical gates thực sự cần và dùng emergency path có kiểm soát khi cần.

## 6. Truy vết security requirements và control assertions

### 6.1. Security requirement ≠ test tool result

Ví dụ mục tiêu: **mọi thao tác quản trị production phải được kiểm soát truy cập và có dấu vết điều tra**. Một thay đổi IAM cần nhiều assertions:

- Chỉ actor/role được phép có thể thay cấu hình.
- Mọi đường privileged interactive access đáp ứng yêu cầu xác thực.
- Service identities có scope tối thiểu và có cơ chế revoke.
- Change approval phù hợp policy.
- Các hành động quản trị được ghi với actor, action, resource, time, outcome.
- Log được chuyển/giữ và không bị thay đổi trái quyền.
- Alert/response hoạt động khi có hành vi vi phạm.
- Có rollback/containment an toàn nếu policy sai.

Một kết quả IaC scanner **“no high issues”** không chứng minh toàn bộ những assertions này.

### 6.2. Ma trận requirement → control → evidence

| Requirement | Assertion | Phép kiểm trước deploy | Phép kiểm sau deploy |
|---|---|---|---|
| **Least privilege** | Role mới chỉ cho phép hành động/tài nguyên cần thiết | Policy diff, quyền mô phỏng/test, review owner | Effective permissions + test deny/allow |
| **Strong admin auth** | Đường privileged không bypass MFA theo criterion | Thiết kế SSO/local access và exceptions | Controlled login tests, IdP/platform config |
| **Logging** | Required events tới central store đúng field/kỳ | Pipeline/log source config, mapping | Synthetic event qua source→SIEM, silence alert |
| **Data protection** | Dữ liệu ở đúng boundary, encrypt/retention phù hợp | Data-flow, schema, privacy/security design | Runtime encryption/access tests, retention checks |
| **Secure API** | Object/tenant authorization không cho truy cập vượt quyền | Threat model, API tests, contract tests | Approved negative authz tests, audit events |
| **Supply chain** | Artifact deploy xuất phát từ pipeline được phép | Provenance, dependency results, signing policies | Deployed digest và admission enforcement |
| **Resilience** | Service/backup vẫn đáp ứng recovery objective | Impact BIA, migration/failover design | Restore/failover test, consistency/DR evidence |
| **Detection** | Critical abuse scenarios vẫn được quan sát | Detection rule regression test | Event/test alert trên source/rule thực |
| **Compliance** | Nghĩa vụ applicable còn được đáp ứng | Obligation/control mapping delta | Evidence theo kỳ, exception/retention assessment |

### 6.3. Control ownership và shared responsibility

Một control có thể thuộc nhiều đội. Ví dụ với SaaS:

- Vendor cung cấp tenant audit log, nhưng khách hàng phải bật export và lưu theo kỳ.
- Provider quản trị hạ tầng cloud, nhưng khách hàng cấu hình IAM, key và region.
- Platform team cung cấp RBAC, nhưng application team phải kiểm object authorization.
- Central SOC cung cấp rule detection, nhưng service team phải tạo event có semantic fields chính xác.

Security change review phải nêu **ai làm phần nào** và test tích hợp chứng minh chuỗi hoạt động đầu cuối. Không được “đẩy” finding sang vendor chỉ vì dịch vụ được thuê, cũng không bỏ qua nghĩa vụ contract/SLA mới.

### 6.4. Acceptance criteria nên định nghĩa trước khi triển khai

Một acceptance criterion có chất lượng:

> Sau thay đổi quyền hỗ trợ trong dịch vụ A, mọi principal thuộc role support chỉ có thể đọc resource trong tenant được gán; các request của role support tới resource thuộc tenant khác phải bị từ chối, log audit chứa actor/resource/outcome; không có đường API hoặc batch job tương đương bypass cơ chế này trong phạm vi đã xác định.

Tiêu chí này tốt hơn **“đã sửa API auth”** vì chỉ ra scope, positive/negative case, logging và điều kiện được phép đóng.

## 7. Threat-model delta: tìm đường tấn công mới do thay đổi

### 7.1. Khi nào cần cập nhật threat model?

Không phải mọi commit đều cần vẽ lại sơ đồ hoàn chỉnh. Nhưng cần xem **delta của trust boundaries và threat scenarios** khi:

- API từ internal chuyển sang public.
- Một role được thêm quyền truy cập dữ liệu/secret.
- Tenant isolation, authorization hoặc session model thay đổi.
- Tích hợp SaaS/subprocessor, webhook, OAuth, federation mới.
- Data flow chuyển region hoặc thêm bản sao nhạy cảm.
- Secrets/key lifecycle và trust roots đổi.
- CI/CD, artifact registry hoặc deploy identity đổi quyền.
- Logging hoặc alert suppression tác động khả năng phát hiện.
- DR account, failover traffic và quyền recovery thay đổi.

### 7.2. Mô tả trước/sau dưới dạng luồng dữ liệu

~~~mermaid
flowchart LR
    CUSTOMER["Khách hàng"] --> EDGE["Edge API / WAF"]
    SUPPORT["Nhân viên hỗ trợ"] --> IDP["IdP / MFA"]
    IDP --> API["Support API"]
    EDGE --> API
    API --> AUTHZ["Tenant/object authorization"]
    AUTHZ --> DB["Database khách hàng"]
    API --> AUDIT["Audit event"]
    AUDIT --> SIEM["Central monitoring"]
    API --> VENDOR["Third-party messaging"]
~~~

Giả sử thay đổi bổ sung webhook đến vendor. Review phải xác định **dữ liệu nào đi tới vendor**, ký xác thực webhook, token scope, retry/duplication, privacy/retention, khả năng replay, observability và cơ chế vô hiệu hóa tích hợp. Nếu chỉ review code compile và integration happy-path, một số security objectives có thể bị bỏ qua.

### 7.3. Các câu hỏi threat-model delta

1. **Assets cần bảo vệ:** dữ liệu, keys, danh tính, service availability, log evidence?
2. **Attacker goals:** chiếm quyền, đọc dữ liệu tenant khác, làm sai transaction, cắt log hoặc phá restore?
3. **Entry points:** endpoint, webhook, admin console, support account, CI runner, vendor integration?
4. **Trust boundaries:** chuyển từ internal sang public, từ tenant A sang tenant B, từ khách hàng sang vendor?
5. **Authentication:** ai được xác thực, có đường bypass local/service identity không?
6. **Authorization:** ai có thể thực hiện hành động gì trên tài nguyên nào, theo điều kiện nào?
7. **Data lifecycle:** thu, xử lý, sao chép, mã hóa, lưu, xuất, xóa, backup?
8. **Failure modes:** service phụ thuộc không sẵn sàng, partial rollback, replay, stale cache?
9. **Monitoring:** event nào chứng minh các hoạt động nhạy cảm? Có detector và responder?
10. **Recovery:** có thể khôi phục trạng thái an toàn, dữ liệu nhất quán và quyền đúng không?
11. **Existing findings:** thay đổi có làm một exception trước đây không còn hợp lệ?
12. **Residual uncertainty:** điều gì chưa thể chứng minh, khi nào và bởi ai?

### 7.4. “Có thể xảy ra” khác “đã xảy ra”

Nếu review phát hiện API có thể bỏ qua object ownership check, đó là **risk hypothesis/confirmed control weakness** tùy phép kiểm. Nó **không tự chứng minh** đã có data breach. Nếu production logs cho thấy truy cập vượt quyền thực tế, cần kích hoạt incident triage và bảo toàn bằng chứng phù hợp.

Với các điều kiện chưa có evidence, ghi **UNKNOWN/INCONCLUSIVE** và kiểm chứng có hạn; không viết "đã an toàn" hay "đã bị tấn công" khi chưa đủ căn cứ.

## 8. Các phương pháp Security change review

### 8.1. Diff review có ngữ nghĩa bảo mật

Không chỉ xem dòng được sửa. Cần đọc:

- IAM policy diff: resources/actions/conditions/trust principals tăng hay giảm?
- IaC plan: tài nguyên mới, security group/network routes, log sinks, encryption/retention.
- Kubernetes manifests: service account, RBAC, securityContext, admission, network policy, secrets.
- Application diff: authentication, authorization, serialization, file upload, input/output, logging.
- Database migrations: schema, data classification, encryption, rollback semantics và business invariants.
- CI/CD diff: runner permissions, approval bypass, artifact signing, secret exposure, deployment credentials.
- Vendor/contract diff: data processing, subprocessors, support access, recovery promises.
- Detection diff: parser fields, rule logic, thresholds, suppressions, alert routes.
- Backup/DR diff: restore path, KMS, identity, region, recovery dependencies.

### 8.2. Review theo rủi ro cần nhiều loại evidence

| Phương pháp | Hỗ trợ kết luận | Giới hạn |
|---|---|---|
| Architecture/threat review | Design hợp lý với kịch bản được xét | Chưa chứng minh runtime đúng |
| Static analysis / SAST | Phát hiện một số patterns trong source | Không bao phủ mọi logic business/authz |
| SCA / dependency scan | Nhận diện package/advisory theo inventory | Có thể sai backport, path hoặc deployment |
| IaC policy scan | Kiểm các baseline đã định nghĩa trước deploy | Console drift và data plane behavior khác |
| Container/image scan | Phát hiện package/config ở image | Không chứng minh mọi pod running đã update |
| Authz/abuse-case tests | Kiểm positive/negative access decisions | Chỉ theo tập role, resource và endpoint đã test |
| Dynamic testing / pen test được phép | Thử attack paths trong scope | Có giới hạn thời gian và quyền; không thay vận hành liên tục |
| Runtime effective-config check | Xác nhận policy/deployed artifact sau change | Snapshot không tự chứng minh cả kỳ |
| End-to-end synthetic event | Xác nhận event đi qua logging/detection path | Một event test không chứng minh mọi event class |
| DR/restore test | Kiểm phục hồi theo failure scenario | Tabletop hoặc component test không chứng minh end-to-end |
| Review record / approval trail | Quyết định và trách nhiệm có dấu vết | Ticket APPROVED không bảo đảm control kỹ thuật PASS |

### 8.3. Positive và negative tests

Ví dụ thay đổi role của nhân viên hỗ trợ:

- **Positive test:** role support có thể xem ticket thuộc tenant được phân công.
- **Negative test:** role support không đọc được ticket tenant khác.
- **Boundary test:** cùng một ticket qua API list, detail, export, webhook và batch processing có áp một chính sách?
- **Audit test:** hành động được phép/bị từ chối có event đúng actor/resource/outcome?
- **Regression test:** role admin và role read-only khác không bị vô tình mất quyền hoặc tăng quyền?
- **Runtime test:** production thực sự dùng policy/artifact mới, không chỉ staging.

Chỉ chạy happy-path khiến reviewer bỏ sót nhiều sai lệch bảo mật.

### 8.4. Review manual và automation nên bổ sung nhau

Các công cụ tự động có thể đảm nhận:

- Formatting, linting và policy baseline rõ ràng.
- Dependency/image/secret scanning theo định nghĩa.
- Test IAM/authorization với fixtures/identities có kiểm soát.
- Conformance của IaC/GitOps.
- Synthetic event, schema checks và drift detection.
- Evidence metadata, links và release provenance.

Con người thường cần phân tích:

- Dữ liệu và tác động nghiệp vụ mới.
- Threat model/attack path chưa biểu diễn bằng rule.
- Mâu thuẫn giữa availability, privacy, security và remediation.
- Phạm vi hợp đồng, pháp lý, risk acceptance.
- Ranh giới trách nhiệm với vendor.
- Sự phù hợp của evidence và quyết định khi còn bất định.

**Tự động hóa giảm thao tác lặp lại, không loại bỏ yêu cầu accountability.**

## 9. Review thay đổi Identity & Access Management

### 9.1. Vì sao IAM là nhóm change nhạy cảm?

Một thay đổi quyền không chỉ thêm/bớt chức năng. Nó có thể mở khả năng:

- Đọc dữ liệu nhạy cảm hoặc cross-tenant.
- Thay cấu hình bảo mật, disable logging/detection.
- Đọc/chỉnh sửa secrets, key material hoặc backup.
- Assume role sang account khác và làm tăng blast radius.
- Bỏ qua approval workflow hoặc tách nhiệm vụ.
- Tạo tài khoản mới ngoài phạm vi MFA/PAM.
- Lấy token sống lâu, không thể revoke hoặc thiếu audit.
- Thay trust boundary giữa khách hàng, nhà cung cấp và service.

Security change review phải đánh giá **effective permissions và đường truy cập thực tế**, không chỉ tên role. Một policy khai báo “ReadOnly” có thể kèm quyền khác thông qua inherited membership, trust policy hoặc resource-based policy.

### 9.2. Checklist thay đổi role/policy

- **Subject:** human, workload identity, service account, vendor support, emergency principal?
- **Action:** hành động cho phép/từ chối nào được thêm, bỏ, hoặc thay condition?
- **Resource:** một tài nguyên, cả account, organization hay wildcard?
- **Context:** MFA, source network, device, session duration, approval, tenant?
- **Trust:** ai có thể assume/cấp/ủy quyền role?
- **Lifecycle:** provisioning, review, expiry, revoke và offboarding?
- **Logging:** event cấp quyền, sử dụng quyền và thay trust có được ghi?
- **Break-glass:** có thể phục hồi IdP khi lỗi, nhưng không tạo bypass vĩnh viễn?
- **Existing principals:** policy sẽ ảnh hưởng bao nhiêu tài khoản đang hoạt động?
- **Rollback:** có khôi phục quyền cần thiết cho ứng cứu/DR nếu thay đổi bị lỗi?

### 9.3. Ví dụ một thay đổi IAM trông nhỏ nhưng rủi ro lớn

Giả sử policy trước chỉ cho ứng dụng lấy object tại một bucket cụ thể. Sau thay đổi, resource được mở sang mọi bucket. Dù diff một dòng, security review phải hỏi:

1. Vì sao business cần quyền rộng hơn?
2. Có thể cấp quyền trên prefix/bucket cần thiết thay vì wildcard?
3. Có deny cho sensitive resources và cross-account paths không?
4. Có test chứng minh quyền ngoài phạm vi bị từ chối?
5. Nếu key bị lộ, blast radius mới là gì?
6. Có telemetry về data access và cảnh báo không?
7. Có thể rollback ngay mà không làm mất dịch vụ không?

Ví dụ JSON minh họa về **quy tắc nên xem xét**, không phải policy deploy:

~~~json
{
  "before": {
    "Action": ["storage:GetObject"],
    "Resource": ["arn:example:storage:::team-a/*"]
  },
  "after": {
    "Action": ["storage:GetObject"],
    "Resource": ["arn:example:storage:::*"]
  },
  "review": {
    "risk": "Increased data-access blast radius",
    "required": [
      "Business justification",
      "Effective-permission evaluation",
      "Cross-boundary deny tests",
      "Data-owner approval when applicable",
      "Rollback and audit validation"
    ]
  }
}
~~~

Các resource strings chỉ là ký hiệu giả định. Không áp dụng chúng trực tiếp cho provider. Đánh giá semantics phụ thuộc mô hình IAM thật, explicit deny, session policies và resource policies.

### 9.4. Kiểm thử IAM sau triển khai

Một bộ retest có thể gồm:

- Đối soát principal inventory với role/policy hiệu lực.
- Test **allowed action** theo business requirement.
- Test **disallowed actions** trên tài nguyên ngoài scope.
- Test đường federation/local/break-glass tương ứng.
- Kiểm tra event trace cho cấp quyền và sử dụng quyền.
- Đảm bảo token/session cũ không giữ quyền ngoài ý muốn theo semantics hệ thống.
- Test rollback/disable path trong phạm vi an toàn khi cần.
- Xác nhận external/vendor principals không được thừa hưởng quyền ngoài dự kiến.

**Chỉ xem IAM diff trước deploy là chưa đủ** nếu effective policy runtime hoặc inherited permissions có thể khác.

## 10. Review thay đổi dữ liệu, privacy và database migration

### 10.1. Data change ảnh hưởng security thế nào?

Đổi schema hoặc pipeline có thể thay:

- Loại dữ liệu được thu và mức độ nhạy cảm.
- Ai được xem/xử lý, tenant isolation và data ownership.
- Vị trí lưu, region, replication, backup và data export.
- Retention, deletion và xử lý yêu cầu của chủ thể dữ liệu theo nghĩa vụ áp dụng.
- Dữ liệu đưa vào log, tracing, analytics, third-party subprocessors.
- Khóa mã hóa, quyền đọc/ghi và nơi chứa secrets.
- Data integrity constraints và giao dịch trước/sau migration.

Một migration database “chỉ thêm cột” vẫn có thể làm lộ dữ liệu nếu cột chứa thông tin nhạy cảm mới được trả về trong API serializer hoặc được gửi vào analytics.

### 10.2. Checklist data-flow delta

| Yếu tố | Câu hỏi kiểm tra | Bằng chứng |
|---|---|---|
| Data classification | Dữ liệu mới thuộc loại nào, có thay scope pháp lý/hợp đồng? | Data inventory, approved classification |
| Collection | Dữ liệu nào thực sự được thu, có minimization? | API schema, event sample đã che nhạy cảm |
| Access | Role nào được quyền đọc/ghi, có cross-tenant access? | Effective grants, negative authorization test |
| Transfer | Thêm endpoint, webhook, region, subprocessor hay external export? | Data-flow diagram, config, contract review |
| Encryption | At-rest/in-transit, keys và boundary có đổi? | Config, KMS/IAM policy, connectivity test |
| Retention | Dữ liệu chính, cache, backup, export, log được giữ thế nào? | Lifecycle policies, deletion test |
| Integrity | Mapping, constraints, transaction consistency có giữ? | Pre/post reconciliation, checksums khi phù hợp |
| Rollback | Có thể về schema/code trước mà không mất dữ liệu? | Compatibility plan, restore rehearsal |
| Observability | Log/trace có chứa PII/secrets mới không? | Synthetic data test, log field review |
| Compliance | Applicable obligations có được đánh giá lại? | Obligation change record, approvals |

### 10.3. Expand–migrate–contract

Một cách làm an toàn với schema migration là:

1. **Expand:** thêm trường/bảng/cơ chế mới theo cách backward-compatible.
2. **Migrate:** chuyển dần dữ liệu hoặc read/write paths, có checkpoint và reconciliation.
3. **Verify:** kiểm tính nhất quán, authorization, encryption và hành vi ứng dụng.
4. **Contract:** xóa schema/đường cũ chỉ khi consumer và rollback plan đã được cập nhật.

Mô hình này **không áp dụng máy móc** cho mọi thay đổi. Với data deletion, key rotation hoặc destructive migration, có thể không có rollback thực sự; cần backup/restore với acceptance rõ và quyết định rủi ro trước thay đổi.

### 10.4. Migration acceptance criteria cần có dữ liệu

Ví dụ chuyển dữ liệu đơn hàng giữa hai hệ thống:

- Tổng record theo partition và điều kiện lọc khớp trong tolerance được phê duyệt.
- Các business invariants: tổng số giao dịch, trạng thái thanh toán, tham chiếu khách hàng, không duplicate key.
- Dữ liệu được mã hóa và quyền truy cập còn đúng sau cutover.
- Không xuất dữ liệu nhạy cảm qua logs/errors.
- Event audits chứa actor và trace ID cần thiết.
- Failover/rollback path không tạo **split-brain**, record divergence hoặc token vượt quyền.
- Kỳ retention/deletion được cập nhật và kiểm trong phạm vi.
- Các consumer cũ không thể truy vấn dữ liệu ngoài quyền.
- Có báo cáo reconciliation gắn batch/version/cutoff và sample/exception.

**Backup snapshot có tồn tại không đủ chứng minh rollback được:** cần biết khôi phục xong ứng dụng có tương thích schema, khóa, message queue và downstream contracts hay không.

### 10.5. Data protection là quyết định liên ngành

Khi change liên quan dữ liệu cá nhân/region/subprocessor, có thể cần privacy/legal/compliance review trong phạm vi thẩm quyền. Security reviewer cung cấp đánh giá technical controls và evidence, **không tự kết luận nghĩa vụ pháp luật** nếu chưa có căn cứ hoặc quyền chuyên môn.

## 11. Review cloud, network và infrastructure change

### 11.1. Các điểm nhạy cảm trong cloud/IaC

- Cloud account/project/subscription mới.
- Organization policy, SCP/guardrail, permissions boundary và trust relationship.
- Public IP, ingress rules, load balancer, private endpoints.
- Network segmentation, service mesh, egress, DNS.
- Object storage ACL/retention/encryption.
- KMS key policy, secret store, key rotation.
- Audit log routes, SIEM destination, monitoring.
- Backup snapshot, replication, DR region/account.
- Autoscaling, infrastructure quotas và failure domains.
- IaC backend, state secrets, drift và manual overrides.

### 11.2. Review một thay đổi ingress

Thay đổi từ private API sang public API có thể thêm các kịch bản:

1. Access từ Internet không qua VPN.
2. Anonymous/authenticated clients và identity federation.
3. Rate limiting, abuse/throttling, DDoS assumptions.
4. Token validation và edge-to-service identity.
5. TLS termination, mTLS hoặc trusted proxy headers.
6. Input/output validation, file upload hoặc deserialization.
7. Credential leakage qua query/log/redirect.
8. Data/tenant authorization, caching và CORS nếu áp dụng.
9. Monitoring của 401/403/5xx, unusual volume và access events.
10. Rollback network route và secret exposure nếu ngừng public.

Một scan cấu hình không thể tự xác định mọi kịch bản abuse của business logic; cần threat-model delta và authz tests.

### 11.3. Infrastructure plan không phải trạng thái production

Ví dụ cùng một thuộc tính:

| Tầng bằng chứng | Có thể chứng minh | Giới hạn |
|---|---|---|
| IaC source diff | Ý định thay cấu hình | Có thể thiếu tài nguyên quản trị ngoài IaC |
| IaC plan | Thay đổi dự kiến theo trạng thái provider tại lúc chạy | Có thể khác khi apply do race/drift |
| Policy-as-code result | Rule đã đánh giá trên plan/config | Chỉ bao phủ các rules và paths đã khai báo |
| Apply/deployment log | Provider chấp nhận hành động thay đổi | Không luôn chứng minh effective security state |
| Runtime API export | Trạng thái thực tế sau deploy | Snapshot; không chứng minh controls hoạt động cả kỳ |
| Controlled access/log test | Hành vi được phép/cấm và event được quan sát | Chỉ đại diện scenario và sample |
| Drift monitoring | Sai lệch sau review có được nhận biết | Phụ thuộc asset population và sensor health |

Vì vậy, một high-impact change cần ít nhất **planned-state checks và effective-state verification**, kèm xác nhận đã được áp lên đúng tài nguyên và account.

### 11.4. Review nguồn gián tiếp

Thay một gateway, proxy hoặc DNS có thể:

- Bỏ qua authentication/authorization layer.
- Cắt luồng security telemetry và làm hỏng source attribution.
- Chuyển dữ liệu sang region khác.
- Làm DR failover trỏ vào endpoint sai.
- Cho phép bypass WAF qua đường internal khác.
- Làm log ghi địa chỉ proxy thay vì client/actor.
- Phá mTLS/identity propagation.

Cần review **đầu cuối**, không chỉ thành phần đang thay.

## 12. Review application và API change

### 12.1. Các lớp cần kiểm

- **Authentication:** identity validation, session/token lifecycle, MFA/hardening nếu áp.
- **Authorization:** object/field/tenant permissions, role inheritance, privilege transitions.
- **Input handling:** validation, serialization/deserialization, file uploads, parsers.
- **Output handling:** lọc trường dữ liệu, serialization, errors và tránh thông tin nhạy cảm.
- **Secrets:** config, environment, repo, logs, build output, client bundles.
- **Business rules:** transaction integrity, idempotency, replay, fraud/abuse scenarios.
- **External calls:** SSRF-type boundaries, allowlisted destinations, timeouts và response trust.
- **Dependencies:** updates, license/policy, artifact provenance, runtime compatibility.
- **Observability:** security events đủ actor/action/resource/outcome, không lộ dữ liệu.
- **Availability:** rate limits, retries, queue/backpressure, fail-safe defaults.
- **Privacy/data:** minimization, retention và approved sharing paths.

### 12.2. API contract changes

Ví dụ thêm endpoint export customer records:

| Review question | Acceptance evidence |
|---|---|
| Ai có quyền export và với tenant/resource nào? | Authorization matrix và negative tests |
| Có thể enumerate hoặc export dữ liệu tenant khác? | Object-level deny tests, pagination checks |
| Có giới hạn khối lượng/rate/async job không? | Abuse controls, backpressure tests |
| Output có dữ liệu mới hoặc PII ngoài dự kiến? | Schema/classification review và redacted sample |
| Token scope và thời hạn tải file? | Effective permissions, signed-link expiry test |
| Event audit có đầy đủ actor, job ID, resource? | Synthetic export event + SIEM inspection |
| Tải lỗi/đứt kết nối có để lại file tạm public? | Failure cleanup test |
| Có thể revoke export permission và token? | Revocation/denial test |
| Có data retention/delete policy cho export? | Object lifecycle và deletion test |

### 12.3. Test logic quyền không thể chỉ dựa SAST

Một security reviewer có thể yêu cầu **authorization matrix**:

| Role | Đọc ticket trong tenant | Đọc ticket tenant khác | Export toàn bộ | Sửa policy |
|---|---|---|---|---|
| Customer agent | Allow theo assignment | Deny | Deny | Deny |
| Tenant admin | Allow trong tenant | Deny | Allow theo policy | Deny |
| Platform support | Chỉ khi có just-in-time approval | Deny nếu ngoài hỗ trợ được phép | Deny mặc định | Deny |
| Platform security admin | Theo đặc quyền được phê duyệt | Theo procedure riêng | Theo policy | Theo approval |

Dữ liệu là giả định. Test cần bao gồm trường hợp **role bị hạ quyền, session cũ, API route khác và batch export**, không chỉ UI hiển thị nút.

### 12.4. Ứng dụng Java và ví dụ kiểm thử chính sách

Với service Java/Spring, security change review có thể yêu cầu:

- Thử security filter chain và method-level authorization thực sự kích hoạt.
- Kiểm integration test chạy với identity/claims tương ứng production.
- Đảm bảo endpoint mới không nằm ngoài security matchers.
- Kiểm multi-tenant repository filters, không tin tenant ID từ client nếu chưa xác minh.
- Kiểm serialization tránh trả trường nhạy cảm do DTO thay đổi.
- Kiểm audit events và exception handler không ghi tokens hoặc PII.
- Kiểm rollback/resilience khi session/token schema đổi.

Ví dụ *pseudocode test* (không phải test chạy sẵn cho một codebase):

~~~java
@Test
void supportAgentCannotReadOtherTenantOrder() {
    TestIdentity agent = identity("support", "tenant-A");
    ApiResponse response = callAs(agent, "GET", "/orders/tenant-B-order");
    assertEquals(403, response.status());
    assertAuditEvent("ORDER_ACCESS_DENIED", agent.id());
}

@Test
void supportAgentCanReadAuthorizedOrder() {
    TestIdentity agent = identity("support", "tenant-A");
    ApiResponse response = callAs(agent, "GET", "/orders/tenant-A-order");
    assertEquals(200, response.status());
    assertOnlyApprovedFields(response.body());
}
~~~

Lớp TestIdentity, ApiResponse và các helper chỉ để minh họa **ý định assertion**; không được sao chép vào production như thư viện có sẵn. Test 403/200 cần kiểm thêm phân quyền theo resource, không suy ra toàn bộ API đã an toàn chỉ từ hai case.

## 13. Review container, Kubernetes và software supply chain

### 13.1. Container/image changes

Cần xem:

- Image digest thực sự deploy, không chỉ mutable tag.
- Base image, package vulnerabilities, provenance và build context.
- User/container privileges, root filesystem, security context.
- Capabilities, host mounts, privileged mode, host networking.
- Secrets injection, environment variables và log leakage.
- Network policies, service-to-service identity, egress.
- Admission controls, resource constraints, liveness/readiness.
- Runtime compatibility và fallback image khi rollback.
- Registry/trust policies, dependency pinning và software integrity.

**Một image scan PASS chưa chứng minh deployment cấu hình an toàn.** Ngược lại, workload runtime tốt chưa chứng minh pipeline ngăn artifact không đáng tin được triển khai.

### 13.2. Kubernetes security review

Một thay đổi service account hoặc RBAC cần xét permissions tại cluster, namespace, aggregated roles và external cloud identity (nếu tích hợp). Một thay đổi ingress controller cần xét đường bypass, TLS, auth headers, backend routing và log fidelity.

Ví dụ policy yêu cầu workload không chạy privileged, không hostPath mount ngoài ngoại lệ và dùng service account tối thiểu. Review có thể gồm:

1. So sánh manifest và Kustomize/Helm render cuối cùng, không chỉ chart values.
2. Xác nhận policy-as-code/admission enforcement ở cluster cần deploy.
3. Kiểm các manifests phát sinh qua operator hoặc mutating webhook.
4. Xác nhận pod/spec effective sau rollout.
5. Test quyền gọi API cluster của workload trong phạm vi được phê duyệt.
6. Kiểm network policy thực tế và runtime events.
7. Kiểm các pod cũ/rollout lỗi và quyết định cleanup.
8. Ghi evidence liên kết namespace/cluster/revision/digest.

### 13.3. CI/CD thay đổi có thể tăng quyền lớn

Các điểm cần kiểm:

- Ai có thể sửa pipeline, protected branch và policy?
- Runner dùng ephemeral identity hay static privileged token?
- Pull request từ nguồn không tin cậy có thể đọc secrets hoặc deploy credential?
- Artifacts được build, kiểm integrity/provenance và promote thế nào?
- Deployment approvals và environment protection có đường bypass?
- Signing keys/trust anchors do ai quản lý và có rotate/revoke được?
- Build logs có chứa secrets hoặc PII?
- Pipeline policy scans có chạy trên **artifact/plan đúng** bản được deploy?
- Emergency workflow có lưu audit trail và kiểm lại sau thay đổi?

Một commit chỉ sửa workflow file có thể ảnh hưởng security posture lớn hơn nhiều commit đổi business code.

### 13.4. Guardrail hai lớp

**Trước deploy:** branch protections, build/test, SCA, image scan, IaC scans, artifact checks, security approvals theo risk.

**Sau deploy:** observed image digest, pod effective config, role/secret access, log/event test, baseline drift và rollback readiness.

Hai lớp giúp tránh trường hợp pipeline đã PASS nhưng runtime chạy artifact khác hoặc một console change tắt security policy sau đó.

## 14. Review logging, monitoring và detection changes

### 14.1. “Giảm noise” có thể tạo blind spot

Việc giảm log volume, tắt rule hoặc tăng threshold cần phân biệt:

- **Optimization hợp lệ:** giảm duplicate, normalize field, sampling phù hợp với tiêu chí, vẫn giữ khả năng phát hiện cần thiết.
- **Security degradation:** bỏ audit events quan trọng, bỏ actor/resource, suppression vô hạn, mất source hoặc route alert.
- **Uncertainty:** chưa có test chứng minh detector vẫn bắt các abuse scenarios.

Một dashboard cho thấy số alert giảm **không chứng minh false positives giảm hoặc khả năng phát hiện tốt hơn**.

### 14.2. Evidence trước và sau thay đổi detection

| Hạng mục | Pre-deploy | Post-deploy |
|---|---|---|
| Event source | Inventory, required event classes | Event synthetic từ nguồn thực |
| Parser | Schema/unit tests, field mapping | Actor/action/resource/outcome trong index |
| Correlation | Positive/negative scenarios, expected matches | Rule version và matched events |
| Suppression | Scope, reason, owner, expiry | Test scenario ngoài suppression vẫn alert |
| Routing | Routing logic, severity thresholds | Alert tới đúng queue/on-call, ack nếu bắt buộc |
| Silence detection | Heartbeat/expected source rules | Fault test/alert khi source ngừng |
| Retention/integrity | Control design, policy, permissions | ACL/effective retention và trace evidence |
| Incident response | Playbook/escalation cập nhật | Tabletop/controlled test khi cần |

### 14.3. Kiểm tra end-to-end thay vì “agent healthy”

Một source có heartbeat bình thường nhưng parser bỏ field hoặc security event bị drop thì control thất bại. Để xác minh logging change:

1. Tạo event an toàn trong môi trường/production scope được phép.
2. Đánh dấu marker và timestamp nguồn.
3. Truy event ở collector, transport, index.
4. Kiểm actor/action/resource/outcome, tenant/service ID, event time.
5. Kiểm expected detection rule và alert route.
6. Kiểm data lag, retries, duplicate, missing event warning.
7. Ghi test ID, source ID, evidence và limitations.

**Không tìm thấy event** có thể do query/index mapping sai, nên cần xác minh trước khi kết luận sensor tắt. **Tìm thấy một event** không chứng minh mọi event class được giữ trong cả kỳ.

### 14.4. Alert threshold và hiệu lực

Khi thay detection threshold, nên so sánh cùng bộ positive/negative tests; xem recall/false negatives, false positives, alert volume và triage load. Nếu dữ liệu production không có ground truth đầy đủ, ghi giới hạn thay vì tuyên bố “false-positive rate giảm 50%” chỉ vì analyst đóng ít case.

## 15. Review resilience, backup, DR và rollback changes

### 15.1. Rollback code không nhất thiết rollback hệ thống

Các thay đổi khó đảo ngược:

- Database schema đã xóa cột hoặc transform dữ liệu không thể đảo.
- Key rotation làm bản backup cũ không giải mã được.
- Thay message format khiến consumer cũ không đọc được.
- Session/token migration khiến account bị khóa hoặc privilege bị lệch.
- Cross-region replication làm lặp, thiếu hoặc xung đột transaction.
- DNS/certificate change có thời gian cache, external dependencies.
- Vendor API upgrade thay behavior không có downgrade path.
- Data deletion/retention policy đã chạy, không thể lấy lại dữ liệu hợp lệ.

Security change review phải phân biệt **code rollback**, **config rollback**, **data restore**, **fail-forward** và **business recovery**. Một playbook “revert commit” không đủ khi dữ liệu đã thay đổi.

### 15.2. Bộ câu hỏi resilience

- Change có làm thay RTO/RPO hoặc service dependency được BIA phê duyệt?
- Backup snapshots và encryption keys có tồn tại ở recovery domain?
- KMS key policies, IAM/SSO, DNS, network và secrets có dùng được khi failover?
- Recovery có giữ data integrity, isolation, auth và logging?
- Rollback có làm mất dữ liệu được ghi sau migration không?
- Có test khôi phục với schema mới và schema cũ khi phù hợp?
- Các DR runbooks, contact và escalation đã cập nhật?
- Có monitoring cho replication lag, backup freshness và restore failures?
- Thay đổi có làm tăng shared failure domain hoặc quyền xóa backup?
- Điều kiện dừng rollout và quyết định degraded mode là gì?

### 15.3. Ví dụ failure mode ở key rotation

Giả sử workload đổi sang key mới. Mọi request sản xuất tiếp tục chạy nên smoke test PASS, nhưng recovery account không có quyền sử dụng key mới để decrypt backup. Đây là **silent recovery gap**.

Acceptance criteria cần gồm:

1. Old/current keys được quản lý theo kế hoạch và vòng đời đã phê duyệt.
2. App có thể encrypt/decrypt dữ liệu hợp lệ sau rotation.
3. Recovery environment được cấp quyền đúng scope, không mở wildcard.
4. Test restore với bản backup đại diện được thực hiện và có data checks.
5. RTO/RPO và security gates có kết quả theo scenario.
6. Key audit logs và failure alerts hoạt động.
7. Kế hoạch thu hồi key cũ không phá dữ liệu còn cần.
8. Khi xảy ra rollback/fail-forward, cả app và backup vẫn đáp ứng nghĩa vụ.

Một smoke test API thành công **không chứng minh DR readiness**.

### 15.4. Canary và monitoring window

Rollout từng bước cần chỉ rõ:

- Sample canary đại diện tenant, traffic và data class nào?
- Rủi ro cao có thể xuất hiện sau nhiều giờ/ngày hoặc trong batch job đêm không?
- Security metrics: auth denials, unusual privilege, key errors, log source health, rate-limit breaches, data export volume.
- Business metrics: transaction integrity, duplicate/loss, latency, error rate.
- Tiêu chí dừng/rollback; ai có thẩm quyền?
- Mức phơi nhiễm tối đa khi canary thất bại.
- Khi nào tăng traffic và mở toàn scope?
- Retest sau full rollout và review sau monitoring window.

Canary không phải bằng chứng mọi user/region/tenant đều đã được kiểm. Cần đối soát **population sau rollout**.

## 16. Trách nhiệm review, approvals và separation of duties

### 16.1. Vai trò cần phân biệt

| Vai trò | Trách nhiệm |
|---|---|
| **Change requester** | Mô tả mục tiêu, scope, business impact và dependency |
| **Service/business owner** | Xác nhận criticality, yêu cầu nghiệp vụ, khả năng chấp nhận gián đoạn |
| **Change implementer** | Thiết kế/deploy/rollback, lưu change evidence |
| **Control owner** | Đảm bảo control objective và cách vận hành trong service/platform |
| **Security reviewer/assessor** | Đánh giá delta, assertions, evidence, gaps và retest |
| **Architecture/platform owner** | Đánh giá trust boundaries, dependencies, cloud/IAM/KMS |
| **SOC/IR/DR owner** | Xác nhận detection, response và recovery khi bị ảnh hưởng |
| **Privacy/legal/compliance** | Xem dữ liệu/nghĩa vụ/hợp đồng trong phạm vi áp dụng |
| **Risk acceptance authority** | Chấp thuận residual risk, ngoại lệ và giới hạn theo policy |
| **Release/change approver** | Quyết định go/no-go theo change governance |

Một người có thể giữ nhiều vai trò trong tổ chức nhỏ, nhưng với **critical change**, nên có cơ chế review độc lập hoặc ít nhất phân tách bước triển khai và bước xác minh theo chính sách.

### 16.2. Phê duyệt không nên thay bằng số lượng chữ ký

Một change có mười approvers nhưng không ai xác minh negative authorization tests có thể kém assurance hơn change với một reviewer rõ trách nhiệm, bằng chứng chặt chẽ và guardrails tự động.

Phê duyệt hữu ích cần ghi:

1. **Approved scope:** service, environment, data, version, change window.
2. **Conditions:** control gates, tests, mitigations, monitoring, rollback.
3. **Decision rationale:** vì sao đủ căn cứ hoặc vẫn có residual risk nào.
4. **Authority:** người phê duyệt đúng risk level, không chỉ người tạo ticket.
5. **Validity:** approval còn hiệu lực cho phiên bản/diff đang deploy?
6. **Exceptions:** có hạn, owner, compensating controls và review date.
7. **Revocation/review trigger:** thay đổi không theo kế hoạch, test fail, threat/incident mới.

Approval cho **commit A** không mặc định bao phủ **commit B** khi B thay IAM, dependencies hoặc data flow.

### 16.3. RACI tham khảo

R = Responsible (người thực hiện); A = Accountable (chịu trách nhiệm cuối); C = Consulted (tham vấn); I = Informed (thông báo).

| Hoạt động | Business owner | Engineering | Security assurance | Risk owner | SOC/IR |
|---|---|---|---|---|---|
| Intake và business justification | **A** | **R** | C | I | I |
| Security impact/threat review | C | R | **A/R** | C | C |
| Control implementation/test | I | **A/R** | C | I | C |
| High-risk residual decision | C | C | C | **A/R** | C |
| Deploy/canary/rollback | **A** theo change policy | **R** | C | I | C |
| Post-deploy security validation | I | R | **A/R** | I | C |
| Incident escalation | C | R | C | I | **A/R** theo IR plan |
| Verified closure và audit record | I | C | **A/R** | C | I |

Bảng là **mẫu**, không phải cấu trúc bắt buộc. Tổ chức cần tự xác định vai trò accountable phù hợp mức rủi ro, luật và chính sách quản trị.

### 16.4. Xử lý xung đột lợi ích

Một người sửa IAM policy critical có thể cung cấp evidence, nhưng không nên tự kết luận **toàn bộ điều kiện bảo mật đã đạt** nếu chính sách yêu cầu kiểm chứng độc lập. Khi thiếu nhân sự, có thể dùng:

- Mandatory peer review với permissions phù hợp.
- Automated policy gates có audit trail.
- Reviewer từ đội khác cho thay đổi high-impact.
- Controlled read-only verification.
- Post-change retrospective và periodic independent sampling.

Mục tiêu là **giảm sai lệch và giữ accountability**, không tạo bureaucracy khiến khắc phục lỗ hổng bị chậm nguy hiểm.

## 17. Pre-deploy assurance gates và evidence contract

### 17.1. Evidence contract là gì?

**Evidence contract** mô tả những bằng chứng cần có để một change được xét pass một assertion:

- Control ID/security objective.
- Scope: asset/service/environment/role/data.
- Test method và test version.
- Evidence source, timestamp, lineage và trust boundary.
- Điều kiện PASS/FAIL/INCONCLUSIVE/NOT_TESTED.
- Owner và reviewer.
- Kỳ hiệu lực và trường hợp phải refresh.
- Chất lượng population/coverage.
- Cách xử lý missing evidence, false positives và exceptions.

Nó giúp tránh tình huống team nói “đã test” nhưng không biết test gì, trên version nào hoặc với ai.

### 17.2. Change gate ví dụ

| Gate | Security assertion | Evidence trước deploy | Hard stop khi nào? |
|---|---|---|---|
| **G1 Scope** | Mọi affected critical assets/owners được xác định | Inventory diff, service/dependency map | Không biết privileged/data boundary bị ảnh hưởng |
| **G2 IAM** | Không có quyền vượt mức chưa phê duyệt | IAM policy diff/effective simulation, negative tests | Có đường privileged access trái baseline |
| **G3 Data** | Data flow/retention/encryption đúng nghĩa vụ | Data-flow diff, classification, privacy review nếu cần | Chuyển dữ liệu nhạy cảm chưa có approval bắt buộc |
| **G4 Supply chain** | Artifact được build từ nguồn được phép, integrity đúng | Build metadata, provenance/signature theo policy | Artifact/provenance không đáp ứng policy critical |
| **G5 Testing** | Positive/negative tests quan trọng đạt | Authz, abuse-case, CI/test reports | High-risk control assertion FAIL |
| **G6 Observability** | Security telemetry và response path sẵn sàng | Logging/detection test và owner confirmation | Thay đổi phá mất logging required không có mitigation hợp lệ |
| **G7 Recovery** | Rollback/recovery hợp lệ cho change impact | DR/backup/migration plan, tests | Destructive change không có recovery/approval cần thiết |
| **G8 Governance** | Review/exception đúng thẩm quyền | Decision record, risk owner sign-off | Bỏ qua nghĩa vụ/hard gate không được phép |

“Hard stop” phải được định nghĩa theo **policy hiện hành và risk level**, không dùng một danh sách cố định cho mọi thay đổi. Với emergency hotfix, đường phê duyệt có thể rút gọn nhưng vẫn cần các biện pháp bảo vệ quan trọng.

### 17.3. Pipeline pseudocode

~~~yaml
security_change_review:
  trigger:
    - pull_request
    - infrastructure_plan
    - material_runtime_change
  context_required:
    - change_id
    - service_owner
    - in_scope_assets
    - environment
    - security_objectives
  checks:
    - id: "SCOPE"
      verify: "inventory-and-trust-boundary-diff"
    - id: "IAM"
      verify: "effective-permission-risk-and-negative-tests"
      conditional: "privilege-or-identity-changed"
    - id: "DATA"
      verify: "classification-and-flow-review"
      conditional: "data-lifecycle-changed"
    - id: "SUPPLY_CHAIN"
      verify: "approved-provenance-and-artifact-controls"
    - id: "LOGGING"
      verify: "event-and-alert-path-test"
      conditional: "telemetry-or-critical-runtime-changed"
    - id: "RESILIENCE"
      verify: "rollback-and-recovery-acceptance"
      conditional: "stateful-or-critical-change"
  results:
    pass: "ALLOW_WITH_RECORDED_SCOPE"
    fail: "BLOCK_OR_ESCALATE_ACCORDING_TO_POLICY"
    inconclusive: "REVIEW_REQUIRED"
  after_deploy:
    - "verify-effective-runtime-state"
    - "execute-required-end-to-end-tests"
    - "check-data-quality-and-monitoring"
    - "record-assurance-verdict-and-closure"
~~~

Đây là **pseudocode YAML minh họa**, không phải cấu hình chạy sẵn của GitHub Actions, GitLab, Jenkins hoặc công cụ policy cụ thể. Một triển khai thật cần viết rule, bảo vệ secrets và kiểm thử logic đối với từng loại change.

### 17.4. Bảo vệ tính toàn vẹn của chính pipeline

Nếu requester có thể:

- Tắt security scans bằng sửa workflow.
- Thay evidence URL thành một report không đúng artifact.
- Chạy privileged runner với code chưa được review.
- Sửa policy gate và tự approve cùng một PR.
- Deploy artifact khác với artifact được kiểm.

thì “CI PASS” không đáng tin. Cần controls cho **branch protections, least privilege, protected environments, trusted runners, signed/provenance metadata, independent approval và audit trail** theo mức rủi ro.

### 17.5. Đối chiếu chính xác artifact đã duyệt với artifact deploy

Một review có thể PASS cho source commit và build A, nhưng deployment có thể dùng mutable tag trỏ đến image B. Evidence contract phải có **commit/ref, image digest/package checksum, pipeline run ID, config version, environment/account và deployment timestamp**, rồi xác minh runtime dùng đúng phiên bản.

## 18. Post-deploy verification và monitoring window

### 18.1. Tại sao cần verify sau deploy?

Pre-deploy test có thể chạy với fixtures, staging permissions, network và dữ liệu khác production. Sau deploy còn có thể xuất hiện:

- IAM policy thừa kế khác staging.
- Resource đã tồn tại với config drift.
- Một cloud account/region không được cập nhật.
- App cũ vẫn chạy trên pod/instance chưa rollout.
- Parser/collector sai mapping với event thực.
- DNS/cache, long-lived sessions hoặc database migration tạo trạng thái hỗn hợp.
- Backend chỉ kích hoạt đường lỗi khi đủ traffic, tenant hoặc batch job.
- Backup/DR permission không khớp với key mới.
- Rollback plan không còn khả thi vì schema đã đổi.

### 18.2. Những kiểm tra hậu triển khai tối thiểu

1. Xác minh deployment IDs/artifact digest/config version ở đúng account/cluster/region.
2. Đối soát thực tế với **approved changed population**; không quên canary pods còn sót.
3. Chạy positive/negative tests có kiểm soát trên các security assertions trọng yếu.
4. Kiểm effective permissions, network paths, key usage và access boundaries.
5. Kiểm audit log/detection events nguồn đến đích và route alert nếu thuộc scope.
6. Đo business invariants, transaction/data consistency và functional regression.
7. Kiểm backup/DR/security recovery gates khi change có ảnh hưởng.
8. Theo dõi error rates, unusual denies, latency, risk events, source silence.
9. Phân loại deviations thành expected, false alert, confirmed gap hoặc unknown.
10. Ghi kết quả, evidence ID, mốc UTC, owner và quyết định rollback/fail-forward/keep.
11. Sau monitoring window, tổng kết risk remaining và action chưa đóng.
12. Cập nhật runtime baseline, threat model/control mapping khi change được chấp nhận.

### 18.3. Bốn trạng thái cần tách

| Trạng thái | Ý nghĩa |
|---|---|
| **DEPLOYED_UNVERIFIED** | Thay đổi đã deploy, các assertion bắt buộc chưa được kiểm |
| **VERIFYING** | Đang đo effective state, test, observability và business gates |
| **VERIFIED_WITH_SCOPE** | Các assertions trong phạm vi/kỳ kiểm đạt, có evidence và limitations |
| **FAILED_OR_INCONCLUSIVE** | Có control failure hoặc thiếu dữ liệu; phải xử lý/risk triage |

Không chuyển **DEPLOYED_UNVERIFIED** thành VERIFIED vì change ticket đã chuyển “Done” hoặc smoke test chỉ kiểm HTTP 200.

### 18.4. Monitoring window phải có chủ đích

Một change tác động IAM có thể kiểm ngay effective permissions, nhưng behavior của access review cần thời gian. Một data migration có thể yêu cầu kiểm các nightly batch jobs; một rate-limit change cần traffic đại diện. Monitoring window nên gắn:

- Business cycle và batch schedules.
- Data classes/tenant segments có rủi ro.
- Time-to-detect cho event classes quan trọng.
- Chu kỳ làm mới tokens/sessions, credential rotations.
- Data retention/backup checkpoints.
- External dependencies và vendor SLAs.
- Fault injection/DR exercise nếu đủ điều kiện và được cấp quyền.

Khi chưa đủ kỳ để chứng minh operating effectiveness, báo **IMPLEMENTED_PENDING_OPERATIONAL_VALIDATION**, không tự công bố PASS cho toàn kỳ.

### 18.5. Hành động khi phát hiện regression

Nếu hậu triển khai xuất hiện critical control failure:

- Kích hoạt incident/rollback theo mức rủi ro, giữ evidence.
- Cân nhắc containment an toàn và business impact.
- Phân biệt code rollback, config rollback, data restore và fail-forward.
- Không xóa/sửa log để làm biến mất cảnh báo.
- Xác minh rollback thực sự khôi phục quyền, logging, data consistency.
- Ghi root cause và test hồi quy để không lặp lại.
- Cập nhật decision và trạng thái change, không sửa lịch sử approval trước đó.

**Rollback thành công cũng cần security verification.** Ví dụ khôi phục image cũ có thể đưa trở lại một vulnerability đã được vá; risk owner phải xem nguy cơ của cả hai hướng.

## 19. Emergency change, hotfix và thay đổi ngoài pipeline

### 19.1. Emergency không đồng nghĩa bỏ security review

**Emergency change** là thay đổi cần triển khai nhanh để giảm rủi ro nghiêm trọng hoặc khôi phục khả năng vận hành. Ví dụ:

- Thu hồi token production bị lộ.
- Cô lập một workload liên quan incident.
- Hotfix lỗ hổng đang bị khai thác.
- Chặn ingress mới phát hiện public ngoài ý muốn.
- Khôi phục audit pipeline bị tắt.
- Chuyển sang DR khi hệ thống chính không thể vận hành an toàn.

Trong tình huống khẩn cấp, một review đầy đủ như feature release thông thường có thể làm chậm containment. Tuy nhiên vẫn phải có **người quyết định, phạm vi, điều kiện bảo vệ tối thiểu, evidence triển khai, rollback/alternative và hậu kiểm**.

### 19.2. Phương pháp two-stage review

**Giai đoạn trước thay đổi (rút gọn, tập trung rủi ro trực tiếp):**

1. Xác nhận threat/incident/availability trigger và người chỉ huy theo playbook.
2. Xác định asset, data, quyền, blast radius và critical constraints.
3. Chọn containment/hotfix có thể triển khai an toàn nhất trong thời gian khả dụng.
4. Kiểm tra tối thiểu secrets, privilege, data integrity, ability to rollback và logging.
5. Ghi decision/approver theo emergency policy (có thể cơ chế out-of-band được định nghĩa).
6. Chụp/lưu evidence hiện trạng phù hợp trước khi thao tác, bảo vệ chain of custody khi có incident.

**Giai đoạn sau thay đổi (hậu kiểm bắt buộc):**

1. Xác minh control đạt và dịch vụ ổn định trên scope thật.
2. Ghi exact change: ai sửa, lúc nào, bằng kênh nào, phiên bản gì.
3. Đối chiếu manual config với source of truth/IaC.
4. Đánh giá tác động lên security controls khác.
5. Cập nhật incident/change record và exception nếu có.
6. Lập corrective/preventive action để tránh emergency lặp lại.
7. Thực hiện independent review và retest trong hạn theo policy.
8. Đồng bộ baseline, dashboards và asset inventory.

### 19.3. Break-glass changes

Tài khoản break-glass có thể cần khi IdP chung không sẵn sàng, nhưng phải:

- Có owner, justification, quyền tối thiểu đủ khôi phục.
- Xác định điều kiện kích hoạt, cơ chế giám sát và thời gian hoạt động.
- Bảo vệ credential, ghi lại phiên truy cập theo khả năng hệ thống.
- Thu hồi/quay lại baseline sau sự cố.
- Kiểm effective permissions và tài khoản tạm sau khi phục hồi.
- Bảo đảm event không bị mất hoặc có nguồn ghi độc lập khi hệ thống log chính lỗi.
- Reconcile mọi thay đổi thực hiện trong thời gian khẩn cấp.

Không để break-glass trở thành **một đường admin vĩnh viễn ngoài MFA/PAM** mà chương trình review không biết.

### 19.4. Manual console change và GitOps drift

Giả sử trong emergency một kỹ sư sửa network policy trực tiếp qua console:

- Lưu bản diff/effective config ngay sau thao tác.
- Link thay đổi tới incident/change ID.
- Đảm bảo IaC/GitOps reconciler không tự đảo ngược mitigation ngoài ý muốn.
- Khi ổn định, hợp nhất thay đổi vào source of truth qua quy trình review.
- Chạy lại IaC plan và runtime drift checks.
- Kiểm control boundaries, routes, permissions và logging.
- Xóa ngoại lệ tạm không còn cần thiết.

Một hệ thống có GitOps **không tự chứng minh mọi thay đổi đều qua Git**; reviewer phải xét runtime drift và out-of-band events.

### 19.5. Tránh hai cực đoan

- **Quá chặt:** bắt buộc hoàn thành toàn bộ form thường khi hệ thống đang bị khai thác, dẫn đến trì hoãn containment.
- **Quá lỏng:** gắn nhãn emergency để vượt approvals và bỏ hậu kiểm, dẫn tới thay đổi đặc quyền không có chứng cứ.

Mô hình tốt có emergency playbook với guardrails tối thiểu, review có thẩm quyền và **hậu kiểm time-boxed**.

## 20. Third-party, cloud provider và thay đổi bên ngoài

### 20.1. Vendor change không do mình merge vẫn cần assurance

Những thay đổi từ nhà cung cấp:

- SaaS thay cách SSO/authorization hoặc API permissions.
- Cloud provider đổi behavior mặc định của service.
- Vendor bổ sung subprocessor hoặc chuyển region.
- Service đổi retention, audit export format hoặc event schema.
- API version bị deprecate, certificate/root CA thay.
- Vendor support được cấp quyền mới hoặc đổi IAM federation.
- Nhà cung cấp backup/DR đổi key/storage/failover path.
- Một bản security advisory buộc upgrade hoặc workaround.

Không có pull request trong tổ chức không có nghĩa **không có change cần review**.

### 20.2. Quy trình delta assessment với vendor

1. Thu thông báo chính thức, version/effective dates và dịch vụ affected.
2. Đối chiếu inventory các integrations, data classes, regions và permission scopes.
3. Kiểm hợp đồng và shared responsibility; legal/privacy tham gia khi áp dụng.
4. Xác định các control assertions có thể bị ảnh hưởng.
5. Yêu cầu evidence đúng service/kỳ/scope hoặc thực hiện test tại tenant của khách hàng.
6. Phân loại critical gaps, khả năng trì hoãn/opt-out và exit plan.
7. Chuẩn bị release, token scope, migration và rollback/compatibility.
8. Xác minh actual tenant behavior sau khi vendor change có hiệu lực.
9. Ghi exceptions, findings, owner, re-review trigger nếu evidence còn thiếu.
10. Theo dõi thay đổi tiếp theo và kiểm audit report mới khi cần.

### 20.3. Báo cáo độc lập không bao phủ mọi change

Một SOC 2 report hoặc chứng nhận ISO/IEC 27001 có thể hỗ trợ đánh giá trong phạm vi đã ghi, nhưng không tự chứng minh add-on/API/region mới an toàn hoặc đã được kiểm sau một thay đổi gần đây. Cần xem:

- Dịch vụ và pháp nhân nằm trong scope không?
- Báo cáo bao phủ kỳ nào?
- Có exceptions, subservice organizations và complementary controls nào?
- Những thay đổi sau kỳ báo cáo cần evidence nào?
- Điều gì thuộc trách nhiệm cấu hình của khách hàng?

Nếu chưa có bằng chứng đủ, ghi **INCONCLUSIVE** và quyết định phạm vi sử dụng; không tự coi vendor lớn đồng nghĩa PASS.

### 20.4. Thay đổi data processor/subprocessor

Một vendor bổ sung đối tác phân tích có thể tạo luồng dữ liệu mới. Security change review cần cập nhật:

- Danh sách data elements được chia sẻ.
- Endpoint, egress allowlist, authentication và mã hóa.
- Location/retention và điều kiện truy cập của nhân viên vendor.
- Hợp đồng và nghĩa vụ thông báo/approval trong phạm vi.
- Security events và khả năng điều tra khi dữ liệu bị gửi sai.
- Incident response contact, data export/delete và offboarding.
- Khả năng tạm dừng tích hợp nếu control không đạt.

Kết quả change review phải phân biệt **technical assurance**, **contract/privacy decision** và **residual risk acceptance**.

## 21. Findings, risk exceptions và thay đổi không được phê duyệt

### 21.1. Review có thể ra những verdict nào?

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| **APPROVED_FOR_DEPLOY** | Plan và pre-deploy gates đủ cho scope đã định | Được triển khai theo điều kiện; vẫn cần post-deploy verification |
| **CONDITIONALLY_APPROVED** | Có điều kiện/giới hạn rõ, được phép theo governance | Chỉ được deploy khi điều kiện hợp lệ và có owner |
| **DEFERRED / BLOCKED** | Thiếu critical evidence, control fail hoặc chưa đủ authority | Sửa hoặc bổ sung evidence trước khi deploy |
| **REJECTED** | Risk hoặc design không phù hợp mục tiêu/không có đường giảm rủi ro chấp nhận được | Thiết kế lại hoặc hủy change |
| **DEPLOYED_UNVERIFIED** | Change đã chạy nhưng chưa có bằng chứng runtime đạt | Kiểm hậu triển khai theo hạn, hạn chế rủi ro |
| **VERIFIED_WITH_SCOPE** | Control assertions đạt trong scope sau deploy | Đóng record có evidence, giữ monitoring |
| **FAILED_AFTER_DEPLOY** | Có confirmed failure ở runtime | Containment/rollback/IR, remediation, retest |
| **INCONCLUSIVE_AFTER_DEPLOY** | Chưa có evidence đủ/collector thiếu | Điều tra, giám sát và risk decision phù hợp |

Mỗi trạng thái phải có **thời điểm, người quyết định, scope, evidence và next action**. Không dùng từ “approved” mơ hồ cho cả review thiết kế và kết quả kiểm tra production.

### 21.2. Finding từ change review

Ví dụ review một chính sách IAM phát hiện resource wildcard không có business justification và negative test chưa đủ. Finding cần:

- **Criterion:** least-privilege baseline/requirement có hiệu lực.
- **Condition:** policy diff có action/resource ngoài scope, effective permission nào đã được xác minh.
- **Evidence:** policy export, test, owner confirmation và limitations.
- **Risk:** potential unauthorized access với privilege blast radius.
- **Severity/confidence:** hai trục riêng.
- **Owner:** platform/IAM change implementer.
- **Recommendation:** thu hẹp resource/condition, test deny và drift checks.
- **Go/no-go impact:** có kích hoạt critical gate không?
- **Retest:** assertion và population, reviewer, kết quả.

Nếu chưa xác minh policy thực sự được deploy, không viết rằng production hiện đã có quyền wildcard; ghi **planned change introduces excessive permissions if deployed**.

### 21.3. Risk acceptance phải có thời hạn và giới hạn

Một exception có thể gồm:

- Change ID, security requirement/control và finding link.
- Asset/data/environment scope.
- Tác động và lý do chưa thể đạt.
- Compensating controls được kiểm chứng, hạn chế và giám sát.
- Người có quyền phê duyệt, ngày hiệu lực và expiry.
- Các hoạt động được phép/cấm trong kỳ ngoại lệ.
- Milestone remediation, deadline và retest.
- Điều kiện phải tái đánh giá ngay: incident, threat mới, scope data đổi, mitigation fail.
- Nghĩa vụ bên ngoài có cho phép ngoại lệ không.

**Chấp nhận rủi ro không biến control FAIL thành PASS**. Với requirement không cho phép ngoại lệ, quyết định nội bộ không thể tự thay thế nghĩa vụ áp dụng.

### 21.4. Thay đổi ngoài phạm vi approval

Nếu release được duyệt cho một API endpoint nhưng deployment đi kèm thay IAM policy organization-wide, approval trước **không bao phủ** thay đổi bổ sung đó. Cần:

1. Xác định chênh lệch từ expected plan và runtime diff.
2. Đánh giá rủi ro và critical boundary mới.
3. Kích hoạt hold/rollback hoặc escalation theo điều kiện.
4. Bổ sung review và evidence, không ghi đè approval cũ.
5. Giữ history về lý do phạm vi thay đổi và thời điểm phát hiện.
6. Kiểm xem pipeline/approval gate vì sao bỏ sót scope.

## 22. Change assurance record và evidence manifest

### 22.1. Tách các thực thể dữ liệu

Một chương trình change assurance nên có:

- **Change request:** ai yêu cầu, điều gì, tại sao, expected scope.
- **Affected asset/control graph:** tài nguyên, data flow, dependency và responsibilities.
- **Risk assessment:** threat, impact, uncertainty, critical gates, owner.
- **Security review:** assertions, criteria, observations và required fixes.
- **Evidence:** source, method, timestamp, test, artifact version, quality.
- **Decision:** approve/defer/reject, conditions, authority và expiry.
- **Deployment event:** actual artifact/config/account/region, mốc thời gian.
- **Post-change validation:** test results, gaps, verdict có scope.
- **Findings/remediation:** owner, deadline, retest, residual risk.
- **Monitoring/closure:** drift checks, review date, final record.

Không gộp các đối tượng vào một checkbox **“security reviewed = true”** nếu cần truy vết các nhận định riêng.

### 22.2. Mẫu YAML tổng hợp

~~~yaml
change_id: "CHG-SEC-2026-043"
name: "Restrict customer-support API permissions"
requested_at: "2026-11-28T02:00:00Z"
requested_by_role: "support-api-team"
service:
  name: "customer-support-api"
  business_owner_role: "customer-experience-owner"
  environment: "production"
  criticality: "HIGH"
scope:
  included:
    - "support-api-v2"
    - "tenant-object-authorization"
    - "audit-event-routing"
  excluded:
    - "other-service-apis"
  data_classes:
    - "customer-contact"
    - "support-tickets"
  regions: ["region-example-a"]
before_after:
  before: "Support role inherits broad object read permission"
  after: "Resource-level tenant-scoped authorization"
  artifact_ref: "repo/ref/example-commit"
risk_triage:
  tier: "HIGH"
  changed_boundaries:
    - "tenant-to-tenant data access"
  threat_scenarios:
    - "cross-tenant object read"
    - "unauthorized bulk export"
  unresolved_questions: []
  review_owner_role: "security-architecture"
control_assertions:
  - id: "CHG-AUTHZ-01"
    criterion_ref: "ACCESS-POL-v3"
    expected: "Support role is denied access outside authorized tenant"
    predeploy_test: "integration-test-authz-matrix"
    postdeploy_test: "approved-controlled-negative-test"
  - id: "CHG-LOG-02"
    criterion_ref: "LOG-POL-v5"
    expected: "Sensitive support access events are centrally observable"
    predeploy_test: "event-schema-contract-test"
    postdeploy_test: "synthetic-event-to-siem-test"
review:
  reviewer_role: "security-assurance"
  predeploy_verdict: "APPROVED_FOR_DEPLOY"
  evidence_refs:
    - "CHG-EV-2026-201"
    - "CHG-EV-2026-202"
  decision_at: "2026-11-28T04:00:00Z"
  approval_conditions:
    - "Deploy only approved image and IAM configuration"
    - "Postdeploy verify all required authorization scenarios"
deployment:
  change_window: "approved-window-reference"
  artifact_digest: "EXAMPLE_DIGEST_NOT_REAL"
  started_at: "2026-11-28T06:00:00Z"
  finished_at: "2026-11-28T06:20:00Z"
  canary: "10-percent-test-traffic-before-full-rollout"
post_deploy:
  verification_started_at: "2026-11-28T06:25:00Z"
  control_results:
    - assertion_id: "CHG-AUTHZ-01"
      verdict: "PASS_WITH_SCOPE"
      evidence_ref: "CHG-EV-2026-203"
    - assertion_id: "CHG-LOG-02"
      verdict: "PASS_WITH_SCOPE"
      evidence_ref: "CHG-EV-2026-204"
  limitations:
    - "Only test identities and endpoints included in approved scope"
  residual_risk: "UNKNOWN_OUTSIDE_SCOPE_NOT_COVERED"
  final_verdict: "VERIFIED_WITH_SCOPE"
  verification_owner_role: "security-assurance"
monitoring:
  drift_check: "tenant-authz-and-log-source-policy"
  review_triggers:
    - "new-export-api"
    - "role-model-change"
    - "subprocessor-change"
status: "VERIFIED_CLOSED"
~~~

Tất cả service, ID, thời gian và digest là **dữ liệu giả định để minh họa**; YAML này không phải schema được yêu cầu bởi một sản phẩm. Trong thực tế, phải ghi actual artifact IDs, evidence sources và quyền phê duyệt có thể kiểm.

### 22.3. Evidence record theo từng assertion

~~~yaml
evidence_id: "CHG-EV-2026-203"
change_id: "CHG-SEC-2026-043"
assertion_id: "CHG-AUTHZ-01"
type: "controlled-authorization-test"
source:
  system: "production-customer-support-api"
  collection_method: "approved-synthetic-test-identities"
collected_at: "2026-11-28T06:25:00Z"
artifact:
  reference: "restricted-change-evidence/CHG-EV-2026-203"
  integrity_method: "approved-evidence-store-controls"
scope:
  environment: "production"
  api_version: "v2"
  tenant_classes: ["test-tenant-A", "test-tenant-B"]
test:
  test_version: "authz-matrix-v4"
  authorized_case: "PASS"
  unauthorized_cross_tenant_case: "DENIED"
  audit_event_observed: true
result: "PASS_WITH_SCOPE"
limitations:
  - "Does not generalize to every tenant or untested endpoint"
reviewed_by_role: "security-assurance"
~~~

Điểm quan trọng là có thể truy vết **assertion → evidence ID → test method → runtime artifact/environment → result → limitation**, không chỉ một file đính kèm không rõ nguồn.

### 22.4. Tính toàn vẹn và kiểm soát truy cập evidence

- Bằng chứng gốc được giữ trong kho hạn chế quyền và retention phù hợp.
- Reviewer có quyền đọc cần thiết, không mặc định quyền sửa production.
- Thông tin nhạy cảm như secrets, account IDs, customer content được che khi báo cáo.
- Mọi transformation/redaction có lịch sử và tham chiếu bản gốc.
- Hash/signature khi áp dụng phải có trust anchor độc lập, không lưu chung dưới cùng quyền sửa mà không bảo vệ.
- Approval và review history có version, thay đổi sau khi phát hành không âm thầm ghi đè.
- Evidence collector/pipeline có health checks và population reconciliation.

Một checksum khớp **không chứng minh log ở nguồn đã đầy đủ**; một chứng nhận vendor **không tự bao phủ tất cả dịch vụ**.

### 22.5. State machine cho change review

~~~mermaid
flowchart TD
    REQUEST["REQUESTED"] --> TRIAGE["IMPACT_ASSESSED"]
    TRIAGE --> REVIEW["UNDER_SECURITY_REVIEW"]
    REVIEW --> PRE{"Pre-deploy verdict"}
    PRE -- "PASS / conditional" --> AP["APPROVED_FOR_DEPLOY"]
    PRE -- "FAIL / unknown" --> BLOCK["DEFERRED / BLOCKED"]
    BLOCK --> REVIEW
    AP --> DEP["DEPLOYED_UNVERIFIED"]
    DEP --> VAL["POST_DEPLOY_VALIDATION"]
    VAL --> RESULT{"Assertion đạt?"}
    RESULT -- "Có" --> CLOSE["VERIFIED_CLOSED"]
    RESULT -- "Không" --> FAIL["FAILED / REMEDIATION"]
    FAIL --> VAL
    CLOSE --> DRIFT["DRIFT_MONITORING"]
    DRIFT --> TRIAGE
~~~

**Conditional approval** cần kiểm điều kiện đã thỏa trước khi chuyển sang deploy. Một emergency change có thể đi nhánh rút gọn nhưng phải giữ audit trail và hậu kiểm.

## 23. Decision logic và ví dụ pseudocode

### 23.1. Phân tầng quyết định

~~~text
function assessSecurityChange(change, context):
    if not change.hasAuthoritativeScopeOrOwner:
        return NEEDS_SCOPE_VALIDATION

    if context.activeIncident:
        return EMERGENCY_PATH_WITH_MINIMUM_GUARDRAILS

    if change.impactsCriticalPrivilegesOrDataBoundary:
        require(SECURITY_REVIEW_AND_EFFECTIVE_CONTROL_TESTS)

    if change.changesDataProcessingOrContractualObligations:
        require(APPLICABILITY_AND_RESPONSIBILITY_REVIEW)

    if change.changesBuildOrDeploymentTrust:
        require(SUPPLY_CHAIN_AND_PIPELINE_REVIEW)

    if change.changesLoggingOrDetection:
        require(END_TO_END_OBSERVABILITY_TESTS)

    if change.isIrreversibleOrStateful:
        require(DATA_RECOVERY_AND_FAIL_FORWARD_PLAN)

    if requiredControlFails:
        return BLOCK_OR_ESCALATE_ACCORDING_TO_APPROVED_POLICY

    if requiredEvidenceMissing:
        return INCONCLUSIVE_WITH_OWNER_AND_DEADLINE

    return APPROVED_FOR_DEPLOY_WITH_POSTDEPLOY_ACCEPTANCE
~~~

Đây là **pseudocode mô hình tư duy**, không phải tool tự động deploy/rollback. Tổ chức phải viết quy tắc phù hợp risk appetite, policy và quyền quyết định. Không cho một nhãn “low risk” bỏ qua critical conditions đã xác định.

### 23.2. Bộ test cho decision engine

| Case | Input chính | Verdict/action phù hợp |
|---|---|---|
| A | Thay documentation, không đổi runtime/controls | Standard automated review |
| B | Mở API chứa dữ liệu nhạy cảm ra Internet | Threat/design review, authz/privacy checks, pre/post gates |
| C | Thêm wildcard quyền admin | High/critical review, least-privilege gate |
| D | Tắt audit events của production | Critical logging control gate, test impact |
| E | Refactor parser không đổi schema kỳ vọng | Test field fidelity, end-to-end detection |
| F | Migration không có data rollback | Recovery/fail-forward acceptance, business approval |
| G | Hotfix đang bị khai thác, có safe containment | Emergency review path + post-change validation |
| H | Vendor đổi subprocessor/region | Delta assessment với scope/obligations |
| I | CI/CD PASS nhưng runtime artifact khác approved | FAIL/hold, reconcile artifact và provenance |
| J | Missing evidence cho critical IAM path | INCONCLUSIVE/BLOCK theo policy, không tự PASS |
| K | Approved change mở rộng scope sau approval | Re-review delta, giữ approval version cũ |
| L | Thay KMS policy làm restore account không giải mã được | Resilience/security gate fail, rollback/fail-forward |

### 23.3. Đánh giá nguy cơ “approval laundering”

Một anti-pattern là dùng một approval thuộc scope nhỏ để hợp thức hóa thay đổi lớn hơn:

- Change “minor version bump” thực tế nâng IAM role.
- “Improve logging performance” thực tế drop audit events.
- “Temporary emergency exception” không có expiry.
- “Config cleanup” tắt admission rule.
- “Vendor update” cho token quyền rộng hơn.
- “Rollback” khôi phục image có vulnerability đã vá.

Cần **review actual diff và observed state**, không chỉ title của ticket. Nếu scope đổi sau approval, phải cập nhật quyết định và evidence.

## 24. Case study 1: thay policy hỗ trợ dẫn đến nguy cơ truy cập dữ liệu tenant khác

### 24.1. Bối cảnh

Một SaaS chăm sóc khách hàng có API theo tenant. Nhóm sản phẩm muốn cho nhân viên hỗ trợ tìm ticket nhanh hơn. Thay đổi gồm:

- Role support được phép gọi endpoint tìm kiếm mới.
- Query builder được cập nhật để giảm latency.
- API token support có thể truy cập nhiều tổ chức nhưng quyền chi tiết được giới hạn theo assignment.
- Dữ liệu bao gồm email, nội dung ticket và lịch sử hỗ trợ.
- Pipeline unit tests và static checks hiện đang PASS.

Thay đổi được ghi “chỉ thêm search filter”, nhưng làm thay **object authorization boundary**.

### 24.2. Before/after và threat scenario

| Thành phần | Before | After | Nguy cơ cần review |
|---|---|---|---|
| Search API | Chỉ query tenant được gán | Cho phép tìm ticket liên quan nhiều workspace | Tenant crossing, data overexposure |
| Role | Support role cơ bản | Support role có permission mới | Least privilege và privilege creep |
| Query | Repository inject tenant filter | Tối ưu query builder mới | Tenant predicate bị bỏ sót |
| Export | Không export search result | Có batch export liên quan | Bulk data exfiltration nếu authz sai |
| Audit | Log ticket detail | Search/export cần event mới | Missing forensic evidence |
| Performance | Query scope nhỏ | Query liên tenant | Rate limiting và query amplification |

Một threat-model delta có thể tạo assertion: “mọi result có tenant/resource được phép theo assignment; search và export không được phụ thuộc vào client-supplied tenant IDs để cấp quyền”.

### 24.3. Security change review

1. Xác định role matrix, service accounts và identity claims.
2. Review query-builder semantics, tenant context do server xác thực.
3. Xây test matrix với tenant A/B, role support, admin, suspended user.
4. Kiểm negative cross-tenant search/list/detail/export.
5. Kiểm paginate, async jobs, cached results và data exposure ở errors.
6. Kiểm rate limiting, request logging và audit event fidelity.
7. Kiểm dữ liệu nhạy cảm trong results và temporary objects.
8. Review rollout strategy, feature flag và emergency disable.
9. Phê duyệt có điều kiện các test quan trọng PASS.
10. Post-deploy verify với synthetic tenants, service logs và monitoring.

### 24.4. Phát hiện trong pre-deploy testing

Giả sử negative test phát hiện một kết quả search từ tenant B xuất hiện cho support role chỉ được gán tenant A. Đây là **confirmed authorization failure trong test environment**, chưa chứng minh đã xảy ra rò rỉ production.

Finding nên ghi:

- **Criterion:** object-level tenant authorization bắt buộc.
- **Condition:** kết quả kiểm thử query tìm kiếm không lọc đủ tenant.
- **Evidence:** test case ID, synthetic test data, commit, API version.
- **Impact:** nguy cơ truy cập dữ liệu ngoài tenant khi triển khai.
- **Decision:** block production deployment cho đến khi sửa.
- **Remediation:** enforce predicate ở data-access layer, centralize authorization decision.
- **Retest:** chạy toàn bộ matrix + regression trên list/detail/export và tenant boundaries.
- **Prevention:** authorization tests bắt buộc khi endpoint mới dùng shared query module.

### 24.5. Sau khi sửa

Reviewer chỉ phê duyệt deploy khi:

- Test negative được chứng minh deny với mọi path trong scope.
- Không có bypass từ batch export hoặc access qua service account.
- Effective deployment dùng artifact đã được kiểm.
- Audit events có actor, resource, decision.
- Canary có monitoring và kill switch nếu phát hiện sai.

Sau deploy, chạy controlled tests bằng dữ liệu giả định; khi đạt mới **VERIFIED_WITH_SCOPE**. Không kết luận “mọi tenant luôn an toàn” ngoài các môi trường và paths đã kiểm.

**Bài học:** kích thước change nhỏ và CI PASS không thay thế threat-model delta cho trust boundary của dữ liệu.

## 25. Case study 2: schema migration kết hợp KMS rotation tạo DR gap

### 25.1. Bối cảnh

Một dịch vụ thanh toán dự kiến đồng thời:

- Migrate schema database để hỗ trợ transaction attributes mới.
- Rotate data encryption key theo kế hoạch.
- Thay replication sang recovery account khác.
- Nâng service version có hỗ trợ schema mới.
- BIA yêu cầu RTO/RPO cụ thể và dữ liệu giao dịch nhất quán.

Engineering đã thử migration trên database staging nhỏ, tất cả API smoke tests đều PASS. Tuy nhiên recovery account chưa được test decrypt với key mới.

### 25.2. Security change review xác định những ràng buộc

| Control | Assertion | Bằng chứng trước/sau |
|---|---|---|
| **Data integrity** | Transaction invariants còn đúng sau migration | Reconciliation, sampling có kiểm soát, duplicate/missing checks |
| **Encryption** | Dữ liệu mới và cũ giải mã hợp lệ trong scope | Key policy, encrypt/decrypt tests |
| **Least privilege** | Recovery chỉ có quyền KMS và storage cần thiết | IAM/KMS effective permission tests |
| **Recovery** | Restore đạt service acceptance và mục tiêu đã được phê duyệt | Representative restore exercise, T0/T1/Tdata |
| **Rollback** | Có fail-forward/restore khi schema không backward-compatible | Migration plan, dry run, restore checkpoints |
| **Audit trail** | Thao tác migration/key change được ghi đầy đủ | Change events source→central store |
| **Data retention** | Backup và key lifecycle không phá thời hạn giữ dữ liệu | Backup/key-retention dependency review |
| **Monitoring** | KMS denial, replication lag và data inconsistency được phát hiện | Alerts và synthetic fault tests |

### 25.3. Một lỗi xuất hiện trong rehearsal

Trong recovery rehearsal, database restore object thành công nhưng ứng dụng không đọc được một partition vì recovery identity thiếu quyền sử dụng key phiên bản mới. Nếu chỉ nhìn backup job, dashboard có thể hiển thị SUCCESS.

Đây là **confirmed failure của recovery assertion trong rehearsal**:

- Không chứng minh production đã mất dữ liệu.
- Chứng minh recovery plan chưa đáp ứng điều kiện đã thử.
- Cần sửa KMS key policy, không cấp wildcard cho toàn account.
- Cần retest restore data và business service sau khi đổi.
- Cần đối chiếu encrypted backups cũ, key retention và failback.

### 25.4. Quyết định go/no-go

Nếu destructive schema migration chưa có đường khôi phục đáng tin, reviewer có thể **DEFER** cutover cho đến khi:

1. Recovery identity có quyền chính xác.
2. Restore rehearsal trên dataset đại diện PASS.
3. Data reconciliation và functional/security acceptance đạt.
4. Rollback hoặc fail-forward plan có scope, owner và thời hạn.
5. Detection/monitoring cho data/key failures sẵn sàng.
6. Service owner chấp nhận downtime/recovery assumptions theo thẩm quyền.

Có thể tách rollout thành **expand schema → kiểm access/key → diễn tập DR → migrate → cutover → contract** để giảm blast radius.

### 25.5. Bằng chứng closure

Evidence package cần link migration commit/version, DB schema, backup snapshot ID, key IDs đã được che phù hợp, recovery test, timestamps, data consistency report, actual app version và reviewer. Khi production cutover đạt, vẫn giữ monitoring window để bắt long-running jobs và các consumer chưa cập nhật.

**Bài học:** một thay đổi tính năng có thể làm thay đổi **recovery security boundary**. Để chứng minh an toàn, phải kiểm data integrity và khả năng decrypt/restore chứ không chỉ API trả 200.

## 26. Case study 3: emergency hotfix và thay đổi logging từ nhà cung cấp

### 26.1. Bối cảnh

Một nhà cung cấp gateway phát hành cập nhật khẩn để giảm rủi ro của lỗ hổng đang bị khai thác ngoài thực tế. Trong quá trình cập nhật, format audit events cũng thay đổi. SOC phụ thuộc vào parser và rule cũ để nhận biết các thao tác quản trị. Service có khối lượng giao dịch lớn và không có cửa sổ downtime thông thường.

### 26.2. Các mục tiêu có thể xung đột

- **Nhanh:** giảm thời gian phơi nhiễm với lỗ hổng.
- **An toàn:** không triển khai artifact không đúng provenance.
- **Sẵn sàng:** không làm gián đoạn gateway và transaction.
- **Quan sát:** không để parser mất trường quan trọng.
- **Khôi phục:** có rollback/fail-forward hợp lý mà không quay lại phiên bản dễ bị khai thác ngoài ý muốn.

Security change review phải đánh giá **rủi ro của deploy và rủi ro của không deploy**.

### 26.3. Cách tổ chức emergency review

1. SOC/IR xác minh dấu hiệu incident ở môi trường mình và threat exposure.
2. Platform xác minh gateway version, route, affected assets và vendor advisory.
3. Chọn mitigation tạm nếu patch cần kiểm thêm, giữ evidence trạng thái hiện tại.
4. Kiểm artifact provenance và integration smoke/security tests quan trọng.
5. Parser/detection owner cập nhật schema và tạo test event trước/đồng thời rollout.
6. Release team deploy canary/blue-green theo business availability.
7. Verify gateway mới và security events từ source→SIEM, check fields/alerts.
8. Nếu event bị mất, cân nhắc rollback parser, dual parsing hoặc contained operation; không tắt logging để được coi healthy.
9. Sau emergency, review approvals, exception, test evidence và control regressions.
10. Cập nhật change/playbook, preventive tests và vendor-change monitoring.

### 26.4. Một phát hiện nguy hiểm

Trong canary, gateway hoạt động nhưng parser mới không đọc trường actor, khiến alert về thay đổi IAM không kích hoạt. Kết luận:

- **Availability gate:** có thể PASS trong canary.
- **Detection/security gate:** FAIL vì field fidelity/alert test chưa đạt.
- **Go/no-go:** cân nhắc critical risk và mitigation; không coi 200 response là đủ.
- **Action:** sửa parser/dual-format support, retest end-to-end, xác minh rollout đầy đủ.
- **Reporting:** ghi khoảng thời gian telemetry suy giảm, asset affected và residual risk.

Nếu threat đang hoạt động khiến không thể chờ parser mới, cần **đường quyết định emergency có thẩm quyền**, biện pháp quan sát/giới hạn tạm có kiểm chứng và hậu kiểm time-boxed; không sửa lại lịch sử thành “đã PASS” khi thực tế có gap.

### 26.5. Bài học

Security assurance của một thay đổi phải xem **tổng thể chuỗi controls**. Một hotfix có thể giảm vulnerability risk nhưng đồng thời làm tăng detection risk. Cả hai cần xuất hiện trong decision record, với người chịu trách nhiệm và bằng chứng cụ thể.

## 27. KPI cho Security change review và change assurance

### 27.1. Đo chất lượng, không chỉ tốc độ approval

Một dashboard cho thấy **100% changes approved** chưa nói review có hiệu lực. Nếu phần lớn change tự qua checklist thiếu threat model, không kiểm effective state hoặc bỏ qua phát hiện hậu triển khai, tỷ lệ approval đẹp có thể là tín hiệu giả.

Nhóm chỉ số hữu ích:

| KPI/KCI | Định nghĩa có ích | Điều không được suy ra |
|---|---|---|
| **Required change review coverage** | Changes thuộc diện cần review đã có security impact assessment hợp lệ / tổng changes thuộc diện | Chỉ số này chưa chứng minh controls PASS |
| **High-risk change assurance coverage** | High-risk changes có pre/post assertions được kiểm PASS / tổng high-risk changes cần kiểm | Không tính DEPLOYED_UNVERIFIED là đạt |
| **Evidence completeness** | Assertion bắt buộc có evidence phù hợp đúng scope/kỳ / tổng assertion cần evidence | Một file đính kèm không chắc có evidence chất lượng |
| **Runtime verification coverage** | Approved changes có effective-state validation / changes cần validate | CI PASS không thay runtime checks |
| **Critical gate failure count** | Số changes có critical control gate FAIL, phân theo scope | Ít FAIL có thể do ít kiểm hoặc kiểm nông |
| **Unauthorized change detection** | Changes ngoài pipeline/approval được phát hiện có bằng chứng | Zero không chứng minh không có manual changes |
| **Post-change security regressions** | Security regressions được xác nhận và liên kết change | Cần xét telemetry quality và severity |
| **Time to detect drift** | Từ change tạo sai lệch đến finding có thể hành động | Mốc start có thể chưa biết chính xác |
| **Time to verified correction** | Từ confirmed gap đến retest PASS và approval | Ticket Done/merge PR không tương đương |
| **Rollback/recovery effectiveness** | Required rollback/restore scenarios đạt các gates / scenarios cần kiểm | Một code revert không đảm bảo data rollback |
| **Emergency post-review timeliness** | Emergency changes được hậu kiểm đúng hạn / emergency changes cần hậu kiểm | Hoàn tất form không chứng minh runtime assurance |
| **Expired exceptions** | Ngoại lệ change đã hết hạn chưa được review/đóng | Không được cộng accepted risk vào PASS |
| **Recurring change findings** | Finding cùng nguyên nhân tái phát sau đã verified closed | Phải giữ root-cause taxonomy |
| **Reviewer rework rate** | Changes phải sửa evidence/requirements sau review | Cao có thể do review phát hiện đúng vấn đề, không hẳn xấu |

### 27.2. Mẫu số phải có nguồn độc lập

Ví dụ trong kỳ có 120 production changes theo change/deployment log:

- 90 changes thực sự thuộc diện cần security review theo policy/risk triggers.
- 70 đã có đầy đủ pre-deploy review.
- 64 có post-deploy security verification PASS.
- 4 có confirmed failures.
- 2 còn INCONCLUSIVE sau deploy.
- 20 chưa hoàn tất review hoặc không có evidence đủ.

Nếu đang đo **verified high-relevance change coverage** trên tập 90 required changes, numerator chỉ 64:

\[
\text{Verified Change Assurance Coverage}
=\frac{64}{90}\times100\%\approx71.1\%
\]

Không báo 64/64 = 100% chỉ vì dashboard chỉ lưu những thay đổi được verified. 30 changes không thuộc diện review sâu phải có **căn cứ risk classification** và vẫn đi qua các guardrails tối thiểu phù hợp.

### 27.3. Các kỳ và tính đồng nhất

Cần ghi:

- **Unit:** change ID, deployment instance, control assertion hay service × change?
- **Period:** mốc request, approval, deploy hay closure được dùng cho cohort?
- **Releases nhiều regions:** một change có thể tạo nhiều affected deployment units.
- **Emergency changes:** được tính cùng mẫu số nào, có hậu kiểm riêng?
- **Canceled/rejected changes:** có nằm trong denominator của coverage không và vì sao?
- **Conditional approvals:** điều kiện đã được đáp ứng hay chỉ được ghi trong ticket?
- **Changes đang chạy:** đang VERIFYING, không tính duration bằng 0.
- **Metric version:** khi threshold, risk classification hoặc scope đổi, cần version.
- **Population completeness:** nhận cả GitOps, console, vendor và emergency changes phù hợp.
- **Evidence freshness:** kỳ và actual runtime state đã được cập nhật chưa?

### 27.4. Dashboard dành cho nhiều đối tượng

**Engineering/platform:** critical gates, runtime deviations, test failures, rollback readiness, IAM/cloud diffs, missing owner.

**SOC/IR:** logging/detection source health sau change, alert routing, suppressed scenarios, emergency-change timeline.

**Security assurance/GRC:** control mapping, evidence quality, required changes chưa review, exceptions, retest/closure.

**Service/business owner:** blast radius, business/security tradeoffs, go/no-go conditions, residual risk và decisions required.

**Leadership:** top high-risk changes, critical regressions, độ bao phủ đã kiểm, recurring root causes, investment decisions.

Một dashboard tốt có thể **drill down từ KPI → change ID → assertion → evidence → finding → action/owner → retest**, không chỉ hiển thị điểm trung bình.

### 27.5. Anti-gaming

Không để KPI khuyến khích:

- Đổi nhãn high risk thành low risk để tránh review.
- Gom nhiều changes critical vào một ticket scope mơ hồ.
- Tự approve để đạt SLA.
- Đóng ticket khi mới deploy nhưng chưa verify.
- Xóa/ẩn failed test hoặc thiếu evidence.
- Không ghi emergency console changes.
- Lùi deadline hậu kiểm không có approval.
- “PASS” bằng cách chạy scanner trên target sai.
- Loại region/tenant khỏi sample denominator mà không cập nhật phạm vi.

Để chống sai lệch cần **independent reconciliation với deployment/cloud audit logs, random sampling theo rủi ro, quality gates, reviewer independence và audit trail**.

## 28. Sai lầm thường gặp khi review thay đổi bảo mật

| Sai lầm | Vì sao có vấn đề | Cách làm tốt hơn |
|---|---|---|
| Chỉ review thay đổi source code | Bỏ sót cloud/IAM/vendor/console changes | Tạo inventory từ deployment, cloud audit, vendor và GRC |
| Dùng số dòng diff để phân tầng | Một dòng IAM có thể gây blast radius lớn | Risk-based triggers, privilege/data/trust boundary |
| Xem “CI xanh” là đã đạt assurance | Chỉ phản ánh checks đã chạy và dữ liệu đầu vào | Liên kết với assertions và runtime verification |
| Bỏ qua positive/negative authz tests | Có thể bypass quyền dù happy-path PASS | Test role/tenant/resource được phép và bị từ chối |
| Review kiến trúc không có data-flow | Không thấy dữ liệu mới đi qua vendor/region | Before/after data-flow và applicability review |
| Chỉ nhìn IaC, không xem console drift | Effective state có thể khác approved plan | Runtime diff và out-of-band change monitoring |
| Tự động cho PASS khi thiếu test | Mất khả năng phân biệt unknown với đạt | INCONCLUSIVE/NOT_TESTED và owner/hạn |
| Giảm log volume bằng cách tắt audit | Detection blind spot và forensic gap | Test end-to-end field fidelity/alert trước/sau |
| Review key rotation chỉ bằng API smoke test | Backup/DR có thể không decrypt được | Restore/recovery test và key lifecycle review |
| “Revert commit” là rollback hoàn chỉnh | Data migrations, credentials, sessions khó đảo | Data reconciliation, restore/fail-forward plan |
| Xem emergency là miễn mọi kiểm soát | Rủi ro thay đổi trái quyền, khó audit | Minimum guardrails + hậu kiểm có hạn |
| Lấy report vendor làm chứng cứ cho mọi add-on | Scope, kỳ và shared responsibility khác nhau | Delta assessment theo service/tenant |
| Approval của một commit áp cho commit khác | Change scope khác nhưng vẫn dùng chữ ký cũ | Bind approval với artifact/config/version |
| Reviewer kiểm được policy nhưng không kiểm effective quyền | Inheritance/trust có thể tạo bypass | Effective permissions và runtime tests |
| Không có owner cho exception | Risk acceptance kéo dài hoặc không ai review | Approver, scope, expiry, monitoring và remediation |
| Trộn design approval với operational PASS | Chưa xác minh hậu triển khai | Hai verdict và hai thời điểm riêng |
| Không lưu kết quả trước/sau | Không truy được cause/impact của regression | Evidence manifest và deployment timeline |
| Chỉ đo “100% approved” | Chỉ đo paperwork, không đo hiệu lực | Verified review coverage, failures và drift |
| Không giữ failed changes trong lịch sử | KPI và audit trail sai lệch | Versioned decision, finding và closure trail |
| Chỉ kiểm canary rồi suy rộng toàn production | Regions/tenants cũ có thể chưa cập nhật | Full-scope inventory reconciliation |
| Không xem security khi rollback | Có thể tái đưa lỗ hổng vào production | Retest security gates sau rollback |
| Bỏ qua data quality của pipeline | Dashboard xanh khi collector im lặng | Monitoring của evidence sources và quality gate |
| Dùng approval để che nghĩa vụ không cho ngoại lệ | Decision nội bộ không thay hợp đồng/pháp luật | Applicability và authority review |
| Không cập nhật threat model sau thay đổi | Attack paths mới không được theo dõi | Delta review, regression tests và monitoring |

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Một PR chỉ sửa một dòng trong IAM policy, thay resource cụ thể thành wildcard. Đội development gọi đây là minor change vì diff nhỏ. Cần xử lý ra sao?

**Gợi ý:** Phân tầng theo privilege, exposure, data và blast radius; kiểm effective permission, resource scope, negative tests, approval và rollback. Số dòng diff không quyết định rủi ro.

**Câu 2.** CI/CD PASS trên image A nhưng production sử dụng mutable tag trỏ đến image B. Có thể coi security change review hoàn tất không?

**Gợi ý:** Chưa. Cần đối soát deployed artifact digest với artifact đã review và kiểm effective configuration/runtime. CI PASS của A không chứng minh B đạt.

**Câu 3.** Tổ chức thêm endpoint export dữ liệu, mọi unit test happy-path PASS. Cần thêm test nào?

**Gợi ý:** Negative object/tenant authorization, role matrix, token scope, rate limiting, log/audit, data minimization, retention, temporary export cleanup và đường batch/API tương đương.

**Câu 4.** Một vendor thêm subprocessor mới nhưng application code của khách hàng không đổi. Có cần security change review?

**Gợi ý:** Có thể cần delta assessment về data flow, applicability, contract, region, security controls và shared responsibility dù không có commit nội bộ.

**Câu 5.** Một change đã APPROVED_FOR_DEPLOY. Sau rollout, role effective rộng hơn plan. Có thể giữ trạng thái VERIFIED vì đã có approval không?

**Gợi ý:** Không. Runtime validation phát hiện deviation; cần triage, containment/rollback hoặc review bổ sung theo criticality. Approval ban đầu không bao phủ scope sai.

**Câu 6.** Hotfix đang bị khai thác cần triển khai khẩn. Có cần hoàn thành toàn bộ quy trình regular release trước không?

**Gợi ý:** Không nhất thiết; dùng emergency path với minimum security/availability guardrails, người quyết định, audit evidence và hậu kiểm có thời hạn. Không bỏ mọi kiểm soát.

**Câu 7.** Thay format log, agent heartbeat vẫn healthy, nhưng alert về thay đổi quyền không còn hoạt động. Kết luận?

**Gợi ý:** Telemetry health theo heartbeat không đủ; end-to-end detection assertion FAIL. Cần parser/rule remediation, test lại event fidelity và route alert.

**Câu 8.** KMS key rotation thành công ở API production nhưng restore thử tại DR account thất bại. Change có đạt không?

**Gợi ý:** Có thể pass ứng dụng hiện tại nhưng fail recovery security assertion. Cần sửa quyền key/backup và retest, không đóng toàn change khi critical recovery gate chưa đạt.

**Câu 9.** Một reviewer nói “không có alert production trong 30 phút sau deploy, nên change an toàn”. Kết luận này có đủ căn cứ?

**Gợi ý:** Không. Cần biết detection coverage, data quality, expected events và control assertions, cùng monitoring window theo business cycles.

**Câu 10.** Thay role của 20 principals, test PASS với hai account staging. Có thể kết luận 20 production principals đều đạt?

**Gợi ý:** Không tự suy rộng. Cần kiểm effective policy và population, và negative cases trong môi trường đại diện hoặc runtime scope phù hợp.

**Câu 11.** Security change review phát hiện một điểm yếu mới nhưng team cho rằng “chưa có incident”. Có thể xóa finding không?

**Gợi ý:** Không có incident không phủ định control weakness. Ghi condition, risk, evidence và decision phù hợp; không tự kết luận đã bị khai thác.

**Câu 12.** Một change đã được triển khai fix nhưng không có retest vì collector hỏng. Nên đánh trạng thái gì?

**Gợi ý:** DEPLOYED_UNVERIFIED hoặc INCONCLUSIVE; cần sửa collector/thu evidence thay thế, không tự chấm PASS.

**Câu 13.** Risk owner chấp nhận ngoại lệ MFA tạm 7 ngày cho một hệ thống legacy. Có nghĩa control MFA PASS không?

**Gợi ý:** Không. Risk acceptance khác control assurance verdict; phải giữ scope, expiry, compensating controls và điều kiện khắc phục.

**Câu 14.** Vì sao code rollback không luôn khôi phục hệ thống về trạng thái cũ?

**Gợi ý:** Data schema, transactions, credentials, keys, cached sessions, replicas và external systems có thể đã thay đổi không thể đảo; cần plan data restore/fail-forward và security validation.

**Câu 15.** Dashboard có 100% approved changes nhưng không phát hiện console changes. Điều gì sai ở metric?

**Gợi ý:** Mẫu số chỉ gồm change records đã vào workflow, bỏ sót out-of-band changes. Cần reconciliation với runtime/audit/deployment inventory.

**Câu 16.** Có 90 high-relevance changes thuộc diện security assurance, 64 đã verified PASS, bốn FAIL, hai INCONCLUSIVE và 20 chưa đủ review/evidence. Verified coverage bao nhiêu?

**Gợi ý:** 64/90 ≈ 71,1%. Không tính missing/FAIL/unknown vào PASS và công bố denominator là required changes.

## 30. Bài thực hành: đánh giá một thay đổi đa hệ thống

### 30.1. Bối cảnh

Một doanh nghiệp vận hành dịch vụ thanh toán và cổng hỗ trợ khách hàng trên Kubernetes/cloud. Một feature mới cho phép nhân viên hỗ trợ xuất báo cáo đơn hàng có giới hạn. Để triển khai, nhóm kỹ thuật đề xuất **cùng một release**:

- Thêm endpoint export vào Java API.
- Thêm role support có quyền đọc một số trường dữ liệu đơn hàng.
- Tạo service account mới để chạy batch export.
- Mở egress từ workload đến một SaaS phân tích của bên thứ ba.
- Thêm queue và object storage tạm giữ file export.
- Thay database schema thêm cột chứa thông tin liên lạc khách hàng.
- Rotate encryption key cho dataset.
- Chỉnh parser audit log để hỗ trợ event export.
- Nâng base image của workload đang có một vulnerability.
- Tăng autoscaling limit cho service.
- Có backup hằng ngày nhưng lần DR test gần nhất không bao phủ key mới.
- Product owner muốn rollout nhanh nhưng có một vendor report chỉ bao phủ nền tảng SaaS cũ.

**Dữ liệu kiểm tra giả định:**

- Unit tests API mới PASS.
- Negative cross-tenant export test FAIL.
- IaC plan không có lỗi network hardening theo rule hiện hành.
- Effective IAM policy cho service account mới chưa được review.
- Audit events thử không xuất hiện đúng actor field ở SIEM.
- DR recovery account chưa có quyền KMS key mới.
- Có 10 pods canary, 8 chạy image mới, 2 vẫn chạy image cũ.
- Product owner đã approve tính năng; security approval chưa hoàn thành.
- Không có bằng chứng về incident hay data breach thực tế.

### 30.2. Nhiệm vụ

1. Tạo **change record** gồm before/after scope, service/data/roles/regions/vendors, owner và thời điểm.
2. Xác định **critical triggers** và đề xuất tier có lý do, không dựa số dòng code.
3. Vẽ data-flow trước/sau và chỉ ra các trust boundaries mới.
4. Liệt kê ít nhất **10 control assertions** liên quan IAM, object authz, data, privacy, logging, supply chain, KMS/DR và runtime.
5. Lập ma trận **pre-deploy gates**: bằng chứng nào phải PASS trước khi approve?
6. Phân loại những test hiện có thành PASS/FAIL/INCONCLUSIVE/NOT_TESTED, có scope và giới hạn.
7. Xác định quyết định **go/no-go** theo một policy giả định, ghi owner và conditions.
8. Đề xuất remediation cho cross-tenant export FAIL, parser mất actor field và DR KMS permission.
9. Viết positive/negative tests cho quyền export theo tenant, rate limits và lifetime của file tạm.
10. Xây acceptance criteria cho key rotation + database migration + restore.
11. Thiết kế progressive rollout và cách xác minh toàn bộ pods dùng đúng image digest.
12. Nêu conditions để rollback/fail-forward, data reconciliation và bảo vệ evidence.
13. Lập evidence manifest gồm các artifacts gắn commit/build/deploy/test IDs.
14. Xác định các thay đổi phải review với vendor và bộ phận privacy/compliance theo phạm vi.
15. Viết executive summary gửi service/risk owner: quyết định cần phê duyệt, rủi ro chưa xử lý và thời gian review theo policy đã cho.
16. Đề xuất ba KPI đo chất lượng security change review theo population độc lập.

### 30.3. Đáp án định hướng

**Go/no-go:** nếu policy định nghĩa tenant authorization, required audit events và DR/key recovery cho dữ liệu này là critical gates, release chưa thể được coi **APPROVED_FOR_DEPLOY** khi negative authz test FAIL, actor field mất và recovery chưa chứng minh được. Product approval không thay security/governance approval. Đội triển khai có thể sửa và test lại, hoặc chia rollout thành các bước riêng với phạm vi không xử lý dữ liệu thật nếu phù hợp thẩm quyền.

**Remediation:** sửa object-level authz ở server/data-access boundary; chuẩn hóa parser/audit schema với end-to-end event test; cấp quyền KMS tối thiểu cho recovery account và chạy restore rehearsal; kiểm toàn 10 pods canary, xử lý hai pods cũ và test runtime image digest.

**Evidence:** test report có nguồn/phiên bản, effective IAM export, Kubernetes deployed digest, migration reconciliation, data classification/approval, vendor data-flow decision, SIEM event test, DR decrypt/restore report. Một checklist tick hoàn tất không thay các artifacts này.

### 30.4. Tiêu chí đánh giá

| Tiêu chí | Đạt khi |
|---|---|
| **Scope** | Tài sản, data classes, roles, regions, vendor và dependency đầy đủ |
| **Risk** | Critical triggers dựa trên data/privilege/observability/recovery thực |
| **Threat model** | Có abuse scenarios và trust-boundary delta |
| **Acceptance** | Assertions rõ positive/negative cases và phạm vi |
| **Evidence** | Mỗi kết luận gắn nguồn, test/version, thời điểm và limitations |
| **Decision** | Phân biệt functional approval, pre-deploy approval và runtime verification |
| **Remediation** | Có owner, action, retest và root-cause prevention |
| **Recovery** | Có data integrity, KMS, rollback/fail-forward và BIA |
| **Third-party** | Có shared responsibility, data-flow và applicability review |
| **Reporting** | Dashboard có mẫu số required changes, unknown và critical blockers |
| **Integrity** | Record giữ lịch sử, không ghi đè failed tests/approval |
| **Continuous** | Có monitoring window, drift detection và reassessment triggers |

## 31. Checklist Security change review trước và sau triển khai

### 31.1. Trước khi phê duyệt

- [ ] Change ID, business justification, owner và scope đã được xác định.
- [ ] Before/after code/config/architecture/data-flow/permission diff có thể truy lại.
- [ ] Các tài sản, môi trường, region, tenant và dependencies bị ảnh hưởng được đối soát từ inventory.
- [ ] Dữ liệu, đặc quyền, exposure và business criticality đã được đánh giá.
- [ ] Change risk tier có căn cứ và những hard triggers đã được kiểm.
- [ ] Threat-model delta được hoàn thành với trust boundaries có thay đổi.
- [ ] Các security controls và nghĩa vụ/commitments applicable được mapping.
- [ ] Có assertion và acceptance criteria rõ ràng cho controls quan trọng.
- [ ] Code, IaC, IAM, API, CI/CD, vendor, data và resilience reviews được chọn theo tác động.
- [ ] Có positive/negative tests đối với authentication, authorization và critical paths.
- [ ] Security logging/detection changes có test event và alert routing phù hợp.
- [ ] Sensitive data changes đã được phân loại, review privacy/contract khi cần.
- [ ] Key/secret changes có vòng đời, quyền truy cập và recovery plan.
- [ ] Artifact provenance, dependency security và runtime image identity có evidence.
- [ ] Data migration/irreversible change có consistency, backup và fail-forward/rollback plan.
- [ ] Critical security gates FAIL không được che bằng overall scan score.
- [ ] Missing evidence/unknown có trạng thái, owner và hạn xử lý.
- [ ] Reviewer roles, separation of duties và approval authority rõ.
- [ ] Residual risks/exceptions có reason, scope, compensating controls và expiry.
- [ ] Decision được gắn với actual commit/artifact/config/change window.
- [ ] Có canary, stop conditions, business/security monitoring và emergency contacts.

### 31.2. Sau khi triển khai

- [ ] Deployed versions, image digests và effective policies khớp approval.
- [ ] Tất cả affected assets/regions/tenants/pods được đối soát; không chỉ canary đã pass.
- [ ] Positive/negative runtime tests của critical assertions được thực hiện đúng scope.
- [ ] IAM, network, encryption, tenant boundaries và token/session behavior đúng expected.
- [ ] Synthetic event đi qua source → collector → SIEM/alert theo acceptance criteria.
- [ ] Không phát hiện mất trường actor, resource, action, outcome hoặc dữ liệu audit bắt buộc.
- [ ] Data migration có reconciliation, integrity checks và retention safeguards.
- [ ] Backup/DR/key restore được đánh giá lại khi change tác động recovery path.
- [ ] Business functionality, rate limits, latency và error rates đạt tiêu chí đã duyệt.
- [ ] Monitoring window phù hợp với batch cycles, users, tenant và criticality.
- [ ] Mọi confirmed control failure/unknown được lập finding và xử lý theo risk.
- [ ] Rollback/fail-forward khi có xảy ra cũng được security verified.
- [ ] Critical exceptions/temporary permissions đã được đóng hoặc có approval hạn chế.
- [ ] Manual/emergency changes được reconcile vào source of truth.
- [ ] Post-change validation và closure có reviewer, timestamps, evidence IDs.
- [ ] Audit trail giữ nguyên failed tests, approvals cũ và thay đổi scope.
- [ ] Security baselines, threat models, runbooks, detections và inventory được cập nhật.
- [ ] Monitoring/drift và review triggers tiếp tục hoạt động sau khi change đóng.
- [ ] Những preventive actions và remediation còn lại có owner/deadline độc lập.
- [ ] Báo cáo không tuyên bố an toàn ngoài phạm vi, kỳ và bằng chứng đã kiểm.

## Kết luận

**Security change review là một quy trình đánh giá tác động và kiểm chứng bảo mật của thay đổi, không phải một chữ ký hình thức trước triển khai.** Cốt lõi là hiểu điều gì đổi trong các ranh giới tin cậy, dữ liệu, quyền và dependencies; xác định security objectives/controls bị ảnh hưởng; kiểm tra có bằng chứng trước và sau thay đổi; ra quyết định phù hợp rủi ro; và bảo đảm khả năng phát hiện, rollback, phục hồi và theo dõi sau triển khai.

Trong **SECURITY_SECURITY_ASSURANCE**, change assurance hiệu quả phải duy trì chuỗi truy vết **change request → before/after impact → risk/threat-model delta → security assertions → evidence/pre-deploy gates → authorized decision → controlled deployment → runtime verification → finding/remediation → verified closure → continuous monitoring**. Khi tổ chức giữ riêng trạng thái approved, deployed, verified và risk accepted, đồng thời dùng dữ liệu production có nguồn tin cậy, Security change review giúp các hệ thống tiếp tục đạt mục tiêu bảo mật qua mỗi lần phát triển và vận hành — thay vì chỉ an toàn trên bản thiết kế hoặc ở một kỳ audit.



