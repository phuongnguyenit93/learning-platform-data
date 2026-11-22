# Quy trình plan, review, apply và quản lý thay đổi

Infrastructure as Code (IaC) cho phép mô tả hạ tầng cloud bằng các file có thể version hóa, review, kiểm thử và triển khai lặp lại. Tuy vậy, việc lưu cấu hình vào Git chưa tự động làm cho thay đổi hạ tầng an toàn. Một dòng sửa nhỏ có thể mở public database, thay IAM policy, xóa storage, thay subnet route hoặc làm gián đoạn nhiều workload. Vì vậy, IaC cần một quy trình thay đổi có kiểm soát từ lúc đề xuất đến khi áp dụng và xác minh trạng thái thực tế.

Quy trình phổ biến gồm **plan → review → approve → apply → verify**, đi cùng quản lý state, drift, rollback/recovery và evidence. Plan cho biết công cụ dự kiến làm gì; review kiểm tra tác động và tính đúng đắn; approval xác nhận người có thẩm quyền chấp thuận rủi ro; apply thực hiện thay đổi; verify kiểm tra hạ tầng sau triển khai và cập nhật bằng chứng. Mỗi bước cần danh tính, quyền hạn, trạng thái và dấu vết rõ ràng.

Bài học thuộc phần **Hạ tầng dưới dạng mã** của học phần kiến trúc cloud. Mục tiêu là biến thay đổi hạ tầng thành một quy trình có thể lặp lại, có thể kiểm chứng và có khả năng phục hồi, đồng thời cân bằng bảo mật, độ tin cậy, hiệu năng, chi phí và tốc độ delivery theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Mô tả vòng đời một thay đổi IaC từ pull request đến production.
- Đọc plan và phân loại create, update, replace, delete cùng blast radius.
- Thiết kế code review, policy-as-code, test và approval theo mức rủi ro.
- Quản lý state, remote backend, locking, versioning và quyền truy cập.
- Phát hiện, đánh giá và xử lý configuration drift.
- Áp dụng apply có kiểm soát, concurrency guard và deployment strategy.
- Xử lý thay đổi thất bại bằng recovery plan thay vì giả định rollback luôn an toàn.
- Thu thập evidence và quản trị ngoại lệ, thay đổi khẩn cấp và audit.

## 1. Vòng đời của một thay đổi IaC

Một thay đổi hạ tầng thường bắt đầu bằng một yêu cầu có mục tiêu, ví dụ tạo private endpoint cho database, tăng dung lượng cluster hoặc thay policy của workload identity. Yêu cầu phải được chuyển thành diff có thể review, plan được sinh trên trạng thái đáng tin cậy, và apply phải sử dụng đúng artifact đã được duyệt.

~~~mermaid
flowchart TD
    REQ["Change request / work item"] --> BR["Branch and IaC change"]
    BR --> TEST["Format, validate, tests"]
    TEST --> PLAN["Generate plan"]
    PLAN --> POLICY["Policy and risk evaluation"]
    POLICY --> REVIEW["Human review"]
    REVIEW --> APPROVE{"Approval granted?"}
    APPROVE -- "No" --> UPDATE["Revise or close"]
    UPDATE --> BR
    APPROVE -- "Yes" --> APPLY["Apply approved plan"]
    APPLY --> VERIFY["Post-apply verification"]
    VERIFY --> EVIDENCE["Record evidence and state"]
    EVIDENCE --> MONITOR["Monitor drift and runtime health"]
~~~

Các bước này không nhất thiết là các hệ thống riêng. Chúng có thể nằm trong một CI/CD pipeline, nhưng ranh giới trách nhiệm và trạng thái cần được giữ rõ.

### Vai trò của từng bước

| Bước | Câu hỏi phải trả lời | Đầu ra |
| --- | --- | --- |
| Request | Tại sao cần thay đổi, owner là ai, môi trường nào? | Change request, acceptance criteria |
| Code | Thay đổi nào trong source of truth? | Commit, pull request, diff |
| Test | Cấu hình có hợp lệ và đáp ứng policy không? | Format, validation, test result |
| Plan | Provider dự định tạo/sửa/xóa tài nguyên gì? | Plan artifact |
| Review | Tác động, blast radius và rủi ro có chấp nhận được? | Review comments, risk assessment |
| Approve | Ai có thẩm quyền cho phép apply? | Approval record |
| Apply | Artifact được duyệt đã được áp dụng thành công chưa? | Apply result, run ID |
| Verify | Runtime state và behavior có đạt yêu cầu? | Health check, smoke test, evidence |
| Monitor | Có drift, lỗi hoặc tác động bất thường sau deploy không? | Alerts, drift report, follow-up |

### Nguyên tắc quan trọng

- Plan và apply phải thuộc cùng một chuỗi thay đổi có thể truy vết.
- Người duyệt phải hiểu plan và rủi ro, không chỉ bấm nút approve.
- Apply cần dùng identity riêng, quyền tối thiểu và phạm vi môi trường rõ.
- Chỉ một quy trình được phép ghi state tại một thời điểm theo locking semantics.
- Thay đổi ngoài pipeline phải được phát hiện và xử lý.
- Hoàn thành apply không đồng nghĩa ứng dụng đã hoạt động đúng; cần verify sau triển khai.

## 2. Change request và chuẩn bị thay đổi

Một pull request tốt bắt đầu từ yêu cầu cụ thể. Nếu mục tiêu chỉ là “tối ưu cloud” hoặc “sửa network”, reviewer khó đánh giá kết quả và mức rủi ro.

### Nội dung change request

Nên ghi:

- Mục tiêu nghiệp vụ hoặc kỹ thuật.
- Resource, module, account/project, region và environment liên quan.
- Trạng thái hiện tại và trạng thái mong muốn.
- SLO, security control hoặc policy bị tác động.
- Giả định, dependency và điều kiện tiên quyết.
- Blast radius nếu thao tác sai.
- Maintenance window hoặc downtime cần thiết.
- Kế hoạch verify, rollback/recovery và người liên hệ.
- Chi phí dự kiến và owner ngân sách nếu thay đổi có tác động đáng kể.

### Phân loại mức rủi ro

| Mức | Ví dụ | Kiểm soát gợi ý |
| --- | --- | --- |
| Thấp | Thêm tag, mô tả, dashboard không ảnh hưởng quyền hoặc traffic | Automated checks và review thông thường |
| Trung bình | Tăng capacity, thêm replica, thay cấu hình non-critical | Plan review, test, owner approval |
| Cao | Thay IAM, network route, encryption key, database topology | Security/platform review, explicit approval, staged apply |
| Rất cao | Xóa dữ liệu production, thay vùng phục vụ, thay đổi identity boundary | Dual review, maintenance plan, backup/restore evidence, change window |

Mức rủi ro cần dựa vào tác động thực tế, không chỉ loại resource. Xóa một resource sandbox có thể ít rủi ro; thay một IAM role dùng chung có thể ảnh hưởng nhiều hệ thống.

## 3. Plan: bản xem trước thay đổi

Plan là kết quả phân tích giữa cấu hình mong muốn, state được quản lý và dữ liệu provider mà công cụ có thể đọc. Nó cho biết những hành động dự kiến, thường gồm:

- **Create:** tạo resource mới.
- **Update in-place:** sửa thuộc tính mà không thay resource.
- **Replace:** xóa resource cũ và tạo resource mới hoặc theo thứ tự provider yêu cầu.
- **Delete:** xóa resource.
- **No-op:** không cần thay đổi theo mô hình hiện tại.

### Đọc plan theo tác động

Không chỉ đếm số dòng. Hãy xem:

1. Resource nào thay đổi và thuộc môi trường nào?
2. Thuộc tính nào đổi? Đây là mutable hay force replacement?
3. Thứ tự create/delete có tạo downtime hoặc mất dữ liệu không?
4. Có IAM/network/public access/security group nào mở rộng quyền?
5. Có encryption, key, backup, retention hoặc residency nào thay đổi?
6. Có dependency nào bị recreate kéo theo?
7. Có thay đổi nào ngoài mục tiêu request?
8. Chi phí có tăng, giảm hoặc phát sinh phí chuyển dữ liệu không?

### Replacement cần chú ý

Một thay đổi có thể nhìn như update nhưng provider yêu cầu replace, ví dụ thay thuộc tính định danh hoặc subnet của resource. Với database, volume hoặc bucket chứa state, replace có thể gây gián đoạn hoặc mất dữ liệu nếu lifecycle và migration chưa được thiết kế.

Khi plan có replace/delete với resource stateful, phải kiểm tra backup, snapshot, retention, data migration và restore test. Không approve chỉ vì công cụ báo plan hợp lệ.

### Plan là snapshot có thời hạn

Plan được sinh từ một trạng thái tại một thời điểm. Nếu state, provider configuration hoặc tài nguyên ngoài hệ thống thay đổi trước khi apply, plan có thể không còn phù hợp. Với công cụ hỗ trợ saved plan, nên lưu artifact bất biến và apply đúng artifact đã review. Nếu plan stale hoặc không thể áp dụng an toàn, tạo plan mới và review lại.

Không chạy lại plan âm thầm sau approval rồi apply kết quả khác. Một plan mới có thể chứa thay đổi mới, nên cần quay lại bước review theo policy.

## 4. Code review và review plan

Review IaC cần xem cả code lẫn kết quả provider dự kiến. Source diff giải thích ý định; plan thể hiện hành động cụ thể. Hai góc nhìn bổ sung cho nhau.

### Review source

- Module/resource có đúng mục tiêu và đúng abstraction không?
- Naming, tags, environment và ownership có nhất quán?
- Input variable có validation và default an toàn?
- Có secret, key material hoặc credential trong code/state output không?
- Có hardcode account, region, CIDR hoặc identity không phù hợp?
- Dependency, provider version và module version có được pin/kiểm soát?
- Có test hoặc example cho interface mới?
- Có thay đổi ngoài scope bị đưa vào cùng PR không?

### Review plan

- Tài nguyên tạo/sửa/xóa có phù hợp diff?
- Có unexpected replacement hoặc destroy?
- IAM policy có wildcard hoặc quyền escalation?
- Network có public exposure hoặc mở port rộng?
- Database/storage có thay đổi encryption, retention, backup?
- Có thay đổi DNS, routing, load balancer hoặc endpoint?
- Có blast radius vượt một service/account/region?
- Cost estimate và capacity có hợp lý?

### CODEOWNERS và required reviewers

Có thể yêu cầu owner của module hoặc control phê duyệt. Ví dụ thay đổi network cần platform/network owner; thay đổi IAM nhạy cảm cần security review; thay đổi database state cần data/platform owner. Quyền merge code và quyền apply production nên được tách theo separation of duties.

### Review comment phải có thể hành động

Thay vì “có vẻ rủi ro”, reviewer nên chỉ rõ resource, thuộc tính, tác động và điều kiện cần trước khi approve. Ví dụ: “Plan sẽ thay database subnet group và recreate instance; bổ sung migration/restore evidence và maintenance plan trước khi apply.”

## 5. Kiểm thử trước khi plan/apply

Các kiểm tra tĩnh và tự động giúp phát hiện lỗi sớm, nhưng không thay thế review plan hoặc runtime verification.

| Lớp kiểm tra | Ví dụ | Phát hiện |
| --- | --- | --- |
| Format/lint | Formatter, linter | Lỗi cú pháp, style và pattern nguy hiểm |
| Validate | IaC validate/provider schema | Cấu hình không hợp lệ, thiếu input |
| Unit/module test | Kiểm tra locals, naming, output và logic module | Sai logic có thể kiểm tra cục bộ |
| Static security scan | Misconfiguration, secret scan | Public resource, encryption thiếu, secret |
| Policy-as-code | Region, tag, IAM, network, backup rule | Vi phạm guardrail tổ chức |
| Integration test | Deploy ephemeral environment | Tương tác provider/module |
| Plan review | Plan artifact | Tác động thật trên workspace/environment |
| Post-apply test | Smoke test, API/connection check | Resource không hoạt động như mong đợi |

### Unit test và integration test

Unit test phù hợp cho logic không cần gọi provider thật. Integration test nên dùng sandbox riêng, dữ liệu thử và identity giới hạn. Không để test pipeline vô tình áp dụng vào production hoặc xóa tài nguyên ngoài scope.

### Policy-as-code

Policy có thể chặn database public, resource thiếu encryption, region ngoài danh sách, IAM wildcard hoặc production resource thiếu owner tag. Policy cần có:

- Scope và resource type chính xác.
- Severity và hành vi deny/warn/audit.
- Lý do nghiệp vụ và remediation guidance.
- Version, owner và review cadence.
- Cơ chế exception có thời hạn.
- Test positive/negative để tránh false positive.

Ví dụ pseudocode:

~~~text
deny if environment == "production"
     and resource.type == "database"
     and resource.public_access == true

deny if resource.data_classification == "restricted"
     and resource.encryption_at_rest != true

require if resource.environment == "production"
     then resource.owner != ""
      and resource.backup_policy != ""
~~~

Đây là logic minh họa, không phải cú pháp của một engine cụ thể.

## 6. Approval và separation of duties

Approval xác nhận người có thẩm quyền đã xem xét mục tiêu, plan, rủi ro và bằng chứng trước khi thay đổi được thực hiện. Không nên để một identity tự viết code, tự duyệt và tự apply những thay đổi production có rủi ro cao mà không có kiểm soát bổ sung.

### Quy tắc approval

- PR có reviewer theo CODEOWNERS hoặc risk classification.
- Production apply cần approval tách khỏi quyền merge nếu mức rủi ro yêu cầu.
- Thay đổi IAM/network/data destruction có reviewer chuyên trách.
- Approval gắn với commit/plan artifact cụ thể.
- Plan stale, source commit thay đổi hoặc policy version đổi thì approval có thể hết hiệu lực.
- Emergency change có quy trình rút gọn, log lý do và retrospective review.

### Ma trận vai trò mẫu

| Vai trò | Quyền chính | Không nên mặc nhiên có |
| --- | --- | --- |
| Developer | Sửa module và mở PR | Production apply credential |
| Reviewer | Review source/plan trong scope | Tự thay đổi plan đã duyệt |
| Platform owner | Xem xét topology, provider, state và capacity | Quyền đọc dữ liệu nghiệp vụ không liên quan |
| Security reviewer | Duyệt control IAM/network/encryption | Quyền apply mọi resource |
| Release approver | Approve production change | Quyền sửa source sau khi duyệt |
| CI/CD apply identity | Apply artifact trong workspace/environment được cấp | Quyền admin toàn account nếu không cần |
| Auditor | Read-only evidence | Sửa state, log hoặc approval record |

Một người có thể giữ nhiều vai trò ở tổ chức nhỏ, nhưng cần compensating control như dual approval, signed artifact, immutable log hoặc review sau triển khai.

## 7. State, remote backend và locking

IaC state ánh xạ cấu hình trong code với resource thực tế. Với Terraform-like tools, state có thể chứa resource identifiers, attributes và đôi khi dữ liệu nhạy cảm. Do đó state là tài sản quan trọng, cần bảo vệ tương tự hoặc chặt hơn hạ tầng được quản lý.

### Remote state

Trong team, state thường được lưu ở backend từ xa để nhiều người và CI/CD dùng chung. Backend cần:

- Authentication bằng workload identity hoặc credential ngắn hạn.
- Encryption at rest và in transit.
- Access control theo project/workspace/environment.
- Versioning hoặc recovery mechanism.
- Audit access/change và backup phù hợp.
- Network path được kiểm soát.
- Không public state object hoặc output nhạy cảm.

Không lưu state trong Git repo công khai hoặc gửi file state qua chat/ticket. State có thể chứa secret dù output đã bị đánh dấu sensitive.

### Locking

Lock ngăn hai tiến trình cùng sửa state của một workspace gây race hoặc corruption. Pipeline cần fail rõ nếu không lấy được lock; không xóa lock thủ công chỉ vì một job đang chờ. Trước khi force-unlock, xác minh tiến trình sở hữu lock đã chết và không còn apply đang chạy.

### Workspace và state isolation

Phân tách state theo environment, account, region hoặc domain sao cho blast radius và quyền truy cập hợp lý. Một state khổng lồ có thể làm plan chậm và mọi thay đổi liên quan tới nhau; quá nhiều state nhỏ lại tăng overhead vận hành. Chọn ranh giới theo lifecycle, ownership và failure domain.

### State backup và recovery

Trước thay đổi state-sensitive hoặc nâng cấp tool/provider, bảo đảm backend có version/backup và biết cách khôi phục. Không sửa state bằng tay trừ quy trình repair đã được kiểm chứng. State restore sai thời điểm có thể làm công cụ nghĩ resource đã mất hoặc quản lý nhầm resource.

## 8. Provider, module và dependency version

Plan reproducible cần kiểm soát version của IaC engine, provider và module. Nếu mỗi lần chạy tự lấy latest, cùng một commit có thể sinh plan khác nhau do schema hoặc behavior thay đổi.

### Version management

- Pin provider theo constraint đã kiểm thử.
- Dùng lock file để ghi provider selection và checksum nếu công cụ hỗ trợ.
- Pin module source/tag/commit phù hợp chính sách.
- Nâng version trong PR riêng có test và plan review.
- Đọc release note, breaking change và migration guide.
- Test provider upgrade trong sandbox trước production.

### Dependency graph

Resource có thể phụ thuộc vào network, IAM, key, database, DNS hoặc certificate. Thứ tự tạo/xóa sai có thể khiến deploy lỗi hoặc xóa nhầm dependency đang dùng. Ưu tiên dependency tường minh và module interface ổn định; tránh dùng dependency ẩn dựa trên tên hoặc timing.

Không tách module chỉ để tăng số lượng file. Ranh giới module nên phản ánh ownership, lifecycle và interface có thể tái sử dụng.

## 9. Apply: thực hiện đúng thay đổi đã duyệt

Apply là bước thay đổi cloud resource thật. Nó cần đúng identity, workspace, provider context, commit và plan artifact.

### Pre-apply checks

- Source commit đúng với commit được duyệt.
- Plan artifact còn hiệu lực và chưa bị thay đổi.
- Workspace/account/region/environment đúng.
- State lock được giữ.
- Approval còn hiệu lực và gắn đúng artifact.
- Credential/apply identity đúng scope và chưa hết hạn.
- Maintenance window và dependency sẵn sàng.
- Không có thay đổi concurrent ngoài quy trình.

### Saved plan

Với công cụ hỗ trợ saved plan, pipeline có thể tạo plan artifact, review artifact rồi apply chính artifact đó. Cách này giảm nguy cơ người duyệt xem một plan nhưng CI chạy một plan khác. Plan file cũng có thể chứa thông tin nhạy cảm; cần bảo vệ artifact store, retention ngắn phù hợp và hạn chế quyền download.

### Concurrency control

Tránh hai pipeline apply cùng workspace hoặc cùng resource scope đồng thời. Có thể dùng environment concurrency group và backend lock. Lock state không nhất thiết khóa mọi thao tác console hoặc hệ thống ngoài IaC; cần phối hợp change window và kiểm tra drift.

### Apply theo giai đoạn

Thay đổi lớn có thể chia thành nhiều phase:

1. Tạo dependency mới như IAM, network hoặc key.
2. Tạo resource đích và kiểm tra health.
3. Chuyển traffic hoặc data flow.
4. Quan sát và đối soát.
5. Xóa resource cũ khi đã hết rollback window.

Không gộp tất cả bước destructive vào một apply nếu có thể tách để giảm blast radius.

## 10. Chiến lược triển khai thay đổi an toàn

Không phải mọi resource đều cần cùng một cách apply.

| Chiến lược | Cách làm | Hợp với | Điều kiện |
| --- | --- | --- | --- |
| Small batch | Áp dụng nhóm thay đổi nhỏ | Thay đổi có phạm vi rõ | Plan độc lập và dễ verify |
| Staged rollout | Triển khai lần lượt theo environment/region | Thay đổi có thể kiểm tra tăng dần | Có health gate và rollback/recovery |
| Blue/green | Dựng môi trường mới, kiểm tra rồi chuyển traffic | Gateway, service cluster, một số managed resource | Data/schema compatibility và cutover plan |
| Canary | Đưa một phần traffic hoặc một nhóm resource sang cấu hình mới | Workload hỗ trợ phân đoạn | Metric và ngưỡng tự động/owner rõ |
| Expand/contract | Mở rộng schema/config tương thích trước, rồi loại bỏ cũ | Database schema, API, IAM migration | Giai đoạn tương thích được duy trì đủ lâu |
| Maintenance window | Áp dụng thay đổi có downtime có kế hoạch | Thay đổi không thể rollout dần | Owner, thông báo, backup và recovery |

Infrastructure apply không tự tạo ra canary cho mọi loại tài nguyên. Cần xem provider/resource hỗ trợ gì và thiết kế ở lớp traffic/application khi cần.

### Expand/contract cho thay đổi schema

Ví dụ đổi tên field hoặc chuyển database:

1. Expand: thêm field/table mới hoặc target mới, vẫn tương thích với code cũ.
2. Dual-write/CDC có kiểm soát nếu cần, kèm consistency/reconciliation.
3. Migrate/backfill và validate.
4. Chuyển reader theo từng bước.
5. Theo dõi trong rollback window.
6. Contract: xóa field/resource cũ sau khi không còn consumer.

Không xóa cột hoặc endpoint trước khi tất cả consumer đã ngừng phụ thuộc.

## 11. Verify sau apply

Apply thành công chỉ cho biết công cụ/provider đã hoàn tất thao tác theo API. Nó không chứng minh ứng dụng, security control hoặc SLO đã đạt.

### Verification levels

| Lớp | Kiểm tra |
| --- | --- |
| Resource | Resource tồn tại, trạng thái và thuộc tính đúng |
| Network/security | Public exposure, route, IAM, TLS và security policy đúng |
| Application | Health check, kết nối, request/response và smoke test |
| Data | Schema, integrity, row count, replication và backup |
| Reliability | Failover/health, alert, autoscaling và recovery behavior |
| Cost | Capacity/tier/replica và estimate sau thay đổi |
| Governance | Tags, owner, region, audit log và evidence cập nhật |

### Post-apply evidence

Ghi lại:

- Change request/PR/commit ID.
- Plan artifact hash hoặc identifier.
- Approver và timestamp.
- Apply run ID, identity và workspace.
- Provider/resource result.
- Smoke test và control test.
- Drift/health scan sau deploy.
- Exception hoặc action item còn mở.

Không đưa secret, raw state hoặc credential vào evidence package.

## 12. Drift detection và reconciliation

Drift là khác biệt giữa cấu hình mong muốn được quản lý bằng IaC và trạng thái thực tế. Drift có thể đến từ console change, sửa chữa khẩn cấp, policy automation, provider default, resource ngoài IaC hoặc thay đổi do service quản lý.

### Các loại drift

- **Configuration drift:** thuộc tính của resource khác code/state.
- **Unmanaged resource:** tài nguyên được tạo ngoài IaC nhưng nằm trong scope cần quản lý.
- **State drift:** state không phản ánh đúng resource thực tế.
- **Dependency drift:** provider/module/version hoặc policy thay đổi.
- **Data/config drift:** dữ liệu/cấu hình runtime thay đổi qua cơ chế không thuộc IaC.

### Phát hiện drift

- Scheduled plan/refresh hoặc cloud configuration scan.
- IaC state refresh và plan so sánh.
- Cloud asset inventory/configuration service.
- Policy-as-code và drift alert.
- Audit log theo dõi console/API change.

### Xử lý drift

Không phải mọi drift đều phải tự động overwrite.

1. Xác định ai/điều gì tạo thay đổi và vì sao.
2. Kiểm tra đó là emergency fix, provider-managed field hay unauthorized change.
3. Đánh giá tác động và có cần incident/change record.
4. Chọn một trong ba hướng: cập nhật code để nhận drift, revert runtime về code, hoặc import/adopt resource vào IaC.
5. Tạo plan mới và review tác động trước khi apply.
6. Ghi evidence, cập nhật inventory và đóng finding.

### Ignore changes có chủ đích

Một số thuộc tính được autoscaler hoặc control plane quản lý động có thể cần ignore trong IaC. Nhưng ignore quá rộng sẽ che drift thật. Mỗi ignored attribute cần owner, lý do, phạm vi, test và review định kỳ; không dùng ignore để làm plan xanh mà không hiểu sai khác.

## 13. Rollback, recovery và thay đổi destructive

Rollback hạ tầng không giống rollback code. Resource có thể đã bị xóa, data schema đã đổi, key đã rotate hoặc dữ liệu mới đã được ghi vào hệ thống. Quay code về commit cũ không tự khôi phục trạng thái trước đó.

### Phân biệt rollback và recovery

- **Rollback:** đưa cấu hình/code về một phiên bản trước khi thay đổi.
- **Recovery:** khôi phục dịch vụ/dữ liệu bằng backup, snapshot, restore, recreate hoặc failover.
- **Forward fix:** tạo thay đổi mới để sửa lỗi khi rollback không an toàn hoặc không khả thi.

### Trước thay đổi destructive

- Kiểm tra resource lifecycle và deletion protection.
- Backup/snapshot và thử restore khi phù hợp.
- Xác định resource replacement và downtime.
- Kiểm tra dependency và consumer.
- Chốt RPO/RTO và data migration.
- Chuẩn bị người có quyền và recovery runbook.
- Xác định điểm không thể rollback, ví dụ sau khi dữ liệu mới đã được ghi.

### Terraform-like lifecycle controls

Một số IaC tool hỗ trợ cờ lifecycle như prevent destroy, create before destroy hoặc ignore changes. Chúng có thể giảm rủi ro nhưng không thay quy trình:

- Prevent destroy có thể chặn cả hoạt động bảo trì hợp lệ nếu không có kế hoạch tháo guard.
- Create before destroy cần tên/resource quota cho phép coexist.
- Ignore changes có thể che drift hoặc bỏ qua security regression.
- Replacement vẫn có thể gây downtime nếu resource identity hoặc provider semantics không hỗ trợ song song.

Chỉ dùng lifecycle setting khi hiểu hành vi provider và có test cho failure path.

## 14. Emergency change và break-glass

Sự cố production có thể cần thay đổi nhanh ngoài quy trình thông thường. Mục tiêu là cho phép khắc phục kịp thời nhưng vẫn bảo vệ state, identity và audit trail.

### Quy trình khẩn cấp

1. Xác định incident commander/owner có quyền quyết định.
2. Ghi lý do, scope, expected effect và nguy cơ.
3. Dùng credential break-glass có MFA và thời hạn ngắn.
4. Giới hạn thay đổi tối thiểu để ổn định dịch vụ.
5. Ghi lại lệnh/API change, identity, timestamp và resource.
6. Verify kết quả và theo dõi health.
7. Tạo PR/IaC reconciliation ngay sau khi ổn định.
8. Review sau sự cố, thu hồi quyền và đóng exception.

### Console change ngoài IaC

Nếu sửa trực tiếp qua console để xử lý sự cố, không để runtime và code ở hai trạng thái khác nhau kéo dài. Sau đó phải quyết định giữ thay đổi và cập nhật IaC, hay revert về cấu hình nguồn. Không chạy apply mù quáng vì có thể ghi đè emergency fix hoặc tạo thêm outage.

## 15. Bảo vệ pipeline và apply identity

Pipeline có quyền thay đổi hạ tầng production là một security boundary quan trọng.

### Workload identity

- Dùng federation/workload identity hoặc credential ngắn hạn thay cho access key dài hạn.
- Tách identity theo environment, account và pipeline job.
- Chỉ cấp quyền resource/action cần cho module/workspace.
- Hạn chế quyền tạo IAM role, policy attachment, public network và key.
- Không để contributor không đáng tin sửa pipeline rồi dùng production credential.

### Pipeline protection

- Branch protection và required review.
- Protect environment approval.
- Pin action/plugin/provider version và kiểm soát supply chain.
- Secret scan và dependency vulnerability scan.
- Chỉ chạy apply trên trusted branch/artifact.
- Giữ plan/apply artifact trong nơi có access control và integrity.
- Audit workflow change và permission change.

### State và plan artifact

State và plan có thể chứa dữ liệu nhạy cảm. Bảo vệ storage, encryption, download, retention, access và log. Không in toàn bộ state/plan ra CI log hoặc gắn file vào ticket công khai.

## 16. Quản lý thay đổi theo environment và dependency

Một quy trình tốt thường tiến từ environment ít rủi ro lên production.

### Promotion flow

~~~mermaid
flowchart LR
    DEV["Development"] --> TEST["Integration / Test"]
    TEST --> STAGE["Staging"]
    STAGE --> PROD["Production"]
    DEV -. "Same reviewed source" .-> TEST
    TEST -. "Promoted artifact/config" .-> STAGE
    STAGE -. "Approved plan for prod" .-> PROD
~~~

Cần phân biệt promotion code với promotion plan. Plan của staging không thể mặc nhiên apply production vì resource, state, account, region và policy khác nhau. Mỗi environment cần plan riêng và approval theo risk, nhưng nên giữ cùng source commit/module version.

### Dependency order

Thường triển khai theo thứ tự:

1. Account/project, baseline identity và policy.
2. Network, DNS, key và shared platform.
3. Data/compute/service resources.
4. Routing, access binding và integration.
5. Traffic cutover và cleanup.

Thứ tự cụ thể tùy hệ thống. Khi xóa, thường phải gỡ consumer/dependency trước rồi mới xóa nền tảng, nhưng cần kiểm tra provider dependency graph.

## 17. Cost, capacity và blast radius trong review

Review IaC không chỉ là review syntax. Hạ tầng có thể đúng về kỹ thuật nhưng quá đắt, không đủ capacity hoặc mở rộng phạm vi lỗi.

### Cost review

- Instance/tier/replica count và autoscaling bounds.
- Storage, IOPS, backup, snapshot và retention.
- NAT, load balancer, private endpoint và network egress.
- Cross-zone/cross-region transfer và replication.
- Log/metric volume và retention.
- License/support và idle resource.
- Tagging, cost allocation và budget alert.

### Capacity review

- Peak traffic và headroom.
- Connection limit và downstream quota.
- Capacity khi một node/zone/region lỗi.
- Autoscaling warm-up và scale-in behavior.
- Quota/service limit của provider.

### Blast radius

Ước lượng số service, tenant, region và data class có thể bị ảnh hưởng nếu plan sai hoặc apply bị gián đoạn. Chia state/workspace/module theo failure domain hợp lý và triển khai staged khi thay đổi rộng.

## 18. Evidence, audit và quản trị ngoại lệ

Một change record cần nối yêu cầu, code, plan, review, approval, apply và verification. Evidence phải đủ để trả lời ai đã thay đổi gì, tại sao, trên scope nào, ai duyệt và kết quả ra sao.

### Evidence package tối thiểu

| Bằng chứng | Nội dung |
| --- | --- |
| Request | Mục tiêu, owner, scope, risk |
| Source | PR, commit, module/provider version |
| Tests | Lint, validate, security/policy scan |
| Plan | Artifact ID/hash, action summary, plan timestamp |
| Review | Reviewer, comments, risk decision |
| Approval | Approver, thời điểm, environment, artifact reference |
| Apply | Run ID, identity, workspace, result |
| Verification | Health, security, smoke, data và cost checks |
| Follow-up | Drift status, issue, exception, remediation |

### Exception

Khi policy không thể đáp ứng ngay, exception cần:

- Control/policy và resource bị ảnh hưởng.
- Lý do, rủi ro và tác động.
- Compensating controls.
- Owner và người có thẩm quyền chấp nhận.
- Expiry, review cadence và remediation plan.
- Điều kiện tự động cảnh báo hoặc thu hồi.

Không để exception vĩnh viễn hoặc chỉ ghi trong comment PR. Hết hạn phải được xử lý hoặc phê duyệt lại theo policy.

## 19. Ví dụ thực tế: thay đổi private connectivity cho database

**Bối cảnh giả định:** Một ứng dụng cloud đang dùng managed relational database với cấu hình network cũ. Đội platform cần chuyển database sang private subnet và giới hạn client chỉ từ application security group. Production có traffic liên tục; thay đổi có thể tác động tới API, worker, migration job và support tool. Đây là ví dụ mô phỏng.

### Change request

- Mục tiêu: database không còn public exposure; chỉ workload được duyệt kết nối.
- Scope: production VPC, subnet group, security group, route và database endpoint.
- Rủi ro: mất kết nối từ worker/migration job hoặc endpoint thay đổi.
- Acceptance: application/worker kết nối qua private path; public connection thất bại; latency và error rate giữ SLO.

### Plan review

Review xác định:

- Database có bị replace hoặc restart không?
- Subnet group có đủ zone và capacity?
- DNS endpoint có giữ nguyên không?
- Security group có cho phép đúng port từ đúng source?
- Các job ngoài application có cần route/private resolver không?
- Terraform state và provider plan có stale không?
- Có chi phí endpoint, NAT hoặc data transfer mới không?

### Apply strategy

1. Tạo/cấu hình private network và route trước.
2. Cấp quyền và security group cho application/worker/migration identity.
3. Kiểm tra kết nối từ từng workload trong staging.
4. Tạo plan production và review lại.
5. Apply theo maintenance window nếu provider yêu cầu restart/cutover.
6. Chạy smoke test, query check và xác minh public access bị chặn.
7. Theo dõi error rate, connection pool và audit log.
8. Gỡ đường public cũ sau khi đã xác minh toàn bộ consumer.

### Recovery

Nếu application không thể kết nối, xác định route, DNS, security group và identity trước khi revert. Nếu phải tạm mở lại đường cũ, chỉ dùng exception khẩn cấp có giới hạn thời gian, audit và điều kiện thu hồi. Không mở database cho toàn internet như phương án chữa cháy.

## 20. Bài thực hành: xây dựng pipeline plan-review-apply

**Tình huống:** Một nhóm quản lý hạ tầng cho nền tảng thương mại điện tử bằng IaC. Repository có module network, database, compute và observability. Pipeline có thể tạo plan tự động cho pull request và apply khi được phê duyệt. Một số thay đổi ảnh hưởng IAM, database và public endpoint. Đây là tình huống mô phỏng.

### Nhiệm vụ

1. **Thiết kế workflow:** mô tả PR, validation, plan, policy, review, approval, apply và post-apply verify.
2. **Thiết kế plan review:** định nghĩa create/update/replace/delete risk classification, đặc biệt resource stateful và IAM/network.
3. **Thiết kế state:** remote backend, encryption, locking, versioning, backup, workspace và permission boundary.
4. **Thiết kế identity:** apply identity riêng theo environment, workload federation, least privilege và protected environment.
5. **Thiết kế policy gate:** chặn public database, encryption thiếu, IAM wildcard, region ngoài scope và resource không owner.
6. **Thiết kế drift:** phát hiện console change, phân biệt emergency drift với unauthorized change và quy trình reconcile.
7. **Thiết kế recovery:** backup, destructive plan approval, staged apply, rollback/forward fix và restore drill.
8. **Thiết kế evidence:** nối change request, commit, plan, approver, apply run và verification.

### Ma trận kiểm thử

| Phép thử | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Unexpected destroy | PR vô tình xóa database | Policy/review gate chặn hoặc yêu cầu approval cấp cao |
| IAM escalation | Policy thêm quyền wildcard | Security scan/policy test fail |
| Public exposure | Database endpoint chuyển public | Pre-deploy policy reject |
| State concurrency | Hai apply cùng workspace | Lock/concurrency group ngăn ghi đồng thời |
| Stale plan | State/resource đổi sau khi plan | Apply từ chối và yêu cầu re-plan/review |
| Drift | Console sửa security group | Drift scan tạo finding và quy trình reconcile |
| Failed apply | Provider lỗi giữa chừng | State nhất quán, runbook và retry/recovery rõ |
| Secret leak | State/plan có sensitive output | Artifact access/retention và log masking bảo vệ |
| Approval mismatch | Commit đổi sau khi approve | Approval mất hiệu lực hoặc pipeline chặn |
| Post-apply failure | Resource tạo xong nhưng app health fail | Roll-forward/recovery theo runbook |
| Emergency change | Break-glass sửa network | Audit, expiry, IaC reconciliation và review |
| Cost regression | Tăng replica hoặc storage bất thường | Cost/policy gate cảnh báo trước apply |

### Deliverables

- Pipeline diagram và state transition.
- Change request template và risk classification.
- Review checklist cho source và plan.
- State/backend/locking/access design.
- Policy-as-code rule và test cases.
- Approval/separation-of-duties matrix.
- Apply, verify, rollback/recovery và drift runbook.
- Evidence package schema và exception register.
- ADR nêu trade-off, owner và review trigger.

## 21. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho quy trình IaC |
| --- | --- |
| **Operational Excellence** | Change flow, owner, approval, evidence, runbook và drift reconciliation có nhất quán không? |
| **Security** | Pipeline identity, state, plan artifact, secret, IAM review và separation of duties có được bảo vệ? |
| **Reliability** | Locking, stale plan check, staged apply, backup, restore và recovery đã được thử? |
| **Performance Efficiency** | Plan/apply, module graph, resource sizing và rollout có đáp ứng delivery/performance mà không tạo rủi ro quá tải? |
| **Cost Optimization** | Plan review có tính compute, storage, network, backup, replica và operational overhead? |
| **Sustainability** | Có tránh tạo resource dư, môi trường ephemeral không được cleanup và log/plan retention không cần thiết? |

## 22. Những sai lầm thường gặp

**Apply trực tiếp từ branch bất kỳ.** Không có source review, plan review hoặc approval gắn với artifact.

**Duyệt code mà không xem plan.** Provider có thể yêu cầu replace/delete khác với điều reviewer suy ra từ diff.

**Apply một plan khác với plan đã duyệt.** Artifact mismatch làm mất ý nghĩa approval.

**Chạy hai apply đồng thời.** Có thể corrupt state hoặc tạo race trên resource.

**Lưu state/plan như file thường.** Chúng có thể chứa identifier và dữ liệu nhạy cảm; cần encryption, access và retention.

**Cho CI/CD quyền admin toàn account.** Một pipeline bị compromise có thể tạo quyền hoặc resource ngoài scope.

**Coi plan xanh là bằng chứng runtime tốt.** Hạ tầng có thể tạo thành công nhưng application không kết nối hoặc security control chưa hoạt động.

**Dùng auto-approve cho mọi production change.** Các thay đổi destructive, IAM và network cần kiểm soát theo rủi ro.

**Rollback bằng cách revert commit mà không xét dữ liệu.** Schema, stateful resource và key rotation có thể không tương thích với cấu hình cũ.

**Bỏ qua drift vì đã dùng IaC.** Console change hoặc policy automation vẫn có thể làm runtime khác code.

**Ignore changes quá rộng.** Drift thật và security regression có thể bị che.

**Không có reconciliation sau emergency change.** Runtime và source of truth lệch nhau kéo dài.

**Không lưu evidence.** Không thể chứng minh ai duyệt, artifact nào được apply và kiểm tra hậu triển khai đã đạt.

## 23. Checklist trước khi áp dụng thay đổi IaC production

- [ ] Change request có mục tiêu, owner, scope, risk và acceptance criteria.
- [ ] Source diff được version hóa, review và gắn commit bất biến.
- [ ] Format, validate, module test, secret/security scan và policy test đã đạt.
- [ ] Plan được tạo từ state/backend đúng và có timestamp/artifact ID.
- [ ] Create/update/replace/delete và blast radius được phân tích.
- [ ] Stateful/destructive change có backup, restore/migration và recovery evidence.
- [ ] Reviewer xem cả source lẫn plan; owner chuyên môn được yêu cầu theo risk.
- [ ] Approval gắn với đúng commit/plan/environment và hết hiệu lực khi artifact thay đổi.
- [ ] Apply identity là workload identity/credential ngắn hạn với least privilege.
- [ ] Remote state được mã hóa, access-controlled, versioned và có locking.
- [ ] Concurrency guard ngăn apply đồng thời trong cùng scope.
- [ ] Provider/module version được kiểm soát và nâng cấp có kiểm thử.
- [ ] Apply sử dụng đúng plan artifact đã duyệt.
- [ ] Thay đổi lớn được chia giai đoạn và có maintenance/cutover plan.
- [ ] Post-apply verify resource, network, security, application, data, reliability và cost.
- [ ] Drift detection và reconciliation có owner, cadence và runbook.
- [ ] Rollback/recovery phân biệt rõ; biết điểm không thể rollback.
- [ ] Emergency change có break-glass, audit, expiry và IaC reconciliation.
- [ ] Evidence nối request, source, tests, plan, review, approval, apply và verify.
- [ ] Exception có risk owner, compensating control, expiry và remediation plan.

Quy trình plan, review, apply và quản lý thay đổi biến IaC từ các file cấu hình thành một cơ chế vận hành hạ tầng có thể kiểm soát. Plan cho biết tác động dự kiến; review và approval đánh giá rủi ro; apply thực hiện đúng artifact đã duyệt; verify và drift monitoring xác nhận trạng thái thực tế. State, identity, locking, evidence và recovery là những phần cốt lõi của quy trình. Một thay đổi chỉ thực sự hoàn tất khi hạ tầng đáp ứng mục tiêu, kiểm soát vẫn có hiệu lực và tổ chức có thể truy vết cũng như phục hồi nếu điều gì đó đi sai.
