# PID và quyền truy cập với jcmd

`jcmd` gửi diagnostic command tới một JVM đang chạy. Trước khi chạy lệnh, cần chọn đúng process ID (PID), xác định JVM đó có cho phép Attach API hay không và bảo đảm tài khoản đang chạy `jcmd` có quyền attach vào process đích.

Khả năng attach phụ thuộc cả môi trường của process đích lẫn quyền ở hệ điều hành. `jcmd` không phải công cụ điều khiển JVM từ xa qua mạng: nó phải chạy trên cùng máy với JVM và theo Oracle JDK 21, phải dùng cùng effective user và group identifiers đã khởi chạy JVM.

## 1. PID là gì và vì sao cần chọn đúng?

PID (Process ID) là mã định danh của một process do hệ điều hành cấp. Một JVM đang chạy trong process Java có PID riêng. `jcmd` dùng PID này để gửi yêu cầu chẩn đoán tới đúng JVM.

PID không phải:

- Java thread ID hiển thị trong thread dump.
- Tên class chính của ứng dụng.
- Port HTTP hoặc JMX của ứng dụng.
- PID của container trên host nếu đang nhìn từ một PID namespace khác.

Một process có thể kết thúc và PID của nó có thể được hệ điều hành cấp lại cho process khác. Vì vậy, không nên lấy PID từ log cũ rồi dùng lại sau một khoảng thời gian dài. Hãy xác nhận process ngay trước khi attach, kiểm tra main class và thực hiện lệnh trong cùng một phiên xử lý.

### 1.1. Liệt kê JVM đang chạy

Lệnh cơ bản:

~~~bash
jcmd -l
~~~

Lệnh này liệt kê PID, main class và command-line arguments của các JVM mà công cụ phát hiện được. Có thể gọi `jcmd` không có tham số; hành vi tương đương `jcmd -l`.

Ví dụ đầu ra minh họa:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

Trong danh sách có thể xuất hiện cả process `JCmd` do chính lệnh vừa chạy tạo ra. Đừng nhầm PID đó với ứng dụng cần kiểm tra.

`jcmd -l` có thể không liệt kê JVM chạy trong một Docker process riêng. Với container, hãy kiểm tra PID trong container bằng công cụ hệ điều hành như `ps`, rồi chạy `jcmd` trong đúng container/PID namespace.

### 1.2. Xem PID từ chính chương trình Java

Từ Java 9 trở lên, `ProcessHandle.current().pid()` trả về PID của process hiện tại. Ví dụ Java 17+:

~~~java
public final class ProcessIdDemo {
    public static void main(String[] args) {
        System.out.println("PID=" + ProcessHandle.current().pid());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ProcessIdDemo.java
java ProcessIdDemo
~~~

Stdout có dạng:

~~~text
PID=12345
~~~

`12345` chỉ là PID minh họa; giá trị thật do hệ điều hành cấp ở mỗi lần chạy.

### 1.3. Chọn process bằng PID hoặc main class

Cú pháp tổng quát:

~~~text
jcmd <pid> <command> [options]
jcmd <main-class> <command> [options]
~~~

Ví dụ:

~~~bash
jcmd 2125 VM.version
~~~

Có thể dùng tên main class:

~~~bash
jcmd com.example.orders.OrderApplication VM.version
~~~

Tên main class có thể khớp một phần hoặc toàn bộ. Nếu có nhiều JVM dùng cùng main class, lệnh theo tên sẽ gửi yêu cầu tới tất cả process khớp. Trong môi trường nhiều instance, ưu tiên PID đã xác minh.

PID `0` có nghĩa là gửi diagnostic command tới tất cả Java process khả dụng:

~~~bash
jcmd 0 VM.version
~~~

Đây là phạm vi rất rộng. Không dùng PID `0` cho các lệnh có thể tạo dump, thay đổi cấu hình hoặc gây ảnh hưởng hiệu năng nếu chưa chủ động muốn áp dụng cho mọi JVM.

## 2. Quyền truy cập khi attach vào JVM

Theo tài liệu `jcmd` của Oracle JDK 21, công cụ phải chạy:

1. Trên cùng máy với JVM đích.
2. Với cùng effective user và group identifiers đã dùng để khởi chạy JVM.

Đây là yêu cầu của cơ chế attach cục bộ. Nó không có nghĩa bất kỳ tài khoản nào có thể đọc hoặc điều khiển mọi JVM trên máy.

### 2.1. Kiểm tra danh tính người dùng

Trên Linux/macOS:

~~~bash
id
ps -o pid=,user=,group=,args= -p 2125
~~~

Lệnh `id` cho biết danh tính của terminal hiện tại; `ps` cho biết owner và command line của process đích. Nếu hai process chạy dưới user khác nhau, hãy thực hiện thao tác chẩn đoán bằng đúng tài khoản vận hành được phép hoặc phối hợp với quản trị viên.

Trên Windows, kiểm tra tài khoản terminal và xác nhận PID:

~~~powershell
whoami
Get-Process -Id 2125
~~~

`whoami` cho biết account hiện tại; `Get-Process` xác nhận process có PID đó đang tồn tại. Việc xác định owner và quyền truy cập của process có thể cần công cụ quản trị phù hợp. Windows còn áp dụng access control của process và pipe. Chạy terminal dưới một account khác có thể khiến attach thất bại. Không giả định rằng chỉ cần mở terminal với quyền Administrator là mọi JVM đều có thể được attach; cần tuân thủ account và chính sách truy cập của máy.

### 2.2. Quyền attach khác quyền chạy lệnh chẩn đoán

Sau khi attach thành công, mỗi diagnostic command vẫn có thể có yêu cầu và tác động riêng. Ví dụ `Thread.print` in stack trace của toàn bộ thread; `GC.heap_dump` tạo file chứa dữ liệu heap. Một tài khoản có khả năng attach có thể nhìn thấy thông tin nội bộ của ứng dụng.

Hãy coi quyền dùng `jcmd` là quyền vận hành nhạy cảm:

- Chỉ cấp cho tài khoản vận hành cần thiết.
- Không chạy bằng tài khoản chia sẻ rộng nếu có thể dùng account chuyên biệt.
- Giới hạn quyền đọc thư mục chứa dump và report.
- Không đưa command line, system properties, thread dump hoặc heap dump lên nơi công khai.
- Xóa hoặc lưu trữ dữ liệu chẩn đoán theo chính sách retention của tổ chức.

## 3. Attach API và cờ DisableAttachMechanism

`jcmd` sử dụng cơ chế Attach API để kết nối tới JVM đang chạy. Attach được bật mặc định trong HotSpot JVM, nhưng process có thể được khởi chạy với tùy chọn:

~~~bash
java -XX:+DisableAttachMechanism -jar app.jar
~~~

Tùy chọn `-XX:+DisableAttachMechanism` tắt cơ chế cho phép công cụ attach. Khi đó, các công cụ như `jcmd`, `jstack`, `jmap` và `jinfo` không thể attach vào JVM đó.

Ví dụ lỗi:

~~~text
com.sun.tools.attach.AttachNotSupportedException:
The VM does not support the attach mechanism
~~~

Nếu process được khởi chạy với cờ này, chạy `jcmd` từ một terminal khác không thể bật lại Attach API vì chính thao tác attach đã bị vô hiệu hóa. Muốn cho phép attach, cần điều chỉnh startup configuration và khởi động lại JVM theo quy trình triển khai được phê duyệt.

Không nên bật attach tùy tiện trên mọi production process. Hãy cân bằng nhu cầu chẩn đoán với mô hình bảo mật và quy trình quản trị máy chủ.

### 3.1. Các trường hợp khác khiến attach không thành công

Ngoài `DisableAttachMechanism`, một số nguyên nhân thường gặp:

- JVM đã kết thúc hoặc PID không còn tồn tại.
- PID được lấy từ lần chạy trước và đã bị tái sử dụng.
- `jcmd` đang chạy dưới user/group khác với process đích.
- Công cụ đang chạy ở host nhưng JVM nằm trong container/PID namespace khác.
- Container không có JDK hoặc không có executable `jcmd`.
- Chính sách hệ điều hành, sandbox hoặc runtime hạn chế thao tác attach.
- JVM không hỗ trợ Attach API hoặc không cung cấp các diagnostic command mà công cụ yêu cầu.

Một process chạy trong container không đồng nghĩa `jcmd -l` từ host luôn nhìn thấy nó. Hãy xác định đúng namespace và tài khoản trước khi điều tra lỗi quyền.

## 4. Khám phá lệnh mà JVM đích hỗ trợ

Danh sách diagnostic command có thể khác nhau giữa các JVM, phiên bản JDK và runtime. Không nên sao chép một lệnh từ máy khác rồi giả định process đích cũng hỗ trợ.

Xem danh sách lệnh của một process:

~~~bash
jcmd 2125 help
~~~

Xem cú pháp, tham số và impact của một lệnh cụ thể:

~~~bash
jcmd 2125 help Thread.print
jcmd 2125 help GC.heap_dump
~~~

Ví dụ phần trợ giúp cho `Thread.print` có thể hiển thị:

~~~text
Thread.print
Print all threads with stacktraces.

Impact: Medium: Depends on the number of threads.
~~~

Mục `Impact` giúp ước lượng mức ảnh hưởng của thao tác. Kiểm tra help của đúng process đích trước khi dùng lệnh trong môi trường production.

### 4.1. Một số lệnh thường dùng

| Diagnostic command | Mục đích | Mức tác động thường thấy trong HotSpot JDK 21 |
|---|---|---|
| `VM.version` | In phiên bản JVM/JDK | Low |
| `VM.uptime` | In thời gian JVM đã chạy | Low |
| `VM.flags` | In các VM flag và giá trị hiện tại | Low |
| `VM.command_line` | In command line khởi chạy JVM | Low |
| `VM.system_properties` | In system properties | Low |
| `GC.heap_info` | Thông tin tổng quan heap | Medium |
| `Thread.print` | Thread dump kèm stack trace | Medium, tùy số thread |
| `GC.class_histogram` | Thống kê instance theo class | High, phụ thuộc heap |
| `GC.heap_dump` | Tạo heap dump | High; mặc định có thể yêu cầu full GC |

Impact có thể thay đổi theo phiên bản và implementation. Lấy giá trị từ `jcmd <pid> help <command>` trên JVM đích thay vì xem bảng này là hợp đồng cố định.

Ví dụ kiểm tra cơ bản:

~~~bash
jcmd 2125 VM.version
jcmd 2125 VM.uptime
jcmd 2125 VM.flags
jcmd 2125 GC.heap_info
~~~

Thread dump:

~~~bash
jcmd 2125 Thread.print
~~~

Nếu cần in thêm lock của `java.util.concurrent`:

~~~bash
jcmd 2125 Thread.print -l
~~~

Heap dump là thao tác nặng và có thể tạo file lớn:

~~~bash
jcmd 2125 GC.heap_dump filename=/var/tmp/orders-heap.hprof
~~~

Dùng đường dẫn tuyệt đối, bảo đảm user của JVM có quyền ghi và ổ đĩa có đủ dung lượng. Heap dump có thể chứa mật khẩu, token, dữ liệu cá nhân và nội dung nghiệp vụ đang nằm trong bộ nhớ. Bảo vệ file như dữ liệu production nhạy cảm.

### 4.2. Cẩn trọng với output chứa thông tin bí mật

Một số lệnh đọc có impact thấp nhưng output vẫn nhạy cảm:

- `VM.command_line` có thể hiển thị tham số `-D...` hoặc đối số khởi chạy chứa secret.
- `VM.system_properties` có thể in URL, path, cấu hình và thông tin môi trường.
- `Thread.print` có thể chứa tên người dùng, URL hoặc dữ liệu nằm trong stack.
- `GC.heap_dump` có thể chứa dữ liệu ứng dụng đang xử lý.

Không đồng nghĩa `Impact: Low` là output có thể công khai. Impact mô tả ảnh hưởng khi chạy lệnh, không phải mức độ nhạy cảm của dữ liệu được trả về.

## 5. Thực hành Java 17+: tạo process để attach

Ví dụ sau giữ JVM chạy cho tới khi bị dừng. Chương trình in PID để terminal thứ hai có thể dùng chính PID đó.

Tệp `JcmdTarget.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class JcmdTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Target ready. Run jcmd from another terminal.");

        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 JcmdTarget.java
java JcmdTarget
~~~

Stdout có dạng:

~~~text
PID=12345
Target ready. Run jcmd from another terminal.
~~~

PID là giá trị thực tế của process, không cố định giữa các lần chạy.

Ở terminal thứ hai, liệt kê JVM và thay `12345` bằng PID vừa in:

~~~bash
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
~~~

Kết quả `VM.version` có phần đầu như sau:

~~~text
12345:
OpenJDK 64-Bit Server VM version 24.0.2+12
JDK 24.0.2
~~~

Phiên bản cụ thể phụ thuộc JDK đang chạy. Dừng chương trình demo bằng `Ctrl+C` ở terminal thứ nhất.

### 5.1. Chọn process theo main class

Nếu chỉ có một process chạy `JcmdTarget`, có thể dùng:

~~~bash
jcmd JcmdTarget VM.version
~~~

Nếu có nhiều instance cùng chạy class này, công cụ có thể gửi lệnh tới tất cả process khớp tên. Hãy dùng PID cụ thể để tránh thu thập nhầm hoặc tác động nhầm instance.

## 6. PID và quyền truy cập trong Docker/container

Container có PID namespace riêng. PID hiển thị bên trong container có thể khác PID trên host. Ngoài ra, `jcmd -l` không liệt kê JVM chạy trong một Docker process riêng theo mô tả của Oracle JDK 21.

Cách kiểm tra thường dùng là vào đúng container rồi chạy công cụ ở bên trong:

~~~bash
docker exec -it orders-app sh
~~~

Trong container:

~~~bash
ps -ef
jcmd -l
~~~

Xác định PID của JVM trong namespace container, sau đó:

~~~bash
jcmd 1 VM.version
~~~

`1` chỉ đúng nếu JVM thực sự là PID 1 trong container. Nếu PID khác, dùng PID vừa xác định từ `ps` hoặc `jcmd -l`.

Điều kiện cần có:

- Image phải có executable `jcmd` (thường cần JDK hoặc một diagnostic image phù hợp).
- `jcmd` phải chạy trong cùng container/PID namespace hoặc môi trường process mà JVM có thể được attach.
- User chạy `jcmd` phải có danh tính và quyền tương thích với user chạy JVM.
- Container policy không được chặn thao tác attach.

Nếu ứng dụng chỉ dùng runtime image tối giản không chứa `jcmd`, hãy dùng quy trình diagnostic image/sidecar đã được tổ chức phê duyệt. Không thay đổi quyền container hoặc chạy toàn bộ ứng dụng bằng root chỉ để né lỗi attach.

## 7. jcmd là công cụ local, không phải remote command

`jcmd` phải chạy trên cùng máy với JVM đích. Lệnh này không nhận hostname, IP hoặc JMX port để attach qua mạng.

Nếu cần chẩn đoán server từ máy khác:

1. Dùng SSH hoặc cơ chế quản trị hạ tầng để vào đúng host.
2. Chạy `jcmd` cục bộ trên host đó dưới danh tính có quyền phù hợp.
3. Nếu không thể chạy công cụ trên host, sử dụng giải pháp quản lý từ xa như JMX đã cấu hình authentication/TLS hoặc nền tảng monitoring/diagnostic được bảo vệ.

Không mở một cổng attach tùy ý ra mạng. Attach API và `jcmd` là cơ chế chẩn đoán cục bộ; remote management cần cơ chế xác thực và bảo vệ riêng.

## 8. Chọn đúng JDK tool

`jcmd` được cung cấp trong thư mục `bin` của JDK. Nếu máy có nhiều JDK, lệnh `jcmd` tìm thấy qua `PATH` có thể không thuộc cùng JDK với ứng dụng.

Kiểm tra đường dẫn công cụ:

Trên Linux/macOS:

~~~bash
which java
which jcmd
"$JAVA_HOME/bin/jcmd" -h
~~~

Trên Windows PowerShell:

~~~powershell
where.exe java
where.exe jcmd
& "$env:JAVA_HOME\bin\jcmd.exe" -h
~~~

Oracle lưu ý các công cụ `jcmd`, `jinfo`, `jmap` và `jstack` được cung cấp trong một JDK không được hỗ trợ khi dùng để troubleshoot JVM thuộc một JDK version khác. Nên chọn công cụ từ cùng JDK release/vendor với JVM đích hoặc theo quy trình hỗ trợ của tổ chức.

Không nhầm `jcmd -h` với `jcmd -version`: cú pháp CLI được tài liệu hóa cho trợ giúp là `-h`; không có tùy chọn phiên bản `-version`.

## 9. Lỗi thường gặp và cách xử lý

| Thông báo/tình huống | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `java.io.IOException: no such process` | PID sai, process đã thoát hoặc namespace không khớp | Chạy lại `jcmd -l`/`ps`, xác nhận PID hiện tại |
| `AttachNotSupportedException: The VM does not support the attach mechanism` | Attach bị tắt hoặc JVM không hỗ trợ cơ chế này | Kiểm tra startup flags, runtime và `-XX:+DisableAttachMechanism` |
| `Operation not permitted` / access denied | User/group hoặc OS policy không cho attach | So sánh account chạy tool và process; kiểm tra ACL/container policy |
| `jcmd -l` không thấy ứng dụng trong Docker | JVM ở Docker process/PID namespace riêng | Dùng `docker exec`, `ps` và `jcmd` trong container |
| `jcmd` không được nhận diện | JDK `bin` không nằm trong `PATH` hoặc chỉ cài runtime image | Gọi bằng đường dẫn `JAVA_HOME/bin/jcmd` hoặc cài diagnostic JDK |
| `Unknown diagnostic command` | JVM đích không cung cấp lệnh đó | Chạy `jcmd <pid> help` trên đúng process |
| Lệnh trả kết quả khác tài liệu | JDK/provider/HotSpot version khác | Dùng `help <command>` và tool phù hợp với target JDK |
| Attach bị timeout | JVM bận, đang shutdown, attach socket/OS policy có vấn đề | Kiểm tra trạng thái process, thử lại sau khi xác nhận nguyên nhân |
| Không ghi được heap dump | User JVM không có quyền ghi hoặc ổ đĩa thiếu dung lượng | Dùng thư mục đích có quyền ghi và đủ dung lượng |

Quy trình chẩn đoán gọn:

1. Xác nhận JVM còn chạy và lấy PID mới.
2. Xác nhận main class và user sở hữu process.
3. Xác nhận terminal đang ở cùng host/container/PID namespace.
4. Kiểm tra `jcmd -h` và `jcmd <pid> help`.
5. Kiểm tra Attach API có bị tắt lúc khởi động không.
6. Kiểm tra quyền file, thư mục tạm, container policy và runtime.
7. Dùng lệnh tác động thấp như `VM.version` trước; chỉ chạy dump hoặc histogram sau khi hiểu impact.

## 10. Checklist vận hành an toàn

- [ ] Xác định PID mới từ `jcmd -l`, `ps` hoặc log của chính ứng dụng.
- [ ] Đối chiếu PID với main class/instance cần kiểm tra.
- [ ] Dùng PID cụ thể; tránh PID `0` hoặc selector main class có thể khớp nhiều process.
- [ ] Chạy `jcmd` trên cùng host và đúng user/group theo yêu cầu attach.
- [ ] Với Docker, xác định PID trong đúng namespace và dùng công cụ trong container.
- [ ] Kiểm tra `-XX:+DisableAttachMechanism` nếu attach không hỗ trợ.
- [ ] Dùng JDK tool phù hợp với phiên bản JVM đích.
- [ ] Chạy `help <command>` để xem cú pháp, quyền và impact trước khi thực thi.
- [ ] Đánh giá tác động trước khi chạy `GC.class_histogram`, `GC.heap_dump` hoặc các lệnh nặng.
- [ ] Bảo vệ command line, system properties, thread dump và heap dump như dữ liệu nhạy cảm.
- [ ] Lưu report/dump ở nơi có quyền truy cập giới hạn và retention rõ ràng.

## 11. Ghi nhớ

PID giúp `jcmd` xác định JVM đích, nhưng PID một mình không đủ để bảo đảm attach thành công. Công cụ cần chạy trên cùng máy và cùng effective user/group với JVM; process phải cho phép Attach API và môi trường OS/container phải cho phép truy cập.

Bắt đầu bằng `jcmd -l`, xác minh PID và main class, sau đó dùng `jcmd <pid> help` để xem các lệnh mà chính JVM đó hỗ trợ. Dùng các lệnh impact thấp trước, đánh giá output nhạy cảm và chỉ tạo histogram/heap dump khi đã chuẩn bị dung lượng, quyền ghi và quy trình bảo vệ dữ liệu.

Tài liệu tham khảo:

- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The java Command — Advanced Serviceability Options, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 Troubleshooting Guide — The jcmd Utility](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)
- [ProcessHandle API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessHandle.html)