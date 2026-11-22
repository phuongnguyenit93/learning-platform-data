# Lệnh jcmd: gửi VM command đến JVM đang chạy

## Mục tiêu

Sau bài này, bạn có thể tìm JVM process và gửi diagnostic command tới tiến trình Java đang chạy; khám phá command mà JVM đích hỗ trợ; kiểm tra version, flags, system properties, uptime, thread, heap, class loader và metaspace; tạo heap dump; thu thập Java Flight Recorder (JFR); sử dụng Native Memory Tracking (NMT); hiểu impact của từng lệnh; và áp dụng jcmd trong quy trình chẩn đoán an toàn.

## 1. jcmd là gì?

**jcmd** là công cụ dòng lệnh đi kèm JDK, dùng để gửi diagnostic command request tới một Java Virtual Machine (JVM) đang chạy. JVM đích thực hiện thao tác chẩn đoán và trả kết quả cho công cụ.

Các việc thường dùng jcmd:

- Liệt kê JVM process và xác định PID.
- Khám phá command mà JVM đích hỗ trợ.
- Kiểm tra phiên bản JVM, command line, flags và system properties.
- In thread dump để điều tra ứng dụng chậm, treo hoặc deadlock.
- Xem heap information và class histogram.
- Tạo heap dump để phân tích memory leak.
- Bắt đầu, kiểm tra, dump và dừng Java Flight Recording.
- Xem native memory nếu NMT đã được bật.
- Kiểm tra class loader, metaspace, code cache và VM logging.

jcmd rất hữu ích khi cần điều tra một JVM đang chạy mà không phải dừng ứng dụng hoặc khởi động lại với các tùy chọn chẩn đoán mới. Tuy nhiên, không phải mọi diagnostic command đều không ảnh hưởng đến ứng dụng. Một số lệnh có thể tạo pause, kích hoạt garbage collection, tạo file lớn hoặc thay đổi cấu hình runtime.

## 2. Cú pháp và chọn JVM đích

Cú pháp tổng quát:

~~~bash
jcmd [pid | main-class] command [arguments]
~~~

Các dạng sử dụng chính:

~~~bash
jcmd -l
jcmd <pid>
jcmd <pid> help
jcmd <pid> help <command>
jcmd <pid> <command> [options] [arguments]
jcmd <pid> -f commands.txt
~~~

Trong đó:

- pid: process ID của JVM đích.
- main-class: tên main class đã dùng để khởi chạy ứng dụng; có thể khớp một phần hoặc toàn bộ.
- command: diagnostic command mà JVM đích hỗ trợ.
- arguments: tham số của diagnostic command.
- -f: đọc và thực thi các command từ file.

### Liệt kê JVM process

~~~bash
jcmd -l
~~~

Lệnh hiển thị PID, main class và command-line arguments của các Java process mà jcmd tìm thấy. Chạy jcmd không có tham số cũng tương đương jcmd -l.

Ví dụ output:

~~~text
4128 com.example.OrderService
7852 org.apache.catalina.startup.Bootstrap
9011 jdk.jcmd/sun.tools.jcmd.JCmd
~~~

PID và tên process trên máy thật sẽ khác ví dụ. jcmd thường cũng xuất hiện trong danh sách vì chính công cụ đang chạy bằng JVM.

Trên một số môi trường Docker, jcmd -l không liệt kê JVM chạy trong một Docker process riêng. Khi đó, hãy xác định PID bằng công cụ hệ điều hành như ps trong đúng container/PID namespace, rồi chạy jcmd trong môi trường có thể attach vào tiến trình đó.

### Chọn bằng PID hoặc main class

~~~bash
jcmd 4128 VM.version
jcmd com.example.OrderService VM.version
~~~

Dùng PID là cách rõ ràng nhất khi máy có nhiều ứng dụng cùng main class. Nếu main class khớp nhiều Java process, command có thể được gửi đến tất cả process phù hợp.

### Gửi command tới mọi JVM process

~~~bash
jcmd 0 VM.uptime
~~~

PID 0 có nghĩa gửi command tới tất cả Java process khả dụng. Chỉ dùng khi thực sự muốn thu thập thông tin từ mọi JVM; không dùng tùy tiện với lệnh tạo dump, kích hoạt GC hoặc thay đổi cấu hình.

### Xem trợ giúp

~~~bash
jcmd -h
jcmd 4128 help
jcmd 4128 help Thread.print
~~~

Danh sách command phụ thuộc JVM, phiên bản JDK, vendor, OS và cấu hình runtime. Luôn dùng help trên chính JVM đích trước khi dựa vào một command cụ thể.

## 3. Điều kiện để jcmd attach được vào JVM

Theo tài liệu JDK, jcmd phải chạy trên **cùng máy** với JVM đích và có cùng effective user ID và group ID đã dùng để khởi chạy JVM.

Các điều kiện thực tế cần kiểm tra:

- Dùng đúng PID của JVM, không nhầm PID của shell, container host hoặc process khác.
- jcmd và JVM phải ở môi trường có thể giao tiếp qua cơ chế attach của nền tảng.
- User chạy jcmd phải có effective UID/GID phù hợp với user chạy JVM.
- Process phải cho phép attach; JVM có thể được khởi chạy với -XX:+DisableAttachMechanism, khi đó attach diagnostic command bị vô hiệu hóa.
- Với container, cần xác định đúng PID namespace, user, quyền truy cập và vị trí chạy công cụ.
- JVM đích phải còn sống và phản hồi attach request.

jcmd không phải công cụ gửi command tùy ý tới JVM từ máy từ xa. Đối với quản trị từ xa, cần cơ chế khác như JMX được cấu hình và bảo vệ phù hợp hoặc hệ thống observability/management của ứng dụng.

Nếu jcmd không attach được, hãy kiểm tra điều kiện môi trường và thông báo lỗi thực tế trước khi thay đổi quyền hoặc khởi động lại dịch vụ.

## 4. Khám phá diagnostic command trên JVM đích

### Liệt kê và xem chi tiết command

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_dump
jcmd <pid> help Thread.print
jcmd <pid> help JFR.start
~~~

Output trợ giúp mô tả cú pháp, tên option, kiểu dữ liệu, argument bắt buộc/tùy chọn, giá trị mặc định và mức độ ảnh hưởng (Impact) nếu command công bố thông tin đó.

### Quy tắc truyền option và argument

Diagnostic command có thể nhận option và argument:

- Option dùng dạng key hoặc key=value, tùy command.
- Argument được truyền như giá trị, không viết name=value trừ khi tài liệu command yêu cầu.
- Nếu giá trị có dấu cách, đặt trong dấu nháy đơn hoặc kép theo cú pháp shell.
- Dấu nháy cần escape khi bên trong giá trị đã có dấu nháy.

Ví dụ option có giá trị:

~~~bash
jcmd <pid> VM.classloaders show-classes=true verbose=true
~~~

Ví dụ argument là tên file:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Tên option, cách đặt dấu gạch ngang và kiểu argument có thể khác giữa các command. Dùng jcmd <pid> help <command> để xác nhận cú pháp trên JVM đang kiểm tra.

## 5. Kiểm tra thông tin JVM và cấu hình

Các command dưới đây thường có impact thấp và phù hợp để bắt đầu điều tra.

### VM.version

~~~bash
jcmd <pid> VM.version
~~~

In thông tin phiên bản JVM/HotSpot và JDK. Hữu ích khi process được khởi chạy từ JDK khác với JDK đang có trong PATH.

### VM.command_line

~~~bash
jcmd <pid> VM.command_line
~~~

In command line dùng để khởi chạy JVM. Có thể giúp xác nhận main class/JAR, heap options như -Xms và -Xmx, system properties -D..., module/class path, JVM flags và agent options.

Command line có thể chứa token, password hoặc giá trị nhạy cảm nếu ứng dụng cấu hình sai. Hãy bảo vệ output và che secret trước khi chia sẻ.

### VM.flags

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.flags -all
~~~

In VM flag cùng giá trị hiện tại. Tùy chọn -all yêu cầu hiển thị tất cả flag mà VM hỗ trợ.

### VM.system_properties

~~~bash
jcmd <pid> VM.system_properties
~~~

In system property của JVM, ví dụ java.home, java.version, os.name, os.arch, user.dir, file.encoding và property ứng dụng đặt bằng -Dname=value.

Output có thể rất dài và có thể chứa endpoint nội bộ, username, đường dẫn, token hoặc thông tin nhạy cảm. Không đăng nguyên output lên ticket/chat công khai.

### VM.uptime và VM.info

~~~bash
jcmd <pid> VM.uptime
jcmd <pid> VM.info
~~~

VM.uptime in thời gian JVM đã chạy, hữu ích để đối chiếu thời điểm deploy, restart hoặc bắt đầu sự cố. VM.info in thông tin tổng quan về môi trường và trạng thái JVM.

### VM.log

~~~bash
jcmd <pid> VM.log list=true
~~~

Liệt kê cấu hình logging hiện tại. VM.log cũng có thể cấu hình output, tags, decorators hoặc rotate log. Vì command có thể thay đổi logging runtime, hãy đọc trợ giúp và chỉ chỉnh cấu hình khi có kế hoạch rõ ràng.

## 6. Thread dump và ứng dụng bị treo

Thread dump cho biết thread đang ở trạng thái nào và thực thi tại stack frame nào. Đây là dữ liệu quan trọng khi ứng dụng bị treo, request chậm, thread pool cạn hoặc nghi ngờ deadlock.

### In thread dump

~~~bash
jcmd <pid> Thread.print
~~~

Command in các platform thread và virtual thread đang mounted, kèm stack trace.

In thêm thông tin lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

Tùy chọn -l yêu cầu in thông tin lock thuộc java.util.concurrent cùng thread dump.

### Lưu thread dump ra file

~~~bash
jcmd <pid> Thread.dump_to_file threads.txt
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Command này ghi các thread cùng stack trace ra file. Impact phụ thuộc số lượng thread.

### Cách đọc thread dump

1. Tìm thread ở trạng thái BLOCKED, WAITING hoặc TIMED_WAITING.
2. Xem stack trace để biết thread đang chờ lock, I/O, queue hay condition nào.
3. Tìm nhiều thread cùng chờ một monitor hoặc lock.
4. Kiểm tra thread RUNNABLE có đang lặp trong cùng stack frame hoặc xử lý một tác vụ quá lâu không.
5. So sánh nhiều thread dump cách nhau một khoảng thời gian để nhận ra trạng thái đứng yên.
6. Đối chiếu tên thread với request, executor, scheduler hoặc subsystem của ứng dụng.

Một thread ở trạng thái WAITING không tự động có nghĩa là lỗi; worker thread bình thường thường chờ tác vụ. Cần hiểu vai trò thread và so sánh với trạng thái mong đợi.

### Virtual thread

JDK mới hỗ trợ các diagnostic command liên quan virtual thread:

~~~bash
jcmd <pid> Thread.vthread_scheduler
jcmd <pid> Thread.vthread_pollers
~~~

Thread.vthread_scheduler in thông tin virtual-thread scheduler và delayed-task scheduler. Thread.vthread_pollers in I/O poller hỗ trợ virtual thread trong các thao tác network blocking. Các command này chỉ có trên JVM có hỗ trợ virtual thread và diagnostic command tương ứng.

## 7. Kiểm tra heap và garbage collection

### GC.heap_info

~~~bash
jcmd <pid> GC.heap_info
~~~

In thông tin tổng quát về Java heap. Đây là snapshot hữu ích để bắt đầu kiểm tra heap usage, nhưng không thay thế heap dump hoặc phân tích GC log.

### GC.class_histogram

~~~bash
jcmd <pid> GC.class_histogram
jcmd <pid> GC.class_histogram -all
~~~

In histogram về số instance và dung lượng heap theo class. Option -all yêu cầu kiểm tra cả object unreachable. Theo tài liệu JDK 26, command này có impact cao, phụ thuộc kích thước và nội dung heap.

Có thể lưu output bằng redirect của shell:

~~~bash
jcmd <pid> GC.class_histogram > class-histogram.txt
~~~

### GC.heap_dump

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Tạo heap dump định dạng HPROF để mở bằng công cụ phân tích heap như Java Mission Control, Eclipse Memory Analyzer hoặc công cụ tương thích.

Theo tài liệu JDK 26, command này có impact cao; mặc định có yêu cầu full GC trừ khi dùng option -all. Heap dump có thể rất lớn, tạo pause và chứa dữ liệu ứng dụng nhạy cảm.

Có thể nén output:

~~~bash
jcmd <pid> GC.heap_dump -gz=1 heap.hprof.gz
~~~

Option -overwrite cho phép ghi đè file đã tồn tại; không bật nếu chưa xác nhận đường dẫn và nội dung file đích.

Trước khi tạo heap dump, hãy xác nhận đủ dung lượng đĩa, thư mục có quyền ghi, nơi lưu được bảo vệ và quy trình chuyển giao file. Heap dump có thể chứa password, access token, dữ liệu cá nhân và nội dung request.

### GC.run

~~~bash
jcmd <pid> GC.run
~~~

Command này gọi System.gc() trong JVM đích. Đây là yêu cầu GC, không phải bảo đảm một chu kỳ full GC cụ thể sẽ chạy. Không dùng nó như cách định kỳ "dọn RAM" hoặc kết luận memory leak đã được sửa.

| Mục tiêu | Command | Mức ảnh hưởng theo tài liệu JDK 26 |
|---|---|---|
| Xem heap tổng quát | GC.heap_info | Medium |
| Xem số object theo class | GC.class_histogram | High |
| Lấy snapshot toàn heap | GC.heap_dump | High |
| Yêu cầu System.gc() | GC.run | Medium |

Hãy bắt đầu bằng GC.heap_info; chỉ dùng histogram hoặc heap dump khi cần dữ liệu sâu hơn và đã đánh giá impact.

## 8. Theo dõi native memory bằng Native Memory Tracking

Java heap chỉ là một phần memory của process. JVM còn dùng native memory cho thread stack, metaspace, code cache, GC, compiler và các subsystem khác. Native library của ứng dụng cũng có thể cấp phát memory ngoài heap.

**Native Memory Tracking (NMT)** là tính năng của HotSpot VM theo dõi memory nội bộ do JVM/HotSpot sử dụng. NMT bị tắt mặc định và phải được bật khi JVM khởi chạy.

### Bật NMT lúc khởi chạy

Chế độ summary:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Chế độ detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

- summary: theo dõi tổng hợp theo subsystem.
- detail: bổ sung dữ liệu chi tiết hơn theo call site và vùng memory.
- off: tắt tracking; đây là mặc định.

Không thể bật hoặc khởi động lại NMT bằng jcmd sau khi JVM đã chạy. Nếu process hiện tại khởi chạy với NMT off, cần lên kế hoạch restart với tùy chọn startup phù hợp mới thu thập được dữ liệu NMT.

NMT có overhead và cần được cân nhắc trước khi bật trên production. Nó cũng không theo dõi đầy đủ allocation của native code bên thứ ba/JNI hoặc mọi thư viện native.

### Xem native memory và so sánh baseline

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Nếu đã bật detail:

~~~bash
jcmd <pid> VM.native_memory detail.diff
~~~

Baseline là mốc để so sánh mức thay đổi về sau. Dữ liệu diff giúp nhận ra subsystem nào tăng memory theo thời gian. Một lần snapshot chưa đủ kết luận leak; hãy thu thập nhiều mốc trong cùng điều kiện tải.

NMT theo dõi memory nội bộ của HotSpot/JVM, không phải bộ đếm tổng memory của toàn bộ process. Nếu RSS của process tăng nhưng NMT không giải thích được, cần xem thêm native library, direct buffer, memory mapping và công cụ OS.

## 9. Thu thập Java Flight Recording bằng jcmd

Java Flight Recorder (JFR) ghi lại event của JVM và ứng dụng để phân tích hiệu năng, latency, allocation, thread, GC và nhiều hoạt động runtime khác.

Các command JFR trong jcmd:

- JFR.start: bắt đầu recording.
- JFR.check: xem recording đang chạy.
- JFR.dump: ghi dữ liệu recording hiện tại ra file nhưng recording vẫn tiếp tục.
- JFR.stop: dừng recording và có thể ghi dữ liệu ra file.
- JFR.configure: xem hoặc cấu hình tham số JFR.
- JFR.view: hiển thị dữ liệu theo các view có sẵn.

### Bắt đầu recording có giới hạn thời gian

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=2m filename=diagnostic.jfr
~~~

- name: tên recording để tham chiếu về sau.
- settings=profile: chọn cấu hình profile có sẵn.
- duration=2m: recording tự kết thúc sau hai phút.
- filename: nơi ghi recording khi kết thúc.

Có thể đặt maxage và maxsize để giới hạn dữ liệu lưu trên disk khi recording dùng disk repository:

~~~bash
jcmd <pid> JFR.start name=bounded settings=profile maxage=10m maxsize=250M
~~~

Chọn settings phù hợp với mục tiêu điều tra. Profile có thể thu thập nhiều event hơn cấu hình mặc định; hãy cân nhắc overhead và kích thước file.

### Kiểm tra recording

~~~bash
jcmd <pid> JFR.check
~~~

Hiển thị các recording đang hoạt động. Có thể chỉ định name=diagnostic hoặc verbose=true để xem thêm event settings.

### Dump dữ liệu nhưng giữ recording tiếp tục chạy

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic-snapshot.jfr
~~~

JFR.dump ghi dữ liệu hiện tại ra file; recording vẫn tiếp tục. Có thể dump một khoảng thời gian bằng begin, end, maxage hoặc giới hạn kích thước theo cú pháp được command hỗ trợ.

Option path-to-gc-roots=true có thể hữu ích khi nghi ngờ memory leak, nhưng việc thu thập đường dẫn tới GC roots có thể khiến ứng dụng pause trong một khoảng thời gian. Chỉ bật khi có mục tiêu điều tra rõ ràng.

### Dừng recording và lưu file

~~~bash
jcmd <pid> JFR.stop name=diagnostic filename=diagnostic-final.jfr
~~~

Nếu dừng recording mà không chỉ định filename, dữ liệu có thể bị loại bỏ. Hãy kiểm tra help của command và xác nhận file đầu ra đã được tạo.

Có thể mở file .jfr bằng Java Mission Control (JMC) hoặc dùng công cụ jfr của JDK để đọc và xuất dữ liệu. jcmd quản lý recording trên JVM đang chạy; công cụ jfr xử lý file recording đã ghi.

## 10. Kiểm tra class loader, class và metaspace

Khi ứng dụng có plugin, application server, dynamic class loading hoặc nghi ngờ class loader leak, các command sau có ích.

### VM.classloader_stats và VM.classloaders

~~~bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> VM.classloaders show-classes=true verbose=true
~~~

VM.classloader_stats in thống kê của các ClassLoader. VM.classloaders in class loader hierarchy; option show-classes và verbose cung cấp thêm thông tin chi tiết.

### VM.classes và VM.class_hierarchy

~~~bash
jcmd <pid> VM.classes
jcmd <pid> VM.class_hierarchy com.example.Order
~~~

VM.classes in các class đã được load. Option -verbose yêu cầu thông tin class chi tiết hơn; output có thể rất lớn.

VM.class_hierarchy in hierarchy của một class cụ thể. Có thể dùng -s để hiển thị subclasses cùng superclasses và -i để in inherited interfaces.

### VM.metaspace

~~~bash
jcmd <pid> VM.metaspace basic=true scale=MB
~~~

In thống kê metaspace. Có thể yêu cầu thông tin theo class loader hoặc class khi cần điều tra chi tiết; hãy xem jcmd <pid> help VM.metaspace để biết option được JVM đích hỗ trợ.

Nếu số class hoặc class loader tăng liên tục sau mỗi lần deploy/reload, hãy so sánh histogram, classloader stats và metaspace qua nhiều thời điểm. Class loader không được thu hồi có thể giữ lại class và metadata.

## 11. Một số diagnostic command hữu ích khác

| Command | Mục đích |
|---|---|
| Compiler.queue | In các method đang chờ JIT compilation |
| Compiler.CodeHeap_Analytics | Phân tích code heap |
| VM.dynlibs | Liệt kê dynamic library đã load |
| VM.events | In VM event log |
| VM.stringtable | Dump string table |
| VM.symboltable | Dump symbol table |
| VM.cds | Tạo static/dynamic CDS archive trong điều kiện phù hợp |
| ManagementAgent.status | Xem trạng thái management agent |
| ManagementAgent.start_local | Khởi động local management agent |
| ManagementAgent.start | Khởi động remote management agent |
| ManagementAgent.stop | Dừng management agent |

Một số command chỉ có trên Linux, một số chỉ xuất hiện khi VM/provider hỗ trợ hoặc cần tùy chọn khởi động trước đó. Đặc biệt, ManagementAgent.start có thể mở bề mặt quản trị từ xa; không bật JMX remote nếu chưa cấu hình authentication, authorization, TLS, network binding và firewall đúng chính sách.

Các command như JVMTI.agent_load, GC.run, VM.log hoặc VM.set_flag có thể thay đổi trạng thái JVM. Đọc help và đánh giá rủi ro trước khi chạy trên dịch vụ production.

## 12. Chạy nhiều command từ file

Có thể lưu các command vào file văn bản, mỗi dòng là một diagnostic command:

~~~text
VM.version
VM.uptime
VM.flags
GC.heap_info
Thread.print
~~~

Gửi file tới JVM:

~~~bash
jcmd <pid> -f diagnostics.txt
~~~

Cách này tiện cho một bộ snapshot tiêu chuẩn. Tuy nhiên, hãy phân loại command theo mức ảnh hưởng trước khi đưa vào file dùng chung. Không gộp heap dump, class histogram hoặc command thay đổi cấu hình vào bộ thu thập định kỳ nếu chưa đánh giá impact.

## 13. Ví dụ thực hành hoàn chỉnh: tạo JVM đích và chẩn đoán bằng jcmd

Ví dụ này tạo một chương trình Java chạy liên tục để có thời gian attach từ terminal khác.

Tạo file DiagnosticTarget.java:

~~~java
public class DiagnosticTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("jcmd-target-ready");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
~~~

### Biên dịch

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 DiagnosticTarget.java
~~~

### Khởi chạy JVM đích

Terminal A:

~~~bash
java DiagnosticTarget
~~~

Output:

~~~text
pid=<PID của JVM đang chạy>
jcmd-target-ready
~~~

PID thay đổi theo mỗi lần chạy. Giữ terminal A hoạt động để JVM tiếp tục chạy.

### Tìm PID và xem trợ giúp

Terminal B:

~~~bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.uptime
~~~

Thay <PID> bằng số được in ở terminal A.

### Kiểm tra JVM

~~~bash
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.flags
jcmd <PID> VM.system_properties
~~~

### In thread dump

~~~bash
jcmd <PID> Thread.print
~~~

Vì chương trình đang sleep, main thread thường có stack frame liên quan Thread.sleep. Đây là trạng thái chờ bình thường của ví dụ, không phải deadlock.

### Xem heap và class histogram

~~~bash
jcmd <PID> GC.heap_info
jcmd <PID> GC.class_histogram
~~~

Histogram có impact cao hơn heap info. Chỉ chạy khi cần quan sát object trên heap.

### Ghi JFR trong hai phút

~~~bash
jcmd <PID> JFR.start name=lab settings=profile duration=2m filename=lab.jfr
jcmd <PID> JFR.check
~~~

Sau khi recording kết thúc, mở lab.jfr bằng JDK Mission Control hoặc công cụ JFR tương thích.

### Dừng JVM đích

Quay lại terminal A và nhấn Ctrl+C. Không cần gửi GC.run hoặc command khác để dừng chương trình mẫu.

Ví dụ này minh họa quy trình attach vào một JVM đang chạy. Trong môi trường production, hãy dùng PID đúng, kiểm tra command có sẵn và chọn diagnostic command theo impact.

## 14. Chọn command theo tình huống sự cố

| Tình huống | Bước đầu tiên | Bước tiếp theo |
|---|---|---|
| Ứng dụng phản hồi chậm | VM.uptime, VM.flags, Thread.print | JFR.start và phân tích recording |
| Nghi ngờ deadlock | Thread.print -l | So sánh nhiều thread dump và lock owner |
| Heap tăng liên tục | GC.heap_info | GC.class_histogram, sau đó heap dump nếu cần |
| Nghi ngờ memory leak | JFR và histogram theo thời gian | Heap dump, phân tích dominator/retained size |
| Process RSS cao nhưng heap nhỏ | VM.native_memory summary nếu NMT đã bật | So sánh baseline/diff và dùng OS tools |
| Metaspace tăng | VM.classloader_stats, VM.metaspace | VM.classloaders show-classes=true |
| JVM dùng sai cấu hình | VM.command_line, VM.flags, VM.system_properties | Đối chiếu với deployment config |
| JIT/code cache bất thường | Compiler.queue, Compiler.CodeHeap_Analytics | Thu thập JFR và xem compilation events |

Không nên chạy tất cả command cùng lúc. Hãy bắt đầu bằng các command impact thấp, xác định giả thuyết rồi mới thu thập dữ liệu nặng hơn.

## 15. Mức độ ảnh hưởng và an toàn khi dùng trên production

Tài liệu jcmd JDK 26 mô tả impact cho từng diagnostic command. Một số ví dụ:

- **Low:** VM.version, VM.uptime, VM.flags, VM.system_properties, JFR.check.
- **Medium:** Thread.print, GC.heap_info, VM.metaspace, GC.run.
- **High:** GC.class_histogram, GC.heap_dump.

Mức impact không phải cam kết thời gian cố định. Ảnh hưởng thực tế phụ thuộc kích thước heap, số thread/class, tải ứng dụng, collector và môi trường.

Các nguyên tắc khi chạy trên production:

1. Xác nhận PID, main class và host/container trước khi gửi command.
2. Bắt đầu bằng lệnh impact thấp và chỉ mở rộng khi cần.
3. Kiểm tra dung lượng disk trước khi tạo heap dump hoặc JFR file lớn.
4. Chọn thư mục output có quyền ghi, quota và retention phù hợp.
5. Bảo vệ heap dump, thread dump, system properties và command line vì có thể chứa dữ liệu nhạy cảm.
6. Không gửi command tới PID 0 nếu không muốn tác động nhiều JVM.
7. Không chạy GC.run như một thao tác tối ưu hóa định kỳ.
8. Không thay đổi VM flags, logging hoặc management agent khi chưa có change plan.
9. Ghi lại command, thời điểm, PID, JDK version và người thực hiện để phục vụ audit.
10. Xóa hoặc lưu trữ dữ liệu chẩn đoán theo chính sách dữ liệu của tổ chức.

Nếu command bị timeout hoặc JVM phản hồi chậm, không lặp lại các lệnh high-impact một cách liên tục. Kiểm tra trạng thái process, tải hệ thống và output đã tạo trước khi quyết định bước tiếp theo.

## 16. Lỗi thường gặp và cách xử lý

### Không tìm thấy PID

**Dấu hiệu:** jcmd -l không liệt kê ứng dụng.

**Nguyên nhân:** process chạy trong container/PID namespace khác, user không có quyền nhìn thấy process, JVM đã thoát hoặc không phải Java process.

**Cách xử lý:** kiểm tra process bằng công cụ OS trong đúng môi trường; xác định PID của JVM; chạy jcmd từ cùng máy/namespace phù hợp.

### Attach failed hoặc Operation not permitted

**Dấu hiệu:** jcmd không attach được vào process.

**Nguyên nhân:** khác effective UID/GID, sai namespace, thiếu quyền, JVM tắt attach mechanism hoặc process không phản hồi.

**Cách xử lý:** xác minh user/group, PID, môi trường container và startup option -XX:+DisableAttachMechanism; không tự ý nâng quyền rộng hoặc thay đổi cấu hình production.

### Unknown diagnostic command

**Dấu hiệu:** JVM báo command không tồn tại.

**Nguyên nhân:** command không được hỗ trợ trên JVM/vendor/version đó hoặc tên command viết sai.

**Cách xử lý:** chạy jcmd <pid> help, rồi jcmd <pid> help <command>; dùng command tương đương có sẵn trên target.

### Command báo sai option/argument

**Dấu hiệu:** command không chấp nhận tham số.

**Nguyên nhân:** sai cách viết key=value, sai dấu gạch ngang, thiếu argument hoặc khác biệt giữa phiên bản JDK.

**Cách xử lý:** đọc trợ giúp command trên chính JVM đích; truyền option và argument theo đúng cú pháp được liệt kê.

### Heap dump không ghi được

**Dấu hiệu:** command báo lỗi tạo file hoặc hết dung lượng.

**Nguyên nhân:** đường dẫn không tồn tại, thiếu quyền ghi, disk đầy hoặc file đã tồn tại mà không bật overwrite.

**Cách xử lý:** chọn thư mục hợp lệ, kiểm tra dung lượng/quyền và chính sách overwrite; không ghi đè file dump cũ ngoài ý muốn.

### Histogram hoặc heap dump làm ứng dụng pause

**Dấu hiệu:** latency tăng trong lúc thu thập.

**Nguyên nhân:** command có impact cao và phụ thuộc kích thước heap/nội dung object; heap dump mặc định có thể yêu cầu full GC.

**Cách xử lý:** lên lịch cửa sổ thu thập phù hợp, bắt đầu từ GC.heap_info, giới hạn tần suất và chỉ dump khi cần.

### VM.native_memory không có dữ liệu

**Dấu hiệu:** NMT báo tracking chưa được bật hoặc không có thông tin hữu ích.

**Nguyên nhân:** JVM khởi chạy với NMT off (mặc định), hoặc đang dùng JVM không hỗ trợ HotSpot NMT.

**Cách xử lý:** lên kế hoạch khởi động lại với -XX:NativeMemoryTracking=summary hoặc detail; không thể bật NMT cho process hiện tại bằng jcmd.

### JFR không ghi được file

**Dấu hiệu:** JFR.start/JFR.stop báo lỗi hoặc file không xuất hiện.

**Nguyên nhân:** sai tên recording, thiếu quyền ghi, disk đầy, option không hợp lệ hoặc JVM không hỗ trợ cấu hình được yêu cầu.

**Cách xử lý:** dùng JFR.check, đọc help JFR.start, xác nhận filename/permission/disk và kiểm tra output của stop/dump.

### Command line hoặc properties chứa secret

**Dấu hiệu:** output chẩn đoán có password, token hoặc URL nội bộ.

**Nguyên nhân:** secret được truyền qua -D, command line hoặc system property.

**Cách xử lý:** bảo vệ file output, giới hạn quyền đọc, che dữ liệu trước khi chia sẻ và chuyển secret sang cơ chế quản lý an toàn hơn.

## 17. Checklist vận hành với jcmd

### Trước khi chạy

- [ ] Xác nhận đúng host, container và PID namespace.
- [ ] Xác định PID bằng jcmd -l hoặc công cụ OS phù hợp.
- [ ] Đảm bảo cùng effective user/group với JVM đích.
- [ ] Kiểm tra jcmd <pid> help để biết command có sẵn.
- [ ] Đọc impact và option của command cần chạy.
- [ ] Xác định thư mục output, quyền ghi, disk space và retention.
- [ ] Đánh giá dữ liệu nhạy cảm trong output.

### Trong khi chạy

- [ ] Bắt đầu bằng VM.version, VM.uptime, VM.flags hoặc VM.info.
- [ ] Dùng Thread.print khi điều tra thread/blocking.
- [ ] Dùng heap histogram/dump chỉ khi cần và đã đánh giá impact.
- [ ] Dùng JFR với duration/maxage/maxsize phù hợp.
- [ ] Chỉ dùng NMT nếu đã bật lúc JVM khởi động.
- [ ] Tránh gửi command tới nhiều process ngoài ý định.
- [ ] Không lặp lại command nặng khi chưa biết kết quả lần trước.

### Sau khi chạy

- [ ] Kiểm tra command exit/output và file thực sự được tạo.
- [ ] Ghi PID, JDK version, thời điểm và command đã dùng.
- [ ] Bảo vệ thread/heap/JFR dump theo chính sách dữ liệu.
- [ ] Phân tích dữ liệu cùng log, metrics và deployment timeline.
- [ ] Xóa hoặc lưu trữ artifact chẩn đoán theo retention policy.
- [ ] Tổng hợp nguyên nhân và hành động tiếp theo vào incident record.

## 18. Tài liệu tham khảo chính thức

- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — cú pháp, cách chọn PID/main class, yêu cầu attach, danh sách diagnostic command và impact của từng lệnh.
- [Diagnostic Tools — Java SE 26 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html) — các command thường dùng để kiểm tra JVM, thread, heap và JFR.
- [Troubleshoot Memory Leaks — Java SE 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html) — histogram, heap dump và Java Flight Recording khi điều tra memory leak.
- [Native Memory Tracking — Java Virtual Machine Guide 26](https://docs.oracle.com/en/java/javase/26/vm/) — bật NMT, lấy summary/detail, baseline và diff bằng jcmd.
- [Java Flight Recorder — Java SE 26](https://docs.oracle.com/en/java/javase/26/jfapi/) — JFR API và cách quản lý/đọc recording.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — tùy chọn JVM như -XX:NativeMemoryTracking và -XX:+DisableAttachMechanism.

jcmd là điểm vào thực tế để yêu cầu một JVM đang chạy tự cung cấp dữ liệu chẩn đoán. Hãy khám phá command trên JVM đích, bắt đầu bằng thao tác impact thấp, chỉ tạo dump/recording khi cần và bảo vệ mọi dữ liệu thu thập được.
