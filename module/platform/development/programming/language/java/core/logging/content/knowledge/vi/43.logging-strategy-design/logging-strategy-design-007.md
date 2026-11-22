# Chọn retention cho Java Logging: lưu bao lâu, ở đâu và xóa như thế nào?

## 1. Retention là một quyết định thiết kế, không chỉ là số ngày

**Log retention** là chính sách xác định bản ghi log **được giữ trong bao lâu, ở hệ thống nào, với quyền truy cập nào, khi nào chuyển tầng lưu trữ và khi nào bị xóa hoặc ẩn khỏi hệ thống**. Trong kiến trúc Java, quyết định này có thể áp dụng độc lập ở file log của JVM, log container, shipper, Collector, cơ sở dữ liệu tìm kiếm, object storage, snapshot, archive và bản export.

Khi thiết kế chiến lược log, câu hỏi đúng không phải chỉ là “để 30 ngày hay 90 ngày?”. Cần trả lời:

1. **Giữ để làm gì?** Chẩn đoán incident, bảo mật, truy vết giao dịch, kiểm toán, điều tra vận hành, phân tích xu hướng?
2. **Giữ loại dữ liệu gì?** DEBUG, INFO, ERROR, access logs, security events, audit trail, exception, trace-correlated logs?
3. **Ai được xem và truy xuất?** Developer, SRE, security team, kiểm toán viên, tenant hoặc bên thứ ba?
4. **Khi nào bắt đầu tính tuổi bản ghi?** Thời điểm xảy ra sự kiện, lúc ingest, khi đóng index, lúc tạo archive?
5. **Lưu ở những tầng nào?** Local rolling file, Kubernetes node, hot index, warm/cold archive, object storage, snapshot, backup?
6. **Xóa đúng nghĩa gì?** Hết xuất hiện trong search, index được delete, object đã xóa, snapshot/backups hết hạn hay dữ liệu bị hủy theo phương pháp phù hợp?
7. **Có ngoại lệ pháp lý/nghiệp vụ nào?** Legal hold, incident investigation, yêu cầu bảo toàn chứng cứ, quy định bảo vệ dữ liệu?
8. **Kiểm chứng bằng cách nào?** Đo khối lượng, kiểm tra rollover và policy, thực thi dry-run, xác nhận xóa, quan sát lỗi cleanup?

**Nguyên tắc:** Thời hạn retention phải dựa trên **mục đích xử lý, mức độ rủi ro, nhu cầu điều tra, nghĩa vụ áp dụng và năng lực vận hành**. Không có một con số ngày duy nhất đúng cho mọi công ty, mọi loại log hoặc mọi quốc gia.

## 2. Những khái niệm không nên nhầm

| Thuật ngữ | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| **Retention period** | Khoảng thời gian bản ghi được phép/phải giữ theo policy | Kích thước một file hoặc số bản archive |
| **Rollover/rotation** | Đóng file/index cũ và bắt đầu file/index mới do thời gian/kích thước | Xóa sạch mọi bản sao log |
| **Local buffer** | Vùng đệm trong JVM, process hoặc agent | Lưu trữ bền vững |
| **Hot storage** | Dữ liệu truy vấn nhanh, thường chi phí cao hơn | Tổng thời gian lưu của toàn pipeline |
| **Warm/cold tier** | Dữ liệu ít truy cập, có thể truy vấn chậm/đòi restore | Xóa dữ liệu |
| **Archive** | Bản lưu cho truy xuất lâu dài hơn theo chính sách | Mặc nhiên immutable hay được phép giữ vô hạn |
| **Index deletion** | Xóa index/partition hoặc đối tượng tìm kiếm | Mọi backup/export đã được xóa |
| **Legal hold** | Tạm ngưng xóa dữ liệu nằm trong phạm vi phải bảo toàn | Quyền lưu/đọc tất cả dữ liệu mãi mãi |
| **Data minimization** | Chỉ thu các trường cần thiết ngay từ đầu | Có thể giữ raw secret trong thời gian ngắn |
| **Data lifecycle** | Thu thập → truy vấn → chuyển tier → xóa → đối chiếu | Một tác vụ cron xóa file riêng lẻ |

Một file có thể bị **rotate vì đạt 100 MB** nhưng các archive vẫn được giữ nhiều tháng; ngược lại, một backend có policy 14 ngày vẫn có thể mất log sớm do quota/disk full. Rotation điều khiển **đơn vị lưu**, retention điều khiển **vòng đời dữ liệu**.

## 3. Vì sao không nên dùng cùng thời hạn cho tất cả logs?

Các loại log có mục đích và rủi ro khác nhau:

- **DEBUG/TRACE:** nhiều thông tin nội bộ, khối lượng lớn; thường hữu ích trong một cửa sổ điều tra ngắn. Bật chi tiết lâu dài có thể gây lộ thông tin và tốn chi phí.
- **INFO vận hành:** phản ánh vòng đời request/job và các sự kiện hệ thống; có thể cần lâu hơn DEBUG để so sánh với release hoặc sự cố lặp.
- **WARN/ERROR:** phục vụ sự cố và phân tích lỗi; retention phụ thuộc chu kỳ phát hiện, xử lý và hậu kiểm incident.
- **Access logs:** giúp phân tích HTTP traffic, bảo mật và hiệu năng; có thể chứa IP, user-agent, URL, query parameters và dữ liệu cá nhân.
- **Security logs:** đăng nhập, từ chối quyền, thay đổi cấu hình bảo mật; cần đánh giá nguy cơ tấn công chậm phát hiện và yêu cầu bảo vệ chứng cứ.
- **Audit trail:** ghi ai làm gì, trên đối tượng nào, kết quả ra sao; có thể có retention và tính toàn vẹn theo nghĩa vụ cụ thể.
- **Job/message logs:** cần cho truy vết retry và workflow; không nên thay thế business event store nếu phải lưu lịch sử nghiệp vụ bền vững.
- **Platform/Collector logs:** chẩn đoán chính pipeline vận chuyển; có thể cần một chính sách độc lập để phát hiện log bị mất.

**Đừng mặc định INFO là audit** hoặc ERROR phải giữ vô hạn. Ý nghĩa lưu giữ đến từ **lớp sự kiện và mục đích**, không chỉ level.

## 4. Bảng retention minh họa theo mục đích

Đây là **kịch bản giả lập để học thiết kế**, hoàn toàn **không phải** khuyến nghị pháp lý hoặc con số bắt buộc:

| Nhóm | Retention ví dụ | Lý do giả lập | Điều cần xem xét trước khi áp dụng |
| --- | --- | --- | --- |
| DEBUG/TRACE | 3 ngày | Điều tra ngay sau lỗi/deploy | Có sampling, dữ liệu nhạy cảm, lượng log cao |
| INFO app | 14 ngày | Hậu kiểm vận hành ngắn hạn | Chu kỳ incident, latency phát hiện và query |
| WARN/ERROR | 30 ngày | Điều tra lỗi và so sánh release | Error code, stack trace, truy cập hạn chế |
| Access log | 14–30 ngày | Kiểm tra HTTP/API và an toàn hệ thống | IP/query/headers, policy quyền riêng tư |
| Security event | 90 ngày hoặc theo chính sách riêng | Phát hiện bất thường chậm | Threat model, sự cố, quyền và nghĩa vụ áp dụng |
| Audit log | Theo lịch bảo quản được phê duyệt | Truy vết hành động có ý nghĩa | Pháp lý/ngành, legal hold, integrity, quyền đọc |
| Agent/Collector diagnostic | 7 ngày | Điều tra pipeline hoạt động sai | Cần bằng chứng khi mất log hay exporter fail |
| Kho archive | Đến hết thời hạn tổng được phép | Truy xuất hiếm, phục hồi có kiểm soát | Backup, legal hold, xóa và chi phí |

**Không copy các số trên thành policy production.** Ví dụ 90 ngày không tự đáp ứng một quy định cụ thể; cũng không có cơ sở rằng cứ giữ audit lâu nhất là hợp pháp hoặc cần thiết. Bộ phận sở hữu dữ liệu, bảo mật, pháp chế và vận hành cần phê duyệt **retention schedule** theo hệ thống, loại dữ liệu và khu vực pháp lý thực tế.

Một loại event có thể cần tách thành **event summary ít nhạy cảm** để giữ lâu, còn raw diagnostics chỉ giữ ngắn. Nếu phải giữ một sự kiện vì kiểm toán, không nhất thiết giữ nguyên mọi request body và stack trace kèm theo.

## 5. Quy trình chọn retention theo các bước

### Bước 1 — Lập danh mục nguồn log

Ghi lại: dịch vụ Java, framework, env/region, class event, mức log, khối lượng, dữ liệu có thể chứa, sink, chủ sở hữu và người được truy cập. Đừng bỏ qua log được sinh từ framework bên thứ ba, reverse proxy, JDBC driver, message broker và agent.

### Bước 2 — Xác định mục đích và câu hỏi cần trả lời

Ví dụ: “SRE cần so sánh lỗi giữa hai phiên bản triển khai trong một chu kỳ release” hoặc “Security cần truy vết các lần đăng nhập bị từ chối theo thời gian điều tra được phê duyệt”. Mục đích phải cụ thể để kiểm chứng retention có đủ hay không.

### Bước 3 — Xác định thời điểm có giá trị

Incident thường được phát hiện sau sự kiện một khoảng thời gian. Thu thập dữ liệu từ vận hành: **time to detect**, **time to investigate**, chu kỳ release, chu kỳ phân tích rủi ro, thời hạn SLA và khoảng thời gian có nghĩa vụ bảo toàn.

### Bước 4 — Phân loại độ nhạy và giới hạn bảo vệ

Một log chứa token hoặc số thẻ không trở nên an toàn vì giữ có ba ngày. **Loại bỏ hoặc mask tại nguồn** trước khi tính retention. Quyền truy cập, encryption, export và vùng địa lý cũng là phần của policy.

### Bước 5 — Kiểm tra nghĩa vụ và ngoại lệ

Trao đổi với người chịu trách nhiệm compliance/legal khi có luật, hợp đồng, điều kiện khách hàng, incident hold hoặc nghĩa vụ lưu chứng cứ. Khi các yêu cầu xung đột, cần quy trình giải quyết và hồ sơ phê duyệt, không tự lấy số ngày dài nhất để giữ mọi dữ liệu.

### Bước 6 — Tính dung lượng/chi phí và quyết định các tier

Đo lượng log **thật** theo loại và env, tỷ lệ nén, index overhead, replicas, data transfer và chi phí query. Thiết kế hot/warm/cold và buffer cục bộ.

### Bước 7 — Thiết kế điểm xóa cho từng bản sao

Lập danh sách nơi log tồn tại: JVM/file, runtime node, agent queue, Collector, hot index, cold object, snapshot, backup, export. Xác định hệ thống nào chịu trách nhiệm xóa và dấu hiệu xác nhận.

### Bước 8 — Kiểm thử, giám sát, điều chỉnh

Test dry-run, chính sách xóa, legal hold, restart/rotation và query; theo dõi data age, oldest searchable event, deletion lag, storage usage, failed deletes. Review retention khi kiến trúc, mối đe dọa hoặc nghĩa vụ thay đổi.

## 6. Retention bắt đầu từ thời điểm nào?

Một log event có thể có nhiều timestamp:

~~~text
event occurredAt:   2026-11-01T10:00:00Z
agent observedAt:  2026-11-01T10:00:05Z
backend ingestedAt:2026-11-01T10:00:09Z
archive createdAt: 2026-11-02T00:00:00Z
~~~

Các mốc này **không tương đương**. Nếu chính sách quy định “14 ngày kể từ khi sự kiện xảy ra”, dùng ngày tạo archive hoặc `lastModifiedTime` của file được copy lại có thể khiến dữ liệu giữ lâu hơn hoặc ít hơn dự định.

**Những quy tắc cần định nghĩa:**

- **Event time:** thời điểm logic diễn ra, ưu tiên UTC và đồng bộ clock.
- **Ingest time:** thời điểm backend chấp nhận event; có thể dùng cho ingestion-based lifecycle nhưng chưa chắc khớp nghĩa vụ dữ liệu.
- **Index creation/rollover time:** lifecycle index có thể dựa trên thời điểm rollover/creation, không cùng tuổi của từng document.
- **Archive object created time:** object được copy/migrate gần đây có thể mang thời gian sửa mới hơn dù log gốc đã cũ.
- **Date-granularity:** “giữ ngày cuối cùng” có thể được hiểu giữ trọn ngày theo UTC; khác với chính xác 14×24 giờ tính theo từng event.

Chọn rõ **inclusive/exclusive boundary**. Ví dụ policy 14 ngày của demo Java ở phần 11 xóa file có ngày *nhỏ hơn* `today.minusDays(14)`; file đúng ngày cutoff được giữ. Đó là quyết định để test có đầu ra xác định, **không phải định nghĩa chung của mọi retention policy**.

Đối với dữ liệu nhạy cảm có yêu cầu xóa chính xác theo thời gian, lưu file chung nhiều ngày có thể không cho phép xóa từng record dễ dàng. Có thể chọn partition/index/time bucket phù hợp hoặc quy trình xóa có kiểm soát ở mức document.

## 7. Phân biệt local retention và backend retention

~~~text
Java Logger
   │
   ▼
[Local rolling file]   ←  giới hạn số file/kích thước/ngày tại host
   │
   ▼
[Agent / Collector]    ←  queue/buffer/checkpoint, có thể lưu bản sao
   │
   ▼
[Hot index]            ←  giữ để query nhanh
   │
   ▼
[Warm/Cold/Object]     ←  giữ ít truy cập hơn
   │
   ▼
[Delete/purge]         ←  theo lịch tổng, ngoại lệ và bằng chứng xử lý
   │
   └── [Snapshot / backup / export] có vòng đời riêng
~~~

Một chính sách “14 ngày trong Elasticsearch/OpenSearch/Loki” **không** tự xóa file Logback ở server hoặc snapshot trong object storage. Ngược lại, cấu hình Logback `maxHistory=7` không kiểm soát bản sao đã gửi tới backend.

Nên có **bảng ownership**: Java team chịu trách nhiệm phát dữ liệu an toàn, platform team chịu trách nhiệm local shipping và cluster lifecycle, observability team sở hữu index/tier policy, security/legal sở hữu lịch bảo quản khi cần. Đường đi có thể khác ở công ty khác, nhưng trách nhiệm phải rõ.

Đặc biệt với pipeline async, agent có thể **chưa ship hết** khi local log bị rotate/xóa. Nếu TTL local quá ngắn so với thời gian outage mà queue không bền vững, có nguy cơ mất log trước khi downstream nhận được.

## 8. Một chính sách retention tốt có thể khác nhau theo môi trường

| Môi trường | Nhu cầu thực tế | Cẩn trọng |
| --- | --- | --- |
| Local development | Debug nhanh, không cần kho tập trung dài hạn | Không copy dữ liệu production vào log local |
| CI/Test | Giữ log để chẩn đoán failure đúng job | Artifact và CI logs cũng cần TTL và quyền truy cập |
| Staging | Test integration, load và rollout | Test data có thể vẫn là thông tin nhạy cảm |
| Production | Quan sát, sự cố, an toàn, audit | Scope quyền, retention theo event class, chi phí |
| Disaster recovery | Phục hồi dữ liệu phù hợp với policy | Backup không được biến thành lưu giữ vô hạn |

**Không mặc định staging là “không có dữ liệu thật”**. Dữ liệu sao chép hoặc dữ liệu tích hợp từ vendor có thể chịu cùng nghĩa vụ bảo vệ như production.

Nếu bật DEBUG tạm thời để chẩn đoán, có thể đặt deadline tắt lại và retention ngắn hơn cho stream đó. Đừng để thao tác bật debug tạm biến thành một chính sách thu thập dài hạn ngoài ý định.

## 9. Rotation theo kích thước và thời gian: khác retention

Một appender có thể rollover:

- **Theo kích thước:** đến ngưỡng MB thì tạo file mới.
- **Theo thời gian:** sang ngày/giờ/tuần/tháng mới tạo archive.
- **Kết hợp:** một ngày có nhiều file nếu log volume cao.

Dù vậy:

- Rollover **không phải** cam kết xóa trên tất cả storage.
- Nếu nhiều file chứa cùng ngày, việc xóa theo filename/date cần xử lý toàn bộ archive trong period.
- Tác vụ cleanup có thể chạy **khi rollover xảy ra**, không phải cron đúng mốc đồng hồ.
- Với ứng dụng ít phát log, đến mốc thời gian mới nhưng chưa có event mới có thể chưa kích hoạt rollover.
- Các file đang active thường khác archive; không xóa active file bằng một cron generic khi app đang ghi.
- Tổng size cap có thể **xóa sớm hơn** time-based retention. Cần quyết định đó có được phép đối với event bắt buộc không.

Do đó chọn cả **tầng cục bộ** và **tầng tập trung**. Nếu retention là yêu cầu kiểm toán, appender rolling thông thường không phải hệ thống bảo quản độc lập.

## 10. Java JUL: `FileHandler` có vòng xoay file, không phải lịch lưu theo ngày

`java.util.logging.FileHandler` trong JDK 17 hỗ trợ `pattern`, `limit` (xấp xỉ số bytes mỗi file), `count` (số file xoay vòng) và `append`. Ví dụ:

~~~java
// Fragment; cần import java.util.logging.FileHandler;
// có thể ném IOException/SecurityException.
var handler = new java.util.logging.FileHandler(
        "%t/app-%u.%g.log", 10_000_000, 4, true);
~~~

Ý nghĩa: ghi file theo pattern, với giới hạn xấp xỉ **10 MB mỗi file** và xoay vòng **4 file**, không phải giữ 4 ngày. Thời gian mỗi file tồn tại **phụ thuộc tốc độ phát log**: khi lưu lượng cao có thể bị ghi đè nhanh; khi thấp có thể ở lại lâu.

Các giả định quan trọng:

- `%t` là thư mục tạm, `%u` giúp tránh xung đột giữa tiến trình, `%g` là generation.
- Không có policy theo ngày/legal hold built-in tương đương hệ thống quản lý retention tập trung chỉ từ `limit`/`count`.
- Chọn charset/formatter theo policy; không log credentials vào file local.
- Bảo đảm quyền file và xử lý disk full; FileHandler có thể báo lỗi I/O qua `ErrorManager`.
- Không dùng FileHandler vòng xoay để giữ audit bắt buộc nếu nó có thể ghi đè trước thời hạn cần giữ.

Nếu yêu cầu “giữ 14 ngày tính theo event time”, hãy chọn cơ chế archive/cleanup theo thời gian phù hợp hoặc để backend quản lý retention; không suy luận `limit×count` ra số ngày nếu không biết log rate.

## 11. Ví dụ Java 17 chạy độc lập: kiểm tra retention theo file và legal hold

Để hiểu **ra quyết định xóa** mà không tác động file thật, chương trình sau:

1. Tạo một thư mục tạm riêng do chính chương trình sở hữu.
2. Tạo 7 file fixture giả: `app`, `debug`, `audit` và một file không được nhận diện.
3. Định nghĩa retention **chỉ phục vụ demo**: `app=14 ngày`, `debug=3 ngày`, `audit=90 ngày`.
4. Dùng một `LocalDate` cố định để kết quả kiểm thử không phụ thuộc ngày chạy thật.
5. Chạy **dry-run** để đếm file đủ điều kiện xóa mà không xóa.
6. Chạy **apply** và kiểm tra chính xác các file còn lại.
7. Bỏ qua file không đúng naming convention và symlink, giữ audit file có cờ **hold**.
8. Xóa toàn bộ fixture tạm trong `finally`.

**Quan trọng:** Không sao chép nguyên chương trình làm job xóa log production. Bản production cần quyền được phê duyệt, xử lý cạnh tranh với appender/shipper, storage semantics, transaction/audit cho cleanup, distributed hold, timezone, backup, deletion acknowledgment và chống TOCTOU/symlink race. Demo cố ý dùng file name chứa ngày và legal-hold set giả, không phải enforcement đủ mạnh.

### 11.1. Tạo tệp RetentionPolicyDemo.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class RetentionPolicyDemo {
    private static final Pattern FILE_NAME = Pattern.compile(
            "^(app|debug|audit)-(\\d{4}-\\d{2}-\\d{2})\\.log$");
    private static final Map<String, Long> DAYS =
            Map.of("app", 14L, "debug", 3L, "audit", 90L);
    private static final Set<String> HOLDS =
            Set.of("audit-2026-01-01.log");

    record Stats(int eligible, int kept, int held, int unrecognized) {}

    static Stats sweep(Path directory, LocalDate today, boolean dryRun)
            throws IOException {
        List<Path> candidates;
        try (Stream<Path> stream = Files.list(directory)) {
            candidates = stream.sorted(Comparator.comparing(
                    path -> path.getFileName().toString())).toList();
        }
        int eligible = 0, kept = 0, held = 0, unrecognized = 0;

        for (Path path : candidates) {
            String name = path.getFileName().toString();
            Matcher matcher = FILE_NAME.matcher(name);
            if (Files.isSymbolicLink(path)
                    || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                    || !matcher.matches()) {
                unrecognized++;
                continue;
            }

            LocalDate fileDate;
            try {
                fileDate = LocalDate.parse(matcher.group(2));
            } catch (DateTimeParseException invalid) {
                unrecognized++;
                continue;
            }

            if (HOLDS.contains(name)) {
                held++;
                continue;
            }

            long days = DAYS.get(matcher.group(1));
            LocalDate cutoff = today.minusDays(days);
            if (fileDate.isBefore(cutoff)) {
                eligible++;
                if (!dryRun) Files.delete(path);
            } else {
                kept++;
            }
        }
        return new Stats(eligible, kept, held, unrecognized);
    }

    public static void main(String[] args) throws Exception {
        Path demoDirectory = Files.createTempDirectory("retention-demo-");
        try {
            List<String> names = List.of(
                    "app-2026-10-20.log",
                    "app-2026-11-01.log",
                    "audit-2026-01-01.log",
                    "audit-2026-10-10.log",
                    "debug-2026-11-01.log",
                    "debug-2026-11-09.log",
                    "readme.txt");
            for (String name : names) {
                Files.writeString(demoDirectory.resolve(name),
                        "FAKE TEST LOG\n", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);
            }

            LocalDate today = LocalDate.of(2026, 11, 10);
            Stats expected = new Stats(2, 3, 1, 1);
            Stats preview = sweep(demoDirectory, today, true);
            if (!preview.equals(expected)) {
                throw new AssertionError("Unexpected dry-run: " + preview);
            }
            System.out.printf(
                    "DRY_RUN eligible=%d held=%d kept=%d unrecognized=%d%n",
                    preview.eligible(), preview.held(), preview.kept(),
                    preview.unrecognized());

            Stats applied = sweep(demoDirectory, today, false);
            if (!applied.equals(expected)) {
                throw new AssertionError("Unexpected apply: " + applied);
            }
            System.out.printf(
                    "APPLY deleted=%d held=%d kept=%d unrecognized=%d%n",
                    applied.eligible(), applied.held(), applied.kept(),
                    applied.unrecognized());

            List<String> remaining;
            try (Stream<Path> stream = Files.list(demoDirectory)) {
                remaining = stream.map(path -> path.getFileName().toString())
                        .sorted().toList();
            }
            List<String> expectedRemaining = List.of(
                    "app-2026-11-01.log",
                    "audit-2026-01-01.log",
                    "audit-2026-10-10.log",
                    "debug-2026-11-09.log",
                    "readme.txt");
            if (!remaining.equals(expectedRemaining)) {
                throw new AssertionError("Unexpected files: " + remaining);
            }
            System.out.println("REMAINING=" + remaining.size());
        } finally {
            try (Stream<Path> stream = Files.list(demoDirectory)) {
                for (Path path : stream.toList()) Files.deleteIfExists(path);
            }
            Files.deleteIfExists(demoDirectory);
        }
    }
}
~~~

### 11.2. Lệnh chạy và stdout chính xác

~~~bash
javac --release 17 RetentionPolicyDemo.java
java RetentionPolicyDemo
~~~

**Standard output (stdout):**

~~~text
DRY_RUN eligible=2 held=1 kept=3 unrecognized=1
APPLY deleted=2 held=1 kept=3 unrecognized=1
REMAINING=5
~~~

**Standard error (stderr):** trống; exit code `0` khi mọi assertion thành công.

### 11.3. Diễn giải

- Ngày demo là `2026-11-10`. `app` có cutoff `2026-10-27`: file ngày 2026-10-20 bị chọn xóa, ngày 2026-11-01 được giữ.
- `debug` có cutoff `2026-11-07`: file 2026-11-01 bị chọn xóa, 2026-11-09 được giữ.
- `audit` có cutoff khoảng 90 ngày trước; file 2026-01-01 đã cũ nhưng **nằm trong `HOLDS`**, nên được giữ; file 2026-10-10 cũng được giữ.
- `readme.txt` không khớp schema tên file nên bị bỏ qua; mặc định **không động vào file không nhận diện**.
- Chạy preview trả `eligible=2` nhưng **chưa xóa**. Chạy apply xóa đúng hai file fixture; sau đó còn năm file.
- `Files.isRegularFile(..., NOFOLLOW_LINKS)` và kiểm tra symlink là hàng rào đơn giản của demo, không loại bỏ mọi **race condition** nếu một actor khác có thể đổi file giữa kiểm tra và xóa.
- Nhận dạng retention dựa vào **ngày trong tên file**, không đọc timestamp của từng event; với file chứa record thuộc nhiều ngày, kết quả có thể không phù hợp một policy ở mức sự kiện.
- `HOLDS` chỉ là một `Set` cứng trong code để minh họa ưu tiên bảo toàn; một legal hold thực phải được quản lý và thực thi bởi các hệ thống lưu trữ/pháp lý có kiểm soát.

Thử đổi ngày cutoff, giữ nguyên hold hoặc thêm file sai pattern để xem test failure. Không thay thư mục demo thành `/var/log` hay một folder đang dùng thật.

## 12. Logback: cấu hình local rolling retention

Với ứng dụng dùng **SLF4J + Logback Classic**, `RollingFileAppender` có thể dùng `TimeBasedRollingPolicy` để quản lý các file archive. Ví dụ **logback.xml** sau chỉ là một chính sách **cục bộ minh họa**, không phải hợp đồng lưu dài hạn:

~~~xml
<configuration>
    <appender name="DIAGNOSTIC"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/diagnostic.log</file>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/diagnostic.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="DIAGNOSTIC"/>
    </root>
</configuration>
~~~

**Điều các tham số thực sự làm:**

- `fileNamePattern` với `%d{yyyy-MM-dd}` tạo archive theo chu kỳ ngày. `maxHistory=7` giữ khoảng bảy **period** archive theo cơ chế Logback, không phải một chính sách pháp lý “168 giờ kể từ mỗi event”.
- `totalSizeCap=1GB` giới hạn tổng kích thước archive; yêu cầu `maxHistory` được cấu hình. Nó có thể khiến archive cũ bị xóa **sớm hơn** chu kỳ ngày.
- `cleanHistoryOnStart=true` yêu cầu cleanup khi appender khởi động, quan trọng khi ứng dụng ít ghi log nên chưa rollover lại.
- Việc cleanup archive có thể chạy bất đồng bộ; **không** dựa vào một thời điểm xóa chính xác đến từng giây.
- Cấu hình không xóa dữ liệu đã được ship tới backend, snapshot hoặc backup, cũng không xử lý legal hold.
- `logs/diagnostic.log` là file đang ghi; archive cleanup và active file là các trường hợp khác nhau.
- Timezone/default settings và quyền thư mục phải được kiểm tra theo môi trường deploy.

Nếu ứng dụng nhiều log trong một ngày và cần giới hạn kích thước **mỗi file**, cân nhắc `SizeAndTimeBasedRollingPolicy` với `%d` và `%i`; đừng nhầm `maxFileSize` với tổng lưu giữ.

**Cảnh báo:** Không áp `totalSizeCap` nhỏ lên một kênh audit có nghĩa vụ giữ đầy đủ; size cap có thể xóa dữ liệu trước lịch. Không dùng chung appender cho debug và audit nếu chúng cần thời hạn và quyền khác nhau.

## 13. Log4j 2: Delete action, IfFileName và IfLastModified

Log4j 2 Core hỗ trợ các **rolling strategies** và một `Delete` action để dọn file archive theo điều kiện. Có thể cấu hình **chế độ thử** trước khi xóa thật.

Ví dụ **log4j2.xml** chỉ áp dụng cho ứng dụng có Log4j 2 Core tương thích:

~~~xml
<Configuration>
    <Appenders>
        <RollingFile name="DIAGNOSTIC"
                     filePattern="logs/diagnostic.%d{yyyy-MM-dd}.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <DirectWriteRolloverStrategy>
                <Delete basePath="logs" testMode="true">
                    <IfFileName glob="diagnostic.*.log.gz"/>
                    <IfLastModified age="P7D"/>
                </Delete>
            </DirectWriteRolloverStrategy>
            <TimeBasedTriggeringPolicy/>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="DIAGNOSTIC"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Cách đọc:**

- `DirectWriteRolloverStrategy` dùng `filePattern` để đặt archive; `TimeBasedTriggeringPolicy` kích hoạt rollover theo thời gian.
- `Delete basePath="logs"` chỉ đánh giá file trong phạm vi thư mục. Theo mặc định, Log4j 2 không theo symbolic links khi đi qua đường dẫn; **không bật `followLinks=true` tùy tiện**.
- `IfFileName` thu hẹp phạm vi để không xóa file của ứng dụng/kênh khác.
- `IfLastModified age="P7D"` dùng **thời gian sửa file** theo điều kiện Log4j 2, không phải timestamp từng log event.
- `testMode="true"` **không xóa**, mà ghi thông tin những file phù hợp vào Status Logger. Sau khi xác minh path/đối tượng/hold và có phê duyệt, mới có thể chuyển sang chính sách thực thi; không tự bỏ testMode trong production.
- Nếu đối tượng log nằm trong kho tập trung hoặc cần legal hold, chính sách xóa archive cục bộ **không thay thế** lifecycle ở storage đó.

**Rủi ro thực tế:** Một pattern `IfFileName` quá rộng hoặc `basePath` sai có thể xóa file không thuộc phạm vi mong muốn. Test trên thư mục tạm, dùng quyền tối thiểu, lưu log kiểm toán của tác vụ dọn dẹp và quan sát lỗi.

## 14. Local rolling files không quyết định retention của log tập trung

Giả sử Logback chỉ giữ 7 archive ngày tại host, trong khi OpenSearch giữ INFO log 30 ngày. Đây **không phải mâu thuẫn** nếu mục đích của local file là buffer ngắn hạn và backend là nơi tra cứu chính.

Nhưng cần kiểm tra:

1. Agent có đọc được tất cả archive trước khi local cleanup không?
2. Khi Collector mất kết nối hai ngày, local files/queue có đủ giữ record cho replay không?
3. File rotate bằng rename hay copytruncate có được agent theo dõi đúng không?
4. Ứng dụng khi restart có xóa cũ trước khi agent đọc không?
5. Backend có thực sự nhận các event đã ship hay chỉ ACK ở một proxy?
6. Có log trùng từ việc ship **stdout lẫn file** không?
7. Nếu một event là audit bắt buộc, có durable recorder riêng thay vì best-effort local rotation không?

**Đừng đặt local retention = 1 ngày một cách máy móc** nếu backend có outage có thể kéo dài lâu hơn và shipper không có buffer bền vững. Ngược lại, không nên giữ vô hạn file trên host “để phòng khi backend lỗi”: disk full có thể làm hại cả ứng dụng.

Một chính sách tốt ghi rõ **SLO của pipeline**, ví dụ thời gian trễ tối đa để ship, mức queue bền vững, alert trước ngưỡng disk và cách xử lý khi vượt hạn.

## 15. Kubernetes: kubelet log rotation không phải kho lưu lịch sử

Khi Java container ghi stdout/stderr, container runtime và kubelet quản lý file log trên node. Kubernetes có các cấu hình `containerLogMaxSize` và `containerLogMaxFiles` để giới hạn file log cho mỗi container.

Điều cần nhớ:

- Đây là **rotation và giới hạn lưu cục bộ trên node**, không phải lịch bảo quản của backend log tập trung.
- `kubectl logs` thường chỉ hiển thị file log hiện tại theo kiến trúc kubelet; dữ liệu xoay trước đó không mặc nhiên truy vấn được qua API này.
- Pod bị xóa/evicted hoặc node hỏng có thể làm mất bản log chỉ tồn tại trên node.
- Kubelet/container runtime dùng định dạng CRI; agent cần đọc, checkpoint và xử lý partial records.
- Một DaemonSet shipper có thể thu stdout/stderr rồi chuyển sang Collector hoặc backend, nhưng retention tại đích phải được thiết kế riêng.
- Sidecar ghi cùng dữ liệu sang file và stdout có thể tạo duplicate hoặc tăng chi phí local storage.

Khi chọn retention **để điều tra incident xuyên pod/node**, cần một cluster-level logging backend với vòng đời riêng. Không dựa vào khả năng `kubectl logs --previous` như phương án lưu trữ lâu dài.

## 16. Retention của Collector, shipper và exporter queue

**OpenTelemetry Collector** là bộ thu thập/xử lý/chuyển log, **không phải hệ thống index/search retention mặc định**. Collector có thể dùng batch, memory limiter, queue/retry hoặc persistent queue theo component và cấu hình; retention ở queue chỉ là **buffer lifecycle**.

Một pipeline điển hình:

~~~text
Java stdout / OTLP
    → agent/receiver
    → memory limiter + batch/transform
    → queued exporter/retry
    → log backend có storage policy
~~~

Nếu exporter có queue trên RAM, process crash có thể làm mất pending records. Nếu queue dùng storage persistent, cần xác định dung lượng, quyền, encryption, cleanup, điều kiện replay và điều gì xảy ra khi disk full.

**Không nói “Collector giữ 30 ngày”** chỉ vì backend giữ 30 ngày hoặc file queue có nhiều dữ liệu. Kênh transport và kho log có hợp đồng khác nhau. Khi outage, dữ liệu queue có thể già hơn lúc bắt đầu; cần quy tắc retry expiration/quarantine để tránh đẩy log đã vượt policy vào kho.

Các telemetry cần theo dõi: accepted/refused records, exporter sent/failed, queue depth, retry failures, dropped logs và tuổi bản ghi lâu nhất đang chờ. Tên metric chính xác phụ thuộc Collector version/distribution.

## 17. Hot, warm, cold và archive: cách tính tổng thời gian

Một chiến lược nhiều tầng có thể như sau (**minh họa**, không phải số bắt buộc):

~~~text
Ngày 0           Ngày 7          Ngày 30          Ngày 90
  │                │                │                │
  ├── HOT ─────────┤                │                │
  │                └── WARM ────────┤                │
  │                                 └── COLD ────────┤
  │                                                  └── DELETE
~~~

**Tổng retention = 90 ngày**, không phải `7 + 30 + 90 = 127`, vì các mốc là **đến ngày**. Nếu chính sách lại ghi “hot 7 ngày, warm thêm 23 ngày, cold thêm 60 ngày”, kết quả cũng là 90 nhưng cách diễn đạt khác; phải phân biệt các mốc với duration của từng giai đoạn.

**Trade-offs:**

| Tier | Lợi ích | Chi phí/giới hạn |
| --- | --- | --- |
| Hot | Truy vấn nhanh, hỗ trợ incident đang diễn ra | Storage/index thường đắt hơn |
| Warm | Cân bằng chi phí và truy vấn hậu kiểm | Query chậm hơn, hạn chế tài nguyên |
| Cold | Giữ dữ liệu ít truy cập với chi phí thấp hơn trong một số hệ thống | Có thể cần restore/truy vấn chậm |
| Archive/object | Lưu theo chính sách và truy xuất có kiểm soát | Search không trực tiếp hoặc cần khôi phục dữ liệu |
| Delete | Giảm rủi ro và chi phí sau khi hết mục đích | Cần xác nhận nhiều bản sao và xử lý hold |

**Không tự coi WARM/COLD là quyền lưu lâu hơn**. Dữ liệu phải được xóa khi hết thời hạn tổng được phép, trừ ngoại lệ hợp lệ được quản trị đúng.

## 18. Backend: retention của index, stream, partition và object

Trong kho log tập trung, retention có thể dùng lifecycle policy theo index/data stream/partition/object.

Ví dụ các cơ chế thường gặp:

- **Elasticsearch Index Lifecycle Management (ILM):** có thể chuyển lifecycle phases và delete indices/data stream backing indices theo chính sách; mốc tuổi/rollover phải được kiểm tra trên chính cấu hình index.
- **OpenSearch Index State Management (ISM):** các states/transitions/actions có thể quản lý rollover/delete theo điều kiện; cần xác minh policy gắn đúng index.
- **Grafana Loki:** có cơ chế retention và compactor theo kiểu lưu trữ/index schema; chỉ cấu hình application label hoặc query window **không tự** tạo retention backend.
- **Object storage:** thường có lifecycle rules để xóa object/versions hoặc chuyển storage class; versioning, replication, object lock và legal hold có thể ngăn xóa ngay.
- **Database partition:** drop partition theo ngày có thể nhanh hơn xóa hàng triệu rows, nhưng chỉ chính xác nếu partition boundary tương thích với retention contract.

**Cảnh báo:** Delete index cho một ngày có thể xóa cả event còn trong retention nếu cùng index chứa các timestamps khác nhau hoặc lifecycle dựa vào rollover time. Không dùng `index age` thay cho `event age` mà không có kiểm chứng.

Một backend có thể “không còn query thấy” do index đóng, đổi tier, quyền hạn hoặc lỗi query; điều đó không tương đương dữ liệu đã được xóa.

## 19. Tính dung lượng retention và chi phí

Cần dự toán từ dữ liệu đo được:

~~~text
rawBytesPerDay = eventsPerSecond × averageRawBytesPerEvent × 86400
storedBytesPerDay ≈ rawBytesPerDay × storageMultiplier
hotBytes ≈ storedBytesPerDay × hotDays
totalBytes ≈ sum(bytes in all active tiers + copies/backups as applicable)
~~~

`storageMultiplier` ở đây là **hệ số thực nghiệm** gồm nén, index, metadata, replicas và backend-specific overhead; nó có thể lớn hơn hoặc nhỏ hơn 1, **không phải một hằng số chung**.

Ví dụ giả lập:

- 100 events/giây × 600 bytes/event ≈ **5,18 GB raw/ngày** theo số thập phân.
- Nếu sau nén/index/replica đo được 4 GB/ngày trong tier hot, giữ 7 ngày cần khoảng 28 GB **dữ liệu hot bình quân**, chưa tính peak traffic, watermark, shard/headroom, snapshot và buffer.
- Giữ thêm warm/cold cần cộng riêng theo dung lượng đo ở các tier tương ứng, không nhân nguyên hot size cho toàn bộ thời gian.
- Nếu tốc độ cao tăng gấp ba theo mùa, size cap phải xét peak chứ không dùng trung bình lâu dài làm bảo đảm.

Công thức chi phí còn cần query load, ingest fees, network egress, cross-region replication và giá storage class. **Không giảm retention audit bắt buộc chỉ vì chi phí bất ngờ**; trước hết giảm raw payload, sampling diagnostics, cân nhắc tier hoặc điều chỉnh quy trình phát log theo chính sách đã được duyệt.

## 20. Legal hold: ngoại lệ bảo toàn và quyền riêng tư

**Legal hold/incident hold** yêu cầu tạm ngưng xóa một tập dữ liệu cụ thể vì điều tra, tranh chấp, yêu cầu bảo toàn hoặc quy trình áp dụng. Không phải mọi log đều được tự động giữ vô hạn.

Thiết kế cần:

1. Phạm vi rõ: event IDs, actor/resource refs được phép, tenant, thời gian, index/object, loại log.
2. Người phê duyệt và căn cứ nghiệp vụ/pháp lý; lưu dấu yêu cầu/bỏ hold.
3. Cơ chế thực thi tại **kho log và bản sao liên quan**, không chỉ một danh sách tên file trong app.
4. Quyền tách biệt: người quản trị app thường không nên tự xóa chứng cứ được hold.
5. Ngày rà soát và điều kiện gỡ hold.
6. Sau khi hold được gỡ, tính lại/xử lý retention theo policy, tránh tự động giữ vô hạn.
7. Tuân thủ nguyên tắc giảm thiểu dữ liệu và giới hạn mục đích; giữ thông tin không cần thiết có thể làm tăng rủi ro.

Một **WORM/object lock/immutable storage** có thể hỗ trợ bảo toàn nhưng có thể gây xung đột với yêu cầu xóa dữ liệu. Phải chọn chính sách theo nghĩa vụ thực tế và khả năng của storage, có kiểm soát và tư vấn phù hợp.

Ví dụ Java phần 11 chỉ dùng `Set<String> HOLDS` để minh họa sự ưu tiên của hold trước khi xóa. **Đó không phải** một workflow legal hold đạt yêu cầu trong tổ chức.

## 21. Xóa dữ liệu: “không tìm thấy” khác “đã xóa toàn bộ”

Khi đến ngày xóa:

- Một index bị delete có thể không còn query được, nhưng snapshot/backup của index vẫn tồn tại.
- Một file bị unlink có thể còn dữ liệu trên bộ lưu trữ/snapshot hoặc trong backup; cơ chế xóa byte vật lý phụ thuộc filesystem/hardware.
- Object storage có versioning, replica và lifecycle; xóa phiên bản hiện hành không nhất thiết xóa mọi version.
- Collector queue, dead-letter/quarantine, SIEM export và downloaded CSV có thể là các bản sao khác.
- Cache/truy vấn được lưu hoặc dữ liệu trong memory có vòng đời khác.
- Legal hold có thể ngăn xóa đúng hạn; hệ thống phải ghi nhận lý do và review.

**Không chứng nhận secure erasure chỉ bằng `Files.delete(path)`.** Xóa logic, xóa version, crypto-erasure và hủy vật lý là những cơ chế khác nhau; chọn theo bảo mật, compliance và công nghệ.

Một quy trình xóa tốt có các trạng thái:

~~~text
RETENTION_EXPIRED
   → HOLD_CHECKED
   → DELETE_REQUESTED
   → DELETE_ACCEPTED
   → DELETE_VERIFIED (theo API/hợp đồng từng storage)
   → RECONCILED / EXCEPTION_REVIEW
~~~

**Bằng chứng verification** có thể là index không còn, object versions bị xóa theo contract, snapshot lifecycle đã qua hoặc số bản ghi vượt tuổi giảm về mức cho phép. Nó chưa chắc chứng minh dữ liệu đã bị hủy vật lý trên mọi thiết bị.

## 22. Thiết kế nhiều lớp dữ liệu cá nhân và bảo mật

Retention dài làm tăng **bề mặt rủi ro**: càng nhiều log, càng nhiều người được quyền xem, càng nhiều nơi phải bảo vệ khỏi truy cập sai hoặc rò rỉ.

Không nên log:

- Password, OTP, bearer/refresh token, API keys, session cookies, private keys.
- PAN/card data hoặc tài liệu nhạy cảm nếu không có mục đích/ủy quyền phù hợp.
- Full HTTP request/response body, query string chứa PII, raw DB bind values.
- Exception message/stack trace có thể chứa URL có token hoặc thông tin người dùng.
- MDC/ThreadContext hoặc `toString()` của DTO chưa được xét an toàn.

**Chọn retention không thay thế data minimization.** Nếu một bản ghi chứa secret thật, giữ 24 giờ vẫn có thể gây hại nghiêm trọng. Bước đầu luôn là không thu dữ liệu không cần thiết, allowlist fields, redaction an toàn và kiểm thử synthetic sentinels.

Khi làm thống kê dài hạn, cân nhắc **aggregate metrics** hoặc summary không chứa định danh thay vì giữ chi tiết request-level logs. Dữ liệu đã pseudonymized vẫn có khả năng liên kết và có thể thuộc phạm vi dữ liệu cá nhân.

Cần có phân quyền RBAC, tenant isolation, TLS/mTLS, encryption at rest, audit truy cập log và retention cho những bản export do người dùng tạo.

## 23. Policy-as-code: viết hợp đồng tách khỏi cấu hình vendor

Một chính sách **trừu tượng** có thể được duy trì như YAML để các đội cùng review:

~~~yaml
version: 1
purpose: "example-retention-policy"
timeBasis: "event_timestamp_utc"
classes:
  diagnostics:
    retainFor: "P3D"
    accessRoles: ["dev-oncall", "sre"]
  application:
    retainFor: "P14D"
    accessRoles: ["sre"]
  security:
    retainFor: "P90D"
    accessRoles: ["security"]
  audit:
    retainFor: "requires-approved-schedule"
    accessRoles: ["audit-reviewer"]
exceptions:
  legalHold: "approved-case-specific"
controls:
  dryRunBeforeDelete: true
  alertOnDeleteFailure: true
~~~

**Đây không phải YAML cấu hình trực tiếp của Logback, Log4j 2, Kubernetes, Collector, Loki hay Elasticsearch.** Nó là một ví dụ biểu diễn intent ở mức tổ chức; muốn áp dụng phải **dịch thành lifecycle policies cụ thể**, kiểm tra khả năng từng backend và tạo automated drift checks.

Một policy đáng review nên chứa:

- Owner và approver, schema version, ngày có hiệu lực.
- Data classes và mục đích, cơ sở lưu giữ đã được phê duyệt.
- Time basis, tier transitions và total retention.
- Regions/tenants, access control và encryption.
- Hold/exception approval, quy trình purge và verification.
- Metrics, alert threshold, rollback và change history.
- Mapping từ source logs tới index/stream/bucket policies.

Tránh để một config Logback thay đổi âm thầm mà backend lifecycle vẫn giữ giá trị cũ nhiều tháng.

## 24. Kiểm thử retention: biên thời gian và lỗi vận hành

| Test case | Dữ liệu/thao tác | Kỳ vọng |
| --- | --- | --- |
| Ngày vừa quá hạn | File/event trước cutoff | Đủ điều kiện xóa theo time basis |
| Ngày đúng cutoff | Event trúng boundary | Giữ/xóa theo điều khoản inclusive được định nghĩa |
| Ngày mới | Event sau cutoff | Được giữ |
| Invalid filename/date | File không theo schema | Không xóa mù; có metric/quarantine |
| Legal hold | File quá hạn nhưng hold còn hiệu lực | Không xóa; có lý do/bằng chứng |
| Bỏ hold | Hold được gỡ hợp lệ | Đánh giá lại lifecycle theo policy |
| File symlink | Link trỏ nơi khác | Cleanup không vượt phạm vi được phê duyệt |
| App file đang mở | Rollover/rotation cùng lúc | Không xóa active file hoặc tạo lỗi dữ liệu |
| Backend index rollover | Index nhiều ngày event | Không xóa event còn trong retention |
| Clock skew | JVM/Collector lệch ngày | Không tính tuổi sai theo mốc ngầm định |
| DST/timezone | Qua ngày địa phương/UTC | Boundary nhất quán theo time basis |
| Disk cap | Volume vượt ngưỡng trước TTL | Alert/buffer/size-policy đúng, không mất audit bắt buộc |
| Collector outage | Agent queue tồn nhiều ngày | Không xóa local khi chưa ship theo contract |
| Backup snapshot | Index đã bị xóa | Snapshot cũng theo lifecycle riêng và hold |
| Restore archive | Bản ghi cũ được restore | Không làm retention “bắt đầu lại” trái policy |
| Delete API fail | Storage từ chối cleanup | Retry có kiểm soát, alert và audit |
| Large scale | Nhiều triệu events | Query/lifecycle không làm nghẽn service |
| Multi-tenant | Policies khác theo tenant | Không giữ nhầm hoặc xóa nhầm tenant |

**Negative assertion:** “Không thấy record cũ” phải đi kèm **positive assertion** rằng query/backend vẫn hoạt động và một record mới phù hợp còn tồn tại. Nếu search toàn bộ lỗi 500 hoặc index bị drop nhầm, test có thể PASS giả khi chỉ assert không tìm thấy record quá hạn.

**Test production policy tại staging hoặc sandbox**, không chạy destructive cleanup trên dữ liệu thật chỉ để thử một regex/path.

## 25. Observability cho chính retention process

Thiết lập telemetry để phát hiện retention không hoạt động hoặc hoạt động sai:

- **Oldest searchable event age** theo class/tenant/tier.
- **Count/bytes over retention threshold** và tuổi bản ghi quá hạn lâu nhất.
- **Deletion candidates**, dry-run vs actual deleted count.
- **Delete failures**, retry backlog và thời gian hoàn tất xóa.
- **Held records** theo case/expiry/review status, không log nội dung nhạy cảm.
- **Index/partition count** theo tier và policy owner.
- **Object versions/snapshot age** so với chính sách.
- **Ingest/export backlog**, để local cleanup không chạy vượt shipper.
- **Storage utilization**, disk watermark, predicted fill date.
- **Access/export activity** và query từ các vai trò nhạy cảm.
- **Policy drift** giữa cấu hình mong muốn và giá trị đang chạy.
- **Cost per class/tier**, volume theo service, thay đổi bất thường sau deploy.

Chỉ đo “size giảm sau delete” **không đủ**: có thể một index bị drop nhầm hoặc policy xóa sớm data còn cần. Cần cả metrics về dữ liệu **quá tuổi** và dữ liệu **chưa đủ tuổi nhưng bị xóa** trong test/đối chiếu.

Canary retention test có thể tạo event giả định danh riêng, đợi hết hạn ở sandbox, sau đó xác nhận lifecycle kết thúc đúng. Không dùng canary chứa token thật hoặc dữ liệu người dùng.

## 26. Khi thay đổi retention đang chạy

Giả sử muốn chuyển INFO retention từ 30 xuống 14 ngày. Đây có thể làm xóa **ngay lập tức** nhiều index/file đang nằm trong khoảng 15–30 ngày nếu policy áp dụng hồi tố.

Quy trình thay đổi an toàn:

1. Xác nhận lý do, owner, compliance/privacy và scope.
2. Đo số record/bytes sẽ bị xóa, danh sách index/object/version bị ảnh hưởng.
3. Kiểm tra active incident, legal hold, audit và các ngoại lệ khác.
4. Chạy dry-run/preview trên config và dữ liệu test; review kết quả.
5. Lên lịch thay đổi có giám sát, có thể chia batch để tránh áp lực I/O.
6. Giới hạn quyền sửa policy và xác nhận approvals.
7. Áp dụng, theo dõi deletion lag, rejection, errors, query behavior.
8. Xác minh không mất data còn trong thời hạn và data quá hạn được xử lý.
9. Lưu audit về thay đổi policy **không chứa bí mật**, độc lập với dữ liệu bị xóa.
10. Đánh giá bản sao ở backup/exports và quy trình quyền riêng tư.

**Không coi “rollback retention” là khôi phục được mọi dữ liệu đã bị xóa.** Một khi index/object đã mất và không có bản sao hợp lệ, tăng lại số ngày không tự hồi sinh dữ liệu.

Khi tăng retention, phải xem lại cơ sở mục đích, privacy, storage cost, index capacity và hợp đồng. “Tăng cho chắc” không mặc nhiên được phép.

## 27. Tình huống: điều tra sự cố chậm phát hiện

Giả sử một bug bắt đầu xuất hiện sau deploy và chỉ được phát hiện sau 10 ngày.

- DEBUG chỉ giữ 3 ngày: các chi tiết code cũ có thể đã mất.
- INFO/ERROR giữ 14–30 ngày: còn bằng chứng mức nghiệp vụ hoặc error code.
- Metrics aggregate và traces có thể có retention khác, giúp nhận diện thời gian lỗi tăng.
- Audit event cần thiết có lịch bảo quản riêng; không nên trông chờ DEBUG làm lịch sử đáng kiểm chứng.
- Nếu thời gian phát hiện incident thường vượt INFO retention, cần xem lại SLO/mục đích: kéo dài log **cần thiết**, giữ summaries lâu hơn hoặc tăng phát hiện sớm.
- Không thể giải quyết bằng việc “lấy lại log từ JVM” nếu tất cả các bản sao đã được cleanup hợp lệ.

Bài học là retention phải liên quan **thời gian thực tế cần quay lại để điều tra**, không chỉ số ngày dễ nhớ.

## 28. Tình huống: log quá nhiều, chi phí vượt ngân sách

Một đội phát hiện DEBUG level bị bật liên tục và disk/index tăng nhanh.

Giải pháp theo thứ tự:

1. Giảm **event volume và dữ liệu thừa tại nguồn**: tắt DEBUG không cần, sampling chẩn đoán có kiểm soát, tránh dump raw payload.
2. Đặt log event schema gọn, bỏ các trường không cần.
3. Kiểm soát local file size/rotation để host không đầy, nhưng xem xét shipper/ACK và data loss.
4. Dùng tiering/nén/index strategy phù hợp backend.
5. Xem lại hot query needs trước khi giảm **total retention**.
6. Đánh giá các nhóm security/audit riêng, không dùng size cap để âm thầm xóa chúng.
7. Tạo cảnh báo dự báo đầy dung lượng và owner duyệt policy mới.

**Sai lầm thường gặp:** giảm mọi index còn 3 ngày để tiết kiệm chi phí, rồi sau 4 ngày phát hiện incident cần xem 2 tuần dữ liệu. Cần thiết kế retention dựa trên mục đích và kinh nghiệm điều tra.

## 29. Anti-patterns khi chọn retention

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| “Giữ tất cả mãi mãi cho chắc” | Tăng PII, chi phí và phạm vi truy cập | Chọn duration theo mục đích và nghĩa vụ |
| “ERROR phải giữ vô hạn” | Không phải mọi lỗi đều cần retention lâu | Phân lớp theo mục đích, hạn chế dữ liệu |
| “DEBUG giữ dài bằng audit” | Log ồn, nhạy cảm, tốn storage | Tách kênh, giảm retention chẩn đoán |
| Dựa vào `FileHandler.count=5` rồi gọi là 5 ngày | Count là số file, không phải thời gian | Time-based lifecycle ở tầng phù hợp |
| Chỉ cấu hình Logback maxHistory | Backend/backup vẫn giữ lâu | Inventory toàn bộ bản sao |
| Dùng size cap cho audit bắt buộc | Có thể xóa sớm, mất chứng cứ | Durable audit store/policy riêng |
| Tưởng `kubectl logs` là retention tập trung | Log trên node/pod có thể mất | Central aggregation có lifecycle |
| Xóa theo `lastModified` mà không xét file được copy | Dữ liệu cũ giữ lại sai thời hạn | Time basis thống nhất |
| Thử delete regex trực tiếp trên `/var/log` | Xóa nhầm file khác, mất dịch vụ | Scope folder, dry-run, allowlist |
| Không xét legal hold | Xóa chứng cứ cần bảo toàn | Hold workflow và exemption engine |
| Xem “search không thấy” là đã hủy byte | Snapshot/backup/export vẫn có | Xác minh theo từng storage |
| Đặt TTL ngắn hơn backlog shipping | Mất log trước khi ingest | Buffer/backpressure và alert |
| Không tách tenants/regions | Xóa sai hoặc lộ data | Policy theo scope, RBAC |
| Dùng retention để xử lý secret đã lộ | Secret vẫn có thể bị khai thác | Incident response và credential rotation |
| Không test boundary ngày/timezone | Xóa sớm/muộn | UTC, fixed clock, cutoff tests |
| Không theo dõi cleanup job | Dữ liệu quá hạn tích tụ im lặng | Metrics/alert/delete reconciliation |
| Tự áp số ngày “chuẩn luật” từ blog | Có thể không đúng lĩnh vực/khu vực | Review pháp lý/contract thực sự áp dụng |

## 30. Checklist trước khi chốt chiến lược retention

1. Đã có bảng inventory mọi nguồn log Java, container, middleware và export chưa?
2. Từng class có **mục đích lưu, owner và người được truy cập** rõ chưa?
3. Retention duration có căn cứ nghiệp vụ/rủi ro/nghĩa vụ chứ không chỉ theo cảm tính không?
4. Có phân biệt DEBUG, operational, security và audit events không?
5. Có định nghĩa **event time vs ingest time vs index rollover time** không?
6. Có hiểu retention là total duration và tier boundaries, tránh cộng sai ngày không?
7. Có xem xét sizing theo event rate, peak, compression, index/replicas, query costs và backpressure không?
8. Local appender/`FileHandler`/kubelet rotation có được hiểu đúng, không bị gọi nhầm là central retention không?
9. Có tài liệu mapping intent → backend lifecycle config và kiểm tra drift không?
10. Agent/Collector queue và offline backlog có được theo dõi để tránh local delete quá sớm không?
11. Có policy handling cho secrets, personal data, redaction và access/export không?
12. Có quy trình legal hold, review và release hợp lệ không?
13. Có kế hoạch xóa ở index, object versions, snapshot, backup, exports và quarantine không?
14. Có test boundary, invalid file, symlink, live file, rollover, legal hold và backend delete error không?
15. Có dry-run và phê duyệt trước thay đổi có thể xóa hàng loạt dữ liệu không?
16. Có metrics/alert về oldest record age, deletion failures, queue lag và storage near capacity không?
17. Có kịch bản điều tra sau 2–4 tuần để xác minh retention thực sự hỗ trợ incident response không?
18. Có cách chứng minh record chưa đủ tuổi **không bị xóa nhầm** không?
19. Khi policy thay đổi, có đánh giá tác động hồi tố và rollback bất khả thi không?
20. Có phân biệt tuyên bố “không query được” với “đã xóa theo hợp đồng storage” không?

## 31. Câu hỏi tự kiểm tra

1. Vì sao `maxHistory=7` của Logback không chứng minh dữ liệu đã biến mất khỏi Elasticsearch sau 7 ngày?
2. `FileHandler(limit,count)` của JUL dựa trên ngày hay số file/kích thước?
3. Hot 7 ngày, warm đến ngày 30, cold đến ngày 90: tổng retention bao lâu?
4. Nếu local file TTL 1 ngày nhưng Collector có thể outage 3 ngày, rủi ro chính là gì?
5. Với Log4j 2, `IfLastModified` phản ánh event time hay file modification time?
6. Vì sao một archive được copy hôm nay có thể khiến retention dựa vào mtime bị sai?
7. Cần làm gì trước khi thực thi `Delete` action trên thư mục chứa nhiều loại file?
8. `testMode=true` của Log4j 2 Delete có xóa file không?
9. Khi audit event đang legal hold, có được tự xóa vì quá retention thông thường không?
10. Việc xóa index có đảm bảo snapshot và bản export trước đó đã bị xóa không?
11. Vì sao retention 3 ngày không tự hợp pháp hóa việc ghi password?
12. Một log quá hạn không tìm thấy trong dashboard có chứng minh đã secure-erase mọi bản sao không?
13. Vì sao timestamp của index rollover không thể thay thế event timestamp trong mọi policy?
14. Bài Java 17 xử lý file đúng ngày cutoff như thế nào?
15. Trong demo, tại sao file `audit-2026-01-01.log` vẫn được giữ dù rất cũ?
16. Nếu một app có log rate tăng mười lần, retention theo count file thay đổi ra sao?
17. Vì sao nên đo `oldest searchable event age` và `delete failures` thay vì chỉ đo disk usage?
18. Khi giảm retention từ 30 xuống 14 ngày, tăng lại thành 30 có tự khôi phục dữ liệu đã xóa không?
19. Backend retention có thay thế việc cấu hình kubelet `containerLogMaxSize` không?
20. Những thông tin nào phải được phê duyệt trước khi tăng retention audit/security logs?

**Gợi ý:** (1) khác storage/sink; (2) file count và byte limit; (3) 90 ngày; (4) mất log chưa được ship; (5) file mtime; (6) mtime mới không phải event age; (7) giới hạn basePath/pattern, dry-run, review; (8) không; (9) hold được quản lý hợp lệ phải được xét trước cleanup; (10) không; (11) bí mật không nên log dù ngắn; (12) không; (13) một index có nhiều event ages; (14) giữ vì chỉ xóa ngày trước cutoff; (15) thuộc tập hold; (16) quay vòng nhanh hơn, thời gian lưu thực tế ngắn; (17) cần phát hiện retention drift; (18) không; (19) không, hai tầng khác; (20) mục đích, luật/contract, privacy, quyền và capacity.

## 32. Tài liệu tham khảo chính thức

- [Java SE 17 — java.util.logging.FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): `limit`, `count`, `pattern`, `append` và vòng xoay file.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): thao tác file và cleanup trong ví dụ.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): toán học ngày, cutoff và date parsing.
- [Logback — Rolling File Appenders](https://logback.qos.ch/manual/appenders-rolling.html): `TimeBasedRollingPolicy`, `maxHistory`, `totalSizeCap`, `cleanHistoryOnStart`.
- [Apache Log4j 2 — Rolling File Appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): `Delete` action, `testMode`, `IfFileName`, `IfLastModified`.
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/): node-level rotation, `containerLogMaxSize`/`containerLogMaxFiles` và cluster-level logging.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): receiver, processor, exporter, pipelines và storage-related extension khi có.
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): event timestamp, observed timestamp, severity và resource attributes.
- [Elastic — Index Lifecycle Management](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-lifecycle-management.html): lifecycle phases và delete policy trong Elasticsearch.
- [OpenSearch — Index State Management](https://docs.opensearch.org/latest/im-plugin/ism/index/): state-based rollover/delete trên OpenSearch.
- [Grafana Loki — Retention](https://grafana.com/docs/loki/latest/operations/storage/retention/): retention, compactor và giới hạn theo backend/schema.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): giảm thiểu dữ liệu, bảo vệ, truy cập và lưu trữ log.
