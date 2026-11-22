# DatagramSocket kết hợp DatagramChannel — điều khiển UDP trong Java 15

> **Mục tiêu:** Hiểu cách kết hợp API UDP dạng `java.net.DatagramSocket`/`DatagramPacket` với NIO `java.nio.channels.DatagramChannel`/`ByteBuffer` trên **cùng endpoint**; biết tạo `DatagramSocket` view qua `DatagramChannel.socket()`, khi nào `DatagramSocket.getChannel()` trả `null`, quy tắc blocking/non-blocking, `Selector`, `bind`/`connect`, timeout, vòng đời `close` và lỗi thường gặp. Bài tập trung vào những API **vẫn áp dụng trên Java hiện đại**. Java 15 có **JEP 373 — Reimplement the Legacy DatagramSocket API**: đây là thay đổi triển khai bên trong JDK, **không phải lời khuyên sử dụng API triển khai cũ hoặc cho rằng `DatagramSocket` đã bị deprecated**. Các ví dụ dùng Java 17+ đã biên dịch và chạy thực tế.

## 1. Nắm đúng hai giao diện truy cập UDP

UDP (User Datagram Protocol) vận chuyển **các datagram độc lập**. Một datagram mang một chuỗi bytes và địa chỉ đích; các gói có thể bị mất, đến sai thứ tự, trùng lặp hoặc bị từ chối bởi mạng. **`send` thành công không phải bằng chứng phía nhận đã xử lý gói**. Không có dòng byte TCP liên tục, không có bắt tay kết nối TCP và không có tính tin cậy được `DatagramSocket` hay `DatagramChannel` tự bảo đảm.

Java có hai cách lập trình UDP chính:

- **`DatagramSocket` + `DatagramPacket` (`java.net`):** mô hình thao tác **blocking** với packet chứa byte array, offset/length và địa chỉ. Gọi `socket.send(packet)`, `socket.receive(packet)`, `socket.setSoTimeout(ms)`. Phù hợp code đơn giản hoặc tích hợp code dùng `DatagramPacket`.
- **`DatagramChannel` + `ByteBuffer` (`java.nio.channels`):** mô hình **channel**, có `send(src, target)`, `receive(dst)` và `connect`/`read`/`write`. Có thể **configureBlocking(false)** và đăng ký với `Selector` để xử lý nhiều kênh trong vòng lặp sự kiện.

`DatagramChannel` có từ Java 1.4; cả hai API vẫn được JDK hiện đại hỗ trợ. Java 15 mang tới **JEP 373**, thay đổi cách JDK triển khai các API DatagramSocket/MulticastSocket bên dưới để dễ bảo trì và phát triển, **không đổi nguyên tắc sử dụng**. Không phải mỗi `DatagramSocket` mới đều có một public `DatagramChannel` mà lập trình viên có thể lấy ra.

## 2. Cách kết hợp đúng: tạo channel trước, lấy socket view sau

Cách chuẩn:

~~~java
try (DatagramChannel channel = DatagramChannel.open()) {
    DatagramSocket socketView = channel.socket();
    System.out.println(socketView.getChannel() == channel); // true
}
~~~

Đây là **đoạn mã minh họa nằm trong một phương thức** có import `java.nio.channels.DatagramChannel` và `java.net.DatagramSocket`, khai báo hoặc xử lý `IOException`.

**Quan hệ chính xác:**

- `DatagramChannel.open()` mở một channel. `channel.socket()` trả về **`DatagramSocket` duy nhất gắn với channel**.
- `socketView.getChannel() == channel` là `true`: hai object **là hai giao diện cho cùng underlying UDP socket**, không phải hai endpoint mới trên hai cổng khác nhau.
- Một `DatagramSocket` tạo độc lập với `new DatagramSocket(...)` **không tự có channel**. `ordinary.getChannel()` thường trả **`null`** theo hợp đồng API; không có phương thức chuẩn “bọc một ordinary DatagramSocket bất kỳ thành DatagramChannel”.
- Muốn dùng đồng thời NIO channel và cách thao tác packet trên **cùng socket**, hãy **khởi tạo qua `DatagramChannel.open()`** rồi lấy `socket()`.
- `DatagramSocket` view và `DatagramChannel` chia sẻ **địa chỉ/cổng bind, trạng thái kết nối và vòng đời đóng**. Không nên xem chúng là hai bản sao độc lập.

Ví dụ đối chiếu:

~~~java
try (DatagramSocket ordinary = new DatagramSocket();
     DatagramChannel channel = DatagramChannel.open()) {

    DatagramSocket view = channel.socket();
    System.out.println(ordinary.getChannel() == null); // true
    System.out.println(view.getChannel() == channel);   // true
}
~~~

Đây là code trong method. `new DatagramSocket()` có thể tự bind vào cổng local; `DatagramChannel.open()` ban đầu chưa bind, chỉ được bind theo yêu cầu. Nếu muốn kiểm soát chính xác địa chỉ/cổng, sử dụng `bind(...)` tường minh trước khi nhận.

### Luồng đối tượng

~~~text
DatagramChannel.open()
        |
        | channel.socket()
        v
   DatagramSocket view
        |
        +---------------------------+
        | Cùng underlying UDP socket|
        | Cùng địa chỉ/cổng local   |
        | Cùng peer nếu connected   |
        | Cùng vòng đời đóng        |
        +---------------------------+
         ^                      ^
         |                      |
channel.receive(ByteBuffer)   socketView.receive(DatagramPacket)
channel.send(ByteBuffer, to)  socketView.send(DatagramPacket)
~~~

**Không đọc cùng lúc từ hai view nếu bạn cần định tuyến packet một cách xác định.** Cả hai hướng nhận có thể cạnh tranh lấy **cùng hàng đợi datagrams**; một gói nhận qua channel sẽ không tiếp tục xuất hiện lần nữa qua socket view.

## 3. So sánh các phương thức quan trọng

| Mục tiêu | `DatagramSocket` view | `DatagramChannel` |
| --- | --- | --- |
| Tạo endpoint có hai giao diện | Dùng `channel.socket()` | `DatagramChannel.open()` |
| Bind địa chỉ/cổng | `socket.bind(local)` | `channel.bind(local)` |
| Xem cổng local | `socket.getLocalPort()` | `((InetSocketAddress) channel.getLocalAddress()).getPort()` |
| Gửi không cần connect | `socket.send(DatagramPacket)` | `channel.send(ByteBuffer, target)` |
| Nhận không cần connect | `socket.receive(DatagramPacket)` | `channel.receive(ByteBuffer)` |
| Gửi khi connected | `socket.send(packet)` với target phù hợp | `channel.write(buffer)` hoặc `send(...)` |
| Nhận khi connected | `socket.receive(packet)` | `channel.read(buffer)` hoặc `receive(buffer)` |
| Connected peer | `socket.connect(remote)`/`disconnect()` | `channel.connect(remote)`/`disconnect()` |
| Timeout blocking receive | `socket.setSoTimeout(ms)` cho `socket.receive` | Không áp dụng trực tiếp cho `channel.receive`; thiết kế timeout qua `Selector`/deadline |
| Non-blocking | **Không có chế độ send/receive non-blocking trên adapter `DatagramSocket`** | `channel.configureBlocking(false)` |
| Kết hợp `Selector` | Không register socket view | `channel.register(selector, OP_READ)` khi non-blocking |
| Buffer dữ liệu | `byte[]` chứa trong `DatagramPacket` | `ByteBuffer` với `position/limit` |
| Giải phóng | `socket.close()` | `channel.close()` |

**Lưu ý về `read`/`write`:** Khác với `receive`/`send`, `DatagramChannel.read` và `write` chỉ hoạt động khi channel **đã connected**. Trên channel chưa connected, `read` có thể ném `NotYetConnectedException`; `write` cũng yêu cầu peer hợp lệ.

## 4. Bind địa chỉ và sử dụng cổng UDP

Một endpoint chỉ nhận packet trên địa chỉ/cổng local tương ứng. Ví dụ IPv4 loopback:

~~~java
InetAddress ip = InetAddress.getByName("127.0.0.1");
try (DatagramChannel channel =
             DatagramChannel.open(StandardProtocolFamily.INET)) {
    channel.bind(new InetSocketAddress(ip, 0));
    DatagramSocket socket = channel.socket();

    int assignedPort = socket.getLocalPort();
    int channelPort =
            ((InetSocketAddress) channel.getLocalAddress()).getPort();

    System.out.println(assignedPort == channelPort); // true
}
~~~

Đây là code minh họa trong method, cần import `java.net` và `java.nio.channels`.

- `127.0.0.1` là địa chỉ **IPv4 loopback**: gói chỉ đi trong máy tính.
- `StandardProtocolFamily.INET` yêu cầu family IPv4; ví dụ sử dụng literal IPv4 nhất quán để tránh nhầm với loopback IPv6.
- Cổng `0` khi bind có nghĩa **để hệ điều hành chọn một cổng còn trống**, không phải “địa chỉ đích cổng 0”.
- `channel.bind(...)` và `socket.bind(...)` là hai cách bind **cùng underlying endpoint**. **Không bind hai lần** như đang cấu hình hai socket độc lập.
- Trong hệ thống thật, nếu server cần cổng cố định, chọn cổng và địa chỉ local theo yêu cầu triển khai; test nên dùng cổng `0` để tránh xung đột với ứng dụng khác.

**Không hardcode cổng số 12345 trong test** rồi kỳ vọng lúc nào cũng trống. Lấy cổng được hệ điều hành cấp bằng `getLocalSocketAddress()` hoặc `getLocalPort()` để gửi thử nghiệm.

## 5. Gửi và nhận: mỗi lần là một datagram riêng

### Dùng `DatagramSocket`

~~~java
byte[] payload = "hello".getBytes(StandardCharsets.UTF_8);
DatagramPacket outbound =
        new DatagramPacket(payload, payload.length, targetAddress);
socket.send(outbound);
~~~

`targetAddress` là `SocketAddress` đã có, chẳng hạn `InetSocketAddress` của phía nhận. Đây là code trong method với socket đã bind, không phải chương trình độc lập.

Nhận:

~~~java
byte[] storage = new byte[1024];
DatagramPacket inbound =
        new DatagramPacket(storage, storage.length);
socket.receive(inbound);

String text = new String(inbound.getData(), inbound.getOffset(),
        inbound.getLength(), StandardCharsets.UTF_8);
SocketAddress sender = inbound.getSocketAddress();
~~~

**Dùng `inbound.getLength()`**, không đọc toàn bộ `storage.length`: những bytes nằm ngoài độ dài datagram nhận được **không phải nội dung thông điệp**. `getOffset()` cũng quan trọng khi packet dùng một vùng con của array.

### Dùng `DatagramChannel`

~~~java
ByteBuffer outgoing =
        ByteBuffer.wrap("hello".getBytes(StandardCharsets.UTF_8));
int bytesSent = channel.send(outgoing, targetAddress);

ByteBuffer incoming = ByteBuffer.allocate(1024);
SocketAddress from = channel.receive(incoming);
if (from != null) {
    incoming.flip();
    String message = StandardCharsets.UTF_8.decode(incoming).toString();
}
~~~

`send(ByteBuffer,target)` truyền **phần remaining** từ `position` tới `limit`. Sau khi nhận, `ByteBuffer.position()` trỏ sau bytes đã ghi, nên phải `flip()` trước khi decode/đọc. Nếu channel ở **non-blocking mode** và chưa có gói, `receive` có thể trả `null`; **không `flip` hoặc xử lý message khi không có sender**.

### Hai view nhận luân phiên có được không?

**Được** nếu bạn điều phối rõ ràng. Ví dụ ở mục 7:

1. Ordinary `DatagramSocket` gửi một gói tới endpoint của channel; nhận bằng `channel.receive`.
2. Channel gửi gói trả lại ordinary socket; nhận bằng `plain.receive`.
3. Ordinary gửi thêm một gói; nhận bằng **`channel.socket().receive`**.

Ba bước đều hợp lệ vì **không có hai reader tranh gói cùng lúc**. Nhưng đây **không phải ba cổng UDP**: channel và socket view trên cùng endpoint chia sẻ một hàng đợi nhận.

## 6. Quy tắc blocking/non-blocking khi ghép hai API

Đây là điểm quan trọng nhất khi thêm `Selector` vào hệ thống đang dùng `DatagramSocket`.

### Khi channel đang blocking

`DatagramChannel.open()` mặc định ở **blocking mode**. Khi đó, `socketView.send(packet)` và `socketView.receive(packet)` được phép hoạt động như các thao tác blocking của `DatagramSocket`. Một lời gọi `socketView.receive` có thể chờ tới khi có datagram hoặc timeout đã cấu hình hết hạn.

### Khi channel đang non-blocking

~~~java
channel.configureBlocking(false);
~~~

Với `DatagramSocket` view **gắn với channel đó**, gọi:

~~~java
socketView.receive(packet);
socketView.send(packet);
~~~

sẽ ném **`IllegalBlockingModeException`** theo Javadoc. **Không** có việc `DatagramSocket.receive` trên view tự biến thành thao tác non-blocking và trả `null`. Muốn non-blocking, hãy gọi **`channel.receive(ByteBuffer)`** hoặc dùng `Selector`.

| Trạng thái channel | `socketView.receive(DatagramPacket)` | `channel.receive(ByteBuffer)` |
| --- | --- | --- |
| Blocking | Blocking; `setSoTimeout` có thể giới hạn thời gian của socket receive | Blocking tới khi có gói (không dùng `setSoTimeout` để điều khiển lời gọi channel) |
| Non-blocking | **`IllegalBlockingModeException`** | Trả sender khi có gói; trả **`null`** nếu chưa có gói |

Tương tự, `socketView.send` không hợp lệ khi channel non-blocking; `channel.send` là API cần dùng, có thể báo số bytes sent hoặc `0` khi chưa gửi được ở non-blocking mode.

**Khi nào khôi phục blocking?**

~~~java
channel.configureBlocking(true);
~~~

Chỉ làm vậy sau khi **không còn đăng ký hợp lệ với `Selector`**. Nếu channel vẫn được đăng ký bằng valid `SelectionKey`, lời gọi bật blocking có thể ném `IllegalBlockingModeException`. Trong chương trình mục 7, key được `cancel` và selector được xử lý để hoàn tất hủy đăng ký trước khi bật blocking trở lại.

## 7. Chương trình Java 17+ hoàn chỉnh: ghép Socket, Channel và Selector

Tạo một file **DatagramInteropDemo.java**. Chương trình dùng **IPv4 loopback**, cổng tự chọn và thứ tự gửi/nhận tuần tự để tránh đua gói; có `setSoTimeout` cho hai socket khi dùng blocking receive. Test có `Selector`, `connect`, `disconnect`, `ByteBuffer`, cách xử lý lỗi non-blocking và `close` từ cả hai phía.

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.IllegalBlockingModeException;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;

public class DatagramInteropDemo {
    private static byte[] bytes(String s) {
        return s.getBytes(StandardCharsets.UTF_8);
    }

    private static String read(ByteBuffer b) {
        b.flip();
        return StandardCharsets.UTF_8.decode(b).toString();
    }

    private static void send(
            DatagramSocket s, String text, SocketAddress destination)
            throws Exception {
        byte[] payload = bytes(text);
        s.send(new DatagramPacket(
                payload, payload.length, destination));
    }

    private static String receive(DatagramSocket s) throws Exception {
        byte[] payload = new byte[128];
        DatagramPacket received =
                new DatagramPacket(payload, payload.length);
        s.receive(received);
        return new String(received.getData(), received.getOffset(),
                received.getLength(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");

        try (DatagramSocket plain =
                     new DatagramSocket(new InetSocketAddress(loopback, 0));
             DatagramChannel channel =
                     DatagramChannel.open(StandardProtocolFamily.INET)) {
            plain.setSoTimeout(2000);
            channel.bind(new InetSocketAddress(loopback, 0));

            DatagramSocket view = channel.socket();
            view.setSoTimeout(2000);

            System.out.println("ordinaryHasNoChannel="
                    + (plain.getChannel() == null));
            System.out.println("viewReturnsSameChannel="
                    + (view.getChannel() == channel));
            System.out.println("sharedLocalPort="
                    + (view.getLocalPort() ==
                        ((InetSocketAddress) channel.getLocalAddress()).getPort()));
            System.out.println("initialBlocking=" + channel.isBlocking());

            send(plain, "socket-to-channel", view.getLocalSocketAddress());
            ByteBuffer channelInput = ByteBuffer.allocate(128);
            SocketAddress source = channel.receive(channelInput);
            System.out.println("fromPlain=" + read(channelInput));
            System.out.println("sourceMatchesPlain="
                    + source.equals(plain.getLocalSocketAddress()));

            channel.send(ByteBuffer.wrap(bytes("channel-to-socket")),
                    plain.getLocalSocketAddress());
            System.out.println("fromChannel=" + receive(plain));

            send(plain, "socket-adapter-receive",
                    view.getLocalSocketAddress());
            System.out.println("viaSocketView=" + receive(view));

            view.connect(plain.getLocalSocketAddress());
            System.out.println("connectedOnChannel="
                    + channel.isConnected());
            channel.write(ByteBuffer.wrap(bytes("connected-write")));
            System.out.println("connectedWrite=" + receive(plain));

            send(plain, "connected-read", view.getLocalSocketAddress());
            ByteBuffer connectedInput = ByteBuffer.allocate(128);
            int n = channel.read(connectedInput);
            System.out.println("connectedReadBytes=" + n);
            System.out.println("connectedRead=" + read(connectedInput));

            view.disconnect();
            System.out.println("disconnectedOnChannel="
                    + !channel.isConnected());

            view.setSoTimeout(100);
            try {
                receive(view);
                System.out.println("socketTimeout=UNEXPECTED");
            } catch (SocketTimeoutException expected) {
                System.out.println("socketTimeout=SocketTimeoutException");
            }

            channel.configureBlocking(false);
            try {
                receive(view);
                System.out.println("nonBlockingViewReceive=UNEXPECTED");
            } catch (IllegalBlockingModeException expected) {
                System.out.println(
                        "nonBlockingViewReceive=IllegalBlockingModeException");
            }

            try {
                send(view, "no-send", plain.getLocalSocketAddress());
                System.out.println("nonBlockingViewSend=UNEXPECTED");
            } catch (IllegalBlockingModeException expected) {
                System.out.println(
                        "nonBlockingViewSend=IllegalBlockingModeException");
            }

            System.out.println("nonBlockingEmpty="
                    + (channel.receive(ByteBuffer.allocate(32)) == null));

            try (Selector selector = Selector.open()) {
                SelectionKey key =
                        channel.register(selector, SelectionKey.OP_READ);
                send(plain, "selector-data", view.getLocalSocketAddress());

                int selected = selector.select(2000);
                System.out.println("selectorReadable="
                        + (selected > 0
                        && selector.selectedKeys().stream()
                                .anyMatch(k -> k.isReadable())));

                selector.selectedKeys().clear();
                ByteBuffer selectorBuffer = ByteBuffer.allocate(128);
                SocketAddress sender = channel.receive(selectorBuffer);
                System.out.println("selectorMessage=" + read(selectorBuffer));
                System.out.println("selectorSenderKnown=" + (sender != null));

                key.cancel();
                selector.selectNow();
            }

            channel.configureBlocking(true);
            System.out.println("restoredBlocking=" + channel.isBlocking());
            view.close();
            System.out.println("closeViewClosesChannel=" + !channel.isOpen());
        }

        try (DatagramChannel secondary = DatagramChannel.open()) {
            DatagramSocket secondaryView = secondary.socket();
            secondary.close();
            System.out.println("closeChannelClosesView="
                    + secondaryView.isClosed());
        }
    }
}
~~~

Biên dịch và chạy ở thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 DatagramInteropDemo.java
java DatagramInteropDemo
~~~

**Stdout đã kiểm chứng trên máy thử với loopback IPv4 hoạt động:**

~~~text
ordinaryHasNoChannel=true
viewReturnsSameChannel=true
sharedLocalPort=true
initialBlocking=true
fromPlain=socket-to-channel
sourceMatchesPlain=true
fromChannel=channel-to-socket
viaSocketView=socket-adapter-receive
connectedOnChannel=true
connectedWrite=connected-write
connectedReadBytes=14
connectedRead=connected-read
disconnectedOnChannel=true
socketTimeout=SocketTimeoutException
nonBlockingViewReceive=IllegalBlockingModeException
nonBlockingViewSend=IllegalBlockingModeException
nonBlockingEmpty=true
selectorReadable=true
selectorMessage=selector-data
selectorSenderKnown=true
restoredBlocking=true
closeViewClosesChannel=true
closeChannelClosesView=true
~~~

**Ghi chú về tính tái lập:** Các cổng được chọn tự động, nên không in số cổng cố định. Những bước nhận gói phụ thuộc mạng loopback và lịch lập lịch hệ điều hành; trên môi trường cấm UDP hoặc bị firewall/container policy chặn, test có thể timeout. Chương trình xác minh hành vi đã chạy thực tế; **không có bảo đảm datagram luôn được giao trong mọi máy/môi trường**. Selector dùng timeout 2 giây để tránh chờ vô hạn trong tình huống không có gói.

## 8. Phân tích các đoạn quan trọng của chương trình

### `channel.socket()` không tạo một cổng UDP thứ hai

~~~java
DatagramSocket view = channel.socket();

boolean same = view.getChannel() == channel;
boolean samePort = view.getLocalPort() ==
        ((InetSocketAddress) channel.getLocalAddress()).getPort();
~~~

`same` và `samePort` là `true`. Nếu bạn thấy ordinary socket trả `getChannel()==null`, đó là **hành vi bình thường**, không phải lỗi Java 15 hoặc thiếu quyền NIO. Không có cách chính thống biến một `new DatagramSocket(...)` đã tạo trước thành `DatagramChannel` sở hữu chung bằng cách chỉ gọi một phương thức getter.

### Gửi qua một API, nhận qua API kia

~~~java
send(plain, "socket-to-channel", view.getLocalSocketAddress());
SocketAddress source = channel.receive(channelInput);
~~~

`plain` là endpoint **khác** nên có địa chỉ/cổng riêng; `view` và `channel` là **hai views của cùng endpoint còn lại**. Source address nhận được trùng `plain.getLocalSocketAddress()` trong ví dụ loopback, và `ByteBuffer.flip()` giúp đọc đúng payload.

Gói chiều ngược lại:

~~~java
channel.send(
        ByteBuffer.wrap(bytes("channel-to-socket")),
        plain.getLocalSocketAddress());
String reply = receive(plain);
~~~

Nhận bằng `plain`, không phải `view`; đây là mô hình client/server UDP thu gọn trong một process.

### Giao diện socket vẫn hoạt động khi channel blocking

~~~java
send(plain, "socket-adapter-receive",
        view.getLocalSocketAddress());
String message = receive(view);
~~~

`receive(view)` gọi `view.receive(DatagramPacket)`. Nó thành công vì channel đang **blocking** và gói đã đến trên endpoint chung. Không cần mở một `DatagramSocket` thứ hai cho adapter.

### Thay trạng thái kết nối bằng một view, quan sát ở view kia

~~~java
view.connect(plain.getLocalSocketAddress());
System.out.println(channel.isConnected()); // true

channel.write(ByteBuffer.wrap(bytes("connected-write")));
// ... plain nhận message ...
view.disconnect();
System.out.println(channel.isConnected()); // false
~~~

Đây là **một endpoint chung** nên `connect/disconnect` của socket view ảnh hưởng tới channel. Không nên vừa tự `connect` một view, vừa để thread khác `send` tùy ý qua view còn lại mà không có ownership rõ.

### Cả hai hướng đóng đều tác động cùng tài nguyên

~~~java
view.close();
System.out.println(!channel.isOpen()); // true
~~~

Và khi đóng channel:

~~~java
channel.close();
System.out.println(view.isClosed()); // true
~~~

Hãy dùng `try-with-resources` với một **đối tượng sở hữu tài nguyên chính** (thường là channel) và không giả định cần đóng hai socket độc lập. Đóng một view làm phía kia **không còn usable**; các thao tác I/O tiếp theo sẽ báo lỗi theo hợp đồng, không tự tạo endpoint mới.

## 9. `connect` của UDP không phải kết nối TCP

Một câu lệnh:

~~~java
channel.connect(remoteAddress);
~~~

không thực hiện TCP handshake. Với UDP, nó thiết lập **peer mặc định và giới hạn hướng gửi/nhận** trên endpoint. Những ảnh hưởng:

- `DatagramChannel.read(dst)` và `write(src)` cần channel đã connected, vì chúng **không truyền target/source address qua tham số**.
- `DatagramChannel.receive(dst)` và `send(src,target)` **không cần connected**. Khi đã connected, channel lọc địa chỉ peer theo hợp đồng.
- `DatagramSocket.connect(remote)` trên socket view làm `channel.isConnected()` thành true.
- `DatagramChannel.connect(remote)` cũng phản ánh trên `socketView.isConnected()`.
- Các datagrams đang chờ trước khi connect **có thể bị loại bỏ** theo Javadoc; đừng dựa vào queue cũ sau khi thay peer.
- Đã connected **không bảo đảm peer thật sự tồn tại**, không bảo đảm gói đã tới, không cung cấp retransmission/acknowledgement.
- `PortUnreachableException` có thể xảy ra trong một số tình huống ICMP/OS, nhưng **không được bảo đảm**. Không dùng nó như cơ chế liveness/health-check chính xác.

Nếu cần reliability, retry, ordering hoặc delivery acknowledgement, **đó là trách nhiệm của giao thức ứng dụng** (hoặc dùng một giao thức khác phù hợp), không phải cờ `isConnected()` của UDP.

## 10. `DatagramPacket`, `ByteBuffer` và giới hạn kích thước nhận

Ở phía socket:

~~~java
byte[] data = new byte[256];
DatagramPacket packet = new DatagramPacket(data, data.length);
socket.receive(packet);

int actualBytes = packet.getLength();
~~~

Nếu datagram thực tế dài hơn không gian nhận của packet, **phần dư bị cắt bỏ**, không “chờ nhận nửa sau” bằng lần `receive` tiếp. Nếu tái sử dụng một `DatagramPacket` cho nhiều lần nhận, hãy bảo đảm **length của packet phù hợp với dung lượng cần nhận**, vì `receive` cập nhật `length` thành độ dài vừa nhận.

Ở phía channel:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(256);
SocketAddress source = channel.receive(buffer);
if (source != null) {
    buffer.flip();
    // Chỉ buffer.remaining() bytes đã nhận là payload của datagram.
}
~~~

Nếu `ByteBuffer.remaining()` nhỏ hơn datagram, **phần còn lại bị loại bỏ im lặng**. `ByteBuffer.position()` được cập nhật sau khi nhận, và `flip()` đặt limit thành số bytes nhận được để đọc đúng.

### Ví dụ kiểm chứng cắt ngắn datagram

Tạo file độc lập **DatagramBoundariesDemo.java**:

~~~java
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.StandardProtocolFamily;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.channels.NotYetConnectedException;
import java.nio.charset.StandardCharsets;

public class DatagramBoundariesDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        try (DatagramChannel receiver =
                     DatagramChannel.open(StandardProtocolFamily.INET);
             DatagramSocket sender =
                     new DatagramSocket(new InetSocketAddress(loopback, 0))) {
            receiver.bind(new InetSocketAddress(loopback, 0));

            try {
                receiver.read(ByteBuffer.allocate(16));
                System.out.println("readBeforeConnect=UNEXPECTED");
            } catch (NotYetConnectedException expected) {
                System.out.println(
                        "readBeforeConnect=NotYetConnectedException");
            }

            byte[] full =
                    "abcdefgh".getBytes(StandardCharsets.UTF_8);
            sender.send(new DatagramPacket(
                    full, full.length, receiver.getLocalAddress()));

            ByteBuffer truncated = ByteBuffer.allocate(3);
            receiver.receive(truncated);
            System.out.println("shortBufferBytes=" + truncated.position());

            truncated.flip();
            System.out.println("shortBufferText="
                    + StandardCharsets.UTF_8.decode(truncated));

            receiver.configureBlocking(false);
            System.out.println("noSecondFragment="
                    + (receiver.receive(ByteBuffer.allocate(16)) == null));
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 DatagramBoundariesDemo.java
java DatagramBoundariesDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
readBeforeConnect=NotYetConnectedException
shortBufferBytes=3
shortBufferText=abc
noSecondFragment=true
~~~

Ví dụ gửi **8 bytes** `abcdefgh` nhưng buffer nhận chỉ có **3 bytes**, nên nhận `abc` và **không còn 5 bytes để nhận tiếp**. Trong thử nghiệm chỉ có một datagram được gửi, nên `receive` non-blocking sau đó trả `null`.

**Không suy luận sai:** `noSecondFragment=true` không chứng minh mạng UDP chưa bao giờ gửi thêm gói khác; nó chứng minh trong test cụ thể **phần dư của một datagram đã nhận không trở thành một datagram thứ hai**. Với mạng thực, vẫn cần xử lý packet mới có thể đến bất kỳ lúc nào.

## 11. Timeout của socket view không điều khiển timeout của channel

Với `DatagramSocket` view ở blocking mode:

~~~java
view.setSoTimeout(1000);
DatagramPacket packet = new DatagramPacket(new byte[512], 512);

try {
    view.receive(packet);
} catch (SocketTimeoutException timeout) {
    // Chưa có datagram trong thời gian chờ; socket vẫn còn dùng được.
}
~~~

`setSoTimeout(1000)` yêu cầu `DatagramSocket.receive` chờ tối đa khoảng 1.000 ms. `0` là chờ vô hạn theo API. Timeout nên được cấu hình **trước** lời gọi blocking receive.

**Không lấy `view.setSoTimeout(...)` rồi kết luận `channel.receive(ByteBuffer)` có cùng deadline**. Channel API có blocking/non-blocking riêng; nếu cần timeout có thể dùng:

1. `channel.configureBlocking(false)`.
2. `channel.register(selector, SelectionKey.OP_READ)`.
3. `selector.select(timeoutMs)`.
4. Khi readable, `channel.receive(buffer)` và xử lý `SocketAddress` trả về.
5. Hủy đăng ký/đóng selector khi hết vòng đời.

**Không được gọi `view.receive` trong vòng lặp selector** khi channel đã chuyển sang non-blocking: lời gọi đó ném `IllegalBlockingModeException`.

### Selector hoạt động thế nào?

~~~java
channel.configureBlocking(false);

try (Selector selector = Selector.open()) {
    SelectionKey key =
            channel.register(selector, SelectionKey.OP_READ);

    int selected = selector.select(2000);
    if (selected > 0) {
        for (SelectionKey ready : selector.selectedKeys()) {
            if (ready.isValid() && ready.isReadable()) {
                ByteBuffer dst = ByteBuffer.allocate(2048);
                SocketAddress sender = channel.receive(dst);
                if (sender != null) {
                    dst.flip();
                    // Xử lý một datagram, sau đó sẵn sàng nhận các gói tiếp theo.
                }
            }
        }
        selector.selectedKeys().clear();
    }

    key.cancel();
    selector.selectNow(); // Đẩy quá trình hủy đăng ký cho selector.
}
~~~

Đây là **mã minh họa đặt trong method**, không có code gửi gói; chương trình mục 7 mới là ví dụ đầy đủ có người gửi. `select(2000)` không bảo đảm có gói; trả `0` khi không có channel ready trước timeout.

**Cẩn thận trong event loop:** Sau khi nhận một gói, có thể còn các gói khác đang chờ. Một handler thường lặp `channel.receive(buffer)` đến khi trả `null` khi non-blocking, đồng thời đặt **giới hạn số packets/lượt** để không khiến một channel nhiều traffic làm đói các channel khác. Đừng có hai handler cùng đọc channel mà không có kế hoạch đồng bộ hóa.

## 12. Cấu hình socket options trên endpoint chung

Các options UDP như `SO_RCVBUF`, `SO_SNDBUF`, `SO_BROADCAST`, `SO_REUSEADDR` có thể được cấu hình bằng NIO:

~~~java
channel.setOption(
        java.net.StandardSocketOptions.SO_RCVBUF, 64 * 1024);
~~~

Hoặc qua view:

~~~java
view.setReceiveBufferSize(64 * 1024);
~~~

Hai API tác động vào **cùng underlying endpoint**. Nhưng buffer size là **hint/setting phụ thuộc hệ điều hành**; không được khẳng định giá trị đọc lại luôn đúng chính xác số đã yêu cầu. Với socket options, hệ điều hành có thể giới hạn hoặc điều chỉnh.

**Nguyên tắc:** Xác định rõ cấu hình được áp dụng **trước khi bind** nếu yêu cầu option cần thời điểm ấy, ví dụ `SO_REUSEADDR` trên một số hệ thống. Với code hiện đại, ưu tiên `channel.setOption` và `channel.supportedOptions` khi quản lý NIO; với code đã dùng `DatagramSocket` vẫn có thể dùng `view.setOption` hoặc các setter thông thường khi phù hợp.

**Không nhầm application receive buffer với OS socket receive buffer:**

- `ByteBuffer.allocate(n)` hoặc `DatagramPacket(new byte[n],n)`: **sức chứa từng datagram** ở tầng ứng dụng, quyết định khả năng bị cắt ngắn.
- `SO_RCVBUF`: **đệm UDP ở tầng hệ điều hành**, có thể ảnh hưởng khả năng chịu burst, không thay thế một ByteBuffer đủ lớn để chứa một datagram.

## 13. Xử lý lỗi và cách phục hồi có chủ đích

| Tình huống | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Ordinary `new DatagramSocket` rồi `getChannel()` | `null` | Nếu cần NIO, tạo lại endpoint qua `DatagramChannel.open()` |
| Dùng `socketView.send/receive` khi channel non-blocking | `IllegalBlockingModeException` | Dùng `channel.send/receive` hoặc khôi phục blocking sau khi hủy selector registration |
| Gọi `channel.read/write` chưa connected | `NotYetConnectedException` | Dùng `send/receive` hoặc `connect` trước |
| Bind trùng cổng/địa chỉ không được OS cho phép | `BindException` hoặc `SocketException/IOException` | Chọn cổng/địa chỉ phù hợp, không giả định `SO_REUSEADDR` giải quyết mọi OS |
| Không có packet khi blocking socket receive có timeout | `SocketTimeoutException` | Có thể thử lại theo policy; socket vẫn có thể dùng tiếp |
| Channel non-blocking receive nhưng chưa có packet | `receive(...) == null` | Chờ `Selector` hoặc xử lý vòng lặp, không đọc ByteBuffer như message hợp lệ |
| Buffer nhận nhỏ hơn datagram | Payload bị cắt ngắn | Thiết kế giới hạn kích thước hợp lý, framing/validation |
| Bên nhận hoặc mạng không sẵn sàng | Có thể mất gói, timeout, `PortUnreachableException` không chắc xuất hiện | Retry/ACK/application protocol hoặc chọn transport khác |
| Socket view bị `close` | Channel cũng bị đóng | Tạo endpoint mới nếu cần tiếp tục; không reuse view cũ |
| Channel bị `close` | Socket view cũng đóng | Ngừng dùng cả hai, cleanup selector/handlers |
| Thread đang blocked và bị interrupt/close | `ClosedByInterruptException`/`AsynchronousCloseException` hoặc I/O error tùy API | Xử lý cancellation, không giả định channel còn open |

**Không dùng `catch (Exception)` rồi bỏ qua lỗi mạng**. Phân loại timeout/retryable, closed endpoint, invalid mode, sai địa chỉ, overflow/format, và lỗi hệ điều hành. Với UDP, retry có thể sinh packet trùng và cần idempotency/key quản lý nếu giao thức yêu cầu.

## 14. Đồng thời: một endpoint, không phải hai đường đọc độc lập

`DatagramChannel` hỗ trợ thao tác đa luồng theo hợp đồng của channel, nhưng có **giới hạn đồng thời**: tối đa một thread thực hiện đọc tại một thời điểm và một thread thực hiện ghi tại một thời điểm. Điều này **không đồng nghĩa** mọi kiểu sử dụng `channel.receive` và `socketView.receive` đồng thời là an toàn về mặt **phân phối gói**.

Ví dụ thiết kế sai:

~~~text
Thread A: channel.receive(byteBuffer)
Thread B: socketView.receive(datagramPacket)

Cả hai đọc từ cùng UDP endpoint.
Packet 1 có thể được A lấy, Packet 2 có thể được B lấy.
Không có quy tắc API bảo đảm Packet 1 thuộc về A.
~~~

Nếu protocol có hai loại message, **không** dùng hai reader độc lập trên hai view để định tuyến bằng cách hy vọng mỗi reader sẽ tự nhận loại mong muốn. Hãy chọn **một owner nhận**, sau đó **parse/route** từng datagram sang queues/handlers tương ứng. Nếu cần non-blocking scalable server, thường chọn **một NIO receive loop** với `Selector` và queue xử lý.

**Sender cũng cần phối hợp:** Hai thread gửi đồng thời có thể mỗi thread gửi một datagram riêng, nhưng business ordering không được UDP bảo đảm. Không dùng “số lần `send` theo thứ tự” làm hợp đồng thứ tự đến.

## 15. UDP vẫn cần xác thực dữ liệu và giới hạn tải

`DatagramSocket`/`DatagramChannel` là transport API, **không tự mã hóa hay xác thực packet**. Trong ứng dụng nhận UDP từ mạng không đáng tin:

- Giới hạn datagram size theo protocol; dùng buffer đủ sức chứa payload tối đa của ứng dụng.
- Kiểm tra packet length, message header/version, field lengths, charset và encoding trước khi xử lý.
- Không tin ngay `sender SocketAddress` như bằng chứng danh tính: địa chỉ/port có thể không chứng minh một chủ thể đã được xác thực.
- Khi cần tính toàn vẹn/xác thực, dùng một giao thức bảo mật phù hợp (chẳng hạn DTLS trong kiến trúc có triển khai hỗ trợ) thay vì tự coi UDP connected là secure.
- Chống replay, rate-limit và resource exhaustion ở tầng ứng dụng.
- Không lưu thông tin nhạy cảm trong thông điệp UDP không mã hóa; phân biệt local-loopback demo với môi trường mạng thật.
- Không cố đọc phần dư của datagram bị cắt ngắn: packet đó đã được tiêu thụ, không thể khôi phục bằng receive thứ hai.
- Thiết kế ACK/retry/idempotency nếu cần delivery semantics cụ thể; tránh retry vô hạn gây tăng tải.

**Nội dung bài học không khuyến khích API nội bộ hoặc kỹ thuật thay socket implementation cũ.** JEP 373 là dấu mốc cải tiến JDK 15, không làm mất nhu cầu bảo đảm tính đúng đắn của ứng dụng khi chạy trên JVM hiện đại.

## 16. Khi nào chọn API nào?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Client UDP nhỏ, code thao tác packet đơn giản | `DatagramSocket` + `DatagramPacket` |
| Muốn cùng endpoint nhưng tận dụng code nhận/gửi packet hiện có | `DatagramChannel.open()` rồi `channel.socket()` ở blocking mode |
| Server xử lý nhiều UDP endpoints trong một event loop | `DatagramChannel` non-blocking + `Selector` |
| Muốn gửi/nhận `ByteBuffer`, dễ kết hợp NIO pipeline | `DatagramChannel` |
| Muốn `setSoTimeout` cho blocking receive kiểu packet | `DatagramSocket`/socket view khi channel blocking |
| Muốn deadline non-blocking cho channel | `Selector.select(timeout)` + state machine |
| Muốn đổi giữa channel và socket view theo từng pha | Chỉ khi quản lý rõ `configureBlocking`, selector registration và ownership |
| Đã có ordinary `DatagramSocket` và muốn tự động lấy channel | **Không có chuyển đổi trực tiếp**; thiết kế lại bước tạo endpoint |
| Muốn bảo đảm gói đến/đúng thứ tự | UDP APIs không đủ; thiết kế protocol hoặc chọn transport có đảm bảo phù hợp |

**Không phải càng nhiều API trên cùng endpoint thì càng tốt.** Nếu chỉ cần NIO, dùng `DatagramChannel` trực tiếp thường đơn giản hơn tạo socket view rồi quay lại channel. Socket view đặc biệt hữu ích khi **tích hợp với thư viện đang nhận `DatagramSocket`** nhưng endpoint được tạo và quản lý ở tầng NIO.

## 17. Các nhầm lẫn phổ biến cần tránh

1. **“`new DatagramSocket().getChannel()` luôn có channel từ Java 15.”** Sai: getter vẫn có thể trả `null`, kể cả sau JEP 373.
2. **“`channel.socket()` mở thêm một UDP port.”** Sai: nó trả view của **cùng endpoint**.
3. **“`DatagramSocket` đã bị xóa/deprecated vì JEP 373 có chữ legacy.”** Sai: JEP 373 cải tiến **implementation**; API DatagramSocket vẫn được hỗ trợ.
4. **“Có thể dùng `socket.receive` trên view sau `configureBlocking(false)`.”** Sai: `IllegalBlockingModeException`.
5. **“`socket.send` non-blocking sẽ tự gửi một phần packet.”** Sai: gọi socket API trên non-blocking channel là lỗi mode; dùng channel API.
6. **“`channel.receive` luôn chờ tới khi có gói.”** Sai: ở non-blocking mode có thể trả `null`.
7. **“`setSoTimeout` giới hạn `channel.receive`.”** Sai: nó áp dụng cho `DatagramSocket.receive`.
8. **“`channel.read` hoạt động trước `connect`.”** Sai: yêu cầu connected, nếu không ném `NotYetConnectedException`.
9. **“`UDP connect` có handshake và bảo đảm giao hàng.”** Sai: connect chọn/giới hạn peer; UDP vẫn unreliable.
10. **“`send` hoàn tất có nghĩa bên kia đã nhận.”** Sai: kết quả chỉ cho biết thao tác gửi local; không xác nhận delivery.
11. **“`DatagramPacket` có thể đọc toàn bộ buffer, bỏ qua `getLength`.”** Sai: chỉ bytes từ offset tới length là payload hợp lệ.
12. **“Buffer nhận nhỏ thì `receive` tiếp nhận phần còn lại của gói.”** Sai: phần dư datagram bị cắt bỏ.
13. **“`ByteBuffer` nhận xong đọc ngay mà không `flip`.”** Sai: phải chuyển từ mode ghi sang mode đọc.
14. **“`ByteBuffer` sau `send` vẫn ở position ban đầu.”** Không nên giả định; channel tiêu thụ `remaining` bytes và cập nhật position phù hợp.
15. **“`channel.register(selector, OP_READ)` khi channel blocking.”** Sai: phải chuyển non-blocking trước khi register.
16. **“Bật blocking lại khi vẫn còn valid selector key.”** Có thể ném `IllegalBlockingModeException`; hủy registration trước.
17. **“`view.close()` không ảnh hưởng channel.”** Sai: channel bị đóng cùng.
18. **“`channel.close()` không ảnh hưởng socket view.”** Sai: view cũng báo closed.
19. **“Hai readers trên cùng endpoint sẽ mỗi người nhận đúng loại message riêng.”** Sai: packet được tiêu thụ bởi reader lấy được trước; phải route ở tầng ứng dụng.
20. **“`PortUnreachableException` chắc chắn được ném nếu peer không chạy.”** Sai: phụ thuộc ICMP/OS, không có bảo đảm.
21. **“Không cần xử lý kích thước datagram hoặc input trust.”** Sai: UDP có thể bị mất, cắt, làm giả hoặc chứa payload không hợp lệ.
22. **“Dùng channel adapter là một cách nâng cấp UDP thành reliable.”** Sai: đây chỉ là **hai giao diện Java cho cùng UDP transport**.

## 18. Bài luyện tập và tiêu chí đạt

**Bài 1 — Hai view.** Mở `DatagramChannel`, lấy `channel.socket()` rồi so `getChannel()`. **Đạt** khi kết quả là cùng channel và cổng local trùng nhau.

**Bài 2 — Ordinary socket.** Tạo `new DatagramSocket(0)`, gọi `getChannel()`. **Đạt** khi biết nó trả `null` và giải thích không thể tự biến socket đã tồn tại thành channel bất kỳ.

**Bài 3 — Socket → Channel.** Dùng một ordinary socket gửi đến channel; nhận qua `ByteBuffer`. **Đạt** khi đọc đúng bytes bằng `flip` và nhận diện `SocketAddress` của sender.

**Bài 4 — Channel → Socket.** Gửi `ByteBuffer` qua `channel.send` đến ordinary socket. **Đạt** khi dùng `DatagramPacket.getOffset/getLength` để decode chính xác và không coi buffer thừa là payload.

**Bài 5 — Adapter receive.** Gửi packet thứ ba tới cùng channel endpoint và nhận qua `channel.socket().receive`. **Đạt** khi chứng minh channel và adapter chia sẻ một cổng, không tranh gói cùng lúc.

**Bài 6 — Connect.** Kết nối `socketView.connect(peer)` rồi xem `channel.isConnected()`, dùng `channel.write/read`, sau đó disconnect. **Đạt** khi nhận ra connect của UDP không có TCP handshake.

**Bài 7 — Blocking restriction.** Chuyển channel sang `configureBlocking(false)` rồi gọi `socketView.send/receive`. **Đạt** khi cả hai ném `IllegalBlockingModeException`; sau đó dùng channel API đúng cách.

**Bài 8 — Selector.** Đăng ký non-blocking channel với `SelectionKey.OP_READ` và `select(timeout)`. **Đạt** khi thấy readiness, gọi `channel.receive` rồi xử lý `null` hợp lệ.

**Bài 9 — Khôi phục blocking.** Hủy selector key/đóng selector trước khi gọi `configureBlocking(true)`. **Đạt** khi không còn `IllegalBlockingModeException` do channel đang registered.

**Bài 10 — Timeout.** Cấu hình `view.setSoTimeout(100)` khi blocking, chờ packet không có. **Đạt** khi bắt `SocketTimeoutException` và hiểu endpoint không bị đóng chỉ vì timeout.

**Bài 11 — Buffer quá nhỏ.** Gửi chuỗi `abcdefgh` (8 bytes) nhưng nhận bằng buffer 3 bytes. **Đạt** khi thu `abc`, không xem 5 bytes còn lại là datagram thứ hai.

**Bài 12 — Đóng view.** Đóng `socketView`, kiểm tra `channel.isOpen()`; thử làm ngược lại. **Đạt** khi hiểu cùng underlying resource và giải phóng đúng một owner.

**Bài 13 — Truyền gói không tin cậy.** Thiết kế header version/length, validate UTF-8, hạn mức payload và retry/idempotency. **Đạt** khi nêu rõ UDP không bảo đảm delivery, ordering, authenticity.

**Bài 14 — Concurrency.** Mô tả một event loop đọc gói rồi route tới handler, thay vì thread A đọc channel và thread B đọc socket view. **Đạt** khi giải thích tại sao hai reader không bảo đảm phân phối theo ý muốn.

## 19. Tài liệu chính thức còn áp dụng

- [JEP 373 — Reimplement the Legacy DatagramSocket API (JDK 15)](https://openjdk.org/jeps/373): thay đổi triển khai bên trong JDK 15, không phải cơ chế chuyển `DatagramSocket` bất kỳ thành channel.
- [Oracle Java SE 25 — DatagramSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramSocket.html): `getChannel()`, `send`, `receive`, `setSoTimeout`, `connect`/`disconnect`, `close` và `IllegalBlockingModeException`.
- [Oracle Java SE 25 — DatagramChannel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/DatagramChannel.html): `open`, `socket()`, `bind`, `send/receive`, `read/write`, non-blocking, buffer truncation, connected peer.
- [Oracle Java SE 25 — DatagramPacket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/DatagramPacket.html): cấu trúc packet, `getOffset()`, `getLength()` và việc đọc một datagram.
- [Oracle Java SE 25 — Selector](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/Selector.html) và [SelectionKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/channels/SelectionKey.html): non-blocking I/O, `OP_READ`, chọn readiness và hủy registration.
- [Oracle Java SE 25 — ByteBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining` và `flip`.
- [Oracle Java SE 25 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_RCVBUF`/`SO_SNDBUF`/`SO_REUSEADDR`/`SO_BROADCAST`.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): nền tảng UDP là các datagrams độc lập; không tự cung cấp reliability kiểu TCP.

**Ghi nhớ:** Muốn kết hợp `DatagramSocket` với `DatagramChannel` trên **cùng endpoint**, hãy **mở channel trước rồi gọi `channel.socket()`**. Ordinary `DatagramSocket` không tự có channel; **`getChannel() == null` là bình thường**. Socket view chỉ dùng `send/receive` khi channel **blocking**; muốn `Selector`/non-blocking phải dùng channel API. Cả hai view chia sẻ bind/connect/close và hàng đợi nhận, nên cần quản lý một owner I/O, kiểm soát `ByteBuffer`/packet lengths, timeout, cạnh tranh đọc và các giới hạn cố hữu của UDP.
