# Approval record trong Release Assurance: Hồ sơ phê duyệt phát hành có thể kiểm chứng

Một đội sản phẩm chuẩn bị triển khai phiên bản mới của dịch vụ thanh toán. Pipeline CI/CD hiển thị màu xanh; một quản lý nhắn trong nhóm chat “OK, release đi”. Sau đó, một lỗ hổng phân quyền xuất hiện ở production. Nhóm audit hỏi: **Ai đã phê duyệt đúng bản build được triển khai? Người duyệt đã nhìn thấy kết quả kiểm thử bảo mật nào? Ngoại lệ nào được chấp nhận? Quyết định có còn hiệu lực khi cấu hình và artifact thay đổi?** Một tin nhắn “OK” không tự trả lời được những câu hỏi này.

**Approval record** (hồ sơ phê duyệt) trong release assurance là **bản ghi có thể truy vết về một quyết định cho phép, từ chối hoặc yêu cầu bổ sung điều kiện trước khi một phiên bản phần mềm/cấu hình được phát hành tới phạm vi xác định**. Nó liên kết danh tính và thẩm quyền của người ra quyết định với **đúng release candidate, môi trường mục tiêu, các điều kiện kiểm soát, bằng chứng được review, rủi ro còn lại, thời hạn hiệu lực và dấu vết thay đổi quyết định**.

Trong chương **Release assurance** của module **SECURITY_SECURITY_ASSURANCE**, approval record không phải giấy chứng nhận “sản phẩm hoàn toàn an toàn”. Đây là một mắt xích của **security assurance dựa trên bằng chứng**, liên kết rủi ro và yêu cầu bảo mật với các security controls, kiểm thử, audit, remediation, release gates và giám sát sau phát hành. Một approval record tốt phải cho phép người khác tái dựng **đã quyết định điều gì, căn cứ vào đâu và giới hạn quyết định ở đâu**.

Sau bài học, người học có thể xây dựng approval record đúng phạm vi, phân quyền người duyệt, ràng buộc quyết định với artifact bất biến và kết quả kiểm thử, đánh giá GO/NO-GO, xử lý conditional release, tái phê duyệt khi thay đổi, bảo vệ dấu vết audit và sử dụng hồ sơ trong điều tra, kiểm toán và cải tiến quy trình phát hành.

## 1. Approval record thực chất chứng minh điều gì?

Approval record có giá trị khi làm rõ **quyết định quản trị** dựa trên trạng thái kỹ thuật đã được xác minh. Nó không thay thế kiểm thử, deployment log hay retest sau phát hành.

| Câu hỏi | Approval record có thể trả lời | Điều không tự chứng minh |
|---|---|---|
| Ai quyết định? | Approver identity, vai trò và quyền được ủy quyền tại mốc quyết định. | Người đó đã trực tiếp kiểm thử mọi tính năng. |
| Quyết định cho phép gì? | Phát hành artifact/revision cụ thể vào môi trường, nhóm người dùng và cửa sổ xác định. | Mọi phiên bản tương lai hoặc môi trường khác cũng được phép. |
| Tại sao quyết định được đưa ra? | Risk assessment, gate results, test references, exceptions và điều kiện. | Những bằng chứng nguồn chắc chắn đầy đủ nếu không được kiểm tra. |
| Quyết định có hiệu lực khi nào? | Thời điểm phê duyệt, thời gian hết hạn, điều kiện tái đánh giá. | Môi trường không drift sau thời điểm duyệt. |
| Việc gì xảy ra tiếp theo? | Gắn approval với deployment run, post-release verification và closure. | Deployment đã thành công chỉ vì được duyệt. |
| Có thể kiểm toán lại không? | Version history, actor, timestamp, event trail, bản evidence được xem. | Không còn rủi ro khai thác hoặc lỗi mới. |

**Phê duyệt hợp lệ** có nghĩa là chủ thể có quyền đã ra quyết định trong phạm vi quyền đó, dựa trên điều kiện và thông tin được yêu cầu. **Release assurance thành công** còn đòi artifact đúng, control gates đúng, deployment đúng mục tiêu và kết quả kiểm chứng sau release phù hợp.

### 1.1. Phân biệt ba tầng “được duyệt”

- **Design approval:** phương án kiến trúc/thay đổi được đánh giá phù hợp về mặt thiết kế.
- **Release approval:** release candidate và phạm vi phát hành cụ thể được phép thực thi.
- **Operational acceptance / post-release sign-off:** trạng thái sau triển khai đã được nghiệm thu theo các tiêu chí kỹ thuật/nghiệp vụ đã chốt.

Ba tầng có thể cùng một workflow hoặc là các hồ sơ liên kết, nhưng **không được suy từ design approval sang production release approval**, hoặc từ release approval sang post-deployment PASS.

## 2. Approval record khác release ticket, change record và risk acceptance như thế nào?

Các hệ thống GRC, DevOps và ITSM thường chứa nhiều đối tượng có tên tương tự.

| Hồ sơ | Trọng tâm | Quan hệ với approval record |
|---|---|---|
| **Release manifest** | Những package, image, cấu hình và tài liệu tạo nên một release. | Là đầu vào định danh thứ được duyệt. |
| **Build provenance / artifact attestation** | Nguồn, quá trình tạo, digest, người/công cụ ký khi có. | Hỗ trợ xác minh artifact là bản đã được kiểm tra. |
| **Security test report** | Kết quả kiểm thử, công cụ, scope, findings và giới hạn. | Là evidence được đánh giá, không tự là quyết định release. |
| **Change request/record** | Lý do thay đổi, hệ thống ảnh hưởng, lịch, triển khai và rollback. | Approval có thể nằm trong hoặc liên kết với change record. |
| **Release approval record** | Ai ra quyết định gì, trên release nào, tại sao, với điều kiện nào. | Bản ghi thẩm quyền và căn cứ của quyết định. |
| **Security exception** | Cho phép lệch khỏi một yêu cầu nội bộ theo scope, quyền và thời hạn. | Phải liên kết khi release có deviation; không thay thế approval phát hành. |
| **Risk acceptance** | Chủ thể có quyền chấp nhận residual risk trong giới hạn cụ thể. | Là một input/quyết định riêng; không chứng minh kiểm soát đã PASS. |
| **Deployment record** | Thực tế đã deploy artifact nào, ở đâu, lúc nào và kết quả. | Cần đối chiếu với approval để xác định execution đúng thẩm quyền. |
| **Post-release verification** | Kiểm tra security/functional/monitoring và rollback sau deployment. | Cung cấp hậu chứng, có thể làm phát sinh thu hồi/finding. |
| **Audit log** | Lịch sử thao tác tạo, sửa, phê duyệt, revoke và đọc hồ sơ. | Bảo vệ khả năng giải trình và truy vết. |

Một release có thể yêu cầu nhiều approval: security, business, change authority, data/privacy hoặc operator theo risk policy. Hệ thống nên ghi **mỗi quyết định riêng** và tạo kết quả tổng hợp theo quy tắc được duyệt; không nén thành một checkbox “Approved” mất thông tin.

## 3. Gắn quyết định với chính xác thứ sẽ được phát hành

Nguy cơ phổ biến là phê duyệt tên dễ thay đổi như “latest”, “main”, “release candidate hiện tại”, rồi triển khai một artifact đã thay sau review.

### 3.1. Release identity tối thiểu

| Thành phần | Ví dụ minh họa | Vì sao cần |
|---|---|---|
| **release_id** | REL-PAY-2026-014 | Định danh nghiệp vụ duy nhất của đợt phát hành. |
| **service/application** | payment-api | Xác định ứng dụng được phép thay. |
| **source_revision** | Git commit ID cố định | Ràng buộc mã nguồn được review. |
| **build_run_id** | CI build 8351 | Truy vết build workflow và kết quả. |
| **artifact_digest** | OCI image digest SHA-256 hoặc package checksum | Phân biệt binary khác dù cùng version tag. |
| **deployment_manifest/plan version** | Helm chart digest, IaC plan ID, config revision | Gắn cả cấu hình và hạ tầng với quyết định. |
| **target environment** | Production account/cluster/region xác định | Approval ở staging không tự áp dụng production. |
| **deployment scope** | Canary 5% → 25% → 100% theo điều kiện | Quyền rollout theo từng giai đoạn. |
| **approved window** | Khoảng UTC được quyết định | Không phát hành ngoài thời gian cho phép nếu policy giới hạn. |
| **recovery reference** | Known-good artifact, backup/rollback plan | Giúp đánh giá khả năng giảm thiểu tác động. |

Một service deploy bằng image có tag `v2.4` nhưng tag có thể bị ghi đè. Để chứng minh đã deploy đúng bản, cần đối chiếu **digest bất biến** hoặc cách định danh tương đương, cùng runtime attest/observed deployment. Chữ ký số của artifact giúp kiểm tra nguồn ký và toàn vẹn theo trust model nhưng **không tự chứng minh mã an toàn**.

### 3.2. Approval trên một tập artifact

Một release có thể gồm nhiều microservices, schema migration, feature flags và API gateway rules. Hồ sơ phải nêu rõ tập artifact được duyệt hoặc **release manifest có hash/version**, không chỉ tên service chính. Nếu database migration thay sau khi các thành phần khác được duyệt, cần xác định phê duyệt trước còn hợp lệ hay phải review lại.

### 3.3. Chống lỗi “đã test A nhưng deploy B”

~~~mermaid
flowchart LR
    SRC["Source revision A"] --> BUILD["Build run + artifact digest H"]
    BUILD --> TEST["Security/functional tests trên H"]
    TEST --> REVIEW["Approval record gắn H + manifest + scope"]
    REVIEW --> GATE{"Pre-deploy verification"}
    GATE -->|Khớp H, gates và quyền| DEP["Deploy đúng artifact"]
    GATE -->|Khác digest/revision/scope| STOP["NO-GO / yêu cầu đánh giá lại"]
    DEP --> OBS["Runtime evidence + hậu kiểm"]
~~~

Cần xem cả các **config thay đổi tại deploy-time**, secret references và target manifests. Artifact binary khớp digest nhưng deployment mở thêm cổng public ngoài scope duyệt vẫn có thể vi phạm điều kiện approval.

## 4. Yêu cầu bảo mật và risk context phải được nhìn thấy trong record

Quyết định phát hành phải liên hệ với **security objectives** và các điều kiện chấp nhận đã được tổ chức phê duyệt. Không đủ khi field “security reviewed” chỉ chứa một dấu tick không có tiêu chí.

### 4.1. Những nguồn cần map

- **Business/security objective:** bảo vệ dữ liệu khách hàng, đảm bảo thanh toán chính xác, duy trì auditability.
- **Threat model và risk register:** kịch bản lạm dụng quyền, truy xuất trái phép, mất dữ liệu, supply-chain compromise.
- **Requirements và controls:** IAM, encryption, secrets, input validation, logging, monitoring, backup, hardening, release gates.
- **Findings và remediation:** lỗ hổng còn mở, ticket sửa, retest kết quả và risk exceptions.
- **Data/privacy/legal context:** loại dữ liệu, retention, chuyển vùng, nhà cung cấp và nghĩa vụ thông báo nếu có.
- **Operational readiness:** SLO, rollback, on-call, incident runbook, monitoring.
- **Change impact:** phạm vi mới, dependency và thay đổi so với release trước.

### 4.2. Approval record cần có “warrant”

Một warrant (cơ sở suy luận) của quyết định GO có thể diễn đạt:

> Nếu release candidate được định danh bất biến, phạm vi triển khai và phụ thuộc được chốt, tất cả gate bắt buộc có evidence đủ độ tin cậy, residual risk còn lại nằm trong thẩm quyền được chấp nhận và có phương án kiểm chứng/khôi phục phù hợp, thì hội đồng có cơ sở phê duyệt phát hành **trong phạm vi và điều kiện đã xác định**.

Lập luận này có thể **bị phá vỡ** nếu release artifact đổi, xuất hiện critical finding mới, mất khả năng rollback, mở rộng region hoặc SOC không còn giám sát. Vì vậy record phải ghi rõ các **reapproval/stop triggers**.

## 5. Thành phần bắt buộc của một Approval record có thể kiểm toán

Một record chất lượng nên gồm các nhóm trường sau.

| Nhóm | Các trường đề xuất | Câu hỏi auditor có thể trả lời |
|---|---|---|
| **Identity** | approval_id, release_id, decision_version, created_at, source system | Quyết định nào đang được xem và có bản nào trước đó? |
| **Subject** | artifact digest, source revision, build ID, deployment manifest, service | Phê duyệt đúng mã, binary và cấu hình nào? |
| **Scope** | environment, account, region, cluster, users, rollout stage, time window | Quyết định được phép áp dụng ở đâu và tới ai? |
| **Purpose** | change reason, security objective, change/risk/finding IDs | Vì sao phát hành và mục tiêu nào bị ảnh hưởng? |
| **Gate snapshot** | required gates, test outcomes, evidence IDs, exceptions | Điều kiện nào được kiểm chứng tại lúc duyệt? |
| **Residual risk** | risk rating, source obligations, risk owner decision, limitations | Rủi ro nào còn được cho phép và quyền của ai? |
| **Approvers** | principal ID, role, authority basis, signature/ack, timestamp | Ai duyệt, có thẩm quyền và độc lập phù hợp không? |
| **Decision** | GO/NO-GO/CONDITIONAL_GO/PENDING, rationale, exact conditions | Được làm gì và không được làm gì? |
| **Validity** | effective_from, expires_at, superseded_by, revoke triggers | Khi nào quyết định không còn dùng được? |
| **Execution linkage** | deployment run IDs, observed digest, target IDs | Triển khai thực có khớp với quyết định không? |
| **Post-release gates** | smoke/security tests, monitoring criteria, rollback thresholds | Kiểm chứng kết quả và phản ứng sai lệch thế nào? |
| **Governance** | audit trail, change history, retention, classification | Dấu vết có thể tái dựng và được bảo vệ không? |

Mỗi nhóm quan trọng có thể là trường trực tiếp hoặc đường dẫn tham chiếu trong công cụ GRC/ITSM; điều cần bảo toàn là **tính ổn định của ID, phiên bản và bằng chứng**. Không nhất thiết nhồi log nhạy cảm vào ticket rộng quyền.

### 5.1. Viết decision rationale như một lập luận

**Yếu:** “Security team approved.”

**Tốt hơn:** “Đã đối chiếu image digest H với bản SAST/SCA/DAST và policy-gate runs được duyệt; các findings thuộc threshold bắt buộc đã khắc phục và retest; backup/rollback prerequisites đạt; rollout canary cho account/region chỉ định được phép từ T1 đến T2. Ngoại lệ EX-17 cho logging feature phụ chưa đạt vẫn còn hạn và được giám sát; nếu synthetic audit check thất bại hoặc runtime digest đổi, tạm dừng rollout và xin quyết định mới.”

Ví dụ minh họa này cho thấy **điều kiện, phạm vi và phản chứng**, không chỉ vai trò người duyệt.

## 6. Quy trình tạo và hoàn thiện Approval record

~~~mermaid
flowchart TD
    A["Release candidate + manifest được chốt"] --> B["Thu evidence từ CI/CD, security, change, risk"]
    B --> C["Validate scope, nguồn, freshness, digest và test coverage"]
    C --> D{"Các release gates bắt buộc đạt?"}
    D -->|Không| E["NO-GO / PENDING: findings, gap, replan"]
    D -->|Có| F["Review residual risk + ngoại lệ + nghĩa vụ"]
    F --> G{"Đúng thẩm quyền và điều kiện?"}
    G -->|Không| E
    G -->|Có| H["Ghi approvals + decision rationale + validity"]
    H --> I["Pre-deploy revalidation: artifact/scope/freshness"]
    I --> J{"Quyết định còn hợp lệ?"}
    J -->|Không| E
    J -->|Có| K["Triển khai + lưu execution evidence"]
    K --> L["Post-release verification + monitoring"]
    L --> M{"Đạt tiêu chí?"}
    M -->|Không| N["Containment/rollback, incident, finding, revoke"]
    M -->|Có| O["Operational acceptance + closure"]
~~~

### Bước 1 — Chốt release candidate

Có bản candidate duy nhất, source commit, build run, artifact digest, manifests và dependencies. Nếu còn dự kiến thay code, record ở trạng thái **DRAFT**; không phê duyệt một đối tượng chưa biết chính xác.

### Bước 2 — Thu evidence tương xứng rủi ro

Các team cung cấp kết quả kiểm thử, threat/risk review, inventory, open findings, exceptions, dữ liệu rollback và readiness. Tập evidence phải nói rõ **được chạy trên phiên bản nào, phạm vi và thời điểm nào**.

### Bước 3 — Kiểm tra quality và completeness

Đối chiếu test runs với artifact, environment và scope; kiểm tra các job SKIPPED, failed-to-run hoặc permission errors. Kết quả “0 critical findings” từ scanner thiếu credential không đủ để kết luận artifact sạch. Khi thiếu bằng chứng, ghi **INCONCLUSIVE** thay vì PASS.

### Bước 4 — Tạo quyết định có thẩm quyền

Phân tách technical reviewer, người chấp nhận residual risk và người phê duyệt phát hành theo RACI. Lưu danh tính/timestamp, phiên bản nội dung đã xem và điều kiện. Approval chỉ có hiệu lực theo policy.

### Bước 5 — Kiểm tra lại ngay trước execution

Xác minh artifact digest, environment, gate freshness, status ngoại lệ, cửa sổ và các thay đổi rủi ro mới. Nếu một condition sai, dừng hoặc xin lại approval.

### Bước 6 — Gắn deployment và verification

Ghi deployment run, version thực tế, rollout stages và post-release tests. Một hồ sơ GO có thể đúng tại lúc quyết định nhưng triển khai **FAIL**; không sửa lại quyết định lịch sử để che lỗi, mà bổ sung execution outcome và finding.

## 7. Định nghĩa release gates và evidence cho từng gate

Approval record chỉ đáng tin nếu các gate bắt buộc được định nghĩa rõ trước khi quyết định.

| Gate minh họa | Acceptance criteria | Evidence cần liên kết |
|---|---|---|
| **G1 — Artifact identity** | Artifact/manifest và source revision được review đúng bản deploy. | Build provenance, digest, artifact registry, PR/source review. |
| **G2 — Security findings** | Findings phải xử lý theo policy hoặc có quyết định ngoại lệ hợp lệ nếu được phép. | SAST/SCA/container/DAST reports, triage, remediation/retest, exceptions. |
| **G3 — Functional integrity** | Business-critical flows và regression tests đạt. | Integration/e2e tests, contract tests, smoke tests. |
| **G4 — IAM/data protection** | Không có quyền mới ngoài scope; bí mật và dữ liệu được bảo vệ. | Effective IAM diffs, secret scans, encryption/permissions checks. |
| **G5 — Deployment safety** | Rollout staged, rollback/forward-fix readiness và runbook rõ. | Change plan, recovery rehearsal, target readiness, on-call. |
| **G6 — Observability/IR** | Audit logging, detection và alerting đủ để giám sát release. | Synthetic logs, SIEM ingest, alert routing và response test. |
| **G7 — Risk & obligations** | Residual risk được đánh giá, nghĩa vụ bắt buộc được xử lý phù hợp. | Risk record, legal/compliance review nếu cần, accepted exceptions. |
| **G8 — Approver authority** | Required approvers còn quyền, không có conflict bị cấm. | Authority matrix, role snapshot, identity/audit record. |
| **G9 — Post-release verification** | Tiêu chí thành công/dừng/rollback và người trực được xác định. | Validation script, thresholds, maintenance window, escalation route. |

Không có “danh sách gate chuẩn cho mọi release”. Một thay đổi tài liệu đơn giản khác với migration dữ liệu khách hàng nhạy cảm. Nhưng **một gate được xác định là bắt buộc thì không được coi là đạt chỉ bằng sự vắng mặt của lỗi được quan sát**.

### 7.1. Trạng thái gate và trạng thái quyết định là hai trục khác nhau

- **Gate PASS:** có evidence đủ tin cậy, đúng scope/phiên bản chứng minh điều kiện đạt.
- **Gate FAIL:** test/evidence cho thấy yêu cầu không đạt.
- **Gate INCONCLUSIVE:** chưa đủ bằng chứng hoặc môi trường không cho phép suy ra kết luận.
- **Gate NOT_APPLICABLE:** có căn cứ rằng điều kiện không áp dụng; được xác nhận đúng quyền.
- **Decision GO/NO-GO:** kết luận cho phép hay không cho phép release, dựa trên gates và thẩm quyền.

Một gate FAIL về security control có thể dẫn đến NO-GO. Nếu nguồn yêu cầu cho phép exception với điều kiện chặt, hồ sơ có thể ghi **conditional release** sau khi ngoại lệ được quản trị hợp lệ. Không dùng approval để đổi trạng thái FAIL thành PASS.

## 8. Phân quyền phê duyệt và Segregation of Duties

Một release có thể chịu áp lực deadline, doanh thu hoặc khắc phục sự cố. Quy trình cần xác định quyền quyết định mà không coi mỗi chữ ký của cấp quản lý là thay thế cho đánh giá kỹ thuật.

| Vai trò | Chịu trách nhiệm gì? | Không nên tự ý làm gì? |
|---|---|---|
| **Release Owner/Manager** | Tập hợp candidate, tài liệu và plan, điều phối review/rollout. | Tự chứng nhận tất cả security gates khi thiếu quyền. |
| **Engineering/QA** | Chạy/đánh giá functional, integration và regressions. | Sửa test result hoặc bỏ test fail mà không có lịch sử. |
| **Security Assessor** | Xác minh security tests, vulnerabilities, control impact và evidence quality. | Thay business risk owner chấp nhận rủi ro vượt thẩm quyền. |
| **Control Owner** | Diễn giải yêu cầu và acceptance criteria của control. | Miễn nghĩa vụ pháp lý/hợp đồng bên ngoài quyền của mình. |
| **Business/Data Risk Owner** | Chấp nhận rủi ro trong phạm vi ủy quyền; đánh giá impact. | Gọi một control chưa đạt là PASS để thuận tiện release. |
| **Change Authority/CAB** | Cho phép thời gian, phương thức, scope triển khai theo chính sách. | Bỏ qua mandatory security/legal gates nếu không có cơ chế hợp lệ. |
| **Legal/Compliance/Privacy** | Kiểm tra nghĩa vụ bên ngoài và quyền thay đổi điều kiện. | Tự kết luận runtime an toàn mà không có evidence kỹ thuật. |
| **Operations/SRE** | Kiểm tra observability, on-call, rollback/DR và runtime readiness. | Triển khai artifact khác bản đã duyệt mà không xét reapproval. |
| **Independent Reviewer/Audit** | Thẩm định tính đầy đủ, trung thực và khả năng truy vết. | Trở thành người duyệt release nếu điều đó gây xung đột vai trò. |

### 8.1. Authority matrix nên dựa trên rủi ro

Tổ chức có thể phân cấp phê duyệt theo mức ảnh hưởng: standard/low-risk có mô hình approval lặp lại, normal cần security/change review, high-risk đòi business risk owner cùng security assurance, privacy-sensitive cần tham vấn chuyên môn, emergency có incident commander. **Tên chức danh và ngưỡng cụ thể phải do tổ chức ban hành**.

### 8.2. Tránh self-approval nguy hiểm

Khi kỹ sư có quyền merge code đồng thời có quyền sửa kết quả scanner, tự phê duyệt release và xóa audit trail, hồ sơ khó có giá trị assurance. Cần tách chức năng, ít nhất ở những control trọng yếu; nếu tổ chức nhỏ không thể tách hoàn toàn, thiết lập reviewer chéo, dấu vết bất biến, giới hạn quyền và review sau triển khai tương xứng.

### 8.3. Xác minh thẩm quyền tại thời điểm duyệt

Một người từng có vai trò Security Lead nhưng đã chuyển bộ phận không mặc nhiên có quyền duyệt production. Approval record nên tham chiếu **effective authority tại timestamp**, nhóm role hoặc ma trận phân quyền được áp dụng. Không chỉ lưu tên hiển thị có thể trùng hoặc đổi.

## 9. Quyết định GO, NO-GO và Conditional GO

### 9.1. GO

Quyết định **GO** chỉ hợp lệ khi tất cả gates bắt buộc đã đáp ứng theo chính sách, thông tin còn đủ mới, người duyệt đúng quyền và điều kiện vận hành sẵn sàng. GO có thể giới hạn riêng một **stage**, account, region hoặc cohort; không tự cho phép full rollout.

### 9.2. NO-GO

**NO-GO** là một kết quả assurance có giá trị khi evidence cho thấy rủi ro chưa được xử lý, không có khả năng rollback, thiếu approval hoặc chưa đủ dữ liệu. NO-GO cần có reason codes và việc phải hoàn thành trước khi xem xét lại; tránh “Security không đồng ý” mà không có tiêu chí.

### 9.3. Conditional GO

**Conditional GO** là quyết định cho phép phát hành **khi những điều kiện đã xác định được đáp ứng và cơ chế governance cho phép**. Ví dụ chỉ canary 5%, có on-call, logging đầy đủ và rollback trigger, không tự mở rộng lên 100%. Nếu policy bắt buộc hoàn tất một security gate trước production và không cho waiver, không được tạo Conditional GO để vượt rào.

Có thể tách các trạng thái:

| Trạng thái | Ý nghĩa | Có quyền deploy? |
|---|---|---|
| **DRAFT** | Hồ sơ chưa hoàn chỉnh. | Không. |
| **UNDER_REVIEW** | Đang review evidence và thẩm quyền. | Không mặc định. |
| **NEEDS_EVIDENCE** | Thiếu test/scope/authorization. | Không. |
| **APPROVED_GO** | Đủ điều kiện release trên scope và thời hạn. | Có, khi revalidation ngay trước deploy PASS. |
| **APPROVED_CONDITIONAL** | Chỉ được release theo điều kiện có quyền. | Có trong phần điều kiện đã đạt và đúng phạm vi. |
| **REJECTED_NO_GO** | Không đủ điều kiện hoặc không được cho phép. | Không. |
| **EXPIRED** | Hết thời gian cho phép hoặc điều kiện hiệu lực. | Không có quyền từ quyết định này. |
| **REVOKED** | Quyết định bị thu hồi vì lỗi/rủi ro/drift. | Không. |
| **SUPERSEDED** | Có bản phê duyệt mới thay thế. | Chỉ dùng bản mới có hiệu lực. |
| **EXECUTED** | Đã liên kết deployment thực tế. | Không tự có nghĩa post-release PASS. |

### 9.4. Risk acceptance là hồ sơ khác

Nếu một lỗ hổng high severity còn mở và người có thẩm quyền chấp nhận tạm, record phải tham chiếu **risk decision và exception còn hiệu lực** đúng điều kiện. Approval phát hành không tự miễn yêu cầu hợp đồng/luật hoặc cho phép lách kiểm soát chương trình chứng nhận có quy tắc riêng.

## 10. Bằng chứng nguồn và tính đầy đủ của review

Approval record chỉ mạnh bằng tập evidence mà nó đã dựa vào. Một bảng tổng hợp “All checks green” có thể không trung thực nếu scanner bỏ qua microservice hoặc pipeline fail nhưng báo thành success.

### 10.1. Thu thập artifact theo evidence chain

~~~text
Control / Requirement ID
   -> Release gate criterion
   -> Test method / tool version / scope
   -> Raw result and normalized report
   -> Evidence ID / digest / storage version
   -> Reviewer interpretation + limitations
   -> Approval decision + conditions
   -> Deployment + post-change verification
~~~

Các artifact cần có **event time, collected time, collector identity, source locator, target revision, tool version, scope/population, filters, errors, integrity metadata và lưu trữ** phù hợp.

### 10.2. Các câu hỏi chất lượng bằng chứng

- **Relevance:** báo cáo quét có kiểm tra đúng công nghệ và attack paths của release?
- **Completeness:** có bỏ account, region, container, dependency hoặc test job nào?
- **Authenticity:** nguồn tạo có xác thực, artifact có đúng từ pipeline được phép?
- **Integrity:** file hoặc bản report có thay đổi sau thu thập không?
- **Timeliness:** còn áp dụng cho commit, artifact, cấu hình và threat hiện tại?
- **Reproducibility:** có thể chạy lại test với cùng input/version/scope?
- **Independence:** reviewer có thể xác minh mà không phụ thuộc hoàn toàn người sửa code?
- **Confidentiality:** artifact chứa PII/secrets có được bảo vệ và chỉ gửi người cần biết?

Một hash giúp phát hiện dữ liệu thay đổi sau mốc được tin cậy; **hash không chứng minh scanner đã kiểm tra đủ hoặc dữ liệu nguồn trước lúc băm là đúng**. Một chữ ký số phù hợp chứng minh kiểm tra nguồn ký theo trust model, không mặc nhiên chứng minh decision có nội dung hợp lệ.

## 11. Dấu vết phê duyệt: Identity, timestamp, signature và audit trail

Approval record có thể lưu trong ITSM, GRC, GitOps policy repository hoặc hệ thống release management. Dù ở đâu, cần giảm khả năng chỉnh sửa lặng lẽ những thông tin quyết định.

### 11.1. Bản ghi tối thiểu cho từng approver

| Trường | Mục tiêu |
|---|---|
| approver_principal_id | Định danh ổn định, không chỉ tên hiển thị. |
| role_at_decision | Vai trò/thẩm quyền tại đúng thời điểm. |
| decision | APPROVE/REJECT/REQUEST_CHANGES/ABSTAIN. |
| decision_at_utc | Thời gian UTC/offset chính xác. |
| approved_subject_digest | Bản manifest/revision được quyết định. |
| reviewed_evidence_snapshot | Các evidence/test IDs và version đã được xem. |
| conditions_and_rationale | Điều kiện, rủi ro, giới hạn và lý do. |
| authentication/attestation | Cơ chế xác thực hành động ký/duyệt. |
| audit_event_id | Đường truy vết đến log hành động. |

### 11.2. Khi nào chữ ký có giá trị?

Click “Approve” trong ứng dụng được xác thực có thể đủ theo chính sách nội bộ; với rủi ro cao hoặc yêu cầu pháp lý, có thể cần ký điện tử/chữ ký số theo cơ chế được công nhận và kiểm soát khóa. Không tự tuyên bố “có chữ ký số thì không thể chối bỏ” trong mọi trường hợp; giá trị pháp lý, xác thực danh tính, quản lý khóa và tính toàn vẹn phụ thuộc quy định và trust model.

### 11.3. Bảo vệ lịch sử quyết định

Không nên cho người có quyền thay đổi artifact cũng có thể xóa mọi log duyệt. Áp dụng RBAC, phân tách quyền, versioning, audit append-only hoặc cơ chế bất biến phù hợp. Khi quyết định bị đổi, **giữ bản cũ và thêm bản mới** thay vì ghi đè “approved_by”.

## 12. Approval validity, expiration, reapproval và revocation

Đây là nguồn lỗi lớn trong phát hành nhanh: một approval đúng lúc 10:00 có thể không còn đủ căn cứ lúc 18:00.

### 12.1. Những sự kiện buộc xét lại

- **Artifact đổi:** source commit, image digest, package list hoặc database migration khác bản được duyệt.
- **Config/manifest đổi:** firewall, IAM, feature flags, secret references, chart values tác động phạm vi.
- **Scope tăng:** từ canary sang full rollout, thêm customer cohort, region, account hoặc dữ liệu.
- **Test hết hiệu lực:** scanner/policy/test result không còn đại diện sau thay đổi.
- **New critical finding:** có lỗ hổng mới, exploit đang diễn ra hoặc incident liên quan.
- **Control bị mất:** audit logging, backup, on-call, rollback path hoặc compensating control không hoạt động.
- **Risk/exception đổi:** ngoại lệ hết hạn, residual risk vượt quyền cho phép, source obligation thay đổi.
- **Time window hết:** change thực hiện ngoài cửa sổ duyệt hoặc approver/owner không còn đúng điều kiện.
- **Supply chain integrity fail:** artifact registry mismatch, signer bị thu hồi, build provenance không xác minh được.

### 12.2. Quy tắc so sánh trước triển khai

~~~text
release.approval.manifest_digest == deployment.target_manifest_digest
AND environment IN approval.allowed_environments
AND rollout_scope WITHIN approval.allowed_scope
AND current_time WITHIN approval.validity_window
AND required_gates STILL_VALID
AND approval.authority_valid
AND no_blocking_findings_or_revocation
=> MAY_EXECUTE_UNDER_APPROVED_RUNBOOK
ELSE
=> STOP_OR_REASSESS_PER_POLICY
~~~

Đoạn trên mô tả logic quản trị, không phải mã có thể thực thi trực tiếp. Trong thực tế cần kiểm tra cả **atomicity/race condition**: giữa lúc check gate và lúc deploy, artifact/target có thể đổi; nên dùng version lock, signed manifest và runtime checks để hạn chế TOCTOU (*time-of-check to time-of-use*).

### 12.3. Reapproval phải lưu khác biệt

Nếu release candidate B chỉ sửa một mô tả nhỏ so với A, policy có thể cho review rút gọn. Nhưng record vẫn phải lưu **diff, người quyết định không cần full retest, lý do và bằng chứng rằng thay đổi không ảnh hưởng control liên quan**. Không mặc định mọi sửa nhỏ đều vô hại; một thay đổi cấu hình một dòng có thể mở Internet exposure.

### 12.4. Revocation không xóa sự thật lịch sử

Nếu release đã GO và triển khai rồi bị phát hiện sai, ghi **revoked_at, actor, reason, action/incident ID**; giữ bản duyệt ban đầu để phân tích vì sao điều kiện bị vượt qua. Rollback/containment cần có runbook riêng, không chỉ đổi một field trong approval.

## 13. Nhiều approval và quy tắc tổng hợp

Một release có thể có bốn luồng quyết định: Engineering, Security, Business và Change Authority. Việc **hai trong bốn người duyệt** không nhất thiết cho phép release; mỗi gate có thể có tính bắt buộc khác nhau.

### 13.1. Mô hình tổng hợp minh họa

~~~text
Required:
  Engineering QA sign-off = PASS
  Security gates = PASS (hoặc exception hợp lệ nếu policy cho phép)
  Change Authority = APPROVE
  Business Owner = APPROVE cho release high-impact
Optional/conditional:
  Privacy/Legal = required nếu có thay đổi data processing
  DR/SRE = required nếu thay đổi recovery critical path

Overall decision:
  GO khi mọi required condition được thỏa
  NO-GO khi có blocking failure
  NEEDS_EVIDENCE khi chưa xác định trạng thái bắt buộc
~~~

Không dùng công thức “đa số phiếu” nếu policy yêu cầu một veto hoặc một approval đặc biệt. Ngược lại, không thêm gate hành chính không cần thiết khiến hotfix khẩn bị trì hoãn; thiết kế luồng phù hợp rủi ro.

### 13.2. Reviewer có thể nêu dissent

Một security reviewer có thể ghi rõ objection/limitation dù business owner có quyền quyết định trong phạm vi được phép. Record nên giữ ý kiến và risk rationale; không xóa phản đối để tạo ấn tượng đồng thuận. Với nghĩa vụ bên ngoài không được waived, risk owner nội bộ **không có quyền biến vi phạm thành được phép**.

### 13.3. Không được tự động nhận ủy quyền vô thời hạn

Nếu approver vắng mặt, phải dùng delegation có hiệu lực, scope, expiry và người được ủy quyền; không sao chép token hoặc cho bot ký thay người ngoài quyền. Tự động hóa chuẩn có thể phát quyết định dựa trên **policy đã được phê duyệt**, cùng nguồn định nghĩa và audit về automation identity.

## 14. Conditional release, exceptions và residual risk

Một bản phát hành có thể chưa đáp ứng mọi security gate nhưng tổ chức có trường hợp cần vận hành hạn chế. Chỉ có thể xét khi **nguồn yêu cầu và thẩm quyền cho phép**, và record phải minh bạch.

| Nội dung | Yêu cầu |
|---|---|
| **Deviated control** | Requirement/control ID, nguồn, tiêu chí chưa đạt. |
| **Finding** | Bằng chứng cho thấy điều gì chưa đạt, asset và time window. |
| **Risk scenario** | Đường tấn công, dữ liệu, impact, exposure, residual risk. |
| **Compensating control** | Biện pháp đã triển khai và test, limitations, monitoring. |
| **Exception authority** | Chủ thể có quyền cho phép lệch và thẩm quyền riêng của release approver. |
| **Conditions** | Canary fraction, feature flag, data class, network isolation, on-call, rollback triggers. |
| **Expiry/reassessment** | Ngày hết hạn, milestone fix, sự kiện buộc dừng/đánh giá lại. |
| **Communication** | Ai phải được thông báo, đặc biệt khi có nghĩa vụ với khách hàng/bên thứ ba. |

**Ví dụ:** một tính năng nội bộ rủi ro thấp chưa hoàn tất performance test được release canary giới hạn, với monitoring chặt và mốc test bổ sung nếu chính sách cho phép. **Phản ví dụ:** một lỗi authorization đang cho phép đọc dữ liệu khách hàng ngoài quyền không thể được coi “PASS về bảo mật” chỉ vì có chữ ký chấp nhận rủi ro. Nếu luật/hợp đồng không cho phép, phải xử lý theo cơ chế phù hợp hoặc NO-GO.

### 14.1. Khi nào phải nói NO-GO dù có risk acceptance?

Nếu một security requirement bắt buộc không được phép miễn, người ký không có thẩm quyền, thẩm định dữ liệu chưa hoàn tất hoặc control bù trừ thất bại, record không thể đưa ra GO hợp lệ. Có thể chọn thay đổi thiết kế, thu hẹp phạm vi, dừng chức năng hoặc xử lý thỏa thuận bên ngoài trước khi xét lại.

## 15. Approval record cho Standard, Normal và Emergency releases

### 15.1. Standard release

Một release ít rủi ro lặp lại có thể được phép theo **pre-approved release model**: quy trình, versioned gates, rollout hạn chế và automation identity. Record của từng lần phát hành vẫn cần chỉ rõ artifact, scope, test runs, mô hình phê duyệt được áp dụng và kết quả kiểm tra; không dùng “standard” để miễn mọi dấu vết.

### 15.2. Normal release

Có review theo risk tier, approval từ các vai trò được yêu cầu, cửa sổ triển khai, test và rollback plan. Record nên gắn vào change ticket và evidence package của đúng candidate.

### 15.3. Emergency release/hotfix

Khi cần khắc phục lỗ hổng đang bị khai thác hoặc incident đang diễn ra, thời gian là yếu tố an toàn. Một workflow khẩn có thể **rút gọn bằng chứng trước deploy**, nhưng phải có **trigger, quyền khẩn, phạm vi tối thiểu, risk rationale, test thiết yếu, monitoring, recording và hậu kiểm**. Không được backdate phê duyệt để làm như đủ gates đã chạy.

~~~mermaid
flowchart TD
    INC["Incident/emergency trigger"] --> AUTH["Thẩm quyền khẩn xác nhận scope + urgency"]
    AUTH --> MIN["Minimum viable security evidence và an toàn triển khai"]
    MIN --> DEC{"Cho phép hotfix?"}
    DEC -->|Không| ALT["Containment thay thế, xử lý blocker"]
    DEC -->|Có| DEP["Deploy hạn chế + audit events + stop triggers"]
    DEP --> VERIFY["Kiểm tra hiệu lực fix và tác động"]
    VERIFY --> REVIEW["Retrospective approval review + bổ sung evidence"]
    REVIEW --> RCA["Finding, root cause và cải tiến release model"]
~~~

Một hotfix an ninh không tự bảo đảm an toàn nếu chưa biết nó phá production IAM, mã hóa, log hay khả năng phục hồi. Thủ tục emergency cân bằng **rủi ro trì hoãn** với **rủi ro triển khai**, thay vì yêu cầu “mọi tài liệu phải đủ trước khi cô lập tấn công”.

## 16. Approval record trong pipeline CI/CD và GitOps

Công cụ CI/CD có thể kiểm tra tự động các điều kiện trước khi chấp nhận deployment. Tuy nhiên, automation cần rõ **ai ban hành policy và bot thực thi theo quyền nào**.

### 16.1. Các tầng kiểm soát

1. **Source control:** branch protection, peer review, signed changes khi cần, change ownership.
2. **Build:** workflow được bảo vệ, build provenance, artifact digest và registry access.
3. **Security/QA tests:** SAST, SCA, container, IaC, functional và negative tests tương xứng; không che SKIP/ERROR.
4. **Policy gate:** xác minh requirement mapping, exceptions có hiệu lực và required security review.
5. **Approval gate:** human decision hoặc policy-automation decision đúng thẩm quyền.
6. **Pre-deploy attestation:** so digest, environment, rollout stage và thời hạn hiệu lực.
7. **Deployment control:** service account chỉ được triển khai artifact đã được ủy quyền tới target.
8. **Post-release monitoring:** smoke/security checks, drift, SLO, rollback và incident response.

### 16.2. Record cần lưu version policy

Nếu gate dùng rule `security-release-policy-v5`, nên lưu policy version và hash/commit để auditor biết **điều kiện nào được áp dụng lúc phê duyệt**. Một thay đổi policy ngày hôm sau không tự thay đổi tính hợp lệ lịch sử, nhưng có thể làm phát sinh yêu cầu đánh giá lại những release còn hoạt động.

### 16.3. Không coi bot “APPROVED” như chữ ký người dùng

Một automated decision phải chỉ rõ service identity, evaluation inputs, policy ID/version, rule outcomes, thời gian và người có quyền thay policy. Không ghi `approved_by: Security Team` nếu thực chất do một bot quyết định; điều đó che accountability. Ngược lại, một người click approve có thể xác nhận policy output nhưng vẫn cần review rõ căn cứ.

## 17. Multi-stage rollout: Approval theo phạm vi và từng giai đoạn

Canary, blue/green, ring deployment và progressive delivery giúp giảm blast radius, nhưng **phê duyệt cho canary không tự cho phép full rollout**.

| Stage | Quyết định và evidence cần có | Trigger dừng |
|---|---|---|
| **Staging readiness** | Tests và artifact identity phù hợp, không suy trực tiếp production. | Security/functional test fail; artifact khác. |
| **Canary 1–5%** | Scope nhỏ được phê duyệt, on-call, baseline và metrics so sánh. | Auth/permission regression, dữ liệu sai, alert pipeline mất. |
| **Partial rollout** | Canary nghiệm thu, business/error/security metrics đạt; quyền mở rộng được xác minh. | Drift, critical finding, signal vượt ngưỡng. |
| **Full rollout** | Gate mở rộng theo policy, data consistency và capacity chứng minh. | Bất kỳ blocking condition mới theo risk policy. |
| **Operational acceptance** | Bản thực chạy đúng digest/scope, audit/monitoring và rollback state rõ. | Không tái lập được evidence hoặc còn lỗi critical. |

### 17.1. Gate mở rộng dựa trên bằng chứng mới

Mẫu: Approval A cho phép canary 5% trong 30 phút. Khi quan sát đạt và nhận đủ chứng cứ, Approval B hoặc automated gate theo chính sách cho phép 25%; Approval C cho full rollout. Có thể đặt toàn bộ lộ trình trong một quyết định ban đầu nếu **điều kiện chuyển stage đã được phê duyệt rõ và được xác minh tự động**, không nhất thiết mỗi lần mở rộng đều cần người click mới.

### 17.2. Scope theo tenant và dữ liệu

Một SaaS phục vụ nhiều khách hàng có thể rollout theo tenant/tier/region. Nếu release làm thay đổi nơi xử lý dữ liệu, loại subprocessor hay quyền truy xuất, cần kiểm tra nghĩa vụ ngoài kỹ thuật; một tenant đã đồng ý thử beta không tự suy ra mọi tenant đã chấp thuận điều kiện xử lý dữ liệu mới.

## 18. Mẫu Approval record dạng YAML

Mẫu sau **chỉ phục vụ học tập** và là ví dụ một release **chưa được chấp thuận** do còn thiếu bằng chứng. Đây không phải schema chuẩn của công cụ release, GRC hoặc chữ ký điện tử. Các ID, dữ liệu, thời gian và kết quả là giả định.

~~~yaml
release_approval:
  approval_id: "REL-APPROVAL-EXAMPLE-006"
  record_version: "1.0"
  service_name: "SECURITY_SECURITY_ASSURANCE"
  release_id: "REL-PAYMENT-EXAMPLE-014"
  lifecycle_state: "NEEDS_EVIDENCE"
  created_at_utc: "2026-11-28T04:00:00Z"
  owner: "Payment Release Owner"

subject:
  application: "payment-api"
  source_revision: "commit-example-5f7a10"
  build_run_id: "ci-build-8351"
  artifact:
    name: "payment-api-image"
    digest_algorithm: "SHA-256"
    digest_reference: "restricted/release-006/digests/image"
  manifest:
    version: "helm-manifest-rev-4"
    digest_reference: "restricted/release-006/digests/manifest"
  database_migration: "migration-example-023"
  environment: "production"
  allowed_accounts: ["prod-account-a"]
  allowed_regions: ["region-a"]
  requested_rollout: "canary-5-percent"
  requested_window_utc:
    start: "2026-11-28T07:00:00Z"
    end: "2026-11-28T08:00:00Z"

context:
  objective: "Release authorization fix without exposing other tenant data"
  control_ids:
    - "IAM-ACCESS-EXAMPLE-01"
    - "RELEASE-GATE-EXAMPLE-02"
  original_finding_id: "FINDING-AUTH-EXAMPLE-014"
  change_id: "CHANGE-EXAMPLE-1042"
  risk_assessment_id: "RISK-RELEASE-EXAMPLE-014"
  security_exception_ids: []

evidence_snapshot:
  collected_at_utc: "2026-11-28T05:00:00Z"
  inventory_reference: "restricted/release-006/asset-inventory"
  artifact_provenance: "restricted/release-006/build-provenance"
  security_test_runs:
    - "sast-run-813"
    - "sca-run-814"
    - "auth-negative-test-run-815"
  qa_test_runs:
    - "integration-run-816"
  rollback_plan: "restricted/release-006/rollback-plan-v2"
  release_manifest: "restricted/release-006/manifest-rev-4"

gates:
  - id: "G1-ARTIFACT-INTEGRITY"
    verdict: "PASS"
    evidence: "restricted/release-006/digest-match"
  - id: "G2-SECURITY-TESTS"
    verdict: "PASS"
    evidence: "restricted/release-006/security-tests-summary"
  - id: "G3-DATA-INTEGRITY"
    verdict: "INCONCLUSIVE"
    evidence: "restricted/release-006/migration-review"
    limitation: "Production-like migration rollback not verified"
  - id: "G4-OBSERVABILITY"
    verdict: "INCONCLUSIVE"
    evidence: null
    limitation: "New audit event not verified end-to-end"
  - id: "G5-ROLLBACK-READINESS"
    verdict: "FAIL"
    evidence: "restricted/release-006/recovery-permission-check"
    limitation: "On-call lacks permission to execute rollback"
  - id: "G6-RISK-AUTHORITY"
    verdict: "PENDING"
    evidence: null
    limitation: "Risk-owner decision not completed"

approval_steps:
  - role: "Engineering QA Reviewer"
    principal_id: "principal-example-engineering-reviewer"
    decision: "APPROVE_TESTED_SCOPE"
    decided_at_utc: "2026-11-28T05:10:00Z"
    reviewed_revision: "helm-manifest-rev-4"
  - role: "Security Assurance Reviewer"
    principal_id: "principal-example-security-reviewer"
    decision: "REQUEST_CHANGES"
    decided_at_utc: "2026-11-28T05:20:00Z"
    reviewed_revision: "helm-manifest-rev-4"
    reason: "Recovery and audit evidence missing"
  - role: "Business Risk Owner"
    principal_id: "principal-example-risk-owner"
    decision: "PENDING"
    decided_at_utc: null
    reviewed_revision: null

decision:
  release_authorized: false
  status: "NO_GO"
  rationale: >
    Một số security tests đạt nhưng rollback readiness FAIL;
    migration và audit coverage còn INCONCLUSIVE;
    required risk approval chưa có.
  effective_from_utc: null
  expires_at_utc: null
  permitted_scope: null
  pre_deploy_validation_required: true
  next_actions:
    - "Test recovery permissions and migration rollback"
    - "Verify new audit event from source to SIEM"
    - "Obtain authorized risk and change approval"

post_release_plan:
  must_verify:
    - "Observed image and manifest digests match approved subject"
    - "Cross-tenant authorization negative tests remain PASS"
    - "Payment events and audit logs reach expected destinations"
    - "Transaction and migration invariants remain valid"
  stop_conditions:
    - "Any cross-tenant access succeeds"
    - "Audit logging fails for critical operations"
    - "Data integrity mismatch"
  deployment_run_id: null

governance:
  artifact_classification: "CONFIDENTIAL"
  evidence_store: "restricted-release-assurance"
  immutable_or_versioned_history: true
  authority_matrix_ref: "policy-release-authority-v3"
  evaluation_policy_version: "security-release-gates-v5"
  supersedes_approval_id: null
  review_required_on:
    - "artifact-digest-change"
    - "deployment-scope-change"
    - "new-critical-finding"
    - "gate-invalidated"
~~~

### 18.1. Đọc đúng kết quả của mẫu

- `G2-SECURITY-TESTS: PASS` chỉ nói các security tests trong **phạm vi đã kiểm tra** đạt, không tự đồng nghĩa release GO.
- `G5-ROLLBACK-READINESS: FAIL` là một điều kiện chặn nếu policy yêu cầu rollback capability trước release.
- `G3` và `G4` **INCONCLUSIVE** phải dẫn tới thu thập thêm evidence; không tự đổi thành PASS.
- Engineering QA có thể approve phần đã kiểm thử, nhưng Security reviewer đang yêu cầu thay đổi và risk owner chưa quyết định.
- `release_authorized: false` là kết luận nhất quán; deployment run vẫn `null` vì chưa có quyền thực thi.
- Record giữ nguyên **source/artifact/manifest IDs** để khi review lại không phê duyệt nhầm candidate khác.

### 18.2. Sau khi khắc phục thiếu sót

Cần tạo **gate evidence mới**, giữ record cũ, cập nhật hoặc sinh decision version mới theo quy trình, yêu cầu approvers đã được ủy quyền review đúng revision, chốt cửa sổ/scope và pre-deploy validation. Không chỉ sửa `status` sang GO mà bỏ những kết quả FAIL/INCONCLUSIVE trước đó.

## 19. Một bảng approval đơn giản và quy tắc đọc

Trong hệ thống nhỏ, thay vì YAML đầy đủ, có thể dùng bảng:

| Trường | Giá trị minh họa |
|---|---|
| Release / subject | payment-api candidate R14, image digest H, manifest M |
| Scope | Production account A, region A, canary 5% |
| Purpose | Sửa lỗi authorization, giữ ổn định thanh toán |
| Mandatory gates | Security PASS, Data INCONCLUSIVE, Recovery FAIL |
| Residual risk | Chưa có quyết định được ủy quyền |
| Approver(s) | QA approve tested scope, Security request changes |
| Overall decision | **NO-GO** |
| Required actions | Test rollback, audit events, migration invariants, xin duyệt lại |
| Next review | Khi đã có evidence mới và revision không đổi |
| Record lineage | approval ID, change ID, run IDs, audit events |

Ưu điểm của cấu trúc gọn là dễ dùng; rủi ro là **quá tóm tắt**. Các cell phải trỏ tới evidence và điều kiện tương ứng, không chỉ ghi “PASS” do người soạn tự điền.

## 20. Tình huống thực hành: Approval đúng người nhưng sai artifact

Một tổ chức phát hành dịch vụ quản lý tài khoản. Security reviewer đã duyệt release candidate A vào 16:00 sau khi kiểm tra SAST, SCA và kiểm thử phân quyền. QA đã nghiệm thu bản A, Change Authority duyệt rollout production vào 22:00. Release Manager lập lịch triển khai.

Từ 16:00 đến 22:00 xảy ra các việc:

- Một kỹ sư sửa một dòng cấu hình để mở debug endpoint; commit mới tạo candidate B.
- Tag `release-latest` được đẩy lại trỏ tới image B, trong khi approval chỉ ghi tên tag mà không lưu digest.
- Bản SAST/SCA mới chưa chạy; một integration test bị SKIP vì agent lỗi.
- Rollout mở rộng sang region thứ hai để tận dụng change window, nhưng CAB ban đầu chỉ duyệt region đầu.
- Nhà cung cấp thông báo một dependency có vulnerability nghiêm trọng đang được đánh giá.
- Lúc 21:30, SOC phát hiện pipeline audit log của region thứ hai không nhận event thử.
- Release Manager nói “Security đã duyệt và trễ deadline sẽ ảnh hưởng khách hàng”.

### 20.1. Câu hỏi

1. Approval ở 16:00 có còn đủ căn cứ để deploy candidate B vào hai region không?
2. Những thuộc tính nào của approval record đã thiếu khiến việc đối chiếu khó khăn?
3. Chỉ cần thay tag về image A rồi triển khai luôn có đủ không?
4. Security finding về dependency và mất log ở region B ảnh hưởng quyết định thế nào?
5. Những điều kiện nào cần trước khi phát hành có kiểm soát?

### 20.2. Hướng giải theo chuỗi assurance

**Bước 1 — Xác định subject bất biến.** Bản A khác B về commit và image. Quyết định đã duyệt **không tự bao phủ B**, dù tag giống nhau. Cần ghi digest của A/B và manifest, truy vết build provenance. Thay tag về A có thể giải quyết khác biệt binary nhưng vẫn phải xác minh deployment manifest, scope, cửa sổ và các gate còn hiệu lực.

**Bước 2 — Phân tích scope drift.** CAB duyệt một region; rollout hai region làm tăng blast radius, thay đổi dữ liệu và monitoring. Cần approval bổ sung theo chính sách hoặc giới hạn scope trở lại phạm vi đã được duyệt.

**Bước 3 — Kiểm tra test validity.** SAST/SCA/test A không chứng minh B an toàn. Integration test SKIP phải được phân loại **INCONCLUSIVE** nếu là required gate. Không được sửa kết quả SKIP thành PASS bằng xác nhận miệng.

**Bước 4 — Xử lý lỗ hổng mới.** Thông báo vulnerability của dependency là sự kiện yêu cầu assessment. Nếu thuộc phần sử dụng của release và vượt ngưỡng blocking, phải sửa, kiểm soát bù trừ hoặc xử lý ngoại lệ hợp lệ khi được phép. Không tự giả định mọi advisory là exploit thực, nhưng cũng không bỏ qua chỉ vì approval trước đó được cấp.

**Bước 5 — Kiểm tra observability.** Log SIEM không nhận từ region thứ hai làm suy yếu khả năng phát hiện/điều tra. Nếu audit logging là release gate bắt buộc, region B phải **NO-GO** cho tới khi có test đủ tin cậy hoặc phương án được phép. Không dùng tình trạng vùng A làm bằng chứng vùng B đạt.

**Bước 6 — Decision và reapproval.** Cho B/two-region rollout: NO-GO tại mốc hiện tại. Có thể xem lại bản A, region A, nếu còn phù hợp với obligations, risk/threat mới, digest xác minh được, gate và approvals đúng scope, cùng pre-deploy revalidation. Trong mọi trường hợp, quyết định phải có người có thẩm quyền và evidence mới cho các điểm đã thay đổi.

**Bước 7 — Bảo toàn lịch sử.** Giữ approval cũ cho A, tạo record đánh giá mới cho B hoặc scope mới, lưu lý do, diff, gate runs, người duyệt và kết quả triển khai. Không chỉnh sửa approval lúc 16:00 thành “đã duyệt B” để làm dashboard liên tục xanh.

### 20.3. Verdict tại thời điểm kiểm tra

| Claim/gate | Evidence | Kết luận |
|---|---|---|
| Artifact deploy đúng bản đã review | Tag trỏ sang B, approval không giữ digest | **FAIL/INCONCLUSIVE** tùy khả năng đối chiếu A; không thể GO cho B. |
| Required tests cho B đạt | Scan chưa chạy, integration SKIP | **INCONCLUSIVE**, không PASS. |
| Scope được phê duyệt | Approval region A, yêu cầu thêm region B | **FAIL** cho scope mở rộng. |
| Risk profile vẫn hợp lệ | Advisory mới chưa đánh giá | **INCONCLUSIVE**, cần reassessment. |
| Audit logging region B sẵn sàng | Synthetic event không đến SIEM | **FAIL** nếu quy tắc yêu cầu end-to-end event arrival. |
| Release authorization toàn bộ candidate B/hai region | Nhiều gate/điều kiện không thỏa | **NO-GO**. |

Điều quan trọng không phải release phải luôn bị chặn, mà là **quyết định không được vượt quá những gì thực sự được đánh giá và cho phép**.

## 21. Audit, forensic và retention của approval record

Khi có sự cố hoặc tranh chấp về thay đổi, câu hỏi đầu tiên thường là **ai đã ra quyết định và tại sao**. Approval record phải sống lâu đủ để trả lời trong phạm vi policy và nghĩa vụ áp dụng, không phụ thuộc nhân viên hiện tại còn ở tổ chức hay không.

### 21.1. Cấu trúc audit trail

~~~text
2026-11-28T04:00Z  Approval draft created for candidate A
2026-11-28T04:20Z  Security test evidence attached (run IDs)
2026-11-28T04:35Z  QA approved tested scope
2026-11-28T04:45Z  Security requested missing rollback evidence
2026-11-28T05:10Z  New test run attached; version 2 created
2026-11-28T05:30Z  Release approver issued decision for exact revision
2026-11-28T07:00Z  Pre-deploy integrity/scope validation
2026-11-28T07:05Z  Deployment execution linked
2026-11-28T07:20Z  Post-deploy verification recorded
~~~

Đây là timeline giả định. Record phải giữ **event time và actor**, không tạo dữ liệu giả sau sự kiện hoặc ghi lùi thời gian để làm đẹp approval.

### 21.2. Retention và quyền riêng tư

Giữ release approvals theo chính sách lưu hồ sơ, hợp đồng, kiểm toán và nhu cầu điều tra. Không có một thời hạn chung áp dụng mọi loại release. Evidence có thể chứa PII, thông tin network, security findings và secrets metadata, vì vậy cần phân loại, phân quyền, mã hóa, redaction và giới hạn sao chép.

### 21.3. Không nhầm chain of custody với audit trail thông thường

Với forensic/legal evidence, có thể cần chuỗi bàn giao chứng cứ chính thức: collector, bản gốc, hash, mỗi lần chuyển quyền nắm giữ, bản sao phân tích và yêu cầu pháp lý. Approval record/audit log thường phục vụ kiểm toán nội bộ; chỉ khi ngữ cảnh yêu cầu mới áp dụng quy trình chain of custody chặt theo chính sách điều tra.

## 22. Metrics đánh giá chất lượng phê duyệt phát hành

Mục tiêu không phải tăng số lượng APPROVED nhanh nhất; một quy trình thông qua mọi thứ có thể cho hiệu suất giấy tờ rất tốt mà kiểm soát thực tế rất kém.

| Chỉ số | Câu hỏi quản trị | Lưu ý |
|---|---|---|
| **Approval evidence completeness** | Tỷ lệ approval có subject, gates, scope, identity, risk và test references đầy đủ? | Đủ trường không đồng nghĩa evidence chính xác. |
| **Artifact-to-approval match rate** | Deployments có digest/manifest khớp phê duyệt? | Cần kiểm tra cả config, secret reference và runtime. |
| **Unauthorized deployment rate** | Bao nhiêu deployment thiếu quyết định hợp lệ hoặc ngoài scope? | Đừng che bằng cách backdate approval sau deploy. |
| **Gate bypass frequency** | Có bao nhiêu bypass, lý do, thẩm quyền và expiry? | Phân biệt emergency có quyền với bypass trái chính sách. |
| **Conditional releases outstanding** | Bao nhiêu release vẫn chưa hoàn thành điều kiện hậu kiểm? | Không gộp thành CLOSED khi chưa chứng minh. |
| **Post-release security regression** | Có bao nhiêu release làm xuất hiện control failures mới? | Phải phân biệt lỗi cũ và regression có căn cứ baseline. |
| **Approval rework/reapproval** | Cần duyệt lại bao nhiêu lần do artifact/scope đổi? | Không mặc định nhiều reapproval là xấu; có thể phản ánh kiểm soát tốt. |
| **Missing/invalid evidence age** | Gap quan trọng tồn tại bao lâu tới khi được giải quyết? | Không chỉ đếm file thiếu; ưu tiên theo risk tier. |
| **Revoked approvals** | Bao nhiêu approval bị thu hồi và nguyên nhân? | Theo dõi incident/new threat/automation failure. |
| **Reviewer independence** | Các quyết định high-risk có review tách quyền phù hợp? | Cần đánh giá SoD theo policy, không chỉ tên người. |
| **Time-to-decision** | Mất bao lâu từ candidate đủ evidence tới quyết định? | Không nên tối ưu giảm thời gian bằng cách bỏ gates. |

### 22.1. Ví dụ diễn giải

Giả sử có 40 production releases trong tháng: 36 có approval gắn digest khớp deployment, 2 có approval chỉ bằng tag mutable, 1 deploy không có record và 1 deploy ngoài region được duyệt. Khi đó **36/40 = 90%** có match được xác minh theo quy tắc đã nêu; không đồng nghĩa 90% releases an toàn. Ba loại gap còn lại cần triage theo severity và nghĩa vụ, không chỉ gộp vào “10% paperwork incomplete”.

Nếu tháng sau cải thiện lên 100% digest match nhưng số production regressions tăng, chương trình cần xem lại test quality/coverage, monitoring và risk decisions. **Evidence chất lượng và quyết định đúng là những điều kiện cần, không phải bằng chứng hệ thống không có lỗi**.

## 23. Sai lầm phổ biến và cách phòng tránh

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Approval là một câu “OK” không có subject. | Không biết đang duyệt bản và phạm vi nào. | Release ID, digest, scope, validity, decision rationale. |
| Duyệt tên tag mutable. | Có thể deploy artifact khác bản đã test. | Digest/manifest/version bất biến và runtime match check. |
| Dùng PR approve như release approval. | PR review không bao phủ môi trường/rollback/risk. | Tách gate source review và production authorization. |
| Chỉ kiểm tra pipeline xanh. | Gate bị SKIP, parser lỗi hoặc coverage thiếu. | Review status per gate, raw evidence, missing/error paths. |
| Cho phép người không đủ quyền ký release high-risk. | Vượt thẩm quyền, conflict of interest. | Authority matrix + effective role at decision. |
| Dùng risk acceptance để biến control FAIL thành PASS. | Assurance sai; nghĩa vụ có thể vẫn vi phạm. | Tách technical verdict, exception và risk decision. |
| Approve release A rồi deploy B. | Chứng cứ không còn hỗ trợ subject. | Pre-deploy digest/scope checks, reapproval triggers. |
| Không xem config, migration và data flows. | Binary đúng nhưng hệ thống thay đổi ngoài review. | Manifest, IaC plan, data/secret/network dependencies. |
| Approval không có expiry/conditions. | Quyết định cũ dùng cho scope mới và threats mới. | Validity window, recency, drift, revoke/reapprove. |
| Canary approved nhưng full rollout tự động không có gate. | Blast radius tăng không được kiểm chứng. | Progressive approval hoặc transitions đã được duyệt. |
| Không có rollback authority hoặc restore test. | Gặp lỗi không thể khôi phục an toàn. | Recovery readiness, owner, stop conditions. |
| Dùng ảnh screenshot thay cho nguồn test truy vết được. | Không kiểm chứng run, scope, authenticity. | Test run IDs, raw artifacts, tool/version/filters. |
| Người duyệt sửa được lịch sử không dấu vết. | Không thể tái dựng quyết định ban đầu. | Versioned records, audit, SoD và integrity control. |
| Emergency approval bị backdate. | Hợp thức hóa giả việc vượt quy trình. | Ghi thời điểm thật, incident context và hậu kiểm. |
| Deploy PASS được hiểu là security acceptance PASS. | Bỏ qua runtime, regression và monitoring. | Post-release control tests và incident/finding integration. |
| Chỉ đo tốc độ duyệt. | Khuyến khích click nhanh, bỏ test/risk. | Kèm quality metrics, unauthorized deployment, regressions. |

## 24. Checklist đánh giá một Approval record

Trước khi tuyên bố một release **được phê duyệt hợp lệ**, reviewer nên xác minh:

1. **Release identity:** Có release ID, service, source revision, build run, artifact digest và manifest version?
2. **Binding:** Approval có gắn đúng những artifact/config/migration mà deployment sẽ sử dụng?
3. **Scope:** Environment, accounts, regions, cohorts, rollout stages, thời hạn và người thực thi được xác định?
4. **Security objectives:** Những controls, threats, risk IDs và findings liên quan được map tới gates?
5. **Gate applicability:** Bắt buộc/không áp dụng có lý do và nguồn policy/version rõ?
6. **Test validity:** Kết quả security/QA chạy trên đúng candidate, đúng môi trường/độ đại diện và đúng thời gian?
7. **Coverage:** Có kiểm tra test SKIP/ERROR, nguồn thiếu, findings chưa phân loại, asset/dependency bỏ sót?
8. **Supply-chain provenance:** Artifact từ workflow tin cậy, digest/attestation và registry access đã được xác minh?
9. **Risk:** Residual risk và nghĩa vụ hợp đồng/pháp luật được xem đúng thẩm quyền?
10. **Exceptions:** Mọi deviation còn lại có exception hợp lệ, điều kiện, expiry và compensating tests không?
11. **Approvers:** Danh tính và vai trò còn hiệu lực, có segregation of duties và quyền ký?
12. **Decision rationale:** Có GO/NO-GO/CONDITIONAL_GO với lý do, phạm vi và điều kiện?
13. **Validity:** Có effective/expiry, stop triggers, reapproval rules và quyền revoke?
14. **Readiness:** Rollout, rollback/forward-fix, data integrity, on-call, incident path và communication sẵn sàng?
15. **Auditability:** Mỗi approval có timestamp, quyết định, reviewed evidence snapshot và history được bảo vệ?
16. **Pre-deploy check:** Artifact/manifest/scope/gates có được kiểm lại sát thời điểm execution?
17. **Execution linkage:** Deployment run/observed digest và environment có khớp bản duyệt?
18. **Post-release verification:** Có security/functional checks, log/alert tests và hành động khi FAIL?
19. **Continuous assurance:** Có monitor drift, new findings, control failure và incident sau release?
20. **Closure:** Record bảo toàn lịch sử quyết định, kết quả deployment và nghiệm thu cuối đúng bản không?

### Câu hỏi tự đánh giá

Một kỹ sư đã được QA và Security phê duyệt bản image X cho staging. Trong cùng ngày, họ muốn deploy image X sang production. Digest không đổi, functional tests đạt, nhưng quyền IAM tại production rộng hơn staging và rollback plan chưa được kiểm thử. Người quản lý sản phẩm nói “binary giống hệt, nên cứ dùng approval staging”.

**Có đủ căn cứ để deploy production không?**

**Gợi ý:** **Chưa.** Artifact identity chỉ là một điều kiện; approval staging không tự bao phủ production scope, quyền IAM, data risk và readiness khác biệt. Cần risk/impact review production, effective IAM diff và test đường được phép/bị cấm, recovery readiness, monitoring và người có thẩm quyền phê duyệt môi trường production theo policy. Nếu rollback là required gate mà chưa có evidence, kết quả NO-GO/NEEDS_EVIDENCE phù hợp. Khi điều kiện đạt, record phải gắn digest X với đúng manifest/scope và decision mới, sau đó kiểm chứng hậu triển khai.

**Approval record có giá trị trong release assurance khi nó tạo được đường truy vết không đứt từ release candidate và yêu cầu bảo mật, qua các test/risk/exception evidence, tới người ra quyết định đúng thẩm quyền và đúng phạm vi, rồi tới deployment thực tế và post-release verification. Một chữ ký không thay thế kiểm thử; một pipeline xanh không thay thế quyết định; và một quyết định GO không thay thế trách nhiệm tiếp tục theo dõi rủi ro sau phát hành.**
