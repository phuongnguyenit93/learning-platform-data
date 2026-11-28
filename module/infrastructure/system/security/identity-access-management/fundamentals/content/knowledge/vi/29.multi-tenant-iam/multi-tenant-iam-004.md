# Tenant administrator

## 1. Tenant administrator là ai?

Trong một ứng dụng đa tenant, **tenant** là phạm vi đại diện cho một tổ chức, khách hàng hoặc đơn vị được tách biệt về dữ liệu và chính sách truy cập. **Tenant administrator** là người được trao quyền quản trị một phần hoặc toàn bộ cấu hình IAM trong phạm vi tenant đó, chẳng hạn mời thành viên, quản lý membership, gán vai trò hoặc cấu hình đăng nhập của tổ chức.

Quyền quản trị tenant là một dạng đặc quyền có giới hạn. Việc một người quản trị tenant A không tạo ra quyền đối với tenant B, cũng không mặc nhiên cho phép người đó vận hành hạ tầng của nhà cung cấp dịch vụ.

Ví dụ, ứng dụng quản lý dự án WorkBoard phục vụ hai khách hàng:

- Công ty An Phú có tenant `tenant-an-phu`.
- Công ty Bình Minh có tenant `tenant-binh-minh`.

Lan là quản trị viên của An Phú. Lan có thể mời nhân viên vào An Phú và gán các vai trò được phép. Lan không thể xem danh sách thành viên Bình Minh bằng cách thay `tenantId` trong một yêu cầu API.

Một người cũng có thể tham gia nhiều tenant với các vai trò khác nhau:

```text
Identity: user-lan
  Membership tại tenant-an-phu   → tenant_admin
  Membership tại tenant-binh-minh → viewer
```

Hệ thống phải giữ riêng vai trò của từng membership. Không được hợp nhất chúng thành một tập quyền toàn cục rồi áp dụng cho mọi tenant mà Lan tham gia.

Sau bài học, người học cần phân biệt được quyền quản trị tenant với quyền quản trị nền tảng, thiết kế được phạm vi ủy quyền và nhận ra các điểm kiểm tra cần có trong thao tác quản trị nhạy cảm.

## 2. Phân biệt các phạm vi quản trị

Tên vai trò như `owner`, `admin` hay `super_admin` không tự mô tả đầy đủ quyền hạn. Mỗi hệ thống cần định nghĩa rõ hành động, tài nguyên và phạm vi mà vai trò đó được phép tác động.

| Chủ thể hoặc vai trò | Phạm vi điển hình | Trách nhiệm | Điều không được suy ra chỉ từ tên vai trò |
|---|---|---|---|
| Platform administrator | Nền tảng của nhà cung cấp | Vận hành dịch vụ, cấu hình nền tảng, xử lý sự cố theo phân quyền | Có quyền đọc mọi dữ liệu khách hàng mà không cần mục đích và kiểm soát |
| Tenant owner | Một tenant cụ thể | Đại diện quyền sở hữu hoặc chịu trách nhiệm cao nhất theo mô hình sản phẩm | Tự động có quyền vận hành cơ sở dữ liệu hay hạ tầng của nhà cung cấp |
| Tenant administrator | Một tenant cụ thể | Quản lý thành viên, vai trò và cấu hình IAM được ủy quyền | Truy cập tenant khác hoặc thay đổi các giới hạn bảo mật của nền tảng |
| Delegated administrator | Một tập chức năng hoặc đơn vị trong tenant | Chỉ quản lý người dùng, nhóm hoặc cấu hình được giao | Có toàn bộ quyền của tenant administrator |
| Thành viên thông thường | Tài nguyên được cấp trong tenant | Sử dụng chức năng nghiệp vụ | Có quyền quản trị vì đã đăng nhập thành công |

Sản phẩm có thể gộp tenant owner và tenant administrator, hoặc tách thành các vai trò khác nhau. Điểm cốt lõi là **quyền có phạm vi xác định và được kiểm tra ở phía máy chủ**.

Quản trị IAM và truy cập dữ liệu nghiệp vụ cũng là hai loại quyền khác nhau. Một quản trị viên được phép khóa tài khoản nhân viên không nhất thiết phải được đọc nội dung tài liệu riêng của nhân viên đó. Nếu sản phẩm cho phép quản trị viên truy cập dữ liệu nghiệp vụ, quyền này cần được định nghĩa rõ thay vì trở thành hệ quả ngầm của vai trò quản trị.

## 3. Mô hình identity, membership và role binding

Một mô hình IAM thường tách ba khái niệm:

1. **Identity** xác định chủ thể là ai trong hệ thống xác thực.
2. **Membership** xác định chủ thể có quan hệ với tenant nào và membership đang ở trạng thái gì.
3. **Role binding** xác định vai trò được gán cho chủ thể trong một phạm vi cụ thể.

Ví dụ dữ liệu minh họa:

```yaml
identity:
  id: user-lan
  state: ACTIVE

memberships:
  - tenantId: tenant-an-phu
    subjectId: user-lan
    state: ACTIVE
  - tenantId: tenant-binh-minh
    subjectId: user-lan
    state: ACTIVE

roleBindings:
  - tenantId: tenant-an-phu
    subjectId: user-lan
    roleId: tenant_admin
  - tenantId: tenant-binh-minh
    subjectId: user-lan
    roleId: viewer
```

Đây là cấu trúc minh họa, không phải schema bắt buộc cho mọi sản phẩm. Một hệ thống có thể dùng identity riêng cho mỗi tenant; một hệ thống khác dùng identity chung và nhiều membership. Dù chọn cách nào, quan hệ giữa chủ thể, quyền và tenant phải rõ ràng.

Trong mô hình identity chung, thao tác “xóa người dùng khỏi tenant” thường có nghĩa là chấm dứt membership và thu hồi quyền trong tenant đó. Nó không đồng nghĩa với việc xóa identity toàn cục, khóa quyền đăng nhập ở tenant khác hoặc xóa dữ liệu của các tenant khác.

Ví dụ, khi An Phú chấm dứt hợp tác với Lan, quản trị viên An Phú chỉ được thu hồi membership của Lan tại An Phú. Việc Lan vẫn là viewer tại Bình Minh nằm ngoài thẩm quyền đó.

## 4. Quyền thực thi và quyền ủy quyền

Tenant administrator cần đủ quyền để tổ chức tự vận hành, nhưng không nên nhận một quyền `*` thiếu ranh giới. Có thể phân tách quyền theo các nhóm sau:

| Nhóm quyền | Ví dụ hành động | Ranh giới cần kiểm tra |
|---|---|---|
| Quản lý membership | Mời, vô hiệu hóa, gỡ thành viên | Chỉ membership của tenant hiện tại |
| Quản lý nhóm | Thêm thành viên, gán nhóm quản trị bộ phận | Nhóm và membership đều thuộc cùng tenant |
| Quản lý role binding | Gán hoặc thu hồi vai trò | Chỉ vai trò nằm trong danh mục được phép cấp |
| Quản lý cấu hình xác thực | Cấu hình SSO, yêu cầu MFA | Không hạ thấp chính sách nền tảng bắt buộc |
| Xem audit | Đọc sự kiện quản trị của tenant | Không lộ sự kiện hoặc danh tính nhạy cảm của tenant khác |
| Quản lý danh tính ứng dụng | Cấp quyền cho service account của tenant | Không cấp quyền nền tảng hoặc phạm vi ngoài tenant |

**Có quyền sử dụng một chức năng không có nghĩa là được cấp quyền đó cho người khác.** Quyền thực thi và quyền ủy quyền cần được mô hình hóa riêng.

Ví dụ, Lan có quyền đọc audit để thực hiện nhiệm vụ quản trị, nhưng chính sách có thể chỉ cho phép tenant owner cấp vai trò đọc audit cho người khác. Ngược lại, một quản trị viên được ủy quyền chuyên trách có thể cấp một số vai trò nghiệp vụ mà bản thân không trực tiếp sử dụng, nếu chính sách cho phép rõ ràng.

Một quyết định cấp vai trò có thể được mô tả bằng các điều kiện:

```text
Cho phép gán vai trò khi đồng thời thỏa mãn:
  - Người thực hiện có membership ACTIVE trong tenant đích.
  - Người thực hiện có quyền role.assign trong phạm vi đó.
  - Người nhận có membership hợp lệ trong cùng tenant.
  - Vai trò đích thuộc tập vai trò người thực hiện được phép cấp.
  - Quyền của vai trò đích nằm trong giới hạn của tenant.
  - Các điều kiện bổ sung của thao tác được đáp ứng.
```

Tập vai trò được phép cấp có thể hẹp hơn rất nhiều so với tập vai trò tồn tại trong hệ thống. Chẳng hạn, quản trị viên bộ phận được cấp `project_member`, nhưng không được cấp `tenant_owner` hoặc bất kỳ vai trò nền tảng nào.

Nếu cho phép tạo custom role, hệ thống phải kiểm soát cả việc tạo, sửa role và việc gán role. Một người không được phép tự thêm quyền `billing.manage` vào role mà mình đang có rồi dùng role đó để vượt giới hạn. Việc sửa một role đã được gán cho nhiều người cũng là thay đổi quyền của toàn bộ những người đó, không chỉ là sửa một tên gọi.

Giới hạn quyền cần áp dụng cho cả các đường gián tiếp: role kế thừa, role gán qua nhóm, thuộc tính dùng trong ABAC và ánh xạ nhóm từ IdP. Nếu quản trị viên có thể sửa thuộc tính `department` để thỏa chính sách quyền cao hơn, khả năng sửa thuộc tính ấy cũng là một đường cấp quyền cần được bảo vệ.

## 5. Xác định đúng tenant context trong từng yêu cầu

Đăng nhập thành công chỉ chứng minh một bước xác thực. Máy chủ vẫn phải xác minh tenant context và quyền quản trị của chủ thể cho từng thao tác.

Tenant có thể được chỉ định qua URL, tên miền con, phiên làm việc hoặc claim đã được xác minh. Dữ liệu do client gửi chỉ là đầu vào để kiểm tra; bản thân một header hoặc tham số tenant không tạo ra thẩm quyền.

Ví dụ yêu cầu:

```http
POST /tenants/tenant-an-phu/members/user-minh/role-bindings
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "roleId": "project_manager"
}
```

Máy chủ cần gắn kết các thành phần thành một quyết định thống nhất:

```text
Chủ thể đã xác thực
        ↓
Tenant đích đã được phân giải và đối chiếu
        ↓
Membership + quyền của chủ thể trong tenant đó
        ↓
Membership đích + role đích trong cùng phạm vi
        ↓
Chính sách ủy quyền + điều kiện bảo mật của thao tác
        ↓
Thực hiện thay đổi và ghi audit
```

Nếu token hoặc phiên bị giới hạn vào một tenant, tenant được yêu cầu phải phù hợp với giới hạn đó. Nếu identity dùng chung có thể chuyển tenant, máy chủ phải xác minh membership và tính lại quyền theo tenant mới. Không mang vai trò quản trị từ tenant trước sang tenant sau chỉ vì người dùng chuyển lựa chọn trong giao diện.

Ví dụ mã giả cho một thao tác cấp vai trò:

```text
function assignRole(request):
    actor = authenticate(request)
    tenant = resolveAndValidateTenant(request, actor)
    require tenant.state == ACTIVE

    actorMembership = findMembership(tenant.id, actor.id)
    require actorMembership.state == ACTIVE
    require can(actor, "role.assign", tenant.id)

    target = findMembership(tenant.id, request.targetSubjectId)
    require target exists and target.state == ACTIVE

    role = resolveRoleAllowedForTenant(tenant.id, request.roleId)
    require role exists
    require mayDelegate(actor, role, tenant.id)
    require role.permissions within tenant.permissionBoundary

    requireSensitiveActionConditions(actor, tenant, role)

    transaction:
        recheckRelevantAuthorizationState()
        createScopedRoleBinding(tenant.id, target.subjectId, role.id)
        persistAuditEventOrDurableOutbox()

    invalidateAffectedAuthorizationCaches()
```

Mã giả thể hiện các điểm quyết định, không phải một thư viện hay triển khai hoàn chỉnh. Trong hệ thống thực tế, các kiểm tra trạng thái liên quan phải được gắn với cơ chế giao dịch hoặc kiểm soát phiên bản phù hợp để giảm nguy cơ trạng thái thay đổi giữa lúc kiểm tra và lúc ghi.

Các truy vấn tài nguyên phải mang phạm vi tenant. Việc tìm một membership theo cặp `(tenantId, subjectId)` giúp thể hiện rõ quan hệ cần kiểm tra. Chỉ tìm theo `subjectId`, sau đó cập nhật đối tượng tìm được mà không đối chiếu tenant, có thể dẫn tới thay đổi membership sai tổ chức.

Ranh giới này cũng cần tồn tại ở xử lý hàng loạt, export, tìm kiếm, cache và tác vụ nền. Một API an toàn không bù được cho một job nền dùng `subjectId` mà bỏ mất tenant context.

## 6. Vòng đời của một tenant administrator

### 6.1. Khởi tạo quản trị viên đầu tiên

Tenant mới cần một chủ thể có thẩm quyền ban đầu. Quá trình bootstrap phải liên kết đúng người đăng ký, tenant được tạo và hành động nhận quyền quản trị.

Một quy trình có thể gồm:

1. Xác minh người đăng ký theo quy trình của sản phẩm.
2. Tạo tenant ở trạng thái phù hợp.
3. Tạo membership cho chủ thể đã xác minh.
4. Gán vai trò khởi tạo bằng một luồng nội bộ có kiểm soát.
5. Ghi nhận người thực hiện, phương thức khởi tạo và thời điểm.

Không nên dùng quy tắc “ai đăng nhập đầu tiên với một email thuộc tên miền này sẽ trở thành admin” nếu chưa có cơ chế xác minh quyền đại diện và xử lý tranh chấp thích hợp. Việc sở hữu một địa chỉ email không tự chứng minh người đó được quyền quản trị toàn bộ tổ chức.

### 6.2. Mời thêm quản trị viên

Lời mời cần gắn với tenant, người nhận và quyền dự kiến. Một thiết kế thường có thời hạn, trạng thái sử dụng và cơ chế kiểm tra người chấp nhận lời mời.

Chỉ gửi email không đồng nghĩa với việc đã cấp membership hoạt động. Khi người nhận chấp nhận lời mời, hệ thống còn phải kiểm tra lời mời chưa bị thu hồi, chưa hết hạn, chưa được dùng và việc cấp quyền vẫn được chính sách hiện tại cho phép.

Đối với quyền quản trị cao, có thể yêu cầu người mời xác thực lại, người nhận thiết lập MFA và một người thứ hai phê duyệt. Mức kiểm soát phụ thuộc độ nhạy cảm của quyền và mô hình vận hành, không chỉ phụ thuộc tên vai trò.

### 6.3. Nâng quyền tạm thời và thu hồi quyền

Một nhân viên hỗ trợ triển khai có thể cần quyền quản trị trong hai giờ thay vì giữ quyền suốt nhiều tháng. Quyền tạm thời nên có thời điểm bắt đầu, thời điểm hết hạn, lý do và người phê duyệt khi cần.

Khi hết hạn hoặc bị thu hồi, hệ thống cần xử lý role binding, quyền suy ra từ nhóm, cache quyết định quyền và những phiên hoặc credential liên quan. Xóa một dòng role binding nhưng tiếp tục chấp nhận token chứa quyền cũ trong thời gian dài sẽ tạo khoảng trễ thu hồi.

Có thể giảm khoảng trễ bằng kiểm tra quyền ở máy chủ cho thao tác nhạy cảm, phiên bản quyền, cơ chế thu hồi phiên và thời hạn token phù hợp. Không nên tuyên bố thu hồi “ngay lập tức” nếu kiến trúc vẫn chấp nhận credential cũ cho đến khi hết hạn.

### 6.4. Chuyển giao và quản trị viên cuối cùng

Tenant có thể cần tránh tình trạng không còn người quản trị hợp lệ. Tuy nhiên, kiểm tra “số admin lớn hơn một” ở giao diện hoặc trước giao dịch là chưa đủ: hai admin có thể đồng thời tự gỡ quyền và cả hai thao tác đều nhìn thấy người còn lại.

Ràng buộc quản trị viên cuối cùng cần được bảo đảm trong thao tác cập nhật bằng cơ chế nhất quán phù hợp, chẳng hạn khóa dữ liệu liên quan hoặc kiểm tra phiên bản và thử lại có kiểm soát. Hệ thống cũng cần xác định thế nào là một quản trị viên còn khả dụng, vì một role binding trỏ tới tài khoản bị vô hiệu hóa không đảm bảo tenant còn người đăng nhập được.

Cơ chế bảo vệ này không được buộc hệ thống giữ nguyên quyền của một tài khoản đã bị chiếm đoạt. Khi quản trị viên cuối cùng không còn an toàn hoặc không còn truy cập được, cần một quy trình phục hồi riêng có xác minh, phê duyệt và audit để khóa chủ thể có rủi ro và khôi phục quyền quản trị hợp lệ.

## 7. Các thao tác nhạy cảm trong quản trị tenant

### 7.1. Cấu hình SSO và ánh xạ vai trò

Quản trị viên có quyền cấu hình SSO có thể ảnh hưởng đến việc ai được đăng nhập và ai được nhận đặc quyền. Vì vậy, thay đổi IdP, chứng thư, quy tắc ánh xạ nhóm hoặc chính sách đăng nhập phải được coi là thao tác nhạy cảm.

Một luồng quản trị cần giữ liên kết giữa cấu hình federation và tenant cụ thể. Sau khi xác minh phản hồi xác thực theo giao thức sử dụng, ứng dụng vẫn phải ánh xạ chủ thể vào đúng tenant và áp dụng danh mục quyền được phép.

Ví dụ, nhóm `Administrators` từ IdP của An Phú chỉ có ý nghĩa trong ánh xạ đã được cấu hình cho An Phú. Nó không được tự động trở thành vai trò quản trị nền tảng hoặc vai trò quản trị Bình Minh. Trong mô hình identity chung, định danh bên ngoài cũng cần đủ ngữ cảnh để tránh ghép nhầm người dùng từ các nguồn xác thực khác nhau.

Nên có cách thử cấu hình và phục hồi được kiểm soát trước khi buộc toàn bộ tenant sử dụng một cấu hình đăng nhập mới. Tài khoản hoặc cơ chế khẩn cấp, nếu có, phải được bảo vệ và kiểm tra riêng, không trở thành một đường bỏ qua xác thực cho hoạt động hằng ngày.

### 7.2. MFA, phiên và phục hồi tài khoản

Tenant administrator có thể được phép yêu cầu thành viên thiết lập MFA, thu hồi phiên hoặc khởi tạo quy trình phục hồi. Quyền này không có nghĩa là được đọc mật khẩu, lấy secret MFA hay sao chép mã phục hồi của người dùng.

Nếu hỗ trợ đặt lại MFA, hệ thống cần phân biệt giữa “bắt đầu quy trình phục hồi” và “bỏ qua toàn bộ bằng chứng xác minh”. Một admin bị chiếm đoạt không nên có thể âm thầm đặt lại MFA của mọi người rồi chiếm các tài khoản đó mà không để lại dấu vết hoặc vượt qua kiểm soát bổ sung.

Với identity dùng chung nhiều tenant, thay đổi một phương thức xác thực toàn cục có thể ảnh hưởng nhiều tổ chức. Khi đó, quyền quản trị membership của một tenant không đủ để mặc nhiên thay đổi phương thức xác thực chung của chủ thể.

### 7.3. Hỗ trợ truy cập thay người dùng

Một số sản phẩm có chức năng hỗ trợ thao tác thay người dùng hoặc mở phiên hỗ trợ. Đây là một quyền riêng, không nên tự động đi kèm mọi vai trò tenant administrator.

Nếu có chức năng này, cần thể hiện rõ ai là người thực hiện thực tế, đang thao tác dưới ngữ cảnh của ai, tenant nào, lý do gì và trong thời hạn nào. Audit phải giữ được danh tính người thực hiện thực tế; không ghi mọi hành động như thể chính người dùng đích tự thực hiện.

Tùy mô hình sản phẩm, phiên hỗ trợ có thể cần được phê duyệt, giới hạn đọc và chặn các thao tác như đổi chủ sở hữu hoặc xuất credential. Việc không phải nhập mật khẩu của người dùng đích không làm cho phiên hỗ trợ trở thành hoạt động ít đặc quyền.

## 8. Audit và khả năng truy trách nhiệm

Thao tác quản trị làm thay đổi ai có quyền truy cập nên cần được ghi nhận đủ để điều tra. Một sự kiện có ích thường chứa:

- Tenant của thao tác.
- Chủ thể thực hiện thực tế và chủ thể được đại diện, nếu có.
- Hành động, đối tượng và phạm vi bị thay đổi.
- Trạng thái trước và sau ở mức cần thiết.
- Kết quả, thời điểm, mã yêu cầu và lý do hoặc tham chiếu phê duyệt.

Ví dụ sự kiện minh họa:

```json
{
  "eventType": "TENANT_ROLE_ASSIGNED",
  "tenantId": "tenant-an-phu",
  "actorId": "user-lan",
  "targetSubjectId": "user-minh",
  "roleId": "project_manager",
  "result": "SUCCESS",
  "requestId": "req-1042",
  "approvalRef": "approval-27"
}
```

Ví dụ chỉ thể hiện một phần trường của sự kiện; hệ thống thực tế cần bổ sung các trường phù hợp với yêu cầu vận hành. Không ghi access token, mật khẩu, secret MFA hoặc mã mời vào audit. Những dữ liệu nhạy cảm khác cũng cần được giảm thiểu và giới hạn người đọc.

Tenant administrator có thể được quyền xem audit của tenant mình nhưng không nên tùy ý sửa hoặc xóa dấu vết quản trị của chính mình. Khi một thao tác nhạy cảm yêu cầu audit tin cậy, thiết kế cần tránh tình huống thay đổi quyền đã thành công nhưng sự kiện bị mất do lỗi giữa hai lần ghi. Một cách triển khai là ghi thay đổi và sự kiện hoặc durable outbox trong cùng giao dịch, rồi chuyển sự kiện sang hệ thống audit.

Các yêu cầu quản trị bị từ chối cũng có giá trị quan sát. Chẳng hạn, nhiều lần thử gán vai trò ngoài danh mục hoặc nhiều lần truy cập tenant khác có thể là dấu hiệu cấu hình sai, lỗi ứng dụng hoặc một tài khoản quản trị bị lạm dụng.

## 9. Tình huống xuyên suốt: quản trị viên của hai tenant

Lan đang mở An Phú ở một tab trình duyệt và Bình Minh ở tab khác. Tại An Phú, Lan có vai trò tenant administrator; tại Bình Minh, Lan chỉ là viewer.

Lan muốn cấp quyền `project_manager` cho Minh trong An Phú. Một kết quả đúng cần đáp ứng các điều kiện sau:

1. Yêu cầu được xác thực là của Lan và được xử lý trong tenant An Phú.
2. Membership của Lan tại An Phú còn hoạt động và có quyền gán vai trò.
3. Minh có membership hợp lệ tại An Phú.
4. `project_manager` là vai trò Lan được phép cấp trong An Phú.
5. Thay đổi được ghi đúng phạm vi, có audit và được phản ánh vào cơ chế tính quyền.

Những biến thể dưới đây phải được xử lý theo ranh giới quyền:

| Biến thể của yêu cầu | Quyết định mong đợi | Căn cứ |
|---|---|---|
| Lan đổi URL sang tenant Bình Minh | Từ chối cấp vai trò | Lan chỉ là viewer tại Bình Minh |
| Lan giữ URL An Phú nhưng chọn membership chỉ thuộc Bình Minh | Từ chối | Đối tượng đích không thuộc tenant của thao tác |
| Lan chọn role quản trị nền tảng | Từ chối | Role vượt giới hạn tenant và phạm vi ủy quyền |
| Lan đã bị thu hồi vai trò tại An Phú nhưng giao diện còn nút quản trị | Từ chối theo trạng thái quyền hiệu lực | Nút giao diện không cấp thẩm quyền |
| Lan mời Minh làm admin nhưng lời mời đã bị thu hồi trước khi Minh chấp nhận | Từ chối sử dụng lời mời | Trạng thái lời mời phải được kiểm tra khi sử dụng |
| Lan cấp một vai trò hợp lệ nhưng ghi sự kiện audit bắt buộc thất bại trước khi giao dịch hoàn tất | Không hoàn tất thay đổi theo thiết kế giao dịch đã chọn | Thay đổi đặc quyền phải đi cùng bằng chứng audit tin cậy |

Tình huống cho thấy một nhãn `isAdmin=true` toàn cục không đủ để ra quyết định. Hệ thống cần biết **ai**, đang thao tác **trong tenant nào**, với **hành động gì**, lên **đối tượng nào**, và theo **điều kiện ủy quyền nào**.

## 10. Những lỗi thiết kế thường gặp

**Chỉ ẩn nút quản trị ở giao diện.** Người dùng vẫn có thể gọi API trực tiếp. Quyền phải được kiểm tra tại điểm thực thi phía máy chủ.

**Tin `tenantId` từ client mà không đối chiếu.** Tenant do client chọn phải được liên kết với membership, phiên hoặc token hợp lệ và tài nguyên đích.

**Dùng `isAdmin` chung cho mọi tenant.** Cần xác định role binding hoặc permission trong phạm vi tenant cụ thể; chuyển tenant phải tính lại quyền.

**Cho phép admin cấp mọi role trong danh mục.** Danh mục role có thể chứa quyền chỉ nền tảng hoặc tenant owner được cấp. Cần kiểm tra phạm vi ủy quyền và giới hạn quyền của tenant.

**Bảo vệ thao tác gán role nhưng bỏ ngỏ việc sửa nhóm hoặc thuộc tính.** Các đường cấp quyền gián tiếp cần cùng mức kiểm soát với đường gán trực tiếp.

**Xóa membership rồi cho rằng mọi quyền đã biến mất.** Cần xử lý phiên, cache, credential và thời hạn hiệu lực thực tế của quyết định quyền.

**Cho tenant admin xóa identity dùng chung.** Thu hồi tư cách thành viên trong một tenant không cho phép phá hủy tài khoản hoặc quyền ở tenant khác.

**Giữ quy tắc quản trị viên cuối cùng chỉ ở giao diện.** Những thay đổi đồng thời có thể làm tenant mất toàn bộ quản trị viên. Ràng buộc phải được bảo đảm trong thao tác cập nhật.

**Cho admin toàn quyền chỉnh audit.** Người có đặc quyền cần được giám sát bằng dấu vết mà chính họ không dễ dàng thay đổi.

## 11. Câu hỏi tự kiểm tra

1. Vì sao Lan là admin của An Phú nhưng không thể dùng cùng quyền đó khi mở tenant Bình Minh?
2. Việc gỡ một membership khác gì với việc khóa identity dùng chung?
3. Nếu một admin không được cấp `tenant_owner`, tại sao việc cho admin sửa custom role hoặc ánh xạ nhóm vẫn có thể tạo đường nâng quyền?
4. Khi token còn hiệu lực sau lúc thu hồi vai trò, hệ thống cần làm gì để thao tác quản trị không tiếp tục sử dụng quyền cũ quá mức chấp nhận?
5. Vì sao kiểm tra số lượng admin trước giao dịch có thể không bảo vệ được quản trị viên cuối cùng?

Một thiết kế tenant administrator vững chắc kết hợp phạm vi tenant rõ ràng, quyền ủy quyền có giới hạn, vòng đời đặc quyền được quản lý và audit có thể truy trách nhiệm. Tenant được tự quản lý những gì thuộc thẩm quyền của mình, trong khi mọi quyết định truy cập vẫn được kiểm tra theo chủ thể, tài nguyên và trạng thái hiện tại.
