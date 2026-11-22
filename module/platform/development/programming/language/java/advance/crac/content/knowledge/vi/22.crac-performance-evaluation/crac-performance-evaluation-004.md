# Đo thời gian tải ảnh, restore và mở lại tài nguyên

Trong Java CRaC, thời gian khởi động sau restore không chỉ là thời gian runtime đọc checkpoint image. Ứng dụng còn phải mở lại các tài nguyên bên ngoài, xác minh dependency và đưa worker hoặc request listener về trạng thái sẵn sàng.

Muốn đánh giá hiệu năng đúng, cần đo riêng từng phần của hành trình:

1. **Tải hoặc chuẩn bị checkpoint image:** lấy artifact từ object storage/registry, sao chép vào node và xác minh file.
2. **Runtime restore:** khởi chạy JVM từ image và phục hồi trạng thái process.
3. **Mở lại tài nguyên:** thực hiện callback afterRestore(), tạo lại connection, file handle, client hoặc native resource.
4. **Readiness và warm-up:** kiểm tra dependency, khởi động worker, nạp cache cần thiết và mở traffic.
5. **Request đầu tiên:** đo độ trễ thực tế mà người dùng hoặc caller quan sát được.

Các mốc này giúp phân biệt lợi ích của CRaC với chi phí chuyển image, I/O, kết nối mạng và công việc khởi động sau restore. Nếu chỉ đo thời gian từ lúc chạy lệnh restore đến khi JVM xuất hiện, kết quả có thể bỏ sót phần lớn thời gian ứng dụng chưa thể phục vụ.

## 1. Xác định chính xác các mốc thời gian

Một lần restore có thể được mô tả như sau:

~~~text
Bắt đầu lấy checkpoint image
          |
          v
Image đã có trên node và được xác minh
          |
          v
Bắt đầu yêu cầu runtime restore
          |
          v
Runtime phục hồi process và JVM
          |
          v
Resource.afterRestore() bắt đầu
          |
          v
Mở lại database, HTTP, file và native resource
          |
          v
Dependency validation hoàn tất
          |
          v
Worker / scheduler sẵn sàng
          |
          v
Readiness chuyển sang READY
          |
          v
Request đầu tiên hoàn tất
~~~

Đặt tên mốc nhất quán để các lần chạy có thể so sánh:

| Mốc | Ý nghĩa |
|---|---|
| T0 | Bắt đầu lấy hoặc copy image |
| T1 | Image đã được ghi xong ở node đích |
| T2 | Kiểm tra integrity/checksum hoàn tất |
| T3 | Bắt đầu yêu cầu runtime restore |
| T4 | Ứng dụng đi vào callback afterRestore() đầu tiên |
| T5 | Các resource bắt buộc đã mở lại |
| T6 | Ứng dụng đánh dấu READY và cho phép traffic |
| T7 | Request kiểm tra đầu tiên hoàn tất |

Từ các mốc này có thể tính:

- **Image staging time:** T1 - T0.
- **Image verification time:** T2 - T1.
- **Runtime restore-to-callback time:** T4 - T3.
- **Resource reopen time:** T5 - T4.
- **Readiness time:** T6 - T3.
- **First-request latency window:** T7 - T6.
- **End-to-end time to serve:** T7 - T0.

Runtime restore-to-callback là khoảng đo từ bên ngoài đến callback ứng dụng đầu tiên; nó có thể gồm thời gian runtime khôi phục process, nạp các trang bộ nhớ cần thiết và chuyển quyền điều khiển cho ứng dụng. Nếu cần tách sâu hơn, dùng log hoặc tracing do runtime cung cấp và giữ cách diễn giải đúng với phiên bản JDK/CRaC đang chạy.

Nếu image đã nằm sẵn trên node, T0 và T1 có thể không thuộc đường restore. Ghi rõ điều kiện đó thay vì coi thời gian tải image bằng 0 trong mọi môi trường.

## 2. Phân biệt thời gian tạo image, tải image và restore

Ba thao tác thường bị gộp thành một:

- **Checkpoint creation:** runtime đóng băng trạng thái và ghi checkpoint image.
- **Image transfer/staging:** đưa image đến nơi sẽ restore.
- **Restore:** runtime đọc image và phục hồi process.

Chúng trả lời các câu hỏi hiệu năng khác nhau.

| Hoạt động | Câu hỏi cần trả lời | Ví dụ metric |
|---|---|---|
| Tạo checkpoint | Mất bao lâu để tạo artifact? | checkpoint duration, image size |
| Tải/stage image | Mất bao lâu để chuyển artifact đến node? | bytes, throughput, staging duration |
| Restore | Mất bao lâu để process tiếp tục chạy? | restore-to-callback duration |
| Reopen resource | Dependency mất bao lâu để hoạt động lại? | per-resource reopen duration |
| Readiness | Bao lâu mới nhận được traffic? | time-to-ready |
| Request đầu tiên | Người dùng thấy độ trễ bao nhiêu? | first-request latency |

Không cộng thời gian tạo checkpoint vào restore latency nếu mục tiêu là đo độ trễ một lần khởi động. Nhưng nếu đánh giá tổng chi phí vận hành, có thể phân bổ chi phí tạo image theo số lần restore mà image phục vụ.

Ví dụ, nếu image được tạo một lần và dùng cho 100 lần restore, có thể báo cáo riêng checkpoint creation cost và một chỉ số chi phí phân bổ:

~~~text
Amortized checkpoint cost per restore
    = checkpoint creation duration / 100
~~~

Đây là cách phân tích chi phí vòng đời, không phải thời gian restore thực tế.

## 3. Dùng đồng hồ phù hợp cho từng phép đo

### Trong cùng một JVM: System.nanoTime()

Đo khoảng thời gian trong callback hoặc trong một operation bằng System.nanoTime():

~~~java
long started = System.nanoTime();

reopenDatabase();

long elapsedNanos = System.nanoTime() - started;
long elapsedMillis =
    TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

nanoTime() phù hợp đo duration vì không bị điều chỉnh theo giờ hệ thống như đồng hồ wall-clock. Không dùng System.currentTimeMillis() để đo các đoạn ngắn vì NTP hoặc thay đổi system clock có thể làm kết quả nhảy.

### Giữa các process: dùng đồng hồ monotonic của harness

Không nên lấy hai giá trị System.nanoTime() từ hai JVM khác nhau rồi trừ cho nhau. API chỉ bảo đảm hiệu quả cho việc đo khoảng thời gian trong cùng JVM; không nên dựa vào origin của nanoTime() giống nhau giữa các process hoặc host.

Để đo T3 đến T6, dùng một supervisor hoặc orchestration harness bên ngoài:

- Ghi thời điểm bắt đầu bằng monotonic clock của harness.
- Khởi chạy lệnh restore.
- Chờ một tín hiệu callback hoặc readiness từ ứng dụng.
- Ghi thời điểm nhận tín hiệu bằng cùng monotonic clock.
- Tính elapsed time trong chính harness.

Nếu các bước chạy trên nhiều host, dùng một bộ đo end-to-end tại orchestrator hoặc đồng bộ clock có kiểm soát. Không trừ timestamp từ các máy khác nhau nếu chưa xử lý sai lệch clock.

### Wall-clock timestamp dùng để đối chiếu log

Có thể ghi UTC timestamp để nối log từ JVM, runtime và orchestrator:

~~~java
Instant eventTime = Instant.now();
~~~

Timestamp giúp đối chiếu sự kiện, nhưng duration chính vẫn nên được tính bằng monotonic clock trong cùng miền đo.

## 4. Đo thời gian tải hoặc staging checkpoint image

Nếu image được lấy từ remote storage, đo riêng:

- Thời điểm bắt đầu download/copy.
- Thời điểm hoàn tất ghi file.
- Kích thước image thực tế.
- Thời gian kiểm tra checksum hoặc chữ ký.
- Throughput trung bình.
- Thời gian chờ volume attach/mount nếu có.
- Thời gian giải nén hoặc chuẩn bị artifact nếu quy trình có bước đó.

Ví dụ dùng GNU time để đo một thao tác copy local:

~~~bash
/usr/bin/time -f 'elapsed_s=%e max_rss_kb=%M' \
  cp /source/checkpoint-image /local/checkpoints/checkpoint-image
~~~

Với image tải từ object storage, dùng thời gian của transfer client hoặc orchestrator và ghi số byte thực tế. Tách thời gian chờ mạng, download và checksum nếu công cụ hỗ trợ.

Thông lượng trung bình:

\[
Throughput = \frac{ImageSizeBytes}{StagingDurationSeconds}
\]

Nếu image có kích thước 2 GiB và staging mất 8 giây, throughput trung bình xấp xỉ 256 MiB/s theo đơn vị nhị phân. Khi báo cáo, ghi rõ dùng MB hay MiB.

### Không bỏ qua checksum

Một image tải nhanh nhưng bị hỏng không phải kết quả hiệu năng hợp lệ. Xác minh checksum hoặc chữ ký trước restore và ghi thời gian xác minh riêng.

Không nên đưa checksum validation ra khỏi phép đo end-to-end nếu production thực tế luôn thực hiện bước đó. Có thể báo cáo cả staging-only và staging-plus-verification để người đọc hiểu chi phí của từng bước.

### Cache của storage

Lần đầu đọc image có thể chậm hơn do cache lạnh; các lần tiếp theo có thể nhanh hơn vì dữ liệu đã nằm trong page cache hoặc cache của storage layer.

Ghi rõ mỗi phép đo là:

- Cold cache: node chưa đọc image gần đây.
- Warm cache: image hoặc các page liên quan đã có trong cache.
- Local storage: image nằm trên disk/volume của node.
- Remote storage: image được lấy qua network hoặc filesystem từ xa.

Không trộn cold-cache và warm-cache vào cùng một percentile mà không phân nhóm.

## 5. Đo thời gian runtime restore

Runtime restore bắt đầu khi hệ thống yêu cầu JVM phục hồi từ checkpoint image. Kết thúc của đoạn đo nên là một mốc ứng dụng có thể quan sát được, chẳng hạn callback afterRestore() đầu tiên.

Một harness bên ngoài có thể:

1. Ghi T3 bằng monotonic clock.
2. Khởi chạy JVM bằng tùy chọn restore phù hợp với bản phân phối JDK CRaC.
3. Chờ ứng dụng ghi marker T4 hoặc gửi sự kiện qua socket/pipe.
4. Ghi T4 bằng cùng clock của harness.
5. Tính runtime restore-to-callback duration.

Cú pháp khởi chạy restore thay đổi theo JDK CRaC distribution và môi trường triển khai. Hãy dùng lệnh được tài liệu của runtime đang chạy hỗ trợ; không lấy lệnh checkpoint làm lệnh restore.

### Marker từ callback đầu tiên

Một Resource có thể ghi marker khi callback bắt đầu:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context)
        throws Exception {
    markerSink.record("AFTER_RESTORE_BEGIN");
    reopenResources();
}
~~~

Marker sink nên là một kênh kiểm thử hoặc telemetry đã sẵn sàng ở thời điểm callback. Nếu marker được ghi ra file, file đó phải nằm trên một filesystem mà tiến trình restore có thể truy cập.

Đối với production, dùng metric hoặc event có cấu trúc. Không để việc ghi marker trở thành một dependency mới có thể làm callback thất bại nếu telemetry server tạm thời không hoạt động.

### Log runtime

Một số bản phân phối JDK cung cấp log cho CRaC hoặc checkpoint/restore. Nếu dùng, ghi rõ cờ log, phiên bản runtime và event cụ thể dùng làm mốc. Không suy luận rằng một log line nội bộ có cùng ý nghĩa giữa các bản JDK khác nhau.

Nếu không có mốc runtime đáng tin cậy, báo cáo T3 đến T4 là "restore-to-first-application-callback", không gọi đó là thời gian CPU thuần của runtime.

## 6. Đo thời gian mở lại từng Resource trong afterRestore()

Không nên chỉ đo tổng thời gian afterRestore(). Khi tổng thời gian tăng, cần biết database pool, HTTP client, file handle hay secret provider đang chiếm phần lớn.

Có thể định nghĩa interface cho tài nguyên cần mở lại:

~~~java
public interface ReopenableResource {
    String name();
    void reopen() throws Exception;
}
~~~

Một Resource CRaC có thể đo từng thao tác:

~~~java
import java.util.concurrent.TimeUnit;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class TimedRestoreResource implements Resource {
    private final ReopenableResource[] resources;
    private final RestoreMetrics metrics;

    public TimedRestoreResource(
            ReopenableResource[] resources,
            RestoreMetrics metrics) {
        this.resources = resources;
        this.metrics = metrics;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Đóng tài nguyên theo thứ tự phụ thuộc của ứng dụng.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        long totalStarted = System.nanoTime();

        for (ReopenableResource resource : resources) {
            long started = System.nanoTime();

            try {
                resource.reopen();

                long elapsed = System.nanoTime() - started;
                metrics.recordSuccess(
                    resource.name(),
                    elapsed,
                    TimeUnit.NANOSECONDS
                );

            } catch (Exception failure) {
                long elapsed = System.nanoTime() - started;
                metrics.recordFailure(
                    resource.name(),
                    elapsed,
                    failure
                );
                throw failure;
            }
        }

        metrics.recordTotal(
            System.nanoTime() - totalStarted,
            TimeUnit.NANOSECONDS
        );
    }
}
~~~

RestoreMetrics là abstraction do ứng dụng triển khai. Nó có thể ghi log, cập nhật Micrometer timer hoặc gửi event đến hệ thống telemetry. Nên giữ đường ghi metric đơn giản, không phụ thuộc vào chính resource đang được mở lại.

### Ghi cả thành công và thất bại

Khi một resource thất bại, vẫn cần ghi duration của lần thử và loại lỗi. Nếu chỉ ghi metric thành công, dashboard có thể bỏ qua những lần restore chậm hoặc thất bại nhất.

Các metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| crac_resource_reopen_seconds | Thời gian mở lại từng resource |
| crac_resource_reopen_total | Số lần thử mở resource |
| crac_resource_reopen_failures_total | Số lần mở lại thất bại |
| crac_after_restore_seconds | Tổng thời gian callback hoặc nhóm callback |
| crac_restore_readiness_seconds | Thời gian từ restore đến READY |

Dùng label có cardinality thấp như resource_type hoặc resource_name cố định. Không đưa instance ID, request ID, path chứa tenant hoặc secret vào label metric có cardinality cao.

## 7. Đo readiness và thời điểm phục vụ request đầu tiên

Một callback afterRestore() hoàn tất không đồng nghĩa ứng dụng đã phục vụ được request.

Ứng dụng có thể còn phải:

- Kiểm tra kết nối database.
- Xác thực với broker hoặc secret manager.
- Khởi động worker.
- Nạp cache quan trọng.
- Khởi tạo scheduler.
- Chạy health check.
- Mở request listener hoặc traffic gate.

Nên có readiness state rõ ràng:

~~~text
RESTORING
    |
    v
REOPENING_RESOURCES
    |
    v
VALIDATING_DEPENDENCIES
    |
    v
STARTING_WORKERS
    |
    v
WARMING_UP
    |
    v
READY
~~~

T6 nên là thời điểm ứng dụng thực sự chấp nhận traffic, không phải lúc callback cuối cùng vừa return nếu còn bước khởi động khác.

Để đo T7, gửi một request kiểm tra giống đường request thật và ghi thời gian từ lúc client bắt đầu gửi đến lúc nhận response hoàn chỉnh. Đo riêng:

- First request latency.
- First successful business request.
- Latency của các request tiếp theo trong giai đoạn warm-up.
- Error rate trong khoảng ngay sau READY.

Một endpoint health đơn giản có thể trả READY trước khi database query hoặc worker thực sự hoạt động. Hãy chọn readiness probe đại diện cho dependency bắt buộc của workload.

## 8. Đo tổng thời gian afterRestore()

Nếu có nhiều Resource riêng, mỗi resource có thể đo callback của mình. Nếu muốn đo tổng thời gian toàn bộ afterRestore(), dùng một coordinator duy nhất hoặc một registry thu thập timestamp.

Ví dụ dùng một timer đơn giản:

~~~java
public final class RestoreTimer {
    private long startedAt;

    public void start() {
        startedAt = System.nanoTime();
    }

    public long elapsedNanos() {
        return System.nanoTime() - startedAt;
    }
}
~~~

Không dùng một biến timer static dùng chung cho nhiều restore nếu ứng dụng có thể tạo nhiều context hoặc nhiều instance trong cùng process test. Nên gắn timer với một restore attempt cụ thể.

Nếu callback được gọi theo nhiều Resource, ghi nhận từng callback và tổng thời gian ở coordinator. Không cộng thời gian callback nếu có thể có phần thực thi song song; tổng elapsed thực tế và tổng CPU time là hai khái niệm khác nhau.

## 9. Tuần tự hay song song khi mở lại tài nguyên?

Mở lại resource tuần tự dễ hiểu và phù hợp khi có dependency:

~~~text
Secret Provider
      |
      v
Database Pool
      |
      v
Repository-dependent worker
~~~

Nếu các thao tác độc lập, ví dụ tạo hai HTTP client không phụ thuộc nhau, có thể cân nhắc mở song song. Tuy nhiên, parallelization cần được đo và kiểm soát:

- Tổng thời gian elapsed có thể giảm.
- CPU, memory và số kết nối đồng thời có thể tăng.
- Dependency ordering phức tạp hơn.
- Một task thất bại trong khi task khác thành công cần cleanup đồng bộ.
- Callback không được return trước khi tất cả resource bắt buộc hoàn tất.

Không dùng parallel stream hoặc executor được tạo tùy tiện trong callback nếu lifecycle thread, shutdown và timeout chưa được quản lý. Hãy đo baseline tuần tự trước, sau đó thử song song với giới hạn concurrency và xác nhận thứ tự phụ thuộc.

## 10. Đo thời gian bằng JFR, Micrometer và log

### Java Flight Recorder

JFR có thể hỗ trợ phân tích CPU, allocation, thread, class loading, file I/O và một số event runtime. Có thể bắt đầu recording quanh giai đoạn khởi động hoặc dùng cấu hình JFR phù hợp với JDK đang chạy.

JFR giúp giải thích tại sao callback hoặc warm-up chậm, nhưng không thay thế stopwatch end-to-end của orchestrator. Việc bật recording cũng có overhead nhỏ; ghi rõ cấu hình khi so sánh.

### Micrometer

Nếu ứng dụng dùng Spring Boot Actuator/Micrometer, Timer có thể đo duration:

~~~java
Timer.Sample sample = Timer.start(registry);

try {
    reopenDatabase();
    sample.stop(registry.timer(
        "crac.resource.reopen",
        "resource", "database"
    ));
} catch (Exception failure) {
    sample.stop(registry.timer(
        "crac.resource.reopen",
        "resource", "database",
        "result", "failure"
    ));
    throw failure;
}
~~~

Ví dụ này minh họa cách ghi timer. Trong ứng dụng thực tế, tránh tạo meter với label thay đổi theo mỗi instance hoặc request.

### Structured log

Một event có thể ghi:

~~~text
event=crac_restore_phase
phase=resource_reopen
resource=database
duration_ms=182
result=success
restore_generation=restore-42
~~~

Ghi cả version ứng dụng, JDK và runtime trong metadata của benchmark. Không ghi credential, JDBC password, token hoặc dữ liệu người dùng.

## 11. Thiết kế benchmark có thể so sánh

Một phép đo có ích phải có điều kiện lặp lại được.

### Chuẩn bị các nhóm chạy

Nên có ít nhất các nhóm:

1. **Cold JVM startup:** khởi động ứng dụng không dùng checkpoint.
2. **CRaC restore, image local:** image đã nằm trên node.
3. **CRaC restore, image remote:** cần staging từ storage.
4. **CRaC restore với dependency warm:** database/broker đã sẵn sàng.
5. **CRaC restore với dependency cold:** cần tạo connection hoặc cache mới.

Nếu mục tiêu là đo lợi ích so với khởi động bình thường, cold startup và CRaC restore phải dùng cùng phiên bản ứng dụng, cấu hình, workload và điều kiện dependency tương đương.

### Số lần lặp và percentile

Chạy nhiều lần để tránh kết luận từ một lần đo. Có thể bắt đầu với khoảng 30 lần cho mỗi cấu hình, sau đó tăng số lần nếu cần ước lượng tail latency ổn định hơn.

Báo cáo:

- Minimum.
- Median (p50).
- p90.
- p95.
- p99 nếu có đủ mẫu.
- Maximum.
- Success rate.

Không chỉ báo cáo average. Một lần restore chậm do storage hoặc DNS có thể bị che khuất trong giá trị trung bình.

### Kiểm soát các yếu tố gây nhiễu

Ghi lại:

- CPU model, số core và quota.
- Memory limit và RSS.
- JDK vendor, version, build và CRaC implementation.
- Kernel và container runtime.
- Kích thước checkpoint image.
- Loại filesystem và storage.
- Cold/warm cache.
- Số resource cần mở lại.
- Database/broker latency.
- Network RTT.
- Số worker và thread.
- Cấu hình logging/JFR.
- Số lượng request warm-up.

Không so sánh hai lần chạy nếu một lần dùng image local và lần còn lại phải tải qua network mà không ghi rõ khác biệt.

## 12. Tính toán và trình bày kết quả

Ví dụ bảng benchmark:

| Kịch bản | Stage image | Runtime restore | Reopen resources | Ready | First request |
|---|---:|---:|---:|---:|---:|
| Cold startup | — | — | — | 4.8 s | 120 ms |
| CRaC, image local | 0 ms | 0.7 s | 0.9 s | 1.9 s | 95 ms |
| CRaC, image remote | 1.1 s | 0.7 s | 0.9 s | 3.0 s | 96 ms |

Số liệu chỉ minh họa cách trình bày, không phải benchmark thực tế hoặc kỳ vọng cho mọi ứng dụng.

Có thể tính:

~~~text
CRaC time-to-ready
    = image staging
    + image verification
    + runtime restore
    + resource reopen
    + readiness / warm-up
~~~

Nếu image đã local, thành phần staging có thể bằng 0 trong phép đo đó. Khi cần so sánh với cold startup:

~~~text
Startup improvement
    = cold-start time-to-ready
      - CRaC time-to-ready
~~~

Tỷ lệ cải thiện:

\[
ImprovementPercent =
\frac{T_{cold} - T_{CRaC}}{T_{cold}} \times 100
\]

Dùng cùng định nghĩa READY ở hai nhóm. Nếu cold startup được đo đến ApplicationReadyEvent còn CRaC được đo đến lúc JVM resume, phép so sánh không công bằng.

## 13. Phân tích khi một phase trở thành bottleneck

### Image staging chậm

Kiểm tra kích thước image, throughput storage, network, checksum, compression và mount. Có thể giảm thời gian bằng cách đặt image gần node restore, dùng storage có throughput phù hợp hoặc tránh copy lặp lại khi artifact vẫn hợp lệ.

Không bỏ integrity check chỉ để giảm vài millisecond.

### Runtime restore chậm

Kiểm tra log CRaC/runtime, image size, memory mapping, page faults, storage latency và CPU quota. Một image lớn hoặc host khác cấu hình có thể làm restore chậm.

Nếu runtime dùng lazy page loading, một phần chi phí có thể xuất hiện sau callback đầu tiên khi ứng dụng truy cập các page chưa được nạp. Vì vậy, đo thêm thời gian warm-up và request đầu tiên.

### afterRestore() chậm

Dùng metric per-resource để xác định resource nào tốn thời gian. Thường có thể là:

- Tạo database connection pool.
- TLS handshake.
- DNS lookup.
- Đọc secret hoặc certificate.
- Khôi phục file handle hoặc mount.
- Khởi động worker và consumer.
- Rebuild cache.

Chỉ tối ưu thành phần được đo là bottleneck. Ví dụ, tăng pool size không chắc giảm restore time nếu database đang giới hạn số connection đồng thời.

### Readiness chậm dù resource đã mở

Kiểm tra health check, warm-up query, cache loading, migration hoặc startup runner. Đừng mở traffic sớm nếu dependency chưa thực sự sẵn sàng.

### Request đầu tiên chậm

Có thể do JIT compilation, class loading, lazy initialization, page fault, DNS, TLS session hoặc cache miss. So sánh first request với request thứ 10, 100 và steady-state để nhận biết warm-up curve.

## 14. Lazy page loading và chi phí xuất hiện sau restore

Một số cách triển khai checkpoint/restore có thể trì hoãn việc nạp một phần memory page cho đến khi ứng dụng truy cập chúng. Khi đó:

- Restore-to-callback có thể nhanh.
- afterRestore() có thể hoàn tất nhanh.
- Request đầu tiên vẫn có thể chậm vì page fault hoặc I/O.
- Warm-up có thể làm tăng READY time nhưng giảm latency của request thật.

Không kết luận rằng runtime restore nhanh đồng nghĩa ứng dụng phục vụ nhanh. Đo ít nhất ba điểm: callback đầu tiên, readiness và request đầu tiên.

Nếu workload có đường code quan trọng, có thể chạy warm-up có kiểm soát trước khi mở traffic. Warm-up phải đại diện cho đường sử dụng thật và không gây side effect nghiệp vụ như tạo đơn hàng hoặc gửi thanh toán.

## 15. Theo dõi hiệu năng qua nhiều lần restore

Khi image được dùng lâu dài, thời gian restore có thể thay đổi theo môi trường:

- Storage volume bị thay đổi.
- Database hoặc secret manager chậm hơn.
- Certificate hoặc credential phải refresh.
- Image cũ không còn phù hợp với node mới.
- Cache lạnh hoặc dữ liệu lớn hơn.
- Số resource cần mở lại tăng.
- CPU/memory quota thay đổi.

Nên ghi một restore generation ID để liên kết các metric trong cùng lần restore. Dùng ID này trong log hoặc trace, tránh đưa nó vào metric label nếu tạo cardinality quá cao.

Dashboard nên có:

- Time-to-ready p50/p95.
- Image staging duration và throughput.
- Runtime restore-to-callback duration.
- afterRestore duration.
- Per-resource reopen p95.
- Restore success/failure count.
- First-request latency.
- CPU, RSS, page fault và I/O.
- Số lần retry và timeout khi mở dependency.

Đặt ngưỡng cảnh báo theo SLO thực tế. Ví dụ, nếu p95 time-to-ready vượt ngưỡng trong nhiều lần liên tiếp, điều tra phase có mức tăng lớn nhất thay vì chỉ restart ứng dụng.

## 16. Các sai lầm thường gặp khi đo

**Chỉ đo thời gian lệnh restore:** bỏ sót image staging, resource reopen, warm-up và readiness.

**Dùng currentTimeMillis() để đo duration:** clock có thể bị điều chỉnh. Dùng nanoTime() trong cùng JVM và monotonic clock ở harness.

**Trừ nanoTime() giữa hai JVM:** origin không được bảo đảm để so sánh giữa process. Dùng một harness bên ngoài.

**Gộp cold cache và warm cache:** làm percentile khó diễn giải. Tách nhóm theo trạng thái cache và storage.

**So sánh mốc READY khác nhau:** cold start và CRaC restore có thể dùng điều kiện readiness khác nhau. Chuẩn hóa mốc kết thúc.

**Chỉ đo tổng afterRestore():** không biết database, HTTP hay file đang chậm. Đo từng resource.

**Bỏ qua lỗi và retry:** chỉ ghi duration thành công sẽ làm kết quả tốt giả tạo. Ghi failure, retry và timeout.

**Chỉ báo cáo average:** không thể hiện tail latency. Báo median và percentile.

**Warm-up gây side effect:** warm-up có thể tạo dữ liệu nghiệp vụ hoặc gửi message thật. Dùng endpoint và workload kiểm thử an toàn.

**Tối ưu bằng cách bỏ validation:** có thể làm instance phục vụ với credential hoặc resource không hợp lệ. Giữ nguyên các bước correctness bắt buộc.

## 17. Quy trình benchmark đề xuất

### Chuẩn bị

1. Chọn cùng một phiên bản ứng dụng và cấu hình cho cold startup và CRaC restore.
2. Ghi lại JDK, CRaC runtime, kernel, container và storage.
3. Xác định checkpoint image, kích thước và vị trí lưu.
4. Liệt kê Resource cần mở lại và thứ tự dependency.
5. Định nghĩa chính xác mốc READY và request đầu tiên.
6. Chuẩn bị harness bên ngoài dùng monotonic clock.

### Đo image

1. Bắt đầu timer khi tải hoặc copy image.
2. Ghi số byte và thời gian staging.
3. Xác minh checksum/chữ ký.
4. Ghi thời gian xác minh riêng.
5. Phân loại cold cache và warm cache.

### Đo restore và resource

1. Bắt đầu timer bên ngoài trước khi gọi lệnh restore.
2. Ghi marker tại callback afterRestore() đầu tiên.
3. Dùng System.nanoTime() đo từng resource reopen.
4. Ghi cả success, failure và retry.
5. Ghi mốc tất cả resource bắt buộc đã sẵn sàng.
6. Ghi mốc ứng dụng chuyển sang READY.

### Đo request

1. Gửi request kiểm tra ngay sau READY.
2. Ghi latency và kết quả.
3. Gửi thêm một nhóm request warm-up có kiểm soát.
4. So sánh first-request với steady-state.
5. Không dùng warm-up tạo side effect nghiệp vụ.

### Tổng hợp

1. Lặp lại từng kịch bản đủ số lần.
2. Tính min, p50, p90, p95 và p99 khi có đủ mẫu.
3. Báo cáo success rate và failure.
4. So sánh cold startup với CRaC trên cùng mốc READY.
5. Xác định phase bottleneck trước khi đề xuất tối ưu.
6. Lưu raw measurement cùng metadata môi trường để có thể tái hiện.

## 18. Nguyên tắc cần ghi nhớ

- Tách image staging, checksum, runtime restore, resource reopen, readiness và first request.
- Không gộp checkpoint creation vào restore latency nếu đang đo thời gian khởi động.
- Dùng System.nanoTime() để đo duration trong cùng JVM.
- Dùng một monotonic clock của harness cho thời gian xuyên process.
- Không trừ nanoTime() từ hai JVM hoặc hai host.
- Ghi kích thước image, storage, cache state và môi trường chạy.
- Đo riêng từng Resource trong afterRestore(), bao gồm cả failure.
- Chỉ đánh dấu READY khi dependency và worker bắt buộc đã sẵn sàng.
- Đo request đầu tiên để phát hiện chi phí lazy page loading và warm-up.
- So sánh cold startup và CRaC restore trên cùng định nghĩa READY.
- Báo cáo percentile và success rate, không chỉ average.
- Không bỏ checksum, validation hoặc readiness gate chỉ để giảm thời gian đo.

Một phép đo CRaC có ý nghĩa phải phản ánh thời điểm ứng dụng thật sự có thể phục vụ. Khi tách thời gian chuyển image, runtime restore, mở lại từng resource và readiness, nhóm phát triển có thể xác định chính xác phần nào đang tiêu tốn thời gian, đánh giá lợi ích so với cold startup và tối ưu mà không làm giảm tính đúng đắn của quá trình phục hồi.
