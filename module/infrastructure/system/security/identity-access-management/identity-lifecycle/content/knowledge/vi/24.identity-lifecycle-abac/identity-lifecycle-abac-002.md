# Subject attribute trong ABAC: thuộc tính chủ thể và quản lý vòng đời danh tính IAM

## 1. Subject attribute là gì?

Trong **Attribute-Based Access Control (ABAC)**, quyết định cho phép hay từ chối một hành động được đưa ra từ những thuộc tính đáng tin cậy của **chủ thể** (*subject*), **tài nguyên** (*resource*), **hành động** (*action*) và **môi trường/ngữ cảnh** (*environment*), cùng với chính sách hiện hành. **Subject attribute** là thuộc tính mô tả chủ thể đang yêu cầu quyền truy cập, chẳng hạn loại danh tính, trạng thái quan hệ làm việc, organization, department, clearance, project assignment hoặc mức đảm bảo xác thực.

Ví dụ, công ty quy định chỉ nhân viên **đang có quan hệ làm việc hợp lệ**, thuộc phòng Tài chính và đã được duyệt cho dự án Atlas mới được xem báo cáo tài chính của Atlas. Khi một người gửi request, hệ thống không chỉ hỏi “đã đăng nhập chưa?” mà còn kiểm tra **employmentStatus**, **departmentId**, **approvedProjects** và những điều kiện tài nguyên tương ứng.

Chủ thể có thể là:

- **Người dùng:** nhân viên, nhà thầu, thực tập sinh, đối tác hoặc người có nhiều quan hệ làm việc.
- **Workload/service identity:** ứng dụng, job CI/CD, robot hoặc dịch vụ gọi API không có con người tương tác.
- **Client hành động thay mặt người dùng:** có cả danh tính của client và người dùng được ủy quyền; không được trộn hai phạm vi quyền.

Subject attribute **không tự là quyền truy cập**. Giá trị **departmentId = Finance** chỉ mô tả một thuộc tính; chính sách cần định nghĩa thuộc tính đó liên quan thế nào tới hành động trên tài nguyên. Một người thuộc Finance **không mặc nhiên** có quyền xem mọi báo cáo tài chính nếu thiếu phê duyệt, vai trò, scope hoặc điều kiện khác.

Trong module quản lý vòng đời **Joiner–Mover–Leaver (JML)**, subject attribute thay đổi theo dữ liệu **HRIS**, nguồn bảo trợ, dự án và IAM/IGA. Nếu thay đổi không được cập nhật đến hệ thống thực thi, có thể phát sinh **quyền truy cập tồn dư** hoặc **từ chối nhầm** người đã được cấp quyền.

## 2. Subject attribute khác các thành phần ABAC còn lại thế nào?

| Nhóm thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Subject attributes** | Ai hoặc workload nào đang yêu cầu? Có đặc tính gì? | employmentStatus, departmentId, organizationMemberships, clearanceLevel |
| **Resource attributes** | Tài nguyên có tính chất gì? | ownerOrganization, projectId, sensitivity, retentionClass |
| **Action attributes** | Hành động đang được yêu cầu thuộc loại nào? | READ, EXPORT, APPROVE, DELETE |
| **Environment attributes** | Ngữ cảnh yêu cầu là gì? | thời điểm, trạng thái thiết bị đã xác minh, vị trí được suy luận |

Ví dụ:

~~~text
Subject:
  identityId = iam-482
  employmentStatus = ACTIVE
  departmentId = FINANCE
  approvedProjects = [ATLAS]
  clearanceLevel = INTERNAL

Resource:
  resourceId = report-42
  projectId = ATLAS
  classification = INTERNAL

Action:
  READ

Environment:
  currentTime = 2026-11-23T09:30:00+07:00

Decision:
  ALLOW chỉ khi policy và tất cả điều kiện liên quan đều đạt
~~~

Nếu subject giữ nguyên nhưng resource chuyển sang **projectId = NOVA**, kết quả có thể trở thành **DENY**. Nếu subject chuyển bộ phận hoặc hết hợp đồng, kết quả cũng có thể đổi dù resource và action không đổi. Đây là điểm cốt lõi của ABAC: **quyền dựa vào giá trị hiện hành và mối quan hệ giữa các thuộc tính**, không chỉ một danh sách role tĩnh.

## 3. Các loại subject attribute thường gặp trong IAM

| Thuộc tính | Mục đích | Nguồn có thẩm quyền thường gặp | Rủi ro nếu sai |
| --- | --- | --- | --- |
| **identityId / subjectId** | Xác định chủ thể ổn định | IAM, IdP theo issuer/namespace | Truy cập nhầm danh tính |
| **identityType** | Phân biệt employee, contractor, partner, workload | HRIS, hệ thống bảo trợ, service catalog | Áp chính sách con người cho bot hoặc ngược lại |
| **employmentStatus** | Biết quan hệ làm việc có hiệu lực | HRIS hoặc nguồn bảo trợ | Leaver vẫn được coi ACTIVE |
| **employmentStart / end** | Quy định mốc hiệu lực | HRIS/hợp đồng | Cấp quyền sớm hoặc rút muộn |
| **departmentId / jobCode** | Phân loại vị trí công việc | HRIS | Cấp role nhầm theo phòng ban |
| **organizationMemberships** | Liệt kê tổ chức được duyệt | Nguồn membership có thẩm quyền | Vượt ranh giới tenant |
| **approvedProjects** | Phạm vi dự án được phân công | Hệ thống dự án/chủ tài nguyên | Mover giữ quyền dự án cũ |
| **clearanceLevel** | Mức được phép xử lý dữ liệu | Quy trình phê duyệt bảo mật | Lộ dữ liệu nhạy cảm |
| **employmentCategory** | Employee, vendor, temporary… | HRIS/contractor management | Nhà thầu có quyền nhân viên thường |
| **manager / sponsor** | Owner phê duyệt, rà soát và chịu trách nhiệm | HRIS/nguồn bảo trợ | Tài khoản không có người bảo trợ hợp lệ |
| **privilegedEligibility** | Có đủ điều kiện nhận quyền đặc biệt không | PAM/IGA/phê duyệt | Nâng đặc quyền không được phép |
| **assuranceLevel** | Đánh giá mức xác thực đã đạt khi policy yêu cầu | IdP/verifier và hợp đồng assurance | Bỏ qua MFA/step-up |
| **workloadId / ownerTeam** | Nhận diện service và đội quản lý | Service catalog/cloud IAM | Service account mồ côi |
| **environment / workloadPurpose** | Ràng buộc bot vào dev/staging/prod và chức năng | Hệ thống quản trị workload | Workload dev truy cập production |

Không phải thuộc tính nào cũng nên mang vào mọi token. Một API chỉ cần kiểm tra entitlement của dự án không nhất thiết phải nhận ngày sinh, số điện thoại hoặc toàn bộ hồ sơ nhân sự của người dùng.

## 4. Subject attribute khác role và entitlement

**Role-Based Access Control (RBAC)** thường đưa ra quyết định từ role, còn **ABAC** sử dụng các thuộc tính và điều kiện linh hoạt. Hai mô hình có thể kết hợp, không nhất thiết loại trừ nhau.

| Khái niệm | Ví dụ | Bản chất |
| --- | --- | --- |
| Subject attribute | departmentId = ENG | Thông tin về chủ thể |
| Role | ReportReader | Nhóm quyền theo trách nhiệm |
| Entitlement | READ báo cáo dự án Atlas | Quyền cụ thể tại tài nguyên/hệ thống |
| Resource attribute | report.projectId = ATLAS | Thuộc tính tài nguyên |
| ABAC policy | Chỉ cho READ khi subject thuộc dự án của report | Quy tắc quyết định |

Một role cũng có thể được biểu diễn như **thuộc tính của chủ thể** trong policy engine, nhưng cần giữ rõ vai trò nguồn dữ liệu: role phải xuất phát từ **quyết định cấp quyền**, không được tự suy bằng một chuỗi do người dùng gửi.

### Ví dụ kết hợp RBAC và ABAC

~~~text
ALLOW READ(report) WHEN
    subject.hasRole("ReportReader", report.organizationId)
    AND subject.employmentStatus == ACTIVE
    AND report.projectId IN subject.approvedProjects
    AND subject.clearanceLevel >= report.requiredClearance
    AND noExplicitDenyApplies

OTHERWISE DENY
~~~

So sánh clearance chỉ có ý nghĩa khi tổ chức định nghĩa **thứ bậc bảo mật** rõ ràng. Không dùng phép so sánh chuỗi ký tự theo thứ tự bảng chữ cái để suy ra cấp độ.

**Có role nhưng thiếu điều kiện ABAC phải từ chối.** Ngược lại, một nhân viên đủ department và project nhưng không được duyệt role cần thiết cũng không tự nhận quyền.

## 5. Nguồn nào có thẩm quyền với từng subject attribute?

Một sai lầm phổ biến là coi **IdP là nguồn chuẩn cho mọi thuộc tính** chỉ vì IdP phát hành token SSO. IdP thường là **nơi tập hợp và phân phối** nhiều thuộc tính, không phải nơi phát sinh quyết định nghiệp vụ về mọi trường.

| Subject attribute | Nguồn quyết định | Nơi có thể lưu bản sao |
| --- | --- | --- |
| Employment status/start/end | HRIS hoặc hệ thống bảo trợ được ủy quyền | IAM, IdP, ứng dụng |
| Department, job code | HRIS | Directory, IdP, SCIM User |
| Project assignment | Nguồn quản lý dự án có thẩm quyền | IGA, nhóm IdP, ứng dụng |
| Security clearance | Bộ phận/chủ quy trình phê duyệt bảo mật | IAM/IGA, policy store |
| Approved role | IAM/IGA và resource owner theo workflow | IdP group, SaaS role |
| Authenticator/assurance | IdP hoặc verifier tin cậy | Token assertion và session theo hợp đồng |
| Workload owner/purpose | Service catalog, nền tảng vận hành | Cloud IAM, secret manager |
| Resource ownership | Hệ thống dữ liệu hoặc chủ tài nguyên | Policy Information Point |

**Thẩm quyền là theo từng trường**, không phải thứ hạng chung của hệ thống. Nếu HRIS và SaaS bất đồng về employmentStatus, không mặc định bản ghi cập nhật sau cùng là đúng. Phải ưu tiên **nguồn được ủy quyền, sự kiện hiệu lực và phiên bản**; còn SaaS cho biết trạng thái account hoặc quyền **đang tồn tại**.

## 6. Identity correlation: bảo đảm thuộc tính thuộc đúng người

Ngay cả dữ liệu HR chính xác cũng nguy hiểm nếu IAM liên kết nó với **sai account**. Cần phân biệt:

- **Person:** con người được tổ chức nhận diện.
- **Worker/employment:** quan hệ làm việc cụ thể, có thể nhiều hợp đồng và nhiều giai đoạn.
- **IAM identity:** danh tính số tổng hợp.
- **IdP subject:** định danh của chủ thể trong namespace/issuer của IdP.
- **Application account:** tài khoản cục bộ hoặc liên kết qua provisioning.

Một nhân viên có thể đổi email hoặc username, nhưng identityId và những liên kết đã được xác minh nên ổn định theo mô hình quản trị. **Không dùng riêng email, tên hiển thị hoặc số điện thoại làm khóa ghép dữ liệu**.

Ví dụ, IdP phát hành claim **sub = 482**. Số 482 không tự duy nhất trên mọi nhà cung cấp; cần xét **issuer + subject**. Một account SaaS có id riêng và có thể nhận SCIM **externalId** do client quản lý. IAM cần lưu ánh xạ giữa các ID theo nguồn và tenant.

### Ba trạng thái liên kết

| Trạng thái | Cách xử lý |
| --- | --- |
| **CONFIRMED_MATCH** | Có định danh ổn định hoặc liên kết đã xác minh; được phép đối chiếu attribute |
| **AMBIGUOUS_MATCH** | Nhiều ứng viên hoặc bằng chứng xung đột; không tự cấp quyền dựa trên kết quả |
| **NO_VERIFIED_MATCH** | Chưa có liên kết đáng tin; phải điều tra và tạo/cập nhật mapping an toàn |

**Không tự gộp account chỉ vì email giống nhau**; lỗi này có thể chuyển clearance, role hoặc membership của người này sang người khác.

## 7. Kiểu dữ liệu và ngữ nghĩa subject attribute

Attribute có thể là chuỗi, số, boolean, tập hợp, đối tượng, mốc thời gian hoặc trạng thái. Chính sách phải hiểu **kiểu và ngữ nghĩa chuẩn hóa**.

| Attribute | Kiểu phù hợp | Ví dụ | Vấn đề cần tránh |
| --- | --- | --- | --- |
| employmentStatus | Enum | ACTIVE, TERMINATED | So sánh tùy tiện với các chuỗi active/Active/1 |
| accountEnabled | Boolean | true/false | Nhầm disabled account với không có quan hệ làm việc |
| organizationMemberships | Tập có namespace | [org-a, org-b] | Mất tenant context |
| approvedProjects | Tập ID ổn định | [atlas, nova] | So khớp tên hiển thị |
| clearanceLevel | Enum có thứ bậc | INTERNAL, CONFIDENTIAL | So sánh từ điển thay vì policy order |
| effectiveFrom/Until | Instant + timezone/semantics | ISO 8601 | Nhầm date-only với UTC timestamp |
| departmentId | Chuỗi/mã chuẩn | DEP-FIN-01 | Dùng displayName thay ID |
| workloadPurpose | Enum hoặc catalog ID | report-exporter | Client tự khai giá trị không được kiểm chứng |
| assuranceLevel | Giá trị theo profile IdP | high-assurance | Tự suy từ tên MFA không có hợp đồng |

**Giá trị trống** có nhiều ý nghĩa: chưa biết, chưa đọc được, không áp dụng hoặc thật sự không có quan hệ. Cần phân biệt bằng schema/trạng thái nguồn. Ví dụ **approvedProjects = []** có thể là chủ thể không được duyệt dự án nào; còn **approvedProjects = UNKNOWN** là chưa đủ dữ liệu để kết luận.

Không ép UNKNOWN thành một tập rỗng rồi lặng lẽ ghi là dữ liệu đã xác minh. Khi thiếu thông tin bắt buộc, quyết định truy cập nên được xử lý **không cho phép** theo chính sách, đồng thời có trạng thái lỗi để vận hành sửa nguồn dữ liệu.

## 8. Thời điểm hiệu lực: attribute không chỉ là giá trị hiện tại

Subject attribute có thể thay đổi từ **ngày hiệu lực** khác với thời gian được ghi nhận. Cần phân biệt:

| Thời điểm | Ý nghĩa |
| --- | --- |
| **effectiveAt** | Khi thay đổi có hiệu lực về nghiệp vụ |
| **recordedAt/updatedAt** | Khi nguồn ghi dữ liệu |
| **receivedAt** | Khi IAM hoặc connector nhận sự kiện |
| **evaluatedAt** | Khi PDP đánh giá quyết định |
| **propagatedAt** | Khi bản sao tại IdP/ứng dụng được cập nhật |
| **verifiedAt** | Khi quyền tại target được đọc lại và kiểm chứng |

Ví dụ, HRIS ngày 23/11 ghi quyết định chuyển Lan từ Dự án Atlas sang Nova **có hiệu lực 01/12**. Nếu IAM thu hồi quyền Atlas ngay ngày 23/11, có thể gây **false denial** trước thời điểm công việc đổi. Nếu đến 01/12 mà API vẫn dựa trên quyền Atlas, đó có thể là **residual access**.

Với dữ liệu **endDate** dạng ngày lịch, phải có quy tắc rõ về **ngày cuối còn quyền** và timezone. Không tự biến **2026-11-30** thành một UTC instant nếu HR chưa định nghĩa. Một mẫu:

~~~text
employmentEndDate = 2026-11-30
semantics = "ngày cuối còn hiệu lực"
timezone = "Asia/Ho_Chi_Minh"
accessCutoff = 2026-12-01T00:00:00+07:00
~~~

Đây là **ví dụ chính sách**, không phải ngữ nghĩa cố định của mọi HRIS. Khi có điều kiện khẩn cấp được ủy quyền, thời điểm chặn quyền có thể sớm hơn lịch thông thường.

## 9. Thuộc tính đa giá trị và người có nhiều quan hệ làm việc

Một người có thể đồng thời làm việc cho hai đơn vị hoặc có hợp đồng riêng với nhiều organization. Khi đó, subject attribute **không nên chỉ là một trường department hay organization duy nhất** nếu quyền thực tế phụ thuộc từng quan hệ.

Ví dụ:

~~~json
{
  "identityId": "iam-482",
  "employmentRelations": [
    {
      "employmentId": "emp-org-a-01",
      "organizationId": "org-a",
      "status": "ACTIVE",
      "approvedProjects": ["atlas"]
    },
    {
      "employmentId": "emp-org-b-07",
      "organizationId": "org-b",
      "status": "ACTIVE",
      "approvedProjects": ["nova"]
    }
  ]
}
~~~

Khi quan hệ **org-a** kết thúc, IAM phải thu hồi entitlement và access **xuất phát từ org-a**, trong khi vẫn có thể giữ quyền hợp lệ của **org-b**. Nếu chỉ dùng một thuộc tính **employmentStatus = ACTIVE** ở cấp person rồi cho phép mọi tenant, hệ thống có thể để quyền của org-a tồn dư.

Chính sách nên kiểm tra **quan hệ hợp lệ khớp chính organization và tài nguyên đang được yêu cầu**. Không lấy tập hợp mọi role của các organization rồi áp dụng chung cho tất cả.

## 10. Kiến trúc thu thập và sử dụng subject attribute

Trong kiến trúc kiểm soát truy cập, thường gặp:

- **Policy Information Point (PIP):** cung cấp thuộc tính từ HR, IAM, IdP, project registry hoặc kho quyền.
- **Policy Decision Point (PDP):** dùng thuộc tính và policy để ra quyết định.
- **Policy Enforcement Point (PEP):** chặn hoặc cho request tại API/gateway/service.
- **Policy Administration Point (PAP):** nơi quản lý và phê duyệt chính sách.

~~~mermaid
flowchart TD
    H["HRIS / Sponsor<br/>employment, department, thời hạn"] --> I["IAM/IGA<br/>identity mapping, approvals"]
    J["Project / Organization registry"] --> PIP["PIP<br/>thuộc tính tin cậy"]
    I --> PIP
    IDP["IdP / SSO<br/>subject, authenticator, session"] --> PIP
    W["Workload catalog<br/>serviceId, owner, environment"] --> PIP
    User["User / Workload / OAuth client"] --> API["API / PEP"]
    API --> PDP["PDP<br/>evaluate subject + resource + action + context"]
    PIP --> PDP
    PAP["PAP<br/>versioned policies"] --> PDP
    PDP -->|"ALLOW / DENY / INDETERMINATE"| API
    API --> RES["Resource / data"]
    API --> AUD["Audit & reconciliation"]
    PDP --> AUD
~~~

Thành phần PIP/PDP/PEP có thể nằm cùng một service hoặc tách nhiều service. Yêu cầu quan trọng là **đường gọi thực tế không thể đi vòng PEP**; dữ liệu từ PIP phải có nguồn và độ mới đủ để PDP quyết định.

## 11. Subject attribute xuất hiện ở IdP, SSO và token như thế nào?

**IdP** thường đồng bộ thuộc tính từ HRIS/IAM và phát hành thông tin định danh trong **OIDC ID token**, **UserInfo** hoặc **SAML assertion**. **OAuth access token** có thể mang một số attribute hoặc chỉ mang thông tin tham chiếu để API tra cứu.

Ví dụ claim payload minh họa, **không phải token JWT đã ký**:

~~~json
{
  "iss": "https://login.example.invalid",
  "sub": "idp-subject-482",
  "aud": "https://reports.example.invalid",
  "scope": "reports:read",
  "org_memberships": ["org-a"],
  "subject_type": "employee",
  "department_id": "dep-fin-01",
  "exp": 1796086800
}
~~~

**Các claim org_memberships, subject_type và department_id là claim tùy biến**, không phải các trường OAuth/OIDC bắt buộc. Phải có hợp đồng về issuer, tên trường, kiểu giá trị, nguồn thẩm quyền, audience và thời hạn; không tự tin claim do client gửi trong HTTP body/header.

### ID token không thay access token

**ID token** chứng minh sự kiện xác thực cho client/RP theo giao thức OIDC; nó không được thiết kế để dùng thay access token gọi API. Resource server phải kiểm tra **access token** theo issuer, audience, chữ ký/introspection, hạn, scope và policy. Có scope **reports:read** cũng không tự tạo quyền đọc mọi báo cáo.

**Một claim hiện diện không đủ chứng minh còn mới.** JWT đã phát hành có thể tiếp tục mang employmentStatus, role hoặc department cũ cho tới khi hết hạn. Nếu chính sách yêu cầu thu hồi trước hạn, phải kết hợp **policy recheck, token introspection, denylist, security epoch hoặc TTL** đã được đánh giá.

## 12. Subject attribute trong SCIM provisioning

**SCIM 2.0** thường được dùng để tạo, cập nhật và vô hiệu User/Group giữa IAM/IdP và ứng dụng. Một số subject attributes có thể được ánh xạ vào **core User schema**, ví dụ userName, active, name, emails; một số thuộc tính doanh nghiệp dùng **Enterprise User extension**, ví dụ department, employeeNumber, costCenter hoặc manager.

Ví dụ payload minh họa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "hris-worker-482",
  "userName": "lan@example.invalid",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "E-482",
    "department": "Finance"
  }
}
~~~

Ứng dụng đích có thể **không hỗ trợ mọi thuộc tính** hoặc có mapping riêng. Việc SCIM trả thành công chỉ cho biết nó đã tiếp nhận/áp dụng operation theo contract, **không tự chứng minh token/session và quyết định ABAC hiện tại đều thay đổi**.

Những điểm cần kiểm tra:

1. Attribute đến từ nguồn có thẩm quyền hay chỉ là giá trị copy?
2. **SCIM id** của ứng dụng và **externalId** của provisioning client có được liên kết đúng identity không?
3. Thuộc tính có đúng schema, mutability, uniqueness và kiểu dữ liệu SP hỗ trợ không?
4. Có cần cập nhật policy store hoặc invalidate cache của PDP ngoài SCIM không?
5. Sau Mover/Leaver, có đọc lại **account, group, role và quyền hiệu lực** không?

## 13. Subject attribute và chính sách least privilege

**Least privilege** yêu cầu chỉ cho phép hành động tối thiểu cần thiết. Subject attribute không nên biến thành một nhãn quá rộng như **trustedEmployee = true** để mở mọi tài nguyên.

Một policy tốt phải xét **tập điều kiện cụ thể**:

| Điều kiện | Ví dụ minh họa |
| --- | --- |
| Chủ thể đang có quan hệ hợp lệ | employment status = ACTIVE cho chính quan hệ liên quan |
| Đúng organization | membership thuộc organization của resource |
| Đúng project | subject.approvedProjects chứa resource.projectId |
| Có phê duyệt cho hành động | entitlement READ/EXPORT/APPROVE còn hạn |
| Đủ mức dữ liệu | clearance đạt classification của resource |
| Có xác thực phù hợp | step-up hoặc phishing-resistant MFA nếu chính sách yêu cầu |
| Không có deny ưu tiên | Không có cờ đình chỉ hoặc hạn chế rủi ro đã được phê duyệt |

**Thuộc Finance chưa đủ được xem mọi báo cáo Finance**; vẫn cần kiểm tra chủ sở hữu tài nguyên và cấp quyền. **Có clearance cao chưa đủ được xóa dữ liệu**; action DELETE thường có yêu cầu role/phê duyệt riêng.

Nếu có nhiều đường cấp quyền như group, direct share và role kế thừa, phải tính **effective access** chứ không chỉ xem một thuộc tính của user.

## 14. Chính sách minh họa theo subject attribute

Giả sử một API báo cáo chỉ cho nhân viên đang làm việc và được phân công dự án đọc báo cáo cùng dự án:

~~~text
policy: read-project-report

subject.identityType == EMPLOYEE
AND exists relation IN subject.employmentRelations WHERE
    relation.status == ACTIVE
    AND relation.organizationId == resource.organizationId
    AND resource.projectId IN relation.approvedProjects
    AND relation.effectiveFrom <= now
    AND (relation.effectiveUntil == null OR now < relation.effectiveUntil)
AND action == READ
AND subject.hasEntitlement("REPORT_READ", resource.projectId)
AND resource.status != RESTRICTED
AND noHigherPriorityDeny

=> ALLOW
~~~

Trong chính sách này, **employmentRelations** là mô hình dữ liệu minh họa của tổ chức. Null effectiveUntil chỉ được hiểu là **không có hạn đã biết** nếu nguồn thẩm quyền và policy định nghĩa rõ; trong những trường hợp dữ liệu không hoàn chỉnh, không được tự cho phép vô thời hạn.

### Ma trận ví dụ

| Subject | Resource | Action | Expected | Lý do |
| --- | --- | --- | --- | --- |
| Employee ACTIVE, Atlas approved | Report Atlas cùng organization | READ | ALLOW | Tất cả điều kiện đạt |
| Employee ACTIVE, chỉ Atlas approved | Report Nova | READ | DENY | Sai assignment |
| Employee TERMINATED ở org-a | Report org-a | READ | DENY | Quan hệ hết hiệu lực |
| Employee ACTIVE org-b, đã Leaver org-a | Report org-a | READ | DENY | Không được dùng quan hệ org-b thay org-a |
| Contractor ACTIVE, không thuộc policy employee | Report Atlas | READ | DENY trừ khi policy riêng | Identity type không đạt |
| Employee đủ project nhưng thiếu entitlement | Report Atlas | READ | DENY | Không có phê duyệt thao tác |
| Employee đủ quyền READ | Report Atlas | DELETE | DENY | Hành động không được cấp |

Policy test phải bao gồm các tình huống **DENY** để ngăn truy cập xuyên tenant và sau Leaver.

## 15. Độ mới của thuộc tính và cache

Khi PDP nhận subject attribute từ cache hoặc JWT, cần có quy tắc **freshness**. Chẳng hạn HRIS vừa chấm dứt hợp đồng nhưng cache vẫn ghi ACTIVE; API có thể tiếp tục cấp quyền dù dữ liệu nghiệp vụ đã đổi.

Các giải pháp thường dùng:

- **TTL ngắn** cho thuộc tính có ảnh hưởng lớn đến quyền.
- **Event-driven invalidation** khi nhận Joiner/Mover/Leaver hoặc thu hồi quyền khẩn cấp.
- **Version/epoch** của identity hoặc entitlement để so sánh với trạng thái hiện hành.
- **PIP lookup tại thời điểm request** cho thuộc tính nhạy cảm khi hệ thống và SLA hỗ trợ.
- **Snapshot và reconciliation định kỳ** để phát hiện sự kiện bị mất.
- **Policy cache có kiểm soát** với giới hạn thời gian và phân loại rủi ro.

Không có TTL chung phù hợp mọi hệ thống. TTL 30 phút có thể chấp nhận cho dữ liệu hiển thị ít nhạy cảm nhưng quá dài cho việc chặn đặc quyền sau Leaver khẩn cấp.

### Một ví dụ về thời điểm thực thi

~~~text
businessAccessCutoffAt  = 2026-12-01T00:00:00+07:00
hrEventReceivedAt      = 2026-12-01T00:00:02+07:00
pdpAttributeUpdatedAt  = 2026-12-01T00:00:06+07:00
accessDeniedVerifiedAt = 2026-12-01T00:00:09+07:00
~~~

Đây là dữ liệu giả định: độ trễ xác minh từ mốc cắt là **9 giây** tại API đã kiểm tra. Nó không tự chứng minh mọi SaaS và API khác đều cập nhật cùng thời điểm.

## 16. Dữ liệu không xác định và hành vi fail-closed

Một request phân quyền có thể gặp các trường hợp:

| Tình huống | Cách hiểu | Xử lý an toàn |
| --- | --- | --- |
| employmentStatus = TERMINATED | Đã có thông tin về quan hệ hết hiệu lực | DENY các quyền từ quan hệ đó |
| employmentStatus = UNKNOWN | Chưa có bằng chứng trạng thái | Không tự suy ACTIVE; xử lý theo policy |
| PIP timeout | Không đọc được attribute | Không tự cấp quyền khi thiếu kiểm chứng |
| organizationId mâu thuẫn | Các nguồn hoặc mapping bất đồng | Điều tra, không tự chọn giá trị thuận tiện |
| project list rỗng đã xác minh | Không có project được duyệt | DENY thao tác cần project |
| attribute bị client tự khai | Nguồn không đáng tin | Bỏ qua hoặc chỉ dùng làm tham số yêu cầu, không làm căn cứ quyền |
| policy không tìm thấy | Không có quy tắc cho phép | DENY theo deny-by-default |

**Deny-by-default** nghĩa là thiếu quy tắc cho phép thì không cấp quyền. **Fail-closed** nghĩa là lỗi xác minh bảo mật không biến thành ALLOW. Tuy nhiên lỗi hệ thống có thể cần trả **503** hoặc thông điệp vận hành thay vì giả lập một kết quả 403 hợp lệ. Phải tách **decision = DENY** với **evaluation = INDETERMINATE/ERROR** trong audit.

Với các tác vụ phải duy trì tính sẵn sàng, có thể thiết kế ngoại lệ có điều kiện hoặc cache đáng tin được phê duyệt trước. Không cho phép một đường “PDP lỗi thì ALLOW tất cả” trên API nhạy cảm.

## 17. Bảo vệ subject attribute khỏi giả mạo

Subject attribute là dữ liệu để ra quyết định bảo mật nên phải có **nguồn gốc và tính toàn vẹn**.

Một số tình huống nguy hiểm:

1. Client gửi header **X-Department: Finance** rồi API tin đó là nguồn thật.
2. Browser tự gửi **role = admin** trong JSON request.
3. API decode JWT không xác minh chữ ký, issuer hoặc audience.
4. Một ứng dụng tin claim từ issuer chưa được phê duyệt.
5. Account bị nối sai với worker do email tái sử dụng.
6. Connector SCIM có quyền quá rộng tự ghi department hoặc manager không có phê duyệt.
7. Cache policy nhận một sự kiện cũ và ghi đè thuộc tính mới.

Các biện pháp:

- **Trust boundary:** xác định trường nào do client tự khai, trường nào từ PIP/IdP có thẩm quyền.
- **Cryptographic verification:** xác minh chữ ký, issuer, audience và hạn khi dùng JWT/assertion.
- **Authenticated connectors:** dùng TLS, quyền tối thiểu, credential của connector được quản lý.
- **Schema validation:** kiểm tra kiểu, namespace, giá trị hợp lệ, độ dài và canonicalization.
- **Strong identity correlation:** dùng stable IDs, không khẳng định dựa vào email/name.
- **Version/sequence handling:** chống ghi đè bằng sự kiện cũ.
- **Audit ownership:** mọi thay đổi thuộc tính có actor, căn cứ và phương thức phê duyệt.

Các thuộc tính như **resourceId** hoặc **tenantId** từ URL là *ngữ cảnh yêu cầu* chứ không chứng minh chủ thể có quyền; phải đối chiếu với owner và membership từ nguồn tin cậy.

## 18. Subject attribute và dữ liệu cá nhân

Việc ABAC tận dụng thuộc tính con người không có nghĩa nên phân phối toàn bộ hồ sơ nhân sự tới mọi ứng dụng.

**Nguyên tắc giảm thiểu dữ liệu:**

- Chỉ cung cấp thuộc tính cần thiết để đánh giá policy đã công bố.
- Ưu tiên **ID/nhóm quyền/điều kiện đã được xác minh** thay vì dữ liệu nhân sự chi tiết không cần thiết.
- Không dùng ngày sinh, địa chỉ nhà, dữ liệu sinh trắc hoặc thông tin nhạy cảm làm điều kiện mặc định chỉ vì có trong HRIS.
- Giới hạn bên nhận, audience, thời hạn và phạm vi đồng bộ claim.
- Phân quyền đọc báo cáo audit vì role/department/project assignment có thể là thông tin nhạy cảm.
- Có quy định retention, xóa dữ liệu theo vòng đời và tuân thủ yêu cầu pháp lý áp dụng.
- Không log nguyên token, session cookie, mật khẩu, TOTP seed, private key hoặc recovery code.

Ví dụ, thay vì gửi **địa chỉ cá nhân đầy đủ** tới một API chỉ cần biết chủ thể thuộc organization nào, IAM nên cung cấp **organizationId đã xác minh** hoặc cho PDP truy vấn dữ liệu cần thiết. **Data minimization** vừa giảm nguy cơ rò rỉ vừa đơn giản hóa việc quản lý claim và cache.

## 19. Subject attributes trong Joiner lifecycle

Với **Joiner**, thuộc tính nền tảng đến từ nguồn có thẩm quyền trước khi tạo account hoặc cấp quyền:

1. HRIS hoặc sponsor xác nhận **person, worker/employment ID**, loại quan hệ, ngày bắt đầu, organization và người quản lý.
2. IAM xác minh identity correlation và tạo hoặc liên kết danh tính số.
3. Chuẩn hóa **identityType, employmentStatus, department, jobCode, organization membership** theo schema và authority matrix.
4. IGA hoặc chủ tài nguyên phê duyệt entitlement cần thiết; không suy quyền admin chỉ từ department.
5. IdP/SCIM phân phối đúng thuộc tính tới ứng dụng được phép nhận.
6. PDP/PEP kiểm tra cả **giá trị thuộc tính, thời điểm hiệu lực và quyền trên resource**.
7. Đối soát các cổng: account exists, authentication ready, entitlement active, required allow/deny tests pass.

### Sai lệch Joiner dễ gặp

| Sai lệch | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Account tạo trước ngày bắt đầu, thuộc tính ACTIVE ngay | Truy cập sớm ngoài thời hạn | Effective-time policy và giới hạn kích hoạt |
| Department lấy từ bản nháp HR | Role không đúng | Kiểm chứng source version và approval |
| Mapping person/account nhầm | Rò rỉ quyền người khác | Stable identity correlation |
| App chưa nhận project assignment | False denial | Reconciliation và xử lý provisioning |
| Default role quá rộng | Unauthorized allow | Least privilege và negative tests |

Không đóng Joiner chỉ vì một User đã được tạo qua SCIM. Trạng thái **identity verified**, **technical account ready**, **MFA/SSO ready** và **access verified** có thể là các cổng riêng.

## 20. Subject attributes trong Mover lifecycle

**Mover** thay đổi vai trò, phòng ban, dự án hoặc organization. Đây là lúc subject attributes cũ dễ tạo **privilege accumulation**.

Giả sử Lan rời Dự án Atlas và chuyển sang Nova từ 01/12:

| Thuộc tính | Trước Mover | Sau Mover |
| --- | --- | --- |
| employmentStatus | ACTIVE | ACTIVE |
| departmentId | ENG | ENG |
| approvedProjects | [ATLAS] | [NOVA] |
| role | AtlasReader | NovaReader đã duyệt |
| resource Atlas | Được READ | Phải DENY |
| resource Nova | Chưa READ | Có thể ALLOW sau khi cấp |

Quy trình cần:

1. Đọc sự kiện nguồn **mới nhất** cùng effectiveAt và sourceVersion.
2. Tính lại **expected attributes** và entitlement theo công việc mới.
3. Phân phối thay đổi tới IdP, PIP và ứng dụng; nếu dùng SCIM thì cập nhật User/Group theo contract.
4. Thu hồi direct ACL, role, group hoặc quyền dự án cũ, không chỉ cộng nhóm mới.
5. Đánh giá **JWT claim và cache** còn giữ project cũ; xử lý token/phiên theo yêu cầu thu hồi.
6. Kiểm thử **READ Atlas = DENY**, **READ Nova = ALLOW** khi đủ điều kiện và đọc lại tại đích.

Nếu có giai đoạn bàn giao hợp lệ, quyền Atlas có thể được giữ theo **ngoại lệ được phê duyệt, có hạn và người chịu trách nhiệm**; không để quyền bàn giao trở thành một trạng thái kéo dài vô thời hạn.

## 21. Subject attributes trong Leaver lifecycle

**Leaver** yêu cầu chấm dứt quyền truy cập gắn với quan hệ làm việc đã hết hiệu lực. Thuộc tính quyết định thường là **employmentStatus**, end date, organization membership, assignment và trạng thái phê duyệt.

Nhưng **cập nhật employmentStatus = TERMINATED ở HRIS không tự làm mọi token/phiên mất hiệu lực**. Các lớp cần kiểm tra:

| Lớp | Việc phải kiểm soát | Giới hạn |
| --- | --- | --- |
| HRIS/sponsor | Xác nhận mốc kết thúc quan hệ | Không quản lý mọi phiên ứng dụng |
| IAM/IGA | Tính lại attribute/entitlement mục tiêu | Quyền target có thể cập nhật trễ |
| IdP/SSO | Vô hiệu account hoặc chặn xác thực mới | Session ứng dụng riêng có thể còn |
| SCIM | Deactivate/cập nhật User/Group | Không phải giao thức thu hồi mọi token |
| PDP/PIP | Không tiếp tục dùng trạng thái ACTIVE cũ | Cache/propagation cần được kiểm soát |
| Resource server | Từ chối quyền trên API | JWT offline có thể chứa claim cũ |
| Ứng dụng cục bộ | Thu hồi direct ACL, PAT, session | Không nhất thiết phụ thuộc IdP |
| Workload/service | Chuyển owner, rà soát secret | Không phải mọi bot đều phải bị xóa khi owner nghỉ |

**Kiểm chứng hoàn tất** cần dựa trên quyền hiệu lực tại target, thời điểm truy cập bị chặn và bằng chứng trạng thái từng hệ thống. Nếu một API chưa thể kiểm chứng, giữ mục đó ở trạng thái **PARTIAL/UNVERIFIED**, không coi toàn bộ Leaver thành công.

## 22. Workload identity: subject attribute không chỉ dành cho con người

Với **service account** hoặc **workload identity**, nhiều thuộc tính HR không phù hợp. Thay vào đó, subject attributes có thể gồm:

| Thuộc tính workload | Ý nghĩa |
| --- | --- |
| serviceId / workloadId | Định danh dịch vụ ổn định |
| ownerTeam | Đội chịu trách nhiệm |
| environment | dev, staging, production |
| applicationId | Ứng dụng sở hữu workload |
| deploymentIdentity | Danh tính workload trong nền tảng chạy |
| allowedResources | Danh sách/phạm vi tài nguyên đã duyệt |
| permittedActions | READ, WRITE hoặc thao tác API cụ thể |
| credentialType / assurance | Loại credential hoặc cơ chế xác thực máy |
| lifecycleStatus | ACTIVE, SUSPENDED, DECOMMISSIONED |
| expiryAt | Thời hạn grant, assignment hoặc credential |

Ví dụ chính sách cho một bot xuất báo cáo:

~~~text
ALLOW EXPORT(report) IF
    subject.identityType == WORKLOAD
    AND subject.serviceId == "report-exporter"
    AND subject.environment == PRODUCTION
    AND subject.lifecycleStatus == ACTIVE
    AND subject.ownerTeam IS VERIFIED
    AND resource.organizationId IN subject.allowedOrganizations
    AND action IN subject.permittedActions
    AND token.audience == expectedResourceServer
    AND noExplicitDeny
~~~

Workload không nên phải nhờ nhân viên bấm **MFA push** mỗi lần gọi API. Nên dùng cơ chế phù hợp như **workload identity federation, managed identity, khóa riêng/certificate hoặc token ngắn hạn**, kết hợp scope/role tối thiểu.

Khi người phụ trách workload **Mover/Leaver**, cần **chuyển owner**, rà soát quyền và các secret cá nhân mà người đó có thể đã biết. Không tự tắt bot sản xuất còn nhiệm vụ hợp lệ, nhưng cũng không để account máy **không còn owner** tiếp tục tồn tại vô hạn.

## 23. Authorization ở API: không tin subject attribute do client tự khai

Ví dụ một request tới Reports API:

~~~http
GET /organizations/org-b/reports/42 HTTP/1.1
Host: reports.example.invalid
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
X-Department: Finance
~~~

API **không được dùng X-Department** như bằng chứng người gọi thuộc phòng Finance. Header này có thể do client tự đặt. Tương tự, **org-b** trong URL chỉ là tài nguyên được yêu cầu, không chứng minh membership org-b.

Trình tự kiểm tra:

1. Xác minh token/phiên đúng **issuer, audience, chữ ký/introspection, thời hạn và điều kiện thu hồi**.
2. Xác định stable **subject identity** từ nguồn tin cậy.
3. Kiểm tra **scope của token** nếu API dùng OAuth.
4. Truy vấn/đọc subject attributes từ nguồn đã được phê duyệt, có kiểm soát version/freshness.
5. Đọc **resource attributes** từ backend, bao gồm owner/tenant/project thực sự.
6. PDP đánh giá policy theo subject, resource, action và context.
7. PEP thực thi **DENY** hoặc **ALLOW** đúng quyết định; không chỉ ẩn nút giao diện.
8. Ghi log quyết định mà không lưu credential.

Việc API trả 403 khi thiếu quyền có thể là **từ chối đúng**, không phải lỗi cần cấp admin để giải quyết. Nếu token hợp lệ nhưng subject thiếu entitlement, không tự cho phép chỉ vì người đó đã SSO/MFA thành công.

## 24. Ví dụ mã giả triển khai policy và kiểm tra freshness

~~~text
authorize(request, verifiedSession):
    identity = requireTrustedSubject(verifiedSession)
    token = validateAccessTokenIfApplicable(
        verifiedSession,
        expectedIssuer,
        expectedAudience
    )

    resource = loadResourceFromTrustedStore(request.resourceId)
    action = mapRequestToAction(request)

    snapshot = subjectAttributeProvider.lookup(
        identity.id,
        resource.organizationId,
        currentPolicyVersion
    )

    if snapshot.unverified or snapshot.isStale or snapshot.isIncomplete:
        audit("ATTRIBUTE_UNAVAILABLE_OR_STALE")
        return DENY_OR_CONTROLLED_ERROR

    if not snapshot.hasCurrentAuthorizedRelation(resource.organizationId):
        return DENY

    decision = policyEngine.evaluate(
        subject = snapshot.attributes,
        resource = resource.attributes,
        action = action,
        environment = trustedContext(request)
    )

    if decision != ALLOW:
        auditDecision(decision)
        return DENY_OR_CONTROLLED_ERROR

    return ALLOW
~~~

Điểm quan trọng là **snapshot phải gắn với đúng chủ thể, tổ chức và phiên bản**. Nếu một worker dùng sự kiện HR cũ ghi đè dữ liệu mới, snapshot có thể trông hợp lệ về schema nhưng sai về quyền. Do đó, cần cơ chế chống sự kiện trùng, đến trễ và xử lý bất đồng bộ.

Không phải mọi hệ thống phải gọi HRIS trực tiếp trên mỗi request. Có thể sử dụng PIP/cache được quản trị và cập nhật theo sự kiện, với độ trễ/TTL được đánh giá theo mức nhạy cảm của tài nguyên.

## 25. Account reconciliation cho subject attribute

Một lần đối soát nên so sánh **expected subject attributes** từ nguồn có thẩm quyền với **observed attributes/permissions** ở IdP, policy store và ứng dụng, rồi kiểm tra quyền thực tế.

| Đối tượng so sánh | Expected | Observed | Hành động khi khác nhau |
| --- | --- | --- | --- |
| employmentStatus | ACTIVE/TERMINATED theo HR | Bản sao IdP/PIP | Cập nhật có version; xem quyền hiện hữu |
| departmentId | Mã department từ HR | Claim/SCIM app | Sửa mapping, kiểm tra policy |
| organization memberships | Tập quan hệ đang hợp lệ | User/group/tenant membership | Thu hồi hoặc cấp theo đúng quan hệ |
| approvedProjects | Assignment mới nhất | Project membership và token claims | Bỏ quyền cũ, thêm quyền mới |
| clearanceLevel | Approval của bộ phận có thẩm quyền | Policy store | Chặn quyền khi thiếu chứng cứ |
| assuranceLevel | Kết quả xác thực của IdP | Assertion/session được RP tin cậy | Step-up hoặc từ chối |
| workload owner | Service catalog | IAM/cloud/secret manager | Chuyển owner hoặc mở ngoại lệ |
| effective access | Quyết định policy hiện hành | ALLOW/DENY thật ở API | Khắc phục lỗi PDP/PEP/cache |

Nếu connector không thể đọc attribute vì thiếu quyền hoặc timeout, giá trị nên là **UNKNOWN**, không được suy là khớp. Với account chưa liên kết identity, cần điều tra trước khi tự động cấp hay thu hồi trên một người có email giống nhau.

### Điều gì là bằng chứng hoàn tất?

- Nguồn thẩm quyền và ID đã được xác minh.
- Giá trị attribute, version và thời điểm hiệu lực phù hợp.
- Target nhận và lưu dữ liệu mong muốn.
- PDP/PEP đã dùng dữ liệu đủ mới.
- **Effective access** kiểm thử cho các trường hợp ALLOW/DENY thiết yếu.
- Ngoại lệ còn mở có owner, mức rủi ro và deadline.

## 26. Kiểm thử subject attribute

Một tập kiểm thử tốt cần có cả đường cho phép và từ chối. Ví dụ:

| Case | Điều kiện | Expected |
| --- | --- | --- |
| T01 | Employee ACTIVE, đúng organization, project và entitlement | ALLOW READ tài nguyên được duyệt |
| T02 | Employee ACTIVE nhưng project không khớp | DENY |
| T03 | Employee TERMINATED | DENY quyền của quan hệ đã kết thúc |
| T04 | Employee còn org-b nhưng Leaver org-a | DENY org-a, giữ quyền org-b khi đủ điều kiện |
| T05 | Department source chưa được xác minh | Không ALLOW theo thuộc tính không tin cậy |
| T06 | Client tự gửi header role/admin | Không nâng quyền |
| T07 | JWT có department cũ sau Mover | Không cho vượt yêu cầu freshness |
| T08 | PIP timeout | Không tự ALLOW |
| T09 | Subject có role phù hợp nhưng sai tenant | DENY |
| T10 | Workload dev gọi resource prod | DENY |
| T11 | Workload prod đủ scope nhưng không có owner | Theo policy: chặn/giới hạn, mở remediation |
| T12 | Rehire có identity cũ nhưng employment mới | Không tự phục hồi role/grant cũ |
| T13 | Date-only end date qua ranh giới timezone | Chuyển đúng từ ngày cuối quyền sang cutoff |
| T14 | Group SCIM đã cập nhật nhưng ACL trực tiếp còn | Phát hiện quyền tồn dư qua effective access |

**Policy unit test** chỉ kiểm tra logic trên dữ liệu giả lập. Cần thêm **integration test tại API/PEP**, vì một policy đúng vẫn có thể bị bypass khi endpoint quên gọi PDP hoặc dùng cache ngoài quy tắc.

## 27. Kiểm toán và chỉ số vận hành

Một quyết định ABAC nên có dấu vết **subject → source attributes → policy version → resource/action → decision → enforcement**, đồng thời bảo vệ dữ liệu cá nhân.

Ví dụ JSON audit metadata:

~~~json
{
  "eventId": "abac-decision-2026-081",
  "correlationId": "api-request-1042",
  "identityRef": "iam-482",
  "identityType": "EMPLOYEE",
  "sourceVersion": "hris-120",
  "subjectAttributesVersion": "attrs-241",
  "subjectAttributeFreshness": "VALID",
  "targetOrganization": "org-a",
  "resourceRef": "org-a/report-42",
  "action": "READ",
  "policyId": "report-read-v7",
  "decision": "DENY",
  "reasonCode": "PROJECT_MEMBERSHIP_MISSING",
  "enforcement": "BLOCKED",
  "occurredAt": "2026-11-23T09:30:00+07:00"
}
~~~

**Không ghi nguyên access token hoặc toàn bộ hồ sơ HR** trong log. Ghi tham chiếu ổn định, phiên bản thuộc tính, lý do từ chối ở mức an toàn và bằng chứng PEP đã thực thi. Tránh tiết lộ danh sách project hoặc role của người khác qua thông báo lỗi công khai.

| Chỉ số | Giá trị vận hành |
| --- | --- |
| Attribute freshness lag | Độ trễ từ thay đổi nguồn đến lúc PDP sử dụng giá trị mới |
| Unverified subject mapping | Số account không có identity correlation chắc chắn |
| Missing/unknown critical attributes | Số request không đủ dữ liệu để quyết định |
| Mover stale assignments | Quyền dự án/phòng ban cũ còn tồn tại |
| Leaver residual access | Quyền tại API còn ALLOW sau mốc cắt |
| Policy enforcement coverage | Tỷ lệ endpoint/operation có kiểm tra quyền |
| Cross-tenant denial tests | Bằng chứng cô lập organization/tenant |
| Time to verified remediation | Thời gian từ sai lệch tới khi target xác minh |
| Ownerless workload identities | Workload không có chủ thể chịu trách nhiệm |

Không có một SLA chung phù hợp mọi tổ chức. Các chỉ số cần phân tách theo **độ nhạy tài nguyên, loại chủ thể và mức đặc quyền**, tránh tỷ lệ trung bình che giấu vài đường truy cập nguy hiểm.

## 28. Tình huống thực hành: đổi dự án, thuộc tính chưa cập nhật

**Bối cảnh:** Nhân viên Minh là Analyst tại Dự án Atlas. Ngày **01/12/2026 09:00 +07:00**, hệ thống dự án có thẩm quyền chuyển Minh sang Nova. IAM đã tiếp nhận sự kiện, nhưng JWT access token phát hành lúc **08:50** vẫn mang claim cũ **approvedProjects = [Atlas]** cho đến hạn lúc **09:20**. Reports API xác thực JWT offline và chỉ đọc claim ấy.

**Vấn đề:** Sau 09:00, API có thể vẫn cho Minh đọc báo cáo Atlas, dù quyết định nghiệp vụ đã thu hồi quyền. Đây là **quyền tồn dư do subject attribute trong token đã cũ**, nếu policy yêu cầu thu hồi hiệu lực ngay hoặc trong một SLA ngắn hơn.

### Phân tích

1. Xác định đúng Minh từ **issuer + subject** và identity correlation; không suy từ email.
2. Đối chiếu sự kiện Mover từ nguồn dự án với **effectiveAt** và sourceVersion.
3. Kiểm tra IGA đã tính expected access: **Atlas DENY, Nova ALLOW khi đủ entitlement**.
4. Kiểm tra PIP/cache và JWT claim; chỉ thay group ở IdP có thể chưa làm token cũ mất hiệu lực.
5. Kiểm tra resource server có **policy recheck, introspection, denylist, epoch hoặc TTL** theo rủi ro không.
6. Đối soát ACL trực tiếp, role cục bộ và những đường quyền khác ở SaaS.
7. Kiểm thử tại API: **READ Atlas = DENY**; **READ Nova = ALLOW** khi đã có role/scope đúng; **DELETE cả hai = DENY** nếu role chỉ đọc.

### Những câu hỏi tự kiểm tra

**Câu 1:** Có role Analyst thì có mặc nhiên xem mọi báo cáo không?

**Trả lời:** Không. Subject attribute và policy phải xét project/organization, quyền cụ thể và resource attributes.

**Câu 2:** HRIS là nguồn chuẩn của mọi attribute trong ABAC?

**Trả lời:** Không. HRIS có thẩm quyền với dữ liệu lao động được chỉ định; project registry, IGA, IdP và service catalog có thể có thẩm quyền với các trường khác.

**Câu 3:** Thay đổi department trong IdP có tự làm JWT cũ đổi claim không?

**Trả lời:** Không. JWT đã phát hành có thể giữ claim cũ cho tới hạn, trừ khi resource server có biện pháp đánh giá lại hoặc thu hồi phù hợp.

**Câu 4:** Người nghỉ việc ở org-a nhưng còn hợp đồng hợp lệ tại org-b có bị khóa toàn bộ không?

**Trả lời:** Không nhất thiết. Phải tính lại entitlement theo từng quan hệ, không dùng một trạng thái person cấp chung để bỏ qua ranh giới organization.

**Câu 5:** API nhận header department từ browser có thể dùng ngay để cấp quyền không?

**Trả lời:** Không. Đó là dữ liệu client tự khai, phải lấy attribute bảo mật từ nguồn đã được xác minh.

## 29. Checklist thiết kế subject attribute trong ABAC

| Câu hỏi | Yêu cầu kiểm chứng |
| --- | --- |
| Subject là người dùng, đối tác hay workload? | identityType, namespace và nguồn liên kết đúng |
| Có stable identity mapping? | person/employment/identity/account không ghép bằng email đơn thuần |
| Mỗi attribute có nguồn có thẩm quyền? | Authority matrix, owner và hợp đồng schema |
| Kiểu dữ liệu/ngữ nghĩa rõ ràng? | Enum, boolean, set, instant, null/unknown được phân biệt |
| Đã định nghĩa ngày hiệu lực và timezone? | effectiveAt, cutoff, source version |
| Có hỗ trợ nhiều employment/tenant? | Không trộn role/clearance giữa các quan hệ |
| Có dùng tối thiểu dữ liệu cá nhân? | Không phát tán hồ sơ HR ngoài nhu cầu |
| Claim/tokens có được kiểm chứng? | iss, aud, signature/introspection, exp và contract |
| Có giới hạn tuổi dữ liệu subject attribute? | TTL, invalidation, PIP freshness, epoch |
| Không tin attribute do client tự khai? | Backend/PDP dùng nguồn đáng tin |
| Có chính sách deny-by-default/fail-closed? | Không ALLOW khi missing hoặc PIP lỗi |
| Có kết hợp RBAC/ABAC đúng? | Role, entitlement, subject/resource/action/context |
| Joiner có cấp đúng dữ liệu và quyền? | Identity proofing, HR effective date, readback |
| Mover có thu hồi assignment cũ? | Token/cache và ACL cũ được đánh giá lại |
| Leaver có chặn quyền hiệu lực? | IdP, SCIM, API, PAT, session, token và audit |
| Workload có owner và policy riêng? | serviceId, environment, action, scope, expiry |
| Có positive/negative policy test? | Cross-tenant, stale claim, unknown và fail-closed |
| Có bằng chứng quyết định và thực thi? | Source/version, policy, PEP result, exception owner |

## 30. Tổng kết

**Subject attribute** là những đặc điểm được dùng để mô tả **chủ thể đang yêu cầu quyền truy cập** trong mô hình **ABAC**. Giá trị này có thể phản ánh quan hệ lao động, organization, department, assignment, clearance, vai trò đã được duyệt, mức xác thực hoặc danh tính workload. **Attribute không tự là quyền**: PDP phải kết hợp nó với resource attributes, hành động, ngữ cảnh và policy, còn PEP phải thực thi quyết định ở đường truy cập thật.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** quyết định nhiều thuộc tính nhân sự; **IAM/IGA** liên kết danh tính và quản trị entitlement; **IdP/SSO** phân phối thông tin xác thực; **SCIM** hỗ trợ đồng bộ User/Group; **RBAC/ABAC** kết hợp vai trò và điều kiện; **resource server** kiểm tra quyền hiệu lực; còn **service/workload identity** có thuộc tính và vòng đời riêng. Để giảm **quyền truy cập tồn dư**, tổ chức cần bảo đảm subject attributes **đúng chủ thể, đúng nguồn, đúng phiên bản, đúng mốc hiệu lực, đủ mới và được kiểm chứng tại API**, đồng thời quản lý trường hợp thiếu dữ liệu, đối soát các hệ thống đích và lưu dấu vết kiểm toán.
