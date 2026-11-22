# 17.1. Phân biệt CPU cao của tiến trình, một thread, GC hoặc compiler

## Mục tiêu

Khi một ứng dụng Java dùng nhiều CPU, cần trả lời **CPU tăng ở cấp nào**, **luồng nào thật sự tiêu thụ**, và **công việc thuộc application code, garbage collector (GC) hay JIT compiler**. Một giá trị CPU process cao không đủ để kết luận có vòng lặp vô hạn; một thread `RUNNABLE` cũng không đủ chứng minh nó tiêu thụ CPU. Phân tích đúng cần nối **số đo OS theo khoảng thời gian** với **thread dump/JFR/GC log/biên dịch JIT**, đồng thời xét giới hạn CPU của host hoặc container.

Bài dùng ví dụ **HotSpot JDK 17+ trên Linux**; các công cụ OS khác (Windows/macOS), collector khác hoặc JDK mới hơn có thể đổi tên luồng, bộ đếm và cách hiển thị. Các con số ví dụ trong bài được gắn nhãn minh họa, không phải kết quả cố định của máy thật.

Sau bài này, bạn sẽ biết:

1. Phân biệt **CPU process**, **CPU từng native thread**, **CPU do GC workers**, và **CPU do C1/C2/JIT compiler threads**.
2. Tính CPU usage từ **chênh lệch CPU time và wall time**, hiểu vì sao một process có thể hiển thị hơn 100%.
3. Dùng `top -H`/`pidstat -t`/`ps -L` rồi ghép **OS TID** với `nid=0x...` trong HotSpot thread dump.
4. Phân biệt GC **pause/elapsed time** với **CPU time của GC workers**, và JIT **compilation events** với **CPU thực sự dùng**.
5. Thu thập JFR/GC log, đối chiếu thời điểm và quyết định hướng sửa phù hợp mà không tuning mò.

## 1. CPU time khác wall-clock time như thế nào?

**Wall time** là thời gian đồng hồ đã trôi qua. **CPU time** là lượng thời gian CPU thực sự chạy các lệnh của một process/thread (thường gồm user time và system/kernel time), được tích lũy qua những lần được scheduler cấp CPU. Thread ngủ, chờ I/O hoặc chờ lock có thể làm thời gian request kéo dài nhưng ít tiêu thụ CPU.

Với hai mẫu của **cùng process** cách nhau `Δwall` giây:

```text
CPU% theo một logical CPU = 100 × Δprocess_cpu_time / Δwall_time

CPU% chuẩn hóa trên N logical CPUs = 100 × Δprocess_cpu_time / (N × Δwall_time)
```

Đơn vị CPU time và wall time phải thống nhất. Tương tự, với một thread:

```text
thread_CPU% theo một logical CPU = 100 × Δthread_cpu_time / Δwall_time
```

Ví dụ **giả định** trong cửa sổ 10 giây:

- Process dùng 24 giây CPU time: **240% theo một core**; đó là tải trung bình tương đương 2,4 logical CPU.
- Máy có 8 logical CPU: con số tương ứng **30% tổng năng lực 8 core** nếu tính mẫu đúng cửa sổ và không có quota.
- Một thread dùng 8 giây CPU trong cùng cửa sổ: **80% một core**. Các thread khác cộng lại có thể dùng 16 giây CPU.
- Process ở mức 240% **không có nghĩa một thread sử dụng 240% một core**; các luồng cùng chạy trên nhiều CPU.

**Cảnh báo về công cụ:** `top` có chế độ chuẩn hóa theo từng core hoặc theo tổng CPU (Irix/Solaris mode), `ps %CPU` thường là tỷ lệ CPU time trên thời gian sống của process/thread thay vì một cửa sổ 1 giây, Task Manager và Kubernetes có mẫu số khác. Không so trực tiếp hai phần trăm từ những công cụ/mẫu số không tương thích.

**Tải cao ≠ CPU throttling:** container có quota 2 core trên host 32 core có thể bị giới hạn khi process cần 4 core. Nếu chỉ nhìn “12,5% host”, bạn sẽ bỏ sót việc container đã dùng hết quota. Kiểm tra `cpu.max`/`cpu.stat` (cgroup v2), request/limit Kubernetes và thời gian bị throttled.

## 2. Bốn tầng dễ bị đánh đồng

| Tầng quan sát | Đang đo cái gì? | Cách đọc đáng tin | Điều số liệu không tự chứng minh |
| --- | --- | --- | --- |
| **Process CPU** | Tổng CPU time của toàn tiến trình JVM: app threads + VM/GC/JIT/native hoạt động trong process | `top -p PID`, `pidstat -p PID`, JMX process CPU, JFR `jdk.CPULoad` | Không phân biệt thủ phạm là application, GC hay compiler. |
| **Thread CPU** | CPU time của một OS thread cụ thể | `top -H -p PID`, `pidstat -t -p PID`, hoặc ThreadMXBean cho **Java platform threads** | Tên thread hoặc trạng thái `RUNNABLE` không đủ kết luận CPU của nó trong cả cửa sổ. |
| **GC CPU** | CPU time do những GC/VM workers thực hiện công việc GC | GC logs có user/sys/real khi có, JFR GC, OS thread CPU, collector phase data | Tổng GC pause hoặc tổng wall time của GC không tự bằng CPU time tiêu thụ. |
| **Compiler CPU** | CPU dùng để JIT compile/optimize Java methods, thường bởi C1/C2 compiler workers | OS per-thread CPU + tên/stack, JFR compilation, `jcmd Compiler.queue`, compilation logs | Một method được compile nhiều không tự nói được tổng CPU của compiler. |

Các tầng không hoàn toàn tách rời: **GC và compiler đều nằm trong CPU process**; thread CPU là cách quy CPU process về từng thread nếu công cụ nhìn thấy đầy đủ. **Một thread application** cũng có thể dành thời gian chạy JDK library, native/JNI hoặc phần việc GC hỗ trợ, tùy collector và thời điểm. Không mặc định chỉ từ tên thread đã xác định chính xác mọi chu kỳ CPU.

## 3. Bước 1 — Xác định đúng JVM/PID và cửa sổ CPU

Ví dụ dùng PID **`12345`** trên Linux:

```bash
jcmd -l
top -p 12345
pidstat -p 12345 1 5
```

- `jcmd -l` liệt kê những JVM mà công cụ attach có thể phát hiện; trong Docker/namespace khác, JVM có thể không hiện. Dùng công cụ OS để lấy đúng PID nếu cần.
- `top -p` dùng cho quan sát nhanh; `pidstat -p 12345 1 5` (gói `sysstat`) cho 5 mẫu cách khoảng 1 giây, thuận tiện xem CPU tăng có bền vững hay chỉ spike.
- CPU **của JVM** cao nhưng **CPU toàn host** thấp có thể là một JVM dùng vài core trên máy lớn. Ngược lại host CPU cao nhưng JVM thấp thì cần xem các process khác.
- Ghi **timestamp, PID, version Java, collector, workload và container quota**; không cộng dữ liệu trước/sau lần restart thành một cửa sổ.

Nếu `pidstat` không được cài, có thể lấy nhiều mẫu `top`/OS metrics tương ứng. Trên Windows, dùng Task Manager/Process Explorer/PerfMon; không dùng lệnh `/proc` của Linux.

**Phân tích CPU phải có thời gian:** một snapshot `ps -p 12345 -o %cpu` chỉ là một dấu hiệu; không đủ để nói thread nào đã đốt CPU đúng lúc latency tăng.

## 4. Bước 2 — Tìm native thread nào thật sự dùng CPU

### 4.1. Đo theo OS thread ID (TID)

```bash
top -H -p 12345
pidstat -t -p 12345 1 5
ps -L -p 12345 -o pid,tid,pcpu,stat,comm
```

- `top -H` hiển thị các luồng của process, thường có cột `PID` nhưng trong thread mode giá trị đó thực chất là **TID** của mỗi thread.
- `pidstat -t` cung cấp lịch sử CPU theo TID trong các khoảng đo, tránh chọn nhầm thread chỉ vì nó vừa chạy trong một snapshot.
- `ps -L` hữu ích để xác minh PID/TID, trạng thái và tên, nhưng `pcpu` có cách tính theo lifetime nên không dùng nó như một mẫu CPU 1 giây nếu chưa xác minh semantics.
- Một thread chạy gần **100% một core** trong nhiều mẫu có thể là hot loop hoặc task CPU-bound; nhiều thread mỗi thread 20–40% có thể tạo process CPU tổng rất cao.

Chọn **2–3 TID đứng đầu liên tiếp**, ghi lại phần trăm và thời điểm. Lưu ý TID có thể được tái sử dụng khi thread kết thúc; ghép dữ liệu của những khoảng xa nhau mà không kiểm tra lifetime là nguy hiểm.

### 4.2. Ghép OS TID decimal với `nid` hexadecimal

HotSpot `Thread.print` có thể in Java thread như:

```text
"busy-worker" #35 prio=5 os_prio=0 cpu=5412.00ms elapsed=6.31s tid=0x00007f... nid=0x3039 runnable
   java.lang.Thread.State: RUNNABLE
        at demo.Worker.compute(Worker.java:42)
```

Đây là **mẫu minh họa**, tên/field/trình bày khác theo JDK và OS. `nid=0x3039` là **native thread ID ở hệ cơ số 16** tương ứng **12345** ở hệ thập phân. Ví dụ này chỉ giải thích chuyển đổi; PID JVM trong dòng lệnh `12345` ở phần trên có thể trùng số TID mẫu vì chọn số dễ nhớ, không phải quy tắc.

Đổi TID thập phân sang hex trên Bash:

```bash
printf '0x%x\n' 12345
```

Kết quả lệnh `printf` cho đúng số mẫu:

```text
0x3039
```

Hoặc trên PowerShell:

```powershell
'{0:x}' -f 12345
```

Lấy thread dump:

```bash
jcmd 12345 Thread.print -l
```

**Phân biệt ba ID:**

- **PID** là process ID JVM (theo namespace OS đang quan sát).
- **Linux TID/LWP** là ID của native thread trong process, dùng để ghép với HotSpot **`nid`**.
- **Java Thread.getId()/ThreadMXBean thread ID** là định danh của Java thread, **không phải TID của Linux**. Không dùng trực tiếp nó để tìm `nid` mà không có ánh xạ hợp lệ.

Nếu không thấy TID trong Java thread dump, có thể đó là VM/GC/JIT/native thread không được in như Java application thread, hoặc thread đã kết thúc, hoặc dump/OS lấy ở thời điểm hay PID namespace khác. OS threads là tín hiệu quan trọng ngay cả khi Java thread dump không hiện đủ worker nội bộ.

### 4.3. Đừng lấy `RUNNABLE` làm phép đo CPU

`RUNNABLE` trong Java thread dump có thể gồm thread đang chạy, sẵn sàng chạy hoặc thao tác native/I/O tùy nơi chặn. Thread `WAITING`/`TIMED_WAITING` thường không tiêu thụ nhiều CPU trong giai đoạn ngủ, nhưng trạng thái ở một thời điểm không nói lượng CPU của vài giây trước.

Cách liên hệ tốt hơn:

1. OS đo **CPU time tăng** của TID trong đúng cửa sổ.
2. Hai hoặc ba thread dump gần cửa sổ ấy cho biết stack ứng dụng/JVM nào liên quan.
3. JFR/async-profiler hoặc sampled method profiles cho biết hàm nào thường xuất hiện khi chạy CPU.
4. Ghép cả ba với workload/latency để tránh quy nhầm một thread nhất thời.

Một stack xuất hiện `java.util.HashMap` không khẳng định `HashMap` có bug: nó chỉ là địa điểm đang chạy. Cần xem caller và tần suất/mẫu CPU.

## 5. Bước 3 — Phân biệt GC CPU với GC pause

GC có thể dùng CPU trong **stop-the-world (STW)** và/hoặc **pha concurrent**. STW pause là **thời gian ứng dụng bị dừng theo ranh giới đo của GC**, còn CPU time của GC là **tổng thời gian CPU mà các worker dùng**.

Ví dụ giả định:

- Một pha STW dài 100 ms có **4 GC worker** cùng thực thi trung bình 80 ms CPU mỗi worker: tổng GC CPU time xấp xỉ **320 ms**, dù wall pause chỉ **100 ms**.
- Một pha concurrent GC có thể dùng CPU khi ứng dụng vẫn chạy, tăng process CPU trong khi pause STW rất ngắn.
- Không được suy **GC CPU% = tổng GC pause / thời gian cửa sổ**, cũng không cộng tất cả wall-time pha concurrent vào STW.

### 5.1. Bật GC logging

Với JVM mới khởi động, ví dụ HotSpot JDK 17:

```bash
java -Xms256m -Xmx512m \
  -Xlog:gc*=info:file=gc.log:time,uptime,level,tags \
  -jar app.jar
```

Trong log, tìm **số lần/loại GC**, STW pause, các pha concurrent, heap before/after, và dòng **CPU times user/sys/real** nếu collector/JDK có phát ra.

- **`user`**: tổng CPU user time của các luồng liên quan trong phép hạch toán log.
- **`sys`**: CPU kernel/system time.
- **`real`**: thời gian wall-clock của pha/sự kiện đó.
- **`user + sys` lớn hơn `real`** có thể hoàn toàn bình thường khi GC song song sử dụng nhiều worker. Không hiểu đây là lỗi log.
- Với collector concurrent, các dòng thời gian riêng cũng không nhất thiết thể hiện *toàn bộ* CPU GC của process. Cần hiểu phạm vi từng pha, các worker và nguồn đo.

Không phải GC log nào cũng có đủ thông tin CPU, đặc biệt với các tag/level khác. Nếu chưa thấy `user/sys/real`, xem log configuration/JDK thay vì tự suy từ pause time.

### 5.2. Dùng JFR để đối chiếu GC

Nếu recording đã thu thập đúng khoảng thời gian:

```bash
jfr summary diag.jfr
jfr print --events "jdk.GarbageCollection,jdk.GCPhasePause" diag.jfr
```

`jdk.GarbageCollection` mô tả GC event; `jdk.GCPhasePause` nêu duration của pause được ghi. Duration không đồng nghĩa tổng CPU GC. Để nhận diện hoạt động GC nền, kết hợp timeline/collector-specific events/OS TID CPU. Đừng mặc định mọi tên event đều bật trong recording; `summary` cho biết instance nào có thực.

Khi **process CPU cao** và **GC log ghi các GC phases dày đặc**, thread OS có tên GC workers chiếm CPU, heap sau GC ít giảm hoặc allocation rate rất cao, đây là bằng chứng nghiêng về **GC overhead**. Ngược lại một pause dài nhưng CPU trung bình của process thấp không có nghĩa mọi thời gian pause là thời gian “đốt CPU”; vẫn phải xem safepoint, collector, scheduler và workload.

### 5.3. Khi nào nên chỉnh GC?

Chỉ sau khi có bằng chứng. Kiểm tra live set, allocation rate, premature promotion, bộ nhớ heap, memory pressure, GC collector flags và giới hạn CPU. Việc giảm allocation trong ứng dụng thường hữu ích hơn chỉnh collector mù quáng. Một số collector dùng thêm thread nền khi có CPU nhàn; cần cân bằng **throughput, tail latency và CPU headroom**.

## 6. Bước 4 — Phân biệt CPU của JIT/compiler

**Just-In-Time compiler (JIT)** chuyển/optimize các Java methods nóng thành mã máy. HotSpot có các compiler tiers; các luồng thường mang tên liên quan **`C1 CompilerThread`**, **`C2 CompilerThread`**, hoặc JVMCI tùy cấu hình/JDK. CPU compilation là **công việc nền của JVM**, vẫn được tính trong CPU process. Một số nguyên nhân:

- Ứng dụng vừa khởi động/warm-up hoặc deploy code mới; nhiều hot methods được biên dịch.
- Nhiều class/method được tải và thực thi lần đầu, tiered compilation hoạt động.
- Biên dịch lại, deoptimization hoặc code cache pressure khiến compiler tiếp tục làm việc.
- Một workload làm phát sinh nhiều method specialization/hot spots; có thể kéo dài compilation hơn dự kiến.

**Không đồng nhất “JIT compile nhiều” với “JIT CPU là thủ phạm”**: cần thấy TID compiler thực sự tiêu thụ CPU cùng cửa sổ với compiler activity. Và **CPU dùng để chạy mã đã JIT-compile** vẫn thuộc thread ứng dụng, không phải CPU của compiler thread.

### 6.1. Lệnh chẩn đoán JIT

```bash
jcmd 12345 Compiler.queue
jcmd 12345 Compiler.codecache
jcmd 12345 VM.flags
```

- `Compiler.queue` cho biết những method đang xếp hàng compile **tại thời điểm lấy mẫu**; queue trống ở một thời điểm không phủ nhận compilation trước đó.
- `Compiler.codecache` mô tả vùng mã máy đã biên dịch. Code cache nhiều không tự chứng minh compiler đang sử dụng CPU nhiều.
- `VM.flags` giúp xác định các tùy chọn/tình huống như tiered compilation, code cache, compiler thread settings; xem thêm `jcmd 12345 help Compiler.queue` để kiểm tra command được JVM đích hỗ trợ.

Có thể bật log compilation **khi khởi động** trong môi trường thử nghiệm:

```bash
java -XX:+PrintCompilation -jar app.jar
```

Log này cho biết thời điểm và những method được compile theo cách JVM ghi nhận. **Đây không phải dữ liệu CPU% của compiler workers.** Việc bật log có overhead, output có thể lớn và không nên suy trực tiếp lượng CPU từ số dòng log.

### 6.2. JFR compiler events

```bash
jfr summary diag.jfr
jfr print --events "jdk.Compilation,jdk.CompilerQueueUtilization" diag.jfr
```

Các event này có thể giúp đối chiếu compilation duration và queue activity, tùy phiên bản/cấu hình ghi. Một **compilation duration** là thời gian thực hiện công việc biên dịch theo semantics của event; không được cộng tất cả duration rồi gọi chính xác là total compiler CPU nếu chưa xác minh có nhiều compiler workers, overlap và định nghĩa field.

Khi OS TID cho thấy compiler workers chiếm CPU trong nhiều cửa sổ, compilation events/tiered compilation diễn ra dày, GC không đặc biệt nặng và application samples không chiếm phần lớn, khả năng cao nguồn tăng process CPU là JIT. Với warm-up hợp lệ, có thể chỉ cần đo ổn định sau khi warm-up; với CPU kéo dài ảnh hưởng SLA, xem startup/deploy patterns, code cache, profiling và đặc điểm workload trước khi thay đổi compiler flags.

**Không vội tắt JIT hoặc tắt tiered compilation** để “giảm CPU”: giảm CPU biên dịch có thể làm mã ứng dụng chạy chậm hơn và tiêu thụ tổng CPU nhiều hơn. Phải benchmark cùng workload từ cold start và steady state.

## 7. JFR kết hợp OS: nhìn timeline thay vì một screenshot

Với PID `12345`, ghi thử 60 giây (file sẽ được tạo sau khi recording hoàn thành):

```bash
jcmd 12345 JFR.start name=cpu-diag settings=profile duration=60s filename=cpu-diag.jfr
```

Sau khi file đã được tạo:

```bash
jfr summary cpu-diag.jfr
jfr print --events "jdk.CPULoad,jdk.ThreadCPULoad" cpu-diag.jfr
jfr print --events "jdk.ExecutionSample" --stack-depth 24 cpu-diag.jfr
jfr print --events "jdk.GarbageCollection,jdk.GCPhasePause,jdk.Compilation" cpu-diag.jfr
```

- **`jdk.CPULoad`**: tín hiệu CPU của process/JVM so với máy theo recording (nếu bật và có instance).
- **`jdk.ThreadCPULoad`**: tín hiệu CPU per-thread theo khả năng thu thập JFR; đối chiếu TID, thread lifetime, khoảng đo. Không xem số mẫu method thay thế trực tiếp cho CPU time.
- **`jdk.ExecutionSample`**: lấy mẫu stack của Java code chạy, hữu ích tìm hot methods. **Số lượng sample chỉ ước lượng điểm nóng**, phụ thuộc tần suất sampling, event settings, thread có thể lấy mẫu và thống kê; không đồng nghĩa số ms CPU chính xác tuyệt đối.
- **`jdk.GarbageCollection/jdk.GCPhasePause`**: thời gian/tình huống GC; không phải mọi pha được tính như STW.
- **`jdk.Compilation`**: diễn biến biên dịch; cần đối chiếu CPU của compiler OS threads, vì duration của event không tự là CPU load.

Dùng `jfr summary` trước để biết event nào xuất hiện. Có thể mở cùng file bằng **JDK Mission Control (JMC)** để xem timeline, CPU, threads, GC, hot methods và compiler activity. **JFR của Java application không nhất thiết lấy mẫu đầy đủ mọi GC/JIT/native worker**; khi nghi CPU native, kết quả OS/perf profiler vẫn quan trọng.

Một cách đọc đúng:

```text
CPU process tăng ở t = 14:32:10
         |
         +-- OS TID worker-7 tăng CPU?
         |       +-- JFR ExecutionSample + thread dump -> application hot path
         |
         +-- OS GC worker(s) tăng CPU?
         |       +-- GC log + JFR GC events -> GC phase và allocation pressure
         |
         +-- OS C2 CompilerThread tăng CPU?
                 +-- Compiler.queue + JFR Compilation -> JIT work
```

Luôn kiểm tra clocks: OS samples, GC log và JFR timestamps có thể dùng timezone/định dạng khác nhau. Không ghép sự kiện chỉ vì thứ tự output tình cờ giống nhau.

## 8. Java 17+: ví dụ đo CPU của hai Java thread và CPU process

Chương trình sau tạo **một thread bận tính toán** và **một thread ngủ**, lấy hai mẫu CPU time và wall time. Nó **không ép gây GC/JIT CPU cao** vì mục tiêu là thấy khác biệt giữa CPU process và CPU từng Java thread. Nó cũng minh họa vì sao CPU process chứa thêm hoạt động JVM ngoài hai thread demo.

Tạo file **`CpuAttributionDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.atomic.AtomicBoolean;

public class CpuAttributionDemo {
    private static volatile long result;

    private static void spin(AtomicBoolean running) {
        long value = 1L;
        while (running.get()) {
            value = value * 1664525L + 1013904223L;
        }
        result = value;
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        boolean threadCpuEnabled =
                threads.isThreadCpuTimeSupported() && threads.isThreadCpuTimeEnabled();

        com.sun.management.OperatingSystemMXBean os =
                ManagementFactory.getPlatformMXBean(
                        com.sun.management.OperatingSystemMXBean.class);

        AtomicBoolean running = new AtomicBoolean(true);
        Thread busy = new Thread(() -> spin(running), "demo-busy");
        Thread sleeper = new Thread(() -> {
            while (running.get()) {
                try {
                    Thread.sleep(50);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "demo-sleep");

        busy.start();
        sleeper.start();

        long wallStart = System.nanoTime();
        long procStart = os == null ? -1 : os.getProcessCpuTime();
        long busyStart = threadCpuEnabled ? threads.getThreadCpuTime(busy.getId()) : -1;
        long sleepStart = threadCpuEnabled ? threads.getThreadCpuTime(sleeper.getId()) : -1;

        Thread.sleep(1000);

        long wallEnd = System.nanoTime();
        long procEnd = os == null ? -1 : os.getProcessCpuTime();
        long busyEnd = threadCpuEnabled ? threads.getThreadCpuTime(busy.getId()) : -1;
        long sleepEnd = threadCpuEnabled ? threads.getThreadCpuTime(sleeper.getId()) : -1;

        running.set(false);
        busy.join();
        sleeper.join();

        double wallSeconds = (wallEnd - wallStart) / 1_000_000_000.0;
        System.out.println("Threads: " + busy.getName() + ", " + sleeper.getName());

        if (procStart >= 0 && procEnd >= procStart) {
            double percent = 100.0 * (procEnd - procStart)
                    / (wallEnd - wallStart);
            System.out.printf("processCpu=%.1f%% of one core%n", percent);
        } else {
            System.out.println("processCpu: unavailable");
        }

        if (busyStart >= 0 && busyEnd >= busyStart
                && sleepStart >= 0 && sleepEnd >= sleepStart) {
            double busyPercent = 100.0 * (busyEnd - busyStart)
                    / (wallEnd - wallStart);
            double sleepPercent = 100.0 * (sleepEnd - sleepStart)
                    / (wallEnd - wallStart);
            System.out.printf("busyCpu=%.1f%% sleepCpu=%.1f%% of one core%n",
                    busyPercent, sleepPercent);
        } else {
            System.out.println("threadCpu: unavailable");
        }

        System.out.println("DONE");
    }
}
```

Biên dịch và chạy trên **HotSpot JDK 17+**:

```bash
javac --release 17 CpuAttributionDemo.java
java CpuAttributionDemo
```

Các dòng do chương trình tự in có nội dung ổn định:

```text
Threads: demo-busy, demo-sleep
<one line showing processCpu or processCpu: unavailable>
<one line showing busyCpu/sleepCpu or threadCpu: unavailable>
DONE
```

Hai dòng có dấu ngoặc nhọn ở trên là **mô tả vị trí output thay đổi**, không phải văn bản output thật; số CPU phải được lấy từ máy chạy. Khi CPU metrics được hỗ trợ và bật, thường thấy `busyCpu` lớn hơn `sleepCpu` trong khoảng mẫu. Nhưng scheduler, container quota, CPU throttling, GC/JIT và điều kiện thử nghiệm có thể làm phần trăm khác đáng kể; không hứa “đúng 100%”.

Giải thích thiết kế:

- `System.nanoTime()` đo **wall elapsed** giữa hai mẫu, không phải CPU time.
- `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` (HotSpot/OpenJDK JDK management extension) đo **CPU time tích lũy của process**, gồm các thread bên trong JVM, không chỉ hai Java demo threads. Nó có thể trả `-1` khi không hỗ trợ.
- `ThreadMXBean.getThreadCpuTime(id)` đo **CPU time tích lũy của Java platform thread** theo ID Java, có thể trả `-1` nếu unsupported/disabled hoặc thread không còn sống. Chụp cả hai mẫu **trong khi thread vẫn sống** rồi mới dừng/join.
- Đo thread CPU của JVM có thể bị tắt; ví dụ kiểm tra trạng thái và **không tự bật** vì thay đổi cấu hình thu thập có thể có overhead.
- `getId()` ở Java 17 là **Java thread ID**, không phải Linux TID hay HotSpot `nid`. Ví dụ này không cung cấp mapping sang OS thread ID.
- `result` là `volatile` để giữ kết quả vòng tính không biến thành logic vô nghĩa đối với optimizer; `AtomicBoolean` cung cấp tín hiệu dừng có khả năng nhìn thấy xuyên threads.
- Vòng bận chỉ chạy khoảng một giây; trong production không thực hiện thử nghiệm kiểu busy loop. Đây là chương trình học tập độc lập.

**Giới hạn quan sát:** Tổng CPU của các **Java platform threads** mà `ThreadMXBean` thấy không luôn bằng toàn bộ CPU process, vì JVM có thể dùng VM/GC/compiler/native threads không hiện trong tập Java thread IDs, và vì các phép đo không chụp đồng thời tuyệt đối. Muốn quy chính xác CPU cho GC/JIT, phối hợp công cụ OS và JVM thay vì lấy hiệu số rồi tự gọi phần dư là “GC”.

## 9. CPU cao nhưng ứng dụng không xử lý nhanh hơn: xét quota và contention

CPU tiêu thụ lớn có thể là công việc có ích hoặc chi phí không hiệu quả:

- **CPU-bound hợp lệ:** service xử lý ảnh, nén, mã hóa, tính toán phức tạp; nhiều core bận và throughput tăng theo tải.
- **Busy spin/polling:** loop kiểm tra trạng thái không sleep/backoff, retry quá nhanh hoặc regex/pathological algorithm; một thread duy trì gần một core dù throughput không tăng.
- **Lock contention:** nhiều thread `BLOCKED` hay chờ I/O thường kéo dài wall time chứ không tự đốt CPU; nếu spin lock/active retry có thể đốt CPU. Cần đọc stack và CPU time thực.
- **GC pressure:** allocation churn, live set cao hoặc collector activity kéo dài tiêu CPU để dọn bộ nhớ.
- **JIT warm-up:** compiler threads đốt CPU trong một giai đoạn có thể chấp nhận được để tăng hiệu suất steady state.
- **CPU throttling:** container đã cạn quota; application đang chờ scheduler, latency tăng dù process nhìn không đạt 100% tổng host.

Với Linux **cgroup v2**, kiểm tra đúng cgroup chứa JVM (đường dẫn chỉ minh họa root mặc định):

```bash
cat /proc/12345/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
```

- `cpu.max` chứa quota và period hoặc từ `max` nếu không đặt quota tại cgroup đó. Ví dụ `200000 100000` tương ứng khoảng **2 CPU** quota bình quân, không có nghĩa có đúng hai logical core được pin.
- `cpu.stat` có các bộ đếm như `usage_usec` và `nr_throttled`/`throttled_usec` khi CPU controller cung cấp; **lấy hiệu giữa hai mẫu** mới biết CPU đã dùng và throttling trong cửa sổ.
- Nếu JVM nằm ở cgroup con hoặc có giới hạn ở cgroup cha, phải xác định **đúng đường dẫn và ancestor quota**. Các đường dẫn `/sys/fs/cgroup` ở trên không đảm bảo trỏ tới đúng cgroup của JVM trong mọi máy/container.
- Giá trị `throttled_usec` là thời gian hệ thống báo throttling theo semantics của cgroup, không tự tương đương độ trễ request. Cần ghép timestamp và latency.

**Khi host CPU thấp mà service vẫn chậm**, hãy kiểm tra cả quota/throttling, lock/I/O và scheduler. Không kết luận “CPU chưa cao nên CPU không phải vấn đề”.

## 10. Ma trận chẩn đoán nhanh

| Số liệu quan sát trong cùng cửa sổ | Nghi vấn ưu tiên | Cách xác nhận |
| --- | --- | --- |
| Process CPU cao; **một TID Java application** gần 100% một core; stack lặp lại logic app | Hot loop, thuật toán tốn CPU, retry/polling | `top -H` + TID→`nid` + nhiều thread dump + JFR ExecutionSample |
| Process CPU cao; **nhiều application TIDs** 30–70% | Parallel workload, concurrency, contention/spin | Group OS TIDs, CPU profiles, queue depth/throughput, xem app methods |
| Process CPU cao; **GC worker threads** có CPU lớn; GC log nhiều hoạt động | GC overhead hoặc allocation churn | GC logs, heap after-GC, JFR GC events, OS worker CPU |
| Process CPU cao; **C1/C2 CompilerThread** chiếm CPU khi warm-up | JIT compilation | OS per-thread + JFR Compilation + Compiler.queue/codecache + deployment timing |
| Process CPU cao; thread dump application không có thread nào chiếm CPU tương xứng | JVM internal/native/JNI threads hoặc giới hạn quan sát | OS TID + native profiler/JFR/NMT khi phù hợp; không suy phần dư là GC |
| Process CPU vừa phải; host CPU cao | Process khác dùng CPU | `top`/Process Explorer toàn máy, cgroup/host metrics |
| CPU% host thấp; cgroup `nr_throttled` tăng; latency cao | Container CPU quota pressure | `cpu.max`, `cpu.stat`, container usage/limits, p95/p99 latency |
| Latency cao; process CPU thấp; nhiều thread WAITING/BLOCKED | I/O, lock contention, external dependency | Thread dump, traces, lock metrics; CPU không phải nguồn duy nhất |
| GC pause tăng nhưng GC worker CPU chưa cao | STW/safepoint hoặc scheduling issue | GC phases, safepoint log, OS pressure; không đánh đồng pause với CPU |
| Compiler queue có việc nhưng compiler TIDs CPU thấp | Queue tồn tại ở thời điểm chụp | Lấy mẫu TID nhiều lần trước khi quy CPU cho compiler |

**Quy tắc:** Có **triệu chứng** → đo **process CPU** → tìm **TID và tỷ lệ CPU theo cửa sổ** → ghép **stack/sự kiện JVM** → đối chiếu **GC/JIT/container/ứng dụng** → sửa và đo lại. Một ảnh chụp từ `top` hoặc một thread dump đứng riêng không đủ để chứng minh quan hệ nhân quả.

## 11. Quy trình điều tra thực tế có thể lặp lại

### Trường hợp: JVM dùng 260% CPU lúc service p99 tăng

Đây là **tình huống giả định**, không phải dữ liệu quan sát từ hệ thống cụ thể.

1. **Khóa phạm vi:** xác nhận 260% là từ `top` ở chế độ theo core, tức khoảng **2,6 core**; ghi số core, container quota, PID, timestamp và tải.
2. **Lấy 5 mẫu theo TID:** `pidstat -t -p PID 1 5`; giả sử thấy một application TID ~90%, hai GC workers tổng ~120%, compiler worker ~30%; các TID khác đóng góp phần còn lại.
3. **Ghép HotSpot `nid`:** đổi từng TID decimal sang hex, lấy `jcmd PID Thread.print -l` gần thời gian đó. Application thread có thể đang chạy method nặng, GC/JIT workers có thể không nằm trong danh sách Java threads.
4. **Đối chiếu GC/JFR:** nếu GC pause/concurrent work dày và heap after-GC lớn, GC overhead có cơ sở; nếu hoạt động GC thưa, không nên quy 120% chỉ từ tên `GC worker` khi chưa có timeline/pha.
5. **Đối chiếu compiler:** có compilation events và compiler queue trong cùng cửa sổ không? Nếu đang warm-up sau deploy, JIT CPU có thể là ngắn hạn.
6. **Phân tích application 90%:** lấy JFR ExecutionSample hoặc CPU profiler, xác định hot code; một method trên stack dump không phải bằng chứng hotspot nếu chỉ xuất hiện một lần.
7. **Thực hiện thay đổi có mục tiêu:** giảm allocation/busy loop, sửa algorithm, điều chỉnh concurrency hoặc cấu hình GC sau khi đo; cân nhắc warm-up strategy nếu JIT đáng kể.
8. **Đo lại cùng tải:** so sánh CPU process/core, per-thread, GC pause và GC CPU, compiler activity, throughput và p99. Đừng chỉ tối ưu cho một con số CPU rồi làm throughput giảm.

### Cần ghi gì trong báo cáo sự cố?

Nên lưu **bảng thời gian cùng nguồn đo**:

| Thời điểm | Process CPU/core | Top TID và CPU | GC/JIT evidence | Latency/throughput |
| --- | --- | --- | --- | --- |
| Trước spike | Nền | Nền | Ít sự kiện đáng kể | Bình thường |
| Trong spike | Cao | TID cụ thể | Log và JFR tương ứng | p99 cao |
| Sau spike | Trở về nền? | TID nào giảm? | GC/JIT có kết thúc? | p99 phục hồi? |

Điền **số liệu thật** từ công cụ, không lấy giá trị giả định của bài như kết quả quan sát. Khi logging/sampling tạo overhead, ghi nhận mức tác động của nó.

## 12. Những sai lầm phổ biến

1. **“Process 300% CPU nghĩa là một thread 300%.”** Sai trong cách đo theo một core: thường là nhiều luồng cùng dùng ~3 core CPU.
2. **“Java thread `RUNNABLE` là thread đốt CPU.”** Sai: cần CPU time delta và sampling ở đúng cửa sổ.
3. **“CPU process cao chắc do vòng lặp trong ứng dụng.”** Sai: GC workers, C1/C2 compiler, JVM/native threads và JNI đều nằm trong process.
4. **“GC pause 200 ms nghĩa là GC dùng 200 ms CPU.”** Sai: pause là wall time của pha dừng; các worker có thể chạy song song hoặc GC concurrent.
5. **“Nhiều GC events chứng minh GC chiếm CPU nhiều nhất.”** Chưa đủ: cần CPU time hoặc bằng chứng worker/TID/phase.
6. **“Compiler queue còn việc nghĩa là compiler đang dùng 100% core.”** Chưa đủ: queue snapshot không phải CPU metric.
7. **“Dòng `PrintCompilation` là 1 ms CPU của compiler.”** Sai: cần hiểu nội dung log cụ thể và CPU time thực tế.
8. **“Tăng heap luôn chữa CPU cao.”** Sai: chỉ có ích trong một số tình huống allocation/GC; có thể tăng memory footprint và làm vấn đề khác.
9. **“`ps %CPU` và `pidstat 1 5` là cùng một cửa sổ.”** Sai: `ps` có thể dùng lifetime average, còn `pidstat` báo khoảng lấy mẫu.
10. **“`nid` là `Thread.getId()`.”** Sai: HotSpot `nid` liên hệ OS native TID; Java thread ID là khái niệm khác.
11. **“Không thấy thread trong `Thread.print` thì nó không tồn tại.”** Sai: có VM/internal/native workers không hiện như Java thread; còn race thời điểm.
12. **“JFR mẫu method cho biết chính xác mili giây CPU của mỗi hàm.”** Sai: sampling là ước lượng thống kê; cần đủ mẫu và hiểu sampling bias.
13. **“CPU host thấp nên container không thể thiếu CPU.”** Sai: quota cgroup có thể đã chạm và throttled.
14. **“CPU cao luôn xấu.”** Sai: CPU dùng hiệu quả có thể đi kèm throughput tốt; xét mục tiêu latency/throughput, cost và headroom.
15. **“Chỉ cần một thread dump để tìm nguyên nhân spike.”** Sai: dump là snapshot của state/stack, cần ghép với CPU delta và timeline.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Trong 10 giây, JVM tăng 18 giây CPU time. CPU% theo một core là bao nhiêu?  
**Đáp án:** 180%; tức trung bình 1,8 core. Nếu máy có 8 logical cores và không bị quota, đó xấp xỉ 22,5% tổng 8 core.

**Câu 2.** `top -H` thấy TID 4096 đứng đầu, còn `Thread.print` ghi `nid=0x1000`. Có thể liên hệ không?  
**Đáp án:** Có, 0x1000 hex = 4096 decimal, nếu cùng OS namespace, cùng JVM và thread còn sống.

**Câu 3.** GC pause 50 ms, có 8 worker chạy cùng lúc. Có thể tổng CPU time của GC vượt 50 ms không?  
**Đáp án:** Có. Song song nhiều worker có thể cộng ra CPU time lớn hơn wall pause; phải đo/đối chiếu phạm vi cụ thể.

**Câu 4.** Một `C2 CompilerThread` có CPU cao ngay sau deploy, nhưng method app CPU ít. Có thể quy về JIT ngay không?  
**Đáp án:** Đây là giả thuyết mạnh nếu cùng cửa sổ có compilation events/queue activity; cần đối chiếu nhiều mẫu TID/JFR trước khi kết luận.

**Câu 5.** `ThreadMXBean.getThreadCpuTime(7)` trả `-1`. Có nghĩa Java thread không dùng CPU?  
**Đáp án:** Không. Có thể thread đã kết thúc, không tồn tại, CPU time bị tắt hoặc không hỗ trợ. Không được biến “không đo được” thành “0 CPU”.

**Câu 6.** Máy có 32 core, container quota 2 core, JVM báo khoảng 180% theo một core. Có thể bị throttling không?  
**Đáp án:** Có. JVM có thể gần quota 2 core mặc dù chỉ dùng khoảng 5,6% năng lực 32 core của host. Phải kiểm tra `cpu.max`, `cpu.stat` và số liệu thực.

**Câu 7.** Thread dump có stack `java.util.HashMap.get` ở một luồng `RUNNABLE`. Có nên tối ưu `HashMap` ngay?  
**Đáp án:** Không. Cần CPU per-TID cùng cửa sổ, nhiều stack sample, hot path/caller và dữ liệu phân bố để xác định nguyên nhân.

## Tài liệu tra cứu

- [Oracle JDK 17 — `jcmd`: `Thread.print`, `Compiler.queue`, `Compiler.codecache`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — `ThreadMXBean` và `getThreadCpuTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle JDK 17 — `java`, GC Unified Logging và `PrintCompilation`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle JDK 17 — Troubleshoot Performance Issues Using JFR: CPULoad, ThreadCPULoad, GC, hot methods](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 17 — `jfr`: `print` và `summary`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Oracle Java SE 17 — `OperatingSystemMXBean` extension](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Linux kernel documentation — Control Group v2: CPU controller](https://docs.kernel.org/admin-guide/cgroup-v2.html)
