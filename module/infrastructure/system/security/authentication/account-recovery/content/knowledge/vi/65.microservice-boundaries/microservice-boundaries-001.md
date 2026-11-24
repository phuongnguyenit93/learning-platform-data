# Identity service responsibility: trách nhiệm của dịch vụ định danh trong account recovery

## 1. Identity service phải giữ ranh giới nào?

Một yêu cầu “khôi phục tài khoản” có thể liên quan hỗ trợ khách hàng, xác minh danh tính, đánh giá rủi ro, thay mật khẩu, đăng ký lại MFA, thu hồi phiên và gửi thông báo. Nếu mọi dịch vụ đều có thể sửa bảng user hoặc tự đánh dấu người dùng đã xác thực, hệ thống không còn một nguồn đáng tin để xác định credential nào đang hợp lệ.

**Identity service** là miền chịu trách nhiệm về danh tính đăng nhập và trạng thái xác thực theo kiến trúc của sản phẩm. Trong recovery, nhiệm vụ cốt lõi của nó là bảo đảm credential được thay đổi cho đúng chủ thể, bằng đúng quyền hạn và theo các bất biến xác thực mà nó có thẩm quyền thực thi.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, recovery phục vụ người mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Identity service phải phối hợp với xác minh danh tính, đánh giá rủi ro, token dùng một lần, chống lạm dụng và kiểm soát phiên, nhưng không vì thế trở thành nơi sở hữu toàn bộ nghiệp vụ của hệ thống.

Ranh giới tốt trả lời được ba câu hỏi: dữ liệu nào chỉ identity service được sửa, quyết định nào nó phải kiểm tra tại thời điểm áp dụng và những kết quả nào phải được chuyển tới dịch vụ khác bằng hợp đồng rõ ràng?

## 2. Phân biệt danh tính, credential và quyền truy cập

Ba khái niệm này liên quan nhưng không đồng nhất:

- **Principal hoặc account:** chủ thể nội bộ ổn định mà hệ thống nhận diện.
- **Credential và factor:** phương tiện dùng để chứng minh quyền kiểm soát chủ thể, như mật khẩu, TOTP hoặc khóa công khai.
- **Authorization:** quyền thực hiện hành động trên tài nguyên, như đọc tài liệu hoặc quản trị workspace.

Thay factor không nên tạo principal mới. Khôi phục credential cũng không tự cấp lại role đã bị thu hồi hoặc chuyển quyền sở hữu tài nguyên theo email mới.

Ví dụ:

```text
principal_42
  ├── Identity: liên kết đăng nhập và credential
  ├── Organization: membership tenant A
  ├── Authorization: quyền EDITOR trên project X
  └── Application: tài liệu và dữ liệu nghiệp vụ
```

Trong một thiết kế, identity service có thể lưu một số thuộc tính hỗ trợ authorization, nhưng cần chỉ rõ nó là nguồn chuẩn hay chỉ là bản sao. Một claim role trong token không biến identity service thành chủ sở hữu của mọi quyết định phân quyền.

## 3. Những dữ liệu identity service thường có thẩm quyền

Phạm vi cụ thể phụ thuộc kiến trúc, nhưng cần được xác định thành một hợp đồng thay vì để từng dịch vụ tự suy diễn.

| Dữ liệu hoặc trạng thái | Trách nhiệm điển hình của identity service |
| --- | --- |
| Principal ID và liên kết account | Giữ định danh ổn định và các quan hệ đăng nhập có thẩm quyền |
| Credential cục bộ | Tạo, kiểm chứng, thay thế hoặc thu hồi theo chính sách |
| Factor và enrollment | Quản lý trạng thái chờ đăng ký, đã kiểm chứng, đình chỉ hoặc thu hồi |
| Liên kết provider | Ánh xạ subject bên ngoài tới đúng principal trong phạm vi cấu hình tin cậy |
| Authentication epoch hoặc revision | Thể hiện thay đổi có thể làm phiên xác thực cũ mất hiệu lực |
| Trạng thái cho phép xác thực | Áp dụng cổng liên quan tới đăng nhập và recovery trong phạm vi mình |
| Kênh recovery được tin cậy | Quản lý liên kết và trạng thái xác minh nếu đây là nguồn chuẩn của sản phẩm |
| Kết quả operation thay credential | Ghi kết quả bền vững phục vụ retry và đối soát |

Không phải mọi thuộc tính hồ sơ đều thuộc miền identity. Tên hiển thị hoặc địa chỉ nhận hóa đơn có thể do dịch vụ hồ sơ hay nghiệp vụ khác quản lý. Đặc biệt, một email dùng để nhận thông báo không mặc nhiên là kênh được phép dùng để reset mật khẩu.

Các trường `emailVerified` hoặc `phoneVerified` cần gắn với đúng giá trị và ngữ nghĩa xác minh. Không sao chép một cờ verified từ bản cập nhật hồ sơ rồi coi đó là bằng chứng cho phép recovery.

## 4. Những trách nhiệm cần phân biệt với các miền khác

Một phân công minh họa:

| Miền | Trách nhiệm chính trong recovery | Điều không nên tự làm |
| --- | --- | --- |
| Recovery coordinator | Quản lý case, tiến độ, điều kiện và operation | Sửa trực tiếp credential store |
| Identity service | Áp dụng thay đổi xác thực có thẩm quyền | Tự cấp role nghiệp vụ hoặc sửa ownership |
| Identity proofing | Thực hiện phương thức chứng minh và cung cấp kết quả có phạm vi | Coi mọi kết quả là quyền reset mọi account |
| Risk service | Cung cấp tín hiệu hoặc quyết định rủi ro theo hợp đồng | Ghi đè credential bằng một điểm số |
| Authorization service | Quyết định quyền tài nguyên và security hold thuộc phạm vi nó | Suy ra factor mới đã hợp lệ từ role của người dùng |
| Session service | Quản lý phiên và token family nếu được tách riêng | Tự cho credential cũ hoạt động lại |
| Notification service | Gửi thông báo đã được cho phép và báo trạng thái bàn giao | Chọn account hoặc kênh recovery mới ngoài phạm vi lệnh |

Đây là ranh giới trách nhiệm, không phải yêu cầu triển khai từng dòng thành một microservice. Một ứng dụng theo module vẫn có thể giữ ranh giới dữ liệu và quyền ghi rõ ràng. Tách mạng nhưng dùng chung quyền sửa mọi bảng không tạo ra cách ly nghiệp vụ có ý nghĩa.

Nếu identity service cũng sở hữu phiên đăng nhập, nó có thể thực thi thu hồi phiên trong cùng miền. Nếu session được tách riêng, cần giao thức xác nhận hiệu lực; không giả định việc phát một event là mọi phiên cũ đã bị chặn.

## 5. Quyền sửa credential phải tập trung tại nguồn có thẩm quyền

Một lỗi ranh giới thường gặp là recovery service hoặc công cụ hỗ trợ cập nhật thẳng password hash, xóa factor hoặc đặt `mfaEnabled=false` trong database của identity. Những đường ghi đó có thể bỏ qua kiểm tra phiên bản, dùng một lần, audit và thu hồi phiên.

Identity service nên cung cấp các hành động có ngữ nghĩa cụ thể, chẳng hạn:

- Chuẩn bị một enrollment có phạm vi cho principal đã xác định.
- Kiểm chứng candidate factor theo loại credential.
- Áp dụng một operation thay credential đã được cho phép.
- Thu hồi credential được chỉ định.
- Trả kết quả operation để coordinator xử lý retry hoặc reconciliation.

Không nên cung cấp một API nội bộ kiểu `updateUser(anyFields)` rồi cho recovery gửi mọi thuộc tính. Một command thay factor không cần quyền sửa tenant, role, owner hoặc trạng thái xác minh của các kênh khác.

Credential mới cần đi qua đường xử lý bí mật phù hợp. Password plaintext, secret TOTP hoặc dữ liệu nhạy cảm của enrollment không nên được phát vào event bus chung. Coordinator có thể dùng tham chiếu candidate được bảo vệ; identity service vẫn kiểm tra candidate đó thuộc đúng principal, mục đích và operation.

Quyền database và service account nên phản ánh ranh giới này. Nếu một dịch vụ không có trách nhiệm sửa credential, nó không cần quyền ghi trực tiếp chỉ vì cùng thuộc nền tảng nội bộ.

## 6. Identity service không chỉ tin một cờ “đã xác minh”

Recovery coordinator có thể đã thực hiện các bước bằng chứng và phê duyệt. Tuy nhiên, identity service không nên chấp nhận request như sau chỉ vì đến từ mạng nội bộ:

```json
{
  "accountId": "account_example",
  "verified": true,
  "skipMfa": true,
  "resetAllFactors": true
}
```

Các boolean không giải thích ai xác minh, xác minh điều gì, quyền có hiệu lực tới khi nào hoặc có bị thu hồi không.

Một cơ chế cho phép recovery cần ràng buộc rõ:

```text
issuer và nguồn quyền được tin cậy
audience là dịch vụ được phép nhận
principal, tenant hoặc identity scope chính xác
purpose và loại thay đổi được phép
case, case version và operation ID
credential version hoặc fencing cần thiết
thời hạn, điều kiện sử dụng và khả năng thu hồi
tham chiếu bằng chứng hoặc phê duyệt theo chính sách
```

Cơ chế có thể là capability được bảo vệ, grant tham chiếu tra tại nguồn có thẩm quyền hoặc giao thức khác. Identity service cần xác thực nguồn và kiểm tra các ràng buộc liên quan tại ranh giới thay credential, không chỉ kiểm tra rằng một chuỗi token có chữ ký hợp lệ.

Danh tính service gọi API và quyền recovery là hai kiểm tra khác nhau. Một workload được xác thực không mặc nhiên có quyền thay credential của mọi principal. Tương tự, biết operation ID không phải quyền đọc toàn bộ case hoặc sử dụng candidate factor.

## 7. Principal toàn cục và tenant scope phải được mô hình hóa riêng

Trong tài khoản độc lập theo tenant, credential có thể thuộc một tenant account cụ thể. Trong mô hình principal dùng chung, cùng một credential có thể mở đường đăng nhập vào nhiều tổ chức.

Một tenant admin không mặc nhiên được reset credential toàn cục chỉ vì người dùng có membership trong tenant đó. Identity service cần hiểu phạm vi của credential và thẩm quyền mà grant cung cấp.

Những trường hợp cần phân biệt:

- Khôi phục credential riêng của tenant account.
- Thay liên kết IdP thuộc tenant.
- Khôi phục credential của principal toàn nền tảng.
- Gộp hoặc liên kết hai principal, vốn là một nghiệp vụ khác thay factor.

Scope phải được xác định từ dữ liệu có thẩm quyền, không chỉ từ header hoặc tenant được chọn trên giao diện. Nếu request nêu tenant A nhưng credential có phạm vi toàn cục, không thể coi việc gắn nhãn A là đã giới hạn tác động.

Identity service cũng cần tránh rò rỉ qua lookup. API công khai không nên xác nhận một email có tài khoản, có factor nào hoặc thuộc tenant nào ngoài phạm vi được cho phép. Luồng nội bộ có quyền tra cứu phải giữ mục đích và phạm vi rõ ràng.

## 8. Hợp đồng command và kết quả operation

Một command nội bộ minh họa có thể biểu diễn:

```yaml
operationId: recovery_operation_example
subjectReference: principal_example
identityScopeReference: tenant_account_scope_example
purpose: REPLACE_FACTOR
candidateCredentialReference: candidate_example
authorizationReference: recovery_grant_example
expectedCredentialVersion: 12
recoveryFence: 57
```

Đây là cấu trúc khái niệm, không phải một endpoint có sẵn. Các tham chiếu phải được phân giải và kiểm tra; chúng không tự mang quyền chỉ vì có mặt trong payload.

Kết quả cần phân biệt rõ:

| Kết quả | Ý nghĩa |
| --- | --- |
| Chưa được chấp nhận | Không có operation được áp dụng; lý do có thể là scope hoặc policy |
| Đang xử lý | Công việc đã được nhận nhưng kết quả cuối chưa xác định |
| Đã áp dụng | Credential change đã commit và có kết quả bền vững |
| Xung đột phiên bản | Trạng thái hiện tại không còn khớp điều kiện command |
| Cần đối soát | Caller chưa xác định được tác động hoặc còn phụ thuộc phải xác nhận |

Idempotency tại identity service cần gắn với operation và fingerprint của nội dung được phép. Cùng operation và cùng nội dung trả lại kết quả đã lưu; cùng operation nhưng đổi principal, candidate hoặc purpose phải bị từ chối.

Khi caller timeout, identity service có thể đã commit. Caller cần truy vấn hoặc retry cùng operation, không tạo một reset mới hoặc tự đánh dấu capability chưa dùng. Identity service phải giữ đủ kết quả để hai bên đối soát được trong khoảng thời gian chính sách yêu cầu.

## 9. Ví dụ Java: cổng kiểm tra trước khi commit recovery

Ví dụ dưới chọn mô hình account có scope rõ và kiểm tra một grant đã được xác thực trước đó. Nó chưa thực hiện transaction, kiểm chứng factor hoặc xác thực service gọi. Tên `VerifiedGrant` chỉ mô tả hợp đồng đầu vào; tạo một record từ request không biến request thành bằng chứng đáng tin.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class IdentityRecoveryCommitPolicy {
    public enum Purpose { REPLACE_PASSWORD, REPLACE_FACTOR }

    public record Subject(UUID scopeId, UUID principalId) {}

    public record CommitRequest(
            UUID operationId,
            Subject subject,
            Purpose purpose,
            UUID candidateReference,
            long expectedCredentialVersion,
            long recoveryFence) {}

    public record VerifiedGrant(
            UUID operationId,
            Subject subject,
            Purpose purpose,
            UUID candidateReference,
            String audience,
            long expectedCredentialVersion,
            long recoveryFence,
            Instant expiresAt) {}

    public record SecurityState(
            Subject subject,
            long credentialVersion,
            long recoveryFence,
            boolean localMutationAllowed) {}

    public record Decision(boolean allowed, String reason) {}

    public static Decision evaluate(
            CommitRequest request,
            VerifiedGrant grant,
            SecurityState current,
            String expectedAudience,
            Instant now) {
        Objects.requireNonNull(request);
        Objects.requireNonNull(grant);
        Objects.requireNonNull(current);
        Objects.requireNonNull(expectedAudience);
        Objects.requireNonNull(now);

        if (!expectedAudience.equals(grant.audience())
                || !request.operationId().equals(grant.operationId())
                || !request.subject().equals(grant.subject())
                || !request.subject().equals(current.subject())
                || request.purpose() != grant.purpose()
                || !request.candidateReference().equals(grant.candidateReference())) {
            return new Decision(false, "RECOVERY_SCOPE_MISMATCH");
        }
        if (grant.expiresAt() == null || !now.isBefore(grant.expiresAt())) {
            return new Decision(false, "RECOVERY_GRANT_EXPIRED");
        }
        if (!current.localMutationAllowed()) {
            return new Decision(false, "LOCAL_MUTATION_NOT_ALLOWED");
        }
        if (request.expectedCredentialVersion() != current.credentialVersion()
                || request.expectedCredentialVersion()
                        != grant.expectedCredentialVersion()
                || request.recoveryFence() != current.recoveryFence()
                || request.recoveryFence() != grant.recoveryFence()) {
            return new Decision(false, "STALE_RECOVERY_AUTHORIZATION");
        }
        return new Decision(true, "ELIGIBLE_FOR_ATOMIC_COMMIT");
    }
}
```

Các ID bắt buộc được giả định đã kiểm tra không rỗng và không null. Grant được tạo qua verifier có thẩm quyền, với kiểm tra nguồn, hiệu lực và quyền sử dụng phù hợp. `localMutationAllowed` là kết quả chính sách của identity service cho đúng loại credential và trạng thái hiện tại, không phải cờ client tự gửi.

Nếu kết quả cho phép, thao tác ghi vẫn phải kiểm chứng candidate đã hoàn tất enrollment và giữ điều kiện version hoặc fence tại thời điểm commit. Đọc state, gọi hàm rồi ghi không có kiểm soát đồng thời vẫn tạo lỗi giữa kiểm tra và sử dụng.

Operation đã commit cần được nhận diện và trả kết quả idempotent theo giao thức trước khi coi retry là một lần áp dụng mới. Hàm trên là cổng cho một commit chưa áp dụng, không phải toàn bộ triển khai retry.

## 10. Ranh giới transaction và sự kiện identity

Tại nơi có thẩm quyền với credential, một transaction có thể gồm:

```text
BEGIN TRANSACTION
  khóa hoặc kiểm tra phiên bản security state của principal
  tra operation đã áp dụng để xử lý retry
  kiểm tra grant, scope, fence và candidate
  thay credential hoặc factor được chỉ định
  cập nhật authentication epoch và restriction thuộc phạm vi identity
  ghi kết quả operation
  ghi audit hoặc outbox
COMMIT
```

Mọi đường ghi credential khác cần tuân thủ cùng cơ chế version hoặc khóa liên quan. Một API quản trị bỏ qua fence có thể phá vỡ bảo đảm của recovery dù đường recovery riêng được thiết kế đúng.

Event sau commit nên mô tả sự kiện xác thực đã xảy ra, chẳng hạn credential recovery đã được áp dụng cho operation nào và revision nào. Event không nên chứa secret, password hash hoặc một lệnh mơ hồ yêu cầu mọi consumer tự quyết định reset thêm.

Consumer cần xử lý message trùng và thứ tự theo hợp đồng. Coordinator có thể dùng event để cập nhật tiến độ, session service để xử lý phạm vi thu hồi, notification service để chuẩn bị thông báo. Không consumer nào được suy ra quyền sửa role hoặc ownership ngoài phạm vi của mình.

Nếu đổi epoch chỉ diễn ra tại identity database mà verifier ở dịch vụ khác không kiểm tra, epoch mới chưa tự làm token cũ mất hiệu lực. Ranh giới ownership cần đi kèm hợp đồng thực thi, không chỉ sự kiện đẹp về mặt schema.

## 11. Quan hệ với phiên, token và mức xác thực

Identity service cần định nghĩa rõ kết quả recovery có ý nghĩa gì với authentication context. Phê duyệt recovery không có nghĩa người dùng vừa sử dụng factor cũ thành công.

Không tự thêm claim như “đã vượt MFA” chỉ vì quản trị viên cho reset MFA. Factor mới phải được đăng ký và kiểm chứng theo loại phương thức. Một phiên recovery được phép enrollment không mặc nhiên là phiên ứng dụng đầy đủ.

Các tác động có thể cần hợp đồng riêng:

- Thu hồi hoặc yêu cầu xác thực lại các phiên đã cấp trước thay đổi.
- Xử lý refresh token family theo phạm vi rủi ro.
- Xóa trạng thái trusted device hoặc remembered MFA không còn phù hợp.
- Kết thúc capability và phiên recovery sau hoàn tất.
- Giữ restriction trước hành động nhạy cảm cho đến khi đạt điều kiện.

Nếu session service độc lập, cần xác định nguồn quyết định thu hồi, receipt hoặc cơ chế kiểm tra có thẩm quyền. Event được broker nhận chưa chứng minh mọi verifier đã từ chối phiên cũ.

Nếu chính sách chấp nhận một độ trễ thu hồi có giới hạn, cần cơ chế thực tế bảo đảm giới hạn đó. Không công bố tức thời chỉ vì identity service đã tăng một con số trong database.

## 12. Danh tính liên kết: biết giới hạn thẩm quyền của hệ thống local

Một credential có thể do nhà cung cấp danh tính bên ngoài quản lý. Identity service local thường có liên kết subject, cấu hình trust và trạng thái tài khoản local, nhưng không vì thế sở hữu mật khẩu upstream.

Nếu người dùng cần reset credential tại IdP, recovery phải được chuyển tới đường có thẩm quyền của provider hoặc tổ chức tương ứng. Không tạo mật khẩu local như một fallback ngầm để vượt qua chính sách đăng nhập doanh nghiệp.

Liên kết danh tính cần dựa trên định danh có thẩm quyền trong cấu hình tin cậy, chẳng hạn issuer và subject của một tích hợp OIDC trong namespace phù hợp. Cùng email hiển thị không đủ để tự liên kết một subject mới với principal cũ.

Một tài khoản liên kết có thể vẫn có một số factor local nếu sản phẩm hỗ trợ. Vì vậy, quyền thay credential cần xét từng loại và phạm vi, không gắn một nhãn federated rồi suy ra mọi thay đổi đều được phép hoặc đều bị cấm.

Thu hồi phiên local không mặc nhiên chấm dứt phiên SSO upstream. Nếu phiên upstream cũ có thể lập tức cấp lại quyền local, hợp đồng đăng nhập sau recovery phải xử lý điều đó theo chính sách; không coi logout một cookie là đã kết thúc mọi phiên.

## 13. Hợp tác với risk, proofing, authorization và notification

### Risk và identity proofing

Identity service cần hiểu kết quả được cấp cho chủ thể nào, mục đích nào, trong thời hạn nào và có bị thu hồi không. Nó không cần đọc mọi giấy tờ nếu một miền proofing chuyên biệt đã cung cấp kết quả có thẩm quyền đủ cho chính sách.

Điểm số rủi ro hoặc nhãn “verified” không tự là quyền thay credential. Quyết định chấp nhận recovery cần được chuyển thành một authorization có phạm vi, cùng các điều kiện mà identity service có thể thực thi.

### Authorization

Recovery credential không cấp thêm membership, không khôi phục role đã hết hạn và không xóa security hold do miền khác quản lý. Identity service có thể cần kiểm tra hold hoặc tín hiệu bắt buộc trước commit; giao thức hiệu lực phải đủ rõ để không dựa vào cache cũ khi chính sách yêu cầu trạng thái hiện hành.

### Notification

Identity service hoặc coordinator cung cấp sự kiện và tham chiếu kênh đã được phép sử dụng. Notification service không tự chọn email mới do người yêu cầu nhập rồi coi đó là địa chỉ recovery tin cậy.

Gửi thông báo thành công không chứng minh credential change hợp lệ. Gửi thất bại cũng không tự cho phép rollback về credential bị nghi xâm phạm. Nếu có điều kiện thông báo trước hoặc khoảng chờ, điều đó phải được mô hình hóa ở workflow.

## 14. Audit, quyền truy cập và xử lý lỗi tại ranh giới

Audit identity recovery cần nối được principal, scope, case, operation, actor, grant, credential revision và kết quả. Các sự kiện cần phân biệt yêu cầu bị từ chối, commit đã thành công và trạng thái chưa xác định ở caller.

Không ghi bí mật vào lỗi hoặc event để tiện hỗ trợ. Có thể dùng reason code như scope mismatch, stale version, grant expired hoặc candidate chưa đủ điều kiện, với mức chi tiết phù hợp người nhận. Endpoint công khai cần tránh tiết lộ trạng thái account ngoài phạm vi quyền.

Các quyền nội bộ cũng cần tối thiểu: đọc metadata identity, chuẩn bị candidate, áp dụng recovery và đọc audit không nhất thiết là cùng một quyền. Workload identity cần được kiểm tra theo audience và mục đích; mạng nội bộ hoặc mTLS không tự quyết định toàn bộ quyền nghiệp vụ.

Khi nguồn bắt buộc không sẵn sàng, hệ thống cần hành vi được định nghĩa: chờ, từ chối có thể retry hoặc giữ operation cần reconciliation. Không coi timeout từ risk, grant verifier hoặc session service là bằng chứng đủ để mở quyền.

Trong vận hành, cần nhìn thấy các operation đã đổi credential nhưng chưa đạt điều kiện hoàn tất toàn workflow. Identity service báo đúng phạm vi thành công của mình; coordinator không mở rộng ý nghĩa đó thành “mọi dịch vụ đã đồng bộ”.

## 15. Ví dụ xuyên suốt: thay MFA mà không sửa dữ liệu nghiệp vụ

Mai mất điện thoại TOTP. Recovery coordinator mở case, thu thập bằng chứng theo chính sách và nhận quyết định rủi ro cần thiết. Một authorization có phạm vi được cấp cho đúng principal, loại thay factor, candidate và operation O.

Mai thực hiện enrollment qua đường được identity service kiểm soát và hoàn tất kiểm chứng candidate. Coordinator yêu cầu áp dụng O bằng danh tính service có quyền. Identity service xác thực command, kiểm tra grant, version, fence, trạng thái tài khoản và candidate rồi commit thay factor.

Trong cùng miền transaction, identity ghi kết quả O, tăng epoch hoặc đặt restriction phù hợp và ghi audit hoặc outbox. Nó không sửa role, membership hoặc owner của các tài liệu của Mai.

Nếu phản hồi bị mất, coordinator truy vấn hoặc retry O. Identity trả lại kết quả đã lưu thay vì đổi factor lần nữa. Session service thực thi hợp đồng thu hồi, còn coordinator chờ các điều kiện bảo mật bắt buộc trước khi hoàn tất case. Notification service gửi thông báo theo kênh đã được cho phép.

Sau recovery, Mai vẫn là cùng principal. Quyền hiện hành tiếp tục do miền authorization quyết định; một role bị thu hồi trong lúc xử lý không tự quay lại. Nếu một phần credential của Mai do IdP bên ngoài quản lý, identity service chỉ thay phần nó có thẩm quyền và không tạo đường đăng nhập local để bỏ qua provider.

Ranh giới trách nhiệm của identity service được giữ khi nó là nguồn chuẩn cho những thay đổi xác thực mà mình sở hữu, kiểm tra quyền đúng tại thời điểm áp dụng và cung cấp kết quả có thể đối soát. Các dịch vụ khác phối hợp qua hợp đồng rõ ràng, thay vì chia sẻ quyền sửa mọi dữ liệu hoặc suy diễn rằng recovery thành công đồng nghĩa mọi quyền đã được khôi phục.
