# Policy repository trong PBAC: quản trị chính sách phân quyền có phiên bản, kiểm chứng và triển khai an toàn

**Policy repository (kho lưu trữ chính sách)** là nơi quản lý **định nghĩa, phiên bản, siêu dữ liệu và vòng đời thay đổi** của các chính sách kiểm soát truy cập trong hệ thống **Policy-Based Access Control (PBAC)**. Thay vì để mỗi ứng dụng tự viết những điều kiện khó kiểm tra trong nhiều đoạn mã khác nhau, tổ chức đưa những quy tắc quan trọng vào các **policy được quản trị**, có người chịu trách nhiệm, quy trình phê duyệt, kiểm thử, phát hành và kiểm toán.

Một **policy repository không tự động là bộ máy ra quyết định**. Nó lưu hoặc phân phối *quy tắc*; các thành phần như **Policy Decision Point (PDP)** đánh giá quy tắc với **subject, action, resource, context** cụ thể, còn **Policy Enforcement Point (PEP)** thực thi quyết định. Tương tự, **repository không thay thế Identity Provider (IdP), SSO, SCIM, RBAC/ABAC hoặc hệ thống nhân sự**: các thành phần đó cung cấp danh tính, trạng thái tài khoản, thuộc tính, quyền đã cấp và kết quả xác thực để policy được đánh giá đúng.

Bài thuộc chương **PBAC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung bám sát quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo account và cấp quyền đến cập nhật vai trò, rà soát và thu hồi. **Điểm mấu chốt:** *Policy được lưu đúng* chưa có nghĩa *quyền đang được thực thi đúng*. Cần chứng minh **phiên bản chính sách nào đang hoạt động, dữ liệu nào được sử dụng khi đánh giá và quyền hiệu dụng tại ứng dụng đã hội tụ** để tránh quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **policy repository** trong PBAC và phân biệt nó với **PAP, PDP, PEP, PIP, IAM/IGA và directory/IdP**.
2. Thiết kế cấu trúc policy có **định danh, owner, phiên bản, phạm vi, trạng thái, hiệu lực, quy tắc và bằng chứng phê duyệt**.
3. Phân biệt **source repository**, **published policy artifact**, **runtime policy store/cache** và **policy decision log**.
4. Mô tả pipeline **soạn thảo → review → kiểm thử → phê duyệt → phát hành → phân phối → readback**.
5. Đánh giá phương án quản lý policy theo **GitOps/Policy-as-Code** hoặc kho chính sách được quản lý tập trung.
6. Xây test **PERMIT/DENY**, tenant isolation, SoD, exception, thiếu thuộc tính và dữ liệu lỗi thời trước khi phát hành.
7. Xử lý **policy drift, eventual consistency, cache, rollback và degraded mode** mà không vô tình mở rộng quyền.
8. Liên kết policy repository với **Joiner–Mover–Leaver, IdP/SSO/SCIM, RBAC/ABAC, workload và service account**, cùng kiểm toán quyền tồn dư.

## 2. PBAC và policy repository: bài toán cần giải quyết

Trong PBAC, quyền truy cập được quyết định bằng **chính sách** mô tả điều kiện nào khiến một chủ thể có thể thực hiện một hành động trên tài nguyên. Policy có thể dùng **role (RBAC)**, **thuộc tính (ABAC)**, quan hệ với tài nguyên, mức xác thực, phân tách nhiệm vụ và những kiểm soát bổ sung.

Ví dụ nghiệp vụ:

> Chỉ nhân viên Finance **đang có engagement hợp lệ**, được giao dự án của hóa đơn, có role `invoice_reader` và thuộc đúng tenant mới được đọc hóa đơn; yêu cầu xuất dữ liệu cần quyền riêng và mức xác thực thích hợp.

Nếu quy tắc này được sao chép bằng tay vào 12 service, các service có thể khác nhau về điều kiện, tên role, hạn hợp đồng hoặc kiểm tra tenant. Thay đổi chính sách sẽ khó kiểm chứng, dễ để sót một API.

**Policy repository** giải quyết những nhu cầu:

- **Tập trung quản lý định nghĩa:** Mỗi policy có ID, scope, owner và phiên bản rõ.
- **Tái sử dụng có kiểm soát:** Cùng một quy tắc/khái niệm được triển khai nhất quán tại những PEP/PDP phù hợp.
- **Kiểm soát thay đổi:** Biết ai đề xuất, ai duyệt, khi nào có hiệu lực và vì sao.
- **Kiểm thử trước triển khai:** Có thể đánh giá các trường hợp được phép/từ chối.
- **Phân phối và đối soát:** Kiểm tra các PDP đã nhận đúng policy chưa.
- **Kiểm toán:** Truy từ quyết định truy cập về **phiên bản chính sách thực sự áp dụng**.
- **Phục hồi:** Có thể quay lại phiên bản an toàn có căn cứ khi một bản phát hành lỗi.

**Không nhầm:** Đưa tất cả policy vào một file lớn không tự mang lại tính nhất quán. Phải có **ranh giới sở hữu, kiểu dữ liệu, quy tắc kết hợp, kiểm thử và quy trình phát hành** phù hợp.

## 3. Phân biệt các thành phần của kiến trúc PBAC

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Policy repository** | Lưu nguồn policy, siêu dữ liệu, phiên bản và lịch sử thay đổi | Kho policy theo ứng dụng/domain |
| **PAP – Policy Administration Point** | Quản trị soạn thảo, phê duyệt, công bố và vòng đời policy | Workflow review và release |
| **PDP – Policy Decision Point** | Đánh giá policy với dữ liệu request/attribute | Engine trả PERMIT hoặc DENY |
| **PEP – Policy Enforcement Point** | Chặn hành động và thực thi kết quả PDP | API middleware, gateway |
| **PIP – Policy Information Point** | Cung cấp thuộc tính/quan hệ cần cho quyết định | IAM, HR/VMS, resource metadata |
| **Identity source / IdP** | Xác định chủ thể, trạng thái và kết quả authentication | HR, directory, IdP/SSO |
| **Provisioning / SCIM** | Tạo/cập nhật/vô hiệu hóa account/group ở hệ thống đích | SCIM connector, API |
| **Audit / monitoring** | Lưu quyết định và trạng thái triển khai, cảnh báo drift | Policy deployment log, decision log |

### 3.1. Luồng từ định nghĩa chính sách đến quyết định truy cập

~~~mermaid
flowchart TD
    A["Business & Security Owner<br/>định nghĩa yêu cầu"] --> PAP["PAP / Change workflow<br/>Review và phê duyệt"]
    PAP --> REPO["Policy repository<br/>Source + metadata + version"]
    REPO --> CI["Validation / Tests<br/>Build + ký artifact nếu áp dụng"]
    CI --> PUB["Published policy artifact<br/>Được phê duyệt"]
    PUB --> PDP["PDP / Runtime policy store<br/>Phiên bản đang thực thi"]
    HR["HR/VMS, IAM/IGA, IdP/SSO<br/>Trạng thái subject"] --> PIP["PIP / Trusted attributes"]
    RES["Resource data<br/>Owner, tenant, classification"] --> PIP
    APP["Request tới API"] --> PEP["PEP: xác thực token<br/>và chặn thao tác"]
    PEP --> PDP
    PIP --> PDP
    PDP -->|"PERMIT/DENY + nghĩa vụ"| PEP
    PEP --> TARGET["Tài nguyên ứng dụng"]
    PDP --> AUD["Decision audit<br/>Policy version + data freshness"]
    PUB --> AUD
    TARGET --> AUD
~~~

**Sơ đồ thể hiện trách nhiệm logic**, không khẳng định mọi nền tảng phải triển khai thành tám dịch vụ riêng. Với ứng dụng nhỏ, PDP có thể là thư viện trong service; với môi trường lớn, PDP có thể dùng dịch vụ tập trung hoặc engine sidecar. Dù topology khác nhau, trách nhiệm **nguồn policy**, **quyết định** và **thực thi** cần rõ ràng.

### 3.2. Repository khác PDP

Một bản policy đã được merge vào Git hoặc lưu trong PAP **chưa chắc đã được tất cả PDP tải**. Khi worker mới rời tổ chức, repository có thể vẫn nguyên vì **policy điều kiện “engagement phải active” không đổi**, nhưng dữ liệu engagement tại PIP thay đổi. Vì vậy cần kiểm cả **policy version** lẫn **trạng thái subject ở thời điểm quyết định**.

## 4. Bốn lớp dữ liệu thường bị gọi chung là “policy store”

Để tránh nhầm, tách:

| Lớp | Lưu gì? | Nguồn đúng cần xác minh |
|---|---|---|
| **Source repository** | Policy source, metadata, test, change history | Commit/version và phê duyệt |
| **Build/published artifact** | Gói policy đã kiểm tra, ví dụ bundle hoặc ruleset | Artifact ID, digest/signature khi áp dụng |
| **Runtime policy store/cache** | Bản policy PDP thực sự đang nạp | Runtime version, activation time, health |
| **Decision/audit store** | Kết quả đánh giá, subject/action/resource tham chiếu và policy version | Log bảo vệ toàn vẹn, thời gian, correlation ID |

**Ví dụ sự cố:** Commit `v12` đã được phê duyệt; package `v12` được xuất bản; một PDP ở site B vẫn chạy `v11` do mất kết nối. Báo cáo “policy đã cập nhật trên Git” là đúng nhưng **không chứng minh mọi API đã áp chính sách mới**.

### 4.1. Repository không phải kho credential

Không lưu mật khẩu người dùng, private signing key, client secret, refresh token hoặc API key nguyên văn trong policy repository để các PEP/PDP đọc chung. Policy có thể **tham chiếu tên secret hoặc identity của service** khi thật sự cần, nhưng credential phải được quản lý tại vault/secret manager phù hợp, có quyền truy cập và rotation riêng.

## 5. Một policy có những thành phần nào?

Không có một schema chung cho mọi sản phẩm PBAC. Tuy nhiên, về mặt quản trị, một policy thường cần:

| Thành phần | Ý nghĩa | Câu hỏi kiểm soát |
|---|---|---|
| **Policy ID** | Định danh ổn định của quy tắc | Có trùng hoặc thay tên tùy tiện không? |
| **Tên/mô tả** | Nghiệp vụ đang bảo vệ | Người phê duyệt hiểu chính sách không? |
| **Owner** | Người/đơn vị có thẩm quyền nghiệp vụ | Khi owner Leaver, ai nhận trách nhiệm? |
| **Domain/scope** | API, tenant, môi trường, loại tài nguyên | Có mở rộng quá phạm vi không? |
| **Subject conditions** | Loại account, trạng thái, role/attribute | Thuộc tính lấy từ nguồn nào? |
| **Action** | Hành động cần bảo vệ | Có phân biệt read/export/approve/admin? |
| **Resource conditions** | Tenant, project, owner, classification | Có chống truy cập chéo đối tượng? |
| **Context conditions** | MFA, thời gian, thiết bị, rủi ro | Nếu thiếu dữ liệu xử lý thế nào? |
| **Effect** | PERMIT/DENY hoặc kết quả khác theo engine | Quy tắc kết hợp có rõ không? |
| **Priority/combining** | Giải quyết nhiều policy cùng áp dụng | Deny có ghi đè Permit trong phạm vi nào? |
| **Version** | Bản logic cụ thể | Quyết định nào dùng bản nào? |
| **Effective window** | Thời điểm có hiệu lực/hết hiệu lực | Có policy cũ nào còn active? |
| **Change approval** | Người duyệt, ticket, reason | Có SoD trong quy trình thay đổi? |
| **Test/evidence** | Các trường hợp allow/deny được xác nhận | Kiểm thử tenant, JML, edge cases? |

### 5.1. Ba loại “phiên bản” nên theo dõi

1. **Source version:** Commit hoặc bản ghi nguồn ở repository.
2. **Released artifact version:** Gói đã build, test, duyệt và công bố.
3. **Runtime version:** Bản đang được PDP thực thi tại thời điểm request.

Một quyết định audit tốt cần cho biết **runtime version**, vì nó là thứ đã thực sự ảnh hưởng tới kết quả.

## 6. Ví dụ một policy document có metadata

Đây là **mẫu YAML minh họa về cấu trúc quản trị**, không phải schema chuẩn của một engine bất kỳ:

~~~yaml
policyId: finance.invoice.read.v1
domain: finance
title: Read invoice within authorized project
owner: finance-data-owner
technicalOwner: identity-platform-team
version: 1.3.0
status: APPROVED
environment: production
target:
  resourceType: invoice
  action: invoice.read
  tenantScope: tenant-isolated
effectiveFrom: "2026-12-01T00:00:00Z"
decision:
  defaultEffect: DENY
  combiningAlgorithm: DENY_OVERRIDES
  permitWhen:
    - subject.kind == HUMAN
    - subject.accountStatus == ACTIVE
    - subject.engagementStatus == ACTIVE
    - role(subject, finance_invoice_reader)
    - subject.tenantId == resource.tenantId
    - resource.projectId in subject.authorizedProjectIds
    - context.authenticationAssuranceOk == true
security:
  attributeSources:
    accountStatus: iam-authoritative
    engagementStatus: hr-vms-authoritative
    projectMembership: project-access-service
    tenantId: verified-identity-and-resource
  onMissingRequiredAttribute: DENY
  maxAttributeAge: configured-by-policy
approval:
  changeId: IAM-POL-2026-121
  businessReviewed: true
  securityReviewed: true
  testsPassed: true
~~~

**Chú ý:** Chuỗi điều kiện dưới `permitWhen` là ký hiệu mô tả, không phải ngôn ngữ biểu thức đã được parser xác nhận. Một implementation thật phải dùng đúng **language, type system, schema và validation** của engine (ví dụ policy DSL/Policy-as-Code), có ranh giới nguồn dữ liệu rõ.

### 6.1. Các thành phần nào cần nằm ngoài policy?

Thông thường không nên nhúng:

- Danh sách hàng triệu user đang active: trạng thái này thuộc **nguồn identity/HR/IAM/PIP**, được cập nhật liên tục.
- Toàn bộ phiên hoặc token đã cấp: thuộc **session/token service**.
- Secret của client hay signing key: thuộc **vault/HSM/secret manager**.
- Dữ liệu nghiệp vụ thô ngoài phạm vi cần ra quyết định: thuộc **resource service** có kiểm soát.
- Quyết định cấp quyền từng người không có hạn và nguồn: thuộc **grant/assignment lifecycle**, cần audit.

Policy nên mô tả **quy tắc**, còn các nguồn PIP và identity quản lý **dữ liệu áp quy tắc**. Có thể có policy chứa bảng tĩnh nhỏ khi phù hợp, nhưng phải xác định ai cập nhật và mốc hiệu lực.

## 7. Quy tắc kết hợp policy: DENY, PERMIT và xung đột

Một ứng dụng có thể chịu nhiều policy:

- Policy cơ bản: Chỉ subject có engagement hợp lệ.
- Policy tenant: Không được truy cập dữ liệu tenant khác.
- Policy vai trò: Finance Reader có quyền đọc hóa đơn.
- Policy dữ liệu: Không xuất dữ liệu classified nếu chưa được duyệt.
- Policy khẩn cấp: Tạm chặn tài khoản có dấu hiệu bị chiếm quyền.

Nếu một policy cho **PERMIT** và policy khác yêu cầu **DENY**, hệ thống cần có **combining semantics** đã xác định. Những mô hình thông dụng gồm **deny-overrides**, **permit-overrides**, thứ tự ưu tiên hoặc logic đặc thù engine. Không có cấu hình áp dụng chung cho mọi tình huống.

### 7.1. Nguyên tắc deny-by-default

Với API nhạy cảm, thường nên **từ chối khi không có quy tắc cho phép hợp lệ**. Điều này giảm nguy cơ một endpoint mới vô tình mở toàn bộ dữ liệu.

~~~text
Input:
  subject, action, resource, context

If authentication/token validation invalid:
  -> DENY / UNAUTHENTICATED

If subject/engagement not eligible:
  -> DENY

If resource tenant outside validated membership:
  -> DENY

If explicit security deny applies:
  -> DENY

If required attributes unavailable:
  -> DENY hoặc chế độ an toàn đã được phê duyệt

If one complete and authorized permit rule matches:
  -> PERMIT, subject to obligations

Otherwise:
  -> DENY
~~~

Đây là cách mô tả nguyên tắc **không tự mở quyền**, không phải thuật toán bắt buộc với mọi engine. Các kết quả **NOT_APPLICABLE** hoặc **INDETERMINATE** cần được xử lý theo policy combining đã thiết kế; **không chuyển lỗi PDP thành PERMIT mặc định**.

### 7.2. Quyền đặc biệt cần tách policy

Ví dụ `invoice.export` thường rủi ro cao hơn `invoice.read`. Không nên đặt một rule “có quyền đọc thì xuất được” chỉ vì dễ cấu hình. Quyền export có thể cần **phê duyệt, phân loại dữ liệu, giới hạn tenant, mức xác thực và thời hạn** riêng.

## 8. Policy-as-Code và các cách tổ chức repository

**Policy-as-Code** biểu diễn policy bằng dữ liệu/mã có thể **version control, review, test, build và deploy** tự động trong khuôn khổ kiểm soát. Đây là một phương pháp, không phải yêu cầu mọi tổ chức phải dùng một công cụ duy nhất.

Một cấu trúc tham khảo:

~~~text
policy-repository/
  README.md                  # Quy ước chung của repository
  schemas/
    authorization-input.json
    policy-metadata.json
  policies/
    finance/
      invoice-read.rego
      invoice-export.rego
      metadata.yaml
    crm/
      lead-access.rego
      metadata.yaml
    platform/
      baseline-deny.rego
  tests/
    finance/
      invoice-read-tests.rego
      invoice-scenarios.json
  environments/
    staging/
      release-manifest.yaml
    production/
      release-manifest.yaml
  governance/
    owners.yaml
    sod-rules.yaml
~~~

Đây là **cấu trúc hình dung**, không phải yêu cầu tạo những file này trong bài tập. Dù chia folder thế nào, cần phân rõ **source được review, artifact đã được phê duyệt và manifest đang triển khai**.

### 8.1. Mono-repository và phân chia theo domain

| Mô hình | Điểm mạnh | Rủi ro cần kiểm soát |
|---|---|---|
| **Monorepo policy** | Quy ước, review, kiểm tra phụ thuộc và audit tập trung | Quyền sửa quá rộng; một thay đổi ảnh hưởng nhiều domain |
| **Repository theo domain** | Team sở hữu độc lập, release linh hoạt | Khó thống nhất schema và baseline deny |
| **Centralized managed policy store** | Quản trị tập trung qua giao diện/API | Cần lịch sử phiên bản, test và xuất bằng chứng tương đương |
| **Hybrid** | Chính sách nền chung + policy theo ứng dụng | Cần cơ chế combining, ownership và phát hành tương thích |

**Không nên chọn mô hình chỉ theo sở thích Git hoặc giao diện.** Quyết định phụ thuộc số ứng dụng, mức rủi ro, khả năng CI/CD, yêu cầu vận hành và sự phân chia trách nhiệm thực tế.

### 8.2. Policy-as-Code không đồng nghĩa auto-approve

Một pull request được merge chỉ nên được công bố khi:

1. Đúng người có quyền thay đổi domain.
2. Kiểm tra schema/định dạng thành công.
3. Test chính sách và regression đạt.
4. Rà soát bảo mật/nghiệp vụ đạt theo mức rủi ro.
5. Artifact được gắn version/digest và xuất bản qua kênh kiểm soát.
6. Runtime đã nạp và phản hồi readback phù hợp.

## 9. Ví dụ chính sách có thể kiểm tra bằng Rego

**Open Policy Agent (OPA)** là một lựa chọn triển khai Policy-as-Code; **Rego** biểu diễn quy tắc dựa trên dữ liệu đầu vào. Ví dụ sau dùng cú pháp **Rego v1**, để minh họa logic authorization của một API.

~~~rego
package iam.invoice

import rego.v1

default allow := false

allow if {
    input.subject.kind == "HUMAN"
    input.subject.accountStatus == "ACTIVE"
    input.subject.engagementStatus == "ACTIVE"
    input.action == "invoice.read"

    input.subject.tenantId == input.resource.tenantId
    input.resource.projectId in input.subject.authorizedProjectIds
    "finance_invoice_reader" in input.subject.roles

    input.context.authenticationAssuranceOk == true
}
~~~

Ví dụ cố tình **không dùng các giá trị input do client tự ý cung cấp như dữ liệu tin cậy**. Một PEP hoàn chỉnh phải:

- Xác thực access token/phiên trước khi xây `input.subject`.
- Đọc tenant/resource từ backend hoặc data source được tin cậy.
- Đọc account/engagement và project membership từ PIP đủ mới.
- Chọn đúng policy package/version của API.
- Chỉ thực thi thao tác khi kết quả PERMIT và các nghĩa vụ khác đã đáp ứng.

**Không dùng mã minh họa như middleware production hoàn chỉnh.** Cần kiểm thiết kế tenant, cấu trúc dữ liệu null/missing, hiệu năng, log, token lifecycle và bảo vệ giao tiếp PEP–PDP.

### 9.1. Bộ input thử nghiệm

~~~json
{
  "subject": {
    "kind": "HUMAN",
    "canonicalId": "P-2048",
    "accountStatus": "ACTIVE",
    "engagementStatus": "ACTIVE",
    "tenantId": "tenant-a",
    "roles": ["finance_invoice_reader"],
    "authorizedProjectIds": ["project-17"]
  },
  "action": "invoice.read",
  "resource": {
    "id": "INV-501",
    "tenantId": "tenant-a",
    "projectId": "project-17"
  },
  "context": {
    "authenticationAssuranceOk": true
  }
}
~~~

Kỳ vọng **PERMIT** trong logic mẫu. Nếu thay `resource.tenantId` thành `tenant-b`, hoặc `engagementStatus` thành `ENDED`, kỳ vọng **DENY**. Nếu thiếu `subject.authorizedProjectIds`, policy mẫu không nên cho phép vì không chứng minh được membership.

### 9.2. Đừng để policy test chỉ có trường hợp thành công

Những bài test hữu ích thường gồm:

- Người đúng role, tenant, project, engagement → PERMIT.
- Cùng subject yêu cầu resource của tenant khác → DENY.
- Subject Leaver nhưng token/session cũ còn sống → DENY khi policy/kiến trúc kiểm được trạng thái hiện hành.
- User không có role, chỉ có MFA mạnh → DENY.
- Workload dùng client credentials vào policy chỉ dành cho HUMAN → DENY.
- Thiếu project membership hoặc trạng thái account → DENY theo chính sách.
- User còn role nhưng chỉ có quyền đọc, cố export → DENY.
- Owner dự án đã đổi, grant cũ không còn căn cứ → DENY.

Độ bao phủ test phải xét **tất cả nhánh có ý nghĩa bảo mật**, không chỉ số dòng mã.

## 10. Quản lý owner, trách nhiệm phê duyệt và SoD

Một policy không thể an toàn lâu dài nếu không ai chịu trách nhiệm khi nghiệp vụ đổi hoặc khi người duyệt rời công ty.

| Vai trò quản trị | Trách nhiệm chính |
|---|---|
| **Business/data owner** | Xác nhận nhu cầu truy cập và phạm vi tài nguyên hợp lệ |
| **Security/IAM governance** | Kiểm least privilege, SoD, ngoại lệ và rủi ro |
| **Policy engineer** | Biểu diễn rule, test, review tương thích |
| **PAP/release operator** | Quản lý quy trình phát hành và quyền thay đổi |
| **Application/API owner** | Xác nhận PEP áp chính sách ở mọi đường truy cập |
| **Identity/attribute owner** | Đảm bảo nguồn dữ liệu PIP có thẩm quyền và độ mới |
| **Audit/compliance** | Theo dõi bằng chứng thay đổi, phê duyệt và hiệu lực |

### 10.1. Separation of Duties đối với thay đổi policy

Với chính sách nhạy cảm, người viết rule không nên có toàn quyền **tự sửa, tự duyệt và tự đưa vào production**. Quy trình có thể yêu cầu business owner và security reviewer độc lập tùy rủi ro.

Đặc biệt với policy cho `payment.release`, `user.create`, `role.admin` hoặc `audit.log.modify`, một lỗi duy nhất có thể mở quyền lớn. Cần kiểm soát:

- Quyền ghi repository.
- Quyền approve/release.
- Quyền quản trị secrets và signing keys.
- Quyền thay đổi pipeline.
- Quyền đổi cấu hình runtime hoặc bỏ qua PEP.

**Protect repository không đủ** nếu người vận hành có thể sửa policy trực tiếp ở PDP mà không để lại lịch sử. Cần phát hiện **out-of-band changes**.

## 11. Phiên bản, vòng đời và lịch sử thay đổi policy

Một policy có thể đi qua các trạng thái:

~~~mermaid
flowchart LR
    A["DRAFT<br/>Soạn thảo"] --> B["IN_REVIEW<br/>Business + Security"]
    B -->|"Cần chỉnh"| A
    B --> C["APPROVED<br/>Được phép phát hành"]
    C --> D["STAGED<br/>Đã tải tại môi trường thử"]
    D --> E["ACTIVE<br/>Đang thực thi"]
    E --> F["DEPRECATED<br/>Có phương án thay"]
    F --> G["RETIRED<br/>Không còn triển khai"]
    E -->|"Sự cố / lỗi"| R["ROLLBACK REVIEW<br/>Quyết định khôi phục"]
    R --> E
~~~

Trạng thái chỉ là **mô hình tham khảo**, không phải schema mặc định của một công cụ. Khi rollback, cần chỉ ra **phiên bản đích** và xác minh nó không khôi phục lỗ hổng hoặc quyền đã được thu hồi.

### 11.1. SemVer và policy version

Một số nhóm dùng `MAJOR.MINOR.PATCH` để diễn đạt mức độ thay đổi. Tuy nhiên **một thay đổi rất nhỏ trong policy có thể tạo tác động quyền rất lớn**. Ví dụ sửa `==` thành `!=` chỉ một ký tự nhưng thay đổi đáng kể tập subject được phép.

Vì vậy, version giúp truy vết, còn **risk classification** phải dựa trên **khác biệt hành vi chính sách**, không chỉ tên phiên bản.

### 11.2. Không tự coi “bản mới hơn” là an toàn hơn

Nếu rule mới loại bỏ kiểm tra tenant, tăng coverage nhưng giảm bảo mật, pipeline phải chặn hoặc yêu cầu phê duyệt đặc biệt. Cần lưu **diff policy, diff kết quả PERMIT/DENY của test corpus và lý do đổi**.

### 11.3. Policy với mốc hiệu lực

Một chính sách có thể cần hiệu lực từ thời điểm quy định; ví dụ sau khi một dự án chính thức kết thúc. Phải phân biệt:

- **Policy effectiveAt:** Khi quy tắc mới được phép áp dụng.
- **Identity/engagement effectiveAt:** Khi trạng thái subject thay đổi.
- **Entitlement expiry:** Khi một grant/role hết hiệu lực.
- **Deployment activatedAt:** Khi PDP thực sự nạp policy.

Các mốc này không tự đồng bộ. Nếu quy tắc cần chặn quyền từ 18:00 nhưng site B vẫn dùng bản cũ đến 18:30, cần đánh giá và xử lý **khoảng trễ quyền hiệu dụng**.

## 12. Pipeline kiểm soát thay đổi policy

~~~mermaid
flowchart TD
    A["Yêu cầu policy change<br/>Lý do + owner + risk"] --> B["Draft / Pull Request<br/>source + metadata"]
    B --> C["Validate syntax/schema/types"]
    C --> D["Static checks + security lint<br/>deny-default, tenant, token"]
    D --> E["Unit + regression + SoD tests<br/>PERMIT/DENY scenarios"]
    E --> F{"Business / Security approval<br/>và SoD phù hợp?"}
    F -->|Không| B
    F -->|Có| G["Build artifact immutable<br/>version + digest/signature nếu áp dụng"]
    G --> H["Staging / shadow evaluation<br/>đối chiếu quyết định"]
    H --> I{"Đạt tiêu chí và<br/>không overgrant?"}
    I -->|Không| B
    I -->|Có| J["Canary / phased rollout<br/>theo domain/tenant khi phù hợp"]
    J --> K["Runtime readback<br/>PDP version + allow/deny"]
    K --> L{"Tất cả target đạt?"}
    L -->|Có| M["Active + audit<br/>giám sát drift"]
    L -->|Không| N["Dừng mở rộng, xử lý / rollback an toàn"]
~~~

### 12.1. Bốn tầng kiểm thử thiết yếu

1. **Structural tests:** Schema, kiểu dữ liệu, package, ID, reference và dependency chính xác.
2. **Policy unit tests:** Đầu vào nhỏ với quyết định mong đợi PERMIT/DENY/INDETERMINATE.
3. **Regression tests:** So sánh hành vi trên bộ case đã được business owner xác nhận; chú ý những PERMIT mới không có căn cứ.
4. **Integration tests:** PEP thật sự chặn endpoint, PIP trả thuộc tính đúng, PDP trả version mong đợi, không còn đường bypass qua API khác.

### 12.2. Kiểm tra khác biệt quyết định

Một bản mới có thể tạo ra:

~~~text
Policy v1:
  invoice.read tenant-a/project-17 -> PERMIT
  invoice.read tenant-b/project-17 -> DENY
  invoice.export without approval  -> DENY

Policy v2 candidate:
  invoice.read tenant-a/project-17 -> PERMIT
  invoice.read tenant-b/project-17 -> PERMIT   <-- cần chặn
  invoice.export without approval  -> DENY

Dù số lượng test "pass" cao:
  PERMIT mới xuyên tenant không được phép là lỗi nghiêm trọng.
~~~

Một báo cáo tốt phân loại **new permits, removed permits, new denies, removed denies và trường hợp không xác định**, thay vì chỉ ghi số test chạy thành công.

## 13. Phân phối policy tới PDP và tính nhất quán runtime

**Policy distribution** có thể theo cơ chế push, pull, bundle, API, sidecar hoặc mô hình được quản lý. Chọn cách nào phải xác định:

- Nguồn artifact **được phép nhận**.
- Cách xác thực tải/đẩy artifact và kiểm tra tính toàn vẹn.
- Khả năng tải toàn bộ hoặc chỉ cập nhật phần chênh lệch.
- Cách các nút xử lý version sai, thiếu dependency hoặc lỗi parse.
- Thời hạn cache và khi nào phải cập nhật khẩn cấp.
- Nhiều PDP có thể **chạy khác phiên bản trong quá trình rollout** không?
- Cách biết thực sự node nào đang chạy bản nào.

### 13.1. Mô hình phân phối

~~~mermaid
sequenceDiagram
    autonumber
    participant G as Source repository + PAP
    participant B as Build / Artifact registry
    participant A as PDP site A
    participant C as PDP site B
    participant P as API / PEP
    participant O as Monitoring / Audit

    G->>B: Policy đã duyệt + tests
    B-->>G: Artifact v24 + digest
    B->>A: Phân phối hoặc cho tải v24
    B->>C: Phân phối hoặc cho tải v24
    A->>A: Kiểm nguồn, digest, schema rồi activate
    C->>C: Kiểm nguồn, digest, schema rồi activate
    A-->>O: Runtime version v24
    C-->>O: Runtime version v24
    P->>A: Request subject/action/resource
    A-->>P: Decision + policy version
    O->>O: Kiểm version drift và quyết định
~~~

**Điểm cần nhớ:** Nếu site B chưa xác nhận bản mới, không thể báo **triển khai đã hoàn tất ở mọi site**. Với thay đổi chặn truy cập rủi ro cao, phải có **cơ chế hành động khi một phần PDP chưa nhận policy mới**, như tạm chặn tại PEP hoặc chặn triển khai, theo kiến trúc và chính sách đã duyệt.

### 13.2. Khi PEP/PDP không liên lạc được

Có ba trường hợp cần tách:

1. **PDP không hoạt động:** PEP không thể nhận quyết định mới.
2. **PDP chạy policy cũ:** Có quyết định nhưng không đạt phiên bản bắt buộc.
3. **PDP có policy đúng nhưng PIP không có dữ liệu mới:** Quy tắc đúng, đầu vào sai/cũ.

Ba trường hợp cần cơ chế **health, freshness và fail-safe** khác nhau. Không tự dùng “last known allow” cho tài nguyên nhạy cảm vô hạn.

## 14. Caching và độ mới: policy version khác attribute freshness

Trong JML, policy thường ổn định hơn **trạng thái subject**. Ví dụ rule “contractor chỉ được truy cập khi hợp đồng còn active” không cần sửa mỗi khi có nhà thầu rời công ty. **PIP/identity state** mới là dữ liệu thay đổi.

| Thành phần cache | Dữ liệu | Rủi ro khi quá cũ |
|---|---|---|
| **Policy cache** | Rule/version đang chạy | Quy tắc mới chặn quyền chưa có hiệu lực |
| **Attribute cache** | Group, role, department, status, project | Mover/Leaver bị áp quyền cũ |
| **Decision cache** | Kết quả PERMIT cho request tương tự | Dùng quyết định cũ sau khi dữ liệu thay đổi |
| **Token/session** | Claim và trạng thái đăng nhập đã cấp | Role/engagement cũ được chấp nhận |
| **Entitlement cache** | Quyền trực tiếp/group tại app | Gỡ role ở IAM nhưng app vẫn còn quyền |

### 14.1. Cache key phải đủ ngữ cảnh

Nếu cache quyết định PERMIT theo chỉ `userId` và `action` mà bỏ qua **resource/tenant**, quyền đọc một báo cáo có thể bị dùng sai cho báo cáo khác.

Một cache key thiết kế cần xét:

~~~text
subject (ID + tenant + relevant assignment version)
action
resource ID/type/tenant + classification
context/policy-relevant attributes
policy version
required attribute freshness / expiry
~~~

Không nhất thiết đưa tất cả thuộc tính vào chuỗi cache key nếu kiến trúc có cơ chế invalidation tương đương, nhưng **mọi đầu vào ảnh hưởng quyết định phải được xem xét**.

### 14.2. Readback phải kiểm policy và dữ liệu

Một phép kiểm hoàn tất phù hợp có thể cần:

- Artifact `v24` đã được PDP tải.
- Policy đang active đúng phiên bản/digest.
- PIP thấy `engagementStatus=ENDED` của contractor.
- API request của contractor bị từ chối, kể cả nếu phiên cũ còn tồn tại khi chính sách đòi thu hồi.
- Audit ghi rõ version và mốc đối soát.

Kiểm policy version mà không kiểm **quyền thực tế** sẽ bỏ sót rủi ro JML.

## 15. Fail-closed, degraded mode và tính sẵn sàng của repository

Repository có thể tạm ngừng hoạt động trong khi PDP vẫn có **artifact đã kiểm tra** và tiếp tục trả quyết định. Đây có thể là thiết kế availability hợp lệ, nhưng cần ranh giới rõ:

- **Repository unavailable:** Không build/publish policy mới; runtime có thể tiếp tục dùng bản đã phê duyệt theo policy.
- **PDP unavailable:** PEP không nhận được quyết định mới; phải áp chế độ an toàn thích hợp.
- **PIP unavailable:** Không có thuộc tính trạng thái mới; không mặc định chấp nhận mọi request.
- **Runtime stale beyond limit:** Có policy cũ nhưng không đáp ứng yêu cầu cập nhật/thu hồi khẩn cấp; cần giới hạn chức năng hoặc chặn.

| Trường hợp | Hướng hành xử cần cân nhắc | Điều không nên làm |
|---|---|---|
| Mất repository vài phút | Giữ artifact active đã xác minh; báo chậm publish | Tải policy từ nguồn chưa tin |
| Lỗi PDP với API tài chính | Từ chối hành động nhạy cảm hoặc dùng phương án an toàn được duyệt | PERMIT mặc định |
| PIP không xác định status Leaver | Từ chối quyền cần trạng thái active rõ | Coi null là ACTIVE |
| Một site chưa nhận policy chặn truy cập | Cảnh báo, chặn đường truy cập có rủi ro và xử lý rollout | Tuyên bố đã thu hồi xong |
| App ít nhạy cảm dùng dữ liệu hiển thị cache | Có thể dùng degraded mode có TTL và phạm vi giới hạn | Mở rộng sang export/admin |
| Break-glass trong sự cố | Theo quy trình khẩn cấp được thiết kế riêng | Vô hiệu hóa mọi audit/SoD |

**Fail-closed không có nghĩa ngừng toàn bộ hệ thống bằng một công thức duy nhất.** Phải phân loại tài nguyên và hành động, định nghĩa tình trạng suy giảm nào được phép, mức cache tối đa, người phê duyệt và cách lưu audit. Nhưng **không được biến lỗi hạ tầng thành lối bỏ qua authorization**.

## 16. Policy repository trong Joiner lifecycle

**Joiner** không nhất thiết tạo **một policy mới cho từng nhân viên**. Thông thường, tổ chức sử dụng policy đã được duyệt, còn IAM cập nhật **identity, account, group/role và thuộc tính** khi người mới đủ điều kiện.

Ví dụ nhân viên An gia nhập Finance:

~~~text
Policy đang active:
  finance.invoice.read v1.3
  Chỉ PERMIT nếu:
    subject role finance_invoice_reader
    AND engagement active
    AND đúng tenant/project
    AND đáp ứng mức xác thực

Joiner:
  HR/VMS -> xác minh quan hệ và mốc hiệu lực
  IAM -> tạo identity/account, cấp role có căn cứ
  IdP/SCIM -> đồng bộ tới các ứng dụng
  PIP -> trạng thái + membership đáng tin
  PDP -> đánh giá theo policy v1.3
  PEP -> chỉ cho phép khi mọi điều kiện đạt
~~~

### 16.1. Những kiểm tra quan trọng

1. Danh tính người mới đã được proofing đủ mức và liên kết account đúng.
2. `effectiveAt` chưa tới thì không mở quyền công việc trái chính sách.
3. Vai trò/entitlement được cấp theo **role catalog và approval** hợp lệ, không sao chép quyền người tiền nhiệm.
4. PIP có đúng status và scope; nếu chưa đồng bộ thì không giả có quyền.
5. PEP áp policy tại **từng API/resource** cần bảo vệ.
6. Readback account, assignment và kết quả PERMIT/DENY bằng identity kiểm thử hoặc cơ chế phù hợp.

**Vai trò repository:** Lưu rule và kiểm soát việc phát hành. **Vai trò IAM/SCIM/PIP:** Cập nhật trạng thái từng subject. Không nhầm hai vòng đời.

## 17. Policy repository trong Mover lifecycle

Một nhân viên chuyển Sales → Finance có thể giữ nguyên canonical identity và phiên xác thực, nhưng **quyền truy cập hiện hành phải được tính lại**.

### 17.1. Khi không cần sửa policy

Nếu đã có policy:

~~~text
Permit invoice.read nếu:
  engagement ACTIVE
  role finance_invoice_reader
  project membership hợp lệ
  tenant khớp

Permit lead.update nếu:
  engagement ACTIVE
  role sales_representative
  lead thuộc scope hợp lệ
~~~

thì Mover chủ yếu thay **role, project membership và entitlement** tại IAM/PIP/app. Repository giữ nguyên.

### 17.2. Khi cần sửa policy

Nếu doanh nghiệp thay hẳn cách phân quyền (ví dụ từ vai trò chung sang phê duyệt theo project), cần tạo policy version mới, migration plan và thử các tình huống:

- Mover đã gỡ Sales: không còn update lead.
- Mover mới vào Finance: chỉ đọc hóa đơn đúng project.
- Token cũ có claim Sales: không còn giữ quyền quá mốc policy.
- Một nhân viên có hai engagement hợp lệ: không xóa quyền engagement còn hiệu lực.
- Truy cập xuyên tenant: luôn bị chặn nếu không có grant đặc biệt được duyệt.

### 17.3. Phát hiện quyền tồn dư

Nếu policy version đã nâng lên nhưng API vẫn cho phép lead từ dự án cũ, điều tra theo từng lớp:

1. PDP chạy version nào?
2. `subject.roles`/`projectIds` có bị cache cũ không?
3. PEP có bỏ qua kiểm tra ở endpoint phụ không?
4. Token/session có chứa entitlement cũ không?
5. Có **direct grant** ở ứng dụng nằm ngoài role catalog không?
6. Có thêm engagement hợp lệ nào cho phép hành động đó không?

Không tự quy lỗi cho repository khi nguyên nhân nằm ở **PIP hoặc local ACL**; nhưng repository cần giúp truy vết rõ policy đang áp.

## 18. Policy repository trong Leaver lifecycle

**Leaver** thường là biến cố nhạy cảm nhất: account hoặc engagement không còn đủ điều kiện truy cập nhưng phiên/token có thể còn sống.

Một policy nền hữu ích:

> **DENY** hành động công việc nếu không xác minh được rằng subject và engagement liên quan đang hợp lệ tại thời điểm/quy tắc yêu cầu.

Chính sách này cần được **triển khai và thực thi**, không chỉ ghi ở repository.

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HR / VMS
    participant I as IAM / IGA
    participant S as IdP / SCIM / App
    participant PIP as PIP / Identity state
    participant PDP as PDP (policy v24)
    participant PEP as API / PEP
    participant A as Audit / Verification

    H->>I: Leaver event + effectiveAt
    I->>S: Disable / revoke entitlement
    I->>PIP: Cập nhật engagement/subject status
    S-->>I: Kết quả thao tác
    PEP->>PDP: Request từ subject có token cũ
    PDP->>PIP: Lấy trạng thái đủ mới
    PIP-->>PDP: engagement ENDED
    PDP-->>PEP: DENY theo policy v24
    PEP-->>A: Quyết định + policy version
    I->>A: Readback account, role, session/token
    A-->>I: Verified hoặc pending exception
~~~

Sơ đồ minh họa kiến trúc có **status check tại decision time**; hệ thống thực tế có thể dùng token ngắn hạn, introspection hoặc cơ chế khác. Nếu PDP chỉ dựa trên claim cũ từ JWT và không có nguồn trạng thái mới, **policy kiểm tra status không tự bảo đảm Leaver bị chặn ngay**.

### 18.1. Tách ba điều kiện “đã xong”

| Điều kiện | Ai chứng minh? | Vì sao chưa đủ một mình? |
|---|---|---|
| **Policy phù hợp** | Repository/PAP + runtime version | Đúng rule nhưng dữ liệu có thể cũ |
| **Identity/account/entitlement đã thu hồi** | IAM/IdP/SCIM/app target | Token hoặc phiên cũ có thể còn hợp lệ |
| **Quyền hiệu dụng không còn** | PEP/RS và readback/verification | Cần xét mọi đường truy cập trong phạm vi |

**Đóng Leaver** chỉ khi tiêu chí bắt buộc được xác minh, ngoại lệ còn mở có người xử lý và thời hạn; không dùng nhãn `WRITTEN` hoặc `APPROVED` của policy để suy ra deprovisioning hoàn tất.

### 18.2. Một người có nhiều engagement

Contractor kết thúc hợp đồng A nhưng còn B. Policy và dữ liệu PIP cần phân biệt **entitlement/project của A** với **quyền B còn được phê duyệt**. Nếu một policy chỉ kiểm `accountActive=true`, có thể giữ quá nhiều quyền từ A. Phải đánh giá **engagement/resource relationship**, không chỉ trạng thái tổng thể.

## 19. Tài khoản dịch vụ, workload và policy repository

Trong hệ thống máy đến máy, subject không nhất thiết là nhân viên. **OAuth Client Credentials**, workload identity hoặc service principal có thể được cấp token để gọi API.

Một policy tốt cần phân biệt:

| Đặc tính | Human user | Workload/service account |
|---|---|---|
| **Định danh** | Canonical person + IdP subject | Workload ID/client ID/managed identity |
| **Nguồn eligibility** | HR/VMS/engagement | Service catalog, deployment/workload registry |
| **Authenticator/credential** | MFA/passkey/session theo thiết kế | Certificate, private key, managed identity, secret |
| **Mục đích** | Nhiệm vụ công việc | Tác vụ hệ thống được duyệt |
| **Scope** | Role, tenant, project, dữ liệu | Audience/API, environment, workload function |
| **Lifecycle** | Joiner–Mover–Leaver người dùng | Provision–rotate–retire của workload và owner |
| **Owner** | Người/quản lý/sponsor theo role | Service owner và team vận hành |

### 19.1. Policy cho workload không nên dùng lại nguyên xi policy người

Ví dụ policy `finance_invoice_reader` yêu cầu `subject.kind=HUMAN`. Một service account có `client_id=svc-invoice-sync` không nên bị giả dạng thành người có role Finance để vượt qua rule. Nên có policy riêng:

~~~text
PERMIT invoice.sync nếu:
  subject.kind == WORKLOAD
  AND workloadId == "svc-invoice-sync"
  AND client/audience được xác minh
  AND environment == "production"
  AND workload status == ACTIVE
  AND scope chỉ bao gồm chức năng đồng bộ cần thiết
  AND resource nằm trong tenant/service boundary hợp lệ
~~~

**Owner kỹ thuật rời tổ chức** không làm workload tự động biến thành tài khoản người đó. Cần chuyển giao owner, xử lý quyền quản lý secret và rotate/revoke credential khi cần, đồng thời bảo vệ dependency sản xuất. Repository có thể chứa policy; trạng thái workload và owner phải có **nguồn dữ liệu quản trị đúng**.

## 20. Tài khoản đặc quyền, SoD và break-glass policies

### 20.1. Policy cho đặc quyền

Quyền như `production.admin` hoặc `iam.policy.publish` cần chú ý:

- Chỉ chủ thể có thẩm quyền và trạng thái hợp lệ.
- MFA/step-up và/hoặc phiên PAM/JIT theo rủi ro.
- Giới hạn thời hạn và môi trường.
- Phân tách người yêu cầu, phê duyệt và người giám sát.
- Kiểm toán chi tiết và khả năng chặn nhanh.
- Không “gộp” với role người dùng thường ngày chỉ để đơn giản hóa.

### 20.2. SoD trong chính sách và quản trị repository

SoD có hai lớp:

1. **Nghiệp vụ:** Người tạo hóa đơn không tự phê duyệt hóa đơn của mình khi policy cấm.
2. **Quản trị policy:** Người sửa policy cấp quyền admin không tự duyệt triển khai và che log, nếu quy trình yêu cầu review độc lập.

Một policy có thể diễn đạt cả RBAC và ABAC, nhưng **điều kiện tạo/chấp thuận trên cùng một giao dịch** thường cần dữ liệu relationship/resource, không chỉ xem role name.

### 20.3. Break-glass không đồng nghĩa bỏ policy

Tài khoản khẩn cấp có thể cần truy cập khi IdP/PIP gặp sự cố; vì vậy **quy trình break-glass phải được định nghĩa trước**, với giới hạn hành động, người có thẩm quyền, bảo vệ credential, giám sát và hậu kiểm.

Không viết một rule `if emergency: permit all` không có cơ chế xác minh emergency. Nếu phải sử dụng chính sách dự phòng, cần xác định rõ **cách kích hoạt, bằng chứng, phạm vi và thời gian**.

## 21. Threat model của policy repository

| Mối đe dọa | Tình huống | Kiểm soát |
|---|---|---|
| **Unauthorized policy modification** | Kẻ tấn công sửa rule từ DENY sang PERMIT | Access control, review, protected branch, signed artifact nếu áp dụng |
| **Insider privilege escalation** | Quản trị viên tự cấp quyền qua policy | SoD, approval độc lập, audit |
| **Supply-chain compromise** | Pipeline hoặc dependency bị thay | Build isolation, artifact integrity, secret protection |
| **Runtime drift** | PDP bị sửa trực tiếp ngoài repository | Readback digest/version, reconciliation, alert |
| **Stale policy** | Một site vẫn chạy bản cũ | Activation monitoring, TTL, rollout gates |
| **Stale attribute** | Leaver đã kết thúc nhưng PIP trả ACTIVE | Data freshness, status check, revoke strategy |
| **Policy injection** | Rule chạy trên dữ liệu chưa kiểm chứng hoặc biểu thức không an toàn | Schema/type validation, trusted PIP, sandbox engine |
| **Fail-open** | PDP lỗi, PEP tự PERMIT | Fail-safe behavior và integration tests |
| **Tenant isolation failure** | Chính sách thiếu so sánh tenant | Negative tests và resource-level enforcement |
| **Secret leakage** | Private key/token vô tình commit vào repo | Secret scanning, vault, revoke khi lộ |
| **Unbounded policy complexity** | Evaluator quá tải do rule/tập dữ liệu lớn | Benchmark, giới hạn input, profiling |
| **Rollback vulnerability** | Khôi phục bản cũ có lỗ hổng bảo mật | Risk review và protected baseline |
| **Audit tampering** | Xóa lịch sử sửa policy/decision | Log độc lập, bảo vệ toàn vẹn, phân quyền |
| **Unowned policy** | Owner nghỉ việc, policy hết hạn mà không ai review | Ownership lifecycle, certification, expiry alerts |

### 21.1. Chỉ mã sạch không đủ

Một policy **đúng cú pháp** vẫn có thể sai nghiệp vụ. Ví dụ, điều kiện tenant không xuất hiện trong rule, hoặc role `finance_admin` được map từ nhóm IdP đối tác có cùng tên. Cần kiểm **trust boundary**, source-of-truth, test domain và quy trình phê duyệt.

### 21.2. “Policy không có lỗi” khác “không có bypass”

Một API có thể dùng PEP/PDP đúng, nhưng endpoint batch, download link, websocket hoặc service-to-service có thể đi đường khác. Khi áp policy tập trung, cần kiểm kê **mọi đường truy cập đến resource** và bảo đảm việc thực thi không thể bị bypass bởi một đường phụ.

## 22. Rollback policy: khôi phục dịch vụ mà không phục hồi quyền cũ

Rollback cần thận trọng vì **phiên bản cũ có thể chứa chính lỗ hổng đã được vá**.

Ví dụ:

~~~text
v19: Cho invoice.export nếu role finance_user
v20: Chỉ finance_exporter + approval + project scope
v21: Có lỗi parsing khiến nhiều request hợp lệ bị DENY

Rollback trực tiếp v21 -> v19:
  Có thể mở lại export cho toàn finance_user (sai bảo mật).

Phương án an toàn:
  Ưu tiên sửa nhanh v21 thành v22,
  hoặc rollback về v20 đã xác minh,
  kiểm thử những DENY bảo mật bắt buộc.
~~~

### 22.1. Một quy trình rollback có kiểm soát

1. Xác định lỗi là **policy syntax, dữ liệu PIP, PEP integration hay rollout drift**.
2. Chọn phiên bản đích **đã được phê duyệt** và không khôi phục quyền bị thu hồi có chủ ý.
3. Chạy regression trên những case nhạy cảm: tenant, privileged, SoD, Leaver.
4. Triển khai với thay đổi được ghi nhận, owner và điều kiện tạm dừng.
5. Readback PDP version/digest trên các site.
6. Kiểm tra hành vi ALLOW/DENY ở endpoint thật hoặc test an toàn.
7. Lưu sự cố, quyết định rollback, phạm vi ảnh hưởng và kế hoạch khắc phục.

**Rollback mã không đồng nghĩa rollback trạng thái IAM.** Không được tái kích hoạt account Leaver hoặc khôi phục grant cũ chỉ vì quay về artifact trước đó.

## 23. Kiểm toán repository và quyết định truy cập

Một hệ thống policy repository cần **hai nhóm bằng chứng riêng**:

- **Change audit:** Chính sách nào được sửa, ai đề xuất/duyệt, phiên bản, artifact, mốc triển khai.
- **Decision audit:** Một request dùng policy version nào, subject/action/resource nào và tại sao PERMIT/DENY.

### 23.1. Mẫu decision record

~~~json
{
  "decisionId": "PBAC-2026-411",
  "time": "2026-12-01T09:15:00+07:00",
  "pep": "invoice-api",
  "pdp": "authz-site-a",
  "policyId": "finance.invoice.read.v1",
  "policyVersion": "1.3.0",
  "policyArtifactDigest": "example-digest-reference",
  "subjectRef": "P-2048",
  "subjectKind": "HUMAN",
  "action": "invoice.read",
  "resourceRef": "INV-501",
  "tenantRef": "tenant-a",
  "decision": "DENY",
  "reasonCode": "ENGAGEMENT_NOT_ACTIVE",
  "attributeFreshness": "WITHIN_POLICY_LIMIT",
  "correlationId": "REQ-9218"
}
~~~

Đây là **ví dụ minh họa**, không phải chuẩn log bắt buộc. Không lưu access token, mật khẩu, secret, nội dung chứng từ hoặc dữ liệu cá nhân vượt mức cần thiết. Bảo vệ và kiểm soát thời hạn lưu audit.

### 23.2. Truy dấu câu hỏi thực tế

Khi một người dùng Mover vẫn đọc được dữ liệu dự án cũ, đội vận hành cần trả lời:

1. **PEP nào** cho phép request?
2. **PDP nào** trả PERMIT và dùng **policy version** gì?
3. **Attribute source/version** nào nói người dùng còn thuộc dự án A?
4. Thay đổi Mover ở HR/VMS đã được IAM áp chưa?
5. Ứng dụng có direct grant, token claim cũ hoặc cache riêng không?
6. Tại sao test regression không phát hiện?
7. Có API khác chưa dùng PEP/PDP đúng không?

Repository có version/history giúp điều tra **policy**, còn dữ liệu IAM/PEP/RS giúp chứng minh **quyền hiệu dụng**.

## 24. Giám sát chất lượng Policy repository

| Chỉ số | Mục tiêu | Cần lưu ý |
|---|---|---|
| **Policy ownership coverage** | Tỷ lệ policy có owner có thẩm quyền | Tên owner tồn tại nhưng đã Leaver chưa? |
| **Approval traceability** | Tỷ lệ thay đổi có phê duyệt và reason | Không chỉ xem commit author |
| **Policy test coverage** | Tỷ lệ rule/đường đi có test có ý nghĩa | Số test nhiều không đồng nghĩa có negative tests |
| **Unauthorized change findings** | Sửa ngoài pipeline hoặc khác nguồn | Cần runtime drift detection |
| **Runtime version convergence** | Các PDP đã nạp artifact mong muốn | Dashboard repository xanh chưa đủ |
| **Policy activation latency** | Từ approved release tới active ở các target | Phân biệt với data freshness |
| **Policy evaluation error rate** | Sai schema, missing attribute, timeout | Không mặc định cho phép khi lỗi |
| **Authorization decision latency** | Ảnh hưởng PEP/PDP/PIP đến API | Tối ưu cache không được làm sai quyền |
| **New permit risk** | PERMIT mới so với baseline đã duyệt | Cần review đặc biệt quyền rộng |
| **Cross-tenant deny tests** | Kiểm biên giới tenant/resource | Không bỏ qua đường API phụ |
| **Policy exception aging** | Ngoại lệ còn mở bao lâu | Cần owner, TTL và chứng cứ |
| **JML access convergence** | Thời gian event đến quyền thực tế | Đo readback, không đo lệnh đã gửi |
| **Residual access after Leaver** | Session/grant còn trái chính sách | Không quy hết cho repository |
| **Rollback safety** | Số lần rollback gây mở quyền ngoài mong đợi | Test baseline và rollback review |

Không có SLA chung cho mọi ứng dụng. Mục tiêu SLO về **policy deployment, decision latency, attribute freshness và Leaver revocation** phải theo rủi ro tài nguyên, khả năng hệ thống và yêu cầu tổ chức.

## 25. Thực hành tình huống A: policy đã sửa nhưng một site vẫn cấp quyền cũ

**Bối cảnh:** Tổ chức sửa chính sách API báo cáo từ “mọi Finance được export” sang “chỉ Finance Exporter được phê duyệt”. Bản `v20` đã merge và xuất bản. Site A chạy `v20`, site B vẫn chạy `v19` do lỗi tải artifact. Người dùng chuyển sang site B và tiếp tục export.

**Phân tích:** Source repository đã đúng, nhưng **runtime policy chưa hội tụ**. Đây là lỗi distribution/activation và giám sát, không được đóng ticket chỉ vì PR đã merge.

**Cách xử lý:**

1. Xác minh bản `v20` và artifact digest được phê duyệt.
2. Kiểm tra PDP từng site và log tải/activate.
3. Nếu quyền export không được tiếp tục ở site B, áp biện pháp chặn phù hợp tại PEP/API trong khi sửa distribution.
4. Đồng bộ site B qua kênh tin cậy; không tắt kiểm artifact integrity.
5. Chạy lại request **PERMIT** cho Finance Exporter đúng scope và **DENY** cho người không được phép ở cả hai site.
6. Readback version và hành vi tại tất cả target bắt buộc.
7. Ghi lý do drift, owner và cải tiến monitor activation.

**Bài học:** **Phiên bản trong repository ≠ phiên bản đang thực thi**.

## 26. Thực hành tình huống B: Leaver vẫn được PERMIT dù policy không đổi

**Bối cảnh:** Policy `v24` có rule `engagementStatus == ACTIVE`. Contractor Bình kết thúc hợp đồng lúc 18:00. HR/VMS đã phát Leaver, nhưng PIP ở một service vẫn cache `ACTIVE`. PDP dùng `v24` và trả PERMIT cho request lúc 18:07.

**Phân tích:** Policy source và runtime version có thể hoàn toàn giống nhau, nhưng **thuộc tính đầu vào lỗi thời**. Repo đúng không tự bảo vệ nếu policy engine được đưa dữ liệu sai.

**Cách xử lý:**

1. Truy vết event Leaver, mốc hiệu lực và tình trạng đồng bộ tại IAM/PIP.
2. Đánh giá độ trễ cache và giới hạn freshness của trạng thái engagement.
3. Nếu trạng thái không thể xác minh, áp **deny/degraded mode** theo rủi ro và policy.
4. Thu hồi phiên/token, account/role ở IdP/SCIM/app khi cần.
5. Đối soát lại request từ contractor phải bị từ chối tại API.
6. Bổ sung test và monitoring cho **Leaver event → PIP state → PDP decision → PEP enforcement**.

**Bài học:** **Độ mới của identity data cũng quan trọng như version của policy**.

## 27. Thực hành tình huống C: cập nhật policy làm mất chặn tenant

**Bối cảnh:** Một lập trình viên tối ưu rule, bỏ điều kiện `subject.tenantId == resource.tenantId` vì nghĩ rằng middleware đã kiểm tenant. Unit test chỉ kiểm người cùng tenant nên đều PASS. Sau triển khai, API có thể trả dữ liệu tenant khác qua một endpoint batch.

**Rủi ro:** **Broken Object Level Authorization (BOLA)** hoặc truy cập chéo tenant. Test thiếu nhánh DENY và PEP/đường batch không được kiểm toàn diện.

**Biện pháp:**

- Khôi phục rule/kiểm tenant ở đúng điểm kiểm soát đã thiết kế.
- Bổ sung negative tests theo subject/resource tenant khác nhau.
- Kiểm mọi endpoint, bao gồm batch/export/background path.
- Áp schema contract cho dữ liệu tenant từ nguồn backend tin cậy.
- Thêm regression gate cho **new permits** và review thay đổi policy nhạy cảm.
- Kiểm lại cả business access hợp lệ để tránh chặn nhầm.

**Bài học:** Một thay đổi một dòng có thể gây **mở quyền lớn**; code review và test phải xem **hành vi**, không chỉ cú pháp.

## 28. Thực hành tình huống D: break-glass khi PDP không khả dụng

**Bối cảnh:** Một sự cố hạ tầng làm PDP trung tâm không trả quyết định. Đội vận hành cần khôi phục hệ thống production. Có người đề xuất cho mọi request có header `X-Emergency: true` đi qua.

**Vì sao nguy hiểm?** Header do client gửi không chứng minh tình trạng khẩn cấp. Cho PERMIT rộng tạo đường bypass authorization ở thời điểm giám sát có thể đang suy giảm.

**Thiết kế phù hợp:**

- Dùng **break-glass workflow** được phê duyệt trước, giới hạn chủ thể, hành động và thời hạn.
- Có authenticator/credential và kiểm soát khẩn cấp riêng được bảo vệ.
- Chỉ cho các tác vụ thực sự cần để phục hồi dịch vụ.
- Ghi log độc lập hoặc buffer an toàn khi đường audit chính ngừng.
- Sau sự cố, rà soát mọi thao tác, thu hồi quyền/phiên khẩn cấp và đối soát.
- Không để policy khẩn cấp tồn tại vô thời hạn.

**Bài học:** Availability của repository/PDP phải được thiết kế cùng **chế độ suy giảm an toàn**, không bằng cơ chế bỏ qua policy tùy ý.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Commit policy đã merge vào repository. Có thể khẳng định các API đang dùng chính sách mới không?

**Gợi ý:** Chưa. Cần kiểm artifact đã phát hành, runtime version trên PDP và hành vi PEP/API.

**Câu 2.** Để cập nhật trạng thái Leaver cho mỗi nhân viên, có nhất thiết phải sửa policy source không?

**Gợi ý:** Thường không. Policy mô tả điều kiện eligibility; HR/VMS/IAM/PIP cập nhật trạng thái subject. Tuy nhiên cần đảm bảo freshness và thu hồi phiên/token.

**Câu 3.** Một người có role Finance Reader và MFA mạnh. Vì sao API vẫn cần kiểm tenant, project và action?

**Gợi ý:** Authentication/role chưa chứng minh quyền trên mọi tài nguyên; PBAC có thể kết hợp RBAC với ABAC/resource relationship.

**Câu 4.** PDP không truy cập được PIP, thiếu `engagementStatus`. Hệ thống nên tự gán ACTIVE để giữ tỷ lệ thành công không?

**Gợi ý:** Không. Thiếu dữ liệu cần thiết phải xử lý theo fail-safe/degraded policy đã được phê duyệt, không mặc định PERMIT.

**Câu 5.** Rollback từ `v21` sang `v19` có thể mở lại quyền export từng bị chặn ở `v20`. Làm gì?

**Gợi ý:** Review rủi ro và regression trước rollback, ưu tiên bản an toàn đã xác minh hoặc hotfix; kiểm tra hành vi quyền sau triển khai.

**Câu 6.** Policy source dùng version `v24`, PDP site B dùng `v23`. Đây là loại sai lệch gì?

**Gợi ý:** Runtime policy drift hoặc deployment convergence failure.

**Câu 7.** Quyền Admin được cấp qua Client Credentials cho một workload. Có nên dùng rule chỉ dành cho employee với trường `employeeStatus` không?

**Gợi ý:** Không. Workload có kind, owner, scope/audience, service status và credential lifecycle riêng.

**Câu 8.** Policy repository lưu toàn bộ access token để phục vụ debug có phù hợp không?

**Gợi ý:** Không. Nên ghi metadata được giảm thiểu và tham chiếu token/decision; bảo vệ secrets trong hệ thống chuyên trách.

**Câu 9.** Policy đơn giản cho phép Finance đọc mọi hóa đơn; ứng dụng chỉ kiểm route, không kiểm hóa đơn cụ thể. Rủi ro?

**Gợi ý:** BOLA/IDOR hoặc cross-tenant access. PEP phải đưa đúng resource attributes và thực thi theo đối tượng.

**Câu 10.** Có cần người phê duyệt độc lập khi policy mở quyền `production.admin`?

**Gợi ý:** Nên xét yêu cầu SoD và review bảo mật theo mức rủi ro; người viết không tự phê duyệt/triển khai nếu policy tổ chức quy định tách nhiệm vụ.

## 30. Checklist thiết kế và vận hành Policy repository

- [ ] **Phạm vi:** Policy repository quản lý tập rule nào và không quản lý dữ liệu nào?
- [ ] **Ranh giới:** Đã phân biệt repository, PAP, PDP, PEP, PIP, IAM/IGA và app owner?
- [ ] **Định danh:** Mỗi policy có ID ổn định, domain, tenant/application scope và tên dễ hiểu?
- [ ] **Metadata:** Có owner, phiên bản, lý do, trạng thái, mốc hiệu lực và nguồn phê duyệt?
- [ ] **Language/schema:** Policy được kiểm cú pháp, kiểu dữ liệu, external references và tương thích engine?
- [ ] **Phân quyền repository:** Người sửa/duyệt/release tách trách nhiệm phù hợp, phát hiện thay đổi ngoài luồng?
- [ ] **Quy tắc kết hợp:** Có default deny và cách xử lý DENY/PERMIT/INDETERMINATE nhất quán?
- [ ] **Least privilege:** Các rule không mở rộng scope, dữ liệu hoặc đặc quyền vượt mục đích?
- [ ] **RBAC/ABAC:** Role và thuộc tính đến từ nguồn tin cậy; resource/tenant được kiểm ở backend?
- [ ] **SoD:** Có test nghiệp vụ và review đặc quyền, quản trị chính sách và break-glass?
- [ ] **Test:** Có positive/negative tests, regression và kiểm hành vi thay đổi của PERMIT?
- [ ] **Build/release:** Artifact có version/digest, nguồn tải, bảo vệ toàn vẹn và workflow phê duyệt?
- [ ] **Runtime convergence:** Mọi PDP/PEP bắt buộc có version active mong muốn và không bị drift?
- [ ] **Cache/freshness:** Có giới hạn tuổi policy, attribute, decision, token/session theo rủi ro?
- [ ] **Fail-safe:** Repository/PDP/PIP outage không tự tạo bypass hoặc cho phép quyền nhạy cảm?
- [ ] **Rollback:** Có phương án khôi phục đã kiểm tra không tái mở quyền bị chặn vì lý do bảo mật?
- [ ] **Joiner:** Account, role, điều kiện engagement và mốc hiệu lực được xác minh trước PERMIT?
- [ ] **Mover:** Quyền mới được cấp, quyền cũ bị thu hồi, session/cache và nhiều engagement được xét?
- [ ] **Leaver:** Có cơ chế chặn quyền không còn căn cứ, thu hồi phiên/token và readback ở target?
- [ ] **Service account:** Policy cho workload tách người dùng, có owner, secret/key lifecycle và scope riêng?
- [ ] **API coverage:** Mọi đường tới resource đều có PEP phù hợp, tránh bypass qua batch/local APIs?
- [ ] **Decision audit:** Có policy runtime version, subject/actor, action/resource, nguồn thuộc tính và kết quả?
- [ ] **Governance:** Có certification, ownership reassignment, policy retirement và rà soát exception?
- [ ] **Bảo mật dữ liệu:** Không đặt password, private key, refresh token và dữ liệu cá nhân thừa vào repository?
- [ ] **Đối soát:** Không chỉ “policy deployed”; có bằng chứng **quyền hiệu dụng** đang đúng theo JML?

## 31. Tổng kết

**Policy repository là nền tảng quản trị vòng đời của *chính sách* trong PBAC**, không phải nơi tự động xác thực mọi người dùng, đồng bộ mọi account hay ra quyết định duy nhất cho từng request. Giá trị của nó nằm ở **định nghĩa chính sách rõ ràng, versioning, quyền sở hữu, review, kiểm thử, phát hành, phân phối và kiểm toán**.

Muốn chính sách trở thành kiểm soát truy cập có hiệu lực, phải nối **source repository → artifact được duyệt → PDP runtime → PEP/API**, đồng thời bảo đảm dữ liệu **subject/resource/engagement** từ **IdP/SSO, IAM/IGA, SCIM, RBAC/ABAC và PIP** là đáng tin cậy, đủ mới. Khi có **Joiner**, quyền ban đầu được đánh giá theo chính sách; khi **Mover**, quyền mới được cấp và quyền cũ được loại bỏ; khi **Leaver**, account, entitlement, phiên/token và đường truy cập tồn dư được xử lý có thể chứng minh. Với **service account**, chính sách phải bao phủ loại chủ thể, owner và credential riêng. **Chỉ khi policy, dữ liệu và kết quả thực thi được đối soát cùng nhau, repository mới thực sự giúp tổ chức cấp đúng quyền và giảm quyền truy cập tồn dư.**
