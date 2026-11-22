# TCP, UDP, HTTP, TLS và WebSocket nằm ở những lớp nào?

**Câu trả lời cốt lõi:** Theo mô hình OSI, **TCP và UDP ở lớp 4 (Transport)**; **HTTP và WebSocket ở lớp 7 (Application)**. **TLS** bảo vệ giao tiếp của ứng dụng phía trên tầng giao vận: thường được liên hệ với chức năng lớp 5–6 (Session/Presentation), nhưng **không có một vị trí lớp OSI cố định, chính thức**. Trong mô hình TCP/IP thực tế, HTTP, WebSocket và TLS thường nằm trong nhóm giao thức phía ứng dụng; TCP/UDP ở tầng giao vận.

Điểm dễ nhầm nhất: **HTTP không luôn chạy trên TCP**. HTTP/1.1 và HTTP/2 thường dùng TCP; **HTTP/3 chạy trên QUIC, mà QUIC chạy trên UDP và tích hợp bắt tay TLS 1.3**.

## 1. Hai mô hình lớp phải phân biệt

Mô hình **OSI 7 lớp** giúp học khái niệm; mô hình **TCP/IP** phản ánh cách các giao thức Internet thường được tổ chức. Việc “xếp giao thức vào lớp” có thể là phép ánh xạ gần đúng, nhất là với TLS và QUIC.

| Lớp OSI | Vai trò chính | Ví dụ, liên hệ |
|---|---|---|
| **7 – Application** | Quy ước thông điệp và hành vi ứng dụng | HTTP, WebSocket, DNS |
| **6 – Presentation** | Biểu diễn dữ liệu, mã hóa/giải mã về mặt khái niệm | Chức năng bảo mật của TLS thường được liên hệ ở đây |
| **5 – Session** | Thiết lập, duy trì phiên theo cách mô tả OSI | Một số chức năng bắt tay/phiên TLS cũng thường được liên hệ ở đây |
| **4 – Transport** | Giao tiếp đầu cuối giữa tiến trình, cổng, truyền dữ liệu | TCP, UDP |
| **3 – Network** | Địa chỉ IP và định tuyến gói | IPv4, IPv6 |
| **2 – Data Link** | Truyền frame trên một liên kết | Ethernet, Wi‑Fi (phần MAC) |
| **1 – Physical** | Tín hiệu truyền qua môi trường vật lý | Cáp, sóng vô tuyến |

Ở cách phân tầng TCP/IP bốn lớp, OSI 5–7 thường được gom vào **Application**; OSI 4 là **Transport**; OSI 3 là **Internet**; OSI 1–2 thuộc **Link/Network access**. Vì vậy câu “TLS ở lớp 6” chỉ là cách minh họa chức năng, **không phải một quy tắc phân tầng bắt buộc**.

## 2. Phân loại năm giao thức

| Giao thức | OSI (gần đúng) | Vai trò riêng | Nền tảng truyền phổ biến |
|---|---|---|---|
| **TCP** | L4 – Transport | Luồng byte tin cậy, có thứ tự; kiểm soát luồng và tắc nghẽn | IP |
| **UDP** | L4 – Transport | Datagram có ranh giới bản tin; không tự bảo đảm nhận đủ, đúng thứ tự hay truyền lại | IP |
| **HTTP** | L7 – Application | Ngữ nghĩa request/response, method, status, header, body | HTTP/1.1, HTTP/2 thường qua TCP; HTTP/3 qua QUIC/UDP |
| **TLS** | Nằm giữa ứng dụng và giao vận trong ngăn xếp TLS-over-TCP; liên hệ L5–L6 về chức năng | Xác thực đầu bên kia (thường là máy chủ), trao đổi khóa, bảo mật và toàn vẹn dữ liệu | Thường bao bọc luồng trên TCP; TLS 1.3 được QUIC tích hợp theo cách riêng |
| **WebSocket** | L7 – Application | Kênh hai chiều, lâu dài, có cấu trúc frame/message | Truyền thống qua TCP, có thể qua TLS; cũng có cơ chế trên HTTP/2 và HTTP/3 |

Các hàng không phải năm lớp nối tiếp nhau. **TCP và UDP là hai lựa chọn cùng cấp**. **HTTP và WebSocket là hai giao thức phía ứng dụng có quan hệ khi thiết lập WebSocket**, còn TLS là lớp bảo mật được dùng tùy ngăn xếp.

### TCP: luồng byte, không phải các “message”

TCP thiết lập kết nối, đánh số thứ tự, truyền lại khi cần và chuyển tới ứng dụng một **luồng byte có thứ tự**. Nếu bên gửi ghi ba lần, bên nhận không nhất thiết đọc đúng ba lần tương ứng: ranh giới từng lần ghi không được TCP bảo toàn. HTTP/1.1, HTTP/2 và WebSocket cổ điển tự định nghĩa cách phân khung bên trên luồng đó.

### UDP: gói dữ liệu độc lập

UDP gửi các datagram; nó không tự hứa giao hàng, truyền lại hay sắp thứ tự. UDP phù hợp khi ứng dụng muốn tự quyết định chính sách truyền, chẳng hạn giao thức thời gian thực. **Không suy ra rằng mọi ứng dụng dùng UDP đều không tin cậy:** QUIC xây cơ chế truyền đáng tin cậy cho từng stream trên UDP.

### HTTP: quy tắc trao đổi ở cấp ứng dụng

HTTP xác định phương thức như GET/POST, mã trạng thái, header, body và ngữ nghĩa trao đổi. HTTP không phải tên khác của TCP: HTTP chỉ cần một cơ chế chuyên chở đáp ứng yêu cầu phiên bản đó.

- **HTTP/1.1:** thường dùng một kết nối TCP; có thể chạy không mã hóa (**http**) hoặc trên TLS (**https**).
- **HTTP/2:** thường chạy trên TLS/TCP khi dùng trên Web; có multiplexing nhiều stream trên kết nối, nhưng TCP vẫn truyền một luồng byte phía dưới. Một số môi trường hỗ trợ HTTP/2 không TLS (**h2c**).
- **HTTP/3:** chuyển việc vận chuyển stream cho **QUIC**, chạy trên UDP; không có TCP dưới HTTP/3.

### TLS: bảo mật, không thay thế TCP/UDP

TLS thường thiết lập khóa, xác thực danh tính bằng chứng chỉ và bảo vệ dữ liệu khỏi nghe lén hoặc sửa đổi khi truyền. Với HTTPS chạy trên TCP, ứng dụng gửi HTTP vào TLS; TLS mã hóa dữ liệu rồi truyền qua TCP. TLS **không tự thực hiện định tuyến IP hay đảm bảo byte đến nơi như TCP**. Với QUIC, TLS 1.3 cung cấp cơ chế bắt tay và khóa được tích hợp vào QUIC; không vẽ một tầng TLS-record thông thường “nằm trên UDP” rồi mới đến QUIC.

TLS bảo vệ nội dung thuộc phạm vi của nó; không có nghĩa mọi metadata mạng đều được mã hóa (ví dụ địa chỉ IP và cổng UDP/TCP vẫn cần để chuyển gói).

### WebSocket: hai chiều sau giai đoạn thiết lập

WebSocket cung cấp **message/frame và giao tiếp hai chiều (full-duplex)**: cả client lẫn server có thể gửi dữ liệu khi kết nối còn sống. Khác với mô hình request/response thông thường của HTTP, server không cần đợi client tạo một request mới mỗi lần muốn đẩy thông điệp.

Với WebSocket truyền thống theo HTTP/1.1, client bắt đầu bằng yêu cầu **HTTP Upgrade**; server chấp nhận bằng **101 Switching Protocols**. Sau bước đó, dữ liệu đi dưới dạng **WebSocket frame**, không phải một chuỗi HTTP response thông thường.

HTTP/2 và HTTP/3 không dùng cơ chế Upgrade/101 đó. Chúng có **Extended CONNECT** để thiết lập WebSocket trên một stream nếu hai đầu hỗ trợ (lần lượt RFC 8441 và RFC 9220). Vì vậy nói “WebSocket luôn yêu cầu TCP riêng và HTTP/1.1 Upgrade” là quá tuyệt đối.

## 3. Nhìn ngăn xếp từ trên xuống

Các sơ đồ dưới đây là **ngăn xếp giao thức**, không phải các tên gọi thay thế cho bảy lớp OSI.

### A. HTTPS bằng HTTP/1.1 hoặc HTTP/2

~~~text
Ứng dụng Java / trình duyệt
  HTTP/1.1 hoặc HTTP/2         Application
  TLS (thường 1.2/1.3)         Bảo mật giữa ứng dụng và TCP
  TCP                          Transport
  IP                           Network/Internet
  Ethernet hoặc Wi-Fi          Link
  Môi trường vật lý            Physical
~~~

Khi truy cập một URL **https://**, không thể chỉ nhìn URL mà kết luận chắc chắn HTTP/1.1 hay HTTP/2; phiên bản được thương lượng và phụ thuộc client/server. TLS thường thương lượng giao thức ứng dụng bằng **ALPN**.

### B. HTTPS bằng HTTP/3

~~~text
Ứng dụng Java / trình duyệt
  HTTP/3                       Application
  QUIC (tích hợp TLS 1.3)      Transport trên UDP
  UDP                          Transport nền
  IP                           Network/Internet
  Ethernet hoặc Wi-Fi          Link
  Môi trường vật lý            Physical
~~~

QUIC cung cấp kết nối, stream, kiểm soát tắc nghẽn và cơ chế tin cậy ở phía trên UDP. Một kết nối QUIC có nhiều stream có thể giảm hiện tượng một mất gói làm đứng các stream khác ở mức giao vận, vốn là vấn đề với nhiều stream HTTP/2 dùng chung một TCP connection. Điều này **không** có nghĩa QUIC không bị mất gói hoặc không cần truyền lại.

### C. WebSocket thông thường

~~~text
ws://host/chat:
  WebSocket messages/frames → TCP → IP → Link

wss://host/chat:
  WebSocket messages/frames → TLS → TCP → IP → Link
~~~

Hai dòng trên mô tả dạng WebSocket cổ điển qua HTTP/1.1 khi thiết lập. Với WebSocket qua HTTP/2, dữ liệu thuộc stream HTTP/2 trên TLS/TCP; với HTTP/3, dữ liệu thuộc stream HTTP/3 trên QUIC/UDP. **ws** là scheme không yêu cầu TLS; **wss** là scheme bảo mật. Scheme không nói chắc giao thức HTTP nào đã được dùng để thiết lập.

## 4. Một phiên làm việc thực sự diễn ra thế nào?

**Ví dụ HTTPS trên HTTP/2/TCP:**

1. Client tìm địa chỉ đích qua DNS (DNS là một giao thức riêng, có thể chạy trên nhiều kiểu vận chuyển).
2. Client bắt tay TCP với máy chủ: SYN → SYN-ACK → ACK.
3. Client/server thực hiện TLS handshake, xác thực và thiết lập khóa; ALPN có thể chọn h2.
4. HTTP/2 gửi request/response trên các stream của kết nối TLS/TCP ấy.
5. Kết nối có thể được tái sử dụng; việc đóng HTTP stream không nhất thiết đóng luôn TCP connection.

**Ví dụ WebSocket trên HTTP/1.1:** sau TCP (và TLS nếu wss), client gửi yêu cầu tương tự:

~~~http
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
~~~

Nếu chấp nhận, server có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

Đây là ví dụ minh họa theo chuẩn; client thực tế phải sinh khóa ngẫu nhiên cho từng handshake. Từ sau phản hồi 101 hợp lệ, hai bên trao đổi frame WebSocket (text/binary, ping/pong, close) trên cùng đường truyền. **HTTP hỗ trợ việc mở kênh**, còn WebSocket quy định cách gửi message trong giai đoạn tiếp theo.

## 5. Liên hệ trực tiếp với Java 17+

| API Java | Giao thức/lớp liên hệ | Dùng khi |
|---|---|---|
| **java.net.Socket**, **ServerSocket**, **SocketChannel** | TCP / Transport | Viết hoặc phân tích giao thức trên luồng TCP |
| **DatagramSocket**, **DatagramPacket**, **DatagramChannel** | UDP / Transport | Gửi nhận datagram |
| **javax.net.ssl.SSLSocket**, **SSLEngine** | TLS | Bổ sung bảo mật cho một kết nối/phương thức vận chuyển phù hợp |
| **java.net.http.HttpClient** | HTTP / Application | HTTP/1.1, HTTP/2, HTTPS |
| **java.net.http.WebSocket** | WebSocket / Application | Giao tiếp full-duplex qua WebSocket |

**Ví dụ chạy được trên Java 17:** chương trình gửi một request HTTPS và in phiên bản HTTP thực sự được dùng cùng phiên bản TLS của kết nối.

~~~java
// File: LayerDemo.java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import javax.net.ssl.SSLSession;

public class LayerDemo {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2) // ưu tiên, không bắt buộc
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/"))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP: " + response.version());
        System.out.println("TLS: " + response.sslSession()
                .map(SSLSession::getProtocol)
                .orElse("(không có phiên TLS)"));
        System.out.println("Status: " + response.statusCode());
    }
}
~~~

~~~bash
javac LayerDemo.java
java LayerDemo
~~~

Ví dụ **cần kết nối Internet và TLS certificate hợp lệ**. Dòng HTTP có thể là **HTTP_2** hoặc **HTTP_1_1** tùy máy chủ, proxy và thương lượng; phiên bản TLS và status code cũng phụ thuộc môi trường. Vì thế không có stdout cố định đáng tin để áp cho mọi lần chạy. Trên **JDK 17 chuẩn**, HttpClient hỗ trợ HTTP/1.1 và HTTP/2; không tự suy ra nó hỗ trợ HTTP/3 chỉ vì URL dùng HTTPS.

Mấu chốt khi lập trình: **Socket** thao tác ở tầng TCP; **HttpClient** diễn đạt HTTP; **WebSocket** quản lý thông điệp hai chiều; **SSLSocket/SSLEngine** lo TLS. Các API không cùng cấp độ trừu tượng.

## 6. Nhận diện nhanh qua URL, cổng và gói tin

| Quan sát | Suy ra được | Không được suy ra |
|---|---|---|
| **https://example.com** | Có HTTP được bảo vệ trên kết nối tới origin (trong trường hợp thông thường) | Chắc chắn là HTTP/2 hoặc luôn dùng TCP |
| **wss://example.com/chat** | WebSocket bảo mật | Chắc chắn dùng HTTP/1.1 Upgrade |
| **TCP port 443** | Một kết nối TCP đến cổng 443 | Chắc chắn toàn bộ nội dung là HTTP hay TLS |
| **UDP port 443** | Một luồng datagram UDP đến cổng 443 | Chắc chắn đó là QUIC/HTTP/3 nếu chưa nhận dạng gói |
| **Có TLS handshake** | Có quá trình thiết lập bảo mật TLS hoặc TLS được tích hợp trong giao thức liên quan | TLS là một “lớp 6 OSI chính thức” |
| **Có HTTP 101 + Upgrade: websocket** | Đang chuyển từ HTTP/1.1 sang WebSocket nếu handshake hợp lệ | Các message WebSocket tiếp theo vẫn là HTTP response |

Để phân tích thực tế, dùng **Wireshark** hoặc trace của client/server; có thể lọc theo tcp, udp, tls, http, websocket, quic. Kết quả phụ thuộc phiên bản, việc giải mã, bộ phân tích giao thức và lưu lượng thực tế. **Cổng mặc định chỉ là quy ước:** HTTP thường dùng TCP 80, HTTPS thường dùng TCP 443 hoặc QUIC/UDP 443; WebSocket ws/wss thường lần lượt 80/443, nhưng đều có thể cấu hình cổng khác.

## 7. Bốn nhầm lẫn quan trọng

1. **“HTTP thuộc tầng Transport vì chạy trên TCP.”** Sai: HTTP là giao thức ứng dụng. Giao thức cấp trên có thể chạy trên nhiều nền truyền khác nhau.
2. **“TLS chính xác là OSI lớp 6.”** Chưa chính xác: đây là cách gán chức năng để học; việc triển khai TLS thường nằm giữa ứng dụng và TCP, còn QUIC tích hợp TLS theo cách khác.
3. **“UDP luôn thiếu độ tin cậy, nên HTTP/3 không đáng tin.”** Sai: UDP không tự làm tin cậy, nhưng QUIC làm việc đó ở bên trên cho từng stream.
4. **“WebSocket chính là HTTP kéo dài.”** Sai về dữ liệu sau handshake HTTP/1.1: WebSocket có định dạng frame và ngữ nghĩa riêng. HTTP/2/3 còn có cơ chế Extended CONNECT, không dùng Upgrade/101 kiểu HTTP/1.1.

## 8. Tự kiểm tra cách chọn sơ đồ

- Gọi REST API qua HTTPS và thấy **HTTP/2**: vẽ **HTTP/2 → TLS → TCP → IP**.
- Cùng URL HTTPS nhưng thương lượng **HTTP/3**: vẽ **HTTP/3 → QUIC (TLS 1.3 tích hợp) → UDP → IP**.
- Ứng dụng chat dùng **wss** qua HTTP/1.1: vẽ **WebSocket frames → TLS → TCP → IP** sau HTTP Upgrade.
- Dịch vụ gửi datagram tự thiết kế: vẽ **giao thức ứng dụng → UDP → IP**; tự quyết định có cần phát hiện mất gói, truyền lại và sắp thứ tự hay không.

**Quy tắc nhớ:** Hỏi **“giao thức này quy định điều gì?”** trước khi hỏi **“nó chạy trên gì?”**. HTTP/WebSocket quy định nội dung và luồng giao tiếp ứng dụng; TCP/UDP quy định cách vận chuyển; TLS cung cấp bảo mật; IP đưa gói đi qua mạng. Các giao thức lồng nhau, nhưng không nhất thiết ánh xạ một-một vào OSI.

### Tài liệu chuẩn để đọc thêm

- [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293)
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [RFC 8441 — WebSocket qua HTTP/2](https://www.rfc-editor.org/rfc/rfc8441)
- [RFC 9220 — WebSocket qua HTTP/3](https://www.rfc-editor.org/rfc/rfc9220)
