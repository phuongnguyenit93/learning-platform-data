# Dùng jcmd an toàn

**jcmd** là công cụ dòng lệnh đi kèm JDK để gửi diagnostic command tới một JVM đang chạy. Công cụ hỗ trợ kiểm tra trạng thái JVM, thread, heap, class loading, native memory, logging và Java Flight Recorder (JFR). jcmd hữu ích khi cần thu thập dữ liệu chẩn đoán mà không phải dừng ứng dụng.

Dùng jcmd an toàn nghĩa là gửi đúng lệnh tới đúng process, hiểu tác động của lệnh trước khi chạy, bảo vệ dữ liệu chẩn đoán và giới hạn quyền truy cập. Không phải mọi diagnostic command đều chỉ đọc thông tin: một số lệnh có thể kích hoạt garbage collection, tạo heap dump lớn, thay đổi logging hoặc nạp native agent.

Bài này tập trung vào JDK 26 và HotSpot JVM. Danh sách lệnh khả dụng, cú pháp và mức tác động có thể khác theo JDK release hoặc JVM implementation; luôn kiểm tra help của process đích trước khi chạy.

## 1. jcmd hoạt động như thế nào?

jcmd gửi một diagnostic command request tới JVM đang chạy. JVM xử lý yêu cầu và trả kết quả về terminal hoặc ghi kết quả vào file theo command được chọn.

Luồng thao tác:

~~~text
Operator / diagnostic script
          |
          v
        jcmd
          |
          | local attach request
          v
      Target JVM
          |
          | diagnostic command
          v
 JVM serviceability subsystem
          |
          v
 Output / dump / JFR recording
~~~

jcmd không khởi chạy lại ứng dụng và không phải debugger tương tác từng dòng code. Nó yêu cầu JVM đang chạy thực hiện một thao tác chẩn đoán cụ thể.

Một số đặc điểm quan trọng:

- jcmd phải chạy trên cùng máy với JVM đích.
- Người chạy jcmd phải có cùng effective user ID và group ID với tài khoản đã khởi chạy JVM.
- Lệnh và tham số phụ thuộc JVM đích.
- jcmd không phải công cụ remote trực tiếp qua mạng.
- Các diagnostic command có mức tác động khác nhau; hãy đọc mô tả command trước khi dùng.

Nên sử dụng jcmd từ JDK cùng release với JVM đích khi có thể. Oracle không hỗ trợ dùng các serviceability tools của một JDK release để troubleshoot một release khác.

## 2. Xác định đúng JVM trước khi gửi lệnh

Bước đầu tiên là liệt kê các Java process:

~~~bash
jcmd -l
~~~

Không truyền đối số cũng tương đương với -l.

Ví dụ output minh họa:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

Output thực tế còn có thể chứa command-line arguments của process. PID là số nhận diện process; main class giúp phân biệt các ứng dụng đang chạy.

### Chọn PID cụ thể

Sau khi xác định đúng process, dùng PID:

~~~bash
jcmd 2125 VM.version
~~~

Dùng PID cụ thể là cách an toàn nhất khi máy chạy nhiều ứng dụng Java.

### Tránh chọn theo main class khi có nhiều instance

Có thể truyền tên main class:

~~~bash
jcmd com.acme.DemoServer VM.version
~~~

Tên main class có thể khớp với nhiều JVM đang chạy. Khi đó jcmd gửi command tới tất cả process có tên main class khớp. Không dùng cách này nếu chưa chắc chỉ có một instance phù hợp.

### Không dùng PID 0 trong thao tác thông thường

PID 0 có nghĩa là gửi command tới tất cả Java process khả dụng:

~~~bash
jcmd 0 VM.version
~~~

Đây là phạm vi rộng. Một command như Thread.print có thể tạo output rất lớn; command có tác động cao có thể ảnh hưởng nhiều ứng dụng cùng lúc. Trong production, không dùng PID 0 như cách viết tắt để xử lý một ứng dụng.

### Kiểm tra lại danh tính process

Trước khi chạy command có tác động trung bình hoặc cao, xác nhận process bằng các thông tin ít tác động:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.command_line
jcmd 2125 VM.uptime
~~~

VM.command_line và danh sách jcmd -l có thể hiển thị tham số khởi chạy. Nếu đội vận hành vô tình truyền secret trong command line, output có thể làm lộ secret. Không đưa nguyên output vào ticket công khai hoặc kênh chat không được phép.

## 3. Điều kiện attach và giới hạn truy cập

jcmd sử dụng cơ chế attach cục bộ của JVM. Các điều kiện thường cần kiểm tra:

| Điều kiện | Ý nghĩa |
|---|---|
| Cùng host | jcmd phải chạy trên máy có JVM đích |
| Cùng effective user/group | Tài khoản chạy jcmd phải phù hợp với tài khoản khởi chạy JVM |
| Attach mechanism đang bật | JVM phải cho phép công cụ attach |
| Đúng PID namespace | Trong container, PID nhìn thấy từ host có thể khác PID bên trong container |
| Công cụ tương thích | Dùng serviceability tool phù hợp với JDK của process đích |

Nếu JVM được khởi chạy với tùy chọn:

~~~bash
-XX:+DisableAttachMechanism
~~~

thì các công cụ attach như jcmd không thể kết nối theo cơ chế thông thường. Đây là cấu hình bảo vệ cần được quyết định lúc khởi chạy JVM; jcmd không thể bật lại attach từ bên ngoài.

### Chạy trong Docker hoặc container

jcmd -l không liệt kê JVM đang chạy trong một Docker process riêng biệt. Oracle khuyến nghị dùng công cụ hệ điều hành như ps để tìm PID trong môi trường phù hợp.

Các cách vận hành thường gặp:

- Chạy jcmd bên trong container, nơi PID namespace nhìn thấy JVM đích.
- Dùng ps trong container để xác định PID rồi gọi jcmd với PID đó.
- Nếu dùng host PID namespace, xác nhận PID trên host thực sự trỏ tới đúng process.
- Bảo đảm tài khoản chạy lệnh có quyền attach tương ứng.

Không lấy PID từ một namespace rồi dùng trong namespace khác mà không xác nhận. PID có thể trỏ tới process hoàn toàn khác.

## 4. Khám phá command trước khi chạy

Danh sách diagnostic command thay đổi theo JVM và JDK release. Hãy hỏi process đích:

~~~bash
jcmd 2125 help
~~~

Xem cú pháp của một command cụ thể:

~~~bash
jcmd 2125 help Thread.print
~~~

Có thể xem toàn bộ help:

~~~bash
jcmd 2125 help -all
~~~

Help của process đích cho biết:

- Command có được hỗ trợ không.
- Options và arguments nào hợp lệ.
- Giá trị mặc định.
- Mức tác động được tài liệu hóa.
- Điều kiện hoặc giới hạn riêng của command.

### Cú pháp option và argument

jcmd sử dụng hai dạng:

- Option thường được ghi dưới dạng key hoặc key=value.
- Argument là giá trị thuần, không thêm tên option=value nếu command định nghĩa argument vị trí.

Ví dụ JFR.start dùng options dạng key=value:

~~~bash
jcmd 2125 JFR.start name=incident settings=default duration=120s
~~~

GC.heap_dump nhận tên file là argument vị trí:

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

Nếu argument có khoảng trắng, đặt trong dấu nháy đơn hoặc kép phù hợp với shell đang sử dụng. Kiểm tra help để tránh nhầm option với argument.

## 5. Phân loại command theo mức tác động

JDK 26 mô tả mức tác động cho từng diagnostic command. Đây là hướng dẫn ước lượng; tác động thực tế phụ thuộc heap size, số thread, lượng class và tải của ứng dụng.

| Mức | Ví dụ | Cách sử dụng |
|---|---|---|
| Low | VM.version, VM.uptime, VM.flags, VM.info | Thường phù hợp cho bước kiểm tra ban đầu |
| Medium | Thread.print, GC.heap_info, VM.native_memory | Chạy khi có câu hỏi chẩn đoán cụ thể |
| High | GC.class_histogram, GC.heap_dump | Lập kế hoạch, kiểm soát pause, disk và dữ liệu đầu ra |

Mức tác động không đồng nghĩa với mức độ nhạy cảm của dữ liệu. Một command low impact như VM.system_properties vẫn có thể xuất thông tin cấu hình nhạy cảm.

### Command ít tác động để bắt đầu

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 VM.info
~~~

Các command này giúp biết JVM version, uptime, flags và thông tin trạng thái mà không cần tạo heap dump.

### Command cần cân nhắc kỹ hơn

~~~bash
jcmd 2125 GC.heap_info
jcmd 2125 Thread.print
~~~

GC.heap_info có mức tác động Medium. Thread.print cũng Medium và phụ thuộc số thread. Với ứng dụng có rất nhiều platform thread hoặc virtual thread, output có thể rất lớn.

### Command tác động cao

~~~bash
jcmd 2125 GC.class_histogram
jcmd 2125 GC.heap_dump /secure/diagnostics/heap.hprof
~~~

GC.class_histogram được JDK 26 xếp mức High. GC.heap_dump cũng High và phụ thuộc kích thước heap, nội dung heap. Mặc định heap dump yêu cầu full GC, trừ khi sử dụng tùy chọn -all để dump cả object không reachable.

Không chạy các command này liên tục theo chu kỳ ngắn trên production. Trước khi thực hiện, xác nhận có đủ dung lượng lưu trữ, quyền ghi, thời gian pause có thể chấp nhận và nơi lưu output được bảo vệ.

## 6. Những command thường dùng để kiểm tra trạng thái

### VM.version

In phiên bản JVM:

~~~bash
jcmd 2125 VM.version
~~~

Dùng để xác nhận JVM đích đang chạy đúng JDK release mong muốn.

### VM.uptime

In thời gian JVM đã chạy:

~~~bash
jcmd 2125 VM.uptime
~~~

Uptime giúp đặt các thông số như thread count, heap usage hoặc class loading vào bối cảnh thời gian hoạt động.

### VM.flags

In các VM flags và giá trị hiện tại:

~~~bash
jcmd 2125 VM.flags
~~~

Xem tất cả flags được JVM hỗ trợ:

~~~bash
jcmd 2125 VM.flags -all
~~~

Output có thể giúp xác định heap size, GC, diagnostic settings và các option đang có hiệu lực. Không chia sẻ output nếu nó tiết lộ đường dẫn, cấu hình hoặc thông tin nội bộ.

### VM.info

~~~bash
jcmd 2125 VM.info
~~~

In thông tin môi trường và trạng thái JVM.

### VM.command_line

~~~bash
jcmd 2125 VM.command_line
~~~

In command line đã dùng để khởi chạy JVM. Hãy xem đây là dữ liệu nhạy cảm vì một số ứng dụng có thể truyền token, password hoặc secret sai cách qua tham số dòng lệnh.

### VM.system_properties

~~~bash
jcmd 2125 VM.system_properties
~~~

In system properties của JVM. Output có thể có hàng trăm dòng. Các property như endpoint, đường dẫn file, user name hoặc giá trị bí mật do ứng dụng tự đặt có thể xuất hiện trong kết quả.

Chỉ thu thập những gì thực sự cần và lọc dữ liệu trước khi chia sẻ.

## 7. Dùng Thread.print để điều tra thread

Thread.print in platform threads và mounted virtual threads cùng stack trace.

~~~bash
jcmd 2125 Thread.print
~~~

Muốn in thêm thông tin lock của java.util.concurrent:

~~~bash
jcmd 2125 Thread.print -l
~~~

Command này hữu ích khi:

- Ứng dụng phản hồi chậm.
- Có thread bị BLOCKED lâu.
- Nhiều thread chờ cùng monitor.
- Nghi ngờ deadlock.
- Cần biết thread đang thực thi hoặc chờ ở method nào.

### Đọc thread dump

Một thread dump thường chứa:

- Tên thread.
- Thread state như RUNNABLE, WAITING, TIMED_WAITING hoặc BLOCKED.
- Stack trace.
- Monitor/lock đang giữ hoặc chờ khi có thông tin tương ứng.

Ví dụ minh họa:

~~~text
"main" #1 prio=5 os_prio=0
   java.lang.Thread.State: WAITING
    at java.lang.Object.wait(Native Method)

"pool-1-thread-1" #21
   java.lang.Thread.State: RUNNABLE
    at com.acme.service.ReportService.generate(ReportService.java:42)
~~~

Không kết luận deadlock chỉ từ một thread đang WAITING. Cần kiểm tra quan hệ lock, nhiều thread dump theo thời gian và trạng thái ứng dụng.

Với ứng dụng có nhiều thread, dump có thể rất lớn. Nếu mục tiêu là theo dõi xu hướng, JFR hoặc công cụ quan sát liên tục có thể phù hợp hơn việc thu thập thread dump lặp lại.

## 8. Kiểm tra heap và class histogram

### GC.heap_info

~~~bash
jcmd 2125 GC.heap_info
~~~

Cung cấp thông tin tổng quát về Java heap. Dùng để xem trạng thái heap trước khi quyết định có cần thu thập dữ liệu sâu hơn không.

### GC.class_histogram

~~~bash
jcmd 2125 GC.class_histogram
~~~

In thống kê object theo class trong Java heap. Các class có lượng instance hoặc dung lượng lớn thường xuất hiện ở đầu bảng.

JDK 26 xếp command này mức High. Chi phí phụ thuộc kích thước và nội dung heap; hãy chạy khi có lý do cụ thể và chuẩn bị cho tác động lên ứng dụng.

Có tùy chọn -all để kiểm tra cả object không reachable:

~~~bash
jcmd 2125 GC.class_histogram -all
~~~

Dùng -all chỉ khi hiểu sự khác nhau giữa object còn reachable và object đã không còn reachable. Kết quả có thể thay đổi đáng kể.

### GC.heap_dump

~~~bash
jcmd 2125 GC.heap_dump /secure/diagnostics/heap-2125.hprof
~~~

Tạo heap dump định dạng HPROF. Đây là dữ liệu hữu ích để điều tra memory leak, retained objects và object graph.

Tác động và rủi ro:

- JDK 26 xếp GC.heap_dump mức High.
- Theo mặc định, command yêu cầu full GC trừ khi chọn -all.
- File dump có thể gần bằng lượng dữ liệu heap cần ghi.
- Việc tạo dump có thể gây pause đáng kể.
- Dump có thể chứa token, password, dữ liệu người dùng, nội dung request và object nhạy cảm trong memory.

Trước khi dump:

1. Xác nhận đúng process và đúng môi trường.
2. Kiểm tra dung lượng đĩa.
3. Chọn thư mục chỉ nhóm được phép mới đọc.
4. Không ghi đè file cũ ngoài chủ đích.
5. Mã hóa hoặc bảo vệ file theo chính sách lưu trữ dữ liệu.
6. Đặt thời hạn retention và xóa an toàn khi hết mục đích điều tra.

Không gửi heap dump lên dịch vụ chia sẻ công khai hoặc đính kèm ticket không có kiểm soát truy cập.

## 9. Dùng Java Flight Recorder qua jcmd

JFR thu thập event về JVM và ứng dụng theo thời gian. jcmd hỗ trợ bắt đầu, kiểm tra, dump và dừng recording.

### Kiểm tra recording hiện có

~~~bash
jcmd 2125 JFR.check
~~~

### Bắt đầu recording ngắn

~~~bash
jcmd 2125 JFR.start name=incident settings=default duration=120s filename=/secure/diagnostics/incident.jfr
~~~

JDK cung cấp hai cấu hình phổ biến:

| Settings | Đặc điểm |
|---|---|
| default.jfc | Thu thập tập event định sẵn với overhead thấp; phù hợp recording liên tục |
| profile.jfc | Thu thập nhiều dữ liệu hơn nhưng overhead cao hơn; dùng trong thời gian ngắn khi cần chi tiết |

Nếu cần dừng recording trước khi hết thời lượng:

~~~bash
jcmd 2125 JFR.stop name=incident filename=/secure/diagnostics/incident-final.jfr
~~~

Nếu cần xuất snapshot trong khi recording vẫn tiếp tục:

~~~bash
jcmd 2125 JFR.dump name=incident filename=/secure/diagnostics/incident-snapshot.jfr
~~~

JFR.dump ghi dữ liệu ra file nhưng recording vẫn tiếp tục chạy.

### Giới hạn chi phí của JFR

- Chọn default.jfc cho mức thu thập nhẹ.
- Dùng profile.jfc trong thời gian ngắn và có mục tiêu cụ thể.
- Đặt duration, maxage hoặc maxsize để giới hạn thời gian và kích thước khi phù hợp.
- Không bật path-to-gc-roots tùy tiện; thu thập đường dẫn GC roots có thể gây pause và tốn thời gian.
- Bảo vệ file .jfr vì event có thể chứa thông tin về hệ thống, thread, class, I/O và hoạt động ứng dụng.

JFR có thể giúp điều tra CPU, allocation, GC, lock contention, I/O và các event theo thời gian mà một snapshot đơn lẻ không thể hiện được.

## 10. Native Memory Tracking qua jcmd

Native Memory Tracking (NMT) theo dõi các allocation nội bộ của HotSpot JVM. NMT không theo dõi đầy đủ native allocation của JNI hoặc thư viện native bên thứ ba.

NMT phải được bật khi JVM khởi chạy:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Hoặc bật mức detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

Không thể bật hoặc khởi động lại NMT bằng jcmd sau khi JVM đã chạy.

### Xem summary

~~~bash
jcmd 2125 VM.native_memory summary
~~~

### Thiết lập baseline

Sau khi ứng dụng warm up:

~~~bash
jcmd 2125 VM.native_memory baseline
~~~

### So sánh với baseline

~~~bash
jcmd 2125 VM.native_memory summary.diff
~~~

Hoặc xem detail diff nếu JVM được khởi động với NMT detail:

~~~bash
jcmd 2125 VM.native_memory detail.diff
~~~

NMT có thể giúp xác định native memory của JVM tăng ở nhóm nào, ví dụ Java Heap, Class, Thread, Code, GC hoặc Compiler.

### Chi phí NMT

Oracle ghi nhận bật NMT có thể làm hiệu năng JVM giảm khoảng 5–10% và tăng bộ nhớ tracking. Vì vậy, cần đánh giá chi phí trước khi bật trong production.

NMT chỉ theo dõi memory allocation của JVM/HotSpot trong phạm vi hỗ trợ. Nếu JNI hoặc native library bị leak, cần kết hợp công cụ hệ điều hành hoặc profiler native.

## 11. Command có thể thay đổi trạng thái JVM

Một số diagnostic command không chỉ đọc thông tin. Hãy xem kỹ trước khi chạy:

| Command | Hành động | Lưu ý |
|---|---|---|
| GC.run | Gọi System.gc() | Có thể tạo GC pause và thay đổi tải |
| GC.run_finalization | Gọi System.runFinalization() | Có thể kích hoạt finalization work |
| VM.set_flag | Thay đổi VM flag | Có thể thay đổi hành vi hoặc hiệu năng JVM |
| VM.log | Bật, tắt, đổi cấu hình hoặc rotate log | Thay đổi logging của process |
| JVMTI.agent_load | Nạp native JVMTI agent | Agent có thể can thiệp sâu vào JVM |
| ManagementAgent.start | Khởi chạy remote management agent | Mở thêm bề mặt quản trị; cần cấu hình mạng và xác thực |
| JFR.start | Bắt đầu recording | Thu thập event và sử dụng tài nguyên |
| JFR.stop | Dừng recording | Có thể ghi file hoặc loại bỏ recording data tùy tham số |

Không dùng các command này như bước kiểm tra mặc định. Trước khi chạy, xác định mục đích, người chịu trách nhiệm, thời gian hiệu lực, cách khôi phục và tác động tới dịch vụ.

Đặc biệt, không dùng ManagementAgent.start để mở JMX remote một cách tùy tiện. Nếu cần quản trị từ xa, phải có xác thực, TLS, giới hạn mạng và cấu hình quyền phù hợp.

## 12. Bảo vệ output và thông tin nhạy cảm

Diagnostic output cũng là dữ liệu production. Nó có thể tiết lộ:

- Đường dẫn nội bộ và tên host.
- Tham số JVM và system properties.
- Tên class, package, thread và method.
- Cấu trúc hệ thống, dependency và cấu hình runtime.
- Dữ liệu người dùng hoặc secret còn nằm trong heap.
- Dấu vết hoạt động ứng dụng trong JFR.

Các biện pháp nên áp dụng:

1. Ghi output vào thư mục có quyền truy cập giới hạn.
2. Không lưu dump trong web root hoặc thư mục chia sẻ công khai.
3. Không gửi nguyên VM.command_line hoặc VM.system_properties lên kênh không được bảo vệ.
4. Không để secret trong command-line arguments ngay từ đầu.
5. Giới hạn retention cho heap dump, thread dump và JFR file.
6. Mã hóa dữ liệu chẩn đoán khi lưu hoặc chuyển giao theo chính sách tổ chức.
7. Ẩn hoặc loại dữ liệu nhạy cảm trước khi chia sẻ.
8. Ghi lại ai thu thập, lúc nào, PID nào, bằng command nào và file được lưu ở đâu.

Quyền chạy jcmd cần được giới hạn theo nguyên tắc least privilege. Người có quyền attach có thể yêu cầu JVM cung cấp dữ liệu nhạy cảm hoặc thực hiện command có tác động lên process.

## 13. Dùng command file với -f

jcmd hỗ trợ đọc và thực thi các command từ file:

~~~bash
jcmd 2125 -f diagnostics.txt
~~~

Ví dụ nội dung file diagnostics.txt:

~~~text
VM.version
VM.uptime
VM.flags
GC.heap_info
~~~

Cách này hữu ích khi cần lặp lại một bộ kiểm tra đã được duyệt.

Quy tắc an toàn:

- Đọc toàn bộ file trước khi chạy.
- Chỉ cho phép command cần thiết.
- Không chạy file command nhận từ nguồn không tin cậy.
- Không thêm command thay đổi trạng thái nếu chưa được phê duyệt.
- Ghi rõ PID mục tiêu và người chịu trách nhiệm.
- Không dùng PID 0 để chạy file command trên mọi JVM.

Một file command không phải sandbox. Nếu file chứa GC.heap_dump, VM.set_flag hoặc JVMTI.agent_load, jcmd vẫn thực thi command đó trên process đích nếu JVM hỗ trợ.

## 14. Ví dụ Java 17+: chạy ứng dụng và kiểm tra bằng jcmd

Tạo cấu trúc:

~~~text
project/
  src/
    com/acme/DemoServer.java
  out/
~~~

Tệp src/com/acme/DemoServer.java:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;

public final class DemoServer {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/acme/DemoServer.java
~~~

Chạy ứng dụng:

~~~bash
java -cp out com.acme.DemoServer
~~~

Stdout:

~~~text
READY
~~~

Chương trình chờ vô thời hạn để giữ JVM hoạt động trong lúc thực hành. Mở terminal thứ hai, liệt kê process:

~~~bash
jcmd -l
~~~

Tìm PID của com.acme.DemoServer rồi thay vào các lệnh dưới đây:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 help Thread.print
jcmd 2125 Thread.print
~~~

PID 2125 chỉ là ví dụ. Dùng PID thực tế hiển thị trên máy của bạn.

Sau khi hoàn tất, quay lại terminal chạy DemoServer và nhấn Ctrl+C để dừng chương trình thử nghiệm.

Ví dụ này chỉ dùng các lệnh kiểm tra và thread dump. Không cần heap dump hoặc thay đổi VM flags để thực hành quy trình an toàn cơ bản.

## 15. Quy trình sử dụng jcmd an toàn trong production

1. **Xác định sự cố**: ghi rõ cần biết JVM version, thread state, heap, native memory hay event theo thời gian.
2. **Xác nhận môi trường**: host, container, service name, JDK release và thời điểm thu thập.
3. **Chọn đúng process**: dùng jcmd -l hoặc công cụ OS; xác nhận PID và command line.
4. **Kiểm tra danh tính process**: dùng VM.version, VM.uptime và VM.command_line nếu cần.
5. **Khám phá command**: chạy help và help cho command cụ thể trên JVM đích.
6. **Bắt đầu với command ít tác động**: VM.version, VM.uptime, VM.flags hoặc VM.info.
7. **Chỉ tăng mức thu thập khi có câu hỏi rõ ràng**: Thread.print, heap histogram, heap dump, JFR hoặc NMT.
8. **Ước lượng tác động**: pause, CPU, disk, dung lượng output và độ nhạy cảm của dữ liệu.
9. **Lưu output an toàn**: thư mục được bảo vệ, tên file có PID/thời gian và retention rõ ràng.
10. **Xác minh kết quả**: kiểm tra file được tạo, nội dung có đầy đủ và không chứa dữ liệu vượt quyền chia sẻ.
11. **Dừng recording hoặc cấu hình tạm**: dùng JFR.stop hoặc khôi phục logging/flag nếu đã thay đổi.
12. **Ghi lại thao tác**: command, người chạy, process, thời gian, tác động và nơi lưu output.

Nếu dịch vụ đang quá tải hoặc đã có sự cố nghiêm trọng, hãy ưu tiên command ít tác động và tránh tạo heap dump lớn trước khi đánh giá khả năng pause hoặc hết dung lượng.

## 16. Troubleshooting khi jcmd không hoạt động

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jcmd không được nhận diện | PATH không chứa thư mục bin của JDK | Kiểm tra JDK và PATH |
| Không thấy process trong jcmd -l | JVM ở Docker process riêng hoặc khác PID namespace | Dùng ps trong đúng namespace hoặc chạy jcmd bên trong container |
| Attach failed hoặc permission denied | Khác effective user/group hoặc quyền hệ điều hành | Chạy bằng tài khoản phù hợp và kiểm tra quyền |
| Không thể attach vào JVM | JVM được khởi chạy với DisableAttachMechanism | Kiểm tra startup flags; không thể bật attach từ jcmd |
| Unknown diagnostic command | JVM đích không cung cấp command đó | Chạy jcmd PID help để xem command khả dụng |
| Option không hợp lệ | Dùng cú pháp khác với command target | Chạy help cho command cụ thể và kiểm tra option/argument |
| PID không còn tồn tại | Process đã thoát hoặc PID thay đổi | Liệt kê lại process và xác nhận PID mới |
| Command chạy rất lâu | Heap lớn, nhiều thread hoặc command tác động cao | Dừng việc gửi lặp lại; đánh giá tác động và chờ command hiện tại |
| Không ghi được heap dump | Thư mục không có quyền ghi hoặc hết dung lượng | Chọn thư mục được phép và kiểm tra dung lượng |
| VM.native_memory không có dữ liệu | NMT chưa bật lúc JVM khởi chạy | Khởi động lại với NMT nếu chấp nhận được overhead |
| JFR.start không được hỗ trợ | JDK/provider hoặc JVM không hỗ trợ command tương ứng | Kiểm tra help và tính năng của JVM đích |
| Output chứa thông tin nhạy cảm | Command line, properties, heap hoặc recording có dữ liệu nội bộ | Hạn chế truy cập, lọc trước khi chia sẻ và áp dụng retention |

## 17. Checklist trước khi gửi diagnostic command

- [ ] Đã xác định đúng host, container và PID.
- [ ] Đã xác nhận process thuộc đúng service.
- [ ] Đã dùng tài khoản có effective user/group phù hợp.
- [ ] Đã kiểm tra jcmd help của JVM đích.
- [ ] Đã hiểu mức tác động của command.
- [ ] Đã tránh PID 0 và main-class selector khi có thể khớp nhiều process.
- [ ] Đã đánh giá CPU, pause, disk và dung lượng output.
- [ ] Đã chọn thư mục output được bảo vệ.
- [ ] Đã cân nhắc dữ liệu nhạy cảm trong command line, properties, thread dump, heap dump và JFR.
- [ ] Đã đặt giới hạn thời gian hoặc kích thước recording khi phù hợp.
- [ ] Đã biết cách dừng recording hoặc khôi phục thay đổi.
- [ ] Đã ghi lại command, người chạy, thời gian và kết quả.

## 18. Ghi nhớ

- jcmd gửi diagnostic command tới JVM đang chạy; nó không phải remote debugger.
- jcmd phải chạy trên cùng máy và cùng effective user/group với JVM đích.
- jcmd -l liệt kê Java process, nhưng không liệt kê JVM trong Docker process riêng biệt.
- Dùng PID cụ thể; main-class có thể khớp nhiều process và PID 0 gửi command tới mọi JVM khả dụng.
- Luôn dùng help và help command để xác nhận lệnh, option và argument trên JVM đích.
- VM.version, VM.uptime, VM.flags và VM.info là các bước kiểm tra ít tác động.
- Thread.print có mức tác động Medium; GC.class_histogram và GC.heap_dump có mức High trong manual JDK 26.
- Heap dump có thể yêu cầu full GC và chứa dữ liệu nhạy cảm trong memory.
- JFR default.jfc có overhead thấp; profile.jfc thu thập nhiều dữ liệu hơn và có overhead cao hơn.
- NMT phải bật lúc khởi chạy JVM; bật NMT có thể làm giảm hiệu năng khoảng 5–10%.
- GC.run, VM.set_flag, VM.log, JVMTI.agent_load và ManagementAgent.start có thể thay đổi trạng thái hoặc bề mặt quản trị của process.
- Diagnostic output là dữ liệu nhạy cảm; bảo vệ quyền truy cập, nơi lưu và thời hạn retention.
- Dùng jcmd có kế hoạch: đúng process, đúng command, đúng mức tác động và đúng mục đích.

## Tài liệu tham khảo chính thức

- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The java Command: DisableAttachMechanism — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Native Memory Tracking — JDK 26](https://docs.oracle.com/en/java/javase/26/vm/java-virtual-machine-guide.pdf)
- [Troubleshooting Memory Leaks — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)