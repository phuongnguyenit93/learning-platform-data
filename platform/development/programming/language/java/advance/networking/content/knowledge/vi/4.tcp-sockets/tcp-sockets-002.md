# Tạo Socket, bind địa chỉ cục bộ và connect đến điểm cuối từ xa

## 1. Socket đứng ở đâu trong một kết nối TCP?

Một kết nối TCP nối hai điểm cuối: **địa chỉ IP + số cổng cục bộ** và **địa chỉ IP + số cổng từ xa**. Trong Java, `java.net.Socket` biểu diễn một đầu kết nối TCP để đọc/ghi luồng byte. Phía server thường dùng `ServerSocket` để lắng nghe, sau đó `accept()` trả về một `Socket` mới cho từng kết nối được chấp nhận.

~~~text
Máy client                                      Máy server
local IP:local port  ------ TCP connect ----->  remote IP:remote port
192.0.2.10:51000                                192.0.2.20:8080

Nhìn từ client: local = 192.0.2.10:51000; remote = 192.0.2.20:8080
Nhìn từ server: local = 192.0.2.20:8080; remote = 192.0.2.10:51000
~~~

Các IP và port trong sơ đồ chỉ minh họa. “Local” và “remote” luôn là **vai trò tương đối với socket đang quan sát**: cổng local của client chính là cổng remote của socket do server `accept()` tạo ra.

Trong bài này cần phân biệt rõ ba hành động:

1. **`new Socket()`:** tạo đối tượng TCP chưa gắn địa chỉ nguồn, chưa có peer từ xa.
2. **`socket.bind(localEndpoint)`:** gắn socket vào một địa chỉ/cổng trên **máy cục bộ**. Thao tác này chưa kết nối đến server.
3. **`socket.connect(remoteEndpoint, timeout)`:** yêu cầu thiết lập kết nối TCP đến **IP/hostname và cổng đích**; sau khi thành công mới trao đổi được byte. Nếu socket chưa bind, hệ thống tự chọn địa chỉ và cổng local phù hợp trong quá trình connect.

Câu hỏi cốt lõi: `bind` chọn **nguồn**, `connect` chọn **đích**. Với đa số TCP client, ta **không cần bind thủ công**: chỉ `connect` đã đủ để hệ thống tự cấp nguồn.

## 2. Các lớp và kiểu địa chỉ liên quan

| Lớp hoặc API | Vai trò |
| --- | --- |
| `Socket` | Socket TCP dùng để kết nối, gửi và nhận dữ liệu |
| `ServerSocket` | Socket phía server dùng để bind cổng lắng nghe và `accept` |
| `SocketAddress` | Kiểu trừu tượng của một địa chỉ socket |
| `InetSocketAddress` | Cặp `(InetAddress/hostname, port)`; dùng làm tham số bind/connect |
| `InetAddress` | Địa chỉ IP; `getLoopbackAddress()` dùng cho thử nghiệm nội bộ |

`InetSocketAddress` chỉ **mô tả địa chỉ**, không tự tạo một kết nối hay giữ cổng khi khởi tạo. `new InetSocketAddress(loopback, 0)` là **yêu cầu** chọn cổng khi bind; nó không chứa cổng thực cho đến khi hỏi socket đã bind.

Các cách khởi tạo `Socket` cần biết:

| Cách tạo | Kết nối được thực hiện khi nào? |
| --- | --- |
| `new Socket()` | Chưa; gọi `connect(...)` sau đó |
| `new Socket(host, port)` | Ngay trong constructor |
| `new Socket(ipAddress, port)` | Ngay trong constructor |
| `new Socket(host, port, localAddress, localPort)` | Constructor chọn địa chỉ/cổng nguồn rồi kết nối |

Dùng `new Socket()` khi cần **điều khiển trình tự**, chỉ định source IP, cấu hình tùy chọn trước connect hoặc đặt connect timeout tường minh. Dùng constructor kết nối ngay cho trường hợp đơn giản. Các constructor kết nối ngay có thể ném ngoại lệ I/O ngay lúc khởi tạo.

## 3. Vòng đời: unbound, bound, connected và closed

~~~text
new Socket()
   |  trạng thái: unbound, unconnected
   |
   | [tùy chọn] bind(local IP, local port)
   v
Socket bound, vẫn unconnected
   |
   | connect(remote IP/hostname, remote port, timeout)
   v
Socket bound + connected
   |
   | getInputStream()/getOutputStream()
   | truyền byte qua TCP
   v
close()
~~~

Nếu **bỏ bước bind tường minh**, `connect` sẽ tự làm việc cần thiết để socket có local endpoint. Khi đã connected, socket không thể đổi local endpoint bằng cách bind lại.

| Thời điểm | `isBound()` | `isConnected()` | `getLocalPort()` | `getPort()` |
| --- | --- | --- | --- | --- |
| Vừa `new Socket()` | `false` | `false` | `-1` | `0` |
| Sau `bind(localIp, 0)` thành công | `true` | `false` | Cổng local thực (> 0) | `0` |
| Sau `connect(remote, timeout)` thành công | `true` | `true` | Cổng local thực | Cổng remote thực |
| Sau `close()` của socket từng kết nối | `true` | `true` | Có thể giữ port cũ | Có thể giữ port cũ |

Cột `getPort()` trong `Socket` là **cổng remote**; `getLocalPort()` mới là **cổng local**. Khi chưa bind, `getLocalSocketAddress()` trả `null`; khi chưa connect, `getRemoteSocketAddress()` trả `null`.

**Chú ý:** `isBound()` và `isConnected()` mô tả việc **đã từng thành công**, nên có thể vẫn `true` sau khi `close()`. Phải kiểm tra `isClosed()` để biết socket đã đóng; ngay cả trạng thái chưa đóng cũng không bảo đảm peer hiện vẫn sẵn sàng nếu mạng vừa lỗi.

## 4. Bind phía client: chọn địa chỉ/cổng nguồn

Một client muốn dùng IP loopback và để hệ điều hành tự cấp cổng có thể gọi:

~~~java
Socket client = new Socket();
InetSocketAddress requestedLocal =
        new InetSocketAddress(InetAddress.getLoopbackAddress(), 0);
client.bind(requestedLocal);
~~~

*Đoạn trên minh họa thao tác bên trong một chương trình có xử lý ngoại lệ và đóng socket; hai ví dụ đầy đủ nằm ở phần sau.*

Hãy đọc chính xác hai thành phần:

- `InetAddress.getLoopbackAddress()` chọn địa chỉ **máy hiện tại** (thường `127.0.0.1` hoặc `::1`). Địa chỉ nguồn phải bind được trên máy đang chạy. Không truyền IP của server từ xa vào `client.bind`.
- Port `0` nhờ hệ điều hành cấp một **cổng local khả dụng** tại lúc bind. `requestedLocal.getPort()` vẫn `0` vì `InetSocketAddress` bất biến; **`client.getLocalPort()`** trả cổng thực được cấp.

Các dạng khác:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `client.bind(new InetSocketAddress(localIp, 0))` | Chọn IP local; hệ thống chọn port local |
| `client.bind(new InetSocketAddress(localIp, 55000))` | Yêu cầu IP và port local cụ thể |
| `client.bind(new InetSocketAddress(0))` | Wildcard local + port tự cấp |
| `client.bind(null)` | Hệ thống chọn địa chỉ local hợp lệ và port tự cấp |
| Không bind trước khi connect | Hệ thống tự bind trong quá trình kết nối |

**Wildcard** (`0.0.0.0` hoặc `::`) chỉ có nghĩa đặc biệt khi bind ở **phía local**; nó không phải địa chỉ IP đích có thể gửi kết nối đến. Nếu máy có nhiều giao diện mạng, bind thủ công có thể giúp chọn IP nguồn nhưng phải chọn địa chỉ thật sự có trên máy và phù hợp với tuyến đến peer.

Đa số client không cần cổng nguồn cố định. Gán cứng một cổng có thể gây `BindException` khi cổng bị chiếm và làm khó chạy nhiều phiên song song. Nếu không có yêu cầu riêng, nên để hệ thống chọn port `0` hoặc tự bind trong `connect`.

Bind trên `ServerSocket` khác về vai trò: `listener.bind(...)` mở **điểm lắng nghe** tại server; `client.bind(...)` chọn **nguồn** cho kết nối đi ra. Cả hai đều chỉ nhận địa chỉ thuộc phía cục bộ tương ứng.

## 5. Connect phía client: chọn địa chỉ/cổng đích

Với `Socket` chưa kết nối:

~~~java
InetSocketAddress remote = new InetSocketAddress("example.com", 443);
try (Socket client = new Socket()) {
    client.connect(remote, 2_000);
    client.setSoTimeout(2_000);
    // Đọc/ghi qua client.getInputStream() và client.getOutputStream().
}
~~~

*Đoạn này dùng để giải thích API, chưa phải chương trình độc lập; ví dụ hostname không bảo đảm một dịch vụ cụ thể đang hoạt động.*

- `remote` chỉ ra **máy/cổng server**. Port đích phải là port dịch vụ thực, ví dụ `443`, không dùng port `0` như cách xin cấp port local.
- `connect(remote, 2_000)` thử bắt tay TCP, với thời hạn chờ kết nối **2.000 mili giây**; nếu thành công, socket trở thành connected và bound.
- `setSoTimeout(2_000)` áp dụng cho lần gọi `read()` chặn trên `InputStream`, **không thay thế connect timeout**.
- `new InetSocketAddress(hostname, port)` có thể phân giải DNS khi tạo. Thời gian DNS không được bảo đảm nằm trong ngân sách timeout của `connect`. Một địa chỉ unresolved có thể không được chấp nhận trong kết nối trực tiếp; khi cần proxy phải kiểm tra API/cấu hình tương ứng.

Cũng có thể gọi `connect(remote)` mà không chỉ rõ timeout; hoặc dùng constructor kết nối ngay. Tuy nhiên, với mạng không tin cậy, truyền connect timeout dương cụ thể giúp kiểm soát thời gian chờ. Connect timeout `0` có nghĩa chờ không giới hạn tới khi kết nối được hoặc có lỗi.

**Kết nối TCP thành công chưa có nghĩa ứng dụng từ xa đã xử lý một yêu cầu**: sau connect phải trao đổi các byte đúng giao thức ứng dụng. TCP cung cấp luồng byte có thứ tự chứ không tự bảo toàn ranh giới “một thông điệp”.

## 6. Ví dụ 1: không bind thủ công, connect tự chọn local endpoint

Ví dụ chạy server và client TCP **trên cùng máy**, không dùng Internet. Server bind loopback tại port `0`, lấy cổng thực; client chỉ `connect` rồi hệ điều hành cấp local IP/port.

Tạo tệp `SocketAutoBindDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketAutoBindDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            try (Socket client = new Socket()) {
                System.out.println("new: bound=" + client.isBound()
                        + ", connected=" + client.isConnected());
                System.out.println("new local port: " + client.getLocalPort());
                System.out.println("new remote port: " + client.getPort());

                client.connect(listener.getLocalSocketAddress(), 2_000);
                try (Socket incoming = listener.accept()) {
                    System.out.println("connected: bound=" + client.isBound()
                            + ", connected=" + client.isConnected());
                    System.out.println("auto local port allocated: "
                            + (client.getLocalPort() > 0));
                    System.out.println("client remote = listener local: "
                            + (client.getPort() == listener.getLocalPort()));
                    System.out.println("server sees client local port: "
                            + (incoming.getPort() == client.getLocalPort()));
                    client.getOutputStream().write(65);
                    System.out.println("server received: "
                            + incoming.getInputStream().read());
                }
            }
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac SocketAutoBindDemo.java
java SocketAutoBindDemo
~~~

Kết quả khi hệ thống cho phép dùng TCP loopback:

~~~text
new: bound=false, connected=false
new local port: -1
new remote port: 0
connected: bound=true, connected=true
auto local port allocated: true
client remote = listener local: true
server sees client local port: true
server received: 65
~~~

Giải thích theo thứ tự thực thi:

1. `listener.bind(new InetSocketAddress(loopback, 0))` tạo một cổng server tự cấp. `listener.getLocalSocketAddress()` trả đúng địa chỉ đích mà client cần.
2. `new Socket()` của client chưa bind/connect, nên `getLocalPort() == -1` và `getPort() == 0`.
3. `client.connect(...)` tự chọn local endpoint; sau đó cả `isBound()` và `isConnected()` đều `true`.
4. `listener.accept()` trả `incoming`, một `Socket` phía server. `incoming.getPort()` là cổng nguồn của client, nên trùng `client.getLocalPort()`.
5. Client ghi một byte `65` qua `OutputStream`, server đọc được `65`. `ServerSocket` tiếp tục là listener; `incoming` mới là socket xử lý kết nối ấy.

Ví dụ kiểm tra các điều kiện bằng boolean thay vì in số cổng thay đổi theo mỗi lần chạy. Địa chỉ loopback lấy từ cùng đối tượng `InetAddress` giúp chạy được trên môi trường ưu tiên IPv4 hoặc IPv6.

## 7. Ví dụ 2: bind nguồn trước rồi connect đích

Trường hợp này dùng cùng server loopback nhưng client gọi `bind` **trước**. Ta sẽ thấy trạng thái **đã bind nhưng chưa connected**, sau đó đối chiếu hai phía của kết nối.

Tạo tệp `SocketExplicitBindDemo.java`:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class SocketExplicitBindDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            InetSocketAddress requestedLocal = new InetSocketAddress(loopback, 0);
            try (Socket client = new Socket()) {
                client.bind(requestedLocal);
                System.out.println("request port stays zero: "
                        + (requestedLocal.getPort() == 0));
                System.out.println("after bind: bound=" + client.isBound()
                        + ", connected=" + client.isConnected());
                System.out.println("actual local port > 0: "
                        + (client.getLocalPort() > 0));
                System.out.println("remote before connect is null: "
                        + (client.getRemoteSocketAddress() == null));

                InetSocketAddress destination =
                        new InetSocketAddress(loopback, listener.getLocalPort());
                client.connect(destination, 2_000);
                try (Socket incoming = listener.accept()) {
                    System.out.println("client remote port is listener port: "
                            + (client.getPort() == listener.getLocalPort()));
                    System.out.println("accepted remote port is client local port: "
                            + (incoming.getPort() == client.getLocalPort()));
                }
                client.close();
                System.out.println("after close: bound=" + client.isBound()
                        + ", connected=" + client.isConnected()
                        + ", closed=" + client.isClosed());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac SocketExplicitBindDemo.java
java SocketExplicitBindDemo
~~~

Kết quả:

~~~text
request port stays zero: true
after bind: bound=true, connected=false
actual local port > 0: true
remote before connect is null: true
client remote port is listener port: true
accepted remote port is client local port: true
after close: bound=true, connected=true, closed=true
~~~

Ba điều dễ hiểu sai được minh chứng trực tiếp:

- `requestedLocal.getPort()` vẫn `0` do `InetSocketAddress` bất biến. Cổng **thực** đã bind nằm ở `client.getLocalPort()` và `client.getLocalSocketAddress()`.
- Sau bind nhưng trước connect: `isBound() == true`, `isConnected() == false` và `getRemoteSocketAddress() == null`. `bind` không tạo kết nối TCP đến máy đích.
- Sau `close()`: `isClosed() == true`, nhưng `isBound()` và `isConnected()` vẫn `true` do chúng ghi nhận trạng thái đã từng thành công. Socket đã đóng không còn dùng được để trao đổi byte.

Để minh họa trạng thái sau đóng, chương trình gọi `close()` tường minh. Khi thoát `try-with-resources`, lời gọi đóng bổ sung là an toàn.

## 8. Đọc đúng endpoint ở mỗi phía

Các getter thường dùng:

| API của `Socket` | Địa chỉ/cổng được trả |
| --- | --- |
| `getLocalAddress()` | Địa chỉ IP cục bộ của socket |
| `getLocalPort()` | Cổng cục bộ; `-1` khi chưa bind |
| `getLocalSocketAddress()` | Endpoint local; `null` khi chưa bind |
| `getInetAddress()` | Địa chỉ IP từ xa sau connect |
| `getPort()` | Cổng từ xa; `0` khi chưa connect |
| `getRemoteSocketAddress()` | Endpoint remote; `null` khi chưa connect |

Với kết nối được chấp nhận qua `ServerSocket listener`:

- `listener.getLocalPort()` là cổng server đang nghe.
- `client.getPort()` là cổng remote nhìn từ **client**, bằng cổng server đang nghe.
- `incoming.getLocalPort()` là cổng local nhìn từ **server**, cũng là cổng server đang nghe.
- `incoming.getPort()` là cổng remote nhìn từ **server**, bằng cổng local của client.

Để chẩn đoán khi đã connect, có thể ghi log:

~~~java
System.out.println("local=" + client.getLocalSocketAddress());
System.out.println("remote=" + client.getRemoteSocketAddress());
~~~

*Đây là đoạn minh họa bên trong một phương thức đang có biến `client`, không phải chương trình chạy độc lập.* Khi chưa bind/connect, một hoặc cả hai giá trị có thể là `null`. Không cố phân tích các IP/port bằng cách cắt chuỗi `toString()`, vì định dạng có thể khác giữa IPv4, IPv6 và hostname.

## 9. Timeout, ngoại lệ và đóng tài nguyên

| Cài đặt/phương thức | Chờ thao tác nào? |
| --- | --- |
| `client.connect(remote, 2_000)` | Hạn chờ thiết lập kết nối TCP trong 2.000 ms |
| `client.setSoTimeout(2_000)` | Hạn chờ cho thao tác `read()` chặn trên `InputStream` |
| `listener.setSoTimeout(2_000)` | Hạn chờ cho `ServerSocket.accept()` |

Chúng là ba hạn chờ **khác nhau**. Không được hiểu connect timeout là thời gian tối đa cho DNS + đọc + ghi + toàn bộ yêu cầu ứng dụng. Trong những API trên, `0` thường là không có giới hạn thời gian chờ; giá trị âm không hợp lệ.

Các lỗi thường gặp:

- **`BindException`:** cổng nguồn bị chiếm hoặc IP nguồn không bind được. Chọn port `0` giúp tránh cố định cổng không cần thiết.
- **`ConnectException`:** máy đích/cổng đích từ chối kết nối, ví dụ không có service đang nghe.
- **`SocketTimeoutException`:** hết hạn chờ connect, read hoặc accept tương ứng. Timeout không tự xác định chính xác nguyên nhân mạng.
- **`UnknownHostException` hoặc unresolved address:** có vấn đề khi cần phân giải hostname. `new InetSocketAddress(String, int)` có thể cố gắng DNS ngay trong constructor và giữ trạng thái unresolved nếu thất bại.
- **`SocketException`/`IOException`:** socket bị đóng, trạng thái không hợp lệ hoặc lỗi I/O khác. `IllegalArgumentException` dùng cho nhiều tham số không hợp lệ, ví dụ timeout âm.

Luôn đóng `Socket`/`ServerSocket` bằng `try-with-resources` để tránh rò rỉ mô tả socket và kết nối. Nếu connect thất bại, nên đóng socket đó và tạo `Socket` mới cho một lần thử độc lập. Không giả định có thể gọi `bind` nhiều lần trên một socket đã bound, hoặc thay địa chỉ nguồn sau khi đã connected. Khi muốn xử lý nhiều client, server có thể tiếp tục `accept()` ở listener; từng socket được accept phải được quản lý và đóng riêng.

Đừng dựa vào `SO_REUSEADDR` như một cách đảm bảo mọi cặp bind trùng IP/port đều hợp lệ: hành vi phụ thuộc hệ thống và trạng thái socket.

## 10. Lỗi thường gặp và hướng sửa

1. **Dùng `client.bind(serverIp:serverPort)`:** sai vai trò. Bind nhận địa chỉ **máy client**, còn địa chỉ server đặt ở `connect`.
2. **Dùng port `0` cho điểm cuối remote:** port `0` dùng để xin cấp cổng khi **bind local**. Client phải biết cổng thật của server.
3. **Cố định một cổng nguồn cho mọi phiên:** dễ đụng cổng, khó chạy đồng thời. Dùng port tự cấp hoặc bỏ `bind` khi không có yêu cầu đặc biệt.
4. **Nghĩ `new Socket()` đã kết nối:** constructor không tham số tạo socket chưa kết nối. Constructor nhận host/port mới chủ động kết nối ngay.
5. **Nghĩ bind thành công nghĩa server đã trả lời:** bind không hề liên hệ server; phải connect trước, sau đó ứng dụng còn phải gửi/nhận dữ liệu đúng giao thức.
6. **Gọi `bind` sau `connect`:** lúc này socket đã có local endpoint; không bind lại để đổi nguồn được.
7. **Dùng `isConnected()` thay `isClosed()`:** `isConnected()` có thể vẫn `true` sau close; cũng không bảo đảm mạng sẽ không đứt giữa hai thao tác.
8. **Không giới hạn thời gian chờ:** connect/read/accept có thể chặn; đặt timeout phù hợp và xử lý `SocketTimeoutException`.
9. **Bind wildcard khi chỉ muốn phục vụ nội bộ:** server thử nghiệm nên bind loopback để giới hạn phạm vi giao diện nghe; vẫn phải xét firewall và chính sách mạng.
10. **Đọc cổng từ đối tượng yêu cầu `InetSocketAddress(..., 0)` sau bind:** nó vẫn `0`. Đọc từ `Socket.getLocalPort()` hoặc `ServerSocket.getLocalPort()` sau bind thành công.

## 11. Tự kiểm tra và luyện tập

**Câu 1.** Vừa gọi `Socket s = new Socket()`. `s.isBound()` và `s.isConnected()` là gì, `s.getLocalPort()` bằng bao nhiêu?

Đáp án: `false`, `false` và `-1`. `s.getPort()` khi chưa connect là `0`.

**Câu 2.** Gọi `s.bind(new InetSocketAddress(loopback, 0))` thành công nhưng chưa connect. Đã có local port thật chưa? Đã có remote endpoint chưa?

Đáp án: có local port thật, đọc bằng `s.getLocalPort()`; chưa có remote endpoint, nên `s.getRemoteSocketAddress() == null`.

**Câu 3.** Client có local port `51432` và connect đến server port `8080`. Sau `accept`, `incoming.getPort()` ở server thường là bao nhiêu?

Đáp án: `51432`. Đây là cổng remote **nhìn từ server**; `incoming.getLocalPort()` là `8080`.

**Câu 4.** Bỏ `client.bind(requestedLocal)` khỏi ví dụ thứ hai. Lúc trước connect `client.getLocalPort()` là gì, và sau connect thành công thay đổi ra sao?

Đáp án: trước connect là `-1`; sau connect, hệ điều hành tự bind cổng local thật (thường > 0).

**Thực hành:** chạy hai ví dụ vài lần và quan sát số cổng thực bằng cách in `getLocalPort()`. Đừng viết kiểm thử khẳng định hai lần chạy **bắt buộc** được cấp hai cổng khác nhau: hệ điều hành có thể cấp lại cổng đã giải phóng. Bổ sung lệnh in `getLocalSocketAddress()`/`getRemoteSocketAddress()` sau connect để đối chiếu với các giá trị phía `incoming`.

## Tài liệu API

- [`Socket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [`ServerSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html)
- [`InetSocketAddress` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetSocketAddress.html)
