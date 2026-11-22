# Debug remote Java: kết nối debugger tới JVM trên máy khác

**Remote debugging** cho phép debugger chạy trên máy phát triển kết nối tới một JVM đang chạy ở máy khác, container hoặc môi trường kiểm thử. Người phát triển có thể đặt breakpoint, dừng chương trình, xem stack trace, đọc biến, thực hiện từng bước và tiếp tục luồng thực thi mà không cần chạy ứng dụng trực tiếp trong IDE trên máy đích.

Trong Java, remote debugging thường dùng **Java Platform Debugger Architecture (JPDA)**, **Java Debug Wire Protocol (JDWP)** và transport TCP socket. Có thể dùng debugger trong IntelliJ IDEA, Eclipse, Visual Studio Code hoặc công cụ dòng lệnh `jdb` của JDK.

## 1. Remote debugging dùng để làm gì?

Remote debugging hữu ích khi ứng dụng chỉ tái hiện lỗi trong môi trường gần production, máy chủ tích hợp, container hoặc máy ảo mà developer không thể mở IDE trực tiếp.

Một phiên debug từ xa có thể giúp:

- Dừng chương trình tại một dòng code hoặc đầu một method.
- Xem call stack để biết luồng gọi dẫn tới vị trí hiện tại.
- Đọc giá trị local variables, arguments, fields và biểu thức.
- Dùng step into, step over và step out để theo dõi luồng chạy.
- Dừng khi một exception được ném ra.
- Kiểm tra thread, trạng thái JVM và điều kiện gây lỗi.
- Tiếp tục hoặc kết thúc phiên debug khi đã tìm được nguyên nhân.

Remote debugging là một phiên điều khiển tương tác. Khi debugger dừng thread hoặc toàn JVM tại breakpoint, ứng dụng có thể tạm ngừng xử lý request. Vì vậy cần chọn thời điểm, phạm vi và môi trường phù hợp.

## 2. Kiến trúc JPDA, JDWP và JDI

JPDA là kiến trúc chuẩn của Java dành cho debugger. Nó gồm các lớp chính:

| Thành phần | Vai trò |
|---|---|
| JVM TI (JVM Tool Interface) | Giao diện cấp thấp để công cụ quan sát và điều khiển hoạt động của JVM. |
| JDWP (Java Debug Wire Protocol) | Giao thức trao đổi lệnh và sự kiện giữa JVM đang được debug và debugger. |
| JDI (Java Debug Interface) | API Java cấp cao để debugger đặt breakpoint, đọc biến, điều khiển thread và truy vấn target VM. |
| Debugger frontend | Công cụ mà developer sử dụng, ví dụ JDB hoặc debugger tích hợp trong IDE. |
| JDWP agent | Thành phần chạy trong target JVM, kết nối JVM với debugger qua transport đã chọn. |

Luồng giao tiếp tổng quát:

~~~text
IDE / jdb
   |
   | JDI
   v
Debugger connector
   |
   | JDWP over transport
   v
JDWP agent trong target JVM
   |
   | JVM TI
   v
Ứng dụng Java đang chạy
~~~

JDWP không phải một công cụ giao diện. Nó là giao thức ở giữa debugger và JVM. JDI cung cấp API cho debugger; IDE thường dùng JDI để thực hiện các thao tác debug.

## 3. Hai đầu của phiên remote debug

Có hai tiến trình:

- **Debuggee:** JVM chạy ứng dụng cần kiểm tra.
- **Debugger:** IDE hoặc `jdb` kết nối tới debuggee.

Với TCP socket, một đầu phải mở cổng chờ kết nối và đầu kia chủ động kết nối. Có hai cách bố trí:

1. Target JVM lắng nghe, debugger kết nối vào.
2. Debugger lắng nghe, target JVM chủ động kết nối tới debugger.

Cách thứ nhất phổ biến trong IDE remote attach. Cách thứ hai hữu ích khi target có thể kết nối ra ngoài nhưng debugger không thể nhận kết nối trực tiếp từ mạng của target.

Hai đầu phải thống nhất transport, địa chỉ và cổng. Nếu một đầu dùng socket còn đầu kia dùng shared memory, kết nối sẽ thất bại.

## 4. Bật JDWP khi khởi chạy target JVM

Để JVM nhận kết nối debugger qua TCP, thêm agent option vào lệnh khởi chạy:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar app.jar
~~~

Ý nghĩa từng option:

| Option | Ý nghĩa |
|---|---|
| `-agentlib:jdwp` | Nạp JDWP agent vào target JVM. |
| `transport=dt_socket` | Dùng TCP socket transport. |
| `server=y` | Target JVM mở socket và chờ debugger kết nối. |
| `suspend=y` | Tạm dừng JVM trước khi chạy main class cho tới khi debugger attach. |
| `address=127.0.0.1:5005` | Lắng nghe trên loopback của máy đích, cổng 5005. |
| `timeout` | Giới hạn thời gian chờ kết nối, tính bằng milliseconds; khả năng áp dụng tùy transport. |

Cổng 5005 chỉ là ví dụ phổ biến, không phải cổng cố định bắt buộc. Chọn cổng chưa được tiến trình khác sử dụng và mở đúng cổng trên đường mạng cần thiết.

Có thể xem trợ giúp của JDWP agent trên JDK đang dùng:

~~~bash
java -agentlib:jdwp=help -version
~~~

Nên dùng `-agentlib:jdwp` trên JDK hiện đại. Cú pháp cũ `-Xrunjdwp` vẫn có thể xuất hiện trong tài liệu cũ nhưng đã lỗi thời.

## 5. Chọn suspend=y hay suspend=n

`suspend` quyết định target JVM có chờ debugger trước khi bắt đầu chạy hay không.

| Giá trị | Hành vi | Khi nào dùng |
|---|---|---|
| `suspend=y` | JVM tạm dừng trước khi chạy main class, chờ debugger kết nối. | Cần đặt breakpoint trước khi ứng dụng thực thi code đầu tiên. |
| `suspend=n` | JVM bắt đầu chạy ngay, debugger có thể attach sau. | Ứng dụng chạy lâu và cần kết nối khi sự cố xuất hiện. |

Ví dụ chờ debugger trước khi chạy:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.acme.RemoteDebugDemo
~~~

Ví dụ ứng dụng tiếp tục chạy trong lúc chờ debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

`suspend=y` là mặc định của JDWP agent. Nếu bật giá trị này mà không có debugger kết nối, ứng dụng có thể đứng ở giai đoạn khởi động. Với dịch vụ cần tiếp tục nhận request, cân nhắc `suspend=n` và đặt breakpoint sau khi attach.

## 6. Chọn địa chỉ bind và giới hạn IP được phép

Địa chỉ socket quyết định interface nào nhận kết nối:

~~~bash
# Chỉ nhận kết nối từ chính máy đích
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005

# Lắng nghe trên mọi network interface
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
~~~

Địa chỉ `127.0.0.1` chỉ có thể truy cập từ chính máy đích. Dùng `*` khiến socket lắng nghe trên mọi network interface, vì vậy phải kiểm soát chặt đường mạng.

Với `server=y` và `dt_socket`, JDWP có option `allow` để giới hạn địa chỉ nguồn hoặc subnet được phép kết nối:

~~~bash
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005,allow=192.0.2.10
~~~

Có thể chỉ định nhiều địa chỉ/subnet bằng dấu `+`, ví dụ:

~~~text
allow=192.0.2.10+198.51.100.0/24
~~~

Thay các địa chỉ ví dụ bằng IP thực của debugger hoặc dải mạng được phê duyệt. `allow` là bộ lọc nguồn kết nối bổ sung; nó không thay thế firewall, VPN hay đường hầm được xác thực.

## 7. Kết nối debugger tới JVM đang lắng nghe

Sau khi target JVM khởi chạy với `server=y`, debugger kết nối tới host và port của target.

Với JDB trên Linux hoặc macOS, socket connector mặc định thường được chọn bởi lệnh:

~~~bash
jdb -attach app-server.example.com:5005
~~~

Trong đó:

- `app-server.example.com` là hostname hoặc IP của máy chạy JVM.
- `5005` là port JDWP mà target đang lắng nghe.

Có thể truyền source path để JDB tìm file Java:

~~~bash
jdb -sourcepath src -attach app-server.example.com:5005
~~~

### Lưu ý trên Windows

Trên Windows, connector mặc định của JDB có thể dùng shared memory transport. Khi target đang lắng nghe bằng TCP socket, hãy chọn socket connector tường minh:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=app-server.example.com,port=5005
~~~

Nếu debug trên cùng máy:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

`SocketAttach` chọn JDI connector cho TCP. Đây là cách rõ ràng khi cần socket trên Windows, tránh nhầm với connector shared memory.

## 8. Cách kết nối ngược: debugger lắng nghe

Trong một số mạng, target có thể tạo kết nối outbound tới máy developer nhưng không thể nhận kết nối inbound. Khi đó, để debugger lắng nghe trước:

~~~bash
jdb -connect com.sun.jdi.SocketListen:port=5006
~~~

Khởi chạy target JVM với `server=n` để target chủ động kết nối tới debugger:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 -cp out com.acme.RemoteDebugDemo
~~~

Trong chế độ này:

- JDB mở listener ở cổng 5006.
- Target JVM kết nối tới địa chỉ của debugger.
- Khi kết nối thành công, JDB bắt đầu phiên debug.
- `suspend=y` vẫn giữ ứng dụng ở trạng thái chờ cho tới khi debugger điều khiển tiếp.

Khi debugger ở máy khác, thay `127.0.0.1` bằng địa chỉ mà target có thể truy cập trên máy debugger. Mở firewall đúng chiều kết nối. Cách reverse connection thay đổi hướng kết nối, nhưng không tự tạo mã hóa hoặc xác thực.

## 9. Dùng SSH tunnel để debug an toàn qua mạng

Một cách thường dùng là giữ JDWP chỉ lắng nghe trên loopback của máy đích và dùng SSH port forwarding.

Trên máy chủ, khởi chạy JVM:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
~~~

Trên máy developer, tạo tunnel:

~~~bash
ssh -N -L 5005:127.0.0.1:5005 user@remote-host
~~~

Giữ terminal SSH mở trong suốt phiên debug. Tunnel chuyển kết nối từ cổng 5005 trên máy developer tới cổng 5005 trên loopback của máy chủ qua SSH.

Sau đó cấu hình IDE hoặc JDB kết nối tới:

~~~text
Host: 127.0.0.1
Port: 5005
Transport: Socket
~~~

Ví dụ với JDB trên Windows:

~~~bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

SSH cung cấp xác thực và mã hóa cho đường truyền. Target JVM không cần mở JDWP ra network interface công khai.

## 10. Remote debugging bằng IDE

Các IDE Java phổ biến đều có chế độ **Remote JVM Debug** hoặc **Attach to Remote JVM**. Tên menu có thể khác theo phiên bản, nhưng thông tin kết nối thường gồm:

- Hostname hoặc IP của target JVM.
- Port JDWP.
- Transport, thường là Socket.
- Source/project tương ứng với bytecode đang chạy.

Quy trình chung:

1. Build ứng dụng có debug information.
2. Khởi chạy target JVM với JDWP agent.
3. Thiết lập SSH tunnel, VPN hoặc network route nếu cần.
4. Tạo cấu hình remote attach trong IDE.
5. Nhập host/port mà IDE có thể truy cập.
6. Chọn source code đúng phiên bản đang chạy trên target.
7. Đặt breakpoint rồi attach.
8. Tiếp tục ứng dụng và kiểm tra trạng thái khi breakpoint được kích hoạt.

Nếu IDE báo đã kết nối nhưng breakpoint không dừng, hãy kiểm tra source và bytecode có cùng build/commit hay không, cũng như line number information trong class file.

## 11. Chuẩn bị source và debug information

Debugger cần liên kết bytecode đang chạy với source code tương ứng. Với ví dụ biên dịch bằng javac, dùng:

~~~bash
javac -g --release 17 -d out src/com/acme/RemoteDebugDemo.java
~~~

`-g` yêu cầu compiler ghi debug information như line number và local variable information. Nếu build dùng `-g:none` hoặc quá trình đóng gói đã loại debug metadata:

- Breakpoint theo số dòng có thể không đặt được hoặc không khớp.
- `locals` có thể không hiển thị local variables.
- IDE có thể báo source không khớp hoặc chỉ hiển thị bytecode.

Hãy giữ source của đúng commit/build đã triển khai. Nếu target chạy JAR được build từ commit khác, line number có thể lệch và debugger có thể hiển thị code không tương ứng với hành vi thật.

## 12. Các lệnh JDB thường dùng

Sau khi kết nối, JDB hiển thị prompt và nhận các lệnh debug:

| Lệnh | Chức năng |
|---|---|
| `stop at ClassName:Line` | Đặt breakpoint tại dòng source. |
| `stop in ClassName.method` | Đặt breakpoint tại method. |
| `clear ClassName:Line` | Xóa breakpoint tại dòng. |
| `cont` | Tiếp tục thực thi. |
| `step` | Đi vào method được gọi ở dòng kế tiếp. |
| `next` | Chạy qua dòng kế tiếp mà không đi vào method. |
| `step up` | Chạy tới khi thoát khỏi stack frame hiện tại. |
| `locals` | Hiển thị arguments và local variables trong frame hiện tại nếu có debug information. |
| `print expression` | Đánh giá và in biểu thức Java. |
| `dump expression` | In chi tiết object hoặc giá trị. |
| `where` | Hiển thị call stack của thread hiện tại. |
| `where all` | Hiển thị stack trace của các thread. |
| `threads` | Liệt kê các thread đã biết với debugger. |
| `catch ExceptionClass` | Dừng khi exception thuộc kiểu chỉ định được ném ra. |
| `ignore ExceptionClass` | Bỏ theo dõi exception đã đăng ký bằng catch. |
| `quit` | Kết thúc phiên JDB. |

Ví dụ:

~~~text
stop at com.acme.RemoteDebugDemo:8
cont
locals
print attempt
next
where
cont
~~~

`locals` và `print` phụ thuộc frame đang dừng, debug metadata và scope của biến. Không phải biến nào cũng có thể đọc ở mọi dòng hoặc mọi frame.

## 13. Ví dụ hoàn chỉnh: remote debug một Java 17+ application

Tạo dự án:

~~~text
remote-debug-demo/
├── src/
│   └── com/
│       └── acme/
│           └── RemoteDebugDemo.java
└── out/
~~~

Tệp `src/com/acme/RemoteDebugDemo.java`:

~~~java
package com.acme;

public class RemoteDebugDemo {
    public static void main(String[] args) throws InterruptedException {
        int attempt = 0;
        System.out.println("REMOTE_DEBUG_READY");

        for (int i = 1; i <= 3; i++) {
            attempt += i;
            System.out.println("attempt=" + attempt);
            Thread.sleep(500);
        }

        System.out.println("REMOTE_DEBUG_DONE=" + attempt);
    }
}
~~~

### Bước 1: biên dịch

Từ thư mục gốc:

~~~bash
javac -g --release 17 -d out src/com/acme/RemoteDebugDemo.java
~~~

### Bước 2: khởi chạy target JVM ở chế độ chờ debugger

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -cp out com.acme.RemoteDebugDemo
~~~

Thông báo từ JDWP agent khi mở listener:

~~~text
Listening for transport dt_socket at address: 5005
~~~

JVM tạm dừng trước khi chạy main method.

### Bước 3: kết nối debugger

Mở terminal thứ hai trên máy có JDK.

Trên Linux/macOS, dùng socket attach mặc định:

~~~bash
jdb -sourcepath src -attach 127.0.0.1:5005
~~~

Trên Windows, chọn socket connector tường minh:

~~~bash
jdb -sourcepath src -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
~~~

Nếu target ở máy khác, thay địa chỉ loopback bằng host của target hoặc kết nối tới loopback thông qua SSH tunnel.

### Bước 4: đặt breakpoint và tiếp tục

Tại prompt JDB:

~~~text
stop at com.acme.RemoteDebugDemo:8
cont
~~~

JDB dừng tại dòng:

~~~java
attempt += i;
~~~

Xem biến:

~~~text
locals
print attempt
print i
~~~

Tại lần dừng đầu tiên, giá trị dự kiến là:

~~~text
attempt = 0
i = 1
~~~

Chạy qua dòng hiện tại:

~~~text
next
print attempt
~~~

Giá trị sau phép cộng đầu tiên:

~~~text
attempt = 1
~~~

Xóa breakpoint và tiếp tục:

~~~text
clear com.acme.RemoteDebugDemo:8
cont
~~~

### Bước 5: kiểm tra output của ứng dụng

Stdout do chương trình Java tạo ra:

~~~text
REMOTE_DEBUG_READY
attempt=1
attempt=3
attempt=6
REMOTE_DEBUG_DONE=6
~~~

Ví dụ đã được biên dịch với `javac -g --release 17` và kiểm thử trên Azul OpenJDK 24.0.2. JDB kết nối qua TCP socket, dừng đúng tại dòng 8, đọc được `attempt` và `i`, thực hiện step, xóa breakpoint và cho chương trình chạy tới kết thúc.

## 14. Remote debug trong container hoặc môi trường cloud

Khi JVM chạy trong Docker, Kubernetes hoặc máy ảo cloud, debugger phải truy cập được đúng endpoint JDWP trong network namespace của target.

Cần kiểm tra:

- JDWP agent đã được bật trong command line của container/process chưa.
- Địa chỉ bind có phù hợp với cách port được publish hoặc forward không.
- Port JDWP có được chuyển qua đúng container/pod không.
- Firewall, security group và network policy có cho phép kết nối cần thiết không.
- Target và debugger có dùng cùng transport và port không.
- Source code trên máy developer có khớp image/build đang chạy không.

Có thể dùng SSH tunnel, VPN hoặc port forwarding được kiểm soát để tạo đường kết nối tạm thời. Tránh publish JDWP port công khai chỉ để IDE có thể kết nối thuận tiện.

Việc mở một cổng trong Dockerfile hoặc khai báo container port không tự bảo đảm rằng cổng đó được bảo vệ. Cần kiểm soát cả network binding, port mapping và chính sách truy cập của môi trường chạy.

## 15. Breakpoint và thread suspension ảnh hưởng ứng dụng thế nào?

Khi breakpoint được kích hoạt, debugger có thể suspend thread hiện tại hoặc nhiều thread tùy suspend policy. Trong một số IDE, mặc định breakpoint Java có thể suspend toàn bộ thread của JVM.

Điều này có thể gây ra:

- Request đang xử lý bị dừng giữa chừng.
- Timeout ở load balancer hoặc client.
- Lock bị giữ lâu hơn bình thường.
- Thread khác bị BLOCKED vì thread dừng tại breakpoint đang giữ monitor.
- Scheduled task, heartbeat hoặc health check không chạy đúng hạn.
- Timing bug hoặc race condition biến mất khi debugger làm chậm chương trình.

Nếu cần theo dõi production-like environment, hãy chọn breakpoint có điều kiện hoặc logpoint khi IDE hỗ trợ, hạn chế suspend toàn JVM và dùng môi trường staging để tái hiện trước. Debugger thay đổi timing của chương trình, nên hành vi quan sát được có thể khác lúc chạy bình thường.

## 16. Bảo mật remote debugging

JDWP là giao diện điều khiển mạnh đối với target JVM. Kết nối JDWP bắt đầu bằng một handshake cố định để xác nhận hai bên dùng đúng protocol; handshake này không phải cơ chế xác thực người dùng và không cung cấp mã hóa đường truyền.

Một debugger có quyền truy cập JDWP có thể đọc dữ liệu trong process, dừng thread, thay đổi giá trị và điều khiển luồng thực thi. Vì vậy, một JDWP port có thể truy cập từ mạng không tin cậy là rủi ro nghiêm trọng.

Thực hành an toàn:

- Chỉ bật JDWP khi thực sự cần debug.
- Ưu tiên bind vào loopback và kết nối qua SSH tunnel.
- Dùng VPN hoặc mạng quản trị riêng khi phải debug từ xa.
- Nếu phải bind ra interface mạng, giới hạn IP bằng `allow` và firewall.
- Không mở JDWP trực tiếp ra Internet.
- Giới hạn người có quyền SSH, VPN hoặc truy cập máy đích.
- Dùng `suspend=n` nếu dịch vụ cần tiếp tục chạy trong lúc chờ attach.
- Ghi lại thời điểm bật debug và tắt sau khi hoàn tất.
- Khởi động lại ứng dụng với cấu hình không còn JDWP agent khi phiên debug kết thúc.

JDWP không nên được xem là một dịch vụ quản trị có sẵn password hoặc TLS. Đường truyền bảo mật phải được cung cấp bởi lớp mạng bên ngoài, ví dụ SSH hoặc VPN.

## 17. Troubleshooting remote debugging

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Connection refused` | JDWP agent chưa chạy, sai host/port hoặc target chưa bind socket. | Kiểm tra JVM arguments, listener và port thực tế. |
| `Connection timed out` | Firewall, routing, security group hoặc tunnel chặn kết nối. | Kiểm tra đường mạng và chiều kết nối. |
| JVM đứng trước khi ứng dụng khởi động | `suspend=y` đang chờ debugger. | Attach debugger hoặc đổi sang `suspend=n` nếu phù hợp. |
| Debugger kết nối nhưng breakpoint không hit | Breakpoint sai dòng, class chưa load hoặc source không khớp bytecode. | Kiểm tra package, class name, line number và build. |
| Không thấy local variables | Class không có local variable debug metadata hoặc frame hiện tại không có biến trong scope. | Build với `javac -g` và dừng đúng dòng. |
| JDB trên Windows báo lỗi shared memory | `jdb -attach` chọn connector mặc định không khớp với TCP socket target. | Dùng `-connect com.sun.jdi.SocketAttach:hostname=...,port=...`. |
| `Address already in use` | Port JDWP đã được tiến trình khác sử dụng. | Chọn port khác và cập nhật debugger configuration. |
| Target kết nối ngược thất bại | JDB listener chưa chạy hoặc target không truy cập được địa chỉ listener. | Khởi động listener trước, xác minh IP/port và firewall. |
| IDE báo source không khớp | IDE mở source từ commit khác với class đang chạy. | Checkout đúng commit hoặc build artifact tương ứng. |
| Debugger không theo dõi virtual thread | Cấu hình debugger mặc định không theo dõi tất cả virtual thread. | Kiểm tra tùy chọn theo dõi virtual thread của JDK/IDE; JDB có `-trackallthreads`. |

## 18. Remote debug khác gì JMX, JFR và thread dump?

Các công cụ đều giúp quan sát JVM nhưng có mục đích khác nhau:

| Công cụ | Cách làm việc | Phù hợp khi |
|---|---|---|
| Remote debugger (JDWP/JDI) | Kết nối tương tác, đặt breakpoint và điều khiển thực thi. | Cần kiểm tra logic, giá trị biến hoặc luồng gọi tại một vị trí cụ thể. |
| JMX/JConsole | Đọc MBean attributes và gọi management operations. | Cần theo dõi metric và trạng thái quản trị JVM/ứng dụng. |
| JFR | Ghi event theo thời gian vào file recording. | Cần phân tích CPU, allocation, GC, lock và I/O sau khi thu thập. |
| Thread dump | Chụp stack/state của thread tại một thời điểm. | Cần điều tra thread bị treo, BLOCKED hoặc deadlock. |
| Heap dump | Ghi object graph trong heap. | Cần tìm object retention và memory leak. |

Không dùng remote debugger như hệ thống monitoring liên tục. Khi cần quan sát dài hạn hoặc giảm tác động tới timing, JFR và metrics thường phù hợp hơn.

## 19. Kiểm tra và đóng phiên debug

Khi hoàn thành:

1. Tiếp tục hoặc kết thúc target theo trạng thái mong muốn.
2. Dừng phiên debugger bằng `quit` hoặc nút Disconnect của IDE.
3. Xác nhận ứng dụng không còn bị suspend.
4. Đóng SSH tunnel hoặc port forwarding.
5. Xóa cấu hình JDWP khỏi startup command, service unit, container environment hoặc deployment manifest nếu không còn cần.
6. Khởi động lại ứng dụng theo cấu hình vận hành bình thường nếu JDWP đã được bật tạm thời.
7. Kiểm tra listener JDWP không còn hoạt động trên host.

Ngắt debugger không tự bảo đảm rằng cấu hình JDWP đã được loại khỏi lần khởi động tiếp theo. Hãy kiểm tra cấu hình deploy để tránh vô tình để lại debug port.

## 20. Quy trình remote debugging khuyến nghị

Khi cần debug một JVM từ xa:

1. Xác định host, PID, JDK version và artifact đang chạy.
2. Build hoặc lấy đúng source code và debug symbols của artifact.
3. Chọn chiều kết nối: target lắng nghe (`server=y`) hay target kết nối tới debugger (`server=n`).
4. Chọn `suspend=y` nếu phải đặt breakpoint trước main; dùng `suspend=n` nếu cần giữ dịch vụ hoạt động.
5. Chỉ mở địa chỉ/port cần thiết và giới hạn nguồn kết nối.
6. Ưu tiên SSH tunnel hoặc VPN để bảo vệ đường truyền.
7. Kết nối IDE/JDB với đúng socket connector.
8. Đặt breakpoint, kiểm tra locals và call stack, sau đó tiếp tục ứng dụng.
9. Theo dõi ảnh hưởng của breakpoint tới request, thread và lock.
10. Ngắt tunnel, loại bỏ debug option và xác nhận cổng không còn mở.

Remote debugging giúp developer điều tra lỗi trong JVM chạy ở môi trường khác bằng chính source code và debugger quen thuộc. Nắm rõ JPDA/JDWP, hai chiều kết nối, `suspend`, transport và bảo mật giúp phiên debug có thể tái hiện được và hạn chế ảnh hưởng tới ứng dụng.

## Tài liệu tham khảo

- Oracle JDK 24 — [Java Platform Debugger Architecture](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/jpda.html).
- Oracle JDK 24 — [Connection and Invocation Details](https://docs.oracle.com/en/java/javase/24/docs/specs/jpda/conninv.html).
- Oracle JDK 24 — [The jdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdb.html).
- Oracle JDK 24 — [Java Debug Wire Protocol Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jdwp/jdwp-spec.html).
- Oracle JDK 24 — [Troubleshooting Guide: Java Debug Wire Protocol](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf).
