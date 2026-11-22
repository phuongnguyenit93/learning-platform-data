# DatagramPacket, địa chỉ đích và ranh giới gói tin UDP trong Java 15+

## 1. Bài toán và mục tiêu

Giả sử ứng dụng Java muốn gửi một lệnh ngắn `"PING"` đến dịch vụ tại một địa chỉ IP và cổng UDP, nhận `"PONG"`, hoặc gửi liên tiếp hai thông điệp `"A"` và `"BETA"`. Với TCP, ta cần tự phân định ranh giới thông điệp trên luồng byte. Với **UDP**, mỗi lệnh gửi tạo một **datagram**, có địa chỉ đích, cổng đích và payload riêng. Java biểu diễn một datagram gửi/nhận bằng `java.net.DatagramPacket` và dùng `java.net.DatagramSocket` để truyền.

**Trọng tâm của bài:** hiểu chính xác nội dung của `DatagramPacket`: **buffer, offset, length, địa chỉ/port từ góc nhìn bên gửi và bên nhận**, cũng như những giới hạn của ranh giới gói tin khi buffer quá nhỏ.

Sau bài học, bạn sẽ có thể:

- Phân biệt `DatagramPacket` (một gói dữ liệu) với `DatagramSocket` (điểm gửi/nhận UDP).
- Tạo gói **gửi** có địa chỉ đích `InetAddress` + cổng hoặc `SocketAddress`; tạo gói **nhận** có buffer và giới hạn nhận.
- Đọc chính xác `getData()`, `getOffset()`, `getLength()`, `getAddress()`, `getPort()` và `getSocketAddress()`.
- Hiểu rằng **một lần `receive(...)` nhận tối đa một datagram**, không nối hai gói và không tự sinh ra gói thứ hai từ phần byte bị cắt.
- Dự đoán hành vi **truncation**, biết đặt lại `setLength(...)` nếu tái sử dụng `DatagramPacket` để nhận lần sau.
- Viết chương trình Java 15 chạy độc lập bằng loopback, gửi nhiều gói, kiểm tra offset, đáp lời về địa chỉ nguồn và thử dữ liệu quá dài.
- Thiết kế payload có quy tắc encoding, giới hạn kích thước, validation, timeout và chống xử lý dữ liệu từ nguồn không đáng tin.

**Tính hiện hành:** `DatagramPacket` và `DatagramSocket` là các API Java SE vẫn được hỗ trợ trong JDK hiện đại. Có thể dùng `java.nio.channels.DatagramChannel` khi ứng dụng cần hướng NIO, nhưng điều đó **không** khiến `DatagramPacket` trở thành legacy. Ví dụ trong bài biên dịch bằng `javac --release 15`; các API cốt lõi đã tồn tại trước đó và còn sử dụng được.

## 2. UDP có ranh giới thông điệp, nhưng không bảo đảm giao hàng

Một datagram UDP có thể mô tả đơn giản:

```text
+----------------------+-----------------------------+
| Thông tin vận chuyển | Payload ứng dụng             |
| source IP + port     | byte[0] ... byte[n-1]       |
| destination IP+port  |                             |
+----------------------+-----------------------------+

Socket phía gửi                        Socket phía nhận
send(packet("A"))      ---- UDP ---->  receive(...) -> "A"
send(packet("BETA"))   ---- UDP ---->  receive(...) -> "BETA"
```

Ở góc nhìn API:
- Mỗi `DatagramSocket.send(packet)` tạo **một datagram gửi** với phần dữ liệu được chọn từ `packet`.
- Mỗi `DatagramSocket.receive(packet)` đọc **một datagram đến** nếu có; khi trả về, `packet` chứa source IP/port và số bytes đã chép vào buffer.
- **Ranh giới datagram được giữ**: hai lần `send` không được API gộp thành một payload dài như một luồng TCP; phần dư của một datagram quá lớn cũng **không** được tiếp tục trong lần `receive` sau.
- Datagram có thể **mất, đến sai thứ tự, đến trùng**; khi không có data, `receive` có thể chờ. Việc gọi `send` trả về thành công chỉ nói hệ thống chấp nhận thao tác gửi, **không chứng minh đối tác đã nhận**.

Chú ý: không nên diễn giải “mỗi send tương ứng một receive” theo nghĩa **bảo đảm nhận được đủ mọi gói**. UDP giữ **ranh giới của mỗi datagram nhận được**, nhưng không cam kết mỗi datagram đã gửi sẽ tới đích. Mạng có thể làm mất hoặc đảo thứ tự.

Nếu cần giao hàng tin cậy, thứ tự, kiểm soát tắc nghẽn, giới hạn gửi lại hoặc tránh xử lý gói trùng, đó là trách nhiệm của một giao thức ở trên UDP hoặc của giao thức đã được thiết kế sẵn (ví dụ QUIC khi phù hợp), không phải tính năng tự động của `DatagramPacket`.

## 3. Hai đối tượng có vai trò khác nhau

### 3.1. DatagramSocket: điểm gửi/nhận, địa chỉ cục bộ

`DatagramSocket` đại diện cho socket UDP được bind vào một **địa chỉ cục bộ và cổng cục bộ**. Nó có thể:
- `send(DatagramPacket)`: gửi payload đến địa chỉ đích ghi trong packet, hoặc đến remote đã gắn với socket nếu đang ở chế độ connected.
- `receive(DatagramPacket)`: nhận datagram vào packet do caller cung cấp; mặc định có thể chờ vô hạn.
- `getLocalPort()` / `getLocalSocketAddress()`: lấy endpoint **cục bộ**.
- `setSoTimeout(milliseconds)`: đặt thời gian chờ tối đa cho **mỗi thao tác nhận đang chặn**; khi hết thời gian, `SocketTimeoutException` và socket vẫn có thể tiếp tục sử dụng.
- `close()`: giải phóng socket; sử dụng `try-with-resources`.

Ví dụ:

```java
InetAddress loopback = InetAddress.getLoopbackAddress();

try (DatagramSocket server = new DatagramSocket(0, loopback)) {
    server.setSoTimeout(3000);
    int portChosenByOs = server.getLocalPort();
    // Chạy các thao tác receive/send khi server còn mở.
}
```

Đây là **đoạn minh họa bên trong phương thức**, cần các import `java.net.*` và xử lý exception. Đối số port `0` ở **constructor bind socket cục bộ** có nghĩa yêu cầu OS chọn cổng còn trống. Ngược lại, trong bài toán gửi đi, bạn cần biết **cổng dịch vụ đích thực sự**, không tùy tiện dùng 0 làm port remote. Chương trình đầy đủ ở mục 8 dùng cổng do server đã bind rồi truyền cho sender.

`InetAddress.getLoopbackAddress()` chọn một địa chỉ loopback do JVM/OS hỗ trợ; đây là lựa chọn tốt để thử trên cùng máy mà không phải phụ thuộc vào DNS/public network.

### 3.2. DatagramPacket: payload và endpoint ở phía remote

`DatagramPacket` không phải socket, không sở hữu cổng cục bộ, không tự gửi hay tự nhận. Nó là **đối tượng mô tả vùng byte cần gửi hoặc vùng byte để nhận**, kèm địa chỉ/port của đầu bên kia:

```java
// Gói gửi: đã có byte[] payload, InetAddress destination, int port.
DatagramPacket outgoing =
        new DatagramPacket(payload, payload.length, destination, port);

// Gói nhận: chưa biết source IP/port, chỉ cấp chỗ cho bytes đến.
byte[] receiveBuffer = new byte[2048];
DatagramPacket incoming =
        new DatagramPacket(receiveBuffer, receiveBuffer.length);
```

**Không gọi `socket.send(incoming)` trên một socket không connected khi packet chỉ được tạo để nhận và chưa có destination**; nó thiếu địa chỉ đích. Tương tự, đừng lấy `outgoing.getAddress()` rồi tưởng đó là local sender address. Ý nghĩa của trường address/port phụ thuộc **packet đang đi ra hay vừa được nhận**.

## 4. Constructor quan trọng và bảng ý nghĩa

| Trường hợp | Constructor tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Nhận datagram, toàn bộ buffer | `new DatagramPacket(buf, buf.length)` | Dùng tối đa `buf.length` bytes |
| Nhận datagram, vùng con | `new DatagramPacket(buf, offset, length)` | Vùng nhận là `[offset, offset + length)` |
| Gửi tới IP và port | `new DatagramPacket(buf, length, inetAddress, port)` | Gửi `length` bytes đầu buffer |
| Gửi vùng con | `new DatagramPacket(buf, offset, length, inetAddress, port)` | Chỉ gửi `buf[offset..offset+length)` |
| Gửi qua địa chỉ socket | `new DatagramPacket(buf, length, socketAddress)` | Địa chỉ đích gồm IP/port |
| Gửi vùng con qua socket address | `new DatagramPacket(buf, offset, length, socketAddress)` | Đồng thời định rõ vùng byte và endpoint |

Các kiểu chính:
- `byte[]`: mảng chứa dữ liệu.
- `offset`: vị trí **bắt đầu vùng dữ liệu** trong mảng; tính bằng bytes, từ 0.
- `length`: số bytes sẽ gửi, hoặc **giới hạn số bytes được phép chép vào packet khi nhận**. Không phải tổng kích thước mảng.
- `InetAddress`: IP đích cho packet gửi, hoặc IP nguồn của packet đã nhận.
- `int port`: cổng **remote** liên quan packet, không phải cổng bind của `DatagramSocket`.
- `SocketAddress`: một đối tượng mô tả remote endpoint; với UDP/IP thường là `InetSocketAddress`.

**Giới hạn hợp lệ:** `offset >= 0`, `length >= 0`, `offset + length <= buf.length`; cổng từ 0 đến 65535 ở mức API, nhưng cổng remote phải hợp lệ đối với thao tác mạng thực tế. Nếu offset/length vượt mảng hoặc port ngoài miền, constructor/setter có thể ném `IllegalArgumentException`.

Không dùng `length = message.length()` với `String` có Unicode, vì `String.length()` đếm UTF-16 code units, **không phải số bytes** dùng cho UDP. Đầu tiên chuyển sang `byte[]` bằng charset xác định, rồi lấy `bytes.length`.

## 5. Địa chỉ đích lúc gửi, địa chỉ nguồn lúc nhận

### 5.1. Gửi không connected: packet phải có remote IP và port

```java
byte[] bytes = "PING".getBytes(StandardCharsets.UTF_8);
InetAddress host = InetAddress.getByName("127.0.0.1");
int servicePort = 9999;

try (DatagramSocket socket = new DatagramSocket()) {
    DatagramPacket request =
            new DatagramPacket(bytes, bytes.length, host, servicePort);
    socket.send(request);
}
```

Đoạn code độc lập này chỉ làm thao tác **gửi**, không bảo đảm có server đang lắng nghe ở port 9999. `127.0.0.1` là loopback IPv4, chỉ để minh họa. Trong chương trình chính mục 8, port được lấy từ một server socket thực sự để không lệ thuộc cổng cố định.

Ở phía gửi:
- `request.getAddress()` trả **IP đích**.
- `request.getPort()` trả **port đích**.
- `socket.getLocalPort()` trả **port nguồn của socket** tại máy gửi.
- `request.getSocketAddress()` trả endpoint **đích**, thường là `InetSocketAddress`.

Ở phía nhận, sau `server.receive(incoming)`:
- `incoming.getAddress()` trả **IP nguồn** của datagram vừa tới.
- `incoming.getPort()` trả **port nguồn** của datagram.
- `incoming.getSocketAddress()` trả **source endpoint** để có thể gửi phản hồi.
- `server.getLocalPort()` vẫn là **cổng server đang bind**, không phải `incoming.getPort()`.

Đây là sự khác nhau dễ gây lỗi trong ứng dụng server: **packet.getPort() không có nghĩa “cổng của chính socket mình đang dùng”**.

### 5.2. Trả lời đúng nơi đã gửi yêu cầu

Nếu server vừa nhận `DatagramPacket request`, một phản hồi đơn giản có thể được gửi tới chính endpoint nguồn:

```java
byte[] reply = "ACK".getBytes(StandardCharsets.UTF_8);
DatagramPacket response = new DatagramPacket(
        reply, reply.length, request.getAddress(), request.getPort());
server.send(response);
```

Đoạn trên nằm trong phương thức đã có `DatagramSocket server` và packet `request` đã nhận. Không được nhầm địa chỉ/port nguồn vừa nhận với đích của request gửi ban đầu.

**Cảnh báo bảo mật:** IP/port nguồn quan sát được là metadata mạng, **không đủ chứng minh người gửi đáng tin**. UDP source address có thể bị giả mạo trong một số môi trường; NAT/firewall cũng có thể thay đổi ánh xạ port. Không gửi dữ liệu nhạy cảm, cấp quyền hay thực hiện thao tác thanh toán chỉ vì `request.getAddress()` trông hợp lệ. Dùng xác thực phiên/giao thức an toàn khi cần.

### 5.3. InetSocketAddress và DNS

Có thể tạo endpoint từ địa chỉ đã được phân giải:

```java
InetAddress dest = InetAddress.getLoopbackAddress();
InetSocketAddress remote = new InetSocketAddress(dest, 12345);
DatagramPacket packet = new DatagramPacket(bytes, bytes.length, remote);
```

Với tên miền có thể phân giải qua `InetAddress.getByName(hostname)` hoặc constructor phù hợp, nhưng việc phân giải có thể cho IPv4/IPv6 và phụ thuộc hệ thống. Khi thiết kế mạng thật, kiểm tra **protocol family và giao diện mạng**; IPv4 và IPv6 không tự hoán đổi trong mọi binding.

Tránh coi `new InetSocketAddress("no-such-host", port)` chắc chắn đã được phân giải: một `InetSocketAddress` có thể ở trạng thái unresolved. Nếu đầu vào đến từ cấu hình/user, kiểm tra địa chỉ đã phân giải và xử lý `UnknownHostException`/lỗi socket thích hợp thay vì coi tên host như bảo đảm sẽ gửi được.

## 6. Ranh giới gói tin: một lần receive lấy một datagram đến

Giả sử hai datagrams thực sự đến server:
1. Datagram payload = `"A"` (1 byte ASCII/UTF-8).
2. Datagram payload = `"BETA"` (4 bytes).

Với buffer nhận đủ lớn:

```java
byte[] receiveBuffer = new byte[20];
DatagramPacket packet =
        new DatagramPacket(receiveBuffer, receiveBuffer.length);

server.receive(packet); // Gói đến thứ nhất, getLength() == 1.
String first = new String(
        packet.getData(), packet.getOffset(), packet.getLength(),
        StandardCharsets.UTF_8);

// Trước khi tái sử dụng packet: phục hồi khả năng nhận đủ 20 bytes.
packet.setLength(receiveBuffer.length);
server.receive(packet); // Gói đến thứ hai, getLength() == 4.
String second = new String(
        packet.getData(), packet.getOffset(), packet.getLength(),
        StandardCharsets.UTF_8);
```

Đoạn code này minh họa **khi hai datagram đã đến theo thứ tự nêu trên**, không phải cam kết UDP sắp thứ tự trong mạng thật. Nó thuộc một phương thức đã có `DatagramSocket server` và `StandardCharsets` import.

Một lần `receive` không trả cả `"ABETA"`, cũng không tự chia `"BETA"` thành nhiều kết quả khác nhau nếu buffer đủ. Mỗi lần trả về tương ứng **một datagram được nhận**.

Tuy nhiên:
- Datagram gửi trước có thể đến sau hoặc mất hoàn toàn.
- UDP có thể nhận bản sao; ứng dụng cần sequence numbers/deduplication nếu điều đó quan trọng.
- Một datagram **0 byte** cũng là một thông điệp có thể tồn tại; `getLength()==0` không tự suy ra “timeout”, bởi timeout được báo bằng exception, không phải “gói rỗng”.

## 7. Offset, length, truncation và tái sử dụng buffer

### 7.1. getData trả mảng **toàn bộ**, không tự cắt payload

`DatagramPacket.getData()` trả về `byte[]` đang gắn với packet, có thể lớn hơn payload vừa nhận. Nếu xử lý như sau là dễ sai:

```java
// Sai nếu mảng chứa vùng trống hoặc dữ liệu cũ:
String wrong = new String(packet.getData(), StandardCharsets.UTF_8);

// Đúng:
String right = new String(packet.getData(),
        packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
```

Khi buffer là 2048 byte nhưng chỉ nhận `"OK"` dài 2 byte, phần còn lại của mảng **không phải** dữ liệu của datagram này. Nó có thể chứa byte 0 hoặc dữ liệu từ lần nhận trước nếu mảng được tái sử dụng. Đừng dùng `.trim()` để “loại phần rác”: trim có thể thay đổi dữ liệu hợp lệ và không sửa được lỗi xử lý length.

### 7.2. Offset khi gửi và khi nhận

Có thể chỉ gửi một lát cắt của mảng:

```java
byte[] data = "xxHELLOz".getBytes(StandardCharsets.US_ASCII);
DatagramPacket outgoing = new DatagramPacket(
        data, 2, 5, destination, port);
// Chỉ gửi 5 bytes: H E L L O.
```

Ở phía nhận, bạn cũng có thể cho phép dữ liệu bắt đầu từ một offset:

```java
byte[] backing = new byte[12];
DatagramPacket incoming = new DatagramPacket(backing, 3, 5);
// receive(incoming): chỉ ghi vào 5 bytes từ backing[3] đến backing[7].
```

Sau khi nhận, `incoming.getOffset()==3`, còn `incoming.getLength()` là số bytes nhận được trong cửa sổ. Đọc payload theo `getOffset()` và `getLength()`, không mặc định offset bằng 0. Vùng con có ích khi đóng gói nhiều phần dữ liệu trong buffer, nhưng phải kiểm tra biên chặt chẽ để tránh lỗi xử lý mảng.

### 7.3. Nếu datagram lớn hơn cửa sổ nhận

Giả sử sender gửi đúng 6 bytes `"LONGER"`, receiver dùng:

```java
DatagramPacket small = new DatagramPacket(new byte[3], 3);
server.receive(small);
// Payload đã nhận trong Java chỉ còn 3 bytes: "LON".
```

Theo `DatagramSocket.receive`, nếu datagram dài hơn packet length, dữ liệu bị **cắt cụt**. Byte `"GER"` còn lại **không** nằm chờ để được trả ở lần nhận sau. Datagram tiếp theo (nếu có) là một **gói khác hoàn toàn**.

Điểm giới hạn quan trọng:
- `small.getLength()` trả số bytes **thực sự đã chép vào buffer**, ở đây là 3, chứ không phải độ dài datagram trước khi bị cắt (6).
- Nếu `getLength() == 3` và capacity là 3, ứng dụng **không thể kết luận chắc chắn đã bị cắt**: một datagram hợp lệ dài đúng 3 cũng tạo ra kết quả đó.
- Nếu cần phát hiện input quá dài, xác định **max payload của protocol**, cấp buffer đủ lớn để quan sát ít nhất một byte vượt giới hạn và từ chối khi vượt max, kết hợp length field trong protocol khi phù hợp. Không dựa duy nhất vào điều kiện `receivedLength == bufferCapacity` như bằng chứng chắc chắn của truncation.
- Không tự ghép bytes nhận từ nhiều `receive` để “hoàn tất” một datagram lớn; đó là sai mô hình UDP.

Nếu ứng dụng thực sự cần truyền một message lớn qua nhiều datagrams, phải thiết kế **application-layer fragmentation/reassembly** có ID, số thứ tự, độ dài, timeout, giới hạn tài nguyên và xử lý mất/trùng/sai thứ tự. Thường nên xem xét một protocol khác đã xử lý được những rủi ro ấy.

### 7.4. Bẫy tái sử dụng DatagramPacket

Sau lần `receive(packet)`, `packet.getLength()` bị cập nhật thành chiều dài gói vừa nhận. Nếu dùng **chính packet** để receive lần kế tiếp mà không đặt lại length, cửa sổ nhận có thể **chỉ còn bằng chiều dài gói trước** và vô tình cắt gói sau.

Ví dụ, lần đầu nhận `"A"` → `getLength()==1`; lần sau muốn nhận `"BETA"` dài 4 byte thì cần:

```java
packet.setLength(packet.getData().length - packet.getOffset());
server.receive(packet);
```

Nếu muốn giới hạn độ dài ứng dụng ở 1024 bytes dù backing buffer lớn hơn, thay bằng `setLength(1024)` miễn `offset+1024 <= buf.length`; đó là *receive window*, không phải giá trị dữ liệu đã nhận. Bạn cũng có thể tạo packet nhận mới cho mỗi lượt và dùng buffer riêng khi đơn giản hơn.

**Không chia sẻ một `DatagramPacket` cùng `byte[]` cho nhiều thread nhận/gửi đồng thời mà không có quy ước ownership rõ ràng.** Payload array là mutable; race condition có thể gây đọc dữ liệu cũ, hỗn hợp hoặc thay đổi vùng gửi/nhận ngoài ý muốn.

## 8. Chương trình đầy đủ: gửi/nhận trên loopback, có địa chỉ đích và ranh giới

Ví dụ sau tạo server và client UDP trên cùng máy, dùng port do OS cấp để tránh xung đột với các ứng dụng khác. Nó lần lượt kiểm tra:
- Gửi datagram `"A"` rồi `"BETA"`; server đọc riêng và reset `setLength`.
- Xác nhận `getPort()` của packet **đã nhận** là cổng nguồn của client.
- Gửi lát cắt `"HELLO"` từ một buffer khác, nhận vào offset 3.
- Gửi `"LONGER"` vào buffer 3 byte rồi gửi datagram khác `"OK"`, chứng minh phần dư không thành datagram tiếp theo.
- Nhận `"REQ"` và phản hồi `"ACK"` tới `request.getAddress()`/`request.getPort()`.
- Kiểm tra offset/length vượt buffer và port ngoài miền bị từ chối.

Lưu đúng tên tệp **`UdpPacketBoundariesDemo.java`**:

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public final class UdpPacketBoundariesDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (DatagramSocket server = new DatagramSocket(0, loopback);
             DatagramSocket client = new DatagramSocket(0, loopback)) {
            server.setSoTimeout(3000);
            client.setSoTimeout(3000);
            int serverPort = server.getLocalPort();

            send(client, "A", loopback, serverPort);
            byte[] reusedBuffer = new byte[20];
            DatagramPacket received = new DatagramPacket(
                    reusedBuffer, reusedBuffer.length);
            server.receive(received);
            System.out.println("first: " + text(received) +
                    " (" + received.getLength() + " byte)");
            System.out.println("source port matches: " +
                    (received.getPort() == client.getLocalPort()));

            // Reset receive capacity; after first receive getLength is 1.
            received.setLength(reusedBuffer.length);
            send(client, "BETA", loopback, serverPort);
            server.receive(received);
            System.out.println("second after reset: " + text(received) +
                    " (" + received.getLength() + " bytes)");

            byte[] sliced = "xxHELLOz".getBytes(StandardCharsets.US_ASCII);
            client.send(new DatagramPacket(sliced, 2, 5, loopback, serverPort));
            byte[] offsetBuffer = new byte[12];
            DatagramPacket offsetReceived = new DatagramPacket(
                    offsetBuffer, 3, 5);
            server.receive(offsetReceived);
            System.out.println("slice sent/received: " + text(offsetReceived));
            System.out.println("receive offset: " + offsetReceived.getOffset());

            send(client, "LONGER", loopback, serverPort);
            DatagramPacket small = new DatagramPacket(new byte[3], 3);
            server.receive(small);
            System.out.println("small window: " + text(small));
            System.out.println("window full: " + (small.getLength() == 3));

            send(client, "OK", loopback, serverPort);
            DatagramPacket next = new DatagramPacket(new byte[10], 10);
            server.receive(next);
            System.out.println("next datagram: " + text(next));

            send(client, "REQ", loopback, serverPort);
            DatagramPacket request = new DatagramPacket(new byte[16], 16);
            server.receive(request);
            byte[] ack = "ACK".getBytes(StandardCharsets.US_ASCII);
            server.send(new DatagramPacket(
                    ack, ack.length, request.getAddress(), request.getPort()));
            DatagramPacket response = new DatagramPacket(new byte[8], 8);
            client.receive(response);
            System.out.println("reply: " + text(response));
            System.out.println("reply from server port: " +
                    (response.getPort() == serverPort));

            boolean badSlice = false;
            try {
                new DatagramPacket(new byte[4], 3, 2);
            } catch (IllegalArgumentException expected) {
                badSlice = true;
            }
            System.out.println("bad slice rejected: " + badSlice);

            boolean badPort = false;
            try {
                new DatagramPacket(ack, ack.length, loopback, 65536);
            } catch (IllegalArgumentException expected) {
                badPort = true;
            }
            System.out.println("bad port rejected: " + badPort);
        }
    }

    private static void send(DatagramSocket socket, String text,
                             InetAddress destination, int port)
            throws Exception {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        socket.send(new DatagramPacket(
                data, data.length, destination, port));
    }

    private static String text(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }
}
```

### 8.1. Biên dịch/chạy và output

Dùng JDK hỗ trợ target Java 15:

```bash
javac --release 15 UdpPacketBoundariesDemo.java
java UdpPacketBoundariesDemo
```

**Stdout đã được kiểm tra khi biên dịch và thực thi thực tế trên loopback:**

```text
first: A (1 byte)
source port matches: true
second after reset: BETA (4 bytes)
slice sent/received: HELLO
receive offset: 3
small window: LON
window full: true
next datagram: OK
reply: ACK
reply from server port: true
bad slice rejected: true
bad port rejected: true
```

Chương trình có 12 dòng output. Nó chạy với hai socket trong **một tiến trình**, lần lượt gửi và nhận từng datagram; tránh giả định địa chỉ IP/port động sẽ có một giá trị cố định. Các giá trị in ra đều là payload/điều kiện có thể kiểm tra xác định.

**Độ tin cậy của ví dụ:** loopback giảm biến động nhưng bản chất vẫn là UDP; trong môi trường OS/network bất thường, gói có thể thất lạc hoặc thời gian chờ 3000 ms có thể hết, làm chương trình ném `SocketTimeoutException` thay vì ra toàn bộ stdout. Output trên là kết quả **khi các datagrams đến đầy đủ**, không phải cam kết UDP bảo đảm giao hàng trên mạng thực.

### 8.2. Giải thích các dòng quan trọng

- `first: A (1 byte)`: server nhận payload dài 1, và `received.getLength()==1`.
- `source port matches: true`: packet server nhận chỉ ra port nguồn của socket client, **không** phải `serverPort`.
- `received.setLength(reusedBuffer.length)` cho phép gói thứ hai `"BETA"` dài 4 bytes được nhận đầy đủ thay vì bị giới hạn ở 1 byte từ lượt trước.
- `slice sent/received: HELLO`: vùng gửi bắt đầu ở offset 2 với length 5, vùng nhận đặt dữ liệu ở offset 3 với length 5; helper `text(...)` đọc chính vùng hợp lệ.
- `small window: LON`: bản tin `"LONGER"` bị cắt còn 3 bytes ở buffer nhận. `window full: true` chỉ nói buffer đã đầy, **không phải thuật toán phát hiện truncation tổng quát**.
- `next datagram: OK`: lần nhận kế tiếp đọc gói mới `"OK"`, không phải phần `"GER"` còn lại.
- `reply: ACK`: server dùng **source address/port** của request để đặt địa chỉ đích cho gói trả lời; client xác nhận cổng nguồn reply bằng port server.
- Hai test cuối xác nhận constructor từ chối cửa sổ `offset+length > buf.length` và remote port vượt 65535.

## 9. Trường hợp nhận timeout, lỗi I/O và vòng đời tài nguyên

Một receiver không nên chờ vô hạn nếu yêu cầu nghiệp vụ có deadline:

```java
try (DatagramSocket socket = new DatagramSocket(0)) {
    socket.setSoTimeout(1000); // 1000 milliseconds.
    byte[] buf = new byte[4096];
    DatagramPacket packet = new DatagramPacket(buf, buf.length);

    try {
        socket.receive(packet);
        // Phân tích đúng vùng [getOffset(), getOffset()+getLength()).
    } catch (java.net.SocketTimeoutException timeout) {
        // Không có datagram nào được nhận trong khoảng thời gian chờ.
    }
}
```

Đây là **đoạn Java minh họa độc lập về nhận/timeout** (khi bổ sung import `java.net.*` và khai báo xử lý `SocketException`/`IOException` trong phương thức bao ngoài). Port bind bằng 0 không tự chỉ ra dịch vụ remote. Không có sender, nhánh timeout sẽ được sử dụng sau khoảng chờ; **đừng viết test phụ thuộc vào thời gian chính xác tuyệt đối** của hệ điều hành.

Những điểm cần nhớ:
- `setSoTimeout(0)` có nghĩa chờ không giới hạn thời gian theo option này; giá trị dương giới hạn thời gian blocking `receive`.
- `SocketTimeoutException` **không làm socket tự đóng**; có thể tiếp tục receive sau khi xử lý deadline.
- `DatagramSocket` triển khai `AutoCloseable`, vì vậy `try-with-resources` giúp đóng socket cả khi I/O có lỗi.
- `send` có thể ném `IOException`; `receive` có thể ném `IOException`, lỗi socket đóng hoặc timeout. Không giả định gửi thành công đồng nghĩa đối tác đang lắng nghe.
- `PortUnreachableException` có thể xuất hiện trong một số điều kiện với socket UDP connected, nhưng **không được bảo đảm** khi remote không tồn tại; không dùng việc **không** có exception làm phép kiểm sống của server.
- Sau khi socket đóng, không tiếp tục dùng nó để gửi/nhận như thể phiên làm việc còn hợp lệ.

### Connected DatagramSocket không phải TCP

`DatagramSocket.connect(remoteAddress, remotePort)` đặt endpoint remote mặc định và lọc việc gửi/nhận với endpoint đó. Nó không thiết lập phiên TCP, không tạo handshake tin cậy, không xác thực danh tính và không có bảo đảm giao hàng. Việc `connect` thường không đòi hỏi phía remote đang mở ứng dụng UDP.

Nếu socket đang connected, gói gửi tới endpoint không khớp có thể bị từ chối. Với socket không connected, packet gửi phải ghi đúng remote destination. Không để shared socket ở trạng thái connected rồi vô tình tái sử dụng cho nhiều client khác nhau.

## 10. Kích thước UDP, MTU và lý do không nên gửi datagram khổng lồ

Theo **RFC 8085**, một UDP datagram thông thường có giới hạn payload lý thuyết khoảng:
- **65.507 byte trên IPv4** với IPv4 header tối thiểu 20 byte và UDP header 8 byte.
- **65.527 byte trên IPv6** với header cơ bản 40 byte và UDP header 8 byte, chưa tính các cơ chế IPv6 jumbogram đặc biệt.

Các con số này **không phải kích thước an toàn khuyên dùng** cho mọi network, không phải bảo đảm Java/OS/provider sẽ gửi được toàn bộ, và không liên quan trực tiếp tới capacity của `DatagramPacket` Java nếu hạ tầng không cho phép.

Điều nguy hiểm là **IP fragmentation**: nếu UDP payload cộng các header vượt **Path MTU**, IP có thể phải chia nhỏ ở mức mạng hoặc thiết bị bỏ gói. Chỉ cần một mảnh mất là datagram nguyên vẹn có thể không được giao cho ứng dụng, làm giảm độ tin cậy và tăng tải.

Khuyến nghị hiện hành:
1. **Thiết kế payload nhỏ**, phù hợp MTU của môi trường mục tiêu thay vì mặc định “càng lớn càng tốt”.
2. Nếu cần kích thước khác nhau trên nhiều đường truyền, dùng **Path MTU Discovery (PMTUD/PLPMTUD)** và tiêu chuẩn/giao thức tương ứng. RFC 8085 có hướng dẫn và được bổ sung bởi RFC 8899.
3. Giới hạn tối đa payload tại tầng ứng dụng, bao gồm header và dữ liệu. Có thể dành thêm một byte trong receive buffer để nhận ra input **vượt giới hạn ứng dụng**.
4. Nếu cần gửi thông điệp lớn, đánh giá giao thức có reliability, congestion control và fragmentation/reassembly phù hợp, thay vì tự gửi UDP gói 60 KiB trên Internet.
5. Không quên **giới hạn tốc độ, chống tắc nghẽn và khả năng bị lợi dụng để khuếch đại lưu lượng** khi thiết kế UDP service.

Đừng nhầm kích thước **buffer ứng dụng** với MTU mạng: `new byte[8192]` có thể tạo vùng nhận lớn, nhưng một datagram 8192 bytes có thể đòi hỏi IP fragmentation trên nhiều tuyến mạng.

## 11. Kiểm tra frame ở tầng ứng dụng và xử lý text đúng bytes

UDP giúp giữ ranh giới datagram, nhưng **không cho biết ý nghĩa nội dung**. Một protocol có thể quy định:

```text
Datagram payload:
+------------+-------------+-------------------+
| magic: 2 B | length: 2 B | payload: N bytes  |
+------------+-------------+-------------------+
                  length = N
```

Ở phía nhận, phải kiểm tra:
- Đã nhận đủ 4 bytes header chưa?
- Magic/version có đúng chuẩn?
- Trường length có bằng số bytes thật sau header không? Có vượt mức cho phép không?
- Nội dung có đúng định dạng UTF-8 hoặc binary protocol không?
- Nếu có sequence number, nonce, MAC, chữ ký hoặc session ID, đã xác minh trước khi áp dụng nghiệp vụ chưa?

Đoạn code sau **chỉ là hàm parser minh họa**, đặt trong lớp có import `java.nio.*` và `java.net.DatagramPacket`. Nó từ chối header thiếu, magic sai, length vượt giới hạn hoặc payload bị cắt thiếu bytes:

```java
static byte[] readFrame(DatagramPacket packet) throws java.io.IOException {
    java.nio.ByteBuffer frame = java.nio.ByteBuffer.wrap(
            packet.getData(), packet.getOffset(), packet.getLength());
    frame.order(java.nio.ByteOrder.BIG_ENDIAN);

    if (frame.remaining() < 4) {
        throw new java.io.IOException("Too short");
    }
    int magic = Short.toUnsignedInt(frame.getShort());
    int expectedSize = Short.toUnsignedInt(frame.getShort());
    int maxPayload = 1200; // Giới hạn thiết kế của ví dụ, không phải MTU chung.

    if (magic != 0xCAFE || expectedSize > maxPayload
            || expectedSize != frame.remaining()) {
        throw new java.io.IOException("Invalid length or magic");
    }
    byte[] payload = new byte[expectedSize];
    frame.get(payload);
    return payload;
}
```

Hàm minh họa giả định frame thực sự chỉ gồm **4-byte header và payload**, không có checksum/tag. Mốc `1200` chỉ là **giới hạn ứng dụng ví dụ**, không phải hằng số UDP hoặc giá trị MTU bảo đảm cho mọi đường truyền. Một frame hợp lệ có thể có payload 0 byte.

Kể cả có trường length, tầng UDP vẫn **có thể cắt datagram nếu receive buffer quá nhỏ**. Parser có thể phát hiện nhiều ca length mismatch, nhưng muốn có chính sách từ chối gói quá lớn chắc chắn, hãy bảo đảm receive window đủ cho giới hạn protocol cộng vùng nhận biết vượt giới hạn, không dùng buffer bị tràn im lặng. Những metadata về packet quá dài nên được ghi vào log thống kê an toàn; không chấp nhận một packet nghi ngờ đã bị truncation chỉ vì decoder trả ra một chuỗi.

### Unicode có thể bị cắt giữa ký tự

Ví dụ chuỗi `"Việt"` hoặc ký tự emoji mã hóa UTF-8 bằng nhiều bytes cho một ký tự. Truncation của UDP hoạt động theo **bytes**, nên có thể cắt ngay giữa một UTF-8 sequence. Nếu code dùng decoder thay thế lỗi bằng ký tự `�`, dữ liệu nghiệp vụ có thể bị biến dạng mà không gây exception.

Khi protocol yêu cầu UTF-8 hợp lệ, dùng decoder kiểm tra lỗi:

```java
java.nio.charset.CharsetDecoder decoder =
        StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(
                    java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(
                    java.nio.charset.CodingErrorAction.REPORT);

String value = decoder.decode(java.nio.ByteBuffer.wrap(
        packet.getData(), packet.getOffset(), packet.getLength())).toString();
```

Đoạn này phải nằm trong phương thức xử lý `CharacterCodingException` và có biến `DatagramPacket packet`. Nó giúp phát hiện bytes UTF-8 malformed, nhưng **không tự chứng minh packet không bị truncation** nếu phần còn lại tình cờ vẫn tạo UTF-8 hợp lệ. Cần kiểm tra frame length/giới hạn và xác thực dữ liệu theo protocol.

## 12. Bảo mật dữ liệu từ DatagramPacket

`DatagramPacket` và UDP **không mã hóa**, **không xác thực danh tính**, và **không bảo đảm datagram thực sự đến từ người gửi mà nghiệp vụ kỳ vọng**. Đọc được source IP/port chỉ cung cấp metadata để giao tiếp, không đủ dùng làm yếu tố phân quyền.

Ứng dụng thực tế cần:
- **Giới hạn kích thước và tốc độ** trước khi cấp phát lớn hay xử lý decode tốn tài nguyên.
- Xác thực message/session bằng giao thức thích hợp (ví dụ **DTLS** khi cần UDP datagrams có bảo mật transport, hoặc **QUIC** khi bài toán cần giao thức hiện đại có encryption, reliability/stream semantics tùy loại dữ liệu); không tự thiết kế sơ sài cơ chế crypto trên UDP.
- Chống **replay/duplicate** nếu một datagram có thể khiến hệ thống ghi dữ liệu hoặc chuyển tiền; dùng sequence number, nonce, session và state đã xác thực.
- Có cơ chế rate limiting, timeout và kiểm soát phản hồi để tránh **reflection/amplification attacks**. Đặc biệt không gửi phản hồi lớn tới source IP chưa được xác thực chỉ vì packet có địa chỉ nguồn đó.
- Không tin dữ liệu từ payload cho đến khi parser kiểm tra đầy đủ độ dài, type, version, encoding, chính sách nghiệp vụ và MAC/tag khi cần.
- **Không coi `DatagramSocket.connect` là bảo mật**; đó chỉ là liên kết endpoint ở mức socket, không phải phương thức xác thực.
- Tránh log toàn bộ payload hoặc nội dung nhạy cảm. Ghi thông tin có kiểm soát như loại lỗi, độ dài, phiên bản protocol, số lượng datagrams bị từ chối.

Một gói nhận được đầy đủ và đúng định dạng vẫn có thể đến từ client không được phép. **Parsing correctness** và **authorization** là hai tầng khác nhau.

## 13. Các lỗi phổ biến và cách sửa

| Lỗi | Biểu hiện | Cách sửa |
| --- | --- | --- |
| Dùng `new String(packet.getData())` | Chuỗi có byte 0/rác từ buffer | Chỉ decode `getOffset()` và `getLength()` |
| Tái sử dụng receive packet, quên `setLength` | Gói lớn sau gói nhỏ bị cắt | Reset receive capacity trước lần receive kế tiếp |
| Dùng `String.length()` làm byte length | Payload UTF-8 bị cắt khi có Unicode | Chuyển String sang bytes trước, dùng `bytes.length` |
| Nghĩ `packet.getPort()` là local port | Reply gửi sai cổng, log sai | Incoming packet port là source; local port ở `socket.getLocalPort()` |
| Quên destination ở send packet | `IllegalArgumentException`/lỗi gửi với unconnected socket | Tạo packet có IP + port remote hợp lệ |
| Xem `send` trả về là đối tác đã nhận | Bỏ kiểm tra timeout/lỗi nghiệp vụ | Ứng dụng cần ACK/retry/sequence khi phù hợp |
| Nghĩ hai `send` sẽ thành một `receive` | Parser sai do tư duy stream | Một receive xử lý một datagram đến |
| Ghép phần byte bị truncation với datagram kế | Nội dung bị lỗi ghép | Datagram lớn bị cắt, phần dư không được nhận lần sau |
| Dùng `getLength()==bufferCapacity` để kết luận chắc bị cắt | Từ chối gói hợp lệ vừa đúng bằng capacity | Thiết kế max length + sentinel hoặc framing và chính sách rõ ràng |
| Nghĩ mọi packet luôn đến theo thứ tự | Sai logic cập nhật trạng thái | Dùng sequence number, loại trùng, xử lý reorder |
| Dùng buffer quá nhỏ | Truncation và dữ liệu không thể khôi phục | Chọn receive capacity phù hợp max frame |
| Dùng buffer thật lớn rồi gửi payload rất lớn | Fragmentation, mất datagram và DoS | Giới hạn payload, MTU-aware design, kiểm soát cấp phát |
| Trộn IPv4/IPv6 sai | Không bind/không gửi được | Dùng địa chỉ/protocol family tương thích |
| Không có `setSoTimeout` | Thread có thể kẹt chờ vô hạn | Đặt timeout/deadline nếu nghiệp vụ cần |
| Dùng source IP/port làm xác thực | Dễ spoof/reflection | Xác thực giao thức/session riêng |
| Chia sẻ cùng packet qua nhiều thread | Race condition trên buffer/length | Tách ownership hoặc đồng bộ rõ ràng |

## 14. Bộ kiểm thử biên cần có

Chỉ kiểm thử `"PING"`/`"PONG"` trên loopback là chưa đủ. Ít nhất hãy kiểm tra:

1. **Gói 1 byte, gói 4 bytes:** xác nhận mỗi receive đọc một datagram và `getLength()` đúng.
2. **Gói 0 byte:** xác nhận parser không coi đó là timeout và xử lý theo hợp đồng (nhận hoặc từ chối payload rỗng).
3. **Gói có Unicode:** sender dùng `StandardCharsets.UTF_8`; receiver decode đúng số bytes chứ không dùng `String.length()`.
4. **Offset khác 0:** gửi/nhận vùng con, xác nhận helper dùng `getOffset()`.
5. **Receive buffer quá nhỏ:** dữ liệu bị cắt, phần dư không trở thành datagram kế tiếp.
6. **Tái sử dụng DatagramPacket:** sau gói ngắn phải `setLength(...)` để nhận gói dài đầy đủ.
7. **Địa chỉ nguồn/đích:** incoming packet báo port nguồn sender; reply dùng `request.getAddress()/getPort()`.
8. **Bad offset, length, port:** API từ chối bằng `IllegalArgumentException` theo contract.
9. **Timeout:** không có sender → `SocketTimeoutException` khi giới hạn chờ hết; socket vẫn có thể dùng tiếp.
10. **Sai thứ tự/mất/trùng gói:** dùng mock/fault injection hoặc công cụ test mạng để quan sát cách ứng dụng chống duplicate/reorder (không dựa vào loopback luôn gây lỗi).
11. **Oversize/fragmentation:** thử trong môi trường có MTU/bandwidth khác nhau, nhưng không chạy thử gây tải lớn trên hệ thống không thuộc quyền kiểm soát.
12. **Payload sai format hoặc sender chưa được xác thực:** parser/protocol từ chối, không coi `getAddress()` là danh tính đã xác thực.

**Phân biệt hai mục tiêu QA:** (A) chức năng Java API đúng offset/length/remote endpoint; (B) ứng dụng giao thức đúng khi mất gói, chậm, sai thứ tự hoặc bị tấn công. Chạy sạch ví dụ trong mục 8 **không chứng minh** ứng dụng production đã giải quyết mục tiêu (B).

## 15. Câu hỏi luyện tập và đáp án

**Câu 1.** Một socket nhận 2 datagrams chứa `"Hi"` và `"Java"`. Có một lần `receive` nào trả `"HiJava"` không?

**Đáp án:** Không theo hợp đồng datagram. Mỗi `receive` chỉ đọc một datagram được nhận; việc các gói đã gửi có tới đầy đủ/đúng thứ tự không được UDP bảo đảm.

**Câu 2.** Một datagram có 20 bytes nhưng receiver tạo `new DatagramPacket(new byte[8], 8)`. Sau `receive` sẽ có điều gì?

**Đáp án:** Tối đa 8 bytes được chép; phần còn lại của datagram bị **cắt bỏ**, không phải một gói nhận tiếp theo. Không có API chuẩn của `DatagramPacket.getLength()` để khôi phục độ dài gốc 20 bytes sau khi truncation.

**Câu 3.** Server nhận packet và thấy `getPort()==53001`, còn `server.getLocalPort()==9000`. Hai giá trị có mâu thuẫn không?

**Đáp án:** Không. `getPort()` của **incoming packet** là **remote/source port** (53001). `server.getLocalPort()` là cổng cục bộ 9000 của server.

**Câu 4.** Buffer 100 bytes, offset = 10, receive window length = 30. Dữ liệu sẽ bắt đầu ở index nào và tối đa bao nhiêu byte?

**Đáp án:** Bắt đầu tại index **10**, tối đa **30 bytes**, trong khoảng [10, 40). Không dùng toàn bộ 100 bytes để decode payload.

**Câu 5.** Sau lần nhận 1 byte, có thể dùng luôn `receive(packet)` lần nữa để chắc chắn nhận 100 bytes với buffer 100 bytes không?

**Đáp án:** Không. Sau lần trước, `packet.getLength()==1`. Cần reset bằng `packet.setLength(packet.getData().length - packet.getOffset())` hoặc tạo packet nhận mới trước lần kế tiếp.

**Câu 6.** `getLength()==bufferCapacity` có chứng minh datagram đã bị cắt không?

**Đáp án:** Không. Datagram gốc có thể dài **đúng** capacity. Muốn từ chối oversize đáng tin hơn, thiết kế maximum frame và receive window phù hợp, dùng framing length/giới hạn, không phỏng đoán từ dấu hiệu buffer vừa đầy.

**Câu 7.** `new DatagramPacket(bytes, bytes.length, destination, port)` đã đủ để “connect UDP” và kiểm tra server có sống không?

**Đáp án:** Nó mô tả một **gói gửi** có địa chỉ đích, chưa phải một handshake. `send` thành công không chứng minh server đã nhận hoặc trả lời.

**Câu 8.** Có nên tin một incoming packet vì IP nguồn nằm trong danh sách IP quen thuộc không?

**Đáp án:** Chỉ IP nguồn không đủ chứng minh danh tính; spoofing/NAT có thể ảnh hưởng nguồn. Cần xác thực ở tầng protocol/session và kiểm tra quyền trước xử lý hành động nhạy cảm.

**Câu 9.** Tại sao một datagram quá dài có thể bị mất dù sender/receiver đều có buffer đủ lớn?

**Đáp án:** Do MTU, fragmentation hoặc xử lý mạng ở giữa, cũng như mất gói/tắc nghẽn. Buffer Java không bảo đảm đường truyền giao được mọi datagram kích thước lớn.

**Câu 10.** Nếu yêu cầu dữ liệu UTF-8 nhưng datagram bị cắt giữa một ký tự nhiều byte, làm thế nào?

**Đáp án:** Không cố “sửa” hay ghép datagram tiếp theo. Dùng framing/giới hạn phù hợp, từ chối frame thiếu bytes, decode UTF-8 có kiểm tra malformed sequence khi cần, rồi yêu cầu gửi lại ở mức giao thức nếu được thiết kế.

**Tiêu chí hoàn thành:** Bạn phân biệt chính xác địa chỉ/port cục bộ với remote, thao tác gửi và nhận, vùng `offset + length`, ranh giới từng datagram, truncate/discard, và xử lý timeout, encoding, giới hạn payload phù hợp.

## 16. Tài liệu chính thức và hướng dẫn còn áp dụng

- [Java SE 15 – java.net.DatagramPacket](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramPacket.html): constructors gửi/nhận, offset/length, getAddress/getPort/getSocketAddress/setLength.
- [Java SE 15 – java.net.DatagramSocket](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramSocket.html): send/receive, bind, SO_TIMEOUT, close và ranh giới khi datagram dài hơn packet length.
- [Java SE 25 – java.net.DatagramPacket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): xác nhận API tiếp tục được hỗ trợ, hợp đồng về vùng buffer và remote endpoint.
- [Java SE 25 – java.net.DatagramSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): hợp đồng hiện hành của send/receive, truncation, connected UDP và option.
- [Java SE 25 – java.net.InetSocketAddress](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetSocketAddress.html): endpoint IP + port và trạng thái unresolved.
- [Java SE 25 – java.nio.channels.DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): lựa chọn NIO khi cần channel/selectors.
- [IETF RFC 768 – User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): mô hình datagram và UDP header.
- [IETF RFC 8085 – UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): kích thước datagram, MTU, tránh fragmentation, loss/reorder và congestion control.
- [IETF RFC 8899 – Datagram Packetization Layer PMTU Discovery](https://www.rfc-editor.org/rfc/rfc8899): cơ chế khám phá MTU cho giao thức datagram hiện đại.

**Ghi nhớ:** `DatagramPacket` mô tả **một datagram với remote endpoint và một lát cắt byte-array**, còn `DatagramSocket` gửi/nhận datagram đó. Ranh giới gói tin được giữ **đối với datagrams thực sự nhận được**, nhưng không có bảo đảm giao hàng. Nếu receive window quá nhỏ, bytes dư bị bỏ; muốn xử lý đúng, hãy dùng `getOffset()`/`getLength()`, reset length khi tái sử dụng packet, và có protocol framing, validation, MTU-aware design khi cần.