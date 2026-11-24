# User trong IAM: danh tính người dùng, tài khoản và quyền truy cập

> **Chương: Chủ thể và vai trò.** Trong Identity and Access Management (IAM), **User** là đối tượng người dùng mà hệ thống nhận biết và quản lý để phục vụ xác thực, cấp quyền, theo dõi hoạt động và xử lý vòng đời truy cập. Bài này tập trung vào mô hình User trong hệ thống quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**; cách User liên hệ với IdP, SSO, SCIM, RBAC/ABAC và với các tài khoản ở ứng dụng đích.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **User** trong IAM, phân biệt người thật, danh tính, tài khoản, chủ thể truy cập và vai trò.
2. Nhận biết các thuộc tính thiết yếu và trạng thái của một đối tượng User; sử dụng mã định danh ổn định khi liên kết nhiều hệ thống.
3. Mô tả hành trình của User trong **Joiner–Mover–Leaver**, từ xác minh, tạo tài khoản đến thay đổi quyền và chấm dứt truy cập.
4. Phân biệt việc xác thực bằng IdP/SSO với việc cấp phát User bằng SCIM và việc phân quyền tại ứng dụng.
5. Áp dụng RBAC/ABAC và nguyên tắc quyền tối thiểu để hạn chế truy cập tồn dư, đồng thời kiểm toán được thay đổi của User.

## 1. User là gì?

Trong ngữ cảnh quản lý danh tính, **User** thường là biểu diễn của một người sử dụng hệ thống: nhân viên, nhà thầu, đối tác, khách hàng hoặc quản trị viên. Tùy sản phẩm, thuật ngữ User có thể chỉ **bản ghi danh tính** ở IdP, **tài khoản ứng dụng** hoặc một loại **principal** mà cơ chế truy cập nhận biết.

Vì thuật ngữ này thay đổi giữa sản phẩm, khi thiết kế IAM cần hỏi rõ: **User ở hệ thống nào, đại diện cho ai, ai là nguồn dữ liệu có thẩm quyền và User đó có thể thực hiện thao tác gì?**

Ví dụ, nhân viên Mai có thể tồn tại đồng thời dưới những dạng sau:

- Hồ sơ nhân sự trong HR, chứa mã nhân viên, bộ phận, thời điểm bắt đầu và ngày kết thúc hợp đồng.
- Một danh tính User trong **Identity Provider (IdP)**, có thông tin đăng nhập và các thuộc tính dùng để xác thực.
- Một User trong CRM, được liên kết với danh tính ở IdP nhưng có quyền trên khách hàng và ticket riêng.
- Một tài khoản trong công cụ quản lý mã nguồn, có quyền theo dự án và nhóm phát triển.

Đây không nhất thiết là bốn con người hay bốn danh tính nghiệp vụ khác nhau. Chúng có thể là **các bản ghi/tài khoản khác nhau cùng biểu diễn một người**. Nhiệm vụ của IAM là liên kết đúng các biểu diễn ấy, duy trì trạng thái chính xác và ngăn quyền cũ tồn tại ngoài mục đích.

### User khác những khái niệm liên quan thế nào?

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Person / human** | Con người ngoài đời thực; có thể chưa có tài khoản hệ thống. | Mai được tuyển dụng nhưng chưa được cấp tài khoản. |
| **Identity** | Tập định danh và thuộc tính đại diện cho thực thể trong phạm vi tin cậy. | Danh tính nhân viên với mã HR và bộ phận. |
| **User** | Đối tượng người dùng được một hệ thống quản lý hoặc cung cấp truy cập. | User của Mai trong IdP hoặc CRM. |
| **Account** | Bản ghi đăng nhập/sử dụng tại một hệ thống cụ thể. | Tài khoản CRM, email, Git của Mai. |
| **Principal / subject** | Thực thể mà hệ thống bảo mật nhận diện khi kiểm tra truy cập. | Subject lấy từ token đã được xác minh. |
| **Credential** | Bằng chứng giúp xác thực chủ thể. | Passkey, mật khẩu, khóa hoặc chứng chỉ. |
| **Role** | Nhóm quyền gắn với nhiệm vụ hoặc trách nhiệm. | SupportAgent, BillingViewer. |
| **Permission / entitlement** | Khả năng thực hiện một thao tác hoặc quyền được gán. | Đọc ticket, quản lý nhóm, xem hóa đơn. |
| **Session / token** | Trạng thái hoặc bằng chứng xác thực/ủy quyền có thời hạn. | Phiên đăng nhập SSO, access token của API. |

**Một User không đồng nghĩa với một Role.** User là đối tượng có thể được gán vai trò; role là một cách tổ chức quyền. Cũng không nên đồng nhất User với thông tin xác thực: đổi mật khẩu không tạo ra con người mới; xóa tài khoản ở CRM không có nghĩa hồ sơ nhân viên trong HR phải bị xóa.

## 2. Mô hình hóa User và các thuộc tính

Một mô hình User phục vụ IAM thường cần những nhóm thông tin sau:

| Nhóm thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| **Định danh nội bộ** | userId, subjectId | Tham chiếu ổn định tới bản ghi trong một hệ thống. |
| **Liên kết nguồn** | employeeId, externalId, issuer + subject | Liên kết đúng người giữa HR, IdP và ứng dụng; hỗ trợ đối soát. |
| **Tên/nhãn hiển thị** | displayName, preferredName | Hiển thị cho người dùng và người quản trị; có thể thay đổi. |
| **Thông tin liên hệ** | email, phone | Gửi thông báo hoặc phục vụ nghiệp vụ; không mặc nhiên là khóa định danh bất biến. |
| **Thông tin tổ chức** | department, jobTitle, manager, contractType | Tính tập quyền phù hợp với vai trò và chính sách. |
| **Trạng thái vòng đời** | pending, active, suspended, terminated | Xác định có nên tạo, duy trì hoặc thu hồi truy cập. |
| **Thông tin kiểm soát** | owner, approvedRoles, accessEndAt | Chỉ ra ai chịu trách nhiệm, quyền nào được phê duyệt, hiệu lực đến lúc nào. |
| **Bằng chứng vận hành** | createdAt, updatedAt, lastReconciledAt | Hỗ trợ truy vết, kiểm toán và phát hiện đồng bộ lỗi. |

Đây là **mô hình khái niệm**, không phải một schema bắt buộc của mọi IdP. Thực tế, các thuộc tính có thể được tách giữa hệ thống nhân sự, IdP, dịch vụ quản trị quyền và ứng dụng; một số trường có thể không tồn tại hoặc mang tên khác nhau.

### Phân biệt mã định danh ổn định với thuộc tính dễ thay đổi

Nguyên tắc quan trọng: **không liên kết danh tính chỉ bằng tên hoặc email**.

Ví dụ, Mai đổi họ sau khi kết hôn, chuyển phòng ban hoặc doanh nghiệp đổi tên miền email. Nếu hệ thống liên kết User bằng email, thay đổi này có thể tạo tài khoản trùng, mất quyền cần thiết, liên kết nhầm người hoặc giữ lại tài khoản cũ. Nên sử dụng một khóa định danh ổn định do nguồn có thẩm quyền cấp, kết hợp bản đồ ánh xạ tài khoản của các hệ thống.

Khi có nhiều tổ chức (multi-tenant), cùng một chuỗi định danh có thể xuất hiện ở những tenant khác nhau. Hệ thống cần xét **namespace/tenant và bên phát hành (issuer)** cùng với định danh thay vì giả định một username là duy nhất toàn cầu.

### Ví dụ mô hình User ở lớp nghiệp vụ

Ví dụ JSON dưới đây **chỉ minh họa mô hình nội bộ**, không phải payload SCIM hay OIDC chuẩn:

~~~json
{
  "identityId": "id-73a1",
  "source": {
    "system": "HR",
    "personId": "EMP-1025"
  },
  "displayName": "Mai Nguyen",
  "primaryEmail": "mai.nguyen@example.org",
  "employmentStatus": "ACTIVE",
  "department": "CUSTOMER_SUPPORT",
  "access": {
    "desiredRoles": ["SupportAgent"],
    "validUntil": null
  },
  "accounts": [
    {
      "system": "CORPORATE_IDP",
      "localUserId": "usr-0193",
      "state": "ENABLED"
    },
    {
      "system": "CRM",
      "localUserId": "crm-884",
      "state": "ENABLED"
    }
  ]
}
~~~

Trong ví dụ này, **identityId** nhận diện danh tính nội bộ, **source.personId** là khóa từ HR, còn **localUserId** là mã ở từng hệ thống đích. Việc gom tài khoản theo identityId giúp IAM biết phải tác động đến những tài khoản nào khi User đổi vai trò hoặc nghỉ việc.

## 3. User và vai trò trong một yêu cầu truy cập

Một ứng dụng thông thường phải xử lý hai vấn đề độc lập:

1. **Authentication (xác thực):** Chứng minh rằng yêu cầu đến từ User hoặc principal hợp lệ. IdP có thể cung cấp thông tin xác thực qua SSO/OIDC/SAML.
2. **Authorization (phân quyền):** Quyết định User đó có thể thực hiện **hành động nào trên tài nguyên nào trong điều kiện nào**. Cơ chế này thường nằm ở ứng dụng, API gateway và/hoặc dịch vụ chính sách.

Một cách mô hình hóa quyết định:

**Cho phép truy cập = User hợp lệ + hành động được cấp + tài nguyên đúng phạm vi + điều kiện chính sách được đáp ứng.**

### RBAC: quyền theo vai trò

**Role-Based Access Control (RBAC)** gán vai trò cho User, và vai trò chứa những quyền cần cho công việc:

| User / loại nhiệm vụ | Role minh họa | Hành động được cấp | Giới hạn |
| --- | --- | --- | --- |
| Nhân viên chăm sóc khách hàng | SupportAgent | Đọc và cập nhật ticket | Ticket thuộc tenant/nhóm được phân công |
| Trưởng nhóm hỗ trợ | SupportLead | Phân công ticket, xem báo cáo nhóm | Trong phạm vi nhóm được quản lý |
| Nhân viên kế toán | InvoiceReader | Xem hóa đơn | Đơn vị, kỳ và dữ liệu được cấp |
| Người kiểm toán | AccessAuditor | Đọc lịch sử cấp/thu hồi quyền | Không mặc nhiên được sửa chính sách IAM |

Trong thực tế, một User có thể có nhiều vai trò. Điều quan trọng là tập quyền kết hợp vẫn thỏa **least privilege**, **phân tách nhiệm vụ (Separation of Duties)** và các giới hạn dữ liệu.

### ABAC: quyền theo thuộc tính và ngữ cảnh

**Attribute-Based Access Control (ABAC)** xét thêm thuộc tính của User, tài nguyên và môi trường, ví dụ department, tenantId, trạng thái hợp đồng, mức xác thực hoặc phân loại dữ liệu.

Quy tắc minh họa sau không phải ngôn ngữ chính sách của sản phẩm cụ thể:

~~~text
ALLOW "ticket.update" KHI
    user.active = true
    AND user.roles contains "SupportAgent"
    AND user.tenantId = ticket.tenantId
    AND user.teamId = ticket.assignedTeamId
    AND session.assuranceLevel >= requiredAssurance
ELSE DENY
~~~

RBAC trả lời “User được trao loại chức năng nào?”, còn ABAC giúp trả lời “User được sử dụng chức năng đó **trên đối tượng nào, khi nào, trong điều kiện gì**?”. Hai mô hình có thể kết hợp.

> **Cảnh báo triển khai:** Token hợp lệ hoặc quyền theo role chưa đủ để truy cập dữ liệu của một tenant cụ thể. Ứng dụng phải kiểm tra quyền ở phía máy chủ cho từng hành động nhạy cảm, tránh lỗi truy cập ngang đối tượng như xem hoặc sửa dữ liệu của User khác.

## 4. Vòng đời User theo Joiner–Mover–Leaver

IAM quản lý User như một đối tượng **có trạng thái và có sự kiện chuyển trạng thái**, gắn với quan hệ lao động, hợp đồng, quyền truy cập và tình trạng của các tài khoản liên kết.

~~~mermaid
flowchart TD
    S["Nguồn có thẩm quyền<br/>HR / quản lý đối tác"] --> E{"Sự kiện của User"}
    E --> J["Joiner<br/>Xác minh, liên kết danh tính, tạo tài khoản"]
    E --> M["Mover<br/>Tính lại quyền khi đổi vai trò/phạm vi"]
    E --> L["Leaver<br/>Thu hồi khi hết nhu cầu truy cập"]
    J --> D["Tập quyền mong muốn<br/>Role + Attribute + Phê duyệt"]
    M --> D
    L --> O["Không còn quyền theo chính sách"]
    D --> P["IdP / SCIM / connector / ứng dụng"]
    O --> P
    P --> R["Đối soát tài khoản, nhóm, quyền,<br/>phiên và credential thực tế"]
    R --> A["Kiểm toán, cảnh báo sai lệch, xử lý lỗi"]
~~~

### Joiner: khi một người trở thành User của hệ thống

Giả sử Mai đã được tuyển vào bộ phận hỗ trợ khách hàng:

1. **Xác minh và duyệt danh tính:** HR hoặc nguồn được ủy quyền xác nhận hồ sơ, ngày bắt đầu, mã nhân sự và bộ phận.
2. **Đối sánh danh tính:** IAM kiểm tra Mai đã có hồ sơ từ hợp đồng trước hay chưa, tránh tạo hai User cho cùng một người.
3. **Tạo User ở IdP:** Cấp định danh, thiết lập phương thức xác thực và MFA theo chính sách.
4. **Tính quyền ban đầu:** Gán vai trò nền cần thiết và ghi nhận những quyền nhạy cảm phải xin phê duyệt riêng.
5. **Provisioning:** Tạo User trong CRM hoặc ứng dụng khác qua SCIM/API/connector nếu có.
6. **Đối soát:** Xác minh tài khoản và quyền thực tế đã sẵn sàng đúng thời điểm, đúng người, đúng phạm vi.

### Mover: khi User vẫn là người đó nhưng quyền cần thay đổi

Mai chuyển từ hỗ trợ khách hàng sang kế toán. **Danh tính và mã nguồn HR vẫn liên kết với cùng một người**, nhưng tập quyền cần được tính lại:

- Thu hồi SupportAgent và các nhóm/quyền hỗ trợ không còn hợp lệ.
- Giữ quyền chung được phép tiếp tục sử dụng.
- Cấp InvoiceReader sau quy trình phê duyệt cần thiết.
- Cập nhật department, manager, tenant/phạm vi và các thuộc tính ảnh hưởng đến ABAC.
- Kiểm tra credential, token, phiên và quyền cục bộ còn duy trì truy cập cũ.

Đây là nơi dễ xuất hiện **privilege accumulation**: hệ thống chỉ cộng vai trò kế toán mà không xóa vai trò hỗ trợ. Cần so sánh **quyền mong muốn** với **quyền thực tế** để đảm bảo việc chuyển vai trò hoàn tất.

### Leaver: khi User không còn được truy cập

Khi Mai nghỉ việc hoặc hợp đồng hết hiệu lực:

1. Tiếp nhận sự kiện và thời điểm hiệu lực từ nguồn có thẩm quyền.
2. Vô hiệu hóa hoặc thu hồi khả năng xác thực theo quy trình; xử lý phiên/token còn hiệu lực khi hệ thống hỗ trợ.
3. Gỡ các vai trò, nhóm và quyền đã cấp ở IdP và hệ thống đích.
4. Vô hiệu hóa tài khoản, credential cục bộ, API key hoặc kênh truy cập trực tiếp có liên quan.
5. Xác minh tại các ứng dụng thực tế; xử lý lỗi đồng bộ và lưu bằng chứng.
6. Lưu giữ dữ liệu kiểm toán hoặc dữ liệu nghiệp vụ theo chính sách; không xóa dấu vết chỉ vì User đã rời tổ chức.

**Vô hiệu hóa User tại IdP chưa mặc nhiên chấm dứt mọi truy cập.** Một token đã phát hành còn hạn, tài khoản cục bộ hoặc khóa API có thể vẫn được ứng dụng đích chấp nhận. Vòng đời User chỉ được quản lý tốt khi những đường truy cập này được nhận diện và xử lý theo khả năng kỹ thuật, có thời hạn và trạng thái kiểm chứng.

### Trạng thái User không đồng nhất giữa các hệ thống

Một tổ chức có thể dùng các trạng thái như **PENDING, ACTIVE, SUSPENDED, TERMINATED** trong quy trình nội bộ. Tuy nhiên:

- Trạng thái nhân sự **ACTIVE** không chứng minh tài khoản CRM đã được tạo.
- Trạng thái tài khoản IdP **DISABLED** không chứng minh mọi phiên truy cập ở ứng dụng đã hết hiệu lực.
- Trường **active** trong bản ghi SCIM phản ánh trạng thái của tài khoản theo cách ứng dụng đích triển khai; không nên đồng nhất nó với việc xóa hoàn toàn User hoặc thu hồi tất cả phiên/token.
- Việc **xóa** User vật lý khỏi một hệ thống có thể khác với **vô hiệu hóa** hoặc **ngừng cấp quyền**; lựa chọn còn phụ thuộc yêu cầu lưu trữ, khôi phục và kiểm toán.

## 5. User giữa IdP, SSO và SCIM

Để hiểu rõ đường đi của User, hãy tách **đăng nhập**, **cấp phát tài khoản** và **thực thi quyền**.

| Thành phần | Xử lý gì đối với User? | Không nên suy ra |
| --- | --- | --- |
| **Identity Provider (IdP)** | Lưu hoặc liên kết danh tính, xác thực User, cấp bằng chứng đăng nhập. | Mọi quyền nghiệp vụ của User đều nằm tại IdP. |
| **SSO (Single Sign-On)** | Cho phép User truy cập nhiều ứng dụng liên kết sau quy trình xác thực thích hợp. | Mọi ứng dụng tự tạo tài khoản hoặc tự thu hồi quyền khi User đổi trạng thái. |
| **OIDC / SAML** | Trao đổi thông tin xác thực/định danh giữa các bên tin cậy theo giao thức. | Một ID token hoặc assertion tự động cấp quyền đọc mọi dữ liệu. |
| **SCIM** | Chuẩn API quản lý người dùng và nhóm ở ứng dụng đích: tạo, đọc, cập nhật, vô hiệu hóa tùy khả năng hỗ trợ. | Thực hiện SSO hoặc buộc mọi phiên hiện có hết hạn. |
| **RBAC / ABAC** | Đánh giá User có quyền gì với tài nguyên và điều kiện cụ thể. | Chỉ cần User đã đăng nhập là mọi API được phép chạy. |
| **Audit / IGA** | Theo dõi yêu cầu, phê duyệt, cấp, thay đổi và rà soát quyền. | Có bản ghi “đã gửi lệnh” tức là hệ thống đích đã hoàn tất thay đổi. |

### User resource trong SCIM

**SCIM (System for Cross-domain Identity Management)** cung cấp mô hình tài nguyên User và Group cùng cơ chế API cho provisioning. Ví dụ đơn giản sau mô phỏng một số thuộc tính thường thấy của **SCIM User**:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "id": "d5a8f0d1",
  "externalId": "EMP-1025",
  "userName": "mai.nguyen@example.org",
  "displayName": "Mai Nguyen",
  "active": true,
  "emails": [
    {
      "value": "mai.nguyen@example.org",
      "primary": true
    }
  ]
}
~~~

Một số điểm cần phân biệt:

- **id** là định danh của tài nguyên do SCIM service provider quản lý, thường dùng trong các thao tác với tài nguyên đích.
- **externalId** là giá trị do bên provision cung cấp để liên kết với nguồn bên ngoài; phải quản lý ánh xạ nhất quán.
- **userName** dùng để định danh User trong ngữ cảnh service provider, không mặc nhiên là mã nhân viên hoặc mã bất biến trong mọi hệ thống.
- **active** biểu thị trạng thái kích hoạt của User tại service provider; cách ảnh hưởng tới đăng nhập, tài khoản và session cần xác minh với sản phẩm đích.
- **groups**, **roles** hay các thuộc tính khác có thể có cơ chế quản lý khác nhau theo khả năng và schema mở rộng của từng service provider; không nên giả định mọi ứng dụng hỗ trợ cùng một mô hình quyền.

SCIM giúp truyền thay đổi đến ứng dụng, nhưng quy trình IAM vẫn phải kiểm tra việc ánh xạ đúng User, quyền ở đích và kết quả thực tế.

### Ví dụ dòng truy cập của một User

~~~mermaid
sequenceDiagram
    actor User as Mai
    participant HR as HR / nguồn danh tính
    participant IAM as IAM / Provisioning
    participant IdP as IdP
    participant CRM as CRM
    HR->>IAM: Sự kiện Joiner/đổi trạng thái
    IAM->>IdP: Tạo hoặc cập nhật danh tính User
    IAM->>CRM: SCIM/API tạo hoặc cập nhật tài khoản
    CRM-->>IAM: Trạng thái xử lý provisioning
    User->>CRM: Mở ứng dụng
    CRM->>IdP: Chuyển hướng/ủy thác xác thực
    IdP-->>CRM: Thông tin xác thực hợp lệ
    CRM->>CRM: Kiểm tra role, tenant, tài nguyên
    CRM-->>User: Cho phép hoặc từ chối
~~~

*Sơ đồ giản lược: luồng thực tế còn có các bước giao thức, kiểm tra chữ ký và xác thực token, cookie/phiên, consent hoặc phân quyền phụ thuộc kiến trúc. Không dùng sơ đồ này thay cho đặc tả OIDC/SAML/SCIM.*

## 6. Các loại User và ranh giới với danh tính máy

Không phải mọi User có cùng phương thức quản lý:

| Đối tượng | Đặc điểm | Điểm cần quản trị |
| --- | --- | --- |
| **Employee user** | Nhân viên có vòng đời từ HR. | Mã nhân sự, ngày hiệu lực, Mover và Leaver. |
| **Contractor / partner user** | Nhà thầu/đối tác thường có ngày kết thúc, đơn vị bảo trợ. | Owner bảo trợ, ngày hết hạn, kiểm tra gia hạn. |
| **Customer user** | Người sử dụng sản phẩm/dịch vụ của doanh nghiệp. | Đăng ký, xác minh, đồng ý, tự phục hồi và khóa tài khoản. |
| **Privileged administrator user** | User có quyền vận hành hoặc thay đổi cấu hình nhạy cảm. | MFA phù hợp, PAM/JIT, kiểm toán phiên, SoD. |
| **Emergency / break-glass user** | Tài khoản dùng theo quy trình khẩn cấp. | Bảo vệ đặc biệt, giới hạn người được sử dụng, ghi nhận và rà soát sau sự cố. |
| **Service account / workload identity** | Danh tính máy chạy job, API hoặc workload. | Owner kỹ thuật, quyền tối thiểu, credential ngắn hạn, vòng đời theo dịch vụ. |

**Service account có thể được một sản phẩm biểu diễn bằng đối tượng “User”**, nhưng cần phân biệt mục đích sử dụng. Tài khoản dịch vụ không nên phụ thuộc vào nhân viên đăng nhập tương tác, không nên dùng chung mật khẩu dài hạn và không được bỏ qua thu hồi chỉ vì không có HR event trực tiếp. Cần liên kết với owner và vòng đời của ứng dụng/workload.

Đối với tài khoản quản trị, một người có thể có tài khoản thường và tài khoản đặc quyền riêng theo chính sách. Cần liên kết hai tài khoản với cùng một người chịu trách nhiệm, đồng thời giới hạn nơi, thời gian và nhiệm vụ mà tài khoản đặc quyền được dùng.

## 7. Những rủi ro đặc thù khi quản lý User

### 7.1. Liên kết nhầm người hoặc tạo tài khoản trùng

Hai người trùng tên, email được tái sử dụng hoặc thay đổi tên miền có thể khiến việc đối sánh sai. Biện pháp là dùng khóa định danh ổn định, xét nguồn và tenant, kiểm tra xung đột và có quy trình xử lý trước khi nối hai tài khoản.

### 7.2. User đã đổi vai trò nhưng quyền cũ vẫn còn

Nguồn nhân sự đã cập nhật nhưng một ứng dụng chưa xóa vai trò cũ, nhóm được lồng vào nhau hoặc quyền địa phương vẫn còn. Cần tính lại tập quyền mong muốn, kiểm tra cả quyền kế thừa, xử lý sai lệch và lưu bằng chứng thu hồi.

### 7.3. User bị vô hiệu hóa nhưng vẫn có phiên hoặc credential

Phiên, token còn hạn, API key hoặc tài khoản cục bộ không tự biến mất khi IdP đổi trạng thái. Thiết kế phải xét thời hạn token, chấm dứt phiên nếu hỗ trợ, khóa credential và kiểm tra kết quả tại hệ thống đích.

### 7.4. Tài khoản mồ côi và tài khoản không rõ owner

User không còn quan hệ hợp lệ nhưng tài khoản vẫn hoạt động; hoặc có tài khoản đặc quyền không biết thuộc người nào. Cần định kỳ đối soát User với nguồn HR/đối tác và kiểm kê các tài khoản ngoài luồng, kèm owner cho từng ngoại lệ.

### 7.5. Thiếu giới hạn tenant hoặc đối tượng trong API

User có thể sở hữu role hợp lệ ở tenant A nhưng thử truy cập mã định danh đối tượng của tenant B. Nếu API chỉ xét role mà bỏ qua sở hữu/tenant, quyền bị mở rộng ngoài ý định. Mỗi thao tác nhạy cảm phải kiểm tra cả thuộc tính tài nguyên, phạm vi và chính sách.

### 7.6. Tài khoản được tái kích hoạt không đúng cách

Người nghỉ việc rồi được tuyển lại có thể mang định danh nguồn mới hoặc quay lại định danh cũ tùy quy trình tổ chức. Không nên tự nối hai hồ sơ chỉ dựa vào email; cũng không nên khôi phục tất cả quyền trước đây nếu không được phê duyệt. Rehire phải có bước xác minh liên kết danh tính và **cấp lại quyền theo vai trò hiện tại**.

## 8. Kiểm toán và quản trị User

Mỗi sự kiện quan trọng của User nên có bằng chứng đủ trả lời:

- **Ai** là chủ thể và mã định danh liên kết ở từng hệ thống?
- **Ai hoặc hệ thống nào** đã yêu cầu thay đổi, trên cơ sở sự kiện nào?
- **Ai phê duyệt**, quyền nào được cấp/thu hồi, phạm vi và thời hạn là gì?
- **Khi nào** sự kiện có hiệu lực, yêu cầu được gửi và đích thực sự áp dụng?
- **Tại hệ thống nào** thay đổi thành công, thất bại hay đang chờ đối soát?
- **Quyền còn lại** có phù hợp với công việc và chính sách hiện tại không?

Ví dụ bảng nhật ký khái niệm:

| Thời điểm | User | Sự kiện | Thay đổi mong muốn | Kết quả cần xác minh |
| --- | --- | --- | --- | --- |
| 08:00 | EMP-1025 | JOINER | Cấp SupportAgent cho Mai. | IdP + CRM đã tạo đúng User và vai trò. |
| 09:15 | EMP-1025 | MOVER | Gỡ SupportAgent, cấp InvoiceReader. | Quyền CRM cũ đã mất; quyền tài chính mới đúng phạm vi. |
| 17:00 | EMP-1025 | LEAVER | Ngừng quyền truy cập và phiên liên quan. | Tất cả tài khoản/credential/phiên trong phạm vi đã xử lý hoặc được báo lỗi. |

**Kiểm toán phải bảo vệ dữ liệu cá nhân và thông tin bí mật.** Log cần đủ mã tham chiếu để truy vết nhưng không chứa mật khẩu, private key, access token nguyên vẹn hoặc dữ liệu nhạy cảm không cần thiết. Chính sách lưu giữ hồ sơ User có thể khác chính sách duy trì quyền đăng nhập.

Các chỉ số vận hành hữu ích gồm:

1. Thời gian từ sự kiện Joiner đến lúc tài khoản cần thiết được cấp và xác minh.
2. Thời gian từ Mover đến lúc quyền cũ không còn hiệu lực tại các hệ thống liên quan.
3. Thời gian từ Leaver đến lúc tất cả đường truy cập thuộc phạm vi đã thu hồi.
4. Số tài khoản mồ côi, User trùng, quyền không owner và ngoại lệ quá hạn.
5. Tỷ lệ sai lệch giữa **desired state** và **observed state** của từng tài khoản đích.

## 9. Ví dụ tổng hợp: một User, nhiều tài khoản

Giả sử tổ chức có HR, IdP, CRM, công cụ quản lý mã nguồn và ứng dụng tài chính. Nhân viên **Mai** chuyển từ đội hỗ trợ sang đội tài chính.

**Trước khi chuyển:** HR ghi Mai thuộc đội hỗ trợ; IdP có User tương ứng, gắn nhóm SupportAgent; CRM còn tài khoản đang hoạt động; ứng dụng tài chính chưa cấp quyền.

**Tại thời điểm chuyển:** HR phát sự kiện Mover, quy trình IAM cập nhật department, đánh giá phê duyệt vai trò InvoiceReader, gỡ SupportAgent, cập nhật nhóm và tài khoản đích qua connector.

**Rủi ro:** CRM đồng bộ thành công nhưng một phiên cũ vẫn còn hiệu lực, hoặc connector ứng dụng tài chính thất bại. IAM không nên gắn nhãn toàn bộ quy trình thành công chỉ vì cập nhật HR và IdP đã hoàn thành.

**Tiêu chí đạt:** Quyền mong muốn được phê duyệt; quyền cũ không còn sử dụng được ngoài ngoại lệ được phê duyệt; các tài khoản ứng dụng ở trạng thái chính xác; phiên/credential được xử lý theo chính sách và khả năng kỹ thuật; sai lệch có cảnh báo và người phụ trách; nhật ký đủ truy vết.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao không nên coi email là định danh bất biến của User?

*Gợi ý:* Email có thể đổi hoặc được tái sử dụng. Cần liên kết bằng định danh ổn định từ nguồn tin cậy và đối chiếu thêm namespace/issuer/tenant khi thích hợp.

**Câu 2.** Người dùng đăng nhập thành công qua SSO. Điều này có chứng minh họ được xem tất cả dữ liệu trong CRM không?

*Gợi ý:* Không. Xác thực chỉ chứng minh chủ thể theo cơ chế tin cậy. CRM còn phải xét quyền, tenant, tài nguyên, hành động và điều kiện thực thi.

**Câu 3.** Khi nhân viên chuyển bộ phận, vì sao không chỉ thêm role mới vào User?

*Gợi ý:* Làm vậy gây tích lũy đặc quyền. Cần tính lại quyền mong muốn, gỡ quyền cũ không còn hợp lệ, cấp quyền mới theo phê duyệt và đối soát ở đích.

**Câu 4.** Một SCIM User có active=false. Có thể kết luận mọi token và phiên tại ứng dụng đích đã bị hủy ngay không?

*Gợi ý:* Không mặc định. Cần xác minh cách ứng dụng triển khai SCIM, quản lý session/token, tài khoản cục bộ và credential khác.

**Câu 5.** Tài khoản chạy job theo lịch có được gọi là User không?

*Gợi ý:* Một số sản phẩm biểu diễn service account bằng đối tượng User. Tuy nhiên, IAM phải nhận diện đây là danh tính máy, gắn owner, áp quyền tối thiểu và quản lý vòng đời theo dịch vụ thay vì chỉ theo sự kiện nhân sự.

## Ghi nhớ

- **User** là đối tượng người dùng trong một hệ thống; cần phân biệt với con người, danh tính nghiệp vụ, tài khoản từng ứng dụng, principal và vai trò.
- Một người có thể có nhiều User/account ở các hệ thống khác nhau. **Định danh ổn định và ánh xạ chính xác** giúp IAM tránh tạo trùng hoặc thu hồi nhầm.
- **IdP/SSO** giải quyết phần lớn bài toán xác thực liên thông; **SCIM/connector** giúp tạo, cập nhật và vô hiệu hóa tài khoản; **RBAC/ABAC** kiểm soát quyền trên tài nguyên.
- **Joiner** tạo quyền vừa đủ; **Mover** thay đổi và thu hồi quyền cũ; **Leaver** chấm dứt truy cập bằng hành động và kiểm chứng ở các hệ thống đích.
- Quản lý User hiệu quả đòi hỏi **nguồn có thẩm quyền, quyền tối thiểu, đối soát trạng thái thực tế, kiểm toán và quản lý ngoại lệ**, đặc biệt khi User thay đổi vai trò hoặc rời tổ chức.
