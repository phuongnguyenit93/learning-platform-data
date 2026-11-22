# Phân biệt I/O chặn và không chặn khi điều khiển UDP (Java 15+)

## 1. Bài toán: cùng là UDP nhưng luồng xử lý có thể rất khác

Khi viết chương trình Java gửi/nhận UDP, lập trình viên thường gặp hai kiểu API:

- **`java.net.DatagramSocket` / `DatagramPacket`:** lập trình theo kiểu socket truyền thống, điển hình là lời gọi `receive(...)` **chặn** luồng khi chưa có datagram.
- **`java.nio.channels.DatagramChannel`:** API NIO có thể chạy ở chế độ **chặn** (*blocking*) hoặc **không chặn** (*non-blocking*). Ở chế độ không chặn, nó có thể phối hợp với `Selector` để phục vụ nhiều socket qua một hoặc vài event-loop thread.

**Điểm quan trọng nhất: UDP không tự quyết định I/O là chặn hay không chặn.** UDP là giao thức vận chuyển datagram; trạng thái chặn/không chặn nằm ở **API và cấu hình I/O của chương trình**.

Bài này sẽ làm rõ:

1. `DatagramSocket.receive` có chờ không, và `setSoTimeout` khác non-blocking như thế nào.
2. Vì sao **`DatagramChannel` mặc định vẫn là blocking**, dù thuộc NIO.
3. `configureBlocking(false)` thay đổi kết quả `DatagramChannel.receive` ra sao.
4. `Selector`, `SelectionKey.OP_READ`, `select(timeout)` và vòng lặp xử lý sự kiện hoạt động thế nào.
5. Cách kiểm tra dữ liệu bằng `ByteBuffer`, giữ đúng ranh giới datagram và tránh vòng lặp chiếm CPU.
6. Chọn giữa blocking và non-blocking theo số socket, mô hình luồng, độ phức tạp, đo đạc hiệu năng.

Đây là các API **còn áp dụng trong Java hiện đại**, tương thích Java 15. `DatagramSocket` vẫn là API hợp lệ; không nên tuyên bố nó đã bị thay thế hoặc deprecated chỉ vì NIO tồn tại. Java 15 cũng có **JEP 373**, cải tiến cách triển khai nền cho các API DatagramSocket cũ mà không bắt ứng dụng phải viết lại sang `DatagramChannel`.

## 2. UDP truyền datagram, không truyền một luồng byte như TCP

Trước khi so sánh hai kiểu I/O, phải nhớ đặc điểm UDP:

- **Không có kết nối vận chuyển bảo đảm** giống TCP handshake. Mỗi datagram có địa chỉ đích, cổng đích, payload; phía nhận có thể nhận địa chỉ/cổng nguồn.
- **Không bảo đảm datagram đến đích**, không bảo đảm đúng thứ tự và không tự loại trừ datagram trùng lặp.
- **Giữ ranh giới thông điệp:** một lần nhận xử lý **một datagram**, không phải một dòng byte kéo dài như TCP. Nếu bộ đệm quá nhỏ, phần dư của datagram có thể **bị cắt bỏ**, không phải đợi lần `receive` kế tiếp để đọc tiếp.
- UDP không tự cung cấp retry, acknowledgment, backpressure đáng tin cậy, flow control hay mã hóa. Nếu nghiệp vụ cần các thuộc tính đó, thiết kế protocol tầng ứng dụng hoặc chọn transport phù hợp.
- `DatagramChannel.connect(remote)` **không thực hiện TCP handshake**. Nó đặt địa chỉ peer mặc định/điều kiện nhận-gửi và cho phép dùng `read/write` trên channel đã connect, nhưng không biến UDP thành TCP.

Ví dụ một datagram:

~~~text
Sender: 127.0.0.1:53001
    |
    | UDP datagram: "PING"
    v
Receiver: 127.0.0.1:53002
    |
    +-- Được nhận => một thao tác receive lấy datagram đó
    |
    +-- Chưa có datagram => lời gọi có thể chờ hoặc trả về ngay
        tùy BLOCKING MODE của API
~~~

**Blocking/non-blocking nói về hành vi gọi I/O của thread**, không nói về khả năng datagram đến đích, tính tin cậy hay tính thứ tự của UDP.

## 3. I/O chặn (blocking) nghĩa là gì?

**Blocking I/O** là kiểu lời gọi có thể khiến thread đang thực thi **đợi** cho tới khi có điều kiện tiến hành, hoặc xuất hiện timeout/lỗi/ngắt do đóng socket hay nguyên nhân khác.

Với UDP, ví dụ kinh điển:

~~~java
DatagramSocket socket = new DatagramSocket(9999);
byte[] bytes = new byte[2048];
DatagramPacket packet = new DatagramPacket(bytes, bytes.length);

socket.receive(packet); // CHO den khi co datagram hoac loi/timeout.
~~~

Nếu chưa có UDP datagram phù hợp, thread gọi `receive` không được trả lại ngay để tự xử lý việc khác. Khi datagram đến, `DatagramPacket` chứa payload, độ dài thực nhận, địa chỉ và cổng nguồn.

Trong code thật cần đóng socket khi không dùng nữa:

~~~java
try (DatagramSocket socket = new DatagramSocket(9999)) {
    byte[] bytes = new byte[2048];
    DatagramPacket packet = new DatagramPacket(bytes, bytes.length);
    socket.receive(packet);
    System.out.println("bytes=" + packet.getLength());
}
~~~

Đây là **minh họa socket nghe cổng 9999**, không phải chương trình đầy đủ có sender. Nếu không có datagram gửi đến, lệnh `receive` có thể chờ rất lâu.

### 3.1. `DatagramSocket.setSoTimeout`: giới hạn thời gian chờ, không chuyển thành NIO

`DatagramSocket` có API:

~~~java
socket.setSoTimeout(1000);
~~~

Giá trị là **milliseconds**. Khi `SO_TIMEOUT > 0`, một `receive` đang chờ có thể ném `SocketTimeoutException` nếu hết thời hạn mà không nhận được datagram phù hợp. `SO_TIMEOUT == 0` có nghĩa **chờ vô hạn** cho đến khi có dữ liệu, đóng socket hoặc lỗi khác.

Ví dụ trong ngữ cảnh đã có socket:

~~~java
try {
    socket.receive(packet);
    System.out.println("received=" + packet.getLength());
} catch (SocketTimeoutException timeout) {
    System.out.println("no packet before deadline");
}
~~~

**`setSoTimeout(1000)` vẫn là blocking I/O**: thread có thể **chờ tới 1000 ms**. Timeout không làm `receive` lập tức trả “chưa có packet” như một channel non-blocking.

Sau khi ném `SocketTimeoutException`, socket vẫn hợp lệ nếu không có nguyên nhân lỗi khác; bạn có thể tiếp tục nhận datagram hoặc thực hiện logic timeout.

### 3.2. Khi nào blocking phù hợp?

Blocking UDP thường phù hợp với:

- Chương trình nhỏ, một hoặc ít socket UDP, lưu lượng vừa phải.
- Công cụ chẩn đoán, tác vụ nền đơn giản, client gửi rồi đợi response.
- Một thread chuyên nhận datagram, đẩy dữ liệu sang hàng đợi/worker pool.
- Server có ít đầu vào và cần code dễ hiểu, dễ debug hơn một event loop.

**Chặn thread không tự động đồng nghĩa “chậm”.** JVM/OS có thể ngủ thread hiệu quả khi chờ dữ liệu. Với số socket và số thread phù hợp, blocking design có thể đơn giản, ổn định và đủ hiệu năng.

## 4. `DatagramChannel`: NIO nhưng mặc định vẫn chặn

Một ngộ nhận phổ biến: “Dùng `java.nio` thì tự động non-blocking.” **Sai.**

`DatagramChannel.open(...)` tạo một channel **ở blocking mode theo mặc định**. Có thể kiểm tra `channel.isBlocking()`.

~~~java
import java.net.InetSocketAddress;
import java.nio.channels.DatagramChannel;

try (DatagramChannel channel = DatagramChannel.open()) {
    channel.bind(new InetSocketAddress("127.0.0.1", 0));

    System.out.println(channel.isBlocking()); // true
}
~~~

Một `DatagramChannel` ở blocking mode sẽ có `receive(ByteBuffer)` **chờ** nếu chưa có datagram phù hợp, giống ý nghĩa chờ dữ liệu của socket thông thường.

Khác biệt trong API là dữ liệu được ghi vào `ByteBuffer` và `receive` trả về `SocketAddress` của nguồn:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(2048);
SocketAddress sender = channel.receive(buffer);
buffer.flip();
~~~

Đoạn trên là **minh họa trong ngữ cảnh có `channel`**, chưa phải chương trình đầy đủ. Nếu chưa có datagram, `receive` có thể chặn lâu. `buffer.flip()` chuẩn bị vùng bytes vừa ghi để đọc.

### 4.1. `ByteBuffer` có state: position, limit, capacity

Quy trình đọc đúng thường là:

~~~java
buffer.clear();                 // position = 0, limit = capacity
SocketAddress source = channel.receive(buffer); // ghi bytes
if (source != null) {
    buffer.flip();              // position = 0, limit = bytes da ghi
    String text = StandardCharsets.UTF_8.decode(buffer).toString();
}
~~~

Trong đoạn minh họa, cần import `java.nio.ByteBuffer`, `java.net.SocketAddress` và `java.nio.charset.StandardCharsets`. Không phải ví dụ độc lập nếu chưa có `channel`/`buffer`.

- `clear()` **không xóa byte thật** trong bộ đệm; nó đặt lại chỉ số để ghi dữ liệu mới.
- `receive` đẩy bytes vào `ByteBuffer` tại `position` hiện tại, tăng position.
- `flip()` chuyển buffer từ trạng thái ghi sang đọc.
- Nếu quên `clear` trước lần nhận tiếp theo, buffer có thể không còn chỗ ghi.
- Nếu quên `flip`, decoder có thể đọc phần vùng rỗng hoặc dữ liệu sai.

Với UDP, **mỗi datagram phải được xử lý theo đúng độ dài**. Không giả định một lần nhận luôn đủ toàn bộ datagram nếu capacity nhỏ hơn payload.

## 5. I/O không chặn: `configureBlocking(false)`

Để đưa `DatagramChannel` sang non-blocking mode, gọi:

~~~java
channel.configureBlocking(false);
System.out.println(channel.isBlocking()); // false
~~~

Sau đó:

~~~java
buffer.clear();
SocketAddress source = channel.receive(buffer);
if (source == null) {
    // Khong co datagram san sang o thoi diem nay.
    // Thread KHONG bi giu cho packet.
} else {
    buffer.flip();
    // Xu ly mot datagram duoc nhan.
}
~~~

**Ngữ nghĩa cốt lõi:**

- Ở blocking mode, `receive` có thể **chờ tới khi có datagram**.
- Ở non-blocking mode, nếu chưa có datagram, `receive` **trả `null` ngay** thay vì chờ.
- Nếu có datagram, nó ghi bytes vào buffer và trả `SocketAddress` nguồn.
- `null` **không** có nghĩa kết nối đóng, peer offline hoặc UDP “đã kết thúc”. Nó chỉ có nghĩa **chưa có datagram khả dụng ngay lúc đó**.
- `receive` có thể ném `IOException` hoặc lỗi khi channel đã đóng/operation không hợp lệ. Phải xử lý exception riêng, không biến tất cả exception thành trạng thái “chưa có dữ liệu”.

Không đặt trong vòng lặp liên tục kiểu sau mà không có cơ chế chờ:

~~~java
// BUG: CPU co the bi su dung cao khi socket rong.
while (true) {
    buffer.clear();
    SocketAddress source = channel.receive(buffer);
    if (source == null) {
        continue; // busy spinning
    }
    processDatagram(buffer);
}
~~~

Đây là **pseudocode minh họa lỗi**, `processDatagram` không phải API JDK. Lặp liên tục khi `receive==null` sẽ khiến thread quay vòng, tốn CPU mà không có dữ liệu.

Giải pháp phổ biến là **`Selector` chờ sự kiện readiness**, hoặc dùng lịch poll có kiểm soát khi bài toán rất nhỏ.

### 5.1. Không chặn ≠ không bao giờ đợi ở mọi nơi

Ở event loop, **channel được cấu hình non-blocking** để mỗi thao tác `receive` không giữ thread quá lâu. Tuy nhiên, chính event loop vẫn có thể **chờ** trong `selector.select()` để tránh chiếm CPU.

Đây không phải mâu thuẫn:

- `DatagramChannel.receive` không chặn.
- `Selector.select(timeout)` **có thể chặn thread event loop** cho tới khi có channel sẵn sàng hoặc timeout.
- Khi `select` báo sẵn sàng, event loop xử lý nhanh những datagram đang chờ.

**Non-blocking I/O không nhất thiết là “không có thread chờ”.** Nó là cách tổ chức chờ **sự kiện tập trung** thay vì tạo một thread blocking trên mỗi socket.

## 6. `Selector` và `OP_READ`: chờ có khả năng nhận

`Selector` theo dõi nhiều `SelectableChannel` qua các `SelectionKey`. `DatagramChannel` hỗ trợ đăng ký readiness khi **đang ở non-blocking mode**.

~~~java
channel.configureBlocking(false);

try (Selector selector = Selector.open()) {
    channel.register(selector, SelectionKey.OP_READ);

    int selected = selector.select(1000);
    if (selected > 0) {
        // Co it nhat mot key bao readiness.
        // Duyet selector.selectedKeys() va receive(...)
    }
}
~~~

**Điều kiện bắt buộc:** Channel đã đăng ký với một selector phải ở non-blocking mode; cố đăng ký channel đang blocking có thể ném `IllegalBlockingModeException`.

Các khái niệm:

| Thành phần | Vai trò |
| --- | --- |
| `channel.configureBlocking(false)` | Cho phép các thao tác I/O channel trả về ngay khi chưa thể hoàn thành. |
| `selector.register(channel, OP_READ)` hoặc `channel.register(selector, OP_READ)` | Yêu cầu selector theo dõi khả năng đọc của channel. |
| `selector.select(timeout)` | Chờ tối đa khoảng thời gian được chỉ định để có readiness; có thể trả `0` khi hết thời gian. |
| `selector.selectNow()` | Kiểm tra readiness **không chờ**. |
| `selector.selectedKeys()` | Các key đã được chọn trong lượt xử lý; ứng dụng phải xử lý và loại key khỏi selected set. |
| `key.isReadable()` | Channel được báo khả năng đọc theo `OP_READ`. |
| `channel.receive(buffer)` | Thực sự đọc datagram nếu có; trong non-blocking mode có thể vẫn trả `null`. |
| `key.cancel()` | Hủy registration khi không còn cần theo dõi channel. |

**Readiness là một gợi ý rằng operation có thể tiến hành, không phải một cam kết nghiệp vụ.** Một thread khác có thể đọc mất datagram trước khi event loop gọi `receive`; non-blocking `receive` phải luôn xử lý được kết quả `null`.

### 6.1. Vì sao nên remove/clear selected keys?

Sau `select`, `Selector.selectedKeys()` là một tập các key mà selector đã chọn. Nếu không loại bỏ key sau khi xử lý, event loop có thể tiếp tục xử lý lại một key đã chọn và tạo logic lặp không mong muốn.

Một pattern phổ biến:

~~~java
Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
while (iterator.hasNext()) {
    SelectionKey key = iterator.next();
    iterator.remove();

    if (!key.isValid()) {
        continue;
    }
    if (key.isReadable()) {
        DatagramChannel dc = (DatagramChannel) key.channel();
        buffer.clear();
        SocketAddress source = dc.receive(buffer);
        if (source != null) {
            buffer.flip();
            // Xu ly datagram.
        }
    }
}
~~~

Đây là **mảnh mã minh họa trong event loop**, chưa phải class độc lập. Cần các biến và imports phù hợp.

### 6.2. `OP_WRITE` và nguy cơ busy loop

`DatagramChannel` hỗ trợ hoạt động gửi; với non-blocking mode, `send(ByteBuffer, SocketAddress)` có thể **trả 0** khi hệ thống không thể gửi datagram ngay. Một event loop có thể theo dõi `OP_WRITE` khi có dữ liệu cần gửi lại.

Tuy nhiên, ở nhiều môi trường, socket UDP thường **luôn được đánh dấu writable**. Nếu đăng ký `OP_WRITE` không điều kiện trong mọi vòng lặp, `select` có thể trả ngay liên tục và làm CPU cao. Vì vậy:

1. Chỉ quan tâm `OP_WRITE` khi có lý do thực sự cần gửi lại/buffer pending.
2. Xử lý `send` và kết quả số byte gửi một cách chính xác.
3. Bỏ `OP_WRITE` khỏi interest set khi không còn việc gửi đang chờ.
4. Không giả định OS cung cấp congestion/backpressure đáng tin cậy cho UDP giống TCP.

Đối với bài học nhận UDP, `OP_READ` là event quan trọng nhất.

### 6.3. Selector theo dõi nhiều channel, không phải từng datagram

Một selector có thể đăng ký nhiều `DatagramChannel`, mỗi channel bind vào một cổng/interface khác nhau. **Một key tương ứng một channel**, không phải từng datagram. Khi channel readable, ứng dụng có thể nhận **nhiều datagram đang chờ** trong một lượt:

~~~java
for (int n = 0; n < 32; n++) {
    buffer.clear();
    SocketAddress source = dc.receive(buffer);
    if (source == null) {
        break;
    }
    buffer.flip();
    // Xu ly datagram nay.
}
~~~

Số `32` là **giới hạn batch minh họa**, giúp event loop không để một socket có lưu lượng lớn chiếm hết CPU của các socket khác. Phần xử lý datagram cần đầy đủ, thường đẩy công việc nặng sang worker/queue riêng.

## 7. Ví dụ Java hoàn chỉnh: blocking, non-blocking và Selector trong một chương trình

Chương trình sau dùng **localhost IPv4 `127.0.0.1`** để không cần server bên ngoài. Nó minh họa:

- `DatagramSocket.receive` với `SO_TIMEOUT=120ms`.
- `DatagramChannel` mặc định **blocking=true**.
- Gửi datagram trước rồi nhận bằng blocking channel.
- Chuyển channel sang **non-blocking** và xác minh `receive` trả `null` khi hàng đợi trống.
- Đăng ký `OP_READ` với `Selector`, gửi datagram thứ hai và đọc sau readiness.
- Quản lý `ByteBuffer.clear/flip` và đóng tài nguyên bằng try-with-resources.

### 7.1. File `UdpBlockingNonBlockingDemo.java`

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class UdpBlockingNonBlockingDemo {
    private static String text(ByteBuffer data) {
        data.flip();
        return StandardCharsets.UTF_8.decode(data).toString();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramSocket socket =
                     new DatagramSocket(new InetSocketAddress(loopback, 0))) {
            socket.setSoTimeout(120);
            System.out.println("socketTimeoutMs=" + socket.getSoTimeout());
            try {
                byte[] bytes = new byte[64];
                socket.receive(new DatagramPacket(bytes, bytes.length));
                System.out.println("socketTimeout=false");
            } catch (SocketTimeoutException expected) {
                System.out.println("socketTimeout=true");
            }
        }

        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramChannel sender =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            receiver.bind(new InetSocketAddress(loopback, 0));
            sender.bind(new InetSocketAddress(loopback, 0));
            SocketAddress address = receiver.getLocalAddress();

            System.out.println("defaultBlocking=" + receiver.isBlocking());
            sender.send(
                    ByteBuffer.wrap("blocking".getBytes(StandardCharsets.UTF_8)),
                    address);

            ByteBuffer buffer = ByteBuffer.allocate(128);
            SocketAddress from = receiver.receive(buffer);
            System.out.println("blockingSourcePresent=" + (from != null));
            System.out.println("blockingReceived=" + text(buffer));

            receiver.configureBlocking(false);
            System.out.println("nonBlocking=" + !receiver.isBlocking());

            buffer.clear();
            System.out.println("noPacketReturnsNull=" +
                    (receiver.receive(buffer) == null));

            try (Selector selector = Selector.open()) {
                receiver.register(selector, SelectionKey.OP_READ);

                sender.send(
                        ByteBuffer.wrap("event".getBytes(StandardCharsets.UTF_8)),
                        address);
                int selected = selector.select(2000);
                System.out.println("selectorReady=" + (selected > 0));

                boolean read = false;
                for (SelectionKey key : selector.selectedKeys()) {
                    if (key.isValid() && key.isReadable()) {
                        buffer.clear();
                        SocketAddress source =
                                ((DatagramChannel) key.channel())
                                        .receive(buffer);
                        if (source != null) {
                            System.out.println(
                                    "selectorReceived=" + text(buffer));
                            read = true;
                        }
                    }
                }
                selector.selectedKeys().clear();
                System.out.println("readViaSelector=" + read);
            }
        }
    }
}
~~~

### 7.2. Biên dịch và chạy

Lưu đúng tên file rồi chạy trong terminal, không cần thư viện ngoài JDK:

~~~bash
javac --release 15 -encoding UTF-8 UdpBlockingNonBlockingDemo.java
java UdpBlockingNonBlockingDemo
~~~

Lệnh `--release 15` cho phép biên dịch API/cú pháp phù hợp Java 15 khi dùng JDK mới hơn. Chương trình này **đã được biên dịch và chạy trên JDK 24**.

**Đầu ra quan sát được ở lần kiểm thử trên JDK 24/localhost:**

~~~text
socketTimeoutMs=120
socketTimeout=true
defaultBlocking=true
blockingSourcePresent=true
blockingReceived=blocking
nonBlocking=true
noPacketReturnsNull=true
selectorReady=true
selectorReceived=event
readViaSelector=true
~~~

**Lưu ý về UDP và scheduler:** đây là kết quả đã kiểm thử trong môi trường loopback, **không phải bảo đảm mạng và thời gian luôn cho kết quả y hệt**. `Selector.select(2000)` có thể trả `0` nếu không có readiness trong 2 giây. UDP có thể mất datagram ngay cả ở môi trường bất thường. Trong ứng dụng production phải có xử lý timeout và không giả định packet chắc chắn đến.

Giải thích từng dòng:

1. `socketTimeoutMs=120`: socket blocking được cấu hình thời hạn tối đa cho `receive` là 120 ms.
2. `socketTimeout=true`: không ai gửi UDP tới cổng socket ấy nên `receive` chờ rồi ném `SocketTimeoutException`.
3. `defaultBlocking=true`: `DatagramChannel` vừa mở **chưa** phải non-blocking.
4. `blockingSourcePresent=true` và `blockingReceived=blocking`: channel đã nhận một datagram gửi nội bộ.
5. `nonBlocking=true`: sau `configureBlocking(false)`, channel không còn ở blocking mode.
6. `noPacketReturnsNull=true`: khi chưa có datagram kế tiếp, `receive` trả `null` ngay.
7. `selectorReady=true`: `OP_READ` được báo có thể nhận sau khi sender gửi datagram `event`.
8. `selectorReceived=event`: event loop nhận được datagram bằng non-blocking `receive`.
9. `readViaSelector=true`: xác nhận trong vòng xử lý selected keys đã đọc được datagram.

Chương trình **gửi trước khi gọi `receive`** trong trường hợp blocking để tránh làm bài học phụ thuộc thời gian một thread khác phải đến đúng lúc. Mục đích là kiểm tra **chế độ và kết quả của API**, không cố chứng minh một thread bị block đúng bao nhiêu milliseconds.

## 8. Các trạng thái và giá trị trả về không nên nhầm lẫn

| API / tình huống | Khi có dữ liệu/sẵn sàng | Khi chưa có dữ liệu | Điều cần nhớ |
| --- | --- | --- | --- |
| `DatagramSocket.receive(DatagramPacket)` | Điền thông tin packet và trả về kiểu `void`. | Chờ; có thể `SocketTimeoutException` nếu `SO_TIMEOUT>0`. | Timeout vẫn là blocking I/O. |
| `DatagramChannel.receive(ByteBuffer)` **blocking** | Trả `SocketAddress` nguồn. | Chờ datagram hoặc lỗi. | `DatagramChannel` mặc định ở chế độ này. |
| `DatagramChannel.receive(ByteBuffer)` **non-blocking** | Trả `SocketAddress` nguồn. | Trả **`null` ngay**. | `null` không phải EOF. |
| `DatagramChannel.send(ByteBuffer, target)` non-blocking | Trả số byte đã gửi. | Có thể trả **`0`** nếu không gửi được ngay. | Không dùng retry nóng không giới hạn; UDP không cam kết delivery. |
| `Selector.select(timeout)` | Trả số key được chọn khi readiness. | Có thể trả **0** khi hết thời hạn. | Selector có thể chặn thread dù channel không chặn. |
| `Selector.selectNow()` | Trả kết quả kiểm tra ngay. | Trả 0 nếu chưa sẵn sàng. | Poll liên tục không nghỉ dễ gây busy loop. |

### 8.1. `receive==null` không phải đóng socket hay EOF

Đối với `DatagramChannel` non-blocking, `null` là câu trả lời “không có datagram để nhận ngay lúc này”. Không phải:

- Remote đã đóng kết nối TCP (UDP không có EOF kiểu TCP).
- Dịch vụ nguồn vĩnh viễn offline.
- Packet trước đó chắc chắn bị mất.
- Có thể bỏ qua xử lý socket vĩnh viễn.

Một datagram hoàn toàn có thể đến **ngay sau khi `receive` trả `null`**, đó là lý do cần `Selector` hoặc cơ chế poll hợp lý.

### 8.2. `send` thành công không chứng minh peer đã nhận

`DatagramChannel.send` trả số byte được gửi từ buffer/được chấp nhận ở phía hệ thống cục bộ, **không phải acknowledgment của remote**. Một datagram có thể bị rơi do firewall, bộ đệm, mạng hoặc ứng dụng bên nhận.

Nếu cần truyền tin đáng tin cậy, phải có protocol tầng ứng dụng cho sequence, acknowledgment, retransmission, duplicate detection và timeout, hoặc chọn transport cung cấp các tính chất cần thiết.

## 9. Khi nào dùng blocking, khi nào dùng non-blocking?

| Tiêu chí | Blocking `DatagramSocket` hoặc `DatagramChannel` | Non-blocking `DatagramChannel` + `Selector` |
| --- | --- | --- |
| Đơn giản, dễ đọc | **Rất phù hợp**, code nhận datagram tuần tự. | Cần event loop, interest set và quản lý state. |
| Ít socket, khối lượng vừa | Thường đủ tốt. | Có thể là phức tạp không cần thiết. |
| Nhiều socket độc lập | Có thể cần nhiều thread nhận. | **Một selector có thể multiplex nhiều channel.** |
| Chờ khi không có packet | Thread gọi `receive` chờ. | Event loop chờ tập trung ở `select`; `receive` không chờ. |
| CPU khi không có packet | Thường tốt: thread ngủ chờ. | Tốt nếu dùng `select`; tệ nếu busy-spin `receive==null`. |
| Xử lý tác vụ chậm | Có thể giao cho worker pool; tránh làm nghẽn receiver. | **Càng cần** tránh chạy tác vụ dài trên event-loop thread. |
| Debug và tư duy điều khiển | Dễ theo từng bước request/response. | Cần quan sát key state, buffers, registration, concurrency. |
| Hiệu năng tổng thể | Phụ thuộc tải, JVM, OS, mô hình thread. | Không mặc nhiên nhanh hơn; có overhead selector và event loop. |

Một cách chọn thực tế:

- **Một UDP client gửi request và chờ response:** `DatagramSocket` với `setSoTimeout` có thể đủ.
- **Một server UDP chuyên nhận packet ở một cổng:** một blocking receiver thread + queue cũng có thể phù hợp.
- **Gateway nhiều cổng/luồng UDP hoặc cần multiplex nhiều socket:** `DatagramChannel` non-blocking + `Selector` thường có lợi về số thread.
- **Xử lý mỗi packet phải truy cập database/HTTP chậm:** dù dùng API nào, nên tách I/O khỏi business work, có queue/backpressure và giới hạn số task đồng thời.

Không đoán hiệu năng bằng tên API. Hãy đo throughput, latency p95/p99, CPU, memory, packet drops, context switches và số thread theo workload thực tế.

## 10. Buffer size, datagram truncation và địa chỉ nguồn

### 10.1. Một datagram không được chia thành nhiều lần receive

Giả sử client gửi một datagram có payload dài 2.000 bytes, nhưng server cấp:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(128);
~~~

Nếu datagram được nhận, phần vượt capacity có thể **bị bỏ**, và lần `receive` kế tiếp không tiếp tục đọc nốt 1.872 bytes còn lại. UDP giữ biên datagram, không hoạt động như stream TCP.

Do đó:

- Xác định **maximum UDP payload** mà protocol của bạn cho phép.
- Cấp buffer đủ chứa datagram hợp lệ, kiểm tra length và version.
- Giới hạn kích thước để phòng DoS.
- Tránh gửi datagram quá lớn gây **IP fragmentation**, dễ tăng rủi ro mất packet.
- Nếu cần payload lớn, thiết kế fragmentation/reassembly có giới hạn và chống duplicate, hoặc dùng transport khác.

`DatagramPacket` còn có offset và length. Nếu tái sử dụng cùng một đối tượng `DatagramPacket` qua nhiều lần `receive`, phải **reset length về capacity cho lần nhận tiếp theo** khi cần, vì giá trị length sau receive phản ánh dữ liệu đã nhận.

### 10.2. `SocketAddress` trả về giúp xác định nguồn

`DatagramChannel.receive` trả `SocketAddress` nguồn của datagram được nhận:

~~~java
SocketAddress source = channel.receive(buffer);
if (source != null) {
    // source la dia chi/port nguon cua datagram.
}
~~~

**Nguồn UDP không phải chứng thực danh tính.** Địa chỉ và cổng nguồn có thể bị giả mạo tùy topology; nếu request có tác động nhạy cảm, cần cơ chế xác thực/chữ ký/MAC hoặc giao thức bảo mật phù hợp.

Không tự gửi phản hồi chứa dữ liệu nhạy cảm tới địa chỉ nguồn không tin cậy. Bảo vệ hệ thống khỏi UDP reflection/amplification bằng rate limit, giới hạn response size và điều kiện xác thực khi cần.

### 10.3. `connect` không tạo tính tin cậy

`DatagramChannel.connect(remote)` chỉ liên kết channel với một peer và cho phép dùng `read`/`write` như thao tác với peer mặc định; nó **không bảo đảm** peer tồn tại, không tự xác minh người nhận, không tạo một kết nối TCP.

Khi non-blocking, `read/write` của channel đã connect cũng tuân theo mode non-blocking. Nhưng vẫn là UDP: packet có thể mất, sai thứ tự, trùng lặp; việc xử lý retry và xác thực vẫn cần thiết.

### 10.4. IPv4 và IPv6

Ví dụ dùng `StandardProtocolFamily.INET` và `127.0.0.1` để rõ ràng IPv4. Nếu hệ thống dùng IPv6, cấu hình địa chỉ/protocol family tương ứng, ví dụ `INET6`, theo yêu cầu môi trường.

Không mặc định `localhost` luôn phân giải thành IPv4; một số máy dùng IPv6 loopback `::1` trước. Khi thử nghiệm đa môi trường, chọn family/address nhất quán và không hard-code network interface production vào ví dụ.

## 11. Event loop đúng không nên làm các việc nặng ngay trong vòng đọc

Non-blocking I/O cho phép một thread quản lý nhiều channel, nhưng nếu xử lý một datagram mất nhiều thời gian ngay trong event loop, các socket khác sẽ không được phục vụ kịp thời.

Mô hình tham khảo:

~~~text
Selector thread
    |
    +-- select(timeout)
    |
    +-- selected OP_READ
    |
    +-- receive ByteBuffer, copy bytes can thiet
    |
    +-- validate size/header nhanh
    |
    +-- queue co gioi han -> worker pool / business handlers
    |
    +-- tiep tuc doc socket khac
~~~

Worker có thể phân tích payload, gọi database hoặc thực hiện tính toán phức tạp; event loop tiếp tục I/O. **Phải sao chép payload trước khi tái sử dụng `ByteBuffer`** nếu worker xử lý bất đồng bộ; nếu không, worker có thể đọc nhầm bytes của datagram kế tiếp.

Các điểm kỹ thuật quan trọng:

- Giới hạn kích thước queue, số concurrent tasks và chính sách khi queue đầy. UDP không cung cấp backpressure end-to-end mặc định.
- Tránh dùng `ByteBuffer` mutable chung giữa nhiều threads nếu không có đồng bộ hoặc tách ownership.
- Dùng `SelectionKey.attach(...)` để giữ state per-channel khi cần, nhưng không giữ tài nguyên mãi.
- Khi thay interest ops hoặc đăng ký channel từ thread khác, dùng `Selector.wakeup()` phù hợp để event loop sớm xử lý thay đổi.
- Xử lý hủy key, đóng socket, exception và shutdown; không tạo vòng vô hạn nuốt lỗi.
- Nếu một channel luôn readable vì nhiều datagram, giới hạn số packet xử lý mỗi lần để socket khác không đói tài nguyên.

**Một selector có thể theo dõi nhiều socket, nhưng không biến một DatagramChannel thành nhiều datagram được xử lý song song an toàn tự động.** Đồng thời nhận nhiều thread trên cùng channel cần thiết kế ownership và buffer đúng.

## 12. Timeout, lỗi và đóng tài nguyên

### 12.1. Timeout ở blocking và non-blocking

Với `DatagramSocket`:

~~~java
socket.setSoTimeout(3000);
socket.receive(packet); // Co the cho toi 3 giay.
~~~

Nếu hết thời gian, có thể ném `SocketTimeoutException`, nên caller có thể retry, báo deadline hoặc dừng operation. Đây là **thời hạn của receive**, không phải xác nhận UDP đã mất packet chắc chắn.

Với `DatagramChannel` non-blocking + `Selector`:

~~~java
int count = selector.select(3000);
if (count == 0) {
    // Khong co ready key trong thoi gian cho.
}
~~~

**Không xem timeout của selector như timeout của từng request nghiệp vụ.** Một selector theo dõi nhiều channel; một key khác có readiness không có nghĩa request bạn quan tâm đã nhận được response. Deadline của từng pending request cần được ứng dụng quản lý riêng.

### 12.2. Đóng socket/channel

`DatagramSocket` và `DatagramChannel` triển khai `AutoCloseable` hoặc `Closeable`, nên dùng try-with-resources. Đóng socket/channel có thể khiến các thao tác đang chờ kết thúc qua exception/hành vi API phù hợp; không dựa vào đó thay cho cancellation protocol nghiệp vụ.

Ví dụ trên dùng:

~~~java
try (DatagramChannel receiver = DatagramChannel.open();
     DatagramChannel sender = DatagramChannel.open()) {
    // Thao tac
}
~~~

Khi selector có nhiều registrations, cần đóng resources trong thứ tự hợp lý, cancel keys khi cần và bảo đảm event loop dừng. Không để thread sống mãi sau khi service shutdown.

## 13. Những nhầm lẫn phổ biến

| Nhận định sai | Vấn đề | Hiểu đúng |
| --- | --- | --- |
| “UDP là non-blocking.” | UDP là transport, không quyết định hành vi thread. | Mode tùy `DatagramSocket` hoặc `DatagramChannel`. |
| “Có `DatagramChannel` là non-blocking.” | Channel mặc định **blocking=true**. | Gọi `configureBlocking(false)` khi cần. |
| “`setSoTimeout` chuyển DatagramSocket sang non-blocking.” | Nó vẫn chờ đến data/timeout. | Timeout chỉ giới hạn thời gian blocking receive. |
| “`receive==null` nghĩa peer đóng.” | UDP không có EOF TCP; non-blocking có thể chưa có datagram. | Cứ theo dõi readiness và xử lý packet sau. |
| “`Selector.select` không bao giờ chặn.” | `select(timeout)` có thể chờ. | Channel operations non-blocking; selector là chỗ chờ readiness. |
| “Cứ poll `receive` trong while(true) là nhanh nhất.” | Busy spin tốn CPU khi không có packet. | Dùng `Selector` hoặc lịch poll có giới hạn. |
| “Selector có thể register channel blocking.” | `register` có thể ném `IllegalBlockingModeException`. | Chuyển sang non-blocking trước. |
| “Một selected key là một packet.” | Key gắn với channel. | Có thể có nhiều datagram chờ trên một channel. |
| “Quên `flip` vẫn decode đúng.” | Buffer position/limit chưa ở trạng thái đọc. | `clear` trước nhận, `flip` trước xử lý. |
| “Buffer nhỏ thì lần receive sau đọc phần còn lại.” | UDP datagram có ranh giới; phần dư có thể bị loại. | Cấp buffer đúng kích thước protocol. |
| “send trả số byte nghĩa remote chắc chắn nhận.” | UDP không có acknowledgment. | Có cơ chế app-level ack/retry khi cần. |
| “connect UDP là TCP handshake.” | UDP connect chỉ thiết lập peer mặc định/filter. | Không tự bảo đảm delivery hay xác thực peer. |
| “Đăng ký `OP_WRITE` mọi lúc sẽ tốt hơn.” | Có thể luôn writable, tạo busy loop. | Theo dõi writability chỉ khi thực sự cần. |
| “NIO luôn nhanh hơn DatagramSocket.” | Performance phụ thuộc tải và thiết kế. | Đo workload thật, chọn mức phức tạp hợp lý. |
| “DatagramSocket đã bị deprecated trong Java 15.” | API vẫn hợp lệ và có cải tiến triển khai nền trong JDK 15. | Chọn API theo nhu cầu, không dựa trên quan niệm lỗi thời. |

## 14. Bài tập nhỏ

**Bài 1.** Một chương trình gọi `DatagramChannel.open()` rồi ngay lập tức `receive(buffer)` khi chưa có datagram. Điều gì có thể xảy ra?

**Đáp án:** Channel mặc định blocking; thread có thể **chờ** cho tới khi nhận datagram, channel đóng hoặc có lỗi. Không mặc định trả `null`.

**Bài 2.** Sau `configureBlocking(false)`, `receive(buffer)` trả `null`. Có phải server UDP đã mất kết nối?

**Đáp án:** Không. Lúc đó chưa có datagram khả dụng; UDP không có “peer EOF” như TCP. Có thể nhận sau khi có readiness.

**Bài 3.** Sự khác nhau giữa `setSoTimeout(1000)` và `configureBlocking(false)`?

**Đáp án:** Timeout làm blocking receive **chờ tối đa khoảng 1 giây**; non-blocking receive **không chờ** nếu chưa có dữ liệu, thường trả `null`.

**Bài 4.** Vì sao `selector.select(1000)` có thể chờ dù channel non-blocking?

**Đáp án:** Selector là cơ chế chờ **readiness**, còn non-blocking mode áp dụng cho thao tác I/O channel. Chờ tập trung giúp tránh bận CPU.

**Bài 5.** Một datagram UDP 2.000 bytes đến `ByteBuffer.allocate(128)`. Có thể gọi `receive` tiếp để đọc 1.872 bytes còn lại không?

**Đáp án:** Không. Ranh giới datagram được xử lý trong một lần nhận; phần không vừa buffer có thể bị bỏ. Cần buffer đủ lớn hoặc thay đổi protocol.

**Bài 6.** Chương trình theo dõi 40 UDP socket có nên tạo 40 blocking threads hay một selector?

**Đáp án:** Không có đáp án cố định. Một selector thường có lợi khi multiplex nhiều channel với ít thread, nhưng blocking receiver threads vẫn có thể phù hợp tùy workload. Cần đo hiệu năng, vận hành và độ phức tạp.

**Bài 7.** Một thread event loop nhận packet rồi truy vấn database mất 200 ms ngay tại chỗ. Có ảnh hưởng gì?

**Đáp án:** Trong 200 ms đó event loop có thể không xử lý các channel khác. Nên chuyển xử lý chậm sang worker pool, có queue giới hạn và copy payload trước khi tái sử dụng buffer.

## 15. Ghi nhớ

- **UDP là datagram transport; blocking/non-blocking là chế độ của API I/O.**
- **`DatagramSocket.receive` chặn luồng khi chờ datagram.** `setSoTimeout` chỉ đặt thời hạn chờ, không chuyển sang non-blocking.
- **`DatagramChannel` mặc định chặn.** Gọi `configureBlocking(false)` để `receive` trả `null` khi chưa có packet.
- **`Selector` cho phép multiplex nhiều non-blocking channels.** `select` có thể chờ readiness, không mâu thuẫn với non-blocking receive.
- **Dùng `ByteBuffer.clear` và `flip` đúng;** một datagram không được đọc thành stream qua nhiều receive.
- **Không busy-spin `receive==null`, không luôn đăng ký `OP_WRITE` và không làm việc nặng trên event-loop thread.**
- **Không có API nào làm UDP trở thành TCP:** delivery, ordering, duplicates, auth và retry là vấn đề riêng.
- **`DatagramSocket` vẫn hiện hành trong Java 15+**; chọn blocking hay non-blocking theo nhu cầu, đo đạc và độ phức tạp ứng dụng.

### Tài liệu chính thức và tiêu chuẩn còn áp dụng

- [Oracle Java 15 – DatagramSocket](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramSocket.html): `receive`, `setSoTimeout`, và hành vi socket UDP.
- [Oracle Java 15 – DatagramPacket](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/net/DatagramPacket.html): ranh giới packet, length và địa chỉ nguồn/đích.
- [Oracle Java 15 – DatagramChannel](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/nio/channels/DatagramChannel.html): blocking/non-blocking, `receive`/`send`, `bind` và `connect`.
- [Oracle Java 25 – DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): API NIO hiện đại và ngữ nghĩa channel.
- [Oracle Java 25 – Selector](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectNow` và selected-key set.
- [Oracle Java 25 – SelectionKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`/`OP_WRITE` và trạng thái interest/ready ops.
- [Oracle Java 25 – ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): buffer position/limit, `clear`, `flip`.
- [OpenJDK JEP 373 – Reimplement the Legacy DatagramSocket API](https://openjdk.org/jeps/373): cải tiến implementation của DatagramSocket trong Java 15, không phải tuyên bố API không còn dùng được.
- [RFC 768 – User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): mô hình UDP datagram.
