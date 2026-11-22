# Gửi diagnostic command bằng jcmd

**`jcmd`** là công cụ chẩn đoán đi kèm JDK, cho phép gửi lệnh quản trị và thu thập thông tin từ một Java Virtual Machine (JVM) đang chạy. Thay vì dừng ứng dụng để bật debugger, bạn có thể dùng `jcmd` để xem thread dump, heap, classloader, VM flags, system properties hoặc bắt đầu một bản ghi Java Flight Recorder (JFR).

`jcmd` đặc biệt hữu ích khi điều tra sự cố trên môi trường đang chạy, chẳng hạn CPU tăng cao, ứng dụng phản hồi chậm, nghi ngờ deadlock, heap tăng bất thường hoặc cần thu thập dữ liệu hiệu năng. Mỗi diagnostic command có phạm vi và mức tác động khác nhau; hãy xem trợ giúp của chính JVM đích trước khi gửi lệnh.

## 1. jcmd hoạt động như thế nào?

`jcmd` sử dụng cơ chế Attach của HotSpot để kết nối tới một JVM cục bộ, gửi diagnostic command và nhận kết quả trả về.

Luồng cơ bản:

1. Xác định tiến trình Java cần kiểm tra.
2. Lấy PID hoặc tên main class của tiến trình.
3. Yêu cầu JVM đích liệt kê các diagnostic command được hỗ trợ.
4. Chọn lệnh phù hợp với vấn đề cần điều tra.
5. Gửi command và thu thập output.
6. Lưu, phân tích kết quả; sau đó dừng recording hoặc tắt debug nếu đã bật.

Cú pháp tổng quát:

```text
jcmd <pid | main-class> <command> [arguments]
```

Trong đó:

- `pid`: process ID của JVM đích.
- `main-class`: tên đầy đủ hoặc một phần tên lớp main đã dùng để khởi chạy JVM.
- `command`: diagnostic command được JVM đích hỗ trợ.
- `arguments`: tùy chọn riêng của command, thường theo dạng `key=value` hoặc flag.

Có thể xem trợ giúp tổng quát:

```bash
jcmd -h
```

`jcmd` không phải công cụ gửi lệnh tới JVM từ xa qua mạng. Nó attach vào JVM trên cùng máy/host theo cơ chế hệ điều hành. Với container, cần chú ý PID namespace, user và quyền attach.

## 2. Liệt kê các JVM đang chạy bằng jcmd -l

Trước khi gửi diagnostic command, hãy tìm tiến trình cần kiểm tra:

```bash
jcmd -l
```

Output minh họa:

```text
18420 com.example.DiagnosticsTarget
29116 org.apache.catalina.startup.Bootstrap
32780 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider
```

Mỗi dòng thường gồm PID và tên main class hoặc thông tin module/class dùng để khởi chạy JVM.

Ví dụ:

- PID `18420` là ứng dụng `com.example.DiagnosticsTarget`.
- PID `29116` là tiến trình Tomcat.
- PID `32780` là JShell.

PID trong ví dụ chỉ minh họa; giá trị thực tế thay đổi theo lần khởi động.

Lệnh thay thế để liệt kê JVM là `jps -l`, nhưng `jcmd -l` là cách trực tiếp để bắt đầu quy trình chẩn đoán bằng jcmd.

**Lưu ý:** `jcmd -l` chỉ hiển thị các JVM mà cơ chế attach có thể phát hiện trong phạm vi môi trường hiện tại. JVM chạy dưới user khác hoặc trong PID namespace/container khác có thể không xuất hiện.

## 3. Chọn đúng JVM đích

Sau khi tìm PID, gửi lệnh theo PID:

```bash
jcmd 18420 VM.uptime
```

Có thể dùng tên main class thay PID:

```bash
jcmd com.example.DiagnosticsTarget VM.uptime
```

Nếu tên main class không duy nhất hoặc có nhiều tiến trình cùng chạy một ứng dụng, ưu tiên PID để tránh gửi nhầm lệnh.

Một số dạng target:

| Target | Ý nghĩa |
| --- | --- |
| `18420` | PID cụ thể |
| `com.example.DiagnosticsTarget` | Tên main class đầy đủ |
| `DiagnosticsTarget` | Có thể dùng một phần tên main class nếu khớp |
| `0` | Gửi command tới tất cả JVM mà công cụ tìm thấy; cần cực kỳ thận trọng |

Không dùng target `0` trong thao tác thông thường. Một command có thể tạo thread dump, heap dump hoặc thay đổi trạng thái của nhiều ứng dụng cùng lúc.

PID có thể thay đổi sau khi ứng dụng restart. Hãy chạy lại `jcmd -l` và xác nhận đúng tiến trình trước mỗi lần điều tra mới.

## 4. Xem diagnostic command được JVM hỗ trợ

Các command có sẵn phụ thuộc phiên bản JDK, loại JVM, provider và trạng thái tiến trình. Không nên giả định mọi JVM đều có cùng danh sách.

Liệt kê command:

```bash
jcmd 18420 help
```

Xem trợ giúp một command:

```bash
jcmd 18420 help Thread.print
jcmd 18420 help GC.heap_info
jcmd 18420 help JFR.start
```

Một số command phổ biến:

| Command | Công dụng |
| --- | --- |
| `VM.uptime` | Thời gian JVM đã chạy |
| `VM.version` | Phiên bản JVM |
| `VM.command_line` | Lệnh khởi chạy JVM |
| `VM.flags` | Giá trị VM flags |
| `VM.system_properties` | System properties |
| `VM.info` | Thông tin tổng quát về JVM |
| `VM.classloader_stats` | Thống kê classloader |
| `VM.classes` | Thông tin các class đã nạp |
| `GC.heap_info` | Thông tin tổng quan Java heap |
| `GC.class_histogram` | Thống kê object theo class |
| `GC.heap_dump` | Tạo heap dump HPROF |
| `Thread.print` | In thread dump và stack trace |
| `JFR.start` | Bắt đầu JFR recording |
| `JFR.check` | Kiểm tra recording đang chạy |
| `JFR.dump` | Xuất dữ liệu recording ra tệp |
| `JFR.stop` | Dừng recording |

Tên và tham số command có thể khác giữa các bản JDK. Lệnh `help` trên chính JVM đích là nguồn tham khảo phù hợp nhất.

## 5. Gửi command đơn giản để kiểm tra JVM

Một số lệnh đọc trạng thái có thể dùng để bắt đầu điều tra.

Xem thời gian hoạt động:

```bash
jcmd 18420 VM.uptime
```

Xem phiên bản JVM:

```bash
jcmd 18420 VM.version
```

Xem VM flags:

```bash
jcmd 18420 VM.flags
```

Liệt kê toàn bộ flags mà VM hỗ trợ:

```bash
jcmd 18420 VM.flags -all
```

Xem thông tin chung:

```bash
jcmd 18420 VM.info
```

Xem classloader statistics:

```bash
jcmd 18420 VM.classloader_stats
```

Ví dụ output của `VM.uptime` có dạng:

```text
18420:
163.650 s
```

Giá trị là thời gian chạy tại thời điểm command được xử lý, nên không cố định.

## 6. Xem heap bằng GC.heap_info

`GC.heap_info` cung cấp thông tin tổng quan về Java heap, chẳng hạn tổng dung lượng reserved/committed, dung lượng đã sử dụng và thông tin collector.

Gửi command:

```bash
jcmd 18420 GC.heap_info
```

Output minh họa với G1:

```text
18420:
garbage-first heap   total reserved 30932992K, committed 245760K, used 52538K
region size 16384K, 3 young, 1 survivors
Metaspace       used 17878K, committed 18368K
class space     used 1926K, committed 2112K
```

Các con số và định dạng phụ thuộc collector, phiên bản JVM và trạng thái ứng dụng. Không dùng một lần đọc heap để kết luận có memory leak; cần quan sát xu hướng theo thời gian và tương quan với GC, allocation và workload.

Phân biệt:

- **Reserved:** vùng địa chỉ bộ nhớ VM đã dành trước.
- **Committed:** vùng VM đã commit để có thể sử dụng.
- **Used:** phần bộ nhớ đang được sử dụng theo thống kê của collector.
- **Metaspace:** bộ nhớ native dùng cho metadata của class.

`GC.heap_info` có tác động thấp hơn heap dump nhưng vẫn là thao tác chẩn đoán lên JVM. Đọc mô tả Impact từ `help GC.heap_info` trên môi trường đích.

## 7. Tạo class histogram bằng GC.class_histogram

`GC.class_histogram` thống kê số lượng object và dung lượng heap theo class. Đây là cách hữu ích để tìm loại object chiếm nhiều bộ nhớ.

Gửi command:

```bash
jcmd 18420 GC.class_histogram
```

Có thể yêu cầu kiểm tra cả object không reachable:

```bash
jcmd 18420 GC.class_histogram -all
```

Output minh họa:

```text
 num     #instances         #bytes  Class description
-------------------------------------------------------
   1:         152340        9134400  [B
   2:          45320        3625600  java.lang.String
   3:          12000        1920000  java.util.HashMap$Node
   4:           8200         656000  java.lang.Object
```

Ý nghĩa:

- `#instances`: số object thuộc class.
- `#bytes`: dung lượng ước tính của các object thuộc class.
- `Class description`: tên class hoặc dạng mảng.

**Tác động:** theo trợ giúp JVM, command này có Impact cao và phụ thuộc kích thước/nội dung heap. Không chạy liên tục hoặc trong thời điểm ứng dụng nhạy cảm nếu chưa đánh giá tác động. Histogram chỉ cho biết phân bố object; nó không tự giải thích vì sao object được giữ lại.

## 8. Tạo heap dump bằng GC.heap_dump

Heap dump lưu trạng thái object trong heap ra tệp HPROF để phân tích bằng công cụ như Java Mission Control hoặc Eclipse Memory Analyzer (MAT).

Windows PowerShell:

```powershell
jcmd 18420 GC.heap_dump C:\diagnostics\app-heap.hprof
```

macOS/Linux:

```bash
jcmd 18420 GC.heap_dump /var/tmp/app-heap.hprof
```

JVM phải có quyền ghi vào thư mục đích. Đảm bảo ổ đĩa còn đủ dung lượng và thư mục chỉ người có quyền phù hợp mới truy cập được.

Theo trợ giúp của JVM HotSpot hiện đại:

- `GC.heap_dump` có Impact cao, phụ thuộc dung lượng và nội dung heap.
- Mặc định command yêu cầu một full GC trước khi dump.
- Tùy chọn `-all` yêu cầu dump cả object không reachable và thay đổi hành vi full-GC mặc định.
- Tệp dump có thể rất lớn.

Heap dump có thể chứa dữ liệu nhạy cảm đang nằm trong bộ nhớ, chẳng hạn token, session data, nội dung request hoặc thông tin cá nhân. Hãy bảo vệ tệp, giới hạn quyền truy cập, mã hóa khi lưu/truyền và xóa theo chính sách lưu giữ.

Không tạo heap dump trong production chỉ để thử lệnh. Chỉ thực hiện khi có mục tiêu chẩn đoán rõ ràng, dung lượng phù hợp và chấp nhận được mức tạm dừng ứng dụng.

## 9. Lấy thread dump bằng Thread.print

Thread dump cho biết các thread Java, trạng thái và stack trace tại thời điểm lấy mẫu. Nó hữu ích khi điều tra:

- Ứng dụng bị treo hoặc phản hồi chậm.
- Thread pool hết worker.
- Deadlock hoặc lock contention.
- Thread chờ I/O hoặc chờ monitor.
- CPU cao do một số thread chạy liên tục.

Gửi thread dump:

```bash
jcmd 18420 Thread.print
```

Bao gồm thông tin lock:

```bash
jcmd 18420 Thread.print -l
```

Trong phiên bản hỗ trợ, có thể bật extended thread information:

```bash
jcmd 18420 Thread.print -e
```

Output minh họa:

```text
"main" #1 prio=5 os_prio=0 tid=0x... nid=0x... waiting
   java.lang.Thread.State: WAITING
   at java.lang.Object.wait(Native Method)
   at com.example.DiagnosticsTarget.main(DiagnosticsTarget.java:...)
```

Đọc thread dump:

- Tên thread giúp xác định vai trò.
- `java.lang.Thread.State` cho biết trạng thái Java.
- Stack trace cho biết thread đang thực hiện hoặc chờ tại đoạn code nào.
- Các dòng `locked`, `waiting to lock` và `parking` giúp nhận diện quan hệ đồng bộ.

Một thread dump là ảnh chụp tại một thời điểm. Khi điều tra deadlock hoặc thread bị kẹt, lấy nhiều thread dump cách nhau vài giây rồi so sánh stack trace và trạng thái. Nếu mọi lần đều giống nhau, đó là dấu hiệu cần điều tra thêm, không tự động chứng minh deadlock.

## 10. Kiểm tra VM flags và system properties

Xem flags hiện tại:

```bash
jcmd 18420 VM.flags
```

Xem tất cả flags:

```bash
jcmd 18420 VM.flags -all
```

Các flags có thể cho biết cấu hình heap, GC, compiler, compressed pointers và những tùy chọn runtime khác.

Xem system properties:

```bash
jcmd 18420 VM.system_properties
```

Xem command line khởi chạy:

```bash
jcmd 18420 VM.command_line
```

Các output này có thể chứa đường dẫn nội bộ, tên môi trường, endpoint hoặc giá trị nhạy cảm nếu ứng dụng đặt bí mật trong system property/command-line argument. Không dán toàn bộ output lên ticket, chat hoặc log công khai nếu chưa lọc và kiểm tra.

`VM.flags`, `VM.system_properties` và `VM.command_line` chủ yếu phục vụ quan sát. Không nhầm chúng với lệnh thay đổi cấu hình. `VM.set_flag` là command khác, có thể thay đổi flag nếu flag đó cho phép ghi; chỉ sử dụng khi đã hiểu tác động và có quy trình vận hành phù hợp.

## 11. Kiểm tra classloader bằng VM.classloader_stats

Classloader statistics giúp điều tra số lượng class được nạp và mức sử dụng metaspace theo từng classloader.

Gửi command:

```bash
jcmd 18420 VM.classloader_stats
```

Output có thể chứa:

- Classloader và parent classloader.
- Địa chỉ class loader data.
- Số lượng class được nạp.
- Kích thước metaspace chunks/blocks.
- Tổng thống kê theo classloader.

Lệnh này hữu ích khi:

- Ứng dụng tạo quá nhiều class động.
- Nghi ngờ classloader leak sau redeploy.
- Metaspace tăng bất thường.
- Nhiều plugin hoặc framework tạo classloader riêng.

Classloader leak thường liên quan đến classloader cũ vẫn bị tham chiếu từ thread, ThreadLocal, static field, JDBC driver, logging framework hoặc thư viện khác. Một lần chụp thống kê chỉ là dữ liệu ban đầu; cần so sánh sau nhiều lần deploy hoặc theo thời gian.

## 12. Ghi Java Flight Recorder bằng JFR.start

Java Flight Recorder (JFR) thu thập sự kiện runtime như GC, allocation, compiler, thread, lock contention, I/O và nhiều sự kiện JVM khác.

Bắt đầu recording có tên:

```bash
jcmd 18420 JFR.start name=incident settings=default
```

Kiểm tra recording:

```bash
jcmd 18420 JFR.check
```

Xem chi tiết cấu hình recording:

```bash
jcmd 18420 JFR.check name=incident verbose=true
```

JFR có các cấu hình dựng sẵn:

- `default`: thu thập thông tin phổ biến với overhead thấp, phù hợp ghi trong thời gian dài.
- `profile`: thu thập nhiều dữ liệu hơn nhưng có overhead cao hơn; nên dùng trong khoảng thời gian ngắn khi cần phân tích sâu.

Có thể đặt thời lượng và tên tệp ngay khi bắt đầu:

```bash
jcmd 18420 JFR.start name=incident settings=default duration=60s filename=incident.jfr
```

Khi hết 60 giây, recording tự kết thúc và ghi tệp theo cấu hình. Đường dẫn tương đối được tính theo working directory của JVM đích, không nhất thiết là thư mục terminal đang chạy `jcmd`.

JFR có thể tạo overhead tùy settings và event. Đừng dùng profile nặng liên tục trong production nếu chưa đánh giá tác động.

## 13. Xuất và dừng JFR recording

Nếu recording đang chạy, có thể xuất snapshot ra tệp mà vẫn tiếp tục recording:

```bash
jcmd 18420 JFR.dump name=incident filename=incident-snapshot.jfr
```

Sau khi đã thu thập đủ dữ liệu, dừng recording và ghi phần dữ liệu còn lại:

```bash
jcmd 18420 JFR.stop name=incident filename=incident-final.jfr
```

Các lệnh chính:

| Command | Ý nghĩa |
| --- | --- |
| `JFR.start` | Bắt đầu recording |
| `JFR.check` | Kiểm tra recording đang chạy |
| `JFR.dump` | Sao chép dữ liệu hiện có ra tệp; recording tiếp tục |
| `JFR.stop` | Dừng recording; có thể ghi dữ liệu ra tệp |

Sau khi có tệp `.jfr`, mở bằng Java Mission Control (JMC) hoặc dùng công cụ `jfr` đi kèm JDK để xem summary:

```bash
jfr summary incident-final.jfr
```

Có thể xuất dữ liệu sự kiện thành JSON hoặc XML bằng các tùy chọn của `jfr print`; xem `jfr help` để chọn event và định dạng phù hợp.

JFR recording có thể chứa thông tin nhạy cảm về hoạt động ứng dụng, URL, tên class, thread và một phần dữ liệu sự kiện. Hãy bảo vệ tệp recording như một diagnostic artifact nội bộ.

## 14. Kiểm tra native memory bằng VM.native_memory

Java heap không phải toàn bộ bộ nhớ tiến trình. JVM còn sử dụng native memory cho thread stacks, metaspace, code cache, compiler, GC structures, direct buffers và thư viện native.

Nếu Native Memory Tracking (NMT) được bật từ lúc JVM khởi động, có thể dùng:

```bash
jcmd 18420 VM.native_memory summary
```

Để so sánh với baseline:

```bash
jcmd 18420 VM.native_memory baseline
jcmd 18420 VM.native_memory summary.diff
```

Có thể yêu cầu chi tiết hơn:

```bash
jcmd 18420 VM.native_memory detail
```

NMT phải được bật khi khởi động JVM, ví dụ:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Nếu JVM không bật NMT từ đầu, `VM.native_memory` có thể báo Native Memory Tracking chưa được bật. Không thể bật đầy đủ NMT hồi tố cho tiến trình đang chạy.

NMT có overhead và chi phí bộ nhớ riêng; chọn `summary` hoặc `detail` theo nhu cầu và đánh giá tác động trước khi bật trong production.

## 15. Gửi nhiều command từ một tệp

Khi cần chạy một nhóm diagnostic command, có thể lưu command trong một tệp rồi dùng tùy chọn `-f`.

Ví dụ tệp **`diagnostics.txt`**:

```text
VM.uptime
VM.flags
GC.heap_info
VM.classloader_stats
```

Gửi các command từ tệp:

```bash
jcmd 18420 -f diagnostics.txt
```

Cách này giúp lưu lại danh sách kiểm tra và tái sử dụng trong một quy trình vận hành. Mỗi command vẫn được thực thi trên JVM đích; hãy bảo đảm tất cả command trong tệp đều phù hợp và an toàn cho tiến trình đó.

Không đưa command có tác động cao như `GC.heap_dump`, `GC.run` hoặc `VM.set_flag` vào tệp chạy tự động nếu chưa có bước phê duyệt và đánh giá tác động.

## 16. Gửi diagnostic command trong Windows và Linux

Cú pháp `jcmd` giống nhau trên các hệ điều hành; khác biệt chủ yếu nằm ở cách chỉ định đường dẫn và quyền truy cập.

**Windows PowerShell:**

```powershell
jcmd -l
jcmd 18420 help
jcmd 18420 VM.uptime
jcmd 18420 Thread.print -l
jcmd 18420 GC.heap_dump C:\diagnostics\app-heap.hprof
```

**macOS/Linux:**

```bash
jcmd -l
jcmd 18420 help
jcmd 18420 VM.uptime
jcmd 18420 Thread.print -l
jcmd 18420 GC.heap_dump /var/tmp/app-heap.hprof
```

Trên Linux/macOS, user thực thi `jcmd` thường cần cùng effective user/group với JVM đích. Trên Windows, tiến trình gọi cũng cần quyền truy cập phù hợp với tài khoản chạy JVM.

Nếu chạy trong Docker/Kubernetes, có thể cần thực thi `jcmd` bên trong container hoặc qua một môi trường chia sẻ PID namespace và quyền attach phù hợp. PID nhìn từ host có thể khác PID trong container.

Không tự ý nâng quyền hoặc chạy command trên tiến trình thuộc user khác khi chưa được quản trị viên cho phép.

## 17. Các giới hạn và lỗi attach thường gặp

`jcmd` có một số điều kiện:

- JVM đích phải ở trên cùng máy/host theo cơ chế attach.
- User và quyền hệ điều hành phải cho phép attach.
- JVM có thể vô hiệu hóa attach bằng `-XX:+DisableAttachMechanism`.
- Một số môi trường container, sandbox hoặc security policy có thể chặn attach.
- Command hỗ trợ thay đổi theo phiên bản JDK và loại JVM.
- PID có thể đã kết thúc hoặc được tái sử dụng.
- Một số command có tác động lớn và có thể làm ứng dụng tạm dừng.

Lỗi thường gặp:

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jcmd` không được nhận diện | Chưa cài JDK hoặc PATH chưa có thư mục bin | Kiểm tra `JAVA_HOME` và PATH |
| Không thấy JVM trong `jcmd -l` | JVM chạy dưới user khác, container khác hoặc attach bị giới hạn | Kiểm tra user, PID namespace và môi trường chạy |
| `AttachNotSupportedException` | Không thể attach vào tiến trình đích | Kiểm tra PID, quyền và attach mechanism |
| `Access is denied` | Tài khoản hiện tại không có quyền truy cập JVM đích | Chạy dưới tài khoản được phép hoặc nhờ admin |
| `No such process` | PID sai hoặc JVM đã dừng | Chạy lại `jcmd -l` để tìm PID hiện tại |
| `Unknown diagnostic command` | JVM đích không hỗ trợ command hoặc sai tên | Dùng `jcmd <pid> help` và `help <command>` |
| Không ghi được heap dump | Thư mục không tồn tại, thiếu quyền hoặc hết dung lượng | Chọn đường dẫn có quyền ghi và kiểm tra disk |
| `VM.native_memory` báo NMT chưa bật | JVM không được khởi động với Native Memory Tracking | Bật NMT trong lần khởi động tiếp theo |
| JFR recording không bắt đầu | Sai option, thiếu quyền ghi hoặc JFR không hỗ trợ cấu hình | Kiểm tra `help JFR.start` và đường dẫn output |

Nếu attach bị vô hiệu hóa hoặc quyền hệ điều hành không cho phép, không có diagnostic command thông thường nào có thể vượt qua giới hạn đó một cách an toàn. Hãy làm việc với người quản trị hoặc dùng cơ chế quan sát đã được triển khai như JMX, JFR từ trước, metrics hoặc log.

## 18. Mức tác động và an toàn khi chẩn đoán

Không phải mọi command đều có chi phí như nhau. JVM thường hiển thị dòng **Impact** trong `help <command>`.

| Nhóm command | Ví dụ | Lưu ý |
| --- | --- | --- |
| Thấp | `VM.uptime`, `VM.flags`, `VM.version`, `VM.classloader_stats` | Thường phù hợp để kiểm tra trạng thái ban đầu |
| Trung bình | `Thread.print`, `GC.heap_info`, `JFR.start` | Có thể ảnh hưởng tùy kích thước ứng dụng, số thread và recording settings |
| Cao | `GC.class_histogram`, `GC.heap_dump` | Có thể tốn thời gian, CPU, bộ nhớ hoặc gây pause đáng kể |

Các command thay đổi trạng thái như `JFR.start`, `JFR.stop`, `GC.run` và `VM.set_flag` cần được xem xét riêng. Một số command tạo file lớn hoặc làm lộ dữ liệu từ heap.

Thực hành an toàn:

- Bắt đầu bằng các command Impact thấp.
- Đọc `help <command>` trước khi gửi lệnh chưa quen.
- Chỉ chọn command phục vụ một câu hỏi chẩn đoán cụ thể.
- Tránh chạy heap dump hoặc class histogram lặp lại không cần thiết.
- Dự trù disk và bảo vệ tệp heap dump/JFR.
- Lọc system properties và command line trước khi chia sẻ log.
- Giới hạn thời gian và settings của JFR recording.
- Ghi lại PID, thời điểm, JDK version và command đã chạy.
- Không dùng `jcmd 0` trừ khi thực sự muốn tác động đến tất cả JVM được phát hiện.

## 19. Ví dụ thực hành: tạo tiến trình Java để chẩn đoán

Tạo tệp **`DiagnosticsTarget.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

public class DiagnosticsTarget {
    private static final AtomicLong COUNTER = new AtomicLong();

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                COUNTER.incrementAndGet();

                try {
                    Thread.sleep(100);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "diagnostic-worker");

        worker.setDaemon(true);
        worker.start();

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Diagnostic target is running.");

        new CountDownLatch(1).await();
    }
}
```

Biên dịch bằng Java 17:

```bash
javac --release 17 DiagnosticsTarget.java
```

Chạy ứng dụng:

```bash
java DiagnosticsTarget
```

Output:

```text
PID=18420
Diagnostic target is running.
```

PID thay đổi theo môi trường. Để giữ tiến trình chạy, không đóng terminal này; mở terminal thứ hai để gửi command.

Tìm PID:

```bash
jcmd -l
```

Giả sử PID được in ra là `18420`, thử các command:

```bash
jcmd 18420 VM.uptime
jcmd 18420 GC.heap_info
jcmd 18420 VM.flags
jcmd 18420 VM.classloader_stats
jcmd 18420 Thread.print -l
```

Kiểm tra JFR:

```bash
jcmd 18420 JFR.start name=practice settings=default duration=30s filename=practice.jfr
jcmd 18420 JFR.check name=practice
```

Sau khi recording kết thúc, tìm tệp `practice.jfr` trong working directory của JVM đích và xem summary:

```bash
jfr summary practice.jfr
```

Dừng tiến trình bằng Ctrl+C trong terminal chạy `DiagnosticsTarget`.

Ví dụ này tạo một worker thread để thread dump có stack trace dễ nhận diện. Nó không mô phỏng tải production và không dùng để benchmark hiệu năng.

## 20. Quy trình chẩn đoán đề xuất

Khi ứng dụng có dấu hiệu bất thường, có thể tiến hành theo trình tự:

1. Xác định đúng host/container và tài khoản chạy JVM.
2. Chạy `jcmd -l` để tìm PID.
3. Chạy `jcmd <pid> help` để xem command hỗ trợ.
4. Thu thập `VM.uptime`, `VM.version`, `VM.flags` và `GC.heap_info`.
5. Nếu nghi ngờ thread blockage, lấy nhiều `Thread.print -l` cách nhau vài giây.
6. Nếu nghi ngờ heap retention, cân nhắc class histogram; chỉ tạo heap dump khi có kế hoạch phân tích và đủ tài nguyên.
7. Nếu cần phân tích hiệu năng theo thời gian, dùng JFR với settings và duration phù hợp.
8. Nếu heap ổn nhưng process memory tăng, xem xét NMT nếu đã bật từ startup.
9. Lưu diagnostic artifacts trong vị trí bảo mật và ghi nhận thời điểm/command.
10. Phân tích kết quả, đối chiếu metrics/log và lập kế hoạch khắc phục.
11. Dừng JFR recording sau khi thu thập đủ dữ liệu.
12. Xóa hoặc lưu trữ dump/recording theo chính sách retention.

Không gửi hàng loạt command trước khi xác định mục tiêu. Một chuỗi thu thập nhỏ, có thứ tự và có thời điểm rõ ràng thường dễ phân tích hơn một tập output lớn không có ngữ cảnh.

## 21. Ghi nhớ

- `jcmd` gửi diagnostic command tới JVM cục bộ đang chạy.
- Dùng `jcmd -l` để tìm PID và `jcmd <pid> help` để liệt kê command.
- Dùng `jcmd <pid> help <command>` để xem cú pháp và mức Impact.
- `VM.uptime`, `VM.flags`, `GC.heap_info` và `VM.classloader_stats` giúp quan sát trạng thái JVM.
- `Thread.print -l` tạo thread dump có thông tin lock.
- `GC.class_histogram` và `GC.heap_dump` có thể có tác động cao; heap dump còn có thể chứa dữ liệu nhạy cảm.
- `JFR.start`, `JFR.check`, `JFR.dump` và `JFR.stop` hỗ trợ ghi nhận sự kiện runtime.
- `VM.native_memory` yêu cầu NMT được bật từ lúc JVM khởi động.
- Attach phụ thuộc PID namespace, user, quyền hệ điều hành và cấu hình JVM.
- Chọn command theo mức Impact, bảo vệ diagnostic artifacts và dừng recording sau khi hoàn tất.

Khi nắm được quy trình tìm PID → xem command hỗ trợ → gửi diagnostic command → phân tích output, bạn có thể thu thập dữ liệu từ JVM đang chạy có kiểm soát, hỗ trợ điều tra sự cố mà không cần dừng ứng dụng chỉ để bắt đầu quan sát.
