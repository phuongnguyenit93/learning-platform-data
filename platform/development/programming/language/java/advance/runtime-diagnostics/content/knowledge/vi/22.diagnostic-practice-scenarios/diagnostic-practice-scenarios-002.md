# 22.2 Chẩn đoán vòng lặp tốn CPU bằng jcmd, thread dump và JFR

## 1. Bài toán: CPU tăng cao, nhưng thread nào và mã nào đang chạy?

Một JVM có CPU cao không đồng nghĩa ngay với “vòng lặp vô hạn”. CPU có thể được tiêu thụ bởi **mã ứng dụng chạy liên tục**, biên dịch JIT, garbage collection, serialization, mã native, tác vụ nền, nhiều request hợp lệ, hoặc sự tranh chấp tài nguyên. Ngay cả khi một thread ở trạng thái `RUNNABLE`, riêng trạng thái đó cũng **chưa chứng minh** nó thực sự dùng nhiều thời gian CPU.

Bài thực hành này kết hợp **ba lớp bằng chứng**:

1. **Hệ điều hành:** tiến trình Java và **native thread ID (TID)** nào đang tiêu thụ CPU theo thời gian?
2. **`jcmd Thread.print`:** native thread đó đang chạy stack Java nào, và stack ấy có lặp lại qua nhiều thời điểm hay không?
3. **Java Flight Recorder (JFR):** các **execution samples** có thường xuyên bắt gặp cùng đường mã nóng trong cửa sổ ghi không, đồng thời CPU và hoạt động JVM diễn biến thế nào?

Kết quả mong đợi là một **chuỗi suy luận có thể kiểm tra lại**: đúng JVM → đúng TID → đúng Java thread → method/vòng lặp nghi vấn → bằng chứng lặp lại qua thời gian → phép thử đối chứng. Không kết luận nguyên nhân chỉ vì một thread dump chứa `RUNNABLE` hoặc một flame graph có method nổi bật.

Phạm vi: Java 17+ trên HotSpot; ví dụ lệnh **Linux** để tìm native TID và ví dụ JDK 21 cho `jcmd`/`jfr`. Trên Windows/macOS, vẫn dùng được phần Java/`jcmd`/JFR nhưng cách quan sát per-thread CPU và định danh OS cần công cụ tương ứng.

## 2. Phân biệt “CPU cao”, “bận chờ”, “treo” và “chậm”

| Hiện tượng | CPU tiến trình | Dấu hiệu thread | Giả thuyết cần kiểm tra |
| --- | --- | --- | --- |
| **Busy CPU loop** | Thường cao trên một hoặc nhiều logical core | Một hoặc nhiều thread tiêu thụ CPU; stack lặp tại method tính toán | Vòng lặp không có điểm thoát, thuật toán quá đắt, polling không backoff |
| **Busy-wait / spin** | Có thể cao dù hệ thống không tạo nhiều kết quả | Thread quay liên tục kiểm tra cờ/queue/lock | Polling quá dày; vòng chờ thiếu sleep/park/backoff |
| **Deadlock/blocking wait** | Có thể thấp trong khi request vẫn kẹt | `BLOCKED`/`WAITING`/`TIMED_WAITING`; lock/deadlock hints | Monitor/lock/condition/I/O; không phải CPU loop chỉ vì thread không tiến |
| **Nhiều request hợp lệ** | Cao theo tải, throughput có thể tăng tương ứng | CPU phân bố trên nhiều worker threads | Workload lớn, capacity/CPU quota, cấu hình concurrency |
| **GC/JIT chiếm CPU** | Có thể cao dù Java business threads không nóng | GC/compiler threads và event GC/compilation | Allocation churn, GC pressure, warm-up, code compilation |
| **CPU throttling trong container** | CPU quan sát trên host có thể khác mức giới hạn container | Thread runnable nhưng thiếu CPU thực thi | Cgroup quota/throttling; CPU cao ≠ toàn bộ thời gian wall clock được chạy |
| **CPU thấp, latency cao** | Thấp hoặc vừa | Thread chờ network, database, lock, queue | Nút nghẽn nằm ngoài mã tính toán |

**Điểm phân biệt:** `RUNNABLE` trong Java thread dump bao gồm thread đang thực thi lẫn một số đường native/đang đủ điều kiện chạy. Nó không phải số đo “thread này đã dùng 98% CPU”. Cần **CPU accounting của OS** hoặc CPU time theo thread trong khoảng thời gian mới xác nhận được tiêu thụ CPU.

Đặc biệt, **CPU percentage có nhiều mẫu số**: 100% của **một logical core** trong `top` có thể tương ứng khoảng 12,5% **toàn máy 8 logical cores** tùy cách hiển thị; cgroup CPU quota, SMT, chuẩn hóa `top/ps`, số core khả dụng và thời gian lấy mẫu đều ảnh hưởng. Không so trực tiếp phần trăm từ hai công cụ nếu chưa biết quy ước.

## 3. Sơ đồ quyết định điều tra

```text
CPU alert / ứng dụng chậm
         |
         v
Xác nhận host, PID, JVM uptime, thời điểm, mức tải
         |
         v
OS: process CPU? CPU theo TID qua nhiều lần lấy mẫu?
         |
         +---- Không có thread Java tiêu thụ rõ rệt
         |       |
         |       v
         |    Xem GC/JIT/native work, CPU quota/throttling,
         |    số thread, metrics độc lập, thời gian sampling
         |
         +---- Có TID nóng ổn định
                 |
                 v
          TID decimal -> hex -> nid trong thread dump
                 |
                 v
          Lặp thread dumps T0/T1/T2, stack giống nhau?
                 |
                 +--- Không: workload/đường mã biến động,
                 |    thread tái sử dụng hoặc code thay đổi
                 |
                 +--- Có: khoanh vùng method/loop nghi vấn
                              |
                              v
                    JFR profile trong cùng cửa sổ
                              |
                              v
                    Execution samples + CPU/GC/JIT events
                              |
                              v
                    Đối chứng busy vs idle / thay một biến
                              |
                              v
                    Kết luận có mức tin cậy, ghi giới hạn
```

Đây không phải luồng bắt buộc để điều tra **mọi** incident, nhưng giúp tách “thread đã ở đâu” khỏi “thread đã thật sự đốt CPU”. Bước xác minh PID trước khi nối dữ liệu là đặc biệt quan trọng sau restart, vì OS có thể cấp lại PID/TID.

## 4. Chuẩn bị môi trường và các giới hạn an toàn

Cần có:

- **JDK 17+** để biên dịch/chạy; `jcmd` và `jfr` có trong JDK phù hợp, có thể không có trong image runtime tối giản.
- Terminal trên cùng host/namespace phù hợp, hoặc công cụ quản trị được cấp quyền. Theo tài liệu JDK, `jcmd` thường cần chạy trên cùng máy và với quyền user tương ứng target JVM; attach trong container có giới hạn riêng.
- Linux `top`, `ps`, `printf`, `sleep` cho các lệnh nhận diện TID. Lệnh `pidstat` nếu cài `sysstat` chỉ là công cụ bổ sung.
- Một thư mục có quyền ghi để lưu `.jfr`, thread dumps và manifest. Đường dẫn của `jcmd ... JFR.start filename=...` được giải quyết theo **filesystem của JVM mục tiêu**, không nhất thiết là đường dẫn nhìn từ shell quản trị nếu target nằm trong container.

**Không chạy demo busy loop trên production.** Dù chương trình có giới hạn thời gian, nó chủ đích sử dụng CPU liên tục của một thread và có thể ảnh hưởng máy dùng chung. Ưu tiên laptop, VM/staging cô lập hoặc container có quota rõ ràng. Để CPU tăng mà không cần làm hỏng JVM, demo không sử dụng native crash, `Unsafe`, cấp phát heap vô hạn hay vòng lặp chạy mãi.

Đối với JVM thật, nên ưu tiên quan sát ít xâm lấn trước, thu 2–3 thread dumps có khoảng cách hợp lý, không kích hoạt `GC.heap_dump`/Full GC chỉ để điều tra CPU. Một snapshot lớn có thể tạo pause/overhead và thay đổi chính hiện tượng đang khảo sát.

## 5. Chương trình Java 17+ tái hiện được, có đối chứng

Để kiểm chứng từng lớp quan sát, tạo **một platform thread** tên `cpu-hot-loop`. Chế độ `busy` lặp phép tính CPU liên tục trong thời gian hữu hạn; chế độ `idle` giữ cùng vòng đời nhưng dùng `sleep` để hầu như không tiêu tốn CPU. Cả hai cùng tên thread để dễ đối chiếu; **tên thread không phải native TID**.

Lưu file **`CpuHotLoopDemo.java`** với toàn bộ mã sau:

```java
public final class CpuHotLoopDemo {
    private static volatile boolean running = true;
    private static volatile long checksum;

    private static void busyLoop() {
        long value = 1L;
        while (running) {
            value = value * 2862933555777941757L + 3037000493L;
            value ^= value >>> 21;
        }
        checksum = value;
    }

    private static void idleLoop() {
        while (running) {
            try {
                Thread.sleep(50);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        String mode = args.length == 0 ? "busy" : args[0];
        int durationSeconds = args.length < 2
                ? 90
                : Integer.parseInt(args[1]);

        if (args.length > 2
                || (!mode.equals("busy") && !mode.equals("idle"))
                || durationSeconds < 15
                || durationSeconds > 300) {
            throw new IllegalArgumentException(
                    "Usage: CpuHotLoopDemo [busy|idle] [15..300]");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("mode=" + mode
                + " durationSeconds=" + durationSeconds);

        Runnable task = mode.equals("busy")
                ? CpuHotLoopDemo::busyLoop
                : CpuHotLoopDemo::idleLoop;
        Thread worker = new Thread(task, "cpu-hot-loop");
        worker.start();

        Thread.sleep(durationSeconds * 1000L);
        running = false;
        worker.join();

        System.out.println("finished mode=" + mode);
    }
}
```

### 5.1. Vì sao mã này phù hợp để quan sát?

- `running` là `volatile`: worker kiểm tra thay đổi của main thread; khác với một biến local chỉ được đọc trước vòng lặp. Khi main đặt `false` sau thời gian đã chọn, worker có điều kiện thoát.
- `checksum` là `volatile`: giá trị tính cuối cùng được ghi ra một trường có hiệu ứng quan sát được, giảm khả năng compiler xem toàn bộ phép tính là không cần thiết. Demo vẫn phụ thuộc JIT/OS scheduling; không hứa số vòng tính bằng một hằng.
- Chế độ `busy` không ngủ/đợi trong hot loop. Trong môi trường đủ CPU, một platform thread sẽ tiêu thụ đáng kể thời gian của **một logical processor**.
- Chế độ `idle` gọi `Thread.sleep(50)` trong vòng: worker tồn tại nhưng chủ yếu ở `TIMED_WAITING` và ít CPU. Đây là **negative control** để phân biệt “thread có tồn tại” với “thread tốn CPU”.
- Giới hạn `15..300` giây và `join()` giúp kết thúc có kiểm soát. Nếu debugger/scheduler tạm dừng tiến trình, wall time có thể khác thời lượng danh nghĩa.
- Một JVM mới là một **lần chạy riêng**; không đổi `mode` giữa chừng trong cùng JVM. Biến `running` chỉ reset khi tạo process mới.

Mã không có networking, disk I/O hay tạo object trong hot loop, giúp hạn chế nhiễu từ GC. Tuy nhiên **không có benchmark nào vô nhiễu**: JIT compilation, class loading, OS scheduler, CPU frequency và CPU quota vẫn có thể tạo khác biệt.

### 5.2. Biên dịch và chạy

Trong terminal A:

```bash
javac -g CpuHotLoopDemo.java
java CpuHotLoopDemo busy 90
```

Dòng mở đầu có dạng:

```text
PID=<PID thực tế>
mode=busy durationSeconds=90
```

Khi kết thúc bình thường, chương trình in **chính xác**:

```text
finished mode=busy
```

`<PID thực tế>` chỉ là chỗ minh họa, **không** phải stdout literal. Lưu PID được in ra và dùng nó trong các lệnh tiếp theo. Chương trình tự chạy khoảng 90 giây nếu không bị debugger tạm dừng hoặc môi trường lỗi; có thể đổi thành 120–180 giây trong phạm vi cho phép để đủ thời gian thao tác.

Trong một **lần chạy khác**, dùng negative control:

```bash
java CpuHotLoopDemo idle 90
```

Dòng `mode=idle durationSeconds=90` và `finished mode=idle` là kết quả logic tương ứng. Với mỗi run phải lấy **PID mới**; tuyệt đối không tái sử dụng PID cũ từ lần `busy`.

## 6. Bước 1 — xác nhận chính xác JVM và mức CPU

Trong terminal B, khi demo đang chạy, thay `12345` bằng PID thực tế:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
```

`jcmd -l` hiển thị các JVM nhìn thấy được từ môi trường công cụ, nhưng có thể bỏ qua tiến trình trong container/namespace khác. `VM.command_line` giúp đối chiếu main class/arguments, nhưng **có thể lộ secrets** trong ứng dụng thực: bảo vệ log và không chia sẻ bừa.

Ghi nhận tối thiểu:

| Trường | Ví dụ cách ghi | Lý do |
| --- | --- | --- |
| Thời điểm | UTC ISO 8601 + timezone của máy quản trị | Ghép OS CPU, thread dumps và JFR |
| PID, process start time/uptime | `12345`, uptime thực tế từ `jcmd` | Tránh lẫn JVM sau restart |
| JDK vendor/build | Output `VM.version` | JFR, thread dump và naming có thể khác |
| Run/workload | `busy` hay `idle`, duration, workload đang gửi | So sánh đúng điều kiện |
| CPU quota/cores | Số logical CPUs khả dụng, cgroup limit | Hiểu mẫu số %CPU |
| Công cụ/cửa sổ đo | `top -H`, `ps -L`, T0/T1/T2 | Chứng cứ là một khoảng, không phải ảnh chụp ngẫu nhiên |

Một tiến trình có nhiều thread, do đó CPU của process là **tổng** hoạt động thread dưới cách tính của công cụ. Trong demo có một worker nóng, còn trong hệ thống thật có GC, compiler, network, application pool và native threads; phải tìm đúng thread chứ không lấy total CPU làm bằng chứng cho một method.

## 7. Bước 2 — tìm native thread đang tiêu thụ CPU trên Linux

Trong terminal B:

```bash
top -H -p 12345
```

`-H` hiển thị threads; `-p` giới hạn theo PID process (cách hiển thị và %CPU có thể khác theo bản `top`). Quan sát **nhiều lần cập nhật**, không chỉ một lần chụp sau khi CPU vừa tăng.

Một snapshot khác:

```bash
ps -L -p 12345 -o pid,tid,pcpu,stat,comm
```

- `PID`: process Java.
- `TID`/`LWP`: **native thread ID** trong Linux namespace nhìn thấy từ công cụ, khác với Java `Thread.getId()`.
- `%CPU`/`PCPU`: tỷ lệ được công cụ ước tính theo khoảng/thời gian phù hợp. Với `ps`, con số thường mang tính **trung bình kể từ khi task chạy**, không đồng nghĩa CPU tức thời của 1 giây gần nhất.
- `STAT`: trạng thái scheduling của OS, không phải Java `Thread.State`.
- `COMMAND/COMM`: tên OS thread có thể bị cắt ngắn hoặc khác tên Java thread; không dùng tên một mình để ghép tuyệt đối.

Tùy máy, có thể lấy mẫu theo khoảng bằng `pidstat` (cần package `sysstat`):

```bash
pidstat -t -p 12345 1 5
```

Lệnh này hỏi CPU usage của các task/thread liên quan PID trên **5 khoảng một giây**. Nếu công cụ không có sẵn, dùng `top -H` và các ảnh/chỉ số hệ thống khác thay thế; không cài phần mềm tùy tiện trên production.

### 7.1. Điều mong đợi ở hai chế độ

- **`busy`:** TID tương ứng `cpu-hot-loop` thường chiếm phần lớn thời gian của một logical core; không cam kết đúng 100% vì CPU quota, nhiệt độ, frequency scaling, scheduling/JIT và các tiến trình khác.
- **`idle`:** worker chủ yếu ngủ và dùng ít CPU; thread vẫn có thể xuất hiện trong thread dump, thường là `TIMED_WAITING`. Nhiều thread khác của JVM vẫn tiêu thụ một chút CPU.
- Nếu cả hai đều có CPU cao, cần xem có tải bên ngoài, công cụ đo sai đối tượng, JIT/GC/thread khác hoặc giới hạn môi trường. Không ép kết quả về “đúng ý” của demo.

**Chỉ số cần giữ lại:** TID nào có `%CPU` cao qua nhiều interval, timestamp, cùng PID và thread lifetime. Đây là điểm bắt đầu để ghép với stack, **không phải kết luận cuối**.

## 8. Bước 3 — ghép TID hệ điều hành với `nid` trong thread dump

`jcmd <PID> Thread.print` in stack Java và thông tin thread ở JVM. Trên HotSpot Linux, thread header thường có `nid=0x...`, tức native thread ID ở dạng **hexadecimal**. Từ OS, TID thường là **decimal**. Phải đổi cơ số trước khi so.

Ví dụ giả định:

```text
PID process:      12345
TID từ top -H:    12416 (decimal)
Đổi sang hex:     0x3080
Tìm trong dump:   nid=0x3080
```

Đổi bằng shell (Linux/bash):

```bash
printf '0x%x\n' 12416
```

Kết quả **chính xác** của phép đổi:

```text
0x3080
```

Trong ví dụ thật, thay `12416` bằng TID nóng đã quan sát, không đoán TID từ `PID+1`. Sau đó:

```bash
jcmd 12345 Thread.print -l > threads-T0.txt
```

Tìm `nid=0x3080` hoặc tên `cpu-hot-loop` trong file. Một header **minh họa cấu trúc**, không phải output thực tế đã đo:

```text
"cpu-hot-loop" #XX prio=5 os_prio=0 cpu=...ms elapsed=...s
   tid=0x... nid=0x3080 runnable
   java.lang.Thread.State: RUNNABLE
        at CpuHotLoopDemo.busyLoop(CpuHotLoopDemo.java:<line>)
        at java.lang.Thread.run(Thread.java:<line>)
```

Những trường `cpu=...` và `elapsed=...` tùy VM/build/định dạng; **không tự bịa số ms**. Nếu có CPU time trong header, so sánh **chênh lệch giữa các snapshot của cùng thread**; không dùng một số tích lũy để suy nó vừa chiếm bao nhiêu CPU trong một giây.

**Quan trọng:** Trong HotSpot, định danh `nid` gắn với **native platform thread**. Với **virtual threads** ở Java 21, virtual thread không có OS TID riêng cố định vì nó có thể chạy trên carrier platform thread; kỹ thuật ghép TID↔nid chủ yếu áp dụng cho **platform threads** như demo này. Nếu thread name bị cắt ở OS, `nid` đáng tin hơn so khớp tên.

### Khi không tìm thấy TID trong dump

Có thể do:

- Thread kết thúc giữa lần đo OS và lúc `jcmd` lấy stack.
- PID/TID của container namespace không tương ứng với góc nhìn OS của công cụ đang chạy.
- `top` và `jcmd` đang xem **hai JVM khác nhau** sau restart.
- Thread native không ánh xạ thành Java thread có stack hiển thị như mong muốn (ví dụ GC/native worker) hoặc output khác JVM/version.
- Một số thread được đặt tên rất giống nhau; nên ghép bằng native identity và timestamp, không chỉ tên.

Không sửa kết luận bằng cách chọn một thread có tên “gần giống” mà bỏ qua sự không khớp của `nid`.

## 9. Bước 4 — lấy nhiều thread dumps để tránh chẩn đoán bằng một ảnh chụp

Một thread dump là snapshot của **một thời điểm**. Thread vừa thực thi `busyLoop` khi dump không chứng minh nó dành phần lớn 60 giây ở đó. Muốn thấy tính ổn định, lấy ba snapshot theo khoảng, trong khi OS vẫn ghi nhận TID nóng.

```bash
jcmd 12345 Thread.print -l > threads-T0.txt
sleep 2
jcmd 12345 Thread.print -l > threads-T1.txt
sleep 2
jcmd 12345 Thread.print -l > threads-T2.txt
```

Tùy số lượng thread, `Thread.print` có tác động **medium** theo tài liệu `jcmd`; thời gian dump có thể lớn. Không thu hàng chục dumps mỗi 100 ms trên service tải cao chỉ để cố thấy stack. Mốc T0/T1/T2 là **giả định trình tự**, phải ghi timestamp thực tế trước/sau mỗi lệnh khi báo cáo incident.

Quan sát các thuộc tính sau trên **cùng `nid`**:

| Quan sát | Phù hợp giả thuyết vòng lặp CPU? | Giới hạn |
| --- | --- | --- |
| `nid` giống nhau ở 3 dumps, OS cũng báo TID đó nóng | **Có**, hai nguồn độc lập quy về cùng native thread | Chưa loại trừ code path khác chạy giữa snapshots |
| Stack liên tục ở `CpuHotLoopDemo.busyLoop` | **Có**, method thường xuyên có mặt lúc quan sát | Snapshot không chứng minh toàn bộ thời gian CPU nằm ở một dòng |
| `java.lang.Thread.State: RUNNABLE` | Phù hợp, nhưng **không đủ** | Runnable có thể đang chờ được OS schedule |
| CPU time tích lũy của đúng thread tăng mạnh giữa hai dumps | Bằng chứng mạnh hơn cho thread dùng CPU | Chênh lệch cần đi kèm elapsed time/counter semantics |
| `idleLoop` đứng ở `Thread.sleep` / `TIMED_WAITING` | Đối chứng phù hợp với worker ngủ | Có thể thức dậy ngắn giữa hai lần dump |
| Stack phân tán giữa nhiều method hoặc `nid` thay đổi | Chưa kết luận một tight loop ổn định | Có thể là worker xử lý request khác nhau hoặc TID reuse |
| VM/GC/compiler thread nóng nhưng business stack không lặp | Cần chuyển giả thuyết sang runtime work | Không gán nhầm GC/JIT CPU cho method ứng dụng |

### Đọc stack từ dưới lên và trên xuống

Một ví dụ stack:

```text
"cpu-hot-loop" ... nid=0x3080 runnable
  java.lang.Thread.State: RUNNABLE
      at CpuHotLoopDemo.busyLoop(CpuHotLoopDemo.java:8)
      at CpuHotLoopDemo$$Lambda$...run(Unknown Source)
      at java.lang.Thread.run(Thread.java:...)
```

Đây là **stack minh họa**, số dòng/lambda frame không phải cam kết. Frame đầu gần vị trí đang thực thi; các frame phía dưới cung cấp **đường gọi**. Hãy xác định:

1. **Top frame:** method nào đang hoạt động khi snapshot thu?
2. **Caller chain:** request/worker hay task nào dẫn tới đó?
3. **Thread name, nid, state:** có đúng TID nóng từ OS?
4. **Các snapshot khác:** có lặp trên cùng đường gọi?
5. **Code/source đúng build:** line number có đúng file/class của JVM đích không?

JIT có thể inline method, tối ưu vòng lặp hoặc làm khác biểu diễn frame; không đòi số line giống nhau từng byte để gọi là cùng **đường mã**. Ngược lại, phương thức `Thread.run` ở đáy stack là bình thường, không phải root cause vì nó xuất hiện ở rất nhiều thread.

### Nếu muốn thêm thông tin lock

`-l` yêu cầu in các lock `java.util.concurrent` để xem thêm ngữ cảnh. Nó **không** có nghĩa `Thread.print -l` đo CPU. Trong bài CPU loop, lệnh này giúp loại trừ hoặc nhận diện tranh chấp khi triệu chứng thực tế thiên về blocking; không nên lạc đề sang chẩn đoán lock nếu OS đã chỉ ra một TID thật sự đang bận tính toán.

## 10. Bước 5 — bắt cửa sổ CPU với JFR

Thread dump có ít thời điểm; **JFR execution sampling** giúp quan sát nhiều stack trong khoảng thời gian thay vì một ảnh. Với HotSpot JDK 21, có thể bắt đầu recording trên JVM **đang chạy**:

```bash
jcmd 12345 JFR.start name=cpu_probe settings=profile duration=40s disk=true filename=/tmp/cpu-probe-%p-%t.jfr
jcmd 12345 JFR.check
```

- `settings=profile` là cấu hình phân tích chi tiết hơn `default`, thường bật những event cần cho profiling như `jdk.ExecutionSample`; số event/period phụ thuộc phiên bản JDK và cấu hình.
- `duration=40s` khiến recording tự dừng sau 40 giây thu, rồi ghi file theo `filename` đã chỉ định. Demo 90 giây cho phép bắt đầu ghi sớm và chờ đủ thời lượng.
- `disk=true` cho phép JFR lưu dữ liệu ra repository trong lúc ghi, giảm nguy cơ lịch sử bị giới hạn trong bộ đệm RAM nhỏ.
- `filename` là đích file **trong filesystem của target JVM**. `%p` và `%t` được thay bằng PID và timestamp. Không giả định file có tên văn bản nguyên dạng `%p`/`%t`.
- `JFR.check` cho thấy tên/trạng thái recording hiện có; nó không tạo tệp.
- JFR sampling có overhead và không bảo đảm mỗi method hoặc mỗi iteration có một event. Dùng recording **cùng setting** nếu so `busy` và `idle`.

Sau khi quá thời gian ghi và tệp tồn tại thật, chạy:

```bash
jfr summary /tmp/cpu-probe-12345-EXAMPLE.jfr
jfr print --events jdk.ExecutionSample --stack-depth 16 /tmp/cpu-probe-12345-EXAMPLE.jfr
jfr print --events jdk.CPULoad /tmp/cpu-probe-12345-EXAMPLE.jfr
```

**Tên file trên chỉ để minh họa vị trí.** Thay bằng tên thật do `jcmd` trả về. `jfr summary` cho biết thời gian ghi và số event theo loại; `jfr print` lọc event để đọc chi tiết. Nếu có JDK Mission Control (JMC), mở file và dùng CPU/method profiling hoặc flame graph theo **thread và time window**.

Nếu recording đang chạy mà muốn chốt ngay một snapshot, dùng:

```bash
jcmd 12345 JFR.dump name=cpu_probe filename=/tmp/cpu-incident-%p-%t.jfr
```

`JFR.dump` xuất dữ liệu **đã giữ tới lúc đó** mà không dừng recording; ngược lại `JFR.stop name=cpu_probe filename=...` sẽ kết thúc recording nếu bạn chủ động stop. Trong demo hữu hạn, hãy **chọn một cách**: chờ `duration` tự stop và xuất file, hoặc chủ động stop/dump trước khi JVM thoát; không gọi `JFR.dump` vào PID đã chết.

### Đọc execution sample đúng ý nghĩa

`jdk.ExecutionSample` là **mẫu quan sát stack**, không phải bộ đếm số lần gọi. Ví dụ bạn thấy 150 sample có `CpuHotLoopDemo.busyLoop` trong một recording. Kết luận đúng là:

> “Trong khoảng ghi và bộ lọc hiện tại, sampler đã bắt gặp đường thực thi `busyLoop` nhiều lần; kết quả phù hợp với OS CPU và thread dumps cho thấy thread này bận chạy.”

Không được viết:

> “`busyLoop` được gọi 150 lần”, “nó chạy chính xác 150 ms” hoặc “150 sample chứng minh 150 iteration”.

Một lần gọi `busyLoop` có thể kéo dài **hàng chục giây**; sampler có thể quan sát nó nhiều lần. Khi đổi sampling period hoặc bật/tắt event, count thay đổi dù workload không đổi.

**Mẫu số cần ghi:** toàn bộ valid execution samples trong time window/thread filter, cấu hình JFR, duration và số thread. Tỷ lệ 60% samples là **tỷ lệ trong tập được lấy mẫu**, không tự bằng 60% CPU của toàn process hay 60% request latency.

### `jdk.CPULoad` và GC/JIT events có vai trò gì?

`jdk.CPULoad` là thống kê định kỳ về CPU, có thể giúp nối mốc thời gian CPU với JFR. Nó không thay thế OS per-thread TID khi muốn chỉ rõ thread. Một số bản JFR còn có `jdk.ThreadCPULoad` theo setting của recording; phải kiểm tra `jfr summary` và event availability chứ không tự bảo đảm nó có mặt.

Nếu CPU tăng bất thường nhưng không thấy `busyLoop` trong execution samples, hãy kiểm tra:

- Profile có bật `jdk.ExecutionSample` không? `JFR.check verbose=true` khi recording còn chạy và/hoặc lưu file `.jfc`.
- Recording bắt đầu sau khi hot loop kết thúc? Chỉ có 5 giây dữ liệu?
- Tên thread, time filter và stack depth có đúng? Có inlined frames hay compiler/native path?
- CPU đang do **GC, JIT compiler threads hoặc native code** tiêu thụ chứ không phải Java worker?
- OS CPU sampling và JFR không cùng JVM/instance sau restart?
- Sampler có đủ sample hợp lệ cho hiện tượng này? Sampling không bắt được mọi lần thực thi.

Không dùng việc vắng một event làm bằng chứng tuyệt đối “code này không chạy”.

## 11. Bước 6 — ghép ba lớp bằng chứng thành một timeline

Một ví dụ **số liệu giả định**, không phải kết quả đã chạy:

| Mốc | OS CPU | Thread dump | JFR | Cách hiểu |
| --- | --- | --- | --- | --- |
| T0 | Java process ~105% một core; TID 12416 ~95% | `nid=0x3080`, `RUNNABLE` tại `busyLoop` | Recording bắt đầu, sample còn ít | Khoanh TID nghi vấn, chưa kết luận |
| T0+2s | TID 12416 tiếp tục cao | Cùng `nid`/method `busyLoop` | Có thêm execution samples | Hai nguồn theo thời gian cùng chỉ vào thread |
| T0+4s | TID 12416 tiếp tục cao | Stack tương tự lần thứ ba | Nhiều mẫu cùng stack trong khoảng | Bằng chứng mạnh cho hot loop |
| Chạy `idle` mới | TID worker ít CPU | `Thread.sleep`, thường `TIMED_WAITING` | Ít execution samples của `idleLoop` | Negative control củng cố cơ chế |

Các giá trị `105%`, `95%`, TID và timestamp tương đối ở đây **đều là giả định để dạy cách đối chiếu**. Người học phải ghi số đo thực tế, có thể khác hẳn trên máy bị giới hạn 0,5 vCPU hoặc khi compiler đang hoạt động.

### Ghép mốc thời gian khi các công cụ có đồng hồ khác nhau

- Ghi UTC/offset cho mỗi lệnh; thread dump thường có timestamp, OS CPU là interval, JFR có start/end của recording.
- Ghi cả **khoảng quan sát**, ví dụ `10:00:00Z–10:00:40Z`, không chỉ “lúc 10h”.
- PID/TID là danh tính trong một khoảng process sống, không phải ID bền sau restart.
- Nếu JFR profile lấy ở phút sau khi hết đợt CPU spike, việc không thấy `busyLoop` không phủ định thread dump cũ.
- JFR event có threshold/period và sampling selection; hình ảnh đồng pha là **tương quan**, cần cơ chế và thử thay đổi để kết luận nguyên nhân.

### Tiêu chí “đủ mạnh” đối với demo

Có thể kết luận **bằng chứng hỗ trợ vòng lặp đốt CPU** khi:

1. Đúng JVM, cùng PID và thời gian chạy đã xác nhận.
2. OS chỉ ra **một TID cụ thể** dùng nhiều CPU qua nhiều interval.
3. TID đổi hex khớp **`nid` của platform thread `cpu-hot-loop`**.
4. Hai hoặc ba dumps cùng thread cho thấy stack ở `busyLoop` / cùng code path.
5. JFR có các execution samples phù hợp trong **cùng cửa sổ**.
6. Chạy `idle` trong JVM mới và workload tương đương làm CPU worker giảm rõ rệt, stack đổi sang đường `Thread.sleep`.

Không có một dấu hiệu riêng nào trong số trên đủ chứng minh nguyên nhân mọi CPU incident thực tế. Demo được chủ động thiết kế để nguyên nhân đã biết, giúp học cách **kiểm tra** chứ không “đoán mò theo kết quả mong muốn”.

## 12. Khi nào kết luận “busy loop” có thể sai?

### 12.1. Thread luôn `RUNNABLE` nhưng không chiếm CPU

Hệ điều hành có thể không cấp CPU đủ cho thread hoặc thread đang ở đường native, trong khi JVM vẫn mô tả `RUNNABLE`. CPU per-thread thực tế thấp hoặc biến động thì chưa gọi là **CPU hot loop**. Kiểm tra CPU time delta và CFS/cgroup throttling trước khi suy từ trạng thái Java.

### 12.2. Một stack lặp qua ba dumps nhưng OS CPU gần 0

Nếu thread `TIMED_WAITING` hoặc snapshot vô tình bắt đúng đoạn xử lý rất ngắn, stack có thể giống nhau. Đặc biệt nhiều thread pool chờ ở cùng một frame `ThreadPoolExecutor.getTask` hoặc `LockSupport.park` là **bình thường**. Đừng nhầm “stack không đổi” với “đang tiêu thụ CPU”.

### 12.3. CPU cao ở `GC Thread` hoặc compiler thread

Nếu OS chỉ ra TID nóng có tên kiểu GC/Compiler thay vì application worker, chuyển câu hỏi sang `GC/compilation`. Xem GC logs/JFR `jdk.GarbageCollection`, `jdk.CPULoad`, `jdk.Compilation`, `jcmd PID Compiler.queue` và các memory metrics liên quan. Không gán GC CPU cho một method Java chỉ vì application stack cũng xuất hiện trong cùng phút.

### 12.4. Thực ra đó là throughput hợp lệ

Một batch xử lý ảnh lớn có thể dùng 100% CPU của core một cách hợp lệ, hoàn thành task đúng hạn và đạt throughput tốt. “CPU cao” chỉ là **triệu chứng tài nguyên**. Cần so expected load, số task đã hoàn thành, SLA/tail latency và độ bão hòa để quyết định có lỗi hay chỉ cần capacity planning.

### 12.5. Vòng lặp bận chờ do race/visibility

Nếu code dùng biến điều kiện chia sẻ sai hoặc polling không backoff, nó có thể spin liên tục. Cần kiểm tra memory visibility (`volatile`, atomic, lock) **và** thiết kế chờ. Tuy nhiên việc sửa concurrency code không chỉ là thêm `Thread.sleep` ngẫu nhiên: nên cân nhắc blocking queue, condition, semaphore, `LockSupport.park`, retry/backoff phù hợp. Thêm sleep có thể đổi semantics/latency và không tự khắc phục data race.

### 12.6. OS/container cho thấy khác nhau

Trong container, `top` từ host và `jcmd` chạy trong container có thể thấy PID/TID khác do **PID namespace**. CPU throttling hoặc quota cũng làm CPU% có cách diễn giải khác. Phải chú giải góc nhìn của từng công cụ, cùng container ID và cgroup metadata; không ghép hai số ID vô tình trùng nhau.

## 13. Ví dụ phân tích một incident giả định

Một service sau deploy có CPU process tăng và p99 latency cao. Dữ kiện thu được (đều **minh họa**, không phải số liệu thực):

```text
Run/instance: svc-a / PID 4721 / start 11:20:00Z
Window: 11:25:10Z..11:26:10Z
OS: process ~170% CPU (top convention)
TID 4740: ~95% CPU trên một logical core
TID 4752: ~55% CPU
Thread dump T0/T1/T2:
  nid=0x1284 (TID 4740): app.Worker.scanQueue -> app.Worker.spin
  nid=0x1290 (TID 4752): JIT/GC/native activity cần phân loại thêm
JFR: ExecutionSample lặp ở Worker.spin, có GC/compilation events.
Control: thay queue polling bằng blocking take() trên staging thì
         CPU giảm dưới tải tương đương trong nhiều run.
```

**Cách đọc:**

- `4721` là PID giả định, `4740` / `4752` là TID giả định và hai `nid` minh họa kết quả chuyển cơ số. Không sao chép ví dụ này làm bằng chứng thực.
- Hai TID cùng tiêu thụ CPU nên tổng process có thể vượt 100% theo quy ước `top`; đừng kết luận một thread chiếm 170%.
- App hot stack và JFR cho thấy cơ chế **có khả năng** tốn CPU; cần đo xem `scanQueue` thực hiện công việc hợp lệ hay spin vô ích.
- Phép thử trên staging giảm polling và giảm CPU dưới điều kiện so sánh là bằng chứng nhân quả mạnh hơn, nhưng vẫn phải kiểm tra throughput, latency và không bỏ sót message.
- TID thứ hai cần được điều tra riêng; không đưa tổng CPU về một nguyên nhân trước khi giải thích phần còn lại.

### Vì sao thay đổi CPU không đủ để xác nhận fix?

Nếu chuyển sang blocking queue làm CPU giảm từ 170% còn 80% nhưng throughput cũng rơi 80% và request backlog tăng, có thể bạn chỉ làm chương trình **ít làm việc hơn**, chưa sửa đúng. Sau fix phải so **CPU per completed task**, throughput, p95/p99, error rate và tài nguyên dưới cùng workload. “CPU thấp nhất” không phải đích mặc định của tối ưu hiệu năng.

## 14. Mẫu nhật ký thu bằng chứng cho một lượt chẩn đoán

Ghi thông tin vào một báo cáo ngắn (dữ liệu dưới đây là **mẫu điền**, không phải kết quả đã đo):

```text
Incident ID:
UTC window:
Host / container / namespace:
JDK vendor + exact version:
JVM PID + start time + uptime:
OS CPU convention and quota:
Workload / request rate / concurrency:

T0:
  OS command + timestamp:
  Hot TID (decimal):
  Converted nid (hex):
  Thread.print path:
  Thread name, state, top frames:
T1:
  ...
T2:
  ...

JFR:
  Recording name:
  .jfc/settings and duration:
  File path + actual file name:
  jfr summary (event types/counts/time range):
  ExecutionSample stacks and relevant thread:
  CPU/GC/JIT cross-check:

Hypotheses:
  Supported by:
  Contradicted by:
  Missing evidence:
Negative control and repeated measurements:
Impact and recommended next step:
```

Phải điền **kết quả thật**, kể cả các lần không thấy sample. Nếu có thông tin nhạy cảm trong stack, method names, JVM command line hoặc file JFR, đặt quyền truy cập/retention phù hợp; đừng dán raw dump vào ticket công khai. Bản báo cáo nên ghi rõ người thu và cách thu từng artefact để người khác có thể lặp lại.

### Gợi ý tiêu chí định lượng theo khoảng

- `process CPU%` và `thread CPU%` theo cùng quy ước công cụ.
- `thread CPU time delta / wall time delta` trong cùng khoảng, nếu công cụ cung cấp.
- Số lần TID đứng top CPU trên tổng số interval hợp lệ, ví dụ 5/5.
- Số snapshots có cùng top stack và đúng `nid`, ví dụ 3/3.
- JFR execution sample count theo đúng thread/time filter, cùng version/setting.
- Throughput và latency ở từng cửa sổ trước–trong–sau incident.

Nếu không có dữ liệu CPU per-thread mà chỉ có `Thread.print`, mức kết luận phải **giảm** xuống “thread đang chạy tại vị trí X khi chụp”, không được khẳng định X tiêu thụ 90% process CPU.

## 15. Checklist thực hành từ đầu tới cuối

1. **Run lab:** `javac -g CpuHotLoopDemo.java`; chạy `busy 90` và ghi PID.
2. **Xác nhận danh tính:** `jcmd -l`, `VM.version`, `VM.uptime` và args/mode.
3. **CPU OS:** `top -H -p PID` / `ps -L`; xác định TID nóng qua nhiều interval.
4. **Đổi hex:** `printf '0x%x\n' TID`; lưu phép đổi và tên namespace.
5. **Thread dumps:** lấy T0/T1/T2 cách nhau vài giây; tìm `nid`, tên `cpu-hot-loop`, `RUNNABLE` và top frames.
6. **JFR:** bắt đầu `settings=profile` 40 giây, xác minh `JFR.check`, đợi dump file rồi `jfr summary`/`jfr print`, xem `jdk.ExecutionSample`.
7. **Đối chiếu:** cùng PID, cùng window, cùng thread, bằng chứng OS + stack + JFR, ghi cả điểm trái với giả thuyết.
8. **Đối chứng:** chạy `idle 90` trong **JVM mới**; lặp quan sát, so CPU/stack/JFR dưới cùng cài đặt.
9. **Kết luận:** mô tả chính xác trạng thái đã quan sát, cơ chế có khả năng xảy ra, giới hạn sampling và dữ liệu còn thiếu.
10. **Thu dọn:** để demo hết hạn bình thường; xác nhận target JVM đã kết thúc; không để recording vô hạn hoặc file chứa dữ liệu nhạy cảm không có retention.

### Ba mức độ diễn đạt nên dùng

- **Quan sát:** “OS ghi TID 12416 có CPU cao ở 5/5 khoảng; `nid=0x3080` ở T0/T1/T2 có top frame `busyLoop`; JFR có nhiều execution samples trên đường này.”
- **Kết luận phù hợp:** “Bằng chứng liên nguồn **phù hợp mạnh** với một vòng lặp CPU-bound đang chạy kéo dài.”
- **Xác nhận tác động:** “Trong đối chứng cùng điều kiện, chuyển chế độ từ busy sang idle làm CPU TID giảm như dự đoán; khi đưa ra production phải kiểm thử rằng fix giữ được chức năng/throughput.”

Ngược lại, câu “có `RUNNABLE` nên chắc chắn dead loop” hoặc “50 JFR samples = method chạy 50 lần” là **không hợp lệ**.

## 16. Các lỗi thường gặp

1. **Nhầm PID process với TID thread:** `jcmd` dùng PID; `top -H` hiển thị TID/LWP; cần lưu cả hai.
2. **So TID thập phân trực tiếp với `nid` hex:** phải đổi cơ số; không đoán theo tên thread.
3. **Chỉ đọc một thread dump:** snapshot có thể trúng thời điểm không đại diện.
4. **Xem `RUNNABLE` là CPU%:** runnable là state, không phải counter CPU.
5. **Coi `ps %CPU` là CPU tức thời một giây:** cách tính khác với `top`/`pidstat`.
6. **Không kiểm tra cgroup quota/namespace:** sai mẫu số CPU và ghép nhầm ID.
7. **Không kiểm tra thời gian ghi JFR:** có thể capture sau khi hot loop đã hết.
8. **Đếm JFR execution samples như số lần gọi:** lấy mẫu stack không đo call count.
9. **So `default` với `profile` rồi quy count tăng cho ứng dụng:** cấu hình sampling khác.
10. **Không kiểm tra event enabled/period:** file có thể không có dữ liệu phương thức cần tìm.
11. **Quên GC/JIT/native threads:** CPU process có thể được tiêu thụ ngoài business loop.
12. **Đọc stack mà không có source đúng build:** line numbers/hàm có thể không tương ứng.
13. **Dùng `jcmd 0` hoặc tên main class thay PID khi chưa kiểm soát phạm vi:** dễ gửi command tới nhiều JVM.
14. **Thu quá nhiều dumps/recording ở production:** chính công cụ có overhead và rủi ro pause.
15. **Dump heap để điều tra CPU theo phản xạ:** chi phí lớn và không trực tiếp trả lời thread nào đốt CPU.
16. **Xem thread name là native identity bền:** tên có thể trùng/cắt ngắn và TID được tái sử dụng.
17. **Kết luận một dòng loop bất biến là root cause:** cần đối chiếu workload và tác động tới business metrics.
18. **Thấy CPU giảm sau đổi code rồi quên throughput:** giảm CPU có thể là làm ít việc hơn.
19. **Không có negative control:** khó tách CPU do chính demo hay máy/GC/JIT.
20. **Để busy loop chạy không giới hạn trên máy chung:** gây ảnh hưởng tài nguyên; demo có duration hữu hạn.
21. **Quên xác nhận `jcmd` thực sự attach vào đúng process:** container/permission/JDK khác có thể chặn.
22. **Sao chép file JFR/dump chứa dữ liệu nhạy cảm:** cần quyền và chính sách lưu trữ.

## 17. Bài tập tự kiểm tra

**Câu 1 — cơ số.** `top -H` cho TID decimal `12416`. Bạn cần tìm gì trong thread dump HotSpot?

**Đáp án:** Đổi sang `0x3080`, tìm header có `nid=0x3080` **trong đúng PID, đúng thời điểm**. Tên thread chỉ hỗ trợ định danh.

**Câu 2 — trạng thái.** Có một `RUNNABLE` thread ở `Worker.run` trong một dump, nhưng `top -H` cho TID đó 0,1% CPU. Có đủ để gọi nó là CPU hot loop?

**Đáp án:** Không. Cần CPU time delta/interval phù hợp; một snapshot Runnable không xác nhận mức dùng CPU.

**Câu 3 — lấy mẫu.** JFR cho thấy `busyLoop` trong 300 execution samples. Nó có được gọi 300 lần không?

**Đáp án:** Không suy được. Trong demo, `busyLoop` được gọi **một lần** cho worker `busy` nhưng có thể bị sampler quan sát rất nhiều lần khi đang chạy.

**Câu 4 — CPU% theo số core.** Process dùng xấp xỉ 100% của một core trên máy 8 logical cores. Dashboard chuẩn hóa theo cả máy có thể báo gần bao nhiêu?

**Đáp án:** Khoảng 12,5% **theo một quy ước chuẩn hóa toàn máy** nếu không bị quota/throttling và các nhân tố khác, nhưng công cụ kiểu `top` có thể hiển thị gần 100%. Luôn xác định mẫu số.

**Câu 5 — đối chứng.** Chạy `busy` và `idle` trong hai JVM khác nhau. Cả hai có thread name `cpu-hot-loop`. Có nghĩa TID giống nhau?

**Đáp án:** Không. TID do OS cấp riêng; `nid` có thể khác hoàn toàn và có thể được tái sử dụng sau khi thread chết.

**Câu 6 — bằng chứng thiếu.** `Thread.print` liên tục chỉ vào `busyLoop` nhưng JFR file không có `jdk.ExecutionSample`. Có phủ định giả thuyết CPU hot loop?

**Đáp án:** Chưa. Kiểm tra enabled/period, recording window, dữ liệu còn giữ, sampler, thread/time filter, JDK/tool và OS CPU evidence.

**Câu 7 — triage production.** OS xác nhận GC thread sử dụng phần lớn CPU, còn ứng dụng có nhiều `WAITING` threads. Có cần sửa ngay một vòng `while` thấy trong source không?

**Đáp án:** Không. Điều tra GC/allocation/heap và workload trước, đồng thời tránh lấy stack của thread không nóng làm root cause.

**Bài thực hành cuối:** ghi hai lần chạy `busy 90` và `idle 90`; cho mỗi run lập bảng có PID, TID thập phân/hex, 3 thread dumps, thời gian recording JFR, số execution samples hợp lệ, CPU intervals và tiêu chí kết luận. Giải thích **tại sao** ba nguồn OS–`jcmd`–JFR cùng củng cố một giả thuyết mà không biến mỗi snapshot/sample thành bằng chứng nhân quả tuyệt đối.

## 18. Nguồn chính thức và đọc thêm

- [Oracle JDK 21 — `jcmd`: `Thread.print`, `JFR.start`, `JFR.dump`, `VM.version`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`, event filtering và stack depth](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — Diagnostic Tools và ví dụ `jcmd Thread.print -l`](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html).
- [Oracle Java 21 — `Thread.State`: RUNNABLE, WAITING và TIMED_WAITING](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html).
- [Oracle Java 21 — `ProcessHandle`: `pid()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html).
- [Oracle JDK 21 — Java Flight Recorder API (`jdk.jfr`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html).
- [Linux `proc_pid_task(5)` — per-thread IDs từ `/proc/<pid>/task`](https://man7.org/linux/man-pages/man5/proc_pid_task.5.html).

**Nguyên tắc ghi nhớ:** `top/ps/pidstat` trả lời **thread nào tiêu thụ CPU**; `jcmd Thread.print` trả lời **thread ấy ở đâu trong Java stack tại thời điểm chụp**; JFR trả lời **những đường thực thi nào được lấy mẫu trong một khoảng thời gian**. Kết luận thuyết phục cần **đúng PID/nid, lặp theo thời gian, workload phù hợp và phép thử đối chứng**, không phải một ảnh chụp đơn lẻ.
