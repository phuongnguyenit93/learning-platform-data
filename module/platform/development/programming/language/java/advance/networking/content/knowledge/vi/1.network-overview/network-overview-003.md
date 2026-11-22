# Phân biệt địa chỉ IP, cổng, điểm cuối, kết nối và thông điệp

## Mục tiêu bài học

Khi đọc một URL, nhìn log kết nối hay viết chương trình socket bằng Java, cần xác định được **đang nói về địa chỉ của máy, địa chỉ của dịch vụ, một phiên giao tiếp hay một đơn vị dữ liệu**. Năm khái niệm liên quan chặt chẽ nhưng không thể thay thế cho nhau:

| Khái niệm | Trả lời câu hỏi | Ví dụ | Vai trò chính |
|---|---|---|---|
| **Địa chỉ IP (IP address)** | Gói tin IP cần đi tới địa chỉ mạng nào? | `192.0.2.20`, `2001:db8::20` | Định địa chỉ và định tuyến ở tầng mạng |
| **Cổng (port)** | Bên trong máy, giao thức vận chuyển giao dữ liệu cho điểm nhận nào? | TCP `443`, UDP `53` | Phân biệt các điểm nhận/gửi thuộc TCP hoặc UDP |
| **Điểm cuối (endpoint)** | Đầu giao tiếp cụ thể nằm ở đâu, theo giao thức/ngữ cảnh nào? | TCP `192.0.2.20:443`; HTTP `GET /orders` | Mô tả nơi một bên giao tiếp hoặc một API được truy cập |
| **Kết nối (connection)** | Hai bên đang duy trì quan hệ truyền dữ liệu nào? | Một kết nối TCP giữa cổng động của client và `:443` | Trạng thái giao tiếp tồn tại theo thời gian |
| **Thông điệp (message)** | Ứng dụng muốn trao đổi đơn vị thông tin nào? | HTTP request, một dòng `PING`, một UDP datagram | Nội dung có ranh giới/ý nghĩa do giao thức quy định |

Đây là mô hình nhiều lớp: **IP** đưa gói tin tới địa chỉ mạng; **TCP/UDP và port** đưa dữ liệu tới socket thích hợp; **giao thức ứng dụng** định nghĩa cấu trúc, ý nghĩa và ranh giới của message. Endpoint và connection phải luôn được hiểu trong ngữ cảnh đang bàn.

## 1. Địa chỉ IP: nơi dữ liệu được định tuyến tới

Một địa chỉ IP là địa chỉ logic dùng để truyền gói tin trên mạng IP. Thiết bị có thể có nhiều giao diện mạng và nhiều địa chỉ IP; một địa chỉ cũng có thể được dùng bởi NAT, load balancer hoặc cơ chế định tuyến đặc biệt. Vì vậy, nói "mỗi IP chính là một máy" là quá đơn giản.

- **IPv4** dài 32 bit, thường viết bốn số thập phân: `192.0.2.20`. **IPv6** dài 128 bit, thường viết dạng thập lục phân: `2001:db8::20`. Các dải `192.0.2.0/24`, `198.51.100.0/24` và `2001:db8::/32` trong bài được dùng làm ví dụ tài liệu, không đại diện server thực.
- `127.0.0.1` và `::1` là địa chỉ **loopback**: traffic quay lại chính thiết bị. `localhost` là *tên* thường được phân giải ra địa chỉ loopback; tên đó không phải bản thân một địa chỉ IP.
- `0.0.0.0` hoặc `::` thường dùng khi **bind** server để lắng nghe trên mọi địa chỉ phù hợp của máy (*wildcard address*). Chúng không phải địa chỉ đích công khai để client tùy ý kết nối.
- Tên miền như `api.example.com` được phân giải qua DNS thành một hoặc nhiều địa chỉ IP. Một tên có thể trả về nhiều IP; nhiều tên có thể cùng dùng một IP. DNS không xác định cổng hay HTTP path.
- Địa chỉ private, địa chỉ public, NAT và proxy tác động tới cách nhìn đường đi mạng; một IP nội bộ quan sát từ client có thể khác IP mà server nhìn thấy.

**Ranh giới:** biết IP vẫn chưa biết dịch vụ nào, cổng nào hay thông điệp nào sẽ được xử lý. Lệnh `ping` thường kiểm tra trao đổi ICMP/khả năng tới đích, không khẳng định cổng TCP của ứng dụng đang mở.

## 2. Cổng: số định danh ở tầng vận chuyển

TCP và UDP đều có trường port **16 bit**, giá trị từ **0 đến 65535**. Hai giao thức có không gian port riêng: TCP port 53 và UDP port 53 là hai điểm nhận khác nhau.

- Server thường **bind/listen** tại một port được biết trước, chẳng hạn TCP 443 (thường dành cho HTTPS) hoặc TCP 9090 của ứng dụng minh họa. Port chỉ là quy ước, **không tự đảm bảo** ứng dụng đang nói TLS/HTTP.
- Client thường được hệ điều hành chọn một **ephemeral port** (cổng tạm thời), ví dụ `53142`, khi bắt đầu giao tiếp. Khoảng ephemeral cụ thể phụ thuộc hệ điều hành/cấu hình, không nên giả định một dải cố định.
- Port `0` khi *bind* socket thường là yêu cầu hệ điều hành chọn một port khả dụng; nó không phải cổng dịch vụ đích dùng trong ví dụ kết nối bình thường.
- Một port chỉ có nghĩa khi gắn với **giao thức vận chuyển, địa chỉ bind và ngữ cảnh mạng**. Không thể suy ra duy nhất process chỉ từ con số `443`; NAT, container, network namespace, proxy và cơ chế chia sẻ socket có thể làm bức tranh phức tạp hơn.

Ví dụ, máy có IP `198.51.100.20` có thể đồng thời nhận TCP `443` (web) và TCP `22` (SSH). Cùng một IP, **dịch vụ khác nhau vì port/giao thức khác nhau**; port không thay IP để định tuyến.

## 3. Endpoint: phải nói rõ tầng và ngữ cảnh

Từ **endpoint** có nhiều cách dùng hợp lệ:

1. **Socket/transport endpoint:** thường là cặp **địa chỉ IP + port**, đi cùng TCP hay UDP. Ví dụ `TCP 198.51.100.20:443`; với IPv6 dùng ngoặc vuông để tránh nhầm dấu hai chấm: `[2001:db8::20]:443`.
2. **Application/API endpoint:** địa chỉ tài nguyên hay thao tác mà ứng dụng cung cấp. Chẳng hạn `GET https://api.example.com:443/v1/orders` chỉ rõ scheme HTTPS, hostname, port, method và path. Phần `/v1/orders` **không phải TCP port** và **không phải thành phần của TCP socket endpoint**.
3. **Java object biểu diễn đích:** `InetSocketAddress` biểu diễn hostname/IP cùng port; `URI` chứa thêm scheme/path/query; `Socket` là đối tượng socket gắn với hoạt động giao tiếp, không đồng nghĩa với một URI.

Một URL có thể tham chiếu tới một **API endpoint** dù chưa có kết nối mạng nào được mở. Nhiều URL/path cũng có thể được xử lý trên **cùng một TCP connection** khi ứng dụng tái sử dụng kết nối (ví dụ HTTP keep-alive). Do đó "endpoint" không đồng nghĩa "connection".

Ví dụ phân rã URL minh họa:

```text
https://api.example.com:443/v1/orders?status=open
  │       │              │   │         │
  │       hostname       │   path      query
  │                      port
  scheme = https
```

Hostname cần được phân giải thành IP để thực hiện kết nối trong mô hình thông thường. Với HTTPS qua TCP, cổng mặc định là 443 nếu không ghi rõ; **HTTP path/query chỉ xuất hiện ở tầng ứng dụng**. Cùng địa chỉ IP:port có thể phục vụ nhiều hostname nhờ thông tin tên host của TLS/HTTP, nên IP:port không nhất thiết xác định duy nhất một trang web.

## 4. Connection: một quan hệ giao tiếp có trạng thái

Với **TCP**, connection là quan hệ được thiết lập giữa hai đầu qua quá trình bắt tay (thường SYN → SYN-ACK → ACK), sau đó cung cấp luồng byte **đúng thứ tự** và cơ chế truyền lại/kiểm soát luồng. Mỗi phía có địa chỉ local và remote.

Một kết nối TCP thông thường được phân biệt trong ngữ cảnh mạng bằng bộ bốn:

```text
(local IP, local TCP port, remote IP, remote TCP port)

Ví dụ:
client 192.0.2.10:53142  ──TCP──>  server 198.51.100.20:443
```

Giao thức TCP và network namespace/ngữ cảnh mạng cũng quan trọng khi nhận diện kết nối. Client khác có thể cùng gọi `198.51.100.20:443`; server phân biệt các connection dựa trên bộ thông tin hai đầu, không tạo "một port server mới" cho mỗi client. **Listening socket** chờ kết nối tới một địa chỉ/port; sau `accept()`, **connected socket** đại diện một kết nối đã được chấp nhận. Nhiều connected socket trên server có thể cùng local port `443` nhưng khác remote endpoint.

**Connection có vòng đời:** thiết lập → gửi/nhận nhiều lần → đóng (hoặc lỗi/timeout). Nó không phải một message; một connection có thể mang không, một hoặc rất nhiều message. Đường đi qua NAT/load balancer/proxy có thể thay đổi endpoint mà mỗi phía quan sát, và proxy có thể tạo **hai kết nối TCP riêng** cho một request từ client đến backend.

Với **UDP**, tầng UDP **không có TCP-style handshake hay reliable byte stream**. Mỗi datagram mang địa chỉ đích và port, có thể gửi/nhận mà không thiết lập connection. Phương thức `DatagramSocket.connect(...)` của Java chỉ cấu hình peer mặc định và lọc nguồn gửi đến ở mức socket; **không biến UDP thành TCP** và không tạo một phiên bắt tay UDP. Một số giao thức cao hơn chạy trên UDP (như QUIC) tự xây dựng khái niệm connection riêng: luôn phân biệt *connection của giao thức nào*.

## 5. Message: đơn vị có ý nghĩa đối với ứng dụng

Ứng dụng trao đổi **message**, ví dụ "đăng nhập", "GET /orders", JSON response, "PING". Message có thể có header, payload và ranh giới theo giao thức. Đừng đồng nhất message với **IP packet**, **TCP segment** hay **lần gọi `read()`**: đó là các đơn vị khác nhau.

**TCP là luồng byte, không giữ ranh giới của mỗi lần `write()`.** Client ghi `HELLO` rồi ghi `WORLD` có thể khiến phía nhận đọc thành `HELLOWORLD` trong một lần đọc, hoặc `HE` rồi `LLOWORLD` trong nhiều lần. TCP đảm bảo thứ tự byte (khi kết nối truyền thành công), **không đảm bảo một `read()` ứng với một `write()` hay một message**.

Muốn chuyển byte stream thành message, giao thức ứng dụng cần cách **framing**, chẳng hạn:

| Cách định khung | Cách nhận biết ranh giới | Lưu ý |
|---|---|---|
| Kết thúc bằng ký tự phân cách | Mỗi message kết thúc bằng `\n` (hoặc `\r\n`) | Payload phải có quy tắc escaping nếu được chứa ký tự phân cách |
| Tiền tố độ dài | Ví dụ 4 byte đầu chỉ độ dài payload; đọc tiếp đủ số byte đó | Phải quy định byte order, giới hạn độ dài, xử lý đọc từng phần |
| Cấu trúc giao thức chuẩn | HTTP/1.1 dùng quy tắc start-line, headers và xác định phần body; HTTP/2 có frame/stream | Dùng thư viện giao thức, không tự tách message theo kích thước TCP segment |
| Kết thúc luồng | Một message duy nhất kéo dài tới EOF | Không phù hợp để gửi nhiều message liên tiếp trên cùng connection |

**UDP** giữ ranh giới datagram ở API nhận: mỗi lần `receive()` nhận **một datagram** (có thể bị cắt nếu buffer quá nhỏ). Tuy vậy, UDP **không đảm bảo** datagram sẽ tới, không bị lặp hay tới đúng thứ tự. Một message lớn có thể phải chia nhỏ ở tầng ứng dụng; không nên dựa vào phân mảnh IP làm cơ chế truyền message lớn đáng tin cậy.

Ví dụ: HTTPS qua TCP có thể mang nhiều HTTP request/response trên một connection; TLS có record riêng, nhưng ranh giới TLS record cũng **không đồng nhất** với ranh giới HTTP message. Ở HTTP/2, nhiều stream request có thể được multiplex trên một connection. Ở mọi trường hợp, một **message ứng dụng** cần được giải mã theo giao thức ứng dụng.

## 6. Đi qua một tình huống: từ URL đến response

Giả sử client gọi `https://api.example.com/v1/orders`; tên miền và IP sau đây chỉ mang tính minh họa.

```text
Ứng dụng client
   │  (1) Xác định HTTPS + hostname + path; tra DNS → 198.51.100.20
   │  (2) TCP: 192.0.2.10:53142 ───────────→ 198.51.100.20:443
   │  (3) TLS handshake và xác thực server
   │  (4) Gửi HTTP request cho /v1/orders trên kết nối bảo mật
   │  (5) Nhận HTTP response, giải mã thành message ứng dụng
   └  (6) Tái sử dụng hoặc đóng connection tùy giao thức/chính sách
```

Điểm cần phân biệt:

- `198.51.100.20` là **IP đích** trong tình huống giả định; `443` là **TCP port đích**.
- `192.0.2.10:53142` và `198.51.100.20:443` là hai **transport endpoint** quan sát ở phía client; một cặp hai đầu được dùng để nhận diện **connection TCP**.
- `GET /v1/orders` là thao tác tới **HTTP API endpoint**; request và response là **HTTP messages**.
- Một HTTP request có thể được gửi qua connection đã tồn tại; không nhất thiết mỗi request mở TCP connection mới. Với HTTPS chạy trên HTTP/3, giao thức nền là QUIC/UDP nên chi tiết tầng vận chuyển khác ví dụ TCP ở trên.

## 7. Java 17+: thực hành TCP và framing theo dòng

Ví dụ dưới đây dùng loopback để chạy hoàn toàn trên một máy. Server lắng nghe TCP port 9090; client tự được cấp local port tạm thời. Giao thức tự định nghĩa mỗi message là **một dòng UTF-8 kết thúc bằng newline**. Hai tệp độc lập được biên dịch bằng JDK 17 trở lên.

**Tệp `TcpLineServer.java`**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpLineServer {
    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090));
            System.out.println("Server ready");

            try (Socket socket = server.accept();
                 BufferedReader reader = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedWriter writer = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                String message = reader.readLine();
                System.out.println("Server received: " + message);
                writer.write("ACK: " + message);
                writer.newLine();
                writer.flush();
            }
        }
    }
}
```

**Tệp `TcpLineClient.java`**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpLineClient {
    public static void main(String[] args) throws Exception {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090), 3000);
            socket.setSoTimeout(3000);

            try (BufferedReader reader = new BufferedReader(
                         new InputStreamReader(socket.getInputStream(),
                                 StandardCharsets.UTF_8));
                 BufferedWriter writer = new BufferedWriter(
                         new OutputStreamWriter(socket.getOutputStream(),
                                 StandardCharsets.UTF_8))) {
                writer.write("PING");
                writer.newLine();
                writer.flush();
                System.out.println("Client received: " + reader.readLine());
            }
        }
    }
}
```

**Biên dịch và chạy:**

```bash
javac -encoding UTF-8 TcpLineServer.java TcpLineClient.java
java TcpLineServer
```

Giữ server chạy, mở **terminal thứ hai** trong cùng thư mục:

```bash
java TcpLineClient
```

Trong lần chạy thành công, kết quả dự kiến:

```text
# Terminal server
Server ready
Server received: PING

# Terminal client
Client received: ACK: PING
```

Dòng bắt đầu bằng `# Terminal ...` ở trên là nhãn chú giải trong block output, không phải dòng chương trình in ra.

**Giải thích theo năm khái niệm:**

1. `InetAddress.getLoopbackAddress()` cung cấp IP loopback phù hợp với môi trường; server chỉ lắng nghe truy cập nội bộ.
2. `9090` là server port. Client bind ngầm vào một local port do hệ điều hành chọn; giá trị cụ thể thay đổi theo lần chạy.
3. `new InetSocketAddress(ip, 9090)` chỉ định transport endpoint của server.
4. `connect()` mở connection TCP; `accept()` trả về socket đã kết nối. `ServerSocket` lắng nghe và `Socket` gửi/nhận là hai vai trò khác nhau.
5. `PING` và `ACK: PING` là **hai message ứng dụng**. `newLine()` + `flush()` tạo ranh giới dòng cho `readLine()`. Nếu bỏ newline mà vẫn giữ `readLine()`, bên nhận có thể tiếp tục chờ delimiter/EOF dù một phần byte đã tới.

Chương trình demo chỉ phục vụ một client một lần rồi kết thúc. Trong server thực, thường có vòng lặp `accept()`, quản lý đồng thời, timeout, xác thực, giới hạn kích thước message và xử lý đóng kết nối rõ ràng. Nếu port 9090 đang bị chiếm, đổi **cả hai** tệp sang port khả dụng.

## 8. Java 17+: thử UDP để thấy ranh giới datagram

Trong `UdpDatagramDemo.java`, receiver bind vào loopback với port `0` để hệ điều hành tự chọn port; sender gửi hai datagram độc lập mà **không gọi `connect()`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpDatagramDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket receiver = new DatagramSocket(
                     new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             DatagramSocket sender = new DatagramSocket()) {
            receiver.setSoTimeout(2000);

            for (String message : new String[] {"ONE", "TWO"}) {
                byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
                sender.send(new DatagramPacket(
                        bytes, bytes.length, receiver.getLocalSocketAddress()));
            }

            for (int i = 1; i <= 2; i++) {
                byte[] buffer = new byte[128];
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                receiver.receive(packet);
                String message = new String(packet.getData(), packet.getOffset(),
                        packet.getLength(), StandardCharsets.UTF_8);
                System.out.println("Datagram " + i + ": " + message);
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 UdpDatagramDemo.java
java UdpDatagramDemo
```

Trên loopback khi hai datagram tới theo thứ tự gửi, output là:

```text
Datagram 1: ONE
Datagram 2: TWO
```

Mỗi `receive()` xử lý một datagram và `getLength()` cho biết độ dài dữ liệu thực nhận. **Đây là quan sát thường gặp, không phải cam kết của UDP:** mạng có thể mất, đảo thứ tự hoặc lặp datagram; nếu hết 2 giây không nhận, ví dụ sẽ ném `SocketTimeoutException`. Buffer 128 byte đủ cho hai chuỗi minh họa; ứng dụng thực phải quy định kích thước hợp lệ và xử lý trường hợp datagram bị cắt.

## 9. Cách đọc log và chẩn đoán nhầm lẫn thường gặp

| Hiện tượng | Cần kiểm tra | Không nên kết luận vội |
|---|---|---|
| DNS không giải được hostname | Tên, DNS, bản ghi, kết nối tới resolver | Chưa thể khẳng định TCP port đích hỏng |
| `Connection refused` khi TCP connect | IP/port đích, listener, firewall chủ động từ chối | Không phải lỗi parse HTTP response |
| TCP connect timeout | Đường đi, firewall, IP/port, reachability | Không đủ bằng chứng server không tồn tại |
| `connect()` thành công nhưng `readLine()` đứng chờ | Bên gửi đã `flush()` chưa, đã có newline/EOF chưa, timeout | Kết nối thành công không có nghĩa message đã hoàn chỉnh |
| Nhận thiếu dữ liệu qua TCP `read()` | Framing, vòng lặp đọc đủ, EOF, giới hạn buffer | Một `read()` không đại diện cho một message |
| UDP không nhận được hoặc sai thứ tự | Port, IP, receiver bind, buffer, timeout, logic thứ tự/lặp | UDP không đảm bảo giao hàng hoặc thứ tự |
| HTTP 404 | Method/path/route/resource trong ứng dụng | TCP connection có thể hoàn toàn bình thường |

Một vài phép kiểm tra theo hệ điều hành:

- `ss -ltn` (Linux) xem TCP listening sockets; `Get-NetTCPConnection -LocalPort 9090` (PowerShell/Windows) có thể xem TCP socket liên quan port, nếu phiên bản hệ điều hành hỗ trợ.
- `curl -v https://example.com/` kiểm tra một **dịch vụ HTTP(S)** và cho thấy nhiều giai đoạn giao tiếp. **Không dùng `curl` để kiểm thử giao thức PING theo dòng** của ví dụ TCP ở trên: server đó không nói HTTP.
- Trong Java, `socket.getLocalSocketAddress()` và `socket.getRemoteSocketAddress()` giúp quan sát **hai transport endpoint** của một connected socket. Khi NAT hoặc proxy hiện diện, hai phía có thể báo các endpoint khác nhau do địa chỉ được chuyển đổi.

Hãy debug theo **tầng thấp nhất đang thất bại**: tra tên → định tuyến IP → TCP/UDP và port → kết nối/TLS (nếu có) → framing và cú pháp message → quy tắc nghiệp vụ. Không dùng một lỗi HTTP để suy diễn thành lỗi IP khi bằng chứng không hỗ trợ.

## 10. Những nhầm lẫn cần tránh

1. **"Có IP là truy cập được API."** Chưa chắc: còn port, listener, giao thức, firewall, URL/method, quyền truy cập.
2. **"Port là địa chỉ IP nhỏ hơn."** Sai: IP và port thuộc hai tầng khác nhau, đảm nhiệm hai công việc khác nhau.
3. **"Endpoint luôn là URL."** Sai: socket endpoint thường là IP/host + port; API endpoint có thể là method + URL/path.
4. **"Mỗi request HTTP là một kết nối TCP."** Sai: connection có thể được tái sử dụng hoặc multiplex, tùy phiên bản HTTP và chính sách.
5. **"TCP gửi một message thì bên kia đọc một message."** Sai: TCP chỉ đưa luồng byte theo thứ tự; cần framing ở tầng ứng dụng.
6. **"UDP có `connect()` trong Java nên UDP đã đảm bảo kết nối như TCP."** Sai: Java thiết lập peer mặc định/lọc datagram, không cung cấp handshake và đảm bảo TCP.
7. **"Mỗi người dùng truy cập server phải có server port riêng."** Sai: nhiều TCP connections dùng cùng server local port, khác endpoint của client.
8. **"Ping thành công thì HTTP chắc chắn hoạt động."** Sai: ICMP, TCP/TLS, HTTP là các bước và giao thức khác nhau.

## 11. Tự kiểm tra hiểu bài

**Tình huống A.** Log mô tả `TCP 192.0.2.10:53142 -> 198.51.100.20:443`, sau đó client gửi `GET /v1/orders`. Hãy nhận diện:

- IP client: `192.0.2.10`; local port client: `53142` (ví dụ ephemeral).
- IP server: `198.51.100.20`; TCP port server: `443`.
- Hai TCP socket endpoints: `192.0.2.10:53142` và `198.51.100.20:443`.
- Connection: quan hệ TCP giữa hai đầu, có trạng thái và vòng đời.
- Application endpoint: route HTTP `GET /v1/orders` tại hostname/dịch vụ tương ứng.
- Message: HTTP request; response tiếp theo là một message khác, có thể qua cùng connection.

**Tình huống B.** Client gọi hai lần `write()` với `"A"` rồi `"B"`, server chỉ đọc một lần và thấy `"AB"`. Có lỗi TCP không? **Không.** TCP được phép gộp byte trong một lần đọc; application protocol phải tạo ranh giới message.

**Tình huống C.** Hai URL `https://api.example.com/orders` và `https://api.example.com/users` có bắt buộc mở hai TCP connections? **Không.** Chúng là hai API paths; thư viện client có thể tái sử dụng connection tới cùng điểm đích phù hợp.

**Tình huống D.** Server bind `0.0.0.0:9090`. Client nên kết nối tới `0.0.0.0:9090`? **Không nên coi wildcard bind là địa chỉ đích có thể truy cập từ client.** Client chọn địa chỉ IP/tên máy thực sự tiếp cận được; khi chạy cùng máy, thường dùng loopback và xác minh server đang lắng nghe trên family tương ứng.

## Tổng kết

- **IP** trả lời nơi định tuyến gói tin; **port** chọn điểm giao tiếp TCP/UDP trên địa chỉ đó.
- **Transport endpoint** là đầu giao tiếp (thường IP + port + protocol); **API endpoint** mô tả thao tác/tài nguyên ứng dụng.
- **TCP connection** là mối quan hệ truyền byte có trạng thái giữa hai đầu; **message** là đơn vị thông tin được giao thức ứng dụng định nghĩa.
- Một connection có thể mang nhiều message; một API endpoint có thể được gọi qua nhiều connection; một server port có thể phục vụ nhiều client đồng thời.
- Khi dùng TCP, **luôn quy định framing**. Khi dùng UDP, **luôn tính đến mất gói, sai thứ tự, trùng lặp và giới hạn datagram**.

Chuỗi ghi nhớ: **DNS/tên → IP để định tuyến → TCP/UDP + port để giao tới socket → connection nếu giao thức có → framing/giao thức để tái dựng message → xử lý API/nghiệp vụ.**
