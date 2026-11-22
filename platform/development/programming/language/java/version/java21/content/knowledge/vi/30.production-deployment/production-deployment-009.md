# Runbook thu thập thread dump, JFR và GC log khi xảy ra sự cố

## 1. Mục tiêu và phạm vi

Khi ứng dụng Java 21 chậm, treo, tăng CPU, tăng latency hoặc có dấu hiệu áp lực bộ nhớ, cần thu thập bằng chứng runtime trước khi restart hoặc thay đổi cấu hình. Ba nguồn dữ liệu thường bổ sung cho nhau:

- **Thread dump** cho biết platform thread và/hoặc virtual thread đang chạy, chờ hoặc bị block tại stack trace nào.
- **Java Flight Recorder (JFR)** ghi lại các sự kiện runtime theo thời gian như CPU sample, thread park, monitor contention, allocation và GC.
- **GC log** cho biết chu kỳ thu gom, pause, heap occupancy và hoạt động của garbage collector.

Runbook này hướng dẫn thu thập trên HotSpot/OpenJDK Java 21 bằng `jcmd`, `jfr` và Unified Logging. Cần xác minh đúng PID, quyền truy cập và filesystem của JVM đích. Trong container, lệnh và đường dẫn phải được thực hiện trong đúng PID namespace và filesystem namespace.

Mục tiêu là thu thập đủ bằng chứng để phân tích, không phải chạy mọi diagnostic command trên mọi incident. Chọn dữ liệu theo triệu chứng và giữ thời gian recording/số snapshot ở mức có kiểm soát.

## 2. Nguyên tắc trước khi thu thập

1. Ghi lại thời điểm bắt đầu incident theo UTC và múi giờ vận hành.
2. Xác định service, host/container, pod, PID, image digest, JDK vendor/build và phiên bản ứng dụng.
3. Nếu process còn hoạt động, ưu tiên thu thập thread dump/JFR trước khi restart; restart có thể làm mất trạng thái và dữ liệu trong bộ nhớ.
4. Dùng cùng effective user đã khởi chạy JVM để attach bằng `jcmd`.
5. Chọn thư mục output có quyền ghi và đủ dung lượng; với container, kiểm tra filesystem bên trong container.
6. Không thu thập lặp vô hạn hoặc tạo nhiều recording nặng cùng lúc trên process đang quá tải.
7. Lưu command, timestamp, kết quả và mọi lỗi thu thập để người khác có thể tái hiện quy trình.
8. Bảo vệ artifact: thread dump, JFR và command line có thể chứa tên class nội bộ, endpoint, tên người dùng, SQL hoặc thông tin nhạy cảm.

Nếu có nguy cơ OOM hoặc process sắp bị hệ thống kill, ưu tiên thu thập nhanh những dữ liệu có giá trị cao nhất. Không để hoạt động điều tra làm trì hoãn việc khôi phục dịch vụ.

## 3. Xác định JVM và kiểm tra quyền attach

Liệt kê các JVM mà `jcmd` nhìn thấy:

```bash
jcmd -l
```

Sau khi xác định PID, kiểm tra runtime:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

Các lệnh này giúp xác nhận phiên bản JVM và cấu hình khởi động. `VM.command_line` có thể chứa secret nếu ứng dụng truyền credential qua argument; hãy rà soát và che thông tin nhạy cảm trước khi lưu hoặc chia sẻ.

Kiểm tra các diagnostic command mà JVM đích hỗ trợ:

```bash
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help Thread.dump_to_file
jcmd <pid> help JFR.start
```

Nếu attach thất bại, kiểm tra:

- `jcmd` đang chạy trên cùng host hoặc trong đúng container/PID namespace.
- User/group có quyền attach vào process.
- PID chưa thay đổi do process restart.
- JVM đích có phải runtime tương thích với công cụ đang dùng không.
- Container có đủ dung lượng và quyền ghi vào thư mục output không.

Trong Kubernetes hoặc Docker, PID nhìn từ host có thể khác PID bên trong container. Khi không chắc, chạy `jcmd -l` bên trong container hoặc dùng công cụ quản lý container để xác định PID theo namespace mà JVM nhìn thấy.

## 4. Tạo thư mục và đặt tên artifact

Tạo thư mục riêng cho từng incident, có timestamp và tên service. Ví dụ trên Linux:

```bash
INCIDENT_DIR=/var/tmp/java-incident-20261116T143000Z
mkdir -p "$INCIDENT_DIR"
```

Chọn filesystem có đủ dung lượng. Dump của ứng dụng có hàng chục nghìn virtual thread hoặc recording JFR dài có thể tạo file lớn. Tránh ghi vào filesystem ephemeral nhỏ của container nếu dữ liệu cần được giữ sau khi pod bị thay thế.

Đặt tên file thể hiện loại dữ liệu, PID và thời điểm:

```text
thread-platform-<pid>-<timestamp>.txt
thread-virtual-<pid>-<timestamp>.txt
thread-virtual-<pid>-<timestamp>.json
incident-<pid>-<timestamp>.jfr
gc.log
metadata.txt
```

Ghi timestamp UTC cho mỗi lần thu thập. Đồng bộ thời gian host/container và hệ thống log/tracing để có thể đối chiếu các sự kiện.

## 5. Thu thập thread dump cho platform thread

`Thread.print` in thread dump truyền thống ra output của `jcmd`. Dùng `-l` để yêu cầu thêm thông tin về các `java.util.concurrent` lock mà command hỗ trợ:

```bash
jcmd <pid> Thread.print -l > "$INCIDENT_DIR/thread-platform-<pid>-1.txt"
```

Dump này hữu ích để xem:

- Thread state như `RUNNABLE`, `BLOCKED`, `WAITING` và `TIMED_WAITING`.
- Stack trace của platform thread.
- Monitor và synchronizer liên quan đến việc chờ/giữ lock trong phạm vi thông tin command cung cấp.
- Nhóm thread cùng chờ ở database, HTTP client, executor, queue hoặc đoạn code ứng dụng.

Một thread ở `WAITING` không tự động có nghĩa là deadlock. Cần xem stack trace, lock ownership, tài nguyên đang chờ và khả năng tiến triển của các thread khác.

### 5.1. Lấy nhiều snapshot

Một dump đơn lẻ chỉ là ảnh chụp trạng thái tại một thời điểm. Khi điều tra thread bị kẹt, lấy khoảng ba snapshot cách nhau 10–15 giây, tùy mức tải và mức độ khẩn cấp:

```bash
jcmd <pid> Thread.print -l > "$INCIDENT_DIR/thread-platform-1.txt"
sleep 10
jcmd <pid> Thread.print -l > "$INCIDENT_DIR/thread-platform-2.txt"
sleep 10
jcmd <pid> Thread.print -l > "$INCIDENT_DIR/thread-platform-3.txt"
```

So sánh stack trace và trạng thái của cùng thread giữa các file. Nếu thread liên tục đứng ở cùng lời gọi, hãy kiểm tra dependency mà lời gọi đó đang chờ. Nếu thread tiến triển qua các stack frame, đó có thể là xử lý chậm chứ không phải bị treo.

Không tạo hàng chục dump liên tiếp khi process đang quá tải. Dump lớn có thể làm tăng I/O và dung lượng lưu trữ; chọn số snapshot đủ để thấy xu hướng.

## 6. Thu thập dump có virtual thread trong Java 21

Trong Java 21, dùng `Thread.dump_to_file` để tạo dump liệt kê cả platform thread và virtual thread. Command hỗ trợ định dạng `text` và `json`.

Dump dạng text:

```bash
jcmd <pid> Thread.dump_to_file -format=text "$INCIDENT_DIR/thread-virtual-<pid>.txt"
```

Dump dạng JSON để phân tích tự động:

```bash
jcmd <pid> Thread.dump_to_file -format=json "$INCIDENT_DIR/thread-virtual-<pid>.json"
```

Chọn text khi cần đọc stack trace trực tiếp; chọn JSON khi cần parser để lọc hoặc nhóm số lượng lớn thread. Không cần tạo cả hai định dạng nếu không có nhu cầu phân tích tương ứng.

### 6.1. Giới hạn của `Thread.dump_to_file`

Dump này giúp quan sát số lượng lớn virtual thread, nhưng không chứa đầy đủ thông tin như traditional thread dump. Trong Java 21, không nên kỳ vọng nó cung cấp object address, lock/monitor ownership, JNI statistics hoặc heap statistics.

Nếu cần điều tra monitor deadlock, bổ sung `Thread.print -l` cho platform thread và các công cụ phù hợp như `ThreadMXBean` hoặc JFR. `Thread.dump_to_file` cũng không thay thế heap dump, GC log hay JFR.

Dump virtual thread có thể rất lớn. Nếu ứng dụng tạo hàng chục nghìn hoặc hàng trăm nghìn virtual thread, kiểm tra dung lượng trước và bảo vệ file như dữ liệu production nhạy cảm.

## 7. Kiểm tra JFR đang chạy trước khi tạo recording mới

Trước tiên, xem recording hiện có:

```bash
jcmd <pid> JFR.check
```

Nếu ứng dụng hoặc nền tảng đã chạy continuous recording, có thể dump recording hiện có thay vì tạo một recording trùng lặp:

```bash
jcmd <pid> JFR.dump name=<recording-name> filename="$INCIDENT_DIR/existing-recording.jfr"
```

Thay `<recording-name>` bằng tên hiển thị trong `JFR.check`. Không dừng recording do thành phần khác quản lý nếu chưa được chủ sở hữu đồng ý; có thể ảnh hưởng khả năng giám sát liên tục của service.

JFR là công cụ ghi sự kiện runtime. Nó có thể giúp liên kết CPU, thread scheduling, lock contention, allocation và GC trong cùng một khoảng thời gian. Nội dung thực tế phụ thuộc recording settings và event được bật.

## 8. Bắt đầu JFR recording có thời hạn

Nếu chưa có recording phù hợp, tạo một recording có thời hạn rõ ràng. Ví dụ dùng cấu hình `profile` trong năm phút:

```bash
jcmd <pid> JFR.start name=incident settings=profile duration=5m filename="$INCIDENT_DIR/incident-<pid>.jfr"
```

`profile` thu thập nhiều sự kiện hơn cấu hình `default`, phù hợp cho một phiên điều tra ngắn nhưng có overhead lớn hơn. Hãy chọn thời lượng vừa đủ để bắt được triệu chứng và tránh ghi không giới hạn trên production.

Kiểm tra recording:

```bash
jcmd <pid> JFR.check
```

Nếu cần tự kiểm soát thời điểm kết thúc, có thể khởi động recording không đặt `duration`, sau đó dump và stop recording do chính mình tạo:

```bash
jcmd <pid> JFR.start name=incident settings=profile
jcmd <pid> JFR.dump name=incident filename="$INCIDENT_DIR/incident.jfr"
jcmd <pid> JFR.stop name=incident
```

Chỉ stop recording mà runbook/operator vừa tạo và sở hữu. Nếu cần lưu dữ liệu trước khi dừng, luôn dump trước. Khi recording có `duration` và `filename`, JVM tự kết thúc recording và ghi file khi hết thời hạn.

### 8.1. Thu thập JFR từ lúc khởi động

Nếu muốn luôn có recording ngắn sau khi service khởi động, có thể cấu hình startup option:

```bash
java -XX:StartFlightRecording=name=startup,settings=profile,duration=5m,filename=/var/log/app/startup.jfr -jar application.jar
```

Đây là cấu hình lúc khởi động JVM. Với incident bất ngờ xảy ra sau nhiều giờ hoặc nhiều ngày, nên có quy trình JFR continuous recording hoặc bắt đầu recording bằng `jcmd` khi phát hiện sự cố.

## 9. Phân tích file JFR

Sau khi có file recording, dùng `jfr` tool của JDK 21:

```bash
jfr summary "$INCIDENT_DIR/incident-<pid>.jfr"
```

`summary` cho biết thời gian recording, số lượng event và các nhóm event có trong file. Sau đó có thể in một số event liên quan đến sự cố:

```bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary,jdk.CPULoad,jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.VirtualThreadPinned "$INCIDENT_DIR/incident-<pid>.jfr"
```

Các event hữu ích gồm:

- `jdk.GarbageCollection`, `jdk.GCHeapSummary`: hoạt động GC và trạng thái heap.
- `jdk.CPULoad`, `jdk.ExecutionSample`: mức tải CPU và các sample thực thi nếu có trong recording.
- `jdk.ThreadPark`, `jdk.JavaMonitorEnter`: thread park và chờ monitor.
- `jdk.VirtualThreadPinned`: virtual thread bị pin trong carrier thread trên Java 21.

Event chỉ xuất hiện nếu recording settings và runtime ghi nhận event đó. Không kết luận event không xảy ra chỉ vì file không có event tương ứng; hãy kiểm tra cấu hình recording và thời điểm thu thập.

Có thể mở file JFR bằng JDK Mission Control (JMC) để phân tích timeline, method profile, allocation, lock contention và GC. Giữ JMC/JFR tool version tương thích với file recording và không chỉnh sửa file gốc trong quá trình điều tra.

## 10. Thu thập GC log trong production

### 10.1. Nếu GC logging đã được bật

Thu thập file log hiện tại và các file đã rotate. Không chỉ lấy file mới nhất vì chu kỳ gây sự cố có thể nằm trong file cũ hơn.

Kiểm tra:

- Thời gian bắt đầu/kết thúc log và khoảng trống giữa các file.
- JVM có đang ghi vào file hiện tại không.
- Rotation có xóa file cũ trước khi incident được phát hiện không.
- Log có bao phủ thời điểm latency tăng, OOM hoặc restart không.

Không dùng `cat` toàn bộ file rất lớn trong terminal hoặc gửi log thô ra nơi không được phê duyệt. Sao lưu file gốc, sau đó dùng công cụ tìm kiếm/lọc theo timestamp hoặc GC event.

### 10.2. Cấu hình Unified Logging cho lần khởi động tiếp theo

Trên Java 21, dùng Unified Logging (`-Xlog`) để ghi GC và safepoint event:

```bash
java \
  -Xlog:gc*,safepoint:file=/var/log/app/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar application.jar
```

Trong ví dụ:

- `gc*` ghi các tag GC và tag con.
- `safepoint` ghi sự kiện safepoint.
- `time,uptime,level,tags` thêm timestamp, uptime, level và tag.
- `filecount=5,filesize=20M` giới hạn rotation theo số file và kích thước mỗi file.

Điều chỉnh đường dẫn, số file và kích thước theo retention, dung lượng disk và chính sách logging của service. Đảm bảo user JVM có quyền ghi thư mục log.

Không dùng các flag GC logging cũ như `-XX:+PrintGCDetails` hoặc `-XX:+PrintGCDateStamps` cho cấu hình mới; Java 21 sử dụng Unified Logging với `-Xlog`.

### 10.3. Nếu GC log chưa được bật khi incident xảy ra

Không thể khôi phục lịch sử GC trước thời điểm bật logging. Ghi rõ khoảng thời gian thiếu dữ liệu trong incident report. Có thể thu thập JFR từ thời điểm hiện tại nếu phù hợp và bổ sung `-Xlog` vào cấu hình startup cho lần restart có kiểm soát tiếp theo.

HotSpot có diagnostic command `VM.log` để quản lý Unified Logging trong runtime. Trước khi thay đổi logging của production, kiểm tra `jcmd <pid> help VM.log`, xác nhận selector/output theo đúng JDK 21 và đánh giá tác động đến disk/retention. Không thay đổi cấu hình log hiện tại một cách mù quáng hoặc ghi đè output mà hệ thống logging đang sử dụng.

## 11. Thu thập metadata và runtime metrics đi kèm

Thread dump, JFR và GC log chỉ hữu ích khi có thể đặt chúng vào đúng bối cảnh. Ghi kèm:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.uptime
jcmd <pid> GC.heap_info
```

Lưu ý `VM.command_line` có thể chứa thông tin nhạy cảm. Không thu thập toàn bộ system properties theo mặc định vì có thể chứa credential, token, endpoint nội bộ hoặc cấu hình bí mật.

Thu thập thêm từ hệ thống giám sát:

- CPU usage và CPU throttling.
- Process RSS, container memory và memory limit.
- Heap usage, allocation rate, GC pause và GC CPU.
- Số platform thread, virtual thread/task đang hoạt động nếu có metric.
- Executor queue, semaphore wait, task rejection và timeout.
- Database/HTTP connection pool active, idle, pending và acquisition latency.
- Request throughput, p50/p95/p99, error rate và retry rate.
- Pod restart, OOMKilled, node pressure và deployment event.

Không dùng một metric riêng lẻ để kết luận. Ví dụ CPU thấp cùng queue tăng có thể là tác vụ đang chờ I/O/lock; CPU cao cùng `ExecutionSample` tập trung vào một method có thể là bottleneck tính toán.

## 12. Trình tự thu thập theo loại sự cố

| Triệu chứng | Thu thập ưu tiên | Điều cần tìm |
|---|---|---|
| Request treo hoặc latency tăng | 2–3 `Thread.print -l`, virtual-thread dump, JFR ngắn | Thread chờ lock, pool, socket, queue hoặc cùng một stack |
| CPU cao kéo dài | JFR `profile`, thread dump | Execution samples tập trung, vòng lặp nóng, retry hoặc contention |
| GC pause/heap pressure | GC log, JFR GC events, `GC.heap_info` | Tần suất GC, pause, live set, allocation và heap headroom |
| Nghi deadlock | `Thread.print -l` nhiều snapshot, JFR monitor events | Chu trình lock và owner; đối chiếu `ThreadMXBean` khi cần |
| Nhiều virtual thread bị chờ/pin | `Thread.dump_to_file`, JFR `jdk.VirtualThreadPinned`, thread/queue metrics | Điểm chờ chung, pinning và downstream saturation |
| Process sắp OOM/restart | Thread dump nhanh, JFR ngắn nếu còn khả năng, GC log và container metrics | Trạng thái trước khi process bị kill; không trì hoãn recovery |

Một số sự cố có nhiều nguyên nhân đồng thời. Ví dụ request latency tăng có thể do GC pressure cộng với database pool exhaustion. Cần đối chiếu timestamp của JFR, GC log, thread dump và distributed trace.

## 13. Correlate dữ liệu bằng thời gian

Để phân tích chính xác:

1. Ghi timestamp UTC khi bắt đầu mỗi lệnh thu thập.
2. Giữ nguyên timestamp và timezone của application log, load balancer, database và tracing backend.
3. Đối chiếu wall-clock timestamp với JVM uptime trong log/recording.
4. Ghi thời gian bắt đầu/kết thúc của JFR recording và các thread dump.
5. Ghi deployment, autoscaling, restart, config change và peak traffic xảy ra cùng khoảng thời gian.

GC log có thể chứa cả timestamp và uptime; JFR chứa timeline của recording. Nếu đồng hồ node lệch hoặc log được lưu theo timezone khác, hãy ghi nhận độ lệch trước khi so sánh.

## 14. Đóng gói và bảo vệ bằng chứng

Một incident bundle nên có cấu trúc dễ hiểu:

```text
incident-20261116T143000Z/
  metadata.txt
  thread-platform-1.txt
  thread-platform-2.txt
  thread-platform-3.txt
  thread-virtual.json
  incident.jfr
  gc.log
  gc.log.1
  metrics-snapshot.txt
  commands.txt
```

Không phải incident nào cũng cần mọi file. Chỉ đưa vào những artifact thực sự được thu thập.

Trước khi chia sẻ:

- Rà soát command line, thread name, URL, SQL, file path và tên tenant/user.
- Lưu artifact ở vị trí có quyền truy cập giới hạn.
- Ghi checksum nếu cần bảo đảm tính toàn vẹn khi chuyển giao.
- Không ghi đè file gốc; tạo bản đã redaction riêng nếu cần chia sẻ.
- Áp dụng retention và xóa an toàn theo chính sách tổ chức.

Thread dump/JFR có thể tiết lộ cấu trúc nội bộ và dữ liệu vận hành nhạy cảm dù không chứa password rõ ràng. Coi chúng là production diagnostic data.

## 15. Những lỗi thường gặp khi chạy runbook

| Vấn đề | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `jcmd -l` không thấy process | Khác user, namespace hoặc JVM không được attach | Chạy trong đúng host/container và user |
| `AttachNotSupportedException` hoặc permission denied | Quyền attach, PID không đúng hoặc môi trường hạn chế | Xác minh PID, user/group và runtime |
| Không tạo được dump/JFR | Đường dẫn không ghi được hoặc disk đầy | Chọn thư mục phù hợp trong filesystem của JVM đích |
| Thread dump không thấy virtual thread | Dùng `Thread.print` và kỳ vọng nó liệt kê mọi virtual thread | Dùng `Thread.dump_to_file` trên Java 21 |
| Không thấy lock owner trong virtual-thread dump | Dump này không chứa lock details như traditional dump | Thu thập thêm `Thread.print -l`, JFR hoặc `ThreadMXBean` |
| JFR file không có event mong muốn | Recording settings không bật event hoặc recording sai thời điểm | Kiểm tra settings, `jfr summary` và thời lượng recording |
| JFR recording đã tồn tại | Service hoặc operator khác đang quản lý recording | Dùng `JFR.check`, dump recording phù hợp; không stop recording của người khác |
| Không có GC log cho thời điểm trước incident | GC logging chưa được bật hoặc file đã rotate mất | Ghi rõ thiếu dữ liệu; cấu hình `-Xlog` cho lần chạy tiếp theo |
| Disk tăng nhanh | Dump lớn, JFR kéo dài hoặc GC log không rotate | Dùng duration, rotation và retention giới hạn |
| Artifact chứa thông tin nhạy cảm | Thread name, command line hoặc URL có dữ liệu nội bộ | Giới hạn quyền đọc và redaction trước khi chia sẻ |

## 16. Checklist runbook

### Trước khi chạy lệnh

- [ ] Xác định đúng service, host/container, PID và JDK 21 build.
- [ ] Ghi timestamp UTC và incident ID.
- [ ] Xác nhận user có quyền attach và thư mục output có quyền ghi.
- [ ] Kiểm tra dung lượng filesystem và phạm vi dữ liệu nhạy cảm.
- [ ] Xem recording JFR hiện có trước khi tạo recording mới.

### Thu thập

- [ ] Lấy 2–3 `Thread.print -l` nếu cần so sánh platform thread.
- [ ] Lấy `Thread.dump_to_file -format=text` hoặc `-format=json` nếu ứng dụng dùng virtual thread.
- [ ] Tạo hoặc dump JFR recording có thời hạn và lưu tên recording.
- [ ] Thu thập GC log hiện tại và các file đã rotate.
- [ ] Ghi metadata JVM, heap và metrics ứng dụng/container.
- [ ] Ghi command và timestamp của từng artifact.

### Sau khi thu thập

- [ ] Kiểm tra file có tồn tại, kích thước hợp lý và đọc được.
- [ ] Dừng chỉ recording JFR do incident operator tạo và sở hữu.
- [ ] Không thay đổi hoặc xóa recording/GC logging do hệ thống khác quản lý.
- [ ] Bảo vệ artifact, redaction khi cần và lưu theo retention policy.
- [ ] Correlate thread dump, JFR, GC log, application log và metrics theo timestamp.
- [ ] Ghi nhận giới hạn dữ liệu còn thiếu và bước điều tra tiếp theo.

## 17. Tài liệu tham khảo chính thức

- [Java SE 21 `jcmd` documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic command, thread dump, JFR và `VM.log`.
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): `Thread.dump_to_file`, định dạng text/JSON và giới hạn của dump virtual thread.
- [Java SE 21 — JFR Configuration](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html): recording settings và cấu hình JFR.
- [Java SE 21 — JFR Runtime Guide](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-runtime-guide.html): bắt đầu, kiểm tra, dump và dừng recording.
- [Java SE 21 — Unified Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): cú pháp `-Xlog`, output, decorators và file rotation.
- [Java SE 21 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/): quy trình chẩn đoán JVM và ứng dụng.

Runbook production nên thu thập thread dump, JFR và GC log theo đúng triệu chứng, có timestamp và metadata để đối chiếu. Với Java 21, dùng `Thread.print -l` cho thông tin platform-thread/lock, `Thread.dump_to_file` để quan sát cả virtual thread, JFR recording có thời hạn để xem diễn biến runtime và Unified Logging `-Xlog` để theo dõi GC. Hãy kiểm tra recording hiện có, giới hạn overhead/disk, bảo vệ artifact và ghi rõ dữ liệu nào không thể khôi phục nếu logging chưa được bật trước incident.
