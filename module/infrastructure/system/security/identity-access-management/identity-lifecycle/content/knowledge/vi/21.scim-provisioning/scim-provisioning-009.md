# SCIM error: chẩn đoán lỗi provisioning và bảo đảm quyền truy cập được cập nhật đúng

Một nhân viên mới đã đăng nhập thành công tại Identity Provider (**IdP**) nhưng không có tài khoản trong ứng dụng SaaS. Một nhân viên chuyển bộ phận vẫn giữ nhóm quyền cũ dù hệ thống IAM đã gửi lệnh cập nhật. Nghiêm trọng hơn, nhân viên đã nghỉ việc vẫn dùng được tài khoản ứng dụng vì tác vụ vô hiệu hóa qua **SCIM** bị lỗi. Cả ba tình huống đều có thể được ghi nhận là **SCIM error**, nhưng nguyên nhân, mức độ rủi ro và cách khắc phục khác nhau.

**SCIM (System for Cross-domain Identity Management)** là tập tiêu chuẩn giúp các hệ thống trao đổi dữ liệu cấp phát danh tính, chủ yếu là tài nguyên **User** và **Group**, qua HTTP/JSON. Khi có lỗi, điều quan trọng không chỉ là đọc mã HTTP: đội IAM cần biết **sự kiện JML nào kích hoạt thay đổi, bản ghi/tài khoản nào bị ảnh hưởng, nhà cung cấp đã áp dụng được đến đâu và quyền thực tế còn tồn dư hay không**.

Bài học thuộc chương **SCIM provisioning** trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, nghiên cứu quản lý vòng đời danh tính theo mô hình **Joiner–Mover–Leaver (JML)**: xác minh, tạo tài khoản, cấp quyền, rà soát và thu hồi khi thay đổi vai trò. Nội dung liên kết **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và kiểm soát truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt lỗi **giao thức SCIM**, lỗi **schema/mapping**, lỗi **xác thực connector**, lỗi **nghiệp vụ JML** và trạng thái **quyền ở ứng dụng đích**.
- Đọc phản hồi lỗi dạng SCIM theo **RFC 7643/7644**, hiểu mã HTTP, `scimType`, `detail` và những giới hạn do từng nhà cung cấp triển khai.
- Chẩn đoán lỗi tạo User, trùng định danh, PATCH thuộc tính, quan hệ manager, Group membership và vô hiệu hóa Leaver.
- Thiết kế retry, idempotency, đồng bộ theo phiên bản, đối soát và xử lý thất bại từng phần mà không vô tình mở lại quyền cũ.
- Xây dựng runbook an toàn, bằng chứng kiểm toán và chỉ số theo dõi sự cố provisioning.

## 1. SCIM provisioning nằm ở đâu trong IAM?

SCIM thường được sử dụng khi **một hệ thống điều phối danh tính muốn tạo, cập nhật, tra cứu hoặc vô hiệu hóa tài khoản ở hệ thống khác**.

- **SCIM client**: thành phần gửi yêu cầu provisioning, thường thuộc IdP, IGA hoặc connector.
- **SCIM service provider**: ứng dụng đích tiếp nhận và quản lý các tài nguyên SCIM.
- **User resource**: đại diện cho tài khoản/người dùng trong phạm vi provider.
- **Group resource**: tập thành viên/nhóm mà provider hỗ trợ.
- **Schema và capability**: mô tả thuộc tính, hành vi truy vấn, PATCH, filter và các khả năng tích hợp được hỗ trợ.

~~~mermaid
flowchart LR
    HR["HRIS / hợp đồng<br/>Joiner, Mover, Leaver"] --> IGA["IAM / IGA<br/>Identity mapping + policy"]
    IGA --> CLIENT["SCIM client / connector"]
    CLIENT -->|"HTTP + JSON"| PROVIDER["SCIM service provider<br/>Users / Groups"]
    IGA --> IDP["IdP<br/>Authentication + SSO"]
    IDP -->|"OIDC / SAML"| APP["Ứng dụng"]
    PROVIDER --> APP
    CLIENT --> AUD["Audit / retry / reconciliation"]
    PROVIDER --> AUD
    APP -->|"Xác minh quyền thực tế"| AUD
    AUD --> IGA
~~~

Sơ đồ là mô hình khái niệm; có nền tảng dùng chính IdP làm SCIM client và có nền tảng không tách riêng service provider khỏi ứng dụng. **SCIM là cơ chế provisioning, không phải giao thức xác thực tương tác như OIDC/SAML.**

### 1.1. Phân biệt các lớp thành công

| Lớp | Kết quả có thể quan sát | Điều chưa chứng minh |
| --- | --- | --- |
| **HRIS/IAM** | Hồ sơ Employee/Contractor có trạng thái mới và IAM đã tính entitlement mong đợi. | Ứng dụng đã nhận thay đổi. |
| **SCIM connector** | Một request đã được tạo hoặc gửi thành công. | Provider đã xử lý đúng tài nguyên. |
| **SCIM API** | HTTP response cho biết provider chấp nhận hoặc từ chối một thao tác. | Mọi bước phụ thuộc như cập nhật Group đã hoàn tất. |
| **Tài khoản ứng dụng** | Đọc lại cho thấy User/Group có giá trị mong đợi. | Mọi phiên hoặc token cũ đã mất hiệu lực. |
| **Authorization tại API** | Tài nguyên đích thực thi đúng RBAC/ABAC, quyền không còn hợp lệ bị từ chối. | Không có đường truy cập khác ngoài phạm vi kiểm tra. |

**SCIM request thành công là một phần của bằng chứng**, không phải kết luận cuối cùng rằng toàn bộ vòng đời danh tính đã hoàn tất.

## 2. Định dạng SCIM error theo chuẩn

Theo mô hình lỗi của **SCIM 2.0 (RFC 7644)**, service provider có thể trả về HTTP status lỗi cùng JSON có schema:

~~~text
urn:ietf:params:scim:api:messages:2.0:Error
~~~

Ví dụ khi tạo user nhưng giá trị định danh bị trùng:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:Error"
  ],
  "scimType": "uniqueness",
  "detail": "A user with the requested unique attribute already exists.",
  "status": "409"
}
~~~

Trong ví dụ:

| Trường | Ý nghĩa |
| --- | --- |
| **`schemas`** | Chỉ rõ đây là tài nguyên thông điệp lỗi SCIM. |
| **`status`** | Mã HTTP dưới dạng chuỗi trong SCIM Error resource, ví dụ `"409"`. |
| **`scimType`** | Loại lỗi SCIM chi tiết hơn, nếu provider cung cấp; ở đây là vi phạm tính duy nhất. |
| **`detail`** | Mô tả lỗi để hỗ trợ xử lý; giá trị mang tính giải thích, không phải giao diện máy bắt buộc. |

**Không phải mọi nhà cung cấp đều trả đủ `scimType` hoặc cùng một thông báo `detail`.** Có ứng dụng trả JSON theo định dạng riêng, cổng API trả HTML/plain text, hoặc lỗi mạng khiến không nhận được HTTP response. Bộ điều phối phải phân biệt **mã HTTP thực tế, kiểu phản hồi, body hợp lệ và trường hợp không có phản hồi**.

Không dựa vào so khớp nguyên văn `detail` để quyết định xóa hay tạo tài khoản. Thông báo có thể thay đổi theo bản phát hành và không nên chứa dữ liệu cá nhân hoặc credential.

## 3. Bảng tra cứu nhanh mã HTTP khi SCIM lỗi

| HTTP status | Ý nghĩa điển hình | Cách điều tra đầu tiên |
| --- | --- | --- |
| **400 Bad Request** | Request JSON, schema, attribute, filter hoặc PATCH không hợp lệ. | Kiểm Content-Type, cấu trúc payload, đường dẫn thuộc tính, `scimType`. |
| **401 Unauthorized** | Connector không được xác thực hoặc credential không còn được chấp nhận. | Kiểm bearer token/credential tại nguồn quản lý bí mật và cơ chế xác thực API. |
| **403 Forbidden** | Connector được nhận biết nhưng thiếu quyền hoặc bị policy chặn. | Kiểm scope, vai trò, tenant và quyền trên đối tượng đích. |
| **404 Not Found** | Endpoint hoặc resource ID không tồn tại/không nhìn thấy theo provider. | Phân biệt sai base URL với user/group đã xóa hoặc mapping ID cũ. |
| **409 Conflict** | Xung đột, thường do thuộc tính unique đã tồn tại. | Tìm theo khóa định danh đáng tin cậy, tránh tạo duplicate hoặc ghi đè nhầm người. |
| **412 Precondition Failed** | Điều kiện cập nhật như `If-Match` không còn đúng. | Đọc lại phiên bản/ETag hiện hành và tính lại thay đổi. |
| **413 Content Too Large** | Payload vượt giới hạn provider/gateway. | Đánh giá số lượng thuộc tính/thành viên và giới hạn yêu cầu. |
| **429 Too Many Requests** | Bị rate limit. | Tôn trọng `Retry-After` nếu có, backoff có jitter và điều phối hàng đợi. |
| **500/502/503/504** | Lỗi server, proxy hoặc timeout từ nhà cung cấp. | Kiểm trạng thái hệ thống và **đọc lại đích trước khi retry** vì request cũ có thể đã được áp dụng. |

Không phải mọi mã trên đều được trả bởi tất cả triển khai SCIM. Một provider có thể trả **400 hoặc 409** cho dạng xung đột khác nhau, hoặc **404** khi cố tình che sự tồn tại của tài nguyên. Cần dùng **hợp đồng API và khả năng SCIM của provider** để diễn giải cụ thể.

### 3.1. Những giá trị `scimType` cần nhận diện

| `scimType` | Tình huống khái niệm | Lớp cần kiểm |
| --- | --- | --- |
| **`invalidSyntax`** | Cấu trúc request không phù hợp. | JSON, filter/operation syntax và encoding. |
| **`invalidFilter`** | Biểu thức lọc SCIM không hợp lệ hoặc không được chấp nhận. | Cú pháp filter, phép toán, thuộc tính hỗ trợ tìm kiếm. |
| **`invalidPath`** | Đường dẫn thuộc tính của PATCH/filter không hợp lệ. | Schema, extension URI, đường dẫn thuộc tính. |
| **`invalidValue`** | Giá trị thuộc tính không đáp ứng quy tắc. | Kiểu dữ liệu, giá trị enum, cấu trúc phức hợp. |
| **`mutability`** | Cố sửa trường chỉ đọc hoặc bất biến. | Quy tắc `readOnly`, `immutable`, `writeOnly`. |
| **`uniqueness`** | Giá trị thuộc tính unique đã tồn tại. | ID mapping, tìm trùng và liên kết user. |
| **`noTarget`** | Một thao tác không tìm được thuộc tính/đối tượng đích cần xử lý trong ngữ cảnh PATCH. | Path filter và trạng thái resource hiện hành. |
| **`tooMany`** | Yêu cầu trả/nhắm tới quá nhiều giá trị cho ngữ cảnh hỗ trợ. | Filter, giới hạn cardinality và yêu cầu. |
| **`invalidVers`** | Vấn đề về phiên bản tài nguyên hoặc tham chiếu phiên bản theo định nghĩa SCIM. | ETag/meta.version và điều kiện cập nhật nếu provider sử dụng. |
| **`sensitive`** | Nội dung yêu cầu hoặc điều kiện liên quan dữ liệu nhạy cảm theo loại lỗi SCIM. | Quy tắc bảo vệ thuộc tính và cách provider diễn giải. |

Danh sách hỗ trợ đọc mã lỗi, **không phải cam kết một mã luôn đi với một HTTP status duy nhất**. Với lỗi phiên bản, thường cần xem rõ việc provider hỗ trợ cập nhật điều kiện bằng ETag và mã HTTP thực nhận.

## 4. Điểm phân tách quan trọng: request, mapping hay quyền thực tế?

Khi xuất hiện lỗi, cần xác định **hệ thống nào sở hữu vấn đề** thay vì quy lỗi ngay cho SCIM:

1. **Nguồn HRIS sai/thiếu:** không có Employee ID, ngày hiệu lực sai hoặc manager chưa được xác minh.
2. **IAM mapping sai:** ghép user theo email có thể thay đổi, không có bảng `subjectId → scimUserId`.
3. **Connector tạo request sai:** filter không đúng cú pháp, dùng `PUT` thay `PATCH` hoặc thiếu header.
4. **Connector thiếu quyền:** credential hết hạn, scope không đủ để sửa nhóm hoặc tắt User.
5. **Provider từ chối:** validation schema, uniqueness, endpoint không hỗ trợ hoặc resource không tồn tại.
6. **Đích áp dụng một phần:** tạo User xong nhưng không thêm được Group, sửa User xong nhưng phiên cũ còn.
7. **Ứng dụng áp dụng quyền khác:** local role, RBAC/ABAC, token cache hoặc override thủ công không còn khớp SCIM.

Đầu ra điều tra lý tưởng là một phát biểu có thể kiểm chứng, chẳng hạn: **“HRIS đã phát Leaver có hiệu lực; IAM gửi PATCH active=false tới đúng User ID; provider trả 429, chưa xác minh vô hiệu; ticket có owner và biện pháp hạn chế truy cập tạm thời.”**

## 5. Lỗi tạo User: trùng, sai định danh và thiếu thuộc tính

### 5.1. `409 uniqueness` không có nghĩa nên xóa user hiện tại

Ví dụ Joiner mới:

~~~http
POST /scim/v2/Users
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "userName": "an.nguyen@example.test",
  "active": true,
  "name": {
    "givenName": "An",
    "familyName": "Nguyen"
  }
}
~~~

Payload trên là ví dụ **không dùng credential thật**. Nếu provider trả 409, có nhiều khả năng:

- Người dùng đã được tạo từ một sự kiện trước hoặc thao tác thủ công.
- `userName`/email xung đột theo chính sách unique của provider.
- Connector dùng lại định danh được tái cấp cho một người khác.
- Request tạo trước đó đã thành công nhưng response bị mất, sau đó được retry.
- Dữ liệu tồn tại ở tenant/vùng khác hoặc tài khoản đã được đánh dấu xóa nhưng vẫn ràng buộc uniqueness.

**Cách khắc phục an toàn**:

1. Tra cứu tài nguyên có thể trùng theo những thuộc tính được phép, kiểm `externalId`, `id`, thuộc tính nguồn và bảng correlation.
2. Đối chiếu **Person/Engagement ID** với nguồn có thẩm quyền; không tự gộp chỉ vì cùng email.
3. Nếu đúng là **cùng một tài khoản đã tạo**, liên kết tới `scimUserId` hiện có, rồi thực hiện UPDATE theo trạng thái mong đợi.
4. Nếu là **người khác**, dừng tác vụ và xử lý xung đột/tái cấp tên đăng nhập qua quy trình phê duyệt.
5. Ghi chứng cứ quyết định linking; không xóa tài khoản chỉ để cho POST tiếp theo hết lỗi.

### 5.2. Phân biệt `id`, `externalId` và `userName`

| Thuộc tính | Vai trò |
| --- | --- |
| **`id`** | ID tài nguyên do SCIM service provider cấp; dùng cho đường dẫn tài nguyên, ví dụ `/Users/{id}`. |
| **`externalId`** | Giá trị do SCIM client quản lý nhằm hỗ trợ liên kết dữ liệu giữa các miền. |
| **`userName`** | Tên dùng để nhận diện người dùng trong provider theo schema; có ràng buộc uniqueness trong phạm vi provider. |
| **`subjectId` nội bộ** | ID canonical của IAM, không phải thuộc tính SCIM bắt buộc. |

Đối với RFC 7643, `id` là thuộc tính tài nguyên do service provider cấp; `externalId` hỗ trợ correlation từ client. **Không giả định chuỗi `externalId` sẽ được provider dùng làm khóa chính hoặc tìm kiếm** nếu chưa xác minh hợp đồng tích hợp.

### 5.3. Sai schema và thiếu trường

Một request có thể bị từ chối vì `userName` vắng mặt hoặc không hợp lệ, sai kiểu dữ liệu, giá trị bắt buộc theo schema mở rộng, hay không đáp ứng quy tắc riêng của ứng dụng. Cần kiểm:

- `/Schemas` để xem thuộc tính và extension mà provider công bố, nếu endpoint hỗ trợ/cho phép.
- `/ResourceTypes` để hiểu schema gắn với tài nguyên User/Group.
- `/ServiceProviderConfig` để biết các khả năng như PATCH, filtering, bulk và ETag theo công bố của provider.
- Hợp đồng riêng của nhà cung cấp: trường bắt buộc thêm, giới hạn username và hành vi cập nhật.

Các endpoint discovery là **khả năng theo chuẩn**, nhưng provider thực tế có thể hạn chế hoặc không triển khai đầy đủ. Không tự suy kết luận chỉ từ việc endpoint chưa truy vấn được.

## 6. Lỗi PATCH/PUT: đường dẫn, kiểu dữ liệu và thuộc tính không được sửa

### 6.1. PATCH dùng để thay đổi có chọn lọc

SCIM PATCH theo RFC 7644 có schema:

~~~text
urn:ietf:params:scim:api:messages:2.0:PatchOp
~~~

Ví dụ vô hiệu hóa một tài khoản User trong quy trình Leaver:

~~~http
PATCH /scim/v2/Users/scim-user-8802
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đây là request minh họa, **chỉ thực hiện trong hệ thống được ủy quyền**. `active` là thuộc tính SCIM User mô tả trạng thái tài khoản; **provider quyết định chính xác nó tác động thế nào tới đăng nhập, session và dữ liệu**.

Những lỗi thường gặp:

| Lỗi | Tình huống | Điều tra |
| --- | --- | --- |
| **`invalidPath`** | `path` sai tên thuộc tính hoặc extension URI. | Xem schema và quy tắc SCIM PATCH path. |
| **`invalidValue`** | Gửi `"false"` dạng chuỗi cho thuộc tính boolean hoặc giá trị không hợp lệ. | Kiểm JSON type và validation của provider. |
| **`mutability`** | Cố PATCH `id`, `meta` hoặc thuộc tính read-only. | Xem `mutability`, ngừng ghi vào trường không được sửa. |
| **`noTarget`** | Phép PATCH có filter/path cần đối tượng khớp nhưng không có. | Đọc lại tài nguyên và tính lại phép cập nhật. |
| **404** | User ID không còn tại đích hoặc URL sai. | Kiểm mapping và tenant trước khi tạo lại. |
| **412** | Dữ liệu đã đổi giữa lúc đọc và ghi. | Đọc ETag/version và tính lại delta. |

**Không nên khắc phục `invalidPath` bằng cách gửi lại cùng request nhiều lần**. Những lỗi xác định do request sai thường cần sửa schema/mapping, không phải retry mù quáng.

### 6.2. PUT không phải PATCH

`PUT` dùng để **thay thế biểu diễn tài nguyên** theo quy tắc SCIM/provider, có thể tác động tới các thuộc tính client không gửi hoặc không được phép thay đổi. `PATCH` diễn đạt các thay đổi chọn lọc. Khi người dùng Mover và chỉ cần đổi phòng ban/nhóm, cần hiểu rõ thao tác mong muốn và hành vi provider để tránh vô tình làm mất các trường không định sửa.

Đặc biệt phải xem cách xử lý **thuộc tính read-only, immutable, defaulted, multi-valued** và các extension. Không nên dùng `PUT` toàn bộ User từ một bản snapshot cũ để “sửa nhanh” lỗi PATCH.

## 7. SCIM Group error: trùng thành viên, sai User ID và lỗi phân quyền

Thêm hoặc thu hồi thành viên Group thường tác động trực tiếp tới **RBAC** của ứng dụng. Dữ liệu `members.value` trong SCIM Group thường tham chiếu **ID tài nguyên thành viên tại chính service provider**, không phải mặc nhiên là employeeNumber, email hay ID nội bộ của IAM.

### 7.1. Một thay đổi thành viên minh họa

~~~http
PATCH /scim/v2/Groups/scim-group-finance-readers
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "Add",
      "path": "members",
      "value": [
        {
          "value": "scim-user-8802"
        }
      ]
    }
  ]
}
~~~

Ví dụ chỉ minh họa cú pháp; provider có thể có ràng buộc riêng về thành viên, loại Group và quyền connector.

### 7.2. Các vấn đề thường gặp

| Tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| User chưa tồn tại nhưng connector thêm vào Group. | Sai tham chiếu, lỗi tạo membership. | Bảo đảm **User provisioned & verified** trước membership. |
| Connector dùng email thay SCIM User `id`. | Membership không được chấp nhận hoặc gắn sai người. | Map `subjectId → scimUserId` theo provider. |
| Hai worker cùng sửa Group. | Một cập nhật ghi đè cập nhật khác. | Điều phối, ETag nếu hỗ trợ, đọc lại và tính delta. |
| Group được quản lý thủ công tại ứng dụng. | SCIM thiếu quyền ghi hoặc provider từ chối. | Xác định quyền sở hữu Group và cơ chế đồng bộ cho phép. |
| Group membership được tính từ nested/dynamic groups. | Người dùng có quyền ngoài membership trực tiếp thấy trong SCIM. | Kiểm **effective entitlement** tại ứng dụng. |
| Chỉ thêm nhóm mới, không xóa nhóm cũ khi Mover. | Tích lũy quyền, tăng rủi ro truy cập dữ liệu trái vai trò. | So sánh **expected vs actual membership** và xử lý cả thu hồi. |

Một lần `PATCH Group` trả thành công **không bảo đảm toàn bộ quyền trong ứng dụng đổi ngay** nếu ứng dụng dùng cache, vai trò cục bộ hoặc token phiên cũ.

## 8. Manager và Enterprise User extension

Một số SCIM provider hỗ trợ **Enterprise User extension**:

~~~text
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User
~~~

Ví dụ nội dung thuộc tính manager trong biểu diễn User:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "scim-user-8802",
  "userName": "an.nguyen@example.test",
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "department": "FINANCE",
    "manager": {
      "value": "scim-user-2088",
      "displayName": "Binh Tran"
    }
  }
}
~~~

**`manager.value` là tham chiếu tới SCIM ID của manager trong provider đích**, không mặc định là ID HRIS hoặc subject ID nội bộ. Nếu manager chưa được provision vào SaaS hoặc provider không hỗ trợ extension, một request có thể lỗi dù hồ sơ HRIS đúng.

Giải pháp:

1. Xác minh manager là người hợp lệ tại **thời điểm có hiệu lực**.
2. Resolve đúng ID manager trong SCIM provider, không dùng displayName/email làm khóa.
3. Kiểm schema/extension được hỗ trợ và thứ tự cấp phát User nếu có phụ thuộc.
4. Nếu không thể cập nhật, tạo ngoại lệ có owner và xem các workflow phê duyệt đang phụ thuộc manager.
5. Xác minh tuyến phê duyệt/quyền xem dữ liệu cấp dưới sau cập nhật, không chỉ trường manager.

## 9. Lỗi xác thực và kết nối SCIM client

SCIM client thường dùng một cơ chế xác thực API (ví dụ OAuth bearer token hoặc credential do provider quản lý). Đây **không phải phiên SSO tương tác của người dùng cuối**.

### 9.1. 401 và 403 không giống nhau

- **401**: request không được xác thực theo cách provider chấp nhận; kiểm token hết hạn, cấu hình connector, audience/issuer nếu là OAuth token, header và thời gian.
- **403**: request có thể đã được xác thực nhưng chưa được phép làm thao tác, ví dụ connector chỉ được đọc User mà không sửa Group hoặc tắt tài khoản.
- **Timeout/TLS/DNS**: có thể không nhận được HTTP status; điều tra kết nối, hostname, chứng chỉ, proxy, outbound policy và tình trạng provider.

Không sửa lỗi bằng cách cấp quyền quản trị toàn tenant cho connector một cách mặc định, tắt kiểm chứng TLS hoặc in bearer token vào log. Cần dùng **quyền tối thiểu**, secret manager, rotation và quyền theo đúng tài nguyên cần provision.

### 9.2. Tenant và URL

Một credential SCIM có thể đúng nhưng đang trỏ tới **tenant khác** hoặc base URL sai. Điều này đặc biệt nguy hiểm: một request cập nhật nhầm tenant có thể ảnh hưởng người dùng không liên quan.

Mỗi cấu hình connector nên ràng buộc:

| Trường | Ý nghĩa |
| --- | --- |
| **connectorId / tenantId** | Phân biệt từng ứng dụng và miền dữ liệu. |
| **baseUrl** | Endpoint SCIM được phê duyệt, dùng HTTPS và hostname tin cậy. |
| **authCredentialRef** | Tham chiếu credential trong kho bí mật, không lưu raw token vào cấu hình công khai. |
| **allowedOperations** | Phạm vi Create/Update/Disable/Group management được phép. |
| **schemaMappingVersion** | Phiên bản ánh xạ thuộc tính đang áp dụng. |
| **owner, changeRef** | Chủ chịu trách nhiệm và bằng chứng đổi cấu hình. |
| **lastSuccessfulSync, lastVerifiedAt** | Thời điểm thành công/đối soát cuối, không chỉ lần gửi gần nhất. |

## 10. Lỗi do filtering, paging và discovery

SCIM sử dụng cú pháp filter riêng. Một filter sai có thể trả `400` với `invalidFilter` hoặc mã khác tùy provider.

Một yêu cầu tra cứu logic:

~~~text
GET /scim/v2/Users?filter=userName%20eq%20%22an.nguyen%40example.test%22
~~~

Đây là ví dụ **filter đã được URL-encode**, không phải cách xây query bằng nối chuỗi đầu vào tùy ý. Hãy sử dụng thư viện encoding và filter builder phù hợp để ngăn filter injection, tránh nhầm dấu ngoặc kép và khoảng trắng.

### 10.1. Filter trả 0 kết quả có nghĩa gì?

Không nhất thiết là User chưa tồn tại:

- Filter dùng trường provider không hỗ trợ tìm kiếm.
- Trường bị chuẩn hóa khác nhau, ví dụ chữ hoa/thường hoặc email đổi.
- Search bị giới hạn theo tenant, scope hoặc trạng thái tài khoản.
- Connector truy vấn dữ liệu replica/cached có độ trễ.
- Provider hỗ trợ lọc nhưng dữ liệu liên kết nằm trong extension không có khả năng filter.

Trước khi quyết định `POST /Users`, phải đối chiếu **ID nguồn, `externalId`, correlation store** và các cách tìm được provider cho phép. Tạo tài khoản mới dựa trên một lần filter rỗng có thể làm trùng người.

### 10.2. Phân trang

Với các API hỗ trợ phân trang theo SCIM, **ListResponse** chứa `totalResults`, `Resources`, `startIndex` và `itemsPerPage` trong ngữ cảnh phù hợp; `startIndex` theo chuẩn dùng chỉ số bắt đầu từ 1.

Nếu một lần GET chỉ lấy trang đầu mà connector coi là toàn bộ danh sách, nó có thể **bỏ sót người dùng hoặc nhóm** khi reconciliation. Cần phân trang theo giới hạn provider và tránh suy ra user đã bị xóa chỉ vì không xuất hiện trong một trang cụ thể.

## 11. Concurrency, ETag và sự kiện JML đến sai thứ tự

SCIM có cơ chế kiểm soát phiên bản như `meta.version` và HTTP ETag khi provider hỗ trợ. Điều này giúp tránh **lost update**: một worker ghi đè dữ liệu do worker khác vừa cập nhật.

Ví dụ:

~~~text
10:00  Client A đọc User version = v10
10:01  Client B cập nhật department; version = v11
10:02  Client A gửi thay đổi dựa trên v10
10:02  Provider từ chối điều kiện If-Match (nếu hỗ trợ)
10:03  Client A đọc v11, tính lại delta và gửi cập nhật đúng
~~~

Khi nhận **412 Precondition Failed**, không nên bỏ `If-Match` rồi ép ghi đè. Phải đọc lại trạng thái, kiểm nguồn thay đổi, tính delta và xác định liệu tác vụ vẫn còn hợp lệ.

### 11.1. Tránh sự kiện cũ khôi phục tài khoản Leaver

Giả sử sự kiện `MOVER` đến muộn sau khi `LEAVER` đã có hiệu lực. Nếu connector không kiểm thứ tự, nó có thể gửi `active=true` hoặc cập nhật vai trò cũ, khiến tài khoản đích được mở lại.

Một chiến lược phù hợp:

1. Ghi **source event ID, record version, effectiveAt** và loại quan hệ.
2. Phân biệt **bản ghi nguồn đã nhận** với **trạng thái kỳ vọng có hiệu lực hiện tại**.
3. Chống xử lý trùng theo event ID cùng khóa nghiệp vụ.
4. Trước khi gửi thao tác có tác động quyền, đọc lại trạng thái authoritative mới nhất.
5. Không cho retry cũ ghi đè kết quả Leaver/revocation mới hơn.
6. Khi xảy ra xung đột, chuyển vào hàng đợi xác minh hoặc tính lại trạng thái từ nguồn.

**Dựa riêng vào timestamp nhận sự kiện là không đủ**; sự kiện có thể bị trễ trong hàng đợi hoặc lịch hiệu lực bị thay đổi.

## 12. Retry an toàn, idempotency và phân loại lỗi

Một SCIM connector vận hành tốt **không retry mọi lỗi như nhau**.

| Nhóm lỗi | Có nên retry tự động? | Cách xử lý |
| --- | --- | --- |
| **400 schema/filter/PATCH sai** | Thường **không** cho tới khi sửa request. | Cô lập payload và mapping, mở case có owner. |
| **401 credential hết hạn** | Chỉ sau khi credential được cấp/rotate hợp lệ. | Không in secret; kiểm scope và config. |
| **403 policy thiếu quyền** | Không retry mù. | Yêu cầu owner kiểm phạm vi/role connector. |
| **404 User ID cũ** | Không tự tạo lại khi chưa xác minh. | Resolve ID, đối chiếu authoritative event. |
| **409 uniqueness** | Không lặp POST vô hạn. | Tìm và liên kết đúng bản ghi hoặc xử lý xung đột. |
| **412 version mismatch** | Có thể retry **sau khi đọc lại và tính delta**. | Dùng version mới, chống lost update. |
| **429 rate limit** | Có, nếu tác vụ vẫn hợp lệ. | Tôn trọng Retry-After; backoff + jitter. |
| **5xx/timeout** | Có điều kiện. | Đọc lại đích vì thao tác có thể đã thành công trước timeout. |

### 12.1. Idempotency của thao tác provisioning

**Idempotent** nghĩa là chạy lại cùng ý định không làm trạng thái cuối bị lệch hoặc tạo thêm tài khoản/nhóm không mong muốn. Giao thức HTTP có một số ngữ nghĩa theo phương thức, nhưng một workflow SCIM đầy đủ **không tự nhiên idempotent** khi còn thao tác tạo User, thay đổi nhóm hoặc các tích hợp ngoài luồng.

Ví dụ, `POST /Users` đã thành công nhưng client bị timeout. Nếu retry `POST` ngay, có thể nhận 409 hoặc tạo duplicate tùy provider. Cần **tra cứu/correlation** trước khi gửi lại, không coi timeout là chắc chắn thất bại.

Với Group, nên tính **membership mong đợi** và so sánh membership thực tế, thay vì cộng thêm cùng một thành viên theo từng event một cách không kiểm soát.

### 12.2. Backoff và thứ tự ưu tiên

Hàng đợi xử lý nên:

- Dùng retry có giới hạn, exponential backoff và jitter phù hợp.
- Tôn trọng header **`Retry-After`** nếu provider cung cấp và chính sách cho phép.
- Giới hạn song song theo tenant/provider để tránh gây quá tải.
- Không để các request Mover cũ vượt qua tác vụ Leaver cần thu hồi khẩn.
- Cảnh báo khi lỗi quá thời hạn, thiếu owner hoặc nhiều lần retry không đổi kết quả.
- Có **dead-letter queue** hoặc cơ chế quản trị ngoại lệ với khả năng khôi phục theo trạng thái nguồn hiện tại.

Nếu thời hạn thu hồi truy cập của Leaver bị đe dọa do 429/5xx, cần áp dụng biện pháp hạn chế khác theo chính sách (chặn tại IdP, policy ứng dụng/API, cắt credential) và **không kết luận Leaver đã hoàn tất** khi SCIM chưa được xác minh.

## 13. SCIM error trong Joiner–Mover–Leaver

### 13.1. Joiner: tạo tài khoản nhưng không tạo quyền sai

**Tình huống:** ngày bắt đầu của An là 01/12; HRIS đã xác minh danh tính, IAM cần tạo user SaaS trước giờ làm việc. Provider trả 409 vì một local user dùng email tương tự đã tồn tại.

Điều cần làm:

1. Giữ thông tin **Person ID và Engagement ID** từ nguồn có thẩm quyền.
2. Xác minh tài khoản có sẵn có thuộc **đúng An** không; tránh lấy email làm khóa duy nhất.
3. Nếu cùng người, liên kết account và cập nhật đúng trạng thái/role; nếu người khác, mở case trùng định danh.
4. Không mặc định bật `active=true` trước Start date hoặc cấp admin để “chữa lỗi”.
5. Đối soát user, group và khả năng đăng nhập đúng thời điểm hiệu lực.

Một lỗi SCIM Joiner có thể làm nhân viên chưa sẵn sàng, nhưng **chữa bằng gộp sai tài khoản có thể gây lộ dữ liệu người khác**.

### 13.2. Mover: cập nhật quyền mới và thu hồi quyền cũ

**Tình huống:** Bình chuyển từ Sales sang Finance. IAM gửi cập nhật `department` thành công nhưng PATCH Group bị 403. Nếu connector chỉ ghi “user updated”, Bình có thể vẫn có Sales access và thiếu Finance access.

Luồng đúng:

1. Tính **expected entitlements** theo role/ABAC và ngày Mover có hiệu lực.
2. So sánh thành viên Group, quyền ứng dụng và mọi assignment trực tiếp.
3. Điều tra 403 tại Group API: connector có quyền quản trị membership không?
4. Khi quyền được sửa, áp dụng cả **thêm Finance** và **bỏ Sales** theo chính sách.
5. Đọc lại Group và quyền thực tế; xem token/phiên còn chứa claim cũ.
6. Đóng task chỉ khi chênh lệch thuộc phạm vi được xử lý hoặc còn ngoại lệ được phê duyệt.

Lỗi chỉ ở group membership vẫn có thể tạo ra **privilege creep**; không được coi là sự cố giao diện đơn thuần.

### 13.3. Leaver: một lỗi SCIM có thể là sự cố an ninh

**Tình huống:** Lan nghỉ lúc 17:00, IdP đã khóa đăng nhập mới. SCIM connector gửi `active=false` tới SaaS nhưng bị 503.

Các bước ưu tiên:

1. Xác minh `subjectId`, tài khoản SaaS và thời điểm Leaver từ HRIS.
2. Ghi rõ SCIM action chưa được xác minh; không đánh dấu deprovision thành công.
3. Đánh giá SaaS có **local password, phiên, API key, PAT, refresh token** hay không.
4. Dùng cơ chế quản trị dự phòng đã được ủy quyền nếu cần chặn truy cập khẩn cấp.
5. Retry có kiểm soát hoặc xử lý thủ công, tránh mở lại tài khoản bằng sự kiện cũ.
6. Đọc lại tài khoản và xác minh các đường truy cập thực tế; giữ bằng chứng và phạm vi chưa kiểm chứng.

**Vô hiệu hóa SCIM User là một biện pháp**, không phải bằng chứng mặc nhiên về việc phiên/token/API credential đã ngừng hoạt động. Nếu ứng dụng không hỗ trợ thu hồi các vật mang quyền đã phát hành, phải ghi nhận cửa sổ truy cập tồn dư và biện pháp giảm thiểu.

### 13.4. Rehire và chuyển Contractor sang Employee

Khi một người quay lại làm việc, **Person** có thể trùng lịch sử nhưng **Engagement** mới cần được xác minh. Không sử dụng một `POST` hoặc `PATCH active=true` chỉ dựa vào email để phục hồi mọi quyền cũ. Cần xác nhận mapping đúng người, cấp credential mới theo chính sách và tính lại RBAC/ABAC từ quan hệ hiện hành.

## 14. Phân biệt SCIM error với lỗi SSO/OIDC/SAML

Một nhân viên có thể thấy “SSO failed” vì **SCIM chưa tạo local user**, dù IdP đã xác thực thành công. Ngược lại, SCIM có thể cập nhật user thành công nhưng **SSO bị lỗi trust hoặc token validation**.

| Quan sát | Lớp lỗi cần ưu tiên |
| --- | --- |
| **IdP không xác thực được user/MFA** | Authentication và chính sách IdP. |
| **OIDC issuer/audience/nonce/state không hợp lệ** | Federation/OIDC client validation. |
| **SAML chữ ký/ACS/audience sai** | Federation/SAML trust và SP validation. |
| **IdP success nhưng SaaS không có user** | SCIM/JIT provisioning và account mapping. |
| **SSO success nhưng 403 ở ứng dụng** | RBAC/ABAC, Group membership, resource scope hoặc trạng thái account. |
| **SCIM 200/204 nhưng local session vẫn truy cập được sau Leaver** | Deprovisioning/session/token thực tế tại app. |
| **Job backend nhận `invalid_client`** | OAuth client credential hoặc workload identity; không mặc nhiên lỗi SSO người dùng. |

**Đừng sửa lỗi SCIM bằng cách tắt MFA hoặc bỏ validation SAML/OIDC.** Hai lớp phục vụ mục tiêu khác nhau và phải được quản trị độc lập.

## 15. Runbook chẩn đoán SCIM error theo thứ tự an toàn

### Bước 1. Xác định đối tượng và mức rủi ro

Ghi lại `eventId`, `subjectId`, `engagementId`, tenant, ứng dụng, user/group đích, loại sự kiện JML và **effectiveAt**. Nếu là Leaver hoặc quyền đặc quyền, ưu tiên xử lý truy cập tồn dư.

### Bước 2. Kiểm request và response

Thu thập **HTTP method, resource path, status, SCIM error schema, scimType, requestId, thời gian, content type**. Che bearer token, dữ liệu nhân sự nhạy cảm và giá trị credential. Phân biệt HTTP response thật với lỗi mạng không có response.

### Bước 3. Xác định trạng thái nguồn

Đối chiếu HRIS/IGA: account đang phải ACTIVE hay DISABLED? Manager hoặc department nào đang có hiệu lực? Quyền nào cần cấp hoặc thu hồi? Không sử dụng snapshot cũ làm nguồn quyết định.

### Bước 4. Kiểm tenant, xác thực và capability

Xác minh base URL, credential reference, quyền connector, schema và khả năng PATCH/filter/ETag, theo hợp đồng provider. Không thử sửa bằng token admin hoặc bỏ TLS.

### Bước 5. Resolve đúng resource ID

Kiểm `subjectId → scimUserId` và `groupId` trong đúng tenant. Khi 404/409, đối chiếu với provider bằng truy vấn được phép; tránh tự tạo/xóa user dựa email.

### Bước 6. Phân loại lỗi có thể sửa bằng retry không

- **Permanent/semantic**: request sai schema, filter không hợp lệ, thiếu quyền, uniqueness chưa xác minh → sửa mapping/quyền/định danh.
- **Transient**: rate limit, 5xx, timeout, replica chưa hội tụ → retry có điều kiện, đọc lại trạng thái trước.
- **Concurrency**: ETag/If-Match xung đột → đọc version mới và tính lại delta.
- **Unknown/partial**: phản hồi mất, lệnh đã được áp dụng một phần → reconcile từng tài nguyên.

### Bước 7. Kiểm kết quả tại provider và ứng dụng

Đọc lại User, Group, thuộc tính, status, membership và **quyền thực tế** của ứng dụng. Kiểm ứng dụng có session/token hoặc local privilege độc lập không. Không đánh dấu VERIFIED chỉ vì connector đã gửi lệnh thành công.

### Bước 8. Khép lỗi và lưu bằng chứng

Ghi nguyên nhân, tác vụ sửa, policy/version, trạng thái từng đích, người chịu trách nhiệm, thời hạn và rủi ro còn mở. Nếu chưa thể xác minh Leaver, giữ case ở trạng thái ngoại lệ, không đóng im lặng.

~~~mermaid
flowchart TD
    A["Cảnh báo lỗi SCIM / JML drift"] --> B["Xác định subject, tenant,<br/>event và quyền ảnh hưởng"]
    B --> C["Phân loại HTTP / SCIM Error<br/>và trạng thái nguồn"]
    C --> D{"Lỗi semantic<br/>hay transient?"}
    D -->|"Semantic"| E["Sửa schema/mapping/permission<br/>và kiểm định danh"]
    D -->|"Transient"| F["Đọc lại provider<br/>retry có giới hạn"]
    E --> G["Đối soát User/Group<br/>và quyền thực tế"]
    F --> G
    G --> H{"Trạng thái đã đúng?"}
    H -->|"Chưa"| I["Exception có owner,<br/>hạn xử lý và biện pháp giảm thiểu"]
    I --> G
    H -->|"Đúng"| J["Audit + verified<br/>đóng tác vụ"]
~~~

## 16. Thiết kế orchestrator chịu lỗi

Một luồng xử lý khái niệm:

~~~text
onTrustedLifecycleEvent(event):
    verifyTrustedSourceAndSchema(event)
    if alreadyProcessed(event.eventId):
        return

    subject = resolveSubjectAndEngagement(event)
    if subject is ambiguous:
        quarantineAndRequestIdentityVerification(event)
        return

    current = loadAuthoritativeEffectiveState(subject)
    if eventIsStaleOrSuperseded(event, current):
        recordIgnoredEvent(event)
        return

    expected = evaluateExpectedAccountsAndEntitlements(current)
    for target in registeredScimTargets(subject):
        enqueueReconciliation(subject, target, expected, event)

reconcileTarget(subject, target, expected, event):
    actual = safelyReadProviderState(target, subject)
    if actual is unknown:
        retryOrOpenException(target, event)
        return

    changes = calculateMinimalSafeDelta(expected, actual)
    result = applyAuthorizedChangesWithConcurrencyControl(changes)

    if result is uniquenessConflict:
        verifyExistingResourceIdentityBeforeLinking()
    else if result is versionConflict:
        reloadAndRecalculateDelta()
    else if result is transientOrUnknown:
        verifyActualStateBeforeRetry()
    else if result is schemaOrPermissionError:
        quarantineAndAlertOwner()

    final = safelyReadProviderState(target, subject)
    verifyAccountGroupsAndEffectivePermissions(expected, final)
    if not verified:
        openTrackedExceptionWithMitigations()
    recordAuditWithNoRawCredentials()
~~~

Giả mã **không phải triển khai runnable** và không mô tả tất cả thao tác bất đồng bộ. Hệ thống thật cần kiểm soát concurrency, retry budget, vòng đời secret, nguồn event, thời gian hiệu lực, quyền connector, giới hạn provider và việc một số tác vụ SCIM không hỗ trợ transaction nguyên tử.

### 16.1. Trạng thái theo từng mục tiêu

| Trạng thái đề xuất | Ý nghĩa |
| --- | --- |
| **`DISCOVERED`** | Sự kiện/đích cần xử lý đã được xác định. |
| **`VALIDATED`** | Identity mapping, schema và quyền thao tác đã được kiểm tra. |
| **`QUEUED`** | Chờ tới thời điểm hiệu lực hoặc vào hàng đợi xử lý. |
| **`SENT`** | Request đã gửi, chưa xác nhận trạng thái cuối. |
| **`ACKNOWLEDGED`** | Provider đã phản hồi; chưa chắc quyền thực tế đã đúng. |
| **`RECONCILING`** | Đang đọc lại User/Group/entitlement để xác minh. |
| **`VERIFIED`** | Các trạng thái thuộc phạm vi đã khớp và bằng chứng đủ tin cậy. |
| **`FAILED` / `UNKNOWN`** | Không thực hiện được hoặc không xác định kết quả. |
| **`EXCEPTION_TRACKED`** | Chưa đúng nhưng đã có owner, giảm thiểu và hạn xử lý. |

Trạng thái là mô hình vận hành gợi ý, không phải state machine quy định trong RFC SCIM. Với **Leaver**, cần phân biệt `SCIM_VERIFIED` và `ACCESS_REVOKED_VERIFIED` nếu kiểm tra session/token ngoài SCIM còn là yêu cầu bắt buộc.

## 17. Bảo mật và kiểm toán khi có SCIM error

Một connector SCIM thường có quyền thay đổi tài khoản và nhóm ở hàng loạt ứng dụng, nên bản thân nó là **thành phần đặc quyền**.

### 17.1. Không làm lộ bí mật khi debug

Tránh ghi vào log/ticket:

- Raw `Authorization: Bearer ...`, refresh token, client secret, API key, password.
- Nội dung đầy đủ của hồ sơ nhân sự không liên quan tới sự cố.
- URL có token trong query string hoặc bản request/response không được che trường nhạy cảm.
- Credential của service account hoặc khóa SSH/certificate private key.

Nên ghi **credential reference ID, connector ID, tenant, requestId, HTTP status, scimType, operation, resource ID, policy version và kết quả**. Nhật ký phải có quyền đọc hạn chế, thời hạn lưu, bảo vệ toàn vẹn và cơ chế kiểm soát xuất dữ liệu.

### 17.2. Bằng chứng cần thiết

| Trường | Giúp trả lời |
| --- | --- |
| **`traceId`, `eventId`** | Tác vụ SCIM bắt nguồn từ sự kiện IAM/JML nào? |
| **`subjectId`, `engagementId`** | Ai bị tác động, trong giai đoạn làm việc nào? |
| **`sourceSystem`, `sourceVersion`, `effectiveAt`** | Dữ liệu nào có thẩm quyền và có hiệu lực lúc nào? |
| **`connectorId`, `targetTenant`, `resourceId`** | Provider và User/Group đích nào? |
| **`operation`, `httpStatus`, `scimType`** | Thao tác nào bị lỗi và kiểu lỗi? |
| **`mappingVersion`, `policyVersion`** | Quy tắc ánh xạ/cấp quyền nào được áp dụng? |
| **`attemptCount`, `nextRetryAt`** | Lỗi đang được retry ra sao? |
| **`expectedState`, `verifiedState`** | Trạng thái mong đợi đã được xác minh chưa? |
| **`owner`, `exceptionId`, `evidenceRef`** | Ai chịu trách nhiệm và chứng cứ đóng lỗi ở đâu? |

Ví dụ log **đã loại bỏ bí mật**:

~~~json
{
  "eventType": "SCIM_PROVISIONING_ERROR",
  "traceId": "leaver-person-1042-20261130",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "sourceEventId": "hr-leaver-912",
  "connectorId": "finance-saas-scim",
  "targetTenant": "enterprise-primary",
  "resourceType": "User",
  "resourceId": "scim-user-8802",
  "operation": "PATCH_ACTIVE_FALSE",
  "httpStatus": 429,
  "scimType": null,
  "reconciliationState": "NOT_VERIFIED",
  "risk": "POSSIBLE_RESIDUAL_ACCESS",
  "exceptionId": "IGA-EX-741",
  "ownerTeam": "identity-operations",
  "occurredAt": "2026-11-30T10:01:00Z"
}
~~~

Đây là **schema nội bộ minh họa**, không phải SCIM Error response chuẩn. Phân biệt bản ghi lỗi của orchestrator với phản hồi do service provider gửi.

## 18. Tình huống tổng hợp: lỗi SCIM trong ngày Mover và Leaver

**Bối cảnh:** tổ chức sử dụng HRIS, IGA, IdP SSO và một SaaS quản lý dự án có SCIM User/Group.

### 18.1. Mover

Ngày 01/12, An chuyển từ nhóm Sales sang Finance.

| Sự kiện | Lỗi/kết quả | Điều cần làm |
| --- | --- | --- |
| HRIS xác nhận Mover lúc 08:00. | IAM đã có quyền mới mong đợi. | Lưu effectiveAt, source version. |
| SCIM PATCH `department` thành công. | Thuộc tính User được cập nhật. | Chưa kết luận membership đúng. |
| SCIM PATCH Group trả 403. | Connector không được phép chỉnh nhóm. | Xác minh scope/owner Group; xử lý phê duyệt đúng, không dùng admin toàn quyền tùy tiện. |
| SaaS vẫn cho An truy cập dữ liệu Sales. | Quyền cũ còn tồn dư. | Giảm quyền theo policy, khắc phục membership, đối soát API và phiên. |
| Sau sửa scope, Group update thành công. | SaaS báo trạng thái mới. | Đọc lại membership và quyền thực tế, xác nhận không còn Sales. |

### 18.2. Leaver

Ngày 15/12, An nghỉ việc lúc 17:00.

| Sự kiện | Lỗi/kết quả | Điều cần làm |
| --- | --- | --- |
| HRIS phát Leaver. | IGA điều phối thu hồi. | Kiểm đúng subject/engagement, thời điểm. |
| IdP khóa đăng nhập mới. | SSO không phát phiên mới. | Cần tiếp tục xử lý app local session và token. |
| SCIM PATCH `active=false` timeout. | Không rõ provider đã áp dụng chưa. | Đọc lại User theo ID hiện hành trước khi retry. |
| Provider trả `active=false` sau kiểm tra. | SCIM account state đã đúng. | Xác minh local account/session/API access theo chính sách. |
| Một PAT vẫn dùng được ở API ngoài SCIM. | Quyền truy cập tồn dư. | Thu hồi PAT tại issuer; điều tra hoạt động và cải thiện inventory. |

**Bài học:** SCIM error cần được đánh giá **theo tác động truy cập**, không chỉ số lỗi API. Một lệnh sửa thuộc tính có thể thành công nhưng quyền cũ chưa mất; ngược lại, một timeout có thể xảy ra sau khi provider đã thực hiện thay đổi.

## 19. Chỉ số vận hành và phát hiện chênh lệch

| Chỉ số | Cách đo gợi ý | Rủi ro được phát hiện |
| --- | --- | --- |
| **Tỷ lệ thao tác SCIM đã xác minh** | User/Group operations có trạng thái đích khớp ÷ số operation phải xử lý. | Chỉ gửi request nhưng chưa chắc áp dụng. |
| **Lỗi SCIM theo HTTP và `scimType`** | Phân nhóm 400/401/403/404/409/412/429/5xx. | Nhìn ra mapping, auth, rate limit hay provider outage. |
| **Độ trễ provisioning Joiner** | EffectiveAt → User/Group đúng tại SaaS. | Nhân viên thiếu khả năng truy cập đúng hạn. |
| **Độ trễ đồng bộ Mover** | EffectiveAt → trạng thái thuộc tính + quyền mới/cũ đúng. | Privilege creep hoặc thiếu quyền. |
| **Độ trễ thu hồi Leaver** | EffectiveAt → account và entitlement được xác minh vô hiệu. | Cửa sổ truy cập tồn dư. |
| **Số tài khoản trùng hoặc mapping mơ hồ** | User không đối chiếu chắc chắn với nguồn có thẩm quyền. | Gắn nhầm người hoặc cấp quyền sai. |
| **Tỷ lệ retry thành công sau reconciliation** | Retry giải quyết được trạng thái mà không tạo duplicate/lost update. | Chất lượng cơ chế idempotency. |
| **Số ngoại lệ quá hạn** | Tác vụ chưa verified, thiếu owner hoặc vượt thời hạn. | Nợ an ninh tích lũy. |
| **Bao phủ provider** | SaaS bắt buộc có SCIM/API và cơ chế verify ÷ tổng SaaS thuộc phạm vi. | “Thành công” trong báo cáo khi còn app chưa tích hợp. |
| **Tỷ lệ drift sau đồng bộ** | Chênh lệch expected vs actual entitlements phát hiện ở kỳ đối soát. | Chỉnh sửa thủ công, cache hoặc đồng bộ thiếu. |
| **Tỷ lệ sự kiện có audit trail** | JML event → SCIM request → provider result → verification. | Không giải trình được quyết định truy cập. |

Mục tiêu và ngưỡng cần phù hợp từng provider, mức nhạy cảm và SLA. Một tỷ lệ HTTP success cao **không thay thế** chỉ số trạng thái quyền đã đối soát.

## 20. Những sai lầm thường gặp

1. **Retry liên tục khi 409 uniqueness** mà không kiểm đúng user hiện có.
2. **Tự tạo tài khoản mới sau một lần GET filter rỗng**, bỏ qua vấn đề paging, tenant và correlation.
3. **Dùng email, DN hoặc HR employee number làm SCIM `id`**, dù provider có ID tài nguyên riêng.
4. **Gửi PATCH sai schema/extension** và cho rằng mọi vendor đều hỗ trợ Enterprise User manager.
5. **Xóa toàn bộ Group membership** để xử lý lỗi của một user mà chưa tính quyền của những người khác.
6. **Tắt TLS verification hoặc cấp admin toàn quyền** chỉ để kết nối SCIM không trả 401/403.
7. **Bỏ điều kiện ETag/If-Match** khi gặp 412, làm mất cập nhật từ tác vụ khác.
8. **Nhận timeout và retry POST ngay**, tạo duplicate hoặc xung đột tài khoản.
9. **Đánh dấu Leaver hoàn tất từ HTTP 200** mà chưa kiểm trạng thái account, session, API key và quyền đích.
10. **Chỉ cấp quyền mới trong Mover** mà quên thu hồi role/Group cũ.
11. **Cho retry sự kiện Joiner/Mover cũ chạy sau Leaver**, có thể mở lại quyền đã thu hồi.
12. **Lưu bearer token, response chứa PII hoặc raw secret trong log** khi điều tra.
13. **Chỉ giám sát SCIM**, bỏ qua ứng dụng không hỗ trợ SCIM hoặc tài khoản service/workload ngoài phạm vi.

## 21. Checklist chẩn đoán và thiết kế SCIM error

1. Đã xác định **SCIM client, service provider, tenant, resourceType, User/Group ID và owner** chưa?
2. Request có đúng **HTTP method, endpoint, Content-Type, schema, PATCH Operations và kiểu dữ liệu** không?
3. Khi lỗi, đã ghi **HTTP status, SCIM Error schema, `scimType`, `detail` đã che và requestId** chưa?
4. Có phân biệt 401/403 với lỗi TLS, timeout hoặc provider outage không?
5. `id`, `externalId`, `userName` và `subjectId` có được ánh xạ đúng, không ghép chỉ bằng email không?
6. Trước khi xử lý 404/409, đã **tra cứu và xác minh đúng người/engagement** chưa?
7. PATCH có kiểm schema, mutability, extension và `active` boolean; PUT có được dùng đúng ngữ nghĩa không?
8. Group membership có dùng **SCIM User ID tại provider**, xử lý đúng thứ tự tạo User và thu hồi nhóm cũ không?
9. Enterprise User manager có resolve tới **ID manager tại provider đích** và kiểm workflow liên quan không?
10. Có kiểm `/ServiceProviderConfig`, `/ResourceTypes`, `/Schemas` và hành vi thực tế của nhà cung cấp khi cần không?
11. Có xử lý ETag/If-Match, 412, stale events và concurrency bằng **đọc lại/tính delta** không?
12. Retry có phân biệt lỗi **semantic, transient, timeout unknown**, tôn trọng Retry-After và chống duplicate không?
13. **Joiner** có account đúng người/đúng ngày, **Mover** có thêm quyền mới và bỏ quyền cũ, **Leaver** có chặn các đường truy cập còn hoạt động không?
14. Có phân biệt **SCIM provisioning** với **IdP authentication, SSO federation, RBAC/ABAC và API token/session** không?
15. Sau khi provider phản hồi thành công, có **đối soát trạng thái User, Group, role và quyền thực tế** không?
16. Các ngoại lệ chưa verified có **owner, hạn xử lý, biện pháp giảm thiểu, cảnh báo và audit trail** không?
17. Log và ticket có che credential/PII, có thể truy từ HRIS event đến kết quả ứng dụng và không chứa raw secret không?

**Ghi nhớ:** **SCIM error không chỉ là lỗi HTTP; đó là dấu hiệu một thay đổi danh tính hoặc quyền có thể chưa tới được hệ thống đích đúng cách.** Muốn xử lý an toàn, phải hiểu **mã HTTP và SCIM Error**, xác minh **đúng user/group và schema**, phân biệt lỗi cần sửa với lỗi có thể retry, bảo vệ thứ tự sự kiện **Joiner–Mover–Leaver** và đối soát **quyền thực tế**. Chỉ khi ứng dụng đã phản ánh đúng account, thuộc tính, nhóm và trạng thái truy cập – hoặc mọi ngoại lệ được theo dõi rõ ràng – IAM mới có cơ sở kết luận đã kiểm soát được provisioning và giảm quyền truy cập tồn dư.
