# Đóng debug endpoint của JVM bằng JDWP

**Debug endpoint của JVM** thường là cổng TCP mà Java Debug Wire Protocol (JDWP) agent mở để IDE hoặc debugger kết nối tới một tiến trình Java đang chạy. Trên HotSpot JDK, agent thường được bật bằng tùy chọn **-agentlib:jdwp**.

Khi kết thúc một phiên debug, cần phân biệt ba việc:

1. **Detach debugger:** ngắt kết nối IDE/debugger hiện tại.
2. **Close the debug endpoint:** đóng listener/cổng mà JVM đang mở để debugger khác không thể kết nối.
3. **Stop the JVM:** kết thúc tiến trình Java, làm socket JDWP đóng cùng tiến trình.

Detach chỉ thực hiện việc thứ nhất. Với JDWP server đang chạy, listener có thể tiếp tục chờ một debugger khác. Muốn đóng hẳn endpoint của JVM, hãy dừng ứng dụng một cách có kiểm soát rồi khởi động lại mà không nạp JDWP agent. Nếu chưa thể restart ngay, hãy chặn truy cập tới cổng bằng firewall hoặc network policy trong lúc chuẩn bị cửa sổ restart.

## 1. Xác định endpoint đang được mở ở đâu

JDWP socket transport dùng kết nối TCP giữa debugger và target JVM. Hai phía có thể đổi vai trò server/client:

| JDWP option | Vai trò của target JVM | Nơi mở listener |
|---|---|---|
| `server=y` | Target JVM chờ debugger kết nối vào | JVM đang debug |
| `server=n` | Target JVM chủ động kết nối tới debugger | Máy chạy debugger |

Ví dụ target JVM mở cổng 5005:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

- `transport=dt_socket`: dùng TCP socket.
- `server=y`: JVM đóng vai trò server và lắng nghe kết nối debugger.
- `suspend=n`: ứng dụng được chạy ngay, không chờ debugger attach.
- `address=127.0.0.1:5005`: chỉ lắng nghe trên loopback của máy JVM.

Nếu dùng `server=n`, JVM là client và cần địa chỉ của debugger:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

Trong trường hợp này, cổng listener nằm ở máy debugger. Hãy đóng listening connector của debugger khi không còn target nào cần kết nối.

Windows còn hỗ trợ transport `dt_shmem` qua shared memory. Với transport này không có TCP port để kiểm tra; cần quản lý phiên kết nối và vòng đời tiến trình tương ứng.

## 2. Vì sao phải đóng debug endpoint sau khi điều tra?

JDWP là kênh điều khiển JVM có quyền rất cao. Theo đặc tả JDWP, debugger có thể đọc và thay đổi field private, gọi method private, suspend/resume thread, đọc stack và yêu cầu JVM thoát. Giao thức không thực thi Java access control đối với các thao tác này.

Nếu một JDWP listener không cần thiết vẫn mở, người có thể kết nối tới endpoint có thể kiểm soát tiến trình Java trong phạm vi quyền mà debugger protocol cung cấp. Đặc biệt cần tránh mở cổng debug trên mọi network interface ở môi trường production.

Một số dấu hiệu cần kiểm tra:

- Log khởi động có dòng `Listening for transport dt_socket at address: 5005`.
- `jcmd <pid> VM.command_line` cho thấy JVM được khởi động với `-agentlib:jdwp`.
- Hệ điều hành báo process Java đang ở trạng thái `LISTEN` trên cổng debug.
- Container hoặc service có port mapping dành riêng cho remote debug.
- Các biến môi trường hoặc cấu hình chạy service tự động thêm JDWP options.

Không xem debug port như một cổng ứng dụng thông thường. Người có thể kết nối JDWP có quyền điều khiển quá trình thực thi của JVM.

## 3. Detach debugger không đóng listener

Khi IDE chọn **Disconnect** hoặc **Detach**, debugger gửi yêu cầu dispose qua JDI/JDWP. Theo JDK 24 JDI API, `VirtualMachine.dispose()` đóng communication channel của debugger, hủy event requests và resume các thread đã bị debugger suspend. Target JVM sau đó **chuẩn bị nhận một kết nối debugger tiếp theo**.

Vì vậy, sau khi bấm Disconnect:

- Breakpoint và event request của debugger hiện tại bị hủy.
- Các thread bị debugger suspend được resume.
- Ứng dụng tiếp tục chạy.
- JDWP listener của target JVM vẫn có thể ở trạng thái LISTEN.
- Một debugger khác có thể attach lại vào cùng JVM.

Đây là hành vi có chủ đích để hỗ trợ detach rồi attach lại mà không cần restart ứng dụng.

~~~text
IDE debugger A
      |
      | JDWP attach
      v
Target JVM + JDWP listener
      |
      | JDI VirtualMachine.dispose()
      v
Debugger A disconnected
      |
      +----> JVM continues running
      |
      +----> Listener accepts debugger B
~~~

Không nhầm `VirtualMachine.dispose()` với `VirtualMachine.exit()`. `exit()` yêu cầu target JVM kết thúc; các thread bị chấm dứt đột ngột và `finally` block không được bảo đảm chạy. Không dùng thao tác này thay cho quy trình shutdown ứng dụng bình thường.

## 4. Quy trình đóng hẳn endpoint an toàn

### Bước 1: xác định đúng JVM và cổng debug

Liệt kê các Java process:

~~~sh
jcmd -l
~~~

Ví dụ:

~~~text
25884 DebugEndpointProbe
57488 com.example.OrderService
~~~

Xem command line của JVM cần kiểm tra:

~~~sh
jcmd 57488 VM.command_line
~~~

Tìm các tham số:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

Lệnh này giúp xác định agent, transport, server/client mode và địa chỉ khởi chạy. Không lấy PID từ một lần chạy cũ; hãy đối chiếu process hiện tại trước khi thao tác.

Kiểm tra listener trên Windows:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 | Format-Table LocalAddress, LocalPort, State, OwningProcess
~~~

Xem process sở hữu cổng:

~~~powershell
Get-Process -Id 57488
~~~

Trên Linux:

~~~sh
ss -ltnp 'sport = :5005'
~~~

Hoặc:

~~~sh
lsof -nP -iTCP:5005 -sTCP:LISTEN
~~~

Xác nhận cổng thuộc đúng JVM cần đóng. Một cổng có thể đã được process khác sử dụng sau khi ứng dụng cũ dừng.

### Bước 2: kết thúc phiên debug đúng cách

Trước khi detach:

1. Lưu các thông tin cần thiết từ debugger, ví dụ stack trace, breakpoint và biến đang kiểm tra.
2. Resume các thread đang bị suspend bởi breakpoint hoặc thao tác debug.
3. Gỡ breakpoint nếu IDE cần tái sử dụng cấu hình cho lần debug sau.
4. Chọn **Disconnect/Detach** trong IDE.
5. Chờ IDE xác nhận phiên debug đã kết thúc.

Bước này giúp ứng dụng tiếp tục chạy bình thường. Nó chưa đóng JDWP listener.

### Bước 3: dừng ứng dụng một cách có kiểm soát

Nếu cần đóng endpoint, hãy dừng target JVM theo lifecycle của ứng dụng:

- Với service Linux, dùng service manager hoặc quy trình deploy/restart đang quản lý service.
- Với Windows Service, dùng Services hoặc công cụ quản lý service tương ứng.
- Với container/Kubernetes, drain traffic, dừng pod hoặc rollout theo quy trình triển khai.
- Với ứng dụng chạy foreground trong terminal, dùng cơ chế shutdown của ứng dụng hoặc nhấn `Ctrl+C` nếu chương trình xử lý shutdown signal phù hợp.

Không dùng `Stop-Process -Force` hoặc `kill -9` làm bước mặc định. Cách kết thúc cưỡng bức có thể bỏ qua shutdown hook, không flush dữ liệu và làm mất công việc đang xử lý.

Khi JVM thoát, socket JDWP thuộc tiến trình đó được đóng cùng process.

### Bước 4: khởi động lại mà không nạp JDWP agent

Xóa tham số debug khỏi cấu hình khởi chạy:

~~~text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

Kiểm tra các nguồn có thể tự thêm JVM options:

- Cấu hình service hoặc startup script.
- `JAVA_TOOL_OPTIONS`.
- `JDK_JAVA_OPTIONS`.
- `JAVA_OPTS` hoặc biến riêng của framework/container.
- Docker Compose, Kubernetes Deployment, Helm values hoặc manifest triển khai.
- Run/Debug configuration của IDE hoặc script khởi động local.

Nếu chỉ xóa option khỏi command line tạm thời nhưng cấu hình service vẫn giữ nó, lần restart tiếp theo endpoint sẽ mở lại.

Khởi động service theo cấu hình đã bỏ JDWP. Sau đó kiểm tra `jcmd <pid> VM.command_line` để xác nhận JVM mới không còn tham số `-agentlib:jdwp`.

## 5. Nếu chưa thể restart ngay

Trong một số tình huống, cần tiếp tục phục vụ request và chưa thể restart JVM ngay. Khi đó, hãy hạn chế đường truy cập tới cổng debug bằng host firewall, network firewall, security group hoặc network policy.

Ví dụ Windows Firewall, chặn inbound TCP tới cổng 5005:

~~~powershell
New-NetFirewallRule -DisplayName "Block JDWP 5005" -Direction Inbound -Protocol TCP -LocalPort 5005 -Action Block
~~~

Khi không còn cần rule này, xóa theo đúng tên:

~~~powershell
Remove-NetFirewallRule -DisplayName "Block JDWP 5005"
~~~

Trên Linux có thể dùng firewall của hệ điều hành hoặc network policy của hạ tầng. Ví dụ với UFW:

~~~sh
sudo ufw deny 5005/tcp
sudo ufw status numbered
~~~

**Firewall chỉ chặn đường truy cập mạng; socket vẫn có thể ở trạng thái LISTEN trong JVM.** Đây là biện pháp hạn chế khẩn cấp trong lúc chờ restart, không phải bằng chứng endpoint đã đóng. Sau khi có cửa sổ bảo trì, hãy bỏ JDWP khỏi startup options, restart ứng dụng và xác minh listener đã biến mất.

Nếu JDWP port được publish qua Docker hoặc Kubernetes, hãy gỡ port mapping/service exposure và kiểm tra cả network policy. Chỉ đóng firewall trên host có thể chưa đủ nếu một lớp proxy hoặc port forwarding khác vẫn công khai cổng.

## 6. Cấu hình debug an toàn cho lần sau

Tốt nhất là không bật JDWP trong cấu hình production thông thường. Chỉ bật trong một lần chạy hoặc một giai đoạn điều tra có kiểm soát.

### 6.1. Chỉ debug từ cùng máy

Bind listener vào loopback:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Kết nối chỉ có thể được thực hiện qua loopback của máy JVM. Không dùng `address=*:5005` nếu không có yêu cầu remote access rõ ràng.

Trong JDK 24, dạng `address=5005` cũng mặc định lắng nghe trên loopback. Việc ghi rõ `127.0.0.1` làm ý định cấu hình dễ đọc và kiểm tra hơn.

### 6.2. Remote debug qua SSH tunnel

Có thể giữ JDWP listener trên loopback của server rồi tạo SSH tunnel từ máy debugger:

~~~sh
ssh -L 5005:127.0.0.1:5005 user@debug-host
~~~

Sau đó cấu hình IDE kết nối tới:

~~~text
localhost:5005
~~~

Tunnel chuyển lưu lượng từ cổng local của máy debugger tới loopback của máy JVM. Cách này tránh phải mở listener JDWP ra mọi interface.

### 6.3. Remote debug qua private network có allowlist

Nếu kiến trúc bắt buộc cần kết nối trực tiếp, hãy bind trên interface phù hợp, giới hạn IP nguồn và cấu hình firewall ở hạ tầng.

Ví dụ:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=192.0.2.25+198.51.100.0/24 -jar app.jar
~~~

- `address=*:5005`: listener nhận kết nối trên mọi network interface.
- `allow=...`: chỉ cho phép IP hoặc subnet đã liệt kê.
- Các địa chỉ trong danh sách `allow` được phân cách bằng dấu `+`.
- Với `dt_socket`, giá trị mặc định của `allow` là `*`, tức cho phép mọi địa chỉ.

Allowlist là một lớp giới hạn nguồn kết nối. Vẫn cần firewall/network ACL và quy trình mở/đóng endpoint có thời hạn. Không dùng wildcard `*` như một biện pháp bảo mật.

Tùy chọn `timeout=5000` trong chế độ `server=y` giới hạn thời gian chờ debugger attach ban đầu theo transport. Nó không phải bộ đếm thời gian tự đóng listener sau khi debugger đã attach rồi detach.

## 7. Kiểm tra endpoint đã đóng thật sự

Sau khi restart JVM không có JDWP, hãy kiểm tra cả command line và socket.

### Windows

Tìm JVM mới:

~~~powershell
jcmd -l
~~~

Kiểm tra JVM options:

~~~powershell
jcmd <pid> VM.command_line
~~~

Không còn `-agentlib:jdwp` hoặc `-Xrunjdwp` trong command line.

Kiểm tra listener:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 -ErrorAction SilentlyContinue
~~~

Nếu không có kết quả, hiện không có TCP listener trên port 5005. Nếu có kết quả, kiểm tra `OwningProcess` để xác định process đang giữ cổng.

Có thể kiểm tra từ máy khác:

~~~powershell
Test-NetConnection debug-host -Port 5005
~~~

Sau khi đóng endpoint, kết nối từ máy được phép truy cập phải thất bại. Nếu firewall đang chặn, kết quả này chỉ xác nhận đường mạng bị chặn; cần kiểm tra thêm listener tại host để phân biệt với việc socket đã đóng.

### Linux

~~~sh
jcmd -l
jcmd <pid> VM.command_line
ss -ltnp 'sport = :5005'
~~~

Nếu không còn dòng `LISTEN` cho port 5005, socket listener đã biến mất. Nếu vẫn có, kiểm tra PID/process sở hữu cổng trước khi kết luận.

Đừng chỉ kiểm tra IDE đã disconnected hoặc `Test-NetConnection` bị timeout. Hãy xác nhận process và trạng thái socket ở máy đang chạy JVM.

## 8. Ví dụ Java 17+ thực hành mở và đóng debug endpoint

Ví dụ tạo một JVM chờ chạy. Shutdown hook in thông báo khi ứng dụng nhận tín hiệu kết thúc bình thường.

Tạo file `DebugEndpointProbe.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class DebugEndpointProbe {
    public static void main(String[] args) throws InterruptedException {
        Runtime.getRuntime().addShutdownHook(new Thread(
            () -> System.out.println("debug-endpoint-stopped")
        ));

        System.out.println("debug-endpoint-ready");
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~sh
mkdir -p out
javac --release 17 -d out DebugEndpointProbe.java
~~~

Khởi chạy với JDWP listener chỉ trên loopback:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugEndpointProbe
~~~

Output:

- JDWP agent ghi ra stderr:

~~~text
Listening for transport dt_socket at address: 5005
~~~

- Ứng dụng ghi ra stdout:

~~~text
debug-endpoint-ready
~~~

Mở terminal thứ hai và tìm PID:

~~~sh
jcmd -l
~~~

Kiểm tra listener trên Windows:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

Khi muốn đóng endpoint trong bài thực hành, quay lại terminal đang chạy ứng dụng và nhấn `Ctrl+C`. Shutdown hook ghi ra stdout:

~~~text
debug-endpoint-stopped
~~~

Kiểm tra lại:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005 -ErrorAction SilentlyContinue
~~~

Không còn kết quả nghĩa là listener đã đóng. Trên Linux, dùng `ss -ltnp 'sport = :5005'` để xác nhận.

## 9. Ví dụ JDI: detach nhưng listener vẫn mở

Đoạn code sau dùng JDI SocketAttach để kết nối tới JVM rồi gọi `VirtualMachine.dispose()`. Nó minh họa việc đóng phiên debugger mà không kết thúc target JVM.

Tạo file `DetachProbe.java`:

~~~java
import com.sun.jdi.Bootstrap;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.connect.AttachingConnector;
import com.sun.jdi.connect.Connector;
import java.util.Map;

public class DetachProbe {
    public static void main(String[] args) throws Exception {
        AttachingConnector connector =
            Bootstrap.virtualMachineManager().attachingConnectors().stream()
                .filter(c -> c.name().equals("com.sun.jdi.SocketAttach"))
                .findFirst()
                .orElseThrow();

        Map<String, Connector.Argument> values = connector.defaultArguments();
        values.get("hostname").setValue("127.0.0.1");
        values.get("port").setValue(args[0]);

        VirtualMachine vm = connector.attach(values);
        System.out.println("debugger-attached");

        vm.dispose();

        System.out.println("debugger-detached");
    }
}
~~~

Biên dịch:

~~~sh
javac --release 17 --add-modules jdk.jdi -d out DetachProbe.java
~~~

Giả sử target JVM đang mở port 5005:

~~~sh
java --add-modules jdk.jdi -cp out DetachProbe 5005
~~~

Stdout chính xác:

~~~text
debugger-attached
debugger-detached
~~~

Sau khi helper kết thúc, kiểm tra:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 5005
~~~

Listener vẫn có thể tồn tại và debugger khác có thể attach lại. Khi target JVM được dừng bằng Ctrl+C trong ví dụ trước, shutdown hook chạy và socket listener biến mất.

Đây là phép thử quan trọng để xác nhận detach và close endpoint là hai hành động khác nhau.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| IDE báo Disconnected nhưng cổng vẫn LISTEN | Debugger chỉ detach; target JVM vẫn giữ JDWP listener | Dừng/restart JVM không có JDWP agent |
| Restart xong cổng lại mở | Startup script, environment variable hoặc manifest vẫn thêm `-agentlib:jdwp` | Kiểm tra VM.command_line và cấu hình deploy |
| Cổng 5005 vẫn mở sau khi process cũ dừng | Process khác đang dùng lại cổng | Xem OwningProcess/PID rồi xác định đúng process |
| Không kết nối được dù listener đang mở | Firewall, allowlist, bind address hoặc routing chặn kết nối | Kiểm tra LocalAddress, allow, security group và network policy |
| Debugger không attach được | Sai server/client mode, sai địa chỉ hoặc port | Đối chiếu server, address và log khởi động |
| Ứng dụng đứng ở startup | `suspend=y` khiến JVM chờ debugger | Attach debugger hoặc dừng JVM theo quy trình phù hợp |
| Đã thêm firewall rule nhưng ss vẫn hiện LISTEN | Firewall chỉ chặn kết nối; socket vẫn thuộc JVM | Restart JVM không có agent để đóng listener |
| Dùng `-XX:+DisableAttachMechanism` nhưng debug port vẫn mở | Tùy chọn này kiểm soát Attach API; không phải lệnh dừng JDWP listener đã được nạp | Bỏ JDWP agent và restart JVM |
| Dùng `VirtualMachine.dispose()` nhưng JVM vẫn debug được lần nữa | Dispose chuẩn bị target VM nhận debugger tiếp theo | Dừng/restart target JVM để đóng endpoint |
| Cổng không mở khi `server=n` | Target JVM đang kết nối ra debugger, không phải server | Kiểm tra listener ở máy debugger |

## 11. Quy trình vận hành sau một phiên debug

1. Xác định JVM, PID, transport và địa chỉ debug đang dùng.
2. Lưu dữ liệu điều tra cần thiết.
3. Resume các thread bị suspend và detach debugger.
4. Xác nhận ứng dụng tiếp tục phục vụ bình thường.
5. Lên lịch graceful stop/restart nếu JDWP listener cần được đóng.
6. Xóa JDWP option khỏi service startup, environment và deployment manifest.
7. Khởi động JVM mới không có JDWP agent.
8. Dùng `jcmd <pid> VM.command_line` để xác nhận command line.
9. Dùng `Get-NetTCPConnection` hoặc `ss` để xác nhận không còn listener.
10. Nếu chưa restart được, chặn inbound port bằng firewall/network policy và ghi nhận đây là biện pháp tạm thời.
11. Kiểm tra lại sau lần deploy/restart tiếp theo để bảo đảm endpoint không tự mở lại.

### Checklist

- [ ] Đã xác định đúng JVM/PID và cổng debug.
- [ ] Đã phân biệt `server=y` với `server=n`.
- [ ] Đã hiểu detach debugger không đóng JDWP listener.
- [ ] Đã resume các thread bị debugger suspend trước khi detach.
- [ ] Đã dừng JVM theo quy trình graceful hoặc restart service.
- [ ] Đã bỏ JDWP options khỏi startup config và environment.
- [ ] Đã kiểm tra `VM.command_line` của JVM mới.
- [ ] Đã xác nhận không còn TCP listener trên debug port.
- [ ] Đã dùng firewall/network policy nếu cần biện pháp chặn tạm thời.
- [ ] Đã kiểm tra Docker/Kubernetes port mapping nếu ứng dụng chạy trong container.
- [ ] Đã xác nhận endpoint không mở lại sau lần restart/deploy tiếp theo.

Đóng debug endpoint nghĩa là listener JDWP không còn chấp nhận kết nối mới. Detach debugger chỉ đóng phiên điều khiển hiện tại; target JVM vẫn có thể tiếp tục lắng nghe. Hãy kết thúc ứng dụng theo lifecycle, bỏ `-agentlib:jdwp` khỏi cấu hình khởi chạy, restart rồi xác minh cả command line lẫn socket listener. Khi chưa thể restart, firewall giúp chặn truy cập trong thời gian chờ nhưng không thay thế việc đóng listener.

## Tài liệu tham khảo

- [Oracle JDK 24 — The java Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle JDK 24 — JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [Oracle JDK 24 — JDI VirtualMachine API](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jdi/com/sun/jdi/VirtualMachine.html)
- [Oracle JDK 24 — JDWP Protocol Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-protocol.html)
- [Oracle JDK 24 — Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html)