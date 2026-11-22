# ServerSocket: bind địa chỉ, lắng nghe và accept kết nối

## 1. Tổng quan: một TCP server mở cổng như thế nào?

Trong Java, `java.net.ServerSocket` là đối tượng **lắng nghe các kết nối TCP đến**. Nó đại diện cho **listening socket** của máy chủ: chọn **địa chỉ IP cục bộ** và **cổng**, yêu cầu hệ điều hành cho phép nhận kết nối tại endpoint đó, rồi chờ nhận một kết nối bằng `accept()`. Mỗi lần `accept()` thành công, Java trả về **một `java.net.Socket` mới** đại diện cho một kết nối TCP với một client cụ thể.

Ba thao tác trọng tâm của đề bài:

1. **Bind địa chỉ:** chỉ định cặp **local IP + TCP port** mà máy chủ sẽ sử dụng; ví dụ `127.0.0.1:8080` để chỉ phục vụ trên loopback.
2. **Lắng nghe (listen):** sau khi bind thành công, listening socket được đặt ở trạng thái sẵn sàng nhận yêu cầu kết nối. API `ServerSocket` truyền thống **không có phương thức `listen()` công khai riêng**: thao tác bind/constructor đã thiết lập khả năng listen ở tầng hệ điều hành.
3. **Accept:** `server.accept()` chờ một kết nối sẵn sàng, rồi trả về **connected `Socket`**; dùng `getInputStream()`, `getOutputStream()` của socket vừa nhận để trao đổi byte.

~~~text
Máy chủ Java                               Hệ điều hành/TCP                    Client
new ServerSocket()                         Chưa gắn endpoint
setReuseAddress(...)                       Đặt tùy chọn trước bind
bind(local-IP, port, backlog) -------->    BIND + LISTEN
accept() ------------------------------>   Chờ kết nối trong hàng đợi
                                           SYN / SYN-ACK / ACK  <-------- connect(...)
accept() <------------------------------   Có kết nối để lấy ra
trả về Socket clientSocket                 TCP connection ESTABLISHED
clientSocket.getInputStream() <---------   Luồng byte TCP  <-------------- write(...)
clientSocket.getOutputStream() -------->   Luồng byte TCP  -------------> read(...)
close(clientSocket)                        Đóng kết nối đã accept
accept()                                   Tiếp tục nhận client khác
close(serverSocket)                        Ngừng nhận kết nối mới
~~~

Sơ đồ là mô tả logic, không cố định thứ tự tuyệt đối giữa `connect()`, TCP handshake và lúc application gọi `accept()`. Trong nhiều hệ thống, **TCP handshake có thể hoàn tất và client `connect()` có thể trở về trước khi thread Java của server gọi `accept()`**; hệ điều hành tạm giữ kết nối trong hàng đợi. **`accept()` không phải nơi Java tự thực hiện toàn bộ handshake bằng code ứng dụng**.

## 2. Phân biệt listening `ServerSocket` và connected `Socket`

| Thuộc tính | `ServerSocket` | `Socket` trả về từ `accept()` |
|---|---|---|
| Vai trò | Nghe các kết nối mới tại endpoint cục bộ | Trao đổi dữ liệu với **một** peer TCP |
| Địa chỉ/cổng chính | Local bind address và listening port | Local address/port **và** remote address/port của kết nối |
| API chính | `bind(...)`, `accept()`, `setSoTimeout(...)`, `close()` | `getInputStream()`, `getOutputStream()`, `setSoTimeout(...)`, `close()` |
| Khi chưa có client mới | `accept()` blocking có thể chờ | Không liên quan đến việc nhận kết nối mới |
| Khi nhận byte | Không đọc dữ liệu ứng dụng | Đọc qua input stream |
| Khi đóng | Ngừng tiếp nhận client mới | Kết thúc kết nối riêng của client đó |

Một máy chủ có thể có **một ServerSocket trên cổng 8080** nhưng cùng lúc quản lý nhiều `Socket` đã accept. Mỗi kết nối có **bộ tứ TCP** phân biệt: local IP, local port, remote IP, remote port. Vì vậy các accepted socket có thể cùng local port 8080 mà vẫn là những kết nối độc lập.

**Không gọi `getInputStream()` trên `ServerSocket`**: nó chỉ listen. **Không dùng `ServerSocket.accept()` để đọc một request HTTP/chat**: `accept()` trả về kết nối; dữ liệu ứng dụng được đọc sau đó trên accepted socket.

## 3. Tạo và bind địa chỉ đúng cách

### 3.1. Các constructor và `bind` thường dùng

~~~java
// Đoạn minh họa: mỗi lựa chọn là một cách tạo server riêng.
ServerSocket a = new ServerSocket();             // Chưa bind
ServerSocket b = new ServerSocket(8080);         // Bind và listen ngay
ServerSocket c = new ServerSocket(8080, 128);    // Bind với backlog yêu cầu
ServerSocket d = new ServerSocket(
        8080, 128, InetAddress.getLoopbackAddress());
~~~

Các dòng là **ví dụ lựa chọn thay thế**, không chạy đồng thời nhiều listener trên cùng cổng 8080. Các constructor có đối số cổng **bind ngay** và có thể ném `IOException` nếu bind thất bại. Với `ServerSocket()`, bạn tự đặt tùy chọn trước rồi gọi:

~~~java
// Trích đoạn, đặt trong phương thức có xử lý IOException:
try (ServerSocket server = new ServerSocket()) {
    server.setReuseAddress(true);  // Nên đặt trước bind nếu dùng
    server.bind(
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 8080),
        128
    );
    // Sau bind thành công, server sẵn sàng accept().
}
~~~

`bind(SocketAddress endpoint, int backlog)` nhận:

- **`endpoint`:** thường là `InetSocketAddress`, gồm địa chỉ **cục bộ của chính máy server** và TCP port, không phải địa chỉ client sắp kết nối.
- **`backlog`:** độ dài **hàng đợi kết nối đang chờ được accept** do chương trình yêu cầu; ý nghĩa và giới hạn thực tế phụ thuộc hệ điều hành/triển khai.
- Nếu chỉ dùng `bind(endpoint)`, JDK dùng backlog mặc định theo triển khai. Các constructor đơn giản tài liệu Java 17 mô tả giá trị yêu cầu mặc định là **50**; con số thực tế có thể bị hệ điều hành điều chỉnh.
- **`port = 0`:** hệ điều hành chọn một cổng trống, thường thuộc dải ephemeral; lấy cổng thật bằng `server.getLocalPort()`. Đây là lựa chọn tốt cho unit/integration test để tránh hard-code cổng đang bận.
- **`bind(null)`:** yêu cầu JVM/hệ thống chọn một endpoint cục bộ và cổng tạm; đối với server phải có cổng cố định cho client thực tế, hãy cung cấp endpoint rõ ràng.
- Cổng hợp lệ **0–65535**, nhưng cổng 0 là yêu cầu cấp cổng tự động chứ không phải server sẽ tiếp tục nghe ở cổng TCP số 0.

### 3.2. Bind một IP hay tất cả IP?

Một máy có thể có loopback, địa chỉ LAN, interface VPN hoặc nhiều địa chỉ IPv4/IPv6.

| Bind address | Ý nghĩa | Trường hợp nên dùng |
|---|---|---|
| `127.0.0.1` | IPv4 loopback, chỉ các kết nối local qua loopback phù hợp | Demo, công cụ quản trị chỉ nội bộ host |
| `::1` | IPv6 loopback | Môi trường chỉ muốn IPv6 loopback |
| `0.0.0.0` | IPv4 wildcard, các địa chỉ IPv4 local phù hợp | Server cần nhận từ nhiều interface IPv4 |
| `::` | IPv6 wildcard; việc nhận đồng thời IPv4 phụ thuộc cấu hình dual-stack | Server IPv6 |
| Một IP LAN của máy | Chỉ interface/địa chỉ đó | Dịch vụ lắng nghe trên mạng cụ thể |

Ví dụ rõ ràng:

~~~java
// Chỉ IPv4 loopback
server.bind(new InetSocketAddress("127.0.0.1", 8080), 128);

// Cổng 8080 trên địa chỉ IPv4 local bất kỳ
server.bind(new InetSocketAddress("0.0.0.0", 8080), 128);
~~~

Hai dòng này **không chạy liên tiếp trên cùng ServerSocket**: chỉ được bind **một lần**. Sau bind thành công, gọi `bind` lần nữa sẽ lỗi. Trong ví dụ đầy đủ ở phần sau dùng `InetAddress.getLoopbackAddress()` để không phụ thuộc máy hỗ trợ loopback IPv4 hay IPv6.

**Chọn bind address dựa trên phạm vi tiếp cận mong muốn.** Bind wildcard làm dịch vụ có thể nhận từ nhiều interface, nhưng vẫn có thể bị firewall, NAT, container network hoặc chính sách hệ điều hành chặn từ bên ngoài. Bind loopback thì máy khác không kết nối trực tiếp đến cổng đó qua LAN, cho dù firewall mở.

### 3.3. DNS và tên máy không phải “địa chỉ để bind”

`new InetSocketAddress("localhost", 8080)` cần phân giải hostname; `localhost` có thể ra `127.0.0.1` hoặc `::1` tùy môi trường. Nếu server chỉ bind IPv4 mà client dùng IPv6, hoặc ngược lại, phép kết nối có thể thất bại. Với demo, chọn cùng một đối tượng `InetAddress` cho server và client để tránh mismatch.

**Không bind vào IP công khai của một máy ở xa**: server chỉ bind được địa chỉ phù hợp với ngăn xếp mạng cục bộ. Khi máy có NAT hoặc chạy container, địa chỉ public mà client thấy thường khác địa chỉ/interface thực tế trên máy/container.

## 4. “Listen” thực sự hoạt động ra sao và `backlog` nghĩa là gì?

Trong C/BSD sockets thường nhắc trình tự `socket → bind → listen → accept`. Java `ServerSocket` cung cấp lớp trừu tượng: constructor đã bind hoặc bạn tự gọi `bind`, sau đó socket đã sẵn sàng listen; **không có `server.listen()` trong API Java**.

Khi client gọi `connect(remote)`:

1. Hệ điều hành hai bên xử lý cơ chế TCP handshake, ví dụ SYN → SYN-ACK → ACK trong tình huống phổ biến.
2. Kết nối đủ điều kiện được đưa vào hàng đợi để server chấp nhận, tùy triển khai TCP và trạng thái mạng.
3. Thread Java gọi `accept()` lấy một kết nối sẵn sàng từ hệ điều hành và được trả về **một Socket mới**.
4. Listening `ServerSocket` vẫn tồn tại để nhận kết nối tiếp theo.

`backlog` là **gợi ý/yêu cầu** về số lượng kết nối đang chờ accept; Javadoc Java 17 nêu semantics là *implementation-specific*: hệ điều hành có thể giới hạn hoặc bỏ qua tham số. Không định nghĩa backlog bằng “số thread được phép chạy”, “tổng số client đang kết nối”, hay “số request HTTP tối đa”.

- **Backlog nhỏ + xử lý `accept()` quá chậm**: nhiều client cùng truy cập có thể bị từ chối, timeout hoặc chậm thiết lập, tùy hệ điều hành/mạng.
- **Backlog lớn** không khắc phục được worker pool kiệt, socket bị giữ quá lâu hay CPU bị nghẽn; hàng đợi chỉ làm dịu các đợt burst ở khâu tiếp nhận.
- **`new ServerSocket(8080, 0)`** không nên dùng để khẳng định “không có hàng đợi”: backlog không dương sẽ dùng default phụ thuộc triển khai.
- Không viết test dựa trên việc backlog=1 chắc chắn chỉ cho một kết nối. Kết quả phụ thuộc OS, handshake, kernel queues, tốc độ `accept` và khả năng đặt các tùy chọn.

## 5. `accept()`: chờ, trả về và lặp nhận client

`Socket accepted = server.accept();` là **blocking call** trong `ServerSocket` thông thường: khi chưa có kết nối sẵn sàng, thread sẽ chờ. Khi có, phương thức trả về `Socket` mới đã kết nối với một peer, hoặc ném exception khi timeout/bị đóng/lỗi.

~~~java
// Đoạn minh họa; server đã bind:
while (!server.isClosed()) {
    try {
        Socket accepted = server.accept();
        // Chuyển Socket đến worker, hoặc xử lý trong phạm vi quản lý tài nguyên.
    } catch (SocketTimeoutException timeout) {
        // Không có client đến trong thời gian chờ; server vẫn có thể accept tiếp.
    }
}
~~~

Đây là **khung ý tưởng, không phải chương trình hoàn chỉnh**: code production cần xử lý `IOException` khi đóng server, giới hạn tài nguyên của worker và bảo đảm **mọi accepted Socket đều được đóng**. Nếu nhận rồi xử lý client hoàn toàn bên trong cùng thread, các client khác phải chờ cho đến khi xử lý xong; tùy ứng dụng nên giao cho thread pool hoặc mô hình non-blocking.

### 5.1. Đặt timeout cho `accept()`

~~~java
server.setSoTimeout(2_000); // accept() chờ tối đa ~2 giây
try {
    Socket client = server.accept();
    // Quản lý/đóng client sau khi xử lý.
} catch (SocketTimeoutException e) {
    // Hết thời gian chờ accept; listening socket vẫn dùng tiếp được.
}
~~~

`setSoTimeout(int milliseconds)` của **ServerSocket** áp cho **`accept()`**, không đặt timeout đọc dữ liệu từ client. Giá trị **0** (mặc định) là **không giới hạn thời gian chờ bằng SO_TIMEOUT**; giá trị âm bị từ chối. Đặt timeout **trước khi gọi `accept`**.

Socket được trả về có timeout I/O **riêng**. Nếu muốn chặn client gửi chậm và làm treo worker, cấu hình thêm:

~~~java
client.setSoTimeout(3_000); // timeout cho thao tác đọc input của client Socket
~~~

`SocketTimeoutException` do `accept` báo rằng **chưa có connection được accept trong khoảng chờ**, không chứng minh mạng bị hỏng. `SocketTimeoutException` khi đọc input của accepted Socket lại báo **chờ byte dữ liệu quá lâu**; đó là hai điểm nghẽn khác nhau. Timeout của `accept` không tự động đóng `ServerSocket`, và read timeout không tự động đóng accepted Socket.

### 5.2. `accept()`, handshake và request là ba việc khác nhau

Một TCP connection có thể chở nhiều request/message theo quy tắc ứng dụng. Sau `accept()`, phải đọc luồng byte có **framing** rõ ràng (length, delimiter, protocol HTTP, v.v.) nếu muốn biết lúc nào đủ một message. `Socket.getInputStream().read()` có thể đọc ít hơn số byte mong đợi; không dựa vào một `read` để suy ra toàn bộ request.

Với HTTPS, `ServerSocket` thông thường chỉ làm **plain TCP**; mã hóa/bắt tay TLS cần lớp tương ứng như `javax.net.ssl.SSLServerSocket`/`SSLSocket` (hoặc thư viện/server framework). `accept()` của TCP không có nghĩa là TLS handshake hay HTTP parsing đã hoàn tất.

## 6. Ví dụ hoàn chỉnh Java 17+: bind loopback, accept, trao đổi dữ liệu, timeout

Chương trình sau chạy **server và client trong cùng JVM** bằng loopback, không cần Internet, không chiếm cổng cố định. Nó chứng minh:

- Tạo `ServerSocket` **chưa bind**, đặt `SO_REUSEADDR` và accept timeout, rồi bind vào loopback với **port 0** và backlog 16.
- Lấy đúng cổng thực tế bằng `getLocalPort()`.
- Một task phía server gọi `accept()` và trả lời client trên **Socket riêng**.
- Client kết nối, gửi dòng `PING`, nhận `ACK:PING`; phía server trả lại nội dung đã nhận.
- Sau đó không có client mới, `accept()` chờ 200 ms rồi ném `SocketTimeoutException`; listener vẫn hợp lệ.
- Mọi `Socket` được đóng bằng `try-with-resources`, executor được shutdown.

Tạo file **`ServerSocketLifecycleDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ServerSocketLifecycleDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.setReuseAddress(true);
            listener.setSoTimeout(3_000);
            listener.bind(new InetSocketAddress(loopback, 0), 16);

            System.out.println("bound=" + listener.isBound());
            System.out.println("loopback=" +
                    listener.getInetAddress().isLoopbackAddress());
            System.out.println("portAssigned=" + (listener.getLocalPort() > 0));

            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> request = executor.submit(() -> {
                    try (Socket peer = listener.accept();
                         BufferedReader input = new BufferedReader(
                             new InputStreamReader(peer.getInputStream(),
                                 StandardCharsets.UTF_8));
                         BufferedWriter output = new BufferedWriter(
                             new OutputStreamWriter(peer.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                        peer.setSoTimeout(3_000);
                        String line = input.readLine();
                        output.write("ACK:" + line);
                        output.newLine();
                        output.flush();
                        return line;
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.setSoTimeout(3_000);
                    BufferedWriter output = new BufferedWriter(
                        new OutputStreamWriter(client.getOutputStream(),
                            StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                            StandardCharsets.UTF_8));

                    output.write("PING");
                    output.newLine();
                    output.flush();
                    System.out.println("reply=" + input.readLine());
                }

                System.out.println("received=" +
                        request.get(5, TimeUnit.SECONDS));
                listener.setSoTimeout(200);
                try {
                    listener.accept();
                    System.out.println("unexpectedSecondClient");
                } catch (SocketTimeoutException expected) {
                    System.out.println("acceptTimeout=true");
                }
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 ServerSocketLifecycleDemo.java
java ServerSocketLifecycleDemo
~~~

**Stdout đã kiểm chứng** (biên dịch ở mức Java 17 và chạy trên OpenJDK 24):

~~~text
bound=true
loopback=true
portAssigned=true
reply=ACK:PING
received=PING
acceptTimeout=true
~~~

Bài demo chỉ in `portAssigned=true` thay vì số port ngẫu nhiên, nên stdout có thể kiểm chứng ổn định. `Future.get(...)` giúp main thread đợi task phía server đọc xong `PING` và gửi phản hồi trước khi thử `accept()` lần nữa. `readLine()` và `newLine()` ở đây tạo **framing theo dòng**, tránh chờ mãi vì không có ký tự kết thúc.

**Lưu ý:** ví dụ dùng timeout vài giây để tránh treo mãi nếu môi trường chạy bị hạn chế loopback hoặc scheduler bất thường. Trong hệ thống thực, cần thiết kế logic timeout theo SLA chứ không sao chép các con số thử nghiệm này.

## 7. Kiểm tra trạng thái trước và sau bind

| API | Trước khi bind | Sau khi bind thành công | Sau khi gọi `close()` |
|---|---|---|---|
| `server.isBound()` | `false` | `true` | **Vẫn `true` nếu từng bind** |
| `server.isClosed()` | `false` nếu mới tạo | `false` | `true` |
| `server.getLocalPort()` | `-1` | Cổng thực tế | Vẫn có thể trả cổng đã bind |
| `server.getInetAddress()` | `null` | Local IP đã bind | Vẫn có thể trả địa chỉ đã bind |
| `server.getLocalSocketAddress()` | `null` | Endpoint local | Vẫn có thể trả endpoint đã bind |

**Đừng dùng riêng `isBound()` như kiểm tra server còn hoạt động**: Java ghi rõ socket đã bind rồi đóng vẫn báo từng bind. Với code server, quản lý lifecycle rõ ràng và xét cả `isClosed()`, lỗi từ `accept()` và trạng thái worker. `getLocalPort() > 0` chỉ xác nhận đã được cấp port trong demo; không chứng minh client từ Internet có thể truy cập.

## 8. Đóng listener và các kết nối đang hoạt động

Có hai cấp tài nguyên:

1. **`ServerSocket`:** đại diện cho listening endpoint, nhận kết nối mới.
2. **Mỗi `Socket` đã accept:** đại diện cho một TCP connection đang trao đổi dữ liệu, có input/output stream và timeout riêng.

Khi đóng `ServerSocket`:

- Các lời gọi `accept()` tiếp theo không được sử dụng trên listener đã đóng.
- Một thread đang blocking trong `accept()` có thể được đánh thức bằng `SocketException` khi listener bị đóng.
- Các **accepted Socket đã tồn tại không tự động đóng hết** chỉ vì listener đóng; ứng dụng phải sở hữu/đóng từng socket, hoàn tất request đang xử lý hoặc đặt chiến lược shutdown riêng.
- `try-with-resources` cho listener và accepted socket khác scope nhau giúp tránh leak descriptor.
- Nếu đang cần graceful shutdown: dừng nhận client mới, báo worker hoàn tất hoặc hủy theo deadline, đóng các accepted socket còn lại, rồi chờ executor dừng.

Đây là lý do production TCP server thường có một **accept loop** nhẹ và một cơ chế xử lý kết nối tách biệt. Để tránh cạn tài nguyên, không tạo thread vô hạn cho mọi client; cần giới hạn số kết nối/worker đang hoạt động, hàng đợi công việc, read timeout và chiều dài message.

## 9. Lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `BindException: Address already in use` | Một socket/process khác đã dùng local IP/port hoặc quy tắc hệ điều hành không cho bind lại | Kiểm tra đúng IP/port, listener cũ, container port mapping và `SO_REUSEADDR` nếu phù hợp |
| `BindException: Cannot assign requested address` | Đang bind một IP không gán cho máy/interface | Chọn local address thật, loopback hoặc wildcard phù hợp |
| Client `Connection refused` | Không có listener nhận tại endpoint được dùng hoặc kết nối bị mạng/firewall từ chối | So địa chỉ bind, cổng thực tế, trạng thái server và mạng |
| Client không kết nối được từ LAN nhưng chạy được ngay trên server | Server bind `127.0.0.1` / `::1` | Bind địa chỉ LAN hoặc wildcard khi thật sự cần truy cập từ xa; cấu hình firewall phù hợp |
| Client dùng `localhost` không connect được | IPv4/IPv6 lệch nhau | In ra địa chỉ thực tế của cả hai bên, dùng literal IP hoặc cùng `InetAddress` |
| `accept()` chờ mãi | Không có client mới, SO_TIMEOUT bằng 0 | Kiểm tra network/listen port; đặt `server.setSoTimeout(...)` nếu cần |
| `accept()` ném `SocketTimeoutException` | Đã chờ hết SO_TIMEOUT nhưng chưa nhận kết nối | Quyết định retry hoặc shutdown; listener vẫn dùng được |
| `accept()` ném `SocketException` sau shutdown | Listener bị đóng trong lúc đang chờ | Xử lý như đường shutdown có chủ đích nếu server đã đóng |
| Client connect được nhưng gửi request không có phản hồi | Worker chưa đọc/flush đúng, thiếu framing, worker bị chặn | Phân biệt bước `accept` với `read`/`write`, kiểm tra newline/length và timeout của accepted socket |
| Nhiều client báo timeout khi tăng tải | Accept loop/worker chậm, backlog/OS queues, giới hạn tài nguyên | Đo accept rate, active connections, worker queue, CPU, timeout |
| `accept()` trên ServerSocket từ `ServerSocketChannel` non-blocking | API chế độ non-blocking không tương thích với blocking accept của wrapper | Dùng `ServerSocketChannel.accept()` đúng mode và xử lý `IllegalBlockingModeException` theo API |

**Không nhầm `SO_REUSEADDR` với khả năng chạy hai listener độc lập trên cùng một IP:port.** Tùy chọn này có ngữ nghĩa phụ thuộc OS, thường hữu ích khi restart server có các connection trong `TIME_WAIT`, và nên đặt trước bind; nó không là giấy phép phổ quát để hai process tùy ý cùng listen một endpoint.

**Kiểm tra port:** trên Linux có thể dùng `ss -ltn`; trên Windows dùng `netstat -ano -p tcp` hoặc `Get-NetTCPConnection` (PowerShell). Khi thấy trạng thái `LISTEN`, vẫn phải kiểm tra đúng địa chỉ local và port; việc một socket LISTEN không bảo đảm mọi client qua firewall/NAT đều đến được.

## 10. Khi nào dùng `ServerSocket` và khi nào chọn API khác?

- **Học cơ chế TCP hoặc xây server nhỏ:** `ServerSocket` + `Socket` là lựa chọn đơn giản để hiểu bind, listen, accept và luồng byte.
- **Server có nhiều kết nối đồng thời:** vẫn có thể dùng `ServerSocket`, nhưng cần executor/pool, giới hạn kết nối và chiến lược đóng; không lấy backlog làm chỉ số công suất.
- **Server non-blocking/event loop:** cân nhắc `java.nio.channels.ServerSocketChannel` + `Selector`; cơ chế `accept` có thể không blocking theo cách của classic API. Chỉ chuyển mô hình khi có nhu cầu rõ ràng.
- **HTTPS/TLS:** dùng `SSLServerSocket` hoặc server framework hỗ trợ TLS; raw `ServerSocket` chỉ chấp nhận kết nối TCP chưa được mã hóa.
- **HTTP ứng dụng:** thường dùng HTTP server/framework đã xử lý framing, request parsing, keep-alive, TLS và lỗi giao thức. Tự viết `ServerSocket` để hiểu cơ chế là hữu ích, nhưng HTTP production có nhiều trách nhiệm ngoài `accept`.

## 11. Câu hỏi tự kiểm tra

**1. `new ServerSocket(8080)` còn cần gọi `listen()` không?** Không. Constructor đã bind và thiết lập listener; Java `ServerSocket` không có method `listen()` công khai.

**2. `new ServerSocket()` rồi gọi `accept()` ngay có đúng không?** Không. Listener chưa bind endpoint; phải gọi `bind(...)` trước.

**3. `accept()` trả dữ liệu client gửi hay trả kết nối?** Trả về **`Socket` đã kết nối**. Đọc dữ liệu qua input stream của socket đó.

**4. Backlog=128 nghĩa server chỉ được có 128 client đang hoạt động?** Không. Nó là giá trị yêu cầu về hàng đợi chờ accept, giới hạn/thực thi phụ thuộc OS; số client đã accept do thiết kế ứng dụng và tài nguyên.

**5. `port=0` có làm server lắng nghe trên cổng TCP số 0 không?** Không. Hệ điều hành cấp cổng thực tế; lấy nó bằng `getLocalPort()`.

**6. `setSoTimeout(1_000)` trên `ServerSocket` có làm `InputStream.read()` của accepted Socket timeout không?** Không. Đặt timeout đọc trên **accepted `Socket`** nếu cần.

**7. Sau khi đóng listener, `isBound()` có chuyển về false không?** Không nhất thiết; `ServerSocket` đã từng bind vẫn báo `true` theo Javadoc. Xét trạng thái `isClosed()`.

**8. Client connect thành công nghĩa server đã xử lý xong request?** Không. Connect/handshake TCP, accept và xử lý application payload là các giai đoạn khác nhau.

## Nguồn chuẩn và bài đọc thêm

- [Java SE 17 – ServerSocket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): constructors, `bind`, `accept`, backlog, `setSoTimeout`, `close` và trạng thái.
- [Java SE 17 – Socket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): connected socket, `connect`, stream và read timeout.
- [Java SE 17 – InetSocketAddress Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/InetSocketAddress.html): endpoint IP và port.
- [Java SE 17 – ServerSocketChannel Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): biến thể non-blocking/NIO.
- [RFC 9293 – Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293): TCP connection lifecycle và cơ chế giao vận.

**Ghi nhớ:** `ServerSocket` **bind local address/port → đặt hệ điều hành vào chế độ listen → `accept()` nhận một `Socket` mới cho từng connection**. Listener tiếp tục tiếp nhận client, còn mỗi accepted socket chịu trách nhiệm trao đổi byte và đóng độc lập. Phân biệt backlog, timeout của `accept`, timeout của `read`, phạm vi bind IP và vòng đời từng socket là nền tảng để viết server TCP đúng.
