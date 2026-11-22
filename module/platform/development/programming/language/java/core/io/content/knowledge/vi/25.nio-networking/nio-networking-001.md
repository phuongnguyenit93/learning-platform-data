# SocketChannel, ServerSocketChannel và DatagramChannel trong Java NIO

## 1. Ba channel mạng giải quyết ba nhu cầu khác nhau

Java NIO (`java.nio.channels`) cung cấp các channel để giao tiếp mạng thông qua `ByteBuffer`. Ba loại quan trọng:

- **`SocketChannel`:** đầu cuối của kết nối luồng byte, thường là **TCP**. Có thể đóng vai trò client hoặc là kênh kết nối được server chấp nhận.
- **`ServerSocketChannel`:** đầu lắng nghe kết nối, thường là **TCP server**; gọi `accept()` để nhận một `SocketChannel` mới cho client cụ thể.
- **`DatagramChannel`:** gửi/nhận các gói tin có ranh giới thông điệp (datagram), thường là **UDP**; không cần một kết nối TCP.

Tất cả sử dụng `ByteBuffer`, đều là `SelectableChannel` và có thể hoạt động **blocking** hoặc **non-blocking**, phù hợp cả code đơn giản và event loop `Selector`. Nhưng semantics dữ liệu và vòng đời của chúng khác nhau: **TCP là stream có thứ tự, UDP là datagram với ranh giới gói**.

Bảng định hướng:

| Tiêu chí | `SocketChannel` | `ServerSocketChannel` | `DatagramChannel` |
|---|---|---|---|
| Vai trò | Đọc/ghi trên kết nối | Lắng nghe, nhận kết nối | Gửi/nhận datagram |
| Giao thức thông thường | TCP | TCP | UDP |
| Dữ liệu ứng dụng | Luồng byte, không có ranh giới bản tin | Không trực tiếp mang payload | Mỗi datagram giữ ranh giới gói |
| API tiêu biểu | `connect`, `finishConnect`, `read`, `write` | `bind`, `accept` | `bind`, `send`, `receive`, `connect`, `read`, `write` |
| Non-blocking | `connect` có thể pending; `read/write` có thể trả 0 | `accept` có thể trả `null` | `receive` có thể trả `null`; `send` có thể trả 0 |
| Khi server chấp nhận client TCP | Là kênh vừa được trả về bởi `accept()` | Vẫn tiếp tục nghe các client khác | Không có ý niệm TCP `accept()` |

Trong Java 17, các API `SocketChannel` và `ServerSocketChannel` còn có khả năng cho **Unix-domain socket** nếu dùng đúng protocol family/address và nền tảng hỗ trợ. Bài này tập trung Internet socket **TCP/UDP** trên loopback, tránh nhầm lẫn rằng mọi implementation chỉ có một protocol family.

## 2. Mô hình TCP: một listener, nhiều kênh kết nối

Một TCP server có thể được hình dung như sau:

~~~text
Client A: SocketChannel --TCP--> SocketChannel A
                                      ^
                                      |
Client B: SocketChannel --TCP--> SocketChannel B
                                      ^
                                      |
                            ServerSocketChannel
                          (listen trên IP + port)
                          accept() trả channel mới
~~~

`ServerSocketChannel` **chỉ là listener**. Mỗi lần `accept()` thành công, server nhận một **`SocketChannel` riêng** cho kết nối đó. Để đọc/ghi dữ liệu của client A, server gọi `read/write` trên channel A, không trên `ServerSocketChannel`.

### 2.1. Các bước phía server

1. Mở `ServerSocketChannel.open()`.
2. Gọi `bind(localAddress)` để lắng nghe một địa chỉ và cổng.
3. Gọi `accept()` để nhận một kết nối.
4. Với `SocketChannel` được chấp nhận, dùng `read`/`write` với `ByteBuffer`.
5. Đóng channel client khi xong, và đóng listener khi dừng server.

Mã minh họa (trong một phương thức đã xử lý `IOException`):

~~~java
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 8080));
    try (SocketChannel peer = server.accept()) {
        // peer là kết nối riêng của client vừa được nhận.
        ByteBuffer received = ByteBuffer.allocate(1024);
        int count = peer.read(received);
        // Cần kiểm tra count và xử lý framing dữ liệu.
    }
}
~~~

Code trên có thể **block vô thời hạn** tại `accept()` hoặc `read()` nếu không có client hoặc dữ liệu phù hợp. Đây là đoạn mô tả cách dùng, không phải demo độc lập ở mục 6.

### 2.2. Các bước phía client

~~~java
try (SocketChannel client = SocketChannel.open()) {
    client.connect(new InetSocketAddress("127.0.0.1", 8080));
    ByteBuffer bytes = StandardCharsets.UTF_8.encode("hello");
    while (bytes.hasRemaining()) {
        client.write(bytes);
    }
}
~~~

Đây là đoạn minh họa, cần listener TCP tương ứng, import và xử lý ngoại lệ. Mặc định channel **blocking**, nên `connect` chờ kết nối được thiết lập hoặc báo lỗi. Chỉ gọi `read/write` sau khi đã kết nối; nếu chưa kết nối, có thể nhận `NotYetConnectedException`.

## 3. TCP là byte stream, không phải các gói bản tin Java

Một trong những lỗi phổ biến nhất là coi một `write` tương ứng chính xác một `read` ở bên kia. TCP chỉ cam kết luồng byte đúng thứ tự khi kết nối hoạt động bình thường; nó **không giữ ranh giới các lần ghi của ứng dụng**.

Ví dụ client gọi:

~~~text
write("HELLO")
write("WORLD")
~~~

Server có thể đọc dữ liệu theo các lần như:

~~~text
read -> "HEL"
read -> "LOWOR"
read -> "LD"
~~~

Hoặc nhiều cách phân chia khác, miễn thứ tự byte không bị đảo. Ngay cả một lần `read(ByteBuffer)` ở blocking mode cũng không phải cam kết lấp đầy toàn bộ buffer.

### 3.1. Đọc với ByteBuffer

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
int n = channel.read(buffer);

if (n == -1) {
    // EOF: peer đã kết thúc phía gửi/đọc hết luồng.
} else if (n > 0) {
    buffer.flip(); // chuẩn bị đọc đúng các byte mới nhận
    // Parse dữ liệu trong [position, limit).
    buffer.clear(); // chuẩn bị buffer cho lượt nhận mới
}
~~~

Mã minh họa với `SocketChannel channel` đã kết nối. `read` trả về:

- **`n > 0`:** đã đọc n byte và `position` của buffer tăng n.
- **`n == 0`:** có thể xảy ra, đặc biệt trong non-blocking mode khi chưa có byte sẵn để nhận; không được coi là EOF.
- **`n == -1`:** phía vào của stream đã tới end-of-stream (ví dụ peer đã đóng/`shutdownOutput`).

Trong code parsing thật, **không gọi `clear()` làm mất các byte thông điệp chưa hoàn chỉnh**. Nếu frame mới chứa một phần dữ liệu, dùng `compact()` để giữ byte dư rồi đọc tiếp. `clear()` chỉ đặt lại trạng thái buffer, không xóa vật lý nội dung.

### 3.2. Ghi phải kiểm tra remaining

~~~java
ByteBuffer data = StandardCharsets.UTF_8.encode("hello");
while (data.hasRemaining()) {
    channel.write(data);
}
~~~

`write` trả về số byte thực sự nhận từ buffer; có thể ít hơn `remaining` ban đầu. Đặc biệt non-blocking `write` có thể trả **0** nếu socket output buffer chưa sẵn sàng. Không lập vòng lặp bận (busy spin) khi non-blocking trả 0: nên chờ `OP_WRITE` qua `Selector` hoặc tổ chức cơ chế retry có kiểm soát.

Trong blocking mode, vòng lặp trên giúp thể hiện yêu cầu “gửi hết dữ liệu trong buffer”, nhưng **không bảo đảm peer đã đọc/xử lý dữ liệu**, cũng không tự thêm ranh giới message.

### 3.3. Protocol framing

Vì TCP không có message boundary, ứng dụng phải chọn **protocol framing**, ví dụ:

- Mỗi message kết thúc bằng newline (phải xác định charset và xử lý newline trong payload).
- Prefix độ dài 4 byte rồi đến đúng số byte body, với endian và giới hạn kích thước được quy định.
- Fixed-length message (chỉ phù hợp khi schema xác định độ dài).
- Giao thức có framing sẵn như HTTP/2 hoặc WebSocket (xử lý theo đúng đặc tả của chúng).

Ví dụ, một parser cho 4-byte length prefix không thể mặc định một `read` sẽ đọc đủ cả 4 byte. Cần lưu trạng thái giữa các lượt đọc, giới hạn độ dài để tránh cấp phát quá lớn và phân biệt EOF giữa frame.

## 4. ServerSocketChannel: bind, accept và nhiều client

`ServerSocketChannel.open()` tạo listener chưa bind. Gọi `bind`:

~~~java
ServerSocketChannel server = ServerSocketChannel.open();
server.bind(new InetSocketAddress("127.0.0.1", 0));
InetSocketAddress address =
        (InetSocketAddress) server.getLocalAddress();
~~~

Đây là mã minh họa, chưa đóng `server`; code production phải sở hữu và đóng tài nguyên. Port **0** yêu cầu OS cấp một ephemeral port còn trống, giúp test tránh cố định port 8080/9000. Địa chỉ `127.0.0.1` chỉ nhận kết nối trong cùng máy; địa chỉ wildcard có thể chấp nhận kết nối trên nhiều giao diện và cần cân nhắc an toàn mạng.

`accept()` có hai tình huống:

- **Blocking mode (mặc định):** thường chờ tới khi có client và trả về `SocketChannel` mới, trừ khi có lỗi/đóng/interrupt.
- **Non-blocking mode:** nếu chưa có kết nối chờ chấp nhận thì trả `null`; khi có kết nối thì trả channel.

`ServerSocketChannel` bản thân không thực hiện `read`/`write` payload TCP. Các socket đã `accept()` tồn tại riêng biệt. Đóng listener không đồng nghĩa một chương trình đã đóng mọi accepted channel; server phải quản lý vòng đời từng kết nối.

### Kết nối non-blocking của SocketChannel

`SocketChannel` có thể được mở non-blocking:

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean connected = client.connect(remote);

if (!connected) {
    // Kết nối đang pending; đợi OP_CONNECT bằng Selector.
    // Khi có readiness, gọi client.finishConnect().
}
~~~

Đây là mã minh họa: `remote` phải là `SocketAddress` phù hợp, và channel cần được đóng khi xong. `connect()` có thể trả ngay **`true`** nếu kết nối hoàn tất tức thì; nếu trả **`false`**, không được đọc/ghi như channel đã kết nối. Khi có tín hiệu connectable (hoặc vào thời điểm thích hợp), `finishConnect()` hoàn tất kết nối; trong non-blocking mode nó cũng có thể trả `false` khi còn pending. Một kết nối thất bại sẽ báo `IOException` thích hợp.

`SocketChannel.isConnectionPending()` và `isConnected()` giúp quan sát trạng thái hiện tại, nhưng không thay `finishConnect()` khi kết nối còn dở dang.

## 5. DatagramChannel: gửi/nhận UDP và ranh giới gói

Khác TCP, UDP có **datagram boundary**. Một lần gửi là một datagram và một lần nhận trả về **một datagram**. Không có đảm bảo tin cậy: gói có thể mất, trùng, đến sai thứ tự hoặc quá trễ. Ứng dụng cần tự xử lý nếu đòi acknowledgement, retry, sequencing hoặc chống trùng.

### 5.1. UDP server và client không cần accept

~~~text
DatagramChannel sender                       DatagramChannel receiver
    send(buffer, remote) --- UDP datagram ---> receive(buffer)
                                                |
                                                +-- trả SocketAddress nguồn
~~~

`DatagramChannel` có thể dùng `send(ByteBuffer, SocketAddress)` và `receive(ByteBuffer)` khi **chưa connected**. Thông thường phía nhận gọi `bind(localAddress)` để nghe cổng ổn định; phía gửi có thể được OS tự bind khi lần đầu gửi.

~~~java
try (DatagramChannel udp = DatagramChannel.open()) {
    udp.bind(new InetSocketAddress("127.0.0.1", 9999));
    ByteBuffer packet = ByteBuffer.allocate(2048);
    SocketAddress from = udp.receive(packet);
    packet.flip();
    // Xử lý đúng một datagram và địa chỉ người gửi 'from'.
}
~~~

Đây là **đoạn mã minh họa**: cần gửi UDP tới port 9999 thì `receive()` mới trả trong blocking mode. Không giả định gói sẽ có độ dài tối đa 2048; nếu datagram đến **lớn hơn `remaining()` của ByteBuffer**, phần dư bị **loại bỏ âm thầm** theo Javadoc. Vì thế phải chọn kích thước nhận thích hợp với giao thức và giới hạn MTU/payload.

### 5.2. Return values cần phân biệt

- `receive(dst)` trả **`SocketAddress`** nguồn khi có datagram; trong non-blocking mode trả **`null`** khi chưa có gói.
- `send(src, target)` trả **số byte** đã gửi. Trong non-blocking mode, có thể trả **0** khi output buffer chưa có chỗ cho datagram.
- Một lần `send` thành công không có nghĩa peer đã nhận, xử lý hay gửi ACK.
- Dùng `dst.flip()` sau receive trước khi giải mã; `receive` đẩy `position` tương ứng số byte đã chép.

**Không chuyển logic đọc stream TCP với vòng lặp ghép các byte thành một frame rồi áp dụng máy móc cho UDP:** UDP đã có ranh giới datagram, một gói quá lớn bị cắt trong buffer nhận là mất dữ liệu gói, không phải “phần còn lại sẽ đến ở `receive()` kế tiếp”.

### 5.3. “Connect” của DatagramChannel khác TCP

`DatagramChannel.connect(peerAddress)` **không tạo phiên TCP và không bắt tay tin cậy**. Nó liên kết channel UDP với một peer mặc định: chỉ nhận datagram từ peer đó, gửi tới peer đó và cho phép dùng `read`/`write` (vốn không có tham số địa chỉ). Channel UDP không connected vẫn dùng `send/receive` được.

Sau `disconnect()`, channel có thể gửi/nhận tới từ các địa chỉ phù hợp qua `send/receive`. Với UDP, một lần `write` là một datagram theo semantics của channel, không phải byte stream ghép với nhiều lần `write` khác.

## 6. Ví dụ Java 17+ hoàn chỉnh: TCP echo mini + UDP loopback

Demo chạy trong **một process**, dùng port do OS cấp nên không cần khởi động server riêng. Luồng TCP tạo listener, client kết nối, server `accept` rồi trao đổi `ping/pong` (mỗi message có đúng bốn byte trong ví dụ). Luồng UDP gửi một datagram `hi` từ sender tới receiver trên loopback.

**Tên tệp: `NetworkChannelsDemo.java`**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;

public class NetworkChannelsDemo {
    private static void sendAll(SocketChannel channel, String value)
            throws IOException {
        ByteBuffer data = StandardCharsets.UTF_8.encode(value);
        while (data.hasRemaining()) {
            channel.write(data);
        }
    }

    private static String readExactly(SocketChannel channel, int size)
            throws IOException {
        ByteBuffer data = ByteBuffer.allocate(size);
        while (data.hasRemaining()) {
            if (channel.read(data) == -1) {
                throw new EOFException("Truncated TCP message");
            }
        }
        data.flip();
        return StandardCharsets.UTF_8.decode(data).toString();
    }

    public static void main(String[] args) throws IOException {
        // 1. TCP: listener + client + accepted SocketChannel.
        try (ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            client.connect(listener.getLocalAddress());

            try (SocketChannel accepted = listener.accept()) {
                sendAll(client, "ping");
                System.out.println(
                        "tcp server: " + readExactly(accepted, 4));

                sendAll(accepted, "pong");
                System.out.println(
                        "tcp client: " + readExactly(client, 4));
            }
        }

        // 2. UDP: mỗi send tương ứng một datagram.
        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress("127.0.0.1", 0));
            sender.send(
                    StandardCharsets.UTF_8.encode("hi"),
                    receiver.getLocalAddress());

            ByteBuffer packet = ByteBuffer.allocate(16);
            SocketAddress source = receiver.receive(packet);
            packet.flip();

            System.out.println("udp source? " + (source != null));
            System.out.println(
                    "udp message: " + StandardCharsets.UTF_8.decode(packet));
        }
    }
}
~~~

Biên dịch và chạy tại thư mục có tệp nguồn:

~~~bash
javac NetworkChannelsDemo.java
java NetworkChannelsDemo
~~~

**Stdout khi TCP/UDP loopback trên máy hoạt động bình thường:**

~~~text
tcp server: ping
tcp client: pong
udp source? true
udp message: hi
~~~

Diễn giải:

1. `listener.bind(..., 0)` mở một port TCP tự chọn, còn `client.connect(listener.getLocalAddress())` kết nối tới listener trong cùng máy.
2. `accept()` trả `SocketChannel` đại diện cho kết nối phía server; hai đối tượng `client` và `accepted` là hai đầu của một kết nối TCP.
3. `sendAll` lặp cho đến khi `ByteBuffer` gửi hết. `readExactly` cũng lặp đến đủ **đúng bốn byte**; việc đó tránh giả định một lần `read` luôn nhận đủ message. Đây chỉ là giao thức fixed-length dùng để minh họa, không phải parser message tùy độ dài.
4. `DatagramChannel` sender gửi đúng một datagram `hi`. Receiver nhận và in địa chỉ nguồn có tồn tại, rồi giải mã hai byte.
5. `try-with-resources` đóng mọi channel, kể cả khi có exception.

**Giới hạn demo:** dùng TCP/UDP trong cùng process và loopback, tránh sự cố mạng bên ngoài. Trên môi trường khóa hoàn toàn quyền socket, TCP/UDP bind/connect có thể thất bại. Chương trình không có timeout vì mục tiêu là ví dụ ngắn, chắc chắn khi loopback hoạt động; code production cần timeout, cancellation và xử lý mạng lỗi. Hình thức TCP fixed-length bốn byte được xác định trước ở cả hai phía, không phải framing tổng quát cho payload tùy ý.

## 7. Blocking, non-blocking và Selector

Các channel trên là `SelectableChannel`. Mặc định chúng ở **blocking mode**. Gọi `configureBlocking(false)` sẽ chuyển sang non-blocking (khi không bị ràng buộc bởi đăng ký `Selector` không tương thích).

| Thao tác | Blocking | Non-blocking |
|---|---|---|
| `ServerSocketChannel.accept()` | Chờ kết nối, rồi trả `SocketChannel` | Chưa có kết nối ⇒ trả `null` |
| `SocketChannel.connect(remote)` | Chờ kết nối thành công hoặc lỗi | Có thể trả `false`; cần `finishConnect()` |
| `SocketChannel.read(dst)` | Thường chờ ít nhất một byte hoặc EOF khi buffer có chỗ | Chưa có dữ liệu ⇒ có thể trả 0 |
| `SocketChannel.write(src)` | Có thể chờ output buffer; vẫn nên kiểm tra remaining | Có thể ghi một phần hoặc trả 0 |
| `DatagramChannel.receive(dst)` | Chờ datagram phù hợp | Chưa có datagram ⇒ trả `null` |
| `DatagramChannel.send(src, remote)` | Gửi datagram hoặc báo lỗi | Có thể trả 0 nếu chưa gửi được gói |

Với nhiều kết nối, một thread có thể quản lý event loop bằng `Selector`:

~~~text
Selector.select() -> selectedKeys
   OP_ACCEPT  -> listener.accept()
   OP_CONNECT -> client.finishConnect()
   OP_READ    -> socket.read(...) hoặc datagram.receive(...)
   OP_WRITE   -> socket.write(...) các byte còn tồn trong hàng đợi
~~~

Đây là sơ đồ ý tưởng. Mỗi `SelectionKey` gắn với channel đã đăng ký; code thật phải kiểm tra key valid, xử lý ngoại lệ, byte framing, backpressure và đóng channel/selector. Trên kênh non-blocking:

- Khi `accept() == null` hay `receive() == null`, không coi đó là lỗi hoặc EOF.
- Khi `SocketChannel.read() == 0`, giữ nguyên state đang đọc dở, chờ thêm dữ liệu.
- Khi `SocketChannel.write() == 0`, lưu `ByteBuffer` còn dữ liệu để ghi tiếp ở một sự kiện phù hợp.
- Nếu đăng ký `OP_WRITE` liên tục kể cả khi không có byte chờ ghi, selector có thể liên tục báo writable và gây CPU busy loop.

Cần hiểu **non-blocking I/O không tự làm TCP thành UDP**, không tự thêm message boundaries và không cam kết tác vụ mạng hoàn thành ngay.

## 8. Đóng kết nối, EOF, timeout và lỗi mạng

### 8.1. Vòng đời của channel

Các channel triển khai `AutoCloseable`, nên dùng `try-with-resources`. Với TCP:

- `SocketChannel.close()` đóng toàn bộ kết nối phía channel.
- `SocketChannel.shutdownOutput()` kết thúc phía ghi nhưng có thể tiếp tục đọc. Peer thường nhận EOF sau khi byte trước đó đã được xử lý theo TCP.
- `SocketChannel.shutdownInput()` kết thúc phía đọc; các lần đọc sau trả `-1` theo hợp đồng.
- `SocketChannel.read(...) == -1` nói tới **EOF của luồng TCP**, không phải một message rỗng.
- Listener và những accepted socket có vòng đời riêng: đóng listener **không thay thế** việc đóng các channel client còn được quản lý.

`DatagramChannel` không có “EOF do peer đóng” như một byte stream TCP. Một thời gian dài không nhận UDP **không chứng minh** peer đã đóng; datagram có thể bị mất, chặn hoặc chưa được gửi.

### 8.2. InterruptibleChannel

`SocketChannel`, `ServerSocketChannel` và `DatagramChannel` đều triển khai `InterruptibleChannel`. Với thread đang bị chặn trong I/O:

- Thread khác gọi `channel.close()` có thể làm blocked operation ném `AsynchronousCloseException`.
- Thread khác gọi `thread.interrupt()` làm channel bị đóng và blocked operation ném `ClosedByInterruptException`, với interrupt flag của thread được đặt.

Nếu channel đã đóng trước khi thao tác I/O bắt đầu, có thể gặp `ClosedChannelException`. Các ngoại lệ `NotYetConnectedException`, `AlreadyConnectedException`, `ConnectionPendingException`, `BindException`, `ConnectException` và những `IOException` khác mang ý nghĩa trạng thái hoặc hỏng kết nối khác nhau, cần xử lý theo tình huống. Không được bắt ngoại lệ interrupt rồi tái sử dụng channel vốn đã đóng.

### 8.3. Timeout và backpressure

Code production phải có chính sách:

- Giới hạn thời gian chờ kết nối/nhận dữ liệu thích hợp, ví dụ non-blocking kết hợp `Selector.select(timeout)`, scheduling deadline hoặc API timeout tương ứng; đừng giả định `configureBlocking(false)` tự cung cấp timeout.
- Với TCP, nếu producer gửi nhanh hơn consumer, phải giữ hàng đợi các `ByteBuffer` còn lại và có giới hạn bộ nhớ/backpressure.
- Với UDP, đặt kích thước datagram hợp lý, xử lý loss/reorder/duplicates ở tầng giao thức nếu cần; gửi nhiều byte không đồng nghĩa chúng tự chia thành các datagram an toàn theo message schema.
- Tránh để nhiều thread cùng sửa một `ByteBuffer` không được đồng bộ. SocketChannel cho phép một read và một write đồng thời nhưng state buffer mà application chia sẻ vẫn do ứng dụng bảo vệ.
- Kiểm soát số kết nối, file descriptor/socket handle và đóng mọi accepted channel khi shutdown.

## 9. Lựa chọn TCP hay UDP theo yêu cầu dữ liệu

**Chọn TCP/SocketChannel + ServerSocketChannel** khi ứng dụng cần truyền **byte stream có thứ tự và kiểm soát độ tin cậy ở tầng transport**: request/response dạng stream, truyền file, giao thức có session. Nhưng cần tự thiết kế framing, timeout, phân luồng và bảo vệ trước peer gửi chậm.

**Chọn UDP/DatagramChannel** khi ứng dụng muốn thao tác trên **từng datagram**, chấp nhận khả năng mất/trùng/sai thứ tự hoặc có cơ chế khắc phục riêng: telemetry, khám phá dịch vụ, dữ liệu thời gian thực tùy protocol. Cần xem MTU, giới hạn payload, chống giả mạo nguồn và rủi ro mạng.

Một số giao thức hiện đại xây dựng độ tin cậy trên UDP bằng logic riêng; vì vậy việc dùng UDP không đồng nghĩa mọi ứng dụng trên nó bắt buộc chấp nhận mất dữ liệu. Khác biệt trọng tâm là **những bảo đảm nào được tầng transport cung cấp sẵn**, những gì phải xử lý ở tầng giao thức ứng dụng.

## 10. Những lỗi thường gặp

1. **Gọi `read/write` trên `ServerSocketChannel` như một kết nối TCP.** Listener chỉ `accept`; đọc/ghi trên accepted `SocketChannel`.
2. **Nghĩ mỗi TCP `write` tương ứng một `read`.** TCP là stream; phải có framing và vòng lặp buffer.
3. **Coi `SocketChannel.read()==0` là EOF.** EOF là `-1`; `0` không có byte được đọc.
4. **Không kiểm tra `hasRemaining()` sau `write`.** Dữ liệu có thể còn trong buffer, nhất là non-blocking.
5. **Dùng vòng lặp busy spin khi non-blocking `write()==0`.** Cần quản lý readiness và backpressure.
6. **Không gọi `finishConnect()` sau non-blocking `connect()==false`.** Kết nối còn pending; không được đọc/ghi như đã connected.
7. **Gọi `accept()` trong non-blocking và mặc định không thể là `null`.** Không có client chờ thì `null` là bình thường.
8. **Nhầm UDP `connect` với TCP handshake.** UDP connect đặt peer mặc định/lọc nguồn; không cung cấp stream hay delivery guarantee.
9. **Buffer UDP quá nhỏ rồi mong nhận phần dư lần sau.** Phần dư của datagram bị cắt **và bỏ**.
10. **Cho rằng UDP `send` thành công là peer đã nhận.** Nó không xác nhận delivery hay xử lý.
11. **Quên `flip` hoặc `compact` khi đọc ByteBuffer.** Parser có thể đọc 0 byte, đọc byte cũ hoặc mất frame dở dang.
12. **Chỉ đóng ServerSocketChannel mà để quên accepted sockets.** Channel listener và client có vòng đời riêng.
13. **Mặc định mọi môi trường đều cho bind port cố định.** Port có thể bận hoặc bị policy chặn; test loopback nên dùng port 0.
14. **Cho rằng non-blocking giải quyết mọi timeout và error handling.** Ứng dụng vẫn cần deadline, queue, xử lý EOF/error và shutdown.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao TCP client gọi hai lần `write("A")` và `write("B")` nhưng server chỉ có một lần `read()` nhận `"AB"`?

**Đáp án:** TCP cung cấp byte stream có thứ tự, không giữ ranh giới từng lần `write` của ứng dụng. Cần framing nếu muốn tách message.

**Câu 2.** Với `ServerSocketChannel` ở non-blocking mode, `accept()` trả gì khi chưa có client?

**Đáp án:** `null`. Đây không phải kết nối lỗi; ứng dụng tiếp tục event loop đợi `OP_ACCEPT`.

**Câu 3.** `SocketChannel.connect(remote)` trả `false` trong non-blocking mode. Bước tiếp theo?

**Đáp án:** Kết nối còn pending; chờ connectable và gọi `finishConnect()` đến khi kết nối hoàn tất hoặc ném lỗi. Không đọc/ghi khi chưa connected.

**Câu 4.** Datagram 120 byte tới `DatagramChannel.receive(dst)` khi `dst.remaining()==32`. Có lấy tiếp 88 byte qua `receive` kế tiếp không?

**Đáp án:** Không. Dữ liệu vượt phần buffer nhận của datagram đó bị loại bỏ theo hợp đồng; lần `receive` tiếp theo dành cho datagram khác.

**Câu 5.** Vì sao kết quả `udp.send` không đủ để khẳng định server nhận thành công?

**Đáp án:** UDP không có ACK/delivery guarantee ở tầng transport; `send` chỉ cho biết hành động gửi ở phía local. Nếu cần xác nhận, giao thức ứng dụng phải bổ sung.

### Tài liệu chính thức Java 17

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html)
- [DatagramChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html)
- [SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html)
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
