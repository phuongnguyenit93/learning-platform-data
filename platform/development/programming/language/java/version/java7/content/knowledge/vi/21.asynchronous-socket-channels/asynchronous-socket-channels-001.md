# AsynchronousServerSocketChannel và chấp nhận kết nối trong Java

## 1. AsynchronousServerSocketChannel giải quyết bài toán gì?

Một TCP server cần **lắng nghe** các kết nối mới, **chấp nhận** từng kết nối, sau đó giao kết nối đã chấp nhận cho phần xử lý dữ liệu. Với cách lập trình blocking, thread có thể dừng ở lời gọi `ServerSocket.accept()` hoặc `ServerSocketChannel.accept()` trong chế độ blocking để đợi một client đến.

Java NIO.2 cung cấp `java.nio.channels.AsynchronousServerSocketChannel`, một server socket channel **bất đồng bộ**. Bạn khởi phát thao tác `accept()` rồi nhận kết quả qua **`Future<AsynchronousSocketChannel>`** hoặc **`CompletionHandler<AsynchronousSocketChannel,A>`**. Thread gọi không nhất thiết phải đứng đợi tại chính lệnh `accept`.

~~~text
Server (loopback hoặc địa chỉ mạng được phép)
    |
    +-- AsynchronousServerSocketChannel.open()
    |
    +-- bind(localAddress, backlog)
    |
    +-- accept() / accept(attachment, handler)
              |
              | Client thiết lập TCP connection
              v
        AsynchronousSocketChannel (đã chấp nhận)
              |
              +-- read(ByteBuffer) / write(ByteBuffer)
              +-- xử lý giao thức, giới hạn, xác thực
              +-- close() khi phiên kết thúc

Server tiếp tục accept cho kết nối tiếp theo.
~~~

**Điểm cốt lõi:** `AsynchronousServerSocketChannel` chỉ là **listener**; sau một lần accept thành công, bạn nhận được **`AsynchronousSocketChannel` riêng cho client**. Chính channel của client mới thực hiện read/write dữ liệu TCP. Listener có thể tiếp tục lắng nghe trong lúc các kết nối đã accept còn hoạt động.

### Mục tiêu học tập

1. Hiểu vòng đời `open → bind → accept → handle → accept again → close`.
2. Mở listener bằng `AsynchronousServerSocketChannel.open()` và `bind(SocketAddress)`.
3. Lấy cổng thật từ `getLocalAddress()` khi bind với port `0`.
4. Nhận một client bằng `Future<AsynchronousSocketChannel>` và `get(timeout, unit)`.
5. Nhận nhiều client bằng `CompletionHandler` và đăng ký lại `accept`.
6. Hiểu **chỉ một accept được pending trên một listener tại một thời điểm**, nhưng **nhiều kết nối đã được accept vẫn xử lý đồng thời**.
7. Phân biệt `NotYetBoundException`, `AcceptPendingException`, `AlreadyBoundException`, lỗi khi đóng, timeout chờ và lỗi I/O.
8. Biết tại sao `Future.get(timeout)` không phải timeout riêng của TCP accept.
9. Giao tiếp với `AsynchronousSocketChannel` qua `ByteBuffer`, xử lý partial read/write và TCP EOF.
10. Tổ chức `AsynchronousChannelGroup`, completion threads, shutdown và quyền sở hữu kênh.
11. Hiểu `backlog`, bind address, socket options, bảo mật và giới hạn tài nguyên.
12. Chạy các ví dụ tích hợp thật trên **loopback** mà không cố định cổng hay mở listener ra Internet.

**Phiên bản:** `AsynchronousServerSocketChannel` xuất hiện từ **Java 7** và vẫn được hỗ trợ trong Java hiện đại. Các ví dụ đầy đủ biên dịch bằng **Java 17+**; kiến thức/hợp đồng API đã được đối chiếu với tài liệu **Oracle Java SE 26**. Không dùng khái niệm legacy làm cách triển khai chính.

**Phạm vi an toàn của ví dụ:** Tất cả server trong mã chạy độc lập đều chỉ bind `InetAddress.getLoopbackAddress()` và **cổng 0** do hệ điều hành cấp, rồi đóng kênh bằng try-with-resources. Vì vậy chúng tạo kết nối **nội bộ trên máy**, không tự công bố dịch vụ công khai. Các stdout đã được đối chiếu trên JDK 17, nhưng môi trường không cho phép tạo socket có thể làm integration test thất bại; đó là hạn chế môi trường, không phải lý do giả kết quả.

## 2. Năm đối tượng/chức năng cần phân biệt

| Thành phần | Vai trò | Phương thức quan trọng |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | TCP listener nhận kết nối mới | `open`, `bind`, `accept`, `getLocalAddress`, `close` |
| `AsynchronousSocketChannel` | Một kết nối TCP tới client | `connect`, `read`, `write`, `shutdownInput`, `shutdownOutput`, `close` |
| `Future<AsynchronousSocketChannel>` | Kết quả pending của một lượt accept | `get`, `isDone`, `cancel` |
| `CompletionHandler<V,A>` | Callback khi thao tác xong hoặc thất bại | `completed(V,A)`, `failed(Throwable,A)` |
| `AsynchronousChannelGroup` | Cơ chế chia sẻ tài nguyên và thread pool cho async channels | `withFixedThreadPool`, `shutdown`, `awaitTermination` |

Nhầm lẫn thường gặp: cố gọi `read` trên listener hoặc nghĩ kết quả `accept()` là một boolean. Thực tế, server channel **không phải kết nối dữ liệu**; `accept` trả một **kênh client** đã kết nối khi thành công.

### 2.1. Hai kiểu accept

**Future-based:**

~~~java
Future<AsynchronousSocketChannel> pending = server.accept();
AsynchronousSocketChannel client =
        pending.get(5, TimeUnit.SECONDS);
~~~

**Handler-based:**

~~~java
server.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel client, Void att) {
        // Có một kết nối mới; quản lý close của client.
    }

    @Override
    public void failed(Throwable error, Void att) {
        // Xử lý lỗi accept.
    }
});
~~~

Cả hai đoạn là **minh họa trong phương thức** có `server` đã bind và import phù hợp. Chúng không phải class độc lập. Với Future, `get()` có thể **block thread gọi**. Với handler, callback được dispatch theo cơ chế nhóm kênh; thread gọi `accept` không phải đứng đợi để đọc kết quả.

**Không có overloaded `accept(timeout, unit)` như một timeout I/O riêng** trong API này. `future.get(timeout,unit)` chỉ giới hạn thời gian **thread chờ Future**, không tự ngừng nhận kết nối.

## 3. Vòng đời server: open trước, bind sau

Một server channel mới mở có trạng thái:

~~~text
open()  -> isOpen()==true, chưa bind
bind()  -> TCP listener gắn với local address/port
accept()-> bắt đầu chờ client kết nối
close() -> đóng listener, không tiếp tục accept
~~~

Mẫu mở:

~~~java
try (AsynchronousServerSocketChannel server =
             AsynchronousServerSocketChannel.open()) {
    server.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(), 0));

    InetSocketAddress local =
            (InetSocketAddress) server.getLocalAddress();

    System.out.println(local.getPort());
}
~~~

Đây là đoạn trong phương thức, có import `java.net.*` và `java.nio.channels.*`; số port thực tế khác nhau trên từng lần chạy. Đừng hardcode stdout chứa port. Trong mã kiểm thử đầy đủ, bài chỉ in boolean như `port>0` để output ổn định.

### 3.1. Tại sao port 0?

`new InetSocketAddress(loopbackAddress, 0)` yêu cầu hệ điều hành chọn **cổng TCP rảnh** cho listener. Dùng `server.getLocalAddress()` để lấy cổng đã được cấp, rồi client kết nối đúng tới địa chỉ đó.

Đây là cách phù hợp cho integration test cục bộ vì tránh xung đột với một cổng cố định như 8080/5000. Với dịch vụ production, cổng thường đến từ cấu hình và hệ thống triển khai.

### 3.2. Loopback và wildcard bind không giống nhau

- `new InetSocketAddress(InetAddress.getLoopbackAddress(), 0)`: listener chỉ nhận kết nối trên giao diện loopback thích hợp của máy.
- `new InetSocketAddress(0)` hoặc `bind(null)`: có thể bind địa chỉ wildcard theo semantics, khiến listener chấp nhận kết nối trên **nhiều giao diện mạng** hơn dự kiến.
- Nếu bạn không muốn công khai dịch vụ, **không dùng wildcard theo thói quen**; hãy kiểm soát bind address, firewall và quyền mạng.

Một server thực tế cần quyết định rõ chỉ phục vụ local process, mạng nội bộ hay mạng công cộng. `accept` chỉ xác nhận TCP connection được thiết lập; **không** xác thực người dùng hoặc bảo đảm dữ liệu có mã hóa.

### 3.3. Bắt buộc bind trước accept

Gọi `accept()` khi chưa `bind` sẽ ném `NotYetBoundException`. Đây là một lỗi trạng thái cần sửa trong cách khởi tạo server, không phải lỗi “chưa có client”.

Nguồn: [AsynchronousServerSocketChannel Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html).

## 4. Ví dụ 1 — Future accept rồi nhận PING từ client

Tạo file `FutureAcceptDemo.java`:

~~~java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class FutureAcceptDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            InetSocketAddress address =
                    (InetSocketAddress) server.getLocalAddress();

            Future<AsynchronousSocketChannel> pending =
                    server.accept();

            client.connect(address).get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                         pending.get(5, TimeUnit.SECONDS)) {
                ByteBuffer message = ByteBuffer.wrap(
                        "PING".getBytes(StandardCharsets.US_ASCII));

                while (message.hasRemaining()) {
                    int n = client.write(message)
                            .get(5, TimeUnit.SECONDS);
                    if (n <= 0) {
                        throw new AssertionError("No write progress");
                    }
                }

                ByteBuffer received = ByteBuffer.allocate(4);
                while (received.hasRemaining()) {
                    int n = accepted.read(received)
                            .get(5, TimeUnit.SECONDS);
                    if (n <= 0) {
                        throw new AssertionError("No read progress");
                    }
                }
                received.flip();

                System.out.println("ephemeralPort=" +
                        (address.getPort() > 0));
                System.out.println("serverIsLoopback=" +
                        address.getAddress().isLoopbackAddress());
                System.out.println("acceptedIsOpen=" +
                        accepted.isOpen());
                System.out.println("message=" +
                        StandardCharsets.US_ASCII.decode(received));
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 FutureAcceptDemo.java
java FutureAcceptDemo
~~~

Stdout đã kiểm chứng:

~~~text
ephemeralPort=true
serverIsLoopback=true
acceptedIsOpen=true
message=PING
~~~

### Giải thích theo thứ tự

1. Listener mở và bind vào **loopback, port 0**.
2. `server.getLocalAddress()` cho địa chỉ/cổng do hệ điều hành cấp.
3. `server.accept()` khởi phát một tác vụ nhận kết nối và trả `Future<AsynchronousSocketChannel>`; mã không gọi get ngay.
4. Client mở `AsynchronousSocketChannel`, khởi phát `connect(address)` rồi chờ kết nối thành công.
5. `pending.get(...)` trả **một AsynchronousSocketChannel đã accept**, riêng với listener và riêng với client-side channel.
6. Client dùng `write(ByteBuffer)` gửi bốn byte ASCII `PING`; vòng lặp không giả định một write luôn chuyển đủ bytes.
7. Server-side channel dùng `read(ByteBuffer)` nhận bốn byte và `flip()` để giải mã nội dung.
8. Các vòng read/write có timeout chờ và kiểm tra không tiến triển; fixture nhỏ giúp output xác định.
9. `accepted`, `client`, `server` đều được đóng đúng thứ tự nhờ try-with-resources.

**Không nhầm:** `server.accept()` không đọc dữ liệu `PING`; **`accepted.read()`** mới thực hiện điều đó. Listener chỉ chịu trách nhiệm đón một kết nối mới.

## 5. Mỗi accept là một kết nối mới, không phải một vòng lặp ngầm

Nếu server đã accept client A, nó **không tự tạo thêm accept pending** cho client B. Muốn tiếp tục nhận kết nối, phải gọi `accept` **một lần nữa** khi không còn accept đang chờ.

~~~text
server.accept() -> pending #1
   |
   +-- Client A connects
   |
   v
acceptedA = Future.get()   (accept #1 hoàn thành)
   |
   +-- server.accept() -> pending #2
            |
            +-- Client B connects
            |
            v
        acceptedB = Future.get()
~~~

**Một listener được phép có nhiều client channels đã accept vẫn mở**, nhưng **không được có hai accept operations đang pending cùng lúc**. Điều này khác với “chỉ phục vụ một client tại một thời điểm”.

### 5.1. Vì sao không gọi server.accept() hai lần ngay?

Theo Javadoc, nếu một accept vẫn pending mà một thread gọi thêm accept mới, sẽ phát sinh `AcceptPendingException`. Bản thân đối tượng server channel an toàn cho nhiều threads gọi, nhưng giới hạn **một pending accept** vẫn áp dụng.

Khi tác vụ accept trước đã hoàn tất, bạn có thể re-arm accept tiếp theo để luôn sẵn sàng đón client mới. Với nhiều client đang xử lý, phần xử lý của họ hoạt động qua những `AsynchronousSocketChannel` riêng biệt.

## 6. Ví dụ 2 — CompletionHandler và đăng ký lại accept

Dạng handler phù hợp với một listener chạy lâu dài: khi hoàn tất accept, **đăng ký accept kế tiếp**, rồi xử lý hoặc giao client vừa nhận cho session handler.

Đặc biệt, Javadoc dùng chính pattern `listener.accept(null, this)` ở đầu `completed` trước khi gọi hàm handle client.

Tạo `HandlerAcceptDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class HandlerAcceptDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel one =
                     AsynchronousSocketChannel.open();
             AsynchronousSocketChannel two =
                     AsynchronousSocketChannel.open()) {

            InetSocketAddress address =
                    (InetSocketAddress) server.getLocalAddress();
            CompletableFuture<Integer> done =
                    new CompletableFuture<>();
            AtomicInteger count = new AtomicInteger();
            AtomicBoolean attachmentMatches =
                    new AtomicBoolean(true);

            CompletionHandler<AsynchronousSocketChannel, String>
                    handler = new CompletionHandler<>() {
                @Override
                public void completed(
                        AsynchronousSocketChannel accepted,
                        String att) {
                    try {
                        attachmentMatches.compareAndSet(
                                true, "connections".equals(att));
                        int n = count.incrementAndGet();

                        if (n < 2) {
                            server.accept(att, this);
                        }
                        accepted.close();

                        if (n == 2) {
                            done.complete(n);
                        }
                    } catch (Throwable ex) {
                        done.completeExceptionally(ex);
                    }
                }

                @Override
                public void failed(Throwable ex, String att) {
                    done.completeExceptionally(ex);
                }
            };

            server.accept("connections", handler);

            one.connect(address).get(5, TimeUnit.SECONDS);
            two.connect(address).get(5, TimeUnit.SECONDS);

            System.out.println("acceptedCount=" +
                    done.get(5, TimeUnit.SECONDS));
            System.out.println("attachmentPreserved=" +
                    attachmentMatches.get());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 HandlerAcceptDemo.java
java HandlerAcceptDemo
~~~

Stdout:

~~~text
acceptedCount=2
attachmentPreserved=true
~~~

### Điểm cần đọc kỹ

- `server.accept("connections",handler)` bắt đầu chờ client đầu tiên.
- Mỗi lượt `completed(accepted,att)` nhận **một channel mới** cùng attachment.
- `count` đếm số accept thành công, dùng `AtomicInteger` cho callback thread.
- Khi chỉ mới nhận client thứ nhất, handler gọi `server.accept(att,this)` để đăng ký **lượt tiếp theo**.
- Khi đã nhận hai client, demo **không re-arm nữa** và hoàn tất `done`.
- `attachmentMatches` xác minh attachment `"connections"` được chuyển đúng qua cả hai lượt, không chỉ in true tùy ý.
- Demo đóng client channel ngay vì mục tiêu là **kiểm tra accept**, không xây ứng dụng giao tiếp dài hạn.
- Nếu callback thất bại, `failed` chuyển lỗi tới `done`; main nhận failure thay vì treo.

**Điểm phân biệt với production:** Khi xử lý client thật, nên re-arm accept rồi **giao accepted channel cho handler khác**, thay vì giữ callback accept làm tác vụ nặng. Nhớ xác định rõ **ai sở hữu và đóng** client channel nếu bước re-arm, xử lý client hoặc executor bị lỗi.

### 6.1. Vì sao không block ngay trong callback?

Completion handlers chạy qua thread pool liên kết với async channel group. Nếu callback accept phải đọc dữ liệu vài phút, gọi database chậm hoặc chờ lock lớn, nó có thể chiếm worker của group, giảm khả năng dispatch các completions khác. Nên:

1. Kiểm tra chính sách server còn chạy hay không.
2. Đăng ký accept tiếp theo khi phù hợp.
3. Chuyển accepted client sang session handler/queue.
4. Đảm bảo client đóng khi lỗi hoặc phiên kết thúc.
5. Trong nhánh failed, quyết định dừng/retry có kiểm soát; **đừng retry vô hạn không backoff** nếu server đã bị đóng hoặc group shutdown.

## 7. Ví dụ 3 — Lỗi NotYetBoundException và AcceptPendingException

Tạo file `AcceptErrorsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class AcceptErrorsDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open();
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            boolean unbound = false;
            try {
                server.accept();
            } catch (NotYetBoundException e) {
                unbound = true;
            }

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            Future<AsynchronousSocketChannel> first =
                    server.accept();

            boolean pendingRejected = false;
            try {
                server.accept();
            } catch (AcceptPendingException e) {
                pendingRejected = true;
            }

            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                         first.get(5, TimeUnit.SECONDS)) {
                System.out.println("unboundRejected=" + unbound);
                System.out.println("secondPendingRejected=" +
                        pendingRejected);
                System.out.println("acceptedAfterConnect=" +
                        accepted.isOpen());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AcceptErrorsDemo.java
java AcceptErrorsDemo
~~~

Stdout:

~~~text
unboundRejected=true
secondPendingRejected=true
acceptedAfterConnect=true
~~~

**Giải thích:**

- `accept()` khi listener chưa bind: `NotYetBoundException`.
- Sau khi bind, `first=server.accept()` tạo một accept đang pending.
- Không có client nào kết nối giữa hai lần gọi; `server.accept()` lần hai bị từ chối bằng `AcceptPendingException`.
- Client sau đó kết nối; Future của lượt đầu trả accepted channel như bình thường.
- Những exception này là **lỗi trạng thái sử dụng API**, không phải tín hiệu “TCP port đã hết cổng” hay “listener chỉ có thể phục vụ một client”.

Nếu một thread khác quản lý vòng accept, tránh để nhiều threads cùng gọi `accept` không phối hợp. Thường thiết kế **một owner accept loop** dễ đúng hơn.

## 8. Ví dụ 4 — Hai client được accept lần lượt, channel độc lập

Tạo `SequentialAcceptDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class SequentialAcceptDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel firstClient =
                     AsynchronousSocketChannel.open();
             AsynchronousSocketChannel secondClient =
                     AsynchronousSocketChannel.open()) {

            SocketAddress address = server.getLocalAddress();

            Future<AsynchronousSocketChannel> first =
                    server.accept();
            firstClient.connect(address)
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel firstAccepted =
                         first.get(5, TimeUnit.SECONDS)) {

                Future<AsynchronousSocketChannel> second =
                        server.accept();
                secondClient.connect(address)
                        .get(5, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel secondAccepted =
                             second.get(5, TimeUnit.SECONDS)) {
                    System.out.println("firstOpen=" +
                            firstAccepted.isOpen());
                    System.out.println("secondOpen=" +
                            secondAccepted.isOpen());
                    System.out.println("separateChannels=" +
                            (firstAccepted != secondAccepted));
                }
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SequentialAcceptDemo.java
java SequentialAcceptDemo
~~~

Stdout:

~~~text
firstOpen=true
secondOpen=true
separateChannels=true
~~~

**Điểm quan trọng:** Khi chấp nhận client B, server **không phải đóng accepted channel của client A**. Hai kết nối đã được chấp nhận có thể còn mở và được xử lý độc lập. Giới hạn một pending accept áp dụng cho **listener**, không áp dụng cho số lượng client channels đang mở sau accept.

Trong ví dụ, cả hai được mở và sau đó tự đóng bằng try-with-resources. Trong production, mỗi session thường có timeout, quota, backpressure và cleanup riêng.

## 9. Future.get(timeout) không phải timeout của accept

Một hiểu nhầm phổ biến:

~~~java
Future<AsynchronousSocketChannel> future =
        server.accept();

AsynchronousSocketChannel client =
        future.get(100, TimeUnit.MILLISECONDS);
~~~

Nếu chưa có client kết nối trong 100 ms, `get(...)` có thể ném `TimeoutException`. **Future không tự bị hủy** chỉ vì thread đợi hết thời gian. Tác vụ accept **vẫn có thể pending** và hoàn tất khi client đến sau đó.

Nếu mã bắt TimeoutException rồi gọi `server.accept()` ngay lần nữa mà không kiểm tra Future đang pending, bạn có thể gặp **AcceptPendingException**.

### 9.1. Ví dụ 5 — Hết hạn chờ, nhưng accept vẫn thành công sau

Tạo `AcceptFutureTimeoutDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class AcceptFutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> pending =
                    server.accept();

            boolean timedOut = false;
            try {
                pending.get(100, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            System.out.println("waitTimedOut=" + timedOut);
            System.out.println("futureStillPending=" +
                    !pending.isDone());

            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                         pending.get(5, TimeUnit.SECONDS)) {
                System.out.println("acceptLaterSucceeded=" +
                        accepted.isOpen());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AcceptFutureTimeoutDemo.java
java AcceptFutureTimeoutDemo
~~~

Stdout:

~~~text
waitTimedOut=true
futureStillPending=true
acceptLaterSucceeded=true
~~~

Ở thời điểm in, chưa có client được tạo kết nối trước đó. Sau khi timeout của **lượt chờ** xuất hiện, chương trình sử dụng **chính Future ban đầu** để nhận client mới. Không submit một accept thứ hai khi lượt đầu vẫn pending.

**Lưu ý production:** Nếu cần deadline cho việc chờ client, hãy định nghĩa policy hủy/đóng listener hoặc điều khiển accept loop; không tự coi `Future.get(timeout)` là timeout của kết nối TCP hoặc việc accept đã bị dừng. Lỗi timeout chờ và lỗi I/O là hai tình huống khác nhau.

## 10. Server.close() khi đang accept

Listener có thể được đóng khi vẫn còn một tác vụ accept chưa hoàn tất: ví dụ ứng dụng shutdown hoặc hủy dịch vụ. Khi đó, Future của accept có thể hoàn tất thất bại với nguyên nhân `AsynchronousCloseException` theo hợp đồng asynchronous channel.

### 10.1. Ví dụ 6 — Đóng listener làm Future accept thất bại

Tạo `ClosePendingAcceptDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class ClosePendingAcceptDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousServerSocketChannel server =
                AsynchronousServerSocketChannel.open();

        try {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            Future<AsynchronousSocketChannel> pending =
                    server.accept();

            server.close();

            boolean closedFailure = false;
            try {
                AsynchronousSocketChannel unexpected =
                        pending.get(5, TimeUnit.SECONDS);
                unexpected.close();
            } catch (ExecutionException e) {
                closedFailure =
                        (e.getCause()
                                instanceof AsynchronousCloseException);
            }

            System.out.println("pendingAcceptClosed=" +
                    closedFailure);
            System.out.println("serverOpen=" +
                    server.isOpen());
        } finally {
            server.close();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ClosePendingAcceptDemo.java
java ClosePendingAcceptDemo
~~~

Stdout trên môi trường kiểm thử:

~~~text
pendingAcceptClosed=true
serverOpen=false
~~~

**Giải thích:** Không có client kết nối trước khi đóng; accept còn pending và bị kết thúc do đóng listener. `pending.get()` trả lỗi qua `ExecutionException` với cause `AsynchronousCloseException`.

**Không nên:** Dùng `close` rồi tiếp tục gọi `accept` và kỳ vọng listener còn hoạt động. Shutdown nên ngăn accept mới, kết thúc các clients theo chính sách và đóng tài nguyên.

**Quan trọng:** Việc đóng listener **không đồng nghĩa tự động đóng mọi accepted client channel đã tồn tại**. Những channel đó là tài nguyên riêng, có thể cần dừng/đóng trong cơ chế session manager.

## 11. Chấp nhận kết nối khác với đọc/ghi trên socket

Sau khi server accept thành công, bạn có một `AsynchronousSocketChannel`. Nó làm việc với **TCP byte stream**, chứ không phải các gói có ranh giới message được bảo toàn. Một lần `client.write("HELLO")` **không đảm bảo** server chỉ cần một `read` là đủ năm byte.

### 11.1. Partial read/write và ByteBuffer

- `AsynchronousSocketChannel.read(ByteBuffer)` trả `Future<Integer>`; số byte đọc thực có thể nhỏ hơn `remaining()`.
- `write(ByteBuffer)` cũng có thể chuyển ít bytes hơn payload.
- Sau read thành công, `ByteBuffer.flip()` để chuyển sang trạng thái đọc từ buffer.
- Khi một read đang pending trên **cùng socket**, không initiate read mới khác: có thể nhận `ReadPendingException`.
- Tương tự, một write pending khác có thể dẫn tới `WritePendingException`.
- Có thể có **một read và một write outstanding cùng lúc** trên một `AsynchronousSocketChannel` theo hợp đồng; chúng là hai hướng dữ liệu khác nhau.
- Buffer được dùng trong một I/O pending không an toàn để sửa/đọc đồng thời; không tái sử dụng trước completion.
- Khi peer đóng hướng gửi dữ liệu đúng cách và không còn bytes, `read` có thể trả `-1`, biểu thị EOF.

### 11.2. TCP không giữ ranh giới thông điệp

Các bytes `HELLO` có thể được phân chia thành nhiều lượt read, hoặc nhiều lượt write có thể được ghép trong một read. Nếu xây giao thức yêu cầu nhiều message, cần **framing**, ví dụ:

- Header với độ dài payload (length prefix).
- Dấu phân cách (newline) với quy định escaping/encoding.
- Giao thức định dạng như HTTP được triển khai đúng chuẩn, hoặc một thư viện protocol đã kiểm chứng.

Không dùng mỗi lần callback read như “một thông điệp hoàn chỉnh”.

## 12. Ví dụ 7 — Mini echo: client gửi HELLO, server trả ACK:HELLO

Tạo `AsyncEchoDemo.java`:

~~~java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class AsyncEchoDemo {
    static void sendFully(
            AsynchronousSocketChannel ch,
            ByteBuffer src) throws Exception {
        while (src.hasRemaining()) {
            int n = ch.write(src).get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IllegalStateException(
                        "No write progress");
            }
        }
    }

    static void readFully(
            AsynchronousSocketChannel ch,
            ByteBuffer dst) throws Exception {
        while (dst.hasRemaining()) {
            int n = ch.read(dst).get(5, TimeUnit.SECONDS);
            if (n <= 0) {
                throw new IllegalStateException(
                        "Stream closed or no progress");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> f =
                    server.accept();
            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                         f.get(5, TimeUnit.SECONDS)) {

                sendFully(client, ByteBuffer.wrap(
                        "HELLO".getBytes(StandardCharsets.US_ASCII)));

                ByteBuffer buf = ByteBuffer.allocate(5);
                readFully(accepted, buf);
                buf.flip();
                String incoming =
                        StandardCharsets.US_ASCII.decode(buf).toString();

                sendFully(accepted, ByteBuffer.wrap(
                        ("ACK:" + incoming).getBytes(
                                StandardCharsets.US_ASCII)));

                ByteBuffer reply = ByteBuffer.allocate(9);
                readFully(client, reply);
                reply.flip();

                System.out.println("serverReceived=" + incoming);
                System.out.println("clientReceived=" +
                        StandardCharsets.US_ASCII.decode(reply));
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 AsyncEchoDemo.java
java AsyncEchoDemo
~~~

Stdout:

~~~text
serverReceived=HELLO
clientReceived=ACK:HELLO
~~~

### Tại sao có vòng lặp?

Đọc/ghi TCP stream có thể chỉ chuyển **một phần** ByteBuffer. `sendFully/readFully` ở đây lặp tới khi hoàn tất đúng kích thước fixture và chặn nếu có EOF/không tiến triển. Với giao thức thực, cần **framing**, giới hạn chiều dài frame, timeout, cancellation, quota và xử lý EOF đúng hơn thay vì luôn giả định kích thước 5/9.

Ví dụ sử dụng `Future.get` để kiểm chứng I/O và tránh đua kết quả khi in; do đó đây **không phải server event-driven production không blocking từ đầu tới cuối**. Các tác vụ I/O vẫn được khởi phát bằng asynchronous channels, còn cách chờ do test chọn.

**Bảo mật:** Socket TCP trong ví dụ **không có TLS** và chỉ chạy trên loopback. Nếu mở server ra mạng không tin cậy, cần mã hóa/xác thực, giới hạn request, kiểm soát nguồn, không chỉ thay bind address là đủ.

## 13. AsynchronousChannelGroup: thread pool và lifecycle

Các async channels được gắn với một `AsynchronousChannelGroup`. Nếu `open()` không truyền group, channel dùng **nhóm mặc định**. Một group có thread pool để xử lý completion events/callbacks và tài nguyên provider.

Những API thường dùng:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(
                2,
                runnable -> new Thread(runnable, "aio-worker"));

AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);

AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open(group);
~~~

Đây là đoạn minh họa. Việc tạo thread factory không tự áp đặt chính sách shutdown; đóng channel rồi `group.shutdown()`/`awaitTermination()` đúng lúc. Không bắt buộc mọi client của server thuộc cùng group nếu client do chương trình khác tạo; tuy nhiên **accepted client channel** từ listener thuộc **cùng group với server** theo Javadoc.

### 13.1. Callback thực thi ở thread nào?

Javadoc `AsynchronousChannelGroup` quy định handler của I/O được gọi bởi thread trong pool của group. Với một số I/O hoàn tất ngay, implementation có thể dispatch trong thread khởi phát nếu nó đã là pooled thread, nhưng riêng accept có chú ý đảm bảo handler **không được gọi trực tiếp bởi initiating thread khi kết nối được accept ngay**, để hỗ trợ concurrent handling.

Đừng giả định callback luôn thuộc main thread hoặc có thứ tự FIFO. Giữ callback ngắn, không block dài, không giữ lock dễ deadlock và không truy cập UI thread-confined state trực tiếp.

### 13.2. Khi shutdown group

- `group.shutdown()` khởi động orderly shutdown; group kết thúc khi các channel gắn với nó đã đóng, active handlers hoàn thành và tài nguyên được giải phóng.
- `group.awaitTermination(timeout,unit)` chờ nhóm kết thúc, giúp tránh thread leak trong ứng dụng/test.
- `group.shutdownNow()` ép đóng các channels gắn với group như thao tác `close`, có thể làm pending I/O thất bại.
- Đừng bắt đầu những channels mới trên group đã shutdown và kỳ vọng hoạt động.
- Server listener, accepted clients và client-side channels cần có ownership rõ ràng; group không thay thế quản lý session.

Nguồn: [AsynchronousChannelGroup Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html).

## 14. Ví dụ 8 — Server và client dùng group riêng

Tạo `ChannelGroupDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.util.concurrent.*;

public class ChannelGroupDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(
                        2,
                        r -> {
                            Thread t =
                                    new Thread(r, "asio-demo");
                            t.setDaemon(true);
                            return t;
                        });

        try {
            try (AsynchronousServerSocketChannel server =
                         AsynchronousServerSocketChannel.open(group)
                                 .bind(new InetSocketAddress(
                                         InetAddress.getLoopbackAddress(),
                                         0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {

                Future<AsynchronousSocketChannel> future =
                        server.accept();
                client.connect(server.getLocalAddress())
                        .get(5, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel accepted =
                             future.get(5, TimeUnit.SECONDS)) {
                    System.out.println("acceptedWithGroup=" +
                            accepted.isOpen());
                    System.out.println("clientConnected=" +
                            (client.getRemoteAddress() != null));
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
                group.shutdownNow();
            }
        }

        System.out.println("groupShutdown=" +
                group.isShutdown());
        System.out.println("groupTerminated=" +
                group.isTerminated());
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ChannelGroupDemo.java
java ChannelGroupDemo
~~~

Stdout:

~~~text
acceptedWithGroup=true
clientConnected=true
groupShutdown=true
groupTerminated=true
~~~

Đây là fixture nhỏ, đã đóng accepted/client/server trước khi `shutdown` group. Nó minh họa cách **quản lý lifetime của một group riêng** thay vì bỏ mặc thread pool. Hai threads chỉ là cấu hình test, không phải con số tối ưu cho mọi server.

## 15. Bind backlog, địa chỉ và socket options

`AsynchronousServerSocketChannel.bind(SocketAddress local,int backlog)` cho phép đặt độ dài gợi ý cho queue các connection indications đang chờ được chấp nhận. Cần hiểu:

- `backlog` **không phải** “số client tối đa server được phép phục vụ”.
- Giá trị có thể bị provider/OS điều chỉnh; khi `backlog<=0`, implementation dùng giá trị mặc định.
- Backlog liên quan đến kết nối **chưa được ứng dụng accept**, không phải số session đã accept.
- Với tải lớn, còn cần chính sách giới hạn active sessions, CPU, memory, retry, client timeouts và hệ thống bảo vệ mạng.
- Nếu client kết nối quá nhanh vượt khả năng xử lý, TCP connection có thể chậm/fail tùy OS; không có bảo đảm backlog tạo một hàng đợi vô hạn.

### 15.1. Socket options trên listener

Theo Javadoc, server channel hỗ trợ ít nhất `StandardSocketOptions.SO_RCVBUF` và `SO_REUSEADDR`; provider có thể hỗ trợ thêm.

~~~java
server.setOption(StandardSocketOptions.SO_REUSEADDR, true);
server.bind(new InetSocketAddress(loopback, 0), 16);
~~~

Đây là đoạn minh họa trong phương thức. `SO_REUSEADDR` **không** có nghĩa “nhiều listeners khác nhau sẽ được phép bind cùng IP:port tùy ý”; semantics phụ thuộc OS và không thay thế kiểm soát xung đột bind.

**TCP_NODELAY** là option thường dùng ở **AsynchronousSocketChannel** (kết nối dữ liệu), không phải option chuẩn được liệt kê cho server listener. Khi không chắc option có hỗ trợ, dùng `supportedOptions()`.

## 16. Ví dụ 9 — Bind port động, backlog và AlreadyBoundException

Tạo `BoundOptionsDemo.java`:

~~~java
import java.net.*;
import java.nio.channels.*;
import java.net.StandardSocketOptions;

public class BoundOptionsDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open()) {

            boolean initiallyUnbound =
                    server.getLocalAddress() == null;

            server.setOption(
                    StandardSocketOptions.SO_REUSEADDR, true);

            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0), 16);

            InetSocketAddress bound =
                    (InetSocketAddress) server.getLocalAddress();

            boolean alreadyBound = false;
            try {
                server.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
            } catch (AlreadyBoundException e) {
                alreadyBound = true;
            }

            System.out.println("initiallyUnbound=" +
                    initiallyUnbound);
            System.out.println("boundPortAssigned=" +
                    (bound.getPort() > 0));
            System.out.println("boundLoopback=" +
                    bound.getAddress().isLoopbackAddress());
            System.out.println("alreadyBoundRejected=" +
                    alreadyBound);
            System.out.println("supportsReuseAddr=" +
                    server.supportedOptions().contains(
                            StandardSocketOptions.SO_REUSEADDR));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 BoundOptionsDemo.java
java BoundOptionsDemo
~~~

Stdout:

~~~text
initiallyUnbound=true
boundPortAssigned=true
boundLoopback=true
alreadyBoundRejected=true
supportsReuseAddr=true
~~~

**Giải thích:**

1. Channel mở nhưng chưa bind, nên `getLocalAddress()==null`.
2. Cấu hình `SO_REUSEADDR` trước khi bind.
3. Bind loopback/port 0 với backlog đề nghị 16, nhận port thực.
4. Lần bind thứ hai trên cùng channel đã bind ném `AlreadyBoundException`.
5. Kiểm tra supported options giúp tránh áp dụng tùy chọn không được hỗ trợ cho provider khác.

Không kiểm tra backlog bằng cách cố nhồi hàng nghìn client vào listener, vì kết quả phụ thuộc hệ điều hành và có thể gây tải không cần thiết.

## 17. TCP EOF và shutdownOutput không phải server.close

TCP cho phép đóng riêng hướng gửi hoặc nhận của một kết nối, tùy trạng thái. `AsynchronousSocketChannel.shutdownOutput()` thông báo phía local không gửi thêm bytes; khi peer đã nhận hết dữ liệu, `read` trên peer có thể trả `-1`.

Điều này khác với đóng **listener**. `server.close()` dừng chấp nhận kết nối mới; `client.shutdownOutput()` ảnh hưởng hướng gửi của **một kết nối cụ thể**.

### 17.1. Ví dụ 10 — Client gửi BYE rồi kết thúc hướng gửi

Tạo `ClientHalfCloseDemo.java`:

~~~java
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.util.concurrent.*;

public class ClientHalfCloseDemo {
    public static void main(String[] args) throws Exception {
        try (AsynchronousServerSocketChannel server =
                     AsynchronousServerSocketChannel.open().bind(
                             new InetSocketAddress(
                                     InetAddress.getLoopbackAddress(), 0));
             AsynchronousSocketChannel client =
                     AsynchronousSocketChannel.open()) {

            Future<AsynchronousSocketChannel> future =
                    server.accept();
            client.connect(server.getLocalAddress())
                    .get(5, TimeUnit.SECONDS);

            try (AsynchronousSocketChannel accepted =
                         future.get(5, TimeUnit.SECONDS)) {

                ByteBuffer req = ByteBuffer.wrap(
                        "BYE".getBytes(StandardCharsets.US_ASCII));
                while (req.hasRemaining()) {
                    client.write(req).get(5, TimeUnit.SECONDS);
                }

                client.shutdownOutput();

                ByteBuffer result = ByteBuffer.allocate(3);
                while (result.hasRemaining()) {
                    int n = accepted.read(result)
                            .get(5, TimeUnit.SECONDS);
                    if (n < 0) {
                        throw new AssertionError("EOF too early");
                    }
                    if (n == 0) {
                        throw new AssertionError("no progress");
                    }
                }

                result.flip();
                int eof = accepted.read(
                        ByteBuffer.allocate(1))
                        .get(5, TimeUnit.SECONDS);

                System.out.println("payload=" +
                        StandardCharsets.US_ASCII.decode(result));
                System.out.println("eofAfterShutdownOutput=" +
                        eof);
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ClientHalfCloseDemo.java
java ClientHalfCloseDemo
~~~

Stdout:

~~~text
payload=BYE
eofAfterShutdownOutput=-1
~~~

Client gửi ba bytes, sau đó shutdown **hướng output**; server-side socket đọc đủ ba bytes rồi thấy EOF. Điều này là semantics TCP stream, không phải server listener tự ngắt mọi clients.

**Production:** Khi peer gửi EOF, hãy quyết định còn dữ liệu trả về không, xử lý half-close có được giao thức cho phép không, sau đó đóng session đúng lúc. Không xem EOF là một thông điệp nghiệp vụ “BYE” nếu giao thức không quy định.

## 18. Một pending accept nhưng nhiều session đồng thời: mô hình triển khai

Một server đơn giản có thể dùng:

~~~text
Listener (1 AsynchronousServerSocketChannel)
    |
    +-- accept pending: tối đa 1 cho listener này
    |
    +-- accepted client #1 --> session #1 --> async read/write
    |
    +-- accepted client #2 --> session #2 --> async read/write
    |
    +-- accepted client #3 --> session #3 --> async read/write
    |
    +-- re-arm accept để đón kết nối #4
~~~

Giới hạn một accept pending không ngăn nhiều **accepted channels** hoạt động. Hãy quản lý **session registry** (chẳng hạn `Set<AsynchronousSocketChannel>` đồng bộ thích hợp) để dừng/đóng những kết nối đang hoạt động khi shutdown.

### 18.1. Skeleton handler trong server chạy lâu dài

Đây là **mã minh họa**, không phải chương trình độc lập. Các biến `running` và `server` cùng hàm `handleSession`/`logError` là thành phần do ứng dụng định nghĩa.

~~~java
server.accept(null,
        new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(
            AsynchronousSocketChannel client, Void att) {
        if (running.get() && server.isOpen()) {
            try {
                server.accept(null, this);
            } catch (RuntimeException error) {
                logError(error);
            }
        }

        try {
            handleSession(client);
        } catch (Throwable error) {
            logError(error);
            try {
                client.close();
            } catch (IOException ignored) {
                // Ghi nhận nếu cần; không che lỗi gốc.
            }
        }
    }

    @Override
    public void failed(Throwable error, Void att) {
        if (running.get() && server.isOpen()) {
            logError(error);
            // Quyết định backoff/recover/stop; không retry vô hạn.
        }
    }
});
~~~

**Cảnh báo ownership:** Mẫu trên minh họa ý tưởng re-arm và chuyển giao client. Trong code thực tế, nếu bước re-arm thất bại, quyết định có tiếp tục phục vụ current client hay đóng toàn listener, và ai có trách nhiệm close `client`. Nếu `handleSession` chạy blocking, nên giao việc sang một executor/handler phù hợp, tránh chặn completion pool.

### 18.2. Accept callback không phải nơi làm mọi nghiệp vụ

Những công việc nên tách khỏi callback accept:

- Giải mã giao thức dài, truy vấn database chậm hoặc tác vụ CPU nặng.
- Đọc dữ liệu không giới hạn vào RAM.
- Xác thực và xử lý toàn bộ phiên trong khi chưa re-arm accept.
- Ghi log blocking nhiều trên thread completion.
- Retry accept vô hạn ngay lập tức sau một lỗi lặp lại.

Các bước của một session thường là: giới hạn số kết nối, thiết lập protocol handshake, đọc frame theo size limit, xử lý request, trả response, timeout/idle và close.

## 19. Những lỗi và ngoại lệ thường gặp

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Gọi accept khi chưa bind | `NotYetBoundException` | Bind đúng trước |
| Gọi accept thứ hai khi lượt đầu pending | `AcceptPendingException` | Re-arm sau completion, dùng một owner |
| Bind listener hai lần | `AlreadyBoundException` | Chỉ bind một lần mỗi channel |
| Bind địa chỉ hoặc port không hợp lệ | `IllegalArgumentException`/`UnsupportedAddressTypeException` hoặc lỗi provider | Kiểm tra config |
| Bind port đã bị chiếm | `BindException`/`IOException` tùy OS | Cấu hình lại port hoặc điều tra dịch vụ |
| Không đủ quyền/bị firewall/OS hạn chế | IOException hoặc client connect fail | Kiểm tra OS/firewall/permissions |
| Future.get chờ quá hạn | `TimeoutException` | Không coi accept đã hủy |
| Client kết nối thất bại | `ExecutionException` từ client connect/get | Kiểm tra `getCause()` |
| Server bị đóng khi accept pending | `AsynchronousCloseException` qua Future/handler | Shutdown có chủ đích |
| Group đã shutdown | `ShutdownChannelGroupException` theo API | Không khởi tạo trên group đã dừng |
| Read khác pending cùng accepted socket | `ReadPendingException` | Mỗi socket tối đa một read pending |
| Write khác pending cùng socket | `WritePendingException` | Mỗi socket tối đa một write pending |
| Client ngắt output | read có thể trả `-1` | Xử lý EOF/half-close |
| Không xử lý partial read/write | Mất dữ liệu hoặc sai framing | Vòng lặp/handler theo bytes còn lại |
| Không đóng accepted channel | Leak sockets/resources | Session owner có trách nhiệm close |
| Callback block dài | Tắc completion pool | Tách nghiệp vụ, backpressure |
| Mở wildcard address ngoài ý muốn | Server có thể lộ qua mạng | Bind địa chỉ phù hợp, firewall/auth/TLS |

Ngoại lệ và thứ tự lỗi có thể phụ thuộc provider/OS. Không kiểm tra message lỗi theo chuỗi nguyên văn trong test; nên bắt loại exception và kiểm tra `cause` khi Future báo lỗi.

## 20. Bảo mật khi mở TCP listener thật

Một listener TCP không tự bảo đảm bảo mật. Khi bind lên giao diện mạng ngoài loopback, cần xem xét:

1. **Bind address:** Chỉ mở giao diện cần thiết; không dùng wildcard theo thói quen.
2. **Firewall/ACL:** Hạn chế nguồn có thể kết nối tới port.
3. **Xác thực:** Accept thành công chỉ chứng minh TCP handshake, không xác thực người dùng.
4. **Mã hóa:** `AsynchronousSocketChannel` là TCP byte stream; **không tự cung cấp TLS**. Nếu cần TLS, dùng stack triển khai phù hợp (ví dụ `SSLEngine` với state machine đúng, hoặc thư viện network/TLS có hỗ trợ async).
5. **DoS:** Giới hạn active clients, outstanding bytes, frame size, idle time, request rate và queued work.
6. **Protocol framing:** Không mặc định mỗi read trả đúng một request; giới hạn payload trước cấp phát bộ nhớ.
7. **Backpressure:** Nếu application processing chậm, không đọc/nhận công việc vô hạn.
8. **Timeout và shutdown:** Thiết kế kết thúc kết nối, giải phóng socket/pool chính xác.
9. **Logging:** Tránh ghi credentials, raw tokens hoặc nội dung nhạy cảm từ client.
10. **Kiểm thử:** Dùng loopback cho test tự động; nếu cần test tích hợp bên ngoài, quản lý port và firewall riêng.

**Tránh giả định:** `SO_REUSEADDR`, backlog hoặc thread pool lớn tự chống được flooding/DoS. Mỗi thứ chỉ giải quyết một phần của TCP server lifecycle.

## 21. Performance và lựa chọn API phù hợp

| Nhu cầu | Cân nhắc |
| --- | --- |
| Server nhiều kết nối có callbacks async | `AsynchronousServerSocketChannel` + `AsynchronousSocketChannel` |
| Một dịch vụ TCP nhỏ rất đơn giản | Blocking `ServerSocket` có thể ít phức tạp hơn |
| Multiplex I/O dựa vào readiness | `ServerSocketChannel` non-blocking + `Selector` |
| Server dùng virtual threads (Java hiện đại) | Blocking I/O trong virtual threads có thể là lựa chọn tốt hơn tùy workload/JDK |
| UDP/datagram | Không dùng `AsynchronousServerSocketChannel`: class này cho stream-oriented TCP |
| Giao thức HTTP/TLS sẵn | Ưu tiên thư viện/server đã kiểm chứng thay vì tự viết protocol stack |
| Đa nền tảng | Test Windows/Linux/macOS đúng provider và network stack sản phẩm |

**Asynchronous không đồng nghĩa tự động nhanh hơn.** Một provider có thể dùng thread pool để dispatch I/O; worker count, OS scheduling, latency, số clients, workload CPU và giao thức quyết định hiệu năng. Benchmark thực tế, đo throughput, P95/P99 latency, số accepted sessions, callback queue, memory và error rate.

**Virtual threads:** Đây là lựa chọn đương đại khi cân nhắc kiến trúc server Java mới, không phải API có từ Java 7. Không cần đưa code virtual threads vào bài trọng tâm AsynchronousServerSocketChannel; chỉ cần biết không phải mọi server hiện đại đều phải dùng NIO.2 async callbacks.

## 22. Checklist xây server bất đồng bộ

1. Đã mở `AsynchronousServerSocketChannel` và bind đúng trước accept?
2. Đã chọn loopback hoặc giao diện production phù hợp, không dùng wildcard ngoài ý muốn?
3. Có lấy cổng thật từ `getLocalAddress()` nếu bind port 0?
4. Có phân biệt listener và `AsynchronousSocketChannel` đã accept?
5. Có dùng Future hoặc CompletionHandler đúng signatures?
6. Có hiểu Future.get timeout chỉ là timeout **chờ**, không hủy accept?
7. Có đảm bảo **tối đa một accept pending trên listener**?
8. Có re-arm accept sau completion khi server còn running?
9. Có nhánh `failed` và policy stop/retry/backoff?
10. Có tránh làm nghiệp vụ chậm ngay trong callback accept?
11. Có quản lý ownership và đóng accepted client channels?
12. Có xử lý partial read/write trên TCP byte stream?
13. Có framing và size limit cho message?
14. Có xử lý EOF/half-close và client disconnect?
15. Có tránh multiple read/write pending cùng hướng trên một socket?
16. Có bảo vệ ByteBuffer trong lúc I/O chưa hoàn tất?
17. Có chính sách giới hạn clients, request rate, queued work và idle timeout?
18. Có đóng listener, accepted sessions và group theo đúng thứ tự?
19. Nếu có group riêng, có shutdown/awaitTermination?
20. Có test NotYetBoundException, AcceptPendingException, AlreadyBoundException?
21. Có test đóng listener khi Future accept pending?
22. Có test hai clients liên tiếp và callbacks?
23. Có test qua loopback, port động và không phụ thuộc stdout cổng cố định?
24. Có dùng TLS/xác thực/firewall khi cần expose ra mạng?
25. Có benchmark lựa chọn async so với Selector/blocking/virtual threads theo workload?

## 23. Câu hỏi tự kiểm tra

**1.** Server channel mới mở đã nhận client được chưa?  
**Đáp án:** Chưa; phải `bind` rồi mới `accept`.

**2.** `accept()` trả gì?  
**Đáp án:** `Future<AsynchronousSocketChannel>`, không phải boolean.

**3.** `accept(attachment,handler)` thông báo thành công ra sao?  
**Đáp án:** Qua `completed(AsynchronousSocketChannel,A)`.

**4.** Có thể có hai accept pending trên cùng listener không?  
**Đáp án:** Không; lượt thứ hai có thể ném `AcceptPendingException`.

**5.** Điều đó có nghĩa chỉ phục vụ một client tại một thời điểm?  
**Đáp án:** Không. Nhiều accepted channels có thể xử lý đồng thời.

**6.** Khi nào re-arm accept?  
**Đáp án:** Sau khi lượt pending trước đã hoàn tất và listener còn hoạt động.

**7.** Vì sao phải re-arm trước khi xử lý client lâu?  
**Đáp án:** Để listener tiếp tục nhận các client mới mà không bị callback nặng trì hoãn.

**8.** `NotYetBoundException` xuất hiện lúc nào?  
**Đáp án:** Gọi accept trước khi bind.

**9.** `AlreadyBoundException` xuất hiện lúc nào?  
**Đáp án:** Gọi bind thêm lần nữa trên listener đã bind.

**10.** Port 0 có tác dụng gì?  
**Đáp án:** Nhờ OS tự cấp cổng rảnh; lấy cổng thật bằng getLocalAddress.

**11.** Loopback bind và wildcard bind có giống nhau không?  
**Đáp án:** Không; wildcard có thể lắng nghe trên nhiều network interfaces.

**12.** `Future.get(timeout)` hết thời gian có hủy accept?  
**Đáp án:** Không, pending accept có thể vẫn hoạt động.

**13.** Đóng listener khi accept đang chờ sẽ ra sao?  
**Đáp án:** Accept có thể hoàn tất thất bại với AsynchronousCloseException.

**14.** Accepted channel có tự đóng khi listener đóng không?  
**Đáp án:** Không nên giả định; quản lý nó như tài nguyên session riêng.

**15.** Server listener có trực tiếp read/write payload TCP không?  
**Đáp án:** Không; accepted `AsynchronousSocketChannel` mới làm việc đó.

**16.** Một `read` có tương ứng một message TCP không?  
**Đáp án:** Không. TCP là byte stream; cần framing.

**17.** Tại sao phải loop read/write?  
**Đáp án:** Một I/O có thể chỉ chuyển một phần ByteBuffer.

**18.** Peer đã shutdown output có thể làm read trả gì?  
**Đáp án:** `-1` sau khi dữ liệu đến đã được đọc hết.

**19.** Một socket có thể có hai read outstanding không?  
**Đáp án:** Không; có thể ReadPendingException.

**20.** Một socket có thể vừa read vừa write pending không?  
**Đáp án:** Có, hai hướng I/O độc lập theo API.

**21.** CompletionHandler chạy ở thread nào?  
**Đáp án:** Thread pool của AsynchronousChannelGroup, không được giả định là main thread.

**22.** Backlog có phải tổng số clients đang online?  
**Đáp án:** Không; liên quan hàng đợi connection indications chưa accept.

**23.** SO_REUSEADDR có đảm bảo bind cùng port vô hạn không?  
**Đáp án:** Không; semantics OS/provider phụ thuộc.

**24.** TCP accept đã mã hóa dữ liệu chưa?  
**Đáp án:** Chưa. Nếu cần, phải thêm TLS và xác thực thích hợp.

**25.** Điểm trọng tâm nhất?  
**Đáp án:** Listener khởi phát **một accept pending**, hoàn tất trả **AsynchronousSocketChannel** cho client, và **re-arm** để tiếp tục nhận kết nối khi server còn hoạt động.

## 24. Tài liệu chính thức

- [Oracle Java SE 26 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): open/bind/accept, giới hạn một pending accept, Future/CompletionHandler, backlog, options, địa chỉ.
- [Oracle Java SE 26 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): connect/read/write, stream, ReadPending/WritePending, half-close và timeout.
- [Oracle Java SE 26 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): nhóm kênh, threads, shutdown, termination.
- [Oracle Java SE 26 — CompletionHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/CompletionHandler.html): completed/failed và attachment.
- [Oracle Java SE 26 — AsynchronousByteChannel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html): semantics ByteBuffer, partial I/O, buffer ownership.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): get/timeout/cancellation.
- [Oracle Java SE 26 — CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): phối hợp callback với kết quả thử nghiệm.
- [Oracle Java SE 26 — InetSocketAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetSocketAddress.html): local address/port.
- [Oracle Java SE 26 — InetAddress](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/InetAddress.html): getLoopbackAddress.
- [Oracle Java SE 26 — StandardSocketOptions](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardSocketOptions.html): SO_RCVBUF, SO_REUSEADDR và TCP_NODELAY.
- [Oracle Java SE 26 — AcceptPendingException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AcceptPendingException.html): lỗi có một accept đang chờ.
- [Oracle Java SE 26 — NotYetBoundException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/NotYetBoundException.html): accept trước bind.
- [Oracle Java SE 26 — AsynchronousCloseException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/AsynchronousCloseException.html): lỗi đóng khi I/O đang chờ.
- [Oracle Java SE 26 — ByteBuffer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html): flip/position/remaining.
- [Oracle Java SE 26 — SSLEngine](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): nếu cần TLS ứng dụng phi blocking.
- [Oracle Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): đối chiếu với JDK 17 của các ví dụ.
- [Oracle Java SE 7 — AsynchronousServerSocketChannel](https://docs.oracle.com/javase/7/docs/api/java/nio/channels/AsynchronousServerSocketChannel.html): xác nhận API đã có từ Java 7, hành vi hiện hành ưu tiên đối chiếu Java mới.

**Tổng kết:** `AsynchronousServerSocketChannel` là một **TCP listener bất đồng bộ**. Bạn phải `bind` trước, sau đó dùng `accept()` hoặc `accept(attachment,handler)` để nhận một `AsynchronousSocketChannel` mới. **Một listener chỉ có tối đa một accept pending tại một thời điểm**, nhưng nhiều kết nối đã chấp nhận có thể cùng tồn tại và được xử lý riêng. Re-arm accept sau completion, quản lý client channel lifecycle, hiểu timeout chờ khác timeout I/O, và xây protocol, giới hạn, TLS/xác thực khi ứng dụng thực sự phục vụ mạng.