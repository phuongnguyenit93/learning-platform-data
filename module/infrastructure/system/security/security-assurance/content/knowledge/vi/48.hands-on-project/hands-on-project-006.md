# Dự án thực hành: Tạo Security Review có bằng chứng cho một bản phát hành

**Security review** là hoạt động đánh giá có cấu trúc nhằm xác định một thiết kế, thay đổi hoặc bản phát hành **có đáp ứng các mục tiêu bảo mật áp dụng trong phạm vi đã xác định hay không**, dựa trên phân tích tài sản, mối đe dọa, yêu cầu, security controls, kiểm thử và bằng chứng. Review phải chỉ ra **điều được chứng minh, điều chưa đủ bằng chứng, điều bị phản chứng, rủi ro còn lại và người có thẩm quyền quyết định**.

Bài học thuộc chương **Dự án thực hành** của module **SECURITY_SECURITY_ASSURANCE**. Mục tiêu module là xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật: từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện và security assurance liên tục trong phát triển/vận hành.

Đây là một dự án **hands-on end-to-end**, không chỉ là checklist câu hỏi. Người học sẽ đóng vai **security reviewer** của một ứng dụng SaaS đa tenant chuẩn bị phát hành tính năng xuất tài liệu. Tất cả hệ thống, người dùng, tài sản, sự kiện, ID và kết quả kiểm thử trong bài đều là **dữ liệu giả định** để thực hành. Không cần truy cập môi trường thật; không được suy diễn rằng các phép thử mô phỏng bên dưới đã được thực thi ngoài đời.

> **Đầu ra cuối cùng:** một **Security Review Package** có thể giải thích cho nhóm phát triển, chủ sở hữu rủi ro và người kiểm toán: *đã review cái gì, theo tiêu chí nào, dùng bằng chứng gì, tìm thấy vấn đề gì, khắc phục ra sao và có nên GO/NO-GO hay GO có điều kiện hay không?*

---

## 1. Kết quả học tập

Sau khi hoàn thành dự án, người học có thể:

1. Viết **review charter** gồm mục tiêu, scope, out-of-scope, stakeholders, authority và tiêu chí kết luận.
2. Xác định **assets, data flows, trust boundaries, roles, environments, endpoints và dependencies**.
3. Thực hiện **delta threat modeling** và chuyển threat scenarios thành security requirements/control tests.
4. Lập **control–claim–evidence matrix**, phân biệt thiết kế, triển khai và vận hành.
5. Đánh giá **evidence provenance, relevance, sufficiency, coverage, freshness và counterevidence**.
6. Lập kế hoạch và phân tích **positive/negative security tests** bằng dữ liệu được phép.
7. Ghi **finding** có criteria, observed condition, impact, root-cause hypothesis, evidence, owner và remediation.
8. Phân biệt **PASS, FAIL, NOT DEMONSTRATED, EXCEPTED**, tránh dùng ticket Done hay scan sạch để thay kiểm chứng.
9. Đưa ra quyết định **GO, CONDITIONAL GO, HOLD hoặc NO-GO** dựa trên blocker, residual risk và thẩm quyền.
10. Tạo báo cáo security review có lịch sử, limitations, CAP, retest plan, reviewer và follow-up triggers.

### 1.1. Sản phẩm phải nộp

Một lần thực hành hoàn chỉnh tạo ra các thành phần sau; có thể gộp trong một báo cáo Markdown và phụ lục YAML:

| Mã deliverable | Nội dung | Điều kiện tối thiểu |
|---|---|---|
| **D1** | Review charter & scope | ID phiên bản, môi trường, dữ liệu, các phần không bao gồm |
| **D2** | Architecture/data-flow review | Diagram, assets, trust boundaries, security assumptions |
| **D3** | Threat & risk register | Ít nhất 6 risk scenarios có mức rủi ro và biện pháp |
| **D4** | Control–claim–evidence matrix | Ít nhất 8 criteria, status, evidence reference và gap |
| **D5** | Security test matrix | Positive/negative/regression, coverage và expected/actual |
| **D6** | Findings & remediation plan | Ít nhất 3 findings/gaps có owner, ưu tiên, closure criteria |
| **D7** | Release decision | GO/NO-GO có lý do, điều kiện và đúng authority |
| **D8** | Security review report | Executive summary, assumptions, limitations, evidence index, sign-off |

**Không bắt buộc viết ứng dụng mới hoặc chạy công cụ khai thác.** Mục tiêu là biết **thiết kế, đánh giá và lập luận từ evidence**. Nếu có môi trường lab hợp pháp, có thể chạy lại các test an toàn và thay các nguồn mô phỏng bằng kết quả thực tế được ghi nhận.

## 2. Bối cảnh dự án giả định

Sản phẩm tên **DocSphere**, một ứng dụng SaaS quản lý tài liệu cho nhiều tổ chức khách hàng (*tenant*). Mỗi tenant có tài liệu riêng, người dùng và vai trò riêng. Release mới **REL-DS-024**, candidate **rc-2**, chuẩn bị đưa vào production tại hai vùng **region-a** và **region-b**.

### 2.1. Tính năng hiện có

- Đăng nhập qua Identity Provider (IdP), API nhận access token đã xác thực.
- Người dùng đọc và sửa tài liệu thuộc tenant mình theo vai trò.
- Backend lưu metadata và quyền tài liệu trong database.
- Nội dung file nằm trong object storage riêng tư.
- Audit events được gửi từ ứng dụng qua log collector tới SIEM.
- Có backup định kỳ và quy trình khôi phục thử nghiệm.

### 2.2. Thay đổi của release mới

| Change ID | Mô tả | Security property có thể bị ảnh hưởng |
|---|---|---|
| CHG-101 | Thêm API tạo export job cho tập tài liệu | Object/tenant authorization, confidentiality |
| CHG-102 | Worker tạo file ZIP và lưu kết quả vào object storage | Data isolation, confidentiality, integrity, encryption |
| CHG-103 | Trả **download link có hạn** để nhận kết quả export | Link capability, expiration, access control, leakage |
| CHG-104 | Thêm vai trò **support-operator** hỗ trợ khách hàng | Privilege separation, auditability |
| CHG-105 | Đổi định dạng audit event cho export và download | Detection, SIEM parsing, evidence completeness |
| CHG-106 | Rolling deployment sang hai region | Mixed-version behavior, rollback, coverage |

Kết quả security review không chỉ phải kiểm tra từng thay đổi, mà còn đánh giá **đường dữ liệu end-to-end**: tạo job → worker xử lý → lưu ZIP → cấp link → tải file → ghi audit event → giám sát.

### 2.3. Tài sản và mức độ quan trọng

| Asset | Chức năng | Mức quan trọng giả định |
|---|---|---|
| API Gateway | Routing và xác thực sơ bộ | High |
| Document API | Kiểm tra quyền trên tài liệu | Critical |
| Export API | Nhận yêu cầu tạo và xem trạng thái job | Critical |
| Export Worker | Truy vấn dữ liệu, đóng gói ZIP | Critical |
| Database | Document metadata, tenant ownership, export job state | Critical |
| Object Storage | Nội dung file và export artifacts | Critical |
| IdP/IAM | Principal, token, roles và service identity | Critical |
| SIEM/log collector | Audit trail, cảnh báo và investigation | High |
| CI/CD & release manifest | Build và triển khai phiên bản | High |
| DR backups | Khôi phục dữ liệu và hoạt động | High |

Các nhãn “High/Critical” chỉ để học; trong tổ chức thật phải theo risk methodology và phân loại dữ liệu đã được phê duyệt.

### 2.4. Vai trò và nguyên tắc truy cập

| Vai trò | Quyền hợp lệ | Giới hạn bắt buộc |
|---|---|---|
| **tenant-viewer** | Xem tài liệu được cấp quyền trong tenant | Không sửa/xuất toàn bộ dữ liệu nếu không được cấp quyền |
| **tenant-editor** | Đọc/sửa tài liệu được phép, tạo export trong phạm vi đã duyệt | Không export tài liệu thuộc tenant khác |
| **tenant-admin** | Quản lý quyền và export trong tenant của mình | Không quản trị tenant khác |
| **support-operator** | Hỗ trợ theo yêu cầu và quy trình được duyệt | Không tự có quyền đọc nội dung khách hàng trên mọi tenant |
| **export-worker** | Đọc dữ liệu được yêu cầu hợp lệ để tạo job | Không dùng quyền wildcard để truy vấn tenant bất kỳ |
| **platform-admin** | Vận hành hạ tầng theo quyền được ủy quyền | Truy cập dữ liệu phải kiểm soát và audit riêng |

**Yêu cầu cao nhất về phân tách tenant:** không principal nào được đọc nội dung tài liệu của tenant khác chỉ bằng cách thay đổi input hoặc sử dụng link/job ID không thuộc quyền của mình.

### 2.5. Một số endpoint của bản phát hành

| Endpoint giả định | Mục đích |
|---|---|
| GET /v2/documents/{docId} | Đọc metadata và nội dung đã được phép |
| PATCH /v2/documents/{docId} | Sửa metadata tài liệu |
| POST /v2/exports | Tạo export job theo bộ lọc tài liệu |
| GET /v2/exports/{jobId} | Xem trạng thái export job |
| GET /v2/exports/{jobId}/download | Nhận download capability/link |
| GET /v2/export-files/{fileId} | Tải file qua đường API tùy cấu hình |
| POST /v2/support/access-requests | Yêu cầu hỗ trợ có phê duyệt |
| GET /v2/audit-events | Truy vấn audit theo quyền và tenant |

Các endpoint minh họa không phải API thực tế. Không thử những URL này trên hệ thống không thuộc quyền kiểm tra.

## 3. Yêu cầu bảo mật và tiêu chí review

Giả sử tổ chức đặt các requirement sau cho release:

| ID | Security requirement | Tiêu chí kiểm tra được |
|---|---|---|
| **SEC-AUTHN-01** | Token phải được xác thực đúng | Token giả/không hợp lệ không được chấp nhận; luồng hợp lệ hoạt động |
| **SEC-AUTHZ-02** | Mọi thao tác tài liệu/export phải kiểm tra tenant và object | Các đường đọc, tạo job, xem job, lấy link, tải file không vượt quyền |
| **SEC-PRIV-03** | Quyền support phải tối thiểu, có chấp thuận và audit | Support không tự mở truy cập nội dung ngoài ticket được duyệt |
| **SEC-DATA-04** | Export file phải được bảo vệ theo phân loại dữ liệu | Storage private, mã hóa, retention và truy cập phù hợp |
| **SEC-LINK-05** | Download link bị giới hạn khả năng lạm dụng | Hạn sử dụng, phạm vi/capability và chia sẻ được quản lý theo policy |
| **SEC-LOG-06** | Hành động export/download quan trọng tạo audit event | Event nhận diện đúng principal/tenant/job và tới SIEM |
| **SEC-BUILD-07** | Artifact được kiểm tra phải khớp artifact phát hành | Commit/digest/manifest và runtime version đối chiếu được |
| **SEC-REL-08** | Phát hành có kiểm soát blast radius và phục hồi | Canary, stopping conditions, rollback/forward fix phù hợp |
| **SEC-DR-09** | Dữ liệu và export-related dependencies có recovery plan | Có test restore/khả năng truy cập key phù hợp khi rủi ro yêu cầu |
| **SEC-FIND-10** | Findings phải được xử lý hoặc có quyết định rủi ro hợp lệ | Blocking finding không được xem là PASS nếu chưa verified fixed |
| **SEC-EVD-11** | Evidence đầy đủ theo population, phiên bản và thời kỳ | Missing source/region/role phải ghi UNKNOWN và được xử lý |
| **SEC-EXC-12** | Ngoại lệ có phạm vi, thời gian, điều kiện và approver đúng quyền | Exception hết hạn hoặc vượt scope không được coi hợp lệ |

**Lưu ý:** đây là yêu cầu được giả định cho lab, không phải nguyên văn một chuẩn ISO/NIST hay yêu cầu pháp luật. Khi thực hành trên doanh nghiệp thật, lấy criteria từ security policy, standards, hợp đồng và risk appetite có hiệu lực.

## 4. Ranh giới hệ thống và data-flow diagram

Một sơ đồ đủ để bắt đầu review:

~~~mermaid
flowchart LR
    U["Tenant user / Support operator"] -->|Access token| G["API Gateway"]
    G --> A["Document & Export API"]
    A --> I["IdP / AuthN / Role policies"]
    A --> D[("Metadata DB")]
    A --> Q["Export job queue"]
    Q --> W["Export Worker"]
    W --> D
    W --> O[("Private Object Storage")]
    A --> L["Signed URL / download endpoint"]
    L --> O
    A --> E["Audit Event Collector"]
    W --> E
    E --> S["SIEM / Alerting"]
    O --> B["Backup / DR"]
~~~

### 4.1. Trust boundaries cần đánh dấu

**TB1 — Internet/user → gateway:** token, session, rate limits, API exposure.

**TB2 — Gateway → backend:** backend có bắt buộc kiểm tra quyền theo object, không tin header do client tự đặt?

**TB3 — API → queue → worker:** nội dung job có được ràng buộc vào tenant/principal/permission tại thời điểm xử lý?

**TB4 — Worker → database/object storage:** service identity có vượt quyền tối thiểu hoặc có thể đọc dữ liệu của tenant khác?

**TB5 — API/link holder → export artifact:** URL là bearer capability hay cần xác thực bổ sung? Nếu lộ link, ai có thể sử dụng theo policy?

**TB6 — Application/worker → SIEM:** các sự kiện có đầy đủ, nhất quán, không ghi secret và được giám sát khi pipeline lỗi?

**TB7 — Production → backups/DR:** mã hóa, key access, retention và khôi phục.

Người học phải **bổ sung ít nhất hai đường truy cập/đường lỗi** chưa thể hiện rõ trên sơ đồ, ví dụ phiên bản cũ trong rolling deployment, support tooling truy cập storage trực tiếp, hoặc upload/export artifact bị cache.

### 4.2. Giả định cần kiểm tra, không coi là sự thật

- Token đã ký đúng và tenant claim đáng tin.
- Mọi API endpoint có cùng security middleware.
- Worker chỉ xử lý job được tạo hợp lệ.
- Link có hạn chỉ dùng cho đúng người/tenant được phép theo yêu cầu.
- Storage không public và không có đường phụ ngoài gateway.
- SIEM nhận đủ export/download events.
- Hai region chạy cùng release candidate khi full rollout.
- Backup có thể khôi phục và key được cấp quyền đúng.

Mỗi giả định phải có **bằng chứng hoặc được ghi rõ chưa kiểm chứng**. Đây là kỹ năng trung tâm của security review.

## 5. Quy định an toàn và phương pháp thực hành

Dự án cho phép đánh giá **tài liệu giả định và các kết quả test mô phỏng**. Nếu tự dựng lab:

1. Chỉ sử dụng môi trường và tài khoản **mình được phép kiểm tra**.
2. Dùng tenant, user, secret và document **giả lập**, không lấy dữ liệu khách hàng thật.
3. Không quét, thử xâm nhập hoặc thực hiện tải dữ liệu từ hệ thống của bên thứ ba.
4. Negative tests cần đo hành vi từ chối bằng fixture có kiểm soát; không cần khai thác payload phá hoại.
5. Không tạo public storage thật chứa dữ liệu nhạy cảm để “xem detector có bắt không”.
6. Giới hạn test về tần suất, tài nguyên, quyền và rollback; bảo toàn bằng chứng mà không tăng rủi ro.
7. Nếu chỉ dùng evidence pack của bài, đánh dấu **SIMULATED** trên mọi test/decision; không gọi là “verified in production”.

**Không được dùng ví dụ trong bài như một biên bản kiểm toán hoặc báo cáo rủi ro đã được phê duyệt thật.**

## 6. Bộ evidence đầu vào của dự án

Người học nhận **evidence pack giả định** sau. Một số hiện vật hỗ trợ claim, một số không đủ, một số tạo phản chứng. Không tự sửa đầu vào để làm kết luận tốt hơn.

| Ref | Hiện vật giả định | Thông tin có thể sử dụng | Giới hạn/cảnh báo |
|---|---|---|---|
| **E-01** | Release manifest | rc-2, commit C24, API/worker image digests, intended rollout hai region | Chưa chứng minh cả hai region đã deploy |
| **E-02** | Security requirements & role matrix | 12 criteria ở mục 3, scope tenant và vai trò | Đây là thiết kế; chưa chứng minh enforcement |
| **E-03** | CI report của rc-2 | 245 unit tests PASS, dependency scan không có finding theo rule đang bật | Không có test export link, scanner chỉ xét image API |
| **E-04** | AuthN integration tests | Token hợp lệ được chấp nhận; token thiếu/chữ ký sai bị từ chối trên gateway | Không bao gồm đường truy cập nội bộ bỏ qua gateway |
| **E-05** | Document API test report | Đọc/sửa tài liệu đúng tenant PASS; cross-tenant GET bị từ chối | Test chỉ 6/8 endpoint, chưa cover export download |
| **E-06** | Export job test | Tenant A tạo job với tài liệu A thành công; API từ chối tạo job tham chiếu tài liệu B | Chưa chứng minh worker và link kiểm tra tenant |
| **E-07** | Download security test | User B nhận được nội dung export do user A tạo khi có link giả định bị chia sẻ ngoài cơ chế được duyệt | **Phản chứng** SEC-AUTHZ-02 / SEC-LINK-05; cần phân loại tác động |
| **E-08** | Support role review | Role hỗ trợ có quyền xem export job metadata của nhiều tenant; lý do nghiệp vụ chưa được phê duyệt | Scope & least privilege chưa được chứng minh |
| **E-09** | Cloud configuration snapshot | Object storage private và encryption bật trong region-a ở 10:00 UTC ngày T | Thiếu region-b và lịch sử cấu hình |
| **E-10** | SIEM parser test | Export-create events đã đến SIEM; download-event format mới chưa được parser nhận diện | **Phản chứng** yêu cầu logging cho download |
| **E-11** | Deployment observation | region-a chạy rc-2; region-b vẫn chạy rc-1 ở thời điểm T | Không thể kết luận full release đã rollout |
| **E-12** | Remediation ticket | Team API ghi “Fix signed link check implemented in PR-77”; ticket status Done | Chưa có digest mới, deploy proof hoặc retest |
| **E-13** | Risk/exception registry | Không tìm thấy approval hợp lệ cho bypass authz/download hay logging gap | Không được tự gán risk accepted |
| **E-14** | DR rehearsal summary | Backup job PASS; lần restore gần nhất chưa thử cùng key/worker version rc-2 | Không đủ evidence cho recovery path mới |
| **E-15** | Source inventory & health | 7/8 endpoint có coverage logging source; route download mới chưa có synthetic event | Không được báo “100% logging coverage” |
| **E-16** | QA regression report | Export hợp lệ hoạt động trên rc-2 trong staging; không có kết quả trên phiên bản mixed region-a/b | Chưa chứng minh compatibility khi rolling deploy |

### 6.1. Dữ liệu test giả định chi tiết

Coi tất cả ID sau là **fixture an toàn**, không gắn dữ liệu khách hàng thật:

~~~yaml
fictional_test_dataset:
  tenants:
    - id: tenant-a
      users:
        - {id: alice, role: tenant-editor}
        - {id: ana, role: tenant-admin}
      documents: [doc-a1, doc-a2]
    - id: tenant-b
      users:
        - {id: bob, role: tenant-viewer}
        - {id: ben, role: tenant-admin}
      documents: [doc-b1, doc-b2]
  system:
    support_principal: support-s1
    export_worker_principal: worker-exports
  jobs:
    - {id: job-a1, owner_tenant: tenant-a, output: file-a1}
  release_candidate: rc-2
  test_environment: approved-staging
  dataset_classification: synthetic
~~~

Cần phân biệt:
- **Negative:** Bob của tenant B không được đọc doc-a1, xem job-a1 hoặc nhận nội dung file-a1 trái quyền.
- **Positive:** Alice được export tài liệu có quyền của tenant A và tải kết quả nếu đáp ứng chính sách.
- **Regression:** role support không được tự tăng quyền, audit event có mặt, phiên bản cũ/mới tương thích trong cửa sổ rollout khi có yêu cầu.

### 6.2. Bất nhất có chủ đích

E-03 cho biết pipeline PASS, nhưng E-07 cho thấy thất bại bảo mật ở hành vi download. Hai thông tin **không mâu thuẫn về mặt logic**: test suite E-03 không bao phủ đường E-07. Vấn đề là **suy luận sai** nếu ai đó dùng E-03 để tuyên bố toàn bộ authz đạt.

E-12 cho biết PR-77 đã sửa, nhưng chưa có kết quả trên artifact/region. **“Implemented” chưa phải “Verified fixed”.**

E-09 phản ánh region-a tại T; E-11 cho thấy region-b chưa cùng phiên bản. **Một snapshot ở một region không chứng minh full production.**

## 7. Tổ chức nhóm, vai trò và sản phẩm review

Nếu học nhóm, chia vai:

| Vai trò | Nhiệm vụ chính | Quyền quyết định minh họa |
|---|---|---|
| **Security reviewer** | Lập kế hoạch, đánh giá claim/evidence, ghi findings và recommendations | Đưa kết luận kỹ thuật, không tự chấp nhận rủi ro nghiệp vụ |
| **Application owner** | Giải thích hệ thống, hoàn thiện test, CAP và artifact | Ưu tiên sửa ứng dụng trong phạm vi |
| **Platform/SRE owner** | Deployment, IAM runtime, network, SIEM/DR dependencies | Triển khai, rollback theo authorization |
| **Data/business owner** | Dữ liệu, tác động và mục tiêu nghiệp vụ | Cung cấp tiêu chí tác động và quyết định trong thẩm quyền |
| **Risk authority** | Chấp nhận residual risk hoặc ngoại lệ theo chính sách | GO có điều kiện khi quy tắc cho phép |
| **Independent verifier** | Retest finding và review closure | Xác nhận đã sửa theo tiêu chí, không thay risk authority |

Một người học cá nhân có thể đóng tất cả vai **trên giấy**, nhưng phải ghi rõ **đâu là quyết định mô phỏng**, đâu là kết luận của reviewer và đâu cần người có thẩm quyền thực trong doanh nghiệp.

## 8. Quy trình thực hiện dự án

Toàn bộ workflow đề xuất:

~~~mermaid
flowchart TD
    A["D1: Review charter + scope"] --> B["D2: Architecture / trust boundaries"]
    B --> C["D3: Threat and risk scenarios"]
    C --> D["D4: Control–claim–evidence matrix"]
    D --> E["D5: Positive/negative/regression test analysis"]
    E --> F["Quality & coverage checks"]
    F --> G["D6: Findings, CAP, retest criteria"]
    G --> H{"Security gates đủ chưa?"}
    H -- "Không" --> I["NO-GO/HOLD, xử lý blocker"]
    H -- "Đạt trong scope" --> J["GO hoặc limited GO đúng thẩm quyền"]
    I --> K["D7: Decision record"]
    J --> K
    K --> L["D8: Report, evidence index, follow-up"]
~~~

Đừng bỏ thẳng từ “đã chạy scan” sang “security approved”. Mỗi bước phải giúp người khác truy ra **lý do** của kết luận.

## 9. Bước 1 — Viết review charter

Review charter là tài liệu thỏa thuận **cần review cái gì, để hỗ trợ quyết định nào**.

### 9.1. Mẫu charter

~~~yaml
security_review_charter:
  review_id: SR-DS-024
  service: DocSphere
  release: REL-DS-024
  candidate: rc-2
  decision_purpose: "Pre-release security GO/NO-GO recommendation"
  environment_scope:
    - approved-staging
    - production-region-a
    - production-region-b
  components:
    - document-api
    - export-api
    - export-worker
    - idp-integration
    - object-storage
    - logging-pipeline
    - deployment-rollback-path
  protected_data: "Synthetic in tests; customer documents in production"
  critical_properties:
    - tenant-isolation
    - authorization
    - export-confidentiality
    - auditability
    - integrity-and-availability
  out_of_scope:
    - "Unrelated marketing website"
    - "Supplier code internals unavailable for review"
  assumptions:
    - "Production requirements and asset inventory will be confirmed"
  review_owner_role: SECURITY_ASSURANCE_REVIEWER
  technical_owner_role: APPLICATION_OWNER
  decision_authority_role: AUTHORIZED_RELEASE_RISK_OWNER
  evidence_set: "E-01..E-16 (fictional training pack)"
  status: DRAFT
~~~

**Yêu cầu thực hành:** sửa ba mục trong bản charter để loại bỏ điều mơ hồ (ví dụ “supplier internals unavailable” cần nêu **rủi ro phụ thuộc và giới hạn kết luận** thay vì coi bên ngoài scope là không có rủi ro).

### 9.2. Điều phải nêu rõ

1. Mục tiêu review: thiết kế, release readiness, kiểm soát vận hành hay compliance?
2. Phiên bản và deadline quyết định.
3. Môi trường, account, region, tenant/role và data flows.
4. Tiêu chí PASS/FAIL, blocking severity và nguồn policy.
5. Các phép thử được phép, giới hạn an toàn.
6. Người cung cấp evidence, người chịu risk, reviewer.
7. Những phần không kiểm tra và tác động tới phạm vi kết luận.
8. Cách thức xử lý finding, phản chứng và thiếu bằng chứng.

**Một review charter không trao quyền pentest mọi mục tiêu.** Testing authorization phải được cấp riêng theo phạm vi thực tế nếu chạy trên hệ thống thật.

## 10. Bước 2 — Xác minh tài sản và luồng dữ liệu

Bắt đầu từ mục 2–4 rồi tự lập **asset inventory** và đánh dấu trust boundaries.

### 10.1. Mẫu bảng để điền

| Asset / Flow | Owner | Dữ liệu | Trust boundary | Rủi ro nếu sai | Bằng chứng cần |
|---|---|---|---|---|---|
| Browser → Gateway | Identity/API owner | Access token | TB1 | AuthN bypass | Token validation tests |
| Gateway → Export API | API owner | Tenant/job request | TB2 | Authz bypass | Source review, negative tests |
| API → Queue → Worker | API/worker owner | Job identity, doc IDs | TB3 | Cross-tenant processing | Job-to-tenant binding tests |
| Worker → Storage | Platform/data owner | ZIP output | TB4 | Lộ dữ liệu hoặc lẫn tenant | IAM, encryption, object access tests |
| Download route | Export owner | Link/file capability | TB5 | Share/link misuse | Link TTL/authorization tests |
| App/Worker → SIEM | Logging control owner | Audit records | TB6 | Không phát hiện truy cập | End-to-end log checks |

**Nhiệm vụ:** bổ sung flow của support operator và flow của DR; ghi rõ **principal nào quyết định quyền trên mỗi điểm**.

### 10.2. Tìm đường bypass

Đặt những câu hỏi:
- Backend có thể được gọi ngoài gateway không?
- Worker có tin tenant ID trong job payload hay kiểm tra chủ sở hữu từ nguồn đáng tin?
- Link download có thể được dùng lại sau khi quyền tạo job bị thu hồi?
- Một support user có thể đọc file mà không có request được duyệt?
- Audit log ghi được “principal thật” hay chỉ ghi service worker?
- Region cũ có route hoặc policy khác cho cùng tính năng?

Đây là câu hỏi **thiết kế và kiểm thử**, không giả định rằng hệ thống thực đã có lỗ hổng ngoài bằng chứng E-07 được cung cấp.

## 11. Bước 3 — Threat modeling theo thay đổi

Thực hiện **delta threat modeling**: so hành vi trước và sau REL-DS-024, xác định attack surfaces và security assumptions mới. Có thể dùng STRIDE hoặc risk-scenario approach. Quan trọng là nối threat tới **control và test**.

### 11.1. Bộ câu hỏi STRIDE rút gọn

| Nhóm | Câu hỏi áp dụng cho export |
|---|---|
| **Spoofing** | Token/principal của job có bị giả mạo hoặc bị tin sai? |
| **Tampering** | Có thể sửa job document list, tenant field hoặc output metadata không? |
| **Repudiation** | Ai đã export/tải file, log có đủ định danh và thời gian? |
| **Information disclosure** | Có đường đọc ZIP của tenant khác, lộ link hoặc dữ liệu qua log? |
| **Denial of service** | Export lớn gây nghẽn queue, storage/quota hoặc ảnh hưởng các tenant khác? |
| **Elevation of privilege** | Support/operator/worker có quyền vượt phạm vi cần thiết? |

### 11.2. Mẫu risk statement

> Do export job tách thành hai pha tạo và tải, nếu download endpoint **không kiểm tra quyền của chủ request đối với job/file** và link có thể được chia sẻ ngoài luồng hợp lệ, người thuộc tenant khác có thể nhận nội dung ZIP, gây lộ thông tin khách hàng.

### 11.3. Risk register sơ khởi

| ID | Threat/failure scenario | Tác động | Control chính | Test/evidence |
|---|---|---|---|---|
| **R-01** | Download link được dùng trái tenant | Confidentiality — Critical | SEC-AUTHZ-02 / SEC-LINK-05 | E-07, negative link tests |
| **R-02** | Support role có quyền rộng | Privilege misuse — High | SEC-PRIV-03 | E-08, role matrix |
| **R-03** | Download audit event mất tại SIEM | Auditability/detection — High | SEC-LOG-06 | E-10, E-15, synthetic tests |
| **R-04** | Một region chưa có bản fix | Exposure/consistency — High | SEC-BUILD-07 | E-01, E-11, runtime digest |
| **R-05** | Export worker đọc nhiều tenant vì IAM rộng | Cross-tenant data exposure — Critical tiềm năng | SEC-AUTHZ-02 / SEC-DATA-04 | Worker IAM/policy tests cần bổ sung |
| **R-06** | Mixed-version queue/job không tương thích | Integrity/availability — High | SEC-REL-08 | E-16, compatibility tests |
| **R-07** | Backup không restore được với key mới | Recovery — High | SEC-DR-09 | E-14, restore rehearsal |
| **R-08** | Export file còn sau retention deadline | Privacy/confidentiality — High | SEC-DATA-04 | Lifecycle/TTL evidence cần bổ sung |

Các mức là **đề xuất giả định để thảo luận**, không tự biến thành quyết định severity của tổ chức. Người học phải giải thích **vì sao** chọn mức và đâu là bất định.

### 11.4. Bài tập bổ sung

Tự viết thêm **ít nhất hai risk statements** cho tình huống:
- Một tenant có tài liệu rất lớn, worker xử lý chung queue với tenant khác.
- Link download tồn tại khi job bị hủy hoặc quyền người tạo đã thay đổi.

Với mỗi scenario, ghi **precondition, hành vi có thể xảy ra, tác động, control, evidence cần thu và owner**.

## 12. Bước 4 — Xây control–claim–evidence matrix

Đây là trung tâm của security review. Một hiện vật chỉ có ý nghĩa khi biết nó **hỗ trợ claim nào** và **không hỗ trợ claim nào**.

### 12.1. Cách viết claim

Không viết: “Authorization secure”.

Hãy viết:

> **C-AUTHZ:** Trên release rc-2 trong các đường export/download thuộc manifest, mọi request đọc job/link/file của người dùng đều được kiểm tra quyền trên tenant/object theo SEC-AUTHZ-02, với negative và positive tests bao phủ các role đã liệt kê.

Phân rã:
- **G1:** policy quyền được định nghĩa đủ.
- **G2:** đúng implementation đã deploy ở các môi trường thuộc scope.
- **G3:** đường tạo job, lấy link, tải file đều enforce.
- **G4:** role support, worker, TTL và biến thể được kiểm tra.
- **G5:** logging và control thay đổi tiếp tục được vận hành.

Nếu có phản chứng ở G3, top-level claim **không thể PASS** chỉ vì G1 và G2 có tài liệu đẹp.

### 12.2. Ma trận mẫu dựa trên evidence pack

| Requirement | Claim cần đánh giá | Evidence | Đánh giá sơ bộ | Cần bổ sung |
|---|---|---|---|---|
| SEC-AUTHN-01 | Token validation trên các đường thuộc scope | E-04 | **PARTIAL / NOT DEMONSTRATED** cho toàn bộ đường truy cập | Kiểm tra bypass gateway và internal calls |
| SEC-AUTHZ-02 | Không cross-tenant data access | E-05, E-06, E-07 | **FAIL** cho download path đã thử | Fix, test export/link và các role |
| SEC-PRIV-03 | Support least privilege, approval và audit | E-08 | **NOT DEMONSTRATED** | Business justification, approval, negative tests |
| SEC-DATA-04 | Export storage private/encrypted theo scope | E-09 | **PARTIAL** region-a tại T | Region-b, retention, runtime tests |
| SEC-LINK-05 | Download link có ràng buộc phù hợp | E-07 | **FAIL / CONTRADICTED** theo policy giả định | Link scope/TTL/revocation tests |
| SEC-LOG-06 | Export/download events đến SIEM | E-10, E-15 | **FAIL** cho download event | Parser fix và source-to-SIEM retest |
| SEC-BUILD-07 | Đúng artifact/manifest ở hai region | E-01, E-11 | **PARTIAL** | Runtime digest region-b |
| SEC-REL-08 | Mixed-version/rollback an toàn | E-16 | **NOT DEMONSTRATED** | Compatibility và rollback rehearsal |
| SEC-DR-09 | Recovery path phù hợp release | E-14 | **NOT DEMONSTRATED** | Key/worker restore test |
| SEC-FIND-10 | Blocking findings được xử lý hợp lệ | E-12, E-13 | **NOT VERIFIED FIXED** | Deploy proof, independent retest |
| SEC-EVD-11 | Evidence đủ scope/period | E-05, E-09, E-15 | **NOT DEMONSTRATED** tổng thể | Endpoint/region/source completeness |
| SEC-EXC-12 | Ngoại lệ hợp lệ nếu có sai lệch | E-13 | **Không có approval** cho lỗi nêu | Không tự ghi EXCEPTED |

### 12.3. Bốn mức cần phân biệt

- **PASS:** bằng chứng đủ, tin cậy, phù hợp criteria, phạm vi, thời kỳ và phiên bản.
- **FAIL / CONTRADICTED:** có bằng chứng tin cậy cho thấy criteria bị vi phạm trong phạm vi đã thử.
- **UNKNOWN / NOT DEMONSTRATED:** nguồn thiếu, độ bao phủ không đủ hoặc chưa có phép thử cần thiết.
- **EXCEPTED:** sai khác được phê duyệt trong phạm vi/thời hạn/điều kiện theo thẩm quyền; **không tự coi control kỹ thuật PASS**.

Một policy hoặc SOP có thể hỗ trợ **design adequacy**; một configuration snapshot hỗ trợ **implementation tại thời điểm T**; log và operating records có thể hỗ trợ **operating effectiveness trong kỳ**. Không dùng một loại evidence để thay thế mặc định loại khác.

## 13. Bước 5 — Đánh giá chất lượng evidence

Người học phải kiểm tra từng E-01..E-16 theo những câu hỏi:

1. **Relevance:** hiện vật giúp trả lời claim/control nào?
2. **Sufficiency:** có đủ để kết luận mạnh đến đâu?
3. **Coverage:** đúng toàn population endpoint/role/tenant/region hay chỉ mẫu?
4. **Freshness:** đúng rc-2, đúng thời điểm/kỳ hay còn dựa release cũ?
5. **Reliability:** phương pháp, công cụ, source và quyền truy cập có đáng tin?
6. **Integrity:** có audit trail/version của raw evidence không?
7. **Independence:** nhiều báo cáo có dùng cùng nguồn lỗi?
8. **Counterevidence:** hiện vật nào chống lại claim?
9. **Data sensitivity:** có thể lưu/chia sẻ nội dung mà không lộ dữ liệu nhạy cảm?
10. **Reassessment trigger:** thay đổi nào làm evidence mất hiệu lực?

### 13.1. Mẫu evidence quality review

| Ref | Điểm mạnh | Điểm yếu | Kết luận được phép |
|---|---|---|---|
| E-03 | Có số lượng test và candidate | Không có authz link tests, dependency scan không cover worker | “Các phép thử trong báo cáo PASS”, **không** “toàn release an toàn” |
| E-07 | Phép thử trực tiếp đường download | Chưa có fix retest hoặc đủ biến thể | Có **phản chứng** cho control download theo fixture |
| E-09 | Trạng thái storage tại region-a, T | Không có region-b/history | Snapshot scope giới hạn |
| E-10 | Chỉ ra parser không nhận event mới | Cần log raw và xác minh ảnh hưởng thời gian | Logging control chưa đạt đường download đã thử |
| E-12 | Có tiến độ sửa code | Không chứng minh deploy/behavior | Implemented claim, chưa verified fixed |

**Nhiệm vụ:** đánh giá thêm ít nhất 6 evidence item và chỉ ra **bằng chứng nào phải được thu lại** nếu release candidate đổi thành rc-3.

### 13.2. Không dùng một con số scan để thay mức bảo đảm

E-03 có 245 unit tests PASS; điều đó không phải phép tính “245/245 = hệ thống an toàn”. Nó chỉ mô tả kết quả **của 245 test hiện có**. Nếu một control cần negative test mới mà test suite không chứa, **khoảng trống vẫn tồn tại**.

### 13.3. Tập đối tượng (population) và sampling

Đối với từng control, định nghĩa population:
- Tất cả route/endpoint, bao gồm async export và legacy download.
- Các role/principal, bao gồm support và worker.
- Các tenant boundaries và các kiểu object.
- Các region, account, artifact version.
- Những event types bắt buộc gửi log.
- Các key/backup/DR dependencies có thể bị ảnh hưởng.

Nếu chỉ test 6/8 route, không suy “75% security” theo phép chia; một endpoint chưa test có thể chứa dữ liệu quan trọng. Nếu dùng sampling, phải giải thích phương pháp, kích thước, cách chọn, rủi ro trọng yếu và giới hạn suy rộng.

## 14. Bước 6 — Lập security test matrix

Mục tiêu không phải “thử hết mọi thứ”, mà **kiểm tra những scenario có thể làm thay đổi quyết định GO/NO-GO**.

### 14.1. Kịch bản kiểm thử đề nghị

| Test ID | Loại | Fixture / Điều kiện | Expected | Trạng thái dữ liệu pack |
|---|---|---|---|---|
| **T-01** | Positive | Alice đọc doc-a1 có quyền | Trả đúng dữ liệu tenant A | E-05: PASS |
| **T-02** | Negative | Bob đọc doc-a1 | Không tiết lộ dữ liệu tenant A | E-05: PASS |
| **T-03** | Positive | Alice tạo export từ doc-a1 | Job thuộc tenant A được tạo | E-06: PASS |
| **T-04** | Negative | Bob tạo job dùng doc-a1 | Bị từ chối, không có side effects trái quyền | E-06: PASS |
| **T-05** | Negative | Bob thử dùng link thuộc job-a1 | Không trả file thuộc tenant A | E-07: FAIL |
| **T-06** | Negative | Support ngoài ticket duyệt lấy download link | Không được cấp quyền | Chưa có kết quả |
| **T-07** | Boundary | Link hết hạn hoặc job bị hủy | Không còn capability sử dụng trái policy | Chưa có kết quả |
| **T-08** | Runtime | Worker truy xuất object ngoài tenant job | Bị policy/logic từ chối | Chưa có kết quả |
| **T-09** | Audit | Tạo/tải export có sự kiện đúng schema vào SIEM | Event xuất hiện kèm principal, tenant, job | E-10: download FAIL |
| **T-10** | Deployment | region-a và region-b chạy đúng rc-2 khi full rollout | Digest khớp manifest | E-11: FAIL ở T |
| **T-11** | Compatibility | Queue/job hoạt động khi old/new versions cùng tồn tại | Không mất/nhân đôi/sai job | Chưa có kết quả |
| **T-12** | Recovery | Khôi phục job/data với key và version có liên quan | Đạt criteria recovery | E-14: chưa có test đầy đủ |
| **T-13** | Regression | Alice export và tải file hợp lệ sau fix | Hoạt động đúng, không lộ dữ liệu qua log | E-16: PASS staging trước fix |
| **T-14** | Negative | Token thiếu/chữ ký sai gọi gateway | Bị từ chối | E-04: PASS |
| **T-15** | Data protection | Retention/lifecycle loại export artifact đúng hạn | File không còn sau hạn policy | Chưa có kết quả |

**Nhiệm vụ:** chọn 8 test trọng yếu và phân tích risk coverage. Đối với T-05 và T-09, viết **root-cause hypothesis** và các biến thể cần thử sau fix; đối với T-10 giải thích khác biệt giữa intended manifest và observed runtime.

### 14.2. Pseudocode negative và positive test

Đây là logic kiểm tra tại **lab được phép**; các hàm không tương ứng với API thật:

~~~text
Given:
  alice = authorized editor in tenant-a
  bob = viewer in tenant-b
  doc_a1 = synthetic document owned by tenant-a

Positive:
  job = export_api.create(alice, [doc_a1])
  assert job.owner_tenant == "tenant-a"
  file = export_api.download(alice, job.id)
  assert file contains only authorized synthetic tenant-a content

Negative:
  denied = export_api.download(bob, job.id)
  assert denied exposes no tenant-a document content
  assert no unauthorized export side effect occurred

Audit:
  verify event(source="download", actor=alice, tenant="tenant-a")
  verify event(source="download-denied", actor=bob, tenant="tenant-b")
  verify end_to_end_delivery_to_siem()

Caution:
  Do not use customer data or unauthorized production targets.
  Review actual status codes/side effects against approved API policy.
~~~

HTTP 403 và 404 đều có thể phù hợp tùy thiết kế tránh tiết lộ sự tồn tại object. Điều cần kiểm chứng là **không có dữ liệu hoặc side effect trái quyền**, không phải ép mọi API dùng cùng một status code.

### 14.3. Regression và các đường kiểm tra phụ

Sau khi sửa T-05, phải đảm bảo:
- Alice vẫn tải kết quả hợp lệ.
- Role hỗ trợ không tự mở đường đọc dữ liệu.
- Job bị hủy/hết hạn không còn truy cập nếu policy yêu cầu.
- Worker không xuất sai tenant.
- Audit logging ghi cả allow/deny theo yêu cầu.
- Cấu hình của cả hai region và mixed-version window không tạo bypass.
- Các business flows khác vẫn hoạt động.

Một fix “chặn mọi download” có thể giúp negative test PASS nhưng làm hỏng nghiệp vụ. **Không đóng finding** khi positive/regression criteria chưa đạt.

## 15. Bước 7 — Đánh giá rủi ro và severity

Dùng phương pháp risk assessment của tổ chức. Trong lab, có thể cân nhắc:

| Yếu tố | Câu hỏi |
|---|---|
| **Data sensitivity** | Nội dung export có dữ liệu nhạy cảm/riêng tư không? |
| **Exposure** | Ai có thể chạm đường lỗi và từ mạng/vai nào? |
| **Exploitability** | Điều kiện cần để lạm dụng link/job là gì? |
| **Blast radius** | Một file, nhiều file, nhiều tenant hay cả service? |
| **Detection** | Có audit/log/alert xác minh được không? |
| **Persistence** | Link/file tồn tại bao lâu, có revoke được? |
| **Compensating controls** | Có lớp khác giảm rủi ro được chứng minh không? |
| **Uncertainty** | Test chỉ một kịch bản hay có evidence về variant rộng hơn? |

### 15.1. Inherent risk, residual risk, confidence

Đừng gộp:
- **Inherent risk:** hậu quả và khả năng trong bối cảnh chưa xét mitigation dự kiến.
- **Residual risk:** phần còn lại sau control thực tế; chỉ giảm nhãn khi có cơ sở.
- **Assurance confidence:** độ tin rằng kết luận đúng với scope, dựa trên chất lượng evidence.

Một kết luận **confidence cao rằng authorization đang FAIL** vẫn có thể dẫn tới rủi ro nghiêm trọng. Ngược lại, confidence thấp không phải dấu hiệu rủi ro thấp; nó cho biết **cần thêm evidence**.

### 15.2. Phân loại mức ưu tiên cho lab

| Nhóm | Ví dụ | Xử lý tham khảo |
|---|---|---|
| **Blocking issue** | Đọc tài liệu trái tenant đã tái hiện, không có ngoại lệ hợp lệ | NO-GO/hold exposure, fix và retest |
| **High-priority control gap** | Thiếu log download khiến không phát hiện được hành động quan trọng | Sửa/parser retest, đánh giá thời kỳ mất log |
| **Material uncertainty** | Region-b/worker chưa có runtime evidence | Thu evidence trước claim full production |
| **Lower-impact observation** | Báo cáo thiếu định dạng hoặc metadata không ảnh hưởng quyết định trọng yếu | Cải tiến hồ sơ, theo dõi có owner |

Severity, SLA và quyền chấp nhận rủi ro là **quy định tổ chức**, không có bảng gợi ý nào trong lab tự thay thế chính sách thật.

## 16. Bước 8 — Ghi findings có thể giao việc và retest

Một finding tốt cần trả lời:

**Criteria → Condition → Evidence → Scope → Impact → Root-cause hypothesis → Owner → Recommended action → Closure criteria → Retest evidence.**

### 16.1. Finding mẫu F-01 — Cross-tenant export download

~~~yaml
finding:
  id: F-01
  title: "Export file can be retrieved outside authorized tenant scope"
  source: "Fictional evidence pack E-07"
  requirement_refs: [SEC-AUTHZ-02, SEC-LINK-05]
  affected_scope:
    release_candidate: rc-2
    endpoint: "GET /v2/exports/{jobId}/download"
    data_type: synthetic-export-archive
  expected:
    - "Unauthorized tenant cannot retrieve contents or a usable capability"
  observed:
    - "Tenant-b fixture received tenant-a export contents"
  impact: "Potential cross-tenant confidentiality breach"
  severity_proposal: CRITICAL
  evidence_refs: [E-07]
  root_cause: "NOT_YET_CONFIRMED"
  remediation_owner_role: EXPORT_SERVICE_OWNER
  actions:
    - "Review authorization at job lookup and artifact retrieval"
    - "Bind download capability to intended authorization model"
    - "Review all export/download routes and shared worker paths"
  verification_criteria:
    - "Negative cross-tenant tests pass without data exposure"
    - "Positive authorized download still works"
    - "TTL, revocation, support-role and alternate-path tests pass"
    - "Fix deployed to all approved production targets"
    - "Independent reviewer checks evidence and authorizes closure"
  status: OPEN
~~~

**Điểm quan trọng:** dù E-07 chứng minh có kết quả trái tiêu chí trong fixture, **nguyên nhân gốc vẫn cần xác minh**. Không nên khẳng định sai ở một dòng code cụ thể khi chưa có source review.

### 16.2. Finding mẫu F-02 — Logging download

| Thuộc tính | Nội dung |
|---|---|
| ID | F-02 |
| Requirement | SEC-LOG-06 |
| Expected | Sự kiện tải file hợp lệ/bị từ chối được ghi theo tiêu chí và đến SIEM |
| Observed | E-10 cho biết parser không nhận dạng event mới; E-15 thiếu source coverage |
| Risk | Mất dấu vết truy cập và giảm detection |
| Owner | Logging platform + Export application owners, A theo control catalog |
| CAP | Cập nhật event schema/parser, kiểm tra source health và alert |
| Closure criteria | Test synthetic event end-to-end, đối chiếu population, xác nhận thời kỳ |
| Limitation | Log sau sửa không tự khôi phục thời kỳ trước nếu dữ liệu lịch sử đã mất |

### 16.3. Finding/gap mẫu F-03 — Runtime rollout chưa đủ

| Thuộc tính | Nội dung |
|---|---|
| ID | F-03 |
| Requirement | SEC-BUILD-07 / SEC-REL-08 |
| Expected | Đúng candidate được triển khai ở đúng region và có compatibility proof |
| Observed | Region-a rc-2, region-b rc-1 tại T |
| Category | Release readiness gap / status mismatch |
| Owner | Release manager + SRE owner |
| Next action | Xác định đây là staged rollout có chủ đích hay triển khai chưa hoàn tất; kiểm tra mixed-version |
| Closure criteria | Manifest/runtime digest, feature exposure, compatibility và post-release checks |
| Result | Không được dùng “rc-2 đã full deployed” trước khi xác minh |

### 16.4. Bài tập cho người học

Tự viết ít nhất **ba findings hoặc evidence gaps** nữa:
- Support role thiếu phê duyệt/quyền hạn (E-08).
- DR recovery với key/worker mới chưa kiểm chứng (E-14).
- Storage/evidence completeness của region-b (E-09, E-11).
- Worker authorization chưa có test riêng (E-05..E-07).

Mỗi mục cần ghi **có lỗi thực được chứng minh hay chỉ thiếu bằng chứng**, không dùng một loại trạng thái cho tất cả.

## 17. Bước 9 — Corrective Action Plan và xác minh khắc phục

Finding không được xem là hoàn thành chỉ vì team tạo pull request hoặc ghi ticket Done.

### 17.1. CAP đề nghị

| Action ID | Finding | Người thực hiện | Công việc | Bằng chứng đóng |
|---|---|---|---|---|
| **A-01** | F-01 | Export engineering | Sửa authz lúc lấy link và lúc đọc artifact | Code/config change + negative/positive retest |
| **A-02** | F-01 | API platform | Kiểm kê mọi đường export/download và role | Route/role inventory + coverage review |
| **A-03** | F-02 | Logging/SOC | Cập nhật parser, test source-to-SIEM | Event test + parser version + alert evidence |
| **A-04** | F-03 | Release/SRE | Kiểm tra compatibility, triển khai đúng digest | Deployment logs + runtime inventory |
| **A-05** | E-08 gap | IAM/control owner | Review support role và approval workflow | Approved role matrix + denied/allowed tests |
| **A-06** | E-14 gap | SRE/DR owner | Kiểm tra restore path cho release mới | Drill result + data/key integrity checks |
| **A-07** | Toàn review | Security assurance | Review retest, điều kiện closure, residual risk | Reviewer decision + evidence index |

### 17.2. Điều kiện xác minh đã sửa

Đối với mỗi CAP:

1. Có **closure criteria** trước retest.
2. Bản sửa thực sự được triển khai lên artifact/env trong scope.
3. Negative test của finding gốc không còn tái hiện.
4. Positive và regression tests không làm hỏng chức năng hợp lệ.
5. Biến thể có rủi ro được thử theo root cause, không chỉ một input.
6. Evidence có test run ID, version, timestamp, expected/actual, result.
7. Có review đủ độc lập theo quy định.
8. Residual risk/exception hoặc gap lịch sử được ghi riêng nếu còn.

**E-12 không đủ để đóng F-01.** Nó có giá trị như evidence về tiến độ implementation, không phải evidence verified fixed. Nếu chưa test đúng bản sửa, trạng thái nên là **PENDING RETEST / NOT DEMONSTRATED**, không phải CLOSED.

## 18. Bước 10 — Xử lý ngoại lệ và chấp nhận rủi ro

Một số finding có thể chưa sửa kịp hạn. Security review phải kiểm tra cơ chế quản trị, không tự đưa quyết định chấp nhận rủi ro.

Một exception hợp lệ tối thiểu gồm:
- Requirement/control bị sai khác.
- Asset, role, environment, tenant/route, release và thời gian.
- Rủi ro và lý do không thể đáp ứng.
- Compensating controls **có bằng chứng hiệu quả**.
- Owner, approver có đúng delegation, thời hạn và review triggers.
- CAP, mốc khắc phục và điều kiện kết thúc.

**Không có approval trong E-13**, nên reviewer không được ghi “risk accepted” đối với F-01/F-02. Ngay cả khi có approval, cũng không được gọi technical FAIL thành PASS.

**Giới hạn quan trọng:** một quyết định nội bộ không thể xóa nghĩa vụ pháp luật/hợp đồng khi tổ chức không có quyền miễn trừ. Dữ liệu khách hàng và cross-tenant confidentiality có thể chịu yêu cầu không được phép vượt qua bằng một approval thông thường.

## 19. Bước 11 — Quyết định GO/NO-GO theo evidence

Một mẫu release security gate:

| Gate | Điều kiện | Evidence pack | Trạng thái tại review |
|---|---|---|---|
| **G1: Scope/manifest** | Candidate và affected asset/route đầy đủ | E-01, E-05, E-11 | **PARTIAL** |
| **G2: AuthN/AuthZ** | Không có đường trái quyền trong scope | E-04..E-08 | **FAIL** vì E-07 |
| **G3: Data protection** | Storage/link controls phù hợp | E-07, E-09 | **FAIL/PARTIAL** |
| **G4: Auditability** | Event quan trọng tới SIEM và alert | E-10, E-15 | **FAIL** |
| **G5: Evidence quality** | Không còn data gap trọng yếu | E-05, E-09, E-15 | **NOT DEMONSTRATED** |
| **G6: Release/rollback** | Region, version, compatibility, recovery phù hợp | E-01, E-11, E-14, E-16 | **NOT DEMONSTRATED** |
| **G7: Findings disposition** | Blocking findings verified fixed hoặc có quyết định hợp lệ | E-12, E-13 | **NOT SATISFIED** |

### 19.1. Quyết định khuyến nghị trong lab

**Đề xuất của security reviewer: NO-GO cho full production release hoặc kích hoạt tính năng export trên diện rộng**, do có phản chứng trực tiếp về cross-tenant export download (E-07), logging chưa đạt (E-10) và bằng chứng về rollout/coverage còn thiếu.

Kết luận này là **khuyến nghị kỹ thuật trong tình huống giả định**, không phải approval/decision của một hệ thống thật. Có thể nghiên cứu phương án deploy artifact nhưng **giữ feature export không reachable/không được kích hoạt** trong điều kiện phù hợp, với review độc lập về feature flag, route exposure và đúng quyền quyết định. Không tự coi “feature flag off” là control authorization.

### 19.2. Điều kiện đánh giá lại

Chỉ xem xét GO lại khi:
1. F-01 được sửa và retest đủ scope, có kiểm tra biến thể/đường thay thế.
2. F-02 được xử lý và xác minh audit events đạt criteria; lịch sử mất log được ghi đúng.
3. Support role được review, quyền hợp lệ và auditable.
4. Manifest/build/deploy coverage được đối chiếu cho hai region theo kế hoạch.
5. Negative/positive/regression và mixed-version checks đạt.
6. Data protection và DR dependencies có bằng chứng theo mức rủi ro.
7. Không còn blocker chưa có disposition hợp lệ; residual risks được owner đúng quyền quyết định.
8. Reviewer đánh giá **đúng release candidate mới** nếu có PR sửa làm thay candidate.

### 19.3. Một quyết định GO không được phát biểu quá mức

Thay vì “Hệ thống an toàn 100%”, hãy viết:

> “Các mandatory security gates của REL-DS-024 candidate rc-X được chứng minh đạt theo criteria và phạm vi review được ghi trong báo cáo. Những rủi ro ngoài phạm vi, bất định và yêu cầu theo dõi được liệt kê; owner và authority đã chấp nhận điều kiện cần thiết. Kết luận sẽ được xem lại khi candidate, trust boundary, dependency hoặc threat thay đổi.”

Không có security review nào chứng minh **an toàn tuyệt đối cho mọi future state**.

## 20. Bước 12 — Viết Security Review Report

Báo cáo phải phục vụ ít nhất ba nhóm đọc:
- **Engineering/SRE:** cần biết vấn đề, cách tái hiện hợp pháp, action, owner, closure criteria.
- **Business/risk/release authority:** cần hiểu tác động, blocker, trade-off, quyết định và giới hạn.
- **Audit/assurance:** cần theo được criteria → claim → argument → evidence → finding → decision.

### 20.1. Cấu trúc báo cáo đề nghị

~~~text
SECURITY REVIEW REPORT
1. Document control and review mandate
2. Executive summary and decision recommendation
3. Scope, exclusions, assumptions and limitations
4. Release manifest, assets, identities and data classification
5. Architecture, data flows, trust boundaries
6. Security objectives, policy and control criteria
7. Risk/threat scenarios and prioritization
8. Test methodology and coverage
9. Control-claim-evidence assessment
10. Findings and evidence gaps
11. CAP, assigned owners and verification criteria
12. Risk acceptance/exceptions and open questions
13. Release GO/NO-GO gates and decision authority
14. Post-release monitoring and review triggers
15. Evidence index and appendices
~~~

### 20.2. Mẫu executive summary có nội dung

> **Review:** SR-DS-024, DocSphere REL-DS-024 rc-2; nguồn đánh giá là evidence pack mô phỏng E-01..E-16.  
> **Mục tiêu:** đánh giá rủi ro bảo mật của luồng export/download, support role, audit logging và release readiness cho hai region production.  
> **Kết quả:** có phản chứng ở download authorization (E-07) và audit event ingestion (E-10). Chưa đủ bằng chứng về support least privilege, region-b deployment, dữ liệu storage/DR và kiểm thử mixed-version.  
> **Khuyến nghị:** NO-GO cho full exposure của export feature trên rc-2. Khắc phục, retest và đánh giá lại trên artifact được định danh trước khi xin phê duyệt.  
> **Giới hạn:** chưa thực thi test trên production; các kết quả là **SIMULATED**; không kết luận về tất cả kịch bản ngoài phạm vi.

Mẫu này **không phải chứng nhận bảo mật**, chỉ minh họa cách diễn đạt có trách nhiệm và không giấu findings.

### 20.3. Bảng tổng hợp findings

| ID | Chủ đề | Severity đề xuất | Status | Next action/owner |
|---|---|---|---|---|
| F-01 | Cross-tenant export content exposure | Critical giả định | OPEN / BLOCKER | Export owner, independent retest |
| F-02 | Download events không vào SIEM | High giả định | OPEN | Logging/SOC owners, end-to-end test |
| F-03 | Region-b chưa khớp rc-2 | High tùy rollout | PENDING VERIFICATION | Release/SRE, manifest/runtime |
| G-04 | Support privilege chưa chứng minh đúng | High uncertainty | UNKNOWN | IAM/control owner |
| G-05 | DR path của rc-2 chưa được kiểm tra | Material uncertainty | UNKNOWN | DR/SRE owner |
| G-06 | Region-b storage config chưa có nguồn | Material uncertainty | UNKNOWN | Evidence/platform owner |

**Không biến finding gốc bị FAIL thành UNKNOWN chỉ vì đã tạo ticket sửa.** Và **không tự gọi evidence gap là lỗ hổng khai thác được** khi chưa có quan sát.

## 21. Mẫu hồ sơ review dạng YAML

Người học có thể dùng cấu trúc sau để chuẩn hóa, nhưng **định dạng không thay việc review evidence nguồn**:

~~~yaml
security_review:
  review_id: SR-DS-024
  project: DocSphere
  release_id: REL-DS-024
  candidate: rc-2
  mode: SIMULATED_TRAINING
  review_scope_ref: "training/charter/SR-DS-024"
  review_owner_role: SECURITY_ASSURANCE_REVIEWER
  release_risk_owner_role: AUTHORIZED_RELEASE_RISK_OWNER

  security_objectives:
    - tenant-data-confidentiality
    - authorization-correctness
    - export-auditability
    - release-integrity-and-recovery

  requirements:
    - SEC-AUTHN-01
    - SEC-AUTHZ-02
    - SEC-PRIV-03
    - SEC-DATA-04
    - SEC-LINK-05
    - SEC-LOG-06
    - SEC-BUILD-07
    - SEC-REL-08
    - SEC-DR-09
    - SEC-FIND-10
    - SEC-EVD-11
    - SEC-EXC-12

  evidence:
    manifest: E-01
    requirements: E-02
    ci: E-03
    authn: E-04
    api_tests: [E-05, E-06, E-07]
    support_role: E-08
    cloud_config: E-09
    logging: [E-10, E-15]
    deployment: E-11
    remediation_ticket: E-12
    risk_exceptions: E-13
    recovery: E-14
    regression: E-16

  control_results:
    SEC-AUTHN-01: PARTIAL
    SEC-AUTHZ-02: FAIL
    SEC-PRIV-03: NOT_DEMONSTRATED
    SEC-DATA-04: PARTIAL
    SEC-LINK-05: FAIL
    SEC-LOG-06: FAIL
    SEC-BUILD-07: PARTIAL
    SEC-REL-08: NOT_DEMONSTRATED
    SEC-DR-09: NOT_DEMONSTRATED

  findings:
    - {id: F-01, status: OPEN, evidence: E-07}
    - {id: F-02, status: OPEN, evidence: E-10}
    - {id: F-03, status: PENDING_VERIFICATION, evidence: E-11}

  assessment:
    recommendation: NO_GO
    reason:
      - "Cross-tenant export download violates an explicit security requirement"
      - "Download audit event cannot be verified in SIEM"
      - "Release/environment coverage remains incomplete"
    exceptions_approved: false
    residual_risk_acceptance: NOT_RECORDED
    confidence: "sufficient for NO-GO recommendation on observed failures"
    limitations:
      - "Only fictional training evidence"
      - "No actual production testing or decision authority exercised"
    next_actions:
      - "Remediate F-01 and perform authorized retest"
      - "Fix audit parser and verify source-to-SIEM path"
      - "Reconcile both regions and mixed-version tests"
      - "Review support access and recovery dependencies"
    decision_authority_role: AUTHORIZED_RELEASE_RISK_OWNER
    decision_status: NOT_SIGNED
~~~

**Đừng để nội dung YAML gây hiểu lầm:** một file có \`recommendation: NO_GO\` chỉ là ghi nhận **khuyến nghị**, không phải một quyết định production đã được ký; \`decision_status: NOT_SIGNED\` thể hiện rõ ranh giới đó.

## 22. Xác minh coverage và chất lượng trước khi nộp

Nhà review nên tự kiểm tra gói hồ sơ bằng các câu hỏi:

### 22.1. Scope integrity

- Có đúng rc-2 và không trộn rc-1/rc-3 vào kết luận?
- Endpoint inventory có đủ 8 route, thêm đường async/legacy quan trọng nếu tồn tại?
- Đã xét cả region-a và region-b?
- Có cả human, support và machine identities trong scope phù hợp?
- Có ghi data classification và nơi file export được lưu/chia sẻ?
- Có phần out-of-scope rõ ràng, không coi nó là không có rủi ro?

### 22.2. Evidence integrity

- E-01..E-16 có liên kết tới claim và giải thích?
- Test report có expected/actual, environment, artifact và thời điểm?
- Bằng chứng từ pipeline có coverage và health checks?
- Có phân biệt design, implementation, operating effectiveness?
- Có giữ phản chứng E-07 và E-10 khi viết kết luận?
- Có nhận diện evidence nào stale hoặc thiếu nguồn?
- Có tránh sao chép secret, account ID nhạy cảm, dữ liệu khách hàng vào report?

### 22.3. Decision integrity

- Finding nào blocking và vì sao?
- Chưa đủ evidence có được ghi UNKNOWN, không tự gộp PASS?
- Risk acceptance hoặc exception có đúng thẩm quyền, thời hạn, scope?
- CAP có owner, deadline, test và retest reviewer?
- Kết luận có ghi rõ candidate, môi trường, limitation và validity triggers?
- Reviewer và risk decision authority có được phân biệt?

## 23. Rubric chấm điểm dự án

Có thể dùng bảng chấm **100 điểm** sau; các tiêu chí ưu tiên chất lượng lập luận, không ưu tiên số lượng trang.

| Tiêu chí | Điểm tối đa | Mức đạt tốt |
|---|---:|---|
| **Charter và phạm vi** | 10 | Đủ candidate, environment, data/roles, exclusions, authority |
| **Kiến trúc và trust boundaries** | 10 | Có luồng end-to-end, dependencies, đường bypass và assumptions |
| **Threat scenarios và risk analysis** | 15 | Ít nhất 6 kịch bản có impact, control, owner, uncertainty |
| **Control–claim–evidence mapping** | 20 | Ít nhất 8 control, evidence phù hợp, rõ FAIL/UNKNOWN |
| **Test matrix và coverage** | 15 | Positive/negative/regression, biến thể, artifact/region |
| **Findings, CAP và retest** | 15 | Action rõ, đúng severity/owner, closure criteria kiểm chứng |
| **Decision và residual risk** | 10 | NO-GO/GO hợp lý, blocker/authority/limitation minh bạch |
| **Báo cáo và evidence hygiene** | 5 | Có truy vết, version, privacy và lịch sử |
| **Tổng** | **100** | Không có lý do mâu thuẫn với evidence pack |

### 23.1. Những lỗi trừ điểm quan trọng

Một sản phẩm có thể trình bày đẹp nhưng **không đạt yêu cầu học tập** nếu:
- Bỏ qua E-07 và vẫn tuyên bố authz PASS.
- Dùng E-12 “ticket Done” để nói finding đã verified fixed.
- Gộp exception vào PASS mà không kiểm tra điều kiện.
- Ghi “100% production covered” dù E-11/E-15 cho thấy thiếu scope.
- Dùng kết quả mô phỏng như bằng chứng kiểm thử thực.
- Không có owner, quyền phê duyệt hoặc điều kiện đánh giá lại.

**Rubric là công cụ đánh giá bài học**, không phải tiêu chuẩn chứng nhận hoặc mô hình tính điểm an toàn của hệ thống thật.

## 24. Đáp án đối chiếu có giải thích

Người học nên hoàn thiện D1–D8 **trước khi đọc mục này**.

### 24.1. Các kết luận then chốt

**A. Cross-tenant download:** E-07 phản chứng trực tiếp claim bảo vệ nội dung export theo yêu cầu giả định. Đề xuất **NO-GO** cho việc bật tính năng export trên diện rộng là phù hợp. Không cần giả vờ có CVSS chính thức khi chưa có thông số đủ cho scoring.

**B. Logging:** E-10 và E-15 cho thấy sự kiện download không được xác minh tới SIEM. Đây không chỉ là “thiếu screenshot”: có kết quả kiểm thử cho thấy parser không nhận event mới và một coverage gap. Cần CAP, test end-to-end và đánh giá khoảng thời gian mù.

**C. Deployment:** E-11 cho thấy region-b vẫn là rc-1 tại T. Nếu rollout mới ở giai đoạn canary, điều này có thể **phù hợp kế hoạch triển khai theo giai đoạn**, nhưng không được gọi full release. Cần xem rollout charter, feature exposure và compatibility để biết đây là issue hay trạng thái đang chờ.

**D. Support:** E-08 nói quyền support vượt ranh giới có thể kỳ vọng nhưng thiếu business justification và approval. Không đủ để suy ra support đã khai thác dữ liệu; cần đánh giá least privilege, phê duyệt, logs và negative tests.

**E. Recovery:** E-14 có backup job thành công, nhưng recovery path theo key/worker mới chưa được thử. Kết luận đúng là **NOT DEMONSTRATED** cho yêu cầu khôi phục mới, không tự báo FAIL/đã có mất dữ liệu.

**F. Remediation:** E-12 chỉ xác nhận PR-77 có tiến độ. Chưa có bằng chứng fix vận hành trên đúng artifact và chưa có independent retest, nên F-01 chưa thể đóng.

**G. Supply-chain/CI:** E-03 hỗ trợ pipeline tests đã chạy theo scope, không chứng minh export link và worker dependency đều an toàn.

### 24.2. Vì sao đây là security review có giá trị?

Review giúp người ra quyết định **thấy rõ rủi ro và đường xử lý**, thay vì cố làm hồ sơ “đủ PASS”. Những control đã đạt ở một phần scope vẫn được ghi nhận, nhưng không che blocker. Evidence gaps được giao owner và có yêu cầu thu thêm. Người reviewer không tự biến khuyến nghị của mình thành approval của business risk authority.

### 24.3. Ví dụ câu trả lời ngắn cho release manager

> “Đối với DocSphere REL-DS-024 rc-2, security review ghi nhận hành vi truy xuất export trái quyền trong E-07 và lỗi ingest download audit event trong E-10. Chưa đủ evidence cho support privilege, rollout hai region và recovery path. Vì vậy khuyến nghị giữ **NO-GO cho full exposure** của export feature. Cần CAP và retest trên candidate được định danh, hoàn thiện logging, inventory/deployment evidence và review lại trước khi xin quyết định GO. Kết quả được xây trên evidence mô phỏng; đây không phải phê duyệt production thật.”

## 25. Bài nâng cao: biến review thành continuous assurance

Sau khi có report, hệ thống sẽ tiếp tục thay đổi. Để review không bị lỗi thời, hãy bổ sung:

### 25.1. Trigger đánh giá lại

- Release candidate, image digest hoặc router/export endpoint thay đổi.
- Thêm tenant, region, storage provider, support role hay kiểu tài liệu mới.
- Thay token semantics, IdP, IAM policy hoặc signing keys.
- Thay output format, SIEM parser hoặc audit event schema.
- CVE/threat intelligence mới ảnh hưởng dependency trong scope.
- Finding/incident mới, retest FAIL, exception hết hạn.
- Tính năng export được mở rộng exposure từ canary sang toàn bộ người dùng.
- Bất kỳ evidence source nào mất quyền truy cập hoặc không còn dữ liệu mới.

### 25.2. Liên kết review với release gates

~~~text
Change to export API or worker
  -> update threat and control mapping
  -> run relevant negative/positive/regression tests
  -> verify build provenance and artifact identity
  -> check deployment targets and source-health
  -> evaluate blockers and open findings
  -> reviewer decision for the scoped candidate
  -> staged rollout and monitored acceptance
  -> update security review / assurance case
~~~

### 25.3. Metrics hữu ích

| Metric | Cần đo | Điều tránh |
|---|---|---|
| Critical controls with current evidence | Tỷ lệ control trọng yếu có evidence còn phù hợp candidate | Đếm file cũ như evidence mới |
| Endpoint/role/region coverage | Tập đã test so với toàn bộ scope phải test | Loại UNKNOWN khỏi mẫu số |
| Verified closure rate | Finding đã retest và đúng closure criteria | Đếm ticket Done là fixed |
| Post-release security regression | Control suy yếu do release mới | Chỉ theo dõi 5xx/latency |
| Evidence gaps by risk | Nguồn/đường chưa chứng minh, mức tác động | Che thiếu nguồn bằng tổng điểm trung bình |
| Exception expiry and review | Sai khác có thời hạn và owner | Xem exception là PASS kỹ thuật |
| Time to detect/export incident | Khả năng phát hiện/đối soát truy cập | Không kiểm tra log source completeness |

Một review tốt luôn có **owner, ngày/điều kiện hiệu lực và kế hoạch cập nhật**. Tài liệu bị để quên sau một release lớn dần mất giá trị assurance.

## 26. Lỗi phổ biến khi làm dự án Security Review

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ checklist “secure/insecure” | Không có criteria, scope và lý do | Review charter và claim cụ thể |
| Đếm test PASS, bỏ đường chưa thử | False assurance | Coverage matrix và uncertainty |
| Thấy CI xanh là phát hành được | Không phản ánh rủi ro tương tác | Release-level threat and gate review |
| Dùng screenshot thiếu resource/time | Không biết evidence thuộc đâu | Provenance, timestamp, environment |
| Không phân biệt tenant/role | Bỏ lỗ hổng object authorization | Negative/positive tests có fixture đa tenant |
| Không review worker và link | Chỉ thử tạo job, bỏ đường tải | End-to-end flow và trust boundary |
| Quên logging/detection | Không phát hiện misuse hoặc evidence gap | Source-to-SIEM test và source health |
| Xem PR merge là remediation closure | Fix có thể chưa deploy | Artifact/runtime proof, independent retest |
| Gộp risk accepted vào PASS | Sai tình trạng kỹ thuật | Kết luận technical và risk decision riêng |
| Đánh giá staging rồi suy production | IAM/config/version khác nhau | Equivalence và production-safe checks |
| Bỏ qua canary/mixed-version | Failure trong giai đoạn rollout | Compatibility tests và guardrails |
| Gán mọi action cho “Security” | Không ai có quyền thực thi | Owner/RACI/escalation |
| Không có phản chứng trong report | Quyết định thiên lệch | Giữ và xử lý FAIL, incident, data gaps |
| Không bảo vệ dữ liệu evidence | Review có thể làm lộ thông tin | Synthetic data, RBAC, retention |
| Không làm mới review sau change | Claim dựa evidence cũ | Change triggers và reassessment |
| Dùng kết quả học tập giả làm chứng nhận thật | Gây hiểu lầm nghiêm trọng | Gắn SIMULATED và giới hạn cụ thể |

## 27. Checklist cuối trước khi nộp bài

- [ ] D1 có charter, release candidate, scope và out-of-scope.
- [ ] D2 có data-flow diagram, trust boundaries và danh mục assets/owners.
- [ ] D3 có ít nhất sáu risk scenarios gắn với security objectives.
- [ ] D4 có ít nhất tám control claims cùng evidence/status/limitations.
- [ ] D5 có negative, positive và regression tests cho export/download.
- [ ] Đã xét service identities, support role, tenant boundaries, object storage.
- [ ] Đã phân biệt review thiết kế, triển khai và hiệu quả vận hành.
- [ ] Đã đánh giá quality, coverage, timeliness và provenance của evidence.
- [ ] Đã giữ nguyên phản chứng E-07, E-10 và không che các thiếu sót E-11/E-15.
- [ ] D6 có findings với criteria, expected/actual, impact, owner và CAP.
- [ ] Mỗi finding có closure criteria, retest plan và reviewer phù hợp.
- [ ] D7 có GO/NO-GO recommendation đúng phạm vi và quyền quyết định.
- [ ] Risk accepted/exception chỉ xuất hiện khi có approval hợp lệ.
- [ ] D8 có executive summary, evidence index, assumptions và limitations.
- [ ] Report ghi rõ đây là dữ liệu **SIMULATED**, không phải production evidence.
- [ ] Không có secret, token thật hoặc dữ liệu khách hàng trong tài liệu.
- [ ] Có triggers đánh giá lại khi release, config, asset hay threat thay đổi.
- [ ] Không đánh đồng “ticket Done”, “scan clean” và “security verified”.

## 28. Tổng kết

Dự án **Tạo security review** giúp chuyển kiến thức về risk management, security requirements, threat modeling, access control, audit, remediation, exception và release assurance thành **một bộ quyết định có thể truy vết**.

Một security review chất lượng **không nhất thiết có nhiều trang hoặc tất cả ô đều xanh**. Nó phải trả lời được:

1. **Đánh giá điều gì?** Một candidate, hệ thống, phiên bản và data flow có ranh giới rõ.
2. **Theo tiêu chí nào?** Yêu cầu, control objective và mức rủi ro áp dụng.
3. **Dựa trên bằng chứng nào?** Nguồn, thời điểm, population, phương pháp và tính đầy đủ.
4. **Điều gì chưa đạt hoặc chưa biết?** Findings, phản chứng, thiếu coverage và assumptions.
5. **Ai xử lý?** Control owner, remediation owner, evidence owner, reviewer và risk authority.
6. **Quyết định nào phù hợp?** GO, limited GO, HOLD hoặc NO-GO có căn cứ và điều kiện.
7. **Khi nào đánh giá lại?** Khi fix/retest, release, asset, policy hoặc threat thay đổi.

Trong module **SECURITY_SECURITY_ASSURANCE**, chuỗi bài học được hiện thực hóa thành:

**Security objective → Review scope → Threat/risk → Control criteria → Claim–Argument–Evidence → Security tests và quality review → Findings/CAP → Independent retest → Release/risk decision → Continuous assurance.**

Kết quả của dự án là một **security review package có thể giải thích và kiểm toán**, giúp các đội phát triển/vận hành đưa ra quyết định bảo mật trên cơ sở bằng chứng thay vì phỏng đoán hoặc checklist hình thức.
