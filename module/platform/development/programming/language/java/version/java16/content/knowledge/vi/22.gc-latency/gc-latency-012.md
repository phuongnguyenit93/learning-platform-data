# Kiểm chứng p95, p99, allocation rate và RSS trước khi đổi cấu hình GC

Khi ứng dụng có latency spike hoặc dùng nhiều bộ nhớ, không nên đổi Garbage Collector (GC), tăng heap hay thêm JVM flags chỉ từ một biểu đồ. Trước tiên cần thu thập baseline trong workload đại diện và đặt các chỉ số vào cùng một trục thời gian: latency p95/p99, allocation rate, GC/safepoint activity và resident memory của tiến trình.

Bốn nhóm số liệu trả lời bốn câu hỏi khác nhau:

- **p95/p99:** request chậm tới mức nào ở phần đuôi phân phối?
- **Allocation rate:** ứng dụng tạo object nhanh tới mức nào?
- **GC metrics:** JVM phải thu gom bao lâu, thường xuyên ra sao và pause ở phase nào?
- **RSS:** bao nhiêu bộ nhớ của tiến trình đang resident trong RAM theo cách hệ điều hành đo?

Allocation rate cao không tự động có nghĩa heap bị leak; RSS cao không tự động có nghĩa heap quá nhỏ; p99 cao cũng không tự động do GC. Chỉ thay đổi cấu hình sau khi dữ liệu cho thấy nguyên nhân có liên hệ rõ với GC và sau khi có phép đo trước/sau trên cùng workload.

## 1. Xác định câu hỏi và SLO trước khi đo

Trước khi chạy benchmark hoặc đọc dashboard, hãy xác định:

- SLO latency áp dụng cho endpoint nào và ở mức tải nào.
- p95/p99 đang đo từ thời điểm nào đến thời điểm nào: từ lúc nhận request, sau queue, trong handler hay toàn bộ round-trip.
- Throughput mục tiêu, concurrency, tỷ lệ lỗi và timeout.
- Cửa sổ đo steady-state, peak, burst hay soak test.
- JDK vendor/build, collector, heap settings, CPU quota và giới hạn bộ nhớ container.

Ví dụ: p99 450 ms của một API có thể bao gồm 300 ms chờ queue, 80 ms xử lý nghiệp vụ và 70 ms GC/scheduling/network. Nếu chỉ đo thời gian bên trong handler, bạn sẽ bỏ qua queue delay. Nếu chỉ nhìn GC log, bạn có thể nhầm một pause trùng thời điểm với nguyên nhân thực sự.

Định nghĩa latency end-to-end thống nhất ở client hoặc gateway, rồi bổ sung metric server-side để chia nhỏ thời gian. Ghi rõ đơn vị và phạm vi của từng biểu đồ.

## 2. Lập baseline có thể so sánh

Baseline chỉ có ý nghĩa khi lần chạy trước và sau dùng cùng điều kiện:

1. Cùng artifact, cấu hình nghiệp vụ và phiên bản thư viện.
2. Cùng JDK vendor/build, JVM flags và GC collector ban đầu.
3. Cùng máy hoặc cùng loại instance, CPU quota, RAM và giới hạn container.
4. Cùng payload distribution, số client, concurrency và tốc độ request.
5. Tách startup/warm-up khỏi measurement steady-state.
6. Đo nhiều lần, đủ lâu để quan sát cả GC cycle và tail latency.
7. Ghi throughput, error rate, timeout và queue depth cùng latency.

Nên có các pha workload riêng:

| Pha | Mục đích |
| --- | --- |
| Startup | Xem chi phí khởi tạo, class loading và thời gian sẵn sàng. |
| Warm-up | Cho JIT, cache và pool ổn định trước khi lấy baseline. |
| Steady-state | Đo hành vi ở tải thường xuyên. |
| Peak/burst | Quan sát queueing, allocation spike và tail latency khi tải tăng. |
| Soak | Phát hiện xu hướng tăng heap, RSS hoặc class metadata theo thời gian. |

Không gộp startup với steady-state nếu mục tiêu là tối ưu latency request. Ngược lại, nếu SLO có tính cả cold start, hãy đo cold start như một chỉ số riêng.

## 3. Đo p95 và p99 bằng histogram

Average không cho biết phần đuôi của phân phối. Một ứng dụng có p50 tốt nhưng p99 rất cao vẫn có thể vi phạm SLO với một nhóm request đáng kể.

- **p50:** median; 50% sample có latency nhỏ hơn hoặc bằng giá trị này.
- **p95:** 95% sample có latency nhỏ hơn hoặc bằng giá trị này.
- **p99:** 99% sample có latency nhỏ hơn hoặc bằng giá trị này.
- **Max:** sample chậm nhất; nhạy với outlier và thời lượng đo.

Ghi từng request vào histogram thay vì chỉ cộng thời gian rồi chia số request. Histogram giữ thông tin phân phối và giúp theo dõi tail mà không cần lưu mọi sample thô.

Ví dụ với thư viện HdrHistogram:

```java
import org.HdrHistogram.Histogram;
import java.util.concurrent.TimeUnit;

class RequestLatencyRecorder {
    private final Histogram histogram =
        new Histogram(TimeUnit.SECONDS.toNanos(30), 3);

    void measureOneRequest(Runnable request) {
        long start = System.nanoTime();
        request.run();
        long elapsed = System.nanoTime() - start;
        histogram.recordValue(elapsed);
    }

    void printPercentiles() {
        System.out.printf(
            "p50=%.2f ms, p95=%.2f ms, p99=%.2f ms%n",
            histogram.getValueAtPercentile(50.0) / 1_000_000.0,
            histogram.getValueAtPercentile(95.0) / 1_000_000.0,
            histogram.getValueAtPercentile(99.0) / 1_000_000.0
        );
    }

    void resetAfterWarmup() {
        histogram.reset();
    }
}
```

Đoạn code minh họa cho một luồng ghi; trong ứng dụng concurrent, dùng histogram riêng theo worker rồi merge, hoặc recorder/concurrency mechanism phù hợp của thư viện để tránh lock contention làm méo kết quả. Chỉ gọi resetAfterWarmup sau khi warm-up kết thúc và trước cửa sổ measurement.

Runnable trong ví dụ không thể trả kết quả và không tự xử lý exception; trong ứng dụng thực tế hãy bọc operation bằng instrumentation phù hợp, ghi cả request lỗi/timeout theo quy ước SLO. Nếu đo client end-to-end, bắt đầu timestamp trước khi gửi request và kết thúc sau khi nhận đủ response. Không chỉ đo phần thân handler rồi gọi đó là request latency.

### Closed-loop và open-loop

Closed-loop client gửi request tiếp theo sau khi request trước hoàn tất. Cách này dễ triển khai nhưng tốc độ phát request giảm khi hệ thống chậm. Open-loop load generator phát theo tốc độ mục tiêu độc lập với response, phù hợp để quan sát queueing khi tải tăng.

Khi dùng open-loop, theo dõi cả thời gian request chờ trong load generator và số request bị drop. Nếu load generator không phát đủ tốc độ dự kiến, kết quả không đại diện cho tải mục tiêu. Tránh coordinated omission: khi hệ thống bị pause, load generator không được âm thầm bỏ qua các thời điểm lẽ ra phải phát request rồi báo latency thấp giả tạo.

## 4. Allocation rate là gì?

Allocation rate là lượng bộ nhớ object được cấp phát trong một khoảng thời gian, thường biểu diễn bằng MiB/s hoặc bytes/s:

`Allocated bytes in measurement window / elapsed seconds`

Ví dụ ứng dụng cấp phát 1.200 MiB trong 60 giây thì allocation rate trung bình là 20 MiB/s. Đây là tốc độ tạo object, không phải lượng object còn sống sau GC.

Phân biệt:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Allocation rate | Tốc độ tạo object mới. |
| Live set / post-GC occupancy | Dung lượng object còn sống sau collection tại thời điểm đo. |
| Heap committed | Dung lượng heap JVM đã commit. |
| RSS | Bộ nhớ resident của toàn tiến trình theo hệ điều hành. |

Ứng dụng có thể có allocation rate cao nhưng live set nhỏ nếu object sống ngắn và được thu gom nhanh. Ngược lại, allocation rate thấp vẫn có thể đi cùng live set lớn nếu cache hoặc object graph giữ nhiều dữ liệu lâu dài.

## 5. Đo allocation bằng JFR

Java Flight Recorder (JFR) là công cụ phù hợp để xác định loại object và call path gây allocation. Có thể ghi một khoảng thời gian giới hạn:

```powershell
jcmd <pid> JFR.start name=allocation-check settings=profile duration=120s filename=allocation-check.jfr
```

Mở file bằng JDK Mission Control (JMC) hoặc công cụ đọc JFR tương thích. Kiểm tra các allocation event, đặc biệt jdk.ObjectAllocationSample, cùng class, thread và stack trace nếu event được cấu hình ghi.

ObjectAllocationSample là event lấy mẫu; trường weight biểu diễn lượng allocation ước tính gắn với sample. Có thể dùng dữ liệu này để xác định nơi allocation tập trung và ước lượng xu hướng, nhưng không coi số event sample là số object thực tế hoặc tổng byte chính xác tuyệt đối.

Một số recording/profile có thể bật hoặc tắt event khác nhau. Kiểm tra event configuration của recording và dùng cấu hình allocation phù hợp với mục tiêu. Bật event chi tiết hơn có thể tăng overhead và dung lượng file; hãy đo overhead trước khi dùng trong production.

JFR giúp trả lời:

- Class nào đang được cấp phát nhiều?
- Stack trace hoặc component nào tạo allocation?
- Allocation tăng ở thread hoặc endpoint nào?
- Allocation spike có trùng với GC frequency hoặc p99 spike không?

JFR allocation sample không thay thế phép đo latency end-to-end. Hãy ghi cùng khoảng thời gian với request histogram và GC logs để đối chiếu.

## 6. Allocation bytes theo thread bằng ThreadMXBean của HotSpot

HotSpot cung cấp extension com.sun.management.ThreadMXBean để đọc số byte được cấp phát bởi từng platform thread. Đây là API mở rộng của JDK, không phải hợp đồng portable của Java SE cho mọi JVM vendor.

Ví dụ đọc counter trước và sau một workload trên cùng thread:

```java
import java.lang.management.ManagementFactory;
import com.sun.management.ThreadMXBean;

class ThreadAllocationCounter {
    static long allocatedBytes(Runnable workload) {
        java.lang.management.ThreadMXBean base =
            ManagementFactory.getThreadMXBean();

        if (!(base instanceof ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()) {
            throw new UnsupportedOperationException(
                "Thread allocated-memory counter is not supported"
            );
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long threadId = Thread.currentThread().getId();
        long before = bean.getThreadAllocatedBytes(threadId);
        workload.run();
        long after = bean.getThreadAllocatedBytes(threadId);

        if (before < 0 || after < before) {
            throw new IllegalStateException("Allocation counter unavailable");
        }
        return after - before;
    }
}
```

Counter này chỉ đo allocation của thread được hỏi trong khoảng đó. Nó bỏ sót allocation do worker thread khác thực hiện, và không tính native allocation như direct memory hoặc malloc từ JNI. Nếu workload dùng thread pool, cần đo các worker liên quan hoặc dùng JFR/profiler ở cấp process.

Không gọi setThreadAllocatedMemoryEnabled(true) trong mỗi request; cấu hình counter một lần ở môi trường đo và đánh giá overhead. Nếu vendor không hỗ trợ extension này, dùng JFR hoặc profiler tương thích.

## 7. Đọc GC activity cùng allocation rate

Allocation rate giúp hiểu áp lực tạo object; GC log cho biết collector phản ứng ra sao. Bật unified GC và safepoint logging khi cần baseline:

```text
-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags
```

Có thể chạy ứng dụng với cấu hình đó:

```powershell
java -Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags -jar app.jar
```

Đọc các nhóm thông tin:

- Thời điểm và loại GC event.
- Pause duration và các phase chi tiết.
- Heap occupancy trước/sau collection.
- Allocation/young generation pressure nếu collector log có thông tin tương ứng.
- Safepoint time-to-reach và VM operation.
- Full GC, evacuation failure hoặc dấu hiệu allocation không đáp ứng được.

JMX GarbageCollectorMXBean có getCollectionCount() và getCollectionTime(). Đây là counter tổng hợp theo collector; getCollectionTime() dùng millisecond và có thể trả -1 nếu không hỗ trợ. Hai giá trị này hữu ích để theo dõi xu hướng, nhưng không thay thế histogram pause p95/p99 vì chúng không giữ phân phối thời gian từng collection.

Kết hợp JFR GC events và unified logs để phân biệt:

- Allocation rate tăng và young GC thường xuyên hơn.
- Live set sau GC tăng qua từng chu kỳ.
- Pause tăng do evacuation/remark/reference processing.
- Safepoint chờ thread lâu dù GC phase không dài.

Không suy ra allocation rate chính xác chỉ từ số lần GC hoặc tổng collection time.

## 8. RSS đo gì?

RSS (Resident Set Size) là lượng trang bộ nhớ của tiến trình hiện đang resident trong RAM theo cách hệ điều hành báo cáo. Nó không đồng nghĩa heap used và cũng không phải tổng virtual address space.

RSS có thể gồm các trang resident của:

- Java heap.
- Metaspace và Compressed Class Space.
- JIT Code Cache.
- Thread stacks.
- Direct ByteBuffer và native allocations.
- JNI/native library, memory mapping và một số trang shared.

Trang shared có thể được tính vào RSS của nhiều process; nếu cần phân bổ phần shared công bằng hơn trên Linux, xem thêm PSS. Trong container, cần theo dõi cả process RSS lẫn memory usage của cgroup vì giới hạn container áp dụng ở cấp cgroup, có thể gồm nhiều process và page cache.

Ví dụ lấy một số đo theo nền tảng:

```powershell
# Windows PowerShell: working set của process
Get-Process -Id <pid> | Select-Object Id, WorkingSet64, PrivateMemorySize64
```

```bash
# Linux: RSS trong /proc
grep -E 'VmRSS|VmSize' /proc/<pid>/status

# Linux cgroup v2: bộ nhớ hiện tại của cgroup (đường dẫn tùy container)
cat /sys/fs/cgroup/memory.current
```

WorkingSet64 trên Windows và VmRSS trên Linux là số đo gần tương ứng ở cấp process nhưng không có cùng ngữ nghĩa hoàn toàn. Ghi rõ nguồn metric và đơn vị khi so sánh. Trên macOS hoặc môi trường container khác, dùng công cụ process/cgroup tương ứng.

## 9. Vì sao RSS có thể tăng dù heap used ổn định?

Nếu heap used sau GC ổn định nhưng RSS vẫn tăng, có thể có nguyên nhân ngoài heap:

- Metaspace tăng do nạp class, class loader retention hoặc proxy generation.
- Direct buffer/native allocation tăng.
- Số thread tăng làm thread stack chiếm thêm bộ nhớ.
- Code Cache tăng khi JIT biên dịch thêm method.
- Native library hoặc JNI giữ allocation.
- Memory mapping, shared memory hoặc page residency thay đổi.
- Container có page cache hoặc process khác cùng cgroup tiêu thụ bộ nhớ.

Khi RSS tăng, đối chiếu JMX heap/non-heap, Metaspace, direct buffer pool, thread count, NMT và cgroup metrics. Không tăng -Xmx để xử lý RSS cao nếu chưa chứng minh heap là thành phần gây áp lực.

Native Memory Tracking (NMT) của HotSpot có thể giúp phân loại reserved/committed native memory. NMT phải được bật khi JVM khởi động và có overhead; nó không phải phép đo RSS, nên vẫn cần số liệu hệ điều hành:

```text
-XX:NativeMemoryTracking=summary
```

```powershell
jcmd <pid> VM.native_memory summary scale=MB
```

So sánh baseline và diff của NMT trong cùng một workload. Đối chiếu category như Java Heap, Class, Thread, Code, GC và Internal; tránh cộng category cha với category con gây đếm trùng.

## 10. Đặt p95/p99, allocation, GC và RSS trên cùng timeline

Một bảng baseline hữu ích có cùng timestamp/window:

| Metric | Ví dụ giá trị | Nguồn |
| --- | ---: | --- |
| Throughput | 2.500 request/s | Load generator / service metrics |
| p95 latency | 85 ms | Request histogram |
| p99 latency | 240 ms | Request histogram |
| Allocation rate | 180 MiB/s | JFR estimate hoặc allocation counter |
| Heap used after GC | 1,8 GiB | GC log/JMX |
| GC pause p95 | 18 ms | GC event histogram |
| GC pause max | 74 ms | GC log/JFR |
| RSS | 3,1 GiB | OS process metrics |
| Cgroup memory | 3,6 GiB | Container metrics |
| Error/timeout rate | 0,05% | Service metrics |

Các con số trên chỉ minh họa cách trình bày, không phải ngưỡng chuẩn cho ứng dụng Java. Hãy giữ cùng cửa sổ đo, timezone/uptime reference và sampling interval. Với p99, số request trong cửa sổ phải đủ lớn để percentile ổn định.

Một dashboard nên hiển thị:

- p50/p95/p99 request latency và throughput.
- Request rate, queue depth, concurrency, timeout và error rate.
- Allocation rate và live heap sau GC.
- GC count, pause duration theo percentile/max và loại collector.
- Safepoint time-to-reach.
- RSS, heap committed/used, Metaspace, direct buffer và cgroup usage.
- CPU utilization, throttling và GC worker utilization.

Nếu chỉ có một snapshot RSS và một dòng GC log, bạn chưa có đủ dữ liệu để thay đổi cấu hình.

## 11. Đọc các mẫu số liệu thường gặp

| Quan sát đồng thời | Diễn giải có thể | Bước tiếp theo |
| --- | --- | --- |
| Allocation rate tăng, young GC tăng, p99 tăng | Allocation pressure có thể làm tăng GC work hoặc CPU contention. | Dùng JFR tìm allocation hot path; xem GC phase và CPU. |
| Allocation cao nhưng post-GC live set ổn định, p99 tốt | Object sống ngắn và collector xử lý được workload. | Chưa có lý do đổi collector; tối ưu allocation chỉ khi CPU/throughput cần. |
| Post-GC live set tăng qua nhiều chu kỳ | Object retention/cache tăng hoặc workload giữ nhiều dữ liệu hơn. | Kiểm tra heap histogram, heap dump và dominator tree. |
| RSS tăng, heap used ổn định | Native memory, thread stack, metaspace, code cache hoặc mapping có thể tăng. | Dùng NMT, JMX non-heap và OS metrics để phân loại. |
| p99 tăng nhưng GC pause không đổi | Bottleneck có thể nằm ở queue, lock, CPU throttling, I/O hoặc downstream. | Correlate request trace, thread/CPU/queue metrics. |
| Safepoint time-to-reach dài, GC phase ngắn | Thread mất thời gian đạt trạng thái an toàn. | Điều tra thread state, long-running native/Java activity và số thread. |
| GC pause dài, allocation ổn định, live set cao | Nhiều object sống hoặc collector phase/heap geometry gây chi phí. | Xem evacuation/remark/Full GC và live-set profile. |

Đây là giả thuyết để điều tra, không phải kết luận tự động. Luôn xác nhận bằng trace/log/profiler và lặp lại trên workload tương đương.

## 12. Tránh các sai lầm khi đo

- **Chỉ xem average:** average có thể che p99 và outlier.
- **Chỉ đo handler:** bỏ qua queue và network làm latency thấp giả tạo.
- **Dùng closed-loop cho mọi tình huống:** khi hệ thống chậm, client tự giảm tốc và không thể hiện tải đến liên tục.
- **Bỏ qua coordinated omission:** load generator không phát request đúng lịch trong lúc pause.
- **Đếm allocation sample như byte chính xác:** JFR sampling là ước lượng; hiểu weight và event configuration.
- **Đồng nhất allocation với live set:** object cấp phát có thể chết nhanh.
- **Đồng nhất RSS với heap:** RSS bao gồm nhiều vùng native và shared pages.
- **So sánh cửa sổ không cùng tải:** request rate hoặc payload khác nhau làm kết quả không thể so sánh.
- **Thay nhiều flags cùng lúc:** không biết thay đổi nào tạo khác biệt.
- **Chỉ nhìn GC log:** latency có thể do CPU throttling, lock, queue hoặc downstream.

## 13. Khi nào mới nên đổi cấu hình GC?

Chỉ cân nhắc thay collector hoặc GC-related flags khi có bằng chứng lặp lại:

1. p95/p99 vi phạm SLO trong workload đại diện.
2. GC pause hoặc GC CPU có tương quan rõ với latency spike/throughput loss.
3. Log/JFR xác định phase hoặc áp lực cụ thể, không chỉ có một dòng "GC occurred".
4. Đã loại trừ queueing, CPU throttling, lock contention, I/O và downstream latency.
5. Đã hiểu allocation rate, post-GC live set và memory headroom.
6. Có hypothesis rõ ràng về thay đổi sẽ cải thiện metric nào và ảnh hưởng metric nào.

Trước khi đổi collector:

- Xem allocation hot path và giảm allocation không cần thiết nếu đó là bottleneck.
- Kiểm tra object retention và cache growth nếu live set tăng.
- Kiểm tra heap headroom và container memory limit.
- Xem GC worker có bị CPU quota/throttling hay cạnh tranh CPU không.
- So sánh collector phù hợp với JDK mục tiêu bằng cùng load test và SLO.

Thay từng yếu tố một, chạy nhiều lần, giữ lại cấu hình baseline để rollback. Đánh giá đồng thời p95/p99, throughput, allocation, GC CPU, pause, RSS/cgroup và error rate. Một collector có pause ngắn hơn nhưng CPU cao hơn hoặc RSS lớn hơn có thể không phù hợp với giới hạn production.

## 14. Dùng logging hiện đại, tránh flag GC logging cũ

JDK hiện đại sử dụng Unified Logging. Dùng:

```text
-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags
```

Các tùy chọn cũ như -XX:+PrintGCDetails và -XX:+PrintGCDateStamps thuộc cách cấu hình GC logging trước Unified Logging. Không đưa chúng vào cấu hình mới; dùng -Xlog để có tag, level và output rotation được quản lý nhất quán.

JFR, JMX, unified GC/safepoint logs và process/container metrics đều có thể dùng trên JDK hiện đại. Hãy xác nhận event và option được hỗ trợ bởi đúng JDK vendor/build đang triển khai.

## 15. Checklist trước khi thay GC

- [ ] Đã định nghĩa p95/p99 và điểm bắt đầu/kết thúc latency.
- [ ] Load test đại diện về payload, throughput, concurrency và request pattern.
- [ ] Warm-up được tách khỏi steady-state; có nhiều lần chạy.
- [ ] Đã ghi p50/p95/p99, throughput, queue depth, timeout và error rate.
- [ ] Allocation rate được đo và ghi rõ là exact counter hay JFR estimate.
- [ ] Đã phân biệt allocation rate với post-GC live set.
- [ ] GC logs/JFR có cùng timestamp window với request metrics.
- [ ] Đã phân biệt GC pause với safepoint time-to-reach.
- [ ] RSS/process và cgroup memory được theo dõi riêng với heap.
- [ ] Đã kiểm tra Metaspace, direct buffers, thread count, Code Cache và native memory khi RSS tăng.
- [ ] Đã loại trừ CPU throttling, queueing, lock và downstream latency.
- [ ] Có hypothesis, một thay đổi mỗi lần, tiêu chí thành công và kế hoạch rollback.

## 16. Những điểm cần nhớ

- p95/p99 phải lấy từ histogram request có định nghĩa latency nhất quán.
- Allocation rate đo tốc độ tạo object; live set đo lượng object còn sống.
- JFR allocation sample hỗ trợ tìm nguồn cấp phát và ước lượng, không phải phép đếm tuyệt đối mọi byte.
- Thread allocated-byte counter của HotSpot là extension theo thread, không bao gồm mọi worker/native allocation.
- RSS là metric process-level của hệ điều hành; nó không đồng nghĩa heap used hay heap committed.
- Đọc GC pause, safepoint, allocation và request latency trên cùng timeline.
- p99 cao không tự động do GC; RSS cao không tự động do heap; allocation cao không tự động là leak.
- Chỉ đổi collector/flags sau khi đã cô lập bottleneck và có baseline lặp lại.
- Dùng Unified Logging -Xlog và JFR thay cho GC logging flags cũ.

Trước khi đổi GC, hãy chứng minh mối liên hệ giữa request tail latency, allocation pressure, GC phase và memory footprint bằng dữ liệu cùng cửa sổ đo. Nếu p99 xấu nhưng GC pause không tăng, hãy tìm bottleneck ngoài GC. Nếu RSS tăng nhưng heap ổn định, hãy phân loại native memory. Một baseline đủ tốt sẽ giúp thay đổi nhỏ, có mục tiêu và có thể kiểm chứng.

## Tài liệu tham khảo

- [Garbage Collection Tuning Guide – Java SE 16](https://docs.oracle.com/en/java/javase/16/gctuning/)
- [Garbage Collection Tuning Guide – Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/)
- [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/26/jfapi/)
- [ThreadMXBean – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/ThreadMXBean.html)
- [MemoryMXBean – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [jcmd – Java SE 26 Tools Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Unified Logging – Java SE 26 Tools Reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
