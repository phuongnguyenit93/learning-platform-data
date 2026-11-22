# UDP: Bind địa chỉ cục bộ, cổng và vòng đời socket trong Java

> **Phạm vi:** Bài thuộc nhóm **UDP và datagram** của module Java 15. Trọng tâm là cách một `DatagramSocket` được **bind vào địa chỉ IP/cổng cục bộ**, sự khác biệt giữa bind và connect, cách nhận diện trạng thái socket, gửi/nhận `DatagramPacket`, timeout, xử lý lỗi và **đóng socket đúng vòng đời**. Tất cả API đều thuộc Java SE hiện hành, sử dụng ổn định trên **JDK 17, 21, 25+**. Ví dụ không dựa vào API đã lỗi thời hoặc tính năng preview.

## 1. UDP và khái niệm endpoint

**UDP (User Datagram Protocol)** là giao thức truyền những *datagram* độc lập. Khác với TCP, UDP **không tạo một luồng byte đáng tin cậy hay bắt buộc có bước bắt tay thiết lập kết nối**. Mỗi lần gửi là một datagram; mỗi lần nhận là một thông điệp có ranh giới riêng trong phạm vi buffer.

Một endpoint UDP về cơ bản gắn với:

- **Địa chỉ IP cục bộ:** địa chỉ của giao diện mạng phía nhận/gửi, ví dụ `127.0.0.1` cho IPv4 loopback.
- **Cổng UDP cục bộ:** số nguyên trong khoảng `0..65535` lúc cấu hình; cổng `0` trong yêu cầu **bind** có nghĩa “nhờ hệ điều hành chọn cổng khả dụng”, không phải cổng ứng dụng lắng nghe cố định.
- **Giao thức:** UDP. Một dịch vụ TCP và một dịch vụ UDP có thể cùng sử dụng con số cổng như `8080` vì chúng là các không gian transport riêng.
- **Endpoint từ xa:** địa chỉ IP và cổng mà một datagram được gửi đến. Endpoint từ xa **không phải** địa chỉ cục bộ mà socket đang bind.

Ví dụ:

```text
Máy A                                             Máy B
UDP socket A                                      UDP socket B
bind 127.0.0.1:ephemeral     -->  UDP datagram -->  bind 127.0.0.1:portB
       source IP:portA                                 destination IP:portB

Mỗi datagram có:
  source IP + source UDP port
  destination IP + destination UDP port
  payload bytes
```

Sơ đồ dùng **hai socket trên cùng một máy loopback** cho dễ kiểm thử. Khi hai máy thật giao tiếp, IP nguồn và IP đích có thể là địa chỉ mạng khác; NAT, firewall và routing có thể thay đổi cách endpoint được nhìn thấy từ bên ngoài.

**UDP không bảo đảm:** datagram tới nơi, chỉ đến một lần, đúng thứ tự gửi, hoặc rằng ứng dụng bên kia đang chạy. Lời gọi `send(...)` thành công thường chỉ có nghĩa dữ liệu đã được hệ điều hành tiếp nhận để xử lý gửi, **không** chứng minh bên nhận đã nhận.

## 2. `DatagramSocket` và `DatagramPacket`: mỗi đối tượng giữ vai trò gì?

Java SE cung cấp hai loại cơ bản:

| API | Vai trò | Thông tin đáng chú ý |
| --- | --- | --- |
| `java.net.DatagramSocket` | Endpoint UDP của tiến trình; bind, send, receive, connect tùy chọn, close | `bind`, `getLocalPort`, `isBound`, `isClosed`, `setSoTimeout` |
| `java.net.DatagramPacket` | Một datagram mang payload và địa chỉ gửi/nhận | `getData`, `getOffset`, `getLength`, `getAddress`, `getPort` |
| `java.net.InetAddress` | Địa chỉ IP | `getByName`, `getLoopbackAddress`, `isLoopbackAddress` |
| `java.net.InetSocketAddress` | Cặp IP + port; dùng cho bind hoặc destination | `new InetSocketAddress(address, port)` |
| `java.net.SocketAddress` | Kiểu nền cho endpoint địa chỉ | Được `DatagramSocket.bind` nhận làm tham số |
| `java.net.SocketTimeoutException` | Timeout khi hoạt động I/O hết thời gian cho phép | `receive` có thể ném sau `setSoTimeout` |

Hình dung:

```text
DatagramSocket                 DatagramPacket
---------------------         --------------------------------------
local IP / local port         data[] / offset / length
bound / connected / closed    source or destination IP / UDP port
socket options                nội dung của 1 lần gửi hoặc nhận
---------------------         --------------------------------------
socket.send(packet)    --->   packet chứa bytes + địa chỉ đích
socket.receive(packet) <---   packet nhận bytes + địa chỉ nguồn
```

Một socket UDP có thể **gửi nhiều datagram** và **nhận nhiều datagram**, không cần tạo socket mới cho từng thông điệp. Tuy nhiên socket có trạng thái và tài nguyên hệ điều hành; ứng dụng cần quản lý nó rõ ràng.

### Điểm khác TCP

- `DatagramSocket` không có `accept()` và không tạo một socket riêng cho từng client sau khi nhận.
- `DatagramSocket.receive(...)` trả về **một datagram** hoặc báo lỗi/timeout; không phải luồng dữ liệu liên tục như `InputStream` của TCP.
- Gọi `DatagramSocket.connect(...)` **không** thiết lập một kết nối tin cậy kiểu TCP; chi tiết ở phần 7.
- `Socket`, `ServerSocket` là lớp TCP, không thay thế cho `DatagramSocket` khi làm việc với UDP.

## 3. Bind là gì? Trạng thái UNBOUND và BOUND

**Bind** liên kết một `DatagramSocket` với địa chỉ/cổng **cục bộ** mà hệ điều hành sẽ dùng để gửi và/hoặc nhận UDP.

Một ví dụ rõ ràng nhất: tạo socket chưa bind rồi bind thủ công:

```java
InetAddress local = InetAddress.getByName("127.0.0.1");
DatagramSocket socket = new DatagramSocket((SocketAddress) null);
socket.bind(new InetSocketAddress(local, 0));
```

Đây là đoạn **minh họa**, cần import `java.net.*` và xử lý `IOException` trong phương thức. Với `(SocketAddress) null`, Java chọn constructor nhận `SocketAddress`; nó tạo socket **chưa bind**. Sau `bind(...)`, socket được gán endpoint cục bộ.

Có thể viết ngắn hơn:

```java
try (DatagramSocket socket =
        new DatagramSocket(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0))) {
    System.out.println(socket.isBound()); // true
}
```

Đây cũng là snippet đặt bên trong phương thức xử lý ngoại lệ. Constructor nhận `SocketAddress` này **bind ngay**, trong khi constructor nhận `null` ở ví dụ trước **chưa bind**.

### Constructor nào bind ngay?

| Cách tạo | Trạng thái sau constructor | Endpoint cục bộ |
| --- | --- | --- |
| `new DatagramSocket()` | `BOUND` | Bind wildcard IP vào một cổng khả dụng do hệ điều hành chọn |
| `new DatagramSocket(0)` | `BOUND` | Bind wildcard IP vào một cổng khả dụng |
| `new DatagramSocket(9000)` | `BOUND` | Bind wildcard IP vào UDP port 9000 nếu được phép |
| `new DatagramSocket(9000, localIp)` | `BOUND` | Bind vào `localIp:9000` nếu địa chỉ và cổng hợp lệ |
| `new DatagramSocket(new InetSocketAddress(localIp, 0))` | `BOUND` | Bind vào IP cụ thể, cổng được tự chọn |
| `new DatagramSocket((SocketAddress) null)` | `UNBOUND` | Chưa có endpoint cục bộ được cấp |
| `socket.bind(new InetSocketAddress(localIp, port))` | Chuyển `UNBOUND → BOUND` | Địa chỉ/cổng được chọn ở lời gọi bind |

Đối với `new DatagramSocket(0)`, số `0` không phải kết quả cổng mà socket đang dùng: hãy đọc **`socket.getLocalPort()` sau khi constructor thành công** để biết cổng thực tế.

**Không gọi bind hai lần:** nếu socket đã bind (ví dụ `new DatagramSocket()`), gọi `bind(...)` lần nữa sẽ dẫn đến `SocketException`. Nếu muốn chọn endpoint sau khi cấu hình option như `SO_REUSEADDR`, hãy **tạo unbound** bằng `new DatagramSocket((SocketAddress) null)` trước.

### Bind có thể thất bại vì sao?

Những nguyên nhân thực tế:

- Cổng đang bị socket khác chiếm theo quy tắc địa chỉ/port và socket options của OS.
- IP yêu cầu bind không gắn với giao diện mạng khả dụng tại máy.
- Tài nguyên socket hệ điều hành không đủ, hoặc chính sách bảo mật cấm bind cổng.
- Địa chỉ/cổng không hợp lệ, không tương thích IPv4/IPv6 hoặc không được runtime hỗ trợ.
- Socket đã bind hoặc đã đóng.

Bind thất bại nên được xử lý như một lỗi **điều kiện hệ thống/cấu hình**, không tự động gọi lại trên cùng socket đã có trạng thái không phù hợp hoặc chuyển sang cổng khác nếu dịch vụ cần một cổng cố định.

## 4. Chọn địa chỉ cục bộ: wildcard, loopback, IP của interface

### 4.1. Wildcard address: nhận trên nhiều giao diện phù hợp

Tạo:

```java
try (DatagramSocket server = new DatagramSocket(9000)) {
    System.out.println(server.isBound()); // true
}
```

`new DatagramSocket(9000)` bind **wildcard address** và cổng `9000`. Với IPv4, wildcard thường được biểu diễn là `0.0.0.0`; trên môi trường IPv6 hoặc dual-stack, cách hiển thị/cấu hình có thể khác.

Ý nghĩa: socket sẵn sàng nhận datagram gửi đến **các địa chỉ/giao diện mà OS và firewall cho phép** trên UDP port đó.

**Chú ý quan trọng:** wildcard address **không phải địa chỉ đích dùng để liên lạc từ xa**. Khi client cần gửi tới server ở máy thật, phải dùng **địa chỉ máy server có thể định tuyến tới được**, ví dụ IP LAN hoặc hostname đã được phân giải. Không gửi tới `0.0.0.0` rồi cho rằng đó là tên server.

### 4.2. Loopback: chỉ trong máy

```java
InetAddress loopback = InetAddress.getByName("127.0.0.1");
DatagramSocket server =
        new DatagramSocket(new InetSocketAddress(loopback, 9000));
```

Snippet này bind server vào **IPv4 loopback**, nên phù hợp với test cục bộ hoặc dịch vụ chỉ cần giao tiếp giữa các tiến trình cùng máy.

- `127.0.0.1` là địa chỉ loopback IPv4.
- `::1` là địa chỉ loopback IPv6 tương ứng nếu hệ thống hỗ trợ.
- `InetAddress.getLoopbackAddress()` có thể trả địa chỉ loopback theo cấu hình nền tảng; để tránh khác biệt IPv4/IPv6 khi chạy ví dụ, bài sử dụng rõ `127.0.0.1`.
- Client ở máy **khác** không thể dùng `127.0.0.1` để đến server của bạn: địa chỉ đó sẽ trỏ về chính máy client.

### 4.3. IP cụ thể của card mạng: giới hạn giao diện

Nếu máy có IP LAN được cấu hình, ví dụ `192.168.x.y`, ứng dụng có thể bind vào IP đó để giới hạn endpoint. Nhưng IP phải **thực sự được gán cục bộ**; viết một địa chỉ trong mã rồi mong bind thành công là không đủ.

Sơ đồ lựa chọn:

| Nhu cầu | Bind IP/port | Cẩn trọng |
| --- | --- | --- |
| Unit/integration test trên một máy | `127.0.0.1:0` | Tự chọn cổng, không cần cấu hình cổng cố định |
| Dịch vụ UDP cần nhận từ nhiều giao diện | Wildcard + cổng cấu hình | Kiểm soát firewall/ACL; không công khai ngoài chủ đích |
| Dịch vụ chỉ trên một network interface | IP cục bộ của interface + cổng | IP này phải đang tồn tại trên host |
| Client gửi request đến server | Thường bind port 0 ở phía client | Phải gửi tới **IP/port của server**, không tới wildcard cục bộ |
| Cần nhiều địa chỉ/port độc lập | Nhiều socket hoặc giải pháp NIO phù hợp | Tránh giả định một socket luôn thay thế tất cả endpoint |

**Bind một địa chỉ** còn mang ý nghĩa bảo mật về phạm vi lắng nghe, nhưng **không thay thế** xác thực, firewall, giới hạn nguồn hoặc bảo vệ payload UDP.

## 5. Cổng 0, ephemeral port và cổng dịch vụ cố định

Một port UDP là số từ `0` đến `65535`. Khi **bind**:

- `port=0`: đề nghị OS cấp **một cổng khả dụng** (*ephemeral/dynamic*).
- `port>0`: đề nghị bind **chính xác** port đó (nếu hợp lệ và khả dụng).
- `port<0` hoặc `port>65535`: tham số không hợp lệ, API báo `IllegalArgumentException`.

### Cổng 0 trong bind không phải cổng thực tế

```java
try (DatagramSocket socket = new DatagramSocket(0)) {
    int assigned = socket.getLocalPort();
    System.out.println(assigned > 0); // true nếu bind thành công
}
```

Gợi ý: cổng thực tế **có thể khác mỗi lần chạy**. Vì thế, trong test nên in `assigned > 0` hoặc dùng port vừa được cấp để điều hướng client thay vì hard-code một số cổng đoán trước.

### Client thường dùng cổng tự động

Khi client chỉ cần gửi request và nhận response:

```text
Client: 127.0.0.1:<ephemeral port>
       |
       | UDP request
       v
Server: 127.0.0.1:9000
       |
       | UDP response gửi về source IP:source port của request
       v
Client: 127.0.0.1:<same ephemeral port>
```

Server cần lấy **địa chỉ nguồn và cổng nguồn** thực tế của datagram vừa nhận qua `DatagramPacket.getAddress()` và `getPort()` (hoặc `getSocketAddress()`) để gửi reply về đúng endpoint.

### Không nên đoán rồi tự kiểm tra cổng rảnh

Kiểu code:

```java
// Chống chỉ định trong ứng dụng cần độ tin cậy:
if (isPortFree(9000)) {
    // Có một khoảng race trước khi bind.
    openSocket(9000);
}
```

Đây là **pseudocode**: `isPortFree` và `openSocket` không phải API Java SE như viết ở trên. Kiểm tra “cổng rảnh” trước rồi mới bind luôn có nguy cơ *time-of-check-to-time-of-use race*: tiến trình khác có thể chiếm cổng ở giữa. Hãy **bind trực tiếp** và xử lý `SocketException`; khi không cần cổng cố định, dùng `0` để OS cấp.

## 6. Ví dụ hoàn chỉnh: UDP loopback request/reply và vòng đời socket

Ví dụ này sử dụng hai `DatagramSocket` trên cùng một tiến trình:

- **Receiver/server:** tạo unbound, bind thủ công vào `127.0.0.1:0`.
- **Sender/client:** tạo và bind vào `127.0.0.1:0`.
- Client gửi `"ping"`, server nhận, lấy source IP/port rồi gửi `"pong"`.
- Client nhận reply và kiểm tra server source port.
- Socket được đóng bằng **try-with-resources**; in trạng thái sau khi đóng.

### 6.1. Tệp `UdpBindLifecycleDemo.java`

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpBindLifecycleDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByName("127.0.0.1");

        // Truyền SocketAddress null: tạo socket CHƯA bind.
        DatagramSocket receiver =
                new DatagramSocket((SocketAddress) null);

        try (receiver) {
            System.out.println("before.bound=" + receiver.isBound());
            System.out.println("before.port=" + receiver.getLocalPort());
            System.out.println("before.endpointNull="
                    + (receiver.getLocalSocketAddress() == null));

            // Port 0: OS cấp một ephemeral port thực tế.
            receiver.bind(new InetSocketAddress(loopback, 0));
            receiver.setSoTimeout(2000);

            int serverPort = receiver.getLocalPort();
            System.out.println("after.bound=" + receiver.isBound());
            System.out.println("after.loopback="
                    + receiver.getLocalAddress().isLoopbackAddress());
            System.out.println("after.portAssigned="
                    + (serverPort > 0));

            try (DatagramSocket sender =
                    new DatagramSocket(
                            new InetSocketAddress(loopback, 0))) {
                sender.setSoTimeout(2000);
                System.out.println("client.bound=" + sender.isBound());

                byte[] ping = "ping".getBytes(StandardCharsets.UTF_8);
                DatagramPacket request = new DatagramPacket(
                        ping, ping.length,
                        new InetSocketAddress(loopback, serverPort));
                sender.send(request);

                // Bộ đệm nhận và DatagramPacket dùng CHỈ cho 1 lần nhận.
                byte[] requestBuffer = new byte[128];
                DatagramPacket incoming = new DatagramPacket(
                        requestBuffer, requestBuffer.length);
                receiver.receive(incoming);

                String requestText = new String(
                        incoming.getData(), incoming.getOffset(),
                        incoming.getLength(), StandardCharsets.UTF_8);
                System.out.println("server.received=" + requestText);
                System.out.println("server.sourceIsClient="
                        + (incoming.getPort() == sender.getLocalPort()));

                // Phản hồi về source endpoint thực tế của datagram.
                byte[] pong = "pong".getBytes(StandardCharsets.UTF_8);
                DatagramPacket reply = new DatagramPacket(
                        pong, pong.length, incoming.getSocketAddress());
                receiver.send(reply);

                byte[] replyBuffer = new byte[128];
                DatagramPacket receivedReply = new DatagramPacket(
                        replyBuffer, replyBuffer.length);
                sender.receive(receivedReply);
                String replyText = new String(
                        receivedReply.getData(),
                        receivedReply.getOffset(),
                        receivedReply.getLength(),
                        StandardCharsets.UTF_8);
                System.out.println("client.received=" + replyText);
                System.out.println("client.sourceIsServer="
                        + (receivedReply.getPort() == serverPort));
            }
        }

        System.out.println("closed=" + receiver.isClosed());
        System.out.println("boundHistory=" + receiver.isBound());
        System.out.println("closed.port=" + receiver.getLocalPort());
        System.out.println("closed.endpointNull="
                + (receiver.getLocalSocketAddress() == null));
    }
}
```

### 6.2. Biên dịch và chạy

Lưu đúng tên `UdpBindLifecycleDemo.java`. Sử dụng **JDK 17+**, không cần thư viện ngoài, không cần Internet và không cần mở cổng public:

```bash
javac -encoding UTF-8 UdpBindLifecycleDemo.java
java UdpBindLifecycleDemo
```

**Stdout dự kiến trên máy có IPv4 loopback hoạt động và cho phép UDP nội bộ:**

```text
before.bound=false
before.port=0
before.endpointNull=true
after.bound=true
after.loopback=true
after.portAssigned=true
client.bound=true
server.received=ping
server.sourceIsClient=true
client.received=pong
client.sourceIsServer=true
closed=true
boundHistory=true
closed.port=-1
closed.endpointNull=true
```

**Lưu ý điều kiện môi trường:** Socket được gắn với địa chỉ loopback, cả hai đầu ở cùng tiến trình và gửi packet trước khi gọi `receive`. Trên hệ điều hành bình thường, đầu ra trên có thể tái lập. Nếu firewall/chính sách sandbox chặn UDP loopback, một lời gọi có thể lỗi hoặc timeout: đó là hạn chế môi trường, không có nghĩa API tự bảo đảm giao packet.

### 6.3. Giải thích trạng thái

**Trước bind:**

- `new DatagramSocket((SocketAddress) null)` tạo socket chưa bound.
- `receiver.isBound()` là `false`.
- `receiver.getLocalPort()` trả `0` khi chưa bind.
- `receiver.getLocalSocketAddress()` trả `null` khi chưa bind.

**Sau bind:**

- `receiver.bind(new InetSocketAddress(loopback, 0))` cấp cổng động, nên `isBound()==true`.
- `serverPort > 0` vì OS đã chọn port thật; chương trình không giả định con số cụ thể.
- `getLocalAddress().isLoopbackAddress()` là `true` khi bind đúng `127.0.0.1`.
- Client cũng bind cổng động và nhận được response đúng địa chỉ/cổng nguồn.

**Sau close:**

- `receiver.isClosed()` là `true`.
- `receiver.isBound()` vẫn là **`true`**: API lưu **lịch sử rằng socket từng bind thành công**, không có nghĩa endpoint vẫn đang chiếm dụng.
- `receiver.getLocalPort()` trả **`-1`** khi socket đã đóng (lưu ý: khác với `java.net.Socket` của TCP).
- `receiver.getLocalSocketAddress()` trả `null` sau khi đóng.

**Đừng dùng `isBound()==true` làm bằng chứng socket vẫn có thể nhận packet.** Muốn kiểm tra trạng thái phục vụ, cần xem **`!isClosed()`** cùng với điều kiện bind/cấu hình phù hợp.

### 6.4. Bài học từ request/reply

- Datagrams được gửi tới **remote address/port** nằm trong `DatagramPacket`.
- Receiver lấy bytes thực nhận bằng `getData()` + `getOffset()` + **`getLength()`**, không dùng toàn bộ capacity 128 byte để tạo `String`.
- `incoming.getSocketAddress()` trả **endpoint nguồn**, tiện để tạo packet reply.
- Reply trở về cổng động của client. Client không cần biết trước số cổng sẽ được OS cấp.
- Sử dụng `setSoTimeout(2000)` để tránh một lần `receive` chờ mãi.
- Try-with-resources đóng socket kể cả khi có exception trong khối.

## 7. `bind(...)` khác `connect(...)`: hai trạng thái độc lập

Với UDP, **bind** nói về **phía cục bộ**. `connect` nói về **peer từ xa** được liên kết với socket để gửi/nhận có chọn lọc.

| Thao tác | Câu hỏi nó giải quyết | Tác dụng |
| --- | --- | --- |
| `socket.bind(localSocketAddress)` | Socket dùng IP/cổng **cục bộ** nào? | Gắn endpoint cục bộ |
| `socket.connect(remoteAddress)` | Socket sẽ giao tiếp với **remote peer** nào? | Liên kết peer UDP; không phải TCP handshake |
| `socket.disconnect()` | Bỏ liên kết remote peer? | Không tự đóng socket, không unbind endpoint cục bộ |
| `socket.close()` | Ngừng sử dụng socket và giải phóng tài nguyên? | Đóng endpoint, đánh thức receive đang block bằng lỗi |

`DatagramSocket` **mặc định chưa connected**, dù đã bound.

### Connect UDP không cần server đang tồn tại

```java
InetAddress loopback = InetAddress.getByName("127.0.0.1");
try (DatagramSocket client = new DatagramSocket(0)) {
    client.connect(new InetSocketAddress(loopback, 9000));
    System.out.println(client.isConnected()); // true nếu connect thành công
}
```

Đây là snippet minh họa. `isConnected()==true` chỉ cho biết socket **đã gắn peer**; nó **không xác nhận** có ứng dụng server đang lắng nghe UDP port 9000 hoặc sẽ phản hồi.

**Khi connected:**

- Socket thường chỉ nhận các datagram từ peer đã chọn; các datagram từ nguồn khác không được chuyển cho ứng dụng theo quy tắc connected socket.
- Khi gửi, `DatagramPacket` cần phù hợp remote endpoint; nếu cung cấp destination khác peer đã connect, `send` sẽ báo lỗi.
- `getInetAddress()` và `getPort()` nói về **remote peer**; `getLocalAddress()` và `getLocalPort()` nói về **local endpoint**.
- Nếu socket chưa bind mà được connect, API tự bind một local endpoint được hệ thống chọn trước khi liên kết.
- Một số lỗi mạng như ICMP Destination Unreachable có thể được phản ánh bằng `PortUnreachableException` ở send/receive, **nhưng không bảo đảm luôn có ngoại lệ**.

**Khi disconnect:**

```java
client.disconnect();
System.out.println(client.isConnected()); // false nếu disconnect thành công
```

Đây là snippet với `client` còn mở, đã connected. `disconnect()` **không đóng** socket và không trả endpoint cục bộ về trạng thái unbound. Nếu disconnect gặp lỗi hệ điều hành, JDK hiện đại có thể báo `UncheckedIOException`; khi trạng thái không còn xác định, nên đóng socket.

### Đừng “connect UDP” để chữa lỗi bind

Một socket bind sai IP/cổng sẽ không tự được sửa chỉ bằng `connect`. Hai quyết định phải rõ ràng:

```text
LOCAL ENDPOINT                    REMOTE ENDPOINT
bind(127.0.0.1, 0)                connect(127.0.0.1, 9000)
             |                             |
             v                             v
      OS chọn source port             peer mặc định
```

Khi phân tích lỗi mạng, luôn log cả **local** và **remote endpoint** (không log payload nhạy cảm).

## 8. Vòng đời socket: NEW → UNBOUND/BOUND → ACTIVE → CLOSED

Hai lối tạo thường gặp:

```text
DatagramSocket((SocketAddress) null)
           |
           v
        UNBOUND
           |
           | bind(...)
           v
         BOUND ----> send/receive <----> optional connect/disconnect
           |
           | close()
           v
         CLOSED

DatagramSocket() / DatagramSocket(0) / DatagramSocket(port)
           |
           v
         BOUND ----> send/receive <----> optional connect/disconnect
           |
           | close()
           v
         CLOSED
```

**Ý nghĩa từng trạng thái:**

- **UNBOUND:** object đã tồn tại nhưng chưa được OS gán endpoint cục bộ. Nếu gọi `send` hoặc `connect` khi chưa bind, `DatagramSocket` có thể tự bind theo quy tắc API. Vì vậy hãy chủ động bind khi cần kiểm soát địa chỉ/cổng.
- **BOUND:** có local endpoint; một số thông tin như cổng có thể đọc được. Bản thân bind **không** chứng minh datagram sẽ tới đích.
- **CONNECTED (tùy chọn):** socket đã bind hoặc tự bind và gắn remote peer; vẫn là UDP, không có stream đáng tin cậy.
- **CLOSED:** tài nguyên socket đã được đóng. Không thể dùng tiếp cho send/receive/bind. Muốn mở lại, tạo **`DatagramSocket` mới**.

Java `DatagramSocket` triển khai `Closeable` và `AutoCloseable`, nên có thể dùng:

```java
try (DatagramSocket socket = new DatagramSocket(0)) {
    // Sử dụng endpoint UDP.
} // close() tự được gọi kể cả khi có exception.
```

**Không phụ thuộc garbage collector** để đóng socket đúng lúc. GC không phải cơ chế kiểm soát vòng đời tài nguyên I/O cho ứng dụng. Với máy chủ sống lâu, quản lý `DatagramSocket` bằng lifecycle của service và đóng ở shutdown hook/service stop theo chính sách.

### Gọi close khi thread khác đang receive

Theo API hiện hành, nếu một thread đang bị chặn ở `socket.receive(packet)` mà thread khác gọi `socket.close()`, lời gọi receive bị giải phóng bằng **`SocketException`**. Đây là một cơ chế kết thúc receive loop khi dừng service.

Pseudo-code:

```java
while (!socket.isClosed()) {
    try {
        DatagramPacket packet = new DatagramPacket(
                new byte[2048], 2048);
        socket.receive(packet);
        processPacket(packet);
    } catch (java.net.SocketException ex) {
        if (socket.isClosed()) {
            break; // Shutdown có chủ đích.
        }
        throw ex;
    }
}
```

Đây là **snippet**, cần biến `socket` và hàm xử lý `processPacket` trong một lớp/service, không phải chương trình độc lập. `SocketException` không chỉ xuất hiện vì close: nếu socket **chưa** đóng mà nhận lỗi, cần xử lý/log và áp dụng chính sách retry hoặc dừng phù hợp.

**Không dùng `Thread.stop()`, finalizer hoặc spin-loop chờ socket “tự hết”** để quản lý shutdown. Chọn đóng socket từ một luồng điều phối rõ ràng, hoặc dùng timeout để vòng lặp có cơ hội kiểm tra cờ dừng.

## 9. Timeout và khả năng dừng hoạt động an toàn

Mặc định `receive(...)` có thể chờ lâu vô hạn khi không có datagram. Dùng:

```java
socket.setSoTimeout(2000); // 2000 milliseconds
```

Với socket đã mở, API cho phép đặt giới hạn chờ cho hoạt động nhận. Nếu quá thời gian, `receive` ném `SocketTimeoutException` nhưng **socket vẫn còn hợp lệ** và có thể tiếp tục nhận sau đó.

```java
try {
    socket.receive(packet);
    // Xử lý một datagram.
} catch (java.net.SocketTimeoutException ex) {
    // Không có datagram trong giới hạn chờ; socket vẫn mở.
}
```

Hai snippet giả định `socket`/`packet` hợp lệ và nằm trong method xử lý checked exceptions. Không cần tạo socket mới sau mỗi lần timeout.

Cần nhớ:

- `setSoTimeout(0)`: tắt giới hạn timeout, có thể chờ vô hạn.
- `setSoTimeout(>0)`: timeout theo **mili-giây**, phải cấu hình **trước khi vào lệnh receive blocking**.
- Giá trị timeout âm: `IllegalArgumentException`.
- `SocketTimeoutException` và `SocketException` do `close()` là **hai tình huống khác nhau**.
- Timeout chỉ nói "không nhận được trong thời hạn"; **không chứng minh** peer đã ngừng hoạt động hoặc datagram không được gửi.
- Cần thiết kế policy retry/backoff và idempotency nếu ứng dụng sử dụng UDP trên mạng không đáng tin cậy.

### Vì sao không giả định timeout là kết nối đã mất?

UDP không giữ kết nối phiên theo kiểu TCP. Không có datagram trong 2 giây có thể vì sender chưa gửi, firewall lọc, datagram mất trên đường, hệ thống bận hoặc buffer OS đã đầy. Quyết định đánh dấu client offline phải dựa trên **logic giao thức ở tầng ứng dụng**, không chỉ một timeout nhận đơn lẻ.

## 10. `DatagramPacket`: độ dài thực nhận, buffer và giới hạn thông điệp

`DatagramPacket` nhận vào một **mảng byte buffer** do ứng dụng cung cấp:

```java
byte[] buffer = new byte[2048];
DatagramPacket packet =
        new DatagramPacket(buffer, buffer.length);
socket.receive(packet);
```

Đây là snippet với `socket` đã bound và xử lý `IOException` bên ngoài.

**Đừng chuyển toàn bộ `buffer` thành chuỗi** vì dung lượng buffer có thể lớn hơn nội dung vừa nhận.

Sai:

```java
String wrong = new String(buffer, StandardCharsets.UTF_8);
```

Đúng:

```java
String value = new String(
        packet.getData(),
        packet.getOffset(),
        packet.getLength(),
        StandardCharsets.UTF_8);
```

Trong đó `getLength()` sau receive là **số bytes thực nhận được vào buffer**, không phải capacity. `getOffset()` có thể khác 0 nếu packet được tạo với vùng dữ liệu bắt đầu tại một offset.

### Packet quá lớn so với buffer

Nếu datagram đến có payload lớn hơn phần buffer khả dụng, phần dữ liệu ngoài buffer có thể bị **cắt/truncate** theo API; không có bảo đảm rằng chương trình nhận được toàn bộ message. Vì vậy:

- Chọn buffer theo **kích thước tối đa giao thức thực sự cho phép**.
- Có thể kiểm tra `packet.getLength()` để xem bytes đã nhận, nhưng chỉ nhìn con số bằng kích thước buffer **không luôn phân biệt được** packet vừa khít hay đã bị cắt.
- Với ứng dụng cần dữ liệu lớn, thiết kế **message framing, validation, chunking/reassembly** ở tầng ứng dụng hoặc chọn giao thức khác phù hợp.
- Tránh gửi những UDP datagram lớn gây fragmentation; kích thước MTU/path và môi trường mạng rất khác nhau. Không giả định payload UDP tối đa về mặt lý thuyết sẽ luôn truyền được.

### Tái sử dụng `DatagramPacket` để receive nhiều lần

Sau `receive`, `DatagramPacket` có `length` của datagram vừa nhận. Nếu tái sử dụng **cùng đối tượng**, cần đặt lại vùng nhận theo capacity mong muốn, ví dụ:

```java
byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

while (running) {
    packet.setLength(buffer.length); // Khôi phục kích thước nhận.
    socket.receive(packet);
    handleBytes(packet.getData(),
            packet.getOffset(), packet.getLength());
}
```

Đây là snippet với `running`, `socket` và `handleBytes` được ứng dụng định nghĩa, **không** phải chương trình độc lập. Nếu không reset, một implementation có thể chỉ nhận theo `length` còn lại từ packet trước, dẫn tới dữ liệu bị cắt ngoài ý muốn.

Nếu thích code đơn giản và thông lượng không quá lớn, tạo một `DatagramPacket` mới cho mỗi lần receive như ở ví dụ hoàn chỉnh sẽ tránh nhầm lẫn hơn.

## 11. Port conflict, `SO_REUSEADDR` và các giới hạn của OS

Một cổng UDP cố định có thể không bind được vì **đã có một socket khác chiếm** theo chính sách nền tảng. Khi bind thất bại, thường nhận `SocketException` hoặc một subtype, kèm thông báo có thể là “Address already in use” hoặc thông điệp OS khác.

**Đừng** dựa vào một câu thông báo tiếng Anh chính xác để viết logic: thông điệp có thể khác theo Windows/Linux/macOS.

### `SO_REUSEADDR` có tác dụng gì?

`DatagramSocket.setReuseAddress(true)` cho phép các chế độ **tái sử dụng endpoint** theo những quy tắc mà OS/runtime hỗ trợ, thường gặp trong bài toán multicast hoặc một số topology socket. Tuy nhiên:

- **Không** bảo đảm nhiều socket có thể cùng bind một địa chỉ/cổng trên mọi nền tảng.
- Không thay thế chính sách chia tải, nhận datagram, firewall hay routing.
- Hiệu quả và hành vi sau khi đã bind có thể **phụ thuộc platform**.

Khi cần cấu hình trước bind:

```java
try (DatagramSocket socket =
        new DatagramSocket((SocketAddress) null)) {
    socket.setReuseAddress(true);
    socket.bind(new InetSocketAddress(9000));
}
```

Đây là snippet hợp lệ khi port 9000 khả dụng và platform hỗ trợ điều kiện cần; **không** giả định gọi `setReuseAddress` khiến việc bind luôn thành công.

### Không đồng nhất `SO_REUSEADDR` với `SO_REUSEPORT`

`SO_REUSEPORT` là socket option riêng trong các API/nền tảng hỗ trợ; ý nghĩa/khả năng có thể khác. Không dùng hai tên này thay nhau. Muốn dùng option không mặc định ở UDP production cần tra tài liệu của JDK và hệ điều hành mục tiêu, sau đó test trên chính môi trường triển khai.

### Tránh port cố định trong unit test

Nhiều bài test chạy song song có thể tranh chấp `9000` hoặc một số port cố định. Khi muốn test request/reply, dùng `bind(loopback, 0)`, đọc cổng được cấp rồi truyền chính xác cho peer, như phần 6. Chọn cổng `0` loại bỏ nhu cầu dự đoán/cố chiếm port, dù vẫn phải xử lý lỗi socket thực tế.

## 12. Lỗi thường gặp và chẩn đoán đúng

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `SocketException: Address already in use` | Port/address đã bị sử dụng theo luật OS | Chọn port khác nếu giao thức cho phép; hoặc dừng dịch vụ đang chiếm |
| `SocketException: Cannot assign requested address` | Bind vào IP không có trên host | Chọn IP thực của interface hoặc wildcard/loopback đúng mục đích |
| `IllegalArgumentException` khi tạo endpoint | Port âm/ngoài `0..65535` hoặc loại `SocketAddress` không hỗ trợ | Kiểm tra input trước khi bind |
| `bind` thất bại vì already bound | Dùng `new DatagramSocket()` rồi gọi `bind` lần nữa | Tạo unbound bằng `new DatagramSocket((SocketAddress) null)` |
| `getLocalPort()==0` | Socket **chưa bind** | Bind trước khi đọc; cổng 0 lúc bind được đổi thành cổng thực |
| `getLocalPort()==-1` | DatagramSocket đã đóng | Tạo socket mới; không dùng lại socket cũ |
| `isBound()==true` sau `close` | API ghi nhớ trạng thái đã bind | Kết hợp `isClosed()`; không coi là socket còn hoạt động |
| Client ở máy khác không gửi tới server được | Server chỉ bind `127.0.0.1` | Bind IP LAN/wildcard phù hợp và cấu hình firewall |
| Client gửi tới `0.0.0.0` | Nhầm bind wildcard với địa chỉ đích server | Dùng server IP/hostname có thể định tuyến |
| `receive` chờ mãi | Không có packet, sai port, firewall lọc, timeout chưa cấu hình | `setSoTimeout`, log local endpoint và kiểm tra network |
| `SocketTimeoutException` | Không có datagram trong thời hạn | Xử lý retry/timeout ở application; socket vẫn dùng được |
| `SocketException` khi service stop | Thread khác gọi `close` | Phân biệt shutdown chủ đích và lỗi mạng |
| Chuỗi nhận có ký tự `\u0000` cuối | Đọc cả buffer thay vì bytes thực | Dùng `getOffset()` và `getLength()` |
| Datagram dài bị cắt | Receive buffer/packet length quá nhỏ | Thiết kế kích thước thông điệp và giới hạn nhận |
| Packet thứ hai bị cắt ngắn khi dùng cùng `DatagramPacket` | Không reset `setLength` trước receive lần tiếp theo | `packet.setLength(buffer.length)` |
| UDP `connect` thành công nhưng không có reply | UDP connect không xác thực server tồn tại | Kiểm tra destination port, packet path và logic ứng dụng |
| Máy nhận không biết gửi reply đi đâu | Không dùng source IP/port của packet nhận | Lấy `packet.getSocketAddress()` |
| `send` thành công nhưng receiver không thấy dữ liệu | UDP không đảm bảo delivery | Nếu cần, thêm sequence ID, ACK, retry, dedup hoặc dùng giao thức tin cậy |
| Không mở lại được socket đã `close` | `DatagramSocket` không có API reopen cùng instance | Tạo object mới, bind lại theo policy |
| Bật reuse nhưng vẫn lỗi bind | `SO_REUSEADDR` phụ thuộc OS và thứ tự thiết lập | Test trên platform; set option trước bind |

### Về `PortUnreachableException`

Với socket UDP đã `connect` vào một peer không thể tới, OS có thể nhận ICMP unreachable. Một số lần `send`/`receive` sau đó **có thể** ném `PortUnreachableException`. Nhưng API **không bảo đảm** sẽ có ngoại lệ, kể cả khi peer không tồn tại.

Vì vậy không viết logic: “Không có `PortUnreachableException` nghĩa là server đã nhận và xử lý”. Muốn biết nhận thành công, giao thức ứng dụng phải có **ACK hoặc phản hồi** được kiểm tra phù hợp.

## 13. Lối thiết kế server UDP hiện đại và quản lý vòng đời

Một UDP server thực tế nên có chính sách rõ cho:

1. **Bind endpoint:** IP và port từ cấu hình đáng tin, xác định rõ chỉ local hay public.
2. **Startup:** mở socket, cấu hình options trước bind nếu cần, thực hiện bind; chỉ thông báo service READY khi bind thật sự thành công.
3. **Receive loop:** đọc datagram, kiểm tra size/format/rate limit và định tuyến theo nguồn/nghiệp vụ.
4. **Response:** phản hồi tới đúng source endpoint và request ID nếu giao thức cần phân biệt nhiều request.
5. **Timeout và shutdown:** `setSoTimeout` hoặc đóng socket từ thread điều phối; xử lý SocketException khi đang receive một cách tường minh.
6. **Observability:** metric về số datagram, bytes, timeout, lỗi parse, drop, bind failure; tránh ghi payload hoặc secret nhạy cảm ra log.
7. **Security:** không tin nội dung hoặc địa chỉ nguồn UDP như xác thực danh tính; cần authentication ở tầng ứng dụng nếu phù hợp.
8. **Resource cleanup:** gọi `close` trong shutdown và khi startup thất bại; không dựa vào GC.

Một service có nhiều client vẫn có thể xử lý qua **một socket UDP bind cổng server**, không có `accept`. Muốn scale, cân nhắc thread model, bounded queues, batching, xử lý song song và `DatagramChannel` theo khối lượng công việc; nhưng vẫn phải hiểu **địa chỉ/cổng cục bộ** và vòng đời socket là quyết định nền tảng.

### `DatagramChannel` có thay thế hoàn toàn `DatagramSocket` không?

`java.nio.channels.DatagramChannel` là API NIO hiện hành cho UDP, cho phép sử dụng buffer/channel và có thể cấu hình non-blocking/selector theo mục tiêu. Nó phù hợp khi cần mô hình I/O có khả năng quản lý nhiều endpoint/luồng sự kiện hoặc tích hợp với kiến trúc NIO.

Tuy nhiên:

- `DatagramSocket` vẫn là API **hiện hành**, không bị coi là legacy chỉ vì có `DatagramChannel`.
- `DatagramChannel.bind(...)` cũng là quyết định về **local endpoint**.
- API, chế độ blocking, cấu trúc buffer và cách xử lý event khác với `DatagramSocket`; không pha trộn mã hai API mà không kiểm soát trạng thái.
- `DatagramSocket.getChannel()` có thể trả `null` nếu socket không được tạo từ `DatagramChannel`.

Với bài học về bind, port và lifecycle cơ bản, `DatagramSocket` là lựa chọn dễ đọc, đầy đủ và vẫn áp dụng ở hiện tại.

## 14. Hai bài tập ngắn có code minh họa

### Bài tập A: đọc cổng được cấp thay vì hard-code

**Đề:** Viết chương trình bind cổng UDP tự chọn trên loopback, in hai mệnh đề boolean: đã bound và port hợp lệ. Đóng socket sau khi in.

**Lời giải runnable — tệp `UdpPortDemo.java`:**

```java
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;

public class UdpPortDemo {
    public static void main(String[] args) throws Exception {
        try (DatagramSocket socket = new DatagramSocket(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0))) {
            System.out.println("bound=" + socket.isBound());
            System.out.println("portAssigned="
                    + (socket.getLocalPort() > 0));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 UdpPortDemo.java
java UdpPortDemo
```

Stdout khi bind thành công:

```text
bound=true
portAssigned=true
```

**Giải thích:** `getLocalPort()` trả port động thực tế. In boolean giúp test không phụ thuộc vào số port mà OS cấp.

### Bài tập B: phân biệt timeout với close

**Đề:** Một UDP socket chờ datagram trong 100 ms nhưng không có ai gửi. Đề xuất quy trình và nêu điều kiện xử lý.

**Lời giải hướng dẫn:**

```java
try (DatagramSocket socket =
        new DatagramSocket(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0))) {
    socket.setSoTimeout(100);
    DatagramPacket packet = new DatagramPacket(new byte[16], 16);
    try {
        socket.receive(packet);
        System.out.println("received");
    } catch (java.net.SocketTimeoutException timeout) {
        System.out.println("timed out, still open="
                + !socket.isClosed());
    }
}
```

Đây là snippet có thể đặt trong `main` và khai báo `throws Exception` hoặc xử lý các checked exception; cần import `java.net.*`.

**Nếu không có datagram đến**, output:

```text
timed out, still open=true
```

Trong môi trường thực tế, có thể có packet đến trước timeout; vì vậy bài này **không** đảm bảo luôn in dòng trên khi chạy trên bất kỳ máy nào. Điều cần học là: **timeout không đóng socket**, còn `close()` sẽ khiến những thao tác gửi/nhận tiếp theo thất bại.

## 15. Câu hỏi tự kiểm tra và đáp án

**1.** `new DatagramSocket()` có phải socket chưa bind không?

**Đáp án:** Không. Constructor không tham số đã bind vào wildcard address và một cổng khả dụng.

**2.** `new DatagramSocket((SocketAddress) null)` khác gì `new DatagramSocket(0)`?

**Đáp án:** Dạng `null` tạo socket **chưa bind**; dạng `0` bind ngay, yêu cầu OS cấp cổng động.

**3.** Khi muốn chỉ nhận UDP trên máy hiện tại qua IPv4, nên bind vào đâu?

**Đáp án:** `127.0.0.1` cùng cổng cần thiết hoặc port 0 cho test. Client máy khác không thể đến qua loopback của server.

**4.** Vì sao không dùng `0.0.0.0` làm địa chỉ đích thông thường của client?

**Đáp án:** `0.0.0.0` là wildcard/unspecified address để bind, không phải địa chỉ server đích được định tuyến tới.

**5.** Sau bind cổng 0, lấy cổng thật ở đâu?

**Đáp án:** `socket.getLocalPort()` khi socket đã bound và còn mở; không giả định nó bằng 0.

**6.** Vì sao `socket.isBound()` có thể vẫn `true` sau `socket.close()`?

**Đáp án:** API giữ trạng thái từng bind thành công. Kiểm tra `isClosed()` để biết socket đã đóng hay chưa.

**7.** `getLocalPort()` của `DatagramSocket` trả gì khi chưa bind và khi đã close?

**Đáp án:** Chưa bind: `0`. Đã đóng: `-1` theo Java SE DatagramSocket API.

**8.** Nếu cần server trả lời đúng client, lấy địa chỉ nào?

**Đáp án:** `getAddress()` và `getPort()` hoặc `getSocketAddress()` của `DatagramPacket` nhận được. Không dùng local endpoint của server làm destination của reply.

**9.** `DatagramSocket.connect(...)` có xác thực remote server đã online chưa?

**Đáp án:** Không. UDP connect không có handshake kiểu TCP; nó chỉ cấu hình peer, có thể lọc nguồn packet.

**10.** Nếu `receive` ném `SocketTimeoutException`, có phải socket đã đóng?

**Đáp án:** Không. Socket vẫn có thể sử dụng; handler có thể tiếp tục nhận sau timeout nếu phù hợp.

**11.** Vì sao cần `packet.getLength()` khi giải mã bytes nhận?

**Đáp án:** Buffer có thể lớn hơn số bytes của datagram. Dùng toàn bộ buffer sẽ đọc cả phần dư.

**12.** Vì sao tái sử dụng `DatagramPacket` cần `packet.setLength(buffer.length)`?

**Đáp án:** Sau lần receive trước, length đã đổi thành số bytes thực nhận; cần khôi phục capacity để lần nhận tiếp theo không bị giới hạn sai.

**13.** Bind cổng cố định bị `SocketException` thì nên làm gì?

**Đáp án:** Kiểm tra port/address có bị chiếm, cấu hình IP, quyền OS và chính sách. Chỉ đổi cổng nếu giao thức cho phép; nếu port bắt buộc thì báo startup failure.

**14.** Có thể dùng `SO_REUSEADDR` như bảo đảm rằng mọi hệ điều hành chia sẻ một UDP port thành công?

**Đáp án:** Không. Hành vi và khả năng hỗ trợ phụ thuộc nền tảng và thời điểm set option.

**15.** Nếu `send` trả bình thường, chắc chắn receiver đã xử lý packet chưa?

**Đáp án:** Chưa. UDP không bảo đảm delivery/ordering/dedup; muốn xác nhận cần cơ chế phản hồi ở tầng ứng dụng.

**16.** Socket UDP đã close có thể gọi bind lại cùng object không?

**Đáp án:** Không. Phải tạo `DatagramSocket` mới.

### Checklist trước khi triển khai

- [ ] Tôi phân biệt **local bind endpoint** và **remote destination**.
- [ ] Tôi biết constructor nào **bind ngay** và constructor nào tạo **unbound**.
- [ ] Tôi sử dụng port `0` cho tình huống cần OS chọn cổng, và đọc lại `getLocalPort()`.
- [ ] Tôi chọn đúng **loopback**, **wildcard** hoặc IP cụ thể của network interface.
- [ ] Tôi không coi UDP `connect` như TCP handshake hay bảo đảm có server.
- [ ] Tôi cấu hình `SO_TIMEOUT`/shutdown và xử lý `SocketTimeoutException` khác `SocketException`.
- [ ] Tôi dùng `DatagramPacket.getOffset()/getLength()` khi đọc bytes.
- [ ] Tôi hiểu UDP có thể mất, lặp, đảo thứ tự hoặc cắt datagram quá buffer.
- [ ] Tôi không giả định `SO_REUSEADDR` luôn cho phép chia sẻ cổng.
- [ ] Tôi dùng try-with-resources/`close()`, không dựa vào GC để giải phóng socket.
- [ ] Tôi biết `isBound` giữ lịch sử từng bind nhưng `isClosed` cho biết socket đã đóng.
- [ ] Tôi có thể biên dịch/chạy `UdpBindLifecycleDemo.java` và giải thích đúng stdout.

## 16. Tài liệu chính thức, còn áp dụng

1. [Java SE 25 — `DatagramSocket`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): constructors, `bind`, `connect`, `disconnect`, `isBound`, `isClosed`, `getLocalPort`, `getLocalSocketAddress`, `setSoTimeout`, `close`.
2. [Java SE 25 — `DatagramPacket`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): `getData`, `getOffset`, `getLength`, `setLength`, địa chỉ nguồn/đích.
3. [Java SE 25 — `InetSocketAddress`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetSocketAddress.html): endpoint địa chỉ IP và port.
4. [Java SE 25 — `InetAddress`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): địa chỉ IPv4/IPv6, loopback/wildcard và phân giải tên.
5. [Java SE 25 — `DatagramChannel`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): UDP theo NIO, bind và I/O theo channel.
6. [Java SE 25 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_REUSEADDR`, buffer và các tùy chọn mạng hiện hành.

**Tổng kết:** `bind` chọn **IP và UDP port cục bộ** của `DatagramSocket`; cổng `0` nhờ OS cấp port động, còn constructor nhận `null` cho phép tạo unbound để cấu hình rồi bind thủ công. `connect` chỉ gắn **remote peer**, không tạo kết nối UDP tin cậy. Trong quá trình sử dụng, đọc đúng bytes qua `DatagramPacket.getLength()`, đặt timeout theo nhu cầu và đóng socket bằng try-with-resources/`close()`. Sau close, `isBound()` vẫn có thể `true` vì ghi nhớ trạng thái đã bind, trong khi `isClosed()` là `true` và `getLocalPort()` của DatagramSocket là `-1`.