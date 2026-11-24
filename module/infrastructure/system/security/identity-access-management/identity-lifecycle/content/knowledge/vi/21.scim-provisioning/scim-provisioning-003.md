# SCIM Group: Đồng bộ nhóm và thành viên trong vòng đời danh tính IAM

> **Chương: SCIM provisioning.** SCIM (**System for Cross-domain Identity Management**) là tập hợp các schema và giao thức HTTP để quản lý danh tính giữa các miền hệ thống. **SCIM Group** biểu diễn một nhóm và các thành viên thuộc nhóm đó, giúp bộ phận IAM đồng bộ đối tượng User và quan hệ nhóm từ nguồn quản trị sang ứng dụng đích. Trong mô hình **Joiner–Mover–Leaver**, đồng bộ Group rất quan trọng để cấp quyền nền, thay đổi nhóm khi chuyển vị trí và thu hồi quyền khi người dùng rời tổ chức. Tuy nhiên, **Group membership không tự đồng nghĩa với quyền hiệu lực**, và cập nhật SCIM thành công không bảo đảm phiên đăng nhập, token hoặc quyền cục bộ đã thay đổi ngay.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **SCIM Group** là gì, phân biệt Group resource với IdP group, role nghiệp vụ, entitlement và policy RBAC/ABAC.
2. Đọc cấu trúc **Core Group schema**, gồm id, externalId, displayName, members, $ref, type và meta; hiểu các khóa thuộc namespace khác nhau.
3. Mô tả các thao tác **GET, POST, PUT, PATCH, DELETE** với Group và quan hệ thành viên; xử lý filter, phân trang, phiên bản tài nguyên và lỗi API.
4. Thiết kế đồng bộ nhóm từ nguồn có thẩm quyền qua IdP/IGA/SCIM tới ứng dụng, tránh gán nhầm User hoặc nhóm.
5. Áp dụng Group provisioning trong **Joiner–Mover–Leaver**, kiểm soát nhóm đặc quyền, quyền truy cập tồn dư, tài khoản dịch vụ và phê duyệt.
6. Xây dựng quy trình đối soát, retry/idempotency, kiểm thử âm, nhật ký kiểm toán và các chỉ số vận hành.

## 1. SCIM Group là gì?

Trong một tổ chức, phòng ban hoặc vai trò có thể tương ứng với các nhóm: Finance-Readers, CRM-Support, Developers, OnCall-Operators. Nhóm giúp quản trị quan hệ thành viên một cách tập trung thay vì cấp từng quyền một cho từng tài khoản.

**SCIM Group** là **một tài nguyên** được định nghĩa trong SCIM 2.0. Nó chứa thông tin nhận diện nhóm và danh sách thành viên, thường được truy cập qua endpoint **/Groups** của một SCIM Service Provider. SCIM Client có thể là một thành phần của IdP, IAM/IGA hoặc hệ thống provisioning khác được ủy quyền.

Ví dụ: khi nhân viên Lan vào đội Engineering, IAM xác định Lan cần nhóm Engineering-Reader. Bộ provisioning có thể tạo hoặc tìm Group tương ứng tại ứng dụng kho mã nguồn, rồi thêm **local SCIM User ID** của Lan vào Group. Khi Lan chuyển sang Finance, Group membership cũ cần được gỡ và membership mới được cấp theo chính sách.

### Group khác gì role và quyền?

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **SCIM Group resource** | Bản ghi nhóm tại ứng dụng, có ID và danh sách thành viên. | Group Engineering-Reader tại hệ thống Git. |
| **IdP/directory group** | Nhóm quản trị tại IdP hoặc directory nguồn. | Đối tượng nhóm của nền tảng xác thực doanh nghiệp. |
| **Business role** | Vai trò do nghiệp vụ định nghĩa, có thể ánh xạ sang nhiều nhóm/quyền. | Nhân viên kế toán được xem báo cáo thu chi. |
| **Application role** | Vai trò do ứng dụng hiểu và thực thi. | CRM Viewer, Project Editor. |
| **Entitlement** | Một quyền, membership, license, role hoặc đặc quyền được cấp. | Được đọc repository project-a. |
| **RBAC** | Phân quyền theo vai trò. | SupportAgent có quyền xử lý ticket được phân công. |
| **ABAC** | Phân quyền dựa trên thuộc tính và ngữ cảnh. | Chỉ xem dữ liệu trong đúng tenant, đơn vị và trạng thái làm việc. |

**Group không phải một phép cấp quyền chuẩn hóa trên mọi ứng dụng.** Một SCIM Service Provider có thể dùng Group chỉ để tổ chức User, hoặc tự ánh xạ Group sang vai trò, license và quyền cục bộ theo cấu hình riêng. Cùng tên nhóm ở hai ứng dụng chưa chắc cho cùng một quyền.

### SCIM dùng để provisioning, không phải đăng nhập

SCIM hỗ trợ đồng bộ User/Group; **OIDC/SAML/SSO** phục vụ xác thực liên thông. Việc một người được thêm vào SCIM Group không chứng minh họ đã được identity proofing, đã đăng nhập bằng MFA hoặc đã được Resource Server cho phép thực hiện thao tác.

Ngược lại, User đăng nhập thành công qua SSO không chứng minh Group membership tại CRM hoặc Git đã đúng. Cần tách **authentication**, **account provisioning** và **authorization**.

## 2. Những thành phần trong mô hình SCIM Group

SCIM 2.0 sử dụng các khái niệm **SCIM Client**, **Service Provider**, **User resource**, **Group resource** và các schema xác định kiểu dữ liệu.

~~~mermaid
flowchart LR
    HR["HR / nguồn hợp đồng<br/>Joiner–Mover–Leaver"] --> IAM["IAM / IGA<br/>identity + policy"]
    IAM --> IDP["IdP / directory<br/>source groups"]
    IDP --> SCIM["SCIM Client / connector"]
    IAM --> SCIM
    SCIM --> SP["SCIM Service Provider<br/>/Users và /Groups"]
    SP --> APP["Ứng dụng đích<br/>app role / resource policy"]
    APP --> API["Resource/API<br/>kiểm tra quyền hiệu lực"]
    SCIM --> AUD["Audit / reconciliation"]
    SP --> AUD
~~~

**Nguồn quyết định ai thuộc nhóm** thường là policy IAM/IGA hoặc nhóm từ IdP đã được giao quyền quản trị. **SCIM Service Provider** lưu trạng thái account và group ở đích. Ứng dụng đích quyết định việc Group đó ảnh hưởng tới quyền nghiệp vụ thế nào.

### Không mặc định tất cả nhà cung cấp đều hỗ trợ như nhau

Trước khi thiết kế connector, cần kiểm tra:

- Ứng dụng có endpoint **/Groups** và ResourceType Group hay không.
- Có hỗ trợ đọc, tạo, cập nhật, PATCH, xóa Group và thay đổi members không.
- Có hỗ trợ **filter, pagination, ETag, concurrency control** và những thao tác PATCH cần thiết không.
- Có hỗ trợ **Group lồng nhau** hoặc **membership của Group khác** hay chỉ hỗ trợ User.
- Group membership có ánh xạ thành role/license/access tại ứng dụng không, hay chỉ là dữ liệu directory.
- Ai là chủ sở hữu Group ở đích? Nếu ứng dụng cũng cho quản trị viên chỉnh tay, ai được quyền ghi đè?
- Có giới hạn tenant, số member, tần suất API và độ trễ đồng bộ được công bố hay không.

SCIM cung cấp khả năng chuẩn hóa API, **không buộc mọi sản phẩm phải thực hiện mọi kiểu quyền hoặc quan hệ nhóm theo cùng cách**.

## 3. Core Group schema và các thuộc tính

SCIM 2.0 định nghĩa Group resource với schema URN:

~~~text
urn:ietf:params:scim:schemas:core:2.0:Group
~~~

Một tài nguyên Group minh họa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "id": "group-git-301",
  "externalId": "IAM:ENGINEERING_READER",
  "displayName": "Engineering-Reader",
  "members": [
    {
      "value": "user-git-102",
      "$ref": "https://git.example.org/scim/v2/Users/user-git-102",
      "type": "User",
      "display": "Lan Nguyen"
    },
    {
      "value": "user-git-245",
      "$ref": "https://git.example.org/scim/v2/Users/user-git-245",
      "type": "User",
      "display": "Minh Tran"
    }
  ],
  "meta": {
    "resourceType": "Group",
    "location": "https://git.example.org/scim/v2/Groups/group-git-301",
    "version": "W/\"group-v8\""
  }
}
~~~

Đây là dữ liệu giả để minh họa schema; không phải Group ID hay endpoint thực. Giá trị meta.version và cơ chế ETag phụ thuộc phía nhà cung cấp.

### Ý nghĩa từng trường

| Thuộc tính | Ý nghĩa | Lưu ý quan trọng |
| --- | --- | --- |
| **schemas** | Danh sách schema URN mô tả Group resource. | Core Group dùng URN riêng, khác Core User. |
| **id** | Định danh tài nguyên do Service Provider cấp. | Chỉ có ý nghĩa trong phạm vi Service Provider/tenant; không tự bằng IdP group ID. |
| **externalId** | Định danh do SCIM Client cấp để liên kết tài nguyên với nguồn. | Cần namespace và quản trị uniqueness; không mặc định mọi đích tự bảo đảm duy nhất. |
| **displayName** | Tên hiển thị của Group. | Là thuộc tính chính của Group, nhưng không nên dùng làm khóa liên kết duy nhất. |
| **members** | Tập các tham chiếu tới thành viên Group. | Phải so theo ID/tham chiếu, không so theo tên hiển thị. |
| **members[].value** | ID của User hoặc Group resource là thành viên tại chính Service Provider. | Thường là **local SCIM resource ID**, không phải HR employeeId. |
| **members[].$ref** | URI tham chiếu tới tài nguyên thành viên. | Phải phù hợp namespace và resource được chấp nhận; không tin URL tùy ý. |
| **members[].type** | Kiểu tham chiếu, thường là User hoặc Group. | Group member dạng Group chỉ có ý nghĩa nếu đích hỗ trợ lồng nhóm. |
| **members[].display** | Nhãn hỗ trợ hiển thị. | Không dùng làm căn cứ xác thực người hoặc liên kết tài khoản. |
| **meta** | Metadata như resourceType, location, version. | Có thể dùng version/ETag hỗ trợ tránh ghi đè cập nhật đồng thời. |

**Phân biệt ID:** HR có EMP-2041; IAM có identityId ID-2041; IdP có User ID idp-u-82; Git SCIM có User ID user-git-102. Khi thêm Lan vào Git Group, phải dùng **ID User mà Git SCIM Service Provider nhận biết**, không tùy ý lấy EMP-2041 hoặc idp-u-82 làm members.value.

### Group có thể chứa Group khác?

SCIM Group members có thể tham chiếu tới User hoặc Group theo mô hình dữ liệu. Tuy nhiên, **không phải mọi Service Provider đều hỗ trợ nested groups**, và hành vi quyền của nhóm lồng nhau không được bảo đảm chỉ bởi việc có một reference kiểu Group.

Nếu nền tảng đích hỗ trợ lồng nhóm, cần làm rõ:

- Quyền có kế thừa theo quan hệ lồng nhóm hay chỉ hiển thị quan hệ?
- Có ngăn nhóm tự tham chiếu hoặc chu kỳ A → B → A không?
- Có giới hạn độ sâu và số member hay không?
- Khi người dùng rời nhóm con, quyền do nhóm cha có biến mất theo thời hạn đúng không?
- API trả thành viên trực tiếp hay đã gồm thành viên hiệu lực qua nhóm lồng?

**Không giả định Group.members tự thể hiện đầy đủ effective entitlements** của một User.

## 4. Ánh xạ nhóm qua HR, IAM, IdP và ứng dụng

Một nhóm có thể tồn tại ở nhiều hệ thống dưới các ID và tên khác nhau:

| Lớp | Định danh ví dụ | Vai trò |
| --- | --- | --- |
| Nguồn tổ chức/policy | BUSINESS_ROLE:ENGINEERING_READER | Quy tắc nghiệp vụ cấp quyền. |
| IAM/IGA | IAM-GROUP-18 | Đối tượng nhóm/entitlement được quản trị. |
| IdP/directory | idp-group-919 | Nhóm IdP cung cấp dữ liệu cho ứng dụng/connector. |
| Git SCIM tenant A | group-git-301 | Group resource ID tại Git. |
| CRM SCIM tenant B | crm-group-225 | Group resource ID tại CRM, có thể ánh xạ quyền khác. |

Nên quản lý bảng mapping rõ ràng:

~~~json
{
  "sourceGroupKey": "IAM:ENGINEERING_READER",
  "targetSystem": "GIT",
  "targetTenant": "tenant-a",
  "targetGroupId": "group-git-301",
  "targetDisplayName": "Engineering-Reader",
  "lastObservedAt": "2026-12-01T08:00:00+07:00",
  "ownership": "IAM_MANAGED"
}
~~~

Đây là mô hình bảng mapping nội bộ, không phải schema SCIM. Khi Group đổi displayName, ID và quan hệ mapping vẫn phải truy vết được. Không tái tạo một Group mới chỉ vì displayName thay đổi.

### Chọn nguồn có thẩm quyền theo loại nhóm

| Loại nhóm | Nguồn quản trị hợp lý | Kiểm soát cần có |
| --- | --- | --- |
| **Birthright** | IAM policy dựa trên quan hệ công việc, bộ phận và loại nhân sự. | Tự động thêm/gỡ theo ngày hiệu lực và least privilege. |
| **Role nghiệp vụ có phê duyệt** | IGA workflow và resource owner. | Phê duyệt, SoD, thời hạn và rà soát. |
| **Nhóm dự án** | Project owner hoặc hệ thống quản trị dự án có ủy quyền. | Phạm vi project, ngày hết nhiệm vụ, thay đổi owner. |
| **Nhóm đặc quyền** | PAM/IGA và chủ sở hữu an ninh. | MFA mạnh, JIT khi cần, phê duyệt độc lập, audit. |
| **Nhóm ứng dụng sở hữu** | Ứng dụng đích. | Connector không tự ghi đè ngoài phạm vi được giao. |
| **Nhóm workload** | Service registry/owner kỹ thuật. | Mục đích, môi trường, scope và thời hạn workload. |

**Một Group có thể có các thuộc tính do nhiều bên quản lý**, nhưng cần xác định chính xác field ownership và membership ownership. Nếu IdP và ứng dụng cùng cập nhật member không theo quy tắc, hai bên có thể liên tục thêm rồi gỡ cùng một người.

## 5. Tạo, truy vấn và liệt kê SCIM Group

Các ví dụ HTTP sau dùng endpoint giả, token đã che và chủ yếu mô tả hành vi SCIM 2.0. Cần dùng HTTPS/TLS, credential riêng của connector và quyền API tối thiểu trong môi trường thật.

### Khám phá khả năng Service Provider

Trước khi thao tác với Group, có thể kiểm tra thông tin phục vụ khám phá:

~~~http
GET /scim/v2/ServiceProviderConfig HTTP/1.1
Host: app.example.org
Accept: application/scim+json
Authorization: Bearer [REDACTED]
~~~

~~~http
GET /scim/v2/ResourceTypes HTTP/1.1
Host: app.example.org
Accept: application/scim+json
Authorization: Bearer [REDACTED]
~~~

Nhà cung cấp cũng có thể hỗ trợ endpoint **/Schemas**. Cần kiểm tra Group có thực sự được khai báo, những thuộc tính nào được đọc/ghi và phương thức PATCH/filter có được hỗ trợ. Không tự suy diễn rằng ServiceProviderConfig cho phép PATCH nghĩa là mọi Group path hoặc kiểu lồng nhóm đều có cùng semantics.

### Tạo Group bằng POST

~~~http
POST /scim/v2/Groups HTTP/1.1
Host: app.example.org
Content-Type: application/scim+json
Accept: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "externalId": "IAM:ENGINEERING_READER",
  "displayName": "Engineering-Reader",
  "members": []
}
~~~

Phản hồi tạo thành công thường có mã **201 Created**, Group resource ID, location và metadata tùy khả năng. Connector phải **lưu local Group ID phía đích** để cập nhật sau đó.

**Không tự coi POST là idempotent.** Nếu request bị timeout nhưng Service Provider đã tạo Group, gửi POST lần hai có thể tạo nhóm trùng hoặc nhận lỗi conflict. Cần tìm lại theo mapping/externalId và xác nhận đúng tài nguyên trước khi tạo lại.

### Đọc Group theo ID

~~~http
GET /scim/v2/Groups/group-git-301 HTTP/1.1
Host: app.example.org
Accept: application/scim+json
Authorization: Bearer [REDACTED]
~~~

Đọc theo ID giúp kiểm tra displayName, members và phiên bản khi nhà cung cấp trả về đủ dữ liệu. Một Group ID không tồn tại có thể gây 404; nhưng nếu kết nối lỗi hoặc connector thiếu quyền đọc thì **không được suy ra Group đã bị xóa**.

### Tìm Group theo filter

SCIM có cơ chế filter; ví dụ truy vấn theo externalId:

~~~http
GET /scim/v2/Groups?filter=externalId%20eq%20%22IAM%3AENGINEERING_READER%22 HTTP/1.1
Host: app.example.org
Accept: application/scim+json
Authorization: Bearer [REDACTED]
~~~

Ví dụ response dạng ListResponse:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:ListResponse"
  ],
  "totalResults": 1,
  "startIndex": 1,
  "itemsPerPage": 1,
  "Resources": [
    {
      "schemas": [
        "urn:ietf:params:scim:schemas:core:2.0:Group"
      ],
      "id": "group-git-301",
      "externalId": "IAM:ENGINEERING_READER",
      "displayName": "Engineering-Reader"
    }
  ]
}
~~~

Tùy filter và khả năng API, một đích có thể trả **0, 1 hoặc nhiều Group**. Nếu tìm thấy nhiều Group có cùng externalId, connector phải coi đó là **mâu thuẫn định danh nhóm**, không chọn phần tử đầu tiên để cập nhật ngẫu nhiên.

### Phân trang và dữ liệu không đầy đủ

Khi đọc danh mục /Groups, phải kiểm tra số lượng kết quả, **startIndex**, **count**, **totalResults**, **itemsPerPage** và giới hạn của nhà cung cấp. Không lấy riêng trang đầu rồi kết luận:

- “Không có nhóm mồ côi”.
- “Tất cả User đã được gỡ khỏi Group”.
- “Toàn bộ Group hiện có khớp với desired state”.

Nếu API lỗi, thiếu trang, thiếu quyền hoặc filter không được hỗ trợ, trạng thái quan sát phải là **INCOMPLETE/UNKNOWN** thay vì tự gán tập Group rỗng.

## 6. Thêm, xóa và sửa thành viên bằng SCIM PATCH

**Group.members** là thuộc tính có nhiều giá trị. Để thay đổi một hoặc một vài thành viên, SCIM PATCH thường phù hợp hơn ghi đè toàn bộ Group vì giảm nguy cơ làm mất các membership khác do bản snapshot cũ.

SCIM PATCH dùng schema thông điệp:

~~~text
urn:ietf:params:scim:api:messages:2.0:PatchOp
~~~

Các Operation thường có **op**, **path** (khi cần) và **value** (khi thao tác yêu cầu).

### Thêm một User đã tồn tại vào Group

Giả sử đã xác minh Lan là User **user-git-102** tại cùng SCIM Service Provider/tenant:

~~~http
PATCH /scim/v2/Groups/group-git-301 HTTP/1.1
Host: app.example.org
Content-Type: application/scim+json
Accept: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "user-git-102",
          "type": "User"
        }
      ]
    }
  ]
}
~~~

Trước thao tác này, phải xác nhận **local User ID** đúng người và đúng tenant. Không dùng email hoặc tên hiển thị làm căn cứ duy nhất. Với quyền nhạy cảm, phải kiểm tra role/approval/SoD trước khi thêm membership.

### Gỡ một User khỏi Group

Thay vì xóa toàn bộ members, có thể chỉ định member theo bộ lọc valuePath khi đích hỗ trợ thao tác:

~~~http
PATCH /scim/v2/Groups/group-git-301 HTTP/1.1
Host: app.example.org
Content-Type: application/scim+json
Accept: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"user-git-102\"]"
    }
  ]
}
~~~

Lệnh trên thể hiện cách chỉ gỡ một member được định danh chính xác. Cần kiểm tra SCIM implementation có hỗ trợ filter path và hành vi khi member đã không tồn tại hay không. Một trường hợp member đã bị gỡ trước đó có thể cần được coi là **desired state đã đạt**, nhưng connector phải xác nhận bằng readback thay vì liên tục retry mù.

### Cập nhật thuộc tính Group

Ví dụ đổi displayName mà không làm mất members:

~~~http
PATCH /scim/v2/Groups/group-git-301 HTTP/1.1
Host: app.example.org
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "displayName",
      "value": "Engineering-ReadOnly"
    }
  ]
}
~~~

**Đổi tên Group không tự bảo đảm đổi role nghiệp vụ hoặc quyền của thành viên.** Nếu ứng dụng ánh xạ quyền theo tên Group, thay đổi này có thể ảnh hưởng authorization; phải kiểm tra thiết kế và kiểm thử trước khi thực hiện trên nhóm đang sử dụng.

### PUT thay thế toàn bộ Group

SCIM còn hỗ trợ **PUT** cho thay thế tài nguyên theo ngữ nghĩa cập nhật của giao thức. Đối với Group có members, PUT từ một snapshot không đầy đủ có thể làm mất thành viên không nằm trong payload.

Nên ưu tiên PATCH phạm vi hẹp khi chỉ cần thêm/gỡ một member; nếu bắt buộc dùng PUT, phải:

1. GET bản Group đầy đủ và phiên bản phù hợp.
2. Tính desired state với **toàn bộ membership do connector thực sự sở hữu**.
3. Kiểm tra sourceVersion, approval và Group ownership hiện hành.
4. Dùng kiểm soát phiên bản như **If-Match/ETag** nếu đích hỗ trợ.
5. PUT payload hợp lệ rồi readback; nếu conflict, đọc lại, tính lại và quyết định xử lý.

### DELETE Group cần khác gỡ một thành viên

**DELETE /Groups/{id}** là hành động liên quan **cả Group resource**, không phải thao tác thu hồi quyền của một User duy nhất. Nó có thể làm mất quyền hàng loạt, thay đổi role mapping hoặc ảnh hưởng audit/license.

Khi một người Leaver, thông thường phải **gỡ người đó khỏi những nhóm phù hợp** và vô hiệu hóa tài khoản của họ, không xóa mọi Group mà họ từng tham gia. Chỉ xóa Group sau khi có quyết định ownership, kiểm tra phụ thuộc và chính sách lưu giữ.

## 7. So sánh Group membership và quyền hiệu lực

Tập members đọc từ SCIM phản ánh **quan hệ thành viên mà Service Provider cung cấp qua API**. Nó chưa chắc là tập quyền thực sự người dùng có tại ứng dụng.

Ví dụ:

| Đối tượng | Desired state | Observed state | Kết luận |
| --- | --- | --- | --- |
| Lan trong Group Finance-Reader | Có | Có | Membership khớp; vẫn cần kiểm tra quyền nếu nhóm điều khiển access. |
| Lan trong Group SupportAdmin sau Mover | Không | Có | Membership dư, có thể gây đặc quyền tồn dư. |
| Minh trong Group Git-Reader sau Joiner | Có | Không | Membership thiếu, có thể làm onboarding chưa hoàn thành. |
| Người Leaver trong Group CRM-User | Không | Có | Cần gỡ và kiểm tra phiên/account/token. |
| Admin role được gán trực tiếp | Không | Có dù SCIM Group khớp | Entitlement drift ngoài SCIM; phải kiểm tra API quyền của app. |
| Group có nhiều members nhưng API trả thiếu trang | Không đủ bằng chứng | UNKNOWN | Không được kết luận membership đã chính xác. |

### Desired và observed cần cùng một hệ quy chiếu

Một thuật toán diff an toàn thường:

1. Tải **desired membership** từ nguồn được ủy quyền và chính sách hiện hành.
2. Resolve từng IAM identityId sang **SCIM User ID** hợp lệ ở tenant đích.
3. Tìm chính xác **SCIM Group ID** cần đối soát.
4. Thu thập **observed membership** đầy đủ, có timestamp, pagination và trạng thái API.
5. Chuẩn hóa thành tập các local User ID; không so displayName hoặc thứ tự phần tử.
6. Tính **missing members** và **unexpected members** trong phạm vi connector quản lý.
7. Áp quyết định cấp/gỡ theo ownership, approval và mức rủi ro.
8. Readback sau thao tác và đánh giá **effective permissions** ở nơi cần.

Ví dụ thuật toán tập hợp:

~~~text
desiredMembers  = { user-git-102, user-git-245 }
observedMembers = { user-git-102, user-git-999 }

toAdd    = desiredMembers - observedMembers
         = { user-git-245 }

toRemove = observedMembers - desiredMembers
         = { user-git-999 }
~~~

**Cảnh báo:** Chỉ tự động gỡ toRemove nếu chính sách khẳng định connector **sở hữu toàn bộ membership** của Group đó. Nếu Group có thành viên được quản trị hợp lệ bởi ứng dụng hoặc một nguồn khác, không coi mọi observed member ngoài nguồn IAM là sai.

### Tránh nhầm tập rỗng và dữ liệu không biết

Phải phân biệt:

- **Desired empty:** chính sách quyết định Group không được có thành viên trong phạm vi đã xác định.
- **Observed empty (verified):** API đọc đầy đủ và xác nhận Group không có members.
- **Observed missing:** không trả trường members vì projection, quyền hoặc API không hỗ trợ.
- **Observed unknown:** lỗi kết nối, thiếu trang, stale cache hoặc chưa resolve đúng Group.

Tự biến **unknown** thành **empty** có thể dẫn tới hành vi cấp lại/xóa hàng loạt không an toàn.

## 8. Group provisioning trong Joiner–Mover–Leaver

Nguồn HR, hợp đồng và quy trình identity proofing thiết lập quan hệ công việc và độ tin cậy của identity. **SCIM Group** là một trong những phương tiện để thực thi tập quyền/quan hệ thành viên đã được tính từ chính sách.

### Joiner: thêm đúng User vào nhóm nền

Quy trình tham khảo:

1. HR phát Joiner với source personId và ngày hiệu lực.
2. IAM kiểm tra identity đã xác minh, đối sánh chống trùng và tạo identityId bền vững.
3. Chính sách tính nhóm nền theo role, department, location, tenant và thời hạn; phân biệt nhóm cần phê duyệt riêng.
4. IdP/SCIM client tạo hoặc tìm User đích, lưu **local SCIM User ID**.
5. Connector tìm chính xác Group đích, sử dụng mapping có namespace và Group ownership.
6. Thêm User vào Group theo hiệu lực chính sách; nếu chuẩn bị trước thì không được mở quyền nghiệp vụ trước ngày kích hoạt.
7. GET Group/ứng dụng sau cập nhật để xác minh membership và quyền bắt buộc.

**Pre-provisioning** giúp chuẩn bị trước, nhưng Group có thể thực sự cấp quyền ngay tại ứng dụng. Nếu nhóm được thêm trước ngày đi làm, cần có cơ chế chặn quyền đáng tin cậy hoặc hoãn membership có hiệu lực, thay vì chỉ gắn nhãn PENDING_ACTIVATION trong IAM.

### Mover: gỡ nhóm cũ, cấp nhóm mới

Lan chuyển từ Support sang Finance. IAM không nên chỉ làm thao tác **thêm Finance-Reader**; phải tính lại **toàn bộ membership mong muốn** và phát hiện **SupportAdmin** đã trở thành quyền dư.

~~~mermaid
flowchart LR
    M["HR Mover<br/>Support → Finance"] --> P["Re-evaluate IAM policy<br/>role/attribute/approval"]
    P --> D["Desired groups<br/>Finance-Reader"]
    D --> C["SCIM Group reconciliation"]
    C --> A["ADD Finance-Reader<br/>nếu được duyệt"]
    C --> R["REMOVE SupportAdmin<br/>không còn hợp lệ"]
    A --> V["Readback membership"]
    R --> V
    V --> E["Kiểm tra quyền hiệu lực<br/>app role / ABAC / session"]
~~~

Nếu Group gắn đặc quyền cao, phải xét **Segregation of Duties (SoD)**, người phê duyệt và kiểm soát thay đổi vai trò. Việc cấp nhóm mới có thể được hoãn nếu approval chưa đủ, nhưng quyền cũ không còn hợp lệ vẫn cần thu hồi theo chính sách.

### Leaver: gỡ Group membership không thay thế khóa account

Khi một Leaver có hiệu lực, IAM cần:

- Vô hiệu hóa tài khoản và chặn đăng nhập mới theo khả năng IdP/ứng dụng.
- Gỡ membership của người đó khỏi các Group do IAM quản trị.
- Thu hồi app role/quyền cục bộ, đặc quyền, PAT, API key và credential độc lập khi cần.
- Xử lý session/token đã được cấp; việc gỡ Group không nhất thiết làm JWT hay cookie ứng dụng cũ hết hiệu lực.
- Đối soát Group ở từng Service Provider và xác minh quyền hiệu lực.
- Ngăn job Joiner/Mover cũ retry và **thêm lại User vào Group** sau Leaver.

Nếu Group được dùng làm nguồn duy nhất của role ở app, việc gỡ member có thể thu hồi quyền nghiệp vụ; nhưng vẫn phải kiểm chứng **độ trễ, session/cache và các đường truy cập ngoài Group**.

### Rehire, nhà thầu và nhóm hết hạn

- **Rehire:** không tự khôi phục toàn bộ membership trước đây; phải xác minh đúng người và tính quyền theo công việc mới.
- **Contractor:** mỗi Group/entitlement cần có owner, phạm vi hợp đồng và endAt hợp lệ; membership không được tiếp tục vô hạn chỉ vì connector không nhận được sự kiện Leaver.
- **Temporary/JIT role:** Group đặc quyền hoặc dự án tạm phải có cơ chế hết hạn và đối soát sau thời hạn.
- **Account mồ côi:** nếu SCIM Group chứa User không còn mapping IAM/owner, cần mở case điều tra hoặc thu hồi theo quy trình, không đoán chủ thể qua email.

## 9. SCIM Group, IdP SSO và RBAC/ABAC

Trong triển khai doanh nghiệp, ba lớp thường đi chung nhưng khác trách nhiệm:

| Lớp | Vai trò | Điều không được suy ra |
| --- | --- | --- |
| **IdP / SSO (OIDC, SAML)** | Xác thực chủ thể và đưa kết quả xác thực tới ứng dụng. | User đã có đúng membership tại mọi SCIM Service Provider. |
| **SCIM User/Group** | Tạo/cập nhật tài khoản và đồng bộ quan hệ nhóm. | Đã bảo đảm mọi quyền cục bộ, session hoặc token được thu hồi. |
| **RBAC/ABAC/PAM** | Quyết định và thực thi quyền theo vai trò, thuộc tính, điều kiện và đặc quyền. | Một Group tồn tại là đủ để cho phép mọi hành động. |

Ví dụ pseudo-policy:

~~~text
ALLOW repository.read KHI
    identity.lifecycleState = ACTIVE
    AND user belongs to effective role "EngineeringReader"
    AND identity.tenantId = repository.tenantId
    AND repository.projectId in identity.approvedProjects
    AND session meets requiredAuthenticationAssurance
ELSE DENY
~~~

Ứng dụng có thể chuyển SCIM Group Engineering-Reader thành effective role EngineeringReader. Tuy nhiên, **mapping Group → role là một quy tắc của ứng dụng**, không phải thuộc tính bắt buộc trong Core Group schema. Quyền project, tenant và assurance vẫn phải được xét riêng.

### Group trong token không tự cập nhật khi membership đổi

Nếu IdP phát access token hoặc ID token có claim groups lúc 08:00, rồi IAM gỡ Group lúc 09:00, token/phiên đang tồn tại có thể vẫn mang danh sách nhóm cũ cho đến khi được làm mới hoặc bị chặn.

Vì vậy:

1. Xác định ứng dụng đọc quyền từ Group membership trực tiếp, token claim hay một policy service.
2. Kiểm tra thời hạn token, cache group, session và cơ chế invalidation.
3. Với Mover/Leaver, áp biện pháp phù hợp như cập nhật chính sách, rút phiên hoặc kiểm tra entitlement đủ mới tại Resource Server.
4. Test quyền thực tế sau thay đổi, không chỉ GET /Groups.

**SCIM PATCH 200/204 không chứng minh các phiên ứng dụng đã mất quyền ngay.** Đây là điểm cần kiểm soát đặc biệt với nhóm quản trị và quyền xem dữ liệu nhạy cảm.

## 10. Lỗi API, idempotency và concurrency

SCIM Group provisioning là hệ thống phân tán; connector, IdP, mạng và ứng dụng đích có thể gặp retry, timeout, rate limit hoặc cạnh tranh thay đổi.

### Một số trạng thái HTTP cần xử lý

| Phản hồi | Ý nghĩa thường gặp | Cách xử lý phù hợp |
| --- | --- | --- |
| **200 OK / 201 Created** | Đọc/cập nhật thành công hoặc tạo mới theo operation. | Kiểm tra payload, local ID và readback khi cần. |
| **204 No Content** | Thao tác thành công nhưng không có body. | GET lại Group để xác minh members/state. |
| **400 Bad Request** | Payload/path/schema không hợp lệ. | Sửa mapping, không retry mù cùng request. |
| **401 Unauthorized** | Credential của connector thiếu hoặc không hợp lệ. | Kiểm tra token/issuer và cơ chế xác thực connector. |
| **403 Forbidden** | Connector không đủ quyền. | Kiểm tra phạm vi API, quyền tối thiểu và ownership. |
| **404 Not Found** | Resource ID/path không tồn tại theo ngữ cảnh đích. | Kiểm tra mapping và tenant; không tự tạo Group nếu chưa xác minh. |
| **409 Conflict** | Xung đột như uniqueness theo khả năng nhà cung cấp. | Tìm chính xác tài nguyên đã tồn tại rồi quyết định link/review. |
| **412 Precondition Failed** | Điều kiện phiên bản/If-Match không còn khớp khi được hỗ trợ. | Readback, tính lại desired và tránh ghi đè thay đổi đồng thời. |
| **429 Too Many Requests** | Chạm giới hạn API. | Backoff có giới hạn, tôn trọng hướng dẫn retry của nhà cung cấp. |
| **5xx / timeout** | Đích lỗi hoặc chưa rõ request đã áp dụng hay chưa. | Không kết luận thất bại chắc chắn; đọc lại trước retry. |

Các mã/chi tiết lỗi thực tế tùy operation, tiêu chuẩn và implementation; cần phân tích error response thay vì ép tất cả lỗi vào một phương án duy nhất.

### Race condition thường gặp

**Tình huống:** hai worker cùng cập nhật Group:

1. Worker A đọc Group có Lan và Minh.
2. Worker B thêm Chi và đã lưu.
3. Worker A dùng PUT từ snapshot cũ sau khi gỡ Lan, vô tình làm mất Chi.

Giải pháp:

- Ưu tiên **PATCH thay đổi member cụ thể** khi hỗ trợ.
- Sử dụng **If-Match/ETag** với operation ghi nếu Service Provider hỗ trợ, tránh ghi đè bản mới.
- Đọc lại resource và **recompute desired state** khi gặp version conflict.
- Có **per-group serialization/queue** hoặc cơ chế đồng bộ nhất quán nếu nhiều worker.
- Không coi response thành công là bằng chứng membership cuối cùng vẫn đúng sau các cập nhật cạnh tranh.

### Idempotency và retry

Với thao tác **thêm User vào Group**, connector nên kiểm tra member hiện tại, xác định có cần thêm không, gửi cập nhật và readback. Nếu timeout sau khi gửi, lần retry phải kiểm tra thực tế User đã thuộc nhóm chưa, không phát request lặp không giới hạn.

Với **xóa member**, xác nhận member đã biến mất khỏi Group là trạng thái mong muốn; nếu member đã không tồn tại, có thể kết thúc an toàn tùy semantics của API. Tuy nhiên, không được xem một lỗi đọc Group là bằng chứng đã xóa thành công.

### Sự kiện JML đến sai thứ tự

~~~text
sourceVersion=51: JOINER -> ADD Engineering-Reader
sourceVersion=52: MOVER  -> REMOVE Engineering-Reader
sourceVersion=53: LEAVER -> DISABLE + REMOVE all managed groups

Actual delivery order:
  v53 processed first
  old v51 retried later

Required:
  v51 must NOT re-add membership after v53
~~~

Mỗi tác vụ provisioning cần mang identityId, sourceVersion, effectiveAt và correlation ID. Trước mọi thao tác **cấp** quyền, phải kiểm tra lifecycle/policy hiện hành và có cơ chế ngăn job cũ ghi đè quyết định Leaver.

## 11. Quy trình đối soát SCIM Group end-to-end

~~~mermaid
flowchart TD
    E["Sự kiện JML / quét định kỳ"] --> A["Tính desired groups/members<br/>policy + approval + owner"]
    A --> B["Resolve IAM identity ↔ SCIM User<br/>và IAM group ↔ SCIM Group"]
    B --> C{"Mapping đáng tin?"}
    C -->|Không| X["IDENTITY/GROUP_CONFLICT<br/>review thủ công"]
    C -->|Có| D["GET /Groups, filter và pagination<br/>thu observed membership"]
    D --> F{"Đủ dữ liệu?"}
    F -->|Không| U["OBSERVATION_INCOMPLETE<br/>retry, cảnh báo"]
    F -->|Có| G["Normalize và diff<br/>member IDs, scope, ownership"]
    G --> H{"Có drift?"}
    H -->|Không| V["VERIFIED<br/>lưu evidence"]
    H -->|Có| J["Đánh giá cấp/gỡ<br/>rủi ro, SoD, approvals"]
    J --> K{"Được phép tự sửa?"}
    K -->|Không| M["MANUAL_REVIEW / EXCEPTION"]
    K -->|Có| P["PATCH/PUT có kiểm soát<br/>idempotency + version guard"]
    P --> R["Readback Group và quyền<br/>tại ứng dụng"]
    R --> Q{"Khớp desired hiện hành?"}
    Q -->|Có| V
    Q -->|Không| Z["PARTIAL_FAILURE<br/>retry, owner, audit"]
~~~

### Các trạng thái vận hành hữu ích

| Trạng thái | Ý nghĩa |
| --- | --- |
| **MAPPED** | Đã liên kết Group nguồn với Group đích có căn cứ. |
| **PENDING_PROVISIONING** | Chưa tạo hoặc cập nhật thành công ở đích. |
| **PENDING_VERIFICATION** | Lệnh đã gửi nhưng dữ liệu đích chưa xác minh. |
| **MATCH/VERIFIED** | Membership thuộc phạm vi đã khớp với nguồn và được đọc lại. |
| **DRIFT_DETECTED** | Có member thiếu hoặc dư so với desired. |
| **MAPPING_CONFLICT** | Có mâu thuẫn định danh Group/User, chưa thể ghi an toàn. |
| **OBSERVATION_INCOMPLETE** | API hoặc snapshot chưa đủ để kết luận. |
| **PARTIAL_FAILURE** | Một hoặc nhiều thao tác/đích chưa đạt. |
| **EXCEPTION_TRACKED** | Ngoại lệ được phê duyệt, có owner và thời hạn. |

Tên trạng thái là thiết kế minh họa, không phải enum bắt buộc trong chuẩn SCIM.

### Pseudocode reconcile

~~~text
reconcileGroup(sourceGroupKey, targetSystem, tenant):
    rule = loadApprovedGroupMapping(sourceGroupKey, targetSystem, tenant)
    currentPolicy = loadLatestAuthoritativeJMLAndApprovals()
    desiredIdentities = calculateDesiredMembers(rule, currentPolicy)

    targetGroup = resolveUniqueGroupByTrustedMapping(rule)
    if targetGroup is ambiguous:
        openGroupMappingCase(rule)
        return MAPPING_CONFLICT

    desiredTargetUserIds = []
    for identity in desiredIdentities:
        targetUser = resolveUniqueScimUser(identity, targetSystem, tenant)
        if targetUser is ambiguous or absent:
            recordUnresolvedMember(identity)
            continue
        desiredTargetUserIds.add(targetUser.id)

    observed = readFullGroupMembership(targetGroup.id)
    if not observed.complete or observed.stale:
        return OBSERVATION_INCOMPLETE

    delta = compareSets(
        desiredTargetUserIds,
        observed.memberUserIds
    )
    for change in delta:
        if not rule.ownsMembership(change):
            routeToResourceOwner(change)
            continue
        if change.isGrant:
            assert currentJMLAllowsGrant(change.identity)
            assert validApprovalAndSoD(change)
        applyChangeIdempotentlyWithVersionGuard(change, targetGroup)

    verified = readBackGroupAndRequiredEffectivePermissions(targetGroup)
    recordAudit(rule, delta, verified)

    if verified.allMandatoryChecksPass:
        return VERIFIED
    return PARTIAL_FAILURE
~~~

**Lưu ý quan trọng:** ví dụ trên có bước **recordUnresolvedMember**; khi chưa resolve được toàn bộ User, không được tự gỡ hoặc ghi đè cả Group dựa trên tập desired bị thiếu. Hệ thống thật cần đánh dấu phạm vi chưa hoàn chỉnh và giới hạn remediation theo chính sách.

## 12. Bảo mật Group provisioning

Group membership thường quyết định quyền truy cập. Một lỗi connector có thể cấp đặc quyền cho hàng trăm User, nên API SCIM phải được bảo vệ như bề mặt quản trị an ninh.

### Nguyên tắc kiểm soát

1. **TLS/HTTPS:** bảo vệ dữ liệu và credential khi truyền.
2. **Connector authentication:** dùng credential/token riêng được quản lý trong secret store; rotate và thu hồi đúng vòng đời.
3. **Least privilege cho API token:** cấp đúng phạm vi đọc/ghi User/Group ở tenant cần thiết, không dùng admin credential toàn hệ thống nếu có thể hạn chế.
4. **Authorization cho Group mutation:** một nguồn đồng bộ hồ sơ không mặc nhiên có quyền sửa Group quản trị sản xuất.
5. **SoD và phê duyệt:** membership vào nhóm nhạy cảm cần kiểm soát độc lập, thời hạn và khả năng audit.
6. **Input validation:** xác minh local User ID, Group ID, namespace, tenant và schema; không lấy đường dẫn $ref chưa tin cậy làm đích gọi mạng tùy ý.
7. **Tenant isolation:** không thể thêm User thuộc tenant A vào Group thuộc tenant B trừ khi mô hình và chính sách minh thị cho phép.
8. **Concurrency và tamper detection:** áp phiên bản/ETag khi có, phát hiện sửa membership ngoài workflow.
9. **Privacy:** giới hạn dữ liệu cá nhân trong Group display và log; không nhúng bằng chứng proofing hoặc credential vào members.
10. **Audit và cảnh báo:** theo dõi thay đổi Group nhạy cảm, phát hiện cấp quyền lớn bất thường hoặc quyền bị tái cấp sau Leaver.

### Không nhầm Group.members với proofing

Việc một User thuộc nhóm HR-Verified hoặc một group có tên Employee không tự chứng minh quy trình **identity proofing** đạt mức cần thiết. Nếu quyền yêu cầu bảo đảm danh tính cao, phải kiểm tra nguồn proofing và kết quả chính sách, không suy ra bằng cách nhìn tên nhóm.

### Cẩn trọng với nhóm quản trị

Ví dụ Group CloudAdmins được ánh xạ tới role đặc quyền. Nếu connector tự thêm User chỉ vì department=IT, đó là một lỗi thiết kế dù PATCH Group hoàn toàn hợp lệ về mặt kỹ thuật.

Quy trình an toàn cần:

- Quyết định cấp quyền đúng role và phạm vi.
- Phê duyệt và đánh giá SoD khi bắt buộc.
- MFA/step-up/PAM/JIT phù hợp ở thời điểm sử dụng.
- Thời hạn membership, cảnh báo và rà soát định kỳ.
- Bằng chứng gỡ quyền sau Mover/Leaver, kể cả session/token còn hiệu lực.

**SCIM không thực thi tất cả chính sách an ninh này**; nó chỉ truyền và cập nhật đối tượng theo API. Kiểm soát cấp quyền phải đặt ở policy/workflow và ứng dụng thực thi.

## 13. Xóa Group, đổi tên và quản trị vòng đời nhóm

Vòng đời Group khác vòng đời một User. Một Group có thể còn được dùng bởi hệ thống ngay cả khi thành viên đầu tiên hoặc người quản trị của nó đã nghỉ việc.

| Sự kiện | Hành động | Lưu ý |
| --- | --- | --- |
| Tạo vai trò/dự án mới | Tạo Group với mapping được duyệt. | Tránh trùng tên và externalId trong tenant. |
| Đổi tên nhóm | PATCH displayName nếu do connector sở hữu. | Kiểm tra role mapping có phụ thuộc tên hay không. |
| Đổi owner | Cập nhật metadata quản trị ngoài hoặc trong schema riêng theo thiết kế. | Owner phải là danh tính/người chịu trách nhiệm hợp lệ. |
| Thêm/gỡ User | PATCH members trong đúng Group. | Thao tác theo entitlement và JML hiện hành. |
| Không còn member | Có thể giữ Group rỗng nếu còn chính sách/dự án. | Group rỗng không bắt buộc phải xóa ngay. |
| Dự án bị hủy | Đánh giá xóa Group và quyền phụ thuộc. | Kiểm tra owner, API, audit, retention, role mapping. |
| Leaver của Group owner | Chuyển ownership, gỡ quyền của người rời đi. | Không mặc nhiên DELETE Group đang dùng. |

Nếu một Group được quản lý thủ công tại ứng dụng đích, không tự đưa nó vào danh sách Group do IAM được phép xóa. Cần có **ownership model** và công cụ phát hiện drift ngoài luồng.

## 14. Tài khoản dịch vụ, nhóm workload và nhóm không có HR user

Nhóm không chỉ dành cho nhân viên. Một tổ chức có thể dùng Group để tập hợp service principals, workloads hoặc tài khoản tích hợp, nhưng **khả năng SCIM Group tham chiếu những loại chủ thể này phụ thuộc schema và ứng dụng đích**.

Những câu hỏi cần trả lời:

1. Workload có được biểu diễn như SCIM User tại đích không, hay thuộc kiểu resource/API khác?
2. Ai là service owner và nguồn có thẩm quyền về dịch vụ?
3. Membership có tạo quyền production nào, ở tenant và môi trường nào?
4. Khi owner nghỉ việc, cần **chuyển owner và xoay vòng credential** chứ không xóa nhầm dịch vụ có thật hay không?
5. Khi workload decommission, Group membership, role, token, trust relationship và secret được thu hồi như thế nào?

Đối với danh tính máy, **không dùng máy móc HR manager** để quyết định membership; thay bằng service registry, workload policy, owner và thời hạn của dịch vụ. Tên Group “ServiceAccounts” không chứng minh các service account đang được quản trị an toàn.

## 15. Kiểm thử SCIM Group provisioning

Nên dùng Service Provider giả lập hoặc tenant thử nghiệm, User/Group tổng hợp và credential connector được giới hạn quyền. Kiểm thử cần kiểm tra **response và trạng thái thực tế sau readback**.

### Ma trận test

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| GROUP-01 | POST Group với schema và displayName hợp lệ. | Tạo đúng một Group; lưu local Group ID. |
| GROUP-02 | POST timeout sau khi server đã tạo Group. | Connector tìm lại, tránh tạo trùng. |
| GROUP-03 | Filter theo externalId trả hai Group. | MAPPING_CONFLICT; không sửa Group tùy ý. |
| GROUP-04 | Thêm User vào members bằng PATCH. | Chỉ đúng User/tenant được thêm; readback khớp. |
| GROUP-05 | Thêm lại User đã có trong Group. | Connector đạt desired state mà không sinh membership trùng ngoài semantics. |
| GROUP-06 | Remove một User theo valuePath. | User bị gỡ; thành viên khác còn nguyên. |
| GROUP-07 | Remove User đã vắng mặt. | Xử lý theo API; readback xác minh desired state. |
| GROUP-08 | PUT Group bằng snapshot cũ. | ETag/If-Match hoặc kiểm soát khác ngăn ghi đè mất thay đổi mới. |
| GROUP-09 | GET Group bị thiếu members do projection. | OBSERVATION_INCOMPLETE, không coi Group rỗng. |
| GROUP-10 | Quét nhiều Group có phân trang. | Lấy đủ tất cả trang trước kết luận drift. |
| GROUP-11 | User của tenant A được yêu cầu vào Group tenant B. | Từ chối hoặc xử lý theo mô hình tenant được phê duyệt; không gán nhầm. |
| GROUP-12 | Joiner được pre-provision trước ngày bắt đầu. | Không mở quyền nghiệp vụ sớm do Group membership. |
| GROUP-13 | Mover từ Support sang Finance. | Gỡ Group cũ, cấp Group mới đúng approval, verify quyền. |
| GROUP-14 | Leaver với User còn trong nhiều Group. | Gỡ các membership trong phạm vi, khóa account và kiểm tra phiên/token. |
| GROUP-15 | Retry Joiner cũ sau Leaver. | Không thêm lại User vào Group đã thu hồi. |
| GROUP-16 | Group nhạy cảm thiếu approval/SoD. | Không cấp membership tự động. |
| GROUP-17 | Connector trả 429 hoặc timeout. | Backoff/retry có hạn và readback; không xóa/ghi đè mù. |
| GROUP-18 | Đích không hỗ trợ nested Group. | Không gửi membership kiểu Group hoặc không giả định kế thừa. |
| GROUP-19 | Nhóm được sửa thủ công ngoài luồng. | Phát hiện drift, xác định source of truth và owner trước khi sửa. |
| GROUP-20 | SCIM update xong nhưng app session còn role cũ. | Phát hiện residual access; áp kiểm soát session/authorization phù hợp. |

### Ví dụ Given–When–Then

~~~gherkin
Feature: SCIM Group membership follows IAM lifecycle

  Scenario: Joiner joins only approved group
    Given an authoritative Joiner event for identity ID-2041
    And an approved EngineeringReader entitlement
    And the target SCIM User mapping is verified
    When the provisioning workflow runs
    Then only the mapped User is added to EngineeringReader
    And the group membership is verified by reading the target
    And no unapproved privileged group is granted

  Scenario: Mover removes an obsolete group
    Given identity ID-2041 previously belonged to SupportAdmin
    And an effective Mover event removes SupportAdmin
    When SCIM reconciliation runs
    Then the User is removed from SupportAdmin
    And unrelated members remain unchanged
    And effective permissions are evaluated after convergence

  Scenario: Leaver rejects stale membership retry
    Given identity ID-2041 has an effective Leaver event at version 53
    And an old Joiner task at version 51 is waiting for retry
    When the old task is retried
    Then it does not re-add the User to any managed group
    And the target account and membership are reconciled
~~~

### Kiểm tra hành vi thay vì chỉ mã HTTP

Một test PATCH Group thành công cần xác minh:

- Group ID và User ID là đúng **local SCIM IDs**.
- Tenant và nguồn sở hữu dữ liệu không bị nhầm.
- Không làm mất thành viên khác trong thao tác cập nhật.
- Không cấp group/role có đặc quyền ngoài approval.
- API báo thành công và sau đó đọc lại thực sự khớp desired.
- Nếu ứng dụng có cache/session, quyền tại tài nguyên được kiểm tra sau hội tụ.
- Lỗi timeout, network và event lặp không tạo account/group trùng.

## 16. Kiểm toán và các chỉ số vận hành

Một thay đổi membership có tác động tới quyền phải được truy vết xuyên **nguồn HR/IGA → connector → SCIM provider → ứng dụng**.

### Bằng chứng nên lưu

| Trường | Mục đích |
| --- | --- |
| identityId, source personId | Liên kết đúng chủ thể. |
| sourceGroupKey, targetGroupId | Liên kết Group nguồn và Group đích. |
| targetUserId, tenant | Xác định chính xác member bị thêm/gỡ. |
| action (ADD/REMOVE/REPLACE) | Phân biệt thao tác thay đổi. |
| JML event, effectiveAt, sourceVersion | Kiểm tra quyền có hiệu lực và không bị job cũ ghi đè. |
| policy version, approval, owner | Chứng minh căn cứ cấp/gỡ quyền. |
| HTTP operation/status, retry count | Điều tra lỗi connector và contention. |
| observedAt, verifiedAt, result | Chứng minh đối soát và thời gian hội tụ. |
| correlationId | Truy vết giữa IAM, IdP, SCIM và app. |

Ví dụ sự kiện nội bộ:

~~~json
{
  "eventType": "SCIM_GROUP_MEMBER_REMOVED",
  "identityId": "ID-LAN-2041",
  "sourceGroupKey": "IAM:SUPPORT_ADMIN",
  "target": {
    "system": "CRM",
    "tenant": "tenant-b",
    "groupId": "crm-group-22",
    "userId": "crm-user-98"
  },
  "lifecycleEvent": "MOVER",
  "sourceVersion": 52,
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "policyVersion": "iam-group-v8",
  "action": "REMOVE_MEMBER",
  "result": "VERIFIED",
  "verifiedAt": "2026-12-01T08:01:12+07:00",
  "correlationId": "mover-2041-v52"
}
~~~

Đây là schema minh họa, **không phải SCIM event chuẩn**. Không lưu bearer token connector, mật khẩu, private key, session cookie hoặc dữ liệu cá nhân không cần thiết. Nhật ký phải có giới hạn truy cập, bảo vệ tính toàn vẹn và thời hạn lưu giữ.

### Chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Provisioning latency** | Từ JML effectiveAt đến khi Group membership được xác minh. |
| **Missing members** | Số User thiếu membership được cấp theo chính sách. |
| **Unexpected members** | Số User còn trong Group dù không có quyền phù hợp. |
| **Privileged group drift** | Sai lệch liên quan nhóm đặc quyền hoặc SoD. |
| **Orphan groups / members** | Nhóm không owner, member không resolve được tới identity hợp lệ. |
| **Duplicate group mappings** | Nhiều Group đích ứng với một Group nguồn ngoài ý muốn. |
| **SCIM PATCH failure rate** | Lỗi schema, connector, quyền API hoặc rate limit. |
| **Retry and version conflicts** | Xung đột concurrent update, sự kiện đến sai thứ tự. |
| **Residual access after Leaver** | Membership/role/session/token còn hiệu lực sau offboarding. |
| **Unverified changes** | Lệnh đã gửi nhưng chưa xác nhận Group và quyền thực tế. |

Ngưỡng giám sát và chu kỳ full reconciliation cần dựa trên rủi ro của từng Group. Nhóm quản trị, truy cập dữ liệu tài chính và production thường cần xử lý drift nhanh hơn nhóm phục vụ hiển thị hoặc cộng tác thông thường.

## 17. Tình huống thực hành

### Tình huống A — Đổi department nhưng chỉ thêm Group

**Bối cảnh:** HR chuyển Lan từ Support sang Finance. Connector thêm Lan vào Finance-Reader nhưng không gỡ SupportAdmin.

**Câu hỏi:** Vì sao “provisioning thành công” vẫn có thể là lỗi bảo mật?

**Gợi ý:** Desired state phải phản ánh toàn bộ membership hợp lệ sau Mover. Thêm Group mới không tự gỡ Group cũ; cần diff và remove đúng User/Group, kiểm tra SoD và quyền tồn dư.

### Tình huống B — Trùng tên Group

**Bối cảnh:** Hai Group trong cùng tenant có displayName là “Developers”. Một nhóm cho quyền đọc, nhóm còn lại cho quyền quản trị. Connector chỉ tìm bằng displayName.

**Câu hỏi:** Rủi ro lớn nhất và cách phòng tránh?

**Gợi ý:** Có thể cấp quyền nhầm nhóm. Cần mapping bằng local Group ID và externalId/source key được xác minh, kết hợp tenant và ownership; khi có mâu thuẫn, dừng sửa tự động để review.

### Tình huống C — PUT làm mất member mới

**Bối cảnh:** Hai admin cùng cập nhật Group. Một người thêm Chi, connector sau đó PUT toàn bộ Group từ snapshot cũ nên Chi biến mất.

**Câu hỏi:** Cần sửa kiến trúc thế nào?

**Gợi ý:** PATCH một member cụ thể, dùng If-Match/ETag khi hỗ trợ, xử lý 412 và đọc lại trước khi tính lại desired. Tránh ghi đè toàn bộ từ snapshot lỗi thời.

### Tình huống D — SCIM báo User đã gỡ nhưng CRM vẫn cho dùng role cũ

**Bối cảnh:** Lan bị gỡ khỏi SupportAdmin tại SCIM nhưng session CRM còn quyền hỗ trợ và một local admin role vẫn tồn tại.

**Câu hỏi:** Có thể đánh dấu Leaver/Mover hoàn tất chỉ từ Group membership không?

**Gợi ý:** Không. SCIM Group không tự thu hồi app session, token hoặc local role. Cần kiểm tra quyền hiệu lực, cache, credential và cơ chế revoke của ứng dụng.

### Tình huống E — Leaver rồi retry Joiner

**Bối cảnh:** HR phát Leaver version 53, IAM đã gỡ User khỏi các Group. Một job Joiner version 51 được retry và thêm người đó vào CRM-Users.

**Câu hỏi:** Kiểm soát nào cần có?

**Gợi ý:** Tại thời điểm cấp quyền, kiểm tra sourceVersion và lifecycle mới nhất; thao tác stale không được cấp lại membership. Reconciliation phát hiện và khắc phục nếu sai lệch đã xảy ra.

### Tình huống F — Group do ứng dụng tự quản lý

**Bối cảnh:** IAM muốn đồng bộ mọi thành viên Group Project-X, nhưng hai thành viên là tài khoản của nhà cung cấp được resource owner duyệt trực tiếp trong app.

**Câu hỏi:** Có nên tự động xóa hai người đó vì không nằm trong HR?

**Gợi ý:** Chỉ thực hiện nếu IAM sở hữu toàn bộ Group và đã xác minh quyền/quan hệ của từng chủ thể. Cần xác định field/membership ownership, hợp đồng đối tác, sponsor, ngày hết hạn và quy trình approval. Không coi khác nguồn là sai mặc định.

## 18. Câu hỏi tự kiểm tra

**1. SCIM Group ID có bắt buộc giống IdP group ID không?**

Không. Mỗi SCIM Service Provider cấp id của resource trong namespace riêng; connector phải duy trì mapping có tenant và nguồn rõ ràng.

**2. Vì sao không nên thêm User vào Group chỉ bằng email?**

Email có thể đổi, trùng hoặc tái sử dụng; cần resolve đúng local SCIM User ID và identity nguồn đáng tin.

**3. Group.members hiển thị đúng có chứng minh mọi role, ACL và session đã đúng không?**

Không. SCIM Group có thể chỉ là một phần dữ liệu quyền; application role trực tiếp, ABAC, token và session cần được xác minh riêng.

**4. Khi chỉ cần gỡ một member, vì sao PATCH thường an toàn hơn PUT toàn bộ?**

PATCH thay đổi phạm vi nhỏ và giảm nguy cơ ghi đè các thành viên khác do snapshot cũ. Vẫn cần kiểm soát concurrency và readback theo khả năng đích.

**5. Nếu API trả 204 No Content sau PATCH, đã đủ bằng chứng membership biến mất chưa?**

Chưa đủ trong quy trình cần xác minh. Nên GET/readback Group và kiểm tra quyền thực tế theo chính sách.

**6. Group không có thành viên có bắt buộc phải DELETE không?**

Không. Group có thể còn role mapping, cấu hình, owner hoặc kế hoạch sử dụng; quyết định xóa thuộc vòng đời Group riêng.

**7. Một Group gồm thành viên kiểu Group có được đảm bảo kế thừa quyền không?**

Không mặc định. Phải kiểm tra nhà cung cấp hỗ trợ nested groups và semantics của effective membership/authorization.

**8. Vì sao phải kiểm tra Leaver sourceVersion trước khi retry thêm member?**

Để ngăn job Joiner/Mover cũ tái cấp quyền cho User đã nghỉ việc hoặc mất điều kiện truy cập.

**9. Nếu GET /Groups trả thiếu trang, observed membership nên được hiểu thế nào?**

Là dữ liệu chưa đầy đủ hoặc chưa xác minh; không được xem những Group/member không được liệt kê là không tồn tại.

**10. Có nên cấp Group CloudAdmins tự động chỉ vì department=IT?**

Không nếu thiếu căn cứ quyền, phê duyệt, SoD, thời hạn và chính sách đặc quyền. SCIM chỉ thực thi thay đổi được phép, không quyết định thay policy.

## Ghi nhớ

- **SCIM Group** là tài nguyên nhóm theo schema **urn:ietf:params:scim:schemas:core:2.0:Group**; dùng displayName, members và các ID để quản lý quan hệ thành viên tại Service Provider.
- **id ở SCIM đích, externalId từ client và mã nhóm/nhân viên tại nguồn không thay thế cho nhau.** Luôn xác minh mapping User/Group, tenant và ownership trước khi ghi.
- **POST/GET/PATCH/PUT/DELETE** thực hiện những thay đổi khác nhau. Với membership, ưu tiên thao tác nhỏ, kiểm tra version khi được hỗ trợ, retry idempotent và **readback**.
- **Joiner** cần đúng User, đúng Group và đúng ngày hiệu lực; **Mover** phải gỡ Group cũ và cấp Group mới theo quyền; **Leaver** phải gỡ membership nhưng đồng thời xử lý account, session, token và credential.
- **Group membership không tự chứng minh effective permissions.** IdP/SSO, SCIM provisioning, RBAC/ABAC và PAM có trách nhiệm khác nhau; quyền cục bộ và cache/token có thể tồn tại sau cập nhật.
- **Nguồn có thẩm quyền, least privilege, SoD, phê duyệt, đối soát drift, chống sự kiện cũ và kiểm toán** giúp Group provisioning an toàn, có thể giải thích và giảm quyền truy cập tồn dư trong suốt vòng đời danh tính.
