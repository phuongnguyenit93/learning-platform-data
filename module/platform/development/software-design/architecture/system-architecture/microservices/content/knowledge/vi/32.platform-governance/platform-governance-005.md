# Chính sách tự động hóa thay cho xét duyệt thủ công mọi thay đổi

## 1. Mục tiêu bài học

Trong tổ chức phát triển microservices, số lượng thay đổi có thể tăng từ vài lần mỗi tuần lên hàng trăm hoặc hàng nghìn lần mỗi ngày: thay đổi source code, version container, cấu hình, feature flag, hạ tầng, quyền truy cập, database schema và các chính sách vận hành. Nếu **mọi thay đổi**, kể cả bản vá nhỏ đã có test và rollback, đều phải chờ một hội đồng hoặc người quản trị bấm “Approve”, quá trình phát hành trở thành hàng đợi phụ thuộc con người. Nhóm dễ hình thành các thói quen nguy hiểm: gộp nhiều thay đổi để giảm số lần xin duyệt, triển khai ngoài giờ để tránh tắc nghẽn, dùng quyền admin để đi đường tắt hoặc chỉ hoàn thành chứng từ sau khi deploy.

Tuy nhiên, bỏ toàn bộ kiểm soát thủ công cũng không phải giải pháp. Thay đổi liên quan tới dữ liệu nhạy cảm, chính sách IAM toàn tổ chức, giao dịch tài chính, migration không thể đảo ngược hoặc xóa tài nguyên quan trọng có thể cần xét duyệt có trách nhiệm và kế hoạch can thiệp.

Cách tiếp cận tốt hơn là **quản trị dựa trên chính sách được thực thi tự động (policy-as-code, automated guardrails)**, kết hợp kiểm tra trong CI/CD, bảo vệ ở hạ tầng, observability sau triển khai và phê duyệt theo rủi ro. Mục đích không phải giảm an toàn để tăng tốc, mà là làm cho những thay đổi đã biết cách kiểm chứng **được kiểm chứng nhất quán, nhanh và có bằng chứng**, đồng thời giữ sự chú ý của con người cho những quyết định thực sự cần phán đoán.

Sau bài học, bạn có thể:

1. Giải thích vì sao “phê duyệt tất cả” không đồng nghĩa với quản trị tốt.
2. Phân loại thay đổi theo phạm vi ảnh hưởng, độ đảo ngược, dữ liệu, quyền và bằng chứng kiểm thử.
3. Thiết kế đường phát hành chuẩn tự động và đường ngoại lệ cho thay đổi rủi ro cao.
4. Viết chính sách đơn giản dưới dạng code, kiểm trong pull request, pipeline và admission.
5. Gắn ownership, segregation of duties, least privilege và audit evidence vào quy trình.
6. Phân biệt kiểm soát prevent/detect/respond và guardrail tổ chức/runtime.
7. Dùng progressive delivery, health checks, SLO và rollback để giảm rủi ro thay đổi.
8. Thiết kế quy trình break-glass và exceptions có thời hạn, chủ sở hữu và kiểm toán.
9. Đo lead time, change failure rate, review bottleneck, policy violations và developer experience.
10. Lập lộ trình áp dụng mà không biến “tự động hóa” thành một bộ máy chặn thay đổi mới.

Ngữ cảnh xuyên suốt là một tổ chức triển khai nhiều Java/Spring Boot microservices trên container/Kubernetes hoặc một nền tảng được quản lý. Các ví dụ YAML, Rego, CEL, shell và policy DSL mang tính minh họa; cần điều chỉnh cho công cụ, phiên bản và quy định nội bộ.

## 2. Xét duyệt thủ công có những vai trò nào?

Một bước approve có thể đang thực hiện nhiều mục đích khác nhau:

- **Xác nhận nhu cầu:** thay đổi này có đúng ưu tiên sản phẩm không?
- **Review kỹ thuật:** code có đúng, an toàn, dễ bảo trì không?
- **Kiểm soát chất lượng:** tests, migrations, compatibility đã pass chưa?
- **Phân quyền:** ai được thay production và theo phạm vi nào?
- **Quản trị thay đổi:** có lịch, owner, blast radius, rollback và truyền thông không?
- **Compliance:** có bằng chứng thay đổi được ghi nhận và người chịu trách nhiệm không?
- **Điều phối:** nhiều service/release có gây xung đột tài nguyên hoặc schema không?
- **Phê duyệt rủi ro:** tổ chức có chấp nhận một quyết định khó đảo ngược không?

Không nên thay tất cả mục đích trên bằng một nút “green pipeline”. Nhưng cũng không nhất thiết cần con người xem **từng lần chạy** nếu cùng một bộ tiêu chí đã được phê duyệt, công cụ thực thi và lưu bằng chứng đúng.

Ví dụ: nhóm Security có thể phê duyệt **chính sách** rằng “image phải được scan, có provenance, không chạy root và chỉ được lấy từ registry cho phép”. Mỗi deployment thỏa chính sách này có thể đi qua tự động. Nhóm Security không cần bấm approve mỗi ngày chỉ để xác nhận lại các điều kiện máy đã kiểm được.

## 3. Quản trị theo policy, không theo thói quen xin phép

### 3.1. Quy tắc và bằng chứng

Một kiểm soát tốt có năm phần:

1. **Mục đích:** rủi ro nào cần ngăn, ví dụ public database hoặc container đặc quyền.
2. **Quy tắc có thể kiểm:** điều kiện rõ, có thể đánh giá pass/fail và phiên bản.
3. **Điểm thực thi:** PR, pipeline, admission, cloud policy hoặc runtime monitor.
4. **Bằng chứng:** artifact/commit, test report, quyết định policy, identity và timestamp.
5. **Hành động khi vi phạm:** block, cảnh báo, ngoại lệ có hạn, rollback, incident.

Nếu policy chỉ ghi “triển khai an toàn” thì khó tự động hóa. Một chính sách có thể kiểm là: “Mọi workload production phải khai báo resource requests/limits phù hợp lớp workload, không bật privileged container, chỉ dùng registry tin cậy, có owner và incident contact”.

### 3.2. Chính sách phải đúng với risk model

Không phải mọi quy tắc có thể kiểm đều đáng block. Ví dụ đặt liveness threshold chung cho tất cả container có thể khiến một Java service startup chậm liên tục restart. Policy cần phân biệt critical services, batch jobs, GPU workloads hoặc legacy exceptions; không đặt một ngưỡng tùy tiện rồi gây outage trên toàn tổ chức.

### 3.3. Cân bằng

- **Mặc định an toàn:** golden paths, secure templates, restricted permissions.
- **Tự động ở rủi ro thấp:** build/test/scan/deploy với audit trail.
- **Can thiệp con người ở quyết định không tự động đánh giá được:** thay đổi pháp lý, dữ liệu, chính sách quyền, chuyển đổi tiền tệ hoặc migration không hồi phục.
- **Phát hiện sau thay đổi:** SLO alerts, anomaly detection, drift và compliance scan.
- **Khả năng xử lý ngoại lệ:** khi guardrail sai hoặc yêu cầu đặc biệt, có owner, expiry và review.

## 4. Tại sao “approve mọi thay đổi” có thể phản tác dụng?

Giả sử 20 teams mỗi team triển khai 8 lần/tuần. Một nhóm phê duyệt trung tâm phải xem 160 requests/tuần. Nếu mỗi request mất 10 phút, riêng thời gian đọc đã gần 27 giờ, chưa tính context switching, follow-ups và sự cố. Khi volume tăng, hai vấn đề xuất hiện:

- **Queueing delay:** thời gian từ code hoàn tất đến deploy phụ thuộc lịch người duyệt.
- **Review fatigue:** reviewer thấy quá nhiều thay đổi quen thuộc, dễ bấm approve theo thói quen mà không thực sự giảm rủi ro.

Các hành vi phát sinh:

1. Gộp 20 commits thành một release lớn để xin duyệt một lần, tăng blast radius và khó rollback.
2. Dồn deployment vào một cửa sổ cố định, làm nhiều teams thay production cùng lúc.
3. Tạo ngoại lệ tạm nhưng không hết hạn, trở thành bypass lâu dài.
4. Đánh giá bằng việc “có approval record” thay vì kiểm outcome.
5. Giữ kiến thức ở một số cá nhân, khiến vắng mặt là blocker.
6. Cho phép admin override để xử lý nhanh, làm suy yếu separation of duties.

Giải pháp không chỉ là loại approval mà là **chuẩn hóa những điều có thể xét tự động**, khiến mỗi lần deploy nhỏ, dễ theo dõi và dễ đảo ngược hơn.

## 5. Phân loại thay đổi theo mức rủi ro

Một ma trận ban đầu:

| Nhóm | Ví dụ | Điều kiện thông thường | Hành động |
|---|---|---|---|
| **Standard / low-risk** | Bug fix trong service, config đã được giới hạn | Tests pass, scan pass, scope nhỏ, rollback rõ | Tự động hóa qua pipeline |
| **Moderate** | Thay logic quan trọng, tăng traffic, thay feature flag | Contract tests, canary, SLO gate, owner | Tự động + giám sát/canary theo policy |
| **High-risk** | Database migration có thể mất dữ liệu, public exposure, IAM rộng | Impact analysis, backup, owner/security review | Cần approval có trách nhiệm |
| **Critical/exceptional** | Xóa production data, đổi payment settlement, disaster cutover | Kế hoạch khôi phục, người phê duyệt có quyền, thời gian | Multi-party approval, change window hoặc break-glass |
| **Emergency** | Khắc phục outage và rủi ro khẩn | Incident ID, quyền tạm, audit | Luồng khẩn có kiểm soát và review hậu kỳ |

Một “standard change” nên được **phê duyệt trước theo loại**, không phải xem xét lại từng instance nếu cùng điều kiện. Khi một thay đổi không còn thỏa điều kiện (quy mô data migration lớn, nhiều regions, quyền mới, không có rollback), pipeline phải chuyển luồng hoặc block.

### 5.1. Các chiều rủi ro

- **Blast radius:** một instance, một service, một region hay toàn tổ chức?
- **Business criticality:** ảnh hưởng checkout, payment, identity hay tác vụ nền ít quan trọng?
- **Reversibility:** rollback code đơn giản, hay thay dữ liệu khó đảo ngược?
- **Data sensitivity:** có PII, financial records, audit logs hoặc keys không?
- **Permission expansion:** có thêm quyền, thay trust boundary, public exposure?
- **Novelty:** đã từng triển khai theo mẫu này chưa; có test coverage đúng loại?
- **Dependency impact:** schema, API/event contracts, shared database, shared ingress?
- **Deployment mode:** full fleet hay canary, có kill switch và auto rollback?
- **Change window:** giờ cao điểm, sự kiện khuyến mãi, disaster mode?
- **Evidence quality:** tests, policy evaluation, provenance, baseline metrics đủ tin cậy?

Có thể tạo risk score để hỗ trợ routing, nhưng **không biến một số điểm giả định thành quyết định tối hậu**. Một thay đổi tạo public access tới database có thể phải block dù tổng điểm thấp.

## 6. Sơ đồ luồng quyết định

~~~mermaid
flowchart TD
    A[Change submitted] --> B[Identify owner, scope, type]
    B --> C[Automated tests and policy evaluation]
    C --> D{Mandatory policy passes?}
    D -->|No| E[Block or request bounded exception]
    D -->|Yes| F{High impact / irreversible?}
    F -->|Yes| G[Risk owner reviews plan and evidence]
    F -->|No| H[Standard path - automated promotion]
    G --> I{Approved for this scope?}
    I -->|No| E
    I -->|Yes| J[Controlled rollout / canary]
    H --> J
    J --> K[Monitor SLO, correctness, security]
    K --> L{Within guardrails?}
    L -->|No| M[Stop, rollback or incident response]
    L -->|Yes| N[Record deployment and evidence]
~~~

Không thể dùng chart này thay state machine thực. Trong tổ chức thật, có thể có nhiều policy cùng áp dụng và exceptions độc lập; tất cả phải được liên kết với một change ID hoặc release record.

## 7. Mô hình kiểm soát nhiều tầng

Một pipeline chỉ scan code chưa đủ để bảo vệ một resource được tạo thủ công qua cloud console. Cần các điểm kiểm soát bổ trợ:

| Tầng | Kiểm soát | Ví dụ |
|---|---|---|
| **Developer experience** | Golden path/templates, IDE, local lint | Service template có auth/tracing/secrets |
| **Source control** | Branch protection, CODEOWNERS, review | Những file quyền/CI cần reviewer chuyên môn |
| **CI** | Tests, SAST/SCA, IaC policy, secret scan | Chặn hardcoded keys, public buckets |
| **Build** | SBOM, signed provenance, immutable artifacts | Chỉ deploy image từ trusted pipeline |
| **CD** | Environment policy, change class, progressive rollout | Canary trước full rollout |
| **Admission** | Guardrails ở cluster/cloud | Cấm privileged containers trong production |
| **Runtime** | Drift detection, audit, security monitoring | Cảnh báo resource không theo Git state |
| **Post-deploy** | SLO/error budget, anomaly detection, business checks | Rollback khi checkout failures tăng |
| **Governance** | Exception registry, owners, periodic review | Temporary waiver có expiry |

Đây là thiết kế **defense in depth**. Nếu một rule trong CI bị bypass do credential lộ hoặc pipeline bug, admission/runtime có thể vẫn chặn một phần tác động.

## 8. “Paved road”: làm đường an toàn thành đường dễ nhất

Một chính sách tốt không chỉ nêu “cấm”. Nó cung cấp cách làm đúng:

- Repository template cho Java/Spring Boot có health probes và structured logs.
- Base image, dependency versions và security defaults được duy trì.
- Build pipeline chuẩn có tests, SCA, scan image và publish immutable digest.
- Artifact registry đã được phép dùng.
- Deployment template với resource budgets, non-root, owner, telemetry và secret references.
- Workload identity theo service, không dùng tài khoản cloud chung.
- Managed database/queue theo mẫu có backup, encryption và network isolation.
- Canary/rollback action được đặt ngay trong pipeline.
- Documentation và runbook từ service template.

Khi developer chọn golden path, phần lớn guardrails được đáp ứng ngay từ đầu. Nếu muốn một thứ khác (GPU job, multi-region, long-running worker), platform cung cấp đường mở rộng hoặc exception thay vì buộc đội phải lách policy.

### 8.1. Golden path không đồng nghĩa cưỡng ép tất cả workload

Một batch Job có lifecycle khác API lâu dài, liveness probe/rolling deployment có thể không áp dụng. Một GPU workload cần scheduling và resource profile riêng. Policy phải hiểu workload class và có validator phù hợp, tránh áp mặc định HTTP server cho mọi container.

## 9. Policy-as-code là gì?

Policy-as-code diễn đạt yêu cầu thành điều kiện có thể version, test và thực thi tự động. Ví dụ:

- Infrastructure as Code phải không mở DB tới §0.0.0.0/0§.
- Kubernetes workloads production không được chạy §privileged: true§.
- Image chỉ từ registries được phép và có provenance.
- Service phải gắn owner, environment, cost center và data classification.
- Thay đổi IAM wildcard cần security review hoặc bị chặn.
- Rollout payment service cần canary và automated SLO gate.
- Một DB deletion không được thực hiện nếu thiếu explicit recovery plan và approved change.

Policy có thể viết bằng OPA/Rego, Kubernetes CEL/ValidatingAdmissionPolicy, Kyverno policy, Terraform plan policy, rule engine của cloud hoặc CI check do tổ chức duy trì. Công cụ nào phù hợp phụ thuộc nguồn data, điểm thực thi và đội vận hành.

### 9.1. Rule phải kiểm được

**Chưa đủ:** “ứng dụng nên an toàn”.

**Kiểm được:** “container thuộc production không được bật privileged, chạy UID khác root trừ exception đã đăng ký”.

**Chưa đủ:** “migration phải được quản lý”.

**Kiểm được:** “migration có thao tác drop column hoặc table phải đi qua high-risk path và có backup/rollback plan được gắn với release record”.

Không phải mọi rủi ro có thể nhận diện chính xác bằng pattern matching. Một migration §ALTER TABLE§ không có từ “DROP” vẫn có thể gây table lock kéo dài; nên dùng phân loại + test + review cho thay đổi rủi ro cao.

## 10. Một rule Rego minh họa

Ví dụ đánh giá input đã được chuẩn hóa từ một manifest Kubernetes:

~~~rego
package deployment.guardrails

import rego.v1

deny contains msg if {
  input.environment == "production"
  some container in input.containers
  container.privileged == true
  msg := sprintf(
    "Privileged container not allowed in production: %v",
    [container.name]
  )
}

deny contains msg if {
  input.environment == "production"
  some container in input.containers
  not container.image_digest
  msg := sprintf(
    "Image digest required for container: %v",
    [container.name]
  )
}
~~~

Đây là **minh họa logic policy**, không phải package copy-paste vào Gatekeeper và chạy ngay. Input §environment§, §containers§ và §image_digest§ là mô hình chuẩn hóa giả định; cần adapter từ Kubernetes admission request/IaC plan và schema tests phù hợp. Cần kiểm behavior khi trường bị thiếu, kiểu dữ liệu sai và admission webhook mất kết nối.

### 10.1. Fail-open hay fail-closed?

Với policy ngăn đặc quyền, public exposure và xóa dữ liệu, thường muốn fail-closed để tránh bypass khi validator lỗi, nhưng cần cân nhắc availability khi control plane hoặc webhook không hoạt động. Với rule chỉ thông tin như style lint, fail-open/soft warning có thể hợp lý.

Quyết định phải nằm trong **threat model và recovery plan**, không để default tùy tiện. Một admission service bị chết mà chặn mọi Pod mới có thể khiến autoscaling và disaster recovery thất bại; cần HA/monitoring của chính policy engine.

## 11. Kubernetes admission policy như một chốt chặn

Một rule trong CI có thể bị bỏ qua nếu ai đó dùng §kubectl apply§ trực tiếp. Admission policies kiểm soát request tại thời điểm tạo/sửa Kubernetes resources, độc lập với pipeline.

Một ví dụ khái niệm theo CEL:

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-owner-label
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["deployments"]
  validations:
    - expression: >
        has(object.metadata.labels) &&
        'platform.example.invalid/owner' in object.metadata.labels
      message: "Deployment must declare an owner label"
~~~

Để policy được thực thi còn cần binding và cấu hình phạm vi theo cluster/version, tránh áp vào toàn bộ namespaces ngoài ý muốn. Tên domain ví dụ là placeholder. Cú pháp/thế hệ API của công cụ thật phải được kiểm với phiên bản Kubernetes đang sử dụng. Một label có thể tồn tại nhưng chứa giá trị không hợp lệ; rule production nên kiểm owner trong registry và không cho dữ liệu giả.

### 11.1. Scope quan trọng hơn “rule có chạy”

- Namespace/environment nào nằm trong phạm vi?
- Có loại trừ system namespaces không?
- Ai được quyền sửa admission policy/binding?
- Policy rule được release và rollback thế nào?
- Nếu rule mới sai, có canary/audit mode trước khi enforce không?
- Có monitoring số admission denied và lý do?
- Có bảo vệ policy engine không bị sửa bởi workload identity thông thường?

## 12. Infrastructure-as-Code guardrails

Thay đổi IaC có thể mở port, thay route, xóa DB, cấp IAM rộng hoặc đổi backup policy. Một đường chuẩn:

~~~text
Pull request
  -> format / validate
  -> dependency and secret scan
  -> IaC plan
  -> policy evaluation on plan
  -> human review for high-risk deltas
  -> approved apply
  -> post-apply drift and health checks
~~~

### 12.1. Những rule thường có lợi

- Storage chứa dữ liệu người dùng không public.
- Database production có encryption, backup retention và network boundary.
- IAM không cấp wildcard actions/resources trừ exception.
- Thay security group 0.0.0.0/0 tới database port bị block.
- Resource có owner, environment, cost center và data classification.
- Production deletion cần plan xác minh, backup và approval.
- Không cho hạ retention log bắt buộc dưới minimum.
- Cloud keys không lưu trực tiếp trong source/config.
- Thay region hoặc residency yêu cầu review phù hợp.

### 12.2. Đừng tin IaC plan là ảnh toàn bộ hệ thống

Plan có thể thiếu tác động runtime, data size, external dependencies hoặc resource được tạo ngoài IaC. Sau apply, cần drift detection, runtime inventory và policy checks trên live resources. Có thể có provider eventual consistency; tránh kết luận drift tức thì luôn là lỗi.

## 13. Branch protection, CODEOWNERS và con người đúng chỗ

Tự động hóa không loại review kỹ thuật có ý nghĩa. Thay vì yêu cầu platform team duyệt **mọi deployment**, hãy dùng code ownership có phạm vi:

- Source code domain: reviewer trong nhóm dịch vụ theo quy định.
- Database migration có tác động lớn: database/data owner.
- Auth/IAM/certificate/security policy: security/platform owners.
- CI/CD pipeline và policy engine code: platform/security owner.
- Shared library hoặc protocol contract: các consumer/producer owners liên quan.
- SLO/incident routing: service owner và on-call stakeholder.

Những thay đổi code đã được review/test trong Git không nhất thiết cần một approval thủ công thứ hai trước deploy nếu đường chuẩn đủ an toàn. Ngược lại, một thay đổi của chính **policy cho phép bypass** cần review mạnh hơn code ứng dụng thông thường.

### 13.1. Separation of duties

Một số quy định hoặc rủi ro yêu cầu người viết thay đổi không phải người duyệt quyết định nhạy cảm. Có thể thực thi bằng CODEOWNERS, protected environments, signed approvals hoặc quyền scoped cho pipeline. Nhưng không nên buộc một hội đồng phải duyệt từng binary đã được ký khi yêu cầu thực sự chỉ là chứng minh quy trình có kiểm soát.

### 13.2. Không dùng automation để tự phê duyệt ngoại lệ của chính nó

Nếu cùng một admin có thể sửa policy, cho phép violation và triển khai thay đổi mà không có audit/independent control, separation of duties có thể chỉ tồn tại trên giấy. Policy changes, exception grants và emergency overrides cần quyền, review và log riêng.

## 14. Tự động hóa trong CI

Một pipeline mẫu cho Java microservice:

~~~mermaid
flowchart TD
    A[PR or Commit] --> B[Build / unit tests]
    B --> C[Integration and contract tests]
    C --> D[Security, secret and dependency checks]
    D --> E[Policy-as-code evaluation]
    E --> F{Mandatory gates pass?}
    F -->|No| G[Block, explain, link remediation]
    F -->|Yes| H[Build signed artifact and provenance]
    H --> I[Deploy staging]
    I --> J[Smoke / load / migration safety]
    J --> K[Deploy canary]
    K --> L[SLO and business checks]
    L --> M{High risk or guardrail breach?}
    M -->|Yes| N[Stop / rollback / responsible review]
    M -->|No| O[Promote and record evidence]
~~~

Các bước có thể thay đổi theo service và độ rủi ro. Một unit test không thay thế integration test, và SAST/scanner không chứng minh không có lỗ hổng. Mục tiêu là có bằng chứng đủ cho **loại thay đổi cụ thể**.

### 14.1. Artifact bất biến

Artifact deploy phải nhận diện được bằng image digest hoặc version không bị ghi đè. Nếu code được review ở commit A nhưng pipeline deploy image §latest§ đã bị thay, bằng chứng review không còn chứng minh nội dung chạy production.

Một chuỗi provenance nên liên kết:

~~~text
Git commit
  -> approved workflow definition
  -> build identity
  -> tests and scans
  -> artifact digest
  -> deployment revision
  -> runtime instance
~~~

### 14.2. Policy result phải nói cách sửa

Thay vì “Policy failed: rule 42”, trả:

~~~text
BLOCK: production deployment cannot use privileged=true.
Resource: order-service / container order-api
Policy: runtime-security/no-privileged, version 1.8
Evidence: deployment.yaml line 57
Remediation: remove privileged or request time-limited exception
Owner: platform-security
~~~

Giảm mơ hồ và vòng hỏi đáp. Nếu policy khiến developer phải hỏi một người để hiểu vì sao fail, bottleneck chỉ chuyển từ approval sang troubleshooting.

## 15. Security supply chain là một phần của tự động hóa

Các guardrails phổ biến:

- Dependency vulnerability scan có mức độ ưu tiên và exception rõ.
- Secret scanning ngăn credential bị commit.
- Container image scan với policy theo severity/exploitability.
- SBOM/provenance đủ để điều tra nguồn thành phần.
- Build pipeline chạy bằng workload identity, token ngắn hạn.
- Artifact được ký hoặc xác thực nguồn theo chính sách tổ chức.
- Registry allowlist và pin digest cho production.
- Không dùng untrusted code với production deploy credentials.
- Cô lập PR từ fork hoặc branch không tin cậy khỏi secrets.
- Review riêng khi workflow pipeline hoặc permissions thay đổi.

**Tự động hóa không thay threat modeling.** Một policy scanner có thể không hiểu rủi ro logic nghiệp vụ: API cho phép refund sai người dùng, race gây double charge hoặc data isolation theo tenant. Các lĩnh vực này cần test nghiệp vụ và security review có trọng tâm.

## 16. Policy cho database migrations

Database thay đổi vừa cần tốc độ vừa có rủi ro lớn. Có thể tự động hóa nhiều migration nếu theo mẫu an toàn:

### 16.1. Standard migration

- Thêm nullable column không phá compatibility.
- Thêm index theo cơ chế online/concurrent thích hợp engine.
- Thêm bảng mới không tác động đường đang phục vụ.
- Expand schema để old/new application cùng chạy được.
- Migrations có version, checksum và integration tests.

Tuy nhiên, việc “thêm index” trên một bảng cực lớn có thể vẫn khóa/tốn tài nguyên. Cần hiểu engine, kích thước dữ liệu và load hiện tại, không phân loại hoàn toàn bằng cú pháp SQL.

### 16.2. High-risk migration

- Drop/truncate bảng hoặc cột đang dùng.
- Đổi kiểu dữ liệu mất chính xác.
- Backfill hàng tỷ bản ghi.
- Thay primary keys/partitioning.
- Thay dữ liệu tài chính hoặc quy tắc tiền tệ.
- Thay retention/audit data.
- Migration không có rollback hoặc ảnh hưởng schema giữa nhiều services.

Các trường hợp này nên có data owner/DBA review, backup+restore plan, capacity simulation, change window và checkpoint/abort conditions.

### 16.3. Expand–migrate–contract

Một cách giảm rủi ro:

1. Expand schema để old/new code đều hoạt động.
2. Deploy code có thể đọc cả schema cũ/mới.
3. Backfill dữ liệu theo batch có monitoring.
4. Chuyển writes/reads theo feature flag hoặc dual-path có kiểm soát.
5. Xác nhận data completeness và consumer compatibility.
6. Contract bỏ schema cũ sau thời gian tương thích.

Policy có thể buộc chứng minh các giai đoạn và test compatibility. Nhưng không nên cho một scanner regex quyết định rằng mọi lệnh §ALTER TABLE§ đều safe hoặc unsafe.

## 17. Policy cho quyền truy cập và secrets

Một số thay đổi ít nên đi tự động hoàn toàn nếu chưa có giới hạn được phê duyệt:

- Tăng quyền IAM theo wildcard trên production.
- Cho workload access mới tới DB chứa PII hoặc ledger.
- Mở public ingress/egress khác vùng tin cậy.
- Vô hiệu hóa MFA, audit logging hoặc encryption.
- Tạo long-lived access keys thay short-lived identity.
- Thay quyền quản lý admission/policy engine.
- Thay key management, encryption policies hoặc break-glass access.

Automation có thể **block rõ ràng** những cấu hình không hợp lệ, đồng thời route các trường hợp hợp pháp sang review có người chịu trách nhiệm.

### 17.1. Approval cho “policy”, không cho mỗi request

Ví dụ: “Payment Service được đọc Secret A bằng workload identity P; chỉ network path tới PSP đã định; rotation không đổi quyền và được tự động rollout”. Khi policy đã được phê duyệt, những lần rotation bình thường có thể chạy tự động với test và audit. Nếu quyền chuyển sang đọc thêm toàn bộ customer secrets, đó là thay đổi risk class cần review.

## 18. Feature flags cũng là thay đổi production

Một flag có thể làm đổi nghiệp vụ ngay mà không deploy image. Vì vậy flag management cần chính sách:

- Owner và mô tả rủi ro.
- Scope của flag theo tenant/region/cohort.
- Default an toàn và kill switch.
- Các ràng buộc không được phép vượt (ví dụ payment capture path).
- Audit ai đổi, trước/sau, lý do, thời điểm.
- Thử trên cohort nhỏ nếu có ảnh hưởng người dùng.
- Automatic rollback trên SLO/business guardrails khi phù hợp.
- Expiry/lifecycle để tránh flag tồn tại vĩnh viễn.

Một flag bật UI theme có thể là standard; flag chuyển logic tính phí hoặc bypass fraud checks phải ở class rủi ro cao. Không tự đồng nhất “không có code change” với “low risk”.

## 19. Progressive delivery thay hội đồng phê duyệt mọi lần

Bước approve dựa trên việc người duyệt đoán rủi ro trước deploy. Progressive delivery đưa **bằng chứng khi thay đổi đang chạy thật trên phạm vi nhỏ**:

- Canary 1–5% traffic nếu đủ mẫu.
- Blue-green với health/smoke gates.
- Phân đoạn theo region/tenant/cohort có kiểm soát.
- Read-only hoặc shadow mode cho phần chưa an toàn.
- Feature flag để tắt nhanh một capability.
- Automatic stop/rollback khi SLO và business metrics xấu đi.

### 19.1. Gate trước và sau deploy

**Trước deploy:** tests, scan, schema compatibility, policy, artifact signature, owner, impact scope.

**Trong rollout:** request failure, latency good-event ratio, error budget burn, queue age, workflows stuck, payment integrity guardrail và resource saturation.

**Sau rollout:** business completion, replay/reconciliation, data correctness, logging/audit và change record.

Không có một SLI nào thay được kiểm soát business integrity. Một canary có 0,01% traffic vẫn có thể tạo một khoản charge sai; với thay đổi settlement, nên có preproduction financial invariants và human risk review phù hợp.

### 19.2. Automated rollback có giới hạn

Không phải mọi thay đổi rollback được chỉ bằng đổi image. Database migration mất dữ liệu, external side effect, webhook phát ra hoặc schema đã thay có thể không đảo ngược. Policy engine cần phân biệt:

- Rollback code/config/flag khả thi.
- Roll forward hoặc compensation cần thiết.
- Restore backup có impact lên dữ liệu mới.
- Freeze writes hoặc dừng promotion nếu không có phương án an toàn.

Một rule “nếu 5xx tăng thì tự rollback hết” có thể nguy hiểm khi bản cũ không tương thích schema mới. Cần runbook theo loại thay đổi.

## 20. Mẫu risk-based release policy

Một policy kỹ thuật có thể diễn đạt theo tiêu chí:

| Điều kiện | Low-risk auto | Medium-risk controlled | High-risk review |
|---|---|---|---|
| Binary/code change trong một service | Có nếu tests pass | Có canary/SLO gates | Nếu xử lý tiền, identity hoặc contract phá |
| Config | Có trong khoảng đã duyệt | Bật flag cohort nhỏ | Thay secret scope/permissions |
| Database | Migrations additive được kiểm | Backfill lớn có window | Drop dữ liệu, đổi kiểu mất dữ liệu |
| Infra | Tag, resource requests trong mức | Scale/topology lớn | Public exposure, destructive action |
| IAM | Rotation cùng scope | Role mới đã nằm trong template | Wildcard/sensitive data expansion |
| Event contract | Backward-compatible | Versioned rollout nhiều consumer | Breaking schema không có migration |
| Runtime | Rollout qua standard pipeline | Canary nhiều vòng | Thay policy cấp tổ chức |
| Emergency | N/A | Incident response policy | Break-glass với audit/escalation |

Đây là mẫu ra quyết định, không áp đặt lên mọi ngành. Định nghĩa **low-risk** phải được owner, Security/Compliance và domain experts cùng chấp nhận, có bằng chứng từ incidents và triển khai.

## 21. Một policy file minh họa

Có thể lưu quy tắc dễ đọc để reviewer hiểu:

~~~yaml
policyVersion: "1.0"
environment: production

standardChange:
  requiredChecks:
    - unit_tests
    - integration_tests
    - contract_tests
    - dependency_scan
    - secret_scan
    - artifact_provenance
    - deployment_plan
  requireOwner: true
  allowedDeployment:
    strategy: canary
    automaticStopOnSLOBreach: true
  noPrivilegeExpansion: true

highRiskTriggers:
  - destructive_database_change
  - external_public_data_exposure
  - broadened_production_iam
  - payment_settlement_logic_change
  - cross_region_data_movement
  - audit_retention_reduction

exception:
  requires:
    - accountable_owner
    - justification
    - scope
    - expires_at
    - compensating_controls
    - independent_approval
    - audit_record
~~~

Đây là một **policy DSL minh họa**, không phải cấu hình được GitHub Actions, OPA hay Argo CD hiểu trực tiếp. Để thực thi, cần viết/duy trì adapter, schema validation, tests và xác định mỗi check được lấy từ đâu, ký xác nhận thế nào.

## 22. Ví dụ pipeline triển khai

Một đoạn CI/CD pseudocode:

~~~yaml
pipeline:
  build:
    - compile
    - unit-tests
    - integration-tests
    - create-image-and-provenance

  evaluate:
    - check-owned-service
    - scan-secrets-and-dependencies
    - validate-infrastructure-plan
    - evaluate-policy-and-risk-class

  decide:
    standard:
      condition: "all_required_checks_pass && no_high_risk_trigger"
      action: "deploy_to_staging_then_canary"
    highRisk:
      condition: "high_risk_trigger_detected"
      action: "require_accountable_review"
    invalid:
      condition: "mandatory_policy_failed"
      action: "block"

  verify:
    - smoke-test
    - SLO-and-business-guardrails
    - record-audit-and-artifact-digest
~~~

Ví dụ này mô tả flow, không phải workflow YAML thực thi bởi một sản phẩm cụ thể. Trong pipeline thật, cần phân biệt PR validation, trusted merge events, protected environment token và deploy credentials. Không để một PR chưa được tin cậy tự đặt §high_risk_trigger_detected=false§ rồi vượt gate.

### 22.1. Chứng cứ nên được sinh tự động

Mỗi release record nên chứa:

~~~json
{
  "change_id": "chg-20261112-336",
  "service": "order-service",
  "environment": "production",
  "commit": "example-commit-sha",
  "artifact_digest": "sha256:example-digest",
  "policy_version": "risk-rules-1.0",
  "risk_class": "standard",
  "checks": {
    "unit": "passed",
    "integration": "passed",
    "contract": "passed",
    "security_scan": "passed",
    "infra_policy": "passed"
  },
  "deployment": {
    "strategy": "canary",
    "region": "apac",
    "result": "completed"
  },
  "exceptions": [],
  "actor": "trusted-release-workflow",
  "timestamp": "2026-11-12T02:30:00Z"
}
~~~

Giá trị là placeholder. Một release record cần provenance và integrity, không tự tin chỉ vì một JSON file có chữ “passed”; nên liên kết trực tiếp tới immutable logs/artifacts, được bảo vệ khỏi sửa bởi chính service account đang deploy nếu yêu cầu audit cao.

## 23. Automated approval không đồng nghĩa “để AI tự quyết”

AI có thể giúp tóm tắt thay đổi, giải thích policy failure, viết test hoặc hỗ trợ review, nhưng các quyết định production nhạy cảm cần quy tắc có thể kiểm chứng và accountability. Không nên cho một model dự đoán “trông an toàn” thay thế một security policy deterministic mà không có validation, threat model, audit và cơ chế human override phù hợp.

Có thể dùng AI ở các khâu **hỗ trợ**:

- Tóm tắt IaC plan để reviewer xem nhanh.
- Gợi ý runbook/rollout tests.
- Nhóm các policy violations có cùng nguyên nhân.
- Phân loại initial risk để gợi ý tuyến xử lý, sau đó kiểm bằng deterministic rules.
- Gợi ý remediation cho linter/scan.
- Phân tích incident trends để cải thiện rule.

Kết quả AI có thể sai; không coi nhận xét tự động là bằng chứng rằng critical action đã được kiểm soát.

## 24. Exception có hạn thay vì bypass vĩnh viễn

Không có policy set nào bao phủ mọi trường hợp. Một sản phẩm có thể cần privileged container cho driver đặc thù hoặc public endpoint cho dịch vụ đã được đánh giá. Quy trình ngoại lệ phải có:

- **Reason:** business/technical need và policy bị vi phạm.
- **Owner:** người chịu trách nhiệm với rủi ro.
- **Scope:** service, resource, namespace, region và thời gian cụ thể.
- **Expiry:** ngày hết hạn, không mặc định vĩnh viễn.
- **Compensating controls:** network isolation, enhanced monitoring, sandboxing...
- **Approval:** người có thẩm quyền, độc lập nếu cần.
- **Evidence:** ticket, threat assessment, tests.
- **Review cadence:** trước khi gia hạn.
- **Revocation:** cách rút ngoại lệ không làm hỏng production đột ngột.
- **Audit:** ai tạo/sửa/gia hạn và vì sao.

### 24.1. Exception-as-code

Một record minh họa:

~~~yaml
exceptionId: "exc-2026-042"
policyId: "runtime/no-privileged"
resource:
  namespace: "device-workers"
  service: "sensor-driver"
justification: "Requires device access under isolated node pool"
owner: "device-platform"
approver: "security-lead"
expiresAt: "2026-12-15T00:00:00Z"
compensatingControls:
  - "dedicated-node-pool"
  - "restricted-network-egress"
  - "enhanced-runtime-monitoring"
reviewLink: "https://tickets.example.invalid/SEC-1234"
~~~

Đây là ví dụ. Policy engine cần thực sự map exception ID vào đúng scope và kiểm expiry; một YAML chứa §expiresAt§ nhưng không có process tự thu hồi/gia hạn không tạo ra kiểm soát.

### 24.2. Đừng biến exception thành default

Nếu 30% workloads có cùng exception, có thể policy không phù hợp hoặc platform thiếu supported path. Cần review policy design, workload types và remediation, không tiếp tục cấp exceptions thủ công vô tận.

## 25. Emergency change và break-glass

Khi production outage lớn, không nên để một approval step bị kẹt vì người duyệt nghỉ làm. Nhưng break-glass cũng không phải “admin quyền vĩnh viễn”.

Một thiết kế cân bằng:

1. Có incident ID và người chịu trách nhiệm.
2. Quyền khẩn có giới hạn và TTL ngắn.
3. Có strong authentication và audit độc lập.
4. Phân quyền theo loại thao tác, không mặc định global admin.
5. Hành động được log, đánh dấu khẩn và gửi notification.
6. Có compensating controls, backup hoặc recovery point trước destructive action nếu khả thi.
7. Sau incident, review trong thời gian đã quy định.
8. Revoke quyền và kiểm không còn bypass.
9. Đưa root cause vào cải thiện đường chuẩn nếu một guardrail không đáp ứng emergency.
10. Không sửa lén evidence hoặc thay đổi lịch sử approval.

### 25.1. Break-glass có thể là cách bảo vệ khả năng phục hồi

Trong một sự cố cluster policy engine ngừng hoạt động, admission fail-closed có thể chặn việc tạo Pod mới. Cần runbook phục hồi policy plane hoặc cơ chế exception có audit và giới hạn, không tắt mọi chính sách toàn cluster mà không ghi nhận.

## 26. Policy engine cũng là hạ tầng quan trọng

Nếu policy engine hoặc workflow checker lỗi, cả pipeline có thể dừng. Quản trị cần tính tới:

- HA và capacity của admission webhooks/policy evaluators.
- Caching/snapshot policy đã ký nếu có.
- Version pinning và controlled rollout của rule changes.
- Monitoring evaluation latency, deny rate, failures và availability.
- Test behavior khi policy service timeout.
- Khả năng rollback policy version.
- Separation of duties khi sửa chính policy.
- Cách phục hồi khi rule sai block hàng loạt deployments.
- Log bằng chứng không bị xóa bởi actor thiếu quyền.
- Compatibility giữa policy và công cụ IaC/deploy.

**Một chính sách được thực thi sai có thể là một nguồn outage.** Vì vậy policy-as-code cần chính những thực hành SDLC: tests, staging, canary, monitoring, ownership, rollback.

## 27. Kiểm thử chính sách

### 27.1. Unit tests cho positive/negative cases

Với rule “production không có privileged container”, test:

- Production, privileged=true → deny.
- Production, privileged=false → allow nếu các rule khác pass.
- Staging, privileged=true → theo policy staging.
- Field privileged không có → hiểu default và đánh giá an toàn.
- Nhiều containers, một container vi phạm → deny.
- Init containers có privileged=true → không bỏ sót.
- Ephemeral containers hoặc resource kind khác → scope policy rõ.
- Resource đang tồn tại và update hợp lệ → không bị chặn vô lý.

### 27.2. Property-based và mutation tests

Có thể sinh nhiều manifests hợp lệ/bất hợp lệ để tìm bypass khi field path khác, nulls, capitalization, schema khác phiên bản hoặc list containers nested. Mutation tests giúp biết test suite có phát hiện một rule bị sửa sai hay không.

### 27.3. Integration test

Chạy policy với admission/IaC provider phiên bản thật trong môi trường test. Kiểm error messages, latency, failure mode và các trường hợp policy engine unavailable. Không suy luận rule chạy đúng chỉ từ unit test trên input đã chuẩn hóa.

### 27.4. Audit → Warn → Enforce

Một policy mới có thể triển khai theo giai đoạn:

1. Audit mode: ghi số violations nhưng chưa block.
2. Review false positives, workload classes và remediation.
3. Warn mode: trả feedback rõ cho developer.
4. Enforce ở staging hoặc nhóm namespaces nhỏ.
5. Enforce production theo progressive rollout.
6. Monitor deny rates, incident impacts và exceptions.
7. Tối ưu rule và golden path khi phát hiện friction.

Với vi phạm nghiêm trọng đã biết (ví dụ lộ secret hoặc public database), có thể cần enforce ngay theo policy tổ chức; quy trình rollout ở trên không thay thế emergency action.

## 28. Phê duyệt tập trung vào việc khó đánh giá tự động

Một số câu hỏi cần người hiểu context:

- Thay đổi chính sách tính phí có đáp ứng hợp đồng khách hàng không?
- Tắt một kiểm soát fraud có được tổ chức chấp nhận?
- Có cho phép dữ liệu khách hàng đi sang vùng pháp lý mới không?
- Migration làm mất dữ liệu có phương án khôi phục/compensation không?
- Đổi quy trình settlement có tạo rủi ro tiền hoặc audit không?
- Chấp nhận lỗ hổng bảo mật chưa vá trong bao lâu và với compensating controls nào?
- Có được deploy giữa sự kiện kinh doanh không thể chấp nhận downtime?
- Khi công cụ quét đưa false positive, ai có quyền chấp nhận rủi ro?

Những quyết định này có thể được **hỗ trợ bởi dữ liệu tự động** nhưng không nhất thiết được quyết định hoàn toàn bởi máy. Mục tiêu là giảm review của con người ở những thay đổi đã chuẩn hóa, dành thời gian cho ngoại lệ có tác động thật.

## 29. Governance cho microservices và shared interfaces

Microservices phân chia ownership, nhưng một thay đổi interface có thể ảnh hưởng nhiều team. Policy nên có contract rules:

- API backward compatibility theo cách đã thống nhất.
- Event schema compatibility và versioning.
- Consumer-driven contract tests.
- Database schema evolution theo expand–migrate–contract.
- Service ownership, dependency catalog và runbook links.
- Deprecation window và migration notice.
- Domain event PII classification.
- SLO/SLI của capability xuyên service.

Một producer có thể triển khai tự động nếu contract tests chứng minh không phá consumers. Nếu cố ý breaking change, cần migration plan và review từ các owner liên quan; không phải chỉ từ một central CAB.

### 29.1. Shared platform changes có blast radius lớn

Thay một ingress controller, DNS policy, service mesh hoặc logging collector có thể ảnh hưởng hàng trăm service. Dù file diff nhỏ, risk class có thể cao. Policy phải xét **đối tượng bị ảnh hưởng**, không chỉ số dòng code.

## 30. Quy trình thay đổi theo trạng thái

Một release record có thể theo state machine:

~~~text
PROPOSED
  -> VALIDATING
  -> POLICY_EVALUATED
      -> BLOCKED (mandatory violation)
      -> AWAITING_RISK_APPROVAL (high-risk)
      -> APPROVED_STANDARD (preapproved path)
  -> STAGING_VERIFIED
  -> CANARY
      -> PAUSED / ROLLED_BACK
      -> PROMOTED
  -> POST_DEPLOY_VERIFIED
  -> CLOSED
~~~

Mỗi transition có actor, thời gian, evidence và rule version. Một bước bị đánh dấu pass nhưng artifact bị thay đổi sau đó phải khiến approvals/evidence không còn hiệu lực; pipeline cần bind evidence tới **exact artifact digest và deployment plan**.

### 30.1. Approval không nên là checkbox bất biến

Nếu risk reviewer đã approve commit X, nhưng branch thay đổi thành commit Y hoặc Terraform plan đổi sau apply drift, cần tính lại policy và có thể xin review lại. Không dùng approval của một nội dung để hợp thức hóa nội dung khác.

## 31. Kiểm soát môi trường khác nhau

| Môi trường | Mục tiêu | Chính sách phù hợp |
|---|---|---|
| Local/dev | Feedback nhanh, tránh rò secrets | Lint, unit tests, secret scan, safe sandbox |
| CI ephemeral | Tái hiện và chứng minh | Integration/contract tests, ephemeral credentials |
| Staging | Kiểm tương thích và rollout | Full policy eval, migrations rehearsal, test identities |
| Production | Bảo vệ users/data và availability | Trusted artifacts, strict IAM, progressive rollout, audit |
| DR region | Phục hồi có giới hạn thời gian | Preapproved DR controls, isolated permissions, recovery runbooks |

Không nên để dev mở toàn quyền production chỉ vì cần “nhanh”. Ngược lại, không cần bắt developer chờ CAB để deploy vào một environment test hoàn toàn cô lập không có sensitive data.

## 32. Runtime enforcement và drift detection

Thực thi ở PR/CI không ngăn người có quyền cloud console sửa resource production sau deploy. Tổ chức cần:

- Inventory và ownership các resources.
- Periodic drift detection giữa IaC/Git và effective config.
- Cloud audit logs, Kubernetes audit, IAM change events.
- Config compliance scanners.
- Alerts khi public exposure, encryption disable hoặc wildcard IAM xuất hiện.
- Tự động rollback/quarantine một số vi phạm nếu chắc chắn an toàn.
- Review và exception cho những drift hợp lệ có thời hạn.
- Chặn write trực tiếp bằng RBAC/identity khi có thể, thay vì chỉ dựa trên cảnh báo.

### 32.1. Tự khôi phục cấu hình không phải lúc nào an toàn

Một controller thấy config drift rồi lập tức revert có thể làm mất emergency mitigation đang giúp hệ thống phục hồi. Cần biết change freeze, incident override và ownership. Rule nên phân biệt vi phạm không thể chấp nhận với drift chưa rõ nguyên nhân và có quy trình can thiệp.

## 33. SLO, error budget và policy phát hành

Tự động hóa phải gắn với tác động người dùng, không chỉ pipeline xanh.

Ví dụ một nhóm Checkout có SLO 99,9% successful eligible workflows trong 30 ngày. Nếu error budget burn quá cao, policy có thể:

- Dừng tự động promote canary.
- Tạm freeze các feature release không cần thiết.
- Cho phép fix-forward/rollback với quyền kiểm soát phù hợp.
- Đòi review owner trước thay đổi không liên quan sự cố.
- Kiểm ongoing incident và critical business guardrails.
- Mở lại standard path sau khi SLO khỏe và owner chấp thuận.

### 33.1. Không khóa toàn bộ delivery khi cần sửa lỗi

Một quy tắc máy móc “error budget còn thấp → cấm mọi deploy” có thể ngăn bản vá khắc phục sự cố. Policy nên có **incident remediation path** và phân biệt risk-increasing changes với reliability improvements, cùng audit và guardrails đặc thù.

### 33.2. Business guardrails

- Không duplicate charge.
- Không oversell.
- Không lost paid orders.
- Không invalid state transitions.
- Không cross-tenant data access.
- Các workflow quan trọng đạt deadline.
- Queue backlog drain được sau spike/dependency outage.

Một canary có low 5xx vẫn có thể vi phạm invariant tiền. Khi cần, policy gate phải có kiểm soát tính đúng vượt ngoài HTTP metrics.

## 34. Đo hiệu quả của thay đổi quản trị

Không lấy “số approvals giảm 90%” làm thành công duy nhất. Cần đo cả tốc độ và an toàn:

| Chỉ số | Ý nghĩa |
|---|---|
| Lead time for changes | Từ commit tới production |
| Deployment frequency | Khả năng release nhỏ thường xuyên |
| Change failure rate | Tỷ lệ deploy gây incident/rollback |
| Time to restore service | Khả năng phục hồi sau thay đổi lỗi |
| Median approval wait | Chi phí hàng đợi do xét duyệt |
| Policy false-positive rate | Guardrail chặn nhầm thay đổi |
| Exception count/age | Mức policy đang cần bypass |
| Unreviewed sensitive changes | Lỗ hổng quản trị |
| Manual direct changes | Drift/ngoại lệ ngoài pipeline |
| SLO/error budget | Tác động người dùng theo capability |
| Security findings exposure | Rủi ro còn tồn tại và thời gian xử lý |
| Developer onboarding time | Độ dễ sử dụng golden path |
| Evidence completeness | Audit trace từ commit tới runtime |
| On-call workload | Gánh nặng incident/alert do pipeline/policy |

Cần baseline trước khi tự động hóa; xem biến động theo service/risk class. Nếu lead time giảm nhưng change failure rate và incidents tăng, cần sửa policy/tests/rollout chứ không chỉ ăn mừng tốc độ.

### 34.1. Cẩn thận với định nghĩa

- Một “deployment” có thể là một service image rollout, một flag change hay một full release; thống nhất đơn vị.
- “Failure” phải có policy: rollback, hotfix, incident, SLO violation hay data correction.
- “Approval wait” nên đo từ lúc evidence hoàn tất tới lúc được quyết định, không gộp thời gian developer còn viết code.
- Chỉ số exception count tăng có thể do phát hiện tốt hơn, không hẳn rủi ro tăng.
- Report tránh cho team “gaming” số liệu, ví dụ cố gộp thay đổi để tăng tỷ lệ successful approvals.

## 35. Tổ chức sở hữu policy

Đề xuất vai trò:

| Vai trò | Trách nhiệm |
|---|---|
| Platform Team | Golden path, CI/CD, admission, policy engine availability |
| Security | Control objectives, threat model, permission/data policies |
| SRE/Operations | SLO, rollout/recovery policies, incident playbooks |
| Domain Owners | Business invariants, data contract, change impact |
| Compliance/Risk | Evidence, regulated controls, exception accountability |
| Developer Teams | Sửa violations, viết tests, duy trì runbook/service metadata |
| Change Governance | Phê duyệt chính sách loại thay đổi, review rủi ro đặc biệt |
| Audit | Kiểm evidence, độc lập với người tạo thay đổi theo yêu cầu |

### 35.1. Policy ownership không phải độc quyền sửa mọi repo

Mỗi policy có maintainer, approvers và review cadence. Team chịu trách nhiệm có thể đóng góp rule qua PR, nhưng các thay đổi mở rộng quyền hoặc làm yếu critical controls cần reviewer độc lập. Quy trình đó giúp policy-as-code được cải tiến cùng nhu cầu sản phẩm thay vì thành tài liệu “không ai dám sửa”.

## 36. Migration từ xét duyệt thủ công sang policy-as-code

### Giai đoạn 1 — Kiểm kê quy trình hiện tại

Thu thập:

- Các loại thay đổi và volume mỗi tháng.
- Những approval steps và thời gian chờ.
- Những quyết định reviewer thực sự tạo ra giá trị.
- Incident nào approval phát hiện/tránh được và incident nào vẫn xảy ra.
- Policy nào hiện nằm trong checklist/email/wiki.
- Exceptions, emergency changes và control gaps.
- Công cụ CI/CD, IaC, cloud audit và identity có sẵn.

Không tự động hóa một bước chưa hiểu mục đích. Một bước xét duyệt có thể đang che lấp dữ liệu/ownership thiếu, và xóa ngay sẽ làm lộ rủi ro.

### Giai đoạn 2 — Chuẩn hóa standard changes

Chọn một loại thay đổi ít rủi ro, lặp lại nhiều, có test và rollback. Ví dụ update Java service đã có CI, integration tests, signed image, canary và SLO dashboard. Định nghĩa tiêu chí để lần deploy tiếp theo không cần approval riêng.

### Giai đoạn 3 — Tự động sinh evidence

Kết nối Git, build pipeline, scanner, IaC plan, deployment revision, test reports và runtime metrics. Dùng release record có stable ID. Tránh yêu cầu developer tự upload screenshot mỗi lần pipeline đã có dữ liệu.

### Giai đoạn 4 — Policy trong audit mode

Chạy rule không block, đo false positives và loại workload đặc thù. Sửa lỗi rule, tạo remediation docs và cập nhật templates.

### Giai đoạn 5 — Enforce theo phạm vi

Áp dụng cho một service/namespace/nhóm trước, theo dõi denied changes, lead time, incident và feedback. Mở rộng dần khi có bằng chứng.

### Giai đoạn 6 — Risk-based approval

Chuyển CAB/human approval sang những hành động không thể tự đánh giá hoặc có impact đặc biệt. Có owner và SLA phản hồi, không tạo hàng đợi vô hạn.

### Giai đoạn 7 — Đánh giá và điều chỉnh

Định kỳ review policy rules, exceptions, security incidents, developer friction và SLO. Loại rule không còn ý nghĩa, sửa defaults và nâng mức kiểm soát nếu rủi ro đã thay đổi.

## 37. Case study: deploy Order Service không cần CAB từng lần

### 37.1. Bối cảnh giả định

Order Service triển khai 10 lần/tuần, mỗi lần thay bug fix nhỏ hoặc bổ sung validation. Trước đây phải chờ approval từ nhóm vận hành 1–2 ngày. Trong khi đó service có đủ unit/integration/contract tests, image versioning, metrics, SLO và canary.

### 37.2. Thiết kế standard change

Bước chuẩn:

1. PR cần code owner review theo rule.
2. CI chạy tests, dependency scan, secret scan.
3. Build image immutable và provenance.
4. Validate IaC/deployment policy: no privileged container, registry allowlist, resource budgets, owner labels.
5. Deploy staging và smoke tests.
6. Promote canary 5% production, theo dõi errors, latency và OrderCompletion SLI.
7. Nếu canary khỏe và không có high-risk trigger, tăng traffic tự động theo bước.
8. Nếu SLO bất thường, pause/rollback code theo điều kiện tương thích.
9. Sinh release record và audit evidence.

Nếu PR đồng thời đổi logic capture tiền hoặc migration drop column, nó **không còn là standard change**; pipeline route sang high-risk review dù test unit pass.

### 37.3. Lợi ích cần đo

- Approval wait giảm.
- Team deploy thay đổi nhỏ nhanh hơn.
- Fewer large-batch releases.
- Change failure rate không tăng.
- RTO/rollback không xấu đi.
- Evidence completeness tốt hơn.
- Số policy violations và false positives nằm trong ngưỡng.

Không tuyên bố cải thiện nếu thiếu baseline và monitoring sau áp dụng.

## 38. Case study: Kubernetes change policy tạo sự cố

### 38.1. Tình huống

Platform team thêm rule bắt buộc mọi Pod có liveness probe ngưỡng ngắn. Một nhóm có startup 120 giây và GPU job không có HTTP server bị block hoặc restart liên tục khi rollout.

### 38.2. Nguyên nhân quản trị

Policy không xét workload class, chưa thử trên staging tương tự và không có audit rollout. Rule đã được phê duyệt thủ công nhưng vẫn sai vì nội dung không phù hợp.

### 38.3. Hành động

- Tạm dừng enforce/sửa policy theo runbook có audit.
- Phân loại Deployment API, Job, CronJob và long-start workloads.
- Dùng startupProbe và readiness/liveness phù hợp thay vì một quy tắc universal.
- Test policy trên representative manifests và shadow evaluation.
- Cập nhật golden path và remediation messages.
- Triển khai lại theo namespace/canary; đo policy false positives và workload SLO.

**Bài học:** policy-as-code cần được kiểm thử và rollout như ứng dụng. Tự động hóa giúp thực thi nhất quán cả rule đúng lẫn rule sai.

## 39. Case study: thay đổi IAM có tác động nhạy cảm

Một team muốn cho Notification Service đọc toàn bộ customer profile database để tạo chiến dịch. Pipeline phát hiện IAM scope mới mở rộng truy cập PII so với policy hiện hành.

Đây không phải một standard deployment dù file diff chỉ vài dòng. Cần:

- Data owner và Security đánh giá mục đích, minimization và quyền.
- Xác định có thể cung cấp một API/data view giới hạn thay vì DB access rộng không.
- Có threat model, audit, retention và privacy controls.
- Nếu được chấp thuận, policy cập nhật scope rõ và tests.
- Không cấp quyền wildcard chỉ để pipeline xanh.
- Có expiry/review nếu quyền chỉ cần tạm.
- Theo dõi data access audit sau triển khai.

Automation ở đây **giúp dừng và định tuyến**, không nhất thiết tự approve.

## 40. Case study: emergency fix giữa outage

Checkout bị lỗi nghiêm trọng sau khi cập nhật cấu hình. Service owner biết cách rollback nhưng production deploy đang yêu cầu CAB approval, người duyệt không online.

Một thiết kế tốt có:

1. Preapproved incident rollback path.
2. On-call identity có quyền rollback scoped, TTL và MFA.
3. Incident ID, timestamp và audit tự động.
4. Artifact rollback đã biết và tương thích.
5. Sau rollback kiểm SLO và paid orders stuck, không chỉ Pod Ready.
6. Notification tới Security/Platform theo policy.
7. Post-incident review và revoke break-glass quyền tạm.
8. Cập nhật gate/canary để phát hiện loại regression này sớm hơn.

Nếu rollback không an toàn do schema đã đổi, emergency path cần hướng dẫn mitigation/fix-forward; không tự động chọn “previous image” như một phép chữa chung.

## 41. Các sai lầm thường gặp

1. **Giữ approval mọi deployment dù checks đã cố định.** Tạo queue và review fatigue.
2. **Bỏ mọi approval và cho bot deploy tất cả.** Không phân biệt high-impact/irreversible changes.
3. **Policy chỉ nằm trong wiki.** Không có enforcement/evidence.
4. **Rule quá chung, không xét workload class.** Chặn service khỏe hoặc tạo outage.
5. **Chỉ kiểm CI, không có admission/runtime checks.** Người dùng đường tắt vẫn thay production.
6. **Chỉ dựa trên scanner.** Không hiểu lỗi logic tài chính/tenant.
7. **Tự động rollback khi database đã đổi không tương thích.** Có thể gây hỏng dữ liệu.
8. **Để developer sửa workflow rồi deploy với credentials nhạy cảm.** Mất trust boundary.
9. **Dùng shared admin credentials.** Không thể truy trách nhiệm hoặc giới hạn blast radius.
10. **Exception không expiry.** Bypass tạm trở thành vĩnh viễn.
11. **Không kiểm policy engine availability.** Một webhook lỗi chặn deploy/scale-out.
12. **Approval không bind vào commit/artifact digest.** Có thể phê duyệt một thứ, deploy thứ khác.
13. **Để owner tự duyệt mở rộng quyền của mình.** Separation of duties chỉ trên giấy.
14. **Không audit thay đổi feature flags.** Production thay đổi mà không có release record.
15. **Chặn mọi deploy khi SLO xấu.** Ngăn cả bản vá phục hồi.
16. **Chỉ đo deployment frequency.** Bỏ qua change failure rate và incident.
17. **Chỉ đo policy deny count.** Không biết false positives và real prevented risks.
18. **Không có remediation docs.** Developer mất giờ hỏi người duyệt rule.
19. **Tự động apply IaC plan không kiểm drift/actual resources.** Evidence thiếu.
20. **Không review exceptions và technical debt.** Policy hiệu lực giảm dần.
21. **Không bảo vệ người sửa policy.** Một token có thể gỡ mọi kiểm soát.
22. **Dùng AI nhận xét “safe” thay control objective.** Không có quyết định kiểm chứng.
23. **Áp production policy y hệt vào local/dev.** Giảm tốc học tập mà không giảm rủi ro production.
24. **Chạy quá nhiều tools chồng lấp, không rõ owner.** Tạo false positives và chi phí vận hành mới.
25. **Xem automation là mục tiêu riêng.** Quên user impact, accountability và recovery.

## 42. Bài tập thực hành

### Bài A — Phân loại thay đổi

Cho mười thay đổi: đổi README; sửa validation trong Order; tăng replica; bật feature flag làm tính phí khác; thêm nullable DB column; drop bảng cũ; cấp quyền đọc PII; rotate secret không đổi scope; mở DB port public; rollback trong incident.

Hãy phân loại standard/controlled/high-risk/emergency, nêu automated gates, người chịu trách nhiệm, điều kiện escalation và evidence.

### Bài B — Viết policy cho container

Thiết kế rule ngăn privileged containers, yêu cầu owner labels và image registry allowlist. Đề xuất input schema, test cases hợp lệ/không hợp lệ, admission scope và cách rollout audit→enforce.

### Bài C — Thiết kế pipeline

Vẽ pipeline cho Spring Boot service: PR review, unit/integration tests, SBOM/secret scan, immutable image, policy eval, staging, canary, SLO gates, rollback và release record. Xác định điều kiện cho low-risk tự promote và high-risk phải review.

### Bài D — Phân tích lỗ hổng trust

Một pipeline cho phép PR từ fork thay CI YAML, đồng thời có production deployment token ở job test. Hãy giải thích trust boundary và thiết kế tách untrusted validation khỏi trusted deployment, dùng short-lived identities và protected environments.

### Bài E — Exception registry

Một nhóm cần privileged GPU driver trong production đến ngày 15/12/2026. Hãy tạo exception có owner, resource scope, expiry, compensating controls, independent approval và cách thu hồi. Thiết kế alert khi exception sắp hết hạn.

### Bài F — Emergency rollback

Incident làm checkout thất bại 30% nhưng CAB không có người trực. Thiết kế preapproved rollback path có incident ID, quyền TTL, audit, SLO verification, payment reconciliation và post-incident review.

### Bài G — Đo kết quả

Một quý có 300 deployment requests, trung bình chờ approval 12 giờ. Sau tự động hóa, 260 standard changes không chờ approval, 40 high-risk vẫn review. Hãy ước lượng tổng thời gian chờ đã loại bỏ theo giả định rõ, và nêu ít nhất năm chỉ số cần theo dõi để chắc hệ thống không kém an toàn.

### Bài H — Chính sách gây outage

Admission policy mới bắt buộc liveness probe trên mọi Job khiến 300 batch jobs fail. Hãy viết incident response, rollback policy, kiểm blast radius, sửa workload classification và canary strategy trước khi enforce lại.

### Bài I — SLO và thay đổi

Checkout SLO đang cháy error budget nhanh. Có một feature deployment bình thường và một hotfix giảm timeout. Bạn sẽ cho phép mỗi change ra sao? Thiết kế rule để không khóa bản vá cần thiết nhưng vẫn bảo vệ trạng thái người dùng.

### Bài J — ADR về governance

Viết một Architecture Decision Record ngắn: bối cảnh nhiều teams phải xin CAB mỗi deploy; lựa chọn (giữ approval, bỏ approval, risk-based policy-as-code); quyết định, tradeoffs, security obligations, exception path và trigger review.

## 43. Checklist thực thi

### Chính sách và ownership

- [ ] Phân loại change theo impact, reversibility, permissions, data và domain risk.
- [ ] Standard change criteria được phê duyệt trước theo loại.
- [ ] High-risk trigger và independent reviewer rõ ràng.
- [ ] Có policy owner, rule version và review cadence.
- [ ] Có danh sách exceptions với scope, expiry và accountability.
- [ ] Có break-glass path an toàn, TTL, audit và post-review.
- [ ] Các rule không xung đột với compliance hoặc contractual obligations.

### CI/CD và enforcement

- [ ] Repository protection/CODEOWNERS theo phạm vi nhạy cảm.
- [ ] Tests, security scans, IaC plan và contract checks theo workload.
- [ ] Artifact digest/provenance được bind với release evidence.
- [ ] Trusted deployment credentials không lộ cho untrusted PR.
- [ ] Admission/cloud/runtime guardrails bổ trợ CI.
- [ ] Policy engine HA, versioned rollout và rollback.
- [ ] Rule errors có hướng sửa và owner.
- [ ] Policy updates cũng được test, review và audit.
- [ ] Feature flags/config changes có tracking/audit tương đương code.

### Triển khai và giám sát

- [ ] Canary/progressive rollout có health/SLO guardrails.
- [ ] Business invariants được kiểm riêng cho luồng quan trọng.
- [ ] Có đường rollback/fix-forward phù hợp database/data changes.
- [ ] Runtime drift được phát hiện và xử lý.
- [ ] Alerts phân biệt user impact và resource diagnostics.
- [ ] Incident ownership, runbook và escalation rõ.
- [ ] Release record liên kết commit, tests, policy, artifact và runtime.
- [ ] Evidence có integrity, retention và least privilege.

### Cải tiến liên tục

- [ ] Lead time và approval wait được đo trước/sau.
- [ ] Change failure rate, recovery time và SLO không xấu đi.
- [ ] Policy false positives được thu thập và khắc phục.
- [ ] Exceptions không tích lũy vô thời hạn.
- [ ] Developer feedback và onboarding time được theo dõi.
- [ ] Golden paths phù hợp các workload classes.
- [ ] Governance review dựa trên incident evidence và business risk.

## 44. Ghi nhớ cốt lõi

**Tự động hóa quản trị tốt không phải “không cần phê duyệt”, mà là “không cần phê duyệt lại bằng tay những điều đã có chính sách và bằng chứng kiểm chứng đáng tin”.** Hệ thống cần ranh giới rõ:

- Những thay đổi tiêu chuẩn đi qua golden path, tests, policy-as-code, trusted artifacts, progressive rollout và audit tự động.
- Những thay đổi nhạy cảm được định tuyến tới người có trách nhiệm, kèm đầy đủ impact analysis và evidence.
- Những vi phạm bắt buộc bị chặn, không thể hợp thức hóa chỉ bằng một nút approve.
- Những trường hợp đặc biệt có exception có thời hạn, compensating controls và quyền độc lập.
- Những tình huống khẩn cấp có break-glass/rollback path đã được chuẩn bị, không làm mất audit.
- Những kiểm soát tự động cũng phải được thử nghiệm, giám sát, triển khai có kiểm soát và cải tiến.

Mục tiêu cuối cùng là **thay hàng đợi approval bằng một hệ thống bảo đảm chất lượng và an toàn có thể lặp lại**, nơi developer đưa thay đổi nhỏ ra production nhanh hơn, Security có bằng chứng nhất quán hơn, và người dùng chịu ít sự cố hơn.