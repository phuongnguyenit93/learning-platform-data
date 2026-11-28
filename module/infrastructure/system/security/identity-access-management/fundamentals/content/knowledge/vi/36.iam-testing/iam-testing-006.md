# Role escalation test — Kiểm thử leo thang vai trò và quyền

## 1. Không chỉ kiểm tra người dùng có gọi được API quản trị hay không

**Role escalation test** kiểm tra một chủ thể có thể đạt thêm vai trò hoặc quyền ngoài phạm vi được cho phép bằng cách thay đổi dữ liệu, gọi chức năng hoặc kết hợp các quyền đang có hay không. Chủ thể có thể là người dùng, quản trị viên được ủy quyền hoặc service principal.

Ví dụ, tài khoản thường được phép sửa tên hiển thị. Nếu API cập nhật hồ sơ nhận cả trường `roles` và ghi nó vào tài khoản mà không kiểm tra riêng, người dùng có thể tự trở thành quản trị viên dù giao diện không có chức năng cấp role.

Một lỗi khác không cần sửa trực tiếp role: người dùng được sửa membership của một group, trong khi group đó được ánh xạ sang quyền quản trị. Nếu việc thêm chính mình vào group không được giới hạn đúng, quyền hiệu lực vẫn tăng dù bảng role trực tiếp của tài khoản không đổi.

Trong bài này, các ví dụ là tình huống giả định để thiết kế kiểm thử trên môi trường, tài khoản và dữ liệu được dành cho mục đích đó. Tên endpoint, role và cấu trúc dữ liệu không phải schema bắt buộc của một sản phẩm IAM.

## 2. Xác định rõ quyền được phép thay đổi

### 2.1. Leo thang không đồng nghĩa mọi lần được cấp thêm role

Một quản trị viên được ủy quyền có thể hợp lệ cấp role cho người khác. Một quy trình đặc quyền tạm thời cũng có thể cho phép người dùng kích hoạt quyền sau khi đủ điều kiện. Đây không phải lỗi nếu hành động đáp ứng chính sách.

Lỗi xuất hiện khi chủ thể vượt qua giới hạn về người được cấp, role được cấp, tài nguyên, tenant, thời gian, phê duyệt hoặc điều kiện xác thực. Vì vậy, test cần một chính sách làm nguồn kỳ vọng; không thể mặc định rằng mọi role mới đều phải bị từ chối.

Một mô hình quyết định khái niệm:

```text
can_assign(
    actor,
    target_subject,
    requested_role,
    resource_scope,
    approval_state,
    authentication_context
)
```

Quyền sử dụng một chức năng không tự kéo theo quyền cấp chức năng đó cho người khác. Ngược lại, người quản trị được phép cấp một role cũng không nhất thiết có quyền tự thực hiện mọi chức năng nghiệp vụ của role đó. Khả năng quản lý quyền và khả năng sử dụng quyền phải được mô hình hóa riêng.

### 2.2. Không giả định role luôn tạo thành một thang cấp bậc đơn giản

Tên `Manager`, `Operator` hoặc `Admin` không tự xác định quan hệ quyền trong mọi hệ thống. Hai role có thể chứa các tập quyền khác nhau, hoặc cùng tên nhưng chỉ áp dụng tại hai tenant khác nhau.

Test cần biết quyền hiệu lực theo hành động và phạm vi. Một role quản trị tenant A không tự là quản trị tenant B. Một role quản lý thành viên dự án không tự được sửa chính sách của toàn tổ chức.

### 2.3. Phân biệt với các lỗi liên quan

| Loại kiểm tra | Ví dụ | Quan hệ với role escalation |
|---|---|---|
| Xác thực | Token bị sửa chữ ký phải bị từ chối | Ngăn giả mạo danh tính, nhưng chưa chứng minh kiểm tra quyền cấp role |
| Leo thang theo chức năng hoặc đặc quyền | Thành viên thường tự đạt quyền quản trị | Mục tiêu chính của bài |
| Vượt phạm vi cùng mức quyền | Quản trị tenant A sửa quyền tenant B | Cùng tên role nhưng vượt ranh giới được ủy quyền |
| Truy cập đối tượng trái phép | Người dùng đọc tài liệu của người khác | Có thể xảy ra mà role không thay đổi |
| Vi phạm quy trình cấp quyền | Người yêu cầu tự duyệt khi chính sách cấm | Có thể tạo quyền ngoài cơ chế phê duyệt dự kiến |

OWASP WSTG mô tả kiểm thử privilege escalation nhằm phát hiện việc người dùng đạt thêm chức năng hoặc tài nguyên ngoài quyền dự kiến, bao gồm thay đổi role và thuộc tính liên quan. [OWASP WSTG v4.2 — Testing for Privilege Escalation](https://wstg.owasp.org/v4.2/4-Web_Application_Security_Testing/05-Authorization_Testing/03-Testing_for_Privilege_Escalation/).

## 3. Chuẩn bị ma trận quyền và dữ liệu kiểm thử

### 3.1. Một ma trận giả định

Giả sử ứng dụng có các chính sách sau:

| Chủ thể fixture | Khả năng hợp lệ | Giới hạn cần kiểm tra |
|---|---|---|
| `member-a` | Đọc dữ liệu được cấp và sửa trường hồ sơ cá nhân cho phép | Không sửa role, membership đặc quyền hoặc tenant của chính mình |
| `support-a` | Hỗ trợ một số thao tác tài khoản tại tenant A | Không cấp role quản trị hoặc tác động tài khoản đặc quyền ngoài phạm vi |
| `role-operator-a` | Cấp role `READER` cho thành viên phù hợp tại tenant A | Không cấp `TENANT_ADMIN`, không cấp quyền tại tenant B |
| `role-admin-a` | Quản lý những role thuộc phạm vi được ủy quyền tại tenant A | Không sửa role hệ thống được bảo vệ hoặc bỏ qua quy trình bắt buộc |
| `service-sync-a` | Đồng bộ tập thuộc tính tài khoản được cấu hình | Không tự chuyển thuộc tính nguồn thành đặc quyền nội bộ ngoài mapping |

Đây là chính sách minh họa, không phải mặc định của mọi ứng dụng. Trước khi chạy test thật, cần thay bằng quyền được chủ hệ thống hoặc chủ nghiệp vụ xác nhận.

Mỗi ca nên có actor, target subject, role hoặc policy đích và tài nguyên cụ thể. Cần có ít nhất một ca hợp lệ làm đối chứng cho chức năng được kiểm tra, cùng các ca bị từ chối theo đúng giới hạn.

### 3.2. Ghi nhận trạng thái và quyền hiệu lực ban đầu

Trước request, ghi lại role trực tiếp, group liên quan, các binding hoặc policy có thể bị thay đổi và quyền đối với một tập hành động đại diện. Quan sát này tạo cơ sở so sánh với trạng thái sau test.

Không chỉ đọc một trường `role` từ endpoint hồ sơ. Quyền có thể đến từ group lồng nhau, policy gắn tại tài nguyên, cơ chế ủy quyền, phiên đặc quyền tạm thời hoặc một danh tính workload mà actor được phép sử dụng.

Tài khoản quan sát fixture có thể có quyền đọc trạng thái để xác minh, nhưng request mục tiêu phải dùng đúng credential của actor ít quyền đang được thử. Dùng nhầm phiên quản trị viên trong request là một nguyên nhân khiến test đưa ra kết luận sai.

## 4. Kiểm thử các đường leo thang trực tiếp

### 4.1. API cấp hoặc sửa role

Một endpoint giả định có thể nhận yêu cầu:

```http
POST /tenants/tenant-a/role-assignments
Content-Type: application/json

{
  "subjectRef": "member-a",
  "roleRef": "TENANT_ADMIN",
  "scopeRef": "tenant-a"
}
```

Với chính sách ví dụ, request do `member-a` gửi phải bị từ chối cấp role. Cần kiểm tra riêng các biến thể: cấp cho chính mình, cấp cho một tài khoản khác, đổi role đích, đổi phạm vi và thay target subject sang tenant khác.

Không coi việc target là người khác thì ít rủi ro hơn. Nếu actor có thể cấp role quản trị cho một tài khoản do mình kiểm soát, giới hạn “không tự cấp cho bản thân” chưa đủ để bảo vệ hệ thống.

Với `role-operator-a`, cần ca dương cấp `READER` đúng phạm vi và ca âm cấp `TENANT_ADMIN`. Điều này giúp chứng minh hệ thống kiểm tra quyền được cấp, thay vì chỉ cho phép mọi thao tác nếu actor có một role mang tên quản lý.

### 4.2. Trường role trong các API không chuyên quản lý quyền

Kiểm tra API hồ sơ, cập nhật người dùng, import dữ liệu và các chức năng quản trị khác có nhận những trường như `roles`, `groups`, `permissions`, `isAdmin` hoặc `tenantRef` hay không. Đây là điểm cần đối chiếu schema được phép ghi, không phải mặc định rằng mọi trường có tên đó đều được hỗ trợ.

Ví dụ, gửi một trường ngoài contract khi sửa tên hiển thị có thể bị từ chối hoặc bị bỏ qua theo thiết kế. Cả hai cách đều có thể phù hợp nếu dữ liệu nhạy cảm và quyền hiệu lực không bị thay đổi ngoài dự kiến. Test phải kiểm tra trạng thái thật, không chỉ thông báo “cập nhật thành công”.

Ẩn nút, field ẩn hoặc kiểm tra role bằng JavaScript không phải nơi thực thi quyền đáng tin cậy. Backend phải kiểm tra request theo actor đã được xác thực. Một role do client tự đưa vào body hoặc header không tự trở thành thuộc tính được tin.

### 4.3. Sửa định nghĩa role hoặc binding

Một người có thể không được gán role quản trị mới nhưng lại được sửa role đang có để thêm quyền quản trị. Cũng có thể sửa một binding đang gắn với mình để trỏ sang role khác. Vì vậy, cần xem cả quyền thay đổi định nghĩa quyền lẫn quyền tạo assignment.

Kubernetes là một ví dụ cụ thể: API RBAC có các hạn chế đối với việc tạo hoặc sửa role và role binding, cùng những quyền đặc biệt như `escalate` và `bind`. Đây là cơ chế theo Kubernetes, không phải tên quyền chuẩn cho mọi hệ thống IAM; nó minh họa vì sao test phải phân biệt quyền sửa đối tượng role với quyền đưa thêm permission vào đối tượng đó. [Kubernetes — Privilege escalation prevention and bootstrapping](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping).

## 5. Kiểm thử leo thang gián tiếp và chuỗi quyền

### 5.1. Group và thuộc tính làm đầu vào policy

Một chuỗi khái niệm có thể là:

```text
Actor được sửa membership của group
    → thêm một tài khoản do actor kiểm soát
    → group được ánh xạ sang role đặc quyền
    → tài khoản đó đạt quyền ngoài phạm vi được ủy quyền
```

Test cần kiểm tra quyền quản lý membership của group đặc quyền, quyền thay owner hoặc manager của group và mapping từ group sang role. Một kiểm tra chỉ áp dụng tại API gán role trực tiếp có thể bỏ sót chuỗi này.

Với ABAC, thuộc tính như đơn vị, cấp phê duyệt hoặc cờ đủ điều kiện có thể tạo tác động tương tự. Nếu actor được tự sửa thuộc tính quyết định đặc quyền mà chính sách không cho phép, quyền hiệu lực có thể tăng dù không xuất hiện role mới.

### 5.2. Danh tính workload và ủy quyền

Một actor có thể đạt khả năng cao hơn thông qua quyền sử dụng một service principal, gắn danh tính vào tác vụ hoặc thay cấu hình của workload chạy với quyền khác. Cần kiểm thử những khả năng này theo mô hình nền tảng, không chỉ role hiển thị trên tài khoản người dùng.

Điều cần đánh giá là actor có được phép chọn danh tính đó, cho thao tác đó, trong phạm vi đó hay không. Một tác vụ được tạo thành công không tự chứng minh quyền được giới hạn đúng; cần xác minh danh tính và quyền mà tác vụ thật sự sử dụng trong môi trường test.

### 5.3. Quy trình phê duyệt và đặc quyền tạm thời

Nếu chính sách yêu cầu phê duyệt độc lập, cần kiểm tra người yêu cầu không tự trở thành người phê duyệt qua sửa field, đổi endpoint hoặc tạo yêu cầu dưới một tài khoản khác cùng phạm vi kiểm thử. Nếu có giới hạn thời gian, cần kiểm tra trạng thái trước kích hoạt, trong thời gian hợp lệ và sau khi hết hiệu lực.

Không áp giả định “không ai được tự phê duyệt” cho mọi ứng dụng. Kỳ vọng phải dựa vào chính sách cụ thể. Ca test cần chứng minh actor không bỏ qua một điều kiện mà quy trình thật sự yêu cầu.

Với yêu cầu MFA hoặc xác thực tăng cường khi kích hoạt đặc quyền, cần xác minh server kiểm tra trạng thái đã hoàn tất, không chỉ việc client gửi một cờ `mfaPassed`. Một phiên ít bảo đảm không được nâng quyền ngoài contract chỉ vì request có hình dạng giống request hợp lệ.

## 6. Ma trận kiểm thử theo actor, thao tác và phạm vi

| Ca | Biến thể cần kiểm tra | Kỳ vọng theo chính sách ví dụ |
|---|---|---|
| Tự cấp role | Thành viên tự gán `TENANT_ADMIN` | Không tạo assignment hoặc quyền hiệu lực mới |
| Cấp cho tài khoản khác | Thành viên gán role quản trị cho target khác | Bị giới hạn như quyền cấp role, không chỉ kiểm tra target có phải chính mình |
| Vượt loại role được cấp | Role operator cấp `TENANT_ADMIN` thay vì `READER` | Bị từ chối dù actor có quyền cấp một số role |
| Vượt tenant | Quản trị tenant A sửa assignment tenant B | Không vượt phạm vi ủy quyền |
| Sửa hồ sơ kèm role | Request cập nhật tên có thêm trường đặc quyền | Không thay đổi thuộc tính quyền ngoài contract |
| Sửa định nghĩa role | Thêm permission đặc quyền vào role actor đang có | Bị kiểm soát theo quyền quản lý định nghĩa |
| Sửa group | Actor thêm tài khoản của mình vào group được bảo vệ | Không tạo đường nhận đặc quyền trái chính sách |
| Sửa thuộc tính ABAC | Actor tự tăng cấp thuộc tính quyết định quyền | Nguồn và quyền ghi thuộc tính được kiểm soát |
| Bỏ phê duyệt | Kích hoạt role khi yêu cầu còn pending | Không có quyền hiệu lực trước khi đủ điều kiện |
| Dùng đặc quyền đã hết hạn | Gọi hành động sau deadline theo contract | Không tiếp tục được phép ngoài giới hạn đã công bố |
| Đường API thay thế | Dùng bulk, import hoặc phiên bản API khác | Cùng quy tắc quyền được áp dụng tại nơi xử lý |
| Ủy quyền workload | Actor chọn danh tính thực thi ngoài phạm vi | Không dùng được quyền của danh tính đó trái chính sách |
| Ca dương đối chứng | Role operator cấp `READER` cho target hợp lệ tại tenant A | Chỉ tạo đúng assignment và tác động được phép |

OWASP Authorization Cheat Sheet nhấn mạnh từ chối theo mặc định và kiểm tra quyền trên từng request. Với kiểm thử leo thang role, điều đó có nghĩa là cần bao phủ các đường thực thi chức năng, không chỉ giao diện quản trị chính. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## 7. Xác minh trạng thái sau request, không chỉ mã HTTP

### 7.1. Ba lớp quan sát

Một ca âm nên quan sát đồng thời:

1. Response của thao tác thay đổi quyền có phù hợp contract từ chối hoặc xử lý trường ngoài phạm vi không?
2. Assignment, group, policy, định nghĩa role và công việc bất đồng bộ liên quan có thay đổi ngoài dự kiến không?
3. Actor hoặc target có đạt thêm khả năng thực hiện hành động được bảo vệ không?

Một response `403` không đủ nếu dữ liệu đã được ghi trước khi trả lỗi. Một response `202` cũng không đủ để kết luận quyền đã được cấp: có thể công việc còn chờ xử lý. Với hệ thống bất đồng bộ, cần theo dõi trạng thái công việc và kết quả đích trong khoảng thời gian được thiết kế.

Khi một request không được phép bị từ chối, audit event hoặc bộ đếm có thể thay đổi hợp lệ. Vì vậy, không yêu cầu “toàn bộ database không đổi”; chỉ so sánh đúng những thay đổi quyền và tác động nghiệp vụ không được phép, trong khi vẫn kiểm tra dấu vết theo contract.

### 7.2. Một đặc tả ca minh họa

```yaml
testId: ROLE-ESCALATION-SELF-GRANT-001
purpose: Thành viên không tự cấp quyền quản trị tenant
given:
  actor: member-a
  actorTenant: tenant-a
  target: member-a
  requestedRole: TENANT_ADMIN
  requestedScope: tenant-a
  authentication: VALID
  otherRequestRequirements: SATISFIED
when:
  action: Gọi API tạo role assignment
then:
  roleAssignmentCreated: false
  protectedGroupChanged: false
  policyOrRoleDefinitionChanged: false
  privilegeGrantJobScheduled: false
  administrativeActionAllowedAfterwards: false
  audit:
    recordsActorTargetRoleAndScope: true
    containsRawCredential: false
```

Đây là đặc tả giả định, không phải schema của một framework. Các assertion cần được triển khai bằng những nguồn quan sát mà hệ thống test có thể tin cậy. Với hệ thống dùng một cơ chế không có queue cấp quyền, phần kiểm tra job có thể được đánh dấu không áp dụng thay vì tạo một kết quả pass giả.

### 7.3. Phiên và cache sau thay đổi quyền

Sau khi role được cấp hợp lệ hoặc bị thu hồi, token và cache có thể chưa phản ánh trạng thái mới ngay. Bộ kiểm thử cần nêu rõ quyền được quyết định từ đâu và thời gian cập nhật được chấp nhận theo contract.

Đối với thu hồi, kiểm tra cả phiên hoặc token đã có và credential được phát hành mới khi phù hợp. Không mặc định mọi hệ thống thu hồi JWT tự chứa ngay lập tức, nhưng cũng không cho phép kéo dài quyền vô hạn nếu chính sách yêu cầu giới hạn rõ.

Với ca bị từ chối cấp role, không nên chỉ chờ token mới rồi đọc claim role. Cần kiểm tra dữ liệu nguồn và hành động bảo vệ, vì quyền có thể đến từ một đường khác không xuất hiện trong claim đang xem.

## 8. Tổ chức kiểm thử để tránh kết luận sai

### 8.1. Dùng request hợp lệ ở các điều kiện không phải mục tiêu

Muốn kiểm tra phân quyền cấp role, request cần có xác thực hợp lệ và thỏa những yêu cầu khác của endpoint, như định dạng, dữ liệu target hoặc cơ chế chống CSRF tương ứng. Nếu request bị chặn vì token hết hạn hoặc thiếu CSRF token, kết quả chưa chứng minh kiểm tra role đã được chạy.

Tương tự, sửa claim `role` trong JWT mà không có chữ ký hợp lệ chủ yếu kiểm tra xác minh token. Cần thêm ca dùng một credential hợp lệ của actor ít quyền để đánh giá việc phân quyền tại chức năng quản lý role.

### 8.2. Kết hợp policy test với integration test

Unit test có thể kiểm tra bảng quyết định như `can_assign` theo nhiều tổ hợp actor, target, role và scope. Tuy nhiên, một policy đúng chưa chứng minh mọi endpoint đều gọi policy đó hoặc truyền đúng tenant vào quyết định.

Integration test cần đi qua security chain và đường ghi dữ liệu thật của môi trường test. End-to-end test bổ sung các luồng giao diện, approval, connector hoặc tác vụ bất đồng bộ. Một test chỉ đặt sẵn principal có role quản trị trong security context sẽ không phát hiện việc cấp role cho actor ít quyền bị bỏ kiểm tra ở API khác.

### 8.3. Kiểm tra các chuỗi và điều kiện đồng thời có ý nghĩa

Một số lỗi chỉ xuất hiện khi kết hợp hai quyền: sửa group rồi kích hoạt role, tạo target rồi cấp quyền, hoặc thay policy rồi dùng role hiện có. Nên chọn các chuỗi gắn với mô hình quyền thực tế thay vì chỉ kiểm tra từng endpoint tách rời.

Với quy trình phê duyệt hoặc cập nhật đồng thời, có thể cần ca kiểm tra điều kiện thay đổi giữa lúc kiểm tra và lúc ghi. Hệ thống phải giữ các điều kiện bảo vệ tại thời điểm thực hiện thay đổi theo thiết kế, không chỉ dựa vào màn hình xác nhận trước đó.

Các ca tạo đặc quyền thử nghiệm cần fixture và cleanup được kiểm soát. Không để một ca dương cấp role trở thành trạng thái đầu vào ngầm của ca âm tiếp theo. Những thao tác có khả năng ảnh hưởng rộng nên sử dụng phạm vi test riêng để kết quả có thể tái lập.

## 9. Báo cáo và chuyển thành kiểm thử hồi quy

Báo cáo cần nêu quyền ban đầu, chính sách được kỳ vọng, chuỗi request trong phạm vi kiểm thử, trạng thái trước và sau, cùng khả năng thực thi quyền đã quan sát. Không chỉ ghi “user thành admin” nếu chưa xác định role, scope và hành động chứng minh.

Nếu phát hiện quyền tăng ngoài dự kiến, cần xác định đường thay đổi: assignment trực tiếp, membership, role definition, policy, mapping hay ủy quyền sang danh tính khác. Điều này giúp sửa đúng nơi thực thi và thêm regression test bao phủ cơ chế đã bị bỏ sót.

Bằng chứng cần đủ để tái lập nhưng không chứa raw token, mật khẩu hoặc dữ liệu cá nhân không cần thiết. Phân biệt test pass, fail, chưa chạy và không áp dụng. Một ma trận có nhiều ô nhưng phần lớn không chạy chưa chứng minh hệ thống chống leo thang tốt.

Sau thay đổi cấu hình role, mapping group, delegated administration hoặc thư viện phân quyền, nên chạy lại những ca liên quan. Cần giữ cả ca dương và ca âm để bảo đảm biện pháp sửa không đơn giản là chặn toàn bộ chức năng cấp quyền hợp lệ.

## 10. Tự kiểm tra cách hiểu

**Không có nút cấp role trên giao diện có đủ để ngăn thành viên tự nâng quyền không?**

Không. Backend phải kiểm tra request trực tiếp và các đường khác có thể ghi thuộc tính, membership hoặc policy liên quan tới quyền.

**Một quản trị viên tenant A có mặc nhiên được cấp cùng role ở tenant B không?**

Không. Tên role không loại bỏ ranh giới phạm vi. Test phải xét tenant, tài nguyên và quyền được ủy quyền cho actor.

**API trả `403` có đủ để kết luận không có leo thang không?**

Chưa. Cần xác minh không có thay đổi quyền hoặc công việc cấp quyền trái phép đã được tạo, đồng thời kiểm tra khả năng thực hiện hành động sau request.

**Role trực tiếp không đổi có chứng minh quyền hiệu lực không tăng không?**

Không. Group, policy, định nghĩa role, thuộc tính ABAC hoặc danh tính workload được sử dụng có thể tạo quyền bổ sung.

**Một role escalation test tốt cần chứng minh điều gì?**

Chủ thể chỉ được làm thay đổi quyền khi đủ điều kiện, đúng target, role, phạm vi và quy trình. Các request hoặc chuỗi thao tác ngoài quyền không tạo thêm khả năng trái chính sách, còn việc cấp quyền hợp lệ vẫn hoạt động và có dấu vết kiểm toán.
