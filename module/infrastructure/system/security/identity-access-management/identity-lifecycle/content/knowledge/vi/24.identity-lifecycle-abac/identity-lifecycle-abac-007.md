# Attribute source trong ABAC: nguồn thuộc tính đáng tin cậy để quyết định quyền truy cập

Một nhân viên đã chuyển khỏi phòng Tài chính nhưng vẫn mở được báo cáo tài chính vì hệ thống phân quyền đang đọc thuộc tính **department** cũ trong token đăng nhập. Một đối tác hết hạn hợp đồng nhưng ứng dụng vẫn chấp nhận giá trị **contractStatus=ACTIVE** từ bộ nhớ đệm. Một API khác lại tin vào header **X-Department** do chính người gọi gửi, cho phép người dùng tự nhận mình thuộc bộ phận có quyền. Cả ba tình huống đều cho thấy: **chính sách ABAC có thể đúng về logic nhưng vẫn đưa ra quyết định sai nếu nguồn thuộc tính không đáng tin cậy hoặc không đủ mới**.

**Attribute source** là nguồn cung cấp hoặc xác nhận các giá trị thuộc tính mà hệ thống **Attribute-Based Access Control (ABAC)** sử dụng để đánh giá yêu cầu truy cập. Nguồn đó có thể là HRIS, directory, IdP, dịch vụ quản trị quyền, cơ sở dữ liệu tài nguyên, hệ thống quản lý thiết bị hoặc ngữ cảnh được xác định tại thời điểm request. Không nguồn nào mặc nhiên có thẩm quyền với **mọi** thuộc tính.

Bài học thuộc chương **ABAC** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tìm hiểu quản lý vòng đời danh tính theo mô hình **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi thay đổi vai trò. Nội dung kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **attribute**, **attribute source**, **source of authority**, **claim**, **derived attribute** và **policy input**.
- Phân loại nguồn thuộc tính theo **subject, resource, action, environment** và xác định chủ sở hữu dữ liệu của từng loại.
- Mô tả cách **Policy Information Point (PIP)** cung cấp dữ liệu cho **Policy Decision Point (PDP)** và vì sao **Policy Enforcement Point (PEP)** phải kiểm tra quyết định ở đúng tài nguyên.
- Thiết kế quy tắc kiểm **tính xác thực, nguồn gốc, thời gian hiệu lực, độ tươi, tính toàn vẹn, phạm vi tenant và xung đột thuộc tính**.
- Đánh giá tác động của sự kiện **Joiner, Mover, Leaver** tới nguồn thuộc tính, phiên, token, role, tài khoản máy và quyền thực tế.
- Xây dựng quy trình đối soát, giám sát, điều tra và kiểm toán **quyết định ABAC** khi thuộc tính thiếu, sai hoặc chậm đồng bộ.

## 1. Attribute trong ABAC là gì?

**ABAC** quyết định một yêu cầu truy cập có được phép hay không bằng cách đánh giá **thuộc tính của chủ thể, tài nguyên, hành động, môi trường và các quan hệ liên quan** theo chính sách.

Ví dụ chính sách đọc báo cáo:

~~~text
PERMIT nếu:
    subject.lifecycleState == "ACTIVE"
    AND subject.departmentId == resource.ownerDepartmentId
    AND subject.approvedDataLevel >= resource.classificationLevel
    AND action == "read"
    AND environment.authStrength >= policy.requiredAuthStrength
~~~

Giả mã thể hiện **điều kiện logic**, không phải ngôn ngữ ABAC tiêu chuẩn chạy trực tiếp. Thứ tự mức phân loại và mức xác thực phải được định nghĩa trong hệ thống chính sách; không thể tự so sánh các chuỗi như \`"SECRET" > "INTERNAL"\` mà không có mô hình thứ bậc.

Ngay cả chính sách đơn giản này cần nhiều nguồn dữ liệu:

- Trạng thái làm việc **ACTIVE** lấy từ HRIS hoặc trạng thái chuẩn hóa do IAM xác định.
- **departmentId** lấy từ hồ sơ tổ chức có thẩm quyền.
- **ownerDepartmentId** và **classificationLevel** lấy từ nguồn sở hữu tài nguyên.
- **approvedDataLevel** lấy từ quy trình phê duyệt hoặc quản trị quyền.
- **action** được suy ra từ endpoint/thao tác mà API thực sự đang xử lý.
- **authStrength** dựa trên bằng chứng xác thực tin cậy và chính sách của IdP/ứng dụng, không phải nhãn do client tự khai.

**Điểm quan trọng:** ABAC không trở nên an toàn chỉ vì viết policy phức tạp. **Mọi thuộc tính ảnh hưởng quyết định cần có nguồn, ý nghĩa và độ tin cậy rõ ràng.**

## 2. Source of authority khác attribute source như thế nào?

Hai thuật ngữ liên quan nhưng không hoàn toàn đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Attribute source** | Hệ thống hoặc thành phần cung cấp giá trị thuộc tính cho quá trình đánh giá. | IdP gửi \`department\` trong token; PIP đọc một directory. |
| **Authoritative source** | Hệ thống được tổ chức chỉ định có quyền xác định giá trị đúng cho một thuộc tính trong ngữ cảnh cụ thể. | HRIS sở hữu \`employmentStatus\`; data catalog sở hữu \`classification\` của tài liệu. |
| **System of record** | Nơi lưu bản ghi nghiệp vụ theo quy trình quản trị dữ liệu. | Hệ thống quản lý hợp đồng ghi ngày kết thúc hợp đồng. |
| **Derived attribute** | Thuộc tính được tính từ một hoặc nhiều dữ liệu nguồn theo quy tắc có phiên bản. | \`eligibleForFinanceAccess\` được tính từ trạng thái nhân sự, phòng ban và phê duyệt. |
| **Claim** | Tuyên bố do một hệ thống phát hành, thường nằm trong token/assertion. | \`department=FINANCE\` trong ID token. |
| **Policy input** | Giá trị cụ thể mà PDP nhận để đánh giá yêu cầu. | Department được PIP trả tại thời điểm quyết định. |

Một **claim có chữ ký hợp lệ** cho biết nó do đúng issuer phát hành và không bị sửa trên đường truyền; **không bảo đảm nội dung claim còn mới, phù hợp ngữ cảnh hoặc issuer có thẩm quyền với thuộc tính đó**.

Ví dụ: IdP phát token chứa phòng ban dựa trên dữ liệu directory đồng bộ hôm qua. Chữ ký token đúng, nhưng HRIS đã xác nhận Mover sáng nay. Nếu PDP tin claim cũ như sự thật hiện tại, quyền có thể bị giữ quá thời hạn.

### 2.1. Thẩm quyền thuộc về thuộc tính, không chỉ về hệ thống

Không nên đặt một thứ tự tổng quát kiểu “HRIS đáng tin hơn IdP trong mọi tình huống”. Thay vào đó:

- HRIS có thể sở hữu **bộ phận, worker type, Start date, termination date**.
- IdP có thể sở hữu **trạng thái xác thực, MFA và bằng chứng phiên đăng nhập**.
- IAM/IGA có thể sở hữu **approval, policy eligibility và quyền đã được phê duyệt**.
- Ứng dụng hoặc data catalog có thể sở hữu **classification, owner và phạm vi của tài nguyên**.
- MDM/EDR có thể cung cấp **device compliance**, nếu thiết bị và tín hiệu đã được xác thực.
- Hệ thống thời gian đáng tin cậy tại server có thể cung cấp **request time**, không phải đồng hồ do client gửi.

Từng thuộc tính cần có **source authority matrix**: nguồn chính, nguồn sao lưu phù hợp, phương pháp xác minh, tuổi dữ liệu cho phép và điều kiện khi không thể đọc nguồn.

## 3. Bốn nhóm thuộc tính cốt lõi

### 3.1. Subject attributes – thuộc tính chủ thể

Thuộc tính liên quan tới con người hoặc workload yêu cầu truy cập.

| Thuộc tính | Nguồn có thẩm quyền khả dĩ | Ứng dụng trong policy |
| --- | --- | --- |
| **subjectId** | IAM/IdP trong namespace đã xác minh. | Liên kết đúng người/tài khoản. |
| **workerType** | HRIS/hệ thống hợp đồng. | Employee khác Contractor. |
| **engagementState** | HRIS/hợp đồng + quy tắc lifecycle của IAM. | Chặn Leaver, tạm đình chỉ hoặc người chưa tới ngày bắt đầu. |
| **departmentId** | HRIS hoặc cơ cấu tổ chức được chỉ định. | Giới hạn dữ liệu theo phòng ban. |
| **managerSubjectId** | HRIS hoặc hệ thống quản lý nhân sự có thẩm quyền. | Tuyến phê duyệt, quan hệ cấp dưới. |
| **approvedAccessLevel** | IGA/owner nghiệp vụ. | Phân loại dữ liệu được phép truy cập. |
| **privilegedEligibility** | PAM/IGA và workflow phê duyệt. | Điều kiện kích hoạt quyền đặc quyền. |
| **group/role memberships** | Hệ thống quản trị nhóm/quyền được chỉ định. | RBAC kết hợp ABAC. |

Thuộc tính chủ thể phải liên kết với **đúng subject và engagement**, không chỉ một địa chỉ email. Một người tái tuyển dụng có thể có cùng Person ID nhưng **quyền và ngày hiệu lực thuộc engagement mới**.

### 3.2. Resource attributes – thuộc tính tài nguyên

| Thuộc tính | Nguồn thường phù hợp | Rủi ro nếu nguồn sai |
| --- | --- | --- |
| **resourceId** | Cơ sở dữ liệu hoặc registry ứng dụng. | Gắn nhầm tài nguyên cần kiểm. |
| **ownerDepartmentId** | Hệ thống quản lý sở hữu dữ liệu. | Người thuộc sai phòng được truy cập. |
| **classificationLevel** | Data catalog, DLP hoặc chủ sở hữu dữ liệu được ủy quyền. | Dữ liệu nhạy cảm bị gắn nhãn quá thấp. |
| **tenantId / projectId** | Ứng dụng sở hữu tài nguyên. | Rò rỉ dữ liệu giữa tenant/dự án. |
| **retentionState** | Data governance/records management. | Truy cập vào hồ sơ cần hạn chế khi legal hold hoặc hết hạn. |
| **resourceStatus** | Dịch vụ nghiệp vụ. | Cho phép thao tác trên tài nguyên đã khóa/archived. |

Không nên cho người dùng không có thẩm quyền **tự sửa classification** rồi dùng chính giá trị đó để vượt qua policy. Metadata tài nguyên phải được bảo vệ bởi quyền ghi và quy trình duyệt tương xứng.

### 3.3. Action attributes – thuộc tính hành động

Ví dụ **read**, **write**, **approve**, **export**, **delete** hoặc **assign-role**. Nguồn đáng tin là **API gateway hoặc ứng dụng đang thực thi hành động**, sau khi ánh xạ endpoint và nghiệp vụ vào action canonical.

Một API nhận \`{"action":"read"}\` do client gửi **không được tin vô điều kiện** nếu request thực sự gọi endpoint xóa dữ liệu. Ứng dụng phải tự xác định hành động đang thực hiện và yêu cầu PEP kiểm policy cho **đúng action + resource**.

### 3.4. Environment attributes – thuộc tính ngữ cảnh

| Thuộc tính | Nguồn đáng tin tùy kiến trúc | Lưu ý |
| --- | --- | --- |
| **requestTime** | Server/gateway có đồng hồ được quản lý. | Quy đổi múi giờ, đồng hồ lệch, ngày nghỉ. |
| **networkZone** | Gateway/proxy đã xác thực, cấu hình mạng. | IP không đại diện chắc chắn cho một người hay nơi ở. |
| **deviceCompliant** | MDM/EDR hoặc nền tảng xác thực device posture. | Tín hiệu có thời hạn và có thể stale. |
| **authenticationContext** | IdP/OP với claim được định nghĩa rõ và có kiểm chữ ký. | Không tự suy rằng mọi \`acr\`/\`amr\` có mức bảo đảm tương đương. |
| **riskScore** | Risk engine có owner, dữ liệu đầu vào và chu kỳ đánh giá. | Có thể thay đổi nhanh; cần ngưỡng và xử lý thiếu tín hiệu. |
| **sessionAge** | Session manager/token validation có thẩm quyền. | Session từ trước Mover/Leaver có thể không còn đủ điều kiện. |

**Environment không phải là dữ liệu do người gọi muốn khai gì cũng được.** Header \`X-Device-Trusted: true\`, múi giờ máy khách hoặc tên mạng được client cung cấp chỉ là input chưa đáng tin nếu không có cơ chế xác nhận.

## 4. Kiến trúc PEP – PDP – PIP trong ABAC

Một cách tổ chức ABAC thường gồm:

- **Policy Enforcement Point (PEP):** điểm chặn hành động, gửi bối cảnh truy cập tới bộ quyết định và thực thi kết quả.
- **Policy Decision Point (PDP):** đánh giá request theo chính sách và trả quyết định.
- **Policy Information Point (PIP):** truy xuất/cung cấp thuộc tính cần thiết từ nguồn bên ngoài cho PDP hoặc dịch vụ quyết định.
- **Policy Administration Point (PAP):** quản lý chính sách, phiên bản, phê duyệt và triển khai policy.

Đây là mô hình trách nhiệm, không bắt buộc phải có bốn máy chủ riêng. Một ứng dụng có thể nhúng PEP/PDP, trong khi PIP truy vấn dịch vụ dữ liệu tập trung.

~~~mermaid
flowchart TD
    HR["HRIS / hợp đồng<br/>JML + worker state"] --> IGA["IAM / IGA<br/>Canonical subject + approval"]
    DIR["Directory / IdP<br/>nhóm, account, auth context"] --> PIP["PIP<br/>Attribute retrieval + validation"]
    IGA --> PIP
    DATA["Resource registry / data catalog<br/>classification, owner, tenant"] --> PIP
    MDM["MDM / Risk / trusted gateway<br/>device + request context"] --> PIP
    REQ["Người dùng hoặc workload"] --> PEP["PEP tại API / ứng dụng"]
    PEP --> PDP["PDP<br/>Evaluate policy"]
    PIP --> PDP
    PAP["PAP<br/>policy + version + approval"] --> PDP
    PDP -->|"Permit / Deny / Indeterminate<br/>theo mô hình engine"| PEP
    PEP --> APP["Tài nguyên / nghiệp vụ"]
    PDP --> AUD["Audit + Decision trace"]
    PEP --> AUD
    PIP --> AUD
~~~

### 4.1. Quyết định phải dựa trên ngữ cảnh đầy đủ

Một PEP không nên gửi chỉ mỗi \`userId\` và \`resourceId\` rồi suy các trường khác từ input không đáng tin. Cần ràng buộc:

1. **Subject** đã được xác thực, đúng issuer/tenant và account.
2. **Action** mà endpoint thực sự đang thực hiện.
3. **Resource** được truy vấn theo ID/owner chính xác, không qua alias gây nhầm lẫn.
4. **Environment** được đo bởi thành phần đáng tin cậy.
5. **Policy version**, thời điểm quyết định và các giá trị thuộc tính được sử dụng.

PIP nên cung cấp **giá trị cùng metadata về nguồn và độ tươi**, hoặc PDP phải có cách kiểm độ tin cậy tương đương. Mỗi hệ thống ABAC có thể biểu diễn metadata khác nhau; không có cấu trúc JSON bắt buộc chung cho mọi PDP.

## 5. Source authority matrix: thiết kế quyền sở hữu từng thuộc tính

Trước khi viết hàng trăm rule, nên lập bảng **mỗi thuộc tính lấy từ đâu, được phép stale bao lâu và xử lý sự cố thế nào**.

| Attribute | Authoritative owner | Cơ chế truy xuất | Kiểm tra cần thiết | Khi không có dữ liệu |
| --- | --- | --- | --- | --- |
| **employmentStatus** | HRIS/contract source, chuẩn hóa bởi IAM. | Event stream, API hoặc store đồng bộ. | Source version, engagement ID, effectiveAt. | Không cấp quyền cần quan hệ ACTIVE. |
| **departmentId** | HRIS/org master được chỉ định. | IGA/Directory PIP. | Code canonical, nguồn, hiệu lực Mover. | Không suy từ email hoặc group tùy tiện. |
| **approvedRole/scope** | IGA và owner có thẩm quyền. | Entitlement registry/API. | Approval ID, expiresAt, SoD. | Từ chối quyền yêu cầu phê duyệt chưa xác minh. |
| **resourceClassification** | Data owner/catalog. | Resource registry hoặc DB app. | Resource ID, tag version, quyền sửa nhãn. | Không mặc định tài nguyên là PUBLIC. |
| **resourceTenantId** | Ứng dụng/dịch vụ dữ liệu. | DB/resource service nội bộ. | Tenant isolation và ID không bị giả. | Không cho qua biên tenant. |
| **deviceCompliance** | MDM/EDR đã liên kết thiết bị. | Signed/verified device posture. | Device ID, freshness, issuer. | Không cho tác vụ đòi thiết bị compliant. |
| **authStrength** | IdP với nghĩa claim đã thống nhất. | Session assertion/validated token. | Issuer, audience, expiration, \`acr\`/\`amr\` mapping. | Yêu cầu step-up hoặc từ chối tác vụ nhạy cảm. |
| **requestTime** | PEP/PDP trusted clock. | Runtime clock được quản lý. | Múi giờ, đồng hồ và window policy. | Từ chối hoặc xử lý theo quy tắc an toàn của ứng dụng. |

**Fail closed** là nguyên tắc phổ biến cho yêu cầu nhạy cảm khi dữ liệu thiết yếu không đáng tin; tuy vậy cần tách rõ trạng thái **DENY** (chính sách từ chối) và **INDETERMINATE/ERROR** (không thể đánh giá). Với hệ thống có yêu cầu an toàn vật lý hoặc tính sẵn sàng đặc biệt, đường xử lý dự phòng phải được thiết kế/phê duyệt rõ ràng, không phải tự suy \`missing=true\` thành **PERMIT**.

## 6. Danh tính bền vững và ánh xạ thuộc tính đúng chủ thể

Thuộc tính **đúng nguồn nhưng gắn sai user** vẫn có thể gây lộ dữ liệu. IAM cần quản lý định danh ổn định xuyên các hệ thống:

| Định danh | Nguồn hoặc phạm vi | Điều cần nhớ |
| --- | --- | --- |
| **personId** | HRIS/IAM quản lý con người. | Có thể liên kết nhiều engagement qua thời gian. |
| **engagementId** | HRIS/hợp đồng. | Chỉ rõ quan hệ có hiệu lực hiện tại. |
| **subjectId** | IAM canonical identity. | Dùng làm khóa liên kết policy trong phạm vi IAM. |
| **directoryObjectId** | Directory cụ thể. | DN, UPN/email không phải ID bất biến. |
| **\`iss\` + \`sub\`** | OIDC issuer và subject. | Không dùng \`sub\` đơn lẻ xuyên mọi issuer. |
| **SCIM \`id\`** | ID User do service provider cấp. | Không tự dùng HR employeeNumber làm ID đích. |
| **Resource ID + tenant** | Hệ thống sở hữu tài nguyên. | Chặn ánh xạ sai giữa khách hàng/dự án. |

### 6.1. Ví dụ gắn nhầm Person khi dùng email

Nhân viên A nghỉ việc. Sau một thời gian, địa chỉ email cũ được tái cấp cho người B. Nếu PIP lưu \`approvedDataLevel\` theo email, B có thể nhận **thuộc tính quyền của A** dù hoàn toàn không phải cùng người.

Cách phòng tránh:

1. Sử dụng khóa subject/engagement ổn định, có namespace của nguồn.
2. Khi email/UPN thay đổi, cập nhật thuộc tính liên hệ mà **không tự tạo hoặc ghép lại danh tính**.
3. Khi rehire, xác minh cùng Person nhưng đánh giá quyền dựa trên engagement mới.
4. Khi mapping mơ hồ, đưa vào bước xác minh; không dùng phép nối lỏng để đưa ra PERMIT.

## 7. Thuộc tính trực tiếp và thuộc tính suy diễn

Nguồn thuộc tính có thể cung cấp giá trị **raw** hoặc hệ thống có thể tính **derived attributes**:

~~~text
HRIS: status=ACTIVE, departmentId=FINANCE
IGA: financeAccessApproval=APPROVED, expiresAt=...
Device management: compliant=true, observedAt=...

Derived attribute:
    financeReadEligible =
        engagementState == ACTIVE
        AND departmentId == FINANCE
        AND financeAccessApproval is valid
~~~

Nếu tạo \`financeReadEligible=true\` thành một trường lưu trữ để tái sử dụng, cần ghi:

- Các **nguồn đầu vào** và ID/phiên bản tương ứng.
- **Policy/derivation version** đã tính giá trị.
- Thời điểm tính, **điểm bắt đầu và kết thúc hiệu lực**.
- Nguyên tắc làm mới khi bất kỳ đầu vào nào thay đổi.
- Ai được quyền thay đổi quy tắc hoặc ghi đè kết quả.

Một derived attribute được tính hôm qua có thể không còn đúng sau Mover hoặc Leaver. **Đừng biến kết quả suy diễn thành “sự thật vĩnh viễn” nếu không có cơ chế invalidation.**

### 7.1. Tránh vòng lặp thẩm quyền

Ví dụ một group \`finance-readers\` được IAM tạo từ HRIS \`department=FINANCE\`; sau đó một PIP lại dùng membership của group để suy ra **department=FINANCE**. Nếu HRIS đổi department nhưng group đồng bộ chậm, vòng suy luận có thể giữ giá trị cũ.

Phải tách:

- **Department** do HRIS/org master định nghĩa.
- **Entitlement** do IAM/owner phê duyệt và thực thi.
- **Group membership** là trạng thái triển khai có thể không đồng bộ.

Không dùng trạng thái đích làm nguồn có thẩm quyền cho giá trị gốc khi chưa có quy tắc ownership rõ.

## 8. Freshness, validity và effective time

Trong ABAC, **giá trị đúng tại thời điểm t₁ có thể sai tại t₂**. Cần phân biệt nhiều mốc:

| Trường thời gian | Ý nghĩa |
| --- | --- |
| **sourceEventTime** | Nguồn ghi nhận sự kiện lúc nào. |
| **effectiveAt** | Thời điểm thay đổi có hiệu lực về mặt nghiệp vụ. |
| **observedAt / fetchedAt** | PIP nhận hoặc lấy dữ liệu lúc nào. |
| **updatedAt** | Bản ghi được sửa lần cuối tại nguồn/bản sao. |
| **expiresAt / validUntil** | Thuộc tính/approval chỉ hợp lệ tới thời điểm nào. |
| **evaluatedAt** | PDP đưa ra quyết định tại thời điểm nào. |
| **tokenIssuedAt / tokenExpiresAt** | Các mốc của token chứa claim nếu có. |
| **verifiedAt** | Lúc trạng thái thực tế được đối soát. |

**Độ tươi (freshness)** khác **giá trị có hiệu lực (validity)**. Một sự kiện được nhận sớm có thể chỉ có hiệu lực tuần sau. Ngược lại, sự kiện Leaver đến muộn nhưng hiệu lực từ trước có thể yêu cầu thu hồi ngay, đồng thời điều tra cửa sổ truy cập tồn dư.

### 8.1. Ví dụ Mover có hiệu lực 08:00

~~~text
30/11 16:00  HRIS thông báo Mover sang Finance.
01/12 08:00  Mover bắt đầu có hiệu lực.
01/12 08:01  PIP vẫn cache departmentId=SALES.
01/12 08:03  IdP token mới đã có departmentId=FINANCE.
01/12 08:05  Ứng dụng A vẫn lưu session role Sales từ hôm trước.
01/12 08:10  Reconciliation phát hiện quyền Sales chưa bị thu hồi.
~~~

Tại 08:01, cache ở PIP có thể gây **từ chối nhầm quyền mới** hoặc **cho phép nhầm quyền cũ**. Tại 08:05, dù IdP token mới đã đúng, phiên ứng dụng A vẫn có thể dùng trạng thái trước đó. Đó là **ba lớp nhất quán khác nhau**: HRIS authority, attribute cache và application session.

### 8.2. TTL không phải công thức chung

TTL (time to live) của thuộc tính nên dựa trên:

- Mức rủi ro của quyền dùng thuộc tính đó.
- Tần suất thay đổi và thời hạn thu hồi cần đạt.
- Cơ chế invalidation/event push.
- Tính sẵn sàng và độ trễ của nguồn.
- Khả năng PDP/PEP kiểm tra lại trước hành động nhạy cảm.

Ví dụ dữ liệu \`employmentStatus\` dùng để chặn Leaver có yêu cầu mới hơn nhiều so với tên hiển thị để trang trí giao diện. **Không đặt cùng một TTL cho mọi thuộc tính chỉ để đơn giản hóa triển khai**.

## 9. Thuộc tính trong IdP, OIDC/SAML claims và phiên SSO

IdP thường đóng vai trò **nguồn cung cấp claims đã được ký**, nhưng cần hiểu giới hạn của chúng.

### 9.1. OIDC claims

Một RP có thể nhận ID token từ OP với các claim như \`sub\`, \`iss\`, \`aud\`, \`auth_time\`, \`acr\`, \`amr\` và một số claim nghiệp vụ được cấu hình.

Các kiểm soát:

1. Kiểm **chữ ký, issuer, audience, thời hạn và các ràng buộc giao thức** theo luồng OIDC.
2. Dùng **\`iss\` + \`sub\`** để liên kết tài khoản trong ngữ cảnh issuer, không mặc định email là khóa ổn định.
3. Kiểm ý nghĩa các claim nghiệp vụ dựa trên **hợp đồng với issuer**, không tin mọi claim có tên giống nhau.
4. Phân biệt **ID token dành cho RP** với **access token dành cho API**; resource server không nên nhận ID token như vật mang quyền API.
5. Đánh giá **claim freshness**: token có chữ ký đúng vẫn có thể mang quyền cũ tới khi hết hạn hoặc bị kiểm soát lại.

### 9.2. SAML attributes

SAML assertion có thể chứa các attributes như department hoặc group. SP phải kiểm **IdP issuer, chữ ký, audience, recipient, subject confirmation và thời gian** theo profile trước khi dùng attributes.

**Chấp nhận một SAML assertion hợp lệ không đồng nghĩa mọi attribute trong đó được quyền quyết định authorization.** Phải có mapping từ issuer/NameID và danh sách attributes được chấp nhận, cùng quy tắc quyền ứng dụng.

### 9.3. Claim snapshot so với PIP tra cứu trực tuyến

| Cách lấy attribute | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Claim trong token/assertion** | Kiểm được nguồn phát hành, giảm tra cứu ngoài, thuận tiện với SSO. | Là snapshot tại thời điểm phát hành; có thể stale sau Mover/Leaver. |
| **PIP query nguồn trực tuyến** | Có thể dùng trạng thái mới hơn, phù hợp quyền nhạy cảm. | Độ trễ, sự cố mạng, tải lên nguồn và tính sẵn sàng. |
| **PIP cache có invalidation** | Giảm độ trễ, hỗ trợ throughput cao. | Phải quản lý event ordering, TTL, cache key và tín hiệu thu hồi. |
| **Materialized entitlement/attribute store** | Tập trung dữ liệu chuẩn hóa, hỗ trợ audit và đối soát. | Cần provenance, phiên bản và pipeline đồng bộ đáng tin. |

Không có kiến trúc duy nhất tốt cho mọi trường hợp. Với quyền nhạy cảm và thay đổi vòng đời nhanh, nên kết hợp **giới hạn tuổi dữ liệu, kiểm lại trạng thái hiện tại và cơ chế thu hồi** phù hợp.

## 10. Directory và SCIM: nguồn dữ liệu hay bản sao được đồng bộ?

Directory, IdP và SaaS có thể cùng chứa \`department\`, \`manager\`, \`active\` hoặc group membership. Tuy nhiên **có cùng tên trường không đảm bảo cùng ý nghĩa**.

Ví dụ:

- HRIS \`employmentStatus=TERMINATED\`: trạng thái quan hệ làm việc.
- IAM \`lifecycleState=LEAVER\`: trạng thái chuẩn hóa của workflow.
- SCIM User \`active=false\`: trạng thái tài khoản tại service provider theo cơ chế ứng dụng.
- IdP account disabled: ngăn xác thực theo cơ chế IdP.
- App session \`valid=true\`: phiên đang được ứng dụng chấp nhận.

Không nên suy từ \`SCIM active=true\` rằng nhân viên vẫn có hợp đồng hợp lệ. Cũng không thể kết luận \`SCIM active=false\` đã thu hồi toàn bộ token/phiên/API key ở ứng dụng.

### 10.1. Khác biệt ID và schema

| Trường | Nguồn/ý nghĩa |
| --- | --- |
| **Directory object ID** | Định danh tài khoản trong một directory. |
| **SCIM \`id\`** | ID User do SCIM service provider cấp. |
| **SCIM \`externalId\`** | Mã tương quan do SCIM client cung cấp. |
| **SCIM \`userName\`** | Tên user ở provider; có thể thay đổi theo chính sách. |
| **OIDC \`sub\`** | Chủ thể theo issuer, không tự là ID ở SCIM. |

PIP phải tra đúng bản ghi theo **bảng mapping đã xác minh**, không chỉ so sánh email, displayName hoặc manager name.

### 10.2. Attribute provenance xuyên các bước đồng bộ

~~~text
HRIS (source of authority cho department)
       ↓  event + version + effectiveAt
IAM/IGA (chuẩn hóa và gắn subject/engagement)
       ↓
Directory/IdP (bản sao phục vụ xác thực và claim)
       ↓
SCIM User / ứng dụng (bản sao đích)
       ↓
PDP / PEP (dữ liệu quyền thực tế cần được kiểm soát)
~~~

Ở mỗi bước cần biết **giá trị được cập nhật khi nào, từ nguồn nào và có còn đúng không**. Một bản sao tại ứng dụng **không trở thành nguồn thẩm quyền** của thuộc tính nhân sự chỉ vì là nơi PEP dễ đọc nhất.

## 11. Resource attributes và nguy cơ thao túng nhãn tài nguyên

Chính sách ABAC có thể dựa vào **classification**, **owner**, **tenant**, **project** hoặc trạng thái hồ sơ. Vì vậy, quyền sửa metadata tài nguyên có tác động tương đương một quyền quản trị gián tiếp.

### 11.1. Ví dụ phân loại báo cáo

~~~json
{
  "resourceId": "report-7301",
  "tenantId": "tenant-a",
  "ownerDepartmentId": "FINANCE",
  "classification": "CONFIDENTIAL",
  "dataOwnerSubjectId": "person-2088",
  "state": "ACTIVE",
  "metadataVersion": 12
}
~~~

Nếu nhân viên có thể sửa \`classification\` từ \`CONFIDENTIAL\` thành \`PUBLIC\` mà không được kiểm tra quyền, họ có thể làm **hạ mức bảo vệ** của tài liệu và khiến PDP chấp nhận request vốn phải bị từ chối.

### 11.2. Các kiểm soát cần có

- Chỉ **data owner/governance process** có thẩm quyền được thay classification.
- Ghi **người sửa, phiên bản, lý do và phê duyệt** nếu thay nhãn nhạy cảm.
- Dùng ID tài nguyên/tenant đáng tin, tránh tình huống tham chiếu tài nguyên của tenant khác.
- Phân biệt thuộc tính **hệ thống tính** và thuộc tính **do người dùng nhập**.
- Nếu classification bị thiếu hoặc đang chờ phân loại, **không mặc định PUBLIC**.
- Với dữ liệu được sao chép hoặc export, kiểm phân loại áp dụng cho bản sao theo chính sách.

## 12. Environment attributes: ranh giới tin cậy của thiết bị, mạng và thời gian

Environment thay đổi nhanh hơn nhiều thuộc tính HRIS. Nguồn context phải được đo hoặc xác nhận tại **một điểm có thẩm quyền**.

### 12.1. IP và proxy

Ứng dụng có thể nhận \`X-Forwarded-For\` hoặc các header tương tự qua reverse proxy. **Không được tin header này từ Internet trực tiếp**. Chỉ chấp nhận khi request đến từ proxy/gateway đáng tin cậy và có quy tắc loại bỏ/ghi đè header từ client.

Một IP còn có thể là NAT/VPN dùng chung, không phải bằng chứng danh tính người dùng. IP-based policy nên là tín hiệu bổ sung, không thay thế xác thực.

### 12.2. Device posture

Giá trị \`deviceCompliant=true\` chỉ đáng tin nếu:

1. Device ID đã gắn với thiết bị thực và account/session theo cơ chế được phê duyệt.
2. Nguồn tín hiệu là MDM/EDR hoặc dịch vụ posture có xác thực.
3. Đã kiểm thời gian đánh giá, TTL, chính sách compliance và tính toàn vẹn dữ liệu.
4. Không nhận một boolean do ứng dụng khách tự gửi là chứng cứ.
5. Có quy tắc khi thiết bị bị mất, bị gỡ quản lý hoặc trạng thái compliance thay đổi.

### 12.3. Thời gian và timezone

Một policy “chỉ được truy cập trong giờ làm việc” phải xác định:

- Múi giờ nghiệp vụ (ví dụ **Asia/Ho_Chi_Minh**, nếu đây là chính sách của đơn vị đó).
- Nguồn giờ của server/PDP, kiểm đồng bộ đồng hồ.
- Quy tắc ngày lễ, cuối tuần và ca trực.
- Chuyển đổi từ **date-only** trong HRIS sang thời điểm hiệu lực.
- Cách xử lý lịch làm việc qua múi giờ và thay đổi giờ mùa hè tại những vùng áp dụng.

Đồng hồ thiết bị của người dùng không nên là nguồn có thẩm quyền cho policy giới hạn thời gian truy cập.

## 13. Quy tắc xử lý missing, null, stale và conflict

Những tình trạng thường gặp:

| Tình trạng | Ví dụ | Cách xử lý nguyên tắc |
| --- | --- | --- |
| **Missing** | PIP không nhận được department do lỗi connector. | Không suy ra user thuộc department mặc định; quyết định theo policy xử lý thiếu. |
| **Null** | HRIS xác nhận manager hiện chưa được chỉ định. | Phân biệt null có chủ ý với field bị bỏ khỏi một PATCH. |
| **Empty string** | \`departmentId=""\` sau làm sạch dữ liệu lỗi. | Không coi là giá trị hợp lệ nếu schema không cho phép. |
| **Stale** | Group/role được lấy từ cache trước thời điểm Mover. | Kiểm tuổi dữ liệu, invalidation và cơ chế truy xuất mới. |
| **Conflicting** | HRIS ghi FINANCE nhưng directory ghi SALES. | Dùng source authority matrix, ghi drift, không chọn bừa dữ liệu thuận lợi cho PERMIT. |
| **Unverifiable** | Claim không có issuer/chữ ký hợp lệ hoặc provenance. | Không đưa vào policy quyền nhạy cảm. |
| **Out of scope** | Thuộc tính lấy từ tenant B cho resource tenant A. | Từ chối/loại khỏi evaluation, điều tra mapping. |
| **Future-dated** | Mover sang Finance có hiệu lực tuần sau. | Không dùng giá trị mới trước effectiveAt. |
| **Expired approval** | Quyền dữ liệu hết hạn ngày hôm qua. | Không coi approval còn hợp lệ chỉ vì record vẫn tồn tại. |

### 13.1. Vì sao không nên tự “lấy giá trị mới nhất”?

Một bản ghi cập nhật lúc 10:00 có thể ghi **sự kiện áp dụng từ 12:00**, trong khi bản ghi cũ cập nhật lúc 09:59 vẫn là giá trị có hiệu lực tại 10:30. Ngược lại, một sự kiện Leaver bị chậm gửi đến 10:00 có thể có **effectiveAt=09:00**.

Chọn thuộc tính bằng **thời điểm nhận gần nhất** dễ sai. Hệ thống cần hiểu **nguồn thẩm quyền, version, effectiveAt và thời điểm đánh giá**.

### 13.2. Deny, NotApplicable và Indeterminate

Một PDP có thể biểu diễn kết quả như:

- **Permit**: policy cho phép khi các điều kiện đủ.
- **Deny**: policy từ chối rõ ràng.
- **NotApplicable**: không có policy áp dụng theo mô hình engine.
- **Indeterminate**: không thể đánh giá chắc chắn vì lỗi hoặc dữ liệu thiếu.

Tên kết quả phụ thuộc công nghệ và cơ chế kết hợp chính sách. **PEP không nên tự biến NotApplicable/Indeterminate thành Permit** nếu không có quy tắc an toàn được thiết kế và phê duyệt rõ. Phân biệt các trường hợp giúp quan sát nguyên nhân thay vì ghi mọi lần lỗi là “access denied” không rõ lý do.

## 14. Bảo vệ PIP và attribute supply chain

PIP có thể trở thành mục tiêu tấn công vì nó cung cấp dữ liệu quyết định quyền. Nếu attacker sửa nguồn hoặc làm giả phản hồi, PDP có thể cấp quyền sai dù engine không có lỗi logic.

### 14.1. Những rủi ro điển hình

| Rủi ro | Ví dụ | Biện pháp |
| --- | --- | --- |
| **Attribute spoofing** | Client tự gửi \`department=FINANCE\`. | PEP/PIP chỉ lấy từ nguồn xác thực có quyền. |
| **Unauthorized attribute write** | Người dùng tự sửa \`approvedDataLevel\`. | ACL/RBAC cho quyền ghi, approval và audit. |
| **Source impersonation** | Service giả mạo endpoint HRIS/PIP. | TLS, xác thực hai chiều/service identity khi phù hợp, kiểm issuer. |
| **Cross-tenant attribute leak** | PIP trả thuộc tính của user tenant khác. | Tenant-scoped queries, ID có namespace, negative tests. |
| **Cache poisoning** | Bản ghi sai được lưu lâu và phát cho nhiều PDP. | Integrity, cache key, invalidation, TTL và provenance. |
| **Replay/stale data** | Dùng lại assertion có quyền trước Leaver. | Token expiry, session invalidation, đọc trạng thái vòng đời hiện hành. |
| **Overbroad connector credential** | PIP có quyền đọc/ghi toàn directory. | Least privilege, secret manager và workload identity. |
| **Sensitive attribute exposure** | Trả dữ liệu HR/đánh giá nhân sự không cần thiết cho app. | Data minimization, projection và logging an toàn. |

### 14.2. PIP chỉ nên có quyền cần thiết

Một PIP dùng để đọc \`departmentId\` và \`engagementState\` không cần quyền **đổi role, reset password hoặc sửa HRIS**. Với các API nguồn, dùng principal dịch vụ riêng, scope tối thiểu, credential ngắn hạn/rotation phù hợp và giám sát truy vấn bất thường.

PIP cũng cần giới hạn truy vấn để tránh filter injection, thiếu pagination, overload hoặc đọc nhầm tenant. Những nguồn dữ liệu do khách hàng ngoài tổ chức quản lý cần được xử lý qua hợp đồng trust và schema được phê duyệt.

## 15. Chuẩn hóa schema và ngữ nghĩa thuộc tính

Một hệ thống có thể biểu diễn cùng ý tưởng bằng nhiều giá trị:

~~~text
HRIS: workerType = "FTE"
IGA:  workerType = "EMPLOYEE"
IdP:  employmentType = "fulltime"
App:  localUserClass = "staff"
~~~

**Không được so sánh chuỗi thô từ các hệ thống khác nhau mà chưa có mapping được phê duyệt**. Cần chuẩn hóa enum, kiểu dữ liệu, định danh và semantics.

### 15.1. Attribute contract

Một hợp đồng thuộc tính có thể ghi:

~~~yaml
# Schema quản trị nội bộ minh họa, không phải chuẩn ABAC bắt buộc.
attributeId: subject.engagementState
dataType: STRING
allowedValues: [PENDING, ACTIVE, SUSPENDED, TERMINATED]
authoritativeOwner: workforce-lifecycle-governance
sourceSystem: hris-primary
canonicalizationVersion: 3
identityKey: subjectId-plus-engagementId
effectiveTimeSemantics: event-effective-at
freshnessPolicy: security-critical
onMissingOrUnverifiable: INDETERMINATE
consumers:
  - finance-data-policy
  - workforce-application-policy
classification: INTERNAL
~~~

Chú ý \`freshnessPolicy: security-critical\` là nhãn yêu cầu thiết kế, **không phải TTL cụ thể**. Kế hoạch phải xác định thời hạn tối đa, invalidation và hành vi khi nguồn không hoạt động tùy rủi ro.

### 15.2. Đúng kiểu dữ liệu

- Boolean \`true\` không đồng nghĩa chuỗi \`"true"\`.
- Date-only \`2026-12-01\` khác timestamp \`2026-12-01T00:00:00Z\`.
- \`departmentId\` phải là mã canonical, không suy từ tên phòng ban hiển thị.
- Một người có thể thuộc **nhiều dự án/đơn vị**, nên thuộc tính multi-valued cần phép kiểm membership rõ ràng.
- Mức phân loại **PUBLIC/INTERNAL/CONFIDENTIAL** cần thứ tự do tổ chức định nghĩa, không xếp từ vựng.
- Giá trị **UNKNOWN** có thể là trạng thái dữ liệu riêng, không tự đồng nghĩa NONE hoặc DENY, trừ khi policy định nghĩa.

## 16. Attribute source trong Joiner

### 16.1. Tài khoản được tạo không đồng nghĩa thuộc tính đã có hiệu lực

Một nhân viên mới có thể được pre-provision vào directory trước **Start date**. HRIS ghi \`startDate=2026-12-01\`, còn directory đã có \`department=FINANCE\` từ 25/11.

Nếu policy chỉ kiểm \`department=FINANCE\`, người dùng có thể nhận quyền quá sớm. Một policy Joiner tốt thường cần **cả trạng thái quan hệ và thời điểm hiệu lực**:

~~~text
PERMIT Finance read nếu:
    subject.engagementState == ACTIVE
    AND trustedNow >= subject.activationAt
    AND subject.departmentId == FINANCE
    AND subject.financeAccessApproved == true
    AND accountState == ENABLED
    AND resource thuộc scope được phê duyệt
~~~

Điều kiện \`activationAt\` không nên suy từ \`recordCreatedAt\`. Nếu Start date bị hoãn, workflow phải nhận thay đổi và cập nhật dữ liệu/role/session theo policy, tránh cấp quyền dựa trên snapshot cũ.

### 16.2. Chuỗi nguồn trong Joiner

1. HRIS/hợp đồng xác minh đúng Person, Engagement, Start date, worker type.
2. IAM liên kết subject ID, tránh duplicate hoặc gắn nhầm email.
3. Directory/IdP nhận thuộc tính đã chuẩn hóa và tài khoản theo trạng thái chờ/hợp lệ.
4. IGA đánh giá chính sách quyền baseline/role, phê duyệt bổ sung nếu cần.
5. PIP cung cấp thuộc tính **có hiệu lực tại thời điểm request**.
6. PEP/PDP kiểm điều kiện người dùng, tài nguyên, action và environment.
7. Ứng dụng được provision qua SCIM/API khi phù hợp; quyền thực tế được xác minh sau khi kích hoạt.

**Không kết luận Joiner hoàn tất chỉ vì HRIS có hồ sơ hoặc PIP trả đúng phòng ban.** Cần kiểm trạng thái tài khoản và quyền ở ứng dụng đích.

## 17. Attribute source trong Mover

**Mover** là nơi ABAC phát huy tác dụng vì các thuộc tính như department, manager, project, assignment owner và risk level có thể thay đổi ngay cả khi credential IdP vẫn giữ nguyên.

### 17.1. Ví dụ Sales → Finance

| Thuộc tính | Trước 08:00 | Sau 08:00 | Nguồn có thẩm quyền |
| --- | --- | --- | --- |
| **engagementState** | ACTIVE | ACTIVE | HRIS/IAM. |
| **departmentId** | SALES | FINANCE | HRIS/org master. |
| **managerSubjectId** | manager-S | manager-F | HRIS. |
| **approvedScope** | sales-reports | finance-reports nếu đã phê duyệt | IGA/data owner. |
| **directoryGroup** | sales-reader | finance-reader sau đồng bộ | Directory/SCIM đích. |
| **applicationSessionRole** | Sales snapshot | Có thể chưa đổi ngay | App/session manager. |

Không nên cho phép FINANCE chỉ vì department vừa đổi nếu quyền đọc Finance còn cần **approval riêng**. Đồng thời, không nên giữ quyền SALES tới kỳ review sau khi Mover đã có hiệu lực nếu policy yêu cầu thu hồi ngay.

### 17.2. Các điểm sai lệch dễ phát sinh

- HRIS đã cập nhật nhưng PIP cache còn department cũ.
- IdP phát token cũ vì session vẫn còn.
- SCIM Group update thêm nhóm mới nhưng xóa nhóm cũ thất bại.
- App có local role trực tiếp ngoài directory.
- Một approval tạm theo dự án cũ chưa bị hết hạn/thu hồi.
- Manager mới chưa có ở provider đích nên workflow cập nhật bị lỗi.

**Cách xử lý:** tính **expected attributes/entitlements** theo nguồn và thời điểm có hiệu lực, đối chiếu **actual tại ứng dụng**, rồi thu hồi quyền cũ và cập nhật quyền mới theo chính sách. **MFA/SSO đăng nhập thành công không chứng minh Mover đã được áp dụng đầy đủ**.

## 18. Attribute source trong Leaver

Trong Leaver, một dữ liệu cực kỳ quan trọng là **trạng thái quan hệ và thời điểm chấm dứt**. Nguồn có thẩm quyền có thể là HRIS với Employee hoặc hệ thống hợp đồng/sponsor đối với Contractor, theo quy tắc đã định.

### 18.1. Luồng xử lý

1. Nhận sự kiện Leaver có \`subjectId\`, \`engagementId\`, \`effectiveAt\` và source version.
2. Cập nhật canonical lifecycle state và đánh dấu các attribute/approval không còn hợp lệ.
3. Phát tín hiệu invalidation tới các PIP cache/entitlement store liên quan.
4. Vô hiệu đăng nhập IdP/account theo chính sách; thu hồi token/phiên khi có khả năng.
5. Đồng bộ SCIM/API để disable tài khoản ứng dụng và thu hồi Group/role/entitlement.
6. Xử lý credential độc lập (PAT/API key), delegated access và đặc quyền có thể còn hoạt động.
7. Đối soát các API/resource quan trọng; ghi ngoại lệ khi chưa xác minh được quyền thực tế.

### 18.2. Vì sao thuộc tính \`ACTIVE\` trong token vẫn là rủi ro?

Giả sử HRIS ghi \`TERMINATED\` lúc 17:00, nhưng ID token phát lúc 16:50 chứa \`employeeActive=true\` và có hạn đến 17:50. Nếu resource server chỉ tin claim này và không kiểm lại lifecycle state hay dùng cơ chế thu hồi, **token có thể còn được chấp nhận trong thời gian hiệu lực**.

Các biện pháp tùy kiến trúc:

- Giảm TTL token và cache cho quyền nhạy cảm.
- Kiểm **current lifecycle/entitlement** tại API/PEP khi cần.
- Thu hồi IdP/application session, refresh token và grant theo tính năng provider.
- Dùng denylist/token version hoặc policy invalidation khi nền tảng hỗ trợ.
- Thu hồi local role, SCIM account và credential ngoài SSO.

**Xóa trường ACTIVE ở directory không mặc nhiên hủy session đã phát hành.** Phải xác minh đường thực thi cuối, nêu rõ cửa sổ truy cập tồn dư có thể xảy ra.

### 18.3. Rehire

Nếu người được tuyển lại, dữ liệu \`Person\` có thể liên kết cùng một người, nhưng **Engagement, approval và điều kiện quyền phải được đánh giá lại**. Không tự tái sử dụng các attribute \`approvedRole=true\`, role group hoặc token của engagement cũ.

## 19. Service account và workload attribute source

ABAC không chỉ áp dụng cho Employee. Một workload gọi API cũng có **subject attributes**:

| Thuộc tính workload | Nguồn phù hợp | Công dụng |
| --- | --- | --- |
| **principalId / serviceAccountId** | Cloud IAM / workload identity issuer. | Xác định chính xác danh tính máy. |
| **workloadId** | Orchestrator/registry đáng tin cậy. | Gắn principal với job/service thật. |
| **ownerTeamId** | Service catalog và governance. | Quản trị vòng đời/duyệt quyền. |
| **environment** | Orchestrator hoặc cloud metadata đã xác thực. | Phân biệt production/staging. |
| **deploymentVersion** | CI/CD attestation hoặc hệ thống triển khai. | Giới hạn phiên bản workload được phép. |
| **credentialValidity** | Issuer/token service. | Tránh key/token đã hết hạn hoặc bị thu hồi. |
| **approvedApiScope** | IAM/API owner. | Cấp đúng quyền đọc/ghi cần thiết. |

Không tin \`environment=production\` do workload tự gửi nếu không có identity attestation. Ví dụ một job thử nghiệm không được phép gọi API production chỉ bằng cách đổi nhãn trong HTTP payload.

### 19.1. Owner của workload rời tổ chức

Khi kỹ sư từng tạo service principal nghỉ việc:

- Service principal có thể cần tiếp tục hoạt động nếu workload hợp lệ.
- **Owner team** và người phê duyệt phải được chuyển giao.
- Thuộc tính quyền và secret đã cấp phải được rà soát; credential từng chia sẻ có thể cần rotate.
- Không giữ PAT của người nghỉ như credential cố định cho pipeline.
- Khi workload ngừng, decommission principal, role, credential và trust liên quan.

Leaver của người sở hữu **không tự động đồng nghĩa xóa tất cả workload**, nhưng cũng không thể bỏ mặc quyền máy mồ côi.

## 20. Quy trình quyết định ABAC với provenance

Một hệ thống có thể biểu diễn **attribute envelope** chứa cả giá trị và metadata:

~~~json
{
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "attributes": {
    "departmentId": {
      "value": "FINANCE",
      "sourceSystem": "hris-primary",
      "sourceRecordVersion": 24,
      "effectiveAt": "2026-12-01T08:00:00+07:00",
      "observedAt": "2026-12-01T01:00:30Z",
      "validated": true
    },
    "approvedDataLevel": {
      "value": "CONFIDENTIAL",
      "sourceSystem": "iga-access-governance",
      "approvalRef": "APR-501",
      "expiresAt": "2027-01-01T00:00:00+07:00",
      "validated": true
    }
  },
  "policyContext": {
    "policyId": "finance-read-access",
    "policyVersion": 7,
    "evaluatedAt": "2026-12-01T01:03:00Z"
  }
}
~~~

Đây là **JSON minh họa nội bộ**, không phải schema của OIDC, SCIM hay XACML. \`validated=true\` tự nó không mang giá trị bảo mật; nó phải là kết quả từ thành phần kiểm nguồn đáng tin, không phải field mà người gọi có thể tự đặt.

### 20.1. Giả mã thu thập và đánh giá

~~~text
authorizeRequest(request):
    subject = verifyAuthenticatedSubject(request)
    resource = resolveTrustedResourceAndTenant(request)
    action = deriveActionFromEnforcedEndpoint(request)

    if subject is invalid or resource is ambiguous:
        return DENY

    requirements = resolveRequiredAttributes(action, resource)
    attributes = {}
    for requirement in requirements:
        source = lookupApprovedSource(requirement.attributeId)
        result = fetchWithLeastPrivilege(source, subject, resource)
        if not verifyProvenanceIdentityTenantAndSchema(result):
            return INDETERMINATE
        if not isEffectiveAndFreshEnough(result, request.time):
            return INDETERMINATE
        attributes[requirement.attributeId] = result.value

    decision = evaluateVersionedPolicy(
        subject, resource, action, trustedEnvironment(request),
        attributes
    )

    recordDecisionTraceWithoutSecretsOrUnneededPII(decision)
    return decision
~~~

**Giả mã không phải implementation hoàn chỉnh.** PEP cần một quy tắc xử lý **INDETERMINATE** an toàn, các policy obligations/advice nếu engine hỗ trợ, kiểm concurrency giữa việc đánh giá và thực thi, kiểm quyền ở thao tác cuối, timeout và circuit breaker. Với action nhiều bước, có thể cần kiểm lại quyền tại thời điểm commit nếu dữ liệu/quan hệ thay đổi.

### 20.2. Decision cache

Cache quyết định **PERMIT** nguy hiểm hơn cache dữ liệu hiển thị đơn thuần vì có thể tiếp tục cho truy cập sau Mover/Leaver.

Cache key nên xét đúng **subject/engagement, resource, action, tenant, policy version và điều kiện ngữ cảnh liên quan**. Cần cơ chế invalidation khi đổi lifecycle, scope, resource classification hoặc quyền. Với quyền nhạy cảm, có thể yêu cầu evaluation mới hoặc kiểm tra trạng thái hiện hành tại PEP.

## 21. Xử lý lỗi nguồn thuộc tính mà không cấp quyền sai

| Sự cố | Hệ quả | Cách xử lý đề xuất |
| --- | --- | --- |
| **HRIS outage** | Không kiểm được lifecycle state mới nhất. | Dùng quy tắc freshness được phê duyệt, hạn chế quyền nhạy cảm khi không chắc chắn; mở incident. |
| **Directory connector chậm** | Group/department tại IdP cũ. | So với authority, đo lag và invalidation, không coi nhóm cũ mặc nhiên đúng. |
| **IdP token cũ** | Role/department snapshot chưa cập nhật. | Kiểm token lifetime và policy hiện hành tại API khi cần. |
| **Resource catalog thiếu classification** | Có nguy cơ coi dữ liệu nhạy cảm là PUBLIC. | Không cấp quyền vượt ngưỡng khi thiếu nhãn; yêu cầu phân loại. |
| **Device posture không truy cập được** | Không chứng minh thiết bị compliant. | Áp dụng policy khi tín hiệu bắt buộc unavailable; đừng tin client flag. |
| **Tenant mapping lỗi** | Lấy thuộc tính người khác/khách hàng khác. | Chặn truy cập và điều tra mapping, không retry bừa gây leak. |
| **Event Leaver đến trễ** | Attribute ACTIVE có thể tồn tại quá thời điểm kết thúc. | Ưu tiên thu hồi, điều tra cửa sổ tồn dư và đối soát. |
| **Cache invalidation lỗi** | Quyền cũ còn hiệu lực dù dữ liệu nguồn đúng. | Cắt TTL/denylist phù hợp, alert và verify ở PEP. |
| **SCIM update thành công nhưng app role chưa đổi** | Tính quyền ABAC ở app khác expected. | Đọc lại local entitlements, role mapping và session. |

Không gộp mọi lỗi thành “User không có quyền”. Phân loại **thiếu dữ liệu**, **sai nguồn**, **policy từ chối**, **provider timeout** giúp khắc phục đúng lớp và tránh thay role/mật khẩu không cần thiết.

## 22. Truy vết và kiểm toán Attribute source

Mỗi quyết định ABAC quan trọng cần giải trình được:

1. **Ai/điều gì** yêu cầu truy cập, subject đã được xác thực ra sao?
2. **Tài nguyên** và **action** là gì, trong tenant/nhóm dữ liệu nào?
3. **Policy ID/version** nào đã được áp dụng?
4. **Những thuộc tính nào được dùng**, nguồn nào sở hữu và phiên bản dữ liệu nào?
5. Các thuộc tính **được lấy, xác minh và có hiệu lực lúc nào**?
6. Kết quả là **Permit/Deny/Indeterminate** hay tình trạng khác theo engine, tại sao?
7. **PEP thực sự cho phép/từ chối** thao tác nào?
8. Có sự kiện **JML, approval, exception, incident** nào liên quan?

### 22.1. Bằng chứng tối thiểu

| Trường | Lý do lưu |
| --- | --- |
| **eventId / traceId** | Liên kết PEP, PDP, PIP và logs ứng dụng. |
| **subjectId / engagementId** | Chứng minh đúng người và quan hệ có hiệu lực. |
| **resourceId / tenantId / action** | Định vị đối tượng và thao tác bị kiểm soát. |
| **policyId / policyVersion** | Tái dựng logic quyết định. |
| **attributeId / sourceId / sourceVersion** | Biết nguồn và bản dữ liệu đã dùng. |
| **observedAt / effectiveAt / evaluatedAt** | Đánh giá tính mới/hiệu lực và thời gian phản ứng. |
| **trust/freshnessValidationOutcome** | Phân biệt giá trị được kiểm chứng và chưa tin cậy. |
| **decision / enforcementOutcome** | Tách quyết định PDP với hành động PEP. |
| **exceptionId / owner / dueAt** | Theo dõi trường hợp chưa khép kín. |

Ví dụ log đã tối thiểu hóa dữ liệu:

~~~json
{
  "eventType": "ABAC_ACCESS_DECISION",
  "traceId": "access-20261201-0481",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "resourceId": "report-7301",
  "tenantId": "tenant-a",
  "action": "read",
  "policyId": "finance-read-access",
  "policyVersion": 7,
  "attributeSources": [
    {"attributeId": "subject.departmentId", "sourceId": "hris-primary", "sourceVersion": "24"},
    {"attributeId": "resource.classification", "sourceId": "data-catalog", "sourceVersion": "12"}
  ],
  "attributeValidation": "PASSED",
  "decision": "PERMIT",
  "enforcementOutcome": "ALLOWED",
  "evaluatedAt": "2026-12-01T01:03:00Z"
}
~~~

Đây là **audit schema minh họa**, không phải định dạng chuẩn của một PDP. Với dữ liệu nhân sự nhạy cảm, có thể lưu **source/version/reference** thay vì giá trị thuộc tính đầy đủ. Audit cần phân quyền, bảo vệ tính toàn vẹn, thời hạn lưu và truy xuất có mục đích.

### 22.2. Không lưu thông tin xác thực trong trace

Không ghi **mật khẩu, OTP, raw SAML assertion, ID/access/refresh token, cookie phiên, API key, client secret hoặc private key** để điều tra ABAC. Các giá trị có thể tái sử dụng để truy cập phải được loại bỏ khỏi log; chỉ lưu metadata an toàn.

**“PDP đã trả PERMIT”** khác với **“API đã cho phép thao tác”**. Khi điều tra một sự cố, cần có cả decision trace và log thực thi, vì PEP có thể bỏ qua chính sách hoặc ứng dụng có đường truy cập khác.

## 23. Case study: đổi phòng ban nhưng còn quyền do attribute stale

**Bối cảnh:** tổ chức có HRIS làm nguồn cho \`departmentId\`, IGA làm nguồn cho phê duyệt quyền và ứng dụng báo cáo sử dụng ABAC. Nhân viên Minh chuyển từ **SALES** sang **FINANCE**, có hiệu lực 08:00 ngày 01/12. Hệ thống dùng PIP cache để giảm độ trễ.

| Thời điểm giả định | Sự kiện | Quan sát / tác động |
| --- | --- | --- |
| **30/11 16:00** | HRIS phát Mover, hiệu lực 01/12 08:00. | Có sự kiện tương lai, chưa đổi quyền trước hạn. |
| **01/12 08:00** | IAM xác nhận departmentId=FINANCE có hiệu lực. | Thuộc tính quyền cũ SALES không còn là nguồn được phép dùng. |
| **01/12 08:01** | PIP của ứng dụng vẫn trả \`departmentId=SALES\`. | Cache stale có thể dẫn tới PERMIT dữ liệu Sales sai. |
| **01/12 08:02** | Một yêu cầu đọc dữ liệu Sales được PEP chấp nhận. | Tín hiệu quyền truy cập tồn dư cần điều tra. |
| **01/12 08:03** | Audit so sánh source version PIP với HRIS, phát hiện lệch. | Định vị được nguồn lỗi và cửa sổ rủi ro. |
| **01/12 08:04** | IAM gửi invalidation, ứng dụng giới hạn quyền cũ theo policy. | Giảm truy cập ngoài phạm vi trong khi đồng bộ. |
| **01/12 08:06** | PIP trả departmentId=FINANCE với version đúng. | Thuộc tính đã đúng, chưa chứng minh mọi phiên đã được cập nhật. |
| **01/12 08:08** | Ứng dụng kiểm tra phiên cũ và effective permissions. | Phát hiện/thu hồi local role hoặc claim cache còn Sales. |
| **01/12 08:10** | Kiểm thử quyền được ủy quyền xác nhận Finance hợp lệ và Sales bị từ chối. | Có bằng chứng đóng sai lệch trong phạm vi đã kiểm. |

### 23.1. Bài học rút ra

1. **Policy ABAC không sai về cú pháp** nhưng PIP lấy thuộc tính từ cache cũ.
2. **HRIS đã cập nhật đúng** không tự bảo đảm API đã sử dụng thông tin đúng.
3. IdP hoặc SCIM cập nhật mới không mặc nhiên thu hồi **application session** trước đó.
4. Cần đo **attribute freshness và effective access**, không chỉ HTTP success của connector.
5. Invalidation phải xử lý cả **source version, cache, token/phiên và local entitlement** liên quan.
6. Một quyền Finance cần approval riêng vẫn phải được phê duyệt dù Minh đã chuyển bộ phận.

### 23.2. Nếu sự kiện là Leaver thay vì Mover?

Nếu HRIS đã xác nhận Minh **TERMINATED**, rủi ro cao hơn vì các đường xác thực và quyền ứng dụng đều phải chấm dứt theo policy. Cần ưu tiên disable IdP, thu hồi phiên/credential, deprovision tài khoản, chặn PERMIT dựa trên \`ACTIVE\` stale và kiểm tra API còn chấp nhận token cũ hay không.

## 24. Chỉ số đánh giá chất lượng Attribute source

| Chỉ số | Cách đo gợi ý | Rủi ro được phát hiện |
| --- | --- | --- |
| **Tỷ lệ attribute có authoritative owner** | Attribute dùng trong policy có source/owner/contract rõ ÷ tổng attribute trong phạm vi. | Thuộc tính không ai chịu trách nhiệm. |
| **Tỷ lệ identity mapping đã xác minh** | Subject-attribute mapping đúng person/engagement/tenant ÷ tổng mapping. | Ghép nhầm người hoặc tenant. |
| **Độ trễ cập nhật JML** | Từ effectiveAt tới khi PIP/PEP dùng trạng thái mới được xác minh. | Quyền tồn dư khi Mover/Leaver. |
| **Tỷ lệ attribute đạt freshness** | Giá trị trong decision trace nằm trong giới hạn tuổi theo policy ÷ số lần dùng attribute. | Cache/token stale. |
| **Số conflict giữa các nguồn** | Trường hợp source authority và bản sao cho giá trị khác nhau. | Mapping sai, connector drift. |
| **Tỷ lệ quyết định Indeterminate** | Decision không thể đánh giá do thiếu nguồn/attribute ÷ tổng decision. | Phụ thuộc nguồn kém sẵn sàng. |
| **Tỷ lệ quyết định audit đầy đủ provenance** | Có policy version, attribute source/version, thời gian và enforcement outcome ÷ tổng quyết định cần kiểm toán. | Khó giải trình hoặc điều tra. |
| **Số PERMIT được xác minh sai do stale attribute** | Trường hợp thực tế chấp nhận request với dữ liệu quá hạn/không được phép. | Kiểm soát bị vượt vì nguồn dữ liệu. |
| **Tỷ lệ API kiểm authorization ở PEP** | Tài nguyên nhạy cảm thực sự dùng policy phù hợp ÷ tài nguyên phải kiểm. | Đường truy cập bỏ qua PDP. |
| **Số tài khoản Leaver còn được API chấp nhận** | Truy cập sau thời điểm chấm dứt, đã xác minh theo phạm vi. | Thu hồi quyền chậm, token/phiên tồn dư. |
| **Tỷ lệ data classification có owner** | Tài nguyên có nhãn phân loại được quản trị ÷ tổng tài nguyên cần phân loại. | Hạ mức bảo vệ do metadata sai. |
| **Số ngoại lệ attribute quá hạn** | Missing/stale/conflict chưa được giải quyết đúng thời hạn. | Nợ bảo mật từ chất lượng dữ liệu. |

Không nên đưa ra một TTL hoặc ngưỡng tỷ lệ cố định cho mọi nguồn. Mỗi chỉ số cần mô tả **phạm vi, policy, nguồn quan sát, mức độ bao phủ và các hệ thống chưa có bằng chứng**.

## 25. Checklist thiết kế và vận hành Attribute source

1. Đã phân biệt **attribute source**, **authoritative source**, **claim**, **derived attribute** và **policy input** chưa?
2. Mỗi attribute dùng cho PERMIT có **owner, namespace, schema, nguồn gốc, effectiveAt và giới hạn độ tươi** không?
3. Có phân loại rõ **subject, resource, action và environment attributes** không?
4. Hệ thống có liên kết đúng **subjectId, engagementId, issuer + sub, SCIM id, resourceId và tenantId** không?
5. Có ngăn **email/displayName** được dùng làm khóa duy nhất để gắn thuộc tính quyền không?
6. PIP/PDP/PEP có **trust boundary**, xác thực service-to-service và quyền truy vấn tối thiểu không?
7. Các attribute do client gửi (department, tenant, role, device compliance, network zone) có được **kiểm chứng hoặc loại bỏ nếu không có thẩm quyền** không?
8. Có **source authority matrix** cho HRIS, IdP, IGA, directory, resource catalog, MDM và application không?
9. Có cơ chế phân biệt **missing, null, stale, expired, conflicting, future-dated** thay vì mặc định PERMIT không?
10. Token OIDC/SAML có được kiểm **issuer, audience, chữ ký, thời hạn** và ý nghĩa claim theo hợp đồng không?
11. Có biết claim/token/session là **snapshot**, có thể không phản ánh JML mới nhất không?
12. Resource classification/ownership có bị người không đủ thẩm quyền sửa để hạ mức bảo vệ không?
13. Với action, API/PEP có suy ra **hành động thật** từ endpoint thay vì tin field do caller tự khai không?
14. Với environment, có kiểm nguồn **device posture, network/proxy và trusted time** không?
15. **Joiner** có dùng Start date/activationAt và approval trước khi ABAC cấp quyền không?
16. **Mover** có cập nhật attribute đúng thời điểm, vô hiệu cache/claim cũ và **thu hồi quyền cũ** không?
17. **Leaver** có chặn quyền dựa trên \`ACTIVE\` stale, xử lý session/token, SCIM/ứng dụng và API credential ngoài IdP không?
18. Workload/service principal có owner, trust, scope, environment và credential lifecycle riêng không?
19. PIP/PDP có phân biệt **Deny/NotApplicable/Indeterminate** và fail-safe theo policy thay vì tự cho qua khi nguồn lỗi không?
20. Có đối soát **nguồn có thẩm quyền → PIP attributes → PDP decision → PEP enforcement → application access** không?
21. Có kiểm soát **source version, cache TTL/invalidation, event ordering, retry và tài khoản tái tuyển dụng** không?
22. Log có thể tái dựng **policy version, attribute provenance, effectiveAt, decision/enforcement** mà không chứa raw token, password hoặc PII không cần thiết không?
23. Có chỉ số cho **attribute drift, freshness, missing/conflict, PERMIT sai và quyền tồn dư sau JML** không?

**Ghi nhớ:** **Attribute source trong ABAC quyết định độ tin cậy của dữ liệu đầu vào cho chính sách truy cập**. Một rule đúng sẽ không an toàn nếu thuộc tính đến từ **nguồn sai, người sai, tenant sai, thời điểm sai hoặc bản sao đã cũ**. Thiết kế IAM phải xác định **nguồn có thẩm quyền cho từng thuộc tính**, bảo vệ đường lấy dữ liệu qua **PIP–PDP–PEP**, kiểm provenance/freshness/effectiveAt, xử lý thiếu/xung đột theo policy an toàn và đối soát tại hệ thống thực thi. Gắn kiểm soát này với **Joiner–Mover–Leaver**, IdP/SSO/SCIM và tài khoản dịch vụ mới giúp thay đổi quyền đúng lúc, phát hiện quyết định sai và giảm quyền truy cập tồn dư có thể giải trình bằng kiểm toán.
