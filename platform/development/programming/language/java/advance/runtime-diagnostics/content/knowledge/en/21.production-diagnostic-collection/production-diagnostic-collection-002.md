# 21.2 Lập thứ tự thu thập theo triệu chứng và thời gian còn lại trước khi sự cố biến mất

## Mục tiêu

Trong vận hành, **bằng chứng chẩn đoán có thời hạn tồn tại**. JVM có thể tự phục hồi, được autoscaler thay thế, bị OOM killer kết thúc, container bị reschedule, hoặc spike CPU/độ trễ chỉ kéo dài vài chục giây. Nếu chọn sai thứ tự thu thập, đến lúc tạo xong một heap dump vài gigabyte thì thread đang deadlock đã biến mất, instance đã restart và recording JFR trong bộ nhớ cũng không còn.

Bài này hướng dẫn chọn **đúng bằng chứng, đúng thứ tự, đúng mức rủi ro** theo triệu chứng và khoảng thời gian dự kiến còn lại của sự cố. Sau bài học, bạn có thể:

1. Nhận biết sự khác nhau giữa bằng chứng **biến mất khi process chết**, bằng chứng có sẵn trong log/monitoring và bằng chứng cần chuẩn bị **trước incident**.
2. Lập ưu tiên theo dấu hiệu **hang/deadlock, CPU spike, GC thrashing/heap OOM, native RSS tăng, I/O/latency và crash/restart**.
3. Dùng thời gian còn lại (vài giây, dưới một phút, vài phút, ổn định dài) để chọn giữa **JFR dump, thread dump, process/OS snapshot, heap histogram, heap dump và NMT**.
4. Phân biệt **snapshot nhanh/rủi ro thấp** với thao tác **có thể pause JVM, tốn disk/CPU và làm thay đổi hiện trạng**.
5. Bảo toàn **timestamp, PID/container identity, quyền truy cập và nguồn gốc file** để các nhóm có thể ghép bằng chứng sau sự cố.
6. Thiết kế **runbook và preconfiguration** giúp incident ngắn vẫn có đủ dữ liệu, thay vì đặt toàn bộ hy vọng vào việc chạy lệnh sau khi sự cố đã xảy ra.

**Quy tắc:** không có thứ tự cứng đúng cho mọi incident. Ưu tiên của một bước phụ thuộc vào **khả năng bằng chứng mất đi, giá trị trả lời câu hỏi, thời gian thu, mức ảnh hưởng hệ thống, dung lượng lưu trữ và an toàn dữ liệu**. Khi nghi process chỉ còn vài giây sống, lấy thứ có thể hoàn thành ngay và không làm nó chết sớm hơn.

## 1. Vì sao cần ưu tiên bằng chứng?

Hãy hình dung một JVM bị OOM sau 30 giây:

~~~text
T0     Memory/RSS bất thường bắt đầu
T+5s   Alerts được gửi; JVM còn chạy
T+10s  Người trực xác định đúng container/PID
T+15s  Có thể dump JFR đang ghi, đọc metrics, lấy stack
T+25s  Heap có thể chạm giới hạn, GC thrash
T+30s  OOM killer hoặc platform restart process
T+31s  /proc/PID, thread states, heap sống: không còn truy cập
~~~

Nếu ở T+15s bắt đầu **GC.heap_dump** trên một heap lớn, lệnh có thể mất quá lâu, tăng áp lực disk và ảnh hưởng JVM trong lúc nó đang yếu. Heap dump có thể rất có giá trị với leak, nhưng không phải mặc định là **việc đầu tiên** trên một process sắp bị kết thúc.

Ngược lại, nếu đang thấy **bộ nhớ tăng chậm nhiều giờ**, được phép tạo dump, có đủ disk và thời gian, heap dump đúng thời điểm có thể là bằng chứng quan trọng hơn vài thread dumps. Do đó ưu tiên phải **theo triệu chứng và thời gian** chứ không theo một checklist “luôn chạy mọi lệnh”.

### 1.1. Các loại bằng chứng có vòng đời khác nhau

| Loại bằng chứng | Khi nào mất? | Mức ưu tiên khi instance sắp chết |
| --- | --- | --- |
| **Java thread stack/state**, lock owner, in-flight task | Biến mất khi thread đổi trạng thái/process kết thúc | Rất cao với hang, deadlock, CPU spike |
| **JFR đang chạy** | In-memory buffers và repository của process có thể không còn sau exit/eviction; một số file tồn tại nếu đã flush | Rất cao nếu recording hiện hữu và chứa giai đoạn lỗi |
| **/proc/PID, native thread, RSS, fd, socket/memory maps** trên Linux | Biến mất khi process không còn | Cao khi cần OS/native perspective |
| **Heap object graph tại trạng thái lỗi** | Không thể chụp lại sau GC, restart hoặc sau khi leak không còn | Cao với retention/OOM, nhưng chi phí dump lớn |
| **GC/class histogram** | Snapshot thay đổi qua các chu kỳ GC; cũng có thể làm thay đổi trạng thái | Trung bình–cao tùy triệu chứng và rủi ro |
| **Continuous GC/application logs** | Thường tồn tại qua restart nếu được ship ra ngoài; có thể bị rotate/xóa hoặc chỉ ở ephemeral disk | Thu/đóng băng sớm, nhưng không thay thế live snapshots |
| **Metrics đã đẩy ra hệ thống quan sát** | Tùy retention/scrape period, có thể còn sau process chết | Có thể truy hồi sau nhưng cần ghi đúng window |
| **Fatal-error log, core file, OOM heap dump đã cấu hình** | Được tạo lúc lỗi; có thể ở local disk không bền | Bảo toàn ngay sau sự cố, không mặc định lúc nào cũng được tạo |

**Quan trọng:** Kubernetes Pod UID, container ID và Linux PID đều là danh tính khác nhau. PID có thể được tái sử dụng sau khi process chết. Khi chuyển ca, cần ghi đủ **host, namespace/container, start time, PID** để không vô tình phân tích một JVM khác.

### 1.2. Ba câu hỏi trước khi bấm Enter

1. **Triệu chứng chính cần giải thích là gì?** CPU, hang, heap, RSS native, I/O, crash hay hỗn hợp?
2. **Bằng chứng sẽ còn bao lâu?** Chỉ vài giây trước restart, dưới phút, hoặc còn ổn định hàng chục phút?
3. **Lệnh này có làm hệ thống xấu đi hoặc phá dữ liệu cần thu không?** Stop-the-world, Full GC, heap dump disk I/O, pause lớn, secrets, quota, quyền truy cập?

Nếu câu 2 là “vài giây” và câu 3 là “có thể tốn phút”, nên chọn snapshot giá trị cao nhưng nhanh hơn hoặc dùng recording đã cấu hình, không cố chạy một lệnh nặng bằng mọi giá.

## 2. Quy tắc chọn theo thời gian còn lại

Các khoảng sau là **mốc điều phối minh họa**, không phải cam kết rằng lệnh JVM sẽ hoàn tất trong đúng thời gian:

| Thời gian ước tính còn lại | Mục tiêu | Việc nên làm trước | Việc cần cân nhắc |
| --- | --- | --- | --- |
| **0–15 giây** | Cứu dấu vết khó tái tạo nhất | Xác nhận PID; dump **JFR đã chạy** hoặc lấy **một thread snapshot** tùy triệu chứng; ghi timestamp, trạng thái Pod/process | Tránh khởi chạy heap dump lớn hoặc thu hàng chục chỉ số không liên quan |
| **15–60 giây** | Có snapshot đầu và thêm một góc nhìn | JFR dump + thread/OS metrics hoặc bộ nhớ nhanh theo triệu chứng; ghi lỗi attach | Histogram/heap dump chỉ khi giá trị cao, hệ thống chịu được và có disk |
| **1–5 phút** | Thu chuỗi thời gian và dấu hiệu root cause | Lặp **thread/CPU/GC/OS samples**, JFR, pool metrics; sau đó chọn histogram/NMT và dump có kiểm soát | Không chờ “đủ bộ” rồi mới lưu những snapshot quan trọng |
| **Hơn 5 phút/ổn định** | So sánh trước–sau, phân tích sâu | Baseline, JFR profile đủ khoảng, NMT diff nếu bật, heap dump khi thích hợp, correlation logs/traces | Cân nhắc overhead, bảo mật, backpressure và tần suất thu |

Đôi khi không thể biết sự cố còn bao lâu. Trong trường hợp đó, đánh giá theo **nguy cơ mất instance cao**: restart loop, container memory.current áp sát limit, RSS tăng nhanh, OOM messages hoặc watchdog sắp kill. **Ưu tiên snapshot ngay**, không đợi một bộ biểu đồ đẹp.

**Tính thứ tự bằng “lợi ích trên chi phí”**: bằng chứng nào có khả năng cung cấp câu trả lời quan trọng, sẽ sớm biến mất, thu xong nhanh và ít tác động thì đứng trước. Nếu thao tác tạo dump có khả năng làm OOM/eviction xảy ra sớm hơn, giá trị kỳ vọng của nó giảm.

## 3. Bảng điều phối theo triệu chứng

| Triệu chứng | Đầu tiên, khi còn rất ít thời gian | Sau đó, nếu JVM còn sống | Thu sâu khi có thời gian/tài nguyên |
| --- | --- | --- | --- |
| **Hang/deadlock, request đứng** | **Thread.print -l** hoặc thread dump đang sẵn; ghi PID/time | Lặp thread dump để thấy chờ ổn định; dump JFR đang chạy | JFR ThreadPark/JavaMonitorEnter, lock ownership, queue/pool/DB |
| **CPU spike ngắn** | OS process/thread CPU snapshot và/hoặc **JFR.dump** của recording đã chạy | Lặp CPU-by-thread, stack snapshots, timestamps | JFR ExecutionSample, native profiling phù hợp, code/JIT/GC correlation |
| **GC thrash, heap OOM gần kề** | JFR đã ghi, heap/GC metrics, GC logs và process/cgroup memory snapshot | Histogram nếu chịu được; xác minh heap used sau GC | Heap dump khi có đủ thời gian/disk/quyền, MAT, GC-root paths |
| **Native RSS tăng/container OOM** | RSS/RssAnon/RssFile, Threads, cgroup memory/current/events, OS maps nhanh | **VM.native_memory summary** nếu NMT đã bật, BufferPoolMXBean, fd count | smaps chi tiết, NMT baseline/diff nếu có, native profiler/JNI |
| **I/O/latency spike** | Timestamps, errors/timeout, inflight/queue/pool, JFR có sẵn | Thread dump, socket/file metrics, DNS/DB/network indicators | JFR SocketRead/Write/FileRead/Write, traces và before/after load |
| **Crash/restart đã xảy ra** | Bảo quản logs, hs_err_pid, core, heap dump/JFR đã xuất, Pod events | Timeline OOM/exit code, last state, host/container metrics | Reproduce có preconfigured diagnostics; không thể chụp live JVM đã chết |
| **Classloader/metaspace tăng** | Metaspace/heap overview, JFR/NMT nếu có | Classloader stats, class-load count | Heap dump/class-loader reference paths và NMT detail khi bật sẵn |

**Đây là bảng ưu tiên, không phải mệnh lệnh chạy toàn bộ các lệnh.** Với CPU spike chỉ kéo dài 8 giây, heap dump thường thấp giá trị hơn CPU/JFR snapshot. Với heap retention kéo dài và PID còn ổn định, heap dump có thể là bằng chứng quyết định.

## 4. Hiểu độ nặng của lệnh trước khi thu

Với **HotSpot JDK 21**, tài liệu **jcmd** phân loại *impact* theo lệnh; thực tế phụ thuộc heap size, số thread và tình trạng hệ thống:

| Lệnh / nguồn | Ý nghĩa | Mức tác động cần lưu ý |
| --- | --- | --- |
| **jcmd PID JFR.check** | Xem recording đang chạy | Thường **Low** |
| **jcmd PID JFR.dump** | Xuất recording đang chạy ra file, recording tiếp tục | Thường **Low**, vẫn tốn I/O và có chi phí lưu file |
| **jcmd PID Thread.print -l** | Stack/locks snapshot của threads | **Medium**, có thể nặng khi rất nhiều threads |
| **jcmd PID GC.heap_info** | Tổng quan heap hiện tại | **Medium** theo JDK 21 |
| **jcmd PID VM.native_memory summary** | NMT memory summary khi đã bật | **Medium**; không đo được nếu NMT chưa bật |
| **jcmd PID GC.class_histogram** | Đếm instances/shallow bytes theo class | **High**, phụ thuộc heap và options; có thể kéo theo GC |
| **jcmd PID GC.heap_dump** | Tạo HPROF heap dump | **High**, tốn disk/CPU, mặc định yêu cầu Full GC trừ khi dùng -all |
| **/proc/PID/status, smaps_rollup** | OS memory/thread snapshot trên Linux | Thường nhẹ hơn full heap dump nhưng phụ thuộc quyền và lượng mappings |
| **Core dump/native profiler** | Native state rất sâu | Tác động/kích thước/quyền cao; chỉ khi đủ điều kiện và kế hoạch |

**Không coi mức Low/Medium/High là SLA thời gian cố định.** Khi JVM đã bị stall nặng, attach của jcmd có thể không phản hồi hoặc timeout. Có thể phải dùng dữ liệu **đã phát ra từ trước** (log shipper, JFR file sẵn, metrics, crash artifacts) thay vì chờ attach vô hạn.

### Heap dump có thể làm biến mất hiện trạng cần điều tra

**GC.heap_dump** mặc định yêu cầu một Full GC trước khi dump (HotSpot), ngoại trừ lựa chọn **-all**. Full GC có thể làm thay đổi số object reachable/heap usage và làm gián đoạn ứng dụng. Chế độ -all giữ cả object unreachable, vì vậy việc diễn giải “leak” cũng phải khác.

Không chạy dump chỉ để “thử xem có gì” trong phút cuối của OOM. Hãy xem dung lượng heap, disk free/inode/quota, tốc độ ghi, tình trạng filesystem và sự cho phép của incident commander. Một file HPROF có thể rất lớn và chứa **password, token, dữ liệu khách hàng, chuỗi SQL và object nghiệp vụ**.

## 5. Nền tảng tốt nhất: chuẩn bị trước incident

Một tình huống kéo dài vài giây hiếm khi cho phép bạn bật một profiler mới, chờ dữ liệu rồi dump. **Chuẩn bị** thường có giá trị hơn cố gắng thao tác thủ công trong lúc sự cố.

### 5.1. Ghi log và metrics liên tục

Ưu tiên đã có từ trước:

- GC logs với timestamps, rotation, shipping ra kho bền vững, theo chính sách chi phí.
- Application errors, request latency (p95/p99), success/error/timeout, inflight/queue depth và các indicators I/O quan trọng.
- JVM heap/non-heap, thread count, JIT/GC counters và container RSS/memory.current, CPU throttling/restarts.
- Host/container event timeline, OOMKilled, exit code và timestamps chính xác.
- Pod UID/container ID, version/build ID và deployment change events.

Nếu scrape interval là 30 giây mà spike chỉ 3 giây, metrics có thể **không nhìn thấy đỉnh**. Cân nhắc số liệu có độ phân giải phù hợp hoặc recording liên tục; không ép một sparse sample thành kết luận tuyệt đối.

### 5.2. Bật JFR vòng quay có giới hạn

Trong HotSpot, có thể tạo một recording khi JVM khởi động bằng tùy chọn **-XX:StartFlightRecording** với settings phù hợp. Một ví dụ khái niệm:

~~~bash
java \
  "-XX:StartFlightRecording=name=continuous,settings=default,maxage=30m,maxsize=256m,disk=true" \
  -jar app.jar
~~~

**Đây chỉ là ví dụ startup cho một ứng dụng đã có app.jar.** Bảo đảm heap/disk/resources đủ; xác minh tùy chọn đúng với JVM/vendor và policies. **maxage/maxsize** giới hạn lượng dữ liệu recording giữ lại. Không mặc định default.jfc thu mọi event hữu ích; nếu cần socket latency/monitor stacks phải kiểm tra effective settings/threshold.

Khi incident xảy ra, nếu recording **đã chạy đủ lâu**, bạn có thể **JFR.dump** mà không phải đợi recording mới tạo dữ liệu. Bắt đầu JFR **lúc T+20s** không thể tái tạo sự kiện CPU spike xảy ra **T+5s**.

### 5.3. Chuẩn bị OOM/crash artifacts

Ví dụ các JVM options phải được xét trước khi bật:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure/diagnostics
-XX:ErrorFile=/secure/diagnostics/hs_err_pid%p.log
~~~

Những options này được cung cấp trong Java command line thực tế, không phải ba lệnh shell độc lập. **HeapDumpOnOutOfMemoryError** tạo heap dump khi JVM ném **Java OutOfMemoryError** trong những điều kiện áp dụng, **không bảo đảm** tạo được dump nếu **kernel/container OOM killer gửi SIGKILL** hoặc disk không đủ.

**-XX:ErrorFile** áp dụng cho fatal error log phù hợp, không có nghĩa mọi exception Java sẽ tạo hs_err. Core dump cần cấu hình OS riêng và kiểm soát dữ liệu nhạy cảm.

**Có preconfiguration không có nghĩa mọi lần crash đều tạo file.** Sau sự cố vẫn phải kiểm tra file thực, exit reason, đường dẫn và upload/retention.

## 6. Runbook khởi đầu trên Linux: xác minh danh tính và đóng băng các số liệu nhẹ

Bước này dành cho Java process đang sống, tại host/container có **jcmd** và quyền truy cập. Không mặc định chạy từ một container khác sẽ nhìn thấy cùng PID namespace. Thay PID=12345 bằng số thật, và đặt một đường dẫn **chỉ người có quyền mới đọc được**.

~~~bash
PID=12345
umask 077
OUT="/secure/diagnostics/incident-$(date -u +%Y%m%dT%H%M%SZ)-$PID"
mkdir -p "$OUT"

date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/utc-time.txt"
ps -o pid,ppid,lstart,etime,rss,vsz,nlwp,comm -p "$PID" \
  > "$OUT/process-identity.txt" 2>&1

# Các file này chỉ có trên Linux, có thể bị hạn chế bởi /proc permissions:
cat "/proc/$PID/status" > "$OUT/proc-status.txt" 2>&1
cat "/proc/$PID/limits" > "$OUT/proc-limits.txt" 2>&1
~~~

Lệnh **ps** và /proc giúp xác nhận process còn sống, thời điểm bắt đầu, RSS/VSZ và số native threads. **Không xem PID là danh tính bền vững**; nếu process restart và PID thay đổi, kết quả các lần sau không nên gộp như cùng JVM. Ghi thêm **host, container ID/Pod UID, application version, namespace và incident ID** trong hệ thống quản lý incident.

**Tránh tự động chép command line đầy đủ vào artifact chia sẻ rộng**: command line/environment có thể chứa secrets. Không chụp /proc/PID/environ hoặc heap dump lên chỗ công khai. Ví dụ này **không tự tạo cgroup identity** và không kiểm chứng quyền ghi vào /secure/diagnostics; đó phải là thư mục tồn tại hoặc có quyền tạo trong môi trường của bạn.

### Khi attach hoạt động và JFR đã chạy

~~~bash
jcmd "$PID" JFR.check > "$OUT/jfr-check.txt" 2>&1

# Chỉ khi JFR.check xác nhận có recording đang chạy:
jcmd "$PID" JFR.dump filename="$OUT/incident.jfr" \
  > "$OUT/jfr-dump-result.txt" 2>&1
~~~

Theo tài liệu JDK 21, **JFR.dump ghi file mà không dừng recording đang chạy**. Nếu nhiều recordings, có thể dùng **name=...** để chọn recording phù hợp. Việc JFR.dump báo thành công chưa thay thế bước **xác minh file tồn tại, kích thước hợp lệ, và thời gian recording phủ sự cố**.

~~~bash
ls -lh "$OUT/incident.jfr"
jfr summary "$OUT/incident.jfr"
~~~

**Không dùng JFR.start rồi tuyên bố đã cứu được 30 giây trước khi start.** Một recording mới chỉ bắt đầu thu từ thời điểm bắt đầu, còn những event đã mất thì không hồi phục.

### Khi vấn đề chính là hang/lock contention

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/threads-1-time.txt"
jcmd "$PID" Thread.print -l > "$OUT/threads-1.txt" 2>&1

# Nếu incident chưa biến mất, chụp lần nữa để so sánh:
sleep 5
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/threads-2-time.txt"
jcmd "$PID" Thread.print -l > "$OUT/threads-2.txt" 2>&1
~~~

Nếu chỉ có 5–10 giây, ưu tiên **một** thread dump trước, không chờ đủ 3 snapshots. Nếu còn hơn một phút, nhiều lần cách nhau 5–10 giây giúp phân biệt một thread chỉ chờ ngắn với deadlock/blocked queue kéo dài. Thread.print trên JDK 21 hiển thị thread stacks trong phạm vi lệnh hỗ trợ; với **virtual threads**, nội dung dump và phạm vi visibility phụ thuộc JDK và command. Khi cần dump nhiều virtual threads, nghiên cứu **Thread.dump_to_file** hoặc JFR ở JDK hỗ trợ, không giả định một output Thread.print liệt kê toàn bộ virtual threads.

### Khi vấn đề chính là CPU spike

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/cpu-1-time.txt"

# Linux: snapshot native threads, CPU và trạng thái tại thời điểm lấy mẫu:
ps -L -p "$PID" -o pid,tid,psr,stat,pcpu,comm \
  > "$OUT/os-threads-cpu.txt" 2>&1

# Bổ sung stack Java trong lúc spike còn xảy ra:
jcmd "$PID" Thread.print > "$OUT/cpu-thread-stacks.txt" 2>&1
~~~

OS per-thread CPU và Java stack phải được chụp **gần cùng timestamp**, nhưng CPU% từ ps là phép đo theo semantics riêng, không phải profile chính xác từng method. Khi cần hotspot methods, **JFR ExecutionSample** từ recording đã chạy thường hữu ích hơn một thread dump đơn lẻ. Nếu CPU spike biến mất sau 3 giây, có thể không đủ thời gian tạo recording mới có ý nghĩa.

## 7. Triệu chứng bộ nhớ: lựa chọn theo rủi ro và thời gian

### 7.1. Heap tăng/GC thrashing gần OOM

Khi process vẫn sống, ưu tiên:

1. **GC logs/metrics đang có**, JFR dump nếu recording đã chạy; lấy **memory/GC snapshot**.
2. Ghi **RSS/container memory, heap used/committed, last GC, restart policy** để phân biệt Java heap OOM với cgroup OOM.
3. Nếu JVM còn chạy và có quyền/khả năng chịu pause, chọn **GC.class_histogram** để biết class nào chiếm instance/shallow bytes.
4. Chỉ khi **heap retention** là nghi vấn quan trọng và có đủ disk/time/authorization, tạo **GC.heap_dump**; lưu lại khi nào dump, có Full GC hay không, file size và tính bảo mật.
5. Sau incident, mở HPROF bằng MAT để xem **Dominator Tree, retained size, Paths to GC Roots**. Không kết luận leak từ histogram một lần.

Các lệnh có mức tác động tăng dần, không nên chạy vô điều kiện theo chuỗi:

~~~bash
jcmd "$PID" GC.heap_info > "$OUT/heap-info.txt" 2>&1

# High impact; chỉ thực hiện sau khi đánh giá rủi ro:
jcmd "$PID" GC.class_histogram > "$OUT/class-histogram.txt" 2>&1

# High impact, có thể gây Full GC; tạo file rất lớn:
jcmd "$PID" GC.heap_dump "$OUT/heap.hprof" \
  > "$OUT/heap-dump-result.txt" 2>&1
~~~

**Không có luật “cần phải chạy heap_dump trước khi chết”.** Nếu process chỉ còn 10 giây và dump chắc chắn vượt disk/time budget, hãy cứu các chỉ số nhẹ, JFR đã chạy và bảo toàn logs. Nếu ngược lại đây là cơ hội hiếm để bắt một leak chỉ xuất hiện một lần, và resources cho phép, quyết định dump sớm có thể có giá trị cao hơn các snapshot ít liên quan.

### 7.2. Native RSS tăng mà heap không tăng

Lấy OS metrics vì đây là phần có thể biến mất rất nhanh khi process exit:

~~~bash
grep -E '^(VmSize|VmRSS|RssAnon|RssFile|RssShmem|Threads):' \
  "/proc/$PID/status" > "$OUT/memory-status.txt" 2>&1

# Linux kernels có smaps_rollup:
cat "/proc/$PID/smaps_rollup" \
  > "$OUT/smaps-rollup.txt" 2>&1
~~~

Tiếp theo, nếu **NMT đã bật từ khi JVM khởi động**:

~~~bash
jcmd "$PID" VM.native_memory summary scale=MB \
  > "$OUT/nmt-summary.txt" 2>&1
~~~

- **NMT** ghi các allocations do HotSpot theo dõi, chia reserved/committed; không phải toàn bộ native allocations của JNI/third-party libraries, và không trực tiếp bằng RSS.
- **/proc/PID/status**: VmRSS là resident; VmSize là virtual address space; RssAnon/RssFile giúp phân biệt anonymous/file-backed ở mức OS.
- **smaps_rollup**: RSS/PSS/Private/Shared; tùy kernel và quyền, có thể không truy cập được.
- **NMT chưa bật từ startup**: không thể bật NMT ở mức summary/detail giữa chừng chỉ bằng jcmd. Hãy ghi “NMT unavailable”, dùng OS/process metrics, BufferPoolMXBean và kế hoạch thu cho lần tái hiện.
- **NMT baseline/diff** chỉ có ý nghĩa khi có baseline từ trước và các lần đo sau; không thể “diff về quá khứ” nếu mới đặt baseline sau incident.

Nếu cgroup memory.current tăng nhưng process RSS không tương ứng, đừng quy mọi byte của cgroup cho Java PID: có thể có page cache, kernel accounting và process khác trong cgroup.

## 8. Triệu chứng I/O và độ trễ: thu đúng thời điểm, không chỉ đúng công cụ

Khi p99 latency tăng đột ngột nhưng vẫn có throughput:

**Trong vài giây đầu**, lấy timestamp, request success/error/timeout, inflight, queue length, connection pool active/pending, cgroup CPU throttling và JFR đang chạy (nếu có). Đó là bức tranh cho biết bottleneck có đang diễn ra trong khoảng lỗi không.

Nếu kéo dài đủ lâu:

- Lặp thread dumps để kiểm tra threads chờ I/O/lock/park hoặc thread pool bị cạn.
- Đọc JFR **jdk.SocketRead**, **jdk.SocketWrite**, **jdk.FileRead**, **jdk.FileWrite**, **jdk.ThreadPark**, **jdk.JavaMonitorEnter**, khi các event được thu.
- Đối chiếu DB connection pool, downstream response time, network RTT/retransmits, disk queue và OS metrics.
- Ghi **cùng khoảng thời gian** client/server latency và JFR. Một SocketRead 500 ms có thể thuộc một request cụ thể; không thể suy toàn bộ p99 request từ event này mà thiếu correlation.

**Không bắt đầu với heap dump** chỉ vì request chậm. Nếu thread dump/JFR cho thấy I/O wait hoặc lock contention, heap dump thường không phải công cụ có giá trị cao nhất trong sự cố ngắn.

**Không đánh đồng Count=0 trong JFR với “không có I/O”**: event có thể bị disabled, threshold loại bỏ các thao tác ngắn hoặc recording không phủ thời gian sự cố.

## 9. Sau khi process đã chết: đổi chiến lược ngay

Một JVM không còn tồn tại thì không thể chụp lại live thread stack, heap graph hay /proc/PID của nó. Đừng lặp vô hạn **jcmd PID** sau khi container bị restart: PID có thể không còn, hoặc PID mới trỏ vào process khác.

Quy trình:

1. Ghi **exit timestamp**, exit code/reason (ví dụ OOMKilled nếu nền tảng báo), Pod UID/container ID, deployment/build ID và host/node.
2. Bảo toàn **stdout/stderr, GC logs, application logs, platform events, last metrics**, không để rotate hoặc eviction xóa dữ liệu.
3. Tìm **hs_err_pid**, core, HPROF do **HeapDumpOnOutOfMemoryError**, JFR file đã dump hoặc repository/chunk còn trên disk; không giả định file tự xuất hiện.
4. Kiểm tra disk path và quyền; **copy artifact trước khi node/container bị dọn** nếu chính sách cho phép.
5. Khi tái hiện, cấu hình continuous JFR, GC log shipping, OOM/crash artifacts và alerts/automation thu snapshot ở ngưỡng sớm hơn.
6. Đưa ra **kết luận có giới hạn** nếu thiếu bằng chứng; không bịa thread dump hay HPROF từ logs của JVM mới.

Lưu ý: **OOMKilled (kernel SIGKILL)** không giống Java ném **OutOfMemoryError**. Cơ chế tạo heap dump của JVM có thể không kịp chạy khi bị SIGKILL, kể cả đã bật option.

## 10. Đặt thứ tự theo giá trị của từng bằng chứng

Một cách lập kế hoạch đơn giản là chấm từng hành động theo bốn tiêu chí:

| Tiêu chí | Câu hỏi | Nếu câu trả lời là “cao” |
| --- | --- | --- |
| **Tính mong manh** | Dữ liệu có biến mất ngay khi restart/GC/stack chuyển trạng thái? | Thu sớm |
| **Độ liên quan** | Dữ liệu có trực tiếp giúp phân biệt các nguyên nhân đang nghi? | Thu sớm |
| **Chi phí/ảnh hưởng** | Lệnh có gây pause, Full GC, tốn disk, timeout, dữ liệu nhạy cảm? | Hoãn hoặc cần phê duyệt |
| **Xác suất hoàn tất** | Với thời gian còn lại, lệnh có khả năng trả kết quả? | Ưu tiên lệnh có thể hoàn tất |

Ví dụ:

- Với **deadlock 8 giây**, một thread dump có khả năng trả lời cao, heap dump vừa chậm vừa lệch chủ đề.
- Với **heap leak chỉ lộ một lần** và process còn 10 phút, HPROF có thể đáng chi phí hơn việc lấy thêm 20 CPU snapshots.
- Với **container sắp OOMKilled**, lấy /proc/cgroup snapshots và JFR đã chạy có thể khả thi hơn heap dump 6 GiB.
- Với **CPU cao nhưng không có JFR đang chạy**, một per-thread CPU snapshot + thread dump sớm có giá trị hơn khởi động JFR rồi chờ vài phút.

**Đừng cứng nhắc cố “đủ bộ”.** Sau mỗi hành động, đánh giá lại: sự cố còn không, thời gian còn bao lâu, bằng chứng quan trọng nhất đã lưu an toàn chưa và thao tác tiếp theo có đe dọa instance không?

## 11. Mẫu lập kế hoạch điều phối bằng Java 17+

Chương trình sau **không chạy lệnh chẩn đoán**, chỉ in thứ tự gợi ý theo triệu chứng và urgency band. Nó dùng một quy tắc minh họa để người học tập ra quyết định; **không dự đoán thời gian thực** của heap dump hay lệnh jcmd và không thay thế runbook có quyền truy cập an toàn.

Tạo file **CapturePriorityDemo.java**:

~~~java
import java.util.List;

public final class CapturePriorityDemo {
    enum Symptom { HANG, CPU, HEAP_OOM, NATIVE_RSS }

    private static List<String> candidates(Symptom symptom) {
        return switch (symptom) {
            case HANG -> List.of(
                    "verify process identity",
                    "one thread dump",
                    "dump existing JFR",
                    "repeat thread dump");
            case CPU -> List.of(
                    "verify process identity",
                    "per-thread CPU snapshot",
                    "dump existing JFR",
                    "correlate repeated samples");
            case HEAP_OOM -> List.of(
                    "verify process identity",
                    "dump existing JFR",
                    "lightweight heap and cgroup snapshot",
                    "consider heap dump only after risk check");
            case NATIVE_RSS -> List.of(
                    "verify process identity",
                    "OS RSS and cgroup snapshot",
                    "NMT summary if pre-enabled",
                    "repeat memory comparison");
        };
    }

    private static void show(Symptom symptom, int secondsLeft) {
        int maximum = secondsLeft <= 15 ? 2
                : secondsLeft <= 60 ? 3 : 4;

        List<String> actions = candidates(symptom);
        System.out.println(symptom + " " + secondsLeft + "s:");
        for (int i = 0; i < Math.min(maximum, actions.size()); i++) {
            System.out.println("  " + (i + 1) + ". " + actions.get(i));
        }
    }

    public static void main(String[] args) {
        show(Symptom.HANG, 12);
        show(Symptom.HEAP_OOM, 45);
        show(Symptom.CPU, 180);
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac CapturePriorityDemo.java
java CapturePriorityDemo
~~~

**Stdout chính xác:**

~~~text
HANG 12s:
  1. verify process identity
  2. one thread dump
HEAP_OOM 45s:
  1. verify process identity
  2. dump existing JFR
  3. lightweight heap and cgroup snapshot
CPU 180s:
  1. verify process identity
  2. per-thread CPU snapshot
  3. dump existing JFR
  4. correlate repeated samples
~~~

Đây là ví dụ **priority selection**, không phải benchmark. Nếu HEAP_OOM nhưng chưa có JFR chạy, **bỏ qua bước JFR.dump không khả dụng** và lấy bằng chứng tiếp theo. Nếu HANG và JVM không phản hồi attach, chuyển sang nguồn logs/metrics hoặc phương án chụp ngoài process theo runbook.

Không nhầm giá trị secondsLeft trong demo với SLA của lệnh. Một thao tác “low impact” vẫn có thể treo do môi trường, quyền, I/O, mutex hoặc JVM đã ngừng phản hồi.

## 12. Thử hai tình huống có cùng thời gian nhưng thứ tự khác nhau

### Tình huống A — 30 giây trước khi instance bị thay

Dấu hiệu: p99 API tăng lên 15 giây, DB pool chờ, CPU không cao, Pod được platform báo sẽ restart trong 30 giây.

**Thứ tự hợp lý:**

1. Ghi process/container identity, timestamp, pool pending, inflight và request errors.
2. Chụp một thread dump để thấy threads nằm tại pool acquire/network read.
3. Dump **JFR đã chạy**, nếu có, để giữ timeline trước thời điểm lỗi.
4. Nếu còn thời gian, lấy thêm thread snapshot và metrics downstream.

**Không hợp lý:** tạo heap dump 4 GiB trước khi lấy bất kỳ lock/pool/thread evidence nào. HPROF có thể không liên quan và làm mất cửa sổ thu thập.

### Tình huống B — 30 giây, memory.current tăng sát limit

Dấu hiệu: Java heap used tương đối ổn nhưng RSS/RssAnon và cgroup memory.current tăng nhanh; platform có thể OOMKill.

**Thứ tự hợp lý:**

1. Ghi identity, process memory, cgroup current/max/events, native thread count.
2. Nếu NMT bật sẵn, lấy nhanh NMT summary; JFR đã chạy thì dump để giữ timeline.
3. Nếu chưa NMT, ghi rõ “unavailable”; xem BufferPoolMXBean nếu endpoint metrics đã có.
4. Tập trung bảo toàn log/OOM platform events trước khi process biến mất.

**Không hợp lý:** chạy class histogram liên tục để tìm “Java object leak” khi heap không tăng và native RSS đang là vấn đề. Histogram có thể tốn thời gian và không giải thích allocations ngoài heap.

### Tình huống C — còn 20 phút, nghi heap leak có thể tái hiện

Dấu hiệu: sau mỗi workload cycle, heap used sau GC tăng, không có restart gấp, disk đủ và có sự cho phép.

**Thứ tự hợp lý:**

1. Baseline heap/GC metrics, JFR và workload timestamps.
2. Chụp heap histogram/HPROF ở mốc có retention, cân nhắc Full GC semantics.
3. Nếu có thể, tái hiện và lấy snapshot ở mốc thứ hai dưới tải tương đương.
4. Phân tích MAT Dominator Tree, retained sets/GC roots và so sánh theo vòng đời nghiệp vụ.

Với tình huống này, heap dump có giá trị chẩn đoán lớn hơn việc cố theo đuổi một thread dump bất kỳ.

## 13. Chất lượng, độ tin cậy và tính an toàn của bằng chứng

### 13.1. Gắn timestamp và provenance

Mỗi artifact nên ghi:

- Incident ID; host, Pod UID/container ID, PID và JVM start time nếu có.
- JDK/vendor/version, application version/build, command/tool version.
- **UTC timestamp** lúc bắt đầu/kết thúc thu, file name, config/options.
- Time window của JFR, GC log, metrics; timezone, clock skew giữa hosts nếu liên quan.
- Lệnh chạy thành công hay lỗi, exit status, quyền/namespace.
- Kích thước file, hash khi cần chain of custody, vị trí lưu trữ bền vững.

Nếu lấy nhiều artifacts, tạo tên riêng thay vì ghi đè file cũ; không để lần thu thứ hai xóa evidence lần thứ nhất. **Data incompleteness** phải được báo rõ: JFR chỉ 10 giây cuối, thread dump một mốc, smaps chưa thu, NMT disabled, heap dump thất bại vì thiếu disk.

### 13.2. Quyền truy cập và dữ liệu nhạy cảm

Thread dump có thể chứa class/method names và thông tin vận hành; heap dump/HSPROF, JFR và crash core có thể chứa thông tin nhạy cảm. Không tải lên chat công khai hoặc hệ thống không được phê duyệt. Dùng **umask 077**, thư mục riêng, access control, encryption/retention và quy trình redaction phù hợp.

**Không tự động chạy lệnh phá hủy** như kill -9, GC.run hay restart để “dễ chụp” trừ khi có runbook và thẩm quyền. Hành động khắc phục có thể làm biến mất nguyên nhân và ảnh hưởng khách hàng; nếu phải restart, ưu tiên dữ liệu nhẹ đã thu được rồi phối hợp với incident commander.

### 13.3. Tránh tình huống thu thập chính là thủ phạm

- JFR event settings quá dày, logging quá nhiều hoặc stack traces có thể thêm overhead.
- Histogram/heap dump có tác động lớn, cần disk space và thời gian.
- NMT có overhead, phải bật trước bằng flags phù hợp.
- smaps đầy đủ trên process có rất nhiều mappings có thể tốn tài nguyên, nên smaps_rollup trước nếu đủ.
- Không đọc/ghi toàn bộ /proc và đổ vài GB artifacts ra filesystem đang sát quota; có thể kích hoạt eviction hoặc OOM khác.
- Nếu SRE/security policy cấm attach trên production, sử dụng metrics/JFR/logs đã được phê duyệt; không vượt quyền.

## 14. Cách báo cáo sau sự cố

Một báo cáo thu thập hiệu quả nên có:

**A. Quyết định tại thời điểm incident:** “CPU spike, dự kiến còn 10–15s; ưu tiên OS thread CPU + JFR đang chạy, hoãn heap dump vì không liên quan và rủi ro cao”.

**B. Artifacts thực tế:** “JFR đã dump từ T−30s tới T+5s; thread dump ở 09:10:12; process RSS/cgroup ở 09:10:13; thiếu snapshot khác do process restart lúc 09:10:15”. Đây là cách trình bày minh họa.

**C. Giới hạn evidence:** “Không có heap dump; NMT chưa bật; JFR ExecutionSample sampling; không đủ bằng chứng để kết luận chắc native leak”.

**D. Next action dựa trên gaps:** thêm rolling JFR, GC log shipping, trigger thu sớm hơn, cgroup OOM alert, chuẩn bị đĩa dump hoặc tái hiện trong staging.

Đừng viết **“đã kiểm tra không có leak”** khi chỉ có thread dump. Đừng viết **“không có deadlock”** nếu chỉ có một stack snapshot sau khi spike kết thúc. **Bằng chứng tốt phải được giới hạn đúng theo những gì thật sự thu được và thời điểm thu.**

## 15. Sai lầm phổ biến

1. **Chạy heap dump đầu tiên cho mọi triệu chứng**: chậm, High impact và có thể không liên quan.
2. **Đợi incident hết rồi mới tạo recording**: JFR.start không tái tạo timeline đã mất.
3. **Chỉ lấy một thread dump sau khi hang đã tự hết**: không phản ánh trạng thái lúc lỗi.
4. **Không ghi PID/Pod UID/start time**: dễ ghép nhầm JVM sau restart hoặc PID reuse.
5. **Dừng ghi JFR để dump** dù không cần: JFR.dump thông thường vẫn cho recording chạy tiếp.
6. **Tưởng JFR.dump luôn thành công**: không có recording, không có quyền hoặc disk đầy có thể thất bại.
7. **Cho rằng NMT có thể bật muộn rồi diff về trước sự cố**: không đúng.
8. **Dùng GC.class_histogram làm bằng chứng native RSS leak**: histogram Java heap không kiểm kê toàn bộ native memory.
9. **Coi code cache reserved, heap committed và RSS là cùng đại lượng**: không so trực tiếp được.
10. **Tự động Full GC trước khi giữ bằng chứng**: có thể thay đổi heap và kéo dài pause.
11. **Coi absence of event là absence of phenomenon**: recording settings/threshold/coverage có thể không đủ.
12. **Không kiểm tra filesystem**: dump thất bại giữa chừng, chiếm hết quota và làm hệ thống tệ hơn.
13. **Tắt/restart instance trước khi giữ một snapshot giá trị cao**: bằng chứng sống mất đi.
14. **Lặp jcmd tới PID đã chết**: mất thời gian, có nguy cơ PID mới trỏ vào process khác.
15. **Đếm đủ số file nhưng không kiểm tra nội dung/time window**: có file rỗng hoặc recording không bao phủ incident.
16. **Không phân biệt OOMKilled và Java OutOfMemoryError**: ảnh hưởng khả năng có HPROF.
17. **Đem dump chứa secrets chia sẻ không đúng quyền**: rủi ro riêng tư và bảo mật.
18. **Thu dữ liệu nhiều hơn khả năng phân tích, không có hypothesis**: vừa tăng overhead vừa bỏ lỡ evidence quan trọng.

## 16. Bài tự kiểm tra

**Câu 1.** Còn khoảng 8 giây trước restart; JVM bị hang, không có bằng chứng heap tăng. Nên chọn thread dump hay heap dump trước?  
**Đáp án:** ưu tiên một thread dump/lock snapshot nhanh và identity; heap dump vừa chi phí cao vừa ít liên quan.

**Câu 2.** CPU spike vừa kết thúc, sau đó mới gọi JFR.start. Có thu lại stack samples của spike trước đó được không?  
**Đáp án:** không. Recording mới chỉ thu từ lúc bắt đầu; nếu trước đó có rolling JFR hoặc profiling khác mới có cơ hội giữ dữ liệu quá khứ.

**Câu 3.** Container bị OOMKilled bằng SIGKILL dù đã bật HeapDumpOnOutOfMemoryError. Có chắc tồn tại HPROF không?  
**Đáp án:** không. Cần kiểm tra file thực tế; kernel kill có thể không tạo Java OutOfMemoryError và JVM không còn thời gian dump.

**Câu 4.** NMT chưa bật khi startup, còn 40 giây trước restart. Có dùng VM.native_memory summary.diff để biết native leak hai giờ qua không?  
**Đáp án:** không. NMT không thể theo dõi ngược các allocation quá khứ, và baseline/diff yêu cầu pre-enabled tracking cùng baseline trước đó.

**Câu 5.** JFR.dump đã tạo file nhưng jfr summary cho thấy thời gian recording trước incident 30 phút. Có thể dùng nó để suy CPU spike hiện tại không?  
**Đáp án:** không đủ, cần recording phủ đúng timestamp. File có tên “incident.jfr” không chứng minh tính liên quan.

**Câu 6.** Với RSS tăng, Java heap ổn định và RssAnon tăng, có nên chạy Java heap histogram nhiều lần trước khi xem /proc và NMT không?  
**Đáp án:** thường không. Ưu tiên OS/native evidence, NMT nếu bật từ đầu, rồi mới lựa chọn công cụ heap khi có giả thuyết phù hợp.

**Câu 7.** Hệ thống còn chạy 20 phút, có leak heap tái hiện và đủ disk. Chụp heap dump có hợp lý không?  
**Đáp án:** có thể hợp lý, sau khi cân nhắc High impact/Full GC, quyền truy cập, dung lượng và thời điểm tốt nhất để giữ graph có retention.

**Câu 8.** Có thread dump, GC metrics, JFR không bao phủ incident và không có application logs vì disk rotate. Báo cáo có được khẳng định root cause chắc chắn không?  
**Đáp án:** chỉ nếu evidence còn lại thực sự đủ; nếu không, phải nêu mức độ bất định, gaps và cải thiện preconfiguration.

## Tài liệu tham khảo

- [Oracle JDK 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): impact, JFR.check/JFR.dump, Thread.print, GC.heap_info/class_histogram/heap_dump và VM.native_memory.
- [Oracle JDK 21 — Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html): thu thread traces, JFR, core, logs và các artifacts trước khi restart.
- [Oracle JDK 21 — Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html): JFR khi leak diễn ra và heap dump khi JVM còn sống.
- [Oracle JDK 21 — Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): maxAge/maxSize, dump, recording lifecycle và giới hạn retention.
- [Oracle JDK 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): StartFlightRecording, HeapDumpOnOutOfMemoryError, HeapDumpPath và ErrorFile.
- [Linux man-pages — proc_pid_status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): VM RSS, virtual memory, native thread count, process fields.
- [Linux kernel — proc filesystem documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html): /proc/PID/smaps, smaps_rollup và các số liệu process.
