# SCIM filter: truy vấn và đối soát tài nguyên danh tính trong IAM lifecycle

**SCIM filter** là cú pháp điều kiện dùng để tìm các tài nguyên **User**, **Group** hoặc tài nguyên SCIM khác dựa trên thuộc tính của chúng. Trong **SCIM 2.0 — System for Cross-domain Identity Management**, bộ lọc giúp client hỏi service provider những câu như: “User nào có `userName` này?”, “Nhóm nào có `displayName` phù hợp?”, “Những tài khoản nào đang `active`?” hoặc “Người dùng nào có email công việc thuộc một miền nhất định?”.

Ví dụ, trước khi provision nhân viên mới vào ứng dụng, IAM có thể dùng filter `userName eq "lan@example.invalid"` để kiểm tra ứng dụng đích đã có một User tương ứng hay chưa. Trong giai đoạn **Mover**, IAM có thể tra nhóm phù hợp rồi kiểm tra membership; trong **Leaver**, bộ lọc giúp **phát hiện tài khoản cần thu hồi** hoặc rà soát tài khoản còn `active`. Tuy nhiên, **kết quả tìm kiếm không phải là quyết định danh tính hoặc quyết định cấp quyền**: phải kiểm tra binding đúng người, nguồn dữ liệu có thẩm quyền, chính sách và trạng thái thực tế trước khi sửa tài nguyên.

Bài thuộc chương **SCIM provisioning** trong module **quản lý vòng đời danh tính IAM (Identity and Access Management)** theo mô hình **Joiner–Mover–Leaver (JML)**. Nội dung liên hệ bộ lọc SCIM với **IdP, SSO, RBAC/ABAC, tài khoản dịch vụ, kiểm toán, deprovisioning và giảm quyền truy cập tồn dư**. Mục tiêu là biết viết, đọc và kiểm tra filter chính xác; nhận diện giới hạn của service provider; thiết kế truy vấn vừa an toàn vừa có ích cho đối soát.

> **Nguyên tắc cần nhớ:** **SCIM filter dùng để lựa chọn tài nguyên**, không phải một cơ chế phân quyền. Server vẫn phải xác thực và cho phép client thực hiện truy vấn; ứng dụng vẫn phải đánh giá quyền trên từng tài nguyên, và IAM vẫn phải xác minh mối liên hệ giữa các account.

## 1. Filter đứng ở đâu trong kiến trúc SCIM?

SCIM mô tả tài nguyên và giao thức HTTP phục vụ quản lý danh tính giữa các hệ thống. Một bên thường đóng vai **SCIM client** (IdP, IAM/IGA hoặc provisioning connector), bên kia là **SCIM service provider** (ứng dụng đích).

~~~mermaid
flowchart LR
    HR["HRIS / contractor source"] --> IAM["IAM/IGA: identity, JML, policy"]
    IAM --> IDP["IdP: đăng nhập SSO và thuộc tính"]
    IAM --> CLIENT["SCIM client / connector"]
    CLIENT -->|GET /Users?filter=...| SCIM["SCIM service provider"]
    SCIM --> DB["User / Group / entitlement state"]
    SCIM -->|ListResponse / resource| CLIENT
    CLIENT -->|POST / PATCH / DELETE được phép| SCIM
    SCIM --> APP["Ứng dụng: account, nhóm, role"]
    APP --> AUTHZ["RBAC/ABAC: kiểm soát tài nguyên"]
    APP --> AUD["Readback, reconciliation, audit"]
    AUD --> IAM
~~~

Filter nằm ở **bước truy vấn hoặc tìm kiếm**. Nó có thể hỗ trợ các tác vụ provisioning, nhưng **không thay thế thao tác tạo/sửa/xóa tài nguyên**:

| Công việc | Phương thức/cơ chế thường dùng | Vai trò của filter |
| --- | --- | --- |
| Tìm user theo username | `GET /Users?filter=...` hoặc `POST /Users/.search` nếu được hỗ trợ. | Tìm những User thỏa điều kiện. |
| Tìm group theo tên | `GET /Groups?filter=...`. | Tìm Group phù hợp; sau đó phải xác minh ID. |
| Đọc user khi đã biết SCIM ID | `GET /Users/{id}`. | **Không cần filter** nếu ID đã được xác minh. |
| Tạo user mới | `POST /Users`. | Có thể dùng tìm kiếm trước để giảm tạo trùng, nhưng `POST` mới là thao tác tạo. |
| Cập nhật user | `PATCH /Users/{id}` hoặc `PUT` theo hỗ trợ. | Có thể dùng filter để tìm đúng ID trước; body PATCH là bước sửa riêng. |
| Gỡ một thành viên group | `PATCH /Groups/{id}` với đường dẫn `members[value eq "..."]`. | Đây là **valuePath trong SCIM PATCH**, không phải query parameter `filter`. |
| Thu hồi account trong Leaver | Thường là `PATCH active=false` hoặc thao tác target hỗ trợ theo chính sách. | Filter giúp xác định/đối soát account; không tự vô hiệu hóa account. |
| Kiểm tra quyền truy cập tài nguyên | Policy ứng dụng, RBAC/ABAC hoặc engine tương ứng. | **Không sử dụng filter như bằng chứng được phép**. |

### 1.1. SCIM User khác account ở IdP

Một nhân viên có thể có IAM identity `person-2048`, account IdP `idp-user-581` và SCIM User `u-9008` tại một ứng dụng. Các ID này **khác phạm vi**. Filter từ client đến ứng dụng phải dùng **thuộc tính và giá trị trong schema của ứng dụng đích**, không mặc định lấy IAM ID làm `User.id` của provider.

Nếu người dùng đã có **target account ID** được mapping và kiểm chứng, `GET /Users/u-9008` thường rõ ràng hơn `filter=userName eq "..."`. Filter hữu ích nhất ở bước **khám phá, đối chiếu hoặc điều tra**, không nhất thiết là thao tác mặc định cho mọi lần cập nhật.

## 2. Cú pháp nền tảng theo SCIM 2.0

SCIM 2.0 định nghĩa cú pháp filter trong **RFC 7644, phần 3.4.2.2**, với đường dẫn thuộc tính theo mô hình **RFC 7643**. Filter diễn đạt một biểu thức có thể được đánh giá là **đúng hoặc sai** đối với mỗi tài nguyên.

Mẫu đơn giản:

~~~text
<attributePath> <comparisonOperator> <comparisonValue>

Ví dụ:
userName eq "lan@example.invalid"
active eq true
name.familyName sw "Ng"
meta.lastModified gt "2026-11-01T00:00:00Z"

Hoặc kiểm tra hiện diện:
nickName pr
~~~

Bảng thuật ngữ:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **`attrPath`** | Đường dẫn thuộc tính tài nguyên được schema nhận biết. | `userName`, `name.familyName`, `externalId`. |
| **Comparison operator** | Phép so sánh trên giá trị/thuộc tính. | `eq`, `co`, `pr`. |
| **Comparison value** | Literal có kiểu phù hợp với thuộc tính. | `"Lan"`, `true`, `25`, chuỗi ngày giờ. |
| **Logical expression** | Kết hợp những biểu thức điều kiện. | `and`, `or`, `not (...)`. |
| **ValuePath** | Kiểm tra một phần tử trong thuộc tính phức hợp nhiều giá trị. | `emails[type eq "work" and value co "@example.invalid"]`. |

**Filter không phải SQL**, không dùng `SELECT`, `JOIN` hoặc biểu thức tùy ý của ngôn ngữ lập trình. Nó cũng **không phải regex**. Thay vì cho người dùng nhập một “truy vấn toàn năng”, client nên xây dựng biểu thức từ những thuộc tính/toán tử mà sản phẩm và server thực sự hỗ trợ.

### 2.1. Các toán tử so sánh

| Toán tử | Tên | Ví dụ | Ghi chú |
| --- | --- | --- | --- |
| `eq` | equals | `userName eq "lan@example.invalid"` | So khớp bình đẳng theo ngữ nghĩa thuộc tính. |
| `ne` | not equals | `userType ne "Employee"` | Không giống việc “thuộc tính không tồn tại”; cần xét giá trị thiếu theo filter semantics. |
| `co` | contains | `displayName co "Lan"` | So khớp chuỗi chứa chuỗi con. |
| `sw` | starts with | `userName sw "lan."` | So khớp chuỗi bắt đầu bằng chuỗi con. |
| `ew` | ends with | `emails.value ew "@example.invalid"` | So khớp chuỗi kết thúc bằng chuỗi con. |
| `pr` | present | `externalId pr` | Không cần literal so sánh; kiểm tra thuộc tính có hiện diện. |
| `gt` | greater than | `meta.lastModified gt "2026-11-01T00:00:00Z"` | Dùng cho kiểu hỗ trợ thứ tự như dateTime, number. |
| `ge` | greater/equal | `meta.created ge "2026-10-01T00:00:00Z"` | Lớn hơn hoặc bằng theo kiểu dữ liệu. |
| `lt` | less than | `meta.created lt "2026-12-01T00:00:00Z"` | Nhỏ hơn. |
| `le` | less/equal | `meta.created le "2026-11-30T23:59:59Z"` | Nhỏ hơn hoặc bằng. |

Điều kiện so sánh phụ thuộc **kiểu dữ liệu** và **metadata schema**, không phải chỉ kiểu ký tự nhìn thấy. `"25"` là chuỗi, còn `25` là số; `"true"` là chuỗi, còn `true` là boolean. Không dùng `co` cho một trường boolean hay hy vọng server chấp nhận cú pháp không phù hợp rồi tự sửa kiểu.

### 2.2. Toán tử logic và dấu ngoặc

Có thể ghép điều kiện với `and`, `or` và phủ định `not`, dùng ngoặc để làm rõ ý định:

~~~text
active eq true and userType eq "Employee"

userType eq "Employee" or userType eq "Contractor"

active eq true and (userType eq "Employee" or userType eq "Contractor")

not (active eq true)

(userName sw "lan" or name.familyName eq "Tran") and active eq true
~~~

**Ưu tiên đặt ngoặc khi trộn `and` và `or`** để người đọc lẫn server đều có ý định rõ ràng. Không dựa vào các cách “đoán” thứ tự ưu tiên từ SQL hay ngôn ngữ khác.

Các toán tử/keyword và tên thuộc tính có quy tắc không phân biệt chữ hoa/thường theo SCIM; **giá trị chuỗi** vẫn phải được so sánh theo metadata `caseExact` của thuộc tính và quy định của provider. Không suy ra mọi tên người, email hoặc ID đều case-insensitive.

### 2.3. Literal chuỗi, số, boolean và ngày giờ

~~~text
userName eq "lan@example.invalid"             # Chuỗi
active eq false                                 # Boolean, không có dấu nháy
employeeNumber eq "004281"                      # Ví dụ HR identifier phải giữ số 0 đầu
meta.lastModified ge "2026-11-01T00:00:00Z"    # Chuỗi biểu diễn dateTime
roles pr                                        # Kiểm tra hiện diện
~~~

Các dòng sau `#` ở đây chỉ là **chú thích giải thích trong tài liệu**, không phải ký hiệu comment được định nghĩa trong grammar SCIM filter. **Không gửi nguyên cả dòng có `# ...`** làm filter.

Trong biểu thức mở rộng Enterprise User, `employeeNumber` là thuộc tính thuộc extension URN, không mặc nhiên là thuộc tính top-level của SCIM User. Phần 5 giải thích cú pháp tham chiếu đúng.

**Cần phân biệt `active eq false` và `active pr`:** thuộc tính `active` có giá trị `false` vẫn là một thuộc tính hiện diện; `pr` không phải phép kiểm tra “truthy” của JavaScript.

## 3. Filter trên thuộc tính đơn và thuộc tính lồng

Schema SCIM phân biệt thuộc tính đơn, phức hợp và thuộc tính nhiều giá trị (*multi-valued*). Đường dẫn của filter cần tôn trọng cấu trúc đó.

Ví dụ một User minh họa:

~~~json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "id": "u-9008",
  "userName": "lan@example.invalid",
  "active": true,
  "name": {
    "givenName": "Lan",
    "familyName": "Nguyen",
    "formatted": "Nguyen Lan"
  },
  "emails": [
    {
      "value": "lan@example.invalid",
      "type": "work",
      "primary": true
    },
    {
      "value": "lan.personal@example.invalid",
      "type": "home"
    }
  ],
  "meta": {
    "resourceType": "User",
    "created": "2026-10-15T08:00:00Z",
    "lastModified": "2026-11-18T13:20:00Z"
  }
}
~~~

Các biểu thức có thể là:

| Filter | Ý nghĩa |
| --- | --- |
| `userName eq "lan@example.invalid"` | So sánh thuộc tính chuỗi đơn. |
| `active eq true` | So sánh boolean. |
| `name.familyName eq "Nguyen"` | So sánh **sub-attribute** của một complex attribute. |
| `meta.lastModified gt "2026-11-01T00:00:00Z"` | So sánh thuộc tính thời gian thuộc `meta`. |
| `emails.value co "@example.invalid"` | Tìm User có ít nhất một giá trị email phù hợp, nếu provider hỗ trợ lọc sub-attribute này. |
| `emails pr` | Tìm User có thuộc tính emails hiện diện theo ngữ nghĩa của provider/SCIM. |
| `emails[type eq "work" and value eq "lan@example.invalid"]` | Có một phần tử email cụ thể đồng thời thỏa cả type và value. |

**Lưu ý quan trọng:** không được giả định mỗi server đều hỗ trợ filter với tất cả thuộc tính phức hợp/sub-attribute. Hãy kiểm tra **`/Schemas`**, `/ServiceProviderConfig`, khả năng tài nguyên và thử nghiệm thực tế.

## 4. ValuePath: điều kiện trên cùng một phần tử của mảng

Đây là phần dễ nhầm nhất khi lọc các thuộc tính **multi-valued complex**. Xét User có:

~~~json
{
  "emails": [
    { "type": "work", "value": "lan@company.example.invalid" },
    { "type": "home", "value": "lan@personal.example.invalid" }
  ]
}
~~~

### 4.1. Hai điều kiện độc lập chưa chắc áp dụng trên cùng phần tử

~~~text
emails.type eq "work" and emails.value co "personal"
~~~

Biểu thức này có thể được đánh giá đúng vì **có một email type=work** và **có một email khác chứa "personal"**. Nó không buộc hai điều kiện cùng thuộc một phần tử. Đây là lỗi logic nguy hiểm nếu client dùng kết quả để suy ra email công việc đã được xác minh.

### 4.2. ValuePath trong ngoặc vuông ràng buộc cùng phần tử

~~~text
emails[type eq "work" and value co "personal"]
~~~

Biểu thức này yêu cầu **ít nhất một email trong mảng** thỏa **cả** điều kiện type và value. Với dữ liệu ví dụ, nó **không khớp**. Để tìm email công việc đúng:

~~~text
emails[type eq "work" and value eq "lan@company.example.invalid"]
~~~

**Quy tắc thực hành:** nếu bạn cần một phần tử mảng thỏa đồng thời nhiều điều kiện, hãy dùng **valuePath** đúng cú pháp thay vì kết hợp các `emails.subAttribute` độc lập.

### 4.3. ValuePath không tự xác nhận email đã được kiểm chứng

Một User có `emails[type eq "work"]` không chứng minh người đó đang làm việc hoặc đã sở hữu email công việc. Thuộc tính có thể do client nhập hoặc đồng bộ từ nguồn chưa được xác minh. **Identity proofing, nguồn HRIS, trạng thái employment, account linking và quyền** vẫn phải được xử lý theo chính sách.

## 5. Filter thuộc tính Enterprise User extension

Ngoài **Core User schema**, SCIM có extension **Enterprise User** với các trường phục vụ ngữ cảnh tổ chức, chẳng hạn `employeeNumber`, `department`, `division`, `costCenter` hoặc `manager` theo cấu trúc được hỗ trợ.

Một tài nguyên minh họa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "u-9008",
  "userName": "lan@example.invalid",
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "004281",
    "department": "Finance",
    "manager": {
      "value": "u-1000"
    }
  }
}
~~~

Filter dùng attribute path có **schema URI**:

~~~text
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber eq "004281"

urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department eq "Finance"
~~~

Một số provider hỗ trợ cú pháp rút gọn, mapping hoặc tên field riêng; những khác biệt đó **không phải bằng chứng syntax rút gọn là chuẩn SCIM portable**. Client cần tra `/Schemas` và hợp đồng target để biết extension có được công bố, có dữ liệu và có filter được hay không.

### 5.1. Employee number không phải ID tài khoản SCIM

| Giá trị | Ai quản lý / phạm vi | Có thể dùng để làm gì? |
| --- | --- | --- |
| `id` | Service provider gán cho resource tại target. | `GET /Users/{id}` hoặc thao tác chính xác tại target. |
| `externalId` | Client cấp, do provider hỗ trợ, ý nghĩa/phạm vi do tích hợp xác định. | Hỗ trợ correlation nếu hợp đồng quản lý uniqueness rõ. |
| Enterprise `employeeNumber` | Dữ liệu nhân sự trong extension, theo nguồn và chính sách tổ chức. | Hỗ trợ đối soát với HRIS; cần phạm vi duy nhất/nguồn chuẩn. |
| `userName` | Giá trị tên đăng nhập/định danh được SCIM provider quản lý theo schema. | Hỗ trợ tìm account; có thể thay đổi theo chính sách. |
| IAM identity ID | IAM/IGA nội bộ. | Liên kết người với nhiều account ở nhiều ứng dụng. |
| IdP OIDC `(iss, sub)` | Issuer và subject do OP cung cấp. | Liên kết login SSO với account theo hợp đồng tin cậy. |

`externalId` **không phải** `User.id`, và `employeeNumber` có thể trùng giữa pháp nhân, đợt tái tuyển hoặc hai nguồn HRIS nếu không có namespace. **Không tự liên kết một User vào người chỉ vì filter trả một kết quả**; cần xem cả issuer/source, tenant, employment record và chính sách correlation.

## 6. Thực hiện filter qua GET

SCIM hỗ trợ truy vấn collection bằng HTTP, thường với tham số query `filter`. Ví dụ:

~~~http
GET /scim/v2/Users?filter=userName%20eq%20%22lan%40example.invalid%22&startIndex=1&count=20 HTTP/1.1
Host: scim.example.invalid
Accept: application/scim+json
Authorization: Bearer <provisioning-access-token>
~~~

Dạng filter đã giải mã là:

~~~text
userName eq "lan@example.invalid"
~~~

**Giá trị `filter` trong URL phải được percent-encode** theo quy tắc URI. Đặc biệt dấu cách, dấu nháy, dấu `@`, `[`, `]` và ký tự đặc biệt cần được encode đúng khi gửi URL. Không tự thay ký tự bằng cách cắt nối không escape.

### 6.1. Mẫu kết quả ListResponse

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
      "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
      "id": "u-9008",
      "userName": "lan@example.invalid",
      "active": true
    }
  ]
}
~~~

Ý nghĩa:

- `totalResults`: tổng số tài nguyên khớp theo đáp ứng của provider.
- `startIndex`: vị trí trang trả về, đánh số từ **1** trong SCIM.
- `itemsPerPage`: số mục thực sự trong trang.
- `Resources`: các tài nguyên thỏa filter trên trang, có thể không chứa mọi thuộc tính nếu server áp dụng projection/permissions.

**`HTTP 200` kèm ListResponse không có nghĩa có user phù hợp.** Trường hợp không có kết quả thường có `totalResults: 0` và danh sách rỗng/không có resource theo hợp đồng provider. Client phải kiểm tra cả số kết quả và dữ liệu thực tế trước khi quyết định tạo tài khoản mới.

### 6.2. Lọc Group theo tên

~~~http
GET /scim/v2/Groups?filter=displayName%20eq%20%22finance-readers%22 HTTP/1.1
Accept: application/scim+json
Authorization: Bearer <provisioning-access-token>
~~~

Khi tìm đúng Group, **lưu `id` thực tế**. Group `displayName` có thể bị đổi tên hoặc trùng ở nhiều target/tenant nếu không có hợp đồng uniqueness toàn cục. Thao tác sửa membership nên nhắm tới Group ID đã xác minh.

### 6.3. Filter không đồng nghĩa có quyền xem mọi User

SCIM endpoint thường phục vụ dữ liệu nhạy cảm về danh tính, quan hệ và nhóm. Server cần **xác thực client, phân quyền truy vấn, giới hạn trường trả về và kiểm soát tenant**. Một query hợp lệ về cú pháp có thể bị `403`, lọc dữ liệu theo phạm vi hoặc từ chối vì privacy. **Không chỉnh filter để vượt giới hạn truy cập**; phải dùng credential/scope được cấp hợp lệ cho workflow IAM.

## 7. POST search: filter nằm trong JSON thay vì query string

SCIM định nghĩa cơ chế **search request** dùng `POST` với body JSON, hữu ích khi biểu thức dài hoặc chứa nhiều ký tự cần encode. Endpoint có thể là `/Users/.search`, `/Groups/.search` hoặc `/.search` theo khả năng của provider.

~~~http
POST /scim/v2/Users/.search HTTP/1.1
Host: scim.example.invalid
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:SearchRequest"
  ],
  "filter": "active eq true and emails[type eq \"work\" and value co \"@example.invalid\"]",
  "startIndex": 1,
  "count": 100
}
~~~

Body JSON chứa chuỗi filter đã escape bằng quy tắc JSON. Sau khi parse, server nhận biểu thức:

~~~text
active eq true and emails[type eq "work" and value co "@example.invalid"]
~~~

**Không phải mọi service provider đều triển khai POST search hoặc mọi endpoint thay thế như nhau.** Cần kiểm tra metadata khả năng và kiểm thử target. Nếu ứng dụng chỉ hỗ trợ GET filter ở collection, client phải dùng cách tích hợp tương thích hoặc áp dụng chiến lược đối soát khác được phép.

### 7.1. Khi nào chọn GET và khi nào chọn POST?

| Tiêu chí | GET với `filter` | POST `.search` |
| --- | --- | --- |
| Biểu thức ngắn, URL đơn giản | Thuận tiện. | Vẫn có thể dùng nếu hỗ trợ. |
| Biểu thức dài, nhiều ký tự đặc biệt | Có giới hạn URL ở gateway/proxy. | Body JSON thường dễ quản lý hơn. |
| Log hạ tầng | Query string có thể xuất hiện trong access log. | Body thường ít xuất hiện trong access log mặc định, nhưng vẫn cần bảo vệ. |
| Cache/proxy | Có thể chịu ảnh hưởng cache nếu thiết kế không an toàn. | Đảm bảo cache và proxy áp dụng chính sách riêng. |
| Tương thích | Phụ thuộc `filter.supported` và provider. | Phụ thuộc provider hỗ trợ search endpoint. |

**POST search là đọc/tìm kiếm**, không có nghĩa “POST tạo mới”. Đừng trộn `POST /Users/.search` với `POST /Users`.

## 8. SCIM PATCH valuePath khác query filter ra sao?

Một bộ lọc xuất hiện ở hai ngữ cảnh dễ bị nhầm:

1. **Query filter** trong `GET /Users?filter=...` hoặc SearchRequest, dùng để **tìm tài nguyên**.
2. **ValuePath** trong `PATCH`, ví dụ `members[value eq "u-9008"]`, dùng để chọn **phần tử bên trong tài nguyên đã biết**.

Ví dụ nhóm `g-prod-23` chứa User `u-9008`. IAM xác định phải thu hồi membership khi nhân viên Mover/Leaver:

~~~http
PATCH /scim/v2/Groups/g-prod-23 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"u-9008\"]"
    }
  ]
}
~~~

**Giải thích chính xác:**

- `/Groups/g-prod-23` xác định **Group cần sửa**.
- `members[...]` là **PATCH operation path**, không phải `filter` query.
- `value eq "u-9008"` chọn phần tử member có `value` là SCIM User ID tại chính provider.
- `remove` yêu cầu gỡ membership đó theo hành vi PATCH của server.
- Kết quả PATCH thành công cần **GET lại Group/membership** và khi cần **kiểm tra quyền thực tế tại ứng dụng**.

**Đừng tự giả định “PATCH remove lặp lại vô hạn luôn trả thành công”.** Provider có thể khác nhau về xử lý đường dẫn không tồn tại, optimistic concurrency và response. Một retry an toàn nên **đọc lại trạng thái trước** rồi quyết định có cần thử tiếp.

### 8.1. Vì sao không nên thay danh sách members bằng snapshot cũ?

Nếu thay toàn bộ mảng members bằng `PUT` hoặc PATCH replace, một bản ghi stale có thể vô tình **xóa người mới được thêm** hoặc **thêm lại người vừa bị gỡ**. Khi phải ghi theo snapshot, áp dụng đồng bộ/ETag/`If-Match` nếu provider hỗ trợ và đọc lại sau ghi.

**Không nhầm filter với một transaction.** Filter tìm resource hoặc phần tử, nhưng không cung cấp khóa đồng thời, nguyên tử xuyên ứng dụng hoặc bảo đảm kết quả áp dụng ngay lập tức.

## 9. Khả năng filter của server: ServiceProviderConfig và Schemas

SCIM định nghĩa các tài nguyên metadata phục vụ khám phá khả năng, đáng chú ý là:

- `GET /ServiceProviderConfig`: khả năng như hỗ trợ filter, PATCH, bulk, sort, ETag và giới hạn.
- `GET /Schemas`: schema/attribute definition được provider công bố.
- `GET /ResourceTypes`: loại tài nguyên và schema extension tương ứng.

Một phần response minh họa của `/ServiceProviderConfig`:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
  ],
  "filter": {
    "supported": true,
    "maxResults": 200
  },
  "patch": {
    "supported": true
  },
  "sort": {
    "supported": false
  },
  "etag": {
    "supported": true
  }
}
~~~

**Đây là ví dụ rút gọn**, không phải toàn bộ resource bắt buộc. Không tự suy ra provider thực tế hỗ trợ mọi tổ hợp filter chỉ vì `filter.supported = true`. Các đường dẫn complex, extension schema, phân trang lớn hoặc giá trị `not` có thể có hạn chế triển khai và cần kiểm thử.

### 9.1. `caseExact` và `returned` trong Schema

SCIM schema metadata có thể mô tả kiểu, tính nhiều giá trị, `caseExact`, `uniqueness`, `mutability`, `returned` và thuộc tính phụ. Chúng ảnh hưởng cách client diễn giải filter và kết quả:

| Thuộc tính schema | Ảnh hưởng |
| --- | --- |
| `type` | Xác định giá trị chuỗi, boolean, number, dateTime, complex... để so sánh đúng. |
| `multiValued` | Chỉ ra có thể có nhiều giá trị; cần cân nhắc valuePath và điều kiện cùng phần tử. |
| `caseExact` | Quy định ngữ nghĩa phân biệt hoa/thường cho so sánh chuỗi. |
| `uniqueness` | Cung cấp ràng buộc duy nhất trong phạm vi mà schema định nghĩa. |
| `mutability` | Chỉ ra quy tắc sửa thuộc tính; ảnh hưởng workflow provisioning. |
| `returned` | Quy định khi nào thuộc tính được trả trong representation; không nên xem “không thấy trong response” luôn đồng nghĩa “không có trong DB”. |

Với extension hoặc thuộc tính không hỗ trợ lọc, provider có thể từ chối yêu cầu. **Không thay metadata schema bằng suy đoán từ một JSON response cá biệt**.

### 9.2. Khi provider không hỗ trợ filter

SCIM có thể từ chối filter vì không triển khai hoặc vì filter không hợp lệ. Theo SCIM protocol, **`501 Not Implemented`** có thể biểu thị không hỗ trợ filtering; lỗi cú pháp thường là **`400 Bad Request`**, có thể đi kèm SCIM error type `invalidFilter`.

Client nên:
1. Kiểm tra khả năng được công bố.
2. Giới hạn filter ở các thuộc tính/toán tử provider hỗ trợ.
3. Dùng bản ghi ID đã lưu khi có thể.
4. Chỉ dùng fallback như **đọc trang có giới hạn và đối soát** nếu được phép về bảo mật, quy mô và dữ liệu.
5. Cảnh báo operator khi không thể tìm đúng account với độ tin cậy cần thiết; **không đoán** target ID.

## 10. Phân trang, sắp xếp và tập kết quả không ổn định

SCIM dùng phân trang với `startIndex` và `count`. `startIndex` có **giá trị bắt đầu từ 1**, `count` là số mục client đề nghị lấy, provider có thể áp giới hạn hoặc trả ít hơn.

~~~http
GET /scim/v2/Users?filter=active%20eq%20true&startIndex=1&count=100 HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Accept: application/scim+json
~~~

Để duyệt nhiều trang, client dùng `itemsPerPage` và `totalResults` được trả về theo ngữ nghĩa provider, đồng thời phải xử lý các trường hợp có thay đổi dữ liệu trong lúc quét.

### 10.1. Ví dụ luồng quét đối soát

~~~text
Filter mục tiêu: active eq true

Trang 1: startIndex=1, count=100
Response: totalResults=245, itemsPerPage=100

Trang 2: startIndex=101, count=100
Response: totalResults=245, itemsPerPage=100

Trang 3: startIndex=201, count=100
Response: totalResults=245, itemsPerPage=45
~~~

Đây là **ví dụ tập dữ liệu đứng yên**. Trong thực tế, giữa các trang có thể phát sinh Joiner, Mover, Leaver; tổng số và vị trí phần tử thay đổi. **SCIM pagination không tự bảo đảm một snapshot nguyên tử** khi provider đang cập nhật dữ liệu.

### 10.2. Khuyến nghị khi cần đối soát tập lớn

- Phân biệt **quét inventory** với **truy vấn lookup một user**; lookup một user nên dùng khóa có chỉ mục hoặc mapping sẵn.
- Ưu tiên lọc hẹp theo `id`/`externalId`/`userName` hoặc thuộc tính tương thích, thay vì quét toàn bộ nếu không cần.
- Đặt giới hạn `count` và thời gian; tôn trọng `maxResults`, rate limit và quyền truy cập dữ liệu.
- Nếu provider hỗ trợ `sortBy` và `sortOrder`, có thể dùng để tăng tính ổn định, nhưng **sort không thay thế snapshot isolation**.
- Khi cần incremental reconciliation, có thể xét `meta.lastModified` theo hợp đồng timestamp của provider, kèm **cửa sổ chồng lấn, deduplication và kiểm tra trạng thái hiện hành** để giảm bỏ sót.
- Với dữ liệu biến động nhanh hoặc độ quan trọng cao, chạy **full reconciliation định kỳ** hoặc phương thức đồng bộ khác khi được cho phép.
- Ghi lại điểm bắt đầu/kết thúc, phạm vi truy vấn, số trang, mục thiếu/trùng và các lỗi chưa xử lý.

**Không tự cho rằng `meta.lastModified` luôn phản ánh mọi thay đổi bên trong group hoặc mọi entitlement tại ứng dụng**. Cần kiểm chứng target có cập nhật timestamp tương ứng và có cho phép lọc trường này không.

## 11. Lọc và chuẩn hóa chuỗi an toàn

### 11.1. Không nối giá trị người dùng vào filter mà không escape

Filter dùng chuỗi trong dấu nháy. Nếu client xây:

~~~text
filter = 'userName eq "' + userSuppliedName + '"'
~~~

một giá trị chứa dấu `"`, dấu `\\` hoặc ký tự đặc biệt có thể làm hỏng cú pháp, dẫn đến kết quả sai hoặc mở rộng filter ngoài dự kiến nếu ứng dụng/server xử lý không chặt chẽ.

Ví dụ JavaScript **minh họa cách xây filter cho một attribute cố định**:

~~~javascript
function buildUserNameFilter(userName) {
  if (typeof userName !== "string" || userName.length > 256) {
    throw new Error("Invalid username");
  }

  // Chỉ chấp nhận tên thuộc tính cố định từ ứng dụng.
  // JSON string literal có quy tắc escape tương thích với
  // string literal trong SCIM filter.
  return "userName eq " + JSON.stringify(userName);
}

const filter = buildUserNameFilter('lan"test@example.invalid');
const uri = "/scim/v2/Users?filter=" + encodeURIComponent(filter);
~~~

**Đây không phải thư viện SCIM hoàn chỉnh.** Trong sản phẩm thực, cần xác minh giới hạn ký tự, encoding, normalization, attribute type, cách escape của client library và provider. Nếu cho phép chọn thuộc tính để lọc, thuộc tính và toán tử phải lấy từ **allowlist schema được duyệt**, không lấy nguyên đoạn filter tùy ý do client không tin cậy gửi vào.

### 11.2. Chuẩn hóa có thể làm thay đổi kết quả

Các trường như `userName`, email hoặc mã nhân viên có chính sách:
- Có phân biệt hoa/thường không?
- Có chuẩn hóa Unicode hoặc khoảng trắng không?
- Có cho phép nhiều email/alias không?
- Có thể được tái sử dụng sau Leaver không?
- Phạm vi uniqueness là một tenant, một directory hay toàn doanh nghiệp?
- Có thể thay đổi khi đổi tên, chuyển bộ phận, tái tuyển không?

Filter `eq` chỉ có ý nghĩa đúng khi client hiểu **ngữ nghĩa thuộc tính**. Không tự chuyển email thành lowercase hoặc xóa dấu tiếng Việt rồi giả định server áp dụng cùng quy tắc, nhất là trong trường `caseExact=true`.

### 11.3. Không biến filter thành công cụ dò thông tin nhân sự

Các truy vấn như `userName sw "a"` hoặc `emails.value co "@company.example.invalid"` có thể được lạm dụng để liệt kê account. Cần:

- Authentication và authorization cho SCIM API client.
- Scope quyền tối thiểu, giới hạn tenant và resource type.
- Rate limiting, size/result caps, timeout và logging phù hợp.
- Chỉ trả attribute cần thiết theo chính sách; bảo vệ PII và audit.
- Không công khai endpoint SCIM cho người dùng cuối không có quyền.
- Không dùng filter response để tiết lộ account tồn tại qua thông báo hỗ trợ công khai.

## 12. Filter trong workflow Joiner

### 12.1. Bài toán account correlation trước khi tạo

Khi nhân viên mới bắt đầu, HRIS/Identity Enrollment thường xác nhận **person identity**, employment record và các thuộc tính có thẩm quyền. SCIM client cần biết liệu target đã có account hợp lệ hay chưa.

Workflow tham khảo:

~~~mermaid
flowchart TD
    H["HRIS: Joiner, identity/employee record"] --> I["IAM xác minh identity và effective date"]
    I --> B{"Đã có target account binding?"}
    B -->|Có| G["GET /Users/{id}, xác minh owner và trạng thái"]
    B -->|Không| F["SCIM filter theo khóa correlation phù hợp"]
    F --> R{"Số ứng viên và độ tin cậy?"}
    R -->|0 ứng viên| C["Tạo mới sau kiểm tra policy và điều kiện"]
    R -->|1 ứng viên nhưng cần xác minh| V["Xác nhận source, tenant, user mapping"]
    R -->|Nhiều hoặc mâu thuẫn| M["Dừng: manual identity review"]
    V -->|Khớp chắc chắn| L["Lưu IAM identity ↔ target account ID"]
    V -->|Không khớp| M
    C --> L
    G --> L
    L --> P["Provision entitlements theo RBAC/ABAC"]
    P --> A["Readback và audit"]
~~~

### 12.2. Thứ tự lookup đề xuất

| Bước | Điều kiện | Hành động |
| --- | --- | --- |
| 1 | IAM đã lưu target account ID đáng tin. | `GET /Users/{id}` và đối chiếu thuộc tính/trạng thái. |
| 2 | Không có binding, provider hỗ trợ `externalId` với uniqueness theo hợp đồng. | Query `externalId eq "..."` trong đúng tenant. |
| 3 | Có extension employee number từ nguồn HR đã xác minh. | Lọc bằng attribute path Enterprise User, kiểm tra phạm vi uniqueness. |
| 4 | Chỉ có username/email. | Lọc để tìm **ứng viên**, không dùng kết quả duy nhất như bằng chứng danh tính tuyệt đối. |
| 5 | Không thể phân giải đáng tin. | Dừng hoặc chuyển review; không tự liên kết/tạo đè tài khoản. |

**Tìm 0 kết quả không chứng minh tuyệt đối user chưa tồn tại**: server có thể hạn chế scope, filter không hỗ trợ, dữ liệu chưa đồng bộ hoặc account dùng alias khác. Với ứng dụng quan trọng, cần xác định độ tin cậy của phương pháp correlation trước khi tạo mới, tránh duplicate và orphaned account.

## 13. Filter trong Mover: nhóm, vai trò và trạng thái

Khi nhân viên đổi vai trò, IAM cần tính lại **desired access** dựa trên các assignment đang có hiệu lực, RBAC/ABAC, approver và SoD. Filter giúp xác định tài nguyên sẽ cập nhật, nhưng không tự xác định tập quyền hợp lệ.

Ví dụ một nhân viên chuyển từ Operations sang Finance:

| Đối tượng | Trạng thái trước | Desired sau | Tác vụ |
| --- | --- | --- | --- |
| `ops-prod-deployers` | Có membership. | Không còn hợp lệ. | Xác định Group ID và gỡ membership, readback. |
| `finance-report-readers` | Chưa có. | Được cấp sau policy/approval. | Tìm Group ID, thêm đúng member và xác minh. |
| `all-employees` | Có membership. | Vẫn hợp lệ. | Giữ nguyên. |
| `cloud-admins` qua nested group | Có đường quyền gián tiếp. | Không còn hợp lệ. | Tìm đường quyền và thu hồi ở nguồn có thẩm quyền. |
| `finance-payment-approve` | Chưa có. | Chưa đủ approval/SoD. | Không tự cấp chỉ vì role name phù hợp. |

### 13.1. Tìm Group và kiểm tra member

Client có thể lọc:

~~~text
displayName eq "ops-prod-deployers"
~~~

Sau đó lấy đúng `Group.id`, tra `members` nếu provider trả và hỗ trợ. Một số provider có thể hỗ trợ tìm Group chứa User bằng filter như:

~~~text
members.value eq "u-9008"
~~~

Tuy nhiên, **khả năng lọc trên group members không được bảo đảm trong mọi provider**. Nhiều hệ thống không biểu diễn đầy đủ **nested group, dynamic group, role được cấp trực tiếp hoặc quyền cloud** qua Group resource SCIM. Phải dùng API hoặc đối soát bổ sung khi cần đánh giá quyền thực tế.

### 13.2. Filter không xóa quyền cũ

Sau khi tìm group, phải thực hiện **PATCH/logic provisioning** tương ứng và **kiểm tra actual state**. Một response filter không còn thấy user trong group SCIM **không chứng minh** role local, token, session hoặc quyền được cấp trực tiếp tại ứng dụng đã mất. Đây là khác biệt giữa **query** và **deprovisioning**.

## 14. Filter trong Leaver: disable, revoke và đối soát

Leaver là tình huống phải chặn quyền truy cập theo thời điểm tổ chức xác định. IAM có thể dùng filter để:
- Tìm account đích khi không có binding ID đáng tin, trong phạm vi đã cho phép.
- Xác nhận các account còn `active` sau sự kiện chấm dứt.
- Tra nhóm/entitlement còn gắn với User tại target.
- Tìm những trường hợp cần remediation khi provisioning thất bại.
- Thực hiện reconciliation theo danh sách Leaver được nguồn nhân sự phê duyệt.

**Tuyệt đối không dùng query `active eq false` như thao tác vô hiệu hóa tài khoản**: filter chỉ *đọc* các tài nguyên có thuộc tính false; nó **không đổi** `active` của bất kỳ User nào.

### 14.1. Ví dụ kế hoạch disable User

Khi đã xác minh `User.id = u-9008`, một thao tác hợp lệ nếu server hỗ trợ:

~~~http
PATCH /scim/v2/Users/u-9008 HTTP/1.1
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

**`active=false` là trạng thái tài nguyên theo SCIM**; ứng dụng có thể có cơ chế khác về khóa phiên, local login, token và entitlement. Sau PATCH, cần `GET /Users/u-9008` và kiểm tra thực tế application access, không chỉ nhìn response thành công.

### 14.2. Từ chối đăng nhập tại IdP không đồng nghĩa toàn bộ đích đã bị chặn

**IdP/SSO** điều khiển xác thực đăng nhập của người dùng theo chính sách, còn **SCIM** cập nhật User/Group tại target. Disable IdP có thể chặn login mới, nhưng session ứng dụng, API key, personal access token hoặc local account vẫn có thể còn đường truy cập. **SCIM filter có thể giúp phát hiện account**, nhưng việc chặn quyền đòi hỏi deprovisioning và readback ở từng hệ thống.

## 15. Trường hợp đặc biệt: tài khoản dịch vụ và workload

**Service account** hoặc **workload identity** có thể xuất hiện dưới dạng SCIM User ở một số ứng dụng, nhưng không nên mặc định chúng thuộc một nhân viên HRIS hay chịu mọi sự kiện JML của người đó.

Ví dụ, một job `billing-etl` có account `svc-billing-01` và được cấp group `report-readers`. Khi engineer sở hữu workload chuyển vai trò:
1. Kiểm tra **owner/team** mới của service identity.
2. Thu hồi quyền quản trị cá nhân đã hết căn cứ.
3. Đánh giá secrets/certificates và khả năng người cũ còn truy cập.
4. Chỉ thay group membership của workload khi **nhu cầu dịch vụ/chính sách quyền** thay đổi.
5. Giữ audit và kế hoạch rotation/deprovision đúng vòng đời workload.

Filter theo tên `svc-*` hoặc `userType eq "Service"` chỉ là **quy ước dữ liệu** nếu provider/tổ chức thực sự sử dụng nó; không có chuẩn chung rằng mọi service account phải có giá trị `userType` đó. Không gỡ quyền workload đang vận hành chỉ vì filter tên có chuỗi “svc”.

## 16. Tình huống xuyên suốt: Joiner → Mover → Leaver

**Bối cảnh:** Công ty có HRIS, IAM/IGA, IdP dùng SSO và ứng dụng Analytics hỗ trợ SCIM. Nhân viên **Lan** có IAM identity `person-2048` và employee number `004281`. Provider Analytics sử dụng `User.id = u-9008` và Group resources riêng.

### 16.1. Joiner — tìm đúng User trước khi tạo

~~~text
IAM đã biết: person-2048; employeeNumber=004281
Target Analytics: chưa có account binding trong inventory

Bước 1: Kiểm tra target schema/ServiceProviderConfig.
Bước 2: Query Enterprise employeeNumber hoặc externalId nếu hợp đồng hỗ trợ.
Bước 3: Đánh giá các kết quả; nếu mâu thuẫn, chuyển manual review.
Bước 4: Tạo hoặc liên kết User, lưu User.id=u-9008.
Bước 5: Cấp nhóm/quyền được duyệt, readback.
~~~

Không kết luận tự động “một user có cùng email là cùng một người”. Hãy xác minh nguồn nhân sự, tenant, mã quan hệ và lịch sử tài khoản, nhất là khi email/username từng được tái sử dụng.

### 16.2. Mover — gỡ nhóm cũ, không chỉ thêm nhóm mới

Khi Lan chuyển sang Finance, IAM tính desired state:

~~~text
KEEP:      all-employees
REMOVE:    ops-prod-deployers
GRANT:     finance-report-readers (nếu policy/approval hợp lệ)
REVIEW:    direct app roles, nested groups, temporary exceptions
~~~

Connector query Group `displayName` để lấy `Group.id` đúng tenant, dùng membership path chuẩn/được hỗ trợ để gỡ User ID tương ứng. Sau đó đọc lại Group và đối soát quyền thực tế. **Filter chọn đúng Group không tự gỡ quyền.**

### 16.3. Leaver — dừng quyền vào đúng thời điểm

Khi HRIS gửi Leaver event:
- IAM dùng binding `u-9008` đã lưu, không cần dò lại bằng email.
- SCIM PATCH hoặc thao tác tương đương disable account khi đến mốc chính sách.
- Kiểm tra Group membership, ứng dụng session/token/local login.
- Readback target và ghi trạng thái remediation nếu quyền còn truy cập.

**Kết quả mong muốn:** IdP từ chối đăng nhập mới và mọi đường truy cập bắt buộc của Lan tại Analytics đã bị chặn; không tự coi một lần GET filter thành công là bằng chứng hoàn tất offboarding.

### 16.4. Ví dụ audit record cho truy vấn và correlation

Đây là **JSON minh họa nội bộ**, không phải event schema của RFC SCIM:

~~~json
{
  "workflowId": "iam-joiner-2048",
  "eventId": "hr-joiner-2026-184",
  "target": "analytics-scim",
  "query": {
    "resourceType": "User",
    "filterTemplate": "externalId eq <bound-value>",
    "resultCount": 1,
    "requestId": "scim-search-1042"
  },
  "correlation": {
    "iamIdentityId": "person-2048",
    "scimUserId": "u-9008",
    "status": "VERIFIED_BY_AUTHORITY"
  },
  "provisioning": {
    "accountState": "ACTIVE",
    "verification": "READBACK_COMPLETE",
    "owner": "analytics-app-owner"
  }
}
~~~

**Không ghi nguyên giá trị nhạy cảm** trong query nếu log không cần; giữ template, correlation ID, resource ID theo chính sách. Không đưa access token hoặc credential vào log. Một filter result count **không thay thế** bằng chứng xác minh liên kết người–account.

## 17. Lỗi thường gặp và troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `400 invalidFilter` | Sai cú pháp, quote, escaping, operator hoặc attributePath. | Kiểm tra grammar, string literal, percent encoding, schema. |
| `501 Not Implemented` khi dùng filter | Provider không hỗ trợ filter. | Xem ServiceProviderConfig và fallback được phép. |
| `200 totalResults=0` nhưng admin nhìn thấy account | Sai tenant, caseExact, attribute khác, dữ liệu chưa đồng bộ hoặc scope hạn chế. | Xác minh target, owner, readback theo ID và schema. |
| `totalResults>1` khi lookup username | Dữ liệu trùng hoặc uniqueness không đúng phạm vi. | Không chọn hàng đầu; chặn correlation và điều tra. |
| Filter `emails.type eq "work" and emails.value co ...` trả kết quả lạ | Hai điều kiện có thể thỏa ở hai phần tử khác nhau. | Dùng valuePath trên cùng phần tử. |
| `employeeNumber` không tìm thấy | Extension không hỗ trợ, chưa có dữ liệu, sai schema URI hoặc số 0 đầu mất. | Tra Schemas/ResourceTypes và nguồn HR mapping. |
| Filter Group membership trả 0 nhưng user vẫn có quyền | Nested group, dynamic group, direct grant, app-specific role hoặc session cũ. | Đối soát effective access, không chỉ SCIM Group. |
| Query GET dài bị 414 hoặc proxy từ chối | URL quá dài hoặc encoding/gateway limitation. | Giảm phạm vi, dùng POST search nếu server hỗ trợ. |
| Thay `active=false` nhưng account vẫn vào app | Session/token/local login độc lập, provider chưa áp policy hoặc propagation delay. | Readback app, kiểm tra access path, remediation. |
| Query bị 401/403 | Credential provisioning hết hạn hoặc scope không đủ. | Refresh/rotate credential theo quy trình; không bypass policy. |
| `429 Too Many Requests` | Rate limit, query quá nhiều hoặc retry ồ ạt. | Backoff có giới hạn và giám sát; không quét vượt quyền. |
| Pagination lặp/thiếu user | Tập dữ liệu thay đổi trong lúc đọc, sort không ổn định. | Dedup, reconciliation nhiều lượt và kiểm tra target. |
| PATCH Group bị conflict/version lỗi | Thay đổi đồng thời hoặc ETag stale. | Đọc lại trạng thái và xây kế hoạch thay đổi mới. |
| Filter lookup đúng nhưng liên kết sai người | Dựa vào email/username làm bằng chứng định danh. | Kiểm tra authoritative identity, target binding và person correlation. |

### 17.1. SCIM error response minh họa

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:Error"
  ],
  "status": "400",
  "scimType": "invalidFilter",
  "detail": "The supplied filter expression is invalid."
}
~~~

Đây là ví dụ mô tả lỗi; nội dung `detail` và mã cụ thể tùy provider. **Không xử lý mọi `400` bằng cách gửi lại y hệt**. Trước khi retry, cần sửa filter hoặc kiểm tra schema/capability.

### 17.2. Cách tiếp cận để tìm nguyên nhân

1. **Tách lớp lỗi:** endpoint/tenant, HTTP authentication, SCIM filter syntax, attribute support, dữ liệu hay account correlation.
2. **Kiểm tra ServiceProviderConfig/Schemas** trong phạm vi đã được phép.
3. **Giảm filter về biểu thức nhỏ** trên thuộc tính có hỗ trợ để khoanh vùng, không dùng truy vấn quá rộng với dữ liệu nhạy cảm.
4. **Đối chiếu tài nguyên qua ID** nếu đã có target ID hợp lệ.
5. **Kiểm tra caseExact, timestamp, encoding** và dữ liệu trả về.
6. **Giám sát rate limit và pagination**, tránh retry không giới hạn.
7. **Ghi nguyên nhân và owner khắc phục**, rồi xác minh desired/actual state.

## 18. Checklist đưa filter vào provisioning production

- [ ] Hiểu rõ **filter chỉ chọn tài nguyên**, không cấp quyền và không tự vô hiệu hóa account.
- [ ] Kiểm tra `/ServiceProviderConfig`, `/Schemas`, `/ResourceTypes` và các giới hạn thực tế của target.
- [ ] Dùng operator đúng kiểu: `eq/ne/co/sw/ew/pr/gt/ge/lt/le`; điều kiện logic có ngoặc rõ ràng.
- [ ] Dùng JSON string literal hợp lệ, đúng boolean/number/dateTime và URI percent encoding.
- [ ] Với complex multi-valued attribute, dùng valuePath khi điều kiện phải khớp cùng phần tử.
- [ ] Khi dùng extension Enterprise User, tham chiếu đầy đủ schema URN theo hợp đồng hỗ trợ.
- [ ] Hiểu `caseExact` và phạm vi uniqueness; không tự biến email/employeeNumber thành khóa định danh tuyệt đối.
- [ ] Có account binding ổn định; ưu tiên `GET /Users/{id}` khi biết ID.
- [ ] Nếu có nhiều ứng viên hoặc dữ liệu mâu thuẫn, đưa vào manual review thay vì chọn ngẫu nhiên.
- [ ] Search GET/POST được thực hiện bằng credential hợp lệ, scope tối thiểu, có giới hạn kết quả và rate limit.
- [ ] Không cho client ngoài truyền filter/issuer/tenant tùy ý để đọc dữ liệu nhạy cảm.
- [ ] Phân biệt query filter với PATCH `members[value eq "..."]`; PATCH có owner, concurrency control và readback.
- [ ] Pagination/reconciliation xử lý tập dữ liệu thay đổi, giới hạn trang và đối soát theo thời gian.
- [ ] Joiner xác minh source/account; Mover thu hồi quyền role cũ; Leaver disable và chặn các đường truy cập có hiệu lực.
- [ ] Đã xét IdP/SSO, SCIM User/Group, application RBAC/ABAC, session/token và direct grants.
- [ ] Service accounts có owner/vòng đời riêng; không gỡ quyền chỉ theo tên `svc` hoặc HR owner.
- [ ] Audit đủ event/tenant/target ID/owner/outcome nhưng không chứa secret hoặc dữ liệu nhân sự dư thừa.
- [ ] Các lỗi filter, 401/403/429, delay và unlinked account có remediation owner và trạng thái kiểm chứng.

## 19. Bài tập tự kiểm tra

### 19.1. Tình huống A — Hai email trong một User

User có một email `type=work` và một email `value=lan@personal.example.invalid` thuộc `type=home`. Tại sao filter `emails.type eq "work" and emails.value co "personal"` có thể khớp dù email công việc không chứa “personal”? Hãy viết lại bằng valuePath để yêu cầu **cùng một phần tử** thỏa cả hai điều kiện.

### 19.2. Tình huống B — Tìm employee number trong extension

Một tổ chức muốn lookup nhân viên có employee number `004281`. SCIM User dùng Enterprise User extension, nhưng truy vấn `employeeNumber eq 4281` trả 0 kết quả. Hãy chỉ ra các lỗi có thể có: sai schema path, dùng number thay string, mất số 0 đầu, target không hỗ trợ extension, dữ liệu/tenant hoặc policy truy vấn.

### 19.3. Tình huống C — Joiner có account trùng email

IAM tạo Joiner cho một nhân viên mới. Filter theo email trả **một User** nhưng email từng thuộc một nhân viên khác đã nghỉ việc. Có được tự liên kết và cấp quyền không? Hãy đề xuất tiêu chí person/HR source/target ID/tenant phải xác minh trước khi quyết định.

### 19.4. Tình huống D — Mover bỏ sót direct grant

Connector tìm nhóm `ops-prod-deployers` và gỡ User bằng SCIM PATCH. Group GET sau đó không còn member, nhưng ứng dụng vẫn cho deploy vì role được cấp trực tiếp. Hãy phân biệt **filter result**, **Group membership state** và **effective access**; đề xuất bước remediation.

### 19.5. Tình huống E — Leaver và status của User

Với `GET /Users?filter=active eq false`, IAM thấy user đã inactive nhưng API key tại ứng dụng vẫn dùng được. Vì sao filter không chứng minh offboarding hoàn tất? Hãy liệt kê các lớp cần readback và cách gắn ticket/owner cho quyền tồn dư.

### 19.6. Tình huống F — Query bị tiêm cú pháp

Ứng dụng ghép `userName` trực tiếp từ input vào biểu thức `userName eq "..."`. Một giá trị chứa dấu nháy làm thay đổi cấu trúc filter. Hãy mô tả cách dùng **JSON string escaping, encodeURIComponent và allowlist attrPath/operator**, và vì sao server vẫn phải phân quyền SCIM API.

### 19.7. Tình huống G — Quét danh sách đang thay đổi

IAM quét `active eq true` theo trang `startIndex` và `count`. Trong lúc quét, HRIS phát ba Leaver và hai Joiner. Vì sao có thể bỏ sót hoặc lặp user? Hãy thiết kế cách dedup, incremental window và full reconciliation để giới hạn sai lệch.

**Điểm cần ghi nhớ:** **SCIM filter** là ngôn ngữ điều kiện để truy vấn **User/Group**; nó cần đúng **cú pháp, kiểu dữ liệu, attribute path, valuePath, schema extension, percent encoding và khả năng của provider**. Đừng nhầm filter với PATCH hoặc authorization; đừng liên kết account chỉ vì username/email trùng; đừng coi `active=false` trong response là đủ chặn mọi session/token. Trong IAM **Joiner–Mover–Leaver**, filter hỗ trợ **tìm đúng tài nguyên**, còn quyết định cấp/gỡ quyền phải dựa trên **nguồn danh tính có thẩm quyền, policy RBAC/ABAC, SCIM provisioning và readback/reconciliation tại ứng dụng đích**.

