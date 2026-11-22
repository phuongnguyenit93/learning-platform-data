# Chống sửa tham số vai trò để vượt quyền (Role parameter tampering)

Một người có thể sửa body, query, header hoặc dữ liệu giao diện để tự khai mình là quản lý, người duyệt hay quản trị viên. Nếu máy chủ lấy giá trị đó làm nguồn phân quyền, một request bình thường có thể trở thành hành động vượt quyền mà không cần chiếm tài khoản đặc quyền.

Ví dụ, người dùng gửi thêm `role=APPROVER` khi gọi API duyệt đơn hoặc thêm `roles=["TENANT_ADMIN"]` trong lệnh cập nhật hồ sơ cá nhân. Nguy cơ xuất hiện khi ứng dụng dùng dữ liệu do người gọi điều khiển để dựng ngữ cảnh quyền hoặc lưu assignment ngoài thẩm quyền.

Bài học thuộc chương **Parameter Tampering** trong bảo mật logic nghiệp vụ. Trọng tâm là ngăn tham số role vượt qua ranh giới tin cậy, đồng thời giữ đúng tenant, đối tượng, trạng thái, phân tách nhiệm vụ, transaction và idempotency.

## 1. Tham số role khác với quyền được xác minh

Có thể phân biệt ba dữ kiện:

| Dữ kiện | Ví dụ | Giá trị thẩm quyền |
|---|---|---|
| Role người gọi tự khai | Body có `role: "ADMIN"` | Chỉ là đầu vào, không tự chứng minh quyền |
| Assignment có thẩm quyền | Hệ thống phân quyền ghi người U có role R trong tenant A | Là dữ kiện cần kiểm tra cùng hiệu lực và phạm vi |
| Quyết định cho hành động | U được duyệt đơn O theo policy hiện tại | Kết quả của đánh giá quyền và điều kiện trên đối tượng |

Một assignment hợp lệ chưa cho phép mọi hành động. Một role đang hoạt động vẫn chịu hạn mức, scope, trạng thái và phân tách nhiệm vụ.

Không nên dùng tên role do client gửi để chọn thẳng một nhánh đặc quyền:

```java
// Dữ liệu request bị biến thành thẩm quyền.
if ("ADMIN".equals(body.role())) {
    approveWithoutFurtherChecks();
}
```

Giá trị role có thể đúng cú pháp và có thật trong hệ thống nhưng vẫn không thuộc người gọi hoặc không áp dụng trong tenant đang xử lý.

### 1.1. Tham số có thể nằm ở nhiều vị trí

```text
body:          role=ADMIN
query:         ?actingRole=APPROVER
header:        X-Role: TENANT_ADMIN
cookie riêng:  isAdmin=true
object lồng:   user.security.roles=[...]
message:       principal.role=SYSTEM
```

Tên hoặc vị trí không quyết định độ tin cậy. Một header nội bộ chỉ có thẩm quyền nếu kiến trúc xác minh nguồn, bảo vệ đường truyền và xử lý header từ caller theo đúng hợp đồng.

Field ẩn, dropdown bị khóa hoặc giá trị chỉ xuất hiện trong mã giao diện vẫn nằm trong môi trường người dùng có thể điều khiển. Mã hóa biểu diễn như Base64 không tạo quyền.

### 1.2. Hai kiểu leo thang cần chặn

| Kiểu | Ví dụ | Ranh giới bị phá |
|---|---|---|
| Dùng role giả cho request hiện tại | Gửi role APPROVER để duyệt ngay | Tạo ngữ cảnh hoặc quyết định quyền từ dữ liệu tự khai |
| Ghi role trái phép để dùng về sau | Sửa profile rồi được lưu thêm role quản trị | Thay đổi assignment ngoài hành động quản trị có thẩm quyền |

Kiểu thứ hai có thể chưa tạo tác dụng đặc quyền trong response hiện tại nhưng xuất hiện ở lần đăng nhập hoặc request tiếp theo. Cần kiểm tra cả dữ liệu lưu, token mới và tác vụ nền liên quan.

## 2. Phân loại tham số role theo mục đích

Không phải mọi endpoint có roleId đều sai. Điều cần xác định là role đó đang mô tả **actor**, **đối tượng quản trị**, **lựa chọn activation** hay chỉ là **bộ lọc**.

| Tham số | Mục đích hợp lệ có thể có | Kiểm tra bắt buộc |
|---|---|---|
| role của actor tự khai | Không phải nguồn quyền cho caller thông thường | Không dùng để cấp khả năng |
| selectedRoleId | Chọn một role đủ điều kiện kích hoạt | Assignment, tenant, phiên, hiệu lực và xung đột |
| targetRoleIds | Đề nghị thay assignment của người khác hoặc chính mình theo luồng được phép | Quyền quản trị, role đích, target, scope và các điều kiện bổ sung |
| roleFilter | Lọc danh sách người dùng được phép xem | Không mở rộng tập dữ liệu hoặc quyền của actor |
| Role claim từ nguồn xác thực | Dữ kiện từ một hợp đồng tin cậy cụ thể | Xác minh nguồn, đối tượng nhận, thời hạn, ánh xạ và scope |

Tên `role` có thể gây nhầm giữa người thực hiện và người được quản trị. Nên đặt tên và kiểu dữ liệu thể hiện ý định rõ, tránh dùng chung một object user chứa cả actor lẫn target.

### 2.1. Chọn role không tạo assignment

Nếu U được gán STAFF và có điều kiện kích hoạt APPROVER, U có thể được chọn một role trong tập được phép. Gửi `selectedRoleId=TENANT_ADMIN` không làm role đó trở thành một lựa chọn hợp lệ.

Tập lựa chọn hiển thị trên giao diện chỉ hỗ trợ trải nghiệm. Máy chủ phải kiểm tra lại khi nhận lệnh.

### 2.2. Role dùng để lọc không được đổi quyền

Một trang quản trị có thể nhận `roleFilter=APPROVER` để lọc những người mà caller được phép xem. Nó không được dùng giá trị đó làm role của caller trong cùng request.

Tương tự, route quản trị một role cụ thể không chứng minh người gọi đang có role đó hoặc được sửa mọi thuộc tính của nó.

## 3. Dựng danh tính và quyền từ nguồn có thẩm quyền

Một luồng an toàn tách dữ liệu nghiệp vụ khỏi ngữ cảnh xác thực:

```text
Thông tin xác thực
    → xác minh nguồn và ràng buộc
    → danh tính thực
    → tenant và quan hệ đại diện được phép
    → assignment, activation và policy phù hợp
    → quyền trên action và đối tượng

Body nghiệp vụ
    → schema của command
    → dữ liệu người dùng được phép đề nghị
```

Hai luồng gặp nhau tại handler để đánh giá hành động. Body không ghi đè danh tính hoặc tập quyền đã xác minh.

### 3.1. Nguồn có thẩm quyền cũng có phạm vi

Nếu dùng token ký, cần xác minh theo hợp đồng về nguồn phát hành, đối tượng nhận, thời hạn và những ràng buộc cần thiết. Chỉ đọc một payload có tên role không đủ.

Ngay cả claim đã được xác minh vẫn cần ánh xạ đúng ứng dụng và tenant. Một role có cùng tên ở một dịch vụ khác không mặc nhiên có nghĩa quản trị tại dịch vụ hiện tại.

Assignment phía máy chủ cũng cần hiệu lực, trạng thái thu hồi và phạm vi. Tên role được lấy đúng nguồn nhưng đã cũ có thể vẫn gây sử dụng quá quyền nếu hệ thống bỏ qua chính sách cập nhật.

### 3.2. Giữ actor và subject được đại diện riêng

Một dịch vụ hoặc người dùng có thể hoạt động thay một chủ thể khác khi có ủy quyền. Cần xác minh quan hệ đó và giữ được danh tính thực.

Không cho body chọn `userId` của quản lý rồi dựng actor như thể quản lý đã xác thực. Không cho header `onBehalfOf` tự tạo quyền đại diện.

Phân tách nhiệm vụ có thể phải xét cả người thực hiện, người được đại diện và người lập giao dịch theo chính sách. Một tài khoản dịch vụ không được dùng để che giấu người tự duyệt.

### 3.3. Kiểu dữ liệu cần thể hiện ranh giới, nhưng tên kiểu chưa đủ

Có thể dùng các kiểu riêng:

```text
AuthenticatedIdentity
VerifiedTenantContext
ApprovalCommand
RoleAssignmentCommand
```

Tuy nhiên, một constructor có tên `TrustedActor` không làm dữ liệu trở nên đáng tin nếu controller vẫn truyền body.role vào đó.

Cần giới hạn đường dựng ngữ cảnh, dùng dữ kiện đã xác minh và kiểm thử những nơi mapper hoặc adapter có thể ghi đè. Không để DTO nghiệp vụ kế thừa một mô hình principal có các setter đặc quyền.

## 4. Ví dụ Java: command phê duyệt không chứa role

Hợp đồng body của lệnh duyệt có thể chỉ nhận:

```json
{
  "expectedVersion": 17,
  "comment": "Đã xem nội dung đề nghị"
}
```

Những field như `role`, `roles`, `isAdmin`, `approvedBy` hoặc `approvalLimit` không thuộc command này. Với chính sách nghiêm, decoder từ chối chúng trước tác dụng nghiệp vụ, kể cả khi chúng nằm trong object con ngoài hợp đồng.

```java
record ApproveBody(
        long expectedVersion,
        String comment) {}

record ApproveCommand(
        String requestId,
        long expectedVersion,
        String comment,
        String idempotencyKey) {}
```

Định danh đối tượng đến từ đường dẫn theo hợp đồng; danh tính và tenant được tạo từ nguồn xác thực đã kiểm tra. Body không được ghi đè các dữ kiện này.

### 4.1. Handler dùng quyền đã phân giải phía máy chủ

Đây là mã giả theo cú pháp Java. Các cổng xác thực, repository, transaction và policy cần triển khai theo hợp đồng tương ứng.

```java
ApprovalResult approve(
        ApproveCommand command,
        VerifiedRequest verifiedRequest) {

    ActorContext actor =
            authenticatedContexts.fromVerifiedRequest(verifiedRequest);

    return transactions.required(() -> {
        PurchaseRequest request = requests
                .findForUpdate(actor.tenantId(), command.requestId())
                .orElseThrow(ResourceNotFound::new);

        accessPolicy.requireMayAccessCommandContext(actor, request);

        CommandClaim claim = commandLog.claimOrReplay(
                actor, "APPROVE_PURCHASE_REQUEST",
                command.idempotencyKey(), fingerprintOf(command));

        if (claim.isCompletedReplay()) {
            resultPolicy.requireMayRead(actor, claim.savedResult());
            return claim.savedResult();
        }

        PermissionSnapshot permissions =
                permissionResolver.resolveApplicable(actor, request);

        authorizer.requireAction(
                actor, permissions,
                Action.APPROVE_PURCHASE_REQUEST, request);

        request.requireVersion(command.expectedVersion());
        request.requireState(RequestState.PENDING_APPROVAL);

        ApprovalChange change = approvalPolicy.evaluate(
                actor, permissions, request, command.comment());

        int changed = requests.applyApprovalIfUnchanged(
                request, change);

        if (changed != 1) {
            throw new ConcurrentChange();
        }

        decisions.insert(change.decision());
        audit.appendApprovalDecision(actor, request, change);
        outbox.appendApprovalChange(change.event());

        ApprovalResult result = ApprovalResult.from(change);
        commandLog.complete(claim, result);
        return result;
    });
}
```

Hợp đồng quan trọng:

- `VerifiedRequest` chỉ được tạo sau xác minh credential và các ràng buộc cần thiết. Không deserialize nó từ body.
- `fromVerifiedRequest` xác định tenant và quan hệ đại diện hợp lệ. Một tenant selector chưa kiểm chứng không đủ.
- `permissionResolver` dùng assignment, activation, policy và phạm vi có thẩm quyền; không dùng một role lẫn trong comment, query hay body.
- Quyền đọc context hoặc kết quả replay khác với quyền ghi một quyết định mới. Mỗi nhánh phải có chính sách phù hợp.
- `approvalPolicy` tiếp tục kiểm tra hạn mức, người lập, nội dung và những bất biến khác. Có role không tự bỏ qua chúng.
- Quyết định ghi người phê duyệt từ ngữ cảnh đã xác minh, đồng thời audit giữ tác nhân thực và quan hệ đại diện nếu có.
- Thay đổi dữ liệu, quyết định, audit, outbox và kết quả lệnh nằm trong cùng transaction minh họa.
- `transactions.required` chỉ trả kết quả sau commit. Lỗi phải rollback những thay đổi tương ứng.
- Dữ liệu quyền thay đổi đồng thời cần cơ chế hiệu lực phù hợp; khóa hàng đơn không tự khóa mọi nguồn assignment hoặc policy bên ngoài.

Nếu một endpoint chọn bỏ qua field ngoài hợp đồng một cách có chủ đích, field role vẫn không được đi vào bất kỳ nguồn quyền hoặc mapper nào khác. Từ chối rõ trong command nhạy cảm giúp tránh việc client hiểu nhầm đầu vào đó đã được chấp nhận.

### 4.2. Bảo vệ cả đường lưu dữ liệu về sau

Không chỉ kiểm tra response của API duyệt. Cần xác nhận không có assignment, cờ quản trị hoặc trường security nào bị cập nhật bởi lệnh này.

Một lần gọi bị chặn không được lưu role vào profile để lần login tiếp theo tự đưa vào token. Tương tự, một vùng metadata không được merge về entity rồi trở thành role khi worker đọc lại.

## 5. Lựa chọn role và tenant hợp lệ

### 5.1. Kích hoạt chỉ trong tập đã được cấp

Một endpoint kích hoạt có thể nhận:

```json
{
  "selectedRoleId": "role-approver",
  "requestedDuration": "khoảng được hợp đồng hỗ trợ",
  "reason": "Xử lý các đề nghị đang chờ"
}
```

Giá trị thời lượng ở đây chỉ minh họa ý định; API thực tế cần kiểu và giới hạn cụ thể.

Máy chủ phải kiểm tra:

- Assignment đúng người và tenant.
- Role có thể được kích hoạt trong ngữ cảnh này.
- Assignment, phiên và các điều kiện cần thiết còn hiệu lực.
- Thời lượng được cấp không vượt những giới hạn áp dụng.
- Các role đang hoạt động không tạo tổ hợp xung đột trái policy.
- Căn cứ bổ sung hoặc phê chuẩn bắt buộc đã đạt.

Không chấp nhận một role không được gán chỉ vì nó có mặt trong bảng định nghĩa role.

### 5.2. Chuyển role không đổi danh tính lịch sử

Người lập tắt role STAFF rồi bật APPROVER vẫn là cùng chủ thể đã lập nội dung. Nếu policy cấm tự duyệt, hành động vẫn phải bị chặn.

Dùng hai account liên kết với cùng một người hoặc một dịch vụ đại diện cũng cần được xét theo mô hình phân tách nhiệm vụ. Chuỗi role khác nhau không chứng minh hai người độc lập.

### 5.3. Role ở tenant A không tự có ở tenant B

Một người có thể là quản trị trong A nhưng là thành viên thông thường trong B.

Khi đổi tenant selector, phải xây lại ngữ cảnh quyền tương ứng. Không giữ nguyên `activeRole=ADMIN` của tenant trước rồi áp cho dữ liệu tenant mới.

Role định nghĩa dùng chung toàn hệ thống có thể tồn tại, nhưng assignment và scope vẫn cần được giải thích đúng. Một ID role hợp lệ không chứng minh mọi assignment tới ID đó có cùng phạm vi.

## 6. Endpoint quản trị role cần kiểm tra quyền cấp, không tin role đích

Một lệnh gán role hợp lệ có thể nhận targetSubjectId, targetRoleId, scope và thời hạn đề nghị. Đây là dữ liệu mô tả **thay đổi muốn thực hiện**, không phải thẩm quyền của người gửi.

Máy chủ cần đánh giá:

| Thành phần | Câu hỏi |
|---|---|
| Actor | Ai thực sự đang thực hiện quản trị? |
| Target | Người hoặc dịch vụ nào sẽ nhận assignment? |
| Role đích | Role có tồn tại và thuộc phạm vi quản trị không? |
| Scope | Tenant, đơn vị, dự án hoặc tài nguyên nào được cấp? |
| Quyền cấp | Actor có được cấp role này với scope và thời hạn này không? |
| Ràng buộc | Có role bị bảo vệ, xung đột hoặc cần phê chuẩn độc lập không? |
| Hiệu lực | Assignment bắt đầu, kết thúc và bị thu hồi thế nào? |

Được xem danh sách role hoặc quản lý hồ sơ người dùng không đồng nghĩa được cấp mọi role.

### 6.1. Không suy quyền cấp từ việc đang có role

Một người có quyền nghiệp vụ chưa chắc được phép cấp quyền đó cho người khác.

Ngược lại, một vai trò quản trị assignment có thể được policy cho phép cấp một số role mà chính họ không dùng cho nghiệp vụ. Quyền cấp phải do chính sách quản trị xác định, không suy ra máy móc từ tập role cá nhân.

Giới hạn cấp cần giữ cả role, target, tenant, scope và thời hạn. Một người được quản lý assignment của dự án X không được đổi scope thành toàn tenant bằng một tham số.

### 6.2. Tránh mô hình cấp bậc số đơn giản

Một điều kiện như:

```java
if (targetRole.level() <= actorRole.level()) {
    allowAssignment();
}
```

không tự xử lý được role khác miền chức năng, phạm vi tenant, hạn mức, quyền cấp hoặc xung đột nhiệm vụ.

Role không nhất thiết tạo thành một thang tuyến tính. Tên hoặc số thứ tự thấp hơn không chứng minh quyền đích là tập con phù hợp với thẩm quyền của actor.

Nếu có cơ chế kế thừa hoặc role tùy biến, cần kiểm tra khả năng hiệu lực và các ràng buộc theo mô hình. Không để người chỉ được cấp role thấp tự sửa định nghĩa role đó thành quyền quản trị trước khi gán.

### 6.3. Tự đăng ký, profile và lời mời

Endpoint đăng ký hoặc cập nhật profile nên xác định những thuộc tính tự phục vụ rõ ràng. Field mô tả công việc không được tự ánh xạ thành assignment bảo mật.

Nếu một lời mời cấp role, role và scope cần gắn với căn cứ lời mời có thẩm quyền cùng các điều kiện hiệu lực. Người nhận không được thay chúng bằng dữ liệu body không được kiểm chứng.

Các bước liên kết tài khoản hoặc đồng bộ danh tính cũng cần ánh xạ role theo nguồn và policy. Một nhãn tự khai ở profile bên ngoài không mặc nhiên là role quản trị của ứng dụng.

### 6.4. Thay assignment phải nhất quán và có dấu vết

Ghi assignment, version hoặc generation quyền liên quan, audit và sự kiện cập nhật cần nằm trong ranh giới nhất quán của thiết kế.

Nếu thay đổi cần phê chuẩn, đề nghị gán role chưa phải assignment hiệu lực. Không để một trường `approved=true` từ caller thay thế quyết định của chủ thể có thẩm quyền.

Các cache hoặc token phụ thuộc cần xử lý theo bảo đảm thu hồi và cập nhật đã công bố. Ghi thành công một hàng assignment không tự chứng minh mọi dịch vụ đã nhận thay đổi.

## 7. Không để đường bind khác khôi phục role giả

### 7.1. Whitelist theo command, không chỉ chặn một tên field

Chặn riêng key `role` nhưng vẫn nhận `roles`, `permissions`, `isAdmin` hoặc object security không thuộc hợp đồng có thể để lại cùng một đường gán quyền.

Không giải quyết bằng việc liên tục thêm blacklist các tên đoán được. Mỗi command cần danh sách trường được phép, schema lồng nhau và mapper tường minh.

Một field có tên vô hại nhưng được code phía sau ánh xạ thành assignment vẫn có thể là nguồn vượt quyền. Điều cần kiểm tra là luồng dữ liệu từ đầu vào tới quyết định và nơi lưu quyền.

### 7.2. Trường trùng, alias và nhiều nguồn cùng tên

Một request có thể làm các tầng thấy giá trị khác nhau nếu có tên trùng hoặc alias xung đột. Với tham số chọn role hợp lệ, cần phát hiện nhập nhằng trước khi bind làm mất dữ kiện.

Nếu query, body và header đều có `selectedRoleId`, hợp đồng phải xác định nguồn nào được nhận và cách xử lý mâu thuẫn. Không để validator kiểm tra một nguồn còn handler dùng nguồn khác.

Với role của actor, không nguồn tự khai nào trong các vị trí đó được phép ghi đè ngữ cảnh đã xác minh.

Không dựa vào việc lọc chuỗi “ADMIN”. Một role khác tên vẫn có thể chứa khả năng nhạy cảm, còn tên có vẻ quản trị có thể chỉ là nhãn không có thẩm quyền. Quyết định phải theo assignment và policy thực tế.

### 7.3. Không merge body vào principal

Một mẫu nguy hiểm:

```text
context = ngữ cảnh đã xác thực
    → merge mọi thuộc tính body vào context
    → kiểm tra context.role
```

Cách làm này biến dữ liệu nghiệp vụ thành thuộc tính đặc quyền ngay cả khi lớp xác thực ban đầu đúng.

Tương tự, một mapper sao chép từ profile, metadata hoặc object user lồng nhau vào principal có thể gây ghi đè gián tiếp.

Nên giữ ngữ cảnh quyền bất biến theo hợp đồng và cập nhật domain qua các lệnh riêng. Field dùng để mô tả target không được tự trở thành field của actor.

### 7.4. Header từ gateway cần ranh giới thực sự

Một backend có thể nhận danh tính hoặc role từ gateway theo kiến trúc. Để có thẩm quyền, cần xác minh nguồn gọi, bảo vệ đường truyền và bảo đảm caller bên ngoài không tự đặt các header dành cho gateway.

Nếu người dùng có thể gọi trực tiếp backend hoặc gateway giữ nguyên header giả, việc endpoint chỉ “tin header nội bộ” là chưa đủ.

Backend cần hợp đồng rõ về nguồn dữ kiện, phạm vi và khả năng xác minh. Tên header bắt đầu bằng một tiền tố nội bộ không tự tạo tính tin cậy.

## 8. Token, dịch vụ gọi thay và cache

### 8.1. Đọc claim không đồng nghĩa xác minh claim

Một token có payload chứa role phải được xác minh theo hợp đồng trước khi dùng. Không chỉ decode rồi gán role vào actor.

Xác minh đúng còn cần kiểm tra nguồn, nơi nhận, thời hạn và ngữ cảnh. Một claim hợp lệ cho ứng dụng khác hoặc tenant khác không tự trở thành quyền hiện tại.

Sau đó, ứng dụng vẫn cần ánh xạ role và kiểm tra action, resource, activation hoặc trạng thái thu hồi phù hợp. Chữ ký hợp lệ không làm mọi nội dung nghiệp vụ trong request trở nên đúng.

### 8.2. Quyền đã thay đổi nhưng token còn dữ liệu cũ

Nếu role bị thu hồi nhưng token cũ vẫn được chấp nhận, cần biết bảo đảm mà kiến trúc cung cấp.

Có thể dùng nguồn assignment hiện tại, version hoặc generation quyền, cơ chế kiểm chứng trạng thái hay thời hạn phù hợp. Những cách này có mức nhất quán khác nhau.

Không hứa thu hồi tức thì nếu hệ thống chỉ giữ một danh sách role tự chứa tới lúc token hết hạn. Không dùng lỗi tải dữ liệu mới làm lý do tin role từ body.

Refresh token hoặc phát phiên mới cần lấy role theo nguồn cùng chính sách có thẩm quyền. Không chép một trường profile đã bị người dùng tự thay vào quyền phát hành.

### 8.3. Dịch vụ mạnh không bù quyền người dùng thiếu

Khi S gọi thay U, một mô hình có thể là:

```text
Quyền hiệu lực =
    quyền U được cấp
    ∩ giới hạn dịch vụ S
    ∩ scope ủy quyền
    ∩ giới hạn token
    ∩ phạm vi tenant và đối tượng
```

Không hợp quyền quản trị của S với dữ liệu role U tự khai để tạo một caller mạnh hơn.

Một job hệ thống tự chủ có thể có policy riêng. Nhưng đó phải là danh tính và luồng được xác định rõ; một tham số `executeAs=SYSTEM` không tự chuyển request của người dùng sang luồng đó.

Message nên tham chiếu căn cứ hoặc execution có thẩm quyền theo hợp đồng. Không chỉ mang `role=ADMIN` rồi để consumer bỏ qua quyền ban đầu.

### 8.4. Cache định nghĩa role không phải cache assignment

Có thể cache định nghĩa role để biết nó chứa những capability nào. Tuy nhiên, việc tìm thấy role trong cache không chứng minh caller được gán nó.

Nếu dùng `body.role` làm khóa lấy capability rồi coi kết quả là quyền caller, cache chỉ làm đường vượt quyền chạy nhanh hơn.

Cache quyết định cần đúng tenant, subject, action, resource, context và các phiên bản hoặc hiệu lực liên quan. Một role cùng tên ở hai tenant không được làm lẫn scope.

Khi nguồn quyền không sẵn sàng, không dự phòng bằng role được đề nghị trong request. Cách từ chối hoặc báo lỗi tạm thời phải giữ nguyên ranh giới.

## 9. Transaction, thời điểm quyết định và idempotency

### 9.1. Quyền cần được đánh giá trước tác dụng theo đúng mốc

Một lệnh mới phải được kiểm tra bằng dữ kiện có thẩm quyền trước khi thay đổi nghiệp vụ.

Nếu role, assignment hoặc tenant membership có thể đổi đồng thời, cần chọn cơ chế nhất quán và mốc kiểm tra phù hợp. Một lần kiểm tra ở giao diện hoặc đầu phiên không bao phủ mọi lệnh tương lai.

Nếu action cần role còn hoạt động tại điểm worker thực hiện, phải có cổng kiểm tra hoặc execution có hợp đồng tương ứng. Không để hàng đợi biến role cũ thành quyền vô thời hạn.

Đồng thời, hết role sau một quyết định hợp lệ không tự xóa lịch sử của quyết định. Cần phân biệt quyền hiện tại, căn cứ quyết định cũ và quyền cho hành động tiếp theo.

### 9.2. Không phân quyền từ target đã bị mutate

Một lỗi đặc biệt là dùng chung object cho actor và tài khoản được cập nhật:

```text
tải user đích
    → chép role từ body vào user
    → thấy user có role quản trị
    → cho phép lưu
```

Khi actor chính là target, object trong bộ nhớ đã bị dữ liệu đầu vào thay đổi trước kiểm tra. Nó không còn phản ánh căn cứ quyền ban đầu.

Ngữ cảnh actor phải tách khỏi target mutable. Kiểm tra thẩm quyền quản trị bằng nguồn đúng, rồi mới áp dụng thay đổi được phép. Các quyết định cần kiểm tra lại khi dữ kiện liên quan đổi theo giao thức.

### 9.3. Role giả không được đi vòng qua nhánh replay

Với command nghiêm không nhận role, request có thêm role lạ phải được xử lý theo hợp đồng cấu trúc trước khi coi nó là một lệnh hợp lệ.

Không xóa field đó rồi trả kết quả idempotency như thể đầu vào mới đã được chấp nhận đúng ý định.

Với endpoint thật sự nhận targetRoleId hoặc selectedRoleId, fingerprint phải giữ các trường có ý nghĩa đó cùng target, tenant context, version và scope liên quan. Cùng key nhưng đổi role đích không được phát lại nhầm kết quả cũ.

Ngược lại, role giả của actor không phải một nguồn thẩm quyền cần “chuẩn hóa” thành actor thật. Nó phải bị chặn hoặc bị cách ly theo hợp đồng, không đi vào quyền.

### 9.4. Lệnh bị từ chối không được lưu dấu vết cấp quyền thành công

Khi kiểm tra thất bại, transaction không được để lại assignment, activation, trạng thái phê duyệt hoặc outbox báo thành công dở dang.

Audit lần thử bị chặn có thể được lưu qua đường phù hợp. Nó cần khác với bản ghi cho thấy một role đã thật sự được cấp.

Nếu commit chưa rõ do lỗi kết nối, cần đối soát lệnh trước khi kết luận đã từ chối hoặc thực hiện lại.

## 10. Phản hồi và audit không được tin role tự khai

Một lỗi đầu vào có thể là:

```json
{
  "code": "INVALID_COMMAND_BODY",
  "errors": [
    { "code": "UNKNOWN_FIELD", "path": "$.role" }
  ],
  "correlationId": "CORR-620"
}
```

Nếu command hợp lệ về cấu trúc nhưng caller thiếu quyền thật, phản hồi cần theo hợp đồng phân quyền và chính sách che giấu đối tượng. Không trả danh sách role bí mật hoặc thông tin tenant khác để hướng dẫn cách chọn một giá trị được chấp nhận.

### 10.1. Tách role được đề nghị khỏi quyền thực tế trong log

Một bản ghi không nên ghi `actorRole=ADMIN` chỉ vì request có giá trị đó. Điều này làm sai cả điều tra lẫn chỉ số sử dụng quyền.

Nếu cần lưu lần thử, dùng tên phản ánh đúng ý nghĩa như trường được đề nghị, loại đầu vào bị chặn và nguồn quyền thực sự đã được đánh giá.

Audit hành động hợp lệ nên liên kết actor thực, subject được đại diện, tenant, đối tượng, action, assignment hoặc policy liên quan và kết quả. Với thay role, cần phân biệt người cấp với người nhận.

Không ghi nguyên credential, token hoặc toàn bộ payload nhạy cảm. Tên field và giá trị do caller điều khiển cũng cần định dạng an toàn cùng giới hạn.

### 10.2. Quan sát cả thay đổi trì hoãn

Nhiều lần gửi field quyền, thay targetRoleId, đổi tenant selector hoặc dùng sai header có thể là tín hiệu lạm dụng.

Cũng cần theo dõi profile, import hoặc đồng bộ đã làm assignment thay đổi ngoài endpoint quản trị. Một đường gán role trì hoãn có thể không xuất hiện ở API đặc quyền mà xuất hiện khi phát token tiếp theo.

Các tín hiệu cần được đánh giá theo ngữ cảnh; lỗi tích hợp hoặc client cũ không tự là bằng chứng cố ý tấn công.

## 11. Những thiết kế dễ tạo đường vượt quyền

| Thiết kế | Vấn đề | Hướng xử lý |
|---|---|---|
| Lấy role của actor từ body hoặc query | Caller tự quyết định quyền | Dựng actor từ nguồn xác thực và assignment có thẩm quyền |
| Bind profile thẳng vào entity có role | Ghi quyền trái phép để dùng về sau | DTO tự phục vụ riêng, cập nhật tường minh |
| Chỉ chặn chuỗi ADMIN | Không kiểm soát role khác hoặc capability thực tế | Kiểm tra quyền theo role, scope và action |
| Tin header có tên nội bộ | Caller có thể tự đặt hoặc đi đường trực tiếp | Xác minh nguồn và ranh giới gateway-backend |
| Chỉ decode token | Claim chưa được kiểm chứng | Xác minh toàn bộ hợp đồng xác thực |
| Kiểm tra roleId có tồn tại | Không chứng minh assignment | Kiểm tra người được gán, tenant và hiệu lực |
| Dùng target đã mutate làm actor | Dữ liệu đầu vào tự hợp thức hóa thay đổi | Tách actor bất biến và target |
| So level số để cấp mọi role thấp hơn | Bỏ scope và quyền cấp | Policy quản trị target, role, scope và điều kiện |
| Tin role trong message vì từ nội bộ | Worker trở thành đường cấp quyền | Giữ căn cứ giao việc và mô hình đại diện |
| Policy lỗi thì dùng role được đề nghị | Lỗi phụ thuộc mở đường vượt quyền | Không thực thi khi thiếu căn cứ bắt buộc |

Những kiểm soát này cần áp dụng trên mọi đường ghi assignment và mọi đường dựng principal. Bảo vệ một controller không đủ nếu import hoặc adapter khác vẫn đưa dữ liệu tự khai vào quyền.

## 12. Kiểm thử role parameter tampering

### 12.1. Ma trận tình huống

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| STAFF thêm role APPROVER vào lệnh duyệt | Không tạo quyền hoặc quyết định hợp lệ từ field đó |
| Thêm roles, isAdmin hoặc permissions ngoài hợp đồng | Không gán quyền qua một tên khác |
| Field quyền nằm trong object user hoặc metadata | Không bị merge về principal hay assignment |
| Thay query, cookie hoặc header tự khai role | Không ghi đè quyền đã xác minh |
| Gửi header dành cho gateway từ đường ngoài | Không được tin như dữ kiện nội bộ có thẩm quyền |
| Dùng token có claim không thỏa hợp đồng xác minh | Không dựng actor từ claim chưa được chấp nhận |
| Claim cùng tên role nhưng sai ứng dụng hoặc tenant | Không ánh xạ thành quyền hiện tại ngoài scope |
| Chọn role tồn tại nhưng chưa được gán | Không tạo activation |
| Chọn role được gán nhưng đã hết hoặc bị thu hồi | Áp dụng đúng hiệu lực, không tự cấp lại |
| Người quản trị A chuyển sang tenant B | Không giữ quyền A cho B |
| Người chỉ được cấp role trong dự án X đổi scope | Không mở rộng assignment ra ngoài thẩm quyền |
| Có quyền dùng role nhưng không có quyền cấp | Không suy ra được phép gán cho người khác |
| Có quyền quản trị assignment hợp lệ theo policy | Cho phép đúng role đích và scope, không chặn máy móc vì actor không dùng role đó |
| Tự đăng ký hoặc sửa profile kèm role quản trị | Không lưu assignment trái quyền |
| Đổi target role definition để tăng quyền rồi gán | Policy quản trị định nghĩa và assignment vẫn kiểm soát tổ hợp |
| Actor và target là cùng một object tài khoản | Không dùng role đã mutate từ body làm căn cứ cho phép |
| Hai alias hoặc hai nguồn có selectedRoleId mâu thuẫn | Phát hiện nhập nhằng theo hợp đồng |
| Dịch vụ rộng quyền gọi thay user thiếu quyền | Không bù quyền user bằng role kỹ thuật |
| Message có executeAs SYSTEM | Không tự đổi sang danh tính hệ thống |
| Cùng key nhưng đổi targetRoleId hoặc scope | Không trả nhầm kết quả lệnh cũ |
| Token, cache còn dữ liệu role cũ | Hành vi đúng bảo đảm cập nhật và thu hồi đã công bố |
| Người lập đổi active role rồi tự duyệt | Phân tách nhiệm vụ vẫn dùng danh tính và lịch sử đúng |

Cần có cả ca hợp lệ để chứng minh luồng chọn hoặc quản trị role hoạt động đúng phạm vi. Mục tiêu là chặn nguồn quyền sai, không phải cấm mọi tham số có tên role.

### 12.2. Kiểm thử đường tự nâng quyền trì hoãn

Một ca end-to-end có thể làm:

```text
Chuẩn bị:
    A chỉ có quyền thông thường trong tenant T

Gửi:
    lệnh sửa profile hoặc đăng ký có thêm field role đặc quyền

Kiểm tra ngay:
    response đúng hợp đồng
    assignment và thuộc tính bảo mật không tăng quyền

Kiểm tra về sau:
    token hoặc phiên mới không nhận quyền từ field giả
    worker và đồng bộ không tạo assignment trái phép
    action đặc quyền vẫn bị chặn
```

Nếu chỉ kiểm tra response hiện tại, có thể bỏ sót dữ liệu đã được lưu để ảnh hưởng lần đăng nhập sau.

Tương tự, cần thử import hoặc adapter đồng bộ nếu chúng có thể ghi cùng những thuộc tính. Không mặc định chúng dùng cùng DTO và cấu hình với API profile.

### 12.3. Kiểm thử ranh giới parser, mapper và context

Gửi request qua đường nhận thực để kiểm tra:

- Field ngoài hợp đồng ở root và object con.
- Tên trùng trước khi bị gộp vào map.
- Alias, chữ hoa thường và cách mã hóa được parser chấp nhận.
- Query, body và header có giá trị mâu thuẫn.
- Mapper cập nhật target mà không chạm actor.
- Đường tạo context không nhận role từ DTO.
- Cấu hình gateway xử lý header tự khai và đường truy cập trực tiếp.
- Cache không lấy role được đề nghị làm bằng chứng assignment.

Một test chỉ tạo sẵn ActorContext đúng rồi gọi handler không chứng minh adapter đã dựng context an toàn.

### 12.4. Kiểm tra sự vắng mặt của thay đổi

Sau một lần vượt quyền bị chặn:

```text
không có assignment hoặc activation đặc quyền mới
không đổi membership hoặc role definition ngoài thẩm quyền
không ghi role giả vào profile để dùng về sau
không có quyết định phê duyệt hoặc execution mới
không đổi owner, tenant hoặc trạng thái nghiệp vụ
không tạo outbox báo cấp quyền hoặc duyệt thành công
không phát token mới có quyền tăng từ dữ liệu tự khai
không ghi audit giả rằng caller thật sự có role đã gửi
```

Log từ chối hoặc chỉ số bảo vệ có thể được ghi theo chính sách. Các assignment và quyết định hợp lệ đã có từ trước phải được giữ nguyên.

Với transaction lỗi giữa các bước quản trị role, cần kiểm tra không có trạng thái cấp quyền dở dang hoặc generation không khớp nguồn dữ liệu.

### 12.5. Cạnh tranh và thay đổi ngữ cảnh

Các ca tích hợp đáng kiểm tra:

1. Assignment bị thu hồi trong lúc action đang xử lý.
2. Người dùng đổi tenant nhưng phiên hoặc cache còn active role trước đó.
3. Hai lệnh gán role cùng tranh chấp một target và scope.
4. Role definition thay đổi trong khi một lệnh cấp đang được xét.
5. Commit gán role thành công nhưng mất phản hồi.
6. Consumer nhận lại message cũ hoặc thông tin đại diện không còn đáp ứng chính sách.
7. Lệnh hợp lệ bị chậm tới sau khi khoảng kích hoạt hết hạn.

Kỳ vọng phải bám vào mốc kiểm tra và mức nhất quán đã công bố. Không giả định một transaction cục bộ đã khóa mọi nguồn danh tính hoặc policy bên ngoài.

## 13. Bài tập áp dụng

Thiết kế API duyệt đơn và API quản trị role cho hệ thống nhiều tenant.

1. Chỉ ra những dữ kiện được lấy từ credential, assignment, context và command.
2. Thiết kế DTO của lệnh duyệt để không nhận role, người duyệt hoặc hạn mức từ client.
3. Mô tả cách một role selector hợp lệ được kiểm tra mà không tạo assignment mới.
4. Tách actor, target và quan hệ đại diện trong lệnh gán role.
5. Viết policy giới hạn role đích, tenant, scope và thời hạn mà một quản trị viên được cấp.
6. Chỉ ra cách chống role giả qua profile, header gateway, message và cache.
7. Xác định hành vi khi role đã bị thu hồi nhưng token còn hạn.
8. Thiết kế audit phân biệt role được đề nghị với assignment và quyết định thực tế.
9. Viết ca kiểm thử tự nâng quyền trì hoãn và actor bị nhầm với target mutable.

Một cơ chế phân quyền đáng tin cần chứng minh vai trò đến từ đâu, thuộc ai, áp dụng ở phạm vi nào và có cho phép chính hành động đang xét không. Tham số do client gửi chỉ thể hiện ý định hoặc dữ liệu; nó chỉ được tạo thay đổi quyền qua một luồng có thẩm quyền và không được tự trở thành quyền của người gọi.
