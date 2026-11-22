# SO_KEEPALIVE, TCP_NODELAY, SO_LINGER và bộ đệm gửi/nhận trong Java TCP Socket

**Chủ đề:** Java Advance - networking  
**Nhóm:** TCP với Socket

Khi lập trình TCP bằng **java.net.Socket**, chúng ta thường đặt câu hỏi: Tại sao kết nối im lặng nhưng chưa phát hiện peer đã biến mất? Vì sao nhiều lần ghi rất ít byte có độ trễ? Vì sao **close()** đôi khi chờ, đôi khi làm phía nhận thấy **Connection reset**? Vì sao tăng bộ đệm vẫn không làm ứng dụng nhanh hơn? Bốn nhóm tùy chọn **SO_KEEPALIVE**, **TCP_NODELAY**, **SO_LINGER**, **SO_SNDBUF/SO_RCVBUF** điều chỉnh các hành vi khác nhau của **TCP stack trong hệ điều hành**.

Đây là tùy chọn của **transport/socket**, không định nghĩa request, response hay việc xử lý nghiệp vụ. Một **write()** thành công chưa chứng minh tiến trình bên kia đã đọc hoặc commit giao dịch. Các giá trị mặc định, giới hạn dung lượng và hiệu quả phụ thuộc hệ điều hành, JDK, trạng thái kết nối và điều kiện mạng.

## 1. Sơ đồ tầng và bảng tra cứu nhanh

~~~text
Ứng dụng Java                           Ứng dụng Java
      │  ghi byte / đọc response              ▲
      ▼                                       │
BufferedOutputStream (nếu dùng)       BufferedInputStream (nếu dùng)
      │                                       ▲
Socket.getOutputStream()               Socket.getInputStream()
      │                                       ▲
TCP send buffer (OS)                    TCP receive buffer (OS)
      │  TCP segments / ACK / window          ▲
      └──────── IP, mạng hoặc loopback ───────┘

TCP_NODELAY: lựa chọn dùng Nagle khi gửi các đoạn dữ liệu nhỏ
SO_KEEPALIVE: probe TCP khi kết nối không hoạt động trong thời gian dài
SO_LINGER: hành vi close() khi còn dữ liệu chưa truyền xong
SO_SNDBUF: gợi ý dung lượng send buffer cấp kernel
SO_RCVBUF: gợi ý dung lượng receive buffer cấp kernel
~~~

| Tùy chọn | API Socket cổ điển | Ảnh hưởng chủ yếu | Điều **không** được bảo đảm |
| --- | --- | --- | --- |
| **SO_KEEPALIVE** | **setKeepAlive(boolean)** / **getKeepAlive()** | Kiểm tra kết nối TCP nhàn rỗi bằng cơ chế của OS | Không phải heartbeat nghiệp vụ; không có thời gian phát hiện cố định |
| **TCP_NODELAY** | **setTcpNoDelay(boolean)** / **getTcpNoDelay()** | Bật/tắt thuật toán Nagle để cân bằng độ trễ và packet nhỏ | Không đồng nghĩa mỗi write tạo một packet; không ép peer đọc ngay |
| **SO_LINGER** | **setSoLinger(boolean, int)** / **getSoLinger()** | Cách **close()** xử lý byte TCP chưa gửi xong | Không xác nhận server đã xử lý dữ liệu |
| **SO_SNDBUF** | **setSendBufferSize(int)** / **getSendBufferSize()** | Gợi ý dung lượng send buffer của socket | Không phải số byte chắc chắn có thể write mà không block |
| **SO_RCVBUF** | **setReceiveBufferSize(int)** / **getReceiveBufferSize()** | Gợi ý dung lượng receive buffer, có liên quan TCP receive window | Không phải kích thước tối đa một message |

Tất cả các tùy chọn trên có thể cấu hình trên socket theo API và tùy trạng thái thích hợp. Với **SocketChannel**, các tương đương tiêu chuẩn nằm trong **java.net.StandardSocketOptions**. **ServerSocket** có **setReceiveBufferSize(...)** cho các kết nối sẽ được **accept()**, nhưng không có ý nghĩa “bật TCP_NODELAY cho mọi client” thông qua cùng một setter ở listener.

## 2. SO_KEEPALIVE: phát hiện kết nối TCP nhàn rỗi đã hỏng

### Vấn đề cần giải quyết

Giả sử client giữ kết nối TCP lâu dài với server. Một thiết bị trung gian mất điện hoặc peer bị ngắt mạng mà không gửi FIN/RST. Chương trình Java có thể vẫn giữ **Socket.isConnected() == true**; method này phản ánh trạng thái đã từng kết nối, **không phải phép ping** xác nhận peer còn sống ở thời điểm gọi. Trong thời gian không có I/O, TCP có thể chưa nhận được dấu hiệu lỗi.

**SO_KEEPALIVE** cho phép TCP stack của hệ điều hành phát các **keepalive probe** khi kết nối đã nhàn rỗi đủ lâu. Nếu các probe không nhận được phản hồi theo chính sách của hệ điều hành, TCP có thể đánh dấu kết nối hỏng; thao tác I/O sau đó có thể nhận lỗi. Đường truyền và thiết bị NAT/firewall cũng ảnh hưởng đến việc idle connection tồn tại được bao lâu.

### API và vòng đời

~~~java
Socket socket = new Socket();
socket.setKeepAlive(true);
boolean enabled = socket.getKeepAlive(); // true nếu đặt tùy chọn thành công
~~~

Đây là **snippet** minh họa, không tạo kết nối vì chưa gọi **connect(...)**. Theo Java StandardSocketOptions, trạng thái mặc định của **SO_KEEPALIVE** là **false**; nên kiểm tra trạng thái thực của socket thay vì dựa vào giả định về toàn bộ môi trường.

**SO_KEEPALIVE=true không có nghĩa vài giây sau sẽ phát hiện lỗi.** OS quyết định thời gian idle trước probe, khoảng cách giữa các probe, số lần thử và cách kết luận. Một số hệ thống mặc định thời gian nhàn rỗi khoảng **hai giờ**, nhưng con số đó không phải cam kết của Java. TCP keepalive là tín hiệu ở tầng truyền tải, không thể chứng minh ứng dụng bên kia đang xử lý request đúng hay còn đủ tài nguyên.

### Cần timeout ngắn hoặc heartbeat nghiệp vụ?

- **TCP keepalive** phù hợp để phát hiện một số kết nối TCP hỏng sau thời gian idle, có chi phí giao thức thấp, nhưng thời gian phát hiện thường dài hoặc phụ thuộc OS.
- **Socket.setSoTimeout(ms)** đặt timeout cho thao tác **read()** đang chờ trên Socket; nó **không** tự gửi keepalive, không đặt timeout cho **write()** và không phải deadline của toàn bộ request.
- **Socket.connect(address, ms)** đặt timeout cho bước connect; không quyết định timeout đọc phản hồi.
- **Heartbeat tầng ứng dụng** (ví dụ **PING/PONG** mang message ID) xác minh rằng peer đã **đọc và phản hồi theo protocol**, hữu ích khi cần health/deadline ngắn hơn. Vẫn phải cân nhắc lịch gửi, jitter, retry và khả năng ứng dụng bị quá tải.
- Một connection qua load balancer/NAT có thể bị cắt khi idle dù SO_KEEPALIVE bật; nếu cần giữ kết nối ở một hệ thống cụ thể, phải hiểu chính sách timeout của mọi chặng.

### Điều chỉnh thời gian keepalive nâng cao

Từ Java 11, module **jdk.net** cung cấp các option tùy nền tảng:

- **ExtendedSocketOptions.TCP_KEEPIDLE**: số giây không hoạt động trước khi bắt đầu probe.
- **ExtendedSocketOptions.TCP_KEEPINTERVAL**: khoảng cách giây giữa các probe khi chưa được đáp.
- **ExtendedSocketOptions.TCP_KEEPCOUNT**: giới hạn số probe không được đáp trước khi đánh giá connection hỏng.

Ví dụ mô tả API (chỉ áp dụng khi option được nền tảng hỗ trợ):

~~~java
import jdk.net.ExtendedSocketOptions;
import java.net.Socket;

try (Socket socket = new Socket()) {
    if (socket.supportedOptions().contains(ExtendedSocketOptions.TCP_KEEPIDLE)) {
        socket.setOption(ExtendedSocketOptions.TCP_KEEPIDLE, 60);
    }
    socket.setKeepAlive(true);
}
~~~

Đây là **đoạn minh họa riêng**, không kết nối tới server. Khi dùng module trong chương trình dạng module, cần khai báo dependency **requires jdk.net;** và kiểm tra hỗ trợ của hệ điều hành. Không tự động đặt ba tham số giống nhau trên mọi OS: một số nền tảng không hỗ trợ option hoặc giới hạn giá trị khác nhau. Đừng dùng SO_KEEPALIVE thay cho timeout/heartbeat trong protocol có SLA rõ.

## 3. TCP_NODELAY: Nagle, gói nhỏ và độ trễ

### Nagle làm gì?

TCP là **byte stream** và có thể phải gửi nhiều đoạn byte nhỏ. **Thuật toán Nagle** là một trong những cơ chế giúp hạn chế việc phát quá nhiều segment nhỏ khi vẫn còn dữ liệu chưa được xác nhận (unacknowledged). Khi Nagle đang bật, một số lần gửi nhỏ có thể được gom/đợi thay vì lập tức tạo thêm segment nhỏ.

~~~text
Ứng dụng: write("A") → write("B") → write("C")
                    │
       Nagle có thể trì hoãn/gom byte nhỏ
                    │
TCP/IP: số segment và thời điểm gửi phụ thuộc ACK, OS,
        send buffer, congestion/flow control và trạng thái link
~~~

**TCP_NODELAY=true** yêu cầu **tắt Nagle**. Tên option dễ gây nhầm: **true** nghĩa là *no delay do Nagle*, còn **false** nghĩa là cho phép Nagle hoạt động.

~~~java
socket.setTcpNoDelay(true);   // tắt Nagle
boolean noDelay = socket.getTcpNoDelay();

socket.setTcpNoDelay(false);  // cho phép Nagle
~~~

### Khi nào cân nhắc true?

- Giao thức **request/response nhỏ, nhạy latency**: ví dụ interactive commands, một số RPC hoặc session cần phản hồi nhanh.
- Nhiều write rất nhỏ có thể chịu tác động tương tác giữa Nagle và **delayed ACK** ở phía peer; đo thực tế có thể cho thấy delay. Tắt Nagle đôi khi cải thiện latency.
- Nếu chương trình truyền dữ liệu khối lớn, chi phí packet nhỏ và số system call có thể quan trọng hơn. **Batching/framing** hợp lý hoặc đệm ở ứng dụng thường hữu ích trước khi chỉnh cờ.

### Các giới hạn dễ bỏ sót

1. **TCP_NODELAY không tắt BufferedOutputStream/BufferedWriter**. Nếu writer còn giữ byte, phải gọi **flush()** đúng lúc theo protocol.
2. **flush()** và **TCP_NODELAY** không cam kết peer đã nhận hoặc ứng dụng peer đã xử lý.
3. **TCP_NODELAY=true** không ép **một write() = một segment**, không tắt TCP congestion control, không tắt delayed ACK của peer và không loại bỏ buffering ở TLS, framework hay NIC.
4. Tắt Nagle có thể tăng số packet nhỏ, overhead CPU/mạng và giảm throughput trên workload khác. Benchmark bằng payload, RTT, concurrent connections và metric thật.

**Nguyên tắc:** chọn theo nhu cầu latency/throughput cụ thể. Nếu ứng dụng gửi từng ký tự trong nhiều write liên tiếp, nên xem lại cách gom request trước khi quyết định chỉ bật TCP_NODELAY.

## 4. SO_LINGER: chuyện gì xảy ra khi close()?

Khi ứng dụng gọi **Socket.close()**, có thể vẫn còn byte TCP trong send buffer chưa được gửi hoặc chưa được xác nhận. **SO_LINGER** điều chỉnh **hành vi đóng socket trong trường hợp này**. Nó **không** thay đổi timeout khi **connect()** hoặc **read()**, và không phải cơ chế “giữ kết nối sống thêm N giây” cho nghiệp vụ.

| Cấu hình | Hành vi điển hình |
| --- | --- |
| **setSoLinger(false, 0)** | Tắt linger; **getSoLinger() == -1**. **close()** không chờ cho tới khi toàn bộ byte chưa gửi được truyền; OS có thể tiếp tục gửi phần còn lại nếu có thể |
| **setSoLinger(true, 0)** | Linger bật với timeout **0**: **abortive close**; trên TCP thường đóng cưỡng bức bằng RST, có thể làm peer nhận **Connection reset** và mất byte chưa đọc |
| **setSoLinger(true, n)** với **n > 0** | Khi còn byte chưa gửi, **close()** có thể block tối đa khoảng **n giây** để OS cố gửi dữ liệu; tới giới hạn vẫn có thể đóng cưỡng bức |

Theo Java **Socket.setSoLinger(boolean, int)**, đơn vị timeout là **giây**; giới hạn tối đa là phụ thuộc nền tảng. **getSoLinger()** trả **-1** khi tắt. **SO_LINGER** chỉ ảnh hưởng **close**, không biến việc gọi **close()** thành xác nhận application-level.

Một vài điểm kỹ thuật:

- **setSoLinger(true, 0)** là tình huống có chủ đích, thường để bỏ nhanh một connection; **không** nên dùng như mặc định của giao thức cần giao hết response.
- **setSoLinger(true, 5)** không bảo đảm bên nhận đã gọi read, parse hay commit request. TCP ACK (nếu có) xác nhận ở tầng TCP, không phải xử lý nghiệp vụ.
- Khi linger đang bật, việc **close()** có thể block và ảnh hưởng latency/tài nguyên thread, đặc biệt khi network chậm hoặc peer không nhận.
- Với **SocketChannel** ở **non-blocking mode**, contract của **SO_LINGER khi close** không được định nghĩa như socket blocking; cần đặc biệt thận trọng.
- Không dùng SO_LINGER để giải quyết framing. Muốn xác nhận đã nhận đủ dữ liệu, hãy đọc **response** của protocol rồi mới đóng.

**Đóng kết nối đúng cách trong chương trình bình thường** thường là: gửi request có framing, nếu cần thì **shutdownOutput()** để báo hoàn tất chiều gửi, đọc hết response theo protocol, sau đó đóng socket bằng **try-with-resources**. Việc **shutdownOutput()** gửi dấu kết thúc chiều gửi (TCP FIN theo ngữ nghĩa half-close) khi thích hợp, nhưng cũng không chứng minh xử lý nghiệp vụ thành công. Không dùng EOF làm delimiter trừ khi protocol định nghĩa như vậy.

## 5. SO_SNDBUF và SO_RCVBUF: các bộ đệm TCP của kernel

Hai option này điều chỉnh **gợi ý** dung lượng bộ đệm TCP do **hệ điều hành** quản lý, không phải kích thước của **byte[]**, **ByteBuffer** hay **BufferedWriter** trong Java.

~~~text
BÊN GỬI                                      BÊN NHẬN
Ứng dụng → Java stream → kernel send buffer    kernel receive buffer → Java stream → ứng dụng
                               │      mạng      ▲
                               └──── TCP/IP ────┘
Ghi nhanh hơn khả năng truyền → send queue có thể đầy
Đọc chậm hơn tốc độ nhận → receive queue đầy, advertised window có thể thu hẹp
~~~

### SO_SNDBUF: bộ đệm gửi

~~~java
socket.setSendBufferSize(16 * 1024);
int actualSendBytes = socket.getSendBufferSize();
~~~

Khi ứng dụng ghi byte vào TCP socket, kernel thường chấp nhận byte vào hàng đợi gửi rồi phát đi theo điều kiện TCP. Nếu peer đọc chậm, receive window nhỏ, congestion window giảm hoặc đường truyền tắc, send buffer có thể đầy; **blocking write()** có thể đợi và do đó biểu hiện **backpressure**. Với SocketChannel non-blocking, **write()** có thể trả số byte nhỏ hơn yêu cầu hoặc **0**, và caller phải đợi readiness rồi tiếp tục ghi.

**setSendBufferSize(n)** chỉ là **hint**; OS có thể áp dụng giá trị khác, tự điều chỉnh hoặc giới hạn bởi policy. Luôn dùng **getSendBufferSize()** để quan sát kích thước báo về. Kích thước lớn không làm mạng hết mất gói hoặc biến write thành “đã gửi đến peer”.

### SO_RCVBUF: bộ đệm nhận

~~~java
socket.setReceiveBufferSize(32 * 1024);
int actualReceiveBytes = socket.getReceiveBufferSize();
~~~

Receive buffer lưu byte TCP mà kernel đã nhận nhưng ứng dụng chưa đọc. Khả năng nhận có liên quan đến **TCP advertised receive window**: nếu ứng dụng đọc chậm, receive buffer đầy, TCP có thể quảng bá cửa sổ nhỏ hoặc bằng không để yêu cầu sender chậm lại. Tăng receive buffer **có thể** giúp đường truyền có độ trễ lớn và tốc độ cao hoạt động hiệu quả hơn, nhưng không thay thế tốc độ đọc, giải mã và xử lý.

Đừng nhầm:

- **SO_RCVBUF** với kích thước một TCP segment: một lần read() có thể trả ít hoặc nhiều byte hơn một segment.
- **SO_RCVBUF** với số byte cố định mỗi lần read: chính caller quyết định kích thước byte[]/ByteBuffer, và read vẫn có thể trả ít hơn.
- **SO_RCVBUF** với message limit: protocol vẫn cần giới hạn payload để tránh đọc và phân bổ bộ nhớ vô hạn.
- Bộ đệm OS với bộ đệm ứng dụng: **BufferedInputStream**, **BufferedOutputStream**, Netty buffer, TLS record, v.v. là các lớp đệm khác.

### Tại sao thời điểm cấu hình lại quan trọng?

Theo **Socket Javadoc**, nếu ứng dụng cần TCP receive window lớn hơn **64 KiB**, nên yêu cầu **SO_RCVBUF** **trước khi kết nối**. Cụ thể:

1. **Client Socket**: gọi **setReceiveBufferSize(...)** trên socket chưa connect, sau đó mới **connect(...)**.
2. **Server side**: tạo **new ServerSocket()** chưa bind, gọi **ServerSocket.setReceiveBufferSize(...)**, rồi mới **bind(...)**. Đây là giá trị đề xuất cho các **Socket** trả về từ **accept()**.
3. Sau **accept()**, gọi **accepted.getReceiveBufferSize()** để xác minh giá trị thực tế. Thay đổi giá trị sau đó không thay thế được mọi yêu cầu thương lượng window scaling khi bắt tay TCP.

~~~java
ServerSocket listener = new ServerSocket();
listener.setReceiveBufferSize(256 * 1024); // trước bind()
listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
// Socket accepted = listener.accept();
// int actual = accepted.getReceiveBufferSize();
~~~

Đoạn trên là **snippet**, cần import **java.net.\***, xử lý exception và đóng listener khi dùng thực tế. **setReceiveBufferSize** không bảo đảm kernel cấp đúng 256 KiB; OS có giới hạn và cơ chế autotuning riêng.

### Bao nhiêu buffer là phù hợp?

Không có một kích thước đúng cho mọi ứng dụng. Với một đường truyền có **100 Mbit/s** và **RTT 100 ms**, bandwidth-delay product ước lượng khoảng:

~~~text
100,000,000 bit/s × 0.1 s ÷ 8 = 1,250,000 byte ≈ 1.25 MB
~~~

Đây chỉ là ước lượng lượng byte có thể đang “trên đường” tại một thời điểm khi muốn tận dụng throughput. Window scaling, congestion window, kernel autotuning, số kết nối, memory pressure, số lần copy, cách ghi/đọc và chính sách OS cùng quyết định hiệu quả. Không suy ra rằng mỗi socket nhất thiết phải cấu hình **1.25 MB**, hay nâng cả hai buffer lên vô hạn là tối ưu.

**Tuning có ý nghĩa khi đo được** sender blocked, receive queue backlog, RTT/throughput, dropped/retransmitted packets, bộ nhớ trên mỗi connection và latency phân vị (p95/p99). Với nhiều nghìn kết nối, tăng buffer quá cao có thể tăng chi phí bộ nhớ đáng kể.

## 6. Chương trình Java 17+ tự chạy trên TCP loopback

Ví dụ sau đặt đủ bốn nhóm tùy chọn, tạo kết nối loopback giữa client và server, gửi **ping** và nhận **pong**. Vì giá trị thực của buffer phụ thuộc OS, chương trình chỉ kiểm tra buffer **dương**, không in một số cụ thể rồi giả định luôn đúng.

Tạo tệp **SocketOptionsDemo.java**:

~~~java
import java.io.DataInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class SocketOptionsDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket()) {
            // Đặt receive-buffer hint trước khi bind cho accepted socket.
            listener.setReceiveBufferSize(64 * 1024);
            listener.bind(new InetSocketAddress(loopback, 0));

            try (Socket client = new Socket()) {
                client.setKeepAlive(true);        // Bật TCP keepalive.
                client.setTcpNoDelay(true);       // Tắt Nagle.
                client.setSoLinger(false, 0);     // Không chờ linger khi close.
                client.setSendBufferSize(16 * 1024);
                client.setReceiveBufferSize(32 * 1024);
                client.connect(new InetSocketAddress(
                        loopback, listener.getLocalPort()), 3000);
                client.setSoTimeout(3000);

                try (Socket serverSide = listener.accept()) {
                    serverSide.setSoTimeout(3000);

                    System.out.println("keepalive=" + client.getKeepAlive());
                    System.out.println("nodelay=" + client.getTcpNoDelay());
                    System.out.println("linger=" + client.getSoLinger());
                    System.out.println("sendBufferPositive=" +
                            (client.getSendBufferSize() > 0));
                    System.out.println("receiveBufferPositive=" +
                            (client.getReceiveBufferSize() > 0));
                    System.out.println("acceptedBufferPositive=" +
                            (serverSide.getReceiveBufferSize() > 0));

                    client.getOutputStream().write(
                            "ping".getBytes(StandardCharsets.UTF_8));
                    byte[] request = new byte[4];
                    new DataInputStream(serverSide.getInputStream())
                            .readFully(request);
                    System.out.println("request=" +
                            new String(request, StandardCharsets.UTF_8));

                    serverSide.getOutputStream().write(
                            "pong".getBytes(StandardCharsets.UTF_8));
                    byte[] response = new byte[4];
                    new DataInputStream(client.getInputStream())
                            .readFully(response);
                    System.out.println("response=" +
                            new String(response, StandardCharsets.UTF_8));
                }
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac --release 17 -encoding UTF-8 SocketOptionsDemo.java
java SocketOptionsDemo
~~~

**Kết quả mong đợi trong môi trường cho phép tạo TCP loopback socket:**

~~~text
keepalive=true
nodelay=true
linger=-1
sendBufferPositive=true
receiveBufferPositive=true
acceptedBufferPositive=true
request=ping
response=pong
~~~

Ví dụ đã được thực thi tương đương trong **JShell trên JDK 24**, với đúng các dòng output trên; các API được dùng có mặt trong Java 17. Trên môi trường mạng bị hạn chế hoặc nếu OS không nhận một tùy chọn, chương trình có thể ném exception thay vì in kết quả trên.

**Giải thích luồng chạy:**

1. **new ServerSocket()** chưa bind, **setReceiveBufferSize** trước **bind** đặt gợi ý buffer nhận cho các kết nối sẽ được accept.
2. **bind(loopback, 0)** yêu cầu OS chọn cổng tạm, không dùng mạng bên ngoài hoặc DNS.
3. Tạo **Socket** client chưa connect rồi bật SO_KEEPALIVE, TCP_NODELAY, tắt linger và đặt send/receive buffer. Mỗi setter chỉ điều chỉnh option socket; không thay đổi nội dung giao thức.
4. **client.connect(..., 3000)** thiết lập kết nối với connect timeout riêng. Sau đó **setSoTimeout(3000)** giới hạn thời gian chờ **read** (trên client); tương tự ở serverSide.
5. **listener.accept()** trả socket của một kết nối đã thiết lập. Đây là socket **khác** với listener.
6. Gửi chính xác **4 byte ASCII UTF-8**, dùng **DataInputStream.readFully(byte[4])** để nhận đủ 4 byte hoặc nhận lỗi EOF. Điều này tránh giả định một lần **read()** luôn lấy đủ dữ liệu. Trong protocol thực tế, cần length-prefix, delimiter hoặc message framing để xác định độ dài.
7. In trạng thái các option và kết quả ping/pong. Buffer được kiểm tra bằng **> 0** vì OS có thể điều chỉnh kích thước.
8. **try-with-resources** đóng các socket. Trong ví dụ, linger đã tắt; không thực hiện abortive close bằng **setSoLinger(true, 0)**.

**Lưu ý:** Việc ping/pong thành công chứng minh hai endpoint đã trao đổi 4 byte theo protocol tối giản ở loopback, **không** chứng minh thay đổi TCP_NODELAY hay buffer đã tăng hiệu suất. Muốn kiểm tra hiệu năng, cần benchmark có tải, theo dõi TCP metrics và so sánh nhiều lần chạy.

## 7. Với SocketChannel và StandardSocketOptions

Nếu dùng **java.nio.channels.SocketChannel**, option nằm trong **StandardSocketOptions**; đây là cách khác để cấu hình cùng nhóm tùy chọn trên Internet TCP socket:

~~~java
import java.net.StandardSocketOptions;
import java.nio.channels.SocketChannel;

try (SocketChannel channel = SocketChannel.open()) {
    channel.setOption(StandardSocketOptions.SO_KEEPALIVE, true);
    channel.setOption(StandardSocketOptions.TCP_NODELAY, true);
    channel.setOption(StandardSocketOptions.SO_SNDBUF, 16 * 1024);
    channel.setOption(StandardSocketOptions.SO_RCVBUF, 32 * 1024);
    channel.setOption(StandardSocketOptions.SO_LINGER, -1);
    // channel.connect(remoteAddress); // cần địa chỉ đích thật khi sử dụng
}
~~~

Đây là **snippet cấu hình**, không phải demo kết nối và trao đổi dữ liệu. **SO_LINGER** trong NIO là **Integer**: số âm tắt, **0** bật linger bằng 0 (có thể đóng cưỡng bức), số dương bật timeout theo giây. Chỉ dựa vào hành vi linger được định nghĩa cho **blocking mode**; với **non-blocking SocketChannel**, hành vi close khi linger bật không được xác định giống blocking mode.

**SocketChannel.supportedOptions()** và **Socket.supportedOptions()** giúp khám phá các option được nền tảng hỗ trợ; các tùy chọn mở rộng hoặc loại socket khác không nhất thiết hỗ trợ toàn bộ danh sách. Với **ServerSocketChannel**, hãy kiểm tra API của listening channel và đặt receive-buffer hint trước **bind** nếu yêu cầu TCP window lớn. NIO **Selector** và partial write/read vẫn cần framing và quản lý backpressure, bất kể cấu hình buffer.

## 8. Chọn cấu hình theo tình huống

| Tình huống | Hướng tiếp cận | Tránh kết luận vội |
| --- | --- | --- |
| Kết nối TCP idle lâu và có thể mất dấu peer | Cân nhắc **SO_KEEPALIVE**, xem OS timeout, thêm heartbeat ứng dụng nếu có SLA | Bật keepalive không tạo health-check mỗi 5 giây |
| RPC nhỏ cần latency thấp | Đo hiệu quả **TCP_NODELAY=true**, đồng thời sửa batching/flush | true không bảo đảm mỗi write được gửi tức thì |
| Gửi hàng loạt byte và ưu tiên throughput | Ghi theo block, profiling, cân nhắc buffer và OS autotuning | Không mặc định buffer càng lớn càng tốt |
| **close()** chậm hoặc thread dừng lâu | Kiểm tra **SO_LINGER**, còn byte chưa gửi, tải mạng và peer | SO_LINGER không phải timeout của read/connect |
| Peer báo **Connection reset** sau khi server đóng | Kiểm tra close cưỡng bức, **SO_LINGER=0**, unread data và middlebox | Không quy mọi RST cho một option duy nhất |
| Throughput kém trên mạng RTT lớn | Đo bandwidth-delay product, TCP window, BDP, congestion, SO_RCVBUF trước connect/bind | Buffer không vượt được giới hạn link hay CPU |
| **write()** block khi server đọc chậm | Đo send queue, advertised receive window, tốc độ ứng dụng nhận | Tăng send buffer chỉ có thể trì hoãn áp lực |
| Hàng nghìn connection đồng thời dùng nhiều RAM | Đo memory/connection, buffer defaults, giới hạn OS | Đừng cố đặt buffer lớn trên mọi socket |

Không có bộ tham số “chuẩn” cho mọi server. Cần biết protocol là tương tác thời gian thực, upload, streaming hay batch, số connection đồng thời, kích thước payload, RTT, loss, nhu cầu idle timeout và giới hạn memory.

## 9. Debug và quan sát đúng hiện tượng

Một cách chẩn đoán có hệ thống:

1. **Xác minh option được áp dụng lên socket nào.** Client Socket và Socket từ **ServerSocket.accept()** là **hai endpoint khác nhau**; setting ở client không tự đặt lại flag trên peer. Listener chỉ có những option phù hợp với server socket.
2. **In getter, không chỉ log setter.** **getKeepAlive()**, **getTcpNoDelay()**, **getSoLinger()**, **getSendBufferSize()**, **getReceiveBufferSize()** cho biết giá trị mà Java/OS báo sau khi áp dụng.
3. **Phân biệt ba loại chờ:** connect timeout, read timeout và đợi do send-buffer/backpressure hoặc linger khi close. Chúng có nguyên nhân và cách xử lý khác nhau.
4. **Kiểm tra thứ tự cấu hình** receive buffer trước connect/bind khi muốn window lớn; theo dõi giá trị thực của accepted Socket.
5. **Đo protocol end-to-end:** latency client gửi, server đọc đủ message, server xử lý, client nhận đủ response. TCP keepalive/Nagle/linger không thay thế log nghiệp vụ.
6. **Quan sát OS TCP state khi cần:** Linux **ss -tinm** và công cụ packet capture khi được phép; Windows có **netstat -ano** cùng công cụ chẩn đoán mạng phù hợp. Cách hiển thị queue/window cụ thể phụ thuộc OS và quyền truy cập.
7. **Benchmark từng thay đổi:** giữ nguyên payload, RTT giả lập hoặc môi trường đo, concurrency, CPU, p50/p95/p99 và throughput; thay một option mỗi lần để dễ xác định tác động.

### Các lỗi hiểu sai thường gặp

- **“SO_KEEPALIVE là keepalive HTTP hoặc WebSocket ping.”** Không. TCP probe khác hẳn thông điệp application.
- **“Bật SO_KEEPALIVE giúp phát hiện mất kết nối ngay.”** Không. Thời gian idle và số lần probe phụ thuộc OS.
- **“TCP_NODELAY=true nghĩa là không có bộ đệm.”** Không. TCP send buffer, Java BufferedWriter, TLS và các tầng khác vẫn tồn tại.
- **“TCP_NODELAY tự làm packet nhỏ nhanh hơn trong mọi trường hợp.”** Không. Hiệu quả phụ thuộc workload, congestion và delayed ACK; overhead có thể tăng.
- **“setSoLinger(true, 0) chờ đủ 0 giây rồi đóng sạch.”** Dễ sai: đó thường là **abortive close/RST**, có nguy cơ bỏ dữ liệu.
- **“SO_LINGER=5 bảo đảm peer xử lý hết request.”** Không; cùng lắm điều chỉnh khoảng chờ vận chuyển của close, không có application acknowledgment.
- **“setSendBufferSize(1_000_000) chắc chắn cấp 1 MB.”** Không; setter là hint, OS có thể thay đổi/giới hạn.
- **“Receive buffer lớn nghĩa là read() lấy nguyên một message.”** Không. TCP không có message boundary; code vẫn cần framing.
- **“setReceiveBufferSize sau accept luôn tương đương set trước bind.”** Không, nhất là yêu cầu TCP receive window lớn hơn 64 KiB.
- **“Socket.isConnected() trả true nghĩa là peer vẫn sống.”** Không. Trạng thái method không xác minh health của peer theo thời gian thực.

## 10. Bài tập tự kiểm tra

1. Một client dùng kết nối lâu dài nhưng không có request suốt 10 phút, peer biến mất. Vì sao **SO_KEEPALIVE=true** chưa bảo đảm phát hiện trong 10 giây? Cần gì khi SLA phát hiện là 10 giây?
2. Ứng dụng ghi 100 lần, mỗi lần 1 byte. Tại sao **TCP_NODELAY=true** vẫn không chứng minh tạo 100 TCP segment? Nếu dùng **BufferedOutputStream**, cần quan sát thêm thao tác nào?
3. Server bật **setSoLinger(true, 0)** rồi đóng khi chưa gửi hết response. Client có thể thấy gì, và vì sao việc dùng **close()** thay application response là sai?
4. Client gửi 2 MiB và **write()** block dù đã tăng **SO_SNDBUF**. Hãy nêu ba nguyên nhân liên quan đến peer/window/network và các metric nên đo.
5. Server cần receive window lớn hơn 64 KiB. Thứ tự khởi tạo **ServerSocket**, **setReceiveBufferSize**, **bind**, **accept** là gì? Vì sao phải kiểm tra accepted socket?
6. NIO SocketChannel non-blocking trả **write() = 0**. Có nên busy-loop liên tục và tăng SO_SNDBUF vô hạn không? Hãy giải thích readiness, backpressure và memory bounds.

**Tổng kết kiến thức:** **SO_KEEPALIVE** giải quyết tình huống **idle/liveness ở tầng TCP**, **TCP_NODELAY** tác động **Nagle và latency của write nhỏ**, **SO_LINGER** tác động **hành vi close khi còn byte chưa gửi**, còn **SO_SNDBUF/SO_RCVBUF** gợi ý **dung lượng bộ đệm kernel và flow control**. Không tùy chọn nào thay thế protocol framing, application acknowledgment, timeout hoặc kiểm thử hiệu năng thực tế.

**Nguồn API để tra cứu chính xác:** [Socket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html), [ServerSocket (Java SE 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html), [StandardSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardSocketOptions.html), [SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) và [ExtendedSocketOptions](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.net/jdk/net/ExtendedSocketOptions.html).