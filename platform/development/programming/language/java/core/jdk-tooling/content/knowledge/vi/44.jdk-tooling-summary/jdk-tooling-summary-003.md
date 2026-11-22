# Luồng chẩn đoán JVM trong Java Core JDK Tooling

## 1. Mục tiêu của chẩn đoán JVM

Chẩn đoán JVM là quá trình thu thập và phân tích bằng chứng để xác định vì sao một ứng dụng Java khởi động lỗi, chạy chậm, dùng CPU cao, tăng bộ nhớ, bị treo hoặc kết thúc bất thường.

Một quy trình tốt phải trả lời được bốn câu hỏi:

1. JVM đang chạy phiên bản nào, với những cờ khởi động và giới hạn tài nguyên nào?
2. Triệu chứng xuất hiện ở heap Java, garbage collection, thread, class loading, native memory, I/O hay hệ điều hành?
3. Bằng chứng nào xác nhận giả thuyết và có thể thu thập mà không làm sự cố nặng hơn?
4. Sau khi thay đổi cấu hình hoặc code, làm sao xác nhận nguyên nhân đã được xử lý?

Không bắt đầu bằng việc tăng ngay -Xmx, đổi garbage collector hoặc restart process. Trước hết, ghi lại thời điểm, PID, phiên bản JDK, JVM arguments, tải hệ thống và triệu chứng. Giữ lại log, thread dump hoặc recording trước khi restart nếu có thể.

## 2. Phân loại triệu chứng trước khi chọn công cụ

| Triệu chứng | Nhóm cần điều tra đầu tiên | Bằng chứng phù hợp |
|---|---|---|
| JVM không khởi động | Launcher, JDK, classpath, module path | java -version, command line, stderr, exception đầu tiên |
| Ứng dụng thoát ngay | Application exception hoặc cấu hình | Stack trace, application log, exit code |
| CPU tăng cao | Thread đang chạy, JIT, vòng lặp, lock contention | JFR, thread dump lặp lại, OS thread monitor |
| Request chậm hoặc treo | Thread pool, lock, network, disk, dependency | Thread dump, JFR, application trace |
| Heap tăng liên tục | Object retention, allocation rate, GC | GC log, histogram, heap dump, JFR |
| GC pause dài | Heap pressure, allocation, collector behavior | GC log, JFR, heap usage sau GC |
| RSS/container memory tăng | Heap, direct buffer, metaspace, thread stack, JNI/native | NMT, JFR, OS/cgroup metrics |
| Metaspace tăng | Class loading hoặc classloader leak | VM.metaspace, VM.classloader_stats, class load log |
| JVM crash hoặc process bị kill | Native code, VM, OS, container limit | hs_err log, core dump, kernel/container events |
| Lỗi class/method lúc chạy | JDK/API hoặc dependency không tương thích | Stack trace, java version, classpath, dependency tree |

Một triệu chứng có thể có nhiều nguyên nhân. Ví dụ, CPU cao có thể đến từ tính toán, garbage collection, spin loop hoặc contention. Chỉ nhìn một biểu đồ CPU không đủ để kết luận.

## 3. Luồng chẩn đoán tổng quát

~~~mermaid
flowchart TD
    A["Ghi nhận triệu chứng và thời điểm"] --> B["Xác định PID, JDK và JVM arguments"]
    B --> C["Thu thập dữ liệu ít tác động"]
    C --> D{"Triệu chứng chính"}
    D -->|"Treo / chậm"| E["Lấy nhiều thread dump và JFR"]
    D -->|"Heap / GC"| F["GC log, heap info, histogram"]
    D -->|"Native memory"| G["NMT và OS / cgroup metrics"]
    D -->|"Crash / startup"| H["hs_err, core dump, stderr"]
    E --> I["Đối chiếu timeline và giả thuyết"]
    F --> I
    G --> I
    H --> I
    I --> J["Chọn phép đo tiếp theo có mục tiêu"]
    J --> K["Sửa nguyên nhân và xác nhận sau thay đổi"]
~~~

Thứ tự ưu tiên thường là:

1. Xác định đúng process và môi trường.
2. Thu thập version, command line, flags, uptime và application logs.
3. Thu thập thread dump hoặc JFR nếu có vấn đề hiệu năng.
4. Kiểm tra heap và GC nếu nghi ngờ memory pressure.
5. Dùng histogram hoặc heap dump khi cần phân tích object retention.
6. Dùng NMT và công cụ OS khi RSS vượt xa heap.
7. Phân tích hs_err/core dump nếu JVM crash.
8. So sánh dữ liệu trước và sau khi sửa.

## 4. Chuẩn bị bằng chứng và mốc thời gian

Trước khi chạy công cụ, ghi lại:

- Thời điểm bắt đầu và kết thúc sự cố, ưu tiên UTC.
- PID của Java process và tên ứng dụng.
- Host, container, pod hoặc service instance.
- JDK vendor, version, build number và architecture.
- JVM command line, heap limits, collector và các flags.
- Application release, commit SHA và cấu hình đang chạy.
- CPU, RAM, disk, network và container memory limit.
- Request ID, correlation ID hoặc job ID liên quan.
- Thay đổi gần nhất: deploy, config, dependency, traffic hoặc infrastructure.

Ghi thời gian lấy từng dump để đối chiếu với application log, GC log và metrics. Khi so sánh hai môi trường, phải kiểm tra cả JDK build, JVM flags, container limit, traffic và dependency version.

Không dump toàn bộ environment vào log thông thường. JVM arguments, system properties, environment variables và diagnostic files có thể chứa token, password, connection string hoặc dữ liệu cá nhân.

## 5. Xác định đúng Java process

Dùng JDK tools từ thư mục bin của JDK. Trên Windows, tên executable có phần mở rộng .exe; trên Linux/macOS, gọi tên lệnh trực tiếp.

Liệt kê JVM mà JDK có thể quan sát:

~~~bash
jcmd -l
~~~

Có thể dùng:

~~~bash
jps -lv
~~~

jcmd -l hiển thị PID, main class/module và arguments của các JVM được công cụ nhận diện. Trong môi trường container, process có thể nằm trong PID namespace riêng; jcmd -l từ host không nhất thiết liệt kê process nằm trong một Docker container tách biệt. Khi đó, chạy công cụ trong đúng container hoặc namespace và dùng ps để xác định PID.

Trên Linux:

~~~bash
ps -eo pid,ppid,user,stat,%cpu,%mem,rss,etime,args | grep '[j]ava'
~~~

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe' OR Name = 'javaw.exe'" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
~~~

Không nhầm PID của Java process với native thread ID trong thread dump. PID được dùng để gọi jcmd; thread ID giúp liên kết thread Java với OS thread.

## 6. Điều kiện để attach bằng jcmd

jcmd gửi diagnostic command tới một JVM đang chạy. Theo tài liệu JDK 17, công cụ phải chạy trên cùng máy và cùng effective user/group ID đã khởi chạy JVM.

Nếu attach thất bại, kiểm tra:

- PID có đúng và process còn chạy không.
- Công cụ có chạy dưới đúng user không.
- Công cụ có đang ở cùng host/container/PID namespace không.
- JDK có tương thích với JVM mục tiêu không.
- JVM có tắt cơ chế attach bằng DisableAttachMechanism không.
- Security policy, endpoint protection hoặc OS permission có chặn attach không.
- Process đang treo sâu trong VM hoặc native code hay không.

Dùng help để xem lệnh thực sự có trên JVM đó:

~~~bash
jcmd 12345 help
jcmd 12345 help Thread.print
jcmd 12345 help GC.heap_dump
~~~

Các diagnostic command có thể khác nhau giữa JVM implementation và JDK release. Không giả định mọi lệnh đều có trên mọi runtime.

## 7. Lấy thông tin nền của JVM

Bắt đầu bằng các lệnh có tác động thấp:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.uptime
jcmd 12345 VM.info
~~~

Ý nghĩa:

| Lệnh | Thông tin |
|---|---|
| VM.version | Phiên bản HotSpot và JDK build |
| VM.command_line | JVM arguments, main class và classpath |
| VM.flags | Flags đang có hiệu lực, kể cả giá trị mặc định |
| VM.uptime | Thời gian JVM đã chạy |
| VM.info | Thông tin tổng quan của VM |
| VM.system_properties | System properties của process |

VM.system_properties có thể chứa thông tin nhạy cảm hoặc endpoint nội bộ. Chỉ thu thập khi cần và phải redact trước khi chia sẻ.

Ngoài ra, ghi lại phiên bản từ launcher:

~~~bash
java -version
javac -version
~~~

java -version cho biết runtime được gọi từ PATH hiện tại. jcmd PID VM.version cho biết JVM của process mục tiêu. Hai giá trị có thể khác nhau nếu máy có nhiều JDK.

## 8. Đọc JVM flags và giới hạn heap

Lệnh VM.flags hiển thị các cờ đang được JVM sử dụng:

~~~bash
jcmd 12345 VM.flags
~~~

Các flag thường cần chú ý:

- InitialHeapSize và MaxHeapSize.
- UseG1GC, UseZGC hoặc collector đang bật.
- MaxMetaspaceSize và MetaspaceSize.
- ThreadStackSize.
- NativeMemoryTracking.
- HeapDumpOnOutOfMemoryError và HeapDumpPath.
- StartFlightRecording.
- Các flag liên quan container và CPU ergonomics.

-Xms là heap size ban đầu, -Xmx là giới hạn heap tối đa. -Xmx không phải giới hạn tổng RAM của process. JVM còn dùng metaspace, code cache, thread stack, direct buffer, GC structures, native libraries và các vùng native khác.

Không tăng -Xmx chỉ vì process RSS tăng. Trước tiên phải xác định phần memory nào đang tăng.

## 9. Thu thập thread dump

Thread dump cho biết thread Java đang ở đâu, đang chạy, chờ monitor, chờ condition hay bị block.

Lệnh khuyến nghị:

~~~bash
jcmd 12345 Thread.print -l
~~~

Tùy JVM, có thể yêu cầu thêm thông tin mở rộng:

~~~bash
jcmd 12345 Thread.print -e
~~~

Thread.print -l bao gồm thông tin về các lock của java.util.concurrent. Diagnostic command này có tác động mức trung bình, phụ thuộc số lượng thread.

Để lưu output:

~~~bash
jcmd 12345 Thread.print -l > thread-1.txt
~~~

Không chỉ lấy một thread dump nếu ứng dụng bị treo. Hãy lấy khoảng ba snapshot cách nhau 5 đến 10 giây:

~~~bash
jcmd 12345 Thread.print -l > thread-1.txt
sleep 5
jcmd 12345 Thread.print -l > thread-2.txt
sleep 5
jcmd 12345 Thread.print -l > thread-3.txt
~~~

So sánh stack trace của cùng thread qua nhiều snapshot:

- Stack không đổi trong thời gian dài có thể cho thấy thread đang chờ hoặc bị kẹt.
- Stack thay đổi liên tục có thể cho thấy thread đang tiến triển.
- RUNNABLE lặp lại ở cùng một đoạn code có thể là vòng lặp CPU cao.
- BLOCKED thường liên quan đến việc chờ monitor.
- WAITING hoặc TIMED_WAITING có thể là chờ condition, queue, sleep hoặc I/O.
- Nhiều thread cùng chờ một lock có thể cho thấy lock contention.

RUNNABLE không đồng nghĩa chắc chắn đang sử dụng CPU. Cần đối chiếu native thread ID, OS thread metrics và JFR.

## 10. Phát hiện deadlock và lock contention

Thread dump của HotSpot có thể phát hiện một số deadlock dựa trên monitor và các synchronizer mà JVM hỗ trợ.

~~~bash
jcmd 12345 Thread.print -l
~~~

Tìm phần báo cáo deadlock và xem:

- Thread nào đang giữ lock.
- Thread nào đang chờ lock.
- Chuỗi phụ thuộc giữa các thread.
- Stack trace tại điểm acquire lock.
- Lock có được giữ trong khi gọi network, disk hoặc callback không.

Deadlock Java thường tạo chu trình chờ: Thread A giữ lock 1 và chờ lock 2, trong khi Thread B giữ lock 2 và chờ lock 1.

Nếu không có deadlock nhưng nhiều thread cùng bị BLOCKED, có thể hệ thống đang bị contention. Hãy dùng JFR để xem thời gian chờ monitor và tìm critical section gây nghẽn.

## 11. Chẩn đoán CPU cao

CPU cao có thể do:

- Một thread chạy vòng lặp hoặc tính toán quá nhiều.
- Nhiều request đồng thời làm tăng allocation và GC.
- Lock contention khiến nhiều thread hoạt động nhưng ít tiến triển.
- JIT compiler hoặc class loading tăng tải trong startup.
- Serialization, regex, parsing hoặc xử lý dữ liệu quá nặng.
- Native method hoặc JNI library sử dụng CPU.

Quy trình:

1. Ghi nhận CPU của process và từng OS thread.
2. Lấy vài thread dump cách nhau vài giây.
3. So sánh các thread RUNNABLE và stack trace lặp lại.
4. Thu JFR profile trong một khoảng thời gian có triệu chứng.
5. Đối chiếu Execution Sample, Thread CPU Load, GC và monitor events.
6. Xác định method hoặc subsystem chiếm thời gian.
7. Sửa code hoặc cấu hình rồi đo lại trên cùng workload.

Trên Linux, có thể dùng:

~~~bash
top -H -p 12345
ps -L -p 12345 -o pid,tid,psr,pcpu,stat,comm
~~~

Không kết luận từ một snapshot. Một thread có thể RUNNABLE tại thời điểm dump nhưng chỉ sử dụng CPU trong thời gian ngắn.

## 12. Kiểm tra heap hiện tại

Lấy thông tin tổng quan:

~~~bash
jcmd 12345 GC.heap_info
~~~

Lệnh này giúp xem loại heap, tổng dung lượng, lượng đã dùng, vùng young/survivor và metaspace. Đây là snapshot tại một thời điểm, không thể thay thế việc theo dõi xu hướng.

Để xem thống kê object theo class:

~~~bash
jcmd 12345 GC.class_histogram
~~~

Histogram liệt kê số instance và tổng byte theo class. Các class có số byte lớn được đưa lên đầu. Với HotSpot, mảng byte thường xuất hiện dưới tên [B.

GC.class_histogram có tác động cao và chi phí phụ thuộc heap size/object count. Tránh chạy liên tục trên production khi chưa cần.

Một histogram lớn không tự chứng minh memory leak. Cần xác định object nào còn reachable, ai giữ reference và retained heap của chúng là bao nhiêu.

## 13. Tạo heap dump để tìm object retention

Heap dump là snapshot object graph của Java heap ở định dạng HPROF. Nó giúp phân tích:

- Object nào chiếm nhiều retained heap.
- Collection hoặc cache nào tăng bất thường.
- Reference chain nào giữ object sống.
- Static field hoặc ThreadLocal nào giữ object ngoài dự kiến.
- Classloader nào còn tồn tại sau khi ứng dụng đã reload module.

Dùng jcmd:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
~~~

GC.heap_dump có tác động cao, phụ thuộc kích thước heap và nội dung. Theo help của JDK 17, lệnh yêu cầu Full GC trừ khi sử dụng tùy chọn -all. Cú pháp filename là đối số positional sau lệnh; ví dụ trên là dạng đã kiểm chứng với JDK 17.

Heap dump có thể rất lớn. Trước khi tạo, kiểm tra dung lượng đĩa (disk space), quyền ghi, vị trí output và thời gian pause có thể chấp nhận được không.

Mở HPROF bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích. Bắt đầu với:

- Histogram: class nào có nhiều instance/bytes.
- Dominator Tree: object nào giữ nhiều memory.
- Retained Heap: lượng memory có thể được giải phóng nếu object bị loại bỏ.
- Path to GC Roots: reference chain giữ object sống.
- Leak Suspects: các cụm object đáng điều tra.

Không chỉ nhìn Shallow Heap. Một object nhỏ có thể giữ một graph rất lớn.

## 14. Tự động tạo heap dump khi OutOfMemoryError

Có thể cấu hình JVM tạo heap dump khi gặp OutOfMemoryError:

~~~bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=./diagnostics \
  -jar app.jar
~~~

Tạo thư mục diagnostics trước khi khởi chạy và bảo đảm process có quyền ghi. Nếu không chỉ định path, file mặc định có thể được tạo ở working directory của process.

Heap dump có thể gần bằng kích thước heap và chứa dữ liệu nhạy cảm. Cần có quota, retention, access control và quy trình xóa phù hợp. Không để nhiều heap dump tích tụ làm đầy disk.

Heap dump tự động giúp giữ bằng chứng tại thời điểm OOM. Nó không giải thích nguyên nhân; vẫn cần phân loại thông báo OOM và phân tích retained objects.

## 15. Đọc Garbage Collection log

JDK 9+ sử dụng Unified Logging. Với JDK 17, có thể bật GC log:

~~~bash
java \
  -Xlog:gc*,gc+phases=debug:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Cấu hình trên ghi GC events và phase details vào gc.log, có timestamp, uptime, level, tags và log rotation.

Một cấu hình gọn hơn:

~~~bash
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Trong GC log, theo dõi:

- Tần suất Young GC và Full GC.
- Pause duration và thời gian giữa các lần GC.
- Heap trước/sau GC.
- GC cause.
- Old generation sau Full GC.
- Metaspace usage.
- Allocation pressure và humongous allocation.
- Safepoint duration khi ứng dụng bị pause.

Nếu Full GC liên tục nhưng heap sau GC gần như không giảm, live set có thể quá lớn hoặc có object bị giữ lại. Nếu heap giảm tốt nhưng GC xảy ra quá thường xuyên, có thể allocation rate cao hoặc heap quá nhỏ.

Không đổi collector chỉ dựa trên số lần GC. Hãy liên kết GC pause với latency, throughput, allocation và workload.

## 16. Hiểu OutOfMemoryError theo loại tài nguyên

OutOfMemoryError không phải lúc nào cũng là Java heap leak.

| Thông báo | Ý nghĩa thường gặp | Bằng chứng cần thu |
|---|---|---|
| Java heap space | Không cấp phát được object trong Java heap | GC log, histogram, heap dump, Xmx |
| GC overhead limit exceeded | GC chạy phần lớn thời gian nhưng thu hồi rất ít heap | GC log, live set, heap dump |
| Metaspace | Không đủ native memory cho class metadata | VM.metaspace, classloader stats, class load/unload |
| Compressed class space | Hết vùng lưu metadata cho compressed class pointers | VM.flags, metaspace và class loading |
| Direct buffer memory | Không cấp phát được direct buffer | Direct buffer metrics, NMT và library usage |
| unable to create native thread | Không tạo thêm OS thread được | Thread count, OS limits, native memory, stack size |
| Requested array size exceeds VM limit | Mảng yêu cầu vượt giới hạn VM | Allocation size và code tạo array |
| Native allocation failure | Native memory hoặc tài nguyên hệ điều hành cạn | NMT, OS memory, swap, JNI/native library |

Với Java heap space, vấn đề có thể là heap quá nhỏ so với workload, allocation spike hoặc memory leak. Không tăng Xmx trước khi kiểm tra live set sau GC.

GC overhead limit exceeded thường cho thấy JVM dành phần lớn thời gian cho GC nhưng thu hồi được rất ít bộ nhớ. Theo quy tắc HotSpot, trường hợp này có thể được báo khi GC chiếm khoảng 98% thời gian, thu hồi dưới 2% heap và lặp qua nhiều chu kỳ GC liên tiếp. Đây là tín hiệu cần phân tích heap và allocation, không phải chỉ tắt cảnh báo.

## 17. Phân biệt heap leak và native memory growth

Java process dùng nhiều loại memory:

- Java heap chứa object.
- Metaspace chứa class metadata.
- Compressed class space chứa class metadata trong vùng riêng.
- Code cache chứa code đã JIT compile.
- Thread stack cho từng thread.
- Direct buffers và native allocations.
- GC, compiler, symbol table, VM structures.
- JNI/native libraries và các memory mapping khác.

Nếu RSS/container memory tăng nhưng heap usage không tăng tương ứng, hãy xem xét direct buffer, thread stack, metaspace, JNI/native library, memory mapping và các process khác.

Không lấy RSS trừ Xmx rồi kết luận đó là native leak. Xmx là giới hạn heap, không phải lượng heap đã commit hoặc tổng memory của process.

## 18. Native Memory Tracking (NMT)

NMT theo dõi các allocation nội bộ của HotSpot JVM. Phải bật khi JVM khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Để có stack allocation chi tiết hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Detail cung cấp thêm thông tin nhưng có overhead cao hơn. Theo tài liệu Oracle JDK 17, NMT có thể làm giảm hiệu năng JVM khoảng 5–10% và tự sử dụng thêm memory cho tracking. Chỉ bật mức chi tiết khi cần.

Lấy thống kê:

~~~bash
jcmd 12345 VM.native_memory summary
~~~

Đặt baseline sau khi ứng dụng đã warm up:

~~~bash
jcmd 12345 VM.native_memory baseline
~~~

Lấy chênh lệch sau một khoảng tải:

~~~bash
jcmd 12345 VM.native_memory summary.diff
jcmd 12345 VM.native_memory detail.diff
~~~

Các nhóm thường gặp gồm Java Heap, Class, Thread, Code, GC, Compiler, Internal, Symbol và Native Memory Tracking.

NMT chỉ theo dõi allocation nội bộ JVM. Nó không bao phủ mọi allocation do native code bên ngoài JVM hoặc JNI library thực hiện. Nếu nghi ngờ native leak ngoài JVM, dùng công cụ OS như pmap trên Linux hoặc PerfMon trên Windows và so sánh theo thời gian.

## 19. Đọc reserved và committed trong NMT

NMT thường hiển thị hai số:

- **Reserved:** vùng địa chỉ ảo JVM đã đặt trước.
- **Committed:** vùng đã được commit để JVM có thể sử dụng.

Reserved lớn không tự có nghĩa process đang tiêu thụ lượng RAM tương ứng. Trên hệ thống 64-bit, JVM có thể reserve một vùng heap lớn nhưng mới commit một phần.

Khi điều tra memory pressure, quan tâm xu hướng committed, OS resident memory, container limit và từng category. Đối chiếu cùng thời điểm thay vì so hai snapshot ở tải khác nhau.

Ví dụ, nếu Thread committed tăng cùng thread count, kiểm tra thread pool hoặc thread leak. Nếu Class/Metaspace tăng cùng số class loaded, kiểm tra classloader lifecycle. Nếu Internal hoặc Other tăng nhưng heap ổn định, tiếp tục bằng native tools và JFR.

## 20. Chẩn đoán Metaspace và classloader

Metaspace tăng có thể do:

- Ứng dụng tạo nhiều class động.
- Framework proxy hoặc bytecode generation tạo class liên tục.
- Plugin/module reload nhưng classloader cũ còn reference.
- ThreadLocal, static registry hoặc callback giữ classloader.
- Class unloading không xảy ra như mong đợi.

Các lệnh hữu ích:

~~~bash
jcmd 12345 VM.metaspace
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.classloaders
~~~

Bật log class loading/unloading khi cần:

~~~bash
-Xlog:class+load=info,class+unload=info
~~~

Theo dõi số class được load/unload và Metaspace qua nhiều chu kỳ deploy. Nếu số class và classloader tăng liên tục sau mỗi lần reload, kiểm tra reference tới classloader cũ.

Tăng MaxMetaspaceSize có thể trì hoãn OOM nhưng không xử lý classloader leak.

## 21. Java Flight Recorder (JFR)

JFR thu thập event về JVM và ứng dụng như CPU load, thread activity, allocation, GC, class loading, lock contention, file I/O và socket I/O.

Có thể bắt đầu recording cùng lúc khởi động JVM:

~~~bash
java \
  -XX:StartFlightRecording=filename=recording.jfr,duration=2m,settings=profile \
  -jar app.jar
~~~

Hoặc bắt đầu trên process đang chạy:

~~~bash
jcmd 12345 JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd 12345 JFR.check
~~~

Dump dữ liệu của recording đang chạy:

~~~bash
jcmd 12345 JFR.dump name=incident filename=incident-partial.jfr
~~~

Dừng recording:

~~~bash
jcmd 12345 JFR.stop name=incident
~~~

Phân tích file:

~~~bash
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
~~~

Có thể mở file JFR bằng JDK Mission Control (JMC) để xem timeline, CPU, threads, allocation, GC, lock và I/O.

Recording profile trong một khoảng thời gian cố định thường có overhead thấp, nhưng mức thực tế phụ thuộc workload và event settings. Theo tài liệu Oracle, recording profile chuẩn với default settings thường dưới 2% với phần lớn ứng dụng. Heap Statistics có thể gây Full GC ở đầu và cuối recording; không bật tùy tiện trong bài đo latency nhạy cảm.

## 22. Continuous Flight Recording

JFR có thể chạy liên tục với buffer dạng vòng để giữ lại sự kiện gần đây. Khi sự cố xuất hiện, nhóm có thể dump dữ liệu của khoảng thời gian trước đó.

Ví dụ cấu hình recording liên tục:

~~~bash
java \
  -XX:StartFlightRecording=disk=true,maxage=1h,maxsize=250m \
  -jar app.jar
~~~

Khi cần lấy bằng chứng:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=incident-last-hour.jfr
~~~

Continuous recording hữu ích khi lỗi hiếm, không thể dự đoán thời điểm xảy ra. Cần đặt giới hạn tuổi/kích thước, quản lý disk và xác định nơi lưu file.

JFR recording có thể chứa thông tin về process, environment, file path, exception, host, thread và hoạt động ứng dụng. Xử lý file recording như dữ liệu nhạy cảm.

## 23. Dùng jstat để quan sát GC theo chu kỳ

jstat cung cấp thống kê JVM theo chu kỳ. Ví dụ:

~~~bash
jstat -gcutil 12345 1000 10
~~~

Lệnh lấy mẫu mỗi 1.000 ms, tổng cộng 10 lần. Các cột thường thể hiện phần trăm sử dụng các vùng heap, số lần GC và thời gian GC.

Có thể dùng jstat để quan sát nhanh xu hướng trước khi bật thêm logging. Tuy nhiên, jstat chỉ cung cấp số liệu tổng hợp; nó không cho biết object nào đang được giữ hoặc thread nào đang chặn request.

Kết hợp jstat với GC log, JFR và heap analysis khi cần xác định nguyên nhân.

## 24. Chẩn đoán JVM crash và fatal error log

Một exception Java thường tạo stack trace trong application log. JVM crash là trường hợp runtime hoặc native code gặp lỗi nghiêm trọng, ví dụ SIGSEGV, access violation hoặc lỗi trong JNI library.

HotSpot thường tạo file hs_err_pid khi gặp fatal error. Có thể chỉ định vị trí:

~~~bash
java \
  -XX:ErrorFile=./diagnostics/hs_err_pid%p.log \
  -jar app.jar
~~~

Tạo thư mục diagnostics trước khi khởi chạy và bảo đảm có quyền ghi. Nếu không chỉ định, JVM thường thử ghi file vào working directory; nếu không thể, nó có thể dùng temporary directory của OS.

Fatal error log có thể chứa:

- Signal/exception gây crash.
- JDK và JVM version/configuration.
- Thread gây lỗi và stack trace.
- Các thread đang chạy và trạng thái.
- Heap summary.
- Native libraries đã load.
- Command-line arguments.
- Environment variables.
- OS và CPU information.

Tìm phần Problematic frame, Current thread, Native frames, Loaded libraries và VM arguments. Nếu frame trỏ tới thư viện JNI hoặc native library, điều tra binary, version, ABI và memory handling của thư viện đó.

Không coi mọi SIGSEGV là lỗi Java source. Có thể là lỗi VM, native code, driver hoặc memory corruption. Cần giữ hs_err log và core dump trước khi restart nếu có thể.

## 25. Core dump và công cụ hệ điều hành

Core dump là snapshot process do OS tạo khi process crash hoặc được yêu cầu. File có thể rất lớn và cần dung lượng lưu trữ đáng kể.

Trên Linux, nếu chính sách hệ thống cho phép, có thể bật core dump cho shell hiện tại:

~~~bash
ulimit -c unlimited
~~~

Vị trí và cách quản lý core dump phụ thuộc kernel, systemd, container runtime và cấu hình host.

Với core dump HotSpot, có thể dùng Serviceability Agent:

~~~bash
jhsdb jstack --exe /path/to/java --core /path/to/core
~~~

Để lấy mixed Java/native stack từ process đang chạy, JDK có lệnh jhsdb jstack với tùy chọn --mixed. Đây là thao tác chuyên sâu và có thể ảnh hưởng process; chỉ dùng khi thread dump thông thường không đủ hoặc JVM không phản hồi.

Công cụ OS cần phối hợp:

- Linux: ps, top, top -H, pmap, vmstat, iostat, dmesg và cgroup files.
- Windows: Task Manager, Process Explorer, PerfMon, Event Viewer và Windows Error Reporting.
- macOS: Activity Monitor, sample, vmmap và Console.

Đối chiếu thời điểm crash với OS logs để tìm OOM killer, access violation, disk full, permission issue hoặc native library failure.

## 26. Chẩn đoán ứng dụng chạy trong container

Trong container, giới hạn RAM/CPU của cgroup có thể thấp hơn tài nguyên của host. JVM có thể bị kill dù heap chưa đạt -Xmx.

Tổng memory của process có thể gồm:

- Java heap.
- Metaspace và class space.
- Thread stacks.
- Direct buffers.
- Code cache.
- GC/native structures.
- JNI/native libraries.
- Memory-mapped files.

Trên Linux cgroup v2, kiểm tra:

~~~bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
~~~

Với cgroup v1, đường dẫn và tên file khác nhau, thường có memory.usage_in_bytes và memory.limit_in_bytes.

Exit code 137 thường xuất hiện khi process nhận SIGKILL trong container, nhưng không đủ để kết luận chắc chắn là OOM kill. Kiểm tra memory.events, kernel logs, pod events và container runtime events.

Nếu heap ổn định nhưng container memory tăng, kiểm tra direct buffer, thread count, native memory, JNI và các process khác trong cùng cgroup. Không đặt -Xmx bằng toàn bộ container memory; phải chừa phần cho non-heap/native và OS overhead.

## 27. Lỗi startup và linkage thường gặp

| Lỗi | Hướng điều tra |
|---|---|
| Could not find or load main class | Kiểm tra main class, classpath, module path và working directory |
| NoClassDefFoundError | Kiểm tra dependency runtime, classloader và lỗi khởi tạo trước đó |
| NoSuchMethodError | Kiểm tra dependency version và binary compatibility |
| UnsupportedClassVersionError | Class được compile bằng Java mới hơn runtime đang chạy |
| ExceptionInInitializerError | Xem root cause trong phần Caused by |
| Unrecognized VM option | Flag không tồn tại hoặc không hỗ trợ trên JDK hiện tại |
| Could not reserve enough space for object heap | Heap reservation, process architecture, address space hoặc OS limits |
| Native library load failed | Kiểm tra native library path, architecture, ABI và dependencies hệ điều hành |

Luôn đọc exception đầu tiên và chuỗi Caused by. Exception cuối cùng có thể chỉ là hậu quả của một lỗi khởi tạo trước đó.

## 28. Đánh giá memory leak bằng xu hướng

Memory leak trong Java thường là object vẫn còn reachable qua một reference chain ngoài ý muốn.

Dấu hiệu mạnh:

- Heap sau GC tăng dần qua các chu kỳ tải tương đương.
- Full GC không thu hồi được nhiều old-generation memory.
- Một nhóm class tăng số instance hoặc retained heap theo thời gian.
- Cache, collection, listener, ThreadLocal hoặc static registry không giải phóng dữ liệu.
- Classloader hoặc Metaspace tăng sau mỗi lần reload.

Quy trình:

1. Thu GC log và heap usage trong tải ổn định.
2. Lấy histogram tại hai hoặc nhiều thời điểm.
3. So sánh class count và bytes.
4. Tạo heap dump khi có đủ bằng chứng.
5. Dùng dominator tree và path to GC roots để tìm reference chain.
6. Sửa lifecycle hoặc ownership của object.
7. Chạy lại cùng workload và so sánh live set sau GC.

Một heap lớn không tự là leak. Ứng dụng có thể có live set lớn hợp lệ. Phải xem mức tăng có tiếp tục khi workload và trạng thái đã ổn định hay không.

## 29. Quy trình production-safe theo mức tác động

| Mức | Công cụ | Khi dùng |
|---|---|---|
| Thấp | jcmd -l, VM.version, VM.flags, VM.uptime | Nhận diện process và môi trường |
| Thấp | GC.heap_info, VM.classloader_stats | Kiểm tra snapshot tổng quan |
| Thấp đến trung bình | JFR.start, JFR.check, JFR.dump | Phân tích performance theo thời gian |
| Trung bình | Thread.print -l | Treo, deadlock, lock contention |
| Trung bình | VM.native_memory summary | Native memory khi NMT đã bật |
| Cao | GC.class_histogram | Cần xác định class chiếm heap |
| Cao | GC.heap_dump | Phân tích object graph/retained heap |

Trước khi tạo heap dump hoặc histogram trên production:

- Kiểm tra dung lượng đĩa và output path.
- Ước lượng heap size và số object.
- Xác định pause/impact có thể chấp nhận.
- Dùng đúng user và PID namespace.
- Ghi timestamp và lý do thu thập.
- Giới hạn quyền truy cập file.
- Không upload file lên nơi chia sẻ công khai.
- Không restart process trước khi lấy dữ liệu cần thiết, trừ khi hệ thống cần khôi phục dịch vụ ngay.

Thu thập đủ bằng chứng để trả lời câu hỏi hiện tại. Không bật tất cả logging/profile ở mức cao cùng lúc vì có thể tạo thêm tải và làm thay đổi triệu chứng.

## 30. Ví dụ Java 17 để thực hành chẩn đoán

Tạo file JvmDiagnosticDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class JvmDiagnosticDemo {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 24; i++) {
            RETAINED.add(new byte[512 * 1024]);
        }

        CountDownLatch stop = new CountDownLatch(1);
        for (int i = 1; i <= 2; i++) {
            Thread worker = new Thread(() -> {
                try {
                    stop.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, "diagnostic-worker-" + i);
            worker.setDaemon(true);
            worker.start();
        }

        System.out.println(
            "diagnostic-demo-ready pid=" + ProcessHandle.current().pid()
        );
        Thread.sleep(120_000);
    }
}
~~~

Compile bằng JDK 17:

~~~bash
javac --release 17 JvmDiagnosticDemo.java
~~~

Chạy với heap giới hạn, NMT, GC log và JFR:

~~~bash
java \
  -Xms64m \
  -Xmx128m \
  -XX:NativeMemoryTracking=summary \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -XX:StartFlightRecording=filename=recording.jfr,duration=2m,settings=profile \
  JvmDiagnosticDemo
~~~

Chương trình in PID theo dạng:

~~~text
diagnostic-demo-ready pid=12345
~~~

Từ terminal thứ hai, thay PID bằng giá trị thực:

~~~bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 Thread.print -l
jcmd 12345 GC.heap_info
jcmd 12345 GC.class_histogram
jcmd 12345 VM.native_memory summary
~~~

Có thể thực hành thêm heap dump và JFR:

~~~bash
jcmd 12345 GC.heap_dump heap.hprof
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=incident.jfr
jfr summary incident.jfr
~~~

Heap dump có thể yêu cầu Full GC và tạo file lớn. Chỉ chạy lệnh đó trên sample hoặc môi trường có thể chấp nhận tác động.

## 31. Kết quả kiểm chứng bằng JDK 17.0.15

Một sample Java 17 được compile và chạy bằng Amazon Corretto 17.0.15 trên Windows 11. JVM được khởi động với heap 64–128 MB, NMT summary, Unified GC Logging và Flight Recorder. Với javac --release 17, class file có major version 61.

Các thao tác đã chạy thành công:

| Thao tác | Kết quả quan sát |
|---|---|
| jcmd -l | Tìm được PID và main class JvmDiagnosticDemo |
| VM.version | Báo OpenJDK 64-Bit Server VM 17.0.15+6-LTS |
| VM.command_line | Hiển thị -Xms, -Xmx, NMT, GC log và JFR flags |
| VM.flags | Xác nhận MaxHeapSize 128 MB, UseG1GC và NMT summary |
| Thread.print -l | Hiển thị diagnostic-worker-1 và diagnostic-worker-2 |
| GC.heap_info | Hiển thị G1 heap, used heap và Metaspace |
| GC.class_histogram | Mảng byte [B xuất hiện trong nhóm object lớn |
| VM.native_memory summary | Hiển thị Java Heap, Class, Thread và các category native |
| VM.native_memory baseline/summary.diff | Lấy baseline và chênh lệch allocation thành công |
| GC.heap_dump heap2.hprof | Tạo HPROF heap dump khoảng 19 MB |
| JFR.start và jfr summary | Tạo recording 5 giây và đọc được event summary |
| Unified GC logging | Ghi gc.log với timestamp và log rotation |

Kết quả này xác nhận cú pháp và luồng thao tác trên sample HotSpot JDK 17.0.15. Nó không chứng minh mọi lệnh có cùng tác động trên mọi JVM hoặc workload production. Luôn xem help của process mục tiêu và đánh giá impact trước khi thu thập dữ liệu lớn.

## 32. Checklist khi xử lý một JVM incident

- [ ] Ghi nhận thời điểm, PID, host/container và symptom.
- [ ] Xác định JDK vendor/version/build của process.
- [ ] Thu JVM command line và flags.
- [ ] Ghi heap limits, container memory/CPU limits và OS resource limits.
- [ ] Giữ application logs và GC logs quanh thời điểm lỗi.
- [ ] Nếu treo/chậm, lấy nhiều thread dump cách nhau vài giây.
- [ ] Nếu CPU cao, đối chiếu OS thread usage và JFR.
- [ ] Nếu heap tăng, so sánh heap sau GC và histogram.
- [ ] Nếu cần, tạo heap dump sau khi kiểm tra disk và impact.
- [ ] Nếu RSS tăng ngoài heap, kiểm tra NMT và OS/cgroup metrics.
- [ ] Nếu Metaspace tăng, kiểm tra classloader stats và class load/unload.
- [ ] Nếu JVM crash, giữ hs_err log, core dump và OS logs.
- [ ] Redact secret và dữ liệu nhạy cảm trước khi chia sẻ.
- [ ] Ghi lại giả thuyết, bằng chứng và kết quả từng phép đo.
- [ ] Sau khi sửa, chạy lại cùng workload và so sánh metrics.

## 33. Lỗi chẩn đoán thường gặp

| Cách làm sai | Vì sao không hiệu quả | Cách làm tốt hơn |
|---|---|---|
| Tăng Xmx ngay khi thấy OOM | Có thể che leak hoặc native memory issue | Phân loại OOM và kiểm tra live set |
| Chỉ lấy một thread dump | Không thấy tiến triển hay trạng thái lặp lại | Lấy nhiều snapshot theo thời gian |
| Kết luận memory leak từ heap used cao | Heap có thể đang chứa cache hợp lệ | So sánh heap sau GC và retained heap |
| Dùng jmap/jstack trước khi thử jcmd | Đây là công cụ cũ hơn trong hướng dẫn JDK 17 | Ưu tiên jcmd; dùng công cụ chuyên biệt khi cần |
| Tạo heap dump mà không kiểm tra disk | Có thể làm đầy filesystem | Kiểm tra kích thước heap và disk trước |
| Bật NMT detail vĩnh viễn mà không đo overhead | Có thể ảnh hưởng hiệu năng | Bật summary trước, detail khi cần |
| Chỉ nhìn CPU tổng của process | Không xác định thread hoặc stack gây tải | Kết hợp OS thread metrics và JFR |
| Restart trước khi thu bằng chứng | Mất thread state, recording và process context | Thu thập dữ liệu cần thiết trước nếu an toàn |
| Xem exit 137 là bằng chứng duy nhất của OOM | SIGKILL có nhiều nguyên nhân | Kiểm tra cgroup/kernel/container events |
| Chia sẻ heap dump/JFR công khai | Có thể lộ dữ liệu ứng dụng và secret | Kiểm soát access, redact và retention |

## 34. Tài liệu tham khảo

- Oracle — Java SE 17 Troubleshooting Guide: https://docs.oracle.com/en/java/javase/17/troubleshoot/
- Oracle — Prepare Java for Troubleshooting: https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html
- Oracle — Diagnostic Tools for Java 17: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle — The jcmd Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle — The java Command and Unified Logging: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle — Debug JVM Issues: https://docs.oracle.com/en/java/javase/17/troubleshoot/debug-jvm-issues.html
- Oracle — Java Flight Recorder API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle — JDK Mission Control: https://www.oracle.com/java/technologies/jdk-mission-control.html

Chẩn đoán JVM hiệu quả dựa trên dữ liệu có mốc thời gian và mức tác động được kiểm soát. Bắt đầu bằng nhận diện process, version và flags; dùng thread dump/JFR cho vấn đề hiệu năng, GC log/histogram/heap dump cho heap, NMT/OS metrics cho native memory và hs_err/core dump cho crash. Sau mỗi thay đổi, chạy lại cùng điều kiện để xác nhận nguyên nhân đã được xử lý.