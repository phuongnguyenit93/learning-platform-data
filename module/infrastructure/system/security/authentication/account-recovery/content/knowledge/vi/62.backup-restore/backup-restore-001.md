# Recovery data backup: sao lưu dữ liệu khôi phục tài khoản an toàn

## 1. Sao lưu recovery data khác sao lưu một bảng nghiệp vụ thông thường

Dịch vụ khôi phục tài khoản cần tồn tại ngay cả khi cơ sở dữ liệu bị hỏng, một vùng hạ tầng gián đoạn hoặc dữ liệu bị sửa trái phép. Nếu mất hồ sơ recovery và liên kết tới chủ tài khoản, hệ thống có thể không biết ai đã được xác minh, quyết định nào đã được phê duyệt và credential nào đã bị thu hồi.

Tuy nhiên, khôi phục một bản sao cũ cũng có thể tạo lỗ hổng. Token đã dùng có thể quay lại trạng thái chưa dùng; một hồ sơ bị từ chối có thể xuất hiện như đang được duyệt; mã dự phòng đã tiêu thụ có thể hoạt động trở lại. Vì vậy, **recovery data backup** phải bảo vệ cả khả năng phục hồi dữ liệu lẫn tính đúng đắn của trạng thái bảo mật sau khi phục hồi.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, dữ liệu này phục vụ khôi phục an toàn khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Bản sao lưu cần giữ được quan hệ với danh tính, bằng chứng, chính sách, kiểm soát lạm dụng và phiên, nhưng không được biến kho backup thành nơi tập trung mọi bí mật đăng nhập.

Cần phân biệt hai quy trình:

- **Account recovery:** xác minh người yêu cầu để cấp lại khả năng xác thực cho một tài khoản.
- **Disaster recovery của dịch vụ recovery:** phục hồi hạ tầng và dữ liệu để dịch vụ hoạt động trở lại.

Phục hồi được cơ sở dữ liệu không tự cho phép hoàn tất các yêu cầu account recovery tồn tại trong bản sao đó. Mỗi yêu cầu vẫn phải đáp ứng điều kiện hiện hành.

## 2. Phân loại dữ liệu trước khi chọn công cụ backup

Không nên bắt đầu bằng câu hỏi “dump toàn bộ database bằng lệnh nào?”. Trước hết cần biết dữ liệu nào bền vững, dữ liệu nào là bí mật, dữ liệu nào có thể tái tạo và dữ liệu nào không được tin nguyên trạng sau restore.

| Nhóm dữ liệu | Ví dụ | Cách tiếp cận |
| --- | --- | --- |
| Liên kết danh tính | Account ID, principal ID, tenant, quan hệ credential | Sao lưu nhất quán, giữ định danh ổn định |
| Hồ sơ recovery | Trạng thái case, phương thức xác minh, phạm vi yêu cầu | Sao lưu cùng phiên bản và lịch sử quyết định |
| Phê duyệt | Actor, phạm vi đã duyệt, thời hạn, policy version | Giữ bằng chứng, nhưng đánh giá lại hiệu lực sau restore |
| Tham chiếu bằng chứng | Evidence ID, vị trí kho bảo vệ, digest | Sao lưu tham chiếu và bảo đảm dữ liệu gốc có chiến lược riêng |
| Cấu hình và chính sách | Phiên bản policy, giới hạn, phương thức được phép | Lưu phiên bản; không tự áp chính sách cũ thay chính sách hiện hành |
| Dữ liệu factor cần tồn tại | Verifier, public key, secret đã mã hóa theo thiết kế | Bảo vệ theo độ nhạy và quản lý khóa độc lập |
| Trạng thái dùng một lần | Token đã tiêu thụ, code đã dùng, challenge | Không phục hồi thành khả năng sử dụng lại |
| Phiên và token | Refresh token, phiên recovery, remembered device | Có chính sách vô hiệu hóa hoặc đối soát trước mở dịch vụ |
| Audit | Ai đã quyết định gì, khi nào, cho tài khoản nào | Lưu bền vững và bảo vệ khỏi sửa hoặc xóa |
| Hàng đợi và outbox | Gửi link, thu hồi phiên, kích hoạt bước tiếp theo | Chặn phát lại tác động cũ không còn hợp lệ |

Không sao lưu mật khẩu dạng rõ, token recovery dạng rõ hoặc secret OTP vào file log để “dễ phục hồi”. Nếu hệ thống hiện đang lưu chúng không đúng cách, một backup mã hóa không sửa được vấn đề thiết kế nguồn.

Khóa riêng passkey nằm trên authenticator hoặc cơ chế lưu trữ phía người dùng, không phải bí mật mà dịch vụ recovery có thể tự tạo lại từ database backup. Bản sao public key tại máy chủ không thay thế khóa riêng đã mất.

## 3. Xác định mục tiêu RPO, RTO và các điều kiện an ninh

**RPO — Recovery Point Objective** diễn tả mức mất dữ liệu theo thời gian có thể chấp nhận. **RTO — Recovery Time Objective** diễn tả thời gian mục tiêu để phục hồi hoạt động ở mức đã định nghĩa.

Ví dụ, một dịch vụ có thể đặt mục tiêu minh họa RPO 10 phút và RTO 2 giờ. Những con số này chỉ có ý nghĩa khi nói rõ phạm vi: dữ liệu nào được phép mất trong 10 phút, và “hoạt động trở lại” là chỉ đọc trạng thái hay đã được phép phát token reset mật khẩu?

Đối với recovery, mất một cập nhật “token đã tiêu thụ” không thể được giải thích đơn giản là tổn thất nghiệp vụ trong RPO. Nếu bản sao cũ làm token dùng lại được, đó là thay đổi thuộc tính bảo mật. Cần cơ chế bổ sung như vô hiệu hóa toàn bộ thế hệ giao dịch cũ hoặc đối soát từ nguồn trạng thái không cùng bị rollback.

RTO đầy đủ có thể bao gồm:

1. Chọn đúng bản sao và xác minh tính toàn vẹn.
2. Khôi phục trong môi trường cô lập.
3. Truy cập được khóa cần thiết và kiểm tra schema.
4. Áp dụng trạng thái thu hồi, xóa và hạn chế hiện hành.
5. Vô hiệu hóa phiên, token và tác vụ cũ thuộc diện phải hủy.
6. Xác nhận các cổng cấp quyền đã dùng trạng thái mới trước khi mở lưu lượng.

Nếu chỉ đo thời gian nạp database mà bỏ các bước sau, chỉ số RTO không phản ánh thời gian dịch vụ recovery có thể vận hành an toàn.

## 4. Một backup nhất quán cần bao phủ những phụ thuộc nào?

Recovery case thường tham chiếu nhiều hệ thống: identity store, kho bằng chứng, policy registry, audit store và dịch vụ khóa. Sao lưu riêng một bảng có thể để lại các tham chiếu không còn phân giải được.

Ví dụ, snapshot chứa `evidenceId=E17` nhưng file bằng chứng chưa được ghi bền vững tại thời điểm chụp. Sau restore, case có nhãn “verified” mà dữ liệu để giải thích kết quả không còn. Hệ thống không nên suy ra rằng nhãn đó tự đủ để tiếp tục cấp quyền recovery.

Một chiến lược cần xác định:

- Điểm nhất quán của database và transaction log nếu dùng phục hồi theo thời điểm.
- Phiên bản schema và ứng dụng có thể đọc dữ liệu đó.
- Quan hệ giữa snapshot metadata với object bằng chứng và audit event.
- Các key ID cần để giải mã dữ liệu và chính sách truy cập khóa khi có sự cố.
- Trạng thái tài khoản, credential và authorization thuộc nguồn có thẩm quyền nào.
- Những bước cần reconciliation nếu không thể chụp nguyên tử giữa nhiều dịch vụ.

Snapshot ở cùng thời điểm đồng hồ chưa chắc là snapshot giao dịch nhất quán. Có thể cần checkpoint hoặc revision có ý nghĩa trong từng nguồn. Với hệ phân tán, ghi lại rõ giới hạn nhất quán và dùng trạng thái chặn tiếp tục nếu một bằng chứng bắt buộc chưa thể kiểm tra.

Không tự mở rộng phạm vi backup sang mọi dữ liệu cá nhân chỉ vì một recovery case tham chiếu chúng. Kho bằng chứng có thể có chính sách lưu trữ riêng; backup metadata cần giữ đủ tham chiếu và phụ thuộc mà không nhân bản dữ liệu nhạy cảm không cần thiết.

## 5. Manifest giúp biết bản sao chứa gì và có thể dùng ra sao

Mỗi tập backup nên có metadata đủ để xác định nguồn, phiên bản, phạm vi và phụ thuộc. Một manifest khái niệm:

```yaml
backupId: recovery_backup_example
dataset: account-recovery
environment: production-example
tenantScope: declared-scope
createdAt: 2030-02-01T02:00:00Z
schemaVersion: 12
applicationCompatibility: recovery-schema-12
databaseCheckpoint: checkpoint_reference
objectManifestReference: evidence_manifest_reference
encryptionKeyReference: backup_key_version_reference
recoveryGenerationAtBackup: 81
revocationCheckpointReference: revocation_checkpoint_reference
restorePolicy: INVALIDATE_PRE_RESTORE_RECOVERY_CAPABILITIES
integrityManifestReference: protected_integrity_manifest_reference
```

Các thời điểm và phiên bản chỉ minh họa. Manifest thật phải được tạo từ quy trình backup có thẩm quyền, không phải file YAML mà người vận hành tự sửa để qua cổng kiểm tra.

Checksum có thể phát hiện dữ liệu khác với giá trị kỳ vọng. Nếu kẻ tấn công sửa được cả backup lẫn checksum, checksum nằm cạnh file không chứng minh nguồn gốc. Cần bảo vệ manifest và thông tin kiểm chứng bằng cơ chế phù hợp như chữ ký, MAC hoặc kho kiểm soát truy cập và lịch sử độc lập theo mô hình đe dọa.

Manifest không chứa khóa giải mã dạng rõ, token recovery, mật khẩu hoặc toàn bộ dữ liệu bằng chứng. Nó giữ tham chiếu cần thiết để người có thẩm quyền phục hồi đúng dữ liệu và đúng khóa.

## 6. Mã hóa và quản lý khóa không được cùng thất bại với backup

Backup có thể chứa password hash, verifier mã dự phòng, thông tin định danh hoặc secret factor đã mã hóa. Quyền đọc backup vì vậy có thể nhạy cảm tương đương hoặc hơn quyền đọc nhiều bảng sản xuất.

Cần bảo vệ dữ liệu khi truyền và lưu trữ, nhưng cũng cần tách quyền tạo backup, đọc backup, giải mã và phục hồi. Một tác vụ được phép chụp dữ liệu không mặc nhiên cần quyền giải mã mọi bản sao hoặc thay thế dữ liệu production.

Với envelope encryption, dữ liệu có thể được mã hóa bằng data key và data key được bảo vệ bởi khóa quản lý tại KMS hoặc hạ tầng tương đương. Backup phải giữ được metadata và bản data key đã bọc cần thiết, còn quyền sử dụng khóa gốc được quản lý độc lập. Không đặt khóa giải mã dạng rõ cạnh file backup rồi coi đó là tách biệt.

Những câu hỏi cần trả lời:

- Khi vùng hạ tầng chính mất, ai còn có thể truy cập khóa để restore?
- Phiên bản khóa nào cần để đọc từng thế hệ backup?
- Xoay khóa có làm các bản sao trong thời hạn lưu trữ không thể giải mã không?
- Nếu khóa bị lộ, những bản sao nào bị ảnh hưởng và cần xử lý ra sao?
- Tài khoản automation có quyền tối thiểu và credential riêng không?
- Mọi thao tác đọc, giải mã, xuất hoặc phục hồi có dấu vết không?

Khóa do HSM hoặc dịch vụ quản lý khóa bảo vệ có quy trình dự phòng riêng. Không giả định database dump chứa đủ khả năng phục hồi khóa, cũng không tùy tiện xuất khóa được thiết kế không cho xuất ra file backup thông thường.

## 7. Tách miền lỗi để backup không biến mất cùng dữ liệu chính

Một bản sao trên cùng ổ đĩa, cùng tài khoản quản trị và cùng cơ chế xóa với dữ liệu chính có thể không bảo vệ được trước lỗi vận hành hoặc kẻ tấn công chiếm quyền.

Chiến lược phù hợp cần cân nhắc các miền lỗi:

- Lỗi thiết bị hoặc vùng hạ tầng.
- Lỗi hoặc xâm nhập tài khoản quản trị.
- Xóa nhầm và mã độc mã hóa dữ liệu.
- Hỏng dữ liệu âm thầm được đồng bộ sang replica.
- Mất khóa hoặc mất khả năng truy cập control plane.

Replication và backup có vai trò khác nhau. Replica giúp duy trì khả dụng nhưng cũng có thể nhận ngay một lệnh xóa hợp lệ về mặt kỹ thuật. Cần có các điểm phục hồi lịch sử được bảo vệ theo chính sách, cùng giới hạn quyền sửa hoặc xóa chúng.

Retention phải được chọn theo nhu cầu khôi phục và yêu cầu bảo vệ dữ liệu của tổ chức, không giữ mọi bản sao vô thời hạn. Dữ liệu bị xóa khỏi nguồn không tự biến mất khỏi các bản backup đã có; quy trình restore cần biết cách áp dụng các quyết định xóa còn hiệu lực trước khi dữ liệu quay lại phục vụ.

Không dùng laptop cá nhân hoặc môi trường phát triển không được kiểm soát để lưu bản dump production. Nếu cần diễn tập, môi trường đích và dữ liệu được sử dụng phải có phạm vi truy cập, mạng và xử lý bí mật phù hợp.

## 8. Ngăn rollback làm sống lại token và mã dùng một lần

Giả sử token T được tạo lúc T0, backup được chụp lúc T1 và token được tiêu thụ lúc T2. Nếu restore về T1 ở thời điểm T3, bản ghi có thể lại mang `used=false`. Nếu token chưa hết hạn theo đồng hồ hiện tại, nó có thể bị sử dụng lần nữa.

TTL không tự giải quyết cửa sổ này. Chỉ lưu hash của token cũng không giải quyết: hash vẫn có thể xác nhận đúng token trong khi trạng thái tiêu thụ đã bị rollback.

Một lựa chọn là hủy hiệu lực mọi capability recovery thuộc thế hệ trước restore. Hệ thống duy trì `recoveryGeneration` trong một nguồn điều khiển có thẩm quyền, không bị quay ngược cùng bản database đang phục hồi. Token hoặc bản ghi capability được ràng buộc với generation lúc cấp, và verifier phải kiểm tra generation đang hoạt động.

```text
Trước sự cố:
  live recovery generation = 81
  token T thuộc generation 81

Trước khi mở môi trường đã restore:
  nguồn điều khiển độc lập cấp generation 82
  mọi token hoặc capability generation 81 bị từ chối
  giao dịch mới chỉ được cấp dưới generation 82
```

Không chỉ đọc số 81 từ backup rồi ghi 82 vào chính database đó mà mặc định an toàn. Một bản restore hoặc môi trường khác có thể đã sử dụng số tương ứng. Việc cấp generation cần bảo đảm tính mới trong toàn phạm vi verifier dựa vào nó, bằng nguồn điều khiển bền vững và giao thức chuyển thế hệ phù hợp.

Nguồn generation, cách phân phối và verifier cũng phải có thiết kế khả dụng. Nếu không xác định được generation có hiệu lực, đường cấp hoặc chấp nhận capability cần đóng lại theo chính sách, không mặc định dùng giá trị cũ trong backup.

Các lựa chọn khác có thể dùng ledger tiêu thụ hoặc thu hồi độc lập với miền rollback, rồi đối soát đầy đủ trước mở dịch vụ. Ledger đó phải có độ bền và checkpoint phù hợp; nếu nó cùng bị mất các sự kiện T2 thì không còn cung cấp bằng chứng cần thiết.

Recovery code cần chính sách tương tự: vô hiệu hóa bộ cũ theo generation hoặc một cơ chế đối soát đủ mạnh, rồi cấp bộ mới khi người dùng đạt điều kiện. Không âm thầm biến các code đã dùng thành khả dụng chỉ vì dữ liệu lưu verifier được phục hồi thành công.

## 9. Credential, phiên và liên kết đã bị thu hồi phải tiếp tục bị thu hồi

Token recovery chỉ là một phần của trạng thái có thể bị quay ngược. Backup cũ còn có thể chứa factor bị mất, email recovery cũ, phiên thiết bị tin cậy hoặc role đã bị thu hồi sau thời điểm chụp.

Trước khi mở lưu lượng cần xác định cách xử lý:

| Trạng thái trong backup | Cổng cần có sau restore |
| --- | --- |
| Recovery case đang chờ | Đánh giá lại bằng chứng, thời hạn, chính sách và rủi ro |
| Phê duyệt còn nhãn hợp lệ | Đối soát thu hồi, phiên bản và quyền hiện hành của người duyệt |
| Factor hoặc kênh recovery cũ | Áp dụng thay đổi và thu hồi có thẩm quyền mới hơn |
| Refresh token, phiên recovery | Vô hiệu hóa hoặc đối soát theo chiến lược đã định |
| Role, membership, security hold | Giữ quyết định hiện hành, không chép ngược trạng thái cũ |
| Tài khoản đã xóa hoặc đình chỉ | Áp dụng tombstone, hạn chế và quyết định xóa tương ứng |

Nếu nguồn authoritative hiện hành còn tồn tại, backup không được ghi ngược dữ liệu cũ vào nguồn đó chỉ để các bảng trông đồng nhất. Nếu chính nguồn đó cũng phải restore, cần quy trình reconciliation và hạn chế hoạt động cho đến khi xác định được trạng thái an toàn.

Tăng epoch hoặc đổi signing key chỉ có tác dụng nếu mọi verifier liên quan thực sự thực thi cơ chế đó. Đổi khóa ký token không tự vô hiệu hóa opaque token được tra trong database, và tăng recovery generation không tự vô hiệu hóa API key nếu API key không thuộc cơ chế generation ấy.

Một recovery case cũ có thể được giữ làm lịch sử, trong khi capability gắn với nó bị hủy và người dùng phải mở bước xác minh mới. Giữ dữ liệu giải thích quyết định và giữ quyền tiếp tục thực thi là hai việc khác nhau.

## 10. Ví dụ Java: chính sách phân loại dữ liệu backup

Đoạn mã sau minh họa allowlist theo loại artifact. Nó không đọc dữ liệu thật hoặc chạy backup. Mục tiêu là khiến hệ thống phải khai báo rõ cách sao lưu và cách xử lý sau restore, thay vì tự đưa mọi trường vào cùng một tập tin.

```java
import java.util.Objects;

public final class RecoveryBackupPolicy {
    public enum Artifact {
        ACCOUNT_MAPPING,
        RECOVERY_CASE,
        APPROVAL,
        EVIDENCE_REFERENCE,
        POLICY_REFERENCE,
        ENCRYPTED_FACTOR_MATERIAL,
        KEY_REFERENCE,
        AUDIT_EVENT,
        TOKEN_VERIFIER,
        OTP_ATTEMPT_STATE,
        OUTBOX_EVENT,
        PLAINTEXT_RECOVERY_TOKEN,
        PLAINTEXT_FACTOR_SECRET
    }

    public enum BackupRule {
        PROTECTED_BACKUP,
        REFERENCE_ONLY,
        LOGICAL_EXCLUSION_PREFERRED,
        PROHIBITED_IN_GENERAL_BACKUP
    }

    public enum RestoreRule {
        RECONCILE_WITH_CURRENT_AUTHORITY,
        RESOLVE_PROTECTED_DEPENDENCY,
        KEEP_AS_HISTORY_REVALIDATE_BEFORE_USE,
        INVALIDATE_OLD_SECURITY_STATE,
        HOLD_SIDE_EFFECTS_FOR_REVIEW,
        REJECT
    }

    public record Handling(BackupRule backup, RestoreRule restore) {}

    public static Handling classify(Artifact artifact) {
        Objects.requireNonNull(artifact);
        return switch (artifact) {
            case ACCOUNT_MAPPING, ENCRYPTED_FACTOR_MATERIAL ->
                    new Handling(BackupRule.PROTECTED_BACKUP,
                            RestoreRule.RECONCILE_WITH_CURRENT_AUTHORITY);
            case RECOVERY_CASE, APPROVAL, AUDIT_EVENT ->
                    new Handling(BackupRule.PROTECTED_BACKUP,
                            RestoreRule.KEEP_AS_HISTORY_REVALIDATE_BEFORE_USE);
            case EVIDENCE_REFERENCE, POLICY_REFERENCE, KEY_REFERENCE ->
                    new Handling(BackupRule.REFERENCE_ONLY,
                            RestoreRule.RESOLVE_PROTECTED_DEPENDENCY);
            case TOKEN_VERIFIER, OTP_ATTEMPT_STATE ->
                    new Handling(BackupRule.LOGICAL_EXCLUSION_PREFERRED,
                            RestoreRule.INVALIDATE_OLD_SECURITY_STATE);
            case OUTBOX_EVENT ->
                    new Handling(BackupRule.PROTECTED_BACKUP,
                            RestoreRule.HOLD_SIDE_EFFECTS_FOR_REVIEW);
            case PLAINTEXT_RECOVERY_TOKEN, PLAINTEXT_FACTOR_SECRET ->
                    new Handling(BackupRule.PROHIBITED_IN_GENERAL_BACKUP,
                            RestoreRule.REJECT);
        };
    }
}
```

`REFERENCE_ONLY` nghĩa là bản backup của dịch vụ này giữ tham chiếu; dữ liệu gốc, chính sách hoặc khóa phụ thuộc phải có chiến lược bảo vệ riêng. Không được xóa dữ liệu gốc rồi coi tham chiếu là một bản sao có khả năng phục hồi.

`LOGICAL_EXCLUSION_PREFERRED` không bảo đảm token verifier vắng mặt trong một backup vật lý nguyên ổ hoặc nguyên database. Nếu ảnh vật lý chứa trạng thái tạm, môi trường restore phải bị cô lập và áp dụng vô hiệu hóa hoặc đối soát trước khi mọi endpoint, worker và verifier hoạt động.

OTP attempt state cũng là dữ liệu chống lạm dụng. Việc loại trừ trạng thái thử sai không được biến thành bỏ rate limit sau restore. Hệ thống cần khởi tạo biện pháp hạn chế thận trọng hoặc khôi phục tín hiệu cần thiết từ nguồn tin cậy theo thiết kế.

Ví dụ không thay thế encryption policy, kiểm soát truy cập hoặc thiết kế ledger chống rollback. Phân loại rõ chỉ là bước đầu để các công cụ backup và restore thực thi đúng chính sách.

## 11. Outbox và worker không được phát lại mù quáng

Một bản backup có thể chứa sự kiện “gửi link reset”, “thực thi recovery đã duyệt” hoặc “gửi mã” đang chờ. Khôi phục database rồi bật worker ngay có thể gửi bí mật cũ hoặc kích hoạt bước đã bị thu hồi.

Trước restore, cần cô lập cả đường HTTP lẫn tác vụ nền, scheduler, consumer và webhook. Chặn lưu lượng người dùng nhưng để worker gửi email chạy vẫn chưa cô lập được hệ thống.

Khi khôi phục outbox:

- Phân biệt sự kiện lịch sử với công việc còn được phép thực thi.
- Kiểm tra case, generation, phạm vi, thời hạn và quyền hiện hành trước tác động.
- Không phát lại token hoặc mã bí mật đã được tạo ở thế hệ cũ.
- Dùng idempotency phù hợp cho tác động có thể retry.
- Giữ trạng thái review hoặc reconciliation cho sự kiện chưa xác định được hiệu lực.

Idempotency lưu trong cùng database bị rollback cũng có thể mất dấu tác động đã xảy ra. Với tác động ngoài hệ thống, cần thiết kế khóa idempotency và nguồn xác nhận đủ bền hoặc đối soát với bên nhận. Một message có cùng ID không tự bảo đảm không gửi trùng nếu nơi kiểm tra ID cũng đã quay về quá khứ.

Các sự kiện thu hồi phiên hoặc áp dụng security hold cần được đối xử theo ý nghĩa bảo mật của chúng. Không áp dụng một quy tắc “xóa hết outbox” cho mọi loại sự kiện nếu điều đó làm mất tác vụ bảo vệ bắt buộc.

## 12. Quy trình restore phải được định nghĩa khi thiết kế backup

Một runbook khái niệm:

```text
1. Xác định sự cố, phạm vi dữ liệu và nguồn trạng thái còn đáng tin.
2. Dừng đường cấp recovery và cô lập các tác vụ có tác động.
3. Chọn backup, xác minh manifest, quyền truy cập và phụ thuộc khóa.
4. Restore vào môi trường cô lập có cấu hình phù hợp.
5. Kiểm tra khả năng đọc schema và tính nhất quán tham chiếu.
6. Áp dụng tombstone, thu hồi, hold và các quyết định hiện hành.
7. Thiết lập generation hoặc cơ chế chống rollback mới có thẩm quyền.
8. Hủy capability, phiên hoặc code cũ thuộc diện phải vô hiệu hóa.
9. Đối soát outbox, audit và các tác động phân tán.
10. Xác nhận verifier và các cổng cấp quyền sử dụng trạng thái đúng.
11. Mở dịch vụ theo phạm vi đã được cho phép và giám sát sát sao.
```

Nếu không giải mã được bằng chứng bắt buộc hoặc không xác minh được nguồn thu hồi, không tự đổi case sang “verified” cho tiện vận hành. Có thể cho phép tra cứu lịch sử ở phạm vi hạn chế trong khi tiếp tục chặn cấp quyền recovery.

Môi trường restore cũng cần đúng endpoint, chứng thư, cấu hình tenant và khóa theo mục đích. Nhầm cấu hình production sang một bản diễn tập có thể gửi thông báo hoặc cấp token ra ngoài phạm vi dự định.

Sau khi dùng bản restore để điều tra hoặc diễn tập, bản sao tạm và quyền truy cập tạm cần được xử lý theo chính sách. Không để một bản database recovery chứa dữ liệu nhạy cảm trở thành môi trường test tồn tại lâu dài mà không có chủ sở hữu.

## 13. Diễn tập khả năng phục hồi và quan sát backup

Một tác vụ báo “backup success” chỉ chứng minh tác vụ đã hoàn tất theo điều kiện của công cụ. Nó chưa chứng minh có thể giải mã, phục hồi dữ liệu nhất quán hoặc mở dịch vụ mà không hồi sinh quyền cũ.

Kế hoạch vận hành nên có diễn tập restore trong môi trường phù hợp, gồm các tình huống như:

- Backup thiếu một phần evidence object hoặc metadata khóa.
- Token đã được tiêu thụ sau checkpoint nhưng còn trong bản sao.
- Recovery case bị thu hồi sau khi chụp backup.
- Tài khoản bị xóa hoặc bị đặt security hold sau checkpoint.
- Signing key và encryption key thay đổi giữa các thế hệ backup.
- Outbox chứa message mà tác động bên ngoài đã diễn ra.
- Permission cache hoặc verifier vẫn giữ generation cũ.

Các tín hiệu cần quan sát gồm thời điểm backup thành công gần nhất, độ trễ so với mục tiêu, khả năng truy cập khóa, dung lượng bất thường, lỗi kiểm chứng manifest và lần restore đã diễn tập gần nhất. Cần cảnh báo khi tác vụ không chạy hoặc khi backup nhỏ bất thường, thay vì chỉ cảnh báo lệnh trả lỗi.

Audit hoạt động backup cần trả lời ai tạo, đọc, tải xuống, giải mã, xóa hoặc phục hồi tập dữ liệu nào. Log không được chứa nội dung bí mật của bản sao. Quyền truy cập khẩn cấp cũng cần được thu hồi sau nhiệm vụ và có lịch sử rõ ràng.

## 14. Ví dụ xuyên suốt: restore không được mở lại link đã dùng

Dịch vụ tạo token reset mật khẩu cho tài khoản của Linh trong recovery generation 81. Backup được chụp khi token chưa tiêu thụ. Linh sử dụng token thành công, đổi mật khẩu và kết thúc phiên recovery. Một lúc sau, lỗi lưu trữ buộc hệ thống phục hồi từ backup đó.

Nếu chỉ restore và bật API, trạng thái cũ có thể cho phép link được sử dụng lại. Người giữ một bản sao link có thể lợi dụng cửa sổ còn hạn của token. Việc database chỉ lưu token hash không ngăn được kịch bản này.

Runbook giữ môi trường cô lập, đối soát các trạng thái có thẩm quyền còn tồn tại và chuyển sang generation mới do nguồn điều khiển độc lập cấp. Verifier từ chối token generation 81; worker cũng không gửi lại link từ outbox cũ. Những phiên và mã dùng một lần khác được xử lý theo phạm vi chính sách của chúng.

Hồ sơ cũ của Linh vẫn được giữ để điều tra và giải thích lịch sử. Nếu cần recovery tiếp, Linh phải đi qua bước xác minh mới với chính sách hiện hành; hệ thống không coi trạng thái chưa tiêu thụ trong snapshot là một quyền mới.

Sau đó, đội vận hành kiểm tra các thay đổi credential, hold và authorization xảy ra sau checkpoint từ nguồn còn đáng tin. Nếu chưa xác định được trạng thái an toàn, dịch vụ tiếp tục hạn chế hành động liên quan thay vì tự chọn dữ liệu cũ làm chuẩn.

Ví dụ cho thấy mục tiêu không chỉ là lấy lại các hàng dữ liệu, mà là phục hồi một dịch vụ có thể đưa ra quyết định đúng ở hiện tại.

## 15. Những lỗi cần tránh

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dump mọi dữ liệu và lưu cùng khóa giải mã | Một lần lộ kho backup làm lộ toàn bộ tập dữ liệu | Phân loại, mã hóa và tách quyền quản lý khóa |
| Cho rằng replica là backup lịch sử | Lỗi xóa hoặc sửa có thể lan sang mọi replica | Có điểm phục hồi được bảo vệ và retention rõ ràng |
| Restore rồi mở API, worker ngay | Token hoặc tác vụ cũ được thực thi lại | Cô lập và áp dụng cổng mở dịch vụ |
| Tin TTL giải quyết token đã dùng | Token chưa hết hạn có thể sống lại | Generation mới hoặc đối soát chống rollback đủ mạnh |
| Tăng generation chỉ từ số trong backup | Không bảo đảm tính mới toàn hệ thống | Dùng nguồn cấp generation độc lập, có thẩm quyền |
| Giữ phê duyệt cũ như quyền thực thi hiện tại | Bỏ qua thu hồi, rủi ro và chính sách mới | Giữ lịch sử, kiểm tra lại trước khi tiếp tục |
| Loại trừ trạng thái chống lạm dụng rồi bỏ rate limit | Kẻ tấn công có thêm lượt thử sau restore | Khởi tạo hạn chế hoặc đối soát từ nguồn tin cậy |
| Chỉ kiểm tra file backup tồn tại | Không biết có giải mã hoặc restore được không | Diễn tập và kiểm tra toàn bộ phụ thuộc |
| Giữ bản dump tạm không thời hạn | Mở thêm kho dữ liệu nhạy cảm không được quản lý | Có chủ sở hữu, phạm vi và quy trình xử lý bản tạm |

Recovery data backup cần giữ được lịch sử và dữ liệu bền vững, bảo vệ bí mật, duy trì khả năng giải mã có kiểm soát và định nghĩa rõ điều gì không được tái sử dụng sau restore. Khả năng phục hồi chỉ hoàn chỉnh khi dữ liệu cũ không thể tự biến thành quyền recovery mới trái với quyết định bảo mật hiện hành.
