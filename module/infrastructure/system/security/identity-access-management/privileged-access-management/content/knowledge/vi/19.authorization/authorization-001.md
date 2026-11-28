# RBAC cho PAM

## 1. Vai trò trả lời câu hỏi ai được làm gì

Role-Based Access Control (RBAC) là mô hình tổ chức quyền thông qua vai trò. Thay vì cấp từng permission trực tiếp cho từng người, hệ thống gán permission cho role và gán người dùng vào role phù hợp với trách nhiệm.

Trong PAM, các nhiệm vụ rất khác nhau: đề nghị truy cập, phê duyệt yêu cầu, mở phiên, luân chuyển credential, xem bằng chứng hoặc quản trị chính nền tảng. Nếu tất cả được gom vào một role “PAM Admin”, người chỉ cần vận hành một chức năng có thể nhận khả năng đọc secret hoặc tự mở rộng quyền ngoài nhu cầu.

Ví dụ, một kỹ sư được phép mở phiên chẩn đoán production sau phê duyệt không cần có quyền xem mật khẩu quản trị. Người kiểm toán được đọc một số bằng chứng không cần có quyền sửa policy. Người quản trị cấu hình broker không mặc nhiên cần mở phiên tới mọi máy đích.

Mục tiêu của RBAC trong PAM là làm rõ những ranh giới đó, giảm cấp quyền tùy tiện và giúp giải thích vì sao một hành động được cho phép. Tuy nhiên, kiểm tra role không thay thế toàn bộ quyết định truy cập: scope, grant, thời hạn, quan hệ với đối tượng và điều kiện phiên vẫn phải được thực thi.

Bài học thuộc chương Authorization, kết hợp RBAC với least privilege, JIT/JEA, vault, quản lý credential, giám sát phiên và bằng chứng kiểm toán. Các role, permission và cấu hình bên dưới là mô hình minh họa; tên gọi không phải chuẩn bắt buộc hoặc cấu hình của một sản phẩm cụ thể.

## 2. Những thành phần cần phân biệt

NIST mô tả RBAC thông qua quan hệ giữa người dùng, vai trò và quyền; mô hình có thể bổ sung phân cấp vai trò và các ràng buộc. [NIST — Role Based Access Control](https://csrc.nist.gov/projects/role-based-access-control)

| Thành phần | Ý nghĩa | Ví dụ trong PAM |
|---|---|---|
| Subject | Chủ thể được xét quyền | Người dùng hoặc danh tính dịch vụ đã xác minh |
| Role | Tập khả năng gắn với một trách nhiệm | Người duyệt truy cập, người xem bằng chứng |
| Permission | Hành động được phép đối với loại đối tượng hoặc đối tượng xác định | Quyết định request, mở phiên, đọc secret |
| User-role assignment | Quan hệ gán chủ thể vào vai trò | Bình có role người duyệt |
| Permission-role assignment | Quan hệ gán khả năng cho vai trò | Role người duyệt có quyền ghi quyết định |
| Role activation/session | Những vai trò được sử dụng trong một phiên theo mô hình | Kích hoạt một tập con vai trò được gán |
| Constraint | Điều kiện hạn chế việc gán hoặc sử dụng quyền | Không tự duyệt request của mình |

Cần phân biệt **permission** với **role name**. Một role tên “Viewer” có thể đọc metadata, recording nhạy cảm hoặc thậm chí secret, tùy định nghĩa thực tế. Tên role không thay cho việc kiểm tra tập khả năng.

Cũng cần phân biệt role với nhóm danh tính. Một nhóm có thể là nguồn gán role, nhưng quan hệ nhóm, lồng nhóm và đồng bộ thành viên phải được quản lý. Việc thuộc nhóm không cho phép client tự khai mọi quyền mà nhóm có thể được ánh xạ tới.

Một hệ thống PAM cần ghi rõ những phần mở rộng như assignment theo tenant, scope hoặc điều kiện thời gian. Không nên gọi mọi logic đó là tính năng tự có của RBAC cơ bản.

## 3. Phân biệt quyền trong PAM và quyền trên hệ thống đích

Một điểm dễ nhầm là có hai không gian quyền:

| Không gian | Đối tượng được bảo vệ | Ví dụ |
|---|---|---|
| PAM control plane | Request, grant, vault object, broker config, recording, policy | Ai được duyệt, sửa role, xem bằng chứng? |
| Hệ thống đích | Máy chủ, cơ sở dữ liệu, cloud API, tài khoản hoặc dịch vụ | Tài khoản phiên thực sự được đọc hay sửa gì? |

Role trong PAM quyết định khả năng sử dụng nền tảng. Role hoặc tài khoản đích quyết định khả năng thực hiện trên tài nguyên. Hai lớp cần được ánh xạ có chủ ý.

Ví dụ, permission `session.open` có thể chỉ cho mở một phiên đã được grant tới một máy cụ thể. Nó không tự giới hạn shell quản trị toàn quyền trên máy đó thành chỉ đọc. Nếu tác vụ cần chẩn đoán, account/profile đích hoặc cơ chế JEA phải thực thi phạm vi tương ứng.

Ngược lại, tài khoản đích có quyền cao không có nghĩa mọi người dùng PAM đều được sử dụng nó. PAM cần kiểm soát ai được yêu cầu, ai được kích hoạt, đường truy cập nào được phép và có được nhìn thấy credential hay không.

### Dùng credential khác với đọc credential

Cần tách ít nhất hai khả năng:

- Cho phép broker sử dụng credential để mở phiên cho một chủ thể được cấp quyền.
- Cho phép chủ thể đọc hoặc xuất credential.

Nếu chỉ cần mở phiên qua broker, không nên tự gán thêm khả năng đọc mật khẩu. Khi secret đã được tiết lộ, người nhận có thể sử dụng ngoài đường phiên nếu hệ thống không có kiểm soát khác. Hết hạn grant trong PAM không tự làm secret đó mất hiệu lực trên đích.

## 4. Thiết kế role theo nhiệm vụ có thể giải thích

Một bộ role tham khảo:

| Role minh họa | Nhiệm vụ chính | Khả năng không tự đi kèm |
|---|---|---|
| Access requester | Tạo và theo dõi yêu cầu trong phạm vi được phép | Duyệt yêu cầu, đọc secret, tự cấp grant |
| Diagnostic session user | Mở phiên chẩn đoán khi có grant và điều kiện phù hợp | Mở shell rộng, dùng tài khoản khác, xuất credential |
| Access approver | Xem và quyết định request thuộc trách nhiệm | Tự duyệt, sửa policy, tự dùng quyền của người được duyệt |
| Credential operator | Thực hiện tác vụ quản lý credential theo profile | Đọc giá trị secret nếu tác vụ không cần tiết lộ |
| Session operator | Giám sát hoặc kết thúc phiên trong phạm vi hỗ trợ | Mở phiên tùy ý hoặc xem mọi recording |
| Evidence reviewer | Xem tập bằng chứng được giao | Sửa log, xóa recording, sử dụng credential |
| Platform configuration administrator | Quản lý thành phần nền tảng trong phạm vi được giao | Mặc nhiên đọc secret hoặc cấp mọi role |
| Access administrator | Quản lý một tập assignment theo thẩm quyền | Tự gán quyền cao hơn hoặc sửa mọi định nghĩa role |

Đây không phải danh sách role phải áp dụng nguyên vẹn. Một tổ chức nhỏ có thể kết hợp một số nhiệm vụ; một hệ thống lớn có thể tách thêm. Điều quan trọng là biết khả năng nào được kết hợp và điều đó có tạo xung đột hay đường tăng quyền không.

### 4.1. Permission nên diễn đạt hành động cụ thể

Các permission minh họa có thể là:

```text
request.create
request.read
request.decide
grant.activate
session.open
session.terminate
session.recording.read
credential.use_via_broker
credential.value.read
credential.rotate
role.definition.update
role.assignment.create
audit.export
```

Một chuỗi như `session.manage` thường cần được phân rã nếu nó bao gồm cả xem, mở, điều khiển và đóng phiên của người khác. Tương tự, `vault.manage` có thể che giấu quyền sửa policy, đọc secret và xóa dữ liệu.

Tách permission giúp đánh giá tác động và cấp đúng quyền hơn. Nhưng không nên tạo quá nhiều permission không phản ánh khác biệt thực thi. Danh mục phải khớp với API và những điểm bảo vệ thực sự.

### 4.2. Permission mới không nên tự rơi vào role rộng

Khi thêm một API đọc credential hoặc export recording, cần quyết định rõ role nào nhận khả năng đó. Wildcard như “mọi hành động hiện tại và tương lai” có thể làm một role tăng quyền mà không có lần xem xét riêng.

Role mạnh vẫn có thể cần trong vận hành, nhưng phạm vi và quyền thay đổi của nó phải được quản trị. Không dùng một wildcard chỉ để tránh phải cập nhật danh mục khi có tính năng mới.

## 5. Scope phải đi cùng assignment và đối tượng

Một người có role người duyệt cho hệ thống thanh toán không đương nhiên được duyệt cho hệ thống nhân sự. Hệ thống cần xét cả **permission** và **scope**.

Scope có thể mô tả tenant, môi trường, nhóm tài nguyên hoặc đối tượng cụ thể. Đây là phần của thiết kế authorization kết hợp với RBAC; cách biểu diễn tùy sản phẩm.

Mô tả assignment minh họa:

```yaml
assignment_ref: assignment-payments-approver-17
subject_ref: principal-reviewer-17
role_ref: pam-access-approver-v2
scope_ref: tenant-payments-production
state: active
valid_from: "2026-11-26T08:00:00+07:00"
valid_until: "2026-11-26T18:00:00+07:00"
assignment_policy_ref: access-reviewers-v3
```

Đây là dữ liệu giả. Máy chủ phải phân giải subject, role, scope và thời hạn từ nguồn có thẩm quyền, không dùng trực tiếp payload của client như một assignment đã có hiệu lực.

### 5.1. Không trộn permission của scope này với scope khác

Giả sử An có:

| Assignment | Permission | Scope |
|---|---|---|
| A | Xem metadata | Tenant thanh toán |
| B | Đọc một tập secret | Tenant phòng lab |

Nếu hệ thống gom thành hai danh sách độc lập “permission của An” và “scope của An”, nó có thể ghép quyền đọc secret từ B với scope production từ A. Đây là một kết quả không nằm trong assignment nào.

Cách đánh giá cần giữ quan hệ giữa role, permission và scope. Một hành động phải được hỗ trợ bởi assignment hợp lệ cho đúng đối tượng, rồi tiếp tục chịu các ràng buộc bắt buộc khác.

### 5.2. Tenant và tài nguyên phải được xác minh phía máy chủ

Client có thể gửi resource ID hoặc tenant selector để chỉ ra đối tượng muốn thao tác. Máy chủ vẫn cần kiểm tra quan hệ thực tế của đối tượng và quyền của actor.

Không coi một header `tenant_id`, hidden field hoặc tên folder do client gửi là căn cứ đủ. Một ID khó đoán cũng không thay thế kiểm tra authorization ở mức đối tượng.

Scope động cần có quy tắc thay đổi thành viên. Khi thêm tài nguyên vào một nhóm đã được cấp quyền, cần biết quyền có mở rộng theo không, ai được thay nhóm và có yêu cầu đánh giá lại grant hay không.

## 6. Role được gán, role đủ điều kiện và quyền đang dùng

Trong RBAC có khái niệm phiên cho phép kích hoạt một tập con vai trò đã được gán. Nhờ đó, người dùng không nhất thiết phải dùng mọi vai trò họ có trong cùng một ngữ cảnh. [NIST — RBAC FAQs](https://csrc.nist.gov/Projects/role-based-access-control/faqs)

Trong PAM, còn cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Role definition | Tập khả năng được định nghĩa |
| Assignment | Chủ thể được gắn với role và phạm vi |
| Eligibility | Chủ thể có thể đề nghị kích hoạt theo điều kiện |
| Activation | Quyền được đưa vào trạng thái sử dụng có hạn |
| Grant | Bản ghi quyền cụ thể cùng tài nguyên, điều kiện và thời gian |
| Session | Lần thực sự dùng quyền qua một đường truy cập |

Các thuật ngữ và cách liên kết phụ thuộc sản phẩm. Ví dụ, Microsoft Entra PIM phân biệt eligible assignment cần kích hoạt với active assignment, và hỗ trợ cơ chế kích hoạt theo thời gian hoặc phê duyệt. [Microsoft — Privileged Identity Management](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure)

Không được coi eligibility là quyền active. Nếu một API chỉ nhìn thấy role name trong token mà bỏ qua trạng thái kích hoạt, người đủ điều kiện có thể dùng quyền trước khi hoàn tất điều kiện bắt buộc.

### Ví dụ JIT

An đủ điều kiện làm người dùng phiên chẩn đoán trong nhóm tài nguyên thanh toán. Điều đó cho An quyền đề nghị kích hoạt, không phải quyền mở mọi phiên.

Khi có một grant hợp lệ cho máy A trong 20 phút, An mới được sử dụng đúng phiên/profile đã cấp. Một assignment vẫn còn hiệu lực ngày mai không kéo dài grant hôm nay. Một phiên PAM còn đăng nhập cũng không làm grant đã hết hạn sống lại.

Nếu role “admin production” luôn active và chỉ credential được phát ngắn hạn, mức quyền thường trực vẫn cần được đánh giá. Tuổi thọ credential và thời gian quyền nền có thể được sử dụng là hai câu hỏi khác nhau.

## 7. Phân cấp role phải phản ánh khả năng, không chỉ chức danh

Role hierarchy có thể giúp tái sử dụng tập permission. Ví dụ, một role quản lý metadata có thể bao gồm khả năng xem metadata. Nhưng không nên mặc định người có chức danh cao hơn phải thừa kế mọi quyền nhạy cảm của cấp dưới.

Một sơ đồ thiết kế minh họa:

```text
resource-metadata-editor
    bao gồm resource-metadata-reader

session-operator
    có tập quyền giám sát/kết thúc phiên được chọn
    không mặc nhiên bao gồm credential.value.read

platform-config-admin
    có tập quyền cấu hình được giao
    không mặc nhiên bao gồm access-approver hoặc evidence-exporter
```

Cần hiểu đúng chiều thừa kế trong engine thực tế. Việc đọc sai một quan hệ cha–con có thể làm cấp quyền theo chiều ngược với ý định.

Khi một role thừa kế role khác, việc sửa role được thừa kế có thể ảnh hưởng nhiều assignment và nhiều người. Do đó, thay đổi hierarchy cần được xem xét cùng những ràng buộc SoD và scope, không chỉ kiểm tra một role đơn lẻ.

Một hierarchy tiện quản trị nhưng dẫn đến nhiều role cùng nhận khả năng đọc secret có thể làm mất ranh giới nhiệm vụ. Đôi khi dùng những role độc lập với permission được định nghĩa rõ dễ kiểm tra hơn một cây thừa kế sâu.

## 8. Separation of duties trong quy trình PAM

NIST phân biệt static separation of duty liên quan tới assignment vai trò và dynamic separation of duty liên quan tới vai trò được kích hoạt trong phiên. [NIST — RBAC model components](https://csrc.nist.gov/Projects/role-based-access-control/faqs)

### 8.1. Ràng buộc ở lúc gán

Một thiết kế có thể cấm một người cùng có quyền sửa policy quyền truy cập và quyền phê duyệt thay đổi policy đó. Khi tạo hoặc sửa assignment, hệ thống phải kiểm tra tổ hợp role cùng những quyền có thể thừa kế.

Nếu chỉ kiểm tra tên role trực tiếp, một role tổng hợp hoặc nhóm lồng có thể đưa người đó trở lại tổ hợp bị cấm. Cần đánh giá quyền và quan hệ hiệu lực theo thiết kế.

### 8.2. Ràng buộc lúc sử dụng

Một người có thể đủ điều kiện cho nhiều trách nhiệm nhưng chỉ được dùng một tập vai trò phù hợp trong một phiên hoặc ngữ cảnh hoạt động. Tuy nhiên, điều đó chưa đủ để ngăn tự duyệt một request cụ thể.

Quy tắc “người nhận quyền không được duyệt yêu cầu của mình” cần xét actor, requester, beneficiary và quan hệ với đúng request. Chỉ ngăn kích hoạt hai role trong cùng một phiên có thể vẫn cho người đó dùng hai phiên khác nhau để thực hiện hai bước.

Đối với quy trình cần hai người thật khác nhau, cần xử lý quan hệ nhiều tài khoản của cùng một người theo nguồn danh tính có thẩm quyền. Hai account ID không tự chứng minh hai người độc lập.

### 8.3. Quản trị role cũng cần phân tách trách nhiệm

Một approver không nên tự sửa role của mình để trở thành access administrator rồi tự gán quyền. Một access administrator cũng không mặc nhiên được sửa mọi role definition để vượt giới hạn được giao.

Có thể giới hạn:

- Tập role mà người quản trị được phép gán.
- Tập subject và scope được quản lý.
- Khả năng tự gán hoặc gán cho người gửi thay.
- Role tối đa hoặc những permission không được ủy quyền.
- Thời hạn, approval và yêu cầu xác thực cho thay đổi.
- Quyền sửa chính sách phân quyền của cơ chế gán đó.

Đây là bài toán administrative authorization của nền tảng. Một permission `role.assignment.create` không có giới hạn có thể trở thành khả năng cấp mọi quyền.

## 9. Một quyết định truy cập cần nhiều điều kiện hơn role

OWASP khuyến nghị deny by default, kiểm tra permission trên mọi request và không dùng kiểm tra phía client làm điểm quyết định. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

Trong mô hình PAM của bài, có thể mô tả ý nghĩa quyết định như sau:

```text
Cho phép hành động khi:
    actor đã được xác thực phù hợp
    AND có assignment/activation còn hiệu lực
    AND role cấp permission cần thiết
    AND assignment áp dụng cho đúng scope và đối tượng
    AND grant hợp lệ nếu hành động cần grant
    AND không vi phạm ràng buộc SoD hoặc hạn chế bắt buộc
    AND đáp ứng thời gian, MFA, thiết bị và điều kiện kênh
    AND những nghĩa vụ thực thi bắt buộc có thể được đáp ứng
```

Đây là biểu thức ý nghĩa cho một thiết kế cụ thể, không phải thuật toán chung của mọi policy engine. Quy tắc kết hợp allow/deny, thứ tự đánh giá và ý nghĩa khi thiếu dữ liệu cần được định nghĩa rõ trong implementation.

### 9.1. Giữ quyết định gần điểm thực thi

Một gateway có thể kiểm tra quyền sơ bộ, nhưng dịch vụ xử lý vẫn cần bảo đảm hành động áp dụng cho đúng đối tượng. Đặc biệt, một API nội bộ không được chấp nhận vai trò do client tùy ý khai chỉ vì request đã đi qua gateway.

Nếu broker dùng danh tính dịch vụ để gọi vault, cần giữ liên kết với actor, grant và phạm vi đã được quyết định. Danh tính mạnh của broker không được biến mọi tham số do người dùng gửi thành một yêu cầu được phép.

### 9.2. Nghĩa vụ phải được thực thi

Một quyết định có thể yêu cầu recording, dùng profile nhất định hoặc không tiết lộ credential. Nếu điểm thực thi không đáp ứng được, không được báo hành động đã tuân thủ chỉ vì role hợp lệ.

Ví dụ, người dùng phiên chẩn đoán có quyền mở một phiên có recording. Recorder lỗi không tự cho phép chuyển sang kết nối trực tiếp không ghi. Đường thay thế phải có quyết định phù hợp với điều kiện thực tế.

### 9.3. Đã duyệt không phải điều kiện vĩnh viễn

Giữa lúc người dùng được duyệt và lúc kích hoạt, assignment có thể hết hạn, grant bị thu hồi hoặc tài nguyên đổi trạng thái. Điểm kích hoạt phải kiểm tra theo mô hình hiệu lực hiện hành đã định nghĩa.

Cũng cần quy định những điều kiện nào được cố định theo phiên bản quyết định và những điều kiện nào phải luôn còn đúng. Không để các dịch vụ hiểu khác nhau về ý nghĩa “đã được duyệt”.

## 10. Ví dụ: mở phiên chẩn đoán mà không đọc secret

### 10.1. Các chủ thể và vai trò

| Chủ thể | Role và scope minh họa | Trách nhiệm |
|---|---|---|
| An | Diagnostic session user, đủ điều kiện trong payments production | Đề nghị và thực hiện chẩn đoán |
| Bình | Access approver trong cùng phạm vi | Xem xét request của người khác |
| Chi | Evidence reviewer cho tập bằng chứng được giao | Kiểm tra hoạt động sau đó |
| Dũng | Platform configuration administrator | Vận hành cấu hình nền tảng theo phạm vi riêng |

Không ai trong bảng tự có quyền đọc mọi secret chỉ nhờ tên role.

### 10.2. Định nghĩa role minh họa

```yaml
role_ref: pam-diagnostic-session-user-v2
permissions:
  - request.create
  - request.read_own
  - grant.activate_own
  - session.open_with_grant
  - session.read_own_metadata
excluded_capabilities:
  - credential.value.read
  - request.decide
  - role.definition.update
  - role.assignment.create
```

Đây là mô tả ý định, không phải syntax chuẩn của một engine. Trường `excluded_capabilities` dùng để giải thích thiết kế; nó không tự trở thành một explicit deny ở sản phẩm thực tế. Cần xác định cách engine xử lý những permission nhận từ các role khác.

Nếu An có thêm một role thật sự cấp `credential.value.read`, phải đánh giá tổng quyền hiệu lực và những hạn chế áp dụng. Không coi việc permission vắng trong role chẩn đoán là bằng chứng An không thể nhận nó qua đường khác.

### 10.3. Request, grant và phiên

An gửi request cho máy ứng dụng A, profile chẩn đoán chỉ đọc, thời lượng tối đa 20 phút và recording bắt buộc. Bình có permission quyết định nhưng máy chủ vẫn kiểm tra scope, quan hệ với request và quy tắc tự duyệt.

Sau khi được chấp thuận, hệ thống tạo grant cho đúng subject, máy A, profile và thời hạn. Khi An kích hoạt, PAM kiểm tra assignment/activation, grant, độ mới xác thực và các điều kiện khác.

Broker dùng credential theo tích hợp vault mà không tiết lộ giá trị cho An. Tài khoản đích và JEA thực thi khả năng chẩn đoán; RBAC tại portal không phải lớp duy nhất hạn chế lệnh.

Chi chỉ được xem bằng chứng trong scope và mục đích được cấp. Recording có thể chứa dữ liệu nhạy cảm, nên role reviewer không được mặc định cho xem mọi phiên của mọi tenant.

### 10.4. Một số quyết định cần rõ

| Hành động | Kết quả theo mô hình |
|---|---|
| An mở đúng phiên khi grant còn hiệu lực | Có thể cho phép khi mọi điều kiện đáp ứng |
| An đọc mật khẩu vì đã mở được phiên | Từ chối; hai khả năng khác nhau |
| An thay máy A bằng máy B ngoài grant | Từ chối dù role vẫn đúng |
| Bình duyệt request ngoài scope được giao | Từ chối |
| Bình gửi thay An rồi duyệt nếu policy cấm quan hệ đó | Từ chối theo ràng buộc |
| Chi export recording ngoài tập được giao | Từ chối |
| Dũng sửa role để tự đọc secret | Phải bị chặn hoặc chịu cơ chế đặc quyền riêng theo thiết kế |
| Grant hết hạn nhưng portal vẫn đăng nhập | Không được mở phiên mới dựa trên grant đó |

## 11. Vòng đời role, assignment và thu hồi

### 11.1. Role definition cần owner và phiên bản

Nên biết role phục vụ nhiệm vụ nào, ai sở hữu, gồm permission gì, sử dụng ở đâu và thay đổi tác động tới ai. Một lần thêm permission vào role có thể tăng quyền cho nhiều người mà không thay assignment nào.

Quy trình thay đổi cần xem xét phạm vi ảnh hưởng, xung đột SoD, hierarchy và những grant có thể liên quan. Role đã được đổi không nên làm grant cũ âm thầm mở rộng ngoài nội dung đã chấp thuận.

Tùy thiết kế, có thể cố định profile/role version cho một quyết định hoặc yêu cầu đánh giá lại khi thay đổi đáng kể. Những hạn chế khẩn cấp vẫn cần cơ chế thu hồi riêng; cố định một phiên bản không được dùng làm lý do bỏ qua quyết định thu hồi có thẩm quyền.

### 11.2. Joiner, mover, leaver và recertification

Khi một người nhận nhiệm vụ mới, cần cấp role phù hợp thay vì sao chép toàn bộ quyền của một đồng nghiệp. Khi chuyển nhóm, phải xem quyền cũ còn cần không; khi rời tổ chức, cần xử lý assignment, phiên và grant liên quan.

Đánh giá định kỳ nên nhìn tổng quyền hiệu lực, gồm nhóm lồng, role thừa kế, assignment theo nhiều scope và quyền ủy quyền. Chỉ xem role trực tiếp có thể bỏ sót đường sử dụng quyền thực tế.

Một quyền ít được dùng không tự là quyền không cần thiết; nhưng cần có owner xác nhận nhu cầu. Ngược lại, quyền được dùng thường xuyên vẫn có thể quá rộng so với nhiệm vụ.

### 11.3. Xóa assignment không tự kết thúc mọi phiên

Một token hoặc cache có thể còn chứa role cũ. Một phiên broker có thể đã mở; một credential có thể đã được phát hoặc tiết lộ.

Thu hồi cần phân biệt:

1. Ngăn assignment/activation mới.
2. Ngăn hành động mới bằng quyền đã thu hồi.
3. Xử lý grant hoặc credential chịu ảnh hưởng.
4. Kết thúc phiên hiện hữu khi policy yêu cầu.
5. Xác nhận kết quả tại các điểm thực thi.

Nếu chưa xác nhận một lớp đã áp dụng, trạng thái phải phản ánh phần còn chờ. Không báo quyền đã kết thúc toàn bộ chỉ vì bản ghi assignment đã bị xóa.

Cache và token cần có giới hạn hiệu lực cùng cách xử lý thay đổi phù hợp. Refresh cache không được coi như gia hạn một assignment hết hạn.

## 12. Giới hạn của RBAC và cách kết hợp điều kiện

Role phù hợp để mô tả trách nhiệm tương đối ổn định: người duyệt, người vận hành, người xem bằng chứng. Những điều kiện như đúng tenant, đúng người được cấp grant, đúng thiết bị và đúng thời điểm thường cần thêm dữ liệu và logic.

Nếu tạo một role riêng cho mọi tổ hợp nhóm, tài nguyên, thời gian, thiết bị và tác vụ, số role có thể tăng rất nhanh. Khi đó, khó hiểu sự khác biệt và khó quản trị vòng đời.

Một cách tổ chức có thể là:

```text
Role:
    mô tả loại khả năng theo trách nhiệm

Assignment/scope:
    chỉ ra chủ thể và phạm vi được quản lý

Grant:
    chỉ ra quyền cụ thể có thời hạn cho công việc

Điều kiện:
    kiểm tra ngữ cảnh, SoD và nghĩa vụ tại lúc dùng
```

Đây là cách phân chia thiết kế, không yêu cầu mọi sản phẩm phải lưu thành bốn bảng. Điều quan trọng là không làm mất quan hệ giữa các phần.

Các thuộc tính bổ sung cần có nguồn có thẩm quyền và độ mới phù hợp. Không thay một role tin cậy bằng điều kiện dựa hoàn toàn trên nhãn do người dùng tự khai.

RBAC ở ứng dụng cũng không tự ngăn một người có quyền quản trị host, cơ sở dữ liệu hoặc bản sao lưu nền tảng sửa dữ liệu ngoài API. Ranh giới bảo vệ thực tế cần xét các đường quản trị này, cùng phân quyền hạ tầng, quản lý credential và bằng chứng thay đổi.

## 13. Bằng chứng cần giải thích được quyết định

Một sự kiện authorization nên giúp trả lời:

- Actor thực tế là ai và đang hành động cho ai nếu có ủy quyền.
- Hành động nào được đề nghị trên đối tượng nào.
- Role và assignment nào hỗ trợ permission đó.
- Scope nào đã được đối chiếu.
- Grant/activation nào đang hiệu lực.
- Policy và role version nào được dùng.
- Điều kiện nào đạt hoặc không đạt.
- Kết quả được thực thi ở vault, broker hoặc đích ra sao.

Không nhất thiết ghi toàn bộ dữ liệu nhạy cảm vào mỗi log. Có thể dùng reference và kho bằng chứng kiểm soát truy cập để nối chuỗi. Không ghi giá trị credential, token phiên hoặc secret chỉ để thuận tiện giải thích quyền.

Audit cần bao gồm cả thay đổi role, assignment, hierarchy, scope và những thao tác quản trị authorization. Người có quyền xem hoặc quản lý request không mặc nhiên được xóa các bằng chứng này.

Một quyết định “allow” chỉ chứng minh thành phần quyết định đã cho phép theo dữ liệu nó có. Bằng chứng thực thi cần thể hiện hành động có được thực hiện, bị lỗi hay chưa xác nhận. Không gộp việc cho phép và việc hoàn thành thành một sự kiện thành công duy nhất.

## 14. Những lỗi thường gặp và thực hành áp dụng

| Lỗi | Tác động | Điều chỉnh |
|---|---|---|
| Dùng một role admin cho mọi nhiệm vụ | Tập trung nhiều khả năng không cần thiết | Tách theo trách nhiệm và tác động |
| Kiểm tra role nhưng bỏ scope | Truy cập chéo tài nguyên hoặc tenant | Giữ quan hệ assignment–permission–scope |
| Trộn permission và scope từ các assignment | Sinh quyền không tồn tại trong assignment nào | Đánh giá theo đúng binding |
| Eligible được coi là active | Bỏ qua bước kích hoạt bắt buộc | Kiểm tra trạng thái và thời hạn thực tế |
| Được mở phiên nên được đọc password | Tăng khả năng dùng ngoài broker | Tách sử dụng credential và tiết lộ credential |
| Cấm hai role cùng phiên là đủ chống tự duyệt | Có thể dùng nhiều phiên hoặc account | Kiểm tra quan hệ actor với đúng request |
| Role admin sửa được mọi role | Có đường tự tăng quyền | Giới hạn administrative authorization |
| Xóa assignment là hoàn tất thu hồi | Phiên, token hoặc credential có thể còn dùng | Đối soát từng lớp thực thi |
| Role tên Viewer nên recording luôn an toàn | Có thể lộ dữ liệu nhạy cảm | Xét loại dữ liệu, scope và mục đích xem |
| Chỉ ẩn nút trên UI | API vẫn có thể nhận hành động trái quyền | Thực thi ở phía có thẩm quyền |

Để thực hành, xây một mô hình lab gồm requester, người dùng phiên chẩn đoán, approver và reviewer. Chọn hai tenant hoặc hai nhóm tài nguyên độc lập để kiểm tra scope.

Lập danh mục permission, role definition và assignment cho từng người. Bổ sung một grant có hạn cho đúng một máy và profile. Viết bảng quyết định cho các hành động hợp lệ và các trường hợp chéo scope, đọc secret ngoài nhiệm vụ, tự duyệt, dùng grant hết hạn và thay role giữa lúc chờ kích hoạt.

Cuối cùng, mô tả cách thu hồi một assignment đang có phiên hoạt động: điểm nào chặn quyền mới, điểm nào xử lý phiên hiện hữu và dữ liệu nào xác nhận kết quả. Nếu một phần chưa thực thi được, cần ghi rõ khoảng trống thay vì chỉ đổi trạng thái trên portal.

Đầu ra cần cho thấy quyền được tổ chức theo trách nhiệm nhưng vẫn bị giới hạn bởi phạm vi và công việc thực tế. Một mô hình RBAC cho PAM có thể kiểm tra được phải giải thích được cả vì sao một thao tác được cho phép và vì sao những thao tác gần giống vẫn bị từ chối.
