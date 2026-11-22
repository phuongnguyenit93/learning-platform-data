# Hủy key, xử lý EOF và đóng kết nối khi xảy ra lỗi

## 1. Vấn đề: Selector không tự đóng mọi kết nối

Trong Java NIO, **Selector** cho phép một thread theo dõi nhiều **SelectableChannel**. Một **ServerSocketChannel** thường đăng ký **OP_ACCEPT** để nhận kết nối; mỗi **SocketChannel** sau accept đăng ký **OP_READ**, rồi có thể đổi sang **OP_WRITE** khi cần gửi phản hồi. Đối tượng **SelectionKey** biểu diễn đăng ký một channel với một selector và lưu thông tin interest, readiness, attachment.

Một server có thể xử lý client bình thường nhưng rò rỉ socket, giữ key không hợp lệ hoặc quay vòng CPU khi một client đóng kết nối, gửi dữ liệu sai, hoặc một thao tác I/O ném ngoại lệ.

Điểm quan trọng cần phân biệt:

- **SelectionKey.cancel():** đánh dấu key invalid ngay và yêu cầu hủy đăng ký với selector. Đây **không phải SocketChannel.close()**, nên không đủ để giải phóng socket.
- **SocketChannel.close():** đóng chính channel/socket. Nếu channel đang đăng ký với selector, các registration key liên quan cũng bị hủy, nhưng vẫn cần dọn state của connection.
- **Selector.close():** đóng selector và hủy các key liên quan. Nó **không tự đóng mọi channel** đã từng đăng ký; server phải đóng SocketChannel và ServerSocketChannel mà nó sở hữu.
- **iterator.remove() trên selectedKeys():** bỏ key khỏi tập các key đang được chọn ở vòng hiện tại; đây **không phải key.cancel()**.

Một đường cleanup đúng khi connection kết thúc là **ngừng theo dõi key, đóng channel và dọn state**. Lỗi của một SocketChannel thường phải được cô lập cho client đó; không tự động làm sập selector dùng chung.

~~~text
ServerSocketChannel --register(OP_ACCEPT)--> Selector
                                               |
                                             select()
                                               |
                                           selectedKeys()
                                               |
                        +----------------------+----------------+
                        |                      |                |
                     OP_ACCEPT               OP_READ          OP_WRITE
                        |                      |                |
                 accept SocketChannel    read() n>0, 0,-1   write pending
                        |                      |
                  register(OP_READ)       EOF hoặc lỗi riêng
                                               |
                                      key.cancel + channel.close
                                               |
                                    event loop còn phục vụ client khác
~~~

## 2. Vòng đời đăng ký và những tập key trong Selector

### 2.1. Các API quan trọng

| Đối tượng/API | Ý nghĩa |
| --- | --- |
| **Selector.open()** | Mở selector |
| **channel.configureBlocking(false)** | Điều kiện để register channel với selector |
| **channel.register(selector, ops, attachment)** | Tạo/cập nhật key; gắn state theo connection |
| **selector.select()** | Chờ ít nhất một thay đổi readiness, wakeup hoặc sự kiện liên quan |
| **selector.selectedKeys()** | Tập key mà event loop cần xử lý ở vòng chọn hiện tại |
| **selector.keys()** | Tập key đang được đăng ký với selector, bao gồm trạng thái cancellation chưa được dọn |
| **key.isValid()** | Kiểm tra key chưa bị hủy và channel/selector còn mở |
| **key.interestOps(...)** | Chỉnh những operation đang quan tâm khi key còn valid |
| **key.cancel()** | Key mất hiệu lực ngay; việc dọn đăng ký được xử lý sau đó |
| **selector.wakeup()** | Đánh thức select đang chờ; không thay cho close() |

Các bit readiness phổ biến là **OP_ACCEPT**, **OP_CONNECT**, **OP_READ** và **OP_WRITE**. Không phải mọi operation đều hợp lệ với mọi channel: ServerSocketChannel dùng OP_ACCEPT; SocketChannel dùng các operation thích hợp cho socket kết nối.

**Lưu ý:** Một lần readiness không có nghĩa chắc chắn đã có đủ toàn bộ message, cũng không có nghĩa một write sẽ tiêu thụ hết ByteBuffer. Đây vẫn là TCP byte stream; parser và outbound queue phải quản lý partial read/write.

### 2.2. Selected key phải được lấy ra khỏi selected-key set

Vòng lặp thường dùng:

~~~java
// Minh họa cấu trúc, selector và các handler được khai báo trong server.
selector.select();
Iterator<SelectionKey> it = selector.selectedKeys().iterator();

while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove(); // Đừng để selected key cũ tồn tại qua vòng kế tiếp.

    if (!key.isValid()) {
        continue;
    }
    // Xử lý accept/read/write...
}
~~~

**selector.selectedKeys() không tự xóa key sau khi code xử lý xong**. Thiếu iterator.remove() có thể khiến event loop xử lý lại readiness cũ hoặc lặp vô ích.

### 2.3. Cancellation có thời điểm và phạm vi riêng

Theo hợp đồng SelectionKey, gọi **key.cancel()** làm key **invalid ngay lập tức**. Việc xóa đăng ký khỏi tập key của selector sẽ diễn ra ở các thao tác chọn tiếp theo. Bởi vậy không nên lấy **selector.keys().size() ngay sau cancel()** làm bằng chứng rằng mọi channel đã dọn xong.

Sau khi cancel, những thao tác đọc hoặc sửa readiness/interest như **key.interestOps(...)** hay **key.readyOps()** có thể ném **CancelledKeyException**. Hãy ngừng thao tác trên key không còn valid.

Một cleanup minh họa:

~~~java
// Minh họa, không phải chương trình độc lập.
// Tài nguyên của connection do event loop sở hữu.
static void closeClient(SelectionKey key) throws IOException {
    key.attach(null);       // Bỏ tham chiếu state nếu phù hợp.
    key.cancel();           // Hủy đăng ký.
    key.channel().close();  // Giải phóng channel thực.
}
~~~

Một implementation production cần xử lý **lỗi ngay trong close**, **gọi cleanup nhiều lần** và các tài nguyên khác chứa trong attachment. Việc attach(null) bỏ tham chiếu, nhưng không tự đóng những resource AutoCloseable nằm bên trong state; phải quản lý chúng riêng.

## 3. Xử lý read() = -1, 0 và số dương

Với SocketChannel đọc vào ByteBuffer:

~~~java
int n = socketChannel.read(inbound);
~~~

| Giá trị | Diễn giải đúng | Hành động khả dĩ |
| --- | --- | --- |
| **n > 0** | Đã nhận n byte, có thể là một phần hoặc nhiều frame | Chuyển buffer sang read mode, xử lý frame hoàn chỉnh, giữ byte dở dang |
| **n == 0** | Không nhận byte trong lời gọi này; phổ biến ở non-blocking mode hoặc khi buffer không còn chỗ | Không coi là EOF; đợi sự kiện tiếp hoặc xử lý buffer đầy |
| **n == -1** | Kết thúc luồng đọc (EOF); peer đã chấm dứt chiều gửi và byte trước đó đã được lấy hết | Xem giao thức còn outbound cần gửi không; đóng connection nếu đã xong |
| **IOException** | I/O hỏng | Ghi nhận và đóng connection theo chính sách |

**Read trả 0 không phải EOF.** Trong non-blocking mode, có thể tại thời điểm gọi chưa có byte mới. Hãy đợi **OP_READ** tiếp thay vì đóng connection hay quay vòng vô hạn. Nếu ByteBuffer đã đầy, đừng liên tục gọi read với remaining=0; cần giải mã frame, mở rộng có giới hạn hoặc từ chối dữ liệu quá dài.

**Read trả -1 là EOF của chiều nhận**, không nhất thiết cả hai chiều của TCP lập tức bị đóng. TCP cho phép **half-close**: client gọi **shutdownOutput()** (FIN ở chiều gửi) nhưng vẫn có thể đọc phản hồi server.

- Nếu server đang đọc message chưa đủ length-prefix/body rồi gặp EOF: frame bị cắt, báo lỗi và dọn connection.
- Nếu giao thức quy định **đọc đến EOF** là kết thúc request rồi **server mới gửi response**, server có thể chuyển sang OP_WRITE và đóng sau khi gửi xong.
- Nếu không còn request/response hợp lệ cần xử lý, cancel key và đóng SocketChannel ngay.

Tránh giữ một SocketChannel đã EOF ở trạng thái **OP_READ** mà không thay đổi gì. Nó có thể lại được chọn ready-to-read vì read sẽ tiếp tục trả -1, gây **busy loop**.

### EOF không đồng nghĩa một thông điệp hợp lệ

Ví dụ giao thức cần body 100 byte nhưng mới nhận 70 byte trước EOF: không được xử lý như message hoàn chỉnh. Nếu một read trả n > 0, vẫn có thể còn frame chưa hoàn chỉnh. EOF là thông tin vòng đời **stream**, còn ranh giới message do **giao thức ứng dụng** xác định.

## 4. Cô lập exception theo connection

Một event loop Selector thường xử lý nhiều socket trong một thread. Nếu chỉ một client gửi command lỗi và handler ném IOException, server không nên vô cớ đóng cả selector.

| Tình huống | Phạm vi xử lý |
| --- | --- |
| **SocketChannel.read/write IOException** | Thường là lỗi một connection; đóng SocketChannel đó |
| **Frame sai, quá dài hoặc command không hợp lệ** | Từ chối request, đóng socket liên quan |
| **CancelledKeyException** khi chạm key invalid | Kiểm tra vòng đời key, dừng xử lý key đó |
| **EOF của client** | Theo giao thức, đóng ngay hoặc gửi hết outbound rồi đóng |
| **ServerSocketChannel.accept() hỏng** | Có thể là lỗi listener cấp server; không ngụy trang thành request lỗi |
| **Selector bị đóng/hỏng** | Dừng event loop có kiểm soát, dọn các channel đang giữ |
| **Lỗi JVM nghiêm trọng** | Không nuốt tùy tiện rồi coi server vẫn an toàn |

Một bố cục xử lý đơn giản:

~~~java
// Minh họa ý tưởng; acceptClient/readClient/writeClient/closeClientBestEffort
// là hàm ứng dụng, không phải API có sẵn.
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();
    if (!key.isValid()) {
        continue;
    }

    try {
        if (key.isAcceptable()) {
            acceptClient();
        } else if (key.isReadable()) {
            readClient(key);
        } else if (key.isWritable()) {
            writeClient(key);
        }
    } catch (IOException | RuntimeException ex) {
        if (key.channel() instanceof SocketChannel) {
            closeClientBestEffort(key); // Chỉ connection lỗi.
        } else {
            throw ex; // Lỗi của listener cần xử lý ở cấp server.
        }
    }
}
~~~

Trong sản phẩm, phải ghi **lỗi gốc**, connection ID và lỗi cleanup nếu có. Nếu close() lại ném exception, đừng để exception cleanup che mất nguyên nhân thật. Một nhánh catch rộng không thay thế việc phân loại lỗi và dọn tài nguyên.

### Vấn đề ownership

- Sau **accept()**, socket mới do accept loop sở hữu cho tới khi được đăng ký/chuyển giao thành công.
- Nếu **configureBlocking/register thất bại**, accept loop phải đóng SocketChannel chưa được quản lý.
- Khi connection đã được đăng ký, event loop (hoặc thành phần quản lý connection) chịu trách nhiệm đóng, dọn attachment và cập nhật chỉ số.
- Khi shutdown, listener đóng không tự kéo theo tất cả accepted SocketChannel đã có trước đó.
- Cleanup nên **idempotent**: được gọi lại không làm đếm hai lần hay tạo lỗi vô nghĩa.

## 5. Ví dụ Java 17+ chạy được: cancel key, EOF, lỗi BAD và cleanup

Ví dụ **SelectorCleanupDemo.java** có cả một server chạy Selector và mã test client trong cùng JVM. Không cần Maven, JUnit hay Internet.

Kịch bản xác định:

1. Server mở **Selector** và **ServerSocketChannel non-blocking** trên **loopback**, port do hệ điều hành cấp.
2. Client thứ nhất gửi **PING + LF**, server nhận và trả **PONG + LF**, rồi đóng socket theo giao thức một request/response trên kết nối.
3. Client thứ hai gọi **shutdownOutput()**, làm server gặp **read = -1**. Không có response đang chờ nên server đóng socket.
4. Client thứ ba gửi **BAD + LF**. Handler ném **IOException**, nhánh catch per-key hủy key và đóng SocketChannel; client đọc được EOF.
5. Client thứ tư gửi **PING** sau lỗi BAD; nhận đúng PONG, chứng minh selector còn hoạt động.
6. Test xác nhận **4 accepted, 2 PING responses, 1 EOF, 1 malformed command, 4 accepted socket channels đóng**.
7. Shutdown gọi selector.wakeup(), đợi event-loop thread thoát và xác nhận selector đã đóng.

Giao thức demo nhận **một dòng ASCII ngắn trên mỗi kết nối**, không hỗ trợ gửi nhiều lệnh trên cùng socket. Buffer input 64 byte có giới hạn. Trong dịch vụ thật cần giới hạn message, thời gian đọc, xác thực và bảo vệ tài nguyên phù hợp.

### Tệp SelectorCleanupDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class SelectorCleanupDemo {
    static final class Server implements AutoCloseable {
        final CountDownLatch ready = new CountDownLatch(1);
        final CountDownLatch fourClosed = new CountDownLatch(4);

        final AtomicInteger accepted = new AtomicInteger();
        final AtomicInteger replies = new AtomicInteger();
        final AtomicInteger eof = new AtomicInteger();
        final AtomicInteger malformed = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();

        volatile Selector selector;
        volatile int port;
        volatile boolean running = true;
        volatile Throwable failure;

        final Thread thread = new Thread(this::run, "selector-server");

        Server() {
            thread.start();
        }

        void closeKey(SelectionKey key) {
            key.cancel();
            if (key.channel() instanceof SocketChannel sc && sc.isOpen()) {
                try {
                    sc.close();
                } catch (IOException ex) {
                    failure = ex;
                } finally {
                    if (!sc.isOpen()) {
                        closed.incrementAndGet();
                        fourClosed.countDown();
                    }
                }
            }
        }

        void run() {
            try (Selector sel = Selector.open();
                    ServerSocketChannel listener =
                            ServerSocketChannel.open()) {
                selector = sel;
                listener.configureBlocking(false);
                listener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
                port = ((InetSocketAddress)
                        listener.getLocalAddress()).getPort();
                listener.register(sel, SelectionKey.OP_ACCEPT);
                ready.countDown();

                try {
                    while (running) {
                        sel.select();
                        Iterator<SelectionKey> it =
                                sel.selectedKeys().iterator();

                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();

                            if (!key.isValid()) {
                                continue;
                            }

                            try {
                                if (key.isAcceptable()) {
                                    SocketChannel peer =
                                            listener.accept();
                                    if (peer != null) {
                                        accepted.incrementAndGet();
                                        try {
                                            peer.configureBlocking(false);
                                            peer.register(
                                                    sel,
                                                    SelectionKey.OP_READ,
                                                    ByteBuffer.allocate(64)
                                            );
                                        } catch (IOException |
                                                RuntimeException ex) {
                                            try {
                                                peer.close();
                                            } finally {
                                                closed.incrementAndGet();
                                                fourClosed.countDown();
                                            }
                                            throw ex;
                                        }
                                    }
                                } else if (key.isReadable()) {
                                    onRead(key);
                                } else if (key.isWritable()) {
                                    onWrite(key);
                                }
                            } catch (IOException |
                                    RuntimeException ex) {
                                if (key.channel()
                                        instanceof SocketChannel) {
                                    malformed.incrementAndGet();
                                    closeKey(key);
                                } else {
                                    throw ex;
                                }
                            }
                        }
                    }
                } finally {
                    // Đóng những accepted sockets còn mở khi shutdown.
                    for (SelectionKey key :
                            new ArrayList<>(sel.keys())) {
                        if (key.channel() instanceof SocketChannel) {
                            closeKey(key);
                        }
                    }
                }
            } catch (Throwable ex) {
                failure = ex;
            } finally {
                ready.countDown();
            }
        }

        void onRead(SelectionKey key) throws IOException {
            SocketChannel peer =
                    (SocketChannel) key.channel();
            ByteBuffer input =
                    (ByteBuffer) key.attachment();

            int n = peer.read(input);
            if (n == -1) {
                eof.incrementAndGet();
                closeKey(key);
                return;
            }
            if (n == 0) {
                return;
            }

            // Chỉ demo một command ASCII kết thúc bằng LF.
            for (int i = 0; i < input.position(); i++) {
                if (input.get(i) == (byte) '\n') {
                    byte[] line = new byte[i];
                    input.flip();
                    input.get(line);
                    String command = new String(
                            line, StandardCharsets.US_ASCII);

                    if (!"PING".equals(command)) {
                        throw new IOException(
                                "Unsupported command: " + command);
                    }

                    key.attach(ByteBuffer.wrap(
                            "PONG\n".getBytes(
                                    StandardCharsets.US_ASCII)));
                    key.interestOps(SelectionKey.OP_WRITE);
                    return;
                }
            }

            if (!input.hasRemaining()) {
                throw new IOException("Line too long");
            }
        }

        void onWrite(SelectionKey key) throws IOException {
            SocketChannel peer =
                    (SocketChannel) key.channel();
            ByteBuffer response =
                    (ByteBuffer) key.attachment();
            peer.write(response);

            // Có thể chỉ ghi một phần; giữ OP_WRITE nếu còn byte.
            if (!response.hasRemaining()) {
                replies.incrementAndGet();
                closeKey(key);
            }
        }

        @Override
        public void close() throws InterruptedException {
            running = false;
            Selector sel = selector;
            if (sel != null) {
                sel.wakeup();
            }
            thread.join(5000);
            if (thread.isAlive()) {
                throw new AssertionError(
                        "selector thread did not stop");
            }
        }
    }

    static Socket connected(int port) throws IOException {
        Socket client = new Socket();
        client.connect(new InetSocketAddress(
                InetAddress.getLoopbackAddress(), port), 3000);
        client.setSoTimeout(3000);
        return client;
    }

    static String command(int port, String text)
            throws IOException {
        try (Socket client = connected(port)) {
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.US_ASCII));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.US_ASCII));

            out.write(text);
            out.write('\n');
            out.flush();
            return in.readLine();
        }
    }

    static void sendEof(int port) throws IOException {
        try (Socket client = connected(port)) {
            client.shutdownOutput();
            if (client.getInputStream().read() != -1) {
                throw new AssertionError(
                        "expected EOF after server close");
            }
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Server server = new Server();
        try {
            check(server.ready.await(5, TimeUnit.SECONDS),
                    "not ready");
            check(server.failure == null,
                    "server startup failure");

            check("PONG".equals(command(server.port, "PING")),
                    "first PING");
            sendEof(server.port);
            check(command(server.port, "BAD") == null,
                    "BAD must close");
            check("PONG".equals(command(server.port, "PING")),
                    "second PING");

            check(server.fourClosed.await(5, TimeUnit.SECONDS),
                    "not all four client channels closed");
            check(server.accepted.get() == 4, "accepted count");
            check(server.replies.get() == 2, "reply count");
            check(server.eof.get() == 1, "EOF count");
            check(server.malformed.get() == 1, "error count");
            check(server.closed.get() == 4, "close count");
            check(server.failure == null,
                    "server loop failure");
        } finally {
            server.close();
        }

        check(!server.selector.isOpen(),
                "selector not closed");
        check(!server.thread.isAlive(),
                "selector thread still alive");

        System.out.println("PASS: 4 connections accepted");
        System.out.println("PASS: 1 EOF, 1 malformed command");
        System.out.println(
                "PASS: 2 PING responses after error isolation");
        System.out.println("PASS: 4 client channels closed");
        System.out.println("PASS: selector and loop stopped");
    }
}
~~~

### Biên dịch, chạy và kết quả

Dùng JDK 17 trở lên, lưu đúng tên tệp **SelectorCleanupDemo.java**:

~~~bash
javac --release 17 -encoding UTF-8 SelectorCleanupDemo.java
java SelectorCleanupDemo
~~~

**Stdout khi test thành công** (logic đã chạy trên Java runtime):

~~~text
PASS: 4 connections accepted
PASS: 1 EOF, 1 malformed command
PASS: 2 PING responses after error isolation
PASS: 4 client channels closed
PASS: selector and loop stopped
~~~

Dòng thứ ba đếm **hai response PING tổng cộng**, một trước và một **sau** command BAD. Chính PING sau BAD chứng minh event loop không bị kết thúc bởi một request lỗi.

**Cơ chế xác nhận:** chương trình không in kết luận nếu các assert về accepted, replies, EOF, malformed, closed hoặc trạng thái selector thất bại. Nó dùng **CountDownLatch** để chờ server ready và chờ đủ bốn socket closed, không dựa vào sleep để đoán lịch chạy.

### 5.1. Luồng PING thành công

~~~text
accept() -> SocketChannel non-blocking -> register(OP_READ, ByteBuffer)
OP_READ  -> read n>0 -> thấy "PING\n" -> attach(PONG buffer)
         -> interestOps(OP_WRITE)
OP_WRITE -> channel.write(response buffer)
         -> nếu còn remaining, chờ OP_WRITE lần sau
         -> khi gửi hết: replies++, cancel key, close channel
~~~

SocketChannel.write(ByteBuffer) có thể chỉ lấy một phần byte. Đừng đóng ngay khi write trả số dương mà vẫn còn remaining. Chỉ khi output buffer đã hết mới đóng theo giao thức **một command/một connection** ở ví dụ. Hành động đóng không chứng minh một hệ thống bên kia đã commit nghiệp vụ.

### 5.2. Luồng EOF

~~~text
Client shutdownOutput()
      |
Server readiness OP_READ
      |
SocketChannel.read(input) = -1
      |
Demo không có pending response
      |
eof++, cancel key, close channel
~~~

Server không gọi PONG cho EOF không có command. Trong giao thức khác có thể phải gửi phản hồi **sau khi EOF** trước khi close; đó là lý do cần phân biệt half-close với đóng cả connection.

### 5.3. Luồng BAD gây lỗi

~~~text
OP_READ -> nhận "BAD\n"
        -> parser ném IOException
        -> catch chỉ ở SelectionKey của SocketChannel
        -> malformed++, cancel key, close channel
        -> event loop tiếp tục accept/read/write
        -> PING tiếp theo vẫn nhận PONG
~~~

Đây là **error isolation** theo connection. Khi listener gặp lỗi nghiêm trọng, chương trình chuyển lên nhánh server failure thay vì coi đó là command sai.

### 5.4. Đóng toàn bộ server

Một thread khác đặt **running=false**, gọi **selector.wakeup()** để select thoát chờ. Event loop đi ra khỏi while, thực hiện finally đóng những client channel còn lại, rồi try-with-resources đóng listener và selector. Sau đó test **join** event-loop thread và xác minh selector.isOpen() là false.

**selector.wakeup() không thay selector.close().** Nó chỉ thúc đẩy select trả quyền để thread có thể tự hoàn tất shutdown. Đồng thời, **selector.close() không thay việc đóng accepted sockets**.

## 6. Dọn attachment, buffer và những lỗi tiềm ẩn

### Attachment có thể giữ cả trạng thái kết nối

Trong dịch vụ có protocol phức tạp, attachment thường là một đối tượng giữ ByteBuffer inbound, queue ByteBuffer outbound, tình trạng half-close và timeout.

~~~java
// Minh họa mô hình state; không phải ứng dụng chạy độc lập.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    boolean inputEnded;
    boolean closingAfterWrite;
}
~~~

Khi socket kết thúc, dọn queue, hủy timeout/scheduled task của connection, đóng những tài nguyên bổ sung nếu có, và bỏ tham chiếu để có thể thu hồi bộ nhớ. Nếu đang có bytes outbound cần gửi sau input EOF, có thể đặt **closingAfterWrite=true** rồi hủy OP_READ, giữ OP_WRITE cho tới khi queue hết; sau đó mới cancel và close.

### Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Chỉ cancel key, không close SocketChannel** | Giữ socket/FD dù key invalid | Đóng channel |
| **Chỉ close Selector, không close accepted channels** | Socket đã accept có thể còn sống | Dọn từng connection thuộc ownership |
| **Quên iterator.remove()** | Xử lý lặp selected key cũ | Remove từng key ở vòng event |
| **Truy cập readyOps/interestOps sau cancel** | CancelledKeyException | Kiểm tra valid và không dùng lại key hủy |
| **Coi read 0 là EOF** | Đóng socket còn sống | Phân biệt 0 với -1 |
| **Giữ OP_READ sau EOF, không đổi state** | Có thể quay vòng ready-to-read vô hạn | Chuyển sang write-only khi cần hoặc close |
| **Đóng ngay khi EOF dù còn response** | Mất phản hồi theo giao thức half-close | Gửi hết outbound rồi mới đóng |
| **Một IOException trên client làm thoát event loop** | Client lỗi làm chết dịch vụ | Catch per-key, phân biệt listener failure |
| **Đếm closed trước khi close thực sự** | Metrics sai | Đếm theo trạng thái sau cleanup |
| **Không đóng socket nếu register lỗi sau accept** | Rò rỉ socket chưa có handler | Accept loop cleanup nhánh register thất bại |
| **Quên giới hạn input trước LF/frame** | Client độc hại giữ RAM/CPU | Giới hạn bytes và deadline |
| **Luôn theo dõi OP_WRITE dù queue trống** | Event loop có thể quay vòng CPU | Chỉ theo dõi OP_WRITE khi có pending output |

### Thực thi cleanup từ một thread sở hữu

Một quy ước hiệu quả là chỉ **event-loop thread** sửa interestOps/cancel key/close per-connection channel. Thread khác gửi yêu cầu dừng qua concurrent queue và gọi **selector.wakeup()**:

~~~text
Worker/thread khác:
    enqueue yêu cầu đóng connection X
    selector.wakeup()

Event loop:
    lấy yêu cầu khỏi queue
    key.cancel()
    channel.close()
    dọn attachment/state
    select tiếp
~~~

Cách này giảm race giữa đọc selectedKeys và hủy key ở thread khác. Nếu nhiều thread cùng sửa một key và connection state, cần một thiết kế đồng bộ/ownership cụ thể; **ByteBuffer và application state không tự thread-safe**.

## 7. Kiểm thử mọi nhánh cần thiết

| Tình huống thử | Điều cần assert |
| --- | --- |
| PING hợp lệ | Server trả đúng PONG, channel đóng theo protocol |
| Client gọi shutdownOutput ngay | read trả -1, không bị hiểu thành read 0, channel đóng |
| BAD/protocol exception | Chỉ client đó bị đóng, client kế tiếp vẫn hoạt động |
| Client gửi không có LF rồi im lặng | Không chờ vô hạn; kích thước và thời gian được giới hạn |
| Client gửi message quá dài | Lỗi giao thức, không cấp phát vô hạn, đóng connection |
| Write chỉ tiêu thụ một phần | Buffer remaining được giữ, tiếp tục OP_WRITE |
| OP_WRITE không còn outbound | Interest OP_WRITE được tắt, không busy-spin |
| Cancel key rồi kiểm tra isValid | isValid false; không truy cập readyOps một cách mù quáng |
| Shutdown khi select đang chờ | wakeup làm event loop thoát, listener/selector đóng |
| Shutdown khi client còn mở | Server đóng từng accepted channel trước khi kết thúc |
| Lặp nhiều lượt start/stop | Không tăng không giới hạn FD, thread hay connection active |

Đo trên JVM bằng **channel.isOpen()**, **selector.isOpen()**, counters accepted/closed, số thread và heap; ở hệ điều hành có thể kiểm tra file descriptors/handles và socket qua nhiều vòng. **TIME_WAIT** sau close có thể là trạng thái TCP hợp lệ, không tự chứng minh Java đang rò rỉ socket; **CLOSE_WAIT** kéo dài đáng kiểm tra khi phía ứng dụng quên close sau peer EOF.

## 8. Tự kiểm tra

**Câu 1.** key.cancel() có đóng socket không?  
**Trả lời:** Không, phải đóng SocketChannel khi connection kết thúc.

**Câu 2.** Close SocketChannel có ảnh hưởng SelectionKey?  
**Trả lời:** Có, các đăng ký của channel bị hủy, nhưng state và tài nguyên bổ sung vẫn cần cleanup.

**Câu 3.** Close Selector có tự đóng tất cả accepted SocketChannel?  
**Trả lời:** Không. Server chịu trách nhiệm đóng những channel do nó tạo/sở hữu.

**Câu 4.** Non-blocking read trả 0 có nghĩa peer đóng?  
**Trả lời:** Không. 0 có thể do chưa có byte mới hoặc buffer không còn chỗ. EOF là -1.

**Câu 5.** Peer gọi shutdownOutput rồi vẫn đợi response có hợp lệ?  
**Trả lời:** Có. TCP hỗ trợ half-close. Server có thể gửi phản hồi sau EOF nếu protocol yêu cầu.

**Câu 6.** Vì sao phải iterator.remove()?  
**Trả lời:** selectedKeys không tự xóa key sau khi handler xử lý; remove tránh lặp readiness cũ.

**Câu 7.** Một client gửi BAD có phải đóng selector?  
**Trả lời:** Không. Đóng connection lỗi, cho các connection khác tiếp tục.

**Câu 8.** Key đã cancel thì có thể gọi interestOps(OP_WRITE) tiếp không?  
**Trả lời:** Không. Key invalid, thao tác có thể ném CancelledKeyException.

**Câu 9.** EOF giữa length-prefix body nên xử lý ra sao?  
**Trả lời:** Coi frame chưa hoàn chỉnh là protocol error, không xử lý payload thiếu như thông điệp đầy đủ.

**Câu 10.** Nếu server muốn shutdown khi select đang chờ, hành động gì giúp đánh thức select?  
**Trả lời:** Đặt cờ dừng và gọi selector.wakeup(); event loop sau đó đóng accepted channels, listener, selector và kết thúc thread.

## Kết luận

Trong Java NIO, **SelectionKey là đăng ký readiness, SocketChannel mới là tài nguyên kết nối**. **key.cancel() không thay channel.close()**, và đóng selector cũng không tự đóng mọi socket client. Để xử lý đúng, phải nhận biết **read -1 là EOF**, **read 0 không phải EOF**, tôn trọng khả năng half-close, cô lập lỗi per-client và có một đường cleanup nhất quán cho cả kết nối lỗi và shutdown.

Khi test cho thấy **PING vẫn hoạt động sau BAD**, **EOF được xử lý**, **mọi SocketChannel đã đóng** và **selector thread kết thúc**, ta mới có bằng chứng cụ thể về vòng đời của các key và tài nguyên.

### Tài liệu tham khảo

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): select, selectedKeys, wakeup, close.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): cancel, interestOps, readyOps, isValid và attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): read/write, EOF, half-close, close.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): accept và non-blocking registration.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): quản lý byte nhận/đợi gửi.
- [RFC 9293 — TCP](https://www.rfc-editor.org/rfc/rfc9293): TCP byte stream và trạng thái đóng kết nối.
