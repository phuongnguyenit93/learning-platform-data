# Create operation trong SCIM provisioning: tạo tài khoản và nhóm có kiểm soát

## 1. Create operation giải quyết bài toán gì?

Trong **System for Cross-domain Identity Management (SCIM)**, **Create operation** là thao tác yêu cầu **Service Provider (SP)** tạo một resource mới, phổ biến nhất là **User** hoặc **Group**, thông qua giao thức HTTP. Trong SCIM 2.0, client gửi **POST** đến endpoint của collection, chẳng hạn **/Users** hoặc **/Groups**, kèm biểu diễn resource theo schema tương ứng.

Ví dụ, phòng nhân sự xác nhận một nhân viên mới sẽ làm việc tại tổ chức. Hệ thống quản trị vòng đời danh tính **Identity and Access Management (IAM)** xác định những ứng dụng nhân viên cần có tài khoản. Một connector SCIM sẽ gửi yêu cầu **POST /Users** đến ứng dụng đích để tạo user với tên đăng nhập, định danh nguồn và những thuộc tính cần thiết. Sau khi nhận phản hồi, IAM phải **liên kết ID resource mà ứng dụng tạo ra với danh tính nội bộ và đọc lại trạng thái thực tế**, không chỉ dựa vào việc đã gửi request.

Create operation nằm trong quá trình **provisioning**, nhưng không đồng nghĩa toàn bộ onboarding đã hoàn tất:

- **Đăng ký danh tính (identity enrollment)**: xác minh chủ thể và liên kết với nguồn có thẩm quyền.
- **SCIM Create**: tạo resource User/Group trong hệ thống đích.
- **Authenticator enrollment**: đăng ký phương tiện xác thực như passkey hoặc MFA nếu cần.
- **SSO**: cấu hình và kiểm chứng luồng đăng nhập từ Identity Provider (IdP).
- **Authorization**: xác định role, entitlement và quyền truy cập thực tế theo **RBAC/ABAC**.
- **Reconciliation**: xác nhận account, membership và quyền tại đích đúng với trạng thái mong muốn.

Trong mô hình **Joiner–Mover–Leaver (JML)**, Create thường xuất hiện ở **Joiner**. Với **Mover**, một chuyển đổi vai trò có thể đòi tạo account trên ứng dụng mới, nhưng cũng phải thu hồi quyền không còn hợp lệ. Với **Leaver**, mục tiêu thường là deactivate/thu hồi chứ **không tạo lại account**.

## 2. Đặc tả và đối tượng tham gia

Hai tài liệu nền tảng cho SCIM 2.0 là **RFC 7643** (Core Schema) và **RFC 7644** (Protocol). RFC 7643 mô tả resource/attribute; RFC 7644 quy định cách thao tác với resource qua HTTP, gồm Create, Read, Update, Delete, Search và các khả năng khác.

| Thành phần | Trách nhiệm trong Create |
| --- | --- |
| **HRIS / nguồn bảo trợ** | Xác nhận nhân viên/đối tác, quan hệ làm việc, ngày hiệu lực và thuộc tính nghiệp vụ |
| **IAM/IGA** | Tính trạng thái account mong muốn, chọn ứng dụng đích, kiểm tra phê duyệt, lưu liên kết identity–account |
| **SCIM Client** | Tạo request đúng schema, xác thực với endpoint, xử lý kết quả và lỗi |
| **SCIM Service Provider** | Kiểm tra request/quyền/schema, gán ID resource, lưu resource và trả kết quả |
| **IdP** | Quản lý đăng nhập, authenticator, SSO và chính sách xác thực nếu kiến trúc dùng IdP tập trung |
| **Ứng dụng đích** | Ánh xạ SCIM User/Group sang account, role hoặc quyền nội bộ; thực thi kiểm soát tài nguyên |
| **Resource Server / policy engine** | Quyết định quyền hiệu lực khi có yêu cầu truy cập, không chỉ dựa vào resource vừa tạo |

**SCIM Client** và **OAuth Client** không phải khái niệm đồng nhất trong mọi kiến trúc. Một connector SCIM có thể dùng access token, mTLS hoặc phương thức được nhà cung cấp hỗ trợ để gọi API quản trị; đó là **ủy quyền cho hoạt động provisioning**. Đừng nhầm credential của connector với token SSO dùng cho người dùng cuối.

## 3. Create khác các thao tác SCIM khác ở đâu?

| Thao tác | HTTP thường dùng | Mục đích | Tình huống IAM |
| --- | --- | --- | --- |
| **Create** | **POST /Users**, **POST /Groups** | Tạo resource mới | Joiner cần account hoặc nhóm mới |
| **Read** | **GET /Users/{id}**, **GET /Groups/{id}** | Lấy resource đã có | Kiểm tra trạng thái sau Create |
| **Search** | GET collection với **filter** hoặc truy vấn được hỗ trợ | Tìm resource theo điều kiện | Phòng tránh tạo trùng, reconciliation |
| **Replace** | **PUT /Users/{id}** | Thay biểu diễn resource theo quy tắc giao thức | Đồng bộ lại các thuộc tính thích hợp |
| **Partial Update** | **PATCH /Users/{id}**, **PATCH /Groups/{id}** | Điều chỉnh thuộc tính hoặc membership | Mover, khóa account, cập nhật nhóm |
| **Delete** | **DELETE /Users/{id}** | Yêu cầu xóa resource | Xử lý tùy chính sách và khả năng ứng dụng |

**Không dùng POST /Users mỗi lần muốn cập nhật một thuộc tính.** Nếu account đã tồn tại, quá trình thông thường là **liên kết đúng account ID rồi dùng Update/PATCH khi cần**. Gửi lại Create mù quáng có thể tạo user trùng hoặc gây lỗi **409 Conflict**.

SCIM không định nghĩa rằng một **DELETE** phải được dùng cho mọi nhân viên nghỉ việc. Nhiều quy trình Leaver sử dụng **active=false**, thu hồi quyền và giữ lại bản ghi vì yêu cầu lịch sử/kiểm toán; hiệu quả thực tế cần được kiểm chứng tại ứng dụng.

## 4. Đường đi của một yêu cầu Create

~~~mermaid
flowchart TD
    H["HRIS / Nguồn bảo trợ<br/>Sự kiện Joiner được xác nhận"] --> I["IAM/IGA: xác minh identity,<br/>organization và ngày hiệu lực"]
    I --> P["Tính target account + thuộc tính<br/>theo chính sách, phê duyệt"]
    P --> Q{"Đã có account liên kết / trùng?"}
    Q -->|"Có, liên kết đã xác minh"| U["Không Create lại<br/>đối soát hoặc Update"]
    Q -->|"Không"| C["SCIM Client gửi POST /Users"]
    C --> S["SCIM Service Provider<br/>kiểm tra schema, quyền, uniqueness"]
    S --> R{"Create thành công?"}
    R -->|"201 Created"| L["Lưu server id, Location, version<br/>và mapping identity–account"]
    R -->|"409/4xx/5xx"| E["Phân loại lỗi, retry/điều tra<br/>không tạo trùng"]
    L --> V["GET/readback + kiểm tra state<br/>và quyền tại ứng dụng"]
    V --> D{"Khớp expected state?"}
    D -->|"Có"| A["Ghi audit và cập nhật trạng thái Joiner"]
    D -->|"Không"| E
    E --> X["Exception có owner, deadline<br/>và kế hoạch khắc phục"]
~~~

Sơ đồ mô tả trách nhiệm logic. Trong triển khai thật, sự kiện HR, tạo account, đồng bộ nhóm và phê duyệt quyền có thể chạy **bất đồng bộ**. Không vì connector trả kết quả thành công ở một bước mà bỏ qua các bước kiểm chứng tiếp theo.

## 5. Kiểm tra khả năng SCIM của hệ thống đích trước khi tạo

Không nên cho rằng mọi sản phẩm tuyên bố “hỗ trợ SCIM” đều có cùng thuộc tính, nhóm, cách mapping và hành vi account.

Các endpoint khám phá chuẩn cần quan tâm khi ứng dụng triển khai:

| Endpoint | Thông tin cần xác định |
| --- | --- |
| **/ServiceProviderConfig** | Những khả năng như filter, patch, bulk, ETag, authentication schemes có được công bố và hỗ trợ không |
| **/ResourceTypes** | Resource type nào tồn tại, endpoint và schema/extension liên quan |
| **/Schemas** | Thuộc tính, kiểu dữ liệu, yêu cầu bắt buộc, mutability, uniqueness, canonical values |
| **/Users** | Có hỗ trợ Create User với các thuộc tính cần thiết không |
| **/Groups** | Có hỗ trợ Create Group và cập nhật membership theo quy tắc ứng dụng không |

Đặc biệt cần kiểm tra **cấu trúc extension, trường bắt buộc bổ sung, cách ánh xạ userName, quy tắc duy nhất, khả năng lọc và giới hạn quota/rate limit**. Nếu endpoint discovery không có hoặc tài liệu sản phẩm khác chuẩn, phải xác nhận contract tích hợp và ghi nhận giới hạn thay vì tự suy đoán.

**Bulk operation** là khả năng riêng, không mặc nhiên được mọi SP hỗ trợ. Dù SP có hỗ trợ bulk, không nên giả định một loạt Create trên nhiều target hoặc bên trong bulk là giao dịch nguyên tử có rollback tự động.

## 6. Điều kiện nghiệp vụ trước POST /Users

Một Create User an toàn nên được đặt sau các cổng kiểm soát:

1. **Identity đã được xác minh:** nguồn nhân sự/bảo trợ đáng tin, liên kết đúng person/worker/employment với identity, không gộp nhầm theo email.
2. **Quan hệ làm việc hợp lệ:** sự kiện đã duyệt, không phải bản nháp/hợp đồng bị hủy; ngày bắt đầu và thời hạn được hiểu theo múi giờ/nguồn.
3. **Ứng dụng được yêu cầu:** role, loại lao động, organization hoặc phê duyệt xác định app thuộc danh sách cần provision.
4. **Chưa có account đã liên kết:** tra cứu bảng mapping identity–targetAccount và xác minh những ứng viên trùng.
5. **Định danh đầu vào rõ ràng:** userName theo hợp đồng SP; externalId ổn định của nguồn provisioning; tránh dùng tên hiển thị làm khóa duy nhất.
6. **Trạng thái kích hoạt phù hợp:** tạo trước ngày bắt đầu có thể cần trạng thái chưa cho đăng nhập, nếu sản phẩm và chính sách hỗ trợ.
7. **Tài khoản của connector có quyền tối thiểu:** chỉ được tạo resource trong phạm vi tenant/organization được ủy quyền.
8. **Quy trình xử lý lỗi đã có:** biết cách đọc lại khi request timeout, kiểm tra xung đột và ghi audit.

**Tạo user thành công không tự chứng minh người đó đã hoàn tất MFA, SSO, phê duyệt role hoặc có quyền truy cập tài nguyên.** Đây là các cổng nghiệm thu riêng.

## 7. POST /Users: yêu cầu tạo User theo SCIM 2.0

Một request minh họa tới endpoint giả định:

~~~http
POST /scim/v2/Users HTTP/1.1
Host: saas.example.invalid
Authorization: Bearer CONNECTOR_TOKEN_PLACEHOLDER
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "hris-employment-2026-018",
  "userName": "linh.nguyen@example.invalid",
  "name": {
    "formatted": "Nguyễn Minh Linh",
    "familyName": "Nguyễn",
    "givenName": "Minh Linh"
  },
  "displayName": "Nguyễn Minh Linh",
  "emails": [
    {
      "value": "linh.nguyen@example.invalid",
      "type": "work",
      "primary": true
    }
  ],
  "active": false
}
~~~

**Toàn bộ giá trị là minh họa**, địa chỉ thuộc miền ví dụ và token chỉ là placeholder; không dán bearer token thật vào tài liệu, shell history hoặc ticket. Endpoint thực tế do **base URL** và cách triển khai của SP quyết định; phần **/scim/v2** trong ví dụ không phải một tiền tố bắt buộc của mọi nhà cung cấp.

Giải thích:

- **schemas**: chứa URI của core User schema; nếu có extension, khai báo schema extension tương ứng.
- **externalId**: ID do provisioning client cung cấp để liên kết với bản ghi nguồn; không thay thế ID do SP cấp.
- **userName**: định danh đăng nhập/định danh user theo quy tắc uniqueness của SP.
- **name, displayName, emails**: các thuộc tính người dùng theo core schema, có thể tùy chọn hoặc có yêu cầu riêng.
- **active: false**: ví dụ tạo account ở trạng thái chưa hoạt động theo SCIM; phải kiểm chứng mapping thật của SP và mọi đường đăng nhập.

**Không gửi trường id như thể client được chọn ID do SP quản lý**, và không gửi các trường meta do server quản trị làm dữ liệu đầu vào cần lưu. Server gán ID, thời điểm tạo và metadata phù hợp.

## 8. Phản hồi thành công: 201 Created, id và Location

Khi tạo resource thành công theo SCIM Create, SP thông thường phản hồi **HTTP 201 Created**, cung cấp vị trí resource và biểu diễn resource vừa tạo theo quy tắc SCIM.

~~~http
HTTP/1.1 201 Created
Content-Type: application/scim+json
Location: https://saas.example.invalid/scim/v2/Users/8f9e2c1d

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "id": "8f9e2c1d",
  "externalId": "hris-employment-2026-018",
  "userName": "linh.nguyen@example.invalid",
  "displayName": "Nguyễn Minh Linh",
  "active": false,
  "meta": {
    "resourceType": "User",
    "created": "2026-11-23T02:45:00Z",
    "lastModified": "2026-11-23T02:45:00Z",
    "location": "https://saas.example.invalid/scim/v2/Users/8f9e2c1d"
  }
}
~~~

Những điểm phải lưu lại:

1. **HTTP status** và ID giao dịch để đối soát.
2. **id** do SP cấp; đây là khóa chính để truy cập resource theo endpoint sau này.
3. **externalId** từ client; dùng để liên kết với identity và nguồn nghiệp vụ khi được quản trị đúng.
4. **Location/meta.location** nếu SP cung cấp theo contract, tránh ghép URL sai hoặc tin nhầm một host ngoài danh sách cho phép.
5. **Trạng thái và thuộc tính thực tế** được SP trả về, không mặc định giống hoàn toàn request.
6. **ETag/meta.version** khi SP có hỗ trợ, có thể phục vụ kiểm soát cập nhật đồng thời sau Create.

**Không phải mọi trường tùy chọn đều được SP lưu hoặc trả y nguyên.** SP có thể chuẩn hóa, áp dụng default, bỏ qua thuộc tính không được hỗ trợ theo quy tắc của nó hoặc từ chối request; cần kiểm tra kết quả thực tế.

### Ý nghĩa của 201 Created

201 xác nhận SP báo đã tạo resource. Nó **chưa chứng minh**:

- Người dùng đã đăng nhập thành công qua SSO;
- MFA đã được đăng ký;
- Group membership/role đã được đồng bộ đúng;
- Quyền ở API hoặc tài nguyên đã có hiệu lực;
- Account chưa tồn tại qua một định danh khác trước đó;
- Tất cả hệ thống hạ nguồn đã cập nhật nếu SP có xử lý bất đồng bộ nội bộ.

Vì vậy, cần **readback/reconciliation** theo yêu cầu nghiệp vụ của Joiner.

## 9. id, externalId, userName và email: vai trò khác nhau

| Trường | Ai quản lý chủ yếu? | Có nên dùng liên kết account? | Lưu ý |
| --- | --- | --- | --- |
| **id** | SP cấp và quản lý | Có, cho đối tượng tại SP đó | Bảo toàn cùng namespace/tenant và endpoint |
| **externalId** | Provisioning client cấp | Có, khi contract xác định nguồn và phạm vi | Không giả định duy nhất toàn cầu giữa nhiều client/tenant |
| **userName** | Client cung cấp; SP kiểm tra theo schema/uniqueness | Có thể hỗ trợ tra cứu, nhưng không thay proofing | Có thể đổi theo chính sách, quy tắc canonicalization riêng |
| **emails** | HR/IdP/IAM hoặc người quản trị theo authority | Chỉ là tín hiệu phụ | Email có thể đổi, tái sử dụng hoặc thuộc alias |
| **displayName** | Nguồn profile có thẩm quyền | Không dùng làm khóa | Không duy nhất, dễ thay đổi |
| **employeeNumber** trong enterprise extension | Thường từ HR | Hữu ích theo mapping và policy | Không phải mọi ứng dụng hỗ trợ enterprise extension |

Một tổ chức có thể có nhiều SCIM Client kết nối tới cùng SP hoặc nhiều tenant. **externalId** là giá trị do client cấp với phạm vi do contract quy định; không mặc nhiên duy nhất trên mọi tổ chức. Khi lưu mapping nên dùng khóa kết hợp như **sourceSystem, sourceObjectId, targetSystem, targetTenant và serverId**.

Trong core schema, **userName** có yêu cầu tính duy nhất theo phạm vi SP quản lý. Nhưng việc SP so sánh hoa/thường, email alias hoặc canonicalization cần đọc schema và cấu hình thực tế; không tự hạ chữ thường mọi trường nếu nguồn không quy định.

## 10. Dùng Enterprise User extension khi cần

RFC 7643 có **Enterprise User extension** để biểu diễn các thuộc tính liên quan tổ chức, ví dụ employeeNumber, department, costCenter hoặc manager. Chỉ gửi khi SP hỗ trợ và có quyền xử lý dữ liệu đó.

Ví dụ payload User có extension:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "employment-2026-018",
  "userName": "linh.nguyen@example.invalid",
  "active": false,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "E-0281",
    "department": "Engineering",
    "costCenter": "CC-150"
  }
}
~~~

Không lấy dữ liệu từ HR rồi đẩy toàn bộ sang ứng dụng. Một SP quản lý ticket không nhất thiết cần cost center hay tên người quản lý. Dùng **data minimization**, nguồn có thẩm quyền theo từng thuộc tính và chính sách xử lý dữ liệu cá nhân. Một custom extension chỉ được dùng khi **schema URI, kiểu dữ liệu và mapping** đã thống nhất với SP; không tự gán nghĩa cho trường chưa hỗ trợ.

Nếu cần quản lý **organization/tenant**, phải phân biệt **pháp nhân, department, tenant và Group**. Việc gán department không tự động chứng minh quyền truy cập dữ liệu tenant tương ứng.

## 11. POST /Groups: tạo nhóm SCIM

Ngoài User, SCIM thường hỗ trợ resource **Group** để quản lý nhóm và membership. Create Group gửi **POST /Groups** với core Group schema.

~~~http
POST /scim/v2/Groups HTTP/1.1
Host: saas.example.invalid
Authorization: Bearer CONNECTOR_TOKEN_PLACEHOLDER
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "externalId": "iam-group-atlas-analysts",
  "displayName": "atlas-analysts",
  "members": [
    {
      "value": "8f9e2c1d",
      "type": "User"
    }
  ]
}
~~~

**value** trong một mục **members** phải tham chiếu đúng **SCIM User id do SP quản lý**, không dùng workerId hoặc email tùy ý. Tùy khả năng SP, có thể tạo Group rỗng trước rồi cập nhật membership qua PATCH, thay vì gộp mọi việc vào một Create.

**User.groups** thường là thuộc tính phản ánh membership do SP quản lý và có ngữ nghĩa **readOnly** theo core User schema; không nên giả định ghi thẳng danh sách groups khi POST /Users sẽ tự tạo membership. Thực tế provisioning nhóm cần theo contract của **Group.members** và sản phẩm đích.

Không phải ứng dụng nào cũng có Group hoặc ánh xạ Group sang role giống nhau. Create Group thành công chỉ chứng minh resource nhóm được tạo; phải xác minh **member, role mapping và quyền hiệu lực** tại ứng dụng.

### Trình tự tạo user và nhóm

Nếu nhóm có members:

1. Bảo đảm các User liên quan đã tồn tại ở SP và có **server id** hợp lệ.
2. Kiểm tra nhóm mục tiêu đã tồn tại hay chưa, tránh tạo trùng.
3. Tạo hoặc cập nhật nhóm theo quyền được duyệt.
4. Đọc lại danh sách thành viên và quyền ứng dụng.

Các bước riêng lẻ có thể thành công một phần; **không có cam kết giao dịch nguyên tử trên mọi resource và mọi ứng dụng** chỉ vì dùng SCIM.

## 12. SCIM Create và các trạng thái tài khoản

Nhiều doanh nghiệp cần tạo account **trước ngày nhân viên chính thức bắt đầu** để chuẩn bị onboarding. Thuộc tính **active** trong core User có thể biểu diễn trạng thái quản trị hoạt động của user. Ví dụ **active: false** thường được dùng cho account chưa được phép hoạt động.

Tuy nhiên, **ý nghĩa thực tế của active do SP áp dụng theo cách triển khai**. Cần kiểm tra:

- Có chặn cả local login và SSO login không?
- Có chặn token/session đã tồn tại không?
- Có vô hiệu API key, PAT hoặc quyền dịch vụ không?
- Có ảnh hưởng license, billing hoặc việc cấp app tự động không?
- Có cần thao tác bổ sung tại IdP hoặc ứng dụng để khóa đường truy cập khác không?

**Không dùng active=false như một bảo đảm phổ quát rằng mọi đường đăng nhập đã đóng.** Khi Joiner chưa đến ngày vào làm, trạng thái và chính sách ứng dụng phải bảo đảm quyền không kích hoạt sớm. Khi Leaver, cần thu hồi thêm các credential/phiên liên quan theo mức rủi ro.

Ví dụ với ngày bắt đầu dạng date-only 01/12/2026 tại Việt Nam, một hệ thống phải xác định cụ thể **thời điểm nào** được bật account theo timezone và lịch làm việc; không tự suy một mốc UTC tùy ý.

## 13. Quyền của SCIM Client: bảo vệ endpoint tạo tài khoản

Create là thao tác quản trị nhạy cảm: một connector cấu hình sai có thể tạo hàng loạt account hoặc cấp nhầm user vào tenant.

Những kiểm soát cần áp dụng:

| Kiểm soát | Mục tiêu |
| --- | --- |
| **HTTPS/TLS** | Bảo vệ đường truyền request và token |
| **Credential connector được quản lý** | Không nhúng bearer token hoặc client secret trong tài liệu, log, mã nguồn |
| **Least privilege cho connector** | Chỉ được tạo/sửa những resource/tenant thật sự được phân công |
| **Client authentication/authorization theo SP** | Mỗi request phải được kiểm tra quyền; không mặc định có quyền admin toàn hệ thống |
| **Phân tách môi trường** | Không dùng token và endpoint production cho test/dev |
| **Allowlist endpoint và kiểm tra Location** | Không gửi token tới host ngoài hợp đồng tích hợp |
| **Giới hạn tốc độ và quota** | Tránh tạo hàng loạt ngoài ý muốn và xử lý lỗi kiểm soát |
| **Kiểm toán** | Gắn actor, source event, identity, client, target tenant và kết quả |
| **Bảo vệ PII** | Chỉ truyền thuộc tính cần thiết, không gửi credential người dùng không cần |

Với token OAuth được cấp cho connector, **scope của token connector** chỉ giới hạn thao tác API quản trị được phép, không thể thay thế kiểm tra **tenant, target user và policy** tại Service Provider. Tránh dùng một credential có quyền vô hạn cho tất cả môi trường/khách hàng.

## 14. SCIM Create có idempotent không?

**Không nên coi POST Create là thao tác idempotent mặc định.** Nếu gửi cùng một POST hai lần, kết quả có thể là:

- SP tạo resource ở lần đầu, lần hai trả **409 Conflict** do trùng userName/unique attribute;
- SP tạo hai resource nếu dữ liệu cho phép và thiếu kiểm soát dedup;
- Request đầu đã được xử lý nhưng **client bị timeout trước khi nhận response**; lần retry tạo trùng hoặc lại lỗi.

Không được xử lý **timeout** bằng kết luận “chắc chắn chưa tạo”. Đó là trạng thái **không rõ kết quả**.

### Chiến lược chống tạo trùng

1. Gán một **identity/account correlation key** ổn định theo source và tenant trước khi POST.
2. Trước khi Create, kiểm tra bảng liên kết **IAM identity → target SCIM id** đã lưu.
3. Khi có khả năng filter/search, tra cứu ứng viên dựa trên **externalId** hoặc **userName** theo contract; xác minh các thuộc tính và nguồn trước khi quyết định.
4. Dùng cơ chế **single-flight/lock hoặc hàng đợi có kiểm soát** để hai event cùng identity không gửi Create đồng thời.
5. Sau timeout, **đọc lại/tìm resource** trước khi retry; nếu chưa thể xác minh, giữ trạng thái pending/unknown.
6. Khi nhận 409, không tự coi là thành công; xác định resource xung đột có đúng identity hay không.
7. Lưu **SCIM server id** sau khi thành công; những lần đồng bộ tiếp theo dùng id đó để Update/Read.

### Ví dụ tra cứu ứng viên

Nếu SP công bố hỗ trợ filter, một cách tra cứu có thể là:

~~~http
GET /scim/v2/Users?filter=externalId%20eq%20%22hris-employment-2026-018%22 HTTP/1.1
Host: saas.example.invalid
Authorization: Bearer CONNECTOR_TOKEN_PLACEHOLDER
Accept: application/scim+json
~~~

Response của một truy vấn danh sách SCIM thường dùng **ListResponse** schema và các trường **Resources, totalResults, startIndex, itemsPerPage** theo giao thức. Cần xử lý phân trang, mapping, quyền tìm kiếm và tính nhất quán của nguồn. Nếu có **0 kết quả** nhưng connector không đủ quyền đọc hoặc dữ liệu còn trễ, không vội kết luận account không tồn tại.

**Không được tự động gộp hai tài khoản chỉ vì email trùng nhau.** Nếu nhiều ứng viên hoặc dữ liệu xung đột, chuyển sang xử lý ngoại lệ có xác minh danh tính.

## 15. Mã giả orchestration Create an toàn

Mã giả sau chỉ minh họa trách nhiệm; không phải SDK SCIM của một nhà cung cấp:

~~~text
provisionJoiner(targetSystem, joinerEvent):
    requireTrustedHRorSponsorSource(joinerEvent)
    requireApprovedEffectiveEmployment(joinerEvent)
    identity = correlateAndVerifyIdentity(joinerEvent)
    target = requireAuthorizedTargetTenant(targetSystem, joinerEvent)

    expected = calculateExpectedAccount(identity, target, policyVersion)
    key = stableCorrelationKey(identity, target)
    withPerTargetIdentityLock(key):
        link = lookupVerifiedAccountLink(key)
        if link.exists:
            return reconcileExistingAccount(link.serverId, expected)

        candidates = findPossibleExistingResources(
            target, expected.externalId, expected.userName
        )
        if candidates.hasAmbiguity:
            return openException("AMBIGUOUS_ACCOUNT_MATCH", key)
        if candidates.hasVerifiedMatch:
            saveAccountLink(key, candidates.serverId)
            return reconcileExistingAccount(candidates.serverId, expected)

        response = scimCreateUser(target, expected)
        if response.is201Created:
            requireValidServerIdAndTrustedLocation(response)
            saveAccountLink(key, response.serverId)
            return readBackAndVerify(response.serverId, expected)

        if response.isTimeoutOrUnknown:
            return investigateTargetStateBeforeRetry(key, expected)
        if response.is409Conflict:
            return investigateConflictWithoutBlindRetry(key, expected)
        return classifyAndAssignException(response, key)
~~~

Trong hệ thống thực, bước khóa và liên kết phải xử lý **cập nhật cạnh tranh giữa nhiều worker**, phân vùng tenant, transaction của cơ sở dữ liệu IAM, sự kiện đến trễ và retry. Nếu chưa có đủ dữ liệu để xác định account đã được tạo, **không ghi trạng thái COMPLETED** chỉ vì không thấy lỗi.

## 16. Lỗi thường gặp khi Create

SCIM sử dụng mã HTTP và **SCIM Error** để mô tả lỗi. Các trường hợp ví dụ:

| Trường hợp | HTTP thường gặp | Cách xử lý |
| --- | --- | --- |
| Payload JSON không hợp lệ / thiếu trường bắt buộc | **400 Bad Request** | Sửa schema, kiểu dữ liệu, thuộc tính yêu cầu |
| Scope/token connector không hợp lệ hoặc thiếu xác thực | **401 Unauthorized** | Kiểm tra credential và cơ chế xác thực |
| Connector không có quyền tạo user/tenant | **403 Forbidden** | Xác minh phân quyền, không tự nâng quyền |
| Endpoint hoặc tài nguyên tham chiếu không tồn tại | **404 Not Found** | Kiểm tra base URL, ResourceType, member references |
| Trùng userName/unique attribute | **409 Conflict** | Tra cứu resource xung đột, tránh tạo trùng/gộp nhầm |
| Vượt giới hạn request | **429 Too Many Requests** nếu SP dùng | Áp dụng backoff và Retry-After nếu cung cấp |
| Lỗi tạm thời của SP | **5xx** | Retry có kiểm soát sau khi xác minh trạng thái, tránh duplicate |
| Timeout/mất kết nối sau khi gửi POST | Không rõ kết quả | Tìm/readback resource trước khi quyết định retry |

Ví dụ SCIM Error minh họa cho xung đột duy nhất:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:Error"
  ],
  "scimType": "uniqueness",
  "detail": "userName conflicts with an existing resource",
  "status": "409"
}
~~~

Không phải mọi SP cung cấp thông điệp lỗi chi tiết giống nhau. Một số tình huống lỗi mapping và account state có thể chỉ xuất hiện khi readback hoặc trong log ứng dụng. **Không chuyển mọi 409 thành success**: nếu resource xung đột thuộc người khác, đây có thể là sự cố liên kết danh tính cần ngăn cấp quyền.

### Xử lý lỗi theo loại

- **Lỗi đầu vào hoặc quyền (4xx):** thường cần sửa dữ liệu, policy hoặc phê duyệt; retry nguyên request không giải quyết nguyên nhân.
- **Lỗi tạm thời (429/5xx):** retry với backoff, kiểm tra quota, trạng thái đích và giới hạn số lần.
- **Kết quả không xác định (timeout):** ưu tiên reconciliation trước khi retry vì POST không idempotent.
- **Xung đột định danh (409):** xác minh account chủ sở hữu, tenant và externalId, không auto-link theo email.

## 17. Create thành công một phần và tính nhất quán cuối cùng

Quá trình onboarding có thể phải tạo account trên nhiều ứng dụng: kho tài liệu, hệ thống báo cáo, công cụ mã nguồn và hệ thống hỗ trợ khách hàng. Mỗi ứng dụng có API hoặc connector riêng.

Giả sử ba request Create diễn ra:

| Ứng dụng | Kết quả | Ý nghĩa |
| --- | --- | --- |
| IdP | Account đã tạo | Có danh tính đăng nhập trung tâm |
| Kho tài liệu | SCIM 201 và đọc lại PASS | Account tồn tại đúng ở ứng dụng |
| Công cụ báo cáo | Timeout, chưa xác minh trạng thái | Không được tự kết luận thành công hay thất bại |
| Công cụ mã nguồn | 409 do userName trùng | Phải điều tra tài khoản đích có đúng người không |

Tình huống này là **PARTIAL/NEEDS_RECONCILIATION**, không phải Joiner hoàn tất. IAM nên theo dõi **trạng thái từng target, mã lỗi, số lần thử, owner, thời hạn và bằng chứng**.

Một số SP có hệ thống nội bộ **đồng bộ bất đồng bộ**: response 201 phản ánh đã tạo resource SCIM, nhưng license, group mapping hoặc quyền trong ứng dụng có thể chưa có hiệu lực ngay. Vì thế, cần quy định **cổng nghiệm thu tài khoản** và **cổng nghiệm thu quyền** riêng; readback có thể cần retry theo SLA.

**SCIM Create không cung cấp giao dịch phân tán nguyên tử trên nhiều ứng dụng.** Nếu một target thất bại, phải quyết định tiếp tục, khắc phục hoặc rollback theo quy trình đã duyệt; không tự xóa các tài khoản đã tạo nếu điều đó làm mất dữ liệu hợp lệ hoặc ảnh hưởng audit.

## 18. Create trong Joiner–Mover–Leaver

### 18.1. Joiner: cấp mới có xác minh

**Joiner** xác nhận người mới, trạng thái lao động, organization và thời điểm hiệu lực. IAM tính app/role cần dùng, tạo hoặc liên kết account đúng người, đồng bộ nhóm/quyền và kiểm chứng.

Một ca Joiner nên tách:

1. **Identity verified** — biết chắc ai là chủ thể và căn cứ nhân sự.
2. **Account created** — SP đã trả id hợp lệ và đọc lại đúng resource.
3. **Access provisioned** — các group/role/entitlement bắt buộc được áp dụng.
4. **Authentication ready** — SSO/MFA phù hợp đã được cấu hình và kiểm tra theo tiêu chí.
5. **Joiner completed** — các cổng bắt buộc được nghiệm thu và có audit.

Chỉ đóng ca ở trạng thái phù hợp với **bằng chứng**; không gộp tất cả thành một giá trị response 201.

### 18.2. Mover: tạo target mới, thu hồi target/quyền cũ

Khi nhân viên chuyển tổ chức, vai trò hoặc dự án, IAM có thể phải Create User trên một ứng dụng mới nếu chưa có account. Đồng thời cần:

- Kiểm tra app cũ có cần giữ hay không theo quan hệ làm việc còn hiệu lực.
- Thu hồi role/nhóm/ACL cũ, tránh **privilege accumulation**.
- Không tạo duplicate nếu user đã tồn tại do phân công khác.
- Cập nhật các thuộc tính source theo phiên bản và mốc hiệu lực chính xác.
- Đối soát session/token nếu quyền cũ cần bị vô hiệu ngay.

**Không giải quyết mọi Mover bằng POST Create.** Nếu cùng account tiếp tục được dùng, PATCH/PUT và entitlement review mới là hướng đi thông thường.

### 18.3. Leaver: chặn khả năng tồn dư

Khi quan hệ làm việc kết thúc, quy trình thường dùng **deactivation, deprovisioning và token/session revocation**, không phải Create. Cần đối soát account SCIM, local login, PAT, API key và quyền đã cấp trước đó.

Nếu Leaver đến khi một job Create đang chờ retry, **không được để retry cũ tạo lại account đang phải vô hiệu**. Hệ thống phải kiểm tra sự kiện HR mới nhất, version và trạng thái mục tiêu trước mọi lần xử lý.

## 19. Tránh race condition: Joiner bị hủy sau khi gửi Create

Ví dụ:

- 08:00: HRIS tạo sự kiện Joiner dự kiến bắt đầu ngày 01/12.
- 08:01: IAM gửi POST /Users tới SaaS.
- 08:02: HRIS gửi sự kiện hủy tuyển dụng, IAM đánh dấu CANCELLED.
- 08:03: Connector nhận lại response 201 hoặc retry vì timeout trước đó.

Nếu connector chỉ nhìn **sự kiện cũ** và phản hồi 201, nó có thể ghi nhận tài khoản “ready” dù Joiner đã bị hủy. Thiết kế an toàn cần:

1. Gắn mỗi job Create với **sourceEventId, sourceVersion và effectiveAt**.
2. Trước khi thực thi hoặc retry, đối chiếu trạng thái nhân sự mới nhất.
3. Khi response đến muộn, đọc lại **trạng thái mục tiêu hiện hành**, không chỉ “request đầu đã thành công”.
4. Nếu account đã được tạo nhưng không còn căn cứ, đưa vào **quy trình deprovisioning** có kiểm toán.
5. Phối hợp cấp nhóm/quyền sao cho tài khoản bị hủy không tiếp tục được cấp quyền ở bước sau.
6. Bảo đảm các event Mover/Leaver đến sau có thể **vượt ưu tiên** các job Create đã lỗi thời.

Không có một trình tự tuyệt đối đúng cho mọi hệ thống; điều cần bảo đảm là **trạng thái mong muốn dựa trên dữ liệu có thẩm quyền mới nhất** và có cơ chế đối soát cuối cùng.

## 20. Create, SSO và MFA là các kiểm soát riêng

SCIM và giao thức xác thực liên quan nhưng khác mục đích:

| Thành phần | Trả lời câu hỏi | Create có bao phủ không? |
| --- | --- | --- |
| **SCIM Create** | Có resource User/Group trong SP chưa? | Chính là đối tượng của operation |
| **IdP/SSO** | Người dùng đăng nhập bằng nhà cung cấp nào, assertion hợp lệ không? | Không tự chứng minh |
| **Authenticator/MFA** | Phương thức chứng thực đã binding đúng người, đủ bảo đảm chưa? | Không tự đăng ký chỉ bằng POST /Users |
| **RBAC** | Role được cấp có đúng theo công việc không? | Chỉ khi có mapping/provisioning riêng và đã kiểm chứng |
| **ABAC** | Điều kiện trạng thái, project, tenant, thời gian có đáp ứng không? | Không chỉ dựa vào resource User |
| **Token/session revocation** | Phiên/token cũ còn được chấp nhận không? | Không phải tác dụng chung của Create |
| **Audit/reconciliation** | Tài khoản và quyền thực tế đúng mục tiêu chưa? | Phải triển khai thêm |

Không nên gửi mật khẩu dùng chung hoặc seed MFA trong request Create cho nhân viên. SCIM core có thuộc tính password với ngữ nghĩa đặc biệt trong một số triển khai, nhưng **không mặc định cần truyền password** và không nên dùng nó để bỏ qua chính sách IdP/SSO hoặc quy trình enrollment an toàn.

Một User vừa được tạo trong SaaS có thể vẫn chưa truy cập được do chờ invitation, license, MFA hoặc SSO mapping. Ngược lại, User bị đặt inactive có thể vẫn còn session/token theo hành vi SP. Cần kiểm thử sản phẩm thật.

## 21. Create và quyền theo RBAC/ABAC

Tài khoản mới có thể được gán vào nhóm tạo ra quyền ở ứng dụng. Nhưng **membership nhóm không tự đồng nghĩa có mọi entitlement tương ứng trong mọi hệ thống**.

Ví dụ:

| Điều kiện | Giá trị |
| --- | --- |
| Identity | Linh, nhân viên phòng Kỹ thuật |
| SCIM User | Đã được tạo trong hệ thống quản lý mã nguồn |
| SCIM Group | atlas-analysts |
| RBAC role | RepositoryReader |
| ABAC condition | projectId = Atlas, employmentStatus = ACTIVE |
| API/resource | Repository thuộc dự án Atlas |

Chỉ nên cho phép **READ** nếu ứng dụng thực sự áp dụng role, project membership còn hiệu lực và tài nguyên đúng dự án. Một account được tạo qua SCIM không tự có quyền **WRITE**, **ADMIN** hoặc đọc repository khác.

Với ứng dụng đa tenant, phải xác minh **account được tạo trong tenant đúng** và membership được cấp đúng organization. Đường dẫn tenant hoặc organization từ request do client gửi không phải bằng chứng người dùng được phép dùng dữ liệu của tenant đó.

Khi group được tạo theo SCIM, mapping sang role là **quy ước của ứng dụng**, không phải bảo đảm chung của RFC 7644. Cần tài liệu mapping, phê duyệt và kiểm thử hiệu lực quyền.

## 22. Account reconciliation sau Create

**Reconciliation** là so sánh trạng thái **expected** do IAM tính từ nguồn có thẩm quyền với trạng thái **observed** ở SP/ứng dụng.

| Thuộc tính | Expected | Observed cần lấy tại target |
| --- | --- | --- |
| Identity/account link | identityId ↔ target account | SCIM server id/externalId liên kết đúng |
| UserName | Quy tắc đăng nhập đã duyệt | userName được SP lưu |
| Account status | active false trước ngày bắt đầu | Trạng thái SCIM và khả năng login thực tế |
| Organization/project | Thuộc phạm vi được phép | Tenant/membership ở ứng dụng |
| Group/role | Chỉ nhóm/role công việc cần | Danh sách group và entitlement hiện hành |
| SSO/MFA | Chính sách xác thực được áp dụng | Kết quả đăng nhập/test theo cổng nghiệm thu |
| Quyền hiệu lực | Đọc/ghi đúng tài nguyên | Authorization ở API hoặc kiểm tra quyền tại đích |

Cần phân biệt **unknown** với **false**. Nếu connector không đọc được danh sách nhóm do thiếu quyền hoặc API lỗi, không được kết luận user không có nhóm. Nếu target phản hồi 201 nhưng một truy vấn readback tạm thời chưa thấy resource, cần xét độ trễ nhất quán trước khi tạo lại.

### Những sai lệch thường gặp

- Tài khoản Create thành công nhưng **không liên kết được identity**: nguy cơ orphan account.
- **userName trùng** với người khác: nguy cơ mapping nhầm và lộ dữ liệu.
- Account tồn tại ở **tenant khác**: nguy cơ sai phạm vi.
- Nhóm được provision nhưng **role ứng dụng không khớp**: nguy cơ thiếu/thừa quyền.
- Có **local account cũ** ngoài SCIM: không tự bị xóa khi Create account mới.
- Account mới đã bật dù **ngày bắt đầu chưa tới**: vi phạm lịch kích hoạt.

## 23. Audit và quan sát hoạt động Create

Một lệnh Create cần được truy vết từ nguồn HR đến resource đã tạo, nhưng **không ghi bí mật**.

Ví dụ audit record minh họa:

~~~json
{
  "provisioningCaseId": "joiner-2026-018",
  "eventId": "hr-event-2026-181",
  "sourceSystem": "hris-main",
  "sourceVersion": 12,
  "identityId": "iam-id-482",
  "targetSystem": "saas-example",
  "targetTenant": "org-a",
  "operation": "SCIM_CREATE_USER",
  "requestCorrelationId": "scim-create-774",
  "externalId": "hris-employment-2026-018",
  "httpStatus": 201,
  "targetServerId": "8f9e2c1d",
  "createResult": "CREATED",
  "accountReadback": "VERIFIED",
  "accessReconciliation": "PENDING",
  "checkedAt": "2026-11-23T09:45:00+07:00"
}
~~~

Ở ví dụ này, **accountReadback = VERIFIED** không đồng nghĩa **accessReconciliation = VERIFIED**. Hệ thống chưa được đánh dấu toàn bộ Joiner hoàn tất nếu những quyền bắt buộc còn ở trạng thái chờ.

Những trường nên theo dõi:

- **Source event/version**: biết quyết định HR nào kích hoạt Create.
- **Identity/target references**: biết tài khoản thuộc chủ thể và tenant nào.
- **Operation/status/latency**: theo dõi số lần gọi, lỗi 4xx/5xx, timeout.
- **Correlation ID**: nối log IAM, connector và SP mà không ghi token.
- **Account mapping**: lưu server id, externalId và thời điểm xác minh.
- **Readback và entitlement status**: phân biệt resource đã tạo với quyền đã có hiệu lực.
- **Exception/owner/deadline**: giao xử lý những trường hợp chưa xác minh hoặc xung đột.

Không lưu nguyên connector bearer token, access token, password, client secret, TOTP seed hoặc private key trong log. Thông tin userName/email, organization và vai trò cũng có thể nhạy cảm; áp dụng tối thiểu hóa và phân quyền xem báo cáo.

## 24. Kiểm thử Create operation trong môi trường được phép

Một bộ kiểm thử không nên chỉ xác nhận HTTP 201. Cần có ca đúng, ca sai và xử lý lỗi:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Create User hợp lệ với thuộc tính tối thiểu bắt buộc | HTTP 201, resource id hợp lệ, đọc lại đúng identity |
| Create User có Enterprise extension được hỗ trợ | SP lưu/chuẩn hóa đúng thuộc tính được phép |
| userName trùng một resource đã tồn tại | Bị xử lý theo uniqueness, không tạo tài khoản cho người khác |
| Gửi lại cùng event | Không sinh account trùng nhờ correlation/reconciliation |
| Timeout sau khi POST được gửi | Trạng thái UNKNOWN cho đến khi kiểm tra target, không retry mù |
| Request thiếu schema hoặc sai kiểu dữ liệu | Bị từ chối bằng phản hồi phù hợp, không tạo resource sai |
| Connector không có quyền tenant | Bị từ chối, không tăng quyền để thử lại |
| Create Group tham chiếu User không hợp lệ | Không cấp membership sai; kiểm tra lỗi theo SP |
| Create thành công nhưng quyền chưa có hiệu lực | Case ở trạng thái PARTIAL/PENDING |
| HR hủy Joiner sau khi Create | Deprovision account đã tạo, ngăn retry lỗi thời |
| Mover sang ứng dụng mới | Create target mới, thu hồi quyền ở target cũ đúng chính sách |
| Leaver của một người có nhiều employment | Không thu hồi nhầm quyền còn hợp lệ |
| Account mới có local login ngoài SSO | Đường đăng nhập được kiểm kê và bảo vệ theo chính sách |

Kiểm thử nên dùng **danh tính, tenant và tài nguyên kiểm thử được ủy quyền**. Không cần dùng dữ liệu HR thật hoặc credential production để chứng minh schema và status code.

## 25. Tình huống thực hành: Joiner tạo tài khoản nhưng bị lỗi xung đột

**Bối cảnh:** Nhân viên mới tên An bắt đầu làm vào ngày 01/12. HRIS đã duyệt bản ghi **employment-501**; IAM cần tạo account trong công cụ báo cáo. SCIM client chuẩn bị **externalId = employment-501**, **userName = an.nguyen@example.invalid**.

### Diễn biến

1. IAM đã xác minh người và quan hệ HR, xác định account chưa có trong bảng liên kết nội bộ.
2. Connector gửi POST /Users tới SaaS; mạng timeout nên không nhận phản hồi.
3. Hệ thống job định retry cùng request.
4. Trước khi retry, connector tra cứu theo externalId nếu filter được hỗ trợ, thấy một User mới có server id **u-501**.
5. Connector đối chiếu thêm nguồn và thuộc tính, xác nhận đây là account do request trước tạo thành công.
6. IAM lưu liên kết **identityId → u-501**, không gửi Create lần nữa, đọc lại trạng thái và tiếp tục provisioning nhóm/quyền.

**Kết quả đúng:** không có duplicate account; audit ghi rõ lần POST đầu có kết quả không xác định ở phía client, nhưng sau đó resource đã được xác minh tại SP.

### Biến thể A — Tìm thấy account khác người

Nếu userName trùng với một account cũ nhưng **externalId không khớp**, không được auto-link. Cần xác minh tài khoản thuộc ai, tenant nào, có phải account cũ được tái sử dụng hay không. Chuyển sang ngoại lệ có owner thay vì cấp quyền của An cho một account chưa xác minh.

### Biến thể B — HR hủy tuyển dụng

Nếu HR hủy Joiner ngay sau khi resource đã tạo, IAM cần chặn bước cấp nhóm/role tiếp theo và deprovision account theo chính sách. Không coi 201 là lý do tiếp tục kích hoạt.

### Biến thể C — Account có rồi nhưng login chưa được

Nếu SCIM tạo User thành công nhưng người dùng chưa đăng ký MFA, chưa được mời vào tenant hoặc chưa có role, phải giữ ca ở **technical provisioning partial** theo tiêu chí nghiệm thu. Tạo lại account bằng POST không giải quyết đúng nguyên nhân.

### Câu hỏi tự kiểm tra

**Câu 1:** POST /Users trả 201 có chứng minh Joiner đã hoàn tất chưa?

**Trả lời:** Chưa. Cần kiểm tra account ID, trạng thái, quyền, SSO/MFA và những hạng mục bắt buộc khác tại hệ thống đích.

**Câu 2:** Vì sao timeout sau POST nguy hiểm nếu retry mù?

**Trả lời:** Vì request đầu có thể đã tạo resource; retry có thể tạo duplicate hoặc 409. Cần tìm/readback account trước.

**Câu 3:** Có thể dùng email làm khóa duy nhất để tự gộp account không?

**Trả lời:** Không. Email có thể thay đổi hoặc tái sử dụng. Cần server id, externalId và bằng chứng liên kết đáng tin.

**Câu 4:** Khi Create Group, members.value thường tham chiếu gì?

**Trả lời:** SCIM resource id của User/Group được SP quản lý trong phạm vi phù hợp, không phải workerId tùy ý từ HR.

**Câu 5:** Nếu active=false, mọi access token đã phát hành có bị thu hồi không?

**Trả lời:** Không mặc nhiên. Cần kiểm chứng hành vi SP và cơ chế thu hồi session/token ở resource server.

## 26. Checklist triển khai SCIM Create operation

| Câu hỏi | Điều kiện cần có |
| --- | --- |
| Nguồn Joiner và danh tính đã xác minh? | Source, employmentId, identityId và thời điểm hiệu lực hợp lệ |
| Target có hỗ trợ SCIM User/Group Create? | ResourceTypes/Schemas/ServiceProviderConfig hoặc contract được duyệt |
| Schema và thuộc tính bắt buộc đúng? | Core/Enterprise extension, type, mutability, uniqueness |
| Connector được bảo vệ? | TLS, token/secret quản lý an toàn, tenant scope và least privilege |
| ID nguồn và ID đích đã phân biệt? | externalId từ client, id do SP cấp, mapping có namespace |
| Có tránh tạo trùng account? | Lookup trước Create, lock/idempotency orchestration, xử lý 409 |
| Khi timeout có xác minh trước retry? | Search/readback, trạng thái UNKNOWN có owner |
| Response Create được kiểm tra? | 201, id, Location/meta, trạng thái và dữ liệu thực tế |
| Group và membership có đúng? | Đúng SCIM id, không gửi field readOnly để tạo membership |
| Có bảo vệ ngày bắt đầu và trạng thái account? | active/mốc kích hoạt và kiểm tra login thực tế |
| Có cấp role/entitlement đúng nhiệm vụ? | RBAC/ABAC, approval, group mapping tại app |
| SSO/MFA có được kiểm chứng riêng? | Không coi Create thành công là authentication ready |
| Có chống event cũ và race condition? | SourceVersion, effectiveAt, cancel, Mover/Leaver priority |
| Tài khoản dịch vụ được xử lý phù hợp? | Workload source/owner riêng, không tự gán HR record |
| Có audit và reconciliation? | Target account readback, effective access, exception owner |

## 27. Tổng kết

**Create operation** trong **SCIM 2.0** sử dụng **POST** tới collection như **/Users** hoặc **/Groups** để tạo một resource tại Service Provider, với **schema hợp lệ**, định danh rõ ràng và quyền connector phù hợp. Khi thành công, SP trả **201 Created** và thông tin resource mới, trong đó **id do SP cấp** và **externalId do client quản lý** phục vụ việc liên kết danh tính xuyên hệ thống.

Trong vòng đời **Joiner–Mover–Leaver**, SCIM Create chỉ là **một bước của provisioning**. Để tránh tài khoản trùng, sai chủ thể hoặc quyền quá rộng, cần kiểm tra nguồn **HRIS/đối tác**, identity correlation, tenant, tính duy nhất, xử lý retry không idempotent và đọc lại kết quả. **IdP/SSO/MFA** quản lý xác thực; **SCIM** quản lý resource User/Group theo khả năng; **RBAC/ABAC và ứng dụng đích** thực thi quyền; còn **workload identity** có vòng đời riêng. Chỉ khi account, membership, session/token và entitlement được đối soát theo các tiêu chí bắt buộc thì tổ chức mới giảm được **quyền truy cập tồn dư** và có bằng chứng kiểm toán đáng tin cậy.
