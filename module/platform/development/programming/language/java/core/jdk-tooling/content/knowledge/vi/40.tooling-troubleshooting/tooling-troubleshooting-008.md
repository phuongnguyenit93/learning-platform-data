# Không attach được JVM: chẩn đoán và khắc phục

**Attach JVM** là thao tác để một công cụ kết nối tới Java Virtual Machine (JVM) đang chạy nhằm lấy thông tin, tạo thread dump/heap dump, bật JMX hoặc nạp agent phục vụ profiling và chẩn đoán. Khi attach thất bại, nguyên nhân thường nằm ở PID, phiên bản JDK, quyền của process, loại JVM, cấu hình attach hoặc ranh giới container.

Trước khi xử lý, hãy xác định công cụ đang dùng cơ chế nào. `jcmd`, `jstack`, `jmap` và Java Attach API dùng cơ chế attach cục bộ của JVM. IDE debugger có thể dùng JDWP qua TCP. JConsole/JDK Mission Control có thể dùng JMX. Ba cơ chế này có điều kiện kết nối và lỗi khác nhau.

## 1. Phân biệt ba kiểu kết nối

| Cơ chế | Công cụ thường gặp | Cách kết nối | Phạm vi |
| --- | --- | --- | --- |
| JVM Attach API | `jcmd`, `jstack`, `jmap`, `jinfo`, `VirtualMachine.attach()` | PID và cơ chế IPC của OS | Process local có thể truy cập |
| JDWP debugger | IntelliJ, Eclipse, `jdb` | TCP socket do JDWP agent mở | Có thể kết nối từ xa nếu cấu hình network |
| JMX | JConsole, JDK Mission Control, ứng dụng quản trị | JMX connector, thường dùng RMI | Local qua Attach API hoặc remote qua network |

Nếu `jcmd <PID> VM.version` thất bại, đó là lỗi của đường Attach API. Nếu IDE báo `Connection refused` khi attach debugger tới `host:port`, hãy kiểm tra JDWP agent, địa chỉ bind và firewall. Nếu JConsole không kết nối tới host/port, hãy kiểm tra JMX agent, RMI port, authentication và TLS.

Không thể dùng `jcmd` như một client TCP để attach JVM trên máy khác. `jcmd` yêu cầu chạy trên cùng máy với JVM và cùng effective user/group đã khởi chạy JVM. Với quản trị từ xa, dùng JMX đã cấu hình bảo mật hoặc cơ chế quản lý phù hợp.

## 2. Xác định đúng PID và JVM

Bước đầu tiên là xác nhận process còn sống và PID đang trỏ tới đúng ứng dụng. PID có thể thay đổi sau restart; PID ở host cũng có thể khác PID trong container.

### Liệt kê JVM trên máy local

```bash
jcmd -l
jps -lv
```

`jcmd -l` liệt kê JVM mà công cụ nhìn thấy, kèm PID, main class và tham số khởi chạy. `jps -lv` hữu ích khi cần xem thêm thông tin launch. Danh sách này không phải lúc nào cũng bao gồm process nằm trong Docker process namespace riêng.

Nếu biết PID, hỏi trực tiếp process:

```bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
```

Các lệnh trên xác nhận target JVM, command line và runtime properties. Đặc biệt, `java.home`, `java.version`, `java.vm.name`, `os.name` và `user.dir` giúp xác định JVM thực tế mà service đang dùng.

Trên Linux, kiểm tra process và user:

```bash
ps -o pid,ppid,user,group,args -p <PID>
id
```

Trên Windows PowerShell:

```powershell
Get-Process -Id <PID> | Format-List Id, ProcessName, Path
whoami
Get-Command java, jcmd
```

Đừng lấy PID của wrapper shell, Maven, Gradle hoặc process cha nếu JVM cần chẩn đoán nằm trong process con. Kiểm tra command line và executable path trước khi attach.

### PID trong Docker/Kubernetes

`jcmd -l` không hiển thị JVM đang chạy trong Docker process namespace riêng. Oracle hướng dẫn dùng `ps` để tìm PID của JVM trong trường hợp này.

Thử bên trong container:

```bash
docker exec -it <container> sh
id
ps -ef
jcmd -l
jcmd <PID_TRONG_CONTAINER> VM.version
```

Với Kubernetes:

```bash
kubectl exec -it <POD> -c <CONTAINER> -- sh
id
ps -ef
jcmd <PID_TRONG_CONTAINER> VM.version
```

Image runtime tối giản có thể không chứa shell, `ps` hoặc JDK tools. Khi đó, dùng image/debug container phù hợp với chính sách triển khai và bảo đảm công cụ có thể nhìn thấy PID, filesystem/attach endpoint và quyền của process đích. PID lấy từ host không mặc nhiên là PID dùng được bên trong container.

## 3. Kiểm tra JDK và Attach API có tương thích không

`jcmd`, `jstack`, `jmap` và `jinfo` là công cụ đi cùng JDK. Oracle ghi rõ các tool này không được hỗ trợ khi dùng tool từ một JDK version để chẩn đoán JVM chạy bằng một JDK version khác.

Kiểm tra:

```bash
java -version
javac -version
jcmd -h
jcmd <PID> VM.version
```

Dùng `jcmd` thuộc JDK phù hợp với JVM đích. Máy có nhiều JDK có thể khiến `java` và `jcmd` trong `PATH` đến từ hai thư mục khác nhau. Có thể gọi bằng đường dẫn đầy đủ:

```bash
/path/to/target-jdk/bin/jcmd <PID> VM.version
```

Trên Windows PowerShell:

```powershell
& "C:\path\to\target-jdk\bin\jcmd.exe" <PID> VM.version
```

Attach API còn phụ thuộc Attach Provider của JVM. `AttachNotSupportedException` có thể xuất hiện khi PID không hợp lệ, process không tồn tại, không có provider tương thích hoặc target JVM không hỗ trợ cơ chế attach của provider đó. Executable native tạo từ GraalVM Native Image không phải JVM process thông thường để `jcmd` attach.

Nếu đang dùng JVM vendor khác HotSpot, kiểm tra tài liệu và công cụ đúng vendor. Đừng kết luận rằng mọi Java runtime đều hỗ trợ cùng một attach provider hoặc cùng bộ diagnostic commands.

## 4. Kiểm tra attach có bị vô hiệu hóa không

Với HotSpot, tùy chọn sau tắt cơ chế attach:

```bash
-XX:+DisableAttachMechanism
```

Mặc định, tùy chọn này không được bật và attach mechanism hoạt động. Nếu ứng dụng được khởi chạy với `-XX:+DisableAttachMechanism`, `jcmd`, `jstack`, `jmap` và Attach API sẽ không kết nối được.

Một lỗi đặc trưng:

```text
com.sun.tools.attach.AttachNotSupportedException:
The VM does not support the attach mechanism
```

Kiểm tra command line thực tế:

```bash
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
```

Nếu flag này đang bật, cần thay đổi cấu hình khởi chạy và restart JVM theo quy trình vận hành để attach được bật. Đây là startup option; lệnh `jcmd` từ bên ngoài không thể bật lại cơ chế attach đã bị vô hiệu hóa trong target process.

Đừng bỏ qua flag này trong cấu hình bảo mật. Việc tắt attach có thể là lựa chọn có chủ đích để giới hạn khả năng nạp agent và thao tác chẩn đoán vào process.

## 5. Kiểm tra user, group và quyền của OS

`jcmd` cần chạy với cùng effective user và group đã khởi chạy JVM. Việc chạy công cụ dưới một tài khoản khác có thể gây `Permission denied`, `Operation not permitted`, lỗi mở attach socket hoặc không tìm thấy process.

### Linux

So sánh danh tính:

```bash
id
ps -o pid,user,group,args -p <PID>
```

Chạy `jcmd` dưới cùng tài khoản service đã khởi chạy JVM, ví dụ qua cơ chế `sudo -u <service-user>` được tổ chức cho phép. Không dùng `sudo` tùy tiện như giải pháp mặc định; cần giữ đúng danh tính và môi trường của target process.

Với container, kiểm tra UID/GID bên trong container. Một user có cùng tên ở host và container có thể có UID khác nhau. Kiểm tra thêm policy bảo mật của container/OS nếu cùng UID/GID mà attach vẫn bị từ chối.

Với HotSpot trên Linux, attach protocol sử dụng file/socket tạm gắn với PID. Mount namespace hoặc temporary directory bị cô lập, read-only hay không truy cập được có thể làm client không tìm thấy endpoint của JVM. Kiểm tra `/proc`, thư mục tạm mà target nhìn thấy và quyền truy cập của process attach. Không xóa thủ công các file attach của JVM đang chạy để thử sửa lỗi.

### Windows

Đảm bảo công cụ chạy dưới tài khoản có quyền phù hợp với process đích và trong đúng session/environment. Nếu ứng dụng chạy dưới Windows Service account, mở terminal dưới tài khoản service hoặc dùng phương thức quản trị được cấp quyền. Kiểm tra executable và JDK path của service thay vì chỉ dựa vào JDK trong terminal cá nhân.

Không trộn lẫn process chạy elevated với công cụ chạy dưới tài khoản thường rồi suy đoán lỗi do JDK. Ghi nhận PID, user, executable path và thông báo lỗi đầy đủ trước khi thay đổi quyền.


## 6. Đọc lỗi theo đúng tầng

| Thông báo/lỗi | Ý nghĩa thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `AttachNotSupportedException: The VM does not support the attach mechanism` | PID/provider không tương thích hoặc attach bị tắt | Xác nhận PID, loại JVM, vendor và `-XX:+DisableAttachMechanism` |
| `Unable to open socket file ... target process ... doesn't respond ... or HotSpot VM not loaded` | Client không hoàn tất handshake với target | Kiểm tra PID, JVM vendor, quyền, namespace và endpoint tạm |
| `Permission denied` / `Operation not permitted` | OS từ chối truy cập hoặc gửi yêu cầu tới process | So sánh effective UID/GID, quyền Windows và policy container |
| `No such process` | PID không còn tồn tại hoặc PID sai namespace | Lấy lại PID từ process list trong cùng môi trường |
| `AgentLoadException` | Attach có thể đã thành công nhưng agent không nạp được | Kiểm tra đường dẫn agent, native library, format và khả năng đọc file |
| `AgentInitializationException` | Agent được gọi nhưng khởi tạo thất bại | Kiểm tra `agentmain`, log của target và exception từ agent |
| `AttachOperationFailedException` | Target JVM nhận request nhưng không hoàn tất operation | Đọc message chi tiết và log phía target |
| `Connection refused` khi debugger attach | JDWP server chưa lắng nghe hoặc sai host/port | Kiểm tra `-agentlib:jdwp`, port bind, firewall và tunnel |
| JConsole/JMC báo lỗi RMI/JMX | JMX endpoint, RMI port hoặc security cấu hình sai | Kiểm tra JMX port, RMI port, hostname, TLS và credentials |

Cần phân biệt lỗi attach với lỗi nạp agent. `VirtualMachine.attach(pid)` thiết lập kết nối tới target. Sau đó `loadAgent(...)` mới yêu cầu JVM nạp agent JAR và gọi `agentmain`. Nếu attach thành công nhưng agent thiếu `Agent-Class`, không có `agentmain`, sai đường dẫn hoặc không tương thích, hãy sửa agent thay vì tiếp tục đổi PID/quyền.

## 7. Quy trình chẩn đoán từng bước

Thực hiện theo thứ tự để xác định đúng điểm hỏng:

1. Ghi lại nguyên văn lỗi và công cụ đang dùng: `jcmd`, IDE debugger, JConsole hay JMX client.
2. Xác nhận process còn chạy và PID thuộc đúng JVM cần chẩn đoán.
3. Nếu có container, tìm PID bên trong đúng container/namespace.
4. Kiểm tra `java -version`, `jcmd -h` và version của target bằng công cụ phù hợp.
5. Xác nhận công cụ và JVM chạy trên cùng host, cùng effective user/group.
6. Kiểm tra target có Attach Provider tương thích và có bật `-XX:+DisableAttachMechanism` không.
7. Trên Linux/container, kiểm tra `/proc`, mount namespace, temporary endpoint và policy bảo mật.
8. Chạy lệnh nhẹ `jcmd <PID> VM.version` trước.
9. Nếu lệnh nhẹ thành công, chạy `jcmd <PID> help` để biết command mà JVM đó hỗ trợ.
10. Chỉ sau khi attach hoạt động mới thử tải agent hoặc chạy thao tác dump/profiling.
11. Lưu log, PID, JDK vendor/version, command line và thời điểm lỗi để so sánh giữa các lần chạy.

Lệnh xác nhận cơ bản:

```bash
jcmd <PID> VM.version
jcmd <PID> VM.command_line
jcmd <PID> help
```

Nếu `VM.version` thành công nhưng `GC.heap_dump` thất bại, attach mechanism có thể đang hoạt động; vấn đề có thể nằm ở quyền ghi file, dung lượng đĩa, option của diagnostic command hoặc trạng thái heap. Không quay lại điều tra PID nếu lệnh attach nhẹ đã chứng minh kết nối thành công.

## 8. Dùng jcmd để lấy dữ liệu sau khi attach thành công

Oracle khuyến nghị dùng `jcmd` thay cho các công cụ cũ `jstack`, `jinfo` và `jmap` trong nhiều tình huống chẩn đoán.

| Mục tiêu | Lệnh |
| --- | --- |
| JVM/JDK version | `jcmd <PID> VM.version` |
| Command line lúc khởi chạy | `jcmd <PID> VM.command_line` |
| JVM flags | `jcmd <PID> VM.flags` |
| System properties | `jcmd <PID> VM.system_properties` |
| Uptime | `jcmd <PID> VM.uptime` |
| Danh sách diagnostic commands | `jcmd <PID> help` |
| Thread dump | `jcmd <PID> Thread.print` |
| Heap summary | `jcmd <PID> GC.heap_info` |
| Class histogram | `jcmd <PID> GC.class_histogram` |
| Heap dump | `jcmd <PID> GC.heap_dump filename=heap.hprof` |
| Flight Recorder status | `jcmd <PID> JFR.check` |

Không phải JVM nào cũng cung cấp cùng command; dùng `jcmd <PID> help` để xem command thực tế. Mỗi command có mức ảnh hưởng khác nhau. `GC.heap_dump` và class histogram có thể gây pause, tiêu tốn I/O và tạo file lớn. Trước khi tạo heap dump trên production, kiểm tra dung lượng đĩa, tác động tới latency và quyền truy cập vào file dump. Heap dump có thể chứa token, password, dữ liệu cá nhân hoặc nội dung nhạy cảm trong bộ nhớ; lưu và chia sẻ theo chính sách bảo mật.

## 9. Ví dụ Java 17+: kiểm thử Attach API

Attach API thuộc module `jdk.attach`. Một công cụ Java có thể attach tới JVM bằng PID, đọc system properties hoặc nạp agent. Ví dụ sau chỉ đọc properties rồi detach.

Tệp `src/AttachTarget.java`:

```java
import java.util.concurrent.CountDownLatch;

public final class AttachTarget {
    private AttachTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("target-ready");
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.flush();

        new CountDownLatch(1).await();
    }
}
```

Tệp `src/AttachClient.java`:

```java
import com.sun.tools.attach.VirtualMachine;
import java.util.Properties;

public final class AttachClient {
    private AttachClient() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: AttachClient <pid>"
            );
        }

        VirtualMachine vm = VirtualMachine.attach(args[0]);
        try {
            Properties properties = vm.getSystemProperties();

            System.out.println("target.pid=" + vm.id());
            System.out.println(
                "target.java.version=" +
                properties.getProperty("java.version")
            );
            System.out.println(
                "target.os.name=" +
                properties.getProperty("os.name")
            );
        } finally {
            vm.detach();
        }
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
mkdir -p out

javac --release 17 -encoding UTF-8 \
  -d out src/AttachTarget.java

javac --release 17 --add-modules jdk.attach \
  -encoding UTF-8 -cp out \
  -d out src/AttachClient.java
```

Terminal thứ nhất chạy target:

```bash
java -cp out AttachTarget
```

Ghi lại PID được in ra. Terminal thứ hai chạy client:

```bash
java --add-modules jdk.attach -cp out AttachClient <PID>
```

Output mẫu:

```text
target.pid=<pid>
target.java.version=24.0.2
target.os.name=Windows 11
```

PID và thông tin OS/version phụ thuộc môi trường. Sau khi đọc properties, client gọi `detach()` trong `finally` để giải phóng kết nối kể cả khi thao tác đọc gặp lỗi.

Nếu chạy target với:

```bash
java -XX:+DisableAttachMechanism -cp out AttachTarget
```

client sẽ nhận `AttachNotSupportedException` với thông báo target không hỗ trợ attach mechanism. Để khôi phục, bỏ flag khi khởi chạy lại target. Thí nghiệm này đã được kiểm tra trên Windows 11, JDK 24.0.2; cả `jcmd` và Attach API đều attach thành công với target bình thường và đều thất bại đúng thông báo khi target bật `-XX:+DisableAttachMechanism`.

## 10. Khi cần debugger: kiểm tra JDWP

IDE debugger thường dùng Java Debug Wire Protocol (JDWP). JVM phải được khởi chạy với JDWP agent, ví dụ:

```bash
java \
  -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 \
  -jar app.jar
```

Sau đó cấu hình IDE hoặc `jdb` kết nối tới `127.0.0.1:5005`:

```bash
jdb -attach 5005
```

`server=y` khiến JVM mở endpoint chờ debugger. `suspend=n` cho phép ứng dụng chạy tiếp trong lúc chờ debugger; dùng `suspend=y` nếu cần dừng ngay khi khởi động để đặt breakpoint sớm.

Nếu debugger chạy trên máy khác, cần cấu hình địa chỉ bind, firewall và network route phù hợp. JDWP cấp quyền điều khiển/debug rất mạnh đối với process; chỉ mở endpoint trên loopback hoặc mạng quản trị được kiểm soát, và có thể dùng SSH tunnel. Không phơi cổng debug trực tiếp ra Internet.

Nếu JVM không được khởi chạy với JDWP agent, debugger attach qua TCP có thể báo connection refused dù `jcmd` vẫn attach thành công. Hai cơ chế phục vụ mục đích khác nhau.

## 11. Khi cần quản trị từ xa: dùng JMX

JMX là cơ chế monitoring/management qua MBeans. Java có thể hỗ trợ local management qua Attach API; remote management cần bật JMX agent và cấu hình network/security khi JVM khởi chạy.

Ví dụ bật remote JMX connector:

```bash
java \
  -Dcom.sun.management.jmxremote.port=9010 \
  -jar app.jar
```

Remote JMX cần cấu hình đúng RMI port, hostname, firewall và credentials. Java SE bật SSL và password authentication mặc định cho remote management agent. Với production, giữ authentication/TLS và cân nhắc client certificate; không tắt đồng thời cả SSL lẫn authentication để "sửa nhanh" lỗi kết nối. Nếu JMX hoạt động từ xa còn `jcmd` không chạy từ máy client, đó là hành vi đúng vì `jcmd` là công cụ attach local.

## 12. Container và Linux: các điểm dễ bỏ sót

Khi JVM chạy trong container, cần nhìn cùng process namespace và đúng user. Trên Linux HotSpot, attach protocol dùng endpoint trong thư mục tạm chung (thường là `/tmp`) và handshake với process đích. Nếu container tách mount namespace, làm `/tmp` read-only, ẩn `/proc` hoặc chặn quyền truy cập process, tool có thể không tìm thấy endpoint.

Kiểm tra:

```bash
id
ps -o pid,user,group,args -p <PID>
ls -ld /tmp
ls -l /tmp/.java_pid<PID>
```

File socket có thể chưa tồn tại cho tới khi attach listener được khởi tạo, vì vậy việc không thấy file ngay từ đầu chưa tự chứng minh JVM bị hỏng. Trước tiên thử `jcmd <PID> VM.version` từ cùng container/user. Không tạo, xóa hoặc sửa thủ công file `.java_pid<PID>` và `.attach_pid<PID>` khi chưa hiểu trạng thái process.

Một số môi trường container có security policy giới hạn signal hoặc truy cập `/proc`. Hãy kiểm tra policy, UID/GID, PID namespace, mount namespace và quyền của container runtime. Không cần cấp quyền đặc biệt rộng cho toàn bộ workload chỉ để một lần chẩn đoán; dùng debug container hoặc quyền tạm theo quy trình vận hành.

## 13. Nếu không thể attach: thu thập dữ liệu thay thế

Nếu attach bị tắt hoặc môi trường không cho phép kết nối, vẫn có thể thu thập một số dữ liệu khi JVM còn chạy.

### Lấy thread dump không qua Attach API

Trên Linux, gửi `SIGQUIT`:

```bash
kill -QUIT <PID>
```

Trên Windows, nhấn `Ctrl+Break` trong console của ứng dụng. HotSpot ghi thread dump ra standard output của process; ứng dụng tiếp tục chạy sau khi dump được in. Hãy tìm output trong log của service/container. Đừng dùng `kill -9` để thay cho `SIGQUIT`; `SIGKILL` kết thúc process ngay và không cho JVM tạo thread dump.

### Ghi Flight Recorder từ lúc khởi chạy

Nếu biết trước cần chẩn đoán nhưng có thể không attach được sau này, bật JFR khi start JVM:

```bash
java \
  -XX:StartFlightRecording:filename=recording.jfr,settings=default,dumponexit=true \
  -jar app.jar
```

Có thể cấu hình duration, maxage, maxsize và settings theo nhu cầu. `default` thường có overhead thấp hơn `profile`; profile thu thập chi tiết hơn và có thể tăng overhead. Khi sự cố xảy ra, dùng `jfr` hoặc JDK Mission Control để phân tích file recording.

### Tạo heap dump khi OutOfMemoryError

Có thể cấu hình từ startup:

```bash
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/secure/dumps \
  -jar app.jar
```

Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm. Bảo đảm thư mục tồn tại, có đủ dung lượng, quyền chỉ dành cho người được phép và retention phù hợp.

Với process đã treo hoặc JVM crash, có thể cần core dump/crash dump và công cụ postmortem như `jhsdb`, `gdb` hoặc WinDbg. Đây là hướng điều tra riêng, không phải thay thế tương đương cho dynamic attach.

## 14. Troubleshooting theo triệu chứng

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| IDE không thấy process trong danh sách | JVM ở container/namespace khác hoặc process không được liệt kê | Lấy PID trong đúng môi trường bằng `ps`, sau đó thử `jcmd <PID>` |
| `jcmd -l` không liệt kê ứng dụng | JVM chạy trong Docker process namespace riêng | Chạy `ps`/`jcmd` bên trong container |
| Attach thành công local nhưng fail trên CI | Khác user, JDK, container hoặc security policy | So sánh UID/GID, JDK path, PID namespace và runtime flags |
| Chỉ fail khi chạy bằng service account | Tool chạy dưới user khác | Chạy công cụ với cùng identity được cấp phép |
| `The VM does not support the attach mechanism` | Attach bị disable hoặc không có provider tương thích | Kiểm tra `-XX:+DisableAttachMechanism` và JVM vendor |
| `target process doesn't respond` | PID sai, target không phải HotSpot tương thích, target bị treo hoặc IPC bị chặn | Xác minh PID/version, thử cùng container và xem OS policy |
| `AgentLoadException` | Đường dẫn/format agent sai hoặc native library không nạp được | Kiểm tra agent JAR, manifest, architecture và log |
| `AgentInitializationException` | `agentmain` ném lỗi hoặc không khởi tạo được | Sửa agent và đọc output phía target |
| Debugger báo connection refused | JDWP agent chưa mở port hoặc sai host/port | Kiểm tra command line, bind address và firewall |
| JMX báo lỗi RMI | Thiếu RMI port, hostname không resolve hoặc TLS/auth không khớp | Cấu hình JMX/RMI cố định và kiểm tra certificate/credentials |
| Heap dump không ghi được | Thiếu disk, path không tồn tại hoặc permission sai | Kiểm tra path, dung lượng và quyền ghi |
| Thread dump không thấy trong terminal | Output được ghi vào log của service/container | Kiểm tra stdout/stderr log của đúng process |

## 15. Checklist trước khi kết luận JVM không thể attach

1. Đúng process và PID còn sống.
2. PID thuộc đúng host/container/process namespace.
3. Tool và target dùng JDK version tương thích.
4. Tool chạy trên cùng máy và cùng effective user/group với target.
5. JVM có Attach Provider tương thích.
6. `-XX:+DisableAttachMechanism` không được bật ngoài chủ đích.
7. `/proc`, thư mục tạm và attach endpoint có thể truy cập trong môi trường Linux/container.
8. OS/container security policy không chặn process access hoặc signal cần thiết.
9. Lệnh nhẹ `jcmd <PID> VM.version` đã được thử trước khi chạy heap dump/agent.
10. Đã phân biệt lỗi Attach API với JDWP debugger hoặc remote JMX.
11. Nếu attach không khả thi, đã cân nhắc thread dump qua SIGQUIT/Ctrl+Break, JFR startup recording hoặc heap dump khi OOM.
12. Diagnostic dump và credentials được lưu trong nơi có quyền truy cập phù hợp.

## 16. Ghi nhớ

- `jcmd`, `jstack`, `jmap` và `VirtualMachine.attach()` dùng JVM Attach API; JDWP và JMX là các cơ chế kết nối khác.
- `jcmd` cần chạy trên cùng máy và cùng effective user/group đã khởi chạy JVM.
- PID trong container có thể khác PID trên host; dùng PID trong đúng namespace.
- Dùng công cụ từ JDK tương thích với JVM đích; tránh trộn tool giữa các JDK version.
- `-XX:+DisableAttachMechanism` tắt attach; muốn bật lại cần thay đổi startup configuration và restart.
- `AttachNotSupportedException` thường chỉ ra PID/provider/target không tương thích hoặc attach không được hỗ trợ.
- `AgentLoadException` và `AgentInitializationException` xảy ra ở giai đoạn nạp/khởi tạo agent sau khi attach.
- Chạy `jcmd <PID> VM.version`, `VM.command_line`, `help` trước các lệnh chẩn đoán nặng.
- Với Linux/container, kiểm tra UID/GID, `/proc`, PID namespace, mount namespace và endpoint tạm.
- Khi không thể attach, có thể lấy thread dump bằng `kill -QUIT` hoặc Ctrl+Break, bật JFR/heap dump từ startup, hoặc dùng công cụ postmortem.
- Không mở JDWP/JMX ra mạng công cộng; giữ xác thực, TLS và firewall phù hợp.

Khi không attach được JVM, hãy xác định cơ chế kết nối, process/PID và danh tính chạy trước; sau đó kiểm tra provider, JDK, startup flags và ranh giới container. Việc đọc đúng exception sẽ cho biết lỗi xảy ra trước khi kết nối, trong lúc attach hay sau khi nạp agent, giúp chọn cách khắc phục phù hợp và thu thập được dữ liệu chẩn đoán cần thiết.

## Tài liệu tham khảo

- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Diagnostic Tools — Java SE 24](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [The java Command — DisableAttachMechanism and JFR startup options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Attach API: VirtualMachine — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html)
- [Attach API package — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html)
- [AttachNotSupportedException — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.attach/com/sun/tools/attach/AttachNotSupportedException.html)
- [The jdb Command — JDWP connection](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [Monitoring and Management Using JMX Technology — Java SE 24](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html)
- [OpenJDK Attach implementation on Linux — temporary endpoint and process namespaces](https://cr.openjdk.org/~gadams/8188856/webrev.03/src/jdk.attach/linux/classes/sun/tools/attach/VirtualMachineImpl.java.sdiff.html)
