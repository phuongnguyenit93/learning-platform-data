# Mapping thuộc tính trong di trú IAM

> **Chương:** IAM migration  
> **Chủ đề:** Mapping thuộc tính  
> **Phạm vi:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM) theo Joiner–Mover–Leaver (JML), bao gồm xác minh danh tính, tạo tài khoản, cấp và thu hồi quyền, tích hợp IdP/SSO/SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Giải thích vì sao **mapping thuộc tính (attribute mapping)** là hợp đồng dữ liệu và kiểm soát bảo mật quan trọng khi di trú identity source, directory, IdP hoặc application.
2. Phân biệt thuộc tính định danh, thuộc tính vòng đời, thuộc tính tổ chức, thuộc tính xác thực, thuộc tính phân quyền và thuộc tính kỹ thuật.
3. Thiết kế **canonical identity model** và bảng ánh xạ nguồn–đích có thẩm quyền, kiểu dữ liệu, quy tắc chuyển đổi, kiểm tra chất lượng và người chịu trách nhiệm.
4. Xử lý đúng các trường hợp đổi email, đổi mã nhân viên, thuộc tính rỗng/không có, giá trị nhiều phần tử, ngày hiệu lực, thay đổi thứ tự sự kiện và xung đột nhiều nguồn.
5. Liên kết mapping thuộc tính với **Joiner–Mover–Leaver**, SCIM, SAML/OIDC, RBAC/ABAC, quyền trực tiếp và quản lý tài khoản phi con người.
6. Thiết kế dry-run, pilot, reconciliation, cutover, rollback, giám sát và bộ kiểm thử theo tác động truy cập thực tế.

**Câu hỏi xuyên suốt:** Khi thay HRIS-A bằng HRIS-B, thuộc tính phòng ban từ mã FIN-01 đổi thành Finance, email người dùng đổi miền và thuộc tính quản lý chuyển từ chuỗi username sang ID nội bộ. Làm thế nào để một người vẫn là cùng một danh tính, có đúng quyền hiện hành và không bị vô hiệu hóa hàng loạt khi một batch dữ liệu bị lỗi?

## 2. Mapping thuộc tính là gì?

**Attribute mapping** là quá trình mô tả và thực thi quan hệ giữa trường dữ liệu nguồn và thuộc tính đích, gồm cả ngữ nghĩa, kiểu dữ liệu, giá trị hợp lệ, quy tắc chuyển đổi, điều kiện áp dụng, nguồn có thẩm quyền và cách xử lý lỗi.

Ví dụ đơn giản:

| Nguồn HRIS-A | Canonical model | Đích SCIM/IdP | Điều cần xác minh |
|---|---|---|---|
| employee_no | canonicalPersonId hoặc source link | externalId theo hợp đồng | Mã nhân viên có thật sự ổn định/không tái sử dụng không? |
| legal_first_name | name.givenName | name.givenName | Bảo toàn Unicode, dấu và tên pháp lý |
| legal_last_name | name.familyName | name.familyName | Quy ước phân tách tên theo quốc gia |
| org_unit_code = FIN-01 | department = finance | enterprise.department | Mã nguồn và mã đích có cùng ý nghĩa quyền không? |
| supervisor_ref | managerCanonicalId | enterprise.manager.value sau khi resolve | Manager phải trỏ đúng account đích |
| employment_state | lifecycleStatus | active/disable action theo chính sách | Không đồng nhất mọi trạng thái vắng/tạm nghỉ với leaver |

Đây là ví dụ minh họa; **employee_no không mặc nhiên bằng canonicalPersonId**. Nếu nguồn thay mã nhân viên khi tái tuyển dụng hoặc sáp nhập, phải lưu bảng liên kết giữa nhiều source ID với một danh tính chuẩn đã xác minh.

### 2.1. Mapping khác copy hoặc rename field

Đổi tên cột departmentCode thành department mới giải quyết cú pháp. Mapping IAM còn phải trả lời:

- **Ngữ nghĩa:** FIN-01 là phòng Tài chính, cost center hay quyền truy cập tài chính?
- **Nguồn:** ai xác nhận giá trị đúng và khi nào có hiệu lực?
- **Tác động:** thay department có cấp hoặc thu hồi quyền RBAC/ABAC nào?
- **Trạng thái:** giá trị không có nghĩa là chưa gửi, bị xóa hay nguồn lỗi?
- **Kiểm toán:** sự kiện, rule version và người phê duyệt nào tạo ra giá trị đích?
- **Khôi phục:** nếu phải đổi về nguồn cũ, làm sao không áp lại dữ liệu và quyền đã hết hiệu lực?

### 2.2. Chuỗi xử lý có kiểm soát

~~~mermaid
flowchart LR
    S["Nguồn có thẩm quyền: HRIS, vendor, registry"] --> V["Đọc và xác minh nguồn"]
    V --> N["Chuẩn hóa kiểu và ngữ nghĩa"]
    N --> I["Resolve canonical identity"]
    I --> M["Mapping thuộc tính + phiên bản"]
    M --> P["IAM/IGA: JML và policy"]
    P --> T["IdP / Directory / SCIM / App"]
    T --> R["Đọc actual state để đối soát"]
    R --> A["Audit, drift, cảnh báo"]
    A -. "Phản hồi kiểm soát" .-> M
~~~

Dữ liệu đầu vào là bằng chứng về identity/lifecycle, còn quyết định cấp quyền phải đi qua chính sách IAM/IGA hoặc cơ chế authorization được quản trị. Mapping thuộc tính không nên tự cấp quyền tùy tiện chỉ bằng thao tác sao chép cột.

## 3. Phân loại thuộc tính trước khi xây bản đồ

Một mapping tốt bắt đầu từ việc biết mỗi trường có chức năng và độ nhạy ra sao.

| Nhóm thuộc tính | Ví dụ | Rủi ro khi sai |
|---|---|---|
| **Định danh bền vững** | canonicalPersonId, sourceSystem + sourceId | Link nhầm người, tạo duplicate, mất lịch sử |
| **Tên/liên hệ** | displayName, legalName, preferredName, email, phone | Hiển thị sai, gửi thông báo nhầm, dùng email làm khóa không an toàn |
| **Tổ chức** | department, costCenter, manager, location | ABAC/RBAC cấp sai nhóm, phân quyền sai dữ liệu |
| **Vòng đời** | startDate, endDate, employmentStatus, contractorExpiry | Cấp quyền sớm, giữ quyền sau khi nghỉ, mass deprovision |
| **Tư cách/chủ sở hữu** | employee, contractor, guest, vendor, sponsor | Dùng nhầm nguồn có thẩm quyền, không quản lý thời hạn |
| **Xác thực/federation** | directoryObjectId, OIDC issuer + sub, SAML NameID | SSO nhận thành user mới, không link được account |
| **Quyền được quản trị** | businessRole, entitlement, approvedException | Tích lũy đặc quyền, vi phạm SoD |
| **Tài khoản kỹ thuật** | appAccountId, SCIM id, externalId, group ID | Cập nhật nhầm resource hoặc tạo trùng |
| **Tài khoản phi con người** | workloadId, ownerPersonId, credentialExpiry | Tài khoản vô chủ, quyền máy tồn dư |
| **Kiểm toán/nguồn gốc** | eventId, sourceVersion, effectiveAt, mappingVersion | Không truy vết và khó replay/rollback |
| **Dữ liệu nhạy cảm** | một số trường HR, thông tin cá nhân riêng tư | Lộ dữ liệu qua claim/log hoặc lưu quá lâu |

**Quy tắc thiết kế:** mọi thuộc tính dùng để xác định một người, cấp/thu hồi quyền hoặc ra quyết định bảo mật cần có định nghĩa ngữ nghĩa, owner, validation và độ tin cậy rõ ràng. Không nhất thiết đồng bộ toàn bộ thuộc tính HR đến mọi ứng dụng.

## 4. Nguồn có thẩm quyền và sở hữu từng thuộc tính

Một hệ thống không nhất thiết là nguồn chân lý cho tất cả thuộc tính.

| Thuộc tính | Nguồn có thẩm quyền điển hình | Quy tắc khi di trú |
|---|---|---|
| Trạng thái lao động, ngày vào/nghỉ | HRIS cho nhân viên | Chỉ chuyển authority sau khi xác minh event và reconciliation |
| Ngày hết hạn hợp đồng nhà thầu | Vendor/contractor management | Không lấy từ HRIS nhân viên nếu không có dữ liệu |
| Canonical person ID | Identity registry/IAM | Bất biến; lưu source links cũ và mới |
| Department, cost center, manager | HRIS hoặc nguồn tổ chức được chỉ định | Ánh xạ mã và reference trước khi tính quyền |
| Email chính, tên đăng nhập | Quy trình directory/email được quản trị | Không dùng email làm bằng chứng link duy nhất |
| MFA enrollment, authenticator | IdP | Không suy từ trường HR hoặc giả định chuyển được secret |
| Role nền tảng và quyền được duyệt | IAM/IGA, entitlement owner | Derived từ chính sách/approval; kiểm tra quyền thực tế |
| Role ứng dụng đặc thù | Owner ứng dụng hoặc IAM theo hợp đồng | Xác định một writer và nguồn phê duyệt |
| Tài khoản dịch vụ/owner | Workload/service identity registry | Có owner độc lập HRIS, bảo đảm handover |

Cần ma trận **attribute-level authority**, không chỉ ma trận “hệ A là master, hệ B là slave”. Một hệ có thể có thẩm quyền về department, nhưng không có thẩm quyền tự thay MFA, admin role hoặc credential.

### 4.1. Single writer theo giai đoạn

Ví dụ chuyển từ HRIS-A sang HRIS-B:

| Giai đoạn | Ai được ghi department chuẩn? | Ai ghi quyền ở ứng dụng? | Điều cần bảo vệ |
|---|---|---|---|
| Trước cutover | Luồng HRIS-A đã kiểm chứng | IAM/IGA hoặc connector được ủy quyền | Baseline có audit |
| Shadow/pilot | HRIS-A vẫn quyết định | Writer production hiện hành | HRIS-B chỉ so sánh/dry-run |
| Cutover từng cohort | HRIS-B cho cohort đã phê duyệt | Vẫn một writer được điều phối | Chống đồng bộ vòng lặp và split-brain |
| Sau cutover | HRIS-B chính thức | Writer mới/theo kiến trúc đích | Dừng write quyền từ nguồn cũ |

Nếu nguồn cũ và mới cùng ghi một trường mà không có ownership, quy tắc last-write-wins theo thời gian nhận có thể làm đảo ngược quyết định cấp quyền hoặc hồi sinh quyền của người đã nghỉ.

## 5. Canonical identity và mapping khóa ổn định

### 5.1. Khóa định danh có phạm vi khác nhau

| Khóa | Phạm vi | Điểm cần lưu ý |
|---|---|---|
| **Canonical person ID** | Một chủ thể được xác minh trong identity registry | Không đổi theo email, phòng ban hoặc HRIS |
| **Source ID** | Bản ghi tại từng hệ HRIS/contractor | Định danh theo cặp system + sourceId; có thể đổi khi đổi nguồn |
| **Directory object ID/GUID** | Object trong directory/tenant | Có thể thay nếu tái tạo account |
| **OIDC issuer + sub** | Chủ thể theo issuer OIDC | Cặp khóa phù hợp cho RP; sub có thể pairwise theo client |
| **SAML NameID và issuer/context** | Subject trong một federation trust | Không mặc định bền vững nếu đổi format/IdP |
| **SCIM id** | Resource do service provider quản lý | Không tự đồng nhất với HRIS/IdP object ID |
| **SCIM externalId** | Khóa liên kết do provisioning client chỉ định | Cần hợp đồng rõ và xác minh hỗ trợ ở đích |
| **Application account ID** | Tài khoản tại ứng dụng | Dùng cho record ownership, quyền cục bộ và audit |
| **Email/UPN** | Liên hệ/đăng nhập | Có thể đổi và tái sử dụng, không làm khóa matching duy nhất |

Lưu bảng **identity crosswalk** giữa canonical ID và các ID phụ, có loại danh tính, phạm vi tenant, thời gian hiệu lực, bằng chứng và người duyệt. Không tự merge hai người chỉ vì giống email/họ tên.

Ví dụ mô hình liên kết:

~~~yaml
canonicalPersonId: person-1042
subjectType: employee
sourceLinks:
  - system: hris-a
    sourceId: E00042
  - system: hris-b
    sourceId: W09213
directoryLinks:
  - system: corporate-directory
    objectId: obj-7001
appAccounts:
  - system: crm
    appAccountId: crm-4411
mappingReview:
  evidence: verified-hr-person-crosswalk
  approvedBy: identity-steward
  version: 8
~~~

Đây là **schema minh họa**, không phải API chuẩn. Mục đích là giữ identity continuity khi ID nguồn hoặc app ID đổi.

### 5.2. Các tình huống matching khó

- Người đổi họ tên/email: cùng người, cần cập nhật thuộc tính liên hệ.
- Email tái sử dụng: không được link với hồ sơ của người tiền nhiệm.
- Nhân viên nghỉ rồi quay lại: xác minh lại danh tính và áp chính sách rejoiner, không tự phục hồi quyền cũ.
- Nhà thầu trở thành nhân viên: có thể cùng canonical subject nhưng tư cách/authority khác.
- Hai tổ chức sáp nhập: source ID, employee number và username có thể trùng giữa namespace.
- Nhiều account có chủ đích: account user thường, admin riêng, guest hoặc nhiều tenant.
- Account cũ không có owner: phải phân loại orphan hay workload identity trước khi xử lý.

Các trường hợp một source ID khớp nhiều canonical ID, hai source ID nghi là cùng người nhưng chưa đủ bằng chứng, hoặc một app account được nhiều người nhận nên vào **quarantine** để identity steward xác minh. Link và merge không tương đương: merge có thể ảnh hưởng lịch sử quyền và dữ liệu, cần kiểm soát chặt hơn.

## 6. Thiết kế hợp đồng mapping thuộc tính

Không nên duy trì quy tắc chuyển đổi chỉ trong code hoặc bảng Excel không có version. Mỗi mapping cần mô tả đủ để vận hành, kiểm thử và kiểm toán.

### 6.1. Cấu trúc một mapping contract

| Thuộc tính hợp đồng | Câu hỏi phải trả lời |
|---|---|
| sourceSystem, sourcePath | Dữ liệu đến từ đâu, trường nào? |
| targetPath, targetSchema | Ghi vào thuộc tính nào, dạng dữ liệu nào? |
| semanticDefinition | Trường có ý nghĩa nghiệp vụ gì? |
| authority, writer | Hệ nào có quyền quyết định và ghi? |
| datatype, cardinality | String, enum, date, boolean, reference, list? |
| transformation, lookupVersion | Rename, parse, normalize, code map, join, split? |
| null/absent policy | Thiếu field có khác lệnh xóa không? |
| validation | Unique, format, referential, allowed values, date range? |
| effectiveTime, precedence | Khi nào giá trị có hiệu lực, xử lý xung đột ra sao? |
| sensitivity, targetScope | PII nào được phép xuống directory/IdP/token/app? |
| failureAction | Reject, hold, quarantine, ticket hay retry? |
| owner, approver, version | Ai chịu trách nhiệm và phê duyệt thay đổi? |
| audit/reconciliation | Log và kiểm tra tính đúng đắn thế nào? |

### 6.2. Ví dụ hợp đồng YAML

~~~yaml
mappingId: employee-department-v3
version: 3
source:
  system: hris-b
  path: employment.orgUnitCode
  authoritativeFor: employee.department
target:
  canonicalPath: person.department
  type: string
transformation:
  kind: dictionaryLookup
  tableVersion: org-unit-map-2026-11
  examples:
    FIN-01: finance
    OPS-02: operations
validation:
  requiredForAccessPolicy: true
  unknownValueAction: quarantine
nullPolicy:
  absentField: preserveCurrentPendingVerification
  explicitClear: requireAuthorizedEvent
accessImpact:
  recalculate: [businessRole, applicationGroup]
governance:
  ownerRole: hr-data-steward
  approverRole: iam-policy-owner
  auditRequired: true
~~~

**Lưu ý:** Đây là DSL minh họa giúp mô tả hợp đồng; các tên trường và action không phải schema có sẵn của một IdP/SCIM provider. Triển khai thật phải viết bộ thực thi, bộ kiểm thử và quy tắc duyệt tương ứng.

### 6.3. Version và thay đổi hợp đồng

Cần version riêng cho:

- **Schema version:** cấu trúc/trường dữ liệu.
- **Mapping rule version:** logic chuyển đổi và độ ưu tiên.
- **Lookup table version:** bảng mã phòng ban, địa điểm, job title.
- **Policy version:** quyết định quyền từ thuộc tính.
- **Identity crosswalk version:** liên kết chủ thể/tài khoản.

Ví dụ, đổi FIN-01 → finance ở mapping version 3 và thay role finance ở policy version 11 là **hai quyết định khác nhau**. Audit phải cho phép giải thích cả hai.

## 7. Các phép biến đổi thuộc tính thường gặp

### 7.1. Rename và chuyển đổi kiểu

Ví dụ source trường joinedAt dạng chuỗi thời gian, đích yêu cầu timestamp. Phải parse hợp lệ, kiểm tra offset/timezone, không dùng so sánh chuỗi tùy tiện. Với mã như "00123", không chuyển sang số nguyên nếu số 0 đầu là thành phần định danh. Boolean true/false cũng không đồng nghĩa chuỗi "true"/"false" khi schema đích phân biệt kiểu.

### 7.2. Chuẩn hóa giá trị nhưng giữ nguyên ý nghĩa

Ví dụ:

| Giá trị nguồn | Canonical | Tác động |
|---|---|---|
| FIN-01 | finance | Tính role theo department |
| finance_dept | finance | Cùng ngữ nghĩa nếu owner xác nhận |
| VN-HCM | VN-HCM | Location chuẩn cho ABAC nếu đã định nghĩa |
| ACTIVE, employed | active | Trạng thái lao động có hiệu lực |
| ENDED, terminated | terminated | Sự kiện leaver có bằng chứng |
| ON_LEAVE | leave_of_absence | Không tự quy thành leaver |
| UNKNOWN | unknown/hold | Không mặc định active hoặc terminated |

Lookup table cần được owner nghiệp vụ phê duyệt. Không biến giá trị lạ thành một role mặc định mạnh; nếu department chưa rõ mà điều kiện ABAC yêu cầu, **tạm chặn quyết định cấp quyền phụ thuộc thuộc tính đó và đưa vào xử lý**, đồng thời bảo đảm không gây mass disable do lỗi nguồn.

### 7.3. Chia và ghép trường

- fullName → givenName/familyName không luôn chính xác ở mọi nền văn hóa; nếu không có cấu trúc nguồn đáng tin, tránh suy đoán tên pháp lý.
- fullAddress → các trường địa chỉ có thể mất dữ liệu nếu parser không hiểu format vùng.
- emailAliases → danh sách địa chỉ cần xác định primary/verified/type.
- managerUsername → managerCanonicalId cần resolve account thật, không chỉ copy chuỗi.
- department + costCenter → entitlement có thể là quyết định từ nhiều thuộc tính, nên tính qua policy engine thay vì nối chuỗi.

Nếu transformation làm mất thông tin, ghi cảnh báo và lưu dữ liệu nguồn cần thiết theo retention policy để đối soát.

### 7.4. Giá trị nhiều phần tử

Ví dụ một user có nhiều email, số điện thoại, vai trò nghiệp vụ hoặc affiliation. Phải xác định:

- List có thứ tự quan trọng hay không?
- Có trùng giá trị không, có phân biệt case không?
- Có trường primary hay type không?
- Một update là **thay toàn bộ danh sách** hay **thêm/gỡ phần tử**?
- Người dùng có thể có nhiều role hợp lệ nhưng hai role bị SoD cấm không?
- Mối quan hệ cũ phải thu hồi ra sao khi một phần tử bị gỡ?

Đặc biệt, nhóm ứng dụng có thể bị **thay toàn bộ** do một lệnh update sai thay vì chỉ remove đúng phần tử. Hãy kiểm thử semantics của vendor và dùng patch đúng đặc tả.

### 7.5. Reference và quan hệ tổ chức

Trường manager, owner, sponsor thường là **tham chiếu tới danh tính khác**. Ví dụ manager ở HRIS-B là mã W0031, nhưng SCIM extension của ứng dụng cần ID user của **service provider đích**.

Chuỗi xử lý:

1. Xác minh managerSourceId ở HRIS-B.
2. Resolve managerSourceId → canonicalPersonId từ identity registry.
3. Resolve canonicalPersonId → app/SCIM target user ID.
4. Kiểm tra người quản lý hợp lệ, không tự tham chiếu và không tạo vòng manager.
5. Chỉ cập nhật reference khi target đã tồn tại; nếu chưa thì tạm giữ và retry có kiểm soát.

Không copy manager email hoặc HRIS ID thẳng vào manager.value nếu ứng dụng mong đợi resource ID khác.

### 7.6. Ngày, giờ và effective time

**Ngày bắt đầu công việc** thường là ngày theo lịch nghiệp vụ; **timestamp tạo sự kiện** thường là thời điểm tuyệt đối. Không tự chuyển giữa date-only và instant mà không có quy tắc timezone.

Một sự kiện có thể có:

- recordedAt: lúc nguồn ghi nhận.
- emittedAt: lúc phát.
- receivedAt: lúc IAM nhận.
- effectiveAt: khi trạng thái nghiệp vụ có hiệu lực.
- version/sequence: thứ tự logic do nguồn có thẩm quyền quy định.

Quyền phải phản ánh **effective time và policy hiện hành**, không chỉ thời điểm event đến. Ví dụ leaver hiệu lực lúc 17:00 địa phương không được xử lý bằng timestamp UTC sai lệch vì bỏ qua timezone.

## 8. Ba trạng thái dữ liệu: thiếu, null và rỗng

Đây là một trong các nguyên nhân phổ biến của mass deprovision hoặc xóa nhầm thuộc tính.

| Đầu vào | Có thể mang nghĩa | Cách xử lý an toàn |
|---|---|---|
| **Field không xuất hiện** | Partial update, nguồn chưa gửi, lỗi batch | Không tự hiểu là xóa; giữ trạng thái hoặc yêu cầu đối soát theo hợp đồng |
| **null được gửi rõ** | Có thể là ý định xóa/reset, hoặc unknown | Chỉ clear khi source và operation có thẩm quyền |
| **Chuỗi rỗng** | Giá trị không được nhập, reset hoặc dữ liệu lỗi | Validation theo trường; không đồng nhất mọi trường |
| **Danh sách rỗng** | Có thể muốn gỡ hết membership, hoặc export thiếu | Kiểm tra loại event và độ tin cậy của snapshot |
| **false** | Boolean false hợp lệ | Không dùng kiểm tra truthy khiến false bị coi là thiếu |
| **0** | Giá trị số bằng 0 hợp lệ | Không biến thành null do code mặc định |
| **Unknown/Not provided** | Thiếu bằng chứng | Không gán role đặc quyền, đưa vào xử lý |

Ví dụ, HRIS-B gửi partial update chỉ có department và manager. Nếu mapper diễn giải mọi field không xuất hiện là null rồi đặt active=false, hàng nghìn nhân viên có thể bị khóa.

Một chính sách cần phân biệt **snapshot đủ**, **delta event**, **partial PATCH**, **lệnh clear đã được phê duyệt** và **input lỗi**. Khi nguồn gặp sự cố, không được coi sự vắng mặt của user là một sự kiện leaver xác nhận.

## 9. Mapping thuộc tính với SCIM

### 9.1. Schema và resource SCIM

SCIM 2.0 có các trường phổ biến như userName, name, emails, active, externalId, groups và các extension hỗ trợ tùy service provider. Theo schema SCIM:

- **id** là resource ID do service provider cấp; ứng dụng SCIM client không nên coi nó là canonical HR ID.
- **externalId** là giá trị liên kết do phía client quản lý; phải thống nhất quy ước với target.
- **userName** là định danh người dùng được schema yêu cầu, nhưng **không mặc định là email** và không nên dùng làm canonical person ID toàn tổ chức.
- **emails** là tập giá trị có thể có type, primary; cần validation và kiểm tra khả năng target.
- **active** mô tả trạng thái hoạt động tài khoản tại SP; mapping với JML phải dựa trên policy.
- **groups/memberships** có semantics riêng; cần biết provider có quản lý qua Group resource hay user attribute.
- **Enterprise User extension** có trường department, costCenter, manager theo hỗ trợ của target; manager.value thường tham chiếu target User resource ID.

Không giả định mọi dịch vụ tuyên bố “SCIM compatible” đều hỗ trợ đầy đủ schema, PATCH filter, active disable, group membership hay extension với cùng hành vi.

### 9.2. Ví dụ payload SCIM minh họa

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "userName": "person-1042@corp.example",
  "externalId": "person-1042",
  "active": true,
  "name": {
    "givenName": "Lan",
    "familyName": "Nguyen"
  },
  "emails": [
    {
      "value": "lan.nguyen@corp.example",
      "type": "work",
      "primary": true
    }
  ],
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "department": "finance",
    "costCenter": "C101",
    "manager": {
      "value": "target-scim-user-421"
    }
  }
}
~~~

Ví dụ dùng ID và domain hư cấu. Việc chọn externalId = canonicalPersonId, dùng userName theo một format cụ thể và manager.value chỉ đúng khi schema/capability của ứng dụng đích và governance cho phép.

### 9.3. PATCH, Replace và Delete

Khi mapping sang SCIM, cần phân biệt:

- **Create** user mới và **link** user đã tồn tại.
- **Update** thuộc tính đơn, tránh tạo duplicate.
- **Add/remove** một phần tử trong multi-valued attribute.
- **Replace** toàn bộ giá trị khi đặc tả và target hỗ trợ.
- **Deactivate** user qua active hoặc API tương ứng, kiểm tra phiên/quyền thực tế.
- **Delete** nếu được phép theo retention và khả năng phục hồi; không mặc định xóa vật lý khi leaver.

Phải test idempotency, retry, rate limit, partial failure, eventual consistency và khóa duy nhất. HTTP 2xx không phải bằng chứng quyền ứng dụng đã bị thu hồi hết; còn phải kiểm tra app-local role, token và session.

## 10. Mapping thuộc tính với IdP, OIDC và SAML

### 10.1. Thuộc tính được dùng để đăng nhập và xác thực

IdP nhận thông tin từ directory/identity source theo quy tắc của sản phẩm, phát claim cho ứng dụng sau khi xác thực. Các thuộc tính trong token/assertion **không nhất thiết** giống mọi trường nguồn.

Với OIDC, **issuer + sub** mới là cặp định danh subject theo issuer; email, name, preferred_username là các claim phục vụ hiển thị/liên hệ hoặc trường hợp app quy định. Không auto-link tài khoản chỉ vì email trùng. Sub có thể được cấp theo cơ chế pairwise nên không luôn giống nhau giữa các client.

Với SAML, cần làm rõ **issuer, NameID format/value, audience, attribute statement và SP mapping**. NameID dạng transient không phải khóa định danh bền vững; emailAddress format không tự biến email thành bằng chứng matching an toàn.

### 10.2. Tối thiểu hóa claim

Một policy IdP có thể thêm department, group hoặc role vào token để SP thực thi quyền, nhưng chỉ nên truyền thuộc tính cần thiết. Không nhét trạng thái HR nhạy cảm hoặc dữ liệu cá nhân không cần thiết vào JWT/SAML assertion, vốn có thể được app đọc và lưu trong log.

Ví dụ:

| Claim/attribute | Nguồn phù hợp | Mục đích | Rủi ro |
|---|---|---|---|
| sub / NameID bền vững | IdP + mapping subject được quản trị | Account linking | Đổi issuer hoặc NameID tạo account mới |
| department | Thuộc tính chuẩn từ HRIS | ABAC hoặc hiển thị | Mã sai cấp nhầm quyền |
| group/role | IAM/IGA/entitlement engine | Authorization | Role cũ không bị thu hồi |
| email | Quy trình directory/email | Thông báo, hiển thị | Email tái sử dụng, trùng |
| employmentType | Nguồn HR/contractor có thẩm quyền | Policy theo tư cách | Không phân biệt contractor với employee |
| manager | HRIS + identity registry | Workflow/approval | Tham chiếu sai người dẫn đến sai phê duyệt |

**Không** biến dữ liệu đăng nhập thành nguồn tự động cấp mọi quyền. Ứng dụng có thể cần kiểm tra policy bên phía server theo ngữ cảnh tài nguyên, SoD và các ngoại lệ đã phê duyệt.

## 11. Mapping thuộc tính tới RBAC và ABAC

### 11.1. Phân biệt thuộc tính và quyền

- **Attribute:** department = finance; employmentType = employee; location = VN-HCM.
- **Policy:** nhân viên phòng Finance được đề xuất quyền xem báo cáo tài chính khi đáp ứng điều kiện khác.
- **Entitlement:** quyền cụ thể đã được cấp trong ứng dụng đích.
- **Actual access:** ứng dụng thật sự cho phép đọc/sửa/xuất tài nguyên nào.

Mapping department từ FIN-01 sang finance chưa chứng minh quyền đúng. Policy phải được tính lại; role/entitlement phải được provision và đối soát tại ứng dụng.

### 11.2. Chính sách minh họa

~~~text
IF person.lifecycleStatus == active
AND person.employmentType == employee
AND person.department == finance
AND request.resource.classification <= allowedClassification
AND separationOfDutiesCheck(person, requestedRole) == PASS
THEN roleCandidate = finance_reader
ELSE roleCandidate = none
~~~

Đây là mã giả, không phải cú pháp của một policy engine. Tổ chức cần định nghĩa quyền dữ liệu và điều kiện cụ thể theo nghiệp vụ.

Nếu department không xác định do lỗi mapping, không nên tự gán finance_reader hoặc admin. Có thể giữ account được xác minh với quyền cơ bản đã phê duyệt, **tạm dừng cấp quyền phụ thuộc thuộc tính thiếu** và đưa vào hàng đợi kiểm tra. Khi sự kiện leaver hợp lệ đã được xác minh, quy trình thu hồi ưu tiên không được bị trì hoãn vô cớ vì một thuộc tính ít quan trọng đang thiếu.

### 11.3. Mapping role cũ và mới

Các role có cùng tên nhưng khác phạm vi cần được giải thích theo ngữ nghĩa:

| Thuộc tính / role nguồn | Đích đề xuất | Yêu cầu bổ sung |
|---|---|---|
| department = FIN-01 | department = finance | Bảng mã được HR/owner duyệt |
| role = MANAGER | role = team_manager | Xác định team scope, không tự mở toàn tenant |
| location = HCM | location = VN-HCM | Chuẩn hóa location code |
| jobLevel = 5 | privilegedActionEligible = false/true theo policy | Không gán trực tiếp admin từ số cấp bậc |
| isContractor = true | employmentType = contractor | Có expiry và owner tổ chức |
| managerId = HR-92 | managerCanonicalId = person-0092 | Resolve qua crosswalk trước approval |

Direct grant và role cục bộ không đi qua thuộc tính nguồn cần được kiểm kê riêng. Dùng **desired/actual reconciliation** để thu hồi quyền cũ và kiểm tra phân tách nhiệm vụ (SoD).

## 12. Mapping thuộc tính qua vòng đời Joiner–Mover–Leaver

### 12.1. Joiner: chuẩn bị khác kích hoạt

Một người có hồ sơ HR trước ngày vào làm. Mapping phải giữ rõ:

- canonical identity đã xác minh;
- nguồn và ngày bắt đầu có hiệu lực;
- trạng thái chuẩn bị account và trạng thái cho phép đăng nhập;
- role mặc định tối thiểu theo policy và approval;
- MFA enrollment và account liên kết đúng ứng dụng.

Không suy ra active chỉ vì bản ghi đã xuất hiện. Với joiner có ngày trong tương lai, có thể tạo account phục vụ chuẩn bị nhưng cấp quyền/khả năng đăng nhập phải theo chính sách tại thời điểm hiệu lực.

### 12.2. Mover: thuộc tính đổi thì quyền cũ cũng phải giảm

Ví dụ nhân viên chuyển từ FIN-01 sang OPS-02. Sự kiện cần đổi department, có thể đổi manager, cost center, approver và RBAC/ABAC. Điều quan trọng là **revoke quyền Finance cũ** đã hết lý do, kể cả direct grant ngoài IdP group.

Nếu cần giữ quyền giai đoạn bàn giao, ngoại lệ phải có approver, owner, phạm vi và ngày hết hạn. Không map cả giá trị department cũ lẫn mới thành danh sách cố định rồi để tồn tại vô hạn.

### 12.3. Leaver: thông tin nguồn phải đủ tin cậy

Một sự kiện nghỉ việc hợp lệ có thể có employmentStatus = terminated và effectiveAt được HR xác nhận. Khi đó IAM phải:

1. Ngừng đường đăng nhập đang áp dụng (IdP, directory, local app nếu có).
2. Deactivate hoặc revoke account/entitlement ở ứng dụng liên quan.
3. Xử lý refresh token, API key, session và quyền trực tiếp theo khả năng hệ thống.
4. Thu hồi privileged access và bàn giao ownership dữ liệu/tài khoản dịch vụ.
5. Đối soát actual state, đo thời gian thu hồi so với SLA.

**Không** suy ra leaver chỉ từ việc user vắng khỏi bản export hoặc trường status biến mất. Với snapshot không đầy đủ, phải tạm dừng bulk deprovision và xác minh nguồn.

### 12.4. Rejoiner, contractor và leave of absence

- **Rejoiner:** xác minh lại cùng chủ thể, kiểm tra source link và chỉ cấp quyền từ trạng thái hiện tại, không tự hồi sinh role cũ.
- **Contractor:** dùng nguồn hợp đồng có thẩm quyền; expiry phải được quản trị ngay cả khi HRIS nhân viên không chứa bản ghi.
- **Leave of absence:** giữ phân biệt với terminated; quy tắc hạn chế/khôi phục do chính sách tổ chức quyết định.
- **External/guest:** xác định sponsor, owner và thời hạn; không gộp danh tính đối tác với nhân viên theo email.
- **Non-human identity:** nguồn owner và trạng thái workload có thể nằm ở service registry, không bắt nguồn từ HRIS.

## 13. Event ordering, xung đột và đồng bộ hai chiều

### 13.1. Đừng dùng last-write-wins thiếu ngữ cảnh

Các sự kiện có thể bị trễ, lặp hoặc đến sai thứ tự. Ví dụ:

- 10:00 HR phát mover, effectiveAt 09:00.
- 10:05 HR phát leaver, effectiveAt 10:05.
- 10:07 một retry cũ của mover mới đến IAM.

Nếu dùng last-write-wins theo receivedAt, hệ thống có thể đổi người đã nghỉ thành active hoặc gán lại quyền.

Hãy sử dụng **source event version / sequence, effective time, trạng thái hiện hành, quy tắc sửa hồi tố và idempotency** phù hợp hợp đồng. Một event không rõ phiên bản cần được kiểm tra qua snapshot nguồn đáng tin thay vì mù quáng áp dụng.

### 13.2. Xử lý multi-source

Nếu hai nguồn cung cấp cùng một trường:

- Định nghĩa authority theo loại identity: employee thuộc HRIS, contractor thuộc hệ quản lý đối tác.
- Định nghĩa authority theo thuộc tính: email do hệ email/directory, MFA do IdP.
- Định nghĩa ownership theo giai đoạn: HRIS-A trước cutover, HRIS-B sau cutover cho cohort đã phê duyệt.
- Có quy trình xung đột và exception, không tự cho nguồn mới ghi đè mọi trường.

**Ví dụ:** HRIS-B gửi manager mới nhưng ứng dụng giữ manager cũ vì direct edit. Nếu manager là thuộc tính có thẩm quyền từ HRIS, IAM cần reconcile và sửa writer/connector gây drift; nếu ứng dụng được ủy quyền riêng cho role approval thì phải mô tả khác biệt đó trong contract.

### 13.3. Đồng bộ tới nhiều đích

Một thuộc tính department chuẩn có thể dẫn tới cập nhật directory, IdP claims và ba ứng dụng. Không đồng nghĩa phải hoàn tất mọi đích trong cùng một transaction phân tán. Thiết kế nên ghi rõ:

- Desired state duy nhất theo identity.
- Event ID/version cho mỗi thao tác.
- Retry/backoff, dead-letter queue hoặc ticket cho lỗi.
- Idempotency tránh tạo account/role lặp.
- Phát hiện drift khi target không cập nhật.
- SLA cho từng đích và phản ứng khi quyền đặc quyền sai.
- Quy trình pause writer khi thay đổi bất thường.

## 14. Validation và chất lượng dữ liệu

### 14.1. Kiểm tra trước khi phát sự kiện tới đích

| Nhóm kiểm tra | Ví dụ |
|---|---|
| **Schema/type** | Timestamp hợp lệ, boolean đúng kiểu, list có phần tử đúng dạng |
| **Completeness** | Trường bắt buộc cho identity/account/policy có mặt |
| **Uniqueness** | Cặp system + sourceId trỏ một canonical ID |
| **Referential integrity** | Manager, sponsor, owner, cost center tham chiếu thực thể hợp lệ |
| **Allowed value** | department trong danh mục mã đã duyệt |
| **Temporal consistency** | endDate không sai bất thường trước startDate; effectiveAt có ngữ cảnh timezone |
| **Policy coherence** | Contractor có expiry/sponsor; admin role qua phê duyệt |
| **Cross-field** | terminated và active app account cần hành động thu hồi |
| **Delta sanity** | Không đột ngột mất phần lớn user vì batch thiếu dữ liệu |
| **Privacy** | Chỉ truyền thuộc tính cần thiết, không đưa dữ liệu nhạy cảm vào claim/log |

### 14.2. Phân loại lỗi

- **Reject:** schema sai rõ ràng, loại dữ liệu không hợp lệ, chữ ký/nguồn sự kiện không đáng tin.
- **Quarantine:** identity mapping mơ hồ, lookup mã chưa rõ, manager không thể resolve.
- **Hold + approval:** lệnh bulk disable/grant bất thường, thay đổi nhạy cảm hoặc mapping gây tác động rộng.
- **Retry:** lỗi API, rate limit, network, eventual consistency.
- **Ticket/owner review:** quyền cục bộ tồn dư, giá trị nguồn cần sửa, ngoại lệ nghiệp vụ.

Không retry vô hạn một trường thiếu ngữ nghĩa; cũng không chuyển lỗi dữ liệu có rủi ro thành một quyền rộng để “cho hệ thống chạy”.

### 14.3. Mã giả pipeline mapping có kiểm soát

~~~text
processIdentityChange(event):
    assertTrustedSource(event)

    if event.id in processedEvents:
        return NO_OP

    person = resolveCanonicalPerson(event.sourceSystem, event.sourceId)
    if person is ambiguous:
        quarantine(event, "IDENTITY_MATCH_UNCERTAIN")
        return REVIEW_REQUIRED

    if isOlderThanAcceptedState(event, person):
        return STALE_EVENT

    changes = interpretFieldsWithTriState(
        event.fields,
        absentMeaning="UNSPECIFIED",
        nullMeaning="CONTRACT_DEFINED",
        emptyMeaning="VALIDATE_PER_ATTRIBUTE"
    )

    normalized = applyVersionedAttributeMappings(changes)
    validateTypesAndReferences(normalized)

    if containsUnknownSecurityCriticalValue(normalized):
        quarantineAffectedPolicyDecision(person, normalized)

    desiredState = calculateCurrentJmlAndAccessPolicies(
        person, normalized, approvedExceptions
    )

    if unexpectedBulkChanges(desiredState):
        pauseWriterAndRequestApproval(event)
        return HOLD

    publishIdempotentTargetOperations(person, desiredState)
    reconcileActualAgainstDesired(person)
    audit(event.id, person, mappingVersion, policyVersion, results)
~~~

Pseudocode không phải implementation production. Hệ thật cần concurrency control, xử lý transaction/queue, replay, bù trừ thất bại từng phần và giới hạn quyền service identity chạy mapping.

## 15. Chiến lược triển khai mapping khi di trú

| Chiến lược | Mô tả | Ưu điểm | Rủi ro |
|---|---|---|---|
| **Shadow mapping** | Chạy nguồn mới để tính kết quả nhưng chưa ghi production | Đo chênh lệch trước cutover | Dữ liệu staging có thể trễ, cần phân quyền |
| **Phased by cohort** | Chuyển owner/writer theo phòng ban hoặc loại identity | Giới hạn phạm vi lỗi | Cross-cohort reference, manager, group chung |
| **Phased by attribute** | Chuyển một nhóm thuộc tính trước, nhóm khác sau | Giảm phạm vi thay đổi | Dễ split authority, cần ma trận rõ |
| **Dual read, single write** | So sánh hai nguồn; chỉ một nơi được ghi đích | Dễ đối soát, ít vòng lặp | Mất cân bằng thời điểm snapshot |
| **Big-bang cutover** | Chuyển mọi mapping trong một cửa sổ | Triển khai ngắn | Lỗi tác động toàn hệ thống |
| **Parallel run** | Hai pipeline cùng tồn tại để đo kết quả | Có thời gian quan sát | Phải khóa rõ writer, tránh đồng bộ hai chiều |

Với IAM phức tạp, thường chọn **inventory → mapping contract → shadow/dry-run → pilot → chuyển từng cohort → đối soát → retire nguồn/connector cũ**. Phased theo thuộc tính chỉ an toàn khi đã phân định authority và dependency rõ, vì department, manager và role thường liên quan chặt chẽ.

## 16. Quy trình từ thiết kế đến cutover

### Giai đoạn 1 — Khảo sát và chuẩn hóa

1. Xác định identity type, nguồn có thẩm quyền, directory/IdP và ứng dụng nhận dữ liệu.
2. Lập danh mục các thuộc tính nguồn/đích: tên, kiểu, ý nghĩa, uniqueness, sensitivity, owner.
3. Xác định khóa canonical identity và bảng liên kết old/new source ID.
4. Thu thập các lookup table tổ chức, manager hierarchy, role mapping và policy dùng thuộc tính.
5. Chụp baseline số account, giá trị thuộc tính, quyền thực tế và JML latency.
6. Phân loại các thuộc tính không nên di trú vì không còn cần thiết hoặc vượt phạm vi privacy.

### Giai đoạn 2 — Xây mapping contract

1. Viết quy tắc chuyển đổi/validation và null semantics cho từng trường.
2. Chỉ định writer, source authority và policy version theo giai đoạn/cohort.
3. Xác định quy trình xử lý giá trị lạ, reference chưa resolve và conflict.
4. Lập test case gồm cả thay đổi quyền dự kiến và quyền bị từ chối.
5. Phê duyệt contract bởi data steward, IAM/IGA owner, bảo mật và owner ứng dụng liên quan.

### Giai đoạn 3 — Shadow, dry-run và pilot

Chạy cùng một tập identity qua mapper cũ và mới để so:

- Giá trị canonical và target trước/sau.
- Mapping coverage, unknown values, manager reference.
- Decision RBAC/ABAC và dự kiến grant/revoke.
- Tác động Joiner, Mover, Leaver, Rejoiner, Contractor.
- Trường hợp source thiếu, null, empty, late event, duplicate.
- Tác động khi một đích API/SCIM không khả dụng.

Pilot phải có user bình thường, admin, nhà thầu, guest, người đã đổi email, người đang chuyển bộ phận, owner service account và account có quyền trực tiếp. Chỉ mở rộng khi lỗi trọng yếu được xử lý và exception đã được owner chấp thuận.

### Giai đoạn 4 — Cutover

1. Chốt mapping/policy/lookup version và ảnh chụp baseline có kiểm soát.
2. Xác nhận go/no-go, SLA, người trực vận hành, backup và kế hoạch rollback.
3. Chuyển authority/writer theo cohort; ghi mốc event và version để bắt delta.
4. Chạy backfill đã kiểm chứng, rồi áp event thay đổi mới theo thứ tự logic.
5. Đối soát user, manager, group, role và trạng thái active tại target.
6. Kiểm tra SSO, JML, SCIM, đặc quyền và tài khoản dịch vụ quan trọng.
7. Theo dõi drift, queue, lỗi, batch-size và thực hiện pause theo guardrail nếu cần.

### Giai đoạn 5 — Ổn định và retire

Khi các cohort đạt nghiệm thu, lưu bảng crosswalk/audit theo retention, đóng quyền ghi của nguồn cũ và rotate/revoke credential connector cũ. Tiếp tục access review và kiểm chứng quyền tồn dư tại ứng dụng. Không xóa mapping/historical ID ngay sau cutover nếu còn cần điều tra hoặc rollback.

## 17. Reconciliation: desired state và actual state

**Desired state** là dữ liệu định danh và quyền người dùng **đáng lẽ phải có** theo nguồn có thẩm quyền, mapping đã duyệt, chính sách IAM/IGA và ngoại lệ hợp lệ.

**Actual state** là dữ liệu và quyền **thực tế** tại directory, IdP, SCIM provider, ứng dụng, ACL, PAM và các đường truy cập khác.

| Sai lệch phát hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| HRIS-B có người, IdP thiếu account | Mapping ID lỗi, provisioning thất bại | Retry theo khóa liên kết, tránh duplicate |
| Directory có 2 user cùng người ngoài thiết kế | Email matching/JIT/SCIM retry sai | Pause create, xác minh crosswalk/link |
| Department chuẩn sai | Lookup lỗi, mã nguồn mới | Sửa mapping có version và đánh giá impact |
| Manager trỏ user khác | Resolve theo email hoặc target ID sai | Quarantine, sửa reference, audit |
| Role Finance còn sau mover | Direct grant, source cũ, event sai thứ tự | Thu hồi và kiểm chứng actual permission |
| User leaver vẫn đăng nhập app | SCIM disable không đủ, session/token tồn dư | Revoke theo từng đích, đo SLA |
| Nhiều user bị mark terminated | Batch thiếu record, null semantics sai | Guardrail hold, xác minh nguồn |
| Role đổi đi đổi lại | Hai writer cùng ghi, loop sync | Pause connector, sửa authority và version |
| Account service thiếu owner | HR source không quản lý non-human | Cập nhật service registry, review/revoke |
| Claim chứa dữ liệu HR không cần thiết | Mapping thiếu privacy review | Giảm claim, giới hạn log và retention |

Kết quả phải được phản ánh thành ticket và audit có owner, thời hạn, mức độ ưu tiên. Không chỉ dựa vào phản hồi thành công từ API mà bỏ qua quyền thực tế ở ứng dụng.

## 18. KPI chất lượng mapping và tác động IAM

Theo dõi theo source, cohort, identity type và nhóm quyền:

- **Verified mapping coverage:** identity trong phạm vi đã có old/new ID liên kết được xác minh.
- **Attribute completeness:** tỷ lệ bản ghi có đủ trường bắt buộc theo policy; phân biệt trường tùy chọn.
- **Unknown enum rate:** tỷ lệ giá trị không ánh xạ được vào danh mục chuẩn.
- **Invalid reference rate:** tỷ lệ manager/owner/group reference không resolve được.
- **Duplicate/orphan rate:** account trùng ngoài thiết kế hoặc không có chủ thể/owner hợp lệ.
- **Attribute drift:** thuộc tính tại target khác canonical desired state.
- **Entitlement drift:** quyền thực tế khác quyền do IAM/IGA phê duyệt.
- **Provisioning success/latency:** thao tác user/group đạt trạng thái mong đợi và thời gian hoàn thành.
- **Leaver revocation latency:** thời gian từ mốc hiệu lực đến khi mọi đường truy cập trong phạm vi bị thu hồi.
- **Source and reconciliation lag:** độ trễ nhận event và xử lý chênh lệch.
- **Quarantine backlog/aging:** số ca mapping mơ hồ và thời gian chờ xác minh.
- **Bulk-change guardrail triggers:** sự kiện bất thường bị giữ để kiểm tra.

Ví dụ số liệu mô phỏng: shadow run phát hiện 17/1.000 department code không ánh xạ, 6 manager reference mơ hồ và 3 user duplicate. Không nên cho 17 người nhận role mặc định quá rộng; phải phân loại ảnh hưởng quyền và xử lý trước cohort production. Các con số này là **ví dụ**, không phải ngưỡng chuẩn.

## 19. Case study: thay HRIS đồng thời chuẩn hóa directory và SCIM

Giả sử doanh nghiệp có **1.000 nhân viên và 80 nhà thầu**. HRIS-A dùng employeeNumber, orgUnitCode và managerLogin. HRIS-B dùng workerId, departmentKey và managerWorkerId. IdP đang nhận dữ liệu qua directory, còn CRM và ERP nhận account/group qua SCIM/API.

### 19.1. Thiết kế mapping

| Thuộc tính | HRIS-A | HRIS-B | Canonical | Kiểm soát |
|---|---|---|---|---|
| Mã nguồn | E123 | W7788 | sourceLinks → person-0441 | Mapping HR xác minh |
| Email | lan@old.example | lan@new.example | preferredEmail | Không dùng làm ID chính |
| Department | FIN-01 | FINANCE | finance | Lookup có version |
| Manager | managerLogin = minh | managerWorkerId = W305 | managerCanonicalId = person-0305 | Resolve reference |
| Trạng thái | WORKING | ACTIVE | active | Phân biệt với leave of absence |
| Ngày nghỉ | yyyy-MM-dd | ISO date | employmentEndDate | Định nghĩa timezone/effective |
| Role app | nhóm cũ | policy từ thuộc tính | desired entitlement | Không copy direct grant thiếu phê duyệt |

### 19.2. Shadow và phát hiện lỗi

Trong shadow run, nhóm tìm được:

- Một số employeeNumber cũ trùng với mã của công ty mới sáp nhập. Cần khóa theo **(sourceSystem, sourceId)**.
- Một số departmentKey mới không nằm trong danh mục đã duyệt; cần owner HR xác nhận ý nghĩa trước khi tính ABAC.
- managerWorkerId của một số joiner trỏ tới manager chưa được tạo ở directory mới; cần resolve theo thứ tự/queue.
- Batch HRIS-B bỏ trường employmentStatus trong partial update; mapper cũ hiểu “không có trường” là inactive và dự kiến disable hàng loạt.

Nhóm bổ sung tri-state semantics và guardrail, chuyển mapping không rõ vào quarantine. Đồng thời kiểm thử giá trị department chuẩn đến IdP claim/SCIM group và **quyền thật** ở CRM/ERP.

### 19.3. Ba ca JML

**Joiner:** Nhân viên mới có startDate vào tuần sau. IAM tạo canonical identity và chuẩn bị account nhưng chỉ kích hoạt quyền theo effective date đã được xác minh.

**Mover:** Nhân viên từ Finance chuyển sang Procurement. Lookup department thay đổi, IAM tính lại RBAC/ABAC; quyền Finance cũ, direct grant và SoD được đối soát, không tích lũy vô hạn.

**Leaver:** Một nhà thầu hết hợp đồng được nguồn vendor management xác nhận. HRIS-B không chứa nhà thầu này, nhưng IAM vẫn phải chặn IdP/ứng dụng và token liên quan đúng SLA; ownership của bot do người đó quản lý được bàn giao riêng.

### 19.4. Cutover và nghiệm thu

Nhóm chuyển từng cohort, chỉ chấp nhận khi canonical ID, mapping field, manager, group, quyền thực tế, JML và audit đạt tiêu chí. Một sự kiện mover đến muộn sau leaver không được mở lại role cũ vì pipeline kiểm tra version/state. Khi ổn định, credential connector cũ được thu hồi theo kế hoạch.

**Bài học:** Thành công của attribute mapping không được đo bằng “100% cột dữ liệu đã copy”, mà bằng **identity continuity**, **quyết định quyền đúng** và **lifecycle correctness** có thể kiểm chứng.

## 20. Bộ kiểm thử bắt buộc

| Mã | Đầu vào / tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | HRIS-A/B dùng source ID khác cho cùng người | Link đúng canonical ID, không tạo user mới |
| T02 | Hai người trùng email/tên | Không tự merge; quarantine |
| T03 | Email user thay đổi | Giữ identity và app account, cập nhật thuộc tính liên hệ |
| T04 | Mã department FIN-01 → FINANCE | Chuẩn hóa finance, policy tính đúng |
| T05 | Department code không có trong lookup | Không cấp role theo giả định; có cảnh báo/owner |
| T06 | Manager ID chưa resolve | Không map nhầm; retry/quarantine reference |
| T07 | Manager trỏ chính mình hoặc tạo vòng | Validation chặn/đưa vào review |
| T08 | Partial update thiếu employmentStatus | Không tự disable user |
| T09 | Explicit null trên field quan trọng | Chỉ clear theo contract và nguồn có thẩm quyền |
| T10 | Boolean false hoặc số 0 hợp lệ | Không bị bỏ qua như trường thiếu |
| T11 | Multi-valued emails có primary | Chọn/đồng bộ đúng type, không nhân bản sai |
| T12 | SCIM externalId và id khác nhau | Update đúng SP resource, không tạo duplicate |
| T13 | OIDC issuer/sub đổi nhưng email giữ | Pre-link đúng app user, không link theo email duy nhất |
| T14 | SAML NameID không bền vững | Không dùng làm canonical ID nếu không bảo đảm |
| T15 | Joiner có ngày hiệu lực tương lai | Kích hoạt/cấp quyền đúng chính sách |
| T16 | Mover đổi department và manager | Cấp role mới, thu hồi role cũ, kiểm tra SoD |
| T17 | Leaver hợp lệ | Thu hồi IdP/app/session/token đúng SLA |
| T18 | Batch HRIS rỗng do lỗi | Không mass disable; hold để xác minh |
| T19 | Event lặp và sai thứ tự | Idempotent, không hồi sinh leaver |
| T20 | Lookup/version thay đổi giữa hai đợt | Audit chỉ ra version và kết quả khác |
| T21 | Group SCIM cập nhật từng phần | Không xóa nhầm toàn bộ membership |
| T22 | App có direct grant ngoài SCIM | Reconciliation phát hiện và xử lý |
| T23 | Contractor hết hạn | Dùng nguồn vendor có thẩm quyền, không bỏ sót |
| T24 | Service account owner nghỉ việc | Có handover/rotation, không thành orphan |
| T25 | Quyền ABAC với department thiếu | Không cấp quyền rộng, có lối xử lý hợp lệ |
| T26 | User thuộc nhiều tenant/persona | Mapping giữ đúng tenant và account purpose |
| T27 | Rollback sau mover/leaver mới | Không khôi phục quyền đã bị thu hồi hợp lệ |
| T28 | Unicode tiếng Việt và mã có số 0 đầu | Không mất dấu hoặc biến đổi ID sai |
| T29 | Ngày hiệu lực gần ranh giới múi giờ | Cấp/thu hồi đúng mốc nghiệp vụ |
| T30 | SCIM/API timeout, retry hoặc lỗi một phần | Retry có kiểm soát, đối soát actual state và audit |

Mỗi ca nên lưu expected result, actual result, nguồn, mapping/policy version, cohort, user/role thử nghiệm, timestamp, correlation ID, người kiểm tra và ticket ngoại lệ. Bài kiểm thử quyền cần bao gồm cả **được phép** lẫn **bị từ chối** tại ứng dụng đích.

## 21. Cutover, rollback và an toàn dữ liệu

### 21.1. Go/no-go

Chỉ chuyển quyền ghi khi:

- Mapping contract, lookup table và identity crosswalk có version đã phê duyệt.
- Ca mơ hồ ảnh hưởng bảo mật được xử lý hoặc cô lập an toàn.
- Shadow/dry-run cho thấy tỷ lệ unknown/drift trong ngưỡng owner chấp thuận.
- Test JML, SCIM, IdP/SSO, ABAC/RBAC, privileged access và service account đạt.
- Có snapshot, delta replay, audit, cảnh báo, on-call và kế hoạch rollback đã diễn tập.
- Có bằng chứng source mới đáng tin, dữ liệu đủ và single writer rõ.

### 21.2. Khi nào phải dừng?

Một trong các dấu hiệu sau có thể kích hoạt pause/rollback theo ngưỡng đã duyệt: mapping nhầm người, role đặc quyền sai, hàng loạt account bị disable, invalid reference tăng đột biến, source batch thiếu, drift vượt mức, leaver vẫn truy cập hoặc SSO/provisioning lỗi trên ứng dụng trọng yếu.

### 21.3. Rollback không chỉ là đổi lookup về bản cũ

1. Pause writer và giữ event log, snapshot, mapping/lookup/policy version.
2. Xác định các joiner/mover/leaver, thay đổi role và ngoại lệ phát sinh sau cutover.
3. Khôi phục authority theo kế hoạch; chọn source/writer có thẩm quyền rõ.
4. Replay delta theo event ID và state hiện hành, tránh duplicate.
5. **Không** lấy snapshot quyền cũ để tự kích hoạt leaver hoặc phục hồi đặc quyền đã bị thu hồi hợp lệ.
6. Đối soát target: directory, IdP, SCIM, app-local role, token, session và service account.
7. Ghi incident, root cause, cải thiện contract/test trước khi cutover lại.

Một số thay đổi không thể đảo ngược hoàn toàn, như xóa tài khoản, hợp nhất dữ liệu, thu hồi credential hoặc thay ownership. Cần tập dượt khả năng phục hồi thật và hạn chế thao tác phá hủy trong các đợt đầu.

## 22. Quyền riêng tư, bảo mật và kiểm toán

- Chỉ đồng bộ thuộc tính cần thiết theo mục đích và quyền truy cập của từng đích.
- Không đưa password, access token, private key hoặc dữ liệu HR nhạy cảm không cần thiết vào mapping log, JWT/SAML claim hay ticket.
- Bảo vệ crosswalk và lookup có chứa PII bằng phân quyền tối thiểu, mã hóa và retention.
- Chạy connector bằng service identity có quyền tối thiểu, tách read-only shadow và production writer.
- Kiểm tra thay đổi bảng mã và chính sách bằng phê duyệt/kiểm thử phù hợp rủi ro.
- Có cơ chế access review và thu hồi credential/exception sau migration.
- Tách dữ liệu định danh cho con người với workload identity; mỗi non-human account phải có owner, purpose, expiry và review.

Audit một thay đổi thuộc tính ảnh hưởng quyền nên đủ các trường:

| Trường | Tác dụng |
|---|---|
| eventId/correlationId | Nối nguồn HR/contractor đến IAM, IdP, SCIM, app |
| canonicalPersonId, sourceId | Xác định chủ thể và bản ghi nguồn |
| attribute before/after | Biết trường nào đã thay đổi |
| sourceSystem, sourceVersion | Kiểm tra nguồn và thứ tự sự kiện |
| mapping/lookup/policy version | Giải thích vì sao giá trị hoặc quyền đổi |
| actor, approver, ticket | Ghi trách nhiệm và ngoại lệ |
| effectiveAt, processedAt, target | Phân biệt thời điểm nghiệp vụ và xử lý |
| outcome, retry, reconciliationResult | Chứng minh trạng thái đã đạt hoặc còn lỗi |

Các trường before/after cần được che hoặc hạn chế truy cập nếu chứa PII; audit không đồng nghĩa lưu mọi dữ liệu thô vô hạn.

## 23. Những anti-pattern thường gặp

**Dùng email làm primary key:** email có thể đổi hoặc được tái sử dụng. Dùng canonical ID và source links được xác minh.

**Copy field theo tên mà không hiểu ngữ nghĩa:** department có thể là mã phòng ban, cost center hoặc nhãn hiển thị. Định nghĩa semantic contract và owner.

**Bỏ qua null/absent/empty:** partial update làm xóa nhầm thuộc tính hoặc deactivate hàng loạt. Thiết kế tri-state semantics và kiểm thử batch lỗi.

**Mapping giá trị unknown sang role mặc định mạnh:** chưa biết department lại được cấp quyền rộng. Quarantine quyết định quyền phụ thuộc giá trị đó.

**Không xử lý reference:** managerId từ HRIS bị ghi thẳng vào target user ID sai. Resolve qua canonical identity và xác minh đích.

**Coi mọi user vắng khỏi export là leaver:** lỗi nguồn dẫn đến mass deprovision. Yêu cầu trạng thái nghỉ việc có thẩm quyền và bulk guardrail.

**Để nhiều writer không có authority:** giá trị department/role dao động và quyền bị cấp lại. Single writer có kiểm soát theo thuộc tính/cohort.

**Chỉ kiểm tra dữ liệu mà bỏ qua quyền:** mapped department có vẻ đúng nhưng direct grant còn tồn dư. So desired/actual access và test hành vi ứng dụng.

**Rollback bằng snapshot cũ:** hồi sinh quyền của người đã nghỉ hoặc chuyển vai trò. Replay trạng thái JML hiện hành.

**Sao chép thuộc tính HR nhạy cảm vào token:** lộ dữ liệu không cần thiết. Áp data minimization và privacy review.

## 24. Câu hỏi tự kiểm tra

1. Mapping thuộc tính khác rename field ở điểm nào?
2. Vì sao phải giữ canonicalPersonId độc lập với employeeNumber, email và OIDC sub?
3. Trong partial update, thiếu trường active có nghĩa là false hay chưa được đề cập?
4. Khi FIN-01 ở nguồn cũ và FINANCE ở nguồn mới cùng chỉ phòng Tài chính, ai xác minh giá trị chuẩn?
5. Vì sao managerWorkerId không thể tự động gán vào trường SCIM manager.value?
6. Nếu department mới không nhận diện được, IAM nên xử lý quyết định quyền phụ thuộc thuộc tính đó ra sao?
7. Khi mover đổi đơn vị, vì sao cập nhật claim nhóm mới chưa đủ?
8. Vì sao SCIM id, SCIM externalId và appAccountId không mặc định giống nhau?
9. Một batch rỗng do lỗi có được coi là lệnh chấm dứt toàn bộ nhân viên không?
10. Làm sao bảo đảm late event không khôi phục quyền của leaver?
11. Tại sao một tài khoản dịch vụ không nên phụ thuộc hoàn toàn vào HRIS người dùng?
12. Những KPI nào cùng chứng minh mapping đúng **và** quyền truy cập đúng?
13. Nếu rollback sau cutover, mapping/lookup version có giúp điều tra điều gì?
14. Vì sao phải kiểm thử quyền bị từ chối, không chỉ kiểm thử đăng nhập thành công?

**Gợi ý trả lời:** Liên hệ identity continuity, source authority, null semantics, reference resolution, JML effective time, single writer, desired/actual entitlements, kiểm toán và phục hồi.

## 25. Thuật ngữ và tài liệu nền tảng

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Attribute mapping** | Quan hệ và logic chuyển thuộc tính giữa schema nguồn/đích |
| **Canonical identity** | Mô hình danh tính chuẩn có khóa ổn định |
| **Source of authority** | Hệ thống được phép xác nhận giá trị hợp lệ |
| **Crosswalk** | Bảng liên kết ID/giá trị giữa các hệ thống |
| **Lookup table** | Bảng chuyển mã có kiểm soát và version |
| **Schema/semantic contract** | Hợp đồng kiểu dữ liệu và ý nghĩa nghiệp vụ |
| **JML** | Joiner–Mover–Leaver: vào, đổi vai trò và rời tổ chức |
| **IdP / SSO** | Nhà cung cấp danh tính / đăng nhập một lần |
| **SCIM** | Giao thức quản lý user/group giữa hệ thống |
| **RBAC / ABAC** | Phân quyền theo vai trò / thuộc tính |
| **SoD** | Separation of Duties: tách nhiệm vụ xung đột |
| **Effective time** | Thời điểm thay đổi có hiệu lực nghiệp vụ |
| **Tri-state handling** | Phân biệt không gửi, null và giá trị có mặt |
| **Idempotency** | Lặp sự kiện không gây tác động lặp ngoài ý muốn |
| **Reconciliation / drift** | Đối soát trạng thái mong muốn và sai lệch thực tế |
| **Quarantine** | Cách ly dữ liệu không đủ tin cậy để duyệt/xử lý |
| **Cutover / rollback** | Chuyển vận hành chính thức / phục hồi có kiểm soát |

Tài liệu tham khảo khi triển khai:

- **RFC 7643 — SCIM Core Schema:** thuộc tính user/group, externalId, multi-valued attributes và enterprise extension.
- **RFC 7644 — SCIM Protocol:** create/update/PATCH, search và xử lý tài nguyên.
- **OpenID Connect Core 1.0:** định danh chủ thể, issuer/sub và claims.
- **OASIS SAML 2.0 Core/Bindings:** NameID, assertion và federation attribute.
- **NIST SP 800-53:** các nguyên tắc quản lý quyền, least privilege, audit và kiểm soát truy cập.
- **Tài liệu chính thức của HRIS, IdP, directory và từng ứng dụng:** schema, semantics null/PATCH, group, manager reference, rate limit, account linking, token/session revocation và khả năng khôi phục; không giả định mọi vendor có hành vi giống nhau.

**Tiêu chí đánh giá cuối cùng:** Mapping thuộc tính được coi là thành công khi cùng một chủ thể vẫn được nhận diện nhất quán, thuộc tính chuẩn mang đúng ngữ nghĩa và nguồn gốc, các chính sách RBAC/ABAC/JML tạo ra quyền hợp lệ, quyền cũ không còn lý do được thu hồi và mọi thay đổi có bằng chứng để kiểm toán, đối soát và phục hồi.
