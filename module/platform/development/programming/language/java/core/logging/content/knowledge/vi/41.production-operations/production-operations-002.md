# Theo dõi dung lượng log trong Java Core Logging — Vận hành production

## 1. Vì sao phải theo dõi dung lượng log?

**Theo dõi dung lượng log** là quan sát liên tục log đang chiếm bao nhiêu tài nguyên, tăng nhanh đến mức nào, khả năng lưu thêm còn bao nhiêu và liệu hệ thống có đang mất log, vượt quota hoặc sắp bị gián đoạn vì hết tài nguyên lưu trữ hay không. Đây không chỉ là câu hỏi “file `app.log` có lớn không?”, mà là bài toán **nhiều tầng**: Java application → appender/console → filesystem hoặc container runtime → shipper/collector → backend tìm kiếm → archive/backup.

Khi log tăng ngoài dự kiến, một sự cố ứng dụng có thể kéo theo một sự cố hạ tầng:

- Vòng lặp exception ghi stack trace liên tục làm đầy ổ; không còn chỗ để ghi log mới hoặc file tạm.
- Disk pressure khiến database, process khác trên cùng mount hoặc node bị ảnh hưởng; trong Kubernetes có thể dẫn tới **Pod eviction**.
- File logger ghi thất bại nhưng ứng dụng vẫn chạy; lỗi tiếp theo không còn bằng chứng để điều tra.
- Collector lag làm queue/buffer lớn lên, retry làm tăng traffic và có thể khiến bản ghi đến backend chậm hoặc mất theo chính sách drop.
- Index/backend hết quota hoặc tăng phí quá nhanh dù **ổ đĩa cục bộ** của application vẫn còn trống.
- Retention/rotation bị cấu hình sai: archive không được dọn, hoặc bị xóa trước thời hạn audit cần giữ.

**Mục tiêu:** biết tình trạng hiện tại, dự báo trước khi cạn, xác định thành phần tạo log, phát cảnh báo có đủ thời gian xử lý và khống chế tăng trưởng **mà không vô tình xóa chứng cứ quan trọng**.

### Ví dụ tình huống

~~~text
09:00   log directory = 5 GiB, filesystem usable = 20 GiB
09:05   log directory = 7 GiB, filesystem usable = 18 GiB
09:10   log directory = 9 GiB, filesystem usable = 16 GiB
...
09:50   log directory có thể tới 25 GiB nếu tốc độ giữ nguyên
~~~

Trong khoảng trên, log tăng khoảng **2 GiB / 5 phút = 0,4 GiB/phút**. Nếu các workload khác không đổi và giữ tốc độ đó, 16 GiB còn trống chỉ cho khoảng 40 phút đến mốc 0 GiB lý thuyết; nhưng thực tế phải trừ **dung lượng dự phòng**, không chờ đến 0 mới hành động. Đây là phép ước lượng xu hướng, không phải cam kết của filesystem.

## 2. Phải đo nhiều loại dung lượng, không chỉ kích thước một file

| Đại lượng | Ý nghĩa | Nguồn đo phù hợp |
| --- | --- | --- |
| `filesystem_total_bytes` | Tổng dung lượng của filesystem chứa log | OS, host exporter, Java `FileStore` |
| `filesystem_usable_bytes` | Số byte application/non-root còn **có thể dùng** tại thời điểm đo | OS hoặc `FileStore.getUsableSpace()` |
| `filesystem_unallocated_bytes` | Số byte chưa cấp phát của filesystem | OS/Java `getUnallocatedSpace()`, khác `usable` |
| `filesystem_used_percent` | Mức dùng của toàn mount, không riêng log | Host filesystem metrics |
| `log_directory_bytes` | Tổng kích thước file log active + archives trong thư mục đã định nghĩa | Agent chuyên dụng / bounded file inventory |
| `active_log_file_bytes` | Kích thước file đang ghi | Filesystem/file appender metrics |
| `archived_log_bytes` | Dung lượng file đã rotate và nén | File inventory / storage lifecycle |
| `log_bytes_written_total` | Số byte log đã phát ra theo thời gian | Appender/agent instrumentation nếu thực sự có |
| `log_events_written_total` | Số event ghi thành công | Counter instrumented tại sink, nếu có |
| `log_events_dropped_total` | Số event đã bỏ do queue/filter/backpressure | Logger, appender, collector tùy hỗ trợ |
| `collector_queue_bytes` / `collector_queue_size` | Backlog chờ chuyển tiếp | Collector/exporter/shipper metrics |
| `backend_ingested_bytes` | Dữ liệu log đã nhận ở backend/index | Backend billing/ingest metrics |
| `backend_stored_bytes` | Kích thước lưu trữ sau index/compression/replication | Backend/index/storage metrics |
| `inode_free` | Số inode/file entries còn trống (trên filesystem có inode) | Linux host metrics/`df -i` |
| `ephemeral_storage_used` | Tài nguyên tạm của Pod/container gồm logs, writable layers, emptyDir | Kubelet/CRI metrics |
| `retention_oldest_age` | Tuổi archive/bản ghi cũ nhất đang tồn tại | Inventory/lifecycle job |

**Ba con số thường bị nhầm:**

1. **Bytes log ghi tại ứng dụng** không bằng bytes file đang chiếm: output còn có timestamp, JSON envelope, stack trace, và khi rotate có thể nén. Appender có thể buffer.
2. **Kích thước file trong thư mục** không bằng toàn bộ dung lượng mount đang mất: mount còn có image layers, DB, temp, journal và cả **file đã bị unlink nhưng process vẫn mở** trên Unix.
3. **Dung lượng đã ingest hoặc được tính phí** không bằng dung lượng lưu trên disk: backend có thể nén, tạo index, replica và lưu snapshot; cần đo từng tầng theo chính sách của nền tảng.

Ví dụ một app chỉ có 2 GiB archives nhưng filesystem 95% đầy: nguyên nhân có thể là workload khác, file đã xóa còn mở, log container runtime ở vị trí khác, hoặc volume quota chứ không nhất thiết appender không rotate.

## 3. Hiểu khái niệm capacity, usable và quota

Trong Java SE 17, `java.nio.file.FileStore` cung cấp:

- `getTotalSpace()` — dung lượng được báo cáo của file store, theo byte.
- `getUnallocatedSpace()` — số byte chưa cấp phát trên file store.
- `getUsableSpace()` — số byte còn được phép sử dụng **bởi JVM hiện tại** theo khả năng hệ thống báo cáo.
- `isReadOnly()` — trạng thái chỉ đọc của file store.

Các kết quả này **là chỉ báo tại một thời điểm, không bảo đảm thao tác ghi sẽ thành công**. Hệ điều hành, quota, quyền, các writer song song, reserved blocks và khác biệt giữa mount/container có thể khiến số byte có thể ghi thực tế thay đổi ngay sau khi đọc.

~~~java
// Snippet Java 17: cần import java.nio.file.Files, Path, FileStore.
Path logDirectory = Path.of("logs").toAbsolutePath();
FileStore fileStore = Files.getFileStore(logDirectory);
long total = fileStore.getTotalSpace();
long usable = fileStore.getUsableSpace();
long unallocated = fileStore.getUnallocatedSpace();
~~~

Đây là **snippet**: đường dẫn phải tồn tại, có thể ném `IOException`/`SecurityException`; chương trình đầy đủ ở mục 7 có xử lý thử nghiệm tương ứng. Không lấy `unallocated` rồi mặc định mọi byte đó là writable của user ứng dụng.

### Giới hạn quan trọng của phép đo trong container

Nếu JVM nằm trong container, `FileStore` có thể đang đo một mount hiển thị qua overlay filesystem hoặc volume mount. Con số tổng/usable của mount **không nhất thiết phản ánh quota cgroup, ephemeral-storage limit của Pod hay quota riêng của storage backend**. Một Pod có thể bị evict vì vượt ephemeral storage limit trước khi số byte host mount trong JVM xuống thấp.

Vì vậy đo đồng thời từ **host/kubelet/container runtime**, **application file store** và **backend** khi mỗi tầng có quyền hạn riêng. Không dùng một metric từ JVM làm nguồn duy nhất cho mọi cảnh báo storage.

### Inode: còn byte nhưng vẫn có thể không tạo file

Ở các filesystem có inode, rất nhiều file log nhỏ có thể làm cạn inode dù vẫn còn dung lượng byte. Khi đó tạo file mới có thể thất bại. Trên Linux, `df -i` giúp xem inode; node-exporter có những metric filesystem file nodes nếu filesystem và collector hỗ trợ. Java `FileStore` không cung cấp API portable dành riêng cho inode count; cần lớp giám sát OS phù hợp.

## 4. Tốc độ sinh log và thời gian dự kiến cạn chỗ

**Dung lượng hiện tại** cho biết mức nguy hiểm lúc này; **tốc độ tăng** cho biết có bao nhiêu thời gian để khắc phục. Một hệ thống có 20% trống nhưng đang ghi 10 GiB/phút có thể nguy cấp hơn hệ thống chỉ còn 10% trống mà tăng rất chậm.

Các đại lượng nên đo:

- **`log_write_bytes_per_second`:** số byte mới của log trước/hoặc sau nén theo một định nghĩa nhất quán; không tự trộn hai hệ quy chiếu.
- **`log_events_per_second`:** log records/giây, theo service, level hoặc event type đã chuẩn hóa.
- **`log_directory_growth_bytes_per_second`:** chênh lệch kích thước thư mục qua thời gian; có thể âm khi rotation/cleanup.
- **`filesystem_usable_bytes`:** byte còn usable trên mount, phản ánh cả workload khác.
- **`time_to_exhaustion`:** thời gian ước tính tới ngưỡng dự phòng theo tốc độ tiêu thụ ròng quan sát được.

Công thức gần đúng:

\[
r_{\text{log}} = \frac{\Delta \text{bytes log}}{\Delta t}
\]

\[
T_{\text{reserve}} \approx
\frac{\max(0, \text{usableBytes}-\text{reserveBytes})}
     {\text{netConsumptionBytesPerSecond}}
\]

Công thức thứ hai **chỉ dùng khi tốc độ tiêu thụ ròng dương và có ý nghĩa**. Nếu tốc độ bằng 0/âm, không suy rằng còn “vô hạn” một cách chắc chắn; có thể đang có rotation, load thấp nhất thời, missing metrics hoặc burst chưa xuất hiện. Dự báo nên được làm mượt đủ lâu, bổ sung peak rate, và cảnh báo theo mức free byte tuyệt đối.

**Phân biệt hai tốc độ:**

1. `r_log` đo log mới được ghi, hữu ích để phát hiện một service đột ngột spam lỗi.
2. `r_disk` đo tốc độ **filesystem usable giảm**, gồm log **và các writer khác**, đã tính ảnh hưởng cleanup; hữu ích hơn để dự báo node disk exhaustion nhưng không cho biết nguyên nhân.

Ví dụ:

~~~text
Usable = 5 GiB; reserve = 1 GiB; tốc độ tiêu thụ ròng = 128 MiB/phút
Time to reserve ≈ (4096 MiB) / (128 MiB/phút) = 32 phút.
~~~

Nếu có spike 512 MiB/phút, thời gian giảm còn 8 phút. Không lấy một điểm 5 phút rồi tin tuyệt đối; phải hiển thị dải biến động và cảnh báo thích hợp.

### Theo dõi xu hướng theo nhiều khoảng

- 1–5 phút: phát hiện burst/nguy cơ sắp hết nhanh, nhưng nhiễu khi rotate.
- 30–60 phút: phát hiện tốc độ tăng ổn định, dự báo có độ tin cậy hơn.
- 1–7 ngày: theo dõi xu hướng kinh doanh, peak theo giờ/ngày, thay đổi sau release.
- Thời hạn retention: so sánh mức tăng và chính sách xóa để biết steady-state có khả thi không.

Theo dõi cả **đỉnh theo phiên triển khai hoặc lỗi production**, không chỉ trung bình ngày. Một incident error loop có thể sinh nhiều log hơn traffic bình thường hàng chục hoặc hàng trăm lần.

## 5. Dự toán dung lượng và ngân sách retention

Một ước lượng cơ bản:

\[
\text{raw bytes/ngày}
\approx \text{events/giây} \times \text{bytes/event} \times 86400
\]

~~~text
100 events/s × 800 bytes/event × 86,400 s
= 6,912,000,000 bytes/ngày ≈ 6.44 GiB/ngày
~~~

Nếu giữ 7 ngày ở cùng tốc độ, raw payload ≈ **45 GiB**, chưa tính compression, active file, archive metadata, index, replica, backup, headroom, hay số ngày có lưu lượng lớn hơn.

Các yếu tố làm lệch dự toán:

- Stack trace nhiều dòng, exception thường xuyên, message chứa object lớn.
- JSON log có metadata lặp lại và log injection escaping.
- Compression ratio khác nhau theo payload.
- Index overhead và số replica của backend.
- Log shipping replays/duplicates, ingest retry, retention policy khác nhau.
- Cách tính GB (10^9 bytes) và GiB (2^30 bytes), mức phí theo compressed hoặc uncompressed ingestion của nhà cung cấp.
- Thời gian hot vs cold storage, query cost, restore cost và retention per class.

**Không dùng một budget chung cho mọi log**: audit/security cần giữ theo chính sách đã phê duyệt; DEBUG vận hành có thể ngắn hơn. Nếu appender nguồn tự xóa khi đạt `totalSizeCap`, nó có thể xóa audit trước hạn nếu hai loại log trộn chung. Cần tách pipeline/retention theo classification.

## 6. Chống tăng dung lượng bằng rolling file, không chỉ bằng “giảm level”

### Logback Classic: size + time rolling

Ví dụ cấu hình `logback.xml` minh họa log **ứng dụng thông thường**, không phải policy audit/legal hold:

~~~xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>5GB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{ISO8601} [%thread] %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
~~~

Ý nghĩa cần hiểu theo tài liệu Logback:

1. `SizeAndTimeBasedRollingPolicy` tạo archive theo **ngày** (`%d`) và theo **index** (`%i`) khi file đạt `maxFileSize`; cả hai conversion tokens cần thiết trong kiểu policy này.
2. `maxFileSize=100MB` là ngưỡng kích hoạt rollover của file active trong chu kỳ, **không phải bảo đảm tổng log tối đa 100 MB**.
3. `maxHistory=7` với pattern hằng ngày nhằm giữ khoảng 7 giai đoạn archives theo quy tắc policy; không phải xóa một event đúng sau 7×24 giờ.
4. `totalSizeCap=5GB` giới hạn **tổng archives do policy quản lý**; **file active không phải phần của archives cap**. `maxHistory` được xét trước, `totalSizeCap` sau; cleanup có thể bất đồng bộ.
5. Khi app ghi nhanh trong burst, disk có thể vượt ngưỡng dự kiến trước khi rollover, cleanup hoặc compression hoàn thành. Không coi config là firewall tuyệt đối chống hết đĩa.
6. Mỗi `totalSizeCap` chỉ quản lý những archive thuộc policy tương ứng; các file khác, temp, Docker logs, shipper buffers và backups vẫn chiếm disk.
7. Nếu muốn giữ những loại log có nghĩa vụ lưu giữ lâu hơn, **không cho cùng policy xóa chúng trước hạn**. Audit nên có storage/retention độc lập và bảo toàn bằng chứng.

Nếu ứng dụng chỉ cần giới hạn tổng archive bytes theo chu kỳ thời gian, `TimeBasedRollingPolicy` với `maxHistory`/`totalSizeCap` có thể đủ; policy kết hợp size+time được dùng khi muốn giới hạn kích thước từng file. Cấu hình phải phù hợp phiên bản Logback thực dùng.

### Log4j 2 và các chính sách xóa

Log4j 2 có `RollingFile`, trigger dựa trên size/time và rollover strategy; có thể cấu hình `Delete` action với điều kiện như `IfLastModified`, `IfAccumulatedFileSize`. Đây là **công cụ quản lý archives**, không tự kiểm soát toàn bộ filesystem. Các điều kiện thứ tự sort, phạm vi `basePath`, file pattern và `testMode` phải được kiểm tra cẩn thận trước khi bật xóa trong production.

Ví dụ **các thành phần khái niệm**:

~~~text
RollingFile appender
  +-- SizeBasedTriggeringPolicy / TimeBasedTriggeringPolicy
  +-- rollover strategy
        +-- archived files
        +-- Delete action (basePath, IfFileName, IfLastModified...)
~~~

Khi thực thi cleanup, chỉ cho phép match file archive trong thư mục đã định nghĩa, không follow symlink không kiểm soát. Test dry-run/testMode nếu phiên bản và cấu hình hỗ trợ. Đặc biệt, đừng đặt một rule xóa rộng tới cùng directory chứa audit hoặc dữ liệu nghiệp vụ.

### Tránh hai bộ rotation cùng điều khiển một file

Trên Linux, ứng dụng có thể vừa dùng `RollingFileAppender` vừa bị `logrotate` của OS xoay cùng file. Hai cơ chế có thể tranh nhau rename/truncate và dẫn đến log mất/nhân bản, descriptor ghi vào inode cũ, sai timestamp hoặc unexpected disk growth. Chọn **một owner rotation** cho mỗi file hoặc thiết kế giao tiếp reopen rõ ràng.

`logrotate copytruncate` có thể có cửa sổ mất dòng vì file vẫn đang được ghi trong khi copy/truncate; chỉ dùng khi đã hiểu trade-off và không có cách reopen tốt hơn. Không coi logrotate thành cơ chế đảm bảo durability của audit.

## 7. Java 17 runnable: theo dõi filesystem và phân loại nguy cơ

Ví dụ sau sử dụng **chỉ JDK 17** để:

- Lấy `FileStore` ứng với một thư mục có thật và đọc tổng dung lượng/usable bytes.
- Phân loại bốn tình huống **giả lập**: bình thường, cảnh báo theo thời gian tới reserve, nguy cấp và chưa biết tốc độ tăng.
- Không xóa, truncate, tạo file hoặc sửa cấu hình logging.
- In output cố định cho các mẫu giả lập, kèm **hai boolean** kiểm tra khả năng đọc dung lượng của môi trường hiện tại.

**Lưu ý:** Đây là công cụ học, không phải exporter metrics hay cơ chế bảo vệ disk production. Một tiến trình khác có thể tiêu thụ dung lượng ngay sau khi kiểm tra; quota/inode/container limit có thể ngăn ghi dù phép đo JVM còn free bytes.

Tạo file **`LogCapacityDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class LogCapacityDemo {
    private static final long MIB = 1024L * 1024L;

    enum Risk {
        OK, WARNING, CRITICAL, UNKNOWN_RATE
    }

    static Risk assess(
            long totalBytes,
            long usableBytes,
            long netGrowthBytesPerMinute,
            long reserveBytes) {

        if (totalBytes <= 0
                || usableBytes < 0
                || usableBytes > totalBytes
                || netGrowthBytesPerMinute < 0
                || reserveBytes < 0
                || reserveBytes > totalBytes) {
            throw new IllegalArgumentException("invalid sample");
        }

        // Hết ngưỡng reserve phải ưu tiên cảnh báo khẩn cấp.
        if (usableBytes <= reserveBytes) {
            return Risk.CRITICAL;
        }

        // Không đủ bằng chứng để dự báo thời gian hết disk.
        if (netGrowthBytesPerMinute == 0) {
            return Risk.UNKNOWN_RATE;
        }

        long minutesToReserve =
                (usableBytes - reserveBytes) / netGrowthBytesPerMinute;
        if (minutesToReserve <= 15) {
            return Risk.CRITICAL;
        }
        if (minutesToReserve <= 60) {
            return Risk.WARNING;
        }
        return Risk.OK;
    }

    public static void main(String[] args) throws IOException {
        long reserve = 100 * MIB; // Chỉ là ngưỡng học tập.

        System.out.println("sample_ok="
                + assess(1000 * MIB, 800 * MIB, 10 * MIB, reserve));
        System.out.println("sample_warning="
                + assess(1000 * MIB, 500 * MIB, 10 * MIB, reserve));
        System.out.println("sample_critical="
                + assess(1000 * MIB, 130 * MIB, 10 * MIB, reserve));
        System.out.println("sample_no_growth="
                + assess(1000 * MIB, 500 * MIB, 0, reserve));

        // Chỉ quan sát file store của đường dẫn đã tồn tại.
        Path directory = Path.of(
                args.length == 0 ? "." : args[0])
                .toAbsolutePath().normalize();
        FileStore store = Files.getFileStore(directory);

        System.out.println("filesystem_total_positive="
                + (store.getTotalSpace() > 0));
        System.out.println("filesystem_usable_nonnegative="
                + (store.getUsableSpace() >= 0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LogCapacityDemo.java
java LogCapacityDemo .
~~~

**Stdout với filesystem thông thường báo cáo tổng dung lượng dương và usable không âm:**

~~~text
sample_ok=OK
sample_warning=WARNING
sample_critical=CRITICAL
sample_no_growth=UNKNOWN_RATE
filesystem_total_positive=true
filesystem_usable_nonnegative=true
~~~

Bốn dòng `sample_*` là **kết quả xác định cho dữ liệu giả lập** và đã được kiểm tra bằng JShell. Hai dòng filesystem phụ thuộc môi trường: `FileStore` có thể báo cáo tổng 0 trên mount đặc biệt, hoặc ném `IOException` với đường dẫn/permission không hợp lệ; không cam kết mọi máy đều in hai giá trị `true`. Lệnh trên chỉ đọc metadata của filesystem, không đọc nội dung file hay xóa dữ liệu.

Giải thích chương trình:

1. `MIB` định nghĩa 1 MiB = 1.048.576 bytes; không trộn MB/MiB khi tính toán.
2. `assess(...)` lấy một **tốc độ tiêu thụ ròng đã được đo ở hệ thống giám sát** (trong bài dùng dữ liệu giả); không tự suy `netGrowthBytesPerMinute` từ một lần `FileStore` read.
3. `reserveBytes` là ngân sách dự phòng. Trong mẫu, reserve = 100 MiB. Với usable = 800 MiB, còn 70 phút theo growth 10 MiB/phút → `OK`; với 500 MiB, 40 phút → `WARNING`; với 130 MiB, 3 phút → `CRITICAL`.
4. Nếu growth = 0 trong một mẫu, `UNKNOWN_RATE` không có nghĩa “không cần theo dõi”; có thể là metric thiếu, log tạm đứng yên hoặc rolling vừa cleanup.
5. `Files.getFileStore(directory)` đọc store tương ứng **đường dẫn đang tồn tại**. Để giám sát thư mục log thật, truyền đúng đường dẫn sau khi tạo/config deploy và kiểm tra mount có đúng như dự kiến. Nếu volume riêng, có thể khác filesystem của `"."`.
6. Code không dùng `Files.walk(...)` để quét hàng triệu file log. Việc đo `log_directory_bytes` thực tế cần inventory/bounded scan hoặc agent phù hợp, vì scan toàn bộ trên request thread có thể tiêu tốn CPU/I/O.
7. Cảnh báo production không nên do mỗi JVM tự chạy timer và in cảnh báo vào **chính file log sắp đầy**. Hãy export số liệu qua metrics/health endpoint hoặc OS exporter, để hệ thống quan sát tách khỏi filesystem bị lỗi.

**Lưu ý ranh giới:** logic phân loại trong demo dùng hai ngưỡng **15 và 60 phút chỉ để thực hành**; đội SRE phải chọn ngưỡng dựa trên tốc độ điều tra/khắc phục, peak burst, dự phòng và yêu cầu dịch vụ. Đừng copy thành SLO/hard requirement không có phê duyệt.

## 8. Prometheus và node-exporter: phát hiện dung lượng sắp cạn

Với Linux host có Prometheus node_exporter, một số metric thường gặp:

- `node_filesystem_size_bytes` — dung lượng filesystem.
- `node_filesystem_avail_bytes` — bytes có thể dùng bởi user không có quyền root.
- `node_filesystem_free_bytes` — byte trống của filesystem; không nhất thiết bằng `avail`.
- `node_filesystem_files` và `node_filesystem_files_free` — tổng/free inode hoặc file nodes, khi filesystem hỗ trợ.
- `node_filesystem_readonly` — trạng thái read-only của mount.

Ví dụ **PromQL** cho một mount **đã xác nhận chính là mount chứa log** (thay `/var/log` nếu log nằm ở mount khác):

~~~promql
100 * (
  node_filesystem_avail_bytes{mountpoint="/var/log"}
  /
  node_filesystem_size_bytes{mountpoint="/var/log"}
) < 15
~~~

Đây là minh họa điều kiện “usable dưới 15%”; không khẳng định 15% phù hợp mọi hệ thống. Nếu `/var/log` không là mount point riêng, selector trên có thể **không có series**; tìm đúng mount của directory (ví dụ `/` hoặc một volume khác) trước khi sử dụng. Với node_exporter, cần lọc pseudo-filesystem/bind mounts, label `instance`, device và `fstype` phù hợp để tránh alert nhiễu.

Dự báo giảm dung lượng qua nội suy tuyến tính:

~~~promql
predict_linear(
  node_filesystem_avail_bytes{mountpoint="/var/log"}[1h],
  4 * 3600
) < 0
~~~

Câu trên dự báo `avail_bytes` có thể xuống dưới 0 trong 4 giờ tới dựa trên 1 giờ vừa qua. Đây là **ước lượng tuyến tính nhạy với rotation và burst**, không phải lời tiên tri; nên kết hợp điều kiện free threshold, tối thiểu thời gian tồn tại (alert `for`), và cảnh báo về việc thiếu metric. Nếu giá trị `predict_linear` bị ảnh hưởng bởi rollover làm tăng free đột ngột, dự báo có thể sai lệch.

Ví dụ cảnh báo inode:

~~~promql
(
  node_filesystem_files_free{mountpoint="/var/log"}
  /
  node_filesystem_files{mountpoint="/var/log"}
) < 0.10
~~~

Áp dụng chỉ khi filesystem cung cấp metric file nodes hợp lệ và mẫu số dương. Cùng với `node_filesystem_avail_bytes`, nó phát hiện thêm dạng cạn inode không biểu hiện bằng số byte free.

### Đo tốc độ ghi log từ appender

Nếu ứng dụng **thực sự instrument counter** `app_log_written_bytes_total`, có thể truy vấn:

~~~promql
sum by (service) (
  rate(app_log_written_bytes_total[5m])
)
~~~

Tên metric trên **chỉ là ví dụ tùy chỉnh**, không phải một metric mặc định mà SLF4J/Logback/JUL tự sinh. Cần xác định counter đo bytes **trước encoder, sau encoder hay bytes đã ghi thành công**; số đo ở những stage khác nhau không thể cộng như nhau.

Để đo log nhanh/đột biến, nên có counter riêng cho `log_events_written_total`, `log_write_errors_total`, `log_events_dropped_total`, với labels **ít cardinality**: service, level, appender/sink, outcome. Không gắn requestId, filename chứa timestamp, userId hoặc error message vào label.

### Cần alert cả khi không có số liệu

Không có metric không đồng nghĩa disk vẫn an toàn. Nếu exporter/agent chết cùng lúc filesystem bị đầy, biểu đồ có thể đứng yên và không có cảnh báo. Thiết kế alert về **exporter down, scrape errors, missing series** riêng, kiểm tra độ trễ collect và đồng bộ clocks. Đường nhận alert nên không phụ thuộc vào chính log file đang bị đe dọa.

## 9. Docker: stdout/stderr vẫn có thể làm đầy host

Trong Docker, ứng dụng Java thường ghi console, nhưng log không vì thế “biến mất khỏi disk”. Tùy logging driver, Docker lưu stdout/stderr vào vùng dữ liệu của daemon. Với driver `json-file`, nếu không cấu hình rotation, file có thể tăng không giới hạn theo chính sách driver/version đang dùng.

Ví dụ `daemon.json` cho Docker Engine với `json-file`:

~~~json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
~~~

**Lưu ý kỹ thuật:**

1. `max-size` là ngưỡng rotate file log driver, `max-file` là số file được giữ; các giá trị `log-opts` trong `daemon.json` phải là **string**.
2. Cấu hình mặc định daemon mới áp dụng cho **container được tạo sau khi đổi cấu hình**; container đang chạy không tự thay rotation bằng việc restart daemon đơn thuần. Cần kiểm tra/recreate theo quy trình triển khai.
3. `max-size=10m` và `max-file=3` chỉ giới hạn theo driver và container tương ứng; không bảo đảm host có đủ dung lượng cho **hàng trăm containers**, images và volumes khác.
4. Có driver `local` hỗ trợ rotation/compression theo thiết kế của Docker. Chọn driver theo nhu cầu `docker logs`, collector hiện có và khả năng vận hành; không thay chỉ vì thấy file lớn mà chưa hiểu pipeline.
5. **Không chỉnh/xóa trực tiếp JSON file do Docker quản lý bằng công cụ tùy ý**; Docker khuyến cáo để daemon tự quản lý. Thao tác bên ngoài có thể gây hành vi không mong đợi và làm collector bị mất offset.

**Nếu JVM vừa ghi RollingFileAppender vào volume, vừa ghi console cùng event**, hai tuyến có thể tạo bản sao ở backend. Đó là vấn đề routing/ingest; cần phân biệt hai sinks trước khi tính dung lượng và tính phí.

## 10. Kubernetes: local ephemeral storage, container logs và eviction

Trên Kubernetes, local ephemeral storage có thể được dùng bởi:

- Container writable layer.
- Container logs do runtime/kubelet quản lý.
- Disk-backed `emptyDir` volumes.
- Một số file tạm hoặc caches trên node.

Kubelet đo usage theo cấu hình filesystem/runtime phù hợp. Khi Pod hoặc container vượt các giới hạn local ephemeral storage, hoặc node filesystem rơi vào disk pressure, Pod có thể bị **evicted** theo các quy tắc hiện hành. Node có thể theo dõi `nodefs`, `imagefs` và `containerfs` tùy layout; chúng không nhất thiết tương ứng ba ổ vật lý.

Ví dụ tài nguyên container có request/limit về ephemeral storage:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: logging-demo
spec:
  containers:
    - name: app
      image: example/app:v1
      resources:
        requests:
          ephemeral-storage: "512Mi"
        limits:
          ephemeral-storage: "2Gi"
~~~

Manifest này **minh họa cấu trúc**, không phải workload triển khai được (image `example/app:v1` chỉ là ký hiệu). Giới hạn này giúp kubelet/scheduler quản lý trong các layout hỗ trợ; nó **không phải vùng disk dành riêng luôn có sẵn**, không bảo đảm log sẽ được lưu dài hạn, và không thay alert node disk pressure/rotation. Một số cách cấu hình filesystem không được kubelet đo ephemeral usage đầy đủ.

**Đừng chỉ giám sát file `app.log` bên trong container**: stdout có thể được lưu trên node ở vị trí khác. Sidecar collector cũng có buffer/queue, writable layer và emptyDir dùng chung budget. Nếu nhiều Pods dùng chung node, tổng log của chúng có thể đẩy node vào eviction dù từng app thấp hơn ngưỡng riêng.

Các nguồn quan sát:

- Node filesystem free bytes và free inode/file nodes.
- Pod/container ephemeral storage usage, evictions và events từ kubelet.
- Container log rotation settings của kubelet/runtime.
- Collector queue depth, receiver/export errors, các receiver đang đọc đúng source.
- Ảnh hưởng tới node workload khác khi disk pressure.

Kubernetes không phải kho lưu audit dài hạn: local ephemeral storage **không có bảo đảm bền vững** khi Pod/node mất. Nếu log có nghĩa vụ lưu giữ, gửi tới kho bền vững theo hợp đồng ACK/retention và kiểm tra khả năng phục hồi.

## 11. Backend tập trung và chi phí ingestion

Giám sát local capacity thôi chưa đủ nếu log được chuyển tới Elasticsearch/OpenSearch, Loki, cloud logging, data lake hoặc hệ thống khác. Mỗi backend có thể có ràng buộc riêng:

| Tầng | Dấu hiệu cần theo dõi |
| --- | --- |
| Receiver/ingest | Records/bytes nhận, lỗi schema, log rejected, rate limit |
| Queue/exporter | Queue depth, pending bytes, retry, backpressure, drop |
| Hot index | Index/storage bytes, shard/replica, mapping, tốc độ tăng |
| Object storage/archive | Bytes lưu, object count, lifecycle/retention, restore |
| Query | Latency, failed queries, cost, giới hạn index/search |
| Billing | Ingested GB, stored GB-month, overage và thay đổi sau release |

**Ingest bytes** có thể được tính khác với **stored bytes** (nén, index, replica); đừng nhân một số dựa trên ổ địa phương để suy ra hóa đơn. Hãy lấy billing metrics của chính nền tảng đang dùng và đối chiếu theo service/team/environment, nếu được hỗ trợ.

Vấn đề phổ biến: tăng DEBUG trong một service để chẩn đoán incident, quên tắt sau một tuần. Local log đã rotate nên host vẫn an toàn, nhưng backend ingest/billing tăng gấp nhiều lần. Nên có:

- Budget bytes/event và records/s theo service/environment, so sánh trước/sau release.
- Cảnh báo khi error logs/stack traces tăng đột ngột.
- Deadline khi bật tạm DEBUG/TRACE và người chịu trách nhiệm tắt.
- Quản trị high-cardinality fields và index labels để tránh tăng chi phí search.
- Retention riêng cho audit, security, application logs, debug logs.
- Kiểm tra sampling/rate limit không làm mất security/audit events bắt buộc.

Nếu collector gửi lại cùng batch do mất ACK, một số backend có thể ingest duplicate. Chi phí và số event đếm cũng có thể tăng. Giải quyết theo đúng delivery semantics và idempotency của pipeline, không dựa vào việc disk đang còn trống.

## 12. Thiết kế cảnh báo để kịp ứng phó

Không có ngưỡng chung cho mọi nơi; bảng sau chỉ là **đề xuất cấu trúc**, không phải thiết lập mặc định bắt buộc.

| Tín hiệu | Cảnh báo sớm | Cảnh báo khẩn | Cần kiểm tra |
| --- | --- | --- | --- |
| Free capacity mount chứa log | Usable dưới ngưỡng cảnh báo đã chọn | Dưới reserve tuyệt đối | Có workload khác cùng mount? |
| Time-to-reserve | Chẳng hạn dưới 4 giờ trong xu hướng ổn định | Chẳng hạn dưới 30 phút hoặc burn rate tăng vọt | Rolling/cleanup vừa diễn ra? |
| Inode available | Giảm liên tục hoặc thấp theo policy | Rất gần cạn inode | Có nhiều file nhỏ? |
| App log output rate | Cao bất thường so với baseline | Tăng nhanh gây risk trong thời gian ngắn | Error loop, debug toggle, payload logging |
| Queue/collector buffer | Backlog tăng và chưa drain | Buffer/queue sắp đầy, drop/error | Remote backend lỗi hay network? |
| Log write errors/drop | Bắt đầu phát sinh | Mất audit/event quan trọng | Appender sync/async policy |
| Backend ingest cost | Tiêu thụ vượt budget ngày/tuần | Overage đang tăng không kiểm soát | New release, duplicate source, debug |
| Retention gap | Archive tuổi cao hơn policy hoặc sớm bị xóa | Audit thiếu record/vi phạm hold | Lifecycle/config/permissions |

**Giảm alert noise:** dùng `for` đủ để tránh spike đơn lẻ; nhóm theo mount/service/sink; không alert mỗi file khi có hàng nghìn archives. Nhưng các điều kiện nguy hiểm nhanh như drop audit hoặc disk chỉ còn vài phút có thể cần alert ngay.

Một cảnh báo đĩa có thể có `severity=warning` và `critical` tùy **absolute free bytes**, **free ratio** và **time-to-reserve**. Không chỉ sử dụng “disk > 90%” ở một ổ 20 TiB, vì 10% free vẫn lớn; ngược lại ổ 2 GiB còn 30% nhưng log ghi 100 MiB/phút có thể nguy hiểm.

### Dashboard hữu ích

Một dashboard sản xuất nên hiển thị:

1. Free bytes và free percentage theo node/mount với xu hướng 1 giờ và 24 giờ.
2. Directory/archive bytes theo service nếu measurement đáng tin.
3. Log events/s và log bytes/s theo level, service, environment.
4. Rolling/retention events, count/size của archive, số file/inode còn trống.
5. Collector queue, retries, drops, rejected logs, ingest latency.
6. Backend stored bytes, ingest bytes, billing và retention.
7. Thay đổi release/config gần lúc volume tăng (deploy version, DEBUG switch).
8. Links đến runbook xử lý disk pressure, owner và impact.

Đừng dùng `filename` có timestamp, `requestId`, `userId` hoặc `eventId` làm metric label: cardinality tăng rất cao. Có thể lưu metadata chi tiết ở **log events** để điều tra từng bản ghi.

## 13. Runbook khi log chiếm gần hết ổ

Một quy trình thực tế, ưu tiên **bảo toàn bằng chứng và an toàn dịch vụ**:

1. **Xác nhận mount:** xác định chính xác filesystem nào gần cạn (`df -h`, `df -i` trên Linux; host/container metrics) và đường `app.log`/stdout/collector buffer thực nằm ở đâu. Đọc được file trong container không chứng minh vị trí lưu ở host.
2. **Xác nhận hướng tăng:** đo usage/bytes-per-second, đối chiếu thời điểm deployment, lỗi exception loop và thay đổi log level. Phân biệt log app với DB/temp/container image.
3. **Kiểm tra logger config:** `RollingFileAppender`, `maxHistory`, `totalSizeCap`, active file và archived file; có rotation thất bại hay nhiều logger cùng ghi file không.
4. **Kiểm tra số file và inode:** rất nhiều file nhỏ có thể làm hết inode. Với host Linux, `du` giúp xem khu vực chiếm dung lượng, nhưng quét thư mục cực lớn cũng tốn I/O; dùng scope hẹp trong production.
5. **Kiểm tra file đã xóa nhưng còn mở:** trên Linux, `lsof +L1` (cần quyền phù hợp) có thể tìm file bị unlink nhưng descriptor vẫn tồn tại; disk không được giải phóng cho đến khi handle đóng. Không xóa/ngắt process vội nếu nó giữ nghiệp vụ trọng yếu.
6. **Giảm nguồn sinh log**: tìm vòng retry/exception, DEBUG/TRACE tạm, payload logging; chỉnh level/sampling chỉ sau khi hiểu ảnh hưởng tới security/audit. Không che lỗi bằng cách tắt tất cả ERROR.
7. **Dọn qua owner hợp lệ:** ưu tiên cơ chế retention/rotation do app/daemon quản lý. Không `rm` hoặc truncate bừa file active, archive đang legal hold, Docker-managed JSON logs hoặc file của database.
8. **Tăng capacity/budget nếu cần:** mở rộng volume, tăng dự phòng hoặc giảm retention **theo policy**, tách logs sang volume riêng khi phù hợp. Đừng dời sang mount không bảo vệ chỉ để có chỗ.
9. **Xác minh sau xử lý:** free bytes hồi phục, write errors/drops ngừng tăng, collector backlog drain, không mất audit, truy vấn backend còn log, cảnh báo trở lại bình thường.
10. **Postmortem và prevention:** lưu snapshot metrics, nguyên nhân, ngưỡng alert đã/không bắt kịp, thay đổi config, owner, bài test burst cần bổ sung.

### Vì sao xóa file mà disk không giảm?

Trên Unix-like filesystem, khi một file bị **unlink** nhưng process vẫn giữ file descriptor mở, blocks có thể tiếp tục chiếm dung lượng cho đến khi descriptor cuối đóng. Lệnh `rm app.log` có thể khiến tên file biến mất nhưng appender vẫn ghi vào inode cũ; `df` không tăng free tương ứng và còn mất đường truy cập log thông thường. Cần xác minh bằng công cụ OS như `lsof +L1` và xử lý lifecycle của writer có kiểm soát.

### Vì sao không nên dọn bằng `truncate -s 0` trực tiếp?

Truncate file active có thể làm mất chứng cứ quan trọng và phá giả định của collector về offset/rotation, dẫn tới bỏ sót hoặc ghi trùng. Nếu cần hành động khẩn, theo runbook có phê duyệt và backup/retention hợp lệ; tốt hơn là khống chế nguồn phát, rotate theo owner hoặc mở rộng capacity.

**Không xóa audit log chỉ để cứu dung lượng**, trừ khi chính sách và người có thẩm quyền cho phép. Audit có thể phải lưu theo legal hold/retention; sai lầm này vừa gây mất bằng chứng vừa không giải quyết nguyên nhân gốc.

## 14. Những lỗi thiết kế làm méo số liệu

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ nhìn size `app.log` | Quên archive, stdout, collector, Docker logs | Đo đường đi và mọi sink thực tế |
| Lấy `FileStore.getUsableSpace()` làm quota Pod | Quá tin mount-level stats | Kubelet/container/runtime metrics song song |
| Dùng `getUnallocatedSpace()` thay usable | Thổi phồng bytes app được phép ghi | Dùng usable khi dự báo app capacity |
| Chỉ alert “disk > 90%” | Không thấy burn rate hoặc ổ lớn có reserve dư | Kết hợp free bytes, ratio, ETA |
| Tính tốc độ từ hai điểm quanh rotation | Nhận growth âm và tưởng hết rủi ro | Dùng cửa sổ dài và byte counter/host trend |
| Quét đệ quy toàn bộ logs mỗi giây | Tự tạo I/O/CPU overhead | Agent chuyên dụng, bounded scan, interval phù hợp |
| Nhầm raw log bytes với backend billed GB | Sai dự toán chi phí | Dùng ingest/storage billing metrics thực |
| Tin `totalSizeCap` giới hạn cả disk | Active log, temp, file khác không nằm trong cap | Alert host mount, reserve, audit/cap riêng |
| Bật logrotate và RollingFile cùng file | Có thể race/nhân bản/mất log | Một owner cho rotation |
| Xóa file đang mở trên Linux | Dung lượng không giảm, log khó truy cập | Kiểm tra descriptors và xử lý writer |
| Truncate Docker json-file trực tiếp | Làm hỏng quản lý daemon/offset | Quản lý qua Docker log driver |
| Giảm log level bỏ qua audit | Mất bằng chứng/ràng buộc tuân thủ | Phân loại log, protect audit path |
| Thấy collector queue 0 rồi tưởng nhận đủ | Có thể đã drop hoặc exporter down | Giám sát drops/errors/received/exported |
| File size tăng ở đầu nguồn nhưng backend thiếu | Drop, retry, parser fail hoặc routing sai | Đối chiếu counts xuyên pipeline |
| Không theo dõi inode | Tạo file mới thất bại dù byte còn | Inode monitoring ở host thích hợp |
| Metric label theo filename timestamp | Cardinality cao | Metric theo service/sink/mount |
| Chỉ test nhu cầu ngày thường | Không chịu được error burst | Test incident load và shutdown |
| Coi rotation là retention audit hợp lệ | Xóa trước hạn, mất hold và bằng chứng | Storage lifecycle/retention riêng có kiểm chứng |

## 15. Kiểm thử hệ thống giám sát dung lượng

### Unit test cho logic

- `usableBytes` gần reserve và đúng reserve: trạng thái có khác nhau theo điều kiện `<=` không?
- Tốc độ sinh log bằng 0/không có metric: trả trạng thái **không đủ dữ liệu** chứ không chia 0.
- Tốc độ tăng lớn, hết reserve trong 15 phút: cảnh báo khẩn.
- Giữa 15 và 60 phút: warning; ngoài 60 phút: bình thường theo ngưỡng của demo.
- Total/usable vô lý, giá trị âm: validate input, không tính ETA rác.
- Hệ thống nhiều filesystem: metric phải gắn đúng mount/path.
- Kiểm tra không có code tự xóa file khi chỉ đang đo và cảnh báo.

### Integration test cho Java logging

1. **Rolling:** cho app ghi đủ nhiều để kích hoạt size-based rollover; xác minh tên archives, compression, `maxHistory` và `totalSizeCap` qua vòng đời thật.
2. **Burst:** mô phỏng lỗi liên tục làm tốc độ log tăng; cảnh báo có xuất đủ sớm, appender có I/O lỗi/drop không?
3. **Queue đầy:** với async logger/collector, kiểm tra block/drop/fallback policy và số event thực nhận ở backend.
4. **Disk gần full trong môi trường thử:** dùng volume/container test nhỏ, không làm đầy filesystem production. Xem ứng dụng xử lý lỗi ghi log thế nào, metrics/alert có còn hoạt động không.
5. **Pod eviction:** xác minh kubelet báo ephemeral usage và ứng dụng có cách thu log bền vững trước khi Pod mất.
6. **Docker rotation:** tạo container với logging driver options mong muốn; xác minh số file/dung lượng và hành vi sau recreate.
7. **Inode exhaustion:** tạo nhiều file thử trên filesystem sandbox có quota riêng, không làm đầy node thật.
8. **Retention:** audit archives không bị dọn sớm; application logs cũ được dọn theo policy; hot storage và backup có lifecycle phù hợp.
9. **Recovery:** khi disk được mở rộng/cleanup, collector queue có drain, appender có phục hồi, log mới có được ghi và gửi hay không.
10. **Alert routing:** trường hợp exporter down hoặc missing series cũng được cảnh báo, không chỉ các giá trị metric thấp.

### Các metric nên có contract rõ ràng

Nếu tự instrument appender Java, định nghĩa rõ `written_bytes` là bytes **sau encoder và ghi thành công** hay bytes ước tính từ message trước format. Đếm `log_events_total` tại API gọi logger không bằng số event thực ghi (filter/sampling/backpressure có thể bỏ). Đối chiếu producer, appender, collector và backend bằng các counter theo stage thay vì cho rằng chúng phải tuyệt đối bằng nhau trong mọi thời điểm.

Cẩn thận **recursive logging**: khi appender ghi lỗi “disk full” vào chính appender đó, lỗi có thể lặp vô hạn. Một health/metrics/alert channel độc lập là ưu tiên để báo tình trạng logging pipeline.

## 16. Checklist đưa vào production

- [ ] Xác định chính xác tất cả đường log đi qua: file, stdout, Docker/kubelet, collector, backend, archive.
- [ ] Giám sát free bytes, usable percent và inode (nơi áp dụng) **tại đúng mount**.
- [ ] Đo log throughput/giây và growth trend, dự báo time-to-reserve thay vì chỉ nhìn dung lượng đã dùng.
- [ ] Cấu hình rotation/retention theo owner rõ; `maxHistory`/`totalSizeCap` không xóa audit trước hạn.
- [ ] Đo active file + archives + queue/buffer và tách khỏi các workload dùng chung disk.
- [ ] Kiểm tra Pod ephemeral-storage, Docker logging-driver rotation và Node disk pressure nếu chạy container.
- [ ] Đặt ngưỡng cảnh báo theo reserve tuyệt đối, thời gian can thiệp, burst và SLO; phát hiện exporter down.
- [ ] Theo dõi appender write failures/drops và collector rejected/retry/lag, không suy log đầy đủ chỉ từ free disk.
- [ ] Theo dõi backend ingest/storage/billing và debug toggles sau release.
- [ ] Có runbook disk-full an toàn, không xóa file đang mở hoặc truncate Docker-managed log tùy tiện.
- [ ] Kiểm thử failure paths, inode, burst, rotation, retention, audit, recovery và alert delivery.
- [ ] Rà lại capacity planning định kỳ theo peak traffic và retention chính sách.

**Ghi nhớ:** Theo dõi dung lượng log không chỉ là xem `du -sh logs` hoặc `df -h`. Cần đồng thời **đo số byte còn ghi được**, **tốc độ sinh log**, **time-to-reserve**, **dung lượng archives/queue/backend**, **lỗi ghi/drop**, và **mối ràng buộc về retention**. Kết hợp đúng tầng đo, rolling có kiểm soát, alert đủ sớm và quy trình xử lý an toàn sẽ giúp logging hỗ trợ vận hành mà không trở thành nguyên nhân làm dịch vụ ngừng hoạt động.

### Tài liệu tham khảo chính thức

- Oracle Java SE 17 — [`java.nio.file.FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html), [`Files.getFileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- Logback — [Rolling file appenders: `SizeAndTimeBasedRollingPolicy`, `maxHistory`, `totalSizeCap`](https://logback.qos.ch/manual/appenders-rolling.html).
- Log4j 2 — [Rolling file appenders và Delete actions](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html).
- Prometheus — [Monitoring Linux host metrics with node_exporter](https://prometheus.io/docs/guides/node-exporter/), [PromQL functions: `predict_linear`](https://prometheus.io/docs/prometheus/latest/querying/functions/).
- Docker — [Configure logging drivers](https://docs.docker.com/engine/logging/configure/), [JSON File logging driver](https://docs.docker.com/engine/logging/drivers/json-file/).
- Kubernetes — [Local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/), [Node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/).
