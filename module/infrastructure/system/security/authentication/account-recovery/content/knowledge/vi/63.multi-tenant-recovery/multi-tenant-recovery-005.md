# Tenant support boundaries trong khôi phục tài khoản

## 1. Vì sao hỗ trợ khôi phục cần ranh giới tenant rõ ràng?

Trong một nền tảng nhiều tenant, nhân viên hỗ trợ của một tổ chức có thể cần giúp người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Quyền hỗ trợ này không nên trở thành quyền truy cập hoặc thay đổi tài khoản của tổ chức khác.

**Tenant support boundaries** là những giới hạn về chủ thể, tài nguyên, hành động, dữ liệu và thời gian mà bộ phận hỗ trợ được phép sử dụng khi xử lý khôi phục. Ranh giới phải được thực thi ở máy chủ và các hệ thống phụ thuộc, không chỉ bằng cách ẩn nút trên giao diện.

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, hỗ trợ tenant cần phối hợp với xác minh danh tính, đánh giá rủi ro, token dùng một lần, chống lạm dụng và kiểm soát phiên. Vai trò hỗ trợ cho phép thực hiện một số nhiệm vụ, nhưng không tự chứng minh người liên hệ là chủ tài khoản và không tự cho phép bỏ qua các cổng khôi phục.

Ví dụ, tenant A là một doanh nghiệp và tenant B là một trường học. Linh có thể là thành viên của cả hai. Nhân viên hỗ trợ của A được giúp Linh truy cập tài nguyên của A trong phạm vi được cấp. Điều đó không mặc nhiên cho phép người này thay mật khẩu của một danh tính dùng chung rồi kiểm soát cả quyền truy cập của Linh ở B.

Một điều kiện cấp quyền đầy đủ cần xét nhiều yếu tố:

```text
Cho phép hành động hỗ trợ =
    danh tính nhân viên hợp lệ
    AND được phân công đúng tenant và hồ sơ
    AND có quyền đối với đúng tài khoản, loại tài nguyên và hành động
    AND bằng chứng người yêu cầu đạt policy
    AND các điều kiện rủi ro, phê duyệt và thời hạn còn hiệu lực
    AND tác dụng phụ không vượt phạm vi được cho phép
```

## 2. Phân biệt tenant, thành viên và chủ thể xác thực

Một nhầm lẫn phổ biến là coi mọi tài khoản xuất hiện trong danh sách thành viên của tenant đều có thông tin xác thực thuộc quyền quản trị của tenant đó. Kiến trúc thực tế có thể khác nhau.

| Mô hình | Phạm vi xác thực | Hệ quả đối với hỗ trợ |
| --- | --- | --- |
| Tài khoản riêng cho từng tenant | Thông tin xác thực được gắn với tenant cụ thể | Có thể cấp quyền xử lý cục bộ nếu policy cho phép |
| Danh tính toàn nền tảng, nhiều membership | Một principal dùng để truy cập nhiều tenant | Tenant admin không tự có quyền đặt lại thông tin xác thực toàn cục |
| Danh tính do tổ chức liên kết quản lý | Xác thực được thực hiện bởi nhà cung cấp danh tính có thẩm quyền | Hỗ trợ phải tôn trọng ranh giới nguồn danh tính và cấu hình liên kết |
| Tài khoản khách hoặc cộng tác viên | Thành viên tenant nhưng chủ thể có thể thuộc tổ chức khác | Quyền quản lý membership không đồng nghĩa quyền kiểm soát danh tính gốc |

Do đó, cần mô hình hóa riêng:

```text
Principal: danh tính được xác thực.
Membership: quan hệ của principal với một tenant.
Authentication authority: nơi có thẩm quyền quản lý phương thức xác thực.
Tenant resource: dữ liệu hoặc quyền nằm trong tenant.
```

Account ID ổn định và tenant ID giúp định danh đúng đích. Email hoặc tên hiển thị không đủ để quyết định quyền hỗ trợ. Hai tài khoản cùng email có thể khác nguồn danh tính; một principal duy nhất cũng có thể có nhiều membership với quyền khác nhau.

Policy hỗ trợ phải nêu rõ phạm vi tác dụng của từng hành động. “Mở khóa thành viên trong tenant A” khác với “mở khóa principal toàn nền tảng”. Nếu giao diện dùng cùng một nhãn “unlock account” cho cả hai, người vận hành có thể thực hiện một thay đổi lớn hơn họ hiểu.

## 3. Ma trận trách nhiệm giữa các nhóm hỗ trợ

Không nên chỉ có một quyền `SUPPORT_ADMIN` bao trùm mọi việc. Phân tách theo trách nhiệm giúp giảm khả năng một người đơn lẻ thay đổi toàn bộ chuỗi khôi phục.

| Chủ thể | Ví dụ phạm vi hợp lệ theo policy | Không được mặc nhiên suy ra |
| --- | --- | --- |
| Người dùng tự phục vụ | Chứng minh quyền với tài khoản và sử dụng luồng khôi phục được cấp | Được chọn lại tài khoản đích sau khi có token |
| Hỗ trợ tenant | Tiếp nhận hồ sơ, hướng dẫn, xử lý tác vụ cục bộ được phân quyền | Được đọc dữ liệu tenant khác hoặc reset danh tính toàn cục |
| Quản trị viên an ninh tenant | Xem tín hiệu và phê duyệt hành động trong tenant theo nhiệm vụ | Được gỡ mọi yếu tố của principal dùng chung |
| Hỗ trợ nền tảng | Xử lý phạm vi được nền tảng ủy quyền với kiểm soát đặc quyền | Có thể bỏ qua xác minh danh tính hoặc xóa audit |
| Nhà cung cấp dịch vụ hỗ trợ bên ngoài | Tác vụ và dữ liệu tối thiểu trong phạm vi hợp đồng, phân công | Được dùng chung tài khoản quản trị hoặc xuất toàn bộ hồ sơ |

Nhân viên hỗ trợ nền tảng có thể có khả năng kỹ thuật rộng, nhưng mỗi lần sử dụng vẫn cần mục đích, quyền hiện hành, phạm vi tài khoản và truy vết. “Là nhân viên của nền tảng” không phải một bằng chứng cấp quyền vô hạn.

Với hành động nhạy cảm, có thể yêu cầu quyền tạm thời, xác thực tăng cường, phê duyệt độc lập hoặc giới hạn theo hồ sơ đang xử lý. Khi quyền hết hạn hoặc người đó chuyển nhiệm vụ, các phiên hỗ trợ và khả năng tiếp tục thực thi phải được đánh giá lại.

## 4. Thiết lập ngữ cảnh tenant từ nguồn đáng tin cậy

Tenant ID có thể xuất hiện ở URL, header, biểu mẫu, token và dữ liệu hồ sơ. Các giá trị này có thể mâu thuẫn. Máy chủ phải xác định ngữ cảnh có thẩm quyền và kiểm tra quan hệ giữa chúng.

Một luồng hợp lệ có thể là:

1. Xác thực nhân viên hỗ trợ và nạp các phân công hiện tại.
2. Cho phép chọn một tenant trong phạm vi thực sự được cấp.
3. Nạp hồ sơ hỗ trợ với tenant và tài khoản đích từ nguồn máy chủ.
4. Kiểm tra hành động trên tài nguyên cùng tenant hoặc phạm vi được ủy quyền rõ ràng.
5. Gắn mọi quyết định và tác vụ tiếp theo với ngữ cảnh đã kiểm tra.

Việc nhân viên chọn tenant trong giao diện chỉ thể hiện ý định làm việc, không tự tạo quyền. Nếu sửa URL từ A sang B, máy chủ vẫn phải từ chối khi không có phân công tương ứng.

Không dùng tenant mặc định làm phương án dự phòng khi thiếu hoặc sai ngữ cảnh. Một endpoint quên truyền tenant xuống repository có thể truy vấn đúng account ID nhưng thuộc phạm vi khác hoặc bỏ mất một điều kiện bảo mật quan trọng.

Ngữ cảnh tenant cũng phải được truyền rõ qua queue, lịch tác vụ và cuộc gọi giữa dịch vụ. Trong xử lý bất đồng bộ, không dựa vào biến thread-local còn sót lại từ yêu cầu trước. Một worker dùng lại thread không được kế thừa tenant của tác vụ khác.

Tên miền tùy chỉnh giúp định tuyến và trải nghiệm, nhưng không thay thế phân quyền. Cần ánh xạ tên miền đã được xác minh tới tenant đúng. Không dùng giá trị `Host` hay địa chỉ chuyển hướng do client cung cấp để tự tạo đích gửi token hoặc xác lập quyền hỗ trợ.

## 5. Kiểm tra quyền theo hành động và phạm vi tác dụng

Một quyết định hỗ trợ nên xét cả vai trò lẫn ngữ cảnh: người thực hiện, tenant được phân công, tài khoản đích, quyền sở hữu thông tin xác thực, loại hành động, trạng thái hồ sơ và các điều kiện hiện tại.

Ví dụ các hành động khác nhau cần quyền khác nhau:

- Xem tiến độ hồ sơ khôi phục.
- Yêu cầu người dùng cung cấp thêm bằng chứng qua kênh hợp lệ.
- Xem kết quả xác minh hoặc truy cập một phần bằng chứng.
- Phê duyệt đề xuất khôi phục trong tenant.
- Thu hồi phiên chỉ thuộc tenant, nếu kiến trúc có phạm vi đó.
- Đặt lại thông tin xác thực do tenant quản lý.
- Đề nghị chuyển hồ sơ tới nhóm có thẩm quyền toàn nền tảng.

Không lấy quyền xem ticket làm quyền xem giấy tờ hoặc quyền reset. Một người được phép hướng dẫn người dùng không nhất thiết cần đọc các chi tiết danh tính nhạy cảm.

### Trường hợp danh tính dùng chung

Nếu mật khẩu hoặc yếu tố MFA thuộc principal toàn nền tảng, thay đổi nó có thể ảnh hưởng mọi membership. Tenant A không được dùng một quyền “reset của A” để tác động toàn cục.

Cách xử lý có thể là đưa người dùng tới luồng tự phục vụ của chủ thể xác thực hoặc chuyển cho nhóm có thẩm quyền phù hợp. Việc chuyển nhóm không tự động chấp thuận hành động; nhóm nhận vẫn phải xác minh bằng chứng và policy của phạm vi rộng hơn.

Tương tự, thu hồi “phiên của A” chỉ có nghĩa cục bộ nếu kiến trúc phiên thực sự phân biệt theo tenant. Nếu một phiên dùng chung cho toàn nền tảng, phải mô tả tác dụng toàn cục và yêu cầu quyền tương ứng. Không đặt tên tham số `tenantId` rồi mặc định hành động đã bị giới hạn.

## 6. Ràng buộc hồ sơ, phê duyệt và quyền thực thi

Hồ sơ hỗ trợ cần xác định chính xác ai đang yêu cầu khôi phục, tài khoản nào, tenant nào và loại hành động nào được xem xét. Một ghi chú tự do “đã được admin đồng ý” không phải quyền thực thi có thể kiểm tra.

Một mô hình dữ liệu khái niệm:

```text
SupportCase
  case_id, tenant_id, target_account_id
  requester_reference, assigned_team, state

SupportRecoveryProposal
  case_id, proposal_version, proposal_digest
  authentication_authority, allowed_actions
  evidence_reference, risk_reference, policy_version

SupportExecutionGrant
  grant_id, case_id, tenant_id, target_account_id
  proposal_version, proposal_digest, allowed_actions
  actor_or_executor_scope, expires_at, consumption_state
```

Nếu thay tài khoản đích, tenant, nguồn quản lý xác thực hoặc phạm vi hành động, cần một đề xuất mới và xem lại các quyết định bị ảnh hưởng. Không duyệt reset cho một tài khoản rồi sử dụng cùng phiếu để reset tài khoản khác.

Quyền thực thi nên ngắn hạn và có phạm vi nhỏ. Nó phải được kiểm tra lại trước tác dụng cuối cùng, bao gồm quyền hiện tại của người hỗ trợ, trạng thái hồ sơ, bằng chứng, rủi ro và phê duyệt bắt buộc. Vai trò đã hợp lệ lúc mở ticket có thể đã bị thu hồi trước khi thực thi.

Việc kiểm tra và tiêu thụ quyền dùng một lần cần nhất quán với hành động. Không trả `authorized=true` cho client rồi cho phép client gọi một API quản trị rộng hơn bằng dữ liệu đích tự chọn. Dịch vụ thực thi phải tự xác minh ràng buộc và chỉ áp dụng kế hoạch đã được chấp nhận.

## 7. Ví dụ Java: giới hạn reset vào thông tin xác thực cục bộ

Ví dụ dưới minh họa riêng việc đối chiếu phạm vi của một grant với tài nguyên. Các giá trị phải được nạp từ nguồn đã được máy chủ xác minh, không từ một DTO mà client tự nhận có quyền.

```java
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

enum AuthenticationAuthority {
    TENANT_LOCAL,
    PLATFORM_GLOBAL,
    EXTERNAL_IDENTITY_PROVIDER
}

enum SupportAction {
    RESET_TENANT_PASSWORD
}

record RecoveryTarget(
        UUID tenantId,
        UUID accountId,
        AuthenticationAuthority authority) {
}

record TenantSupportGrant(
        UUID actorId,
        UUID caseId,
        UUID tenantId,
        UUID targetAccountId,
        Set<SupportAction> allowedActions,
        Instant expiresAt) {
}

final class TenantPasswordResetBoundary {
    static boolean matchesScope(
            UUID currentActorId,
            UUID currentCaseId,
            TenantSupportGrant grant,
            RecoveryTarget target,
            Instant trustedNow) {

        if (currentActorId == null || currentCaseId == null
                || grant == null || target == null || trustedNow == null
                || target.tenantId() == null || target.accountId() == null
                || grant.allowedActions() == null
                || grant.expiresAt() == null) {
            return false;
        }

        return currentActorId.equals(grant.actorId())
                && currentCaseId.equals(grant.caseId())
                && target.tenantId().equals(grant.tenantId())
                && target.accountId().equals(grant.targetAccountId())
                && target.authority() == AuthenticationAuthority.TENANT_LOCAL
                && grant.allowedActions().contains(
                        SupportAction.RESET_TENANT_PASSWORD)
                && trustedNow.isBefore(grant.expiresAt());
    }
}
```

Một grant cho tenant A không khớp tài khoản cục bộ của B. Một tài khoản có authority là `PLATFORM_GLOBAL` hoặc `EXTERNAL_IDENTITY_PROVIDER` cũng bị loại khỏi thao tác reset cục bộ, dù người dùng xuất hiện trong danh sách thành viên của A.

Kết quả `true` chỉ xác nhận phần ràng buộc được minh họa. Nó chưa kiểm tra trạng thái grant đã dùng hay bị thu hồi, phân công hiện tại, xác thực tăng cường, quyền người hỗ trợ, phiên bản đề xuất, bằng chứng hoặc rủi ro. Cổng thực thi phải kiểm tra đầy đủ các điều kiện đó và có cơ chế đồng bộ phù hợp.

`currentActorId`, `currentCaseId` và `trustedNow` phải được xác lập phía máy chủ. `authority` phải đến từ cấu hình và dữ liệu có thẩm quyền, không phải một trường client được phép đổi từ `PLATFORM_GLOBAL` sang `TENANT_LOCAL` để làm kiểm tra thành công.

Một hệ thống có quyền reset toàn nền tảng cần contract và cổng quyền riêng. Không mở rộng ví dụ bằng cách bỏ kiểm tra tenant hoặc authority rồi tiếp tục gọi nó là thao tác hỗ trợ cục bộ.

## 8. Ranh giới dữ liệu phải đi hết chuỗi xử lý

Phân quyền ở controller là cần thiết nhưng chưa đủ. Repository, cache, kho tệp, export, queue và công cụ hỗ trợ đều có thể làm rò dữ liệu nếu bỏ ngữ cảnh tenant.

### Truy vấn và cache

Truy vấn hồ sơ cục bộ nên có điều kiện phạm vi tương ứng, chẳng hạn:

```sql
SELECT case_id, target_account_id, state
  FROM support_recovery_case
 WHERE tenant_id = :authorized_tenant_id
   AND case_id = :case_id;
```

`:authorized_tenant_id` là ngữ cảnh đã được máy chủ cấp quyền. Câu lệnh có tenant ID không tự an toàn nếu giá trị đó chỉ được sao chép nguyên từ client mà không kiểm tra.

Cache cũng cần khóa đủ phạm vi. Cache kết quả cấp quyền theo `actor_id` duy nhất có thể tái sử dụng quyết định của A khi người đó chuyển sang B. Khóa và vòng đời cache cần phản ánh hành động, tenant, tài nguyên và những phiên bản quyền có liên quan.

Cơ chế phân tách ở cơ sở dữ liệu, như schema riêng hoặc policy hàng, có thể tăng phòng vệ. Chúng vẫn cần cấu hình và ngữ cảnh đáng tin cậy. Nếu dùng kết nối dùng chung, phải bảo đảm ngữ cảnh cũ không rò sang yêu cầu khác; không xem một cơ chế phía dữ liệu là lý do bỏ kiểm tra ở tầng dịch vụ.

### Tệp và liên kết truy cập

Một tài liệu xác minh thuộc hồ sơ A không được đọc bằng cách đổi artifact ID sang một hồ sơ của B. Dịch vụ phải đối chiếu artifact với case, tenant và quyền người xem trước khi cấp khả năng truy cập.

URL khó đoán không thay thế phân quyền. Link ký cần phạm vi, thời hạn và cách cấp phù hợp; không gửi một link toàn quyền vào ticket mà mọi thành viên hỗ trợ đều đọc được. Không đưa token khôi phục, giấy tờ hoặc bí mật vào thông báo vận hành thông thường.

### Queue và cuộc gọi giữa dịch vụ

Thông điệp tác vụ cần có định danh tenant, case, tài khoản đích và hành động để bên nhận kiểm tra. Chỉ tin payload khi có nguồn phát và quyền gửi phù hợp; một dịch vụ nội bộ cũng có thể gửi sai phạm vi do lỗi hoặc bị chiếm.

Dịch vụ thực thi không nên trở thành **confused deputy**: một thành phần có quyền rộng bị người ít quyền yêu cầu làm việc ngoài phạm vi của họ. Nó phải kiểm tra grant và đối tượng, không chỉ thấy cuộc gọi đến từ mạng nội bộ rồi thực hiện reset.

## 9. Giới hạn xem dữ liệu, đại diện người dùng và xuất thông tin

Nhân viên hỗ trợ không cần biết mật khẩu, OTP, backup code hoặc token khôi phục đầy đủ để xử lý hồ sơ. Không yêu cầu người dùng đọc các bí mật đó qua điện thoại hoặc gửi vào chat.

Quyền xem bằng chứng cần theo nhu cầu công việc. Có thể một người chỉ cần thấy kết quả xác minh, trong khi nhóm chuyên trách mới được xem tài liệu nguồn. Tách quyền đọc, tải, xuất và thực thi để tránh một quyền xem ticket kéo theo khả năng sao chép hàng loạt dữ liệu nhạy cảm.

Không để giao diện hỗ trợ tự động liệt kê mọi membership của một principal dùng chung. Hỗ trợ A có thể cần biết người dùng thuộc A nhưng không cần biết họ đồng thời là thành viên của một tổ chức nhạy cảm ở B. Nguồn toàn cục có thể phục vụ quyết định phía máy chủ mà không phải hiển thị toàn bộ cho người hỗ trợ tenant.

Nếu sản phẩm có cơ chế đại diện hoặc impersonation, cơ chế đó cần quyền và policy riêng. Hỗ trợ khôi phục không mặc nhiên được đăng nhập như người dùng sau khi reset. Một khả năng đại diện hợp lệ phải có phạm vi tenant, thời hạn, giới hạn hành động và truy vết phù hợp; không tạo phiên người dùng toàn cục để phục vụ một ticket cục bộ.

Việc thu thập “ảnh chụp để dễ xử lý” cũng có thể vượt ranh giới. Hạn chế nội dung trong screenshot, export và log; không sao chép hồ sơ sang công cụ cá nhân hoặc kênh ngoài phạm vi được phép.

## 10. Chuyển tuyến và xử lý ngoại lệ

Khi quyền hỗ trợ hiện tại không đủ, kết quả đúng là chuyển tuyến theo quy trình có thẩm quyền hoặc giữ chờ, không mượn tài khoản quản trị của đồng nghiệp.

Một handoff nên truyền các tham chiếu và kết quả cần thiết: case ID, phạm vi đã xác minh, loại hành động cần xem xét, policy và lý do chuyển. Nhóm nhận truy cập bằng quyền của chính họ. Không gửi mật khẩu, token hoặc toàn bộ hồ sơ thô chỉ để chứng minh rằng nhóm trước đã làm việc.

Nhóm nền tảng nhận một hồ sơ từ tenant A vẫn phải kiểm tra yêu cầu có thuộc danh tính toàn cục, có ảnh hưởng tenant khác và bằng chứng cần bổ sung hay không. Phê duyệt cục bộ của A không tự trở thành phê duyệt thay đổi toàn nền tảng.

Với người hỗ trợ bên ngoài hoặc phiên hỗ trợ từ xa, cần giới hạn quyền theo nhiệm vụ và thời gian, dùng danh tính cá nhân có thể truy trách nhiệm và kết thúc quyền khi nhiệm vụ xong. Một tài khoản dùng chung làm khó việc xác định ai đã xem hoặc thay đổi thông tin.

### Trường hợp khẩn cấp

Quy trình khẩn cấp cần được thiết kế trước: người có thẩm quyền, loại sự cố, phạm vi tài nguyên, phê duyệt cần thiết, thời hạn và cách theo dõi. Không có một cờ `emergency=true` do nhân viên tự chọn để bỏ mọi kiểm tra tenant.

Nếu không thể xác minh ngữ cảnh hoặc nguồn quyền đang lỗi, không tự chuyển sang tenant mặc định hoặc quyền nền tảng. Giữ tác vụ ở trạng thái phù hợp và dùng tuyến dự phòng đã được cho phép. Áp lực “khách VIP cần vào ngay” không chứng minh quyền với tài khoản.

## 11. Thông báo, chống dò tìm và nhật ký

Thông báo cần được định tuyến từ nguồn quản trị đúng tenant và mục đích. Người yêu cầu không được chọn một địa chỉ `tenantAdminEmail` tùy ý để nhận quyền phê duyệt hoặc chi tiết hồ sơ.

Nếu hành động ảnh hưởng danh tính toàn cục, policy có thể yêu cầu thông báo hoặc xử lý ở phạm vi nền tảng. Không gửi dữ liệu của B cho quản trị viên A chỉ để giải thích rằng hành động có ảnh hưởng rộng hơn. Có thể nêu lý do ở mức cần thiết rồi chuyển đúng nhóm.

Phản hồi công khai cần tránh trở thành công cụ dò tài khoản hoặc cơ cấu tổ chức. Với nhân viên đã xác thực, thông tin được trả vẫn phải theo quyền: không tiết lộ tài khoản có tồn tại ở tenant khác, cấu hình MFA của người ngoài phạm vi hoặc địa chỉ liên hệ của nhóm không liên quan.

Các thông điệp từ chối có thể dùng cách diễn đạt không phân biệt quá mức giữa tài nguyên không tồn tại và tài nguyên không được phép truy cập, tùy bề mặt và contract. Chi tiết điều tra phù hợp được lưu cho người có quyền, không trả tất cả cho người gọi.

Giới hạn tốc độ theo danh tính hỗ trợ, tenant, tài khoản đích và hành vi phù hợp giúp phát hiện dò tìm hoặc lạm dụng. Không để một tenant gây tải làm mọi luồng khôi phục của tenant khác mất khả dụng; cách phân bổ tài nguyên cần xét phạm vi và mức ưu tiên.

Nhật ký nên giữ đủ ngữ cảnh để phân biệt:

```text
actor_principal_id
actor_assignment_reference
acting_tenant_id
target_account_id
authentication_authority
support_case_id
proposal_version, grant_reference
requested_action, effective_scope
policy_version, authorization_outcome
execution_id, outcome, occurred_at
```

`acting_tenant_id` là phạm vi người đó đang làm việc; authority và effective scope cho biết hành động thật sự tác động ở đâu. Chỉ ghi một `tenant_id` mơ hồ có thể làm mất sự khác biệt quan trọng này.

Ghi cả các lần bị từ chối do sai tenant, sai account, authority không phù hợp, quyền hết hạn hoặc cố phát lại grant. Không ghi token đầy đủ, mật khẩu, mã xác thực hoặc giấy tờ thô. Những người hỗ trợ tenant chỉ được xem phần nhật ký họ có quyền; log tập trung cũng cần phân quyền, không phải nơi mọi tenant đều đọc được dữ liệu lẫn nhau.

## 12. Những thiết kế dễ vượt ranh giới

| Thiết kế | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Kiểm tra vai trò SUPPORT rồi reset theo account ID | Quyền hỗ trợ không được ràng buộc phạm vi | Kiểm tra tenant, tài khoản, action và authority |
| Chỉ lọc tenant trên giao diện | API vẫn có thể được gọi trực tiếp | Thực thi ở máy chủ và nơi truy cập dữ liệu |
| Reset principal chung bằng quyền tenant | Ảnh hưởng quyền truy cập tenant khác | Chuyển luồng có thẩm quyền toàn cục |
| Cache quyền theo người, thiếu tenant và action | Quyết định của phạm vi trước bị tái sử dụng | Thiết kế khóa và hiệu lực cache theo ngữ cảnh |
| Worker dùng tenant còn sót trong thread | Tác vụ của A chạy dưới ngữ cảnh B | Truyền và kiểm tra tenant rõ ràng cho từng tác vụ |
| Hỗ trợ đọc token rồi đưa cho người dùng | Nhân viên có thể chiếm tài khoản sau kiểm tra | Giao bí mật qua luồng cho người dùng được phép |
| Link hồ sơ tự cấp quyền khi mở | Link bị chuyển tiếp gây lộ dữ liệu hoặc thực thi | Xác thực, phân quyền và giới hạn hành động ở đích |
| Coi phê duyệt tenant là quyền toàn nền tảng | Bỏ qua phạm vi và bằng chứng của chủ thể toàn cục | Cổng quyết định riêng khi mở rộng tác dụng |
| Đặt tenant mặc định khi thiếu ngữ cảnh | Sai đối tượng mà vẫn có thể thành công | Từ chối hoặc giữ chờ để xác lập đúng phạm vi |

## 13. Tình huống xuyên suốt

Linh dùng một principal toàn nền tảng và là thành viên của tenant A cùng tenant B. Linh mất điện thoại chứa MFA và liên hệ nhân viên hỗ trợ của A.

Nhân viên được phân công vào hồ sơ của A có thể xem tiến độ liên quan và hướng dẫn Linh tới luồng khôi phục chính thức. Máy chủ không hiển thị mọi membership của Linh và không cấp quyền đọc dữ liệu của B.

Khi nhân viên chọn “reset MFA”, dịch vụ xác định MFA thuộc principal toàn cục. Quyền cục bộ của A không đủ để gỡ nó. Hồ sơ được chuyển theo tuyến nền tảng với những tham chiếu và kết quả cần thiết; nhân viên không gửi token hoặc giấy tờ qua kênh cá nhân.

Nhóm có thẩm quyền toàn cục xác minh người yêu cầu, đánh giá rủi ro và áp dụng policy phù hợp trước khi tạo kế hoạch khôi phục. Họ không chỉ dựa vào việc quản trị viên A đã nói “đồng ý”. Grant thực thi gắn với tài khoản, đề xuất và phạm vi đã được chấp nhận.

Trong một trường hợp khác, tenant A có tài khoản cục bộ với thông tin xác thực riêng. Một grant có thể cho phép xử lý tài khoản đó nếu mọi điều kiện đạt. Khi client sửa tenant hoặc account ID sang B, đối chiếu phạm vi thất bại. Nếu quyền nhân viên hết hiệu lực trước bước cuối, máy chủ cũng không tiếp tục chỉ vì ticket từng được mở hợp lệ.

Tác vụ bất đồng bộ mang ngữ cảnh rõ ràng và dịch vụ nhận kiểm tra lại quyền thực thi. Thông báo đi tới người nhận thuộc phạm vi cần biết; nhật ký thể hiện ai xử lý, nhân danh tenant nào và tác động thực tế ở phạm vi nào.

Ranh giới hỗ trợ tenant có giá trị khi nó giới hạn được cả quyết định lẫn tác dụng phụ. Một nhân viên có thể giúp người dùng lấy lại khả năng truy cập trong phạm vi được giao mà không trở thành một đường vòng để kiểm soát danh tính hoặc dữ liệu của tenant khác.
