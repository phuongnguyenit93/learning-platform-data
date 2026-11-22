# DatagramSocket và hợp đồng gửi nhận UDP trong Java

## 1. Hiểu đúng UDP và datagram

**UDP (User Datagram Protocol)** là giao thức vận chuyển theo thông điệp (*datagram*), không thiết lập phiên kết nối kiểu TCP. Mỗi lần ứng dụng gửi một datagram, UDP chuyển **một thông điệp có ranh giới riêng** đến cặp địa chỉ IP và cổng (port) đích. Bên nhận đọc từng datagram; UDP không biến chúng thành một luồng byte liên tục.

Đổi lại sự đơn giản và độ trễ thiết lập thấp, UDP **không cam kết** gói sẽ đến, đến đúng một lần, đến theo thứ tự gửi hoặc được bên kia xử lý. `send()` hoàn thành chỉ có nghĩa hệ thống đã chấp nhận thao tác gửi, **không phải** bên nhận đã nhận hay phản hồi. Trên mạng thật, gói có thể bị mất, lặp, đảo thứ tự, chặn bởi firewall hoặc bị loại khi quá lớn.

UDP phù hợp khi ứng dụng tự quyết định cách ứng phó với mất gói: truy vấn ngắn, telemetry, khám phá dịch vụ trong mạng nội bộ, dữ liệu thời gian thực. Nếu nghiệp vụ cần truyền một luồng dữ liệu đầy đủ, đúng thứ tự và đáng tin cậy mà không muốn tự xây cơ chế phục hồi, nên xem xét TCP hoặc giao thức cấp cao hơn.

**Phân biệt quan trọng:** Một lần `DatagramSocket.send(packet)` tạo một datagram; một lần `receive(packet)` nhận tối đa một datagram vào vùng nhớ đã cấp. Điều đó **không** có nghĩa mọi lệnh gửi đều tương ứng với một lệnh nhận thành công.

## 2. Các lớp Java và vai trò

| Thành phần | Vai trò thực tế |
| --- | --- |
| `java.net.DatagramSocket` | Điểm cuối UDP: bind địa chỉ/cổng cục bộ, `send`, `receive`, đặt timeout, `close`. |
| `java.net.DatagramPacket` | Bao bọc mảng byte, vị trí bắt đầu, số byte, địa chỉ và cổng của datagram gửi/nhận. |
| `java.net.InetAddress` | Biểu diễn địa chỉ IP của máy/đích. |
| `java.net.InetSocketAddress` | Gộp địa chỉ và cổng khi cần một `SocketAddress`. |
| `java.nio.charset.StandardCharsets.UTF_8` | Chuyển chuỗi sang byte và ngược lại theo một encoding đã thống nhất. |
| `java.net.SocketTimeoutException` | Báo `receive()` hết thời gian chờ khi đã gọi `setSoTimeout(...)`. |

Các thao tác cơ bản:

1. **Bên nhận** mở `new DatagramSocket(port, localAddress)` để bind và lắng nghe một cổng; **bên gửi** có thể dùng `new DatagramSocket(0, localAddress)` để hệ điều hành chọn cổng tạm (*ephemeral port*).
2. Bên gửi mã hóa dữ liệu thành `byte[]`, tạo `DatagramPacket(data, data.length, destinationIp, destinationPort)`, rồi gọi `socket.send(packet)`.
3. Bên nhận tạo buffer và `new DatagramPacket(buffer, buffer.length)`, sau đó gọi `socket.receive(packet)`; lệnh này thường chặn cho đến khi có datagram hoặc xảy ra lỗi/timeout.
4. Sau khi nhận, sử dụng **đúng** `packet.getOffset()` và `packet.getLength()` để giải mã các byte hợp lệ. Dùng `packet.getAddress()` và `packet.getPort()` để biết nguồn gửi và trả lời đúng cổng nguồn.
5. Đóng socket bằng `try-with-resources` để nhả tài nguyên.

Cổng mà server bind là **cổng cục bộ**; địa chỉ/cổng trong gói gửi là **đích từ xa**. Một client gửi từ cổng tạm vẫn nhận phản hồi trên chính socket và cổng tạm đó nếu server trả về đúng `getAddress()`/`getPort()`.

## 3. Xác định “hợp đồng gửi nhận” trước khi viết code

Một socket chỉ vận chuyển byte; ứng dụng phải thống nhất định dạng và cách xử lý. Ví dụ dưới đây dùng hợp đồng nhỏ, dễ kiểm chứng:

| Mục | Quy ước của ví dụ |
| --- | --- |
| Máy chủ | `127.0.0.1`, UDP port `9999`; chỉ trao đổi trên máy đang chạy ví dụ. |
| Yêu cầu | Chuỗi UTF-8 chính xác `PING|42`. |
| Phản hồi hợp lệ | Chuỗi UTF-8 chính xác `PONG|42`. |
| Mã nhận diện | `42` là ID cố định để minh họa cặp request/response; ứng dụng thật phải cấp ID phù hợp cho từng yêu cầu. |
| Kích thước | Buffer nhận 1.024 byte; thông điệp của ví dụ ngắn hơn giới hạn này. |
| Timeout | Client chờ tối đa 3 giây cho một phản hồi. |
| Phạm vi | Server phục vụ **một** datagram rồi đóng; ví dụ chưa triển khai retry, chống gửi trùng, xác thực hoặc nhiều client. |

Luồng một lượt trao đổi:

```text
Client (cổng tạm)                  Server (127.0.0.1:9999)
       |                                      |
       | ----------- PING|42 --------------> |
       |                                      | receive + kiểm tra payload
       | <---------- PONG|42 ---------------- |
       |                                      |
   receive + kiểm tra nguồn/ID             đóng socket
```

Định dạng này cố ý đơn giản để làm rõ API. Với giao thức thực tế, cần có **phiên bản giao thức, loại thông điệp, request ID, giới hạn kích thước, quy tắc lỗi và thời hạn xử lý** rõ ràng. Không thể suy ra tính xác thực của một yêu cầu chỉ từ IP/port.

## 4. Ví dụ chạy được: UDP server và client

Hai tệp Java độc lập bên dưới dùng các API chuẩn, tương thích Java 15 và các JDK hiện đại. Không cần thư viện ngoài. Dùng địa chỉ IPv4 loopback để đầu ra ổn định và không mở dịch vụ ra mạng công cộng.

### 4.1. `UdpPingServer.java`

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public class UdpPingServer {
    private static final int PORT = 9999;

    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramSocket socket = new DatagramSocket(PORT, loopback)) {
            System.out.println("Server listening on 127.0.0.1:9999");

            byte[] receiveBuffer = new byte[1024];
            DatagramPacket requestPacket =
                    new DatagramPacket(receiveBuffer, receiveBuffer.length);
            socket.receive(requestPacket);

            String request = new String(
                    requestPacket.getData(), requestPacket.getOffset(),
                    requestPacket.getLength(), StandardCharsets.UTF_8);
            System.out.println("Server received: " + request);

            String response = "PING|42".equals(request) ? "PONG|42" : "ERROR";
            byte[] responseBytes = response.getBytes(StandardCharsets.UTF_8);
            DatagramPacket responsePacket = new DatagramPacket(
                    responseBytes, responseBytes.length,
                    requestPacket.getAddress(), requestPacket.getPort());
            socket.send(responsePacket);
            System.out.println("Server sent: " + response);
        }
    }
}
```

Server bind vào `127.0.0.1:9999`, nhận **một** datagram, đọc đúng các byte thực nhận, rồi gửi phản hồi tới IP và cổng nguồn của datagram. Nếu nội dung không phải `PING|42`, server trả `ERROR`; đây là quy tắc minh họa, không phải một bộ giải mã giao thức đầy đủ. `try-with-resources` đóng socket cả khi có ngoại lệ.

### 4.2. `UdpPingClient.java`

```java
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpPingClient {
    private static final int SERVER_PORT = 9999;

    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramSocket socket = new DatagramSocket(0, loopback)) {
            socket.setSoTimeout(3_000);

            byte[] requestBytes = "PING|42".getBytes(StandardCharsets.UTF_8);
            DatagramPacket requestPacket = new DatagramPacket(
                    requestBytes, requestBytes.length, loopback, SERVER_PORT);
            socket.send(requestPacket);
            System.out.println("Client sent: PING|42");

            byte[] receiveBuffer = new byte[1024];
            DatagramPacket replyPacket =
                    new DatagramPacket(receiveBuffer, receiveBuffer.length);
            try {
                socket.receive(replyPacket);
            } catch (SocketTimeoutException ex) {
                throw new IOException("No UDP reply within 3 seconds", ex);
            }

            if (!loopback.equals(replyPacket.getAddress())
                    || replyPacket.getPort() != SERVER_PORT) {
                throw new IOException("Unexpected UDP responder");
            }

            String response = new String(
                    replyPacket.getData(), replyPacket.getOffset(),
                    replyPacket.getLength(), StandardCharsets.UTF_8);
            if (!"PONG|42".equals(response)) {
                throw new IOException("Unexpected response: " + response);
            }
            System.out.println("Client received: " + response);
        }
    }
}
```

Client bind cổng tạm bằng `0`, gửi yêu cầu đến cổng `9999`, rồi đợi trên **cùng socket**. `setSoTimeout(3_000)` chỉ giới hạn thời gian chặn của `receive()`: hết 3 giây không có datagram phù hợp **không chứng minh** server chưa xử lý yêu cầu. Kiểm tra IP/cổng nguồn và nội dung `PONG|42` giúp bắt lỗi giao thức; IP/cổng **không phải** cơ chế xác thực chống giả mạo.

### 4.3. Biên dịch và chạy

Lưu hai tệp cạnh nhau, mở **hai terminal** trong thư mục đó. Biên dịch bằng JDK có hỗ trợ `--release 15` (ví dụ JDK 17 hoặc 21):

```bash
javac --release 15 UdpPingServer.java UdpPingClient.java
```

Terminal thứ nhất chạy server:

```bash
java UdpPingServer
```

Terminal thứ hai chạy client **sau khi server đã bắt đầu lắng nghe**:

```bash
java UdpPingClient
```

Kết quả thành công của server:

```text
Server listening on 127.0.0.1:9999
Server received: PING|42
Server sent: PONG|42
```

Kết quả thành công của client:

```text
Client sent: PING|42
Client received: PONG|42
```

Đây là đầu ra mỗi tiến trình; thứ tự xen kẽ giữa hai terminal không cần giống nhau. Nếu client chạy khi server chưa lắng nghe, nó có thể hết timeout. Nếu cổng `9999` đã được chiếm, server không bind được; đổi **cùng số cổng** ở cả hai tệp rồi biên dịch lại. Server chỉ xử lý một yêu cầu nên muốn thử lại phải chạy server lần nữa.

## 5. Các chi tiết dễ hiểu sai trong API

### 5.1. Độ dài của `DatagramPacket` không bằng độ dài buffer

`new DatagramPacket(new byte[1024], 1024)` tạo vùng **có thể nhận tối đa** 1.024 byte. Sau `receive()`, `getLength()` là **số byte đã nhận** (không nhất thiết là 1.024), `getOffset()` là vị trí bắt đầu. Không dùng `new String(packet.getData())`: cách đó có thể đọc cả phần buffer chưa dùng hoặc còn dữ liệu cũ.

```java
String text = new String(
        packet.getData(), packet.getOffset(),
        packet.getLength(), StandardCharsets.UTF_8);
```

Đoạn trên minh họa khi biến `packet` đã chứa datagram nhận được; đây không phải một chương trình Java độc lập. Với dữ liệu nhị phân, giải mã theo schema của giao thức thay vì ép thành chuỗi.

Nếu tái sử dụng **cùng một đối tượng** `DatagramPacket` qua nhiều lần `receive()`, phải phục hồi sức chứa trước lần nhận tiếp theo, ví dụ `packet.setLength(buffer.length)` (với offset bằng 0), hoặc tạo packet mới. Nếu không, chiều dài datagram ngắn trước đó có thể vô tình trở thành giới hạn lần sau.

### 5.2. UDP giữ ranh giới thông điệp, nhưng không tự ghép gói lớn

Một lệnh `send()` gửi một datagram, nhưng nếu buffer nhận nhỏ hơn nội dung, dữ liệu có thể **bị cắt** và phần vượt quá không được tự nối vào lần `receive()` kế tiếp. Kích thước datagram cũng bị giới hạn bởi IP/UDP và đường truyền: gói lớn làm tăng nguy cơ phân mảnh, rơi gói và lỗi trên mạng thật.

Thiết kế payload nhỏ phù hợp với MTU đường đi, xác định giới hạn tối đa ngay trong hợp đồng và từ chối dữ liệu vượt giới hạn. Giá trị khoảng 1.200 byte đôi khi được dùng làm điểm khởi đầu cho giao thức Internet, **không phải** lời bảo đảm không phân mảnh trên mọi mạng. Nếu nghiệp vụ cần chuyển dữ liệu lớn, dùng giao thức có cơ chế chia nhỏ/ghép lại, kiểm tra toàn vẹn và truyền lại, hoặc cân nhắc TCP.

Với text, hãy kiểm tra giới hạn trên **số byte sau UTF-8 encoding**, vì `String.length()` đếm đơn vị UTF-16, không phải số byte gửi qua UDP.

### 5.3. `connect()` trên UDP không tạo một kết nối tin cậy

`DatagramSocket.connect(remoteAddress, remotePort)` gắn một peer mặc định và lọc datagram theo địa chỉ/cổng của peer đó; nó **không** thực hiện handshake TCP, không xác nhận peer tồn tại và không thêm bảo đảm giao hàng. Có thể dùng `connect()` khi chỉ trao đổi với một peer, nhưng demo chọn `send(packet)` và `receive(packet)` không connect để làm rõ IP/port của từng datagram.

Khi đích không thể tới, một socket UDP đã connect **có thể** gặp `PortUnreachableException`; sự xuất hiện của ngoại lệ này phụ thuộc hệ điều hành và mạng, nên không được dùng nó làm cơ chế phát hiện chắc chắn server có đang chạy hay không.

### 5.4. Timeout và vòng đời socket

- `receive()` chờ datagram; gọi `setSoTimeout(milliseconds)` để không chặn vô hạn khi cần một giới hạn thời gian.
- `SocketTimeoutException` nghĩa là chưa nhận được trong thời gian chờ, **không** phân biệt được mất request, mất response, server chậm hay firewall.
- `close()` giải phóng cổng và tài nguyên; dùng `try-with-resources` để đóng đúng cả khi lỗi.
- Server nhiều request thường có vòng lặp nhận, kiểm tra và phản hồi, nhưng phải có điều kiện dừng, giới hạn tài nguyên, giám sát lỗi và chiến lược xử lý tải.

## 6. Nâng hợp đồng từ demo lên ứng dụng thực tế

**Độ tin cậy theo yêu cầu nghiệp vụ.** Với thao tác cần phản hồi, client cần timeout và chính sách retry có giới hạn, backoff phù hợp. Mỗi request nên có ID; server ghi nhận ID đã xử lý trong khoảng thời gian cần thiết để tránh thực thi tác dụng phụ hai lần nếu client gửi lại sau khi mất response. Đừng retry mù quáng thao tác không idempotent như ghi nhận thanh toán hay thay đổi số dư.

**Xử lý sai thứ tự, trùng và lỗi.** Phản hồi phải gắn `requestId` để client nhận đúng request đang đợi. Khi nhiều yêu cầu cùng lúc, chỉ kiểm tra IP/cổng không đủ. Bên nhận kiểm tra phiên bản, loại thông điệp, độ dài, encoding và các giới hạn giá trị; định nghĩa thông điệp lỗi rõ ràng. Nếu cần truyền dữ liệu có thứ tự, thêm sequence number và quy tắc bỏ gói cũ.

**Bảo mật.** UDP bình thường **không tự mã hóa, xác thực hoặc chống giả mạo nguồn**. Chỉ bind `127.0.0.1` trong bài thực hành để giới hạn phạm vi. Khi dùng mạng không tin cậy, cần giao thức bảo mật phù hợp và kiểm soát truy cập; giới hạn kích thước, tốc độ, số client, vùng nhớ để giảm nguy cơ lạm dụng. Không tin rằng `getAddress()/getPort()` chứng minh danh tính.

**Quan sát và vận hành.** Ghi log request ID, nguồn, kích thước, timeout và số lần retry; tránh log payload nhạy cảm. Tách rõ lỗi không bind được cổng, lỗi timeout và lỗi dữ liệu. Kiểm thử trên môi trường có mất gói, trễ và đảo thứ tự thay vì chỉ dựa vào localhost.

**Chọn API.** `DatagramSocket` vẫn là **API Java công khai, được hỗ trợ** cho UDP đồng bộ đơn giản. Khi cần `Selector`, non-blocking I/O hoặc làm việc qua `ByteBuffer`, cân nhắc `java.nio.channels.DatagramChannel`. Java 15 có JEP 373 **thay thế phần cài đặt nội bộ cũ của DatagramSocket** bằng cơ chế hiện đại hơn; tên JEP chứa chữ “legacy” nói về phần cài đặt trước đó, **không** có nghĩa phải ngừng dùng lớp `DatagramSocket`. Không cần dùng các chi tiết cài đặt nội bộ như `DatagramSocketImpl`.

## 7. Lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Client timeout | Server chưa chạy, sai IP/cổng, gói bị mất hoặc bị chặn | Kiểm tra server đã bind, đúng endpoint, firewall, logging; bổ sung retry nếu hợp đồng yêu cầu. |
| `BindException` khi mở server | Cổng đã được tiến trình khác sử dụng hoặc bind không hợp lệ | Chọn cổng còn trống; sửa đồng bộ cấu hình hai phía. |
| Chuỗi có ký tự rác hoặc ký tự `\u0000` | Giải mã toàn bộ buffer thay vì số byte thực nhận; encoding không khớp | Dùng `getOffset()/getLength()` và UTF-8 nhất quán. |
| Gói ngắn sau làm gói tiếp theo bị cắt | Tái sử dụng `DatagramPacket` nhưng không reset độ dài | Gọi `setLength(buffer.length)` trước khi nhận lại hoặc tạo packet mới. |
| Request có vẻ thành công nhưng server không xử lý | Giả định `send()` là xác nhận giao hàng | Dùng phản hồi ứng dụng, timeout, request ID và retry có giới hạn. |
| Dữ liệu lớn thiếu phần cuối | Buffer nhận nhỏ, datagram bị cắt hoặc phân mảnh gây rơi gói | Thiết kế giới hạn payload nhỏ; xử lý phân mảnh ở cấp giao thức nếu thật sự cần. |
| Phản hồi sai yêu cầu | Không kiểm tra nguồn hoặc request ID; có nhiều gói cùng lúc | Ghép phản hồi bằng ID, xác minh nguồn theo chính sách và xử lý gói lạ. |

### Tự kiểm tra

1. Vì sao client dùng `new DatagramSocket(0, loopback)` vẫn nhận được phản hồi? Hãy giải thích vai trò của cổng tạm và `requestPacket.getPort()`.
2. Nếu server nhận datagram dài 1.500 byte vào buffer 1.024 byte thì ứng dụng còn đọc được 476 byte dư ở lần `receive()` sau không? Giải thích theo ranh giới datagram.
3. Nếu server đã xử lý yêu cầu nhưng response bị mất, retry có thể gây lỗi nghiệp vụ gì? Đề xuất `requestId` và quy tắc idempotency.
4. Thử chạy client trước server và quan sát timeout; giải thích tại sao đây không phải bằng chứng chắc chắn rằng datagram chưa được xử lý.

**Điểm cần nhớ:** `DatagramSocket` cung cấp việc gửi/nhận **datagram**; tính đúng đắn của một giao thức UDP nằm ở hợp đồng dữ liệu, giới hạn byte, kiểm tra nguồn/ID, deadline, xử lý mất hoặc trùng gói và bảo mật ở tầng ứng dụng.

## Tài liệu chính thức

- [Oracle Java API — DatagramSocket (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramSocket.html)
- [Oracle Java API — DatagramPacket (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/DatagramPacket.html)
- [OpenJDK JEP 373 — Reimplement the Legacy Datagram Socket API (JDK 15)](https://openjdk.org/jeps/373)