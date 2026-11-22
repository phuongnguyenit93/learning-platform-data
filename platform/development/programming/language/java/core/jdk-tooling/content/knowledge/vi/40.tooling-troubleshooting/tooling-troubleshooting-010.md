# Quy trình chẩn đoán sự cố Java

Chẩn đoán là quá trình thu thập bằng chứng để xác định sự cố nằm ở ứng dụng, JVM, JDK, dependency hay hệ điều hành. Một quy trình tốt bắt đầu bằng triệu chứng có thể kiểm chứng, ghi lại trạng thái ban đầu, chọn công cụ phù hợp với giả thuyết và kiểm tra kết quả sau mỗi thay đổi.

Trong Java Core JDK Tooling, các công cụ thường dùng nhất là jcmd, Java Flight Recorder (JFR), jfr, jstat, jdeps, jar, javap và các công cụ hệ điều hành. jcmd gửi lệnh chẩn đoán trực tiếp tới JVM đang chạy; JFR ghi lại sự kiện runtime để phân tích sau; các công cụ còn lại giúp kiểm tra GC, module, bytecode, archive và trạng thái process.

Mục tiêu không phải chạy tất cả công cụ. Hãy chọn phép đo đủ nhỏ để kiểm tra một giả thuyết, giữ lại bằng chứng và tránh làm thay đổi trạng thái sự cố trước khi hiểu nó.

## 1. Quy trình chẩn đoán tổng quát

~~~text
Ghi nhận triệu chứng và thời điểm
              |
              v
Xác định ứng dụng, PID và môi trường
              |
              v
Thu thập baseline ít tác động
              |
              v
Phân loại: startup / CPU / hang / heap / GC / native / crash
              |
              v
Chọn công cụ và tạo bằng chứng
              |
              v
Đối chiếu log, metrics, thread và recording
              |
              v
Đưa ra giả thuyết có thể kiểm tra
              |
              v
Thay đổi một yếu tố và đo lại
              |
              v
Xác nhận nguyên nhân, lưu kết quả và theo dõi
~~~

Thực hiện theo các bước:

1. Ghi lại điều người dùng hoặc hệ thống quan sát được.
2. Xác định thời điểm bắt đầu, tần suất và phạm vi ảnh hưởng.
3. Ghi nhận phiên bản Java, JVM, OS, container, cấu hình và commit đang chạy.
4. Lưu log, exit code, thread dump hoặc recording phù hợp.
5. Phân loại triệu chứng và chọn công cụ ít tác động trước.
6. So sánh kết quả với trạng thái bình thường hoặc một lần chạy tốt.
7. Nêu giả thuyết và bằng chứng ủng hộ/phản bác.
8. Thay đổi một yếu tố, chạy lại cùng phép đo.
9. Xác nhận sự cố đã hết và theo dõi để phát hiện tái diễn.

Một giả thuyết tốt có thể bị bác bỏ bằng dữ liệu. Ví dụ: “request chậm vì thread chờ database connection” có thể kiểm tra bằng thread dump, JFR socket events, pool metrics và thời gian truy vấn.

## 2. Ghi nhận triệu chứng trước khi chạy công cụ

Không chỉ ghi “ứng dụng chậm” hoặc “Java bị lỗi”. Hãy mô tả sự kiện bằng thông tin cụ thể:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Thời điểm | Lỗi bắt đầu lúc nào? Múi giờ nào? |
| Phạm vi | Toàn bộ service, một instance, một endpoint hay một tác vụ? |
| Tần suất | Liên tục, theo tải, theo lịch hay ngẫu nhiên? |
| Hành vi | Crash, timeout, treo, CPU cao, OOM hay kết quả sai? |
| Tác động | Request lỗi, latency tăng, restart, mất dữ liệu hay chỉ cảnh báo? |
| Tải | Request/second, số kết nối, queue depth và concurrency lúc xảy ra? |
| Thay đổi gần nhất | Release, config, JDK, dependency, traffic, database hoặc hạ tầng? |
| Bằng chứng | Stack trace, log, metric, PID, exit code, dump và recording? |

Ghi lại một khoảng thời gian trước, trong và sau sự cố nếu có thể. Đồng bộ timestamp giữa application log, JVM, container và hệ điều hành. Nếu các máy lệch giờ, so sánh sự kiện có thể dẫn tới kết luận sai.

Phân biệt lỗi xuất hiện lần đầu với lỗi chỉ được phát hiện lần đầu. Ví dụ heap có thể tăng dần trong nhiều giờ trước khi OOM; log OOM chỉ là thời điểm triệu chứng trở nên rõ ràng.

## 3. Xác định đúng Java và process đang chạy

Một máy có thể cài nhiều JDK. Lệnh java trên terminal không nhất thiết là runtime của service. Kiểm tra executable và environment của đúng process.

### Kiểm tra JDK trên terminal

Linux/macOS:

~~~bash
java -version
javac -version
command -v java
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
Get-Command java -All
$env:JAVA_HOME
$env:PATH -split ';'
~~~

Kiểm tra thêm JDK vendor và full version, OS, kernel, CPU architecture, JAVA_HOME, PATH, working directory, Maven/Gradle Wrapper version và runtime flags.

Lệnh sau hiển thị VM settings và system properties của runtime được gọi từ terminal:

~~~bash
java -XshowSettings:properties -version
java -XshowSettings:vm -version
~~~

Hai lệnh này không tự đọc cấu hình của process service đang chạy. Dùng jcmd để lấy thông tin từ đúng JVM.

### Tìm PID

~~~bash
jcmd -l
~~~

Lệnh này liệt kê các JVM mà công cụ nhìn thấy. Có thể dùng:

~~~bash
jcmd
~~~

Trên Linux, các công cụ hệ điều hành cũng có thể giúp tìm process:

~~~bash
ps -ef | grep '[j]ava'
top -p <pid>
~~~

Trên Windows PowerShell:

~~~powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='java.exe' OR Name='javaw.exe'" | Select-Object ProcessId, ExecutablePath, CommandLine
~~~

Trong Docker, jcmd -l có thể không liệt kê JVM nằm trong một Docker process riêng. Hãy lấy PID từ bên trong container và chạy công cụ chẩn đoán trong cùng môi trường. jcmd cần chạy trên cùng máy với JVM và cùng effective user/group đã khởi chạy JVM.

## 4. Thu thập baseline bằng jcmd

jcmd là điểm bắt đầu hữu ích cho nhiều sự cố JVM. Trước tiên, hỏi chính JVM xem nó hỗ trợ lệnh nào:

~~~bash
jcmd <pid> help
~~~

Lấy phiên bản JVM:

~~~bash
jcmd <pid> VM.version
~~~

Lấy lệnh khởi chạy, flags, system properties và uptime:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.uptime
~~~

Lấy trạng thái heap:

~~~bash
jcmd <pid> GC.heap_info
~~~

Những thông tin này giúp phát hiện khác biệt giữa môi trường đang lỗi và môi trường bình thường, ví dụ JDK khác, Xmx khác, collector khác, system property thiếu hoặc service chạy nhầm file cấu hình.

Không chia sẻ nguyên trạng output VM.system_properties hoặc command line nếu có thể chứa password, token, URL nội bộ, credential hay dữ liệu nhạy cảm. Hãy lưu bản gốc ở nơi kiểm soát truy cập và tạo bản đã che thông tin trước khi gửi.

### Điều kiện attach

jcmd phải chạy trên cùng máy và cùng effective user/group với JVM. Nếu attach bị từ chối:

- Xác nhận PID thuộc đúng process và process còn chạy.
- Chạy jcmd bằng user đã khởi động service.
- Kiểm tra công cụ JDK tương thích với JVM đích.
- Kiểm tra container PID namespace và mount/runtime environment.
- Xác nhận JVM không tắt cơ chế attach bằng cấu hình khởi động.
- Kiểm tra thông báo lỗi thực tế trước khi kết luận nguyên nhân.

Không suy ra rằng ứng dụng đã hỏng chỉ vì jcmd không attach được. Khi không thể attach, dùng log, JMX đã được cấu hình, JFR recording có sẵn hoặc công cụ hệ điều hành phù hợp.

## 5. Chọn công cụ theo triệu chứng

| Triệu chứng | Bằng chứng nên lấy trước | Công cụ phù hợp |
|---|---|---|
| Không khởi động | stderr, exit code, Java version, command line | java, jar, jdeps, javap |
| CPU cao | CPU theo process/thread, stack mẫu, recording | top/Task Manager, jcmd, JFR, JMC |
| Treo hoặc timeout | Nhiều thread dump, lock owner, I/O wait | jcmd Thread.print, JFR |
| Deadlock | Thread dump có lock cycle | jcmd Thread.print -l |
| Heap tăng/OOM | Heap info, histogram, heap dump, GC log | jcmd GC.*, jstat, JFR |
| GC pause dài | GC log, pause events, allocation rate | -Xlog:gc*, jstat, JFR |
| RSS cao nhưng heap thấp | Native memory, thread count, native library | NMT, OS tools, JFR |
| Crash JVM | hs_err log, core dump, OS/kernel log | Fatal Error Log, jhsdb, debugger |
| Lỗi class/module | Classpath, module graph, manifest, class version | jar, jdeps, javap, java |
| TLS/network | Exception, certificate chain, socket timing | keytool, JFR, OS/network tools |

Bắt đầu bằng dữ liệu ít tác động. Tăng mức chi tiết khi kết quả đầu tiên chưa đủ để phân biệt các giả thuyết.

## 6. CPU cao và ứng dụng phản hồi chậm

CPU cao có thể do vòng lặp tính toán, retry quá nhiều, serialization, regex, lock contention, logging hoặc số lượng request tăng. CPU thấp nhưng request chậm thường gợi ý thời gian chờ I/O, connection pool, lock hoặc downstream service.

### Quan sát process và thread

Linux:

~~~bash
top -H -p <pid>
~~~

Windows: dùng Task Manager hoặc Performance Monitor để theo dõi CPU của process và thread. So sánh với số request, queue depth, thread pool và CPU của máy/container.

Lấy thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Lấy extended thread information và lock:

~~~bash
jcmd <pid> Thread.print -e -l
~~~

So sánh nhiều thread dump cách nhau khoảng 5–10 giây. Một stack chỉ là ảnh chụp tại một thời điểm. Nếu cùng thread liên tục ở cùng đoạn tính toán và CPU cao, đó là manh mối cho code đang chạy nhiều. Nếu thread lặp lại trạng thái WAITING hoặc BLOCKED, hãy kiểm tra lock owner, queue, socket và downstream dependency.

Trên Linux, có thể so sánh native thread ID trong thread dump với TID từ top -H. Thread dump hiển thị nid ở dạng hexadecimal; chuyển đổi đúng TID trước khi đối chiếu.

Không kết luận mọi thread WAITING đều là lỗi. Thread pool worker chờ task, scheduler và nhiều thread nền có thể ở trạng thái chờ bình thường.

### Dùng JFR để tìm bottleneck

Bắt đầu recording ngắn trên JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

profile thu thập nhiều dữ liệu hơn default và phù hợp recording ngắn khi cần điều tra sâu. Với recording chạy liên tục hoặc môi trường nhạy cảm với overhead, cân nhắc settings=default.

Sau khi recording hoàn tất:

~~~bash
jfr summary incident.jfr
jfr view all-views incident.jfr
~~~

Có thể lọc event cần xem:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.SocketRead,jdk.FileRead incident.jfr
~~~

Dùng JDK Mission Control (JMC) để xem flame graph, thread, lock, GC và I/O theo timeline. Các sự kiện monitor wait/park giúp tìm thời gian chờ đồng bộ; socket/file events giúp phát hiện thời gian chờ I/O; execution samples giúp xác định code đang tiêu thụ CPU.

JFR chỉ ghi những event đã được bật và theo threshold của recording settings. Không thấy event trong file không chứng minh sự kiện đó không xảy ra.

## 7. Treo, timeout và deadlock

Khi ứng dụng treo, trước tiên xác định process còn sống hay đã dừng, CPU có tăng hay không và sự cố ảnh hưởng một request hay toàn bộ process.

Tạo ít nhất ba thread dump ở các thời điểm cách nhau vài giây:

~~~bash
jcmd <pid> Thread.print -l > thread-1.txt
jcmd <pid> Thread.print -l > thread-2.txt
jcmd <pid> Thread.print -l > thread-3.txt
~~~

Trên PowerShell, có thể redirect output bằng:

~~~powershell
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-1.txt
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-2.txt
jcmd <pid> Thread.print -l | Out-File -Encoding utf8 thread-3.txt
~~~

Đọc dump theo trình tự:

1. Tìm thông báo deadlock nếu JVM phát hiện được.
2. Tìm thread đang BLOCKED và monitor/lock mà nó chờ.
3. Xác định thread giữ lock và stack trace của nó.
4. So sánh cùng thread qua các dump để xem trạng thái có thay đổi không.
5. Kiểm tra thread đang chờ socket, file, database hoặc queue.
6. Đối chiếu với request ID, application log và thời điểm timeout.

Deadlock thường tạo chu trình: thread A giữ lock X và chờ Y, trong khi thread B giữ Y và chờ X. Một thread BLOCKED đơn lẻ có thể chỉ đang chờ lock bình thường.

JDK có thể tạo thread dump bằng cơ chế Control+Break. Trên Windows dùng Control+Break trong console của process; trên Linux có thể gửi SIGQUIT bằng kill -QUIT PID. Cách này có thể ghi dump ra stderr/log của JVM, nên phải biết nơi log được thu thập.

Thread.print có tác động phụ thuộc số thread. Nếu process có hàng chục nghìn thread, dump có thể lớn và mất thời gian. Dùng đúng thời điểm và giữ output ở nơi đủ dung lượng.

## 8. Heap, memory leak và OutOfMemoryError

Phân biệt các loại sự cố bộ nhớ:

- Java heap OOM: heap không đủ chỗ cho allocation.
- Metaspace OOM: không gian metadata class không đủ.
- Direct buffer OOM: bộ nhớ direct buffer cạn.
- Native thread creation failure: OS không cấp được thread/stack.
- Native memory OOM: JVM hoặc native library không cấp được bộ nhớ.
- Process bị OS/container kill: có thể không tạo được Java OutOfMemoryError hoặc heap dump.

### Heap info và class histogram

Lấy heap summary:

~~~bash
jcmd <pid> GC.heap_info
~~~

Lấy class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Histogram cho biết loại class nào có nhiều instance hoặc chiếm nhiều heap. Chụp ở các thời điểm khác nhau để xem số lượng object có tiếp tục tăng sau khi tải giảm hay không.

GC.class_histogram có impact cao tùy kích thước heap và nội dung. Không chạy liên tục như một metric rẻ.

### Heap dump

Khi cần phân tích object retention:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Heap dump có thể lớn, tốn thời gian và gây pause; lệnh mặc định có thể yêu cầu full GC. Kiểm tra dung lượng đĩa trước khi chạy. Dùng MAT hoặc công cụ phân tích heap tương thích để tìm dominator tree, retained size, GC roots và object path.

Heap dump thường chứa dữ liệu trong bộ nhớ ứng dụng như token, session, dữ liệu cá nhân, request và cấu hình. Giới hạn quyền truy cập, mã hóa khi lưu/truyền và áp dụng retention policy.

### Chuẩn bị tự động cho OOM

Có thể cấu hình từ lúc khởi động:

~~~bash
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/log/myapp
-XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log
~~~

HeapDumpOnOutOfMemoryError tạo heap dump khi JVM phát hiện OutOfMemoryError. ErrorFile định vị fatal error log cho lỗi VM nghiêm trọng. Bảo đảm thư mục tồn tại, có quyền ghi và đủ dung lượng.

Một process bị cgroup OOM killer hoặc hệ điều hành kill có thể không có cơ hội ghi heap dump. Trong trường hợp đó, kiểm tra container events, kernel log, exit code, memory limit và RSS.

## 9. GC và pause time

Khi GC bị nghi ngờ, đo pause và xu hướng theo thời gian trước khi thay collector hoặc thay heap size.

### GC log

Bật Unified Logging khi khởi động:

~~~bash
-Xlog:gc*,safepoint:file=logs/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Log có thể cho biết tần suất và thời gian GC pause, heap trước/sau collection, allocation pressure, collector phase và safepoint pause ngoài GC. Giữ rotation để tránh log tăng vô hạn.

Không kết luận GC là nguyên nhân chỉ từ một pause dài; hãy đối chiếu request latency, CPU, allocation rate và thời điểm GC.

### Theo dõi bằng jstat

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh lấy 10 mẫu, mỗi mẫu cách nhau 1 giây. Các cột thể hiện mức sử dụng các vùng heap và số/count thời gian GC theo JVM. Tên cột và ý nghĩa chi tiết phụ thuộc option và JDK; xem trợ giúp của đúng bản jstat.

### Phân tích GC bằng JFR

Có thể lọc GC phase pause:

~~~bash
jfr print --events jdk.GCPhasePause incident.jfr
~~~

Đối chiếu thời lượng pause với latency. Nếu heap occupancy tăng sau mỗi chu kỳ và không giảm về mức ổn định, kiểm tra object retention bằng histogram/heap dump. Nếu heap ổn định nhưng process RSS tăng, mở rộng điều tra native memory.

Không gọi System.gc() hoặc jcmd GC.run chỉ để “xem heap có giảm không” trong production. Full GC có thể làm thay đổi chính hiện tượng cần chẩn đoán và gây pause đáng kể.

## 10. Native memory và RSS cao

Heap không phải toàn bộ memory của JVM. Process còn dùng metaspace, code cache, thread stacks, GC structures, direct buffers, JNI/native libraries và các vùng native khác.

Nếu RSS tăng nhưng heap usage tương đối ổn định, hãy kiểm tra native memory, số thread, direct buffer và native library.

### Native Memory Tracking (NMT)

NMT phải được bật khi JVM khởi động:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Có thể chọn detail để lấy thông tin allocation chi tiết hơn:

~~~bash
-XX:NativeMemoryTracking=detail
~~~

NMT có overhead và chỉ theo dõi bộ nhớ nội bộ của HotSpot JVM; nó không theo dõi toàn bộ allocation của native code bên thứ ba. Không thể bật NMT cho một JVM đã chạy nếu lúc khởi động chưa bật.

Lấy summary:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Đặt baseline sau khi ứng dụng đã warm up:

~~~bash
jcmd <pid> VM.native_memory baseline
~~~

Sau một khoảng thời gian:

~~~bash
jcmd <pid> VM.native_memory summary.diff
jcmd <pid> VM.native_memory detail.diff
~~~

So sánh reserved và committed. Reserved là vùng địa chỉ được dành trước; committed là phần bộ nhớ đã được cấp cho subsystem sử dụng. Committed tăng liên tục có thể là manh mối về tăng native memory, nhưng phải phân tích theo category và tải thực tế.

Nếu NMT không giải thích được RSS, kiểm tra OS memory map, native allocator, JNI library, direct buffer và memory limit của container.

## 11. Lỗi khởi động, classpath và module

Lỗi xảy ra trước khi ứng dụng phục vụ request thường liên quan tới executable Java, version, classpath, module path, manifest, cấu hình hoặc dependency.

### Kiểm tra JAR và manifest

~~~bash
jar --list --file application.jar
~~~

Xem module descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

Kiểm tra bytecode và method:

~~~bash
javap -classpath application.jar -verbose com.acme.Main
javap -classpath application.jar -c -p com.acme.Main
~~~

Kiểm tra dependency/module:

~~~bash
jdeps --recursive --multi-release 17 application.jar
~~~

Với ứng dụng modular, kiểm tra module resolution:

~~~bash
java --show-module-resolution --module-path mods -m com.acme.app/com.acme.Main
~~~

### Một số lỗi thường gặp

| Lỗi | Nguyên nhân thường gặp | Bằng chứng cần kiểm tra |
|---|---|---|
| UnsupportedClassVersionError | Runtime cũ hơn bytecode được biên dịch | javap -verbose, java -version |
| ClassNotFoundException | Class thiếu trên runtime classpath hoặc classloader | command line, dependency tree, class load log |
| NoClassDefFoundError | Class từng được resolve nhưng không còn load được hoặc khởi tạo lỗi | Exception gốc, dependency và classloader |
| NoSuchMethodError | Runtime nạp version class khác với version lúc compile | Dependency tree, JAR thực tế, class origin |
| NoSuchFieldError | API binary không tương thích | Version dependency và bytecode |
| InaccessibleObjectException | Module encapsulation chặn reflection | Module path và opens/exports |
| ServiceConfigurationError | Service provider thiếu hoặc descriptor sai | META-INF/services, module provides/uses |
| UnsatisfiedLinkError | Native library thiếu, sai kiến trúc hoặc không load được | OS, architecture, library path và native dependencies |

Để xem class được nạp từ đâu, bật Unified Logging khi khởi động:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Output có thể rất lớn. Bật trong khoảng thời gian ngắn và lọc theo package/class cần điều tra.

### So sánh build và runtime

Kiểm tra JDK vendor/version lúc compile so với runtime, compiler --release và class file version, dependency version đã resolve, classpath/module path thực tế, manifest Class-Path, module descriptor, multi-release JAR và service provider.

Không chỉ nhìn POM hoặc build.gradle rồi giả định process đang dùng đúng dependency. Hãy kiểm tra file JAR thực tế được deploy và digest của nó.

## 12. Lỗi cấu hình, TLS và I/O

Khi ứng dụng không kết nối được database, API hoặc HTTPS endpoint, hãy xác định lỗi xảy ra ở DNS, TCP, TLS, authentication, protocol hay tầng ứng dụng.

Kiểm tra:

1. Hostname và port có đúng không?
2. DNS resolve ra địa chỉ nào?
3. TCP connection có được thiết lập không?
4. TLS handshake có thành công không?
5. Certificate chain có được tin cậy và còn hạn không?
6. Authentication và authorization có đúng không?
7. Connection pool có cạn hoặc giữ connection quá lâu không?
8. Downstream có latency, timeout hoặc rate limit không?

Dùng keytool để kiểm tra keystore/truststore:

~~~bash
keytool -list -keystore truststore.p12 -storetype PKCS12
~~~

Nếu cần TLS debug, có thể bật trong một lần chạy kiểm soát:

~~~bash
-Djavax.net.debug=ssl:handshake
~~~

TLS debug có thể tạo output rất lớn và chứa thông tin nhạy cảm. Chỉ bật trong thời gian cần thiết, giới hạn quyền truy cập log và tắt sau khi thu thập xong.

JFR SocketRead/SocketWrite và FileRead/FileWrite giúp xác định thời gian chờ I/O. Đối chiếu với network metrics, database logs và server-side traces để xác định đầu nào tạo ra latency.

## 13. Crash và postmortem diagnostics

Khi JVM crash, process biến mất hoặc exit bất thường, giữ lại:

- Fatal error log, thường có tên dạng hs_err_pid*.log.
- Core dump hoặc Windows crash dump nếu được tạo.
- Application stdout/stderr và service manager logs.
- Exit code, signal và thời điểm process kết thúc.
- OS/kernel logs và container termination reason.
- JDK vendor/version, executable path và native library list.
- Artifact digest, command line và environment đã che secret.

Fatal error log thường là tài liệu đầu tiên cần đọc sau một lỗi VM nghiêm trọng. Nó có thể chứa signal, problematic frame, thread, native stack, JVM flags và thông tin hệ thống.

Có thể cấu hình vị trí log:

~~~bash
-XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log
~~~

Với core dump, công cụ Serviceability Agent như jhsdb có thể đọc thông tin từ core file. Binary JDK dùng để phân tích phải tương thích với binary đã tạo core. Phân tích native crash có thể cần debugger của hệ điều hành như gdb hoặc WinDbg.

Phân biệt Java exception, Java OutOfMemoryError, fatal JVM error và OS kill. Chúng có cơ chế tạo log/dump khác nhau. Process bị SIGKILL hoặc container OOM kill thường không thể tự ghi fatal error log.

## 14. Container và hệ điều hành

JVM chạy trong container có thể nhìn thấy CPU/memory giới hạn khác với host. Hãy thu thập cả giới hạn container và số liệu process.

Linux/container:

~~~bash
cat /proc/<pid>/status
cat /proc/meminfo
ps -o pid,ppid,%cpu,%mem,rss,vsz,stat,etime,cmd -p <pid>
top -H -p <pid>
~~~

Nếu chạy Docker, kiểm tra container inspect, memory limit, CPU quota, restart count và OOMKilled state. Trong Kubernetes, đối chiếu pod events, requests/limits, restart reason, node pressure và container logs.

Windows có thể dùng Get-Process, Get-CimInstance Win32_Process, Performance Monitor và Event Viewer. macOS có Activity Monitor, vm_stat và các công cụ hệ thống phù hợp.

Không chỉ nhìn phần trăm heap. RSS bao gồm native memory và có thể chịu ảnh hưởng page cache, mapped file và shared library. So sánh heap, NMT, RSS, container limit và OS metrics trong cùng một khoảng thời gian.

## 15. Reproduce và xác nhận nguyên nhân

Khi đã có giả thuyết:

1. Tạo kịch bản tái hiện nhỏ nhất có thể.
2. Giữ nguyên JDK, flags, dependency và input liên quan.
3. Ghi lại baseline trước khi thay đổi.
4. Thay một yếu tố duy nhất.
5. Chạy cùng tải và cùng thời lượng.
6. So sánh log, latency, CPU, memory và recording.
7. Lặp lại để loại trừ biến động ngẫu nhiên.
8. Thử một kịch bản regression cho lỗi đã sửa.

Nếu lỗi chỉ xuất hiện production, tạo môi trường gần production về JDK, container limit, traffic, dependency và cấu hình. Không sao chép dữ liệu production nhạy cảm vào máy cá nhân; dùng dữ liệu đã ẩn danh hoặc bộ dữ liệu mô phỏng phù hợp.

Một nguyên nhân chỉ được xem là đã xác nhận khi có bằng chứng giải thích được triệu chứng và một thay đổi kiểm soát làm thay đổi kết quả theo dự đoán.

## 16. Ví dụ Java 17+: kiểm tra các MXBean chẩn đoán cơ bản

JDK cung cấp Java Management API để ứng dụng đọc thông tin runtime. Ví dụ dưới đây kiểm tra các MXBean chính có thể truy cập được. Nó minh họa cách một chương trình Java tự kiểm tra khả năng đọc runtime metrics; kết quả PASS chỉ xác nhận các API này hoạt động, không chứng minh toàn bộ ứng dụng khỏe mạnh.

Cấu trúc:

~~~text
diagnostic-probe/
  src/
    DiagnosticProbe.java
  out/
~~~

Tệp src/DiagnosticProbe.java:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.lang.management.RuntimeMXBean;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadMXBean;

public final class DiagnosticProbe {

    private DiagnosticProbe() {
    }

    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();

        if (runtime.getUptime() < 0
                || heap.getUsed() < 0
                || threads.getThreadCount() < 1) {
            throw new IllegalStateException("JVM diagnostic probe failed");
        }

        System.out.println("runtimeMXBean=OK");
        System.out.println("heapMXBean=OK");
        System.out.println("threadMXBean=OK");
        System.out.println("DIAGNOSTIC_RESULT=PASS");
    }
}
~~~

Biên dịch từ thư mục project:

~~~bash
javac -d out src/DiagnosticProbe.java
~~~

Chạy:

~~~bash
java -cp out DiagnosticProbe
~~~

Stdout chính xác:

~~~text
runtimeMXBean=OK
heapMXBean=OK
threadMXBean=OK
DIAGNOSTIC_RESULT=PASS
~~~

Có thể mở rộng probe để in runtime uptime, heap used/max, thread count, loaded class count và JVM input arguments. Khi ghi các giá trị này vào log, hãy dùng tên metric và đơn vị rõ ràng; tránh in system properties hoặc environment variables có chứa secret.

Trong hệ thống thực tế, MXBean phù hợp cho metrics và health diagnostics có kiểm soát. Khi cần stack trace, event timeline, allocation hoặc lock profiling, dùng jcmd/JFR theo tình huống.

## 17. Những lỗi thường gặp khi chẩn đoán

| Cách làm sai | Hệ quả | Cách làm phù hợp |
|---|---|---|
| Chạy mọi công cụ cùng lúc | Tạo nhiều dữ liệu nhiễu và overhead | Chọn công cụ theo giả thuyết |
| Chỉ lấy một thread dump | Không biết trạng thái có kéo dài hay không | So sánh nhiều snapshot |
| Nhầm heap với RSS | Bỏ sót native memory hoặc container limit | Đối chiếu heap, NMT, RSS và OS |
| Kết luận GC là nguyên nhân từ một pause | Tuning sai và che mất bottleneck | Ghép GC log với latency/JFR |
| Tạo heap dump không kiểm tra dung lượng | Hết disk hoặc tăng pause | Kiểm tra dung lượng và tác động trước |
| Dùng jcmd bằng user khác | Attach thất bại | Dùng đúng effective user/group |
| So sánh log lệch timezone | Timeline sai | Chuẩn hóa timestamp và timezone |
| Chỉ xem source build config | Bỏ qua binary/runtime thực tế | Kiểm tra command line, JAR và digest đã deploy |
| Tăng heap ngay khi thấy OOM | Có thể làm container bị kill sớm hơn | Phân biệt heap OOM và native/container OOM |
| Gửi dump không kiểm soát | Lộ dữ liệu trong bộ nhớ | Giới hạn quyền, mã hóa và che dữ liệu |

Không sửa nhiều flags JVM cùng lúc trong lúc sự cố đang diễn ra. Mỗi thay đổi phải có lý do, giả thuyết và phép đo xác nhận.

## 18. Mẫu báo cáo chẩn đoán

| Trường | Nội dung cần ghi |
|---|---|
| Incident ID | Mã sự cố hoặc ticket |
| Symptom | Triệu chứng và thông báo lỗi nguyên văn |
| Timeline | Timestamp, timezone và các mốc liên quan |
| Impact | Người dùng/service/endpoint bị ảnh hưởng |
| Environment | JDK vendor/version, OS, container, CPU/RAM limit |
| Application | Version, commit SHA và artifact digest |
| JVM config | Command line, flags, heap, collector, system properties đã che secret |
| Evidence | Log, thread dump, JFR, GC log, heap/native dump nếu có |
| Hypothesis | Nguyên nhân dự kiến và bằng chứng |
| Experiment | Thay đổi đã thử, input và điều kiện chạy |
| Result | Số liệu trước/sau và kết quả tái hiện |
| Root cause | Nguyên nhân được bằng chứng xác nhận |
| Fix | Thay đổi đã triển khai |
| Regression | Test và metric theo dõi sau sửa |
| Follow-up | Việc cần làm và người phụ trách |

Không đưa mật khẩu, token, private key, dữ liệu cá nhân hoặc heap dump nguyên bản vào ticket công khai.

## 19. Checklist chẩn đoán trước khi kết luận

- [ ] Đã mô tả triệu chứng bằng thời điểm, phạm vi và tác động.
- [ ] Đã xác định đúng PID và executable Java của process.
- [ ] Đã ghi JDK vendor/version, OS, architecture và container limits.
- [ ] Đã lưu command line và JVM flags, đồng thời che secret.
- [ ] Đã lưu log và timestamp theo cùng timezone.
- [ ] Đã chọn công cụ phù hợp với loại sự cố.
- [ ] Đã đánh giá impact và dung lượng trước khi tạo dump.
- [ ] Đã so sánh nhiều snapshot hoặc recording nếu cần.
- [ ] Đã phân biệt heap, native memory và OS/container memory.
- [ ] Đã kiểm tra dependency, classpath/module path nếu lỗi khởi động.
- [ ] Đã kiểm tra artifact digest và binary thực sự được deploy.
- [ ] Đã tái hiện hoặc xác nhận giả thuyết bằng phép đo.
- [ ] Đã kiểm tra regression và theo dõi sau thay đổi.
- [ ] Đã lưu bằng chứng với quyền truy cập và retention phù hợp.

## 20. Ghi nhớ

- Chẩn đoán bắt đầu bằng triệu chứng có thể kiểm chứng và baseline của đúng process.
- Xác định đúng JDK, PID, command line, flags, OS và giới hạn container.
- jcmd là công cụ chính để truy vấn JVM đang chạy; kiểm tra lệnh hỗ trợ bằng help.
- Thread dump cần được so sánh theo thời gian để phát hiện lock, deadlock và thread bị kẹt.
- JFR/JMC giúp tìm bottleneck CPU, synchronization, GC và I/O theo timeline.
- Histogram và heap dump giúp tìm object retention; chúng có thể gây pause và cần dung lượng lớn.
- GC log và jstat giúp kiểm tra allocation, heap usage và pause time.
- NMT phải bật lúc khởi động và chỉ theo dõi memory nội bộ HotSpot.
- Heap, RSS và container memory là các số đo khác nhau.
- jar, jdeps và javap giúp kiểm tra archive, module và bytecode.
- Fatal error log, core dump và OS logs là bằng chứng quan trọng khi JVM crash.
- Thay một yếu tố mỗi lần và dùng cùng phép đo để xác nhận kết quả.
- Bảo vệ dump và log vì chúng có thể chứa dữ liệu nhạy cảm.

## Tài liệu tham khảo chính thức

- [Oracle JDK 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 26 — jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Oracle JDK 26 — jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [Oracle JDK 26 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [Java Management Extensions (JMX) Technology](https://docs.oracle.com/en/java/javase/26/management/monitoring-and-management-using-jmx-technology.html)
- [The jstat Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jstat.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jar Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The javap Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)