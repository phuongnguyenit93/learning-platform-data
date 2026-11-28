# Thiết kế RBAC cho admin

Một trang quản trị thường tập trung những thao tác có ảnh hưởng lớn: tạo tài khoản, mở khóa người dùng, cấp quyền, xuất dữ liệu và thay đổi cấu hình. Nếu mọi người vận hành đều nhận một role `ADMIN`, chỉ một tài khoản bị chiếm đoạt cũng có thể mở đường đến toàn bộ hệ thống.

Bài thực hành này xây dựng một thiết kế Role-Based Access Control (RBAC) cho cổng quản trị của một dịch vụ SaaS. Mục tiêu là biến công việc thực tế thành các quyền có thể giải thích, kiểm tra và thu hồi, đồng thời ngăn quản trị viên tự nâng quyền hoặc truy cập nhầm tổ chức. Bản thiết kế bao gồm vòng đời cấp quyền, các điểm kiểm soát ở backend và bằng chứng phục vụ kiểm toán; đây không chỉ là danh sách role trên giao diện.

## 1. Bối cảnh và đầu ra của bài thực hành

Giả sử dịch vụ có nhiều tổ chức khách hàng, gọi là tenant. Mỗi tenant có người dùng cuối và một nhóm quản trị riêng. Nhân viên hỗ trợ của nhà cung cấp đôi khi cần hỗ trợ một tenant được chỉ định. Nhân sự an ninh và kiểm toán có trách nhiệm độc lập với nhóm vận hành thường ngày.

Các yêu cầu nghiệp vụ ban đầu là:

- Hỗ trợ được tra cứu tài khoản và kết thúc phiên khi xử lý sự cố, nhưng không được cấp role quản trị hoặc xuất dữ liệu hàng loạt.
- Người quản lý tài khoản được tạo, khóa và mở khóa người dùng trong tenant của mình. Họ không được đổi role quản trị của chính mình.
- Người quản lý quyền được đề nghị cấp hoặc thu hồi role theo danh mục được phép. Họ không được tự phê duyệt đề nghị của mình.
- Kiểm toán viên được đọc lịch sử thay đổi quyền, nhưng không được sửa tài khoản hoặc xóa log.
- Quyền nhạy cảm có thời hạn, có người phê duyệt độc lập và phải thu hồi được khi không còn cần thiết.
- Quyền quản trị nền tảng không phát sinh chỉ vì một người có quyền quản trị trong tenant.

Sau bài này, người học cần tạo được năm đầu ra: danh mục permission, ma trận role–permission, mô hình assignment có scope, luồng quyết định truy cập và bộ kiểm thử gồm cả trường hợp bị từ chối. Những đầu ra này phải mô tả cùng một chính sách, tránh tình trạng tài liệu nói một kiểu còn API thực thi một kiểu khác.

## 2. Tách xác thực khỏi phân quyền

Xác thực trả lời người gửi yêu cầu là ai và phiên đăng nhập có hợp lệ hay không. Phân quyền trả lời người đó có được thực hiện hành động cụ thể trên tài nguyên cụ thể, tại thời điểm hiện tại hay không.

Đăng nhập thành công, hoàn tất MFA hoặc có token hợp lệ chưa đủ để được cấp quyền quản trị. MFA tăng mức tin cậy vào phiên xác thực; nó không tự tạo ra permission. Ngược lại, một assignment còn hiệu lực cũng không có giá trị nếu tài khoản đã bị khóa hoặc phiên đã bị thu hồi.

Trong thiết kế này, một quyết định cho phép cần đồng thời thỏa mãn các nhóm điều kiện:

```text
ALLOW = phiên hợp lệ
        AND tài khoản được hoạt động
        AND assignment còn hiệu lực
        AND role chứa permission cần thiết
        AND scope bao phủ tài nguyên
        AND điều kiện bổ sung của thao tác được thỏa mãn
```

Các điều kiện bổ sung có thể là xác thực lại gần đây, phê duyệt độc lập hoặc không được thao tác lên chính mình. Phần ánh xạ người dùng → role → permission là RBAC; kiểm tra tenant, thời gian và quan hệ giữa người thực hiện với người bị tác động là các ràng buộc đi kèm. Nêu rõ sự kết hợp này giúp tránh kỳ vọng rằng tên role có thể mô tả toàn bộ chính sách.

Mặc định phải từ chối. Nếu một API chưa khai báo permission, không tìm được tài nguyên hoặc không đánh giá được chính sách thì không được mặc nhiên cho phép thao tác quản trị.

## 3. Xây permission từ hành động nghiệp vụ

Permission nên biểu diễn một khả năng cụ thể, ổn định và kiểm chứng được. Không nên dùng `admin.access` cho mọi thao tác hoặc gắn chính sách vào tên nút trên giao diện.

Một danh mục ban đầu có thể gồm:

| Permission | Ý nghĩa | Giới hạn cần ghi rõ |
|---|---|---|
| `user.read` | Xem hồ sơ tài khoản phục vụ vận hành | Chỉ các trường được phép; dữ liệu nhạy cảm được che |
| `user.create` | Tạo người dùng cuối | Không kèm quyền cấp role quản trị |
| `user.update_profile` | Sửa trường hồ sơ được cho phép | Không sửa trạng thái đặc quyền hay trường bảo mật nội bộ |
| `user.suspend` | Khóa người dùng cuối | Chỉ trong tenant; xử lý admin theo quy trình riêng |
| `user.reactivate` | Mở lại người dùng cuối | Không tự khôi phục assignment quản trị đã thu hồi |
| `session.revoke` | Kết thúc phiên của người dùng đích | Có ràng buộc đối tượng và scope |
| `access.request` | Tạo đề nghị thay đổi role quản trị | Bị giới hạn bởi danh mục role được đề nghị |
| `access.approve` | Phê duyệt đề nghị hợp lệ | Không phê duyệt đề nghị do mình tạo hoặc có lợi cho mình |
| `access.revoke` | Thu hồi assignment trong phạm vi được giao | Không được dùng để chiếm quyền kiểm soát quản trị |
| `audit.read` | Đọc lịch sử quản trị | Không bao gồm sửa hoặc xóa bản ghi |
| `report.export` | Xuất một tập dữ liệu đã định nghĩa | Quyền đọc không tự bao hàm quyền xuất |

Không nên tạo permission cho từng tài khoản, chẳng hạn `user.123.read`. Permission mô tả loại hành động; ID tài nguyên và tenant là đầu vào của kiểm tra scope.

Các endpoint cập nhật tổng quát cần được phân tích kỹ. Nếu `PATCH /users/{id}` nhận cả `displayName`, `status` và `adminRole`, việc kiểm tra duy nhất `user.update_profile` có thể biến chỉnh hồ sơ thành đường nâng quyền. Có thể tách endpoint theo hành động hoặc áp dụng danh sách trường được phép và kiểm tra quyền riêng cho từng nhóm trường. Backend phải từ chối trường không được cấp quyền, kể cả khi giao diện không hiển thị trường đó.

## 4. Định nghĩa role theo trách nhiệm

Role là tập permission phục vụ một trách nhiệm công việc. Trước khi tạo role mới, cần trả lời: ai cần nó, để làm công việc gì, trên phạm vi nào và khi nào phải thu hồi?

Đối với bài thực hành, chọn các role sau:

| Role | Trách nhiệm | Cách sử dụng |
|---|---|---|
| `SUPPORT_AGENT` | Tra cứu và hỗ trợ phiên đăng nhập | Assignment theo tenant được hỗ trợ |
| `USER_OPERATOR` | Quản lý vòng đời người dùng cuối | Assignment trong một tenant |
| `ACCESS_MANAGER` | Đề nghị cấp quyền và thu hồi theo chính sách | Không được tự phê duyệt |
| `ACCESS_APPROVER` | Phê duyệt thay đổi quyền | Độc lập với người yêu cầu và người nhận quyền |
| `AUDITOR` | Đọc bằng chứng kiểm toán | Không thay đổi cấu hình hoặc người dùng |
| `REPORT_EXPORTER` | Xuất báo cáo đã được phê duyệt | Cấp tạm thời khi có nhu cầu cụ thể |

Tránh đặt tên `SUPER_ADMIN` rồi dùng nó như lối đi tắt thường ngày. Quyền khẩn cấp được xử lý ở một quy trình riêng có phạm vi và thời hạn cụ thể, thay vì đưa vào role mặc định cho trưởng nhóm.

Ma trận quyền cho phiên bản đầu tiên:

| Permission | Support | User operator | Access manager | Approver | Auditor | Exporter |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `user.read` | ✓ | ✓ | — | — | — | — |
| `user.create` | — | ✓ | — | — | — | — |
| `user.update_profile` | — | ✓ | — | — | — | — |
| `user.suspend` | — | ✓ | — | — | — | — |
| `user.reactivate` | — | ✓ | — | — | — | — |
| `session.revoke` | ✓ | ✓ | — | — | — | — |
| `access.request` | — | — | ✓ | — | — | — |
| `access.approve` | — | — | — | ✓ | — | — |
| `access.revoke` | — | — | ✓ | — | — | — |
| `audit.read` | — | — | ✓ | ✓ | ✓ | — |
| `report.export` | — | — | — | — | — | ✓ |

Dấu ✓ chỉ xác nhận role có permission. Nó chưa xác nhận người giữ role được tác động đến mọi đối tượng. Ví dụ, `USER_OPERATOR` có `user.suspend` nhưng chính sách của bài này chỉ cho khóa người dùng cuối, không cho khóa quản trị viên đang kiểm soát tenant.

`ACCESS_APPROVER` cần đọc nội dung đề nghị được giao để ra quyết định. Khả năng này thuộc quy trình phê duyệt, với dữ liệu hiển thị tối thiểu; không đồng nghĩa được tra cứu tự do mọi hồ sơ người dùng. Tương tự, `REPORT_EXPORTER` chỉ xuất đúng loại báo cáo được cấp, không mặc nhiên được đọc mọi dữ liệu qua API khác.

Trong phiên bản đầu, danh mục role và permission do nhóm quản trị chính sách trung tâm duy trì, không cho tenant tự sửa định nghĩa role. Nếu sau này hỗ trợ role tùy chỉnh, phải thiết kế quyền sửa role, giới hạn permission được đưa vào role và phân tích tác động lên tất cả assignment hiện có. Chỉ kiểm tra quyền lúc gán role là chưa đủ nếu định nghĩa role có thể bị sửa sau đó.

## 5. Gắn role với scope và thời hạn

Một assignment cần nhiều hơn cặp `userId`–`roleId`. Mô hình tối thiểu nên biểu diễn:

```text
RoleAssignment
  assignmentId
  subjectId
  roleId
  scopeType
  scopeId
  validFrom
  expiresAt
  revokedAt
  grantedBy
  requestId
  policyVersion
```

Ví dụ một nhân viên hỗ trợ được làm việc trong tenant A:

```json
{
  "assignmentId": "ra-1042",
  "subjectId": "staff-17",
  "roleId": "SUPPORT_AGENT",
  "scopeType": "TENANT",
  "scopeId": "tenant-a",
  "validFrom": "2027-01-10T08:00:00Z",
  "expiresAt": "2027-01-10T12:00:00Z",
  "revokedAt": null,
  "grantedBy": "access-workflow",
  "requestId": "ar-208",
  "policyVersion": "rbac-v1"
}
```

Các giá trị thời gian trong ví dụ chỉ minh họa dữ liệu. Khi triển khai, hệ thống cần thống nhất cách lưu và so sánh thời gian, thường là thời điểm UTC do server kiểm soát. Assignment có hiệu lực khi `validFrom <= now < expiresAt` và chưa bị thu hồi; không chờ một tác vụ dọn dẹp chạy mới coi assignment hết hạn.

Người dùng thuộc tenant A và tenant B có thể nhận role khác nhau ở mỗi nơi. Không được gộp tất cả role thành một tập toàn cục rồi bỏ mất scope. Cũng không được suy rằng `TENANT_ADMIN` bao hàm quản trị nền tảng.

Nếu cần phạm vi nền tảng, phải có loại scope, permission và quy trình cấp riêng. Không diễn giải `scopeId = null` thành “mọi tenant”; dữ liệu thiếu phải bị từ chối. Với assignment theo tenant, hệ thống phải xác nhận tenant còn hoạt động và người nhận còn đủ điều kiện giữ assignment đó.

## 6. Kiểm tra scope từ tài nguyên thực tế

Yêu cầu có đường dẫn chứa `tenant-a` không chứng minh tài nguyên bên trong thuộc tenant A. Kẻ tấn công có thể thay `userId` bằng ID của một người thuộc tenant B hoặc gửi `tenantId` giả trong body.

Một chuỗi xử lý phù hợp là:

1. Xác thực phiên và xác định `subjectId` từ ngữ cảnh đáng tin cậy.
2. Tải hoặc truy vấn tài nguyên với điều kiện tenant tương ứng từ kho dữ liệu.
3. Xác định permission cần thiết từ hành động của API.
4. Tìm assignment còn hiệu lực của chủ thể trong đúng scope.
5. Kiểm tra các ràng buộc đối tượng, phê duyệt và phiên xác thực.
6. Thực hiện thay đổi và ghi bằng chứng quyết định.

Ví dụ truy vấn có điều kiện tenant:

```sql
SELECT id, tenant_id, account_type, status
FROM users
WHERE id = :target_user_id
  AND tenant_id = :authorized_tenant_id;
```

`:authorized_tenant_id` phải được xác định sau khi kiểm tra ngữ cảnh tenant và assignment. Một giá trị lấy trực tiếp từ body mà chưa xác minh không trở nên đáng tin cậy chỉ vì đã được đưa vào truy vấn có tham số.

Kiểm tra tương tự phải áp dụng cho danh sách, tìm kiếm, đếm bản ghi, file xuất, tác vụ nền và các tài nguyên con. Bảo vệ endpoint sửa một người dùng nhưng để endpoint danh sách trả toàn bộ tenant vẫn là lỗi phân quyền.

## 7. Phân tách nhiệm vụ và ngăn tự nâng quyền

RBAC thường cộng hợp permission từ nhiều role. Điều đó thuận tiện nhưng có thể vô hiệu hóa ý định phân tách nhiệm vụ. Nếu cùng một người vừa tạo yêu cầu vừa phê duyệt, hai tên role khác nhau không tạo ra kiểm soát độc lập.

Trong bài thực hành, áp dụng hai lớp ràng buộc:

- Phân tách tĩnh: không gán đồng thời `ACCESS_MANAGER` và `ACCESS_APPROVER` cho cùng một chủ thể trong cùng tenant.
- Phân tách động: người phê duyệt của một yêu cầu phải khác người tạo yêu cầu và khác người nhận quyền, kể cả khi họ đang có một assignment hợp lệ khác.

Ràng buộc động vẫn cần thiết vì role có thể đổi sau khi yêu cầu được tạo. Không chỉ so sánh role tại thời điểm tạo yêu cầu; phải kiểm tra danh tính và quyền hiện tại khi phê duyệt cũng như khi thực thi.

`access.request` không cho phép đề nghị bất kỳ role nào. Cần thêm chính sách ủy quyền rõ ràng:

```text
ACCESS_MANAGER tại tenant T:
  được đề nghị SUPPORT_AGENT và USER_OPERATOR tại T
  được đề nghị REPORT_EXPORTER tại T với thời hạn giới hạn
  không được cấp role quản trị nền tảng
  không được cấp ACCESS_MANAGER hoặc ACCESS_APPROVER theo luồng thông thường
  không được thay đổi assignment của chính mình
```

Các role điều khiển quyền truy cập phải có quy trình quản trị riêng, do chủ sở hữu chính sách và người phê duyệt đủ thẩm quyền xử lý. Nếu một access manager có thể cấp access manager cho tài khoản thứ hai do mình kiểm soát, quy tắc “không tự cấp cho mình” đơn thuần vẫn chưa ngăn được nâng quyền.

Thu hồi quyền cũng là hành động nhạy cảm. Không để một access manager thông thường thu hồi toàn bộ approver hoặc quản trị viên cuối cùng rồi độc chiếm tenant. Có thể cho phép thu hồi các role được ủy quyền thấp hơn, còn thay đổi role kiểm soát truy cập phải qua quy trình độc lập. Với quản trị viên cuối cùng, cần kiểm tra ràng buộc trong cùng giao dịch để hai yêu cầu song song không cùng vượt qua kiểm tra rồi làm tenant mất người quản trị.

## 8. Thiết kế vòng đời cấp quyền

Luồng cấp quyền nhạy cảm nên có trạng thái rõ ràng:

```text
REQUESTED → APPROVED → APPLIED
     │           │
     ├→ REJECTED ├→ EXPIRED
     └→ CANCELED └→ CANCELED
```

Assignment sau khi được tạo có vòng đời riêng: có thể đang hoạt động, đã hết hạn hoặc đã thu hồi. Hết hạn của yêu cầu phê duyệt và hết hạn của assignment là hai mốc khác nhau.

Một yêu cầu cần lưu người nhận, role, scope, thời hạn, lý do và phiên bản nội dung. Phê duyệt phải gắn với đúng phiên bản đó. Nếu người yêu cầu đổi role từ `SUPPORT_AGENT` sang `REPORT_EXPORTER` sau khi đã được duyệt, phê duyệt cũ không còn hợp lệ.

Khi chuyển sang `APPLIED`, dịch vụ cấp quyền phải kiểm tra lại:

1. Yêu cầu còn hợp lệ, chưa bị hủy và chưa được áp dụng trước đó.
2. Người yêu cầu và người phê duyệt vẫn có thẩm quyền cần thiết.
3. Người nhận vẫn hoạt động và đủ điều kiện trong tenant.
4. Role, scope và thời hạn nằm trong giới hạn ủy quyền hiện hành.
5. Không vi phạm phân tách nhiệm vụ hoặc điều kiện tự tác động.
6. Phiên bản yêu cầu khớp với phiên bản đã phê duyệt.

Việc tạo assignment và chuyển trạng thái yêu cầu cần được bảo vệ bằng giao dịch hoặc cơ chế tương đương. Khóa duy nhất theo `requestId` giúp retry không cấp trùng. Khi kiểm tra xung đột role, cần xử lý đồng thời để hai yêu cầu cấp hai role xung đột không cùng được áp dụng dựa trên trạng thái cũ.

Dịch vụ thực thi tự động dùng danh tính workload riêng với quyền giới hạn. Việc chạy nền không cho phép bỏ qua chính sách; workload chỉ hiện thực quyết định đã được kiểm tra và phải giữ liên kết đến chủ thể, đề nghị và phê duyệt ban đầu.

## 9. Đặt kiểm soát ở backend

Ẩn nút hoặc menu giúp giao diện dễ sử dụng, nhưng không tạo ra ranh giới bảo mật. Người dùng có thể gọi API trực tiếp, sửa request hoặc dùng ứng dụng khách khác.

Nên phân biệt hai vai trò kỹ thuật:

- Điểm thực thi chính sách nhận yêu cầu, gọi kiểm tra quyền và chặn thao tác nếu không được phép.
- Thành phần quyết định chính sách đánh giá phiên, assignment, role, scope và các ràng buộc liên quan.

Ví dụ sau là mã giả Java để diễn tả luồng, không phải một triển khai framework hoàn chỉnh:

```java
void suspendEndUser(AuthContext auth, TenantId tenantId, UserId userId) {
    transaction.run(() -> {
        authService.requireActiveSession(auth);

        User target = users.findForUpdate(tenantId, userId)
            .orElseThrow(ResourceUnavailable::new);

        Decision decision = authorization.evaluate(
            auth,
            "user.suspend",
            target,
            clock.instant()
        );

        decision.requireAllowed();
        accountPolicy.requireEndUser(target);
        accountPolicy.requireDifferentSubject(auth.subjectId(), target.id());

        target.suspend();
        users.save(target);
        auditOutbox.appendSuspension(auth, target, decision);
    });
}
```

Các kiểm tra bị từ chối cần tạo sự kiện bảo mật ở luồng phù hợp. Trong ví dụ, outbox cho thay đổi thành công được ghi cùng giao dịch; khi giao dịch rollback do từ chối, không thể trông chờ bản ghi trong cùng giao dịch đó vẫn tồn tại. Cần kênh ghi sự kiện từ chối riêng và chính sách xử lý lỗi ghi log rõ ràng.

Một annotation kiểm tra permission ở controller có thể giúp giảm lặp, nhưng chưa đủ nếu service còn được gọi từ lịch chạy, message consumer hoặc API nội bộ. Đặt kiểm soát ở ranh giới nghiệp vụ nơi biết tài nguyên thật, đồng thời dùng kiểm tra ở biên API khi cần. Không truyền `isAdmin=true` từ client xuống service như một kết quả phân quyền đã đáng tin cậy.

## 10. Quản lý thay đổi quyền và cache

Nạp role vào token rồi tin token cho đến lúc hết hạn tạo ra khoảng trễ thu hồi. Một quản trị viên đã bị thu hồi assignment có thể vẫn dùng token cũ nếu API không kiểm tra trạng thái quyền hiện tại.

Thiết kế cần xác định rõ yêu cầu độ trễ thu hồi cho từng loại thao tác. Ví dụ, thay đổi assignment có thể tăng `authorizationVersion` của chủ thể; API đối chiếu phiên bản token hoặc cache với phiên bản được quản lý ở server. Khi không khớp, hệ thống tải lại quyền hoặc yêu cầu thiết lập lại phiên theo chính sách.

Đối với thao tác quản trị nhạy cảm, có thể yêu cầu kiểm tra quyền từ nguồn hiện hành ngay trước lúc thực thi. Nếu dùng cache, khóa cache cần bao gồm chủ thể, tenant, phiên bản chính sách và các dữ liệu ảnh hưởng đến quyết định; thời gian sống không được vượt quá thời điểm hết hạn assignment sớm nhất liên quan.

Thông báo vô hiệu hóa cache giúp giảm độ trễ nhưng bản thân thông báo có thể thất lạc. Cần có cơ chế phiên bản, giới hạn thời gian sống hoặc cách đối chiếu nguồn có thẩm quyền để đạt cam kết thu hồi đã công bố. Không hứa “thu hồi tức thì” nếu kiến trúc chỉ xóa cache theo một sự kiện không được xác nhận.

Tác vụ xuất báo cáo kéo dài cần kiểm tra quyền khi tạo job, khi bắt đầu xử lý và khi tải kết quả. Nếu quyền bị thu hồi giữa chừng, hệ thống cần có chính sách dừng hoặc chặn bàn giao kết quả; không coi lần kiểm tra lúc đưa vào hàng đợi là đủ cho mọi bước sau đó.

## 11. Xử lý nhiều role và kế thừa

Với mô hình cho phép cộng hợp, người dùng có `SUPPORT_AGENT` và `AUDITOR` nhận tổng các permission của hai role trong đúng scope. Các ràng buộc phân tách nhiệm vụ và phạm vi vẫn phải được kiểm tra sau khi xác định quyền ứng viên.

Không nên đưa “deny” vào role một cách tùy tiện. Nếu một role cho phép và role khác từ chối cùng hành động, hệ thống cần định nghĩa thứ tự ưu tiên rõ ràng. Với phiên bản đầu của bài thực hành, chọn mô hình đơn giản: role chỉ cấp permission; các ràng buộc bắt buộc có thể từ chối bất kể role nào đã cấp permission. Không có permission phù hợp cũng là từ chối.

Role kế thừa có thể giảm trùng lặp nhưng làm việc giải thích quyền khó hơn. Nếu sử dụng, đồ thị kế thừa phải không có chu trình, không trộn tenant với nền tảng và phải hiển thị permission hiệu lực. Bài thực hành này chọn role phẳng để dễ kiểm tra; không cần thêm kế thừa chỉ vì tên role có vẻ có thứ bậc.

Mỗi lần thay đổi role cần xác định tập assignment bị ảnh hưởng. Thêm `report.export` vào một role hiện có là cấp thêm quyền cho mọi người đang giữ role đó, không chỉ là chỉnh một bản ghi cấu hình. Vì vậy thay đổi định nghĩa role cần được xem xét, phê duyệt và kiểm toán như thay đổi quyền thực tế.

## 12. Quyền khẩn cấp

Có thể xuất hiện tình huống không còn người phê duyệt thông thường hoặc cần khôi phục quyền truy cập trong sự cố. Quy trình khẩn cấp phải được thiết kế trước, với chủ thể định danh được, xác thực mạnh, thời hạn ngắn, phạm vi rõ và cảnh báo ngay khi kích hoạt.

Không dùng tài khoản chung mà nhiều người biết mật khẩu nếu có thể tránh. Bằng chứng cần chỉ ra ai kích hoạt, lý do gì, được phép làm những hành động nào và khi nào quyền tự hết hạn. Việc hậu kiểm phải có người chịu trách nhiệm và không được chính người sử dụng quyền tự xác nhận hoàn thành.

Quyền khẩn cấp cũng không nên mặc định vô hiệu hóa mọi kiểm soát tenant, log và bảo vệ dữ liệu. Nếu một điều kiện thông thường được miễn trong tình huống khẩn cấp, ngoại lệ đó phải được mô tả chính xác và vẫn để lại dấu vết. Không triển khai một biến `bypassAuthorization` có thể xuất hiện từ request của client.

## 13. Ghi log để giải thích được quyết định

Một bản ghi “admin sửa user” là quá ít. Đối với thay đổi đặc quyền hoặc thao tác nhạy cảm, bằng chứng nên đủ để trả lời ai, làm gì, lên tài nguyên nào, trong tenant nào, dựa trên quyền nào và kết quả ra sao.

Ví dụ sự kiện phân quyền thành công:

```json
{
  "eventType": "ADMIN_ACTION_AUTHORIZED",
  "actorId": "staff-17",
  "tenantId": "tenant-a",
  "action": "session.revoke",
  "resourceType": "USER",
  "resourceId": "user-315",
  "assignmentIds": ["ra-1042"],
  "policyVersion": "rbac-v1",
  "decision": "ALLOW",
  "reasonCode": "ACTIVE_SCOPED_PERMISSION",
  "correlationId": "req-712"
}
```

Với quyết định từ chối, nên dùng mã lý do như `SCOPE_MISMATCH`, `ASSIGNMENT_EXPIRED`, `SELF_APPROVAL_FORBIDDEN` hoặc `MISSING_PERMISSION`. Phản hồi công khai có thể giữ thông tin tối thiểu để tránh lộ sự tồn tại của tài nguyên; log nội bộ lưu chi tiết theo quyền truy cập phù hợp.

Không ghi mật khẩu, secret, token hoặc toàn bộ hồ sơ nhạy cảm vào log. Người có `audit.read` chỉ được xem phạm vi được giao và không được sửa bằng chứng. Các thay đổi role và assignment nên có dữ liệu trước–sau hoặc chênh lệch có kiểm soát, liên kết đến đề nghị và phê duyệt. Việc ghi nhận thành công phải nhất quán với thay đổi dữ liệu; outbox là một cách tổ chức luồng gửi sự kiện, không tự bảo đảm kho log cuối cùng chống sửa đổi.

## 14. Bộ kiểm thử theo chính sách

Đừng chỉ kiểm tra rằng admin có thể thao tác. Phần quan trọng là chứng minh người không phù hợp bị từ chối và dữ liệu không bị thay đổi.

| Ca kiểm thử | Thiết lập và hành động | Kết quả cần quan sát |
|---|---|---|
| Đúng quyền, đúng tenant | Support có assignment còn hạn tại A thu hồi phiên người dùng cuối A | Cho phép; phiên đích bị thu hồi; có sự kiện tương ứng |
| Vượt tenant | Cùng support gửi ID người dùng B trong request của A | Từ chối hoặc phản hồi không tìm thấy theo chính sách; không có tác động ở B |
| Thiếu permission | Support gọi API cấp role | Từ chối; không tạo assignment |
| Giả mạo tenant | Client sửa `tenantId` trong body | Không thay đổi scope đã xác minh; không tác động tenant khác |
| Tự phê duyệt | Người tạo yêu cầu cũng gửi lệnh approve | Từ chối dù phiên xác thực hợp lệ |
| Phê duyệt cho mình | Approver là người nhận assignment | Từ chối theo phân tách động |
| Role xung đột | Hai yêu cầu đồng thời cấp manager và approver cho cùng người ở A | Không để cả hai assignment xung đột cùng có hiệu lực |
| Hết hạn | Thao tác đúng tại `expiresAt` | Từ chối; không phụ thuộc lịch dọn dữ liệu |
| Thu hồi và token cũ | Thu hồi assignment rồi dùng lại token hoặc cache cũ | Chặn trong giới hạn độ trễ thu hồi đã cam kết |
| Sửa yêu cầu đã duyệt | Đổi role hoặc scope trước lúc áp dụng | Phê duyệt cũ không được sử dụng |
| Retry áp dụng | Gửi lặp lệnh áp dụng cùng `requestId` | Không tạo assignment trùng |
| Chèn trường nhạy cảm | User operator gửi thêm `adminRole` vào cập nhật hồ sơ | Từ chối trường ngoài quyền; không nâng đặc quyền |
| Khóa quản trị viên | User operator gửi tài khoản admin vào API khóa người dùng cuối | Từ chối theo loại tài khoản |
| Tác vụ nền | Exporter hết quyền sau khi tạo job nhưng trước lúc tải file | Kết quả không được bàn giao trái chính sách |
| Quản trị cuối cùng | Hai yêu cầu đồng thời loại bỏ hai người quản trị cuối | Giữ được điều kiện tối thiểu của tenant |
| Nguồn quyền lỗi | Không xác minh được trạng thái assignment cho thao tác nhạy cảm | Từ chối an toàn; không dùng fallback toàn quyền |

Với API danh sách, thêm kiểm thử dữ liệu từ nhiều tenant và xác nhận không rò qua kết quả tìm kiếm, tổng số bản ghi hoặc phân trang. Với mỗi endpoint thay đổi trạng thái, kiểm tra cả cơ sở dữ liệu, tác vụ phát sinh và bằng chứng kiểm toán; một mã HTTP từ chối không đủ nếu tác vụ nền đã được đưa vào hàng đợi trước đó.

Một kiểm thử có giá trị cần nêu rõ principal, tập assignment, thời gian, tài nguyên đích và phiên bản chính sách. Nhờ đó khi thất bại, nhóm phát triển có thể xác định lỗi nằm ở ma trận quyền, kiểm tra scope hay vòng đời quyền.

## 15. Trình tự triển khai capstone

Bắt đầu bằng một lát cắt nhỏ: `SUPPORT_AGENT` với `user.read` và `session.revoke` trên một tenant. Tạo tài khoản thử thuộc hai tenant, chứng minh thao tác đúng scope thành công và thao tác chéo tenant bị chặn. Chỉ sau đó mở rộng sang quản lý người dùng, cấp quyền có phê duyệt và xuất dữ liệu.

Trình tự thực hiện đề xuất:

1. Viết danh mục hành động và xác định dữ liệu, tác dụng phụ của từng hành động.
2. Chốt ma trận role–permission và ràng buộc đối tượng; chỉ rõ phần nào là quyền thường ngày, phần nào cần cấp tạm thời.
3. Mô hình hóa assignment có tenant, thời hạn, trạng thái thu hồi và nguồn cấp quyền.
4. Triển khai kiểm tra ở backend với tài nguyên thực, bao gồm các đường gọi nội bộ.
5. Thêm quy trình đề nghị–phê duyệt–áp dụng với kiểm soát đồng thời và retry.
6. Triển khai thu hồi, cache, log và kiểm soát tác vụ nền theo các cam kết đã chọn.
7. Chạy bộ kiểm thử quyền được phép, quyền bị từ chối, thời hạn và truy cập chéo tenant.

Để nghiệm thu, người học phải giải thích được vì sao một principal cụ thể có hoặc không có quyền thực hiện một hành động. Lời giải cần truy ngược từ hành động qua permission, assignment, scope và ràng buộc; câu trả lời “vì người đó là admin” chưa đủ.

Thiết kế đạt mục tiêu khi role phản ánh trách nhiệm, quyền quản trị có phạm vi và thời hạn phù hợp, mọi đường thực thi đều kiểm tra cùng chính sách, và các thay đổi quyền có thể thu hồi cũng như truy vết. RBAC khi đó trở thành cơ chế quản lý vòng đời quyền có thể vận hành được, thay vì chỉ là một cột role trong bảng người dùng.
