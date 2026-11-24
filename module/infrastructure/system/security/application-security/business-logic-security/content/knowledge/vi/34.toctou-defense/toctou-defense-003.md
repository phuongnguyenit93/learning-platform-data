# Authorization recheck

## Mục tiêu bài học

Authorization recheck là việc kiểm tra lại quyền của một chủ thể đối với một hành động và đối tượng cụ thể tại thời điểm thao tác chuẩn bị tạo hiệu ứng. Kết quả kiểm tra trước đó, chẳng hạn khi mở màn hình, upload dữ liệu hoặc đưa công việc vào hàng đợi, không tự chứng minh quyền vẫn còn hiệu lực khi công việc được thực thi.

Trong phòng vệ TOCTOU, tên gọi này gắn với khoảng trống giữa thời điểm kiểm tra và thời điểm sử dụng quyết định quyền. Một người có thể mất vai trò, bị thu hồi ủy quyền, rời tenant hoặc không còn quyền sửa sau khi đối tượng đã chuyển trạng thái. Nếu hệ thống dùng lại kết quả cho phép cũ, thao tác vẫn có thể vượt qua quy tắc nghiệp vụ.

Kiểm tra lại sát lúc ghi giúp giảm rủi ro nhưng chưa tự tạo ra bảo đảm nguyên tử. Muốn phối hợp với thu hồi quyền đồng thời, cần xác định rõ thời điểm quyền có hiệu lực và cơ chế bảo vệ các dữ liệu làm căn cứ quyết định.

Sau bài học, bạn có thể:

- Xác định các quyền và điều kiện cần kiểm tra lại cho một lệnh nghiệp vụ.
- Phân biệt xác thực, quyết định quyền và điều kiện chuyển trạng thái.
- Thiết kế ranh giới kiểm tra, cập nhật và thu hồi quyền có ngữ nghĩa rõ ràng.
- Xử lý tác vụ nền, cache và token mà không dùng nhầm quyền của service account.
- Kiểm thử các lịch thu hồi quyền, hết hạn ủy quyền và thay đổi đối tượng.

## 1. Quyền có thể thay đổi giữa hai bước hợp lệ

Giả sử người duyệt mở một hồ sơ hoàn ứng ở trạng thái `SUBMITTED`. Khi tải màn hình, máy chủ xác nhận họ có quyền duyệt. Trước khi họ bấm xác nhận, quản trị viên thu hồi quyền được ủy quyền.

Một luồng có khoảng trống:

```text
T1: mở màn hình -> kiểm tra quyền -> cho phép hiển thị nút duyệt
T2: quyền duyệt bị thu hồi và thay đổi được commit
T3: người dùng gửi lệnh duyệt
T4: server tin kết quả ở T1 -> ghi APPROVED
```

Ẩn nút sau T2 có thể cải thiện trải nghiệm nhưng không bảo vệ server. Trình duyệt có thể giữ trang cũ, request có thể đã được chuẩn bị hoặc một client khác có thể gọi trực tiếp endpoint.

Luồng cần thiết là server xác định lại quyền của chủ thể trên chính hồ sơ khi xử lý lệnh ở T3. Nếu quyền đã được thu hồi theo chính sách có hiệu lực, không được tạo quyết định duyệt.

Một trường hợp khó hơn xảy ra khi thu hồi chen giữa lần kiểm tra lại và lần ghi:

```text
T1: lệnh duyệt kiểm tra lại, thấy quyền còn hiệu lực
T2: thu hồi quyền commit
T3: lệnh duyệt ghi dữ liệu dựa trên kết quả ở T1
```

Gọi hàm `canApprove()` thêm một lần không tự loại bỏ lịch này. Cần thiết kế cả cách quyết định quyền được phối hợp với thao tác tạo hiệu ứng.

## 2. Xác thực không thay thế quyền theo đối tượng

Các câu hỏi phải được tách rõ:

| Câu hỏi | Dữ liệu liên quan |
|---|---|
| Chủ thể là ai? | Phiên, token hoặc cơ chế xác thực đã được kiểm chứng |
| Chủ thể thuộc phạm vi nào? | Tenant, trạng thái thành viên, phạm vi được ủy quyền |
| Có được thực hiện hành động này không? | Vai trò, grant, chính sách hành động |
| Có được làm trên đối tượng này không? | Chủ sở hữu, ACL, đơn vị, quan hệ với đối tượng |
| Có được thay các thuộc tính này không? | Quyền mức trường hoặc phạm vi thay đổi |
| Trạng thái hiện tại có cho phép không? | State machine và bất biến nghiệp vụ |
| Quyết định có còn áp dụng cho dữ liệu này không? | Version, snapshot và các phụ thuộc liên quan |

Token hợp lệ chứng minh một phần ngữ cảnh xác thực theo cơ chế đã chọn. Nó không tự chứng minh mọi quyền ghi trong token vẫn là trạng thái quyền hiện hành.

Tương tự, biết đúng `reportId` hoặc gửi đúng `expectedVersion` không tạo ra quyền duyệt. Version giúp phát hiện dữ liệu đã thay đổi; authorization recheck xác minh chủ thể có được thực hiện hành động trên dữ liệu đó hay không.

Tenant và danh tính chủ thể phải lấy từ ngữ cảnh xác thực tin cậy. Không dùng `tenantId`, `approvedBy` hay `isAdmin` do request tùy ý gửi để thay thế quyết định của máy chủ.

## 3. Định nghĩa đầy đủ đối tượng của lần kiểm tra lại

Một kết quả quyền chỉ có ý nghĩa khi gắn với đủ ngữ cảnh:

```text
subject: chủ thể đang yêu cầu
actingContext: tenant và quan hệ ủy quyền
resource: đúng đối tượng cùng quan hệ cha/con
operation: hành động cụ thể
requestedChanges: phạm vi trường hoặc tác động
resourceSnapshot: trạng thái và version liên quan
authorizationSnapshot: nguồn quyền và revision nếu có
decisionTime: thời điểm quyết định theo chính sách
```

Ví dụ, quyền tải hóa đơn lên một hồ sơ không phải quyền thay bằng chứng đã duyệt. Quyền sửa hồ sơ của mình không phải quyền sửa hồ sơ cùng phòng ban. Quyền xem tài liệu không phải quyền cấp lại tài liệu cho người khác.

Nếu lệnh sửa một dòng đơn hàng, cần xác minh dòng thuộc đúng đơn hàng và đơn hàng thuộc tenant được phép. Không kiểm tra quyền trên `orderId` rồi ghi một `lineId` không được ràng buộc với đơn hàng đó.

Với lệnh nhiều đối tượng, cần kiểm tra toàn bộ tập đối tượng tạo hiệu ứng. Một quyền hợp lệ trên đối tượng đầu tiên không tự bao phủ các đối tượng còn lại trong batch hoặc import.

## 4. Chọn ngữ nghĩa thu hồi quyền trước khi chọn kỹ thuật

Không phải mọi sản phẩm đều yêu cầu cùng thời điểm cắt hiệu lực. Cần công bố rõ mô hình:

| Mô hình | Ý nghĩa |
|---|---|
| Quyền tại thời điểm tiếp nhận | Lệnh được chấp nhận khi quyền còn hiệu lực có thể tiếp tục theo quy trình đã cam kết |
| Quyền tại thời điểm thực thi | Tác vụ chờ phải kiểm tra lại trước khi tạo hiệu ứng; thu hồi trước đó làm lệnh không còn được phép |
| Thu hồi có độ trễ được giới hạn | Cache hoặc quyết định được dùng trong một khoảng thời gian đã được chấp nhận rõ ràng |
| Thu hồi phối hợp với thao tác ghi | Việc chấp nhận lệnh và thu hồi được tuần tự hóa trên nguồn quyết định chung |

Trong ví dụ của bài học, lệnh duyệt được kiểm tra tại thời điểm thực thi. Việc chấp nhận lệnh và thu hồi grant được phối hợp để có một thứ tự rõ ràng:

- Thu hồi hoàn tất trước khi lệnh được chấp nhận theo giao thức thì lệnh không được dùng quyền cũ.
- Lệnh đã giành quyền xử lý trong ranh giới được bảo vệ có thể hoàn tất trước thao tác thu hồi đang chờ.
- Thời điểm người dùng bấm nút không tự quyết định bên nào thắng; thứ tự phải do giao thức nhất quán xác lập.

Không hứa rằng một thao tác thu hồi sẽ xóa tác động của các transaction đã commit. Hủy hiệu ứng đã có là một nghiệp vụ khác, cần điều kiện và audit riêng.

Nếu sự kiện sau commit được phát muộn, nó có thể xuất hiện sau khi quyền đã thu hồi dù lệnh nguồn được chấp nhận trước đó. Cần phân biệt việc thực hiện lại quyền của người dùng với việc hoàn tất một nghĩa vụ hệ thống đã được commit hợp lệ.

## 5. Tình huống xuyên suốt: duyệt hồ sơ bằng grant trực tiếp

Giả sử hệ thống sử dụng các dữ liệu sau:

| Thành phần | Dữ liệu liên quan |
|---|---|
| `tenant_subject` | Chủ thể trong tenant, trạng thái hoạt động, hạn hiệu lực |
| `expense_report` | Tenant, chủ hồ sơ, trạng thái, revision |
| `report_acl_guard` | Một hàng ổn định cho hồ sơ, chứa revision chính sách ACL |
| `report_grant` | Chủ thể, hồ sơ, hành động, trạng thái, khoảng hiệu lực |
| `approval_record` | Người duyệt, snapshot được duyệt, thời điểm quyết định |
| Audit và outbox | Dấu vết cùng hiệu ứng cần phát sau commit |

Chính sách minh họa:

- Người duyệt phải là thành viên còn hiệu lực trong tenant.
- Phải có grant trực tiếp cho hành động `APPROVE` trên hồ sơ.
- Người duyệt không được là chủ hồ sơ.
- Hồ sơ phải còn `SUBMITTED` và đúng version mà quyết định dựa vào.
- Grant phải còn hiệu lực tại thời điểm quyết định được bảo vệ theo giao thức.

Ví dụ này chưa bao phủ quyền kế thừa từ nhóm, cấu trúc tổ chức hoặc một hệ thống IAM bên ngoài. Nếu quyết định thực tế còn phụ thuộc các nguồn đó, giao thức phải bảo vệ hoặc xác định ngữ nghĩa cho chúng. Không thể dùng mô hình giản lược rồi tuyên bố đã thu hồi nguyên tử mọi loại quyền.

## 6. Giao thức khóa cho lần kiểm tra lại và cập nhật

### 6.1. Kiểm tra trong cùng transaction là cần thiết nhưng chưa đủ

Một transaction có thể đọc quyền cũ rồi ghi hồ sơ sau khi transaction khác đã thu hồi quyền, tùy isolation và các hàng thực sự bị tranh chấp. Chỉ đặt hai câu lệnh trong một khối transaction không làm chúng tự động xung đột.

Một giao thức minh họa dùng các hàng bảo vệ chung:

1. Khóa bản ghi thành viên của chủ thể trong tenant.
2. Khóa hồ sơ đích trong tenant.
3. Khóa hàng `report_acl_guard` của hồ sơ.
4. Đọc grant theo cơ chế đọc thích hợp dưới giao thức khóa.
5. Đánh giá quyền, thời hạn, phân tách người tạo/người duyệt và trạng thái hiện tại.
6. Cập nhật có điều kiện, ghi quyết định duyệt, audit và outbox.
7. Giữ các khóa liên quan tới hết transaction.

Các đường đổi trạng thái thành viên, đổi chủ hồ sơ, sửa grant và chuyển trạng thái hồ sơ phải tham gia quy ước tương ứng. Mọi thao tác cần nhiều khóa dùng thứ tự ổn định để hạn chế deadlock.

### 6.2. Phác thảo SQL

```sql
BEGIN;

SELECT active, valid_until
FROM tenant_subject
WHERE tenant_id = :authenticatedTenantId
  AND subject_id = :authenticatedSubjectId
FOR UPDATE;

SELECT id, owner_id, status, revision
FROM expense_report
WHERE tenant_id = :authenticatedTenantId
  AND id = :reportId
FOR UPDATE;

SELECT acl_revision
FROM report_acl_guard
WHERE tenant_id = :authenticatedTenantId
  AND report_id = :reportId
FOR UPDATE;

SELECT action, active, valid_from, valid_until
FROM report_grant
WHERE tenant_id = :authenticatedTenantId
  AND report_id = :reportId
  AND subject_id = :authenticatedSubjectId
  AND action = 'APPROVE'
FOR UPDATE;

-- Service đánh giá quyền và điều kiện trên dữ liệu đã được bảo vệ.
-- Nếu thiếu hoặc không hợp lệ: kết thúc không tạo quyết định duyệt.

UPDATE expense_report
SET status = 'APPROVED',
    revision = revision + 1
WHERE tenant_id = :authenticatedTenantId
  AND id = :reportId
  AND status = 'SUBMITTED'
  AND revision = :reviewedRevision;

-- Chỉ khi cập nhật đúng một hàng mới ghi approval_record, audit, outbox.

COMMIT;
```

Đây là phác thảo giao thức, không phải đoạn SQL tự xử lý mọi nhánh lỗi. Service phải kiểm tra bản ghi đọc được, update count, điều khiển rollback và không trả thành công trước khi commit được xác nhận.

Cần chọn isolation và loại đọc theo hệ quản trị thực tế để dữ liệu đánh giá phản ánh trạng thái đúng của giao thức. Nếu engine trả lỗi cạnh tranh thay vì cho đọc trạng thái mới, transaction phải rollback và xử lý theo chính sách. Không ghép khóa hiện tại với một snapshot quyền cũ đã cache trong ngữ cảnh ORM rồi giả định quyết định đã mới.

### 6.3. Vì sao cần hàng guard ổn định?

Nếu grant không tồn tại, khóa riêng bản ghi grant có thể không tạo được điểm phối hợp như mong muốn. Việc thêm, xóa hoặc thay một grant khác cũng có thể tác động quyết định dựa trên sự vắng mặt hoặc tập hợp quyền.

Một hàng guard được tạo cùng hồ sơ cho phép các đường thay đổi ACL phối hợp ngay cả khi grant cụ thể chưa tồn tại. Trong mô hình này, mọi sửa grant của hồ sơ phải lấy guard và tăng `acl_revision` trong transaction tương ứng.

Guard không tự bảo vệ nguồn quyền nằm ngoài mô hình, chẳng hạn việc xóa thành viên khỏi một nhóm bên ngoài. Cần đưa đúng phụ thuộc vào giao thức, thay vì đặt tên một hàng là guard rồi coi mọi quyền đều được bảo vệ.

### 6.4. Thao tác thu hồi phải dùng cùng quy ước

Khi thu hồi grant trực tiếp của một chủ thể trên hồ sơ, đường thu hồi phải phối hợp với các hàng mà đường duyệt dựa vào, theo thứ tự khóa đã định nghĩa. Sau đó nó vô hiệu hóa grant, tăng revision ACL, ghi audit và commit.

Một lịch hợp lệ có thể là:

```text
A khóa các hàng bảo vệ, kiểm tra grant và thực hiện duyệt.
R yêu cầu thu hồi nhưng phải chờ hàng bảo vệ.
A commit và giải phóng khóa.
R thu hồi grant, commit và trả thành công.
Lệnh duyệt mới không thể được chấp nhận bằng grant cũ.
```

Hoặc R hoàn tất trước, khi đó A đọc quyền đã bị thu hồi và không được duyệt. Đây là thứ tự có thể giải thích; không phải lời hứa mọi request đã bắt đầu đều bị hủy ngay khi có người bấm thu hồi.

Khóa theo chủ thể có thể làm nhiều thao tác của cùng người tranh chấp. Có thể chọn giao thức chi tiết hơn khi cần, nhưng phải giữ được bảo đảm và kiểm thử tương ứng.

## 7. Thời hạn quyền không bị khóa bởi database

Một grant có thể hết hạn mà không có transaction nào cập nhật nó. Khóa hàng grant không làm đồng hồ ngừng chạy.

Vì vậy, cần định nghĩa chính xác thời điểm kiểm tra thời hạn. Trong ví dụ:

```text
validFrom <= decisionTime < validUntil
```

`decisionTime` được máy chủ lấy trong ranh giới quyết định được bảo vệ. Nếu thời điểm này bằng `validUntil`, grant không còn hiệu lực.

Quyền hết hạn sau khi lệnh đã được chấp nhận theo giao thức không tự đảo ngược transaction đó trong mô hình đã chọn. Nếu sản phẩm yêu cầu một thời điểm cắt khác, chẳng hạn điều kiện tại một hành động bên ngoài sau đó, phải kiểm tra tại chính ranh giới đó hoặc dùng giao thức phù hợp.

Không nói “đúng tại commit” nếu chỉ kiểm tra đồng hồ trước đó. Một transaction dài có thể vượt qua thời hạn giữa lần kiểm tra và commit. Cũng cần hiểu hàm thời gian của hệ quản trị được lấy tại đầu transaction, đầu statement hay thời điểm gọi; không mặc định chúng luôn là cùng một giá trị.

Giữ transaction ngắn và tránh cuộc gọi mạng dài trong lúc giữ khóa. Đây là cách giảm chờ đợi, không thay thế định nghĩa thời điểm quyền có hiệu lực.

## 8. Ví dụ Java 17: đánh giá lại chính sách từ dữ liệu tin cậy

Đoạn mã sau minh họa phần quyết định quyền. Các snapshot phải được service tải trong giao thức nhất quán đã chọn, từ nguồn tin cậy và có các trường bắt buộc không null. Hàm này không tự tạo ra khóa, truy vấn quyền hay bảo đảm chống TOCTOU.

```java
import java.time.Instant;
import java.util.UUID;

public final class ApprovalAuthorization {
    public enum Action {
        READ, EDIT, APPROVE
    }

    public enum ReportState {
        DRAFT, SUBMITTED, APPROVED, CANCELLED
    }

    public record Actor(UUID tenantId, UUID subjectId) {}

    public record Membership(
            UUID tenantId,
            UUID subjectId,
            boolean active,
            Instant validUntil) {}

    public record ReportSnapshot(
            UUID tenantId,
            UUID reportId,
            UUID ownerId,
            ReportState state,
            long revision) {}

    public record DirectGrant(
            UUID tenantId,
            UUID reportId,
            UUID subjectId,
            Action action,
            boolean active,
            Instant validFrom,
            Instant validUntil) {}

    public static final class Denied extends RuntimeException {
        public Denied() {
            super("RESOURCE_NOT_ACCESSIBLE_OR_ACTION_NOT_ALLOWED");
        }
    }

    public static void requireApprove(
            Actor actor,
            Membership membership,
            ReportSnapshot report,
            DirectGrant grant,
            Instant decisionTime) {

        boolean sameReportScope = report != null
                && actor.tenantId().equals(report.tenantId());
        require(sameReportScope);

        boolean activeMembership = membership != null
                && actor.tenantId().equals(membership.tenantId())
                && actor.subjectId().equals(membership.subjectId())
                && membership.active()
                && decisionTime.isBefore(membership.validUntil());
        require(activeMembership);

        boolean applicableGrant = grant != null
                && actor.tenantId().equals(grant.tenantId())
                && report.reportId().equals(grant.reportId())
                && actor.subjectId().equals(grant.subjectId())
                && grant.action() == Action.APPROVE
                && grant.active()
                && !decisionTime.isBefore(grant.validFrom())
                && decisionTime.isBefore(grant.validUntil());
        require(applicableGrant);

        // Phân tách người tạo và người duyệt theo chính sách minh họa.
        require(!actor.subjectId().equals(report.ownerId()));
    }

    private static void require(boolean condition) {
        if (!condition) {
            throw new Denied();
        }
    }
}
```

Sau khi hàm cho phép, service còn phải kiểm tra `SUBMITTED`, revision đã được xem và các bất biến phê duyệt trước khi ghi. Quyền và trạng thái có thể dùng những mã lỗi nội bộ khác nhau, nhưng phản hồi công khai chỉ được chứa thông tin chủ thể được phép biết.

Điều cần giữ khi dùng ý tưởng này:

- Không tạo `Membership` hoặc `DirectGrant` từ các cờ `active`, `role` hay `canApprove` trong request.
- Không tái sử dụng các snapshot này từ lần mở màn hình hoặc một job đã chờ lâu.
- `decisionTime` do máy chủ cung cấp theo chính sách thời gian đã định nghĩa.
- Thông qua hàm không tạo ra một permit có thể lưu vô thời hạn rồi dùng sau khi transaction kết thúc.
- Kết quả kiểm tra phải gắn với đúng `reportId`, hành động và phạm vi thay đổi đang được ghi.

## 9. Recheck bằng version hoặc epoch: cần bảo vệ cả bước sử dụng

Một hệ thống có thể lưu `membershipRevision`, `aclRevision` hoặc `permissionEpoch` để phát hiện quyết định quyền đã cũ. Chúng hữu ích khi mỗi thay đổi liên quan chắc chắn cập nhật revision tương ứng.

Tuy nhiên, cách làm sau vẫn có khoảng trống:

```text
đọc aclRevision hiện tại
so sánh với revision đã dùng để đánh giá quyền
nếu bằng nhau:
    ghi đối tượng ở một thao tác độc lập
```

ACL có thể thay đổi sau phép so sánh. Tương tự, chỉ đọc các version của nhiều hàng không tự ngăn write skew giữa transaction sửa quyền và transaction tạo hiệu ứng.

Một giao thức optimistic có thể xác nhận quyền bằng thao tác ghi có điều kiện trên hàng bảo vệ chung, rồi giữ quyền phối hợp đó tới hết transaction. Ví dụ, một trường điều phối riêng được cập nhật chỉ khi `acl_revision` còn khớp; thao tác thu hồi cũng phải ghi cùng hàng bảo vệ.

Cần phân biệt revision quyền với số lần sử dụng: không bắt buộc tăng epoch thu hồi quyền sau mỗi lệnh nghiệp vụ. Có thể có một trường điều phối riêng, miễn giao thức thực sự tạo ra tranh chấp và thứ tự cần thiết.

Một điều kiện `EXISTS` đọc grant trong câu `UPDATE` có thể thể hiện chính sách kiểm tra tại statement, nhưng không tự chứng minh một ngữ nghĩa mạnh hơn về thu hồi tới thời điểm commit trên mọi engine. Cần xét isolation, snapshot và cách transaction thu hồi tham gia.

Version tài nguyên cũng chưa đủ nếu quyền thay đổi ở bảng khác mà version tài nguyên không đổi. Phải xác định đầy đủ tập phụ thuộc của quyết định, không chỉ đặt thêm một trường tên `version`.

## 10. Cache quyền và token mang theo claim cũ

### 10.1. Cache là một lựa chọn nhất quán, không phải nguồn quyền tự động mới nhất

Một cache có thể giữ kết quả cho phép sau khi quyền đã bị thu hồi. TTL ngắn làm giảm thời gian tồn tại của dữ liệu cũ nhưng không cung cấp thu hồi ngay lập tức.

Nếu nghiệp vụ yêu cầu quyết định hiện hành tại lúc ghi, cần đọc nguồn chuẩn hoặc sử dụng giao thức invalidation, epoch và xác nhận đủ mạnh cho bảo đảm đó. Không chỉ thêm một request đọc cache nữa rồi gọi đó là recheck.

Thông điệp invalidation cũng có thể bị trễ, mất hoặc đảo thứ tự. Một cache đã nhận thông điệp cũ không được làm version quyền quay lùi. Việc khởi động lại instance và nạp cache cũng cần cùng chính sách.

### 10.2. Chữ ký token không cập nhật nội dung claim

Một token được ký hợp lệ có thể chứa vai trò hoặc phạm vi quyền tại lúc phát hành. Chữ ký chứng minh nội dung không bị sửa theo cơ chế đã dùng, không chứng minh vai trò đó chưa bị thu hồi sau phát hành.

Các lựa chọn có thể gồm kiểm tra trạng thái phiên, token introspection, epoch của chủ thể hoặc token có thời hạn phù hợp với mức độ trễ được chấp nhận. Bảo đảm thực tế phải tương ứng với cách triển khai, không chỉ với tên cơ chế.

Không lưu `canApprove=true` trong token hoặc session rồi dùng nó cho mọi hồ sơ. Quyền theo đối tượng, quan hệ chủ sở hữu, trạng thái và phạm vi ủy quyền vẫn cần được xét cho lệnh cụ thể.

### 10.3. Nguồn quyền lỗi phải có hành vi rõ ràng

Nếu dịch vụ quyền không truy cập được, không tự chuyển một quyết định không xác định thành cho phép. Với thao tác nhạy cảm, không tạo hiệu ứng khi thiếu bằng chứng quyền cần thiết.

Lỗi hạ tầng cũng không nhất thiết là người dùng không có quyền. Có thể phản hồi tạm thời không thể xác minh, theo hợp đồng dịch vụ, thay vì gắn nhầm thành một kết luận từ chối quyền vĩnh viễn.

Nếu sử dụng quyết định đã cache trong sự cố, đó phải là chính sách có phạm vi, thời hạn và rủi ro nhất quán được chấp nhận rõ ràng. Không biến fallback sang kết quả cho phép cũ thành hành vi ngầm.

## 11. IAM bên ngoài và giới hạn của kiểm tra lại qua mạng

Nếu dữ liệu quyền ở một hệ thống khác với database nghiệp vụ, hai lần gọi IAM không tự tạo transaction chung:

```text
gọi IAM -> được phép
quyền thay đổi ở IAM
ghi database nghiệp vụ
```

Gọi lại IAM ngay trước ghi chỉ thu hẹp khoảng trống. Muốn có bảo đảm mạnh hơn, cần một giao thức phối hợp thực sự hoặc chọn ngữ nghĩa có giới hạn rõ ràng.

Một quyết định quyền có thời hạn hoặc lease có thể ràng buộc chủ thể, tenant, đối tượng, hành động, snapshot và thời hạn. Nhưng nó chỉ cung cấp những tính chất mà giao thức phát và kiểm tra quyết định hỗ trợ:

- Có chữ ký không tự làm quyết định được thu hồi ngay lập tức.
- Có thời hạn không tự làm quyết định chỉ dùng được một lần.
- Có nonce không tự chống dùng lại nếu không có cơ chế tiêu thụ nguyên tử.
- Có resource version không tự bao phủ các nguồn quyền khác.

Nếu chấp nhận một quyết định cho phép trong thời gian lease, phải hiểu đó là mô hình nhất quán đã chọn. Nếu nghiệp vụ không cho phép độ trễ đó, cần thay đổi ranh giới thực thi hoặc cách phối hợp thay vì tuyên bố rằng gọi API thêm một lần đã loại bỏ TOCTOU.

## 12. Tác vụ nền và danh tính thực hiện

Một lệnh vào hàng đợi khi người dùng có quyền có thể được thực thi sau khi họ đã rời tenant. Worker chạy bằng service account có quyền rộng không nên mặc nhiên dùng quyền của mình để hoàn tất một yêu cầu đã mất quyền.

Job nên lưu ngữ cảnh đủ để đánh giá lại:

```text
initiatingSubjectId
tenantId
resourceId và quan hệ đích
operationType
requestedChanges hoặc snapshot đã chốt
expectedResourceRevision
operationId / idempotency context
chính sách ủy quyền áp dụng
```

Các trường này phải được tạo và bảo vệ phía máy chủ. Chúng không phải cơ chế xác thực độc lập chỉ vì được lưu trong queue.

Với mô hình kiểm tra tại thời điểm thực thi, worker xác định lại trạng thái thành viên, grant, phạm vi đối tượng và trạng thái nghiệp vụ trước khi tạo hiệu ứng. Không dùng kết quả `authorized=true` từ payload job làm bằng chứng cuối cùng.

Cần tách hai trường hợp:

1. Job vẫn đang chờ quyền thực hiện một lệnh thay người dùng: kiểm tra lại theo chính sách quyền người dùng.
2. Job đang phát hoặc hoàn tất hiệu ứng của một lệnh đã được commit hợp lệ: thực hiện theo nghĩa vụ hệ thống đã ghi, với cơ chế chống trùng và điều kiện riêng.

Nếu nhập nhằng hai trường hợp, hệ thống có thể tiếp tục thao tác trái quyền hoặc dừng một nghĩa vụ đã được chấp nhận mà không có quy trình xử lý tương ứng.

## 13. Idempotency và kết quả quyền khi retry

Authorization recheck và idempotency có trách nhiệm khác nhau:

| Cơ chế | Trách nhiệm |
|---|---|
| Recheck quyền | Một lần thực thi mới có được phép tạo hiệu ứng hay không |
| Version checking | Snapshot tài nguyên có còn phù hợp với ý định không |
| Idempotency | Cùng một ý định đã tạo hiệu ứng trước đó chưa |

Nếu lệnh đã commit nhưng phản hồi mất, retry cần nhận diện kết quả cũ thay vì thực thi lại. Máy chủ vẫn kiểm tra quyền đọc kết quả đó; quyền đọc kết quả không nhất thiết có cùng điều kiện với quyền tạo quyết định mới.

Ví dụ, hồ sơ đã chuyển sang `APPROVED` nên không thể duyệt mới lần nữa. Điều đó không có nghĩa retry của quyết định đã thành công phải bị coi là một lệnh duyệt mới rồi báo xung đột trạng thái.

Ngược lại, người dùng đã mất quyền xem hồ sơ có thể không còn được nhận chi tiết kết quả cũ. Việc trả lỗi truy cập khi tra kết quả không chứng minh lệnh trước chưa commit.

Một lệnh mới chưa commit không được mượn bản ghi idempotency của tenant hoặc nội dung khác để bỏ qua recheck. Khóa và fingerprint cần phạm vi rõ ràng, kết quả bền vững phải nhất quán với transaction nghiệp vụ.

## 14. Ghi nhận quyết định quyền và phản hồi lỗi

Audit nên cho phép giải thích tại sao một lệnh được chấp nhận:

- Chủ thể, tenant, đối tượng và hành động.
- Nguồn quyền hoặc grant liên quan, trong phạm vi được phép lưu.
- Revision hoặc epoch đã tham gia quyết định nếu có.
- Snapshot tài nguyên, thời điểm quyết định và kết quả transaction.
- Operation ID cùng thông tin đối chiếu idempotency cần thiết.

Không cần lưu token, toàn bộ claim nhạy cảm hoặc dữ liệu cá nhân không cần thiết để chứng minh chính sách. Audit thành công phải nhất quán với quyết định nghiệp vụ đã commit.

Lần bị từ chối quyền có thể được ghi ở kênh phù hợp với trạng thái thất bại rõ ràng. Không để transaction rollback làm hệ thống vẫn ghi một quyết định duyệt thành công ở hệ thống khác thiếu phối hợp.

Phản hồi cho người gọi cần tránh tiết lộ việc một hồ sơ hoặc grant ngoài quyền có tồn tại hay không. Có thể dùng thông báo chung theo chính sách, kèm mã tham chiếu hỗ trợ không chứa bí mật.

Nếu chưa tạo hiệu ứng vì không xác minh được quyền, có thể nói rõ thao tác chưa được áp dụng khi hệ thống đã xác nhận điều đó. Nếu sự cố ở gần commit làm kết quả chưa xác định, không dùng một lỗi quyền mới để khẳng định lệnh trước đã thất bại.

## 15. Kiểm thử thu hồi quyền với lịch có kiểm soát

### 15.1. Thu hồi sau kiểm tra sớm nhưng trước thực thi

```text
A mở màn hình hoặc tạo job khi còn quyền.
Tạm dừng trước bước recheck có hiệu lực.
R thu hồi grant và commit.
Cho A tiếp tục.
```

Kết quả trong chính sách kiểm tra tại thực thi: không tạo quyết định duyệt, không chuyển trạng thái hồ sơ và không phát event thành công. Đọc dữ liệu cuối bằng connection mới để xác nhận.

### 15.2. Thu hồi cạnh tranh với ranh giới được bảo vệ

Với giao thức khóa của ví dụ:

```text
A đã lấy các khóa bảo vệ và đánh giá quyền hợp lệ.
R bắt đầu thu hồi và phải chờ.
A kết thúc transaction.
R tiếp tục và commit thu hồi.
Gửi một lệnh mới để xác nhận grant cũ không còn được dùng.
```

Không đặt barrier yêu cầu R thu hồi xong rồi mới cho A commit nếu A đang giữ chính khóa mà R cần. Cách dựng test đó tạo bế tắc do bộ điều phối, không phải bằng chứng chống TOCTOU.

Nếu thiết kế dùng optimistic coordination, cần tạo lịch khiến một bên cập nhật revision bảo vệ trước và xác nhận bên kia không thể commit dựa trên quyết định cũ.

### 15.3. Ma trận kiểm thử bổ sung

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Mở màn hình còn quyền, gửi lệnh sau thu hồi | Server không dùng lại quyền từ giao diện |
| Job chờ lâu rồi quyền bị thu hồi | Worker không dùng quyền service account để duyệt thay |
| Token còn hạn nhưng grant đã thu hồi | Hành vi đúng với mô hình nhất quán đã công bố |
| Cache còn kết quả cho phép cũ | Không vượt quá bảo đảm TTL hoặc giao thức xác nhận đã chọn |
| Thay đổi chủ hồ sơ trước khi duyệt | Quy tắc không tự duyệt hồ sơ của mình vẫn được áp dụng |
| Dòng hoặc tài liệu bị chuyển sang đối tượng khác | Quan hệ cha/con được kiểm tra lại, không chỉ ID ban đầu |
| Chủ thể bị vô hiệu hóa trong tenant | Không tạo hiệu ứng mới bằng trạng thái thành viên cũ |
| Grant chưa đến hạn hoặc đã hết hạn | Từ chối theo decision time tin cậy |
| Decision time đúng bằng validUntil | Không coi grant còn hiệu lực trong mô hình khoảng nửa mở |
| Cùng actor, grant của tenant khác | Không dùng quyền chéo tenant |
| Grant có quyền EDIT nhưng lệnh yêu cầu APPROVE | Không suy rộng quyền sang hành động khác |
| Nguồn quyền timeout hoặc không xác định | Không tự chuyển thành cho phép |
| Grant thay đổi nhưng version tài nguyên không đổi | Cơ chế bảo vệ quyền riêng vẫn phát hiện hoặc phối hợp đúng |
| Lệnh commit, mất response, rồi chủ thể mất quyền | Không thực thi lại; quyền đọc kết quả được xét riêng |
| Có đường import hoặc admin sửa grant trực tiếp | Không bỏ qua hàng guard hoặc epoch mà giao thức dựa vào |
| Transaction thất bại sau recheck | Không có trạng thái hoặc audit thành công còn sót |

Kiểm thử phải dùng các transaction độc lập và quan sát đúng điểm. Một test chỉ gọi `requireApprove()` với `grant.active=false` kiểm tra logic chính sách, chưa chứng minh giao thức chống thay đổi quyền đồng thời.

## 16. Những cách triển khai cần tránh

| Cách triển khai | Khoảng trống còn lại | Hướng xử lý |
|---|---|---|
| Kiểm tra quyền duy nhất khi đăng nhập | Quyền và đối tượng có thể thay đổi sau đó | Kiểm tra theo lệnh và đối tượng lúc tạo hiệu ứng |
| Tin cờ authorized trong frontend hoặc job | Kết quả cũ hoặc dữ liệu không tin cậy | Dựng lại quyết định từ ngữ cảnh và nguồn quyền được bảo vệ |
| Gọi canApprove ngay trước update nhưng không phối hợp | Quyền vẫn có thể bị thu hồi ở giữa | Xác định điểm hiệu lực và giao thức khóa/version phù hợp |
| Chỉ dùng transaction trên hồ sơ | Dữ liệu quyền ở hàng hoặc hệ thống khác chưa được bảo vệ | Bao phủ đúng phụ thuộc quyết định quyền |
| Chỉ khóa grant khi nó tồn tại | Thiếu điểm phối hợp cho biến đổi của tập quyền | Guard ổn định hoặc cơ chế tương đương đúng mô hình |
| Dùng TTL ngắn như bảo đảm thu hồi tức thời | Vẫn có cửa sổ dùng quyền cũ | Công bố độ trễ hoặc dùng xác nhận mạnh hơn |
| Dùng đúng resource version như bằng chứng quyền | Version không cấp quyền và có thể không đổi khi ACL đổi | Kiểm tra quyền cùng revision nguồn quyền cần thiết |
| Worker dùng quyền rộng của chính mình | Trở thành bên thực hiện hộ vượt phạm vi ủy quyền | Phân biệt lệnh thay người dùng với nghĩa vụ hệ thống đã commit |
| Đọc IAM hai lần rồi tuyên bố nguyên tử | Không có transaction chung với hệ thống quyền | Giao thức phối hợp hoặc mô hình lease nhất quán rõ ràng |

## 17. Thiết kế recheck cho một thao tác mới

Trước khi triển khai, cần trả lời:

1. Lệnh được phép nếu quyền còn hiệu lực ở thời điểm nào?
2. Quyết định phụ thuộc danh tính, tenant, đối tượng, hành động, trường dữ liệu và nguồn quyền nào?
3. Các nguồn đó thay đổi ra sao, và đường thu hồi hoặc sửa quyền có tham gia cùng giao thức không?
4. Điều gì giữ kết quả kiểm tra đúng tới điểm sử dụng: khóa, cập nhật có điều kiện, snapshot chốt hay một lease có giới hạn?
5. Hết hạn theo thời gian, cache và quyền ngoài hệ thống được diễn giải thế nào?
6. Worker, import và retry có đi qua cùng ranh giới kiểm tra bắt buộc không?
7. Kiểm thử nào chứng minh thu hồi đã có hiệu lực không bị một quyết định cũ vượt qua?

Authorization recheck có giá trị khi quyết định quyền được dựng lại cho đúng lệnh, từ đúng nguồn và gắn với một điểm thực thi có ngữ nghĩa rõ ràng. Phối hợp bước kiểm tra với transaction, version, vòng đời quyền và xử lý retry giúp ngăn kết quả cho phép cũ trở thành đường bỏ qua quy tắc nghiệp vụ.
