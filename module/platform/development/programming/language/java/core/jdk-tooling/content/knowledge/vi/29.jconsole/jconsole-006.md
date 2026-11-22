# Theo dõi Thread tab trong JConsole

**JConsole** là công cụ giao diện đồ họa dựa trên Java Management Extensions (JMX), dùng để theo dõi hoạt động và tài nguyên của một Java Virtual Machine (JVM). Tab **Threads** tập trung vào tình trạng thread: số thread đang sống theo thời gian, danh sách thread hiện hoạt động, trạng thái của từng thread, stack trace và khả năng phát hiện deadlock.

Quy trình cơ bản:

1. Khởi chạy JConsole từ JDK.
2. Kết nối tới JVM local hoặc JMX agent remote.
3. Mở tab Threads.
4. Quan sát biểu đồ live/peak thread.
5. Lọc danh sách theo tên thread.
6. Chọn thread để xem state và stack trace.
7. Dùng Detect Deadlock khi nghi ngờ deadlock.
8. Đối chiếu nhiều thời điểm và dùng jstack/jcmd khi cần chẩn đoán sâu hơn.

JConsole là công cụ quan sát. Nó không tự sửa thread bị block, mở latch, giải phóng lock hoặc khắc phục deadlock.

## 1. Thread tab hiển thị những gì?

Sau khi kết nối thành công, JConsole có các tab Overview, Memory, Threads, Classes, VM và MBeans. Chọn **Threads** để xem hoạt động thread của JVM.

Theo tài liệu JDK 24, Threads tab có ba vùng quan trọng:

- **Biểu đồ số thread:** thể hiện số live thread theo thời gian và mức peak.
- **Danh sách Threads:** liệt kê các thread đang hoạt động.
- **Chi tiết thread được chọn:** hiển thị tên, state và stack trace.

Ở danh sách thread, nhập một chuỗi vào ô Filter để chỉ giữ lại các thread có tên chứa chuỗi đó. Chọn tên thread để xem thông tin ở khung bên cạnh.

Biểu đồ trong JDK 24 có hai đường:

- Đường đỏ: Peak number of threads, số live thread cao nhất đã đạt được kể từ khi JVM khởi động.
- Đường xanh: Number of live threads, số thread hiện đang sống tại từng thời điểm.

Các số liệu daemon và total started có thể xem trong VM Summary hoặc qua Threading MXBean ở tab MBeans.

## 2. Hiểu các chỉ số thread

Các chỉ số giúp phân biệt số thread hiện tại, mức cao nhất và tổng số thread đã được tạo.

| Chỉ số | Ý nghĩa |
|---|---|
| Live threads | Số thread daemon và non-daemon hiện đang sống |
| Peak | Số live thread cao nhất kể từ khi JVM khởi động hoặc kể từ lần reset peak |
| Daemon threads | Số daemon thread hiện đang sống |
| Total threads started | Tổng số thread đã được start kể từ khi JVM khởi động, bao gồm cả thread đã kết thúc |

Ví dụ:

~~~text
Live threads:          24
Peak:                  41
Daemon threads:        18
Total threads started: 126
~~~

Diễn giải:

- JVM hiện có 24 thread đang sống.
- Trước đó JVM từng đạt 41 live thread.
- Trong 24 thread hiện tại có 18 daemon thread.
- Tổng cộng 126 thread đã từng được start, kể cả thread đã kết thúc.

Total threads started thường không giảm vì thread kết thúc không làm giảm bộ đếm tích lũy. Live threads có thể tăng hoặc giảm khi thread được tạo và kết thúc.

### Live threads

Live threads là số thread hiện đang tồn tại trong JVM, gồm daemon và non-daemon. Thread có thể đang RUNNABLE, BLOCKED, WAITING hoặc TIMED_WAITING mà vẫn được tính là live.

Không đồng nhất live thread với thread đang sử dụng CPU. Một worker đang chờ queue vẫn là live thread.

### Peak

Peak giúp nhận diện đỉnh tải thread. Nếu live threads hiện thấp nhưng peak cao, ứng dụng có thể từng tạo một đợt thread lớn rồi các thread đã kết thúc.

Peak không tự cho biết nguyên nhân. Hãy đối chiếu với thời điểm tăng request, batch job, deploy, retry hoặc tải nền.

### Daemon threads

Daemon thread là thread nền không giữ JVM tiếp tục sống khi mọi non-daemon thread đã kết thúc. Các ví dụ thường gặp là một số thread phục vụ runtime, scheduler hoặc nền tảng.

Daemon không có nghĩa là thread không quan trọng. Một daemon thread vẫn có thể tiêu thụ CPU, giữ tài nguyên, chờ I/O hoặc gặp deadlock. Khi JVM thoát, daemon thread có thể bị dừng cùng quá trình shutdown.

### Total threads started

Chỉ số này bao gồm cả thread đã kết thúc. Nếu total started tăng nhanh nhưng live thread ổn định, ứng dụng có thể tạo và kết thúc nhiều thread ngắn hạn. Đây có thể là thiết kế hợp lệ hoặc dấu hiệu tạo thread quá thường xuyên.

Nếu cả live và total started tăng liên tục, cần kiểm tra thread leak, executor không giới hạn hoặc tác vụ tạo thread không được kiểm soát.

## 3. Lọc và chọn thread

Danh sách Threads có thể dài vì JVM có nhiều thread runtime, GC, compiler, cleaner, JMX và thread ứng dụng.

Cách lọc:

1. Mở tab Threads.
2. Nhập một phần tên vào Filter.
3. Danh sách chỉ còn những thread có tên chứa chuỗi đã nhập.
4. Chọn một thread để xem chi tiết.
5. Xóa filter để trở lại danh sách đầy đủ.

Ví dụ tên thread:

~~~text
http-nio-8080-exec-1
http-nio-8080-exec-2
pool-3-thread-1
scheduler-1
demo-WAITING-latch
demo-BLOCKED-monitor
~~~

Nhập http-nio-8080 để tập trung vào worker của web server; nhập pool-3 để xem một nhóm executor; nhập demo- để tìm thread của bài lab.

Đặt tên thread có ý nghĩa trong ứng dụng giúp việc quan sát và điều tra dễ hơn. Với ExecutorService, có thể dùng ThreadFactory tùy chỉnh để đặt tên theo chức năng hoặc nhóm worker.

### Chi tiết thread được chọn

Khi chọn một thread, JConsole hiển thị:

- Thread name.
- Thread state.
- Stack trace tại thời điểm lấy thông tin.

Stack trace cho biết thread đang thực hiện hoặc chờ ở method nào. Tìm frame đầu tiên thuộc package ứng dụng để xác định vị trí code nghiệp vụ.

Ví dụ:

~~~text
Name: demo-WAITING-latch
State: WAITING

Stack trace:
    at jdk.internal.misc.Unsafe.park(...)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.CountDownLatch.await(...)
    at com.example.JConsoleThreadTabDemo.await(...)
~~~

Diễn giải: thread đang chờ CountDownLatch. Tìm nơi gọi countDown() trên latch tương ứng để biết điều kiện đánh thức có được thực hiện hay không.

Stack trace là snapshot. Nếu cần lưu toàn bộ thread dump hoặc phân tích nhiều thread cùng lúc, dùng jstack hoặc jcmd Thread.print.

## 4. Đọc trạng thái thread

Java định nghĩa sáu trạng thái trong Thread.State:

| Trạng thái | Ý nghĩa |
|---|---|
| NEW | Thread đã tạo nhưng chưa start |
| RUNNABLE | Thread đang chạy hoặc sẵn sàng được scheduler chạy |
| BLOCKED | Thread chờ lấy intrinsic monitor |
| WAITING | Thread chờ một hành động khác mà không có timeout |
| TIMED_WAITING | Thread chờ trong khoảng thời gian có giới hạn |
| TERMINATED | Thread đã kết thúc |

JConsole liệt kê các thread đang hoạt động, vì vậy NEW và TERMINATED thường không xuất hiện trong danh sách live thread.

### RUNNABLE

RUNNABLE không đảm bảo thread đang dùng CPU tại đúng thời điểm quan sát. Thread có thể đang được scheduler cấp CPU, chờ CPU hoặc thực hiện native operation.

Nếu một thread RUNNABLE lâu và stack trace không thay đổi, hãy kiểm tra vòng lặp CPU, xử lý dữ liệu lớn hoặc native call. Có thể đối chiếu CPU time qua Threading MXBean.

### BLOCKED

BLOCKED có nghĩa thread đang chờ lấy intrinsic monitor để vào synchronized block hoặc synchronized method.

Ví dụ:

~~~java
synchronized (sharedLock) {
    updateState();
}
~~~

Nếu thread khác đang giữ sharedLock, thread này có thể ở BLOCKED. Xem stack trace và thông tin lock qua Threading MXBean hoặc jstack -l để xác định owner.

### WAITING

WAITING là trạng thái chờ vô thời hạn, thường do:

- Object.wait() không có timeout.
- Thread.join() không có timeout.
- CountDownLatch.await().
- Condition.await().
- LockSupport.park().
- Blocking queue hoặc synchronizer đang chờ dữ liệu/tín hiệu.

WAITING không tự động có nghĩa là treo. Worker chờ queue rỗng có thể đang hoạt động đúng.

### TIMED_WAITING

TIMED_WAITING là chờ có timeout, thường do:

- Thread.sleep().
- Object.wait(timeout).
- Thread.join(timeout).
- LockSupport.parkNanos().
- Một số thao tác đồng bộ có timeout.

Một thread ngủ giữa các lần retry có thể ở TIMED_WAITING. Kiểm tra timeout, backoff và stack trace trước khi kết luận có lỗi.

### Vì sao không chỉ nhìn state?

Nhiều thread ở WAITING có thể là bình thường trong một thread pool. Ngược lại, một thread BLOCKED duy nhất có thể gây nghẽn toàn bộ request nếu nó giữ lock quan trọng.

Hãy kết hợp state, tên thread, stack trace, lock owner, CPU time và xu hướng qua nhiều thời điểm.

## 5. Phát hiện deadlock bằng Detect Deadlock

Deadlock là tình trạng các thread giữ tài nguyên mà thread khác trong chu trình đang cần, khiến không thread nào có thể tiếp tục.

Ví dụ:

- Thread A giữ lock X và chờ lock Y.
- Thread B giữ lock Y và chờ lock X.
- A không thể lấy Y cho tới khi B nhả Y.
- B không thể nhả Y vì đang chờ A nhả X.

Trong Threads tab, chọn **Detect Deadlock**. Nếu phát hiện deadlock, JConsole mở tab mới để hiển thị các thread thuộc chu trình deadlock.

JConsole phát hiện chu trình liên quan tới:

- Object monitor locks, ví dụ synchronized.
- Ownable synchronizers, ví dụ các lock dựa trên AbstractQueuedSynchronizer như ReentrantLock.

Khả năng phát hiện phụ thuộc JVM và hỗ trợ của Threading MXBean.

### Cách điều tra kết quả

1. Chọn Detect Deadlock.
2. Mở tab deadlock được tạo.
3. Chọn từng thread trong chu trình.
4. Đọc state và stack trace.
5. Xác định lock thread đang chờ.
6. Xác định thread đang giữ lock đó.
7. Lần theo toàn bộ chu trình để tìm thứ tự lấy lock.
8. Đối chiếu source code và thiết kế đồng bộ.

Detect Deadlock chỉ phát hiện và hiển thị bằng chứng. JConsole không tự giải phóng lock hoặc sửa code.

### Deadlock khác với thread chờ lâu

Thread chờ CountDownLatch mà không ai gọi countDown() có thể bị kẹt logic, nhưng không nhất thiết là deadlock monitor. Tương tự, thread chờ database hoặc HTTP response có thể chờ rất lâu mà không tạo chu trình lock.

Nếu Detect Deadlock không tìm thấy chu trình, ứng dụng vẫn có thể gặp starvation, thread pool exhaustion, I/O hang hoặc lỗi tín hiệu đồng bộ.

## 6. Threading MXBean trong tab MBeans

JConsole sử dụng nền tảng JMX. Nhiều thông tin về thread được cung cấp bởi Threading MXBean, có ObjectName:

~~~text
java.lang:type=Threading
~~~

Mở tab MBeans, tìm java.lang rồi chọn Threading. Tùy phiên bản JConsole, cây MBeans có thể được hiển thị theo nhóm object name.

Các thuộc tính hữu ích:

| Attribute | Ý nghĩa |
|---|---|
| ThreadCount | Số live thread hiện tại |
| PeakThreadCount | Số live thread cao nhất |
| DaemonThreadCount | Số daemon thread hiện tại |
| TotalStartedThreadCount | Tổng số thread đã start |
| CurrentThreadCpuTime | CPU time của thread hiện tại |
| CurrentThreadUserTime | User-mode CPU time của thread hiện tại |
| ThreadContentionMonitoringEnabled | Trạng thái bật/tắt contention monitoring |

Các operation quan trọng:

| Operation | Chức năng |
|---|---|
| getThreadInfo | Lấy tên, state, stack trace và thông tin lock của thread |
| getThreadCpuTime | Lấy CPU time của một thread |
| findMonitorDeadlockedThreads | Tìm deadlock liên quan tới object monitor |
| findDeadlockedThreads | Tìm deadlock liên quan tới monitor và ownable synchronizer |
| resetPeakThreadCount | Đặt lại bộ đếm peak thread |

Không phải mọi thuộc tính hoặc operation đều khả dụng trong mọi JVM. Hãy xem MBeanInfo và kết quả thực tế của runtime đang kết nối.

### CPU time khác với elapsed time

CPU time là thời gian CPU mà thread đã sử dụng. Elapsed time là thời gian thực tế trôi qua.

Một thread chờ network 30 giây có thể có elapsed time lớn nhưng CPU time rất nhỏ. Một thread chạy vòng lặp tính toán có thể có CPU time tăng nhanh.

Nếu ThreadMXBean không hỗ trợ hoặc chưa bật CPU time measurement, giá trị có thể không khả dụng. Không suy luận CPU usage chỉ từ thread state.

## 7. So sánh nhiều snapshot

Threads tab cập nhật theo thời gian. Một lần xem chỉ phản ánh trạng thái ở một thời điểm.

Khi điều tra:

1. Quan sát danh sách và biểu đồ hiện tại.
2. Ghi nhận tên, state và stack trace của thread đáng chú ý.
3. Chờ một khoảng thời gian phù hợp với workload.
4. Quan sát lại cùng thread.
5. So sánh state và stack trace.
6. Nếu thread luôn chờ cùng một điều kiện hoặc cùng lock, tìm producer hoặc lock owner.
7. Nếu thread chuyển qua các stack frame khác nhau, nó có thể vẫn đang tiến triển.

Ví dụ:

| Snapshot | Thread | State | Stack |
|---|---|---|---|
| T1 | worker-1 | WAITING | BlockingQueue.take |
| T2 | worker-1 | WAITING | BlockingQueue.take |
| T3 | worker-1 | RUNNABLE | OrderService.process |

Worker có thể đã nhận được công việc giữa T2 và T3. Việc thấy WAITING trong hai snapshot không đủ để kết luận thread bị treo.

### Dấu hiệu thread leak

Một số dấu hiệu cần điều tra:

- Live threads tăng liên tục và không giảm sau khi tải kết thúc.
- Peak tăng qua từng đợt tải.
- Nhiều thread cùng nhóm tên nhưng không kết thúc.
- Thread pool có số worker vượt cấu hình mong đợi.
- Nhiều thread chờ cùng một dịch vụ hoặc lock.
- Total started tăng rất nhanh vì tạo thread mới cho mỗi request.

Đối chiếu số thread với request rate, queue depth, executor configuration, deploy và workload. Không kết luận leak chỉ vì số live thread cao; server có thể được cấu hình để giữ một pool worker lớn.

## 8. Lưu dữ liệu biểu đồ

JConsole cho phép lưu dữ liệu biểu đồ thành CSV:

1. Nhấp chuột phải lên biểu đồ.
2. Chọn Save data as...
3. Chọn vị trí và tên file CSV.
4. Mở CSV bằng spreadsheet hoặc công cụ phân tích.

CSV có cột thời gian và một hoặc nhiều cột giá trị. Có thể dùng để so sánh số live thread và peak trong một giai đoạn.

Khi lưu dữ liệu, ghi nhận thời điểm, JVM, môi trường, tải ứng dụng và khoảng thời gian quan sát để tránh diễn giải biểu đồ tách rời bối cảnh.

## 9. Kết nối JConsole tới JVM local

JConsole nằm trong thư mục bin của JDK. Kiểm tra executable:

Windows PowerShell:

~~~powershell
Get-Command jconsole
where.exe jconsole
~~~

Linux/macOS:

~~~bash
command -v jconsole
~~~

Khởi chạy giao diện:

~~~bash
jconsole
~~~

JConsole hiển thị danh sách JVM local mà công cụ có thể truy cập. Chọn JVM cần theo dõi rồi bấm Connect.

Nếu đã biết PID:

~~~bash
jconsole 12345
~~~

Thay 12345 bằng PID thực tế.

### Điều kiện local monitoring

Theo tài liệu JDK 24:

- JConsole và JVM đích phải chạy dưới cùng user ID.
- Kết nối local sử dụng cơ chế management/Attach và quyền file của hệ điều hành.
- Một JVM có thể được attach để bật management agent động nếu JVM hỗ trợ.
- JVM không attachable và chưa bật management agent có thể không kết nối được.
- JVM khởi chạy với DisableAttachMechanism có thể chặn kết nối local dựa trên attach.

Nếu không thấy JVM trong danh sách, kiểm tra PID, user, JDK, container namespace và khả năng attach.

### Kết nối bằng PID không đồng nghĩa với quyền root

Dùng đúng tài khoản vận hành sở hữu JVM là cách thông thường. Không tự động chạy JConsole bằng Administrator/root để xử lý mọi lỗi kết nối. Hãy xác định chính sách quyền của process và môi trường trước.

## 10. Kết nối JConsole tới JVM remote bằng JMX

Để theo dõi JVM ở máy khác, ứng dụng cần bật JMX remote agent và mở cổng quản lý theo cấu hình.

Ví dụ cấu hình rõ ràng authentication và SSL:

~~~bash
java \
    -Dcom.sun.management.jmxremote.port=9010 \
    -Dcom.sun.management.jmxremote.rmi.port=9010 \
    -Dcom.sun.management.jmxremote.authenticate=true \
    -Dcom.sun.management.jmxremote.ssl=true \
    -jar app.jar
~~~

Sau đó trên máy quản trị:

~~~bash
jconsole app-server.example.com:9010
~~~

Nếu JMX agent yêu cầu xác thực, JConsole sẽ yêu cầu username và password trong hộp thoại kết nối.

Cần cấu hình password/access file, TLS keystore/truststore và firewall theo tài liệu JMX của JDK. Chỉ cho phép kết nối từ mạng quản trị hoặc host được cấp quyền.

Không mở JMX remote không xác thực ra Internet. Người có quyền truy cập JMX có thể đọc dữ liệu quản trị nhạy cảm và thực hiện operation trên MBeans. Bảo vệ cổng JMX như một giao diện quản trị production.

### Remote JMX và local attach khác nhau

| Local | Remote |
|---|---|
| Kết nối tới JVM cùng máy | Kết nối qua JMX agent |
| Dựa trên quyền local/Attach | Dựa trên JMX connector, network, authentication và TLS |
| Thường cần cùng user ID | Dùng credentials được cấu hình cho JMX |
| Hữu ích cho development | Phù hợp hơn để tách công cụ khỏi JVM production |

## 11. JConsole có thể ảnh hưởng tới ứng dụng không?

JConsole liên tục truy vấn MBean để cập nhật biểu đồ và thông tin. Việc giám sát có overhead về CPU, thread và network.

Oracle khuyến cáo local monitoring hữu ích cho development/prototype nhưng không khuyến nghị trong production vì chính JConsole tiêu thụ tài nguyên đáng kể. Remote monitoring giúp tách tài nguyên giao diện khỏi máy đang chạy ứng dụng.

Thực hành:

- Chỉ mở các tab và biểu đồ cần thiết.
- Tránh kết nối quá nhiều JConsole tới cùng một JVM.
- Không chạy thao tác chẩn đoán nặng liên tục.
- Chọn khoảng quan sát vừa đủ cho sự cố.
- Dùng remote monitoring từ máy quản trị khi phù hợp.
- So sánh metrics trước và trong khi giám sát để nhận diện overhead.

JConsole là công cụ quan sát trực tiếp, không phải hệ thống metrics dài hạn hoặc alerting thay thế monitoring platform.

## 12. Troubleshooting Thread tab

### Không kết nối được JVM local

Kiểm tra:

- JConsole và JVM có cùng user ID không?
- PID còn tồn tại không?
- JVM có hỗ trợ Attach không?
- Có dùng DisableAttachMechanism không?
- JConsole có cùng môi trường JDK phù hợp không?
- JVM có nằm trong container hoặc process namespace khác không?

### JVM hiển thị màu xám hoặc không thể chọn

Có thể JVM chưa bật management agent và cũng không hỗ trợ dynamic attach. Khởi chạy lại ứng dụng với cấu hình management agent phù hợp hoặc dùng JMX remote đã được bảo vệ.

### Thread list không hiển thị thread mong muốn

Thread có thể đã kết thúc, tên khác với dự kiến hoặc filter đang loại bỏ nó. Xóa Filter và quan sát lại. Kiểm tra thêm bằng jstack hoặc jcmd Thread.print.

### Không thấy thread state thay đổi

Có thể thread đang chờ điều kiện dài hạn hoặc biểu đồ chưa có đủ thời gian quan sát. Chọn thread, xem stack trace và so sánh nhiều snapshot. Kiểm tra producer, queue, latch, future, timeout hoặc lock owner.

### Detect Deadlock không tìm thấy gì

Không có deadlock cycle được phát hiện không có nghĩa ứng dụng không bị treo. Có thể là I/O hang, starvation, thread pool exhaustion, thiếu tín hiệu hoặc deadlock logic ngoài các lock mà JVM phát hiện được.

### Remote JMX connection refused

Kiểm tra host/port, JMX agent đã bật, RMI port, firewall, routing, credentials và TLS certificate. Không tắt authentication/SSL để thử nhanh trên mạng không tin cậy.

### Stack trace không đủ sâu

Dùng jstack hoặc jcmd Thread.print để lấy thread dump đầy đủ hơn. Chọn cùng PID và ghi nhận thời điểm dump để so sánh với ảnh chụp JConsole.

## 13. Kết hợp Threads tab với jstack và jcmd

JConsole phù hợp để quan sát xu hướng và chọn thread. Khi cần lưu bằng chứng đầy đủ, dùng công cụ dòng lệnh.

Liệt kê JVM:

~~~bash
jcmd -l
~~~

In thread dump:

~~~bash
jcmd 12345 Thread.print
~~~

In thêm thông tin lock:

~~~bash
jcmd 12345 Thread.print -l
~~~

Hoặc:

~~~bash
jstack -l 12345
~~~

Thay 12345 bằng PID thực tế.

| Công cụ | Mục tiêu |
|---|---|
| JConsole Threads | Theo dõi live/peak, lọc thread, xem state và stack trace |
| Detect Deadlock | Phát hiện chu trình deadlock |
| Threading MXBean | Đọc thread metrics, stack info, CPU time và deadlock operations |
| jstack -l | Lấy thread dump kèm lock information |
| jcmd Thread.print -l | Lấy thread dump bằng diagnostic command |

JConsole không thay thế thread dump trong các cuộc điều tra cần lưu trữ, so sánh hoặc phân tích offline.

## 14. Ví dụ Java 17+ hoàn chỉnh: tạo các trạng thái để quan sát

Chương trình sau tạo các thread có tên dễ lọc trong JConsole:

- demo-WAITING-latch: chờ CountDownLatch không được mở.
- demo-TIMED_WAITING-sleep: ngủ có timeout.
- demo-monitor-owner: giữ một synchronized monitor.
- demo-BLOCKED-monitor: chờ monitor mà owner đang giữ.
- demo-daemon-WAITING: daemon thread chờ latch.
- demo-short-lived: thread kết thúc nhanh để tăng total threads started.

### JConsoleThreadTabDemo.java

~~~java
package com.example;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class JConsoleThreadTabDemo {
    private static final Object LOCK = new Object();
    private static final CountDownLatch OWNER_HAS_LOCK = new CountDownLatch(1);
    private static final CountDownLatch NEVER_RELEASED = new CountDownLatch(1);

    private JConsoleThreadTabDemo() {
    }

    public static void main(String[] args) throws Exception {
        Thread waiting = new Thread(
                () -> await(NEVER_RELEASED), "demo-WAITING-latch");

        Thread timed = new Thread(
                () -> sleepFor(120_000), "demo-TIMED_WAITING-sleep");

        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                OWNER_HAS_LOCK.countDown();
                sleepFor(120_000);
            }
        }, "demo-monitor-owner");

        Thread blocked = new Thread(() -> {
            await(OWNER_HAS_LOCK);
            synchronized (LOCK) {
                System.out.println("demo-BLOCKED acquired monitor");
            }
        }, "demo-BLOCKED-monitor");

        Thread daemon = new Thread(
                () -> await(NEVER_RELEASED), "demo-daemon-WAITING");
        daemon.setDaemon(true);

        waiting.start();
        timed.start();
        owner.start();
        blocked.start();
        daemon.start();

        OWNER_HAS_LOCK.await();
        Thread.sleep(500);

        Thread shortLived = new Thread(() -> { }, "demo-short-lived");
        shortLived.start();
        shortLived.join();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println(
                "JConsoleThreadTabDemo ready; pid=" + ProcessHandle.current().pid());
        System.out.println("Live threads=" + bean.getThreadCount());
        System.out.println("Daemon threads=" + bean.getDaemonThreadCount());
        System.out.println("Peak threads=" + bean.getPeakThreadCount());
        System.out.println(
                "Total threads started=" + bean.getTotalStartedThreadCount());
        System.out.println("demo-WAITING-latch=" + waiting.getState());
        System.out.println("demo-TIMED_WAITING-sleep=" + timed.getState());
        System.out.println("demo-BLOCKED-monitor=" + blocked.getState());
        System.out.println("demo-daemon-WAITING daemon=" + daemon.isDaemon());

        Thread.sleep(120_000);
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static void sleepFor(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

### Biên dịch

Từ thư mục gốc dự án:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/JConsoleThreadTabDemo.java
~~~

### Chạy ứng dụng

~~~bash
java -cp build/classes com.example.JConsoleThreadTabDemo
~~~

Output mẫu đã quan sát trên JDK 24.0.2:

~~~text
JConsoleThreadTabDemo ready; pid=37548
Live threads=12
Daemon threads=7
Peak threads=13
Total threads started=13
demo-WAITING-latch=WAITING
demo-TIMED_WAITING-sleep=TIMED_WAITING
demo-BLOCKED-monitor=BLOCKED
demo-daemon-WAITING daemon=true
~~~

PID và các bộ đếm có thể khác trên máy khác hoặc sau khi JConsole kết nối vì JVM, GC và management agent có thể tạo thêm thread.

### Mở JConsole

Trong terminal thứ hai, dùng cùng tài khoản hệ điều hành:

~~~bash
jconsole 37548
~~~

Thay 37548 bằng PID được chương trình in ra.

Chọn tab Threads. Trong Filter, nhập demo- để chỉ xem các thread lab. Chọn từng thread và kiểm tra state cùng stack trace.

Quan sát:

- demo-WAITING-latch ở WAITING, stack trace đi qua CountDownLatch.await.
- demo-TIMED_WAITING-sleep ở TIMED_WAITING, stack trace đi qua Thread.sleep.
- demo-BLOCKED-monitor ở BLOCKED, stack trace đang chờ vào synchronized block.
- demo-monitor-owner giữ monitor và đang sleep.
- demo-daemon-WAITING là daemon thread.

Nếu chọn thread BLOCKED và xem chi tiết lock qua MBeans hoặc thread dump, object monitor mà nó chờ sẽ khớp với monitor do demo-monitor-owner giữ.

Chương trình tự kết thúc sau khoảng hai phút. Có thể nhấn Ctrl+C ở terminal chạy ứng dụng để dừng lab.

## 15. Ví dụ deadlock để thử Detect Deadlock

Đoạn code sau tạo hai thread lấy hai monitor theo thứ tự ngược nhau.

~~~java
package com.example;

public final class JConsoleDeadlockDemo {
    private static final Object A = new Object();
    private static final Object B = new Object();

    public static void main(String[] args) throws Exception {
        Thread first = new Thread(() -> {
            synchronized (A) {
                pause();
                synchronized (B) {
                    System.out.println("first acquired both");
                }
            }
        }, "demo-deadlock-A-then-B");

        Thread second = new Thread(() -> {
            synchronized (B) {
                pause();
                synchronized (A) {
                    System.out.println("second acquired both");
                }
            }
        }, "demo-deadlock-B-then-A");

        first.start();
        second.start();
        Thread.sleep(120_000);
    }

    private static void pause() {
        try {
            Thread.sleep(500);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -d build/classes \
    src/com/example/JConsoleDeadlockDemo.java

java -cp build/classes com.example.JConsoleDeadlockDemo
~~~

Kết nối JConsole tới PID của chương trình, mở Threads và chọn Detect Deadlock. JConsole sẽ hiển thị chu trình deadlock nếu JVM phát hiện được.

Ví dụ này cố ý tạo deadlock và không tự kết thúc. Chỉ chạy trong lab, không chạy trong ứng dụng production.

Cách sửa điển hình là quy định thứ tự lấy lock thống nhất, ví dụ mọi thread luôn lấy A trước B. Cũng có thể giảm số lock, tránh lock lồng nhau hoặc dùng concurrency utility phù hợp.

## 16. Checklist điều tra bằng Thread tab

- [ ] Đã kết nối đúng JVM và ghi nhận PID.
- [ ] Đã xác nhận môi trường local/remote và danh tính truy cập.
- [ ] Đã quan sát live thread và peak theo thời gian.
- [ ] Đã phân biệt live, daemon, peak và total started.
- [ ] Đã lọc đúng nhóm thread theo tên.
- [ ] Đã chọn thread đáng chú ý và đọc state.
- [ ] Đã xác định frame đầu tiên thuộc code ứng dụng.
- [ ] Đã phân biệt BLOCKED, WAITING và TIMED_WAITING.
- [ ] Đã xác định lock owner khi có monitor contention.
- [ ] Đã chạy Detect Deadlock nếu nghi ngờ deadlock.
- [ ] Đã so sánh nhiều snapshot trước khi kết luận thread bị kẹt.
- [ ] Đã kiểm tra CPU time hoặc dùng thread dump khi cần.
- [ ] Đã lưu CSV/thread dump nếu cần bằng chứng.
- [ ] Đã bảo vệ thông tin trong stack trace và JMX credentials.

## 17. Tóm tắt thao tác

~~~text
jconsole
jconsole <pid>
jconsole hostName:portNum
~~~

Trong JConsole:

1. Kết nối JVM local hoặc remote.
2. Chọn Threads.
3. Theo dõi đường live và peak.
4. Lọc danh sách bằng tên thread.
5. Chọn thread để đọc state và stack trace.
6. Chọn Detect Deadlock khi cần kiểm tra deadlock.
7. Mở MBeans > Threading để xem các operation và attribute nâng cao.
8. Dùng jstack/jcmd để lấy thread dump đầy đủ khi cần.

Threads tab giúp nhìn thấy hành vi concurrency đang diễn ra trong JVM. Hãy đọc biểu đồ cùng danh sách thread, hiểu ý nghĩa của từng state và dùng stack trace để tìm vị trí code đang chờ. Kết hợp Detect Deadlock, Threading MXBean và nhiều snapshot theo thời gian sẽ giúp phân biệt tải thread bình thường, thread leak, contention và deadlock.

## Tài liệu tham khảo

- [Using JConsole — Java SE 24](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [The jconsole Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jconsole.html)
- [ThreadMXBean API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Thread.State API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)
- [Remote Monitoring and Management — Java SE 24](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html)
