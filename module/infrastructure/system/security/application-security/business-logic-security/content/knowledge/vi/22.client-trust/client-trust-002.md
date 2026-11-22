# Untrusted mobile state: không dùng trạng thái trên thiết bị làm thẩm quyền nghiệp vụ

Trong chương **Client Trust**, untrusted mobile state là nguyên tắc xem dữ liệu do ứng dụng di động gửi lên như đầu vào cần xác minh, kể cả khi dữ liệu đó từng được máy chủ trả về hoặc đang nằm trong kho lưu trữ cục bộ được bảo vệ. Trạng thái trên thiết bị có thể bị sửa, khôi phục từ bản cũ, dùng sai tài khoản hoặc đơn giản là không còn phản ánh dữ liệu hiện tại.

Trong module bảo vệ logic nghiệp vụ, vấn đề này xuất hiện khi máy chủ tin một cờ đã duyệt, hạn mức, tenant, giá hoặc kết quả xác minh do ứng dụng tự khai. Một ứng dụng chính thức, một phiên đăng nhập hợp lệ hay một thiết bị vượt kiểm tra môi trường không tự chứng minh từng quyết định nghiệp vụ là đúng.

Bài học dùng ví dụ ứng dụng duyệt đề nghị chi công tác có khả năng lưu nháp và xếp lệnh khi mất mạng. Trọng tâm là giữ đúng quyền theo đối tượng, snapshot, thứ tự workflow, transaction và idempotency khi thiết bị đồng bộ trở lại.

Sau bài này, bạn có thể:

- Phân biệt bản sao trạng thái trên thiết bị với nguồn có thẩm quyền ở máy chủ.
- Thiết kế hàng đợi offline chứa ý định thay vì kết luận đã được chấp nhận.
- Ngăn dùng quyền, giá trị hoặc nội dung cũ để tạo quyết định mới.
- Xử lý đổi tài khoản, nhiều thiết bị, mất phản hồi và đồng bộ lặp.
- Đặt đúng vai trò của bảo vệ lưu trữ, xác thực thiết bị và các tín hiệu chống can thiệp.
- Kiểm thử dữ liệu cục bộ bị sửa cùng các tình huống lỗi tự nhiên của ứng dụng di động.

## 1. Dữ liệu do ứng dụng chính thức gửi vẫn cần được xác minh

Giả sử ứng dụng lưu một bản trạng thái:

```json
{
  "currentTenantId": "tenant-a",
  "currentPersonId": "person-17",
  "roles": ["APPROVER"],
  "approvalLimitVnd": 100000000,
  "biometricPassed": true,
  "expense": {
    "id": "expense-42",
    "version": 7,
    "status": "APPROVED",
    "amountVnd": 1000000
  }
}
```

Nếu endpoint đồng bộ nhận nguyên cấu trúc này rồi cập nhật dữ liệu, caller có thể tự khai vai trò, hạn mức hoặc kết quả phê duyệt. Ngay cả khi không có can thiệp, dữ liệu có thể đã cũ: người dùng mất quyền, đề nghị đổi số tiền hoặc tenant hiện tại không còn là tenant lúc tạo lệnh.

Máy chủ cần tách:

```text
người dùng muốn duyệt đề nghị nào
khỏi
người dùng có quyền duyệt đề nghị đó lúc quyết định được chấp nhận không
```

Vế thứ nhất có thể đến từ client. Vế thứ hai phải được xác lập bằng danh tính, dữ liệu và chính sách có thẩm quyền.

## 2. Trạng thái mobile có thể sai theo nhiều cách

Không cần giả định mọi thiết bị đều bị can thiệp để thấy rủi ro.

| Tình huống | Hệ quả có thể có |
| --- | --- |
| Dữ liệu cục bộ bị thay đổi | Giá, vai trò, cờ duyệt hoặc chủ thể bị giả |
| Ứng dụng dùng bản cache cũ | Người dùng nhìn và thao tác trên quyền hoặc nội dung đã thay đổi |
| Khôi phục bản sao lưu | Lệnh đã gửi hoặc bộ đếm cũ xuất hiện lại |
| Nhiều thiết bị cùng hoạt động | Hai thiết bị cùng tưởng tài nguyên hoặc nhiệm vụ vẫn chưa được xử lý |
| Đổi tài khoản trên cùng thiết bị | Lệnh của người A bị gửi bằng phiên của người B |
| Đổi tenant làm việc | ID và dữ liệu của tenant trước bị trộn vào request mới |
| Đồng hồ thiết bị sai hoặc bị chỉnh | Thời hạn, thứ tự hoặc thời điểm được khai không đáng tin |
| Ứng dụng bị đóng giữa các bước | Không biết request chưa gửi, đã commit hay chỉ mất phản hồi |
| Notification hoặc deep link cũ | Điều hướng tới đối tượng đã đổi quyền hoặc trạng thái |

Các tình huống này có thể tạo lỗi nghiệp vụ giống hành vi lạm dụng: thực hiện hai lần, duyệt sai nội dung hoặc truy cập nhầm đối tượng.

Thiết kế tốt không dựa vào giả định rằng ứng dụng sẽ luôn đi theo đúng các màn hình hoặc xóa sạch mọi trạng thái cũ ở đúng thời điểm.

## 3. Phân loại trạng thái theo nguồn thẩm quyền

| Dữ liệu trên thiết bị | Có thể dùng để làm gì? | Điều máy chủ phải tự xác minh |
| --- | --- | --- |
| Sản phẩm, nội dung nháp hoặc ghi chú người dùng | Thể hiện ý định và dữ liệu được phép đề xuất | Schema, quyền trường và invariant |
| ID đề nghị hoặc tenant được chọn | Tham chiếu và lựa chọn phạm vi | Membership, quyền đối tượng và quan hệ |
| Role, permission, hạn mức đã cache | Hỗ trợ giao diện và giải thích khả năng dự kiến | Quyền hiện hành tại ranh giới quyết định |
| Số tiền hoặc giá đã hiển thị | Cho biết bản người dùng đã xem | Snapshot, nguồn tính và điều kiện áp dụng |
| Cờ `approved`, `paid`, `verified` | Có thể phản ánh giao diện cục bộ | Bằng chứng nghiệp vụ từ nguồn có thẩm quyền |
| Timestamp client | Metadata phục vụ trải nghiệm hoặc điều tra | Thời gian máy chủ và hiệu lực thực tế |
| Command ID | Nhận diện một ý định khi retry | Phạm vi key, dấu vân tay và chống thực hiện trùng |
| Token hoặc bằng chứng được phát hành | Mang credential hoặc tham chiếu có thể xác minh | Nguồn, mục đích, đối tượng nhận, thời hạn và policy liên quan |

Dữ liệu từng do máy chủ trả về có nguồn gốc hợp lệ ở thời điểm phát hành. Điều đó không làm mọi bản sao được gửi lại tự nhiên còn hiệu lực mãi hoặc vẫn thuộc đúng ngữ cảnh sử dụng.

## 4. Lưu trữ an toàn không thay thế kiểm tra nghiệp vụ

Mã hóa cơ sở dữ liệu cục bộ, bảo vệ token và dùng kho khóa của nền tảng có thể giảm rủi ro khi thiết bị hoặc dữ liệu bị truy cập ngoài ý muốn. Chúng không biến mọi giá trị mà client gửi thành sự thật nghiệp vụ.

Ví dụ một client có thể gửi request mới chứa `approved=true` mà không cần sửa đúng file dữ liệu nơi ứng dụng chính thức lưu cờ đó. Máy chủ không nên phụ thuộc vào việc caller có sửa được một lớp lưu trữ cụ thể hay không.

Tương tự:

- Kết nối mã hóa bảo vệ dữ liệu trên đường truyền, không chứng minh người gửi được phép đặt đơn giá hoặc vai trò.
- Ứng dụng được phân phối chính thức không có nghĩa mọi request sẽ theo đúng luồng giao diện.
- Kiểm tra môi trường hoặc attestation cung cấp tín hiệu theo cơ chế của nền tảng, không tự cấp quyền trên từng đối tượng.
- Một thiết bị không bị phát hiện bất thường vẫn có thể dùng dữ liệu cũ hoặc gửi lặp.

Các lớp bảo vệ thiết bị có giá trị, nhưng cần đặt đúng mục đích. Chúng bổ sung cho quyết định máy chủ và có thể phục vụ đánh giá rủi ro; không thay thế trạng thái, quyền và bằng chứng nghiệp vụ.

## 5. Ví dụ chính sách duyệt chi trên mobile

Giả sử ứng dụng cho phép:

- Nhân viên soạn nháp và xem dữ liệu đã cache khi mất mạng.
- Người có quyền có thể ghi lại ý định duyệt để gửi sau.
- Chỉ máy chủ mới chấp nhận một quyết định duyệt có hiệu lực.
- Quyền và hạn mức được đánh giá tại lúc máy chủ nhận quyết định theo ranh giới nhất quán của hệ thống.
- Không được duyệt đề nghị do chính cá nhân đó tạo.
- Quyết định phải gắn với đúng snapshot nội dung mà người dùng định duyệt.
- Retry và nhiều thiết bị không được tạo phiếu hoặc tác dụng phụ trùng.

Trong chính sách này, nút duyệt khi offline chỉ tạo một lệnh chờ. Nó không làm đề nghị trở thành đã được duyệt tại nguồn có thẩm quyền.

```text
Trên thiết bị: lệnh chờ gửi hoặc chờ xác nhận
Trên máy chủ: chưa có quyết định duyệt cho tới khi commit hợp lệ
```

Giao diện cần thể hiện được sự khác nhau đó. Nếu hiện “Đã duyệt” ngay khi chỉ ghi vào bộ nhớ cục bộ, người dùng có thể hiểu sai một hành động mà máy chủ sau đó từ chối.

## 6. Hàng đợi offline lưu ý định, không lưu quyền tự khai

Một mục hàng đợi có thể tham chiếu:

```json
{
  "clientCommandId": "command-8",
  "action": "APPROVE_EXPENSE",
  "expenseId": "expense-42",
  "expectedVersion": 7,
  "expectedSnapshotId": "snapshot-3",
  "clientCreatedAt": "2026-11-22T03:00:00Z"
}
```

Ứng dụng còn cần lưu ngữ cảnh tài khoản và tenant mà người dùng đang dùng khi tạo lệnh để tránh gửi nhầm sau đổi phiên. Đây là dữ liệu hỗ trợ điều phối cục bộ; máy chủ vẫn xác minh actor thực tế và phạm vi của request.

Không dùng mục hàng đợi có dạng:

```text
status = APPROVED
approvedBy = manager-7
approvalLimit = 100 triệu
skipServerValidation = true
```

Những trường này tự khai kết luận hoặc điều kiện cho phép thay vì diễn đạt ý định cần kiểm tra.

Một API đồng bộ nhận nhiều lệnh phải chỉ hỗ trợ các loại hành động xác định trước. Không cho client gửi một graph entity tùy ý rồi dùng một hàm merge chung để biến toàn bộ trạng thái cục bộ thành dữ liệu máy chủ.

## 7. Thiết kế request với danh tính và scope được xác minh

Ví dụ khi có mạng trở lại:

```http
POST /expense-requests/expense-42/approve
Authorization: Bearer <access-token>
X-Tenant-ID: tenant-a
Idempotency-Key: command-8
Content-Type: application/json

{
  "expectedVersion": 7,
  "expectedSnapshotId": "snapshot-3",
  "clientCreatedAt": "2026-11-22T03:00:00Z"
}
```

Máy chủ:

1. Xác minh credential và danh tính actor thực tế.
2. Xác minh actor được dùng tenant được chọn theo hợp đồng API.
3. Tải đề nghị trong phạm vi đó và kiểm tra quyền trên đối tượng.
4. Lấy số tiền, bộ phận, người tạo và snapshot từ dữ liệu có thẩm quyền.
5. Kiểm tra trạng thái, version, quyền reviewer, hạn mức và phân tách trách nhiệm.
6. Ghi quyết định bằng thời gian máy chủ cùng kết quả idempotency khi hợp lệ.

`clientCreatedAt` không chứng minh quyền còn hiệu lực. Nếu người dùng tạo lệnh offline trước khi bị thu hồi quyền nhưng gửi sau đó, chính sách ví dụ vẫn đánh giá quyền tại ranh giới máy chủ nhận quyết định.

Nếu token hết hạn, cơ chế xác thực có thể yêu cầu làm mới hoặc đăng nhập lại. Việc có credential mới không tự cho phép áp dụng một ý định cũ vào snapshot mới mà người dùng chưa xem.

## 8. Minh họa Java: ra quyết định từ dữ liệu máy chủ

Ví dụ dùng record của Java 16 trở lên và chỉ mô hình hóa duyệt chi bằng VND. Các record session, authority và expense được dựng từ nguồn tin cậy. Command ID và expense ID có thể được đưa vào mô hình lệnh từ header và route đã phân tích theo hợp đồng.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

enum ExpenseState {
    DRAFT, PENDING_APPROVAL, APPROVED, REJECTED
}

record VerifiedSession(
        UUID tenantId,
        UUID principalId,
        UUID personId,
        boolean active) {
}

record MobileApprovalCommand(
        UUID clientCommandId,
        UUID expenseId,
        long expectedVersion,
        UUID expectedSnapshotId,
        Instant clientCreatedAt) {
}

record ExpenseSnapshot(
        UUID id,
        UUID tenantId,
        UUID departmentId,
        UUID createdByPersonId,
        UUID contentSnapshotId,
        long amountVnd,
        ExpenseState state,
        long version) {
}

record ApprovalAuthority(
        UUID tenantId,
        UUID departmentId,
        UUID reviewerPersonId,
        long limitVnd,
        Instant validUntil,
        boolean active) {
}

record ServerApprovalDecision(
        UUID commandId,
        UUID tenantId,
        UUID expenseId,
        UUID snapshotId,
        UUID actorPrincipalId,
        UUID reviewerPersonId,
        Instant decidedAt) {
}

final class MobileApprovalPolicy {
    private MobileApprovalPolicy() {
    }

    static ServerApprovalDecision decide(
            VerifiedSession session,
            MobileApprovalCommand command,
            ExpenseSnapshot current,
            ApprovalAuthority authority,
            Instant serverNow) {
        Objects.requireNonNull(session);
        Objects.requireNonNull(command);
        Objects.requireNonNull(current);
        Objects.requireNonNull(authority);
        Objects.requireNonNull(serverNow);

        UUID tenant = Objects.requireNonNull(session.tenantId());
        UUID person = Objects.requireNonNull(session.personId());
        UUID principal = Objects.requireNonNull(session.principalId());
        UUID snapshot = Objects.requireNonNull(current.contentSnapshotId());

        require(session.active() && authority.active(), "INACTIVE_AUTHORITY");
        require(tenant.equals(current.tenantId())
                && tenant.equals(authority.tenantId()), "TENANT_MISMATCH");
        require(Objects.requireNonNull(current.id())
                .equals(command.expenseId()), "EXPENSE_MISMATCH");
        require(person.equals(authority.reviewerPersonId()),
                "REVIEWER_MISMATCH");
        require(Objects.requireNonNull(authority.departmentId())
                .equals(current.departmentId()), "OUT_OF_SCOPE");
        require(!person.equals(current.createdByPersonId()),
                "SELF_APPROVAL_FORBIDDEN");
        require(current.state() == ExpenseState.PENDING_APPROVAL,
                "WRONG_STATE");
        require(current.version() == command.expectedVersion()
                && snapshot.equals(command.expectedSnapshotId()),
                "CONTENT_CONFLICT");
        require(serverNow.isBefore(authority.validUntil()),
                "AUTHORITY_EXPIRED");
        require(current.amountVnd() > 0
                && current.amountVnd() <= authority.limitVnd(),
                "AMOUNT_NOT_ALLOWED");

        return new ServerApprovalDecision(
                Objects.requireNonNull(command.clientCommandId()), tenant,
                current.id(), snapshot, principal, person, serverNow);
    }

    private static void require(boolean valid, String code) {
        if (!valid) {
            throw new SecurityException(code);
        }
    }
}
```

Quyết định không dùng role, hạn mức, số tiền hoặc cờ sinh trắc học từ thiết bị. Thời điểm quyết định dùng `serverNow`, không dùng timestamp do client khai.

Đoạn mã chỉ tạo kết quả chính sách trong bộ nhớ. Service vẫn phải kiểm tra dữ liệu bắt buộc, quản lý quyền hiện hành, quota tích lũy nếu có và bảo vệ việc kiểm tra tới commit. Một `ApprovalAuthority` tải từ cache lỗi thời không tự trở thành bằng chứng quyền hiện tại chỉ vì có kiểu như trên.

## 9. Đồng bộ và commit trong ranh giới nhất quán

Một luồng server có thể là:

```text
BEGIN TRANSACTION
  nhận quyền xử lý key theo tenant + actor thực tế + loại thao tác
  nếu cùng lệnh đã commit:
    kiểm tra quyền xem kết quả và trả kết quả cũ

  tải và bảo vệ đề nghị, vòng duyệt và snapshot
  đọc quyền cùng các dữ liệu có thẩm quyền cần thiết
  kiểm tra hành động, phạm vi, người tham gia và nội dung
  kiểm tra version, trạng thái và thời gian máy chủ
  bảo vệ quota hoặc tài nguyên dùng chung nếu hành động cần
  ghi quyết định, trạng thái mới và version bằng cơ chế có điều kiện
  ghi audit, outbox và kết quả idempotency
COMMIT
```

Nếu quyền có thể bị thu hồi đồng thời, cần ranh giới kiểm tra và nhận quyết định phù hợp với cam kết hiệu lực. Một lần kiểm tra trước transaction không tự bảo vệ mọi thay đổi tiếp theo.

Hai thiết bị cùng thấy đề nghị đang chờ không được cùng tạo các quyết định loại trừ nhau hoặc tạo thêm hiệu ứng. Version, ràng buộc nhiệm vụ và dữ liệu operation phải giữ invariant độc lập với số thiết bị.

Không giữ transaction mở trong lúc thiết bị mất mạng hoặc người dùng suy nghĩ. Trạng thái chờ được lưu bền vững; mỗi lần máy chủ chấp nhận một hành động là một transaction ngắn theo thiết kế.

## 10. Xung đột nội dung không được giải quyết bằng cách nâng version tự động

Giả sử điện thoại đã hiển thị đề nghị 1 triệu VND ở snapshot S3. Trong lúc offline, đề nghị được sửa thành 10 triệu VND ở S4.

Lệnh duyệt S3 không được tự chuyển thành duyệt S4 bằng quy trình:

```text
server báo version cũ
app tải version mới
app thay expectedVersion và expectedSnapshotId
app gửi lại APPROVE mà không có quyết định mới của người dùng
```

Việc sửa các điều kiện phiên bản đã làm thay đổi ý nghĩa đồng ý ban đầu. Người duyệt có thể cần xem nội dung mới trước khi đưa ra một ý định mới.

Quy tắc đồng bộ cần theo từng loại dữ liệu:

| Dữ liệu | Cách xử lý có thể phù hợp theo chính sách |
| --- | --- |
| Bản nháp chưa có hiệu ứng | Hợp nhất có kiểm soát hoặc yêu cầu người dùng chọn |
| Ghi chú độc lập | Có thể thêm một ghi chú mới nếu quyền còn đủ |
| Số tiền, người nhận hoặc nội dung đã duyệt | Tạo revision và đánh giá lại bằng chứng liên quan |
| Trạng thái, owner hoặc quyền | Thực hiện qua lệnh có guard, không dùng last-write-wins chung |
| Kết quả đã commit | Đồng bộ lại kết quả, không tạo hành động mới |

Timestamp hoặc cấu trúc phát hiện xung đột có thể giúp biết có cập nhật đồng thời. Chúng không tự quyết định cập nhật nào được phép theo nghiệp vụ.

## 11. Đổi tài khoản, đổi tenant và thiết bị dùng chung

Một lỗi phổ biến là hàng đợi offline không gắn với ngữ cảnh lúc tạo. Người A đăng xuất, người B đăng nhập, rồi ứng dụng gửi mọi lệnh còn chờ bằng token của B.

Ứng dụng cần quản lý dữ liệu và hàng đợi theo tài khoản cùng tenant phù hợp, đồng thời có quy tắc rõ khi logout, xóa tài khoản hoặc chuyển scope. Không tự chuyển ý định của A thành hành động của B.

Máy chủ vẫn phải kiểm tra actor thực tế trên mọi lệnh. Một trường `originalActorId` do client gửi có thể hữu ích để phát hiện mismatch theo hợp đồng, nhưng không cấp quyền hành động như actor đó.

Với user thuộc nhiều tenant, mỗi request có một scope được xác minh. Việc có membership ở cả A và B không cho phép trộn ID đề nghị A với quyền duyệt hoặc dữ liệu cache của B.

`deviceId` hoặc `installationId` có thể phục vụ định tuyến, hỗ trợ hoặc đánh giá rủi ro, nhưng không tự là căn cứ danh tính hay quyền. Cài lại ứng dụng hoặc dùng thiết bị mới không được đặt lại quota toàn cục của cùng cá nhân nếu quota được định nghĩa ở cấp đó.

## 12. Thời gian trên thiết bị và bằng chứng xác thực cục bộ

Không dùng đồng hồ điện thoại để quyết định rằng grant chưa hết hạn, mã giảm giá còn hiệu lực hoặc một approval được tạo trước khi thu hồi.

Có thể lưu timestamp client để hiển thị hoặc điều tra, nhưng phải phân biệt với:

```text
thời điểm máy chủ nhận request
thời điểm quyền được kiểm tra và quyết định được nhận
thời điểm transaction commit
thời điểm hiệu ứng bên ngoài được xác nhận
```

Một cờ `biometricPassed=true` cũng không chứng minh máy chủ đã nhận một bằng chứng xác thực mạnh theo chính sách. Nếu hành động yêu cầu mức bảo đảm bổ sung, máy chủ cần xác minh bằng chứng theo cơ chế đăng ký, challenge và hiệu lực mà nền tảng hỗ trợ.

Ngay cả một chữ ký từ khóa thiết bị cũng cần được hiểu đúng: nó có thể bảo vệ nguồn hoặc tính toàn vẹn của dữ liệu theo cơ chế đó, nhưng không chứng minh đơn giá, vai trò hoặc kết quả nghiệp vụ trong payload là đúng. Cần ràng buộc mục đích, actor, đối tượng, nội dung, thời hạn và chống replay theo thiết kế.

Không đặt bí mật có khả năng phát hành quyền toàn hệ thống trong ứng dụng rồi coi nó là bí mật không thể bị tiếp cận. Khả năng client giữ credential được giới hạn phải được tách khỏi thẩm quyền máy chủ xác lập quyền cho mọi người.

## 13. Notification, deep link và kết quả từ SDK không phải quyết định cuối

Ứng dụng có thể được mở qua một link chứa:

```text
expenseId=expense-42&status=APPROVED&role=manager
```

Link chỉ nên dẫn tới hành động hoặc màn hình phù hợp sau khi tải và kiểm tra dữ liệu. Nó không cấp role hoặc xác lập trạng thái. Notification có nguồn hợp lệ cũng có thể đến muộn và phản ánh snapshot đã cũ.

Nút hành động trực tiếp trên notification phải gọi cùng cơ chế backend với màn hình thông thường. Không tạo một endpoint yếu hơn vì giao diện cho rằng sự kiện bấm nút chỉ có thể đến từ ứng dụng chính thức.

Các ví dụ tương tự:

- Cờ mua hàng thành công trong bộ nhớ thiết bị không tự cấp entitlement lâu dài ở máy chủ.
- Màn hình thanh toán hoàn tất hoặc callback trong app không tự chứng minh tiền đã được xử lý.
- Trạng thái một SDK báo về cần được hiểu trong giao thức và đối chiếu nguồn có thẩm quyền trước khi tạo hậu quả nghiệp vụ.

Nếu nhận bằng chứng giao dịch, máy chủ cần kiểm tra nguồn, đối tượng, giao dịch, tài khoản liên kết và chống xử lý lặp theo mô hình tương ứng. Không chỉ nhận `isPremium=true`, `paid=true` hoặc một ảnh chụp màn hình kết quả.

## 14. Offline thật sự cần mô hình cấp quyền riêng

Ví dụ của bài chỉ lưu ý định offline. Nếu sản phẩm thực sự phải cho phép tạo một hậu quả được công nhận khi không kết nối máy chủ, cần một thiết kế riêng thay vì coi cache role là giấy phép.

Các vấn đề phải xác định gồm:

- Hành động nào được phép offline và mức hậu quả có thể chấp nhận.
- Phạm vi, thời hạn và hạn mức đã được cấp trước.
- Cách ràng buộc bằng chứng với thiết bị, chủ thể, đối tượng hoặc một lần sử dụng theo mô hình.
- Cách xử lý bản sao, khôi phục dữ liệu cũ và nhiều thiết bị.
- Khi nào quyết định được coi là có hiệu lực và cách đối soát khi kết nối lại.
- Thu hồi có thể tác động đến phần quyền đã phát hành offline bằng cơ chế nào và với độ trễ nào.

Không thể chỉ dùng một bộ đếm cục bộ để bảo đảm hạn mức toàn cục khi nhiều bản sao độc lập có thể cùng sử dụng mà không chia sẻ trạng thái nhất quán. Có thể cần dành phần quyền hoặc tài nguyên từ trước, giới hạn hậu quả, bằng chứng sử dụng và đối soát phù hợp.

Nếu điểm thực thi không thể biết một grant vừa bị thu hồi ở máy chủ, không nên hứa thu hồi tức thời cho mọi hành động offline. Hợp đồng sản phẩm cần phản ánh đúng giới hạn đó.

Không tự xây một cơ chế chữ ký tùy ý rồi xem vấn đề đã được giải quyết. Tính toàn vẹn, phân bổ quyền, replay, thu hồi và invariant giữa nhiều thiết bị là các phần khác nhau của thiết kế.

## 15. Idempotency và phục hồi sau mất phản hồi

Mobile thường gặp tình huống server đã commit nhưng thiết bị không nhận được phản hồi. Ứng dụng cần tiếp tục cùng ý định thay vì tạo lệnh mới ở mỗi lần gửi.

Một phạm vi có thể là:

```text
(tenantId, actualActorPrincipalId, operationType, clientCommandId)
```

Dấu vân tay còn bao gồm đối tượng, snapshot, version và dữ liệu có ý nghĩa của lệnh. Command ID khó đoán không phải token cấp quyền; server vẫn phải xác minh request và quyền xem kết quả.

| Tình huống | Hành vi cần giữ |
| --- | --- |
| Cùng command, cùng nội dung đã commit | Trả kết quả cũ theo quyền hiện tại, không tạo phiếu hoặc hiệu ứng mới |
| Cùng command ID nhưng đổi snapshot hoặc hành động | Từ chối tái sử dụng cho ý định khác |
| Command ID mới trên nhiệm vụ đã được quyết định | State machine và ràng buộc nghiệp vụ tiếp tục chặn thực hiện trùng |
| Khôi phục bản sao có lệnh đã gửi | Đồng bộ kết quả, không coi là một yêu cầu mới hợp lệ mặc nhiên |
| Cài lại app hoặc dùng thiết bị khác | Không đặt lại hạn mức hoặc số lần thực hiện được phép |
| Token hết hạn sau lần thành công | Xác thực lại và kiểm tra quyền đọc; không cần thực hiện lại quyết định cũ |

Không xem retry là một cơ hội tự cập nhật nội dung lệnh cho khớp dữ liệu mới. Khi người dùng thực sự đưa ra ý định mới, cần nhận diện và kiểm tra ý định mới đó rõ ràng.

Nếu bước tiếp theo gọi hệ thống ngoài, dùng operation ổn định và xử lý kết quả chưa rõ bằng đối soát. Đổi mạng, đóng app hoặc timeout không chứng minh phía ngoài chưa thực hiện.

## 16. Ma trận kiểm thử trạng thái mobile không đáng tin

Tạo dữ liệu và credential thử nghiệm có ca đối chứng hợp lệ. Không chỉ kiểm thử giao diện; cần gửi trực tiếp các lệnh theo hợp đồng API trong môi trường được phép.

| Ca kiểm thử | Kết quả cần giữ |
| --- | --- |
| Sửa role hoặc hạn mức trong trạng thái cục bộ | Không làm thay đổi quyền server |
| Gửi `approved=true`, `paid=true` hoặc cờ xác minh | Không tự tạo bằng chứng hoặc kết quả |
| Sửa actor hoặc tenant trong payload | Không ghi đè danh tính và scope đã xác minh |
| Người có quyền tạo đề nghị tự duyệt bằng dữ liệu cache | Vẫn bị chặn theo người tham gia thực tế |
| Lệnh offline dùng snapshot cũ sau khi số tiền đổi | Không được tự áp dụng lên nội dung mới |
| Lệnh được tạo trước nhưng gửi sau thu hồi quyền | Kết quả theo ranh giới hiệu lực đã chọn, không tin timestamp client |
| Chỉnh đồng hồ thiết bị ra trước hoặc sau | Không kéo dài quyền, quote hoặc thời hạn nghiệp vụ |
| Link hoặc notification tự khai role và trạng thái | Chỉ điều hướng hoặc tạo ý định được kiểm tra, không cấp quyền |
| Cờ sinh trắc học cục bộ bị gửi như bằng chứng | Không thay thế cơ chế xác minh server yêu cầu |
| Dữ liệu có chữ ký hợp lệ nhưng sai đối tượng hoặc mục đích | Không được dùng ngoài phạm vi đã cấp |
| Thiết bị vượt kiểm tra môi trường nhưng request sai quyền | Vẫn bị chặn bởi policy nghiệp vụ |
| Caller không có đầy đủ dữ liệu để xác lập quyền | Không mặc định cho phép vì đang ở chế độ mobile hoặc offline |

Các ca đổi tài khoản cần xác minh cả phía ứng dụng lẫn server: hàng đợi A không tự được gửi như B, và server không cho trường actor tự khai biến request B thành A.

## 17. Kiểm thử đồng bộ, nhiều thiết bị và quan sát hiệu ứng

| Kịch bản | Invariant hoặc hành vi cần giữ |
| --- | --- |
| Hai thiết bị cùng duyệt một nhiệm vụ | Không tạo hai quyết định loại trừ hoặc hiệu ứng trùng |
| Đóng app sau gửi nhưng trước nhận phản hồi | Có thể truy vấn hoặc retry cùng command an toàn |
| Khôi phục bản sao hàng đợi cũ | Không tạo lại operation đã được chấp nhận |
| Đổi tenant trước khi mạng trở lại | Không gửi hoặc áp dụng sai scope |
| Worker xử lý ý định sau khi quyền thay đổi | Kiểm tra đúng ranh giới tạo quyết định, không chỉ lúc enqueue |
| Lỗi sau khi nhận quota nhưng trước ghi quyết định | Không để trừ quota riêng ngoài transaction hoặc giao thức đã chọn |
| Server đã commit nhưng push kết quả đến muộn | App không tự ghi đè kết quả mới bằng trạng thái cache cũ |
| Cùng người tạo nhiều command ID trên nhiều thiết bị | Quota và invariant nghiệp vụ không bị nhân lên |
| Kết quả ngoài thành công nhưng app báo timeout | Đối soát đúng operation, không tạo lại hiệu ứng |

Quan sát dữ liệu bền vững gồm snapshot, quyết định, version, quota, operation, outbox và lời gọi biên ngoài. Một response lỗi không đủ nếu tác dụng phụ đã được tạo trước đó.

Kiểm thử tranh chấp cần lịch thực thi có kiểm soát và cơ chế lưu trữ phù hợp. Các test chỉ sửa một biến trong bộ nhớ app không chứng minh server an toàn nếu chưa kiểm tra đường request và commit thực tế.

Audit nên giữ actor thực tế, tenant, command ID, đối tượng, snapshot, thời gian máy chủ và kết quả đã commit hoặc bị từ chối. Timestamp client có thể được lưu như metadata được khai, với nhãn rõ ràng.

Không ghi access token, bí mật thiết bị hoặc toàn bộ dữ liệu riêng tư vào log đồng bộ. Các dấu hiệu như nhiều lệnh sai snapshot, dùng tenant cũ hoặc lặp command giúp điều tra lỗi tích hợp và lạm dụng, nhưng không thay thế guard trên đường xử lý.

## 18. Cách áp dụng nguyên tắc vào một tính năng mobile

1. Liệt kê dữ liệu cục bộ và xác định dữ liệu nào chỉ phục vụ hiển thị, dữ liệu nào là ý định, dữ liệu nào phải do server xác lập.
2. Chọn rõ hành động offline chỉ được xếp chờ hay thực sự được công nhận theo một mô hình cấp quyền riêng.
3. Thiết kế lệnh hẹp có đối tượng, snapshot, version và command ID, không gửi toàn bộ entity để merge.
4. Xác minh actor, tenant, quyền đối tượng, trạng thái và hạn mức bằng dữ liệu có thẩm quyền.
5. Gắn quyết định với đúng nội dung người dùng định xử lý; không tự nâng version để duyệt một bản mới.
6. Giữ hàng đợi và cache theo tài khoản cùng scope, có quy tắc khi logout, đổi tenant và khôi phục dữ liệu.
7. Bảo vệ commit, quota và tác dụng phụ bằng transaction, version, operation ổn định và idempotency.
8. Dùng bảo vệ lưu trữ, xác thực thiết bị và tín hiệu môi trường như các lớp bổ sung đúng mục đích.
9. Kiểm thử trạng thái bị sửa, dữ liệu cũ, nhiều thiết bị, mất phản hồi và thay đổi quyền trong lúc offline.

Trạng thái trên thiết bị giúp ứng dụng hoạt động và thể hiện ý định, nhưng không tự cấp thẩm quyền cho kết quả nghiệp vụ. Máy chủ cần chứng minh quyền, nội dung và điều kiện còn đúng tại ranh giới chấp nhận, rồi trả kết quả bền vững để thiết bị đồng bộ lại.
