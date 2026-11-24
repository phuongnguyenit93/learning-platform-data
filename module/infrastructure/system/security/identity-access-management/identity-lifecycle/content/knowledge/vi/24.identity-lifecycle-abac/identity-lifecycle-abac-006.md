# Policy condition trong ABAC: điều kiện quyết định quyền truy cập theo ngữ cảnh và vòng đời danh tính

Trong **Attribute-Based Access Control (ABAC)**, **policy condition** là một biểu thức hoặc tập biểu thức quy định **khi nào một quy tắc truy cập được áp dụng hoặc cho phép một hành động** dựa trên các thuộc tính đáng tin cậy. Thay vì chỉ hỏi “người dùng giữ role nào?”, điều kiện có thể hỏi: **người dùng thuộc đơn vị nào, tài nguyên thuộc đơn vị nào, hành động gì đang được yêu cầu, mức độ nhạy cảm ra sao, tài khoản có hiệu lực không và phiên xác thực có đủ mạnh không?**

Ví dụ, một nhân viên có role `ReportReader` được phép đọc báo cáo tài chính **chỉ khi** nhân viên đang active, thuộc cùng đơn vị dữ liệu với báo cáo và báo cáo không vượt mức phân loại mà họ được ủy quyền xem. Nhân viên đó vẫn có role nhưng nếu đổi phòng ban, điều kiện có thể chuyển từ **đúng** sang **sai** mà không nhất thiết phải thay toàn bộ hệ thống role. Ngược lại, nếu nguồn thuộc tính cũ không được cập nhật, policy có thể tiếp tục cho phép truy cập trái ý định.

Bài thuộc chương **ABAC** của module **quản lý vòng đời danh tính IAM (Identity and Access Management)** theo **Joiner–Mover–Leaver (JML)**. Nội dung gắn policy condition với **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư**. Mục tiêu là biết viết điều kiện chính xác, đánh giá dữ liệu đầu vào có thẩm quyền, xử lý giá trị thiếu/lỗi, kiểm thử chính sách và xác minh rằng quyết định truy cập được thực thi tại đúng tài nguyên.

> **Nguyên tắc xuyên suốt:** Một policy condition **không phải chỉ là câu lệnh `if` có thể tùy tiện tin dữ liệu người dùng cung cấp**. Nó là một phần của quyết định authorization cần xác định **nguồn thuộc tính, kiểu dữ liệu, thời điểm hiệu lực, thứ tự phối hợp chính sách và nơi thực thi**. Đăng nhập SSO thành công không tự làm mọi condition trở thành đúng.

## 1. Policy condition là gì và đứng ở đâu?

Một yêu cầu truy cập có thể được mô hình hóa bằng bốn nhóm thông tin:

| Nhóm | Ký hiệu khái niệm | Ví dụ |
| --- | --- | --- |
| **Subject attributes** | `S` | `identityId`, `employmentStatus`, `department`, `roles`, `clearance`, `managerId`. |
| **Resource attributes** | `R` | `resource.ownerId`, `department`, `classification`, `tenantId`, `state`. |
| **Action attributes** | `A` | `read`, `update`, `approve`, `delete`, `export`. |
| **Environment/context attributes** | `E` | Thời điểm yêu cầu, trạng thái thiết bị đã kiểm chứng, mức rủi ro, mức bảo đảm MFA, network zone. |

Một policy condition thường kiểm tra một hoặc nhiều mối quan hệ giữa `S`, `R`, `A` và `E`.

~~~text
allow(subject, action, resource, environment)
  = subject.employmentStatus == "ACTIVE"
    AND action == "read"
    AND subject.department == resource.department
    AND subject.clearance >= resource.classification
    AND environment.authAssurance >= "REQUIRED_ASSURANCE"
~~~

Đây là **pseudocode khái niệm**, không phải cú pháp của một ABAC engine chuẩn. Trong triển khai thật, việc so sánh `clearance` và `classification` phải dựa trên **thứ bậc phân loại được định nghĩa rõ**, không được so sánh chuỗi bằng thứ tự chữ cái. Mức `authAssurance` cũng phải có nguồn đáng tin, giá trị có ngữ nghĩa đã thống nhất và tiêu chí theo chính sách.

### 1.1. Condition khác policy, rule và authorization decision

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Policy** | Tập quy tắc/điều kiện quản trị việc truy cập. | “Chỉ nhân viên Finance đang làm việc được xem báo cáo của đơn vị mình”. |
| **Rule / statement** | Một phần chính sách có hiệu lực áp dụng và điều kiện cụ thể. | Quy tắc cho `report:read`. |
| **Target / applicability** | Xác định rule/policy có áp dụng cho yêu cầu hay không. | Chỉ xét tài nguyên loại `FinancialReport`. |
| **Condition** | Biểu thức đánh giá dữ liệu để quyết định yêu cầu có thỏa một điều kiện. | `subject.department == resource.department`. |
| **Effect / decision** | Kết quả rule/policy theo semantics engine. | `Permit`, `Deny` hoặc trạng thái khác tùy engine. |
| **Enforcement** | Ứng dụng/gateway/API thực sự cho phép hoặc chặn hành động. | API từ chối `GET /reports/123` bằng 403 khi không có quyền. |

Trong một số ngôn ngữ chính sách, **target** và **condition** được tách riêng; trong hệ thống khác, chúng có thể cùng nằm trong một biểu thức boolean. **Không tự coi một ví dụ `allow if ...` là định nghĩa cú pháp bắt buộc cho mọi sản phẩm ABAC**.

### 1.2. Policy condition không thay thế identity proofing

Biểu thức `subject.department == "Finance"` chỉ có ý nghĩa khi `subject` đã được **liên kết đúng account với identity**, và `department` đến từ **HRIS/nguồn quản trị được phê duyệt**. Nếu client tự gửi HTTP header `X-Department: Finance` và ứng dụng tin trực tiếp, một người có thể giả mạo thuộc tính để vượt kiểm soát.

**Điều kiện đúng về mặt cú pháp nhưng dùng dữ liệu không đáng tin vẫn là một lỗi bảo mật.**

## 2. Kiến trúc đánh giá policy condition

Trong mô hình phân tách trách nhiệm thường gặp, có thể phân biệt:

| Thành phần | Tên viết tắt | Trách nhiệm |
| --- | --- | --- |
| **Policy Administration Point** | PAP | Quản lý và phê duyệt policy, version, owner. |
| **Policy Decision Point** | PDP | Đánh giá policy/condition để đưa ra authorization decision. |
| **Policy Information Point** | PIP | Cung cấp/tra cứu thuộc tính phục vụ đánh giá. |
| **Policy Enforcement Point** | PEP | Chặn yêu cầu hoặc cho hành động dựa trên quyết định được tin cậy. |

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User/Client
    participant PEP as API / PEP
    participant PDP as Policy Engine / PDP
    participant PIP as Trusted Attribute Sources / PIP
    participant DB as Resource/Data Store
    U->>PEP: GET /reports/123 + credential
    PEP->>PEP: Xác thực request và xác định subject
    PEP->>DB: Lấy metadata bảo vệ của report 123
    DB-->>PEP: tenant, department, classification
    PEP->>PDP: Subject, resource, action, environment
    PDP->>PIP: Tra nguồn thuộc tính cần thiết, policy version
    PIP-->>PDP: Employment, roles, assurance, freshness
    PDP->>PDP: Đánh giá condition và combining policy
    PDP-->>PEP: Permit / Deny / NotApplicable / Indeterminate*
    alt Quyết định được phép và đủ nghĩa vụ
        PEP->>DB: Truy vấn dữ liệu trong scope đã cho phép
        DB-->>PEP: Report được phép
        PEP-->>U: Nội dung báo cáo
    else Không được phép hoặc không thể quyết định an toàn
        PEP-->>U: 403 hoặc phản hồi an toàn thích hợp
    end
~~~

Dấu `*` lưu ý **NotApplicable/Indeterminate** là kiểu kết quả trong các mô hình như XACML; **không phải mọi ABAC engine đều dùng đúng bốn giá trị đó**. PEP phải có **quy tắc fail-safe** cho trường hợp không thể quyết định, nhất là đối với tài nguyên nhạy cảm.

### 2.1. PDP không nhất thiết là một dịch vụ từ xa

PDP có thể là:
- Thư viện policy chạy trong ứng dụng.
- Dịch vụ authorization tập trung.
- Engine phía API gateway hoặc service mesh.
- Hệ thống kiểm soát dữ liệu áp dụng ở lớp truy vấn/resource.
- Logic kết hợp nhiều lớp trong một kiến trúc lớn.

Điều quan trọng là **đơn vị nào có quyền quyết định, nó dựa trên thuộc tính nào và PEP nào bắt buộc thực thi**. Một kết quả “Permit” trong công cụ mô phỏng không có giá trị nếu endpoint thực tế bỏ qua nó.

### 2.2. Nguyên tắc default deny

Nếu không tìm thấy rule nào cho phép, hoặc hệ thống không lấy được dữ liệu thiết yếu một cách đáng tin, nhiều kiến trúc áp dụng **mặc định từ chối**. Tuy nhiên, semantics cụ thể của `Deny`, `NotApplicable` và `Indeterminate` tùy policy engine và thuật toán kết hợp.

**Không viết logic**: “nếu PDP không phản hồi thì cho phép để ứng dụng vẫn chạy”. Với quyền đặc quyền hoặc dữ liệu nhạy cảm, đây là lỗi **fail-open** nghiêm trọng. Các trường hợp cần duy trì vận hành khẩn cấp phải dùng đường **break-glass** đã được phê duyệt, có phạm vi giới hạn và kiểm toán.

## 3. Viết condition từ các thuộc tính chủ thể

Subject attributes mô tả chủ thể đang yêu cầu truy cập. Trong IAM lifecycle, những thuộc tính thường có ảnh hưởng trực tiếp gồm:

| Thuộc tính | Nguồn thẩm quyền thường gặp | Điều kiện tham khảo | Rủi ro khi cũ/sai |
| --- | --- | --- | --- |
| `identityId` | IAM identity registry | Liên kết đúng subject với account. | Nhầm hai người trùng email/username. |
| `employmentStatus` | HRIS hoặc contractor source được đồng bộ tin cậy. | `employmentStatus == ACTIVE`. | Leaver vẫn dùng được app nếu trạng thái chậm cập nhật. |
| `department` | HRIS/nguồn tổ chức. | `subject.department == resource.department`. | Mover vẫn được xem dữ liệu bộ phận cũ. |
| `businessUnit` | HRIS, hệ thống cơ cấu. | Giới hạn truy cập theo đơn vị. | Khác pháp nhân/tenant bị trộn scope. |
| `jobAssignment` | HRIS/IGA từ các assignment hiệu lực. | Kiểm tra nhiệm vụ đang có. | Bỏ sót assignment đồng thời hoặc đã hết hạn. |
| `managerId` | HRIS/nguồn quản lý. | Quan hệ quản lý theo policy. | Manager cũ còn duyệt đơn của nhân viên đã chuyển nhóm. |
| `roles` | IAM/IGA/app entitlement source. | Kiểm tra role nền tảng. | Role trực tiếp và role kế thừa không đồng bộ. |
| `clearance` | Hệ thống phân loại/ủy quyền có owner. | `clearanceLevel >= classificationLevel`. | Cấp vượt mức nhạy cảm. |
| `accountState` | IdP và ứng dụng. | Account phải active và không bị chặn. | Đăng nhập qua session cũ dù IdP disable. |
| `authAssurance` | IdP/SSO hoặc session authority. | MFA/step-up đủ mức. | Client tự khai MFA đã hoàn tất. |

### 3.1. Chức danh không phải quyền

Một condition kiểu `jobTitle == "Manager"` thường quá rộng. Chức danh có thể trùng giữa nhiều đơn vị, không biểu thị đúng phạm vi phê duyệt và có thể bị thay đổi trong HRIS không cùng thời điểm cấp quyền.

Thay vào đó, hãy xác định:
1. **Business role/assignment** nào có thẩm quyền.
2. **Đơn vị và phạm vi** nào được quản lý.
3. **Hành động** nào cần cho phép.
4. **SoD và phê duyệt** nào áp dụng.
5. **Ngày hiệu lực** nào cho phép dùng quyền.
6. **Điều kiện AuthN** nào cần có, ví dụ step-up.

### 3.2. Người có nhiều assignment

Một nhân viên có thể đồng thời làm việc cho hai dự án đã được phê duyệt. Condition đơn giản:

~~~text
subject.department == resource.department
~~~

có thể làm mất một quyền hợp lệ nếu `subject.department` chỉ ghi đơn vị chính. Trong trường hợp đó, policy có thể cần:

~~~text
exists assignment in subject.activeAssignments:
    assignment.projectId == resource.projectId
    AND assignment.effectiveFrom <= now
    AND (assignment.effectiveUntil is absent OR now < assignment.effectiveUntil)
    AND assignment.approved == true
~~~

Dữ liệu assignment phải đến từ nguồn có thẩm quyền. Không thêm “projectId hợp lệ” bằng cách tin một request parameter của client.

## 4. Viết condition từ thuộc tính tài nguyên

**Resource attributes** phải được lấy từ dữ liệu tài nguyên hoặc registry đáng tin, không chỉ từ đường dẫn mà người dùng yêu cầu.

| Thuộc tính tài nguyên | Ví dụ | Điều kiện tham khảo |
| --- | --- | --- |
| `tenantId` | `tenant-vn` | Subject và tài nguyên phải nằm trong tenant được phép. |
| `department` | `Finance` | Chỉ người cùng đơn vị/được ủy quyền mới xem. |
| `classification` | `CONFIDENTIAL` | Cần clearance phù hợp. |
| `ownerId` | `person-2048` | Cho owner thực hiện những thao tác đã phê duyệt. |
| `projectId` | `project-alpha` | User phải có assignment dự án hợp lệ. |
| `state` | `DRAFT`, `APPROVED` | Chỉ sửa tài nguyên ở trạng thái cho phép. |
| `createdBy` | ID người tạo | Dùng để kiểm tra maker–checker/SoD. |
| `legalHold` | `true` | Ngăn xóa khi có yêu cầu lưu giữ pháp lý. |
| `region` | `VN` | Giới hạn phạm vi theo chính sách lưu trữ/xử lý dữ liệu. |

### 4.1. IDOR/BOLA: condition phải ràng buộc đúng resource

Giả sử API:

~~~http
GET /api/reports/123 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Một lỗi nghiêm trọng là chỉ kiểm tra `role == ReportReader` rồi trả bất kỳ report ID nào người dùng đưa vào. **Object-level authorization** cần đọc metadata của **report 123 thực tế** và đánh giá tenant/owner/scope tương ứng. Nếu client đổi `123` thành `124` của đơn vị khác, policy phải tiếp tục chặn.

Không được chỉ dựa vào dữ liệu `resource.department` do client gửi trong JSON body. PEP cần truy xuất/kiểm tra thuộc tính từ nguồn bảo vệ thật của đối tượng.

### 4.2. Kiểm tra cả tập dữ liệu, không chỉ màn hình

Nếu API trả một danh sách:

~~~text
GET /api/reports?sort=latest
~~~

chính sách phải áp dụng cho **từng resource hoặc phạm vi truy vấn**. Chỉ kiểm tra một điều kiện chung “user có role Reader” mà không giới hạn rows có thể làm lộ báo cáo ngoài tenant/department.

Có thể thực thi bằng **query-time predicate**, row-level security hoặc lọc phía server, nhưng phải kiểm tra:
- Filter thực sự được áp dụng trước khi dữ liệu rời hệ thống.
- Phân trang, tìm kiếm, export và count/aggregate không làm lộ dữ liệu.
- Cache và background job giữ đúng scope người yêu cầu.
- Mọi endpoint tương đương áp dụng cùng một chính sách.

## 5. Condition dựa trên hành động và môi trường

### 5.1. Action không chỉ là GET/POST

HTTP method thường là tín hiệu kỹ thuật, nhưng **business action** mới là ngữ nghĩa của quyền:

| Hành động nghiệp vụ | HTTP có thể dùng | Condition đặc thù |
| --- | --- | --- |
| `report:read` | `GET` | Subject được xem tài nguyên/scope này. |
| `report:update` | `PATCH` hoặc `PUT` | Resource còn ở trạng thái được sửa. |
| `payment:create` | `POST` | Người tạo có nhiệm vụ và đơn vị hợp lệ. |
| `payment:approve` | `POST` | Người duyệt được ủy quyền, khác người tạo nếu SoD yêu cầu. |
| `data:export` | `POST`/job | Phân loại dữ liệu, mục đích và khối lượng xuất hợp lệ. |
| `identity:disable` | `PATCH`/workflow | Actor có quyền quản trị và có căn cứ IAM/JML. |

Đừng mặc định `GET` luôn chỉ đọc vô hại hoặc `POST` luôn tạo mới. Định nghĩa và enforcement action nên dựa trên **hợp đồng API và thao tác nghiệp vụ**.

### 5.2. Environment attributes

Một số điều kiện phụ thuộc:
- **Thời điểm thực tế** và lịch công việc.
- **Thiết bị** có quản lý/attestation phù hợp.
- **Network zone** theo tín hiệu hạ tầng được tin cậy.
- **Authentication assurance** từ IdP/SSO.
- **Risk level** đã được tính và chứng thực bởi hệ thống đánh giá.
- **Transaction amount** và tình trạng nghiệp vụ.
- **Emergency mode** với thủ tục riêng.

~~~text
allowExport =
    subject.active
    AND action == "data:export"
    AND subject.exportApproval.valid
    AND resource.classification <= subject.clearance
    AND environment.devicePosture == "COMPLIANT"
    AND environment.authentication.isRecentAndStrong
    AND request.exportPurpose in approvedPurposes
~~~

Các tên trường là minh họa. `request.exportPurpose` chỉ được tin sau khi đã được **phê duyệt hoặc xác thực theo workflow**; một chuỗi do người dùng tự khai “audit” chưa đủ để nâng quyền.

### 5.3. Thời gian, múi giờ và hiệu lực

Một condition thời gian cần xác định rõ:
- `effectiveFrom` bắt đầu có hiệu lực bao gồm hay không.
- `effectiveUntil` là hạn chót loại trừ hay bao gồm.
- Đồng hồ hệ thống nào được tin cậy.
- Chuyển đổi múi giờ, DST và định dạng thời gian.
- Bản ghi chấm dứt đã đến mốc hiệu lực hay chưa.

Quy ước tham khảo phổ biến là **khoảng nửa mở**:

~~~text
isActiveAt(now) =
    effectiveFrom <= now
    AND (effectiveUntil is absent OR now < effectiveUntil)
~~~

Nên so sánh các **instant đã chuẩn hóa**; không dùng so sánh chuỗi ngày giờ tùy ý khi múi giờ khác nhau. Quy tắc nghiệp vụ như “hết quyền vào cuối ngày địa phương” phải được chuyển thành thời điểm cụ thể theo lịch/múi giờ được định nghĩa và kiểm thử.

## 6. Toán tử và cấu trúc biểu thức điều kiện

Trong nhiều policy engine, condition được tạo từ phép so sánh và logic. Cú pháp cụ thể phụ thuộc ngôn ngữ chính sách, nhưng nguyên tắc mô hình hóa khá giống nhau.

| Loại | Biểu thức minh họa | Cảnh báo |
| --- | --- | --- |
| **Equals** | `subject.tenantId == resource.tenantId` | Bảo đảm cùng namespace/kiểu dữ liệu. |
| **Membership** | `"FinanceReader" in subject.roles` | Role có thể được gán trực tiếp hoặc hiệu lực qua hierarchy. |
| **Conjunction** | `condA AND condB` | Cả hai cần đúng. |
| **Disjunction** | `condA OR condB` | Một nhánh yếu có thể mở rộng quyền ngoài dự kiến. |
| **Negation** | `NOT condA` | Nếu thuộc tính thiếu/unknown, không được tự coi là `false` rồi đảo thành `true`. |
| **Ordered comparison** | `amount <= approvedLimit` | Cùng kiểu số/đơn vị tiền tệ và nguồn hạn mức. |
| **Set overlap** | `intersects(user.projects, resource.allowedProjects)` | Cần điều kiện membership có hiệu lực/được phê duyệt. |
| **Existential** | `exists activeAssignment matching resource.projectId` | Giải quyết danh sách nhiều assignment. |
| **Temporal** | `start <= now < end` | So sánh instant, xử lý hết hạn đúng. |
| **Relationship** | `subject.id == resource.createdBy` | Tài nguyên phải có owner/creator đáng tin, đã xác minh. |

### 6.1. `AND` và `OR` có thể tạo lỗ hổng nếu thiếu ngoặc

Mục tiêu: chỉ cho người dùng **active** đọc báo cáo khi họ là owner **hoặc** thuộc đơn vị được duyệt.

~~~text
# Có thể sai nếu AND/OR áp dụng ưu tiên không như người viết nghĩ:
active AND isOwner OR sameDepartment

# Ý định an toàn và rõ ràng hơn:
active AND (isOwner OR sameDepartment)
~~~

Nếu diễn giải biểu thức đầu thành `(active AND isOwner) OR sameDepartment`, một người đã nghỉ việc vẫn có thể được phép vì `sameDepartment` đúng từ dữ liệu cũ.

**Không phó mặc vào thứ tự ưu tiên toán tử** nếu điều kiện có nhiều loại. Viết ngoặc rõ, có test phủ các nhánh và hiểu semantics của engine.

### 6.2. `NOT` và giá trị thiếu: tránh mở quyền ngoài ý muốn

Condition như:

~~~text
NOT subject.suspended
~~~

có thể nguy hiểm nếu nguồn không trả `suspended`, thư viện biến giá trị thiếu thành `false` và `NOT false` thành `true`. Với yêu cầu cần trạng thái tin cậy, nên xác định nghĩa rõ:

~~~text
subject.suspended == false
AND subject.statusSource == trustedIdentityRegistry
AND subject.statusFreshEnough == true
~~~

Đây là pseudocode mang tính khái niệm; cách xử lý thiếu/unknown phải tuân theo contract engine. **Unknown, missing và false không tự đồng nghĩa**.

### 6.3. So sánh thứ bậc phân loại dữ liệu

Không viết:

~~~text
"SECRET" >= "CONFIDENTIAL"
~~~

theo so sánh chữ cái để đánh giá clearance. Thay vào đó cần **taxonomy có thẩm quyền**:

~~~text
CLASSIFICATION_RANK = {
  PUBLIC: 0,
  INTERNAL: 1,
  CONFIDENTIAL: 2,
  RESTRICTED: 3
}

subject.clearanceRank >= resource.classificationRank
~~~

Đây là **taxonomy minh họa**; mỗi tổ chức phải định nghĩa mức, phạm vi và yêu cầu đào tạo/ủy quyền riêng. Một số nhãn phân loại còn có **ngăn thông tin (compartments)** hoặc điều kiện mục đích truy cập, không thể giản lược thành một số nguyên duy nhất.

## 7. Nguồn thuộc tính: điều kiện tốt không thể dựa vào dữ liệu giả

Đối với mỗi trường trong condition, cần xác định **source of truth**, quy trình đồng bộ, quyền chỉnh sửa và mốc hiệu lực.

| Thuộc tính | Nguồn tốt thường gặp | Nguồn không nên tự tin |
| --- | --- | --- |
| Tình trạng lao động | HRIS/contractor master đã được IAM xác nhận. | Cookie do browser tự sửa. |
| Tenant và identity mapping | IAM identity registry và account bindings. | Email domain do người dùng tự nhập. |
| Department, cost center | HRIS/nguồn tổ chức được chỉ định. | Profile text không có owner. |
| Role, entitlement | IGA/application permission registry. | Danh sách roles trong body request. |
| Mức assurance/MFA | IdP session context được ứng dụng kiểm chứng. | HTTP header `X-MFA: true` chưa tin cậy. |
| Resource owner/tenant | Database/resource catalog có kiểm soát. | `ownerId` client gửi khi GET resource. |
| Device posture | Nguồn device management/risk engine đã kiểm chứng. | Chuỗi `compliant=true` tự khai. |
| Time | Đồng hồ tin cậy của backend. | Giờ trên máy người dùng. |
| Approval | Workflow có actor, hiệu lực, scope, audit. | Một comment “đã được duyệt” trong request. |

### 7.1. Attribute lineage

Một condition `department == resource.department` có thể “đúng” nhưng sai nếu department ở IdP là bản sao HRIS chưa cập nhật. Cần truy vết:

~~~text
HRIS employment/assignment
  -> IAM/IGA authoritative identity attributes
  -> IdP/Directory synchronization
  -> OIDC/SAML claims or PIP attribute lookup
  -> PDP decision input
  -> PEP enforcement
  -> Application readback / audit
~~~

Mỗi bước cần có **owner, cơ chế xác thực nguồn, version/thời gian cập nhật, mapping và hành vi khi đồng bộ lỗi**. Một SSO claim được ký hợp lệ chứng minh IdP đã phát hành claim theo nội dung lúc đó; nó **không tự chứng minh thuộc tính vẫn mới nhất** theo HRIS.

### 7.2. Cặp `(iss, sub)` và tài khoản đích

Trong OIDC, subject `sub` nằm trong phạm vi issuer `iss`. Đối với ứng dụng liên kết nhiều IdP/tenant, nên xác minh đúng cặp **`(iss, sub)`** hoặc account binding có ngữ nghĩa tương đương, không quyết định chỉ dựa vào email.

Ví dụ:
- IAM identity: `person-2048`.
- IdP issuer/subject: `(https://login.example.invalid/workforce, idp-sub-991)`.
- SCIM User.id tại ERP: `erp-user-88`.
- Target resource tenant: `tenant-vn`.

Policy condition `subject.tenantId == resource.tenantId` chỉ có giá trị sau khi **subject identity được liên kết đúng tenant và account của ERP**.

## 8. Kết quả đánh giá: Permit, Deny, NotApplicable, Indeterminate

Một số engine/phương pháp ABAC, nổi bật là **XACML**, biểu diễn các loại kết quả như:

| Kết quả | Diễn giải | Ví dụ |
| --- | --- | --- |
| **Permit** | Một chính sách hoặc tập quy tắc theo thuật toán kết hợp cho phép. | Đủ role, department và MFA. |
| **Deny** | Có rule/policy từ chối theo ngữ nghĩa engine. | Account disabled hoặc sai tenant. |
| **NotApplicable** | Policy/rule không áp dụng cho request. | Rule cho báo cáo không áp dụng tài nguyên payroll. |
| **Indeterminate** | Lỗi hoặc thiếu thông tin khiến không thể đánh giá hợp lệ. | Không tải được trạng thái nhân sự thiết yếu. |

**Bốn tên này là ví dụ mô hình XACML**, không phải giao diện bắt buộc của Cedar, OPA/Rego hay mọi thư viện authorization. Engine cụ thể có thể trả boolean hoặc một cấu trúc lỗi khác.

### 8.1. Từ `NotApplicable` đến default deny

Nếu tất cả rule đều không áp dụng, một hệ thống thiết kế theo default deny có thể **không cấp quyền**. Nhưng policy engine với thuật toán kết hợp khác có thể xử lý `NotApplicable` khác nhau. Cần xác định:
- Rule nào được đưa vào quyết định?
- Có rule mặc định nào áp dụng không?
- Combining algorithm là gì?
- PEP nhận những trạng thái nào?
- Có ngoại lệ/break-glass hợp lệ không?

Không viết PEP kiểu “chỉ từ chối khi nhận literal `Deny`; còn mọi giá trị khác coi là `Allow`”. `Indeterminate` phải được xử lý an toàn, không vô tình mở quyền.

### 8.2. Deny-overrides và permit-overrides

Một số engine có **policy combining algorithms** như deny-overrides hoặc permit-overrides. Ví dụ hai rule:

~~~text
Rule A: role FinanceReader -> Permit
Rule B: employmentStatus != ACTIVE -> Deny
~~~

Nếu cả hai áp dụng cho Leaver, deny-overrides có thể cho kết quả Deny; permit-overrides có thể có ngữ nghĩa khác. Không thể chỉ đọc từng rule để biết kết quả cuối.

**Tổ chức phải chọn và kiểm thử cách phối hợp** sao cho một rule “có role” không vượt qua kiểm soát bắt buộc “account phải active, đúng tenant, tài nguyên trong scope”. Với policy phức tạp, điều kiện bắt buộc nên được bảo đảm ở lớp không thể bị một permit rộng hơn vô tình bỏ qua.

## 9. Kết hợp RBAC và ABAC trong cùng quyết định

**RBAC** giúp gom quyền theo role; **ABAC** tinh chỉnh quyết định bằng dữ liệu chủ thể, tài nguyên và ngữ cảnh. Hai mô hình có thể cùng tồn tại:

~~~text
ALLOW only when:
  subject.accountActive
  AND rolePermissions(subject.roles).contains("report:read")
  AND subject.tenantId == resource.tenantId
  AND subject.department in resource.allowedDepartments
  AND authentication.assurance >= report.requiredAssurance
~~~

### 9.1. Role hierarchy không tự bỏ qua ABAC scope

Giả sử:
- `FinanceEditor >= FinanceReader`.
- `FinanceReader` có permission `report:read`.
- Lan được gán `FinanceEditor`.
- Lan thuộc `Finance-VN`, báo cáo thuộc `Finance-SG`.

Lan kế thừa `report:read`, nhưng **policy condition theo department** vẫn có thể từ chối báo cáo SG. Không được hiểu senior role là được truy cập mọi tài nguyên có cùng permission.

### 9.2. Conditional role assignment và runtime condition khác nhau

Hai cách thường gặp:

1. **Provisioning-time condition:** IAM chỉ cấp role khi người dùng có assignment hợp lệ tại thời điểm xét.
2. **Request-time condition:** ứng dụng/PDP kiểm tra điều kiện trên **mỗi yêu cầu hoặc mỗi phiên được quy định**, ngay cả khi role đã được cấp.

| Khía cạnh | Provisioning-time | Request-time |
| --- | --- | --- |
| Dữ liệu quyết định | HR/IGA state vào thời điểm cấp. | Subject/resource/context lúc truy cập. |
| Hiệu quả | Giảm số lần kiểm tra lúc runtime. | Giới hạn chính xác theo ngữ cảnh hiện tại. |
| Rủi ro | Quyền có thể còn khi HR/role đã đổi mà connector chưa xử lý. | PDP/PIP/caching có thể lỗi hoặc chậm. |
| Ví dụ | Nhân viên Finance được gán `ReportReader`. | Chỉ đọc báo cáo của đúng department và tenant. |

**Kết hợp cả hai** thường cần thiết: cấp quyền tối thiểu ở IAM, rồi enforce ngữ cảnh tại tài nguyên. Một runtime condition không làm cho việc giữ những role không còn căn cứ trở thành chấp nhận được.

### 9.3. Policy của API phải thực thi tại đường truy cập thật

Một “policy” chỉ dùng để ẩn nút trên frontend không đủ. Người dùng vẫn có thể gọi API trực tiếp. PEP phải áp dụng ở server/gateway/resource layer đáng tin cậy, bao gồm **batch, export, scheduled jobs và API phụ** tạo cùng tác động nghiệp vụ.

## 10. SoD, quan hệ nghiệp vụ và policy condition

**Segregation of Duties (SoD)** yêu cầu phân tách các trách nhiệm có thể xung đột. ABAC condition có thể kiểm tra quan hệ **ai đã tạo** và **ai đang duyệt** một giao dịch.

### 10.1. Maker–checker trên từng giao dịch

~~~text
allowApprovePayment =
    subject.hasPermission("payment:approve")
    AND subject.accountActive
    AND resource.status == "PENDING_APPROVAL"
    AND resource.createdByIdentityId != subject.identityId
    AND resource.amount <= subject.approvalLimit
    AND subject.tenantId == resource.tenantId
    AND environment.authentication.recentAndStrong
~~~

Điều kiện `createdByIdentityId != subject.identityId` nhằm ngăn **tự duyệt**. Giá trị createdBy cần được hệ thống ghi nhận khi giao dịch được tạo, không phải trường client có thể tùy ý sửa. Approval limit cần có kiểu tiền tệ/đơn vị và phạm vi rõ.

**Đây không thay thế static SoD hoặc dynamic SoD** nếu chính sách còn yêu cầu cấm nắm đồng thời những role, hoặc cấm kích hoạt chúng trong cùng phiên. Có thể cần cả **role governance** lẫn **transaction-level condition**.

### 10.2. Manager access phải có quan hệ thực tế

Condition sơ sài:

~~~text
subject.role == "Manager"
~~~

có thể cho xem hồ sơ của mọi nhân viên. Một condition phù hợp hơn có thể yêu cầu:

~~~text
subject.hasPermission("employee:review")
AND resource.employeeId in verifiedDirectOrDelegatedReports(subject.identityId)
AND resource.tenantId == subject.tenantId
AND delegation.isActiveAt(now)
~~~

Trong thực tế, chính sách cần phân biệt cấp quản lý, quan hệ trực tiếp/gián tiếp, ủy quyền có thời hạn, dữ liệu nhạy cảm và employee status. **Không dùng cây quản lý nhân sự làm quyền truy cập mặc định toàn bộ dữ liệu cấp dưới.**

## 11. Vòng đời Joiner: điều kiện khi danh tính mới được kích hoạt

Trong **Joiner**, việc có identity HRIS không có nghĩa một tài khoản đã đủ điều kiện vào mọi ứng dụng. Một số điều kiện thường cần:
- Identity đã được xác minh/bind đúng account.
- Quan hệ làm việc hoặc sponsor đã có hiệu lực.
- Account IdP/target đã được tạo và đúng trạng thái.
- MFA/authenticator enrollment đáp ứng policy.
- Role/assignment được phê duyệt, không xung đột SoD.
- Tài nguyên/tenant/scope chính xác.

~~~mermaid
flowchart TD
    HR["HRIS / sponsor: Joiner event"] --> IAM["IAM: identity verification + effective dates"]
    IAM --> IDP["IdP: account + MFA"]
    IAM --> PROV["SCIM/API provisioning"]
    IDP --> SSO["SSO: verified authentication context"]
    PROV --> TARGET["Application User/Group/Role"]
    SSO --> PDP["ABAC PDP: policy conditions"]
    TARGET --> PDP
    PDP --> PEP["API PEP: allow/deny"]
    PEP --> AUD["Readback + audit"]
~~~

### 11.1. Ví dụ điều kiện trước ngày bắt đầu

Nhân viên có `effectiveFrom = 2026-12-01T00:00:00+07:00`. Nếu truy cập ngày 25/11, condition:

~~~text
now >= effectiveFrom
AND subject.accountActive
AND subject.onboardingComplete
~~~

có thể chưa thỏa. Đây là **từ chối đúng chính sách**, không phải lỗi cần khắc phục bằng cách bỏ `effectiveFrom`. Nếu doanh nghiệp cần onboarding trước ngày làm việc, hãy định nghĩa **quyền pre-start hẹp** cho các tài nguyên cần thiết và thời hạn cụ thể, không mở toàn bộ production.

### 11.2. SCIM không tự truyền mọi attribute cần cho ABAC

**SCIM** chuẩn hóa User/Group và một số schema/extension, nhưng không bảo đảm mọi ứng dụng hỗ trợ cùng thuộc tính như clearance, device posture, risk, resource owner hay approval. Một ứng dụng cần PIP/API riêng hoặc mapping bổ sung cho condition.

Nếu `department` được đồng bộ từ HRIS qua IAM → SCIM, cần kiểm tra **target field, owner, tính cập nhật và hành vi khi đồng bộ lỗi**. Không tự mặc định một User được tạo thành công nghĩa là condition đã có đủ dữ liệu tin cậy.

## 12. Mover: policy condition giúp giảm quyền cũ nhưng không thay deprovisioning

**Mover** là chuyển bộ phận, nhiệm vụ, vị trí hoặc scope mà identity/account có thể giữ nguyên. Condition có thể điều chỉnh quyền ngay khi thuộc tính mới có hiệu lực — **nếu nguồn dữ liệu mới đến được PDP/PEP đúng lúc**.

Ví dụ:
- Lan chuyển từ `Operations` sang `Finance`.
- Trước đó được đọc dashboard Operations qua `department == resource.department`.
- Sau effectiveAt, `subject.department` đổi thành Finance.
- PDP cần từ chối dashboard Operations dù Lan còn session SSO.

### 12.1. Nguy cơ stale attributes

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HRIS
    participant IAM as IAM/IGA
    participant IDP as IdP / Claim
    participant APP as Application / PDP
    HR->>IAM: Mover: Operations -> Finance, effectiveAt
    IAM->>IDP: Cập nhật thuộc tính/nhóm có thẩm quyền
    Note over IDP,APP: Session/token cũ có thể vẫn chứa department=Operations
    APP->>APP: Nếu tin claim cũ -> có thể ALLOW sai
    IAM->>APP: Đồng bộ / invalidation / policy update
    APP->>APP: Re-evaluate với attributes hiện hành
    APP-->>HR: Đối soát quyền cũ đã bị chặn (qua audit/workflow)
~~~

Sơ đồ chỉ diễn đạt khái niệm. Không phải mọi ứng dụng đồng bộ trực tiếp thuộc tính qua IdP; có thể dùng PIP runtime, SCIM hoặc cache. Điều quan trọng là **xác định thời gian tối đa thuộc tính cũ còn hiệu lực**, cơ chế invalidation và tiêu chí hoàn tất.

### 12.2. Desired state và quyền tồn dư

Một Mover phải tính:
- **KEEP:** quyền vẫn cần theo assignment khác đang có hiệu lực.
- **REMOVE:** nhóm, role, entitlement và điều kiện không còn hợp lệ.
- **GRANT:** quyền mới đã đủ policy, approval và SoD.

**Condition từ chối sau khi department đổi là một lớp bảo vệ**, nhưng **không nên để role/SCIM group cũ tồn tại vô hạn**. Khi nhóm/role cũ còn cấp quyền qua ứng dụng không dùng cùng PDP, người dùng vẫn có thể truy cập nơi khác.

### 12.3. Multi-assignment và handover

Nếu Lan tiếp tục làm nhiệm vụ Operations có thời hạn được duyệt, condition nên kiểm tra **assignment cụ thể, scope và expiration**, thay vì gán cố định `department=Operations` lại trên hồ sơ chính. Điều này tránh làm sai HR source và giảm khả năng cấp quá nhiều quyền.

Handover cần owner, thời gian, phạm vi, SoD review và kiểm tra sau khi hết hạn. Với quyền nhạy cảm, chỉ chấp nhận overlap nếu chính sách cho phép.

## 13. Leaver: điều kiện trạng thái nhân sự và thu hồi truy cập

Khi HRIS xác nhận **Leaver** có hiệu lực, ABAC có thể có một điều kiện bắt buộc:

~~~text
subject.lifecycleStatus == "ACTIVE"
AND subject.accountEnabled == true
AND now < subject.authorizedAccessEnd
~~~

Đây là **một kiểm soát cần thiết nếu được áp dụng đúng**, nhưng **chưa đủ** để hoàn tất offboarding. Ứng dụng có thể không gọi PDP khi session đã có; token cũ có thể mang claim `ACTIVE`; local account/API key có thể độc lập IdP.

### 13.1. Những đường truy cập phải xét

| Đường truy cập | Rủi ro | Kiểm soát và bằng chứng |
| --- | --- | --- |
| **Login mới qua IdP** | Account chưa disable. | Kiểm tra IdP state, authentication denial đúng policy. |
| **Application session cũ** | Ứng dụng không re-evaluate trạng thái account. | Session revocation/re-auth và thử chặn truy cập theo khả năng. |
| **Access/refresh token** | Token hoặc refresh còn hiệu lực. | TTL, revocation/introspection/denylist khi có và resource server validation. |
| **Local account/password** | Bỏ qua SSO. | Disable/revoke ở target theo policy. |
| **Direct role/group grant** | Một số hệ thống không dùng cùng ABAC condition. | Deprovision SCIM/API/manual và readback. |
| **Privileged account** | Account phụ, admin hoặc PAM session chưa thu hồi. | Inventory/binding và quy trình privileged access riêng. |
| **API key/secret** | Đường máy–máy hoặc personal token vẫn hoạt động. | Credential inventory và revocation phù hợp. |

**Sai lầm thường gặp:** một query `GET /Users?filter=active eq false` thấy account inactive, rồi đóng ticket dù API token còn gọi được. **Trạng thái User, policy evaluation và actual access là ba bằng chứng khác nhau**.

### 13.2. Không biến sự cố dữ liệu thành cho phép truy cập

Nếu Leaver event có hiệu lực nhưng PIP không lấy được `employmentStatus`, có thể xuất hiện kết quả Indeterminate/unknown. Không để PEP suy luận “không thấy bị disabled tức là active”. Với đường quyền nhạy cảm, thiết kế phải bảo đảm **default-deny/fail-safe** khi không xác thực được điều kiện bắt buộc.

## 14. Session, IdP/SSO và độ mới của thuộc tính

**SSO** (SAML/OIDC) xác thực người dùng và có thể chuyển claim. **ABAC** dùng thuộc tính đó trong authorization, nhưng cần xem **độ mới và ngữ nghĩa claim**.

### 14.1. Token claim là một snapshot

Một OIDC ID token có thể chứa thông tin do OP phát hành cho RP tại một thời điểm. Điều đó **không đồng nghĩa claim được cập nhật sau mỗi thay đổi HRIS**. Một access token cũng có thể mang nhóm/scope snapshot cho API. Nếu resource server chấp nhận JWT tự kiểm chứng đến `exp` mà không có kiểm tra quyền runtime bổ sung, thay đổi Mover/Leaver có thể **không có hiệu lực ngay**.

Tổ chức cần xác định:
- Token/session lifetime.
- Khi nào authorization kiểm tra lại thuộc tính từ nguồn mới.
- Có introspection, revocation, cache invalidation hoặc back-channel notification không.
- Claim nào được tin cho quyết định nhạy cảm.
- Các hành động nào yêu cầu step-up hoặc kiểm tra trạng thái mới.

### 14.2. Authentication condition và authorization condition

Một IdP có thể áp **conditional access** để quyết định có cho phép login/MFA dựa trên thiết bị hoặc risk. Ứng dụng lại có **ABAC policy condition** để quyết định có cho xem báo cáo hay phê duyệt thanh toán. Hai lớp liên quan nhưng không thay thế nhau.

Ví dụ:
- IdP đã xác thực thành công bằng phishing-resistant MFA.
- User thuộc Finance-VN.
- Report thuộc Finance-SG.
- Ứng dụng vẫn **Deny** do sai data scope.

**Đăng nhập an toàn không chứng minh mọi tài nguyên được phép truy cập.** Ngược lại, người có role hợp lệ nhưng chưa hoàn tất MFA bắt buộc cũng có thể bị từ chối thực hiện thao tác nhạy cảm.

### 14.3. Claim mapping và source precedence

Nếu IdP claim `department=Finance` nhưng PIP ứng dụng có dữ liệu `department=Operations`, policy phải có **quy tắc ưu tiên nguồn** hoặc dừng đánh giá an toàn. Không tùy ý lấy giá trị “cho phép hơn” để người dùng tiếp tục thao tác. Các nguồn đồng bộ cần có owner, version, effectiveAt và reconciliation.

## 15. Service account, workload identity và policy condition

**Non-human identity** như service account, job, ứng dụng và workload có vòng đời khác nhân viên. Chúng có thể dùng credential OAuth client, certificate, workload federation hoặc managed identity để gọi API.

Ví dụ một job `billing-etl` được phép đọc dữ liệu báo cáo khi:

~~~text
subject.kind == "WORKLOAD"
AND subject.workloadId == "billing-etl"
AND subject.ownerTeam == "finance-platform"
AND subject.accountState == "ACTIVE"
AND action == "data:read"
AND resource.dataset in approvedDatasets("billing-etl")
AND environment.runtimeIdentityVerified
AND environment.environment == "production"
~~~

Trong ví dụ, `runtimeIdentityVerified` phải đến từ cơ chế tin cậy thực sự (ví dụ workload identity federation và token được resource server kiểm tra), không phải cờ client tự gửi. `approvedDatasets` phải lấy từ quyền đã phê duyệt.

### 15.1. Owner thay đổi không tự nghĩa workload phải bị khóa

Khi engineer phụ trách dịch vụ Mover/Leaver:
1. Cập nhật/bàn giao owner có thẩm quyền.
2. Thu hồi quyền quản trị cá nhân cũ.
3. Đánh giá credential mà người cũ biết/có thể truy cập; rotate/revoke nếu cần.
4. Giữ role và policy condition của workload nếu dịch vụ vẫn cần, nhưng rà soát least privilege.
5. Khi workload ngừng hoạt động, deprovision identity, credential, nhóm và quyền; readback.

Không viết condition `ownerEmployee.active == true` cho phép vô hiệu hóa toàn bộ job khi một người nghỉ việc **nếu policy nghiệp vụ không yêu cầu điều đó**. Tốt hơn là owner team/sponsor có trách nhiệm được quản lý, có quy trình chuyển giao và cảnh báo orphaned service identities.

### 15.2. Human MFA không áp dụng máy móc cho workload

Một workload chứng minh sở hữu khóa riêng có thể xác thực rất mạnh, nhưng **không đồng nghĩa đã hoàn tất MFA như người dùng**. Policy condition cần sử dụng tín hiệu phù hợp loại chủ thể: `humanAuthAssurance` cho người; `workloadAttestation/trustBinding` cho workload khi được hỗ trợ.

## 16. Thiết kế policy condition có thể kiểm thử

Một policy condition phải được **kiểm thử như logic bảo mật**, không chỉ chạy được với một tài khoản thử nghiệm. Bộ test cần bao phủ positive, negative, missing, stale, boundary, conflict và JML transitions.

### 16.1. Chính sách ví dụ: đọc báo cáo nội bộ

Giả sử policy tham khảo:

~~~text
PERMIT report:read IF
  subject.type == HUMAN
  AND subject.employmentStatus == ACTIVE
  AND subject.tenantId == resource.tenantId
  AND "ReportReader" in subject.effectiveRoles
  AND (
       subject.department == resource.department
       OR hasValidDelegatedReportAccess(subject, resource, now)
  )
  AND subject.clearanceRank >= resource.classificationRank
  AND environment.authAssurance >= requiredAssurance(resource)
  AND attributesAreTrustedAndFresh(subject, resource, environment)
OTHERWISE DENY or UNRESOLVED according to the chosen policy model
~~~

Những helper là **hàm logic minh họa**, không phải API chuẩn của XACML, OPA/Rego hoặc Cedar. Trong thực tế, cần xác định rõ output decision, thứ tự kết hợp và PEP behavior.

### 16.2. Ma trận kiểm thử

| Test | Input khác biệt | Kết quả mong đợi | Vì sao quan trọng |
| --- | --- | --- | --- |
| **T1 — hợp lệ** | User active, cùng tenant/department, role đủ, MFA đủ. | Permit. | Luồng bình thường. |
| **T2 — sai tenant** | Role đủ, tenant khác. | Deny. | Chống cross-tenant access. |
| **T3 — thiếu role** | Cùng department nhưng role không đủ. | Deny. | ABAC không tự bỏ qua RBAC. |
| **T4 — Mover** | Department đổi, report thuộc đơn vị cũ. | Deny, trừ delegation hợp lệ. | Ngăn quyền tồn dư. |
| **T5 — Leaver** | Employment status đã chấm dứt. | Deny. | Kiểm soát offboarding. |
| **T6 — thiếu trạng thái** | PIP không trả employment status. | Không Permit; xử lý lỗi an toàn. | Không suy unknown thành active. |
| **T7 — MFA yếu** | Assurance không đáp ứng resource. | Deny/step-up theo policy. | Kiểm soát AuthN. |
| **T8 — hết hạn delegation** | `now == effectiveUntil` với khoảng nửa mở. | Deny. | Ranh giới thời gian. |
| **T9 — hai assignment** | Một assignment hợp lệ đúng report, một assignment đã hết hạn. | Chỉ phạm vi hợp lệ được Permit. | Tránh cấp rộng/thu hồi sai. |
| **T10 — data classification** | Clearance thấp hơn tài nguyên. | Deny. | Bảo vệ dữ liệu nhạy cảm. |
| **T11 — stale token** | Claim cũ mâu thuẫn HRIS/PIP mới. | Không tiếp tục Permit sai; xử lý theo freshness policy. | Tránh quyền sau Mover/Leaver. |
| **T12 — API trực tiếp** | Gọi endpoint ngoài frontend/portal. | Cùng quyết định như UI. | PEP phải ở server. |
| **T13 — batch/export** | Request gom nhiều resource khác scope. | Chỉ dữ liệu trong scope hoặc từ chối theo design. | Chặn dữ liệu rò qua bulk. |
| **T14 — service identity** | Workload không có human MFA nhưng có trust binding. | Theo policy workload riêng. | Không gộp nhầm loại subject. |

### 16.3. Property tests và regression

Ngoài test đầu vào cụ thể, có thể áp dụng những **tính chất an toàn**:
- Thêm một điều kiện giới hạn truy cập bắt buộc không được làm **tăng** tập yêu cầu được phép, trừ khi chính sách kết hợp có thay đổi được phê duyệt.
- Đổi `employmentStatus` từ ACTIVE sang TERMINATED không được tạo một đường Permit mới ngoài ngoại lệ đã được định nghĩa.
- Một user không được truy cập tài nguyên **tenant khác** chỉ bằng cách đổi resource ID.
- Nếu clearance subject giảm, quyền đọc tài nguyên phân loại cao không được tăng.
- Điều kiện thời gian hết hạn phải thay đổi kết quả đúng tại ranh giới.
- Khi thêm resource attribute mới, thiếu schema hoặc null không được tự tạo Permit.

**Regression test** phải chạy khi thay policy, role mapping, data schema, IdP claim, HRIS synchronization hoặc authorization library, vì một thay đổi ở nguồn thuộc tính có thể thay đổi kết quả condition ngay cả khi code policy không đổi.

## 17. Chính sách dưới dạng dữ liệu: ví dụ JSON và pseudocode

Nhiều engine lưu policy dưới dạng code, DSL hoặc JSON cấu trúc. Ví dụ dưới đây là **schema nội bộ minh họa**, không phải định dạng chuẩn của một sản phẩm:

~~~json
{
  "policyId": "finance-report-read-v7",
  "version": 7,
  "effect": "PERMIT_IF_ALL",
  "target": {
    "resourceType": "FinancialReport",
    "action": "report:read"
  },
  "conditions": [
    { "attribute": "subject.accountActive", "op": "eq", "value": true },
    { "left": "subject.tenantId", "op": "eqAttribute", "right": "resource.tenantId" },
    { "attribute": "subject.effectiveRoles", "op": "contains", "value": "ReportReader" },
    { "left": "subject.department", "op": "eqAttribute", "right": "resource.department" },
    { "left": "subject.clearanceRank", "op": "gteAttribute", "right": "resource.classificationRank" }
  ],
  "metadata": {
    "owner": "finance-data-owner",
    "effectiveAt": "2026-12-01T00:00:00+07:00",
    "auditCategory": "SENSITIVE_DATA_ACCESS"
  }
}
~~~

### 17.1. Ví dụ policy dạng Rego để học ý tưởng

Một ví dụ nhỏ theo **cách viết Rego tham khảo**, nhằm minh họa điều kiện cho một request đã được chuẩn hóa:

~~~rego
package example.finance

default allow := false

allow if {
    input.subject.account_active == true
    input.subject.tenant_id == input.resource.tenant_id
    input.action == "report:read"
    "ReportReader" in input.subject.effective_roles
    input.subject.department == input.resource.department
    input.subject.clearance_rank >= input.resource.classification_rank
}
~~~

**Giới hạn của ví dụ:** chỉ mô tả policy boolean, chưa gồm policy ownership, input validation, attribute freshness, JML effective dates, SoD, time, step-up, audit và các đường thực thi ở API. Nó không kiểm chứng identity hay token; ứng dụng phải tạo `input` từ nguồn đã tin và enforce kết quả. Cú pháp cụ thể phụ thuộc phiên bản Rego/OPA và conventions triển khai.

### 17.2. Pseudocode luồng đánh giá an toàn

~~~text
function authorize(request):
    subject = authenticateAndResolveVerifiedIdentity(request)
    if subject cannot be resolved safely:
        return DENY

    resource = loadAuthoritativeResourceAttributes(request.resourceId)
    action = mapEndpointToBusinessAction(request)
    environment = collectVerifiedRuntimeSignals(request)

    attrs = attributeProvider.load(subject, resource, environment)
    if requiredAttributesMissingOrUntrusted(attrs):
        recordDecision("INDETERMINATE_OR_DENY", reason="ATTRIBUTES_UNAVAILABLE")
        return DENY

    if attributesPastFreshnessLimit(attrs):
        recordDecision("INDETERMINATE_OR_DENY", reason="STALE_ATTRIBUTES")
        return DENY

    decision = policyEngine.evaluate(
        subject=attrs.subject,
        resource=attrs.resource,
        action=action,
        environment=attrs.environment,
        policyVersion=activeApprovedVersion()
    )

    if decision is not explicitly PERMIT:
        recordDecision(decision, reason="POLICY_NOT_PERMITTED")
        return DENY

    applyRequiredObligationsOrDeny(decision)
    enforceResourceAndRowScope(resource, attrs)
    recordDecision("PERMIT", reason="POLICY_SATISFIED")
    return ALLOW
~~~

**Cảnh báo:** pseudocode không thay thế authorization framework. Trong thực tế phải quản lý race condition giữa đọc thuộc tính–ra quyết định–ghi tài nguyên (**TOCTOU**), cache, transaction boundary, PDP outages, audit failures, obligations và độ nhất quán theo mức rủi ro. Đặc biệt với thao tác thay đổi giao dịch, có thể cần kiểm tra state/policy ngay trong transaction.

## 18. Governance, audit và giải thích quyết định

Một policy condition khó kiểm toán nếu không biết ai sở hữu nó, dữ liệu đến từ đâu và request nào đã dùng phiên bản nào.

### 18.1. Metadata cần có cho policy

| Trường | Ý nghĩa |
| --- | --- |
| `policyId`, `version` | Định danh ổn định và phiên bản. |
| Owner/approver | Người hoặc nhóm có thẩm quyền xác nhận business rule. |
| Purpose / protected resources | Loại dữ liệu/hành động chính sách bảo vệ. |
| Trusted attribute sources | HRIS, IAM, resource catalog, IdP hoặc PIP cụ thể. |
| Required attribute schema | Kiểu dữ liệu, tính bắt buộc, namespace, null behavior. |
| Freshness/TTL | Thời gian thuộc tính được phép dùng trước khi refresh. |
| Combining behavior | Deny/permit/not applicable/error xử lý thế nào. |
| Effective time | Thời điểm policy có hiệu lực, rollback theo quy trình. |
| Test cases / coverage | Positive, negative, stale, missing, lifecycle boundary. |
| Deployment/verification evidence | PEP nào đang áp version đó và kết quả test/readback. |

### 18.2. Audit event minh họa

~~~json
{
  "eventId": "authz-decision-2026-1218",
  "timestamp": "2026-12-01T08:20:00+07:00",
  "correlationId": "api-flow-2048-171",
  "identityRef": "person-2048",
  "targetAccountRef": "finance-user-882",
  "resourceRef": "report-123",
  "action": "report:read",
  "policy": {
    "id": "finance-report-read-v7",
    "version": 7,
    "decision": "DENY",
    "reasonCode": "DEPARTMENT_SCOPE_MISMATCH"
  },
  "attributes": {
    "subjectSourceRef": "iam-directory-sync-812",
    "resourceSourceRef": "report-catalog",
    "subjectAttributesCheckedAt": "2026-12-01T08:19:59+07:00",
    "freshness": "ACCEPTED"
  },
  "enforcement": {
    "pep": "finance-report-api",
    "result": "REQUEST_BLOCKED"
  }
}
~~~

Đây là **JSON minh họa nội bộ**, không phải schema của XACML/SCIM/OIDC. Nó tách **quyết định policy** và **kết quả enforcement**. Không nên log password, OTP, private key, access/refresh token đầy đủ, full personal profile hay dữ liệu tài chính nhạy cảm không cần thiết. Quyền xem log, retention, tính toàn vẹn và mức chi tiết phải tuân theo chính sách.

### 18.3. Giải thích “vì sao Deny” mà không lộ quy tắc nhạy cảm

Người dùng có thể nhận thông báo chung: “Bạn không có quyền thực hiện thao tác này”. Đội hỗ trợ có quyền có thể thấy reason code nội bộ và policy version. Không nên để một API công khai phản hồi mọi thuộc tính HRIS, clearance hoặc đánh giá rủi ro chỉ vì client yêu cầu giải thích.

**Giải thích quyết định cho audit** khác **trả toàn bộ policy và profile trong phản hồi HTTP**.

## 19. Lỗi thiết kế phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Tin `department` do client gửi. | User tự tăng phạm vi dữ liệu. | Thuộc tính từ HRIS/IdP/PIP đã xác minh. |
| So sánh clearance như chuỗi alphabet. | Cấp quyền sai thứ bậc phân loại. | Taxonomy và so sánh có kiểu rõ. |
| Dùng `NOT suspended` khi thuộc tính thiếu. | Missing dễ trở thành Permit. | Missing/unknown rõ semantics, fail-safe. |
| Viết `active AND isOwner OR sameDepartment` không có ngoặc. | Leaver có thể vẫn được cho phép bởi một nhánh. | Nhóm điều kiện và test từng nhánh. |
| Chỉ kiểm tra role, không kiểm tra resource tenant. | IDOR/BOLA, cross-tenant leak. | Object-level authorization ở PEP. |
| Chỉ áp điều kiện trên UI. | API vẫn cho truy cập. | Server-side enforcement ở mọi endpoint. |
| Coi IdP login success là được phép xem mọi dữ liệu. | Nhầm AuthN với AuthZ. | RBAC/ABAC tại ứng dụng và tài nguyên. |
| Tin claim SSO cũ sau Mover. | Truy cập dữ liệu bộ phận cũ. | Freshness, cache invalidation, reconciliation. |
| Disable IdP nhưng không quản lý session/token tại target. | Leaver còn đường truy cập. | Deprovision và kiểm chứng actual access. |
| Cho phép khi PDP/PIP timeout. | Fail-open. | Default deny/handling được phê duyệt, break-glass riêng. |
| Kết hợp permit/deny không có semantics rõ. | Quyền bị cấp ngoài ý định. | Policy combining và test xung đột. |
| Quên transaction-level SoD. | Người tạo tự duyệt giao dịch. | Check creator/approver và workflow state. |
| Không xét multi-assignment và expiration. | Gỡ sai quyền còn hợp lệ hoặc giữ quyền quá hạn. | Assignment sources, effective window, owner. |
| Coi SCIM User/Group đủ toàn bộ thuộc tính ABAC. | Điều kiện thiếu dữ liệu/không có owner. | Schema mapping, PIP và attribute governance. |
| Chặn workload chỉ vì owner nhân sự nghỉ. | Gián đoạn dịch vụ hợp lệ. | Handover owner và service lifecycle riêng. |
| Chỉ log “Policy Permit”, không log enforcement. | Không chứng minh quyền thực tế đã được áp dụng đúng. | Decision+PEP outcome, policy version, correlation. |
| Chỉ test trường hợp đủ dữ liệu. | Unknown/missing/stale tạo lỗ hổng. | Negative/boundary/regression test. |

## 20. Tình huống xuyên suốt: báo cáo tài chính và chuyển vai trò

**Bối cảnh:** Doanh nghiệp có IdP SSO, IAM/IGA, HRIS và ứng dụng **Finance Reports**. Người dùng Lan có IAM identity `person-2048`, application account `finance-user-882`, role `ReportReader` và phòng ban hiện tại `Operations`. Báo cáo `report-123` thuộc `Operations`, phân loại `INTERNAL`.

### 20.1. Trước Mover

Dữ liệu:
- `subject.employmentStatus = ACTIVE`.
- `subject.department = Operations`.
- `resource.department = Operations`.
- `subject.roles` chứa `ReportReader`.
- `subject.tenantId == resource.tenantId`.
- MFA/session đáp ứng chính sách.

Kết quả tham khảo: **Permit**, nếu tất cả yêu cầu khác cũng đạt và PEP thực thi tại API.

### 20.2. Tại thời điểm Mover

HRIS xác nhận Lan chuyển sang Finance vào `2026-12-01T00:00:00+07:00`. IAM cập nhật desired access; SCIM/group provisioning thay vai trò liên quan; PIP cập nhật department.

Sau khi thay đổi:
- `subject.department = Finance`.
- `resource.department = Operations`.
- `subject.roles` vẫn có thể chứa một role `ReportReader` phù hợp cho Finance.
- Condition `subject.department == resource.department` trở thành **false** với `report-123`.

Ứng dụng phải **Deny** yêu cầu đọc báo cáo Operations, dù Lan còn đăng nhập qua SSO. IAM đồng thời phải rà soát entitlement cũ và session/token để các đường khác không còn quyền Operations.

### 20.3. Failure mode: claim SSO còn cũ

Nếu token phát hành từ trước Mover vẫn chứa `department=Operations` và ứng dụng dùng claim đó không kiểm tra freshness, policy có thể trả **Permit sai**. Giải pháp cần phù hợp kiến trúc:
- Rút ngắn thời gian chấp nhận token hoặc áp revalidation.
- Tra thuộc tính mới ở PIP đáng tin cho yêu cầu nhạy cảm.
- Dùng session/policy invalidation hoặc cơ chế revocation hỗ trợ.
- Theo dõi effective time, độ trễ đồng bộ và remediation.
- Kiểm chứng bằng request vào report cũ rằng access đã bị chặn.

Không thể khẳng định mọi IdP/ứng dụng hỗ trợ revocation tức thì; cần thiết kế thời hạn và biện pháp theo khả năng thật.

### 20.4. Leaver sau đó

Khi Lan nghỉ việc, nguồn HRIS đặt trạng thái không còn active. Điều kiện bắt buộc phải Deny, IdP cũng chặn đăng nhập mới. Tuy nhiên IAM vẫn cần kiểm tra application session, local account, API token và quyền ở target trước khi kết luận **không còn residual access**.

### 20.5. Service owner thay đổi

Finance Reports còn có workload `report-scheduler` được một nhân viên quản lý. Khi owner nghỉ việc, workload có thể tiếp tục truy cập đúng dataset nếu có owner mới và policy hợp lệ, nhưng quyền quản trị/credential người cũ phải được thu hồi. **Không trộn điều kiện employmentStatus của con người với điều kiện service identity**.

## 21. Chỉ số vận hành và checklist

### 21.1. Chỉ số nên theo dõi

| Chỉ số | Cách đo tham khảo | Điều dễ đo sai |
| --- | --- | --- |
| **Policy condition coverage** | Tỷ lệ hành động/tài nguyên nhạy cảm có PEP kiểm tra policy được duyệt. | Chỉ nhìn UI hoặc API chính, bỏ qua export/batch. |
| **Trusted attribute coverage** | Tỷ lệ điều kiện trọng yếu dùng thuộc tính có nguồn, owner và schema rõ. | Coi mọi claim SSO đều đang mới và đúng HRIS. |
| **Attribute freshness violation** | Số decision có thuộc tính quá TTL hoặc mâu thuẫn nguồn có thẩm quyền. | Không phân biệt cache hợp lệ và stale trái policy. |
| **Deny-on-unknown compliance** | Tỷ lệ lỗi dữ liệu thiết yếu được xử lý không Permit. | Bỏ qua trường hợp PDP/PIP timeout. |
| **Cross-tenant authorization tests** | Kịch bản thay resource ID/tenant bị chặn đúng. | Chỉ test một URL/một user. |
| **Mover revocation latency** | Thời gian từ mốc phải hết quyền cũ đến lúc actual access bị chặn. | Đếm chỉ thời điểm HRIS update/connector HTTP 200. |
| **Leaver access closure** | Tỷ lệ các access path bắt buộc được xác minh đã chặn. | Coi disable IdP là đủ. |
| **Policy regression pass rate** | Test dương/âm/boundary đạt trên version mới. | Chỉ chạy test cho trường hợp Permit. |
| **Decision–enforcement mismatch** | Tình huống PDP Deny nhưng request vẫn được xử lý, hoặc scope sai. | Chỉ ghi decision không đo kết quả tại PEP. |
| **SoD violations detected** | Xung đột role/transaction phát hiện được trong scope. | Chỉ xét role trực tiếp, bỏ qua quan hệ giao dịch. |

Không có **một ngưỡng chung** phù hợp mọi tổ chức. Đặt thời hạn thu hồi và mức giám sát theo **độ nhạy tài nguyên, quyền đặc quyền, yêu cầu tuân thủ và rủi ro kinh doanh**.

### 21.2. Checklist thiết kế và vận hành policy condition

- [ ] Xác định rõ subject, resource, action và environment; không lẫn AuthN với AuthZ.
- [ ] Mỗi thuộc tính thiết yếu có source of truth, owner, kiểu dữ liệu, namespace và quy tắc freshness.
- [ ] Identity/account binding đúng người và tenant; không chỉ dựa vào email hoặc employee number.
- [ ] Resource attributes lấy từ hệ thống đáng tin; chặn IDOR/BOLA và cross-tenant access.
- [ ] Biểu thức logic rõ ngoặc, `AND/OR/NOT` không tạo nhánh cho phép thiếu trạng thái active.
- [ ] Missing/null/unknown/Indeterminate không bị biến thành Permit do lỗi mã hoặc cấu hình.
- [ ] Phân loại/clearance có thứ bậc/compartment hợp lệ, không so sánh chuỗi tùy tiện.
- [ ] Thời gian, effectiveFrom/effectiveUntil, timezone và expiration có test ranh giới.
- [ ] Có định nghĩa combining behavior, default deny và xử lý PDP/PIP unavailable.
- [ ] RBAC role/permission và ABAC scope đều phải thỏa; SoD được kiểm tra ở cấp phù hợp.
- [ ] Policy được enforcement ở server/PEP trên UI, API, export, batch và resource thực tế.
- [ ] IdP/SSO claim được kiểm chứng và có cách xử lý khi thuộc tính/phiên đã cũ.
- [ ] SCIM provisioning, quyền ở target và readback tách khỏi kết quả policy condition.
- [ ] Joiner chỉ có quyền đúng mốc; Mover loại quyền cũ nhưng xét assignment khác; Leaver chặn mọi đường bắt buộc.
- [ ] Service/workload identity có owner, trust binding, policy và vòng đời riêng.
- [ ] Test đủ Permit/Deny, wrong tenant, stale/missing, time boundary, mixed assignment, override, SoD và API bypass.
- [ ] Policy có version, approval, owner, audit; log không lộ credential hoặc PII không cần thiết.
- [ ] Reconciliation kiểm tra **actual effective access**, không đóng ticket chỉ vì policy đã lưu hoặc IdP disabled.

## 22. Bài tập thực hành

### 22.1. Tình huống A — Sai ưu tiên toán tử

Một developer viết `active AND isOwner OR sameDepartment`. Employee vừa Leaver nhưng `sameDepartment=true` vì dữ liệu phòng ban chưa đổi. Hãy giải thích vì sao condition có thể Permit và viết lại biểu thức với dấu ngoặc để **active luôn bắt buộc**.

### 22.2. Tình huống B — Thiếu thuộc tính

PIP timeout và không trả `employmentStatus`. Ứng dụng dùng `NOT suspended` và tự coi missing là `false`. Hãy xác định lỗi fail-open, phân biệt **unknown, false, NotApplicable, Indeterminate** và đề xuất quyết định an toàn.

### 22.3. Tình huống C — Report thuộc tenant khác

User có `ReportReader` và MFA đầy đủ. Người đó đổi path từ `/reports/123` sang `/reports/124` (báo cáo tenant khác). Những thuộc tính nào phải được lấy từ resource store? PEP cần chặn ở bước nào để ngăn IDOR/BOLA?

### 22.4. Tình huống D — Mover có hai assignment

Lan chuyển sang Finance nhưng được phê duyệt hỗ trợ dự án Operations trong 14 ngày. Hãy thiết kế condition kiểm tra **active assignment + resource project + scope + expiration** mà không ghi đè department chính hoặc cho phép toàn bộ Operations.

### 22.5. Tình huống E — Tự duyệt thanh toán

Một Manager có role `PaymentApprover` và trước đó tự tạo giao dịch. Hãy viết condition dùng `resource.createdByIdentityId != subject.identityId`, approval limit, trạng thái giao dịch và tenant; nêu kiểm tra SoD nào vẫn cần ngoài condition.

### 22.6. Tình huống F — Stale SSO token

IdP đã nhận Mover từ HRIS nhưng token còn mang `department=Operations`. Hãy giải thích vì sao chữ ký token đúng không bảo đảm dữ liệu đang mới, và đề xuất kiểm soát PIP freshness/token/session để chặn quyền tồn dư.

### 22.7. Tình huống G — Workload owner Leaver

Owner của `billing-etl` nghỉ việc. Condition dùng `ownerEmployee.active` để chặn mọi request từ workload. Hãy đánh giá ảnh hưởng vận hành, phân biệt quyền cá nhân và quyền workload, rồi đề xuất owner handover/credential rotation và policy phù hợp.

### 22.8. Tình huống H — PDP trả Permit nhưng dữ liệu vẫn rò

PDP trả Permit cho `report:read` của người thuộc Finance-VN, nhưng API query không giới hạn department và trả cả báo cáo Finance-SG. Hãy chỉ ra lỗi ở **PEP/resource query enforcement** và cách kiểm thử kết quả thực tế, bao gồm export và pagination.

**Điểm cần ghi nhớ:** **Policy condition là phần biểu diễn ràng buộc của một quyết định ABAC**, sử dụng thuộc tính **subject, resource, action và environment** từ nguồn có thẩm quyền. Chính sách an toàn phải xử lý **missing/unknown, thứ tự logic, thời gian, trạng thái JML, SoD, phạm vi dữ liệu và độ mới của thuộc tính**, đồng thời có **PDP quyết định và PEP thực thi**. Trong hệ thống IAM, condition phối hợp với **RBAC, IdP/SSO và SCIM** nhưng không thay thế việc **provisioning/deprovisioning, kiểm soát session/token, đối soát quyền tại ứng dụng đích và bằng chứng kiểm toán**.

