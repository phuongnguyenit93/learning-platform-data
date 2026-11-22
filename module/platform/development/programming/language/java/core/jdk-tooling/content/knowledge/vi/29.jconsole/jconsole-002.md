# Kết nối local JVM bằng JConsole

`JConsole` (Java Monitoring and Management Console) là công cụ giao diện đồ họa đi kèm JDK, dùng để theo dõi và quản lý một Java Virtual Machine (JVM) thông qua Java Management Extensions (JMX). Khi kết nối local, JConsole chạy trên cùng máy với ứng dụng và gắn vào JVM đích bằng cơ chế Attach API của nền tảng Java.

Kết nối local hữu ích khi phát triển, kiểm tra một ứng dụng đang chạy hoặc điều tra nhanh CPU, heap, thread, class loading và các MBean. Cách nhanh nhất là chạy `jconsole` để chọn một JVM trong danh sách Local Process, hoặc chạy `jconsole <pid>` để kết nối thẳng tới process có PID đã biết.

Trên các JDK hiện đại, local monitoring có thể tự bật management agent khi JConsole attach vào JVM hỗ trợ Attach API. Vì vậy, thông thường không cần mở cổng JMX remote hay thêm `-Dcom.sun.management.jmxremote.port` chỉ để kết nối local. JConsole và JVM đích phải chạy dưới cùng tài khoản hệ điều hành.

## 1. JConsole và local JVM connection

JConsole là một JMX client. Nó đọc các thông tin quản trị mà JVM và ứng dụng công bố qua MBean server.

Với local connection, JConsole sử dụng cơ chế attach của hệ điều hành/JVM để kết nối đến process trên cùng máy. Sau khi kết nối, JConsole có thể tải management agent vào JVM nếu target hỗ trợ dynamic attach và agent chưa được bật.

Luồng kết nối cơ bản:

1. Khởi chạy ứng dụng Java trên máy hiện tại.
2. Xác định PID của JVM đích.
3. Khởi chạy JConsole bằng cùng user đã chạy ứng dụng.
4. Chọn JVM trong danh sách Local Process hoặc truyền PID trực tiếp.
5. Nhấn Connect và chờ JConsole đọc thông tin JMX.
6. Dùng các tab để quan sát memory, threads, classes, VM và MBeans.

Kết nối local không giống remote JMX. Local connection không yêu cầu host/port remote. Remote connection cần JMX agent được cấu hình lắng nghe trên cổng và phải thiết lập bảo mật phù hợp.

## 2. Chuẩn bị JDK và kiểm tra jconsole

Executable `jconsole` nằm trong thư mục `bin` của JDK:

```text
<JDK_HOME>/bin/jconsole
```

Trên Windows:

```powershell
& "$env:JAVA_HOME\bin\jconsole.exe" -version
```

Trên Linux/macOS:

```sh
"$JAVA_HOME/bin/jconsole" -version
```

Nếu thư mục `JAVA_HOME/bin` đã nằm trong PATH, có thể chạy trực tiếp:

```sh
jconsole -version
```

Kiểm tra trợ giúp:

```sh
jconsole -help
```

Nên dùng JConsole từ một JDK phù hợp với JVM cần kiểm tra. Một số công cụ chẩn đoán của JDK có giới hạn tương thích khi dùng tool từ một bản JDK khác để attach vào runtime đích.

Nếu lệnh không được tìm thấy, kiểm tra:

- Đã cài JDK hay chỉ có runtime tối giản.
- `JAVA_HOME` có trỏ đến thư mục JDK đúng không.
- `PATH` có chứa `JAVA_HOME/bin` không.
- Có nhiều JDK trên máy và terminal đang gọi nhầm bản hay không.

JConsole là ứng dụng đồ họa. Trên Windows, chạy lệnh không nhất thiết tạo một cửa sổ console riêng; cửa sổ JConsole sẽ xuất hiện nếu khởi chạy thành công.

## 3. Xác định PID của JVM đích

Có thể dùng `jps` để liệt kê các Java process:

```sh
jps -l
```

Ví dụ:

```text
24680 com.example.OrderService
25120 com.example.LocalJConsoleDemo
25210 jdk.jconsole/sun.tools.jconsole.JConsole
```

PID ở ví dụ chỉ để minh họa. Hãy xác định đúng ứng dụng qua tên main class, JAR hoặc command line trước khi kết nối.

Các cách khác để tìm PID:

**Linux/macOS**

```sh
ps -ef
```

Có thể lọc theo tên ứng dụng:

```sh
ps -ef | grep '[j]ava'
```

**Windows PowerShell**

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

Hoặc mở Task Manager, vào tab Details và tìm process `java.exe` hoặc `javaw.exe`; bật cột PID nếu chưa hiển thị.

PID mà JConsole nhận là process ID của hệ điều hành. Với container, PID trên host có thể khác PID bên trong container. Hãy chạy JConsole trong cùng môi trường/namespace có thể nhìn thấy JVM hoặc dùng đúng PID mà môi trường đó cung cấp.

## 4. Kết nối bằng giao diện Local Process

Khởi chạy JConsole không truyền tham số:

```sh
jconsole
```

Cửa sổ New Connection xuất hiện. Khu vực Local Process liệt kê các JVM cục bộ mà user hiện tại có thể nhìn thấy và kết nối. Danh sách thường hiển thị tên ứng dụng hoặc class cùng PID.

Thực hiện:

1. Tìm dòng có tên ứng dụng cần kiểm tra.
2. Đối chiếu PID để tránh chọn nhầm process.
3. Chọn dòng ứng dụng.
4. Nhấn Connect.
5. Nếu xuất hiện hộp thoại xác nhận kết nối hoặc thông báo management agent sẽ được bật khi attach, đọc kỹ thông tin rồi tiếp tục theo môi trường của bạn.
6. Chờ các tab và biểu đồ tải dữ liệu.

Danh sách Local Process thường chỉ liệt kê JVM được khởi chạy bởi cùng user ID với JConsole. Nếu ứng dụng chạy bằng service account khác, process có thể không xuất hiện hoặc không thể kết nối.

Nếu JVM hỗ trợ Attach API nhưng management agent chưa bật, JConsole có thể tự bật agent khi kết nối. Một số phiên bản hiển thị ghi chú rằng management agent sẽ được enable lúc kết nối.

Nếu process không hỗ trợ attach và management agent cũng chưa được bật, dòng ứng dụng có thể bị làm mờ hoặc nút Connect không khả dụng.

## 5. Kết nối trực tiếp bằng PID

Nếu đã biết PID, có thể mở JConsole và kết nối ngay đến process:

```sh
jconsole 24680
```

Thay `24680` bằng PID thực tế. Cách này bỏ qua bước chọn process trong danh sách và hữu ích khi máy chạy nhiều JVM.

Có thể truyền thêm tùy chọn cập nhật biểu đồ:

```sh
jconsole -interval=2 24680
```

`-interval=2` đặt chu kỳ cập nhật biểu đồ là 2 giây. Mặc định của JConsole là 4 giây.

Một số tùy chọn thường gặp:

| Tùy chọn | Tác dụng |
|---|---|
| `-interval=n` | Đặt chu kỳ cập nhật biểu đồ, tính bằng giây |
| `-notile` | Không tự xếp cửa sổ khi kết nối nhiều JVM |
| `-version` | In phiên bản JConsole |
| `-help` | Hiển thị trợ giúp |
| `-J<flag>` | Truyền tham số cho JVM chạy chính JConsole |

Tùy chọn `-J` tác động đến JVM chạy công cụ JConsole, không phải JVM ứng dụng được giám sát. Ví dụ `jconsole -J-Xmx512m 24680` đặt heap tối đa cho process JConsole.

## 6. Điều kiện để local attach hoạt động

Để kết nối local thành công, hãy kiểm tra các điều kiện sau:

- JConsole và JVM đích chạy trên cùng máy.
- Cả hai chạy dưới cùng user hệ điều hành.
- JVM đích hỗ trợ Attach API/dynamic attach hoặc management agent đã được bật.
- Cơ chế attach không bị vô hiệu hóa.
- Process còn chạy và PID chính xác.
- Hệ điều hành cho phép user truy cập file/socket dùng trong attach.
- Với container, JConsole chạy trong namespace có thể nhìn thấy process đích.

JVM có thể vô hiệu hóa attach bằng tùy chọn:

```sh
-XX:+DisableAttachMechanism
```

Nếu ứng dụng được khởi chạy với tùy chọn này, các công cụ dựa trên attach như JConsole, `jcmd` hoặc `jstack` có thể không kết nối được theo cách local attach thông thường.

Trên JDK hiện đại, ứng dụng Java HotSpot thường không cần thêm property remote JMX để local monitoring. JMX remote port chỉ cần khi client kết nối từ một máy khác hoặc qua một remote JMX endpoint.

Trên Windows, local monitoring yêu cầu thư mục temporary mặc định nằm trên filesystem hỗ trợ quyền truy cập file/directory phù hợp, chẳng hạn NTFS. Filesystem FAT không cung cấp cơ chế permission cần thiết cho local monitoring.

## 7. Management agent được bật khi nào?

Có hai tình huống phổ biến.

**Agent đã bật từ lúc khởi động**

Ứng dụng có thể được khởi chạy với các management properties, ví dụ:

```sh
java -Dcom.sun.management.jmxremote -jar app.jar
```

Hoặc cấu hình remote agent với cổng JMX:

```sh
java -Dcom.sun.management.jmxremote.port=7091 -jar app.jar
```

Property có cổng chủ yếu phục vụ remote JMX connection. Không cần cấu hình cổng này chỉ để JConsole kết nối local vào một JVM có thể attach.

**Agent được bật động khi JConsole kết nối**

Với JVM hỗ trợ Attach API, JConsole có thể tải management agent trong lúc ứng dụng đang chạy. Ứng dụng không cần khởi động lại chỉ để bật local monitoring trong trường hợp này.

Nếu agent không thể tải động, hãy kiểm tra attach mechanism, user, runtime và cách JVM được khởi chạy. Nếu JVM không hỗ trợ attach, có thể cần bật management agent từ đầu lần khởi chạy tiếp theo.

## 8. Hiểu sáu tab sau khi kết nối

Sau khi kết nối thành công, JConsole hiển thị các khu vực giám sát chính:

| Tab | Nội dung |
|---|---|
| Overview | Tổng quan CPU, memory, thread và class loading |
| Memory | Heap, non-heap, memory pools và GC |
| Threads | Danh sách thread, trạng thái, stack trace và deadlock |
| Classes | Số class được load/unload |
| VM | Thông tin JVM, uptime, arguments, classpath và hệ điều hành |
| MBeans | Các platform MXBeans và MBean do ứng dụng đăng ký |

Có thể mở nhiều kết nối bằng menu Connection → New Connection. JConsole giữ một cửa sổ/kết nối riêng cho mỗi JVM được giám sát.

## 9. Overview: xem nhanh tình trạng JVM

Tab Overview gom các biểu đồ chính trên một màn hình:

- Heap memory usage.
- Number of threads.
- Number of loaded classes.
- CPU usage của JVM.

Dùng Overview để nhận diện xu hướng tổng quan. Ví dụ:

- Heap tăng liên tục trong khi tải không đổi: cần kiểm tra object retention hoặc cache.
- Thread count tăng không giảm: kiểm tra thread leak hoặc task bị mắc kẹt.
- CPU tăng cao kéo dài: chuyển sang profiler/JFR để tìm method tiêu thụ CPU.
- Class count tăng liên tục: kiểm tra dynamic class generation hoặc classloader lifecycle.

Biểu đồ là dữ liệu lấy mẫu theo chu kỳ cập nhật. Một đỉnh ngắn có thể bị bỏ qua nếu khoảng lấy mẫu quá dài; một thay đổi trong biểu đồ cũng không tự chứng minh nguyên nhân gốc.

Có thể lưu dữ liệu biểu đồ thành CSV bằng cách nhấn chuột phải vào biểu đồ và chọn Save data as..., sau đó mở file bằng công cụ bảng tính để so sánh.

## 10. Memory: đọc heap và non-heap

Tab Memory hiển thị mức sử dụng bộ nhớ của JVM và từng memory pool. Có thể chuyển giữa heap và non-heap hoặc chọn pool cụ thể tùy runtime.

Các chỉ số thường gặp:

| Chỉ số | Ý nghĩa |
|---|---|
| Used | Dung lượng hiện đang được sử dụng |
| Committed | Dung lượng JVM đã cam kết có thể sử dụng |
| Max | Mức tối đa được phép sử dụng; có thể không xác định hoặc thay đổi tùy pool |
| GC time | Tổng thời gian dành cho garbage collection và số lần collection |

Thông thường:

\[
Used \le Committed \le Max
\]

Khi Max không xác định, không nên dùng công thức này như một phép kiểm tra bắt buộc cho mọi pool. Ý nghĩa và giới hạn phụ thuộc memory manager và JVM implementation.

**Heap memory** chứa phần lớn object instance và array được cấp phát trong Java. **Non-heap memory** chứa class metadata, runtime structures và JIT code cache cùng các vùng nội bộ khác.

Tên memory pool phụ thuộc garbage collector và JDK. Ví dụ có thể gặp Eden, Survivor, Old/Tenured, Metaspace, Compressed Class Space và Code Cache. Không áp dụng tên Permanent Generation từ tài liệu Java cũ cho JDK hiện đại; PermGen đã được thay bằng Metaspace từ Java 8.

Nút `Perform GC` yêu cầu JVM thực hiện garbage collection. Đây là thao tác chủ động, có thể gây pause và không đảm bảo mọi object không còn dùng sẽ được thu hồi ngay lập tức. Chỉ dùng khi có mục đích kiểm tra rõ ràng, đặc biệt trên môi trường production.

## 11. Threads: kiểm tra thread và deadlock

Tab Threads cho biết:

- Danh sách thread đang hoạt động.
- Tên và trạng thái thread.
- Stack trace của thread được chọn.
- Số lượng live thread theo thời gian.
- Số thread cao nhất đã ghi nhận.

Có thể nhập một phần tên vào Filter để lọc danh sách. Chọn thread để xem trạng thái và stack trace của nó.

Một số trạng thái thường gặp:

| Trạng thái | Ý nghĩa |
|---|---|
| RUNNABLE | Đang chạy hoặc sẵn sàng chạy trong JVM |
| BLOCKED | Đang chờ lấy intrinsic monitor |
| WAITING | Chờ vô thời hạn một điều kiện/tín hiệu |
| TIMED_WAITING | Chờ trong khoảng thời gian giới hạn |
| TERMINATED | Thread đã kết thúc |

Không kết luận thread bị treo chỉ từ trạng thái WAITING hoặc TIMED_WAITING. Worker thread nhàn rỗi trong thread pool thường chờ công việc theo cách này.

Nút Detect Deadlock yêu cầu JVM kiểm tra chu trình deadlock. Nếu phát hiện, JConsole hiển thị thông tin thread liên quan ở tab bổ sung. Cơ chế kiểm tra có thể phát hiện deadlock liên quan intrinsic monitor và ownable synchronizer mà JVM hỗ trợ.

Nếu nghi ngờ lock contention nhưng không có deadlock, hãy xem stack trace, thread state và thread owner. Có thể dùng `jcmd <pid> Thread.print -l` để lưu thread dump phục vụ phân tích sâu.

## 12. Classes: theo dõi class loading

Tab Classes hiển thị số lượng class đã load theo thời gian.

Các giá trị cần phân biệt:

- Total loaded: tổng số class từng được load kể từ khi JVM khởi động, kể cả class sau đó đã unload.
- Currently loaded: số class đang được load hiện tại.
- Unloaded: số class đã được unload.

Nếu total loaded tăng nhưng currently loaded ổn định, JVM có thể đang load và unload class theo workload. Nếu currently loaded tăng liên tục, kiểm tra framework sinh class động, proxy, plugin, classloader và quy trình redeploy.

Có thể bật verbose class loading từ giao diện để quan sát thêm log class loading. Việc bật log có thể tạo nhiều output, nên chỉ bật trong khoảng thời gian điều tra cần thiết.

## 13. VM: xem thông tin của process

Tab VM/VM Summary cung cấp thông tin về JVM đang được kết nối, thường gồm:

- Uptime: thời gian JVM đã chạy.
- Process CPU Time: tổng CPU time của process.
- Total Compile Time: thời gian tích lũy cho JIT compilation.
- Live, peak và daemon thread counts.
- Số class hiện tại, tổng số class đã load và unload.
- Heap size, committed memory và maximum heap size.
- Thông tin garbage collector.
- VM arguments, classpath và library path.
- Thông tin hệ điều hành/runtime tùy JDK.

VM arguments là các tham số truyền cho JVM, ví dụ `-Xmx` hoặc `-Dname=value`; chúng không bao gồm các đối số truyền vào `main(String[] args)`.

Tab này hữu ích để xác nhận ứng dụng đang chạy bằng runtime và cấu hình nào. Nếu cần xem chi tiết hơn, có thể dùng:

```sh
jcmd 24680 VM.command_line
jcmd 24680 VM.flags
jcmd 24680 VM.system_properties
```

Thay PID bằng process thực tế. Các command cụ thể cần được target JVM hỗ trợ.

## 14. MBeans: xem dữ liệu và thao tác quản trị

MBeans tab hiển thị các MBean đã đăng ký trong platform MBean server. Có thể xem:

- Object name và thông tin mô tả MBean.
- Attributes: các giá trị mà MBean công bố.
- Operations: các thao tác có thể gọi.
- Notifications: thông báo mà MBean phát ra.

Một số platform MXBean thường dùng:

| MBean | Thông tin |
|---|---|
| `java.lang:type=Memory` | Heap/non-heap memory usage |
| `java.lang:type=Threading` | Thread count, thread info và deadlock operations |
| `java.lang:type=ClassLoading` | Số class load/unload |
| `java.lang:type=GarbageCollector,name=...` | GC count và collection time |
| `java.lang:type=Runtime` | Uptime, VM name và input arguments |
| `java.lang:type=OperatingSystem` | Thông tin hệ điều hành và process |

MBeans tab có thể hiển thị cả MBean tùy chỉnh do ứng dụng đăng ký. Đây là cách kiểm tra các metric nghiệp vụ hoặc trạng thái nội bộ nếu ứng dụng đã triển khai custom MBean.

Một số attribute có thể ghi được và một số operation có thể thay đổi trạng thái ứng dụng. Không nhấn operation hoặc sửa writable attribute nếu chưa hiểu tác dụng. Ví dụ thay đổi cấu hình GC logging hoặc gọi operation quản trị có thể ảnh hưởng process đang chạy.

## 15. Ví dụ Java 17+: tạo JVM để kết nối local

Ví dụ sau tạo một JVM có allocation workload nhẹ và một worker thread để bạn quan sát Memory và Threads trong JConsole.

Tạo file `LocalJConsoleDemo.java`:

```java
public class LocalJConsoleDemo {
    private static volatile byte[] lastBuffer;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1_000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "jconsole-demo-worker");

        worker.setDaemon(true);
        worker.start();

        System.out.println("READY");

        while (true) {
            byte[] buffer = new byte[128 * 1024];
            buffer[0] = 1;
            lastBuffer = buffer;
            Thread.sleep(250);
        }
    }
}
```

Biên dịch:

```sh
javac LocalJConsoleDemo.java
```

Chạy:

```sh
java -Xms64m -Xmx256m LocalJConsoleDemo
```

Stdout chính xác:

```text
READY
```

Chương trình tiếp tục chạy sau khi in READY. Vòng lặp cấp phát một byte array nhỏ theo chu kỳ để biểu đồ memory có hoạt động; worker thread ngủ định kỳ để bạn có thể tìm nó trong tab Threads.

Mở terminal thứ hai và tìm PID:

```sh
jps -l
```

Ví dụ:

```text
24680 LocalJConsoleDemo
```

Kết nối trực tiếp:

```sh
jconsole 24680
```

Hoặc chạy `jconsole` không tham số, tìm `LocalJConsoleDemo` trong Local Process và nhấn Connect. Sau khi kết nối, thử xem Overview, Memory, Threads, Classes và VM.

PID 24680 chỉ là ví dụ. Dùng PID mà `jps` hiển thị trên máy thực tế. Sau khi hoàn thành, đóng cửa sổ JConsole hoặc chọn Disconnect, rồi quay lại terminal chạy demo và nhấn Ctrl+C để dừng ứng dụng.

## 16. Cách điều tra nhanh theo triệu chứng

| Triệu chứng | Tab nên xem trước | Bước tiếp theo |
|---|---|---|
| Heap tăng liên tục | Memory | So sánh live set, histogram và heap dump |
| CPU cao | Overview, VM | Dùng JFR hoặc profiler để tìm method nóng |
| Thread count tăng bất thường | Threads, Overview | Tìm nguồn tạo thread và thread không kết thúc |
| Ứng dụng có vẻ bị treo | Threads | Kiểm tra stack, lock và Detect Deadlock |
| Class count tăng mãi | Classes, Memory | Kiểm tra classloader, proxy và redeploy |
| Metaspace tăng | Memory, Classes, MBeans | Kiểm tra class loading và classloader lifecycle |
| GC tốn nhiều thời gian | Memory, MBeans | Đối chiếu GC logs và JFR |
| Cần xem cấu hình runtime | VM | Kiểm tra VM arguments, classpath và system properties |

JConsole giúp khoanh vùng triệu chứng. Để xác định nguyên nhân gốc, thường cần thêm thread dump, heap dump, GC log hoặc JFR recording.

## 17. Lỗi thường gặp khi kết nối local JVM

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jconsole: command not found` | JDK/bin không nằm trong PATH hoặc chưa cài JDK đầy đủ | Kiểm tra JAVA_HOME và chạy executable bằng đường dẫn đầy đủ |
| Không thấy JVM trong Local Process | JVM chạy dưới user khác, container namespace khác hoặc process không được quan sát | Chạy JConsole bằng đúng user và trong đúng môi trường |
| Process xuất hiện nhưng bị làm mờ | JVM không attach được và management agent chưa bật | Kiểm tra target runtime, Attach API và cách khởi chạy |
| Connect bị từ chối | Sai PID, quyền hệ điều hành hoặc attach bị vô hiệu hóa | Xác minh PID, user và JVM flags |
| `AttachNotSupportedException` | Runtime không hỗ trợ attach, attach bị chặn hoặc process không ở cùng namespace | Kiểm tra JDK/VM, namespace và attach configuration |
| JConsole không kết nối được sau khi đổi user | Local attach dùng quyền filesystem của hệ điều hành | Chạy JConsole bằng cùng user với JVM |
| Không kết nối được trên Windows | Temporary directory nằm trên filesystem không hỗ trợ permission cần thiết | Kiểm tra default temp directory; dùng filesystem hỗ trợ ACL như NTFS |
| JConsole hiển thị dữ liệu chậm | Chu kỳ cập nhật, tải JVM hoặc số lượng MBean lớn | Điều chỉnh interval và giới hạn thao tác truy vấn |
| Không thấy tab/dữ liệu tùy chỉnh | Ứng dụng chưa đăng ký MBean hoặc runtime không cung cấp metric tương ứng | Kiểm tra MBean server và instrumentation của ứng dụng |
| JConsole làm ứng dụng chậm hơn | Công cụ tiêu thụ tài nguyên và truy vấn dữ liệu định kỳ | Giảm tần suất, giới hạn thời gian quan sát và dùng công cụ phù hợp hơn |
| Đã bật remote JMX nhưng local list vẫn trống | Remote JMX và local attach là hai đường kết nối khác nhau | Xác định đúng host/port hoặc kiểm tra local attach riêng |

Nếu attach thất bại, không vội bật cổng JMX remote hoặc tắt bảo mật. Trước hết xác định đây là lỗi PID, user, attach mechanism, namespace hay management agent.

## 18. Hiệu năng và bảo mật khi dùng local JConsole

JConsole tự tiêu thụ CPU, memory và tạo các truy vấn quản trị. Khi chạy trên cùng máy với ứng dụng, tài nguyên của JConsole có thể ảnh hưởng đến số liệu quan sát và hiệu năng target process.

Nguyên tắc sử dụng:

- Dùng local JConsole chủ yếu cho development, test và prototype.
- Không mở nhiều biểu đồ hoặc MBean truy vấn nặng nếu không cần.
- Không đặt interval quá ngắn trong thời gian dài.
- Chỉ gọi thao tác MBean khi hiểu tác dụng.
- Cẩn thận khi nhấn Perform GC vì nó yêu cầu garbage collection.
- Không chia sẻ ảnh chụp hoặc CSV chứa thông tin nội bộ ra ngoài tổ chức.
- Giữ quyền truy cập hệ điều hành và tài khoản vận hành ở mức cần thiết.

JConsole có khả năng quản lý JVM thông qua MBeans, vì vậy quyền truy cập local cần được xem là quyền quản trị đối với process đó. Chỉ cho user đáng tin cậy kết nối vào ứng dụng.

Nếu cần monitoring production liên tục, hãy dùng hệ thống metrics/JMX agent được tổ chức phê duyệt, JFR hoặc monitoring service chạy tách khỏi JVM cần giám sát. Tránh để GUI JConsole trở thành hệ thống polling thường trực trên máy chủ tải cao.

## 19. Phân biệt local JConsole và remote JMX

| Nội dung | Local connection | Remote JMX |
|---|---|---|
| Vị trí JConsole | Cùng máy với JVM | Có thể ở máy khác |
| Định danh | PID | Host và port hoặc JMX service URL |
| Cơ chế | Attach API/local management agent | JMX connector, thường dùng RMI |
| Cùng user OS | Có, cho local attach thông thường | Không yêu cầu cùng user OS; dùng cơ chế xác thực JMX |
| Cần remote port | Không | Có |
| Bảo mật | Quyền truy cập hệ điều hành/local process | Cần cấu hình authentication và TLS phù hợp |

Remote JMX không nằm trong quy trình local connection của bài này. Nếu muốn kết nối từ máy khác, cần cấu hình JMX agent trên JVM đích, chọn cổng, thiết lập authentication/TLS và giới hạn network access. Không bật remote JMX không xác thực trên mạng không tin cậy.

## 20. Checklist kết nối local JVM

- [ ] Đã cài JDK có JConsole.
- [ ] Đã kiểm tra `JAVA_HOME/bin` hoặc PATH.
- [ ] Đã xác định đúng PID bằng `jps -l` hoặc công cụ hệ điều hành.
- [ ] JConsole và JVM đích chạy trên cùng máy.
- [ ] JConsole và JVM đích chạy dưới cùng user hệ điều hành.
- [ ] Target JVM hỗ trợ Attach API hoặc management agent đã được bật.
- [ ] Attach mechanism không bị vô hiệu hóa.
- [ ] Đã chạy `jconsole` hoặc `jconsole <pid>`.
- [ ] Đã chọn đúng process trong Local Process.
- [ ] Đã xem Overview, Memory, Threads, Classes, VM và MBeans.
- [ ] Đã hiểu sự khác biệt giữa heap, non-heap, used, committed và max.
- [ ] Đã thận trọng với Perform GC và writable MBean operations.
- [ ] Đã lưu chart CSV hoặc chụp dữ liệu cần thiết nếu phục vụ điều tra.
- [ ] Đã disconnect JConsole và dừng ứng dụng demo sau thực hành.

## 21. Tài liệu tham khảo

- Oracle JDK 21 Tool Reference — The `jconsole` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html
- Oracle Java SE 21 Management Guide — Using JConsole: https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html
- Oracle Java SE 21 Management Guide — Monitoring and Management Using JMX Technology: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Oracle Java SE 21 Tool Reference — The `jps` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html

Kết nối local JVM bằng JConsole chủ yếu cần đúng PID, cùng user hệ điều hành và một JVM hỗ trợ attach hoặc đã bật management agent. Sau khi kết nối, hãy đọc các tab theo triệu chứng, dùng MBeans cẩn thận vì chúng có thể thực hiện thao tác quản trị, và kết hợp JConsole với JFR, thread dump hoặc heap dump khi cần tìm nguyên nhân sâu hơn.