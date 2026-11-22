# 21.3. Ưu tiên bằng chứng ít ảnh hưởng rồi đánh giá nhu cầu dump hoặc cấu hình chi tiết

Khi một dịch vụ Java bị tăng độ trễ, tăng RSS, treo thread hoặc có dấu hiệu OutOfMemoryError, thao tác chẩn đoán **cũng có thể làm tình hình xấu hơn**. Một heap dump lớn có thể làm JVM pause, tạo nhiều I/O và tiêu thụ hàng GiB dung lượng đúng lúc máy đang thiếu bộ nhớ hoặc đĩa. Bật logging ở mức quá chi tiết có thể làm tăng CPU, cấp phát chuỗi và ghi file. Đôi khi chỉ cần metrics hiện có, vài snapshot đúng thời điểm hoặc một recording JFR cấu hình nhẹ đã đủ chỉ ra hướng điều tra.

Nguyên tắc của bài là: **thu bằng chứng có chi phí thấp nhất đủ để kiểm tra giả thuyết hiện tại; chỉ nâng mức thu thập khi đã xác định khoảng trống thông tin và chấp nhận được rủi ro**. Không phải “tuyệt đối cấm heap dump” hoặc “mọi metric đều miễn phí”. Đây là cách quản lý đánh đổi giữa **giá trị chẩn đoán, tác động vận hành, thời gian thu, kích thước và bảo mật dữ liệu**.

Phạm vi: HotSpot/OpenJDK Java 17+ trên server/container; ví dụ `jcmd`, `jstat`, Java Flight Recorder (JFR), các MXBean và các mức thu thập từ quan sát sẵn có tới heap dump. Với JVM khác hoặc phiên bản khác, phải tra `jcmd <pid> help` và khả năng hỗ trợ thật trước khi dùng.

## 1. Tại sao chọn công cụ theo mức ảnh hưởng?

Có ba câu hỏi phải trả lời trước khi tác động lên JVM đang có sự cố:

1. **Bằng chứng nào đang thiếu?** Ví dụ: cần biết “CPU tăng do mã nào?”, “thread đang đợi lock hay I/O?”, “post-GC heap có tăng lâu dài?”, “vì sao object còn reachable?”. Mỗi câu hỏi cần loại dữ liệu khác nhau.
2. **Việc thu bằng chứng có thể làm sai hoặc xóa dấu vết không?** Một lệnh có thể tạo safepoint, kích hoạt GC, thay đổi scheduling, tăng allocation/I/O, khiến tiến trình gặp giới hạn cgroup hoặc làm gián đoạn latency.
3. **Kết quả có đủ an toàn, đủ chi tiết và đủ bền để phân tích?** Tệp JFR/HPROF có thể chứa đường dẫn, tham số, tên class, stack traces, token, chuỗi và dữ liệu người dùng. Thu xong cần lưu trữ, phân quyền, chuyển giao và xóa đúng chính sách.

**Mức độ ảnh hưởng là tương đối**, không phải nhãn bất biến. Một thread dump trên JVM vài chục thread khác nhiều với JVM hàng chục nghìn thread. Một JFR recording `default` ngắn khác việc bật toàn bộ allocation stack traces liên tục. Ngay cả lệnh được tài liệu đánh dấu `Impact: Low` vẫn nên đo, giới hạn tần suất và giám sát khi chạy trên production nhạy cảm.

## 2. Thang ưu tiên bằng chứng: từ nhẹ đến nặng

| Mức | Nhóm bằng chứng/công cụ | Lợi ích chính | Đánh đổi, lưu ý |
| --- | --- | --- | --- |
| **0 — sẵn có** | Dashboard, application logs đã ghi, metrics từ OS/cgroup, GC logs đã bật, trace hiện hữu, deployment timeline. | Không cần yêu cầu JVM tạo loại bằng chứng mới. | Metric có thể lấy mẫu thưa, bị aggregate, thiếu correlation hoặc hết retention. |
| **1 — truy vấn nhẹ có kiểm soát** | `jcmd <pid> VM.version`, `VM.uptime`, `VM.flags`, `VM.command_line`; `jstat -gcutil` lấy mẫu hạn chế; JMX counters đang có. | Xác minh đúng tiến trình, cấu hình, xu hướng heap/GC/class/thread. | Attach, sampling, xuất stdout vẫn có overhead và yêu cầu quyền. |
| **2 — ghi thu thập nhẹ có thời hạn** | JFR `settings=default`, dump từ recording đang chạy, một số logging đã bật hoặc thay đổi có scope hẹp. | Có timestamp/stack/event nhiều chiều hơn để đối chiếu CPU, GC, I/O, contention. | Overhead, file size và event coverage phụ thuộc cài đặt; không bật tràn lan. |
| **3 — snapshot/điều tra có tác động vừa** | `jcmd <pid> Thread.print`, `VM.native_memory summary` nếu NMT đã bật, một số lệnh thống kê sâu. | Xác định nhóm thread BLOCKED/WAITING, locks, native-memory subsystem. | Thread count, attach cost, safepoint/VM operation và lượng output có thể đáng kể. |
| **4 — thu nặng, cần quyết định riêng** | `GC.class_histogram`, `GC.heap_dump`, heap statistics/path-to-GC-roots trong một số cấu hình JFR, profiler hoặc native/core dump chuyên sâu. | Xem class histogram, object graph, retained references, bằng chứng chi tiết cho leak. | Có thể pause mạnh, kích hoạt GC, I/O/disk lớn, yêu cầu bảo mật cao và ảnh hưởng triệu chứng. |

Các mức là **khung lựa chọn thực hành**, không phải API công bố chính thức. Theo tài liệu `jcmd` Java 17 của Oracle: `JFR.start` được ghi `Impact: Low`, `Thread.print` là `Medium` tùy số thread, còn `GC.class_histogram` và `GC.heap_dump` là `High` tùy heap. Lệnh `VM.native_memory` có mức `Medium`. Phải đọc help và rủi ro thực tế của đúng VM/host.

Một hành động ở mức cao vẫn **có thể đúng** khi cần bắt trạng thái trước khi tiến trình chết và hậu quả bỏ lỡ bằng chứng lớn hơn rủi ro thu thập. Nhưng phải nêu rõ quyết định, thời gian, mức ảnh hưởng dự kiến, nơi lưu, đường thoát và ai phê duyệt.

## 3. Bắt đầu bằng “incident envelope” và bằng chứng đã có

Trước khi chạy một lệnh tác động đến JVM, ghi lại khung incident:

- **Định danh:** service, môi trường, deployment version, instance/pod/container, host, PID, JVM vendor/version, collector, application uptime.
- **Cửa sổ:** thời điểm bắt đầu bất thường, timestamp có timezone, thời gian kéo dài, mốc triển khai hoặc cấu hình thay đổi gần nhất.
- **Ảnh hưởng:** request rate, throughput, p95/p99 latency, error/timeout/rejection, số user hoặc job bị tác động.
- **Tài nguyên:** CPU của host và tiến trình, RSS, giới hạn memory cgroup, heap used/committed/max, GC count/pause, disk free/inode, socket count, thread count.
- **Bằng chứng hiện hữu:** logs có correlation ID, traces, JFR đã chạy, GC log rotation, container events (ví dụ `OOMKilled`), cảnh báo autoscaling/restart.
- **Ràng buộc:** production có SLA latency nghiêm ngặt? JVM sắp bị restart? Có volume lưu trữ? Ai có quyền nhận HPROF/JFR?

Không cần thu hết một lượt. Chọn những metric trực tiếp phân biệt các giả thuyết. Ví dụ một process bị `OOMKilled` theo cgroup có thể **không hề phát sinh `java.lang.OutOfMemoryError` trong Java heap**, nên heap dump tự động chưa chắc có hoặc giúp ích; xem RSS/cgroup/native memory trước.

### Giữ tính đối chiếu

Đối với một metric, lưu **đúng instance và đơn vị**. Heap used sau GC, committed heap, RSS, container working set, native memory committed và reserved **không đồng nghĩa**. Không suy luận “Java heap leak” chỉ từ biểu đồ RSS tăng.

Tập hợp mốc **trước – trong – sau** khi có thể: ví dụ cùng một instance ở 10:00 (bình thường), 10:10 (bất thường), 10:20 (phục hồi). Không so hai instance có workload/JDK/heap flags khác nhau rồi khẳng định một JVM tăng memory.

## 4. Bước 0: metrics, logs và sự kiện vận hành đã tồn tại

Đây thường là nơi có tỷ lệ thông tin/chi phí tốt nhất. Tìm bằng chứng có sẵn mà không yêu cầu JVM đổi chế độ ghi:

| Triệu chứng | Chỉ số nên đọc trước | Gợi ý phân biệt |
| --- | --- | --- |
| Latency tăng | ingress latency, app handler duration, queue wait, thread pool active/queue, DB/client duration, error rate | Queue chờ nhiều hay code/I/O đang xử lý chậm? |
| CPU cao | process CPU vs host CPU, GC CPU/time, method samples nếu JFR có sẵn | CPU nằm trong application hot path, GC hay tiến trình khác? |
| Heap tăng | used sau GC, GC pauses, allocation rate, max/committed | Churn cấp phát hay retained live set đang tăng? |
| RSS tăng | RSS/cgroup limit, Java heap committed, thread count, direct buffer pools, metaspace, NMT nếu đã bật | Heap hay native memory đóng góp chính? |
| Thread treo | active vs idle threads, queue length, lock/DB pool waits, thread dump cũ nếu có | Chờ I/O/lock, backlog hay deadlock? |
| Process chết | exit code, `OOMKilled` event, Java exception/stderr, fatal error logs, disk capacity | JVM OOM có dump hay kernel kill/crash không kịp ghi? |
| Spike sau deploy | release timestamp, config diff, traffic mix, warmed-up state, GC/JFR sample trước đó | Regression ứng dụng hay thay đổi load/infra? |

**Không chỉ nhìn mức trung bình**. p99 latency có thể tăng rất mạnh trong khi average ổn định; tỷ lệ GC pause trên tổng thời gian nhỏ không loại trừ một số pause dài. Khi điều tra tail latency, cần time series hoặc event có timestamp, không chỉ một tổng count.

**Không lạm dụng log nội dung request** để “có nhiều bằng chứng hơn”. Log payload, header, token, SQL parameters hoặc PII có thể tạo rủi ro bảo mật lẫn I/O; chỉ bật field thật cần thiết với scope/retention phù hợp.

## 5. Bước 1: xác minh JVM, flags và metric nhẹ

Trên host hoặc namespace phù hợp, với JDK có `jcmd` và quyền attach đến JVM mục tiêu:

```bash
# Liệt kê JVM có thể nhìn thấy từ môi trường chạy lệnh
jcmd -l

# Thay <pid> bằng PID thực của đúng JVM
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.command_line
jcmd <pid> VM.flags

# Xem help đúng phiên bản JVM trước các thao tác mới
jcmd <pid> help
```

Lệnh `jcmd` phải nhắm đúng PID, host, user và quyền; trên container PID bên trong khác PID trên host. `jcmd -l` có thể không liệt kê JVM trong namespace container khác. **Không chạy `jcmd 0 ...` để gửi lệnh hàng loạt tới nhiều JVM** khi chỉ đang điều tra một service.

Một số command có thể in system properties hay command line chứa thông tin nhạy cảm như endpoint và đôi khi credentials; **chọn lọc trước khi lưu hoặc chia sẻ output**. `VM.flags` cho thấy JVM flags, `VM.command_line` cho thông tin khởi chạy, nhưng không phải mọi thay đổi runtime/application config đều thể hiện ở đây.

### 5.1. Quan sát GC trong cửa sổ ngắn

```bash
# 10 mẫu, cách nhau 1.000 ms
jstat -gcutil <pid> 1000 10

# Nếu cần thông tin class load/unload và tool có hỗ trợ
jstat -class <pid> 1000 10
```

`jstat -gcutil` cung cấp tỉ lệ sử dụng vùng nhớ và GC counters/elapsed thông qua performance instrumentation của HotSpot; cột cụ thể khác theo JDK/collector. Đây là **lấy mẫu trong khoảng 10 giây**, không phải tổng toàn bộ sự cố, và không chứng minh class/object nào đang leak. Cột percent không phải MiB; nếu cần số tuyệt đối, kiểm tra loại metric hoặc dùng JMX/GC logs.

`jstat` vẫn phải chạy với tần suất hợp lý; lặp hàng trăm tiến trình mỗi vài mili-giây là một workload giám sát riêng có thể làm méo số liệu. Thông số `1000 10` là **minh họa ít mẫu**, không phải cadence bắt buộc.

### 5.2. Những phép đọc có giới hạn

- `MemoryMXBean.getHeapMemoryUsage()` và `getNonHeapMemoryUsage()` cho snapshot managed-memory pools theo ngữ nghĩa Java MXBeans; **non-heap MXBean không đồng nghĩa tổng native RSS**.
- `ClassLoadingMXBean` báo loaded/unloaded classes.
- `ThreadMXBean.getThreadCount()` cho thread count tại lúc lấy mẫu; **không tạo thread dump**.
- `GarbageCollectorMXBean` cho collection count/time nếu collector cung cấp, nhưng GC time tổng hợp **không mặc nhiên là tổng pause time tuyệt đối** đối với các collector concurrent.

Metric đọc nhẹ có ích để thu **xu hướng**, nhưng không thể trả lời “object cụ thể nào giữ 2 GiB heap”. Chỉ chuyển sang dữ liệu chi tiết khi có câu hỏi về bản chất object/stack/lock mà các counters không đủ.

## 6. Java 17+ — lấy mẫu trạng thái nhẹ bên trong ứng dụng

Chương trình độc lập dưới đây chỉ gọi các **management MXBeans**, lấy hai mẫu cách nhau khoảng một giây, không yêu cầu full GC, heap dump hay thay đổi cờ JVM. Nó đo **chính JVM chạy chương trình**, hữu ích để hiểu mẫu số liệu; trên dịch vụ thật nên xuất những metric tương ứng qua monitoring/JMX được bảo vệ thay vì thêm một JVM mới rồi tưởng đang đo service khác.

Lưu `LowImpactSnapshot.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public final class LowImpactSnapshot {
    record Snapshot(long timestampNs,
                    long heapUsedBytes,
                    long heapCommittedBytes,
                    long nonHeapUsedBytes,
                    int threads,
                    int loadedClasses,
                    long gcCount) {}

    static Snapshot take() {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean thread = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        long totalGcCount = 0;
        boolean gcCountKnown = true;
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            long count = bean.getCollectionCount();
            if (count < 0) {
                gcCountKnown = false;
            } else {
                totalGcCount += count;
            }
        }

        return new Snapshot(
                System.nanoTime(),
                heap.getUsed(),
                heap.getCommitted(),
                nonHeap.getUsed(),
                thread.getThreadCount(),
                classes.getLoadedClassCount(),
                gcCountKnown ? totalGcCount : -1);
    }

    public static void main(String[] args)
            throws InterruptedException {
        Snapshot before = take();
        Thread.sleep(1000);
        Snapshot after = take();

        double elapsedSeconds =
                (after.timestampNs() - before.timestampNs())
                        / 1_000_000_000.0;
        double heapDeltaMiB =
                (after.heapUsedBytes() - before.heapUsedBytes())
                        / (1024.0 * 1024.0);

        System.out.printf(
                "elapsed=%.3fs heapDelta=%.2fMiB%n",
                elapsedSeconds, heapDeltaMiB);
        System.out.printf(
                "heapCommitted=%dKiB nonHeapUsed=%dKiB%n",
                after.heapCommittedBytes() / 1024,
                after.nonHeapUsedBytes() / 1024);
        System.out.printf(
                "threads=%d->%d loadedClasses=%d->%d%n",
                before.threads(), after.threads(),
                before.loadedClasses(), after.loadedClasses());

        if (before.gcCount() >= 0 && after.gcCount() >= 0) {
            System.out.println(
                    "gcCountDelta=" +
                    (after.gcCount() - before.gcCount()));
        } else {
            System.out.println("gcCountDelta=unavailable");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac LowImpactSnapshot.java
java LowImpactSnapshot
```

Output có dạng:

```text
elapsed=1.001s heapDelta=0.10MiB
heapCommitted=16384KiB nonHeapUsed=5900KiB
threads=6->6 loadedClasses=835->844
gcCountDelta=0
```

**Các con số chỉ minh họa định dạng**; giá trị thực thay đổi theo JVM, JIT, lớp được nạp và scheduler. `Thread.sleep(1000)` không bảo đảm đúng 1,000 giây, nên chương trình báo thời gian thực đo bằng `nanoTime()`. Việc đọc nhiều MXBeans không phải snapshot nguyên tử, còn heap delta trong 1 giây không bằng allocation rate vì GC có thể đã thu hồi object trong khoảng đó.

Bài tập này chỉ cho thấy cách hỏi những câu ít tác động: “heap/non-heap đang biến động không?”, “thread và class count có tăng không?”, “có GC nào xảy ra giữa hai lần lấy mẫu?”. Để điều tra **một JVM đang chạy khác**, dùng công cụ/agent/monitoring kết nối đúng process; không suy diễn từ số liệu JVM của chương trình ví dụ.

## 7. Bước 2: JFR default hoặc tận dụng recording đã có

Java Flight Recorder là lựa chọn hợp lý khi metric cho biết “có bất thường” nhưng chưa biết **thời điểm và stack/loại hoạt động nào** tương quan với spike. JFR có thể cho sự kiện CPU, GC, thread, I/O, contention, class loading và application events tùy settings.

### 7.1. Ưu tiên recording đang chạy sẵn

Đầu tiên xem JVM có recording nào không:

```bash
jcmd <pid> JFR.check
jcmd <pid> help JFR.dump
```

Nếu có một recording tên thực tế, ví dụ `service_baseline`, có thể tạo **snapshot của dữ liệu đã thu**, không phải khởi động thêm một recording mới:

```bash
jcmd <pid> JFR.dump \
  name=service_baseline \
  filename=/var/diag/jfr/service-baseline-incident.jfr \
  maxage=5m
```

Đường dẫn là **ví dụ**, thư mục phải tồn tại và JVM đích có quyền ghi. `JFR.dump` **không dừng recording**; nó ghi tệp từ dữ liệu còn được giữ trong repository. `maxage=5m` giới hạn phần lịch sử cần dump nếu còn dữ liệu, không thể khôi phục event đã hết retention hoặc chưa từng được bật. Nếu đang chạy trong container, tệp thuộc filesystem/mount của **JVM đích**, không tự xuất hiện trên máy của operator.

Theo tài liệu Java 17, `JFR.dump` có mức `Impact: Low`, nhưng vẫn tốn I/O/dung lượng để ghi file và có thể gây ảnh hưởng khi host gần đầy disk. Không xem việc dump JFR như bằng chứng hoàn toàn “miễn phí”.

### 7.2. Nếu chưa có recording, bắt đầu có thời hạn

Trong một cửa sổ incident được phép, ví dụ **hai phút**:

```bash
jcmd <pid> JFR.start \
  name=triage_2m \
  settings=default \
  duration=120s \
  filename=/var/diag/jfr/triage-2m.jfr
```

`settings=default` thường phù hợp ghi nhẹ liên tục; `profile` thu nhiều sự kiện hơn và có overhead cao hơn, dùng cho cửa sổ ngắn khi thật sự thiếu bằng chứng. File được viết khi recording dừng theo cấu hình; nếu JVM bị kernel kill/crash trước đó hoặc filesystem lỗi, tệp hoàn chỉnh có thể không có. Không thay đổi các event thresholds xuống mức cực thấp chỉ để “thu tất cả” mà chưa đánh giá chi phí.

Trên máy có thể truy cập file vừa tạo:

```bash
jfr summary /var/diag/jfr/triage-2m.jfr
jfr print --events jdk.GarbageCollection \
  /var/diag/jfr/triage-2m.jfr
```

`jfr summary` cho biết event types/count/size và khoảng thời gian; nó không tự suy ra nguyên nhân gốc. `jfr print` in chi tiết các event được chọn; trên file lớn nên lọc để tránh tràn stdout/đĩa. Tên event phải có trong file và phụ thuộc JVM/settings; một recording trống về event mục tiêu không có nghĩa hoạt động đó chắc chắn bằng không.

### 7.3. Khi nào mới cân nhắc `profile` hoặc settings chi tiết?

Khi `default` đã cho bằng chứng rằng **CPU hotspot**, **allocation churn**, **I/O chờ dài** hoặc **lock contention** đáng nghi nhưng thiếu stack/mẫu, cân nhắc recording `profile` ngắn có phạm vi và quyền phê duyệt:

```bash
# Chỉ sau khi thống nhất mức ảnh hưởng và điều kiện dừng
jcmd <pid> JFR.start \
  name=profile_60s \
  settings=profile \
  duration=60s \
  filename=/var/diag/jfr/profile-60s.jfr
```

Không để nhiều recording profile chồng nhau không giới hạn. Tác động thực tế thay đổi theo ứng dụng; Oracle mô tả JFR default có chi phí thấp trong đa số trường hợp, nhưng **không có cam kết “overhead = 0%” cho mọi workload**. Heap statistics và path-to-GC-roots là những tính năng có thể tốn kém hơn nhiều: không bật chỉ vì muốn có mọi loại dữ liệu.

**Đánh giá chất lượng ghi:** đủ event? đủ khoảng thời gian xảy ra bất thường? event có sampling/threshold loại bỏ hoạt động ngắn? Có stack traces cần thiết? Nếu thiếu, tăng mức thu **có chủ đích**, không mở toàn bộ event ở mức tối đa.

## 8. Bước 3: thread dump khi vấn đề thật sự nằm ở thread/lock

Metrics + JFR nhẹ đôi khi chưa đủ để biết một nhóm thread cụ thể đang chờ lock, chờ `Future.get()`, network read hay executor queue. Một vài **thread snapshots có timestamp** có thể trả lời câu hỏi đó.

Trên HotSpot Java 17:

```bash
# Chỉ thực hiện khi đã phê duyệt mức tác động
jcmd <pid> Thread.print -l
```

Theo Oracle JDK 17, `Thread.print` có `Impact: Medium` và phụ thuộc số thread; tùy chọn `-l` thêm thông tin một số `java.util.concurrent` locks. Đọc lệnh qua `jcmd <pid> help Thread.print` nếu VM khác. **Không dùng thread dump như thao tác nhẹ hoàn toàn vô hại** trên dịch vụ có hàng chục nghìn thread.

Phương án hữu ích là chụp **2–3 lần cách nhau một khoảng có ý nghĩa** (ví dụ 5–10 giây, chỉ là kịch bản) nếu ứng dụng vẫn chịu được, thay vì một lần rồi khẳng định deadlock. Nếu cùng nhóm thread nằm ở cùng stack/lock qua nhiều mốc, bằng chứng mạnh hơn một snapshot đơn. Đừng dùng vòng lặp vô hạn `jcmd Thread.print` gây thêm tải và làm đầy disk.

### Đọc thread dump đúng

| Quan sát | Có thể là gì | Không được suy diễn ngay |
| --- | --- | --- |
| Nhiều thread ở `WAITING` | Worker nhàn rỗi đang chờ việc, hoặc đợi condition/future. | “Tất cả thread đang chết”. |
| Nhiều thread `BLOCKED` tại cùng monitor | Lock contention trong một vùng code. | “Có deadlock” nếu chưa thấy chu kỳ khóa hoặc JVM phát hiện deadlock. |
| Worker chờ `SocketInputStream`/NIO/read | Chờ I/O hoặc downstream. | “CPU cao do method read”. |
| Thread pool queue tăng và active threads tối đa | Có khả năng saturation/backlog. | “Chỉ cần tăng thread là khỏi”, bỏ qua DB pool/CPU limit. |
| Cùng một stack nhiều lần | Nghi stuck operation hoặc hoạt động lặp. | “Chắc chắn bug” nếu thread đang xử lý job lâu hợp lệ. |

**Thời điểm thread dump có tác động đến hành vi**: nếu hệ thống đang stress, việc chụp có thể kéo dài/đổi timing; so với latency spike thời điểm đó, kết hợp metrics và traces. Thread dump cũng có thể chứa URL, file path, SQL/stack liên quan dữ liệu nội bộ; lưu quyền hạn phù hợp.

Với JDK mới có virtual threads, công cụ dump có thể khác với Java 17. Đừng bê nguyên lệnh `Thread.dump_to_file` của JDK 21 vào hệ thống JDK 17 nếu lệnh không có trong `jcmd <pid> help`.

## 9. Khi nghi vấn nằm ở native memory

Một dịch vụ có RSS tăng nhưng Java heap used sau GC ổn định cần xem **thread stacks, direct buffers, metaspace, JIT/code cache, GC/native allocations** hoặc container accounting trước khi kết luận Java heap leak.

Nếu **Native Memory Tracking (NMT) đã được bật từ lúc khởi động**:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

NMT có thể được bật bằng `-XX:NativeMemoryTracking=summary` hoặc `detail` khi khởi động JVM; cần hiểu overhead từ thời điểm bật. Nếu NMT **không được bật**, lệnh runtime không thể tự cung cấp lại lịch sử native allocation đã không được theo dõi. Đừng yêu cầu restart production chỉ để có NMT khi chưa phân tích các metric sẵn có.

Khi đã có NMT và cần so sánh theo thời gian, trong phạm vi cho phép:

```bash
# Đánh dấu mốc gốc
jcmd <pid> VM.native_memory baseline

# Sau khoảng thời gian cần quan sát
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Theo tài liệu `jcmd` JDK 17, `VM.native_memory` có mức `Impact: Medium`. NMT có thể làm rõ nhóm memory trong HotSpot nhưng **không bao quát mọi allocation** từ thư viện native bên ngoài JVM. Và **reserved ≠ committed ≠ RSS**; không cộng “reserved” làm RAM vật lý đã sử dụng.

Bật `-XX:NativeMemoryTracking=detail` cho lần deploy sau là thay đổi cấu hình có overhead lớn hơn `summary`. Chỉ làm sau khi đã quyết định muốn truy callsite native nào và đã thử/đánh giá trên môi trường phù hợp.

## 10. Khi nào histogram là bước hợp lý hơn heap dump?

Nếu dữ liệu trước đó cho thấy **Java heap used sau GC tăng bền vững**, cần biết nhóm class nào chiếm bộ nhớ; histogram có thể là bước trung gian trước khi quyết định chụp toàn bộ HPROF:

```bash
# Tác động HIGH: không dùng như lệnh kiểm tra "nhẹ"
jcmd <pid> GC.class_histogram
```

`GC.class_histogram` thống kê số object và dung lượng theo class, nhưng không cho quan hệ tham chiếu/dominator. Kết quả có thể cho biết `byte[]`, `HashMap$Node` hay một kiểu cache xuất hiện nhiều; nó **không chứng minh object nào bị leak** hoặc GC root nào giữ chúng.

Quan trọng: Oracle đánh dấu `GC.class_histogram` là **High impact**, phụ thuộc heap. Nó có thể giữ JVM ở trạng thái phải kiểm tra lượng lớn object và tạo output lớn. Đừng đưa vào “mức thấp” chỉ vì output là text thay vì file HPROF. Tùy chọn `-all` (khi VM hỗ trợ) bao gồm cả các object unreachable; điều đó có thể gây hiểu nhầm rằng mọi object đều đang live. Cần so đối chiếu chính xác collection policy và thời điểm.

**Quyết định có chụp histogram không:** chỉ nên thực hiện khi ta cần **phân bố object theo class**, tác động phù hợp với tình hình, thread/GC/JFR nhẹ chưa trả lời câu hỏi và có phương án xử lý output an toàn.

## 11. Khi nào thật sự cần heap dump?

Heap dump `.hprof` chứa object graph, hữu ích khi mục tiêu là tìm **đường giữ tham chiếu**, dominator tree, retained size, class loader/retention hoặc một dạng leak Java heap không thể giải thích bằng histogram và metric.

Ví dụ HotSpot JDK 17:

```bash
# HIGH impact, cần đúng đường dẫn/quyền/dung lượng và phê duyệt
jcmd <pid> GC.heap_dump /var/diag/heap/incident-001.hprof
```

Theo tài liệu Oracle JDK 17, `GC.heap_dump` là **High impact** và **yêu cầu full GC trừ khi có tùy chọn `-all`**. Full GC có thể thay đổi chính object population bạn muốn quan sát; `-all` ghi cả object unreachable và không phải một công tắc “không có tác động”. HPROF có thể có dung lượng hàng GiB; không mặc định bằng `-Xmx`. Nếu đang gần cgroup memory/disk limit, thao tác có thể làm hệ thống hỏng nặng hơn hoặc file được ghi dở.

### Checklist go/no-go trước heap dump

- [ ] **Giả thuyết rõ:** đang tìm retained references trong Java heap, không phải native RSS, network timeout hay container `OOMKilled` không có Java OOM?
- [ ] **Bằng chứng đã có:** đã so after-GC baseline/GC logs, classloader/class counts hoặc JFR phù hợp; xác nhận thông tin nào chỉ object graph mới cung cấp?
- [ ] **Tính cấp thiết:** có nguy cơ mất cơ hội điều tra do tiến trình sắp chết? Có replica/staging có thể tái hiện ít ảnh hưởng hơn?
- [ ] **Impact:** chấp nhận được pause/Full GC? Ai phê duyệt? Có kế hoạch hủy việc thu hoặc failover nếu SLO xấu đi?
- [ ] **Storage:** thư mục có sẵn, quyền ghi bằng user chạy JVM, đủ quota/inode, không dùng tên file đã tồn tại; đo free disk trên **đúng mount**.
- [ ] **Container:** file được lưu trên volume phù hợp để không mất khi pod bị thay thế? Giới hạn I/O và ephemeral storage?
- [ ] **Bảo mật:** dump có thể chứa secret/PII; chỉ người được phép đọc, mã hóa khi truyền/lưu, retention và xóa có nhật ký.
- [ ] **Phân tích:** có công cụ như Eclipse MAT/VisualVM, máy phân tích đủ RAM và kế hoạch đối chiếu timestamp/JFR/GC logs không?

Nếu đa số câu trả lời chưa rõ, **chưa nên chụp** chỉ vì đã có sẵn lệnh. Một heap dump khó mở, không đúng instance, không còn log/metrics để đối chiếu hoặc làm đầy đĩa production có thể đem lại ít giá trị hơn chi phí gây ra.

### Khi gặp OOM thì sao?

`-XX:+HeapDumpOnOutOfMemoryError` cùng `-XX:HeapDumpPath=...` có thể tạo dump khi **JVM xử lý những loại `OutOfMemoryError` phù hợp**. Hai cờ này thường được thiết lập trước lúc khởi động. Chúng **không bảo đảm** có HPROF khi kernel/cgroup kill JVM (`OOMKilled`/`SIGKILL`), mất quyền ghi, đầy đĩa hoặc tiến trình crash trước khi hoàn tất.

Đừng gây OOM trên production chỉ để kiểm tra cơ chế dump. Kiểm tra chức năng trên staging cùng image, user, mount/quota tương đương. Nếu production không có dump sau sự cố, trước tiên xem **JVM OOM hay OS kill**, log báo dump, container events và mount/retention — không tự suy luận không có leak.

## 12. Cấu hình chi tiết: thay đổi nhỏ, có thời hạn và có đường quay lại

Một số loại vấn đề không đủ bằng chứng khi settings mặc định quá thưa. Có thể cần:

- Tăng mức chi tiết của **một nhóm JFR event** như `jdk.SocketRead` hoặc `jdk.JavaMonitorEnter` trong cửa sổ ngắn, thay vì bật tất cả event.
- Thêm stack traces/sampling cho một nghi vấn cụ thể, nhớ overhead sẽ thay đổi theo event rate và threshold.
- Bật **GC unified logging** có rotation trong lần deploy sau hoặc thay đổi runtime logging **chỉ khi JVM hỗ trợ và có phê duyệt**, tránh ghi log liên tục mức `trace`.
- Bật NMT `summary` khi khởi động cho incident có tính lặp lại; chỉ dùng `detail` khi cần native callsites và đã đo overhead.
- Chụp thêm heap dump/diagnostic artifact nặng chỉ khi mức bằng chứng nhẹ không thể trả lời câu hỏi nguyên nhân.

Trước khi thay cấu hình, ghi **trạng thái ban đầu**, thời gian bắt đầu/kết thúc, phạm vi instance, người thực hiện, disk/CPU budget, điều kiện tự dừng, cách restore. Không “nâng hết flags cho chắc”; mỗi thay đổi có thể ảnh hưởng cả symptom và độ tin cậy của phép đo.

Ví dụ **chỉ xem** cấu hình Unified Logging đã có:

```bash
jcmd <pid> VM.log list
```

Lệnh `VM.log` có khả năng thay đổi cấu hình logging khi truyền options thích hợp; phần ví dụ chỉ liệt kê. Để bật thêm tags hoặc đổi output, xem `jcmd <pid> help VM.log` và thử trên môi trường tương thích. Không gửi một lệnh cấu hình động chưa kiểm tra sang toàn bộ fleet.

### JFR heap statistics và GC roots không phải lựa chọn đầu tiên

Bật **Heap Statistics** trong JFR hoặc tùy chọn `path-to-gc-root` có thể tạo thêm công việc và pause. Oracle cảnh báo Heap Statistics có thể gây overhead đáng kể do việc thu heap statistics liên quan GC; các tùy chọn GC root cũng chỉ nên bật khi đang điều tra suspected memory leak. Không bật `path-to-gc-root=true` cho mọi recording chỉ vì file có thêm “chi tiết”.

Muốn biết **allocation churn** thì JFR samples/metrics có thể đủ; muốn biết **retained object graph** mới cân nhắc heap dump. Hai câu hỏi khác nhau, và một loại artifact không nên được kỳ vọng giải thích hoàn toàn loại kia.

## 13. Thu bằng chứng theo nhóm sự cố: ba playbook minh họa

### A. p99 latency tăng nhưng CPU không cao

1. Đọc request latency breakdown, thread pool queue/active, connection pool pending, socket/database metrics và logs hiện có.
2. Nếu thấy nhiều worker đợi downstream, dùng JFR `default`/recording sẵn có để xem I/O, contention và timestamp (chú ý threshold có thể bỏ event ngắn).
3. Nếu vẫn không biết thread nào đang giữ lock/wait, cân nhắc **một số thread dump** có điều kiện, so giữa các mốc.
4. **Không chụp heap dump** chỉ vì latency cao nếu không có tín hiệu memory/retention.

Dấu hiệu như `ThreadPark` hoặc `SocketRead` là hướng điều tra, không tự động kết luận code sai. Một số thread đang `WAITING` là bình thường nếu chúng là idle workers.

### B. RSS tiến sát container limit, heap sau GC ổn định

1. Xem RSS/cgroup memory, container events, `-Xmx` và heap committed, số thread, direct buffer/metaspace metrics hiện có.
2. Nếu NMT đã bật, đọc `VM.native_memory summary` và so với baseline; kiểm tra reserved vs committed.
3. Nếu nghi native allocations ngoài phạm vi HotSpot NMT, chuyển sang OS/native tooling có phê duyệt, không cố dùng HPROF để giải thích toàn bộ RSS.
4. Chỉ cân nhắc heap dump nếu có **bằng chứng Java heap retention** hoặc cần truy đối tượng liên quan tới native buffers/classloaders.

Tăng `-Xmx` theo phản xạ có thể khiến container bị kill sớm hơn vì giảm headroom cho bộ nhớ native.

### C. Heap after-GC tăng đều qua nhiều giờ

1. Thu chuỗi thời gian after-GC heap used, allocation rate, GC frequency/pause, workload và các deploy gần nhất.
2. Dùng JFR sẵn có hoặc `settings=default` để tương quan GC, class loading, allocation samples khi được bật.
3. Nếu nghi nhiều object thuộc một số class và cần định hướng, cân nhắc histogram **High impact** khi có cửa sổ phù hợp.
4. Nếu câu hỏi là “điều gì giữ object này không được GC”, quyết định heap dump theo checklist go/no-go rồi mở bằng MAT để xem dominator tree và path to GC roots.
5. Nếu leak chỉ xuất hiện ở staging có thể tái hiện, ưu tiên thu artifact nặng tại đó để bảo vệ production.

Đừng coi mọi biểu đồ heap dạng răng cưa hoặc mọi sự tăng trong giai đoạn warm-up là leak. Xem mức **sau chu kỳ GC có tính so sánh**, không chỉ peak trước khi GC.

## 14. Chọn công cụ theo câu hỏi, không theo thói quen

| Câu hỏi điều tra | Bằng chứng đủ nhẹ cần thử trước | Chỉ nâng mức thu khi... |
| --- | --- | --- |
| JVM có chạy đúng flags và version? | `VM.version`, `VM.flags`, `VM.command_line`. | Hiếm khi cần heap/thread dump cho câu hỏi này. |
| Có GC pause/heap trend đáng ngại? | Dashboard + GC log hiện có + `jstat`/JFR default. | Cần phân bố object/GC roots cụ thể. |
| CPU hotspot thuộc method nào? | JFR execution samples trong recording phù hợp. | Sampling không đủ, phải chẩn đoán có profiler chi tiết hơn. |
| Task chậm do I/O hay lock? | Traces, queue wait, DB/socket metrics, JFR I/O/contended events. | Cần snapshot stack thread để xác thực block cụ thể. |
| Metaspace/classloader tăng? | Class loading/Metaspace metrics, `VM.classloader_stats` nếu phù hợp. | Muốn tìm root giữ loader hoặc metadata retention cụ thể. |
| Native RSS tăng? | OS/cgroup + heap committed + NMT nếu đã bật. | Cần native profiler hoặc core dump, theo quy trình riêng. |
| Java heap leak, object nào giữ bộ nhớ? | After-GC trend + JFR allocations + histogram nếu phù hợp. | Chỉ object graph/retained-size mới trả lời được. |
| Process đột ngột biến mất? | Kernel/container events, stderr/fatal logs, exit code. | Xác nhận loại lỗi trước khi quyết định dump. |

Một bảng dashboard không phải kết luận; một HPROF cũng không phải kết luận. **Các nguồn bằng chứng cần hỗ trợ hoặc bác bỏ nhau**. Nếu metric bảo “CPU 100%” nhưng JFR CPU samples rất ít, kiểm tra file có ghi đúng cửa sổ hay không, sampling/threshold, host vs JVM CPU, số instance và timezone trước khi khẳng định tool nào sai.

## 15. Không để công cụ chẩn đoán làm mất dịch vụ

### 15.1. Những tình huống cần thận trọng đặc biệt

- **Memory/cgroup sắp hết:** một dump/recording có thể tăng I/O/storage hoặc CPU; kernel có thể kill tiến trình giữa chừng.
- **Disk gần đầy:** JFR/GC log/heap dump có thể tiêu thụ volume chứa ứng dụng hoặc log quan trọng.
- **Độ trễ rất nhạy:** snapshot yêu cầu safepoint/Full GC có thể phá vỡ SLO.
- **Nhiều replica đồng thời:** chạy diagnostic nặng trên mọi replica có thể gây incident diện rộng; ưu tiên giới hạn một replica/cửa sổ khi được phép.
- **Hệ thống có autoscaling/restart:** tệp sinh trong container ephemeral có thể biến mất; cần mount/thu chuyển an toàn.
- **Dữ liệu nhạy cảm:** heap dump/recording/thread dump có thể lộ token, path và nội dung đối tượng.
- **Không rõ JVM/vendor:** lệnh khác nhau, impact/hỗ trợ khác nhau; đừng dùng tham số được chép từ phiên bản khác.

Trong tình huống nguy cấp, **ổn định dịch vụ và giữ bằng chứng hiện có** có thể ưu tiên hơn việc cố thu artifact nặng. Nếu cần restart/failover, lưu số liệu sẵn có và thời điểm quyết định; không hứa lấy lại dữ liệu chưa được thu.

### 15.2. Nguyên tắc “thu ít nhưng tái hiện được”

Mỗi lần thu nên kèm một manifest tối thiểu:

```text
incident: INC-2026-042
service/instance: inventory-api / pod-7c8f...
JVM: OpenJDK 17.x, PID 1234, G1
window: 2026-10-29T09:15:00Z .. 2026-10-29T09:17:00Z
symptom: p99 latency increased, errors 1.2% (illustrative)
artifact: triage-2m.jfr
command: jcmd 1234 JFR.start name=triage_2m settings=default duration=120s ...
scope/overhead: one JVM, two-minute default recording
time_zone: UTC
owner/approval: authorized operations contact
storage/retention: restricted incident storage; delete per policy
```

Tất cả giá trị ở đây là **ví dụ**, không phải incident thật. Manifest giúp xác định đúng file thuộc đúng phiên bản/instance, tránh nhầm recording của replica khác. Lưu checksum sau khi chuyển file nếu cần chứng minh không thay đổi; không đưa dump hoặc config chứa secret vào Git hay ticket công khai.

### 15.3. Cách đánh giá ảnh hưởng quan sát được

Trong khi chạy một diagnostic có tác động hơn mức 0, xem:

- p95/p99 latency và error/timeout/rejection so với khoảng trước, theo cùng instance.
- CPU user/system, GC pause/time, heap allocation, RSS/cgroup và disk I/O.
- Dung lượng file đang được tạo, free disk/inode, network transfer nếu có.
- Thời điểm bắt đầu/đóng diagnostic; event nào tăng đúng từ lúc thu mới?
- Có dấu hiệu disk pressure, container eviction/restart hoặc dữ liệu hỏng không?

Không khẳng định “lệnh A gây spike” chỉ vì xảy ra gần thời điểm A; nhưng nếu tín hiệu xấu đi đồng thời, phải có **điều kiện dừng** và khả năng quay lại trước khi làm thêm. Tham số `duration`/`maxage`/`maxsize` giúp giới hạn một số recording nhưng không thay thế giám sát thực tế.

## 16. Tính toàn vẹn của bằng chứng: tránh suy luận từ dữ liệu thiếu

Một ảnh chụp có thể **đúng** nhưng **không đại diện**:

- Một thread dump chỉ cho biết trạng thái thread **tại thời điểm thu**; thread có thể đang idle giữa hai đợt nghẽn.
- JFR recording ngắn có thể bỏ qua spike trước khi recording bắt đầu; JFR `default` có event threshold và sampling.
- Histogram là phân bố object tại một snapshot, không cho path to roots và có thể chịu ảnh hưởng GC.
- HPROF có thể được ghi **sau full GC**, object ngắn hạn đã biến mất; file không kể lại toàn bộ allocation history.
- NMT là những khoản theo dõi của HotSpot, không thể xem nó là toàn bộ RAM/container memory.
- Metrics aggregate trong một phút che mất một spike 200 ms; tăng tần suất lấy mẫu cũng có chi phí.
- File `.jfr`/`.hprof` có tên đúng nhưng có thể bị **cắt dở** vì full disk, quyền, kill, crash; cần kiểm tra dung lượng và có mở được không.

Báo cáo nên ghi rõ “bằng chứng quan sát được trong cửa sổ X cho thấy…” thay vì “chắc chắn nguyên nhân” nếu chưa có dữ liệu phân biệt các giả thuyết.

### Đối chiếu hai mốc không đồng nghĩa hai lần đo là nguyên tử

Nếu đọc heap, threads, class count và GC counters tuần tự bằng MXBeans, các số có thể được lấy ở những microtime khác nhau. Không giả định tập metric của một lần scrape là snapshot đồng thời của toàn JVM. Với nhiều JVM/máy, đồng bộ thời gian, ghi timezone và biết sai số của clock; không lấy `System.nanoTime()` từ JVM A trừ của JVM B.

## 17. Một quy trình quyết định escalation có thể dùng lại

```text
Triệu chứng mới / cảnh báo
         │
         ▼
Xác định service/PID/instance + rủi ro + time window
         │
         ▼
Đọc metrics/logs/traces/cgroup và recording đã tồn tại
         │
         ▼
Có giả thuyết đủ cụ thể để hành động?
    ┌────┴────┐
   Có        Chưa
    │          │
    ▼          ▼
Xác minh bằng  Bổ sung metric/snapshot nhẹ hoặc JFR default
bằng chứng sẵn có     │
    │                ▼
    │           Có tín hiệu mới?
    │                │
    └────────────┬───┘
                 ▼
Thiếu điều gì chỉ loại bằng chứng sâu hơn mới trả lời?
                 │
         ┌───────┴────────┐
         │                │
      Không              Có
         │                │
         ▼                ▼
Kết luận trong phạm vi   Đánh giá impact, dữ liệu, disk,
dữ liệu hiện có         quyền, approval, stop condition
         │                │
         │       ┌────────┴────────┐
         │      No-go            Go
         │       │                │
         │       ▼                ▼
         │   Hoãn/escalate   Thu targeted artifact
         │                    đúng một lần/cửa sổ
         │                         │
         └─────────────────────────┤
                                   ▼
                   Kiểm chứng file + tương quan timestamps
                                   │
                                   ▼
                        Báo cáo giả thuyết + giới hạn
```

Quy trình không bắt buộc luôn đi đủ mọi cấp. Một sự cố được giải thích rõ bởi metrics và trace thì **dừng ở bằng chứng nhẹ**. Nếu JVM có nguy cơ chết trước khi đội vận hành lấy được object graph, có thể chọn dump sớm sau khi cân rủi ro/phê duyệt. Điểm quan trọng là **quyết định có lý do**, không thu dữ liệu nặng theo thói quen.

## 18. Những nhầm lẫn thường gặp

- **“Muốn debug thì cứ heap dump trước.”** Sai: heap dump không giúp trực tiếp cho mọi lỗi CPU, I/O, lock hay cgroup kill; nó có High impact.
- **“Thread dump chỉ là text nên chắc Low impact.”** Sai: `Thread.print` được Oracle JDK 17 ghi Medium, phụ thuộc thread count.
- **“Histogram nhỏ hơn HPROF nên rẻ.”** Không nhất thiết: `GC.class_histogram` vẫn là High impact.
- **“JFR luôn overhead 0%.”** Sai: `default` thường thấp nhưng phụ thuộc workload và event settings; `profile`/heap statistics có thể nặng hơn.
- **“`JFR.dump` chạy là có mọi event đã xảy ra.”** Sai: chỉ có event đã được bật và còn trong retention.
- **“`jstat -gcutil` cho chính xác object gây leak.”** Sai: đây là các counters/ratios, không phải object graph.
- **“RSS bằng heap used.”** Sai: RSS gồm nhiều thành phần khác; native memory phải được xem riêng.
- **“NMT không bật vẫn xem lại mọi native allocation quá khứ.”** Sai: phải bật tracking từ startup để có dữ liệu tương ứng.
- **“Heap dump bao giờ cũng ghi mà không đổi trạng thái heap.”** Sai: `GC.heap_dump` mặc định yêu cầu Full GC trên HotSpot JDK 17, trừ khi dùng `-all`.
- **“`-all` khiến dump không có chi phí.”** Sai: nó đổi phạm vi object, không biến high-impact operation thành low-impact.
- **“Có HPROF là xác định được lỗi ở dòng code.”** Sai: phải tìm retained paths/GC roots và đối chiếu nghiệp vụ; dump không phải allocation-history profiler.
- **“Một snapshot chứng minh được xu hướng.”** Sai: cần time series, workload/cửa sổ và tính tương đương.
- **“Có thể chạy cùng lệnh trên mọi pod.”** Nguy hiểm: nhiều diagnostic cùng lúc có thể đẩy incident diện rộng; giới hạn target.
- **“Không cần kiểm tra disk vì chỉ chụp một lần.”** Sai: file lớn có thể làm đầy volume hoặc vi phạm quota.
- **“Dump không chứa dữ liệu nhạy cảm.”** Sai: JFR, heap/thread dump và command-line output có thể chứa thông tin cần bảo vệ.
- **“Không có file nghĩa là JVM không có vấn đề.”** Sai: file có thể ghi lỗi, bị kill, bị mất sau restart hoặc dùng sai path.
- **“Hễ có thêm dữ liệu thì chẩn đoán chính xác hơn.”** Không luôn đúng: dữ liệu ồn, sampling không tương thích và overhead làm méo hệ thống có thể khiến suy luận sai.

## 19. Checklist trước, trong và sau thu bằng chứng

**Trước khi thu:**

- [ ] Ghi lại câu hỏi/giả thuyết, instance/PID, thời gian và mức tác động dịch vụ.
- [ ] Đọc dữ liệu đã có: metrics, log, traces, GC/JFR recording, OS/cgroup events.
- [ ] Chọn loại bằng chứng **ít ảnh hưởng nhất** đủ để trả lời câu hỏi tiếp theo.
- [ ] Kiểm tra đúng JDK, quyền attach, namespace, path, storage, privacy.
- [ ] Nếu thao tác Medium/High impact: có approval, giới hạn thời gian, resource budget, stop condition và kế hoạch failover?
- [ ] Bảo đảm không vô tình kích hoạt Full GC hoặc logging quá chi tiết.

**Trong khi thu:**

- [ ] Gắn timestamp, timezone, target và command để đối chiếu.
- [ ] Theo dõi p99/errors/GC/RSS/disk để phát hiện tác động chẩn đoán.
- [ ] Không lặp lệnh nặng hoặc mở file lớn vô thời hạn; không chạy trên toàn fleet.
- [ ] Không gửi dữ liệu chứa secret/PII vào nơi công khai.

**Sau khi thu:**

- [ ] Xác nhận artifact đã ghi hoàn chỉnh, đúng JVM/instance/cửa sổ và mở đọc được.
- [ ] Ghi lại version, flags, settings/sampling/threshold và những gì file **không** chứa.
- [ ] Phân tích đúng giả thuyết: timeline/stack với JFR, thread state với thread dumps, retained graph với HPROF.
- [ ] So lại metrics trước–trong–sau để ước lượng ảnh hưởng của chính thao tác thu.
- [ ] Khôi phục logging/profiling tạm thời, dọn file theo retention và bảo vệ evidence.
- [ ] Báo cáo **kết luận có phạm vi**, mức tin cậy và bước tiếp theo, không suy luận từ dữ liệu thiếu.

**Ghi nhớ:** hành động chẩn đoán tốt nhất không phải hành động thu nhiều dữ liệu nhất, mà là **hành động có giá trị thông tin cao với tác động chấp nhận được**. Bắt đầu từ telemetry đã có, thêm counters/short JFR recording, chỉ dùng thread dump/histogram/heap dump khi biết chính xác loại bằng chứng cần tìm. Việc giữ dịch vụ ổn định, định danh đúng phiên bản và bảo vệ artifact là một phần của kỹ năng chẩn đoán Java, không phải việc làm sau cùng.

### Tài liệu tham khảo

- [Oracle JDK 17 — jcmd: impact của từng diagnostic command, JFR.start/JFR.dump, Thread.print, GC.class_histogram và GC.heap_dump](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — jstat: lấy mẫu GC/class counters](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html)
- [Oracle JDK 17 — jfr: summary/print để đọc recording](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle JDK 17 — Troubleshoot Performance Issues Using Flight Recorder: overhead, thresholds, sampling và heap statistics](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 17 — Java Management Extensions / MXBean API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/module-summary.html)
- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328)