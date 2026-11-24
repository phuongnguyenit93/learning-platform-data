# Policy version – quản lý phiên bản chính sách PBAC trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **Policy version** trong **Policy-Based Access Control (PBAC)** là gì, tại sao thay đổi chính sách phân quyền phải có danh tính, phiên bản, phê duyệt và khả năng truy vết.
- Phân biệt **policy ID**, **revision**, **policy bundle version**, **policy schema version**, **decision policy version**, **identity/entitlement version** và các giá trị về thời gian hiệu lực.
- Mô tả vòng đời **draft → review → approved → staged → active → retired** của chính sách và tác động của **rollback, hotfix, canary, shadow evaluation**.
- Thiết kế cách **Policy Administration Point (PAP)** phân phối phiên bản đến **Policy Decision Point (PDP)**, cách **Policy Enforcement Point (PEP)** áp quyết định và **Policy Information Point (PIP)** cung cấp thuộc tính.
- Giải thích vì sao hai PDP cùng nhận một request có thể quyết định khác nhau khi đang dùng policy khác version hoặc thuộc tính không cùng độ mới.
- Xây dựng mẫu **Policy as Code**, metadata, audit log, kiểm thử âm tính và chiến lược version pinning hợp lý cho Java/microservices.
- Liên hệ thay đổi chính sách với **Joiner–Mover–Leaver**, **IdP/SSO, SCIM, RBAC/ABAC**, tài khoản dịch vụ, quyền truy cập tồn dư và reconciliation.

## 1. Policy version là gì?

**Policy version** là **định danh của một trạng thái chính sách phân quyền cụ thể** ở một thời điểm trong vòng đời quản trị chính sách. Khi chính sách thay đổi, phiên bản mới cho phép đội vận hành, hệ thống thực thi và kiểm toán xác định **đã dùng đúng tập quy tắc nào** để đưa ra quyết định.

Ví dụ, một công ty có policy:

- Phiên bản 7: nhân viên thuộc nhóm `FinanceReader` được xem báo cáo tài chính thuộc đơn vị của mình.
- Phiên bản 8: ngoài role `FinanceReader`, còn cần quan hệ làm việc ACTIVE, đúng tenant và không có security block.
- Phiên bản 9: khi xuất báo cáo nhạy cảm phải có xác thực đủ mạnh, còn mới và quyền export đã được phê duyệt.

Một request được xử lý với phiên bản 7 có thể được **PERMIT**, nhưng khi đánh giá theo phiên bản 9 lại **DENY** hoặc yêu cầu xác thực bổ sung. Không có thông tin version, người điều tra rất khó giải thích vì sao hai request giống nhau nhận kết quả khác nhau.

**Policy version không phải chỉ là chuỗi được ghi trong file.** Để có giá trị kiểm soát truy cập, version cần gắn với **nội dung chính sách bất biến, nguồn phê duyệt, phạm vi triển khai, thời điểm áp dụng và bằng chứng PEP/PDP thực sự sử dụng nó**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, versioning giúp kiểm soát thay đổi quyền qua **Joiner–Mover–Leaver (JML)**. Các quy tắc liên quan **IdP, SSO, SCIM, RBAC/ABAC, service identity, audit và reconciliation** có thể thay đổi độc lập. Một phiên bản policy không làm mọi account hoặc phiên đăng nhập tự cập nhật; vẫn cần đồng bộ và xác minh ở điểm thực thi.

### 1.1. Vì sao PBAC cần version?

| Vấn đề | Nếu không có version rõ | Khi có version được quản trị |
| --- | --- | --- |
| **Điều tra truy cập** | Không biết rule nào cho phép thao tác | Tìm được rule/policy bundle tại thời điểm decision |
| **Review và approval** | Quy tắc bị sửa trực tiếp không dấu vết | Phê duyệt đúng nội dung thay đổi |
| **Triển khai nhiều dịch vụ** | Instance chạy quy tắc khác nhau khó phát hiện | Theo dõi version đang active tại từng PDP |
| **Rollback/hotfix** | Khó biết bản trước và tác động | Có thay đổi mới được ghi nhận, review và đối soát |
| **Joiner/Mover/Leaver** | Thay đổi quyền không có mốc chính sách | Đối chiếu entitlement với policy hiệu lực |
| **Kiểm thử** | Không tái hiện được quyết định cũ | Chạy lại test với policy artifact và input snapshot |
| **Bảo mật** | Rollback vô tình mở lại quyền đã cấm | Có change gates, guard và báo cáo |
| **Kiểm toán** | Chỉ thấy PERMIT/DENY, thiếu nguồn quyết định | Có policyId, version, digest, rollout và evidence |

### 1.2. Policy version không đồng nghĩa kết quả luôn giống nhau

Hai request được đánh giá bởi **cùng một policy version** vẫn có thể ra kết quả khác nếu **identity status, role, tenant, resource owner, approval, thời gian, rủi ro hoặc authentication assurance** khác nhau.

Vì vậy, để tái hiện một quyết định cần **cả policy version lẫn dữ liệu ngữ cảnh mà policy đã dùng**. Chỉ ghi `policyVersion=9` chưa đủ chứng minh vì sao một người được cấp quyền.

## 2. Phân biệt các loại phiên bản và định danh

| Thuật ngữ | Ý nghĩa | Ví dụ | Không nên nhầm với |
| --- | --- | --- | --- |
| **Policy ID** | Định danh ổn định cho một policy logic | `finance-invoice-read` | Nội dung hoặc revision của policy |
| **Policy revision/version** | Một trạng thái bất biến của policy | `revision=9` | Số role được cấp cho user |
| **Policy bundle version** | Phiên bản gói nhiều policy được phát hành cùng nhau | `iam-bundle-2026.11.23.2` | Version của một rule đơn lẻ |
| **Policy artifact digest** | Dấu vân tay nội dung artifact cụ thể | `sha256:<digest>` | Bằng chứng nguồn đã được phê duyệt nếu thiếu ký/kiểm soát |
| **Policy schema version** | Phiên bản cấu trúc dữ liệu, cú pháp hoặc contract | `schemaVersion=2` | Thay đổi điều kiện quyền |
| **Policy engine version** | Phiên bản runtime thực thi rule | `engine=release-X` | Policy revision |
| **Decision ID** | Định danh một lần đánh giá | `authz-decision-501` | Policy ID |
| **Entitlement version** | Thay đổi tập role/permission của identity | `identityVersion=41` | Policy bundle version |
| **Resource version** | Mốc thay đổi thuộc tính resource | `invoiceVersion=12` | Quy tắc phân quyền |
| **Token/session version** | Mốc được ứng dụng dùng để kiểm phiên/token khi có thiết kế | `sessionRev=5` | Bằng chứng policy đã rollout |
| **Deployment version** | Bản build hoặc bản triển khai dịch vụ | `serviceRelease=2026.11.23` | Policy đang active của mọi instance |

Các tên trên là **mô hình thiết kế**, không phải trường bắt buộc trong mọi PBAC engine. Một hệ thống có thể dùng SemVer, số revision tăng dần, Git commit ID hoặc digest. Quan trọng là **mỗi định danh có ngữ nghĩa rõ, không bị tái sử dụng cho nội dung khác**.

### 2.1. Policy ID ổn định, version thay đổi

~~~text
policyId = "finance-invoice-read"

revision 7  -> nội dung A
revision 8  -> nội dung B
revision 9  -> nội dung C

policyId giữ nguyên.
revision mới mô tả thay đổi của cùng policy.
Không chỉnh nội dung revision 8 sau khi đã publish.
~~~

Nếu sửa artifact phiên bản 8 ngay tại chỗ, audit lịch sử có thể trỏ tới nội dung không còn giống lúc quyết định. Vì thế nên dùng **immutable published artifacts**.

### 2.2. SemVer có phù hợp không?

Có thể dùng kiểu `major.minor.patch`, nhưng **PBAC không có một quy tắc SemVer chung bắt buộc**. Một thay đổi nhỏ về mã nguồn có thể gây tác động lớn tới quyền. Tổ chức cần định nghĩa:

- **Security-impacting/breaking change:** mở rộng hoặc thu hẹp quyền ở phạm vi đáng kể.
- **Rule clarification:** thay đổi logic hoặc điều kiện dù chỉ sửa một dòng.
- **Operational fix:** thay đổi cấu hình mà không chủ đích đổi quyền.
- **Schema/engine compatibility:** thay đổi cách policy được đọc/đánh giá.

Một chỉ số version cao hơn **không tự có nghĩa an toàn hơn**. Nội dung và kiểm thử mới là căn cứ.

## 3. Policy version nằm ở đâu trong kiến trúc PBAC?

Một mô hình PBAC có thể gồm:

- **PAP – Policy Administration Point:** quản trị chính sách, review, approval, phát hành và version.
- **PDP – Policy Decision Point:** đánh giá request theo đúng policy artifact, data và context.
- **PIP – Policy Information Point:** cung cấp thuộc tính về identity, resource, role, trạng thái JML và quan hệ.
- **PEP – Policy Enforcement Point:** chặn hoặc thực thi tác vụ theo decision và điều kiện bắt buộc.
- **Policy registry/bundle distributor:** lưu artifact, integrity metadata và đưa version đến các PDP/PEP.
- **Audit/observability:** ghi lại policy và trạng thái áp dụng thực tế.

~~~mermaid
flowchart LR
    Owner["Resource owner / Security"] --> PAP["PAP: Review & Approval"]
    PAP --> Repo["Immutable policy artifacts"]
    Repo --> Deploy["Bundle rollout / Version control"]
    Deploy --> PDP1["PDP instance A, version V8"]
    Deploy --> PDP2["PDP instance B, version V8"]
    PIP["PIP: HRIS / IGA / Resource / Risk"] --> PDP1
    PIP --> PDP2
    User["User / Workload"] --> PEP["PEP: API / Backend"]
    PEP --> PDP1
    PEP --> PDP2
    PDP1 --> PEP
    PDP2 --> PEP
    PEP --> Resource["Resource / Data plane"]
    PEP --> Audit["Audit: decision + policy version"]
    Deploy --> Audit
~~~

Sơ đồ mô tả **trạng thái mục tiêu** khi hai PDP cùng version. Trong lúc rollout, PDP-A có thể đã cập nhật V9 nhưng PDP-B vẫn dùng V8. Vì thế phải theo dõi **active version per instance**, không chỉ ghi một trường `desiredVersion=V9` trong PAP.

### 3.1. Version trong decision response

Một quyết định có thể mang thông tin:

~~~json
{
  "decisionId": "authz-req-5842",
  "effect": "DENY",
  "policyId": "finance-invoice-read",
  "policyRevision": 9,
  "bundleVersion": "iam-bundle-2026.11.23.2",
  "artifactDigest": "sha256:illustrative-placeholder",
  "engineInstance": "pdp-east-3",
  "reasonCode": "ENTITLEMENT_NOT_APPROVED",
  "evaluatedAt": "2026-11-23T09:45:00+07:00"
}
~~~

**Đây là JSON minh họa**, không phải response chuẩn của XACML, OPA, Cedar hoặc engine khác. Digest chỉ mang tính hình thức. Một hệ thống thật phải tính digest trên nội dung artifact thực tế và bảo vệ đường truyền từ PDP đến PEP.

**Không nhận `policyRevision` do client gửi làm lệnh chọn bản quyền dễ dãi.** Nếu người dùng có thể tự yêu cầu `v7` còn rộng quyền thay vì `v9`, versioning đã trở thành đường bypass.

## 4. Vòng đời quản trị phiên bản policy

Một chu kỳ phù hợp có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> IN_REVIEW: Tạo change request
    IN_REVIEW --> DRAFT: Yêu cầu chỉnh sửa
    IN_REVIEW --> APPROVED: Có phê duyệt phù hợp
    APPROVED --> STAGED: Build, test và ký artifact
    STAGED --> CANARY: Rollout hạn chế
    CANARY --> ACTIVE: Đạt gates và coverage
    CANARY --> SUPERSEDED: Không đạt, phát bản sửa
    ACTIVE --> SUPERSEDED: Bản mới thay thế
    SUPERSEDED --> RETIRED: Ngừng sử dụng theo chính sách
    RETIRED --> [*]
~~~

Sơ đồ là **mô hình quản trị minh họa**, không phải định nghĩa bắt buộc của PBAC. Có tổ chức dùng state khác hoặc không có canary. Điều quan trọng là kiểm soát **ai tạo, ai duyệt, artifact nào được phát, version nào active và có bằng chứng hay không**.

### 4.1. DRAFT – đề xuất

Policy owner mô tả:

- **Business justification:** vì sao cần thay đổi quyền?
- **Risk:** nhóm user/tài nguyên/hành động nào bị ảnh hưởng?
- **Source of truth:** role và thuộc tính đến từ đâu?
- **Expected effect:** điều kiện PERMIT/DENY và trường hợp ngoại lệ.
- **JML impact:** Joiner, Mover, Leaver và non-human identity có thay đổi không?

Không nên tạo rule chỉ dựa vào một ticket không có owner hoặc dùng email của nhân viên làm điều kiện phân quyền bền vững.

### 4.2. REVIEW/APPROVED – kiểm soát trước khi phát hành

Tùy mức nhạy cảm, có thể yêu cầu review bởi resource owner, IAM/security, compliance hoặc đơn vị vận hành; bảo đảm **Segregation of Duties (SoD)** để người viết policy không được tự phê duyệt một thay đổi mở rộng đặc quyền của chính mình.

Phê duyệt phải trỏ tới **đúng nội dung commit/digest**. Nếu sau review có thêm một điều kiện mở quyền, phải review lại thay vì gắn approval cũ cho nội dung mới.

### 4.3. STAGED/ACTIVE – triển khai có chứng cứ

Policy được test với fixtures, build theo schema và phân phối đến PDP. Đội vận hành cần phân biệt:

- **Desired version:** bản muốn các instance sử dụng.
- **Deployed version:** bản đã được phân phối/tải xuống.
- **Loaded version:** bản PDP đã đọc và xác minh.
- **Active version:** bản PDP đang dùng để ra decision.
- **Observed version:** bản được xác minh qua telemetry hoặc truy vấn health.
- **Retired version:** bản không còn được phép sử dụng cho decision mới.

**“CI pipeline thành công” không chứng minh mọi PDP đang dùng policy mới.** Cần quan sát tại điểm ra quyết định.

## 5. Bất biến của một phiên bản được phát hành

**Immutability** giúp audit, rollback và tái hiện quyết định.

Một artifact đã phát hành nên có:

1. **Policy ID** và **revision** không tái sử dụng.
2. **Nội dung rule** chính xác, gồm deny/allow và các obligations.
3. **Schema/engine compatibility** hoặc ràng buộc rõ engine.
4. **Digest** được tính bằng thuật toán phù hợp, dùng để kiểm tính toàn vẹn.
5. **Provenance:** source commit, build/run ID, người duyệt, thời điểm phê duyệt.
6. **Effective/activation metadata** theo phạm vi triển khai.
7. **Tenant/environment scope** để tránh nhầm dev/test/prod.
8. **Rollback/deprecation metadata** nếu policy bị thay hoặc ngừng dùng.

### 5.1. Metadata minh họa

~~~yaml
policyId: finance-invoice-read
revision: 9
schemaVersion: 2
bundleId: finance-policy-bundle
bundleVersion: 2026.11.23.2
artifactDigest: "sha256:illustrative-only"
owner: finance-security
environment: production
lifecycleState: APPROVED
effectiveFrom: "2026-12-01T00:00:00+07:00"
effectiveUntil: null
sourceCommit: illustrative-commit-id
approvalRef: approval-2081
defaultEffect: DENY
~~~

**YAML chỉ minh họa thiết kế metadata**, không phải cấu hình chuẩn của một PBAC engine. Khi chạy thật cần chọn nơi lưu source commit, signature, effective time và approval sao cho bảo vệ được tính toàn vẹn.

### 5.2. Hash và chữ ký giải quyết hai vấn đề khác nhau

- **Digest/hash:** kiểm nội dung artifact có bị thay đổi hay không.
- **Chữ ký/nguồn phân phối tin cậy:** chứng minh artifact đến từ pipeline/đơn vị được phép, với khóa và quy trình tin cậy phù hợp.

Chỉ có hash trong một file do cùng người tấn công kiểm soát **không tự chứng minh policy đáng tin**. Hệ thống cần bảo vệ repository, CI/CD, registry, quyền publish và runtime loader.

### 5.3. Version không được “sửa nóng” âm thầm

Nếu phát hiện lỗi ở revision 9, nên tạo **revision 10** hoặc change tương đương với phê duyệt và audit. Chỉnh trực tiếp artifact 9 làm mất khả năng tái tạo chính sách đã chạy trước đó.

## 6. Phân loại thay đổi policy theo tác động quyền

| Loại thay đổi | Ví dụ | Rủi ro | Kiểm thử cần chú ý |
| --- | --- | --- | --- |
| **Tăng quyền** | Cho FinanceReader đọc thêm tenant-B | Lộ dữ liệu | Negative test cross-tenant và approval |
| **Thu hẹp quyền** | Bắt buộc đúng department | Có thể gián đoạn hợp lệ; phải chặn quyền dư | Test DENY, rollout và fallback |
| **Thêm security block** | DENY chủ thể bị đình chỉ | Cần hiệu lực nhanh toàn hệ thống | Test cache, token cũ, nhiều PDP |
| **Thay nguồn thuộc tính** | Department từ claim IdP sang HRIS | Có thể sai mapping hoặc stale | Test nguồn, null, unknown |
| **Thay rule ưu tiên** | Explicit deny thắng allow | Thay nhiều decision | Regression/combining tests |
| **Thay nghĩa role** | Admin bao gồm thêm export | Privilege creep | SoD, approval, access review |
| **Thay obligations** | Cần step-up trước `role.grant` | Có thể bị bỏ qua ở PEP cũ | Contract compatibility |
| **Thay schema** | Field `tenant` chuyển sang `tenantId` | Engine/PEP không đọc được | Contract/version migration |
| **Thay thời gian hiệu lực** | Quyền chỉ trong ca làm | Quyết định phụ thuộc đồng hồ | Boundary/timezone tests |

**Không phân loại chỉ theo số dòng sửa.** Một điều kiện boolean bị đảo có thể chuyển hàng nghìn quyết định DENY thành PERMIT.

### 6.1. Kiểm tra tác động trước khi duyệt

So sánh ít nhất:

- **Who:** những identity, role, nhóm, service principal nào chịu ảnh hưởng?
- **What:** action/resource/tenant/classification nào?
- **When:** từ lúc nào, trong bao lâu?
- **Why:** có phê duyệt nghiệp vụ và dữ liệu nguồn phù hợp không?
- **How:** PDP và PEP nào phải tương thích?
- **Reversibility:** có thể phát hành policy sửa mà không khôi phục quyền cũ trái phép không?

## 7. Policy bundle và các phụ thuộc version

Nhiều hệ thống không triển khai từng rule độc lập mà đóng gói **policy bundle**: nhiều policy, mapping, schema và data definitions được phát cùng nhau.

Ví dụ:

~~~text
bundle finance-v9
  policy finance-invoice-read  revision 9
  policy finance-invoice-edit  revision 5
  policy finance-export       revision 12
  role-map finance-roles      revision 7
  schema attributes           version 2
  engine compatibility        runtime profile A
~~~

Nếu PDP được cập nhật policy invoice-read nhưng vẫn dùng role-map cũ, kết quả có thể sai dù tên **policy revision 9** đúng.

### 7.1. Tính nhất quán của bundle

Một hệ thống nên định nghĩa cách **chuyển atomically** từ bundle A sang B trên *từng PDP* khi nền tảng hỗ trợ. Tránh cho một decision dùng một nửa rule của v8 và một nửa của v9 nếu các rule có phụ thuộc.

Trong hệ phân tán, **atomic trên từng PDP không có nghĩa atomic toàn bộ cụm**. Các instance có thể chuyển version ở các thời điểm khác nhau; cần rollout gates và quan sát.

### 7.2. Tham chiếu tới dữ liệu động

Một rule có thể được version cố định nhưng truy vấn **PIP** lấy thông tin thay đổi liên tục, ví dụ employmentStatus hoặc owner.

Vì vậy cần nêu rõ **artifact version khác attribute snapshot/version**. Có thể giữ policy bundle nguyên vẹn và vẫn có quyết định mới sau một sự kiện Leaver vì PIP đọc đúng trạng thái hiện hành.

### 7.3. Xác định compatibility

Đổi schema từ `subject.department` sang `subject.orgUnit` có thể khiến PDP cũ không hiểu thuộc tính mới.

Cần **contract tests** giữa PIP, PDP và PEP. Không chỉ test cú pháp policy mà phải test cả:

- Thuộc tính thiếu hoặc null.
- Tên/kiểu dữ liệu đổi.
- Kết hợp policy allow/deny.
- Obligations không được PEP hỗ trợ.
- Các application versions đồng thời tồn tại khi rollout.

## 8. Thời gian hiệu lực của policy

Một policy thường có nhiều mốc thời gian:

| Mốc | Ý nghĩa |
| --- | --- |
| **createdAt** | Bản draft được tạo |
| **approvedAt** | Nội dung cụ thể được phê duyệt |
| **publishedAt** | Artifact được xuất bản |
| **desiredActivationAt** | Thời điểm hệ thống dự kiến bắt đầu dùng |
| **loadedAt** | PDP tải được artifact |
| **activatedAt** | PDP bắt đầu dùng artifact |
| **effectiveFrom/Until** | Thời kỳ quyền theo policy có giá trị nghiệp vụ |
| **decisionEvaluatedAt** | Thời điểm một request được đánh giá |
| **resourceCommittedAt** | Thời điểm hành động thực sự xảy ra |
| **verifiedAt** | Thời điểm giám sát xác minh tình trạng thực tế |

Các mốc **không nhất thiết bằng nhau**. Ví dụ policy đã được publish hôm nay nhưng phải tới ngày đầu tháng sau mới effective; hoặc desired activation đã qua nhưng một PDP vùng xa chưa nhận được bundle.

### 8.1. Ví dụ tương lai hóa chính sách

~~~text
2026-11-20  Bản policy 9 được phê duyệt
2026-11-23  Policy bundle phát đến môi trường production
2026-11-30  PDP đều loaded, chưa được kích hoạt theo lịch
2026-12-01  Policy có hiệu lực nghiệp vụ
2026-12-01  Telemetry xác minh PDP/PEP dùng version tương ứng
~~~

Đây là timeline giả định, không phải cam kết của engine cụ thể.

Nếu policy dựa trên `now`, cần xác định **timezone, độ lệch đồng hồ và nguồn thời gian**. Không tin timestamp do trình duyệt gửi làm căn cứ mở quyền.

### 8.2. Effective time khác deployment time

Một policy được load thành công **không đồng nghĩa** đã active. Một policy đã active **không chứng minh** quyền của mọi resource đã thay đổi theo mong muốn vì có thể còn cache, entitlement ở ứng dụng khác và token đã phát.

## 9. Triển khai policy an toàn qua nhiều PDP

Trong một cụm microservices, rollout thường diễn ra dần.

~~~mermaid
sequenceDiagram
    autonumber
    participant PAP as PAP / Release Controller
    participant A as PDP East
    participant B as PDP West
    participant PEP as Application PEP
    participant OBS as Monitoring

    PAP->>A: Phân phối bundle V9
    A-->>OBS: Loaded/active V9
    PAP->>B: Phân phối bundle V9
    B-->>OBS: Vẫn V8 do sự cố kết nối
    PEP->>A: Evaluate sensitive action
    A-->>PEP: DENY; policy V9
    PEP->>B: Evaluate tương đương
    B-->>PEP: PERMIT; policy V8
    OBS-->>PAP: Cảnh báo version skew
    PAP->>B: Retry/khắc phục theo runbook
    B-->>OBS: Active V9
~~~

**Version skew** là tình trạng các instance dùng khác version. Điều này nguy hiểm khi V9 thu hồi một permission mà V8 vẫn cho phép.

### 9.1. Các chiến lược rollout

- **Staging:** kiểm thử policy và PEP obligations trong môi trường gần production.
- **Shadow evaluation:** tính kết quả policy mới trên traffic/test data nhưng **không thực thi PERMIT mới**; so khác biệt với policy hiện hành.
- **Canary:** một phần workload/tenant/instance dùng bản mới theo phạm vi được kiểm soát.
- **Progressive rollout:** tăng phạm vi sau khi đạt test và quan sát.
- **Coordinated cutover:** kiểm soát thời điểm sử dụng khi yêu cầu tránh version skew trong thao tác rủi ro cao.
- **Stop-the-line:** tạm dừng rollout và xử lý lỗi nếu xuất hiện PERMIT ngoài dự kiến.

Canary **không phù hợp cho mọi thay đổi an ninh**: nếu một bản vá cần DENY tài khoản bị xâm nhập ngay, để phần lớn cụm chạy policy cũ lâu hơn có thể tạo khoảng trống. Lúc đó cần **cơ chế deny khẩn cấp hoặc chặn ở control plane** có khả năng bao phủ yêu cầu.

### 9.2. Phân biệt rollout coverage với enforcement coverage

- **Rollout coverage:** bao nhiêu PDP/PEP đã nhận hoặc kích hoạt version.
- **Enforcement coverage:** bao nhiêu đường truy cập thực sự đi qua kiểm soát phù hợp.

100% PDP dùng V9 nhưng một endpoint không gọi PDP **vẫn chưa an toàn**. Cần giám sát cả hai.

## 10. Quyết định có được chọn policy version tùy request không?

**Không nên để người dùng hoặc client tự chọn một phiên bản policy yếu hơn** qua query string, header hoặc request body.

Ví dụ không an toàn:

~~~text
POST /api/admin/role-grants
X-Policy-Version: 7

Backend áp policy v7 vì client yêu cầu
trong khi policy active v9 đã cấm quyền đó.
~~~

Trong một số hệ thống có nhu cầu **version pinning** hợp lệ, chẳng hạn xử lý workflow pháp lý hoặc tái hiện audit lịch sử, nhưng version phải được **hệ thống đáng tin cấp và kiểm soát**.

### 10.1. Những trường hợp version pinning có thể hợp lệ

- **Audit replay:** tính lại quyết định cũ để điều tra, **không thực thi thao tác thật**.
- **Migration test:** so kết quả giữa hai policy để phát hiện sai khác, không cấp quyền.
- **Long-running business workflow:** ghi nhận các điều kiện đã được phê duyệt tại thời điểm đầu, nhưng xác định rõ điều kiện nào phải kiểm lại.
- **Controlled canary:** routing được release controller quản trị, không để client tùy ý.

**Version pinning không tự tạo quyền sử dụng một policy đã retired**. Những lệnh nhạy cảm đang được thực thi phải đáp ứng quy tắc active và guard hiện hành.

### 10.2. Principal và resource phải được ràng buộc

Một decision trả về từ PDP cần gắn với đúng **subject, action, resource, tenant và request context**. Không lấy PERMIT của invoice-412 rồi dùng cho invoice-413, ngay cả khi policy version giống nhau.

## 11. PEP phải làm gì với version trong decision?

PEP không chỉ đọc `PERMIT` rồi cho chạy. Nó cần bảo vệ toàn bộ contract:

1. **Nguồn decision:** response đến từ PDP đáng tin, hoặc policy engine local được phê duyệt.
2. **Tính nguyên vẹn:** không bị client hoặc proxy không đáng tin sửa decision.
3. **Scope:** đúng actor, action, resource, tenant và session/transaction.
4. **Policy version:** có thuộc tập version mà release/controller cho phép với hành động này không?
5. **Obligations:** step-up, audit, data filtering, approval hoặc rate/quota có thực thi được không?
6. **Freshness:** dữ liệu JML, role, approval và policy có đủ mới không?
7. **TOCTOU:** trước commit, version/resource/entitlement có thay đổi khiến decision không còn hợp lệ không?
8. **Execution evidence:** tác vụ thực sự được thực hiện, bị chặn hay lỗi?

### 11.1. Trạng thái version không đáp ứng

Khi PDP trả một PERMIT dựa trên version quá cũ so với yêu cầu chặn khẩn cấp, PEP cần **từ chối hoặc yêu cầu đánh giá lại trên version hợp lệ** theo chính sách.

Không có cơ chế PBAC phổ quát bảo đảm **đúng cùng một version trên mọi node tại mọi thời điểm**. Nếu hệ thống yêu cầu tính nhất quán mạnh hơn, phải thiết kế **coordinated activation, revision guard hoặc central decision barrier** cùng cơ chế fail-safe phù hợp.

### 11.2. Không cứng nhắc so version như số lớn hơn

Một string như `v9.10` không thể được so chính xác bằng thứ tự từ điển với `v9.9`. Một số hệ dùng commit hash không có thứ tự tự nhiên. Cần dùng **registry hoặc metadata có ngữ nghĩa**: active set, policy lineage, environment và effective time.

## 12. Ví dụ Policy as Code với version metadata

Ví dụ dưới đây là **DSL/YAML minh họa**, không phải ngữ pháp chuẩn của một công cụ cụ thể:

~~~yaml
policy:
  id: finance-invoice-read
  revision: 9
  schemaVersion: 2
  effect: PERMIT
  action: invoice.read
  subject:
    lifecycleStatus: ACTIVE
    entitlement: FINANCE_INVOICE_READ
  resource:
    tenant: equals-subject-tenant
    department: equals-subject-department
  conditions:
    identityProofingSatisfied: true
    securityBlocked: false
    withinEmploymentWindow: true
  obligations:
    - audit-decision-and-execution
  defaultEffect: DENY
release:
  bundleVersion: finance-bundle-2026-11-23-2
  environment: production
  owner: finance-security
  approvalRef: approval-2081
  effectiveFrom: "2026-12-01T00:00:00+07:00"
~~~

Trong triển khai thật:

- Tập trung **policy logic** và metadata ở nơi có versioning, review.
- Tách secrets/credentials khỏi policy artifact.
- Không tin `securityBlocked: false` nếu giá trị do client tự khai.
- Chỉ PERMIT nếu resource và actor được lấy từ nguồn đáng tin.
- Định nghĩa nghĩa `withinEmploymentWindow` theo quan hệ làm việc cụ thể.
- Nếu một obligation không thể thực thi, PEP phải xử lý theo cách an toàn.

### 12.1. So sánh hai revision bằng test case

~~~text
Case A:
  subject.lifecycleStatus = ACTIVE
  role = FinanceReader
  resource.tenant = same tenant
  securityBlocked = false
  result v8 = PERMIT
  result v9 = PERMIT

Case B:
  subject.lifecycleStatus = LEAVER
  role claim vẫn FinanceReader
  resource.tenant = same tenant
  result v8 = PERMIT (rule thiếu chặn Leaver)
  result v9 = DENY

Case C:
  subject.lifecycleStatus = ACTIVE
  role = FinanceReader
  resource.tenant = other tenant
  result v8 = DENY
  result v9 = DENY
~~~

Các quyết định ở v8/v9 là **giả định của ví dụ**. Không được suy luận rằng mọi phiên bản có số lớn hơn đều xử lý đúng Leaver; phải kiểm nội dung và dữ liệu.

## 13. Version và các yếu tố ảnh hưởng quyết định theo thời gian

Để tái hiện một kết quả, cần coi authorization là hàm:

~~~text
Decision = Evaluate(
  policyArtifact,
  actorIdentity,
  currentEntitlements,
  resourceSnapshot,
  environment,
  approvals,
  timestamps
)
~~~

Khi audit nói “đã dùng policy v9”, cần biết những yếu tố khác:

- **Identity:** issuer+sub/account link, identityId, workerType và quan hệ JML.
- **Entitlement:** role nào được duyệt, lúc nào bị thu hồi.
- **Resource:** tenant, owner, classification và revision.
- **Environment:** auth_time, ACR/AMR nếu cần, risk context, thời điểm.
- **Policy:** version/digest, nguồn quyết định, kết hợp rule và obligations.
- **Execution:** PEP có thật sự áp giới hạn và thực thi không.

Một phiên bản policy **không cố định dữ liệu động**. Những sự kiện Mover/Leaver mới có thể thay đổi kết quả ngay khi PIP cập nhật, dù PDP vẫn dùng cùng revision.

### 13.1. Decision snapshot cho kiểm toán

Không nên lưu dữ liệu bí mật hoặc toàn bộ hồ sơ cá nhân trong mỗi decision. Có thể lưu **tham chiếu có thể tra cứu an toàn, reason code, policy version, attribute version/freshness, input digest có phạm vi** và áp retention.

Với kết quả cần tái hiện một cách chính xác, phải bảo đảm bản sao lịch sử của **policy artifact và những dữ liệu quan trọng** còn truy xuất được theo quyền và chính sách lưu trữ.

## 14. Rollback chính sách: quay lại bản cũ có luôn an toàn?

**Rollback** thường được hiểu là chuyển hệ thống về policy artifact trước đó khi bản mới gây lỗi. Trong authorization, thao tác này có thể **khôi phục một quyền đã bị cố ý thu hồi**, nên không thể xem rollback là cách chữa lỗi vô hại.

Ví dụ:

~~~text
Revision 7: Admin có quyền export mọi dữ liệu
Revision 8: Admin cần export approval và đúng tenant
Revision 9: Lỗi parse khiến một số request hợp lệ bị DENY

Rollback 9 -> 7:
  Sửa lỗi khả dụng nhưng vô tình mở quyền export-all.

Hướng an toàn hơn:
  Phát revision 10 sửa lỗi parse
  và giữ nguyên các ràng buộc bảo mật của revision 8.
~~~

### 14.1. Rollback là một change có rủi ro

Trước khi quay về version trước, cần:

1. Xác định **những rule nào sẽ thay đổi**, kể cả hiệu ứng cấp thêm quyền.
2. Kiểm tra các **security deny/hotfix** đã được thêm sau bản cũ.
3. Đánh giá scope: tenant, nhóm người dùng, ứng dụng và tài nguyên bị ảnh hưởng.
4. Có approval phù hợp với mức thay đổi.
5. Kiểm tra khả năng tương thích với schema và PEP/PDP hiện hành.
6. Phát hành/ghi nhận một **rollout event mới**, không sửa lịch sử artifact.
7. Giám sát quyền thật và hoàn thành reconciliation sau rollout.

**Một artifact cũ vẫn bất biến, nhưng hành động kích hoạt lại nó là một sự kiện quản trị mới** với owner, thời điểm và bằng chứng riêng.

### 14.2. Rollback một phần và policy dependency

Nếu policy-read v9 phụ thuộc role-map v7, chỉ rollback policy-read về v8 nhưng giữ role-map v7 có thể tạo ra kết quả không được kiểm thử. Nên xem xét **bundle dependency** và chạy test với tổ hợp version được triển khai thật.

### 14.3. Khi nào nên fix-forward?

**Fix-forward** là phát hành một revision mới sửa lỗi và giữ các kiểm soát bảo mật cần thiết. Cách này thường phù hợp khi rollback có thể tái mở quyền nguy hiểm hoặc schema đã thay đổi không tương thích.

Không có quy tắc “luôn fix-forward” cho mọi sự cố; quyết định phụ thuộc ảnh hưởng vận hành và rủi ro. Nhưng **mở lại quyền không được phê duyệt không thể là hành động mặc định**.

## 15. Policy hotfix và chặn truy cập khẩn cấp

Một số tình huống không thể chờ rollout thông thường:

- Một service account hoặc tài khoản người dùng bị nghi bị chiếm quyền.
- Một quyền quản trị đã được cấp sai.
- Một nhóm người dùng đã Leaver nhưng còn access token và role cũ.
- Một tenant bị lộ dữ liệu do rule cho phép cross-tenant.
- Một policy mới vô tình bỏ điều kiện approval.

### 15.1. Emergency deny

Có thể thiết kế một **security-block policy** hoặc control plane đáng tin có thể chặn chủ thể/tài nguyên độc lập với đợt rollout bình thường. Ví dụ:

~~~text
IF subject.securityBlocked == TRUE
THEN DENY

IF tenant.securityIncidentLock == TRUE
   AND action.classification == SENSITIVE
THEN DENY
~~~

Đây là mã giả. Muốn chặn nhanh, cần biết **PEP nào thực sự kiểm tra security block**, dữ liệu block có đủ mới không và có hệ thống nào tiếp tục dùng token offline mà không kiểm trạng thái.

### 15.2. Khẩn cấp không miễn trừ audit

Hotfix vẫn cần:

- Người có thẩm quyền kích hoạt.
- Lý do và ticket/incident reference.
- Giới hạn đối tượng, scope và thời gian khi thích hợp.
- Version/digest mới hoặc một version của lớp deny khẩn cấp.
- Theo dõi coverage và kiểm tra hiệu quả.
- Review hậu sự cố.

Không dùng “emergency” như lý do xóa log, sửa lén artifact đã ký hoặc cấp một role wildcard không thời hạn.

### 15.3. Fail-safe khi version không xác minh được

Nếu PDP trả `PERMIT` nhưng PEP không thể xác định đó có phải version còn được phép dùng hay không, tài nguyên nhạy cảm nên **chặn hoặc yêu cầu đánh giá lại qua đường tin cậy** theo policy. Không hạ về một policy cũ chỉ vì hệ thống chưa kết nối được registry.

## 16. Chính sách và tình trạng vòng đời Joiner–Mover–Leaver

Versioning chỉ có ý nghĩa khi được gắn với **quyền nghiệp vụ hiện hành**. Trong IAM lifecycle, một người có thể có account và phiên đã xác thực nhưng không còn entitlement của vai trò cũ.

### 16.1. Các nguồn khác nhau

| Nguồn/thành phần | Vai trò đối với quyền | Cách versioning liên quan |
| --- | --- | --- |
| **HRIS / nguồn hợp đồng** | Quan hệ làm việc, trạng thái, effectiveAt | Event/relationship revision khác policy version |
| **Identity registry / IGA** | Account link, approval, desired access | Entitlement revision, approval reference |
| **Directory / IdP** | Nhóm, xác thực, SSO và claim | Dữ liệu có thể replication/sync chậm |
| **SCIM / connector** | Provision/deprovision account/nhóm tại SaaS | Connector apply status khác rollout policy |
| **PDP** | Đánh giá rule trên context hiện hành | Đúng policy bundle revision |
| **PEP** | Chặn/thi hành ở API hoặc resource | Cần decision hiện hành và obligations |
| **Reconciliation** | So desired vs observed và kiểm effective access | Chứng minh quyền sau thay đổi version/JML |

### 16.2. Thời điểm nào là căn cứ?

Ví dụ **Policy revision 9** đã active từ 08:00, còn HRIS đánh dấu **Leaver effectiveAt 09:00**. Lúc 08:30, một số hành động theo policy có thể hợp lệ; lúc 09:01, cùng policy revision 9 phải ra **DENY** nếu PIP biết quan hệ đã hết hiệu lực và chính sách yêu cầu ACTIVE.

Ngược lại, nếu PIP chưa cập nhật Leaver, cùng policy revision 9 có thể vẫn cho PERMIT sai do thuộc tính cũ. Vì thế phải thiết kế cả **policy freshness** lẫn **identity/entitlement freshness**.

## 17. Joiner: policy version nào áp dụng cho người mới?

Trong **Joiner**, HRIS xác nhận người mới và ngày bắt đầu, identity proofing liên kết người thật với hồ sơ, IdP/SSO cấp phương thức đăng nhập, IGA tính role được phép và SCIM/API tạo account ở ứng dụng đích.

### 17.1. Preboarding có phải là ACTIVE?

Không mặc định. Một tổ chức có thể có policy cho preboarding portal:

~~~text
PERMIT onboarding.documents.read IF
    relationship.status == PRE_HIRE
    AND identity.proofingComplete
    AND resource.scope == PREBOARDING
ELSE DENY
~~~

Sau khi effectiveAt và điều kiện xác minh đạt yêu cầu, policy của người đang làm việc mới cho phép quyền nghiệp vụ rộng hơn. Không cấp quyền production chỉ vì account đã được provision sớm.

### 17.2. Thay đổi policy trong lúc Joiner đang chạy

Giả sử Joiner bắt đầu theo policy revision 7, nhưng trước ngày nhận việc, security phát hành revision 8 thêm điều kiện về approval.

- **Quyền cần có vào thời điểm thực thi** phải tuân theo policy hiệu lực theo thiết kế.
- Một workflow Joiner cũ không được dùng `revision=7` để bỏ qua điều kiện mới.
- Những tác vụ provisioning chưa chạy cần có **version guard hoặc quyết định lại**.
- Nếu đã provision dư quyền trước revision mới, IAM cần remediation và reconciliation.

**Version của workflow tạo account không tự quyết định quyền được phép tại thời điểm sử dụng.**

### 17.3. Ví dụ checklist Joiner

- Account linking đúng identityId, không dựa email đơn thuần.
- Role được duyệt theo policy active.
- Các điều kiện workerType, department, manager và effectiveAt đủ dữ liệu.
- Đích SCIM/API đã áp account và entitlement.
- PEP ở ứng dụng dùng version hợp lệ.
- Không có quyền extra ở đích; audit truy được approval và decision.

## 18. Mover: policy version và loại bỏ quyền cũ

**Mover** có thể đổi bộ phận, vai trò, pháp nhân, cấp quản lý hoặc dự án, trong khi employment status vẫn ACTIVE.

Ví dụ:

~~~text
Trước Mover:
  role = SupportReader
  policy v8 -> PERMIT support.ticket.read

Sau Mover:
  desiredRole = FinanceReader
  policy v9 -> DENY support.ticket.read
  policy v9 -> PERMIT finance.invoice.read nếu đủ approval

Nhưng:
  access token cũ vẫn có SupportReader
  SaaS role SupportReader chưa được gỡ
  một PDP vẫn chạy v8
~~~

### 18.1. Ba lớp phải theo dõi

1. **Desired access:** IGA tính lại theo role/job hiện hành.
2. **Provisioned/observed entitlement:** group/role ở directory, SaaS hoặc cloud có được gỡ/cấp đúng không.
3. **Effective authorization:** API/PEP thực tế có còn cho phép quyền cũ khi request tới không.

**Policy version mới không tự thu hồi role đã lưu trong SaaS hoặc token đang còn hiệu lực.**

### 18.2. Race condition giữa Mover và rollout

Nếu policy v9 thay cách ánh xạ `department`, nhưng SCIM vẫn giữ group cũ, một người có thể nhận quyền nhầm. Một migration an toàn có thể:

- Chạy test trên snapshot user/role/resource đại diện.
- Xác định thứ tự đổi **attribute source, role mapping, policy version**.
- Chặn quyền cũ ở PEP trong cửa sổ chuyển đổi.
- Recheck access sau rollout.
- Ghi và xử lý **EXTRA_ACCESS**, không chỉ xem job đã “success”.

### 18.3. Không dùng step-up để sửa role sai

Một người hoàn thành passkey/MFA mạnh vẫn không được phép truy cập Support nếu role Support đã mất hiệu lực. **Step-up tăng assurance, không tự khôi phục authorization.**

## 19. Leaver: policy mới chưa đủ nếu phiên và token còn tồn tại

**Leaver** cần khóa đường truy cập thực tế khi quan hệ làm việc/hợp đồng hết hạn.

Một luồng có thể là:

~~~mermaid
flowchart TD
    HR["HRIS: Leaver effectiveAt"] --> IGA["IGA: desired access = revoke"]
    IGA --> IdP["IdP: disable/revoke theo policy"]
    IGA --> SCIM["SCIM/API: disable và remove roles"]
    IGA --> Block["Security block / authorization control"]
    Block --> PEP["PEP API: current-state check"]
    IdP --> VERIFY["Reconciliation / audit"]
    SCIM --> VERIFY
    PEP --> VERIFY
    VERIFY --> Q{"Đường truy cập trong scope đã chặn?"}
    Q -->|"Chưa"| E["Exception, owner, escalation"]
    Q -->|"Đã xác minh"| DONE["Kết thúc và lưu evidence"]
    E --> VERIFY
~~~

### 19.1. Policy version và local session là hai việc khác nhau

Một ứng dụng có thể dùng policy v9 nhưng vẫn có **local session** được tạo trước Leaver, hoặc token chứa role cũ. Nếu PEP chỉ kiểm token cryptographically valid mà không tham chiếu trạng thái đủ mới, v9 có thể không phát huy tác dụng như kỳ vọng.

Cần cân nhắc:

- Chặn new login tại IdP.
- Thu hồi/giới hạn session và refresh token khi nền tảng hỗ trợ.
- SCIM/API deprovision account và entitlement.
- PEP tái kiểm trạng thái Leaver ở hành động nhạy cảm.
- Có cơ chế invalidate cache hoặc global deny của security block.
- Reconciliation kiểm cả quyền ở đích và luồng truy cập quan trọng.

### 19.2. Policy rollback sau Leaver

Nếu revision 9 đã thêm chặn Leaver, rollback về revision 7 **có thể mở lại quyền của người đã nghỉ**. Đây là lý do cần **rollback risk review**, hotfix và lớp deny khẩn cấp tách biệt khi thiết kế.

### 19.3. Nhiều quan hệ làm việc

Một người có thể nghỉ ở pháp nhân A nhưng tiếp tục hợp đồng hợp lệ tại B. PBAC cần xét **relationship nào cấp quyền cho resource cụ thể**, không áp một event TERMINATED của A như lý do chặn mọi công việc trong B nếu policy không yêu cầu.

## 20. Service account và workload identity

Policy versioning cũng áp dụng cho **service account, bot, máy chủ, pipeline CI/CD, managed identity và workload principal**.

| Thuộc tính workload | Ví dụ | Rủi ro khi policy đổi |
| --- | --- | --- |
| **Owner** | platform-team | Owner cũ Mover/Leaver chưa bàn giao |
| **Purpose** | deploy production | Policy mới hạn chế repo/environment |
| **Audience** | deployment-api | Credential dùng sai resource |
| **Scope** | deployment.create | Role wildcard còn trên cloud |
| **Principal identity** | pipeline/repo/job subject | Claim/source trust thay đổi |
| **Credential lifetime** | short-lived credential | Token đã phát vẫn còn hiệu lực |
| **Environment** | production | Deploy từ test project nếu mapping sai |
| **Expiry** | project decommission date | Account mồ côi sau dự án |

### 20.1. Workload federation không giống human SSO

Một workload có thể dùng OIDC federation để xin credential cloud ngắn hạn, nhưng đây **không phải đăng nhập tương tác** của nhân viên. Quyền workload cần kiểm **issuer, audience, subject/claims, environment, role và owner** theo control plane hỗ trợ.

Khi policy v9 đổi phạm vi deploy từ toàn organization thành một project, phải kiểm:

- PDP/PEP và cloud IAM đang áp rule nào.
- Credential/token cũ còn thời hạn tới đâu.
- Role ở cloud đã được thu hẹp thật chưa.
- Pipeline cũ có đường API bypass không.
- Owner đã nhận trách nhiệm và có audit.

### 20.2. Mover/Leaver của owner

Không tự xóa workload còn cần cho sản xuất khi owner nghỉ việc. Phải **gỡ quyền người cũ, chuyển owner, rà secret/trust, xác minh quyền và ghi audit**. Service principal có lifecycle riêng.

## 21. Tích hợp IdP/SSO, RBAC/ABAC và SCIM khi đổi policy

Policy version có thể ảnh hưởng nhiều tầng, nhưng không tự thay chúng.

### 21.1. Authentication và authorization độc lập

**IdP/SSO** xác thực và có thể phát claims/phiên. **PBAC** quyết định quyền theo policy và context. Một ID token OIDC hợp lệ không tự chứng minh người dùng còn quyền thao tác.

**Access token** có audience/scope phù hợp cũng chưa chắc đủ quyền trên **đối tượng cụ thể**. API cần PEP kiểm resource, tenant, approval và trạng thái hiện hành.

### 21.2. RBAC và ABAC có thể cùng dùng

Ví dụ:

~~~text
PERMIT invoice.export IF
    subject.hasApprovedRole("FinanceExporter")
    AND subject.lifecycleStatus == ACTIVE
    AND subject.tenantId == resource.tenantId
    AND resource.classification <= subject.clearance
    AND session.assuranceSatisfies(policy.requiredAssurance)
    AND approval.isValidFor(resource.id)
ELSE DENY
~~~

**Policy revision 9** có thể bổ sung điều kiện approval hoặc tenant, trong khi **role FinanceExporter** đã tồn tại từ trước. Phải xác định việc đổi rule có cần **migrate entitlements** hay chỉ cần cập nhật PDP.

### 21.3. SCIM là provisioning, không phải policy distribution

SCIM quản lý user/group ở hệ thống đích theo capability. Nó **không tự đưa policy artifact v9 tới từng PDP**.

Một thay đổi policy có thể yêu cầu **SCIM gỡ/cấp group**, nhưng cần workflow kết nối release policy với provisioning và reconciliation. Ngược lại, SCIM trả thành công không chứng minh phiên/role cục bộ đã cập nhật tức thì.

### 21.4. Mapping group/claim thay đổi

Nếu policy v9 đổi từ `groups contains Finance` sang `entitlements contains FinanceExporter`, phải:

1. Xác định nguồn claim/entitlement có thẩm quyền.
2. Đảm bảo PIP/connector cung cấp đúng dữ liệu.
3. Test dữ liệu thiếu, trễ, trùng, thay đổi tenant.
4. Không ngầm coi mọi người đang có group Finance đều được cấp FinanceExporter.
5. Rà các account JIT hoặc service account bị ảnh hưởng.
6. Đối soát quyền sau chuyển đổi.

## 22. Thiết kế kiểm tra version tại PEP trong Java

Ví dụ **mã giả Java** dưới đây minh họa **ý tưởng version guard**, không phải SDK hoàn chỉnh hoặc code có thể copy chạy trực tiếp.

~~~java
// PSEUDOCODE: các type/service được đặt tên để giải thích.
Decision authorizeSensitiveAction(
        AuthenticatedPrincipal principal,
        SensitiveAction action) {

    Identity identity = identities.readCurrent(principal.identityId());
    Resource resource = resources.loadTrusted(action.resourceId());

    if (!identity.isAllowedToUse(resource) || identity.securityBlocked()) {
        return Decision.deny("IDENTITY_OR_LIFECYCLE_BLOCKED");
    }

    // Không lấy version từ request client.
    PolicyRequirement requirement = releaseController
        .requirementFor(action.type(), resource.environment());

    Decision decision = trustedPdp.evaluate(
        principal,
        action,
        resource,
        identity,
        trustedContext()
    );

    if (!requirement.accepts(decision.policyArtifactId(),
                             decision.policyDigest(),
                             decision.engineProfile())) {
        return Decision.deny("POLICY_VERSION_NOT_APPROVED");
    }

    if (!decision.isPermit() || !obligationsSatisfied(decision)) {
        return Decision.deny("POLICY_NOT_SATISFIED");
    }

    // Với tài nguyên nhạy cảm cần kiểm tra lại khi thực thi.
    if (!currentStateGuard.stillValid(
            identity.id(), resource.id(),
            identity.version(), resource.version(),
            decision.policyDigest())) {
        return Decision.deny("STATE_CHANGED_REEVALUATE");
    }

    return actions.executeIdempotentlyWithScope(principal, action, resource);
}
~~~

### 22.1. Giới hạn của mã giả

- `requirementFor` phải đến từ **control plane đáng tin**; nếu release controller stale, guard có thể chấp nhận bản cũ.
- `Decision` phải được **xác minh tính toàn vẹn và scope** trong kiến trúc PDP remote.
- Không chỉ kiểm `policyDigest` rồi bỏ qua **entitlement và resource version**.
- Trong database, cần chiến lược transaction/version check để tránh race condition giữa guard và commit.
- `obligationsSatisfied` phải kiểm những điều kiện bắt buộc, không chỉ trả true theo mặc định.
- Không dùng policy revision để tự nâng authority cho actor.

### 22.2. Cấu hình Spring Security ở điểm thực thi

Ví dụ method-level authorization:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class InvoiceExportService {

    @PreAuthorize(
        "@pbacEnforcer.canExport(authentication, #invoiceId)"
    )
    public ExportResult exportInvoice(String invoiceId) {
        return doAuthorizedExport(invoiceId);
    }

    private ExportResult doAuthorizedExport(String invoiceId) {
        // Giả định repository chỉ đọc đúng tenant/resource scope.
        // Production cần current-state guard, audit và transaction control.
        return new ExportResult();
    }
}
~~~

Mẫu trên **giả định** có bean `pbacEnforcer`, DTO và business service tương ứng; không phải ứng dụng Java hoàn chỉnh. Phải bật method security, xử lý self-invocation/proxy bypass theo kiến trúc, cấu hình xác thực token/session và kiểm cả API/background job khác.

**Không dùng annotation như bằng chứng hệ thống đã enforce** nếu một đường gọi khác có thể truy cập trực tiếp dữ liệu mà không qua policy.

## 23. Kiểm thử policy version

Kiểm thử **không chỉ xem file policy có parse được không**. Cần chứng minh thay đổi version **tạo đúng quyết định và PEP áp đúng**.

### 23.1. Ma trận case quan trọng

| Case | Policy cũ | Policy mới | Kỳ vọng khi active bản mới |
| --- | --- | --- | --- |
| ACTIVE FinanceReader đúng tenant | PERMIT | PERMIT | PERMIT nếu đủ điều kiện |
| ACTIVE FinanceReader sai tenant | Có thể PERMIT do lỗi | DENY | Chặn cross-tenant |
| Mover đã mất role Support | PERMIT nếu claim cũ | DENY | DENY cả khi token cũ |
| Leaver còn session | PERMIT nếu thiếu check | DENY | Chặn ở PEP |
| Approval hết hạn | PERMIT nếu thiếu thời hạn | DENY | Chặn thao tác |
| Service principal ngoài environment được duyệt | Có thể PERMIT | DENY | Chặn API/cloud action |
| PIP không trả employment status | Lỗi/không xác định | INDETERMINATE | PEP không thực thi nhạy cảm |
| PDP-B còn policy cũ | PERMIT | PDP-A DENY | Cảnh báo skew và guard |
| Rollback về bản mở quyền rộng | PERMIT | Không còn được duyệt | Chặn rollback nguy hiểm |
| Phiên có step-up nhưng không có entitlement | PERMIT nếu rule sai | DENY | Step-up không hợp thức hóa quyền |
| Policy mới có obligation PEP cũ không hỗ trợ | Không có obligation | Có obligation | Không được bỏ qua nghĩa vụ |

Các kết quả của chính sách cũ là **kịch bản giả định để tạo bài test**, không khẳng định mọi phiên bản cũ đều có lỗi.

### 23.2. Những loại test cần có

1. **Unit tests:** rule allow/deny, boundary conditions, tenant/role/resource.
2. **Regression/differential tests:** so quyết định giữa hai revision trên cùng snapshot dữ liệu.
3. **Contract tests:** PIP field/schema, PDP result, PEP obligations.
4. **Integration tests:** API/DB thật bị chặn khi DENY.
5. **Negative tests:** tài khoản Leaver, quyền Mover cũ, token stale, tenant mismatch.
6. **Rollout tests:** version skew, node thiếu bundle, canary và rollback.
7. **Fault tests:** PDP/PIP outage, timeout, clock skew, corrupt bundle, signature mismatch.
8. **Concurrency tests:** policy/entitlement/resource đổi giữa decision và commit.
9. **Replay/idempotency tests:** không dùng decision/challenge cũ cho resource khác.
10. **Audit tests:** kiểm `policyVersion`, artifact digest, decision và execution outcome.

### 23.3. Shadow evaluation không được biến thành shadow PERMIT

Một policy mới có thể được đánh giá song song với policy đang active để **so sánh** quyết định. Nếu shadow policy trả PERMIT rộng hơn, không được tự dùng kết quả này để cho truy cập production cho tới khi đã được review và kích hoạt.

## 24. Kiểm toán và khả năng tái hiện quyết định

Một bản ghi audit nên giúp trả lời:

- Ai hoặc workload nào yêu cầu action?
- Resource/tenant cụ thể nào?
- Policy/bundle **revision và digest** nào được dùng?
- PDP/PEP instance nào xử lý?
- Identity, entitlement và resource ở version hoặc độ mới nào?
- Decision là gì; obligations có thực thi không?
- Hành động bị chặn, thực thi hay lỗi?
- Policy có được duyệt và đang active tại thời điểm đó không?

### 24.1. Mẫu event minh họa

~~~json
{
  "eventId": "authz-event-7742",
  "correlationId": "request-20261123-77",
  "principalType": "HUMAN",
  "identityRef": "person-1042",
  "action": "invoice.export",
  "resourceRef": "invoice-412",
  "tenantRef": "tenant-a",
  "policyId": "finance-invoice-export",
  "policyRevision": 9,
  "bundleVersion": "finance-bundle-2026.11.23.2",
  "artifactDigest": "sha256:illustrative-placeholder",
  "pdpInstance": "pdp-east-3",
  "identityVersion": 41,
  "resourceVersion": 12,
  "decision": "DENY",
  "reason": "ROLE_REVOKED",
  "enforcementOutcome": "BLOCKED",
  "evaluatedAt": "2026-11-23T10:15:00+07:00"
}
~~~

Đây là dữ liệu **minh họa**, không phải schema tiêu chuẩn. Không nên ghi full ID/access/refresh token, session cookie, OTP, secret, private key hoặc toàn bộ dữ liệu cá nhân không cần thiết vào log.

### 24.2. Decision khác execution

~~~text
Authentication: SUCCESS
Authorization PDP: DENY (policy revision 9)
PEP outcome: BLOCKED
Business operation: NOT_EXECUTED
~~~

Và:

~~~text
Authentication: SUCCESS
Authorization PDP: PERMIT (policy revision 9)
PEP outcome: FAILED (database unavailable)
Business operation: NOT_EXECUTED
~~~

**PERMIT không chứng minh giao dịch thành công**; không nên gộp decision và execution trong một trạng thái duy nhất.

### 24.3. Tái diễn lại quyết định lịch sử

Để audit một request cũ, có thể dùng artifact lịch sử cùng snapshot thuộc tính/quan hệ và môi trường thời điểm đó. Nhưng **replay chỉ để điều tra hoặc test**, không tự cấp quyền hiện tại theo một policy đã retired.

## 25. Reconciliation sau đổi policy

Sau khi policy version mới được active, phải kiểm tra **trạng thái mong muốn và thực tế**:

- Role/entitlement của nhân viên có đúng với policy active và approval không?
- Những quyền cũ của Mover đã được gỡ khỏi directory/SaaS chưa?
- Leaver còn account, token, session hay quyền cloud nào không?
- Workload principal có scope/owner/hạn dùng phù hợp không?
- Mọi PDP/PEP trong scope có dùng version được duyệt không?
- PEP có thực sự DENY ở hành động bị cấm không?
- Có ứng dụng JIT hoặc local role nằm ngoài SCIM/IGA không?

### 25.1. So ba trạng thái

~~~text
DESIRED_POLICY
  Phiên bản policy được phê duyệt và có hiệu lực.

OBSERVED_POLICY
  Policy/bundle thực tế đã load và dùng bởi PDP/PEP.

EFFECTIVE_ACCESS
  Hành động thực tế có được API/tài nguyên chấp nhận không.
~~~

Ba trạng thái này **không phải một**. Một instance có đúng policy nhưng token/entitlement cũ khiến PERMIT sai; hoặc một phiên bản cũ vẫn chạy nhưng tình cờ từ chối một request. Phải đối soát **policy convergence và quyền hiệu lực**.

### 25.2. Phân loại drift

| Drift | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **POLICY_VERSION_DRIFT** | PDP-B v8, desired v9 | Kiểm rollout/health, đánh giá tác động |
| **ENTITLEMENT_DRIFT** | Role Support còn ở SaaS sau Mover | Gỡ entitlement, kiểm nguồn và approval |
| **ATTRIBUTE_DRIFT** | Department claim IdP khác HRIS | Kiểm sync/claim freshness |
| **ENFORCEMENT_GAP** | Endpoint export bỏ qua PDP | Sửa PEP và kiểm thử bypass |
| **SESSION_RESIDUAL** | Leaver còn token/phiên được chấp nhận | Revoke/TTL/current-state guard |
| **OWNER_GAP** | Workload thiếu owner sau chuyển giao | Cập nhật ownership và rà credential |
| **AUDIT_GAP** | Không lưu version/decision | Sửa observability và quy trình lưu chứng cứ |

**Không tự remediation bằng cách cấp lại quyền từ policy cũ khi trạng thái nguồn mới chưa rõ.** Khi dữ liệu bất nhất, cần owner, mức ưu tiên và xử lý theo rủi ro.

## 26. Chỉ số vận hành Policy version

| Chỉ số | Mục đích | Điều cần tránh |
| --- | --- | --- |
| **Active version coverage** | Tỷ lệ PDP/PEP chạy bản được duyệt | Chỉ đo “artifact đã tải” |
| **Version skew duration** | Khoảng thời gian nhiều instance khác version | Chấp nhận skew không giới hạn |
| **Deployment-to-active latency** | Từ phát hành đến lúc active ở scope cần thiết | Nhầm thời gian publish với active |
| **Unauthorized PERMIT difference** | Số trường hợp bản mới/cũ khác nhau theo hướng mở quyền | Bỏ qua diff khi canary |
| **Rollback security regressions** | Quyền bị mở lại do rollback | Rollback tự động không review |
| **Policy test coverage** | Bao phủ rule, DENY, tenant, JML, service identity | Chỉ tính số test tổng |
| **PIP/attribute staleness** | Độ cũ thuộc tính dùng trong decision | Coi policy đúng là đủ |
| **PEP enforcement gap count** | Đường API/job không thực thi rule | Chỉ kiểm frontend |
| **Leaver access denial latency** | Từ effectiveAt đến khi PEP chặn quyền | Chỉ đo gửi lệnh SCIM |
| **Mover extra access count** | Quyền cũ chưa gỡ sau Mover | Chỉ đếm role mới đã cấp |
| **Policy decision audit completeness** | Mức có đủ version/digest/context/outcome | Lưu secret trong log |
| **Workload owner coverage** | Principal phi con người có owner/policy | Bỏ qua danh tính dịch vụ |

Tổ chức cần xác định mục tiêu theo **mức rủi ro, loại tài nguyên và khả năng hệ thống**, không khẳng định một SLA thời gian áp dụng chung cho mọi policy engine.

## 27. Tình huống tổng hợp: chính sách tài chính thay đổi

Một doanh nghiệp có cổng Finance Portal dùng **OIDC SSO**, quản trị user/role bằng **SCIM**, phân quyền theo **RBAC/ABAC** và dùng **PDP** phân tán hai vùng.

### 27.1. Ngày đầu: revision 7

Policy v7 cho FinanceReader đọc tài liệu Finance trong tenant được cấp nhưng thiếu điều kiện `employmentStatus == ACTIVE`. Một nhà thầu hết hợp đồng vẫn còn local session, có nguy cơ dùng permission cũ.

Đội IAM phát hiện rủi ro và tạo change request sửa rule.

### 27.2. Review và phát hành revision 8

Revision 8 bổ sung:

~~~text
AND relationship.status == ACTIVE
AND relationship.effectiveAt <= now
AND subject.tenantId == resource.tenantId
~~~

Resource owner và security phê duyệt đúng artifact/digest. Tests xác minh FinanceReader ACTIVE vẫn đọc được hóa đơn hợp lệ, Leaver bị DENY và không đọc chéo tenant.

### 27.3. Rollout gặp version skew

PDP-East đã chạy v8, PDP-West còn v7 do sự cố phân phối. Cùng một session của nhà thầu Leaver có thể nhận DENY ở East nhưng PERMIT ở West nếu PEP không có guard.

Release controller phát hiện version skew, chặn các hành động nhạy cảm chưa có decision đạt version tối thiểu, đồng thời khắc phục rollout. **Không tuyên bố hoàn tất chỉ vì CICD báo thành công**.

### 27.4. Mover đổi role trong lúc rollout

Nhân viên **Lan** chuyển Finance sang Operations. Role FinanceReader được gỡ ở IGA, nhưng claim token cũ còn FinanceReader và một SaaS chưa nhận SCIM.

PDP v8 cần **đọc entitlement và quan hệ hiện hành** để từ chối các hành động Finance. Reconciliation theo dõi role cũ ở SaaS, session/token và kiểm endpoint export; version mới **không tự xóa quyền cục bộ**.

### 27.5. Rollback sai bị chặn

Một lỗi schema phụ làm một số request hợp lệ nhận INDETERMINATE. Rollback trực tiếp v8 về v7 có thể mở lại truy cập của Leaver. Nhóm phát hành **revision 9 sửa schema** nhưng giữ yêu cầu ACTIVE/tenant; lỗi được xử lý có audit và negative tests.

### 27.6. Kết thúc sự cố

Bằng chứng đóng việc gồm:

- Policy revision 9 có approval, artifact digest và build provenance.
- Mọi PDP/PEP trong scope dùng version phù hợp.
- Leaver và người Mover bị DENY đúng ở API.
- SCIM/API và reconciliation xác minh entitlement ở đích.
- Audit ghi decision, version, identity/attribute freshness và kết quả enforcement.

**Bài học:** quản lý version thành công phải chứng minh cả **policy đã được duyệt, đã triển khai, đã được dùng và quyền thực tế đúng**.

## 28. Checklist triển khai Policy version

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Policy ID ổn định và revision không bị tái sử dụng? | Registry/immutable artifacts |
| Policy bundle/schema/engine version được tách biệt? | Metadata và compatibility contract |
| Mỗi artifact có digest hoặc bảo vệ toàn vẹn phù hợp? | Build/publish evidence |
| Owner, reviewer và approval gắn đúng nội dung? | Review record, change ticket |
| Có lifecycle draft→approved→active→retired? | State transitions và audit |
| Có định nghĩa desired/deployed/loaded/active version? | Release controller và telemetry |
| Có xác định effectiveFrom/timezone? | Policy activation/expiry contract |
| Có test thay đổi quyền theo action/resource/tenant? | Regression và negative tests |
| Có shadow evaluation không cấp PERMIT thật? | Diff reports, rollout records |
| Canary có giới hạn phù hợp rủi ro? | Scope, stop conditions |
| Có version guard cho quyền nhạy cảm? | PEP checks, deny-on-stale tests |
| Client có thể tự chọn policy cũ không? | Không có untrusted version selector |
| PIP attribute có nguồn và freshness rõ? | HRIS/IGA/resource source contract |
| Có kiểm TOCTOU và cache invalidation? | Resource/identity version guard |
| Có xử lý skew giữa nhiều PDP? | Version coverage, alerts |
| Rollback có review tránh mở quyền cũ? | Security regression tests |
| Emergency deny có owner, audit và coverage? | Runbook, security-block proof |
| Joiner có đúng effectiveAt và role approved? | JML tests, onboarding checks |
| Mover có gỡ role cũ và token cache? | Reconciliation, stale-token test |
| Leaver còn session có bị PEP chặn? | End-to-end deny evidence |
| IdP/SSO/OIDC không bị xem là authorization? | Token contract và resource checks |
| SCIM/API provisioning không nhầm với policy rollout? | Separate workflow evidence |
| Workload principal có owner và scope/version? | Workload IAM inventory |
| Audit log có policyId/version/digest và outcome? | Correlation ID, retention |
| Có test PDP/PIP outage và INDETERMINATE? | Fault tests, fail-safe policy |
| Có đối soát observed policy và effective access? | Dashboard, exception owners |

## 29. Những nhầm lẫn thường gặp

1. **“Policy version chỉ là số để ghi chú.”** Nó phải gắn artifact, phê duyệt, hiệu lực và chứng cứ triển khai.
2. **“Số version lớn hơn luôn bảo mật tốt hơn.”** Cần xem nội dung và test; một revision mới có thể mở quyền sai.
3. **“Đã publish nghĩa là mọi PDP active.”** Cần loaded/active/observed telemetry.
4. **“Cùng policy version luôn có cùng quyết định.”** Thuộc tính, role, resource và thời gian có thể khác.
5. **“Client được chọn policy version cho request.”** Đó có thể là bypass; version selection cần quyền kiểm soát.
6. **“Rollback về v7 chắc an toàn vì trước đây chạy ổn.”** Có thể khôi phục quyền từng bị thu hồi.
7. **“PDP đúng version là API an toàn.”** Một endpoint không có PEP vẫn bypass.
8. **“Policy v9 chặn Leaver thì session cũ tự mất.”** Cần PEP current-state check và session/token controls.
9. **“SCIM đã deactivate là policy update hoàn tất.”** SCIM và policy distribution khác nhau.
10. **“IdP đã gỡ group thì mọi token hết quyền.”** Token/session có lifecycle riêng.
11. **“Hash artifact tự chứng minh người phát được phép.”** Cần trust/signing và release governance phù hợp.
12. **“Không liên hệ được PDP thì dùng PERMIT cache vô hạn.”** Phải xử lý fail-safe theo rủi ro.
13. **“So chuỗi v9.10 và v9.9 theo từ điển được.”** Version ordering cần schema có ngữ nghĩa.
14. **“Shadow policy trả PERMIT thì có thể mở quyền.”** Shadow chỉ phục vụ so sánh.
15. **“Rehire được tự lấy lại quyền của identity cũ.”** Phải xác minh đúng người và tính lại entitlement.
16. **“Workload không cần Policy version vì không phải nhân viên.”** Service identity cũng phải được quản trị và audit.

## 30. Câu hỏi tự đánh giá

1. Policy ID khác Policy version và Policy bundle version như thế nào?
2. Vì sao published artifact nên bất biến và có content digest?
3. PAP, PDP, PIP và PEP có vai trò gì trong việc phát hành version?
4. Vì sao audit chỉ ghi `policyVersion=9` chưa đủ tái hiện quyết định?
5. Khi v9 thêm điều kiện security block, rollback về v7 có thể gây hậu quả gì?
6. So sánh desired, deployed, loaded, active và observed policy version.
7. Version skew giữa hai PDP có thể làm lộ dữ liệu trong tình huống nào?
8. Tại sao PEP không được tin header `X-Policy-Version` do client tự gửi?
9. Thay đổi schema attribute cần những loại contract test nào?
10. Cách khác biệt giữa shadow evaluation và canary khi đánh giá policy mới?
11. Khi HRIS phát Leaver, tại sao policy mới không tự kết thúc token hoặc SaaS session?
12. Một nhân viên Mover còn role cache cũ. Nên đo những trạng thái nào ngoài policy version?
13. PIP không đọc được employment status: policy engine và PEP nên hành xử ra sao?
14. Khác biệt giữa policy artifact version và entitlement version là gì?
15. Nêu cách giảm TOCTOU khi quyền bị thu hồi trước khi transaction commit.
16. Tại sao workload identity cần policy version, owner, audience và credential expiry?
17. So sánh khắc phục bằng rollback và fix-forward trong một sự cố policy.
18. Những trường audit nào chứng minh một request được đánh giá và chặn đúng revision?
19. Khi release controller báo 100% coverage nhưng một API vẫn PERMIT sai, có thể thiếu lớp kiểm soát nào?
20. Viết ba negative tests cho policy sửa lỗi cross-tenant và quyền Leaver tồn dư.

## 31. Ghi nhớ

**Policy version** trong **PBAC** là công cụ quản trị **một trạng thái cụ thể của chính sách phân quyền** để có thể phê duyệt, kiểm thử, phân phối, truy vết và điều tra. Một version đáng tin cần **định danh ổn định, artifact bất biến, kiểm soát nội dung và nguồn phát, trạng thái hiệu lực, version ở mỗi PDP/PEP, audit và kiểm thử sự khác biệt giữa các revision**.

Trong IAM **Joiner–Mover–Leaver**, thay đổi policy chỉ là **một lớp** của quản lý quyền: **HRIS/identity registry** xác định chủ thể và quan hệ, **IdP/SSO** cung cấp xác thực, **SCIM/API** cấp/đổi/thu hồi account, **RBAC/ABAC/PBAC** quyết định quyền, **PEP** thực thi tại tài nguyên, còn **reconciliation** kiểm chứng trạng thái thực. **Policy mới không tự thu hồi role, token, session hoặc quyền dịch vụ đã tồn tại**. Thiết kế an toàn phải quản lý **version skew, cache, hotfix, rollback, quyền cấp sai và bằng chứng chặn truy cập**, để ngăn quyền tồn dư ngay cả khi nhiều hệ thống chưa hội tụ.
