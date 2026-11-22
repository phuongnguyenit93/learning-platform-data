# AsynchronousSocketChannel và vòng đời kết nối trong Java NIO.2

**Chủ đề:** Java 7 — Kênh mạng bất đồng bộ  
**Bài học:** AsynchronousSocketChannel và vòng đời kết nối  
**Phạm vi:** Java 17+ với `java.nio.channels.AsynchronousSocketChannel`, `AsynchronousServerSocketChannel`, `AsynchronousChannelGroup`, `Future`, `CompletionHandler` và `ByteBuffer`. Các API này được giới thiệu từ Java 7, vẫn được Java hiện đại duy trì. Ví dụ sử dụng **loopback và cổng do hệ điều hành chọn**, không đòi hỏi máy chủ Internet hay thư viện bên ngoài.

## 1. Vai trò của AsynchronousSocketChannel

`AsynchronousSocketChannel` là API NIO.2 dành cho **socket TCP dạng luồng** có các thao tác kết nối, đọc và ghi với **kết quả bất đồng bộ**. Thay vì một lời gọi `connect` hoặc `read` luôn chờ đến khi hoàn tất mới trả về, ứng dụng có thể:

- Gọi `connect(remote)` và nhận `Future<Void>`; hoặc truyền `CompletionHandler<Void,A>` để nhận thông báo sau.
- Gọi `read(ByteBuffer)` / `write(ByteBuffer)` và nhận `Future<Integer>`; hoặc dùng callback để nhận số byte và lỗi.
- Xử lý các request khác, giám sát deadlines hoặc lập lịch công việc trong thời gian I/O chưa hoàn thành.
- Duy trì nhiều connections đồng thời mà không buộc mỗi câu lệnh của thread khởi tạo chờ tới khi I/O hoàn tất.

**Điều cần nhớ:** “asynchronous” ở đây mô tả **cách ứng dụng được thông báo khi I/O hoàn tất**. Nó không cam kết không có bất kỳ worker thread nào chờ bên dưới, không cam kết nhanh hơn ở mọi tải và **không tự cấp framing, retries, TLS hay exactly-once delivery**.

Đối tượng `AsynchronousSocketChannel` tương ứng với **một endpoint socket**, không phải một message. Socket TCP gửi và nhận **các byte liên tiếp**; một lần `write` của ứng dụng **không tương ứng chắc chắn** với đúng một lần `read` của peer.

### 1.1. Ba vai trò khi dùng API

| Thành phần | Vai trò |
| --- | --- |
| `AsynchronousServerSocketChannel` | Bind/listen và **accept** các kết nối đến theo cơ chế bất đồng bộ |
| `AsynchronousSocketChannel` | Client-side `open/connect` hoặc server-side channel nhận từ `accept`; đọc/ghi và quản lý kết nối |
| `AsynchronousChannelGroup` | Nhóm channels chia sẻ hạ tầng dispatch completion/threads, có vòng đời và shutdown riêng |
| `Future<T>` | Theo dõi/đợi kết quả một operation cụ thể |
| `CompletionHandler<V,A>` | Callback nhận `completed` hoặc `failed`, cùng attachment do ứng dụng cấp |
| `ByteBuffer` | Vùng byte do ứng dụng sở hữu, nơi dữ liệu đọc/ghi được đặt vào/lấy ra |

Không nhầm `AsynchronousSocketChannel` với `AsynchronousFileChannel`: socket là **stream network** không có “file position” và không nhận tham số offset cho mỗi lần đọc. File channel bất đồng bộ làm việc với các **vị trí byte trong tệp**, còn socket channel làm việc với **luồng bytes theo thứ tự TCP**.

## 2. Sơ đồ vòng đời

Một client channel mới có trạng thái **open nhưng chưa connected**. Sau khi `connect` thành công, có thể đọc và ghi; cuối phiên có thể half-close một chiều rồi `close` hoàn toàn.

```text
             AsynchronousSocketChannel.open()
                              |
                              v
                  OPEN, NOT CONNECTED
                              |
                      connect(remote)
                              |
                +-------------+------------+
                |                          |
          connect success              connect failure
                |                          |
                v                          v
           CONNECTED                 CLOSED / failed
                |
       +--------+---------+
       |                  |
    read(...)           write(...)
       |                  |
       +--------+---------+
                |
         tùy giao thức ứng dụng:
         shutdownOutput() hoặc shutdownInput()
                |
              close()
                |
                v
              CLOSED
```

Sơ đồ là mô hình khái niệm, không phải class enum Java. `AsynchronousSocketChannel` không cung cấp sẵn enum `CONNECTING`/`HALF_CLOSED`. Ứng dụng cần quản lý state của riêng mình nếu dùng một state machine nghiệp vụ.

**Các điểm quan trọng:**

1. `open()` tạo channel **đang mở nhưng chưa kết nối**; `getRemoteAddress()` trả `null` khi chưa connected.
2. `connect(remote)` khởi tạo kết nối; chỉ sau **successful completion** mới được coi phiên TCP đã established.
3. Theo JavaDoc, nếu lần kết nối **thất bại**, channel bị đóng; muốn thử địa chỉ khác nên **mở channel mới**, không retry trên channel hỏng.
4. Một channel đã kết nối tiếp tục được xem là connected cho đến khi `close()`; `shutdownInput/Output` là **half-close** và không tương đương `close`.
5. Khi `close` xảy ra, các I/O còn chờ có thể thất bại với `AsynchronousCloseException`. Không dựa vào `isOpen` kiểm tra trước rồi cho rằng thao tác sau đó luôn thành công: thread khác có thể đóng channel giữa chừng.

### 2.1. Trên server, ai tạo channel kết nối?

`AsynchronousServerSocketChannel` được mở và `bind` để chờ client. Một lần `accept()` thành công trả về **một `AsynchronousSocketChannel` mới đã connected**. Listener vẫn là một đối tượng riêng, phục vụ các kết nối tiếp theo.

```text
Server listener (bind port 0 -> OS cấp cổng)
      |
      +-- accept Future/handler đang đợi
                   |
         client.connect(server address)
                   |
                   v
          serverSide SocketChannel   <==== TCP ====>   client SocketChannel
                   |                                      |
                read/write                              read/write
                   |                                      |
                 close                                    close
      |
   listener còn có thể accept kết nối mới
```

**Không lấy `AsynchronousServerSocketChannel` để gọi `read/write` dữ liệu ứng dụng.** Listener dùng để accept; các channel trả về mới thực hiện trao đổi bytes.

## 3. Mở và kết nối bằng Future

API client:

```java
AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open();

Future<Void> pendingConnect = client.connect(remote);

pendingConnect.get(5, TimeUnit.SECONDS); // thành công thì trả null
```

Đây là snippet, `remote` là `SocketAddress` được phép truy cập. `get(timeout)` có thể **block thread gọi**; giá trị thành công của `Future<Void>` là `null`, không phải `true`.

Phía listener:

```java
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open().bind(address);

Future<AsynchronousSocketChannel> pendingAccept =
        listener.accept();

AsynchronousSocketChannel peer =
        pendingAccept.get(5, TimeUnit.SECONDS);
```

Đây cũng là snippet; cần quản lý đóng `listener` và `peer`. `address` là địa chỉ bind, không nhất thiết là IP mà client ngoài mạng có thể truy cập. Dùng loopback để thực hành an toàn, dùng địa chỉ phù hợp mô hình mạng khi triển khai.

### 3.1. Chương trình runnable: một vòng connect → trao đổi → close

Tạo file `AsyncConnectFutureDemo.java`:

```java
import java.io.IOException;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.*;
import java.util.concurrent.*;
public class AsyncConnectFutureDemo {
    static void writeAll(AsynchronousSocketChannel ch, String data) throws Exception {
        ByteBuffer src = ByteBuffer.wrap(data.getBytes(StandardCharsets.UTF_8));
        while (src.hasRemaining()) {
            int n = ch.write(src).get(5, TimeUnit.SECONDS);
            if (n <= 0) throw new IOException("No write progress");
        }
    }
    static String readExact(AsynchronousSocketChannel ch, int length) throws Exception {
        ByteBuffer dst = ByteBuffer.allocate(length);
        while (dst.hasRemaining()) {
            int n = ch.read(dst).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new IOException("Unexpected EOF");
        }
        dst.flip();
        return StandardCharsets.UTF_8.decode(dst).toString();
    }
    public static void main(String[] args) throws Exception {
        AsynchronousSocketChannel retained;
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            retained = client;
            InetSocketAddress address = (InetSocketAddress) server.getLocalAddress();
            Future<AsynchronousSocketChannel> accepted = server.accept();
            Future<Void> connected = client.connect(address);
            System.out.println("connect-result=" + connected.get(5, TimeUnit.SECONDS));
            try (AsynchronousSocketChannel peer = accepted.get(5, TimeUnit.SECONDS)) {
                System.out.println("connected=" + (client.getRemoteAddress() != null));
                writeAll(client, "PING");
                System.out.println("server-read=" + readExact(peer, 4));
                writeAll(peer, "PONG");
                System.out.println("client-read=" + readExact(client, 4));
            }
        }
        System.out.println("client-open-after-close=" + retained.isOpen());
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all AsyncConnectFutureDemo.java
java AsyncConnectFutureDemo
```

**stdout đã kiểm thử qua TCP loopback:**

```text
connect-result=null
connected=true
server-read=PING
client-read=PONG
client-open-after-close=false
```

**Giải thích từng bước:**

- `new InetSocketAddress(InetAddress.getLoopbackAddress(),0)` yêu cầu OS tự chọn một cổng trống của loopback. Không hard-code 8080 nên hạn chế xung đột.
- `server.accept()` khởi tạo thao tác chờ kết nối.
- `client.connect(address)` khởi tạo kết nối; `Future<Void>.get` xác nhận connected.
- `accepted.get` trả **một channel server-side khác**; server channel này không phải listener.
- `writeAll` tiếp tục ghi nếu một `write` chuyển ít bytes hơn còn lại.
- `readExact` tiếp tục đọc đến đủ **4 bytes**; vì giao thức demo biết chính xác length, không suy một lần read tương ứng một write.
- `try-with-resources` đóng lần lượt các channels; `isOpen()` sau khi đóng trả false.

**Giới hạn demo:** helper `readExact` thích hợp cho frame đã biết kích thước. Khi nguồn đóng sớm, `read` trả `-1` và helper ném lỗi. Nếu mạng không tiến triển hoặc bị tắc, Future có timeout. Trong ứng dụng thật, phải xử lý tình trạng timeout/cancel và dọn channel theo chính sách, thay vì chỉ propagate exception cho main.

## 4. Kết nối bằng CompletionHandler

Một cách khác là đăng ký:

```java
client.connect(remote, attachment,
        new CompletionHandler<Void, MyAttachment>() {
            public void completed(Void ignored, MyAttachment info) {
                // Đã kết nối; không dùng giá trị Void làm dữ liệu.
            }
            public void failed(Throwable error, MyAttachment info) {
                // Không dùng channel kết nối lỗi để retry tùy tiện.
            }
        });
```

Đây là snippet; `MyAttachment` là kiểu do ứng dụng định nghĩa. `completed` nhận kết quả `Void` (thường null) và attachment ban đầu. `failed` nhận lỗi, không giống một response application-level từ máy chủ.

**Khi nào chọn handler?** Khi một thành phần như gateway hoặc server event-driven không muốn một thread chờ `Future.get` cho mỗi kết nối. Callback có thể gửi sự kiện sang queue, hoàn thành `CompletableFuture`, bắt đầu bước handshake hoặc đăng ký đọc tiếp.

**Quan trọng:** callback vẫn là code Java, nó có thể chạy trên thread trong `AsynchronousChannelGroup`; đừng làm xử lý blocking kéo dài ngay trong callback. JavaDoc `CompletionHandler` yêu cầu handlers hoàn tất kịp thời để thread có thể dispatch các completions khác.

### 4.1. Chương trình runnable: callback với attachment

Tạo file `AsyncConnectCallbackDemo.java`:

```java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
public class AsyncConnectCallbackDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            Future<AsynchronousSocketChannel> accepting = listener.accept();
            CompletableFuture<String> connected = new CompletableFuture<>();
            client.connect(listener.getLocalAddress(), "dial-1",
                    new CompletionHandler<Void, String>() {
                        public void completed(Void ignored, String tag) {
                            connected.complete(tag + ":CONNECTED");
                        }
                        public void failed(Throwable failure, String tag) {
                            connected.completeExceptionally(failure);
                        }
                    });
            System.out.println("callback=" + connected.get(5, TimeUnit.SECONDS));
            try (AsynchronousSocketChannel serverSide = accepting.get(5, TimeUnit.SECONDS)) {
                ByteBuffer src = ByteBuffer.wrap(new byte[]{'Q'});
                while (src.hasRemaining()) {
                    if (client.write(src).get(5, TimeUnit.SECONDS) <= 0)
                        throw new IllegalStateException("No write progress");
                }
                ByteBuffer dst = ByteBuffer.allocate(1);
                while (dst.hasRemaining()) {
                    if (serverSide.read(dst).get(5, TimeUnit.SECONDS) < 0)
                        throw new IllegalStateException("EOF");
                }
                dst.flip();
                System.out.println("received=" + StandardCharsets.US_ASCII.decode(dst));
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncConnectCallbackDemo.java
java AsyncConnectCallbackDemo
```

**stdout đã kiểm thử:**

```text
callback=dial-1:CONNECTED
received=Q
```

`CompletableFuture<String>` ở đây **do ứng dụng tự tạo** để nối kết callback với phần kiểm thử; `AsynchronousSocketChannel` không cung cấp sẵn overload `connect` trực tiếp trả `CompletableFuture`. `CompletionHandler.completed` có thể được gọi trước hoặc sau khi initiating method trả về; code không được phụ thuộc thứ tự đó.

**Đối với handler thất bại:** `connected.completeExceptionally(failure)` truyền lỗi tới thread chờ, không “giấu” exception trong background thread. Trong một service, còn phải đóng channel kết nối thất bại và giải phóng metadata/session.

## 5. TCP là luồng byte: phải thiết kế giao thức thông điệp

TCP bảo toàn thứ tự bytes của một luồng được truyền thành công nhưng **không bảo toàn ranh giới lời gọi `write`**. Ví dụ producer gọi:

```text
write("HEL") + write("LO")
```

Receiver có thể quan sát một lần read nhận `HELLO`, hai lần nhận `HEL` và `LO`, hoặc nhiều lần đọc nhỏ hơn. Số bytes một `read` trả về phụ thuộc lượng dữ liệu hiện có, buffer và hệ điều hành. Đừng gọi `decode` trên bytes chưa đủ rồi kết luận parser gặp lỗi bất thường.

**Các mô hình framing phổ biến:**

1. **Length-prefix:** gửi số bytes của payload trước, rồi gửi chính xác payload; phải giới hạn độ dài chống cấp phát vô hạn.
2. **Delimiter:** ví dụ newline giữa các messages; cần escape/encoding policy và giới hạn line length.
3. **Fixed-length record:** khi giao thức đã quy định kích thước cố định.
4. **Protocol-specific parser:** HTTP/WebSocket/TLS hoặc frame riêng có trạng thái; không chỉ lấy một read làm message.

Đối với payload UTF-8, **length được tính theo bytes sau encode**, không phải `String.length()` (UTF-16 code units). Nếu split nhiều chunks, dùng `CharsetDecoder` có trạng thái để xử lý ký tự nhiều byte nằm qua ranh giới.

### 5.1. Chương trình runnable: length-prefixed UTF-8 qua socket

Tạo file `AsyncTcpFramingDemo.java`:

```java
import java.io.IOException;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
public class AsyncTcpFramingDemo {
    static void send(AsynchronousSocketChannel ch, ByteBuffer src) throws Exception {
        while (src.hasRemaining()) {
            int n = ch.write(src).get(5, TimeUnit.SECONDS);
            if (n <= 0) throw new IOException("No write progress");
        }
    }
    static void receive(AsynchronousSocketChannel ch, ByteBuffer dst) throws Exception {
        while (dst.hasRemaining()) {
            int n = ch.read(dst).get(5, TimeUnit.SECONDS);
            if (n < 0) throw new IOException("Truncated frame");
        }
        dst.flip();
    }
    public static void main(String[] args) throws Exception {
        String text = "Xin chào 🌍";
        byte[] content = text.getBytes(StandardCharsets.UTF_8);
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            var accepting = server.accept();
            client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepting.get(5, TimeUnit.SECONDS)) {
                ByteBuffer frame = ByteBuffer.allocate(4 + content.length);
                frame.putInt(content.length).put(content).flip();
                send(client, frame);
                ByteBuffer header = ByteBuffer.allocate(4);
                receive(peer, header);
                int length = header.getInt();
                if (length < 0 || length > 4096) throw new IOException("Invalid length");
                ByteBuffer payload = ByteBuffer.allocate(length);
                receive(peer, payload);
                byte[] decoded = new byte[length];
                payload.get(decoded);
                System.out.println("length-validated=" + (length == content.length));
                System.out.println("bytes-preserved=" + Arrays.equals(content, decoded));
                System.out.println("text-preserved="
                        + text.equals(new String(decoded, StandardCharsets.UTF_8)));
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncTcpFramingDemo.java
java AsyncTcpFramingDemo
```

**stdout đã kiểm thử:**

```text
length-validated=true
bytes-preserved=true
text-preserved=true
```

Đây là **length-prefix gồm 4 bytes big-endian** mặc định của `ByteBuffer.putInt/getInt`. Quy tắc endianness phải là một phần của protocol nếu hai ứng dụng khác ngôn ngữ giao tiếp.

**Tại sao có hai vòng while?** Vì `send` phải đợi đến khi toàn bộ buffer được tiêu thụ; `receive` phải tích lũy đủ bytes của **header** và **payload**. Hai bên không đoán một lần `write` thành một lần `read`.

**Ràng buộc bảo mật:** `length` lấy từ network input; bắt buộc kiểm tra trước khi `ByteBuffer.allocate(length)`. Ứng dụng thực có thể dùng quota message, streaming parser và kiểm tra authentication/authorization; không tin một header báo 2 GiB rồi cấp phát 2 GiB RAM.

**Lưu ý encoding:** test sử dụng text có dấu tiếng Việt và emoji để chứng minh `String.length()` không phải byte length. Output in boolean để tránh phụ thuộc encoding của terminal đang hiển thị Unicode.

## 6. Full-duplex và hai giới hạn pending operation

`AsynchronousSocketChannel` hỗ trợ **một thao tác đọc và một thao tác ghi đang chờ đồng thời** trên cùng channel. Tuy nhiên, cùng một lúc chỉ được có:

- **Tối đa một read pending** → gọi read thứ hai trước khi read thứ nhất hoàn tất gây `ReadPendingException`.
- **Tối đa một write pending** → gọi write thứ hai trước khi write thứ nhất hoàn tất gây `WritePendingException`.

Đây là hạn chế cấp channel, không phải hạn chế “một request cho cả socket”. Trong khi đang đọc, chương trình **có thể khởi tạo write**. Đó là tính full-duplex của TCP.

### 6.1. Vì sao giới hạn pending quan trọng?

Nếu worker A đang chờ read cho một frame và worker B cũng gọi read trên cùng channel, không còn quy tắc rõ ràng worker nào nhận bytes nào. NIO.2 buộc ứng dụng **điều phối lần read tiếp theo** sau completion của lần read trước.

Thiết kế thường dùng:

```text
Per-connection state:
  read side:
    IDLE -> READING -> PARSING -> IDLE -> ...
  write side:
    queue -> one WRITE_PENDING -> on completion -> next queue item

Có thể READING và WRITE_PENDING đồng thời,
nhưng không có hai READING hoặc hai WRITE_PENDING cùng lúc.
```

Nếu nhiều business threads muốn gửi message, đẩy vào **per-connection outbound queue**; chỉ một writer coordinator khởi tạo `write` tiếp theo khi previous write đã hoàn tất. Queue cần giới hạn để tránh một client chậm khiến server giữ dữ liệu vô hạn.

### 6.2. Chương trình runnable: read thứ hai bị từ chối

Tạo file `AsyncPendingReadDemo.java`:

```java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.TimeUnit;
public class AsyncPendingReadDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            var accepted = server.accept();
            client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepted.get(5, TimeUnit.SECONDS)) {
                ByteBuffer firstBuffer = ByteBuffer.allocate(1);
                var first = client.read(firstBuffer);
                boolean rejected = false;
                try {
                    client.read(ByteBuffer.allocate(1));
                } catch (ReadPendingException ex) {
                    rejected = true;
                }
                System.out.println("second-read-rejected=" + rejected);
                ByteBuffer send = ByteBuffer.wrap(new byte[]{65});
                while (send.hasRemaining())
                    if (peer.write(send).get(5, TimeUnit.SECONDS) <= 0)
                        throw new IllegalStateException("No write progress");
                System.out.println("first-read-count=" + first.get(5, TimeUnit.SECONDS));
                firstBuffer.flip();
                System.out.println("first-byte=" + firstBuffer.get());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncPendingReadDemo.java
java AsyncPendingReadDemo
```

**stdout đã kiểm thử:**

```text
second-read-rejected=true
first-read-count=1
first-byte=65
```

Trong demo, peer **chưa gửi byte nào** khi client gọi lần read thứ hai. Vì thế lần read đầu còn pending và thao tác tiếp theo bị từ chối. Sau đó peer gửi byte ASCII `A` (mã decimal 65), Future đầu tiên hoàn thành với 1 byte.

Đừng cố “sửa” bằng cách tạo nhiều buffers rồi gửi nhiều lời gọi `read` đồng thời: vấn đề nằm ở **trạng thái pending của channel**, không ở địa chỉ bộ nhớ buffer.

**Ghi chú với write pending:** nếu cần chứng minh `WritePendingException` qua integration test, phải chủ động điều phối một write còn pending (ví dụ mô phỏng provider hoặc điều kiện backpressure). Một đoạn dữ liệu nhỏ trên loopback có thể ghi xong trước khi bạn kịp gọi write tiếp; test kiểu “gọi 2 writes sát nhau thì chắc chắn bị exception” là **không ổn định**.

## 7. Trạng thái chưa kết nối và các lỗi trước khi connected

Một channel vừa `open` **không** được tự ý đọc/ghi dữ liệu TCP:

- `getRemoteAddress()` thường trả `null` trước khi connected.
- `read/write` trên socket chưa connected ném `NotYetConnectedException`.
- `connect` gọi khi đã connected ném `AlreadyConnectedException`.
- `connect` gọi khi một connect khác còn pending ném `ConnectionPendingException`.
- Địa chỉ unresolved hoặc không hỗ trợ có thể tạo `UnresolvedAddressException`/`UnsupportedAddressTypeException`.
- Nếu thao tác connect thất bại ở mức kết quả asynchronous, channel bị đóng theo contract; không retry trên cùng object.
- Binding local address qua `bind` là thao tác khác với connecting; một socket có thể **đã bind nhưng chưa connect**.

### 7.1. Chương trình runnable: open khác connected

Tạo file `AsyncUnconnectedDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.channels.*;
public class AsyncUnconnectedDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
        try (client) {
            System.out.println("open=" + client.isOpen());
            System.out.println("remote-null=" + (client.getRemoteAddress() == null));
            boolean readRejected = false;
            try { client.read(ByteBuffer.allocate(1)); }
            catch (NotYetConnectedException ex) { readRejected = true; }
            boolean writeRejected = false;
            try { client.write(ByteBuffer.wrap(new byte[]{1})); }
            catch (NotYetConnectedException ex) { writeRejected = true; }
            System.out.println("read-rejected=" + readRejected);
            System.out.println("write-rejected=" + writeRejected);
        }
        System.out.println("open-after-close=" + client.isOpen());
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncUnconnectedDemo.java
java AsyncUnconnectedDemo
```

**stdout đã kiểm thử:**

```text
open=true
remote-null=true
read-rejected=true
write-rejected=true
open-after-close=false
```

Chương trình không mở một kết nối đến network bên ngoài. Nó chứng minh **“channel đang mở” không đồng nghĩa “TCP connection đã thiết lập”**.

Trạng thái business-level như “authenticated”, “logged in”, “authorized” **không phải** thuộc tính ngầm của socket connected. Một TCP connection thành công chỉ chứng minh kết nối đến endpoint theo địa chỉ; tầng ứng dụng vẫn cần handshake và xác thực riêng.

## 8. ByteBuffer và số byte thực nhận

Mỗi read/write có số byte hoàn tất qua `Future<Integer>` hoặc `CompletionHandler<Integer,A>`:

- `read` trả **số byte thực chuyển**, có thể ít hơn buffer còn chỗ.
- `read` trả **-1** khi peer đã đóng chiều gửi và không còn bytes để nhận, tức EOF (nếu kênh/operation hợp lệ).
- `write` trả số byte đã chuyển từ buffer vào channel, không có nghĩa peer đã **xử lý nội dung nghiệp vụ**.
- Trạng thái `position/limit` của ByteBuffer thay đổi theo lượng bytes hoàn tất.
- Trong khi I/O còn pending, **không dùng/sửa ByteBuffer** gắn với operation đó.
- `ByteBuffer` không tự thread-safe; một buffer chỉ nên thuộc quyền sở hữu **một outstanding operation** tại một thời điểm.
- Với Unicode có nhiều bytes/chunk, quản lý decoder qua các lần nhận.

**Ví dụ điển hình:** nếu app cần nhận frame 100 bytes, một read trả 23 bytes không phải lỗi. Cần giữ `ByteBuffer` đang được điền, khởi tạo read mới **sau completion**, cho tới khi đủ 100 hoặc nhận -1/error/deadline.

### 8.1. Buffer lifecycle

```text
READ vào buffer:
  allocate -> read pending -> completed(n) -> ... -> flip -> parse
  (nếu cần đọc tiếp trước flip: giữ nguyên position và issue read kế tiếp)

WRITE từ buffer:
  put data -> flip -> write pending -> completed(n)
  -> nếu remaining: write tiếp -> nếu hết: clear/recycle
```

**Không gọi `flip()` trước khi read hoàn tất**, và **không `clear()` một source buffer trước khi write hoàn tất**. Kết quả có thể là dữ liệu sai, trùng hoặc mất.

### 8.2. Nhiều buffers và vectored operations

`AsynchronousSocketChannel` còn có overload đọc/ghi nhiều `ByteBuffer[]` với `offset`, `length`, timeout và handler trả `Long`. Chúng có ích để gửi header + payload mà không cần ghép một buffer duy nhất trong một số trường hợp.

Tuy nhiên, vẫn chỉ được có **một read pending và một write pending** trên channel; dùng vectored I/O không biến mỗi buffer thành một operation độc lập có thể chồng nhiều reads. Hãy hiểu `Long result` là tổng bytes thực được chuyển, phân phối qua buffers theo contract và kiểm tra `remaining`.

## 9. Half-close: shutdownOutput và shutdownInput

TCP hỗ trợ đóng riêng từng hướng truyền, còn channel vẫn có thể mở.

- `client.shutdownOutput()`: đóng **chiều ghi của client**; sau đó client không được tiếp tục write. Phía peer, khi đã đọc hết các bytes trước đó, read sẽ nhận **-1 (EOF)**.
- `client.shutdownInput()`: đóng **chiều đọc của client**; các reads tiếp theo trả **-1** theo contract. Ảnh hưởng tới read đang pending hoặc bytes đã nhận nhưng chưa tiêu thụ có thể phụ thuộc OS.
- `close()`: đóng channel, giải phóng tài nguyên, gây thất bại cho các I/O còn pending theo contract.

**Half-close rất hữu ích cho giao thức request-to-EOF**: client gửi dữ liệu, gọi `shutdownOutput()` để báo hết request, nhưng **vẫn giữ chiều nhận** để server phản hồi. Không phải mọi application protocol đều dùng EOF để đánh dấu message; HTTP/WebSocket thường có framing/quy tắc khác.

### 9.1. Chương trình runnable: gửi request, half-close rồi nhận response

Tạo file `AsyncHalfCloseDemo.java`:

```java
import java.io.IOException;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
public class AsyncHalfCloseDemo {
    static void writeAll(AsynchronousSocketChannel ch, String value) throws Exception {
        ByteBuffer b = ByteBuffer.wrap(value.getBytes(StandardCharsets.UTF_8));
        while (b.hasRemaining()) {
            int n = ch.write(b).get(5, TimeUnit.SECONDS);
            if (n <= 0) throw new IOException("No progress");
        }
    }
    static String readToEof(AsynchronousSocketChannel ch) throws Exception {
        StringBuilder result = new StringBuilder();
        ByteBuffer b = ByteBuffer.allocate(32);
        while (true) {
            b.clear();
            int n = ch.read(b).get(5, TimeUnit.SECONDS);
            if (n == -1) return result.toString();
            if (n > 0) {
                b.flip();
                result.append(StandardCharsets.UTF_8.decode(b));
            }
        }
    }
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            var accepted = server.accept();
            client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = accepted.get(5, TimeUnit.SECONDS)) {
                writeAll(client, "REQ");
                client.shutdownOutput();
                System.out.println("peer-received=" + readToEof(peer));
                writeAll(peer, "ACK");
                peer.shutdownOutput();
                System.out.println("client-received=" + readToEof(client));
                System.out.println("client-still-open=" + client.isOpen());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncHalfCloseDemo.java
java AsyncHalfCloseDemo
```

**stdout đã kiểm thử:**

```text
peer-received=REQ
client-received=ACK
client-still-open=true
```

**Giải thích:**

1. Client gửi đủ 3 bytes request và **đợi write hoàn tất** trước khi half-close chiều gửi.
2. Server đọc đến **-1** để biết request đã kết thúc theo protocol demo.
3. Server gửi 3 bytes response và half-close chiều gửi của server.
4. Client vẫn có thể **đọc** response sau khi `shutdownOutput()` của chính nó.
5. `client.isOpen()` vẫn true trước khi TWR gọi `close()`.

**Giới hạn minh họa:** `readToEof` decode từng chunk riêng vì payload demo chỉ chứa ASCII. Nếu gửi văn bản UTF-8 nhiều byte, phải dùng `CharsetDecoder` qua chunks hoặc tích lũy bytes để decode sau khi đủ payload. Giao thức production nên giới hạn tối đa bytes và deadline khi đợi EOF.

**Cẩn thận:** đừng gọi `shutdownOutput()` trong khi còn outstanding writes chưa xác định; hiệu ứng lên write pending là system-dependent. Hoàn tất các sends cần thiết rồi mới shutdown.

## 10. close() khi còn I/O đang chờ

Một socket có thể bị đóng bởi:

- Ứng dụng kết thúc request hoặc người dùng hủy tác vụ.
- Timeout/deadline trong policy.
- Shutdown service/connection group.
- Lỗi connect/read/write nghiêm trọng.
- Một thread khác gọi `close()` trong lúc callback đang đợi.

Theo `AsynchronousChannel`, khi `close()` được gọi mà còn I/O outstanding, operation đó có thể kết thúc bằng `AsynchronousCloseException`. Đừng cho rằng `Future.get()` luôn trả số byte thành công sau khi channel bị đóng.

### 10.1. Chương trình runnable: read pending bị ngắt bởi close

Tạo file `AsyncClosePendingDemo.java`:

```java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
public class AsyncClosePendingDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0))) {
            AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
            try {
                var accepting = server.accept();
                client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer = accepting.get(5, TimeUnit.SECONDS)) {
                    System.out.println("peer-accepted=" + (peer.getRemoteAddress() != null));
                    var pending = client.read(ByteBuffer.allocate(8));
                    client.close();
                    boolean interrupted = false;
                    try {
                        pending.get(5, TimeUnit.SECONDS);
                    } catch (ExecutionException ex) {
                        interrupted = ex.getCause() instanceof AsynchronousCloseException;
                    }
                    System.out.println("pending-asynchronous-close=" + interrupted);
                    System.out.println("client-open=" + client.isOpen());
                }
            } finally {
                client.close();
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncClosePendingDemo.java
java AsyncClosePendingDemo
```

**stdout đã kiểm thử:**

```text
peer-accepted=true
pending-asynchronous-close=true
client-open=false
```

Client bắt đầu read nhưng peer không gửi bytes. Khi client `close()`, Future nhận lỗi; `ExecutionException.getCause()` là `AsynchronousCloseException` trong môi trường thử nghiệm. `client.close()` trong `finally` là phép đóng idempotent giúp dọn tài nguyên kể cả khi lỗi.

**Không dùng đoạn code trên làm pattern hủy tùy tiện mọi request:** một lệnh `close()` sẽ cắt cả hai chiều của connection, làm các operations khác của cùng phiên không thể hoàn tất như dự tính. Trong service, cần policy ownership và trạng thái đang xử lý.

## 11. Quản lý accept loop: chỉ một accept pending trên một listener

`AsynchronousServerSocketChannel` hỗ trợ một `accept` đang chờ tại một thời điểm. Nếu bắt đầu accept thứ hai trước khi accept thứ nhất hoàn tất, `AcceptPendingException` được ném.

Một server long-running thường làm:

1. Bind listener và khởi tạo một `accept`.
2. Khi accept hoàn tất, **đăng ký lần accept tiếp theo** để tiếp tục nhận connections.
3. Bàn giao channel accepted cho connection handler/state machine riêng.
4. Giới hạn số active connections và buffer usage.
5. Khi shutdown, ngăn accept mới, đóng listener và các connections theo policy.

Với callback, có thể re-arm `accept` trong `completed` nhưng không làm xử lý business nặng ngay trên callback thread. Cần xử lý `failed`; nếu listener đã đóng, không loop vô hạn tiếp tục accept.

### 11.1. Chương trình runnable: AcceptPendingException

Tạo file `AsyncAcceptPendingDemo.java`:

```java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.TimeUnit;
public class AsyncAcceptPendingDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            var first = server.accept();
            boolean rejected = false;
            try { server.accept(); }
            catch (AcceptPendingException ex) { rejected = true; }
            System.out.println("second-accept-rejected=" + rejected);
            client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
            try (AsynchronousSocketChannel peer = first.get(5, TimeUnit.SECONDS)) {
                System.out.println("first-accepted=" + (peer.getRemoteAddress() != null));
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncAcceptPendingDemo.java
java AsyncAcceptPendingDemo
```

**stdout đã kiểm thử:**

```text
second-accept-rejected=true
first-accepted=true
```

Vì client chỉ connect **sau** khi thử hai `accept`, accept đầu tiên chắc chắn đang chờ. Lần thứ hai bị từ chối theo API; sau đó request đầu được hoàn tất bằng kết nối thật. Đây là demo xác định, không phụ thuộc timing ngẫu nhiên của network.

**Điểm phân biệt:** `AcceptPendingException` liên quan **listener**, còn `ReadPendingException`/`WritePendingException` liên quan **socket channel đang kết nối**.

## 12. AsynchronousChannelGroup: quản lý threads và shutdown

`AsynchronousSocketChannel.open()` dùng **default asynchronous channel group**. Nếu cần ràng buộc lifecycle/threads rõ cho một subsystem, có thể tạo `AsynchronousChannelGroup` riêng:

```java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
            4, threadFactory);

AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);

AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
```

Đây là snippet; cần quản lý group, channels và `ThreadFactory`. Đối với group do ứng dụng tạo, **đóng các channels** rồi gọi `group.shutdown()` hoặc `shutdownNow()` theo nhu cầu. Đừng “shutdown” group ngay sau mỗi connect khi các channel còn sử dụng.

**Các sự kiện vòng đời group:**

- `shutdown()`: ngừng nhận channels mới thuộc group; group chỉ terminated khi channels đã đóng và completion handlers đang chạy hoàn tất.
- `shutdownNow()`: ngoài shutdown còn yêu cầu đóng các channels đang mở của group; vẫn phải cân nhắc callbacks đang thực thi.
- `awaitTermination(timeout,unit)`: chờ group kết thúc trong deadline.
- `isShutdown()` khác `isTerminated()`: đã ra lệnh shutdown chưa nghĩa mọi resource đã được thu hồi.
- Mở channel trong group đã shutdown ném `ShutdownChannelGroupException`.

**Không đồng nhất group thread pool với một executor bất kỳ dành cho business logic.** Completion handlers nên nhỏ, còn CPU-heavy parsing/DB calls nên được đưa tới worker pool có backpressure. Group có thể được provider quản lý theo cách khác thread pool tự dựng, nên chỉ lập giả định theo API công khai.

### 12.1. Chương trình runnable: group riêng, đóng rồi shutdown

Tạo file `AsyncChannelGroupDemo.java`:

```java
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.util.concurrent.*;
public class AsyncChannelGroupDemo {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = task -> {
            Thread thread = new Thread(task, "net-group-demo");
            thread.setDaemon(true);
            return thread;
        };
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, factory);
        try {
            try (AsynchronousServerSocketChannel server =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client = AsynchronousSocketChannel.open(group)) {
                var accepted = server.accept();
                client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer = accepted.get(5, TimeUnit.SECONDS)) {
                    ByteBuffer byteToSend = ByteBuffer.wrap(new byte[]{77});
                    while (byteToSend.hasRemaining()) {
                        if (client.write(byteToSend).get(5, TimeUnit.SECONDS) <= 0)
                            throw new IllegalStateException("No progress");
                    }
                    ByteBuffer incoming = ByteBuffer.allocate(1);
                    while (incoming.hasRemaining()) {
                        if (peer.read(incoming).get(5, TimeUnit.SECONDS) < 0)
                            throw new IllegalStateException("EOF");
                    }
                    incoming.flip();
                    System.out.println("received-byte=" + incoming.get());
                }
            }
            group.shutdown();
            System.out.println("group-shutdown=" + group.isShutdown());
            System.out.println("group-terminated=" + group.awaitTermination(5, TimeUnit.SECONDS));
            boolean refused = false;
            try {
                AsynchronousSocketChannel.open(group).close();
            } catch (ShutdownChannelGroupException ex) {
                refused = true;
            }
            System.out.println("new-channel-rejected=" + refused);
        } finally {
            group.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncChannelGroupDemo.java
java AsyncChannelGroupDemo
```

**stdout đã kiểm thử:**

```text
received-byte=77
group-shutdown=true
group-terminated=true
new-channel-rejected=true
```

Dữ liệu truyền là byte decimal **77**. Khi mọi channels trong group đóng, gọi `shutdown` và `awaitTermination` thành công. Thao tác mở channel mới sau shutdown bị từ chối.

**Vì sao `finally {group.shutdownNow();}`?** Bảo đảm yêu cầu dọn group nếu một operation trước đó ném exception. Với service thực, nên có một shutdown coordinator để chờ các requests đang hoạt động, giải phóng buffers và hoàn tất audit/metrics theo chính sách.

## 13. Cấu hình socket options và binding address

AsynchronousSocketChannel cung cấp `supportedOptions()`, `setOption(...)` và `getOption(...)`. Những options chuẩn được hỗ trợ gồm:

| Option | Công dụng |
| --- | --- |
| `StandardSocketOptions.TCP_NODELAY` | Bật/tắt Nagle algorithm; không thay đổi TCP thành message transport |
| `SO_KEEPALIVE` | Yêu cầu TCP keepalive của OS; thông số/timing phụ thuộc hệ điều hành |
| `SO_SNDBUF` | Yêu cầu kích thước buffer gửi |
| `SO_RCVBUF` | Yêu cầu kích thước buffer nhận |
| `SO_REUSEADDR` | Điều khiển reuse address theo OS/provider |

**Không coi `TCP_NODELAY=true` là bảo đảm giảm latency trong mọi workload.** Nó có thể tăng số packets nhỏ và chi phí. `SO_KEEPALIVE` **không thay thế heartbeat/deadline ở tầng ứng dụng**: khoảng thời gian keepalive mặc định của OS có thể dài và không phản ánh được tính sống của business session.

**Địa chỉ:**

- `InetAddress.getLoopbackAddress()`: chọn địa chỉ loopback cho demos/test tự chứa.
- Port **0** khi bind: yêu cầu OS cấp một cổng đang trống tại thời điểm bind.
- `getLocalAddress()`: địa chỉ local mà socket đang bind.
- `getRemoteAddress()`: địa chỉ peer khi kết nối thành công; trước đó thường null.
- Bind socket của client không tự làm nó connected.

### 13.1. Chương trình runnable: socket options trước khi kết nối

Tạo file `AsyncSocketOptionsDemo.java`:

```java
import java.net.*;
import java.nio.channels.AsynchronousSocketChannel;
public class AsyncSocketOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
            System.out.println("supports-tcp-nodelay="
                    + client.supportedOptions().contains(StandardSocketOptions.TCP_NODELAY));
            client.setOption(StandardSocketOptions.TCP_NODELAY, true);
            System.out.println("tcp-nodelay=" + client.getOption(StandardSocketOptions.TCP_NODELAY));
            System.out.println("remote-null=" + (client.getRemoteAddress() == null));
            client.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            System.out.println("bound-local=" + (client.getLocalAddress() != null));
        }
    }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AsyncSocketOptionsDemo.java
java AsyncSocketOptionsDemo
```

**stdout đã kiểm thử:**

```text
supports-tcp-nodelay=true
tcp-nodelay=true
remote-null=true
bound-local=true
```

Chương trình có thể bind local socket nhưng không kết nối ra ngoài. Nó chứng minh **binding local address** khác **connecting remote address**; đồng thời kiểm tra TCP_NODELAY theo API.

Trên provider/socket implementation khác, có thể có thêm options; không hard-code danh sách nâng cao mà không dùng `supportedOptions()`. Nếu `setOption` bị từ chối do OS/provider hoặc quyền, phải xử lý exception và không báo cấu hình đã áp dụng.

## 14. Timeout: cần phân biệt hai loại

Có hai cơ chế mà người mới dễ nhầm:

**(A) Thời hạn đợi kết quả Future:**

```java
Future<Void> pending = client.connect(remote);
pending.get(5, TimeUnit.SECONDS);
```

`get(timeout)` hết hạn ném `TimeoutException` cho thread đợi; **không tự cam kết underlying connect bị hủy**. Caller phải quyết định giữ theo dõi Future, cancel/close hoặc teardown session.

**(B) Thời hạn của operation read/write theo overload có timeout:**

```java
client.read(buffer, 5, TimeUnit.SECONDS,
        attachment, handler);
```

Đây là snippet; `buffer`, `attachment`, `handler` đã được khai báo. Nếu read bị timeout theo API, handler có thể nhận `InterruptedByTimeoutException`. JavaDoc đặc biệt lưu ý **channel/connection có thể rơi vào trạng thái không nhất quán**, và khi không biết liệu bytes đã được đọc/ghi hay chưa, implementation có thể cấm các operations tiếp theo theo cách phụ thuộc provider.

**Hệ quả:** đừng retry ngay trên cùng buffer/channel như thể không có byte nào bị chuyển khi xảy ra timeout. Với một giao thức có yêu cầu toàn vẹn, thường nên **close session, thiết lập connection mới và dùng request ID/idempotency** để tránh duplicate effects.

### 14.1. Khi không có dữ liệu đến

Một lần `read` đang chờ không tự coi việc “chưa thấy data” là EOF. Chỉ khi peer half-close/close chiều gửi (và dữ liệu đã nhận được tiêu thụ), read có thể trả -1. Trong lúc chưa có bytes, Future có thể tiếp tục pending.

**Không chờ vô thời hạn ở server:** cần application idle timeout, handshake timeout, frame deadline, write deadline và shutdown policy. Chúng có thể được quản lý bằng scheduler ở tầng ứng dụng, không nhất thiết chỉ nhờ một con số timeout cứng trên mọi read.

### 14.2. Cancellation khác close

`Future.cancel(...)` thay đổi trạng thái Future và yêu cầu cancel theo contract; không cam kết mọi bytes chưa được chuyển trên network. Theo API `AsynchronousChannel`, việc cancel một operation có thể ảnh hưởng channel, và caller không nên sớm tái sử dụng buffers khi completion/cancellation chưa được giải quyết đúng.

`close()` đóng channel, ảnh hưởng tất cả outstanding operations trên connection đó. Không dùng nó để hủy một business job mà các jobs khác vẫn cần dùng cùng channel, trừ khi transaction/protocol được thiết kế như vậy.

## 15. Kiểm thử lỗi với Future và callback

| Tình huống | Biểu hiện/API | Hướng xử lý |
| --- | --- | --- |
| `open` thành công, chưa connect | `getRemoteAddress() == null` | Đợi successful connect trước I/O |
| Gọi read/write trước connect | `NotYetConnectedException` | Sửa state machine |
| Gọi connect khi đã connected | `AlreadyConnectedException` | Không reconnect cùng channel |
| Connect khác đang pending | `ConnectionPendingException` | Chỉ một connect attempt/connection |
| Không kết nối được endpoint | `ExecutionException` hoặc `handler.failed` | Đóng/không tái sử dụng channel, retry bằng instance mới nếu policy cho phép |
| Hai reads pending | `ReadPendingException` | Một read coordinator per channel |
| Hai writes pending | `WritePendingException` | Per-connection write queue |
| Hai accepts pending | `AcceptPendingException` | Chỉ một accept outstanding/listener |
| Peer đóng chiều gửi, buffer còn chỗ | `read` trả `-1` tại EOF | Kết thúc frame/stream theo protocol |
| Client gọi `shutdownOutput` rồi write | `ClosedChannelException` theo API | Không gửi sau half-close |
| Close khi I/O còn chờ | `AsynchronousCloseException` có thể được báo | Teardown/complete pending promises |
| Channel group đã shutdown | `ShutdownChannelGroupException` | Không mở channel mới trong group đó |
| Wait Future hết hạn | `TimeoutException` của `Future.get` | Không coi là underlying I/O đã cancel |
| Operation read/write timeout | `InterruptedByTimeoutException` qua handler | Cân nhắc channel/buffer state bất định, thường teardown |
| Peer từ chối kết nối | `ConnectException`/`IOException` trong cause | Retry có backoff theo policy, tránh loop gấp |
| OS không cho bind/listen | `BindException`/`IOException` | Kiểm tra quyền, cổng và cấu hình |
| Peer đóng/reset connection | `IOException`/`ClosedChannelException` | Ghi nhận và giải phóng session |

**Cách đọc lỗi Future:**

```java
try {
    int n = pendingRead.get(5, TimeUnit.SECONDS);
    // Xử lý n >= 0 hoặc n == -1 theo protocol.
} catch (ExecutionException ex) {
    Throwable rootCause = ex.getCause();
    // Phân loại nguyên nhân I/O thật; không chỉ log "ExecutionException".
}
```

Đây là snippet và cần imports, biến `pendingRead` phù hợp. `get()` có thể ném `InterruptedException`, `TimeoutException` hoặc `CancellationException` ngoài `ExecutionException`; mỗi loại cần chính sách riêng.

**Callback:** `failed(Throwable,attachment)` là đường lỗi ngang vai với `completed`. Một callback chỉ log exception rồi không kết thúc request state sẽ gây leak: client chờ vô hạn, buffer không được giải phóng, request không có trạng thái terminal.

## 16. Close, half-close, cancellation và lifecycle hoàn chỉnh

Một connection state machine của service có thể là:

```text
NEW
  |
CONNECTING ---------> FAILED/CLOSED
  |
CONNECTED
  |
AUTHENTICATING ------> FAILED/CLOSED
  |
ACTIVE (one read pending + one write pending max)
  |
DRAINING (ngừng nhận jobs mới; gửi hết output queue)
  |
HALF_CLOSED_OUTPUT (nếu protocol dùng EOF)
  |
WAITING_RESPONSE_OR_EOF
  |
CLOSING
  |
CLOSED
```

Đây là **trạng thái ứng dụng**, không phải enum sẵn có của JDK. `AUTHENTICATING` không tự xuất hiện nhờ TCP connect; đó là trách nhiệm của application protocol/TLS.

**Thứ tự giải phóng gợi ý:**

1. Chặn tạo jobs/requests mới cho connection.
2. Đánh dấu state shutdown để callbacks đến muộn không tạo read/write mới.
3. Cho outstanding writes hoàn tất nếu graceful shutdown và deadline còn phù hợp.
4. Nếu protocol có half-close, gọi `shutdownOutput` **sau** khi write queue đã rỗng.
5. Đợi peer response/EOF theo deadline hoặc close ngay nếu forceful shutdown.
6. Gọi `close()` cho từng `AsynchronousSocketChannel`, bảo đảm đóng server-side accepted channels, client channels và listener.
7. Hoàn thành/reject pending Futures/business promises, log lỗi có chọn lọc.
8. Cuối cùng shutdown group riêng nếu component sở hữu nó; đợi termination.
9. Giải phóng buffers, per-connection state và metrics sau khi không còn callback cần chúng.

**Không đóng listener rồi mặc nhiên nghĩ mọi accepted connections cũng đóng.** Listener và các channels đã accept là các objects riêng; service cần quản lý collection active sessions hoặc cơ chế ownership khác.

## 17. Những vấn đề không được giải quyết tự động bởi TCP async

### 17.1. Không có framing hoặc backpressure tự động

`AsynchronousSocketChannel` không biết một message JSON hoặc protobuf dài bao nhiêu. Cần parser có trạng thái. Khi peer gửi nhanh hơn consumer, buffer/queue tích lũy: phải đặt giới hạn per-connection và global, áp dụng backpressure hoặc đóng kết nối chậm.

**Không cấp phát một ByteBuffer mới cho từng byte vô hạn.** Với hàng nghìn concurrent connections, memory của buffers và request metadata có thể lớn hơn cả data trên wire.

### 17.2. Không có TLS tự động

Raw `AsynchronousSocketChannel` là transport TCP, **không tự mã hóa dữ liệu**. Nếu làm dịch vụ chứa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm, dùng TLS qua một stack được kiểm thử. Java có `SSLEngine` để tích hợp TLS non-blocking nhưng việc ghép nó với async channel đòi hỏi quản lý handshake, wrap/unwrap, buffer sizing, timeouts và hostname verification đúng.

Không nhầm “asynchronous” với “secure”; chỉ bind loopback trong bài thực hành không có nghĩa giao thức production an toàn khi mở ra mạng công khai.

### 17.3. Không có business-level acknowledgement

Khi `write` hoàn tất, bytes đã được chuyển khỏi `ByteBuffer` theo I/O operation. Điều đó không chứng minh peer đã parse, lưu database hoặc commit transaction. Muốn biết request thành công, phải định nghĩa **response frame/acknowledgement**, request ID và retry/idempotency policy.

### 17.4. Không có exactly-once hay auto reconnect

TCP có bảo đảm truyền bytes theo luồng khi connection hoạt động, nhưng nếu connection đứt giữa request và response, client có thể **không biết** server đã thực hiện business action hay chưa. Retry một khoản chuyển tiền hoặc tạo đơn hàng có thể tạo duplicate nếu không có idempotency key/transaction.

Một lần `connect` thất bại thì channel đóng; reconnect nên tạo **channel mới** và tuân theo backoff, jitter, max attempts và circuit-breaker tùy hệ thống. Không retry vô hạn không giới hạn.

### 17.5. Không cam kết native nonblocking cho mọi provider

API completion-based cho phép bạn **khởi tạo** I/O và nhận result sau. Cách OS/JDK thực hiện có thể dùng kernel facilities, thread pool hoặc kết hợp. Không đoán throughput từ tên API. Nếu vấn đề của bạn là một HTTP service phổ biến, framework mạng/TLS đã được kiểm thử có thể phù hợp hơn viết nguyên server trên raw NIO.2.

## 18. Bảo mật và vận hành

Một server lắng nghe TCP là bề mặt tấn công thật. Với production:

- **Bind địa chỉ cần thiết**, không mở wildcard/public listener khi bài toán chỉ cần loopback/internal.
- Xác thực peer và phân quyền theo domain; TCP connect thành công không chứng minh peer đáng tin.
- Áp dụng TLS và kiểm tra chứng chỉ/hostname khi cần.
- Đặt giới hạn connection count, frame size, requests pending, queue bytes, idle timeout và tổng memory.
- Không phản hồi toàn bộ input không giới hạn (reflection/amplification).
- Validate length header/encoding/schema trước khi cấp phát/parse.
- Tránh SQL/command injection trong dữ liệu downstream nhận từ socket.
- Không log tokens, raw payload nhạy cảm hoặc IP chi tiết ngoài chính sách.
- Hạn chế quyền process, container/network policy, file system access.
- Kiểm tra denial-of-service do connection chỉ connect nhưng không gửi data, partial headers và slow receivers.
- Đặt monitoring cho active connections, connect failures, pending reads/writes, timeout, callback errors, P99 latency và group shutdown.
- Khi graceful shutdown, hoàn tất/thu hồi các business promises; đừng để callbacks sau shutdown ghi vào objects đã dọn.

**Đặc biệt với read timeout:** JavaDoc cảnh báo state channel/buffer có thể bất định khi timeout xảy ra. Không dùng kết quả buffer chưa rõ ràng để parse dữ liệu đã xác thực.

## 19. Kiểm thử: điều gì phải deterministic, điều gì phụ thuộc hệ điều hành?

Các demo trong bài dùng **loopback** và server port 0 nên không phụ thuộc DNS/public Internet. Tuy vậy, một OS/container/firewall có thể cấm mở sockets ngay cả trên loopback. Khi gặp `BindException` hoặc `IOException`, cần phân biệt environment blocker với bug Java.

**Test nên khẳng định:**

1. `Future<Void>` của connect hoàn thành thành công trước khi dùng channel.
2. `accepted.get` trả một channel server-side đã connected.
3. Server và client có thể đọc/ghi một payload theo framing đã định nghĩa.
4. Read/write partial đều được xử lý bằng số byte thực.
5. `ReadPendingException` xảy ra khi read thứ nhất thực sự đang chờ.
6. `AcceptPendingException` xảy ra khi accept thứ nhất thực sự đang chờ.
7. `shutdownOutput` báo EOF tới peer nhưng channel local vẫn có thể nhận response.
8. `close` làm pending read kết thúc bằng failure phù hợp.
9. Group shutdown ngăn mở channel mới và dọn sau khi tất cả channels đóng.
10. ByteBuffer và callback state chỉ được sử dụng sau completion hợp lệ.

**Test KHÔNG nên ép:**

- Một `write` tạo đúng một `read`.
- Read 4 bytes luôn trả một lần đúng 4 bytes.
- Callback luôn chạy trên thread có tên cố định.
- Connection A luôn hoàn tất trước B.
- Mọi local port được cấp cùng một con số.
- Network latency nằm trong một ngưỡng vài ms trên mọi CI.
- Một `Future.get(timeout)` timeout làm I/O chắc chắn bị cancel.
- Một lần read không nhận byte nghĩa peer đã đóng.
- `TCP_NODELAY` làm mọi message đều đến nhanh hơn.
- Close listener tự đóng các sockets đã accept.
- Socket có `isOpen` true nghĩa remote peer còn hoạt động thực tế.

### 19.1. Mã và lệnh QA

Tất cả **10 class trong bài** có thể lưu thành các file cùng tên class rồi biên dịch bằng JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all AsyncConnectFutureDemo.java
javac -encoding UTF-8 -Xlint:all AsyncConnectCallbackDemo.java
javac -encoding UTF-8 -Xlint:all AsyncTcpFramingDemo.java
javac -encoding UTF-8 -Xlint:all AsyncHalfCloseDemo.java
javac -encoding UTF-8 -Xlint:all AsyncPendingReadDemo.java
javac -encoding UTF-8 -Xlint:all AsyncUnconnectedDemo.java
javac -encoding UTF-8 -Xlint:all AsyncChannelGroupDemo.java
javac -encoding UTF-8 -Xlint:all AsyncSocketOptionsDemo.java
javac -encoding UTF-8 -Xlint:all AsyncClosePendingDemo.java
javac -encoding UTF-8 -Xlint:all AsyncAcceptPendingDemo.java
```

Sau đó chạy `java AsyncConnectFutureDemo` hoặc một class tương ứng. Các ví dụ có output cụ thể đã được kiểm thử với mạng loopback trên JDK; không yêu cầu module/dependency thứ ba.

**Khi tích hợp vào CI:** đặt deadline hợp lý hơn tùy tải, ưu tiên test protocol semantics thay vì event timing; dọn channels và group dù có exception. Tests phản ánh quyền và network stack của môi trường hiện tại, không chứng minh cùng hành vi tại mọi proxy/load balancer/production network.

## 20. Các sai lầm điển hình

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `open()` rồi gọi read/write ngay | Channel còn unconnected | Đợi connect successful completion |
| Gọi `client.connect` lần nữa khi đã connected | `AlreadyConnectedException` | Dùng connection đang mở hoặc tạo channel mới khi cần |
| Retry connect failed trên cùng channel | Connect thất bại đóng channel | Tạo channel mới theo backoff policy |
| Đóng channel khi Future connect còn pending mà nghĩ sẽ thành công | Close ngắt I/O | Lifecycle ownership và handling cancellation |
| Quên close server-side accepted channel | Rò rỉ socket/file descriptor | Mỗi accepted channel có owner và finally/TWR |
| Dùng listener để đọc bytes ứng dụng | Listener chỉ accept | Read/write trên channel trả về từ accept |
| Gọi hai accepts cùng lúc | `AcceptPendingException` | Chờ/re-arm một accept mỗi listener |
| Gọi hai reads đang chờ | `ReadPendingException` | Một read coordinator per connection |
| Gọi hai writes đang chờ | `WritePendingException` | Write queue, serialize pending writes |
| Coi mỗi TCP read là một message | TCP không lưu message boundary | Framing length/delimiter/protocol |
| Sử dụng `String.length()` làm payload byte length | UTF-8 nhiều bytes/ký tự | Encode trước, đếm bytes |
| Cấp phát theo length từ peer mà không giới hạn | Memory exhaustion | Kiểm tra quota/max frame |
| Chỉ gọi `read` một lần rồi parse frame | Short read hợp lệ | Lặp đến đủ frame hoặc EOF |
| Chỉ gọi `write` một lần rồi coi gửi hết | Short write có thể xảy ra | Lặp theo `ByteBuffer.hasRemaining` |
| Reuse ByteBuffer khi read/write còn pending | Races/data corruption | Chỉ reuse sau completion |
| Read trả `0` bị xem là EOF | EOF = `-1` | Phân biệt 0 và -1 |
| Gọi `shutdownOutput` trước khi writes hoàn tất | Pending write behavior phụ thuộc OS | Đợi writes rồi half-close |
| Gọi `close` để chỉ báo kết thúc request rồi mong nhận response | Close cả hai chiều | Dùng `shutdownOutput` nếu protocol cần half-close |
| Coi `isOpen` true là peer còn sống | Trạng thái local không xác minh remote | Heartbeat/protocol/deadline |
| Dùng `get(timeout)` như deadline thực cho socket I/O | Chỉ giới hạn thời gian chờ Future | Định nghĩa cancel/close/session deadline |
| Retry sau timed read trên cùng buffer/channel | State có thể bất định sau timeout | Teardown và thiết lập lại connection theo policy |
| Block lâu trong callback | Có thể chiếm completion threads | Offload business work |
| Shutdown group trước khi đóng channels | Nhóm chưa terminated, request mới lỗi | Orderly draining/close/shutdown/await |
| Coi `TCP_NODELAY` là luôn tốt | Phụ thuộc workload/latency | Benchmark |
| Coi keepalive OS là heartbeat ứng dụng | Không phản ánh đầy đủ business health | App-level ping/idle policy |
| Truyền dữ liệu nhạy cảm trên raw TCP và nghĩ async đã bảo mật | Không có TLS tự động | Dùng TLS stack đã kiểm thử |
| Retry request nghiệp vụ không có ID | Có thể tạo duplicate actions | Idempotency key và transaction |
| Hard-code cổng đang dùng trong unit test | Conflict trên CI | Bind port 0 và dùng `getLocalAddress` |

## 21. Checklist code review cho kết nối bất đồng bộ

1. Tại sao chọn `AsynchronousSocketChannel` thay vì `SocketChannel`/framework mạng sẵn có?
2. Client `open` và server `accept` có chủ sở hữu và trách nhiệm `close` riêng không?
3. Có đợi successful connect trước khi read/write?
4. Có xử lý `getRemoteAddress()==null` và `NotYetConnectedException` không?
5. Có xử lý connect failure bằng channel mới thay vì reuse object cũ?
6. Có dùng `Future` hoặc `CompletionHandler` rõ ràng cho mỗi operation?
7. Có xử lý cả callback `completed` và `failed` không?
8. Có chặn hai pending reads và hai pending writes trên mỗi connection không?
9. Listener chỉ có một accept đang chờ, và accept được re-arm khi phù hợp không?
10. Có framing và max frame size/bytes không?
11. Có xử lý partial read/write và EOF `-1` đúng không?
12. Có quản lý ByteBuffer ownership cho từng pending operation không?
13. Có phân biệt UTF-8 bytes với `String.length()` không?
14. Có một write queue per connection khi nhiều threads muốn gửi không?
15. Có backpressure và giới hạn active connections/queues/buffers không?
16. Có phân biệt half-close với full close theo giao thức không?
17. Có đợi pending writes trước `shutdownOutput` không?
18. Có state machine xử lý requests khi close/timeout/cancel?
19. Có retry bounded và idempotency cho actions không chắc đã được peer xử lý?
20. Có timeout cho connect/read/write/handshake/idle phù hợp không?
21. Có hiểu `Future.get(timeout)` khác timed I/O callback overload không?
22. Có tránh reuse channel/buffer khi operation timeout để lại state bất định không?
23. Có phân loại `ExecutionException.getCause()` và `handler.failed` không?
24. Có đóng accepted channels riêng, không chỉ listener không?
25. Nếu dùng `AsynchronousChannelGroup` riêng, có shutdown đúng thứ tự không?
26. Có tránh CPU-heavy/DB blocking trong completion handlers không?
27. Có chọn socket options theo profile và `supportedOptions()` không?
28. Có TLS/authentication/authorization và size quotas không?
29. Có chống slow clients, malformed frames và resource exhaustion không?
30. Có metrics và tests bảo đảm logic, không phụ thuộc timing không?
31. Có dùng loopback test/port 0 và không mở public port ngoài ý muốn không?
32. Có xử lý lỗi hệ điều hành/network policy thay vì tự quy là lỗi Java không?

## 22. Bài tập

**Bài 1 — Vòng đời cơ bản.** Chạy `AsyncConnectFutureDemo`. Liệt kê từng bước tạo listener, bắt đầu accept, khởi tạo connect, nhận Future, trao đổi hai thông điệp và đóng cả ba channels.

**Bài 2 — Callback.** Chạy `AsyncConnectCallbackDemo`. Thay attachment `String` bằng record chứa `requestId`, `startNanos`; chuyển failure sang một CompletableFuture và ghi correlation ID.

**Bài 3 — Framing.** Chạy `AsyncTcpFramingDemo` với nội dung dài hơn 4 KiB bằng cách tăng max frame được phép trong môi trường thử. Giải thích vì sao một `read` không đại diện trọn một message.

**Bài 4 — UTF-8.** Dùng payload có ký tự tiếng Việt và emoji, phân biệt UTF-16 `String.length()` với `text.getBytes(UTF_8).length`. Thiết kế decode qua nhiều chunks mà không làm hỏng ký tự.

**Bài 5 — Full-duplex.** Từ `AsyncConnectFutureDemo`, khởi tạo read và write khác phía trong cùng một khoảng, vẫn đảm bảo mỗi channel chỉ có một pending read và một pending write.

**Bài 6 — Read pending.** Chạy `AsyncPendingReadDemo`. Thử thêm một outbound write trong khi client read đang pending; vì sao write không bị cùng loại `ReadPendingException`?

**Bài 7 — Accept loop.** Chạy `AsyncAcceptPendingDemo`. Chuyển sang callback accept re-arm trong handler hoàn tất; giới hạn tối đa số active connections.

**Bài 8 — Open vs connected.** Chạy `AsyncUnconnectedDemo`. Thêm kiểm tra `getLocalAddress` sau `bind` và giải thích vì sao local bind vẫn chưa tạo remote connection.

**Bài 9 — Half-close.** Chạy `AsyncHalfCloseDemo`. Thay protocol request-to-EOF bằng length-prefixed request/response, rồi so sánh khi nào cần half-close.

**Bài 10 — Close pending.** Chạy `AsyncClosePendingDemo`. Giải thích vì sao `ExecutionException.getCause()` quan trọng và tại sao không được đọc ByteBuffer trước khi operation terminal.

**Bài 11 — Group lifecycle.** Chạy `AsyncChannelGroupDemo`. Thử có hai accepted channels đồng thời, shutdown listener, đợi active sessions xong rồi mới shutdown group; ghi log trạng thái.

**Bài 12 — Socket options.** Chạy `AsyncSocketOptionsDemo`. Kiểm tra `SO_KEEPALIVE` và `TCP_NODELAY` bằng `supportedOptions/getOption` rồi lý giải vì sao app heartbeat vẫn cần thiết.

**Bài 13 — Timeout policy.** Mô phỏng `Future.get(timeout)` hết hạn với test double; phân biệt nó với `InterruptedByTimeoutException` từ operation có timeout. Thiết kế teardown mà không làm reuse buffer sớm.

**Bài 14 — Slow receiver.** Thiết kế một per-connection write queue tối đa 128 KiB, xử lý duplicate requests, backpressure và đóng kết nối khi quota bị vượt.

**Bài 15 — Security.** Thiết kế phiên TCP công khai có TLS, authentication, max frame, idle timeout, rate limiting và monitoring. Giải thích raw `AsynchronousSocketChannel` không tự cung cấp các lớp này.

**Bài 16 — Chọn abstraction.** So sánh raw NIO.2 async socket với `SocketChannel`/framework mạng có event loop để tạo HTTP service. Phân tích complexity, testability, TLS, resource ownership và throughput thực tế thay vì chỉ dựa tên async.

## 23. Kết luận

- **`AsynchronousSocketChannel` cung cấp kết nối TCP với completion-based connect/read/write**, nhận kết quả bằng `Future` hoặc `CompletionHandler`; Java 17+ vẫn hỗ trợ API này.
- **Mở ≠ kết nối.** `open()` tạo unconnected channel; chỉ sau connect successful completion mới đọc/ghi hợp lệ. Connect thất bại đóng channel.
- **`AsynchronousServerSocketChannel` accept** tạo một server-side socket channel riêng. Listener chỉ có một pending accept; mỗi connected channel chỉ có tối đa một pending read và một pending write nhưng cho phép hai hướng đó hoạt động đồng thời.
- **TCP là byte stream**. Phải xử lý short read/write, EOF `-1`, length-prefix/delimiter và ByteBuffer ownership; không giả định mỗi write = một read.
- **Half-close khác close.** `shutdownOutput` giúp bên kia quan sát EOF mà phía local vẫn có thể đọc response, còn `close` đóng connection và có thể làm pending I/O thất bại.
- **`AsynchronousChannelGroup` có vòng đời riêng**; quản lý ownership, callbacks, shutdown và waiting correctly.
- **Future timeout khác I/O operation timeout**. Một lần timeout có thể để channel/buffer ở trạng thái không thể tiếp tục an toàn; không retry mù.
- **API không tự cung cấp TLS, authentication, application framing, retries hoặc exactly-once**. Những cơ chế đó do protocol, business logic và hạ tầng mạng đảm nhiệm.
- **Đo hiệu năng, kiểm thử loopback/OS thật và giới hạn tài nguyên** thay vì kết luận “asynchronous luôn nhanh hơn”.

## Tài liệu chính thức

- [AsynchronousSocketChannel — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): open, connect, read/write, close, shutdownInput/Output, socket options, timeout và pending operations.
- [AsynchronousServerSocketChannel — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): bind, accept, AcceptPendingException và lifecycle listener.
- [AsynchronousChannel — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannel.html): Future/callback, cancellation và AsynchronousCloseException.
- [AsynchronousChannelGroup — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): group-owned threads, shutdown, shutdownNow và awaitTermination.
- [CompletionHandler — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed, attachment và yêu cầu không chặn callback quá lâu.
- [ByteBuffer — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position/limit, flip/clear, quản lý binary framing.
- [Future — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): get, timeout và cancellation.
- [StandardSocketOptions — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/StandardSocketOptions.html): TCP_NODELAY, SO_KEEPALIVE và options.
