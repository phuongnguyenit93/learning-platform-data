# Key backup

## 1. Mục tiêu là khôi phục đúng quyền sử dụng khóa

Key backup là tạo và bảo vệ thông tin cần thiết để phục hồi khả năng sử dụng khóa khi bản đang hoạt động hoặc môi trường hiện tại không còn sẵn có. Nó không chỉ là sao chép một file chứa byte khóa sang nơi khác.

Một backup có giá trị khi hệ thống có thể khôi phục đúng key version, đúng mục đích và đúng trạng thái được phép trong thời gian yêu cầu. Đồng thời, người chỉ có quyền đọc bản backup không được tự có quyền giải mã dữ liệu hoặc ký tài liệu trái phép.

Ví dụ trong nền tảng học tập: database backup vẫn còn đầy đủ báo cáo đã mã hóa, nhưng KEK dùng mở các DEK đã mất. Khôi phục database thành công chưa giúp đọc được báo cáo. Ngược lại, nếu backup chứa raw key cạnh ciphertext với cùng quyền truy cập, khả năng phục hồi có thể đạt nhưng mục tiêu bảo mật ban đầu bị phá vỡ.

NIST mô tả key recovery như quá trình lấy lại keying material khi cần phục hồi. Trong thiết kế hệ thống, quy trình đó phải gắn với chính sách quản lý khóa và quyền sử dụng, không phải một đường bỏ qua kiểm soát production. [NIST: key recovery](https://csrc.nist.gov/glossary/term/key_recovery).

Bài học tập trung vào yêu cầu bảo mật và bằng chứng kiểm chứng cho backup/restore khóa. Các mốc thời gian, định danh và profile minh họa không phải thao tác backup, import hay restore đã được thực hiện trên hạ tầng thật.

## 2. Phân biệt backup, replication, archive và escrow

| Khái niệm | Mục tiêu chính | Điều cần lưu ý |
| --- | --- | --- |
| Backup | Phục hồi từ một bản sao hoặc snapshot đã bảo vệ | Có thể có độ trễ, phiên bản và điều kiện restore riêng |
| Replication | Duy trì bản sao phục vụ availability/failover | Một thay đổi sai hoặc hành động quản trị có thể lan theo cơ chế replication |
| Archive | Giữ key/thông tin cần thiết cho dữ liệu lịch sử trong thời hạn đã chốt | Không đồng nghĩa khóa được phép dùng cho dữ liệu mới |
| Escrow | Một mô hình giữ khả năng phục hồi theo thẩm quyền đã định | Tạo thêm bên/quy trình có khả năng tiếp cận hoặc sử dụng key |
| Export/import | Chuyển key material hoặc biểu diễn provider giữa boundary | Không tự tạo lịch sử backup, integrity hoặc quyền restore |

Một cụm KMS có nhiều node không tự là bản backup chống xóa nhầm hoặc tài khoản quản trị bị chiếm. Một backup cũng không tự là cơ chế failover tức thời. Phải chọn thiết kế theo từng sự cố cần chịu được.

Với archive, có thể cần giữ quyền giải mã lịch sử nhưng cấm encryption/signing mới. Với escrow, cần xác định ai có quyền phục hồi, bằng chứng phê duyệt, điều kiện truy cập và cách audit. Không thêm escrow vào mọi use case mà chưa đánh giá tác động của bên giữ quyền phục hồi.

## 3. Khóa nào cần backup và để làm gì?

Không có quy tắc hợp lý rằng phải lưu lại mọi key material của hệ thống. Mục tiêu phụ thuộc loại khóa và thời hạn dữ liệu:

| Loại khóa/thông tin | Nhu cầu phục hồi cần xét | Rủi ro khi giữ bản sao |
| --- | --- | --- |
| DEK bảo vệ báo cáo dài hạn | Cần đọc ciphertext trong thời gian lưu dữ liệu | Lộ DEK làm mất bí mật của phạm vi dữ liệu tương ứng |
| KEK bảo vệ nhiều DEK | Cần mở wrapped DEK còn phụ thuộc | Lộ KEK có thể ảnh hưởng một tập dữ liệu lớn |
| Signing private key | Có thể cần tiếp tục phát hành theo kế hoạch DR | Bản sao có thể tạo chữ ký mới dưới cùng danh tính |
| Verification public key và trust metadata | Cần kiểm tra tài liệu lịch sử theo policy | Tính toàn vẹn và liên kết issuer/purpose quan trọng hơn bí mật |
| MAC key | Có thể cần xác minh thông điệp cũ hoặc tiếp tục tích hợp | Bên có key cũng có khả năng tạo MAC |
| Ephemeral/session key | Thường không có nhu cầu archive như key dài hạn | Giữ thêm có thể làm mất mục tiêu giới hạn lifetime/forward secrecy |

Nếu signing key không cần được phục hồi để ký tiếp, có thể phát hành bằng key mới và giữ public key cùng trạng thái cần thiết để verify lịch sử. Không lưu private key vô thời hạn chỉ vì chứng chỉ cũ vẫn cần được kiểm tra.

Với envelope encryption, wrapped DEK thường đi cùng ciphertext. Nhưng một bản wrapped DEK không tự giải quyết việc mất KEK hoặc trust/configuration cần để unwrap. Inventory backup phải đi theo dependency của dữ liệu, không chỉ theo danh sách key đang active.

## 4. Threat model của kho backup

Backup phải giữ cả confidentiality, integrity, availability và tính đúng nguồn gốc. Một số tình huống cần phân tích:

| Khả năng của đối thủ/sự cố | Yêu cầu cần hình thành |
| --- | --- |
| Đọc được kho backup | Không thu được raw secret/private key hoặc quyền dùng key chỉ từ bản đọc đó |
| Sửa hoặc tráo một backup | Xác thực format, manifest và material theo cơ chế tin cậy |
| Xóa hoặc mã hóa kho vận hành | Có failure domain/bản sao phục hồi phù hợp với sự cố đã chọn |
| Chiếm một tài khoản backup operator | Không tự có đầy đủ quyền export, restore, activate và dùng key trái scope |
| Mất một vùng/thiết bị/provider endpoint | Restore được vào đích tương thích trong RTO đã cam kết |
| Lấy snapshot cũ trước một lần thu hồi | Không hồi sinh trạng thái active của khóa đã bị hạn chế/compromise |
| Lộ recovery credential hoặc wrapping key | Có kế hoạch xác định phạm vi, thay cơ chế bảo vệ và xử lý bản sao liên quan |

OWASP yêu cầu quản lý cả vòng đời, khả năng recovery và bảo vệ các bản sao key material; bản backup không được trở thành nơi bỏ qua chính sách dùng khóa. [OWASP: Key Management](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html).

Từ “tách biệt” phải gắn với một giả định cụ thể. Hai bucket ở hai vị trí nhưng cùng một identity có toàn quyền xóa cả hai có thể chưa chống được sự cố chiếm identity đó. Một offline copy không có recovery credential sẵn sàng cũng có thể không đáp ứng RTO.

## 5. Lập dependency graph từ ciphertext tới recovery root

Với báo cáo học tập, một chuỗi phục hồi có thể là:

```text
Data snapshot chứa báo cáo mã hóa
└── Envelope: ciphertext, nonce/tag, context và wrapped DEK
    └── KEK version được tham chiếu
        └── Provider backup/security domain hoặc cơ chế phục hồi được duyệt
            └── Recovery identity/credential và thẩm quyền cần thiết

Đi kèm: key registry, crypto profile, format version,
mapping tenant/purpose và trạng thái hạn chế/thu hồi có thẩm quyền.
```

Nếu một mắt xích không còn, dữ liệu có thể không phục hồi được dù các bước khác đều có bản sao. Các phần cần bảo vệ cũng không có cùng yêu cầu: raw private key cần bí mật; public key cần authenticity; manifest cần integrity và liên kết với đúng backup.

### 5.1. Tránh vòng phụ thuộc không có gốc phục hồi

Ví dụ, backup key A được mã hóa bằng B, còn bản sao duy nhất của B lại được mã hóa bằng A. Nếu không có một đường mở độc lập, hai file còn nguyên vẫn không tạo khả năng recovery.

Cần xác định recovery root nằm ở đâu: cơ chế provider/HSM, một key được bảo vệ riêng hoặc một cơ chế khác được thiết kế và duyệt. Không giải quyết vòng phụ thuộc bằng cách ghi một master password vào cùng script restore.

Recovery credential cũng cần owner, khả năng truy cập khi identity provider hoặc vùng production hỏng, và quy trình kiểm soát. Tài liệu restore chỉ nói “đăng nhập bằng tài khoản đang dùng” có thể thất bại đúng lúc hệ thống nhận diện đó không còn sẵn có.

### 5.2. Phải giữ đủ key version, không chỉ alias hiện tại

Alias `current-report-key` có thể đã chuyển nhiều lần. Dữ liệu lịch sử vẫn có thể tham chiếu các key version khác nhau. Backup chỉ có current alias không bảo đảm đọc được mọi data snapshot thuộc retention.

Inventory cần liên kết snapshot dữ liệu với các version thực sự cần dùng, gồm cả metadata/profile và đích restore phù hợp. Trước khi ngừng hoặc hủy một key version, phải đối soát ciphertext, wrapped DEK, archive và backup còn phụ thuộc.

Nếu một provider quản lý rotation nội bộ dưới một key resource, phải hiểu đúng semantics của provider đó. Không suy từ tên một resource rằng mọi material version đã được đưa vào một export/backup độc lập theo cách ứng dụng tưởng.

## 6. RPO/RTO phải xét cả dữ liệu lẫn khóa

Recovery Point Objective (RPO) mô tả mức mất dữ liệu/trạng thái chấp nhận được theo mục tiêu đã chốt; Recovery Time Objective (RTO) mô tả thời gian mục tiêu để phục hồi khả năng cần thiết. Hai mục tiêu này phải bao gồm các dependency mật mã.

Giả sử data backup được chụp sau khi khóa v4 bắt đầu bảo vệ báo cáo mới, nhưng key backup chỉ có tới v3. Khôi phục data snapshot mới nhất sẽ để lại một tập ciphertext không đọc được. Không thể chỉ báo RPO của database mà bỏ khoảng trống key coverage.

### 6.1. Coverage theo version quan trọng hơn timestamp đơn thuần

Một backup mới về thời gian chưa chắc chứa key version đúng nếu thao tác backup thất bại một phần hoặc không bao phủ đúng đối tượng. Cần kiểm tra tập version cần cho data snapshot là tập con của khả năng phục hồi đã được xác nhận.

Ngược lại, backup cũ vẫn có thể chứa đủ key material cho một snapshot dữ liệu nếu chưa phát sinh version mới. Việc chấp nhận còn phụ thuộc tuổi backup, trạng thái hiện tại và policy; không dùng một phép so sánh ngày thay toàn bộ coverage check.

Với use case yêu cầu khả năng phục hồi trước khi ghi dữ liệu mới, gate kích hoạt key cần xác nhận cơ chế recovery đã sẵn sàng. Điều này có thể là backup đã kiểm tra, provider durability/replication được chấp nhận trong threat model hoặc một thiết kế khác đã được duyệt.

### 6.2. Đo RTO tới khả năng sử dụng, không chỉ tới lúc import xong

Thời gian phục hồi có thể gồm lấy approval, truy cập recovery credential, chuẩn bị đích, restore/import, đối chiếu trạng thái và kiểm thử dữ liệu. Một API trả `restore complete` chưa chứng minh ứng dụng có thể đọc báo cáo hợp lệ theo quyền.

RTO/RPO cụ thể phải được owner dữ liệu và vận hành chốt theo tác động nghiệp vụ. Không có một lịch “backup mỗi ngày” đủ cho mọi loại key và tốc độ thay đổi dữ liệu.

## 7. Cơ chế backup phải phù hợp provider và boundary

### 7.1. Non-exportable không có nghĩa bỏ qua kế hoạch recovery

Một private key không được xuất plaintext có thể có cơ chế backup hoặc replication được provider hỗ trợ trong boundary của nó. Không cố gọi `getEncoded()` hoặc sửa policy để lấy raw material chỉ vì checklist ghi “phải có file backup”.

Ví dụ, AWS CloudHSM mô tả backup của users, keys và policies trong cluster, với dữ liệu được mã hóa trước khi rời HSM. Đây là một mô hình backup theo provider, không phải plaintext export tùy ý cho ứng dụng. [AWS CloudHSM: cluster backups](https://docs.aws.amazon.com/cloudhsm/latest/userguide/backups.html).

### 7.2. Backup blob không tự có tính portable

Azure Key Vault mô tả backup từng object thành encrypted blob và điều kiện restore liên quan tới cùng subscription và Azure geography. Do đó có file blob không đồng nghĩa có thể mang sang mọi tài khoản, region hoặc provider để phục hồi. [Microsoft Learn: Key Vault backup and restore](https://learn.microsoft.com/en-us/azure/key-vault/general/backup).

Nếu dự án cần một failure domain ngoài giới hạn của định dạng provider, phải chọn kiến trúc recovery đáp ứng trước khi đưa key vào sử dụng. Không hứa khả năng cross-provider restore chỉ dựa vào việc artifact đã được tải xuống thành công.

### 7.3. Resilience dịch vụ và xóa key là các trường hợp khác nhau

AWS KMS cung cấp các đặc tính resilience và tùy chọn multi-Region key cho chiến lược availability phù hợp. Cần phân biệt các đặc tính đó với một cơ chế khôi phục sau khi key bị xóa hoặc material nguồn không còn. [AWS KMS: resilience](https://docs.aws.amazon.com/kms/latest/developerguide/disaster-recovery-resiliency.html).

Tài liệu AWS KMS nêu việc xóa key là thao tác không thể đảo ngược và có thể khiến dữ liệu không còn giải mã được, với những trường hợp ngoại lệ/điều kiện riêng được mô tả theo loại key. Không xem backup database hay một key ID đã lưu là cách phục hồi mọi KMS key đã bị xóa. [AWS KMS: deleting keys](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html).

Những ví dụ provider trên dùng để chỉ ra giới hạn cần xác minh, không phải đề xuất đổi hạ tầng của nền tảng. Triển khai thật phải dựa đúng loại key, origin, API và khả năng restore đang được sử dụng.

## 8. Bảo vệ artifact và quyền backup/restore

### 8.1. Bảo vệ bí mật và tính toàn vẹn

Key material có thể xuất phải được bảo vệ bằng cơ chế wrapping/backup được duyệt trước khi ra khỏi boundary cho phép. Cần xác thực cả material và metadata quan trọng như version, owner, purpose và format để phát hiện sửa đổi hoặc tráo bản.

Một checksum lưu cạnh file không tự chống được kẻ có quyền thay cả file lẫn checksum. Manifest cần cơ chế integrity/authenticity phù hợp hoặc được đối soát qua một nguồn tin cậy độc lập. Metadata chưa được xác thực không được dùng để tự chọn target, key URL hoặc scope restore.

Wrapped backup cũng có thể tiết lộ metadata. Tên tenant, loại dữ liệu hoặc cấu trúc key inventory cần được giảm và bảo vệ theo policy, không mặc định mọi field ngoài ciphertext đều được công bố.

### 8.2. Tách quyền theo thao tác

Backup operator không tự cần quyền dùng key để decrypt/sign. Restore operator không tự cần quyền kích hoạt key cho production. Người phê duyệt recovery không nhất thiết là người được phép đọc plaintext đã phục hồi.

Với key quan trọng, có thể áp dụng dual control/quorum theo rủi ro. Nếu dùng chia sẻ bí mật hoặc recovery share, phải dùng cơ chế đã được duyệt và bảo vệ từng phần theo mô hình đó; không tự sáng tác cách chia file hay XOR rồi gọi là threshold scheme.

Quorum không có giá trị mong muốn nếu một người hoặc một tài khoản có thể đọc mọi share, reset mọi credential và tự phê duyệt. Phải kiểm tra cả quyền kỹ thuật và đường phục hồi danh tính.

### 8.3. Tách failure domain và giới hạn xóa

Thiết kế cần nêu sự cố nào một bản sao phải chịu được: mất thiết bị, mất vùng, ransomware, xóa nhầm hoặc chiếm tài khoản quản trị. Chọn quyền ghi/xóa, retention protection và bản sao phù hợp theo threat model đó.

Không gọi một bản backup là immutable chỉ vì ứng dụng không có nút xóa. Cần kiểm tra ai có thể đổi retention, purge, thay khóa bảo vệ backup hoặc vô hiệu hóa toàn bộ đường recovery.

Một backup nhạy cảm cũng không nên được sao chép vô hạn để tăng cảm giác an toàn. Mỗi bản sao tạo thêm nơi cần kiểm soát và xử lý khi khóa hoặc credential bị compromise.

## 9. Ví dụ Java: kiểm tra coverage trước khi restore

Ví dụ Java 17 sau kiểm tra một số điều kiện của recovery plan đã được phê duyệt đối với manifest đã được xác thực. Nó không export/import raw key và không tự thực hiện restore trên provider.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public final class KeyBackupPreflight {
    public record ApprovedPlan(
            String sourceEnvironment,
            String recoveryScope,
            String targetReference,
            Set<String> requiredKeyVersions,
            Set<String> allowedBackupFormats,
            Instant minimumBackupTime
    ) {
        public ApprovedPlan {
            Objects.requireNonNull(sourceEnvironment);
            Objects.requireNonNull(recoveryScope);
            Objects.requireNonNull(targetReference);
            requiredKeyVersions = Set.copyOf(requiredKeyVersions);
            allowedBackupFormats = Set.copyOf(allowedBackupFormats);
            Objects.requireNonNull(minimumBackupTime);
            if (requiredKeyVersions.isEmpty() || allowedBackupFormats.isEmpty()) {
                throw new IllegalArgumentException("Incomplete recovery plan");
            }
        }
    }

    // Chỉ tạo sau khi artifact/manifest đã qua xác thực của cơ chế backup.
    // Không deserialize type này trực tiếp từ request rồi coi là tin cậy.
    public record VerifiedManifest(
            String backupId,
            String sourceEnvironment,
            String recoveryScope,
            String format,
            Instant createdAt,
            Set<String> keyVersions
    ) {
        public VerifiedManifest {
            Objects.requireNonNull(backupId);
            Objects.requireNonNull(sourceEnvironment);
            Objects.requireNonNull(recoveryScope);
            Objects.requireNonNull(format);
            Objects.requireNonNull(createdAt);
            keyVersions = Set.copyOf(keyVersions);
        }
    }

    public record RestoreSelection(
            String backupId,
            String targetReference,
            Set<String> selectedKeyVersions
    ) {
        public RestoreSelection {
            selectedKeyVersions = Set.copyOf(selectedKeyVersions);
        }
    }

    public static RestoreSelection inspect(
            ApprovedPlan plan,
            VerifiedManifest manifest
    ) {
        Objects.requireNonNull(plan);
        Objects.requireNonNull(manifest);

        if (!plan.sourceEnvironment().equals(manifest.sourceEnvironment())
                || !plan.recoveryScope().equals(manifest.recoveryScope())) {
            throw new IllegalArgumentException("Backup outside approved scope");
        }
        if (!plan.allowedBackupFormats().contains(manifest.format())) {
            throw new IllegalArgumentException("Unsupported backup format");
        }
        if (manifest.createdAt().isBefore(plan.minimumBackupTime())) {
            throw new IllegalArgumentException("Backup outside age policy");
        }
        if (!manifest.keyVersions().containsAll(plan.requiredKeyVersions())) {
            throw new IllegalArgumentException("Missing required key versions");
        }

        return new RestoreSelection(
                manifest.backupId(),
                plan.targetReference(),
                plan.requiredKeyVersions()
        );
    }

    private KeyBackupPreflight() {}
}
```

`requiredKeyVersions` phải được tính từ data snapshot và inventory có thẩm quyền, không phải một danh sách client tự đề nghị để vượt policy. `targetReference` và tập format cho phép cũng xuất phát từ recovery plan đã được kiểm tra tương thích/quyền, không từ metadata chưa tin cậy.

`minimumBackupTime` là một điều kiện tuổi backup của policy mẫu, độc lập với coverage. Không bỏ coverage check chỉ vì timestamp mới. Đồng thời, việc một manifest nói có version chưa chứng minh material trong provider restore sẽ đúng; vẫn cần gate kiểm tra sau restore.

`RestoreSelection` không phải quyết định activate. Nó chỉ trả tập version đã được plan yêu cầu. Nếu provider chỉ restore cả một bundle, adapter cần giữ các key ngoài tập ở trạng thái và quyền bị hạn chế phù hợp hoặc dùng một kế hoạch khác; không tự active toàn bộ vì manifest có thêm version.

Tên type `VerifiedManifest` không tự cung cấp mật mã. Implementation đọc backup phải xác thực artifact/manifest trước khi tạo descriptor này, và lớp điều phối vẫn phải kiểm tra thẩm quyền actor, target, trạng thái thu hồi cùng các điều kiện ngoài ví dụ.

## 10. Quy trình restore có gate rõ ràng

Một runbook cần đủ cụ thể để thực hiện trong sự cố nhưng không biến thành công cụ bypass. Có thể chia thành các bước sau:

### 10.1. Xác định sự cố và thẩm quyền

Chốt mục tiêu phục hồi: đọc dữ liệu lịch sử, khôi phục workload hay tiếp tục ký. Xác định data snapshot, key versions cần thiết, source/target và người/workload được phép thực hiện. Kiểm tra approval/quorum hoặc break-glass theo policy của loại khóa.

Không dùng cùng một lệnh restore tổng quát cho mọi sự cố. Mất thiết bị khác với nghi ngờ private key bị compromise; trong trường hợp sau, khôi phục rồi cho ký mới có thể làm tiếp tục dùng một danh tính đã không còn an toàn.

### 10.2. Chuẩn bị đích phục hồi có giới hạn

Đích phải đúng boundary, capability, trust và mạng được phép. Một máy thử nghiệm thông thường không tự được cấp plaintext key production chỉ vì thao tác đang được gọi là diễn tập.

Staging nên hạn chế quyền sử dụng đến khi hoàn tất kiểm tra. Nếu provider không có trạng thái disabled/import tương ứng, phải có lớp cô lập và policy thay thế đáp ứng mục tiêu, được thiết kế trước khi vận hành.

### 10.3. Xác thực artifact và dependency

Kiểm tra format/version, authenticity/integrity, scope, thời điểm và coverage. Xác nhận wrapping/recovery root, credential/quorum và các resource cần thiết thực sự sẵn có ở đích.

Không đọc một path hoặc URL tùy ý từ backup manifest rồi tải key ngoài policy. Vị trí backup và provider reference cần được resolve trong tập resource của kế hoạch đã duyệt.

### 10.4. Restore và kiểm tra đúng material, binding

Sau bước provider restore/import, đối chiếu logical key version, owner, purpose, thuật toán/capability và khả năng mở dữ liệu canary đã được chuẩn bị. Với symmetric key không xuất, có thể kiểm tra qua phép giải mã/xác thực kiểm soát thay vì kéo raw bytes ra để so sánh.

Physical provider handle ở đích có thể khác reference ban đầu. Cần mapping có thẩm quyền từ logical version sang resource đích theo format/kiến trúc; tạo một key mới với tên cũ không phục hồi được ciphertext dùng material cũ.

Nếu context hoặc envelope ràng buộc key reference, migration/remapping phải giữ đúng hợp đồng xác thực. Không sửa field metadata đến khi decrypt được rồi coi đó là quy trình phục hồi an toàn.

### 10.5. Đối soát trạng thái bảo mật hiện tại

Đọc nguồn trạng thái có thẩm quyền về khóa bị hạn chế, thu hồi hoặc compromise. Không lấy một snapshot cũ của registry làm lý do re-enable khóa đã bị cấm sau thời điểm snapshot.

Khi chưa xác định được trạng thái hiện tại, runbook phải có hành vi rõ. Có thể cần giữ khóa phục hồi ở vùng cô lập và chỉ cho thao tác điều tra được phê duyệt, thay vì tự quay lại active để giảm downtime.

### 10.6. Kiểm tra ứng dụng rồi mới mở quyền cần thiết

Thử đọc dữ liệu canary và một tập bản ghi kiểm soát theo quyền tenant/purpose. Kiểm tra tag/context, reader version, khả năng quan sát và các luồng lỗi. Chỉ mở quyền theo mục tiêu đã chốt: ví dụ decrypt lịch sử, không mặc định encrypt/sign mới.

Đo thời gian tới khi ứng dụng phục hồi khả năng yêu cầu và đối soát dữ liệu không phục hồi được theo RPO. Ghi nhận những khoảng trống và owner xử lý; không báo DR PASS chỉ vì import API trả thành công.

## 11. Restore không được quay lui vòng đời khóa

### 11.1. Khóa lịch sử không tự trở lại active for write

Một key version đã ngừng mã hóa mới có thể vẫn cần để đọc archive. Restore phải giữ giới hạn mục đích đó, kể cả khi bản backup ghi state active ở thời điểm chụp.

Với signing key, việc cần verify tài liệu cũ thường chỉ đòi public key và trust/status phù hợp. Không đưa private key cũ trở lại luồng ký mới chỉ vì nó được phục hồi thành công.

### 11.2. Xét cả trạng thái nonce/counter nếu tiếp tục mã hóa

Nếu một scheme dùng nonce được cấp từ bộ đếm hoặc trạng thái có thể bị rollback, restore key cùng snapshot cũ có thể làm lặp nonce dưới cùng key khi ghi mới. Cần bảo toàn nguồn uniqueness có thẩm quyền hoặc chuyển sang key/profile mới theo kế hoạch phù hợp.

Một phép decrypt thành công không chứng minh an toàn để tiếp tục encrypt. Gate sử dụng sau restore phải kiểm tra đúng thao tác được mở và các invariant của scheme.

### 11.3. Recovery sau compromise có phạm vi khác

Backup có thể giúp tiếp cận dữ liệu hợp lệ trong một quy trình điều tra được kiểm soát, nhưng không làm khóa đã lộ trở thành bí mật lại. Cần đánh giá dữ liệu, artifact và backup bị ảnh hưởng, đồng thời triển khai re-key/migration hoặc cập nhật trust theo use case.

Nếu wrapping/recovery key bị lộ, các backup được bảo vệ dưới khóa đó cũng thuộc phạm vi cần xem xét. Việc đổi khóa active production không tự bảo vệ lại mọi file backup cũ đang nằm ngoài hệ thống.

## 12. Retention và hủy bản backup theo dependency

Giữ backup đủ lâu để đáp ứng dữ liệu và recovery policy, nhưng không giữ mọi secret vô thời hạn. Trước khi xóa một bản key backup hoặc hủy key bảo vệ nó, phải đối soát các data snapshot/archive còn phụ thuộc và các thẩm quyền giữ dữ liệu đã chốt.

| Điều kiện | Quyết định cần có |
| --- | --- |
| Dữ liệu lịch sử còn phải đọc | Giữ đường recovery phù hợp cho các version cần thiết |
| Key ngừng ghi mới nhưng dữ liệu cũ còn tồn tại | Giữ quyền đọc giới hạn, không tự xóa mọi bản sao |
| Một backup đã được thay thế | Kiểm tra coverage, retention và khả năng restore của bản thay trước khi dọn |
| Private key ký không còn mục tiêu giữ | Xét public verification và policy hủy private material riêng |
| Recovery key/wrapping key bị compromise | Xác định backup bị ảnh hưởng và phương án thay cơ chế bảo vệ |
| Hết thời hạn giữ theo policy | Hủy đúng scope, gồm replica/share/cache cần xử lý và bằng chứng tương ứng |

Key deletion/cryptographic erasure phải xét các bản backup, archive, escrow và material trong boundary khác. Nếu một bản sao còn mở được dữ liệu, không công bố rằng việc xóa một resource active đã làm mọi bản ciphertext không thể đọc.

Ngược lại, không tự xóa key production để “kiểm tra backup” khi chưa có quy trình và thẩm quyền thích hợp. Diễn tập phục hồi cần được cô lập và thiết kế để không gây mất dữ liệu hoặc vô tình tạo thêm plaintext không được quản lý.

## 13. Audit và quan sát quá trình phục hồi

Một sự kiện backup/restore cần liên kết operation ID, actor/workload, backup reference, logical key version, source/target, approval reference và kết quả gate. Không ghi raw key, recovery share, password hoặc response provider chưa giảm dữ liệu.

Các trạng thái nên được phân biệt: backup artifact đã tạo, integrity đã xác nhận, bản sao đã chuyển, restore đã hoàn tất ở provider, kiểm tra ứng dụng đạt và quyền sử dụng đã được mở. Một nhãn `SUCCESS` không rõ cấp độ dễ che mất khoảng trống giữa lưu file và phục hồi dịch vụ.

Theo dõi backup quá tuổi, coverage thiếu, credential gần hết hiệu lực, thao tác bị từ chối, restore thất bại và các key chưa có kết quả diễn tập phù hợp. Metrics dùng nhóm/profile/state được kiểm soát, không đưa material hoặc toàn bộ metadata nhạy cảm vào label.

Audit và runbook cũng cần khả năng truy cập khi môi trường production hỏng. Nếu bằng chứng phê duyệt duy nhất nằm trong cùng hệ thống đã mất, quy trình có thể không vận hành được theo RTO hoặc tạo áp lực bỏ kiểm soát trong sự cố.

## 14. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-KB-01 | Mỗi loại key có quyết định backup/archive/không giữ cùng mục tiêu và owner | Inventory theo purpose và thời hạn dữ liệu |
| SR-KB-02 | Mỗi data snapshot phục hồi có coverage key version và dependency cần thiết | Đối soát snapshot–envelope–key–recovery root |
| SR-KB-03 | Backup bảo vệ bí mật material và xác thực metadata/artifact theo format đã duyệt | Kiểm tra cơ chế wrapping/integrity cùng ca tráo/sửa |
| SR-KB-04 | RPO/RTO bao gồm key, credential, registry, target và kiểm tra ứng dụng | Kết quả diễn tập có timeline và phạm vi dữ liệu |
| SR-KB-05 | Boundary và khả năng restore phù hợp provider; không xuất plaintext trái policy để tạo backup | Readback capability/origin/format và ca export bị từ chối |
| SR-KB-06 | Backup, restore, activate và dùng key có quyền/thẩm quyền tách theo rủi ro | Ma trận IAM/quorum và ca một operator không tự hoàn tất mọi bước |
| SR-KB-07 | Recovery root không có vòng phụ thuộc không thể mở; credential/quorum sẵn trong failure scenario | Dependency graph và thử đường bootstrap được kiểm soát |
| SR-KB-08 | Restore không tự kích hoạt khóa đã hạn chế, thu hồi hoặc compromise | Ca snapshot cũ đối chiếu trạng thái hiện tại |
| SR-KB-09 | Sau restore chỉ mở thao tác được phê duyệt và giữ invariant nonce/counter khi có ghi mới | Ca historical decrypt-only và ca tiếp tục encrypt sau restore |
| SR-KB-10 | Bản sao chịu được failure domain đã chọn và quyền xóa/retention được kiểm tra | Diễn tập mất vùng/identity hoặc kịch bản tương ứng |
| SR-KB-11 | Retry/partial restore có trạng thái và reconcile; không báo ứng dụng đã phục hồi chỉ từ API success | Ca timeout, import một phần và đọc lại registry/provider |
| SR-KB-12 | Backup/restore được kiểm tra định kỳ và sau thay đổi ảnh hưởng theo kế hoạch dự án | Lịch/bằng chứng diễn tập, owner và action khắc phục |
| SR-KB-13 | Hủy backup/key chỉ sau khi kiểm tra dependency và retention của đúng scope | Hồ sơ đối soát, phê duyệt và readback kết quả |
| SR-KB-14 | Audit đủ liên kết operation và gate, không chứa material/recovery secret | Kiểm tra log, capture middleware và quyền truy cập audit |

Tần suất backup, thời gian diễn tập và RPO/RTO cụ thể phải do dự án chốt. Các yêu cầu trên cần được bổ sung trị số hoặc gate phù hợp, không để những từ “định kỳ” hay “khôi phục nhanh” là tiêu chí duy nhất.

Với key không có mục tiêu recovery, SR-KB-01 có thể chốt không backup và một chiến lược thay key hợp lệ. Không cố tạo bản sao ngoài boundary chỉ để mọi dòng trong inventory đều có file.

## 15. Thiết kế bằng chứng kiểm chứng

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định các kiểm thử dưới đây đã được thực hiện trong bài học.

### 15.1. Ma trận ca kiểm thử

| Ca | Tình huống | Kỳ vọng |
| --- | --- | --- |
| B1 | Data snapshot cần v3/v4, backup chỉ có v3 | Preflight hoặc gate coverage từ chối; không báo restore đầy đủ |
| B2 | Backup mới về thời gian nhưng thiếu một key version | Timestamp không che mất lỗi coverage |
| B3 | Sửa artifact hoặc manifest, tráo owner/purpose | Phát hiện trước khi chấp nhận scope/material để sử dụng |
| B4 | Operator chỉ có quyền đọc backup | Không tự có quyền unwrap/decrypt/sign hoặc activate |
| B5 | Restore vào target không tương thích hoặc ngoài plan | Từ chối, không xuất material ra boundary khác để lách |
| B6 | Lấy snapshot trước lúc một key bị compromise | Không tự khôi phục state active từ snapshot |
| B7 | Restore historical key chỉ để đọc dữ liệu cũ | Decrypt đúng quyền; encryption/signing mới vẫn bị hạn chế theo policy |
| B8 | Mất một recovery credential/share hoặc vùng đã chốt | Hành vi và RTO đúng thiết kế; không tự bỏ quorum |
| B9 | Provider timeout hoặc restore chỉ hoàn tất một phần | State pending/failed rõ và reconcile đúng; không báo ứng dụng đã sẵn sàng |
| B10 | Restore key cùng counter snapshot cũ rồi chuẩn bị ghi | Gate ngăn nonce reuse hoặc dùng kế hoạch key/state mới đã duyệt |
| B11 | Chuẩn bị hủy một key backup còn ciphertext phụ thuộc | Bị chặn theo dependency/retention policy |
| B12 | Restore đủ dependency và policy hợp lệ | Ứng dụng đọc dữ liệu canary đúng quyền; đo được RPO/RTO |

### 15.2. Canary phải kiểm tra cả ngữ cảnh và quyền

Dùng dữ liệu canary không nhạy cảm nhưng được bảo vệ bằng đúng profile, context và version của môi trường diễn tập. Kiểm tra nội dung khôi phục, integrity tag, tenant/purpose và đường chọn logical key version.

Một canary đơn lẻ không đại diện mọi key version hay format. Chọn mẫu theo coverage cần thiết và bổ sung đối soát inventory. Cần ca quyền âm: identity không được phép vẫn không đọc được dữ liệu sau restore.

### 15.3. Không đánh đồng file tồn tại với khả năng phục hồi

Backup upload thành công chỉ chứng minh artifact đã được ghi theo phản hồi của kho. Cần thử tính toàn vẹn, compatibility, bootstrap credential và khả năng sử dụng ở target theo kế hoạch.

Một blob provider không mở được ngoài boundary có thể là hành vi đúng. Ca kiểm thử phải restore bằng API/đích được hỗ trợ, không kết luận backup hỏng vì không thể tự decrypt file trên laptop.

### 15.4. Kiểm tra lỗi và trạng thái sau lỗi

Sau timeout, kiểm tra provider đã tạo resource nào, key nào còn pending, policy nào đã được gắn và có quyền nào bị mở ngoài ý muốn không. Retry phải dựa vào operation/reconcile đã chốt, không import lặp rồi ghi đè mapping cho tới khi thành công.

Nếu một bước kiểm tra thất bại, cần giữ khóa/material trong trạng thái phù hợp cho điều tra và cleanup theo thẩm quyền. Không có quy tắc chung “lỗi thì xóa hết key target”, vì một resource có thể đã được dùng hoặc thuộc operation khác.

### 15.5. Đo cả khả năng thực hiện của con người và control plane

Diễn tập cần kiểm tra người được chỉ định có thể lấy runbook, hoàn tất approval/quorum, truy cập credential và sử dụng target đúng scope. Đủ file và API nhưng thiếu người có thẩm quyền trong cửa sổ RTO vẫn là một khoảng trống của thiết kế recovery.

Sau diễn tập, ghi các dependency chưa đủ, thời gian từng bước, dữ liệu không phục hồi được và action owner. Không chỉ chụp màn hình một thông báo restore thành công rồi đóng toàn bộ yêu cầu.

## 16. Những giả định cần loại bỏ

**“Database đã backup thì key cũng được backup.”** Ciphertext, wrapped DEK, KEK và registry có thể ở các hệ thống khác nhau với lịch khác nhau. Phải đối soát dependency.

**“Có replication thì chống được mọi lần xóa nhầm.”** Replication có thể phục vụ availability nhưng không tự tách khỏi quyền quản trị hoặc sự kiện thay đổi sai.

**“Non-exportable key không cần kế hoạch DR.”** Cần cơ chế recovery/failover hợp lệ theo provider và threat model; không giải quyết bằng raw export trái policy.

**“Có file encrypted blob thì restore ở đâu cũng được.”** Format có thể bị ràng buộc với provider, account, region/geography, boundary hoặc security domain.

**“Restore snapshot là đưa mọi key trở lại active.”** Phải đối chiếu trạng thái bảo mật hiện tại và chỉ mở thao tác đã được duyệt.

**“Đổi một key mới cùng tên sẽ mở được dữ liệu cũ.”** Tên/reference không thay material. Logical version mapping và context phải được giữ đúng.

**“Giữ càng nhiều bản sao càng an toàn.”** Mỗi bản sao thêm quyền recovery và nghĩa vụ bảo vệ; cần số bản/failure domain/retention có mục tiêu.

**“Hủy key active đã xóa mọi khả năng đọc ciphertext.”** Backup, archive, wrapped material và các boundary khác có thể còn giữ đường phục hồi.

## 17. Bài tập vận dụng

Một nền tảng lưu báo cáo mã hóa theo envelope encryption. Data snapshot mới nhất dùng KEK v5, nhưng lịch backup key chưa xác nhận v5. Một snapshot registry cũ còn ghi signing key đã compromise là active. Kế hoạch DR hiện chỉ yêu cầu tải các file backup về một máy quản trị rồi thử import.

Hãy thiết kế quy trình thay thế:

1. Lập dependency graph cho data snapshot, wrapped DEK, KEK, registry và recovery credential.
2. Chốt coverage cùng RPO/RTO, chỉ ra gate trước khi dùng key version mới nếu policy yêu cầu.
3. Chọn target và cơ chế restore đúng boundary/provider, không mặc định raw material được xuất.
4. Thiết kế bước đối soát trạng thái hiện tại để không re-enable signing key đã compromise.
5. Tách quyền backup, restore, activate và sử dụng; mô tả approval/quorum phù hợp.
6. Viết ba ca nghiệm thu chứng minh dữ liệu đọc được đúng quyền, key thiếu bị phát hiện và lỗi một phần không tạo trạng thái thành công giả.

Kết quả cần chứng minh không chỉ rằng một bản sao tồn tại, mà rằng khả năng mật mã được phục hồi đúng dữ liệu, đúng boundary và đúng thẩm quyền. Key backup có giá trị khi đường recovery vận hành được trong sự cố mà vẫn giữ nguyên các giới hạn bảo mật cần thiết.
