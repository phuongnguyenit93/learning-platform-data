# SCIM là gì? Chuẩn hóa provisioning danh tính trong IAM

> **Chương:** SCIM provisioning  
> **Bài:** SCIM là gì  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Ngữ cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản và cấp quyền đến cập nhật vai trò, thu hồi và kiểm toán. SCIM kết nối hệ thống danh tính với ứng dụng đích, đồng thời phối hợp IdP, SSO, RBAC/ABAC và quản lý tài khoản dịch vụ để giảm quyền truy cập tồn dư.

## 1. Bài toán thực tế: tạo tài khoản dễ hơn giữ tài khoản đúng trạng thái

Một doanh nghiệp sử dụng một Identity Provider (IdP), hệ thống nhân sự (HRIS) và nhiều ứng dụng: email, CRM, quản lý dự án, hệ thống tài chính. Khi nhân viên An bắt đầu làm việc, nhóm IT phải tạo tài khoản và nhóm/quyền phù hợp trên từng ứng dụng. Sau ba tháng, An chuyển từ Hà Nội sang Đà Nẵng; quyền ở chi nhánh cũ phải giảm trong khi quyền mới được bổ sung. Khi An nghỉ việc, các ứng dụng cần ngừng cho An truy cập.

Nếu mỗi ứng dụng có một API riêng, bộ phận IAM phải duy trì nhiều connector khác nhau, dễ gặp các lỗi:

- Tài khoản đã bị khóa ở IdP nhưng vẫn `active` trên một SaaS.
- Nhân viên chuyển bộ phận vẫn giữ nhóm/role của bộ phận cũ.
- Email đổi nhưng connector tạo thêm một tài khoản thay vì cập nhật tài khoản cũ.
- Yêu cầu thu hồi được gửi thành công nhưng hệ thống đích vẫn còn quyền cấp trực tiếp.
- Không có bằng chứng ứng dụng đã nhận và thực thi thay đổi.

**SCIM (System for Cross-domain Identity Management)** ra đời để tiêu chuẩn hóa việc **trao đổi và quản lý dữ liệu danh tính giữa các miền/hệ thống**. Thay vì mỗi ứng dụng tự định nghĩa một bộ API User/Group hoàn toàn khác nhau, SCIM cung cấp **mô hình tài nguyên và giao thức HTTP có thể tương tác** cho provisioning.

**Điểm cần nhớ:** SCIM giúp đồng bộ **danh tính, tài khoản, thuộc tính và membership**. Nó không tự thay thế xác thực bằng SSO/OIDC, không tự bảo đảm mọi quyền SaaS được gỡ, và không tự chấm dứt mọi phiên/token đang hoạt động.

## 2. SCIM trong một câu và các chuẩn liên quan

SCIM 2.0 gồm những thành phần quan trọng được chuẩn hóa bởi IETF:

| Tài liệu | Chủ đề | Công dụng |
|---|---|---|
| **RFC 7642** | Definitions, Overview, Concepts, and Requirements | Giải thích kiến trúc, mục tiêu và cách sử dụng SCIM |
| **RFC 7643** | Core Schema | Định nghĩa các tài nguyên và thuộc tính chuẩn như User, Group, thuộc tính mở rộng |
| **RFC 7644** | Protocol | Định nghĩa truy cập tài nguyên qua HTTP: GET, POST, PUT, PATCH, DELETE; filter, search, pagination, lỗi và discovery |

Trong triển khai, một hệ thống có thể là:

- **SCIM client:** bên chủ động gửi yêu cầu provisioning, ví dụ IdP hoặc hệ thống Identity Governance and Administration (IGA).
- **SCIM service provider:** ứng dụng/connector phía đích triển khai các endpoint SCIM và lưu/quản lý đối tượng User/Group của nó.
- **Nguồn có thẩm quyền (source of truth):** HRIS, danh mục workload hoặc hệ thống khác có trách nhiệm quyết định trạng thái nghiệp vụ. Source of truth không nhất thiết trực tiếp gọi SCIM.

Một ví dụ định tuyến:

~~~text
HRIS / nguồn nhân sự
      |
      | Joiner / Mover / Leaver
      v
IAM / IGA / IdP  -- SCIM 2.0 HTTPS --> SaaS CRM
      |                                  | /Users
      |                                  | /Groups
      |                                  | local account / group state
      +-- SCIM / API khác ------------> Ứng dụng quản lý dự án
~~~

Ở đây **SCIM là giao diện quản lý danh tính**, không phải phiên SSO mà An thực hiện khi đăng nhập ứng dụng.

### 2.1. Tên “cross-domain” nghĩa là gì?

Hai hệ thống có thể có cơ sở dữ liệu tài khoản, group ID, tenant và mô hình quyền khác nhau. SCIM cho phép chúng trao đổi dữ liệu danh tính theo định dạng/giao thức chung mà không buộc tất cả dùng cùng một database hoặc cùng một địa chỉ email làm khóa.

“Có chuẩn chung” không có nghĩa hai hệ thống đều hỗ trợ chính xác toàn bộ thuộc tính, extension, thao tác hoặc vòng đời. Phải **kiểm tra capability của từng SCIM provider** và hợp đồng tích hợp.

## 3. SCIM và năm khái niệm IAM dễ nhầm

| Thành phần | Câu hỏi nó chủ yếu trả lời | Không nên suy diễn |
|---|---|---|
| **Identity proofing / HRIS** | Người này là ai và quan hệ công việc có hợp lệ không? | HRIS tự cấp mọi role kỹ thuật |
| **IdP / Authentication** | Ai đang đăng nhập, đã chứng minh danh tính như thế nào? | Đăng nhập đúng nghĩa là có quyền trên mọi tài nguyên |
| **SSO / OIDC / SAML** | Ứng dụng nhận kết quả xác thực/phiên theo giao thức nào? | SSO tự tạo/xóa toàn bộ account tại SaaS |
| **SCIM** | Làm thế nào tạo, đọc, cập nhật, vô hiệu hóa hoặc xóa tài nguyên User/Group tại đích? | SCIM tự thu hồi mọi access token, API key và role local |
| **RBAC / ABAC** | Chủ thể được làm gì, trên tài nguyên nào, trong điều kiện nào? | Có mặt trong group SCIM tự bảo đảm được phép mọi hành động |

**OAuth 2.0** cũng xuất hiện trong bức tranh này: một SCIM API có thể dùng OAuth access token để xác thực và phân quyền cho **SCIM client** gọi endpoint quản trị. Nhưng việc truyền access token tới SCIM API và việc dùng SCIM để đồng bộ User/Group là **hai mục đích khác nhau**.

Một ứng dụng có thể dùng **SSO để đăng nhập**, **SCIM để cấp/thu hồi account** và **RBAC/ABAC để kiểm tra quyền từng request**.

## 4. Mô hình tài nguyên của SCIM

SCIM định nghĩa hai loại tài nguyên cơ bản:

1. **User:** biểu diễn một người dùng/tài khoản trong phạm vi SCIM service provider.
2. **Group:** biểu diễn một tập thành viên, thường được dùng để điều phối quyền, assignment hoặc đơn vị tổ chức.

Ngoài ra có **schema extension**, ví dụ Enterprise User extension hỗ trợ thuộc tính liên quan tổ chức như mã nhân viên, bộ phận, quản lý hoặc đơn vị.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Lưu ý quản trị |
|---|---|---|
| `schemas` | Danh sách URN schema tài nguyên tuân thủ | Phải phù hợp loại User/Group và extension |
| `id` | ID tài nguyên do service provider cấp | Không tự tạo/đổi khi client cập nhật |
| `externalId` | ID tham chiếu do provisioning client quản lý | Hữu ích để đối chiếu nguồn; không mặc định là ID duy nhất toàn cục |
| `userName` | Tên định danh user theo schema, bắt buộc và duy nhất theo phạm vi provider | Không mặc định là email hay định danh bất biến |
| `name` | Tên có cấu trúc, ví dụ `givenName`, `familyName` | Chủ yếu phục vụ hồ sơ và hiển thị |
| `emails` | Mảng địa chỉ email với thuộc tính phụ | Không nên làm khóa nối account duy nhất |
| `active` | Cờ trạng thái hành chính của User | Ngữ nghĩa chặn đăng nhập/session phụ thuộc ứng dụng đích |
| `groups` trên User | Tham chiếu group membership theo schema | Thường là thuộc tính chỉ đọc, nên quản lý membership qua Group |
| `displayName` trên Group | Tên hiển thị nhóm | Có thể đổi, không nên dùng làm khóa duy nhất |
| `members` trên Group | Danh sách thành viên, mỗi phần tử tham chiếu tài nguyên | `value` tham chiếu ID tài nguyên của **provider đích** |
| `meta` | Metadata như loại tài nguyên, địa chỉ resource, phiên bản | Có thể hỗ trợ optimistic concurrency tùy provider |

### 4.1. Phân biệt `id`, `externalId` và `userName`

Giả sử trong hệ thống IAM, An có `employeeId=emp-1042`. SaaS CRM có User ID nội bộ `f9ab-12` và tên đăng nhập `an@corp.example`.

~~~text
Source identity ID (HR/IAM):  emp-1042
SCIM externalId (client):     emp-1042
SCIM id (provider CRM):       f9ab-12
SCIM userName (CRM):          an@corp.example
OIDC subject (IdP):          u-4792
~~~

Các giá trị trên **có thể khác nhau mà không sai**. SCIM `id` là ID do provider cấp; `externalId` do client cung cấp và hữu ích cho correlation; `userName` có thể thay đổi theo chính sách; `sub` thuộc ngữ cảnh của OIDC issuer.

Để chống liên kết nhầm, IAM cần lưu **bảng ánh xạ có kiểm soát** giữa identity nguồn, SCIM resource ID, tenant/provider và account được liên kết. Không suy rằng email giống nhau đồng nghĩa cùng người, nhất là khi email được tái cấp.

## 5. Ví dụ User resource trong SCIM 2.0

Một User resource mẫu:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "f9ab-12",
  "externalId": "emp-1042",
  "userName": "an@corp.example",
  "name": {
    "givenName": "An",
    "familyName": "Nguyen",
    "formatted": "Nguyen An"
  },
  "displayName": "Nguyen An",
  "emails": [
    {
      "value": "an@corp.example",
      "type": "work",
      "primary": true
    }
  ],
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "1042",
    "department": "customer-support",
    "manager": {
      "value": "mgr-301"
    }
  },
  "meta": {
    "resourceType": "User",
    "location": "https://crm.example/scim/v2/Users/f9ab-12"
  }
}
~~~

Đây là **JSON minh họa**. Một số trường, extension hoặc thuộc tính có thể không được provider hỗ trợ; client phải dựa trên discovery, schema và hợp đồng tích hợp. Không giả định có thể ghi `id`, `meta` hoặc mọi thuộc tính do provider quản lý.

### 5.1. Thuộc tính SCIM có đặc tính riêng

Core Schema định nghĩa metadata của thuộc tính như:

- **Type:** string, boolean, number, complex và các kiểu khác.
- **Multi-valued:** một hay nhiều giá trị, ví dụ `emails`, `phoneNumbers`.
- **Mutability:** readOnly, readWrite, immutable hoặc writeOnly theo định nghĩa schema.
- **Required / uniqueness:** giá trị bắt buộc hoặc quy tắc duy nhất.
- **Case exact:** phép so sánh chữ hoa–chữ thường theo định nghĩa thuộc tính.

Không nên biến tất cả thuộc tính thành string tùy ý. Ví dụ `active` là boolean; gửi `"false"` dạng chuỗi có thể không hợp lệ hoặc bị provider xử lý khác dự kiến.

### 5.2. Extension giúp mở rộng nhưng không bảo đảm tính tương thích tuyệt đối

Doanh nghiệp có thể dùng enterprise extension hoặc extension riêng cho cost center, loại hợp đồng, mã tenant. Tuy nhiên:

- Client và provider phải thống nhất URN schema, tên, kiểu, mutability.
- Không đưa dữ liệu nhạy cảm không cần thiết vào mọi SaaS.
- Role/permission đặc thù của ứng dụng không mặc nhiên trở thành SCIM standard attribute.
- Khi extension thay đổi, cần version/migration và kiểm thử mapping.

## 6. Ví dụ Group resource và membership

Group giúp biểu diễn ai thuộc nhóm phục vụ provisioning hoặc role assignment.

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "id": "g-support-hn",
  "externalId": "grp-corp-support-hn",
  "displayName": "crm-support-hanoi",
  "members": [
    {
      "value": "f9ab-12",
      "$ref": "https://crm.example/scim/v2/Users/f9ab-12",
      "type": "User",
      "display": "Nguyen An"
    }
  ],
  "meta": {
    "resourceType": "Group"
  }
}
~~~

Lưu ý:

1. `members[].value` phải là ID của tài nguyên thành viên **trong SCIM provider đích**, không phải cứ dùng employee ID nguồn.
2. Provider có thể hỗ trợ hoặc hạn chế việc tạo/đồng bộ Group; một số ứng dụng chỉ nhận User.
3. Group membership **không mặc định** cấp quyền. Ứng dụng có thể cần bảng group-to-role mapping riêng.
4. SCIM có thể biểu diễn nhóm lồng nhau theo mô hình thành viên Group, nhưng **khả năng và cách diễn giải nested groups của provider/connector không được mặc định là như nhau**.
5. Nếu cần xóa một thành viên, phải xử lý đúng ID và trạng thái group ở hệ thống đích, tránh vô tình xóa cả nhóm.

### 6.1. Group để chọn người được provisioning và Group để cấp role

Hai cơ chế trong một hệ sinh thái IdP có thể khác nhau:

- **Assignment group:** xác định user nào nằm trong phạm vi cần có account tại SaaS.
- **Group push/synchronization:** đẩy đối tượng group và membership sang SaaS.
- **Role mapping:** cấu hình của SaaS hoặc connector chuyển membership thành entitlement.

Một user thuộc assignment group có thể được tạo account nhưng chưa nhận quyền nghiệp vụ. Một group được đồng bộ sang SaaS cũng không tự bảo đảm member được phép xuất dữ liệu.

## 7. Endpoint và khả năng khám phá của SCIM

Một SCIM 2.0 service provider thường cung cấp tài nguyên và endpoint phù hợp như:

| Endpoint | Mục đích |
|---|---|
| `/Users` | Danh sách, tìm kiếm hoặc tạo User |
| `/Users/{id}` | Đọc/cập nhật/thay thế/xóa User cụ thể |
| `/Groups` | Danh sách, tìm kiếm hoặc tạo Group |
| `/Groups/{id}` | Đọc/cập nhật/thay thế/xóa Group cụ thể |
| `/ServiceProviderConfig` | Công bố capability của provider, ví dụ PATCH, bulk, filter, etag |
| `/ResourceTypes` | Liệt kê resource types và các schema/extension liên quan |
| `/Schemas` | Truy vấn các định nghĩa schema thuộc tính được hỗ trợ |
| `/.search` theo tài nguyên nếu hỗ trợ | Tìm kiếm qua POST khi tình huống yêu cầu theo profile |

Đường dẫn cơ sở như `https://crm.example/scim/v2` chỉ là ví dụ. Một số ứng dụng đặt endpoint dưới tenant hoặc đường dẫn khác. Client phải dùng **địa chỉ đã được cấu hình/tin cậy**.

### 7.1. Discovery trước khi đồng bộ

Trước khi triển khai, kiểm tra:

- Provider có hỗ trợ `PATCH` không?
- `filter` và `sort` có được hỗ trợ như cần không?
- Có `etag` và conditional requests không?
- Có `bulk` không và giới hạn số operation?
- Thuộc tính/extension nào hiện có, trường nào readOnly hoặc immutable?
- Group, nested group và thao tác `members` hoạt động thế nào?
- Provider sử dụng HTTP status và lỗi theo hợp đồng nào?
- Cần credential/scope nào để gọi SCIM API?

**Không xây connector bằng cách giả định mọi capability đều bật.** SCIM tiêu chuẩn hóa cách biểu diễn và giao thức; provider có thể công bố những khả năng tùy chọn.

## 8. Các thao tác HTTP cơ bản

| Phương thức | Ý nghĩa thường gặp | Ghi chú |
|---|---|---|
| `POST /Users` | Tạo User mới | Cần xử lý trùng `userName`/mapping để tránh duplicate |
| `GET /Users/{id}` | Đọc User | Kiểm tra ID thực tại đích |
| `GET /Users?filter=...` | Tìm User theo filter | Kiểm tra provider hỗ trợ và cú pháp |
| `PUT /Users/{id}` | Thay thế representation theo ngữ nghĩa PUT của provider/SCIM | Tránh vô tình làm mất thuộc tính nếu không hiểu policy |
| `PATCH /Users/{id}` | Cập nhật một phần, ví dụ đổi `active` | Cần dùng SCIM PatchOp, không tùy tiện dùng JSON Patch |
| `DELETE /Users/{id}` | Xóa User theo hành vi hỗ trợ | Có thể ảnh hưởng dữ liệu, không mặc định là cách Leaver tối ưu |
| `PATCH /Groups/{id}` | Thêm/gỡ membership | Phải kiểm tra ID thành viên và role mapping thực tế |
| `POST /Groups` | Tạo Group | Không phải ứng dụng nào cũng cho tạo nhóm qua SCIM |

### 8.1. Tạo User

Ví dụ request rút gọn:

~~~http
POST /scim/v2/Users HTTP/1.1
Host: crm.example
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "externalId": "emp-1042",
  "userName": "an@corp.example",
  "name": {
    "givenName": "An",
    "familyName": "Nguyen"
  },
  "active": true
}
~~~

Token trong ví dụ là placeholder, **không dùng secret thật trong bài học hoặc log**. Phản hồi thành công có thể có `201 Created` và resource/ID do provider trả về. Client phải lưu `id` đích để cập nhật đúng đối tượng những lần sau.

### 8.2. Đọc User và kiểm tra ID

~~~http
GET /scim/v2/Users/f9ab-12 HTTP/1.1
Host: crm.example
Authorization: Bearer <provisioning-access-token>
Accept: application/scim+json
~~~

Nếu provider trả `404 Not Found`, **chưa thể kết luận** user đã bị thu hồi hoàn toàn: có thể đang hỏi sai tenant/ID, người dùng có account khác, hoặc endpoint chưa phản ánh trạng thái thực.

### 8.3. Lọc tài nguyên

SCIM định nghĩa ngôn ngữ filter như `eq`, `co`, `sw`, `pr` và các toán tử kết hợp theo phạm vi hỗ trợ. Một biểu thức minh họa:

~~~text
userName eq "an@corp.example"
active eq true
department eq "customer-support"
~~~

Client phải mã hóa filter khi đưa vào query URL và kiểm tra provider công bố hỗ trợ thuộc tính/điều kiện. Không dùng một query theo email rồi mặc định account trả về là đúng danh tính nếu chưa có đối chiếu ID nguồn/đích.

### 8.4. Phân trang

Khi kết quả nhiều tài khoản, SCIM hỗ trợ thông tin `startIndex`, `count`, `totalResults` và kiểu trả về ListResponse. Ví dụ:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:ListResponse"
  ],
  "totalResults": 230,
  "startIndex": 1,
  "itemsPerPage": 2,
  "Resources": [
    { "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "id": "u-1", "userName": "user1@corp.example" },
    { "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "id": "u-2", "userName": "user2@corp.example" }
  ]
}
~~~

Trong thực tế, **không giả định một lần GET đã trả toàn bộ inventory**. Phân trang đúng là điều kiện để đối soát Leaver, phát hiện account mồ côi và tránh bỏ sót tài khoản.

## 9. PATCH trong SCIM: cập nhật từng thuộc tính

SCIM PATCH dùng schema `urn:ietf:params:scim:api:messages:2.0:PatchOp` với các operation như `add`, `replace`, `remove`.

### 9.1. Vô hiệu hóa User qua PATCH

~~~http
PATCH /scim/v2/Users/f9ab-12 HTTP/1.1
Host: crm.example
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Nếu provider hỗ trợ `active`, yêu cầu này biểu thị mong muốn chuyển account sang trạng thái không hoạt động theo ngữ nghĩa đích. **Không kết luận nó đã thu hồi mọi access token, session, local password hoặc API key.** Đây là tác vụ provisioning, chưa phải toàn bộ bằng chứng deprovisioning.

### 9.2. Thêm thành viên vào Group

~~~http
PATCH /scim/v2/Groups/g-support-hn HTTP/1.1
Host: crm.example
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        { "value": "f9ab-12", "type": "User" }
      ]
    }
  ]
}
~~~

SCIM PATCH có quy tắc cụ thể về operation path, value path và xóa giá trị; thao tác remove membership phải chọn đúng tài nguyên thành viên. Client cần kiểm thử theo capability provider để không gỡ nhầm cả Group hoặc thành viên khác.

### 9.3. Khi nào dùng PUT thay PATCH?

`PUT` là thao tác thay thế resource representation theo semantics được định nghĩa. Nếu gửi một body thiếu thuộc tính, provider có thể xử lý việc bỏ thuộc tính theo schema/mutability và hợp đồng của nó. Vì vậy với cập nhật nhỏ như `active`, `department` hoặc membership, **PATCH thường thuận tiện hơn** khi hỗ trợ.

Nếu provider không hỗ trợ PATCH, connector phải xử lý PUT cẩn trọng: đọc trạng thái, xây lại representation hợp lệ, tính concurrency và readback sau thao tác. Không dùng một body thiếu nhiều field rồi mặc định provider sẽ giữ nguyên tất cả field cũ.

## 10. Joiner: SCIM giúp tạo tài khoản mới thế nào?

**Joiner** là giai đoạn một người được xác minh và gia nhập tổ chức. SCIM giúp điều phối tạo account bên ứng dụng đích, nhưng quyết định **ai được cấp và cấp khi nào** phải đến từ IAM/HRIS/chủ ứng dụng.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / IdP Provisioning
    participant CRM as SCIM Provider CRM
    participant A as Audit / Reconciliation
    HR->>IAM: Nhân viên mới, identity ID, ngày hiệu lực
    IAM->>IAM: Xác minh identity, chính sách group/role
    IAM->>CRM: POST /Users với externalId và dữ liệu cần thiết
    CRM-->>IAM: Resource ID hoặc lỗi cần xử lý
    IAM->>CRM: PATCH /Groups khi policy yêu cầu
    CRM-->>IAM: Kết quả cập nhật
    IAM->>CRM: GET /Users/{id} và kiểm tra membership
    CRM-->>IAM: Trạng thái thực tế
    IAM->>A: Ghi mapping, thời điểm, approval và readback
~~~

### 10.1. Các bước Joiner cần có

1. Nguồn có thẩm quyền xác thực identity, loại nhân sự, ngày bắt đầu và ID ổn định.
2. IAM quyết định SaaS nào là **ứng dụng cần được cấp**, không tự tạo account ở mọi nơi.
3. Tính nhóm/role theo công việc và phê duyệt quyền nhạy cảm.
4. Tìm tài khoản đích theo bảng correlation/ID tin cậy để tránh tạo trùng.
5. Gửi `POST /Users` hoặc cập nhật resource nếu đã tồn tại theo quy trình đã xác minh.
6. Lưu `id` đích cùng `externalId`/identity ID và tenant/provider.
7. Đồng bộ membership, kiểm tra role mapping theo khả năng của SaaS.
8. Tôn trọng ngày hiệu lực; có thể chuẩn bị account sớm nhưng quyền truy cập phải theo policy.
9. **Readback:** xác minh account/membership thực tế thay vì chỉ tin lệnh đã gửi.
10. Ghi event, kết quả và owner; không lưu token quản trị SCIM nguyên dạng.

### 10.2. JIT provisioning khác SCIM provisioning

Một số ứng dụng dùng **Just-In-Time (JIT) provisioning**: tạo user khi người dùng đăng nhập qua SSO lần đầu. Khác với SCIM chủ động, JIT phụ thuộc vào sự kiện đăng nhập.

Doanh nghiệp có thể dùng cả hai, nhưng phải tránh:

- SCIM và JIT tạo **hai account** cho cùng người.
- JIT tự gán quyền admin từ claims không được phê duyệt.
- Account chỉ được tạo khi đăng nhập, nhưng không có cách **thu hồi đúng hạn khi Leaver** mà người dùng không đăng nhập nữa.

Không mặc định SCIM tự thực hiện JIT hoặc ngược lại.

## 11. Mover: cập nhật thuộc tính và thu hồi quyền cũ

**Mover** có thể là chuyển phòng ban, chi nhánh, dự án, role, manager hoặc thời hạn hợp đồng. Đây là nơi dễ phát sinh quyền truy cập tồn dư nếu hệ thống chỉ thêm quyền mới.

Ví dụ An chuyển từ Hà Nội sang Đà Nẵng:

| Trạng thái | Group Hà Nội | Group Đà Nẵng | Quyền dữ liệu đúng |
|---|---|---|---|
| Trước Mover | Có | Không | Chỉ dữ liệu Hà Nội |
| Trạng thái đích | Không | Có | Chỉ dữ liệu Đà Nẵng |
| Thực thi sai | Có | Có | Có thể xem cả hai nơi |

### 11.1. Quy trình Mover

1. Xác nhận sự kiện Mover, ID người dùng, thời điểm hiệu lực và nguồn thuộc tính mới.
2. Tính trạng thái group/role kỳ vọng theo RBAC/ABAC.
3. Đọc trạng thái đang có tại đích, kể cả group lồng nhau nếu sản phẩm dùng.
4. Gỡ membership/quyền cũ không còn hợp lệ; thêm membership cần thiết ở phạm vi mới.
5. Cập nhật User `department`, `manager`, `active` hoặc các thuộc tính có liên quan nếu provider hỗ trợ.
6. Kiểm tra SoD: không giữ hai vai trò xung đột mà thiếu phê duyệt/kiểm soát.
7. Đối soát rằng quyền tại SaaS đã đúng; không chỉ so sánh group nguồn.
8. Đánh giá token/session/role local có còn quyền cũ hay không.

**Quan trọng:** SCIM có thể cập nhật membership thành công, nhưng role được cấp qua local administrator hoặc quyền cấp trực tiếp vẫn còn. Các quyền đó cần được quản trị riêng.

### 11.2. Không bỏ qua độ trễ và cache

Nếu nhân viên đổi department lúc 09:00 nhưng connector chạy hàng giờ, SaaS có thể còn dữ liệu cũ. Chính sách IAM phải quy định **thời điểm tối đa cho thay đổi quyền** tùy rủi ro. Đối với quyền production hoặc dữ liệu nhạy cảm, có thể cần biện pháp hạn chế ngay thay vì chờ batch provisioning.

### 11.3. Chuyển manager không phải đổi identity

Thay `manager`, `department`, `userName` hoặc email không nhất thiết yêu cầu xóa User và tạo User khác. Ưu tiên cập nhật cùng một resource ID, nếu phù hợp policy, để tránh mất audit và phát sinh quyền trong account cũ.

## 12. Leaver: SCIM tham gia thu hồi nhưng không thay toàn bộ deprovisioning

Trong **Leaver**, tổ chức muốn chặn những đường truy cập của người đã kết thúc quan hệ. SCIM thường được dùng để gửi thay đổi `active=false`, gỡ membership hoặc xử lý account theo chính sách ứng dụng.

~~~mermaid
flowchart TD
    A[HRIS báo Leaver và thời điểm hiệu lực] --> B[IAM xác minh identity + target]
    B --> C[IdP chặn xác thực mới]
    B --> D[SCIM disable User và cập nhật Group]
    B --> E[Thu hồi role/credential ngoài phạm vi SCIM]
    C --> F[Đối soát login và phiên/token]
    D --> G[Đọc lại User / Group tại SaaS]
    E --> H[Kiểm tra direct grant, local account, API key]
    F --> I{Tất cả đường truy cập theo policy đã bị chặn?}
    G --> I
    H --> I
    I -- Chưa / không rõ --> J[PARTIAL, containment và escalation]
    I -- Đã xác minh --> K[VERIFIED, lưu audit]
    J --> G
~~~

### 12.1. Disable, delete và remove membership là ba việc khác nhau

| Hành động | Có thể đạt | Không tự bảo đảm |
|---|---|---|
| `active=false` | Cập nhật trạng thái User ở SCIM provider theo hợp đồng | Session/refresh token/API key đều mất hiệu lực |
| Gỡ Group membership | Không còn là thành viên group đích đó | Không còn direct grant hoặc role từ group khác |
| `DELETE /Users/{id}` | Xóa resource theo semantics provider | Dữ liệu/tài khoản liên quan đã được bàn giao đúng |
| Khóa IdP/SSO | Chặn đăng nhập hoặc cấp token mới qua IdP | SaaS không còn session cũ |
| Revoke credential/session tại ứng dụng | Chặn đường truy cập tương ứng | Tất cả hệ thống khác cũng đã thu hồi |

**Không mặc định `DELETE` là lựa chọn tốt nhất cho Leaver.** Có hệ thống cần giữ account ở trạng thái disabled để chuyển giao tài liệu, bảo toàn lịch sử hoặc tuân thủ yêu cầu lưu trữ.

### 12.2. Thu hồi thất bại phải hiển thị rõ

Nếu SCIM endpoint không khả dụng hoặc chưa có bằng chứng trạng thái đích, không ghi `COMPLETED`. Phải giữ `PENDING_VERIFICATION`, `PARTIAL` hoặc `ESCALATED` theo quy trình và kích hoạt kiểm soát bù trừ khi quyền nhạy cảm còn mở.

### 12.3. Tránh sự kiện cũ tái cấp quyền sau Leaver

Một job Mover đến trễ có thể gửi `active=true` và thêm group ngay sau khi Leaver đã disable user. Workflow cần đánh giá trạng thái nhân sự **hiện hành**, phiên bản sự kiện và ngày hiệu lực trước khi áp dụng retry. Đừng tin “sự kiện được nhận sau cùng” là trạng thái đúng nếu hàng đợi có thể gửi sai thứ tự.

## 13. SCIM Group và mô hình RBAC/ABAC

SCIM cung cấp Group/membership, nhưng **không quy định một ngữ nghĩa RBAC thống nhất cho mọi ứng dụng**.

### 13.1. Mapping group sang role

| Group do IAM quản lý | Tác vụ SCIM | Role/quyền tại SaaS (theo cấu hình đích) |
|---|---|---|
| `app-crm-users` | Tạo/giữ User trong phạm vi provisioning | Được đăng nhập nếu các điều kiện khác hợp lệ |
| `crm-support-hn` | Đồng bộ member của Group tương ứng | Xử lý ticket Hà Nội |
| `crm-report-viewer` | Đồng bộ membership | Xem báo cáo theo policy |
| `crm-export-approved` | Đồng bộ group sau approval | Quyền xuất dữ liệu trong thời hạn/phạm vi đã duyệt |

Mapping trên **chỉ là ví dụ nghiệp vụ**. SaaS có thể cần cấu hình riêng hoặc API quản lý role. Không tự động giả định tên group `admins` sẽ cấp admin và cũng không nên tin group do đối tác tự đặt tên là quyền quản trị nội bộ.

### 13.2. ABAC vẫn kiểm tra tài nguyên cụ thể

User có role `crm.support-agent` không tự được đọc mọi hồ sơ khách hàng. API phải kiểm tra chi nhánh, tenant, owner, classification và hành động trên từng resource.

~~~text
function canReadCustomer(user, customer):
    if user.status != ACTIVE:
        return DENY
    if not user.hasRole("crm.support-agent"):
        return DENY
    if user.tenantId != customer.tenantId:
        return DENY
    if user.region != customer.region:
        return DENY
    return ALLOW
~~~

Đây là pseudocode. Các thuộc tính phải đến từ nguồn đáng tin; không tin client tự gửi `region=ALL` hoặc `role=admin`.

### 13.3. Tính effective permission quan trọng hơn group nguồn

Một User có thể nhận quyền từ:

- Group SCIM đã đồng bộ.
- Group lồng nhau, nếu ứng dụng triển khai theo mô hình đó.
- Role cấp trực tiếp bởi admin ứng dụng.
- Quyền chia sẻ tài nguyên hoặc tài liệu.
- Role trong cloud, database hoặc local account khác.
- Token/session được phát hành từ trạng thái cũ.

Do đó **gỡ một member khỏi Group không chứng minh mọi quyền hiệu lực đã biến mất**. IAM cần đọc lại entitlement của hệ thống đích hoặc dùng phép kiểm tra phù hợp mức rủi ro.

## 14. Đồng bộ sự kiện và reconciliation

SCIM cung cấp giao thức để client thao tác tài nguyên. **Nó không buộc tất cả nhà cung cấp phải tự phát một sự kiện thay đổi nhân sự, cũng không định nghĩa một hàng đợi đồng bộ thời gian thực bắt buộc**.

Một hệ thống vận hành có thể kết hợp:

- Event từ HRIS/IGA kích hoạt provisioning.
- Scheduled batch cho những đích không hỗ trợ thông báo sự kiện.
- Retry khi API bị gián đoạn.
- Periodic reconciliation để phát hiện drift, account mồ côi và quyền tồn dư.
- Ticket thủ công cho đích không hỗ trợ đầy đủ SCIM.

### 14.1. Desired state và observed state

Nên tách:

- **Desired state:** trạng thái tài khoản/group **được phép** theo nguồn có thẩm quyền và policy JML.
- **Observed state:** trạng thái tài khoản/group **đang thấy** khi đọc từ SCIM provider.
- **Effective access:** quyền người dùng/workload **thực sự có thể dùng** theo role, session và resource policy.

Một trường `active=false` được đọc từ SCIM provider là bằng chứng của **một trạng thái account**, nhưng có thể chưa đủ để chứng minh **effective access** trên mọi đường truy cập.

### 14.2. Ví dụ thuật toán đối soát

~~~text
function reconcileScimAccount(identity, provider):
    desired = computeDesiredState(identity, currentLifecyclePolicy)

    targetId = resolveMappedProviderId(identity, provider)
    observed = provider.readUser(targetId)

    if observed is NOT_FOUND:
        if desired.accountShouldExist:
            createApprovedAccount(identity, provider)
        else:
            markTargetVerifiedIfNoOtherMappedAccountExists()
        return

    if not matchesDesiredAccountState(observed, desired):
        applySafeScimPatchOrUpdate(observed, desired)

    latest = provider.readUser(targetId)
    verifyUserAndGroupState(latest, desired)

    if hasUnverifiedEffectiveAccess(identity, provider):
        markTarget("PENDING_VERIFICATION")
        escalateIfDeadlineOrRiskRequires()
    else:
        markTarget("VERIFIED")
~~~

Pseudocode này không giải quyết toàn bộ cạnh tranh, eventual consistency hay chính sách thu hồi thực tế. Đặc biệt, xử lý `NOT_FOUND` phải kiểm tra **đúng tenant và đúng ID**, không mặc định “xóa thành công” khi truy vấn sai tài khoản.

## 15. Xử lý lỗi, retry và idempotency

Một connector SCIM an toàn cần phân biệt **lệnh đã gửi**, **phản hồi kỹ thuật** và **trạng thái đích đã xác minh**.

| Tình huống | Nguy cơ | Hành động phù hợp |
|---|---|---|
| Timeout sau POST tạo User | Provider có thể đã tạo account nhưng phản hồi bị mất | Readback theo ID/correlation; không tạo bản trùng mù quáng |
| HTTP 401 | Token quản trị SCIM sai hoặc hết hạn | Kiểm tra credential/rotation, không retry mãi token sai |
| HTTP 403 | Connector thiếu quyền/scope | Điều tra quyền API và owner phê duyệt |
| HTTP 404 | Sai ID, tenant hoặc resource không có | Đối chiếu mapping; tránh kết luận đã deprovision |
| HTTP 409 | Xung đột/trùng thuộc tính duy nhất tùy endpoint | Kiểm tra account hiện hữu, tránh nối nhầm theo email |
| HTTP 412 | Có thể xảy ra khi conditional update không đạt | Đọc version mới, hòa giải trước khi ghi lại |
| HTTP 429 | Bị giới hạn tốc độ theo chính sách dịch vụ | Backoff, quota, `Retry-After` khi được cung cấp |
| HTTP 5xx | Lỗi provider hoặc trạng thái thực thi chưa chắc chắn | Retry có giới hạn và readback |
| HTTP 2xx / 204 | API đã phản hồi theo semantics operation | Readback; không tự suy ra quyền ứng dụng đã biến mất |
| Event đến sai thứ tự | Mover cũ có thể cấp lại sau Leaver | Dựa trên lifecycle version và nguồn có thẩm quyền |

Các mã trạng thái phải được diễn giải theo **HTTP, SCIM error response và hợp đồng thực tế của provider**, không gán một nguyên nhân duy nhất cho mọi tình huống.

### 15.1. Idempotency để chống cấp trùng

Một event Joiner có thể được gửi lại. Nếu `POST /Users` chạy lần nào cũng tạo user mới, tổ chức sẽ có account trùng và không biết account nào cần disable khi Leaver.

Biện pháp:

1. Dùng **event ID** và identity ID ổn định để nhận biết sự kiện lặp.
2. Lưu mapping **source identity → provider resource ID** theo tenant.
3. Trước khi tạo, tìm tài khoản hiện hữu bằng correlation đáng tin.
4. Với update, dùng thao tác hướng đến trạng thái đích thay vì “thêm quyền” không kiểm soát.
5. Khi timeout, đọc lại trước khi quyết định retry.
6. Không tự cấp lại User đã bị Leaver vì một job Joiner cũ chạy sau.

### 15.2. Concurrency và ETag

Nếu provider hỗ trợ `meta.version`/ETag theo hợp đồng, client có thể dùng conditional request như `If-Match` để tránh ghi đè một cập nhật mới bằng dữ liệu cũ.

Đối với lỗi precondition, hãy lấy phiên bản hiện hành và tính lại thao tác, không tắt kiểm soát version chỉ để yêu cầu “thành công” nhanh.

### 15.3. Hàng đợi lỗi và owner

Khi retry vượt ngưỡng hoặc lỗi cố định, đưa tác vụ vào trạng thái có **người chịu trách nhiệm, mức rủi ro, thời hạn và bằng chứng**. Đừng để job failed biến mất khỏi dashboard; với Leaver, điều đó có thể đồng nghĩa account còn active nhiều ngày.

## 16. Bảo mật SCIM API và connector

SCIM API thường có quyền quản lý User/Group hàng loạt. Credential bị lộ có thể cho phép kẻ tấn công tạo tài khoản, kích hoạt user đã nghỉ hoặc thêm người vào group quyền cao.

### 16.1. Kiểm soát cơ bản

- Sử dụng **HTTPS/TLS** với endpoint đã xác minh.
- Bảo vệ API token/OAuth client credential trong secret manager phù hợp.
- Cấp scope/role quản trị SCIM theo **least privilege**; tách connector giữa môi trường/tenant khi phù hợp.
- Xác định nguồn IP/network và cơ chế bảo vệ bổ sung nếu provider hỗ trợ.
- Không ghi access token, secret, password hoặc toàn bộ thông tin nhân sự không cần thiết vào log.
- Xác minh đúng tenant, issuer/provider và resource ID trước khi cập nhật.
- Áp dụng approval/change control với group có quyền đặc biệt.
- Giám sát việc thêm user, bật lại `active` hoặc thay group bất thường.
- Thu hồi/rotation credential khi connector hoặc nhân viên quản trị thay đổi.
- Đối soát tất cả thao tác tạo, cập nhật và vô hiệu hóa có ảnh hưởng nhạy cảm.

### 16.2. SCIM không tự quyết định quyền của connector

RFC SCIM không thay thế hệ thống xác thực/ủy quyền cho chính API SCIM. Provider có thể dùng OAuth 2.0 bearer access token, mTLS hoặc cơ chế được hỗ trợ khác; client phải tuân theo hợp đồng dịch vụ.

**MFA của người vận hành** có thể cần khi họ vào console thay cấu hình provisioning. Nhưng một connector chạy tự động thường dùng **machine authentication**, không nên yêu cầu nhân viên bấm TOTP để mỗi job hoạt động.

### 16.3. Chống mass assignment và thay đổi thuộc tính trái thẩm quyền

Client/proxy không nên cho người dùng thông thường tự chọn `department`, `active`, `manager` hay các thuộc tính được dùng cấp quyền. Provider cũng phải giới hạn những trường được phép ghi theo schema, mutability và permission của client.

Nếu một form cho phép user tự sửa `department=finance` rồi group dynamic cấp quyền quản trị, **SCIM đồng bộ thành công vẫn dẫn đến lỗ hổng quyền**. Vấn đề là **nguồn và thẩm quyền của thuộc tính**, không phải HTTP PATCH có hợp lệ hay không.

## 17. SCIM với tài khoản dịch vụ và định danh phi con người

SCIM được sử dụng nhiều nhất để provisioning tài khoản người dùng và Group. Nó **không phải tiêu chuẩn mặc định quản lý mọi service principal, API key, certificate, workload identity hoặc cloud role**.

Với một bot `invoice-exporter-prod`, tổ chức cần biết:

- Principal/workload ID ổn định, owner kỹ thuật và chủ nghiệp vụ.
- Quyền API/data cần dùng; audience, scope, tenant và môi trường.
- Cơ chế xác thực workload, ví dụ certificate, workload federation hoặc secret được bảo vệ.
- Thời hạn secret/trust và kế hoạch rotation.
- Quyền nào do SCIM/Group quản lý (nếu có), quyền nào do API/cloud IAM khác quản lý.
- Cách xử lý khi workload đổi đội, môi trường hoặc ngừng vận hành.

### 17.1. Joiner–Mover–Leaver của workload

- **Joiner:** tạo service principal, cấp quyền tối thiểu, đăng ký owner, scope và trust.
- **Mover:** thay API, tenant, bộ phận sở hữu, secret hoặc role; thu hồi quyền không còn hợp lệ.
- **Leaver:** thu hồi credentials, role, trust, API grants và secret, kiểm tra tại mỗi target.

Nếu chủ sở hữu bot là một nhân viên nghỉ việc, **không mặc định phải xóa bot đang phục vụ hoạt động hợp lệ**. Trước tiên xác định cần bàn giao workload cho owner khác hay ngừng, sau đó thu hồi quyền cá nhân của người nghỉ và xử lý credential theo policy.

## 18. Audit, quyền riêng tư và chỉ số vận hành

### 18.1. Bản ghi audit tối thiểu

Một event SCIM nên có thể truy vết:

- Identity ID nội bộ và provider/tenant đích.
- SCIM resource ID, `externalId` hoặc correlation phù hợp; không tiết lộ dữ liệu nhạy cảm dư thừa.
- Nguồn JML/event ID, policy version và thời điểm hiệu lực.
- Kiểu thao tác `CREATE`, `UPDATE`, `GROUP_MEMBERSHIP_CHANGE`, `DISABLE`.
- Người hoặc hệ thống có thẩm quyền yêu cầu/phê duyệt.
- Thời điểm gửi, phản hồi, lỗi/retry và correlation ID.
- **Readback:** trạng thái account/group thực tế được quan sát ở đích.
- Các quyền ngoài SCIM cần xử lý và trạng thái ngoại lệ.
- Owner của ticket chưa hoàn tất, hạn xử lý và thời điểm đóng.

Ví dụ audit record:

~~~json
{
  "eventId": "scim-jml-2026-001",
  "sourceIdentityId": "emp-1042",
  "targetProvider": "crm-tenant-a",
  "targetScimResourceId": "f9ab-12",
  "lifecycleEvent": "MOVER_REGION_CHANGE",
  "operation": "GROUP_MEMBERSHIP_RECONCILIATION",
  "desiredGroups": ["g-support-dn"],
  "removedGroups": ["g-support-hn"],
  "executionStatus": "SUCCESS",
  "verificationStatus": "PENDING_TARGET_READBACK",
  "policyVersion": "iam-scim-v3",
  "correlationId": "CHG-01204"
}
~~~

Dữ liệu trên **chỉ minh họa**. `executionStatus=SUCCESS` không tự chứng minh `verificationStatus=VERIFIED`. Không log SCIM bearer token, password, private key, session cookie hoặc raw dữ liệu cá nhân khi không cần thiết.

### 18.2. Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa | Điều phải phân biệt |
|---|---|---|
| Thời gian từ Joiner đến account sẵn sàng | Hỗ trợ ngày đầu làm việc | Tạo account khác cấp quyền đúng |
| Thời gian từ Mover đến quyền mới/cũ đúng | Chất lượng đồng bộ thay đổi vai trò | Chỉ cập nhật thuộc tính không đủ |
| Thời gian từ Leaver đến xác minh thu hồi | Khả năng giảm cửa sổ quyền tồn dư | API response khác effective access |
| Số account mồ côi hoặc trùng | Chất lượng account correlation | Cần xác minh trước khi xóa |
| Tỷ lệ lỗi connector và oldest pending | Phát hiện backlog hoặc outage | Không trộn lỗi tạm với lỗi cố định |
| Tỷ lệ case có readback | Khả năng xác nhận trạng thái đích | Chưa có readback không nên coi VERIFIED |
| Số group/mapping không có owner | Rủi ro quyền không được quản trị | Không xóa ồ ạt khi có phụ thuộc |
| Số quyền tồn dư sau Mover/Leaver | Nguy cơ bảo mật thực tế | Có xét direct grants/local role/token không? |
| Số exception quá hạn | Nợ kiểm soát cần xử lý | Mỗi exception phải có owner/TTL |

## 19. Case study: SCIM triển khai cho CRM theo ba giai đoạn JML

Một doanh nghiệp dùng HRIS → IAM/IdP → CRM SaaS. CRM cung cấp SCIM 2.0 User/Group và xác thực người dùng qua OIDC SSO. Hai hệ thống phục vụ **hai luồng khác nhau**.

### 19.1. Joiner — ngày đầu An vào bộ phận hỗ trợ

1. HRIS tạo ID `emp-1042`, trạng thái active từ ngày hiệu lực, department `support`, region `HN`.
2. IAM xác định An cần CRM, ánh xạ group `crm-support-hn`.
3. SCIM client tạo User, lưu `id=f9ab-12`, `externalId=emp-1042`.
4. SCIM client thêm đúng member của Group CRM theo provider ID.
5. CRM cấu hình role mapping cho quyền xử lý ticket Hà Nội.
6. IdP hỗ trợ An đăng nhập SSO theo MFA policy, nhưng **CRM API vẫn phải kiểm tra quyền trên ticket cụ thể**.
7. IAM readback account và group; audit lưu kết quả.

**Kiểm thử phủ định:** An không được đọc ticket Đà Nẵng chỉ vì có tài khoản và đăng nhập SSO thành công.

### 19.2. Mover — chuyển sang Đà Nẵng

1. HRIS phát sự kiện vùng mới `DN`, có thời điểm hiệu lực.
2. IAM tính trạng thái đích: không còn group HN, có group DN.
3. Connector cập nhật thuộc tính hỗ trợ và membership tại CRM.
4. IAM kiểm tra Group HN đã gỡ An, Group DN đã thêm An.
5. CRM kiểm tra role/tenant dữ liệu, xử lý local grants và session cũ theo policy.
6. Nếu role HN còn tồn tại qua một nguồn khác, workflow giữ **PARTIAL** để xử lý quyền tồn dư.

**Kiểm thử phủ định:** API chặn quyền trên hồ sơ Hà Nội sau thời điểm chuyển quyền theo chính sách.

### 19.3. Leaver — kết thúc hợp đồng

1. HRIS xác nhận An nghỉ việc.
2. IdP chặn đăng nhập SSO mới.
3. SCIM gửi PATCH `active=false` và gỡ membership theo chính sách, hoặc dùng thao tác deprovision được SaaS hỗ trợ.
4. Ứng dụng xử lý session/token và quyền cấp trực tiếp theo cơ chế riêng.
5. IAM readback User/group tại đích và kiểm tra quyền hiệu lực phù hợp.
6. Nếu một target chưa xác nhận, mở ticket với owner thay vì tự đánh dấu hoàn tất.

**Điểm rút ra:** SCIM giúp tự động hóa thay đổi dữ liệu User/Group, nhưng **ngăn truy cập thực sự** cần phối hợp IdP, ứng dụng/API, session và rà soát entitlement.

## 20. Những hiểu lầm phổ biến về SCIM

**“SCIM là giao thức đăng nhập giống OIDC.”** Không. OIDC/SAML hỗ trợ xác thực liên kết; SCIM chủ yếu là provisioning và quản lý tài nguyên danh tính qua HTTP.

**“Bật SCIM thì SaaS tự thu hồi mọi session khi Leaver.”** Không mặc định. `active=false` không đồng nghĩa xóa mọi token/cookie, local login, API key và role trực tiếp.

**“`externalId`, `id` và `sub` luôn giống nhau.”** Không. Chúng thuộc các miền định danh/ownership khác nhau và phải được ánh xạ an toàn.

**“SCIM Group đồng nghĩa với quyền RBAC trong mọi ứng dụng.”** Không. Provider có thể cần mapping role riêng; authorization trên tài nguyên thuộc trách nhiệm hệ thống đích.

**“Chỉ cần lấy email tìm tài khoản đích là an toàn.”** Không. Email có thể đổi hoặc được tái cấp; phải chống link nhầm và account takeover.

**“SCIM bắt buộc mọi provider hỗ trợ PATCH, Bulk và mọi filter.”** Không. Cần xem capability discovery và tài liệu hợp đồng.

**“HTTP 200/204 nghĩa là mọi quyền đã mất.”** Không. Cần đối soát tài nguyên và effective access ở đích.

**“Xóa group khỏi IdP thì SaaS chắc chắn không còn quyền.”** Không nếu role local, direct grant, nested membership hoặc token cũ còn hiệu lực.

**“Leaver chỉ cần DELETE User là xong.”** Không. Xóa có thể ảnh hưởng dữ liệu/hồ sơ cần giữ, còn session/token có thể cần xử lý riêng.

**“Tài khoản dịch vụ nào cũng dùng SCIM.”** Không. Service principal và workload thường có API/trust/credential lifecycle riêng; phải quản trị như chủ thể kỹ thuật.

## 21. Bài tập tự kiểm tra

### Tình huống A: account trùng sau timeout

IAM gửi `POST /Users`, request timeout. Worker dự định gửi lại ngay mà không đối soát.

**Phân tích:** Provider có thể đã tạo User. Cần tìm resource đúng theo mapping/correlation đáng tin và đọc trạng thái trước khi retry, tránh tạo account trùng.

### Tình huống B: Mover chỉ thêm group mới

An chuyển HN → DN. Connector thêm Group DN nhưng giữ Group HN.

**Phân tích:** Quyền cũ còn tồn tại; phải tính desired membership, gỡ HN, kiểm tra role/permission thực tế tại CRM và quản lý cửa sổ chuyển tiếp nếu được phê duyệt.

### Tình huống C: Leaver được đánh dấu completed quá sớm

SCIM trả `204 No Content` sau PATCH `active=false`, nhưng SaaS còn session cookie hợp lệ.

**Phân tích:** Tác vụ SCIM có thể thành công trong phạm vi cập nhật User, nhưng Leaver vẫn cần xử lý session và quyền ứng dụng. Không tuyên bố đã thu hồi toàn bộ.

### Tình huống D: người dùng tự đổi department

Nhân viên tự đổi `department` thành `finance` trong portal, thuộc tính được đồng bộ qua SCIM và hệ thống đích cấp quyền xuất dữ liệu.

**Phân tích:** Sai nguồn có thẩm quyền và mapping quyền. Thuộc tính quyết định quyền phải được kiểm soát/duyệt; SCIM chỉ vận chuyển dữ liệu, không tự đánh giá tính hợp pháp.

### Tình huống E: `externalId` bằng email cũ

Khi user đổi email, connector không tìm thấy account và tạo bản mới, còn bản cũ vẫn active.

**Phân tích:** Không dùng email dễ đổi làm identity key duy nhất; duy trì correlation ID ổn định, phát hiện account cũ và deprovision đúng theo policy.

### Tình huống F: service account do người nghỉ việc sở hữu

Một bot production vẫn cần vận hành nhưng owner là nhân viên đã Leaver. Nhóm IT định xóa toàn bộ bot cho an toàn.

**Phân tích:** Trước hết xác định nghiệp vụ và bàn giao owner, sau đó thu hồi credential cá nhân và xử lý service principal riêng; không làm ngừng workload hợp lệ một cách không kiểm soát.

## 22. Checklist triển khai SCIM provisioning

Khi tích hợp một ứng dụng vào IAM qua SCIM, hãy trả lời:

1. **Nguồn danh tính:** HRIS/IGA/IdP nào có thẩm quyền và ID nguồn nào ổn định?
2. **Phạm vi:** những User/Group nào cần được provisioning; ai duyệt quyền nhạy cảm?
3. **SCIM version/capability:** provider triển khai SCIM 2.0, endpoint và discovery nào?
4. **Schema:** thuộc tính/extension nào bắt buộc, readOnly, mutable hoặc có uniqueness?
5. **Correlation:** có mapping source identity ↔ provider `id`/`externalId` theo tenant không?
6. **Chống trùng:** POST/retry có phát hiện account đã tồn tại và chống link nhầm email?
7. **Authentication connector:** API token/credential có được bảo vệ, giới hạn scope và rotation?
8. **Joiner:** account được tạo đúng ngày hiệu lực, quyền cơ sở và role có owner?
9. **Group:** assignment group, group synchronization và role mapping có được phân biệt?
10. **Mover:** đã vừa thêm quyền mới vừa gỡ quyền cũ, xử lý group lồng nhau và SoD?
11. **Leaver:** `active=false`, disable/delete, group, role, session/token có được xử lý riêng?
12. **SSO/OIDC:** đã tách đăng nhập xác thực khỏi provisioning SCIM đúng vai trò?
13. **RBAC/ABAC:** API đích kiểm tra quyền theo tenant, resource và action chứ không chỉ dựa group?
14. **Provider limits:** PATCH/filter/bulk/etag có được hỗ trợ; quota/pagination xử lý đúng?
15. **Retry:** timeout, 409/412, 429 và lỗi cố định có phân loại/idempotency không?
16. **Sự kiện trễ:** có chặn Mover/Joiner cũ tái kích hoạt quyền sau Leaver?
17. **Reconciliation:** desired/observed/effective access được đối chiếu định kỳ?
18. **Non-human identities:** service accounts, certificates và workload trust có owner/lifecycle riêng?
19. **Audit:** event ID, mapping, policy, approval, lệnh và trạng thái readback có lưu đầy đủ?
20. **Quyền riêng tư:** dữ liệu chia sẻ qua SCIM là tối thiểu và được bảo vệ?
21. **Lỗi chưa hoàn tất:** có PENDING/PARTIAL/ESCALATED, owner, hạn và cảnh báo?
22. **Bằng chứng hoàn thành:** trạng thái thực tế ở SaaS đã được xác minh thay vì chỉ tin response API?

---

**Ghi nhớ:** **SCIM là chuẩn trao đổi và quản lý tài nguyên danh tính qua HTTP**, đặc biệt cho **User, Group và membership** giữa hệ thống cấp phát và ứng dụng đích. Nó giúp tự động hóa **Joiner–Mover–Leaver**, nhưng không phải giao thức SSO, không tự thay RBAC/ABAC và không tự thu hồi mọi token/session hoặc quyền ngoài phạm vi connector. Triển khai SCIM hiệu quả cần **định danh ổn định, mapping có thẩm quyền, connector bảo mật, retry/idempotency, đối soát trạng thái và audit** để giảm tài khoản mồ côi và **quyền truy cập tồn dư**.
