# Thao tác trên quan hệ như thành viên, quyền hoặc mặt hàng

## 1. Bài toán: quan hệ giữa hai tài nguyên cũng có hành vi nghiệp vụ

Trong REST API, thao tác không chỉ là tạo, xem, sửa hoặc xóa một đối tượng độc lập. Nhiều nghiệp vụ thực chất thao tác trên **mối quan hệ** giữa các đối tượng:

- Thêm một người dùng vào nhóm, đổi vai trò thành viên, tạm khóa hoặc rời nhóm.
- Gán vai trò cho người dùng trong một dự án; thu hồi quyền truy cập một tài liệu.
- Thêm sản phẩm vào giỏ hàng hoặc đơn hàng, sửa số lượng, xóa mặt hàng.
- Gắn nhãn vào bài viết hoặc liên kết tài liệu với một thư mục.

Ví dụ, với nhóm **team-42** và người dùng **user-7**, việc người dùng có tồn tại không trả lời được họ có phải thành viên nhóm hay không. **Membership** (tư cách thành viên) mang thông tin riêng: thời điểm gia nhập, vai trò trong nhóm, trạng thái, ai đã mời và phiên bản thay đổi. Tương tự, một **order item** có số lượng và đơn giá được chốt tại một thời điểm; nó không đồng nhất với bản ghi **product** trong danh mục.

Bài học thuộc chương **Thao tác tài nguyên** của module **INTEGRATION_API_REST**, tập trung thiết kế REST API dựa trên **resource, URI, HTTP method và status code**, có hợp đồng dữ liệu rõ ràng. Chúng ta sẽ kết hợp **idempotency, phân trang, cache, OpenAPI, xác thực, phân quyền, lỗi và kiểm thử** với ví dụ **Java/Spring**, đồng thời chỉ ra các lựa chọn và đánh đổi trong thực tế.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **tài nguyên gốc**, **quan hệ** và **bản ghi gắn quan hệ** (*association resource*).
2. Chọn URI hợp lý cho thành viên nhóm, gán vai trò và mặt hàng trong đơn hàng.
3. Xác định khi nào nên dùng GET/POST/PUT/PATCH/DELETE cùng 200/201/204/404/409/412/422.
4. Bảo vệ thao tác quan hệ bằng kiểm tra quyền theo **đối tượng cha, tenant và hành động**.
5. Giữ đúng dữ liệu khi hai client cùng sửa, khi gửi lại request hoặc khi transaction thất bại.
6. Viết mô tả OpenAPI và kiểm thử hành vi bằng Spring Boot.

## 2. Mô hình hóa quan hệ: không phải mọi liên kết đều giống nhau

Giả sử có các thực thể:

~~~mermaid
erDiagram
    USER ||--o{ MEMBERSHIP : "tham gia"
    TEAM ||--o{ MEMBERSHIP : "có"
    USER ||--o{ ROLE_ASSIGNMENT : "nhận"
    PROJECT ||--o{ ROLE_ASSIGNMENT : "phạm vi"
    ROLE ||--o{ ROLE_ASSIGNMENT : "được gán"
    ORDER ||--o{ ORDER_ITEM : "bao gồm"
    PRODUCT ||--o{ ORDER_ITEM : "tham chiếu"
    MEMBERSHIP {
      uuid teamId
      uuid userId
      string role
      string status
      long version
    }
    ROLE_ASSIGNMENT {
      uuid id
      uuid projectId
      uuid userId
      string roleKey
    }
    ORDER_ITEM {
      uuid id
      uuid orderId
      uuid productId
      int quantity
      decimal unitPriceSnapshot
    }
~~~

Ở mô hình này:

- **USER** là tài khoản của một người; **TEAM** là nhóm. **MEMBERSHIP** là quan hệ có thuộc tính và vòng đời riêng.
- **ROLE_ASSIGNMENT** mô tả việc một chủ thể nhận một vai trò trong **phạm vi** cụ thể. Một người có thể có nhiều vai trò khác nhau ở các dự án khác nhau.
- **PRODUCT** là hàng hóa trong danh mục; **ORDER_ITEM** tham chiếu product nhưng sở hữu **quantity**, **đơn giá tại thời điểm chốt** và các giá trị nghiệp vụ của đơn.

Mỗi quan hệ có thể có ràng buộc duy nhất, trạng thái, thao tác và lịch sử khác nhau. Không nên chọn cách tổ chức endpoint chỉ vì hai bảng đang được nối bằng khóa ngoại.

### 2.1. Bốn cách biểu diễn phổ biến

| Cách | Ví dụ URI | Phù hợp | Hạn chế |
|---|---|---|---|
| **Subcollection của tài nguyên cha** | /v1/teams/{teamId}/members | Danh sách và thao tác các thành viên trong một nhóm | Phải xác định quyền với cha và quan hệ khi tra cứu |
| **Quan hệ có khóa ghép ổn định** | /v1/teams/{teamId}/members/{userId} | Mỗi user chỉ có một membership hiện hành trong team; client biết ID hai phía | Khó nếu cần nhiều quan hệ cùng cặp hoặc nhiều lần gia nhập có lịch sử tách biệt |
| **Bản ghi quan hệ có ID riêng** | /v1/projects/{projectId}/role-assignments/{assignmentId} | Quan hệ nhiều thuộc tính, nhiều gán quyền cùng user, audit và vòng đời độc lập | Thêm ID và endpoint tra cứu; cần unique constraint nghiệp vụ |
| **Cập nhật tập liên kết trong tài nguyên cha** | PATCH /v1/articles/{id} với tags | Tập nhỏ, đơn giản, được cập nhật nguyên tử như một thuộc tính | Dễ ghi đè thay đổi đồng thời; không phù hợp với quan hệ có quyền/vòng đời riêng |

**Không có một kiểu URI bắt buộc cho mọi quan hệ.** Chọn mô hình dựa trên quy tắc nghiệp vụ, quyền sở hữu, danh tính ổn định của relation, khả năng cần truy vấn riêng và nhu cầu chống tranh chấp.

### 2.2. Khi nào quan hệ nên là tài nguyên hạng nhất?

Ưu tiên tạo **association resource** khi quan hệ có ít nhất một đặc điểm:

- Có thuộc tính riêng: role, quantity, status, invitedAt, grantedBy, expiresAt.
- Có vòng đời hoặc thao tác riêng: invite, accept, suspend, revoke.
- Có quyền truy cập riêng, cần audit hoặc trả về trong một collection.
- Có unique constraint, phiên bản cập nhật hoặc transaction cần bảo vệ.
- Client cần tham chiếu trực tiếp bằng URI hoặc dùng ETag để sửa có điều kiện.

Với quan hệ đơn giản, ít thay đổi, không cần metadata (chẳng hạn thêm một tag vào danh sách tag của bài viết), có thể biểu diễn bằng trường của resource hoặc một subresource riêng. Tuy nhiên, nếu tag do nhiều người chỉnh đồng thời, vẫn cần chiến lược chống mất cập nhật.

## 3. Đặt tên URI cho thao tác quan hệ

URI nên gọi tên **thứ được quản lý**, tránh biến endpoint thành lệnh RPC không có resource rõ ràng.

| Nhu cầu | URI đề xuất | Cần hiểu |
|---|---|---|
| Xem thành viên nhóm | GET /v1/teams/{teamId}/members | Collection membership nằm trong team |
| Xem một thành viên | GET /v1/teams/{teamId}/members/{userId} | Resource membership, không phải hồ sơ USER |
| Thêm thành viên | POST /v1/teams/{teamId}/members | Server xử lý yêu cầu tạo relation |
| Đặt/ghi đè membership có khóa tự nhiên | PUT /v1/teams/{teamId}/members/{userId} | Cần hợp đồng replace/upsert rõ ràng |
| Đổi vai trò một thành viên | PATCH /v1/teams/{teamId}/members/{userId} | Thay đổi một phần membership |
| Gỡ thành viên | DELETE /v1/teams/{teamId}/members/{userId} | Xóa relation trong team, **không xóa user** |
| Xem các gán vai trò của dự án | GET /v1/projects/{projectId}/role-assignments | Quan hệ user-role trong project |
| Tạo gán vai trò | POST /v1/projects/{projectId}/role-assignments | Nhiều role mỗi user có thể dùng ID riêng |
| Thu hồi gán vai trò | DELETE /v1/projects/{projectId}/role-assignments/{assignmentId} | Thu hồi **assignment cụ thể** |
| Liệt kê mặt hàng trong đơn | GET /v1/orders/{orderId}/items | Collection item thuộc order |
| Thêm mặt hàng vào đơn | POST /v1/orders/{orderId}/items | Server cấp itemId, kiểm tra trạng thái đơn |
| Sửa số lượng | PATCH /v1/orders/{orderId}/items/{itemId} | Chỉ sửa trường được phép |
| Bỏ mặt hàng khỏi đơn chưa chốt | DELETE /v1/orders/{orderId}/items/{itemId} | Giữ ràng buộc theo trạng thái order |

**Tên số nhiều** ở collection là lựa chọn dễ đọc: /members, /role-assignments, /items. URI con thể hiện quan hệ có **phạm vi** trong tài nguyên cha. Ví dụ, cùng itemId không được cho phép truy cập nếu nó không thuộc orderId trong đường dẫn.

### 3.1. Vì sao tránh endpoint động từ?

Những đường dẫn sau có thể chạy được nhưng dễ làm hợp đồng mơ hồ:

~~~text
POST /v1/teams/42/addUser
POST /v1/users/7/assignRole
POST /v1/orders/99/addProduct
POST /v1/orders/99/removeProduct
~~~

Chúng khiến client khó biết **resource nào được tạo**, cách đọc trạng thái kết quả, có thể lặp lại request hay không và cách áp dụng HTTP semantics. Ưu tiên resource:

~~~http
POST /v1/teams/42/members HTTP/1.1
Content-Type: application/json

{"userId":"7","role":"VIEWER"}
~~~

Nếu thao tác thực sự là **workflow dài hoặc hành động nghiệp vụ** không diễn đạt hợp lý bằng CRUD (chẳng hạn phê duyệt lời mời), có thể tạo tài nguyên yêu cầu/biên bản hành động như /invitations hoặc /approvals và cho phép trạng thái tiến triển. Không ép một luồng nhiều bước thành sửa bừa một thuộc tính nếu nghiệp vụ cần lưu lịch sử.

### 3.2. URI lồng nhau không buộc dữ liệu phải lồng nhau

URI /orders/{orderId}/items/{itemId} biểu diễn **phạm vi truy cập và quan hệ sở hữu**, không buộc database phải là document lồng item trong order. Bên dưới có thể là bảng order_items với order_id, item_id, product_id, quantity, price_snapshot. API vẫn phải bảo đảm tra cứu bằng **cả orderId và itemId** và kiểm tra quyền đối với order.

Không mặc định lồng URL vô hạn như /companies/{companyId}/departments/{deptId}/teams/{teamId}/members/{userId}/roles/{roleId}. Nếu đường dẫn quá sâu hoặc entity có vòng đời độc lập, cân nhắc resource có ID riêng và filter theo scope; miễn hợp đồng và phân quyền luôn rõ.

## 4. Hợp đồng representation của quan hệ

### 4.1. Thành viên nhóm

Ví dụ biểu diễn membership:

~~~json
{
  "teamId": "team-42",
  "userId": "user-7",
  "role": "EDITOR",
  "status": "ACTIVE",
  "joinedAt": "2026-11-18T09:00:00Z",
  "updatedAt": "2026-11-18T09:35:00Z",
  "links": {
    "self": "/v1/teams/team-42/members/user-7",
    "user": "/v1/users/user-7"
  }
}
~~~

**Membership.role** là vai trò **trong team-42**, không làm thay đổi vai trò toàn cục của USER. **Membership.status** cho biết trạng thái quan hệ, không nói tài khoản có bị khóa ở mức hệ thống hay không. Thuộc tính như joinedAt, updatedAt và links có thể là read-only; một PATCH từ client không được tự sửa các giá trị server quản lý này.

### 4.2. Gán vai trò trong một phạm vi

~~~json
{
  "id": "assignment-815",
  "projectId": "project-61",
  "principalId": "user-7",
  "roleKey": "REPORT_VIEWER",
  "grantedBy": "user-admin",
  "createdAt": "2026-11-18T10:00:00Z"
}
~~~

Việc **gán role** khác với **định nghĩa role**. Một role như REPORT_VIEWER có thể ánh xạ đến nhiều permission được quản lý bởi hệ thống. Hợp đồng phải phân biệt:

- **Role definition:** /v1/roles/{roleKey} định nghĩa tập permission (thường quản trị hệ thống).
- **Role assignment:** /v1/projects/{projectId}/role-assignments/{assignmentId} gán một role cho một principal trong phạm vi project.
- **Effective permissions:** quyền thực sự được suy ra từ các assignment, chính sách tổ chức, ownership và điều kiện bổ sung; có thể cung cấp endpoint read-only nếu nghiệp vụ cần.

**Đổi role của một membership** có thể được model như PATCH role khi mỗi member chỉ có một role trong nhóm; nếu người dùng có **nhiều vai trò** trong dự án, dùng role-assignment resource thường rõ ràng hơn.

### 4.3. Mặt hàng trong đơn

~~~json
{
  "id": "item-12",
  "orderId": "order-85",
  "productId": "product-9",
  "sku": "SKU-BLUE-L",
  "quantity": 2,
  "unitPrice": {
    "amount": "149000",
    "currency": "VND"
  },
  "lineTotal": {
    "amount": "298000",
    "currency": "VND"
  }
}
~~~

**PRODUCT** giữ giá niêm yết và thông tin hàng hóa hiện hành; **ORDER_ITEM** giữ thông tin giá/thuế/giảm giá **được tính hoặc chốt theo chính sách của đơn**. Client thường chỉ được gửi productId, quantity và lựa chọn biến thể, **không được đặt giá cuối cùng** tùy ý. Server phải xác minh sản phẩm, người bán, trạng thái đơn, tồn kho và quy tắc định giá.

**Tiền** nên dùng decimal hoặc đơn vị nhỏ nhất của đồng tiền, tránh phép cộng số thực nhị phân gây sai lệch. Các giá trị tiền trong ví dụ là chuỗi đơn vị VND để minh họa hợp đồng; production cần thống nhất định dạng tiền, thuế, làm tròn và tỉ giá.

## 5. Chọn HTTP method theo danh tính và ý định

| Method | Quan hệ | Tính chất HTTP liên quan | Phản hồi thường gặp |
|---|---|---|---|
| **GET** | Đọc membership, assignment hoặc item | Safe, idempotent | 200 với body; 404 nếu không có/không được tiết lộ |
| **POST** trên collection | Tạo membership, assignment, item do server định danh/xử lý | Không mặc định idempotent | 201 + Location; có thể 202 khi xử lý bất đồng bộ |
| **PUT** trên relation URI xác định | Tạo hoặc **thay thế toàn bộ trạng thái mong muốn** theo hợp đồng | Idempotent theo hiệu ứng dự kiến | 201 khi tạo; 200 hoặc 204 khi thay thế |
| **PATCH** trên relation URI | Chỉnh một phần thuộc tính của quan hệ | Không mặc định idempotent; tùy patch document | 200 với representation; 204 nếu không trả body |
| **DELETE** trên relation URI | Loại bỏ quan hệ | Idempotent theo hiệu ứng dự kiến | 204; 404 theo hợp đồng khi không có |
| **HEAD** | Kiểm tra metadata của relation có thể xem | Safe, idempotent, **không có body** | 200/404/403 theo chính sách GET |

**Idempotent không có nghĩa trả cùng status mỗi lần.** Chẳng hạn PUT tạo resource lần đầu trả 201, gửi lại cùng trạng thái có thể trả 204; DELETE lần đầu trả 204, lần sau 404. Điều kiện là **hiệu ứng dự kiến lên server** không thay đổi sau khi thực hiện nhiều lần giống hệt nhau.

### 5.1. POST khi server quyết định danh tính

~~~http
POST /v1/teams/team-42/members HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: join-team42-user7

{
  "userId": "user-7",
  "role": "VIEWER"
}

HTTP/1.1 201 Created
Location: /v1/teams/team-42/members/user-7
Content-Type: application/json
ETag: "membership-v1"

{
  "teamId": "team-42",
  "userId": "user-7",
  "role": "VIEWER",
  "status": "ACTIVE"
}
~~~

Header **Idempotency-Key** trong ví dụ là **hợp đồng ứng dụng tự chọn** (không phải tự động được mọi REST server xử lý). Server phải lưu kết quả theo khóa, phạm vi principal/tenant, fingerprint request và thời hạn sử dụng nếu muốn chống tạo trùng do client gửi lại.

**Location** trỏ đến resource mới. Nếu tạo invitation bất đồng bộ cần chờ người dùng chấp nhận, nên trả representation/URI của **invitation** hoặc operation tương ứng, thay vì nói membership đã ACTIVE khi chưa có.

### 5.2. PUT khi client biết URI duy nhất của relation

~~~http
PUT /v1/teams/team-42/members/user-7 HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json
If-None-Match: *

{
  "role": "VIEWER",
  "status": "ACTIVE"
}

HTTP/1.1 201 Created
Location: /v1/teams/team-42/members/user-7
~~~

Đây là **một hợp đồng cho phép tạo quan hệ tại URI ổn định**. Dùng **If-None-Match: \*** để yêu cầu chỉ tạo khi chưa có representation hiện tại. Nếu đã có, server phải đánh giá tiền điều kiện và thường trả **412 Precondition Failed**; không mặc định xử lý như create mới. Chỉ bật PUT upsert khi client được phép quyết định trạng thái relation và các ràng buộc nghiệp vụ cho phép; không dùng PUT để bỏ qua bước mời/chấp nhận bắt buộc.

Khi PUT thay thế một membership đã tồn tại, có thể yêu cầu **If-Match** để tránh ghi đè thay đổi đồng thời. PUT dùng representation đủ các trường được phép ghi cho relation; không coi PUT như PATCH tùy tiện mà không mô tả hợp đồng.

### 5.3. PATCH để thay một trường quan hệ

~~~http
PATCH /v1/teams/team-42/members/user-7 HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/merge-patch+json
If-Match: "membership-v4"

{"role":"EDITOR"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "membership-v5"

{"teamId":"team-42","userId":"user-7","role":"EDITOR","status":"ACTIVE"}
~~~

Với **JSON Merge Patch** (RFC 7396), giá trị null thường có ý nghĩa **xóa trường**, nên phải phân biệt các trường được phép patch và giá trị null hợp lệ. Nếu API chỉ hỗ trợ payload tùy chỉnh như **ChangeMembershipRoleRequest**, sử dụng media type và hợp đồng riêng rõ ràng; đừng khai báo application/merge-patch+json rồi diễn giải theo một quy tắc khác.

Một PATCH đặt giá trị cố định "EDITOR" có thể có hiệu ứng lặp ổn định; một PATCH kiểu **tăng quantity thêm 1** không idempotent và rất dễ bị thực thi trùng. Với số lượng mặt hàng, ưu tiên gửi **giá trị tuyệt đối** và dùng precondition nếu có cạnh tranh.

### 5.4. DELETE loại bỏ quan hệ, không xóa thực thể hai bên

~~~http
DELETE /v1/teams/team-42/members/user-7 HTTP/1.1
Authorization: Bearer <token>
If-Match: "membership-v5"

HTTP/1.1 204 No Content
~~~

DELETE ở URI membership xóa **quan hệ thành viên team-42 ↔ user-7**. Nó không xóa account user-7 khỏi hệ thống, cũng không xóa team-42. Có thể lưu audit record hoặc tombstone nội bộ mà response vẫn là 204. Không trả body cho 204.

Nếu membership không có hoặc không được phép tiết lộ, 404 là chính sách phù hợp; một API chọn DELETE “đảm bảo trạng thái vắng mặt” có thể trả 204 kể cả khi quan hệ không có. **Phải kiểm tra phân quyền trước**: trả 204 vô điều kiện cho một quan hệ thuộc tenant khác có thể tạo lỗ hổng hoặc che giấu việc thiếu quyền.

## 6. Vòng đời thành viên: mời, chấp nhận, kích hoạt, thu hồi

Không phải mọi thành viên đều vào team ngay khi người quản trị thêm một ID. Nếu nghiệp vụ cần đồng ý tham gia, nên mô hình hóa **invitation** và **membership** là những resource hoặc trạng thái có ranh giới rõ.

~~~mermaid
stateDiagram-v2
    [*] --> INVITED : Tạo lời mời
    INVITED --> ACTIVE : Người được mời chấp nhận
    INVITED --> EXPIRED : Hết hạn
    INVITED --> REVOKED : Người mời thu hồi
    ACTIVE --> SUSPENDED : Quản trị tạm khóa
    SUSPENDED --> ACTIVE : Khôi phục
    ACTIVE --> REMOVED : Rời nhóm / bị gỡ
    SUSPENDED --> REMOVED : Bị gỡ
~~~

**Sơ đồ mô tả một mô hình nghiệp vụ có thể chọn**, không yêu cầu mọi API phải lưu lời mời và tư cách thành viên trong cùng bảng. Một thiết kế rõ hơn là:

~~~text
POST /v1/teams/{teamId}/invitations
GET  /v1/teams/{teamId}/invitations/{invitationId}
POST /v1/invitations/{invitationId}/acceptances
GET  /v1/teams/{teamId}/members/{userId}
DELETE /v1/teams/{teamId}/members/{userId}
~~~

POST /acceptances tạo **record chấp nhận** và kích hoạt membership trong transaction phù hợp; các trạng thái/tác dụng cụ thể phải được mô tả. Nếu muốn dùng PATCH trạng thái lời mời, cần xác định chính xác ai được sửa và transition nào hợp lệ.

### 6.1. Các bất biến nghiệp vụ cần giữ

| Bất biến | Ví dụ | Biện pháp triển khai |
|---|---|---|
| **Một membership hiện hành cho mỗi cặp team-user** | User-7 không được có hai membership ACTIVE trong cùng team | Unique constraint phù hợp với mô hình xóa mềm/lịch sử |
| **Không tự nâng quyền** | VIEWER không tự chuyển role thành OWNER | Phân quyền action + vai trò mục tiêu phía server |
| **Không xóa chủ sở hữu cuối cùng** | Team phải có ít nhất một OWNER hiện hành | Transaction/lock bảo vệ thao tác đồng thời |
| **Không nhận lời mời đã hết hạn hoặc bị thu hồi** | Invitation EXPIRED không tạo ACTIVE membership | Kiểm tra trạng thái trong transaction; ràng buộc version |
| **Không tham gia sai tenant** | User từ tenant B không được thêm vào team A trừ khi policy chia sẻ cho phép | Xác thực tenant/team, chính sách cross-tenant minh bạch |
| **Audit được thay đổi quyền** | Ai gán OWNER cho user-7, lúc nào và lý do | Audit event/record có phạm vi truy cập bảo vệ |

**Quy tắc "không xóa OWNER cuối cùng" phải được kiểm tra nguyên tử**. Hai admin đồng thời tự hạ quyền có thể cùng đọc thấy hai OWNER và cùng được phép, làm team không còn ai quản lý. Cần khóa hoặc cập nhật có điều kiện ở **cấp team**, không chỉ optimistic lock trên hai bản ghi membership riêng lẻ.

### 6.2. Tách quyền xem thành viên và quyền sửa thành viên

Một thành viên có thể được xem danh sách nhóm nhưng không được **thêm**, **xóa** hoặc **đổi role** của người khác. API cần kiểm tra quyền theo hành động:

~~~text
team.members.read
team.members.invite
team.members.role.assign
team.members.suspend
team.members.remove
~~~

Đây chỉ là ví dụ tên permission. Phân quyền thực tế có thể dựa trên RBAC, ABAC hoặc chính sách theo tổ chức. Quyền tạo membership không tự động bao gồm quyền gán mọi role; quyền xóa người khác không tự động cho phép xóa owner cuối cùng.

## 7. Gán vai trò và quyền: tách định nghĩa khỏi hiệu lực

Thiết kế liên quan đến **quyền** thường bị sai khi coi permission là một danh sách chuỗi do client tự gửi lên user:

~~~json
{"permissions":["read:any","write:any","admin:all"]}
~~~

Nếu server chấp nhận bất kỳ tập quyền nào từ client, người có quyền gán thành viên có thể tự leo thang thành quản trị viên. Đúng hơn, hệ thống nên quản lý **role definition** và một hợp đồng **role assignment** được phân quyền.

### 7.1. Các resource và phạm vi

~~~text
GET    /v1/roles                             # role được phép xem
GET    /v1/projects/{projectId}/role-assignments
POST   /v1/projects/{projectId}/role-assignments
GET    /v1/projects/{projectId}/role-assignments/{assignmentId}
DELETE /v1/projects/{projectId}/role-assignments/{assignmentId}
GET    /v1/projects/{projectId}/effective-permissions/me
~~~

Một role assignment có thể biểu diễn cặp **principal + roleKey + scope**. Ví dụ, user-7 là REPORT_VIEWER ở project-61 không làm họ có quyền đọc báo cáo của project-62.

### 7.2. Gán role

~~~http
POST /v1/projects/project-61/role-assignments HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "principalId": "user-7",
  "roleKey": "REPORT_VIEWER"
}

HTTP/1.1 201 Created
Location: /v1/projects/project-61/role-assignments/assignment-815
Content-Type: application/json

{
  "id": "assignment-815",
  "projectId": "project-61",
  "principalId": "user-7",
  "roleKey": "REPORT_VIEWER"
}
~~~

Server phải kiểm tra người gọi có quyền gán **roleKey này trong project-61**; roleKey có tồn tại, được phép sử dụng, không vi phạm chính sách phân cấp, không gán cho tài khoản bị cấm, và assignment có trùng không. Nếu trùng, có thể trả 409 hoặc hỗ trợ request lặp qua idempotency key theo hợp đồng.

### 7.3. Thu hồi assignment và quyền hiệu lực

DELETE /role-assignments/{assignmentId} thu hồi một assignment đã biết, không đồng nghĩa xóa role khỏi catalog hoặc xóa tài khoản. Quyền hiệu lực có thể được hợp thành từ nhiều assignment, quyền kế thừa, ownership, điều kiện thời gian và chính sách từ chối ưu tiên. Vì vậy:

- Sau khi thu hồi một assignment, user vẫn **có thể còn quyền tương ứng** từ một nguồn khác.
- Không suy quyền chỉ bằng một trường role trong JWT quá hạn nếu nghiệp vụ yêu cầu thu hồi tức thì; cần chiến lược token TTL, introspection, cache invalidation hoặc kiểm tra tập trung phù hợp.
- API liệt kê assignment và endpoint **effective-permissions** phải có quy tắc phân quyền, phạm vi tenant và thời hạn cache riêng.
- Audit cần lưu người thực hiện, phạm vi, vai trò trước/sau và ID request, nhưng không lộ dữ liệu nhạy cảm qua lỗi công khai.

**Lựa chọn đặt role là field của membership hay resource riêng** phụ thuộc câu hỏi: mỗi user có tối đa một role trong team hay nhiều role theo nhiều phạm vi? Có cần audit/quản lý hiệu lực riêng không? Câu trả lời quyết định cấu trúc, không phải trào lưu REST.

## 8. Mặt hàng trong giỏ hoặc đơn: quan hệ có số lượng và giá trị

Giỏ hàng và đơn hàng trông giống nhau về cấu trúc nhưng **vòng đời khác nhau**:

- **Cart item:** trạng thái dự kiến mua, có thể tăng/giảm quantity và tính lại giá; giá hiển thị có thể thay đổi.
- **Order item:** thành phần đã được xác nhận trong đơn; thường cần chốt giá, thuế, giảm giá, sản phẩm và lựa chọn tại thời điểm mua. Sau khi đặt hàng, việc sửa có thể bị cấm hoặc cần nghiệp vụ điều chỉnh đơn riêng.

Không nên dùng chung một API sửa mặt hàng cho cả giỏ nháp và đơn đã thanh toán nếu invariants khác nhau.

### 8.1. Tạo mặt hàng

~~~http
POST /v1/orders/order-85/items HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json
Idempotency-Key: order85-add-product9-request1

{
  "productId": "product-9",
  "quantity": 2
}

HTTP/1.1 201 Created
Location: /v1/orders/order-85/items/item-12
Content-Type: application/json

{
  "id": "item-12",
  "orderId": "order-85",
  "productId": "product-9",
  "quantity": 2,
  "unitPrice": {"amount":"149000","currency":"VND"},
  "lineTotal": {"amount":"298000","currency":"VND"}
}
~~~

API cần xác định **đơn có đang ở trạng thái cho phép sửa không**, sản phẩm có bán được không, số lượng có hợp lệ không và giá được lấy từ nguồn tin cậy nào. Nếu một sản phẩm đã có trong đơn, hợp đồng có thể:

- **Tạo item mới:** mỗi lần thêm tạo một line riêng, dùng ID server cấp.
- **Hợp nhất vào một item theo product + biến thể:** cần unique constraint và cập nhật quantity có kiểm soát.
- **Từ chối item trùng:** trả **409 Conflict** và chỉ rõ cách client cập nhật item hiện có.

Không có lựa chọn nào tự nhiên đúng hơn. Quan trọng là client biết liệu **POST lần hai** là tạo dòng thứ hai, tăng số lượng hay bị coi là duplicate.

### 8.2. Sửa số lượng bằng giá trị tuyệt đối

~~~http
PATCH /v1/orders/order-85/items/item-12 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "item-v3"
Authorization: Bearer <token>

{"quantity":3}

HTTP/1.1 200 OK
ETag: "item-v4"
Content-Type: application/json

{
  "id":"item-12",
  "orderId":"order-85",
  "productId":"product-9",
  "quantity":3,
  "unitPrice":{"amount":"149000","currency":"VND"},
  "lineTotal":{"amount":"447000","currency":"VND"}
}
~~~

Client gửi **quantity = 3** biểu thị trạng thái mong muốn. Nếu client gửi câu lệnh **increment quantity** và HTTP request bị gửi lại, số lượng có thể tăng hai lần. Khi cần hành vi cộng dồn, nên dùng operation resource có ID/idempotency key riêng hoặc phối hợp cập nhật có điều kiện, thay vì cho phép retry mù.

### 8.3. Trạng thái đơn và tính nhất quán tổng tiền

Giả sử đơn có ba item và client sửa item thứ nhất cùng lúc client khác xóa item thứ hai. Nếu chỉ khóa từng item, phần **order.total** có thể bị tính sai do hai transaction ghi đè. Cần xác định **aggregate boundary** là Order:

1. Trong một transaction, xác minh **orderId, itemId, owner/tenant và trạng thái order**.
2. Kiểm tra điều kiện cạnh tranh đối với item, đồng thời khóa/cập nhật có điều kiện version của order nếu tổng tiền hoặc trạng thái phụ thuộc toàn bộ danh sách.
3. Xác minh quantity, giới hạn, promotion, tax, chính sách pricing và sản phẩm.
4. Lưu item, tính lại subtotal/discount/tax/total trong cùng ranh giới tính nhất quán được chọn.
5. Tăng version phù hợp, ghi sự kiện outbox nếu cần thông báo downstream.

**If-Match của URI item** áp dụng cho representation item. Muốn đồng thời bảo vệ toàn bộ **Order aggregate**, server phải thêm khóa/version/check trong transaction hoặc thiết kế yêu cầu PATCH trên Order với ETag của chính Order. Không tự coi ETag của item đã thay thế cơ chế đồng bộ ở cấp Order.

### 8.4. Sau khi đặt hàng

Một khi order đã chuyển sang PLACED hoặc PAID, việc PATCH quantity thường phải trả **409 Conflict** hoặc từ chối theo hợp đồng. Nếu muốn sửa đơn, có thể tạo **order amendment**, **cancelation** hoặc **return** resource tùy quy trình. Đừng thay đổi giá trị hóa đơn lịch sử ngay trong order item mà không có dấu vết.

Kiểm tra tồn kho và thanh toán thường liên quan nhiều hệ thống. Không hứa transaction nguyên tử xuyên qua catalog, inventory, payment và database đơn chỉ vì dùng REST; cân nhắc reservation, idempotency, outbox và workflow bù trừ theo yêu cầu.

## 9. Idempotency: thêm quan hệ đúng một lần về mặt nghiệp vụ

Mạng có thể mất response ngay sau khi server đã commit. Client thấy timeout, gửi lại POST và có nguy cơ thêm thành viên hoặc mặt hàng lần thứ hai. Cần phân biệt **idempotency của HTTP method** và **idempotency ở nghiệp vụ**.

### 9.1. POST tạo relation có thể trùng khi retry

Ví dụ:

~~~text
Client                 API                        DB
  | POST add item       |                         |
  |-------------------->| INSERT item-12          |
  |                     |------------------------>|
  |                     | COMMIT                  |
  |                     |<------------------------|
  |    (mất response)   |                         |
  | POST add item again |                         |
  |-------------------->| INSERT item-13 ?        |
~~~

Nếu nghiệp vụ không cho phép tạo hai dòng, cần **unique constraint** theo khóa nghiệp vụ và/hoặc **Idempotency-Key**. Nếu nghiệp vụ cho phép hai line item có cùng productId, chỉ unique(productId, orderId) sẽ **thay đổi thiết kế**; lúc đó idempotency key giúp phân biệt **hai yêu cầu tạo thật sự khác nhau** với **một yêu cầu bị lặp**.

### 9.2. Quy tắc quản lý Idempotency-Key

| Quy tắc | Mục đích |
|---|---|
| Khóa được cấp theo **ý định nghiệp vụ** và giữ nguyên khi retry | Retry cùng một thao tác không tạo side effect thứ hai |
| Phạm vi gồm người gọi/tenant, endpoint và operation thích hợp | Không cho người dùng khác “mượn” cache idempotency của nhau |
| Lưu **hash/canonical fingerprint** của request | Cùng key nhưng payload khác phải bị từ chối theo hợp đồng |
| Ghi trạng thái thực thi và kết quả **bền vững** | Retry sau khi process crash vẫn có thể xác định đã thành công |
| Chặn hai request cùng key chạy đồng thời | Tránh xử lý side effect hai lần trước khi cache kết quả |
| Có retention và quy tắc hết hạn được công bố | Client biết thời gian có thể retry an toàn |
| Không coi key là chứng chỉ phân quyền | **Mọi retry** vẫn phải kiểm tra authentication/authorization |

Ví dụ hợp đồng: với cùng key và cùng payload trong thời hạn lưu, server trả lại kết quả đã xử lý (có thể cùng status/body ban đầu); cùng key nhưng payload khác trả **409 Conflict** hoặc lỗi được tài liệu hóa. Nếu request trước còn đang chạy, có thể trả 409/202 với operation status hoặc chặn/đợi ngắn có deadline. Đừng mặc định mọi dịch vụ tự hiểu header Idempotency-Key.

### 9.3. PUT vào URI ổn định và giới hạn của nó

~~~text
PUT /v1/teams/team-42/members/user-7
Body: {"role":"VIEWER","status":"ACTIVE"}
~~~

Vì resource được định danh bởi cặp team/user, gửi cùng **full desired state** lặp lại thường không làm xuất hiện membership thứ hai. Nhưng vẫn cần:

- Ràng buộc duy nhất ở database; nếu có soft-delete cần thống nhất cách tái tạo.
- Kiểm tra role được phép gán và trạng thái quan hệ hợp lệ ở mỗi lần.
- Cơ chế chống **lost update** nếu client khác đã đổi role giữa hai lần.
- Quy tắc về những side effect như gửi email mời, audit event, notification; không được gửi trùng vô hạn chỉ vì PUT idempotent về resource.

**Phân biệt “tạo trùng record” và “thực hiện side effect trùng”.** Một request idempotent ở trạng thái resource vẫn có thể gửi thông báo nhiều lần nếu side effect không được bảo vệ.

## 10. Concurrency: ngăn ghi đè vai trò, mặt hàng và owner cuối cùng

Hai quản trị viên có thể cùng nhìn membership role = VIEWER. Admin A đổi thành EDITOR; admin B ở tab cũ đổi thành GUEST. Nếu API xử lý **last write wins**, thay đổi A biến mất mà không có cảnh báo.

### 10.1. ETag và cập nhật có điều kiện

Server trả ETag thể hiện phiên bản representation:

~~~http
GET /v1/teams/team-42/members/user-7 HTTP/1.1

HTTP/1.1 200 OK
ETag: "membership-v7"
Content-Type: application/json

{"teamId":"team-42","userId":"user-7","role":"VIEWER","status":"ACTIVE"}
~~~

Client muốn sửa trạng thái đã đọc:

~~~http
PATCH /v1/teams/team-42/members/user-7 HTTP/1.1
If-Match: "membership-v7"
Content-Type: application/merge-patch+json

{"role":"EDITOR"}
~~~

Nếu resource đã thành version v8, điều kiện **If-Match** sai và server trả:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/precondition-failed",
  "title":"Precondition Failed",
  "status":412,
  "detail":"Quan hệ đã thay đổi; tải lại dữ liệu trước khi sửa."
}
~~~

**If-Match sử dụng strong comparison**, nên cung cấp **strong ETag** nhất quán với phiên bản representation mà server bảo vệ; weak ETag như W/"membership-v7" không phù hợp cho If-Match. ETag có thể được xây từ version dữ liệu nhưng phải được thiết kế sao cho mỗi trạng thái biểu diễn có ý nghĩa khác nhau không bị nhận nhầm là cùng validator.

### 10.2. 412 và 409 khác nhau thế nào?

- **412 Precondition Failed:** header điều kiện như If-Match hoặc If-None-Match **được cung cấp nhưng không thỏa**, ví dụ client đã đọc bản cũ.
- **428 Precondition Required:** API yêu cầu phải có điều kiện, nhưng request **không gửi header bắt buộc**. Dùng nếu chính sách yêu cầu optimistic concurrency.
- **409 Conflict:** điều kiện nghiệp vụ hiện tại khiến thao tác không thể thực hiện, chẳng hạn order đã PAID, thành viên đã ACTIVE theo chính sách tạo không trùng, hoặc team sẽ không còn OWNER.
- **422 Unprocessable Content:** payload có cú pháp hợp lệ, nhưng vi phạm quy tắc nội dung như quantity ngoài miền cho phép, nếu API chọn 422 thay cho 400.

Không trả 412 cho mọi lỗi nghiệp vụ chỉ vì API có version. Nếu client gửi If-Match hợp lệ nhưng muốn loại bỏ OWNER cuối cùng, lỗi phù hợp hơn là **409 Conflict** với mã nghiệp vụ rõ ràng và an toàn.

### 10.3. Đảm bảo kiểm tra version tại điểm ghi

Mẫu thao tác an toàn:

~~~text
PATCH membership(role = EDITOR, If-Match = "membership-v7")
  -> xác thực caller
  -> kiểm tra quyền gán role trong team
  -> đọc membership được phép thấy
  -> kiểm tra precondition version v7
  -> kiểm tra bất biến nghiệp vụ
  -> UPDATE membership
        SET role = 'EDITOR', version = 8
        WHERE team_id = :teamId
          AND user_id = :userId
          AND version = 7
  -> affected_rows == 1 ? COMMIT : 412 (sau đối soát thích hợp)
~~~

**Chỉ kiểm tra version trong bộ nhớ rồi UPDATE không điều kiện** không đủ: hai request có thể cùng đọc v7 trước khi một request ghi. Dùng compare-and-set tại database, optimistic locking (@Version), hoặc transaction có khóa phù hợp.

Với bất biến **còn ít nhất một OWNER**, cần đồng bộ ở phạm vi cả team hoặc tập OWNER: chỉ @Version trên từng membership vẫn cho phép hai OWNER khác nhau bị hạ đồng thời. Có thể khóa bản ghi TEAM, dùng constraint/serializable transaction phù hợp hoặc tổ chức thao tác role-change qua một điểm tuần tự hóa.

### 10.4. Retry khi tranh chấp

Đừng tự retry PATCH với body cũ sau 412 vì có thể ghi đè ý định mới. Client nên:

1. GET lại representation và ETag mới.
2. Hiển thị hoặc xử lý khác biệt trạng thái (conflict resolution).
3. Quyết định có gửi lại thay đổi hợp lệ hay không.
4. Nếu gửi, dùng If-Match mới và chịu được request mất response thông qua idempotency/kiểm tra trạng thái.

Retry lỗi DB do deadlock/throttling là chuyện khác với **xung đột nghiệp vụ**. Kể cả retry nội bộ do transient error, vẫn phải có giới hạn thời gian và bảo vệ side effect.

## 11. Xử lý lỗi REST API cho quan hệ

### 11.1. Ma trận trạng thái phổ biến

| Tình huống | Mã nên cân nhắc | Ghi chú |
|---|---|---|
| Tạo membership mới thành công | **201 Created** | Có Location trỏ relation; body nếu hữu ích |
| Tạo lời mời/quan hệ bất đồng bộ | **202 Accepted** | Chỉ khi đã nhận yêu cầu và có cách theo dõi tiến độ |
| Đọc membership hoặc item được phép | **200 OK** | Representation đầy đủ |
| PATCH và trả representation mới | **200 OK** | Trả ETag mới nếu có version |
| PATCH/DELETE xong, không trả body | **204 No Content** | Không kèm body |
| Thiếu token hoặc token không hợp lệ | **401 Unauthorized** | Có WWW-Authenticate phù hợp |
| Đã xác thực nhưng thiếu quyền thao tác được phép công bố | **403 Forbidden** | Ví dụ quyền export danh sách thành viên |
| Parent/relation không có hoặc không được tiết lộ | **404 Not Found** | Chống lộ tài nguyên giữa tenant |
| Trạng thái nghiệp vụ ngăn thao tác | **409 Conflict** | LAST_OWNER, ORDER_ALREADY_PAID, DUPLICATE_MEMBERSHIP |
| Body sai kiểu, JSON không hợp lệ, tham số sai | **400 Bad Request** | Validation về cú pháp và kiểu dữ liệu |
| Body hợp cú pháp nhưng vi phạm quy tắc miền | **422 Unprocessable Content**, hoặc 400 theo hợp đồng | Ví dụ quantity = -1 |
| If-Match/If-None-Match không đạt | **412 Precondition Failed** | Trạng thái server không còn phù hợp |
| Không gửi If-Match khi API yêu cầu | **428 Precondition Required** | Giảm lost update |
| Client vượt quota/rate limit | **429 Too Many Requests** | Có thể cung cấp Retry-After |
| Phương thức không hỗ trợ với URI | **405 Method Not Allowed** | Trả Allow các method được hỗ trợ |

**404 không nên bị hiểu là khẳng định resource chưa từng tồn tại.** Nếu relation thuộc tenant khác hoặc API có chính sách ẩn, 404 giúp hạn chế lộ thông tin; nếu client được phép biết relation tồn tại nhưng không được thao tác, 403 có thể hữu ích hơn.

### 11.2. Problem Details có mã nghiệp vụ

Sử dụng **application/problem+json** theo RFC 9457, ví dụ lỗi không được xóa OWNER cuối:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/last-team-owner",
  "title":"Conflict",
  "status":409,
  "detail":"Nhóm phải còn ít nhất một chủ sở hữu.",
  "code":"LAST_OWNER",
  "requestId":"req-4d28"
}
~~~

**code** và **requestId** là trường mở rộng do ứng dụng công bố; client không nên parse text tiếng Việt ở **detail** để suy luận. Không trả stack trace, SQL, role nội bộ ngoài phạm vi hoặc ID của tenant khác. Nếu relation bị ẩn, response 404 cần có body trung tính như trường hợp thật sự không tồn tại.

### 11.3. Phân biệt mã lỗi và trạng thái nghiệp vụ

Một membership SUSPENDED vẫn có thể là resource đang tồn tại: GET trả 200 với status = SUSPENDED cho người có quyền. Một order PAID vẫn tồn tại: GET /orders/{id}/items trả 200, còn PATCH số lượng có thể trả 409. **Không trả 404 chỉ vì resource không cho phép một hành động** trừ khi chính sách nhìn thấy thực sự muốn che giấu nó.

## 12. Xác thực, phân quyền và cách ly tenant

Các API thao tác quan hệ thường có rủi ro **BOLA/IDOR**: client biết ID của resource ở tenant khác và thử gọi URI quan hệ. Một lỗi phổ biến là chỉ kiểm tra người dùng đã đăng nhập rồi tin teamId, orderId hoặc projectId từ URL.

### 12.1. Kiểm tra tối thiểu cho mọi thao tác

~~~text
Principal đã xác thực
   ↓
Xác định tenant/scope đáng tin cậy
   ↓
Parent resource (team/project/order) có nằm trong phạm vi được thấy?
   ↓
Caller có quyền hành động trên parent/quan hệ?
   ↓
Relation có thực sự thuộc parent trong URI?
   ↓
Target user/role/product có hợp lệ theo nghiệp vụ?
   ↓
Kiểm tra invariant, precondition, transaction
   ↓
Trả representation đã lọc dữ liệu được phép
~~~

**Scope không được lấy trực tiếp từ payload do client tự gửi.** Nếu URL có tenantId, phải đối chiếu với identity và policy. Truy vấn ví dụ cho relation member:

~~~sql
SELECT m.*
FROM team_memberships m
JOIN teams t ON t.id = m.team_id
WHERE t.id = :teamId
  AND t.tenant_id = :authenticatedTenantId
  AND m.user_id = :userId
  AND m.deleted_at IS NULL;
~~~

**Chỉ kiểm tra WHERE member.user_id = :userId là chưa đủ**: phải kiểm tra team, scope và quyền người thực hiện. Với order item, truy vấn bằng **order_id + item_id** sau khi xác thực owner/tenant của order, ngăn lấy item có cùng ID ở order khác.

### 12.2. Phân quyền theo cả hành động và quyền mục tiêu

Giả sử một ADMIN có quyền thêm VIEWER vào team, nhưng chỉ OWNER mới được gán OWNER. Khi POST membership hoặc PATCH role, server phải kiểm tra:

- Người gọi có quyền **manage members** của team?
- Người gọi có quyền **gán role đích cụ thể** không?
- Role đích có được phép trong tenant hoặc loại team này không?
- Target principal có đủ điều kiện được thêm, có bị chặn hay nằm ngoài phạm vi không?
- Có vi phạm giới hạn thành viên, owner cuối cùng, segregation of duties hoặc chính sách phê duyệt không?

Tránh **mass assignment**: nếu client gửi thêm "grantedBy", "isSystemAdmin", "billingAccess", "joinedAt", server phải từ chối hoặc bỏ qua theo hợp đồng xác định; ưu tiên request DTO chỉ liệt kê trường được sửa. Không bind trực tiếp JSON vào entity chứa trường nhạy cảm.

### 12.3. 404 để che giấu quan hệ ngoài phạm vi

Ví dụ:

~~~text
GET /v1/teams/other-team/members/user-7
GET /v1/teams/nonexistent-team/members/user-7
~~~

Hai request có thể đều trả **404 Not Found** nếu chính sách không tiết lộ team không được xem. Không để một endpoint trả “team tồn tại nhưng bạn không có quyền” trong khi endpoint kia trả “không tồn tại” khiến client dò được team ID. Áp dụng nhất quán cho GET, PATCH, DELETE, list, count, search và HEAD, đồng thời kiểm soát cache của các response theo người gọi.

**403 vẫn hữu ích** khi người gọi được quyền biết team và membership tồn tại nhưng không được thực hiện thao tác được công bố, ví dụ một thành viên thường không thể xem audit log quyền của chính team mình. Quyết định 403/404 phải được ghi trong API contract.

### 12.4. Thu hồi quyền và cache

Khi revoke role assignment, quyền đọc/ghi có thể vẫn tồn tại tạm thời trong **access token, permission cache hoặc session**. Nếu nghiệp vụ yêu cầu thu hồi gần tức thì, cần cơ chế phù hợp: token ngắn hạn, kiểm tra trạng thái tại nguồn, cache version/TTL và invalidation. Không giả định HTTP DELETE trả 204 đồng nghĩa mọi service downstream đã ngừng chấp nhận token cũ.

Mọi response phụ thuộc danh tính hoặc quyền nên có **Cache-Control phù hợp**, ví dụ no-store cho thông tin thành viên/role nhạy cảm; không để CDN cache chung kết quả theo URL mà không tách tenant/principal. Log và audit phải bảo vệ dữ liệu cá nhân, không ghi access token hoặc thông tin nhạy cảm vào body lỗi.

## 13. Truy vấn collection quan hệ: phân trang, lọc và cache

Khi một nhóm có vài thành viên, trả toàn bộ trong một response có thể chấp nhận được. Khi có hàng chục nghìn membership hoặc assignment, API cần **pagination** và quy tắc lọc có phạm vi.

### 13.1. Ví dụ truy vấn

~~~http
GET /v1/teams/team-42/members?status=ACTIVE&role=EDITOR&limit=20&cursor=eyJ... HTTP/1.1
Authorization: Bearer <token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {
      "teamId": "team-42",
      "userId": "user-7",
      "role": "EDITOR",
      "status": "ACTIVE"
    }
  ],
  "nextCursor": "eyJ..."
}
~~~

Ví dụ này dùng **cursor** như một token opaque; client không nên giải mã rồi tự dựng token khác. Trường "eyJ..." chỉ là ký hiệu minh họa, không phải chuỗi base64 hợp lệ. Server phải kiểm tra token đúng định dạng, đúng scope/tenant/filter/sort và chưa hết hạn nếu có ký/hạn dùng.

### 13.2. Quy tắc phân trang và lọc

- Chỉ trả quan hệ **trong parent được phép xem**, không phân trang toàn bộ membership rồi lọc quyền trên mỗi trang; cách đó lộ số lượng và tạo trang thiếu dữ liệu.
- Có **thứ tự ổn định**: chẳng hạn joinedAt tăng dần, userId làm tie-breaker. Offset pagination có thể bị lặp/bỏ sót khi danh sách thay đổi đồng thời; cursor/keyset thường hữu ích hơn.
- Áp giới hạn **limit tối đa** và whitelist filter/sort; không cho client gửi tên cột SQL trực tiếp vào ORDER BY.
- Không tiết lộ **totalCount** của tenant khác hoặc danh sách role không được xem.
- Quy định filter mặc định có bao gồm **INVITED, SUSPENDED, REMOVED** không; role assignment hết hiệu lực có nằm trong lịch sử không.
- Nếu cần đọc snapshot nhất quán trên nhiều trang, phải giải quyết thay đổi đồng thời bằng snapshot/cursor version; cursor thường chỉ bảo đảm **thứ tự tiếp tục**, không mặc định cung cấp snapshot.

### 13.3. Cache collection quan hệ

Membership và effective permissions biến đổi theo principal, tenant và chính sách. Lựa chọn thận trọng là **Cache-Control: no-store**, nhất là khi dữ liệu nhạy cảm hoặc cần thu hồi quyền nhanh. Với danh sách công khai (ví dụ thành viên của cộng đồng public), có thể cache có TTL ngắn sau khi tách đúng khả năng hiển thị.

**ETag trên collection** nếu có phải đại diện cho phiên bản danh sách dưới các filter và quyền hiện tại; thay đổi membership có thể làm ETag không còn hợp lệ. Không lấy ETag của một item rồi xem đó là ETag của collection.

## 14. Triển khai minh họa bằng Java/Spring Boot

Các đoạn dưới đây mô tả ranh giới **HTTP/controller → service nghiệp vụ → repository/transaction** trên Spring Boot 3, Java 17 trở lên. Đây là mã **minh họa thiết kế**, không phải dự án chạy độc lập: cần bổ sung entity, dependency Spring Security, DTO mapper, validation, exception handlers, persistence configuration và migration DB.

### 14.1. DTO giới hạn trường client được sửa

~~~java
enum TeamRole {
    VIEWER, EDITOR, OWNER
}

record AddMemberRequest(
    @NotNull UUID userId,
    @NotNull TeamRole role
) {}

record ChangeMemberRoleRequest(
    @NotNull TeamRole role
) {}

record MemberView(
    UUID teamId,
    UUID userId,
    TeamRole role,
    String status,
    long version
) {}

record CreatedMember(MemberView value, boolean createdNew) {}
~~~

**Trường do server quản lý** như tenantId, grantedBy, joinedAt, version, isSystemAdmin không có trong request DTO. Nếu vai trò có hàng trăm mã, có thể dùng enum/mã roleKey được registry quản lý và validate theo scope; không nhận tùy ý các chuỗi permission từ client.

### 14.2. Controller định nghĩa HTTP contract

~~~java
@RestController
@RequestMapping("/v1/teams/{teamId}/members")
class TeamMemberController {
    private final MembershipService service;

    TeamMemberController(MembershipService service) {
        this.service = service;
    }

    @GetMapping("/{userId}")
    ResponseEntity<MemberView> get(
            @PathVariable UUID teamId,
            @PathVariable UUID userId,
            @AuthenticationPrincipal Jwt jwt) {

        MemberView member = service.findVisible(teamId, userId, jwt);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .eTag(etag(member.version()))
            .body(member);
    }

    @PostMapping
    ResponseEntity<MemberView> add(
            @PathVariable UUID teamId,
            @Valid @RequestBody AddMemberRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false)
                String idempotencyKey,
            @AuthenticationPrincipal Jwt jwt) {

        CreatedMember result = service.add(
            teamId, request, idempotencyKey, jwt
        );
        MemberView member = result.value();
        URI location = URI.create(
            "/v1/teams/" + teamId + "/members/" + member.userId()
        );

        // Ví dụ: service trả createdNew=false khi replay hợp lệ.
        HttpStatus code = result.createdNew()
            ? HttpStatus.CREATED : HttpStatus.OK;
        return ResponseEntity.status(code)
            .location(location)
            .cacheControl(CacheControl.noStore())
            .eTag(etag(member.version()))
            .body(member);
    }

    @PatchMapping(
        path = "/{userId}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<MemberView> changeRole(
            @PathVariable UUID teamId,
            @PathVariable UUID userId,
            @Valid @RequestBody ChangeMemberRoleRequest request,
            @RequestHeader(value = "If-Match", required = false)
                String ifMatch,
            @AuthenticationPrincipal Jwt jwt) {

        MemberView member = service.changeRole(
            teamId, userId, request.role(), ifMatch, jwt
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .eTag(etag(member.version()))
            .body(member);
    }

    @DeleteMapping("/{userId}")
    ResponseEntity<Void> remove(
            @PathVariable UUID teamId,
            @PathVariable UUID userId,
            @RequestHeader(value = "If-Match", required = false)
                String ifMatch,
            @AuthenticationPrincipal Jwt jwt) {

        service.remove(teamId, userId, ifMatch, jwt);
        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }

    private static String etag(long version) {
        return "\"membership-v" + version + "\"";
    }
}
~~~

Controller ở đây dùng **application/json với DTO ChangeMemberRoleRequest** cho PATCH như một **hợp đồng patch chuyên biệt**, không tuyên bố hỗ trợ chuẩn JSON Merge Patch. Nếu thực sự muốn hỗ trợ **application/merge-patch+json**, cần parse và áp dụng đầy đủ semantics của RFC 7396 (bao gồm trường null và trường không có), đồng thời whitelist các trường được phép sửa.

**Không trông chờ controller tự bảo vệ quyền.** Mọi hàm service phải đọc claims từ JWT đã xác thực và kiểm tra team/tenant, action, role đích, version, invariant và transaction. Dù controller được gọi từ endpoint khác hoặc worker nội bộ, cơ chế bảo vệ nghiệp vụ vẫn phải được giữ.

### 14.3. Service quản lý transaction và invariant

Pseudocode có thể dịch sang @Transactional và repository tương ứng:

~~~text
changeRole(teamId, userId, targetRole, ifMatch, principal):
    actor = requireAuthenticatedActor(principal)
    requireHeader(ifMatch)                       # thiếu -> 428

    transaction:
        team = teams.findByIdAndTenantForUpdate(teamId, actor.tenantId)
        if team absent: raise HiddenNotFound     # 404 chung

        requirePermission(actor, team, "team.members.role.assign")
        requireCanAssignRole(actor, targetRole, team)

        member = members.findVisibleInTeam(teamId, userId)
        if member absent: raise HiddenNotFound

        requireStrongEtagMatch(ifMatch, member.version) # sai -> 412

        if member.role == OWNER and targetRole != OWNER:
            if members.countActiveOwners(teamId) <= 1:
                raise LastOwnerConflict         # 409

        member.role = targetRole
        members.saveWithOptimisticVersion(member)
        audit.append(actor, teamId, userId, "ROLE_CHANGED")
        # nếu có external event: ghi outbox trong transaction

    return memberViewWithNewVersion
~~~

**findByIdAndTenantForUpdate** là ý tưởng khóa bản ghi team trong cùng transaction khi phải giữ bất biến liên quan nhiều membership. Những thay đổi OWNER ở các luồng khác (DELETE, suspend, revoke, chuyển team) cũng phải tuân theo **cùng quy tắc đồng bộ**, nếu không vẫn có race condition.

Nếu backend dùng JPA/Hibernate:

~~~java
@Entity
@Table(
    name = "team_memberships",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_team_user",
        columnNames = {"team_id", "user_id"}
    )
)
class TeamMembership {
    @EmbeddedId
    private TeamMembershipId id;

    @Enumerated(EnumType.STRING)
    private TeamRole role;

    @Version
    private long version;
}
~~~

Đây là **phác thảo schema cho membership hiện hành không xóa mềm**. Nếu cần lưu nhiều lần gia nhập hoặc soft-delete, constraint trên team_id, user_id có thể phải thay bằng unique index chỉ áp dụng cho relation **đang hiệu lực**, hoặc dùng bảng lịch sử riêng. Khả năng partial unique index tùy loại database; chọn một cơ chế đúng với công nghệ triển khai.

### 14.4. Map exception nghiệp vụ sang HTTP

~~~java
@RestControllerAdvice
class RelationApiExceptionHandler {

    @ExceptionHandler(HiddenNotFoundException.class)
    ResponseEntity<ProblemDetail> hidden() {
        return failure(HttpStatus.NOT_FOUND, "Không tìm thấy tài nguyên.");
    }

    @ExceptionHandler(LastOwnerConflictException.class)
    ResponseEntity<ProblemDetail> lastOwner() {
        return failure(
            HttpStatus.CONFLICT,
            "Nhóm phải còn ít nhất một chủ sở hữu."
        );
    }

    @ExceptionHandler(StaleRelationException.class)
    ResponseEntity<ProblemDetail> stale() {
        return failure(
            HttpStatus.PRECONDITION_FAILED,
            "Tài nguyên đã thay đổi; hãy tải lại."
        );
    }

    @ExceptionHandler(MissingPreconditionException.class)
    ResponseEntity<ProblemDetail> requirePrecondition() {
        return failure(
            HttpStatus.PRECONDITION_REQUIRED,
            "Yêu cầu phải gửi If-Match."
        );
    }

    private static ResponseEntity<ProblemDetail> failure(
            HttpStatus status, String detail) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        return ResponseEntity.status(status)
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

Các exception là **kiểu do ứng dụng tự định nghĩa**. Hành vi **401/403** từ Spring Security cần được cấu hình riêng trong security filter và access-denied handler, bảo đảm không làm lộ tài nguyên. Exception optimistic lock từ JPA phải được chuyển thành **412 khi liên quan đến precondition của client**; không được coi mọi lỗi @Version đều là 412 nếu request không có hoặc không dùng điều kiện HTTP. Hãy thống nhất 400/422 cho validation ở controller và service.

### 14.5. Mã hóa vai trò và kết quả nghiệp vụ

Không nên trao toàn bộ role-assignment logic cho một @PreAuthorize đơn giản như hasRole('ADMIN') mà bỏ qua **projectId, tenant, role đích** và ràng buộc không được tự nâng quyền. Có thể dùng method security để thực thi một phần policy, nhưng service vẫn cần các điều kiện nghiệp vụ trong transaction.

Nếu gửi event **MemberAdded** hoặc **RoleChanged** cho hệ thống khác, không gửi event trước khi DB commit. Dùng transactional outbox hoặc cơ chế có bảo đảm tương đương; consumer cần chịu được event lặp và đến muộn.

## 15. Công bố hợp đồng bằng OpenAPI

OpenAPI cần mô tả **resource là quan hệ**, danh tính trong URI, những trường client có thể ghi, điều kiện cập nhật và các tình huống lỗi. Không nên chỉ document request thành công rồi để client tự đoán mã 409 hoặc 412.

Ví dụ rút gọn sử dụng OpenAPI 3.1 cho một phần API membership:

~~~yaml
openapi: 3.1.0
info:
  title: Team Relations API
  version: 1.0.0
paths:
  /v1/teams/{teamId}/members:
    parameters:
      - $ref: "#/components/parameters/teamId"
    get:
      operationId: listTeamMembers
      summary: Liệt kê thành viên được phép xem
      security:
        - bearerAuth: []
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: cursor
          in: query
          schema:
            type: string
      responses:
        "200":
          description: Danh sách thành viên trong phạm vi quyền
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/MemberPage"
        "401":
          description: Thiếu hoặc không có credential hợp lệ
        "403":
          description: Không đủ quyền liệt kê, nếu policy cho phép tiết lộ
        "404":
          description: Team không có hoặc không được phép tiết lộ
    post:
      operationId: addTeamMember
      summary: Tạo membership trong team
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          description: Khóa chống tạo trùng theo hợp đồng dịch vụ
          required: false
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/AddMember"
      responses:
        "201":
          description: Đã tạo membership
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Member"
        "200":
          description: Kết quả đã tồn tại được trả lại khi replay idempotent
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Member"
        "400":
          description: Request sai cú pháp hoặc không hợp lệ
        "401":
          description: Credential không hợp lệ
        "403":
          description: Không được phép thêm thành viên hoặc gán role đích
        "404":
          description: Team không có hoặc bị ẩn
        "409":
          description: Membership trùng hoặc xung đột nghiệp vụ
  /v1/teams/{teamId}/members/{userId}:
    parameters:
      - $ref: "#/components/parameters/teamId"
      - $ref: "#/components/parameters/userId"
    get:
      operationId: getTeamMember
      security:
        - bearerAuth: []
      responses:
        "200":
          description: Membership được phép xem
          headers:
            ETag:
              description: Validator mạnh của representation
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Member"
        "401":
          description: Credential không hợp lệ
        "404":
          description: Membership không có hoặc không được tiết lộ
    patch:
      operationId: changeMemberRole
      summary: Sửa role của membership có điều kiện
      security:
        - bearerAuth: []
      parameters:
        - name: If-Match
          in: header
          required: true
          description: Strong ETag trả về từ lần GET gần nhất
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ChangeRole"
      responses:
        "200":
          description: Membership sau khi đổi role
          headers:
            ETag:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Member"
        "400":
          description: Payload sai
        "401":
          description: Credential không hợp lệ
        "403":
          description: Không được phép gán role đích
        "404":
          description: Membership không có hoặc bị ẩn
        "409":
          description: Vi phạm bất biến nghiệp vụ, ví dụ LAST_OWNER
        "412":
          description: If-Match không khớp với representation hiện tại
        "428":
          description: Thiếu If-Match bắt buộc
    delete:
      operationId: removeTeamMember
      security:
        - bearerAuth: []
      parameters:
        - name: If-Match
          in: header
          required: true
          schema:
            type: string
      responses:
        "204":
          description: Đã loại bỏ membership; không có response body
        "401":
          description: Credential không hợp lệ
        "403":
          description: Không có quyền loại bỏ thành viên
        "404":
          description: Membership không có hoặc bị ẩn
        "409":
          description: Bất biến LAST_OWNER hoặc trạng thái không cho xóa
        "412":
          description: If-Match không khớp
        "428":
          description: Thiếu If-Match bắt buộc
components:
  parameters:
    teamId:
      name: teamId
      in: path
      required: true
      schema:
        type: string
        format: uuid
    userId:
      name: userId
      in: path
      required: true
      schema:
        type: string
        format: uuid
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    AddMember:
      type: object
      additionalProperties: false
      required: [userId, role]
      properties:
        userId:
          type: string
          format: uuid
        role:
          type: string
          enum: [VIEWER, EDITOR, OWNER]
    ChangeRole:
      type: object
      additionalProperties: false
      required: [role]
      properties:
        role:
          type: string
          enum: [VIEWER, EDITOR, OWNER]
    Member:
      type: object
      required: [teamId, userId, role, status, version]
      properties:
        teamId:
          type: string
          format: uuid
        userId:
          type: string
          format: uuid
        role:
          type: string
          enum: [VIEWER, EDITOR, OWNER]
        status:
          type: string
          enum: [ACTIVE, SUSPENDED]
        version:
          type: integer
          format: int64
    MemberPage:
      type: object
      required: [items]
      properties:
        items:
          type: array
          items:
            $ref: "#/components/schemas/Member"
        nextCursor:
          type:
            - string
            - "null"
~~~

Các UUID trong schema là **kiểu được chọn cho bản triển khai minh họa**; ví dụ URI team-42 ở các phần trước là ID giả lập dễ đọc, không phải UUID hợp lệ. Khi áp dụng vào dự án, hãy thay bằng định dạng ID thực tế và kiểm tra thông số OpenAPI khớp DTO/controller. OpenAPI ví dụ chỉ mô tả membership; role assignment và order item cần thêm paths, schemas, constraints riêng.

**Cần thống nhất trước khi phát hành:**

- POST có yêu cầu Idempotency-Key hay chỉ hỗ trợ tùy chọn? Replay trả 201 nguyên bản hay 200 theo chính sách?
- PUT upsert có được hỗ trợ hay chỉ POST + PATCH? Nếu hỗ trợ, công bố 201/200/204 và precondition.
- PATCH dùng **application/json cho DTO riêng** hay **JSON Merge Patch**? Không dùng lẫn hai semantics.
- Scope của ETag là membership, item hay Order aggregate? Client lấy ETag ở đâu?
- Mã 403/404 thể hiện chính sách tiết lộ tài nguyên như thế nào?
- 409 với LAST_OWNER, DUPLICATE_MEMBERSHIP và ORDER_PAID có **problem type/code** nào?
- Cache-Control, pagination, sorting và filter có hành vi nhất quán giữa backend/CDN không?

## 16. Kiểm thử REST API quan hệ với Java/Spring

Thiết kế đúng phải được kiểm chứng ở **HTTP contract**, **database invariant** và **bảo mật**. Chỉ test controller trả 201 khi POST thành công chưa chứng minh được tránh duplicate, mất cập nhật hoặc leo thang quyền.

### 16.1. Ma trận kiểm thử bắt buộc

| Mã test | Tình huống | Kỳ vọng |
|---|---|---|
| M01 | OWNER thêm một user chưa có trong team | 201 + Location + membership đúng |
| M02 | Gửi lại cùng POST với **Idempotency-Key** và payload giống | Trả kết quả theo hợp đồng replay; DB chỉ có một membership |
| M03 | Cùng key nhưng payload khác | 409 hoặc lỗi được tài liệu hóa; không sửa dữ liệu cũ |
| M04 | Hai POST song song cùng teamId/userId không có key | Constraint ngăn tạo hai membership hiện hành |
| M05 | Người ngoài tenant đọc membership | 404 trung tính nếu policy che giấu |
| M06 | VIEWER tự đổi role thành OWNER | 403 hoặc 404 tùy visibility policy; DB không đổi |
| M07 | OWNER đổi role hợp lệ với If-Match đang đúng | 200 + ETag mới; phiên bản tăng |
| M08 | PATCH với If-Match đã cũ | 412; không ghi đè role vừa sửa |
| M09 | PATCH không gửi If-Match khi policy bắt buộc | 428 |
| M10 | Hai OWNER đồng thời cố hạ quyền hoặc rời team | Không giao dịch nào khiến team còn 0 OWNER |
| M11 | DELETE membership hợp lệ | 204 không body; user account vẫn tồn tại |
| M12 | DELETE membership không thuộc tenant | Không thay đổi dữ liệu; không lộ thông tin qua response |
| M13 | API role assignment: ADMIN thường cố gán role vượt quyền | Từ chối, không tạo assignment |
| M14 | Revoke một assignment nhưng user còn assignment khác | Quyền hiệu lực được tính theo chính sách, không xóa nhầm assignment khác |
| I01 | POST item vào order DRAFT | 201; amount được **server tính**, không tin giá client |
| I02 | PATCH item quantity = 3 với ETag cũ | 412; không làm sai total |
| I03 | PATCH item thuộc order B qua URI order A | 404/ẩn, không đổi item |
| I04 | PATCH/DELETE item khi order đã PAID | 409 hoặc trạng thái theo hợp đồng; không thay đổi hóa đơn lịch sử |
| I05 | Hai client sửa hai item khác nhau cùng order | Tổng tiền cuối và version Order nhất quán |
| C01 | GET members với cursor/filter của tenant khác | Cursor bị từ chối; không lộ count hoặc items |
| C02 | 401/403/404 cho cùng route với các principal khác nhau | Chính sách authn/authz/visibility nhất quán |
| C03 | GET/HEAD cùng membership | Trạng thái và header tương thích; HEAD không có body |

### 16.2. Ví dụ MockMvc có JWT giả lập

Giả sử test fixture đã tạo team và hai membership hợp lệ, service/repository thật trong cơ sở dữ liệu test. Mã sau là **phác thảo kiểm thử tích hợp**; các UUID, principal, helper seed và import cần được cung cấp trong test project.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MembershipApiContractTest {

    @Autowired MockMvc mvc;

    UUID teamId;
    UUID memberId;

    @Test
    void patchRejectsStaleEtag() throws Exception {
        mvc.perform(
                patch("/v1/teams/{t}/members/{u}", teamId, memberId)
                    .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-a")))
                    .header("If-Match", "\"membership-v0\"")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"role\":\"EDITOR\"}")
            )
            .andExpect(status().isPreconditionFailed());
    }

    @Test
    void patchWithoutIfMatchRequiresPrecondition() throws Exception {
        mvc.perform(
                patch("/v1/teams/{t}/members/{u}", teamId, memberId)
                    .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-a")))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"role\":\"EDITOR\"}")
            )
            .andExpect(status().isPreconditionRequired());
    }

    @Test
    void foreignTenantMustNotSeeMembership() throws Exception {
        mvc.perform(
                get("/v1/teams/{t}/members/{u}", teamId, memberId)
                    .with(jwt().jwt(j -> j.claim("tenant_id", "tenant-b")))
            )
            .andExpect(status().isNotFound())
            .andExpect(header().string(
                "Cache-Control", containsString("no-store")
            ));
    }
}
~~~

**jwt() của spring-security-test** tạo principal trong test mà không tự kiểm chứng issuer, audience, chữ ký hoặc expiry của token thật. Cần bổ sung bài kiểm tra Resource Server với token sai/hết hạn, thiếu quyền và claim bất thường ở môi trường tích hợp. Fixture phải bảo đảm actor có **đúng quyền** cần thiết trong các test 412/428, nếu không lỗi 403 sẽ xảy ra trước khi kiểm tra ETag và làm test không đánh giá được điều cần kiểm.

### 16.3. Kiểm thử cạnh tranh và side effect

Một bài test đồng thời hữu ích là tạo team có **hai OWNER**, sau đó mở hai transaction làm cả hai yêu cầu hạ quyền cùng lúc. Dùng barrier/concurrency harness ở tầng service hoặc database thực phù hợp để tăng xác suất tái hiện race. Kỳ vọng cuối cùng có **ít nhất một OWNER** và một yêu cầu bị từ chối/đợi theo thiết kế. Test chỉ chạy tuần tự hai lần **không đủ** để chứng minh invariant nguyên tử.

Đối với idempotency:

1. Gửi POST tạo item với key K; giả lập **mất response sau commit**.
2. Gửi lại POST cùng key K, cùng request body.
3. Xác nhận chỉ có một tác động nghiệp vụ và response đúng hợp đồng.
4. Gửi key K với body khác, xác nhận lỗi và không thay đổi item cũ.
5. Gửi **key khác** cùng product với chính sách cho phép nhiều line để xác nhận hệ thống phân biệt ý định khác nhau.

Khi có event downstream, kiểm thử consumer lặp và outbox để xác minh **không gửi email mời, thu tiền hoặc ghi audit nghiệp vụ nhiều lần** ngoài thiết kế. Audit log có thể ghi nhiều lần **request đến** cho mục đích an ninh, nhưng không được nhầm với nhiều lần **membership được tạo**.

## 17. Bài tập thiết kế API quan hệ

### Bài tập A — Quản lý thành viên của nhóm

**Yêu cầu:** một ứng dụng quản lý công việc có TEAM, USER và MEMBERSHIP. Một nhóm có tối thiểu một OWNER, tối đa 200 ACTIVE members. Người mới phải **chấp nhận lời mời** mới được tham gia. OWNER có thể mời người, nâng role thành EDITOR và gỡ thành viên. Người ngoài team không được suy ra team có tồn tại hay không.

Hãy thiết kế:

1. URI và phương thức để **mời**, **xem trạng thái lời mời**, **chấp nhận**, **xem danh sách thành viên**, **đổi role** và **gỡ thành viên**.
2. Mã trạng thái khi lời mời đã được gửi nhưng chưa chấp nhận, khi bị hết hạn, khi người ngoài tenant truy cập team.
3. Cách ngăn **hai OWNER đồng thời tự xóa** hoặc hạ quyền.
4. Chính sách pagination và cache của danh sách member.

**Phương án tham khảo:**

| Hành động | URI | Method | Hành vi |
|---|---|---|---|
| Tạo lời mời | /v1/teams/{id}/invitations | POST | 201 + Location của invitation, trạng thái PENDING |
| Xem lời mời | /v1/teams/{id}/invitations/{invitationId} | GET | 200 cho người được quyền xem, 404 khi bị ẩn |
| Chấp nhận | /v1/invitations/{id}/acceptances | POST | 201/200 theo hợp đồng khi chấp nhận và tạo membership; idempotency bảo vệ retry |
| Xem thành viên | /v1/teams/{id}/members | GET | 200 với cursor/limit sau khi xác thực và kiểm tra team |
| Đổi role | /v1/teams/{id}/members/{userId} | PATCH | 200 + ETag; 412 nếu version cũ, 409 nếu phá invariant |
| Gỡ thành viên | /v1/teams/{id}/members/{userId} | DELETE | 204; chỉ xóa quan hệ, không xóa USER |

**Lời mời PENDING** không đồng nghĩa ACTIVE membership, vì vậy không trả member ACTIVE ngay sau POST invitation. Invitation hết hạn trả trạng thái nghiệp vụ phù hợp cho người có quyền, còn việc thực hiện acceptance có thể trả 409 hoặc 422 theo hợp đồng thay vì lén khôi phục lời mời. Người ngoài tenant nhận 404 trung tính tại resource được bảo vệ theo chính sách ẩn.

Để bảo vệ OWNER cuối cùng, đồng bộ thao tác thay đổi role, suspend, remove ở **cấp team**, chẳng hạn transaction khóa bản ghi team và kiểm tra số ACTIVE OWNER trước khi commit. Danh sách member dùng cursor/keyset với sort ổn định, chỉ xét scope team được phép xem; **Cache-Control: no-store** nếu có thông tin nội bộ.

### Bài tập B — Quyền theo dự án

**Yêu cầu:** người dùng có thể có cả REPORT_VIEWER và DEPLOYER trong project A nhưng chỉ REPORT_VIEWER trong project B. Chỉ PROJECT_OWNER mới được gán DEPLOYER; có thể thu hồi từng role mà không đụng role khác.

Câu hỏi:

1. Dùng một trường role trong USER có đúng không?
2. Chọn composite URI theo user+role hay server-generated assignmentId?
3. Khi thu hồi một assignment, có thể kết luận người đó mất mọi quyền đọc report không?
4. Một admin project A có được gán quyền cho project B nếu biết ID?

**Lời giải:** role toàn cục trên USER không biểu đạt quyền **theo project**. Dùng ROLE_ASSIGNMENT trong scope project; nếu cặp projectId/principalId/roleKey là duy nhất và ổn định thì composite URI có thể dùng, nhưng assignmentId riêng linh hoạt hơn khi lưu lịch sử/hiệu lực. Thu hồi một assignment **không chứng minh** mất quyền nếu người dùng còn các nguồn cấp quyền khác. Phải kiểm tra quyền thực hiện với **projectId được xác thực**, không chỉ tin URI hoặc biết assignmentId.

### Bài tập C — Thêm mặt hàng trong đơn nháp

**Yêu cầu:** mỗi order DRAFT cho phép một dòng với mỗi product/variant, quantity từ 1 đến 99. Server tính giá; một đơn có thể được hai cửa sổ trình duyệt sửa cùng lúc. Khi order PAID không được sửa item.

Thiết kế REST và cách xử lý:

1. Client thêm product P hai lần do timeout sau khi request đầu thành công.
2. Client A và B cùng đọc quantity 2, A đổi thành 3, B đổi thành 5.
3. Client đổi quantity thành 0 hoặc -3.
4. Client gửi PATCH quantity cho item ở order của người khác.
5. Client gửi unitPrice tự chọn thấp hơn giá hiện hành.

**Phương án tham khảo:**

- **POST /v1/orders/{orderId}/items** nhận productId, variantId, quantity; dùng **Idempotency-Key** để nhận biết request bị lặp và constraint duy nhất theo order/product/variant để bảo vệ mô hình một dòng.
- **PATCH /v1/orders/{orderId}/items/{itemId}** nhận quantity tuyệt đối và **If-Match**; B dùng version cũ được trả 412, tải lại và quyết định có sửa tiếp. Transaction cập nhật cả line item và tổng tiền ở cấp Order aggregate.
- Quantity ngoài 1–99 trả 422 hoặc 400 theo hợp đồng; **quantity = 0** không tự động hiểu là xóa nếu API chỉ nhận 1–99, client nên gọi DELETE. Nếu nghiệp vụ muốn coi 0 là xóa, phải công bố rõ.
- Item ngoài order/tenant được ẩn bằng 404; không cho cross-order update.
- Server không nhận unitPrice/lineTotal như trường có thể ghi; tự xác định giá/thuế/giảm giá và kiểm soát tính toàn vẹn.
- Khi Order PAID, trả 409 cho sửa item và hướng người dùng đến luồng thay đổi/trả hàng riêng nếu nghiệp vụ có.

### Câu hỏi tự kiểm tra nhanh

**1.** POST /teams/42/members với payload userId=7 có nhất thiết tạo relation mới mỗi lần gọi?  
**Trả lời:** không; hành vi phụ thuộc unique constraint, idempotency key và hợp đồng duplicate. POST không mặc định idempotent.

**2.** DELETE /teams/42/members/7 có xóa account USER 7?  
**Trả lời:** không; URI thể hiện xóa quan hệ membership của user đó với team.

**3.** Client gửi PATCH role với If-Match cũ và server phát hiện version khác, mã nào phản ánh tiền điều kiện không đạt?  
**Trả lời:** 412 Precondition Failed.

**4.** Nếu last OWNER còn lại muốn rời team, nên trả 404 hay 409?  
**Trả lời:** 409 Conflict là phù hợp khi caller có quyền biết resource, nhưng bất biến nghiệp vụ cấm thực hiện.

**5.** Có thể dùng 401 thay mọi 403 và 404?  
**Trả lời:** không. 401 xử lý thiếu/không hợp lệ xác thực; 403 xử lý bị cấm thao tác; 404 có thể được dùng để ẩn resource ngoài phạm vi.

**6.** Hai order item khác nhau có ETag riêng là đủ bảo đảm order.total luôn đúng?  
**Trả lời:** chưa đủ; cần bảo vệ aggregate Order và cập nhật tổng tiền nhất quán trong transaction hoặc cơ chế tương đương.

## 18. Những phản mẫu thiết kế thường gặp

| Phản mẫu | Rủi ro | Cách cải thiện |
|---|---|---|
| Xem membership là một mảng userIds không có danh tính | Khó có role, trạng thái, version, audit | Model membership thành resource khi có vòng đời riêng |
| POST /users/{id}/makeAdmin cho bất kỳ client | Endpoint động từ mơ hồ, dễ tự nâng quyền | Role assignment hoặc membership role với policy rõ |
| Xóa membership bằng DELETE /users/{id} | Có thể xóa sai tài khoản toàn cục | DELETE URI relation trong team |
| PATCH toàn bộ TEAM để đổi một membership | Ghi đè danh sách do sửa đồng thời, payload lớn | PATCH relation riêng với ETag |
| Không có unique constraint cho cặp team/user | Retry/race tạo hai membership ACTIVE | Unique constraint phù hợp, transaction, idempotency |
| Gán OWNER dựa vào role client tự gửi | Privilege escalation | Kiểm tra caller, role đích, scope trong service |
| Chỉ dùng @Version cho từng membership để giữ ít nhất một OWNER | Hai hàng OWNER khác nhau vẫn có thể bị hạ đồng thời | Đồng bộ invariant ở cấp team |
| Đọc order item bằng itemId nhưng không kiểm tra orderId | BOLA/IDOR, có thể sửa item của người khác | Truy vấn orderId + itemId + scope hợp lệ |
| Cho client sửa unitPrice/total | Gian lận giá hoặc total không nhất quán | Tính tại server, snapshot theo nghiệp vụ |
| POST item tự tăng quantity khi client retry | Quantity tăng hai lần | Idempotency-Key hoặc contract PUT absolute state |
| Trả 200 khi thay đổi quyền đã bị từ chối | Client hiểu sai kết quả, mất khả năng quan sát | Mã lỗi 403/409/412/422 nhất quán |
| Trả 204 kèm body JSON | Vi phạm semantics của 204 | 204 không body; dùng 200 nếu cần representation |
| Dùng If-Match nhưng UPDATE không điều kiện | Lost update vẫn xảy ra | So sánh version tại thời điểm ghi DB |
| Trả 403 cho ID tồn tại ngoài tenant, 404 cho ID không tồn tại | Lộ ID hợp lệ của tenant khác | Chính sách ẩn 404 chung khi phù hợp |
| Cache permission/role assignment như nội dung công khai | Quyền cũ còn hiệu lực hoặc rò rỉ giữa tenant | Cache-Control và invalidation theo scope/quyền |
| Thêm URI lồng 6–7 cấp cho mọi relation | Đường dẫn khó quản lý, cột ID lặp, tài nguyên độc lập bị phụ thuộc giả | URI theo scope cần thiết hoặc resource có ID riêng |

## 19. Checklist thiết kế và tài liệu tham khảo

### Checklist trước khi chốt hợp đồng API

- [ ] Đã xác định **entity gốc, association resource, owner/tenant và scope** của từng quan hệ.
- [ ] URI định danh chính xác **relation**; DELETE relation không vô tình xóa entity hai đầu.
- [ ] Chọn **composite key hay relation ID riêng** dựa trên nghiệp vụ và lịch sử.
- [ ] Dùng GET/POST/PUT/PATCH/DELETE theo semantics; công bố 201 Location, 200, 204, 202 khi thích hợp.
- [ ] POST tạo relation có chính sách **duplicate, Idempotency-Key và unique constraint**.
- [ ] Nếu hỗ trợ PUT upsert, đã định nghĩa **full replacement**, điều kiện tạo và status khi replay.
- [ ] PATCH nêu rõ **media type, trường được sửa, null/absent và ETag**; không nhầm JSON tùy chỉnh với Merge Patch.
- [ ] DELETE và PATCH có bảo vệ **owner cuối cùng, order đã chốt và trạng thái workflow**.
- [ ] Kiểm tra **parent + relation + target** trong phạm vi tenant, principal và role đích.
- [ ] Không cho **mass assignment, tự nâng role, thay đổi giá/tổng tiền do client gửi**.
- [ ] Đặt **transaction/locking đúng ranh giới aggregate** để chống race và lost update.
- [ ] Thiết kế 400/401/403/404/409/412/422/428 và **application/problem+json** nhất quán.
- [ ] Có pagination/filter/sort hợp lệ và không lộ count, cursor, data của tenant khác.
- [ ] Cache-Control, invalidation, quyền hiệu lực và khả năng thu hồi role được cân nhắc.
- [ ] OpenAPI mô tả resource schema, header điều kiện, status và trường chỉ đọc.
- [ ] Test đầy đủ positive, negative, duplicate/retry, concurrent update, cross-tenant và side effect.
- [ ] Audit, metrics, trace, rate limit và reconciliation đủ để vận hành, không làm rò dữ liệu nhạy cảm.

### Tài liệu kỹ thuật để đào sâu

- **RFC 9110 — HTTP Semantics:** GET, POST, PUT, DELETE, 201/204, ETag, If-Match, If-None-Match, 409, 412. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- **RFC 5789 — PATCH Method for HTTP:** semantics của PATCH, ví dụ và điều kiện áp dụng. [RFC 5789](https://www.rfc-editor.org/rfc/rfc5789)
- **RFC 7396 — JSON Merge Patch:** khác biệt giữa trường vắng và null. [RFC 7396](https://www.rfc-editor.org/rfc/rfc7396)
- **RFC 9457 — Problem Details for HTTP APIs:** định dạng lỗi có cấu trúc. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
- **RFC 6585 — Additional HTTP Status Codes:** 428 Precondition Required và 429 Too Many Requests. [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585)
- **OpenAPI Specification 3.1:** mô tả schema, path, header, security và response. [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)

**Điểm cốt lõi:** quan hệ như **thành viên, quyền và mặt hàng** thường có danh tính, trạng thái, quy tắc và rủi ro riêng. Thiết kế chúng như resource có hợp đồng rõ ràng giúp client thao tác nhất quán bằng HTTP, server bảo vệ được quyền và bất biến nghiệp vụ, và cả hệ thống chống chịu tốt hơn với retry, cạnh tranh đồng thời và thay đổi theo thời gian.
