# Dựa vào API công khai thay vì chi tiết triển khai nội bộ khi làm việc với UDP và datagram (Java 15+)

## Mục tiêu bài học

Java hỗ trợ UDP từ lâu qua `java.net.DatagramSocket` và `java.net.DatagramPacket`, đồng thời có API NIO `java.nio.channels.DatagramChannel`. Đáng chú ý, **Java 15 (JEP 373)** đã thay đổi phần lớn cách JDK **triển khai bên trong** các API datagram truyền thống. Điều này minh họa nguyên tắc quan trọng:

**Chương trình của bạn phải phụ thuộc vào hợp đồng API công khai, không phụ thuộc vào tên lớp nội bộ, đối tượng socket dưới hệ điều hành, buffer bí mật hay hành vi ngẫu nhiên của một phiên bản JDK.**

Bài này thuộc nhóm **UDP và datagram**, giúp bạn:

1. Phân biệt API chuẩn `DatagramSocket`, `DatagramPacket`, `DatagramChannel` với những chi tiết triển khai không được bảo đảm.
2. Hiểu ý nghĩa của JEP 373 trong Java 15: **thay triển khai bên dưới** không yêu cầu ứng dụng đúng chuẩn phải viết lại logic UDP.
3. Gửi và nhận datagram bằng API công khai, quản lý địa chỉ/port, timeout, độ dài dữ liệu, trạng thái kết nối UDP và tài nguyên.
4. Hiểu đúng `DatagramSocket.getChannel()` khi socket được tạo trực tiếp so với `DatagramChannel.socket()`: **không suy luận implementation từ đối tượng public**.
5. Tránh các giả định triển khai về thứ tự nhận gói, packet reuse, buffer size, ICMP lỗi, IPv4/IPv6, OS socket, và multicast.
6. Chạy ví dụ **JDK 17+** đầy đủ, vừa dùng classic datagram API vừa dùng NIO channel, với **13 kiểm tra có expected output rõ ràng**.

**Phạm vi:** `DatagramSocket` là API công khai còn được hỗ trợ; tên “legacy DatagramSocket API” trong JEP 373 nói tới **tên hạng mục triển khai được hiện đại hóa**, không có nghĩa mọi ứng dụng dùng `DatagramSocket` đã trở thành code legacy phải bỏ ngay. Bài ưu tiên các API hiện hành và tránh những cách truy cập nội bộ JVM đã lỗi thời.

## 1. Hợp đồng công khai quan trọng hơn việc JDK được cài như thế nào

API công khai cho ứng dụng một hợp đồng có thể đọc từ Java API documentation:

- `DatagramSocket.send(DatagramPacket)` gửi một datagram tới địa chỉ/port xác định.
- `DatagramSocket.receive(DatagramPacket)` nhận một datagram vào buffer đã cung cấp; khi hoàn tất, packet cho biết **nguồn gửi** và **độ dài thực tế**.
- `DatagramPacket.getData()`, `getOffset()`, `getLength()` cho biết vùng byte hữu ích.
- `setSoTimeout(int)` giới hạn thời gian chặn của `DatagramSocket.receive(...)`.
- `close()` giải phóng tài nguyên liên quan tới socket; dùng `try-with-resources` để chắc chắn đóng khi rời scope.
- `DatagramChannel` cung cấp API NIO qua `ByteBuffer`, hỗ trợ blocking/non-blocking và tùy nhu cầu có thể phối hợp với selector.

Ngược lại, **những điều không phải hợp đồng ứng dụng** bao gồm:

- JDK dùng lớp triển khai nào trong package nội bộ `sun.nio.ch` hoặc một package implementation khác.
- Một lời gọi UDP sử dụng bao nhiêu thread, file descriptor hoặc lời gọi hệ điều hành ở hậu trường.
- JDK tạo một object delegate cụ thể nào cho `DatagramSocket`.
- Một system property phục vụ chuyển đổi implementation trong một bản JDK cụ thể sẽ tồn tại mãi.
- Độ dài header nội bộ, layout của một object hoặc bytecode implementation.
- Một lỗi mạng/ICMP bất kỳ nhất thiết phát sinh thành một exception giống nhau trên Windows, Linux và mọi JVM.

**Cách tiếp cận đúng:** chương trình sử dụng phương thức public, kiểm tra kết quả public và kiểm thử trên các JDK/OS cần hỗ trợ. Không dùng reflection hay `--add-opens` để móc vào field/private constructor của lớp triển khai chỉ vì một phiên bản JDK cụ thể từng có chúng.

## 2. Java 15 và JEP 373: tại sao cần quan tâm?

**JEP 373 — Reimplement the Legacy DatagramSocket API**, được tích hợp trong Java 15, hiện đại hóa triển khai phía dưới của `java.net.DatagramSocket` và `java.net.MulticastSocket`. Mục tiêu tập trung vào bảo trì, ổn định và khả năng phát triển JDK. Nó tiếp nối xu hướng thay đổi phần network stack bên dưới API mà người dùng vẫn quen thuộc.

Ý nghĩa thực hành:

- Nếu code tuân theo **public contract** (mở socket, bind, send/receive datagram, kiểm tra lỗi và đóng), logic nghiệp vụ không nên phụ thuộc việc JDK dùng bộ máy nội bộ nào.
- Nếu code **ép kiểu** một object sang lớp implementation cụ thể hoặc mở private field nội bộ, nâng JDK có thể khiến code lỗi dù public API không hề đổi.
- Nếu test dựa vào thứ tự/ICMP/buffering không được bảo đảm, một JVM hoặc OS khác có thể khiến test thất bại; đó không nhất thiết là regression trong API.
- Không dùng cờ hoặc property nội bộ từng giúp quay về triển khai cũ làm “giải pháp lâu dài”. Chúng không phải API chuẩn cho ứng dụng, có thể biến mất và không bảo đảm tồn tại trong các JDK tương lai.

Cũng cần phân biệt: thay triển khai JDK **không làm UDP thành TCP**. Datagram vẫn không có cam kết giao hàng, thứ tự hoặc chống trùng lặp. Quy tắc transport này vẫn đúng dù phần code bên dưới socket được viết lại.

### Ví dụ anti-pattern

Mã **không nên dùng**:

```java
// Chỉ là mô tả anti-pattern; KHÔNG phải mã nên biên dịch.
// Class<?> impl = Class.forName("sun.nio.ch.SomeInternalDatagramClass");
// Field f = impl.getDeclaredField("privateSocketState");
// f.setAccessible(true);
// Object internalSocket = f.get(socket);
```

Đừng cố tìm đúng tên class nội bộ để thay vào đoạn minh họa. **Không có hợp đồng Java SE** hứa rằng cấu trúc ấy tồn tại, gọi được hay có cùng ngữ nghĩa.

Thay bằng API công khai, ví dụ lấy endpoint:

```java
int port = socket.getLocalPort();
java.net.SocketAddress bound = socket.getLocalSocketAddress();
boolean connected = socket.isConnected();
```

Trích đoạn trên giả định `DatagramSocket socket` đã được tạo. Không cần nhìn field nội bộ để biết port hoặc trạng thái kết nối mà public API đã cung cấp.

## 3. Những API hiện hành cần biết cho UDP

| API | Dùng cho việc gì? | Điều nên kiểm tra |
| --- | --- | --- |
| `DatagramSocket` | Gửi/nhận UDP kiểu blocking với `DatagramPacket` | Bind, timeout, địa chỉ/port, close |
| `DatagramPacket` | Vỏ chứa buffer byte và metadata đầu gửi/đích | `getData/getOffset/getLength/getAddress/getPort` |
| `InetAddress` | Địa chỉ IP của peer/local | Dùng địa chỉ explicit, đừng suy ra hostname luôn chỉ có IPv4 |
| `InetSocketAddress` | Gắn IP/host với port | Phân biệt local bind và destination |
| `DatagramChannel` | UDP qua NIO, `ByteBuffer` và selectable channel | Blocking/non-blocking, byte order, `flip`, address |
| `StandardProtocolFamily.INET/INET6` | Chọn họ giao thức khi tạo channel | Tương thích IPv4/IPv6, môi trường |
| `StandardSocketOptions` | Tên option public, ví dụ `SO_RCVBUF`, `SO_SNDBUF`, `SO_REUSEADDR`, `IP_MULTICAST_IF` | Option được hỗ trợ hay chỉ là hint |
| `NetworkInterface` | Liên hệ multicast với network interface | Chọn interface thực sự phù hợp và có quyền |
| `SocketTimeoutException` | Hết timeout của thao tác blocking có cấu hình | Timeout không khẳng định peer đã chết |
| `PortUnreachableException` | Có thể phát sinh khi remote không tới được | **Không được bảo đảm** luôn xuất hiện |

Chọn API dựa vào yêu cầu:

- Dịch vụ nhỏ cần gửi/nhận từng packet và timeout đơn giản: `DatagramSocket` thường đủ rõ.
- Nhiều socket, selector, non-blocking hoặc code đã dùng `ByteBuffer`: `DatagramChannel` thường phù hợp hơn.
- Multicast hiện đại có nhu cầu any-source/source-specific hoặc tương tác NIO: cân nhắc `DatagramChannel` / `MulticastChannel` thay vì phụ thuộc vào khác biệt implementation của `MulticastSocket`.

Không nhất thiết chuyển một codebase đang dùng `DatagramSocket` đúng chuẩn sang `DatagramChannel` chỉ vì Java 15 đã thay implementation. Hai API công khai có hợp đồng khác nhau và đều đáng học.

## 4. Gửi một datagram: luôn xác định đúng bytes và địa chỉ

Ví dụ trích đoạn (trong phương thức có `DatagramSocket socket` và `InetAddress remoteAddress`):

```java
byte[] payload = "PING".getBytes(java.nio.charset.StandardCharsets.UTF_8);
DatagramPacket outgoing = new DatagramPacket(
        payload, payload.length, remoteAddress, remotePort);
socket.send(outgoing);
```

Hành vi:

- `payload` là **byte thực tế** được gửi qua UDP, không phải object Java `String`.
- `payload.length` là **số byte** mà packet sẽ gửi.
- `remoteAddress` và `remotePort` xác định endpoint đích.
- `send(...)` hoàn tất **không chứng minh bên nhận đã nhận được packet**. UDP có thể mất, trễ, trùng hoặc đổi thứ tự.

Với dữ liệu có Unicode như tiếng Việt, số byte UTF-8 có thể **lớn hơn** số ký tự UTF-16 của `String.length()`. Không dùng `text.length()` làm độ dài `DatagramPacket` khi buffer đã chuyển sang UTF-8.

Ví dụ:

```java
String greeting = "Xin chào";
byte[] utf8 = greeting.getBytes(java.nio.charset.StandardCharsets.UTF_8);
System.out.println(utf8.length > greeting.length()); // true
```

Độ dài datagram phải tính từ **mảng byte**, không phải số ký tự hiển thị.

### Port 0 cho bài thử cục bộ

Khi bind vào `new InetSocketAddress(loopback, 0)`, hệ điều hành chọn một port còn trống. Kiểm tra bằng `getLocalPort()` thay vì hardcode port vào expected output. Cách này giúp tránh xung đột khi nhiều test chạy cùng máy.

Ví dụ loopback IPv4:

```java
InetAddress loopback = InetAddress.getByName("127.0.0.1");
try (DatagramSocket socket =
        new DatagramSocket(new InetSocketAddress(loopback, 0))) {
    System.out.println(socket.getLocalPort() > 0); // true nếu bind thành công
}
```

Các ví dụ hoàn chỉnh phía dưới dùng loopback để không cần mạng ngoài, nhưng vẫn đòi hỏi môi trường test cho phép tạo và dùng UDP socket.

## 5. Nhận một datagram: getLength không phải độ dài mảng

`DatagramSocket.receive(DatagramPacket)` nhận gói vào mảng byte do caller cung cấp. Khi trả về:

- `packet.getData()` là **toàn bộ buffer**, có thể lớn hơn dữ liệu vừa nhận.
- `packet.getOffset()` là vị trí bắt đầu vùng hợp lệ.
- `packet.getLength()` là **số byte dữ liệu đã nhận**.
- `packet.getAddress()` và `packet.getPort()` là endpoint **nguồn gửi**.

Ví dụ:

```java
byte[] buffer = new byte[2048];
DatagramPacket received = new DatagramPacket(buffer, buffer.length);
socket.receive(received);

String content = new String(
        received.getData(),
        received.getOffset(),
        received.getLength(),
        StandardCharsets.UTF_8);
```

Đây là **mã trích đoạn** và giả định `socket` cùng import tương ứng đã tồn tại. Cách giải mã chỉ phần buffer được nhận giúp tránh đọc các byte trống/cũ.

**Không làm thế này:**

```java
// Sai khi buffer lớn hơn message hoặc tái sử dụng buffer.
String wrong = new String(received.getData(), StandardCharsets.UTF_8);
```

Trích đoạn sai có thể đưa thêm `\0` hoặc byte dư từ thông điệp trước vào `String`. Độ dài cần lấy từ public API, không phải đoán theo byte cuối khác zero hay kiểm tra private buffer position của JDK.

### 5.1. Datagram dài hơn dung lượng nhận bị cắt

Một datagram là **đơn vị thông điệp**, không phải byte stream TCP. Nếu buffer nhận không đủ, dữ liệu vượt dung lượng có thể bị **truncation**; không có lần `receive` sau nào tự trả phần dư của chính datagram đó.

Vì vậy, ứng dụng cần:

- Quy định kích thước datagram tối đa ở tầng giao thức.
- Dành buffer đủ cho dữ liệu hợp lệ và giới hạn phía gửi.
- Đưa trường độ dài hoặc phiên bản payload vào protocol khi cần để phát hiện dữ liệu bị cắt.
- Không nghĩ rằng việc tăng `SO_RCVBUF` tự tăng kích thước **mảng byte** `DatagramPacket` đã cấp.
- Tránh các UDP payload rất lớn dễ bị IP fragmentation; nếu cần truyền dữ liệu lớn, cân nhắc chia khối có protocol ở tầng ứng dụng hoặc sử dụng transport có cơ chế reliability/stream phù hợp.

Trong chương trình đầy đủ, một buffer chỉ có 4 byte nhận gói `"HELLO-WORLD"` và chỉ giữ `"HELL"`.

### 5.2. Tái sử dụng DatagramPacket: thao tác an toàn là đặt lại capacity

Một `DatagramPacket` có **length** dùng làm giới hạn nhận và sau khi nhận cũng mô tả độ dài message. Khi tái sử dụng packet với một buffer lớn hơn, nên đặt lại giá trị length một cách rõ ràng:

```java
byte[] buffer = new byte[2048];
DatagramPacket packet = new DatagramPacket(buffer, buffer.length);

while (running) {
    packet.setLength(buffer.length);  // Đặt lại dung lượng nhận.
    socket.receive(packet);
    handle(packet.getData(), packet.getOffset(), packet.getLength());
}
```

Đây là **mã minh họa trong phương thức**, giả định `running`, `socket` và hàm `handle` đã được định nghĩa.

Đừng viết test dựa trên **chi tiết một implementation** rằng packet luôn tự điều chỉnh capacity khi tái sử dụng, hoặc ngược lại luôn giữ đúng length cũ. Tập trung vào điều bạn kiểm soát bằng API: **thiết lập length trước mỗi lần nhận**, đọc `getLength()` sau mỗi lần nhận.

Điểm này càng đáng chú ý với Java 15+: việc JDK thay implementation của DatagramSocket có thể làm lộ ra các test vốn vô tình phụ thuộc vào một hành vi không được mô tả rõ trong thiết kế ứng dụng.

### 5.3. Byte buffer có offset

`DatagramPacket(byte[] buf, int offset, int length)` cho phép nhận vào một phần mảng. Khi tạo String, bắt buộc dùng cả `getOffset()` và `getLength()`.

Không nhầm `length` với **chỉ số kết thúc**; nó là số byte có hiệu lực tính từ offset. Với packet có buffer được tái sử dụng, tuyệt đối không dùng `buffer.length` thay cho số byte thực nhận để parse JSON/protobuf hoặc lưu file.

## 6. UDP connect() không phải TCP handshake

`DatagramSocket.connect(InetAddress,int)` đặt **peer mặc định** cho socket UDP. Socket chỉ gửi/nhận datagram từ peer đó theo các quy tắc API; đây **không phải thủ tục bắt tay thiết lập phiên tin cậy**.

```java
sender.connect(remoteAddress, remotePort);
System.out.println(sender.isConnected());
```

Một `true` ở `isConnected()` chỉ cho biết trạng thái peer đã được cấu hình trong socket — **không xác nhận remote server có chạy, nhận được gói, đồng ý giao thức hay xác thực danh tính**.

Kết nối UDP cũng không bảo đảm:

- Dữ liệu giao thành công.
- Các packet đến đúng thứ tự.
- Không bị nhận trùng.
- Có mã hóa, xác thực nội dung hay chống giả mạo.
- Remote có cùng giao thức ứng dụng.

UDP không có luồng byte đáng tin cậy như TCP. Nếu ứng dụng cần reliability, retransmission/ACK, sequence number, checksum ứng dụng, timeout, congestion control hoặc xác thực, phải thiết kế các cơ chế phù hợp ở lớp trên hoặc chọn một transport đã hỗ trợ chúng.

### Lưu ý với lỗi ICMP

Trên socket UDP đã `connect`, một số thao tác có thể ném `PortUnreachableException` nếu hệ thống biết remote không đến được. Nhưng tài liệu Java nói **không bảo đảm exception sẽ phát sinh**. Không dùng sự vắng mặt của `PortUnreachableException` làm bằng chứng dịch vụ đích còn sống.

Nếu cần kiểm tra tình trạng peer, dùng protocol heartbeat/ACK hoặc request/response ở tầng ứng dụng có timeout và xác thực phù hợp.

## 7. Timeout và quản lý tài nguyên bằng API chính thức

Một lời gọi `receive` trên socket blocking có thể chờ vô thời hạn nếu không có datagram. Để test và production không treo vô hạn:

```java
socket.setSoTimeout(5000);
DatagramPacket packet = new DatagramPacket(new byte[1024], 1024);
try {
    socket.receive(packet);
} catch (java.net.SocketTimeoutException timeout) {
    // Không nhận được datagram trong khoảng chờ được cấu hình.
}
```

`setSoTimeout(5000)` đặt giới hạn chờ nhận là **5.000 ms**. Timeout không có nghĩa remote chắc chắn chết hay việc gửi chắc chắn thất bại. Socket vẫn còn hợp lệ để tiếp tục nếu không có lỗi khác.

**Không dùng** một hằng số timeout cho mọi môi trường mà không nghĩ tới latency, tải hệ thống, packet loss và yêu cầu ứng dụng. Test loopback có thể dùng timeout tương đối ngắn, production cần chính sách khác.

Đóng socket:

```java
try (DatagramSocket socket = new DatagramSocket()) {
    // send/receive...
} // socket.close() được gọi.
```

Với `DatagramChannel`, cũng sử dụng `try-with-resources`. Việc đóng channel ảnh hưởng tới socket được tạo từ chính channel đó theo hợp đồng public, chứ không cần gọi trực tiếp code implementation để đóng file descriptor.

## 8. DatagramSocket.getChannel() và DatagramChannel.socket()

Một bẫy khác khi nhìn JDK nội bộ: kể cả khi một bản JDK có thể triển khai `DatagramSocket` bằng cơ chế NIO, **không có nghĩa public `DatagramSocket.getChannel()` phải luôn trả một `DatagramChannel`**.

Tài liệu nói `DatagramSocket.getChannel()` chỉ trả channel gắn với socket **nếu socket thực sự được tạo từ `DatagramChannel.open(...)`**. Với socket tạo trực tiếp bằng constructor `new DatagramSocket(...)`, kết quả public API là `null`.

Ví dụ:

```java
try (DatagramSocket direct = new DatagramSocket()) {
    System.out.println(direct.getChannel() == null); // true
}
```

Ngược lại, khi bạn chủ động tạo một channel:

```java
try (DatagramChannel channel = DatagramChannel.open()) {
    DatagramSocket socket = channel.socket();
    System.out.println(socket.getChannel() == channel); // true
}
```

Đây là **hợp đồng quan hệ giữa hai API công khai**. Không cố lấy “NIO implementation ẩn” bằng reflection trên socket chỉ để gọi các chức năng mà public API không hứa.

Nếu muốn dùng `DatagramChannel`, **hãy tạo và giữ `DatagramChannel` ngay từ đầu**. Đừng lấy một `DatagramSocket` có sẵn rồi giả định có channel kèm theo.

## 9. DatagramChannel: phương án public NIO cho UDP

`DatagramChannel` dùng `ByteBuffer` và `SocketAddress` thay vì `DatagramPacket`:

```java
InetAddress loopback = InetAddress.getByName("127.0.0.1");
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET);
     DatagramChannel sender =
        DatagramChannel.open(StandardProtocolFamily.INET)) {

    receiver.bind(new InetSocketAddress(loopback, 0));
    sender.bind(new InetSocketAddress(loopback, 0));

    ByteBuffer data = StandardCharsets.UTF_8.encode("NIO");
    sender.send(data, receiver.getLocalAddress());

    ByteBuffer destination = ByteBuffer.allocate(64);
    SocketAddress from = receiver.receive(destination);
    destination.flip();
    String message = StandardCharsets.UTF_8.decode(destination).toString();
}
```

Đây là **mã minh họa cần imports**, còn chương trình hoàn chỉnh ở phần sau có đầy đủ imports và assertions.

Cần hiểu:

- `DatagramChannel.open(StandardProtocolFamily.INET)` tạo channel IPv4; `INET6` là lựa chọn khi cần IPv6 và môi trường hỗ trợ.
- `send(ByteBuffer, SocketAddress)` truyền các byte còn lại giữa `position` và `limit` của buffer nguồn.
- `receive(ByteBuffer)` ghi byte vào buffer đích từ `position` hiện tại, trả địa chỉ nguồn nếu nhận được datagram.
- `flip()` của `ByteBuffer` chuẩn bị buffer từ chế độ ghi sang đọc.
- Trong **blocking mode** (mặc định), `receive` có thể chờ datagram; với **non-blocking mode**, `receive` có thể trả `null` khi chưa có dữ liệu. Dùng `Selector` nếu kiến trúc cần multiplex nhiều channel.
- Không bê nguyên giả định `SO_TIMEOUT` của `DatagramSocket` vào vòng `DatagramChannel.receive` non-blocking; quản lý timeout/selector theo API NIO tương ứng.

**Lưu ý portability:** việc channel có thể cấu hình non-blocking, join multicast hay set socket options là lý do chọn NIO; không cần tham chiếu một lớp `sun.nio.ch` nào để đạt các tính năng này.

## 10. Socket options: public nhưng không phải mọi tác động đều bảo đảm tuyệt đối

Java cung cấp tên option công khai qua `StandardSocketOptions`, ví dụ:

```java
socket.setOption(StandardSocketOptions.SO_RCVBUF, 64 * 1024);
int actual = socket.getOption(StandardSocketOptions.SO_RCVBUF);
```

Tùy chọn `SO_RCVBUF` hay `SO_SNDBUF` là **gợi ý/cấu hình cho bộ đệm của network stack**; hệ điều hành và provider có thể áp dụng, giới hạn hoặc điều chỉnh giá trị. Đừng mặc định lần gọi set thành công chứng minh thực tế bộ đệm luôn có kích thước y hệt đã yêu cầu.

Kiểm tra bằng:

- `socket.supportedOptions()` để biết option public có được hỗ trợ.
- `getOption(...)` hoặc accessor cụ thể để xem giá trị hiệu dụng.
- Benchmark và test trong môi trường triển khai thật thay vì suy ra từ implementation.

Các thay đổi buffer socket **không đảm bảo việc nhận datagram không bị mất** khi ứng dụng xử lý chậm. UDP vẫn có thể drop do quá tải buffer, routing hoặc network.

### Multicast hiện đại

Với multicast, chú ý `NetworkInterface`, `IP_MULTICAST_IF`, `SO_REUSEADDR` và điều kiện OS/network. Theo API tài liệu, `DatagramChannel`/`MulticastChannel` là lựa chọn cần cân nhắc khi cần multicast có kiểm soát tốt, bao gồm source-specific multicast khi môi trường hỗ trợ.

Không dựa vào giả định rằng tất cả interface/stack hỗ trợ cùng một multicast group, hay socket bind địa chỉ cụ thể sẽ luôn nhận multicast trên mọi OS. Test multicast ở network triển khai, không chỉ test loopback.

Tránh các phương thức thiết lập system-wide socket implementation factory cũ; đây không phải cách khuyến nghị để tùy biến một ứng dụng UDP hiện đại.

## 11. Chương trình Java hoàn chỉnh: kiểm thử API công khai

Tạo tệp **`PublicUdpApiDemo.java`** bằng UTF-8. Chương trình dùng chính public API `DatagramSocket`, `DatagramPacket` và `DatagramChannel`. Nó hoạt động trên **loopback 127.0.0.1**, tự chọn port từ hệ điều hành và không cần internet.

Mục đích kiểm thử:

- Kiểm soát timeout và port ephemeral qua accessor public.
- Cấu hình UDP peer bằng `connect`, không suy đoán remote đã bắt tay.
- Gửi PING và nhận PONG, kiểm tra địa chỉ nguồn và độ dài nhận.
- Cố tình nhận datagram dài bằng buffer thật sự chỉ có bốn byte để quan sát truncate.
- Đặt lại capacity bằng `DatagramPacket.setLength(buffer.length)` trước lần nhận khác.
- Kiểm tra UTF-8 byte length và giao tiếp bằng `DatagramChannel`.
- Chứng minh hợp đồng `getChannel()`: socket tạo trực tiếp **không** tự có public channel, channel tạo qua NIO có socket liên kết.

### 11.1. Mã nguồn đầy đủ

```java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public final class PublicUdpApiDemo {
    private static void check(String label, boolean ok) {
        if (!ok) {
            throw new AssertionError(label + " FAILED");
        }
        System.out.println(label + "=PASS");
    }

    private static String text(DatagramPacket packet) {
        return new String(packet.getData(), packet.getOffset(),
                packet.getLength(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramSocket receiver =
                     new DatagramSocket(new InetSocketAddress(loopback, 0));
             DatagramSocket sender =
                     new DatagramSocket(new InetSocketAddress(loopback, 0))) {
            receiver.setSoTimeout(5000);
            sender.setSoTimeout(5000);

            check("timeoutConfigured", receiver.getSoTimeout() == 5000);
            check("ephemeralPorts",
                    receiver.getLocalPort() > 0 && sender.getLocalPort() > 0);

            sender.connect(loopback, receiver.getLocalPort());
            check("peerConfigured", sender.isConnected()
                    && sender.getPort() == receiver.getLocalPort());
            check("channelContract", sender.getChannel() == null);

            byte[] ping = "PING".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    ping, ping.length, loopback, receiver.getLocalPort()));

            byte[] buffer = new byte[64];
            DatagramPacket incoming = new DatagramPacket(buffer, buffer.length);
            receiver.receive(incoming);
            check("receivedPayload", text(incoming).equals("PING"));
            check("receivedSource", incoming.getPort() == sender.getLocalPort());
            check("receivedLength", incoming.getLength() == ping.length);

            byte[] pong = "PONG".getBytes(StandardCharsets.UTF_8);
            receiver.send(new DatagramPacket(
                    pong, pong.length, incoming.getAddress(), incoming.getPort()));
            DatagramPacket reply = new DatagramPacket(new byte[64], 64);
            sender.receive(reply);
            check("replyPayload", text(reply).equals("PONG"));

            byte[] longer = "HELLO-WORLD".getBytes(StandardCharsets.UTF_8);
            DatagramPacket small = new DatagramPacket(new byte[4], 4);
            sender.send(new DatagramPacket(
                    longer, longer.length, loopback, receiver.getLocalPort()));
            receiver.receive(small);
            check("shortBufferTruncates", small.getLength() == 4
                    && text(small).equals("HELL"));

            // Explicitly restore the full receive capacity before reuse.
            incoming.setLength(buffer.length);
            sender.send(new DatagramPacket(
                    longer, longer.length, loopback, receiver.getLocalPort()));
            receiver.receive(incoming);
            check("resetCapacity", text(incoming).equals("HELLO-WORLD"));

            String international = "Xin chào";
            byte[] utf8 = international.getBytes(StandardCharsets.UTF_8);
            check("utf8ByteLength", utf8.length > international.length());
        }

        try (DatagramChannel channelReceiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel channelSender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            channelReceiver.bind(new InetSocketAddress(loopback, 0));
            channelSender.bind(new InetSocketAddress(loopback, 0));

            ByteBuffer source = StandardCharsets.UTF_8.encode("NIO");
            int sent = channelSender.send(source, channelReceiver.getLocalAddress());
            ByteBuffer target = ByteBuffer.allocate(64);
            SocketAddress from = channelReceiver.receive(target);
            target.flip();

            check("nioDatagram", sent == 3 && from != null
                    && StandardCharsets.UTF_8.decode(target).toString()
                            .equals("NIO"));
            check("publicChannelLink",
                    channelReceiver.socket().getChannel() == channelReceiver);
        }
    }
}
```

### 11.2. Biên dịch và chạy

Với JDK 17 hoặc mới hơn, từ thư mục chứa `PublicUdpApiDemo.java`:

```bash
javac --release 17 -encoding UTF-8 PublicUdpApiDemo.java
java PublicUdpApiDemo
```

**Stdout chính xác trong môi trường cho phép UDP loopback:**

```text
timeoutConfigured=PASS
ephemeralPorts=PASS
peerConfigured=PASS
channelContract=PASS
receivedPayload=PASS
receivedSource=PASS
receivedLength=PASS
replyPayload=PASS
shortBufferTruncates=PASS
resetCapacity=PASS
utf8ByteLength=PASS
nioDatagram=PASS
publicChannelLink=PASS
```

Chương trình dùng thời gian chờ để tránh `DatagramSocket.receive` block vô hạn nếu môi trường mạng cấm UDP; NIO channel ở đoạn cuối dùng blocking receive sau khi đã gửi packet trong cùng process. Môi trường sandbox/CI chặn socket hoặc UDP có thể khiến bài test **không chạy được** dù code đã biên dịch hợp lệ. Khi đó cần phân biệt hạn chế môi trường với lỗi trong Java, thay vì “fix” bằng cách lấy quyền truy cập implementation nội bộ.

### 11.3. Diễn giải 13 kết quả

| Kết quả | Hợp đồng API được kiểm tra |
| --- | --- |
| `timeoutConfigured=PASS` | `setSoTimeout/getSoTimeout` công khai hoạt động |
| `ephemeralPorts=PASS` | Bind port 0 và `getLocalPort` trả port được OS chọn |
| `peerConfigured=PASS` | `connect/isConnected/getPort` phản ánh peer đã cấu hình |
| `channelContract=PASS` | Socket tạo trực tiếp có `getChannel() == null`, không đồng nghĩa JDK không dùng NIO nội bộ |
| `receivedPayload=PASS` | `getData/getOffset/getLength` giải mã đúng PING |
| `receivedSource=PASS` | `getPort` sau receive phản ánh nguồn gửi |
| `receivedLength=PASS` | Độ dài nhận từ packet bằng bốn byte PING |
| `replyPayload=PASS` | Dùng địa chỉ/port nhận được để gửi reply, đọc PONG |
| `shortBufferTruncates=PASS` | Buffer bốn byte chỉ nhận bốn byte đầu của message dài |
| `resetCapacity=PASS` | `setLength(buffer.length)` trước khi tái sử dụng packet cho đủ dung lượng |
| `utf8ByteLength=PASS` | Số byte UTF-8 có thể khác `String.length()` |
| `nioDatagram=PASS` | NIO dùng `send/receive` với `ByteBuffer` và địa chỉ nguồn |
| `publicChannelLink=PASS` | Socket lấy từ `DatagramChannel.socket()` có liên kết channel public theo contract |

**Tại sao test không in số port hoặc tên implementation?** Port động do OS chọn; tên class/stack nội bộ do JDK quyết định. Test chỉ khẳng định những điều được public API bảo đảm. Đây chính là trọng tâm của bài.

## 12. Hướng xử lý lỗi và khác biệt môi trường

### 12.1. Timeout không phải bằng chứng “server chết”

`SocketTimeoutException` khi nhận nghĩa là trong khoảng chờ đã cấu hình, socket **không nhận được một datagram phù hợp**. Có thể vì packet mất, firewall, network, peer không chạy, lỗi địa chỉ, packet bị lọc hoặc scheduler chậm.

Ứng dụng có thể retry theo protocol, nhưng phải cân nhắc **idempotency**, giới hạn số lần, backoff và chính sách tránh duplicate/replay. Không mặc định mọi request UDP có thể lặp vô hạn.

### 12.2. PortUnreachableException không phải thông báo lỗi bắt buộc

Ngay cả khi UDP remote port đóng, hệ điều hành có thể không gửi hoặc không phân phối ICMP error theo cách Java nhận được. Vì vậy **không thấy exception** không chứng minh remote thật sự lắng nghe. Lập health check/ACK ở tầng ứng dụng khi có yêu cầu.

### 12.3. IPv4 và IPv6

Một ứng dụng có thể chạy trên máy chỉ có IPv6 hoặc dual-stack. Việc “mặc định open socket” chọn họ địa chỉ nào còn phụ thuộc môi trường. Trong bài test, chúng ta **chỉ rõ loopback IPv4 127.0.0.1** và `StandardProtocolFamily.INET` cho NIO để tránh phụ thuộc default.

Trong code production, cần hỗ trợ DNS trả cả IPv4/IPv6, kiểm tra route và network interface thật. Không so sánh tên host nội bộ hoặc ép cast implementation để suy ra network family; dùng các API public như `InetAddress` và `StandardProtocolFamily` khi thích hợp.

### 12.4. Socket buffer vs message buffer

`SO_RCVBUF` là cấu hình/hint cho network stack; `DatagramPacket.getData()` là mảng byte Java do ứng dụng cấp. Tăng `SO_RCVBUF` không có nghĩa một `new byte[64]` có thể nhận đầy đủ datagram 1.000 byte.

Muốn giảm truncation cần **buffer của ứng dụng đủ lớn** và protocol có giới hạn message hợp lý. Còn để giảm drop khi xử lý chậm, cân nhắc điều chỉnh socket buffer, kiến trúc xử lý và kiểm thử tải; không có tham số duy nhất bảo đảm không bao giờ mất UDP packet.

## 13. Checklist khi nâng JDK hoặc đổi implementation

| Kiểm tra | Đúng trọng tâm API công khai |
| --- | --- |
| Dự án chỉ import `java.net` / `java.nio` / `java.nio.channels` chuẩn cho UDP? | Không phụ thuộc `sun.*` hoặc tên lớp nội bộ |
| Có dùng reflection vào field private của socket không? | Loại bỏ; tìm accessor/method public |
| Có dựa vào system property để bật implementation datagram “cũ” không? | Tránh, không coi là hợp đồng lâu dài |
| Có giải mã đúng `getOffset/getLength` không? | Không dùng cả `getData().length` nếu dữ liệu ngắn hơn |
| Có reset `packet.setLength(capacity)` trước khi tái sử dụng? | Rõ ràng và tránh suy luận từ implementation |
| Có quy tắc buffer tối đa cho protocol không? | Tránh truncation, hạn chế UDP payload lớn |
| Có `setSoTimeout` hoặc selector phù hợp? | Tránh block vô hạn trong server/test |
| Có dùng `try-with-resources` để đóng socket/channel? | Tránh leak tài nguyên |
| Có hiểu `connect` UDP không chứng minh peer tồn tại? | Nếu cần reliability phải có ACK/tầng ứng dụng |
| Có test trên IPv4/IPv6 và OS cần hỗ trợ? | Tránh giả định stack mặc định |
| Có kiểm thử multicast trên interface thật? | Không dựa vào hành vi loopback/wildcard không bảo đảm |
| Có kết luận dựa trên `getChannel()` đúng public contract? | Không suy đoán delegate nội bộ |
| Có giả định `PortUnreachableException` luôn xuất hiện? | Không; exception này không được bảo đảm |
| Có phân biệt byte length với Java String length? | Dùng UTF-8 và `byte[].length` |
| Có đánh giá bảo mật/anti-replay của tầng ứng dụng? | UDP không tự mã hóa hay xác thực |

## 14. Các sai lầm điển hình

| Sai lầm | Rủi ro | Cách thay |
| --- | --- | --- |
| Import hoặc phản chiếu `sun.nio.ch.*` để dùng UDP | JDK nâng cấp có thể đổi class/field/method | Dùng `DatagramSocket`/`DatagramChannel` public |
| Đặt phụ thuộc vào implementation flag của JDK cũ | Flag có thể bị bỏ hoặc có nghĩa khác | Xác minh contract và test trên JDK đích |
| Suy ra `getChannel()!=null` vì JDK dùng NIO phía dưới | Public `getChannel` chỉ có giá trị trong trường hợp socket được tạo từ channel | Khởi tạo `DatagramChannel.open` nếu cần NIO |
| Giải mã toàn bộ `packet.getData()` | Đọc byte trống/byte cũ | Dùng `getOffset/getLength` |
| Giữ `getLength()` của lần nhận trước làm capacity | Bất định/giới hạn nhận ở lần tiếp theo | Đặt lại `setLength(buffer.length-offset)` |
| Dùng `String.length()` làm độ dài UDP payload UTF-8 | Có thể cắt mất một phần byte của chữ có dấu | Dùng `bytes.length` |
| Tin `send()` thành công nghĩa là đã giao | UDP không có ACK bắt buộc | Thiết kế protocol ACK/timeout/retry |
| Tin `isConnected()` như TCP handshake | UDP chỉ cấu hình peer | Kiểm tra tầng ứng dụng nếu cần |
| Nghĩ tăng `SO_RCVBUF` sẽ tăng `byte[]` | Hai loại buffer khác nhau | Cấp buffer nhận đúng kích thước |
| Dùng `PortUnreachableException` để kiểm tra sức khỏe remote | Exception không bảo đảm phát sinh | Health check/ACK riêng |
| Dùng `DatagramChannel.receive` non-blocking mà chờ nó luôn block | Non-blocking có thể trả `null` ngay | Selector/poll theo API NIO |
| Cho rằng packet dài sẽ tự chia qua nhiều lần `receive` | UDP giữ biên thông điệp, phần vượt buffer bị bỏ | Dùng giao thức chunking hoặc transport thích hợp |
| Không đóng socket khi lỗi | Tốn port/file descriptor | `try-with-resources` |
| Test hardcode port ephemeral hoặc class name JDK | Test không ổn định giữa máy và release | Kiểm tra giá trị public và invariant |
| Dựa vào thứ tự đến của các gói UDP | UDP không cam kết thứ tự | Sequence number và reorder logic nếu cần |

## 15. Bài tập tự kiểm tra

**Bài 1.** Một JDK mới thay implementation của `DatagramSocket`, nhưng những lệnh `send/receive/getLength` vẫn chạy đúng. Ứng dụng có cần phản chiếu lớp implementation cũ để “tương thích Java 15” không?

**Đáp án:** Không. JEP 373 nhấn mạnh sự thay đổi **bên dưới API**; ứng dụng phải phụ thuộc vào hợp đồng public.

**Bài 2.** Bạn tạo `DatagramSocket socket = new DatagramSocket();`, gọi `socket.getChannel()` và thấy `null`. Có kết luận được JDK chắc chắn không dùng bất kỳ cơ chế NIO nội bộ nào không?

**Đáp án:** Không. `getChannel()` mô tả **channel public gắn với socket được tạo từ DatagramChannel.open**; nó không phải API tiết lộ delegate nội bộ của JDK.

**Bài 3.** Receiver tạo `new DatagramPacket(new byte[4],4)` rồi nhận datagram chứa `"HELLO-WORLD"`. Có lấy tiếp phần `"O-WORLD"` trong `receive` kế tiếp không?

**Đáp án:** Không. Datagram bị truncate tới bốn byte. UDP không cung cấp byte stream để đọc “phần còn lại” của cùng gói bằng lần nhận sau.

**Bài 4.** Sau khi nhận PING dài bốn byte vào buffer 64 byte, bạn muốn tái sử dụng packet để nhận message dài hơn. Nên làm gì trước `receive`?

**Đáp án:** Chủ động đặt `packet.setLength(buffer.length - packet.getOffset())` hoặc capacity phù hợp. Đừng dựa vào cách một JDK xử lý reuse ngầm.

**Bài 5.** `socket.connect(remote,port)` thành công và `isConnected()==true`. Có thể kết luận remote đã nhận packet hoặc đã xác minh danh tính chưa?

**Đáp án:** Không. Kết nối UDP chỉ cấu hình peer, không thực hiện handshake tin cậy như TCP và không xác thực danh tính.

**Bài 6.** Một socket UDP không nhận được phản hồi và `receive` ném `SocketTimeoutException`. Có chắc dịch vụ remote đã chết không?

**Đáp án:** Không. Network/firewall/packet loss/lịch xử lý cũng có thể dẫn tới timeout; có thể retry theo chính sách nhưng cần giới hạn và chống duplicate.

**Bài 7.** Khi dùng `DatagramChannel.receive(ByteBuffer)`, tại sao thường cần gọi `buffer.flip()` trước khi decode?

**Đáp án:** Byte được nhận vào buffer từ vị trí ghi hiện tại. `flip()` đặt limit tại vị trí vừa ghi và position về đầu để giải mã **đúng các byte đã nhận**.

**Bài 8.** Một chương trình dùng `StandardSocketOptions.SO_RCVBUF` và set 64 KiB, nhưng mảng Java nhận là `new byte[32]`. Datagram dài 200 byte sẽ tự được lưu đủ vào mảng này không?

**Đáp án:** Không. Socket receive buffer của OS khác với message buffer mà ứng dụng cung cấp. Mảng 32 byte không chứa được toàn bộ datagram 200 byte; cần cấp buffer thích hợp và giới hạn protocol.

## Ghi nhớ

**Dựa vào API công khai nghĩa là kiểm thử những gì Java cam kết, không đoán cách JDK cài đặt.** Với UDP, sử dụng `DatagramSocket`/`DatagramPacket` hoặc `DatagramChannel` đúng theo yêu cầu; lấy dữ liệu từ `getData/getOffset/getLength`, cấu hình timeout bằng public API, quản lý buffer, close và xử lý UDP packet loss/truncation đúng. Java 15 đã hiện đại hóa implementation của DatagramSocket qua **JEP 373**, nhưng đó không phải lời mời gọi ứng dụng truy cập implementation hoặc dựa vào cờ nội bộ. Những kỹ thuật này áp dụng trên các JDK hiện đại và giúp code dễ nâng cấp, kiểm thử và vận hành hơn.

### Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 373 — Reimplement the Legacy DatagramSocket API (Java 15)](https://openjdk.org/jeps/373)
- [Java SE 17 — DatagramSocket: send, receive, connect, timeout, getChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html)
- [Java SE 17 — DatagramPacket: getData, getOffset, getLength, setLength](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramPacket.html)
- [Java SE 17 — DatagramChannel, send/receive, blocking mode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [Java SE 17 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html)
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
