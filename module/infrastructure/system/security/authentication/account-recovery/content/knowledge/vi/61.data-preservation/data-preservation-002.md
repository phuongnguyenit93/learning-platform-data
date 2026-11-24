# Preserving authorization data: bảo toàn dữ liệu phân quyền khi khôi phục tài khoản

## 1. Khôi phục xác thực không đồng nghĩa cấp lại mọi quyền

Một người dùng mất điện thoại chứa MFA nhưng vẫn là thành viên của tổ chức, vẫn sở hữu tài liệu và vẫn có những quyền được cấp trước đó. Nếu quy trình recovery xóa tài khoản rồi tạo lại, các liên kết phân quyền có thể mất. Ngược lại, nếu recovery chép toàn bộ quyền từ một snapshot cũ, nó có thể làm sống lại quyền quản trị đã bị thu hồi.

**Preserving authorization data** là bảo vệ tính toàn vẹn, liên kết chủ thể và lịch sử của dữ liệu quyết định ai được làm gì trên tài nguyên nào trong suốt quá trình khôi phục tài khoản. Mục tiêu là thay đổi phương thức chứng minh danh tính mà không vô tình làm mất, chuyển nhầm hoặc mở rộng quyền truy cập.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, điều này gắn với khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Xác minh danh tính, đánh giá rủi ro, token dùng một lần và kiểm soát phiên phải kết hợp với phân quyền: chứng minh được chủ tài khoản không tự chứng minh rằng mọi quyền trong một bản sao cũ vẫn còn hợp lệ.

Cần tách ba câu hỏi:

1. **Authentication:** ai đang chứng minh quyền kiểm soát tài khoản?
2. **Authorization:** chủ thể đó hiện được phép thực hiện hành động nào?
3. **Recovery restriction:** trong và sau recovery, có hạn chế bổ sung nào đang áp dụng?

Giữ nguyên dữ liệu phân quyền không có nghĩa bỏ qua hạn chế recovery, dừng đồng hồ hết hạn quyền hoặc khôi phục tất cả quyền từng tồn tại.

## 2. Dữ liệu phân quyền gồm những gì?

Phân quyền thường nằm ở nhiều nơi hơn một cột `role` trong bảng người dùng.

| Nhóm dữ liệu | Ví dụ | Điều cần bảo toàn |
| --- | --- | --- |
| Membership | Thành viên tenant, tổ chức, workspace | Đúng chủ thể, đúng phạm vi, trạng thái và thời hạn |
| Role binding | Editor của workspace A, approver của dự án B | Vai trò gắn với đúng tài nguyên và điều kiện cấp |
| Quyền trực tiếp | Được đọc một tài liệu cụ thể | Subject, resource, action và hiệu lực của grant |
| Quyền sở hữu | Chủ tài liệu, repository hoặc cấu hình | Không chuyển owner do đổi email hoặc credential |
| Điều kiện ABAC | Bộ phận, mức nhạy cảm, yêu cầu thiết bị | Nguồn có thẩm quyền và phiên bản chính sách |
| Entitlement | Tính năng theo gói dịch vụ hoặc quyền sử dụng | Trạng thái hiện hành từ nguồn nghiệp vụ tương ứng |
| Hạn chế và thu hồi | Đình chỉ tài khoản, deny, quyền đã thu hồi | Không mất hiệu lực do reset mật khẩu hoặc thay factor |
| Delegation và quyền tạm | Quyền được ủy quyền, quyền nâng tạm thời | Người cấp, phạm vi và thời điểm hết hạn ban đầu |
| Dấu vết quyết định | Người cấp, lý do, phiên bản và thời gian | Khả năng truy vết và đối chiếu sau sự cố |

Một số dữ liệu chỉ là biểu diễn dẫn xuất: role nằm trong access token, permission cache hoặc bản sao tìm kiếm. Chúng không nhất thiết là nguồn chuẩn. Bảo toàn chúng bằng cách giữ mọi token cũ có thể làm duy trì quyền đã bị thu hồi.

Trước khi thiết kế recovery, cần biết dịch vụ nào có thẩm quyền đối với từng nhóm. Ví dụ, membership do dịch vụ tổ chức quản lý; entitlement do nghiệp vụ thuê bao quyết định; một cache trong dịch vụ đăng nhập không có quyền ghi ngược để phục hồi các nguồn đó.

## 3. Giữ ổn định chủ thể, thay đổi credential

Một nguyên tắc quan trọng là giữ định danh nội bộ ổn định của chủ thể, chẳng hạn `principalId` hoặc `accountId`, và thay đổi credential gắn với chủ thể đó. Không dùng email làm khóa duy nhất để nối lại mọi quyền sau recovery.

Ví dụ:

```text
principalId = principal_482
  ├── membership: tenant_A / ACTIVE
  ├── role: project_17 / EDITOR
  ├── ownership: document_901
  └── authentication:
        password credential: được thay thế
        MFA factor: được đăng ký lại
```

Nếu email của người dùng đổi từ `old@example.test` sang `new@example.test`, owner của tài liệu vẫn là `principal_482`. Việc thay địa chỉ liên lạc không tạo chủ thể mới và cũng không chuyển quyền sang một tài khoản khác đang dùng cùng chuỗi email.

Các cách làm dễ gây lỗi:

- Xóa user cũ, tạo user mới và mong các liên kết tự khớp lại.
- Tìm tất cả tài nguyên theo email rồi cập nhật owner sau reset mật khẩu.
- Đổi `principalId` khi thay provider đăng nhập mà không có quy trình liên kết danh tính riêng.
- Sao chép role sang một tài khoản mới chỉ vì người yêu cầu biết thông tin của tài khoản cũ.

Nếu thật sự cần gộp, chuyển hoặc tái tạo danh tính nội bộ, đó là một thay đổi có phạm vi khác recovery credential thông thường. Nó cần quy trình riêng để xác minh chủ thể, xử lý xung đột quyền và ghi nhận việc chuyển quyền. Không giấu thay đổi đó bên trong nút “Reset MFA”.

## 4. Các bất biến bảo toàn

Một thiết kế có thể đặt các bất biến sau:

1. Recovery không tự thêm role, membership, quyền sở hữu hoặc entitlement.
2. Recovery không làm sống lại grant đã thu hồi hoặc kéo dài grant đã hết hạn.
3. Tài nguyên tiếp tục tham chiếu đúng chủ thể nội bộ đã được xác minh.
4. Các deny, đình chỉ và security hold hiện hành không bị xóa chỉ vì credential đã thay.
5. Mọi hạn chế recovery được biểu diễn rõ và được áp dụng trên tất cả đường truy cập liên quan.
6. Role và quyền vẫn tiếp tục chịu chính sách hiện hành, kể cả khi chính sách đổi trong thời gian recovery.
7. Lịch sử cấp, thu hồi và thay đổi quyền được giữ để giải thích quyết định.

Các bất biến không có nghĩa dữ liệu authorization phải bất biến hoàn toàn trong thời gian xử lý. Quản trị viên có thể hợp lệ thu hồi quyền, dịch vụ thuê bao có thể cập nhật entitlement và quyền tạm có thể hết hạn. Recovery phải tôn trọng những thay đổi đó thay vì khôi phục trạng thái tại lúc mở hồ sơ.

Một yêu cầu cụ thể cần trả lời: recovery này được phép ghi những trường nào? Thông thường nó chỉ thay credential, phiên bản xác thực, trạng thái hồ sơ và một hạn chế tạm được chính sách cho phép. Các bảng role, ACL, ownership và membership không nên nằm trong một lệnh cập nhật tổng quát do client gửi.

## 5. Nguồn chuẩn, snapshot và dữ liệu dẫn xuất

Một snapshot trước recovery có ích để đối chiếu và điều tra, nhưng không phải lệnh khôi phục vô điều kiện.

Ví dụ:

```text
T0: Người dùng có role EDITOR và ADMIN tạm, ADMIN hết hạn lúc T3.
T1: Bắt đầu recovery, chụp snapshot.
T2: Quản trị viên thu hồi EDITOR do đổi nhiệm vụ.
T3: ADMIN tạm hết hạn.
T4: Hoàn tất recovery.
```

Nếu chép snapshot T1 vào T4, cả quyền đã thu hồi và quyền hết hạn có thể được hồi sinh. Bảo toàn đúng nghĩa là giữ nguồn chuẩn và lịch sử ở T4, không buộc hệ thống quay về T1.

Nên phân loại:

- **Nguồn chuẩn:** role binding, membership hoặc policy do dịch vụ có thẩm quyền duy trì.
- **Bằng chứng đối chiếu:** snapshot, audit event, phiên bản và digest phục vụ xác nhận thay đổi.
- **Dữ liệu dẫn xuất:** token claim, cache quyền hoặc index có thể cần vô hiệu hóa và xây dựng lại.

Snapshot cần được bảo vệ khỏi sửa đổi và truy cập trái phép. Nếu dùng digest, digest giúp phát hiện sai khác dữ liệu nhưng không chứng minh snapshot sạch hoặc có quyền áp dụng. Một snapshot có chữ ký vẫn có thể chứa quyền bị kẻ tấn công thêm trước khi chụp.

Không ghi toàn bộ ACL hoặc danh sách tài nguyên nhạy cảm vào ticket hỗ trợ thông thường. Có thể lưu tham chiếu snapshot và revision tại kho kiểm soát truy cập, rồi chỉ cho người có thẩm quyền đọc chi tiết khi cần.

## 6. Phân quyền trong lúc recovery: giữ dữ liệu, hạn chế thực thi

Một tài khoản có thể giữ nguyên role nhưng tạm bị chặn thao tác nhạy cảm trong khi recovery. Cách rõ ràng là dùng một lớp hạn chế riêng, thay vì xóa role rồi cố gắng nhớ để cấp lại.

Ví dụ:

```yaml
principalId: principal_482
recoveryState: RESTRICTED
restrictionReference: recovery_case_25
blockedBusinessActions: true
allowedRecoveryCapabilities:
  - factor:replacement:enroll
  - recovery:status:read
```

Cấu trúc trên chỉ minh họa trạng thái có thẩm quyền ở máy chủ. Client không được tự khai báo danh sách capability hoặc tắt `blockedBusinessActions`.

Trong thiết kế này, quyết định cho phép một hành động nghiệp vụ phải đồng thời thỏa mãn:

```text
đúng chủ thể và tenant
AND tài khoản còn hoạt động
AND không có security hold chặn hành động
AND phiên xác thực còn hợp lệ
AND chính sách authorization hiện hành cho phép
AND hạn chế recovery cho phép
```

Đây là các điều kiện bắt buộc của thiết kế minh họa, không phải giả định rằng mọi policy engine sẵn có đều dùng quy tắc “deny luôn thắng”. Nếu engine có cách kết hợp allow/deny khác, ứng dụng phải đưa các cổng bắt buộc vào đúng vị trí và áp dụng trên mọi đường truy cập.

Phiên recovery nên là một loại principal hoặc session context có phạm vi hạn chế, không phải phiên ứng dụng thường được gắn toàn bộ role. Một người đang đăng ký MFA mới chưa được phép xuất dữ liệu hoặc phê duyệt giao dịch chỉ vì role cũ vẫn còn trong cơ sở dữ liệu.

Khi hoàn tất recovery, việc gỡ hạn chế cần kiểm tra điều kiện cụ thể. Nó không xóa các security hold khác, không tự gia hạn quyền tạm và không thay thế quyết định riêng của người quản lý tổ chức.

## 7. Giữ riêng phiên bản xác thực và phiên bản phân quyền

Đổi mật khẩu hoặc factor làm thay đổi trạng thái xác thực. Thêm role hoặc thu hồi ACL làm thay đổi trạng thái phân quyền. Hai loại thay đổi có liên quan nhưng không đồng nhất.

Một mô hình có thể dùng:

```text
authenticationEpoch: tăng khi cần vô hiệu hóa phiên xác thực cũ
authorizationVersion: tăng khi role, grant hoặc restriction liên quan thay đổi
policyVersion: phiên bản chính sách dùng để ra quyết định
```

Không cần bắt buộc mọi hệ thống có đúng ba trường này. Ý chính là verifier phải phát hiện được phiên cũ và dữ liệu quyền cũ theo cơ chế nhất quán với kiến trúc.

Ví dụ, access token mang role `ADMIN` được cấp trước khi quyền bị thu hồi không nên tiếp tục được chấp nhận chỉ vì chữ ký còn hợp lệ. Có thể dùng introspection, kiểm tra phiên bản, cache có cơ chế vô hiệu hóa hoặc một thiết kế token phù hợp khác. Tăng version trong cơ sở dữ liệu không có tác dụng nếu dịch vụ tài nguyên không bao giờ kiểm tra nó.

Sau recovery, refresh token cũ, phiên thiết bị tin cậy và credential máy phải được xử lý theo chính sách rủi ro. Việc thu hồi token không làm mất dữ liệu role binding. Cấp token mới cũng không được sao chép nguyên role claim từ token cũ; cần đánh giá lại từ nguồn hiện hành.

Cache quyền cần được định danh đủ phạm vi, chẳng hạn chủ thể, tenant, tài nguyên, revision và policy version phù hợp. Cache chỉ theo `userId` có thể trả quyền của tenant này cho một request thuộc tenant khác.

## 8. Ví dụ Java: cổng phân quyền không làm sống lại quyền cũ

Ví dụ sau dành cho API nghiệp vụ thông thường. Nó cho thấy phiên và snapshot quyền phải khớp trạng thái hiện hành, đồng thời recovery restriction có thể chặn hành động mà không xóa role. API phục vụ recovery cần cổng capability riêng, không được bỏ qua kiểm tra chỉ để dùng lại hàm này.

Các ID bắt buộc được giả định đã kiểm tra không rỗng. `PrincipalState` và `PermissionDecision` phải do máy chủ lấy từ nguồn có thẩm quyền và bộ đánh giá chính sách cho đúng request, không ánh xạ từ các trường do client gửi.

```java
import java.util.Objects;

public final class AuthorizationPreservationGuard {
    public record SessionContext(
            String principalId,
            String tenantId,
            long authenticationEpoch,
            long authorizationVersion,
            boolean recoveryOnly) {}

    public record PrincipalState(
            String principalId,
            String tenantId,
            long authenticationEpoch,
            long authorizationVersion,
            boolean active,
            boolean businessSecurityHold,
            boolean recoveryRestricted) {}

    public record Resource(String id, String tenantId) {}

    public record PermissionDecision(
            String principalId,
            String tenantId,
            String resourceId,
            String action,
            long evaluatedAuthorizationVersion,
            boolean allowed) {}

    public record Result(boolean allowed, String reason) {}

    public static Result authorizeBusinessAction(
            SessionContext session,
            PrincipalState current,
            Resource resource,
            String action,
            PermissionDecision permission) {
        Objects.requireNonNull(session);
        Objects.requireNonNull(current);
        Objects.requireNonNull(resource);
        Objects.requireNonNull(action);
        Objects.requireNonNull(permission);

        if (!session.principalId().equals(current.principalId())
                || !session.tenantId().equals(current.tenantId())
                || !current.tenantId().equals(resource.tenantId())) {
            return new Result(false, "PRINCIPAL_OR_TENANT_MISMATCH");
        }
        if (!current.active() || current.businessSecurityHold()) {
            return new Result(false, "ACCOUNT_RESTRICTED");
        }
        if (session.authenticationEpoch() != current.authenticationEpoch()) {
            return new Result(false, "REAUTHENTICATION_REQUIRED");
        }
        if (session.recoveryOnly() || current.recoveryRestricted()) {
            return new Result(false, "RECOVERY_CAPABILITY_ONLY");
        }
        if (session.authorizationVersion() != current.authorizationVersion()
                || permission.evaluatedAuthorizationVersion()
                        != current.authorizationVersion()) {
            return new Result(false, "AUTHORIZATION_REFRESH_REQUIRED");
        }
        boolean decisionMatchesRequest =
                current.principalId().equals(permission.principalId())
                && current.tenantId().equals(permission.tenantId())
                && resource.id().equals(permission.resourceId())
                && action.equals(permission.action());
        if (!decisionMatchesRequest || !permission.allowed()) {
            return new Result(false, "PERMISSION_DENIED");
        }
        return new Result(true, "CURRENT_POLICY_ALLOWED");
    }
}
```

Ví dụ dùng lựa chọn chặt: phiên mang authorization version cũ bị yêu cầu làm mới thay vì tiếp tục dùng claim cũ. Một kiến trúc khác có thể đánh giá quyền trực tiếp cho mỗi request mà không đưa version vào session; khi đó vẫn phải bảo đảm không dùng kết quả permission đã lỗi thời.

`authorizationVersion` trong ví dụ phải thay đổi khi bất kỳ nguồn dữ liệu nào có ảnh hưởng tới quyết định đã thay đổi, hoặc được thay bằng cơ chế revision tương đương. Nếu thay chính sách toàn cục mà version không phản ánh, phép so sánh số đơn thuần không phát hiện được thay đổi đó.

Hàm thuần cũng không tự giải quyết cạnh tranh giữa kiểm tra và tác động nghiệp vụ. Với thao tác nhạy cảm như chuyển quyền sở hữu, dịch vụ cần bảo vệ revision hoặc trạng thái liên quan tại thời điểm thực thi, không dùng một kết quả allow cũ vô thời hạn.

## 9. Phạm vi ghi của giao dịch recovery

Cách đơn giản để tránh mất dữ liệu phân quyền là không cho luồng recovery ghi chúng ngoài các ngoại lệ đã định nghĩa. Một transaction hoàn tất credential recovery có thể tổ chức như sau:

```text
BEGIN TRANSACTION
  xác nhận recovery case, chủ thể và capability còn hiệu lực
  kiểm tra bằng chứng và factor mới đã được kiểm chứng
  kiểm tra security hold và điều kiện hoàn tất hiện hành
  tiêu thụ capability hoàn tất đúng một lần
  cập nhật credential được phép thay
  tăng authentication epoch nếu chính sách yêu cầu
  cập nhật recovery restriction theo phạm vi được cho phép
  ghi audit và outbox
COMMIT
```

Không có bước “xóa mọi role rồi chép lại snapshot”. Membership và grant tiếp tục được quản lý bởi workflow phân quyền có thẩm quyền. Nếu việc đổi recovery restriction làm thay đổi quyền hiệu lực, nó cần kích hoạt cơ chế version hoặc invalidation phù hợp.

Các entity và DTO nên tách rõ trường được phép sửa. Một request reset mật khẩu không nên chứa `roles`, `ownerId`, `tenantId` mới hoặc `isAdmin`. Việc dùng chung hàm `saveUser()` với một object do client gửi dễ làm các trường authorization bị ghi đè hoặc bị mass assignment.

Ở tầng lưu trữ, có thể tách bảng hoặc giới hạn quyền của service account để recovery service không tự sửa role binding. Tuy nhiên, phân tách vật lý không thay thế kiểm tra logic: một API nội bộ có quyền rộng vẫn có thể bị gọi sai nếu không xác thực phạm vi và mục đích.

Nếu nguồn authorization nằm ở dịch vụ khác, recovery không nên gọi một API đồng bộ toàn bộ user từ bản sao cũ. Chỉ phát sự kiện có ý nghĩa như “credential recovery completed” và để dịch vụ có thẩm quyền quyết định những tác động thuộc phạm vi của nó.

## 10. Cạnh tranh với thay đổi quyền hợp lệ

Trong thời gian người dùng recovery, quản trị viên có thể chuyển họ sang dự án khác hoặc thu hồi membership. Không thể giả định mọi dữ liệu đều đứng yên từ khi mở case đến khi hoàn tất.

Hai nguyên tắc cần cùng được giữ:

- Recovery không làm mất thay đổi phân quyền hợp lệ đang diễn ra.
- Recovery không hoàn tất dựa trên điều kiện bảo mật đã bị thay đổi theo cách khiến kết quả không còn được phép.

Ví dụ, việc thu hồi role `EDITOR` có thể không ngăn người dùng hoàn tất recovery để đăng nhập với quyền còn lại. Ngược lại, một security hold do nghi xâm nhập có thể phải chặn hoàn tất. Hệ thống cần phân biệt thay đổi quyền thông thường với điều kiện cổng bắt buộc.

Có thể dùng optimistic locking, version fence hoặc khóa cho các trạng thái có liên quan. Các writer phải tuân thủ cùng mô hình nhất quán; khóa một bản ghi recovery không chặn được một dịch vụ khác sửa trạng thái bảo vệ tài khoản nếu dịch vụ đó không tham gia cơ chế kiểm soát.

Nếu ghi nhận fingerprint authorization trước và sau recovery, khác biệt không tự có nghĩa lỗi. Cần kiểm tra revision và các sự kiện thay đổi hợp lệ giữa hai thời điểm. Một phép so sánh buộc hai snapshot bằng nhau có thể vô tình dẫn tới việc chép ngược dữ liệu để xóa thay đổi đúng.

Trong hệ thống phân tán, outbox và consumer idempotent có thể dùng để thông báo thay đổi epoch hoặc invalidation. Khi một thành phần chưa cập nhật, các đường truy cập nhạy cảm cần có kiểm tra trạng thái có hiệu lực theo thiết kế. Không đánh dấu mọi thứ đã an toàn chỉ vì message đã được đưa vào hàng đợi.

## 11. Khi nghi ngờ dữ liệu authorization đã bị sửa trái phép

Bảo toàn không có nghĩa tiếp tục tin mọi grant đang tồn tại. Nếu kẻ tấn công từng thêm role quản trị hoặc đổi owner, cần vừa bảo vệ bằng chứng vừa xác định lại trạng thái hợp lệ.

Một cách tiếp cận có cấu trúc:

1. Đặt hạn chế phù hợp để ngăn thay đổi và truy cập nhạy cảm tiếp tục gây tác động.
2. Lưu bằng chứng hiện trạng, lịch sử grant và các phiên bản có liên quan tại kho được bảo vệ.
3. Xác định khoảng thời gian nghi ngờ và nguồn có thẩm quyền cho từng quyền.
4. Đối chiếu baseline đã được xác minh với trạng thái hiện tại và các thay đổi hợp lệ trong khoảng giữa.
5. Tạo đề xuất khắc phục cụ thể, có người chịu trách nhiệm và phê duyệt theo chính sách.
6. Áp dụng sửa đổi phân quyền bằng workflow riêng, đồng thời thu hồi phiên hoặc token liên quan.

Không chọn một snapshot “trước khi người dùng báo mất điện thoại” rồi mặc định nó sạch. Thời điểm người dùng phát hiện không nhất thiết trùng thời điểm bắt đầu xâm nhập.

Cũng không dùng phép hợp hoặc giao đơn giản cho mọi loại quyền. Lấy hợp có thể khôi phục grant nguy hiểm; lấy giao có thể làm mất quyền hợp lệ hoặc xử lý sai deny và điều kiện ABAC. Việc đối chiếu cần hiểu ngữ nghĩa từng loại binding và những quyết định có thẩm quyền.

Nếu phát hiện một quyền mới không rõ nguồn gốc, có thể tạm chặn việc sử dụng quyền đó theo chính sách trong khi đánh giá. Việc xóa, khôi phục hoặc chuyển quyền cần được ghi rõ, không chỉnh sửa lịch sử như thể sự kiện trái phép chưa từng xảy ra.

## 12. Ownership, quyền tạm và entitlement cần chú ý riêng

### Quyền sở hữu tài nguyên

Owner thường là liên kết lâu dài và có thể mang quyền cao hơn role thông thường. Recovery credential không được tự chuyển owner sang người hỗ trợ, địa chỉ email mới hoặc tài khoản thay thế. Nếu tài nguyên dùng owner là principal đã bị tạo lại, cần một quy trình khắc phục liên kết có thẩm quyền thay vì tìm theo tên hiển thị.

### Quyền tạm thời và delegation

Grant có hạn phải tiếp tục giữ thời điểm hết hạn ban đầu. Không tính lại `expiresAt = lúc hoàn tất recovery + thời lượng cũ`, vì điều đó kéo dài quyền. Delegation cũng cần giữ người cấp, người nhận, phạm vi và điều kiện thu hồi.

### Entitlement nghiệp vụ

Quyền theo thuê bao hoặc trạng thái tổ chức cần dựa vào nguồn hiện hành. Một snapshot lúc người dùng còn gói dịch vụ cao không cho phép recovery phục hồi entitlement sau khi gói đã thay đổi hợp lệ.

### Tài khoản đặc quyền

Khôi phục được credential không nhất thiết đủ để kích hoạt lại một role quản trị nhạy cảm. Chính sách có thể yêu cầu step-up mới, phê duyệt hoặc tái cấp quyền tạm thời qua workflow quản trị. Những yêu cầu này nên là điều kiện thực thi rõ ràng, không phụ thuộc vào việc role có tình cờ còn nằm trong token cũ.

## 13. Audit, quyền riêng tư và khả năng giải thích

Một hồ sơ recovery cần cho biết điều gì đã thay đổi và điều gì vẫn được quản lý bởi authorization hiện hành. Audit hữu ích có thể chứa:

```text
recoveryCaseId, principalId, tenantScope
actorId, approverReferences, executionService
authenticationEpochBefore, authenticationEpochAfter
authorizationRevisionObserved, policyVersionObserved
credentialChangeReferences
recoveryRestrictionBefore, recoveryRestrictionAfter
securityHoldReferences
authorizationSnapshotReference, reconciliationReference
result, reasonCode, occurredAt, correlationId
```

Không ghi token recovery, password hash, secret MFA hoặc toàn bộ danh sách quyền nhạy cảm vào log chung. Tham chiếu snapshot và revision thường phù hợp hơn việc nhân bản mọi ACL vào các hệ thống quan sát có phạm vi đọc rộng.

Các thay đổi authorization thực sự, nếu cần để xử lý sự cố, phải có sự kiện riêng thể hiện ai cho phép và lý do. Đừng ghi tất cả dưới một nhãn “user recovered” làm mất khả năng phân biệt reset credential với sửa role.

Thông báo cho người dùng nên mô tả thay đổi xác thực và những hạn chế còn áp dụng ở mức thông tin phù hợp. Nó không cần liệt kê cấu trúc quyền nội bộ hoặc tài nguyên mà người nhận chưa được phép xem. Bản thân thông báo gửi thành công không chứng minh authorization đã được bảo toàn.

## 14. Ví dụ xuyên suốt: mất MFA trong lúc quyền đang thay đổi

Mai có principal cố định, là thành viên workspace A, sở hữu một tài liệu và có role `APPROVER` tạm đến hết ngày. Mai mất thiết bị MFA, mở recovery case và được đưa vào chế độ hạn chế truy cập nghiệp vụ.

Hệ thống giữ nguyên membership, ownership và bản ghi grant. Nó cho phiên recovery thực hiện các capability cần thiết để đăng ký factor mới, đồng thời không coi phiên này là phiên ứng dụng đầy đủ.

Trong khi hồ sơ đang xử lý, quản trị viên thu hồi quyền sửa một dự án của Mai vì thay đổi nhiệm vụ. Quyền `APPROVER` tạm cũng hết hạn theo lịch ban đầu. Các thay đổi này được ghi nhận ở nguồn authorization và làm mới revision tương ứng.

Sau khi bằng chứng được chấp nhận và factor mới được kiểm chứng, recovery cập nhật credential của chính principal đó, xử lý phiên cũ và gỡ đúng restriction thuộc hồ sơ nếu đủ điều kiện. Nó không chép role từ snapshot lúc mở case.

Khi Mai đăng nhập lại, tài liệu vẫn thuộc về Mai và membership hợp lệ vẫn còn. Quyền sửa đã thu hồi không quay lại; quyền tạm đã hết hạn cũng không được gia hạn. Nếu có security hold riêng từ hệ thống sự cố, hold vẫn tiếp tục được kiểm tra.

Đây là kết quả bảo toàn đúng: không mất liên kết dữ liệu vì đổi factor, không cấp thêm quyền vì recovery và không làm vô hiệu các quyết định phân quyền hợp lệ xảy ra trong khoảng xử lý.

## 15. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng thiết kế |
| --- | --- | --- |
| Xóa và tạo lại user khi reset MFA | Mất ownership, grant hoặc membership | Giữ principal ổn định, thay credential |
| Sao chép snapshot quyền khi hoàn tất | Hồi sinh quyền đã thu hồi hoặc hết hạn | Giữ nguồn chuẩn hiện hành và đối chiếu thay đổi |
| Xóa role để hạn chế recovery | Khó khôi phục đúng và dễ mất lịch sử | Dùng restriction riêng có điều kiện gỡ rõ ràng |
| Cấp token mới từ role claim của token cũ | Giữ quyền lỗi thời | Đánh giá lại quyền từ trạng thái hiện hành |
| Dùng email để nối lại owner | Chuyển nhầm tài nguyên khi email đổi hoặc tái sử dụng | Dùng định danh chủ thể nội bộ ổn định |
| Recovery tự xóa mọi security hold | Bỏ qua điều kiện bảo vệ do sự cố | Gỡ riêng restriction được phép, giữ các hold khác |
| Kéo dài grant tạm theo thời điểm recovery | Cấp quyền lâu hơn quyết định ban đầu | Giữ thời hạn và điều kiện ban đầu |
| Tăng version nhưng verifier không kiểm tra | Phiên và cache cũ vẫn có hiệu lực | Cưỡng chế invalidation hoặc kiểm tra trạng thái thật |
| Cho DTO recovery sửa role hoặc tenant | Tự nâng quyền hoặc vượt tenant | Whitelist trường và phân tách workflow ghi |

Bảo toàn dữ liệu phân quyền trong account recovery là giữ đúng chủ thể, nguồn thẩm quyền, phạm vi và lịch sử của quyền truy cập. Credential có thể được thay thế, phiên có thể bị thu hồi và restriction có thể thay đổi, nhưng những thay đổi đó phải có ý nghĩa riêng và không âm thầm viết lại quyền của người dùng.
