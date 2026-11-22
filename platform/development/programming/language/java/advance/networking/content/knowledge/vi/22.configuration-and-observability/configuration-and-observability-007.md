# Nhận diện EOF, connection reset, broken pipe và lỗi do đóng channel trong Java

Khi sử dụng Java Networking, một socket có vẻ “bị ngắt” chưa đủ để kết luận nguyên nhân. Cùng một đường truyền TCP có thể kết thúc **bình thường bằng FIN**, bị **abort bằng RST**, vẫn mở một chiều sau **half-close**, hoặc bị ứng dụng **đóng channel cục bộ** trong lúc thread khác đang đọc/ghi. Các trường hợp đó tạo ra giá trị trả về và exception khác nhau; nếu xử lý chung thành “mất mạng” sẽ dẫn tới retry sai, CPU spin, rò tài nguyên hoặc mất dữ liệu.

Bài Knowledge này thuộc **Java Advance - networking → Cấu hình và quan sát**, tập trung vào các dấu hiệu có thể kiểm chứng bằng **`Socket`**, **`SocketChannel`**, **`AsynchronousSocketChannel`**, stack trace, trạng thái Java và thông tin kết nối.

Các kết luận quan trọng:
- **`read() == -1`**: EOF, tức chiều đọc đã hết bytes theo contract. Thường do peer gửi TCP FIN, nhưng cũng có thể do **local `shutdownInput()`**.
- **`read() == 0`**: chưa chuyển bytes tại lần đọc (thường trên nonblocking channel hoặc buffer không còn chỗ); **không phải EOF**.
- **Connection reset**: TCP connection bị abort/RST. Trong Java thường thấy `SocketException`/`IOException` với message gợi ý `Connection reset`, nhưng class/message chính xác phụ thuộc hệ điều hành, provider và thời điểm đọc/ghi.
- **Broken pipe**: tên lỗi I/O thường thấy khi **ghi** vào một connection phía kia không còn nhận dữ liệu. Không có exception type Java chuẩn tên `BrokenPipeException`; thường hiện dưới `SocketException`.
- **`ClosedChannelException`**: I/O trên channel đã đóng **hoặc chiều đang thao tác đã shutdown**.
- **`AsynchronousCloseException`**: một thread đang blocked I/O, thread khác đóng channel/chiều liên quan.
- **`ClosedByInterruptException`**: thread bị interrupt trong blocked channel I/O; channel bị đóng và interrupt flag được đặt.

Hai điều không được suy diễn: **write thành công không chứng minh remote application đã xử lý bytes**, và **`channel.isOpen() == true` không chứng minh peer còn hoạt động**.

Bài có ba chương trình Java 17+ hoàn chỉnh, chỉ chạy trên `127.0.0.1`, không cần Internet: `GracefulEofDemo.java`, `ChannelClosureDemo.java` và `ResetProbeDemo.java`. Chương trình thứ ba **cố tình không assert exact OS error message** vì reset là hành vi phụ thuộc nền tảng.

## 1. FIN, RST và hai chiều độc lập của TCP

TCP là **byte stream hai chiều**. Khi máy chủ hoàn tất chiều gửi, nó có thể đóng riêng chiều output bằng `shutdownOutput()`. Máy khách đọc các bytes đã tới rồi thấy EOF, nhưng vẫn có thể gửi dữ liệu trong chiều còn lại.

~~~text
Client                                Server
   |                                     |
   |<--------------- hello --------------|
   |<---------------- FIN ---------------| server.shutdownOutput()
   |                                     |
client.read() nhận "hello"              |
client.read() => -1 (EOF)               |
   |                                     |
   |---------------- ack --------------->| server.read() vẫn nhận ack
   |---------------- FIN --------------->| client.shutdownOutput()
   |                                     |
   +-- client.close()       server.close()
~~~

**FIN** đánh dấu kết thúc **chiều gửi** của phía phát FIN; nó không tự kết thúc chiều ngược lại. Vì thế sau khi đọc `-1`, ứng dụng vẫn phải xem giao thức có yêu cầu gửi ACK/response hay không, thay vì đóng mọi thứ ngay.

**RST** là reset/abort connection. Nó khác với FIN: nó có thể gây lỗi I/O thay vì một EOF “đẹp”. Tuy nhiên message Java bạn thấy còn do kernel, socket provider, proxy, timing, dữ liệu đang chờ và thứ tự read/write quyết định; không được nhìn chữ “reset” rồi kết luận chắc chắn process server đã crash.

**Local close** lại là vấn đề khác. Ví dụ thread A gọi `channel.close()` thì thread B đang blocked read có thể nhận `AsynchronousCloseException`. Không cần peer gửi FIN/RST mới xảy ra lỗi này.

## 2. Bảng phân loại nhanh: kết quả đọc/ghi và exception

| Dấu hiệu | Operation thường thấy | Ý nghĩa có căn cứ | Điều không chứng minh |
| --- | --- | --- | --- |
| `read() == -1` | InputStream hoặc SocketChannel read | End-of-stream của chiều đọc | Không chứng minh toàn connection đã đóng |
| `read() > 0` | read | Đã nhận số bytes đó | Không chứng minh đã nhận nguyên message |
| `read() == 0` | nonblocking read hoặc buffer hết chỗ | Không chuyển bytes lúc này | Không chứng minh EOF/reset |
| `write() > 0` | SocketChannel write | Bytes được tiếp nhận ở bước write | Không chứng minh peer app đã commit |
| `write() == 0` | nonblocking SocketChannel write | Không ghi được bytes ở lần này | Không phải Broken pipe |
| `SocketException: Connection reset` | read hoặc write | Socket I/O bị lỗi, message gợi ý reset | Không chứng minh đích nào phát RST |
| `SocketException: Broken pipe` | write | Gợi ý đường gửi đã hỏng | Không phải exception class cố định |
| `ClosedChannelException` | NIO read/write | Channel/chiều I/O không còn mở | Không tự khẳng định lỗi remote |
| `AsynchronousCloseException` | blocked NIO read/write | Close từ thread khác khi đang block | Không phải async HTTP operation bình thường |
| `ClosedByInterruptException` | blocked NIO read/write | Interrupt đã đóng channel | Không có nghĩa remote đóng trước |
| `SocketTimeoutException` | connect/read có timeout | Hết hạn chờ theo operation | Không phải EOF |
| `ConnectException: Connection refused` | connect | Không kết nối được tới endpoint | Không phải một established connection vừa EOF |
| `NotYetConnectedException` | NIO read/write trước connect | Sai channel lifecycle | Không phải connection reset |
| `CancelledKeyException` | SelectionKey operations | Key không còn hợp lệ | Không tự nói gì về peer TCP |

Phân loại theo **operation + return value + exception class + trạng thái ứng dụng**, sau đó mới dùng OS error message để tăng ngữ cảnh. Không coi một đoạn text exception là một mã giao thức ổn định.

## 3. EOF: số -1 là end-of-stream, không phải data rỗng

Với `SocketChannel.read(ByteBuffer dst)`, số trả về được hiểu:
- **`n > 0`**: nhận được `n` bytes, có thể chỉ là mảnh đầu của message.
- **`n == 0`**: không nhận bytes vào buffer trong lần gọi. Khi nonblocking chưa có data, đây là kết quả bình thường. Khi `dst.remaining() == 0`, buffer cũng không có nơi chứa bytes.
- **`n == -1`**: reached end-of-stream (EOF), không có data mới trên chiều đọc.

Với `InputStream.read()` không tham số, **`0` là một byte giá trị NUL hợp lệ**, trong khi `-1` mới báo EOF. Đừng đánh đồng overload đọc một byte với `SocketChannel.read` trả số lượng bytes.

Ví dụ đọc đúng (snippet):

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8192);
while (true) {
    buffer.clear();
    int n = channel.read(buffer);

    if (n == -1) {
        onEof();                 // Đọc tới EOF.
        break;
    }
    if (n == 0) {
        // Với nonblocking: đợi Selector readiness,
        // KHÔNG spin vô hạn ở đây.
        continue;
    }

    buffer.flip();
    consumeBytes(buffer);        // Parser xử lý partial frame.
}
~~~

Đây là **snippet**, `channel/onEof/consumeBytes` cần được triển khai. Với blocking channel và buffer còn chỗ, read thông thường block chờ ít nhất một byte, EOF hoặc lỗi. Với nonblocking channel, phải điều phối qua `Selector.OP_READ` thay vì vòng `while(n == 0)` bận CPU.

### EOF khác với kết thúc message

TCP không gắn message boundaries. Một peer gửi 100 bytes có thể khiến client nhận 30, 50 rồi 20 bytes qua ba lần đọc. Nếu frame khai báo `Content-Length: 100` hoặc length-prefix 100 mà mới nhận 40 bytes đã EOF, đó là **truncated application message** dù TCP kết thúc bằng FIN bình thường.

Vì vậy app phải có một protocol framing rule:
- Length-prefix: đọc đủ byte count trước khi hoàn tất message.
- Delimiter: tích lũy tới delimiter; EOF trước delimiter có thể là lỗi.
- EOF-delimited: chính EOF là cách kết thúc body; áp giới hạn bytes để không nhận vô hạn.
- Fixed header/body: parse từng state, chỉ chuyển state khi bytes đủ.

**Đừng đổi mọi EOF thành success**. Một request có EOF ở thời điểm không mong đợi cần báo `UNEXPECTED_EOF/TRUNCATED_FRAME` theo giao thức.

## 4. shutdownOutput và shutdownInput không giống close

`SocketChannel.shutdownOutput()` đóng nửa **gửi**. Theo Java 17, những lần `write` tiếp theo ném `ClosedChannelException`; chiều đọc còn có thể tiếp tục.

~~~java
channel.shutdownOutput();
boolean open = channel.isOpen(); // Vẫn có thể true.
// channel.write(...) sau đây sẽ không được phép.
~~~

`SocketChannel.shutdownInput()` đóng nửa **nhận**, khiến những lần đọc tiếp theo trả `-1` theo contract:

~~~java
channel.shutdownInput();
int n = channel.read(ByteBuffer.allocate(8)); // EOF: -1.
~~~

**Đặc biệt:** `read()==-1` có thể đến từ **chính local `shutdownInput`**, không nhất thiết remote FIN. Nếu cần điều tra, log local lifecycle events chứ không chỉ log EOF.

`close()` đóng toàn channel và không cho I/O mới. `shutdownOutput()`, `shutdownInput()` có thể để lại một nửa connection; không nên áp dụng khi application protocol không cho half-close.

| Thao tác | Tác dụng | Ghi chú |
| --- | --- | --- |
| `shutdownOutput()` | Dừng gửi; báo peer rằng đã hết bytes gửi theo TCP | Có thể tiếp tục đọc |
| `shutdownInput()` | Dừng nhận local; read tiếp theo trả EOF | Không chứng minh remote chủ động đóng |
| `close()` | Đóng channel toàn bộ | Không thể mở lại cùng object |
| Peer gửi FIN | Kết thúc chiều peer→local | Chiều local→peer có thể vẫn gửi |
| Peer gửi RST | Kết nối bị abort | Read/write có thể báo IOException |

## 5. Ví dụ chạy được 1 — EOF nhưng vẫn gửi được chiều ngược lại

**`GracefulEofDemo.java`** cho server gửi `hello` rồi `shutdownOutput()`. Client đọc đến EOF, thấy channel vẫn mở, gửi `ack`. Server đọc được `ack` trước khi client shutdown chiều gửi. Đây là minh họa trực tiếp rằng **EOF không đồng nghĩa full close**.

Tạo file **`GracefulEofDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class GracefulEofDemo {
    static String readAll(SocketChannel ch) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteBuffer buffer = ByteBuffer.allocate(4);

        while (true) {
            buffer.clear();
            int n = ch.read(buffer);
            if (n == -1) break;
            if (n == 0) continue;

            buffer.flip();
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            out.write(bytes);
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    static void writeAll(SocketChannel ch, String text)
            throws IOException {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(text);
        while (buffer.hasRemaining()) {
            ch.write(buffer);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            Future<String> serverResult = worker.submit(() -> {
                try (SocketChannel peer = listener.accept()) {
                    writeAll(peer, "hello");
                    peer.shutdownOutput();
                    return readAll(peer);
                }
            });

            try (SocketChannel client =
                    SocketChannel.open(listener.getLocalAddress())) {
                String received = readAll(client);
                System.out.println("Client received: " + received);
                System.out.println("Peer EOF after FIN: "
                        + received.equals("hello"));
                System.out.println("Channel still open: "
                        + client.isOpen());

                writeAll(client, "ack");
                client.shutdownOutput();
                System.out.println(
                        "Server read after peer half-close: "
                        + serverResult.get(3, TimeUnit.SECONDS));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 GracefulEofDemo.java
java GracefulEofDemo
~~~

**Kết quả đã kiểm thử trên localhost:**

~~~text
Client received: hello
Peer EOF after FIN: true
Channel still open: true
Server read after peer half-close: ack
~~~

**Giải thích:**
1. Server ghi toàn bộ bytes rồi `shutdownOutput`, nên client sẽ có EOF khi đã đọc hết `hello`.
2. Channel client vẫn mở vì bản thân client chưa gọi `close()`.
3. Client vẫn gửi `ack`, server còn đọc được phía chiều ngược.
4. Chương trình sử dụng buffer 4 bytes nên phải gom chunks để tạo String. Đây là **test nhỏ**; với dữ liệu lớn cần bounded parsing, không đọc vô hạn vào `ByteArrayOutputStream`.
5. Các `Future.get(3,SECONDS)` chỉ bảo vệ thời gian chờ của phép thử; chúng không tự tạo total TCP deadline cho mọi thao tác blocking.

## 6. Connection reset: TCP RST khác FIN

**RST** là dạng TCP abort/reset. Java không có exception class chuẩn tên `ConnectionResetException`. Trên nhiều nền tảng, thao tác `read/write` có thể ném:

~~~text
java.net.SocketException: Connection reset
java.net.SocketException: Connection reset by peer
java.io.IOException: An existing connection was forcibly closed ...
~~~

Các chuỗi này là **ví dụ** từ những môi trường khác nhau, không phải output bắt buộc Java 17. Có nhiều nguồn gây reset:
- Peer đóng socket theo kiểu abortive, có thể do `SO_LINGER=0`.
- Process hoặc proxy đóng connection bất thường.
- Load balancer, middlebox, firewall hoặc OS hủy connection theo chính sách.
- Giao thức bị lỗi hoặc TCP state không còn hợp lệ.
- Remote process crash là **một khả năng**, không phải kết luận duy nhất.

RST có thể được phát hiện khi **đọc** hoặc khi **ghi**, và một số bytes đã được chấp nhận/gửi trước lúc exception xuất hiện. Không suy luận rằng server chắc chắn chưa xử lý request.

**Làm gì sau reset?** Dừng sử dụng socket/channel đó, cleanup connection state, ghi lớp exception, operation, bytes/phase và thời điểm. Nếu cần retry, tạo connection mới và áp chính sách idempotency, retry budget và backoff. Đừng retry mù quáng một giao dịch có side effects.

## 7. Broken pipe: thường xuất hiện ở chiều ghi

`Broken pipe` thường là message gắn với lỗi OS như `EPIPE` khi **ghi vào đường truyền không còn khả dụng**. Java thường lộ lỗi này dưới `SocketException` hoặc `IOException` chứ không có một checked exception type đặc biệt tên `BrokenPipeException`.

Những điều cần tránh suy diễn:
- Sau **FIN** từ peer, nó chỉ dừng **gửi**; peer có thể vẫn nhận data. Ghi sau FIN **không nhất thiết** broken pipe.
- Nếu peer đã full-close hoặc RST, các lần ghi tiếp có thể lỗi. OS có thể trả `Connection reset` hoặc `Broken pipe` tùy thời điểm.
- Một lời gọi `write` đầu tiên có thể thành công vì local kernel đã nhận bytes; lỗi mới xuất hiện ở lần read/write sau.
- Nếu bạn **tự** gọi `SocketChannel.shutdownOutput()`, lần write tiếp có thể là `ClosedChannelException` dù `isOpen()==true`.
- Nếu bạn **tự** gọi `SocketChannel.close()`, lần write tiếp thường báo `ClosedChannelException`, không có lý do gán lỗi cho peer.

**Không retry write trên cùng channel đã hỏng.** Với TCP stream, một channel lỗi không tự phục hồi. Hãy tạo connection mới nếu nghiệp vụ được phép, đồng thời nhớ **write success không phải application acknowledgment**.

## 8. Cây ClosedChannelException trong Java NIO

Từ Javadoc Java 17:

~~~text
IOException
└── ClosedChannelException
    └── AsynchronousCloseException
        └── ClosedByInterruptException
~~~

Ba class quan trọng có quan hệ kế thừa như trên, nên **thứ tự catch** phải từ subtype cụ thể tới superclass.

~~~java
try {
    channel.read(buffer);
} catch (ClosedByInterruptException ex) {
    // Thread đang blocked I/O bị interrupt, channel đã đóng.
    Thread.currentThread().interrupt();
} catch (AsynchronousCloseException ex) {
    // Thread khác đóng channel/chiều đang block.
} catch (ClosedChannelException ex) {
    // Channel hoặc chiều I/O đã đóng trước thao tác.
} catch (IOException ex) {
    // Các lỗi network/transport khác.
}
~~~

Đây là snippet: `channel`/`buffer` chưa được khai báo. Nếu bắt `ClosedChannelException` trước, các catch cụ thể theo sau là unreachable.

### 8.1. ClosedChannelException

Không đồng nghĩa channel đã *hoàn toàn* đóng. Javadoc ghi rõ I/O trên channel đã đóng **hoặc ít nhất chiều đang thao tác không còn mở** có thể ném class này. Ví dụ `shutdownOutput` rồi `write` nhưng `read` vẫn được.

### 8.2. AsynchronousCloseException

Nếu thread A đang blocked trong `SocketChannel.read()`, thread B gọi `channel.close()`, thao tác đang block có thể kết thúc bằng `AsynchronousCloseException`. Đây là lỗi **lifecycle đồng thời**, không phải bằng chứng remote reset.

### 8.3. ClosedByInterruptException

Nếu thread A bị `interrupt()` khi đang blocked channel I/O, JDK đóng channel, đặt interrupt flag, rồi ném `ClosedByInterruptException`. Không được xem nó như một `InterruptedException` chung mà bỏ qua channel state; **không tái sử dụng channel này**.

### 8.4. isOpen() không phải remote health check

`isOpen()` chỉ cho biết object channel chưa close toàn bộ. Peer có thể đã gửi FIN, RST chưa được xử lý hoặc channel local đã shutdown một chiều. Chỉ application protocol, heartbeat, read/write thật, metadata và acknowledgment phù hợp mới giúp đánh giá trạng thái remote.

## 9. Ví dụ chạy được 2 — đóng local, close từ thread khác và interrupt

Chương trình **`ChannelClosureDemo.java`** minh họa:
1. `shutdownOutput()` làm write báo `ClosedChannelException` nhưng channel vẫn mở.
2. `close()` toàn channel khiến read mới báo `ClosedChannelException`.
3. Một thread đang blocked trong `read()`, thread khác close channel: `AsynchronousCloseException`.
4. Interrupt thread đang blocked read: `ClosedByInterruptException`, interrupt flag true, channel đóng.

Tạo file **`ChannelClosureDemo.java`**:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousCloseException;
import java.nio.channels.ClosedByInterruptException;
import java.nio.channels.ClosedChannelException;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ChannelClosureDemo {
    static void localCloseAndHalfClose() throws Exception {
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            try (SocketChannel client =
                         SocketChannel.open(listener.getLocalAddress());
                 SocketChannel peer = listener.accept()) {
                client.shutdownOutput();

                boolean halfClosed = false;
                try {
                    client.write(ByteBuffer.wrap(new byte[]{1}));
                } catch (ClosedChannelException expected) {
                    halfClosed = true;
                }
                System.out.println(
                        "Write after shutdownOutput: " + halfClosed);
                System.out.println(
                        "Open after shutdownOutput: " + client.isOpen());

                client.close();
                boolean closedRead = false;
                try {
                    client.read(ByteBuffer.allocate(1));
                } catch (ClosedChannelException expected) {
                    closedRead = true;
                }
                System.out.println("Read after close: " + closedRead);
            }
        }
    }

    static void blockedRead(boolean interrupt) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));

            try (SocketChannel client =
                         SocketChannel.open(listener.getLocalAddress());
                 SocketChannel peer = listener.accept()) {

                CountDownLatch started = new CountDownLatch(1);
                AtomicReference<Thread> readerThread =
                        new AtomicReference<>();

                Future<String> result = worker.submit(() -> {
                    readerThread.set(Thread.currentThread());
                    started.countDown();
                    try {
                        int n = client.read(ByteBuffer.allocate(1));
                        return "read=" + n;
                    } catch (ClosedByInterruptException ex) {
                        return "ClosedByInterruptException|interrupt="
                                + Thread.currentThread().isInterrupted();
                    } catch (AsynchronousCloseException ex) {
                        return "AsynchronousCloseException";
                    } catch (IOException ex) {
                        return ex.getClass().getSimpleName();
                    }
                });

                if (!started.await(3, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Reader not started");
                }
                Thread.sleep(100); // Tạo điều kiện read đang block.

                if (interrupt) {
                    readerThread.get().interrupt();
                } else {
                    client.close();
                }

                String observed = result.get(3, TimeUnit.SECONDS);
                System.out.println(
                        (interrupt ? "Interrupt blocked read: "
                                   : "Close blocked read: ") + observed);
                System.out.println(
                        "Channel open afterward: " + client.isOpen());
            }
        } finally {
            worker.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        localCloseAndHalfClose();
        blockedRead(false);
        blockedRead(true);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ChannelClosureDemo.java
java ChannelClosureDemo
~~~

**Stdout đã kiểm thử trên JDK với blocking NIO SocketChannel:**

~~~text
Write after shutdownOutput: true
Open after shutdownOutput: true
Read after close: true
Close blocked read: AsynchronousCloseException
Channel open afterward: false
Interrupt blocked read: ClosedByInterruptException|interrupt=true
Channel open afterward: false
~~~

**Ý nghĩa:** Đây là các hiệu ứng close/interrupt **cục bộ**, không phải remote RST. Phần `Thread.sleep(100)` chỉ giúp worker đi vào blocked read; trên máy scheduler cực bất thường có thể có race trước khi read thực sự block. Do đó nếu timing khác thì phải xem exception thực tế và vẫn dựa trên Javadoc contract, thay vì hard-code output mọi môi trường.

Nếu service đang shutdown, `AsynchronousCloseException` có thể là sự kiện dự kiến. Ghi `closeReason=shutdown` để tránh gọi mọi close trong lúc dừng là incident.

## 10. Dùng SO_LINGER(0) quan sát reset, không dùng để chữa lỗi

Một peer có thể bật `Socket.setSoLinger(true, 0)` rồi close để yêu cầu abortive close. Nhiều OS sẽ gửi TCP RST, nhưng timing/message từ socket API không được đảm bảo giống hệt nhau trên mọi hệ thống.

**Chỉ dùng kỹ thuật này trong localhost test**. Đặt SO_LINGER=0 trong production không phải cách “sửa Broken pipe”, vì nó có thể làm mất dữ liệu chưa truyền/đang nhận và gây reset cho peer.

## 11. Ví dụ chạy được 3 — quan sát reset theo OS

Tạo file **`ResetProbeDemo.java`**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ResetProbeDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            Future<?> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoLinger(true, 0);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });

            try (Socket client = new Socket(
                    "127.0.0.1", listener.getLocalPort())) {
                server.get(3, TimeUnit.SECONDS);
                try {
                    int value = client.getInputStream().read();
                    System.out.println(
                            "Observed read result: " + value);
                } catch (IOException error) {
                    System.out.println("Observed read exception: "
                            + error.getClass().getSimpleName());
                    System.out.println(
                            "OS message: " + error.getMessage());
                }
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ResetProbeDemo.java
java ResetProbeDemo
~~~

**Một kết quả quan sát trên máy kiểm thử Windows/JDK:**

~~~text
Observed read exception: SocketException
OS message: Connection reset
~~~

**Không assert stdout này trên mọi OS.** Trong các điều kiện khác, message/class hoặc kết quả có thể khác. Chương trình chủ động in sự kiện đã quan sát. Nếu muốn phân biệt TCP FIN/RST thật sự trên wire, dùng packet capture/OS TCP counters trong môi trường được phép và đối chiếu hai phía.

**Vì sao không làm một demo Broken pipe luôn in đúng chữ đó?** Trên một số OS, lần ghi sau remote shutdown có thể trả `Connection reset`; trên OS khác, có thể chấp nhận write rồi mới lỗi lần sau hoặc báo `Broken pipe`. Gán một stdout cố định sẽ dạy sai rằng message này là API contract Java.

## 12. Phân loại local close bằng instanceof thay vì OS message

Nếu cần phân biệt chắc chắn nhóm lỗi **local NIO channel lifecycle**, dùng exception hierarchy:

~~~java
static String classify(IOException e) {
    if (e instanceof ClosedByInterruptException) {
        return "LOCAL_INTERRUPT";
    }
    if (e instanceof AsynchronousCloseException) {
        return "LOCAL_CONCURRENT_CLOSE";
    }
    if (e instanceof ClosedChannelException) {
        return "LOCAL_CHANNEL_CLOSED_OR_HALF_CLOSED";
    }
    if (e instanceof SocketTimeoutException) {
        return "TIMEOUT";
    }
    if (e instanceof SocketException) {
        return "SOCKET_ERROR_NEEDS_MORE_CONTEXT";
    }
    return "OTHER_IO_ERROR";
}
~~~

Đây là snippet, cần imports `java.io.IOException`, `java.net.SocketException`/`SocketTimeoutException` và `java.nio.channels.*`.

**Không viết logic nghiệp vụ kiểu:**

~~~java
// PHẢN VÍ DỤ: error message có thể null, không portable.
if (error.getMessage().contains("Broken pipe")) {
    retryPaymentImmediately();
}
~~~

Ngoài message không ổn định, retry thanh toán có thể tạo double-processing. Thay vào đó phân loại bằng `operation`, `exception class`, `application request ID`, `bytes transferred` và idempotency policy.

EOF là **return value** `-1`, không phải `IOException` nên không thuộc helper trên.

## 13. Selector và nonblocking SocketChannel

Trong `SocketChannel.configureBlocking(false)`:
- `read()==0` khi chưa có bytes sẵn là bình thường.
- Khi peer đã kết thúc chiều gửi, readiness có thể xuất hiện liên tục; read trả `-1`.
- Nếu không xử lý EOF bằng chuyển state/cancel key, selector loop có thể bận CPU mãi.
- `SelectionKey.OP_READ` không tự mang thông tin “peer FIN”; phải gọi `read` để xác định.
- `CancelledKeyException` là lỗi selection key lifecycle; `ClosedSelectorException` là selector đã đóng, không phải TCP reset.

Một snippet xử lý một event:

~~~java
try {
    int n = channel.read(buffer);

    if (n == -1) {
        key.cancel();
        channel.close(); // Chỉ nếu protocol không cần half-close.
        return;
    }
    if (n == 0) {
        return;           // Nhường event loop, không spin.
    }

    buffer.flip();
    parseAvailableBytes(buffer);
    buffer.compact();
} catch (IOException ex) {
    key.cancel();
    channel.close();
    recordTransportFailure(ex);
}
~~~

Snippet này giả định `channel/key/buffer` hợp lệ và helpers được định nghĩa. Với protocol cần gửi response sau khi nhận FIN, phải quản lý **half-close state** thay vì close toàn channel tại EOF.

**Đừng xoá buffer chưa parse xong:** TCP có thể trả partial frame. Dùng `flip/compact` đúng để giữ bytes còn dư cho lần đọc sau.

## 14. AsynchronousSocketChannel: completed(-1) và failed(Throwable)

Với `AsynchronousSocketChannel`, API Future hoặc `CompletionHandler` biểu diễn I/O completion.

~~~java
channel.read(buffer, null,
        new CompletionHandler<Integer, Void>() {
            @Override
            public void completed(Integer n, Void unused) {
                if (n == -1) {
                    onEof();
                    return;
                }
                if (n == 0) {
                    // Không phải EOF, quản lý re-arm theo state.
                    return;
                }
                onBytes(n);
            }

            @Override
            public void failed(Throwable error, Void unused) {
                recordFailure(error);
            }
        });
~~~

Đây là snippet; `channel/buffer/onEof/onBytes/recordFailure` cần định nghĩa, không tự hoàn tất một parser đầy đủ. **`completed(-1)` khác với `failed(IOException)`**. Khi dùng `Future<Integer>`, exceptional completion thường hiển thị qua `ExecutionException` của `get()`; xem `getCause()` để biết exception thực.

Đừng suy diễn rằng interrupt một thread bất kỳ sẽ hủy đúng một async read operation đã submit. Với async channels, cần quản lý Future, `CompletionHandler.failed`, channel close và completion ownership.

Theo Javadoc `AsynchronousSocketChannel.shutdownInput()`, các **lần read sau** khi shutdown input sẽ thấy EOF; còn **tác động lên một read đang pending là system dependent**. Nếu đọc có timeout, `InterruptedByTimeoutException` có thể xuất hiện; khi provider không chắc buffer sẽ không bị chạm tới, tiếp tục dùng channel/buffer phải tuân thủ hạn chế trong contract.

## 15. Logging: thông tin nào giúp xác định nguồn lỗi?

Khi vận hành, hãy ghi một sự kiện có đủ ngữ cảnh:

~~~text
time=2026-11-01T09:00:00Z
connectionId=conn-381
requestId=req-19
operation=read
phase=response-body
remote=api.example:443
local=service-host:ephemeral-port
blockingMode=true
bytesReceived=4096
expectedFrameBytes=8192
exceptionClass=java.net.SocketException
exceptionMessage="Connection reset"
lastLocalCloseReason=none
retryAttempt=0
~~~

Đây là **mẫu log minh họa**, không phải kết quả chạy demo hay log thật. Không đưa bearer token, cookie, password, dữ liệu nhạy cảm vào log. Địa chỉ và request identifiers cũng phải tuân thủ quyền truy cập telemetry.

Các trường hữu ích:
- Direction: connect/read/write, đang ở request hay response.
- Exception **class** + root cause + message.
- Local close/interrupt/shutdown history.
- Bytes read/written và protocol frame progress.
- Local/remote address ghi trước khi channel bị đóng (sau close, query address có thể fail).
- Connection ID, request ID, endpoint, retry attempt.
- OS/JDK/provider/version và thời điểm deploy.
- Có FIN/RST thật trong packet capture hoặc counters không, nếu được phép quan sát.

**Không kết luận remote cause chỉ từ client log.** Kết hợp server logs, proxy/load balancer, firewall, OS telemetry và packet captures (khi có quyền). Một broken pipe tại server có thể do client bỏ response khi timeout, không nhất thiết server làm sai business processing.

## 16. Phân biệt transport error và lỗi giao thức ứng dụng

Một vài ví dụ:
- Client chờ 100 bytes, nhận 40 bytes rồi EOF → **truncated frame** ở application protocol.
- Server gửi response đầy đủ, client đóng chiều gửi bằng FIN → có thể thành công.
- Server đang ghi response, client timeout rồi close → server có thể gặp broken pipe/reset, còn database transaction có thể đã commit.
- Bên đọc bị thread quản lý đóng khi shutdown → `AsynchronousCloseException`, **expected cancellation** nếu design dự kiến.
- Thread worker bị `interrupt()` do cancellation → `ClosedByInterruptException`, không nên tự quy lỗi cho remote.
- TCP RST trước khi trả response cho POST → chưa biết POST có thực thi hay không, cần idempotency key/status endpoint.

**Giao thức ứng dụng phải quyết định thành công hay thất bại.** Một lần `SocketChannel.write()==n` chỉ xác nhận số bytes accepted ở bước write; không phải chứng nhận người nhận đã parse, validate, lưu database hay trả ACK nghiệp vụ.

## 17. Timeout, retry và idempotency

| Sự kiện | Cách ứng xử thường phù hợp |
| --- | --- |
| EOF đúng cuối message | Kết thúc reader/half-close theo protocol |
| EOF giữa message | Báo lỗi truncated, không parse partial như message đầy đủ |
| Reset trong read của GET idempotent | Cleanup, retry có giới hạn/backoff nếu deadline còn |
| Broken pipe khi đang gửi POST | Không kết luận request chưa tới server; cần idempotency key/status query |
| ClosedChannelException do local close | Sửa lifecycle/race; tạo channel mới nếu policy cần |
| AsynchronousCloseException do shutdown | Cleanup như cancellation có chủ đích |
| ClosedByInterruptException do cancel | Giữ interrupt state; không reuse channel |
| SocketTimeoutException | Phân loại timeout, không coi là EOF; retry theo operation/contract |
| Connect refused | Backoff/new connection, kiểm tra service/port; không phải established peer reset |

**Không retry trên channel đã đóng/hỏng.** Tạo connection mới nếu có quyền retry. Với thao tác có side effects, nếu server đã xử lý nhưng response mất, retry có thể tạo dữ liệu/giao dịch trùng. Dùng idempotency key, request ID, reconciliation/status query khi API hỗ trợ.

Có thể áp exponential backoff + jitter, giới hạn số lần retry, tổng deadline, concurrency và circuit breaker. Không biến reset storm thành retry storm.

## 18. Cleanup và một chủ sở hữu lifecycle

Khi nhiều threads dùng chung một channel, một thread đóng tài nguyên trong khi thread khác đang đọc có thể tạo exception “bất ngờ”. Thiết kế nên có state machine và close owner rõ ràng:

~~~text
NEW -> CONNECTING -> OPEN
                       |
             +---------+---------+
             |                   |
       HALF_CLOSED_IN      HALF_CLOSED_OUT
             |                   |
             +---------+---------+
                       |
                    CLOSING
                       |
                     CLOSED
~~~

Đây là **mô hình app**, không phải enum Java mặc định. Lưu close reason trước khi đóng (`normal EOF`, `shutdown`, `timeout`, `protocol violation`, `peer failure`), để callbacks/logs phân biệt expected/unexpected.

Khuyến nghị:
- Dùng try-with-resources khi sở hữu `Socket/SocketChannel/ServerSocketChannel`.
- Không cho nhiều owners tùy ý gọi `close` và tiếp tục ghi trên connection đó.
- Dừng queue gửi, kết thúc Futures/pending writes với error rõ ràng.
- Với Selector, cancel/deregister key và dọn map connection.
- Với async channel, phối hợp completion handlers và close, không để stale ByteBuffer bị ghi lại.
- Không log stack trace hàng nghìn lần cho expected shutdown.
- Khi gặp reset/broken pipe, đóng/deregister và tạo connection mới theo retry policy; không giữ channel bị lỗi trong pool.

## 19. Sổ tay chẩn đoán sự cố

Khi thấy lỗi:
1. **Xác định thao tác:** connect, read, write, selector, close hay callback.
2. **Đọc return value:** `-1`, `0` hay positive bytes; đừng bỏ qua số bytes nhận trước lỗi.
3. **Phân loại exception:** class trước, cause chain sau, message cuối.
4. **Tìm local close event:** thread khác gọi close? Có shutdownInput/Output, interrupt, cancellation hay timeout?
5. **Đối chiếu protocol state:** EOF có đúng sau khi đủ bytes/frame hay xảy ra giữa message?
6. **Đối chiếu peer:** logs server/proxy/LB với connection ID/timestamp.
7. **Kiểm tra chứng cứ TCP:** Nếu cần và được phép, dùng packet capture để xác nhận FIN/RST thay vì đoán từ message.
8. **Tính đến side effects:** DB transaction, request commit, ứng dụng peer có thể đã xử lý dù client không nhận được response.
9. **Cleanup:** key/channel/streams/futures theo ownership, tránh double close side effects hoặc retry trên channel cũ.
10. **Cải thiện metrics:** EOF expected/unexpected, reset-per-operation, local-close reasons, latency, queue depths, retry attempts và bytes transferred.

Không dựa vào duy nhất `isOpen`, `SocketException.getMessage` hoặc thời điểm một thread bị unblock để khẳng định root cause.

## 20. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `read()==0` là EOF | Đóng nonblocking socket quá sớm | Chỉ `-1` là end-of-stream |
| Coi EOF là full close | Mất khả năng gửi phản hồi cuối | Quản lý half-close |
| Không kiểm tra framing khi EOF | Nhận message dở | Validate length/delimiter |
| Tin một `read` sẽ nhận cả message | Parse sai TCP stream | Loop/tích lũy ByteBuffer |
| Spin khi nonblocking read trả 0 | CPU cao | Selector readiness/event loop |
| Gọi write sau `shutdownOutput()` | ClosedChannelException | Không dùng chiều ghi đã đóng |
| Dùng `isOpen()` làm remote health check | Bỏ sót FIN/RST | App heartbeat/real I/O |
| Coi `Broken pipe` là Java exception type | Không compile/catch sai | Bắt IOException/SocketException |
| Hardcode `"Connection reset"` message | Không portable | Class + OS metadata |
| Gán mọi `ClosedChannelException` cho remote | Chẩn đoán sai race local | Truy vết local shutdown/close |
| Catch `ClosedChannelException` trước subtype | Catch subtype unreachable | Catch specific trước |
| Bị interrupt rồi reuse SocketChannel | I/O trên closed channel | Tạo channel mới, giữ interrupt flag |
| Coi write success là business success | Double-processing/retry sai | Acknowledgment/idempotency |
| Retry ngay mọi Broken pipe khi POST | Có thể xử lý trùng | Idempotency keys/status lookup |
| SO_LINGER=0 để “dọn nhanh” | RST/mất bytes | Graceful close theo protocol |
| Quên cancel SelectionKey sau EOF | Selector busy loop | Hủy key hoặc state change |
| Quên đóng stream/future | Resource leak | Terminal cleanup |
| Nuốt mọi IOException thành null | Mất nguyên nhân | Preserve cause/context |
| Không phân biệt timeout vs EOF | Logic sai | Timeout là exception riêng |
| Log raw secrets/payload | Rò dữ liệu | Redact/sanitize logs |

## 21. Bài tập tự kiểm tra

**1.** `SocketChannel.read(ByteBuffer)` trả `-1` biểu thị gì?  
**Đáp án:** End-of-stream chiều đọc; thường do peer FIN, nhưng local shutdownInput cũng tạo EOF.

**2.** Nonblocking read trả `0` có phải kết nối đã đóng?  
**Đáp án:** Không. Lần này chưa chuyển bytes; cần đợi readiness hoặc xem buffer.

**3.** Sau khi client đọc EOF từ peer, client còn write được không?  
**Đáp án:** Có thể, vì peer mới đóng chiều gửi; chiều client gửi còn có thể hợp lệ.

**4.** `InputStream.read()` trả `0` có nghĩa không có bytes?  
**Đáp án:** Không; với overload đọc một byte, 0 là byte NUL, -1 mới EOF.

**5.** EOF sau 40 bytes của frame khai báo 100 bytes có phải thành công?  
**Đáp án:** Không. Đây là truncated application frame.

**6.** `Connection reset` có chứng minh remote server crash?  
**Đáp án:** Không. RST có thể liên quan OS, proxy, middlebox, abortive close hoặc lỗi khác.

**7.** `Broken pipe` có phải class riêng trong Java 17?  
**Đáp án:** Không; thường là OS message đi kèm SocketException/IOException ở write.

**8.** Vì sao write sau `shutdownOutput()` báo ClosedChannelException nhưng isOpen vẫn true?  
**Đáp án:** Vì một chiều I/O có thể shutdown mà toàn channel chưa close.

**9.** `AsynchronousCloseException` khác `ClosedByInterruptException` thế nào?  
**Đáp án:** Một do thread khác đóng blocked channel; một do chính blocked thread bị interrupt, channel đóng và interrupt flag set.

**10.** Thứ tự catch ba local exceptions?  
**Đáp án:** ClosedByInterruptException → AsynchronousCloseException → ClosedChannelException.

**11.** Việc `SocketChannel.write()==100` có chứng minh server đã commit DB không?  
**Đáp án:** Không. Cần protocol/application acknowledgment hoặc status query.

**12.** Vì sao không assert mọi OS đều in `"Broken pipe"` sau remote close?  
**Đáp án:** Lỗi và message phụ thuộc timing, TCP state, OS/provider.

**13.** SO_LINGER=0 có nên dùng làm close mặc định?  
**Đáp án:** Không. Có thể tạo abortive close/RST, mất dữ liệu.

**14.** Selector xử lý EOF sai có thể gây CPU cao vì sao?  
**Đáp án:** Read readiness có thể lặp khi EOF, phải cancel/deregister/đổi state.

**15.** `AsynchronousSocketChannel.completed(-1)` và `failed(IOException)` có giống nhau không?  
**Đáp án:** Không. Một là EOF result, một là I/O failure.

**16.** Khi thấy ClosedChannelException lúc service đang shutdown, nên kiểm tra gì?  
**Đáp án:** Local owner/close reason, thread/cancel lifecycle và operation còn pending trước khi quy trách remote.

**17.** `SocketTimeoutException` có phải EOF?  
**Đáp án:** Không. Timeout là không có bytes trong thời hạn, không chứng minh kết nối đóng.

**18.** Vì sao retry POST sau reset có thể nguy hiểm?  
**Đáp án:** Remote có thể đã xử lý request nhưng response thất lạc; cần idempotency.

## 22. Tài liệu tham khảo chính thức Java SE 17

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): read -1/0, shutdownInput/Output, local close và I/O exceptions.
- [Channel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Channel.html): isOpen/close và lifecycle.
- [ClosedChannelException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedChannelException.html): I/O trên channel hoặc chiều đã đóng.
- [AsynchronousCloseException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): blocked I/O bị đóng từ thread khác.
- [ClosedByInterruptException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ClosedByInterruptException.html): interrupt blocked I/O đóng channel.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future/CompletionHandler EOF và failure/timeout.
- [Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): shutdownInput/Output, setSoLinger, close.
- [SocketException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketException.html): socket I/O errors.
- [SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): I/O timeout semantics.
- [StandardSocketOptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): SO_LINGER, SO_KEEPALIVE, TCP_NODELAY.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): readiness and selection keys.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): EOF return value -1.
