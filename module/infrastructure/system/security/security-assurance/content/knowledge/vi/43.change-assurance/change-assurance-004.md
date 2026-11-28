# Pre-change evidence: Bằng chứng trước thay đổi để bảo đảm triển khai an toàn

Một nhóm vận hành chuẩn bị cập nhật chính sách IAM của môi trường production. Pull request đã được duyệt, pipeline CI hiển thị xanh và change ticket có ghi “đã kiểm tra”. Sau triển khai, dịch vụ thanh toán không thể ghi vào queue; nhóm muốn rollback nhưng không lưu được cấu hình hiệu lực của quyền truy cập trước đó, cũng không biết tài khoản nào mới phát sinh ngoài danh sách được review. Khó khăn không chỉ nằm ở thao tác sửa lỗi: **không có bằng chứng đáng tin về trạng thái trước thay đổi để so sánh, kiểm chứng và khôi phục**.

**Pre-change evidence** (bằng chứng trước thay đổi) là tập dữ liệu, kết quả kiểm tra, quyết định và hiện vật được **thu thập, xác minh và bảo quản trước khi một thay đổi được thực thi lên phạm vi mục tiêu**. Nó giúp trả lời: hệ thống hiện ở trạng thái nào, thay đổi dự định tác động tới cái gì, yêu cầu bảo mật và rủi ro nào đang tồn tại, các điều kiện sẵn sàng đã đạt hay chưa, ai phê duyệt, và nếu triển khai hoặc rollback gặp sự cố thì lấy mốc nào để kiểm tra?

Trong chương **Change assurance** của module **SECURITY_SECURITY_ASSURANCE**, pre-change evidence được xem là một phần của lập luận bảo đảm có chứng cứ: **security objectives → change scope → baseline và risk assessment → test/authorization → release gate → đo hậu thay đổi → findings/remediation**. Tài liệu không chỉ phục vụ Change Advisory Board (CAB) mà còn hỗ trợ engineering, security review, audit, incident response, disaster recovery và đánh giá liên tục trong phát triển/vận hành.

Sau bài học, người học có thể xác định những bằng chứng cần thu trước mỗi loại thay đổi, lập baseline đúng phạm vi và thời kỳ, phân biệt chứng cứ thiết kế/kiểm thử/phê duyệt, kiểm tra độ tin cậy và tính sẵn sàng rollback, tổ chức evidence manifest, đặt điều kiện GO/NO-GO rõ ràng và xử lý khoảng trống bằng chứng một cách có trách nhiệm.

## 1. Pre-change evidence khác gì một change ticket?

**Change ticket** là hồ sơ quản trị yêu cầu và tiến độ thay đổi. **Pre-change evidence** là những dữ kiện hỗ trợ quyết định rằng thay đổi **được hiểu đủ, có điều kiện triển khai và có thể kiểm tra hậu quả**. Ticket thường chứa liên kết tới evidence nhưng không thay thế bản thân evidence.

| Đối tượng | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Change request** | Muốn thay đổi điều gì, lý do, thời gian và người chịu trách nhiệm? | CR-1042: thu hẹp quyền IAM cho dịch vụ thanh toán. |
| **Pre-change baseline** | Trước triển khai, cấu hình và hoạt động thực tế ra sao? | Export effective permissions, quyền runtime, tỷ lệ giao dịch thành công. |
| **Risk/impact assessment** | Nếu thay đổi sai hoặc không thay đổi, điều gì có thể xảy ra? | Mất quyền gửi queue, lộ dữ liệu, gián đoạn giao dịch hoặc mất log. |
| **Pre-change test evidence** | Thay đổi dự kiến đã được kiểm tra đủ trong điều kiện nào? | Test allow/deny, integration, backup/restore rehearsal, config policy gate. |
| **Approval evidence** | Ai có thẩm quyền cho phép thực hiện và trong điều kiện nào? | Chữ ký điện tử gắn đúng revision, scope, cửa sổ thay đổi. |
| **Change execution evidence** | Sau khi bắt đầu, bước nào đã diễn ra? | Deployment log, run ID, artifact digest. |
| **Post-change evidence** | Trạng thái mới có đáp ứng acceptance/security criteria? | Effective policy mới, kiểm thử nghiệp vụ và log sau deploy. |
| **Rollback/failback evidence** | Phương án phục hồi có được thực hiện và kiểm chứng? | Restore test, revert record, đối soát dữ liệu sau phục hồi. |

**Không được dùng một bản post-change screenshot để giả định trạng thái pre-change.** Khi baseline gốc thiếu, không thể suy ngược đáng tin trạng thái cũ chỉ từ cấu hình hiện tại. Tương tự, việc pipeline được duyệt không có nghĩa rủi ro triển khai bằng không.

### 1.1. Các thời điểm cần tách

~~~text
T_identify     Xác định nhu cầu thay đổi
T_assess       Phân tích rủi ro và phạm vi
T_prepare      Thu baseline, kết quả test và approvals
T_freeze       Chốt phiên bản phạm vi/plan/evidence đủ điều kiện
T_execute      Bắt đầu thay đổi tại môi trường mục tiêu
T_verify      Kiểm chứng trạng thái mới và tác động nghiệp vụ
T_close       Review, lưu kết luận, mở findings khi cần
~~~

Pre-change evidence chủ yếu được tạo trong giai đoạn **trước T_execute**, nhưng có thể cần refresh ngay sát thời điểm triển khai nếu hệ thống thay đổi liên tục. Mọi thay đổi phạm vi hoặc risk condition sau khi phê duyệt cần có quy tắc **reassessment**; không dùng approval cũ cho revision mới ngoài điều kiện.

## 2. Pre-change evidence là một luận điểm assurance

Hãy xem claim: “Thay đổi chính sách truy cập có thể được triển khai với rủi ro trong mức chấp nhận được và có thể xác minh hậu triển khai.”

Một assurance case cho claim này có thể phân rã:

~~~mermaid
flowchart TD
    O["Security objective: bảo vệ dữ liệu và duy trì dịch vụ"] --> C["Claim: change đủ điều kiện được thực hiện"]
    C --> S["Scope và dependencies đã được chốt"]
    C --> R["Risk/impact và threats đã được đánh giá"]
    C --> B["Current-state baseline đáng tin"]
    C --> T["Test và rollback readiness có bằng chứng"]
    C --> A["Approval đúng thẩm quyền và đúng revision"]
    S --> E["Evidence package: inventory, diagram, diffs, tests, signatures"]
    R --> E
    B --> E
    T --> E
    A --> E
    E --> G{"Pre-change gate"}
    G -->|GO| X["Triển khai có kiểm soát và kiểm chứng sau thay đổi"]
    G -->|NO-GO / INCONCLUSIVE| Y["Giải quyết gap, giảm scope, replan hoặc escalate"]
~~~

**Warrant** của lập luận phải giải thích vì sao các nguồn evidence được chọn **đủ bao phủ các đường tác động quan trọng**. Ví dụ kiểm thử trên staging chỉ hỗ trợ dự đoán production nếu khác biệt cấu hình, dữ liệu, scale và quyền đã được đánh giá. Nếu staging dùng fake IAM policy và production dùng federation khác, một bài test xanh chưa đủ.

### 2.1. Bằng chứng tốt không đồng nghĩa kết quả tốt

Bộ pre-change evidence có thể rất đầy đủ nhưng lại chứng minh một **điều kiện NO-GO**: backup restore test thất bại, quyền rollback không tồn tại, hoặc có đường network bypass. Đây vẫn là bằng chứng có giá trị vì giúp tổ chức tránh một thay đổi không kiểm soát được.

Một hồ sơ được trình bày đẹp, nhiều tài liệu nhưng không có provenance, scope hoặc acceptance criteria chưa tạo ra assurance. Cần phân biệt **sự tồn tại của artifact** với **khả năng artifact hỗ trợ quyết định**.

## 3. Bốn nhóm mục tiêu cần chứng minh trước thay đổi

### 3.1. Tính chính xác của phạm vi

Change ảnh hưởng những service, tài sản, tài khoản, dữ liệu, dependency, tenant, region và nhóm người dùng nào? Có môi trường dự phòng, tác vụ batch, tài khoản máy và hỗ trợ bên thứ ba nằm ngoài mô tả ban đầu không?

### 3.2. Trạng thái và hiệu lực kiểm soát trước thay đổi

Đã biết **effective state** trước triển khai hay chỉ biết file cấu hình dự kiến? Các controls IAM, encryption, logging, monitoring, backup và policy enforcement đang hoạt động ở mức nào, có findings hoặc exceptions còn mở không?

### 3.3. Khả năng thực hiện và khôi phục có kiểm chứng

Artifact định triển khai, phương án change, pre-deployment tests, test cases quan trọng và rollback/runbook có đúng revision, quyền và môi trường? Đã có mốc trạng thái đủ tin cậy để đối chiếu sau change chưa?

### 3.4. Quyền quyết định và khả năng giải trình

Change có được phê duyệt theo rủi ro và đúng thẩm quyền? Approval dựa trên evidence nào, còn hiệu lực trong cửa sổ nào và những điều kiện nào buộc dừng hoặc đánh giá lại?

Các nhóm mục tiêu cần **cùng lúc** được đáp ứng. Ví dụ backup đã được tạo nhưng không ai kiểm tra khả năng phục hồi; hoặc test hoàn tất nhưng change chưa được duyệt cho production. Không thể coi GO từ một nhóm PASS riêng lẻ.

## 4. Phân loại thay đổi và chọn mức evidence tương xứng

Không nên bắt một thay đổi văn bản không ảnh hưởng runtime phải có cùng hồ sơ với việc đổi encryption key của production. Nhưng cũng không nên gán nhãn “standard change” rồi bỏ qua đánh giá scope và tác động khi thực tế có quyền truy cập rộng hoặc dữ liệu nhạy cảm.

| Nhóm thay đổi | Ví dụ | Evidence trọng yếu |
|---|---|---|
| **Thay đổi chuẩn/lặp lại đã được phê duyệt (standard)** | Triển khai một image đã ký trên scope quen thuộc qua pipeline ổn định. | Change model/version, kiểm thử định kỳ, artifact provenance, kiểm tra scope/drift, điều kiện thực thi. |
| **Thay đổi thông thường (normal)** | Đổi IAM role, firewall rule, storage policy, phiên bản dịch vụ. | Inventory, risk assessment, diff, test, approvals, rollback và acceptance plan. |
| **Thay đổi lớn / high-risk** | Chuyển vùng dữ liệu, schema migration, đổi IdP, key rotation trọng yếu. | Dependency/impact analysis sâu, integrity baseline, DR/readiness, rehearsal, decision gates và owner nhiều bên. |
| **Emergency change** | Cô lập vùng mạng đang bị tấn công, revoke compromised key. | Incident ID, thẩm quyền khẩn, scope tối thiểu, mốc trước hành động khi khả thi, recording và review hậu kiểm. |
| **Change có nghĩa vụ bên ngoài** | Thay data location, subprocessor, retention hoặc encryption cam kết. | Điều khoản/hợp đồng, legal/privacy assessment, approvals/notifications theo yêu cầu áp dụng. |

Các nhóm trên chỉ để hướng dẫn. Quy tắc thực tế phải dựa vào **risk policy, business impact, nghĩa vụ và mức thay đổi**, không chỉ tên loại ticket.

### 4.1. Tập chứng cứ tối thiểu không đồng nhất

Một minor feature flag có thể chỉ cần trạng thái trước, phạm vi, test, quyền thay đổi và khả năng tắt lại. Một database migration có thể cần bản sao dữ liệu, kế hoạch backfill, reconciliation queries, validation, pause writes, RPO/RTO và quyết định khi rollback không thể phục hồi dữ liệu.

**Evidence depth = mức đủ để hỗ trợ quyết định theo rủi ro**, không phải số lượng file càng nhiều càng tốt.

## 5. Xác định phạm vi: Asset population và dependency mapping

Một change mô tả “deploy lên dịch vụ A” chưa đủ khi A gọi queue B, database C, authentication D và được giám sát bằng logging pipeline E. Thay đổi IAM cho A có thể làm hỏng B; thay đổi network gateway có thể khiến E không thu được log; thay đổi storage encryption có thể làm job backup không đọc dữ liệu.

### 5.1. Những thuộc tính cần có

| Trường | Câu hỏi |
|---|---|
| **Change ID và revision** | Quyết định đang áp dụng cho bản kế hoạch/mã nào? |
| **Assets/resource IDs** | Có danh sách account, region, cluster, hosts, namespaces và resource ổn định? |
| **Business services** | Dịch vụ và quy trình nghiệp vụ nào có thể bị ảnh hưởng? |
| **Data scope** | Loại dữ liệu, mức nhạy cảm, volume và luật/điều khoản liên quan? |
| **Identity/network paths** | Human/machine identities, role, trust boundary và đường truy cập nào? |
| **Upstream/downstream** | Các thành phần nào gửi/nhận dữ liệu hoặc sự kiện? |
| **Recovery dependencies** | Backup, KMS, IdP, DNS, control plane và đường quản trị có nằm trên đường phục hồi? |
| **Owners/approvers** | Ai sở hữu service, dữ liệu, security controls và quyết định change? |
| **Current exceptions/findings** | Có ngoại lệ đang còn hạn, rủi ro đã chấp nhận hoặc issue chưa khắc phục? |
| **Coverage limits** | Nguồn inventory có thể thiếu account, region hoặc phần hệ thống bên thứ ba nào? |

### 5.2. Đối chiếu nguồn inventory

Nên đối chiếu CMDB/service catalog với cloud API, IaC state và runtime discovery, tùy công nghệ. Nếu IaC chỉ quản lý 80 trên 100 resource, diff IaC không đại diện cho 20 resource ngoài kiểm soát. Ghi rõ 80/100 đối tượng đã đối chiếu và 20 đối tượng cần xử lý, thay vì kết luận “toàn bộ fleet đã được kiểm tra”.

### 5.3. Blast radius

~~~mermaid
flowchart LR
    CH["Change: thu hẹp IAM role"] --> API["API payment service"]
    API --> Q["Payment queue"]
    API --> DB["Transaction DB"]
    API --> LOG["Audit logging pipeline"]
    API --> BACKUP["Backup/restore workflows"]
    ID["Service identity & secret"] --> API
    NET["Network/IAM trust boundary"] --> API
~~~

Đường tác động không chỉ gồm những service trực tiếp được sửa. Khi service identity mất quyền, **backup job** hoặc **log shipping** có thể hỏng mà health check API vẫn xanh. Evidence trước change phải xác định các tính năng **critical-path và control-path** để xây dựng bộ kiểm chứng phù hợp.

## 6. Thu Current-state baseline có nguồn gốc rõ

**Baseline trước thay đổi** là trạng thái đã quan sát, có timestamp, scope và phương pháp thu, dùng làm điểm so sánh sau triển khai hoặc khi điều tra. Baseline không nhất thiết là trạng thái “an toàn”; có thể chứa cấu hình lỗi hoặc finding đang mở, và điều đó phải được ghi.

### 6.1. Các lớp baseline

| Lớp | Ví dụ cần chốt | Tác dụng |
|---|---|---|
| **Configuration baseline** | Effective IAM policy, firewall routes, TLS settings, feature flags, IaC state. | So sánh chính xác cấu hình trước/sau, phát hiện drift. |
| **Asset baseline** | Accounts, instances, services, deployment versions, image digests. | Biết đối tượng nào thuộc scope và version cũ khi rollback. |
| **Security-control baseline** | MFA enforcement, audit log coverage, encryption state, segmentation, EDR health. | Phân biệt lỗi đã tồn tại từ trước với hồi quy do change. |
| **Functional baseline** | API success rate, job queue status, latency, transaction invariants. | Biết giới hạn hoạt động trước thay đổi. |
| **Data baseline** | Counts, checksums theo schema/thao tác thích hợp, sequence ID, replica lag, backup state. | Đối soát tính toàn vẹn trước/sau migration. |
| **Observability baseline** | Log source IDs, alert routes, synthetic check results, SIEM ingest latency. | Xác định có thể phát hiện sự cố hậu change. |
| **Dependency baseline** | Owner và health của IdP, KMS, DNS, secrets, upstream/downstream. | Giảm bất ngờ với điểm lỗi chung. |
| **Risk baseline** | Findings, exceptions, accepted risk và threats còn hiệu lực. | Đánh giá thay đổi rủi ro thật sự, không xóa trạng thái lịch sử. |

### 6.2. Effective state quan trọng hơn “desired state”

Một pull request thay đổi Terraform/IaC có thể hiển thị diff hợp lý nhưng production đã có **manual changes** ngoài IaC. Nếu chỉ so hai file source, có thể không biết runtime đang khác mong muốn.

Nên đối chiếu:

~~~text
Declared desired state   <- repo/IaC revision
       |
       v
Observed effective state  <- cloud/API/runtime export
       |
       v
Planned target state      <- change diff + migration steps
       |
       v
Acceptance criteria       <- expected controls + business invariants
~~~

Việc drift tồn tại trước change cần được ghi thành finding hoặc điều kiện. Không âm thầm điều chỉnh baseline để làm báo cáo “không có khác biệt”.

### 6.3. Baseline có tuổi thọ

Một IAM snapshot chụp một tuần trước deploy có thể không còn phù hợp nếu nhiều account được tạo trong tuần. Đối với high-risk change, cần quy tắc làm mới snapshot hoặc **drift check ngay trước điểm thực thi**, kèm event triggering nếu asset/permission thay đổi sau phê duyệt.

Không có một ngưỡng “baseline phải mới dưới N phút” áp dụng toàn bộ ngành. Độ mới phụ thuộc tốc độ thay đổi, impact và thời gian cần để tái thẩm định.

## 7. Thu bằng chứng về yêu cầu bảo mật và trạng thái rủi ro

Pre-change evidence không chỉ nói **hệ thống đang như thế nào**, mà còn nói **trạng thái nào được phép**.

### 7.1. Traceability từ risk đến change

Một bộ hồ sơ nên cho phép truy ngược:

~~~text
Business/security objective
   -> Threat scenario / risk ID
   -> Requirement / control ID / policy version
   -> Current-state test & findings
   -> Change objective and proposed design
   -> Pre-change test evidence and risk treatment
   -> Approval and execution gates
   -> Planned post-change verification
~~~

Ví dụ, muốn thu hẹp IAM role phải biết yêu cầu least privilege và những action hợp lệ của ứng dụng. Chỉ giảm số permission có thể “trông an toàn hơn” nhưng vẫn cho phép một quyền nguy hiểm hoặc làm hỏng luồng kinh doanh thiết yếu.

### 7.2. Những nguồn cần đối chiếu

- Control baseline và standard version, tình trạng áp dụng ở scope cụ thể.
- Threat model/attack paths liên quan đến trust boundaries thay đổi.
- Vulnerabilities và security findings đang mở, rủi ro có thể tăng sau change.
- Approved security exceptions và ngày hiệu lực/hạn.
- Data classification, privacy/contractual duties liên quan retention, locality và người nhận.
- Business impact analysis, recovery objectives hoặc service criticality.
- Chức năng bảo vệ mà change **phải giữ nguyên**, ví dụ logging và khả năng điều tra.

Một change có thể khắc phục security finding nhưng đồng thời tạo **compliance deviation khác**; risk assessment phải xem toàn bộ mục tiêu liên quan, không chỉ finding đã kích hoạt yêu cầu.

## 8. Evidence cho thiết kế thay đổi và review kiến trúc

Một bản thiết kế được duyệt là đầu vào quan trọng nhưng cần liên kết tới implementation và test đã được review.

| Nội dung thiết kế | Bằng chứng nên có | Điều cần phản biện |
|---|---|---|
| **Target architecture / data flow** | Sơ đồ trust boundary, owner, source/destination, data sensitivity. | Có đường phụ hoặc data flow không ghi trên sơ đồ không? |
| **IAM và machine identities** | Role mapping, quyền dự kiến, access paths và service-account dependencies. | Có wildcard quyền, local admin bypass, token không quản lý? |
| **Network exposure** | Ingress/egress rules, routes, service mesh policy, DNS/endpoint mapping. | Chính sách mới có làm rộng public exposure hoặc chặn log/backup? |
| **Data migration** | Schema diff, dữ liệu chuyển, backfill, consistency model, test scripts. | Có mất dữ liệu, ghi trùng, không thể rollback hay quyền đọc mới? |
| **Encryption/keys/secrets** | KMS policy, key ownership, rotation, fallback, decryption dependency. | Ai có thể decrypt, key cũ có cần cho restore không? |
| **Resilience/DR** | Replication, backup/restore, failover, RTO/RPO, runbook. | Thay đổi có phá kênh phục hồi hoặc tạo điểm lỗi chung? |
| **Observability/IR** | Audit event mapping, alert routes, on-call, incident playbook. | Sau change, dấu vết quan trọng có còn tới SIEM không? |
| **Supplier integration** | Vendor/subprocessor, API permissions, DPA, support paths. | Dữ liệu có chuyển tới đơn vị hoặc vị trí mới ngoài phạm vi duyệt? |

### 8.1. Review assumption và negative scenario

Không chỉ kiểm tra “happy path”. Đối với thay đổi cấp quyền, phải hỏi điều gì xảy ra khi secret hết hạn, API trả 403, backup cần quyền cũ hoặc principal ngoài inventory truy cập. Đối với network policy, cần kiểm tra những nguồn **phải bị chặn**, không chỉ những nguồn phải được phép.

### 8.2. Phân biệt design approval và implementation evidence

Architecture review có thể xác nhận chiến lược hợp lý, nhưng không chứng minh artifact chạy production tuân thủ thiết kế. Pre-change package nên có **liên kết đến commit, image digest, IaC plan, config bundle hoặc release candidate** để biết chính xác cái gì đã được review. Khi thay revision, một số review/test có thể không còn hiệu lực.

## 9. CI/CD, IaC và software supply-chain evidence

Với các hệ thống có pipeline tự động, pre-change evidence thường là sự kết hợp **source review → build/test → artifact provenance → planned deployment**.

~~~mermaid
flowchart LR
    SRC["Source revision + PR review"] --> BUILD["Build job / trusted workflow"]
    BUILD --> ART["Artifact digest / SBOM nếu phù hợp"]
    ART --> SCAN["Security tests + policy gates"]
    SCAN --> PLAN["Deployment/IaC plan + affected resources"]
    PLAN --> APPROVE["Change authorization gắn revision"]
    APPROVE --> RELEASE["Pre-deploy gate"]
    RELEASE --> VERIFY["Post-change evidence"]
~~~

### 9.1. Những gì cần lưu

| Bằng chứng | Vai trò |
|---|---|
| **Source revision/commit và PR** | Xác định code/config dự định thay và người review. |
| **Build run ID, environment và workflow version** | Truy nguồn cách tạo artifact. |
| **Artifact digest / package/version** | Ràng buộc dữ liệu kiểm thử và deployment target vào một artifact cụ thể. |
| **Dependency/SBOM khi phù hợp** | Hỗ trợ kiểm soát component và lỗ hổng chuỗi cung ứng. |
| **SAST/SCA/container/IaC scanning** | Phát hiện một tập rủi ro theo tool coverage. |
| **Policy-as-code outputs** | Chứng minh các guardrails được thử trên bản plan/artifact. |
| **IaC plan hoặc config diff** | Liệt kê resources dự kiến tạo/sửa/xóa. |
| **Secrets checks** | Xác nhận artifact/config không chứa secrets không được phép và phương thức phân phối khóa phù hợp. |
| **Signed approval / release authorization** | Xác định người duyệt đúng bản, phạm vi và cửa sổ deploy. |

**Pipeline xanh** chỉ chứng minh các job đã chạy theo logic được cấu hình và trả kết quả mong đợi trong kỳ đó. Nó không tự chứng minh coverage đầy đủ, không có false negatives hoặc code thực tế được triển khai giống bản đã test.

### 9.2. Gắn tất cả quyết định vào một immutable identifier

Nếu test chạy trên commit A nhưng deployment lấy image được build từ commit B, chuỗi evidence bị đứt. Một hướng quản trị là gắn:

~~~text
change_id
  -> approved_source_revision
  -> build_run_id
  -> artifact_digest
  -> security_test_run_ids
  -> infrastructure_plan_id
  -> approval_decision_id
  -> deployment_target_scope
~~~

Tùy công nghệ, có thể dùng cryptographic digest, provenance attestation, chữ ký và kho artifact có kiểm soát. Chữ ký đúng cho biết artifact gắn với khóa ký theo trust model; **không chứng minh artifact an toàn** nếu pipeline, nguồn hoặc khóa đã bị xâm nhập.

### 9.3. Chống TOCTOU (time-of-check to time-of-use)

Một plan có thể PASS lúc 10:00 nhưng production drift lúc 10:20, trong khi change thực thi 10:30. Đây là rủi ro **điều kiện đã kiểm tra không còn đúng lúc sử dụng**. Có thể giảm bằng cách refresh plan, lock state thích hợp, xác minh expected version, hạn chế concurrent changes và so lại resource population trước thao tác rủi ro cao.

## 10. Pre-change test evidence: Đã thử gì và chưa thử gì?

Bằng chứng kiểm thử cần mô tả **đối tượng, môi trường, phương pháp, dữ liệu, kết quả và giới hạn**, không chỉ số test PASS.

### 10.1. Lớp kiểm thử hữu ích

| Test | Claim có thể hỗ trợ | Không tự chứng minh |
|---|---|---|
| **Unit/security tests** | Logic code hoặc policy đáp ứng case cụ thể. | Toàn bộ behavior production hay cấu hình runtime. |
| **Integration tests** | Những dependency được mô phỏng/khởi tạo tương tác đúng. | Các dependency bị bỏ qua sẽ an toàn. |
| **Positive functional tests** | Luồng nghiệp vụ hợp lệ hoạt động. | Hành vi trái quyền đã bị chặn. |
| **Negative security tests** | Một số đường truy cập/điều kiện sai bị từ chối. | Mọi bypass path đã được thử. |
| **Performance/load tests** | Hệ thống đáp ứng tải trong cấu hình test. | Scale production có cùng giới hạn nếu khác môi trường. |
| **Policy/IaC tests** | Plan/config thỏa các rule có phạm vi đã định. | Runtime đã triển khai y hệt. |
| **Backup restore rehearsal** | Có thể phục hồi dữ liệu thử theo điều kiện được thử. | Backup production mới nhất chắc chắn restore được hoặc không mất dữ liệu. |
| **Security monitoring test** | Event thử đi qua pipeline và alert đến đúng nơi. | Không có telemetry gaps ngoài tập thử. |

### 10.2. Bằng chứng kiểm thử nên có

- Test run ID, framework/tool version, commit/artifact digest.
- Environment và những khác biệt trọng yếu so với production.
- Input dataset, loại dữ liệu an toàn, test accounts và rights.
- Điều kiện trước test, expected vs actual outcomes, timestamp.
- Cases PASS/FAIL/SKIP/INCONCLUSIVE, không chỉ tổng số thành công.
- Mẫu âm, boundary conditions, failure injection nếu được phê duyệt.
- Quan hệ test case → requirement/control/threat scenario.
- Owner của finding phát hiện và trạng thái remediation/retest.
- Bằng chứng không thử được, ngoại lệ và risk decision.

### 10.3. Nếu test thất bại thì sao?

Không tự xóa kết quả FAIL khỏi báo cáo khi đã sửa một dòng code. Phải tạo **retest run** gắn phiên bản mới; baseline cho change chỉ được xem là sẵn sàng khi các gate bắt buộc đạt hoặc có xử lý risk/exception hợp lệ theo thẩm quyền và nghĩa vụ. Đặc biệt, một exception về security test chưa hoàn tất không tự cho phép vượt yêu cầu release bắt buộc của hợp đồng.

## 11. Risk assessment cho chính hành động thay đổi

Một change có thể giảm rủi ro bảo mật dài hạn nhưng tạo rủi ro **khi triển khai**, vì vậy cần hai trục đánh giá.

### 11.1. Hai loại rủi ro

| Trục | Ví dụ | Câu hỏi |
|---|---|---|
| **Risk of not changing** | Lỗ hổng authorization tồn tại, khóa bị lộ, baseline lỗi thời. | Nếu giữ nguyên, kịch bản tấn công nào tiếp tục tồn tại và trong bao lâu? |
| **Risk of changing** | Tắt quyền queue, mất key giải mã, gây mất dữ liệu, trễ log, downtime. | Nếu triển khai sai, ảnh hưởng nghiệp vụ/bảo mật và khả năng phục hồi là gì? |

Cần quyết định cân bằng theo mức rủi ro và điều kiện cho phép. Không trì hoãn containment của incident đang diễn ra chỉ vì chưa có đủ hồ sơ normal change; sử dụng quy trình emergency có kiểm soát.

### 11.2. Threat scenarios trước change

Một threat model ngắn có thể hỏi:

1. Change có thêm trust boundary, endpoint hoặc quyền mới không?
2. Có làm rộng dữ liệu được truy xuất hoặc vùng lưu trữ không?
3. Có làm mất khả năng logging/detection hoặc chặn kênh ứng cứu không?
4. Có tạo secret/credential mới, thay đổi rotation hay root trust không?
5. Có làm mất backup, replication, failover hoặc khả năng xác minh integrity không?
6. Có phụ thuộc một vendor/cấu hình chưa có evidence không?
7. Có khả năng rollback làm tái mở lỗ hổng đang sửa không?
8. Nếu kết quả partial success, hệ thống có rơi vào trạng thái quyền không đồng nhất không?

### 11.3. Risk register trước thay đổi

Mỗi risk scenario nên có ID, asset, inherent/current risk, controls hiện tại, planned mitigation, owner, acceptance threshold, trigger dừng và evidence. Không chỉ ghi “Risk: Medium” không có luận cứ. Khi scope thay đổi đáng kể sau review, assessment cần được cập nhật.

## 12. Rollback và recovery readiness phải có bằng chứng trước

**Có một đoạn runbook rollback không có nghĩa rollback khả thi.** Những thay đổi schema, encryption, secrets, replication và quyền có thể làm rollback dữ liệu hoặc cấu hình nguy hiểm hơn giữ trạng thái mới.

### 12.1. Những câu hỏi tối thiểu

| Chủ đề | Bằng chứng cần kiểm tra |
|---|---|
| **Known-good version** | Artifact/config/version cũ có định danh chính xác và còn lấy được? |
| **Backup/recovery point** | Backup phù hợp được tạo, trạng thái thành công, có thể restore trong điều kiện cần thiết? |
| **Key/credential dependency** | Còn quyền dùng khóa cũ và đường quản trị phục hồi an toàn? |
| **Data backward compatibility** | Schema mới có ghi dữ liệu mà bản cũ không đọc được không? |
| **Rollback steps and owners** | Lệnh/chuỗi thao tác được review, quyền, người trực và điểm cần phê duyệt? |
| **Trigger and decision authority** | Error budget, security signal, integrity mismatch hoặc downtime nào buộc dừng? |
| **Maximum safe rollback window** | Sau mốc nào dữ liệu hoặc giao thức đã đổi khiến revert trực tiếp không an toàn? |
| **Recovery acceptance** | Ai xác nhận dữ liệu, chức năng và security controls sau rollback? |

### 12.2. Một rollback có thể tái mở finding

Nếu change đang khắc phục public exposure, rollback về image/config cũ có thể khôi phục lỗ hổng. Plan phải có **mitigation khi rollback** (ví dụ chặn gateway, feature flag hoặc giảm scope), không mặc định rằng khôi phục vận hành đồng nghĩa khôi phục bảo mật.

### 12.3. Kết quả diễn tập và giới hạn

Một restore test trên staging hỗ trợ khả năng phục hồi trong phạm vi kiểm thử. Nó không thay thế bằng chứng rằng **backup mới nhất** đã được tạo, có thể giải mã và khớp dữ liệu production. Đối với high-risk data change, cần chú ý transaction reconciliation, RPO/RTO thực tế và trách nhiệm đối với dữ liệu được ghi trong thời gian chuyển đổi.

## 13. Baseline dữ liệu và transaction integrity trước migration

Đối với schema/data migration, pre-change evidence cần giúp kiểm chứng **không mất, không lặp, không sai quan hệ và không vi phạm giới hạn dữ liệu**.

### 13.1. Những dữ kiện hữu ích

- **Schema version** và bảng/collection/ràng buộc sẽ bị thay đổi.
- **Population/counts** theo khóa nghiệp vụ, phân vùng hoặc thời kỳ có ý nghĩa.
- **Reference integrity:** foreign keys, uniqueness, mối liên hệ giữa bản ghi.
- **Sequence/cursor/watermark** cho CDC, queue và xử lý batch.
- **Checksum/digest** trên tập dữ liệu và cách canonicalize khi thích hợp.
- **Replication lag** và consistency model tại mốc pre-change.
- **Backup/snapshot ID**, encryption/key ID và bằng chứng restore test.
- **In-flight transactions** và cách pause/quiesce hoặc đối soát.
- **Privacy/data retention** đối với bản sao tạo thêm khi migration.

### 13.2. Hash/count không đủ cho mọi tình huống

Hai bảng có cùng số dòng vẫn có thể khác nội dung. Checksum tổng có thể không có cùng ý nghĩa nếu thứ tự, encoding hoặc kiểu dữ liệu thay đổi; phải nêu thuật toán canonicalization và phạm vi. Với hệ thống có giao dịch đang chạy, số liệu tiền/hậu thay đổi chỉ so sánh được khi đã xác định **điểm cắt giao dịch** hoặc phương pháp đối soát những thay đổi phát sinh giữa hai mốc.

Không dùng số liệu dữ liệu khách hàng thô trong ticket rộng quyền chỉ để chứng minh integrity. Lưu nguồn có kiểm soát và bản tổng hợp/đã che dữ liệu cùng lineage.

## 14. Security baseline trước thay đổi: IAM, network, secrets và audit

Các lớp bảo mật cần được đo trước khi thay đổi để phát hiện regression, nhưng mỗi lớp có kiểu evidence riêng.

### 14.1. IAM và quyền đặc biệt

- Xuất effective roles/policies và tập principals trong scope.
- Kiểm tra service identities, break-glass, local admins, external federation và quyền vendor.
- Đối chiếu access review, exceptions còn hạn và quyền dùng cho rollback.
- Xác định một bộ **allow tests và deny tests** để hậu change chứng minh least privilege và chức năng.
- Không để quá trình “thử khả năng rollback” tạo tài khoản quản trị vượt quyền không có expiry.

### 14.2. Network và trust boundary

- Ghi routes, ingress/egress, firewall policies, security groups, DNS/service discovery và network identities.
- Kiểm tra public exposure và đường tới log, backup, KMS, IdP, monitoring.
- Đặt baseline traffic/synthetic test cho những đường phải mở và những đường phải bị chặn.
- Nếu thay đổi segmentation, kiểm tra kịch bản failover và dịch vụ quản trị khẩn.

### 14.3. Secrets, encryption và key management

- Xác định key IDs/versions, owners, access policies, rotation plan, dependency để decrypt và restore.
- Không xuất plaintext secret hoặc private key vào evidence; dùng metadata và tests an toàn.
- Kiểm tra khả năng key rollover, revoke, fallback, re-encryption và backup decryption trước change.
- Bằng chứng “KMS key tồn tại” không chứng minh mọi dữ liệu mã hóa đều phục hồi được.

### 14.4. Logging, alerting, forensic readiness

- Chốt nguồn log, audit event types, retention, ingest path, timestamp và on-call route.
- Thực hiện synthetic event an toàn và xác nhận tại nơi nhận trước thay đổi khi cần.
- Ghi các logging gaps đã tồn tại để không nhầm với regression.
- Nếu thay đổi có thể ảnh hưởng SIEM, cần kênh quan sát độc lập hoặc phương án thủ công được phê duyệt.

## 15. Change windows, thẩm quyền và bằng chứng phê duyệt

Một change được kiểm thử đúng nhưng triển khai sai thời điểm hoặc sai thẩm quyền vẫn có thể tạo rủi ro.

### 15.1. Những trường nên có trong approval

| Thuộc tính | Ý nghĩa |
|---|---|
| **Change ID/revision và scope** | Approval gắn đúng bản đề xuất, artifact/plan, tài sản và mục tiêu. |
| **Reviewer roles** | Security, service owner, data owner, change authority, legal/privacy khi cần. |
| **Decision và timestamp** | APPROVED/CONDITIONAL/REJECTED với mốc hiệu lực và người quyết định. |
| **Điều kiện bắt buộc** | Test phải PASS, có backup, rollback owner và monitoring hoạt động. |
| **Maintenance window** | Thời điểm, timezone, blackout windows và người trực. |
| **Risk/exception reference** | Rủi ro được chấp nhận trong quyền nào, expiry và điều kiện. |
| **Communication plan** | Người dùng, support, vendor, incident/DR teams nào cần biết? |
| **Stop/rollback authority** | Ai có thể dừng hoặc kích hoạt rollback theo tín hiệu. |
| **Reassessment trigger** | Scope, artifact digest, data classification hoặc risk thay đổi thì duyệt lại. |

**Chữ ký phê duyệt là bằng chứng về quyết định**, không phải bằng chứng test an ninh đã đạt. Một approval thiếu thẩm quyền không được sửa bằng cách gắn nhãn “standard” sau triển khai.

### 15.2. Không phê duyệt theo tên file bất định

Thay vì “approve deployment latest-build”, nên có bản gắn commit/artifact digest, environment, manifest, plan hash/version và test run IDs. Khi pipeline tạo artifact khác, gate phải xác nhận xem approval có còn áp dụng hoặc cần review bổ sung.

## 16. Go/No-Go gates trước thời điểm triển khai

Tổ chức nên định nghĩa một bảng gate tùy mức rủi ro để có quyết định nhất quán, có thể giải thích và kiểm toán.

| Gate | Điều kiện để GO | Điều kiện NO-GO / yêu cầu điều tra |
|---|---|---|
| **G1 — Scope** | Population và dependencies đủ tin cậy, phạm vi thay đổi được chốt. | Asset quan trọng chưa xác định hoặc blast radius vượt review. |
| **G2 — Risk** | Đánh giá rủi ro hiện hành, high risks xử lý hoặc có quyết định hợp lệ. | Incident mới, exposure thay đổi, risk owner chưa ký điều kiện bắt buộc. |
| **G3 — Target artifact** | Revision/build/plan nhất quán với phần được test và review. | Artifact không khớp digest hoặc có drift ảnh hưởng kết luận. |
| **G4 — Tests** | Required positive/negative/security/functional tests đạt đúng scope. | Bypass path hoặc security gate bắt buộc FAIL, test bị skip chưa xử lý. |
| **G5 — Recovery** | Backup/rollback/forward-fix đáp ứng yêu cầu và có quyền thực hiện. | Không có khả năng restore, khóa cần thiết bị mất, plan revert gây mất dữ liệu. |
| **G6 — Observability** | Logging/metrics/alerts và kênh response đủ để nhận biết lỗi hậu change. | Thay đổi làm mù nguồn audit trọng yếu mà không có phương án an toàn. |
| **G7 — Approvals** | Đúng người, đúng revision, đúng cửa sổ, điều kiện rõ ràng. | Thiếu thẩm quyền hoặc nghĩa vụ bên ngoài chưa giải quyết. |
| **G8 — Execution readiness** | Người trực, runbook, stop threshold và communications sẵn sàng. | Không có owner quyết định dừng hoặc change window không phù hợp. |

### 16.1. GO, NO-GO và INCONCLUSIVE không phải cùng một trục

- **PASS:** Có bằng chứng đủ tin cậy rằng gate cụ thể đạt.
- **FAIL:** Có bằng chứng cho thấy gate không đạt.
- **INCONCLUSIVE:** Không đủ bằng chứng hoặc scope không xác định để kết luận.
- **NOT_APPLICABLE:** Gate thực sự không áp dụng, có lý do xác nhận.
- **GO/NO-GO:** Quyết định có thẩm quyền dựa trên kết quả các gates, rủi ro và nghĩa vụ.

Nếu một gate quan trọng **INCONCLUSIVE**, không gọi nó là PASS vì chưa thấy lỗi. Có thể chọn thu thêm evidence, giảm scope, trì hoãn hoặc sử dụng cơ chế ngoại lệ hợp lệ khi thực sự được phép; **approval không biến kết quả kiểm tra chưa xác minh thành đã đạt**.

### 16.2. Không “fix” dữ liệu bằng cách sửa ngưỡng

Nếu latency baseline đạt 100 ms nhưng dự kiến rollout có thể tăng lên 400 ms, phải đánh giá SLO và business impact. Không hạ acceptance threshold sau khi test FAIL mà không có sự xem xét, quyết định và version history.

## 17. Tính xác thực, toàn vẹn và bảo vệ pre-change evidence

Pre-change evidence thường chứa thông tin nhạy cảm: cấu hình IAM, topology, địa chỉ nội bộ, log bảo mật, danh sách dữ liệu và kết quả scan. Nó vừa phải đáng tin vừa phải được bảo vệ.

### 17.1. Metadata tối thiểu

| Trường | Tác dụng |
|---|---|
| **evidence_id / control_id / change_id** | Liên kết nguồn với claim và change đúng revision. |
| **source system và source locator** | Chứng minh nơi sinh artifact, tenant, account và resource ID. |
| **event_time và collected_at_utc** | Tách thời điểm sự kiện và lúc export. |
| **collector identity và tool version** | Biết ai hoặc công cụ nào thu; đủ quyền đọc scope không? |
| **Query, filters, pagination, completeness** | Kiểm tra dữ liệu không bị cắt hoặc bỏ account. |
| **Raw/derived và lineage** | Bản nào là nguồn, bản nào đã redacted/normalized, input-output của phép biến đổi. |
| **Artifact digest, object version** | Phát hiện thay đổi sau khi chốt; hỗ trợ tính toàn vẹn. |
| **classification và access policy** | Giới hạn người xem/chỉnh sửa, tránh lộ secrets. |
| **retention/hold policy** | Bảo toàn cho audit, incident và quy định áp dụng. |
| **reviewer/verdict/limitations** | Đánh giá chất lượng và điều chưa chứng minh. |

### 17.2. Hash không chứng minh tính đúng của nguồn

Một file CSV bị bỏ một account trước khi tính hash vẫn có digest hợp lệ cho file thiếu dữ liệu. Hash giúp so sánh sự thay đổi nội dung từ **mốc digest đáng tin**, không tự xác nhận API đã export đủ hoặc clock của máy nguồn là đúng. Cần kết hợp inventory reconciliation, quyền collector, số lượng kết quả, source authentication và audit trail.

### 17.3. Kho lưu evidence

Nên áp dụng **least privilege**, mã hóa, versioning/immutable retention khi phù hợp, audit access và phân tách quyền. Những artifact có thể lộ khóa, thông tin cá nhân hoặc kịch bản khai thác cần lưu trong kho giới hạn quyền; báo cáo chỉ nên tham chiếu ID/URI nội bộ và dữ liệu đã che khi có thể. Thời hạn lưu theo chính sách, luật/hợp đồng và mục đích; không giữ bí mật vô hạn chỉ vì có thể cần audit.

### 17.4. Tách evidence khỏi đối tượng bị thay đổi

Nếu log/audit của thay đổi IAM được lưu ở cùng account mà change đang sửa quyền, có nguy cơ mất khả năng xem chứng cứ. Với thay đổi trọng yếu, cân nhắc snapshot/config/log vào **kho có quyền độc lập** hoặc location khác để tránh cùng một sự cố xóa cả trạng thái cũ lẫn bằng chứng.

## 18. Emergency changes: Thu chứng cứ trước khi hành động bao nhiêu là đủ?

Khi hệ thống đang bị tấn công, chờ hoàn tất một gói tài liệu tiêu chuẩn có thể làm tăng thiệt hại. **Emergency change** cần cơ chế được phê duyệt trước giúp cân bằng tốc độ containment và khả năng kiểm chứng.

### 18.1. Những điều nên làm khi khả thi và an toàn

1. Ghi incident ID, người chỉ huy/được ủy quyền và lý do cần thay đổi ngay.
2. Xác định tài sản, quyền, phạm vi tối thiểu và nguy cơ nếu chậm.
3. Thu snapshot/config hoặc evidence trọng yếu **nếu việc thu không làm chậm containment nguy hiểm**.
4. Bảo toàn log và thời điểm trước khi revoke/xóa/cô lập theo mức an toàn cho phép.
5. Ghi quyết định, lệnh thực hiện, người thực hiện, T0 và expected outcome.
6. Dùng runbook khẩn đã được duyệt, có stop/rollback và kênh giám sát ngoài băng nếu cần.
7. Kiểm chứng hiệu lực containment, không chỉ lệnh được chấp nhận.
8. Hậu kiểm: bổ sung missing pre-change evidence một cách trung thực, không bịa snapshot đã không được tạo, đánh giá rủi ro và mở corrective actions.

### 18.2. Cảnh báo về “thu bằng chứng hoàn hảo”

Nếu khóa truy cập đang bị kẻ tấn công sử dụng, việc dành nhiều giờ lấy đầy đủ dashboard trước khi revoke có thể tăng thiệt hại. Quy trình khẩn nên xác định **tập tối thiểu khả thi**, ai quyết định cân bằng và những gì bắt buộc hậu kiểm. Không vì “cần pre-change evidence” mà giữ kênh xâm nhập hoạt động.

### 18.3. Không tạo phê duyệt hồi tố giả

Nếu có bước ngoài quy trình, hãy ghi đúng thời điểm và lý do, cùng approval/decision hậu kiểm theo chính sách. Không backdate quyết định hoặc làm như thể mọi gate đã được kiểm trước thay đổi. Một hồ sơ trung thực có **evidence gap minh bạch** có giá trị assurance hơn hồ sơ giả tạo.

## 19. Mẫu Pre-change evidence package dạng YAML

Đây là **mẫu minh họa dùng cho bài học**, không phải schema chuẩn của GRC, CI/CD hay một framework. Các tên, ID, ngày, giá trị và kết quả đều giả định.

~~~yaml
pre_change_evidence:
  package_id: "CHANGE-EVIDENCE-EXAMPLE-004"
  version: "1.0"
  service: "payment-api"
  change_id: "CR-PAY-1042"
  change_revision: "rev-3"
  change_type: "normal-high-risk"
  environment: "production"
  collected_at_utc: "2026-11-28T06:30:00Z"
  expected_execution_window_utc:
    start: "2026-11-28T08:00:00Z"
    end: "2026-11-28T09:00:00Z"
  owner: "Payment Platform Owner"

scope:
  cloud_accounts: ["prod-account-a", "prod-account-b"]
  regions: ["region-a", "region-b"]
  workloads: ["payment-api", "payment-worker"]
  affected_identities: ["svc-payment-api", "svc-payment-worker"]
  population_source: "asset-inventory-snapshot-20261128"
  population_reconciled: true
  dependencies:
    - "payment-queue"
    - "transaction-database"
    - "central-audit-logging"
  excluded_scope:
    - "development environment"

intent:
  objective: "Replace wildcard write permissions with least-privilege policy"
  security_control_id: "IAM-LEAST-PRIV-EXAMPLE"
  risk_reference: "RISK-IAM-042"
  original_finding: "FINDING-IAM-042"
  target_artifact:
    source_revision: "commit-example-abc123"
    iac_plan_id: "iac-plan-example-031"
    artifact_digest_reference: "restricted/change-004/digests/target"
  accepted_business_invariants:
    - "Payment authorization and queue publishing remain operational"
    - "Unauthorized administrative actions are denied"
    - "Audit events continue reaching central logging"

current_state:
  baseline_time_utc: "2026-11-28T06:20:00Z"
  sources:
    - id: "E-CFG-01"
      kind: "effective-iam-policy-export"
      source: "cloud-iam-api"
      artifact: "restricted/change-004/baseline-iam"
      digest_reference: "restricted/change-004/digests/baseline-iam"
    - id: "E-INV-02"
      kind: "inventory-and-role-mapping"
      source: "asset-management-and-runtime"
      artifact: "restricted/change-004/asset-inventory"
    - id: "E-OPS-03"
      kind: "functional-health-baseline"
      source: "payment-service-metrics"
      artifact: "restricted/change-004/health-baseline"
    - id: "E-LOG-04"
      kind: "audit-ingestion-synthetic-check"
      source: "source-audit-and-siem"
      artifact: "restricted/change-004/audit-test"
  open_findings:
    - "FINDING-IAM-042"

pre_change_tests:
  - id: "T-ALLOW-01"
    purpose: "Allow legitimate queue writes"
    scope: "payment-api staging integration"
    result: "PASS"
    evidence: "restricted/change-004/allow-test"
  - id: "T-DENY-02"
    purpose: "Deny unrelated privileged actions"
    scope: "staging policy simulation"
    result: "PASS"
    evidence: "restricted/change-004/deny-test"
  - id: "T-DRIFT-03"
    purpose: "Detect runtime drift after evidence freeze"
    scope: "all production target identities"
    result: "PENDING"
    evidence: null
  - id: "T-RECOVERY-04"
    purpose: "Verify rollback credentials and prior policy availability"
    scope: "production recovery prerequisites"
    result: "INCONCLUSIVE"
    evidence: "restricted/change-004/rollback-review"

rollback_readiness:
  known_good_policy_version: "iam-policy-before-1042"
  backup_reference: "restricted/change-004/known-good-policy"
  rollback_approved: false
  restoration_test: "INCONCLUSIVE"
  rollback_authority: "Change Commander"
  stop_conditions:
    - "payment queue publishing fails above approved threshold"
    - "central security logs stop arriving"
    - "unexpected privilege escalation path is detected"

authorization:
  risk_assessment_reference: "RISK-IAM-042"
  security_review: "PASS_FOR_CURRENT_DESIGN"
  service_owner_approval: "PENDING_RECOVERY_EVIDENCE"
  change_authority: "PENDING"
  revision_binding_verified: true
  external_requirement_review: "NOT_APPLICABLE_WITH_DOCUMENTED_REASON"

assurance:
  scope_baseline: "PASS"
  pre_change_test_coverage: "INCONCLUSIVE"
  recovery_readiness: "INCONCLUSIVE"
  change_authorization: "INCONCLUSIVE"
  decision: "NO_GO"
  rationale: >
    Runtime drift check, rollback capability and required approvals
    have not been verified at the planned decision gate.
  next_actions:
    - "Complete runtime drift validation"
    - "Verify rollback permissions and restore method"
    - "Obtain approval for the exact reviewed revision"

governance:
  evidence_classification: "CONFIDENTIAL"
  evidence_store: "restricted-security-assurance"
  retain_previous_versions: true
  post_change_verification_plan: "restricted/change-004/post-change-tests"
  reviewed_by: "Independent Security Assurance Reviewer"
~~~

### 19.1. Vì sao kết luận NO-GO?

Một số test staging đã PASS nhưng **runtime drift**, **rollback readiness** và **approval** chưa được chứng minh. Với gate được định nghĩa là bắt buộc, không thể kết luận GO chỉ vì job CI xanh hoặc IAM policy mới trông hợp lý. Mẫu cố ý trình bày quyết định NO-GO để cho thấy evidence package có giá trị ngay cả khi thay đổi **chưa được phép triển khai**.

### 19.2. Bảo đảm tính nhất quán nội bộ của package

Mọi artifact và test cần gắn **change revision/target artifact** đã review. Nếu một test chạy trên revision khác, đánh dấu không còn đại diện hoặc yêu cầu test lại. Không nhập một `PASS` trong YAML mà không có nguồn evidence và phạm vi; các giá trị ở ví dụ là mô phỏng, không phải chứng cứ thực.

### 19.3. Phần nào thuộc pre-change, phần nào thuộc post-change?

Các trường `post_change_verification_plan` và `stop_conditions` thuộc **kế hoạch chuẩn bị** trước change. Kết quả thực thi tương lai phải được ghi vào **post-change evidence** hoặc change execution log, không điền giả định là PASS ngay tại bước chuẩn bị.

## 20. Tình huống thực hành: Thay đổi firewall và IAM trước phát hành

Một dịch vụ đặt hàng sẽ đổi network policy và service-account IAM để chuyển luồng xử lý qua queue mới. PR đã được duyệt và IaC plan chỉ hiển thị thay đổi ở hai security groups. Trưởng nhóm muốn triển khai ngay trong tối nay vì hạn release.

Khi security reviewer kiểm tra:

- Tài liệu kiến trúc chỉ mô tả region A, trong khi workload dự phòng ở region B đang dùng chung service identity.
- Plan từ repo không phản ánh một firewall rule được cập nhật thủ công ở production một ngày trước.
- Negative test chặn truy cập từ subnet ngoài scope đã PASS trên staging, nhưng staging không chứa đường hỗ trợ từ vendor.
- Business test cho thanh toán thành công; job export hóa đơn chạy batch hằng đêm chưa được kiểm tra.
- Dịch vụ queue mới gửi log sang một destination khác; chưa có synthetic event chứng minh log đến SIEM.
- Snapshot IAM được tạo một tuần trước và thiếu một service account mới xuất hiện.
- Rollback plan yêu cầu khôi phục policy IAM cũ nhưng người trực hiện tại không có quyền thực hiện.
- CAB đã duyệt plan revision 1; hiện tại repo đã có revision 3 nhưng không có xác nhận phê duyệt lại.

### 20.1. Câu hỏi

1. Có đủ cơ sở GO cho change không?
2. Những lớp evidence nào bị thiếu hoặc không còn đại diện?
3. Cần test và thu baseline bổ sung ở đâu?
4. Nếu deploy rồi phải rollback, rủi ro an ninh nào xuất hiện?
5. Nếu service owner muốn chấp nhận rủi ro vì hạn release, ai có quyền quyết định và giới hạn nào vẫn bắt buộc?

### 20.2. Hướng giải

**Bước 1 — Xác minh phạm vi.** Gồm cả region A/B, worker dự phòng, queue, export hóa đơn, vendor support path và service accounts. Cập nhật dependency map và inventory từ nguồn runtime, không chỉ IaC state.

**Bước 2 — Thu lại effective baseline.** Diff IaC không phản ánh firewall rule thay đổi thủ công; cần export cấu hình thực tế trước thời điểm deploy, xử lý drift và xem sự khác nhau với target plan. IAM snapshot một tuần tuổi thiếu identity mới, phải refresh và xét quyền thực tế.

**Bước 3 — Mở rộng security/business tests.** Thử allow và deny paths cho cả chính sách mới và đường vendor support theo quyền được phép; kiểm tra luồng export hóa đơn, queue auth, quyền consumer, audit event từ nguồn đến SIEM và điều kiện rollback. Test staging phải nói rõ mức khác biệt so với production.

**Bước 4 — Kiểm chứng quyền khôi phục.** Người trực không có quyền revert policy nên rollback readiness chưa đạt. Cần xác định người có quyền trực, JIT process nếu có, mốc safe rollback và bài kiểm tra trước change. Rollback bản cũ cũng có thể mở lại quyền wildcard; phải có mitigation nếu điều kiện kích hoạt.

**Bước 5 — Kiểm tra phê duyệt.** CAB duyệt revision 1 không tự động áp dụng revision 3. Phải so scope/diff, yêu cầu re-review theo risk/change policy và giữ evidence người duyệt, timestamp, điều kiện.

**Bước 6 — Quyết định gate.** Với thiếu scope, drift, log verification, rollback permission và revision approval, quyết định **NO-GO theo gates bắt buộc** là có cơ sở. Nếu có cơ chế rủi ro/ngoại lệ hợp lệ cho một số thiếu sót, vẫn phải phân biệt kết luận test và decision; những điều kiện pháp lý/hợp đồng hoặc safety gate không thể tự miễn phải được xử lý riêng.

**Bước 7 — Chốt phiên bản và triển khai có quan sát.** Khi tất cả điều kiện cần đạt, gắn source revision, artifact/plan digest, baseline timestamp, approvals và script hậu change vào cùng change ID; trước thực thi kiểm tra drift lần cuối theo mức rủi ro. Sau change, thử cả security/functional invariants và audit path trên phạm vi thực tế, báo lỗi và rollback theo ngưỡng đã duyệt.

### 20.3. Bảng quyết định minh họa

| Gate | Bằng chứng hiện có | Kết luận |
|---|---|---|
| **Scope completeness** | Thiếu region B và vendor path. | **FAIL/INCONCLUSIVE theo tiêu chí coverage**. |
| **Current-state baseline** | Manual firewall drift và IAM inventory cũ. | **INCONCLUSIVE** cho trạng thái mới nhất. |
| **Pre-change tests** | Staging PASS nhưng thiếu batch/export và logging. | **INCONCLUSIVE** cho toàn bộ scope. |
| **Observability** | Chưa kiểm tra nguồn log mới tới SIEM. | **INCONCLUSIVE**. |
| **Rollback readiness** | Người trực không có quyền revert. | **FAIL** nếu policy yêu cầu quyền rollback sẵn sàng. |
| **Approval revision** | CAB duyệt revision 1, target là revision 3. | **FAIL** nếu không nằm trong cơ chế duyệt thay đổi tương ứng. |
| **GO decision** | Nhiều gate quan trọng chưa đạt. | **NO-GO** cho đợt triển khai dự kiến. |

Không được ghi “security reviewer đã chặn release” như một thất bại của assurance. **Phát hiện thiếu bằng chứng trước khi gây sự cố chính là một kết quả có giá trị**.

## 21. Những sai lầm phổ biến khi thu Pre-change evidence

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ lưu change ticket, không có baseline. | Không so sánh được trạng thái trước/sau. | Thu effective config, asset, metric và event snapshots có provenance. |
| Xem file IaC là trạng thái production. | Bỏ manual drift và resource ngoài IaC. | Reconcile declared vs observed state. |
| Chụp baseline quá sớm rồi không refresh. | Asset/quyền mới không được review. | Đặt freshness/TOCTOU gate phù hợp risk. |
| Tính số test xanh thay vì coverage. | Test bỏ các đường quan trọng nhưng dashboard vẫn PASS. | Map tests với requirements, assets, negative paths. |
| Chỉ thử happy path, không thử quyền bị cấm. | Có thể làm rộng quyền truy cập. | Negative security tests và bypass checks. |
| Bỏ vùng dự phòng và tác vụ batch khỏi scope. | Hồi quy chỉ xuất hiện sau failover hoặc cuối ngày. | Dependency graph và inventory đủ môi trường/thời gian. |
| Có backup nhưng không thử restore. | Không có cơ sở khẳng định recoverability. | Restore rehearsal, key access, data validation. |
| Giả định rollback luôn đảo ngược được migration. | Có thể mất dữ liệu hoặc tái mở lỗ hổng. | Rollback feasibility, backward compatibility, forward-fix. |
| Không ràng buộc approval với artifact revision. | Deploy bản khác bản đã duyệt. | Commit/digest/plan ID, kiểm tra integrity trước execution. |
| Bỏ logging/alert checks vì API vẫn xanh. | Security regression không được phát hiện. | Synthetic event và telemetry readiness. |
| Dùng staging PASS cho production không nêu khác biệt. | Coverage/lượng tải/IDP không tương đương. | Document environment delta, test bổ sung. |
| Chỉ xét rủi ro không thay đổi, bỏ rủi ro do thay đổi. | Fix gây mất dữ liệu, downtime hoặc mở quyền mới. | Dual-risk assessment và stop conditions. |
| Ghi PASS khi evidence thiếu. | Assurance giả và approval sai căn cứ. | INCONCLUSIVE/NO-GO phù hợp; bổ sung nguồn. |
| Copy secrets vào evidence package. | Rò rỉ credentials và thông tin nhạy cảm. | Dùng metadata, redaction, vault, RBAC. |
| Tạo hash rồi tuyên bố data collection đầy đủ. | File thiếu vẫn có hash hợp lệ. | Population reconciliation, query metadata, source trust. |
| Đổi due date/condition sau khi FAIL để tạo GO. | Lịch sử audit không còn trung thực. | Versioned gates, risk sign-off và decision trail. |
| Dùng emergency procedure để đi tắt release thường. | Mất accountability và tạo bypass dài hạn. | Điều kiện emergency cụ thể, hậu kiểm và thu hồi quyền. |
| Không lưu bản pre-change khi post-change thất bại. | Không thể phân biệt regression và lỗi cũ. | Evidence vault độc lập, retention và lineage. |

## 22. Checklist chấp nhận một Pre-change evidence package

Trước khi reviewer xác nhận release gate, hãy kiểm tra:

1. **Change identity:** Change ID, revision, artifact digest, plan và môi trường mục tiêu được ràng buộc rõ chưa?
2. **Security objective:** Change liên kết với yêu cầu/control và mục tiêu rủi ro nào?
3. **Scope:** Asset, account, region, identity, dữ liệu, workload và dependency đã được đối chiếu thực tế chưa?
4. **Effective baseline:** Có cấu hình/behavior từ runtime, không chỉ desired state trong repo?
5. **Freshness:** Baseline, inventory và test có còn đại diện tại thời điểm deploy? Có drift/TOCTOU check?
6. **Existing issues:** Findings, exceptions, incidents, risk acceptances còn mở đã được xem xét?
7. **Threat modeling:** Có phân tích attack paths hoặc trust boundaries bị thay đổi?
8. **Architecture:** Data flow, permissions, logs, backup, KMS, IdP, DNS và vendor dependencies đã có review?
9. **Tests:** Có positive/negative security, functional, integration và failure-case tests tương xứng?
10. **Test provenance:** Test run, source revision, tool version, environment delta và limitations được lưu?
11. **Supply chain:** Build/artifact/plan đúng revision được test và được kiểm soát integrity?
12. **Data safety:** Có schema/data baseline, backup và phương pháp reconciliation khi thay dữ liệu?
13. **Recovery:** Rollback/forward-fix khả thi, quyền/người trực và stop triggers đã được xác minh?
14. **Observability:** Logging, metrics, synthetic event, on-call và triage sẵn sàng cho hậu change?
15. **Approvals:** Đúng người, risk tier, external obligations, thời hạn và đúng bản change?
16. **Gate outcomes:** PASS/FAIL/INCONCLUSIVE/N/A của từng tiêu chí được đánh giá, không che gaps?
17. **Decision:** GO/NO-GO do chủ thể có thẩm quyền đưa ra trên cơ sở evidence và điều kiện rõ?
18. **Protection:** Evidence có nguồn, timestamp, scope, access control, version/integrity và retention?
19. **Emergency path:** Nếu khẩn, có incident ID, thẩm quyền, phạm vi tối thiểu, bằng chứng khả thi và hậu kiểm?
20. **Post-change verification plan:** Có test cases, success thresholds, baseline comparator và thời điểm nghiệm thu?
21. **Continuous assurance:** Có theo dõi regression, findings, rollback, drift và kết quả để cải tiến các change sau?

### Câu hỏi tự đánh giá

Một thay đổi xoay vòng encryption key của database production có change ticket đã duyệt, key mới đã tạo trong KMS và test đọc dữ liệu với key mới trên staging đạt. Không có restore test từ backup production, danh sách consumer dùng key cũ chưa đầy đủ và nhóm vận hành định xóa key cũ ngay sau deploy.

**Có thể kết luận pre-change readiness PASS không?**

**Gợi ý:** **Không đủ bằng chứng để GO**. Chưa biết backup/consumer có thể giải mã dữ liệu bằng key cũ sau rotation hay không; xóa key có thể gây mất khả năng truy xuất và khôi phục dữ liệu. Cần inventory data/consumer/key dependencies, xác định thời gian giữ key cũ theo chính sách, backup/restore rehearsal phù hợp, kiểm tra quyền KMS, kịch bản rollback/forward fix, observability và acceptance criteria cho tính toàn vẹn/khả dụng. Tách kết quả staging PASS khỏi kết luận production readiness còn **INCONCLUSIVE/NO-GO** theo các gate trọng yếu.

**Pre-change evidence có giá trị khi làm rõ trạng thái thật trước thay đổi, chứng minh được phạm vi và các điều kiện sẵn sàng, ràng buộc test và approval vào đúng revision, bảo vệ khả năng phục hồi và cung cấp một baseline đáng tin để kiểm chứng hậu triển khai. Tổ chức không thể bảo đảm rằng mọi change đều thành công, nhưng có thể bảo đảm rằng quyết định GO hay NO-GO được đưa ra trên căn cứ minh bạch, kiểm tra được và có trách nhiệm.**
