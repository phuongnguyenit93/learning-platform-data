# Cấu hình debug port cho JVM Java

## 1. Debug port là gì?

Debug port là cổng TCP mà Java Virtual Machine (JVM) dùng để trao đổi dữ liệu gỡ lỗi với debugger thông qua Java Debug Wire Protocol (JDWP). Khi bật JDWP agent, một debugger như IntelliJ IDEA, Eclipse hoặc JDB có thể kết nối tới JVM để đặt breakpoint, xem stack trace, kiểm tra biến, chạy từng bước và tiếp tục hoặc tạm dừng thread.

Debug port thường là một cổng riêng, ví dụ `5005`. Nó không phải HTTP port của ứng dụng, không phải cổng JMX và cũng không phải cổng của `jcmd`.

Một phiên remote debugging có hai đầu:

- **Target JVM:** process Java đang chạy ứng dụng và cần được debug.
- **Debugger:** IDE hoặc JDB kết nối tới target để gửi lệnh debug.

JDWP agent nằm trong target JVM. Transport `dt_socket` truyền các gói JDWP qua TCP/IP. Khi debugger và JVM ở hai máy khác nhau, địa chỉ và port phải có thể kết nối qua mạng.

## 2. JPDA, JDI và JDWP liên quan thế nào?

Java Platform Debugger Architecture (JPDA) gồm các thành phần phối hợp:

| Thành phần | Vai trò |
|---|---|
| JPDA | Kiến trúc tổng thể cho việc debug Java. |
| JDI (Java Debug Interface) | API phía debugger để điều khiển target VM. |
| JDWP (Java Debug Wire Protocol) | Giao thức trao đổi lệnh và phản hồi giữa debugger và JVM. |
| JDWP agent | Thành phần được nạp vào target JVM để thực hiện giao thức. |
| Transport | Kênh truyền dữ liệu, thường là TCP socket `dt_socket`. |

IDE dùng JDI để tạo kết nối và gửi yêu cầu. JDWP agent trong JVM xử lý yêu cầu đó và trả về thông tin từ runtime. Với socket transport, dữ liệu đi qua một kết nối TCP.

Debug port chính là địa chỉ transport mà hai bên dùng để gặp nhau. Cả debugger và JVM phải thống nhất host, port và chiều kết nối.

## 3. Hai chiều kết nối: server=y và server=n

Tùy chọn `server` mô tả vai trò mạng của target JVM:

| Cấu hình | Target JVM làm gì? | Debugger làm gì? | Khi dùng |
|---|---|---|---|
| `server=y` | Mở cổng và chờ debugger kết nối. | Chủ động attach tới JVM. | Cách phổ biến khi IDE kết nối tới ứng dụng. |
| `server=n` | Chủ động kết nối tới debugger đang lắng nghe. | Mở listener và chờ JVM kết nối. | Khi mạng chỉ cho phép kết nối đi từ máy chạy ứng dụng. |

Với `server=y`, JVM là TCP server. Với `server=n`, debugger là TCP server. Tên server không có nghĩa debugger luôn là server.

Cách phổ biến nhất là `server=y`: ứng dụng mở debug port, sau đó IDE chọn Attach to remote JVM và kết nối vào host/port đó.

## 4. Cú pháp JDWP agent

Nạp JDWP agent khi khởi chạy JVM bằng:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Cú pháp tổng quát:

~~~text
-agentlib:jdwp=<option>=<value>,<option>=<value>,...
~~~

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `transport` | Transport dùng để trao đổi dữ liệu. Với TCP/IP là `dt_socket`. |
| `server` | `y` để JVM lắng nghe debugger; `n` để JVM kết nối tới debugger. |
| `address` | Địa chỉ và port của đầu lắng nghe hoặc đầu cần kết nối. |
| `suspend` | `y` để tạm dừng JVM cho tới khi debugger kết nối; `n` để ứng dụng chạy ngay. |
| `timeout` | Thời gian chờ kết nối, tính bằng milliseconds. |
| `allow` | Với `server=y` và `dt_socket`, giới hạn IP/subnet được phép kết nối. |

Dùng dấu phẩy để phân cách các tùy chọn. Không thêm khoảng trắng bên trong chuỗi JDWP vì JVM có thể coi đó là phần của giá trị.

Xem danh sách option được hỗ trợ trên JDK đang dùng:

~~~bash
java -agentlib:jdwp=help
~~~

JDK 24.0.2 trong bài thực hành xác nhận các option `transport`, `server`, `address`, `suspend` và `allow`. Giá trị mặc định của `suspend` là `y`; `server` mặc định là `n`.

## 5. Chọn địa chỉ bind cho debug port

Địa chỉ bind quyết định interface nào nhận kết nối:

| Địa chỉ | Hành vi |
|---|---|
| `address=5005` | Lắng nghe trên loopback theo mặc định của socket transport JDK 24. |
| `address=127.0.0.1:5005` | Chỉ lắng nghe trên IPv4 loopback. |
| `address=localhost:5005` | Lắng nghe trên loopback được phân giải từ hostname. |
| `address=*:5005` | Lắng nghe trên tất cả network interface. |

Đối với debug trên cùng máy, nên bind loopback:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Khi debugger chạy ở máy khác, target cần lắng nghe trên interface có thể truy cập được. Có thể dùng:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar app.jar
~~~

`address=*:5005` làm cổng lắng nghe xuất hiện trên mọi network interface. Chỉ sử dụng khi đã giới hạn kết nối bằng firewall, allow list hoặc mạng riêng. Không mở cổng debug ra Internet công cộng.

Port `5005` là một quy ước phổ biến, không phải port bắt buộc. Có thể chọn port TCP khác còn trống và được phép qua firewall.

## 6. Hiểu suspend=y và suspend=n

`suspend` quyết định ứng dụng có chạy trước khi debugger kết nối hay không:

**suspend=y**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

JVM mở debug port rồi tạm dừng trước khi chạy main class. Ứng dụng chờ debugger kết nối. Đây là lựa chọn phù hợp khi cần debug:

- Lỗi xảy ra ngay trong static initializer hoặc constructor lúc startup.
- Class loading hoặc Spring/application initialization.
- Cấu hình chỉ tồn tại trong giai đoạn khởi động.
- Một lỗi xuất hiện trước khi người vận hành có thể attach.

Nếu debugger không kết nối, ứng dụng có thể tiếp tục bị treo ở giai đoạn startup. Trong môi trường triển khai có health check, điều này có thể khiến instance bị đánh dấu unhealthy.

**suspend=n**

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

JVM khởi chạy ứng dụng ngay cả khi chưa có debugger. Dùng lựa chọn này khi muốn attach vào một process đang hoạt động, quan sát một request hoặc điều tra vấn đề xuất hiện sau startup.

Với `server=y`, `suspend=y` là mặc định. Nên ghi rõ `suspend` trong cấu hình để người vận hành hiểu ứng dụng sẽ chờ hay chạy ngay.

## 7. Bật debug port cho ứng dụng chạy bằng JAR

Có thể truyền JDWP agent trực tiếp vào lệnh `java`:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar service.jar
~~~

Nếu ứng dụng nhận thêm JVM option, đặt option debug trước `-jar`:

~~~bash
java -Xms512m -Xmx1g -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar service.jar
~~~

Đối với ứng dụng chạy bằng classpath:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out com.example.Main
~~~

JDWP là option của JVM, vì vậy phải đặt trước tên class chính hoặc `-jar`. Đặt nó sau tên class sẽ khiến JVM chuyển chuỗi đó thành argument của ứng dụng.

## 8. Bật debug port bằng biến môi trường hoặc script khởi chạy

Trong Docker, Kubernetes hoặc service script, có thể thêm JDWP vào biến JVM option mà entrypoint sử dụng.

Ví dụ:

~~~bash
JAVA_TOOL_OPTIONS="-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005"
export JAVA_TOOL_OPTIONS
java -jar app.jar
~~~

JVM tự đọc `JAVA_TOOL_OPTIONS` khi khởi chạy. Log startup thường hiển thị thông báo cho biết option đã được áp dụng.

Nếu dùng `JAVA_OPTS`, cần chắc chắn script khởi chạy thực sự đưa biến này vào lệnh `java`. `JAVA_OPTS` không phải biến JVM tự động đọc trong mọi môi trường.

Không thêm cùng một JDWP agent hai lần, ví dụ vừa đặt trong `JAVA_TOOL_OPTIONS` vừa đặt trong command line. Việc nạp agent lặp lại có thể làm JVM khởi động lỗi hoặc chiếm port không như mong muốn.

## 9. Kết nối debugger bằng JDB

JDB là debugger dòng lệnh đi kèm JDK. Khi target JVM đang lắng nghe ở localhost port 5005, có thể kết nối qua socket connector:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Trên Linux/macOS, shortcut sau thường dùng socket connector mặc định:

~~~bash
jdb -attach 127.0.0.1:5005
~~~

Trên Windows, `jdb -attach` mặc định có thể chọn shared-memory connector. Nếu target JVM đang dùng TCP socket, lệnh đó có thể báo lỗi kiểu `shmemBase_attach failed`. Dùng connector tường minh để kết nối TCP:

~~~powershell
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Sau khi kết nối, JDB mở prompt. Một số lệnh hữu ích:

| Lệnh | Tác dụng |
|---|---|
| `help` | Xem danh sách lệnh. |
| `threads` | Liệt kê thread trong target JVM. |
| `thread <id>` | Chọn thread cần kiểm tra. |
| `where` | Hiển thị stack trace của thread hiện tại. |
| `where all` | Hiển thị stack trace của các thread. |
| `stop at ClassName:line` | Đặt breakpoint theo số dòng. |
| `stop in ClassName.method` | Đặt breakpoint theo method. |
| `locals` | Hiển thị local variable khi thread đang suspend. |
| `print expression` | Đánh giá và in giá trị biểu thức. |
| `next` | Chạy tới dòng tiếp theo, không đi vào method call. |
| `step` | Đi vào method call tiếp theo. |
| `cont` | Tiếp tục chạy target. |
| `clear` | Xóa breakpoint. |
| `exit` | Thoát JDB. |

Ví dụ:

~~~text
stop at com.example.Main:42
cont
locals
where
next
cont
~~~

Breakpoint theo dòng cần class được biên dịch có thông tin debug phù hợp. Khi dùng `javac`, thêm `-g` để giữ thông tin local variable và line number:

~~~bash
javac --release 17 -g -d out src/com/example/Main.java
~~~

## 10. Kết nối bằng IDE

Với IntelliJ IDEA, Eclipse hoặc IDE có hỗ trợ remote debugging, tạo cấu hình Remote JVM Debug hoặc Attach to Remote JVM.

Các trường cần điền:

| Trường | Giá trị ví dụ |
|---|---|
| Debugger mode | Attach to remote JVM |
| Host | `127.0.0.1` nếu debug local hoặc qua tunnel |
| Port | `5005` |
| Transport | Socket / TCP |
| Module / classpath | Module chứa source code của ứng dụng |

Sau khi target JVM đã mở port, nhấn Debug/Attach trong IDE. Khi kết nối thành công, IDE có thể hiển thị thread, stack frame, local variable và breakpoint.

Source code trong IDE phải tương ứng với phiên bản class đang chạy. Nếu source và bytecode không khớp, breakpoint có thể bị lệch dòng hoặc không được xác nhận.

## 11. Dùng server=n khi debugger phải lắng nghe trước

Trong một số mạng, target không được phép mở cổng inbound nhưng có thể tạo kết nối outbound tới máy phát triển. Khi đó, để debugger làm TCP server, mở socket listener bằng JDI connector:

~~~bash
jdb -connect com.sun.jdi.SocketListen:port=5005,localAddress=127.0.0.1
~~~

Khởi chạy target JVM với `server=n` để JVM kết nối tới debugger listener:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=n,address=127.0.0.1:5005,suspend=y -jar app.jar
~~~

Nếu debugger nằm ở máy khác, thay `127.0.0.1` bằng hostname/IP của máy debugger và cấu hình listener để bind vào interface có thể truy cập.

Trong JDI, connector tương ứng là `com.sun.jdi.SocketListen`. Cách này hữu ích khi firewall cho phép target kết nối ra ngoài nhưng không cho debugger chủ động kết nối vào target. `server=n` là cấu hình nâng cao; hãy xác nhận listener đã sẵn sàng trước khi khởi chạy target.

## 12. Dùng allow để giới hạn IP được kết nối

Với `server=y` và `transport=dt_socket`, option `allow` giới hạn IP hoặc subnet được phép kết nối:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=127.0.0.1+10.20.30.40 -jar app.jar
~~~

Ví dụ trên lắng nghe trên mọi interface nhưng chỉ cho phép địa chỉ loopback và IP debugger được chỉ định.

Có thể dùng subnet CIDR:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=10.20.0.0/16 -jar app.jar
~~~

Các entry trong danh sách `allow` được phân cách bằng dấu cộng. Mỗi entry có thể là một IP đơn hoặc subnet. Option này được JDK 24 hỗ trợ; hãy kiểm tra `java -agentlib:jdwp=help` trước khi dùng trên JDK khác.

`allow` là một lớp giới hạn bổ sung. Vẫn cần cấu hình firewall hoặc network policy để chỉ cho phép máy debugger truy cập port.

## 13. Kết nối qua SSH tunnel

Khi JVM chạy trên máy chủ từ xa, có thể giữ debug port chỉ bind vào loopback trên máy chủ và dùng SSH tunnel.

Trên máy phát triển:

~~~bash
ssh -L 5005:127.0.0.1:5005 user@remote-host
~~~

Trên remote host, khởi chạy JVM:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Trong IDE hoặc JDB trên máy phát triển, kết nối tới:

~~~text
127.0.0.1:5005
~~~

SSH chuyển tiếp lưu lượng từ localhost của máy phát triển tới loopback của remote host. Cách này tránh phải mở debug port trực tiếp trên public network.

## 14. Dùng debug port trong Docker và Kubernetes

### Docker

Trong container, JVM cần bind vào interface của container để host có thể chuyển tiếp kết nối:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005 -jar app.jar
~~~

Có thể truyền JDWP qua `JAVA_TOOL_OPTIONS` và chỉ publish cổng trên loopback của host:

~~~bash
docker run -e "JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005" -p 127.0.0.1:5005:5005 my-java-image
~~~

Khi đó IDE trên host kết nối tới `127.0.0.1:5005`. Không publish debug port trên mọi interface nếu không có network restriction phù hợp.

### Kubernetes

Có thể dùng `kubectl port-forward` để chuyển tiếp port từ pod về máy phát triển:

~~~bash
kubectl port-forward pod/my-java-pod 5005:5005
~~~

JVM trong pod phải lắng nghe trên port 5005 và bind vào interface của pod. Khi port-forward đang hoạt động, debugger kết nối tới `127.0.0.1:5005` trên máy phát triển.

Port-forward chỉ hoạt động khi phiên lệnh còn chạy. Khi dừng port-forward, debugger mất kết nối.

## 15. Kiểm tra debug port đã mở

### Xem command line của JVM

Tìm PID:

~~~bash
jcmd -l
~~~

Kiểm tra JVM option:

~~~bash
jcmd 18420 VM.command_line
~~~

Output cần có cấu hình `-agentlib:jdwp` với đúng transport, server mode và address.

### Kiểm tra TCP listener

Linux:

~~~bash
ss -lntp | grep 5005
~~~

Windows PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen
~~~

Nếu dùng loopback, local address phải là `127.0.0.1` hoặc loopback tương ứng. Nếu dùng wildcard, listener có thể hiển thị `0.0.0.0` hoặc `::` tùy hệ điều hành.

### Kiểm tra từ debugger

Thử kết nối bằng JDB:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Nếu JDB kết nối được và lệnh `threads` liệt kê thread, TCP path và JDWP handshake đã hoạt động.

## 16. Ví dụ Java 17 hoàn chỉnh để thực hành

Tạo file `src/DebugPortDemo.java`:

~~~java
public class DebugPortDemo {
    public static void main(String[] args) throws InterruptedException {
        int total = 0;
        System.out.println("DebugPortDemo started");

        for (int i = 1; i <= 5; i++) {
            total += i;
            System.out.println("step=" + i + ", total=" + total);
            Thread.sleep(1000);
        }

        System.out.println("DebugPortDemo complete: " + total);
    }
}
~~~

Biên dịch:

~~~bash
mkdir -p out
javac --release 17 -g -d out src/DebugPortDemo.java
~~~

Stdout khi chạy không bật debugger:

~~~text
DebugPortDemo started
step=1, total=1
step=2, total=3
step=3, total=6
step=4, total=10
step=5, total=15
DebugPortDemo complete: 15
~~~

Chạy JVM với debug port local:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out DebugPortDemo
~~~

Log JDWP của JDK 24.0.2 có dạng:

~~~text
Listening for transport dt_socket at address: 5005
~~~

Trong terminal khác, kết nối JDB:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Tại prompt JDB, có thể liệt kê thread và đặt breakpoint:

~~~text
threads
stop at DebugPortDemo:7
cont
locals
where
cont
exit
~~~

Bài lab đã được biên dịch bằng `javac 24.0.2 --release 17 -g` và chạy với JDWP socket transport. JDB kết nối tới port 5017 trong môi trường thử nghiệm, liệt kê được thread `main` và các thread nền của JVM. Port 5017 chỉ là port kiểm thử; lệnh thực hành trong README dùng port 5005.

## 17. Timeout và địa chỉ được cấp tự động

Có thể đặt timeout cho việc kết nối debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=y,timeout=5000 -jar app.jar
~~~

`timeout` được tính bằng milliseconds. Với `server=y`, đây là khoảng chờ debugger attach; với `server=n`, đây là thời gian chờ khi JVM kết nối tới debugger. Timeout bằng 0 là không giới hạn theo trợ giúp JDK 24.

Nếu `server=y` nhưng không chỉ định `address`, JDWP có thể chọn một transport address khả dụng và in địa chỉ đó ra output:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n -jar app.jar
~~~

Đọc port được in ra rồi dùng chính địa chỉ đó để cấu hình debugger. Không giả định port ngẫu nhiên sẽ luôn là 5005.

## 18. Bảo mật khi bật debug port

JDWP là một kênh điều khiển mạnh đối với JVM. Người kết nối debugger có thể xem dữ liệu trong process, đọc stack và biến, tạm dừng thread, đặt breakpoint và tác động tới luồng thực thi. Socket transport không cung cấp lớp xác thực người dùng hoặc TLS riêng trong các tùy chọn JDWP thông thường.

Vì vậy:

- Không mở debug port trực tiếp ra Internet.
- Ưu tiên bind loopback khi debug local.
- Với remote debug, dùng VPN, SSH tunnel hoặc private network.
- Dùng `allow` và firewall để giới hạn nguồn kết nối.
- Chỉ bật debug agent trong thời gian cần thiết.
- Tắt debug option sau khi điều tra xong và restart JVM theo quy trình triển khai.
- Không dùng debug port như một endpoint monitoring công khai.
- Bảo vệ log và file cấu hình vì chúng có thể chứa host, port và thông tin triển khai.

Đừng coi một port khó đoán hoặc một port không được quảng bá là cơ chế bảo mật. Chỉ những debugger được tin cậy mới được phép truy cập.

## 19. Lỗi thường gặp khi cấu hình debug port

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Address already in use` | Port đã được process khác sử dụng. | Chọn port khác hoặc xác định process đang listen. |
| `Connection refused` | JVM chưa mở port, sai host/port hoặc process target đã kết thúc. | Kiểm tra log JDWP, PID và listener TCP. |
| Kết nối timeout | Firewall, route, container mapping hoặc bind address không đúng. | Kiểm tra interface, network policy, port-forward và allow list. |
| JVM đứng trước khi main chạy | `suspend=y` đang chờ debugger attach. | Kết nối debugger hoặc dùng `suspend=n` nếu không cần dừng startup. |
| JVM chạy nhưng debugger không attach được | Chưa nạp JDWP agent hoặc port không đúng. | Kiểm tra `jcmd PID VM.command_line` và log startup. |
| `shmemBase_attach failed` trên Windows | JDB chọn shared-memory connector trong khi target dùng TCP socket. | Dùng `jdb -connect com.sun.jdi.SocketAttach:hostname=...,port=...`. |
| Breakpoint không được xác nhận | Source khác bytecode hoặc thiếu line debug information. | Dùng đúng source revision và biên dịch với `javac -g`. |
| Breakpoint không dừng | Sai class/line, method chưa được nạp hoặc thread không đi qua dòng đó. | Kiểm tra breakpoint, stack trace và luồng thực thi. |
| Remote debug không vào được container | JVM bind loopback bên trong container hoặc chưa publish port. | Bind vào interface container và publish/forward đúng port. |
| Port bị lộ trên mạng ngoài ý muốn | Dùng `address=*` mà không có firewall hoặc allow restriction. | Bind loopback hoặc giới hạn IP và network access. |
| Target chờ sai phía | Dùng nhầm `server=y` hoặc `server=n`. | Xác định bên nào phải listen và bên nào phải connect. |
| JDK không nhận option `allow` | Phiên bản JDK hoặc agent không hỗ trợ option đó. | Chạy `java -agentlib:jdwp=help` để kiểm tra option của runtime. |

## 20. Quy trình bật và tắt debug port trong môi trường làm việc

1. Xác định JVM, host/container và JDK version.
2. Chọn port TCP còn trống, ví dụ 5005.
3. Chọn chiều kết nối; thường dùng `server=y` để debugger attach vào JVM.
4. Chọn địa chỉ bind. Dùng loopback cho debug local; dùng interface riêng, allow list và firewall cho remote debug.
5. Chọn `suspend=y` nếu cần debug startup hoặc `suspend=n` nếu cần attach vào ứng dụng đang chạy.
6. Thêm `-agentlib:jdwp` vào command line hoặc cấu hình JVM option của service.
7. Khởi động lại JVM nếu agent chưa được nạp từ lúc startup.
8. Kiểm tra log JDWP, command line và TCP listener.
9. Cấu hình IDE/JDB với đúng host, port và socket transport.
10. Đặt breakpoint, quan sát thread/stack/variable và tiếp tục ứng dụng.
11. Dừng phiên debug khi hoàn tất.
12. Gỡ JDWP option, đóng port hoặc restart service theo quy trình triển khai.

Debug port giúp debugger điều khiển một JVM từ xa qua JDWP. Cấu hình đúng phụ thuộc vào chiều kết nối, địa chỉ bind, port, trạng thái suspend và quyền truy cập mạng. Hãy xác nhận listener và debugger handshake trước khi điều tra code, đồng thời giới hạn thời gian và nguồn truy cập tới cổng debug.

## 21. Tài liệu tham khảo

- [Connection and Invocation Details — JPDA, JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html)
- [The jdb Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
