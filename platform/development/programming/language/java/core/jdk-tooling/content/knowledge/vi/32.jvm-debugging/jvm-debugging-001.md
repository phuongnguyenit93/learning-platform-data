# JVM debugging: quy trình và công cụ

**JVM debugging** là quá trình tìm nguyên nhân khiến một ứng dụng Java hoạt động sai, chậm, treo, tiêu thụ tài nguyên bất thường hoặc bị crash. Việc debug có thể diễn ra ở nhiều mức: kiểm tra code bằng breakpoint, quan sát thread và memory của JVM đang chạy, phân tích sự kiện theo thời gian bằng Java Flight Recorder (JFR), hoặc điều tra crash dump sau khi process kết thúc.

Không có một lệnh duy nhất giải quyết mọi loại lỗi. Cách hiệu quả là bắt đầu từ triệu chứng, thu thập bằng chứng phù hợp và chọn công cụ ít xâm lấn nhất có thể. Với nhiều diagnostic command trên HotSpot, Oracle khuyến nghị dùng `jcmd` thay cho các công cụ cũ như `jstack`, `jmap` và `jinfo`. Để debug logic ở cấp source, dùng IDE debugger hoặc `jdb`. Để tìm xu hướng runtime, dùng JFR/JDK Mission Control (JMC), JConsole và các metric của JVM.

## 1. Xác định loại sự cố trước khi debug

Trước khi chạy công cụ, hãy mô tả rõ điều gì đang xảy ra và thời điểm bắt đầu. Một ứng dụng Java có thể gặp nhiều nhóm vấn đề khác nhau:

| Triệu chứng | Câu hỏi đầu tiên | Bằng chứng nên thu thập |
|---|---|---|
| Exception hoặc kết quả sai | Exception xuất hiện ở method nào? Input nào làm lỗi tái hiện? | Stack trace, log có request ID, input và breakpoint |
| Process treo hoặc request không trả lời | Thread đang chạy, chờ lock hay chờ I/O? | Nhiều thread dump, lock information, JFR |
| CPU cao | Thread/method nào dùng CPU? | JFR execution samples, thread dump, OS process metrics |
| Heap tăng hoặc OutOfMemoryError | Object nào đang được giữ lại? | Heap usage, class histogram, heap dump |
| GC pause hoặc GC liên tục | Allocation rate, live set và GC time thay đổi ra sao? | GC logs, JFR, jstat, JMX metrics |
| Metaspace tăng | Class nào được load và classloader nào còn sống? | Class-loading metrics, classloader statistics, heap dump |
| Crash của JVM hoặc native code | Có fatal error log hoặc core dump không? | `hs_err_pid` log, core dump, native stack và OS logs |
| Lỗi chỉ xuất hiện trong production | Môi trường, cấu hình và workload khác gì staging? | JDK/version, JVM flags, properties, environment, JFR và logs |

Một triệu chứng có thể có nhiều nguyên nhân. Ví dụ CPU cao có thể do vòng lặp vô hạn, retry quá nhanh, lock contention, GC pressure hoặc code native. Không thay đổi heap size hay GC flags trước khi có dữ liệu hỗ trợ giả thuyết.

## 2. Một quy trình debug JVM có thể lặp lại

Dùng quy trình sau để tránh thu thập quá nhiều dữ liệu không liên quan:

1. **Ghi lại bối cảnh:** JDK vendor/version, OS, container, PID, JVM arguments, thời điểm, workload và thay đổi triển khai gần nhất.
2. **Tái hiện hoặc khoanh vùng:** xác định request, input, thread hoặc thời điểm làm lỗi xuất hiện.
3. **Thu thập bằng chứng ban đầu:** application logs, exception stack trace, `jcmd -l`, uptime, JVM flags và system properties.
4. **Chọn công cụ theo triệu chứng:** `jdb` cho logic; thread dump cho hang/deadlock; JFR cho CPU/latency/GC; histogram/heap dump cho memory; crash log/core dump cho JVM/native crash.
5. **Đặt giả thuyết có thể kiểm chứng:** ví dụ cache không giới hạn, thread pool hết worker, lock bị giữ quá lâu hoặc một method cấp phát object quá nhiều.
6. **Kiểm tra bằng một phép đo phù hợp:** so sánh nhiều thread dump, recording hoặc histogram trong workload tương đương.
7. **Sửa nguyên nhân và kiểm tra lại:** chạy cùng kịch bản, xác nhận triệu chứng biến mất và không tạo regression.
8. **Lưu kết quả:** ghi lại command, timestamp, PID, JDK version, artifact và kết luận để người khác có thể lặp lại.

Không nên thay đổi nhiều tham số cùng lúc. Nếu vừa tăng heap, đổi collector, tăng thread pool và sửa cache, rất khó biết thay đổi nào đã tác động đến lỗi.

## 3. Phân biệt debug code và diagnostic JVM

Hai hoạt động này có mục đích khác nhau:

| Hoạt động | Mục tiêu | Công cụ |
|---|---|---|
| Source-level debugging | Dừng tại dòng code, xem biến, gọi stack và từng bước thực thi | IntelliJ IDEA, Eclipse, VS Code Java debugger, `jdb` |
| Runtime diagnostics | Xem trạng thái JVM đang chạy mà không cần breakpoint source | `jcmd`, `jstat`, JConsole, JFR/JMC |
| Memory analysis | Tìm class/object chiếm heap và reference giữ object | `jcmd GC.class_histogram`, heap dump, Eclipse MAT |
| Postmortem analysis | Phân tích sau khi process crash hoặc bị dừng | `hs_err_pid` log, core dump, `jhsdb`, native debugger |

Breakpoint có thể làm thread dừng và thay đổi timing của ứng dụng. Runtime diagnostics thường phù hợp hơn để quan sát production. Heap dump hoặc các lệnh heap inspection có thể tốn thời gian, bộ nhớ và I/O, nên cần đánh giá tác động trước khi chạy.

## 4. Tìm đúng JVM process

Các công cụ diagnostic cần PID hoặc VMID của JVM đích. Liệt kê Java process bằng:

```sh
jcmd -l
```

Hoặc:

```sh
jps -l
```

Ví dụ:

```text
24680 com.example.OrderService
25120 com.example.PaymentWorker
```

PID ở đây chỉ minh họa. Đối chiếu main class/JAR, command line, service name hoặc thông tin deployment để chọn đúng process.

Nếu công cụ JDK không liệt kê process, dùng công cụ hệ điều hành:

Linux/macOS:

```sh
ps -ef
```

Windows PowerShell:

```powershell
Get-Process java, javaw -ErrorAction SilentlyContinue
```

Trong container, PID trên host có thể khác PID trong PID namespace của container. Chạy công cụ trong đúng container hoặc namespace, và dùng PID mà môi trường đó nhìn thấy.

`jcmd` cần chạy trên cùng máy với JVM đích và bằng effective user/group ID phù hợp với tài khoản đã khởi chạy JVM. Nếu attach bị từ chối, kiểm tra user, namespace, quyền hệ điều hành và attach mechanism trước khi đổi công cụ.

## 5. Bắt đầu với jcmd

`jcmd` gửi diagnostic command trực tiếp đến JVM đang chạy. Các command có sẵn phụ thuộc runtime; hãy hỏi JVM đích thay vì giả định mọi phiên bản đều hỗ trợ cùng một tập lệnh.

Liệt kê command:

```sh
jcmd 24680 help
```

Xem trợ giúp của một command:

```sh
jcmd 24680 help Thread.print
```

Một số command hữu ích:

| Command | Mục đích |
|---|---|
| `VM.version` | Phiên bản JVM |
| `VM.command_line` | Command line khởi chạy JVM |
| `VM.flags` | Các JVM flags hiện tại |
| `VM.system_properties` | Java system properties |
| `VM.uptime` | Uptime của JVM |
| `Thread.print` | Thread dump và stack trace |
| `GC.heap_info` | Thông tin heap |
| `GC.class_histogram` | Histogram instance theo class |
| `GC.heap_dump` | Tạo heap dump |
| `VM.classloader_stats` | Thống kê classloader |
| `VM.native_memory summary` | Thống kê native memory nếu NMT đã được bật |
| `JFR.start` / `JFR.check` / `JFR.dump` / `JFR.stop` | Điều khiển Flight Recorder |

Ví dụ thu thập thông tin cơ bản:

```sh
jcmd 24680 VM.version
jcmd 24680 VM.uptime
jcmd 24680 VM.command_line
jcmd 24680 VM.flags
```

Có thể lưu output vào file để đính kèm incident report:

```sh
jcmd 24680 VM.flags > vm-flags.txt
jcmd 24680 VM.system_properties > system-properties.txt
```

Các file này có thể chứa đường dẫn, tên service, endpoint hoặc secret bị truyền nhầm qua `-D`. Che thông tin nhạy cảm trước khi chia sẻ.

## 6. Debug logic bằng jdb

`jdb` là debugger dòng lệnh mẫu của JDK. Nó dùng Java Debug Interface (JDI), thuộc Java Platform Debugger Architecture (JPDA), để khởi chạy hoặc kết nối đến JVM đang được debug.

Có hai cách phổ biến:

- Cho `jdb` khởi chạy chương trình: dễ dùng trong bài thực hành và môi trường local.
- Khởi chạy JVM với JDWP agent rồi attach `jdb`: hữu ích khi cần kết nối đến process đã được chuẩn bị cho debug.

Xem trợ giúp:

```sh
jdb -help
```

Liệt kê connector:

```sh
jdb -listconnectors
```

Khi dùng debugger, source và debug information giúp đặt breakpoint theo dòng, xem biến local và bước qua method. Biên dịch với `javac -g` để tạo thông tin debug đầy đủ hơn, đặc biệt là local variable tables.

## 7. Các lệnh jdb thường dùng

| Lệnh | Tác dụng |
|---|---|
| `stop in Class.method` | Breakpoint tại đầu method |
| `stop at Class:line` | Breakpoint tại dòng source |
| `clear Class:line` | Xóa breakpoint tại dòng |
| `run` | Chạy chương trình được debugger khởi chạy |
| `cont` | Tiếp tục sau khi breakpoint/exception dừng |
| `step` | Đi vào method được gọi ở dòng kế tiếp |
| `next` | Chạy dòng kế tiếp mà không đi vào method |
| `step up` | Chạy đến khi method hiện tại trả về |
| `where` | In call stack của thread hiện tại |
| `where all` | In stack của các thread |
| `locals` | Xem biến local trong stack frame hiện tại |
| `print expression` | Đánh giá và in biểu thức |
| `dump expression` | In chi tiết object/biểu thức |
| `threads` | Liệt kê thread |
| `thread id` | Chọn thread để kiểm tra |
| `catch ExceptionClass` | Dừng khi exception phù hợp được throw |
| `ignore ExceptionClass` | Bỏ chế độ dừng do `catch` đã đặt |
| `help` | Xem trợ giúp |
| `quit` | Thoát debugger |

Ví dụ đặt breakpoint tại method:

```text
stop in com.example.DebugDemo.calculateTotal
```

Breakpoint theo dòng:

```text
stop at com.example.DebugDemo:18
```

Breakpoint theo dòng phụ thuộc số dòng trong source đã biên dịch. Nếu source thay đổi, kiểm tra lại vị trí breakpoint.

Với method overload, có thể cần chỉ rõ kiểu tham số để debugger chọn đúng method. `step` và `next` giúp theo dõi luồng thực thi; `where` cho biết call stack để hiểu method được gọi từ đâu.

## 8. Ví dụ Java 17+: tìm lỗi bằng breakpoint

Ví dụ có một lỗi tính discount: chương trình định giảm 10% nhưng code lại trừ cố định 10 đơn vị.

Tạo file `src/com/example/DebugDemo.java`:

```java
package com.example;

public class DebugDemo {
    public static void main(String[] args) {
        int result = calculateTotal(3, 450);
        System.out.println("total=" + result);
    }

    static int calculateTotal(int quantity, int unitPrice) {
        int subtotal = quantity * unitPrice;
        int discount = subtotal > 1_000 ? 10 : 0;
        return subtotal - discount;
    }
}
```

Biên dịch kèm debug information:

```sh
javac -g -d out src/com/example/DebugDemo.java
```

Chạy bình thường:

```sh
java -cp out com.example.DebugDemo
```

Stdout:

```text
total=1340
```

Nếu yêu cầu là giảm 10%, kết quả mong đợi phải là 1215. Chương trình hiện trả 1340 vì `discount` bằng 10 thay vì 135.

Khởi chạy debugger:

```sh
jdb -classpath out com.example.DebugDemo
```

Tại dấu nhắc `jdb`, đặt breakpoint và chạy:

```text
stop in com.example.DebugDemo.calculateTotal
run
```

Khi debugger dừng tại method, dùng:

```text
locals
where
next
print subtotal
next
print discount
```

`locals` cho biết tham số và biến local đang có trong stack frame; `where` cho biết call stack. Sau khi đã xác nhận `subtotal` và `discount`, tiếp tục:

```text
cont
quit
```

Ứng dụng in `total=1340`. Có thể sửa công thức thành `int discount = subtotal > 1_000 ? subtotal / 10 : 0;`, biên dịch lại và chạy để nhận `total=1215`.

Các prompt và thông báo của `jdb` có thể khác nhẹ theo JDK, nhưng stdout của chương trình ở hai lần chạy được xác định bởi dữ liệu đầu vào và công thức.

## 9. Debug exception

Stack trace thường là bằng chứng đầu tiên khi ứng dụng throw exception. Đọc từ dòng exception đầu tiên, tìm frame đầu tiên thuộc code ứng dụng và lần ngược call chain.

Ví dụ:

```text
Exception in thread "main" java.lang.NullPointerException
    at com.example.OrderService.calculate(OrderService.java:42)
    at com.example.OrderService.main(OrderService.java:18)
```

Các bước:

1. Đọc exception type và message.
2. Xác định class, method và line number đầu tiên thuộc ứng dụng.
3. Kiểm tra input, state và dữ liệu tại thời điểm lỗi.
4. Tìm nơi object có thể trở thành null hoặc state bị thay đổi.
5. Tái hiện với input nhỏ nhất có thể.
6. Đặt breakpoint trước dòng lỗi và quan sát biến.
7. Thêm regression test cho tình huống đã gây lỗi.

Trong `jdb`, có thể yêu cầu debugger dừng khi exception được throw:

```text
catch java.lang.NullPointerException
```

Hoặc một exception cụ thể của ứng dụng:

```text
catch com.example.InvalidOrderException
```

Lệnh `catch` khiến debugger dừng tại điểm throw khi exception phù hợp xuất hiện. Dùng `ignore` để bỏ yêu cầu dừng đó. Không bật catch cho mọi exception trong ứng dụng lớn nếu nó làm debugger dừng liên tục và che khuất lỗi cần điều tra.

## 10. Debug process đang chạy bằng JDWP

JDWP (Java Debug Wire Protocol) cho phép debugger giao tiếp với JVM đích. Trên HotSpot, bật agent bằng tùy chọn `-agentlib:jdwp`.

Ví dụ khởi chạy ứng dụng và chờ debugger attach:

```sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.example.DebugDemo
```

Các tham số:

- `transport=dt_socket`: dùng socket TCP.
- `server=y`: JVM đích mở socket và chờ debugger kết nối.
- `suspend=y`: JVM tạm dừng lúc khởi động cho đến khi debugger attach.
- `address=127.0.0.1:5005`: lắng nghe trên loopback của máy tại port 5005.

Mở terminal thứ hai:

```sh
jdb -attach 127.0.0.1:5005
```

Sau khi attach, đặt breakpoint rồi tiếp tục chương trình:

```text
stop in com.example.DebugDemo.calculateTotal
cont
```

Nếu muốn ứng dụng bắt đầu chạy trước khi debugger kết nối, có thể dùng `suspend=n`. Khi đó, breakpoint có thể bỏ lỡ những dòng đã chạy trước khi attach. Dùng `suspend=y` khi cần bắt đầu từ đầu chương trình.

Để `jdb` khởi chạy chương trình thay vì attach thủ công, có thể dùng trực tiếp:

```sh
jdb -classpath out com.example.DebugDemo
```

Không cần thêm `-Xdebug` trên JDK hiện đại; `-agentlib:jdwp` là cách cấu hình debug agent được dùng.

## 11. Bảo vệ cổng JDWP

JDWP là giao thức điều khiển debugger có quyền rất mạnh đối với JVM đích. Người kết nối có thể xem trạng thái chương trình, dừng thread, đọc biến và điều khiển luồng thực thi. Không coi debug port như một cổng metrics thông thường.

Quy tắc an toàn:

- Chỉ bật JDWP khi thật sự cần.
- Với local debug, bind loopback như `127.0.0.1`, không dùng wildcard.
- Không công khai port debug trên Internet hoặc mạng không tin cậy.
- Nếu cần remote debug, ưu tiên SSH tunnel hoặc VPN; giới hạn firewall và nguồn kết nối.
- Tắt debug agent sau khi điều tra.
- Không bật `suspend=y` trên production nếu chưa đánh giá tác động vì ứng dụng sẽ chờ debugger và không phục vụ request.
- Không để debug port tồn tại trong cấu hình production mặc định.

Ví dụ dùng SSH tunnel khi JVM trên máy remote đã bind vào loopback của chính máy đó:

```sh
ssh -L 5005:127.0.0.1:5005 user@server.example
```

Sau khi tunnel hoạt động, debugger trên máy phát triển kết nối tới:

```sh
jdb -attach 127.0.0.1:5005
```

JDWP socket transport không phải một endpoint JMX được bảo vệ bằng username/password. SSH tunnel mã hóa kết nối và tận dụng cơ chế xác thực SSH. Nếu môi trường yêu cầu remote debugging, phối hợp với quy trình access control và firewall của tổ chức.

## 12. Điều tra process treo bằng thread dump

Khi request không trả lời, CPU không nhất thiết cao. Process có thể đang chờ lock, chờ network, chờ database hoặc deadlock.

Tạo thread dump:

```sh
jcmd 24680 Thread.print
```

Để thêm thông tin lock/synchronizer:

```sh
jcmd 24680 Thread.print -l
```

Có thể lưu vào file:

```sh
jcmd 24680 Thread.print -l > thread-01.txt
```

Với process treo kéo dài, lấy vài thread dump cách nhau vài giây, ví dụ 5–10 giây. So sánh stack của cùng thread qua các mẫu:

- Stack không thay đổi có thể cho thấy thread bị kẹt tại một điểm.
- Nhiều thread cùng chờ một lock có thể chỉ ra lock contention.
- Một nhóm thread chờ lẫn nhau có thể là deadlock.
- Thread pool có toàn bộ worker ở trạng thái chờ I/O có thể làm queue tăng.

Một thread ở `WAITING` hoặc `TIMED_WAITING` không tự động là lỗi; worker thread nhàn rỗi thường chờ công việc. Hãy đọc stack frame và trạng thái lock trước khi kết luận.

`Thread.print` có impact phụ thuộc số lượng thread. Kiểm tra `jcmd PID help Thread.print` trên target JVM và tránh lấy dump quá dày trong process nhạy cảm.

## 13. Nhận diện deadlock

Deadlock xảy ra khi các thread giữ lock mà thread khác cần, tạo thành chu trình chờ không thể tự giải quyết.

Ví dụ logic:

- Thread A giữ Lock 1 và chờ Lock 2.
- Thread B giữ Lock 2 và chờ Lock 1.
- Không thread nào tiếp tục được để nhả lock.

Trong thread dump, tìm thông báo deadlock và phần `waiting to lock`/`locked`. JConsole có nút Detect Deadlock. Có thể dùng thread dump từ `jcmd` để lưu bằng chứng.

Khi sửa code:

- Giữ thứ tự lấy nhiều lock nhất quán.
- Giữ critical section ngắn.
- Tránh gọi I/O hoặc callback bên ngoài khi đang giữ lock.
- Dùng `tryLock` với timeout nếu phù hợp.
- Cân nhắc concurrent collection hoặc thiết kế immutable để giảm chia sẻ state.

Không giải quyết deadlock bằng cách tăng thread pool. Thêm thread có thể chỉ làm tăng số thread bị mắc kẹt.

## 14. Điều tra CPU cao và latency

Nếu CPU cao:

1. Xác định process Java đang dùng CPU bằng công cụ hệ điều hành.
2. Ghi lại PID và thread có CPU time cao nếu OS hỗ trợ.
3. Thu thập JFR recording hoặc execution samples.
4. Đối chiếu thread ID với stack trace.
5. Xem method nóng, vòng lặp, retry, serialization hoặc code xử lý dữ liệu.
6. Kiểm tra lock contention và GC nếu CPU không nằm trong application method rõ ràng.

Bắt đầu JFR cho JVM đang chạy:

```sh
jcmd 24680 JFR.start name=cpu-investigation settings=profile duration=2m
```

Kiểm tra recording:

```sh
jcmd 24680 JFR.check name=cpu-investigation
```

Dump ra file:

```sh
jcmd 24680 JFR.dump name=cpu-investigation filename=cpu-investigation.jfr
```

Mở file bằng JDK Mission Control hoặc kiểm tra bằng:

```sh
jfr summary cpu-investigation.jfr
```

`profile` thu thập dữ liệu chi tiết hơn `default` và có thể tạo overhead cao hơn. Chọn thời gian ngắn, đánh giá impact và tránh bật nhiều recording chi tiết cùng lúc.

CPU cao cũng có thể do GC. Đối chiếu JFR với GC logs, allocation rate, thread count và CPU metrics của OS để phân biệt application hot loop với GC overhead.

## 15. Điều tra heap tăng và OutOfMemoryError

Khi heap tăng, bắt đầu bằng việc xem heap usage và xu hướng GC. Một snapshot đơn lẻ không chứng minh memory leak.

Lấy heap information:

```sh
jcmd 24680 GC.heap_info
```

Tạo class histogram:

```sh
jcmd 24680 GC.class_histogram
```

Histogram cho biết số instance và shallow bytes theo class. Nó giúp xác định nhóm object đáng chú ý nhưng không cho biết object nào giữ reference đến chúng.

Nếu cần object graph, tạo heap dump:

```sh
jcmd 24680 GC.heap_dump /var/tmp/order-service.hprof
```

Mở file bằng Eclipse Memory Analyzer (MAT) hoặc công cụ heap analysis phù hợp. Xem dominator tree, retained heap và path to GC roots để tìm reference giữ object.

Heap dump có thể rất lớn và thao tác có impact cao, có thể gây pause và cần dung lượng đĩa đáng kể. Kiểm tra trợ giúp của target JVM trước khi chạy, chọn thời điểm phù hợp và bảo vệ file vì nó có thể chứa dữ liệu nghiệp vụ, token hoặc thông tin người dùng.

Với OutOfMemoryError do Java heap, có thể cấu hình trước khi khởi chạy:

```sh
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/tmp/heap-dumps -jar app.jar
```

Đường dẫn cần có quyền ghi và đủ dung lượng. Heap dump tự động không thay thế việc thu thập log và metadata về thời điểm lỗi.

## 16. Phân biệt Java heap và native memory

Không phải mọi memory issue đều nằm trong Java heap. Process RSS có thể tăng do:

- Metaspace và compressed class space.
- Thread stacks.
- JIT code cache.
- Direct byte buffers.
- JNI hoặc native libraries.
- Cấu trúc nội bộ của JVM và garbage collector.

Nếu heap histogram ổn định nhưng RSS tiếp tục tăng, kiểm tra native memory và vùng off-heap.

Native Memory Tracking (NMT) phải được bật lúc JVM khởi động:

```sh
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau khi chạy, xem thống kê:

```sh
jcmd 24680 VM.native_memory summary
```

Có thể xem chênh lệch nếu đã chụp baseline:

```sh
jcmd 24680 VM.native_memory baseline
jcmd 24680 VM.native_memory summary.diff
```

NMT chỉ theo dõi các nhóm native allocation mà HotSpot quản lý; nó không nhất thiết bao phủ mọi allocation của thư viện native bên thứ ba. Nếu cần điều tra sâu hơn, kết hợp công cụ hệ điều hành và native profiler.

## 17. Điều tra GC và class loading

Để xem GC nhanh, có thể dùng:

```sh
jstat -gcutil 24680 1000 10
```

Các cột như Eden/Old utilization, young GC count và full GC count giúp nhìn xu hướng qua nhiều mẫu. `jstat` là công cụ có giới hạn và output phụ thuộc JDK/collector; không parse output như một API ổn định.

Để xem classloader statistics:

```sh
jcmd 24680 VM.classloader_stats
```

Để xem Metaspace:

```sh
jcmd 24680 VM.metaspace
```

Nếu class count hoặc Metaspace tăng liên tục, kiểm tra dynamic proxy, class generation, plugin, redeploy và classloader lifecycle. Classloader cũ có thể không được thu hồi nếu còn thread, ThreadLocal, static reference hoặc registry giữ nó.

## 18. JConsole và JDK Mission Control

JConsole là công cụ JMX GUI đi kèm JDK. Nó hiển thị heap/non-heap memory, thread, class loading, CPU và MBeans. Dùng JConsole khi cần quan sát trực quan một JVM đang chạy hoặc kiểm tra platform/custom MBean.

JDK Mission Control (JMC) là bộ công cụ phân tích JFR và giám sát JVM. JMC thường được cài riêng, không nằm trong mọi bản JDK. Dùng JMC để xem CPU samples, allocation, GC, lock contention, thread và I/O theo timeline.

| Công cụ | Thế mạnh |
|---|---|
| JConsole | Quan sát JMX, memory, threads, classes và MBeans |
| JMC | Phân tích JFR, event timeline và profiling |
| `jcmd` | Gửi diagnostic command trực tiếp đến JVM |
| `jdb` | Debug source bằng breakpoint và stepping |

Không nên dùng JConsole làm hệ thống polling production lâu dài nếu truy vấn MBean quá dày hoặc thao tác có thể làm thay đổi trạng thái ứng dụng. Với điều tra dài hạn, ưu tiên JFR, JMX metrics và hệ thống observability được phê duyệt.

## 19. JVM crash và postmortem debugging

Khi JVM crash, tìm file fatal error log thường có tên dạng:

```text
hs_err_pid24680.log
```

Vị trí file phụ thuộc cấu hình và working directory. Có thể chỉ định đường dẫn bằng:

```sh
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log -jar app.jar
```

Trong fatal error log, kiểm tra:

- Signal hoặc exception gây crash.
- Current thread và native/Java stack.
- Problematic frame.
- JVM version, OS và CPU.
- Loaded libraries.
- Command line và VM arguments.
- Memory map hoặc core dump information nếu có.

Nếu có core dump, có thể dùng `jhsdb` và native debugger như `gdb`/WinDbg tùy OS, symbol và loại crash. Các lệnh `jhsdb jstack`, `jhsdb jmap` hoặc `jhsdb clhsdb` có thể giúp phân tích core file. Cần đúng binary/JDK build và core dump tương ứng.

Crash trong native code, JNI hoặc JVM có thể không tạo Java exception. Đừng chỉ tìm application stack trace; kiểm tra `hs_err_pid` log, native libraries và OS logs.

## 20. JNI và native integration

Nếu ứng dụng dùng JNI hoặc thư viện native, có thể bật kiểm tra JNI khi khởi chạy:

```sh
java -Xcheck:jni -jar app.jar
```

`-Xcheck:jni` giúp phát hiện một số cách dùng JNI không hợp lệ, ví dụ sai thứ tự gọi API hoặc truyền reference không đúng. Nó có thể tạo overhead và log nhiều hơn, nên dùng có mục đích trong môi trường kiểm thử hoặc phiên điều tra phù hợp.

Để xem log JNI chi tiết hơn có thể cân nhắc `-verbose:jni`, nhưng output có thể rất lớn. Không bật mọi verbose option cùng lúc nếu chưa xác định điều cần tìm.

## 21. Virtual threads và debugging

Với Java 21, ứng dụng có thể dùng virtual threads. Số lượng virtual thread có thể rất lớn; debugger hoặc thread inspection cố theo dõi tất cả có thể tạo overhead và làm công cụ quá tải.

Trong `jdb`, mặc định không theo dõi mọi virtual thread ngay từ lúc được tạo. Tùy chọn `-trackallthreads` yêu cầu theo dõi toàn bộ thread, bao gồm virtual threads:

```sh
jdb -trackallthreads -classpath out com.example.DebugDemo
```

Chỉ bật khi thật sự cần. Nếu số virtual thread rất lớn, debugger có thể tốn tài nguyên và danh sách thread trở nên khó xử lý. Một số virtual thread đã được tạo trước khi attach có thể không xuất hiện đầy đủ tùy thời điểm và cấu hình debug agent.

Khi điều tra virtual-thread application, kết hợp JFR, thread dump, event và metric của executor/scheduler. Đừng giả định mọi virtual thread tương ứng với một OS thread riêng.

## 22. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jcmd` không tìm thấy process | PID sai, process đã dừng hoặc khác PID namespace | Dùng `jcmd -l`/`jps -l` trong đúng môi trường |
| Attach bị từ chối | Khác user/group, quyền OS hoặc attach bị vô hiệu hóa | Chạy bằng tài khoản phù hợp và kiểm tra JVM flags |
| `jdb` không tìm thấy class | Classpath sai hoặc tên package/class không đúng | Kiểm tra output `javac -d` và truyền `-classpath` |
| Breakpoint không dừng | Breakpoint đặt sai method/line, class chưa load hoặc thiếu debug info | Dùng `javac -g`, kiểm tra sourcepath và breakpoint list |
| Không xem được local variables | Compile thiếu local variable debug information hoặc sai stack frame | Biên dịch lại bằng `javac -g` và chọn đúng thread/frame |
| JDWP connection refused | Target chưa bật agent, sai port hoặc firewall chặn | Kiểm tra startup option, port, bind address và tunnel |
| JVM đứng ngay khi khởi chạy | JDWP dùng `suspend=y` nhưng debugger chưa attach | Attach debugger hoặc đổi `suspend=n` khi phù hợp |
| Thread dump không chỉ ra nguyên nhân | Chỉ có một snapshot hoặc stack thay đổi nhanh | Thu thập nhiều dump và đối chiếu cùng thread |
| Heap dump không tạo được | Thiếu disk, quyền ghi hoặc đường dẫn không tồn tại | Kiểm tra dung lượng, quyền và path trên máy JVM |
| Histogram tăng nhưng không chứng minh leak | Workload tăng hoặc object còn được sử dụng hợp lệ | So sánh live set nhiều lần và kiểm tra heap dump |
| RSS tăng nhưng heap ổn định | Native/off-heap memory tăng | Kiểm tra NMT, direct buffers và native libraries |
| JFR không có event mong đợi | Template không bật event hoặc threshold chưa đạt | Kiểm tra settings và tạo recording phù hợp |
| `jhsdb` không đọc được core | Binary/JDK không khớp hoặc core không tương thích | Dùng đúng executable và core của cùng process/build |
| Debugger làm lỗi không tái hiện | Breakpoint làm thay đổi timing/thread scheduling | Dùng logging, JFR hoặc profiler ít xâm lấn hơn |

Khi lỗi công cụ xảy ra, kiểm tra đúng target JVM, quyền, namespace và phiên bản JDK trước. Không kết luận ứng dụng không có lỗi chỉ vì một diagnostic command không attach được.

## 23. Chọn công cụ theo câu hỏi điều tra

| Câu hỏi | Công cụ nên bắt đầu |
|---|---|
| Dòng code nào tạo ra kết quả sai? | IDE debugger hoặc `jdb` |
| Exception phát sinh ở đâu? | Stack trace, breakpoint, `catch` trong `jdb` |
| Thread đang làm gì? | `jcmd Thread.print -l` |
| Có deadlock không? | Thread dump, JConsole Detect Deadlock |
| Method nào dùng CPU? | JFR/JMC hoặc profiler |
| Heap chứa class nào nhiều? | `jcmd GC.class_histogram` |
| Object nào giữ heap? | Heap dump + MAT dominator/path to GC roots |
| GC có gây latency không? | JFR, GC logs, `jstat`, JMX |
| Metaspace tăng vì sao? | `VM.classloader_stats`, `VM.metaspace`, heap dump |
| RSS tăng ngoài heap? | NMT và native OS tools |
| JVM crash vì native code? | `hs_err_pid` log, core dump, `jhsdb`, native debugger |

Chọn công cụ theo câu hỏi cụ thể sẽ giúp giảm overhead và tạo bằng chứng dễ diễn giải.

## 24. Checklist cho một phiên JVM debugging

- [ ] Đã ghi lại JDK vendor/version, OS, container, PID và JVM arguments.
- [ ] Đã xác định triệu chứng và thời điểm bắt đầu.
- [ ] Đã lưu application logs, exception stack trace và request/correlation ID.
- [ ] Đã dùng `jcmd -l` hoặc `jps -l` để xác định đúng JVM.
- [ ] Đã kiểm tra `jcmd PID help` trước khi dùng command ít quen thuộc.
- [ ] Đã chọn debugger source-level hay runtime diagnostics theo câu hỏi.
- [ ] Đã dùng thread dump nhiều lần nếu điều tra hang/deadlock.
- [ ] Đã dùng JFR nếu cần timeline CPU, GC, lock hoặc I/O.
- [ ] Đã dùng histogram/heap dump khi cần phân tích memory.
- [ ] Đã kiểm tra native memory nếu RSS không khớp Java heap.
- [ ] Đã bảo vệ heap dump, JFR và diagnostic output.
- [ ] Đã không mở JDWP debug port ra mạng không tin cậy.
- [ ] Đã đánh giá impact trước khi chạy heap dump hoặc command có impact cao.
- [ ] Đã sửa nguyên nhân và chạy lại cùng workload để xác nhận.

## 25. Tài liệu tham khảo

- Oracle JDK 21 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 Tool Reference — The `jcmd` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 Tool Reference — The `jdb` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html
- Java Platform Debugger Architecture — Connection and Invocation Details: https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html
- Oracle Java SE 21 Management Guide — JConsole: https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html

JVM debugging hiệu quả bắt đầu bằng việc phân loại triệu chứng và thu thập bằng chứng đúng loại. Dùng `jdb` cho logic source, `jcmd` và thread dump cho trạng thái process, JFR/JMC cho hiệu năng theo thời gian, heap dump cho object retention và `hs_err_pid`/core dump cho crash. Đánh giá tác động và bảo vệ dữ liệu chẩn đoán, đặc biệt khi bật JDWP hoặc thu thập heap dump trong production.