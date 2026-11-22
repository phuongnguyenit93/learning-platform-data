# connect, disconnect và lọc peer với UDP datagram trong Java 15+

## 1. Mục tiêu và phạm vi

UDP (*User Datagram Protocol*) là giao thức **hướng datagram**, **không thiết lập kết nối vận chuyển** như TCP. Mỗi datagram mang thông tin endpoint nguồn/đích và có thể đến, mất, lặp hoặc đảo thứ tự. Trong Java, bạn vẫn có thể gọi `DatagramSocket.connect(...)` hoặc `DatagramChannel.connect(...)`. Tên `connect` dễ gây hiểu lầm: đây là thao tác **chọn một peer IP + port cho socket cục bộ**, **không phải TCP handshake**, không xác minh bên kia đang tồn tại, không tạo luồng byte tin cậy, không tự mã hóa và không tự xác thực danh tính.

Bài học dưới nhóm **UDP và datagram** tập trung vào việc lựa chọn peer và thay đổi bộ lọc khi socket đang hoạt động:

1. Phân biệt `bind`, `connect`, `disconnect` và `close`.
2. Nêu chính xác cách `DatagramSocket` **lọc peer nhận** và **hạn chế đích gửi** khi đã connected.
3. Hiểu một peer được xác định bằng **địa chỉ IP và cổng UDP**, không chỉ hostname hoặc cổng.
4. Biết trạng thái socket sau `disconnect()`, những datagram đã đợi trong bộ đệm và lỗi thường gặp.
5. So sánh `DatagramSocket` với `java.nio.channels.DatagramChannel`, đặc biệt `read/write` chỉ dành cho channel đã connect.
6. Viết chương trình Java 15+ chạy trên **loopback**, chứng minh peer khác không được nhận khi connected nhưng được nhận sau disconnect.
7. Chọn chiến lược lọc peer và xác thực dữ liệu cho ứng dụng nhiều client mà không coi UDP connect là một cơ chế bảo mật.

Toàn bộ API được trình bày vẫn tồn tại trong Java hiện đại; không sử dụng `SecurityManager` như thiết kế bảo mật mới hay các API nội bộ/lỗi thời. Để chạy ứng dụng thực tế, hãy dùng JDK/JVM còn được nhà cung cấp hỗ trợ. Ví dụ có thể biên dịch với mức Java 15.

## 2. UDP socket và địa chỉ peer

Một UDP datagram có các thành phần định tuyến cơ bản:

- **Source IP** và **source UDP port**: nơi datagram được gửi từ, theo thông tin packet đã nhận.
- **Destination IP** và **destination UDP port**: endpoint mà datagram được gửi đến.
- **Payload bytes**: nội dung ứng dụng tự định nghĩa; UDP không gắn message ID, phiên đăng nhập hoặc bảo đảm tính hợp lệ cho ứng dụng.
- **Length**: datagram được nhận thành một đơn vị. Nó không phải một phần của một luồng vô hạn như TCP.

Trong Java, `InetAddress` biểu diễn địa chỉ IP, `InetSocketAddress` biểu diễn một endpoint **IP + port**, còn `DatagramPacket` chứa buffer dữ liệu và metadata endpoint gửi/nhận.

Ví dụ tạo một UDP socket lắng nghe trên loopback và yêu cầu hệ điều hành cấp **cổng tạm**:

```java
InetAddress loopback = InetAddress.getLoopbackAddress();
try (DatagramSocket socket = new DatagramSocket(0, loopback)) {
    int localPort = socket.getLocalPort();
    System.out.println("Bound to local UDP port " + localPort);
}
```

Đoạn này có thể đặt vào một `main` khai báo `throws Exception`, với import `java.net.*`. Cổng hệ điều hành chọn là **không cố định**, vì vậy không đặt số cổng ngẫu nhiên vào expected stdout. `DatagramSocket(0, loopback)` **bind** một endpoint cục bộ, chưa chọn peer từ xa.

**Bind trả lời:** “Socket này nhận datagram gửi tới địa chỉ/cổng cục bộ nào?”

**Connect trả lời:** “Trên socket UDP này, chỉ làm việc với peer từ xa IP/cổng nào?”

Đừng nhập nhằng **local port** với **remote port**. Sau `connect`, `getLocalPort()` vẫn là cổng local; `getPort()` là cổng của **remote peer**.

## 3. Bốn thao tác dễ nhầm

| Thao tác | Chức năng | Có TCP handshake không? | Có thể tiếp tục dùng socket không? |
| --- | --- | --- | --- |
| `bind(localAddress)` | Gắn socket vào IP/cổng **cục bộ** | Không | Có |
| `connect(remoteAddress)` | Gắn **remote peer IP + port**, lọc datagram nhận và giới hạn đích gửi | **Không** | Có |
| `disconnect()` | Xóa gắn kết peer, trở về trạng thái UDP **unconnected** | Không | **Có**, nếu không xảy ra lỗi và socket chưa đóng |
| `close()` | Đóng socket, giải phóng tài nguyên | Không | **Không**; muốn dùng tiếp phải tạo socket mới |

Đây là bảng ý nghĩa của **API DatagramSocket**, không phải vòng đời TCP. Dù method đặt tên `connect`, một socket UDP có thể `connect` tới cổng **không có process nào lắng nghe** mà lời gọi vẫn hoàn thành. Phản hồi ICMP lỗi đích không tới (*port unreachable*) nếu có có thể khiến thao tác gửi/nhận về sau ném `PortUnreachableException`, nhưng **không có bảo đảm** nhận được lỗi này.

### Trạng thái của `DatagramSocket`

| Trạng thái | `isBound()` | `isConnected()` | `getRemoteSocketAddress()` |
| --- | --- | --- | --- |
| Socket mới được bind nhưng chưa connect | `true` | `false` | `null` |
| Đã `connect` thành công | `true` | `true` | Endpoint của peer đã chọn |
| Đã `disconnect` thành công | `true` | `false` | `null` |
| Đã `close` | Có thể vẫn báo từng được bind | Có thể phản ánh trạng thái kết nối trước khi close, tùy API | Không dùng những cờ cũ thay cho `isClosed()` |

**Cảnh báo nhỏ:** Javadoc ghi `isBound()` và `isConnected()` có thể còn phản ánh trạng thái trước `close()`. Vì thế, nếu quan tâm socket còn dùng được không, kiểm tra `isClosed()`/quản lý lifecycle rõ ràng, đừng chỉ nhìn `isConnected()`.

## 4. `DatagramSocket.connect(...)`: chọn và lọc remote peer

Hai overload thường dùng:

```java
socket.connect(InetAddress remoteAddress, int remotePort);
socket.connect(new InetSocketAddress(remoteAddress, remotePort));
```

Đoạn minh họa giả định `socket`, `remoteAddress` và `remotePort` đã được chuẩn bị. Nếu chưa `bind`, gọi `connect` có thể khiến socket tự bind đến local endpoint mà hệ thống chọn.

Với socket UDP đã connected đến `192.0.2.10:5000` (địa chỉ trong khối minh họa dành cho tài liệu), Java chỉ cho trao đổi datagram với **endpoint ấy** trên socket đó:

- `receive(DatagramPacket)` chỉ trả các datagram phù hợp remote **IP và port** đã connect. Datagram từ `192.0.2.11:5000` hoặc `192.0.2.10:5001` không phải peer đã chọn.
- `send(DatagramPacket)` chỉ được gửi tới peer đã connect. Nếu packet chỉ định địa chỉ/cổng **khác** peer, Javadoc quy định có thể ném `IllegalArgumentException`.
- `isConnected()` trả `true`, `getInetAddress()` và `getPort()` phản ánh IP/port của peer; `getRemoteSocketAddress()` là endpoint remote.
- `connect` không tạo session có authentication, ACK, congestion control, retransmission hoặc message ordering. UDP vẫn là UDP.

**Lọc peer ở đây là điều kiện endpoint trên socket**, không phải đăng nhập thành công. Một datagram có source IP/port giống peer mong đợi vẫn không tự chứng minh danh tính ứng dụng; địa chỉ có thể bị giả mạo trong một số kịch bản, NAT có thể thay đổi endpoint, và payload có thể là dữ liệu chưa tin cậy.

### 4.1. Sender IP **và** sender port đều quan trọng

Giả sử hai process cùng host:

```text
Peer A: 127.0.0.1:41001
Peer B: 127.0.0.1:41002
Receiver: 127.0.0.1:42000
```

Nếu receiver connect tới `127.0.0.1:41001`, thì B **khác peer** dù có cùng IP `127.0.0.1`. Trong một ứng dụng NAT, nhiều client có thể xuất hiện cùng public IP nhưng khác source port; lọc theo IP đơn thuần dễ nhận nhầm người gửi.

Ngược lại, nếu bạn muốn một **server UDP nhiều client** cùng lắng nghe cổng `42000` thì connect server socket vào một peer cố định thường **không phù hợp**. Hãy để socket unconnected, đọc metadata từ packet, định tuyến request theo endpoint/client ID và áp dụng kiểm tra quyền trong **giao thức ứng dụng**.

### 4.2. Gửi packet khi đã connect

Dữ liệu gửi là **bytes**. Với socket đã connected, packet cần nhắm đúng peer. Mẫu dễ đọc:

```java
byte[] bytes = "ping".getBytes(StandardCharsets.UTF_8);
DatagramPacket packet = new DatagramPacket(
        bytes, bytes.length,
        new InetSocketAddress(remoteAddress, remotePort));
socket.send(packet);
```

Đây là mảnh mã minh họa, cần import `java.net.*`, `java.nio.charset.StandardCharsets` và có biến `remoteAddress`, `remotePort`, `socket` hợp lệ. Thao tác `send` có thể trả về **mà không đảm bảo datagram được peer nhận**. Không coi thành công của `send` như một ACK.

### 4.3. UDP connect tới multicast không giống peer unicast

Javadoc của `DatagramSocket` nêu rằng socket **connected tới địa chỉ multicast chỉ dùng để gửi packet**, không dùng như cách nhận multicast thông thường. Muốn làm multicast, phải thiết kế riêng theo API nhóm multicast và network interface phù hợp; không dùng `connect(multicastAddress, port)` làm phép lọc peer cho server nhận multicast.

Bài này dùng **unicast loopback** để minh họa đúng một remote peer.

## 5. `DatagramSocket.disconnect()`: bỏ bộ lọc nhưng **không đóng socket**

```java
socket.disconnect();
boolean unconnected = !socket.isConnected();
int unchangedLocalPort = socket.getLocalPort();
```

Đây là các câu lệnh minh họa. Sau `disconnect()` thành công, socket không còn gắn remote peer, nên bạn có thể:

- Gửi datagram đến **nhiều endpoint** khác nhau, bằng `DatagramPacket` mang địa chỉ/cổng đích phù hợp.
- Nhận datagram từ **các peer khác nhau** qua `receive()` trên cùng local endpoint.
- `connect()` lại với một peer mới nếu ứng dụng muốn chuyển sang connected mode.
- Tiếp tục dùng **local port** đã bind; `disconnect` không phải `close`, không cần xây lại socket chỉ vì muốn bỏ peer filter.

**Không dùng `disconnect` như cách “xóa hết mọi packet” hoặc “chặn packet cũ”**. Các datagram trong receive queue có thể đã bị lọc/bỏ khi connect; kết quả dữ liệu đợi trong buffer và các packet đến sát lúc thay trạng thái có thể phụ thuộc JVM/OS. Với thay peer ở runtime, định nghĩa rõ **ranh giới phiên và validation theo message ID/session ID**, tránh nhận nhầm response cũ sau khi filter được mở.

### 5.1. Trường hợp thay peer

Một workflow đơn giản cho client có thể là:

```text
UNCONNECTED
    |
    | connect(A)
    v
CONNECTED_TO_A  -- datagram nhận chỉ từ A; gửi chỉ tới A
    |
    | disconnect()
    v
UNCONNECTED
    |
    | connect(B)
    v
CONNECTED_TO_B  -- datagram nhận chỉ từ B; gửi chỉ tới B
    |
    | close()
    v
CLOSED
```

Đây là sơ đồ trạng thái **logic**, không bảo đảm kernel đã làm sạch mọi packet cũ ở đúng thời điểm chuyển. Nếu giao thức của bạn không chấp nhận bất kỳ response của phiên cũ nào, **đừng chỉ dựa vào connect/disconnect**: thêm generation/version/session token có xác thực ở tầng ứng dụng hoặc tạo socket khác tùy yêu cầu.

### 5.2. Nếu `disconnect()` thất bại

Ở JDK hiện đại, `DatagramSocket.disconnect()` có thể ném `UncheckedIOException` nếu không thể gỡ association và phục hồi trạng thái nhất quán. Javadoc khuyến nghị **đóng socket khi disconnect thất bại**, vì trạng thái kết nối sau lỗi có thể không xác định.

Tương tự, nếu `connect` lại tới peer mới nhưng thao tác thất bại, Javadoc có thể coi trạng thái sau lỗi **không xác định**. Đừng mặc nhiên tiếp tục gửi như thể vẫn connected tới peer trước. Đóng và tạo socket mới là phương án khôi phục dễ suy luận hơn khi cần trạng thái chính xác.

## 6. Lọc peer ảnh hưởng những datagram đang chờ thế nào?

Javadoc của `DatagramSocket.connect(...)` và `DatagramChannel.connect(...)` nêu rằng **các datagram đã nằm trong socket receive buffer nhưng chưa được nhận trước khi gọi connect có thể bị bỏ**.

Điều này kéo theo ba hệ quả quan trọng:

1. **Không bảo đảm các datagram đã xếp hàng trước connect còn nguyên.** Nếu muốn chuyển từ unconnected sang connected khi đang tải nặng, ứng dụng phải chấp nhận khả năng mất packet/thiết kế retry nếu cần.
2. **Không bảo đảm một packet từ peer khác gửi sát thời điểm connect sẽ được kiểm tra theo một “mốc thời gian ứng dụng” tùy ý.** Socket và kernel cùng có thể tham gia xử lý; không tự viết test đòi số packet bị drop chính xác trong một cuộc đua.
3. **Không nhận lại được packet đã bị loại** chỉ bằng cách gọi `disconnect`. Nếu lúc connected socket đã bỏ một datagram từ peer B, sau disconnect bạn chỉ có thể nhận **datagram B gửi mới**, không “hồi sinh” packet cũ.

Trong ví dụ hoàn chỉnh, chương trình **connect trước khi gửi**, sau đó cho peer B gửi packet, peer A gửi packet, rồi receiver nhận. Kết quả nhận được packet của A; sau `disconnect`, B gửi **một packet mới** và receiver nhận nó. Cách làm này tránh dựa vào packet đã tồn tại trong queue trước connect.

## 7. Ví dụ Java 15+ hoàn chỉnh: lọc peer A, loại peer B, rồi disconnect

Tạo file **`UdpPeerFilterDemo.java`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class UdpPeerFilterDemo {
    static void send(DatagramSocket source, InetAddress address, int port,
                     String text) throws Exception {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        DatagramPacket packet = new DatagramPacket(
                bytes, bytes.length, new InetSocketAddress(address, port));
        source.send(packet);
    }

    static String receive(DatagramSocket socket) throws Exception {
        byte[] buffer = new byte[128];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        socket.receive(packet);
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket receiver = new DatagramSocket(0, loopback);
             DatagramSocket allowedPeer = new DatagramSocket(0, loopback);
             DatagramSocket otherPeer = new DatagramSocket(0, loopback)) {

            receiver.setSoTimeout(2000);
            int receivingPort = receiver.getLocalPort();
            receiver.connect(new InetSocketAddress(
                    loopback, allowedPeer.getLocalPort()));

            System.out.println("connected=" + receiver.isConnected());
            System.out.println("peerPortMatches="
                    + (receiver.getPort() == allowedPeer.getLocalPort()));

            try {
                send(receiver, loopback, otherPeer.getLocalPort(), "wrong-dest");
                System.out.println("wrongDestinationRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("wrongDestinationRejected=true");
            }

            send(otherPeer, loopback, receivingPort, "from-other");
            send(allowedPeer, loopback, receivingPort, "from-allowed");

            String accepted = receive(receiver);
            System.out.println("whileConnected=" + accepted);

            receiver.disconnect();
            System.out.println("disconnected=" + !receiver.isConnected());
            System.out.println("remoteCleared="
                    + (receiver.getRemoteSocketAddress() == null));
            System.out.println("localPortPreserved="
                    + (receiver.getLocalPort() == receivingPort));

            send(otherPeer, loopback, receivingPort, "after-disconnect");
            System.out.println("afterDisconnect=" + receive(receiver));
        }
    }
}
```

### 7.1. Biên dịch/chạy

Dùng JDK hiện đại có compiler hỗ trợ `--release 15` (ví dụ JDK 21 hoặc JDK 24). Tại thư mục chứa file:

```bash
javac --release 15 -encoding UTF-8 UdpPeerFilterDemo.java
java UdpPeerFilterDemo
```

**Stdout mong đợi trong môi trường loopback UDP hoạt động bình thường:**

```text
connected=true
peerPortMatches=true
wrongDestinationRejected=true
whileConnected=from-allowed
disconnected=true
remoteCleared=true
localPortPreserved=true
afterDisconnect=after-disconnect
```

Ví dụ đã được biên dịch với `--release 15` và chạy thành công trên OpenJDK 24 tại môi trường thử nghiệm loopback. Việc dùng `new DatagramSocket(0, loopback)` để hệ điều hành cấp cổng tạm làm cho kết quả **không phụ thuộc cổng số cụ thể**. Giới hạn `setSoTimeout(2000)` tránh việc chờ vô hạn nếu hệ điều hành cấm loopback UDP hoặc môi trường thử nghiệm mất packet. Không coi local loopback là đảm bảo UDP giao packet 100% trên mọi môi trường: nếu có `SocketTimeoutException`, cần kiểm tra network policy và thứ tự gửi/nhận.

### 7.2. Diễn giải từng dòng

**`connected=true`:** `receiver.connect(new InetSocketAddress(...))` gắn socket nhận với endpoint của `allowedPeer`.

**`peerPortMatches=true`:** `receiver.getPort()` là **remote peer port** và bằng cổng của `allowedPeer`. Nó **khác** `receiver.getLocalPort()` — cổng cục bộ.

**`wrongDestinationRejected=true`:** `send(receiver, loopback, otherPeer.getLocalPort(), ...)` cố gửi từ socket đã connected tới peer **khác**. `DatagramSocket.send` từ chối vì packet destination không khớp peer.

**`whileConnected=from-allowed`:** `otherPeer` gửi `"from-other"` trước, nhưng receiver chỉ chấp nhận packet đến từ `allowedPeer`. Sau đó `allowedPeer` gửi `"from-allowed"`, và `receive` trả payload ấy.

**`disconnected=true`:** `disconnect` bỏ association của remote peer, chưa đóng socket.

**`remoteCleared=true`:** `getRemoteSocketAddress() == null` sau khi disconnect thành công.

**`localPortPreserved=true`:** socket vẫn bind tại cổng local ban đầu, không được tạo lại.

**`afterDisconnect=after-disconnect`:** `otherPeer` gửi một packet **mới** sau disconnect; khi socket unconnected nó không còn bị loại chỉ vì source port khác A.

**Vì sao không in cổng thật?** Giá trị cổng tạm thay đổi theo lần chạy. Những điều kiện boolean thể hiện đúng ý nghĩa cần học mà không khiến stdout phụ thuộc hệ điều hành.

### 7.3. Vì sao tạo `DatagramPacket` mới ở mỗi lần nhận?

`receive(DatagramPacket)` ghi dữ liệu vào buffer mà caller cấp, kèm metadata địa chỉ/cổng sender và độ dài dữ liệu thực tế. Trong ví dụ, mỗi lần nhận tạo buffer 128 byte mới nên không có lỗi do tái sử dụng packet có `length` đã bị thay đổi.

Nếu ứng dụng tái sử dụng một `DatagramPacket`, hãy kiểm tra ý nghĩa `getLength()` và gọi `setLength(capacity)` trước lượt nhận kế tiếp khi cần. Với message dài hơn buffer, phần vượt quá bị **cắt bỏ**, không tự xuất hiện trong một lần `receive` tiếp theo.

## 8. Lọc peer khi socket **không connect**: kiểm tra IP + port trong ứng dụng

Với một server dùng chung socket cho nhiều client, thường không gọi `connect` mà nhận mọi datagram trên local port và **đọc sender từ metadata**:

```java
DatagramPacket packet = new DatagramPacket(new byte[2048], 2048);
socket.receive(packet);

InetAddress senderIp = packet.getAddress();
int senderPort = packet.getPort();
int length = packet.getLength();
```

Đây là **đoạn minh họa**, cần có `socket` hợp lệ và import `java.net.*`. `getAddress()` và `getPort()` lấy endpoint **thực tế được packet report**; đừng lấy `packet.getData()` rồi đoán source từ một chuỗi text do client gửi.

Nếu ứng dụng chỉ muốn phục vụ một peer A nhưng cần socket unconnected vì lý do kiến trúc:

```java
InetAddress expectedIp = /* địa chỉ đã xác định từ cấu hình tin cậy */;
int expectedPort = /* cổng đã xác định từ cấu hình tin cậy */;

while (true) {
    byte[] buf = new byte[2048];
    DatagramPacket packet = new DatagramPacket(buf, buf.length);
    socket.receive(packet);

    if (!expectedIp.equals(packet.getAddress())
            || expectedPort != packet.getPort()) {
        continue; // Bỏ packet từ endpoint khác.
    }

    // Chỉ lúc này parse/validate payload trong packet.getLength() byte.
}
```

Đây là **pseudocode minh họa**, không biên dịch độc lập vì hai biến `expectedIp`/`expectedPort` phải được điền và `socket` phải tồn tại. Đối với server nhiều peer, thay điều kiện cố định bằng bảng endpoint/client và **session/authorization** thích hợp.

**Tại sao phải có cả địa chỉ và cổng?** Vì nhiều client có thể chia sẻ IP public sau NAT; hai request từ cùng IP nhưng source port khác không phải cùng UDP endpoint. Cũng không thể giả định source port giữ nguyên vô thời hạn: NAT rebinding, thay mạng hoặc client restart có thể thay endpoint. Trong hệ thống có phiên xác thực, việc đổi endpoint cần một thủ tục **revalidation** rõ ràng, không chỉ tự coi mọi packet có cùng ID trong payload là người dùng cũ.

### 8.1. Lọc endpoint khác xác thực danh tính

Một whitelist IP+port có giá trị **routing/filtering** và giảm nhiễu, nhưng **không thay thế authentication/authorization**. Tùy môi trường mạng, giả mạo source address có thể xảy ra; trên mạng nội bộ, attacker cũng có thể phát dữ liệu giả tới cổng lắng nghe nếu hệ thống không có lớp bảo vệ khác.

Nếu cần bảo vệ datagram khỏi giả mạo và sửa đổi:

- Dùng cơ chế **message authentication** ở tầng ứng dụng, hoặc giao thức UDP có xác thực/mã hóa được tiêu chuẩn hóa và triển khai đúng (ví dụ DTLS phù hợp trường hợp sử dụng).
- Cân nhắc **replay protection**, nonce, request ID, sequence/generation và thời hạn token.
- Chỉ parse những payload có giới hạn kích thước; validate định dạng, length, version, permission, session state.
- Dùng rate limit, quotas, firewall/network policy và logging an toàn nếu public UDP endpoint lộ ra Internet.
- Không “tin” một hostname do payload gửi lên; nếu cần DNS, resolve/cấu hình có kiểm soát, quan tâm địa chỉ IPv4/IPv6 và sự thay đổi IP theo thời gian.

**UDP connect không có TLS handshake**, không tự trao đổi khóa và không nói gì về danh tính/độ tin cậy của peer; nó chỉ giới hạn endpoint của socket.

## 9. `DatagramChannel.connect/disconnect` trong Java NIO

`java.nio.channels.DatagramChannel` là lựa chọn UDP theo Java NIO, phù hợp khi cần `ByteBuffer`, selector/non-blocking I/O hoặc tích hợp với pipeline NIO.

### 9.1. Quy tắc chính

- `DatagramChannel.open()` trả về channel mở nhưng **chưa connected**.
- `channel.bind(localAddress)` gắn cổng cục bộ (nếu chưa bind, connect/send có thể làm tự bind).
- `channel.connect(remote)` gắn peer IP+port. Channel chỉ nhận/gửi datagram với peer ấy.
- `channel.disconnect()` gỡ association; channel trở lại unconnected nếu chưa đóng.
- `channel.isConnected()`, `channel.getRemoteAddress()` dùng quan sát trạng thái.
- `channel.send(ByteBuffer, SocketAddress)` và `channel.receive(ByteBuffer)` có thể dùng khi **unconnected**.
- `channel.read(ByteBuffer)` và `channel.write(ByteBuffer)` yêu cầu **connected channel**, vì hai method **không có tham số remote address**.
- `channel.configureBlocking(false)` cho phép non-blocking; trong chế độ này `receive` có thể trả `null` nếu chưa có datagram ngay.

**Đừng nhầm `DatagramSocket.connect` và `DatagramChannel.connect` về gọi lặp lại:** `DatagramChannel.connect` ném `AlreadyConnectedException` nếu channel đã connected. Muốn thay peer, gọi `disconnect()` trước khi `connect(newPeer)`. Với `DatagramSocket`, gọi `connect` lại sẽ thử thay remote peer.

### 9.2. Mẫu NIO ngắn

```java
try (DatagramChannel channel = DatagramChannel.open()) {
    channel.bind(new InetSocketAddress(0));
    channel.connect(new InetSocketAddress("127.0.0.1", 9000));

    ByteBuffer payload = StandardCharsets.UTF_8.encode("hello");
    channel.write(payload); // Đích đã gắn: 127.0.0.1:9000.

    channel.disconnect();
    // Giờ có thể channel.send(buffer, someOtherRemote) nếu cần.
}
```

Đây là **đoạn minh họa**, cần các import:

```java
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;
```

`9000` chỉ là **cổng giả định để minh họa**, đoạn code không tạo process nhận trên cổng đó; không có guarantee rằng payload được phía kia nhận. Đừng coi `channel.write` thành công là kết nối thành công hay phản hồi ứng dụng. `ByteBuffer` có `position`/`limit` nên trong code thực tế cần `flip`/`clear` hoặc tạo buffer mới đúng cách khi nhận/gửi nhiều datagram.

### 9.3. So sánh nhanh hai API

| Tiêu chí | `DatagramSocket` | `DatagramChannel` |
| --- | --- | --- |
| Đối tượng payload | `DatagramPacket` + `byte[]` | `ByteBuffer` |
| Chọn peer | `connect(InetAddress, int)` / `connect(SocketAddress)` | `connect(SocketAddress)` |
| Gỡ peer | `disconnect()` | `disconnect()` |
| Quan sát peer | `getInetAddress/getPort/getRemoteSocketAddress` | `getRemoteAddress` |
| Gửi khi unconnected | `send(packet)` có destination | `send(buffer, target)` |
| Nhận khi unconnected | `receive(packet)` trả địa chỉ/cổng trong packet | `receive(buffer)` trả `SocketAddress` |
| API gửi/nhận không kèm address | Dùng `send/receive` với packet; connect ảnh hưởng kiểm tra endpoint | `read/write` **chỉ khi connected** |
| Non-blocking và selector | Không phải giao diện NIO chính | Hỗ trợ `configureBlocking(false)`/`Selector` |
| Gọi connect khi đã connected | Có thể thử chuyển remote peer | Ném `AlreadyConnectedException`; disconnect trước |

Cả hai đều chạy trên **UDP**: không tạo bảo đảm delivery/order, không cung cấp bảo mật ứng dụng, không thay đổi giới hạn kích thước datagram.

## 10. Các tình huống ứng dụng và quyết định thiết kế

### 10.1. UDP client chỉ giao tiếp với một server cố định

Một client DNS-like hoặc telemetry gửi đến một endpoint cố định và chỉ muốn đọc trả lời từ endpoint đó có thể dùng connected UDP:

```text
bind local ephemeral port
connect(server IP, UDP port)
send(request)
receive(response)
validate response version/requestId/authentication
close or disconnect when necessary
```

Lợi ích là **giảm xử lý địa chỉ đích lặp lại** và lọc những packet đến từ endpoint khác. Tuy nhiên:

- Có thể vẫn nhận datagram **không thuộc request hiện tại** nhưng đến từ **đúng endpoint**.
- Cần request ID/generation/nonce, payload validation, timeout, retries và xử lý trường hợp trễ/lặp.
- Cổng/địa chỉ server có thể đổi do DNS, failover, NAT; phải quyết định rõ thời điểm reconnect.
- Một response chưa được xác thực từ đúng IP+port chưa nhất thiết đáng tin.

### 10.2. UDP server phục vụ nhiều client

Một server lắng nghe trên một local port và muốn xử lý đồng thời nhiều client thường dùng **unconnected `DatagramSocket` hoặc `DatagramChannel`**:

1. `bind` tới local port.
2. `receive` datagram, lấy source IP+port.
3. Kiểm tra giới hạn dữ liệu, định dạng, phiên, credentials và quyền.
4. Xử lý message; nếu trả lời, gửi một `DatagramPacket` tới endpoint tương ứng.
5. Quản lý cleanup/rate limit/idle timeout cho mỗi peer/session.

**Không `connect` chung socket server tới client A rồi mong vẫn nhận client B.** Việc đó khiến bộ lọc của socket chỉ cho A, trái với mục tiêu phục vụ nhiều endpoint.

Có thể thiết kế một socket riêng mỗi peer trong một số kiến trúc, nhưng cần cân nhắc cổng, bộ nhớ, file descriptors và cách NAT/firewall xử lý. Đây là quyết định kiến trúc, không phải bắt buộc của UDP.

### 10.3. Failover giữa A và B

Nếu server A ngừng phản hồi, một client có thể `disconnect()` rồi `connect(B)`, nhưng:

- Packet từ A có thể đến trễ hoặc bị loại.
- Packet response cũ của A đã nằm trong queue trước connect có thể bị bỏ.
- B có thể dùng giao thức hoặc session state khác; `connect(B)` **không** tự tái xác thực hay đồng bộ trạng thái.
- Nếu đổi peer làm thay đổi tính đúng đắn của session, phải tạo **session mới hoặc re-authentication**, và phân biệt request generations trong ứng dụng.

Đừng tự gán “connect thành công” bằng “peer B sẵn sàng”. Với UDP, nên dùng **application-level health/ack** nếu cần bằng chứng peer nhận và xử lý request.

## 11. Timeout, PortUnreachableException và trạng thái lỗi

### 11.1. Đặt timeout nhận

`DatagramSocket.receive(packet)` là thao tác **blocking** trong cấu hình thường. Dùng `setSoTimeout(milliseconds)` để không chờ vô hạn:

```java
socket.setSoTimeout(1500);

try {
    DatagramPacket response = new DatagramPacket(new byte[4096], 4096);
    socket.receive(response);
    // Kiểm tra sender, packet.getLength(), protocol message...
} catch (SocketTimeoutException e) {
    // Timeout: không đồng nghĩa server đã chết.
}
```

Đây là đoạn minh họa, cần import `java.net.*` và biến `socket`. Sau timeout, socket vẫn hợp lệ để dùng nếu không có lỗi khác. UDP có thể mất packet trên đường truyền, response có thể đến trễ hoặc ứng dụng server chưa trả lời.

**Không dùng timeout như một chỉ báo xác thực**. Packet có thể đến đúng IP+port nhưng giả mạo hoặc không thuộc request đang đợi.

### 11.2. `PortUnreachableException`

Với connected UDP, nếu hệ thống nhận được ICMP báo destination không tới/UDP port không mở, lời gọi `send` hoặc `receive` về sau **có thể** ném `PortUnreachableException`.

Javadoc nói rõ **không có bảo đảm** lỗi này sẽ được ném: ICMP có thể bị chặn, không được tạo hoặc không được báo cho Java. Vì vậy:

- Không dùng việc thiếu exception để kết luận remote peer tồn tại.
- Không coi exception là lỗi giao thức tuyệt đối; cần phân loại mạng/firewall/peer và thử lại có giới hạn nếu hợp đồng cho phép.
- Không viết logic connectivity chỉ dựa trên `socket.isConnected()`: cờ này chỉ biểu thị **cấu hình local remote association**.

### 11.3. Các lỗi khác

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` khi `send(packet)` trên connected socket | Packet nhắm IP hoặc port **khác** connected peer | Dùng đúng endpoint hoặc `disconnect` nếu thực sự muốn gửi nhiều peer |
| `SocketTimeoutException` khi receive | Không có packet được phép nhận trong giới hạn thời gian | Kiểm tra send/peer/filter/network; dùng timeout và retry có chiến lược |
| `PortUnreachableException` | Hệ thống báo peer/port có thể không tới | Không coi lỗi có hoặc không như tín hiệu tuyệt đối |
| `SocketException` khi bind | Port đang dùng, quyền hệ điều hành hoặc cấu hình địa chỉ lỗi | Kiểm tra local bind, port, firewall/network policies |
| `UncheckedIOException` khi connect/disconnect | Không cập nhật association thành công | Đóng socket nếu trạng thái không rõ, tạo socket mới khi cần |
| `AlreadyConnectedException` với `DatagramChannel.connect` | Channel đã connected | `disconnect()` trước khi connect peer khác |
| `NotYetConnectedException` với `DatagramChannel.read/write` | Channel chưa connected | Dùng `receive/send` hoặc gọi `connect` |
| `ClosedChannelException` hoặc I/O trên socket đã close | Lifecycle đã kết thúc | Tạo socket/channel mới, không dùng lại closed object |
| `receive` trả payload bị cắt | Buffer nhỏ hơn datagram | Đặt giới hạn payload hợp lý, kiểm tra protocol size, tăng buffer theo nhu cầu |
| Packet từ B “mất” khi connected A | **Peer filtering là hoạt động đúng** | Nếu muốn nhiều peer, dùng unconnected socket |
| Sau `disconnect` nhận response cũ | Không có application-level session/generation filter | Gắn message ID, xác thực và loại dữ liệu của phiên cũ |
| Không kết nối thực sự dù `isConnected() == true` | UDP không có handshake xác nhận bên kia | Dùng application-level probe/response hợp lệ và timeout |
| `receive` mã hóa text sai | Decode cả buffer hoặc charset không khớp | Dùng `getOffset/getLength` và encoding giao thức, không parse bytes chưa được nhận |

## 12. Kiểm thử peer filter có thể tin cậy

Để kiểm thử đúng tác dụng của API, nên kiểm tra những invariant thay vì dự đoán mọi packet trên một mạng thật:

1. **Chưa connect:** `isConnected() == false` và `getRemoteSocketAddress() == null`.
2. **Sau connect:** remote address/port trùng endpoint A, trạng thái true.
3. **Gửi đúng đích:** packet tới A được chấp nhận để gửi (không đồng nghĩa A đã nhận).
4. **Gửi sai đích:** `DatagramSocket.send` từ connected socket tới B bị từ chối bằng `IllegalArgumentException`.
5. **Nhận khi connected:** packet từ B không được trả cho ứng dụng; packet từ A được nhận.
6. **Sau disconnect:** remote address thành `null`, `isConnected() == false`, local port không đổi.
7. **Nhận sau disconnect:** một datagram **mới** từ B có thể được nhận.
8. **Thử packet ngay trước connect:** không khẳng định queue giữ nguyên; API cho phép bỏ packet đã đợi.
9. **Kiểm tra sender IP và port:** nếu dùng unconnected socket, tuyệt đối không chỉ lọc theo một trong hai.
10. **Timeout:** không để unit test treo vô hạn; packet loss có thể xảy ra ngay cả trên môi trường mạng giả lập.
11. **Security:** một packet có đúng source endpoint vẫn cần kiểm tra message ID, nonce/session và authentication nếu nghiệp vụ yêu cầu.
12. **Channel:** phân biệt `send/receive` với `read/write`, kiểm tra `AlreadyConnectedException` và nonblocking `receive==null` khi chưa có packet.

**Đừng xây test mặc định phụ thuộc Internet, DNS public, dịch vụ UDP ngoài hoặc một remote port cố định.** Loopback + ephemeral ports phù hợp hơn cho kiểm thử behavior của Java API. Với bài test lọc peer, sử dụng **hai socket nguồn với source port khác nhau**, như `UdpPeerFilterDemo`.

## 13. Ghi nhớ nhanh

- **`bind` chọn endpoint cục bộ.**
- **`connect` chọn remote peer theo IP + port, lọc peer nhận và hạn chế đích gửi.**
- **UDP connect không phải handshake, không ACK, không bảo đảm delivery/order và không xác thực peer.**
- **`disconnect` bỏ remote association nhưng giữ socket/local binding; `close` mới kết thúc sử dụng object.**
- **Packet đã nằm trong receive queue trước connect có thể bị bỏ; đừng dựa vào dữ liệu cũ sau khi thay association.**
- **Connected DatagramChannel cho phép `read/write`; unconnected dùng `send/receive` có endpoint, và `connect` lần hai khi đã connected ném `AlreadyConnectedException`.**
- **Server nhiều client nên dùng unconnected socket và tự chọn/kiểm tra endpoint theo yêu cầu.**
- **Source IP+port là bộ lọc định tuyến, không phải danh tính được xác thực; protocol validation và bảo mật vẫn cần riêng.**

## 14. Tài liệu chính thức còn áp dụng

- **Java SE 15 — `DatagramSocket`**, `connect(InetAddress,int)`, `connect(SocketAddress)`, `disconnect`, `receive`, `send` và `setSoTimeout`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramSocket.html
- **Java SE 25 — `DatagramSocket`**, kiểm tra API hiện hành về peer association, queue, `UncheckedIOException` và `PortUnreachableException`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html
- **Java SE 15 — `DatagramPacket`**, `getAddress`, `getPort`, `getOffset`, `getLength` và quy tắc buffer: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramPacket.html
- **Java SE 15 — `DatagramChannel`**, connected mode, `read/write`, `send/receive`, `AlreadyConnectedException` và nonblocking: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE hiện đại — `DatagramChannel`**, API đang được hỗ trợ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Java SE 15 — `SocketTimeoutException`**, timeout và xử lý I/O: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/SocketTimeoutException.html
- **Java SE 15 — `PortUnreachableException`**, ICMP và giới hạn phát hiện peer: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/PortUnreachableException.html
- **RFC 768 — User Datagram Protocol**, nền tảng IP/port/datagram: https://www.rfc-editor.org/rfc/rfc768
- **RFC 8085 — UDP Usage Guidelines**, những cân nhắc liên quan reliability/congestion và sử dụng UDP trong ứng dụng: https://www.rfc-editor.org/rfc/rfc8085

**Kết luận:** `DatagramSocket.connect/disconnect` và `DatagramChannel.connect/disconnect` là công cụ **chọn, lọc hoặc bỏ lọc remote UDP peer** trên socket cục bộ. Chúng giúp làm rõ endpoint trao đổi nhưng không tạo kết nối đáng tin, không khởi tạo phiên bảo mật và không quản lý dữ liệu cũ của ứng dụng. Trong Java 15+ và JDK hiện đại, hãy dùng chúng theo đúng nhu cầu **một peer hay nhiều peer**, kiểm tra cả địa chỉ lẫn cổng, giới hạn receive timeout và bổ sung authentication/replay protection khi giao thức yêu cầu.
