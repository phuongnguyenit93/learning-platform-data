# File replacement policy

## Mục tiêu bài học

File replacement policy là tập quy tắc quyết định ai được thay một tệp, thay vào thời điểm nào, phiên bản mới cần qua những bước kiểm tra gì và việc thay thế ảnh hưởng thế nào tới phê duyệt, lịch sử, liên kết tải xuống và các nghiệp vụ đã sử dụng phiên bản cũ.

Trong bảo mật logic nghiệp vụ, thao tác “thay file” thường làm thay đổi bằng chứng mà một quyết định đã dựa vào. Ví dụ, người duyệt chấp thuận một hóa đơn nhưng sau đó người nộp thay nội dung ở cùng đường dẫn. Nếu hệ thống chỉ giữ tên file và trạng thái `APPROVED`, quyết định phê duyệt có thể bị gắn nhầm với nội dung chưa từng được xem xét.

Sau bài học, bạn có thể:

- Định nghĩa quyền thay file theo đối tượng và trạng thái nghiệp vụ.
- Tách phiên bản nội dung khỏi tên file và con trỏ phiên bản hiện tại.
- Thiết kế quy trình thay thế có vùng cách ly, quét, xác nhận và kích hoạt.
- Bảo vệ phê duyệt, bất biến dữ liệu, tính nguyên tử và idempotency.
- Kiểm thử các tình huống thay bằng chứng, thay đồng thời và dùng lại kết quả kiểm tra của file khác.

## 1. Phân biệt các thao tác thường bị gọi chung là “thay file”

| Thao tác | Nội dung thực tế | Câu hỏi chính sách |
|---|---|---|
| Đổi tên hiển thị | Đổi metadata, giữ nguyên byte nội dung | Có được đổi tên sau khi nộp hồ sơ không? |
| Tải phiên bản ứng viên | Lưu nội dung mới nhưng chưa dùng làm tài liệu chính thức | Ai được tải lên, ứng viên tồn tại bao lâu? |
| Kích hoạt phiên bản mới | Đổi phiên bản mà hồ sơ đang sử dụng | Hồ sơ còn cho sửa không, cần hủy phê duyệt nào? |
| Đính chính sau phê duyệt | Tạo tài liệu hoặc hồ sơ điều chỉnh có liên kết với bản đã duyệt | Ai có quyền mở quy trình điều chỉnh và duyệt lại? |
| Xóa nội dung vật lý | Loại bỏ byte khỏi nơi lưu trữ | Có tham chiếu, thời hạn lưu giữ hoặc yêu cầu giữ lại nào không? |

Quyền upload không tự tạo ra quyền kích hoạt. Quyền sửa hồ sơ cũng không tự cho phép xóa mọi phiên bản lịch sử. Một endpoint nhận file thành công chưa có nghĩa rằng phiên bản đó đã trở thành bằng chứng có hiệu lực.

Tên hiển thị như `hoa-don.pdf` không phải định danh đáng tin cậy của nội dung. Hai file có cùng tên có thể khác hoàn toàn, còn hai tên khác nhau có thể chứa cùng byte.

## 2. Tình huống xuyên suốt: thay hóa đơn trong hồ sơ hoàn ứng

Giả sử mỗi hồ sơ hoàn ứng có một vị trí đính kèm hóa đơn, gọi là `attachment slot`. Một slot có thể có nhiều phiên bản lịch sử nhưng chỉ có tối đa một phiên bản hiện tại.

Hồ sơ đi qua các trạng thái:

```text
DRAFT -> SUBMITTED -> APPROVED -> PAID
                  -> CHANGES_REQUESTED -> SUBMITTED
DRAFT hoặc CHANGES_REQUESTED -> CANCELLED
```

Các chuyển trạng thái cần được triển khai bằng service nghiệp vụ với quyền và điều kiện riêng. Sơ đồ chỉ mô tả những nhánh cần cho bài học.

Chính sách thay file của ví dụ:

| Trạng thái hồ sơ | Thay phiên bản hiện tại? | Điều kiện |
|---|---|---|
| `DRAFT` | Có | Chủ hồ sơ hoặc người được ủy quyền còn quyền thay tài liệu |
| `CHANGES_REQUESTED` | Có | Đúng phạm vi được sửa; khi nộp lại phải tạo lần xét duyệt mới |
| `SUBMITTED` | Không | Muốn sửa phải qua thao tác rút hồ sơ hoặc yêu cầu bổ sung được thiết kế riêng |
| `APPROVED` | Không | Tạo quy trình đính chính hoặc điều chỉnh liên kết với hồ sơ đã duyệt |
| `PAID` | Không | Thực hiện nghiệp vụ điều chỉnh tài chính phù hợp, giữ bằng chứng đã dùng khi thanh toán |
| `CANCELLED` | Không | Hồ sơ không còn mở để chỉnh sửa |

Đây là chính sách minh họa, không phải quy định bắt buộc cho mọi sản phẩm. Một hệ thống khác có thể cho phép thay file khi đang xét duyệt, nhưng phải chuyển hồ sơ về trạng thái cần duyệt lại và vô hiệu hóa những quyết định bị ảnh hưởng trong cùng một thao tác nhất quán.

Trong bài học này, không có ngoại lệ “quản trị viên được ghi đè mọi trạng thái”. Quyền xử lý ngoại lệ, nếu cần, phải là một thao tác nghiệp vụ riêng có phạm vi, lý do, audit và quy trình phê duyệt tương ứng.

## 3. Các bất biến cần bảo vệ

Trước khi viết API, hãy diễn đạt các điều kiện luôn phải đúng:

1. **Đúng phạm vi:** hồ sơ, slot, phiên bản ứng viên và chủ thể thực hiện cùng nằm trong phạm vi tenant được phép.
2. **Đúng đối tượng:** quyền thay file được kiểm tra trên hồ sơ và slot cụ thể, không chỉ trên endpoint upload.
3. **Nội dung đã chốt không bị ghi đè:** một phiên bản đã hoàn tất upload và được định danh không đổi byte trong suốt thời gian tồn tại.
4. **Đúng nội dung đã kiểm tra:** kết quả quét và kiểm tra định dạng áp dụng cho đúng phiên bản, object trong storage và digest đang được kích hoạt.
5. **Không mất cập nhật:** kích hoạt chỉ thành công nếu phiên bản hồ sơ và slot còn phù hợp với điều kiện mà yêu cầu đã dựa vào.
6. **Không mượn phê duyệt:** quyết định phê duyệt tham chiếu đúng snapshot nội dung, không tự chuyển hiệu lực sang phiên bản mới.
7. **Một kết quả nghiệp vụ khi retry:** gửi lại cùng yêu cầu không tạo thêm phiên bản có hiệu lực, audit thành công hoặc thông báo nghiệp vụ trùng.
8. **Lịch sử còn được giải thích:** sau thay thế vẫn xác định được ai thay, từ phiên bản nào sang phiên bản nào, vì sao và trong trạng thái nào.

Một file có định dạng PDF hợp lệ vẫn có thể vi phạm bất biến số 6 nếu được thay vào sau khi người duyệt đã xem bản cũ. Quét mã độc giải quyết một nhóm rủi ro nội dung, không chứng minh việc thay thế là hợp lệ về nghiệp vụ.

## 4. Mô hình phiên bản: tạo bản mới rồi đổi tham chiếu

### 4.1. Không ghi đè object đang được sử dụng

Cách triển khai nguy hiểm thường có dạng:

```text
storageKey = "reports/" + reportId + "/invoice.pdf"
upload(newBytes, storageKey)
```

Nếu object ở đường dẫn này bị ghi đè, mọi nơi đang đọc đường dẫn đó có thể nhận nội dung mới trong khi metadata phê duyệt, kết quả quét hoặc dữ liệu cache vẫn mô tả nội dung cũ.

Thiết kế tốt hơn là tạo object riêng cho mỗi lần upload, giữ object ở chế độ riêng tư và chỉ đổi con trỏ trong cơ sở dữ liệu sau khi mọi điều kiện đã đạt:

```text
Slot hóa đơn của hồ sơ R
    currentVersionId = V7

V7 -> object riêng O7 -> SHA-256 H7
V8 -> object riêng O8 -> SHA-256 H8 -> đang chờ kiểm tra

Kích hoạt thành công:
    currentVersionId = V8
    slotRevision = slotRevision + 1

V7 vẫn là phiên bản lịch sử; byte của O7 không bị thay bằng O8.
```

Dùng khóa object mới cho từng upload thường dễ kiểm soát hơn việc ghi đè một khóa rồi dựa vào cấu hình versioning. Nếu storage hỗ trợ generation hoặc version ID, lưu định danh đó và sử dụng nó khi đọc, quét hoặc phục vụ nội dung.

Không coi ETag của storage luôn là SHA-256 hoặc checksum nội dung theo ý nghĩa mà ứng dụng cần. Lưu digest ứng dụng tính trên nội dung thực tế và định danh phiên bản storage theo hợp đồng của storage đang sử dụng.

### 4.2. Các bản ghi cần có trách nhiệm rõ ràng

| Thành phần | Dữ liệu điển hình | Trách nhiệm |
|---|---|---|
| `Report` | Tenant, chủ hồ sơ, trạng thái, revision | Bảo vệ vòng đời nghiệp vụ |
| `AttachmentSlot` | Hồ sơ cha, loại tài liệu, `currentVersionId`, revision | Xác định phiên bản hiện tại của vị trí tài liệu |
| `FileVersion` | ID, slot, object key, storage generation, digest, kích thước, người tải | Định danh nội dung đã chốt |
| `ReplacementRequest` | Ứng viên, revision kỳ vọng, trạng thái, khóa idempotency, kết quả | Theo dõi một thao tác thay thế |
| `ScanAttestation` | Phiên bản, generation, digest, verdict, phiên bản chính sách, thời hạn | Chứng minh nội dung cụ thể đã được dịch vụ tin cậy kiểm tra |
| `ApprovalRecord` | Snapshot hồ sơ, các phiên bản tài liệu và quyết định | Gắn phê duyệt với bằng chứng đã xem |
| `AuditEvent` và outbox | Chủ thể, bản cũ, bản mới, kết quả, sự kiện cần phát | Truy vết và phát hiệu ứng ngoài transaction |

Mô hình lưu trữ cần ngăn `currentVersionId` trỏ sang một phiên bản thuộc slot khác. Có thể sử dụng khóa ngoại ghép theo tenant, slot và phiên bản hoặc một mô hình tương đương, kết hợp kiểm tra nghiệp vụ.

Các trường như `tenantId`, `createdBy`, kết quả quét, revision hiện tại và trạng thái phê duyệt phải do phía máy chủ quản lý. Không ánh xạ chúng từ form upload hoặc JSON do người dùng gửi vào.

### 4.3. Tách trạng thái yêu cầu, kết quả quét và phiên bản hiện tại

Một quy trình ứng viên có thể dùng:

```text
UPLOADING -> QUARANTINED -> SCANNING -> READY -> COMMITTED
                        -> REJECTED
               SCANNING -> REJECTED
                  READY -> EXPIRED
```

Lỗi hạ tầng khi quét có thể được lưu riêng để retry có kiểm soát. Không chuyển một lần quét lỗi hoặc chưa có kết luận thành `READY`.

`COMMITTED` có nghĩa yêu cầu thay thế đã được áp dụng thành công tại một thời điểm. Nó không có nghĩa phiên bản đó mãi là bản hiện tại: một lần thay tiếp theo có thể chuyển con trỏ sang bản khác. Muốn biết bản hiện tại phải đọc `AttachmentSlot.currentVersionId`.

Tương tự, việc một bản không còn hiện tại không chứng minh nó được phép xóa; bản đó có thể vẫn là bằng chứng trong một lần phê duyệt hoặc thanh toán.

## 5. Kiểm tra quyền theo đối tượng và trạng thái

Máy chủ cần kiểm tra đồng thời:

- Chủ thể có quyền truy cập hồ sơ trong tenant đang được xác thực.
- Slot thuộc đúng hồ sơ và đúng loại tài liệu được phép thay.
- Chủ thể có quyền thay nội dung slot, thông qua vai trò, quyền sở hữu hoặc ủy quyền hợp lệ.
- Trạng thái hồ sơ cho phép thay ở thời điểm kích hoạt.
- Ứng viên thuộc đúng slot và cùng phạm vi dữ liệu.

Không dựa vào việc người dùng đoán được hoặc gửi được `fileVersionId`. UUID khó đoán vẫn không phải một cơ chế cấp quyền.

Một phiên bản ứng viên do người dùng có quyền tải lên không được chuyển sang hồ sơ khác chỉ bằng cách đổi `reportId` trong request kích hoạt. Máy chủ phải kiểm tra quan hệ giữa yêu cầu thay thế, ứng viên, slot và hồ sơ cha từ dữ liệu tin cậy.

Tác vụ nền cần thực hiện đúng chính sách ủy quyền. Trong ví dụ này, quyền thay được kiểm tra lại khi kích hoạt. Nếu người được ủy quyền bị thu hồi quyền sau upload, worker không được dùng quyền rộng của service account để hoàn tất thay thế thay họ.

Nếu nghiệp vụ yêu cầu phân tách người nộp và người duyệt, việc thay file không được tự làm chủ thể trở thành người phê duyệt. Quyền thay nội dung và quyền chấp thuận nội dung là hai quyết định khác nhau.

## 6. Upload, cách ly và ràng buộc kết quả kiểm tra

Một luồng thay thế có thể gồm các bước sau:

1. Tạo `ReplacementRequest` với hồ sơ đích, slot và revision kỳ vọng; kiểm tra quyền sớm.
2. Cấp quyền upload chỉ tới object ứng viên mới, riêng tư, có kích thước và thời hạn theo chính sách.
3. Khi upload hoàn tất, máy chủ xác nhận kích thước, định dạng và digest trên nội dung thực tế.
4. Chốt object hoặc pin đúng generation; các quyền upload còn sống không được làm thay đổi nội dung sẽ được kích hoạt.
5. Đưa nội dung vào vùng cách ly, chạy các kiểm tra cần thiết và lưu kết quả gắn với phiên bản đã chốt.
6. Chuyển ứng viên sang `READY` khi các kiểm tra bắt buộc đã đạt.
7. Kích hoạt trong transaction sau khi kiểm tra lại quyền, trạng thái và revision.

Các bước kiểm tra nội dung có thể gồm giới hạn dung lượng, loại file, chữ ký định dạng, parser an toàn, chống mã độc và quy tắc nghiệp vụ về tài liệu. Không chỉ tin phần mở rộng hoặc `Content-Type` do trình duyệt khai báo.

Kết quả quét cần ràng buộc tối thiểu với:

```text
fileVersionId
storageGeneration
contentDigest
scanPolicyRevision
verdict
scannedAt / validUntil theo chính sách
```

Dịch vụ quét phải đọc chính object mà bản ghi phiên bản chỉ tới. Các trường này do dịch vụ tin cậy tạo và được lưu trong phạm vi được bảo vệ; một JSON có `verdict=CLEAN` do người dùng gửi không phải bằng chứng quét.

Khi kích hoạt, không nhận mỗi cờ `scanPassed=true`. Nếu byte được thay sau quét, digest hoặc generation không còn khớp thì kết quả quét cũ không áp dụng cho nội dung mới. Đây là một dạng khoảng trống giữa thời điểm kiểm tra và sử dụng, thường được gọi là TOCTOU.

Hash bằng nhau không chứng minh tài liệu được phép sử dụng hoặc không có mã độc. Hash giúp ràng buộc đúng nội dung đã được kiểm tra; quyền, trạng thái và kết luận kiểm tra vẫn có trách nhiệm riêng.

Nếu bước làm sạch tài liệu tạo ra byte mới, coi đầu ra đó là một nội dung được định danh riêng, lưu quan hệ với bản nguồn và kiểm tra đầu ra theo chính sách trước khi kích hoạt. Không gắn digest của bản nguồn lên một object đã biến đổi.

## 7. Kích hoạt bằng transaction và kiểm soát đồng thời

### 7.1. Lưu storage và đổi con trỏ có hai ranh giới khác nhau

Storage object và cơ sở dữ liệu thường không tham gia cùng một transaction. Một chiến lược thực dụng là hoàn tất ứng viên bất biến trước, sau đó dùng transaction cơ sở dữ liệu để đổi con trỏ.

- Upload thất bại: con trỏ hiện tại không đổi.
- Quét thất bại: con trỏ hiện tại không đổi.
- Ứng viên đạt kiểm tra nhưng transaction thất bại: bản hiện tại vẫn giữ nguyên; ứng viên có thể được thử lại hoặc thu dọn theo chính sách.
- Transaction thành công nhưng mất phản hồi: retry đọc lại kết quả đã lưu qua idempotency.

Không xóa bản cũ trước khi kích hoạt bản mới. Cũng không đổi con trỏ trước rồi mới hy vọng lần quét nền sẽ thành công.

### 7.2. Revision kỳ vọng giúp phát hiện ý định đã cũ

Giả sử A và B cùng mở hồ sơ ở `slotRevision=7`. Cả hai tải ứng viên khác nhau. A kích hoạt thành công và đưa revision lên 8. Yêu cầu của B vẫn mang revision kỳ vọng là 7 nên phải nhận xung đột, thay vì âm thầm thay luôn bản mà A vừa chọn.

Revision do client gửi là điều kiện so sánh, không phải nguồn dữ liệu đáng tin để cập nhật revision hiện tại. Máy chủ đọc trạng thái thật và tự tăng revision sau khi thao tác thành công.

Nếu việc thay file ảnh hưởng snapshot toàn hồ sơ, kiểm tra thêm `reportRevision`. Điều này giúp phát hiện hồ sơ đã được sửa hoặc chuyển trạng thái dù slot tài liệu chưa thay đổi.

Một thao tác đổi con trỏ có điều kiện có thể có dạng:

```sql
UPDATE attachment_slot
SET current_version_id = :candidateVersionId,
    revision = revision + 1
WHERE tenant_id = :authenticatedTenantId
  AND id = :slotId
  AND report_id = :reportId
  AND revision = :expectedSlotRevision;
```

Nếu số dòng cập nhật không bằng 1, transaction không được tiếp tục như thành công. Câu SQL chỉ minh họa phần đổi con trỏ, chưa thay thế kiểm tra quyền, trạng thái, kết quả quét và cập nhật revision hồ sơ.

### 7.3. Thay file và phê duyệt phải dùng cùng quy ước đồng thời

Đổi con trỏ có điều kiện trên slot chưa đủ để ngăn phê duyệt chạy đồng thời nếu đường phê duyệt không kiểm soát cùng aggregate.

Một quy ước có thể là luôn khóa hồ sơ cha trước, rồi khóa slot và yêu cầu thay thế theo thứ tự ổn định. Cả thay file, nộp hồ sơ, yêu cầu sửa và phê duyệt đều tuân thủ quy ước đó. Hoặc hệ thống dùng optimistic locking nhất quán trên revision của hồ sơ và rollback khi phát hiện xung đột.

Nhờ vậy, nếu nộp hoặc phê duyệt thắng trước, thao tác thay file nhìn thấy trạng thái không cho sửa và thất bại. Nếu thay file thắng trước, thao tác tiếp theo phải làm việc với snapshot mới hoặc báo xung đột với snapshot mà người thao tác đã xem.

Chỉ một endpoint dùng khóa đúng không tạo ra bảo đảm cho toàn hệ thống nếu một đường ghi khác vẫn đổi trạng thái hoặc con trỏ trực tiếp.

## 8. Ví dụ Java: guard cho một lần kích hoạt mới

Ví dụ Java 17 dưới đây minh họa các điều kiện phía service. Các snapshot được tải từ nguồn tin cậy, có trường bắt buộc không null và đã parse kiểu; chúng không phải object được ánh xạ trực tiếp từ request.

Guard được gọi trong transaction với quy ước khóa hoặc optimistic locking phù hợp. Nó chưa thực hiện I/O storage, đổi con trỏ, idempotency, audit hay cập nhật phê duyệt.

```java
import java.time.Instant;
import java.util.UUID;

public final class ReplacementPolicy {
    public enum ReportState {
        DRAFT, SUBMITTED, CHANGES_REQUESTED, APPROVED, PAID, CANCELLED
    }

    public enum CandidateState {
        UPLOADING, QUARANTINED, SCANNING, READY,
        REJECTED, EXPIRED, COMMITTED
    }

    public enum ScanVerdict {
        CLEAN, UNSAFE, ERROR
    }

    public record Actor(UUID tenantId, UUID userId) {}

    public record Report(
            UUID id, UUID tenantId, UUID ownerId,
            ReportState state, long revision) {}

    public record Slot(
            UUID id, UUID tenantId, UUID reportId, long revision) {}

    public record Candidate(
            UUID tenantId, UUID slotId, UUID fileVersionId,
            CandidateState state, Instant expiresAt) {}

    public record FileVersion(
            UUID id, UUID tenantId, UUID slotId,
            String storageGeneration, String sha256) {}

    public record ScanProof(
            UUID fileVersionId, String storageGeneration, String sha256,
            long policyRevision, ScanVerdict verdict, Instant validUntil) {}

    public record ExpectedRevisions(long report, long slot) {}

    public interface Authorization {
        boolean canReplace(Actor actor, Report report, Slot slot);
    }

    public static final class PolicyViolation extends RuntimeException {
        private final String code;

        public PolicyViolation(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public static void validateNewActivation(
            Actor actor,
            Report report,
            Slot slot,
            Candidate candidate,
            FileVersion file,
            ScanProof proof,
            ExpectedRevisions expected,
            Authorization authorization,
            long requiredScanPolicyRevision,
            Instant now) {

        boolean sameScope =
                actor.tenantId().equals(report.tenantId())
                && actor.tenantId().equals(slot.tenantId())
                && actor.tenantId().equals(candidate.tenantId())
                && actor.tenantId().equals(file.tenantId())
                && report.id().equals(slot.reportId())
                && slot.id().equals(candidate.slotId())
                && slot.id().equals(file.slotId())
                && file.id().equals(candidate.fileVersionId());
        require(sameScope, "RESOURCE_NOT_ACCESSIBLE");

        require(authorization.canReplace(actor, report, slot),
                "RESOURCE_NOT_ACCESSIBLE");

        require(report.revision() == expected.report()
                && slot.revision() == expected.slot(), "STALE_REVISION");

        require(report.state() == ReportState.DRAFT
                || report.state() == ReportState.CHANGES_REQUESTED,
                "REPLACEMENT_NOT_ALLOWED_IN_STATE");

        require(candidate.state() == CandidateState.READY,
                "CANDIDATE_NOT_READY");
        require(candidate.expiresAt().isAfter(now), "CANDIDATE_EXPIRED");
        require(proof != null, "SCAN_REQUIRED");

        boolean sameContent =
                file.id().equals(proof.fileVersionId())
                && file.storageGeneration().equals(proof.storageGeneration())
                && file.sha256().equals(proof.sha256());
        require(sameContent, "SCAN_CONTENT_MISMATCH");

        require(proof.verdict() == ScanVerdict.CLEAN, "SCAN_NOT_CLEAN");
        require(proof.policyRevision() == requiredScanPolicyRevision,
                "SCAN_POLICY_CHANGED");
        require(proof.validUntil().isAfter(now), "SCAN_EXPIRED");
    }

    private static void require(boolean condition, String code) {
        if (!condition) {
            throw new PolicyViolation(code);
        }
    }
}
```

Các lựa chọn trong ví dụ cần được hiểu đúng:

- `Authorization` là dịch vụ quyết định quyền từ dữ liệu và chính sách tin cậy; không nhận một boolean quyền từ client.
- Scan proof phải do dịch vụ tin cậy cung cấp. So khớp các trường không xác thực được một proof do người dùng tự tạo.
- Ví dụ yêu cầu chính xác phiên bản chính sách quét hiện hành và thời hạn còn hiệu lực. Sản phẩm có thể chọn chính sách tương thích hoặc tái quét khác, nhưng phải diễn đạt rõ.
- `Instant now` phải do máy chủ cung cấp từ đồng hồ tin cậy, thuận tiện cho kiểm thử thời hạn.
- Qua guard chưa có nghĩa thao tác đã thành công. Việc đổi con trỏ và ghi kết quả cần transaction; race condition không được giải quyết chỉ bằng một hàm `if`.

## 9. Ràng buộc phê duyệt với đúng phiên bản nội dung

### 9.1. Phê duyệt một snapshot, không phê duyệt một tên file

Một bản ghi phê duyệt nên chỉ tới snapshot đã được xem xét, chẳng hạn:

```text
reportId = R
submittedReportRevision = 42
attachments = [
    { slotId: S1, fileVersionId: V7, digest: H7 },
    { slotId: S2, fileVersionId: V3, digest: H3 }
]
approvedBy = reviewer
```

Bản ghi snapshot có thể được biểu diễn bằng manifest lưu riêng, manifest digest và các quan hệ phiên bản. Điều quan trọng là có thể xác định chính xác các nội dung được quyết định phê duyệt sử dụng.

Đường tải tài liệu từ màn hình quyết định phê duyệt phải lấy đúng phiên bản trong snapshot, không tra lại “file hiện tại” rồi giả định nó vẫn là nội dung đã duyệt.

### 9.2. Hồ sơ bị yêu cầu sửa cần lần xét duyệt mới

Khi chuyển sang `CHANGES_REQUESTED`, hệ thống phải xác định quyết định hoặc bước duyệt nào không còn là phê duyệt đang có hiệu lực. Những bản ghi cũ có thể vẫn được giữ làm lịch sử, với liên kết tới snapshot cũ.

Sau khi thay tài liệu và nộp lại, hệ thống tạo snapshot mới. Không sao chép trạng thái chấp thuận của snapshot cũ sang tài liệu mới chỉ vì cùng một slot hoặc cùng tên `hoa-don.pdf`.

Nếu một sản phẩm cho phép sửa trong lúc đang xét duyệt, transaction sửa phải đồng thời thực hiện chuyển trạng thái và vô hiệu hóa các chấp thuận bị ảnh hưởng. Gửi một event để “sau đó sẽ hủy duyệt” có thể để lại khoảng thời gian nội dung mới mang trạng thái đã được chấp thuận sai.

### 9.3. Hồ sơ đã thanh toán cần nghiệp vụ điều chỉnh

Với hồ sơ đã `PAID`, thay byte của hóa đơn gốc làm mất khả năng giải thích quyết định thanh toán. Một hướng xử lý là tạo hồ sơ điều chỉnh hoặc tài liệu đính chính có liên kết với phiên bản đã dùng, có quyền và phê duyệt riêng.

Không tự suy luận rằng bất kỳ file mới nào cũng là một bản đính chính hợp lệ. Chủ thể, lý do và ảnh hưởng nghiệp vụ của điều chỉnh vẫn cần được kiểm soát.

## 10. Idempotency và phục hồi sau lỗi

### 10.1. Phân biệt retry với một ý định thay thế mới

Người dùng có thể bấm lại do mất mạng. Worker cũng có thể nhận lại cùng một message. Những lần xử lý đó phải dẫn tới cùng kết quả nghiệp vụ nếu chúng đại diện cho một yêu cầu đã được áp dụng.

Một fingerprint của thao tác kích hoạt có thể bao gồm:

```text
operationType
reportId
slotId
candidateFileVersionId
candidateDigest
expectedReportRevision
expectedSlotRevision
```

Các giá trị nội dung trong fingerprint được lấy hoặc đối chiếu với metadata phía máy chủ. Tên file không đủ để nhận diện thao tác.

Khóa idempotency phải có phạm vi, ví dụ tenant, loại thao tác và slot, cùng ràng buộc duy nhất trong cơ sở dữ liệu. Cùng khóa nhưng fingerprint khác phải báo xung đột.

Nếu yêu cầu đã `COMMITTED`, retry không được chạy lại guard như một lần thay mới rồi báo xung đột chỉ vì revision đã tăng. Sau khi xác thực quyền đọc kết quả và kiểm tra fingerprint, trả lại kết quả đã lưu, gồm phiên bản đã kích hoạt và revision tại lần commit đó. Kiểm tra này cũng cần đi trước điều kiện hết hạn của ứng viên dành cho một lần kích hoạt mới.

Nếu sau đó một người khác đã thay sang bản tiếp theo, kết quả retry vẫn mô tả thao tác cũ. Nó không được đổi con trỏ ngược về phiên bản đã commit trong quá khứ.

### 10.2. Phác thảo transaction kích hoạt

```text
activate(actor, replacementRequestId, idempotencyKey):
    lấy metadata định tuyến đúng tenant từ request phía máy chủ

    bắt đầu transaction
        khóa report -> slot -> replacement request theo quy ước chung
        kiểm tra tenant, quan hệ đối tượng và quyền truy cập kết quả
        đối chiếu khóa idempotency và fingerprint

        nếu thao tác đã commit:
            trả kết quả đã lưu, không áp dụng lại hiệu ứng

        kiểm tra quyền thay và trạng thái hồ sơ cho lần thực thi mới
        kiểm tra revision kỳ vọng
        kiểm tra ứng viên READY, thời hạn và proof đúng nội dung
        kiểm tra các điều kiện nghiệp vụ của loại tài liệu

        đổi currentVersionId bằng cập nhật có điều kiện
        tăng revision hồ sơ và slot
        lưu kết quả và đánh dấu replacement request COMMITTED
        ghi audit và outbox trong cùng transaction
    commit transaction
```

Đây là phác thảo; việc nhận quyền xử lý idempotency cần dùng khóa hoặc ràng buộc duy nhất phù hợp để hai lần thực thi không cùng thắng. Các đường ghi liên quan phải dùng thứ tự khóa nhất quán để hạn chế deadlock và bảo vệ cùng bất biến.

Nếu audit hoặc trạng thái job nằm ở một hệ thống khác, không thể mặc nhiên coi chúng thuộc cùng transaction cơ sở dữ liệu. Cần một thiết kế phối hợp và phục hồi tương ứng.

### 10.3. Hiệu ứng ngoài cơ sở dữ liệu

Gửi thông báo, cập nhật chỉ mục tìm kiếm hoặc thu dọn ứng viên có thể chạy sau commit thông qua outbox. Consumer cần chống xử lý trùng theo event ID hoặc revision và tránh để sự kiện cũ ghi đè trạng thái mới.

Ví dụ, event thay V7 thành V8 đến sau event thay V8 thành V9 không được làm chỉ mục hiện tại quay lại V8. Consumer có thể so revision hoặc đọc trạng thái chuẩn từ cơ sở dữ liệu, tùy thiết kế.

Nếu transaction thất bại sau khi object ứng viên đã tồn tại, object đó trở thành ứng viên chưa dùng; không có nghĩa phiên bản cũ cần bị xóa. Job dọn dẹp chỉ được xóa khi đã kiểm tra không có tham chiếu hoặc yêu cầu đang có hiệu lực, cùng thời gian đệm và cơ chế phối hợp tránh tranh chấp với kích hoạt.

## 11. Tải xuống, liên kết chia sẻ và cache sau thay thế

Có hai ngữ nghĩa đường đọc cần phân biệt:

| Đường đọc | Ý nghĩa |
|---|---|
| Tài liệu hiện tại của slot | Tra quyền, đọc con trỏ hiện tại, phục vụ phiên bản tương ứng |
| Tài liệu thuộc một snapshot lịch sử | Tra quyền với snapshot, phục vụ chính xác phiên bản được tham chiếu |

Quyền xem bản hiện tại không nhất thiết cho phép xem tất cả lịch sử. Lịch sử có thể chứa thông tin nhạy cảm đã được thay ra; quyền truy cập cần được quyết định theo chính sách của hồ sơ.

URL có chữ ký nên trỏ tới object hoặc generation cụ thể, có phạm vi và thời hạn phù hợp. Với object bất biến, URL cũ không tự đổi thành nội dung mới. Tuy nhiên, URL cũ đã cấp có thể vẫn truy cập được cho tới khi hết hạn theo khả năng storage; đổi con trỏ trong cơ sở dữ liệu không tự thu hồi URL đó.

Nếu cần thu hồi quyền gần như ngay lập tức, cân nhắc phục vụ qua lớp kiểm tra quyền mỗi lần tải hoặc cơ chế thu hồi mà hạ tầng thực sự hỗ trợ. Không hứa bảo đảm này chỉ bằng việc đặt thời hạn URL ngắn.

Cache theo file version giúp tránh dùng lại nội dung cũ cho định danh mới. Với endpoint “hiện tại”, cần cơ chế làm mới phù hợp và vẫn phải bảo vệ quyền; cache công khai theo `slotId` không đủ cho dữ liệu riêng tư.

Nếu sau này một phiên bản bị phát hiện không an toàn, hệ thống có thể chặn truy cập hoặc đánh dấu cần xử lý theo chính sách. Không âm thầm phục vụ bản hiện tại khác thay cho bản trong snapshot đã duyệt, vì điều đó làm sai bằng chứng của quyết định cũ.

## 12. Lưu giữ và xóa phiên bản cũ

Thay thế không đồng nghĩa xóa. Một phiên bản cũ có thể còn được tham chiếu bởi:

- Snapshot nộp hồ sơ hoặc quyết định phê duyệt.
- Quyết định thanh toán và nghiệp vụ điều chỉnh.
- Audit, yêu cầu điều tra hoặc chính sách lưu giữ của tổ chức.
- Một quy trình khác được phép sử dụng chính phiên bản đó.

Nếu nội dung được dùng chung hoặc storage có deduplication, việc một slot ngừng dùng file không chứng minh object vật lý không còn tham chiếu. Quyền trên một hồ sơ cũng không cấp quyền xóa object mà hồ sơ khác còn sử dụng.

Quy trình xóa nên tách quyền yêu cầu xóa, đánh giá điều kiện lưu giữ, thời điểm thực hiện và audit kết quả. Các thời hạn cụ thể phải theo chính sách áp dụng của tổ chức; không tự suy ra từ việc phiên bản đã bị thay thế.

Ứng viên bị từ chối hoặc hết hạn cũng cần lịch dọn dẹp rõ ràng. Không để một job thu gom chỉ dựa trên tuổi object và tranh chấp với transaction đang kích hoạt nó.

## 13. Phản hồi lỗi và trải nghiệm thao tác

Một lỗi revision có thể trả cấu trúc ổn định như:

```json
{
  "code": "STALE_REVISION",
  "message": "Hồ sơ đã thay đổi. Hãy tải lại thông tin trước khi thay tài liệu.",
  "replacementRequestId": "request-123",
  "candidateStatus": "READY"
}
```

Mã HTTP và các trường bổ sung cần theo hợp đồng của dịch vụ. Chỉ trả thông tin ứng viên hoặc revision hiện tại khi chủ thể được phép biết chúng. Với đối tượng ngoài quyền, tránh thông báo chi tiết giúp phân biệt tài liệu của tenant khác.

Giao diện cần phân biệt rõ:

- “Đã tải lên” với “Đã thay tài liệu thành công”.
- “Đang kiểm tra” với “Tài liệu hiện tại đã sẵn sàng sử dụng”.
- “Có bản thay thế đang chờ” với “Bản đã dùng để phê duyệt”.

Nếu thay thất bại, người dùng vẫn phải thấy bản hiện tại và lý do ứng viên chưa được áp dụng. Không hiển thị trạng thái thành công chỉ vì request upload trả mã thành công.

Không trả stack trace, object key nội bộ hoặc URL có chữ ký trong log lỗi công khai. Tên file do người dùng đặt cũng cần được xử lý an toàn tại nơi hiển thị hoặc xuất báo cáo.

## 14. Ma trận kiểm thử tình huống lạm dụng

Kiểm thử phải kiểm tra cả quyết định trả về và dữ liệu cuối cùng: con trỏ hiện tại, phiên bản, revision, audit, phê duyệt và hiệu ứng ngoài transaction.

| Tình huống | Kết quả cần đạt |
|---|---|
| Chủ hồ sơ thay hóa đơn trong `DRAFT`, ứng viên đạt kiểm tra | Chuyển sang bản mới một lần; bản cũ vẫn nguyên byte và có lịch sử |
| Người chỉ có quyền upload gọi API kích hoạt | Từ chối; upload không được nâng thành quyền thay |
| Thay `slotId` hoặc `fileVersionId` sang tenant khác | Không đọc hoặc kích hoạt nội dung ngoài quyền |
| Dùng ứng viên của slot khác trong cùng tenant | Từ chối do sai quan hệ đối tượng |
| Upload ở `DRAFT`, hồ sơ được nộp trước khi kích hoạt | Kích hoạt bị từ chối; nội dung đang xét duyệt không bị thay |
| Thay sau khi hồ sơ `APPROVED` hoặc `PAID` | Không đổi bằng chứng đã dùng; hướng xử lý qua nghiệp vụ điều chỉnh |
| Người được ủy quyền mất quyền sau upload | Kích hoạt mới bị từ chối theo chính sách kiểm tra lại quyền |
| File cùng tên nhưng khác digest | Không tái sử dụng proof hoặc phê duyệt chỉ dựa vào tên |
| Proof đúng ID nhưng sai generation hoặc digest | Từ chối kích hoạt |
| Scan timeout, lỗi hoặc chưa có kết luận | Ứng viên không trở thành bản hiện tại |
| Upload token bị dùng lại để ghi nội dung sau quét | Không thay được object đã chốt hoặc nội dung khác không thể được kích hoạt bằng proof cũ |
| Hai yêu cầu cùng revision kích hoạt đồng thời | Chỉ một yêu cầu thắng; yêu cầu còn lại báo xung đột |
| Thao tác nộp hồ sơ và thay file chạy đồng thời | Kết quả tuân thủ một thứ tự hợp lệ, không có hồ sơ đã nộp gắn sai snapshot |
| Cùng khóa idempotency, cùng fingerprint, gửi đồng thời | Một hiệu ứng nghiệp vụ và một kết quả nhất quán |
| Cùng khóa idempotency nhưng đổi ứng viên | Báo xung đột; không kích hoạt ứng viên khác |
| Mất phản hồi sau commit rồi retry khi ứng viên đã hết hạn | Trả kết quả đã commit nếu còn quyền đọc; không chạy lại thao tác |
| Retry thao tác cũ sau khi đã có lần thay tiếp theo | Không kéo con trỏ trở về bản cũ |
| Event cập nhật chỉ mục bị trùng hoặc đảo thứ tự | Không phát sinh hiệu ứng trùng hoặc làm nội dung hiện tại quay lùi |
| Transaction kích hoạt rollback | Con trỏ và revision không đổi; không có audit thành công giả |
| Dọn ứng viên chạy cùng lúc với kích hoạt | Không xóa object đã hoặc đang được bảo vệ để kích hoạt |
| Tải bản từ quyết định phê duyệt cũ sau nhiều lần thay | Nhận đúng phiên bản trong snapshot nếu còn quyền truy cập |
| Dùng URL tải cũ sau thay file | Không nhận nhầm byte của bản mới; hành vi hết hạn đúng chính sách |

Đối với kiểm thử đồng thời, cần tạo giao nhau thực sự giữa các transaction bằng cơ chế đồng bộ trong môi trường kiểm thử. Gửi hai request nối tiếp không chứng minh được bất biến chống mất cập nhật.

Đối với kiểm thử proof, kiểm tra cả quan hệ với object thực sự được scanner đọc. Chỉ mock một boolean `clean=true` sẽ bỏ sót rủi ro nội dung bị thay giữa quét và sử dụng.

## 15. Các cách triển khai cần tránh

| Cách triển khai | Hệ quả | Hướng thay thế |
|---|---|---|
| Ghi đè object ở đường dẫn cố định | Phê duyệt và proof có thể mô tả nội dung khác | Object riêng theo phiên bản, đổi con trỏ có kiểm soát |
| Chỉ kiểm tra quyền khi upload | Người mất quyền vẫn kích hoạt được sau đó | Kiểm tra lại quyền lúc tạo hiệu ứng |
| Tin cờ quét do client gửi | Kích hoạt nội dung chưa được kiểm tra | Proof từ dịch vụ tin cậy, gắn đúng phiên bản và digest |
| Giữ `APPROVED` khi tài liệu đã thay | Chuyển nhầm hiệu lực phê duyệt sang bằng chứng mới | Bất biến snapshot, quy trình duyệt lại hoặc đính chính |
| Dùng tên file làm khóa chống trùng | Retry hoặc đổi tên tạo hành vi sai | Idempotency có phạm vi và fingerprint |
| Xóa bản cũ trước khi commit | Lỗi giữa chừng làm mất tài liệu đang dùng | Giữ bản cũ; thu dọn riêng theo tham chiếu và lưu giữ |
| Chỉ khóa slot, đường phê duyệt bỏ qua hồ sơ cha | Race giữa thay tài liệu và chấp thuận | Quy ước đồng thời chung cho mọi đường ghi |
| Xử lý lại idempotency sau mọi guard trạng thái | Retry thành công trước đó bị từ chối sai | Đọc kết quả đã commit sau kiểm tra quyền và fingerprint |
| Tải tài liệu đã duyệt bằng endpoint “hiện tại” | Không tái hiện được bằng chứng của quyết định cũ | Tải đúng version trong snapshot |

## 16. Xây dựng chính sách cho một loại tài liệu mới

Với mỗi loại tài liệu, hãy làm rõ các quyết định sau trước khi triển khai:

1. Ai được tải ứng viên, ai được kích hoạt và ai được xem lịch sử?
2. Những trạng thái nào cho phép thay, và thao tác nào cần mở quy trình điều chỉnh riêng?
3. Định danh phiên bản, object bất biến, digest và proof được liên kết như thế nào?
4. Những snapshot hoặc quyết định nào bị ảnh hưởng khi tài liệu thay đổi?
5. Các đường nộp, thay, duyệt và thanh toán dùng chung cơ chế kiểm soát đồng thời nào?
6. Retry, sự cố giữa storage và cơ sở dữ liệu, cùng event trùng được phục hồi ra sao?
7. Phiên bản cũ được giữ, phục vụ và xóa theo những điều kiện nào?

Một chính sách thay file có thể kiểm chứng phải chỉ ra được nội dung nào đang có hiệu lực, nội dung nào đã được người duyệt xem, ai đã làm thay đổi quan hệ đó và điều gì ngăn một yêu cầu cũ áp dụng lên trạng thái mới. Mô hình phiên bản bất biến, quyền theo đối tượng và transaction nhất quán giúp biến những yêu cầu này thành các ràng buộc có thể thực thi.
