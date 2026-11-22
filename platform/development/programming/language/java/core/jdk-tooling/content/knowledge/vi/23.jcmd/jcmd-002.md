# Liệt kê JVM process bằng jcmd

## 1. jcmd dùng để làm gì?

**jcmd** là công cụ dòng lệnh của JDK để gửi diagnostic command tới một Java Virtual Machine (JVM) đang chạy trên cùng máy. Nó giúp tìm tiến trình Java, kiểm tra thông tin JVM và thực hiện các thao tác chẩn đoán mà JVM hỗ trợ.

Với tác vụ liệt kê JVM process, lệnh quan trọng nhất là:

~~~bash
jcmd -l
~~~

Lệnh này hiển thị các tiến trình Java mà công cụ phát hiện được trên máy cục bộ. Mỗi dòng thường có process ID (PID), tên main class hoặc module và có thể kèm đối số khởi chạy.

jcmd hữu ích khi máy chạy nhiều ứng dụng Java, service hoặc nhiều phiên bản ứng dụng. Bạn tìm PID trước, xác minh đúng JVM, rồi gửi diagnostic command tới đúng tiến trình.

jcmd là công cụ chẩn đoán JVM. Nó không phải trình quản lý toàn bộ process của hệ điều hành và không thay thế Task Manager, tasklist, ps hoặc Process Explorer.

## 2. Kiểm tra jcmd đã có trong JDK

jcmd được cung cấp cùng JDK. Kiểm tra hướng dẫn sử dụng:

~~~bash
jcmd -h
java --version
~~~

Trên Windows PowerShell, kiểm tra vị trí executable:

~~~powershell
where jcmd
& "$env:JAVA_HOME\bin\jcmd.exe" -l
~~~

Trên Linux/macOS:

~~~bash
which jcmd
"$JAVA_HOME/bin/jcmd" -l
~~~

Nếu shell không tìm thấy lệnh, kiểm tra thư mục bin của JDK và biến PATH. Một runtime image tối giản được tạo bằng jlink có thể không chứa công cụ jcmd. Khi thiếu công cụ, cần dùng JDK có jcmd trong cùng môi trường máy/container với JVM đích.

## 3. Cú pháp và các chế độ chính

Cú pháp tổng quát:

~~~text
jcmd <pid | main class> <command ...>
jcmd -l
jcmd -h
~~~

Các dạng sử dụng thường gặp:

| Lệnh | Tác dụng |
|---|---|
| jcmd -l | Liệt kê JVM process trên máy cục bộ. |
| jcmd | Không có tùy chọn cũng liệt kê Java process, tương đương -l. |
| jcmd -h | Hiển thị hướng dẫn sử dụng. |
| jcmd <pid> help | Liệt kê diagnostic command mà JVM có thể nhận. |
| jcmd <pid> <command> | Gửi command tới JVM có PID tương ứng. |
| jcmd <main class> <command> | Chọn JVM bằng tên main class, khớp một phần hoặc toàn bộ. |
| jcmd <pid> -f <file> | Đọc và thực thi command từ file. |

PID là process ID của JVM ở cấp hệ điều hành. Khi có nhiều tiến trình Java cùng chạy, chọn bằng PID thường rõ ràng hơn chọn bằng main class.

Trên JDK 24.0.2, jcmd -h xác nhận rằng -l liệt kê JVM process cục bộ; khi không có option, jcmd cũng liệt kê process theo cách tương tự.

## 4. Liệt kê JVM process bằng jcmd -l

Chạy:

~~~bash
jcmd -l
~~~

Ví dụ output:

~~~text
12132 JcmdProbe
94336 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider --feedback silent
21864 jdk.jshell/jdk.internal.jshell.tool.JShellToolProvider --feedback concise
43528 jdk.jcmd/sun.tools.jcmd.JCmd -l
~~~

Các PID và tên class trong ví dụ phụ thuộc máy đang chạy. Một số dòng biểu diễn main class truyền thống; ứng dụng modular có thể hiển thị tên module cùng main class.

Ý nghĩa các phần:

- **12132:** PID của tiến trình JVM.
- **JcmdProbe:** main class dùng để khởi chạy ứng dụng.
- **jdk.jshell/...:** ứng dụng modular, tên module và main class xuất hiện cùng nhau.
- **--feedback silent:** đối số khởi chạy được hiển thị sau tên class nếu có.

Chính tiến trình jcmd đang chạy lệnh liệt kê cũng có thể xuất hiện, ví dụ dòng jdk.jcmd/sun.tools.jcmd.JCmd -l. Đây là tiến trình công cụ chẩn đoán, không nhất thiết là ứng dụng cần kiểm tra.

Danh sách có thể thay đổi ngay sau khi chạy vì JVM có thể khởi động hoặc kết thúc đồng thời. Hãy xác minh lại PID trước khi gửi command chẩn đoán.

## 5. Phân biệt JVM process với process hệ điều hành

Máy có thể chạy nhiều loại process:

- Java application chạy trên HotSpot JVM.
- Tiến trình jcmd hoặc jps.
- Java service chạy dưới tài khoản hệ thống.
- Native executable không chạy trên JVM.
- Process của trình duyệt, database, IDE hoặc công cụ hệ điều hành.

jcmd -l nhằm liệt kê Java VM process mà cơ chế phát hiện/attach của công cụ nhận diện được. Nó không liệt kê toàn bộ process của Windows, Linux hoặc macOS.

Có thể dùng công cụ hệ điều hành để đối chiếu:

Windows:

~~~powershell
tasklist | findstr /i java
~~~

Linux:

~~~bash
ps -ef | grep '[j]ava'
~~~

macOS:

~~~bash
ps aux | grep '[j]ava'
~~~

Các lệnh này tìm process có tên hoặc command line chứa java, nhưng không thay thế danh sách JVM của jcmd. Một process có tên java không nhất thiết cung cấp HotSpot diagnostic command.

Một số ứng dụng Java được biên dịch thành native executable cũng không xuất hiện như JVM process thông thường. Hãy xác định loại runtime trước khi chọn công cụ.

## 6. Tạo JVM mẫu để thực hành liệt kê

Tạo file **JcmdProbe.java**:

~~~java
public class JcmdProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "JcmdProbe ready; pid=" + ProcessHandle.current().pid());

        Thread.sleep(120_000);
    }
}
~~~

ProcessHandle.current().pid() trả về PID của tiến trình hiện tại. Thread.sleep giữ JVM chạy trong hai phút để có thời gian quan sát.

Biên dịch bằng Java 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 JcmdProbe.java
~~~

Terminal thứ nhất, khởi chạy:

~~~bash
java JcmdProbe
~~~

Ví dụ stdout:

~~~text
JcmdProbe ready; pid=12132
~~~

PID là giá trị động, không cố định giữa các lần chạy.

Mở terminal thứ hai trên cùng máy và chạy:

~~~bash
jcmd -l
~~~

Dòng chứa PID vừa in ra phải có main class JcmdProbe. Sau khi kiểm tra, quay lại terminal thứ nhất và nhấn Ctrl+C để kết thúc chương trình mẫu.

Ví dụ này đã được biên dịch bằng javac --release 17 và kiểm tra với jcmd trên JDK 24.0.2.

## 7. Chọn đúng JVM sau khi tìm thấy PID

Không nên gửi diagnostic command chỉ dựa vào một PID cũ được ghi trong tài liệu hoặc log. PID có thể được tái sử dụng sau khi process kết thúc.

Quy trình xác nhận:

1. Chạy jcmd -l để lấy danh sách mới nhất.
2. Tìm dòng có main class hoặc module mong muốn.
3. Ghi lại PID.
4. Dùng VM.command_line để xác minh ứng dụng và tham số khởi chạy.
5. Dùng VM.version để xác nhận phiên bản JVM.
6. Chỉ sau đó mới chạy command chẩn đoán phù hợp.

Ví dụ:

~~~bash
jcmd 12132 VM.command_line
jcmd 12132 VM.version
~~~

Output minh họa:

~~~text
12132:
VM Arguments:
java_command: JcmdProbe
java_class_path (initial): ...\out
Launcher Type: SUN_STANDARD
~~~

~~~text
12132:
OpenJDK 64-Bit Server VM version 24.0.2+12
JDK 24.0.2
~~~

Nếu hai tiến trình có cùng main class, hãy dùng PID và đối chiếu command line, classpath, phiên bản hoặc thông tin triển khai để tránh nhầm ứng dụng.

## 8. Xem diagnostic command mà JVM hỗ trợ

Sau khi xác định PID, xem danh sách command:

~~~bash
jcmd 12132 help
~~~

JVM trả về các command mà phiên bản và cấu hình hiện tại hỗ trợ. Danh sách có thể khác giữa JDK release, vendor, loại JVM và runtime image.

Để xem cú pháp và mô tả một command cụ thể:

~~~bash
jcmd 12132 help VM.version
~~~

Ví dụ output:

~~~text
12132:
VM.version
Print JVM version information.

Impact: Low

Syntax: VM.version
~~~

Phần **Impact** mô tả mức ảnh hưởng của command theo thông tin JVM cung cấp. Hãy đọc phần này trước khi thực hiện thao tác có thể tốn tài nguyên hoặc ảnh hưởng tiến trình.

Không giả định mọi JVM đều có cùng bộ command. Lệnh help của chính target JVM là nguồn tham khảo trực tiếp.

## 9. Các command thường dùng sau khi liệt kê

Sau khi tìm được PID, có thể dùng một số command thông tin:

| Command | Thông tin |
|---|---|
| VM.version | Phiên bản JVM và JDK. |
| VM.command_line | Command line và thông tin khởi chạy. |
| VM.flags | Các JVM flag đang có hiệu lực. |
| VM.uptime | Thời gian JVM đã chạy. |
| VM.system_properties | Các system property của JVM. |
| Thread.print | Thread dump và stack trace của các thread. |
| GC.heap_info | Thông tin tổng quan về heap. |
| GC.class_histogram | Histogram số lượng và dung lượng class instance. |

Ví dụ:

~~~bash
jcmd 12132 VM.version
jcmd 12132 VM.command_line
jcmd 12132 VM.flags
jcmd 12132 VM.uptime
jcmd 12132 GC.heap_info
~~~

Để kiểm tra thread:

~~~bash
jcmd 12132 Thread.print
~~~

Thread.print có thể tạo output lớn. GC.class_histogram có thể tốn thời gian và ảnh hưởng hiệu năng tùy kích thước heap. Chỉ chạy khi cần, đặc biệt trên production.

VM.system_properties có thể chứa đường dẫn, endpoint hoặc giá trị cấu hình nhạy cảm. Không chia sẻ output công khai nếu chưa kiểm tra và loại bỏ secret.

## 10. Gửi command bằng PID hoặc main class

Cách phổ biến và rõ ràng nhất là chỉ định PID:

~~~bash
jcmd 12132 VM.version
~~~

Có thể chọn bằng main class:

~~~bash
jcmd JcmdProbe VM.version
~~~

Theo cú pháp jcmd, tên main class có thể khớp một phần hoặc toàn bộ tên class dùng để khởi chạy Java. Cách này tiện khi chỉ có một instance phù hợp.

Nếu có nhiều JVM chạy cùng class, việc chọn theo main class có thể không rõ ràng. Trong môi trường service hoặc production, ưu tiên PID vừa được xác minh.

jcmd cũng hỗ trợ PID bằng 0:

~~~bash
jcmd 0 VM.version
~~~

PID 0 có nghĩa command sẽ được gửi tới tất cả Java process mà jcmd có thể truy cập. Đây không phải cách liệt kê đơn thuần. Chỉ dùng khi thật sự muốn thực hiện cùng một diagnostic command trên mọi JVM có thể truy cập, vì tác động có thể nhân lên theo số process.

## 11. Chạy nhiều diagnostic command từ file

jcmd hỗ trợ đọc command từ file với tùy chọn -f.

Ví dụ file **jcmd-commands.txt**:

~~~text
VM.version
VM.uptime
VM.flags
~~~

Chạy:

~~~bash
jcmd 12132 -f jcmd-commands.txt
~~~

Các command trong file được gửi tới JVM đã chọn. Hãy kiểm tra nội dung file trước khi chạy, vì file có thể chứa command tạo tác động lên process.

Cách này hữu ích khi cần lặp lại một bộ kiểm tra thống nhất trong môi trường kiểm thử hoặc quy trình hỗ trợ vận hành. Đối với production, nên giữ bộ command ngắn và chỉ dùng những lệnh đã được đánh giá về impact.

## 12. Quyền truy cập và cơ chế Attach

jcmd sử dụng cơ chế Attach để giao tiếp với JVM đích. Một số điều kiện quan trọng:

- jcmd và JVM đích phải ở cùng máy.
- Trên hệ thống Unix, người chạy jcmd cần cùng effective user và group phù hợp với process đích.
- Trên Windows, tài khoản và quyền truy cập phải cho phép attach vào process.
- JVM đích phải hỗ trợ Attach mechanism và chưa bị vô hiệu hóa cơ chế này.
- Cần dùng môi trường JDK/JVM tương thích với target.

Nếu JVM được khởi chạy với tùy chọn **-XX:+DisableAttachMechanism**, các công cụ dựa trên Attach như jcmd không thể gửi diagnostic command theo cơ chế thông thường.

Việc nhìn thấy process trong danh sách và việc attach thành công là hai việc cần phân biệt. Một process có thể xuất hiện nhưng từ chối attach vì cấu hình, quyền hoặc môi trường.

Không nên mặc định chạy mọi lệnh bằng quyền Administrator/root. Trước tiên xác định tài khoản sở hữu JVM và thực hiện bằng đúng danh tính được cấp quyền.

## 13. JVM trong Docker và môi trường container

Container tạo ranh giới về process namespace, filesystem và user. Vì vậy, jcmd chạy trên host có thể không nhìn thấy JVM nằm trong một container có PID namespace riêng.

Khi cần chẩn đoán JVM trong container:

1. Xác định đúng container hoặc pod đang chạy ứng dụng.
2. Vào cùng container hoặc môi trường có chung PID namespace với JVM.
3. Đảm bảo có công cụ jcmd trong image hoặc mount/cài JDK tool phù hợp.
4. Dùng user có quyền attach vào JVM.
5. Chạy jcmd -l bên trong môi trường đó.
6. Chọn PID mà container nhìn thấy, rồi chạy command cần thiết.

Ví dụ với Docker:

~~~bash
docker exec -it <container-name> jcmd -l
~~~

Ví dụ với Kubernetes khi đã có quyền truy cập cluster:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- jcmd -l
~~~

Các lệnh trên chỉ là ví dụ; tên container, pod, container name và việc có jcmd trong image phụ thuộc triển khai thực tế.

PID nhìn từ host có thể khác PID nhìn bên trong container. Dùng PID được liệt kê trong cùng namespace nơi bạn chạy jcmd.

## 14. Giới hạn và lưu ý khi đọc danh sách

jcmd -l là một công cụ discovery hữu ích nhưng danh sách không phải nguồn kiểm kê tuyệt đối cho mọi Java runtime.

Một số tình huống có thể làm kết quả không đầy đủ:

- JVM nằm trên máy khác.
- JVM chạy trong PID namespace hoặc container khác.
- Process thuộc user khác và không thể attach.
- Attach mechanism bị tắt hoặc không khả dụng.
- Runtime image không có công cụ tương ứng.
- Ứng dụng không chạy trên HotSpot JVM thông thường.
- Process vừa khởi động hoặc kết thúc trong lúc truy vấn.

Một JVM không xuất hiện trong danh sách không đồng nghĩa chắc chắn ứng dụng không chạy. Hãy đối chiếu với công cụ process của hệ điều hành, log service manager, container runtime và thông tin triển khai.

jcmd cũng không cung cấp một danh sách JVM từ xa bằng cách truyền hostname. Với JVM ở máy khác, cần dùng cơ chế quản lý/giám sát từ xa đã được cấu hình riêng, ví dụ JMX hoặc nền tảng observability.

## 15. So sánh jcmd -l và jps

Cả jcmd và jps đều có thể liệt kê JVM process cục bộ, nhưng mục đích sử dụng khác nhau.

| Công cụ | Vai trò |
|---|---|
| jcmd -l | Liệt kê JVM và là điểm bắt đầu để gửi diagnostic command trực tiếp tới PID. |
| jps | Tiện ích liệt kê JVM process; có option hiển thị main class, arguments và JVM arguments. |
| tasklist / ps | Liệt kê process ở cấp hệ điều hành, không phải diagnostic interface chuyên biệt cho JVM. |

Ví dụ:

~~~bash
jps -lv
~~~

jps có thể hữu ích khi cần xem nhanh danh sách process và JVM arguments. Sau khi tìm được PID, jcmd cho phép truy vấn sâu hơn bằng diagnostic command.

Cả jps và jcmd đều có giới hạn về khả năng nhìn thấy process cục bộ, quyền và môi trường attach. Không nên dùng output của một công cụ như bằng chứng duy nhất rằng mọi JVM trên hệ thống đã được phát hiện.

## 16. Lỗi thường gặp khi liệt kê hoặc attach JVM

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jcmd is not recognized | JDK bin chưa nằm trong PATH hoặc chỉ cài runtime tối giản. | Kiểm tra JAVA_HOME, PATH và thư mục bin của JDK. |
| jcmd -l không hiển thị ứng dụng | JVM ở container/PID namespace khác, user khác hoặc không được discovery. | Chạy trong đúng môi trường và đối chiếu bằng công cụ OS. |
| PID không còn tồn tại | Process kết thúc hoặc PID cũ đã được tái sử dụng. | Chạy lại jcmd -l và xác nhận PID mới. |
| AttachNotSupportedException | JVM không hỗ trợ attach, attach bị tắt hoặc môi trường không phù hợp. | Kiểm tra JVM flags, user, container và runtime. |
| Operation not permitted / access denied | Không đủ quyền hoặc khác user sở hữu JVM. | Dùng đúng tài khoản được phép attach. |
| Could not attach to process | JVM đã thoát, attach socket/namespace không truy cập được hoặc cơ chế attach lỗi. | Xác nhận process còn sống, đúng namespace và quyền. |
| Unknown diagnostic command | Target JVM không hỗ trợ command đó. | Chạy jcmd PID help và dùng command khả dụng. |
| Nhiều process cùng main class | Chọn target bằng tên class gây mơ hồ. | Chọn PID và xác minh VM.command_line. |
| Output Thread.print quá lớn | Có nhiều thread hoặc stack trace dài. | Lưu output vào file và chỉ chạy khi cần chẩn đoán. |
| Process hiện trong danh sách nhưng không attach được | Discovery thành công nhưng quyền hoặc Attach mechanism không cho phép gửi lệnh. | Kiểm tra user, -XX:+DisableAttachMechanism và namespace. |

Nếu gặp lỗi, hãy ghi nhận command đã chạy, PID, JDK version, tài khoản thực thi và thông báo lỗi đầy đủ. Không chạy lại các diagnostic command có impact cao chỉ để thử quyền truy cập.

## 17. Quy trình sử dụng jcmd trong vận hành

Một quy trình ngắn và có thể lặp lại:

1. Mở terminal trong đúng máy hoặc container chạy JVM.
2. Xác nhận jcmd thuộc JDK có sẵn bằng jcmd -h.
3. Chạy jcmd -l để liệt kê process.
4. Tìm PID theo main class/module và đối số khởi chạy.
5. Xác minh target bằng VM.command_line và VM.version.
6. Chạy help để xem command được target hỗ trợ.
7. Đọc Impact và chọn diagnostic command cần thiết.
8. Lưu output vào vị trí được kiểm soát nếu cần điều tra.
9. Kiểm tra dữ liệu nhạy cảm trước khi chia sẻ output.
10. Ghi lại PID, thời điểm, JDK version và command đã chạy để có thể đối chiếu.

Ví dụ chuỗi lệnh cơ bản:

~~~bash
jcmd -l
jcmd 12132 VM.command_line
jcmd 12132 VM.version
jcmd 12132 help
jcmd 12132 GC.heap_info
~~~

Thay 12132 bằng PID thực tế vừa xác nhận. Không sao chép PID minh họa từ tài liệu vào môi trường đang chạy.

Trong script tự động, kiểm tra exit code và xử lý trường hợp không tìm thấy target. Tránh giả định một PID cố định qua nhiều lần deploy hoặc reboot.

## 18. Checklist khi liệt kê JVM process

- [ ] Đã xác nhận jcmd thuộc JDK và có thể chạy trên môi trường hiện tại.
- [ ] Đã dùng jcmd -l để lấy danh sách JVM process mới nhất.
- [ ] Đã hiểu PID, main class/module và arguments trong output.
- [ ] Đã phân biệt dòng process JCmd với ứng dụng cần kiểm tra.
- [ ] Đã xác minh PID bằng VM.command_line và VM.version.
- [ ] Đã dùng jcmd PID help để xem command target hỗ trợ.
- [ ] Đã đọc Impact trước khi chạy diagnostic command.
- [ ] Đã dùng đúng user và cùng máy/PID namespace với JVM.
- [ ] Đã kiểm tra Attach mechanism nếu không kết nối được.
- [ ] Đã tránh dùng PID cũ hoặc selector main class khi có nhiều instance.
- [ ] Đã bảo vệ output có thể chứa command-line argument hoặc system property nhạy cảm.
- [ ] Đã đối chiếu bằng công cụ hệ điều hành khi danh sách JVM không đầy đủ.

jcmd -l là bước đầu để tìm JVM process cục bộ và lấy PID cho các thao tác chẩn đoán tiếp theo. Khi xác nhận đúng target, kiểm tra quyền attach và đọc impact của từng command, bạn có thể điều tra JVM an toàn và có thể lặp lại trong môi trường phát triển lẫn vận hành.