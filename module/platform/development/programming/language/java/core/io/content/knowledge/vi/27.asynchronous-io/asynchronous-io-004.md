# AsynchronousSocketChannel và AsynchronousServerSocketChannel trong Java NIO.2

Java NIO.2 cung cấp hai API kết nối TCP bất đồng bộ quan trọng: `AsynchronousServerSocketChannel` để lắng nghe và chấp nhận kết nối, và `AsynchronousSocketChannel` để kết nối, đọc, ghi trên một socket. Thay vì buộc luồng gọi chờ I/O hoàn tất, các phương thức có thể **khởi phát thao tác rồi trả về ngay**; kết quả được nhận bằng `Future` hoặc `CompletionHandler`.

Chữ “asynchronous” nói về **mô hình hoàn thành thao tác**, không phải bảo đảm mọi hệ điều hành đều dùng cùng cơ chế I/O ở nhân hệ điều hành, cũng không có nghĩa callback của ứng dụng không bao giờ chạy trên một luồng có thể bị chặn bởi công việc khác. Khi dùng API này phải quản lý **trạng thái kết nối, buffer, thao tác đang chờ, thứ tự callback, lỗi và đóng tài nguyên**.

Bài này hướng dẫn hai channel, cách mở và sử dụng, hai kiểu nhận kết quả, ví dụ Java 17 chạy độc lập, các giới hạn liên quan đến concurrent read/write và những lỗi dễ gặp.

## 1. Phân biệt hai loại channel và luồng hoạt động

| Lớp | Trách nhiệm | Phương thức chính |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | Bind vào địa chỉ TCP, chờ và chấp nhận kết nối mới | `open()`, `bind(...)`, `accept()`, `accept(attachment, handler)`, `close()` |
| `AsynchronousSocketChannel` | Kết nối tới server hoặc thao tác trên kết nối được server nhận | `open()`, `connect(...)`, `read(...)`, `write(...)`, `shutdownInput()`, `shutdownOutput()`, `close()` |

Một phiên trao đổi thường có các bước:

```text
Server                                       Client
  |                                           |
  | AsynchronousServerSocketChannel.open()    |
  | bind(localAddress)                        |
  | accept()   [đang chờ hoàn thành]          | AsynchronousSocketChannel.open()
  |                                           | connect(serverAddress)
  |<----------- TCP connection -------------->|
  | accept hoàn thành, trả về                  | connect hoàn thành
  | AsynchronousSocketChannel của server      |
  | read()    [đang chờ] <--------------------| write()
  | write() ------------------------------->  | read()
  | đóng các channel theo vòng đời            | đóng channel
```

**Quan trọng:** `accept()` không trả về một `SocketChannel` đồng bộ mà là một `AsynchronousSocketChannel` mới đại diện cho kết nối đã được chấp nhận. `AsynchronousServerSocketChannel` chỉ dùng cho **lắng nghe và accept**, không dùng để gọi `read()` / `write()` dữ liệu trên từng client.

Các lớp nằm trong package `java.nio.channels`. Chúng là API khác với `ServerSocketChannel` và `SocketChannel` được dùng cùng `Selector`. Không đăng ký `AsynchronousSocketChannel` với `Selector`, không gọi `configureBlocking(false)` và không áp dụng `SelectionKey.OP_READ/OP_WRITE` cho loại channel bất đồng bộ này.

## 2. Mở server và client

Server thường mở channel, `bind` địa chỉ cục bộ rồi bắt đầu một thao tác `accept`:

```java
// Minh họa trong một phương thức cho phép ném IOException.
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open();
server.bind(new InetSocketAddress("127.0.0.1", 9000));

Future<AsynchronousSocketChannel> pending = server.accept();
```

Đoạn mã là **minh họa**, cần import các lớp `java.nio.channels`, `java.net`, `java.util.concurrent` và đóng `server` trong `finally` / `try-with-resources`. Nếu port 9000 đang được dùng hoặc địa chỉ không thể bind, sẽ có `IOException`. Lệnh `accept()` đặt một yêu cầu đang chờ; `pending.get()` mới chặn luồng gọi cho tới khi có kết quả.

Client tạo channel và khởi động kết nối:

```java
// Minh họa, bỏ qua quản lý close để tập trung vào API.
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
Future<Void> connecting =
        client.connect(new InetSocketAddress("127.0.0.1", 9000));
// Sau khi connecting hoàn thành thành công mới tiến hành I/O.
```

Với dạng `Future`, có thể gọi `connecting.get()` để chờ kết nối, nhưng chính việc chờ này **làm luồng gọi bị chặn**. API vẫn bất đồng bộ ở bước khởi tạo operation; việc gọi `get()` ngay lập tức là một quyết định của ứng dụng, không biến channel trở lại `SocketChannel` đồng bộ.

Các cách mở `open()` sử dụng **asynchronous channel group mặc định** của provider. Ngoài ra có overload nhận `AsynchronousChannelGroup` để nhiều channel dùng chung nhóm luồng và tài nguyên do ứng dụng cấu hình.

## 3. Hai mô hình nhận kết quả hoàn thành

### 3.1. Dùng Future: dễ viết logic theo từng bước

Các phương thức như `connect(remote)`, `read(buffer)`, `write(buffer)` và `accept()` trả `Future`. Giá trị hoàn thành phụ thuộc thao tác:

| Lời gọi | Kiểu Future | Dữ liệu nhận qua `get()` |
| --- | --- | --- |
| `client.connect(remote)` | `Future<Void>` | `null` khi kết nối thành công |
| `server.accept()` | `Future<AsynchronousSocketChannel>` | Kết nối client vừa được chấp nhận |
| `client.read(dst)` | `Future<Integer>` | Số byte thực đọc; `-1` khi EOF |
| `client.write(src)` | `Future<Integer>` | Số byte thực ghi |

Ví dụ:

```java
// Đoạn minh họa trong phương thức xử lý checked exceptions.
Future<Integer> operation = client.read(buffer);

// Có thể làm công việc khác tại đây.
Integer n = operation.get(5, TimeUnit.SECONDS);
```

`Future.get(timeout, unit)` đặt **thời hạn chờ cho chính luồng gọi**; khi `get` báo `TimeoutException`, không được mặc định rằng I/O nền đã bị hủy. Muốn có chính sách timeout thực sự phải kiểm soát operation và channel; việc `cancel()` trên một thao tác I/O có những hệ quả provider/API cần xem xét (có trường hợp khiến channel không còn dùng được cho thao tác cùng loại), nên đừng tùy tiện tiếp tục sử dụng như thể không có yêu cầu nào đang chạy.

`Future.get()` có thể ném `InterruptedException` nếu luồng chờ bị ngắt, `ExecutionException` nếu thao tác nền thất bại, `TimeoutException` nếu quá hạn ở overload có timeout. Nên xử lý đúng từng trường hợp và giải phóng tài nguyên.

### 3.2. Dùng CompletionHandler: kết quả đến qua callback

Overload bất đồng bộ nhận **attachment** và **handler** để gửi kết quả khi thao tác kết thúc. Giao diện chính:

```java
public interface CompletionHandler<V, A> {
    void completed(V result, A attachment);
    void failed(Throwable exc, A attachment);
}
```

Đây là chữ ký để minh họa, không phải file code độc lập. `V` là kiểu kết quả của operation (`Integer`, `Void`, hoặc `AsynchronousSocketChannel`); `A` là kiểu state đính kèm do ứng dụng chọn.

Ví dụ bắt đầu accept bằng callback:

```java
// Minh họa: server đã bind, cần import CompletionHandler.
server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel peer, Void unused) {
        // peer là kết nối đã accept; phải quản lý vòng đời peer.
        handleNewClient(peer); // Hàm nghiệp vụ minh họa.
    }

    @Override
    public void failed(Throwable error, Void unused) {
        reportAcceptFailure(error); // Hàm nghiệp vụ minh họa.
    }
});
```

`handleNewClient` và `reportAcceptFailure` là **hàm ứng dụng chưa định nghĩa**, nên đoạn này không phải chương trình chạy độc lập. Không gọi `Future.get()` trong callback để chờ chính operation; callback đã là điểm hoàn thành của operation đó.

Callback có thể được chạy bởi một thread của asynchronous channel group. **Không giả định callback luôn chạy trên cùng thread đã bắt đầu I/O, hoặc các callback của một ứng dụng luôn có một thứ tự dễ dự đoán**. Công việc nặng, I/O chặn và lời gọi khóa lâu trong callback có thể làm giảm khả năng phục vụ các kết nối khác. Hãy chuyển công việc nặng ra executor thích hợp nếu cần.

## 4. Accept bất đồng bộ: không chỉ accept một lần

Một lời gọi `server.accept()` thường ứng với **một kết nối mới**. Sau khi yêu cầu hoàn tất, muốn nhận client tiếp theo thì phải gọi `accept` mới.

Với kiểu callback, mẫu ý tưởng:

```java
// Phác thảo, ở trong một thành phần đang quản lý server.
void acceptNext(AsynchronousServerSocketChannel server) {
    server.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
        @Override
        public void completed(AsynchronousSocketChannel peer, Void ignored) {
            if (server.isOpen()) {
                acceptNext(server); // Lên lịch accept tiếp theo.
            }
            servePeer(peer); // Hàm ứng dụng, không làm nghẽn callback.
        }

        @Override
        public void failed(Throwable error, Void ignored) {
            if (server.isOpen()) {
                onAcceptFailure(error); // Ghi nhận lỗi, điều phối retry.
            }
        }
    });
}
```

Đây là **phác thảo kiến trúc**, chưa cung cấp các hàm `servePeer` / `onAcceptFailure`, retry/backoff hay quản lý đóng socket; không phải chương trình độc lập. Với server chạy thực tế cần bảo đảm luôn có quy ước đăng ký accept tiếp theo sau những lỗi có thể phục hồi, tránh lặp lỗi tức thì không giới hạn.

**Giới hạn bắt buộc:** Một `AsynchronousServerSocketChannel` chỉ cho phép **một yêu cầu accept đang chờ**. Gọi accept khác khi accept trước chưa hoàn tất có thể ném `AcceptPendingException`. Không dùng nhiều thread gọi `accept` không phối hợp trên cùng server channel rồi trông chờ mỗi lời gọi sẽ trở thành một hàng đợi accept.

Trong `completed`, channel `peer` trả về đã được cấp cho ứng dụng; phải có chủ sở hữu và chính sách `close` cho nó, độc lập với chuyện server vẫn tiếp tục chấp nhận client mới.

## 5. Read/write bất đồng bộ và partial I/O

Khi `AsynchronousSocketChannel` hoàn thành một lời gọi đọc hoặc ghi, số byte hoàn thành **không bắt buộc bằng toàn bộ số byte còn lại trong ByteBuffer**:

```java
Future<Integer> r = client.read(input);
Future<Integer> w = client.write(output);
```

Đây là hai thao tác minh họa; chúng cần các buffer hợp lệ, channel ở trạng thái kết nối đúng và chương trình điều phối tránh thao tác trùng loại. Với TCP, bên gửi và bên nhận luôn xử lý **byte stream**, không phải thông điệp có ranh giới tự nhiên.

| Kết quả | `read(dst)` | `write(src)` |
| --- | --- | --- |
| Số dương `n` | Nhận `n` byte, `dst.position()` tăng `n` | Gửi `n` byte, `src.position()` tăng `n` |
| `0` | Chưa đọc byte nào ở operation này, không phải EOF | Chưa ghi byte nào ở operation này, không phải đã gửi xong |
| `-1` | EOF đầu vào (peer đóng hướng gửi) | Không phải kết quả thành công thông thường của write |

Ví dụ ứng dụng cần gửi 10 byte, operation ghi đầu tiên hoàn thành với kết quả 3. Khi callback đến, `output.position()` đã tăng lên 3; **phải tiếp tục gửi 7 byte còn lại từ chính buffer đó**, không `rewind()` rồi gửi lại từ đầu và cũng không thả buffer khi chưa hoàn tất.

Tương tự, một lần đọc vào buffer 8 byte có thể trả 2; chưa thể giải mã một frame dài 8 byte. Ứng dụng phải bảo toàn 2 byte và bắt đầu yêu cầu read tiếp theo để lấy thêm dữ liệu.

### Một thao tác đọc và một thao tác ghi đang chờ

`AsynchronousSocketChannel` cho phép một yêu cầu đọc và một yêu cầu ghi diễn ra đồng thời trên cùng kết nối, nhưng:

- Khi **đang có một read chưa hoàn tất**, khởi phát read thứ hai trên cùng channel có thể ném `ReadPendingException`.
- Khi **đang có một write chưa hoàn tất**, khởi phát write thứ hai trên cùng channel có thể ném `WritePendingException`.
- Chỉ bắt đầu lần read/write **cùng loại** tiếp theo sau khi lần trước hoàn thành thành công hoặc thất bại và trạng thái được điều phối.
- Không thay đổi nội dung, `position` hoặc `limit` của buffer đang được dùng cho một operation khi operation chưa hoàn thành. Tránh chuyển buffer này cho luồng khác sửa đồng thời.
- Sau khi đã hoàn thành read/write, callback hoặc code xử lý `Future` có thể dùng số byte thật và buffer state để quyết định xử lý tiếp.

Đây là sự khác biệt quan trọng so với `Selector`: AIO báo **operation completed**, không phải chỉ có `OP_READ/OP_WRITE` readiness. Dù vậy, completion vẫn có thể chỉ xử lý một phần frame.

### Dùng vòng lặp với Future để xử lý đầy đủ buffer

Đoạn sau là **mẫu minh họa** khi caller có thể chờ kết quả, xử lý `InterruptedException`, `ExecutionException`, `TimeoutException` và có `AsynchronousSocketChannel client` đã kết nối:

```java
ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
while (data.hasRemaining()) {
    int n = client.write(data).get(5, TimeUnit.SECONDS);
    if (n < 0) {
        throw new IOException("Unexpected write result");
    }
    // n==0: chưa gửi thêm; thử operation kế tiếp theo chính sách timeout.
}
```

Chỉ khi `data.hasRemaining()` bằng `false` mới coi byte của buffer đã được channel chấp nhận đủ. Việc đó **không xác nhận ứng dụng bên nhận đã đọc hoặc xử lý dữ liệu**; muốn xác nhận ở tầng nghiệp vụ cần giao thức phản hồi/ACK của ứng dụng.

Với `CompletionHandler`, mẫu xử lý partial write là giữ buffer dưới dạng attachment (hoặc state của kết nối), và gọi `write()` tiếp khi `completed` cho biết còn byte:

```java
// Phác thảo trong thành phần sở hữu channel và buffer.
CompletionHandler<Integer, ByteBuffer> handler =
        new CompletionHandler<>() {
            @Override
            public void completed(Integer n, ByteBuffer pending) {
                if (n < 0) {
                    reportWriteFailure(new IOException("Negative write"));
                } else if (pending.hasRemaining()) {
                    channel.write(pending, pending, this);
                } else {
                    onFrameSent();
                }
            }

            @Override
            public void failed(Throwable error, ByteBuffer pending) {
                reportWriteFailure(error);
            }
        };

channel.write(outbound, outbound, handler);
```

Đây là **phác thảo**, cần `channel`, `outbound`, `onFrameSent`, `reportWriteFailure` và cơ chế ownership/đóng channel. Với lỗi hoặc timeout không được khởi phát lại tùy tiện một operation khi trạng thái channel không còn tin cậy. Ứng dụng sản xuất còn cần hạn mức số byte chờ, số lần thử, deadline và chính sách backpressure.

## 6. Chương trình Java 17 hoàn chỉnh: server accept bằng handler, client kết nối và trao đổi bằng Future

Ví dụ dưới đây tạo server TCP trên địa chỉ loopback với **cổng động** để tránh phụ thuộc vào dịch vụ bên ngoài. Server đăng ký `accept` bằng `CompletionHandler`, dùng `CompletableFuture` chuyển kết quả callback sang luồng điều khiển ví dụ. Client sử dụng `Future` để kết nối và thực hiện I/O. Hai đầu trao đổi các byte ASCII `PING` và `PONG`; hàm đọc/ghi lặp theo byte thực hoàn thành, không dựa vào giả định một operation xử lý hết.

Tạo tệp **`AsyncSocketDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public final class AsyncSocketDemo {
    private AsyncSocketDemo() {}

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                    AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                    AsynchronousSocketChannel.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            CompletableFuture<AsynchronousSocketChannel> accepted =
                    new CompletableFuture<>();

            server.accept(null,
                    new CompletionHandler<AsynchronousSocketChannel, Void>() {
                        @Override
                        public void completed(
                                AsynchronousSocketChannel peer,
                                Void attachment) {
                            accepted.complete(peer);
                        }

                        @Override
                        public void failed(Throwable error, Void attachment) {
                            accepted.completeExceptionally(error);
                        }
                    });

            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                    accepted.get(5, TimeUnit.SECONDS)) {

                writeFully(client, ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII)));

                ByteBuffer request = ByteBuffer.allocate(4);
                readFully(peer, request);
                request.flip();
                System.out.println("server received="
                        + StandardCharsets.US_ASCII.decode(request));

                writeFully(peer, ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.US_ASCII)));

                ByteBuffer response = ByteBuffer.allocate(4);
                readFully(client, response);
                response.flip();
                System.out.println("client received="
                        + StandardCharsets.US_ASCII.decode(response));
            }
        }
    }

    private static void writeFully(AsynchronousSocketChannel channel,
                                   ByteBuffer data) throws Exception {
        while (data.hasRemaining()) {
            int n = channel.write(data).get(5, TimeUnit.SECONDS);
            if (n < 0) {
                throw new IOException("Unexpected write result");
            }
        }
    }

    private static void readFully(AsynchronousSocketChannel channel,
                                  ByteBuffer data) throws Exception {
        while (data.hasRemaining()) {
            int n = channel.read(data).get(5, TimeUnit.SECONDS);
            if (n < 0) {
                throw new EOFException("Stream ended before frame was complete");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AsyncSocketDemo.java
java AsyncSocketDemo
```

Kết quả khi loopback hoạt động bình thường và I/O hoàn tất trong thời hạn của ví dụ:

```text
server received=PING
client received=PONG
```

**Giải thích luồng thực thi:**

1. `server.bind(..., 0)` yêu cầu hệ điều hành chọn một cổng còn trống trên địa chỉ loopback.
2. `server.accept(null, handler)` đăng ký yêu cầu nhận kết nối và **trả về ngay**; khi hoàn thành, callback đặt channel nhận được vào `accepted`.
3. `client.connect(...)` khởi động kết nối TCP; `get(5, TimeUnit.SECONDS)` chờ kết quả trong demo.
4. `accepted.get(...)` lấy channel phía server. Nó là một `AsynchronousSocketChannel` riêng với `client`.
5. `writeFully(client, ...)` gửi các byte của `PING`. `readFully(peer, ...)` nhận đủ 4 byte và `flip()` trước khi giải mã.
6. Server ghi `PONG`, client đọc đủ 4 byte và in kết quả. `try-with-resources` đóng peer, client và server.

Hàm `readFully` và `writeFully` gọi các **operation bất đồng bộ** nhưng sau đó chờ `Future.get()`, nên ví dụ điều khiển tuần tự để dễ học. Một server AIO có tính mở rộng cao thường tổ chức state/callback để không chặn luồng điều phối cho mỗi connection.

Ví dụ cố ý dùng giao thức **khung cố định 4 byte**, không phải framing cho mọi TCP message. Trong giao thức thực tế, cần đặt giới hạn kích thước frame và giữ state cho frame chưa hoàn tất. Khi `Future.get` timeout, code demo thoát khối `try` và đóng channel thay vì giả định operation tự ngừng. Các hàm minh họa không có backoff cho trường hợp operation liên tục hoàn thành với 0 byte; ví dụ loopback nhỏ không nhằm triển khai server chịu tải.

## 7. Xử lý state theo kết nối và callback mà không chặn

Khi server có nhiều client, không nên giữ một biến `ByteBuffer` chung cho tất cả kết nối. Mỗi `AsynchronousSocketChannel` có thể có một đối tượng `Session` chứa:

```java
// Định nghĩa minh họa cho server nhiều kết nối.
final class Session {
    final AsynchronousSocketChannel channel;
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outgoing =
            new java.util.ArrayDeque<>();
    boolean inputEnded;
    int expectedFrameLength = -1;

    Session(AsynchronousSocketChannel channel) {
        this.channel = channel;
    }
}
```

Đây là phần minh họa, không có server đầy đủ hay hàng đợi thread-safe. Một thiết kế thực tế phải làm rõ ai sở hữu `Session` và liệu callback có thể chạy đồng thời hay không.

Chuỗi xử lý điển hình:

1. Khi accept xong, tạo `Session` cho client.
2. Bắt đầu một `read` với `session.inbound` và đính kèm `session` vào handler.
3. Khi read hoàn thành: nếu `-1`, xử lý EOF; nếu nhận dữ liệu, `flip()` để phân tích các frame đã đủ, `compact()` giữ byte chưa hoàn tất; sau đó xin read mới nếu kết nối còn mở và có chỗ trong buffer.
4. Khi một response sẵn sàng, đưa `ByteBuffer` vào hàng đợi output và **chỉ khởi động một write đang chờ** cho từng channel. Sau khi write hoàn thành, nếu buffer còn byte thì tiếp tục; nếu hết thì xử lý buffer kế tiếp.
5. Nếu output queue quá lớn, áp dụng **backpressure**: giới hạn số request, số byte đang chờ, tạm dừng nhận input theo giao thức hoặc đóng kết nối chậm. Không tạo vô hạn buffer khi client không đọc.

`ByteBuffer.flip()` chuyển từ ghi vào buffer sang đọc dữ liệu đã có; `compact()` giữ phần byte chưa được parser tiêu thụ. Gọi `clear()` khi chưa xử lý hết sẽ làm mất ranh giới dữ liệu dở; gọi `rewind()` trên buffer gửi còn byte có thể gây gửi trùng.

Khi hai callback read và write chạy gần nhau, việc cùng sửa `Session` cần sự điều phối cụ thể (ví dụ một state machine và single-owner executor, hoặc khóa thích hợp). **Không suy ra callback được gọi tuần tự chỉ vì cùng channel**.

## 8. AsynchronousChannelGroup và tài nguyên thread

`AsynchronousChannelGroup` là nhóm channel bất đồng bộ liên quan một provider, cho phép kiểm soát tài nguyên dùng để xử lý những completion task. Thay vì dùng group mặc định, ứng dụng có thể tạo group với executor:

```java
// Đoạn minh họa, cần IOException/try-finally và quản lý executor.
ExecutorService executor = Executors.newFixedThreadPool(4);
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);

AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);

AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
```

Đoạn này cần import `java.util.concurrent.ExecutorService`, `Executors` và `java.nio.channels.AsynchronousChannelGroup`; không phải chương trình độc lập. Trong thực tế **phải đóng các channel, shutdown group và quản lý executor/thread lifecycle** theo API cùng provider. Một executor phục vụ callback cũng không nên bị chiếm bởi quá nhiều tác vụ chặn lâu.

Các điểm cần biết:

- Không giả định số lượng thread callback đúng bằng số lượng kết nối TCP; một group có thể phục vụ nhiều channel.
- Implementation có thể khác nhau giữa hệ điều hành/JDK: `AsynchronousSocketChannel` là API bất đồng bộ, không bắt buộc native kernel AIO cho mọi platform.
- `CompletionHandler.failed` phải xử lý lỗi theo trạng thái kết nối; lỗi một client không nên khiến tất cả callback bị bỏ không xử lý.
- Group shutdown và channel close là hai trách nhiệm khác nhau. Không ngừng group giữa lúc còn operation cần chạy hoặc chưa xử lý hết kết quả mà không có chính sách phục hồi.

## 9. Timeout, đóng channel và hủy thao tác

Các overload callback của `AsynchronousSocketChannel` cho phép timeout I/O:

```java
// Minh họa: channel và dst đã khai báo.
channel.read(dst, 5, TimeUnit.SECONDS, state,
        new CompletionHandler<Integer, Session>() {
            @Override
            public void completed(Integer n, Session s) {
                onReadComplete(n, s);
            }

            @Override
            public void failed(Throwable error, Session s) {
                onReadFailure(error, s);
            }
        });
```

Đây là mẫu không độc lập: `channel`, `dst`, `state`, `Session`, `onReadComplete` và `onReadFailure` là các phần của ứng dụng. Khác với `Future.get(5,SECONDS)` (chỉ giới hạn **lúc chờ kết quả**), timeout trên overload `read/write` là một tham số **của chính operation**.

Khi operation timeout hoặc bị hủy, hợp đồng của `AsynchronousSocketChannel` có thể khiến khả năng tiếp tục đọc/ghi ở channel trở nên không được bảo đảm trong một số trường hợp. Với kết nối gặp lỗi nghiêm trọng, cách an toàn thường là đánh dấu session thất bại, hủy tác vụ liên quan, đóng channel và dọn state thay vì cố tái sử dụng buffer/channel một cách mù quáng.

Một số trường hợp cần xử lý riêng:

| Tình huống | Điều cần làm |
| --- | --- |
| `UnresolvedAddressException` hoặc `UnsupportedAddressTypeException` khi connect | Kiểm tra địa chỉ và loại `SocketAddress` |
| Connect thất bại | Operation báo thất bại; không coi channel là kết nối hợp lệ |
| `ReadPendingException` hoặc `WritePendingException` | Có operation cùng loại đang chờ; sửa state machine |
| `AcceptPendingException` | Không phát lệnh accept thứ hai trước khi lệnh đầu hoàn thành |
| `AsynchronousCloseException` hoặc `ClosedChannelException` | Channel đã bị đóng trong lúc thao tác/đã đóng trước thao tác |
| `InterruptedException` khi chờ Future | Giữ đúng chính sách interrupt và cleanup, không mất dấu lỗi |
| `ExecutionException` khi chờ Future | Xem nguyên nhân gốc trong `getCause()` |
| `read` hoàn thành với `-1` | Xử lý EOF, half-close hoặc frame còn thiếu theo giao thức |
| `write` hoàn thành với `0` | Giữ buffer và tiến hành operation tiếp theo có kiểm soát |

`AsynchronousSocketChannel.shutdownOutput()` dùng khi muốn đóng hướng gửi nhưng có thể vẫn đọc phản hồi ở hướng nhận, phù hợp một số giao thức TCP half-close. Tuy nhiên gọi `shutdownOutput()` trước khi tất cả byte chờ gửi hoàn thành có thể làm mất dữ liệu theo ý định ứng dụng.

## 10. So sánh với blocking I/O và Selector

| Tiêu chí | `Socket` / blocking channel | `SocketChannel` + `Selector` | `AsynchronousSocketChannel` |
| --- | --- | --- | --- |
| Cơ chế chính | Luồng đợi khi đọc/ghi | Theo dõi readiness với `select()` | Khởi phát operation, nhận completion |
| Cách biết có dữ liệu | `read` trả về sau khi thao tác hoàn tất hoặc EOF | `OP_READ` báo có thể thử đọc | `Future` hoặc callback cho biết read đã hoàn thành |
| Cách biết ghi xong | Lời gọi blocking kết thúc sau khi ghi phần dữ liệu được chấp nhận | `OP_WRITE` báo khả năng thử ghi | Completion của `write` có số byte đã ghi |
| Partial read/write | Vẫn có thể xảy ra | Cần giữ buffer qua nhiều lượt readiness | Cần giữ buffer qua nhiều completion |
| Điều phối | Có thể đơn giản cho ít kết nối | Event loop, interest operations, state theo key | Callback/Future, state theo connection/attachment |
| Điểm dễ nhầm | Một read chưa chắc bằng một frame | Readiness chưa chắc có một frame | Completion chưa chắc hoàn thành cả frame |

AIO không phải lựa chọn tối ưu mặc định. `Selector` có thể thuận tiện nếu ứng dụng đã có event loop rõ ràng; blocking I/O hoặc virtual threads (trên phiên bản Java hỗ trợ) có thể làm code nghiệp vụ dễ đọc hơn trong một số hệ thống. Hãy chọn kiến trúc dựa trên yêu cầu throughput, latency, số lượng kết nối, tính dễ bảo trì và kiểm thử trên nền tảng triển khai thực tế.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `accept()` tự động nhận tất cả kết nối tiếp theo | Server chỉ nhận một client rồi dừng accept | Khởi phát accept mới sau completion phù hợp |
| Gọi hai `accept` đang chờ trên cùng server channel | `AcceptPendingException` | Chỉ một accept outstanding mỗi server channel |
| Gọi `read` lần hai khi read cũ đang chờ | `ReadPendingException` | State machine chỉ lập lịch read mới sau completion |
| Gọi `write` chồng lên write cũ | `WritePendingException` | Hàng đợi output và một write đang chờ |
| Nghĩ một completion đọc bằng một TCP message | Ghép/tách sai frame | Framing, parser và buffer state |
| Không kiểm tra `ByteBuffer.hasRemaining()` sau write | Gửi thiếu dữ liệu | Tiếp tục write từ position hiện tại |
| Gọi `Future.get()` trực tiếp trên thread callback chính rồi chờ lâu | Mất khả năng xử lý completion khác | Dùng callback/state machine hoặc executor riêng |
| Dùng chung một buffer cho nhiều operation, sửa trước completion | Dữ liệu sai và race | Rõ ownership, không đụng buffer đang pending |
| Coi timeout của `get` là đã hủy I/O | Operation vẫn có thể chạy | Đóng/hủy/cleanup theo chính sách rõ ràng |
| Callback ném lỗi hoặc bỏ qua `failed` | Rò rỉ kết nối, mất thông tin lỗi | Xử lý mọi nhánh, logging và close |
| Không quản lý group/executor/socket lifecycle | Giữ thread, kết nối hoặc bộ nhớ không cần thiết | `try-with-resources` cho channel, shutdown group đúng cách |

**Ghi nhớ:** `AsynchronousServerSocketChannel` chờ kết nối TCP và tạo `AsynchronousSocketChannel` cho mỗi client; `AsynchronousSocketChannel` thực hiện connect/read/write bất đồng bộ. Nhận kết quả bằng `Future` hoặc `CompletionHandler`, không phát operation cùng loại trùng khi chưa hoàn thành, không giả định một lần I/O xử lý đủ một frame, và luôn quản lý buffer/state cùng vòng đời kết nối một cách rõ ràng.