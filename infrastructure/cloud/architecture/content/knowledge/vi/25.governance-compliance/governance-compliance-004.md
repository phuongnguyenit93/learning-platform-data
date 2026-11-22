# Policy as code và guardrail ở cấp tổ chức

## 1. Vì sao tổ chức cần guardrail có thể kiểm chứng?

Khi một tổ chức vận hành nhiều team, project, subscription hoặc cloud account, mỗi nhóm có thể tự tạo network, compute, database và storage. Nếu mọi quyết định bảo mật, vị trí dữ liệu, logging và chi phí chỉ dựa vào tài liệu hướng dẫn, cấu hình thủ công và review cuối dự án, sai lệch sẽ xuất hiện khi số lượng môi trường tăng.

Ví dụ một nhóm tạo object storage công khai để chia sẻ ảnh thử nghiệm, nhưng vô tình đưa dữ liệu khách hàng vào đó. Nhóm khác triển khai database ở region chưa được phê duyệt. Một môi trường production mới được tạo mà chưa bật audit log. Những lỗi này có thể xảy ra dù kiến trúc tổng thể đã có tiêu chuẩn tốt, bởi tiêu chuẩn chưa được chuyển thành kiểm soát kỹ thuật áp dụng nhất quán.

**Policy as code (PaC)** là cách biểu diễn quy tắc quản trị dưới dạng mã hoặc dữ liệu có cấu trúc để máy có thể kiểm tra, thực thi, đánh giá và ghi nhận kết quả. **Guardrail** là cơ chế đặt ranh giới an toàn để các nhóm có quyền tự chủ triển khai trong phạm vi đã được tổ chức chấp thuận.

Trong module **CLOUD_ARCHITECTURE**, policy as code kết nối kiến trúc mạng, compute, dữ liệu, identity và triển khai với yêu cầu bảo mật, tuân thủ, độ tin cậy, chi phí và vận hành. Mục tiêu là giúp tổ chức mở rộng môi trường cloud mà vẫn duy trì các kiểm soát cần thiết theo tư duy Well-Architected.

Ví dụ xuyên suốt: công ty có nhiều business unit. Mỗi unit quản lý nhiều cloud project; team ứng dụng được phép tạo compute, database và storage qua pipeline. Tổ chức muốn bắt buộc mã hóa, audit log, network boundary và tagging; chỉ một số workload được phép xử lý dữ liệu nhạy cảm hoặc chạy tại region nhất định.

## 2. Policy as code là gì?

Policy as code chuyển quy tắc quản trị thành policy có thể kiểm tra bằng máy. Policy có thể được viết bằng ngôn ngữ chuyên dụng của cloud provider, policy engine tổng quát, rule trong CI/CD hoặc cấu hình có schema và validator.

Một policy thường mô tả:

- **Subject/principal:** ai hoặc workload nào đang thực hiện hành động?
- **Action:** tạo, sửa, xóa, đọc, deploy hay truy cập tài nguyên nào?
- **Resource:** loại tài nguyên, project/account, namespace hoặc phạm vi cụ thể.
- **Condition:** region, label, encryption, network exposure, image source, environment hoặc thuộc tính khác.
- **Effect:** allow, deny, warn, require approval hoặc tạo finding.
- **Exception:** ai có quyền phê duyệt ngoại lệ, lý do, thời hạn và compensating control.

Policy as code có thể được thực thi ở nhiều thời điểm:

1. **Design time:** kiểm tra kiến trúc/IaC trước khi triển khai.
2. **Build/CI:** kiểm tra source, manifest, container image và Terraform plan.
3. **Deployment time:** admission controller hoặc cloud policy ngăn cấu hình vi phạm.
4. **Runtime:** phát hiện hoặc chặn hành động truy cập không hợp lệ.
5. **Continuous assessment:** quét định kỳ để phát hiện drift và tài nguyên tồn tại ngoài policy.

Không có một policy engine duy nhất phù hợp mọi lớp. Có thể kết hợp native organization policy của cloud, IAM policy, admission policy cho Kubernetes, IaC scanner và engine tổng quát như Open Policy Agent (OPA). Mỗi cơ chế cần có owner và nguồn sự thật rõ ràng.

## 3. Phân biệt governance, policy, standard và guardrail

Các khái niệm liên quan nhưng không đồng nghĩa:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Governance | Cơ cấu quyết định, trách nhiệm và giám sát | Hội đồng kiến trúc phê duyệt chuẩn region |
| Policy | Quy tắc bắt buộc hoặc điều kiện được chấp nhận | Production database phải mã hóa at rest |
| Standard | Cách triển khai được khuyến nghị/chuẩn hóa | Dùng module database đã được tổ chức duyệt |
| Guardrail | Cơ chế kỹ thuật giữ hoạt động trong ranh giới policy | Từ chối tạo database không mã hóa |
| Control | Kiểm soát cụ thể nhằm giảm rủi ro | Audit log được bật và gửi tới log account |
| Evidence | Bằng chứng cho thấy control được thiết kế/vận hành | Kết quả policy evaluation, log cấu hình, ticket ngoại lệ |

Policy diễn đạt điều tổ chức yêu cầu; guardrail triển khai yêu cầu đó; evidence giúp chứng minh kết quả. Một tài liệu policy chưa phải guardrail, và một guardrail chưa chắc đủ bằng chứng tuân thủ nếu không ghi nhận ai, lúc nào và tài nguyên nào đã được đánh giá.

## 4. Cấu trúc guardrail ở cấp tổ chức

Tổ chức thường có nhiều cấp quản trị: organization, folder/organizational unit, account/project/subscription, workload và resource. Guardrail nên được áp dụng từ cấp rộng rồi tinh chỉnh theo nhu cầu hợp lệ của từng nhóm.

~~~mermaid
flowchart TD
    O["Organization policies<br/>Nguyên tắc bắt buộc"]
    O --> OU1["OU: Production"]
    O --> OU2["OU: Non-production"]
    O --> OU3["OU: Restricted data"]
    OU1 --> A1["Account / Project A"]
    OU1 --> A2["Account / Project B"]
    OU2 --> A3["Account / Project C"]
    OU3 --> A4["Account / Project D"]
    A1 --> W1["Workload resources"]
    A2 --> W2["Workload resources"]
    A3 --> W3["Workload resources"]
    A4 --> W4["Workload resources"]
~~~

Đây là mô hình khái niệm; tên và khả năng kế thừa khác nhau giữa cloud provider. Một số nền tảng có organization policy, management group, folder, OU hoặc project hierarchy. Policy ở cấp cha có thể được kế thừa, áp dụng như deny boundary hoặc kết hợp theo semantics riêng.

### 4.1. Phân lớp policy

| Cấp | Trách nhiệm điển hình | Ví dụ guardrail |
| --- | --- | --- |
| Organization | Quy tắc nền tảng không được bỏ qua tùy tiện | Chỉ dùng account thuộc organization; bật audit cơ bản |
| OU/business unit | Điều chỉnh theo loại dữ liệu hoặc mô hình vận hành | Region được phép, yêu cầu network boundary |
| Environment | Phân biệt dev/test/staging/prod | Production không cho public database |
| Workload/project | Quy tắc theo ứng dụng hoặc domain | Chỉ deploy image từ registry được duyệt |
| Resource | Cấu hình chi tiết | Encryption, label, access policy, backup |

### 4.2. Inheritance và conflict resolution

Phải hiểu rõ cách policy cha/con kết hợp:

- Policy deny ở cấp cha có bị policy con override được không?
- Allow policy ở nhiều cấp được hợp nhất hay phải thỏa tất cả?
- Có explicit deny/mandatory control không?
- Policy exception có kế thừa xuống resource hay chỉ một scope?
- Khi một resource được di chuyển sang OU khác, policy nào có hiệu lực?

Đừng mặc định “policy con ghi đè policy cha”. Hành vi này phụ thuộc engine/provider. Hãy kiểm tra tài liệu chính thức, viết test cho policy hierarchy và có công cụ hiển thị effective policy tại resource.

## 5. Preventive, detective và corrective guardrail

Guardrail có thể ngăn sai lệch trước khi tạo, phát hiện sau khi xảy ra hoặc tự sửa có kiểm soát.

| Loại | Thời điểm | Ví dụ | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| Preventive | Trước hoặc trong thao tác | Deny public bucket; chỉ cho region được duyệt | Có thể chặn deploy hợp lệ nếu policy sai |
| Detective | Sau khi cấu hình/thay đổi | Quét tài nguyên không mã hóa, phát hiện public IP | Có khoảng thời gian từ lúc vi phạm tới lúc phát hiện |
| Corrective | Sau khi phát hiện | Tự bật encryption hoặc thu hồi public access | Có thể gây gián đoạn hoặc thay đổi ngoài ý muốn |
| Compensating | Khi chưa thể đáp ứng control gốc | Network isolation bổ sung khi migration chưa hỗ trợ encryption mới | Cần owner, lý do và thời hạn |

Một control quan trọng thường cần hơn một lớp: preventive policy ngăn cấu hình mới, detective scanner phát hiện drift, corrective workflow xử lý vi phạm và audit log giữ bằng chứng.

### 5.1. Chọn mức thực thi

Policy có thể hoạt động ở các mode:

- **Audit/monitor:** chỉ ghi finding, không chặn.
- **Warn:** thông báo developer trong pipeline hoặc portal.
- **Deny:** từ chối thao tác vi phạm.
- **Require approval:** đưa vào quy trình phê duyệt ngoại lệ.
- **Remediate:** tự sửa khi hành động có thể lặp an toàn và đã được phê duyệt.

Khi triển khai policy mới, có thể bắt đầu audit để đo false positive, phân loại workload và hoàn thiện exception. Sau khi kiểm thử, chuyển sang deny theo đợt. Với control bảo vệ dữ liệu nhạy cảm hoặc nguy cơ nghiêm trọng, tổ chức có thể yêu cầu preventive ngay từ đầu và cung cấp quy trình exception khẩn cấp.

## 6. Policy as code trong Infrastructure as Code

Infrastructure as Code (IaC) mô tả hạ tầng mong muốn; policy as code kiểm tra IaC có đáp ứng tiêu chuẩn tổ chức hay không. Hai thứ bổ sung cho nhau.

~~~mermaid
flowchart LR
    DEV["Developer change"]
    SRC["Source / IaC"]
    PLAN["Plan / Manifest"]
    POLICY["Policy evaluation"]
    APPROVE["Review / approval"]
    DEPLOY["Deploy"]
    RUNTIME["Runtime guardrail"]
    DRIFT["Continuous drift scan"]
    DEV --> SRC --> PLAN --> POLICY
    POLICY -->|"Pass"| APPROVE --> DEPLOY --> RUNTIME
    POLICY -->|"Fail"| DEV
    RUNTIME --> DRIFT
    DRIFT -->|"Finding / remediation"| DEV
~~~

### 6.1. Kiểm tra trước deploy

Một pipeline có thể thực hiện:

1. Format và validate syntax IaC.
2. Kiểm tra module/version và nguồn provider.
3. Sinh execution plan hoặc manifest.
4. Chạy security/misconfiguration scanner.
5. Đánh giá policy organization.
6. Kiểm tra quyền, region, encryption, network exposure và tagging.
7. Hiển thị finding với resource address và lý do.
8. Yêu cầu review/approval nếu thay đổi nhạy cảm.
9. Deploy theo quyền tối thiểu.
10. Lưu policy result và deployment evidence.

Policy nên đánh giá plan/manifest đã render, không chỉ dò chuỗi source code. Một thuộc tính có thể được đặt qua module, variable, default hoặc data source; kiểm tra source đơn thuần dễ bỏ sót giá trị cuối.

### 6.2. Ví dụ rule khái niệm

Điều kiện: database production phải có encryption at rest, không public, có backup và tag owner.

~~~rego
package cloud.guardrails

deny[msg] {
  input.environment == "production"
  input.resource_type == "database"
  not input.encryption_at_rest
  msg := "Production database must enable encryption at rest"
}

deny[msg] {
  input.environment == "production"
  input.resource_type == "database"
  input.public_access
  msg := "Production database must not allow public access"
}
~~~

Đây là ví dụ OPA/Rego rút gọn với input giả định. Schema input, cách xác định production, ý nghĩa public_access và nguồn giá trị encryption phải được chuẩn hóa trong tổ chức. Không sao chép rule vào production mà chưa test với dữ liệu plan thực tế và các trường hợp hợp lệ.

## 7. Các nhóm policy quan trọng trong cloud

### 7.1. Identity và quyền

- Workload chỉ dùng identity được quản lý; hạn chế static credential.
- Production deployment role phải tách khỏi development role.
- Quyền cấp theo least privilege và có owner.
- Không cho workload tự sửa IAM policy hoặc trust relationship của chính nó.
- Hành động đặc quyền cần audit và approval phù hợp.

### 7.2. Network và exposure

- Production database/cache không được public trừ ngoại lệ đã phê duyệt.
- Ingress/egress phải có chủ đích và owner.
- Dùng private endpoint/network path theo phân loại dữ liệu.
- Chỉ cho phép protocol/port cần thiết.
- Security group/firewall rule quá rộng phải bị phát hiện.

### 7.3. Data protection

- Encryption at rest và in transit.
- Backup, retention, immutable protection theo phân loại.
- Data location/region theo yêu cầu pháp lý và hợp đồng.
- Không lưu dữ liệu nhạy cảm trong tag, resource name hoặc log.
- Public access và cross-account sharing cần kiểm soát.

### 7.4. Logging và monitoring

- Audit log phải được bật ở account/project thuộc phạm vi.
- Log quan trọng phải gửi tới nơi lưu trữ độc lập với workload.
- Không cho workload thông thường xóa hoặc sửa audit evidence.
- Có retention, access control và cảnh báo khi logging ngừng hoạt động.
- Metric/alert phục vụ SLO phải có owner.

### 7.5. Reliability và recovery

- Production stateful resource phải có backup phù hợp.
- Database critical phải có HA/replication theo tier.
- Có health check, alert và runbook.
- DR region/capacity được kiểm tra khi cần.
- Không cho tạo resource không có owner hoặc không có kế hoạch lifecycle.

### 7.6. Cost và resource hygiene

- Bắt buộc tag owner, application, environment, cost center và data classification.
- Giới hạn instance family/region hoặc service được phép khi có lý do.
- Phát hiện unattached disk, idle load balancer, snapshot quá hạn và resource không gắn owner.
- Budget/quota alert cho project và tenant.
- Yêu cầu expiration/cleanup cho môi trường tạm thời.

## 8. Policy theo phân loại dữ liệu và môi trường

Một policy toàn cục quá đơn giản có thể không phản ánh rủi ro khác nhau. Nên phân loại workload/data trước:

| Phân loại | Ví dụ | Guardrail có thể áp dụng |
| --- | --- | --- |
| Public | Website asset công khai | CDN, integrity/versioning, bảo vệ origin |
| Internal | Metadata vận hành | IAM nội bộ, logging và retention |
| Confidential | Booking/customer records | Encryption, private network, least privilege, audit |
| Restricted | Payment/identity secrets hoặc dữ liệu chịu ràng buộc cao | Isolated account/OU, access approval, key policy, stronger monitoring |

Tên mức phân loại chỉ là ví dụ; phải khớp taxonomy chính thức của tổ chức. Không đưa dữ liệu vào cấp nhạy cảm thấp hơn để tránh policy.

### 8.1. Policy theo môi trường

Development có thể linh hoạt hơn production, nhưng không nên trở thành nơi chứa dữ liệu thật không kiểm soát. Policy dev có thể cho phép instance nhỏ và dữ liệu synthetic; production yêu cầu backup, private networking, approved image, logging và change review. Staging cần dữ liệu đã được ẩn danh hoặc dữ liệu giả nếu không có phê duyệt khác.

## 9. Exception management: ngoại lệ phải có vòng đời

Không phải mọi policy đều có thể áp dụng ngay cho hệ thống legacy hoặc tình huống khẩn cấp. Một cơ chế exception tốt cho phép ngoại lệ có kiểm soát, có người chịu trách nhiệm và tự hết hạn.

Một bản ghi exception nên có:

- Policy/rule bị ngoại lệ và resource/scope chính xác.
- Lý do nghiệp vụ, rủi ro đã đánh giá và tác động nếu không duyệt.
- Owner chịu trách nhiệm và người phê duyệt độc lập.
- Compensating control hoặc biện pháp giảm thiểu.
- Ngày bắt đầu, ngày hết hạn và ngày review.
- Kế hoạch remediation, milestone và bằng chứng hoàn tất.
- Audit trail cho việc tạo, sửa, gia hạn và đóng exception.

~~~yaml
exception:
  id: EX-2026-0142
  policy: production-db-private-only
  scope: project-legacy-migration
  owner: data-platform
  reason: temporary migration dependency
  compensatingControls:
    - restricted-source-network
    - enhanced-access-logging
  expiresAt: "2026-12-15T00:00:00Z"
  remediationTicket: ARCH-4821
~~~

Ví dụ chỉ minh họa cấu trúc. Exception hết hạn cần tự động chuyển finding/escalation hoặc chặn tiếp tục triển khai theo policy. Không được tạo exception vĩnh viễn bằng cách gia hạn lặp lại mà không review rủi ro và phê duyệt cấp phù hợp.

### 9.1. Break-glass

Break-glass là quyền truy cập đặc biệt trong tình huống khẩn cấp khi quy trình thông thường không đáp ứng. Cần tách credential, kiểm soát người phê duyệt, thời hạn ngắn, logging đầy đủ và hậu kiểm bắt buộc. Không biến break-glass thành tài khoản admin dùng hằng ngày.

## 10. Continuous compliance và drift detection

Một resource có thể hợp lệ khi deploy nhưng lệch policy sau đó do thao tác console, script ngoài pipeline, thay đổi provider hoặc drift trong state. Vì thế policy as code cần đánh giá liên tục.

~~~mermaid
flowchart TD
    DESIRED["Desired state: IaC / policy"]
    ACTUAL["Actual cloud resources"]
    SCAN["Inventory + policy evaluator"]
    FIND["Findings / drift"]
    TRIAGE["Owner / severity / due date"]
    FIX["Remediation workflow"]
    VERIFY["Re-evaluate + evidence"]
    DESIRED --> SCAN
    ACTUAL --> SCAN
    SCAN --> FIND --> TRIAGE --> FIX --> VERIFY
~~~

### 10.1. Drift không phải lúc nào cũng là vi phạm

Có thể có drift do:

- Thay đổi được phê duyệt nhưng IaC chưa cập nhật.
- Emergency fix đã thực hiện qua console.
- Resource do dịch vụ quản lý tự thay đổi.
- State file không phản ánh thực tế.
- Policy thay đổi khiến resource cũ không còn đạt chuẩn.

Phải phân loại nguyên nhân trước khi tự động revert. Auto-remediation nhầm có thể xóa dữ liệu, cắt network hoặc phá một dịch vụ đang hoạt động.

### 10.2. Quy trình remediation

1. Thu thập resource, policy version, finding và bằng chứng.
2. Xác định mức độ nghiêm trọng và khả năng khai thác.
3. Gán owner và deadline.
4. Chọn tự động sửa, tạo pull request IaC, hoặc xử lý thủ công.
5. Đánh giá blast radius và kế hoạch rollback.
6. Xác minh sau remediation.
7. Lưu evidence và đóng finding.

## 11. Policy engine và lựa chọn công nghệ

| Cơ chế | Điểm mạnh | Cần cân nhắc |
| --- | --- | --- |
| Native organization policy | Tích hợp control plane, dễ áp phạm vi account/project | Phạm vi rule/condition phụ thuộc provider |
| IAM/resource policy | Kiểm soát principal/action/resource | Cần quản trị policy sprawl và kiểm thử quyền hiệu lực |
| OPA/Rego | Policy engine tổng quát, phù hợp CI/admission/custom input | Cần xây input schema, deployment, test và vận hành |
| Kubernetes admission policy | Chặn manifest không đạt chuẩn khi tạo resource | Không thay thế cloud account policy hoặc runtime monitoring |
| IaC scanner/plan policy | Phát hiện cấu hình sai trước deploy | Cần xét plan render và runtime drift |
| CSPM/configuration management | Quét posture liên tục trên cloud resource | Có thể có false positive, coverage/licensing khác nhau |

Không nên chọn công cụ chỉ theo số rule hoặc bảng điều khiển đẹp. Đánh giá:

- Có thể áp dụng ở mọi account/project/region cần thiết không?
- Policy có thể test, version, review và rollback không?
- Effective policy và source của finding có giải thích được không?
- Có hỗ trợ exception có thời hạn không?
- Có tích hợp audit, ticketing và evidence export không?
- Chi phí vận hành, latency và ảnh hưởng deployment là bao nhiêu?
- Khi policy engine không khả dụng, hệ thống fail-open hay fail-closed?

## 12. Test policy như phần mềm

Policy cũng có bug: rule có thể quá rộng, quá hẹp, logic sai hoặc không bao phủ biến thể input. Cần áp dụng quy trình phát triển phần mềm:

1. Unit test cho từng rule.
2. Positive test cho cấu hình hợp lệ.
3. Negative test cho cấu hình vi phạm.
4. Boundary test cho giá trị thiếu, null, wildcard, inherited value và type khác.
5. Regression test cho finding từng xuất hiện.
6. Integration test với plan/manifest thật.
7. Test hierarchy và exception.
8. Canary rollout và rollback.

Ví dụ test matrix:

| Tình huống | Kỳ vọng |
| --- | --- |
| Production DB có encryption, private access, backup, owner | Pass |
| Production DB public | Deny |
| Dev DB thiếu backup nhưng policy dev cho phép | Pass hoặc warning theo policy dev |
| Production resource thiếu owner tag | Deny hoặc remediation theo control |
| Exception còn hiệu lực và có approval | Pass trong đúng scope, có finding theo dõi |
| Exception hết hạn | Fail/escalate |
| Resource ở region ngoài allowlist | Deny |
| Policy input thiếu environment | Fail safe hoặc yêu cầu bổ sung metadata |

### 12.1. Policy rollout

Không triển khai hàng trăm rule mới trên toàn organization cùng lúc nếu chưa biết tác động. Một cách rollout:

- Chạy report-only/audit và thu baseline.
- Nhóm findings theo policy, team và loại resource.
- Sửa false positive hoặc data contract.
- Thông báo owner và thời hạn xử lý.
- Áp dụng deny ở sandbox/non-production trước.
- Mở rộng theo OU/account canary.
- Có kill switch/rollback có kiểm soát và audit.
- Chuyển sang enforcement toàn phạm vi sau khi đánh giá.

Với policy bảo vệ dữ liệu hoặc rủi ro nghiêm trọng, cần xác định rõ phần nào không được phép ở report-only.

## 13. Governance workflow và trách nhiệm

Policy as code không loại bỏ vai trò quản trị. Nó làm quyết định dễ kiểm tra và thực thi hơn.

| Vai trò | Trách nhiệm |
| --- | --- |
| Business/compliance owner | Xác định nghĩa vụ, phạm vi dữ liệu và mức chấp nhận rủi ro |
| Security architecture | Chuyển yêu cầu thành control và threat model |
| Cloud platform team | Triển khai organization policy, landing zone và guardrail |
| Workload owner | Sử dụng module chuẩn, sửa finding và đề xuất exception |
| Policy owner | Quản lý rule, test, release, version và deprecation |
| Auditor/risk team | Kiểm tra evidence và hiệu lực control độc lập |
| Incident commander | Điều phối break-glass và xử lý sự cố |

Mỗi policy có owner kỹ thuật và owner nghiệp vụ. Policy không rõ chủ sở hữu sẽ sớm lỗi thời hoặc bị vô hiệu hóa để unblock deployment.

## 14. Evidence, audit và chứng minh tuân thủ

Để audit được, cần lưu:

- Policy source, version/commit, người review và thời điểm phê duyệt.
- Policy engine/runtime version và cấu hình evaluator.
- Scope tài nguyên được đánh giá, thời điểm scan và coverage.
- Kết quả pass/deny/finding, mức độ và resource identifier.
- Exception, approval, expiry và compensating control.
- Remediation ticket, thay đổi IaC và kết quả re-evaluation.
- Audit log cho thay đổi guardrail và quyền quản trị.

Evidence cần bảo vệ khỏi sửa/xóa trái phép, có retention, access control và khả năng truy xuất theo thời gian. Nếu chỉ giữ dashboard trạng thái hiện tại, tổ chức có thể không chứng minh được control đã hoạt động tại thời điểm audit.

## 15. Tránh policy sprawl và guardrail gây cản trở

Khi mỗi team viết policy riêng, có thể xuất hiện rule trùng lặp, mâu thuẫn và khó giải thích. Khi một policy chung quá cứng, developer có thể tìm đường vòng bằng account ngoài tổ chức hoặc thao tác thủ công.

Nguyên tắc quản trị:

- Tái sử dụng policy module và naming convention.
- Phân biệt mandatory guardrail với recommendation.
- Có tài liệu giải thích lý do và cách khắc phục finding.
- Cung cấp self-service portal để xem effective policy và xin exception.
- Đo false positive, thời gian xử lý finding và deployment friction.
- Version policy và công bố breaking change.
- Dọn rule lỗi thời; không giữ rule chỉ vì không ai dám xóa.
- Không cho workload tự disable guardrail hoặc sửa policy cấp cao.

## 16. Ví dụ kiến trúc guardrail ở cấp tổ chức

Một mô hình cho công ty đặt chỗ:

~~~text
Organization
  Mandatory:
    - central audit logging enabled
    - approved regions only
    - identity federation for workload access
    - prevent public exposure of restricted data
    - required owner/environment/classification tags

  Production OU:
    - approved runtime images
    - private database/cache
    - encryption and backup controls
    - deployment through protected pipeline

  Non-production OU:
    - synthetic or masked data only
    - lower-cost instance families
    - temporary resource expiry tags

  Restricted-data OU:
    - dedicated encryption key policy
    - narrow network path
    - privileged access approval
    - extended audit evidence retention
~~~

Đây là cấu trúc minh họa. Cần chuyển từng mục thành policy thực thi tương ứng nền tảng và xác định control nào preventive, detective hoặc procedural.

## 17. Bài thực hành: xây dựng policy as code cho landing zone

**Bối cảnh giả định:** tổ chức có 80 cloud projects, bốn business unit và ba environment. Mỗi team triển khai bằng Terraform và Kubernetes. Audit gần đây phát hiện database public, thiếu owner tag, log không được gửi tập trung và một số CI runner dùng access key dài hạn.

### Nhiệm vụ

1. Xác định governance owner, policy owner, workload owner và auditor.
2. Phân loại policy thành identity, network, data protection, logging, reliability, region và cost.
3. Thiết kế hierarchy organization/OU/project/environment và mô tả inheritance/conflict.
4. Viết tối thiểu sáu policy rule có input/output rõ ràng.
5. Phân loại mỗi rule là preventive, detective, corrective hoặc compensating.
6. Xây CI pipeline kiểm tra IaC plan và Kubernetes manifest trước deploy.
7. Thiết kế continuous compliance scan để phát hiện drift sau deploy.
8. Xây exception record có owner, approval, expiry, compensating control và remediation ticket.
9. Thiết kế policy test matrix, report-only rollout, canary và rollback.
10. Xác định evidence cần lưu để audit có thể tái tạo trạng thái tại thời điểm kiểm tra.
11. Mô phỏng policy engine outage và quyết định fail-open/fail-closed theo loại control.
12. Viết ADR mô tả trade-off giữa enforcement mạnh, developer autonomy, reliability và cost.

### Mẫu policy catalog

| Policy ID | Phạm vi | Control | Mode | Owner | Evidence |
| --- | --- | --- | --- | --- | --- |
| GOV-IDENTITY-01 | Organization | Workload dùng federation/managed identity | Deny | IAM Platform | Identity inventory |
| GOV-NET-02 | Production | Database không public | Deny | Network Security | Effective policy + scan |
| GOV-DATA-03 | Restricted data | Encryption và approved region | Deny | Data Governance | Config + key audit |
| GOV-LOG-04 | All production | Central audit log | Preventive + detective | SecOps | Log delivery status |
| GOV-COST-05 | All projects | Owner/cost-center tags | Warn rồi deny | FinOps | Inventory report |
| GOV-EXC-06 | Exception scope | Ngoại lệ có hạn dùng | Approval | Risk Owner | Exception register |

### Tiêu chí hoàn thành

- Policy có owner, phạm vi, input, effect và lý do.
- Hierarchy và semantics kế thừa đã được kiểm chứng bằng test.
- CI kiểm tra cấu hình render/plan thay vì chỉ tìm chuỗi source.
- Runtime/continuous scan phát hiện drift ngoài pipeline.
- Exception có thời hạn, audit và remediation.
- Rollout có report-only/canary/rollback phù hợp rủi ro.
- Evidence đủ để chứng minh coverage, trạng thái và remediation tại thời điểm audit.
- Developer hiểu cách sửa finding và xin ngoại lệ theo quy trình.

## 18. Checklist Well-Architected trước khi đưa policy as code vào production

- [ ] Policy được liên kết với rủi ro, nghĩa vụ hoặc tiêu chuẩn cụ thể.
- [ ] Có owner nghiệp vụ, owner kỹ thuật và phạm vi áp dụng rõ.
- [ ] Organization hierarchy và inheritance/conflict semantics được xác minh.
- [ ] Mandatory guardrail, recommendation và exception được phân biệt.
- [ ] Có preventive, detective và corrective control theo mức rủi ro.
- [ ] Policy đánh giá IaC plan/manifest đã render và cấu hình runtime.
- [ ] IAM, network, data, logging, reliability, region và cost được bao phủ.
- [ ] Rule có positive, negative, boundary, regression và integration test.
- [ ] Policy release có version, review, canary và rollback.
- [ ] Exception có owner, lý do, approval, expiry, compensating control và remediation.
- [ ] Continuous compliance phát hiện drift ngoài pipeline.
- [ ] Auto-remediation có giới hạn blast radius, idempotency và rollback.
- [ ] Fail-open/fail-closed khi policy engine lỗi được quyết định theo loại control.
- [ ] Evidence có timestamp, scope, policy version, kết quả, access control và retention.
- [ ] Developer có self-service để xem effective policy và xử lý finding.
- [ ] Policy sprawl, false positive và deployment friction được đo và review.
- [ ] Guardrail không cho workload tự vô hiệu hóa hoặc nâng quyền policy.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** policy as code biến yêu cầu quản trị thành quy tắc có thể kiểm tra và thực thi; guardrail giữ workload trong ranh giới an toàn xuyên các account, project và môi trường. Để mô hình bền vững, tổ chức cần hierarchy rõ, policy được test như phần mềm, ngoại lệ có thời hạn, continuous drift detection và evidence có thể kiểm chứng. Guardrail tốt vừa bảo vệ nền tảng vừa cho phép team triển khai tự chủ trong phạm vi đã được định nghĩa.
