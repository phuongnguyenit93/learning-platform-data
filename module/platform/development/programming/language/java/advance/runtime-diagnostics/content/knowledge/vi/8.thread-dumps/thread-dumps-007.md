# 8.7 Đối chiếu native thread id với số liệu CPU của hệ điều hành

Một dịch vụ Java có CPU cao, nhưng thread dump có hàng trăm luồng `RUNNABLE`, `WAITING` và `TIMED_WAITING`. Luồng nào thật sự đang tiêu thụ CPU? Chỉ nhìn `Thread.State` không trả lời được: thread có trạng thái Java `RUNNABLE` có thể đang ở native I/O wait, còn luồng đang tiêu thụ CPU có thể là mã ứng dụng, GC, JIT compiler hoặc JNI.

Cách điều tra hữu ích trên **HotSpot/OpenJDK 17 chạy Linux** là **lấy CPU theo từng OS thread → tìm native thread ID (`nid`) tương ứng trong thread dump → đọc stack frames của đúng luồng → xác minh bằng mẫu CPU và dump gần nhau theo thời gian**. Bài này giải thích chính xác phép ánh xạ đó và những giới hạn khi dùng `top -H`, `ps -L`, `pidstat -t`, `/proc/<pid>/task/<tid>`, `ThreadMXBean`, JFR và container metrics.

**Kết quả học tập:** sau bài này, bạn có thể chuyển `nid` hex sang Linux TID decimal; phân biệt Java ID, HotSpot `tid` và native `nid`; chọn phép đo CPU tức thời hay tích lũy phù hợp; tính %CPU từ hai mẫu có cùng đơn vị; đối chiếu nhiều snapshot có PID/JVM identity chính xác; và không nhầm CPU cao với luồng `RUNNABLE`, load average hoặc CPU throttling.

## 1. Mô hình điều tra: hai góc nhìn, một thread

Một thread Java được HotSpot ánh xạ tới một OS thread trên JDK 17 thông thường. Thread dump kể chuyện theo **call stack trong JVM**; các công cụ Linux kể chuyện theo **CPU time/OS scheduling**. Hai phía cần một khóa nối chung, thường là **native thread ID**, đồng thời cần đúng process và thời điểm.

```text
           Linux / OS                            JVM HotSpot
┌────────────────────────────┐        ┌───────────────────────────────┐
│ PID của Java process       │        │ JVM PID/start/container      │
│ LWP/TID decimal: 10815     │        │ thread header: nid=0x2a3f    │
│ %CPU qua khoảng quan sát    │        │ name="payment-worker-7"      │
│ TIME / utime+stime ticks    │        │ #42, tid=0x..., Java state   │
│ OS scheduling state         │        │ Java stack frames + locks    │
└──────────────┬─────────────┘        └───────────────┬───────────────┘
               └───── 10815 == 0x2a3f ───────────────┘
                              │
                              ▼
                   Thêm UTC timestamp,
             PID namespace và đời JVM cụ thể
                              │
                              ▼
       Giả thuyết có bằng chứng: Java/GC/JIT/native,
                 CPU-bound hay blocked/I/O
```

**Một ánh xạ thành công chưa phải kết luận gốc:** `nid` đưa bạn tới một thread entry, nhưng stack tại đúng một thời điểm có thể khác mã đã dùng CPU trong khoảng trước đó. Muốn phân biệt “hotspot lặp đi lặp lại” với “một lần tình cờ đang ở method X”, dùng nhiều dump, counters CPU và JFR/profiler phù hợp.

### 1.1. Sáu điều kiện trước khi ghép

1. **Cùng JVM process:** đừng ghép output `top` của PID A với dump PID B.
2. **Cùng đời JVM:** PID có thể được hệ điều hành tái sử dụng sau restart; ghi thêm JVM start/uptime và container identity.
3. **Cùng PID namespace:** Linux host PID/TID có thể khác số nhìn từ trong container.
4. **Khoảng thời gian đủ gần:** `top` đo một khoảng; dump là snapshot ở một mốc.
5. **Đúng định nghĩa CPU%:** một logical core hay tổng N cores? Trung bình từ process start hay gần đây?
6. **Đúng định danh:** `nid` native TID; **không** thay bằng Java ID, `tid` pointer hay object monitor ID.

## 2. Ba định danh dễ nhầm trong thread dump

Một header **mô phỏng theo HotSpot**:

```text
"payment-worker-7" #42 daemon prio=5 os_prio=0 cpu=512.40ms elapsed=30.02s
   tid=0x00007f1a84032000 nid=0x2a3f runnable
   [0x00007f1a001bd000]
   java.lang.Thread.State: RUNNABLE
        at com.example.pricing.PriceEngine.calculate(PriceEngine.java:118)
        at com.example.checkout.CheckoutService.total(CheckoutService.java:75)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

Dòng xuống và giá trị ở đây được dàn để dễ đọc; HotSpot thật có thể in header trên cùng dòng, thay thứ tự hoặc thiếu một số trường tùy build/JDK/options.

| Trường | Ví dụ | Ý nghĩa | Cách sử dụng |
| --- | --- | --- | --- |
| Thread name | `"payment-worker-7"` | Nhãn do app/framework/JVM đặt; không duy nhất | Nhận diện chức năng, đọc stack |
| `#42` | Java thread number trong format HotSpot minh họa | Liên quan Java thread identity, không phải OS TID | So với Java management khi format phù hợp |
| `tid=0x00007f...` | Địa chỉ cấu trúc nội bộ HotSpot `JavaThread` | **Không** phải Linux TID | Chẩn đoán VM theo format cụ thể, không dùng trong `top -H` |
| `nid=0x2a3f` | Native OS thread ID dạng hexadecimal | **Khóa nối sang Linux LWP/TID decimal** | Đổi thành `10815` |
| `cpu=512.40ms` | CPU time tích lũy được runtime in nếu có | **Không** là CPU% của một giây qua | So sự tăng giữa hai mẫu của cùng thread khi metric phù hợp |
| `elapsed=30.02s` | Thời gian sống của thread theo runtime | Không phải request duration | Gợi ý vòng đời thread, không đo CPU usage |
| `java.lang.Thread.State: RUNNABLE` | Java thread state | Không nhất thiết đang chạy trên CPU | Đọc kèm frame và OS counters |

Không có contract Java SE bắt mọi vendor dùng đúng text header hoặc tên trường này. Phần nối `nid` áp dụng cho **HotSpot dump có native ID**, không phải parser portable cho mọi JVM.

### 2.1. Java thread ID không phải Linux thread ID

Java 17:

```java
long javaId = Thread.currentThread().getId();
```

Đây là **snippet đặt trong method**, trả Java ID kiểu `long`. `ThreadMXBean.getThreadCpuTime(long id)` và `ThreadInfo.getThreadId()` dùng **Java thread ID**. Interface Java SE 17 **không cung cấp `getNativeThreadId()` chuẩn**. Nếu thấy `ThreadMXBean` báo Java ID `42`, không tự tìm Linux LWP 42.

Cũng không đổi HotSpot `tid=0x00007f...` sang decimal rồi đưa vào `top -H`: trường này là **con trỏ native nội bộ của JVM**, thường rất lớn và khác `nid`.

### 2.2. Native ID trong Linux là gì?

Một Linux process có thể có nhiều task/threads. Ở Linux, mỗi thread có **thread ID (TID)** do kernel cấp; công cụ `ps -L` thường gọi cột đó là `LWP` hoặc `SPID`. Trong nhóm threads của một process, thread-group ID (TGID) thường được người dùng gọi là **PID process**.

Trên HotSpot/Linux, `nid` trong dump thường in native TID **dưới dạng hexadecimal**, còn `top -H` và `ps -L` hiển thị **decimal**.

Ví dụ:

```text
nid = 0x2a3f (hex)
    = 2*4096 + 10*256 + 3*16 + 15
    = 10815 (decimal)
```

Linux shell `bash`:

```bash
printf '%d\n' 0x2a3f
```

Output chính xác:

```text
10815
```

Nếu cần đổi ngược để tìm từ Linux sang dump:

```bash
printf '0x%x\n' 10815
```

Output chính xác:

```text
0x2a3f
```

Với Bash, `printf` nhận số dạng `0x...`. Trên shell hoặc tool khác, cách parse số hex có thể khác; không mặc định Windows `cmd.exe` hiểu cùng cú pháp. Đối với số TID lớn hơn, không cắt bớt leading digits hay ép kiểu số có thể tràn.

### 2.3. PID namespace làm số thay đổi

Trong container, JVM có thể thấy PID `1`, còn host thấy cùng JVM là PID `18432`. Những thread TID cũng có thể khác theo namespace. Vì thế:

```text
container namespace: TGID=1,    TID=88
host namespace:      TGID=18432, TID=18510
```

Đây là **ví dụ giả định** về mapping, không phải thông số một hệ thống thật. Nếu dump lấy **bên trong container**, hãy đọc OS thread metrics **từ cùng PID namespace** hoặc xác định mapping một cách có căn cứ. Dùng `/proc/<pid>/status` cùng các trường `NSpid`/`NStgid` khi có hỗ trợ và đủ quyền để kiểm tra, hoặc dùng công cụ container runtime được phê duyệt. Đừng trộn số ở host và container chỉ vì cùng tên service.

## 3. Lấy OS CPU theo thread trên Linux

### 3.1. Bắt đầu bằng đúng PID

Trước lệnh đo:

- Xác định Java process thực, host/container ID, JVM start và build revision.
- Xác nhận PID nằm trong namespace của terminal đang chạy.
- Kiểm tra quyền OS để đọc process/thread information.
- Nếu dùng `jcmd`, JDK tool có thể cần cùng effective user/group với JVM và có thể không thấy JVM ở container khác.
- Ghi mốc UTC cho từng lần thu, vì OS %CPU và dump hiếm khi được lấy tại đúng một tích tắc.

Ví dụ bên dưới giả định PID JVM là `12345` trong cùng Linux PID namespace. **Thay bằng PID đã xác minh**, không dùng PID của process khác.

### 3.2. `top -H -p PID`: quan sát CPU theo khoảng cập nhật

```bash
top -H -p 12345
```

Với GNU/procps `top`, `-H` bật chế độ hiển thị **threads** thay vì gộp tất cả threads của process, và `-p` lọc theo PID. Trong giao diện interactive, có thể sắp xếp theo `%CPU` và xem cột PID/TID của dòng thread.

Để thu batch khi công cụ hỗ trợ:

```bash
top -b -H -p 12345 -d 1 -n 3
```

`-b` là batch, `-d 1` chu kỳ lấy mẫu 1 giây, `-n 3` số vòng cập nhật. **Vòng đầu** có thể tính theo thông tin/cửa sổ khác hoặc chưa đại diện khoảng gần nhất; khi phân tích spike, dùng các vòng tiếp theo với timestamp nếu có. Các command này không tự lưu file; nếu cần lưu, chọn đường dẫn truy cập hạn chế.

Trong `top`, **Irix mode** và **Solaris mode** ảnh hưởng cách chuẩn hóa `%CPU` trên máy nhiều CPU:

- Irix mode bật: `100%` tương ứng khoảng **một logical CPU core** bận đầy trong khoảng đo. **Một process nhiều thread** có thể đạt trên 100%.
- Solaris mode: `%CPU` được chia cho số CPU theo định nghĩa của công cụ, nên con số nhìn nhỏ hơn.

Cần ghi chế độ của `top` (phím `I` có thể chuyển đổi trong procps), phiên bản công cụ và số CPU denominator. Với **một OS thread** thông thường, mức tiêu thụ gần tối đa của **một core-equivalent** là khoảng 100% ở chế độ Irix (trừ sai số/độ trễ lấy mẫu). Không so trực tiếp một dòng `top` ở Solaris mode với dashboard đang định nghĩa 100% = một core.

### 3.3. `ps -L`: xem LWP và lifetime CPU

```bash
ps -L -p 12345 -o pid,lwp,stat,pcpu,time,comm
```

Các cột thường có:

| Cột | Ý nghĩa | Bẫy |
| --- | --- | --- |
| `PID` | Thread-group/process ID | Không phải LWP của từng dòng |
| `LWP` | OS thread ID decimal | Nối với `nid` HotSpot sau đổi hex |
| `STAT` | Trạng thái OS scheduler | Khác `java.lang.Thread.State` |
| `%CPU` / `PCPU` | Theo procps `ps`, tỷ lệ CPU time / thời gian sống của task (lifetime average) | **Không** là %CPU của 1 giây vừa qua |
| `TIME` | CPU time tích lũy | Không phải wall time hay UTC timestamp |
| `COMMAND` / `COMM` | Tên native task, có thể bị rút ngắn | Không luôn giống Java thread name |

Vì `ps %CPU` có thể là **trung bình từ khi thread tồn tại**, một thread từng bận trong 10 phút rồi idle 20 phút có thể hiện %CPU khác đáng kể so với `top` gần đây. Dùng `ps -L` để kiểm tra identity và lifetime data; dùng mẫu delta hoặc `top`/`pidstat` khi cần rate gần đây.

Một dòng mẫu **hư cấu**:

```text
PID     LWP   STAT  %CPU     TIME COMMAND
12345  10815  R     79.5 00:02:03 java
```

Chỉ từ `STAT=R` và `%CPU=79.5` chưa thể kết luận frame Java nào gây tải: cần tìm `nid=0x2a3f` trong dump gần thời điểm đo.

### 3.4. `pidstat -t -p PID`: CPU thread theo nhiều interval

Nếu Linux có **sysstat** (`pidstat` không phải một phần JDK):

```bash
pidstat -t -u -p 12345 1 5
```

Lệnh có thể báo từng TID, `%usr`, `%system`, `%CPU` trong các interval 1 giây (số lượt 5). Cách đặt nhãn/cột và normalization phụ thuộc phiên bản `pidstat`; đọc manual trên máy trước khi so với `top`. Chọn công cụ đã có sẵn, không cài phần mềm lên production chỉ để có bảng CPU đẹp hơn.

### 3.5. Bảng chọn công cụ

| Cần biết | Nguồn khởi đầu | Lý do |
| --- | --- | --- |
| TID nào gần đây dùng CPU nhất? | `top -H -p PID` hoặc `pidstat -t` | Theo khoảng đo gần đây |
| Một TID có tồn tại trong process? | `ps -L` hoặc `/proc/PID/task/TID` | Xác nhận mapping và namespace |
| CPU time tích lũy của TID? | `ps TIME` hoặc `/proc/PID/task/TID/stat` | Có counter để lấy delta |
| Stack Java của TID đó? | `jcmd PID Thread.print -l` và `nid` | Ánh xạ native ID → Java frames |
| Native/GC/JIT thread không có Java frames? | HotSpot internal threads, JFR/native profiler | Java stack có thể không tồn tại |
| Process CPU tổng và quota? | Process/cgroup OS metrics | Một thread không đại diện toàn JVM |
| Lỗi xảy ra vì CPU throttling? | `cpu.stat` và quota của đúng cgroup | CPU% theo thread không đủ chứng minh throttling |

## 4. Cách lấy thread dump để ghép với OS metrics

### 4.1. `jcmd Thread.print` trên đúng JVM

```bash
jcmd -l

# Kiểm tra phiên bản JVM thực, không chỉ Java từ shell.
jcmd 12345 VM.version

# Xem command có hỗ trợ và option nào.
jcmd 12345 help Thread.print

# Lấy Java thread stacks và thông tin locks (khi được phép).
jcmd 12345 Thread.print -l
```

Theo tài liệu Oracle JDK 17, `Thread.print` có impact **Medium** (phụ thuộc số threads); nó không phải đọc chỉ số không tốn tài nguyên. Với JVM có hàng nghìn thread hoặc đang chịu latency nghiêm trọng, cần hạn chế số lần, tránh lấy dump trên toàn cluster. `jcmd` yêu cầu quyền phù hợp và có thể không liệt kê/attach được qua ranh giới container.

Khi cần tiết kiệm tác động, đừng chụp hàng trăm dumps để “quét” CPU. Một đến vài snapshots gần thời điểm spike, kết hợp OS CPU samples/JFR, thường có ý nghĩa hơn.

### 4.2. Ví dụ nối một dòng `top` tới dump

Giả sử `top -H` in dòng:

```text
PID      %CPU    TIME+      COMMAND
10815    97.3    2:06.43    java
```

Trong **cùng JVM**, một mục dump minh họa:

```text
"pricing-hot-loop" #42 daemon prio=5 os_prio=0 cpu=126000.00ms elapsed=184.00s
   tid=0x00007f1a84032000 nid=0x2a3f runnable
   java.lang.Thread.State: RUNNABLE
        at com.example.pricing.PriceEngine.calculate(PriceEngine.java:118)
        at com.example.pricing.PriceEngine.score(PriceEngine.java:92)
        at com.example.web.CheckoutController.handle(CheckoutController.java:47)
        at java.base/java.lang.Thread.run(Thread.java:833)
```

**Điều quan sát được:** OS báo native TID `10815` dùng khoảng 97,3% một core trong cửa sổ `top` đã chọn; `10815 = 0x2a3f`; dump gắn `nid=0x2a3f` với một Java thread tên `pricing-hot-loop`, state RUNNABLE và stack tại `PriceEngine.calculate`.

**Chưa được kết luận:** chính `PriceEngine.calculate` nhất thiết đã tiêu hết 97,3% CPU trong **cả interval**; thread có thể di chuyển qua nhiều method giữa hai lần đo. Cần lặp sample/profiler/tracing hoặc tối thiểu xem CPU time delta và tính ổn định của stack trong các lần chụp gần nhau.

### 4.3. Tên, `#n`, `tid` và `nid` khác nhau

- Tên `pricing-hot-loop`: dùng để nhóm chức năng, có thể trùng.
- `#42`: ID/number Java thread in theo kiểu HotSpot, **khác OS TID**.
- `tid=0x00007f...`: HotSpot native structure pointer, **không đối chiếu với LWP**.
- `nid=0x2a3f`: **native TID**, cần đổi ra decimal khi so với Linux tools.
- Dòng `java.lang.Thread.State: RUNNABLE`: trạng thái Java VM, **không phải số CPU%**.
- `cpu=...ms`: CPU time của thread do VM in, **không phải phần trăm tại t0**.

Nhiều JVM internal threads (GC worker, JIT compiler, VM Thread) có thể xuất hiện ở phần riêng hoặc chỉ có thông tin native, không có Java `Thread` object/Java stack dễ ghép. Đừng tự gán một native GC thread cho ứng dụng chỉ vì nó không khớp với tên Java thông thường.

## 5. Hiểu đúng `%CPU`, CPU time và CPU cores

### 5.1. CPU time và wall time

**CPU time** là lượng thời gian thread thực sự chạy trên CPU (user mode và kernel mode theo định nghĩa counter). **Wall time** là thời gian trôi qua ngoài đời.

Một thread chạy liên tục trên một logical core trong 5 giây wall time có thể tích lũy khoảng **5 CPU-seconds**. Nếu nó bị block chờ network 4,5 giây và dùng CPU 0,5 giây, trong cùng 5 giây wall time CPU usage của thread xấp xỉ 10% **một core-equivalent**.

Một **process nhiều thread** có thể dùng tổng 20 CPU-seconds trong 5 giây wall time = **4 core-equivalents**, tức khoảng 400% theo kiểu 100%=một core. Điều này hoàn toàn có thể trên host/namespace có ít nhất bốn cores hiệu lực. Một **OS thread riêng lẻ** không đồng thời chạy trên nhiều CPU cores, nên trung bình gần 100% một core là mức tối đa thông thường (trừ sampling noise/counter errors).

### 5.2. Công thức chuẩn hóa bằng interval

Gọi:

- `cpuTime0Ns`, `cpuTime1Ns`: CPU time tích lũy của **cùng thread**, nanoseconds;
- `wall0Ns`, `wall1Ns`: hai mốc elapsed monotonic của máy/công cụ, nanoseconds.

```text
deltaCpuNs  = cpuTime1Ns - cpuTime0Ns
deltaWallNs = wall1Ns    - wall0Ns

coreEquivalents = deltaCpuNs / deltaWallNs
percentOneCore  = 100 * coreEquivalents

percentOfNProcessors = percentOneCore / N
```

Nếu `deltaCpuNs=450,000,000` và `deltaWallNs=1,500,000,000`:

```text
coreEquivalents    = 0.30
percentOneCore     = 30%
percentOf4Cpus     = 7.5%
```

**N cần được định nghĩa:** logical CPUs của host, cpuset CPUs của process, số processor JVM nhìn thấy hay quota cores của container? Những denominator khác nhau trả lời **câu hỏi khác nhau**. Không tự dùng `Runtime.availableProcessors()` để chia mọi OS metric và coi là một chuẩn duy nhất, nhất là khi container CPU quota fractional hoặc JDK update thay đổi container awareness.

### 5.3. Thời gian lấy mẫu không đồng thời

Với `top`, CPU% phản ánh **một khoảng cập nhật**; với thread dump, call stack phản ánh **thời điểm JVM thu snapshot**. Một thread có thể đã tiêu thụ nhiều CPU trong 2 giây, rồi chặn I/O ngay trước khi dump được lấy. Bạn sẽ thấy một `RUNNABLE`/native read hoặc `WAITING` dù CPU sample vừa cao.

Một quy trình tốt:

```text
t0: OS CPU counters + UTC / monotonic timestamp
t1: thread dump gần cùng khoảng
t2: OS CPU counters + UTC / monotonic timestamp
t3: thread dump tiếp nếu vẫn có triệu chứng và được phép
```

Đừng gọi hai công cụ “cùng lúc” nếu bạn chưa lưu timestamp thực. Nếu CPU burst chỉ 100 ms, một dump bất kỳ rất dễ bỏ lỡ; **JFR/profile sampling** phù hợp hơn cho attribution ngắn.

### 5.4. Lifetime average của `ps` và interval rate của `top`

| Tình huống | `ps -L %CPU` | `top -H %CPU` | Diễn giải |
| --- | --- | --- | --- |
| Thread từng nóng 10 phút, giờ idle | Có thể vẫn cao vì trung bình từ lúc bắt đầu | Có thể gần 0% trong interval gần đây | Không phải mâu thuẫn |
| Thread vừa bắt đầu hotspot | Lifetime avg còn phản ánh thời gian sống ngắn | Có thể gần 100% một core | Cần quan sát thêm |
| Process 4 threads chạy full CPU | Các dòng `ps -L` khác nhau | Mỗi TID gần 100% ở Irix mode, process gộp có thể ~400% | Không có “một thread 400%” |
| Host 32 CPUs, pod quota 1 CPU | % có thể được trình bày theo định nghĩa tool | Một thread full core có thể ~100% | Pod vẫn có thể bị throttling dù host bận ít |

Không cộng các %CPU từ các tool/period khác nhau để suy ra một tỷ lệ chính xác. Tổng các **CPU-time deltas** của cùng kỳ và các threads hiện diện phù hợp là cách so nhất quán hơn, vẫn phải tính thread lifecycle và missing samples.

## 6. Đo trực tiếp CPU thread từ `/proc` trên Linux

### 6.1. `/proc/PID/task/TID`

Linux procfs có đường dẫn:

```text
/proc/<process-tgid>/task/<native-tid>/
    stat
    status
    schedstat
    ...
```

Trong đó:

- `PID` là process/thread-group ID của JVM **trong namespace mà procfs thấy**.
- `TID` là ID của một OS thread thuộc nhóm đó.
- `/proc/PID/task/TID/stat` có các CPU time fields.
- `/proc/PID/task/TID/status` có tên thread, state và các metadata; trường `NSpid` có thể hỗ trợ đối chiếu PID namespaces.
- `schedstat` có thêm dữ liệu scheduler trong những kernel/configuration hỗ trợ; không bảo đảm trường luôn có hoặc luôn mang đủ số liệu.

Ví dụ đọc một thread đã biết, **chỉ khi đúng PID/TID và đủ quyền**:

```bash
cat /proc/12345/task/10815/status
cat /proc/12345/task/10815/stat
getconf CLK_TCK
```

`getconf CLK_TCK` cho số clock ticks trong một giây mà `/proc` fields sử dụng (thường 100 trên Linux nhưng **phải đo**, không hard-code). Đường dẫn có thể biến mất giữa hai lần đọc khi thread kết thúc. Trong một container có procfs được mount khác, path/TID có thể không tương ứng với host.

### 6.2. `stat` field 14/15 là user/system CPU ticks

Theo Linux `proc_pid_stat(5)`:

- **Field 14 `utime`**: CPU time ở user mode, đo bằng **clock ticks**.
- **Field 15 `stime`**: CPU time ở kernel mode, đo bằng **clock ticks**.
- **Field 22 `starttime`**: thời gian task bắt đầu tính theo clock ticks kể từ boot (hữu ích nhận diện TID reuse).

Trong file của **từng task** `/proc/PID/task/TID/stat`, counters phản ánh task/thread đó. Tổng `utime+stime` cho CPU time tích lũy của thread theo quy tắc procfs. Để ra giây:

```text
cpuSeconds = (utimeTicks + stimeTicks) / CLK_TCK
```

Để tính %CPU theo **một core** từ hai mẫu:

```text
percentOneCore =
    100 * ((utime1 + stime1) - (utime0 + stime0))
        / (CLK_TCK * elapsedWallSeconds)
```

Không dùng `/proc/PID/stat` tổng process thay cho `/proc/PID/task/TID/stat` khi mục tiêu là **thread riêng lẻ**.

### 6.3. Cảnh báo parse `stat`

`/proc/PID/task/TID/stat` **không phải chuỗi các trường luôn split đơn giản theo whitespace**: field 2 `comm` nằm trong cặp ngoặc `(...)` và có thể chứa dấu cách hoặc ngoặc. Nếu dùng `awk '{print $14,$15}'` một cách vô điều kiện, tên thread chứa khoảng trắng có thể làm lệch index và dẫn tới CPU time sai.

Cách parse có cấu trúc là:

1. Tìm dấu `)` đóng **cuối cùng** của field `comm`.
2. Phần sau bắt đầu từ **field 3 `state`**.
3. Khi split phần sau, `utime` (field 14) là **index 11**, `stime` (field 15) là **index 12**, `starttime` (field 22) là **index 19** tính từ index 0.
4. Kiểm tra đủ fields, số hợp lệ và thread identity không thay đổi.

Một parser production nên được kiểm thử với tên thread có khoảng trắng, dấu `)`, thread kết thúc giữa mẫu và namespace khác; không tin vào regex đơn giản tạo từ một output đẹp.

### 6.4. `schedstat` có thể hỗ trợ phân biệt chạy và đợi scheduler

Khi kernel hỗ trợ, `/proc/PID/task/TID/schedstat` có thể cung cấp các counters cho thời gian chạy trên CPU, thời gian chờ được schedule và số lần chạy (định nghĩa phụ thuộc kernel). Chúng giúp hỏi “thread muốn chạy nhưng đợi CPU?” tốt hơn chỉ nhìn Java state.

Không biến `schedstat` thành nguồn chuẩn duy nhất trên mọi Linux distro; tính khả dụng, quyền và cấu hình kernel khác nhau. Nếu không có dữ liệu, ghi unavailable và dùng `top`/`pidstat`/cgroup CPU metrics/JFR phù hợp.

## 7. Java 17+ runnable: tính mapping và CPU% chính xác từ số liệu giả định

Để kiểm tra phép đổi hex và công thức mà không phụ thuộc máy, dùng một chương trình với số liệu cố định. Lưu file **`NativeThreadCpuMath.java`**:

```java
import java.util.Locale;

public class NativeThreadCpuMath {
    public static void main(String[] args) {
        String nidHex = "0x2a3f";
        long nativeTid = Long.parseLong(
                nidHex.substring(2), 16);

        long userTicks0 = 1_000L;
        long systemTicks0 = 400L;
        long userTicks1 = 1_030L;
        long systemTicks1 = 415L;

        long ticksPerSecond = 100L;
        double elapsedSeconds = 1.5;
        int logicalCpus = 4;

        long deltaTicks = (userTicks1 + systemTicks1)
                        - (userTicks0 + systemTicks0);
        double cpuSeconds = (double) deltaTicks / ticksPerSecond;
        double percentOneCore = 100.0 * cpuSeconds / elapsedSeconds;
        double percentOfFour = percentOneCore / logicalCpus;

        System.out.println("nid.hex=" + nidHex);
        System.out.println("nid.decimal=" + nativeTid);
        System.out.println("delta.ticks=" + deltaTicks);
        System.out.printf(Locale.ROOT, "cpu.seconds=%.2f%n",
                cpuSeconds);
        System.out.printf(Locale.ROOT, "one.core.percent=%.2f%%%n",
                percentOneCore);
        System.out.printf(Locale.ROOT, "four.cpus.percent=%.2f%%%n",
                percentOfFour);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac NativeThreadCpuMath.java
java NativeThreadCpuMath
```

**Stdout chính xác:**

```text
nid.hex=0x2a3f
nid.decimal=10815
delta.ticks=45
cpu.seconds=0.45
one.core.percent=30.00%
four.cpus.percent=7.50%
```

Giải thích: 30 user ticks + 15 system ticks = 45 ticks; ở 100 ticks/giây là 0,45 giây CPU trong 1,5 giây wall time. Đây là **30% một core**, không phải “CPU của cả host 30%”. Với bốn logical CPUs làm denominator, 30/4 = **7,5% tổng bốn cores**. Những giá trị này cố định cho bài toán, không đại diện tải hệ thống thật.

## 8. Java 17+ runnable trên Linux: đo `/proc` của đúng TID

Ví dụ sau là công cụ **đọc-only**, chạy trên Linux khi có quyền đọc `/proc`. Nó đọc CPU ticks của một native TID trong một JVM process tại hai thời điểm, kiểm tra `starttime` để hạn chế TID reuse, rồi in CPU% trên **một logical core**. Chương trình **không attach, không gửi signal, không chỉnh JVM**, nhưng vẫn cần tuân thủ quyền truy cập và sampling budget.

Lưu file **`LinuxNativeTidCpu.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class LinuxNativeTidCpu {
    record Sample(long userTicks, long systemTicks, long startTicks) {
        long totalTicks() {
            return userTicks + systemTicks;
        }
    }

    private static Sample sample(String processPid, String nativeTid)
            throws IOException {
        Path file = Path.of("/proc", processPid,
                "task", nativeTid, "stat");
        String stat = Files.readString(file);

        // comm là field 2 được bao trong (...), có thể có dấu cách.
        int endComm = stat.lastIndexOf(')');
        if (endComm < 0 || endComm + 1 >= stat.length()) {
            throw new IOException("Malformed /proc task stat");
        }

        // Phần sau ')' bắt đầu từ field 3: state.
        String[] fields = stat.substring(endComm + 1)
                .trim().split("\\s+");
        if (fields.length <= 19) {
            throw new IOException("Missing /proc task fields");
        }

        long utime = Long.parseLong(fields[11]);    // field 14
        long stime = Long.parseLong(fields[12]);    // field 15
        long start = Long.parseLong(fields[19]);    // field 22
        return new Sample(utime, stime, start);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                "Usage: java LinuxNativeTidCpu PID NID_HEX CLK_TCK INTERVAL_MS");
            return;
        }

        String processPid = args[0];
        String nidHex = args[1];
        if (!processPid.matches("[0-9]+")
                || !nidHex.matches("0[xX][0-9a-fA-F]+")) {
            throw new IllegalArgumentException("Bad PID or NID_HEX");
        }

        String nativeTid = Long.toUnsignedString(
                Long.parseUnsignedLong(nidHex.substring(2), 16));

        long ticksPerSecond = Long.parseLong(args[2]);
        long intervalMs = Long.parseLong(args[3]);
        if (ticksPerSecond <= 0 || intervalMs < 200) {
            throw new IllegalArgumentException(
                    "CLK_TCK must be positive; interval >= 200 ms");
        }

        long wallStart = System.nanoTime();
        Sample first = sample(processPid, nativeTid);
        Thread.sleep(intervalMs);
        Sample second = sample(processPid, nativeTid);
        long elapsedNs = System.nanoTime() - wallStart;

        if (first.startTicks != second.startTicks) {
            throw new IllegalStateException("TID was reused");
        }

        long cpuTicks = second.totalTicks() - first.totalTicks();
        if (cpuTicks < 0 || elapsedNs <= 0) {
            throw new IllegalStateException("Invalid CPU/wall delta");
        }

        double cpuSeconds = (double) cpuTicks / ticksPerSecond;
        double wallSeconds = elapsedNs / 1_000_000_000.0;
        double percentOneCore = 100.0 * cpuSeconds / wallSeconds;

        System.out.println("linux.tid=" + nativeTid);
        System.out.println("cpu.delta.ticks=" + cpuTicks);
        System.out.printf(Locale.ROOT, "one.core.percent=%.2f%%%n",
                percentOneCore);
    }
}
```

Trên Linux với JDK 17 và ví dụ JVM PID `12345`, `nid=0x2a3f`:

```bash
javac LinuxNativeTidCpu.java

# Tự lấy ticks/giây từ môi trường thực.
getconf CLK_TCK

# Thay PID/nid bằng cặp đã xác minh; đo trong khoảng 1000 ms.
java LinuxNativeTidCpu 12345 0x2a3f "$(getconf CLK_TCK)" 1000
```

**Output không cố định**: thread có thể kết thúc, counters và CPU% thay đổi theo tải, hoặc quyền `/proc` bị hạn chế. Một output giả định:

```text
linux.tid=10815
cpu.delta.ticks=73
one.core.percent=72.91%
```

`72.91%` chỉ là ví dụ: thời gian đo thực có thể hơn/ít hơn 1 giây, vì vậy không thể tính chính xác từ riêng `delta.ticks=73` mà không có `elapsedNs` của lần chạy đó.

Các lưu ý quan trọng:

- `Sample` là **record Java 17**, biên dịch được trong một source file.
- Parser dùng `lastIndexOf(')')` để không split sai field `comm` chứa khoảng trắng. Index `11/12/19` chỉ đúng vì phần sau ngoặc bắt đầu từ field 3.
- Chương trình đọc thread **trong namespace procfs hiện tại**; nếu PID/nid lấy từ namespace khác, path sẽ không tồn tại hoặc có thể trỏ nhầm task.
- `starttime` giảm rủi ro TID reuse, nhưng khi thu incident thực vẫn cần kiểm tra JVM PID/start, container identity và nguồn clock.
- CPU ticks có granularity nhất định, thời gian đọc `/proc` không hoàn toàn đồng thời với `System.nanoTime()`; sampling quá ngắn tăng sai số.
- Nếu process/thread kết thúc giữa hai mẫu, `Files.readString` có thể ném `IOException`: phải báo “thread disappeared”, không ép CPU về 0.
- Parser là ví dụ học tập; production collector cần xử lý định dạng/kernel, phiên bản cgroup, quyền và logging/an toàn theo chuẩn vận hành.
- Một native HotSpot GC/JIT thread vẫn có thể xuất hiện trong procfs và dùng CPU dù không có Java `ThreadInfo` tương ứng.

## 9. So sánh CPU của Linux thread với Java `ThreadMXBean`

### 9.1. ThreadMXBean sử dụng Java thread ID

Trong JVM Java 17, `java.lang.management.ThreadMXBean` có:

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory.getThreadMXBean();

boolean supported = mx.isThreadCpuTimeSupported();
boolean enabled = mx.isThreadCpuTimeEnabled();
long javaThreadId = Thread.currentThread().getId();

if (supported && enabled) {
    long cpuNs = mx.getThreadCpuTime(javaThreadId);
    // cpuNs >= 0: CPU time tích lũy, đơn vị nanoseconds.
}
```

Đây là snippet trong method, không phải chương trình độc lập. `getThreadCpuTime(id)` nhận **Java thread ID**, **không** nhận Linux LWP/native ID. Nó có thể trả `-1` khi không có thông tin, thread đã chết hoặc CPU time measurement bị tắt. Trên JVM không hỗ trợ, method có thể ném `UnsupportedOperationException`; trước khi dùng, kiểm tra capability. Đừng mặc định bật CPU time monitoring trên production nếu chưa đo tác động và có quyền thay đổi trạng thái.

### 9.2. Java CPU nanoseconds vs Linux CPU ticks

Hai nguồn có thể kể cùng một câu chuyện nhưng khác đơn vị:

| Nguồn | ID đầu vào | Đơn vị | Đặc điểm |
| --- | --- | --- | --- |
| `ThreadMXBean.getThreadCpuTime(javaId)` | Java thread ID | Nanoseconds | JVM management view; chỉ Java threads mà API quản lý |
| `/proc/PID/task/TID/stat` | Native TID | Clock ticks | Kernel view; gồm cả JVM native/internal threads |
| `ps -L TIME` | Linux LWP | CPU duration formatted | Lifetime accumulated; dùng để nhìn nhanh |
| `top -H %CPU` | Linux TID trong namespace tool | %CPU theo update window | Cần biết Irix/Solaris mode và interval |
| `pidstat -t %CPU` | Linux TID | Interval CPU% | Phụ thuộc tool configuration/version |
| HotSpot `Thread.print cpu=...` | Header thread | Thường milliseconds | JVM-specific; không mặc định có trên mọi format |

Không kỳ vọng hai counter khớp từng nanosecond: cách JVM và kernel lấy timestamp/CPU scheduling, sampling time, counter granularity và phần native runtime có thể khác. Chỉ so CPU **delta** trong interval gần giống, cùng đời thread; nếu thiếu ID mapping, không tự lấy Java ID làm Linux TID.

### 9.3. Ví dụ chương trình Java 17+ cho Java ID và CPU time availability

Lưu **`JavaThreadCpuProbe.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public class JavaThreadCpuProbe {
    public static void main(String[] args) {
        Thread self = Thread.currentThread();
        self.setName("cpu-probe-main");

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();

        System.out.println("threadName=" + self.getName());
        System.out.println("javaIdPositive=" + (self.getId() > 0));
        System.out.println("mxThreadIdMatches="
                + (mx.getThreadInfo(self.getId()).getThreadId()
                    == self.getId()));

        boolean supported = mx.isThreadCpuTimeSupported();
        System.out.println("cpuTimeSupported=" + supported);
        if (supported && mx.isThreadCpuTimeEnabled()) {
            long cpuNs = mx.getThreadCpuTime(self.getId());
            System.out.println("cpuTimeNonNegative=" + (cpuNs >= 0));
        } else {
            System.out.println("cpuTime=unavailable");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac JavaThreadCpuProbe.java
java JavaThreadCpuProbe
```

Ba dòng đầu trong stdout **có nội dung xác định**:

```text
threadName=cpu-probe-main
javaIdPositive=true
mxThreadIdMatches=true
```

Dòng cuối **phụ thuộc hỗ trợ CPU time** và cấu hình JVM, ví dụ:

```text
cpuTimeSupported=true
cpuTimeNonNegative=true
```

Nếu không hỗ trợ hoặc chưa bật, output có thể là `cpuTimeSupported=false` và `cpuTime=unavailable` hoặc `cpuTimeSupported=true` và `cpuTime=unavailable`. Chương trình không in native TID, bởi Java SE 17 `ThreadMXBean` không có API portable để lấy `nid`. Để nối với OS, đọc HotSpot dump/JFR/native tool phù hợp.

## 10. Nhiều thread native của JVM cũng dùng CPU

Một JVM không chỉ có application threads. Các thành phần có thể tiêu thụ CPU:

- GC workers và GC concurrent threads;
- JIT compiler threads (C1/C2) và VM service threads;
- signal dispatcher, native agents, JVMTI/profiler threads;
- JNI/native libraries tạo pthread riêng;
- Java ForkJoinPool, executor hoặc HTTP worker threads.

Một native thread được `top -H` báo nóng nhưng **không có Java stack** tương ứng trong dump. Điều này không chứng minh công cụ OS sai: nó có thể là **non-Java thread** thuộc JVM runtime hoặc JNI. Một số HotSpot dumps có mục riêng về internal threads; định dạng khác nhau giữa builds.

Khi `nid` ánh xạ tới GC worker:

1. Kiểm tra process CPU và tổng GC/JIT activity ở cùng khoảng.
2. Xem GC log/JFR events (GC pauses, concurrent phases) và heap/allocation rate.
3. Không tự quy toàn bộ CPU cao cho “Java method X” vì thread nóng là JVM worker.
4. Nếu đang có native profiling, kiểm tra kiến trúc, đủ symbol và quyền truy cập; Java dump không chứa đầy đủ C/C++ stack.

### 10.1. “Không thấy nid” có thể có nhiều nguyên nhân

- Native thread đã kết thúc trước khi chụp dump.
- JVM restart và OS TID được tái sử dụng.
- Dump không gồm non-Java threads hoặc JDK format chỉ in một phần.
- PID/TID đến từ namespace khác.
- OS công cụ hiển thị **thread-group ID** thay cho LWP do chưa bật threads mode.
- Lỗi parse hex hoặc có nhiều dòng bị cắt/truncated.
- Công cụ `jcmd` đang attach vào một JVM khác.

Đừng gán `nid` gần giống về mặt số học, hoặc ép tìm Java thread “tên gần giống” nếu ID không khớp. Ghi rõ “unmapped” và thu bằng chứng khác.

## 11. CPU cao nhưng dump ghi WAITING hoặc RUNNABLE ở native poll

### 11.1. RUNNABLE không luôn dùng CPU

`Thread.State.RUNNABLE` trong Java là trạng thái VM, có thể gồm đang chờ OS I/O trong native method. Ví dụ tổng hợp:

```text
"selector-0" #70 ... nid=0x2a3f runnable
   java.lang.Thread.State: RUNNABLE
        at java.base/sun.nio.ch.EPoll.wait(Native Method)
        at java.base/sun.nio.ch.EPollSelectorImpl.doSelect(...)
        at java.base/java.nio.channels.Selector.select(...)
```

Đây là mẫu minh họa, stack cụ thể khác giữa các bản JDK. Nếu `top -H` báo TID này gần 0% CPU thì không có mâu thuẫn: Java RUNNABLE không nói thread đang dùng hết một core.

### 11.2. WAITING không có nghĩa lỗi

Một thread ở:

```text
java.lang.Thread.State: WAITING (parking)
    at java.base/jdk.internal.misc.Unsafe.park(Native Method)
    at java.base/java.util.concurrent.locks.LockSupport.park(...)
    at java.base/java.util.concurrent.LinkedBlockingQueue.take(...)
    at java.base/java.util.concurrent.ThreadPoolExecutor.getTask(...)
```

có thể là worker **idle bình thường**. Nếu vừa có một OS CPU sample cao, nhưng dump ngay sau đó ghi WAITING, thread có thể đã hoàn thành tác vụ CPU-bound. Muốn kết luận hotspot, xem CPU time delta và stack nhiều mẫu/JFR thay vì đoán “state sai”.

### 11.3. RUNNABLE lặp lại ở business code

Ví dụ thread liên tiếp được chụp ở:

```text
java.lang.Thread.State: RUNNABLE
    at com.example.pricing.RuleEvaluator.apply(RuleEvaluator.java:214)
    at com.example.pricing.PriceService.score(PriceService.java:86)
```

Nếu cùng lúc CPU time của đúng `nid` tăng đều, đây là bằng chứng **mạnh hơn** cho CPU-bound work. Tuy vậy, ba snapshots ở cùng method vẫn có thể do một loop lặp nhanh đi qua method; muốn biết hàm nào tiêu thụ CPU nhiều nhất cần sampling profiler/JFR, không chỉ một frame.

### 11.4. CPU thấp, latency cao

Một thread có thể bị:

- khóa Java monitor (`BLOCKED`), AQS lock (`WAITING/parking`);
- chờ database/network I/O;
- chờ queue, future hoặc giới hạn downstream;
- CPU throttling/cgroup pressure;
- stop-the-world GC/safepoint;
- native blocking/OS scheduler.

Thread dump và `top -H` giúp phân biệt bước đầu, nhưng CPU thấp không chứng minh “ứng dụng khỏe”. Chọn thread dumps, GC/JFR logs, tracing và cgroup counters theo triệu chứng.

## 12. Cgroup, Kubernetes và chuẩn hóa CPU%

### 12.1. Host CPU khác CPU quota container

Giả sử host có 32 logical CPUs, pod đặt CPU limit 1 core, JVM dùng gần 100% một core trong interval:

- Host-wide CPU% ≈ `100/32 = 3.125%` tổng capacity;
- pod CPU usage so với limit 1 core ≈ `100%`;
- `top -H` Irix mode của một thread nóng ≈ `100%` một core;
- JVM `getAvailableProcessors()` có thể bằng 1 theo container-awareness hoặc khác nếu flag/vendor thay đổi.

Bốn con số có thể **đồng thời đúng**. Vì vậy mọi dashboard phải ghi denominator rõ, không chỉ tên “CPU%”. Nếu pod có limit 500m (nửa CPU), không thể xem một CPU thread báo 50% một core là “dùng 50% quota”: nó có thể gần hết 500m quota.

### 12.2. CPU throttling không nằm trong Java thread state

Nếu cgroup quota dùng hết trong kỳ scheduler, thread muốn chạy có thể bị trì hoãn. `top -H` có thể hiển thị usage thấp hơn kỳ vọng dù requests chậm. Để chứng minh throttling, xem đúng cgroup:

- cgroup v2: `cpu.max` (quota/period), `cpu.stat` (nr_throttled, throttled_usec khi có);
- cgroup v1: các file `cpu.cfs_quota_us`, `cpu.cfs_period_us` và `cpu.stat` trong controller phù hợp;
- orchestrator metrics: CPU throttled periods/time, requests/limits, node contention.

**Không thể khẳng định throttling chỉ từ `nid` hay Thread.State.RUNNABLE**. CPU limit, kernel scheduler, CPU affinity/cpuset và JVM active processor count có thể ảnh hưởng kết quả một cách khác nhau.

### 12.3. Quy tắc khi lấy từ host vs container

1. Chọn một góc nhìn làm **nguồn identity chính**: host PID namespace hoặc container PID namespace.
2. Trong góc nhìn đó, lấy `ps/top`, `/proc` và `nid` phù hợp.
3. Nếu chuyển namespace, ghi mapping PID/TID bằng công cụ/container metadata có thẩm quyền; không đoán theo PID bằng mắt.
4. Ghi container ID, JVM start, image digest và host/node identity vì PID bị reuse.
5. Đặt chung UTC timestamps, interval, đơn vị và scope vào một bản ghi.

## 13. Quy trình thực hành end-to-end cho CPU hotspot

### Bước 1 — Xác minh đúng Java process

Dùng process/service/container metadata để xác định PID và thời điểm JVM start. `jcmd -l` có thể giúp nhưng không liệt kê hết JVM trong container khác. Tránh chọn Java PID chỉ theo tên gần giống.

### Bước 2 — Chọn khoảng đo CPU

Ví dụ dùng `top -H` trong 2–3 interval hoặc `pidstat -t`. Ghi timestamp, tool/version, Irix/Solaris mode, CPU denominator và TID đứng đầu. Đừng dựa vào `ps%CPU` lifetime nếu sự cố chỉ kéo dài vài giây.

### Bước 3 — Đổi decimal TID sang `nid` hex

```bash
# TID mà OS tool báo: 10815.
printf '0x%x\n' 10815
```

Output:

```text
0x2a3f
```

Tìm đúng chuỗi `nid=0x2a3f` trong thread dump **cùng namespace/JVM**.

### Bước 4 — Lấy một thread dump có kiểm soát

```bash
jcmd 12345 Thread.print -l
```

Với JVM có rất nhiều threads, cân nhắc overhead và security. Nếu cần lưu, bảo đảm file private và retention. Dùng `Thread.print -e` nếu JVM hỗ trợ và cần metadata mở rộng; hỏi `jcmd PID help Thread.print` thay vì đoán options theo version.

### Bước 5 — Đọc đúng thread entry

Ghi tên, Java ID nếu có, `tid` pointer, `nid` native ID, Java state, frames và locks:

- `RUNNABLE` + business computation frame → **giả thuyết** CPU hotspot;
- `RUNNABLE` + native socket/epoll → có thể đang đợi I/O;
- `BLOCKED` + `waiting to lock` → lock contention;
- `WAITING` ở `ThreadPoolExecutor.getTask` → có thể idle;
- JVM GC/JIT native thread → xem GC/JIT metrics và event logs.

### Bước 6 — Thu CPU delta hoặc mẫu thứ hai

Nếu triệu chứng còn xảy ra, lấy thêm interval CPU và dump gần đó, so **cùng TID và JVM generation**. Một thread có cùng frame nhưng `CPU time` hầu như không tăng có thể đang đợi; cùng frame và `CPU time` tăng nhanh có cơ sở hotspot hơn.

### Bước 7 — Tìm bằng chứng nguyên nhân

- CPU-bound Java code → JFR Method Profiling, async profiler hoặc công cụ đã được phép; kiểm tra input size, thuật toán, hot loops.
- GC/JIT → GC logs, JFR GC/Compilation events, heap/allocation metrics.
- JNI/native → native profiling, OS scheduling, thư viện/ABI.
- Lock contention → lock owner, `ThreadMXBean`/thread dumps nhiều mốc.
- CPU throttling → cgroup `cpu.stat` và quota.

### Bước 8 — Viết kết luận kiểm chứng được

Một kết luận tốt có dạng:

> Trong pod checkout-3, JVM start gần 08:12Z; tại 08:15:04–08:15:07Z Linux TID 10815 tiêu thụ 0,92–0,98 core-equivalent. Dump cùng JVM hiển thị `nid=0x2a3f`, tên `pricing-hot-loop` và nhiều snapshots trong `PriceEngine.calculate`. JFR samples xác nhận CPU tập trung ở method đó. Cần tối ưu đường tính giá, kiểm chứng sau deploy.

Đây là **mẫu kết luận giả định**, không phải sự kiện đã xảy ra. Nếu chỉ có một dump và một interval OS, dùng “gợi ý” thay vì “chứng minh”.

## 14. Bốn tình huống điều tra minh họa

### Tình huống A — 100% CPU trên một JVM worker

`top -H` báo TID 10815 gần 100% ở Irix mode; dump có `nid=0x2a3f` với `java.lang.Thread.State.RUNNABLE` và `RuleEvaluator.evaluate` ở top. Thu tiếp một vài mẫu thấy CPU time tăng và stack tương tự. **Giả thuyết mạnh** là Java business code CPU-bound; dùng JFR/profiler để xác định method thật sự chiếm thời gian, rồi mới thay thuật toán.

**Tránh:** nhìn thấy RUNNABLE rồi tuyên bố ngay đó là root cause, hoặc đổi số worker threads mà không đo contention/throughput.

### Tình huống B — CPU process cao nhưng không khớp Java thread

OS báo một TID nóng, nhưng không tìm thấy `nid` tương ứng trong Java thread entries. Kiểm tra JVM internal/GC/JIT threads, native library/JNI threads, thời điểm snapshot, namespaces và target PID. GC worker có thể dùng CPU cao trong khi các Java application threads đang WAITING. **Không ép gắn TID cho Java thread tên giống nhau**.

### Tình huống C — CPU tăng ngắn hạn rồi dump thấy WAITING

Trong interval trước dump, OS TID 10815 dùng 80% CPU. Một giây sau, thread đã kết thúc tính toán và đợi queue trong `LinkedBlockingQueue.take`. Dump thấy WAITING. Hai nguồn không mâu thuẫn vì **sampling windows khác nhau**. Để bắt burst ngắn, chọn JFR/profiler sampling hoặc application event tracing thay vì tăng tần suất dump bừa bãi.

### Tình huống D — Pod chậm do CPU quota

Host có 64 CPUs, ứng dụng có container CPU limit 0.5 core. `top -H` của một worker hiển thị trung bình gần 50% một core, còn latency tăng và cgroup `nr_throttled` tăng liên tục. Đây là giả thuyết quota bottleneck mạnh, nhưng vẫn phải xem traffic/GC/queue và phân biệt `CPU requests` với `CPU limits`. Không xem 50% một core nghĩa là “pod còn 50% CPU chưa dùng”.

## 15. Lỗi phổ biến khi đối chiếu native TID và CPU

1. **Tìm `tid` thay cho `nid`.** HotSpot `tid` là VM pointer, không phải Linux LWP.
2. **Dùng `Thread.getId()` để tra `top -H`.** Java ID khác native TID.
3. **Không đổi hex ↔ decimal.** `nid=0x2a3f` khớp OS TID `10815`, không phải 0x2a3f dưới dạng decimal.
4. **Ghép OS output và dump của PID khác.** Chỉ tên process giống nhau là không đủ.
5. **Bỏ qua PID namespace container.** Host và container có thể thấy số TID khác.
6. **Ghép hai đời JVM sau restart.** PID/Java ID/TID có thể bị reuse.
7. **Dùng `ps -L %CPU` như CPU của một giây gần nhất.** `ps` thường là lifetime average.
8. **Quên Irix/Solaris normalization của `top`.** Một con số CPU% có thể khác denominator.
9. **Gọi `CPU% > 100` là lỗi trên process đa luồng.** Process dùng nhiều cores có thể trên 100% kiểu một core.
10. **Cộng `user ticks` và `system ticks` mà quên chia `CLK_TCK`.** Tick không tự động là nanoseconds.
11. **Hard-code `CLK_TCK=100` cho mọi Linux.** Dùng `getconf CLK_TCK`.
12. **Parse `/proc/.../stat` bằng cách split whitespace từ đầu.** Field `comm` có thể làm lệch chỉ số.
13. **Bỏ qua field `starttime` khi TID biến mất/tái xuất hiện.** Có thể nối hai đời thread khác nhau.
14. **Kết luận `RUNNABLE` đồng nghĩa CPU 100%.** Native I/O wait vẫn có thể hiện RUNNABLE.
15. **Xem `WAITING` sau CPU spike là bằng chứng OS sai.** CPU interval và dump là hai thời điểm/cửa sổ khác nhau.
16. **Chọn một frame top rồi sửa code ngay.** Một snapshot không đo hàm chiếm CPU.
17. **Nhầm `java.lang.Thread.State` với Linux `STAT=R/S/D`.** Hai hệ state khác ngữ nghĩa.
18. **Đánh đồng process CPU time với CPU time của một thread.** Chỉ số tổng có thể gồm GC/JIT/native threads.
19. **Bỏ qua JVM internal threads.** GC và JIT có thể là nguồn CPU.
20. **Không xem CPU throttling dù process %CPU không cao.** Cần cgroup quotas/counters.
21. **Chia OS CPU% cho processor count JVM mà không xác minh scope.** Quota fractional và affinity làm sai.
22. **Tin rằng một lần `top -H` và một dump có thể bắt burst 50 ms.** Dùng JFR/profiler sampling phù hợp.
23. **Lấy dump quá dày trên tiến trình đang quá tải.** `Thread.print` có tác động phụ thuộc số threads.
24. **Xem TID không map được là bug của Java.** Có thể là GC/JIT/native hoặc thread đã kết thúc.
25. **Đưa full dump, process args hoặc `/proc` metadata nhạy cảm lên issue công khai.** Gắn quyền/retention.
26. **Dùng `top` interactive trên production nhưng vô tình nhấn thao tác `kill/renice`.** Chỉ thao tác đọc khi mục tiêu là chẩn đoán.
27. **Gộp samples từ các interval khác nhau mà không lưu timestamp.** Kết luận nhân quả dễ sai.

## 16. Checklist thu thập và phân tích

- [ ] Đúng service, JVM PID/start, container ID và PID namespace?
- [ ] `top -H` hoặc `pidstat -t` đang thực sự hiển thị **threads**, không chỉ process?
- [ ] Đã ghi CPU tool version, mode Irix/Solaris, sampling interval và timestamp UTC?
- [ ] TID decimal đã được đổi chính xác sang `nid=0x...` hex?
- [ ] Đã xác nhận `tid` JVM pointer **không** dùng làm Linux LWP?
- [ ] Java ID/`ThreadMXBean` và native ID được tách rõ?
- [ ] Thread trong dump còn tồn tại vào lúc OS sample? Có kiểm tra TID reuse?
- [ ] `%CPU` có phải interval rate hay lifetime average?
- [ ] CPU-time data có đúng ticks/ns và `CLK_TCK` thực?
- [ ] Nếu dùng `/proc`, đã parse field `comm` đúng và xác minh field 14/15/22?
- [ ] Đã hiểu một OS thread dùng tối đa khoảng một core tại một thời điểm, process đa luồng có thể >100%?
- [ ] Có hiểu chuẩn hóa CPU% theo core, host hay quota container?
- [ ] Thread state và Java frames có khớp CPU evidence qua nhiều mẫu?
- [ ] Đã xem JVM GC/JIT/native threads nếu Java entry không khớp?
- [ ] Có kiểm tra cgroup CPU throttling/affinity khi latency tăng nhưng CPU load thấp?
- [ ] Cần JFR/native profiler/GC logs để xác nhận hotspot thay vì chỉ thread dump?
- [ ] Thu thập có quyền và tần suất hợp lý, không làm lộ dữ liệu nhạy cảm?
- [ ] Báo cáo phân biệt quan sát, giả thuyết và kết luận đã xác minh?

## 17. Bài tập vận dụng

**Bài 1 — Đổi ID.** `top -H` hiển thị thread LWP 10815 dùng 87% CPU. Dump HotSpot có các trường `#42`, `tid=0x00007f0120001000`, `nid=0x2a3f`. Trường nào khớp Linux LWP? **`nid=0x2a3f`**, vì `0x2a3f=10815`; `#42` là Java number và `tid` là pointer JVM.

**Bài 2 — CPU% từ ticks.** CPU ticks tăng từ 1000 lên 1075; `CLK_TCK=100`; hai lần đọc cách 2.5 giây wall time. CPU time tăng 0.75 giây; `percentOneCore=0.75/2.5*100=30%`. Trên host 4 cores, tỉ lệ theo cả bốn cores là 7.5%. Tên “CPU%” phải nêu denominator.

**Bài 3 — Hai công cụ báo khác.** `ps -L` báo 65%, `top -H` báo 5% cho cùng TID. Có chắc một trong hai sai? **Không**. `ps` có lifetime average, `top` interval gần đây; thread có thể đã chuyển từ CPU work sang idle. Kiểm tra mode, interval và CPU-time deltas.

**Bài 4 — RUNNABLE nhưng CPU thấp.** Dump có `EPoll.wait(Native Method)` ở state RUNNABLE, `top -H` gần 0%. Có lỗi? **Không mặc định**. Có thể đang chờ native I/O, cần latency/tracing/OS state.

**Bài 5 — 100% quota nhưng 3% host.** Host có 32 cores, pod CPU limit 1 core, JVM dùng xấp xỉ một core. Cùng lúc pod có thể gần 100% quota và host gần 3.125% capacity. Phải nêu rõ source/normalization.

**Bài 6 — Khớp TID sau JVM restart.** Lúc 08:00 thấy `nid=0x2a3f`, lúc 08:10 vẫn có `nid=0x2a3f` nhưng JVM start đã thay. Đó có chắc là cùng Java thread? **Không**: PID/TID có thể được tái sử dụng; không nối hai chuỗi CPU time/dump làm một.

## Tài liệu tham khảo

- Oracle Java SE 17, [Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): ví dụ và cách dùng HotSpot thread dumps, `jcmd Thread.print`, `nid`, JVM troubleshooting.
- Oracle Java SE 17, [`jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, điều kiện quyền và tác động.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): Java thread ID và CPU time nanoseconds, capability flags.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): Java ID, name, state, stack frames, locks.
- Linux man-pages project, [`ps(1)`](https://man7.org/linux/man-pages/man1/ps.1.html): `-L`, `LWP`, `%CPU` và lifetime CPU utilization.
- Linux man-pages project, [`top(1)`](https://man7.org/linux/man-pages/man1/top.1.html): threads mode `H`, Irix/Solaris normalization `I` và CPU% theo update window.
- Linux man-pages project, [`proc(5)`](https://man7.org/linux/man-pages/man5/proc.5.html): `/proc/PID/task/TID` cho từng OS thread.
- Linux man-pages project, [`proc_pid_stat(5)`](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html): fields `utime` (14), `stime` (15), `starttime` (22).
- Linux kernel documentation, [Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, throttling và giới hạn container.

**Kết luận:** bước then chốt khi tìm thread tiêu thụ CPU là **chuyển native TID của Linux thành `nid` trong HotSpot thread dump của đúng JVM**, không dùng nhầm Java ID/VM pointer. Sau đó phải đối chiếu **CPU-time delta và stack snapshots theo cùng thời gian**, có hiểu biết về CPU% normalization, container quota, JVM internal threads và tác động của việc thu thập. Một mapping đúng giúp tìm nơi cần điều tra; bằng chứng lặp lại và profiling mới giúp khẳng định nguyên nhân.