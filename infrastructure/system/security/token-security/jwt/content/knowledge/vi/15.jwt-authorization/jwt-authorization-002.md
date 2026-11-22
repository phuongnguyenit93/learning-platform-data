# Biểu diễn scope, role và permission theo hợp đồng ứng dụng

## 1. Bài toán: cùng là thông tin phân quyền, nhưng không cùng ý nghĩa

Một hệ thống sử dụng JSON Web Token (JWT) thường cần diễn đạt những quyền mà access token được phép yêu cầu. Ba khái niệm hay gặp là **scope**, **role** và **permission**. Chúng đều có thể xuất hiện trong claims của JWT, nhưng **không phải ba cách viết thay thế cho cùng một quyền**.

Giả sử một ứng dụng quản lý hóa đơn có các yêu cầu:

- Cổng thanh toán chỉ được gọi những API nằm trong phạm vi đã cấp cho ứng dụng khách.
- Nhân viên kế toán có vai trò phù hợp với công việc của họ trong một tổ chức.
- Người dùng chỉ được xem, sửa hoặc duyệt các hóa đơn cụ thể mà chính sách nghiệp vụ cho phép.
- Khi quyền của một người bị thu hồi, API phải có cách xử lý rủi ro token còn hiệu lực nhưng chứa quyền cũ.

Nếu hệ thống gộp mọi thông tin thành một claim **role = admin**, API rất khó trả lời câu hỏi: admin của **tổ chức nào**, được thực hiện **hành động nào**, trên **tài nguyên nào**, bằng **ứng dụng khách nào**, và theo **chính sách nào**?

Vì vậy, nội dung quan trọng của phần **JWT và phân quyền** trong lĩnh vực **Security - JSON Web Token (JWT)** là thiết kế **hợp đồng ứng dụng (application contract)**: bên phát hành và bên tiếp nhận token phải thống nhất tên claim, kiểu dữ liệu, ngữ nghĩa, phạm vi áp dụng, nguồn sự thật, cách ra quyết định và cách thay đổi hợp đồng theo thời gian.

Các ví dụ trong bài độc lập với ngôn ngữ lập trình, framework, nhà cung cấp danh tính và nền tảng triển khai.

## 2. Phân biệt scope, role và permission

| Thành phần | Câu hỏi chính | Ví dụ trong hệ thống hóa đơn | Phạm vi ý nghĩa |
| --- | --- | --- | --- |
| **Scope** | Token này được cấp phép **yêu cầu loại thao tác nào** đối với API? | **invoice:read**, **invoice:approve** | Thường gắn với quyền được cấp cho access token, ứng dụng khách, API/audience và luồng ủy quyền. |
| **Role** | Chủ thể đang đảm nhiệm **vai trò nghiệp vụ nào** trong một phạm vi quản lý? | **billing_reader**, **invoice_approver** | Thường gắn với người dùng/tài khoản dịch vụ, tổ chức, nhóm hoặc ngữ cảnh nghiệp vụ. |
| **Permission** | Một chủ thể có **khả năng thực hiện hành động cụ thể nào** theo mô hình quyền của ứng dụng? | **invoice.read**, **invoice.approve** | Gần với thao tác nghiệp vụ mà API phải kiểm soát; có thể là quyền trực tiếp hoặc quyền suy ra từ role. |

### 2.1. Scope: giới hạn quyền được cấp cho token

**Scope** mô tả một tập khả năng mà token được cấp. Trong các luồng OAuth 2.0, scope còn liên quan đến những gì ứng dụng khách yêu cầu và máy chủ cấp quyền chấp thuận; tập scope thực tế được cấp có thể nhỏ hơn tập được yêu cầu.

Ví dụ:

~~~text
scope = "invoice:read invoice:approve"
~~~

Theo hợp đồng ví dụ, token có thể được dùng để **yêu cầu** đọc hoặc duyệt hóa đơn qua API tương ứng. Tuy nhiên:

- Scope **invoice:read** không nói người dùng được đọc hóa đơn của tất cả công ty.
- Scope **invoice:approve** không chứng minh người dùng đang giữ chức vụ phê duyệt.
- Scope thuộc token dành cho API A không tự động có hiệu lực ở API B.
- Một token có scope phù hợp vẫn có thể bị từ chối vì trạng thái tài nguyên, tổ chức, chủ sở hữu hoặc chính sách hiện hành.

**Scope là giới hạn quyền của token, không thay thế kiểm tra quyền trên tài nguyên.**

### 2.2. Role: gói nhóm trách nhiệm

**Role** gom các trách nhiệm theo công việc. Ví dụ:

~~~text
billing_reader       -> đọc hóa đơn
billing_editor       -> đọc, tạo, cập nhật hóa đơn
invoice_approver     -> đọc, phê duyệt hóa đơn
billing_auditor      -> kiểm tra hóa đơn theo quy tắc kiểm toán
~~~

Role phải có **ngữ cảnh áp dụng**. Một người có thể là **invoice_approver** tại **company-a** nhưng chỉ là **billing_reader** tại **company-b**. Tên role không đủ để suy ra quyền nếu không biết role đó thuộc tổ chức nào, do bên nào định nghĩa và được ánh xạ thành những permission gì.

Role có thể xuất hiện trong JWT như một ảnh chụp quyền tại lúc phát hành. Nhưng tên role **không mang ý nghĩa chuẩn giống nhau ở mọi hệ thống**; vai trò **admin** của một ứng dụng không mặc nhiên là admin của ứng dụng khác.

### 2.3. Permission: quyền thao tác do ứng dụng định nghĩa

**Permission** thường mô tả một hành động trên một loại tài nguyên:

~~~text
invoice.read
invoice.create
invoice.update
invoice.approve
invoice.export
~~~

Permission có thể được:

1. **Gán trực tiếp:** một tài khoản được cấp quyền duyệt hóa đơn.
2. **Suy ra từ role:** vai trò **invoice_approver** ánh xạ tới permission **invoice.approve**.
3. **Tính theo chính sách:** khả năng duyệt phụ thuộc trạng thái hóa đơn, giới hạn số tiền, người tạo hóa đơn, tổ chức hoặc thời điểm.

Một permission như **invoice.approve** là điều kiện cần cho thao tác phê duyệt trong ví dụ, nhưng chưa đủ nếu chính sách quy định “người lập hóa đơn không được tự duyệt” hoặc “hóa đơn đã thanh toán không được duyệt lại”.

### 2.4. Không suy ra quyền bằng cách ghép tên

Trong bài này, **invoice:approve** là scope, còn **invoice.approve** là permission. Hai tên gần giống nhau nhưng thuộc **hai danh mục khác nhau**, do những phần khác nhau của hợp đồng định nghĩa. Chúng chỉ có liên hệ khi hợp đồng có khai báo ánh xạ rõ ràng.

Ví dụ:

| Scope trong token | Permission tối thiểu mà chính sách có thể yêu cầu |
| --- | --- |
| **invoice:read** | **invoice.read** |
| **invoice:create** | **invoice.create** |
| **invoice:approve** | **invoice.approve** |

Không viết quy tắc kiểu “thay dấu hai chấm bằng dấu chấm sẽ có permission”. Cách đó khiến API vô tình chấp nhận quyền mới chưa được rà soát. Dùng bảng ánh xạ được kiểm soát và có phiên bản.

## 3. JWT chứa những claims nào là do hợp đồng quyết định

JWT định nghĩa một số registered claims phổ biến như **iss**, **sub**, **aud**, **exp**, **iat**, **nbf** và **jti**. Nhưng JWT nói chung **không buộc mọi token phải có roles, permissions hoặc tenant_id**, cũng không định nghĩa một thuật toán phân quyền duy nhất cho chúng.

Trong hệ sinh thái OAuth 2.0, **scope** có quy ước riêng; với profile JWT access token theo RFC 9068, claim **scope** được biểu diễn bằng một chuỗi các scope phân cách bằng dấu cách. Một số hệ thống khác dùng **scp**, mảng chuỗi hoặc cấu trúc riêng. Những biến thể đó **không tương đương tự động**: API phải chọn một hợp đồng cụ thể cho mỗi loại token/issuer.

Các tên như **roles**, **permissions**, **tenant_id** và **authz_contract_version** dưới đây là **claims do ứng dụng ví dụ quy định**. Không được suy luận rằng mọi issuer đều tạo chúng với cùng tên hoặc cùng kiểu.

### 3.1. Ví dụ payload theo hợp đồng của API hóa đơn

Header minh họa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "billing-signing-key-1"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-514",
  "aud": "https://api.example.test/billing",
  "iat": 1900000000,
  "exp": 1900003600,
  "jti": "access-a18e7",
  "client_id": "billing-portal",
  "scope": "invoice:read invoice:approve",
  "tenant_id": "company-a",
  "roles": ["billing_reader", "invoice_approver"],
  "permissions": ["invoice.read", "invoice.approve"],
  "authz_contract_version": 1
}
~~~

Đây chỉ là ví dụ các trường sau khi giải mã, **không phải JWT hoàn chỉnh có chữ ký thực**. Thời gian được chọn để minh họa, không biểu diễn một token đang sử dụng. Giá trị **typ = at+jwt** mô tả trường hợp issuer áp dụng profile JWT access token tương ứng; hệ thống dùng profile khác cần tuân theo hợp đồng riêng. Không được chấp nhận token chỉ vì header tự khai báo loại token như vậy.

Trong ví dụ này:

- **iss** xác định bên phát hành đã được API cấu hình tin cậy.
- **aud** ràng buộc token với API billing, ngăn chuyển token sang dịch vụ khác ngoài mục đích cấp phát.
- **sub** định danh chủ thể trong không gian định danh của issuer; cần xét cùng **iss**.
- **client_id** mô tả ứng dụng khách liên quan theo hợp đồng, không được đồng nhất với **sub**.
- **scope** đặt giới hạn hành động mà access token được cấp cho phép yêu cầu.
- **tenant_id** đặt ngữ cảnh tổ chức của những claims phân quyền theo quy ước này.
- **roles** là ảnh chụp vai trò của chủ thể **trong company-a** tại thời điểm phát hành.
- **permissions** là ảnh chụp khả năng thao tác đã tính theo chính sách của issuer tại thời điểm phát hành.
- **authz_contract_version** chỉ rõ quy tắc diễn giải bộ claims tùy chỉnh.

Điểm quan trọng: **roles và permissions trong ví dụ có thể chứa cùng thông tin ở hai mức trừu tượng**. Hợp đồng phải nói rõ API dựa vào trường nào để quyết định, khi nào cần kiểm tra lại quyền hiện hành, và phải làm gì nếu chúng mâu thuẫn. Nếu không thực sự cần cả hai, nên phát hành ít claims hơn.

## 4. Mẫu hợp đồng claims cho một API

Hợp đồng không chỉ là tên trường trong JSON. Nó phải mô tả **ai có quyền phát hành**, **bên nào được tiếp nhận**, **ý nghĩa từng trường**, **nguồn quyết định**, **kiểu dữ liệu**, **cách kiểm tra**, **chính sách lỗi** và **cách nâng phiên bản**.

### 4.1. Đặc tả minh họa phiên bản 1

~~~yaml
contract_id: billing-access/v1
token_purpose: access_token
trusted_issuer: https://identity.example.test
expected_audience: https://api.example.test/billing
accepted_signature_algorithms:
  - RS256

claims:
  scope:
    type: string
    format: space_delimited_exact_tokens
    required_for_protected_actions: true
  tenant_id:
    type: string
    required_for_tenant_resources: true
  roles:
    type: array_of_strings
    meaning: assigned_roles_at_issue_time
    required: false
  permissions:
    type: array_of_strings
    meaning: allowed_operations_snapshot_at_issue_time
    required_for_billing_operations: true
  authz_contract_version:
    type: integer
    accepted_values: [1]
    required: true

scope_to_action:
  invoice:read: invoice.read
  invoice:create: invoice.create
  invoice:approve: invoice.approve

authorization:
  permission_claim_mode: token_capability_ceiling
  live_membership_check: required
  live_permission_check: required
  resource_policy_check: required
  on_missing_or_invalid_required_claim: deny
  on_unsupported_contract_version: deny
~~~

Đây là một **tài liệu hợp đồng minh họa**, không phải cú pháp cấu hình chuẩn bắt buộc của JWT, OAuth hoặc bất kỳ sản phẩm cụ thể nào. Trong hợp đồng này, claim **permissions** là **giới hạn quyền đã cấp vào token**. API còn phải xác minh quyền hiện hành bên ngoài token. Quyền thực tế là **phần giao** của nhiều giới hạn; một trường không tự mở rộng quyền của trường khác.

### 4.2. Quy tắc cho từng trường

| Claim | Kiểu kỳ vọng | Ngữ nghĩa bắt buộc trong ví dụ | Nếu thiếu hoặc sai kiểu |
| --- | --- | --- | --- |
| **scope** | Chuỗi | Danh sách scope chính xác, phân tách bằng dấu cách; không tự diễn giải như mảng. | Từ chối hành động có yêu cầu scope. |
| **tenant_id** | Chuỗi không rỗng | Tổ chức của quyền trong token; API đối chiếu với tổ chức và tài nguyên thực tế. | Từ chối mọi thao tác cần tenant. |
| **roles** | Mảng chuỗi | Danh sách vai trò tại thời điểm phát hành; chỉ trong tenant đã khai báo. | Không tự tạo role mặc định; các chính sách yêu cầu role phải từ chối. |
| **permissions** | Mảng chuỗi | Giới hạn thao tác cấp cho token tại thời điểm phát hành. | Từ chối các thao tác yêu cầu permission. |
| **authz_contract_version** | Số nguyên | Phiên bản hợp đồng mà API đã biết cách diễn giải. | Từ chối nếu không có cơ chế nhận dạng phiên bản an toàn khác. |

**Cần tách biệt “optional trong payload” với “optional cho một hành động”.** Ví dụ **roles** có thể không bắt buộc đối với API chỉ kiểm tra permission; nhưng nếu một thao tác đòi role phê duyệt hiện hành, việc thiếu role **không** được biến thành “mọi role đều được phép”.

Hợp đồng cũng phải quy định:

- Tên claim có **phân biệt chữ hoa/chữ thường** hay không; thông thường nên so khớp chính xác.
- Tên scope, role và permission có thể chứa những ký tự nào; có cho phép khoảng trắng ở đầu/cuối không.
- Khi gặp phần tử mảng rỗng, sai kiểu, trùng lặp hoặc chưa được hỗ trợ thì xử lý ra sao.
- Một token có thể chứa nhiều tenant hay chỉ một tenant; nếu đa tenant thì biểu diễn và chọn ngữ cảnh thế nào.
- Quyền được phát hành cho **người dùng**, **tài khoản dịch vụ**, hay cả hai; có cần claim xác định loại principal không.
- Có cần coi **roles** và **permissions** là nguồn dữ liệu nhất quán bắt buộc hay chỉ dùng role để hiển thị và kiểm toán.

Để giảm nhập nhằng, hợp đồng nên quy định rõ các tên claim tùy chỉnh hoặc đặt chúng trong một namespace được tổ chức quản lý, đặc biệt khi API tiếp nhận token từ nhiều issuer.

## 5. Thiết kế namespace và quy ước đặt tên

Một claim **roles** có thể là mảng role của toàn công ty, role theo tenant, role do client khai báo hoặc role dành cho một API. Nếu không có hợp đồng, các trường này rất dễ bị hiểu nhầm.

### 5.1. Quy ước scope

Một quy ước dễ đọc là:

~~~text
<resource>:<action>

invoice:read
invoice:create
invoice:update
invoice:approve
payment:refund
~~~

Đây là **quy ước minh họa**, không phải định dạng bắt buộc trong OAuth. Nhóm phát triển nên hạn chế scope quá rộng kiểu **all**, **superuser**, **admin** nếu các API khác nhau có thể diễn giải chúng khác nhau.

Nếu một scope chỉ có ý nghĩa trong một API, phải ràng buộc nó với **audience** và issuer tương ứng. Tên scope giống nhau ở hai API không bảo đảm hai API trao quyền giống nhau.

### 5.2. Quy ước role

Nên chọn tên role mô tả trách nhiệm:

~~~text
billing_reader
billing_editor
invoice_approver
billing_auditor
~~~

Role thường gắn với tổ chức hoặc nhóm:

~~~text
Principal: (issuer, subject) = (identity.example.test, user-514)
Tenant: company-a
Roles: [billing_reader, invoice_approver]
~~~

Không nên dựa vào những chuỗi role có tính toàn cục như **admin** hoặc **user** mà không xác định **lĩnh vực, tenant và nguồn phát hành**. Nếu hệ thống cho phép nhiều bộ role, cần quy định chúng được gán bởi ai và có quyền tác động vào tài nguyên nào.

### 5.3. Quy ước permission

Một quy ước có thể là:

~~~text
<resource>.<operation>

invoice.read
invoice.create
invoice.update
invoice.approve
invoice.export
~~~

Permission nên ổn định theo **hành vi API và nghiệp vụ**, không theo tên nút giao diện. Ví dụ đổi nhãn từ “Duyệt hóa đơn” thành “Phê duyệt” không nhất thiết tạo permission mới; nhưng tách thao tác **approve** thành **approve_limit_under_10000** và **approve_limit_over_10000** có thể là thay đổi chính sách thật sự và cần thiết kế lại quyền.

### 5.4. Namespace cho custom claims

Các tên như **tenant_id**, **roles** hay **permissions** thường là private claims theo hợp đồng hệ thống. Nếu nhiều hệ thống phối hợp, có thể sử dụng tên claim trong một namespace do tổ chức kiểm soát, ví dụ:

~~~json
{
  "https://claims.example.test/billing": {
    "version": 1,
    "tenant_id": "company-a",
    "roles": ["billing_reader"],
    "permissions": ["invoice.read"]
  }
}
~~~

Đây là **một lựa chọn thiết kế** để hạn chế xung đột tên và định nghĩa ranh giới sở hữu. URL trong tên claim chỉ đóng vai trò tên định danh, không hàm ý API được phép truy cập URL đó hoặc tin dữ liệu từ URL. Bên nhận vẫn phải xác minh chữ ký, issuer, audience và hợp đồng. Nếu chọn cấu trúc lồng nhau này, phải cập nhật bộ kiểm tra schema tương ứng; **không** mặc định nhận đồng thời cả dạng phẳng và dạng lồng nhau.

## 6. Role ánh xạ sang permission thế nào?

Trong mô hình **RBAC**, role là nhóm quyền. Chẳng hạn, ứng dụng hóa đơn có thể thiết kế:

| Role | invoice.read | invoice.create | invoice.update | invoice.approve | invoice.export |
| --- | :---: | :---: | :---: | :---: | :---: |
| **billing_reader** | Có | Không | Không | Không | Không |
| **billing_editor** | Có | Có | Có | Không | Không |
| **invoice_approver** | Có | Không | Không | Có | Không |
| **billing_auditor** | Có | Không | Không | Không | Có |

Đây chỉ là ma trận mẫu. Các hành vi thật phải được chủ sở hữu nghiệp vụ duyệt và được quản lý theo phiên bản. Ma trận chưa quyết định **đối tượng** nào được thao tác: một **billing_reader** vẫn chỉ được đọc hóa đơn trong phạm vi công ty và chính sách cho phép.

### 6.1. Hai hợp đồng triển khai phổ biến

**Mô hình A — Phát hành role, API tính permission**

~~~json
{
  "scope": "invoice:read invoice:approve",
  "tenant_id": "company-a",
  "roles": ["invoice_approver"],
  "authz_contract_version": 1
}
~~~

API sở hữu bảng ánh xạ role → permission, lấy role đã xác minh rồi tính tập quyền. Nếu role có thể thay đổi trong thời gian token tồn tại, API phải có biện pháp giới hạn độ trễ hoặc kiểm tra quyền hiện hành. Hợp đồng không cần claim **permissions**, tránh trùng dữ liệu.

**Mô hình B — Phát hành permission, API kiểm tra trực tiếp**

~~~json
{
  "scope": "invoice:read invoice:approve",
  "tenant_id": "company-a",
  "permissions": ["invoice.read", "invoice.approve"],
  "authz_contract_version": 1
}
~~~

Bên phát hành chịu trách nhiệm ánh xạ role và chính sách thành tập permission tại thời điểm cấp token. API kiểm tra permission theo hợp đồng và vẫn đánh giá điều kiện trên tài nguyên. Nếu cần thu hồi quyền ngay, phải bổ sung kiểm tra trạng thái hiện hành hoặc cơ chế thu hồi phù hợp.

Hai mô hình đều có thể hợp lệ. Điều quan trọng là **có một mô tả rõ ai chịu trách nhiệm tính permission**. Nếu phát hành đồng thời cả **roles** và **permissions**, phải chọn một trong các cách hiểu cụ thể:

- **permissions là quyền hiệu lực đã tính**, roles chỉ dành cho hiển thị, truy vết hoặc chính sách phụ được quy định rõ; hoặc
- **roles là đầu vào để API tự tính permission**, còn permissions là tập giới hạn được cấp cho token; kết quả phải nằm trong **giao** của hai tập; hoặc
- **cả hai là các điều kiện cần độc lập** theo một chính sách đã công bố.

Không nên tự động lấy **hợp (union)** của role-derived permissions và token permissions. Ví dụ token có role cho phép đọc và permission cho phép duyệt, phép hợp có thể vô tình cấp cả hai khả năng dù từng nguồn chỉ cho phép một phần.

## 7. Scope, role và permission tham gia quyết định truy cập như thế nào?

Giả sử một người dùng yêu cầu duyệt hóa đơn **INV-100**. Trong một hợp đồng chặt chẽ, API có thể áp dụng công thức:

**ALLOW** khi:

~~~text
TokenValid
AND ScopeAllows(action)
AND TokenPermissionAllows(action)
AND CurrentRoleOrPermissionAllows(principal, action, tenant)
AND ResourcePolicyAllows(principal, action, invoice, context)
~~~

Công thức này là một **chính sách ví dụ có nhiều lớp giới hạn**. Nếu hệ thống dùng mô hình A hoặc B khác, phải định nghĩa các điều kiện tương đương một cách rõ ràng; không có quy tắc JWT nào buộc mọi hệ thống phải sử dụng chính xác công thức trên.

### 7.1. Sơ đồ luồng quyết định

~~~mermaid
flowchart TD
    A["Yêu cầu hành động lên tài nguyên"] --> B{"Xác minh JWT, issuer, audience, thời gian và loại token?"}
    B -- "Không" --> X["Từ chối xác thực"]
    B -- "Có" --> C["Đọc claims theo hợp đồng được hỗ trợ"]
    C --> D{"Scope của token cho phép yêu cầu hành động?"}
    D -- "Không" --> Y["Từ chối quyền truy cập"]
    D -- "Có" --> E{"Permission của token cho phép?"}
    E -- "Không" --> Y
    E -- "Có" --> F["Tra quyền hiện hành và tài nguyên"]
    F --> G{"Quyền hiện hành, tenant và chính sách tài nguyên đều phù hợp?"}
    G -- "Không" --> Y
    G -- "Có" --> H["Thực thi hành động"]
~~~

Nếu hợp đồng không có claim **permissions**, bước kiểm tra đó được thay bằng việc tính permission từ role theo quy tắc đã thống nhất; **không** được coi claim thiếu là một permission cho phép tất cả.

### 7.2. Ví dụ quyền bị thu hẹp ở từng lớp

Token có:

~~~text
Scope:       invoice:read invoice:approve
Permission:  invoice.read invoice.approve
Role ở lúc phát hành: invoice_approver
Tenant:      company-a
~~~

Các trường hợp:

| Trạng thái hiện tại | Vì sao | Quyết định minh họa |
| --- | --- | --- |
| Người dùng còn role phê duyệt; hóa đơn cùng tenant, đang chờ duyệt, không phải người tự tạo | Tất cả điều kiện đều đạt. | **ALLOW** |
| Người dùng bị gỡ role **invoice_approver** sau khi token phát hành | Token còn permission cũ nhưng quyền hiện hành không cho phép. | **DENY** |
| URL yêu cầu hóa đơn thuộc **company-b** | Tenant của tài nguyên nằm ngoài tenant mà quyền được cấp áp dụng. | **DENY** |
| Hóa đơn đã được thanh toán | Trạng thái tài nguyên cấm duyệt lại. | **DENY** |
| Hóa đơn do chính người gọi tạo, chính sách yêu cầu người duyệt khác người lập | Vi phạm tách nhiệm vụ (*separation of duties*). | **DENY** |
| Người dùng có role hiện hành nhưng token chỉ có **invoice:read** | Scope không bao gồm quyền yêu cầu duyệt. | **DENY** |
| Token có scope duyệt nhưng thiếu **invoice.approve** trong permissions | Giới hạn permission của token không cho phép duyệt. | **DENY** |

Tài nguyên thực tế, quyền thành viên hiện hành và chính sách thường nằm **ngoài JWT**. Hợp đồng cần nói rõ có chấp nhận độ trễ của claims hay không. Access token ngắn hạn làm giảm thời gian claims cũ còn hiệu lực, nhưng **không tạo khả năng thu hồi tức thì**.

## 8. Pseudocode: một hợp đồng kiểm tra rõ ràng

Ví dụ sử dụng hợp đồng **billing-access/v1** ở mục 4, trong đó **scope** và **permissions** của token là giới hạn, còn quyền hiện hành và dữ liệu hóa đơn lấy từ nguồn tin cậy.

~~~text
function authorizeInvoiceRequest(request, action):
    verified = validateAccessToken(
        request.bearerToken,
        trustedIssuer = "https://identity.example.test",
        expectedAudience = "https://api.example.test/billing",
        allowedAlgorithms = ["RS256"],
        tokenPurpose = "access_token"
    )
    if verified.failed:
        return DENY_UNAUTHENTICATED

    claims = verified.claims
    if claims.authz_contract_version != 1:
        return DENY_UNSUPPORTED_CONTRACT
    if not matchesBillingClaimSchema(claims):
        return DENY_INVALID_CLAIMS

    principal = resolvePrincipal(claims.iss, claims.sub)
    if principal is null:
        return DENY_FORBIDDEN

    requiredScope = {
        "invoice.read": "invoice:read",
        "invoice.create": "invoice:create",
        "invoice.approve": "invoice:approve"
    }[action]
    if requiredScope is null:
        return DENY_UNKNOWN_ACTION

    scopes = parseExactScopeTokens(claims.scope)
    if requiredScope not in scopes:
        return DENY_FORBIDDEN
    if action not in claims.permissions:
        return DENY_FORBIDDEN

    tenant = claims.tenant_id
    if request.tenantId != tenant:
        return DENY_FORBIDDEN

    membership = loadCurrentMembership(principal, tenant)
    if membership is null or not membership.active:
        return DENY_FORBIDDEN

    currentPermissions = permissionsFromCurrentRoles(membership.roles)
    if action not in currentPermissions:
        return DENY_FORBIDDEN

    invoice = loadInvoiceBoundToTenant(tenant, request.invoiceId)
    if invoice is null:
        return NOT_FOUND
    if not businessPolicyAllows(principal, action, invoice, membership):
        return DENY_FORBIDDEN

    return ALLOW
~~~

Điểm đáng chú ý:

- **validateAccessToken** phải thực hiện kiểm tra mật mã và ràng buộc ngữ cảnh đầy đủ; giải mã payload đơn thuần là chưa đủ.
- **matchesBillingClaimSchema** kiểm tra kiểu và các ràng buộc của hợp đồng **trước khi** diễn giải claims; tránh lỗi “sai kiểu nhưng vẫn gán quyền”.
- **requiredScope** là bảng ánh xạ tường minh, không ghép chuỗi từ input.
- **claims.permissions** là giới hạn quyền của token; **currentPermissions** từ quyền hiện hành là lớp giới hạn thứ hai.
- **loadInvoiceBoundToTenant** chỉ lấy tài nguyên trong tenant được phép; chính sách có thể thêm kiểm tra sở hữu, trạng thái và người duyệt.
- **DENY_FORBIDDEN** là quyết định nội bộ. HTTP API có thể ánh xạ sang **403 Forbidden** hoặc **404 Not Found** theo chính sách che giấu tài nguyên; token thiếu hoặc không hợp lệ thường tương ứng **401 Unauthorized**.

Ở thao tác **tạo hóa đơn**, API cần xử lý riêng trường hợp tài nguyên chưa tồn tại: chính sách dựa vào tenant, dữ liệu tạo và giới hạn nghiệp vụ; không mặc nhiên gọi quy tắc tải hóa đơn đã tồn tại. Pseudocode minh họa tập trung vào các thao tác trên tài nguyên hiện hữu.

## 9. Chuẩn hóa dữ liệu claims: chính xác trước khi cho phép

Một hợp đồng tốt cần nói rõ parser chấp nhận những định dạng nào. Việc “linh hoạt đoán” định dạng của một claim phân quyền có thể tạo lỗ hổng.

### 9.1. Chuỗi scope và mảng scope không phải một

Trong profile minh họa:

~~~json
{
  "scope": "invoice:read invoice:approve"
}
~~~

Đây là một **chuỗi**. Parser tách thành các scope đúng quy tắc đã thống nhất rồi kiểm tra **toàn bộ phần tử**:

~~~text
parse("invoice:read invoice:approve")
    -> {"invoice:read", "invoice:approve"}

containsExact("invoice:read")    -> true
containsExact("invoice:write")   -> false
~~~

Không kiểm tra bằng cách tìm chuỗi con **read**, **admin** hay **invoice**; các giá trị khác có thể chứa cùng đoạn ký tự. Cũng không tự động chấp nhận payload:

~~~json
{
  "scope": ["invoice:read", "invoice:approve"]
}
~~~

...trừ khi **hợp đồng của issuer đó** định nghĩa mảng là kiểu hợp lệ. Nếu hệ thống chuyển sang dùng mảng hoặc claim khác như **scp**, phải tạo phiên bản/adapter cụ thể và kiểm thử, không đoán kiểu trong runtime.

### 9.2. Roles và permissions thường là mảng theo hợp đồng

~~~json
{
  "roles": ["billing_reader", "invoice_approver"],
  "permissions": ["invoice.read", "invoice.approve"]
}
~~~

Với hợp đồng này, các phần tử đều là **chuỗi đã được định nghĩa**. API cần từ chối những kiểu sai nếu chúng ảnh hưởng đến quyết định, chẳng hạn:

~~~json
{
  "roles": "invoice_approver",
  "permissions": [true, 123, "invoice.approve"]
}
~~~

Một số quyết định thiết kế nên được ghi thành điều kiện kiểm tra:

- Chỉ nhận tên thuộc danh mục đã hỗ trợ; các quyền lạ **không** tự động được chấp nhận.
- So khớp chính xác, có quy tắc rõ cho chữ hoa/thường và Unicode.
- Không tự động chuyển số/boolean/object thành chuỗi tên quyền.
- Không ngầm biến chuỗi role đơn thành mảng hoặc ngược lại nếu schema không cho phép.
- Không diễn giải tiền tố như **invoice.*** hay ký tự **\*** thành quyền mọi thao tác trừ khi có một chính sách wildcard được thiết kế và kiểm soát rất rõ ràng; mặc định nên tránh.
- Nếu có phần tử trùng lặp, có thể chuẩn hóa bằng tập hợp sau khi dữ liệu đã hợp lệ; không để trùng lặp tạo cách diễn giải khác.
- Giới hạn số lượng và kích thước claims phù hợp để tránh token quá lớn và chi phí xử lý bất thường.

Nếu nhận JWT từ **nhiều issuer**, cần kiểm tra **issuer → schema và ánh xạ riêng**. Không tự động coi **roles: ["admin"]** của issuer A có cùng sức mạnh với **roles: ["admin"]** của issuer B.

## 10. Ranh giới ủy quyền trong ứng dụng nhiều tổ chức

Tổ chức là ngữ cảnh đặc biệt quan trọng khi biểu diễn role và permission.

Giả sử **user-514** có hai bộ quyền:

~~~text
company-a:
    roles = [invoice_approver]
    permissions = [invoice.read, invoice.approve]

company-b:
    roles = [billing_reader]
    permissions = [invoice.read]
~~~

Một access token dành cho **company-a** không nên tự động được dùng để duyệt hóa đơn của **company-b**, dù người dùng là cùng một người.

### 10.1. Hai cách biểu diễn tenant

**Cách 1 — Một ngữ cảnh tenant trên mỗi token**

~~~json
{
  "tenant_id": "company-a",
  "roles": ["invoice_approver"],
  "permissions": ["invoice.read", "invoice.approve"]
}
~~~

Đây thường là cách đơn giản để hiểu và kiểm tra. Khi đổi tenant, ứng dụng cần lấy token phù hợp với ngữ cảnh quyền mới hoặc sử dụng cơ chế chuyển ngữ cảnh đã được thiết kế.

**Cách 2 — Nhiều tenant trong một token**

~~~json
{
  "tenant_permissions": {
    "company-a": ["invoice.read", "invoice.approve"],
    "company-b": ["invoice.read"]
  }
}
~~~

Nếu chọn cách này, hợp đồng phải định nghĩa cách chọn tenant, định dạng và giới hạn kích thước dữ liệu, nguồn gán quyền và cách chống truy cập chéo. Đây là **custom claim minh họa**, không phải một định dạng JWT chuẩn được áp dụng phổ biến cho mọi hệ thống. Tránh tự hợp nhất quyền từ nhiều tenant thành một danh sách toàn cục rồi bỏ mất phạm vi.

### 10.2. API phải kiểm tra tài nguyên thật

Một yêu cầu:

~~~http
GET /tenants/company-b/invoices/INV-100 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Không có nghĩa rằng tenant được phép là **company-b** chỉ vì client đã gắn tên đó trong URL. API phải đối chiếu:

1. Tenant và quyền đã xác minh từ token/hệ thống phân quyền.
2. Tư cách thành viên hiện hành và loại hành động được phép.
3. Tenant mà hóa đơn **INV-100** thật sự thuộc về, lấy từ nguồn dữ liệu đáng tin cậy.

Điều này còn đúng khi scope, role và permission đều hiện diện và đúng kiểu. **Phân quyền ở mức đối tượng** là bước riêng, không được bỏ qua.

## 11. User token, application token và quyền được ủy quyền

Các claims cần thể hiện rõ **ai đang hành động** và **quyền từ đâu đến**.

### 11.1. Người dùng truy cập qua ứng dụng khách

Ví dụ ứng dụng **billing-portal** thay mặt **user-514** gọi billing API:

~~~text
Issuer: identity.example.test
Subject: user-514
Client: billing-portal
Audience: billing API
Scope: invoice:read
~~~

Token có thể đại diện cho một luồng ủy quyền có người dùng. API cần kiểm tra khả năng của **client/token** lẫn quyền của **người dùng** đối với tài nguyên. Việc client được cấp scope đọc không có nghĩa mọi người dùng của client đều được đọc mọi hóa đơn.

### 11.2. Tài khoản dịch vụ gọi API

Một ứng dụng nền có thể nhận token theo luồng **client credentials**. Tùy issuer và profile, chủ thể trong token có thể đại diện cho ứng dụng hoặc tài khoản dịch vụ, không có người dùng cuối.

~~~text
Principal type: service
Client: nightly-reporting
Scope: invoice:read
Business permission: report.generate
~~~

Nếu một endpoint yêu cầu người duyệt là **nhân viên được chỉ định**, token của tài khoản dịch vụ không tự động phù hợp chỉ vì có scope. Hợp đồng nên quy định rõ loại principal và các luồng được chấp nhận cho từng thao tác.

Khi có cơ chế **đại diện/ủy quyền thay mặt** (*on-behalf-of*, delegation), cần mô tả riêng danh tính chủ thể, tác nhân thực hiện và giới hạn quyền. Không tự suy rằng **client_id** là người dùng hoặc **sub** luôn là người dùng. Các chi tiết claim biểu diễn tác nhân phụ thuộc profile token và hợp đồng được lựa chọn.

## 12. Vấn đề quyền cũ, thu hồi và cache

Role hoặc permission được nhúng vào JWT thường phản ánh trạng thái **lúc token được phát hành**. Giả sử:

~~~text
09:00  Phát hành token có permissions = [invoice.approve]
09:10  Quản trị viên thu hồi quyền duyệt của người dùng
09:30  Token mới hết hạn
~~~

Nếu API chỉ kiểm tra permission từ JWT, người dùng có thể tiếp tục được duyệt trong khoảng sau 09:10 cho tới khi token không còn được chấp nhận. Đây là độ trễ quyền do thiết kế, cần được đánh giá theo độ nhạy cảm của hành động.

Các mô hình xử lý:

| Cách xử lý | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Token ngắn hạn | Hạn chế khoảng thời gian claims cũ tồn tại. | Không thu hồi tức thì. |
| Kiểm tra role/permission hiện hành ở backend | Phát hiện thay đổi quyền kịp thời theo nguồn dữ liệu. | Thêm độ trễ và phụ thuộc hệ thống quyền. |
| Danh sách thu hồi/token version/session version | Có thể chặn token hoặc phiên đã mất hiệu lực. | Cần cơ chế tra cứu và duy trì trạng thái chính xác. |
| Đánh giá chính sách qua dịch vụ chuyên biệt | Tập trung quy tắc phân quyền phức tạp. | Cần xử lý lỗi, độ trễ, cache và tính sẵn sàng. |
| Token tham chiếu và kiểm tra trạng thái tập trung | Có thể quản lý hiệu lực tập trung. | Thay đổi mô hình token và đường kiểm tra so với JWT tự xác minh. |

Một chính sách cân bằng có thể xem **scope** và **permissions** trong JWT là **trần quyền**: token cũ không được tự có quyền mới, còn quyền hiện hành có thể bị thu hẹp ngay. Nếu cache kết quả phân quyền, cache key cần có các yếu tố phù hợp như principal, tenant, hành động, tài nguyên và phiên bản quyền; thời gian cache và cơ chế invalidation phải phù hợp yêu cầu thu hồi. Không dùng một kết quả **ALLOW** của tài nguyên A cho tài nguyên B chỉ vì hai yêu cầu có cùng token.

Khi hệ thống phân quyền tạm thời không truy cập được, cách xử lý an toàn cho thao tác nhạy cảm là **không cấp quyền mới nếu thiếu bằng chứng cho phép**. Chính sách dự phòng phải được định nghĩa rõ thay vì ngầm cho phép.

## 13. Quản lý thay đổi hợp đồng theo phiên bản

Phạm vi quyền và ngữ nghĩa của chúng sẽ thay đổi theo sản phẩm. Các thay đổi có thể gây lỗi hoặc mở rộng quyền ngoài ý muốn:

- Đổi tên scope **invoice:read** thành **billing:invoice:read**.
- Tách permission **invoice.update** thành **invoice.update_draft** và **invoice.update_final**.
- Chuyển **roles** từ danh sách role toàn cục sang danh sách role theo tenant.
- Chuyển định dạng **scope** từ chuỗi sang mảng.
- Thay đổi ý nghĩa role **billing_editor** để thêm quyền phê duyệt.

### 13.1. Khi nào cần phiên bản mới?

Nếu cách diễn giải thay đổi về **kiểu, cấu trúc, quyền hoặc phạm vi áp dụng**, đây thường là thay đổi phá vỡ hợp đồng. Nên có phiên bản rõ ràng và giới hạn API chỉ chấp nhận những phiên bản nó hiểu.

Ví dụ nâng từ v1 lên v2:

~~~text
v1:
    scope = "invoice:update"
    permission = "invoice.update"

v2:
    scope = "invoice:update-draft invoice:update-final"
    permissions = ["invoice.update_draft", "invoice.update_final"]
~~~

Không âm thầm coi **invoice:update** của v1 là quyền cập nhật mọi loại hóa đơn trong v2. Nếu cần hỗ trợ hai phiên bản trong giai đoạn chuyển đổi, dùng **bảng ánh xạ có chủ đích**, giới hạn thời gian và kiểm thử hành vi của từng phiên bản.

### 13.2. Quy trình triển khai thay đổi an toàn

1. Xác định sự thay đổi về dữ liệu và ý nghĩa quyền; đánh giá các API/audience và issuer chịu ảnh hưởng.
2. Cập nhật tài liệu hợp đồng, ma trận role → permission, danh mục scope và điều kiện tài nguyên.
3. Triển khai khả năng **đọc an toàn** phiên bản mới ở API trước khi bắt đầu phát hành token theo phiên bản đó, nếu quy trình chuyển đổi yêu cầu.
4. Dùng dữ liệu thử nghiệm để kiểm tra cả quyền đúng và các trường hợp bị từ chối.
5. Phát hành token mới, quan sát lỗi bất tương thích và thu hẹp dần hỗ trợ phiên bản cũ.
6. Chấm dứt phiên bản cũ sau khi bảo đảm vòng đời token/cơ chế thu hồi và các phụ thuộc đã được xử lý.

Nếu API gặp **authz_contract_version** không hỗ trợ, không nên “thử đoán” bằng cách rơi về một hợp đồng chung có quyền rộng hơn.

## 14. Những lỗi thiết kế hợp đồng thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Gọi scope, role và permission là cùng một thứ | Quyền token bị nhầm với quyền nghiệp vụ hoặc phạm vi tài nguyên. | Định nghĩa ba lớp và quy tắc kết hợp tường minh. |
| Dùng role **admin** toàn cục | Role của một tenant/ứng dụng mở rộng sang nơi khác. | Gắn role với issuer, domain và tenant; ánh xạ theo chính sách. |
| API tự suy permission từ chuỗi scope bằng quy tắc ghép tên | Scope mới có thể vô tình sinh quyền mới. | Dùng bảng ánh xạ cho phép chính xác. |
| Gặp claim sai kiểu thì cố ép sang kiểu hợp lệ | Giá trị không đáng tin có thể được diễn giải thành quyền. | Validate schema, fail closed cho claim bắt buộc. |
| Chấp nhận đồng thời **scope** string và array mà không khai báo | Cùng một dữ liệu có nhiều cách hiểu, khó kiểm toán. | Khóa kiểu theo issuer, profile và phiên bản hợp đồng. |
| Hợp quyền từ **roles** và **permissions** mà không có quy tắc | Có thể cấp quyền quá mức nếu hai nguồn mâu thuẫn. | Xác định nguồn sự thật và quy tắc intersection/precedence. |
| Dựa hoàn toàn vào claim role cũ khi quyền cần thu hồi ngay | Người bị gỡ quyền tiếp tục thực hiện thao tác. | Giới hạn tuổi token, kiểm tra quyền hiện hành hoặc thu hồi. |
| Chỉ kiểm tra permission mà không kiểm tra tài nguyên | Người dùng truy cập hóa đơn của người/tổ chức khác. | Đánh giá tenant, chủ sở hữu và chính sách object-level. |
| Đọc claims trong token chưa xác minh | Client có thể chỉnh sửa payload để tự nhận quyền. | Xác minh token đầy đủ trước khi dùng claims. |
| Nhận token đúng chữ ký nhưng sai audience/loại token | Token được dùng ngoài mục đích cấp phát, ví dụ ID token dùng cho API. | Kiểm tra issuer, audience, profile, loại token và giới hạn thời gian. |
| Nhúng toàn bộ cấu trúc tổ chức và dữ liệu nhạy cảm vào token | Token to, dễ cũ và payload có thể bị đọc. | Tối thiểu hóa claims; lấy dữ liệu hiện hành khi cần. |
| Nâng phiên bản scope/role bằng cách giữ ngữ nghĩa mơ hồ | API cũ và mới cấp quyền khác nhau. | Versioning và migration có kiểm thử từ chối quyền. |

## 15. Kiểm thử hợp đồng và quyết định phân quyền

Bộ kiểm thử cần chứng minh cả **claim được hiểu đúng** lẫn **quyền trên tài nguyên được áp dụng đúng**.

### 15.1. Kiểm thử định dạng

~~~text
scope là chuỗi hợp lệ                     -> chấp nhận theo schema
scope là mảng khi hợp đồng yêu cầu chuỗi  -> từ chối
roles là chuỗi khi schema yêu cầu mảng    -> từ chối
permissions chứa phần tử boolean         -> từ chối
permission không nằm trong danh mục       -> không tự cấp quyền
contract_version không được hỗ trợ        -> từ chối
claim tenant_id bị thiếu cho tài nguyên tenant -> từ chối
~~~

### 15.2. Kiểm thử kết hợp quyền

~~~text
Đúng scope + đúng permission + quyền hiện hành + tài nguyên hợp lệ
    -> ALLOW

Đúng scope + thiếu permission
    -> DENY

Thiếu scope + có permission
    -> DENY

Đúng scope và permission + role hiện hành đã bị thu hồi
    -> DENY (trong hợp đồng có live permission check)

Đúng quyền + sai tenant
    -> DENY

Đúng quyền + tài nguyên thuộc người khác và chính sách không cho phép
    -> DENY

Đúng quyền + hóa đơn không ở trạng thái có thể duyệt
    -> DENY

Token sai issuer, audience, mục đích hoặc đã hết hạn
    -> từ chối token trước khi đánh giá claims phân quyền
~~~

### 15.3. Kiểm thử thay đổi và tương tác giữa dịch vụ

Kiểm thử thêm các trường hợp: token v1 trên API v2, hai issuer cùng tên role khác nghĩa, token được cấp cho API A gửi sang API B, token của tài khoản dịch vụ gọi endpoint chỉ dành cho người dùng, quyền đổi giữa lúc phát hành và lúc gọi API, cũng như thay đổi trạng thái tài nguyên trước khi thao tác ghi.

Đối với endpoint cập nhật dữ liệu, nên kiểm thử quyền **tại thời điểm thao tác thực sự được thực thi**, tránh tình huống kiểm tra quyền từ bản ghi cũ rồi dữ liệu/chính sách thay đổi trước khi ghi. Tùy mức độ nhạy cảm, có thể cần giao dịch, điều kiện cập nhật, khóa dữ liệu hoặc cơ chế kiểm tra lại phù hợp.

## 16. Checklist thiết kế cho đội phát hành token và đội xây dựng API

Trước khi đưa một contract vào sử dụng, các bên cần thống nhất:

1. **Mục đích token:** token là access token dành cho API nào; issuer, audience, profile và thuật toán được chấp nhận là gì?
2. **Định danh chủ thể:** ánh xạ **(iss, sub)** vào user/service nào; có cần phân biệt client và người dùng không?
3. **Scope:** danh mục, cách đặt tên, kiểu dữ liệu, cú pháp, ánh xạ sang hành động và quyền cấp tối đa.
4. **Role:** ai quản lý role, role gắn với tenant hay phạm vi nào, bảng role → permission được kiểm soát ở đâu?
5. **Permission:** tên thao tác, nguồn tính quyền, thời điểm tính, vai trò của claim permission nếu nó được phát hành.
6. **Nguồn sự thật:** claim nào là giới hạn tại thời điểm phát hành; quyền hiện hành cần lấy từ nguồn nào?
7. **Chính sách tài nguyên:** kiểm tra tenant, ownership, trạng thái, điều kiện theo thuộc tính và chính sách tách nhiệm vụ ra sao?
8. **Xử lý bất thường:** làm gì khi claim thiếu/sai kiểu, quyền xung đột, version không hỗ trợ, dữ liệu quyền tạm không khả dụng?
9. **Vòng đời:** thời hạn token, thu hồi, cache, phiên bản contract và lộ trình thay đổi quyền?
10. **Giám sát:** ghi audit gồm chủ thể, hành động, tài nguyên, kết quả và lý do ở mức cần thiết; tránh ghi nguyên access token hoặc dữ liệu nhạy cảm.

## 17. Tổng kết

**Scope**, **role** và **permission** có quan hệ nhưng giữ vai trò khác nhau:

- **Scope** là giới hạn khả năng mà **access token** được cấp để yêu cầu.
- **Role** nhóm trách nhiệm của **chủ thể** trong một phạm vi quản lý như tổ chức hoặc nghiệp vụ.
- **Permission** mô tả những **thao tác** ứng dụng cho phép và có thể được gán trực tiếp, suy ra từ role hoặc xác định bằng chính sách.

JWT chỉ là phương tiện mang những claims đã được xác minh theo một **hợp đồng**. Muốn phân quyền đúng, hệ thống phải quy định tên và kiểu claim, nguồn quyền, ánh xạ rõ ràng, audience, ngữ cảnh tenant, phiên bản, kiểm tra quyền hiện hành khi cần và điều kiện trên từng tài nguyên. Một access token có cả scope, role và permission vẫn **không tự tạo ra quyết định ALLOW** nếu chính sách tài nguyên chưa cho phép.

**Tài liệu tham khảo kỹ thuật:** RFC 7519 (JSON Web Token); RFC 8725 (JWT Best Current Practices); RFC 6749 (OAuth 2.0 Authorization Framework, bao gồm khái niệm scope); RFC 6750 (Bearer Token Usage); RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens). Các chuẩn mô tả token và giao thức; **hợp đồng quyền nghiệp vụ của từng ứng dụng vẫn phải được thiết kế và tài liệu hóa riêng**.
