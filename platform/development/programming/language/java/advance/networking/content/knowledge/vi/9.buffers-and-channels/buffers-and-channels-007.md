# SocketChannel.connect(), finishConnect() và kết nối chưa hoàn tất trong Java NIO

Trong phần **Buffer và channel** của Java Networking, **java.nio.channels.SocketChannel** có một khác biệt rất quan trọng giữa **blocking** và **non-blocking** khi thiết lập TCP connection. Ở blocking mode, lời gọi **connect(remote)** đợi kết nối thành công hoặc thất bại. Ở non-blocking mode, lời gọi ấy có thể **khởi động** kết nối rồi trả **false** ngay: khi đó SocketChannel **chưa được coi là connected** theo hợp đồng Java, và không thể tự ý read/write. Ứng dụng cần dùng **finishConnect()**, thường sau sự kiện **SelectionKey.OP_CONNECT**, để xác nhận kết nối đã hoàn tất hoặc nhận lỗi.

Ba API cốt lõi là **connect(SocketAddress)**, **finishConnect()**, **isConnectionPending()**; hai phép kiểm tra liên quan là **isConnected()** và **isOpen()**. Chúng giải quyết các tình huống: kết nối hoàn tất tức thì, kết nối đang chờ, kết nối hoàn tất sau một hoặc nhiều vòng Selector, thất bại/timeout và quản lý tài nguyên.

Đây là kiến thức nền để xây dựng một **event-loop NIO** quản lý nhiều kết nối TCP mà không dành riêng một thread bị chặn cho mỗi thao tác connect. Bài này sử dụng Java 17+, có ví dụ runnable với localhost và cổng động, ví dụ lỗi trạng thái, giải thích timeout, ByteBuffer, partial I/O, cleanup và bài tập.

## 1. Mô hình trạng thái của SocketChannel

Một **SocketChannel.open()** mới được mở (**isOpen() == true**) nhưng **chưa connected**. Chế độ mặc định của channel là **blocking**. Muốn non-blocking connect thì cấu hình trước khi kết nối:

~~~java
SocketChannel channel = SocketChannel.open();
channel.configureBlocking(false);
boolean immediate = channel.connect(remoteAddress);
~~~

Đoạn trên chỉ minh họa API: giả sử **remoteAddress** là SocketAddress hợp lệ, có import và phải đóng channel khi hoàn thành. Biến **immediate** mang ý nghĩa “kết nối đã xong ngay trong connect()” chứ không có nghĩa “có lỗi hay không”.

~~~text
OPEN / UNCONNECTED
       |
       | configureBlocking(false)
       | connect(remoteAddress)
       |
       +---- true -----------------------> CONNECTED
       |                                   isConnected() = true
       |                                   isConnectionPending() = false
       |
       +---- false ---> CONNECTION_PENDING
                           isConnected() = false
                           isConnectionPending() = true
                                     |
                                     | đợi OP_CONNECT
                                     | finishConnect()
                                     |
                         +-----------+------------+
                         |           |            |
                        false       true       IOException
                         |           |            |
                      PENDING     CONNECTED    FAILED/CLOSED
~~~

Khi connect non-blocking trả **false**, kernel đã nhận yêu cầu bắt đầu kết nối, nhưng ứng dụng phải hoàn tất trạng thái qua **finishConnect()**. Ngay cả khi TCP handshake trên máy đã có kết quả, **isConnectionPending()** vẫn biểu diễn tiến trình chưa được hoàn thành theo API Java cho đến khi finishConnect giải quyết nó. Không được coi “TCP có vẻ sẵn sàng” là đủ để read/write.

**Connect trả true ngay là trường hợp bình thường**, nhất là localhost. Do đó code đúng bắt buộc có cả nhánh true và false; không được giả định non-blocking connect luôn phát sinh một sự kiện OP_CONNECT sau đó.

## 2. Hợp đồng của từng phương thức

| Phương thức | Khi dùng với non-blocking SocketChannel | Ghi nhớ |
|---|---|---|
| **connect(remote)** | Trả true nếu hoàn tất ngay, false nếu còn đang kết nối; có thể ném exception | false là pending, không phải kết nối thất bại |
| **finishConnect()** | Trả true nếu hoàn tất; false nếu chưa hoàn tất; IOException nếu lỗi | Chỉ sau true mới sang trạng thái I/O |
| **isConnectionPending()** | True nếu đã khởi động connect nhưng chưa hoàn tất bằng finishConnect | Không phải lệnh đợi; chỉ quan sát |
| **isConnected()** | True khi channel đang mở và connected | Không thay thế kiểm tra lỗi I/O tương lai |
| **isOpen()** | True nếu chưa close | Không chứng minh đã connected |
| **configureBlocking(false)** | Cho phép connect không chặn và đăng ký Selector | Phải thực hiện trước register/select và connect |

### connect trong blocking mode

Theo Javadoc Java 17, **SocketChannel.connect(remote)** ở blocking mode đợi tới khi connection thành công hoặc xảy ra lỗi I/O. Một lần connect thành công sẽ trả **true**. Nếu bạn muốn xử lý nhiều kết nối trong một event loop, không để SocketChannel ở blocking mode rồi gọi connect trong event-loop thread.

### connect trong non-blocking mode

~~~java
channel.configureBlocking(false);
if (channel.connect(remote)) {
    // CONNECTED ngay: chuyển trực tiếp tới I/O thích hợp.
} else {
    // CONNECTION_PENDING: chờ và dùng finishConnect().
}
~~~

**connect(false) không phải ConnectException.** Nếu server từ chối hoặc mạng lỗi, Java có thể ném **IOException** ngay tại connect hoặc báo lỗi sau qua finishConnect. Không có quy tắc rằng mọi lỗi đều xuất hiện ở bước nào nhất định.

### finishConnect có ba đường chính

1. **true:** kết nối hoàn tất. Nếu channel đã connected, gọi finishConnect cũng trả true ngay.
2. **false:** kết nối non-blocking vẫn pending; đợi tiếp, không được read/write.
3. **IOException:** kết nối thất bại, ví dụ remote từ chối hoặc lỗi mạng. Theo hợp đồng Java 17, một connection attempt thất bại qua checked exception làm **channel đóng**; dọn registration/state và tạo channel mới khi retry.

**NoConnectionPendingException** xuất hiện khi gọi finishConnect ở channel chưa connected và chưa từng bắt đầu kết nối. Đây là lỗi sai thứ tự thao tác. Gọi **connect()** lần hai trong lúc pending ném **ConnectionPendingException**; gọi lại connect trên channel đã connected ném **AlreadyConnectedException**.

## 3. Không nhầm open, connected và pending

| Thời điểm | isOpen | isConnected | isConnectionPending | Bước tiếp |
|---|---:|---:|---:|---|
| SocketChannel.open() vừa trả về | true | false | false | configure mode, connect |
| connect(false) | true | false | true | chờ OP_CONNECT/finishConnect |
| finishConnect(false) | true | false | true | tiếp tục chờ |
| connect(true) | true | true | false | read/write theo protocol |
| finishConnect(true) | true | true | false | đổi interest ops rồi I/O |
| connect attempt ném checked exception báo thất bại | false theo hợp đồng | false | false | cleanup, mở channel mới nếu cần |
| close() đã được gọi | false | false | false | không tái sử dụng |

**isConnectionPending() == false không đủ để kết luận kết nối đã thành công.** Nó cũng false trên channel mới chưa connect và channel đã đóng. Phải kết hợp **isConnected()** và state của ứng dụng.

**SocketChannel.isConnected() khác java.net.Socket.isConnected():** theo tài liệu Java 17, SocketChannel.isConnected() trả true chỉ khi channel vẫn **open và connected**. Socket.isConnected() của API cổ điển có thể vẫn true sau close vì phản ánh lịch sử từng kết nối. Khi làm việc với NIO, dựa trên trạng thái SocketChannel và kết quả I/O của chính nó, không trộn hai phương thức.

**Không thể dùng isConnectionPending như vòng chờ:** while(isConnectionPending()) liên tục sẽ gây busy-spin; trạng thái còn cần được hoàn tất bằng finishConnect. Hãy dùng Selector hoặc cơ chế đợi có deadline.

## 4. Chờ OP_CONNECT bằng Selector

**Selector** theo dõi trạng thái sẵn sàng của nhiều **SelectableChannel**, trong đó SocketChannel dùng các cờ **OP_CONNECT**, **OP_READ** và **OP_WRITE**. Channel đăng ký với Selector phải ở non-blocking mode.

Quy trình đúng:

1. Mở **SocketChannel** và **Selector**; chuyển channel sang non-blocking.
2. Gọi **connect(remote)**. Nếu trả true, đăng ký **OP_READ**/**OP_WRITE** theo bước tiếp theo của ứng dụng, **không cần OP_CONNECT**.
3. Nếu connect trả false, **register(selector, SelectionKey.OP_CONNECT)**.
4. Event loop gọi **selector.select(timeout)** và duyệt **selectedKeys()**.
5. Khi **key.isConnectable()**, gọi **channel.finishConnect()**:
   - true: channel connected, đổi **interestOps** sang OP_READ/OP_WRITE nếu cần.
   - false: tiếp tục quan tâm OP_CONNECT, đợi vòng tiếp.
   - IOException: đóng channel, hủy key, dọn state và thông báo lỗi.
6. Sau khi xử lý selected key, gọi **iterator.remove()** để không giữ thông báo cũ.
7. Nếu quá **connection deadline**, close channel và dọn registration.

~~~text
non-blocking connect(remote)
  |
  +-- true --> CONNECTED --> interestOps(OP_READ hoặc OP_WRITE)
  |
  +-- false -> register(OP_CONNECT)
                |
             select(...)
                |
          isConnectable()
                |
          finishConnect()
                |
       +--------+----------+
       |        |          |
     false     true      IOException
       |        |          |
    chờ tiếp  đổi ops    close/cleanup
~~~

**isConnectable() chỉ là readiness hint.** Theo Java 17 SelectionKey, connectable có thể có nghĩa thao tác kết nối **đã sẵn sàng hoàn tất hoặc có lỗi đang chờ**. Không suy ra connection thành công khi Selector trả key OP_CONNECT; thành công/chưa xong/thất bại phải được phân biệt bằng **finishConnect()**.

**OP_CONNECT phải được bỏ sau khi connected.** Giữ cờ ấy hoặc tiếp tục xử lý key như CONNECTING là lỗi state machine. Khi đã connected, chỉ bật **OP_WRITE** nếu có dữ liệu thực sự cần gửi; socket thường writable gần như liên tục, vì vậy OP_WRITE bật vô điều kiện có thể làm event loop chạy bận.

## 5. Chương trình Java 17 hoàn chỉnh: non-blocking connect và nhận phản hồi

Ví dụ này tự tạo một **ServerSocketChannel trên loopback với cổng động**, không cần mạng Internet hay dịch vụ bên ngoài. Worker thread phía server gọi accept, gửi hai byte UTF-8 **OK** rồi đóng accepted channel. Phía client dùng SocketChannel non-blocking và Selector để kết nối, chờ finishConnect nếu cần, rồi đọc đủ hai byte.

**Quan trọng:** code xử lý cả **connect(true)** và **connect(false)**, vì trên localhost hành vi phụ thuộc OS/timing; đầu ra chỉ in trạng thái cuối để ổn định.

Tệp **NonBlockingConnectDemo.java**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NonBlockingConnectDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            ExecutorService workers = Executors.newSingleThreadExecutor();

            try {
                Future<Void> task = workers.submit(() -> {
                    try (SocketChannel peer = server.accept()) {
                        ByteBuffer reply = ByteBuffer.wrap(
                                "OK".getBytes(StandardCharsets.UTF_8));
                        while (reply.hasRemaining()) {
                            peer.write(reply);
                        }
                    }
                    return null;
                });

                boolean connected;
                boolean pending;
                String text;

                try (Selector selector = Selector.open();
                     SocketChannel client = SocketChannel.open()) {
                    client.configureBlocking(false);
                    boolean immediate =
                            client.connect(server.getLocalAddress());

                    SelectionKey key = client.register(
                            selector, immediate
                                    ? SelectionKey.OP_READ
                                    : SelectionKey.OP_CONNECT);

                    ByteBuffer buffer = ByteBuffer.allocate(2);
                    long deadline = System.nanoTime()
                            + TimeUnit.SECONDS.toNanos(5);

                    while (buffer.hasRemaining()) {
                        long leftNanos = deadline - System.nanoTime();
                        if (leftNanos <= 0) {
                            throw new SocketTimeoutException(
                                    "Connect/read deadline expired");
                        }

                        // select(0) sẽ chờ vô hạn, nên tối thiểu 1 ms.
                        long waitMillis = Math.max(
                                1L, TimeUnit.NANOSECONDS.toMillis(leftNanos));
                        selector.select(waitMillis);

                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();

                        while (it.hasNext()) {
                            SelectionKey ready = it.next();
                            it.remove();

                            if (!ready.isValid()) {
                                continue;
                            }

                            if (ready.isConnectable()) {
                                if (client.finishConnect()) {
                                    ready.interestOps(SelectionKey.OP_READ);
                                }
                            }

                            if (ready.isReadable()) {
                                int n = client.read(buffer);
                                if (n == -1) {
                                    throw new EOFException(
                                            "EOF before 2 bytes received");
                                }
                                // n == 0: chưa có byte, đợi lần sau.
                            }
                        }
                    }

                    connected = client.isConnected();
                    pending = client.isConnectionPending();
                    buffer.flip();
                    text = StandardCharsets.UTF_8
                            .decode(buffer).toString();
                }

                task.get(5, TimeUnit.SECONDS);
                System.out.println("Connected: " + connected);
                System.out.println("Pending: " + pending);
                System.out.println("Reply: " + text);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Lệnh chạy với Java 17 trở lên:

~~~bash
javac -encoding UTF-8 NonBlockingConnectDemo.java
java NonBlockingConnectDemo
~~~

Stdout khi thử nghiệm thành công:

~~~text
Connected: true
Pending: false
Reply: OK
~~~

### Diễn giải chính xác

- **server.bind(..., 0)** chọn cổng còn trống trên loopback. **server.getLocalAddress()** cung cấp địa chỉ server thực cho client.
- **ServerSocketChannel.accept()** là blocking trong worker, không chặn event loop client; accepted SocketChannel có vòng đời riêng.
- **client.configureBlocking(false)** được gọi trước connect. Khi immediate=true, đăng ký OP_READ thẳng; khi false, đăng ký OP_CONNECT và chờ finishConnect.
- **Selector.select(waitMillis)** có thể trả 0 do timeout hoặc wakeup, vì vậy mỗi vòng kiểm tra lại deadline chứ không kết luận lỗi ngay.
- Khi ready.isConnectable(), chỉ sau **finishConnect(true)** mới thay interestOps thành OP_READ. Nếu finishConnect false, key vẫn theo dõi OP_CONNECT; nếu ném IOException, try-with-resources dọn channel.
- Server gửi hai byte **OK**. Client đọc cho đủ hai byte, chấp nhận read() trả 0, nhận biết **-1 trước khi đủ hai byte** là dữ liệu không đầy đủ.
- **buffer.flip()** chuyển ByteBuffer từ trạng thái đang ghi byte sang đọc/giải mã. **Future.get()** xác nhận worker server hoàn tất trước khi in ba dòng.

Đây là **demo kết nối và I/O tối giản**, không phải protocol production: để nhận response độ dài thay đổi cần message framing và giới hạn byte; để ghi nhiều ByteBuffer cần xử lý partial write và OP_WRITE. Timeout 5 giây bảo vệ phần chờ client trong ví dụ, không bảo đảm DNS, TLS handshake hoặc mọi tác vụ nghiệp vụ của ứng dụng đều nằm trong 5 giây.

Nếu không thể bind hoặc connect loopback, hoặc máy quá chậm, ví dụ có thể ném exception/timeout thay vì in ba dòng. Không in giá trị **immediate** cố định vì đó là điều phụ thuộc runtime.

## 6. Ví dụ Java 17: trạng thái ban đầu và lỗi gọi sai thứ tự

**finishConnect không tự mở kết nối mới.** Một channel vừa open, chưa có connect pending, gọi finishConnect sẽ gặp **NoConnectionPendingException**; thao tác read trước kết nối sẽ gặp **NotYetConnectedException**.

Tệp **ConnectionStateDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.channels.NoConnectionPendingException;
import java.nio.channels.NotYetConnectedException;
import java.nio.channels.SocketChannel;

public class ConnectionStateDemo {
    public static void main(String[] args) throws Exception {
        try (SocketChannel channel = SocketChannel.open()) {
            channel.configureBlocking(false);

            System.out.println("Open: " + channel.isOpen());
            System.out.println("Connected: " + channel.isConnected());
            System.out.println("Pending: "
                    + channel.isConnectionPending());

            try {
                channel.finishConnect();
            } catch (NoConnectionPendingException ex) {
                System.out.println(
                        "finishConnect: NoConnectionPendingException");
            }

            try {
                channel.read(ByteBuffer.allocate(1));
            } catch (NotYetConnectedException ex) {
                System.out.println(
                        "read: NotYetConnectedException");
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConnectionStateDemo.java
java ConnectionStateDemo
~~~

Kết quả:

~~~text
Open: true
Connected: false
Pending: false
finishConnect: NoConnectionPendingException
read: NotYetConnectedException
~~~

Đầu ra chứng minh **open != connected**, **not pending != connected** và **finishConnect != connect**. Chương trình không dùng network endpoint nào nên kết quả không phụ thuộc tốc độ TCP handshake.

## 7. Deadline cho non-blocking connect

SocketChannel không có overload **connect(remote, timeout)** như một số cách gọi trên **java.net.Socket**. Nếu connect đang pending, chương trình phải tự kiểm soát tổng thời gian chờ với **Selector + deadline**.

~~~text
end = monotonicNow + timeoutBudget
connect(remote)
while connection pending:
    remaining = end - monotonicNow
    if remaining <= 0: close channel, báo timeout
    selector.select(roundedUpMillis(remaining))
    nếu OP_CONNECT: finishConnect()
~~~

Đây là thuật toán minh họa, không phải mã Java chạy độc lập.

**Vì sao dùng System.nanoTime()?** Nó phù hợp để đo thời gian trôi qua và tính deadline tương đối; thời gian wall-clock từ System.currentTimeMillis() có thể nhảy do NTP hoặc chỉnh đồng hồ. Khi đổi nanosecond sang milliseconds, không truyền 0 vào **Selector.select(0)** vì **0 nghĩa là chờ vô hạn**. Nếu cần chọn ngay không chặn, dùng **selectNow()**; nếu vẫn còn deadline dương rất ngắn, dùng **ít nhất 1 ms**.

**Selector.select(timeout) không tự làm TCP connect thất bại khi timeout.** Nó chỉ kết thúc *một lần chờ readiness*; bạn cần kiểm tra thời hạn của connection cụ thể rồi **close** kênh chưa hoàn tất. Hãy xử lý trường hợp select trả 0, wakeup và spurious event; không reset tổng deadline mỗi lần nhận một event không liên quan.

**DNS có thể là bước chặn trước connect.** Tạo InetSocketAddress từ hostname có thể dẫn đến name resolution trước lời gọi nonblocking connect. Nếu hệ thống cần SLA end-to-end, tính cả DNS, TCP connect, TLS, auth và request/response, hoặc dùng cơ chế giải quyết tên miền riêng.

**Không dùng channel.socket().connect(endpoint, timeout) như thay thế mù quáng** trên một SocketChannel đang ở non-blocking mode và đăng ký Selector. Đây là API khác, có ràng buộc blocking mode; thao tác không phù hợp có thể gây **IllegalBlockingModeException**. Chọn một mô hình nhất quán: khi dùng Selector thì quản lý deadline trong event loop và hoàn tất connect qua finishConnect.

### Hàng trăm channel thì theo dõi deadline ra sao?

Mỗi connection cần state riêng: **phase CONNECTING/CONNECTED**, **startedNanos/deadlineNanos**, **SelectionKey** và kết quả callback/future riêng. Event loop chọn thời gian đợi dựa vào deadline gần nhất; sau mỗi lần select xử lý cả selected keys lẫn connection quá hạn. Không dùng một biến deadline duy nhất làm timeout chung cho mọi channel được mở ở những thời điểm khác nhau.

**Retry khi quá hạn:** dọn channel cũ, hủy key, báo caller, nếu nghiệp vụ cần thì tạo **SocketChannel mới** sau backoff và trong tổng budget cho phép. Không giữ hàng trăm pending channels vô hạn vì mỗi channel vẫn tốn file descriptor và tài nguyên kernel.

## 8. ByteBuffer và I/O sau kết nối

Trước khi có **connect(true)** hoặc **finishConnect(true)**, channel chưa connected và read/write có thể ném **NotYetConnectedException**. Sau khi connected, non-blocking I/O vẫn có kết quả từng phần:

| Thao tác | Kết quả | Ý nghĩa |
|---|---|---|
| read(dst) | số dương | nhận được bấy nhiêu byte vào ByteBuffer |
| read(dst) | 0 | hiện không có byte, không phải EOF |
| read(dst) | -1 | end-of-stream trên chiều nhận |
| write(src) | số dương | chuyển bấy nhiêu byte từ src vào socket |
| write(src) | 0 | chưa thể gửi thêm, giữ src để thử khi writable |

**Một lần read không đồng nghĩa một message**, TCP là byte stream. Muốn nhận đầy đủ phải có framing như length-prefix, delimiter hoặc EOF-based protocol. **ByteBuffer.flip()** để chuyển từ ghi vào buffer sang đọc; **compact()** giúp giữ lại byte chưa xử lý khi nhận tiếp; **clear()** trên buffer chứa dữ liệu chưa gửi có thể làm mất payload.

Ví dụ minh họa với channel đã kết nối:

~~~java
ByteBuffer outgoing = StandardCharsets.UTF_8.encode("PING");
while (outgoing.hasRemaining()) {
    int n = channel.write(outgoing);
    if (n == 0) {
        // Non-blocking: đợi OP_WRITE rồi ghi nốt;
        // KHÔNG drop outgoing khi vẫn còn dữ liệu.
        break;
    }
}
~~~

Đây không phải chương trình chạy độc lập; cần import, channel đã connected, và code quản lý OP_WRITE sau break. Khi còn dữ liệu, bật OP_WRITE. Khi gửi hết, bỏ OP_WRITE để tránh busy loop do socket writable gần như liên tục.

Một key có thể **attach** một state object chứa phase, pending output buffer, incoming parser, deadline và request context. Đó là mô hình tốt hơn chia sẻ một ByteBuffer duy nhất giữa hàng nghìn connections.

## 9. Exceptions cần nhớ

| Exception | Khi nào? | Ứng xử |
|---|---|---|
| **NoConnectionPendingException** | finishConnect trên channel chưa connected và chưa pending | Sửa luồng trạng thái; connect trước |
| **ConnectionPendingException** | connect lại khi nonblocking connect vẫn pending | Không connect lần hai; finishConnect |
| **AlreadyConnectedException** | connect lại khi đã connected | Dùng I/O, không kết nối lại |
| **NotYetConnectedException** | read/write hoặc shutdown khi chưa connected | Chờ connect(true)/finishConnect(true) |
| **UnresolvedAddressException** | remote InetSocketAddress chưa được resolve | Xử lý phân giải tên miền |
| **ClosedChannelException** | thao tác trên channel đóng | Cleanup và mở channel mới nếu retry |
| **IOException**, có thể gồm ConnectException | Kết nối bị từ chối hoặc lỗi network | Cleanup, ghi nguyên nhân, retry có giới hạn |
| **AsynchronousCloseException** | thread khác đóng channel khi đang thao tác | Phối hợp cancellation/ownership |
| **ClosedByInterruptException** | interrupt trong I/O interruptible làm đóng channel | Giữ chính sách interrupt, cleanup |
| **IllegalBlockingModeException** | dùng chế độ blocking/Selector không phù hợp | Không đổi mode sai khi registered |
| **Selector.select() == 0** | timeout, wakeup hoặc chưa có ready key | Kiểm tra deadline, không mặc định thất bại |

**Lỗi connect có thể xuất hiện ở connect() hoặc finishConnect().** Đặc biệt, **OP_CONNECT readiness có thể báo một lỗi cần được rút ra qua finishConnect()**; không in “connected” dựa chỉ trên isConnectable().

Theo Javadoc, nếu connect attempt ném **checked exception** mô tả thất bại, SocketChannel sẽ **bị đóng**. Không retry ngay trên đối tượng ấy; mở channel mới. Trạng thái và thông báo lỗi cụ thể của TCP có thể khác nhau giữa Linux/Windows và tùy firewall/network.

## 10. Cạm bẫy phổ biến

### 10.1. Chỉ xử lý nhánh connect(false)

Đây là lỗi dễ qua test ở một OS rồi fail ở OS khác. **connect(true)** hoàn toàn hợp lệ, nhất là khi remote ở localhost; phải đi thẳng tới protocol I/O và đăng ký interest mới.

### 10.2. Busy-spin finishConnect

Đoạn sau cần tránh trong event-loop:

~~~java
while (!channel.finishConnect()) {
    // Không có Selector, deadline hoặc sleep.
}
~~~

Nó có thể tiêu thụ CPU, chặn những connection khác và không có kiểm soát timeout. Dùng **OP_CONNECT**, select với timeout và hoàn tất ở sự kiện thích hợp.

### 10.3. Nhầm OP_CONNECT với success

Selector cho biết connect sequence **có kết quả** hoặc **có lỗi cần xử lý**; **finishConnect** mới có thông tin thực. Không chuyển key sang OP_READ nếu finishConnect còn false hoặc ném exception.

### 10.4. Giữ OP_WRITE bật thường trực

Trong nhiều hệ thống, writable là trạng thái thường xuyên. Nếu event loop không có outgoing ByteBuffer mà vẫn giữ OP_WRITE, selector sẽ wake liên tục. Khi write hết dữ liệu, bỏ interest OP_WRITE và chỉ bật lại khi có byte cần gửi.

### 10.5. Không xóa selected keys

Sau khi xử lý selectedKeys, dùng **iterator.remove()** hoặc thao tác loại key tương đương. Nếu không, vòng sau có thể tiếp tục thấy key cũ và xử lý readiness sai thời điểm. **SelectionKey.cancel()** cũng không nhất thiết xóa object tức thì; selector xử lý cancelled key ở một lượt selection.

### 10.6. Đổi sang blocking khi vẫn registered

Nếu channel còn đăng ký với Selector, việc **configureBlocking(true)** có thể ném IllegalBlockingModeException. Hãy thiết kế vòng đời registration rõ ràng trước khi đổi mô hình hoặc tiếp tục dùng non-blocking nhất quán.

### 10.7. Race khi nhiều thread cùng quản lý một connection

SocketChannel hỗ trợ đọc và ghi đồng thời ở giới hạn API nhất định, nhưng **connect() và finishConnect() được đồng bộ với nhau**. Đừng để nhiều thread tranh giành state machine, interestOps và close. Một event-loop owner cho từng channel giúp dễ đảm bảo thứ tự sự kiện. Nếu worker cần đổi interest, giao message thread-safe và dùng **Selector.wakeup()** khi thích hợp.

### 10.8. Không giới hạn pending channels

Non-blocking không đồng nghĩa tài nguyên vô hạn. Mỗi channel có file descriptor, kernel state, deadline và Java objects. Giới hạn số pending theo endpoint, total concurrent connections, dùng retry backoff và đóng quá hạn.

## 11. TCP connected chưa chắc application đã sẵn sàng

**finishConnect(true)** chỉ xác nhận network socket đã connected. Với TLS, vẫn cần TLS handshake; với HTTP phải gửi request đúng format rồi đọc response; với giao thức riêng có thể còn authentication/session negotiation.

~~~text
DNS_RESOLVED
    -> TCP_CONNECTING
    -> TCP_CONNECTED
    -> TLS_HANDSHAKING (nếu có)
    -> APPLICATION_HANDSHAKING / AUTHENTICATING (nếu có)
    -> READY_FOR_APPLICATION_DATA
    -> CLOSING / CLOSED
~~~

**Không dùng isConnected() làm liveness check tuyệt đối.** Peer có thể mất mạng ngay sau khi connection thành công; I/O về sau vẫn có thể lỗi. Xử lý EOF, IOException, deadline và heartbeat theo protocol.

Nếu connect thất bại hoặc timeout và caller muốn retry, mở channel mới. Với thao tác có side effect, không tự phát lại application request khi không biết lần trước đã được xử lý hay chưa; cần idempotency policy và request ID ở tầng ứng dụng.

## 12. So sánh các mô hình kết nối Java

| Tiêu chí | SocketChannel blocking | SocketChannel non-blocking + Selector | AsynchronousSocketChannel |
|---|---|---|---|
| connect | Chặn tới thành công/lỗi | Có thể trả true hoặc false ngay | Completion Future/callback |
| Hoàn tất kết nối | Không cần finishConnect riêng sau connect thành công | finishConnect khi pending | Kết quả qua completion API |
| Cách chờ | Thread gọi connect | OP_CONNECT + Selector + deadline | Completion framework và lifecycle riêng |
| I/O | Blocking nếu giữ mode | Partial I/O, read/write có thể trả 0 | Completion-based read/write |
| Lỗi hay gặp | Chặn lâu, timeout thiếu | Quên finishConnect, interest, deadline | Callback race, cancellation, quản lý state |

**AsynchronousSocketChannel không dùng cùng cặp connect/finishConnect như SocketChannel.** Nó là API khác. Nếu dùng Java 21+ virtual threads, code blocking có thể thuận tiện hơn cho nhiều connection trong một số workload, nhưng không xóa deadline, FD limit hay lỗi TCP.

## 13. Bài tập luyện tập

**A. Quan sát nhánh immediate/pending.** Chạy NonBlockingConnectDemo nhiều lần, thêm log giá trị trả về của connect và isConnectionPending ngay sau đó. Có thể một máy chỉ thấy một nhánh; giải thích vì sao code vẫn phải xử lý cả hai.

**B. Bỏ finishConnect.** Trong nhánh isConnectable, thử chuyển interest sang OP_READ mà không finishConnect. Nêu nguy cơ NotYetConnectedException, rồi sửa.

**C. Kết nối bị từ chối.** Thử địa chỉ loopback/cổng không có listener trong môi trường tự kiểm soát. Bắt IOException ở cả connect và finishConnect; log đúng lý do, close, không kỳ vọng một subclass exception/cùng thời gian lỗi trên mọi OS.

**D. Quá deadline.** Dùng một endpoint thử nghiệm phản hồi chậm và giới hạn kết nối 100 ms. Kiểm tra không có select(0) khi còn deadline dương và channel được close khi quá hạn. Không thử trên mạng người khác trái phép.

**E. Gửi ByteBuffer lớn.** Sau finishConnect(true), gửi payload lớn hơn send buffer. Xử lý write trả 0, giữ position, đăng ký OP_WRITE, tắt OP_WRITE khi gửi hết; server dùng framing để đọc đủ byte.

**F. Nhiều kết nối cùng lúc.** Quản lý 100 SocketChannel pending trong một Selector với state object/deadline riêng, giới hạn tổng FD và thống kê số immediate, pending, success, timeout, failure.

## 14. Tự kiểm tra hiểu đúng

**1. connect() non-blocking trả false có phải thất bại?** Không; một connection operation đã được khởi tạo và chưa hoàn tất.

**2. connect() trả true có cần đợi OP_CONNECT không?** Không, đã connected, chuyển sang I/O.

**3. isConnectionPending() luôn phản ánh kernel còn bắt tay TCP chứ?** Không; nó mô tả kết nối chưa hoàn tất qua API Java, có thể đã có kết quả chờ finishConnect.

**4. Key isConnectable() bảo đảm TCP connect thành công?** Không; cả kết quả thất bại có thể làm key connectable. Gọi finishConnect.

**5. finishConnect() trả false nghĩa là gì?** Kết nối vẫn pending trong non-blocking mode; chưa read/write.

**6. Chưa gọi connect mà gọi finishConnect thì sao?** NoConnectionPendingException khi channel chưa connected và chưa có operation pending.

**7. isOpen() true nghĩa đã connected?** Không. Channel mới tạo vẫn open nhưng chưa connected.

**8. Vì sao read/write trước kết nối gây lỗi?** SocketChannel chưa connected; có thể ném NotYetConnectedException.

**9. Selector.select(0) nghĩa là không đợi?** Không. Nó có thể chờ vô hạn; muốn không đợi dùng selectNow().

**10. Sau finishConnect(true) còn giữ OP_CONNECT không?** Không nên; đổi interest sang OP_READ hoặc OP_WRITE nếu cần.

**11. Retry connect bằng cùng channel sau checked IOException được không?** Không: theo API, connection attempt thất bại có thể đóng channel; tạo channel mới và quản lý backoff.

**12. Connected tức HTTP/TLS đã sẵn sàng?** Chưa; TCP connected là một giai đoạn, còn handshake và protocol application.

## Tài liệu đối chiếu

- **Java SE 17 — SocketChannel:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html
- **Java SE 17 — Selector:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html
- **Java SE 17 — SelectionKey:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html
- **Java SE 17 — ByteBuffer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html

**Ghi nhớ:** **connect(true)** là connected ngay; **connect(false)** là **pending, không phải failure**. Chỉ sử dụng channel cho I/O sau **connect(true)** hoặc **finishConnect(true)**. **OP_CONNECT** báo tình huống cần kiểm tra kết quả qua finishConnect, không chứng minh success. Hãy quản lý **deadline, SelectionKey interestOps, ByteBuffer, IOException, close/cancel và retry** bằng state machine rõ ràng.