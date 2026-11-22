# Đo Garbage Collection (GC) trong JVM

## 1. Vì sao cần đo GC?

Garbage Collection (GC) tự động thu hồi vùng nhớ của những object không còn reachable. Cơ chế này giúp ứng dụng Java không phải tự giải phóng object, nhưng hoạt động GC vẫn sử dụng CPU, memory bandwidth và đôi khi tạm dừng application thread.

Đo GC là thu thập dữ liệu trong một khoảng thời gian có tải đại diện để trả lời:

- JVM chạy GC bao nhiêu lần và loại collection nào đang diễn ra?
- Mỗi lần pause kéo dài bao lâu? P95, P99 và pause dài nhất là bao nhiêu?
- Tổng thời gian ứng dụng bị dừng vì GC chiếm bao nhiêu phần trăm thời gian quan sát?
- Heap còn bao nhiêu dung lượng sau collection?
- Ứng dụng tạo object với tốc độ bao nhiêu byte/giây?
- Object có bị promote lên old generation quá nhanh không?
- Có Full GC, evacuation failure, allocation stall hoặc chu kỳ concurrent GC kéo dài không?
- GC có liên quan tới throughput giảm hoặc request latency tăng không?

Đo GC cần kết hợp log của JVM, số liệu runtime, dữ liệu ứng dụng và profiling. Một con số đơn lẻ như heap usage hoặc số lần GC không đủ để kết luận GC có phải bottleneck hay không.

## 2. Những chỉ số GC quan trọng

### 2.1. Tần suất và số lần collection

Đếm số collection theo loại trong một khoảng thời gian:

- Young collection: thu gom vùng dành cho object trẻ.
- Mixed collection: với G1, thu gom young regions cùng một số old regions được chọn.
- Full GC: collection toàn heap theo cách triển khai của collector.
- Concurrent cycle: các giai đoạn collector làm việc song song với application thread.

Tên và cách phân loại collection phụ thuộc collector. Không giả định mọi JVM đều có cùng khái niệm hoặc cùng tên sự kiện.

Tần suất cao có thể phản ánh allocation rate lớn, heap nhỏ hoặc nhiều object sống lâu. Tần suất cao tự nó chưa phải lỗi: nhiều young collection ngắn có thể là hành vi bình thường.

### 2.2. Pause time và tổng thời gian pause

Pause time là thời gian application thread bị dừng trong một GC pause. Theo dõi:

- Average pause: thời gian pause trung bình.
- Maximum pause: pause dài nhất.
- P95/P99 pause: phân vị để nhìn các lần pause bất thường.
- Total pause time: tổng thời gian ứng dụng bị dừng vì GC trong cửa sổ đo.

Với ứng dụng tương tác hoặc API, P99 latency và pause dài nhất thường quan trọng hơn chỉ số trung bình. Một pause 300 ms có thể ảnh hưởng rõ đến request dù hàng trăm pause khác chỉ kéo dài vài millisecond.

Với collector concurrent như G1, ZGC hoặc Shenandoah, phần lớn công việc GC có thể diễn ra khi application thread vẫn chạy. Vì vậy, thời gian của cả chu kỳ GC không đồng nghĩa với thời gian pause của ứng dụng. Cần đo pause riêng.

### 2.3. Throughput và latency của ứng dụng

Hai mục tiêu GC phổ biến là:

- Throughput: tỷ lệ thời gian JVM không dành cho GC trong một khoảng dài.
- Latency: mức phản hồi của ứng dụng; GC pause có thể làm request bị chậm.

Đo cùng lúc với GC:

- Request/second hoặc job/second.
- P50, P95 và P99 latency.
- Error/timeout rate.
- CPU process và CPU quota.
- GC pause và allocation rate.

Throughput GC không thay thế throughput nghiệp vụ. Một collector có pause thấp vẫn có thể tiêu thụ CPU concurrent nhiều, làm giảm lượng CPU dành cho application thread.

### 2.4. Heap trước và sau GC

Log GC thường ghi heap used trước và sau collection, cùng heap capacity.

Ví dụ:

```text
239M->57M(307M)
```

Ý nghĩa:

- `239M`: heap used trước collection.
- `57M`: heap used sau collection.
- `307M`: heap capacity tại thời điểm đó.

Mức used sau GC có thể giúp ước lượng live set, nhưng cần so sánh nhiều lần và đúng pool. Heap usage được đọc ở một thời điểm bất kỳ có thể bao gồm cả object chưa được thu hồi, kể cả object không còn reachable nhưng chưa được GC xử lý.

### 2.5. Allocation rate và promotion

Allocation rate là lượng bộ nhớ object được tạo ra trên một đơn vị thời gian:

```text
Allocation rate = bytes allocated / elapsed seconds
```

Ví dụ: ứng dụng cấp phát 600 MB trong 30 giây thì allocation rate trung bình là 20 MB/s.

Promotion rate là tốc độ object sống sót qua các collection trẻ và chuyển sang vùng quản lý object lâu sống. Promotion tăng có thể làm old generation tăng nhanh và dẫn tới old collection thường xuyên hơn.

Allocation rate cao không nhất thiết là memory leak. Ứng dụng có thể tạo nhiều object tạm thời nhưng thu hồi chúng nhanh. Memory leak thường thể hiện qua live set sau GC tăng dần qua các chu kỳ hoặc qua nhiều cửa sổ quan sát.

### 2.6. Footprint và live set

Theo dõi cả heap used, committed và max; used sau collection ở từng memory pool khi collector hỗ trợ; process RSS hoặc container memory; Metaspace và direct/native memory khi cần.

Heap không đại diện cho toàn bộ memory của process. JVM còn có Metaspace, code cache, thread stack, direct buffer, native library và vùng nhớ nội bộ. Vì vậy, heap còn trống không đảm bảo process không chạm giới hạn RAM hoặc container.

## 3. Chuẩn bị một phép đo có ý nghĩa

Trước khi bật công cụ, xác định câu hỏi cần trả lời và chuẩn hóa điều kiện đo.

1. Ghi lại JDK vendor/version, OS, collector, `-Xms`, `-Xmx`, container CPU/memory limit và các JVM option.
2. Chọn workload đại diện, dữ liệu đầu vào và concurrency tương đương production.
3. Ghi baseline khi chưa thay đổi cấu hình GC.
4. Cho ứng dụng warm-up để giảm ảnh hưởng class loading và JIT compilation.
5. Đo trong cửa sổ đủ dài để có nhiều chu kỳ GC; với sự cố hiếm gặp, cần quan sát lâu hơn.
6. Ghi throughput, P95/P99 latency, CPU, memory và error rate cùng thời điểm.
7. Lặp lại phép đo và giữ nguyên workload khi so sánh các cấu hình.
8. Lưu GC log và JFR recording kèm timestamp, phiên bản JDK và cấu hình.

Không gọi `System.gc()` trong benchmark để cố tạo collection. Lời gọi này có thể làm thay đổi hành vi collector và tạo ra kết quả không đại diện cho workload thật. Nếu cần kiểm tra phản ứng với explicit GC, hãy đo riêng và ghi rõ đó là phép thử có chủ đích.

## 4. Bật GC log bằng Unified Logging

Từ JDK 9, HotSpot dùng Unified Logging qua tùy chọn `-Xlog`. Cách cơ bản:

```bash
java -Xlog:gc -jar app.jar
```

Ghi thêm thông tin về heap, phase và các thành phần GC:

```bash
java -Xlog:gc* -jar app.jar
```

Có thể chỉ định file log, timestamp, uptime và mức log:

```bash
java "-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags" -jar app.jar
```

Thư mục `logs` cần tồn tại và tài khoản chạy JVM phải có quyền ghi.

Ví dụ dùng log rotation để tránh file tăng không giới hạn:

```bash
java -Xms2g -Xmx2g "-Xlog:gc*,safepoint:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
```

Trong ví dụ:

- `gc*`: ghi các log tag có `gc`, bao gồm các tag GC kết hợp như `gc,heap` hoặc `gc,phases`.
- `safepoint`: ghi thêm thông tin safepoint.
- `filecount=5`: giữ tối đa năm file log đã rotate, không tính file đang ghi.
- `filesize=20M`: ngưỡng kích thước mục tiêu để rotate mỗi file.
- `time,uptime,level,tags`: thêm thời gian thực, thời gian từ lúc JVM khởi động, mức log và tag.

Nếu chỉ cần log GC cơ bản, có thể dùng:

```bash
java "-Xlog:gc:file=gc.log:time,uptime,level,tags" -jar app.jar
```

Để xem heap detail hoặc phase cụ thể:

```bash
java "-Xlog:gc+heap=debug,gc+phases=debug" -jar app.jar
```

Mức `debug` và `trace` tạo nhiều dữ liệu hơn. Chỉ bật khi cần điều tra cụ thể, kiểm tra dung lượng và overhead sau khi thay đổi cấu hình.

`-verbose:gc` là alias của `-Xlog:gc` trên HotSpot hiện đại. Các cờ GC logging cũ như `-XX:+PrintGCDetails` thuộc cách cấu hình trước Unified Logging; khi làm việc với JDK mới, ưu tiên `-Xlog`.

## 5. Đọc một dòng GC log

Ví dụ rút gọn từ log G1:

```text
[15.651s][info][gc] GC(36) Pause Young (G1 Evacuation Pause) 239M->57M(307M) 5.048ms
```

Có thể đọc các trường như sau:

| Thành phần | Ý nghĩa |
|---|---|
| `15.651s` | Uptime của JVM tại thời điểm log |
| `info` | Log level |
| `gc` | Tag của log |
| `GC(36)` | ID của collection |
| `Pause Young` | Loại collection/pause |
| `G1 Evacuation Pause` | Nguyên nhân hoặc loại pause theo G1 |
| `239M->57M(307M)` | Heap used trước, sau collection và capacity |
| `5.048ms` | Thời gian pause được log |

Một số log có thêm thời điểm bắt đầu/kết thúc và CPU time:

```text
[10.191s][info][gc] GC(36) Pause Young (G1 Evacuation Pause) 391M->114M(508M) 13.075ms
[10.191s][info][gc,cpu] GC(36) User=0.20s Sys=0.00s Real=0.01s
```

`Real` là thời gian thực đã trôi qua, `User` và `Sys` là CPU time. CPU time có thể lớn hơn real time khi nhiều GC worker chạy song song. Không dùng `User + Sys` thay cho thời gian ứng dụng bị pause.

Các log chi tiết còn cho biết số region Eden/Survivor/Old, Metaspace, phase evacuation và thông tin collector. Tên tag, trường và format có thể thay đổi giữa JDK release hoặc collector; dùng tài liệu đúng phiên bản và không viết parser cứng dựa vào một dòng log duy nhất.

## 6. Dùng jstat để xem GC theo thời gian

`jstat` lấy thống kê từ một JVM HotSpot đã được instrument. Trước tiên tìm PID:

```bash
jps -l
```

Lấy số liệu GC utilization mỗi giây, mười mẫu:

```bash
jstat -gcutil -t <PID> 1000 10
```

Hoặc lấy thống kê dung lượng và mức sử dụng từng vùng:

```bash
jstat -gc <PID> 1000 10
```

Xem nguyên nhân của collection gần nhất:

```bash
jstat -gccause <PID> 1000 10
```

Một số cột thường gặp trong `-gcutil`:

| Cột | Ý nghĩa |
|---|---|
| `S0`, `S1` | Tỷ lệ sử dụng Survivor space 0 và 1 |
| `E` | Tỷ lệ sử dụng Eden |
| `O` | Tỷ lệ sử dụng Old space |
| `M` | Tỷ lệ sử dụng Metaspace |
| `CCS` | Tỷ lệ sử dụng Compressed Class Space |
| `YGC` | Số young GC |
| `YGCT` | Thời gian young GC tích lũy |
| `FGC` | Số full GC |
| `FGCT` | Thời gian full GC tích lũy |
| `GCT` | Tổng thời gian GC tích lũy |
| `CGC`, `CGCT` | Số lần và thời gian concurrent GC nếu JVM hiển thị |

Các cột phụ thuộc JDK, VM và collector. Ví dụ một lần lấy mẫu trên JDK 24 có thể hiển thị:

```text
Timestamp    S0     S1      E      O      M     CCS    YGC   YGCT   FGC   FGCT   CGC   CGCT    GCT
1.0           -  100.00  57.14  28.18  73.95  35.01      5  0.007     0  0.000     0  0.000  0.007
1.5           -   93.75   8.82  33.60  73.95  35.01      8  0.009     0  0.000     0  0.000  0.009
```

Trong ví dụ, Eden tăng rồi giảm sau young collection; `YGC` tăng từ 5 lên 8. Đây là dấu hiệu collection đã xảy ra giữa hai mẫu.

**Lưu ý:** Oracle đánh dấu `jstat` là experimental/unsupported; các tùy chọn và format có thể thay đổi hoặc bị loại bỏ ở phiên bản sau. Dùng nó để quan sát trực tiếp và kiểm tra xu hướng, không xây dựng parser production phụ thuộc vào format output.

`GCT` và `YGCT` là bộ đếm thời gian tích lũy do JVM cung cấp. Với collector có concurrent phase, không coi các số này là tổng stop-the-world pause chính xác. Dùng GC log hoặc JFR để phân tích pause.

## 7. Đo GC bằng GarbageCollectorMXBean

Java cung cấp platform MXBean để đọc số lần collection và thời gian collection tích lũy.

Lấy danh sách collector:

```java
List<GarbageCollectorMXBean> collectors =
        ManagementFactory.getGarbageCollectorMXBeans();

for (GarbageCollectorMXBean gc : collectors) {
    System.out.println(gc.getName());
    System.out.println(gc.getCollectionCount());
    System.out.println(gc.getCollectionTime());
}
```

Hai phương thức quan trọng:

- `getCollectionCount()`: tổng số collection đã xảy ra.
- `getCollectionTime()`: thời gian collection tích lũy gần đúng, tính bằng millisecond.

Một số JVM có thể trả `-1` nếu không xác định được giá trị. Vì vậy, khi tính delta, cần kiểm tra cả giá trị ban đầu và giá trị cuối.

Ví dụ tính chênh lệch trong một cửa sổ đo:

```java
long countBefore = gc.getCollectionCount();
long timeBefore = gc.getCollectionTime();

// Chạy workload cần đo ở đây.

long countAfter = gc.getCollectionCount();
long timeAfter = gc.getCollectionTime();

long countDelta = countBefore < 0 || countAfter < 0
        ? -1 : countAfter - countBefore;

long timeDeltaMs = timeBefore < 0 || timeAfter < 0
        ? -1 : timeAfter - timeBefore;
```

Các số liệu này phù hợp để làm metric giám sát và xem xu hướng. `getCollectionTime()` là thời gian collection tích lũy gần đúng, không phải phép đo chính xác tổng thời gian application thread bị dừng. Với collector concurrent, dùng JFR hoặc GC log để đo pause.

Có thể theo dõi heap qua `MemoryMXBean`:

```java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

long used = memory.getHeapMemoryUsage().getUsed();
long committed = memory.getHeapMemoryUsage().getCommitted();
long max = memory.getHeapMemoryUsage().getMax();
```

`used` là lượng heap đang sử dụng tại thời điểm đọc; `committed` là dung lượng JVM đã cam kết và `max` là giới hạn tối đa nếu được xác định. Giá trị này không tự động cho biết live set sau GC.

Với từng memory pool, `MemoryPoolMXBean.getCollectionUsage()` có thể cung cấp mức sử dụng sau collection nếu pool hỗ trợ. Kiểm tra `isCollectionUsageThresholdSupported()` trước khi sử dụng collection threshold. Tên pool và khả năng hỗ trợ phụ thuộc collector.

## 8. Theo dõi MXBean trong JConsole

Có thể quan sát GC mà không viết code giám sát riêng:

1. Chạy ứng dụng Java.
2. Mở `jconsole`.
3. Kết nối tới local process hoặc JVM đã cấu hình remote JMX.
4. Mở tab **Memory** để xem heap và memory pool.
5. Mở tab **MBeans**.
6. Chọn `java.lang` → `GarbageCollector`.
7. Chọn từng collector để xem `CollectionCount`, `CollectionTime` và tên memory pool liên quan.
8. Mở `java.lang` → `Memory` để xem heap usage.

JConsole hữu ích để quan sát trực tiếp và xác định thời điểm memory thay đổi. Đối với điều tra dài hạn, nên xuất metric ra hệ thống monitoring và giữ log/recording để phân tích theo thời gian.

Có thể dùng MemoryMXBean notification để phát hiện pool vượt usage threshold hoặc collection usage threshold. Không phải mọi pool đều hỗ trợ cả hai loại threshold; kiểm tra capability trước khi cấu hình.

## 9. Dùng Java Flight Recorder để đo pause chính xác hơn

Java Flight Recorder (JFR) ghi các event của JVM theo thời gian. Đây là công cụ hữu ích để phân tích GC pause, GC phase và allocation.

Bắt đầu một profiling recording có thời hạn:

```bash
jcmd <PID> JFR.start name=gc-profile settings=profile duration=10m disk=true filename=gc-profile.jfr
```

Kiểm tra recording:

```bash
jcmd <PID> JFR.check
```

Sau khi recording hoàn tất, xem tổng quan:

```bash
jfr summary gc-profile.jfr
```

In các GC pause event:

```bash
jfr print --events jdk.GCPhasePause gc-profile.jfr
```

Có thể xem event collection tổng quát:

```bash
jfr print --events jdk.GarbageCollection gc-profile.jfr
```

`jdk.GCPhasePause` cung cấp duration của pause. Dựa trên các event này, có thể tính pause trung bình, pause lớn nhất và tổng pause time. Khi phân tích, dùng event pause cấp cao; không cộng thêm các phase con lần nữa vì sẽ đếm trùng thời gian.

JFR cũng có event về allocation như `jdk.ObjectAllocationInNewTLAB`, `jdk.ObjectAllocationOutsideTLAB` và `jdk.ThreadAllocationStatistics`. Chúng giúp tìm class hoặc thread tạo nhiều allocation.

**Không bật Heap Statistics trong phép đo latency thông thường.** Theo Oracle, Heap Statistics có thể kích hoạt old GC ở đầu và cuối recording, tạo thêm pause làm sai lệch phép đo. Chỉ bật khi điều tra live set hoặc memory leak và ghi rõ ảnh hưởng này trong kết quả.

## 10. Phân tích recording bằng JDK Mission Control

JDK Mission Control (JMC) đọc file JFR và trình bày dữ liệu theo timeline.

Để điều tra GC:

1. Mở file `.jfr` trong JMC.
2. Xem **Automated Analysis Results** và phần Garbage Collections.
3. Mở trang **JVM Internals → Garbage Collections**.
4. Quan sát biểu đồ GC pauses và **Sum of Pauses**.
5. So sánh pause count, average, maximum và tổng thời gian pause.
6. Mở phần TLAB Allocations để tìm class/thread tạo nhiều object.
7. Đối chiếu GC event với CPU, thread, allocation và thời điểm latency tăng.

**Sum of Pauses** là tổng thời gian ứng dụng thực sự bị dừng trong các GC pause. Đây là chỉ số hữu ích với collector làm nhiều công việc concurrent, vì tổng thời gian một chu kỳ GC có thể dài hơn rất nhiều so với pause mà ứng dụng phải chịu.

Nếu thấy Full GC hoặc pause tăng mạnh, kiểm tra nguyên nhân trong GC log và heap sau collection. Không kết luận chỉ từ biểu đồ; cần đối chiếu workload, allocation và memory retention.

## 11. Tính các chỉ số từ dữ liệu đã thu thập

### 11.1. GC pause ratio

Tính tỷ lệ thời gian ứng dụng bị dừng vì GC:

```text
GC pause ratio (%) =
  Tổng GC pause time / Measurement window × 100
```

Ví dụ, trong cửa sổ đo 300 giây, tổng pause time là 1,5 giây:

```text
1.5 / 300 × 100 = 0.5%
```

Đây là tỷ lệ thời gian dừng do GC pause. Nó không bao gồm toàn bộ CPU mà concurrent GC sử dụng.

### 11.2. GC frequency

```text
GC frequency = Số collection / Số giây quan sát
```

Nên tách theo young, mixed, full và concurrent cycle khi log/collector cung cấp loại tương ứng.

### 11.3. Average pause

```text
Average pause = Tổng pause time / Số pause events
```

Không chỉ xem average. P95, P99 và maximum giúp phát hiện các pause hiếm nhưng ảnh hưởng lớn.

### 11.4. Allocation rate

```text
Allocation rate (MB/s) =
  Allocated bytes / Elapsed seconds / 1,048,576
```

Để so sánh hai phiên bản ứng dụng, cần dùng cùng workload và cùng cách thu thập allocation. Allocation rate cao có thể làm young GC thường xuyên hơn dù live set không tăng.

### 11.5. Application throughput

```text
Application throughput = Số request hoàn thành / Thời gian đo
```

Luôn ghi kèm P95/P99 latency và error rate. Pause ratio thấp nhưng throughput vẫn giảm có thể do concurrent GC tiêu thụ CPU, CPU throttling, allocation stall hoặc bottleneck khác.

## 12. Nhận biết các mẫu GC bất thường

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Young GC tăng nhanh, Old usage sau GC ổn định | Allocation rate cao hoặc workload tạo nhiều object ngắn hạn |
| Old usage sau GC tăng dần qua nhiều cửa sổ | Object sống lâu, retention tăng hoặc memory leak |
| Full GC xuất hiện thường xuyên | Heap pressure, live set lớn, explicit GC hoặc vấn đề promotion/collector |
| Một số pause riêng lẻ rất dài | Evacuation/compaction, live object lớn, heap pressure hoặc collector configuration |
| Tổng pause time cao dù mỗi pause ngắn | Collection xảy ra quá thường xuyên |
| Concurrent cycle kéo dài, CPU cao | Collector cần nhiều CPU để theo kịp allocation hoặc bị giới hạn CPU |
| Allocation rate tăng sau release | Thay đổi code tạo thêm object, buffer hoặc collection tạm |
| Heap sau GC thấp nhưng RSS vẫn cao | Native memory, direct buffer, thread stack, metaspace hoặc memory chưa trả về OS |
| `jdk.DataLoss` trong JFR | Event rate hoặc điều kiện thu thập vượt khả năng ghi/buffer hiện tại |

Với G1, chú ý các thông báo liên quan evacuation failure, humongous allocation và Full GC. Với ZGC hoặc Shenandoah, xem thêm concurrent cycle và allocation stall theo event/log của collector. Tên sự kiện và cách diễn giải phụ thuộc JDK và collector.

Một lần Full GC chưa đủ để kết luận memory leak. Hãy xem nguyên nhân collection, heap sau GC và xu hướng qua nhiều cửa sổ đo.

## 13. Ví dụ thực hành: tạo allocation và đọc GC MXBean

Ví dụ sau tạo các object tạm thời theo từng batch, sau đó đọc chênh lệch số collection và collection time từ MXBean. Chương trình không gọi `System.gc()`.

Tạo file `GcMeasureDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.util.Arrays;
import java.util.List;

public class GcMeasureDemo {
    private static long allocatedBytes;

    public static void main(String[] args) throws Exception {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();
        long[] countsBefore = new long[collectors.size()];
        long[] timesBefore = new long[collectors.size()];

        for (int i = 0; i < collectors.size(); i++) {
            countsBefore[i] = collectors.get(i).getCollectionCount();
            timesBefore[i] = collectors.get(i).getCollectionTime();
        }

        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        byte[][] batch = new byte[128][];
        long started = System.nanoTime();

        for (int round = 0; round < 40; round++) {
            for (int i = 0; i < batch.length; i++) {
                byte[] block = new byte[64 * 1024];
                block[0] = (byte) i;
                block[block.length - 1] = (byte) round;
                batch[i] = block;
                allocatedBytes += block.length;
            }

            Arrays.fill(batch, null);
            Thread.sleep(50);
        }

        long elapsedMillis =
                (System.nanoTime() - started) / 1_000_000;

        System.out.println("ALLOCATED_BYTES=" + allocatedBytes);
        System.out.println("ALLOCATION_WINDOW_MS=" + elapsedMillis);
        System.out.println("READY_FOR_JSTAT");

        // Giữ JVM đủ lâu để jstat có thể lấy mẫu từ terminal khác.
        Thread.sleep(6000);

        for (int i = 0; i < collectors.size(); i++) {
            GarbageCollectorMXBean gc = collectors.get(i);
            long countAfter = gc.getCollectionCount();
            long timeAfter = gc.getCollectionTime();

            System.out.println("GC=" + gc.getName()
                    + ",COUNT_DELTA="
                    + delta(countsBefore[i], countAfter)
                    + ",TIME_DELTA_MS="
                    + delta(timesBefore[i], timeAfter));
        }

        System.out.println("HEAP_USED_AFTER_BYTES="
                + memory.getHeapMemoryUsage().getUsed());
        System.out.println("DEMO_DONE");
    }

    private static long delta(long before, long after) {
        return before < 0 || after < 0 ? -1 : after - before;
    }
}
```

Biên dịch:

```bash
javac --release 17 -g GcMeasureDemo.java
```

Chạy với heap giới hạn và GC log:

```bash
java -Xms64m -Xmx64m "-Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=3,filesize=1M" GcMeasureDemo
```

Chương trình tạo 40 batch, mỗi batch có 128 object kích thước 64 KB. Tổng lượng allocation được đếm là:

```text
40 × 128 × 64 KB = 327,680 KB = 320 MB
```

Khi chương trình in `READY_FOR_JSTAT`, mở terminal thứ hai và tìm PID bằng `jps -l`. Sau đó lấy tám mẫu cách nhau 500 ms:

```bash
jstat -gcutil -t <PID> 500 8
```

Trong GC log, tìm `Pause Young`, `Pause Full`, heap before/after và nguyên nhân collection. Khi chương trình kết thúc, stdout sẽ có dạng:

```text
ALLOCATED_BYTES=335544320
ALLOCATION_WINDOW_MS=2063
READY_FOR_JSTAT
GC=G1 Young Generation,COUNT_DELTA=10,TIME_DELTA_MS=9
GC=G1 Concurrent GC,COUNT_DELTA=0,TIME_DELTA_MS=0
GC=G1 Old Generation,COUNT_DELTA=0,TIME_DELTA_MS=0
HEAP_USED_AFTER_BYTES=43107352
DEMO_DONE
```

Đây là output của một lần chạy trên OpenJDK Zulu 24.0.2 với G1 và heap 64 MB. Thời gian, số collection, collector name và heap usage có thể khác giữa máy hoặc lần chạy. Các số MXBean trong ví dụ là collection count và collection time tích lũy, không phải phép đo pause chính xác.

## 14. Quy trình đo trước và sau khi tối ưu GC

Khi cần đánh giá một thay đổi code hoặc cấu hình GC:

1. Chọn workload có request mix, dữ liệu và concurrency đại diện.
2. Warm-up JVM trước khi bắt đầu đo.
3. Chụp baseline: throughput, P95/P99, CPU, RSS, heap và allocation rate.
4. Thu GC log và JFR trong cùng cửa sổ đo.
5. Thực hiện thay đổi duy nhất cần đánh giá.
6. Chạy lại đúng workload với cùng JDK, CPU/memory limit và thời lượng.
7. So sánh pause distribution, tổng pause, Full GC, allocation rate, live set và throughput.
8. Lặp lại đủ số lần để loại nhiễu.
9. Chỉ kết luận thay đổi tốt hơn nếu nó cải thiện mục tiêu đã đặt mà không làm xấu các chỉ số quan trọng khác.

Không tăng `-Xmx` hoặc đổi collector chỉ vì thấy một lần GC chậm. Heap lớn hơn có thể giảm tần suất collection nhưng tăng footprint và có thể làm một số collection dài hơn. Chọn collector và heap size theo mục tiêu latency, throughput, footprint và giới hạn môi trường.

## 15. Lỗi thường gặp khi đo GC

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Heap usage cao bị kết luận là leak | Chỉ nhìn usage tức thời, chưa xem sau collection | So sánh live set sau nhiều GC và nhiều cửa sổ |
| MXBean collection time bị coi là pause time | Nhầm elapsed collection time với STW pause | Dùng `jdk.GCPhasePause` hoặc GC log |
| GC cycle dài bị coi là ứng dụng bị dừng suốt chu kỳ | Collector làm nhiều việc concurrent | Đo pause riêng và đối chiếu application latency |
| JFR ghi nhận pause lớn bất thường | Bật Heap Statistics trong recording | Tắt heap statistics khi đo latency thông thường |
| JFR file lớn hoặc overhead tăng | Bật nhiều event, threshold quá thấp hoặc ghi quá lâu | Chỉ bật event cần thiết và giới hạn duration |
| jstat không thấy process | Sai PID, user hoặc process namespace | Kiểm tra đúng host/container và tài khoản |
| jstat output thay đổi giữa JDK | Công cụ experimental/unsupported | Kiểm tra `jstat -options` và docs đúng JDK |
| GC log file tăng không giới hạn | Chưa cấu hình rotation | Đặt `filecount` và `filesize` |
| GC count tăng nhưng latency không đổi | Collection ngắn hoặc phần lớn concurrent | So sánh pause, throughput và CPU |
| Full GC xuất hiện sau khi chạy benchmark | Code hoặc profiler chủ động gọi GC | Kiểm tra call `System.gc()` và cấu hình công cụ đo |

## 16. Những nguyên tắc cần nhớ

- Đo GC trong workload đại diện, sau warm-up và trên một cửa sổ đủ dài.
- Theo dõi cả pause time, throughput, allocation rate, live set, CPU và application latency.
- Dùng `-Xlog:gc*` để xem collection, heap và phase; bật rotation cho production.
- Dùng `jstat -gcutil` để quan sát nhanh các pool và bộ đếm; nhớ giới hạn của công cụ.
- Dùng `GarbageCollectorMXBean` cho số lần và collection time tích lũy; không coi đó là STW pause chính xác.
- Dùng JFR `jdk.GCPhasePause` và JMC Sum of Pauses để phân tích thời gian ứng dụng bị dừng.
- Không bật Heap Statistics trong phép đo latency thông thường vì có thể kích hoạt thêm old GC.
- Phân biệt GC cycle concurrent với pause thực tế.
- Không kết luận memory leak chỉ từ heap usage cao hoặc một lần Full GC.
- So sánh baseline và sau tối ưu bằng cùng workload, JDK, collector và giới hạn tài nguyên.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — Garbage Collector Implementation and Performance Measurement](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html)
- [Oracle Java SE 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [Oracle Java SE 24 — The java Command and Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle Java SE 24 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 24 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 24 — MemoryMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 24 — ManagementFactory](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Oracle Java SE 24 — HotSpot Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/24/gctuning/)
