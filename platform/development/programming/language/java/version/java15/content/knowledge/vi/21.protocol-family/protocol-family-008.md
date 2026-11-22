# Protocol family: chọn blocking mode và quản lý vòng đời channel trong Java

> **Ngữ cảnh:** Trong Java 15+, các channel mạng thuộc `java.nio.channels` có thể chọn rõ protocol family khi mở, chẳng hạn `StandardProtocolFamily.INET` hoặc `INET6`. Sau khi tạo channel, ta lựa chọn **blocking** hay **non-blocking** cho từng chiến lược I/O, quản lý đăng ký với `Selector`, rồi đóng tài nguyên đúng cách. Protocol family và blocking mode là **hai quyết định độc lập**: chọn IPv4/IPv6 không tự khiến I/O trở nên bất đồng bộ. Bài này tập trung vào API còn được dùng trên JDK 17+; nội dung bổ sung về Unix-domain socket được ghi rõ thời điểm xuất hiện từ **JDK 16**.

## 1. Ba câu hỏi thiết kế phải trả lời

Khi tạo một kênh kết nối mạng Java, cần giải quyết ba câu hỏi khác nhau:

1. **Protocol family:** socket thuộc họ địa chỉ nào: IPv4 (`INET`), IPv6 (`INET6`) hay một họ khác được hỗ trợ?
2. **I/O mode:** thao tác như `accept()`, `connect()`, `read()`, `receive()` có thể **chờ đến khi hoàn tất** (blocking) hay phải trả về ngay nếu chưa sẵn sàng (non-blocking)?
3. **Lifecycle:** ai tạo, bind/connect, đăng ký selector, ngắt kết nối, hủy đăng ký, đóng channel và xử lý những I/O đang chờ?

Sơ đồ trách nhiệm:

~~~text
ProtocolFamily (INET / INET6 / UNIX nếu được hỗ trợ)
         |
         v
open channel -> open, chưa bind hoặc connect (tùy loại)
         |
         +---- blocking mode? ---- yes -> thao tác I/O tuần tự
         |
         +---- non-blocking -> Selector.register(...)
         |                         |
         |                         v
         |                 select -> ready keys -> I/O
         |
         v
shutdown / cancel key / close resources
         |
         v
isOpen() == false
~~~

**Không nhầm:**

- **Protocol family** xác định loại địa chỉ/socket; không phải TCP hay UDP mode switch. `SocketChannel`/`ServerSocketChannel` phục vụ stream socket (thường TCP cho INET/INET6), `DatagramChannel` phục vụ datagram (UDP cho INET/INET6).
- **Blocking mode** xác định cách lời gọi I/O chờ hoặc trả về; không làm TCP chuyển thành UDP hay IPv4 thành IPv6.
- **Selector** multiplex các selectable channels, không quyết định protocol family, không tự đóng application channels khi selector bị đóng.

## 2. Chọn protocol family trước khi mở channel

`java.net.ProtocolFamily` là interface, còn `java.net.StandardProtocolFamily` có các lựa chọn thông dụng:

| Protocol family | Ý nghĩa | Address thường dùng | Tình huống |
| --- | --- | --- | --- |
| `StandardProtocolFamily.INET` | IPv4 | `InetSocketAddress` chứa IPv4 | UDP IPv4, TCP IPv4, giao thức chỉ hỗ trợ IPv4 |
| `StandardProtocolFamily.INET6` | IPv6 | `InetSocketAddress` chứa IPv6 | UDP IPv6, TCP IPv6, IPv6 multicast |
| `StandardProtocolFamily.UNIX` | Unix-domain socket (local IPC) | `UnixDomainSocketAddress` | Truyền thông tiến trình trên cùng máy bằng stream socket; **JDK 16+** |

### 2.1. API tạo channel theo family

~~~java
// Mảnh mã minh họa, đặt trong phương thức có xử lý IOException.
DatagramChannel udp4 =
        DatagramChannel.open(StandardProtocolFamily.INET);

DatagramChannel udp6 =
        DatagramChannel.open(StandardProtocolFamily.INET6);

SocketChannel tcpClient4 =
        SocketChannel.open(StandardProtocolFamily.INET);

ServerSocketChannel tcpServer6 =
        ServerSocketChannel.open(StandardProtocolFamily.INET6);
~~~

Cần import các kiểu trong `java.nio.channels` và `java.net.StandardProtocolFamily`. Các channel trên **chưa tự bind hoặc kết nối tới peer** chỉ vì `open` thành công. Trong code thực tế, sử dụng `try-with-resources` hoặc chủ sở hữu tài nguyên rõ ràng; ví dụ mở bốn channel ở trên chỉ nhằm minh họa lựa chọn.

**Điểm phiên bản quan trọng:**

- `SocketChannel.open(ProtocolFamily)` và `ServerSocketChannel.open(ProtocolFamily)` được bổ sung từ **Java 15**.
- `DatagramChannel.open(ProtocolFamily)` đã tồn tại trước Java 15 và vẫn hữu ích để xác định IPv4/IPv6, đặc biệt với multicast.
- `StandardProtocolFamily.UNIX` và `UnixDomainSocketAddress` dành cho Unix-domain socket channels xuất hiện qua **JEP 380 ở Java 16**, nên không biên dịch một ví dụ `UNIX` với `--release 15`.
- Trong Java 17, `DatagramChannel.open(ProtocolFamily)` có ghi chú **Unix-domain datagram sockets không được hỗ trợ**. Không suy luận `UNIX` áp dụng cho mọi channel chỉ vì enum có giá trị này.

### 2.2. `open()` không tham số khác gì?

~~~java
// Mảnh minh họa:
SocketChannel client = SocketChannel.open();
DatagramChannel datagram = DatagramChannel.open();
~~~

Các factory không tham số chọn Internet socket theo cách mặc định của platform/JDK, và đối với datagram channel, protocol family cụ thể có thể tùy cấu hình/platform. Nếu ứng dụng **phải** sử dụng IPv4 hoặc IPv6, nhất là multicast, nên chọn rõ `INET` hoặc `INET6` và dùng đúng loại địa chỉ.

Không tự coi `open()` luôn là IPv4. Cũng không mặc định socket IPv6 sẽ chấp nhận mọi IPv4-mapped address: dual-stack và OS socket policy khác nhau. Kiểm thử trên hệ điều hành/JDK mục tiêu.

### 2.3. Family không đổi sau `open`

Tạo `DatagramChannel.open(INET)` nghĩa là lựa chọn family ngay tại lúc mở. `configureBlocking(...)` **không** đổi family. Nếu cần chuyển từ IPv4 sang IPv6, hãy tạo channel mới với family phù hợp và quản lý lại bind/connect/selector registration. Không có `setProtocolFamily` để đổi một channel đang hoạt động.

### 2.4. Family hoặc address không được hệ thống hỗ trợ

Có thể nhận `UnsupportedOperationException` nếu chọn family không được OS/JDK hỗ trợ, chẳng hạn IPv6 bị tắt. Địa chỉ không khớp family có thể dẫn đến lỗi bind/connect như `UnsupportedAddressTypeException` hoặc `IOException` tùy thao tác và platform.

**Không** bắt tất cả lỗi chọn family rồi âm thầm chuyển sang family khác nếu điều này làm thay đổi quy tắc bảo mật/route/binding của ứng dụng. Nếu có fallback IPv4/IPv6, phải là **chính sách được thiết kế và kiểm thử**.

## 3. Blocking mode: mặc định và ý nghĩa

`SocketChannel`, `ServerSocketChannel` và `DatagramChannel` đều là **SelectableChannel**. Theo Java NIO API, channel mới tạo **mặc định ở blocking mode**:

~~~java
// Mảnh minh họa:
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    System.out.println(channel.isBlocking()); // true
}
~~~

`configureBlocking(false)` chuyển sang non-blocking:

~~~java
// Mảnh minh họa:
channel.configureBlocking(false);
System.out.println(channel.isBlocking()); // false
~~~

### Blocking mode

Các thao tác được định nghĩa là blocking có thể **chờ** cho đến khi sự kiện/operation hoàn tất hoặc bị lỗi/ngắt/đóng:

- `ServerSocketChannel.accept()` có thể đợi có client.
- `DatagramChannel.receive(dst)` có thể đợi có UDP datagram.
- `SocketChannel.read(dst)` có thể đợi dữ liệu, EOF hoặc điều kiện kết thúc liên quan.
- `SocketChannel.connect(remote)` có thể chờ hoàn tất kết nối ở blocking mode.

**Không** đồng nghĩa mọi lời gọi luôn mất thời gian. Nếu dữ liệu/connection đã sẵn sàng, lời gọi có thể trả ngay.

### Non-blocking mode

I/O operation **không chờ vô hạn cho readiness**. Kết quả có thể biểu thị chưa sẵn sàng hoặc chỉ hoàn thành một phần:

- `ServerSocketChannel.accept()` có thể trả `null`.
- `DatagramChannel.receive(ByteBuffer)` có thể trả `null` nếu không có datagram.
- `SocketChannel.read(ByteBuffer)` có thể trả `0` nếu chưa có bytes, hoặc `-1` khi stream đã đến EOF.
- `SocketChannel.write(ByteBuffer)` có thể ghi một phần hoặc `0`; phải giữ các bytes còn lại.
- `SocketChannel.connect(remote)` có thể trả `false` khi kết nối đang tiến hành; sau readiness `OP_CONNECT`, gọi `finishConnect()`.

**Điểm phân biệt TCP và UDP:** `SocketChannel` làm việc với **byte stream**, nên một `read` không tương ứng một message nghiệp vụ hoàn chỉnh. `DatagramChannel` giữ **ranh giới UDP datagram**, nhưng vẫn có thể mất gói, và nếu buffer nhận nhỏ, phần dư của một datagram có thể bị loại.

## 4. Chọn blocking hay non-blocking theo workload

| Hoàn cảnh | Blocking phù hợp khi | Non-blocking + Selector phù hợp khi |
| --- | --- | --- |
| CLI/test/tool quản trị | Ít kết nối, logic tuần tự dễ hiểu | Cần quan sát nhiều sockets cùng lúc |
| Kết nối TCP đơn lẻ | Một request/response, thời gian chờ được kiểm soát | Cần nhiều operations không chặn event loop |
| UDP collector | Ít peers, có luồng nhận chuyên trách | Nhiều sockets và workloads cùng event loop |
| Server nhiều connections | Có mô hình threads/virtual threads phù hợp | Một số event loops multiplex nhiều channels |
| Latency/throughput | Dễ lập trình, vận hành ổn khi tài nguyên cho phép | Tối ưu I/O concurrency và backpressure có quản lý |
| Shutdown | Phải đánh thức/hủy I/O đang chặn | Phải gọi `selector.wakeup()`/đóng tài nguyên theo thiết kế |

Không có quy tắc “NIO = non-blocking” hay “blocking luôn lỗi thời”:

- NIO `SocketChannel` có **cả hai chế độ**.
- Non-blocking hữu ích khi kết hợp `Selector`, nhưng cần state machine, output queues, xử lý partial I/O.
- **JDK 21+** có virtual threads, giúp nhiều mô hình **blocking-style I/O** dễ mở rộng hơn; đây là khả năng hiện đại, **không có ở Java 15**. Đừng đưa API JDK 21 vào ví dụ biên dịch với `--release 15`.
- Chọn theo số kết nối, thời gian chờ, khả năng bảo trì, thư viện/framework và nhu cầu hiệu năng thực đo.

## 5. Bắt buộc non-blocking trước khi đăng ký Selector

`Selector` chỉ làm việc với **selectable channels** đang **non-blocking**. Quy trình đúng:

~~~java
// Mảnh minh họa có IOException và tài nguyên được quản lý:
try (Selector selector = Selector.open();
     DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {

    channel.bind(new InetSocketAddress("127.0.0.1", 0));
    channel.configureBlocking(false);
    SelectionKey key = channel.register(
            selector, SelectionKey.OP_READ);

    // I/O event loop...
}
~~~

**Sai thứ tự:**

~~~java
// SAI: channel mới mở còn blocking.
DatagramChannel channel = DatagramChannel.open();
channel.register(selector, SelectionKey.OP_READ);
// -> IllegalBlockingModeException
~~~

`register(...)` cần channel chưa đóng, selector chưa đóng, cùng provider tương thích, và `ops` phải nằm trong `channel.validOps()`.

### Những operations hợp lệ

| Channel | Operations thường hợp lệ |
| --- | --- |
| `ServerSocketChannel` | `SelectionKey.OP_ACCEPT` |
| `SocketChannel` | `OP_CONNECT`, `OP_READ`, `OP_WRITE` |
| `DatagramChannel` | `OP_READ`, `OP_WRITE` |

Không đăng ký `OP_ACCEPT` cho `DatagramChannel` hoặc `OP_READ` cho `ServerSocketChannel`; sẽ vi phạm tập operations hợp lệ và có thể bị `IllegalArgumentException`.

Có thể kiểm tra chương trình:

~~~java
// Mảnh minh họa:
int supported = channel.validOps();
boolean canRead = (supported & SelectionKey.OP_READ) != 0;
~~~

### Selector báo readiness, không hoàn thành nghiệp vụ thay ứng dụng

`select()` và `select(timeout)` cho biết các keys sẵn sàng theo trạng thái I/O. Sau đó **ứng dụng vẫn phải gọi `accept`/`receive`/`read`/`write`**, xử lý giá trị trả về và cập nhật state.

Không suy ra `key.isReadable()==true` nghĩa là đã có **một message nghiệp vụ hoàn chỉnh**, hoặc `key.isWritable()==true` nghĩa là toàn bộ pending bytes chắc chắn được ghi xong.

## 6. Cấu trúc event loop cơ bản

~~~java
// Mảnh code minh họa nằm trong method có xử lý IOException.
// selector đã mở, channels đã register non-blocking.
while (running) {
    int changed = selector.select(1000); // timeout millis
    if (changed == 0) {
        // Không có key mới/được cập nhật, hoặc wakeup/timeout.
        continue;
    }

    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Rất quan trọng: bỏ key khỏi selected set.

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            // ((ServerSocketChannel) key.channel()).accept();
        }
        if (key.isConnectable()) {
            // ((SocketChannel) key.channel()).finishConnect();
        }
        if (key.isReadable()) {
            // Đọc/receive những bytes đang sẵn sàng.
        }
        if (key.isWritable()) {
            // Đẩy pending output, có thể chỉ ghi một phần.
        }
    }
}
~~~

Cần import `Iterator`/`SelectionKey` và các loại channel. Đoạn trên chỉ là **khung khái niệm**, không phải ứng dụng hoàn chỉnh. Trong chương trình thật, cần state machine, error handling, per-connection buffers, queue bounds, backpressure, timeouts và shutdown logic.

### Vì sao phải bỏ key khỏi selected set?

`Selector.selectedKeys()` là tập các key đã được phát hiện ready. Theo contract, việc gọi `selectedKeys()` **không tự xóa key đã xử lý**. Nếu giữ lại, vòng sau có thể xử lý lại readiness cũ hoặc gây lặp logic. Dùng iterator và `remove()` sau khi lấy key là pattern phổ biến.

### `select(0)` không có nghĩa “poll ngay”

Với API `Selector.select(long timeout)`, **timeout=0** có ý nghĩa chờ không giới hạn giống `select()`, không phải không chờ. Muốn thử readiness ngay, dùng `selector.selectNow()`. Đừng vô tình biến event loop thành blocking vô hạn khi developer dự định “poll mỗi 0 mili giây”.

### Khi nào dùng `OP_WRITE`?

Một TCP socket thường có thể writable rất nhiều thời điểm. Nếu luôn đăng ký `OP_WRITE` ngay cả khi ứng dụng không có bytes cần gửi, event loop có thể bị đánh thức liên tục và tốn CPU. Chỉ bật `OP_WRITE` khi có **pending output**, và tắt khi queue đã rỗng. Với non-blocking `SocketChannel.write`, phải giữ buffer state sau lần ghi chưa hết.

## 7. Chuyển lại blocking mode: phải deregister trước

Đây là ràng buộc dễ gây lỗi nhất:

- `configureBlocking(false)` chuyển channel sang non-blocking để đăng ký selector.
- Nếu channel **đang registered với một hoặc nhiều selectors**, gọi `configureBlocking(true)` sẽ ném **`IllegalBlockingModeException`**.
- `SelectionKey.cancel()` đánh dấu key cần hủy, **không đảm bảo deregister đã hoàn tất ngay trong dòng code kế tiếp**.
- Distration được selector xử lý trong **selection operation tiếp theo** (hoặc khi đóng selector).
- Chỉ chuyển về blocking khi channel **đã thực sự không còn registered**.

Quy trình an toàn khi một event loop không còn giữ channel:

~~~java
// Mảnh minh họa, giả định key thuộc channel/selector.
// Phải phối hợp với thread đang sở hữu selector.
key.cancel();
selector.selectNow();               // Xử lý cancelled-key set.
channel.configureBlocking(true);    // Sau khi deregister.
~~~

Nếu channel đã đăng ký **nhiều selectors**, phải hủy và hoàn tất deregistration ở **tất cả selectors liên quan** trước khi chuyển blocking.

Không lấy `key.isValid()==false` làm bằng chứng đủ rằng channel đã deregister. Key bị cancel có thể invalid ngay trong khi `channel.isRegistered()` còn trả `true` một khoảng ngắn.

### Một số cách giải quyết thiết kế

**Ưu tiên giữ nguyên mode trong vòng đời:** ứng dụng đơn giản chọn blocking hoặc selector-based non-blocking từ lúc khởi tạo đến lúc đóng; như vậy tránh phải đổi qua lại.

**Khi bắt buộc chuyển mode:** bảo đảm channel đã ngừng chịu trách nhiệm của event loop, cancel key, đánh thức selector nếu thread đang `select()`, chờ selector xử lý cancellation và không còn các registrations, rồi mới gọi `configureBlocking(true)`.

**Không** dùng `Thread.sleep(...)` để “đợi đủ lâu cho key biến mất”. Dùng synchronization/handoff và lifecycle signals đúng.

## 8. `SelectionKey`, `Selector` và lifecycle có khác nhau không?

Một hệ thống có ba đối tượng:

| Đối tượng | Vai trò | Khi đóng/hủy thì sao? |
| --- | --- | --- |
| `DatagramChannel` / `SocketChannel` / `ServerSocketChannel` | Tài nguyên OS socket, I/O state | `close()` đóng channel, hủy các keys liên quan |
| `SelectionKey` | Đại diện cho đăng ký channel ↔ selector | `cancel()` yêu cầu deregister, **không đóng channel** |
| `Selector` | Multiplex readiness của nhiều channels | `close()` hủy các đăng ký và tài nguyên selector, **không tự đóng tất cả application channels** |

**Không đồng nhất ba hành động:**

~~~text
key.cancel()       -> huỷ đăng ký key với selector
selector.close()   -> đóng selector và deregister channels
channel.close()    -> đóng channel/socket tương ứng
~~~

Nếu chỉ `key.cancel()`, channel vẫn có thể mở, bind/connect và dùng I/O theo mode hiện tại. Nếu chỉ đóng selector, các channel chưa chắc đã đóng, và socket handles có thể bị giữ. Nếu đóng channel, keys của nó bị cancel; việc loại đăng ký khỏi selector có thể diễn ra ở selection operation kế tiếp.

### Lifecycle state theo khái niệm

~~~text
NEW / OPEN
  |
  +--> BOUND (UDP receiver, TCP listener)
  |
  +--> CONNECTING / CONNECTED (TCP client)
  |
  +--> NONBLOCKING + REGISTERED (nếu chọn Selector)
  |        |
  |        +--> key.cancel()
  |        +--> selector processes deregistration
  |
  +--> CLOSED (channel.close())
~~~

**Đây không phải một enum state chuẩn** của `SelectableChannel`. Trạng thái bind, connect, registered, blocking và open là **các thuộc tính riêng** có thể tồn tại cùng nhau. Ví dụ một UDP channel có thể **bound**, **unconnected**, **non-blocking**, **registered** và **open** đồng thời.

## 9. Quản lý tài nguyên bằng try-with-resources

Vì `Channel` và `Selector` hỗ trợ `AutoCloseable`/`Closeable`, Java có thể đóng tự động khi thoát khỏi khối:

~~~java
// Mảnh minh họa:
try (Selector selector = Selector.open();
     DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {

    channel.configureBlocking(false);
    // ...register, process I/O...
} // selector và channel được close khi thoát scope.
~~~

Điểm mạnh:

- Đóng kể cả khi có exception trong thân `try`.
- Giảm socket/selector resource leak.
- Đóng ngược thứ tự khởi tạo của các resources.
- Giữ trách nhiệm sở hữu channel rõ ràng.

### Ai chịu trách nhiệm close?

Nếu một method **tự tạo** channel và không chuyển ownership đi, thường method đó nên đóng nó. Nếu trả channel cho caller hoặc đăng ký nó với long-lived event loop, cần nêu rõ **ai** sẽ close, khi nào và trong điều kiện lỗi nào. Tránh cả **không ai đóng** và **hai thành phần đóng ngoài dự kiến**.

Ví dụ:

~~~java
// Mảnh minh họa: phương thức tạo và chuyển ownership cho caller.
static DatagramChannel openReceiver() throws IOException {
    DatagramChannel ch =
            DatagramChannel.open(StandardProtocolFamily.INET);
    try {
        ch.bind(new InetSocketAddress("127.0.0.1", 0));
        return ch; // Caller nhận trách nhiệm đóng channel.
    } catch (IOException | RuntimeException ex) {
        ch.close();
        throw ex;
    }
}
~~~

Đây là code phương thức có thể biên dịch khi đặt trong class với imports phù hợp. Khi application hoàn tất, caller dùng `try (DatagramChannel receiver = openReceiver()) { ... }`.

### Close có thể ảnh hưởng thread đang blocking

Theo Java NIO channel contract, đóng channel từ thread khác có thể khiến một thao tác I/O đang chặn kết thúc với **`AsynchronousCloseException`** hoặc kết quả đặc thù của operation. Ngắt thread trong lúc I/O trên interruptible channel có thể đóng channel và báo **`ClosedByInterruptException`**. Vì vậy, shutdown không đơn thuần là “đặt boolean running=false”: thread blocking cần cơ chế đánh thức/hủy hợp lý.

**Không** mặc định một `SocketChannel` đã đóng có thể `open` lại: sau close, cần tạo một channel mới.

## 10. Blocking channel, non-blocking channel và socket adapters

Java vẫn có các API socket cổ điển như `java.net.Socket` hoặc `DatagramSocket`. Khi truy cập adapter qua `channel.socket()`:

- Adapter và channel có thể **chia sẻ underlying socket**; closing một phía thường ảnh hưởng phía kia.
- Một số operation của adapter yêu cầu blocking mode; nếu channel đang non-blocking, có thể nhận **`IllegalBlockingModeException`**.
- Khi xây dựng một lớp abstraction, đừng để hai thành phần đồng thời sở hữu/channel lifecycle mà không có hợp đồng.
- Với code NIO, ưu tiên thao tác trực tiếp qua `SocketChannel`/`DatagramChannel` và `ByteBuffer` nếu dùng selector.

Không nên trộn:

~~~java
// Mảnh ý tưởng rủi ro: không phải code hoàn chỉnh.
channel.configureBlocking(false);
// Sau đó dùng channel.socket().getInputStream() ở thread khác
// mà giả định mọi blocking semantics vẫn như trước.
~~~

Với TCP adapter và non-blocking mode, thao tác InputStream/OutputStream có thể không còn phù hợp. Nếu muốn kết hợp API, phải kiểm tra Javadoc và trạng thái mode.

## 11. TCP khác UDP khi chọn blocking mode

### 11.1. TCP server (`ServerSocketChannel`)

**Blocking:**

~~~java
// Mảnh minh họa nằm trong try có server được bind.
SocketChannel client = server.accept(); // Chờ kết nối đến.
try (client) {
    // Đọc/ghi theo protocol, xử lý EOF và timeout.
}
~~~

**Non-blocking:**

~~~java
// Mảnh minh họa.
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);

// Khi readiness OP_ACCEPT:
SocketChannel client = server.accept();
if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ);
}
~~~

Cần hiểu **mỗi accepted client channel** có lifecycle riêng. Nếu muốn dùng `Selector`, phải bảo đảm **client cũng non-blocking** trước khi register. `accept()` có thể trả `null` ở non-blocking mode; không được ép nó thành một client object hợp lệ khi chưa có kết nối.

### 11.2. TCP client (`SocketChannel`)

Blocking:

~~~java
// Mảnh minh họa:
try (SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.INET)) {
    client.connect(new InetSocketAddress("127.0.0.1", 9000));
    // Sau khi connect thành công, read/write.
}
~~~

Non-blocking:

~~~java
// Mảnh minh họa:
client.configureBlocking(false);
boolean connected = client.connect(remote);

if (!connected) {
    client.register(selector, SelectionKey.OP_CONNECT);
    // Khi isConnectable():
    // if (client.finishConnect()) đổi interestOps cho OP_READ/WRITE.
}
~~~

Không coi `connect(...)==false` là lỗi. Đó là dấu hiệu kết nối **đang tiến hành** trong non-blocking mode. `finishConnect()` có thể vẫn chưa xong hoặc ném IOException nếu thất bại. Không đọc/ghi như đã kết nối trước khi process kết nối hoàn tất.

### 11.3. TCP read/write partial

Ở non-blocking:

~~~java
// Mảnh minh họa với SocketChannel đã kết nối.
int bytesRead = client.read(dst);
if (bytesRead == 0) {
    // Hiện chưa có bytes mới.
} else if (bytesRead == -1) {
    // EOF: peer đã đóng/half-close chiều gửi.
}
~~~

Với `write(src)`, có thể chỉ ghi một phần `src.remaining()`. Phần còn lại được thể hiện bằng `ByteBuffer.position()` và phải được giữ để ghi tiếp khi writable. Không vô tình gọi `flip()` sai rồi phát lại bytes đã gửi.

### 11.4. UDP (`DatagramChannel`)

Ở blocking mode, `receive(dst)` đợi datagram. Ở non-blocking mode, nó có thể trả `null`; nếu có datagram, vị trí buffer tăng theo số bytes được ghi.

~~~java
// Mảnh minh họa:
ByteBuffer dst = ByteBuffer.allocate(1024);
SocketAddress peer = datagram.receive(dst);

if (peer != null) {
    dst.flip();
    // Đọc bytes thuộc datagram vừa nhận.
}
~~~

Đừng suy ra `peer==null` là “UDP peer đóng stream” — UDP không có TCP-style EOF. Với UDP, `connect(remote)` chỉ cố định peer cho send/receive và cho phép `read/write`; nó không thiết lập phiên TCP hay bảo đảm delivery.

## 12. Chương trình Java 17+ hoàn chỉnh: INET, hai blocking modes và đóng channel

Ví dụ dùng **IPv4 loopback (`127.0.0.1`)** để không phụ thuộc kết nối Internet, không dùng threads và không đòi quyền đặc biệt. Nó chứng minh:

1. `DatagramChannel.open(StandardProtocolFamily.INET)` tạo channel đang blocking.
2. `configureBlocking(false)` trước `register`.
3. Không thể chuyển về blocking khi còn selector registration.
4. `Selector.select(timeout)` chờ readiness có giới hạn.
5. `SelectionKey.cancel()` + `selectNow()` xử lý deregistration trước khi chuyển về blocking.
6. `try-with-resources` đóng channel kể cả khi có lỗi.

Tạo file **`ProtocolFamilyLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.DatagramChannel;
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;

public final class ProtocolFamilyLifecycleDemo {

    public static void main(String[] args) throws IOException {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        DatagramChannel receiver =
                DatagramChannel.open(StandardProtocolFamily.INET);

        try (receiver;
             Selector selector = Selector.open();
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {

            receiver.bind(new InetSocketAddress(loopback, 0));

            System.out.println(
                    "new channel blocking: " + receiver.isBlocking());

            receiver.configureBlocking(false);
            System.out.println(
                    "non-blocking configured: " + !receiver.isBlocking());

            SelectionKey key =
                    receiver.register(selector, SelectionKey.OP_READ);
            System.out.println(
                    "registered for READ: "
                            + (receiver.isRegistered() && key.isValid()));

            boolean blockingRejected = false;
            try {
                receiver.configureBlocking(true);
            } catch (IllegalBlockingModeException expected) {
                blockingRejected = true;
            }
            System.out.println(
                    "blocking while registered rejected: "
                            + blockingRejected);

            byte[] message = "PING".getBytes(StandardCharsets.UTF_8);
            SocketAddress target = receiver.getLocalAddress();
            int sent = sender.send(ByteBuffer.wrap(message), target);
            if (sent != message.length) {
                throw new IOException("UDP send was incomplete");
            }

            int ready = selector.select(3000);
            if (ready == 0 || !key.isReadable()) {
                throw new IOException("No readable event in 3 seconds");
            }
            System.out.println("selected READ: true");

            ByteBuffer incoming = ByteBuffer.allocate(64);
            SocketAddress peer = receiver.receive(incoming);
            if (peer == null) {
                throw new IOException("Unexpected empty receive");
            }
            incoming.flip();
            String text = StandardCharsets.UTF_8.decode(incoming)
                    .toString();

            System.out.println("received: " + text);

            selector.selectedKeys().clear();
            key.cancel();
            selector.selectNow();  // Process cancelled registrations.

            receiver.configureBlocking(true);
            System.out.println(
                    "blocking restored: " + receiver.isBlocking());
        }

        System.out.println(
                "receiver open after scope: " + receiver.isOpen());
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 17+ có IPv4 loopback và quyền mở UDP local:

~~~bash
javac ProtocolFamilyLifecycleDemo.java
java ProtocolFamilyLifecycleDemo
~~~

**Stdout dự kiến nếu loopback UDP hoạt động bình thường:**

~~~text
new channel blocking: true
non-blocking configured: true
registered for READ: true
blocking while registered rejected: true
selected READ: true
received: PING
blocking restored: true
receiver open after scope: false
~~~

### Đọc từng kết quả

- **`new channel blocking: true`**: `SelectableChannel` mới mặc định blocking.
- **`non-blocking configured: true`**: `configureBlocking(false)` cập nhật mode.
- **`registered for READ: true`**: selector được đăng ký bằng key hợp lệ.
- **`blocking while registered rejected: true`**: thử chuyển blocking khi còn registered phát sinh `IllegalBlockingModeException` và được demo bắt **đúng loại lỗi**.
- **`selected READ: true`**: một datagram loopback đã đến trong timeout, `Selector` phát hiện channel readable.
- **`received: PING`**: `DatagramChannel.receive` lấy một UDP datagram, `ByteBuffer.flip()` chuẩn bị đọc.
- **`blocking restored: true`**: key đã cancel và selector xử lý deregistration, nên mode có thể đổi lại.
- **`receiver open after scope: false`**: `try-with-resources` đóng tài nguyên `receiver`.

**Điều kiện môi trường:** UDP không bảo đảm delivery. Nếu OS, sandbox hoặc firewall chặn loopback, chương trình có thể ném `IOException`/`SocketException` thay vì in đủ stdout. Code có `select(3000)` để tránh đợi vô hạn. Một kết quả loopback thành công cũng không chứng minh Internet path sẽ luôn nhận được datagram.

### Có dùng được trên Java 15 không?

Các APIs trong chương trình đã tồn tại trước hoặc tại Java 15; chương trình **không** dùng record, switch preview hay `StandardProtocolFamily.UNIX`. Trên compiler còn hỗ trợ Java 15, có thể kiểm tra:

~~~bash
javac --release 15 ProtocolFamilyLifecycleDemo.java
~~~

Không cần `--enable-preview`.

## 13. Vì sao cancellation không thể xem là deregistration tức thì?

Theo Javadoc `SelectableChannel` và `Selector`:

- `SelectionKey.cancel()` đặt key vào **cancelled-key set**.
- Selector loại các cancelled keys và thực hiện deregistration trong **một selection operation** kế tiếp.
- `channel.isRegistered()` có thể vẫn đúng trong khoảng chờ dù key đã invalid.
- `channel.configureBlocking(true)` chỉ hợp lệ sau khi không còn registrations với **bất kỳ selector nào**.
- `selector.close()` xử lý việc vô hiệu keys/deregister với selector đó; còn channel cần đóng riêng nếu không muốn giữ socket.

Để kiểm tra lifecycle trong ứng dụng lớn, có thể dùng các bước có xác nhận:

~~~text
event-loop owner receives shutdown/transfer request
        |
        v
stop scheduling new I/O on channel
        |
        v
cancel key(s), call selector.wakeup() if needed
        |
        v
selector executes selection/cancellation processing
        |
        v
deregistration observed/acknowledged
        |
        v
choose configureBlocking(true) OR close channel
~~~

Đừng cố register lại cùng channel với selector khi key cũ chỉ mới bị cancel nhưng selector **chưa xử lý cancellation**; có thể nhận `CancelledKeyException`. Một lệnh `selectNow()` trên selector tương ứng là cách thực thi quy trình hủy đăng ký trong ví dụ đơn giản.

## 14. Shutdown sạch trong event loop nhiều threads

Khi event loop chạy riêng trong một thread, đặt `running=false` ở thread khác **không nhất thiết đánh thức** `selector.select()` đang chờ. Một thiết kế shutdown thường gồm:

1. Ngừng nhận các requests/connections mới.
2. Đánh dấu trạng thái shutdown (ví dụ `AtomicBoolean` hoặc signaling được đồng bộ).
3. Gọi `selector.wakeup()` để `select()` sớm trở về, sau đó event loop đọc trạng thái dừng.
4. Dừng đăng ký mới và hoàn tất/huỷ pending operations theo timeout.
5. Đóng từng client channel/UDP channel/server channel thuộc sở hữu event loop.
6. Close selector và giải phóng attachments, buffers, tasks, queues.
7. Join thread/đợi executor kết thúc theo deadline để tránh leak.
8. Ghi log nguyên nhân đóng nhưng không coi exception do shutdown có chủ đích là lỗi nghiệp vụ bất ngờ.

Mảnh minh họa:

~~~java
// selector và running thuộc cùng component quản lý vòng đời.
// running là AtomicBoolean, event loop kiểm tra running.get().
running.set(false);
selector.wakeup();
~~~

`wakeup()` **không tự đóng channel**, không tự giải phóng ByteBuffer hay dừng mọi processing tasks. Nó chỉ tác động việc chờ của selector; logic shutdown còn lại thuộc application.

### Khi đóng channel từ thread khác

Nếu một thread đang blocking trên channel và thread khác đóng, I/O có thể kết thúc bằng exception như `AsynchronousCloseException`. Nếu thread bị interrupt khi làm interruptible I/O, channel có thể bị đóng và báo `ClosedByInterruptException`. Tùy operation, một số path có kết quả đặc thù (ví dụ TCP input shutdown có thể trả EOF).

Vì vậy:

- Ghi nhận cancellation/shutdown là trường hợp vòng đời có chủ đích.
- Không tiếp tục đọc/ghi sau khi channel đã đóng.
- Không retry vô hạn `ClosedChannelException` trên channel cũ.
- Nếu muốn tái kết nối, **tạo channel mới**, bind/connect/register lại theo policy.
- Cẩn trọng tránh deadlocks giữa selector thread và thread yêu cầu shutdown.

## 15. Unix-domain sockets trên JDK hiện đại: family và lifecycle

**JEP 380** đưa Unix-domain socket channels vào Java **16**. Một ví dụ khởi tạo **trên JDK 17+**, nếu hệ điều hành hỗ trợ:

~~~java
// Mảnh minh họa, cần xử lý IOException và đóng channel.
try (ServerSocketChannel server =
             ServerSocketChannel.open(StandardProtocolFamily.UNIX);
     SocketChannel client =
             SocketChannel.open(StandardProtocolFamily.UNIX)) {
    // server.bind(UnixDomainSocketAddress.of(path));
    // client.connect(UnixDomainSocketAddress.of(path));
}
~~~

Đây là **mảnh khung cú pháp**, chưa bind/connect thật và không phải chương trình chạy độc lập. Unix domain socket dùng **`UnixDomainSocketAddress`** thay cho IPv4/IPv6 `InetSocketAddress`, thường dùng cho IPC trên cùng host. Tùy OS, socket path nằm trong filesystem và cần quản lý quyền/trạng thái, có thể cần cleanup pathname sau khi channel đóng.

**Điểm khác so với UDP/IP:**

- Unix-domain socket support của JDK17 được thiết kế chủ yếu cho **`SocketChannel`/`ServerSocketChannel` kiểu stream**.
- `DatagramChannel.open(StandardProtocolFamily.UNIX)` không được hỗ trợ theo Javadoc Java 17. Không cố dùng cùng family cho cả TCP-like channel và datagram channel.
- `configureBlocking`, `Selector` và `try-with-resources` vẫn là công cụ quản lý I/O mode/lifecycle đối với các selectable channels phù hợp, bất kể family.
- Không cho rằng mọi hệ điều hành hoặc bản JDK đều có hỗ trợ UNIX family hoặc cùng một tập socket options.

### Version boundary: Java 15 so với Java 16+

| API / khái niệm | Java 15 | JDK 17+ hiện đại |
| --- | --- | --- |
| `StandardProtocolFamily.INET`/`INET6` | Có | Có |
| `DatagramChannel.open(ProtocolFamily)` | Có | Có |
| `SocketChannel.open(ProtocolFamily)` | Có, từ Java 15 | Có |
| `ServerSocketChannel.open(ProtocolFamily)` | Có, từ Java 15 | Có |
| `configureBlocking`/`Selector` | Có | Có |
| `StandardProtocolFamily.UNIX` + `UnixDomainSocketAddress` | **Chưa có** | Có từ Java 16 nếu platform hỗ trợ |
| Virtual threads chính thức | **Chưa có** | Có từ Java 21, là lựa chọn khác cho blocking-style I/O |

Chỉ sử dụng API đúng với **source/target Java version** mà ứng dụng đang biên dịch. Không trộn code JDK17/21 và tuyên bố toàn bộ đều chạy Java 15.

## 16. Các lỗi API thường gặp và cách chẩn đoán

| Lỗi/hiện tượng | Nguyên nhân hay gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalBlockingModeException` khi `register` | Channel còn blocking | `configureBlocking(false)` trước register |
| `IllegalBlockingModeException` khi `configureBlocking(true)` | Channel vẫn registered | Cancel keys, selector process deregistration trước |
| `CancelledKeyException` | Key đã bị cancel nhưng code còn dùng hoặc register lại trước khi deregister | Kiểm tra lifecycle, xử lý cancellation trong selector |
| `ClosedChannelException` | I/O/register trên channel đã close | Không tái dùng; tạo channel mới nếu cần |
| `ClosedSelectorException` | Dùng selector đã close | Quản lý ownership và shutdown đúng |
| `IllegalSelectorException` | Channel và selector không tương thích provider | Dùng các channels/selectors tương thích |
| `IllegalArgumentException` khi register ops | `OP_ACCEPT` cho UDP, `OP_READ` cho server listener, v.v. | Chỉ đăng ký bits trong `validOps()` |
| `UnsupportedOperationException` mở `INET6` | Platform/JDK/OS không hỗ trợ IPv6 family | Kiểm tra môi trường hoặc fallback có chính sách |
| `UnsupportedOperationException` mở datagram `UNIX` | Java 17 không hỗ trợ Unix datagram channel | Dùng stream Unix socket hoặc IP datagram theo nhu cầu |
| `UnsupportedAddressTypeException` | Bind/connect bằng loại address không hợp family | Dùng đúng `InetSocketAddress` hoặc `UnixDomainSocketAddress` |
| `NotYetBoundException` | `ServerSocketChannel.accept()` trước bind | Bind listener trước |
| `NotYetConnectedException` | `SocketChannel.read/write` trước connect xong | Hoàn thành `connect/finishConnect` |
| `accept()==null` ở non-blocking | Chưa có client sẵn sàng | Chờ OP_ACCEPT, không xem null là SocketChannel |
| `DatagramChannel.receive()==null` | Không có UDP datagram tại thời điểm non-blocking read | Chờ readiness rồi thử lại theo state |
| `SocketChannel.read()==0` | Hiện không có bytes sẵn sàng | Không busy-spin; chờ OP_READ |
| `SocketChannel.read()==-1` | TCP peer EOF/input đã hết | Đóng/half-close theo protocol |
| `SocketChannel.write` ghi thiếu | Output buffer/OS chưa nhận hết | Giữ `ByteBuffer` và đăng ký OP_WRITE khi có backlog |
| CPU 100% khi dùng selector | Giữ `OP_WRITE` liên tục hoặc không remove selected keys | Quản lý interests và selected-key set |
| `select(0)` đợi mãi | Timeout zero có nghĩa chờ vô hạn | Dùng `selectNow()` để nonblocking poll |
| Sau `key.cancel()` vẫn isRegistered | Deregistration bị trì hoãn | Cho selector thực hiện selection operation |
| Đóng selector nhưng socket vẫn mở | `Selector.close()` không tự đóng application channels | Close mọi channel có ownership |
| Chặn shutdown vì `select()` | Chưa gọi `wakeup()`/chưa close đúng | Signal + wakeup + orderly shutdown |
| Loopback test thành công nhưng production lỗi | Address family/firewall/route/provider khác | Test môi trường thật, xử lý failures |

## 17. Checklist triển khai production

1. Xác định rõ `ProtocolFamily`: INET, INET6 hay UNIX (nếu target JDK/OS hỗ trợ).
2. Bind/connect bằng địa chỉ phù hợp family; không dựa vào dual-stack behavior không được bảo đảm.
3. Quyết định blocking hay non-blocking **trước khi bắt đầu event loop**.
4. Nếu dùng Selector: gọi `configureBlocking(false)` **trước register**.
5. Đăng ký đúng operation bits; kiểm tra `validOps()` khi cần.
6. Xử lý tất cả return values của non-blocking I/O: `null`, `0`, `-1` và partial writes.
7. Dùng `selector.selectedKeys().iterator().remove()` hoặc cơ chế đã định nghĩa để không xử lý lại key cũ.
8. Không đăng ký `OP_WRITE` khi không có bytes đang chờ gửi; tránh busy spin.
9. Nếu chuyển về blocking, cancel/deregister **toàn bộ keys** và đợi selector hoàn tất.
10. Định nghĩa ownership: ai close listener, clients, datagram channels, selector, task queues?
11. Dùng `try-with-resources` cho channels sống ngắn; long-lived channels cần lifecycle manager rõ.
12. Khi shutdown, signal, `wakeup()`, ngừng nhận việc, drain/cancel operations, close và join.
13. Có timeouts, buffer bounds, backpressure, max concurrent sessions và xử lý lỗi có kiểm soát.
14. Với UDP, nhớ datagram có thể lost/truncated; với TCP, nhớ stream không giữ message boundary.
15. Kiểm tra JDK version: UNIX family từ Java16, virtual threads từ Java21.
16. Đo CPU, memory, file descriptors, số channels còn mở và selector wakeups thay vì chỉ benchmark “blocking vs nonblocking” bằng ví dụ nhỏ.
17. Không gọi lại `configureBlocking` bừa bãi từ nhiều threads; đồng bộ với owner/event loop.
18. Dọn resource trên mọi error path, không retry trên channel đã đóng.

## 18. Bài tập tự kiểm tra và đáp án

**Bài 1.** `DatagramChannel.open(StandardProtocolFamily.INET6)` có tự chuyển I/O sang non-blocking không?

**Đáp án:** **Không.** Family xác định loại socket IPv6; channel mới vẫn mặc định blocking. Phải gọi `configureBlocking(false)` riêng.

**Bài 2.** Vì sao `channel.register(selector, OP_READ)` có thể ném `IllegalBlockingModeException`?

**Đáp án:** Vì `SelectableChannel` ở blocking mode. Phải chuyển non-blocking trước khi register.

**Bài 3.** Đã gọi `key.cancel()`, có thể lập tức `channel.configureBlocking(true)` không?

**Đáp án:** **Không chắc.** Key invalid không đồng nghĩa deregistration đã hoàn tất. Cho selector xử lý cancelled-key set bằng selection operation, và bảo đảm không còn registrations khác.

**Bài 4.** `Selector.close()` có đóng tất cả `SocketChannel` từng được register không?

**Đáp án:** **Không.** Nó deregister/invalidate keys và giải phóng tài nguyên selector, còn application channels phải do owner đóng.

**Bài 5.** Một `ServerSocketChannel` non-blocking gọi `accept()` trả `null`. Có phải connection đã đóng không?

**Đáp án:** **Không.** Có thể đơn giản chưa có connection sẵn sàng; chờ readiness `OP_ACCEPT`.

**Bài 6.** `SocketChannel.read(dst)` trả `0` khác `-1` ra sao?

**Đáp án:** `0` nghĩa là hiện chưa chuyển được byte nào; `-1` biểu thị EOF của TCP stream. Đừng hiểu 0 như peer đóng.

**Bài 7.** `SocketChannel.connect(remote)` trả `false` trong non-blocking mode. Có chắc connect thất bại không?

**Đáp án:** **Không.** Kết nối có thể đang pending; đợi `OP_CONNECT` và gọi `finishConnect()`.

**Bài 8.** `DatagramChannel.receive(dst)` trả `null` trong non-blocking mode. Có phải UDP peer gửi EOF không?

**Đáp án:** **Không.** UDP không có EOF như stream. Null nghĩa là hiện chưa có datagram để nhận.

**Bài 9.** Có thể sử dụng `StandardProtocolFamily.UNIX` với `DatagramChannel.open(...)` trên JDK17 không?

**Đáp án:** **Không**, Unix-domain datagram channel không được hỗ trợ ở Java 17; Unix-domain socket channels chuẩn dùng `SocketChannel`/`ServerSocketChannel` và xuất hiện từ Java 16.

**Bài 10.** Dùng `SocketChannel.open(ProtocolFamily)` trong source `--release 15` có hợp lệ không?

**Đáp án:** Có, API family overload cho SocketChannel được thêm từ Java 15. Nhưng `StandardProtocolFamily.UNIX` không có ở Java15.

**Bài 11.** Vì sao giữ `OP_WRITE` liên tục có thể làm CPU cao?

**Đáp án:** Socket TCP thường writable, selector có thể báo readiness liên tục ngay cả khi app không có pending bytes. Chỉ bật OP_WRITE khi cần flush output.

**Bài 12.** Vì sao gọi `selector.select(0)` không phải non-blocking poll?

**Đáp án:** Theo Javadoc, timeout 0 có nghĩa chờ vô hạn. Dùng `selectNow()` để không chờ.

**Bài 13.** Nếu muốn restart TCP client sau `channel.close()`, có thể gọi `connect()` lại trên channel cũ không?

**Đáp án:** Không. Tạo channel mới, dùng family/address đúng, rồi connect/register theo lifecycle mới.

**Bài 14.** Một event loop đang `select()` vô hạn; thread khác đặt flag `running=false`. Vì sao shutdown có thể vẫn chậm?

**Đáp án:** Vì selector chưa được đánh thức. Gọi `selector.wakeup()` (và thực hiện shutdown logic trên owner thread) hoặc close theo thiết kế.

**Bài 15.** Khi dùng `DatagramChannel.open()` không tham số, có chắc sẽ là IPv4 không?

**Đáp án:** Không. Family mặc định phụ thuộc platform/configuration. Nếu yêu cầu IPv4, chọn `StandardProtocolFamily.INET`.

**Bài 16.** Blocking mode có còn là cách lập trình hiện đại không?

**Đáp án:** Có. Nó vẫn là lựa chọn hợp lệ trong Java 15+, đặc biệt với workload đơn giản; JDK21+ còn có virtual threads giúp mở rộng blocking-style code. Non-blocking/Selector phù hợp khi cần multiplex nhiều channels và quản lý event loops, không phải thay thế bắt buộc.

## 19. Tài liệu kỹ thuật còn áp dụng

- **Oracle Java SE 17 — `SelectableChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html
- **Oracle Java SE 17 — `Selector`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- **Oracle Java SE 17 — `SelectionKey`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- **Oracle Java SE 17 — `DatagramChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/DatagramChannel.html
- **Oracle Java SE 17 — `SocketChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- **Oracle Java SE 17 — `ServerSocketChannel`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html
- **Oracle Java SE 17 — `StandardProtocolFamily`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardProtocolFamily.html
- **JEP 380 — Unix-Domain Socket Channels (Java 16):** https://openjdk.org/jeps/380
- **JEP 444 — Virtual Threads (Java 21):** https://openjdk.org/jeps/444

**Kết luận:** chọn **protocol family** quyết định họ socket/address, còn chọn **blocking mode** quyết định cách thao tác I/O chờ/readiness. Mọi selectable channel mới đều **blocking mặc định**; muốn sử dụng `Selector` phải đặt **non-blocking trước register**. Khi muốn chuyển về blocking, phải **cancel và thực sự deregister** toàn bộ keys, không chỉ gọi `cancel()`. Cuối vòng đời, quản lý sở hữu và đóng cả **channels lẫn selectors**, dùng `try-with-resources`, xử lý shutdown/wakeup, partial I/O và errors. Đừng nhầm family, mode, registration và đóng tài nguyên — chúng là các phần **độc lập nhưng tương tác** của thiết kế Java NIO.
