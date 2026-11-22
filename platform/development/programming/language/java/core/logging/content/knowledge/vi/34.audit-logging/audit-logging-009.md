# Lưu giữ audit trong Java Core Logging

## 1. Lưu giữ audit là gì?

**Lưu giữ audit (audit log retention)** là chính sách và cơ chế bảo đảm các bản ghi kiểm toán được thu thập, lưu trữ, bảo vệ, truy xuất và chỉ được tiêu hủy đúng thời điểm, đúng thẩm quyền. Giá trị của audit không nằm ở việc giữ càng lâu càng tốt, mà ở việc giữ **đủ nội dung cần chứng minh, trong đúng khoảng thời gian và dưới sự kiểm soát phù hợp**.

Audit log nhằm trả lời các câu hỏi: *ai* (hoặc hệ thống nào) thực hiện *hành động gì*, *trên tài nguyên nào*, *khi nào*, *kết quả ra sao*, *dựa trên quyền nào*, và *có thể xác minh lịch sử không?* Ví dụ: thay đổi quyền quản trị, xuất dữ liệu, sửa cấu hình quan trọng, xóa tài khoản, thay đổi chính sách truy cập, giao dịch nhạy cảm. Audit thường cần đáng tin cậy hơn log DEBUG/INFO phục vụ chẩn đoán.

~~~text
Audit event
  -> capture + validate schema/identity
  -> durable ingest/ACK và phân loại
  -> immutable/protected storage
  -> index/search (nếu cần)
  -> archive + kiểm tra khả năng truy xuất
  -> hết hạn? kiểm tra legal hold/ngoại lệ
  -> duyệt tiêu hủy + xóa theo phạm vi
  -> chứng cứ kiểm kê/tiêu hủy
~~~

**Lưu giữ audit không đồng nghĩa với chỉ tạo file `audit.log` rồi quay vòng.** Rolling giúp quản lý kích thước/tên file, nhưng không tự giải quyết tính toàn vẹn, legal hold, quyền truy cập, bảo vệ bản sao, độ bền, khôi phục dữ liệu hay yêu cầu retention từ nhiều chính sách.

### Audit log khác application log ở đâu?

| Tiêu chí | Log vận hành thông thường | Audit log |
| --- | --- | --- |
| Mục đích | Chẩn đoán lỗi, theo dõi hiệu năng, quan sát hệ thống | Truy vết hành động và trách nhiệm, phục vụ điều tra/kiểm toán |
| Sự kiện | Thường phụ thuộc logger level và cấu hình debug | Danh mục sự kiện cần ghi theo chính sách, không tắt tùy tiện |
| Độ đầy đủ | Có thể sampling/drop một số DEBUG khi quá tải | Cần kiểm soát mất event và có phản ứng rõ khi ghi thất bại |
| Thời hạn | Theo nhu cầu vận hành, có thể ngắn | Theo phân loại dữ liệu, nghĩa vụ áp dụng và chính sách đã phê duyệt |
| Khả năng sửa/xóa | Có thể linh hoạt hơn | Thường cần chống sửa/xóa không phép và truy xuất bằng chứng |
| Người truy cập | Developer, SRE, vận hành theo quyền | Vai trò giới hạn, có audit việc xem/truy xuất/tiêu hủy |

**Không dùng mức log `INFO` làm thước đo để quyết định record có phải audit hay không.** Một sự kiện thay đổi quyền có thể là INFO nhưng thuộc audit; ngược lại stack trace ERROR không nhất thiết phải lưu theo thời hạn audit. Tốt nhất tạo event type hoặc schema riêng cho audit thay vì suy đoán từ string message.

## 2. Thời hạn lưu giữ do ai quyết định?

Không tồn tại một con số `30 ngày`, `90 ngày` hay `7 năm` áp dụng cho mọi audit log Java. Thời hạn có thể phụ thuộc **loại hoạt động**, phạm vi pháp lý, quy định ngành, hợp đồng, chính sách tổ chức, điều tra đang diễn ra và nghĩa vụ bảo vệ dữ liệu cá nhân.

NIST SP 800-53 (kiểm soát AU-11) diễn tả thời hạn audit là giá trị **do tổ chức xác định**, phục vụ điều tra sau sự kiện và nghĩa vụ lưu giữ của tổ chức. Hướng dẫn OWASP Logging cũng lưu ý không tiêu hủy trước thời hạn bắt buộc và không giữ vượt quá thời hạn được phép khi không có căn cứ. Do đó:

1. Đội nghiệp vụ/security/compliance/legal xác định **loại record, mục đích, căn cứ và thời hạn**.
2. Engineering chuyển quyết định thành policy **có version**, gắn với từng record hoặc batch.
3. Operations xác minh storage, backup, archive và deletion thực sự thực thi đúng policy.
4. Thay đổi policy có cơ chế xét duyệt và xử lý bản ghi cũ; không tự sửa ngược lịch sử.

### Mẫu bảng chính sách (chỉ để thiết kế, không phải thời hạn pháp lý)

| Loại sự kiện | Mục đích | Mốc bắt đầu | Thời hạn | Ngoại lệ |
| --- | --- | --- | --- | --- |
| `access_granted` / `access_denied` | Điều tra truy cập | Thời điểm theo chính sách | Do security/compliance phê duyệt | Incident hold |
| `role_changed` | Truy vết thay đổi quyền | Thời điểm hiệu lực/ghi nhận | Do policy chỉ định | Legal hold, điều tra |
| `data_exported` | Truy vết xuất dữ liệu | Mốc theo hợp đồng/chính sách | Do policy chỉ định | Yêu cầu bảo toàn chứng cứ |
| `payment_admin_action` | Kiểm soát hành động nhạy cảm | Mốc nghiệp vụ được duyệt | Theo nghĩa vụ tương ứng | Hold/retention khác |
| `debug_trace` | Debug ngắn hạn, không mặc định là audit | Thời điểm thu thập | Chính sách vận hành riêng | Không nhập nhầm vào audit |

**Mốc bắt đầu** (retention anchor) không luôn là `eventTime`. Có chính sách tính từ lúc sự kiện phát sinh, lúc giao dịch hoàn tất, lúc hồ sơ đóng, lúc hợp đồng kết thúc, hoặc lúc archive được chốt. Không dùng timestamp do client tự khai làm cơ sở để xóa record an toàn.

### Một cấu trúc policy minh họa

~~~yaml
# Chỉ là mẫu tài liệu policy, KHÔNG phải cấu hình auto-delete sẵn dùng.
policyId: audit-access-v3
recordClass: security-access
retention:
  anchor: sealedAt
  duration: P18M       # ISO-8601 Period: 18 tháng lịch; số minh họa
exceptions:
  legalHold: block_deletion
  pendingInvestigation: require_review
storage:
  immutable: required
  encryptionAtRest: required
  restoreTest: required
disposal:
  approval: security-and-records-owner
  evidence: required
~~~

Mã `P18M` diễn tả 18 tháng lịch trong ISO-8601, không đồng nghĩa số giây cố định. Trước khi đưa vào hệ thống, phải xác định rõ timezone, cách xử lý cuối tháng/năm nhuận, độ bao gồm tại ranh giới, sự kiện sửa policy và chủ sở hữu phê duyệt. Không lấy YAML mẫu trên làm căn cứ tuân thủ.

## 3. Retention bắt đầu và kết thúc tại thời điểm nào?

Một sự kiện có thể có nhiều mốc thời gian:

- **`eventTime`:** khi hoạt động diễn ra; có thể đến từ máy khách hoặc nguồn có clock sai.
- **`observedAt`/`receivedAt`:** thời điểm server/collector đáng tin cậy nhận sự kiện.
- **`committedAt`:** thời điểm bản ghi hoặc manifest được lưu bền vững.
- **`sealedAt`:** thời điểm archive/batch được đóng, niêm phong và được gắn retention policy.
- **`retainUntil`:** thời điểm tối thiểu mà đối tượng không được bị tiêu hủy theo policy.
- **`holdUntil`/legal hold:** quy tắc giữ bổ sung độc lập, thường kéo dài đến khi được giải tỏa hợp lệ.

Tùy policy, `retainUntil` có thể được tính từ một mốc nghiệp vụ khác với thời điểm file được tạo. Lưu dấu **policyId/policyVersion** và thời điểm chốt để sau này tái hiện được quyết định.

**Phân biệt `Duration` và `Period` trong Java:** `Duration.ofDays(30)` là 30 × 24 giờ, thích hợp làm ví dụ fixed elapsed time. `Period.ofMonths(18)` tính theo tháng lịch khi cộng vào `LocalDate`/`ZonedDateTime`. Nghĩa vụ “18 tháng” không nên đổi thành `18 * 30` ngày; kết quả có thể sai khi qua tháng dài/ngắn hoặc múi giờ có DST.

Khi cần tính `retainUntil` cho dữ liệu thực, dùng calendar convention và timezone đã phê duyệt, đồng thời xác định có tính **đến hết ngày** hay hết ngay tại mốc. Tránh xóa ở chính ranh giới nếu quy tắc `retainUntil` chưa rõ, và áp nguyên tắc **không xóa khi metadata chưa chắc chắn**.

### Ví dụ timeline minh họa

~~~text
Ngày 1: event phát sinh / backend nhận
Ngày 2: batch được xác nhận đầy đủ và sealed
Tháng kế tiếp: chuyển sang archive truy xuất chậm hơn
Trước hết hạn: xuất hiện yêu cầu legal hold -> ngăn xóa
Sau hết hạn cơ bản: vẫn phải giữ vì legal hold đang hiệu lực
Sau khi hold được giải tỏa: kiểm tra lại policy, tất cả bản sao và quyền xóa
Khi được duyệt: tiêu hủy có kiểm soát, lưu bằng chứng disposal
~~~

Quá trình chuyển tầng storage **không được làm mất khả năng truy xuất** đã cam kết. Tìm ra archive chỉ tồn tại trên danh sách nhưng không thể giải nén, xác minh hoặc phục hồi khi điều tra là thất bại của cơ chế retention.

## 4. Đặc tả audit record để có thể giữ và kiểm chứng

Một schema audit có cấu trúc thường cần:

| Trường | Vai trò |
| --- | --- |
| `eventId` | Định danh event riêng, hỗ trợ phân biệt bản sao transport |
| `eventType` | Loại hành động chuẩn hóa: `role_changed`, `data_exported`... |
| `eventTime` và `receivedAt` | Phân biệt lúc sự kiện xảy ra và lúc hệ thống nhận |
| `actorId` / `actorType` | Ai/hệ thống nào thực hiện; hạn chế dữ liệu cá nhân trực tiếp |
| `action`, `objectType`, `objectId` | Thao tác và đối tượng tác động |
| `outcome` | Thành công, thất bại, bị từ chối, một phần |
| `tenantId` và `serviceInstance` | Phân vùng ngữ cảnh và nguồn phát |
| `requestId` / `traceId` | Liên kết ngữ cảnh, không dùng thay eventId |
| `schemaVersion` | Giúp đọc các bản ghi từ nhiều phiên bản phần mềm |
| `policyId` / `retentionClass` | Ánh xạ tới chính sách lưu giữ phù hợp |
| `ingestionId` hoặc manifest/batch ID | Bằng chứng record thuộc lần nhận và archive nào |

Ví dụ JSON **minh họa**, dùng ID giả và không chứa payload bí mật:

~~~json
{
  "eventId": "evt-2026-000042",
  "eventType": "role_changed",
  "eventTime": "2026-11-10T08:00:00Z",
  "receivedAt": "2026-11-10T08:00:01Z",
  "actorId": "admin-ref-17",
  "actorType": "human",
  "action": "grant_role",
  "objectType": "user",
  "objectId": "user-ref-42",
  "outcome": "success",
  "tenantId": "tenant-a",
  "requestId": "req-8",
  "schemaVersion": 2,
  "retentionClass": "privileged-access",
  "policyId": "audit-access-v3"
}
~~~

**Không nên ghi secret, password, access token, cookie, toàn bộ request/response body hoặc dữ liệu cá nhân quá mức vào audit** chỉ vì record sẽ được giữ lâu. Bản ghi được giữ càng lâu, phạm vi rủi ro càng lớn; cân nhắc pseudonymization/redaction có chủ đích, nhưng vẫn phải đáp ứng khả năng truy vết được cấp quyền.

Bộ lọc message ở logging framework không tự xác thực actor hay action. Audit record chỉ có giá trị khi nguồn xác định được danh tính đã xác thực và hành động thực sự xảy ra; đừng tin các field từ client gửi lên mà không kiểm tra.

## 5. Kiến trúc lưu giữ: từ ứng dụng Java đến archive

Một kiến trúc tham khảo:

~~~text
Java business operation / authorization
    |
    +--> transactional audit record hoặc durable outbox
    |           |
    |           v
    |      reliable publisher / retry
    |           |
    v           v
Validated structured audit event
    |
    v
Collector / ingest (ACK, dedup policy, durable queue)
    |
    +--> Hot searchable storage (chỉ cho người có quyền)
    |
    +--> Immutable archive / WORM + manifest, retention policy
                 |
                 v
         Inventory / integrity checks / restore tests
                 |
                 v
       Legal hold / release / disposal approval
~~~

Không phải ứng dụng nào cũng cần transactional outbox. Tuy nhiên, với sự kiện audit gắn liền thay đổi quan trọng trong database, một lời gọi `logger.info("role_changed")` chạy bất đồng bộ **không đủ để chứng minh** event đã được nhận và lưu bền vững. Nếu transaction commit nhưng process crash trước khi log được gửi, audit trail có thể có lỗ hổng.

**Một cách tăng tính đầy đủ** là lưu bản ghi audit hoặc outbox trong cùng giao dịch với thay đổi nghiệp vụ, sau đó publisher giao record tới audit sink có ACK/at-least-once và idempotent ingest. Phải thiết kế retry và chống bản sao bằng `eventId` phù hợp: at-least-once delivery giúp không bỏ sự kiện khi truyền tải tạm lỗi, nhưng có thể **giao trùng**; chính sách idempotency mới quyết định record cuối cùng không bị đếm đôi.

Nếu nghiệp vụ bị roll back, cần quyết định audit ghi **attempt bị từ chối/thất bại** như thế nào: record yêu cầu ghi thất bại có thể cần đường ghi độc lập với transaction nghiệp vụ. Không tự động viết “transactional outbox giải quyết mọi tình huống” khi audit cần ghi cả thao tác không commit.

### Tính bền vững khi ghi

- `logger.info(...)` thành công thường mới chỉ cho thấy API đã nhận lời gọi; async queue có thể chưa xả.
- `FileAppender` đã flush không chứng minh collector đã ship; file chưa chắc đã được fsync theo yêu cầu độ bền.
- Collector có ACK chưa chắc kho lưu trữ cuối đã committed nếu hợp đồng ACK không ghi rõ.
- Khi queue đầy, backend có thể block/drop theo policy; audit quan trọng cần cơ chế xử lý rõ, cảnh báo và không âm thầm bỏ record.
- Khi shutdown, dừng producer, drain queue và xác minh writer/collector theo thời gian cho phép. Crash/SIGKILL vẫn cần kiến trúc durable nếu không thể mất audit.

**Đo từng mốc** `produced` → `durablyQueued` → `ingested` → `archived` để phát hiện thiếu/nhân bản. Không dùng số dòng console làm bằng chứng archive đầy đủ.

## 6. Bảo vệ toàn vẹn và bất biến trong thời gian lưu giữ

Audit record cần chống sửa/xóa không phép và phát hiện tampering. Các lớp bảo vệ có chức năng khác nhau:

- **Least privilege:** service tạo audit có quyền append/gửi record nhưng không được sửa/xóa archive cũ; người vận hành đọc/điều tra có quyền tách biệt với quyền xóa.
- **Mã hóa khi truyền và khi lưu:** TLS cho đường truyền; encryption at rest, key rotation và kiểm soát quyền giải mã. **Mã hóa không tự ngăn người có quyền xóa object**.
- **Immutable/WORM storage:** cơ chế write-once/read-many hoặc retention lock ở tầng lưu trữ nhằm ngăn sửa/xóa trong thời hạn bảo vệ, kể cả khi appender bị lỗi.
- **Hash/checksum hoặc manifest đã ký:** giúp phát hiện dữ liệu bị sửa, thiếu hoặc sai thứ tự khi có thiết kế xác minh nguồn và key tin cậy. Chỉ hash một file bằng SHA-256 rồi lưu hash cạnh file trong cùng thư mục có quyền sửa **không đủ** để ngăn kẻ tấn công đổi cả hai.
- **Bản sao và availability:** replication/backup giúp tránh mất do hỏng thiết bị; phải đảm bảo bản sao cũng đáp ứng chính sách truy cập và retention.
- **Audit việc xem/xóa:** hành động đọc, xuất, đặt/gỡ hold, đổi policy, đặt lại retention và tiêu hủy đều cần ghi nhận ở kênh giám sát độc lập phù hợp.

### WORM và legal hold

Một ví dụ thực tế là **object storage có retention lock**. Với Amazon S3 Object Lock, tài liệu phân biệt `Governance` và `Compliance` mode: governance có quyền đặc biệt có thể bypass trong một số trường hợp; compliance có hạn chế mạnh hơn đối với việc sửa/xóa phiên bản object còn hạn bảo vệ. **Legal hold** là cơ chế giữ riêng, không tự hết theo thời gian; sau khi retention date qua mà hold còn hiệu lực thì object vẫn được giữ.

Đây là **ví dụ công nghệ**, không phải yêu cầu dùng Amazon S3. Cách lựa chọn phải theo threat model, quy định, quyền của administrator, key management và mô hình storage thực tế. S3 Object Lock bảo vệ **phiên bản object**; thao tác delete marker, versioning và lifecycle cần được hiểu đúng, không chỉ nhìn tên object trong bucket.

Ngay cả khi storage cung cấp WORM, toàn hệ thống có thể chưa tuân thủ: ingest có thể bỏ event, schema sai, retention sai, backup thiếu hoặc quyền xem quá rộng. WORM bảo vệ **dữ liệu đã đưa vào vùng bảo vệ**, không tự bảo đảm sự kiện được ghi từ nguồn.

## 7. Rotation của Logback không thay thế retention policy audit

Một nhầm lẫn phổ biến là đặt `maxHistory=30` và khẳng định “đã lưu audit 30 ngày”. Trong Logback, `RollingFileAppender` và `TimeBasedRollingPolicy` quản lý file active/archive và xóa theo lịch rollover; behavior phụ thuộc cách đặt pattern, ngày/size, việc có sự kiện kích hoạt rollover và điều kiện vận hành.

Ví dụ **`logback.xml` để minh họa rolling cho log vận hành**, **không đủ** dùng riêng cho audit có nghĩa vụ lưu giữ:

~~~xml
<configuration>
    <appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>30</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Điều cần hiểu:

1. `maxHistory=30` ở rolling **theo ngày** thường hướng tới tối đa 30 giai đoạn archive; với pattern theo tháng, ý nghĩa sẽ khác. Không phải chính sách “xóa từng audit event sau đúng 30×24 giờ”.
2. `totalSizeCap=1GB` có thể xóa archive cũ theo giới hạn tổng kích thước, **ngay cả khi vẫn nằm trong 30 kỳ**. Nếu dùng ngay cho audit bắt buộc lưu lâu hơn, đây là rủi ro xóa sớm.
3. `cleanHistoryOnStart=true` kích hoạt cleanup khi appender khởi động; một rollout/restart có thể khiến xóa archive cũ theo chính sách rolling mà không có bước xét duyệt legal hold.
4. Rolling không tự cung cấp WORM, manifest, lưu bằng chứng xử lý, quota backup, phân quyền riêng, kiểm thử restore hoặc legal hold.
5. File active và archived có thể chịu cơ chế xóa khác nhau; đừng suy diễn tình trạng archive chỉ từ một cấu hình.

**Thiết kế an toàn hơn:** nếu vẫn ghi file trung gian, dùng file rotation để quản lý I/O ở tầng nguồn, sau đó **ship** audit vào storage có chính sách giữ độc lập được chốt đúng và chỉ xóa file nguồn khi đã xác nhận đích nhận bền vững theo hợp đồng. Đừng dùng `totalSizeCap` hoặc `maxHistory` ở nguồn như cơ chế retention chuẩn duy nhất cho audit.

## 8. Java 17 độc lập: đánh giá tình trạng retention mà không xóa dữ liệu

Ví dụ sau minh họa cách **phân loại archive để xét duyệt**, không tự xóa file hoặc object. Chính sách “30 ngày kể từ `sealedAt`” ở đây **hoàn toàn giả định** để có kết quả kiểm chứng được. Trong sản phẩm thật, mốc tính và thời hạn phải được chính sách áp dụng phê duyệt.

Lưu file **`AuditRetentionDecisionDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;

public class AuditRetentionDecisionDemo {
    record AuditArchive(
            String id,
            Instant sealedAt,
            boolean legalHold,
            boolean integrityVerified) {}

    enum Decision {
        RETAIN,
        LEGAL_HOLD,
        REVIEW_METADATA,
        ELIGIBLE_FOR_REVIEW
    }

    static Decision evaluate(
            AuditArchive archive, Instant now, Duration retention) {

        // Hold luôn ngăn xét xóa, dù đã quá hạn cơ bản.
        if (archive.legalHold()) {
            return Decision.LEGAL_HOLD;
        }

        // Metadata thiếu/sai hoặc chưa kiểm chứng thì không xét xóa.
        if (archive.sealedAt() == null
                || archive.sealedAt().isAfter(now)
                || !archive.integrityVerified()) {
            return Decision.REVIEW_METADATA;
        }

        Instant cutoff = now.minus(retention);
        return archive.sealedAt().isBefore(cutoff)
                ? Decision.ELIGIBLE_FOR_REVIEW
                : Decision.RETAIN;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");
        Duration sampleRetention = Duration.ofDays(30);

        List<AuditArchive> archives = List.of(
                new AuditArchive("a-old",
                        Instant.parse("2026-10-01T00:00:00Z"), false, true),
                new AuditArchive("a-recent",
                        Instant.parse("2026-10-20T00:00:00Z"), false, true),
                new AuditArchive("a-hold",
                        Instant.parse("2026-09-01T00:00:00Z"), true, true),
                new AuditArchive("a-future",
                        Instant.parse("2026-11-11T00:00:00Z"), false, true),
                new AuditArchive("a-unknown", null, false, true),
                new AuditArchive("a-unverified",
                        Instant.parse("2026-10-01T00:00:00Z"), false, false)
        );

        for (AuditArchive archive : archives) {
            System.out.println(archive.id() + "="
                    + evaluate(archive, now, sampleRetention));
        }
    }
}
~~~

Chạy với Java 17 trở lên:

~~~bash
javac -encoding UTF-8 AuditRetentionDecisionDemo.java
java AuditRetentionDecisionDemo
~~~

**Stdout xác định**:

~~~text
a-old=ELIGIBLE_FOR_REVIEW
a-recent=RETAIN
a-hold=LEGAL_HOLD
a-future=REVIEW_METADATA
a-unknown=REVIEW_METADATA
a-unverified=REVIEW_METADATA
~~~

Kết quả đã được đối chiếu bằng logic Java `java.time` chạy trong JShell. Mỗi dòng chỉ **phân loại**, không thao tác filesystem. Dữ liệu mẫu là metadata giả, không chứa audit thật.

Giải thích:

- `record AuditArchive` giữ metadata của một archive (có thể diễn giải là batch đã được chốt). `sealedAt` không tự nhiên là mốc retention hợp pháp; nó chỉ được chọn cho bài thực hành.
- `Instant.parse(...)` dùng thời gian UTC không phụ thuộc timezone máy. `Instant now` được cố định để stdout không thay đổi theo ngày chạy.
- `Duration.ofDays(30)` là 30 × 24 giờ; **không được xem là yêu cầu tuân thủ thực tế**.
- `legalHold` được kiểm tra trước thời gian, nên `a-hold` vẫn phải giữ dù rất cũ.
- Mốc trong tương lai, timestamp thiếu hoặc integrity chưa xác nhận → `REVIEW_METADATA`; **không xóa**.
- `isBefore(cutoff)` dùng so sánh nghiêm ngặt: archive đúng bằng cutoff vẫn `RETAIN` ở ví dụ này. Điều kiện biên thật phải theo chính sách.
- `ELIGIBLE_FOR_REVIEW` **không có nghĩa “xóa ngay”**. Trước tiêu hủy còn phải đọc policy mới nhất, kiểm tra hold tại kho lưu trữ, nghiệp vụ/điều tra, bản sao, quyền và quy trình duyệt.

**Giới hạn cố ý:** Cờ `legalHold` hoặc `integrityVerified` ở bộ nhớ demo không đủ để quyết định xóa trong production. Quyết định thật cần metadata được xác thực từ authoritative store, quyền thực thi, nhiều điều kiện và bằng chứng đã kiểm tra. Mẫu demo không kết nối DB/object storage; không nên bổ sung lệnh `Files.delete` vào vòng lặp này như một “bước tiếp theo” tự động.

## 9. Legal hold và yêu cầu giữ ngoại lệ

**Legal hold** hoặc preservation hold là quyết định giữ lại tài liệu liên quan tới điều tra, tranh chấp hoặc yêu cầu hợp pháp, ngay cả khi thời hạn retention thường đã hết. Chính sách chính xác do tổ chức và nghĩa vụ áp dụng quyết định.

Luồng kiểm soát nên gồm:

1. **Tạo hold:** xác định phạm vi (sự kiện, tenant, user, giai đoạn, case ID, object version), người phê duyệt, lý do và thời điểm.
2. **Áp hold đến mọi lớp liên quan:** hot store, archive, replica, backup nằm trong phạm vi, bản export/copy đã tạo, không chỉ gắn nhãn trong một bảng dữ liệu.
3. **Chặn tiêu hủy:** mọi disposal job phải tra trạng thái hold **ở nguồn authoritative** ngay trước khi xóa, không chỉ dựa vào cache từ hôm trước.
4. **Ghi nhận thao tác:** audit người đặt/gỡ hold, thay đổi phạm vi, các yêu cầu truy xuất và mọi quyết định được phép.
5. **Giải tỏa hold:** chỉ người có quyền gỡ theo quy trình; sau đó tính lại các chính sách retention khác đang áp dụng.
6. **Xử lý overlap:** một object có thể chịu nhiều policy/hold. Nếu bất kỳ chính sách hợp lệ nào vẫn yêu cầu giữ, không được xóa.

Đừng hiểu rằng `retainUntil` đã qua thì object luôn có thể xóa; legal hold, điều tra mở hoặc retention khác có thể tiếp tục chặn. Cũng đừng quên nhu cầu ngược lại: khi hết mọi căn cứ giữ, tiếp tục lưu dữ liệu cá nhân vô hạn có thể vi phạm chính sách giảm dữ liệu.

## 10. Tiêu hủy audit có kiểm soát

Tiêu hủy là một **quy trình có bằng chứng**, không chỉ là script xóa file.

~~~text
Inventory archive + bản sao
    |
    v
Xác định retention policy hiện hành, anchor, retainUntil
    |
    v
Kiểm tra hold, điều tra, nghĩa vụ và quyền trên object version
    |
    v
Đủ điều kiện? -- không/không rõ --> GIỮ + cảnh báo/review
    |
    v
Dry-run + phê duyệt đúng vai trò
    |
    v
Thực thi disposal an toàn, idempotent, có giới hạn
    |
    v
Xác minh object/version/index/replica/backup theo policy
    |
    v
Lưu chứng cứ disposal tối thiểu, không sao chép lại PII
~~~

**Phân biệt các bản sao:** xóa record khỏi search index không nhất thiết xóa object trong archive, snapshot, backup, CDN/cache hoặc bản export đã gửi. Một thao tác delete có thể chỉ thêm **delete marker** trong kho có versioning, không xóa các version cũ được bảo vệ. Với backup, có thể phải chờ lịch hết hạn của backup hoặc cơ chế xóa riêng theo quy định. Nếu không thể xóa ngay mọi bản sao, chính sách cần nêu rõ cơ chế cách ly, thời gian thực thi và cách chứng minh.

Trong thiết kế thực tế, disposal job cần:

- Chạy **dry-run** và xuất danh sách object ID cùng lý do đủ điều kiện, không đưa payload audit nhạy cảm vào báo cáo.
- Xác minh **cận trên** số object/byte có thể xóa để tránh một lỗi chính sách quét cả kho.
- Áp nguyên tắc tối thiểu quyền, phân tách vai trò giữa người sửa retention policy và người chấp thuận xóa.
- Có kiểm tra lại **authoritative legal hold và retention lock** ngay trước khi thao tác, tránh race nếu hold được đặt trong lúc job chạy.
- Sử dụng API theo object **version** và xử lý đúng storage semantics; retry idempotent, không tự bypass governance/hold.
- Ghi event `deletion_requested`, `deletion_approved`, `deletion_attempted`, `deletion_verified` với ID, thời gian, policy/version, kết quả.
- Giữ bằng chứng tiêu hủy ở hệ thống được bảo vệ, nhưng không vô tình lưu lại nội dung audit đã phải xóa.
- Có khả năng dừng khẩn cấp, rollback policy trước khi xóa (không giả định dữ liệu đã xóa có thể phục hồi).

**Sự kiện “đã gửi API delete” không đồng nghĩa “đã tiêu hủy mọi bản sao”.** Phải xác minh bằng quyền, API và kiểm kê thích hợp, đồng thời hiểu độ trễ của lifecycle storage.

## 11. Archive lâu dài phải tìm kiếm và phục hồi được

Một hệ thống có thể giữ byte nhiều năm nhưng vẫn thất bại khi kiểm toán vì không thể tìm, giải mã hoặc đối chiếu sự kiện. Cần bảo đảm:

- **Inventory:** biết một sự kiện nằm trong batch/object nào, ở vùng/tenant, thời gian và policy nào.
- **Manifest và metadata:** checksum/hash, schema, codec, phiên bản parser, encryption key ID, thời điểm seal, số record và chuỗi liên kết khi có.
- **Search/index:** thời hạn index nóng có thể ngắn hơn retention archive; cần quy trình tìm bằng eventId/requestId hoặc thời gian/tenant mà không buộc quét bằng tay toàn bộ object.
- **Khóa giải mã:** rotation và hủy key phải phù hợp retention; mất key trước hạn khiến dữ liệu **không còn truy xuất được**, dù object vẫn tồn tại.
- **Restore test:** định kỳ khôi phục mẫu đại diện trong môi trường hạn chế quyền, xác minh checksum, schema, số sự kiện, timestamp và khả năng xuất chứng cứ.
- **Chain of custody:** ai xuất dữ liệu, từ object/version nào, lúc nào, hash đầu ra, ai được nhận và mục đích; không chỉ ảnh chụp dashboard.
- **Khả dụng:** replication/backup theo yêu cầu khôi phục; theo dõi lỗi region, quyền IAM, chi phí và độ trễ phục hồi từ cold/archive tier.

**Hash chain và chữ ký số có giới hạn:** chúng giúp phát hiện sửa đổi nếu root/signature/metadata được bảo vệ ở nơi độc lập. Nếu kẻ tấn công kiểm soát cả nguồn sự kiện và khóa ký, chuỗi hash tự nó không chứng minh hành động từng xảy ra. Dùng đồng hồ đồng bộ và receipt từ hạ tầng đáng tin để giảm khoảng trống bằng chứng.

## 12. Chi phí, dung lượng và khả năng vận hành

Tính dung lượng dự kiến trước khi chọn thời hạn/tầng lưu trữ:

\[
\text{Raw bytes/ngày} \approx \text{event/giây} \times \text{bytes/event} \times 86400
\]

Sau đó cộng phần index, metadata, replica, compression (có thể giảm dung lượng nhưng không dự đoán chính xác), backup và lưu trữ theo nhiều tier. Không lấy `totalSizeCap` ở appender nguồn làm ngân sách retention tổng.

Ví dụ minh họa:

- 10 sự kiện audit/giây, trung bình 1 KiB/event → khoảng 864.000 event/ngày, khoảng **844 MiB/ngày** raw payload (chưa tính metadata/replica/compression).
- Giữ 365 ngày ở cùng mức phát sinh → khoảng **301 GiB** raw payload. Đây chỉ là ước tính tải đều, **không là yêu cầu giữ 365 ngày** hay hóa đơn thực tế.
- Cộng mức tăng trưởng, burst, sự kiện xuất dữ liệu lớn và overhead của hệ thống index; dùng đo đạc thay vì suy từ ví dụ.

Giải pháp chia tầng:

| Tầng | Công dụng | Lưu ý retention |
| --- | --- | --- |
| Hot/searchable | Điều tra nhanh, query theo eventId/tenant | Có thể ngắn hơn thời hạn archive |
| Warm | Điều tra ít thường xuyên hơn | Giữ schema và khả năng kiểm chứng |
| Cold/archive | Giữ dài hạn, chi phí truy cập thường thấp hơn | Kiểm tra độ trễ restore, quyền và WORM |
| Backup/replica | Khôi phục khi mất dữ liệu/hạ tầng | Retention và legal hold phải tính cả bản sao |

Đưa log vào cold tier không đồng nghĩa đã hoàn tất nhiệm vụ. Hệ thống phải biết **đến hạn hay chưa**, truy xuất có kết quả không, và có bị sửa/xóa trái phép hay không.

## 13. Các tình huống lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `maxHistory=30` là thời hạn audit 30 ngày | Rollover không hiểu legal hold, giai đoạn khác nhau, xóa theo size | Retention policy riêng tại storage |
| Gộp audit và DEBUG vào cùng cơ chế auto-clean | Mất audit cần giữ hoặc giữ DEBUG quá lâu | Tách record class và lifecycle |
| Xóa theo `eventTime` từ client | Clock sai/backdate có thể làm xóa sớm | Dùng anchor authoritative theo policy |
| Thấy hết `retainUntil` là xóa ngay | Bỏ qua legal hold/điều tra/ngoại lệ | Review mọi điều kiện trước disposal |
| Bảo rằng đã “WORM” khi chỉ chmod file | Admin có thể sửa/xóa, nhiều bản sao không bảo vệ | Kiểm tra năng lực immutability thực ở storage |
| Chỉ mã hóa rồi gọi là immutable | Người có quyền xóa vẫn xóa được ciphertext | Encryption + WORM + quyền riêng |
| Xóa ở index nhưng backup còn chứa record | Vẫn giữ bản sao ngoài thời hạn | Kiểm kê và lifecycle mọi bản sao |
| Log audit bằng async logger cấu hình discard | Mất record trước khi tới archive | Đường ghi bền, backpressure/alert/idempotency |
| Ghi hết payload người dùng “để đủ audit” | Lộ PII/secret trong archive lâu dài | Chỉ giữ field cần chứng minh, redact |
| Hủy encryption key trước khi hết hạn | Record tồn tại nhưng không thể đọc | Đồng bộ key lifecycle với retention |
| Không test restore | Không biết archive bị hỏng/mất quyền | Restore kiểm thử định kỳ và ghi nhận kết quả |
| Thay policy nhưng không version | Không giải thích được quyết định xóa/giữ cũ | Lưu policy ID/version cùng evidence |
| Dùng một cron job có quyền xóa toàn kho | Lỗi code có thể tiêu hủy hàng loạt | Dry-run, approval, batch cap, least privilege |
| Xem legal hold như flag local | Có thể bị bỏ qua bởi job khác | Authoritative hold tại storage/policy service |

## 14. Kiểm thử retention và giám sát thực tế

### Kiểm thử chức năng

1. **Ranh giới thời gian:** record trước cutoff, đúng cutoff, sau cutoff; cả timezone khác, tháng nhuận, cuối tháng và quy tắc tính từ event/close/seal.
2. **Legal hold:** record quá hạn nhưng hold bật vẫn không thể bị xóa; hai hold overlap, gỡ một hold nhưng hold khác còn hiệu lực.
3. **Metadata lỗi:** missing `sealedAt`, timestamp tương lai, record chưa verify integrity → xét duyệt thay vì xóa.
4. **Policy change:** đổi duration/version, di chuyển tenant, cấu trúc schema cũ; không âm thầm áp duration mới lên record cũ nếu chưa có quyết định.
5. **Storage lock:** thao tác xóa trước `retainUntil` bị từ chối; thăm dò cả object versions, governance bypass, delete marker, legal hold.
6. **Pipeline failure:** queue đầy, collector offline, mất ACK, retry và duplicate ingest; audit record không biến mất im lặng.
7. **Restore:** giải mã và xác minh archive ở cold tier; tìm đúng record từ inventory và đối chiếu manifest/count.
8. **Security:** developer/read-only analyst không sửa policy hay xóa; admin có quyền hạn chế cũng bị kiểm soát theo mô hình đã chọn.
9. **Disposal:** dry-run không xóa, approval thực sự cần thiết, job không vượt cap, chạy lại idempotent và có evidence.
10. **Backup/export:** sau tiêu hủy hợp lệ, kiểm tra kết quả ở mọi nơi nằm trong phạm vi và ghi nhận hạn chế của các backup có lịch riêng.

### Các chỉ số hữu ích

Theo dõi `audit_events_produced`, `audit_events_durably_ingested`, `audit_events_archived`, số lượng batch lệch manifest, tuổi backlog, queue drop/retry, lỗi archive/restore, số record chưa gắn policy, số object quá hạn chưa xét duyệt, số hold đang hiệu lực, số lần truy cập/xuất archive và tiêu hủy thành công/thất bại.

Cảnh báo không nên chỉ dựa vào việc ít dòng log; khi **nguồn audit dừng phát**, hệ thống phải phát hiện mất heartbeat/record của các luồng quan trọng. Đảm bảo kênh alert độc lập còn hoạt động khi chính audit pipeline gặp lỗi.

## 15. Quy trình triển khai đề xuất

1. **Lập inventory** các loại audit event, chủ sở hữu và nguồn. Phân biệt audit bắt buộc với log chẩn đoán.
2. **Phê duyệt retention matrix**: loại record, anchor, thời hạn, timezone, legal hold, quyền truy xuất và nguyên tắc xóa; không suy đoán con số từ template kỹ thuật.
3. **Chuẩn hóa schema và event ID**, giảm secret/PII và xác thực nguồn để record có thể được điều tra.
4. **Thiết kế durable path** cho những sự kiện cần tính đầy đủ cao; quản lý ACK, retry, idempotency, shutdown và lỗi queue.
5. **Chọn storage** có quyền tối thiểu, encryption, WORM/retention lock khi cần, inventory/manifest và khả năng restore.
6. **Đồng bộ policy** giữa hot index, archive, replica, backup, export và key lifecycle.
7. **Bảo vệ legal hold** với nguồn thông tin đáng tin cậy, ưu tiên giữ khi thiếu điều kiện, và có audit của mọi thao tác nhạy cảm.
8. **Xây disposal hai pha**: đánh giá/dry-run → phê duyệt → xóa có giới hạn → xác minh → lưu evidence.
9. **Kiểm thử tự động/diễn tập** ở ranh giới thời gian, tháng lịch, sự cố lưu trữ, legal hold và khôi phục.
10. **Giám sát và rà soát định kỳ** policy, event coverage, quyền truy cập, năng lực archive, chi phí và các hồ sơ quá hạn.

**Ghi nhớ:** “lưu giữ audit” không phải là lưu file lâu hơn. Đó là một vòng đời có kiểm soát: **ghi nhận đầy đủ → lưu bền vững → chống sửa/xóa sai → truy xuất và kiểm chứng được → giữ theo chính sách/hold → tiêu hủy đúng hạn có chứng cứ**. Đối với Java, Logback/Log4j 2 chỉ là một phần của đường phát sự kiện; thời hạn và chứng cứ audit cần được quản trị ở kiến trúc lưu trữ và quy trình tổ chức.

### Tài liệu tham khảo

- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): security logging, protection, verification và disposal.
- NIST — [SP 800-92 Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final), [SP 800-53 Rev. 5: Audit and Accountability / AU-11](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final). Các nguồn đưa ra khuôn khổ; thời hạn cụ thể thuộc chính sách và yêu cầu áp dụng.
- Logback — [Rolling file appenders, maxHistory và totalSizeCap](https://logback.qos.ch/manual/appenders-rolling.html).
- Amazon S3 — [Object Lock, retention modes và legal hold](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) (ví dụ một giải pháp storage, không phải yêu cầu bắt buộc).
- Java SE 17 — [Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html), [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html), [Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html).
