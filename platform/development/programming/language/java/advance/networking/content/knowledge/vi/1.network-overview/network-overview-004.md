# Đường đi dữ liệu: ứng dụng → Java API → hệ điều hành → mạng → tiến trình đích

**Chủ đề:** Java Advance - networking · **Nhóm:** Bức tranh mạng

Một lời gọi **Socket.getOutputStream().write(...)** trong Java trông đơn giản, nhưng dữ liệu đi qua nhiều ranh giới trước khi ứng dụng bên kia xử lý được: biểu diễn dữ liệu của ứng dụng, Java API/JVM, socket của hệ điều hành, tầng truyền tải TCP/UDP, định tuyến IP, giao diện mạng hoặc loopback, rồi các lớp tương ứng phía nhận. Hiểu luồng này giúp lý giải vì sao “write thành công” chưa có nghĩa là server đã xử lý, một lần write không tương ứng một lần read, và các lỗi mạng xuất hiện ở tầng nào.

## 1. Mô hình đầu-cuối

~~~text
CLIENT (tiến trình gửi)                                    SERVER (tiến trình nhận)
Dữ liệu nghiệp vụ                                            Xử lý nghiệp vụ
     ↓ encode, framing                                            ↑ decode, parse
Java: OutputStream / SocketChannel                        Java: InputStream / SocketChannel
     ↓ JVM / socket provider                                      ↑ JVM / socket provider
OS: socket, send buffer, TCP/UDP, IP                       OS: IP, TCP/UDP, receive buffer, socket
     ↓                                                                  ↑
  Loopback hoặc NIC A → mạng, router/NAT/proxy nếu có → NIC B
~~~

Đây là **mô hình khái niệm**, không phải quy tắc mỗi method Java tạo một system call hay một IP packet. JVM có thể đệm dữ liệu; TCP có thể gom, chia và truyền lại; router, firewall, NAT hoặc proxy có thể thêm các chặng trung gian. Với địa chỉ loopback trên cùng host, dữ liệu đi qua network stack cục bộ, không qua card mạng vật lý.

Cần phân biệt bốn mốc:

1. **Ứng dụng tạo dữ liệu** như String, JSON hay byte array.
2. **Java ghi thành công**: dữ liệu được API/stream nhận để chuyển tiếp; chưa chứng minh máy đích đã nhận.
3. **TCP phía nhận xác nhận byte**: ACK ở tầng vận chuyển, không chứng minh ứng dụng đích đã đọc hoặc xử lý.
4. **Ứng dụng đích xác nhận nghiệp vụ**: ví dụ response hợp lệ, mã kết quả hoặc transaction ID theo protocol.

## 2. Biến dữ liệu ứng dụng thành byte có ý nghĩa

Socket truyền **byte**. Khi gửi text, code cần chọn bảng mã (thường UTF-8); khi gửi object, cần serialization được hai đầu thống nhất. Ngoài encode/decode, ứng dụng còn phải chọn **framing** để nhận ra ranh giới một thông điệp và định nghĩa semantic request/response.

| Cách đóng khung | Quy ước | Điểm cần giữ |
| --- | --- | --- |
| Delimiter | Một dòng kết thúc bằng newline | Payload chứa delimiter phải được escape hoặc cấm; readLine chờ newline/EOF |
| Length-prefix | Ghi độ dài rồi tới đúng số byte | Validate độ dài, giới hạn payload, đọc đủ byte bằng vòng lặp/readFully |
| Protocol chuẩn | HTTP headers/body, WebSocket frame, v.v. | Áp dụng quy tắc framing của protocol, không suy luận theo TCP packet |

**TCP là luồng byte có thứ tự, không phải hàng đợi message.** Client có thể gọi write cho **ABC** rồi **DEF**; phía server có thể đọc **ABCDEF** trong một lần, hoặc **A**, **BCDE**, **F** trong nhiều lần. Java **InputStream.read(...)** có thể trả ít byte hơn số byte yêu cầu; trả **-1** khi luồng kết thúc và dữ liệu còn đệm đã được đọc hết. Với non-blocking **SocketChannel**, read/write còn có thể xử lý một phần và trả về ngay: caller phải theo dõi vị trí ByteBuffer.

Một số câu hỏi phải giải quyết trước khi gửi: ai xác định độ dài thông điệp, tối đa bao nhiêu byte, charset là gì, dữ liệu sai được xử lý thế nào, khi nào phải trả response, và request có an toàn khi retry không?

## 3. Đường đi TCP theo thứ tự thời gian

### Bước 0: Tìm đích (hostname, IP, port)

Ứng dụng thường bắt đầu với **hostname + port**. Nếu cần, resolver của JVM/hệ điều hành phân giải hostname thành một hoặc nhiều IP (IPv4/IPv6), có thể thông qua DNS hoặc cache; không phải mỗi lần connect đều tạo một truy vấn DNS. IP giúp xác định đích ở tầng mạng, port phân biệt endpoint truyền tải trong host.

Một TCP connection thường được phân biệt bởi bộ **(source IP, source port, destination IP, destination port)** trong ngữ cảnh protocol và network namespace. Hệ điều hành thường cấp **ephemeral source port** cho client. IP đích của một TCP hop có thể là load balancer hoặc proxy, không nhất thiết là tiến trình nghiệp vụ cuối cùng.

### Bước 1: Server bind, listen, accept

Trên Java server, **ServerSocket** bind vào địa chỉ/port rồi listen. Lời gọi **accept()** chờ và trả một **Socket mới** đại diện cho một kết nối đã được chấp nhận. ServerSocket ban đầu vẫn lắng nghe những kết nối tiếp theo. Hệ điều hành quản lý TCP state, hàng đợi kết nối và giới hạn tài nguyên; **accept() trả về không có nghĩa toàn bộ request đã đến**.

### Bước 2: Client kết nối

Client gọi **Socket.connect(...)** hoặc API cấp cao. Trong TCP thông dụng, OS thực hiện bắt tay **SYN → SYN-ACK → ACK**; code Java không tự tạo các segment này. Việc connect có thể thất bại trước khi có payload ứng dụng: hostname sai, không có route, bị firewall từ chối, server không listen hoặc timeout. Cần phân biệt lỗi resolve với lỗi TCP connect.

### Bước 3: Java viết xuống socket

Ứng dụng encode dữ liệu rồi gọi **OutputStream.write(...)**, **SocketChannel.write(...)** hoặc API tương ứng. Nếu có **BufferedWriter**, byte/character có thể còn ở bộ đệm Java cho tới khi gọi **flush()** hoặc đủ điều kiện ghi xuống lớp tiếp theo.

**flush() chỉ đẩy dữ liệu đang đệm theo contract của writer/stream; không chứng minh byte đã qua mạng hoặc được server xử lý.** Một lần write có thể block khi send buffer đầy hoặc đối tác chậm đọc. Với NIO non-blocking, một lần write có thể chấp nhận ít byte hơn phần còn lại trong ByteBuffer nên phải ghi tiếp khi channel sẵn sàng.

### Bước 4: OS và TCP vận chuyển luồng byte

OS quản lý socket send buffer, số thứ tự byte TCP, cửa sổ nhận, congestion control, segmentation và retransmission khi cần. Phía nhận TCP kiểm tra và tái lắp thứ tự luồng byte, xử lý segment trùng/lệch thứ tự trước khi giao byte tới receive buffer. Số TCP segment và thời điểm packet rời máy **không suy ra được từ số lần Java write**.

**TCP ACK không tương đương ứng dụng đã xử lý request.** Nó xác nhận ở tầng TCP; server có thể còn chưa gọi read, chưa parse đủ message hoặc xử lý nghiệp vụ thất bại. Muốn biết request thành công, phải có xác nhận ở tầng ứng dụng.

### Bước 5: IP và tầng liên kết chuyển dữ liệu

TCP segment được đóng vào IP packet; OS chọn route/interface theo bảng định tuyến. Trên Ethernet/Wi-Fi, IP packet đi qua frame tầng liên kết; tìm địa chỉ lân cận có thể dùng ARP (IPv4) hoặc Neighbor Discovery (IPv6). Router chuyển tiếp, NAT có thể thay đổi địa chỉ/port; packet có thể đi qua nhiều hop hoặc đường khác nhau. Firewall có thể chặn kết nối theo policy. Với loopback, không cần NIC vật lý hay router ngoài host.

### Bước 6: OS máy nhận và Java API giao byte

TCP/IP stack phía server xác định socket phù hợp, xử lý segment và đặt byte hợp lệ vào receive buffer. **InputStream.read(...)** lấy lượng byte khả dụng; một read không nhất thiết khớp với write bên gửi. Ứng dụng phải đọc **đủ một frame**, decode, validate, rồi dispatch vào logic nghiệp vụ. Response quay về theo chiều ngược lại qua các lớp tương tự.

### Bước 7: Đóng kết nối

Đóng TCP bình thường sử dụng cơ chế **FIN** và trạng thái đóng theo từng chiều; sau khi byte đệm đã được đọc hết, phía nhận có thể thấy **read() == -1**. Đóng cưỡng bức hoặc lỗi có thể gây **RST**, **SocketException** hay lỗi khác. Đóng socket là thao tác tài nguyên và transport; nó không tự bảo đảm transaction nghiệp vụ đã commit.

## 4. Các Java API nằm ở khâu nào?

| Java API | Vai trò | Điều không thể ngầm suy ra |
| --- | --- | --- |
| **InetAddress**, **InetSocketAddress** | Địa chỉ IP/hostname và cặp địa chỉ-cổng | Không chứng minh đích sẵn sàng hoặc protocol đúng |
| **Socket**, **ServerSocket** | TCP connect, bind/listen/accept, stream I/O | Không tự có message boundary |
| **InputStream**, **OutputStream** | Đọc/ghi byte | Không tự biết UTF-8, JSON, HTTP |
| **SocketChannel**, **ServerSocketChannel**, **Selector** | Channel I/O, multiplexing và non-blocking | Vẫn phải quản lý partial I/O, framing và trạng thái |
| **DatagramSocket**, **DatagramPacket**, **DatagramChannel** | Datagram UDP | Không có bảo đảm delivery/order/retry mặc định |
| **SSLSocket**, **SSLContext** | TLS trên transport phù hợp | TCP kết nối được chưa chắc TLS handshake thành công |
| **java.net.http.HttpClient** | Client HTTP mức cao, quản lý protocol/kết nối | Vẫn có DNS, kết nối, timeout, HTTP status và lỗi server |

Việc JDK/JVM đi từ Java API xuống OS có thể qua native code, system call, socket provider và OS abstraction tùy platform/implementation; không có quy tắc cố định “một method = một syscall = một packet”.

## 5. Ví dụ tự chạy với Java 17+: TCP loopback

Chạy server và client trong **cùng một tiến trình Java**, nhưng chúng kết nối qua **TCP loopback** thật của host. Server nhận một dòng UTF-8 rồi trả chuỗi **ACK:** cộng nội dung. Chữ **ACK:** trong demo là phản hồi của ứng dụng, **khác với TCP ACK**.

Tạo tệp **NetworkPathDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.EOFException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class NetworkPathDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 50, loopback)) {
            listener.setSoTimeout(5_000);
            CompletableFuture<String> receivedByServer = new CompletableFuture<>();

            Thread server = new Thread(() -> {
                try (Socket accepted = listener.accept()) {
                    accepted.setSoTimeout(5_000);
                    try (BufferedReader input = new BufferedReader(
                             new InputStreamReader(accepted.getInputStream(), StandardCharsets.UTF_8));
                         BufferedWriter output = new BufferedWriter(
                             new OutputStreamWriter(accepted.getOutputStream(), StandardCharsets.UTF_8))) {
                        String line = input.readLine();
                        if (line == null) {
                            throw new EOFException("Client closed before sending a line");
                        }
                        output.write("ACK:" + line);
                        output.newLine();
                        output.flush();
                        receivedByServer.complete(line);
                    }
                } catch (Exception error) {
                    receivedByServer.completeExceptionally(error);
                }
            }, "loopback-server");
            server.start();

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, listener.getLocalPort()), 5_000);
                client.setSoTimeout(5_000);
                try (BufferedReader input = new BufferedReader(
                         new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8));
                     BufferedWriter output = new BufferedWriter(
                         new OutputStreamWriter(client.getOutputStream(), StandardCharsets.UTF_8))) {
                    output.write("xin chao");
                    output.newLine();
                    output.flush();
                    System.out.println("Client received: " + input.readLine());
                }
            }
            System.out.println("Server received: " + receivedByServer.get(5, TimeUnit.SECONDS));
            server.join(5_000);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 NetworkPathDemo.java
java NetworkPathDemo
~~~

**Kết quả stdout của lần chạy thành công:**

~~~text
Client received: ACK:xin chao
Server received: xin chao
~~~

Ví dụ đã được **biên dịch và chạy trên JDK 21**, sử dụng các API có trong Java 17. Chỉ thread main in stdout, sau khi đã nhận response nên hai dòng có thứ tự xác định. Nếu môi trường không cho phép tạo loopback socket, lệnh có thể thất bại vì cấu hình mạng hay quyền hạn.

Theo dõi các điểm ranh giới trong code:

1. **ServerSocket(0, 50, loopback)** bind lên loopback; **0** yêu cầu OS cấp port khả dụng, **getLocalPort()** trả port thực tế. Không cần DNS hay router ngoài.
2. **listener.accept()** chờ TCP connection; **client.connect(...)** thiết lập kết nối với connect timeout 5 giây.
3. **output.write("xin chao")**, **newLine()**, **flush()** tạo một *dòng* văn bản có delimiter. Server **readLine()** lấy một dòng và giải mã UTF-8, không phụ thuộc packet boundary.
4. Server viết **ACK:xin chao** và flush; client **readLine()** lấy dòng response. **CompletableFuture** chuyển nội dung server đọc về main cho dòng in thứ hai.
5. **try-with-resources** đóng socket và listener. **setSoTimeout(5_000)** giới hạn chờ read/accept; timeout của connect được cài riêng trong **connect(..., 5_000)**.

Ví dụ cố ý tối giản, phù hợp một dòng văn bản. Với binary hoặc request dài, dùng length-prefix/protocol chuẩn, giới hạn size và kiểm soát timeout, authentication, retry/idempotency cùng tài nguyên. Đừng dùng việc đóng connection làm delimiter trừ khi đó là hợp đồng protocol rõ ràng.

## 6. Điểm thay đổi khi kết nối sang máy thật

~~~text
Process A → Java API → socket send buffer → TCP/IP A → NIC A
            → switch/router/NAT/proxy nếu có → NIC B
            → TCP/IP B → socket receive buffer → Java API → Process B
                     ← response đi theo quá trình ngược lại
~~~

Server phải bind vào interface mà client truy cập được; firewall/network ACL phải cho phép cổng tương ứng. Bind **127.0.0.1** hoặc **::1** chỉ nhận kết nối loopback từ **chính host**; client ở máy khác không thể dùng địa chỉ loopback đó để kết nối server. Bind wildcard có thể mở truy cập rộng hơn, cần cấu hình bảo mật phù hợp.

Nếu có reverse proxy/load balancer/service mesh, TCP socket ở một hop có thể kết thúc tại proxy. Proxy có thể tạo **kết nối khác** tới backend. Bởi vậy cần phân biệt địa chỉ/port ở từng hop và hành trình request nghiệp vụ cuối cùng; không giả định cả chuỗi hệ thống chia sẻ một kết nối TCP.

## 7. So sánh các giao thức trên đường đi

**TCP** giữ thứ tự luồng byte, kiểm soát flow/congestion và retransmit trong phạm vi kết nối. Nó không định nghĩa request/response, framing hoặc thành công nghiệp vụ. Connection có thể hỏng sau khi server đã xử lý một phần hoặc toàn bộ request; retry giao dịch cần xem xét tính idempotent và định danh yêu cầu.

**UDP** gửi datagram có ranh giới ở mức API, không có TCP handshake và không tự đảm bảo dữ liệu đến nơi, đúng thứ tự, không trùng lặp. Kích thước packet và MTU/fragmentation là mối quan tâm thực tế. Không coi một datagram lớn là chắc chắn gửi thành công tới application.

**HTTP** là protocol ứng dụng: method, URL, headers, body, status và framing. HTTP/1.1 thường chạy trên TCP; HTTP/2 multiplex các stream trên một connection; HTTP/3 dùng QUIC trên UDP. **HttpClient** ẩn nhiều thao tác socket, nhưng response HTTP 4xx/5xx vẫn là kết quả ở tầng ứng dụng và không tự đồng nghĩa với lỗi truyền tải.

**TLS** thường nằm giữa plaintext ứng dụng và transport, thực hiện handshake, mã hóa và xác thực theo cấu hình. Với HTTPS/TLS qua TCP, tầng IP vận chuyển byte đã mã hóa; TCP connect thành công **không** đảm bảo TLS handshake/certificate validation thành công. Nếu TLS kết thúc tại proxy, phía sau proxy là một kết nối/ranh giới bảo mật riêng.

## 8. Chẩn đoán theo ranh giới

| Triệu chứng | Ưu tiên kiểm tra |
| --- | --- |
| **UnknownHostException** | Hostname, resolver, DNS/caching, cấu hình máy |
| **ConnectException / connection refused** | Đích có listen đúng IP:port? bind interface? policy/firewall từ chối? |
| **SocketTimeoutException** | Phân biệt timeout connect, read và accept; kiểm tra server chậm phản hồi, network policy, packet loss |
| **read() trả -1 trước đủ frame** | Peer đóng chiều gửi; protocol có đang nhận thiếu dữ liệu không? |
| **Connection reset / SocketException** | Peer đóng bất thường, proxy/firewall, shutdown giữa chừng, lỗi protocol |
| **SSLHandshakeException** | Certificate, truststore, hostname verification, phiên bản TLS, proxy TLS |
| **HTTP 4xx/5xx** | Server đã trả status ứng dụng; đọc body, request ID và server log |

Một timeout không đủ để kết luận packet mất ở đâu. Hãy đối chiếu log thời điểm **resolve → connect → ghi/flush → server đọc đủ request → server xử lý → client đọc đủ response** bằng correlation ID. Khi được phép, dùng **tcpdump/Wireshark** để quan sát gói; phải chọn đúng interface (kể cả loopback). **ss -tn** trên Linux hay **netstat -ano** trên Windows có thể quan sát connection đang sống; ví dụ loopback ở trên có thể kết thúc quá nhanh để lệnh liệt kê bắt gặp.

Lưu ý trong đo thời gian: “write/flush xong” không đo chính xác thời gian byte đến server vì bộ đệm và TCP scheduling nằm bên dưới. Mốc TCP ACK cũng không đo được thời gian xử lý nghiệp vụ; chỉ một application response có quy ước rõ mới phản ánh kết quả phía server.

## 9. Các hiểu nhầm cần tránh

- **Một write bằng một read hoặc một packet.** Sai với TCP stream. Thiết kế framing và đọc đủ message.
- **flush() xác nhận server đã xử lý.** Không. Nó chủ yếu xử lý bộ đệm phía gọi; cần application response.
- **TCP ACK là phản hồi nghiệp vụ.** Không. Hai loại xác nhận ở hai tầng khác nhau.
- **Đọc cho tới EOF là cách kết thúc request phổ quát.** Không với connection tái sử dụng; dễ chờ vô hạn/deadlock nếu protocol không dùng EOF làm delimiter.
- **Connect thành công là endpoint hoạt động đúng.** Chưa thể suy ra protocol, authentication hay business logic.
- **IP:port đích luôn chỉ tiến trình backend.** Có thể là load balancer/proxy/NAT endpoint.
- **TCP bảo đảm mọi giao dịch ứng dụng luôn thành công.** TCP chỉ quản lý luồng byte trong kết nối. Khi lỗi giữa chừng, có thể không biết request đã commit hay chưa; retry phải xử lý idempotency.
- **NIO tự giải quyết partial I/O, framing và timeout.** Không; NIO đổi mô hình I/O và readiness, các trách nhiệm đó vẫn tồn tại.

## 10. Checklist khi phân tích một request mạng Java

1. **Ứng dụng gửi dữ liệu gì?** Charset/serialization, framing, request ID, response contract và size limit là gì?
2. **Java API nào được dùng?** Socket, NIO, HTTP client hay UDP? Buffer, flush, partial read/write và timeout ở đâu?
3. **OS giữ trạng thái gì?** Bind/listen/connect, socket buffers, TCP state, flow control và backpressure?
4. **Network path thực?** Loopback hay NIC; DNS, IP/port, routing, NAT, proxy, firewall, TLS termination nào?
5. **Phía đích đọc thế nào?** Socket được chọn ra sao, đã nhận đủ frame chưa, decode/validate ra sao, nghiệp vụ xử lý tới đâu?
6. **Có chứng cứ hoàn tất không?** Chỉ write thành công, TCP ACK, hay phản hồi ứng dụng đúng với request ID?
7. **Lỗi ở đâu?** Resolve, connect, TLS handshake, write, read, framing, authorization hay business logic?

**Kết luận:** Java networking API cung cấp cách trao đổi byte, OS/TCP/IP chịu trách nhiệm vận chuyển và định tuyến, còn protocol ứng dụng xác định ý nghĩa của byte và điều kiện thành công. Hiểu rõ ranh giới giữa các lớp là nền tảng để viết code mạng đúng, dự đoán backpressure và debug timeout hoặc dữ liệu thiếu một cách có hệ thống.