# Datagram và khác biệt với luồng TCP trong Java NIO

## 1. Vấn đề cần hiểu

Khi truyền dữ liệu qua mạng, ứng dụng có thể cần gửi **từng thông điệp độc lập** hoặc duy trì **một luồng byte liên tục**. Hai mô hình thường gặp:

- **Datagram:** mỗi lần gửi tạo một gói/thông điệp có ranh giới riêng. Trên Internet, mô hình quen thuộc là **UDP** (User Datagram Protocol); Java NIO cung cấp `DatagramChannel`.
- **TCP stream:** TCP truyền một **luồng byte có thứ tự** giữa hai đầu đã kết nối, không gắn ý nghĩa ranh giới thông điệp vào từng lời gọi ghi. Java NIO thường dùng `SocketChannel` và `ServerSocketChannel`.

Sự khác biệt quan trọng không chỉ là “UDP nhanh, TCP chậm”. Cần hiểu **ranh giới thông điệp, kết nối, độ tin cậy, thứ tự, hành vi đọc/ghi, kích thước dữ liệu, điều khiển luồng, bảo mật và cách thiết kế giao thức ứng dụng**.

Mục tiêu bài này:

1. Hiểu datagram là gì, mỗi datagram mang địa chỉ đích/nguồn như thế nào.
2. Dùng `DatagramChannel.send`, `receive`, `bind`, `connect` trong Java NIO.
3. Phân biệt datagram với byte stream mà `SocketChannel` đọc/ghi.
4. Xử lý `ByteBuffer`, chế độ blocking/non-blocking và `Selector`.
5. Chọn UDP/datagram hoặc TCP phù hợp và nhận biết các lỗi thiết kế phổ biến.

> **Phạm vi:** đây là bài về Java core I/O/NIO, tập trung vào semantics của datagram UDP và TCP stream. UDP không đồng nghĩa với mọi giao thức dựa trên UDP; chẳng hạn một giao thức tầng trên có thể tự bổ sung xác thực, truyền lại hoặc kiểm soát tắc nghẽn.

## 2. Hai mô hình nhìn từ ứng dụng

### UDP datagram: từng thông điệp riêng

Một ứng dụng gửi ba datagram:

```text
Sender                         Network                      Receiver

Datagram #1: ["ABC"] ---------\
Datagram #2: ["DEF"] ----------> [có thể mất/đảo thứ tự] ---> receive(): một datagram
Datagram #3: ["GHI"] ---------/

Ranh giới ["ABC"], ["DEF"], ["GHI"] thuộc từng gói.
```

Một lần `DatagramChannel.send(buffer, address)` gửi nội dung remaining như **một datagram**. Một lần `receive(buffer)` nhận **một datagram** (nếu có) và trả địa chỉ của bên gửi. Không ghép hai datagram thành một lời gọi `receive` và không chia một datagram thành các phần để các lần `receive` sau tự nhận tiếp.

Tuy nhiên, datagram có thể **bị mất, đến trễ, bị nhân bản hoặc đến không theo thứ tự**. Sender không nhận được cam kết delivery chỉ từ việc `send` trả về số byte đã gửi. Chương trình muốn reliability phải tự xây cơ chế hoặc chọn giao thức tầng trên thích hợp.

### TCP: một luồng byte có thứ tự

Ứng dụng TCP gọi ghi ba lần:

```text
Sender SocketChannel                      Receiver SocketChannel

write("ABC")
write("DEF")  ----->  TCP byte stream -----> read() có thể trả:
write("GHI")                                "ABCDEF", hoặc
                                            "AB" rồi "CDEFGHI", hoặc
                                            các phân đoạn khác
                        Nội dung logic: "ABCDEFGHI"
```

TCP đảm bảo thứ tự byte và cơ chế truyền lại/kiểm soát lỗi khi kết nối hoạt động bình thường, nhưng **không giữ ranh giới giữa các lần `write`**. Một lần `read` có thể trả một phần thông điệp, nhiều thông điệp hoặc không có byte ở chế độ non-blocking. Ứng dụng phải tự định nghĩa framing, chẳng hạn tiền tố độ dài, delimiter, hoặc định dạng tự mô tả.

**Điểm cốt lõi:** UDP giữ ranh giới gói ở API nhưng không bảo đảm giao hàng; TCP hỗ trợ luồng byte tin cậy có thứ tự trong kết nối, nhưng không giữ ranh giới thông điệp ứng dụng.

## 3. Bảng so sánh datagram UDP và TCP stream

| Tiêu chí | UDP / DatagramChannel | TCP / SocketChannel |
|---|---|---|
| Mô hình dữ liệu | Datagram độc lập, mỗi gói có ranh giới | Luồng byte liên tục |
| Thiết lập kết nối | Không bắt buộc handshake để gửi UDP | TCP cần kết nối và bắt tay trước khi trao đổi thông thường |
| API gửi NIO | `send(ByteBuffer, SocketAddress)`; khi connected có `write` | `write(ByteBuffer)` trên kết nối TCP |
| API nhận NIO | `receive(ByteBuffer)` trả `SocketAddress` của gói | `read(ByteBuffer)` trả số byte, `-1` khi EOF của stream |
| Ranh giới thông điệp | Giữ theo datagram; gói quá lớn so với receive buffer bị cắt mất phần dư | Không có ranh giới theo từng lần write; ứng dụng tự framing |
| Bảo đảm dữ liệu tới đích | Không có bảo đảm ở tầng UDP | Có truyền lại, thứ tự và cơ chế kiểm soát lỗi trong kết nối còn hoạt động |
| Thứ tự/nhân bản | Có thể đảo thứ tự, trùng hoặc mất gói | Ứng dụng thấy byte đúng thứ tự; không tự hiển thị dữ liệu lặp do retransmission |
| Kích thước | Mỗi datagram có giới hạn; MTU và fragmentation quan trọng | Byte stream không có khái niệm “một message kích thước MTU” ở API |
| Flow/congestion control | UDP không cung cấp sẵn bảo đảm tương đương TCP | TCP có flow control và congestion control |
| Phát hiện peer không khả dụng | Khó và không đồng nhất; `send` thành công không chứng minh peer nhận | Kết nối có trạng thái, có thể thấy EOF/lỗi, nhưng phát hiện sự cố vẫn có thể bị trễ |
| Broadcast/multicast | UDP phù hợp với các cơ chế này nếu OS/network hỗ trợ | TCP unicast kết nối giữa hai endpoint |
| Selector | `DatagramChannel` hỗ trợ `OP_READ`, `OP_WRITE` | `SocketChannel` hỗ trợ `OP_READ`, `OP_WRITE`, `OP_CONNECT` |
| Khi nào thường chọn | Telemetry, discovery, game state, real-time với chính sách mất gói rõ ràng | HTTP thông thường qua TCP, RPC theo stream, chuyển file, dữ liệu cần truyền đủ có thứ tự |

Bảng này mô tả **UDP/TCP ở mức transport**. Một giao thức ứng dụng trên UDP có thể xây thêm reliability, ví dụ truyền lại và kiểm soát congestion. Khi đó ứng dụng **không còn dựa vào UDP thuần** để đạt các tính năng đó.

## 4. `DatagramChannel` trong Java NIO

`java.nio.channels.DatagramChannel` là selectable channel để gửi/nhận các datagram. Một số API cốt lõi:

| API | Ý nghĩa |
|---|---|
| `DatagramChannel.open()` | Tạo channel datagram với protocol family mặc định do hệ thống lựa chọn |
| `DatagramChannel.open(StandardProtocolFamily.INET)` | Tạo channel cho IPv4 |
| `bind(SocketAddress local)` | Gắn socket vào địa chỉ/cổng cục bộ; truyền `null` để hệ thống chọn |
| `getLocalAddress()` | Đọc địa chỉ/cổng cục bộ khi đã bind |
| `send(ByteBuffer src, SocketAddress target)` | Gửi một datagram tới target |
| `receive(ByteBuffer dst)` | Nhận một datagram, trả địa chỉ sender; có thể trả `null` nếu channel non-blocking và chưa có gói |
| `connect(SocketAddress remote)` | Gắn một địa chỉ peer vào UDP channel; không phải TCP handshake |
| `read(ByteBuffer dst)` / `write(ByteBuffer src)` | I/O trên DatagramChannel **đã connect**, theo peer đã định |
| `disconnect()` | Bỏ peer gắn trước đó, không có TCP close handshake |
| `configureBlocking(false)` | Chuyển sang non-blocking, có thể đăng ký với `Selector` |
| `setOption(...)` | Cấu hình socket options có hỗ trợ, ví dụ receive/send buffer |

Thông thường làm việc với `Path` là FileChannel, còn làm việc với địa chỉ mạng là `SocketAddress` / `InetSocketAddress`. Hai khái niệm đều là “channel” nhưng không có cùng API dữ liệu.

### Bind và địa chỉ

Server UDP thường bind vào cổng xác định:

```java
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress("127.0.0.1", 9000));
    // Nhận datagram gửi tới địa chỉ/cổng này.
}
```

Đây là **đoạn minh họa**, cổng 9000 có thể đang được sử dụng. `127.0.0.1` là loopback IPv4, chỉ để thử giữa các tiến trình trên cùng máy. Muốn lắng nghe trên một địa chỉ mạng thật, cần chọn bind address, firewall và quyền tương ứng.

Có thể dùng cổng `0` để hệ điều hành chọn cổng còn trống, ví dụ `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)` rồi lấy cổng được gán từ `getLocalAddress()`. Cách này thuận tiện trong bài thử tự động và tránh tranh chấp một số cổng cố định.

### Gửi datagram

```java
ByteBuffer outbound = StandardCharsets.UTF_8.encode("PING");
int bytes = channel.send(
        outbound,
        new InetSocketAddress("127.0.0.1", 9000)
);
```

Đây là đoạn minh họa, cần các import `ByteBuffer`, `StandardCharsets` và `InetSocketAddress` cùng channel đã mở. `send` lấy các byte từ vùng `[position, limit)` của buffer, và khi gửi thành công sẽ tiến buffer position theo số byte gửi.

Với UDP, dữ liệu của một lần send được xử lý như **một datagram**, chứ không phải “một phần stream đang tiếp diễn”. Nếu channel **non-blocking** và không thể gửi ngay, `send` có thể trả `0`. Nếu lỗi mạng/tài nguyên hoặc kích thước gói không hợp lệ, có thể ném `IOException`. Đừng tự nối một lệnh send trả `0` với giả định “phần gói đầu đã được gửi”; phải quản lý retry của **cùng datagram** theo kết quả và trạng thái buffer.

### Nhận datagram

```java
ByteBuffer incoming = ByteBuffer.allocate(2048);
SocketAddress source = channel.receive(incoming);

if (source != null) {
    incoming.flip();
    String text = StandardCharsets.UTF_8.decode(incoming).toString();
    System.out.println(text);
}
```

Đây cũng là đoạn minh họa. `receive` ghi nội dung gói vào buffer từ position hiện tại, cập nhật position, rồi trả địa chỉ người gửi. Khi channel non-blocking, nếu chưa có datagram, `source == null`; khi blocking, lời gọi có thể chờ gói đến.

**Ranh giới quan trọng:** nếu datagram dài hơn `incoming.remaining()`, phần không vừa bị **bỏ** theo semantics nhận datagram; lần receive sau không nhận tiếp “phần đuôi” của gói đó. Vì vậy hãy chọn dung lượng buffer thích hợp với **kích thước message tối đa của giao thức**, kèm chính sách từ chối/kiểm tra message quá dài. `flip()` chuyển buffer sang chế độ đọc phần byte mới nhận, nhưng không làm sống lại phần byte đã bị cắt.

## 5. Ví dụ Java 17+: gửi và nhận qua loopback bằng DatagramChannel + Selector

Ví dụ hoàn chỉnh dùng hai `DatagramChannel` trên cùng máy:

1. Receiver bind vào loopback IPv4 cổng do hệ điều hành chọn.
2. Receiver chuyển sang non-blocking và đăng ký `SelectionKey.OP_READ` với `Selector`.
3. Sender gửi một datagram chứa đúng bốn byte ASCII `PING`.
4. Selector chờ tối đa 3 giây để tránh ví dụ treo vô hạn nếu datagram không đến.
5. Receiver nhận datagram và in nội dung cùng một xác nhận rằng địa chỉ nguồn đã được trả về.

Tạo tệp **`DatagramVsTcpDemo.java`**:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class DatagramVsTcpDemo {
    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             Selector selector = Selector.open()) {

            receiver.bind(new InetSocketAddress(loopback, 0));
            receiver.configureBlocking(false);
            receiver.register(selector, SelectionKey.OP_READ);

            sender.bind(new InetSocketAddress(loopback, 0));

            SocketAddress destination = receiver.getLocalAddress();
            ByteBuffer outbound = StandardCharsets.US_ASCII.encode("PING");

            int sent = sender.send(outbound, destination);
            if (sent != 4 || outbound.hasRemaining()) {
                throw new IOException("Could not send complete PING datagram");
            }

            if (selector.select(3000) == 0) {
                throw new IOException("Timed out waiting for UDP datagram");
            }

            ByteBuffer incoming = ByteBuffer.allocate(128);
            SocketAddress source = receiver.receive(incoming);
            if (source == null) {
                throw new IOException("No datagram available after select");
            }

            incoming.flip();
            String message =
                    StandardCharsets.US_ASCII.decode(incoming).toString();

            System.out.println("Sent bytes: " + sent);
            System.out.println("Received: " + message);
            System.out.println("Sender identified: " + (source != null));
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac DatagramVsTcpDemo.java
java DatagramVsTcpDemo
```

Trên máy cho phép UDP loopback và datagram được chuyển tới receiver trong thời gian chờ, stdout:

```text
Sent bytes: 4
Received: PING
Sender identified: true
```

Giải thích:

- `StandardProtocolFamily.INET` chọn IPv4; hai channel dùng địa chỉ `127.0.0.1`.
- Cổng `0` nhờ OS cấp một cổng có thể sử dụng. `receiver.getLocalAddress()` trả cổng thật nên ví dụ không phải hardcode một cổng.
- `StandardCharsets.US_ASCII.encode("PING")` tạo buffer có bốn byte cần gửi. `send` tiêu thụ bốn byte, làm `outbound.hasRemaining()` thành `false`.
- Receiver đăng ký `OP_READ`, còn `selector.select(3000)` chờ tối đa ba giây. `DatagramChannel` phải ở non-blocking mode khi đăng ký với selector.
- `receive(incoming)` trả `SocketAddress` của sender nếu lấy được datagram; `incoming.flip()` chuẩn bị đọc đúng số byte vừa nhận.
- Chương trình không in địa chỉ/cổng thật, vì cổng do OS cấp thay đổi theo mỗi lần chạy.
- Không in/chạy một ví dụ TCP riêng; phần khác biệt với TCP được phân tích bằng sơ đồ và quy tắc framing ở dưới.

**Giới hạn:** UDP vốn không bảo đảm delivery. Dù gửi tới loopback thường thành công, không thể khẳng định mọi môi trường đều trả đúng stdout; nếu firewall, OS hoặc tài nguyên mạng chặn, chương trình ném `IOException`, kể cả timeout. Điều này cố ý làm lỗi rõ ràng thay vì treo ở blocking `receive` mãi.

`Selector` báo readiness, không bảo đảm tuyệt đối rằng trong mọi trạng thái hệ thống khi gọi `receive` sẽ chắc chắn có gói; vì vậy ví dụ vẫn kiểm tra `source == null`. Trong ứng dụng thực, sự kiện và tập `selectedKeys()` thường được xử lý trong event loop để phục vụ nhiều channel; với một receiver duy nhất, ví dụ có thể kiểm tra trực tiếp sau khi select trả số dương.

## 6. Đọc/ghi không blocking và Selector

`DatagramChannel` kế thừa `SelectableChannel`. Với `configureBlocking(false)`:

- `receive(dst)` có thể trả `null` nếu chưa có gói.
- `send(src, target)` có thể trả `0` nếu không thể gửi ngay mà không block.
- Có thể đăng ký channel với `Selector` dùng `SelectionKey.OP_READ` và `OP_WRITE`.
- `OP_READ` chỉ báo sẵn sàng nhận theo thông tin tại lúc selector kiểm tra; xử lý phải chấp nhận tình trạng không còn dữ liệu khi thật sự receive.
- Đăng ký `OP_WRITE` thường cần quản lý interest ops cẩn thận vì socket có thể gần như luôn được coi là writable, gây vòng lặp CPU nếu kích hoạt nó liên tục mà không có gói chờ gửi.
- Không dùng `OP_ACCEPT` cho `DatagramChannel` (không có khái niệm accept TCP) hay `OP_CONNECT` như với `SocketChannel` (UDP `connect` không phải kết nối TCP đang chờ hoàn tất).

Cấu trúc event loop thường gặp:

```java
// Mã minh họa: channel đã configureBlocking(false) và đăng ký OP_READ.
while (running) {
    selector.select();

    var iterator = selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (key.isValid() && key.isReadable()) {
            ByteBuffer packet = ByteBuffer.allocate(2048);
            SocketAddress from = ((DatagramChannel) key.channel())
                    .receive(packet);
            if (from != null) {
                packet.flip();
                // Giải mã đúng một datagram và xử lý from.
            }
        }
    }
}
```

Đây **không phải chương trình chạy độc lập**; `running`, `selector`, cấu hình channel, chính sách quản lý buffer và đóng tài nguyên cần được định nghĩa bên ngoài. Vòng lặp chọn khóa chỉ là ví dụ tổ chức event loop. Trong hệ thống thực phải xử lý exceptions, giới hạn tốc độ, timeouts, malformed packets và shutdown.

Một datagram đến không có nghĩa sender đã thực hiện handshake. UDP server không cần một `ServerSocketChannel.accept()`; chỉ cần channel bind đúng cổng để nhận message.

## 7. Connected DatagramChannel không biến UDP thành TCP

`DatagramChannel.connect(remote)` có thể khiến tên API dễ gây nhầm. Với UDP, `connect` **gắn một địa chỉ peer vào socket**, cho phép I/O kiểu `read(ByteBuffer)` và `write(ByteBuffer)`, và thường chỉ nhận datagram từ peer đó theo ngữ nghĩa channel. Nó **không thực hiện handshake TCP**.

Ví dụ minh họa:

```java
SocketAddress remote = new InetSocketAddress("127.0.0.1", 9000);

try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.connect(remote);

    ByteBuffer request = StandardCharsets.US_ASCII.encode("HELLO");
    channel.write(request);          // Gửi datagram tới peer đã kết nối.

    // channel.read(response) sẽ đọc từ peer này; nếu đang blocking
    // có thể chờ, vì UDP không bảo đảm có response.
}
```

Đoạn này cần các import tương ứng; không tự chạy như một client hoàn chỉnh vì không có server trên cổng 9000.

Sau `connect`:

- `channel.isConnected()` có thể trả `true`, nhưng không chứng minh peer thực sự đang hoạt động.
- `read` và `write` có thể dùng địa chỉ peer đã lưu. Khi unconnected, `read/write` không hợp lệ và có thể ném `NotYetConnectedException`.
- Việc nhận thông điệp được gắn với peer đã kết nối; không hiểu đây là kết nối có session state, sequence number và cơ chế truyền lại kiểu TCP.
- Gọi `disconnect()` bỏ peer đã gắn; channel tiếp tục là datagram channel.
- Trong một số tình huống, thông báo ICMP (chẳng hạn port unreachable) có thể làm `PortUnreachableException` xuất hiện; không dựa vào nó như cơ chế phát hiện peer chết đáng tin cậy.

**UDP connect giúp đơn giản hóa địa chỉ peer**, chứ không tự cung cấp reliable stream.

## 8. Ranh giới datagram và nguy cơ truncate

UDP là giao thức theo message. Giả sử peer gửi datagram chứa `ABCDEFGHIJ` (10 byte), trong khi receiver cấp buffer chỉ còn 4 byte:

```text
Datagram đến: [A B C D E F G H I J]  (10 byte)
Receive buffer remaining: 4 byte

Sau receive:
  Buffer có thể chứa [A B C D]
  [E F G H I J] của datagram này bị bỏ.
```

Phần đuôi **không được gửi vào lần `receive` kế tiếp** như với byte stream. Nó đã mất ở cấp API nhận datagram. Đó là lý do một server UDP phải quy định tối đa message và chọn receive buffer phù hợp.

Nếu giao thức cần payload 1.000 byte, ngoài việc cấp buffer đủ lớn, có thể đặt một header gồm `version`, `messageType`, `messageLength` và checksum/sequence. Sau nhận, kiểm tra tổng byte đã nhận, header và `messageLength` trước khi parse. Tránh tin tưởng độ dài do client tự báo.

### Giới hạn kích thước và MTU

UDP có giới hạn độ dài datagram ở mức giao thức/địa chỉ IP; không thể gửi một buffer tùy ý lớn bao nhiêu cũng được. Dữ liệu gửi qua IP còn chịu **MTU** (Maximum Transmission Unit):

- Datagrams lớn có thể cần IP fragmentation (tùy IPv4/IPv6, cấu hình hệ thống và chính sách đường truyền).
- Mất một fragment có thể khiến cả datagram không tái lắp được, nên datagram lớn dễ thất bại hơn trong một số môi trường.
- Gửi vượt kích thước hỗ trợ có thể gây lỗi như `IOException`/lỗi socket.
- Phần kích thước phù hợp phụ thuộc thực tế network, IPv4/IPv6 và path MTU; không nên lấy một con số lý thuyết làm “message size an toàn trên mọi mạng”.

Đối với hệ thống thực, giữ message ở mức nhỏ phù hợp với đường truyền, hoặc tự thiết kế phân mảnh/reassembly tầng ứng dụng kèm giới hạn bộ nhớ, timeout và xác thực. Đừng mặc định UDP tự đảm bảo việc tách một thông điệp ứng dụng khổng lồ thành các `receive` nhỏ có thể ghép lại.

## 9. Vì sao TCP cần framing?

TCP stream **không giữ ranh giới giữa các lần `write`**. Chẳng hạn server gọi:

```java
socketChannel.write(ByteBuffer.wrap(new byte[]{'A', 'B', 'C'}));
socketChannel.write(ByteBuffer.wrap(new byte[]{'D', 'E', 'F'}));
```

Đây chỉ là đoạn minh họa; cần xử lý short write, quyền socket và vòng đời channel. Client có thể đọc `ABCDEF` trong một lần, hoặc `A` rồi `BCDE` rồi `F`, tùy trạng thái buffer/network. Không được suy ra “mỗi lần client.read là một message”.

Hai cách framing cơ bản:

### Length-prefixed framing

```text
TCP bytes:
[4-byte length N][N-byte payload][4-byte length M][M-byte payload]...

Receiver:
1. Đọc đủ 4 byte length.
2. Giải mã length theo endian cố định.
3. Kiểm tra 0 <= length <= maxMessageSize.
4. Đọc đủ length byte payload.
5. Lặp lại cho message tiếp theo.
```

Ví dụ muốn dùng `ByteBuffer.getInt()` cho length, phải đảm bảo đã nhận đủ bốn byte. Nếu chỉ nhận một hoặc hai byte, lưu chúng trong buffer và tiếp tục đọc; không coi đó là một “message thiếu” rồi bỏ tùy ý.

### Delimiter framing

```text
HELLO\nWORLD\n
```

Ứng dụng tìm `\n` để phân biệt các thông điệp. Khi payload có thể chứa delimiter, cần escape/encode; đồng thời quy định giới hạn độ dài dòng để tránh client gửi dữ liệu vô hạn mà không có delimiter.

TCP cung cấp **thứ tự byte**, nhưng không cung cấp cấu trúc message. UDP cung cấp **cấu trúc datagram** ở transport, nhưng nếu ứng dụng cần một message logic trải qua nhiều datagram, phải tự định nghĩa framing/chunking/reassembly ở tầng ứng dụng.

## 10. Reliability, ordering và duplicate trên UDP

UDP không tự gửi ACK, retransmit và sắp thứ tự giúp ứng dụng. Nếu ứng dụng cần các tính năng này, một giao thức tầng trên có thể đặt metadata vào payload:

```text
+---------+-------------+-------------+----------------+
| version | sequence No | timestamp   | payload        |
+---------+-------------+-------------+----------------+
```

Ví dụ chiến lược:

1. **Sequence number:** phân biệt thông điệp mới/cũ, phát hiện mất gói hoặc duplicate.
2. **ACK/timeout:** thông báo gói đã nhận; sender quyết định retransmit sau thời gian thích hợp.
3. **Idempotency:** khi retransmit khiến cùng tác vụ xuất hiện hai lần, receiver không thực thi thao tác nghiệp vụ hai lần.
4. **Reordering buffer:** giữ các gói đến sai thứ tự khi cần phát lại theo trình tự.
5. **Rate/congestion control:** hạn chế tốc độ gửi khi network congested, tránh tự tạo bão retransmission.
6. **Expiration:** với trạng thái game/telemetry, dữ liệu cũ có thể nên bị bỏ thay vì gửi lại quá trễ.

Nhưng khi tự bổ sung đầy đủ retransmission, congestion control, ordering, flow control và bảo mật, hệ thống sẽ phức tạp đáng kể. Với dữ liệu nghiệp vụ yêu cầu đầy đủ byte theo thứ tự, TCP thường tiết kiệm công sức hơn. Với thời gian thực, đôi khi **bỏ frame cũ để nhận frame mới** là đúng mục tiêu, nên UDP/datagram lại phù hợp.

### TCP cũng có giới hạn cần nhận thức

- TCP không cam kết latency cố định hay rằng thông điệp sẽ đến trước deadline.
- TCP retransmit có thể gây tăng trễ khi packet loss, khiến dữ liệu mới phía sau không được ứng dụng đọc trước byte cũ bị thiếu theo thứ tự stream (head-of-line blocking).
- Một lần `write` trả thành công không đảm bảo ứng dụng peer đã **xử lý** dữ liệu. TCP xác nhận ở tầng truyền tải, không phải ACK nghiệp vụ.
- Kết nối TCP có thể đứt, timeout hoặc bị đóng nửa chừng; ứng dụng vẫn cần timeout, retry thích hợp, kiểm soát idempotency và xử lý dữ liệu chưa commit.

## 11. Lựa chọn API Java NIO theo nhu cầu

| Bài toán | Hướng tiếp cận |
|---|---|
| Discovery trong mạng cục bộ | `DatagramChannel` + UDP broadcast/multicast nếu mạng hỗ trợ, kèm giới hạn và xác thực |
| Telemetry định kỳ, chấp nhận mất mẫu cũ | Datagram + sequence/timestamp, rate limit |
| Trạng thái game cập nhật liên tục, dữ liệu cũ ít giá trị | Datagram + xử lý packet loss/out-of-order |
| Gửi file chính xác toàn vẹn | TCP stream hoặc giao thức tin cậy khác, kiểm tra checksum |
| RPC cần request/response hoàn chỉnh | Thường TCP hoặc giao thức ứng dụng đã được xây dựng phù hợp |
| Nhiều kết nối TCP đồng thời trên một luồng | `ServerSocketChannel` + `SocketChannel` + `Selector` |
| Nhiều sender gửi một gói tới một cổng | `DatagramChannel.bind` + `receive` hoặc `Selector` |
| UDP chỉ trao đổi với một peer cố định | Có thể `DatagramChannel.connect(peer)` và `read/write`, nhưng vẫn là UDP |
| Cần TLS theo dòng byte | TCP + TLS/`SSLEngine` (hoặc stack mạng thích hợp); UDP thuần không tự có TLS |
| Cần bảo mật UDP | Thiết kế DTLS hoặc giao thức đã được kiểm chứng; không tự coi datagram là đã xác thực |

Chọn protocol ở **mức yêu cầu ứng dụng**: chấp nhận mất gói hay không, có deadline không, cần ordering không, dữ liệu nhạy cảm không, môi trường mạng nào và liệu phải xử lý NAT/firewall hay multicast.

## 12. Lỗi phổ biến khi lập trình DatagramChannel

1. **Cho rằng `send` thành công đồng nghĩa receiver đã nhận.** Sai: UDP không có ACK nghiệp vụ, đường truyền vẫn có thể mất gói.
2. **Cho rằng UDP `connect` có TCP handshake.** Sai: nó chỉ gắn peer vào datagram socket theo semantics UDP.
3. **Dùng receive buffer nhỏ rồi tưởng lần receive kế tiếp lấy phần dư.** Sai: dữ liệu vượt remaining của một datagram bị bỏ.
4. **Quên `ByteBuffer.flip()` sau `receive`.** Buffer position đang ở sau byte mới ghi; decode trực tiếp trước flip có thể nhận sai vùng.
5. **Quên giữ ranh giới message khi xử lý nhiều datagram.** Mỗi lần nhận một gói cần parse độc lập hoặc theo protocol reassembly riêng.
6. **Dùng `read/write` với DatagramChannel chưa `connect`.** Cần `send/receive` hoặc kết nối peer trước.
7. **Gọi `receive` trên blocking channel rồi mong trả `null` ngay khi chưa có gói.** Blocking có thể chờ; muốn poll, dùng non-blocking hoặc selector/timeout theo thiết kế.
8. **Không kiểm tra `source == null` ở non-blocking.** Khi không có datagram, `receive` có thể trả null.
9. **Quên `configureBlocking(false)` trước khi đăng ký selector.** Đăng ký selectable channel đang blocking có thể ném `IllegalBlockingModeException`.
10. **Đăng ký `OP_ACCEPT` cho DatagramChannel.** UDP không có accept; hãy dùng `OP_READ`.
11. **Giả định mỗi TCP read trả đúng một message.** TCP là stream; phải có framing và vòng lặp đủ byte.
12. **Tự gửi datagram quá lớn.** MTU, fragmentation và độ ổn định mạng khiến gói lớn kém phù hợp trong nhiều trường hợp.
13. **Không giới hạn message size/rate.** Packet từ nguồn không tin cậy có thể khiến server tốn CPU hoặc bộ nhớ.
14. **Dùng địa chỉ sender làm danh tính bảo mật.** Địa chỉ UDP có thể bị giả mạo hoặc thay đổi; cần xác thực ứng dụng khi thao tác quan trọng.
15. **Cho rằng UDP nhanh hơn TCP trong mọi bài toán.** Tổng chi phí reliability tự xây, retry, fragmentation hoặc packet loss có thể khiến thực tế phức tạp và kém hiệu quả hơn.
16. **Không đóng channel/selector.** Dùng try-with-resources, xử lý exceptions và shutdown để giải phóng socket và hệ thống.

## 13. Các tình huống tư duy

### Tình huống A: ứng dụng nhận nhiệt độ mỗi giây

Nếu mỗi mẫu mới thay thế giá trị cũ và việc mất một vài mẫu chấp nhận được, UDP datagram thường hợp lý. Gắn `timestamp`/`sequence` để loại dữ liệu đến muộn hoặc trùng. Đừng suy ra datagram đáng tin cậy chỉ vì chương trình chạy ổn trên loopback.

### Tình huống B: gửi lệnh thanh toán một lần

UDP thuần không phù hợp nếu chỉ send rồi kết luận giao dịch thành công. Thao tác thanh toán cần cơ chế xác thực, idempotency, xác nhận nghiệp vụ, lưu trạng thái và retry kiểm soát. Dùng protocol tin cậy và giao thức ứng dụng được thiết kế để tránh thực thi trùng, không dựa vào API `send`.

### Tình huống C: game gửi vị trí 20 lần mỗi giây

Thông tin vị trí cũ có thể trở nên vô nghĩa khi frame mới đã tới. Datagram có thể giảm tình trạng phải chờ truyền lại dữ liệu cũ, nhưng vẫn cần sequence number, xử lý packet loss, tốc độ gửi hợp lý và đồng bộ trạng thái quan trọng theo kênh đáng tin hơn.

### Tình huống D: gửi hai thông điệp trên TCP

Sender thực hiện `write("HELLO")` và `write("WORLD")`. Receiver đọc `"HELLOWORLD"` một lần. Đó là hành vi hoàn toàn bình thường với TCP. Nếu cần hai message, phải dùng framing, ví dụ `[length=5][HELLO][length=5][WORLD]`.

### Tình huống E: nhận gói 1.500 byte vào buffer 512 byte

Receiver không thể lấy nốt 988 byte trong lần `receive` kế tiếp. Nó phải thiết kế kích thước receive buffer và giới hạn protocol từ đầu, hoặc reject packet có kích thước không đúng. Phần đã bị cắt không thể khôi phục chỉ bằng `flip` hay đọc lại.

### Tình huống F: client UDP muốn tránh xử lý gói từ peer khác

`DatagramChannel.connect(remote)` có thể giúp lọc địa chỉ peer và cung cấp API `read/write` đơn giản. Nó vẫn không xác thực người gửi theo chuẩn bảo mật, không bảo đảm remote sẽ trả lời và không thay thế mã hóa/chống giả mạo.

## 14. Câu hỏi tự kiểm tra

**1.** Gửi UDP hai lần: `"AB"` và `"CD"`. Receiver có được quyền giả định một `receive` sẽ trả `"ABCD"` không?  
**Không.** Mỗi lần receive xử lý một datagram; các gói có thể mất/đảo thứ tự, nhưng UDP không tự ghép hai datagram thành một message.

**2.** Ghi TCP `"AB"` rồi `"CD"`. Receiver có thể nhận cả `"ABCD"` trong một `read` không?  
**Có.** TCP là byte stream, không lưu ranh giới hai lần write.

**3.** Vì sao `channel.receive(buffer)` trả `SocketAddress` thay vì chỉ trả số byte?  
**Vì** DatagramChannel khi nhận gói unconnected cần cung cấp địa chỉ nguồn cho ứng dụng. Số byte có thể xác định từ mức tăng `ByteBuffer.position()` (cần ghi nhận trạng thái trước khi receive).

**4.** Channel non-blocking và chưa có datagram thì `receive` trả gì?  
**Có thể trả `null`.** Đừng dereference địa chỉ nguồn khi chưa kiểm tra kết quả.

**5.** Sau `DatagramChannel.connect(peer)`, sender có tự được bảo đảm truyền lại khi mất gói không?  
**Không.** Vẫn là UDP.

**6.** Nếu datagram có 1.000 byte nhưng `dst.remaining() == 100`, liệu mười lần receive sẽ đọc đủ 1.000 byte đó?  
**Không.** Phần không vừa buffer bị loại bỏ ở lần nhận datagram đó.

**7.** Để chờ gói trên một receiver non-blocking có thể dùng công cụ nào?  
**`Selector`** và đăng ký `OP_READ`; hoặc polling có chiến lược phù hợp. Không dùng `OP_ACCEPT`.

**8.** TCP có ngăn ứng dụng gửi trùng một lệnh sau khi client retry không?  
**Không tự ngăn ở tầng nghiệp vụ.** TCP đảm bảo stream trong một kết nối nhưng retry request qua ứng dụng/kết nối mới vẫn có thể khiến thao tác được gửi hai lần. Cần idempotency khi quan trọng.

## 15. Ghi nhớ

- **UDP datagram = ranh giới thông điệp ở cấp gói, không có bảo đảm delivery/thứ tự.**
- **TCP = luồng byte có thứ tự và cơ chế truyền tin cậy, không có ranh giới message ở API.**
- **`DatagramChannel.send`/`receive` xử lý từng datagram**, `receive` trả địa chỉ người gửi; buffer thiếu chỗ sẽ làm mất phần dư của gói.
- **`DatagramChannel.connect` không phải TCP handshake**; UDP không tự thành reliable stream.
- **`SocketChannel.read/write` cần framing và xử lý partial I/O** nếu ứng dụng làm việc theo thông điệp.
- **`Selector` phù hợp với DatagramChannel non-blocking**, đặc biệt cho event loop nhiều socket.
- Khi chọn UDP hay TCP, ưu tiên yêu cầu về latency, loss, ordering, message size, bảo mật và độ phức tạp giao thức.

### Tài liệu API

- [DatagramChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [SocketChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [Selector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [ByteBuffer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
