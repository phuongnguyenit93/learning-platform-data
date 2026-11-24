# SCIM User trong provisioning và vòng đời danh tính IAM

## 1. SCIM User là gì?

**SCIM User** là tài nguyên biểu diễn một người dùng trong **System for Cross-domain Identity Management (SCIM)**. SCIM cung cấp mô hình dữ liệu và giao diện HTTP tiêu chuẩn để một hệ thống quản lý danh tính gửi các thay đổi về người dùng tới ứng dụng hoặc dịch vụ đích mà không cần mỗi tích hợp tự phát minh một API riêng.

Ví dụ, khi Lan gia nhập tổ chức, IAM/IGA có thể tạo tài khoản cho Lan trong hệ thống quản lý dự án qua **POST /Users**. Khi Lan chuyển bộ phận, IAM cập nhật các thuộc tính cần thiết. Khi Lan rời tổ chức, IAM có thể gửi thay đổi **active=false** để vô hiệu hóa tài khoản theo khả năng và chính sách của hệ thống đích.

SCIM User là **bản ghi provisioning**, không phải một phiên đăng nhập, OAuth access token, bằng chứng identity proofing hoặc một vai trò nghiệp vụ. Một User có thể tồn tại trong ứng dụng nhưng chưa được quyền đăng nhập; ngược lại, một User được đánh dấu inactive có thể còn các phiên/token riêng nếu ứng dụng không thu hồi chúng.

Bài này thuộc chương **SCIM provisioning** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, với mục tiêu quản trị danh tính theo **Joiner–Mover–Leaver (JML)**. Nội dung liên hệ SCIM với **nguồn nhân sự, IdP/SSO, OAuth/OIDC, RBAC/ABAC, service account, đối soát và giảm quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học cần có khả năng:

1. Nhận biết SCIM 2.0, hai vai trò **provisioning client** và **service provider**, và tài nguyên **User**.
2. Phân biệt **id, externalId, userName** và các thuộc tính định danh khác.
3. Hiểu cách tạo, đọc, lọc, cập nhật, PATCH, vô hiệu hóa và xử lý xóa User.
4. Tránh tạo tài khoản trùng hoặc cập nhật nhầm khi retry, đổi email và tái gia nhập.
5. Liên kết SCIM User với vòng đời **Joiner–Mover–Leaver**, entitlement và phiên truy cập thực tế.
6. Áp dụng bảo mật connector, phân loại lỗi, đối soát và kiểm toán đáng tin cậy.

## 2. SCIM 2.0 dựa trên những chuẩn và vai trò nào?

Hai tài liệu nền tảng thường được nhắc tới là:

- **RFC 7643 – SCIM Core Schema:** định nghĩa các tài nguyên, thuộc tính, kiểu dữ liệu, đặc điểm như mutability, uniqueness và các schema mở rộng.
- **RFC 7644 – SCIM Protocol:** định nghĩa giao thức HTTP để tạo, đọc, cập nhật, xóa, tìm kiếm và quản lý tài nguyên.

SCIM mô tả các **khả năng có thể được công bố** bởi nhà cung cấp dịch vụ. Vì vậy không nên giả định mọi phần mềm có ghi “hỗ trợ SCIM” đều hỗ trợ PATCH, Bulk, filtering, sorting, versioning hoặc mọi thuộc tính theo cách giống nhau.

### Hai vai trò chính

| Vai trò | Chức năng | Ví dụ |
|---|---|---|
| **Provisioning Client** | Tạo yêu cầu SCIM, đồng bộ dữ liệu và theo dõi kết quả | IAM/IGA, IdP provisioning connector |
| **Service Provider (SP)** | Cung cấp SCIM API, lưu và quản lý User/Group ở hệ thống đích | Ứng dụng SaaS hoặc dịch vụ nội bộ |
| **Authoritative Source** | Nguồn xác định trạng thái nhân sự/quan hệ hợp lệ | HRIS, hệ thống hợp đồng |
| **Identity Orchestrator** | Tính desired state, điều phối JML, phê duyệt và retry | IAM/IGA |
| **Resource Owner/Business Owner** | Quyết định nhu cầu tài khoản và quyền nghiệp vụ | Chủ ứng dụng hoặc người quản lý |
| **Auditor/Reconciliation** | Xác minh trạng thái thực tế, kiểm tra sai lệch | IGA, security và nhóm kiểm toán |

Ở một số tổ chức, IdP cũng là provisioning client; ở nơi khác, IGA điều phối trực tiếp nhiều connector. **Nguồn HRIS không nhất thiết gọi SCIM trực tiếp**, mà có thể phát sự kiện JML cho IAM/IGA xử lý.

### Sơ đồ tổng quan

~~~mermaid
flowchart TD
    H[HRIS / Contract source] --> I[IAM / IGA orchestration]
    P[RBAC / ABAC / Approval] --> I
    I -->|SCIM /Users và /Groups| S[Service Provider / SaaS]
    I --> D[IdP / Directory]
    U[Người dùng] -->|SSO SAML hoặc OIDC| D
    D -->|Federation authentication| S
    S --> R[Observed accounts và entitlements]
    R --> I
    I --> A[Audit / Reconciliation]
~~~

**SCIM provisioning** thay đổi bản ghi user/group. **SAML/OIDC SSO** phục vụ xác thực liên kết. **Authorization** còn phải được ứng dụng hoặc policy engine quyết định. Ba lớp cần phối hợp nhưng không thể thay thế nhau.

## 3. Tài nguyên User và URI schema cốt lõi

SCIM 2.0 định nghĩa schema User cốt lõi với URI:

~~~text
urn:ietf:params:scim:schemas:core:2.0:User
~~~

Một tài nguyên User có thể mang thêm các **schema extension** được service provider hỗ trợ. Trường **schemas** là danh sách URI mô tả schema đang áp dụng; không phải một nhãn tùy tiện do client tự tạo.

### Các nhóm trường quan trọng

| Thuộc tính | Ý nghĩa | Ghi chú khi đồng bộ |
|---|---|---|
| **schemas** | Danh sách URI schema áp dụng | Core User URI thường có mặt trong User resource |
| **id** | Định danh tài nguyên do service provider tạo | Read-only, dùng khi gọi URL của User ở đích |
| **externalId** | ID do provisioning client định nghĩa để tham chiếu nguồn | Không mặc định duy nhất toàn hệ thống đích |
| **userName** | Định danh đăng nhập của User theo schema | Thuộc tính core bắt buộc; cần quy tắc chuẩn hóa và uniqueness ở đích |
| **name** | Cấu trúc tên người, gồm các thành phần như givenName/familyName | Không dùng tên hiển thị làm khóa nối duy nhất |
| **displayName** | Tên dễ đọc trong UI | Có thể thay đổi theo tên người và chính sách |
| **emails** | Danh sách email dạng multi-valued | Có thể có type, primary; không tự chứng minh email đã xác minh |
| **phoneNumbers** | Số điện thoại theo kiểu dữ liệu được hỗ trợ | PII cần tối thiểu hóa |
| **active** | Giá trị boolean cho trạng thái active của User | Ngữ nghĩa deactivation thực tế tùy service provider |
| **groups** | Quan hệ nhóm của User được biểu diễn ở User | Trong core User schema là thuộc tính read-only |
| **roles** | Danh sách vai trò theo schema | Không giả định mọi app dùng roles để cấp quyền thực |
| **entitlements** | Danh sách entitlement theo schema | Ngữ nghĩa cụ thể tùy ứng dụng và khả năng triển khai |
| **meta** | Metadata do service provider quản lý | Có thể gồm resourceType, created, lastModified, location, version |
| **password** | Thuộc tính phục vụ thay đổi password khi dịch vụ hỗ trợ | Write-only trong schema; không phải mặc định cần dùng trong provisioning SSO |

**Không đồng nhất displayName/email với danh tính gốc.** Một hệ thống có thể đổi tên Lan hoặc cấp lại email mà tài nguyên User vẫn là cùng một đối tượng theo **id**.

### Các đặc tính thuộc tính

SCIM Core Schema còn mô tả những thuộc tính như **mutability** (readOnly, readWrite, immutable, writeOnly), **returned**, **required**, **uniqueness** và **caseExact**. Tích hợp nên tôn trọng những ràng buộc này.

Ví dụ, **id** do server tạo; **groups** của User là thông tin dẫn xuất và không nên được cập nhật như một thuộc tính User writable nếu nhà cung cấp tuân theo core schema. Thay đổi thành viên nhóm thường đi qua **Group.members** hoặc cơ chế provisioning quyền do ứng dụng cung cấp.

## 4. Ví dụ JSON một SCIM User

Dưới đây là một request tạo User đơn giản. Các giá trị minh họa không phải dữ liệu thật:

~~~http
POST /scim/v2/Users HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Content-Type: application/scim+json
Accept: application/scim+json
~~~

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "person-2046",
  "userName": "lan.nguyen@example.org",
  "name": {
    "givenName": "Lan",
    "familyName": "Nguyen",
    "formatted": "Nguyen Lan"
  },
  "displayName": "Nguyen Lan",
  "emails": [
    {
      "value": "lan.nguyen@example.org",
      "type": "work",
      "primary": true
    }
  ],
  "active": true
}
~~~

Server có thể trả **HTTP 201 Created** và một tài nguyên đã được gán **id**. Ví dụ response rút gọn:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "id": "9a03b8c7",
  "externalId": "person-2046",
  "userName": "lan.nguyen@example.org",
  "displayName": "Nguyen Lan",
  "active": true,
  "meta": {
    "resourceType": "User",
    "created": "2026-11-23T09:15:00Z",
    "lastModified": "2026-11-23T09:15:00Z",
    "location": "https://app.example.org/scim/v2/Users/9a03b8c7"
  }
}
~~~

Ví dụ response nhằm thể hiện **id** và **meta**; một response đầy đủ thực tế còn chịu ràng buộc về các thuộc tính trả về và schema của service provider. Không xem việc tạo User thành công là bằng chứng MFA đã enroll hoặc người dùng đã có đủ entitlement trong ứng dụng.

### Lưu ý về endpoint

Đường dẫn **/scim/v2/Users** ở ví dụ chỉ là base URL giả định. Chuẩn quy định đường dẫn tài nguyên như **/Users** tương đối với **SCIM service endpoint** do nhà cung cấp công bố; không phải mọi sản phẩm đặt tiền tố **/scim/v2** giống nhau.

## 5. Phân biệt id, externalId và userName

Đây là phần quan trọng nhất để tránh **tạo trùng, liên kết sai tài khoản và bỏ sót Leaver**.

| Trường | Bên tạo/kiểm soát | Dùng trong thực tế | Điều cần tránh |
|---|---|---|---|
| **id** | Service provider | Định danh tài nguyên ở đích, ví dụ /Users/{id} | Tự đặt id trong POST như thể client sở hữu |
| **externalId** | Provisioning client | Nối tài nguyên với định danh nguồn/IGA | Cho rằng mặc định unique toàn tenant hoặc giữa mọi client |
| **userName** | Theo dữ liệu được quản lý và quy tắc của đích | Định danh đăng nhập/lookup theo chính sách | Chỉ dựa userName để xác định một người trong mọi vòng đời |
| **personId/identityId** | HRIS/IAM, ngoài schema User nếu không được ánh xạ | Khóa chủ thể bền vững | Dùng email thay cho ID nguồn ổn định |
| **relationshipId** | Nguồn nhân sự/hợp đồng | Phân biệt quan hệ nhân viên/nhà thầu đang cấp quyền | Xóa nhầm mọi quyền khi chỉ một quan hệ kết thúc |

**id là server-assigned và thường phải được lưu trong bảng mapping IAM ↔ target.** Khi tạo User thành công, client nên lưu id do server trả về và liên kết với identity ID đáng tin cậy.

**externalId** rất hữu ích để đối chiếu khi chưa biết id đích, nhưng theo schema **không có bảo đảm uniqueness toàn hệ thống** như userName. Có thể nhiều provisioning client dùng không gian externalId khác nhau. Nếu lọc theo externalId mà có nhiều bản ghi khớp, cần **cách ly và điều tra**, không tự chọn bản đầu tiên.

### Ví dụ thay email

Lan đổi tên/email sau khi kết hôn. IAM vẫn lưu:

~~~text
identityId (IAM):     person-2046
externalId (SCIM):    person-2046
targetUserId (SCIM):  9a03b8c7
old userName:         lan.nguyen@example.org
new userName:         lan.tran@example.org
~~~

Nếu ứng dụng đích cho cập nhật userName hợp lệ, IAM cập nhật **User 9a03b8c7**, không tạo một User mới chỉ vì email/userName thay đổi.

### Ví dụ rehire

Người từng nghỉ có thể được tuyển lại với **quan hệ công việc mới**. Tổ chức phải quyết định có tái dùng bản ghi User cũ hay tạo mới theo policy và dữ liệu đã lưu, nhưng **không tự phục hồi mật khẩu, token, phiên và quyền cũ**. Việc liên kết phải dựa trên identity/relationship được xác minh và quy trình Joiner hiện hành.

## 6. Đọc User: GET /Users và GET /Users/{id}

SCIM API cho phép đọc danh sách User hoặc một User cụ thể theo khả năng endpoint.

### Đọc theo id của service provider

~~~http
GET /scim/v2/Users/9a03b8c7 HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Accept: application/scim+json
~~~

Khi có **id** đã xác minh, GET theo id giúp tránh rủi ro tra cứu bằng thuộc tính đổi được. Nếu server trả 404, cần xác định tài nguyên đã bị xóa, ID cũ, sai tenant hay connector đang gọi sai endpoint; **không tự lập tức tạo User mới**.

### Lấy danh sách User

~~~http
GET /scim/v2/Users?startIndex=1&count=100 HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Accept: application/scim+json
~~~

SCIM dùng **startIndex bắt đầu từ 1**, còn **count** yêu cầu số lượng bản ghi muốn lấy, tùy giới hạn server. Để đối soát đầy đủ, client phải kiểm tra phân trang và số bản ghi được trả thực tế thay vì chỉ đọc trang đầu.

Response danh sách sử dụng schema **ListResponse**. Ví dụ minh họa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:ListResponse"
  ],
  "totalResults": 2,
  "startIndex": 1,
  "itemsPerPage": 2,
  "Resources": [
    {
      "schemas": [
        "urn:ietf:params:scim:schemas:core:2.0:User"
      ],
      "id": "9a03b8c7",
      "userName": "lan.nguyen@example.org",
      "active": true
    },
    {
      "schemas": [
        "urn:ietf:params:scim:schemas:core:2.0:User"
      ],
      "id": "12d67a90",
      "userName": "minh.pham@example.org",
      "active": false
    }
  ]
}
~~~

**totalResults** thể hiện tổng số kết quả phù hợp truy vấn; **itemsPerPage** là số phần tử trong trang được trả. Không nên giả định hai giá trị luôn bằng nhau.

### Giới hạn dữ liệu khi phân trang

Trên hệ thống có thay đổi liên tục, các trang có thể phản ánh thời điểm khác nhau nếu dịch vụ không hỗ trợ snapshot nhất quán. Cần ghi nhận thời điểm đối soát, kiểm tra completeness và xử lý biến động khi đang đọc để không kết luận sai rằng account biến mất hoặc thừa.

## 7. Tìm User bằng SCIM filter

SCIM Protocol định nghĩa cú pháp **filter** cho các truy vấn được hỗ trợ. Một ví dụ tìm theo externalId:

~~~text
GET /scim/v2/Users?filter=externalId%20eq%20%22person-2046%22
~~~

Sau giải mã URL, biểu thức filter là:

~~~text
externalId eq "person-2046"
~~~

Một ví dụ khác theo userName:

~~~text
userName eq "lan.nguyen@example.org"
~~~

Tính năng filtering, thuộc tính được phép filter và hành vi case matching phải được kiểm tra ở **ServiceProviderConfig/schema** và tài liệu dịch vụ. **Không được tự giả định mọi nhà cung cấp hỗ trợ filter trên mọi thuộc tính**.

### Các toán tử phổ biến

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| **eq** | Bằng | userName eq "lan.nguyen@example.org" |
| **ne** | Không bằng | active ne false |
| **co** | Chứa | userName co "@example.org" |
| **sw** | Bắt đầu bằng | userName sw "lan." |
| **pr** | Thuộc tính tồn tại | externalId pr |
| **gt/ge/lt/le** | So sánh giá trị phù hợp kiểu dữ liệu | meta.lastModified gt "2026-11-01T00:00:00Z" |

Không phải toán tử nào cũng thích hợp với mọi thuộc tính hoặc được server triển khai. Với dữ liệu multi-valued như emails, SCIM còn có cú pháp **valuePath** để lọc phần tử theo điều kiện, nhưng client cần tuân thủ schema và khả năng đích thay vì tự dựng truy vấn không kiểm chứng.

### Chống filter injection và lookup nhầm

- Mã hóa URL và escape giá trị theo cú pháp SCIM filter; không ghép chuỗi trực tiếp từ đầu vào người dùng thiếu kiểm tra.
- Giới hạn lookup vào **tenant/endpoint** đã xác định đúng.
- Nếu filter trả **0 kết quả**, không kết luận chắc chắn User chưa tồn tại khi hệ thống còn thiếu coverage hoặc khác quy tắc matching.
- Nếu filter trả **nhiều kết quả**, không lấy phần tử đầu tiên làm chuẩn; mở finding trùng mapping.
- Sau lookup, kiểm tra **id, externalId, userName, nguồn và quan hệ** trước khi cập nhật hoặc thu hồi.

## 8. Tạo User với POST: Joiner cần idempotency

Khi nhận sự kiện **Joiner**, IAM thường chuẩn bị tài khoản trước hoặc ngay ngày hiệu lực. Trước khi gửi POST, cần kiểm tra:

1. **Nguồn có thẩm quyền:** HRIS/contract source đã xác minh người và quan hệ đúng chưa?
2. **Điều kiện tạo:** policy có cho chuẩn bị trước ngày làm việc không? Account có phải ở trạng thái chưa hoạt động không?
3. **Định danh ổn định:** client biết identityId/externalId và quy tắc userName chưa?
4. **Mapping hiện có:** target User id đã tồn tại hoặc có khả năng rejoiner không?
5. **Schema:** thuộc tính bắt buộc và kiểu dữ liệu được service provider chấp nhận không?
6. **Quyền connector:** client có được phép tạo User trong đúng tenant/ứng dụng không?
7. **Đồng bộ về sau:** sau POST, đã xác minh và lưu id do server trả về chưa?

### Timeout sau POST: tình huống nguy hiểm

Giả sử client gửi POST, server **đã tạo User**, nhưng response bị mất do kết nối timeout. Nếu client retry POST ngay, kết quả có thể là **account trùng** hoặc lỗi **409 Conflict**.

Quy tắc đúng là **read-after-unknown-outcome**:

- Tra cứu mapping và tài nguyên tại đích bằng ID/khóa đã xác minh.
- Nếu thấy một tài nguyên chắc chắn thuộc đúng identity, **tiếp tục theo id đó**.
- Nếu có nhiều kết quả hoặc bằng chứng mâu thuẫn, cách ly để xử lý.
- Chỉ tạo mới khi xác định được chưa có User phù hợp và quy trình cho phép.

**SCIM không tự bảo đảm POST tạo User idempotent trong mọi dịch vụ.** Đừng dựa vào việc userName có ràng buộc duy nhất để bỏ qua thiết kế xử lý timeout.

## 9. Cập nhật User bằng PUT và PATCH

Sau Joiner, **Mover** và thay đổi dữ liệu cá nhân có thể yêu cầu cập nhật thuộc tính.

### PUT /Users/{id}

PUT là thao tác thay thế hoặc cập nhật toàn bộ tài nguyên theo ngữ nghĩa giao thức của dịch vụ. Nếu client gửi thiếu thuộc tính quan trọng, kết quả có thể không như mong muốn. Vì vậy trước khi dùng PUT phải hiểu rõ **quy tắc giữ/xóa giá trị mặc định, mutability và thuộc tính readOnly** của service provider.

Ví dụ khái quát:

~~~http
PUT /scim/v2/Users/9a03b8c7 HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Content-Type: application/scim+json
~~~

Trong môi trường có nhiều nguồn cập nhật, **PUT thiếu thông tin hoặc dùng snapshot cũ** có nguy cơ ghi đè dữ liệu mới. Có thể cần đọc trạng thái hiện hành và dùng kiểm soát version.

### PATCH /Users/{id}

PATCH thường phù hợp khi chỉ cần thay đổi một vài thuộc tính. SCIM PATCH dùng schema **PatchOp** và danh sách **Operations**.

Ví dụ thay displayName:

~~~http
PATCH /scim/v2/Users/9a03b8c7 HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Content-Type: application/scim+json
~~~

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "Replace",
      "path": "displayName",
      "value": "Nguyen Lan"
    }
  ]
}
~~~

Các thao tác PATCH được SCIM định nghĩa gồm **add, remove, replace**. Đường dẫn có thể chỉ tới thuộc tính đơn, thuộc tính phức hợp hoặc trường hợp có biểu thức lọc trên thuộc tính đa trị theo cú pháp tương ứng.

**Không giả định mọi service provider hỗ trợ PATCH.** Kiểm tra capability và dữ liệu schema. Khi PATCH không được hỗ trợ, connector có thể phải dùng PUT hoặc API khác, với quy tắc đồng bộ và kiểm thử để không làm mất thuộc tính.

### Cập nhật theo phiên bản

Nếu service provider hỗ trợ versioning/ETag, client có thể dùng điều kiện **If-Match** để tránh ghi đè một phiên bản đã bị thay đổi. Nếu đích trả **412 Precondition Failed**, cần đọc lại tài nguyên và tính lại desired state; không tự bỏ điều kiện phiên bản rồi ghi đè.

## 10. Trường active và ý nghĩa vô hiệu hóa tài khoản

Thuộc tính **active** là một boolean của SCIM User nhằm diễn tả trạng thái hoạt động theo schema. Một request thường dùng khi Leaver là:

~~~http
PATCH /scim/v2/Users/9a03b8c7 HTTP/1.1
Host: app.example.org
Authorization: Bearer <REDACTED_CONNECTOR_TOKEN>
Content-Type: application/scim+json
~~~

~~~json
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

**active=false không đồng nghĩa mặc định account đã bị xóa hoặc mọi session/API token ngay lập tức mất hiệu lực.** Nhà cung cấp có thể diễn giải trạng thái này thành chặn đăng nhập mới, ngừng quyền truy cập, khóa ở ứng dụng, hoặc một hành vi khác được tài liệu hóa.

### Cần kiểm tra thêm những gì?

- Ứng dụng có còn cho **SSO login mới** vào account này không?
- Phiên local và refresh/access token đã phát có tiếp tục dùng được không?
- API key, PAT, SSH key, certificate hoặc credential riêng ở ứng dụng có bị thu hồi không?
- Tài khoản có còn **role/group/entitlement trực tiếp** hoặc quyền qua nhóm không?
- Các tác vụ tự động và tài nguyên sở hữu có cần bàn giao trước khi vô hiệu/xóa không?
- Readback qua GET có phản ánh **active=false** không, và thao tác thật có bị từ chối không?

**Hủy account trong IdP và gửi active=false qua SCIM là hai hành động khác nhau.** Với Leaver, cần đối soát khả năng truy cập thực tế, không chỉ hai cờ trạng thái.

## 11. DELETE User: khác deactivate như thế nào?

SCIM Protocol hỗ trợ **DELETE /Users/{id}** đối với dịch vụ triển khai thao tác tương ứng. Tuy nhiên, thao tác xóa có thể gây tác động đến dữ liệu nghiệp vụ, ownership, retention và khả năng kiểm toán.

| Thao tác | Ý nghĩa mong muốn | Cần cân nhắc |
|---|---|---|
| **PATCH active=false** | Vô hiệu hóa User, thường giữ bản ghi | Phụ thuộc ngữ nghĩa SP về phiên, token và quyền |
| **DELETE /Users/{id}** | Yêu cầu xóa tài nguyên User | Có thể xóa/ẩn dữ liệu hoặc kích hoạt quy tắc riêng của nhà cung cấp |
| **Gỡ Group.members** | Thu hồi thành viên nhóm ở đích | Cần xác nhận ảnh hưởng quyền qua nhóm |
| **Thu hồi credential riêng** | Cắt API key, session, token/certificate | Thường không được bảo đảm chỉ bởi User active=false |
| **Data retention/ownership transfer** | Lưu giữ hoặc chuyển tài nguyên theo chính sách | Không đồng nghĩa phải tiếp tục cho account đăng nhập |

### Quy tắc Leaver an toàn

1. Xác định **thời điểm cắt quyền** theo nguồn nhân sự.
2. **Ngăn truy cập** theo chính sách và khả năng đích.
3. Xử lý session, API token, secret, quyền và tài khoản khác liên quan.
4. Bàn giao dữ liệu/tài nguyên sở hữu theo thẩm quyền.
5. Giữ hoặc xóa hồ sơ khi đến hạn và có căn cứ lưu giữ hợp lệ.
6. Đối soát tại đích để chứng minh không còn quyền truy cập ngoài ý muốn.

Không dùng DELETE như biện pháp chữa lỗi SCIM hàng loạt mà không kiểm tra impact. Trường hợp user đang được liên kết với nhiều hệ thống, xóa nhầm có thể khiến dữ liệu khó phục hồi.

## 12. Group membership không đơn giản là trường groups của User

SCIM có tài nguyên **Group** cốt lõi với endpoint **/Groups** và thuộc tính **members**. Việc quản lý thành viên nhóm ảnh hưởng trực tiếp đến entitlement và RBAC tại hệ thống đích.

### User.groups và Group.members

- **User.groups** trong core schema thường là **read-only**, thể hiện những Group mà User thuộc về.
- **Group.members** là thuộc tính quản lý thành viên nhóm ở Group; client cập nhật theo khả năng và chính sách của service provider.
- Một số SaaS có hệ thống vai trò/giấy phép riêng, nên thay đổi Group không nhất thiết cấp/thu hồi mọi role nghiệp vụ.

Ví dụ thêm User vào Group qua PATCH tại tài nguyên Group:

~~~json
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
          "value": "9a03b8c7",
          "type": "User"
        }
      ]
    }
  ]
}
~~~

Đây là **body minh họa** gửi tới **PATCH /Groups/{groupId}** nếu đích hỗ trợ. Tài nguyên Group phải tồn tại, User ID phải đúng trong ngữ cảnh của service provider, và client phải được phân quyền cập nhật nhóm.

### Tránh nhầm với entitlement của ứng dụng

| Thuộc tính hoặc cơ chế | Vai trò | Giới hạn |
|---|---|---|
| **User.groups** | Đọc danh sách Group liên quan đến User | Không nên ghi trực tiếp khi schema read-only |
| **Group.members** | Quản lý thành viên Group | Tùy mapping Group → quyền thực tế |
| **User.roles** | Thông tin vai trò theo schema | Không có ngữ nghĩa RBAC chung cho mọi app |
| **User.entitlements** | Thông tin entitlement theo schema | Cách dùng và mutability tùy nhà cung cấp |
| **Ứng dụng API riêng** | Quản lý role/license/grants ngoài SCIM core | Cần connector bổ sung và reconciliation |

Vì vậy, **User đã được tạo bằng SCIM** chưa đủ để kết luận đã cấp hết quyền cho công việc. Cần kiểm tra Group, role, entitlement và quyền trực tiếp thực tế.

## 13. Enterprise User Extension: nhân sự và người quản lý

SCIM Core Schema có **Enterprise User Extension** phổ biến để biểu diễn một số thông tin liên quan đến tổ chức, ví dụ **employeeNumber, costCenter, organization, division, department, manager**.

URI extension:

~~~text
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User
~~~

### Ví dụ User có enterprise extension

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "person-2046",
  "userName": "lan.nguyen@example.org",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "E2046",
    "department": "Finance",
    "costCenter": "FIN-01",
    "manager": {
      "value": "3fa1d420",
      "$ref": "https://app.example.org/scim/v2/Users/3fa1d420"
    }
  }
}
~~~

Đây là ví dụ cấu trúc. **manager.value** thường tham chiếu **id của User quản lý tại service provider**, không phải tự động dùng mã nhân sự HRIS. Client cần liên kết manager identity với target User ID tương ứng; phải xử lý trường hợp manager chưa được provision hoặc đã đổi vai trò.

### Bảo vệ dữ liệu nhân sự

Các trường department, manager và employeeNumber có thể là dữ liệu cá nhân/nhân sự. Chỉ đồng bộ những trường cần thiết cho ứng dụng và được phép theo chính sách. Không đưa **lý do sa thải, hồ sơ kỷ luật, giấy tờ định danh, dữ liệu sức khỏe** vào extension tùy tiện.

### Không lạm dụng extension để thay thế chính sách

Một thuộc tính department=Finance **không tự cấp quyền Finance-Admin**. Ứng dụng hoặc IGA còn phải áp RBAC/ABAC, approval, SoD và quyền trên tài nguyên cụ thể. Nếu vai trò được suy từ department ở đích, phải kiểm tra mapping và tránh **privilege accumulation** khi Mover.

## 14. SCIM schema discovery và khả năng service provider

Để triển khai tin cậy, không chỉ đọc một mẫu User rồi suy ra tất cả. SCIM có các tài nguyên phục vụ khám phá khả năng:

| Endpoint | Mục đích |
|---|---|
| **/ServiceProviderConfig** | Công bố hỗ trợ filter, patch, bulk, sorting, ETag, authentication schemes và một số giới hạn |
| **/Schemas** | Mô tả schema/thuộc tính và đặc điểm cần tuân thủ |
| **/ResourceTypes** | Liên kết resource type với endpoint, core schema và extension |
| **/Users** | Truy vấn/tạo User theo khả năng được hỗ trợ |
| **/Groups** | Truy vấn/tạo/cập nhật Group theo khả năng được hỗ trợ |

Những endpoint này có thể có chính sách xác thực/ủy quyền riêng; thực tế một số dịch vụ tuyên bố SCIM nhưng cung cấp tính năng hạn chế. Nếu sản phẩm không trả discovery đầy đủ, phải dựa trên tài liệu tích hợp đã được kiểm chứng, kiểm thử trong môi trường được phép và ghi giới hạn connector.

### Cần kiểm tra trước khi triển khai

1. Hỗ trợ SCIM 2.0 và base URL đúng tenant.
2. Cách xác thực connector: bearer token, OAuth hoặc phương thức được vendor hỗ trợ.
3. User schema bắt buộc, quy tắc userName và thuộc tính email.
4. Có hỗ trợ **PATCH** và dùng được cho active, name, emails không?
5. Có hỗ trợ filtering và trả đúng **ListResponse/pagination** không?
6. Group.members có thể sửa và quyền thực tế ánh xạ thế nào?
7. Có hỗ trợ ETag/version để chống cập nhật cạnh tranh không?
8. Hành vi **active=false**, DELETE, session, local login và retention ra sao?
9. Giới hạn rate limit, error handling, delay và hệ thống audit.
10. Những extension/entitlements nào được hỗ trợ hoặc bắt buộc theo sản phẩm.

Không nên “tự chữa” thiếu hỗ trợ bằng cách **vô hiệu kiểm tra bảo mật hoặc gửi trường lạ** rồi cho rằng ứng dụng sẽ hiểu.

## 15. Mã lỗi SCIM và cách phân loại thất bại

SCIM dùng HTTP status cùng biểu diễn lỗi theo giao thức. Bảng sau là **hướng dẫn triage**, không thay thế tài liệu nhà cung cấp.

| HTTP status | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| **400 Bad Request** | Schema, filter, giá trị thuộc tính hoặc cấu trúc PATCH không hợp lệ | Kiểm tra payload và khả năng đích, sửa dữ liệu/mapping |
| **401 Unauthorized** | Connector thiếu xác thực hợp lệ | Kiểm tra token/credential kết nối |
| **403 Forbidden** | Connector không có quyền thao tác | Kiểm tra scope/role connector theo phê duyệt |
| **404 Not Found** | Sai User id/endpoint hoặc tài nguyên không tồn tại | Readback, đối chiếu mapping và tenant |
| **409 Conflict** | Xung đột uniqueness hoặc trạng thái | Đối chiếu account hiện có, tránh tạo trùng |
| **412 Precondition Failed** | Phiên bản ETag/If-Match không còn phù hợp | Đọc lại tài nguyên, tính lại patch theo version mới |
| **429 Too Many Requests** | Rate limit phía ứng dụng | Backoff, tuân thủ Retry-After khi có |
| **5xx** | Lỗi phía dịch vụ hoặc gateway | Retry có giới hạn và readback trạng thái nếu kết quả chưa rõ |

Một lỗi SCIM có thể dùng schema:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:Error"
  ],
  "status": "409",
  "scimType": "uniqueness",
  "detail": "A resource with the requested unique attribute already exists"
}
~~~

Đây là response **minh họa**. Nội dung **detail** có thể khác tùy dịch vụ và không nên được log nguyên trạng nếu chứa thông tin người dùng hoặc secret. **scimType** là tín hiệu hữu ích nhưng không đảm bảo mọi lỗi vendor đều có cấu trúc nhất quán.

### Những kết luận sai cần tránh

- **HTTP 201 sau POST** không chứng minh đã gán group và entitlement cần thiết.
- **HTTP 200 sau PATCH active=false** không tự chứng minh mọi session đã bị thu hồi.
- **HTTP 404 sau DELETE** có thể phản ánh User đã bị xóa từ trước; cần kiểm tra đúng đối tượng/mapping trước khi xác nhận hoàn tất.
- **Timeout** không có nghĩa request chắc chắn chưa được áp dụng.
- **409 Conflict** không có nghĩa có thể gắn account trùng email cho đúng người mà không xác minh.

## 16. Retry, idempotency và thứ tự sự kiện

SCIM connector thường chạy bất đồng bộ. Job có thể được gửi lại, xử lý muộn hoặc đến sai thứ tự.

### Trạng thái nên theo dõi

| Mốc | Ý nghĩa | Có thể kết luận gì? |
|---|---|---|
| **Requested** | IAM đã có yêu cầu hợp lệ | Chưa có kết quả ở đích |
| **Dispatched** | Đã gửi request tới SCIM API | Chưa biết request được thực thi chưa |
| **Acknowledged** | HTTP response/acknowledgment được trả | Có kết quả thao tác theo hợp đồng API |
| **Observed** | Đã đọc lại User và thuộc tính quan trọng | Có bằng chứng trạng thái hiện hành |
| **Reconciled** | Desired state khớp observed state trong phạm vi | Hạng mục đã được xác minh |
| **Partial** | User đúng nhưng group/quyền khác chưa đúng | Workflow chưa hoàn tất toàn bộ |
| **Failed** | Không thể áp đúng desired state | Cần xử lý lỗi, owner và escalation |

### Phân biệt retry an toàn và nguy hiểm

- **PATCH active=false** có thể được thiết kế theo kiểu đặt trạng thái mong muốn, an toàn hơn về tác động lặp nếu SP hỗ trợ đúng ngữ nghĩa.
- **POST tạo User** sau timeout phải tra cứu trước; nhiều lần POST có thể tạo trùng hoặc xung đột.
- **PUT từ snapshot cũ** có thể ghi đè thuộc tính mới, dù cùng id.
- **Thao tác cập nhật Group** phải tính đến thành viên đã được thêm/xóa bởi nguồn khác, tránh mất dữ liệu.
- **Leaver đã có hiệu lực:** một job Joiner/Mover cũ không được phép tự gửi active=true để mở account trở lại.

### Pseudocode chống cập nhật lỗi thời

~~~text
function reconcileScimUser(event):
    verifyAuthoritativeSource(event)
    identity = resolveImmutableIdentity(event.subjectId)
    relation = resolveRelationship(identity, event.relationshipId)

    latest = readCurrentAuthoritativeState(identity, relation)
    if event.sourceVersion < latest.version:
        return STALE_EVENT

    target = findVerifiedTargetMapping(identity, event.targetSystem)
    if target is unknown:
        candidates = lookupByApprovedExternalId(identity)
        target = verifyUniqueCandidateOrEscalate(candidates)

    desired = calculateDesiredUserState(latest, policies, approvals)

    if latest.lifecycleState == LEAVER_EFFECTIVE:
        desired.active = false

    if target exists:
        applyMinimalUpdateWithConcurrencyControl(target, desired)
    else if desired.shouldExist:
        createAndVerifyUserWithDuplicateProtection(desired)

    observed = readBackUserAndRequiredEntitlements(target)
    if observed != desired:
        createFindingWithOwnerAndDeadline(observed, desired)
        return PARTIAL

    return RECONCILED
~~~

Đây là **giả mã**, không phải code sản xuất. Hệ thống thật phải xử lý **giao dịch, race condition giữa worker, retry/backoff, tenant isolation, cách biểu diễn quyền và sự khác biệt của service provider**.

## 17. SCIM User trong Joiner lifecycle

Một Joiner thường có chuỗi hoạt động:

1. **HRIS tạo hồ sơ** với identity ID, quan hệ làm việc, ngày có hiệu lực.
2. **IAM/IGA xác minh nguồn**, đối chiếu nhân sự, trạng thái proofing và vai trò baseline.
3. **Tính desired state** cho từng ứng dụng: có cần account không, userName, email, active, group và thời hạn.
4. **SCIM client tạo User hoặc cập nhật account đã được xác minh**, lưu id ở đích.
5. **Gán group/role** bằng Group API hoặc connector tương ứng nếu cần.
6. **IdP/SSO** quản lý enrollment MFA, xác thực và điều kiện phiên; SCIM không tự thay thế.
7. **Đối soát** User, trạng thái và quyền đích, sau đó mới thông báo sẵn sàng đúng phạm vi.

### Account trước ngày bắt đầu

Tùy chính sách, có thể tạo User sớm để chuẩn bị provisioning nhưng để **active=false** hoặc hạn chế quyền. Không nên tự động kích hoạt đầy đủ chỉ vì HRIS đã biết người sắp vào làm. Quyết định phải dựa trên **effectiveAt**, mức rủi ro và khả năng đích.

### Trường hợp Joiner provisioning thất bại

Nếu IdP user đã có nhưng SCIM User chưa tạo ở SaaS, người dùng có thể đăng nhập SSO nhưng không có account đích để liên kết. Nếu User đã tạo nhưng group chưa gán, đăng nhập thành công nhưng thiếu quyền nghiệp vụ. Cần phân biệt trạng thái từng bước thay vì ghi toàn bộ onboarding đã hoàn tất.

## 18. SCIM User trong Mover lifecycle

**Mover** thay đổi vai trò, nhóm, bộ phận, hợp đồng hoặc quan hệ quản lý của người dùng. Với SCIM User, cập nhật có thể gồm:

- **name/displayName/emails/userName** khi thông tin chính thức thay đổi.
- **EnterpriseUser department, manager, costCenter, organization** khi bộ phận/quan hệ tổ chức thay đổi.
- **Group.members** để thêm hoặc thu hồi các nhóm quyền liên quan.
- **active** nếu người dùng cần tạm đình chỉ, chuyển trạng thái hoặc chuyển quyền theo chính sách.
- Entitlement/role riêng qua API nếu ứng dụng không hỗ trợ mô hình nhóm quyền đầy đủ trong SCIM.

### Rủi ro cộng dồn quyền

Lan chuyển từ Sales sang Finance. SCIM client đã cập nhật **department=Finance** và thêm nhóm **FINANCE_READER**, nhưng quên gỡ nhóm **SALES_EXPORT_ADMIN**. User vẫn active và có quyền Finance, tuy nhiên **quyền Sales cũ còn tồn dư**.

**Mover không chỉ là cập nhật thuộc tính mới; còn phải thu hồi quyền không còn hợp lệ.** Đối soát cần tính chênh lệch cả **quyền thiếu** và **quyền dư**.

### Quy tắc xử lý

- Xác định nguồn đã thay đổi thực sự và version mới nhất.
- Tính desired state theo vai trò/thuộc tính mới, approval và SoD.
- Cập nhật User/Group qua connector theo ngữ nghĩa hỗ trợ.
- Đọc lại account, group, direct grants và trạng thái phiên khi cần.
- Nếu nhóm cũ không gỡ được, mở finding theo rủi ro và không đánh dấu Mover hoàn tất.
- Nếu chính sách MFA tăng mức, yêu cầu security key/passkey/step-up tại IdP; **SCIM User không phải công cụ đăng ký authenticator**.

## 19. SCIM User trong Leaver lifecycle

**Leaver** là tình huống phải ưu tiên tránh sai lệch: một người rời tổ chức có thể vẫn có tài khoản local hoặc token độc lập trong ứng dụng đích dù IdP đã bị khóa.

### Phân biệt các lớp thu hồi

| Lớp | Hành động | SCIM có tự bảo đảm? |
|---|---|---|
| **User record** | active=false hoặc DELETE theo chính sách | SCIM có thể yêu cầu thay đổi trạng thái/tài nguyên |
| **Group membership** | Gỡ User khỏi Group | Cần thao tác group/entitlement phù hợp |
| **SSO login** | Ngăn đăng nhập qua IdP | Thực hiện tại IdP/chính sách federation |
| **Local password** | Khóa xác thực local hoặc xóa credential | Tùy service provider; không tự suy từ active=false |
| **Session/token** | Thu hồi phiên và access/refresh token đã phát | Không mặc nhiên được giải quyết chỉ bằng SCIM |
| **API keys/PAT/SSH keys** | Thu hồi credential ở dịch vụ đích | Thường cần API/tác vụ riêng |
| **Dữ liệu sở hữu** | Chuyển owner, lưu giữ theo chính sách | Quy trình offboarding nghiệp vụ riêng |
| **Audit/reconciliation** | Kiểm chứng quyền đã mất hiệu lực | Cần readback và bằng chứng độc lập |

### Quy trình Leaver mẫu

1. Nguồn có thẩm quyền phát sự kiện nghỉ với **subjectId, relationshipId, effectiveAt và version**.
2. IAM xác minh người/quan hệ, tránh cắt nhầm tài khoản còn được cho phép bởi quan hệ khác.
3. Đến mốc hiệu lực, IdP chặn đăng nhập và xử lý phiên/token theo chính sách.
4. SCIM connector gửi **active=false** hoặc thao tác deactivate do SP hỗ trợ.
5. Connector/IGA thu hồi group và entitlement không còn được phép.
6. Hệ thống xử lý local account, credential độc lập, API key, VPN, PAM và dữ liệu cần bàn giao.
7. **GET/readback** xác minh User ở đích inactive hoặc không còn tồn tại theo desired state.
8. Nếu còn đường truy cập, workflow ở trạng thái **PARTIAL/OPEN**, có owner, deadline, escalation và biện pháp bù trừ.
9. Chỉ đóng khi các đường truy cập thuộc phạm vi được xác minh đạt chính sách.

**SCIM trả HTTP 200 không chứng minh mọi đường truy cập đã bị cắt.** Một ứng dụng có thể chấp nhận token đã phát trước đó hoặc có cache quyền độc lập.

### Một người có nhiều quan hệ

Một người vừa là nhân viên vừa là người dùng dịch vụ với quan hệ độc lập. Khi kết thúc hợp đồng lao động, không tự xóa mọi danh tính cùng email; cần xác định **quan hệ và quyền thực sự chịu tác động** theo chính sách. SCIM User đích có thể được giữ cho quan hệ hợp lệ khác nhưng entitlement liên quan quan hệ cũ phải được thu hồi.

## 20. Reconciliation: đối chiếu User thực tế với desired state

**Reconciliation** so sánh **expected/desired User state** do IAM tính theo JML và policy với **observed User state** đọc từ service provider.

### Các đối tượng cần so sánh

| Khía cạnh | Desired state | Observed state | Sai lệch điển hình |
|---|---|---|---|
| Sự tồn tại User | Có hoặc không nên có tài khoản | GET/ListResponse tại SP | Orphan/duplicate/missing User |
| Trạng thái active | True/false theo thời điểm và policy | User.active | Leaver còn active |
| Mapping | identityId ↔ externalId ↔ target id | Thuộc tính và mapping ở SP | Gắn sai account |
| Thuộc tính | userName, email, department, manager | Readback User và extension | Mover chưa đồng bộ |
| Groups | Tập Group hợp lệ | Group.members và User.groups nếu trả | Quyền thừa hoặc thiếu |
| Entitlements | Role/permission đã duyệt | API riêng hoặc SCIM được hỗ trợ | Quyền trực tiếp tồn dư |
| Access thực tế | Không có truy cập khi Leaver | Session, token, local login nếu quan sát được | Residual access |
| Owner phi con người | Chủ trách nhiệm của workload | Service/asset registry | Tài khoản kỹ thuật mồ côi |

### Không chỉ dựa vào danh sách User tại IdP

Một tài khoản có thể đã mất tại IdP nhưng vẫn tồn tại trong SaaS. SCIM reconciliation cần đọc **tài nguyên thực tế ở từng SP**, không chỉ so sánh với cache hoặc database của provisioning client.

### Cửa sổ nhất quán

Service provider có thể áp thay đổi bất đồng bộ. Sau PATCH, GET tức thì đôi khi chưa phản ánh giá trị mới. Connector nên có **cửa sổ kiểm tra có giới hạn**, retry readback và xử lý lỗi; không được dùng eventual consistency để bỏ qua các chênh lệch quyền tồn dư vô thời hạn.

### Các finding quan trọng

- **UNEXPECTED_ACTIVE_USER:** account hoạt động dù không còn quan hệ/phê duyệt.
- **MISSING_USER:** tài khoản cần tạo nhưng chưa tồn tại.
- **UNMATCHED_USER:** tài khoản ở đích chưa liên kết được với identity đáng tin.
- **DUPLICATE_USER:** nhiều account ứng viên cho một subject ngoài mô hình cho phép.
- **STALE_USER_ATTRIBUTES:** thông tin Mover chưa cập nhật.
- **EXCESS_GROUP_MEMBERSHIP:** group/entitlement vượt desired state.
- **INCOMPLETE_DEPROVISIONING:** SCIM thay đổi thành công cục bộ nhưng đường truy cập khác vẫn hoạt động.

Không tự xóa mọi **UNMATCHED_USER**; tài khoản có thể thuộc một **owner hợp lệ, local admin, break-glass hoặc workload** chưa đưa vào registry.

## 21. Bảo mật SCIM connector và dữ liệu User

SCIM thường dùng HTTP(S) API với quyền tạo/sửa/xóa tài khoản, nên credential của provisioning client là **điểm truy cập nhạy cảm**.

### Kiểm soát connector

1. **TLS:** chỉ kết nối đến endpoint/tenant được phê duyệt qua TLS đúng cấu hình.
2. **Authentication:** bảo vệ bearer token hoặc credential connector bằng secret manager; không ghi vào Git, ticket hoặc log.
3. **Least privilege:** cấp connector quyền cần thiết cho User/Group trong phạm vi được quản lý; không cấp vai trò admin tổng quát nếu không cần.
4. **Scope/tenant isolation:** tránh đồng bộ một nhân viên sang nhầm tenant hoặc môi trường test/production.
5. **Rate limiting:** giới hạn tốc độ, xử lý 429 và retry có backoff.
6. **Input validation:** kiểm tra schema, filter escaping, độ dài và định dạng thuộc tính.
7. **Sensitive attributes:** chỉ gửi PII cần thiết; không đồng bộ password, dữ liệu proofing hoặc lý do nghỉ việc nếu không có căn cứ.
8. **Logging:** ghi correlation ID, id đích, thao tác và kết quả, **không log token hoặc password**.
9. **Change control:** version hóa mapping và xác minh tác động trước khi thay đổi đồng bộ hàng loạt.
10. **Credential rotation:** luân chuyển token/secret connector có kế hoạch để tránh mất khả năng deprovision hàng loạt.

### Vì sao không nên đồng bộ password thông thường?

Trong môi trường doanh nghiệp dùng **SSO**, ứng dụng đích thường không cần nắm plaintext password của nhân viên. SCIM có thuộc tính password trong schema nhưng **không có nghĩa nên gửi hoặc giữ mật khẩu qua mọi connector**. Nên để IdP thực hiện xác thực và cung cấp federation; ứng dụng đích quản lý account/quyền theo SCIM.

### Rủi ro API được cấp quyền cao

Nếu credential SCIM connector bị lộ, kẻ tấn công có thể **tạo user trái phép, cấp quyền qua nhóm hoặc vô hiệu hóa hàng loạt account** tùy quyền connector. Do đó cần kiểm tra quyền, phát hiện hành vi bất thường và có cơ chế thu hồi connector credential khẩn cấp.

## 22. SCIM User và non-human identities

Không phải mọi principal của IAM đều là nhân viên. **Service account, bot, workload identity, thiết bị và tài khoản khẩn cấp** cũng có vòng đời và quyền.

### Không áp mù quáng User schema cho mọi loại

SCIM User schema được thiết kế cho mô hình người dùng, dù có ứng dụng dùng User resource biểu diễn account kỹ thuật. Nếu nhà cung cấp dùng User cho service account, tổ chức cần quy định:

- **Account type** và nguồn desired state phù hợp.
- **Owner kỹ thuật và workload/application ID** trong registry đáng tin.
- **Credential** được quản lý bằng vault, managed identity hoặc cơ chế máy–máy thay cho password nhân viên.
- **Scope quyền tối thiểu**, thời hạn, lịch review và quy trình nghỉ/retire dịch vụ.
- **Không xóa bot** chỉ vì người từng là owner đã Leaver; chuyển owner và rà soát secret/quyền.
- **Đối soát account máy** ở từng hệ thống đích, không lọc bỏ khỏi inventory vì không có HRIS personId.

### SSO và OAuth workload

Một bot có thể dùng **OAuth client credentials** hoặc workload identity federation để gọi API. **Đó không phải SSO trình duyệt của nhân viên**. Nếu service provider quản lý bot dưới SCIM User, việc active=false của User có thể không thu hồi **client credential/token khác**. Cần đối soát từng loại credential.

## 23. Tình huống xuyên suốt: một SCIM User qua JML

Giả sử **Lan** gia nhập tổ chức ngày **01/12/2026**, làm Sales rồi chuyển sang Finance và cuối cùng nghỉ việc. Ứng dụng CRM có SCIM 2.0 User/Group và dùng IdP SSO.

### Giai đoạn A — Joiner

- HRIS tạo hồ sơ **person-2046**, relationship **employment-2046-v1**, effectiveAt đúng ngày bắt đầu.
- IAM kiểm tra identity, role baseline và tenant CRM đúng.
- SCIM client gửi **POST /Users** với externalId=person-2046, userName và các thuộc tính cần thiết.
- Service provider trả **id=9a03b8c7**; IAM lưu mapping và GET readback.
- IAM cập nhật Group.members cho nhóm **SALES_READER** theo phê duyệt.
- Lan hoàn tất enrollment MFA ở IdP. CRM cho Lan đăng nhập bằng SSO và áp quyền thực tế.

Nếu POST timeout sau khi CRM đã tạo User, connector phải tra cứu externalId và xác minh id trước retry; nếu không có thể sinh tài khoản trùng.

### Giai đoạn B — Mover

- Lan chuyển sang Finance; HRIS phát version mới.
- IAM cập nhật **EnterpriseUser.department**, manager mapping nếu cần và role/Group theo desired state.
- Connector thêm **FINANCE_READER** và gỡ **SALES_EXPORT** nếu không còn hợp lệ.
- Một thao tác gỡ nhóm cũ bị lỗi 429; workflow chuyển **PARTIAL**, retry có backoff và kiểm tra trạng thái.
- IAM chỉ đóng Mover khi quyền mới hợp lệ và quyền Sales cũ không còn dư, bao gồm quyền trực tiếp nếu có.

### Giai đoạn C — Leaver

- HRIS phát sự kiện Leaver với effectiveAt.
- IdP chặn đăng nhập mới và xử lý phiên/token theo khả năng.
- SCIM client gửi **PATCH active=false** đến **/Users/9a03b8c7**, không tra nhầm account theo email.
- CRM trả thành công; IAM GET readback và đối soát nhóm, quyền, token và local session.
- Nếu CRM vẫn cho phép dùng một API key cũ, workflow **chưa hoàn tất**; phải thu hồi key hoặc áp biện pháp chặn theo rủi ro.

### Giai đoạn D — Rejoiner

- Lan được tuyển lại với quan hệ mới. IAM đối chiếu identity, dữ liệu được phép lưu giữ và chính sách rehire.
- Không dùng lại session, API token, password hoặc quyền cũ.
- Nếu được phép tái dùng User id cũ, phải kiểm tra owner, trạng thái, tài khoản và quyền trước khi re-activate theo quy trình mới; nếu không, tạo account mới theo mapping có kiểm soát.

**Bài học từ ví dụ:** SCIM User giúp chuẩn hóa dữ liệu và thao tác quản lý tài khoản, nhưng **đúng ID, đúng sự kiện, đúng quyền và xác minh tại hệ thống đích** mới quyết định một vòng đời IAM an toàn.

## 24. Checklist triển khai SCIM User an toàn

1. **Chuẩn:** đã hiểu SCIM 2.0 Core Schema (RFC 7643), Protocol (RFC 7644) và phạm vi implementation thực tế?
2. **Schema:** User có URI core đúng, thuộc tính bắt buộc và extension hỗ trợ, không cố ghi field read-only?
3. **Định danh:** đã phân biệt id của SP, externalId của client, userName và identityId/relationshipId của nguồn?
4. **Mapping:** đã lưu và xác minh liên kết IAM identity ↔ target User id, không chỉ dựa email/name?
5. **Joiner:** kiểm tra trạng thái nguồn, ngày hiệu lực và existing account trước POST, không tạo trùng sau timeout?
6. **GET/filter:** đã kiểm tra khả năng filter, escape dữ liệu, xử lý 0/nhiều kết quả và phân trang đầy đủ?
7. **PUT/PATCH:** đã biết thuộc tính nào writable và server có hỗ trợ PATCH/ETag không?
8. **active:** đã kiểm tra active=false thực sự tác động đến đăng nhập, phiên và quyền thế nào?
9. **DELETE:** có quyết định retention/ownership trước khi xóa tài nguyên không?
10. **Group:** đã dùng Group.members đúng cách, không coi User.groups read-only là field cấp quyền ghi được?
11. **Enterprise extension:** department, manager và employeeNumber có được đồng bộ đúng schema, tối thiểu hóa PII?
12. **Connector security:** token/secret được bảo vệ, scope và tenant đúng, TLS, audit và luân chuyển credential?
13. **Retry:** 400/401/403/409/412/429/5xx được phân loại đúng; timeout được readback trước khi tạo lại?
14. **Concurrency:** source version, ETag/If-Match và fencing có ngăn event cũ ghi đè Leaver không?
15. **Mover:** có thu hồi nhóm/quyền cũ và đối soát entitlement dư, không chỉ cập nhật department?
16. **Leaver:** SCIM deactivation có đi cùng xử lý IdP, SSO, session/token, API key và quyền độc lập không?
17. **Non-human:** service/workload/device accounts có owner và desired state riêng, không bị xóa nhầm vì thiếu HRIS?
18. **Reconciliation:** đã so sánh desired với observed, ghi coverage, readback và xử lý các finding?
19. **Audit:** có event ID, policy version, target id, request outcome, owner và bằng chứng xác minh mà không log bí mật?
20. **Đóng vòng đời:** chỉ đánh dấu hoàn tất khi User, Group, entitlement và quyền truy cập thực tế đạt chính sách?

### Ghi nhớ

**SCIM User là tài nguyên tiêu chuẩn để quản lý bản ghi người dùng ở hệ thống đích**, với schema cốt lõi, định danh do service provider cấp, thuộc tính do client đồng bộ và các thao tác HTTP như GET, POST, PUT, PATCH và DELETE theo khả năng hỗ trợ. Để triển khai đúng, cần phân biệt **id, externalId và userName**, xử lý uniqueness, retry và sự kiện đến muộn, cũng như quản lý Group và enterprise extension theo schema. Trong **Joiner–Mover–Leaver**, SCIM User phải phối hợp với **IdP/SSO, MFA, RBAC/ABAC, account reconciliation và thu hồi phiên/token/credential độc lập**. **Một response SCIM thành công không thay thế bằng chứng tài khoản và quyền thực tế đã đúng tại ứng dụng đích.**
