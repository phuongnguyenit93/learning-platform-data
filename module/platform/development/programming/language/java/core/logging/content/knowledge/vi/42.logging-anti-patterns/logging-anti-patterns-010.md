# Không có chiến lược retention — Anti-pattern logging trong Java

## 1. Retention là gì và vì sao thiếu chiến lược là anti-pattern?

**Log retention** là tập hợp quy tắc quy định **loại log nào được giữ, ở đâu, trong bao lâu, ai được truy cập, khi nào chuyển sang tầng lưu trữ khác và khi nào phải xóa hoặc xử lý kết thúc vòng đời**. Một chiến lược đầy đủ cũng xác định các ngoại lệ như legal hold, nghĩa vụ bảo toàn bằng chứng, yêu cầu xóa dữ liệu cá nhân, backup, snapshot và cách xác minh việc xóa thực sự xảy ra.

**Anti-pattern “không có chiến lược retention”** xảy ra khi ứng dụng cứ ghi log nhưng không có câu trả lời nhất quán cho các câu hỏi đó. Hậu quả có thể đi theo cả hai hướng:

- **Giữ quá lâu:** ổ đĩa đầy, index phình lớn, chi phí cloud tăng, secret/PII tồn tại vô hạn, phạm vi ảnh hưởng của sự cố dữ liệu lớn hơn cần thiết.
- **Xóa quá sớm:** mất chứng cứ cho điều tra sự cố, kiểm toán, phát hiện hành vi tấn công, đối soát hoặc nghĩa vụ pháp lý.
- **Giữ không đồng nhất:** file ứng dụng chỉ còn 7 ngày nhưng object archive còn 5 năm, trong khi dashboard tưởng mọi bản sao đã hết hạn.
- **Không có chủ sở hữu:** không ai biết chính sách do đâu quyết định, ai được sửa và ai phải xử lý khi job xóa lỗi.
- **Không kiểm chứng:** một cấu hình “rotate daily” được nhầm thành “đã xóa dữ liệu đúng hạn”.

Ví dụ:

~~~text
Java service
  |
  +-- application.log (growing forever)
  |
  +-- app.2026-11-01.log.gz (archives forever)
  |
  +-- stdout -> container runtime -> log shipper
                                    |
                                    +--> search index
                                    +--> object storage
                                    +--> backup/snapshot
~~~

Chỉ cấu hình log level là INFO hoặc bật một rolling appender chưa phải chiến lược retention đầu-cuối. Nếu ứng dụng ghi vào cả file và stdout, hai tuyến có thể có **vòng đời độc lập**. Những gì đã đẩy đến collector không tự biến mất khi ứng dụng xóa bản local.

**Mục tiêu của bài:** nhận diện thiếu sót, thiết kế policy theo loại dữ liệu và rủi ro, cấu hình phù hợp Logback/Log4j 2, kiểm soát vòng đời ở collector/index/archive, rồi kiểm thử và đo việc thực thi. Không sử dụng bài như hướng dẫn xóa mù chứng cứ đang cần giữ.

## 2. Triệu chứng dễ nhận ra trong production

Một số dấu hiệu:

1. File application.log chỉ tăng, không có rotation hoặc archive cleanup.
2. Có file app.2020-...log.gz nhưng không ai biết chúng còn cần thiết hay không.
3. Chỉ dùng giới hạn kích thước, không có thời hạn giữ; hệ thống ít log có thể giữ dữ liệu rất lâu.
4. Chỉ dùng giới hạn số file, không có giới hạn thời gian; log lưu trong bao nhiêu ngày thay đổi theo traffic.
5. Cấu hình Logback maxHistory, nhưng chưa từng thử xem archive cũ có được dọn.
6. Log4j 2 có rollover, nhưng không có Delete action hoặc matching condition đúng với tên file.
7. Search index có chính sách ILM/ISM nhưng archive/snapshot giữ vô thời hạn.
8. Retention ở dev, staging và production không được quản lý phiên bản hoặc nhất quán theo dữ liệu.
9. Audit và debug log bị lưu cùng một policy, trong khi mục đích và nghĩa vụ hoàn toàn khác nhau.
10. Không có alert disk free, index storage, lifecycle errors hoặc log ingestion failures.
11. Một lỗi DEBUG/TRACE làm log volume tăng mạnh khiến ổ đĩa đầy trong vài giờ.
12. Yêu cầu xóa dữ liệu cá nhân được đánh dấu “hoàn tất” chỉ vì đã xóa file trên server, mặc dù collector và backup còn bản sao.
13. Sau restore backup, log đã bị xóa lại xuất hiện vì không có deletion ledger/tombstone.
14. Không ai nêu được policy version, người phê duyệt và bằng chứng hoàn tất xóa.
15. Một operator phải dùng lệnh xóa thủ công trực tiếp trên server để cứu dung lượng vì không có runbook.

**Đừng chỉ nhìn số file.** Một file active có thể cực lớn; một archive ít file có thể chứa dữ liệu nhiều năm, hoặc hàng triệu object nhỏ ở object storage tạo chi phí đáng kể.

## 3. Phân biệt rotation, retention, archival và deletion

| Khái niệm | Ý nghĩa | Điều không tự bảo đảm |
| --- | --- | --- |
| **Rotation/rollover** | Đổi file active sang archive theo ngày/kích thước | Không nhất thiết xóa archive cũ |
| **Retention** | Quy định thời gian/điều kiện giữ hoặc kết thúc vòng đời | Không chứng minh job xóa đã chạy |
| **Archival** | Chuyển sang kho lâu dài hoặc tầng rẻ hơn | Không đồng nghĩa “được phép giữ mãi” |
| **Compression** | Nén dữ liệu để tiết kiệm chỗ | Không giới hạn thời gian lưu |
| **Purge/deletion** | Loại dữ liệu theo policy và khả năng backend | Không chắc đã xử lý mọi bản sao/phiên bản |
| **Legal hold** | Giữ dữ liệu có căn cứ dù retention thông thường hết | Không được tùy tiện bật để giữ mọi dữ liệu |
| **Backup** | Bản khôi phục khi có sự cố | Không thay thế policy của kho vận hành |
| **Masking/anonymization** | Giảm hoặc loại khả năng nhận dạng | Không phải lúc nào cũng xóa byte gốc |

Ví dụ cấu hình quay file mỗi ngày có thể tạo:

~~~text
app.log
app.2026-11-07.log.gz
app.2026-11-08.log.gz
app.2026-11-09.log.gz
...
~~~

Nhưng nếu không có cơ chế cleanup hoặc giới hạn vòng đời, dữ liệu tiếp tục tích lũy. Ngược lại, nếu xóa toàn bộ archive sau đúng một ngày mà không đánh giá nhu cầu, những log quan trọng có thể biến mất trước khi đội vận hành nhận ra sự cố.

Một policy khả thi phải trả lời cả **thời điểm ghi**, **thời điểm archive**, **thời điểm chuyển tầng** và **thời điểm xóa theo điều kiện**. Không có một property Java chung áp dụng cho tất cả những bước này.

## 4. Xác định log cần giữ: phân loại theo mục đích

Không có một số ngày retention “đúng cho mọi hệ thống”. Thời hạn phải được xác định từ nhu cầu vận hành, yêu cầu pháp lý/kiểm toán, rủi ro quyền riêng tư, chi phí và tính sẵn có của dữ liệu.

| Nhóm log | Mục đích | Gợi ý cách nghĩ về chính sách |
| --- | --- | --- |
| DEBUG/TRACE chẩn đoán | Phân tích ngắn hạn, thường có volume cao | Giữ ngắn, bật có giới hạn, tránh payload nhạy cảm |
| Application INFO | Trạng thái request/operation, xử lý sự cố | Giữ phù hợp cửa sổ hỗ trợ và nhu cầu điều tra |
| ERROR/WARN | Điều tra lỗi và suy giảm | Cần đủ thời gian phát hiện, theo dõi và phân tích |
| Access log | Truy cập HTTP, hành vi mạng | Xem quyền riêng tư và nhu cầu bảo mật |
| Security events | Đăng nhập sai, chặn truy cập, thay quyền | Có thể cần giữ/giám sát theo quy định và rủi ro |
| Audit trail | Bằng chứng hoạt động quan trọng | Quy tắc tính toàn vẹn, quyền, thời hạn và legal hold riêng |
| Infrastructure logs | Kubernetes, JVM, OS, proxy, database | Có nguồn/owner và lưu trữ độc lập với app |
| Business event log | Dữ liệu sự kiện nghiệp vụ được dùng tái dựng state | Không thể áp policy của DEBUG log tùy ý |

**Ví dụ giả định dùng trong tài liệu học**, không phải quy định bắt buộc: DEBUG 2 ngày, application 14 ngày, security 30 ngày và audit 90 ngày. Đây chỉ là dữ liệu mẫu để giải thích thiết kế; tổ chức **không được áp dụng những con số đó cho production trước khi có phê duyệt chuyên môn**.

Nếu luật hoặc hợp đồng buộc giữ chứng cứ lâu hơn, một giới hạn tổng dung lượng không thể âm thầm xóa sớm. Khi có rủi ro vượt dung lượng, cần thay đổi hạ tầng/budget, chuyển tier hoặc điều chỉnh chính sách bằng quy trình được phép; không phá nghĩa vụ lưu giữ chỉ để giải phóng disk.

## 5. Tạo retention policy có chủ sở hữu rõ ràng

Một chính sách cần ít nhất:

- **Data classification:** loại log, service/tenant, có PII/secret hay không.
- **Purpose:** vì sao cần lưu và ai sử dụng.
- **Retention start:** tính từ lúc event xảy ra, lúc file đóng, index creation, rollover, ingest hay mốc khác; phải ghi rõ.
- **Duration/expiry:** thời hạn và ngoại lệ; không dùng “khi nào đầy disk thì xóa”.
- **Storage tiers:** local, centralized hot/warm/cold, object/archive, snapshot/backup.
- **Access control:** ai đọc, xuất, tải, khôi phục hoặc xóa được.
- **Hold/exceptions:** căn cứ giữ, owner phê duyệt, thời điểm tái đánh giá và scope.
- **Deletion semantics:** xóa record, file, index, object version hay encryption key; kết quả nào được coi hoàn tất.
- **Verification:** kiểm chứng sau thao tác; xử lý khi job lỗi hoặc data drift.
- **Ownership:** ai có quyền đổi policy và ai nhận cảnh báo.
- **Change history:** policy version, lý do, ngày áp dụng và kế hoạch migration dữ liệu cũ.

Ví dụ cấu trúc chính sách (chỉ là biểu diễn vận hành, không phải một file cấu hình Logback):

~~~yaml
policyVersion: "logging-retention-v3"
service: "order-service"
classes:
  diagnostic:
    retention: "P2D"
    owner: "platform-observability"
  application:
    retention: "P14D"
    owner: "platform-observability"
  security:
    retention: "P30D"
    owner: "security-operations"
  audit:
    retention: "P90D"
    owner: "compliance-security"
holds:
  requireApproval: true
  storeHoldDecisionsSeparately: true
verification:
  requireDeletionEvidence: true
~~~

**Chú ý:** YAML này không tự thiết lập bất kỳ lifecycle nào. Nó là **bản mô tả đã version hóa** để dịch sang cấu hình appender, index lifecycle, archive policy và thủ tục vận hành đúng backend.

## 6. Đánh giá vòng đời dữ liệu ở mọi điểm lưu

Một application log có thể được lưu như sau:

~~~text
Application Java
  |
  +--> Logback/Log4j 2 file appender
  |       +--> active file
  |       +--> rolled/compressed archives
  |
  +--> stdout
          |
          v
     container runtime logs
          |
          v
      Filebeat / Fluent Bit / OTel Collector
          |
          +--> buffer/queue/retry
          |
          +--> search index / data stream
          |
          +--> object storage/archive
                    |
                    v
               backup/snapshot/export
~~~

Xóa các archive trong /var/log/my-service **không xóa** document đã được index. Một ILM policy đã xóa index **không xóa** backup/snapshot, file được tải về hoặc các bản export của đội hỗ trợ. Dữ liệu có thể được replay từ archive và **hồi sinh** sau khi đã xóa ở index.

Cần lập data inventory cho mỗi destination:

| Nơi lưu | Câu hỏi chính |
| --- | --- |
| Active application file | Có giới hạn kích thước, handle còn mở, ai chịu trách nhiệm rotation? |
| Rotated archives | Chính sách tuổi/dung lượng? Cleanup chạy lúc nào? |
| Container logs/stdout | Runtime/node có rotation riêng không? Khi pod mất thì dữ liệu thế nào? |
| Agent buffers/spool | Disk queue giữ bao lâu khi collector offline? |
| Central index | ILM/ISM/data stream lifecycle được áp dụng thực tế chưa? |
| Object archive | Có versioning, lifecycle rule, Object Lock/WORM không? |
| Snapshot/backup | Có retention riêng, restore phải tôn trọng deletion requests không? |
| Export/manual copy | Người xuất log có policy xóa và quyền truy cập riêng không? |

Một bảng inventory không chỉ liệt kê đường dẫn; cần thêm owner, quyền truy cập, retention thực tế, cách kiểm tra và cách xử lý ngoại lệ.

## 7. Thiếu retention gây mất kiểm soát dung lượng

Giả sử một service tạo trung bình **5 GB log/ngày**. Trong 30 ngày, một bản lưu chưa nén đã xấp xỉ **150 GB**; nếu hệ thống sao chép cùng khối lượng sang ba bản lưu vật lý tương đương thì khoảng **450 GB** trước overhead, replication overhead khác, indexing, snapshot và compression thực tế.

Đây chỉ là mô hình đơn giản: độ nén, tỉ lệ log trùng, index metadata, replicas và traffic burst làm chi phí thật khác biệt. Nhưng nó cho thấy vì sao "đĩa còn trống" không phải một chính sách.

Cần tính:

~~~text
Estimated storage
  = average bytes/day
  x target retention days
  x effective copy/replication factor
  + index/metadata overhead
  + reserve for burst and recovery
~~~

Nên đo **bytes/day theo service, level và destination**, thêm các kịch bản:

- INFO bình thường;
- DEBUG/TRACE tạm bật để điều tra;
- downstream lỗi khiến hàng nghìn ERROR/stack trace mỗi giây;
- collector mất kết nối gây local buffer tăng;
- replay/backfill dữ liệu lịch sử;
- backup snapshot hoặc migration giữ đồng thời hai bản.

**Dung lượng là ràng buộc vật lý, không thay thế retention pháp lý.** Nếu dữ liệu bắt buộc phải giữ, khi vượt ngân sách cần mở rộng hoặc chuyển tier phù hợp, không xóa âm thầm để trở lại dưới một cap.

## 8. Java 17+ chạy độc lập: đánh giá retention nhưng không xóa dữ liệu

Ví dụ sau dạy cách **phân loại một segment log thành ứng viên xử lý** dựa trên loại log, thời điểm và trạng thái bảo vệ. Chương trình cố ý **không đọc/xóa file thật**: an toàn cho người học, và tránh biến một ví dụ sơ cấp thành công cụ xóa chứng cứ.

Dữ liệu giả định: thời điểm đánh giá là **2026-11-10T00:00:00Z**, chính sách mẫu DEBUG 2 ngày, APP 14 ngày, SECURITY 30 ngày, AUDIT 90 ngày. Một segment đang được dùng để ghi sẽ không bị chọn để dọn; một segment có legal hold được giữ mặc dù đã qua mốc tuổi thông thường.

Tạo file **RetentionPolicyDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public class RetentionPolicyDemo {
    enum Kind { APP, DEBUG, SECURITY, AUDIT }

    record Segment(String name, Kind kind, Instant created,
                   long bytes, boolean legalHold, boolean active) {}

    record Decision(String action, String reason) {}

    // GIÁ TRỊ MINH HỌA, KHÔNG PHẢI RETENTION BẮT BUỘC.
    static final Map<Kind, Duration> POLICY = Map.of(
        Kind.APP, Duration.ofDays(14),
        Kind.DEBUG, Duration.ofDays(2),
        Kind.SECURITY, Duration.ofDays(30),
        Kind.AUDIT, Duration.ofDays(90)
    );

    static Decision evaluate(Segment segment, Instant now) {
        if (segment.active()) {
            return new Decision("SKIP", "active-file");
        }
        if (segment.legalHold()) {
            return new Decision("HOLD", "legal-hold");
        }

        Duration retention = POLICY.get(segment.kind());
        if (retention == null) {
            throw new IllegalArgumentException("No policy");
        }

        Instant expiry = segment.created().plus(retention);
        return now.isBefore(expiry)
            ? new Decision("KEEP", "within-retention")
            : new Decision("CANDIDATE", "expired");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<Segment> samples = List.of(
            new Segment("app-old.log", Kind.APP,
                Instant.parse("2026-10-20T00:00:00Z"),
                2048, false, false),

            new Segment("app-new.log", Kind.APP,
                Instant.parse("2026-11-05T00:00:00Z"),
                1024, false, false),

            new Segment("debug-old.log", Kind.DEBUG,
                Instant.parse("2026-11-01T00:00:00Z"),
                512, false, false),

            new Segment("security-held.log", Kind.SECURITY,
                Instant.parse("2026-09-01T00:00:00Z"),
                8192, true, false),

            new Segment("audit-active.log", Kind.AUDIT,
                Instant.parse("2026-08-01T00:00:00Z"),
                5120, false, true)
        );

        int candidates = 0;
        int keep = 0;
        int holds = 0;
        int skipped = 0;
        long candidateBytes = 0;

        for (Segment segment : samples) {
            Decision decision = evaluate(segment, now);
            System.out.println(segment.name() + " -> "
                    + decision.action() + " ("
                    + decision.reason() + ")");

            switch (decision.action()) {
                case "CANDIDATE" -> {
                    candidates++;
                    candidateBytes += segment.bytes();
                }
                case "KEEP" -> keep++;
                case "HOLD" -> holds++;
                case "SKIP" -> skipped++;
                default ->
                    throw new IllegalStateException("Unexpected action");
            }
        }

        System.out.println("summary candidates=" + candidates
                + " keep=" + keep
                + " holds=" + holds
                + " skipped=" + skipped
                + " candidateBytes=" + candidateBytes);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac RetentionPolicyDemo.java
java RetentionPolicyDemo
~~~

**Stdout xác định**:

~~~text
app-old.log -> CANDIDATE (expired)
app-new.log -> KEEP (within-retention)
debug-old.log -> CANDIDATE (expired)
security-held.log -> HOLD (legal-hold)
audit-active.log -> SKIP (active-file)
summary candidates=2 keep=1 holds=1 skipped=1 candidateBytes=2560
~~~

### Vì sao có những kết quả này?

- **app-old.log:** APP 14 ngày tính từ 20/10 tới trước 10/11, đã hết khoảng giữ mẫu nên là CANDIDATE.
- **app-new.log:** mới 5 ngày, chưa tới mốc 14 ngày nên KEEP.
- **debug-old.log:** quá thời hạn mẫu 2 ngày nên CANDIDATE.
- **security-held.log:** dù cũ, vẫn đang legalHold=true nên HOLD.
- **audit-active.log:** mô phỏng file đang ghi; SKIP để tránh thao tác lên writer đang hoạt động.

Hai ứng viên có tổng kích thước **2048 + 512 = 2560 bytes**. **CANDIDATE không đồng nghĩa có thể xóa ngay**. Trước khi xóa thật phải kiểm tra owner, căn cứ lưu giữ, snapshot/backup, chính sách phân loại, file identity, symlink, quyền và job deletion; ví dụ này chỉ phân loại.

### Giới hạn phải hiểu rõ

1. Trường created là **thời điểm metadata của segment trong ví dụ**, không phải bằng chứng rằng mọi sự kiện trong file có cùng ngày. Log file thực có thể chứa records qua nhiều ngày.
2. Một số backend xóa theo **lastModified** hoặc thời điểm rollover/index creation, không nhất thiết theo timestamp từng event. Phải dùng cùng semantics với policy đã duyệt.
3. Một boolean legalHold không đủ cho production: hold phải được quản lý bởi hệ thống đáng tin, có phê duyệt, scope và thời hạn đánh giá lại; không để client tự gửi cờ.
4. Chương trình không đụng filesystem, không có worker concurrent, không xử lý object lock, WORM, bản sao hay quyền xóa dữ liệu.
5. Nếu cùng file chứa audit bắt buộc và debug log, **không thể áp một quyết định xóa toàn file** chỉ vì một phần đã hết hạn; cần thiết kế tách dữ liệu.
6. Giá trị retention 2/14/30/90 ngày chỉ là ví dụ học tập, **không phải khuyến nghị pháp lý hoặc chuẩn bắt buộc**.
7. Hàm evaluate dùng mốc thời gian cố định cho kết quả có thể tái lập; hệ thống thật phải xác định nguồn clock tin cậy và timezone khi tính mốc.
8. Các quyết định giữ/xóa phải được **đối chiếu ở mọi storage destination**, không phải chỉ một danh sách segment trong bộ nhớ.

## 9. Logback: maxHistory, totalSizeCap và cleanHistoryOnStart

Trong ứng dụng Java dùng Logback Classic, **RollingFileAppender** phối hợp với **TimeBasedRollingPolicy** có thể tạo archive theo ngày và dọn history. Ví dụ **logback.xml** dành riêng cho **application logs không có nghĩa vụ lưu giữ dài hạn**:

~~~xml
<configuration>
  <appender name="APP"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>/var/log/my-service/app.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
      <fileNamePattern>
        /var/log/my-service/archive/app.%d{yyyy-MM-dd}.log.gz
      </fileNamePattern>
      <maxHistory>14</maxHistory>
      <totalSizeCap>2GB</totalSizeCap>
      <cleanHistoryOnStart>true</cleanHistoryOnStart>
    </rollingPolicy>

    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="APP"/>
  </root>
</configuration>
~~~

**Cần chỉnh và kiểm thử trên phiên bản Logback thực tế**; path trong fileNamePattern có thể viết trên một dòng nếu cấu hình XML/whitespace trong môi trường tạo ra path không như mong đợi. Khi triển khai, dùng đường dẫn và quyền đã được xác minh.

Ý nghĩa theo tài liệu Logback:

- **fileNamePattern** có %d{yyyy-MM-dd} nghĩa là archive theo chu kỳ ngày của pattern.
- **maxHistory=14** quy định tối đa **14 kỳ lưu lịch sử dạng ngày** cho archive. Nó không tự đặt thời hạn bảo quản trên collector/index, và không phải timer chính xác tới từng mili giây cho mọi record.
- **totalSizeCap=2GB** giới hạn tổng dung lượng archive thuộc policy, dọn archive cũ khi vượt cap. Nó yêu cầu maxHistory được đặt, và giới hạn thời gian áp dụng trước giới hạn tổng dung lượng. **Cap có thể dọn dữ liệu sớm hơn dự kiến** nếu lượng log tăng mạnh.
- **cleanHistoryOnStart=true** cho phép chạy việc dọn history lúc appender khởi động; thường dọn khi rollover. Hữu ích cho job ít ghi log nhưng không thay thế kiểm chứng.
- Logback có thể dọn archive **bất đồng bộ**. Không nên coi việc gọi log.info() hoặc thấy file mới là bằng chứng rằng mọi archive cũ đã được xóa.

**Cảnh báo:** nếu yêu cầu nghiệp vụ phải giữ đủ ít nhất 14 ngày, một totalSizeCap quá nhỏ có thể mâu thuẫn với yêu cầu đó. Cần thiết kế kho có đủ dung lượng và policy phù hợp. Không gắn cùng APP appender cho audit buộc lưu lâu hơn rồi chỉ giữ 14 kỳ.

**Rollover không phải cron tuyệt đối.** Logback thường thực hiện rollover khi có event mới sau mốc thời gian, nên có thể chậm khi ứng dụng ít ghi. Khi thời hạn xóa cần kiểm soát chặt, cần lifecycle độc lập và đo thực tế.

## 10. Log4j 2: rolling và Delete action có điều kiện

Log4j 2 Core hỗ trợ **RollingFile** cùng các TriggeringPolicy/rollover strategy và các action như **Delete**. Nếu pattern tạo archive theo ngày mà không có điều kiện xóa phù hợp, dữ liệu có thể tiếp tục giữ dù file mới vẫn được sinh.

Ví dụ **log4j2.xml** dùng **DirectWriteRolloverStrategy** với file ngày và action chỉ chọn file archive khớp tên, đã đủ tuổi theo lastModified:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <RollingFile name="APP"
       filePattern="/var/log/my-service/archive/app.%d{yyyy-MM-dd}.log.gz">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
      <Policies>
        <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
      </Policies>
      <DirectWriteRolloverStrategy>
        <Delete basePath="/var/log/my-service/archive" maxDepth="1">
          <IfFileName glob="app.*.log.gz"/>
          <IfLastModified age="P14D"/>
        </Delete>
      </DirectWriteRolloverStrategy>
    </RollingFile>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="APP"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Đây là **mẫu kỹ thuật cho archive có thể dọn**, không có giá trị pháp lý của mốc P14D. Kiểm tra đúng phiên bản Log4j 2, path, quyền ứng dụng, file đang ghi, timezone và các tình huống rollover. Trước khi chạy trên dữ liệu thật, thử trên directory riêng chứa file giả để tránh xóa nhầm.

Các điểm quan trọng:

- **TimeBasedTriggeringPolicy** xác định khi nào rollover theo thời gian; nó **không tự là luật xóa log**.
- **DirectWriteRolloverStrategy** dùng filePattern trực tiếp cho các file đầu ra; ví dụ này không khai báo fileName active riêng.
- **Delete** chỉ nên được giới hạn ở một **basePath hẹp**, cùng điều kiện IfFileName và IfLastModified; không đặt basePath là thư mục hệ thống hoặc root chung.
- **IfLastModified age="P14D"** xét **mtime của file**, không phải sự kiện bên trong file và không phải nghĩa vụ pháp lý về retention.
- Các action này liên quan hoạt động rollover; khi ít log có thể không dọn đúng thời điểm mong đợi, phải kiểm tra thực nghiệm.
- Nếu dùng symlink, recursion hoặc tùy chọn followLinks, cần đánh giá nguy cơ Delete vượt khỏi phạm vi. Với configuration theo ví dụ, không bật followLinks.
- Nếu cần giữ chứng cứ, không cho phép action Delete chạm vào đường lưu audit được bảo vệ.

Log4j 2 còn có thể giới hạn số archive theo **DefaultRolloverStrategy max** trong các cấu hình dùng index %i, nhưng **giới hạn số file không tương đương số ngày**, đặc biệt khi volume biến thiên. Đọc manual tương ứng cho chiến lược cụ thể thay vì cho rằng max="14" nghĩa là 14 ngày trong mọi pattern.

## 11. Rolling policy và retention policy không phải một

Cùng một ví dụ có thể bị hiểu sai:

~~~text
Config A: rotate daily, keep 14 files
Config B: rotate at 100MB, keep 14 files
Config C: daily and max 2GB archives
~~~

A có thể gần ý nghĩa 14 kỳ ngày **nếu** logic archive thực sự theo ngày. B chỉ giới hạn **số file**, có thể tương đương vài phút lúc log storm hoặc nhiều tháng lúc service ít hoạt động. C giới hạn dung lượng, có thể xóa log trước thời hạn nếu throughput tăng.

Do đó policy cần nói rõ mục tiêu:

- **Retention tối thiểu:** dữ liệu **phải có** ít nhất bao lâu khi có nghĩa vụ giữ.
- **Retention tối đa:** dữ liệu **không được giữ quá** bao lâu nếu không có căn cứ.
- **Operational capacity cap:** dung lượng tối đa an toàn cho local disk/archival tier.
- **Rollover interval:** lịch chia file phục vụ vận hành, không tự là bằng chứng expiry.

Khi hai mục tiêu mâu thuẫn, cần **escalation và thiết kế tier khác**, không “chọn con số nhỏ hơn” và dọn không kiểm soát. Có thể chuyển evidence bắt buộc sang protected storage trước khi local cleanup, rồi quản lý retention ở destination đó.

## 12. Spring Boot và ứng dụng chạy trong container

Với Spring Boot, thuộc tính như logging.level.root=INFO chỉ kiểm soát level, **không phải** thời hạn giữ. Spring Boot có thể dùng Logback qua starter mặc định, nhưng cấu hình thực sự phụ thuộc vào backend và các file **logback-spring.xml**, **log4j2.xml**, environment, JVM system properties hoặc config server.

**Trường hợp stdout-only**: ứng dụng không ghi local file nhưng stdout/stderr được runtime/container lưu; retention do container runtime, node log rotation, collector và đích tập trung quyết định. Khi pod mất, bản local có thể biến mất nhanh, nhưng bản đã ingest vẫn ở backend cho tới khi policy của backend chạy.

**Trường hợp file appender trong container**: cần biết file ghi trên ephemeral filesystem hay persistent volume, người sở hữu volume, cách log shipper tail file và lifecycle khi pod đổi tên/restart. Không mặc định pod termination làm toàn bộ log bị xóa hoặc được lưu.

Một số rủi ro:

- Runtime giữ log container cũ vượt quá thời gian cần thiết vì node GC không theo policy.
- App ghi cả stdout và file, shipper thu cả hai gây duplicate.
- Pod restart nhưng file trong PVC vẫn còn, khác với local ephemeral path.
- Disk/ephemeral storage đầy dẫn tới eviction hoặc app crash.
- Mỗi replica dùng policy khác nhau do rollout không đồng nhất.
- Một service thay đường dẫn appender và policy cleanup cũ không còn quản lý archive.

Đội vận hành phải kiểm tra retention thực tế **tại từng hop**, không chỉ xem application.properties hoặc XML trong source repository.

## 13. Centralized logging: Elasticsearch ILM và OpenSearch ISM

Khi log vào search cluster, **local rotation không quản lý index retention**.

### 13.1. Elasticsearch ILM (Index Lifecycle Management)

Elasticsearch ILM có các phase **hot, warm, cold, frozen và delete** tùy policy. Có thể rollover index/data stream, chuyển tầng và xóa index cũ. Một ví dụ **policy JSON minh họa**, phải kiểm tra version, tên index/template và quyền trước khi áp dụng:

~~~json
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_primary_shard_size": "25gb"
          }
        }
      },
      "delete": {
        "min_age": "14d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
~~~

Đây là **body minh họa của ILM policy**, chưa bao gồm việc tạo policy, gắn vào index template/data stream hoặc xác minh. Delete min_age phụ thuộc semantics tuổi của index và **rollover**; không tự diễn giải thành “từng document bị xóa đúng 14 ngày từ event timestamp”. Độ tuổi của index, creation/rollover date và lifecycle state phải được kiểm tra theo tài liệu phiên bản.

Lưu ý:

- **Rollover không đồng nghĩa delete.** Policy phải có delete action nếu muốn lifecycle xóa index.
- Cần gắn policy vào template/data stream hoặc các index mong muốn; file JSON tồn tại trên máy không có nghĩa index đang được quản lý.
- Nếu search có **data streams**, lifecycle có thể khác với index truyền thống.
- **Elasticsearch Serverless** có cơ chế Data Stream Lifecycle thay vì ILM trong những môi trường mà ILM không khả dụng.
- ILM delete index **không xóa snapshot/backup/exports** nằm ngoài index đó.
- Một delete action có thể xóa toàn index, nên không trộn dữ liệu có thời hạn bảo vệ khác nhau vào cùng index nếu không có chiến lược rõ.

### 13.2. OpenSearch ISM (Index State Management)

OpenSearch **ISM** cho phép chính sách theo state/action/transition, ví dụ rollover, read-only, snapshot và delete khi đáp ứng điều kiện. Cần policy, template hoặc attachment tương ứng và theo dõi trạng thái managed index.

Đừng cho rằng **Elasticsearch ILM** và **OpenSearch ISM** cùng một cú pháp hoặc cùng semantics. Nếu đổi backend, phải đọc tài liệu và kiểm tra từng action. Với ISM, việc thay policy có thể cần thời gian chạy tới chu kỳ đánh giá kế tiếp và managed index có thể đang dùng phiên bản policy cache; nên kiểm tra trạng thái thực tế, không chỉ cấu hình mới đã lưu.

**Cả hai đều không tự quản lý snapshot ở object storage hoặc log đã export ra ngoài hệ thống.**

## 14. Object storage, archive, snapshot và backup

Với object storage, retention có thể dựa trên **lifecycle rules**, prefix/tag, object versioning và các cơ chế immutability. Một archive có thể có nhiều phiên bản nếu versioning bật. Xóa “current version” bằng delete marker **không nhất thiết xóa phiên bản cũ**.

Cần phân biệt:

- **Standard archive:** có thể hết hạn bằng lifecycle theo ngày tạo/last modified tùy backend.
- **Versioned object:** có thể có current version và noncurrent versions cần xử lý theo policy riêng.
- **Object Lock/WORM:** một số object bị hạn chế xóa trước hạn; không phá cơ chế chống sửa đổi để giải phóng disk.
- **Snapshot/backup:** có chính sách bảo vệ và xóa bản cũ riêng. Backup có thể chứa nhiều loại log và dữ liệu của nhiều chủ thể.
- **Exported files:** log do nhân viên tải về để support/debug có thể nằm ngoài đường lifecycle tự động.

**Retention ở từng kho không bằng nhau một cách tự động.** Ví dụ search index 14 ngày, object archive 90 ngày và backup 180 ngày chỉ có thể hợp lệ nếu có mục đích/căn cứ và quyền tương ứng. Nếu không, đó là dấu hiệu thiếu policy end-to-end.

Khi có yêu cầu xóa dữ liệu cá nhân, phải kiểm tra khả năng xóa ở index, archive, version và quy trình restore; không đánh dấu “đã xóa mọi nơi” khi chưa có bằng chứng. Nếu backup không chỉnh sửa từng event được, cần một **restore gate** và cơ chế replay deletion ledger/tombstone trước khi cho dữ liệu phục hồi được phục vụ theo chính sách.

## 15. Legal hold và dữ liệu kiểm toán: hai trường hợp cần cân nhắc riêng

**Legal hold** là quyết định giữ một tập dữ liệu vì căn cứ pháp lý hoặc điều tra phù hợp, có scope, người phê duyệt và thời điểm đánh giá lại. Nó **không phải một biến boolean cho người dùng cuối tự đặt** để tránh xóa dữ liệu.

Với dữ liệu audit/security bắt buộc:

- Phải xác định **trường nào thực sự cần giữ**, không lấy mọi log DEBUG làm “audit”.
- Có thể cần protected append-only/WORM storage, integrity check và quyền truy cập chặt.
- Không được để chính sách dọn local archive tự ý xóa bằng chứng khi chưa đến hạn.
- Cần quy trình xét lại hold, không giữ vô hạn chỉ vì không ai tắt flag.
- Có thể dùng **một kênh audit riêng** với vòng đời bảo vệ khác application logging.

Ngược lại, mục đích kiểm toán không có nghĩa **mọi PII trong log audit đều được phép giữ mãi**. Các trường không cần thiết nên loại ngay từ nguồn và có chính sách khử nhận dạng/xóa khi áp dụng.

Một bài học anti-pattern quan trọng: **gộp DEBUG, INFO và security audit vào cùng file/index chỉ vì tiện cấu hình**. Sau đó team không thể chọn retention ngắn cho DEBUG mà không ảnh hưởng audit. Hãy phân tách kênh theo mục đích từ thiết kế.

## 16. Data minimization giúp retention dễ thực thi

Retention không sửa được mọi rủi ro từ dữ liệu đã ghi sai. Nếu log chứa password, bearer token, session cookie, email đầy đủ hoặc request body không cần thiết, giữ 2 ngày vẫn có nguy cơ rò rỉ trong 2 ngày và trong các bản sao đã export.

Các thực hành cần có:

1. **Không ghi secret/credential từ đầu**. Không log raw Authorization/Cookie headers.
2. Tránh log nguyên URL query hoặc payload chứa PII khi không cần.
3. Dùng structured logging với eventCode, status, route template, duration và ID kỹ thuật phù hợp.
4. Phân biệt **pseudonymization** với anonymization thực sự; hash userId không mặc nhiên là vô danh.
5. Giới hạn DEBUG/TRACE ở production, dùng feature toggle có phê duyệt và tự hết hạn khi cần.
6. Áp dụng masking/redaction tại nguồn và collector; kiểm thử cả exception message từ thư viện thứ ba.
7. Có data inventory để biết dữ liệu đã đi đến đâu.
8. Retention của log, snapshots, exports, deletion ledger và dữ liệu hỗ trợ phải được quản lý tương ứng.

OWASP Logging Cheat Sheet nhấn mạnh việc log tạm, bản sao, backup và extraction không nên bị tiêu hủy **trước thời gian cần giữ**, nhưng cũng không nên giữ **quá thời hạn được quy định**. Đó là lý do retention phải cân bằng giữa tính sẵn có và giới hạn lưu dữ liệu.

## 17. Policy retention theo tuổi không giống cap theo dung lượng

Một nhầm lẫn phổ biến là coi **size cap** như một giải pháp retention duy nhất.

Ví dụ khi đặt maxHistory 30 và totalSizeCap 1GB cho archive chứa 10GB/tuần, cap có thể xóa file chỉ sau một thời gian ngắn. Nếu dữ liệu bắt buộc có sẵn 30 ngày, không thể coi policy này đáp ứng được. Cần tách:

| Mục tiêu | Cách quản lý |
| --- | --- |
| Giữ đủ thời gian tối thiểu | Protected storage đủ dung lượng, retention legal/compliance |
| Không giữ quá thời gian tối đa | Lifecycle delete/expiry và kiểm chứng |
| Ngăn local disk đầy | Size/time rotation, quota, log volume alert, chuyển tier |
| Giảm chi phí index | Hot/warm/cold tiers, data stream/index lifecycle |
| Giảm rủi ro PII | Minimize, redact, access controls, purge mọi bản sao |
| Khôi phục khi ingest lỗi | Buffered/durable shipping, replay có kiểm soát |

Không có thứ tự “cái nào cũng được”. Phải ưu tiên nghĩa vụ lưu giữ/quyền dữ liệu, cân đối dung lượng và thiết kế kỹ thuật có thể đảm bảo cả hai; khi không đáp ứng cần báo rủi ro và phương án đầu tư.

## 18. Quy trình triển khai một chiến lược retention

### Giai đoạn A — Inventory và phân loại

1. Liệt kê service, nguồn log, appender, stdout/file và đường ingest.
2. Xác định từng destination: container runtime, shipper queue, search index, archive, backup, support export.
3. Phân loại event: DEBUG, application, security, audit, infrastructure.
4. Xác định có PII/secret, quyền truy cập, owner và mục đích lưu.
5. Đánh giá nghĩa vụ pháp lý/hợp đồng/điều tra, thời hạn giữ tối thiểu/tối đa và các ngoại lệ.

### Giai đoạn B — Thiết kế

6. Chọn thời điểm bắt đầu retention, timezone/offset và dữ liệu đích.
7. Viết policy version hóa với owner và approval.
8. Phân tách kênh có retention khác nhau, tránh index/file dùng chung khi không phù hợp.
9. Dự báo bytes/day, peak, replication, backup và ngân sách.
10. Chọn cơ chế rotation, archive và delete phù hợp từng backend.
11. Thiết kế legal hold, deletion requests, restore gate và evidence of deletion.
12. Định nghĩa metric, alert, canary và rollback.

### Giai đoạn C — Kiểm thử

13. Tạo **dữ liệu tổng hợp** ở nơi kiểm thử, gồm event đủ loại, file cũ/mới, hold, object version và snapshot.
14. Chạy dry-run hoặc tính candidate count/bytes; xác nhận phạm vi path/index.
15. Thử rollover theo ngày/kích thước, file ít event và file log storm.
16. Thử tuổi tính theo lastModified/createdAt/eventTimestamp để phát hiện khác biệt.
17. Kiểm tra cleanup không xóa active file, log của tenant khác hoặc archive có hold.
18. Kiểm tra collector/index lifecycle, job status, versioning và snapshot.
19. Thử gián đoạn collector, disk full và khôi phục từ backup.
20. Đối chiếu lượng log thực sự bị dọn và dữ liệu vẫn cần giữ.

### Giai đoạn D — Rollout và giám sát

21. Áp dụng theo service/tier với change record và phạm vi tăng dần.
22. Kiểm tra cấu hình đang có hiệu lực trên từng replica và index/data stream.
23. Theo dõi age of oldest log, bytes retained, bytes/day, cleanup errors và disk free.
24. Kiểm tra log đã xóa không tái xuất hiện qua replay/restore không được phép.
25. Lưu deletion evidence, exception/hold registry và thời điểm review policy.
26. Thử định kỳ; khi traffic, luật, platform hoặc backend thay đổi thì đánh giá lại.

Không dùng một câu lệnh xóa hàng loạt trên production để “thử xem policy có chạy” trước khi có xác minh scope, backup, sự cho phép và kế hoạch khôi phục.

## 19. Monitoring retention: đo điều gì?

Một số metric khả thi:

~~~text
log_archive_bytes{service,storage_tier}
log_retained_bytes{service,storage_tier}
log_oldest_record_age_seconds{service,storage_tier}
log_ingested_bytes_total{service}
log_rotation_events_total{service,appender}
log_retention_runs_total{service,result}
log_retention_candidates_total{service,category}
log_retention_deleted_total{service,category}
log_retention_failures_total{service,reason}
log_legal_hold_segments{service,category}
log_index_lifecycle_errors{cluster}
node_filesystem_avail_bytes{mountpoint}
~~~

Metric names là **gợi ý**, không nhất thiết có sẵn trong Logback/Log4j 2 hoặc exporter của backend. Cần xây từ monitoring system, API storage/lifecycle hoặc công cụ vận hành phù hợp.

Một số alert quan trọng:

- Dung lượng còn trống dưới ngưỡng an toàn, disk fill rate tăng đột biến.
- Oldest archive/index vượt chính sách tối đa mà không có hold hợp lệ.
- Cleanup/ILM/ISM chạy lỗi nhiều lần hoặc không có successful run.
- File active/log volume tăng đột ngột do DEBUG/stack trace loop.
- Collector/backlog tăng khi storage downstream không nhận.
- Protected audit data có nguy cơ bị xóa sớm do cap hoặc lỗi cấu hình.
- Object versions/backup không tuân thủ thời hạn hoặc restore gây data reappearance.

**Không chỉ đo số file.** Một index có thể rất lớn; một directory chứa log nhỏ hàng năm nhưng volume ít; điều cần theo dõi là **tuổi, dung lượng, loại dữ liệu, khả năng truy cập và trạng thái thực thi policy**.

Hạn chế metric labels có cardinality cao: không đưa requestId, userId, email, raw filename ngẫu nhiên hoặc eventId vào label phổ biến.

## 20. Kiểm thử chống mất dữ liệu và xóa nhầm

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Application archive cũ quá policy | Được chọn đúng theo phạm vi và policy đã duyệt |
| File mới chưa hết hạn | Được giữ |
| Active file còn đang ghi | Không bị xóa bằng thao tác archive cleanup |
| Segment có legal hold hợp lệ | Không bị dọn cho tới khi hold được gỡ theo quy trình |
| Security/audit khác hạn với DEBUG | Không bị áp nhầm policy |
| Tăng lưu lượng log đột biến | Cảnh báo dung lượng, không âm thầm xóa chứng cứ bắt buộc |
| Logback ít ghi không kích hoạt rollover | Cleanup theo lịch/khởi động được thử, cảnh báo nếu chưa dọn |
| Log4j 2 Delete glob sai | Test phát hiện không xóa đúng file, không xóa ngoài basePath |
| Symlink tới thư mục bên ngoài | Không được follow/delete ngoài phạm vi |
| Central index có ILM/ISM | Kiểm tra trạng thái managed, delete phase và error thực tế |
| Archive có versioning | Không nhầm delete marker với xóa mọi phiên bản |
| Backup giữ bản cũ | Có retention và restore gate riêng |
| Subject đã có yêu cầu xóa | Không re-ingest dữ liệu đã được xóa hợp lệ |
| Service ít traffic hoặc stopped | Không giả định không có event nghĩa là lifecycle đã chạy |
| Sai timezone/clock | Không xóa nhầm trước tuổi vì mốc thời gian không rõ |
| Hai tenant trong một file/index | Không xóa nhầm dữ liệu tenant khác |
| Policy update/rollback | Chỉ ảnh hưởng phạm vi mong muốn, có audit trail |
| Disk full/permission denied | Cleanup báo lỗi có giám sát; không tuyên bố thành công |

Một bài kiểm thử cần kiểm tra **bản gốc trước/sau**, những record được giữ, archive phiên bản khác, snapshot và trạng thái job. Không đánh giá PASS chỉ từ cấu hình XML “trông đúng”.

## 21. Những nhầm lẫn và anti-pattern liên quan

**“Bật rolling log nghĩa là có retention.”** Rolling chỉ tổ chức file; cleanup cần quy tắc và kiểm tra riêng.

**“Logback maxHistory=14 chắc chắn giữ đủ 14×24 giờ.”** Với pattern daily, maxHistory quản lý kỳ archive; rollover và cleanup phụ thuộc hoạt động appender. Nó không phải đồng hồ xóa từng record.

**“totalSizeCap càng nhỏ càng an toàn.”** Cap quá nhỏ có thể xóa log trước thời gian tối thiểu cần giữ. Nó là biện pháp quản lý dung lượng, không đại diện nghĩa vụ retention.

**“Log4j 2 max=14 nghĩa là 14 ngày.”** Trong các chiến lược dùng %i, max có thể giới hạn số archive/index. Không suy diễn thành số ngày trừ khi policy cụ thể được chứng minh.

**“Khi đủ 14 ngày thì IfLastModified tự xóa đúng lúc.”** Delete action trong rolling strategy thường chạy với rollover; mtime của file khác với timestamp của từng event. Cần xác minh thực tế.

**“Xóa file trên server là xóa log khỏi mọi nơi.”** Collector, index, archive, object versions và backup có vòng đời độc lập.

**“Chỉ cần giữ ERROR vì INFO không quan trọng.”** Có những INFO/audit event cần giữ để điều tra; phân loại theo mục đích, không chỉ severity.

**“Audit là dữ liệu giữ mãi.”** Nghĩa vụ giữ có thời hạn/căn cứ cụ thể; không dùng chữ audit để biện minh vô hạn cho PII không cần thiết.

**“Backup không phải log nên không thuộc retention.”** Backup có thể chứa log và phục hồi dữ liệu đã xóa; cần chính sách riêng.

**“Đặt root level=ERROR là đã giảm rủi ro retention.”** Giảm volume không quyết định thời gian lưu, nguồn copy hay retention của audit/security.

**“Xóa theo filename timestamp luôn chính xác.”** Tên file có thể đổi, metadata timestamp có thể sai sau copy hoặc restore, event bên trong có thời điểm khác.

**“Xóa file cũ bằng cron rm -rf trong /var/log là giải pháp đủ tốt.”** Phá quyền, path safety, symlink, legal hold, backup và auditing. Nên dùng lifecycle chuyên dụng với dry-run/allowlist và kiểm chứng.

**“Storage rẻ nên lưu tất cả mãi.”** Chi phí tìm kiếm, quyền riêng tư, data breach exposure và nghĩa vụ xóa vẫn tồn tại dù disk rẻ.

**“Đã cấu hình retention 30 ngày nghĩa là backup cũng chỉ giữ 30 ngày.”** Phải kiểm tra từng nơi lưu.

## 22. Checklist triển khai

- [ ] Xác định policy retention theo loại log và mục đích, không chọn một số ngày cho mọi thứ.
- [ ] Có người phê duyệt, owner và policy version; pháp lý/compliance tham gia khi phù hợp.
- [ ] Biết dữ liệu ở local file, stdout, container, shipper, index, archive, snapshot, backup và export.
- [ ] Phân biệt rotation với expiry, archival và deletion.
- [ ] Logback maxHistory/totalSizeCap/cleanHistoryOnStart được kiểm thử theo phiên bản.
- [ ] Log4j 2 rollover strategy và Delete conditions giới hạn basePath, file pattern và tuổi chính xác.
- [ ] Application/debug và security/audit có kênh và chính sách phù hợp, không gộp tùy tiện.
- [ ] ILM/ISM/data stream lifecycle đã thực sự áp dụng lên index/cluster cần quản lý.
- [ ] Có kế hoạch storage capacity cho normal traffic, burst, retry, replay và backup.
- [ ] Có cơ chế legal hold hợp lệ, không xóa chứng cứ trước hạn.
- [ ] Có data minimization, PII redaction và quyền truy cập phù hợp.
- [ ] Backup/versioning/restore được kiểm soát, không hồi sinh dữ liệu đã xóa.
- [ ] Có dry-run, kiểm thử phân loại candidate, file active, symlink, tenant và lỗi permission.
- [ ] Giám sát cleanup failures, oldest age, disk free, retained bytes, index lifecycle và ingestion health.
- [ ] Có runbook khôi phục, audit thao tác, kiểm chứng xóa và quy trình review định kỳ.

**Kết luận:** Thiếu chiến lược retention là một **anti-pattern logging nghiêm trọng** vì không chỉ tốn dung lượng mà còn có thể làm **mất chứng cứ quá sớm** hoặc **giữ dữ liệu nhạy cảm quá lâu**. Hãy định nghĩa policy theo mục đích, tách các loại log có nghĩa vụ khác nhau, áp dụng cơ chế phù hợp ở từng tầng lưu trữ và **xác minh bằng dữ liệu thực tế**. Rotation, cấu hình XML, policy JSON hay một số ngày ghi trên tài liệu đều chưa đủ nếu không có vận hành, monitoring và xử lý ngoại lệ.

## 23. Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): quản lý logging, bảo vệ, retention và disposal, bao gồm backups/copies/extractions.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): TimeBasedRollingPolicy, maxHistory, totalSizeCap, cleanHistoryOnStart, hoạt động rollover.
- [Log4j 2 — Rolling File Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): rollover policies, Default/DirectWriteRolloverStrategy, Delete, IfFileName và IfLastModified.
- [Elasticsearch — Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management): ILM, rollover và retention của index/data stream.
- [Elasticsearch — Index lifecycle phases/actions](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management/index-lifecycle): điều kiện phase và delete action.
- [OpenSearch — Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/index/): policy, states, transitions, rollover và delete.
- [OpenSearch — ISM Policies](https://docs.opensearch.org/latest/im-plugin/ism/policies/): policy management, index templates và áp dụng cho managed indexes.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, observed timestamp, resource và attributes.
- [Oracle Java SE 17 — java.time.Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): biểu diễn duration và phương pháp đánh giá expiry.
- [Oracle Java SE 17 — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): so sánh thời điểm và cộng Duration.
