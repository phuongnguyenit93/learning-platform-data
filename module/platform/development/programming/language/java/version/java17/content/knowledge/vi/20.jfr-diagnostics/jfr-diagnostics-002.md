# jcmd để tra tiến trình và khả năng chẩn đoán trong Java 17

Khi một ứng dụng Java chạy chậm, dùng CPU cao, tiêu thụ nhiều bộ nhớ hoặc có thread bị kẹt, bước đầu tiên là xác định **JVM nào đang chạy** và thu thập dữ liệu từ đúng tiến trình đó. Java 17 cung cấp công cụ dòng lệnh `jcmd` để liệt kê JVM, xem thông tin runtime, lấy thread dump, quan sát heap, kiểm tra cờ JVM và điều khiển Java Flight Recorder (JFR).

`jcmd` là công cụ chẩn đoán cục bộ của JDK. Nó gửi diagnostic command tới một JVM đang chạy thông qua cơ chế attach. Mỗi lệnh có phạm vi và mức ảnh hưởng khác nhau: một số chỉ đọc metadata, một số có thể duyệt heap, kích hoạt garbage collection hoặc tạo file dump rất lớn.

Bài này trình bày cách tìm đúng tiến trình, khám phá lệnh mà JVM hỗ trợ, chọn lệnh chẩn đoán phù hợp và thu thập dữ liệu có kiểm soát trong môi trường Java 17.

## 1. jcmd là gì?

`jcmd` là tiện ích trong bộ JDK, nằm trong thư mục `bin`, dùng để gửi diagnostic command tới các tiến trình Java. Công cụ có thể:

- Liệt kê JVM đang chạy mà cơ chế attach có thể nhìn thấy.
- Hiển thị danh sách lệnh được JVM đích hỗ trợ.
- In command line, system properties, JVM flags, version và uptime.
- Lấy thread dump và thông tin class loader.
- Xem heap summary, class histogram và tạo heap dump.
- Kiểm tra Native Memory Tracking nếu JVM đã bật tính năng này.
- Khởi chạy, kiểm tra, dump và dừng bản ghi Java Flight Recorder.

Ví dụ đường dẫn:

~~~text
JDK_HOME/
  bin/
    java
    javac
    jcmd
~~~

Nên dùng `jcmd` thuộc JDK phù hợp với phiên bản JVM đích. Trong production, hãy xác định đúng JDK và đúng máy/container đang chạy ứng dụng trước khi gửi lệnh.

### 1.1. Cú pháp tổng quát

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Các thành phần:

- `pid`: process ID của JVM cần chẩn đoán.
- `main-class`: tên lớp main để chọn JVM trong trường hợp phù hợp; PID thường rõ ràng và ít mơ hồ hơn.
- `command`: diagnostic command gửi tới JVM.
- `arguments`: tham số riêng của command.

Các dạng gọi phổ biến:

~~~bash
jcmd -l
jcmd -h
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> VM.version
~~~

`jcmd -h` hiển thị hướng dẫn cú pháp của công cụ trên máy hiện tại. `jcmd <pid> help` yêu cầu chính JVM đích liệt kê lệnh nó hỗ trợ.

## 2. Liệt kê tiến trình Java với jcmd -l

Lệnh bắt đầu thường dùng:

~~~bash
jcmd -l
~~~

Kết quả thường có PID và thông tin main class hoặc command line của tiến trình:

~~~text
24680 com.example.orders.OrderApplication
25104 org.gradle.launcher.daemon.bootstrap.GradleDaemon
~~~

Trong ví dụ, `24680` và `25104` là PID. Chọn PID của ứng dụng cần điều tra, không nhầm với Gradle daemon, công cụ build hoặc một JVM khác.

### 2.1. Đối chiếu với hệ điều hành

Nếu không chắc PID thuộc ứng dụng nào, đối chiếu bằng công cụ hệ điều hành.

Linux:

~~~bash
ps -eo pid,ppid,user,etime,args | grep '[j]ava'
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe' OR Name = 'javaw.exe'" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
~~~

Không chỉ dựa vào tên main class. Một máy có thể chạy nhiều instance cùng một ứng dụng, nhiều service Java hoặc các JVM phụ trợ. Hãy kiểm tra PID, user, thời gian chạy, command line và thư mục làm việc nếu cần.

### 2.2. Giới hạn của danh sách jcmd -l

`jcmd -l` liệt kê các JVM mà công cụ nhìn thấy qua cơ chế attach trong phạm vi môi trường hiện tại. Nó không phải trình quản lý process tổng quát và không bảo đảm nhìn thấy mọi JVM trên máy.

Một số nguyên nhân khiến tiến trình không xuất hiện:

- Tiến trình chạy dưới user khác hoặc quyền truy cập hiện tại không đủ.
- JVM đã tắt, đang khởi động hoặc attach listener chưa sẵn sàng.
- JVM được khởi chạy với `-XX:+DisableAttachMechanism`.
- Công cụ và target nằm trong container hoặc PID namespace khác nhau.
- Môi trường tạm dùng cho attach không được chia sẻ hoặc có quyền truy cập không phù hợp.
- Tiến trình không phải HotSpot/OpenJDK JVM tương thích với cơ chế attach đang dùng.

Nếu không tìm thấy PID bằng `jcmd -l`, hãy xác minh bằng process list của hệ điều hành và môi trường chạy trước khi kết luận JVM không tồn tại.

## 3. Điều kiện để attach vào JVM đích

`jcmd` không phải công cụ gửi lệnh từ xa qua mạng. Công cụ thường phải chạy trên cùng máy với JVM đích và dưới cùng effective user/group theo yêu cầu của cơ chế attach.

Các điều kiện thực tế cần kiểm tra:

1. Có JDK với `jcmd` trong môi trường thực thi.
2. Đang chạy lệnh trên đúng host hoặc đúng container/PID namespace.
3. User chạy `jcmd` có quyền attach vào target process.
4. JVM đích không tắt attach mechanism.
5. Target JVM còn sống và có thể xử lý diagnostic request.

JVM có thể được khởi chạy với:

~~~bash
java -XX:+DisableAttachMechanism -jar application.jar
~~~

Khi tùy chọn này được bật, các công cụ dựa trên attach như `jcmd` không thể attach theo cách thông thường. Đây là một quyết định vận hành/bảo mật cần được cân nhắc từ lúc khởi chạy; không có lệnh `jcmd` thông thường nào tự bật lại attach cho JVM đang chạy.

### 3.1. Container và PID namespace

Trong môi trường container, PID nhìn từ host có thể khác PID nhìn từ bên trong container. Công cụ `jcmd -l` chạy ở host có thể không nhìn thấy JVM ở namespace riêng; ngược lại, PID trong container không nhất thiết là PID trên host.

Quy trình phù hợp thường là:

- Xác định container hoặc pod đang chạy ứng dụng.
- Chạy công cụ trong cùng container hoặc môi trường có thể truy cập đúng PID namespace và attach endpoint.
- Dùng JDK tools có phiên bản phù hợp với JVM target.
- Kiểm tra user và quyền truy cập vào thư mục tạm được attach sử dụng.

Không đoán PID giữa host và container. Hãy xác minh lại PID ngay trong môi trường mà `jcmd` được chạy.

### 3.2. Attach có tác động gì?

`jcmd` gửi yêu cầu vào JVM đích. Tùy command, JVM có thể cần thực hiện thao tác đồng bộ, duyệt metadata hoặc dừng một số thread trong một khoảng thời gian. Vì vậy:

- Command đọc metadata thường ít ảnh hưởng hơn heap dump hoặc class histogram.
- Thread dump có thể tạo một lượng dữ liệu đáng kể nếu ứng dụng có rất nhiều thread.
- Heap histogram và heap dump có thể ảnh hưởng latency và CPU.
- JFR có overhead, phụ thuộc loại event, cấu hình và thời gian ghi.

Hãy đọc phần mô tả/impact trong `help` của chính JVM đích trước khi chạy command có ảnh hưởng cao.

## 4. Khám phá command được hỗ trợ

Danh sách diagnostic command phụ thuộc JVM, phiên bản, build và cấu hình. Vì vậy, sau khi xác định PID, hãy hỏi chính tiến trình:

~~~bash
jcmd 24680 help
~~~

Để xem chi tiết một command:

~~~bash
jcmd 24680 help Thread.print
jcmd 24680 help GC.heap_dump
jcmd 24680 help JFR.start
~~~

Đây là bước quan trọng trước khi dùng command có tham số. Cú pháp, tùy chọn và mức ảnh hưởng được JVM đích công bố có giá trị hơn việc suy đoán từ một máy khác.

### 4.1. Chạy một command

~~~bash
jcmd 24680 VM.version
~~~

Kết quả được in trực tiếp ra terminal. Có thể lưu output vào file để so sánh giữa các lần thu thập:

Linux:

~~~bash
jcmd 24680 VM.flags -all > vm-flags.txt
~~~

Windows PowerShell:

~~~powershell
jcmd 24680 VM.flags -all | Out-File -Encoding utf8 vm-flags.txt
~~~

Nếu dùng shell khác, cú pháp redirect và encoding của file output có thể khác. Đảm bảo thư mục đích có quyền ghi và không ghi đè bằng chứng chẩn đoán cần giữ.

### 4.2. Chạy command từ file

`jcmd` có tùy chọn `-f <filename>` để đọc các lệnh từ file:

~~~bash
jcmd -f diagnostics.txt 24680
~~~

File chứa các command theo định dạng được công cụ hỗ trợ. Trước khi chạy hàng loạt, hãy đọc lại nội dung file và đánh giá impact của từng command. Không đưa lệnh thay đổi trạng thái JVM vào batch chỉ vì muốn thu thập nhiều thông tin cùng lúc.

## 5. Tra cứu thông tin runtime cơ bản

Một số command hữu ích, thường ít tác động hơn các thao tác duyệt heap:

| Command | Thông tin |
| --- | --- |
| `VM.version` | Phiên bản JVM |
| `VM.uptime` | Thời gian JVM đã chạy |
| `VM.command_line` | Tham số khởi chạy JVM |
| `VM.flags` | Các cờ JVM hiện tại |
| `VM.system_properties` | System properties |
| `VM.info` | Thông tin runtime và môi trường JVM |
| `VM.dynlibs` | Thư viện native đang được nạp |
| `VM.classloader_stats` | Thống kê class loader |

Ví dụ:

~~~bash
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags
jcmd 24680 VM.system_properties
~~~

### 5.1. VM.command_line

~~~bash
jcmd 24680 VM.command_line
~~~

Giúp xem main class hoặc JAR và tham số đã truyền khi khởi chạy. Thông tin này có thể giúp phát hiện:

- JVM đang dùng profile cấu hình nào.
- Có bật heap size, GC hoặc diagnostic option không.
- Có truyền system property liên quan tới môi trường không.
- Tiến trình đang chạy đúng artifact và tham số dự kiến không.

Command line có thể chứa token, password hoặc thông tin nhạy cảm nếu ứng dụng cấu hình sai. Hạn chế quyền truy cập file output và không đưa nguyên output vào ticket/log công khai.

### 5.2. VM.flags

~~~bash
jcmd 24680 VM.flags
jcmd 24680 VM.flags -all
~~~

`VM.flags` hiển thị các cờ JVM. Tùy chọn `-all` yêu cầu hiển thị rộng hơn, gồm giá trị và metadata của các flag theo implementation.

Thông tin hữu ích khi điều tra:

- Heap sizing như `InitialHeapSize`, `MaxHeapSize`.
- GC được chọn.
- Tùy chọn liên quan đến compiler/JIT.
- Diagnostic hoặc experimental flag.
- Native Memory Tracking có được bật lúc khởi động không.

Không thay đổi flag chỉ vì thấy một giá trị khác máy khác. Một số flag chỉ có thể đặt lúc JVM khởi động; command `VM.set_flag` chỉ hỗ trợ một số flag có thể thay đổi khi chạy và còn chịu ràng buộc của JVM.

### 5.3. VM.system_properties

~~~bash
jcmd 24680 VM.system_properties
~~~

Command này liệt kê system properties của JVM. Chúng có thể giúp xác định:

- `java.version`, `java.vendor`, `java.home`.
- `user.dir`, `user.timezone`, `file.encoding`.
- Profile hoặc endpoint cấu hình qua property.
- Đường dẫn tạm và thư mục ứng dụng.

System properties có thể chứa bí mật nếu ứng dụng hoặc script khởi chạy đặt thông tin xác thực trong property. Hãy lọc/redact trước khi chia sẻ output.

## 6. Chẩn đoán thread với Thread.print

Thread dump là ảnh chụp trạng thái thread tại một thời điểm. Nó giúp tìm:

- Thread đang chạy CPU hoặc chờ I/O.
- Deadlock.
- Lock contention.
- Thread pool cạn worker.
- Thread chờ monitor hoặc condition.
- Nhiều thread cùng chờ một dependency.

Lệnh:

~~~bash
jcmd 24680 Thread.print
~~~

Tùy chọn:

~~~bash
jcmd 24680 Thread.print -l
jcmd 24680 Thread.print -e
~~~

- `-l`: in thêm thông tin về các lock thuộc `java.util.concurrent`.
- `-e`: yêu cầu thông tin mở rộng về thread theo command help của JVM đích.

### 6.1. Đọc một thread dump

Một đoạn output minh họa:

~~~text
"http-worker-12" #84 daemon prio=5 os_prio=0
   java.lang.Thread.State: BLOCKED
        at com.example.store.Cache.refresh(Cache.java:84)
        - waiting to lock <0x0000000712345678>
        at com.example.api.OrderHandler.handle(OrderHandler.java:51)
~~~

Các thành phần:

- Tên thread giúp nhận diện nhóm công việc.
- `Thread.State` cho biết trạng thái JVM như `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`.
- Stack trace cho thấy đường gọi tại thời điểm chụp.
- Monitor/lock ID giúp liên kết thread đang chờ với thread đang giữ lock khi output có thông tin tương ứng.

`RUNNABLE` không luôn có nghĩa thread đang sử dụng CPU liên tục; nó cũng có thể đang ở trạng thái runnable theo góc nhìn JVM trong khi chờ hoạt động native hoặc I/O.

### 6.2. Deadlock

Nếu thread dump báo phần deadlock, tìm các thread chờ lock theo vòng tròn. Ví dụ:

~~~text
Thread A holds Lock-1 and waits for Lock-2
Thread B holds Lock-2 and waits for Lock-1
~~~

Một dump đơn lẻ có thể cho thấy trạng thái deadlock tại thời điểm chụp. Nếu nghi ngờ nghẽn tạm thời, thu thập nhiều dump cách nhau vài giây để so sánh stack và trạng thái. Không kết luận deadlock chỉ từ một thread ở trạng thái `BLOCKED`.

### 6.3. Thu thập nhiều thread dump

Linux:

~~~bash
for i in 1 2 3; do
  jcmd 24680 Thread.print -l > "threads-$i.txt"
  sleep 5
done
~~~

PowerShell:

~~~powershell
1..3 | ForEach-Object {
    jcmd 24680 Thread.print -l |
        Out-File -Encoding utf8 "threads-$_.txt"
    Start-Sleep -Seconds 5
}
~~~

Ba snapshot cách nhau vài giây có thể giúp phân biệt một thread chờ bình thường với một thread bị kẹt lâu. Khoảng cách và số lượng snapshot nên phù hợp với tốc độ tái hiện sự cố, tránh tạo quá nhiều output không cần thiết.

## 7. Quan sát heap và class histogram

### 7.1. GC.heap_info

~~~bash
jcmd 24680 GC.heap_info
~~~

Command hiển thị thông tin tổng quan về heap theo GC đang dùng, chẳng hạn các vùng heap và dung lượng đã cấp phát/đang sử dụng. Định dạng output thay đổi theo garbage collector và phiên bản JVM.

Thông tin này hữu ích để xem nhanh heap có đang gần giới hạn hay không. Nó không thay thế phân tích heap dump và không giải thích trực tiếp object nào giữ bộ nhớ.

### 7.2. GC.class_histogram

~~~bash
jcmd 24680 GC.class_histogram
~~~

Class histogram tổng hợp số instance và tổng byte theo class. Có thể dùng để nhận diện:

- Một class có số instance tăng bất thường.
- Mảng byte hoặc char chiếm nhiều bộ nhớ.
- Cache/collection có số phần tử lớn.
- Các kiểu object có footprint đáng chú ý.

Tùy chọn `-all` yêu cầu tính cả object không còn reachable theo cách mặc định chỉ xét object sống:

~~~bash
jcmd 24680 GC.class_histogram -all
~~~

Histogram cần duyệt thông tin heap và có thể gây pause/ảnh hưởng đáng kể. Hãy kiểm tra `help GC.class_histogram` trên JVM đích trước khi chạy, nhất là khi service đang có latency cao.

Histogram là ảnh chụp tổng hợp; nó không cho biết đầy đủ đường tham chiếu khiến object được giữ lại. Nếu cần tìm GC root hoặc đường giữ object, có thể cần heap dump và phân tích bằng công cụ phù hợp.

### 7.3. GC.heap_dump

Heap dump lưu đồ thị object của JVM ra file để phân tích sâu:

~~~bash
jcmd 24680 GC.heap_dump /var/tmp/orders-heap.hprof
~~~

Tùy chọn của command có thể gồm:

- `-all`: đưa cả object không reachable vào dump.
- `-gz=<level>`: nén output theo mức hỗ trợ.
- `-overwrite`: cho phép ghi đè file đích nếu command hỗ trợ.

Hãy xem `jcmd 24680 help GC.heap_dump` để biết cú pháp chính xác của JDK đích. Mặc định, heap dump có thể yêu cầu full GC trước khi ghi; thao tác có impact cao và có thể làm ứng dụng pause đáng kể.

Trước khi tạo dump:

1. Xác định thư mục đích và dung lượng đĩa còn trống.
2. Kiểm tra heap tối đa và ước lượng kích thước dump.
3. Đảm bảo có quyền ghi file.
4. Chọn thời điểm phù hợp với mức độ ảnh hưởng cho phép.
5. Hạn chế quyền đọc file dump và xóa an toàn sau khi hoàn tất điều tra.

Heap dump có thể chứa password, token, session, dữ liệu người dùng và nội dung request/response đang ở trong bộ nhớ. Xem nó như dữ liệu nhạy cảm.

## 8. Native Memory Tracking

Heap không phải toàn bộ bộ nhớ mà tiến trình Java sử dụng. JVM còn có native memory cho thread stack, metaspace, code cache, GC, compiler, direct buffer và các thành phần native khác.

Native Memory Tracking (NMT) cho phép JVM ghi nhận phân bổ native memory để hỗ trợ chẩn đoán. Trong Java 17, NMT phải được bật khi JVM khởi chạy:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Hoặc dùng mức chi tiết:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Không thể bật NMT đầy đủ cho một JVM đã chạy từ trước chỉ bằng cách gọi `jcmd`. Nếu target không bật NMT, `VM.native_memory` sẽ thông báo tính năng chưa được kích hoạt.

### 8.1. Xem native memory summary

~~~bash
jcmd 24680 VM.native_memory summary
~~~

NMT summary phân nhóm native memory theo các khu vực do JVM theo dõi, giúp tìm phần tiêu thụ tăng bất thường ngoài Java heap.

### 8.2. Tạo baseline và so sánh

~~~bash
jcmd 24680 VM.native_memory baseline
~~~

Sau một khoảng thời gian hoặc sau khi tái hiện tải:

~~~bash
jcmd 24680 VM.native_memory summary.diff
~~~

So sánh với baseline giúp quan sát mức tăng/giảm giữa hai thời điểm. Nếu NMT được bật ở mức `detail`, có thể dùng các chế độ detail/diff tương ứng theo `help VM.native_memory`.

NMT có overhead về bộ nhớ và CPU. Mức `detail` thường tốn chi phí hơn `summary`; chỉ bật mức cần thiết cho điều tra. NMT không theo dõi mọi allocation native do mọi thư viện bên ngoài thực hiện, vì vậy không phải phép đo toàn diện mọi byte của process.

## 9. Chẩn đoán class loader và code cache

Khi ứng dụng nạp nhiều plugin, tạo class động hoặc có dấu hiệu metaspace tăng, các command class loader có thể hữu ích:

~~~bash
jcmd 24680 VM.classloader_stats
jcmd 24680 VM.classloaders
jcmd 24680 VM.class_hierarchy
~~~

Các command có sẵn và tham số cụ thể phụ thuộc JVM đích. Hãy gọi `help` cho từng command.

`VM.classloader_stats` cung cấp thống kê về class loader và số class được nạp theo loader. `VM.classloaders` có thể hiển thị cấu trúc class loader. `VM.class_hierarchy` hỗ trợ quan sát quan hệ kế thừa theo các tùy chọn được JVM hỗ trợ.

Nếu class loader không được giải phóng, ứng dụng có thể giữ class và metadata lâu hơn dự kiến. Cần phân tích tham chiếu và vòng đời loader trước khi kết luận có class loader leak; số lượng class tăng đơn thuần chưa đủ chứng minh rò rỉ.

### 9.1. Compiler và code cache

Một số command liên quan compiler:

~~~bash
jcmd 24680 Compiler.codecache
jcmd 24680 Compiler.queue
jcmd 24680 Compiler.codelist
~~~

Chúng giúp quan sát code cache, hàng đợi biên dịch hoặc danh sách code đã biên dịch nếu JVM đích hỗ trợ. Hữu ích khi điều tra JIT, code cache pressure hoặc hoạt động compiler bất thường.

## 10. Điều khiển và kiểm tra Java Flight Recorder bằng jcmd

Java Flight Recorder (JFR) là cơ chế ghi sự kiện runtime của JVM. Nó có thể thu thập thông tin về CPU sampling, allocation, GC, thread, lock contention, class loading và các sự kiện khác.

JFR có sẵn trong OpenJDK/Oracle JDK hiện đại, bao gồm Java 17; không cần bật commercial unlock flag kiểu cũ.

Các command chính:

| Command | Mục đích |
| --- | --- |
| `JFR.check` | Liệt kê recording và trạng thái |
| `JFR.start` | Bắt đầu recording |
| `JFR.dump` | Xuất dữ liệu recording hiện có ra file |
| `JFR.stop` | Dừng recording |
| `JFR.configure` | Xem hoặc cấu hình một số thiết lập JFR |

### 10.1. Kiểm tra recording

~~~bash
jcmd 24680 JFR.check
~~~

Nếu đã có recording, output cho biết tên, trạng thái và thông tin liên quan. Kiểm tra trước khi bắt đầu recording mới để tránh chạy trùng nhiều phiên không cần thiết.

### 10.2. Bắt đầu recording có thời hạn

~~~bash
jcmd 24680 JFR.start name=triage settings=profile duration=5m filename=/var/tmp/triage.jfr
~~~

Giải thích:

- `name=triage`: đặt tên recording để tham chiếu về sau.
- `settings=profile`: dùng cấu hình profile có nhiều sự kiện hơn cấu hình mặc định, phù hợp điều tra ngắn hạn.
- `duration=5m`: giới hạn thời gian ghi.
- `filename=...`: chỉ định nơi lưu recording khi hoàn tất theo hành vi command.

Đường dẫn file phải tồn tại hoặc có thể được tạo theo yêu cầu của command, và JVM cần quyền ghi. Xem `help JFR.start` trên target để kiểm tra tùy chọn hỗ trợ.

### 10.3. Dump recording đang chạy

~~~bash
jcmd 24680 JFR.dump name=triage filename=/var/tmp/triage-snapshot.jfr
~~~

`JFR.dump` ghi snapshot của recording ra file mà không nhất thiết phải dừng recording. Điều này hữu ích khi muốn lấy dữ liệu tại thời điểm phát hiện vấn đề nhưng vẫn tiếp tục theo dõi.

### 10.4. Dừng recording

~~~bash
jcmd 24680 JFR.stop name=triage
~~~

Nếu recording đã cấu hình `filename` hoặc có chỉ định output phù hợp, dữ liệu sẽ được lưu theo cấu hình. Hãy kiểm tra file đã được tạo và có thể mở bằng JDK Mission Control (JMC) hoặc công cụ phân tích JFR.

### 10.5. Chọn default hay profile?

- `default`: thường ít sự kiện hơn, phù hợp quan sát tổng quát dài hơn.
- `profile`: thu thập nhiều chi tiết hơn, hữu ích khi điều tra ngắn hạn; overhead có thể cao hơn.

Không có một cấu hình tối ưu cho mọi workload. Hãy bắt đầu với thời gian ghi ngắn và cấu hình phù hợp, sau đó tăng chi tiết khi dữ liệu chưa đủ để giải thích sự cố.

JFR recording có thể chứa thông tin về class, method, thread, đường dẫn file và dữ liệu runtime. Bảo vệ file `.jfr` theo chính sách dữ liệu của tổ chức.

## 11. Một số command khác hữu ích khi điều tra

| Command | Tình huống |
| --- | --- |
| `VM.info` | Cần thông tin tổng quan JVM, OS, runtime |
| `VM.dynlibs` | Điều tra thư viện native được nạp |
| `VM.classloader_stats` | Điều tra class loading/metaspace |
| `Compiler.codecache` | Kiểm tra code cache |
| `GC.heap_info` | Xem tổng quan heap |
| `GC.class_histogram` | Tìm class có số instance hoặc dung lượng cao |
| `VM.native_memory` | Điều tra native memory khi NMT đã bật |
| `JFR.*` | Thu thập sự kiện runtime trong một khoảng thời gian |

Đây là các nhóm lệnh thường gặp trên HotSpot JDK 17. Không phải mọi JVM vendor/build đều có cùng danh sách hoặc cùng tùy chọn. Dùng `help` từ JVM đích làm nguồn cú pháp cuối cùng.

## 12. Quy trình chẩn đoán theo triệu chứng

### 12.1. Ứng dụng phản hồi chậm hoặc request bị treo

1. Dùng `jcmd -l` và process list để xác định đúng PID.
2. Gọi `VM.uptime`, `VM.command_line` và `VM.flags` để hiểu môi trường.
3. Thu thập 2–3 thread dump bằng `Thread.print -l`, cách nhau vài giây.
4. So sánh stack của các thread liên quan; tìm lock, wait, socket read hoặc stack không tiến triển.
5. Nếu chưa đủ dữ liệu, chạy JFR recording ngắn để quan sát CPU, lock, GC và allocation.

### 12.2. Heap tăng nhanh hoặc gần OOM

1. Xem `GC.heap_info` để có bức tranh tổng quan.
2. Dùng `GC.class_histogram` nếu impact cho phép để tìm class/mảng chiếm nhiều bộ nhớ.
3. Nếu cần phân tích đường tham chiếu, lên kế hoạch heap dump với dung lượng đĩa và bảo vệ dữ liệu phù hợp.
4. So sánh nhiều snapshot hoặc recording để phân biệt tăng tải bình thường với object giữ lại lâu bất thường.

### 12.3. Process dùng RAM cao nhưng heap không lớn

1. So sánh RSS của process với heap đã cấp phát.
2. Kiểm tra `VM.flags` để biết NMT có bật không.
3. Nếu NMT hoạt động, lấy `VM.native_memory summary`.
4. Nếu có baseline, dùng `summary.diff` để xem nhóm native memory tăng.
5. Kiểm tra thread count, direct buffer, native library và cấu hình GC/compiler.

NMT chỉ là một góc nhìn; đối chiếu với số liệu hệ điều hành và thư viện native của ứng dụng.

### 12.4. CPU cao

1. Lấy nhiều thread dump để xem thread nào thường xuyên xuất hiện ở stack liên quan.
2. Dùng JFR `profile` trong khoảng ngắn để xem CPU samples và hot methods.
3. Kiểm tra GC activity, compiler và code cache nếu dữ liệu gợi ý.
4. Đối chiếu với metrics của ứng dụng để xác định endpoint hoặc workload tạo tải.

Thread dump không phải profiler CPU. JFR hoặc profiler phù hợp sẽ giúp định lượng tốt hơn.

## 13. Bảo toàn bằng chứng và giới hạn tác động

Chẩn đoán production cần cân bằng giữa lượng thông tin và ảnh hưởng tới dịch vụ.

Trước khi chạy lệnh:

- Xác nhận đúng PID, host, container và user.
- Xem `help <command>` để biết cú pháp và impact.
- Chọn command ít tác động trước; chỉ dùng heap dump hoặc thao tác nặng khi có lý do.
- Kiểm tra dung lượng đĩa và quyền ghi.
- Đặt tên file có PID, thời điểm và loại dữ liệu.
- Ghi lại thời gian, command, phiên bản JDK và triệu chứng đang quan sát.

Sau khi thu thập:

- Lưu output ở vị trí có quyền truy cập hạn chế.
- Redact secret trước khi chia sẻ.
- Không gửi heap dump hoặc JFR chứa dữ liệu nhạy cảm tới nơi lưu trữ công khai.
- Xóa dữ liệu chẩn đoán khi hết thời hạn lưu giữ.
- Đối chiếu kết quả với metrics/logs của ứng dụng và hệ điều hành.

Các file heap dump có thể rất lớn và chứa gần như mọi dữ liệu còn reachable trong heap. Thread dump, command line và system properties cũng có thể để lộ tên người dùng, đường dẫn, endpoint và thông tin bí mật.

## 14. jcmd không phải công cụ giám sát từ xa

`jcmd` làm việc với một JVM có thể attach từ môi trường cục bộ. Nó không tự cung cấp giao thức quản trị từ xa qua mạng.

Trong môi trường nhiều máy hoặc Kubernetes:

- Dùng SSH, cơ chế exec của container hoặc nền tảng vận hành để chạy công cụ tại đúng môi trường.
- Tuân thủ quyền truy cập process và container.
- Thu thập dữ liệu theo quy trình kiểm soát.
- Nếu cần monitoring liên tục hoặc quản trị từ xa, dùng hệ thống metrics, JMX/management agent, APM hoặc nền tảng quan sát phù hợp.

Không mở attach mechanism hoặc quyền truy cập process rộng ra mạng chỉ để tiện chạy `jcmd`.

## 15. So sánh nhanh một số công cụ chẩn đoán

| Công cụ | Vai trò chính |
| --- | --- |
| `jcmd` | Gửi nhiều diagnostic command tới JVM đích; công cụ tổng hợp được khuyến nghị cho nhiều tác vụ chẩn đoán HotSpot |
| `jps` | Liệt kê JVM process và thông tin main class |
| `jstack` | Lấy thread dump theo cách chuyên biệt |
| `jmap` | Công cụ chuyên biệt cho heap/map memory |
| `jstat` | Quan sát thống kê JVM như GC theo chu kỳ |
| JDK Mission Control | Phân tích recording JFR và dữ liệu chẩn đoán |

Các công cụ chuyên biệt vẫn có thể hữu ích, nhưng nhiều thao tác có thể thực hiện qua `jcmd`. Với Java 17, hãy bắt đầu bằng `jcmd <pid> help` để khám phá command mà target hỗ trợ, thay vì giả định một tùy chọn có mặt trên mọi build.

## 16. Ví dụ phiên chẩn đoán tổng hợp

Giả sử service `OrderApplication` có latency tăng và heap có dấu hiệu tăng liên tục. Một phiên thu thập có kiểm soát có thể gồm:

~~~bash
# 1. Xác định JVM
jcmd -l

# 2. Kiểm tra thông tin khởi chạy
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags

# 3. Lấy một số thread dump cách nhau
jcmd 24680 Thread.print -l > threads-1.txt
sleep 5
jcmd 24680 Thread.print -l > threads-2.txt
sleep 5
jcmd 24680 Thread.print -l > threads-3.txt

# 4. Xem heap và class histogram nếu impact cho phép
jcmd 24680 GC.heap_info
jcmd 24680 GC.class_histogram

# 5. Ghi JFR ngắn để phân tích runtime
jcmd 24680 JFR.start name=triage settings=profile duration=5m filename=/var/tmp/orders-triage.jfr
~~~

Các lệnh trong ví dụ cần thay PID và đường dẫn theo môi trường thực tế. Không chạy cả chuỗi một cách máy móc: xem impact, dung lượng và mức độ ảnh hưởng trước mỗi command. Nếu `GC.class_histogram` hoặc heap dump có rủi ro pause lớn đối với service, có thể bỏ qua ở thời điểm tải cao và thu thập vào cửa sổ bảo trì.

Sau khi recording hoàn tất, mở file `.jfr` bằng công cụ phân tích phù hợp. Kết hợp thread dump, heap metrics, JFR và application metrics để tìm nguyên nhân thay vì suy luận từ một snapshot.

## 17. Các lỗi thường gặp khi dùng jcmd

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không thấy JVM trong `jcmd -l` | Sai namespace/user, attach bị tắt hoặc JVM không tương thích | Kiểm tra process list, container, user và `DisableAttachMechanism` |
| `AttachNotSupportedException` | Không thể attach vào target trong môi trường hiện tại | Xác minh cùng host/namespace, quyền và trạng thái target |
| `Unknown diagnostic command` | JVM đích không hỗ trợ command đó | Gọi `jcmd PID help` và chọn lệnh được liệt kê |
| `IllegalArgumentException` về tham số | Sai cú pháp hoặc option không được hỗ trợ | Gọi `jcmd PID help <command>` |
| Không ghi được dump | Đường dẫn sai, thiếu quyền hoặc hết dung lượng | Kiểm tra filesystem và quyền ghi |
| Heap dump làm service pause lâu | Thao tác có impact cao, heap lớn hoặc GC cần thiết | Lên kế hoạch, xem xét thời điểm và dung lượng trước khi chạy |
| NMT báo chưa bật | JVM không khởi chạy với `-XX:NativeMemoryTracking` | Bật cho lần khởi chạy tiếp theo; không thể bật đầy đủ hồi tố |
| Không có file JFR như mong đợi | Sai tên recording, filename hoặc recording chưa kết thúc/dump | Kiểm tra `JFR.check`, `help JFR.start`, `JFR.dump`, `JFR.stop` |
| Output có secret | Command line/property hoặc heap chứa dữ liệu nhạy cảm | Hạn chế quyền truy cập và redact trước khi chia sẻ |

## 18. Câu hỏi tự kiểm tra

**1. `jcmd` dùng để làm gì?**  
Gửi diagnostic command tới JVM đang chạy để tra thông tin runtime và thu thập dữ liệu chẩn đoán.

**2. Lệnh nào liệt kê JVM mà công cụ nhìn thấy?**  
`jcmd -l`.

**3. Làm sao xem danh sách command mà một JVM hỗ trợ?**  
`jcmd <pid> help`.

**4. Làm sao xem cú pháp của một command cụ thể?**  
`jcmd <pid> help <command>`.

**5. `jcmd` có phải công cụ remote attach qua mạng không?**  
Không. Nó sử dụng cơ chế attach cục bộ và cần chạy trong môi trường có thể truy cập target process.

**6. Command nào lấy thread dump?**  
`jcmd <pid> Thread.print`; có thể dùng `-l` để in thêm thông tin lock.

**7. Command nào hiển thị heap summary?**  
`jcmd <pid> GC.heap_info`.

**8. `GC.class_histogram` cho biết điều gì?**  
Số instance và tổng dung lượng theo class trong heap theo phạm vi mà command chọn.

**9. Có thể bật Native Memory Tracking bằng jcmd sau khi JVM đã chạy không?**  
Không. NMT cần được bật lúc khởi chạy JVM.

**10. JFR command nào bắt đầu recording?**  
`JFR.start`; các command liên quan gồm `JFR.check`, `JFR.dump`, `JFR.stop`.

**11. Vì sao cần cẩn trọng với `GC.heap_dump`?**  
Heap dump có thể gây pause đáng kể, cần nhiều dung lượng và chứa dữ liệu nhạy cảm trong bộ nhớ.

**12. Nếu JVM không xuất hiện trong `jcmd -l`, có thể kết luận nó không chạy không?**  
Không. Hãy kiểm tra process list của hệ điều hành, user, container/PID namespace và attach mechanism.

**13. `VM.command_line` và `VM.system_properties` có thể làm lộ dữ liệu gì?**  
Tham số khởi chạy, endpoint, đường dẫn và đôi khi cả token/password nếu ứng dụng cấu hình sai.

**14. Thread dump có đủ để tìm CPU hot spot không?**  
Không. Thread dump là snapshot; JFR hoặc profiler phù hợp cung cấp dữ liệu định lượng về CPU.

**15. Vì sao phải kiểm tra `help` trên JVM đích?**  
Danh sách command, tham số và impact phụ thuộc phiên bản, build và cấu hình của JVM đang chạy.

## Tài liệu tham khảo chính thức

- [Java SE 17 — jcmd Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cú pháp, liệt kê process, command và tùy chọn công cụ.
- [Java SE 17 — Diagnostic Commands](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): danh sách diagnostic command và cách gọi.
- [Java SE 17 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-api-programmers-guide.pdf): cơ chế recording và phân tích sự kiện JFR.
- [Java SE 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): bật NMT lúc khởi chạy, baseline và so sánh native memory.
- [Java SE 17 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/): quy trình chẩn đoán JVM, heap, thread, GC và công cụ hỗ trợ.
