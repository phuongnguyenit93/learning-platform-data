# Debug production an toàn với Java

## 1. Mục tiêu và nguyên tắc

Debug production an toàn là thu thập đủ bằng chứng để xác định nguyên nhân sự cố trong khi giữ ứng dụng phục vụ request, bảo vệ dữ liệu và kiểm soát tác động lên JVM.

Trong môi trường production, ưu tiên chẩn đoán bằng metrics, logs, distributed traces, JFR và các diagnostic command có mức ảnh hưởng phù hợp. Breakpoint, heap dump, class histogram, bật debug logging toàn cục hoặc thay đổi JVM flags có thể làm thay đổi tải, thời gian pause, dung lượng đĩa hay hành vi ứng dụng.

Một quy trình tốt cần:

- Xác định đúng JVM, container, phiên bản JDK và thời điểm xảy ra lỗi.
- Ghi lại baseline từ metrics trước khi chạy lệnh chẩn đoán.
- Bắt đầu với thông tin có mức ảnh hưởng thấp.
- Tăng mức thu thập khi đã có giả thuyết cụ thể.
- Giới hạn thời lượng, dung lượng và phạm vi dữ liệu.
- Ghi lại lệnh, thời điểm, PID và kết quả để có thể đối chiếu.
- Bảo vệ mọi file dump, recording và log như dữ liệu nhạy cảm.

Không có diagnostic command nào hoàn toàn miễn phí. Ngay cả lệnh chỉ đọc cũng cần attach vào JVM, lấy snapshot hoặc in dữ liệu; thời gian và tác động phụ thuộc số thread, kích thước heap, collector, event settings và tải hiện tại.

## 2. Phân loại mức ảnh hưởng trước khi chạy lệnh

`jcmd` là công cụ chẩn đoán chính được Oracle khuyến nghị cho HotSpot JDK hiện đại. Mỗi diagnostic command có thông tin Impact trong help của JVM đích. Mức Impact là hướng dẫn về chi phí tương đối, không phải cam kết rằng lệnh luôn an toàn trong mọi tải.

Ví dụ trên Azul JDK 24.0.2 đã kiểm tra:

| Mức Impact | Lệnh ví dụ | Tác dụng và lưu ý |
|---|---|---|
| Impact: Low | `VM.version`, `VM.uptime`, `VM.flags`, `VM.log list` | Đọc phiên bản, uptime, flags hoặc cấu hình log hiện tại |
| Impact: Low | `JFR.dump` | Ghi dữ liệu từ recording đang chạy ra file |
| Impact: Medium | `GC.heap_info` | Đọc thông tin heap tổng quát |
| Impact: Medium | `Thread.print`, `Thread.dump_to_file` | Lấy stack trace của thread; chi phí phụ thuộc số thread |
| Impact: Medium | `JFR.start` | Bắt đầu recording; tác động thay đổi theo profile và event settings |
| Impact: Medium | `VM.native_memory` | Đọc thống kê native memory nếu NMT đã được bật |
| Impact: High | `GC.class_histogram` | Quét heap để thống kê object theo class |
| Impact: High | `GC.heap_dump` | Ghi HPROF; mặc định yêu cầu full GC nếu không dùng `-all` |

Luôn kiểm tra đúng lệnh trên JVM đích:

~~~bash
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
jcmd <pid> help JFR.start
~~~

Tên command, option và Impact có thể khác theo JVM vendor và phiên bản JDK. Hãy dùng help của tiến trình đang gặp sự cố thay vì sao chép mù một command từ máy phát triển.

## 3. Xác định đúng JVM trước khi attach

Liệt kê các Java process mà JDK tool nhìn thấy:

~~~bash
jcmd -l
~~~

Có thể dùng:

~~~bash
jps -l
~~~

Xác nhận PID bằng main class, command line, service name hoặc thông tin từ process manager. Trên máy có nhiều ứng dụng Java, đừng đoán PID chỉ dựa vào thứ tự dòng output.

Xem phiên bản và thời gian chạy:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
~~~

Xem các diagnostic command mà JVM hỗ trợ:

~~~bash
jcmd <pid> help
~~~

`jcmd` phải chạy trên cùng máy với JVM và cùng effective user/group identifiers (UID/GID) đã khởi chạy JVM. Nếu dùng Docker hoặc container, PID bên trong container có thể khác PID trên host. Hãy chạy lệnh trong đúng container hoặc PID namespace và xác nhận process bằng `ps` hoặc `jcmd -l` tại đó.

Không chạy chẩn đoán trên process chưa được xác định rõ. Ghi lại PID, tên ứng dụng, container/pod, node và JDK version để tránh lấy nhầm dữ liệu của instance khác.

## 4. Bắt đầu với các lệnh đọc thông tin JVM

Các lệnh sau thường là bước kiểm tra ban đầu:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.uptime
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

- `VM.version` cho biết JVM/JDK version.
- `VM.uptime` cho biết thời gian JVM đã chạy.
- `VM.flags` in các VM flag hiện tại, bao gồm heap sizing và collector flags.
- `GC.heap_info` cung cấp thông tin tổng quát về heap và metaspace.

`VM.flags` có thể giúp phát hiện cấu hình heap hoặc collector khác với dự kiến. `GC.heap_info` có Impact Medium, vì vậy hãy cân nhắc tải hiện tại trước khi chạy lặp lại.

Không nên in toàn bộ system properties, command line hoặc VM environment ra kênh chat/ticket công khai. `VM.command_line`, `VM.system_properties` và `VM.info` có thể tiết lộ tham số khởi chạy, đường dẫn, environment variables, URL nội bộ hoặc thông tin xác thực được cấu hình sai cách. Nếu cần thu thập, lưu ở vị trí hạn chế quyền truy cập và redact trước khi chia sẻ.

## 5. Dùng thread dump để điều tra request bị treo

Thread dump ghi trạng thái thread và stack trace tại một thời điểm. Đây là cách nhanh để tìm thread đang chạy CPU, chờ monitor, chờ condition hoặc bị block.

In thread dump kèm thông tin lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

Ghi ra file dạng text:

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain C:\secure\incident\threads.txt
~~~

Ghi ra JSON:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json C:\secure\incident\threads.json
~~~

`Thread.print` và `Thread.dump_to_file` có Impact Medium, phụ thuộc số lượng thread. File dump có thể lớn trong ứng dụng có hàng nghìn thread; kiểm tra dung lượng và quyền ghi trước khi lưu.

Nếu ứng dụng bị treo, lấy một vài thread dump cách nhau khoảng 5–10 giây. So sánh cùng thread qua các mẫu để xem stack có tiến triển hay bị kẹt tại cùng vị trí. Một thread ở trạng thái `RUNNABLE` chưa chắc đang tiêu thụ CPU; cần đối chiếu với CPU metrics và stack. `BLOCKED` thường cho biết đang chờ monitor; `WAITING` và `TIMED_WAITING` có thể là hành vi bình thường của pool, scheduler hoặc I/O.

### Lấy thread dump bằng tín hiệu hệ điều hành

Nếu không thể attach bằng `jcmd` nhưng có quyền truy cập console của JVM:

- Windows: nhấn Control+Break trong console đang gắn với JVM.
- Linux/Unix: gửi `SIGQUIT` bằng `kill -QUIT <pid>`.

HotSpot thường ghi thread dump ra stdout/stderr của tiến trình. Kiểm tra nơi service đang redirect output. Tín hiệu này không giống `SIGKILL`; đừng dùng `kill -9` như một cách lấy thread dump vì nó kết thúc process mà không cho JVM xử lý yêu cầu chẩn đoán.

## 6. Đọc thread dump và nhận diện dấu hiệu bất thường

Một số trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| `RUNNABLE` | Thread đang chạy hoặc sẵn sàng chạy trong JVM | CPU, stack lặp lại và hot method |
| `BLOCKED` | Thread đang chờ lấy intrinsic monitor | Thread đang giữ lock, lock order và vùng synchronized |
| `WAITING` | Thread chờ vô thời hạn một điều kiện | Pool, queue, latch, future hoặc signal |
| `TIMED_WAITING` | Thread chờ có thời hạn | Sleep, timed wait, park hoặc timeout |

Ví dụ rút gọn từ một thread dump có lock contention:

~~~text
"safe-worker-0"
   java.lang.Thread.State: TIMED_WAITING (sleeping)
   at demo.SafeDebugTarget.work(SafeDebugTarget.java:14)
   - locked <0x...> (a java.lang.Object)

"safe-worker-1"
   java.lang.Thread.State: BLOCKED (on object monitor)
   at demo.SafeDebugTarget.work(SafeDebugTarget.java:14)
   - waiting to lock <0x...> (a java.lang.Object)
~~~

Ở ví dụ này, `safe-worker-1` đang chờ object monitor mà `safe-worker-0` giữ. Hãy tìm thread giữ lock, xem stack trace của cả hai và xác định vì sao critical section kéo dài.

`Thread.print -l` giúp hiển thị lock và ownable synchronizer. Nếu JVM phát hiện deadlock, thread dump có thể in phần mô tả deadlock và các thread liên quan. Đừng kết luận deadlock chỉ từ một thread đang ở trạng thái `BLOCKED`; cần kiểm tra chu trình chờ lock và nhiều snapshot theo thời gian.

## 7. Dùng JFR để ghi nhận sự cố trong một khoảng ngắn

Java Flight Recorder (JFR) ghi sự kiện runtime có timestamp, gồm CPU samples, allocation samples, GC, lock contention, thread và I/O. JFR tích hợp trong HotSpot và có thể dùng trong production với cấu hình phù hợp.

Bắt đầu bằng cấu hình mặc định trong 60 giây:

~~~bash
jcmd <pid> JFR.start name=incident settings=default duration=60s filename=incident.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check name=incident verbose=true
~~~

Nếu cần lưu snapshot trong khi recording vẫn tiếp tục:

~~~bash
jcmd <pid> JFR.dump name=incident filename=incident-snapshot.jfr
~~~

Nếu recording chưa có duration và cần dừng thủ công:

~~~bash
jcmd <pid> JFR.stop name=incident
~~~

`default.jfc` thường có overhead thấp và phù hợp để thu thập nền. `profile.jfc` bật thêm dữ liệu profiling, có thể tăng overhead và dung lượng; chỉ dùng trong cửa sổ ngắn khi có câu hỏi cụ thể như CPU hotspot, allocation hoặc lock contention.

Ví dụ profile ngắn 30 giây khi đã có giả thuyết cần xem CPU/allocation sâu hơn:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=30s filename=profile.jfr
~~~

JDK help xếp `JFR.start` ở mức Impact Medium vì tác động phụ thuộc settings. Không bật đồng thời nhiều profile nặng nếu chưa đánh giá tổng chi phí. Nếu cần `path-to-gc-roots` để điều tra memory leak, hãy hiểu rằng việc thu thập có thể mất thời gian và làm JVM pause trong một khoảng ngắn.

## 8. Phân tích recording mà không thay đổi ứng dụng

Xem tổng quan file:

~~~bash
jfr summary incident.jfr
~~~

Xem CPU execution samples:

~~~bash
jfr print --events jdk.ExecutionSample incident.jfr
~~~

Xem allocation samples:

~~~bash
jfr print --events jdk.ObjectAllocationSample incident.jfr
~~~

Xem monitor contention:

~~~bash
jfr print --events jdk.JavaMonitorEnter incident.jfr
~~~

Đối chiếu timestamp trong recording với request latency, logs, metrics và distributed traces. Ví dụ, nếu latency tăng lúc `jdk.JavaMonitorEnter` có duration dài, hãy xem thread chờ, thread giữ monitor và stack trace. Nếu CPU tăng và cùng một stack xuất hiện trong nhiều execution sample, kiểm tra hot method và call path.

Không thấy event trong recording không chứng minh sự cố không xảy ra. Event có thể bị tắt, threshold quá cao, sampling không bắt trúng hoặc recording không bao phủ đúng thời điểm.

## 9. Kiểm tra heap trước khi tạo heap dump

`GC.heap_info` cho cái nhìn tổng quát về heap, metaspace và region của collector. Dùng nó để kiểm tra nhanh tình trạng heap trước khi cân nhắc thao tác sâu hơn.

Histogram thống kê số instance và shallow size theo class:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Trên JDK 24, `GC.class_histogram` có Impact High vì phụ thuộc kích thước và nội dung heap. Hãy cân nhắc tải và thời gian pause trước khi chạy, đặc biệt với heap lớn hoặc hệ thống đang quá tải. Không chạy histogram lặp đi lặp lại chỉ để theo dõi một chỉ số có thể lấy từ metrics.

Histogram cho biết class nào chiếm nhiều object/bytes nhưng không giải thích đường tham chiếu giữ object. Nếu cần biết vì sao object còn sống, hãy phân tích heap dump bằng công cụ như Eclipse Memory Analyzer (MAT).

## 10. Heap dump là thao tác có chi phí cao

Tạo HPROF heap dump:

~~~bash
jcmd <pid> GC.heap_dump C:\secure\incident\heap.hprof
~~~

Tạo dump gzip:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 C:\secure\incident\heap.hprof.gz
~~~

`GC.heap_dump` có Impact High, phụ thuộc kích thước heap và nội dung. Mặc định, lệnh yêu cầu full GC trước khi dump, trừ khi chỉ định `-all`. Full GC có thể gây pause đáng kể và làm tăng latency của ứng dụng.

`-all` yêu cầu dump cả object unreachable, vì vậy không yêu cầu full GC theo cách mặc định. Dump có thể bao gồm object chưa được thu gom; chọn chế độ theo câu hỏi phân tích.

Trước khi tạo heap dump:

1. Xác nhận đây là đúng PID và đúng instance.
2. Kiểm tra dung lượng đĩa, quota và quyền ghi.
3. Chọn đường dẫn có ACL phù hợp và đủ chỗ cho file lớn.
4. Xem mức tải hiện tại và thống nhất cửa sổ thao tác nếu cần.
5. Chọn live/all theo mục tiêu điều tra.
6. Ghi lại thời gian bắt đầu/kết thúc và loại dump.
7. Hạn chế người có thể đọc file và thời gian lưu giữ.

Heap dump có thể chứa password, access token, session, request payload, dữ liệu khách hàng và cache. Chỉ mở bằng công cụ phân tích được phê duyệt; không upload lên dịch vụ công cộng hoặc chia sẻ vào ticket/chat có nhiều người đọc.

## 11. Native Memory Tracking cần được bật từ lúc JVM khởi động

Java heap không phải toàn bộ memory của process. Native memory còn có thể đến từ metaspace, code cache, thread stack, GC structures, direct buffer, JNI và native library.

Native Memory Tracking (NMT) theo dõi phần cấp phát nội bộ JVM. NMT phải được bật khi khởi động JVM bằng flag:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Hoặc mức chi tiết hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Sau đó có thể truy vấn:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

NMT không thể bật hồi tố cho JVM đã chạy mà không có flag khởi động. Trên JDK 24, lệnh trả thông báo `Native memory tracking is not enabled` nếu tiến trình không bật NMT.

NMT có thể làm giảm hiệu năng khoảng 5–10% và tiêu tốn thêm bộ nhớ cho tracking. Nó không thể theo dõi mọi native allocation do code JNI hoặc thư viện bên ngoài JVM thực hiện. Chỉ bật NMT trong production khi đã cân nhắc overhead và mục tiêu theo dõi; dùng OS tools khi cần điều tra native memory nằm ngoài phạm vi NMT.

## 12. Kiểm tra logging hiện tại trước khi đổi cấu hình

Xem cấu hình Unified Logging đang chạy:

~~~bash
jcmd <pid> VM.log list
~~~

Lệnh này giúp biết output, tag và level hiện tại. Nếu đã có GC log hoặc application log, hãy phân tích dữ liệu đó trước khi bật thêm logging.

Bật trace/debug cho toàn bộ tag có thể tạo lượng log rất lớn, tăng I/O, làm đầy disk và ảnh hưởng latency. Nếu cần thay đổi log level, hãy giới hạn tag, output, thời gian và dung lượng; ghi lại cấu hình ban đầu để có thể khôi phục chính xác.

Không dùng `VM.log` để thay đổi logging trong production nếu chưa biết rõ output và tác động. Tránh bật debug logging toàn cục chỉ vì chưa xác định được nguyên nhân.

## 13. Chọn công cụ theo triệu chứng

| Triệu chứng | Bằng chứng nên thu thập trước | Bước tiếp theo |
|---|---|---|
| CPU tăng cao | CPU metrics, vài thread dump, JFR execution samples | Xác định hot stack và method |
| Latency tăng nhưng CPU thấp | Thread dump lặp lại, JFR lock/I/O events, request traces | Tìm thread chờ lock, network hoặc file I/O |
| Request bị treo | `Thread.print -l` và 2–3 snapshot cách nhau vài giây | Tìm thread blocked, deadlock hoặc pool cạn |
| Heap tăng liên tục | Heap/GC metrics, GC logs, JFR allocation samples | Histogram; cân nhắc heap dump khi cần |
| Process RSS tăng nhưng heap ổn định | NMT nếu đã bật, direct buffer và OS metrics | Kiểm tra metaspace, thread stacks, JNI/native library |
| OOM | OOM logs, heap dump nếu đã cấu hình, GC history | Phân tích retained heap và allocation path |
| JVM crash | Fatal error log, core dump, OS logs | Phân tích bằng Serviceability Agent/native debugger |

Không dùng heap dump để điều tra mọi sự cố memory. Nếu RSS tăng nhưng Java heap không tăng, heap dump có thể không trả lời đúng câu hỏi; hãy kiểm tra NMT, direct buffers, thread count và native allocation.

## 14. Debugger và JDWP trong production

JDWP là giao thức điều khiển debugger. Một debugger có thể đọc trạng thái, đặt breakpoint, đánh giá biểu thức và điều khiển thread. Các thao tác này có thể làm thay đổi timing, tạm dừng thread hoặc khiến request bị treo.

Không mở cổng JDWP ra Internet hoặc mạng không tin cậy. Tránh cấu hình listener trên mọi interface, không để debugger port tồn tại lâu hơn cửa sổ điều tra và không dùng breakpoint có thể suspend ứng dụng đang phục vụ traffic.

Nếu bắt buộc phải dùng debugger trên production, cần có phê duyệt vận hành, giới hạn truy cập mạng bằng VPN/bastion/firewall allowlist, thời gian ngắn và kế hoạch gỡ kết nối. Ưu tiên JFR, thread dump và metrics cho chẩn đoán ban đầu vì chúng thu thập bằng chứng mà không yêu cầu dừng thread tại breakpoint.

Không khởi động lại ứng dụng chỉ để bật remote debugging giữa incident nếu chưa đánh giá tác động restart và phương án phục hồi.

## 15. Chẩn đoán trong Docker và Kubernetes

PID trên host có thể khác PID trong container. `jcmd -l` trên host cũng không nhất thiết liệt kê JVM chạy trong một Docker process riêng.

Ví dụ vào container:

~~~bash
docker exec -it <container-name> sh
~~~

Sau đó chạy bên trong container:

~~~bash
ps -ef
jcmd -l
jcmd <pid> VM.version
~~~

Với Kubernetes:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- sh
~~~

Chọn đúng container khi pod có nhiều container. Dùng JDK tools sẵn có trong image hoặc một diagnostic image được tổ chức phê duyệt; tránh cài package hoặc thay đổi image production trong lúc incident nếu chưa có quy trình.

Đảm bảo user chạy `jcmd` có cùng effective UID/GID với JVM. Nếu container không có shell hoặc JDK tools, dùng cơ chế ephemeral/debug container được nền tảng cho phép và xác nhận PID namespace, filesystem và quyền attach trước khi thao tác.

## 16. Lỗi attach và cách xử lý

### jcmd -l không hiển thị process

Xác nhận process đang chạy, đúng host/container/PID namespace và đúng user. Trong Docker, chạy lệnh từ bên trong container hoặc namespace phù hợp.

### Unable to open socket file hoặc attach thất bại

Kiểm tra effective user/group, quyền filesystem, JDK tool đang dùng, PID còn tồn tại và attach mechanism. JVM có thể được khởi chạy với `-XX:+DisableAttachMechanism`, khiến attach command không hoạt động.

Không thay đổi quyền process hoặc restart service chỉ để vượt qua lỗi attach khi chưa có phê duyệt. Thu thập logs/metrics có sẵn và dùng phương án chẩn đoán được nền tảng hỗ trợ.

### Command không được hỗ trợ

Chạy `jcmd <pid> help` và `jcmd <pid> help <command>`. Command phụ thuộc JVM vendor, version và tính năng đã bật.

### Không ghi được file dump/recording

Kiểm tra đường dẫn trong filesystem mà process hoặc công cụ nhìn thấy, quyền ghi, dung lượng trống và quota. Đặt file ở volume riêng có kiểm soát truy cập.

### JFR recording không có event mong muốn

Kiểm tra settings, event enabled, threshold, period và thời điểm recording. Dùng `jcmd <pid> JFR.check name=profile verbose=true` để xem cấu hình thực tế.

### NMT không có dữ liệu

NMT phải được bật lúc JVM khởi động. Nếu không có flag, `VM.native_memory` sẽ báo tracking chưa được bật; lên kế hoạch bật trong lần triển khai phù hợp và đánh giá overhead trước.

## 17. Bảo vệ dữ liệu chẩn đoán

Các artifact sau có thể chứa thông tin nhạy cảm:

- Heap dump: object, field, token, mật khẩu, request/response, cache và dữ liệu nghiệp vụ.
- Thread dump: tên thread, stack trace, tên class/method, đôi khi có dữ liệu được nhúng trong tên hoặc message.
- JFR: stack trace, class, file path, thread, system information và custom event fields.
- JVM command line/system properties/environment: endpoint nội bộ, user, token hoặc credential cấu hình sai cách.
- GC/JVM logs: đường dẫn, cấu hình, tên service và thông tin môi trường.

Lưu artifact ở thư mục hạn chế quyền truy cập, mã hóa khi lưu/chuyển nếu chính sách yêu cầu, đặt thời hạn xóa, ghi nhận người nhận và không chia sẻ rộng. Trước khi gửi ra ngoài tổ chức, rà soát và redact dữ liệu nhạy cảm theo chính sách.

## 18. Quy trình runbook khi production gặp sự cố

1. Ghi nhận thời gian bắt đầu, triệu chứng, phạm vi ảnh hưởng, request mẫu và service instance.
2. Thu thập metrics/logs/traces hiện có; lưu baseline CPU, heap, GC, thread count, RSS và latency.
3. Xác định đúng JVM, PID, container, JDK version và user.
4. Đọc `VM.version`, `VM.uptime`, `VM.flags` và `GC.heap_info` nếu phù hợp.
5. Với hang/latency, lấy 2–3 thread dump cách nhau 5–10 giây; kiểm tra lock owner, blocked thread và stack lặp lại.
6. Với CPU hoặc latency, chạy JFR default trong một khoảng ngắn, có duration và filename rõ ràng.
7. Phân tích recording bằng `jfr summary`, `jfr print` hoặc JDK Mission Control.
8. Chỉ chạy histogram hoặc heap dump khi đã có câu hỏi memory cụ thể, đánh giá Impact High, pause, dung lượng và quyền truy cập.
9. Nếu nghi ngờ native memory, kiểm tra NMT đã được bật chưa và kết hợp OS metrics.
10. Ghi lại command, output, thời điểm, thời lượng, người thực hiện và thay đổi đã áp dụng.
11. Kiểm tra ứng dụng sau chẩn đoán: latency, error rate, CPU, memory, GC và thread count.
12. Đóng recording/debug session, khôi phục logging nếu đã thay đổi và áp dụng retention cho artifact.

## 19. Ví dụ Java 17 hoàn chỉnh để thực hành thread dump và JFR

Tạo file `src/demo/SafeDebugTarget.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

/** Generates controlled allocation and monitor contention for diagnostics. */
public final class SafeDebugTarget {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();
    private static volatile long sink;

    private static void work() {
        while (!Thread.currentThread().isInterrupted()) {
            byte[] bytes = new byte[1024];
            sink += bytes.length;

            synchronized (LOCK) {
                try {
                    Thread.sleep(20);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 8; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        for (int i = 0; i < 2; i++) {
            new Thread(SafeDebugTarget::work, "safe-worker-" + i).start();
        }

        System.out.println("READY retainedKiB=" + RETAINED.size() * 256);
        Thread.sleep(120_000);
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/demo/SafeDebugTarget.java
~~~

Chạy trong Terminal 1:

~~~bash
java -Xms32m -Xmx128m -cp out demo.SafeDebugTarget
~~~

Stdout chính xác:

~~~text
READY retainedKiB=2048
~~~

Trong Terminal 2, tìm PID và lấy thread dump:

~~~bash
jcmd -l
jcmd <pid> Thread.print -l
~~~

Lưu JSON thread dump:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Bắt đầu JFR recording 5 giây:

~~~bash
jcmd <pid> JFR.start name=practice settings=default duration=5s filename=practice.jfr
~~~

Sau khi recording hoàn tất:

~~~bash
jfr summary practice.jfr
jfr print --events jdk.JavaMonitorEnter practice.jfr
~~~

Trong lần thử với Azul JDK 24.0.2, thread dump cho thấy một worker ở trạng thái `BLOCKED` chờ monitor mà worker còn lại đang giữ. Recording 5 giây ghi nhận 37 sự kiện `jdk.JavaMonitorEnter` trong lần chạy kiểm tra. Số event có thể thay đổi theo scheduling, CPU và thời gian chạy; mục tiêu là luyện cách đối chiếu thread dump với event JFR.

Khi hoàn tất, dừng chương trình bằng Ctrl+C trong Terminal 1.

## 20. Checklist trước khi chẩn đoán production

- [ ] Xác nhận đúng JVM, PID, container và JDK version.
- [ ] Chạy `jcmd <pid> help` để kiểm tra command trên JVM đích.
- [ ] Xem Impact của command trước khi chạy.
- [ ] Thu thập metrics/logs/traces và baseline trước khi attach.
- [ ] Bắt đầu bằng `VM.version`, `VM.uptime`, `VM.flags` hoặc `GC.heap_info` khi phù hợp.
- [ ] Dùng thread dump lặp lại để phân tích hang, block và deadlock.
- [ ] Ưu tiên JFR `default` và duration giới hạn cho profiling ban đầu.
- [ ] Chỉ dùng `profile` hoặc custom events khi đã có giả thuyết và cửa sổ thu thập rõ ràng.
- [ ] Tránh histogram và heap dump khi chưa đánh giá Impact High, full GC, pause và disk.
- [ ] Chỉ dùng NMT nếu đã bật từ startup và chấp nhận overhead 5–10%.
- [ ] Không bật debug logging toàn cục hoặc mở JDWP ra mạng công cộng.
- [ ] Bảo vệ thread dump, JFR, heap dump và JVM metadata như dữ liệu nhạy cảm.
- [ ] Ghi lại thời điểm, command, kết quả và người thực hiện.
- [ ] Kiểm tra lại sức khỏe ứng dụng sau khi hoàn tất.

## 21. Tài liệu tham khảo

- [Oracle JDK 24 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html): phân loại công cụ giám sát, JFR, jcmd, thread dump, heap histogram, heap dump và Native Memory Tracking.
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html): cú pháp, Impact và tùy chọn của diagnostic command.
- [Oracle JDK 24 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf): cách thu thập thread dump, heap dump, thông tin JVM và chẩn đoán process bị treo.
- [Oracle JDK 24 — Submit a Bug Report](https://docs.oracle.com/en/java/javase/24/troubleshoot/submit-bug-report.html): thu thập thread stack và core dump khi cần điều tra sâu.
- [Oracle JDK 24 — JFR Configurations](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-configurations.html): lựa chọn cấu hình Flight Recorder và trade-off giữa default/profile.

Debug production an toàn là thu thập bằng chứng theo mức tác động tăng dần. Bắt đầu với metrics, thread dump và JFR cấu hình nhẹ; chỉ chuyển sang histogram, heap dump hoặc native-memory tracking khi có mục tiêu cụ thể, đã đánh giá chi phí và có cách bảo vệ dữ liệu thu thập.
