# 17.2 Kết hợp số liệu CPU, nhiều stack snapshot và JFR execution sample

> **Phạm vi:** Java 21 / HotSpot, phân tích một ứng dụng có **CPU cao hoặc throughput/latency bất thường**. Bài này hướng dẫn ghép **CPU metrics của OS/JVM**, **nhiều ảnh chụp thread stack (thread dump)** và **JFR `jdk.ExecutionSample`** thành một kết luận có bằng chứng. Những nhóm CPU dành cho **JIT compiler, class loading và GC** được đưa vào để tránh nhầm CPU của JVM với CPU thực thi mã nghiệp vụ. Các lệnh hệ điều hành minh họa Linux; cần điều chỉnh trên Windows/container.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Xác định **CPU đang cao ở cấp máy, container, tiến trình hay OS thread**, trên đúng JVM/PID và trong **cùng cửa sổ triệu chứng**.
2. Thu **nhiều** stack snapshot có timestamp, phân biệt `RUNNABLE` với đang thực sự dùng CPU và liên hệ thread name, Java thread ID, OS TID (`nid`) khi có.
3. Thu JFR `settings=profile`, đọc `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample` và phân tích phân bố các **stack được lấy mẫu**.
4. Kết hợp ba nguồn để khoanh vùng **hot code path**; giải thích tại sao một snapshot hay một sample **không đủ** khẳng định nguyên nhân.
5. Nhận biết **JIT warmup, class loading, GC, native CPU, CPU quota/throttling và waiting** là những hướng chẩn đoán cạnh tranh; thiết kế phép đo lại để bác bỏ/ủng hộ giả thuyết.

**Câu hỏi xuyên suốt:** “Trong đúng khoảng có triệu chứng, tiến trình Java có thực sự tiêu thụ CPU không; thread nào tiêu thụ; stack nào lặp lại trong **nhiều mẫu độc lập**; và kết luận đó có phù hợp với JFR hay không?”

## 2. Ba nguồn bằng chứng giải ba câu hỏi khác nhau

| Nguồn | Trả lời tốt nhất | Không tự chứng minh được |
| --- | --- | --- |
| **CPU của máy/container/JVM/OS thread** (monitoring, `top`, `ps`, cgroup) | CPU có bận thật không, bận ở đâu, trong bao lâu, mức hạn chế tài nguyên | Phương thức Java nào tốn CPU hoặc code path gọi từ request nào |
| **Nhiều thread dump** (`jcmd <PID> Thread.print`) | Vào từng thời điểm, thread đang ở stack và trạng thái nào; cùng frame có xuất hiện lặp lại không | Thread `RUNNABLE` đã tiêu thụ bao nhiêu CPU giữa hai lần dump; toàn bộ lịch sử |
| **JFR execution sampling** (`jdk.ExecutionSample`, kết hợp `jdk.CPULoad`, `jdk.ThreadCPULoad`) | Trong một khoảng, stack/method nào xuất hiện nhiều trong các mẫu thực thi, xu hướng theo thread/time | Số lần phương thức chạy, số CPU-ns chính xác trên một method hoặc nguyên nhân nhân quả chỉ từ tỷ lệ sample |

Một sự cố CPU đáng tin thường có **tam giác chứng cứ**:

```text
CPU process cao trong cửa sổ T
        │
        ├── OS: những platform thread / TID nào đang bận?
        │
        ├── Thread dump tại T1, T2, T3...: stack nào lặp lại?
        │
        └── JFR trong cùng T: ExecutionSample tập trung ở đâu?
                              ↓
                  Giả thuyết code path nóng
                              ↓
                  Đo/điều chỉnh và so cùng tải
```

Lưu ý: **tương quan theo thời gian** chưa phải bằng chứng chắc chắn về nhân quả. Nếu ba nguồn mâu thuẫn, hãy tìm lý do về thời gian, cấu hình sample, tên thread hoặc CPU không nằm trong Java user code trước khi sửa chương trình.

## 3. Trước khi tìm hot method: định nghĩa “CPU cao”

### 3.1. Phân biệt các cấp đo

- **Machine CPU**: mức sử dụng của toàn máy/VM. Có thể cao vì tiến trình khác, kernel hoặc system services, trong khi JVM ứng dụng lại ít dùng.
- **Process CPU**: CPU time tích lũy của các thread trong tiến trình Java, thường được trình bày dưới dạng tỷ lệ trong một khoảng. `100%` trong một số công cụ Linux tương đương **một logical CPU bận hoàn toàn**, vì vậy một JVM trên máy nhiều core có thể xuất hiện **hơn 100%**. Công cụ khác chuẩn hóa về tổng CPU của máy; phải ghi rõ quy ước.
- **Thread CPU**: CPU time của một OS/platform thread. Nó có thể là thread nghiệp vụ, GC worker, JIT compiler thread hoặc VM thread.
- **Container/cgroup CPU**: CPU sử dụng so với **CPU quota**, `cpu.max`, throttle time và throttled periods. Một pod bị giới hạn 1 CPU có thể bị throttling nghiêm trọng dù cả host còn nhiều lõi rảnh.
- **JFR `jdk.CPULoad`**: sự kiện định kỳ chứa tỷ lệ JVM user/system và máy; sử dụng các field đó **như một phép đo theo thời gian**, không đếm số event để kết luận phần trăm CPU.
- **JFR `jdk.ThreadCPULoad`**: thông tin sử dụng CPU theo thread trong giai đoạn đo; không coi một sự kiện hay tỷ lệ mẫu `ExecutionSample` là số CPU-ns chính xác cho từng phương thức.

Công thức định hướng cho một khoảng đo:

```text
Process CPU cores used ≈ Δ(process CPU time in seconds) / Δ(wall time in seconds)

Nếu trong 10 giây tiến trình tăng 18 CPU-seconds:
    trung bình ≈ 1,8 logical CPUs bận trong khoảng đó
```

Con số trên **chỉ là cách quy đổi CPU time thành mức sử dụng core trung bình**; không thể kết luận 1,8 core bị chiếm đều suốt 10 giây hoặc hệ thống đạt 180% theo cùng quy ước của mọi dashboard. Phải đọc số core/quota hợp lệ và khoảng lấy mẫu của nguồn đo.

### 3.2. Một ví dụ dễ nhầm

| Tín hiệu | Diễn giải ưu tiên |
| --- | --- |
| Host CPU 95%, JVM process 8% | Kiểm tra tiến trình khác hoặc CPU của kernel; đừng vội tối ưu Java |
| JVM dùng gần 2 core nhưng pod bị quota 2 core | Có thể saturation; xem throttling, backlog, p95/p99 |
| JVM CPU cao lúc vừa startup, giảm sau vài phút | Có thể JIT warmup, class loading, GC và cache; chưa đủ gọi là hot loop bất thường |
| JVM CPU thấp, request latency cao và thread thường `WAITING` | Xem connection pool, lock/park, socket I/O, downstream thay vì coi là CPU bottleneck |
| Một thread `RUNNABLE` trong một dump | Không chứng minh nó dùng 100% CPU; trạng thái Java không phải phép đo CPU time |

Đối với ứng dụng chạy container, hãy đối chiếu CPU usage, quota và `nr_throttled`/`throttled_usec` hoặc metric tương ứng của phiên bản cgroup; định dạng khác nhau giữa cgroup v1/v2. Nếu thiếu số liệu quota, ghi rõ độ bất định, tránh kết luận hệ thống còn dư CPU chỉ vì nhìn CPU host.

## 4. Chốt cùng một cửa sổ thời gian và JVM

Trước khi thu chứng cứ, ghi ít nhất: tên service, host/pod, PID, **startup time**, JDK vendor/build, phương thức deploy, khung giờ p95/p99 hoặc throughput bất thường, CPU của process và container, resolution/sampling interval.

Ví dụ giả định:

```text
Service/pod:        orders-api / orders-7b8...
JVM:                Java 21, PID 3187 (cần xác nhận thực tế)
Symptom UTC:        2026-10-29T10:15:20Z .. 10:16:50Z
CPU series:         process + machine + container, bucket 10 s
Stack snapshots:    10:15:30, 10:15:34, 10:15:38, 10:15:42Z
JFR recording:      bao trùm 10:14:30 .. 10:17:30Z
Control window:     10:12:00 .. 10:13:30Z, tải tương đương
```

**Đây là dữ liệu ví dụ**, không phải một sự cố đã quan sát. Các dấu thời gian phải được quy về cùng timezone/UTC và đối chiếu NTP/clock skew. Dashboard lưu bucket 10 giây không đủ để khẳng định một method bắt đầu chạy chính xác trước alert 5 ms.

Khi JVM restart, PID có thể được dùng lại. Không nối các stack dump/JFR của hai JVM khác nhau thành cùng một phép đo nếu chưa đánh dấu rõ ranh giới restart và khởi động/warmup.

## 5. Thu CPU cùng lúc với thread dump trên Linux

### 5.1. Xác minh đúng tiến trình và đo CPU

`jcmd` phải attach vào JVM đúng user/machine/namespace (trên container, PID nhìn từ host có thể khác). Thay **`3187`** bằng PID thật; ví dụ sau chỉ dùng trong môi trường được phép quan sát:

```bash
jcmd -l
jcmd 3187 VM.version
jcmd 3187 VM.uptime
ps -p 3187 -o pid,ppid,etime,pcpu,comm
```

Xem usage từng OS thread trên Linux khi triệu chứng còn xảy ra:

```bash
top -H -p 3187
```

Hoặc in bảng TID (phần trăm CPU của `ps` là **thống kê theo quy ước/cửa sổ của ps**, không tự bảo đảm tức thời):

```bash
ps -L -p 3187 -o pid,tid,psr,pcpu,stat,comm
```

Chọn thời điểm `top` có thread nóng để lấy **TID hệ điều hành** và timestamp. Một JVM có nhiều thread tương ứng các vai trò khác nhau; không phải mọi OS thread đều là Java thread của request.

Trên máy hoặc container đang tải, tránh chạy công cụ quá thường xuyên hoặc lấy output quá lớn. Có thể thu 3–6 ảnh chụp theo nhịp vài giây trong một đợt spike dài, tùy mức nhạy của dịch vụ và số thread.

### 5.2. Lấy nhiều thread dump có timestamp

Dùng lệnh **được JDK 21 hỗ trợ**:

```bash
jcmd 3187 help Thread.print
jcmd 3187 Thread.print -e -l
```

- `-e`: thông tin thread mở rộng.
- `-l`: thông tin `java.util.concurrent` locks/ownable synchronizers.
- `Thread.print` có **Impact: Medium**, phụ thuộc số lượng thread; việc lấy nhiều dump cũng có chi phí. Hãy định khoảng cách vừa đủ để thấy thay đổi trạng thái mà không biến quá trình điều tra thành gánh nặng mới.

Ví dụ shell Linux **cố ý lấy bốn snapshot**, kèm thời gian bên ngoài mỗi lệnh:

```bash
umask 077
mkdir -p ./cpu-evidence

for index in 1 2 3 4; do
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "./cpu-evidence/stack-$index.time"
  jcmd 3187 Thread.print -e -l > "./cpu-evidence/stack-$index.txt"
  sleep 3
done
```

Chạy trong thư mục an toàn, có quyền ghi và đủ dung lượng; sửa PID trước khi chạy, kiểm tra mã thoát `jcmd` và file không rỗng. Mỗi snapshot chỉ phản ánh **một thời điểm**; việc `date` ghi trước khi gọi lệnh cũng có một sai số gồm thời gian attach/thu dump. Nếu cần chặt hơn, ghi cả giờ trước và sau để tạo khoảng sai số.

**Không lấy toàn bộ kết quả `Thread.print` đưa lên ticket công khai.** Stack có thể lộ package, class, đường dẫn, thông tin nội bộ. Giữ nguyên file gốc, đánh dấu version/instance/UTC, kiểm soát người đọc.

### 5.3. Từ OS TID sang `nid` trong thread dump

Đối với nhiều **platform threads của HotSpot trên Linux**, dòng thread dump chứa `nid=0x...` là native thread ID biểu diễn hệ 16; `top -H`/`ps -L` thường hiển thị TID ở hệ 10. Ví dụ minh họa:

```bash
printf '0x%x\n' 12345
```

Kết quả của lệnh trên:

```text
0x3039
```

Nếu OS TID là `12345`, tìm `nid=0x3039` trong dump **của cùng JVM và thời điểm tương ứng**, từ đó đọc tên thread và stack. Đừng nhầm `nid` với giá trị `#...`, `tid=0x...` hoặc Java `Thread.getId()/threadId()`; đây là những định danh khác nhau. ID có thể bị tái sử dụng sau khi thread kết thúc.

Với **virtual threads** Java 21, nhiều virtual threads không sở hữu OS TID cố định vì chạy luân phiên trên carrier. `Thread.print` truyền thống **không trình bày đầy đủ mọi virtual thread**. Nếu nhiệm vụ cần quan sát virtual threads, có thể dùng `jcmd <PID> Thread.dump_to_file -format=json <path>` của JDK 21 nhưng nội dung/khóa/monitor không giống dump truyền thống. Không cố “map một virtual thread sang một OS TID vĩnh viễn”.

### 5.4. Đọc trạng thái thread mà không suy diễn quá mức

| Trạng thái trong dump | Ý nghĩa cần kiểm tra | Điều không nên khẳng định |
| --- | --- | --- |
| `RUNNABLE` | Java thread có thể chạy hoặc đang thực thi; stack cho biết vị trí hiện tại, có thể ở native call | Không đồng nghĩa thread đang chiếm một CPU core |
| `BLOCKED` | Đang chờ vào monitor `synchronized` | Không phải CPU-bound loop chỉ vì nhiều thread BLOCKED |
| `WAITING` | Chờ vô thời hạn theo cơ chế Java, ví dụ `Object.wait`, `LockSupport.park` | Không đồng nghĩa leak hoặc deadlock |
| `TIMED_WAITING` | Chờ có giới hạn như `Thread.sleep`, timed park | Không phải nguyên nhân CPU cao nếu thiếu nguồn khác |
| `NEW` / `TERMINATED` | Chưa bắt đầu / đã kết thúc (nếu công cụ quan sát được) | Không phải thread được OS lập lịch bận hiện tại |

Đối với `RUNNABLE`, **đối chiếu OS thread CPU** và **sự lặp lại của call stack** qua ít nhất vài snapshot. Đừng đếm mọi dòng `RUNNABLE` để nhân ra “số core bận”.

## 6. Vì sao cần nhiều stack snapshot?

Một thread dump là một lát cắt trong vài mili giây hoặc lâu hơn. Nó rất dễ bắt trúng một lệnh bình thường đang thoáng chạy; đồng thời có thể **bỏ lỡ** đoạn code nóng khi stack đổi nhanh hoặc thread vừa bị OS deschedule.

Chẳng hạn một chuỗi giả định có cùng thread:

```text
T1  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T2  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T3  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
T4  cpu-hot-A  RUNNABLE  PriceCalculator.aggregate()
```

Nếu OS cho biết TID tương ứng dùng CPU ổn định và JFR có nhiều `ExecutionSample` tại `PriceCalculator.aggregate`, giả thuyết phương thức này **tiêu thụ đáng kể thời gian thực thi trong khoảng đó** trở nên mạnh hơn. Nhưng nếu chỉ có một ảnh chụp và `top` cho thấy CPU thấp, đây chưa phải bằng chứng.

Một chuỗi khác:

```text
T1  worker-1  RUNNABLE      processOneBatch()
T2  worker-1  TIMED_WAITING Thread.sleep()
T3  worker-1  WAITING       LinkedBlockingQueue.take()
T4  worker-1  RUNNABLE      processOneBatch()
```

Đây có thể là vòng xử lý bình thường có cả làm việc lẫn chờ; “thấy `processOneBatch` hai lần” chưa chứng minh vòng lặp bất tận. Hãy kiểm tra **tỷ lệ CPU**, tần suất hoạt động và JFR samples theo cùng window.

**Phương pháp ghép snapshots:**

1. Nhóm theo **JVM identity + OS TID/nid + thread name** khi có; đừng chỉ dùng tên thread có thể trùng.
2. Gắn thời điểm/UTC; xác nhận chúng giao cửa sổ CPU cao.
3. So **mẫu stack từ trên xuống và call chain** (top frame có thể thay do inline/JIT, vì vậy quan sát thêm khung caller/hot package).
4. Tính “xuất hiện ở `k` trong `n` snapshots” **như chỉ số gợi ý**, không quy ra “k/n % CPU”.
5. Phân biệt nhiều threads cùng một vùng code với một thread lặp ở đó; cả hai có thể gây CPU cao nhưng giải pháp khác nhau.
6. Tìm thông tin trái giả thuyết: khi CPU hết cao thì stack có còn ở đó không? Trên nhiều bản ghi/tải khác nhau có xuất hiện tương tự không?

Nếu một ứng dụng có 100.000 virtual threads, phương pháp chụp quá nhiều full dumps không phù hợp; dùng JFR sampling và scoped metrics trước, chỉ tạo dump virtual threads khi có lý do rõ.

## 7. Thu JFR `ExecutionSample` trong đúng khoảng CPU cao

### 7.1. Tạo recording trên JVM chạy thật (Java 21)

Xác minh trước rằng JVM đích có JFR và quyền attach; **bật recording khi symptom tái hiện**, không chờ sự cố kết thúc rồi đòi dữ liệu lịch sử. Ví dụ:

```bash
jcmd 3187 JFR.check
jcmd 3187 JFR.start name=cpu-investigation \
  settings=profile duration=90s \
  filename=/srv/diagnostics/cpu-investigation.jfr
```

`settings=profile` chọn profile thu nhiều mẫu thực thi hơn `default` trên JDK 21; chi phí thường cao hơn nên giới hạn cửa sổ. Đường dẫn **thuộc filesystem JVM** và phải ghi được; tên và PID là ví dụ cần thay. Nếu recording đã tồn tại, không đặt cùng tên một cách tùy tiện; xem `JFR.check` trước.

Khi cần xuất dữ liệu sớm mà vẫn giữ recording hoạt động:

```bash
jcmd 3187 JFR.dump name=cpu-investigation \
  filename=/srv/diagnostics/cpu-partial.jfr
```

Lưu cả thông số `.jfc`, thời gian bắt đầu/kết thúc, JVM build, checksum và event types. `JFR.dump` xuất dữ liệu hiện có; không tạo ra event trước lúc recording bắt đầu.

Sau khi đã có file (trong môi trường truy cập được):

```bash
jfr summary cpu-investigation.jfr
jfr metadata --events jdk.ExecutionSample,jdk.CPULoad,jdk.ThreadCPULoad cpu-investigation.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-investigation.jfr
jfr print --stack-depth 64 --events jdk.ExecutionSample cpu-investigation.jfr
```

**Cảnh báo khi so sánh:** `jfr print` lọc theo **event type**, không tự giới hạn theo một khoảng thời gian do người dùng chỉ định. Nếu file chứa nhiều thời điểm, hãy chọn interval trong JDK Mission Control hoặc lập bộ lọc thời gian bằng `jdk.jfr.consumer`. `jfr summary` đếm event trong **toàn recording**; không lấy counts cả file để kết luận chỉ từ một phút có sự cố.

### 7.2. Ý nghĩa của ba event

| Event JFR | Đọc như thế nào | Lỗi diễn giải cần tránh |
| --- | --- | --- |
| `jdk.CPULoad` | Xem giá trị tỷ lệ `jvmUser`, `jvmSystem`, `machineTotal` **theo timestamp** để biết JVM và host bận đến đâu | Đếm 10 event CPU load rồi nói JVM dùng 10 CPU |
| `jdk.ThreadCPULoad` | Xem CPU load/định danh của thread, theo event và khoảng đo; kiểm tra role của các worker nóng | Gán trực tiếp `% sample ExecutionSample` thành CPU load của thread |
| `jdk.ExecutionSample` | Xem `eventThread`, `stackTrace`, `startTime`; nhóm theo stack/method/time trên **cùng cửa sổ** | Xem mỗi event là một lần gọi method hay số CPU milliseconds chính xác |

Trong JDK 21, `jdk.ExecutionSample` là **lấy mẫu** vị trí thực thi chứ không phải trace từng lời gọi. Các thread đang chờ lock, sleep hoặc I/O có thể ít được lấy mẫu hơn; để tìm lý do chờ hãy xem thêm `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead` và các event tương ứng **nếu recording có bật**. Một phương thức xuất hiện nhiều trong samples gợi ý đó là **hot path** theo điều kiện sampling, không tự chứng minh nó gây ra request timeout.

Cấu hình `default`/`profile`, interval, stack depth và workload ảnh hưởng số mẫu. Hai recordings với số sample khác nhau không nên so số đếm tuyệt đối nếu thời gian và tần suất sampling khác nhau.

### 7.3. Phân tích trong JDK Mission Control (JMC)

JMC có thể được cài riêng. Tên tab thay đổi theo version nhưng thao tác cốt lõi gồm:

1. Mở file `.jfr`, xác minh JVM/instance và khoảng recording.
2. Chọn **đúng thời gian CPU cao** trên timeline; đối chiếu với timezone và độ phân giải của monitoring.
3. Xem **CPU usage** theo JVM/machine; nếu CPU JVM thấp, dừng giả thuyết “Java code CPU-bound”.
4. Mở **Method Profiling / Hot Methods / Call Tree** để xem tỷ lệ stack samples; phân biệt **self/top method** và **inclusive call tree**.
5. Phân nhóm theo **thread**, phân biệt business worker với compiler/GC/VM threads, đánh dấu các method hoặc library tập trung mẫu.
6. Chuyển sang cửa sổ đối chứng bình thường với cùng cài đặt; xem cùng một method có chiếm mẫu ngay cả khi CPU thấp không.
7. Kiểm tra `Compiler`/`Class Loading`/`GC` event và heap/threads khi CPU tăng gần startup/deploy.

Ví dụ JIT có thể **inline** phương thức vào caller, đổi stack profile, hoặc tối ưu loop qua thời gian. Đừng dựa tuyệt đối vào thứ tự một top frame khi các snapshots/JFR khác thời điểm hoặc JVM đã warmup khác nhau.

## 8. Cách ghép ba nguồn thành một bảng bằng chứng

Đừng phân tích ba nguồn thành ba câu chuyện độc lập. Dùng cùng **thời gian UTC, service instance, JVM và nhóm thread**:

| Khoảng / tín hiệu | CPU process/container | Nhiều thread dump | JFR ExecutionSample | Kết luận tạm |
| --- | --- | --- | --- | --- |
| Tăng CPU dưới tải | Gần quota, thread TID A dùng CPU cao | `nid=A` RUNNABLE, lặp frame `calculate()` | Nhiều samples cùng code path trong window | Giả thuyết `calculate()` CPU-bound mạnh; kiểm tra JIT/GC |
| CPU host cao, JVM thấp | CPU machine cao, process JVM ổn | Business threads chủ yếu WAITING | Ít samples ứng dụng | Kiểm tra process khác/kernel hoặc quota metrics |
| JVM CPU tăng khi startup | Process CPU cao 1–2 phút đầu | Nhiều class loader/compiler frames (không nhất thiết thấy trong Java dump) | Nhiều startup path và JIT samples | Có thể warmup; so sau khi ổn định |
| p99 cao, CPU JVM thấp | CPU thấp | Threads chờ pool/network | Hot-method samples không tập trung | Ưu tiên I/O, contention, pool; xem JFR blocking events |
| JVM CPU cao, business samples ít | Process bận | Dump business threads không nổi bật | Ít `ExecutionSample` Java business code | Xem JIT compiler, GC worker, native CPU, sample settings |

**Tất cả hàng là tình huống minh họa**, không phải một bộ kết quả thật; cần thêm log, tải và điều kiện tái hiện trước khi quyết định sửa code.

### 8.1. Đừng cộng nhầm các đại lượng

- `jdk.CPULoad` có **giá trị phần trăm/ratio** theo thời gian; không cộng các giá trị như CPU-seconds.
- Một sample không chứa thời lượng thực thi của frame Java tương ứng. Mẫu của nhiều threads và nhiều khoảng thời gian phải **chuẩn hóa theo số samples hợp lệ**.
- 60% samples trong `PriceCalculator` **không đồng nghĩa** phương thức chiếm đúng 60% CPU time hoặc 60% request latency.
- Một method **inclusive** trong call tree có thể xuất hiện ở nhiều samples vì nó gọi các method con; **self** là thời điểm sampled trực tiếp tại method. Không cộng hai tỷ lệ của cùng stack như hai nguồn CPU độc lập.
- OS thread CPU có thể chứa thời gian native/JNI hoặc runtime; JFR `ExecutionSample` không phải profiler native toàn diện.
- Nếu biết máy có 8 logical cores và CPU JVM tương đương 1 core, không thể gọi đó là 100% tổng máy chỉ bằng giá trị 100% của `top`.

### 8.2. Từ tương quan tới giả thuyết có thể kiểm chứng

Ví dụ bảng điều tra giả định:

```text
Triệu chứng: p99 tăng cùng process CPU từ 0,8 lên 2,0 cores
OS:        TID 8142/8144 là hai threads bận, cùng JVM/PID
Dump:      nid tương ứng có 4/5 snapshots tại computeQuote()
JFR:       trong window, phần lớn sampled stacks của hai threads
           có computeQuote() hoặc caller liên quan
Ngoại lệ:  GC pause thấp; JIT compilation ít trong window
Giả thuyết: computeQuote() đang làm nhiều phép tính dư dưới tải
Kiểm chứng: đo thời gian một request và throughput trước/sau thay đổi
```

Đây là **ví dụ lý luận**, không phải kết luận thực tế. Kiểm tra xem phương thức đó vốn là hot path hợp lệ do có rất nhiều request; nếu giảm số lần xử lý nhưng làm sai logic, không được xem là tối ưu thành công.

Thử nghiệm đáng tin phải đối chiếu **đúng workload, số cores/quota, cấu hình JDK/GC, dữ liệu đầu vào và trạng thái warmup**; báo cáo throughput, p95/p99, CPU-seconds/request và error rate, không chỉ một flame graph trông đẹp hơn.

## 9. Lab Java 21: hai CPU workers và một sleeper

Lab dưới đây cố tình có **hai platform threads tính toán liên tục** và một thread chỉ ngủ. Nhờ đó, bạn có thể nhìn thấy sự khác nhau giữa CPU time, trạng thái thread ở nhiều dump và phân bố `ExecutionSample`, mà không cần ứng dụng bên ngoài.

Tạo file **`CpuCorrelationLab.java`**:

```java
public class CpuCorrelationLab {
    private static volatile boolean stop;
    private static volatile long sink;

    public static void main(String[] args) throws Exception {
        int seconds = args.length == 1 ? Integer.parseInt(args[0]) : 25;
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        stop = false;
        Thread cpuA = new Thread(CpuCorrelationLab::burnCpu, "cpu-hot-A");
        Thread cpuB = new Thread(CpuCorrelationLab::burnCpu, "cpu-hot-B");
        Thread sleeper = new Thread(() -> {
            while (!stop) {
                try {
                    Thread.sleep(250);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "idle-sleeper");

        cpuA.start();
        cpuB.start();
        sleeper.start();
        System.out.println("READY: two CPU workers and one sleeper");
        Thread.sleep(seconds * 1000L);
        stop = true;
        cpuA.join();
        cpuB.join();
        sleeper.join();
        System.out.println("DONE");
    }

    private static void burnCpu() {
        long x = 1;
        while (!stop) {
            x = mixedWork(x);
            sink = x;
        }
    }

    private static long mixedWork(long x) {
        for (int i = 0; i < 20_000; i++) {
            x ^= (x << 13);
            x ^= (x >>> 7);
            x ^= (x << 17);
        }
        return x;
    }
}
```

Đây là chương trình độc lập, dùng Java API ổn định có sẵn trong Java 17+ và **biên dịch/chạy bằng JDK 21** mà không cần preview flag. Nó chỉ tạo tải CPU cục bộ; **không chạy trên máy production** hoặc node đang có CPU quota quá chặt.

**Terminal A:** biên dịch rồi khởi động với JFR profile trong 25 giây:

```bash
javac CpuCorrelationLab.java
java -XX:StartFlightRecording=filename=cpu-lab.jfr,settings=profile,dumponexit=true \
  CpuCorrelationLab 25
```

Chương trình sẽ giữ hai worker bận khoảng 25 giây, rồi dừng chúng. Sau khi hoàn tất bình thường, stdout **do code tự in** là:

```text
READY: two CPU workers and one sleeper
DONE
```

JVM/JFR có thể in **thông báo khởi động recording riêng**, nên toàn bộ terminal output có thể nhiều hơn hai dòng này. Tên file đầu ra có thể chứa JFR event rất khác nhau theo máy và tải. File `.jfr` được ghi tại working directory; đảm bảo đủ dung lượng và phân quyền.

**Terminal B:** trong lúc còn thấy `READY`, xác định PID thật của lab, đo CPU và lấy snapshot. Ví dụ dưới dùng `3187` làm **placeholder**, không phải PID cố định của lab:

```bash
jcmd -l
top -H -p 3187
jcmd 3187 Thread.print -e -l
```

Lấy 3–5 dumps ở những thời điểm khác nhau (cùng cách ở mục 5.2). Kiểm tra rằng `cpu-hot-A`, `cpu-hot-B` có khả năng xuất hiện nhiều lần tại `mixedWork`/`burnCpu`, còn `idle-sleeper` thường ở `Thread.sleep`/`TIMED_WAITING`. Số lần xuất hiện và frame cụ thể **không được bảo đảm** vì snapshot timing và JIT inlining.

**Sau khi terminal A kết thúc**, xem recording:

```bash
jfr summary cpu-lab.jfr
jfr print --events jdk.CPULoad,jdk.ThreadCPULoad cpu-lab.jfr
jfr print --stack-depth 64 --events jdk.ExecutionSample cpu-lab.jfr
```

Trong JMC, mở `cpu-lab.jfr`, chọn 20–25 giây lab hoạt động và mở hot methods/call tree. Giải thích vì sao hai thread tính toán xuất hiện nhiều trong samples, nhưng `idle-sleeper` không nên được coi là CPU hotspot chỉ vì nó tồn tại lâu.

**Bài thực hành tăng độ khó:** chạy lại lab với tham số 10 và 40 giây, cùng JDK/JFR settings. So **tỷ lệ samples theo call path** thay vì số samples tuyệt đối; so CPU theo cores, warmup và duration. Nếu máy chỉ có 1 core/quota, hai CPU workers sẽ **tranh nhau** thời gian CPU, và tổng process CPU có thể không đạt 2 cores. Không dùng lab này làm benchmark ứng dụng thực tế.

## 10. Trường hợp số liệu mâu thuẫn: chẩn đoán trước khi sửa

### 10.1. OS báo CPU cao, JFR `ExecutionSample` hiếm

Các hướng kiểm tra:

- Đúng recording/JVM/PID và window chưa? JFR đang dùng `settings=default` ít mẫu hơn hay event bị tắt?
- CPU đó đến từ **GC worker hoặc JIT compiler native threads** mà `ExecutionSample` của business Java code không đại diện đủ?
- CPU đang dành cho JNI/native code, crypto native, codec, thư viện ngoài JVM hoặc kernel? Java stack tại thời điểm snapshot có thể chỉ thể hiện lời gọi native/Java wrapper.
- Thời gian sampling quá ngắn, method chạy rất nhanh, JIT inlining, event/drop/truncation hoặc sampling bị ảnh hưởng bởi cấu hình?
- Có `-Xint`/debug build/JIT flags khác bình thường hoặc trình profiler cùng chạy làm thay đổi profile?

Dùng metrics CPU per-thread và JFR Compiler/GC events để chọn hướng. Nếu yêu cầu hotspot bên **native**, cân nhắc OS profiler như `perf` trên Linux (khi được phép và phù hợp kernel/JDK), vì JFR Java execution samples không thay thế mọi native stack.

### 10.2. Stack snapshot thấy `RUNNABLE` thường xuyên nhưng CPU thấp

`RUNNABLE` không phải số liệu tiêu thụ CPU. Các thread có thể runnable nhưng **chưa được OS cấp CPU**, chờ native syscall hoặc tranh CPU quota. Kiểm tra per-thread CPU time trong cùng khoảng, throttling, số CPU logical, thread scheduling và sampling. Có thể thread dump luôn bắt một vòng ngắn đang chạy, trong khi phần lớn thời gian nó chờ.

### 10.3. JFR thấy nhiều mẫu ở code khi startup

Class loading, bytecode verification, JIT compilation, method profiling/warmup, code cache và GC có thể tạo CPU cao tạm thời. Để phân biệt:

1. Kiểm tra CPU trên **startup vs steady-state** và dấu thời gian deploy.
2. Xem `jdk.Compilation`, `jdk.ClassLoad`/class loading stats và các event GC **nếu có** trong recording (không mặc định đã bật tất cả).
3. So số mẫu nghiệp vụ trong khoảng sau warmup; nếu hotspot biến mất thì tối ưu code trên startup path có thể cần tiêu chí khác với throughput nóng.
4. Không coi mọi stack trong compiler/JDK là “lỗi JIT”. Chỉ chứng minh khi có bằng chứng về compilation activity, CPU thread tương ứng và tác động đến SLO.

### 10.4. Latency cao, CPU vẫn bình thường

Sử dụng JFR duration events và tracing: `jdk.JavaMonitorEnter`, `jdk.ThreadPark`, `jdk.SocketRead`, `jdk.FileRead`, pool queues, database latency. Những event này có threshold và config riêng, nên vắng mặt không có nghĩa không có chờ. JFR execution samples thường **thiên về thread thực thi**; một request chờ I/O lâu có thể hầu như không có hot samples dù người dùng thấy rất chậm.

### 10.5. Nhiều hot methods thay đổi theo từng lần đo

Sampling có sai số; dưới số mẫu nhỏ, thứ hạng phương thức dễ dao động. Chọn cửa sổ đủ dài, ghi sample count, lặp nhiều lần, xem **call tree, caller và nhóm method** thay vì một top frame. Nếu có hai phases (ví dụ parse rồi calculate), gộp toàn recording sẽ che giấu từng pha. Chia theo symptom phases và cùng CPU metrics.

## 11. Bảng checklist đối chiếu dành cho điều tra production

| Bằng chứng | Phải có | Dùng để xác thực |
| --- | --- | --- |
| **CPU timeline** | CPU host, JVM process, cgroup quota/throttling, cùng UTC window và bucket | Có saturation thật ở JVM hay không |
| **Per-thread CPU** | OS TID, %CPU hoặc CPU-time delta, timestamp, PID/host | Hot OS thread là ai |
| **Snapshot series** | 3–6 thread dumps có timestamp, `nid`, stack và trạng thái | Frame nào lặp lại trong spike |
| **JFR recording** | File `.jfr`, recording interval, JDK build, JFR settings/profile, checksum | Dữ liệu lấy mẫu và tỷ lệ các event |
| **JFR ExecutionSample** | Event count trong interval, thread IDs, stack, hot methods/call tree | Mức tập trung sampled execution |
| **JVM runtime phụ trợ** | GC pauses, compiler activity, class loading khi có event | Có yếu tố JIT/GC/warmup gây nhiễu hay không |
| **Ứng dụng** | Request rate, endpoint, trace/span, p95/p99, error rate, deploy | Hot path gắn với tác động người dùng ra sao |
| **So sánh đối chứng** | Window bình thường cùng workload/config và phép đo sau thay đổi | Giả thuyết có đứng vững ngoài một lần quan sát không |

Không phải service nào cũng thu được đầy đủ mọi cột. Khi thiếu dữ liệu, **đánh dấu đúng phần thiếu** và mức chắc chắn của kết luận; tránh tự điền TID, CPU %, stack hay sample count mà chưa đo.

## 12. Những lỗi suy luận phổ biến

**“Thấy `RUNNABLE` là CPU bị chiếm.”** Sai: trạng thái Java không phải CPU profiler. Phải đọc OS/JFR CPU time.

**“Một thread dump cho biết method nào chiếm nhiều CPU nhất.”** Sai: nó chỉ là snapshot; cần chuỗi snapshots và sampling trong cửa sổ có triệu chứng.

**“60% JFR samples nghĩa là method chiếm chính xác 60% CPU.”** Sai: đó là tỷ lệ mẫu của tập event đã ghi, phụ thuộc sampling và điều kiện lọc.

**“CPU của host 99% nên Java process là thủ phạm.”** Không chắc: phải kiểm tra CPU theo process và container.

**“Có 16 threads RUNNABLE nên chắc dùng 16 cores.”** Không suy ra được; số runnable threads có thể lớn hơn số cores và chúng còn tranh nhau lịch CPU.

**“Top frame của một sample là method gốc gây tải.”** Chưa chắc: cần call chain, inclusive/self samples, JIT inlining và context workload.

**“Không có ExecutionSample nghĩa là không dùng CPU.”** Không chắc: recording settings, sample interval, native/GC/compiler CPU và dữ liệu thiếu đều có thể giải thích.

**“Tối ưu hot method là giải quyết p99.”** Chỉ đúng sau khi chứng minh liên hệ critical path, đo lại CPU-seconds/request, latency, throughput và correctness cùng tải.

## 13. Bài tập tự đánh giá

1. Một JVM trên máy 8 logical cores dùng 1,5 CPU-seconds trong một giây. Giải thích ý nghĩa “~1,5 cores bận”, và tại sao số `%CPU` của `top` có thể khác dashboard đã chuẩn hóa về 8 cores.
2. Lấy bốn snapshots quanh thời điểm CPU cao của lab. Tìm `cpu-hot-A/B`, chọn một TID từ `top -H`, chuyển sang hex và đối chiếu `nid`. Nêu vì sao OS TID và Java thread ID không cùng loại.
3. Mở `cpu-lab.jfr`; xem `jdk.CPULoad` và samples của `mixedWork`/`burnCpu`. Lặp lab với `10` và `40` giây, so **sample proportions** và giải thích khác biệt do warmup/JIT/sampling.
4. Trong một kịch bản giả định, host 90% CPU, JVM 12%, request p99 tăng, đa số thread `WAITING`. Viết giả thuyết ưu tiên và số liệu cần thu thay vì sửa hot Java method.
5. Một JVM có 70% sampled stacks ở `jsonEncode`, nhưng CPU process thấp và QPS lớn. Giải thích vì sao `jsonEncode` có thể nhiều mẫu mà chưa đáng tối ưu.
6. So sánh GC/JIT CPU trong phút sau deploy với mười phút sau. Thiết kế cách đo để không kết luận nhầm “CPU leak” khi warmup.

**Checklist hoàn tất:** đã xác định đúng JVM và cửa sổ UTC; có process/container CPU + OS TID; có nhiều dumps lặp theo thời gian; có JFR profile ghi được `ExecutionSample` và CPULoad; ghép stack/thread theo cùng giai đoạn; đã kiểm tra JIT, GC, class loading và waiting; kết luận có điều kiện, phép kiểm chứng và chỉ số trước/sau.

## 14. Tài liệu gốc (Java 21)

- [Oracle JDK 21 — `jcmd` command: `Thread.print`, `JFR.start`, `JFR.check`, `JFR.dump`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr` command: `summary`, `print`, `metadata`, `view`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 21 — Virtual Threads: virtual-thread dump và khác biệt với platform threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle JDK 21 — JFR package và cấu hình sự kiện](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle JDK 21 — Diagnostic Tools và giới hạn thu thread dump](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
