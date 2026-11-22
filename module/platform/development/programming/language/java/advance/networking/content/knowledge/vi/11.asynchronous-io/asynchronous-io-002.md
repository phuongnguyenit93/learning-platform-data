# AsynchronousServerSocketChannel và AsynchronousSocketChannel trong Java NIO.2

**I/O bất đồng bộ** cho phép ứng dụng **khởi tạo một thao tác nhận kết nối, kết nối, đọc hoặc ghi** rồi nhận kết quả sau, thay vì buộc thread gọi phương thức đợi tới khi tác vụ I/O hoàn thành. Trong Java 17, hai API quan trọng của mạng TCP ở tầng này là **java.nio.channels.AsynchronousServerSocketChannel** (listener nhận kết nối) và **java.nio.channels.AsynchronousSocketChannel** (một kết nối TCP có thể đọc/ghi). Chúng thuộc nhóm **NIO.2**, có từ Java 7.

Điểm mấu chốt là **asynchronous không có nghĩa tự động chạy nhanh hơn hay không dùng thread**, và **không đồng nghĩa với SocketChannel non-blocking + Selector**. Asynchronous channel dùng **Future** hoặc **CompletionHandler** để thông báo kết quả; provider/JVM và hệ điều hành sẽ quản lý cơ chế hoàn tất, dispatch callback và tài nguyên ở hậu trường. Lời gọi khởi tạo I/O thường trả về ngay nhưng nếu sau đó gọi **Future.get()** ngay trên cùng thread, chính thread ấy vẫn chặn để đợi kết quả.

Bài Knowledge này thuộc mục **I/O bất đồng bộ**. Sau bài học, bạn cần: chọn đúng vai trò của server/client asynchronous channels, hiểu **accept/connect/read/write** theo Future và callback, dùng ByteBuffer và xử lý partial I/O, quản lý tối đa một thao tác cùng chiều đang pending, thiết kế timeout/cancellation/group lifecycle, đọc exception đúng và viết một TCP echo demo Java 17 chạy được.

## 1. Phân biệt ba mô hình TCP I/O thường gặp

| Mô hình | API điển hình | Cách ứng dụng nhận kết quả | Lưu ý |
|---|---|---|---|
| Blocking I/O | **ServerSocket**, **Socket** | Lời gọi **accept/read/write** trả về sau khi hoàn thành hoặc ném lỗi | Dễ viết tuần tự; thread gọi có thể bị chặn |
| Non-blocking readiness I/O | **ServerSocketChannel**, **SocketChannel**, **Selector** | **select()** báo readiness; ứng dụng chủ động **accept/read/write** và quản lý **OP_CONNECT/OP_READ/OP_WRITE** | Có thể trả 0/partial I/O; ứng dụng điều hành event loop |
| Asynchronous completion I/O | **AsynchronousServerSocketChannel**, **AsynchronousSocketChannel** | Nhận **Future** hoặc callback **CompletionHandler.completed/failed** khi thao tác kết thúc | Kết quả đến bất đồng bộ; phải quản lý outstanding operations, ByteBuffer và vòng đời |

**NIO.2 asynchronous socket channels không đăng ký với Selector** và không yêu cầu **configureBlocking(false)**. Đừng bê nguyên vòng lặp **OP_ACCEPT/OP_CONNECT** của SocketChannel sang AsynchronousSocketChannel. Với async API, khởi tạo thao tác và nhận completion; nếu dùng callback, callback chỉ nên làm việc ngắn và khởi tạo bước I/O tiếp theo.

Cả hai asynchronous channels đều làm việc với **TCP byte stream**, không tự thêm message framing, thứ tự request nghiệp vụ, TLS hay logic retry/idempotency. Dù completion callback báo một **write** đã hoàn tất, peer **chưa chắc** đã xử lý thông điệp ở tầng ứng dụng.

### Sơ đồ vòng đời

~~~text
                    Máy chủ (listener)
AsynchronousServerSocketChannel.open()
              |
           bind(...)
              |
           accept() -------------------------------------+
              |                                         |
        Future<AsynchronousSocketChannel>                |
              |                                         |
         accept hoàn tất                                |
              |                                         |
         accepted peer  <----- TCP connection -----  client
              |                                  AsynchronousSocketChannel.open()
              |                                            |
              |                                         connect(...)
              |                                            |
         read(ByteBuffer)                    Future<Void> / CompletionHandler
              |                                            |
         write(ByteBuffer)                               read/write
              |                                            |
         close accepted peer                           close client
              |
         close listener
~~~

**Listener** và **accepted peer** là hai đối tượng khác nhau. Đóng một accepted channel kết thúc **một connection**, không phải dừng listener. Đóng listener ngừng nhận kết nối mới; các accepted channels đã tạo cần quản lý và đóng riêng.

## 2. AsynchronousServerSocketChannel: listener và accept bất đồng bộ

Listener được tạo rồi bind địa chỉ, cổng:

~~~java
AsynchronousServerSocketChannel listener =
        AsynchronousServerSocketChannel.open();
listener.bind(new InetSocketAddress("127.0.0.1", 0));
~~~

Đây là **đoạn API minh họa**, chưa phải chương trình độc lập và phải đóng listener về cuối. Cổng **0** yêu cầu OS chọn một cổng tạm; đọc địa chỉ thực qua **listener.getLocalAddress()**. Listener mới mở nhưng **chưa bind**; gọi **accept** quá sớm ném **NotYetBoundException**.

Hai overload quan trọng:

~~~java
Future<AsynchronousSocketChannel> next = listener.accept();
listener.accept(attachment, completionHandler);
~~~

- **accept()** trả **Future<AsynchronousSocketChannel>**. **Future.get()** sau khi thành công trả channel đại diện cho connection vừa nhận, không trả chính listener.
- **accept(A attachment, CompletionHandler<AsynchronousSocketChannel, ? super A> handler)** khởi tạo thao tác rồi gọi **completed(acceptedChannel, attachment)** hoặc **failed(throwable, attachment)**.
- **Tối đa một accept đang pending trên cùng listener.** Nếu gọi accept khác trước khi thao tác cũ hoàn thành, Java ném **AcceptPendingException**. Điều này **không** có nghĩa một server chỉ có thể phục vụ một client; mỗi accepted channel xử lý riêng và listener tiếp tục accept.
- **bind(local, backlog)** có tham số backlog được đề nghị; giới hạn hàng đợi listening và cách thực thi cụ thể thuộc OS/implementation, **không** phải giới hạn số client đã accept.
- Listener và accepted channel có thể thuộc **AsynchronousChannelGroup** chung, phụ thuộc group đã cấu hình.

### Vì sao thường re-arm accept trong callback?

Một listener chạy liên tục cần **khởi tạo lần accept kế tiếp sau khi lần trước đã hoàn tất**, không lặp lời gọi accept khi vẫn pending:

~~~java
listener.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
            @Override
            public void completed(
                    AsynchronousSocketChannel peer, Void ignored) {
                listener.accept(null, this); // Re-arm cho client kế tiếp.
                handle(peer);                 // Xử lý connection vừa accept.
            }

            @Override
            public void failed(Throwable error, Void ignored) {
                report(error);                // Áp dụng chính sách lỗi/đóng.
            }
        });
~~~

**Đây chỉ là đoạn minh họa ý tưởng**: **handle(peer)** và **report(error)** là hàm do ứng dụng phải tự định nghĩa, chưa phải file chạy độc lập. Trong server thật, cần kiểm tra listener đang đóng hay không, bao quanh thao tác re-arm bằng xử lý lỗi đồng bộ, giới hạn concurrent connections và bảo đảm mọi accepted peer có owner chịu trách nhiệm close. Không re-arm khi server đang shutdown.

Đừng nhầm quy tắc “một accept pending” với “một callback đang chạy”. Thao tác accept đã hoàn tất có thể trả peer cho callback; lúc đó bạn có thể bắt đầu accept tiếp, trong khi connection cũ được xử lý bằng các thao tác read/write trên accepted channel.

## 3. AsynchronousSocketChannel: kết nối TCP và trao đổi ByteBuffer

Client tạo channel chưa kết nối:

~~~java
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
Future<Void> connecting = client.connect(remoteAddress);
connecting.get(); // Chặn thread hiện tại tới completion.
~~~

Đoạn trên là minh họa, không phải chương trình độc lập; **remoteAddress** cần được xác định. Kênh mới **open nhưng chưa connected**. **connect(SocketAddress)** trả **Future<Void>**; khi hoàn tất thành công, **get() trả null**, không trả boolean true hay Socket. Nếu connect thất bại, Future.get ném **ExecutionException** có cause chứa lỗi I/O. API callback tương ứng:

~~~java
client.connect(remoteAddress, attachment,
        new CompletionHandler<Void, MyState>() {
            @Override
            public void completed(Void ignored, MyState state) {
                // Kết nối thành công; có thể bắt đầu read/write.
            }

            @Override
            public void failed(Throwable error, MyState state) {
                // Ghi lỗi và dọn channel.
            }
        });
~~~

Đây cũng là minh họa có **MyState** tự định nghĩa. **AsynchronousSocketChannel không dùng finishConnect()**; đó là API của **SocketChannel** trong mô hình Selector/non-blocking. Cũng không có **isConnectionPending()** giống SocketChannel. Theo tài liệu AsynchronousSocketChannel, có thể kiểm tra địa chỉ remote bằng **getRemoteAddress()**: trả **null** khi chưa kết nối; nhưng thiết kế ứng dụng nên theo dõi **state và completion** rõ ràng, không chỉ polling địa chỉ.

**Một connect operation chỉ thực hiện cho một channel.** Gọi connect lại khi operation cũ đang chờ có thể ném **ConnectionPendingException**; gọi connect khi đã kết nối ném **AlreadyConnectedException**. Nếu connect thất bại, channel bị đóng theo hợp đồng API. Muốn retry, hãy tạo channel **mới** và tuân thủ deadline/backoff.

### Read và write asynchronous

~~~java
Future<Integer> reading = client.read(dst);
Future<Integer> writing = client.write(src);
~~~

- **read(ByteBuffer)** trả **Future<Integer>**, get thành công cho số byte đọc được hoặc **-1** khi EOF.
- **write(ByteBuffer)** trả **Future<Integer>**, get thành công cho số byte đã ghi từ ByteBuffer vào channel.
- Có thể dùng **CompletionHandler<Integer, AttachmentType>** thay Future để nhận số byte và attachment.
- Với **read/write**, hoàn tất một operation không đồng nghĩa đọc/ghi hết **message**. Nếu ByteBuffer còn byte cần gửi hoặc chưa nhận đủ theo framing, phải khởi tạo thao tác tiếp **sau completion của thao tác trước**.
- **Read và write độc lập:** có thể có một read pending **đồng thời** với một write pending trên cùng AsynchronousSocketChannel (full-duplex), nhưng **không được có hai reads pending hoặc hai writes pending cùng lúc**. Java sẽ ném **ReadPendingException** hoặc **WritePendingException**.

### Không có auto-framing

TCP là **byte stream**. Nếu ứng dụng ghi hai message, receiver không được giả định sẽ có đúng hai callback read. Muốn biết message kết thúc, cần **length-prefix, delimiter hoặc quy tắc EOF**, kèm giới hạn kích thước. Callback chỉ cho biết một đợt I/O đã hoàn tất với số byte cụ thể; không tự phân chia message.

## 4. Hai phong cách hoàn tất: Future và CompletionHandler

| Câu hỏi | Future API | CompletionHandler API |
|---|---|---|
| Khởi tạo | **Future<T> op = channel.read(buffer)** | **channel.read(buffer, attachment, handler)** |
| Nhận kết quả | **op.get()** hoặc **op.get(timeout, unit)** | **completed(result, attachment)** |
| Nhận lỗi | **get()** có thể ném **ExecutionException** | **failed(Throwable, attachment)** |
| Có chặn caller? | Lệnh khởi tạo không cần chặn lâu; **get() sẽ chặn nếu chưa xong** | Handler được gọi khi hoàn tất; caller không cần đợi nếu đã tổ chức callback |
| Quản lý state | State do caller/future coordinator giữ | **attachment** mang state của thao tác |
| Bẫy lớn | Gọi get trong event-loop/callback, vô tình block | Callback lồng sâu, callback ném lỗi, buffer bị chia sẻ sai, xử lý quá nặng |

### Future không bảo đảm toàn bộ chương trình là asynchronous

~~~java
Future<Integer> f = channel.read(dst);
int n = f.get();
~~~

Tại thời điểm gọi **read**, operation đã được bắt đầu asynchronous. Nhưng ngay sau đó, **get** chặn thread hiện tại cho đến khi có kết quả. Đây là lựa chọn hữu ích cho các ví dụ và tác vụ tuần tự đơn giản, nhưng **nếu luôn get ngay trên một thread/event loop duy nhất**, ứng dụng không tận dụng được nhiều thao tác I/O đang pending cùng lúc. Có thể khởi tạo các operation hợp lệ trên nhiều channels trước rồi phối hợp Future, hoặc dùng CompletionHandler/CompletableFuture để không phải chặn thread điều phối.

### CompletionHandler có hai đường, cả hai phải được xử lý

~~~java
channel.read(dst, myAttachment,
        new CompletionHandler<Integer, MyState>() {
            @Override
            public void completed(Integer bytes, MyState state) {
                // Kiểm tra bytes, xử lý partial read và EOF.
            }

            @Override
            public void failed(Throwable error, MyState state) {
                // Báo caller, giải phóng channel/buffer/state.
            }
        });
~~~

Đoạn trên có **MyState** tự định nghĩa, không phải file chạy độc lập. **Attachment** là dữ liệu gắn với *một operation* (connection context, buffer, request id...), không phải kết quả I/O. Đừng ghi dữ liệu bất kỳ lên một attachment dùng chung mà không đồng bộ; completion callback có thể chạy trên **thread thuộc group**, không phải chính thread đã khởi tạo.

Với callback, tránh chạy query DB lâu, xử lý JSON nặng hay chờ **Future.get()** từ một operation phụ thuộc vào pool ấy. Có nguy cơ làm nghẽn các thread completion và gây starvation/deadlock. Nếu cần CPU-bound work hoặc blocking DB, chuyển việc nặng sang executor khác có giới hạn và thiết kế backpressure.

## 5. Ví dụ Java 17 hoàn chỉnh: TCP echo dùng Future

Ví dụ này tự mở **asynchronous server** và **asynchronous client** trên loopback/cổng do OS cấp, không cần dịch vụ ngoài. Protocol tối giản quy định request đúng **4 byte PING** và response đúng **8 byte ACK:PING**; vì biết trước độ dài nên helper **readExactly** có thể đọc đến đủ byte mà không đợi EOF.

Cả listener, client và accepted channel đều được đóng bằng **try-with-resources**. Lệnh **Future.get(timeout)** dùng timeout khi chờ; nếu có exception, try-with-resources đóng channel. Đây là demo **Future-based**, vì main vẫn có thể chặn khi gọi get; điểm học là hiểu completion và partial I/O, không phải benchmark throughput.

Tệp **AsyncFutureEchoDemo.java**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncFutureEchoDemo {
    private static final long WAIT_SECONDS = 3L;

    private static void writeAll(
            AsynchronousSocketChannel channel, ByteBuffer data)
            throws Exception {
        while (data.hasRemaining()) {
            int written = channel.write(data)
                    .get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (written < 0) {
                throw new IOException("Write terminated unexpectedly");
            }
        }
    }

    private static void readExactly(
            AsynchronousSocketChannel channel, ByteBuffer dst)
            throws Exception {
        while (dst.hasRemaining()) {
            int n = channel.read(dst)
                    .get(WAIT_SECONDS, TimeUnit.SECONDS);
            if (n == -1) {
                throw new EOFException("EOF before expected bytes");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(loopback, 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> accepting =
                    listener.accept();
            Future<Void> connecting =
                    client.connect(listener.getLocalAddress());

            // Thành công: Future<Void>.get() trả null.
            connecting.get(WAIT_SECONDS, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel peer =
                         accepting.get(WAIT_SECONDS, TimeUnit.SECONDS)) {

                writeAll(client,
                        StandardCharsets.UTF_8.encode("PING"));

                ByteBuffer serverInput = ByteBuffer.allocate(4);
                readExactly(peer, serverInput);
                serverInput.flip();
                String request = StandardCharsets.UTF_8
                        .decode(serverInput).toString();

                writeAll(peer, StandardCharsets.UTF_8
                        .encode("ACK:" + request));

                ByteBuffer clientInput = ByteBuffer.allocate(8);
                readExactly(client, clientInput);
                clientInput.flip();
                String response = StandardCharsets.UTF_8
                        .decode(clientInput).toString();

                System.out.println("Server received: " + request);
                System.out.println("Client received: " + response);
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac -encoding UTF-8 AsyncFutureEchoDemo.java
java AsyncFutureEchoDemo
~~~

Stdout khi chạy thành công:

~~~text
Server received: PING
Client received: ACK:PING
~~~

### Phân tích chính xác

1. **AsynchronousServerSocketChannel.open().bind(...,0)** tạo listener trên loopback và cổng tạm. **accept()** bắt đầu nhận connection, trả Future mà chưa cần đợi.
2. **AsynchronousSocketChannel.open()** tạo client chưa kết nối. **connect(listener.getLocalAddress())** bắt đầu connect và trả **Future<Void>**.
3. **connecting.get(3,SECONDS)** chờ kết nối thành công; nếu bị từ chối/lỗi, get ném exception, chương trình không đi vào read/write.
4. **accepting.get(3,SECONDS)** trả về **AsynchronousSocketChannel peer** được accept. Đó là **một channel khác listener**, có nghĩa vụ close riêng.
5. Client gửi đúng 4 byte **PING**. Helper writeAll tiếp tục gọi write **tuần tự sau khi Future của lần trước hoàn tất** nếu ByteBuffer còn byte.
6. Server readExactly lấy đúng 4 byte qua một hoặc nhiều operation read; **không** giả định một read chắc chắn đủ.
7. Server gửi **ACK:PING**, client đọc đúng 8 byte. Hai ByteBuffer được **flip** trước khi UTF-8 decode.
8. Hai dòng stdout được in trong main sau khi tất cả operation cần thiết hoàn tất; không phụ thuộc cổng động hay thứ tự callback nên kết quả xác định khi demo thành công.

**Phạm vi có chủ đích:** demo chỉ có một request/response, kích thước cố định và không xử lý throughput cao. Với dữ liệu thật cần framing, maximum length, application deadline, cấu trúc outstanding operations, bảo mật, phân biệt EOF với partial message và tài nguyên cho nhiều clients. Mỗi **Future.get(3s)** đặt thời hạn chờ *của caller*; toàn giao dịch có thể lâu hơn 3 giây vì nhiều get nối tiếp. Khi dùng production, tính **deadline tổng** và đóng channel chưa hoàn tất khi hết thời hạn.

## 6. Ví dụ Java 17 hoàn chỉnh: accept, connect và read bằng CompletionHandler

Ví dụ thứ hai dùng các callback để biểu diễn sự kiện, thay vì lấy Future accept/connect rồi get. Listener khởi tạo **accept(null, handler)**; client khởi tạo **connect(..., null, handler)**; server khởi tạo read callback nhiều lần nếu cần cho tới khi đủ bốn byte. **CompletableFuture** chỉ dùng để main đợi kết quả cuối và in stdout dễ kiểm chứng; các operation accept/connect/read đều là callback-based.

Tệp **AsyncHandlerDemo.java**:

~~~java
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

public class AsyncHandlerDemo {
    private static void closeQuietly(AsynchronousSocketChannel ch) {
        try {
            ch.close();
        } catch (IOException ignored) {
            // Chỉ là cleanup sau khi báo kết quả.
        }
    }

    private static void readFour(
            AsynchronousSocketChannel peer,
            ByteBuffer buffer,
            CompletableFuture<String> received) {
        try {
            peer.read(buffer, buffer,
                    new CompletionHandler<Integer, ByteBuffer>() {
                @Override
                public void completed(Integer n, ByteBuffer dst) {
                    if (n == -1) {
                        received.completeExceptionally(
                                new EOFException("EOF before 4 bytes"));
                        closeQuietly(peer);
                        return;
                    }

                    if (dst.hasRemaining()) {
                        // Lần read trước đã hoàn tất, giờ mới read tiếp.
                        readFour(peer, dst, received);
                        return;
                    }

                    dst.flip();
                    received.complete(StandardCharsets.UTF_8
                            .decode(dst).toString());
                    closeQuietly(peer);
                }

                @Override
                public void failed(Throwable error, ByteBuffer dst) {
                    received.completeExceptionally(error);
                    closeQuietly(peer);
                }
            });
        } catch (Throwable error) {
            received.completeExceptionally(error);
            closeQuietly(peer);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        CompletableFuture<String> serverReceived =
                new CompletableFuture<>();
        CompletableFuture<Void> clientConnected =
                new CompletableFuture<>();

        try (AsynchronousServerSocketChannel listener =
                     AsynchronousServerSocketChannel.open()
                             .bind(new InetSocketAddress(loopback, 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            listener.accept(null,
                    new CompletionHandler<AsynchronousSocketChannel, Void>() {
                @Override
                public void completed(
                        AsynchronousSocketChannel peer, Void attachment) {
                    readFour(peer, ByteBuffer.allocate(4), serverReceived);
                }

                @Override
                public void failed(Throwable error, Void attachment) {
                    serverReceived.completeExceptionally(error);
                }
            });

            client.connect(listener.getLocalAddress(), null,
                    new CompletionHandler<Void, Void>() {
                @Override
                public void completed(Void result, Void attachment) {
                    clientConnected.complete(null);
                }

                @Override
                public void failed(Throwable error, Void attachment) {
                    clientConnected.completeExceptionally(error);
                }
            });

            clientConnected.get(3, TimeUnit.SECONDS);

            ByteBuffer request = StandardCharsets.UTF_8.encode("PING");
            while (request.hasRemaining()) {
                client.write(request).get(3, TimeUnit.SECONDS);
            }

            String received = serverReceived.get(3, TimeUnit.SECONDS);
            System.out.println("Connect callback: completed");
            System.out.println("Accept/read callback: " + received);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncHandlerDemo.java
java AsyncHandlerDemo
~~~

Stdout khi các operation hoàn thành thành công:

~~~text
Connect callback: completed
Accept/read callback: PING
~~~

### Điều callback demo chứng minh

- **accept handler** nhận **accepted AsynchronousSocketChannel**, không cần một thread chuyên đi gọi blocking accept.
- **connect handler** nhận **Void** ở đường thành công, **Throwable** ở đường thất bại. Không gọi **finishConnect()**.
- **read handler** nhận **Integer** chỉ số byte vừa đọc, không phải toàn bộ message. Nếu buffer còn chỗ, **readFour** khởi tạo operation kế tiếp **sau khi** callback trước đã chạy; không đè lên một read đang pending.
- **readFour** giữ cùng ByteBuffer cho chuỗi callback của một connection. Buffer chỉ được **flip** khi đã nhận đủ 4 byte.
- Nếu EOF đến trước 4 byte, **CompletableFuture.completeExceptionally(...)** báo lỗi và peer được close.
- Main dùng **CompletableFuture.get(timeout)** chỉ để chờ kết quả cuối và in thứ tự cố định. Bản thân callback path vẫn là asynchronous. Với server có nhiều clients, không nên để callback block chờ một future phụ thuộc chính nhóm thread ấy.
- Đây là mô hình **một kết nối, một request**; callback chỉ nhận request rồi đóng peer. Server thật cần reply, re-arm accept, giới hạn số client, timeout I/O và một state object rõ ràng, không dùng mã demo để production.

**Lưu ý Java 17:** **CompletableFuture** thuộc **java.util.concurrent** và giúp phối hợp hoàn tất; nó không tự biến thao tác SocketChannel blocking thành asynchronous. Ở ví dụ này chính **AsynchronousSocketChannel** đã chủ động khởi tạo async read/connect/accept.

## 7. ByteBuffer và partial I/O: hoàn tất một operation chưa chắc hoàn tất một message

Đây là nơi ứng dụng NIO.2 dễ sai nhất: operation hoàn tất và callback gọi **completed(n, attachment)**, nhưng **n chỉ là số byte chuyển được lần ấy**. Nếu yêu cầu message dài 10 KiB, hoàn tất read đầu tiên chỉ nhận 300 byte là hợp lệ. Nếu write chỉ chuyển 600 byte cũng là hợp lệ.

~~~text
Message 1000 bytes
    |
    +-- read callback #1: 230 bytes
    +-- read callback #2: 400 bytes
    +-- read callback #3: 370 bytes
    |
    +-- total = 1000; lúc ấy mới parse message hoàn chỉnh
~~~

Quy tắc:

- **Buffer position** dịch chuyển theo số byte khi operation hoàn tất; **limit** giữ nguyên. Chỉ parse/decode dữ liệu nhận được sau khi operation đã hoàn tất và khi framing đã đủ.
- Với **ByteBuffer.allocate(N)**, trước read thì position = 0, limit = N. Khi nhận đủ N, gọi **flip()** để chuyển sang đọc từ byte 0.
- Khi ghi từ ByteBuffer, **write(src)** có thể chỉ ghi một phần; dùng **src.hasRemaining()** và tiếp tục operation sau completion. Không gọi **clear** nếu vẫn còn byte chưa gửi.
- **read result -1** nghĩa end-of-stream của hướng nhận; nếu protocol chờ N byte mà mới có một phần, đó là message thiếu, không phải tự động xem như thành công.
- Với async read/write, **không thay đổi hoặc tái sử dụng ByteBuffer cho tới khi operation đang dùng nó kết thúc**. Javadoc nhấn mạnh buffer không an toàn để truy cập từ nhiều thread trong thời gian pending.
- **Một read pending + một write pending** trên cùng channel là hợp lệ; hai reads pending hoặc hai writes pending cùng chiều gây ReadPendingException/WritePendingException.
- Tối ưu **scattering read/gathering write** có overload đọc/ghi **mảng ByteBuffer** và callback kết quả **Long**; vẫn phải kiểm tra số byte đã chuyển và giới hạn mảng.

Ví dụ minh họa gửi toàn bộ ByteBuffer qua callback, **không phải file độc lập** (giả sử đã có channel, buffer và completion handler):

~~~java
channel.write(buffer, buffer,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer pending) {
        if (pending.hasRemaining()) {
            channel.write(pending, pending, this);
        } else {
            onMessageSent();
        }
    }

    @Override
    public void failed(Throwable error, ByteBuffer pending) {
        onWriteFailed(error);
    }
});
~~~

Ở đoạn này **onMessageSent()** và **onWriteFailed(...)** do ứng dụng định nghĩa; callback chain phải giữ buffer trong attachment/state, bắt cả exception đồng bộ khi khởi tạo operation mới, và có deadline/cancel. Không suy rằng callback **write completed** là remote application đã xử lý request: nó chỉ phản ánh I/O local theo hợp đồng channel.

## 8. ReadPendingException, WritePendingException và AcceptPendingException

Một số giới hạn của async channels là **quy tắc bất biến cần thiết kế ngay từ đầu**, không chỉ lỗi hiếm:

| Đối tượng | Giới hạn outstanding I/O | Nếu cố gọi chồng |
|---|---|---|
| **AsynchronousServerSocketChannel** | Tối đa **một accept** đang pending trên listener | **AcceptPendingException** |
| **AsynchronousSocketChannel** | Tối đa **một read** đang pending trên connection | **ReadPendingException** |
| **AsynchronousSocketChannel** | Tối đa **một write** đang pending trên connection | **WritePendingException** |
| **AsynchronousSocketChannel** | **Một read** và **một write** có thể pending cùng lúc | Hợp lệ để dùng TCP full-duplex |

### Sai lầm: một connection, hai worker cùng read

Ví dụ worker A khởi tạo **channel.read(bufferA)** rồi callback chưa chạy; worker B cùng lúc gọi **channel.read(bufferB)**. B có thể gặp **ReadPendingException**. Đừng chữa bằng vòng lặp retry ngay lập tức; thiết kế **một read owner/state machine** cho connection, phân phối kết quả cho các request phù hợp.

### Sai lầm: nhiều message cùng gọi write

Đừng cho nhiều threads thực hiện **channel.write(buffer)** độc lập trên cùng connection mà không có coordinator. Khi write thứ nhất còn pending, write thứ hai gây **WritePendingException**, hoặc ứng dụng mất thứ tự message. Dùng **queue outgoing buffers** theo connection, chỉ khởi tạo write tiếp sau khi operation trước hoàn tất; có giới hạn byte/queue depth và backpressure.

### Sai lầm: re-arm accept quá sớm

Khi listener.accept đã pending, không mở thêm accept mới trên cùng listener. Trong **completed** callback, operation trước đã kết thúc và có thể re-arm; vẫn phải bắt error và không re-arm khi đang shutdown. Không tạo một task chuyên retry AcceptPendingException bằng vòng lặp CPU bận.

## 9. Timeout, deadline và cancellation không phải một khái niệm

**AsynchronousSocketChannel** có overload read/write dùng timeout theo operation với **CompletionHandler**, chẳng hạn:

~~~java
channel.read(buffer, 2, TimeUnit.SECONDS, requestState,
        new CompletionHandler<Integer, RequestState>() {
    @Override
    public void completed(Integer n, RequestState state) {
        // Operation hoàn tất trước timeout.
    }

    @Override
    public void failed(Throwable error, RequestState state) {
        // Có thể là InterruptedByTimeoutException.
    }
});
~~~

**Đây là đoạn minh họa**, với RequestState tự định nghĩa; không phải chương trình độc lập. Cần phân biệt:

| Cơ chế | Bảo đảm/hiệu ứng |
|---|---|
| **Future.get(2, SECONDS)** | Caller chỉ đợi tối đa khoảng 2 giây; **TimeoutException không tự đảm bảo operation đã bị hủy hoặc channel đã đóng** |
| **read/write(..., timeout, unit, attachment, handler)** | Timeout của **operation** theo API; completion thất bại với **InterruptedByTimeoutException** khi quá hạn |
| **Deadline toàn request** | Chính sách ứng dụng: bao gồm connect, accept, read/write, parse, xử lý nghiệp vụ và response |
| **Future.cancel(...)** | Yêu cầu hủy Future theo hợp đồng; không được tự suy ra mọi byte/side effect đều được hoàn tác |
| **channel.close()** | Đóng channel để dừng sử dụng và giải phóng tài nguyên; operation đang pending có thể hoàn tất thất bại |
| **group.shutdown()/shutdownNow()** | Quản lý lifecycle nhóm channel/thread, không thay thế per-connection timeout |

**Bẫy nghiêm trọng của timeout read/write:** Javadoc Java 17 nói nếu operation timed out, **trạng thái ByteBuffer liên quan có thể không xác định** và provider có thể đặt chiều I/O của channel vào **error state implementation-specific** nếu không thể bảo đảm byte chưa bị đọc/ghi. Vì thế **không mặc nhiên retry cùng buffer trên cùng channel** sau InterruptedByTimeoutException. Với giao thức cần chắc chắn trạng thái, thường **đóng channel, bỏ buffer liên quan rồi tạo session/connection mới**, hoặc theo hợp đồng provider cụ thể nếu hiểu rõ.

**TimeoutException từ Future.get** chỉ chứng minh *thread đợi hết thời hạn*, không chứng minh I/O chưa diễn ra. Nếu mã code tiếp tục tái dùng ByteBuffer trong khi operation cũ vẫn pending, có thể vi phạm ownership và tạo lỗi dữ liệu. Cần hủy/đóng theo chính sách trước khi tái sử dụng state; tránh giả định cancel luôn làm remote chưa nhận byte.

### Connect và accept timeout

- **AsynchronousSocketChannel.connect(...)** không có overload nhận timeout ở API đang xét. Bạn có thể đợi Future với deadline bên ngoài rồi **đóng channel khi quá hạn**, hoặc điều phối bằng scheduler/CompletableFuture và đóng kết nối chưa hoàn tất theo policy.
- **AsynchronousServerSocketChannel.accept(...)** không có overload timeout tương tự timed read/write. Nếu đợi bằng **acceptFuture.get(timeout)**, timeout chỉ giới hạn caller; listener có thể vẫn đang accept. Đừng khởi tạo accept mới khi operation cũ còn pending.
- **System.nanoTime()** thích hợp đo **khoảng thời gian**, không dùng System.currentTimeMillis cho deadline vì wall-clock có thể thay đổi. Sử dụng **remaining budget** cho các operation nối tiếp thay vì mỗi lần lại cho đủ 5 giây.
- **DNS/name resolution** có thể xảy ra trước khi connect asynchronous được khởi tạo, tùy cách bạn tạo InetSocketAddress. Trong hệ thống thật, tính cả DNS và TLS/auth handshake vào tổng deadline.

**Timeout quá nhỏ và retry vô hạn** có thể tạo bão kết nối hoặc overload server. Hãy dùng số lần retry hữu hạn, exponential backoff + jitter, giới hạn pending connections, quan sát latency và phân biệt an toàn idempotency nếu client cần gửi lại request có side effect.

## 10. AsynchronousChannelGroup: thread pool và ownership

Hai channel có thể dùng **nhóm mặc định của JVM** qua **open()**, hoặc nhóm do ứng dụng tạo qua **open(group)**. **AsynchronousChannelGroup** quản lý các tài nguyên cần thiết để xử lý I/O completions và dispatch handlers, cùng với thread pool liên quan.

~~~text
AsynchronousChannelGroup
    |
    +-- thread pool / completion dispatch
    |
    +-- AsynchronousServerSocketChannel (listener)
    |
    +-- accepted AsynchronousSocketChannel(s)
    |
    +-- AsynchronousSocketChannel client(s)
~~~

Ví dụ khởi tạo nhóm trong Java 17, **đoạn code minh họa**:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
                4, runnable -> new Thread(runnable, "async-io"));

try (AsynchronousServerSocketChannel server =
             AsynchronousServerSocketChannel.open(group)) {
    server.bind(new InetSocketAddress(0));
    // Mở AsynchronousSocketChannel.open(group) nếu cần.
    // Khởi tạo và hoàn tất các operation trước khi dọn tài nguyên.
} finally {
    group.shutdown();
    group.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Đoạn trên giả định các import có sẵn, không phải file độc lập. Cần đóng **mọi accepted/client channel** thuộc group (nếu có), chờ callback hoàn tất và kiểm tra kết quả awaitTermination. **AsynchronousChannelGroup không phải AutoCloseable** trong Java 17; dùng **shutdown** và **awaitTermination**, không đặt group trực tiếp vào try-with-resources.

### Mỗi accepted channel thuộc group nào?

Nếu listener được mở trong một **AsynchronousChannelGroup**, các accepted AsynchronousSocketChannel của listener cũng thuộc **cùng group**. Điều này giúp quản lý tài nguyên rõ ràng, nhưng cũng có nghĩa **callback nặng** trên group có thể làm ảnh hưởng các connection khác.

### shutdown và shutdownNow

- **group.shutdown()** bắt đầu dừng có trật tự: ngăn tạo channel mới gắn với group; group chỉ kết thúc khi các channels liên quan đóng, callbacks đang chạy hoàn thành và tài nguyên được giải phóng.
- **group.shutdownNow()** dừng mạnh hơn, đóng các channels trong group; các operation pending có thể thất bại.
- **group.awaitTermination(...)** chờ group kết thúc, có thể chặn thread gọi; kiểm tra giá trị boolean trả về.
- **Không tự ý shutdown executor do group sở hữu** ở một nơi khác trong ứng dụng; tài liệu group cảnh báo việc kết thúc executor trực tiếp có thể có hành vi không xác định.
- **Không dùng pool cố định rất nhỏ rồi gọi get() chờ future khác trong callback cùng pool**: có thể gây starvation hoặc deadlock. Dispatch kết quả ngắn, chuyển tác vụ CPU/blocking business sang executor riêng có giới hạn.

**Không tồn tại quy tắc mọi OS đều dùng cùng implementation.** NIO.2 API cung cấp contract async, còn provider có thể dùng cơ chế native hoặc threads/helper I/O tùy platform. Không suy rằng async hoàn toàn không chiếm thread hoặc async luôn nhanh hơn blocking I/O.

## 11. Vòng đời và cleanup đáng tin cậy

Một thiết kế production nên phân biệt **listener lifecycle**, **accepted connection lifecycle** và **request lifecycle**:

1. Listener bind, bắt đầu một accept pending.
2. Khi accept hoàn thành, kiểm tra shutdown policy; nếu còn nhận tải, re-arm accept.
3. Gắn **ConnectionContext** cho accepted channel: parser, outgoing queue, ByteBuffer ownership, read/write pending flags, authentication status, deadline, số bytes, request IDs.
4. Chạy một read chain theo connection và tối đa một write chain; hai chiều có thể hoạt động song song.
5. Nếu có message hoàn chỉnh, validate/framing và chuyển xử lý nghiệp vụ sang pool phù hợp; giới hạn active tasks và queue.
6. Nếu response tới, xếp ByteBuffer vào write queue, kích hoạt write chain nếu chưa có writer.
7. Khi lỗi, EOF, timeout hoặc cancellation: hoàn tất Future/response đúng một lần, đóng channel, giải phóng buffer và state, giảm metrics active connections.
8. Khi shutdown server: dừng re-arm accept, đóng listener, xử lý drain/close accepted clients theo deadline, rồi shutdown group nếu group thuộc ownership của server.

**Closing listener không tự đóng mọi accepted peer.** Đóng từng accepted AsynchronousSocketChannel và giải phóng attachment/state. Với group mặc định, ứng dụng thường không trực tiếp shutdown toàn bộ JVM default group; chỉ đóng channels do mình sở hữu. Nếu tạo group riêng cho server, quản lý kết thúc group rõ ràng.

**Closing một channel không bảo đảm mọi callback đã chạy xong tại thời điểm close trả về.** Thiết kế callback theo trạng thái **OPEN/CLOSING/CLOSED**, tránh tạo operation mới khi đang đóng, và dùng atomic/lock thích hợp để tránh double completion hoặc double resource release.

## 12. Những lỗi và exception thường gặp

| Lỗi/exception | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **AcceptPendingException** | Gọi accept hai lần khi lần đầu còn pending trên listener | Một accept owner; re-arm khi hoàn tất |
| **NotYetBoundException** | accept trước bind | Bind listener trước khi accept |
| **NotYetConnectedException** | read/write trên async client chưa connect thành công | Đợi completion của connect |
| **ConnectionPendingException** | connect mới trong khi connect cũ đang pending | Không bắt đầu connect lần hai; chờ/cancel/close có kiểm soát |
| **AlreadyConnectedException** | connect lại channel đã connected | Tái dùng connection cho I/O, không connect lại |
| **ReadPendingException** | Hai reads đang pending trên một channel | Serialize read chain |
| **WritePendingException** | Hai writes đang pending trên một channel | Serialize write queue |
| **InterruptedByTimeoutException** | Timed async read/write quá hạn | Xem channel/buffer state không xác định; thường close và xử lý lỗi |
| **ExecutionException** | Future.get nhận kết quả operation thất bại | Xem getCause(), không che lỗi |
| **TimeoutException** | Future.get(timeout) hết thời hạn chờ | Không suy operation đã bị cancel; cleanup theo policy |
| **ClosedChannelException / AsynchronousCloseException** | Channel bị đóng khi operation còn diễn ra | Xử lý cancellation/cleanup bình thường nếu đang shutdown |
| **ShutdownChannelGroupException** | Group shutdown/terminated khi cố mở hoặc khởi tạo I/O | Không enqueue operation mới; đóng resources |
| **EOF: read trả -1** | Peer kết thúc chiều gửi | Xử lý framing và nửa đóng theo protocol; không phải ngoại lệ mặc định |

**IOException có thể được báo qua Future hoặc CompletionHandler.failed**, không nhất thiết ném đồng bộ ở điểm gọi async operation. Nhưng một số lỗi điều kiện tiên quyết (unbound, already pending, invalid buffer, closed group...) có thể được ném **ngay khi khởi tạo**. Vì vậy callback path đúng phải xử lý **cả synchronous initiation exception lẫn asynchronous completion failure**.

**Không bắt rồi bỏ qua mọi Throwable trong callback**. Lỗi phải được báo cho người điều phối yêu cầu, ghi log đủ thông tin và dọn resources. Với lỗi nghiêm trọng, tuân thủ chính sách giám sát và crash của hệ thống thay vì cố chạy tiếp trong trạng thái không kiểm soát.

## 13. Đặc điểm hiệu năng và rủi ro overload

Asynchronous API giúp tránh một thread chặn chờ cho mỗi connection trong nhiều kiến trúc, nhưng bottleneck vẫn có thể nằm ở:

- **Thời gian xử lý completion handler**, nhất là khi callback truy vấn DB blocking, giải mã payload quá lớn hoặc đợi một Future khác trên cùng pool.
- **Số accepted connections**: mỗi peer dùng tài nguyên kernel, buffer và Java objects; async không làm FD/network memory vô hạn.
- **Số bytes đang chờ ghi**: write queue không giới hạn dẫn tới tăng heap/direct memory và latency.
- **Đọc message không giới hạn**: nếu server tích tụ payload từ các client chậm mà không giới hạn byte, có rủi ro DoS.
- **Thread pool của AsynchronousChannelGroup** không phù hợp workload; completion callbacks bị starvation hoặc tranh tài nguyên.
- **Timeout và cancellation rối**: operation không còn được caller đợi nhưng buffer vẫn sống hoặc channel chưa được đóng.
- **Framing/TLS/auth**: async TCP vẫn phải xác định ranh giới message, xác thực và giao thức mã hóa phù hợp (TLS thường cần SSLEngine hoặc thư viện đã kiểm thử).

Các metrics nên thu thập: **active accepted channels**, accepts/second, **pending accepts**, **outstanding reads/writes per connection**, bytes in/out, write queue depth, completion latency, callback duration, group thread utilization, connection/operation timeouts, EOF/error rates, request latency p95/p99 và số channel được close.

Về backpressure, có thể tạm ngừng khởi tạo read mới trên connection khi business queue quá đầy, hạn chế đầu vào theo connection/tenant, giới hạn message size và write queue, và áp dụng admission control cho các accepted clients. Không chỉ tăng số threads hoặc pending operations một cách mù quáng.

## 14. Những lỗi lập trình tinh vi cần tránh

### 14.1. Read và write cùng ByteBuffer không đồng bộ

Một Buffer có thể đang được provider cập nhật position khi async operation còn pending. Nếu thread khác gọi **flip/clear/put** trên buffer ấy, payload hoặc bookkeeping có thể hỏng. Giữ **ownership một operation/buffer**, hoàn tất xong mới tái sử dụng hoặc trao quyền.

### 14.2. Future.get timeout rồi quên đóng connection

**Future.get(timeout)** giới hạn thread chờ, không tự đóng channel. Nếu trả TimeoutException mà caller bỏ Future và tiếp tục tái dùng buffer, operation cũ có thể vẫn hoàn thành và ghi lên dữ liệu đã được tái mục đích. Close/cancel theo hợp đồng, đợi cleanup khi cần và không hứa rằng packet/bytes chưa đến remote.

### 14.3. Đóng listener và quên accepted peer

AsynchronousServerSocketChannel sở hữu **listener**, còn accept trả channel cho connection riêng. Nếu server stop mà không có registry các accepted connections, chúng có thể tiếp tục sống hoặc giữ tài nguyên. Cần theo dõi và đóng từng peer.

### 14.4. Gọi accept đồng thời từ nhiều thread

Một listener chỉ cho **một accept pending**. Không dùng nhiều worker gọi accept bừa bãi; đợi completed rồi re-arm, hoặc tổ chức một accept coordinator. Nếu cần scale server, tăng số listener/instance theo kiến trúc và OS, không cố bẻ contract.

### 14.5. Cho rằng async callback chạy trên event-loop đơn

Completion handlers chạy qua **AsynchronousChannelGroup** và có thể chạy trên các thread khác nhau; thứ tự giữa callback của những operations độc lập không được bảo đảm như một luồng xử lý đơn. State đồng thời phải thread-safe, đặc biệt nếu một read callback và write callback cùng sửa connection context.

### 14.6. Dùng completed(n) như “đủ một message”

Số n chỉ là số byte của một lần read/write; cần giữ ByteBuffer, kiểm tra **hasRemaining**, framing và EOF. Với stream, không thể giả định client.write(1024) tương ứng một callback server.read(1024).

### 14.7. Không xử lý failed và synchronous initiation exception

**Completed** có thể không bao giờ xảy ra nếu operation thất bại; lỗi được đưa tới **failed** hoặc ném đồng bộ trước khi operation bắt đầu. Không để CompletableFuture/caller chờ vô hạn vì quên báo đường lỗi.

### 14.8. Không có read deadline hoặc write queue limit

Một client gửi 1 byte rồi ngừng có thể giữ read operation pending rất lâu. Dùng timed read và overall request deadline, đồng thời chấp nhận rằng timeout có thể làm buffer state không xác định; close khi phù hợp. Với client chậm đọc, queue response của server có thể đầy; áp dụng backpressure và giới hạn memory.

## 15. Chọn NIO.2 asynchronous hay mô hình khác?

| Tình huống | Một lựa chọn hợp lý | Lý do |
|---|---|---|
| Muốn học completion-style TCP API của Java | **AsynchronousServerSocketChannel/AsynchronousSocketChannel** | Future và CompletionHandler rõ ràng |
| Ít connection, I/O tuần tự đơn giản | **Socket/ServerSocket blocking** | Dễ phát triển và debug |
| Nhiều connection, đã có event loop Selector | **SocketChannel + Selector** | Kiểm soát readiness, buffer và scheduling |
| Dùng Java 21+ với nhiều I/O blocking | Có thể cân nhắc **virtual threads** | Mô hình lập trình tuần tự dễ hiểu, vẫn cần timeout/limit |
| Dịch vụ có framing, TLS, backpressure phức tạp | Framework networking đã được kiểm thử | Tránh tự viết lại nhiều tầng protocol |

Không có công thức **async luôn nhanh hơn blocking**. Phải đo theo loại workload, số kết nối, đặc tính callback, CPU/GC, cơ chế provider và hệ điều hành. NIO.2 asynchronous có API completion khác Selector; công cụ phù hợp phụ thuộc yêu cầu quản lý state và độ phức tạp của hệ thống.

## 16. Bài tập thực hành

### Bài tập A — Future và giới hạn độ dài

Chạy **AsyncFutureEchoDemo.java**. Đổi request thành chuỗi UTF-8 dài 1.024 byte; thay buffer cố định bằng giao thức **4-byte length-prefix**, đọc header trước rồi đọc đúng payload theo giới hạn. Giải thích vì sao không thể suy từ một Future.read trả về rằng message đã đủ.

### Bài tập B — Callback read từng phần

Chạy **AsyncHandlerDemo.java**, sửa buffer từ 4 lên 8 và client gửi đủ 8 byte. Đảm bảo callback chỉ complete CompletableFuture sau khi đã đọc đủ; khi peer đóng trước đó, chuyển sang completeExceptionally chứ không giải mã message thiếu.

### Bài tập C — Hai read pending

Trên một AsynchronousSocketChannel đã connected, khởi tạo read đầu tiên đang chờ byte, rồi cố khởi tạo read thứ hai. Quan sát **ReadPendingException** theo Java API và sửa kiến trúc thành một read chain duy nhất có quyền quản lý buffer.

### Bài tập D — Timeout operation khác wait timeout

So sánh **Future.get(100, MILLISECONDS)** với **channel.read(buffer, 100, MILLISECONDS, attachment, handler)**. Giải thích vì sao trường hợp đầu chỉ giới hạn chờ của caller, còn trường hợp sau hoàn tất thất bại bằng InterruptedByTimeoutException và có thể khiến buffer/channel state không xác định. Không tái dùng một buffer đang có operation cũ pending.

### Bài tập E — Re-arm accept

Từ AsyncHandlerDemo, xây dựng listener liên tục: mỗi lần accept callback completed, re-arm một accept mới rồi xử lý peer vừa nhận. Thêm số active connections tối đa và shutdown flag; khi dừng, không re-arm và đóng mọi peer được giữ.

### Bài tập F — AsynchronousChannelGroup

Mở group cố định bốn threads, gắn listener/client vào group ấy, ghi thread name trong callback (không dự đoán tên hoặc thứ tự). Thực nghiệm callback cố ý chặn lâu và quan sát throughput giảm; sau đó chuyển blocking business logic sang bounded worker pool. Dùng shutdown/awaitTermination đúng lifecycle.

### Bài tập G — Write queue và backpressure

Tạo client đọc rất chậm và server tạo nhiều response liên tục. Tổ chức outgoing ByteBuffer queue có giới hạn byte; không khởi tạo write thứ hai trước khi write trước đã hoàn tất. Đo write latency và queue depth. Khi vượt ngưỡng, từ chối hoặc tạm dừng sản xuất theo policy thay vì giữ vô hạn.

### Bài tập H — Đường lỗi và cleanup

Đóng client ngay khi server đang read; kiểm tra read trả -1 hoặc failed tùy tình huống. Thử đóng listener khi accept pending; đảm bảo callback/future báo lỗi, không để accepted channel bị rò. Với connect đến endpoint không phục vụ, xử lý lỗi ở Future/failed, đóng channel, không retry vô hạn.

## 17. Câu hỏi kiểm tra hiểu đúng

**1. AsynchronousServerSocketChannel có trực tiếp đọc dữ liệu của client không?** Không. Nó là listener; accept trả **AsynchronousSocketChannel** để đọc/ghi connection cụ thể.

**2. Future<Void>.get() của connect trả true?** Không; kiểu kết quả **Void**, get thành công trả **null**.

**3. Một listener có thể có hai accept đang pending không?** Không. Theo API sẽ có **AcceptPendingException**.

**4. Có thể có một read và một write đồng thời trên cùng async connection?** Có. Nhưng không được có hai reads pending hay hai writes pending cùng lúc.

**5. CompletionHandler.completed(n) là “đã đọc/ghi đủ message”?** Không. **n** chỉ số byte của *operation* ấy; cần kiểm tra remaining và framing.

**6. Callback có luôn chạy trên thread gọi operation không?** Không. Chúng được dispatch qua group; code xử lý state phải phù hợp concurrency.

**7. Future.get(timeout) có chắc đã hủy read khi timeout?** Không. Nó giới hạn caller đợi; operation có thể tiếp tục pending.

**8. Timed async read/write hết hạn có luôn an toàn để retry cùng ByteBuffer?** Không. Java 17 cảnh báo buffer có thể ở trạng thái không xác định và channel có thể ở error state implementation-specific.

**9. AsynchronousSocketChannel có dùng Selector OP_CONNECT và finishConnect?** Không. Đó là mô hình của **SocketChannel**; async connect thông báo bằng Future/CompletionHandler.

**10. Group.shutdown() có tức thì đóng mọi channel không?** Không. Orderly shutdown đợi các channels liên quan đóng và các callbacks xong; **shutdownNow()** mạnh hơn.

**11. Accepted channel được đóng khi listener.close() chứ?** Không nên giả định vậy; quản lý và đóng accepted peers riêng.

**12. Asynchronous I/O có làm hệ thống không cần thread, backpressure hay framing?** Không. Nó thay cách chờ I/O, không loại bỏ giới hạn OS/threads/memory hay trách nhiệm thiết kế protocol.

## Tài liệu chính thức để đối chiếu

- Java SE 17 — **AsynchronousServerSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html
- Java SE 17 — **AsynchronousSocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html
- Java SE 17 — **AsynchronousChannelGroup**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html
- Java SE 17 — **CompletionHandler**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html
- Java SE 17 — **ByteBuffer**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html

**Ghi nhớ:** **AsynchronousServerSocketChannel** nhận kết nối bằng **accept** bất đồng bộ và trả **AsynchronousSocketChannel** cho mỗi peer; **AsynchronousSocketChannel** thực hiện **connect/read/write** với **Future** hoặc **CompletionHandler**. Đừng chồng nhiều accept/read/write cùng chiều; đừng sửa ByteBuffer khi operation pending; luôn xử lý partial I/O, lỗi, EOF và timeout. **Future.get() có thể làm caller bị chặn, timed read/write có thể để buffer/channel state không xác định, và callback nặng có thể nghẽn group.** Thiết kế đúng cần framing, deadline, bounded queues, ownership, cleanup và quan sát tải.