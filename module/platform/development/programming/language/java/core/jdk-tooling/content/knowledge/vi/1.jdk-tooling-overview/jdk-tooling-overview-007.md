# Công cụ chẩn đoán trong JDK Tooling

Công cụ chẩn đoán của JDK giúp quan sát một tiến trình Java đang chạy, tìm nguyên nhân ứng dụng chậm hoặc treo, theo dõi garbage collection (GC), kiểm tra heap và thu thập dữ liệu để phân tích sâu hơn. Chúng thường được dùng khi ứng dụng đã chạy trong môi trường phát triển, kiểm thử hoặc production và cần bằng chứng từ chính JVM.

Không có một công cụ nào trả lời được mọi câu hỏi. Hãy bắt đầu bằng dữ liệu ít tốn kém như thông tin tiến trình và thread dump, sau đó mới thu heap dump hoặc chạy công cụ có khả năng làm JVM tạm dừng.

## 1. Các nhóm công cụ và khi nào nên dùng

| Nhóm cần kiểm tra | Công cụ chính | Dữ liệu thu được |
|---|---|---|
| Tìm tiến trình và cấu hình JVM | jps, jcmd, jinfo | PID, main class, tham số khởi chạy, JVM flags và system properties |
| Thread và lock | jcmd Thread.print, jstack | Stack trace, trạng thái thread, monitor và lock đang chờ |
| Heap và object | jcmd GC.heap_info, GC.class_histogram, GC.heap_dump; jmap | Tình trạng heap, số lượng object theo class, heap dump |
| GC và hiệu năng | jstat, unified logging, JFR | Tần suất GC, mức sử dụng vùng heap, pause và sự kiện runtime |
| Bộ nhớ native | Native Memory Tracking, jcmd VM.native_memory, jhsdb | Phân bổ bộ nhớ native do HotSpot theo dõi |
| Quan sát trực quan | JConsole, VisualVM | Biểu đồ heap, thread, GC, MBeans và profiling |

Trong JDK hiện đại, **jcmd** thường là điểm bắt đầu tốt nhất vì nó gom nhiều lệnh chẩn đoán vào một giao diện. Các lệnh riêng như jstack và jmap vẫn hữu ích, đặc biệt khi đã quen với quy trình cũ, nhưng nên kiểm tra khả năng của jcmd trên đúng phiên bản JVM trước.

## 2. Chuẩn bị trước khi chẩn đoán

Các công cụ dòng lệnh nằm trong thư mục **bin** của JDK, ví dụ **$JAVA_HOME/bin** trên Linux/macOS hoặc **%JAVA_HOME%\\bin** trên Windows. Có thể thêm thư mục này vào PATH để gọi lệnh ở mọi thư mục.

Một số nguyên tắc quan trọng:

- Chạy công cụ trên cùng máy với JVM cần kiểm tra và thường bằng cùng tài khoản hệ điều hành đã khởi chạy JVM.
- Ưu tiên dùng JDK cùng major version với JVM đích. Một số lệnh hoặc trường dữ liệu thay đổi giữa các phiên bản.
- Xác định đúng PID trước khi chạy lệnh. Một máy có thể có nhiều tiến trình Java.
- Cơ chế attach có thể bị tắt bằng tùy chọn JVM **-XX:+DisableAttachMechanism**, hoặc bị giới hạn bởi quyền hệ điều hành, container, namespace hay cấu hình runtime.
- Trong container, PID nhìn từ host và PID nhìn bên trong container có thể khác nhau. Chạy công cụ trong đúng môi trường và namespace chứa JVM.
- Không giả định mọi lệnh đều có mặt ở mọi bản JDK. Dùng lệnh help của công cụ và JVM đích để xác nhận.

Ví dụ dưới đây dùng **<pid>** làm ký hiệu cho PID thực tế. Hãy thay ký hiệu này bằng số PID đã tìm được, không gõ nguyên dấu ngoặc nhọn.

## 3. Tìm tiến trình Java và xem cấu hình JVM

### Liệt kê tiến trình

**jps** liệt kê các JVM mà công cụ có thể phát hiện:

~~~bash
jps -lv
~~~

Các tùy chọn thường dùng:

- **-l**: hiển thị tên class chính đầy đủ hoặc đường dẫn JAR.
- **-v**: hiển thị tham số JVM.
- **-m**: hiển thị tham số truyền cho main method.

Có thể dùng **jcmd -l** để liệt kê các JVM có thể attach:

~~~bash
jcmd -l
~~~

Nếu tiến trình không xuất hiện, kiểm tra tài khoản đang chạy lệnh, PID namespace, quyền truy cập và việc attach có bị vô hiệu hóa hay không. Kết quả của jps không phải lúc nào cũng là danh sách đầy đủ mọi tiến trình Java trên host.

### Xem thông tin một JVM

Trước khi thu thập dữ liệu, hỏi JVM những lệnh mà nó hỗ trợ:

~~~bash
jcmd <pid> help
~~~

Một số lệnh thường hữu ích:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
~~~

Ý nghĩa:

- **VM.version**: phiên bản JVM đang chạy.
- **VM.command_line**: class chính, JAR và tham số khởi chạy.
- **VM.flags**: các cờ cấu hình JVM đang có hiệu lực.
- **VM.system_properties**: system properties của tiến trình.

Có thể dùng **jinfo** để kiểm tra một số thông tin tương tự:

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
~~~

Thông tin command line và system properties có thể chứa đường dẫn, token hoặc thông tin kết nối. Khi chia sẻ log chẩn đoán, hãy rà soát và che dữ liệu nhạy cảm.

## 4. Phân tích thread và tình trạng treo

Thread dump là ảnh chụp stack trace của các thread tại một thời điểm. Nó giúp tìm thread đang chạy lâu, chờ lock, chờ I/O hoặc mắc vào deadlock.

### Thu thread dump bằng jcmd

~~~bash
jcmd <pid> Thread.print -l
~~~

Tùy chọn **-l** yêu cầu hiển thị thêm thông tin về các lock mà thread đang giữ hoặc chờ. Có thể lưu kết quả vào file để so sánh:

~~~bash
jcmd <pid> Thread.print -l > thread-1.txt
~~~

Lặp lại sau khoảng 5–10 giây để lấy thêm snapshot:

~~~bash
jcmd <pid> Thread.print -l > thread-2.txt
jcmd <pid> Thread.print -l > thread-3.txt
~~~

Nếu một thread liên tục xuất hiện ở cùng một stack frame, đó có thể là dấu hiệu bị kẹt hoặc xử lý một công việc kéo dài. Nếu stack thay đổi giữa các lần lấy mẫu, thread có thể vẫn đang tiến triển.

### Dùng jstack

~~~bash
jstack -l <pid>
~~~

**jstack** tạo thread dump trực tiếp. Với JVM đang chạy cục bộ, jcmd thường là lựa chọn linh hoạt hơn; jstack vẫn hữu ích trong các quy trình đã có sẵn hoặc khi cần lệnh quen thuộc.

### Hiểu các trạng thái thread

- **RUNNABLE**: thread đang chạy hoặc sẵn sàng chạy. Trạng thái này không đảm bảo thread đang tiêu thụ CPU; nó cũng có thể đang ở trong một lời gọi native hoặc chờ tài nguyên ở tầng hệ điều hành.
- **BLOCKED**: thread đang chờ lấy intrinsic monitor để vào hoặc tiếp tục một vùng synchronized.
- **WAITING**: thread chờ một thread khác thực hiện hành động, thường không có thời hạn, ví dụ chờ qua Object.wait hoặc LockSupport.park.
- **TIMED_WAITING**: thread chờ có thời hạn, ví dụ Thread.sleep hoặc wait với timeout.
- **TERMINATED**: thread đã kết thúc; trạng thái này thường không còn xuất hiện như một thread đang hoạt động trong dump.

Khi đọc dump, hãy chú ý:

1. Tên thread và mục đích của nó, ví dụ HTTP worker, scheduler hoặc consumer.
2. Trạng thái thread và stack trace hiện tại.
3. Dòng mô tả lock mà thread đang chờ hoặc đang giữ.
4. Thread nào giữ lock mà nhiều thread khác cùng chờ.
5. Phần thông báo deadlock ở cuối dump, nếu JVM phát hiện được deadlock.

Một thread ở trạng thái WAITING hoặc TIMED_WAITING không mặc nhiên là lỗi. Thread pool thường có các worker chờ nhận việc. Cần kết hợp trạng thái, stack trace, mức tải và nhiều snapshot để kết luận.

### Ví dụ chương trình nhỏ để thực hành

Tạo file **DiagnosticDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class DiagnosticDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "diagnostic-worker");

        worker.start();
        System.out.println("DiagnosticDemo started");
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac DiagnosticDemo.java
java DiagnosticDemo
~~~

Stdout:

~~~text
DiagnosticDemo started
~~~

Chương trình giữ tiến trình chạy để có thời gian quan sát. Mở terminal khác, tìm PID bằng **jps -lv**, rồi chạy **jcmd <pid> Thread.print -l**. Trong dump, thread **diagnostic-worker** thường ở TIMED_WAITING vì đang sleep; thread **main** chờ CountDownLatch. Đây là trạng thái có chủ đích của ví dụ, không phải deadlock.

## 5. Kiểm tra heap và object

### Xem tổng quan heap

~~~bash
jcmd <pid> GC.heap_info
~~~

Lệnh này cung cấp thông tin tổng quan về heap của JVM, tùy garbage collector và phiên bản JVM. Dùng nó để định hướng xem heap đang sử dụng bao nhiêu, sau đó kết hợp GC log hoặc JFR để hiểu xu hướng theo thời gian.

### Xem histogram theo class

~~~bash
jcmd <pid> GC.class_histogram
~~~

Histogram liệt kê số instance và tổng dung lượng theo class. Nó hữu ích để tìm class chiếm nhiều object hoặc bộ nhớ bất thường. Tùy chọn và hành vi cụ thể phụ thuộc phiên bản; lệnh này có thể gây Full GC theo mặc định nên cần cân nhắc trên production.

Có thể dùng jmap:

~~~bash
jmap -histo <pid>
jmap -histo:live <pid>
~~~

Biến thể **:live** chỉ thống kê object còn sống sau khi GC và có thể kích hoạt GC. Histogram chỉ cho biết số lượng và dung lượng theo class; nó không chỉ ra đầy đủ đường dẫn tham chiếu giữ object trong bộ nhớ.

### Thu heap dump

Heap dump là bản ghi các object và quan hệ tham chiếu trong heap tại thời điểm thu thập. Có thể dùng jcmd:

~~~bash
jcmd <pid> GC.heap_dump filename=heap-dump.hprof
~~~

Hoặc dùng jmap:

~~~bash
jmap -dump:live,format=b,file=heap-dump.hprof <pid>
~~~

Heap dump có thể rất lớn và thao tác tạo dump có thể làm JVM tạm dừng hoặc kích hoạt GC. Chỉ thu khi có đủ dung lượng đĩa và đã đánh giá tác động đến ứng dụng.

Có thể mở file HPROF bằng Eclipse Memory Analyzer (MAT) hoặc công cụ tương thích. Khi phân tích, thường bắt đầu từ:

- **Dominator Tree**: tìm object hoặc nhóm object đang giữ phần lớn heap.
- **Retained Heap**: ước lượng dung lượng sẽ được giải phóng nếu object đó không còn được giữ.
- **Path to GC Roots**: tìm chuỗi tham chiếu khiến object vẫn còn sống.
- **Histogram**: so sánh số lượng object theo class.

Một class có nhiều instance chưa đủ để kết luận memory leak. Cần kiểm tra object có còn được tham chiếu ngoài dự kiến hay không, tốc độ tăng theo thời gian và khả năng thu hồi sau GC.

Heap dump có thể chứa mật khẩu, token, dữ liệu người dùng, nội dung request hoặc dữ liệu nghiệp vụ. Hãy xem đây là dữ liệu nhạy cảm: giới hạn quyền truy cập, lưu ở nơi an toàn và tuân thủ chính sách lưu giữ của tổ chức.

## 6. Theo dõi garbage collection

### Dùng jstat

**jstat** lấy các bộ đếm thống kê của JVM theo chu kỳ. Ví dụ:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh lấy mẫu mỗi 1.000 mili giây, tổng cộng 10 lần. Các cột thường gặp:

- **S0, S1**: mức sử dụng hai Survivor space.
- **E**: mức sử dụng Eden.
- **O**: mức sử dụng Old generation.
- **M**: mức sử dụng Metaspace.
- **CCS**: mức sử dụng Compressed Class Space, nếu có.
- **YGC, YGCT**: số lần và tổng thời gian Young GC.
- **FGC, FGCT**: số lần và tổng thời gian Full GC.
- **GCT**: tổng thời gian GC được ghi nhận.

Có thể xem thêm dung lượng và mức sử dụng theo đơn vị của các vùng heap:

~~~bash
jstat -gc <pid> 1000 10
~~~

Tên cột và ý nghĩa chi tiết có thể khác theo collector và phiên bản. Không nên kết luận chỉ từ một mẫu. Hãy quan sát xu hướng: Old generation có tăng liên tục không, GC có diễn ra dày hơn không, và dung lượng sau GC có trở về mức ổn định không.

### Bật unified logging cho GC

Java 9 trở lên dùng unified logging. Có thể bật khi khởi chạy ứng dụng:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Log giúp xem thời điểm GC, loại sự kiện, thời gian pause và thay đổi dung lượng heap. Cần cấu hình xoay vòng log trong môi trường chạy lâu dài để tránh file tăng không giới hạn.

Nếu ứng dụng đã chạy mà chưa bật GC log, có thể dùng jstat hoặc JFR để thu thập một phần dữ liệu runtime. Không phải mọi thông tin lịch sử đều có thể khôi phục sau khi sự kiện đã xảy ra.

## 7. Java Flight Recorder (JFR)

JFR ghi lại sự kiện của JVM và ứng dụng như CPU sampling, allocation, GC, lock contention, thread park và một số sự kiện I/O. Đây là công cụ mạnh để tìm nguyên nhân hiệu năng vì nó cung cấp dữ liệu theo dòng thời gian, thay vì chỉ một snapshot.

### Bắt đầu recording bằng jcmd

~~~bash
jcmd <pid> JFR.start name=diagnostic settings=profile duration=60s filename=diagnostic.jfr
~~~

Lệnh trên yêu cầu recording trong 60 giây và ghi kết quả ra file khi hoàn tất. Profile setting thu thập nhiều chi tiết hơn cấu hình default và có thể tạo thêm overhead; hãy chọn thời lượng phù hợp với tình huống.

Kiểm tra recording đang chạy:

~~~bash
jcmd <pid> JFR.check
~~~

Nếu recording được bắt đầu mà chưa đặt thời lượng hoặc tên file, có thể dump dữ liệu rồi dừng recording:

~~~bash
jcmd <pid> JFR.dump name=diagnostic filename=diagnostic.jfr
jcmd <pid> JFR.stop name=diagnostic
~~~

Tên recording phải khớp với recording đã tạo. Xem **jcmd <pid> help JFR.start**, **JFR.dump** và **JFR.stop** nếu cú pháp khác trên bản JDK đang dùng.

### Đọc file JFR

JDK cung cấp lệnh **jfr** để tóm tắt hoặc in sự kiện:

~~~bash
jfr summary diagnostic.jfr
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostic.jfr
~~~

Có thể mở file bằng Java Mission Control (JMC) để xem timeline, CPU hot methods, allocation, GC pause và lock contention. JMC được phân phối riêng ở nhiều môi trường; không nên giả định nó có sẵn trong mọi bản cài JDK.

JFR thường có overhead thấp khi cấu hình phù hợp, nhưng không phải bằng không. Với sự cố ngắn, hãy ghi trong khoảng thời gian tái hiện được vấn đề và đối chiếu timestamp với log ứng dụng.

## 8. Kiểm tra bộ nhớ native bằng Native Memory Tracking

Heap không phải toàn bộ bộ nhớ của một tiến trình Java. RSS của process còn bao gồm Metaspace, code cache, thread stack, direct buffer, thư viện native và cấu trúc nội bộ của JVM.

**Native Memory Tracking (NMT)** theo dõi một phần phân bổ bộ nhớ native của HotSpot. NMT phải được bật khi JVM khởi chạy:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Có thể chọn **detail** để thu thập chi tiết hơn, đổi lại chi phí theo dõi cao hơn. Sau khi JVM đã chạy với NMT, dùng jcmd:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

- **summary**: xem mức phân bổ theo nhóm.
- **baseline**: đặt mốc để so sánh.
- **summary.diff**: xem thay đổi so với baseline.

NMT không theo dõi mọi vùng native memory do thư viện bên thứ ba hoặc mã native tùy ý cấp phát. Nếu RSS tăng nhưng NMT không giải thích được, cần kết hợp công cụ hệ điều hành, profiler native và kiểm tra direct buffer hoặc thư viện JNI.

## 9. Serviceability Agent và jhsdb

**jhsdb** là bộ công cụ Serviceability Agent, dùng để kiểm tra sâu trạng thái JVM hoặc core dump. Ví dụ:

~~~bash
jhsdb jstack --pid <pid>
jhsdb jmap --heap --pid <pid>
jhsdb jmap --histo --pid <pid>
~~~

Có thể mở giao diện dòng lệnh của Serviceability Agent:

~~~bash
jhsdb clhsdb --pid <pid>
~~~

Đây là nhóm công cụ chuyên sâu, thường chỉ dùng khi các lệnh thông thường chưa đủ. Việc attach Serviceability Agent vào tiến trình sống có thể làm tiến trình bị dừng trong lúc phân tích và có rủi ro ảnh hưởng dịch vụ. Ưu tiên thử trên môi trường tái hiện hoặc phân tích core dump khi quy trình vận hành cho phép. Dùng đúng quyền và JDK tương thích với JVM đích.

## 10. Công cụ giao diện: JConsole và VisualVM

### JConsole

**jconsole** là công cụ giao diện đi kèm JDK. Nó kết nối đến JVM thông qua JMX và hiển thị:

- Heap và các vùng bộ nhớ.
- Số lượng thread và thread dump.
- Hoạt động GC.
- MBean và các thuộc tính runtime.

Khởi chạy bằng:

~~~bash
jconsole
~~~

JConsole phù hợp để quan sát nhanh xu hướng và kiểm tra MBean. Nó không thay thế heap dump hoặc JFR khi cần phân tích sâu.

### VisualVM

VisualVM hỗ trợ quan sát process, thread, heap, sampler và profiler. VisualVM được phân phối riêng ở các bản JDK hiện đại; cài đặt và phiên bản phù hợp tùy môi trường.

Cả JConsole và VisualVM có thể kết nối từ xa qua JMX nếu JVM được cấu hình. Remote JMX cần xác thực và mã hóa phù hợp; không mở cổng quản trị không xác thực ra mạng công cộng.

## 11. Quy trình chẩn đoán theo triệu chứng

### Ứng dụng dùng CPU cao

1. Xác định đúng PID bằng **jps -lv**.
2. Thu vài thread dump bằng **jcmd <pid> Thread.print -l**, cách nhau vài giây.
3. Tìm thread RUNNABLE có stack lặp lại hoặc liên tục xuất hiện trong cùng đoạn xử lý.
4. Dùng JFR với profile setting trong một khoảng thời gian ngắn để tìm method tiêu thụ CPU.
5. Đối chiếu với công cụ hệ điều hành như top, pidstat hoặc Process Explorer để biết thread/process nào dùng CPU.

Thread RUNNABLE trong dump không tự chứng minh đó là thread gây tải. Hãy kết hợp thread dump, JFR và số liệu CPU.

### Heap tăng liên tục hoặc nghi memory leak

1. Kiểm tra xu hướng bằng **jstat -gcutil <pid> 1000 10**.
2. Thu histogram ở các thời điểm cách nhau và so sánh số lượng object.
3. Nếu cần xác định object nào đang được giữ, thu heap dump.
4. Dùng MAT xem Dominator Tree, Retained Heap và Path to GC Roots.
5. Xác nhận object tăng có thực sự không được giải phóng sau GC và có tham chiếu sống ngoài dự kiến.

Tăng heap trong một giai đoạn tải cao có thể là hành vi bình thường. Dấu hiệu đáng quan tâm là mức sử dụng sau GC tăng dần qua nhiều chu kỳ và không ổn định trở lại.

### GC pause dài hoặc xảy ra quá thường xuyên

1. Dùng jstat để quan sát tần suất và thời gian GC.
2. Đọc GC log nếu ứng dụng đã bật unified logging.
3. Thu JFR để liên hệ GC với allocation, CPU và lock contention.
4. Kiểm tra kích thước heap, tốc độ cấp phát, loại collector và workload.
5. Đánh giá pause cùng latency thực tế của ứng dụng; tổng thời gian GC không cho biết đầy đủ ảnh hưởng đến người dùng.

### Ứng dụng treo hoặc request bị kẹt

1. Thu ít nhất ba thread dump theo thời gian.
2. Tìm deadlock, lock contention và thread pool cạn worker.
3. Kiểm tra thread chờ I/O, database, network hoặc future/promise.
4. Đối chiếu stack trace với request log và timeout.
5. Xác định thread giữ lock và chuỗi công việc khiến lock không được giải phóng.

### RSS tăng nhưng heap không tăng tương ứng

1. So sánh heap với RSS của process.
2. Nếu NMT đã bật từ lúc khởi chạy, dùng **VM.native_memory summary** và **summary.diff**.
3. Kiểm tra số lượng thread, stack, Metaspace, code cache và direct buffer.
4. Nếu NMT không giải thích được mức tăng, kiểm tra thư viện native, JNI và công cụ quan sát của hệ điều hành.

## 12. Chọn công cụ theo mức độ tác động

| Công cụ / thao tác | Mục đích | Lưu ý vận hành |
|---|---|---|
| jps, VM.version, VM.flags | Nhận diện tiến trình và cấu hình | Thường là bước đầu ít tác động |
| Thread.print, jstack | Chụp stack của thread | Dump có thể lớn; nên lấy nhiều snapshot khi điều tra treo |
| jstat | Theo dõi bộ đếm GC | Dữ liệu dạng mẫu, cần xem xu hướng |
| JFR | Ghi sự kiện runtime | Chọn setting và thời lượng phù hợp |
| GC.class_histogram | Thống kê object theo class | Có thể kích hoạt Full GC tùy phiên bản/lựa chọn |
| GC.heap_dump, jmap dump | Ghi toàn bộ heap | Có thể tốn nhiều dung lượng và gây pause đáng kể |
| jhsdb | Phân tích JVM sâu | Có thể dừng tiến trình; chỉ dùng khi cần thiết |

## 13. Checklist khi thực hiện một lượt chẩn đoán

- Ghi lại thời điểm, timezone, PID, hostname/container và phiên bản JDK.
- Ghi rõ triệu chứng: CPU cao, heap tăng, GC pause, deadlock hay request timeout.
- Bắt đầu với lệnh ít tác động; chỉ thu heap dump hoặc dùng jhsdb khi có lý do cụ thể.
- Lưu command line và cấu hình JVM cần thiết, đồng thời che secret trước khi chia sẻ.
- Đặt tên file theo dịch vụ và thời điểm để tránh ghi đè dữ liệu giữa các lần thu thập.
- Đối chiếu dữ liệu JVM với log ứng dụng, metric và số liệu hệ điều hành.
- Ghi lại lệnh đã chạy, thời lượng thu thập và tác động quan sát được.
- Giới hạn quyền truy cập và thời gian lưu giữ thread dump, JFR, heap dump vì chúng có thể chứa dữ liệu nhạy cảm.

## 14. Ghi nhớ

- **jcmd** là điểm bắt đầu đa dụng để hỏi JVM và chạy nhiều lệnh chẩn đoán.
- **Thread dump** trả lời thread đang làm gì tại một thời điểm; nhiều snapshot giúp nhận ra tiến triển hay bế tắc.
- **Histogram** cho biết class nào có nhiều object; **heap dump** cho phép lần theo tham chiếu và GC roots.
- **jstat** và GC log cho thấy xu hướng GC; **JFR** kết nối các sự kiện runtime theo thời gian.
- Bộ nhớ process lớn hơn Java heap; dùng **NMT** và công cụ hệ điều hành khi điều tra native memory.
- Mọi kết luận cần dựa trên nhiều nguồn bằng chứng và cân nhắc chi phí của thao tác thu thập.