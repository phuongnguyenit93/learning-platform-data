# So sánh I/O chặn, không chặn và bất đồng bộ trong Java Networking

Khi viết ứng dụng mạng, một kết nối TCP có thể đang chờ client gửi dữ liệu, chờ socket sẵn sàng để ghi, hoặc chờ thao tác đọc đã hoàn thành. Ba cách tổ chức việc chờ đó — **blocking I/O**, **non-blocking I/O** và **asynchronous I/O** — tạo ra mô hình lập trình, nhu cầu luồng và cách xử lý lỗi khác nhau. Chúng không phải ba mức “nhanh dần”: hiệu quả phụ thuộc số kết nối, tỷ lệ kết nối đang rảnh, lượng dữ liệu, công việc xử lý và cách triển khai.

**Sau bài này, bạn cần làm được:** phân biệt thời điểm lệnh gọi trả về với thời điểm dữ liệu thật sự đến; giải thích readiness so với completion; nhận diện Java API tương ứng; đọc được ví dụ socket của cả ba kiểu; chọn mô hình phù hợp và xử lý những lỗi phổ biến như đọc thiếu dữ liệu, ghi một phần, quá tải hàng đợi và đóng kết nối.

## 1. Cần phân biệt hai câu hỏi

**Câu hỏi 1 — Lệnh gọi có giữ luồng ở trạng thái chờ không?**

- **Blocking:** một lệnh như đọc socket có thể giữ luồng gọi chờ cho đến khi có dữ liệu, EOF, lỗi hoặc timeout. Trong lúc đó, luồng không tiếp tục chạy các câu lệnh kế tiếp.
- **Non-blocking:** lệnh đọc/ghi thử tiến hành ngay và trả về kết quả hiện có; chẳng hạn đọc từ một SocketChannel ở chế độ non-blocking có thể trả về **0** vì hiện chưa có byte nào. Ứng dụng tự quyết định khi nào thử lại.
- Chú ý: lệnh non-blocking vẫn là một lệnh gọi **đồng bộ** theo nghĩa lệnh trả về kết quả của lần thử ngay tại chỗ. “Non-blocking” và “asynchronous” không đồng nghĩa.

**Câu hỏi 2 — Ứng dụng được báo “có thể thử” hay “đã hoàn tất”?**

- **Readiness (sẵn sàng):** hệ thống báo socket có dấu hiệu có thể đọc/ghi mà không phải chờ lâu. Ứng dụng vẫn phải tự gọi **read/write** và kiểm tra kết quả. Java NIO **Selector** đi theo cách này.
- **Completion (hoàn tất):** ứng dụng phát động thao tác và nhận một **Future** hoặc **CompletionHandler**; kết quả được cung cấp khi thao tác hoàn thành hoặc thất bại. Java NIO.2 **AsynchronousSocketChannel** đi theo cách này.

Dòng thời gian khái niệm:

~~~text
Blocking:
  read() --------[luồng đợi dữ liệu]--------> trả về n / -1 / lỗi

Non-blocking + readiness:
  read() -> 0 -> đăng ký OP_READ -> select() báo sẵn sàng
                                     -> read() -> n / 0 / -1 / lỗi

Asynchronous + completion:
  phát động read(buffer, handler) -> trả về ngay
  ... ứng dụng có thể làm việc khác ...
  completed(n) / failed(error) khi thao tác kết thúc
~~~

**Điểm cốt lõi:** readiness chỉ là tín hiệu để **thử I/O**; completion là thông báo **kết quả của I/O đã yêu cầu**. Mô hình asynchronous không bảo đảm mỗi thao tác được kernel thực hiện thuần túy bất đồng bộ; nhà cung cấp Java có thể dùng cơ chế hệ điều hành hoặc luồng nền để triển khai.

## 2. Bảng so sánh nhanh

| Tiêu chí | Blocking I/O | Non-blocking I/O | Asynchronous I/O |
|---|---|---|---|
| Java API điển hình | **Socket**, **ServerSocket**, **InputStream/OutputStream** | **SocketChannel**, **ServerSocketChannel** với **configureBlocking(false)**, **Selector** | **AsynchronousSocketChannel**, **AsynchronousServerSocketChannel** |
| Khi chưa có dữ liệu để đọc | Lệnh đọc chờ | Lệnh đọc có thể trả **0** | Đã khởi động thao tác; kết quả đến qua Future/handler |
| Tín hiệu điều phối | Luồng chờ tại lời gọi | **SelectionKey**: OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE | **CompletionHandler.completed/failed** hoặc **Future** |
| Mô hình phổ biến | Một luồng xử lý cho mỗi kết nối/tác vụ; cũng có thể dùng virtual threads trên Java 21+ | Một hoặc vài event loop quản lý nhiều socket | Callback, Future, nhóm luồng hoàn tất |
| Độ phức tạp | Thấp cho luồng nghiệp vụ tuần tự | Cao hơn: trạng thái kênh, interestOps, buffer, partial I/O | Cao hơn: callback, vòng đời thao tác, pending I/O |
| Điểm mạnh | Dễ đọc, debug, phối hợp thư viện đồng bộ | Hợp nhiều kết nối nhàn rỗi và điều phối readiness | Không buộc luồng gọi chờ mỗi kết quả; API completion rõ ràng |
| Rủi ro | Nhiều platform threads, hàng đợi/thread pool quá tải | Busy loop, quên xử lý kết quả 0/ghi thiếu, chặn event loop | Callback phức tạp, luồng completion bị chặn, read/write chồng nhau |

Không nên suy từ bảng rằng non-blocking hay asynchronous tự động nhanh hơn. Ví dụ một dịch vụ có vài kết nối và xử lý đơn giản có thể dùng blocking code với độ trễ và mức bảo trì tốt hơn. Ngược lại, hàng chục nghìn kết nối lâu sống nhưng ít hoạt động có thể làm mô hình mỗi kết nối một platform thread trở nên tốn tài nguyên.

## 3. Blocking I/O — mã tuần tự, điểm chờ rõ ràng

Trong Java networking truyền thống, **ServerSocket.accept()** chờ kết nối mới, **Socket.getInputStream().read()** chờ dữ liệu hoặc EOF, còn **Socket.getOutputStream().write(...)** có thể chờ khi không gian bộ đệm gửi bị giới hạn. Một lệnh write trả về chỉ có nghĩa dữ liệu đã được tầng gửi chấp nhận theo hợp đồng của API; **không** chứng minh ứng dụng ở đầu kia đã đọc/xử lý dữ liệu đó.

Ví dụ Java 17 dưới đây dùng địa chỉ loopback, cổng tạm do hệ điều hành cấp, một luồng phục vụ server và một client. Protocol minh họa chỉ trao đổi **một byte**: client gửi chữ **A** (65), server trả chữ **B** (66).

**BlockingEchoDemo.java**

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BlockingEchoDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server = new ServerSocket(0, 10, loopback)) {
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<?> handling = executor.submit(() -> {
                    try (Socket peer = server.accept()) {
                        int request = peer.getInputStream().read();
                        if (request == -1) {
                            throw new EOFException("Client đóng trước khi gửi");
                        }
                        peer.getOutputStream().write(request + 1);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });

                try (Socket client = new Socket(loopback, server.getLocalPort())) {
                    client.setSoTimeout(3_000);
                    client.getOutputStream().write('A');

                    int reply = client.getInputStream().read();
                    if (reply == -1) {
                        throw new EOFException("Server đóng trước khi phản hồi");
                    }
                    System.out.println("Client nhận: " + (char) reply);
                }
                handling.get(3, TimeUnit.SECONDS);
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 BlockingEchoDemo.java
java BlockingEchoDemo
~~~

Kết quả khi chạy bình thường:

~~~text
Client nhận: B
~~~

Ở luồng phục vụ, **accept()** đợi kết nối và **read()** đợi một byte. Ở luồng client, **read()** đợi phản hồi. Ta cần luồng riêng cho server vì nếu đặt **accept()** rồi mới tạo client trong cùng một luồng thì chương trình không tự tiến triển.

**Ưu điểm:** logic tuần tự dễ theo dõi, thích hợp công cụ nhỏ, tương tác tuần tự hoặc dịch vụ sử dụng thư viện có API đồng bộ. **Giới hạn:** nếu dành một platform thread cho từng client và số lượng client nhàn rỗi tăng mạnh, bộ nhớ stack, scheduling và giới hạn thread pool có thể trở thành nút thắt. **Timeout:** **Socket.setSoTimeout(...)** trong ví dụ áp dụng cho lệnh đọc socket; nó không thay thế timeout kết nối, timeout ghi hoặc deadline của toàn request. Với connect, dùng overload **Socket.connect(address, timeout)** khi cần.

## 4. Non-blocking I/O — thử ngay, chờ readiness bằng Selector

**java.nio.channels.SocketChannel** có thể bật **configureBlocking(false)**. Khi ấy **read(ByteBuffer)** trả về:

- **n > 0:** đã đọc n byte; vị trí ByteBuffer tăng tương ứng;
- **n = 0:** lần thử này không đọc được byte nào; không được coi là EOF hay lỗi;
- **n = -1:** đầu kia đã kết thúc luồng nhận đọc của kết nối (EOF).

Với **write(ByteBuffer)**, giá trị trả về là số byte ghi trong **lần gọi ấy** và có thể nhỏ hơn số byte còn trong buffer, kể cả 0. Buffer tiếp tục giữ position để lần sau gửi phần còn lại. TCP là dòng byte, không bảo toàn ranh giới của một lần **write** thành một lần **read**.

Thay vì thử đọc liên tục rồi tiêu tốn CPU, ứng dụng đăng ký các kênh với **Selector**:

1. Mở **ServerSocketChannel**, đặt non-blocking và đăng ký **OP_ACCEPT**.
2. **selector.select()** đợi ít nhất một sự kiện sẵn sàng; lệnh **select** có thể chặn **luồng event loop**, dù chính các socket đã ở chế độ non-blocking.
3. Duyệt selected keys, lấy ra khỏi tập selected keys, kiểm tra **isValid()**, rồi xử lý **accept/read/write**.
4. Với kết nối chưa hoàn thành, dùng **OP_CONNECT** và **finishConnect()**; với dữ liệu gửi còn tồn, chỉ bật **OP_WRITE** khi thật sự cần.

Ví dụ Java 17 tự chứa dưới đây cho thấy **server** xử lý accept/read bằng readiness. Client giữ chế độ blocking để rút gọn phần mô phỏng. Đây là một giao thức **một byte**, không phải bộ đọc message tùy ý.

**NonBlockingSelectorDemo.java**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.util.Iterator;

public class NonBlockingSelectorDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());

                ByteBuffer outgoing = ByteBuffer.wrap(new byte[] {'A'});
                while (outgoing.hasRemaining()) {
                    client.write(outgoing);
                }

                boolean received = false;
                while (!received) {
                    selector.select();
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();

                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();
                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(1));
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer input = (ByteBuffer) key.attachment();
                            int n = peer.read(input);
                            if (n == -1) {
                                peer.close();
                                throw new IllegalStateException(
                                        "Client đóng trước khi gửi");
                            }
                            if (!input.hasRemaining()) {
                                input.flip();
                                System.out.println(
                                        "Server nhận: " + (char) input.get());
                                peer.close();
                                received = true;
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NonBlockingSelectorDemo.java
java NonBlockingSelectorDemo
~~~

~~~text
Server nhận: A
~~~

**Điều đáng quan sát:** lệnh **server.accept()** chỉ được gọi sau khi key sẵn sàng; **peer.read(input)** có thể trả 0 nên chương trình **không** dùng 0 như tín hiệu đóng. Việc **it.remove()** ngăn xử lý lại sự kiện cũ trong tập selected keys. **ByteBuffer.flip()** chuyển từ chế độ ghi vào buffer sang chế độ đọc từ buffer. Vì mẫu chỉ cần đúng một byte, vòng lặp hoàn tất khi buffer đầy; giao thức thực phải tích lũy nhiều byte và phân tách message.

**Selector không phải bộ điều phối nghiệp vụ tự động.** Nếu ở callback xử lý **OP_READ** bạn gọi database đồng bộ, ngủ, giải mã nặng hoặc chờ một API khác, cả event loop có thể bị chặn, khiến những socket khác phải đợi. Công việc dài cần được chuyển sang worker phù hợp, có giới hạn hàng đợi và cơ chế đưa kết quả về loop nếu cần.

Một lỗi kinh điển là bật **OP_WRITE** thường trực: socket thường xuyên sẵn sàng ghi, làm **select()** thức dậy liên tục và CPU tăng dù không còn dữ liệu cần gửi. Chỉ đăng ký OP_WRITE khi queue ghi có dữ liệu chưa gửi hết; tắt nó sau khi đã drain queue. Ngược lại, luôn duy trì **OP_READ** mà không có ngưỡng kiểm soát sẽ khiến buffer và queue xử lý tăng vô hạn trước một client gửi quá nhanh.

## 5. Asynchronous I/O — yêu cầu thao tác, nhận completion

**AsynchronousSocketChannel** và **AsynchronousServerSocketChannel** thuộc NIO.2. Với kiểu này, thao tác **connect/accept/read/write** có thể được phát động ngay và hoàn tất sau đó qua:

- **Future**: gọi **read(buffer)** hoặc **write(buffer)** nhận Future kết quả. Gọi **Future.get()** sẽ **chặn chính luồng đang get** cho đến khi có kết quả; vì vậy chỉ “dùng API async” không đồng nghĩa phần còn lại của chương trình không chặn.
- **CompletionHandler**: gọi overload có **attachment** và handler. Khi hoàn tất, **completed(result, attachment)** được gọi; khi thất bại, **failed(error, attachment)** được gọi. Code không nên dựa vào giả định callback luôn chạy trên một luồng cụ thể hoặc không bao giờ có tranh chấp.

Ví dụ Java 17 tiếp theo dùng Future để hoàn tất bước kết nối/accept cho dễ khởi tạo, nhưng thao tác **đọc dữ liệu** thực sự dùng **CompletionHandler** và tín hiệu **CompletableFuture**. Main đợi ở rìa chương trình để giữ demo chạy đến khi nhận kết quả; một server thực sẽ tiếp tục điều phối công việc mà không chặn hàng loạt luồng chỉ để đợi một read.

**AsyncCallbackDemo.java**

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class AsyncCallbackDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> accepting = server.accept();

            try (AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open()) {
                client.connect(server.getLocalAddress())
                        .get(3, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel peer =
                             accepting.get(3, TimeUnit.SECONDS)) {
                    CompletableFuture<Byte> completedRead =
                            new CompletableFuture<>();
                    ByteBuffer input = ByteBuffer.allocate(1);

                    peer.read(input, null,
                            new CompletionHandler<Integer, Void>() {
                        @Override
                        public void completed(Integer n, Void ignored) {
                            if (n == -1) {
                                completedRead.completeExceptionally(
                                        new IllegalStateException("EOF"));
                            } else if (input.hasRemaining()) {
                                peer.read(input, null, this);
                            } else {
                                input.flip();
                                completedRead.complete(input.get());
                            }
                        }

                        @Override
                        public void failed(Throwable error, Void ignored) {
                            completedRead.completeExceptionally(error);
                        }
                    });

                    ByteBuffer output = ByteBuffer.wrap(new byte[] {'A'});
                    while (output.hasRemaining()) {
                        client.write(output).get(3, TimeUnit.SECONDS);
                    }

                    byte value = completedRead.get(3, TimeUnit.SECONDS);
                    System.out.println("Server nhận: " + (char) value);
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncCallbackDemo.java
java AsyncCallbackDemo
~~~

~~~text
Server nhận: A
~~~

Callback không trả n trực tiếp cho câu lệnh **peer.read(...)**. Nó hoàn tất **completedRead** khi một byte đã vào buffer; với trường hợp chưa đủ dữ liệu, nó phát động đọc tiếp **sau khi** thao tác trước hoàn thành. Nếu có exception/EOF, nó hoàn tất tương ứng thay vì để main chờ vô hạn.

**Lưu ý về pending operations:** với **AsynchronousSocketChannel**, không phát động hai lần đọc cùng lúc trên cùng một channel khi lần đọc trước còn pending, nếu không có thể gặp **ReadPendingException**; tương tự các lần ghi chồng nhau có thể gặp **WritePendingException**. Nên tuần tự hóa read, tuần tự hóa write, quản lý queue và trạng thái đóng; không tự đồng nhất “nhiều callback” với “mọi thao tác đều chạy song song an toàn”.

**Chú ý triển khai:** completion handler thường được điều phối bằng các luồng của channel group hoặc cơ chế của provider. Một callback làm CPU nặng hoặc gọi code blocking có thể chiếm luồng dùng cho nhiều completion khác. Async API giúp tách thời điểm yêu cầu khỏi thời điểm kết quả nhưng không xóa chi phí luồng, bộ nhớ, copy dữ liệu hoặc kernel.

## 6. Nhìn cùng một kết nối dưới ba góc

Giả sử 10.000 client kết nối tới server nhưng phần lớn mỗi vài giây mới gửi một gói nhỏ:

- **Blocking với một platform thread/client:** rất nhiều luồng có thể đang đứng ở **read()**; cách viết dễ nhưng số luồng, stack và context switch có thể trở thành chi phí đáng kể. Nếu giới hạn thread pool quá thấp, kết nối mới có thể phải đợi; nếu tạo vô hạn, tài nguyên máy có thể cạn.
- **Non-blocking + Selector:** một số ít event loop gọi **select()**, chỉ xử lý socket khi readiness xuất hiện. Mô hình tốt cho kết nối rảnh nhiều nhưng cần buffer, trạng thái từng kết nối, xử lý ghi từng phần và backpressure thật cẩn thận.
- **Asynchronous + completion:** ứng dụng đăng ký thao tác chờ hoàn tất, sau đó tiếp tục xử lý khi callback/Future có kết quả. Phù hợp khi tầng ứng dụng đã tổ chức theo completion, nhưng vẫn phải đo số callback, số luồng nền và khả năng giữ thứ tự.

Giả sử chỉ 20 client, mỗi request phải xử lý CPU 200 ms: chuyển read từ blocking sang non-blocking **không làm CPU giảm**. Nếu xử lý CPU ngay trên selector loop, 20 client thậm chí có thể phản hồi chậm hơn vì loop bị chiếm. Khi đó chiến lược cho tác vụ CPU và giới hạn mức đồng thời có ý nghĩa hơn việc đổi socket API.

**Java 21+ bổ sung một lựa chọn đáng cân nhắc:** virtual threads cho phép giữ phong cách lập trình blocking tuần tự mà hỗ trợ lượng lớn tác vụ đồng thời với chi phí luồng thấp hơn platform threads trong nhiều tình huống I/O. Đây là lựa chọn của runtime/scheduler, **không** biến mỗi lời gọi **Socket.read()** thành callback **AsynchronousSocketChannel**. Các ví dụ ở đây dùng Java 17 nên không phụ thuộc virtual threads.

## 7. Những điều bất biến với cả ba mô hình

### 7.1. TCP là byte stream, phải có message framing

TCP không bảo toàn ranh giới message. Gửi một lần 2 KB có thể được nhận qua nhiều lần đọc; hai lần gửi có thể được gom thành một lần đọc. Đối với protocol thực, cần quy định rõ:

- **Delimiter** như ký tự xuống dòng; phải xét encoding, giới hạn chiều dài và delimiter nằm trong payload.
- **Length prefix** như 4 byte độ dài network byte order; đọc đủ header, kiểm tra length hợp lệ, rồi đọc đủ payload.
- **Fixed-size** khi định dạng thật sự cố định; hoặc protocol chuẩn đã định nghĩa framing.

**Không** dùng “một read là một request”. Ba ví dụ trên cố ý trao đổi một byte để minh họa đúng cơ chế chờ; chưa phải parser TCP đa message.

### 7.2. Đọc thiếu, ghi thiếu và EOF

Với **ByteBuffer**, kiểm tra **hasRemaining()**, **position/limit/flip/compact()**. Khi một message chưa đủ byte, giữ trạng thái để nhận tiếp; khi ghi chưa hết, giữ buffer trong outbound queue. Không bỏ phần dư sau một **write()** trả về số byte nhỏ hơn yêu cầu.

Kết quả **-1** trên read báo phía bên kia đóng hướng gửi (EOF); **0** từ non-blocking channel thường có nghĩa lần thử chưa tiến triển. EOF không có nghĩa mọi dữ liệu ứng dụng đã xử lý hoặc phản hồi đã được xác nhận. Có thể cần half-close, flush ở tầng ứng dụng và cơ chế xác nhận riêng của protocol.

### 7.3. Backpressure là chính sách, không phải tự nhiên có

Nếu client gửi nhanh hơn tốc độ parse/xử lý/ghi trả lời, queue có thể tăng vô hạn ở cả blocking, selector lẫn async. Nên có giới hạn cụ thể: số connection, số read pending, kích thước frame, tổng bytes đang giữ, outbound queue, thời gian chờ và tốc độ mỗi client.

Trong selector, có thể tạm ngưng quan tâm **OP_READ** cho connection đang quá tải rồi bật lại khi đã tiêu thụ dữ liệu. Trong async, chỉ phát động read tiếp khi hệ thống còn đủ năng lực. Nếu quá tải lâu, trả lỗi protocol hợp lệ hoặc đóng kết nối theo chính sách thay vì tiêu thụ vô hạn bộ nhớ.

### 7.4. Timeout, cancellation và close có phạm vi khác nhau

| Nhu cầu | Blocking API | Non-blocking/Selector | Asynchronous API |
|---|---|---|---|
| Chờ kết nối | **Socket.connect(addr, timeout)** | Deadline của ứng dụng + **OP_CONNECT/finishConnect()** | Theo dõi Future/callback và deadline |
| Chờ byte đọc | **Socket.setSoTimeout(...)** cho lệnh read | **select(timeout)** chỉ giới hạn thời gian đợi readiness; cần deadline **riêng cho mỗi connection/request** | Dùng overload đọc/ghi có timeout khi phù hợp, hoặc deadline/cancellation do ứng dụng quản lý |
| Dừng thao tác | Timeout/close/interrupt tùy API và trạng thái | Bỏ interest, hủy key, đóng channel | Cancel Future hoặc close channel, xử lý lỗi/callback khi hoàn tất |
| Giải phóng tài nguyên | Đóng socket/stream | Hủy key và đóng channel; giải phóng buffer/queue | Đóng channel; kết thúc channel group nếu ứng dụng sở hữu nó |

**Future.get(timeout)** chỉ giới hạn thời gian **luồng chờ Future**; việc get ném **TimeoutException** không bảo đảm thao tác I/O phía sau đã bị hủy. Với async, đừng tự phát động read mới trên cùng channel khi read trước có thể vẫn pending. Chọn một deadline end-to-end cho request và xác định rõ cách hủy, dọn dẹp, ghi log.

### 7.5. Lỗi, thứ tự và thread safety

Connection reset, EOF, timeout, đóng giữa chừng, lỗi parse và dữ liệu độc hại phải được xử lý ở cả ba mô hình. Với event loop/callback, callback có thể đụng trạng thái từ nhiều luồng: cần quy ước ai sở hữu buffer, ai được sửa queue, lúc nào được đóng channel. Tránh chia sẻ cùng một **ByteBuffer** để nhiều read/write độc lập sửa **position** đồng thời.

**Đừng coi I/O network là toàn bộ request.** DNS resolution, TLS handshake, database, logging đồng bộ, chuyển đổi JSON và logic ứng dụng có thể có các điểm blocking/CPU khác. Với TLS non-blocking, **SSLEngine** còn thêm trạng thái handshake, underflow/overflow và buffer ứng dụng/network; blocking **SSLSocket** thường dễ dùng hơn khi không có hạ tầng event loop thích hợp.

## 8. Chọn cách nào cho hệ thống của bạn?

| Bối cảnh | Lựa chọn nên xem xét trước | Vì sao |
|---|---|---|
| Công cụ CLI, proxy nhỏ, vài client, xử lý tuần tự | Blocking Socket, timeout rõ ràng | Đơn giản, dễ kiểm thử và vận hành |
| Server nhiều kết nối lâu sống, đa phần nhàn rỗi, cần kiểm soát event loop | Non-blocking SocketChannel + Selector hoặc framework đã chứng minh | Multiplex readiness trên ít luồng, chủ động backpressure |
| Ứng dụng đã có tầng completion/Future, muốn tách phát động I/O khỏi phản hồi | AsynchronousSocketChannel hoặc thư viện async thích hợp | Dễ tổ chức completion chain khi quản lý đúng trạng thái |
| Dịch vụ Java 21+ muốn code tuần tự cho rất nhiều tác vụ I/O | Blocking API với virtual threads, đồng thời đo tài nguyên | Giữ code dễ đọc mà giảm chi phí platform-thread-per-task trong nhiều trường hợp |
| Payload CPU nặng, phụ thuộc DB hoặc dịch vụ chậm | Chọn mô hình I/O theo workload, đồng thời giới hạn concurrency và tách worker | Đổi socket API không tự giải quyết CPU/DB bottleneck |

**Cách đánh giá thực tế:** đo cùng một workload với số connection đồng thời, tỷ lệ nhàn rỗi, kích thước frame, tốc độ yêu cầu, độ trễ p50/p95/p99, CPU, heap/direct memory, số thread, backlog, queue và tỷ lệ timeout. Đo trên protocol/framing, timeout và backpressure tương đương thì so sánh mới công bằng.

### Các ngộ nhận cần tránh

1. **“Non-blocking nghĩa là select() không chặn.”** Sai. Selector có thể chặn luồng đang đợi readiness; socket I/O của các channel được cấu hình mới là non-blocking.
2. **“Readable nghĩa là sẽ đọc hết một message.”** Sai. Readiness không cho biết số byte của message ứng dụng, và read có thể trả 0.
3. **“Async luôn dùng ít thread hơn.”** Không bảo đảm. Provider, callback, channel group và công việc xử lý quyết định số thread thực tế.
4. **“Một write tương ứng một read bên nhận.”** Sai với TCP: nó là stream.
5. **“Future.get có timeout là đã hủy I/O.”** Sai; timeout của thao tác chờ không tự động chứng minh I/O đã bị hủy.
6. **“Bật OP_WRITE mãi để không mất sự kiện.”** Thường tạo vòng lặp thức dậy liên tục; chỉ bật khi còn buffer phải gửi.
7. **“Dùng virtual thread là đã chuyển sang async callback.”** Sai. Đây là mô hình lập lịch luồng, API chương trình vẫn có thể blocking.

## 9. Bài tập tự kiểm chứng

1. **Chạy ba tệp Java 17** và quan sát output; đặt breakpoint ở **accept/read**, **selector.select/read**, và **CompletionHandler.completed** để xem nơi nào chờ, nơi nào nhận kết quả.
2. **Thay giao thức một byte bằng length-prefix:** client gửi 4 byte độ dài rồi đến payload UTF-8. Viết hàm đọc đủ 4 byte, validate 0 <= length <= mức tối đa, đọc tiếp đủ length; thử cố tình gửi payload thành nhiều đoạn và ghép nhiều message vào một socket.
3. **Thử partial write trên non-blocking:** dựng outbound queue, ghi cho đến khi **write** trả 0 hoặc buffer hết; chỉ bật **OP_WRITE** khi queue chưa rỗng. Quan sát CPU khi bật OP_WRITE thường trực để thấy lý do phải tắt nó.
4. **Thử client chậm và client ngắt giữa chừng:** đặt deadline, giới hạn queue, ghi log lý do close, xác minh không rò rỉ buffer/socket và không phát động hai async read pending.
5. **So sánh bằng đo đạc:** thử 100, 1.000 và nhiều kết nối nhàn rỗi hơn trong môi trường kiểm soát; giữ payload/timeout tương tự, đo cả p99 latency, bộ nhớ, thread count và CPU thay vì chỉ nhìn requests/second.

## 10. Kiểm tra hiểu đúng

- **Một non-blocking read trả 0: làm gì?** Giữ trạng thái buffer, đợi readiness phù hợp hoặc đến lần điều phối sau; không coi đó là EOF, không spin liên tục.
- **Selector báo OP_READ có phải packet hoàn chỉnh chưa?** Chưa; phải read, kiểm tra số byte rồi áp dụng framing ở tầng protocol.
- **Async read đã gọi handler, main vẫn gọi get(): có còn bất đồng bộ không?** Thao tác read có cơ chế completion bất đồng bộ, nhưng luồng đang gọi get vẫn bị chặn trong lúc chờ; cần phân biệt API I/O với cách tổ chức luồng gọi.
- **Điều gì quyết định khả năng mở rộng?** Hợp đồng protocol, số kết nối/tải, cơ chế đợi, chi phí mỗi request, callback/worker, giới hạn tài nguyên và backpressure — không chỉ tên API.

**Ghi nhớ:** **blocking** mô tả *luồng có phải chờ trong lời gọi*; **non-blocking + Selector** mô tả *thử I/O và được báo readiness*; **asynchronous** mô tả *phát động thao tác rồi nhận completion*. Cả ba đều phải đọc/ghi đúng số byte, xử lý EOF và timeout, giới hạn tài nguyên và đo trong tải thật.