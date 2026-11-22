# Shenandoah: Kiểm chứng bằng log, tải đại diện và giới hạn tài nguyên trong Java

> **Ngữ cảnh:** Bài thuộc nhóm **Shenandoah**, module **Java 15**, tập trung vào cách **chứng minh collector có đạt mục tiêu độ trễ và sử dụng bộ nhớ hay không** bằng số liệu thực: log GC, JFR, workload đại diện, giới hạn heap/CPU/RAM và quy trình so sánh có kiểm soát. Đây là kiến thức **còn áp dụng cho các JDK hiện hành**, không phải một tập hợp cờ tối ưu hóa đã lỗi thời. Ví dụ dùng **Java 17+** và HotSpot/OpenJDK **có build Shenandoah**. Đặc biệt, **Generational Shenandoah được hoàn thiện trong JDK 25 (JEP 521)** và có thể chọn bằng `-XX:ShenandoahGCMode=generational` trong các build hỗ trợ; **không giả định tất cả bản phân phối Java đều có Shenandoah hoặc tự động chọn generational mode**.

## 1. “Đã bật Shenandoah” không phải bằng chứng đạt SLO

Shenandoah là bộ thu gom rác có nhiều pha **concurrent**: JVM thực hiện phần lớn công việc truy vết, thu hồi hoặc di chuyển các đối tượng trong khi các luồng Java tiếp tục chạy. Nhờ đó có thể giảm những lần tạm dừng ứng dụng dài do GC.

Tuy nhiên, một câu lệnh khởi động thành công:

```bash
java -XX:+UseShenandoahGC -Xms256m -Xmx2g MyApp
```

chỉ chứng minh runtime **chấp nhận cấu hình** và khởi động collector, **không** chứng minh:

- Request p99/p99.9 đáp ứng SLO.
- Không có **allocation pacing**, **degenerated GC** hay **Full GC**.
- JVM có đủ CPU để collector bắt kịp allocation.
- `-Xmx2g` đủ cho live set và burst.
- Container không bị giới hạn RAM/CPU hoặc OOMKilled.
- Mọi lần trả lời request đều nhanh.
- Cùng config sẽ tốt trên mọi hardware/JDK.

Một phép kiểm chứng có giá trị phải kết hợp **bốn lớp bằng chứng**:

```text
                 Kết quả cần chứng minh
                SLO p95/p99/p99.9, throughput
                           |
        +------------------+-------------------+
        |                  |                   |
        v                  v                   v
   GC runtime          Workload             OS/container
   GC log/JFR          tải thật             CPU + RSS + cgroup
   pause/pacing        steady + burst       CPU throttling
   degen/full          retention            memory/OOM kill
        |                  |                   |
        +------------------+-------------------+
                           |
                    Kết luận có điều kiện
            (JDK, mode, heap, CPU, tải, thời gian)
```

**Nguyên tắc trung tâm:** kiểm chứng GC bằng **độ trễ end-to-end của ứng dụng** cùng với **dấu vết collector**, không chỉ bằng một dòng “Using Shenandoah” hoặc một biểu đồ pause time.

## 2. Xác nhận JDK và Shenandoah thực sự có sẵn

Shenandoah được tích hợp trong các bản OpenJDK hỗ trợ nó, nhưng **không phải mọi JDK vendor/build/platform đều phân phối hoặc bật collector này**. Vì vậy, bước đầu tiên của thí nghiệm là kiểm tra chính JVM sẽ chạy workload.

```bash
java -version
java -XX:+UseShenandoahGC -Xms128m -Xmx256m -Xlog:gc=info -version
```

Đây là các lệnh kiểm tra độc lập, không cần class ứng dụng. Trên một bản HotSpot/OpenJDK có Shenandoah và tương thích với flags, GC log thường có thông báo chọn Shenandoah. Nếu JVM báo **unrecognized VM option** hoặc **support for Shenandoah not included in this VM**, đó là **hạn chế runtime**, không phải lý do để chuyển sang các flag Shenandoah cũ hay giả vờ bài kiểm thử đã chạy.

Đọc cấu hình thực tế:

```bash
java -XX:+UseShenandoahGC -XX:+PrintFlagsFinal -version
```

Trong output dài, tìm:

```text
UseShenandoahGC
ShenandoahGCMode
ShenandoahGCHeuristics
InitialHeapSize
MaxHeapSize
ConcGCThreads
ParallelGCThreads
ActiveProcessorCount
```

Không chép **giá trị mặc định** của một máy để khẳng định máy khác cũng vậy. Những giá trị phụ thuộc JDK build, OS, CPU, container, RAM và flags được triển khai.

### Chọn mode theo đúng phiên bản

| Môi trường | Khuyến nghị dùng kiến thức hiện hành |
| --- | --- |
| JDK 17/21 có Shenandoah | Kiểm tra mode collector mà build hỗ trợ; không truyền cờ `generational` của các đời JDK mới nếu runtime không hỗ trợ |
| JDK 24 có Generational Shenandoah | Đó là **mốc thử nghiệm lịch sử** trước JDK 25; khi cần triển khai mới, ưu tiên JDK được hỗ trợ và mode đã được hoàn thiện |
| JDK 25+ có Shenandoah | Có thể chọn **`-XX:ShenandoahGCMode=generational`** theo JEP 521, hoặc mode `satb` khi phù hợp; ghi rõ mode trong kết quả kiểm thử |
| Build không chứa Shenandoah | Bài thí nghiệm Shenandoah **không khả dụng**; chọn một JDK được tổ chức hỗ trợ và có collector thay vì bỏ qua lỗi |

**Generational Shenandoah không tự là mặc định trên mọi JDK.** Trong tài liệu lệnh Java hiện đại, `ShenandoahGCMode=satb` vẫn được mô tả là giá trị mặc định ở những build liên quan; `generational` là lựa chọn phải xác nhận qua chính runtime. JDK 25 hoàn thiện mode generational, nhưng **không làm tất cả bản JDK khác đồng nhất**.

Với **JDK 25+ có hỗ trợ**, một lệnh mẫu:

```bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xms256m -Xmx2g MyApp
```

`MyApp` là tên class ứng dụng do bạn cung cấp. **Lệnh này không được hứa hẹn tương thích với mọi JDK 17/21 hoặc mọi vendor**; không bật cờ experimental đời JDK cũ trong cấu hình sản xuất JDK 25+.

## 3. Định nghĩa tiêu chí PASS/FAIL trước khi chạy thử

Không nên chạy load test rồi mới chọn một metric đẹp nhất để tuyên bố thành công. Hãy ghi rõ các mục tiêu:

| Nhóm | Metric phải có | Câu hỏi kiểm chứng |
| --- | --- | --- |
| Trải nghiệm | p50, p95, **p99**, p99.9 response latency | Có đạt **SLO đã ký** khi tải bình thường, burst và hồi phục không? |
| Hiệu năng | throughput/RPS, error rate, timeout | Tăng hoặc giảm do GC hay do ứng dụng/quy trình tải? |
| GC | STW pause, concurrent cycle, degenerated/full GC | Shenandoah có chạy chủ yếu theo đường concurrent không? |
| Áp lực cấp phát | allocation rate, retained/live data, GC pacing | Luồng ứng dụng có phải chờ cấp phát vì GC không theo kịp? |
| Bộ nhớ | heap used, committed, `-Xmx`, process RSS | Có đủ heap headroom và RAM process không? |
| CPU | process CPU, GC CPU, cgroup throttling, run queue | Concurrent GC có giành CPU của ứng dụng không? |
| Độ ổn định | OOME, OOMKilled, restart, GC failure | Có đủ tài nguyên để phục vụ suốt thời gian thử? |

**Ví dụ tiêu chí (minh họa, KHÔNG phải chuẩn chung):**

```text
Workload: 800 RPS steady; burst lên 1,600 RPS trong 30s.
Service target: p99 < 150 ms; error rate < 0.5%.
Safety: không OOME/OOMKilled, không Full GC dưới tải mục tiêu.
GC: quan sát và phân loại mọi pacing/degenerated event.
Resource cap: 2 vCPU và 2 GiB container memory.
```

Các số trên **chỉ là hợp đồng thí nghiệm giả định**. Từng dịch vụ cần SLO phù hợp nghiệp vụ. Không dùng các con số minh họa này làm nhận định Shenandoah “bảo đảm p99 150 ms”.

Khi phân tích **p99**, ghi rõ cỡ mẫu và cách tính (cửa sổ từng phút, cả bài test, hay theo loại request). Một p99 tổng thể có thể che giấu đợt burst ngắn nếu gộp với hàng triệu request ở giai đoạn ổn định.

## 4. Đọc đúng GC log: pause, concurrent và thất bại khi thiếu headroom

Unified logging `-Xlog` là cơ chế được hỗ trợ trên các JVM HotSpot hiện hành. Thử:

```bash
java -XX:+UseShenandoahGC \
     -Xms256m -Xmx2g \
     -Xlog:gc*,safepoint:file=shenandoah-gc.log:time,uptime,level,tags \
     MyApp
```

Ý nghĩa:

- `gc*`: các dòng log có tag bắt đầu từ `gc` và các tổ hợp tag GC, tùy level được bật.
- `safepoint`: các điểm an toàn/sự kiện liên quan JVM, giúp tách một số nguồn tạm dừng khác.
- `file=shenandoah-gc.log`: log ra file; vị trí ghi cần có quyền, dung lượng và chính sách lưu trữ.
- `time,uptime,level,tags`: metadata giúp gắn với timeline ứng dụng.

Cú pháp nhiều dòng là kiểu **Bash**. Trên Windows PowerShell/CMD, viết các cờ `java` trên **một dòng**.

**Không hard-code câu chữ log** theo một phiên bản cụ thể: tag, tên phase, số liệu và định dạng Shenandoah có thể thay đổi giữa JDK 17/21/25 và hai mode `satb`/`generational`. Hãy dùng tài liệu của **đúng runtime**, và kiểm tra `java -Xlog:help` khi cần thay level/tag.

### Những nhóm sự kiện cần phân biệt

**Concurrent cycle:** Shenandoah làm công việc GC đồng thời với luồng ứng dụng. Các dòng concurrent không có nghĩa JVM “dừng toàn bộ ứng dụng” trong toàn bộ thời gian ấy.

**Pause / STW:** một pha dừng mutator; phải đo **thời lượng pause thật**. Concurrent cycle kéo dài 200 ms **không đồng nghĩa** một pause 200 ms.

**Allocation pacing:** Shenandoah có thể làm các luồng đang cấp phát **chờ ngắn** để collector có cơ hội theo kịp. Pacing ảnh hưởng **latency request** dù không nhất thiết xuất hiện như một lần STW GC dài.

**Degenerated GC:** khi áp lực cấp phát khiến hoạt động concurrent không thể tiếp tục theo đường bình thường, Shenandoah có thể chuyển một phần công việc sang **stop-the-world** để hoàn tất chu kỳ. Đây là dấu hiệu áp lực và thường cần điều tra.

**Full GC:** biện pháp mạnh hơn khi không thể thu hồi đủ theo các đường bình thường; có thể gây pause rất dài tương đối với mục tiêu low latency. Cần phân loại nguyên nhân, không tuyên bố tất cả Full GC có cùng trigger.

### Đường suy giảm khi bị áp lực cấp phát

```text
Normal concurrent collection
           |
           | Allocation tăng nhanh, headroom hẹp
           v
Allocation pacing (luồng Java bị trì hoãn ở đường cấp phát)
           |
           | GC vẫn không theo kịp
           v
Degenerated GC (STW để tiếp tục/hoàn tất một phần việc)
           |
           | Vẫn không thu hồi đủ hoặc gặp điều kiện khó
           v
Full GC (biện pháp cuối, STW lớn hơn có thể xảy ra)
           |
           v
Có thể vẫn thất bại nếu heap/tài nguyên thực sự không đủ
```

Đây là **mô hình chẩn đoán** của các cơ chế Shenandoah, không phải tuyên bố **mọi** sự cố luôn đi qua đủ bốn bước hoặc có thời lượng cố định. Pacing có thể làm application latency tăng mà một dashboard chỉ đếm `GC pause` không nhìn thấy.

**Đối chiếu log với request traces:** một spike p99 cần được xem cùng timestamp của pacing, degenerated/full, GC CPU, allocation rate và saturation. Nếu p99 tăng nhưng GC log bình thường, tiếp tục điều tra lock, database, I/O, network, scheduler hoặc thread pool.

## 5. Bật mức log phù hợp mà không gây quá tải

Một cấu hình thông dụng để nghiên cứu có log GC chi tiết hơn:

```bash
java -XX:+UseShenandoahGC \
     -Xms256m -Xmx2g \
     -Xlog:gc*=debug,safepoint=info:file=shenandoah-debug.log:time,uptime,level,tags \
     MyApp
```

**Cân nhắc chi phí:** debug/trace log có thể rất lớn và ảnh hưởng CPU/I/O, nhất là khi ứng dụng có nhiều GC events. Không bật tràn lan trên production mà không giới hạn dung lượng/quay vòng log.

Nếu cần file rotation, theo cú pháp HotSpot `-Xlog`:

```bash
java -XX:+UseShenandoahGC -Xmx2g \
     -Xlog:gc*:file=gc-rotating.log:time,uptime,level,tags:filecount=5,filesize=20M \
     MyApp
```

Đây là lệnh minh họa đầy đủ; `MyApp` thay bằng ứng dụng thật. Nó yêu cầu luân phiên các file log theo cấu hình, tránh để một bản ghi kéo dài chiếm đầy ổ đĩa.

### Nên trích xuất gì từ log?

- JVM xác nhận **collector/mode** đang chạy.
- Từng **cycle** cùng thời điểm, loại cycle, duration và phase (theo log runtime cung cấp).
- Tổng thời lượng các **STW pauses**, phân vị hoặc maximum, đặt cạnh request latency.
- Dấu hiệu **pacing**, **allocation failure**, **degenerated GC** và **Full GC**.
- Heap occupancy/capacity, regions, reclaimed bytes nếu có trong log tương ứng.
- Chi phí của GC dưới tải cao, số concurrent cycles liên tiếp.
- Khả năng collector có thời gian nghỉ giữa các chu kỳ hay chạy back-to-back.

**Không lập dashboard chỉ từ một regex cố định** như mọi JDK luôn in đúng chữ `"Degenerated GC"`. Cách viết và tag có thể đổi. Nên kiểm tra log mẫu trên chính bản JDK thực tế rồi mới xây parser phù hợp.

## 6. Live set, allocation rate và headroom: tại sao log GC chưa đủ?

Một GC collector concurrent cần **thời gian + CPU + bộ nhớ** để bắt kịp ứng dụng. Ba đại lượng rất quan trọng:

1. **Live set:** các đối tượng **vẫn reachable**, GC phải giữ lại. Một cache không giới hạn có thể làm live set tăng qua từng giờ.
2. **Allocation rate:** số bytes object mới được cấp phát trên heap mỗi giây, có thể tăng vọt trong burst. Nó **không** bằng `ΔheapUsed/Δt` vì GC có thể thu hồi trong khoảng đo.
3. **Headroom:** dung lượng heap còn hữu ích cho những allocations mới/GC trước khi chạm hard max; không chỉ là `-Xmx - liveSet` vì còn các đối tượng chưa reclaim, overhead và trạng thái collector.

Một **heuristic** suy nghĩ ban đầu:

```text
H_estimate ≳ L_peak + A_peak × T_gc_concurrent + S

H_estimate        = heap nên thử nghiệm
L_peak            = live set ở tải cao
A_peak            = allocation rate khi burst
T_gc_concurrent   = thời gian GC cần để bắt kịp
S                 = safety margin cho đo đạc/overhead/burst
```

**Không phải công thức bảo đảm.** GC liên tục thu hồi dữ liệu và throughput collector phụ thuộc CPU/region/loại object/generation. Phép nhân chỉ giúp nhớ rằng **cấp phát vẫn diễn ra khi collector đang làm việc**; không được nhầm `T_gc_concurrent` với một lần STW pause.

### Ví dụ budget

Giả sử:

```text
L_peak             = 2.50 GiB
A_peak             = 0.75 GiB/s
T_gc_concurrent    = 2.00 s
S                  = 1.00 GiB

H_estimate ≈ 2.50 + 0.75 × 2.00 + 1.00
           ≈ 5.00 GiB
```

Chọn `-Xmx5g` để **thử** là một giả thuyết; không được kết luận 5 GiB chắc chắn đủ. Nếu chạy trong container memory limit 5 GiB, đặt `-Xmx5g` lại **không an toàn** vì tiến trình còn non-heap. Cần đánh giá giới hạn memory ở cấp process/container riêng.

### Allocation pressure cao không có nghĩa memory leak

Một service có thể cấp phát vài GiB đối tượng tạm mỗi giây nhưng live set ổn định sau GC. Đây là **allocation churn** gây áp lực cho concurrent collector, không tự chứng minh leak.

Ngược lại, nếu `heap used` sau những chu kỳ GC phù hợp tăng đều và queue/cache tiếp tục giữ tham chiếu, có thể là **retention leak**, dù allocation rate trung bình không cao. Không khắc phục triệt để leak chỉ bằng tăng `-Xmx`.

## 7. Thiết kế workload đại diện: không dùng mỗi một vòng lặp allocate

Shenandoah nên được kiểm tra dưới workload **gần với traffic của hệ thống sẽ triển khai**, không chỉ chạy một benchmark cấp phát mảng rồi đo pause.

Một workload có ích cần chứa:

- **Request mix:** truy vấn đọc, cập nhật, ghi, batch, cache miss/hit, payload lớn/nhỏ đúng tỉ lệ vận hành.
- **Concurrency:** số request đang xử lý, số luồng/virtual threads, thread pool, connection pool.
- **Allocation shape:** object nhỏ sống ngắn, object lớn, dữ liệu sống lâu, buffers, session, queue và kích thước graph.
- **Backpressure:** có giới hạn queue/bulkhead hay backlog tích tụ?
- **Live set:** cache đã warmup, session/retained data ở mức gần production.
- **Network/DB I/O:** độ trễ phụ thuộc dịch vụ bên ngoài có thể che lấp tác động GC.
- **Pha traffic:** warmup, steady, ramp, burst, cooldown/idle, burst trở lại.
- **Điều kiện OS:** quota CPU, memory limit, heap size, số replica, background load.

Ví dụ một kế hoạch thí nghiệm:

```text
T0-T1  Warmup      : load class, JIT warmup, cache warmup
T1-T2  Steady      : giữ 60% tải đỉnh dự kiến
T2-T3  Ramp        : tăng tải theo từng bậc
T3-T4  Peak/Burst  : giữ tải đỉnh đủ lâu để qua nhiều GC cycles
T4-T5  Recovery    : giảm tải, xem backlog và độ trễ hồi phục
T5-T6  Idle        : xem heap footprint và committed/RSS
T6-T7  Re-burst    : kiểm tra latency khi đột ngột tăng tải sau idle
```

Các tỉ lệ/thời gian trên là **ví dụ thiết kế**, không phải công thức tải chuẩn của mọi ứng dụng. Điều quan trọng là một chế độ test có tải **ổn định đủ lâu** và có **các đỉnh thực tế**, không chỉ chạy 10 giây trước khi JIT/cache warmup xong.

### Đừng để bộ tạo tải trở thành nút cổ chai

Nếu load generator thiếu CPU, client timeout hàng loạt hoặc không giữ được throughput mục tiêu, kết quả không thể dùng kết luận GC server. Đo **RPS thực nhận, client latency, server-side latency, error rate** và số kết nối, đồng bộ timestamp giữa các máy.

Nếu benchmark dùng dữ liệu/trạng thái nhạy cảm, dùng môi trường staging và bộ dữ liệu có quyền truy cập phù hợp; không gửi traffic thử nghiệm vào production nếu chưa có quy trình phê duyệt vận hành.

## 8. Đo bằng JFR và công cụ JVM ngoài GC log

GC log cho biết rất nhiều về hoạt động collector, nhưng không đủ xác định **mã ứng dụng nào cấp phát nhiều** hoặc **request nào chịu latency**.

### 8.1. JFR: đo GC, allocation và trạng thái luồng

Có thể bật Java Flight Recorder ở HotSpot hiện hành:

```bash
java -XX:+UseShenandoahGC -Xmx2g \
     -XX:StartFlightRecording=filename=shenandoah.jfr,settings=profile,dumponexit=true \
     MyApp
```

Hoặc attach vào tiến trình đang chạy:

```bash
jcmd 12345 JFR.start name=shenandoah-study settings=profile duration=60s filename=sh-study.jfr
```

`12345` chỉ là **PID minh họa**, không phải một PID cần sử dụng nguyên xi. Cần quyền attach hợp lệ, runtime hỗ trợ JFR và policy cho phép profiling. Recording có thể chứa class/method/stack traces nhạy cảm, cần bảo vệ và giới hạn lưu trữ.

Các event thường có ích:

- `jdk.GarbageCollection`: các lần collection ở mức mà JFR ghi nhận.
- `jdk.GCHeapSummary`: một số snapshot heap quanh GC.
- `jdk.ObjectAllocationSample`: **các mẫu** nơi cấp phát object; không phải toàn bộ allocation bytes có độ chính xác tuyệt đối.
- `jdk.CPULoad` hoặc các chỉ số CPU khác nếu settings bật.
- Thread/monitor events và sample stack để xem lock contention, thread scheduling.

Có thể xem:

```bash
jfr summary sh-study.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.ObjectAllocationSample sh-study.jfr
```

**Chú ý:** các event có mặt và tần suất phụ thuộc JDK/JFR settings/collector. Không có mẫu allocation **không có nghĩa** application không allocate. Không cộng bytes của một vài `ObjectAllocationSample` rồi gọi đó là “allocation rate chính xác của JVM”; phải dùng phương pháp sampling/weighting hoặc metrics allocated bytes phù hợp.

### 8.2. `jcmd` và JMX

Các lệnh chẩn đoán:

```bash
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
```

Chúng cho biết config/heap/thread state tùy khả năng runtime. `VM.native_memory summary` chỉ có ý nghĩa đầy đủ nếu **Native Memory Tracking** đã được bật:

```bash
java -XX:NativeMemoryTracking=summary -XX:+UseShenandoahGC MyApp
jcmd 12345 VM.native_memory summary
```

Đây là quy trình minh họa hai bước, phải thay PID thật và cân nhắc overhead. **Không tự động bật profiling hoặc NMT trên mọi service production** khi chưa đo chi phí.

### 8.3. `MemoryMXBean` không đo “live set chính xác”

```java
java.lang.management.MemoryUsage usage =
        java.lang.management.ManagementFactory
                .getMemoryMXBean().getHeapMemoryUsage();

long used = usage.getUsed();
long committed = usage.getCommitted();
long max = usage.getMax();
```

Đây là snippet nằm trong một phương thức Java hợp lệ, không phải chương trình độc lập. `used`, `committed` và `max` là các loại số liệu **khác nhau**. `used` có thể bao gồm đối tượng không còn reachable nhưng chưa được reclaim; đó không phải giá trị live set toàn bộ heap chính xác tại mọi thời điểm.

Trong generational Shenandoah, chỉ nhìn một sự kiện liên quan young collection cũng chưa đủ kết luận tất cả đối tượng old generation đã được kiểm tra liveness. Cần dữ liệu qua **nhiều chu kỳ phù hợp** và xem retained objects khi nghi vấn leak.

## 9. Ví dụ Java chạy được: kiểm tra GC MXBean và tài nguyên nhìn từ JVM

Tạo file **`ShenandoahEnvironmentDemo.java`**. Chương trình đọc **GC MXBeans** và thông tin heap/CPU được JVM công bố; nó không hard-code tên GC bean vì các JDK có thể khác nhau. Chỉ dùng Java SE `java.lang.management`, không phụ thuộc thư viện ngoài.

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.List;
import java.util.Locale;

public class ShenandoahEnvironmentDemo {
    public static void main(String[] args) {
        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        boolean shenandoah = collectors.stream()
                .anyMatch(bean -> bean.getName()
                        .toLowerCase(Locale.ROOT)
                        .contains("shenandoah"));

        MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();

        System.out.println("gc.beans.present="
                + !collectors.isEmpty());
        System.out.println("shenandoah.mxbean=" + shenandoah);
        System.out.println("cpu.count.positive="
                + (Runtime.getRuntime().availableProcessors() > 0));
        System.out.println("heap.max.positive="
                + (heap.getMax() > 0));
        System.out.println("heap.usedLEcommitted="
                + (heap.getUsed() <= heap.getCommitted()));
        System.out.println("heap.committedLEmax="
                + (heap.getCommitted() <= heap.getMax()));

        // Tên GC beans và số CPU cụ thể phụ thuộc runtime.
        for (GarbageCollectorMXBean bean : collectors) {
            System.out.println("collector.name=" + bean.getName());
        }
    }
}
```

Biên dịch và chạy trên **JDK 17+ có Shenandoah**, ví dụ ở mức heap nhỏ:

```bash
javac -encoding UTF-8 ShenandoahEnvironmentDemo.java
java -XX:+UseShenandoahGC -Xms64m -Xmx256m ShenandoahEnvironmentDemo
```

**Các dòng stdout có giá trị xác định trong HotSpot/OpenJDK tương thích:**

```text
gc.beans.present=true
shenandoah.mxbean=true
cpu.count.positive=true
heap.max.positive=true
heap.usedLEcommitted=true
heap.committedLEmax=true
```

Chương trình còn in các dòng `collector.name=...`; **tên bean phụ thuộc JVM/mode** nên không đưa ra expected output cố định cho phần đó.

**Đã kiểm chứng trên Zulu OpenJDK 24.0.2** có Shenandoah: các biểu thức boolean trên đều đúng; collector beans được đặt tên theo phiên bản runtime. Mỗi bản JDK mới có thể thay đổi cấu trúc metrics, vì vậy code không dựa vào tên đầy đủ cụ thể.

### Ý nghĩa

- `shenandoah.mxbean=true` là **tín hiệu** rằng runtime phơi bày collector có tên Shenandoah; đồng thời nên kiểm tra startup GC log/flags để xác nhận mode đang chạy.
- `availableProcessors()>0` chỉ cho biết JVM nhận diện một số CPU dương; **không** nói container có CPU không bị throttling.
- `heap.getMax()>0` phản ánh cấu hình heap có max xác định trong ví dụ.
- `used <= committed <= max` là những bất biến quản lý bộ nhớ được kiểm tra trong snapshot; không chứng minh ứng dụng có đủ headroom ở burst.
- Một màn hình chỉ hiển thị MXBean **không thay thế** đo request latency hoặc log cảnh báo allocation failure.

## 10. Ví dụ Java chạy được: tạo một workload có retained data và allocation churn

Tạo file **`ShenandoahLoadDemo.java`**. Mẫu này cố tình đơn giản để **tạo GC log có thể quan sát** và minh họa sự khác nhau giữa **đối tượng giữ lâu** và **object tạm**. Đây là **synthetic workload**, không phải công cụ thay thế load test dịch vụ thực.

### 10.1. Mã nguồn

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class ShenandoahLoadDemo {
    private static final int MIB = 1024 * 1024;
    private static volatile byte[] escape;

    private static void phase(
            String label, int count, int bytesPerObject) {
        long start = System.nanoTime();
        long totalBytes = 0;

        for (int i = 0; i < count; i++) {
            byte[] temporary = new byte[bytesPerObject];
            temporary[0] = (byte) i;
            temporary[temporary.length - 1] = (byte) (i >>> 8);

            // Publish đối tượng để JIT không đơn giản coi
            // toàn bộ cấp phát là kết quả không được quan sát.
            escape = temporary;
            totalBytes += temporary.length;
        }

        long elapsedNanos = System.nanoTime() - start;
        System.out.println(label + ".requestedMiB="
                + totalBytes / MIB);
        System.out.println(label + ".durationMs="
                + TimeUnit.NANOSECONDS.toMillis(elapsedNanos));
    }

    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();

        // 16 mảng giữ tham chiếu, payload logic 16 MiB.
        for (int i = 0; i < 16; i++) {
            retained.add(new byte[MIB]);
        }
        System.out.println("retained.payloadMiB=" + retained.size());

        // 4,096 × 16 KiB = 64 MiB cấp phát được yêu cầu.
        phase("steady", 4096, 16 * 1024);

        // 16,384 × 16 KiB = 256 MiB cấp phát được yêu cầu.
        phase("burst", 16384, 16 * 1024);

        retained.clear();
        System.out.println("retained.afterClear=" + retained.size());
    }
}
```

### 10.2. Biên dịch/chạy

```bash
javac -encoding UTF-8 ShenandoahLoadDemo.java

java -XX:+UseShenandoahGC \
     -Xms64m -Xmx256m \
     -Xlog:gc*,safepoint:file=sh-load-256m.log:time,uptime,level,tags \
     ShenandoahLoadDemo
```

**Các dòng stdout cố định khi chạy thành công:**

```text
retained.payloadMiB=16
steady.requestedMiB=64
burst.requestedMiB=256
retained.afterClear=0
```

Giữa những dòng cố định, chương trình còn in `steady.durationMs=<số thực đo>` và `burst.durationMs=<số thực đo>`. **Không có giá trị mili-giây đúng cho mọi máy**; nó phụ thuộc JIT, CPU, heap, OS và cả GC. Không lấy các giá trị này làm SLO response time của một dịch vụ.

Các mệnh đề số bytes từ vòng lặp và hành vi cấp phát đã được kiểm tra trong môi trường **OpenJDK 24.0.2 có Shenandoah**. Vì bài dùng một luồng và các mảng đơn giản, nó **không đại diện** request mix, số lượng thread, network I/O hoặc live set của ứng dụng sản xuất.

### 10.3. Đọc log của thí nghiệm

Mở file `sh-load-256m.log` và quan sát:

1. Shenandoah có khởi chạy đúng mode mà JVM công bố không?
2. Có bao nhiêu concurrent GC cycles? Chúng kéo dài bao lâu?
3. Có pacing/degenerated/full GC hay không?
4. Heap occupancy/committed và free regions thay đổi ra sao?
5. Nếu thay `-Xmx256m` bằng `-Xmx512m`, log và tổng thời gian có thay đổi theo cùng hướng không?

**Không yêu cầu chương trình chắc chắn in một số GC cycles cố định.** GC tự quyết định thời điểm collection, phụ thuộc JIT, nền tảng và memory pressure. Nếu số lượng dữ liệu trong demo quá nhỏ để thể hiện khác biệt, tăng workload **trên một môi trường thử nghiệm được phép**, không cố ép ứng dụng production OOME.

**`requestedMiB` là payload bytes do vòng lặp yêu cầu**, không phải allocation rate MiB/s được profiler đo. Muốn biết rate thực, cần đồng hồ đo khoảng thời gian và số allocation thực tế (cùng phương pháp qua các lần chạy); `durationMs` là thước đo **thô của riêng vòng lặp**, không phải độ trễ end-to-end.

## 11. So sánh có kiểm soát: A/B Shenandoah theo heap và mode

Một phép thử đáng tin cần giữ nguyên các biến còn lại trong lúc thay **một** yếu tố.

### Bước A — baseline

Với cùng JDK/build, cùng class, cùng CPU/OS:

```bash
java -XX:+UseShenandoahGC \
     -Xms64m -Xmx256m \
     -Xlog:gc*:file=sh-256m.log:time,uptime,level,tags \
     ShenandoahLoadDemo
```

### Bước B — chỉ tăng hard max heap

```bash
java -XX:+UseShenandoahGC \
     -Xms64m -Xmx512m \
     -Xlog:gc*:file=sh-512m.log:time,uptime,level,tags \
     ShenandoahLoadDemo
```

Chỉ thay `-Xmx`, còn code và `-Xms` giữ nguyên. So sánh GC cycles, degenerated/full, memory occupancy, thời gian chạy và (với workload thật) p99 request. Heap lớn hơn có thể giúp headroom nhưng cũng có chi phí bộ nhớ và không tự giải quyết leak.

### Bước C — so mode trên JDK 25+ khi cả hai được hỗ trợ

Ví dụ muốn kiểm tra **generational** rõ ràng:

```bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -Xms64m -Xmx512m \
     -Xlog:gc*:file=sh-gen-512m.log:time,uptime,level,tags \
     ShenandoahLoadDemo
```

Khi muốn so sánh với mode `satb`, phải chạy một job **khác** được cấu hình rõ `-XX:ShenandoahGCMode=satb` nếu chính runtime hỗ trợ. Kết quả so sánh giữa các mode **không đồng nghĩa** so sánh hai phiên bản Java khác nhau hoặc hai bộ tải khác nhau.

**Không dùng cờ `generational` trên JDK 17/21 chỉ vì tìm thấy trong hướng dẫn JDK 25.** Đừng sao chép cờ experimental JDK 24 vào production JDK 25 mà không kiểm tra tài liệu chính thức.

### Ma trận thí nghiệm đề nghị

| Lần chạy | JDK/build | Mode | `-Xmx` | CPU quota | Load |
| --- | --- | --- | --- | --- | --- |
| A | Cùng một JDK | mode được xác nhận | 256 MiB | Cố định | Cùng workload |
| B | Như A | như A | 512 MiB | Cố định | Cùng workload |
| C | JDK 25+ hỗ trợ | generational | 512 MiB | Cố định | Cùng workload |
| D | JDK 25+ hỗ trợ | satb | 512 MiB | Cố định | Cùng workload |

Hàng A/B/C/D là **kế hoạch kiểm thử**, không phải bằng chứng đo được. Với một hệ thống thực, chạy nhiều lần, warmup đủ, lấy median và tail latency phù hợp để giảm nhiễu.

**Điều kiện quan trọng:** không có căn cứ so sánh nếu một lần load là 1.000 RPS, lần kia chỉ thực nhận 700 RPS do client hoặc server quá tải. Phải ghi **throughput thực đạt** trong mỗi lần.

## 12. Giới hạn RAM: `-Xmx` không phải mức tối đa của toàn tiến trình

Trong container, memory limit không chỉ chứa Java heap:

```text
Container memory budget
+-----------------------------------------------------+
| Java heap (-Xmx chỉ là trần của phần này)            |
| Metaspace + class metadata                          |
| JIT/code cache                                      |
| Thread stacks                                       |
| Direct ByteBuffers, JNI/native libraries            |
| GC/JVM runtime metadata                             |
| Các khoản OS/cgroup khác tùy cách kế toán            |
+-----------------------------------------------------+
```

Đặt container memory limit **2 GiB** và `-Xmx2g` thường là lựa chọn nguy hiểm vì không còn dự phòng cho non-heap/native. Container có thể bị **OOMKilled** dù Java heap chưa hoàn toàn đầy.

### Hai dạng thiếu bộ nhớ khác nhau

| Tình huống | Triệu chứng | Cần kiểm tra |
| --- | --- | --- |
| **Java heap hết chỗ** | Allocation failure, pacing, degenerated/full GC; có thể `OutOfMemoryError: Java heap space` | Live set, allocation rate, `-Xmx`, GC log |
| **Container/process hết RAM** | OS/cgroup OOM kill, exit code không phải Java exception thông thường | RSS/cgroup memory, direct/native allocations, limit |
| **Host bị swapping/page faults** | Latency tăng mạnh, collector chậm, CPU/IO bất thường | Swap, major page faults, RSS, memory pressure |
| **Native/off-heap leak** | RSS tăng dù heap used tương đối ổn định | NMT, direct buffers, native libraries, threads |

Vì vậy **dùng thêm heap** chỉ khi process/container có đủ RAM. Tăng `-Xmx` trong một container đã sát limit có thể khiến toàn tiến trình bị kill sớm hơn.

### Sàn heap và footprint

`-Xms` cao có thể làm footprint ban đầu lớn hơn và hạn chế khả năng thu hồi committed pages tùy collector/cấu hình. `-Xms` thấp giúp linh hoạt bộ nhớ nhưng có thể tăng chi phí commit trong lúc tải hồi phục. Mọi lựa chọn phải cân bằng footprint, latency và SLO; không giả định mọi bản Shenandoah đều áp dụng một chính sách uncommit giống nhau.

## 13. Giới hạn CPU và CPU throttling: kẻ thù của concurrent GC

Shenandoah làm phần lớn GC khi ứng dụng vẫn chạy, nên **concurrent GC threads phải chia sẻ CPU** với request handlers, JIT, OS và những tiến trình khác.

Nếu container bị giới hạn CPU:

- Application threads vẫn cấp phát khi phục vụ request.
- GC cần CPU để truy vết và reclaim object.
- Khi CPU quota cạn hoặc cgroup throttle mạnh, GC có thể hoàn tất chậm hơn.
- Allocation tiếp tục làm headroom giảm.
- Shenandoah có thể tăng pacing hoặc chuyển sang các chế độ xử lý đắt hơn; request p99 bị ảnh hưởng.

**Không đọc “CPU usage 100%” bằng một cách duy nhất.** CPU của process, CPU theo core, CPU quota và số lượng cores JVM nhận biết có định nghĩa khác nhau. Cần đọc **cgroup throttled time/periods**, process CPU, thread run queue, số CPU của JVM và CPU của load generator.

### `-XX:ActiveProcessorCount` không phải CPU limit của OS

Cờ HotSpot:

```bash
java -XX:+UseShenandoahGC \
     -XX:ActiveProcessorCount=2 \
     -Xms256m -Xmx2g MyApp
```

cho JVM **nhìn thấy một số CPU do bạn cấu hình** khi tính các heuristic và pool sizes. Nó **không tạo một CPU quota/throttle thực ở mức cgroup/OS**. Muốn thử nghiệm ảnh hưởng 2 vCPU thật, cần cấu hình CPU limit ở **container/host** và xác minh counters của hệ điều hành.

### Có nên tăng `ConcGCThreads`?

`-XX:ConcGCThreads` là tùy chọn HotSpot cho số worker đồng thời của GC; nhưng tăng số GC threads:

- Có thể giúp collector hoàn thành nhanh hơn khi CPU **thực sự còn dư**.
- Có thể tranh CPU với ứng dụng, làm throughput hoặc p99 xấu đi.
- Không chữa được việc **container chỉ cấp ít CPU thực** hoặc liên tục bị throttling.

**Thứ tự hợp lý:** để heuristic mặc định, đo trước; sau đó nếu số liệu cho thấy GC không theo kịp và có CPU dư, thử đổi **từng thông số**. Không tăng/giảm GC threads theo một công thức không xét workload.

## 14. Pacing, Degenerated GC, Full GC: xác định nguyên nhân rồi mới sửa

Bảng chẩn đoán thực hành:

| Dấu hiệu thực đo | Khả năng cần điều tra | Bước tiếp theo |
| --- | --- | --- |
| Nhiều concurrent cycles nối tiếp | Allocation pressure cao hoặc free heap không đủ cho collector nghỉ | Xem allocation rate/live set, heap headroom |
| Pacing tăng khi traffic tăng | Mutator cấp phát nhanh hơn khả năng GC theo kịp | So request latency, CPU và allocation rate |
| Degenerated GC xuất hiện | Concurrent cycle không đạt tiến độ dưới áp lực cấp phát | Kiểm tra `-Xmx`, CPU, live set và burst |
| Full GC xuất hiện | Không reclaim đủ qua đường bình thường hoặc sự kiện đặc biệt | Xác định nguyên nhân trong log; ưu tiên điều tra |
| Pause thấp nhưng p99 cao | Có thể pacing, CPU contention, lock/I/O hoặc scheduler | Kết hợp request traces, JFR và logs |
| Heap used ổn định nhưng GC chạy dày | Đối tượng sống ít nhưng object churn cao | Giảm allocation per request, batching |
| Heap after-cycle tăng đều | Retained data/cache/queue có thể tăng | Kiểm tra ownership/eviction, heap dump theo kế hoạch |
| RSS sát limit trong khi heap used thấp | Native/direct/non-heap hoặc cgroup pressure | JCMD/NMT/OS metrics và giới hạn |
| CPU quota thường xuyên throttled | Mutator và GC tranh thời gian xử lý | Tăng CPU hoặc giảm contention/workload |

### Thứ tự quyết định đề xuất

1. Xác minh **collector/mode/version** đang thực sự chạy.
2. Đồng bộ timeline **p99 spikes** với `gc`/`safepoint` logs và các metric khác.
3. Xem **live set/retained data** có chiếm gần phần lớn hard heap không.
4. Xem **allocation rate burst** có cao gấp nhiều lần steady hay không.
5. Kiểm tra **CPU quota/throttling**: GC chạy đồng thời nhưng CPU thực tế có đủ?
6. Kiểm tra **heap headroom** trước khi thay heuristic/pacing flags.
7. Nếu thử tăng heap/CPU hoặc giảm allocation, **giữ nguyên các điều kiện khác**.
8. Chạy lặp lại trên workload cùng hình dạng, rồi quyết định theo p99, errors, RSS và GC events.

**Không khuyến nghị “tăng pacing delay” theo phản xạ.** Pacing có thể tránh một số GC failure nhưng vẫn làm request chờ; nếu chỉ xem GC pause metric, bạn có thể tự che tác động lên latency của người dùng.

## 15. Đừng biến benchmark thành phép thử thiếu an toàn

Khi chạy thử sức chịu đựng của heap/GC:

- Không gây OOME chủ động trên một service production có khách hàng.
- Chạy trên staging hoặc môi trường isolate có memory/CPU limit và khả năng rollback.
- Tăng tải theo các bậc, đặt stop conditions cho error rate, p99, memory pressure.
- Đừng tạo hàng nghìn thread không giới hạn chỉ để làm “stress test”.
- Đừng tắt các cơ chế an toàn như pacing/degenerated GC nếu chưa hiểu hậu quả và chưa có quy trình phê duyệt.
- Nếu cần heap dump, hiểu rằng nó có thể chứa **dữ liệu nhạy cảm** và chiếm dung lượng lớn; chỉ bật theo chính sách.
- Khi chạy JFR/NMT/GC debug, đo overhead của công cụ quan sát.

### Những biến phải cố định khi so sánh

```text
JDK vendor/build
OS/kernel/container image
Collector & mode
Heap parameters ngoài biến đang thử
CPU quota và RAM limit
Warmup duration
Traffic shape / request mix
Input data distribution
Thread pools / queue limits
External dependencies
JFR/GC log level (cùng overhead)
Số lần chạy và cách tổng hợp metric
```

Nếu cần so nhiều JDK hoặc so Shenandoah với collector khác, hãy tạo **một thí nghiệm khác có chủ đích**; không kết luận từ hai lần chạy mà JDK, heap và tải cùng thay đổi.

## 16. Phân tích ví dụ: cùng GC pause thấp, kết quả khác vì CPU

Giả định một service có hai lần chạy:

| Thuộc tính | Lần A | Lần B |
| --- | --- | --- |
| Cùng JDK/Shenandoah mode | Có | Có |
| Heap hard max | 4 GiB | 4 GiB |
| Live set | ~2 GiB | ~2 GiB |
| Allocation rate khi burst | 800 MiB/s | 800 MiB/s |
| CPU quota | 4 vCPU | 1 vCPU |
| GC concurrent cycles | Hoàn tất đều | Có thể kéo dài hơn |
| Pacing/degenerated | Ít/không | Có thể xuất hiện |
| p99 request | Có thể đạt SLO | Có thể xấu hơn |

**Đây là tình huống giả định để suy luận**, không phải số liệu Shenandoah được benchmark ở một hệ thống cụ thể.

Khi giảm CPU quota, cả collector và ứng dụng đều có ít CPU hơn; không thể quy tất cả p99 xấu chỉ do GC. Cần so:

- Process CPU và quota usage.
- cgroup throttled periods/duration.
- GC cycle duration và các dấu hiệu allocation pacing.
- Request-side CPU time/blocked time/DB latency.
- Throughput thực tế.

Một phép thử có **same GC pause p99** nhưng **request p99 khác** là lời nhắc rằng điểm số GC riêng lẻ không đại diện cho toàn hệ thống.

## 17. Runbook triển khai: từ chuẩn bị đến quyết định PASS/FAIL

### Giai đoạn A — trước thí nghiệm

1. Ghi JDK version, vendor, Shenandoah mode và flags thực tế.
2. Xác nhận collector hoạt động bằng startup log và `ShenandoahEnvironmentDemo`.
3. Chốt SLO request và stop conditions được tổ chức cho phép.
4. Chọn dữ liệu/tải đại diện và kế hoạch warmup → steady → burst → recovery.
5. Bật GC log/JFR/metrics cấp OS đủ nhưng tránh overhead quá mức.
6. Kiểm tra `-Xmx` **cộng non-heap** không sát memory limit container.

### Giai đoạn B — thực thi

1. Warmup đủ để cache/JIT ổn định.
2. Chạy steady state và ghi throughput, error, p99.
3. Tăng tải theo bậc; đánh dấu thời điểm chuyển pha.
4. Giữ burst đủ lâu để quan sát GC qua nhiều cycles nếu workload phát sinh.
5. Giảm tải và xem backlog/p99 có phục hồi không.
6. Chạy lại nhiều lần theo cùng quy trình để giảm nhiễu.
7. Nếu xuất hiện OOMKilled/OOME hoặc áp lực tài nguyên ngoài giới hạn an toàn, **dừng thí nghiệm** theo kế hoạch.

### Giai đoạn C — phân tích

1. Đồng bộ timestamps của request metrics, GC logs, JFR và OS.
2. Trích các lần STW pause, pacing/degenerated/full, heap occupancy.
3. Đối chiếu allocation rate/burst và retained live data.
4. Kiểm tra CPU quota, throttling, RSS/cgroup limit.
5. Phân loại nguồn p99: GC, allocation, CPU, lock, I/O, network, DB hoặc kết hợp.
6. Lập bảng A/B, ghi cả **sai số và điều kiện môi trường**.

### Giai đoạn D — quyết định

**PASS** khi toàn bộ tiêu chí đã định nghĩa từ trước đạt: SLO, error, throughput, memory/process safety, tính ổn định qua steady và burst; collector thực sự chạy với mode đã nêu.

**FAIL** khi có sự cố đủ mức theo điều kiện dừng hoặc kết quả dưới mức chấp nhận: p99 quá SLO, error quá ngưỡng, OOME/OOMKilled, quá quota, hoặc dấu hiệu GC failure không được phép.

**INCONCLUSIVE** khi thiếu bằng chứng: tải thực nhận không đạt, generator nghẽn, log/JFR không đủ, thời gian test quá ngắn, JDK thiếu Shenandoah hoặc hai lần chạy không thể so sánh.

**Không biến INCONCLUSIVE thành PASS.** Dùng đúng kết quả để quyết định có cần sửa workload, monitoring hoặc JDK build hay không.

## 18. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ thấy `Using Shenandoah` và tuyên bố p99 tốt | Chưa đo workload và end-to-end latency | Đo request p99, error, throughput và GC logs |
| Dùng tài liệu không cập nhật cho mode generational | Cờ/mode thay đổi theo JDK | Ghi JDK, dùng JEP 521 và tài liệu đúng build |
| Cho rằng mọi JDK 25 đều có Shenandoah | Build/vendor có thể không phân phối GC này | Thử JVM startup và kiểm tra flags |
| Chạy `ShenandoahGCMode=generational` trên JDK cũ | Runtime có thể không hỗ trợ | Chỉ dùng JDK 25+ hỗ trợ cho cấu hình hiện hành |
| Chỉ xem tổng thời gian concurrent cycle như STW pause | Hai đại lượng khác nhau | Dùng phase/pause tags và timeline |
| Không đo pacing | Pacing làm luồng Java chờ nhưng không nhất thiết là STW | Xem log collector và request latency |
| Có degenerated/full nhưng bỏ qua vì average thấp | Tail latency có thể bị ảnh hưởng lớn | Phân tích nguyên nhân, không giấu spike |
| Dùng `ΔheapUsed/Δt` làm allocation rate | GC thu hồi đồng thời | Dùng metrics allocations/profiling phù hợp |
| Nhìn young GC sau collection rồi coi là live set toàn heap | Old objects có thể vẫn chưa được thu hồi | Xem chu kỳ phù hợp và retention |
| Chọn `-Xmx` bằng đúng live set | Thiếu headroom cho allocation/GC | Tính live set + burst + safety theo dữ liệu |
| Đặt `-Xmx` bằng container memory limit | Bỏ qua non-heap/native | Dành RAM cho cả tiến trình |
| Dùng `ActiveProcessorCount=2` coi là quota 2 vCPU thật | Cờ JVM không áp throttle OS | Thiết lập CPU quota thực và đọc cgroup |
| Heap tăng gần max, tăng GC threads ngay | Có thể tranh CPU với mutator | Đo CPU/GC progress trước |
| Thử chỉ ở idle hoặc steady | Không thấy burst, queue/backlog, recovery | Test cả warmup, ramp, burst, cooldown |
| Chạy benchmark synthetic rồi kết luận cho production | Object shape, I/O và concurrency khác | Test service với traffic đại diện |
| Thay heap, JDK, GC mode và payload cùng lúc | Không biết biến nào gây khác biệt | Thiết kế A/B một biến mỗi lần |
| Mức tải thực nhận A/B khác nhau | So sánh p99 thiếu công bằng | Ghi throughput thực và kiểm soát generator |
| Cộng các sample JFR thành tổng bytes chính xác | Sampling không phải total allocation counter | Dùng profiler/weighting hoặc counter phù hợp |
| Bật GC debug/trace không kiểm soát | Log overhead làm lệch workload | Chỉ bật tag cần thiết, dùng rotation |
| Không đồng bộ timestamp giữa client/server | Không ghép được p99 và GC event | Đồng bộ clock, dùng uptime/timestamp markers |
| Kết luận p99 cao luôn do GC | Còn lock/I/O/DB/scheduler | Đối chiếu tracing/JFR/OS metrics |
| Chạy stress OOM trên production | Có thể gây sự cố dịch vụ | Staging, giới hạn tải và stop conditions |

## 19. Bài tập tự kiểm tra có đáp án

**Bài 1.** JVM chạy `-XX:+UseShenandoahGC` và in “Using Shenandoah”. Có đủ kết luận hệ thống đạt p99 dưới 100 ms không?

**Đáp án:** Không. Đó chỉ là bằng chứng collector được chọn; phải đo end-to-end request latency dưới workload đại diện.

**Bài 2.** Một concurrent GC cycle kéo dài 220 ms, nhưng tổng thời gian pause trong chu kỳ rất nhỏ. Có được ghi “GC đã dừng app 220 ms” không?

**Đáp án:** Không. Concurrent cycle chạy đồng thời với mutator; phải tách STW pauses.

**Bài 3.** Vì sao allocation pacing nguy hiểm nếu chỉ theo dõi dashboard STW?

**Đáp án:** Pacing có thể làm luồng Java chờ cấp phát và tăng request latency, dù không xuất hiện là một STW pause dài.

**Bài 4.** Nếu log có Degenerated GC thường xuyên khi traffic burst, nên xem gì trước?

**Đáp án:** Live set, allocation burst, hard heap headroom, CPU quota/throttling và khả năng GC bắt kịp; sau đó mới cân nhắc tuning collector.

**Bài 5.** `-Xmx4g` trong container memory limit 4 GiB có an toàn tuyệt đối không?

**Đáp án:** Không. Tiến trình còn nhiều non-heap/native memory; container có thể OOMKilled.

**Bài 6.** JDK 25 đã hỗ trợ Generational Shenandoah nhưng runtime in `ShenandoahGCMode=satb`. Có mâu thuẫn không?

**Đáp án:** Không. Hỗ trợ một mode mới không có nghĩa luôn dùng nó mặc định. Muốn thử generational, chọn đúng flag trên build hỗ trợ và xác minh effective mode.

**Bài 7.** Một lần benchmark với `-Xmx512m` tốt hơn lần `-Xmx256m`. Nhưng lần đầu chạy trên 8 CPU, lần sau chỉ 1 CPU. Có thể kết luận heap lớn là nguyên nhân duy nhất?

**Đáp án:** Không. CPU khác nhau là confounder. Phải cố định điều kiện CPU rồi đo lại.

**Bài 8.** `MemoryMXBean.getHeapMemoryUsage().getUsed()` giảm mạnh sau GC. Có thể suy ra allocation rate bằng 0?

**Đáp án:** Không. App có thể đã cấp phát rất nhiều rồi GC thu hồi; `heap used` là snapshot, không phải tổng allocation.

**Bài 9.** Vì sao phải warmup trước khi đo GC/latency?

**Đáp án:** Class loading, JIT compilation, cache/connection warmup và hệ thống ổn định có thể làm giai đoạn đầu khác với vận hành bền vững.

**Bài 10.** Test 10 giây hoàn toàn không có Full GC. Có chắc workload chịu được đợt burst 30 phút?

**Đáp án:** Không. Cần workload đủ dài, có load và live set đại diện; không có sự kiện trong test ngắn chưa chứng minh an toàn dài hạn.

**Bài 11.** `ActiveProcessorCount=2` có giới hạn thực process chỉ được dùng 2 vCPU không?

**Đáp án:** Không. Nó thay số CPU mà JVM **nhìn thấy** cho các heuristic; CPU quota thực phải do OS/container thực thi.

**Bài 12.** Một máy có pause rất thấp nhưng p99 tăng khi CPU throttling cao. Có thể GC vẫn liên quan không?

**Đáp án:** Có. Concurrent GC thiếu CPU có thể bị chậm, tác động pacing, nhưng vẫn phải xem request CPU, lock và I/O để kết luận.

**Bài 13.** Trong `ShenandoahLoadDemo`, `burst.requestedMiB=256` có phải throughput hay allocation rate chính xác không?

**Đáp án:** Không. Đó là **tổng payload cấp phát logic** theo vòng lặp, không tính thời gian hay overhead/JIT. Muốn allocation rate cần metrics/profile hợp lệ.

**Bài 14.** Vì sao `jfr ObjectAllocationSample` không thể tự cộng thành tổng bytes cấp phát chính xác?

**Đáp án:** Nó là sample và chỉ ghi một phần sự kiện. Cần phương pháp trọng số/counter của công cụ đo.

**Bài 15.** `heap used` còn thấp nhưng RSS sát container limit. Vì sao?

**Đáp án:** Process còn metaspace, stacks, direct/native allocations và OS charges. Cần đo memory cấp process/cgroup.

**Bài 16.** Một phép thử có p99 tốt nhưng error rate 20% vì hệ thống từ chối request. Đây có phải PASS?

**Đáp án:** Không. Phải đạt cả latency, throughput thực và error SLO; drop request có thể làm latency nhìn tốt giả tạo.

**Bài 17.** Nếu hai lần test dùng JDK 21 và JDK 25 khác GC mode, có nên quy mọi chênh lệch do “heap size” không?

**Đáp án:** Không. JDK, mode và các tối ưu JVM khác đều là biến có thể ảnh hưởng. Cần mô hình test được kiểm soát.

**Bài 18.** Thấy vài dòng “Full GC” nên luôn tăng `-Xmx`?

**Đáp án:** Không ngay lập tức. Xác định trigger và điều kiện memory/CPU trước. Live set không giới hạn hoặc container RAM chật có thể khiến tăng heap phản tác dụng.

**Bài 19.** Phải làm gì nếu JDK build không chứa Shenandoah?

**Đáp án:** Ghi rõ **không thể thực hiện thí nghiệm collector này**; chọn runtime được hỗ trợ có Shenandoah hoặc thay đổi mục tiêu so sánh chính thức, không tự báo PASS.

**Bài 20.** Khi nào một phép so sánh nên được đánh dấu INCONCLUSIVE?

**Đáp án:** Khi thiếu dữ liệu, log không đầy đủ, traffic không tương đương, generator trở thành bottleneck hoặc runtime không có collector/mode được yêu cầu.

### Checklist trước khi chốt kết quả

- [ ] Tôi xác nhận **đúng JDK vendor/build**, `UseShenandoahGC` và mode.
- [ ] Tôi không giả định JDK 25 luôn mặc định generational Shenandoah.
- [ ] Tôi đặt **SLO/throughput/error criteria** trước khi đo.
- [ ] Tôi thu GC logs với timestamps và xác định concurrent vs STW.
- [ ] Tôi phân biệt pacing, degenerated GC, Full GC và OOME.
- [ ] Tôi biết GC pause tốt **không đủ** nếu request p99 bị pacing hoặc CPU contention.
- [ ] Tôi có số liệu live set/retention và allocation rate burst.
- [ ] Tôi không lấy heap used delta làm allocation rate.
- [ ] Tôi tính cả RSS/non-heap và container memory limit.
- [ ] Tôi xem CPU quota/throttling, không chỉ `availableProcessors()`.
- [ ] Tôi có các pha warmup, steady, ramp, burst, recovery.
- [ ] Tôi giữ các điều kiện A/B giống nhau và thay từng biến.
- [ ] Tôi biết JFR allocation sampling có giới hạn.
- [ ] Tôi không ép OOM hoặc bật log quá mức trên production.
- [ ] Tôi phân biệt kết luận PASS, FAIL và INCONCLUSIVE.
- [ ] Tôi có thể biên dịch và chạy hai ví dụ Java 17+ rồi giải thích phần output nào là cố định.

## 20. Tài liệu chính thức còn áp dụng

1. [OpenJDK JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): hoàn thiện Generational Shenandoah trong **JDK 25**, giải thích động lực và khác biệt mode.
2. [OpenJDK JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): bối cảnh lịch sử của giai đoạn thử nghiệm; **không dùng các yêu cầu bật experimental cũ làm hướng dẫn cấu hình sản xuất JDK 25+**.
3. [OpenJDK — Shenandoah Wiki](https://wiki.openjdk.org/display/shenandoah/Main): thuật ngữ, đo GC, pacing, Degenerated/Full GC, quyết định headroom và áp lực cấp phát; kiểm tra sự tương thích của các flag theo phiên bản.
4. [OpenJDK — Java launcher documentation](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md): `UseShenandoahGC`, `ShenandoahGCMode` và `ShenandoahGCHeuristics` của JDK mainline hiện hành.
5. [Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): cú pháp `-Xmx`, `-Xms`, `-Xlog`, `-XX:ActiveProcessorCount`, JFR startup và các tùy chọn VM chung.
6. [Java SE 25 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): thông tin MXBean của garbage collectors.
7. [Java SE 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html) và [MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html): snapshot heap `used`, `committed`, `max`.
8. [Java SE 25 — jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) và [jfr](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): chẩn đoán JVM, recording JFR và xem events.
9. [Red Hat Build of OpenJDK 25 — Generational Shenandoah](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): ví dụ runtime có hỗ trợ mode generational trong JDK 25.

**Tổng kết:** Muốn chứng minh Shenandoah đạt mục tiêu **GC độ trễ thấp**, phải đo **p99/p99.9 request dưới tải đại diện**, đặt cạnh **GC log/JFR** (concurrent pauses, pacing, Degenerated/Full GC) và **giới hạn tài nguyên thật** (heap headroom, allocation rate, CPU throttling, RSS/cgroup). Cùng một lần chạy nên có workload warmup–steady–burst–recovery, thống nhất JDK/collector mode và điều kiện thí nghiệm. Shenandoah được chọn bằng `-XX:+UseShenandoahGC` khi build hỗ trợ; trên JDK 25+ có thể thử `ShenandoahGCMode=generational` theo JEP 521. **Chỉ kết luận PASS khi ứng dụng đạt SLO, không gặp failure và dữ liệu đo đầy đủ**, không chỉ vì log ghi “Using Shenandoah”.