# DatagramChannel: gửi/nhận, kết nối UDP và tương tác với ByteBuffer trong Java

`java.nio.channels.DatagramChannel` là kênh NIO để trao đổi **UDP datagram** bằng `ByteBuffer`. Khác với `SocketChannel` dùng TCP, `DatagramChannel` có thể gửi/nhận **không cần kết nối trước**; khi gọi `connect(remote)`, kênh gắn với một peer UDP cụ thể để dùng `read()/write()` thuận tiện, nhưng **không tạo TCP handshake và không chứng minh máy ở xa đang tồn tại hay có ứng dụng lắng nghe**.

Ba nhóm kiến thức quan trọng cần nắm cùng lúc:

1. **Datagram:** mỗi lời gọi gửi tạo một thông điệp UDP với ranh giới riêng, không phải một luồng byte liên tục như TCP.
2. **Channel:** kênh có thể chưa kết nối (dùng `send/receive`), hoặc đã kết nối logic với một peer (có thêm `read/write`); hỗ trợ blocking/non-blocking và `Selector`.
3. **ByteBuffer:** vị trí `position`, giới hạn `limit`, dung lượng `capacity` và các bước `put → flip → send`, `receive → flip → get → clear` quyết định byte nào được truyền và đọc.

Bài học có chương trình Java 17+ hoàn chỉnh, gửi/nhận cả hai kiểu trên IPv4 loopback mà không phụ thuộc Internet, rồi giải thích vấn đề truncation, non-blocking, kết nối UDP, quản lý lỗi và thiết kế production.

## 1. UDP datagram và ý nghĩa của DatagramChannel

TCP cung cấp stream byte có thứ tự. UDP cung cấp các **datagram riêng biệt**: mỗi gói có địa chỉ nguồn, cổng nguồn, địa chỉ đích, cổng đích và payload. Nếu sender gửi hai datagram `A` và `B`, receiver không được coi chúng là một stream liên tục và không tự ghép thành một message duy nhất. UDP không đảm bảo delivery, thứ tự, không trùng lặp hoặc ACK ở tầng ứng dụng.

`DatagramChannel` là lớp abstract thuộc `java.nio.channels`; tạo kênh bằng factory method:

~~~java
// Fragment Java 17+ trong phương thức có xử lý IOException.
try (DatagramChannel channel =
        DatagramChannel.open(StandardProtocolFamily.INET)) {
    // INET = họ giao thức IPv4.
}
~~~

Với `StandardProtocolFamily.INET`, chương trình yêu cầu socket IPv4. `StandardProtocolFamily.INET6` dành cho họ IPv6 ở hệ thống hỗ trợ. `DatagramChannel.open()` để provider chọn họ giao thức mặc định và cách hỗ trợ địa chỉ phù hợp runtime; không nên đoán mọi môi trường đều chọn cùng giao thức.

Một `DatagramChannel` mới tạo mặc định là **open, chưa kết nối**, và ở **blocking mode** trừ khi đổi bằng `configureBlocking(false)`. Kênh có thể cần bind cổng nội bộ trước khi nhận; `send()`/`receive()`/`connect()` trên kênh chưa bind có thể khiến OS tự bind một địa chỉ/cổng khả dụng, theo API. Đối với server muốn nhận tại một cổng xác định, hãy `bind()` tường minh.

Các API chủ yếu:

| Chức năng | Phương thức | Khi nào dùng |
| --- | --- | --- |
| Tạo channel UDP | `DatagramChannel.open(...)` | Chọn họ giao thức / mở kênh |
| Gắn local IP/port | `bind(SocketAddress)` | Receiver tại port cố định, hoặc sender muốn source IP/port ổn định |
| Gửi chưa kết nối | `send(ByteBuffer src, SocketAddress target)` | Mỗi datagram có thể chỉ định đích |
| Nhận chưa kết nối | `receive(ByteBuffer dst)` | Trả lại **địa chỉ nguồn** của datagram |
| Gắn peer UDP | `connect(SocketAddress remote)` | Chỉ trao đổi với peer chỉ định; dùng `read/write` |
| Ghi đã kết nối | `write(ByteBuffer src)` | Gửi datagram tới peer đã kết nối |
| Đọc đã kết nối | `read(ByteBuffer dst)` | Đọc datagram từ peer đã kết nối |
| Bỏ peer | `disconnect()` | Trở về chế độ không kết nối |
| Đổi I/O mode | `configureBlocking(false)` | Non-blocking + `Selector` |
| Đóng tài nguyên | `close()` | Giải phóng socket/channel |

**Từ “connect” trong UDP có ý nghĩa khác TCP.** UDP channel có thể đặt remote peer cho socket ở máy cục bộ mà không cần thương lượng kết nối qua mạng. `isConnected()==true` chỉ nói channel đang mở và đã được gắn peer theo API, không phải chỉ báo peer online.

## 2. Chế độ không kết nối: `send()` và `receive()`

Server UDP nhận datagram thường bind vào một port và gọi `receive`:

~~~java
// Fragment Java 17+; cần imports cho java.net, java.nio, java.nio.channels.
try (DatagramChannel receiver =
        DatagramChannel.open(StandardProtocolFamily.INET)) {

    receiver.bind(new InetSocketAddress(50000));

    ByteBuffer input = ByteBuffer.allocate(2048);
    SocketAddress peer = receiver.receive(input); // Blocking mặc định.
    input.flip();

    byte[] bytes = new byte[input.remaining()];
    input.get(bytes);
    String message = new String(bytes, StandardCharsets.UTF_8);

    System.out.println("From " + peer + ": " + message);
}
~~~

Đoạn này **không phải chương trình độc lập** và sẽ **chờ** nếu chưa có datagram. `receiver.receive(input)` chép datagram vào buffer bắt đầu tại `input.position()`, làm tăng position theo số byte đã nhận, và trả về địa chỉ nguồn của gói. Nếu buffer không đủ chỗ, phần còn lại **bị bỏ** (xem mục 6).

Sender không cần kết nối trước:

~~~java
// Fragment Java 17+; target là InetSocketAddress đã xác minh.
ByteBuffer output = StandardCharsets.UTF_8.encode("HELLO");
int sent = sender.send(output, target);
~~~

`StandardCharsets.UTF_8.encode(...)` trả về `ByteBuffer` đã sẵn sàng **đọc** (position/limit khoanh đúng byte mã hóa), do đó truyền trực tiếp bằng `send` mà không cần `flip()` thêm. Phương thức `send` dùng **toàn bộ remaining bytes** làm **một UDP datagram**. Nếu gửi thành công, position của source buffer tiến tới limit.

Với blocking mode, `send` chờ điều kiện local buffer nếu cần; với non-blocking mode, nếu không đủ chỗ để gửi, nó có thể trả `0`. Javadoc Java 17 quy định số byte trả về là **toàn bộ số byte còn lại ban đầu**, hoặc `0` ở non-blocking khi không thể gửi ngay; không được thiết kế kiểu TCP bằng cách gửi phần datagram còn lại thành gói tiếp theo. Nếu payload được gửi, nó là **một** datagram tại thời điểm gọi. `send` thành công không phải ACK từ receiver.

### Địa chỉ nguồn của datagram

`receive(dst)` trả `SocketAddress` từ gói; đối với IP thông thường, có thể ép kiểu `InetSocketAddress` sau khi kiểm tra kiểu rồi đọc `getAddress()/getPort()`. Trong một protocol request-response chưa kết nối, ta thường phản hồi bằng cách gọi `send(reply, source)` để trả về IP và UDP port người gửi.

Hãy kiểm tra kích thước payload và nội dung của gói trước khi đưa địa chỉ nguồn vào hành động đặc quyền. Địa chỉ nguồn UDP không chứng minh danh tính ứng dụng. Ở một số mạng, UDP source IP có thể bị giả mạo; phản hồi lớn không giới hạn dễ gây khuếch đại lưu lượng.

## 3. Kết nối UDP: `connect()`, `read()` và `write()`

Khi chỉ giao tiếp với **một peer**, ta có thể gọi:

~~~java
// Fragment Java 17+ bên trong phương thức throws IOException.
channel.connect(peer);
System.out.println(channel.isConnected()); // true nếu channel còn mở, đã connect.

ByteBuffer request = StandardCharsets.UTF_8.encode("PING");
int sent = channel.write(request);

ByteBuffer response = ByteBuffer.allocate(1024);
int received = channel.read(response);
response.flip();

channel.disconnect();
~~~

**Điều `connect(peer)` làm:**

- Cấu hình remote IP và port cho socket. Các datagram nhận từ **địa chỉ/port khác** không được giao tới channel đã kết nối.
- Cho phép `read(ByteBuffer)` và `write(ByteBuffer)` vì không cần truyền địa chỉ nguồn/đích ở mỗi lời gọi.
- `getRemoteAddress()` phản ánh peer đang cấu hình; `isConnected()` cho biết trạng thái kết nối **logic tại local socket**.
- Có thể làm **bỏ những datagram đã có trong receive buffer** trước lúc `connect()`. Không nên dựa vào dữ liệu đang chờ nhận vẫn được giữ nguyên qua thời điểm chuyển chế độ.
- Nếu socket chưa bind, `connect` sẽ tự bind local address/port do hệ thống cấp.

**Điều `connect(peer)` không làm:**

- Không thực hiện bắt tay SYN/SYN-ACK/ACK như TCP, không chờ xác nhận có service UDP ở xa.
- Không biến UDP thành cơ chế đảm bảo nhận, thứ tự, retransmit hay stream byte.
- Không xác nhận server phía xa đã sẵn sàng hoặc phiên ứng dụng đã được xác thực.

Khi đã kết nối, `write` gửi **một datagram** đến peer gắn sẵn; `read` nhận datagram từ peer đó. Gọi `read()/write()` khi kênh **chưa kết nối** gây `NotYetConnectedException`. `receive/send` vẫn là API có thể gọi trên kênh đã kết nối, nhưng đích gửi phải phù hợp với peer; gọi `send(src, otherTarget)` sẽ báo `AlreadyConnectedException` nếu đích khác peer. Không cố dùng `connect()` lần nữa khi đang kết nối; muốn chuyển peer thì `disconnect()` trước, rồi mới `connect(newPeer)`.

Với UDP kết nối, hệ điều hành có thể thông báo `PortUnreachableException` khi nhận ICMP báo cổng xa không tới được; API **không bảo đảm** rằng mọi peer không lắng nghe đều tạo ra ngoại lệ. Vì vậy, không dùng việc `write` thành công hay `isConnected` trả true làm phép đo sống/chết peer.

## 4. ByteBuffer: `capacity`, `position`, `limit` và `remaining`

Các phương thức của `DatagramChannel` truyền dữ liệu từ/đến `ByteBuffer`; nếu hiểu sai trạng thái buffer, bạn có thể gửi **0 byte**, gửi dữ liệu cũ hoặc in ra phần byte không thuộc datagram vừa nhận.

| Thuộc tính | Ý nghĩa | Ví dụ với `ByteBuffer.allocate(16)` mới |
| --- | --- | --- |
| `capacity()` | Dung lượng cố định của buffer | `16` |
| `position()` | Vị trí đọc/ghi tương đối tiếp theo | `0` |
| `limit()` | Ranh giới trên hiện tại cho đọc/ghi | `16` |
| `remaining()` | `limit - position` | `16` |
| `flip()` | Chuyển từ chế độ **đã ghi/fill** sang **đọc/drain**: `limit=position` rồi `position=0` | Sau `put(4 byte)`: `limit=4, position=0` |
| `clear()` | Chuẩn bị ghi/fill mới: `position=0, limit=capacity` | `position=0, limit=16` |
| `rewind()` | Đọc lại phần dữ liệu trong limit hiện tại: `position=0` | Dùng để đọc lại khi chưa muốn xóa trạng thái limit |
| `compact()` | Chuyển những byte **còn chưa đọc** về đầu buffer và chuẩn bị viết tiếp | Hữu ích cho stream/partial processing, không nên tự ghép datagram khác nhau |

Bất biến chính: `0 ≤ position ≤ limit ≤ capacity`. Buffer có thể lưu trên heap bằng `allocate()` hoặc vùng nhớ direct bằng `allocateDirect()`. Không phải mọi buffer đều có `array()`; ví dụ direct buffer thường không có mảng Java để truy cập. Khi giải mã, dùng `get(byte[])` hoặc decoder hỗ trợ `ByteBuffer`.

### Gửi từ buffer tự điền

~~~java
// Fragment: tự fill, rồi mới chuyển sang chế độ đọc.
ByteBuffer out = ByteBuffer.allocate(32);
out.put("OK".getBytes(StandardCharsets.UTF_8));
out.flip();  // position=0, limit=2
int n = channel.send(out, destination);
~~~

Nếu quên `flip()` sau `put`, position đang ở cuối dữ liệu vừa ghi, còn limit có thể bằng capacity. `send` sẽ lấy phần **remaining** từ vị trí hiện tại đến limit, có thể gửi các byte chưa được chuẩn bị. Đối với `ByteBuffer.wrap(byte[])` hoặc `StandardCharsets.UTF_8.encode("OK")`, buffer thường đã có position/limit đúng để đọc, nên **không tự động flip lần nữa**: flip lại ở position 0 sẽ đặt limit 0 và làm thông điệp rỗng.

### Nhận vào buffer và giải mã

~~~java
// Fragment: dst là buffer đã clear hoặc mới allocate.
ByteBuffer dst = ByteBuffer.allocateDirect(2048);
SocketAddress source = channel.receive(dst);
if (source != null) {
    dst.flip(); // Chỉ các byte vừa nhận nằm từ 0 tới limit.
    byte[] bytes = new byte[dst.remaining()];
    dst.get(bytes);
    String text = new String(bytes, StandardCharsets.UTF_8);
    dst.clear(); // Chuẩn bị cho datagram kế tiếp; KHÔNG xóa byte vật lý.
}
~~~

Một buffer mới có `position=0, limit=capacity` và nhận dữ liệu tiến position. `flip()` sau receive đặt limit đúng số byte, khiến `get` chỉ lấy nội dung của datagram. `clear()` cho phép ghi đè lần kế tiếp **chứ không xóa sạch nội dung bí mật**; không dùng `clear()` làm phương thức sanitization. Dữ liệu cũ nằm trong backing memory cho đến khi bị ghi đè hoặc xử lý theo cơ chế khác.

## 5. Chương trình Java 17+ chạy độc lập trên UDP loopback

Ví dụ này tạo hai `DatagramChannel` IPv4, bind chúng vào loopback `127.0.0.1` với cổng tự do. Đầu tiên sender không kết nối gửi `PING` bằng `send()` và receiver nhận bằng `receive()`; sau đó **hai channel cùng connect tới địa chỉ đối phương** và dùng `write()/read()` để truyền `OK`. Mọi thao tác I/O nằm trên cùng luồng để giảm yếu tố thời điểm: chương trình gửi trước rồi mới đọc từng gói.

**Lưu thành tệp `DatagramChannelDemo.java`:**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.charset.StandardCharsets;

public class DatagramChannelDemo {
    private static String takeUtf8(ByteBuffer input) {
        byte[] bytes = new byte[input.remaining()];
        input.get(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});

        try (DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            sender.bind(new InetSocketAddress(loopback, 0));
            receiver.bind(new InetSocketAddress(loopback, 0));

            // 1) Không connect: send(buffer, target).
            ByteBuffer out = StandardCharsets.UTF_8.encode("PING");
            int sent = sender.send(out, receiver.getLocalAddress());
            System.out.println("sendBytes=" + sent);
            System.out.println(
                    "sourceRemaining=" + out.remaining());

            // Dùng direct buffer: không phụ thuộc dst.array().
            ByteBuffer in = ByteBuffer.allocateDirect(64);
            SocketAddress from = receiver.receive(in);
            System.out.println(
                    "expectedSource="
                            + from.equals(sender.getLocalAddress()));
            System.out.println(
                    "receivePosition=" + in.position());

            in.flip();
            System.out.println("unconnectedText=" + takeUtf8(in));

            in.clear(); // position=0, limit=capacity=64
            System.out.println(
                    "afterClear=position:" + in.position()
                            + ",limit:" + in.limit());

            // 2) UDP connect: ghim peer, vẫn không có TCP handshake.
            sender.connect(receiver.getLocalAddress());
            receiver.connect(sender.getLocalAddress());
            System.out.println(
                    "connected=" + (sender.isConnected()
                            && receiver.isConnected()));

            ByteBuffer next = StandardCharsets.UTF_8.encode("OK");
            int written = sender.write(next);
            int n = receiver.read(in);
            in.flip();

            System.out.println("writeBytes=" + written);
            System.out.println("readBytes=" + n);
            System.out.println("connectedText=" + takeUtf8(in));

            sender.disconnect();
            receiver.disconnect();
            System.out.println(
                    "disconnected=" + (!sender.isConnected()
                            && !receiver.isConnected()));
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac DatagramChannelDemo.java
java DatagramChannelDemo
~~~

**Đầu ra mong đợi trong môi trường cho phép UDP loopback** (đã kiểm tra với JDK):

~~~text
sendBytes=4
sourceRemaining=0
expectedSource=true
receivePosition=4
unconnectedText=PING
afterClear=position:0,limit:64
connected=true
writeBytes=2
readBytes=2
connectedText=OK
disconnected=true
~~~

Giải thích theo thứ tự:

1. Sender gửi UTF-8 `PING`, dài 4 byte. `send` chuyển toàn bộ 4 byte của `out`, khiến `remaining()==0`.
2. Receiver nhận một gói từ đúng local socket của sender: `receive` trả địa chỉ nguồn, buffer direct có `position==4`. So sánh source với địa chỉ sender trả `true` vì cả hai bind trực tiếp vào `127.0.0.1` với port do OS chọn.
3. `flip()` giới hạn vùng đọc ở 4 byte, giải mã thành `PING`.
4. `clear()` đặt buffer 64 byte về trạng thái sẵn sàng nhận mới; không cần cấp phát buffer mới.
5. Hai socket được gắn peer UDP và `isConnected()==true`. Sender `write` 2 byte `OK`; receiver `read` trả 2, sau đó `flip` và giải mã tương ứng.
6. `disconnect()` bỏ cấu hình peer trên cả hai kênh; `isConnected()==false`. Khối `try-with-resources` sẽ `close()` cả hai kênh.

**Không diễn giải sai kết quả:** ví dụ chạy trên **cùng máy**, các gói rất nhỏ, không có firewall mạng ngoài; nó kiểm tra API NIO, buffer và UDP loopback, **không chứng minh UDP luôn đến đích trong Internet**. Nếu môi trường sandbox chặn socket loopback, chương trình có thể báo `IOException` hoặc chờ; đó là giới hạn môi trường, không phải thay đổi ngữ nghĩa các phương thức.

## 6. Ranh giới UDP datagram và nguy cơ cắt gói khi ByteBuffer nhỏ

Với TCP, một lệnh `read` không ứng với một message; ứng dụng thường cần ghép byte thành frame. Với UDP, một `send` thành công là **một datagram**; một `receive` thành công nhận dữ liệu từ **một datagram** và trả source.

Nhưng khi datagram chứa 2.000 byte còn buffer chỉ có 512 byte `remaining()`:

~~~text
Sender: [------------------ 2000 bytes ------------------]
                            UDP datagram
Receiver: ByteBuffer.remaining() = 512

receive(dst)
  -> chép tối đa 512 byte vào dst
  -> phần còn lại của cùng datagram bị bỏ đi
  -> không thể gọi receive() lần hai để lấy "phần còn lại" đó
~~~

Theo Javadoc `DatagramChannel.receive` và `read`, nếu số byte còn lại trong buffer không đủ, **phần dư của datagram bị bỏ im lặng**. Vì vậy:

- Kiểm tra `buffer.remaining()` **trước** `receive`; nếu position chưa reset thì dung lượng thực tế còn lại giảm.
- Đặt giới hạn kích thước giao thức phù hợp; ví dụ một message discovery tối đa 1.024 byte, allocation tối thiểu theo ranh giới đó và kiểm tra mọi field length.
- Sau `receive`, nếu `position == capacity`, **có thể** đã đầy hoặc bị cắt; không thể chỉ dựa vào điều này để chứng minh datagram chắc chắn bị truncate (datagram bằng đúng capacity cũng cho vị trí cuối).
- Nếu cần payload vượt giới hạn an toàn qua mạng, thiết kế fragmentation/reassembly ở tầng ứng dụng hoặc chọn giao thức thích hợp. Tránh lệ thuộc vào IP fragmentation vì mất một mảnh làm ảnh hưởng cả UDP datagram.

**ByteBuffer không ghép ranh giới UDP giúp bạn.** `compact()` vốn hữu ích để giữ byte chưa đọc của một luồng, nhưng không nên dùng mặc định để nối các datagram khác nhau thành một message mà không có protocol layer rõ ràng. Nếu mỗi datagram là một message độc lập, hãy xử lý xong, `clear()` và nhận gói tiếp theo.

### Dữ liệu UTF-8 và số byte

Một ký tự tiếng Việt có thể chiếm nhiều byte UTF-8. `ByteBuffer.remaining()` là **số byte**, không phải số ký tự Java. Nếu một gói bị cắt giữa chuỗi UTF-8, giải mã có thể thay byte lỗi bằng ký tự thay thế hoặc báo lỗi tùy chính sách decoder. Với protocol nghiêm ngặt, cần xác minh độ dài gói, mã hóa và chính sách lỗi decoder trước khi sử dụng nội dung.

Để có body nhị phân, dùng `ByteBuffer.putInt/getInt`, `putLong/getLong` và `order(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` theo format đã quy định. ByteBuffer mặc định big-endian; chỉ giải mã chính xác khi cả sender/receiver tuân theo quy ước byte order, kiểu dữ liệu và boundary của datagram. Không ghép ngẫu nhiên dữ liệu nhị phân qua `new String(..., UTF_8)`.

## 7. Blocking và non-blocking: sự khác biệt cần nhớ

Mặc định kênh được mở ở **blocking mode**:

- `receive(dst)` có thể **chờ** đến khi có datagram hợp lệ (hoặc lỗi/đóng channel).
- `read(dst)` khi kênh **đã kết nối** có thể chờ datagram từ peer.
- `send(src,target)`/`write(src)` có thể chờ cho tới khi local output buffer cho phép gửi gói.

Sau `channel.configureBlocking(false)`:

- `receive(dst)` trả `null` khi không có datagram ngay lúc gọi. Không có packet **khác với** một datagram rỗng: nhận datagram 0 byte có thể trả về source và không làm tăng position.
- `read(dst)` trên channel đã kết nối có thể trả `0` khi chưa có dữ liệu ngay; không coi `0` là TCP EOF hay lỗi.
- `send(src,target)`/`write(src)` có thể trả `0` khi không có chỗ gửi ngay. Không spin liên tục hoặc biến một gói chưa gửi thành nhiều packet nhỏ bằng cách chia buffer.
- Nếu kênh dùng `Selector`, event loop có thể đợi `OP_READ`/`OP_WRITE` thay vì làm một thread blocking cho từng socket.

Ví dụ **fragment** minh họa non-blocking, không chạy độc lập:

~~~java
// channel đã được mở, bind và configureBlocking(false).
ByteBuffer dst = ByteBuffer.allocate(2048);
SocketAddress source = channel.receive(dst);

if (source == null) {
    // Chưa có datagram ngay bây giờ.
    // Chờ OP_READ qua Selector hoặc một cơ chế lập lịch phù hợp.
} else {
    dst.flip();
    // Chỉ xử lý byte từ position tới limit.
}
~~~

Không lạm dụng vòng `while (channel.receive(dst) == null) { }`: nó tạo busy-spin, tiêu hao CPU và không cung cấp deadline/backpressure đúng nghĩa.

### Selector, registration và timeout

Kênh phải ở non-blocking mode để đăng ký vào `Selector`:

~~~java
// Fragment Java 17+; channel đã bind, selector đã mở.
// imports: java.nio.channels.*, java.nio.ByteBuffer.
channel.configureBlocking(false);
channel.register(selector, SelectionKey.OP_READ);

int readyKeys = selector.select(2_000); // Chờ tối đa khoảng 2 giây.
if (readyKeys == 0) {
    // Chưa có kênh sẵn sàng trong chu kỳ kiểm tra.
} else {
    for (SelectionKey key : selector.selectedKeys()) {
        if (key.isValid() && key.isReadable()) {
            DatagramChannel readable = (DatagramChannel) key.channel();
            ByteBuffer buffer = ByteBuffer.allocate(2048);
            SocketAddress source = readable.receive(buffer);
            if (source != null) {
                buffer.flip();
                // Xử lý một datagram đã nhận; bảo vệ khối lượng công việc.
            }
        }
    }
    selector.selectedKeys().clear();
}
~~~

Đây là **mẫu ý tưởng của một chu kỳ event loop**, không phải server production: phải tổ chức selector/channel lifecycle, giới hạn backlog xử lý, các lần receive tiếp theo, lỗi I/O, điều kiện đóng và tài nguyên. `select(timeout)` không đặt “timeout kết nối UDP” mà chỉ giới hạn thời gian chờ sự kiện sẵn sàng trong event loop. Sẵn sàng đọc không nhất thiết đảm bảo một lời gọi về sau luôn đọc được gói, vì có race hoặc state change; code non-blocking vẫn phải xử lý `null`.

**Lưu ý:** không dùng `DatagramChannel.socket().setSoTimeout(...)` như thể nó là cách chuẩn để điều khiển `DatagramChannel.receive()`. Đối với I/O NIO, hãy dùng non-blocking + selector/deadline hoặc thiết kế hủy/đóng channel thích hợp; khi dùng `DatagramSocket.receive()` thông thường, `setSoTimeout` là API khác với các ngữ nghĩa riêng của socket adaptor.

## 8. Kết nối UDP không bảo đảm liveness, delivery hoặc response

Một ứng dụng đôi khi suy luận sai:

~~~java
// Anti-pattern: không thể xác nhận peer đang sống bằng cờ này.
channel.connect(remote);
if (channel.isConnected()) {
    // Sai nếu kết luận "remote server chắc chắn đang nhận gói".
}
~~~

UDP connect chỉ cấu hình peer và xử lý lọc địa chỉ ở phía local/OS. Server không cần gọi `accept()` cho UDP. Một server UDP thông thường `bind(localPort)` rồi `receive()`; không có listen backlog hay TCP handshake. Kể cả `write()` trả số byte đã gửi và `isConnected()==true`, datagram vẫn có thể mất, bị firewall drop, bị route sang interface không mong muốn hoặc đến app không xử lý.

Để xác thực **peer/app đã trả lời**, phải có protocol request-response với message ID, deadline, khả năng kiểm tra phản hồi đúng request, retry có kiểm soát và bảo vệ trùng lặp. Ví dụ:

~~~text
CLIENT UDP                                    SERVER UDP
send datagram: requestId=42  --------------> receive requestId=42
                                              validate & process
receive datagram: requestId=42 <------------ send responseId=42
       |
       +-- id đúng, dữ liệu hợp lệ, nguồn phù hợp?
       +-- không phản hồi trước deadline -> timeout nghiệp vụ
       +-- timeout không chứng minh request trước chưa được xử lý
~~~

**Giao thức ứng dụng quyết định độ tin cậy**, không phải chữ “connected” trong tên phương thức. Nếu ứng dụng dùng UDP cho tác vụ có side effects (thanh toán, ghi DB…), retry cần idempotency key hoặc dedup theo request ID; nếu không, một yêu cầu có thể bị xử lý nhiều lần.

### Địa chỉ peer, NAT và bảo mật

`connect()` giới hạn peer theo cặp IP/port quan sát được ở socket. NAT có thể thay đổi port phía ngoài; peer có thể tái khởi động dùng port mới, các gói từ cặp khác bị lọc. Việc lọc theo IP/port **không phải xác thực mật mã** và không đủ để tin nguồn gửi có quyền. Đối với dữ liệu nhạy cảm, cần xác thực, integrity và encryption ở lớp phù hợp, hoặc giao thức được thiết kế như DTLS/QUIC khi đúng bài toán.

## 9. So sánh DatagramChannel và DatagramSocket

| Tiêu chí | `DatagramChannel` | `DatagramSocket` |
| --- | --- | --- |
| Dữ liệu gửi/nhận | `ByteBuffer` | `DatagramPacket` kết hợp `byte[]` |
| Chưa kết nối | `send(src,target)` / `receive(dst)` | `send(packet)` / `receive(packet)` |
| Kết nối peer | `connect(remote)`; dùng `read/write` | `connect(remote)`; vẫn dùng `send/receive` trên packet |
| Non-blocking + Selector | Có, với `configureBlocking(false)` | API `DatagramSocket` truyền thống không có `Selector` registration tương ứng |
| Phạm vi gói | Mỗi `send/receive` xử lý một datagram | Mỗi `send/receive` xử lý một datagram |
| Buffer | Direct/heap `ByteBuffer`, position/limit | Mảng/payload trong `DatagramPacket` |
| Khi nên dùng | Ứng dụng NIO, tích hợp event loop, quản lý nhiều socket | Ví dụ đơn giản, blocking UDP ứng dụng nhỏ |

**Không mặc định DatagramChannel luôn nhanh hơn DatagramSocket.** Tốc độ phụ thuộc khối lượng gói, JVM/OS, buffer, cách phân bổ, tác vụ xử lý, batching, mạng và kiến trúc. Có thể dùng `channel.socket()` để lấy `DatagramSocket` adapter, nhưng không được tạo kỳ vọng sai rằng mọi cấu hình blocking mode/timeout sẽ hoạt động giống hệt một socket được tạo độc lập.

## 10. Các lỗi thực tế và cách xử lý

### 10.1. `NotYetConnectedException`

Gọi `channel.read(dst)` hoặc `write(src)` khi chưa `connect(remote)`. Cách sửa: dùng `receive(dst)` và `send(src,target)` khi chưa kết nối; hoặc `connect(remote)` trước nếu protocol chỉ có một peer.

### 10.2. Gửi gói rỗng hoặc byte lạ vì quên `flip()`

Sau `buffer.put(bytes)`, `position` đã tiến đến sau dữ liệu; phải `flip()` trước khi `send/write`. Ngược lại, `StandardCharsets.UTF_8.encode(...)` đã trả buffer ở tư thế đọc: nếu flip thêm ngay, limit có thể thành 0 và gửi payload rỗng. Kiểm tra `position/limit/remaining` ngay trước mỗi lần gửi.

### 10.3. Nhận xong in ra rác hoặc ký tự `\\u0000`

Có thể do giải mã cả dung lượng buffer (ví dụ `new String(buffer.array())`) thay vì **đúng số byte datagram**. Sau nhận, `flip()` rồi lấy `remaining()`. Với direct ByteBuffer, `array()` còn có thể ném `UnsupportedOperationException`. Dùng `get(byte[])` như ví dụ sẽ hoạt động cho cả buffer heap/direct.

### 10.4. Mất phần cuối datagram

Nhận với buffer `remaining` nhỏ hơn payload khiến phần dư bị bỏ, không đọc tiếp được bằng một lần `receive()` khác. Tăng kích thước hợp lý, kiểm tra định dạng và payload length. Không nhầm hành vi này với TCP stream cần đọc nhiều lần.

### 10.5. `receive()` chờ mãi

Kênh đang blocking và không có datagram hợp lệ. Kiểm tra server `bind()` đúng local port, sender đích đúng, firewall/route, socket đã `connect` chỉ nhận một peer, và trạng thái selector. Muốn deadline, dùng non-blocking + selector hoặc tổ chức hủy/đóng phù hợp, không poll bận.

### 10.6. Có `isConnected()==true` nhưng không có phản hồi

UDP kết nối không kiểm tra peer và không retry. Xác minh IP/port đúng, server có bound port đó, firewall/NAT, message schema và timeout tầng ứng dụng. Không coi `PortUnreachableException` là tín hiệu bắt buộc trong mọi tình huống mất server.

### 10.7. Hai peer khác nhau không trao đổi được qua kênh đã kết nối

Channel đã `connect(peerA)` chỉ nhận/gửi với địa chỉ/port của A. Khi cần nói chuyện với B, sử dụng channel chưa kết nối cùng `send/receive` hoặc `disconnect()` rồi cấu hình lại một peer khác. Lưu ý datagram đã được buffer trước connect có thể bị loại.

### 10.8. Selector luôn báo sẵn sàng nhưng CPU cao

Kiểm tra có giữ `OP_WRITE` liên tục khi không còn dữ liệu cần gửi, có gọi `selectedKeys().clear()/remove` đúng cách, có kênh readable nhưng chưa drain, hoặc có xử lý blocking bên trong event loop. Ưu tiên sự kiện và backpressure; không dùng event loop để chạy DB/CPU task dài.

## 11. Thiết kế datagram service an toàn

Khi tiến tới service thực tế, nên có các nguyên tắc:

1. **Quy định kích thước:** max payload, version, message type, length và encoding rõ ràng. Không nhận payload chưa kiểm tra rồi cấp phát bộ nhớ theo số length tùy ý. Kích thước tối đa lý thuyết UDP phụ thuộc IPv4/IPv6/IP headers; để giảm fragmentation, đa số protocol nên chọn datagram nhỏ phù hợp path MTU thay vì cố gửi gần 65 KB.
2. **Giữ đúng ranh giới gói:** mỗi datagram xử lý độc lập, validate trước khi parse. Không giả định thứ tự hoặc mỗi lần gửi chắc chắn có lần nhận.
3. **Áp dụng deadline:** nếu gửi request, đặt giới hạn thời gian chờ response và chính sách retry/backoff. Timeout không xác minh peer đã không xử lý yêu cầu.
4. **Chống replay và trùng:** có request ID, idempotency khi tương tác có side effects và xác thực thông điệp nếu cần.
5. **Tối ưu phân bổ:** có thể tái dùng `ByteBuffer` theo vòng đời xử lý nhưng tránh đưa cùng buffer cho nhiều worker đọc/ghi đồng thời mà không đồng bộ; direct buffer không giúp nếu cứ cấp phát liên tục.
6. **Kiểm soát nguồn/đích:** host và port phải được xác minh, cân nhắc IPv4/IPv6, NAT, route, firewall và policy. UDP source address không tự xác thực danh tính.
7. **Bảo vệ event loop:** không blocking ngoài ý muốn; phân giới hạn mức xử lý mỗi vòng, quota theo client, tối đa số packet/byte và cơ chế overload.
8. **Đóng đúng tài nguyên:** dùng `try-with-resources`, xử lý `IOException`/closed channel và không sử dụng buffer/frame sau khi lifecycle của thông điệp đã kết thúc.
9. **Quan sát được:** ghi số datagram nhận/gửi/thất bại, kích thước byte, source/target, quá hạn, queue length, dropped/oversize, thời gian xử lý và lỗi parse; không log payload nhạy cảm một cách mặc định.
10. **Kiểm chứng trên môi trường thật:** loopback demo không đại diện NAT, Wi-Fi, loss, reordering, MTU, container hay firewall. Thử với packet loss/latency được mô phỏng ở môi trường test có kiểm soát.

Đặc biệt với `ByteBuffer`, phần lớn lỗi phát sinh từ **quên hướng đọc/ghi và vùng remaining**. Hãy đặt biến rõ ý nghĩa như `outboundReadyToRead`, `inboundToFill` hoặc dùng những method encode/decode để kiểm soát state thay vì truyền một buffer vô danh qua nhiều tầng cùng sửa position.

## 12. Bài tập mở rộng và tự kiểm tra

**Bài tập A — Đọc trạng thái buffer:** Một `ByteBuffer.allocate(8)` được `put` bốn byte, sau đó `flip()`. `position/limit/remaining` bằng bao nhiêu?  
**Đáp án:** `0/4/4`. Sau khi `send` thành công 4 byte, `position=4` và `remaining=0`. `clear()` đưa về `0/8/8` chứ không xóa dữ liệu trong backing memory.

**Bài tập B — Phân biệt mode:** Channel chưa kết nối cần gửi `HELLO` tới cổng 9000 trên một IP; nên gọi phương thức nào?  
**Đáp án:** `send(ByteBuffer, SocketAddress)`. `write(ByteBuffer)` đòi hỏi `connect(remote)` trước.

**Bài tập C — Kết nối UDP:** `channel.connect(remote)` trả về bình thường và `channel.isConnected()==true`. Có bảo đảm remote đang nghe UDP port đó không?  
**Đáp án:** Không. Đây là cấu hình peer cục bộ, không có TCP handshake; chỉ nhận response đúng protocol mới giúp đánh giá peer/app tại thời điểm thử.

**Bài tập D — Truncation:** Datagram dài 1.400 byte; receiver còn 1.000 byte trống. Gọi `receive(dst)` hai lần có lấy được đủ 1.400 byte không?  
**Đáp án:** Không. Lần nhận đầu chép tối đa 1.000 byte; phần dư của datagram đầu bị bỏ, lần sau là datagram khác nếu có.

**Bài tập E — Non-blocking:** `receive(dst)` trả `null` có chắc sender không gửi gói không?  
**Đáp án:** Không. Nó chỉ cho biết lúc gọi chưa có datagram khả dụng ngay trên channel non-blocking. Gói có thể đến về sau hoặc bị chặn/mất trên mạng.

**Bài tập F — Zero-length datagram:** `receive(dst)` trả source nhưng `position` không tăng. Có thể tồn tại datagram đó không?  
**Đáp án:** Có. Datagram UDP có thể có payload 0 byte; đừng dùng `position==0` thay thế điều kiện `source==null` để kiểm tra có nhận được gói hay không.

**Bài tập G — Tái sử dụng buffer:** Sau khi receive một gói 6 byte vào buffer capacity 32, muốn nhận datagram độc lập tiếp theo phải làm gì?  
**Đáp án:** `flip()` để đọc đúng 6 byte, xử lý hoặc sao chép dữ liệu cần giữ, rồi `clear()` để chuẩn bị fill gói mới. Không `compact()` để tự nối hai gói UDP độc lập.

**Bài tập H — Chuyển peer:** Kênh đã connect tới A, cần gửi tới B khác. Có thể gọi thẳng `send(src,B)` không?  
**Đáp án:** Không; theo API connected channel, đích khác peer dẫn tới `AlreadyConnectedException`. Dùng channel chưa kết nối, hoặc `disconnect()` rồi `connect(B)` khi thiết kế yêu cầu.

**Bài tập I — Vì sao cần direct buffer trong demo?**  
**Đáp án:** Để cho thấy cách lấy dữ liệu đúng qua `position/limit/get` mà không phụ thuộc `array()`. Không phải vì direct buffer bảo đảm nhanh hơn ở mọi trường hợp.

**Bài tập J — Điều gì cần bổ sung để demo thành UDP request-response thực tế?**  
**Đáp án:** Định dạng frame/version, xác thực input, request ID, deadline nhận, retry/backoff, xử lý duplicate, max payload, các bước đánh giá response source và kiểm thử mạng thật.

## Tài liệu chính thức

- Java SE 17 — `DatagramChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `Buffer` (position, limit, flip, clear, rewind): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- Java SE 17 — `Selector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- Java SE 17 — `SelectionKey`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- Java SE 17 — `StandardProtocolFamily`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html
- Java SE 17 — `PortUnreachableException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/PortUnreachableException.html
