# Đối chiếu GC log, CPU và thời gian dừng

GC log cho biết JVM thu gom bộ nhớ khi nào, loại collection nào xảy ra, heap thay đổi ra sao và ứng dụng bị dừng bao lâu. Tuy nhiên, thời gian dừng (pause time) không phản ánh toàn bộ chi phí của G1. G1 thực hiện nhiều công việc đồng thời với ứng dụng, vì vậy một ứng dụng có pause ngắn vẫn có thể tiêu thụ đáng kể CPU cho GC và làm giảm phần CPU còn lại dành cho xử lý nghiệp vụ.

Java 26 cải thiện G1 qua JEP 522 bằng cách giảm đồng bộ giữa application threads và các GC refinement threads. Cùng release này, HotSpot bổ sung cách ghi nhận CPU time của GC đầy đủ hơn qua `-Xlog:cpu` và `MemoryMXBean.getTotalGcCpuTime()`. Để đánh giá đúng hiệu quả, cần đặt ba nhóm dữ liệu cạnh nhau: **GC log và các phase**, **GC CPU so với process CPU**, và **pause time mà ứng dụng thật sự phải chờ**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích JEP 522 thay đổi card table và write barrier của G1 như thế nào.
- Phân biệt thời gian một GC cycle, stop-the-world pause, CPU time của GC và thời gian xử lý request.
- Bật unified GC logging phù hợp trên JDK 26/27 và đọc các dòng `Pause`, `gc,cpu`, heap summary và phase summary.
- Dùng `-Xlog:cpu` hoặc `MemoryMXBean.getTotalGcCpuTime()` để ước lượng phần CPU mà GC tiêu thụ.
- Dùng JFR để tính tổng pause và tìm phase gây dừng lâu.
- Nhận biết trường hợp pause ngắn nhưng GC CPU cao, pause dài do GC phase hoặc do môi trường, và Full GC do thiếu khả năng thu hồi.
- So sánh JDK 25, 26 và 27 mà không nhầm thay đổi cách đo CPU với thay đổi hiệu năng thực tế.

## 1. Những cải tiến G1 đáng chú ý trong Java 26 và trạng thái hiện tại

### JEP 522 — giảm đồng bộ trong G1

G1 chia heap thành các region và dùng remembered set để biết region khác đang giữ reference trỏ vào region được thu gom. Khi ứng dụng thay đổi một object reference, write barrier được chèn vào mã máy để đánh dấu card tương ứng trong card table. Các GC refinement threads xử lý những card này trong lúc ứng dụng vẫn chạy, phân loại reference và cập nhật remembered set để giảm công việc cần làm trong pause tiếp theo.

Ở thiết kế trước JEP 522, application threads và refinement threads có thể cùng cập nhật hoặc xóa trạng thái của một card. Để tránh mất dấu reference, write barrier phải thực hiện đồng bộ bộ nhớ ở mức chi tiết. Nó cũng phải lưu vị trí card vào refinement buffer để GC thread xử lý sau. Phần mã này làm write barrier lớn và tốn CPU, nhất là ứng dụng thường xuyên thay đổi reference giữa các object.

JEP 522 đưa vào **hai card table**:

1. Application threads ghi card vào bảng đang hoạt động của ứng dụng.
2. Refinement threads xử lý bảng còn lại, độc lập với việc ứng dụng ghi bảng của mình.
3. Khi heuristic dự đoán số card chưa được xử lý có thể vượt lượng công việc phù hợp với pause-time goal, G1 hoán đổi hai bảng một cách nguyên tử.
4. Ứng dụng tiếp tục ghi vào bảng mới; refinement threads quét bảng vừa được chuyển giao.

Thiết kế này loại bỏ phần lớn fine-grained synchronization trong write barrier và không còn cần refinement buffer để lưu từng vị trí card. Write barrier ngắn hơn, ít ảnh hưởng đến tối ưu của JIT hơn và công việc refinement dễ được quét theo vùng nhớ tuần tự.

**Sơ đồ khái niệm:**

```text
Trước JEP 522
Application threads ──┐
                      ├── một card table + đồng bộ chi tiết
Refinement threads ───┘    + refinement buffers

Từ JDK 26
Application threads ─────> Application card table
                                  │
                         atomic table swap
                                  │
Refinement threads ──────> Refinement card table
```

Theo kết quả được công bố trong JEP và bài viết của nhóm phát triển G1, throughput tăng khoảng 5–15% ở workload cập nhật reference nhiều; một số workload ít cập nhật reference cũng có thể tăng tới khoảng 5%. Pause time thường giữ nguyên hoặc giảm nhẹ. Đổi lại, card table bổ sung có chi phí native memory xấp xỉ 0,2% dung lượng heap, khoảng 2 MB cho mỗi 1 GB heap; một phần chi phí có thể được bù bởi việc bỏ refinement buffers và giảm cấu trúc remembered set phụ.

Các con số này là kết quả benchmark trên workload cụ thể, không phải cam kết mọi ứng dụng đều nhanh hơn cùng tỷ lệ. JEP 522 là thay đổi đã hoàn tất trong JDK 26, không phải preview, không cần bật cờ và vẫn là nền tảng G1 ở JDK 27.

### Điều chỉnh mục tiêu GC CPU của G1

JDK 26 đổi mặc định `-XX:GCTimeRatio` của G1 từ `12` sang `24`:

| JDK | Giá trị mặc định | Tỷ lệ mục tiêu theo công thức `1 / (1 + GCTimeRatio)` |
|---|---:|---:|
| JDK 25 | 12 | Khoảng 7,7%, thường làm tròn thành 8% |
| JDK 26 và JDK 27 | 24 | 4% |

Đây là mục tiêu mà heuristic quản lý heap của G1 dùng để cân bằng CPU dành cho GC với CPU dành cho ứng dụng. Khi GC tiêu thụ tỷ lệ CPU cao hơn mục tiêu trong một khoảng thời gian, G1 có thể tăng heap để giảm tần suất hoặc chi phí thu gom; khi hoạt động GC thấp, G1 có thể thu nhỏ heap. Đây **không phải giới hạn cứng** bảo đảm GC luôn tiêu thụ tối đa 4% CPU. Nếu `-Xmx` hoặc giới hạn bộ nhớ của container không cho phép heap tăng, G1 không thể dùng thêm heap để đáp ứng mục tiêu.

Khi so sánh JDK 25 với JDK 26, hãy ghi nhận thay đổi mặc định này. Nếu muốn cô lập tác động của JEP 522, có thể chạy thêm một phép đo kiểm soát với cùng `-XX:GCTimeRatio` và cùng giới hạn heap trên cả hai JDK; sau đó chạy một phép đo khác với mặc định để phản ánh hành vi triển khai thực tế.

### Những thay đổi còn liên quan trong JDK 27

JDK 27 tiếp tục giữ cải tiến JEP 522 và có hai thay đổi cần biết khi so sánh log trên môi trường hiện tại:

- Qua JEP 523, G1 trở thành collector mặc định trong mọi môi trường HotSpot nếu người dùng không chỉ định collector. JDK 26 có thể chọn Serial GC trong môi trường rất hạn chế; JDK 27 chọn G1 ngay cả trong container nhỏ hoặc máy một CPU. Serial GC vẫn có thể được chọn tường minh bằng `-XX:+UseSerialGC`.
- Mặc định `-XX:MinHeapFreeRatio` và `-XX:MaxHeapFreeRatio` của G1 đổi từ `40`/`70` thành `0`/`100`, để các heuristic thu/phóng heap không xung đột với việc điều chỉnh heap dựa trên CPU của GC. Nếu ứng dụng đã đặt tường minh các cờ này, giá trị của ứng dụng vẫn được giữ.

Vì vậy, trước khi phân tích hiệu năng, hãy xác nhận collector thực tế trong log. Không giả định cùng một ứng dụng tự động dùng cùng collector khi chạy JDK 25, 26 và 27 trên các container có cấu hình CPU/RAM khác nhau.

## 2. Bốn loại thời gian không nên đánh đồng

| Chỉ số | Đo điều gì? | Đọc ở đâu? |
|---|---|---|
| GC cycle elapsed time | Thời gian từ lúc một chu kỳ GC bắt đầu tới lúc kết thúc, có thể bao gồm nhiều phase concurrent và nhiều pause | Các dòng cycle/phase trong GC log |
| Stop-the-world pause time | Khoảng thời gian application threads bị dừng để JVM thực hiện một thao tác GC tại safepoint | Dòng `Pause ...` trong GC log; JFR `jdk.GCPhasePause` |
| GC CPU time | Tổng CPU time các thread/công việc GC đã tiêu thụ; nhiều thread có thể cộng dồn CPU time song song | JDK 26 `-Xlog:cpu`, `MemoryMXBean.getTotalGcCpuTime()` |
| Request/operation latency | Thời gian người dùng hoặc tác vụ nghiệp vụ phải chờ để hoàn tất | APM, metrics ứng dụng, load test hoặc tracing |

G1 thực hiện concurrent marking và remembered-set refinement trong khi ứng dụng vẫn chạy. Các phase đó có thể tiêu thụ CPU nhưng không phải toàn bộ đều làm ứng dụng dừng. Vì thế:

- Pause ngắn không chứng minh GC rẻ về CPU.
- GC CPU time lớn hơn pause time là điều bình thường khi collector chạy song song hoặc concurrent.
- GC cycle kéo dài không có nghĩa ứng dụng bị dừng suốt cả cycle.
- Request latency không bằng một pause riêng lẻ. Một request dài có thể bị gián đoạn bởi nhiều pause ngắn và còn chịu ảnh hưởng của CPU contention, lock, I/O hoặc network.

Khi đánh giá ảnh hưởng lên ứng dụng, hãy quan sát cả từng pause dài nhất, phân vị pause, tổng pause trong khoảng đo và request latency p95/p99.

## 3. Bật unified GC logging trên JDK 26/27

JDK hiện hành dùng Unified Logging với `-Xlog`. Một cấu hình chẩn đoán có thể bắt đầu như sau:

```bash
java \
  -Xms4g -Xmx4g \
  -Xlog:gc*=info,gc+phases=debug,gc+cpu=info,cpu=info,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

Ý nghĩa các phần chính:

- `gc*=info`: ghi các thông điệp GC ở mức info, gồm loại collection, nguyên nhân, heap trước/sau và các phase chính.
- `gc+phases=debug`: ghi thời gian chi tiết của các phase như `Merge Heap Roots`, `Scan Heap Roots`, `Object Copy` và `Reference Processing`.
- `gc+cpu=info`: ghi phần User/Sys/Real gắn với pause GC.
- `cpu=info`: trên JDK 26 ghi bảng tổng hợp CPU của process và GC khi JVM kết thúc.
- `safepoint=info`: giúp đối chiếu thời gian và hoạt động đưa thread tới safepoint.
- `filecount=5,filesize=20M`: xoay vòng log để giới hạn dung lượng file.

`-Xms4g -Xmx4g` chỉ là cấu hình minh họa cho một phép đo heap cố định; không sao chép giá trị này nếu workload hoặc giới hạn container khác. Trong production, cân nhắc log rotation và dung lượng đĩa. Có thể bắt đầu bằng mức `info`, sau đó chỉ bật phase `debug` trong lần chẩn đoán có mục tiêu vì log chi tiết làm tăng lượng I/O và dung lượng ghi.

Nếu chỉ muốn kiểm tra collector được chọn, có thể chạy:

```bash
java -Xlog:gc+init=info -version
```

Đối chiếu dòng khởi tạo GC và các dòng đầu của log ứng dụng để chắc chắn đang quan sát G1. Khi cần log nhiều tag, dùng `java -Xlog:help` trên chính JDK đích để kiểm tra tag và cú pháp được hỗ trợ.

Không dùng các cờ GC logging cũ như `-XX:+PrintGCDetails`, `-XX:+PrintGCDateStamps` hoặc `-Xloggc`; hãy dùng Unified Logging. Cách viết `-Xlog:gc*` là cú pháp hiện hành để thu thập GC log chi tiết.

## 4. Đọc một dòng pause và dòng CPU tương ứng

Ví dụ rút gọn dưới đây là log minh họa:

```text
[120.000s][info][gc] GC(42) Pause Young (Normal) (G1 Evacuation Pause) 1G->600M(4G) 18.2ms
[120.000s][info][gc,cpu] GC(42) User=0.12s Sys=0.01s Real=0.02s
```

Đọc dòng thứ nhất:

- `GC(42)` là mã định danh để ghép các dòng thuộc cùng collection.
- `Pause Young` là pause thu gom vùng young; `G1 Evacuation Pause` mô tả hoạt động evacuation.
- `1G->600M` là lượng heap đang dùng trước và sau pause.
- `(4G)` là dung lượng heap tại thời điểm đó, không nhất thiết là `-Xmx` trong mọi cấu hình.
- `18.2ms` là thời gian pause theo wall clock.

Đọc dòng thứ hai:

- `User=0.12s` là CPU time chạy ở user mode trong quá trình pause.
- `Sys=0.01s` là CPU time ở system mode.
- `Real=0.02s` là thời gian thực đã trôi qua.

User + Sys xấp xỉ 0,13 giây CPU trong khi wall-clock chỉ 0,02 giây. Điều đó tương ứng trung bình khoảng 6,5 CPU cores làm việc trong khoảng pause này. CPU time được cộng dồn trên các thread; vì vậy tổng CPU time có thể lớn hơn thời gian thực. Nó không có nghĩa ứng dụng bị dừng 130 ms. Ứng dụng bị dừng khoảng 20 ms theo dòng pause.

Nếu `Real` lớn hơn nhiều so với `User + Sys`, có thể JVM đã không được cấp đủ CPU hoặc bị trì hoãn bởi hệ điều hành, hypervisor, container quota, page fault hay I/O. Nếu `Sys` cao bất thường, kiểm tra hoạt động kernel, cấp phát/thu hồi bộ nhớ từ OS, Transparent Huge Pages và I/O ghi log. Đối chiếu cùng lúc với CPU throttling và tải của host trước khi quy kết cho G1.

## 5. Đọc bảng CPU tổng hợp của JDK 26

JDK 26 bổ sung `-Xlog:cpu`, ghi bảng tổng hợp khi JVM kết thúc. Ví dụ trích từ JDK 26 Release Notes:

```text
[info][cpu] === CPU time Statistics =============================================
[info][cpu] Process
[info][cpu]   Total                 410.2789  100.00  6.5
[info][cpu]   Garbage Collection    124.8134   30.42  2.0
[info][cpu]     GC Threads          124.5082   30.35  2.0
[info][cpu]     VM Thread             0.3052    0.07  0.0
[info][cpu] =====================================================================
```

Các cột lần lượt là CPU seconds, phần trăm CPU time của process và số CPU cores trung bình được sử dụng. Trong ví dụ:

- Process tiêu thụ khoảng 410,3 CPU seconds, trung bình 6,5 cores trong khoảng thời gian đo.
- GC được ghi nhận khoảng 124,8 CPU seconds, chiếm 30,42% tổng CPU time của process.
- GC Threads chiếm phần lớn chi phí GC; VM Thread có phần nhỏ hơn.

Con số 30,42% là tỷ trọng trong CPU time của process, không phải 30,42% wall-clock pause và cũng không phải 30,42% tổng CPU của toàn host. Một process có thể dùng nhiều cores đồng thời nên CPU seconds của process có thể lớn hơn wall-clock seconds.

JDK 26 cải thiện việc hạch toán GC CPU trên toàn collector. Phần này bao gồm cả CPU time trong pause, concurrent work như marking/refinement và công việc liên quan như string deduplication. Vì vậy, tổng GC CPU trong JDK 26 có thể cao hơn số đo từ công cụ cũ hoặc từ JDK trước đó vốn không tính đầy đủ concurrent work. Đừng tự động kết luận JDK 26 chậm hơn chỉ vì con số GC CPU mới cao hơn; hãy so sánh cùng một phương pháp đo và đối chiếu throughput, latency, heap và pause.

## 6. Đo GC CPU trong ứng dụng bằng MemoryMXBean

Java 26 bổ sung `MemoryMXBean.getTotalGcCpuTime()`, trả về tổng CPU nanoseconds đã được hạch toán cho GC. Có thể lấy delta trước và sau một khoảng workload rồi so sánh với CPU time của process:

```java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

public class GcCpuMeasurement {
    public static void main(String[] args) {
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        OperatingSystemMXBean osBean = ManagementFactory.getPlatformMXBean(
                OperatingSystemMXBean.class);

        if (osBean == null) {
            throw new IllegalStateException(
                    "Process CPU time không được hỗ trợ trên runtime này");
        }

        // Chạy warm-up trước, rồi đo một khoảng workload đủ dài.
        runWorkload();

        long gcStart = memoryBean.getTotalGcCpuTime();
        long processStart = osBean.getProcessCpuTime();
        long wallStart = System.nanoTime();

        runMeasuredWorkload();

        long wallElapsed = System.nanoTime() - wallStart;
        long processElapsed = osBean.getProcessCpuTime() - processStart;
        long gcElapsed = memoryBean.getTotalGcCpuTime() - gcStart;

        if (gcStart < 0 || processStart < 0
                || gcElapsed < 0 || processElapsed <= 0 || wallElapsed <= 0) {
            throw new IllegalStateException("Không có đủ dữ liệu CPU time để tính");
        }

        double gcCpuShare = 100.0 * gcElapsed / processElapsed;
        double gcCoresAverage = (double) gcElapsed / wallElapsed;

        System.out.printf("GC / process CPU: %.2f%%%n", gcCpuShare);
        System.out.printf("Average CPU cores used by GC: %.2f%n", gcCoresAverage);
    }

    private static void runWorkload() {
        // Thay bằng workload thật; không dùng System.gc() để tạo số đo.
    }

    private static void runMeasuredWorkload() {
        // Chạy đủ lâu và với dữ liệu đại diện cho ứng dụng.
    }
}
```

`getTotalGcCpuTime()` trả về số nanoseconds tích lũy xấp xỉ, có thể bao gồm overhead GC nên giá trị đôi khi vẫn lớn hơn 0 dù chưa có collection pause. API trả `-1` nếu runtime không hỗ trợ hoặc không có dữ liệu. Trong HotSpot, phép đo gồm các thành phần GC như driver threads, worker threads, VM operations và string deduplication nếu được bật. `OperatingSystemMXBean.getProcessCpuTime()` thuộc package `com.sun.management` trong module `jdk.management`; với ứng dụng dùng module path, khai báo `requires jdk.management;` nếu cần.

Hai tỷ lệ trong ví dụ trả lời hai câu hỏi khác nhau:

- `gcElapsed / processElapsed`: phần trăm CPU time của process được hạch toán cho GC.
- `gcElapsed / wallElapsed`: số cores trung bình mà GC tiêu thụ trong khoảng đo.

Đo một khoảng quá ngắn dễ bị nhiễu bởi startup, JIT warm-up và độ phân giải của OS. Hãy warm-up, đo nhiều iteration đủ dài, dùng cùng một workload và không gọi `System.gc()` để cố tạo GC vì nó thay đổi hành vi đang cần quan sát.

## 7. Đo tổng pause bằng JFR

GC log phù hợp để đọc nguyên nhân và phase. Java Flight Recorder (JFR) bổ sung dữ liệu sự kiện có timestamp và duration để tính tổng thời gian ứng dụng bị dừng. Oracle khuyến nghị dùng event `jdk.GCPhasePause` để tính:

- Tổng pause trong toàn recording.
- Pause lớn nhất.
- Trung bình pause và phân bố theo GC ID hoặc loại pause.
- Tỷ lệ tổng pause trên wall-clock duration của khoảng đo.

Khởi động ứng dụng với một profiling recording:

```bash
java \
  -XX:StartFlightRecording:filename=gc-profile.jfr,settings=profile,dumponexit=true \
  -jar app.jar
```

Sau khi JVM kết thúc, in các pause event:

```bash
jfr print --events jdk.GCPhasePause gc-profile.jfr
```

Có thể mở file trong JDK Mission Control để xem đồ thị GC pause, sum of pauses, allocation pressure và các event liên quan. Không bật Heap Statistics trong recording benchmark latency thông thường: tùy chọn này có thể kích hoạt old GC ở đầu và cuối recording, làm thay đổi chính số pause đang đo. Với profiling hiệu năng, dùng recording profile tiêu chuẩn trước rồi chỉ bật dữ liệu heap statistics khi điều tra memory leak/live set.

Tổng pause là thước đo tốt cho mức độ ứng dụng bị dừng bởi GC. Nhưng nó không đo concurrent GC CPU. Hãy đặt kết quả JFR cạnh `-Xlog:cpu` hoặc `getTotalGcCpuTime()` để không bỏ sót chi phí nền.

## 8. Đối chiếu heap, phase và CPU để tìm nguyên nhân

Khi có một đợt pause tăng, hãy ghép các dòng cùng GC ID và xem các chỉ số theo thứ tự:

1. **Loại collection và nguyên nhân:** `Pause Young`, `Pause Mixed`, `Pause Remark`, `Pause Cleanup` hay `Pause Full`; kiểm tra cause như allocation failure hoặc explicit GC.
2. **Heap trước/sau:** lượng dùng trước và sau collection, dung lượng heap, Eden/Survivor/Old regions và Humongous regions.
3. **Phase chiếm thời gian:** `Merge Heap Roots`, `Scan Heap Roots`, `Object Copy`, `Reference Processing`, `Other` hoặc các phase marking.
4. **CPU trong pause:** User, Sys và Real để biết pause tốn CPU hay bị trì hoãn bởi môi trường.
5. **CPU tổng của GC:** so với CPU process để biết concurrent GC đang chiếm bao nhiêu tài nguyên ngoài pause.
6. **Tác động nghiệp vụ:** throughput, request p95/p99, error rate và CPU throttling cùng khoảng thời gian.

Các dấu hiệu thường gặp:

| Dấu hiệu | Cách diễn giải | Hướng điều tra |
|---|---|---|
| Pause ngắn, GC CPU share cao | Nhiều công việc GC chạy concurrent; pause không đại diện tổng chi phí | Kiểm tra concurrent marking/refinement, allocation rate, heap headroom và CPU quota |
| Pause dài, GC CPU cao, `Object Copy` lớn | Nhiều live object phải di chuyển trong collection set | Xem live set, kích thước young generation, survivor/promotion và tỷ lệ object sống |
| `Merge Heap Roots` hoặc `Scan Heap Roots` chiếm nhiều thời gian | Công việc remembered set/card scan lớn | Bật `gc+phases=debug`, kiểm tra pending/scanned cards và đặc điểm reference graph |
| `Reference Processing` kéo dài | Nhiều soft/weak/phantom references hoặc xử lý reference tốn thời gian | Kiểm tra ứng dụng dùng Reference API và số lượng reference được xử lý |
| Pause Real dài hơn nhiều User + Sys | JVM bị chờ CPU hoặc hệ điều hành trì hoãn | Kiểm tra CPU throttling, host oversubscription, page fault, THP và I/O |
| Nhiều pause nhỏ sát nhau | Tần suất GC cao; tổng gián đoạn có thể lớn dù từng pause ngắn | Tính sum of pauses, allocation rate, heap size và khoảng cách giữa các pause |
| `Pause Full` lặp lại, heap sau GC vẫn cao | Live set lớn, heap thiếu headroom, marking không kịp hoặc có memory leak | Kiểm tra old occupancy, evacuation failure, humongous regions, `System.gc()` và retained objects |
| Process CPU cao nhưng GC CPU thấp, pause thấp | CPU chủ yếu do ứng dụng, JIT hoặc công việc khác | Dùng JFR/CPU profiler để tìm hot methods, lock và I/O |

G1 có thể thực hiện một số phase concurrent trong lúc application chạy. Không cộng thời gian của mọi phase concurrent rồi gọi đó là pause. Dùng dòng `Pause` hoặc `jdk.GCPhasePause` để tính thời gian dừng; dùng CPU accounting để tính chi phí CPU.

### Ví dụ: pause thấp không có nghĩa GC miễn phí

Giả sử trong một khoảng chạy 60 giây, log và CPU accounting cho thấy:

| Chỉ số | Giá trị minh họa |
|---|---:|
| Tổng GC pause | 0,8 giây |
| Pause lớn nhất | 24 ms |
| GC CPU time | 18 giây |
| Process CPU time | 50 giây |
| GC CPU share | 36% |

Ứng dụng chỉ bị dừng tổng cộng khoảng 0,8 giây, nhưng GC đã dùng 18 CPU seconds trong 50 CPU seconds của process. Phần lớn công việc GC được thực hiện ngoài các pause. Nếu máy chủ đang bị giới hạn CPU, công việc concurrent đó có thể cạnh tranh trực tiếp với request threads và làm throughput hoặc request latency xấu đi dù dashboard pause time vẫn đẹp.

### Ví dụ: pause dài nhưng không phải G1 tiêu tốn nhiều CPU

Nếu một pause có `Real=250ms` nhưng `User=35ms` và `Sys=5ms`, phần chênh lệch khoảng 210ms có thể là thời gian chờ lịch CPU hoặc một chậm trễ của hệ điều hành. Hãy kiểm tra host/container và safepoint logs. Không nên chỉ tăng heap hoặc đổi collector trước khi xác định thời gian đó thực sự được tiêu thụ ở đâu.

## 9. Dùng phase log để khoanh vùng vấn đề G1

Khi pause dài, `-Xlog:gc+phases=debug` giúp xác định phần việc cụ thể. Một số phase cần biết:

- `Merge Heap Roots`: hợp nhất các remembered set để chuẩn bị quét reference vào collection set.
- `Scan Heap Roots`: quét card và root để tìm reference tới object sẽ được evacuate.
- `Object Copy`: sao chép live objects ra khỏi region được thu gom và cập nhật reference.
- `Reference Processing`: xử lý `java.lang.ref.Reference` theo loại reference và chính sách tương ứng.
- `Concurrent Mark`: đánh dấu object còn sống trong old generation; phần lớn công việc này chạy đồng thời với ứng dụng, nhưng có các pause Remark/Cleanup để hoàn tất và cập nhật dữ liệu.

Nếu `Merge Heap Roots` và `Scan Heap Roots` chiếm phần lớn pause, xem `gc+ergo+cset=debug` và log phase để hiểu collection set, predicted time, pending cards và scanned cards. Oracle G1 tuning guide đề xuất xem xét region size và remembered-set granularity khi hai phase này chiếm tỷ trọng rất cao; thay đổi các cờ đó có trade-off về lượng object phải copy và native memory, nên chỉ thử sau khi có bằng chứng từ log.

Nếu `Object Copy` chiếm nhiều thời gian, hãy kiểm tra số lượng live objects trong collection set và cấu hình young generation. Nếu `Reference Processing` chiếm nhiều thời gian, kiểm tra việc tạo và giữ các `SoftReference`, `WeakReference` hoặc `PhantomReference`. Nếu pause là Full GC, tìm nguyên nhân trước đó: evacuation failure, allocation failure, humongous allocation, explicit `System.gc()` hoặc heap không đủ chứa live set.

## 10. Đánh giá hiệu quả JEP 522 bằng phép đo có kiểm soát

Để so sánh JDK 25 với JDK 26/27, không chỉ so một dòng pause. Hãy chạy cùng một workload và ghi các điều kiện:

- Cùng phần cứng hoặc cùng giới hạn CPU/RAM của container.
- Cùng ứng dụng, dependency, dữ liệu đầu vào và mức đồng thời.
- Cùng collector được chọn tường minh; với phép thử G1, dùng `-XX:+UseG1GC` để tránh JDK 25 chọn Serial trong môi trường nhỏ.
- Cùng heap size, `-Xms`, `-Xmx`, và các cờ tuning khác trong phép thử cô lập.
- Warm-up JIT trước khi lấy số liệu; đo nhiều lần và so sánh phân bố thay vì chỉ một lần chạy.
- Ghi throughput, request p95/p99, GC CPU share, average GC cores, tổng pause, pause p99/max, số lần GC và heap sau GC.

Nên thực hiện hai nhóm so sánh:

1. **So sánh kiểm soát:** cố định `GCTimeRatio`, heap, collector và các cờ khác giữa các JDK để giảm tác động của thay đổi mặc định khi đánh giá JEP 522.
2. **So sánh cấu hình mặc định:** chạy JDK 26/27 với default tương ứng để xem kết quả thực tế khi nâng cấp, bao gồm thay đổi mục tiêu GC CPU và việc G1 trở thành collector mặc định trong mọi môi trường ở JDK 27.

JDK 26 cải thiện hạch toán GC CPU đầy đủ hơn so với JDK trước. Do đó, nếu GC CPU share tăng sau khi nâng cấp nhưng pause và throughput không xấu đi, hãy kiểm tra xem đó có phải do phép đo mới đã tính thêm concurrent GC work hay không. Không dùng CPU metric từ JDK 25 và JDK 26 như hai phép đo hoàn toàn đồng nhất nếu cách hạch toán khác nhau.

JEP 522 hướng tới giảm overhead của G1, đặc biệt với workload cập nhật nhiều object references. Một benchmark tạo nhiều primitive arrays hoặc workload không có nhiều reference writes có thể không thể hiện rõ lợi ích. Chọn workload đại diện cho hành vi thực tế của ứng dụng, nhất là các thao tác cập nhật graph object, collection, cache và cấu trúc dữ liệu có nhiều reference.

## 11. Điều chỉnh G1 sau khi đã xác định nguyên nhân

Ưu tiên giữ cấu hình mặc định của G1, sau đó chỉ thay đổi tham số khi log và benchmark chỉ ra một vấn đề cụ thể. Một số nguyên tắc:

- `-XX:MaxGCPauseMillis` là mục tiêu gợi ý, không phải SLA hoặc bảo đảm mọi pause đều nhỏ hơn giá trị đó.
- Nếu throughput quan trọng hơn pause, có thể nới pause-time goal hoặc cung cấp thêm heap headroom; đổi lại pause có thể dài hơn.
- Tránh cố định young generation bằng `-Xmn`, `-XX:NewRatio` hoặc cấu hình tương đương khi muốn G1 tự điều chỉnh theo pause-time goal. Cố định young generation có thể vô hiệu hóa khả năng điều khiển pause của G1.
- Không tắt concurrent refinement chỉ vì GC CPU cao. Tắt refinement có thể chuyển nhiều công việc vào pause và làm latency tăng đáng kể.
- Khi GC CPU share cao, xem allocation rate, heap headroom và live set trước khi tăng số GC threads hoặc thay collector.
- Khi Full GC xảy ra, kiểm tra cause và heap sau GC. Nếu heap sau GC vẫn gần đầy, cần xử lý live set, leak hoặc heap limit thay vì chỉ tinh chỉnh pause-time goal.
- Trong container, xác nhận JVM nhận đúng CPU quota và memory limit. Một GC thread pool lớn so với CPU được cấp có thể tạo contention dù host còn CPU tổng.

Đừng sao chép các cờ từ một bài viết cũ hoặc từ collector khác. Dùng tài liệu G1 tuning của JDK đang triển khai và kiểm tra bằng `java -XX:+PrintFlagsFinal -version` hoặc log khởi tạo tương ứng khi cần xác minh giá trị hiệu lực.

## 12. Bài tập thực hành

Một dịch vụ Java xử lý nhiều object reference trong cache. Sau khi nâng từ JDK 25 lên JDK 26, dashboard cho thấy tổng pause gần như không đổi nhưng CPU process tăng. Nhóm cần xác định thay đổi này đến từ JEP 522, từ cách đo CPU mới hay từ workload.

**Yêu cầu:**

1. Chạy ứng dụng trên JDK 26 với G1 và bật GC log gồm `gc*=info`, `gc+phases=debug`, `gc+cpu=info`, `cpu=info` và `safepoint=info`.
2. Ghi nhận các dòng `Pause Young`, `Pause Mixed`, `Pause Remark`, `Pause Cleanup` và `Pause Full`; tính tổng pause và pause lớn nhất.
3. Đọc `User`, `Sys`, `Real` cho một số pause; giải thích vì sao tổng User + Sys có thể lớn hơn Real.
4. Đọc bảng `-Xlog:cpu` ở cuối tiến trình; tính phần trăm GC CPU trên process CPU và số cores trung bình của GC.
5. Dùng `MemoryMXBean.getTotalGcCpuTime()` và `OperatingSystemMXBean.getProcessCpuTime()` để đo delta CPU trong một khoảng workload đủ dài.
6. Tạo JFR recording và dùng `jfr print --events jdk.GCPhasePause` để xác nhận tổng pause độc lập với GC log.
7. Lặp lại trên JDK 25 và JDK 27 với cùng collector, heap và workload; ghi nhận khác biệt default `GCTimeRatio` và việc JDK 27 dùng G1 làm mặc định mọi môi trường.
8. Giải thích vì sao GC CPU time được hạch toán đầy đủ hơn ở JDK 26 có thể tăng so với số đo JDK 25 ngay cả khi pause không đổi.
9. Đề xuất thay đổi chỉ khi phase log, CPU metrics và request latency cùng chỉ ra một nguyên nhân cụ thể.

**Kết quả mong đợi:**

- Người học phân biệt được GC cycle, stop-the-world pause, GC CPU time và request latency.
- Có thể tính tổng pause, pause lớn nhất, GC CPU share và average GC cores.
- Nhận ra concurrent GC work có thể làm GC CPU cao trong khi pause thấp.
- Biết dùng `gc+phases=debug` để tìm phase gây pause và `gc+cpu` để phân tích User/Sys/Real.
- Giải thích được JEP 522 giảm đồng bộ bằng hai card table và hiểu mức cải thiện benchmark không phải cam kết cho mọi workload.
- So sánh JDK 25/26/27 trong điều kiện kiểm soát và không coi thay đổi cách hạch toán CPU là regression hiệu năng.

## Tài liệu tham khảo

- [JEP 522: G1 GC: Improve Throughput by Reducing Synchronization](https://openjdk.org/jeps/522): thiết kế hai card table và mục tiêu giảm đồng bộ của G1 trong JDK 26.
- [New Write Barriers for G1 — Thomas Schatzl](https://tschatzl.github.io/2025/02/21/new-write-barriers.html): giải thích card marking, write barrier, refinement và tác động throughput/pause/native memory.
- [JDK 26 G1/Parallel/Serial GC changes — Thomas Schatzl](https://tschatzl.github.io/2026/02/26/jdk26-g1-serial-parallel-gc-changes.html): các thay đổi GC trong JDK 26, gồm GC CPU accounting, G1 CPU target và JEP 522.
- [JDK 26 Release Notes — New CPU Time Logging](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): định dạng bảng `-Xlog:cpu` được in khi JVM kết thúc.
- [MemoryMXBean — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): hợp đồng và giới hạn của `getTotalGcCpuTime()`.
- [Garbage-First Garbage Collector Tuning — Java SE 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html): chẩn đoán Full GC, phase timing, User/Sys/Real, throughput và heap sizing.
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): cách phân tích GC pause, sum of pauses và allocation pressure bằng JFR.
- [JDK 27 G1/Parallel/Serial GC changes — Thomas Schatzl](https://tschatzl.github.io/2026/08/10/jdk27-g1-serial-parallel-gc-changes.html): cập nhật G1 trong JDK 27.
- [JEP 523: Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523): thay đổi collector mặc định từ JDK 27.
- [Garbage-First Garbage Collector Tuning — Java SE 27](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-garbage-collector-tuning.html): xác nhận G1 defaults, `GCTimeRatio=24` và khuyến nghị tuning hiện hành.
