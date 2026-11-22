# Đóng Socket, đóng stream và quản lý tài nguyên bằng try-with-resources

Một kết nối TCP dùng `java.net.Socket` thường có **hai luồng byte**: `InputStream` để nhận và `OutputStream` để gửi. Ngoài hai luồng đó, hệ điều hành còn giữ tài nguyên kết nối như socket descriptor, buffer và trạng thái TCP. Nếu một nhánh lỗi bỏ qua việc đóng socket, ứng dụng có thể giữ kết nối và tài nguyên lâu hơn dự kiến. Ngược lại, đóng nhầm một stream quá sớm có thể cắt luôn **cả kết nối**, làm hỏng cuộc trao đổi hai chiều.

Bài học này tập trung vào việc **ai sở hữu socket, lúc nào đóng socket hoặc stream, `try-with-resources` bảo đảm điều gì, và khi nào cần `shutdownOutput()` thay vì `close()`**. Các ví dụ dùng Java 17+, `Socket`/`ServerSocket` blocking và TCP loopback; không cần thư viện ngoài.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vòng đời của `ServerSocket`, `Socket` client, `Socket` được `accept()` trả về, và hai stream đi kèm một `Socket`.
- Hiểu rõ: **đóng stream lấy từ socket cũng đóng socket**, và **đóng socket cũng đóng cả input/output stream**.
- Viết `try (Socket socket = ...)` đúng phạm vi; tránh rò rỉ khi `connect()`, đọc, ghi hoặc xử lý dữ liệu ném exception.
- Phân biệt `flush()`, `close()`, `shutdownOutput()`, `shutdownInput()` và thông báo kết thúc ở tầng giao thức.
- Hiểu cách `try-with-resources` đóng ngược thứ tự, giữ exception chính và ghi nhận `suppressed exceptions`.
- Đóng đúng tài nguyên ở client/server và khi có thread/executor; không cắt kết nối đang được worker khác dùng.
- Chạy hai ví dụ: (1) client/server có phản hồi, giải phóng socket an toàn; (2) half-close để báo hết dữ liệu yêu cầu nhưng vẫn đọc phản hồi.

## 2. Ai sở hữu tài nguyên nào?

Cần tách **socket lắng nghe** khỏi **socket kết nối**, đồng thời phân biệt stream như một **view** của kết nối với một kết nối độc lập.

| Tài nguyên | Được tạo/lấy bằng | Vai trò | Ai thường chịu trách nhiệm đóng? |
| --- | --- | --- | --- |
| `ServerSocket` | `new ServerSocket(...)` hoặc `new ServerSocket()` rồi `bind()` | Lắng nghe TCP; `accept()` | Thành phần sở hữu vòng đời server/listener |
| `Socket` phía client | `new Socket()`, `connect(...)` | Kết nối tới server | Mã client sở hữu kết nối, hoặc pool quản lý kết nối |
| `Socket` phía server | `listener.accept()` | Kết nối riêng tới một client | Handler/worker nhận ownership sau `accept()` |
| `InputStream` | `socket.getInputStream()` | Đọc byte nhận được từ peer | Thường đóng **qua socket** trong một scope bao trùm |
| `OutputStream` | `socket.getOutputStream()` | Ghi byte sang peer | Thường đóng **qua socket**; `flush()` nếu có buffering |
| `BufferedReader`, `BufferedWriter` | Wrapper quanh stream và bộ chuyển mã | Đọc dòng/ghi đệm | Phải biết `close()` của wrapper lan xuống stream/socket |
| `ExecutorService`/worker task | `Executors...`, thread | Xử lý nhiều kết nối hoặc chạy server demo | Bộ phận tạo executor phải quản lý shutdown và chờ công việc kết thúc khi cần |

Sơ đồ vòng đời trong một TCP server:

~~~text
ServerSocket (LISTEN)
  |
  +-- accept() --> Socket client A --+-- InputStream A  (đọc từ A)
  |                                 +-- OutputStream A (ghi tới A)
  |
  +-- accept() --> Socket client B --+-- InputStream B
                                    +-- OutputStream B

close(Socket A)     -> chỉ đóng kết nối A và các stream của nó
close(ServerSocket) -> dừng lắng nghe/accept; không tự đóng B nếu B vẫn sống
~~~

**Quy tắc thiết kế:** mỗi tài nguyên sở hữu độc lập nên có một **owner** chịu trách nhiệm đóng. Đừng đóng socket được mượn từ một connection pool ở đoạn code không nắm ownership, và đừng chuyển socket cho worker khác rồi đóng ở caller trước khi worker dùng xong. Khi một handler thực sự sở hữu accepted socket, `try-with-resources` trong handler là vị trí đóng tự nhiên.

## 3. `Socket.close()` làm gì?

`Socket` hiện thực `java.io.Closeable` (và `AutoCloseable`), nên dùng được với `try-with-resources`. Theo API `Socket` của JDK:

1. `socket.close()` làm socket không còn dùng được cho network I/O; không thể kết nối lại cùng đối tượng đó.
2. Nó **đóng cả stream** trả bởi `getInputStream()` và `getOutputStream()`.
3. Thread đang bị chặn ở I/O trên socket bị đóng sẽ nhận lỗi tương ứng (với `Socket` blocking thông thường, `SocketException`).
4. `close()` là cleanup **cục bộ**. Nó không bảo đảm ứng dụng phía peer đã xử lý xong thông điệp vừa gửi; cần phản hồi xác nhận ở **tầng ứng dụng** nếu yêu cầu đó quan trọng.
5. `isClosed()` cho biết đối tượng đã bị đóng. **`isConnected()` không phải phép kiểm tra kết nối vẫn còn hoạt động**: một socket đã từng kết nối thành công có thể vẫn trả `true` sau khi đóng.

Ví dụ kiểm tra trạng thái:

~~~java
Socket socket = new Socket();
// Sau khi socket.connect(...) thành công:
try (socket) {
    // Trao đổi dữ liệu trong phạm vi kết nối.
}
System.out.println(socket.isClosed()); // true
// socket.isConnected() vẫn có thể true vì đã từng kết nối.
~~~

Đoạn này là **mã minh họa**, cần import `java.net.Socket`, một endpoint có thật và xử lý `IOException`. Không được xem `isConnected()` như cơ chế heartbeat hoặc kiểm tra peer còn sống; đọc/ghi cùng protocol timeout mới phản ánh được trạng thái tương tác.

### Đóng `ServerSocket` không tương đương đóng accepted `Socket`

Khi server nhận kết nối bằng `Socket accepted = listener.accept()`, `accepted` là **tài nguyên mới**. Đóng `listener` làm `accept()` đang chờ bị ngắt bằng `SocketException`, nhưng các `Socket` đã nhận **không tự động đóng theo listener**. Server cần quản lý từng accepted connection, nhất là khi chuyển chúng cho thread pool.

Khi TCP server dừng có kiểm soát, một cách tổ chức là: ngừng nhận kết nối mới → đóng listener để giải phóng thread `accept` → cho các request đang chạy kết thúc theo deadline → đóng các accepted socket còn lại → shutdown executor. Thời điểm đóng từng socket phải phù hợp với giao thức và yêu cầu phục vụ.

## 4. Đóng stream của Socket: tác động thường bị hiểu sai

`Socket.getInputStream()` và `Socket.getOutputStream()` trả về các stream **gắn với cùng socket**. JDK quy định:

- Gọi `socket.getInputStream().close()` sẽ đóng socket liên quan.
- Gọi `socket.getOutputStream().close()` sẽ đóng socket liên quan.
- Đóng `BufferedReader`, `InputStreamReader`, `BufferedWriter` hoặc `OutputStreamWriter` thường đóng stream được chúng bao bọc; cuối chuỗi đó có thể là **đóng luôn socket**.

Điều này khác với giả định “đóng input chỉ cấm đọc, output vẫn gửi bình thường”. Với một `Socket` Java, **đóng một stream gốc từ socket là đóng toàn bộ socket**. Muốn đóng **một hướng** nhưng tiếp tục hướng còn lại, xem `shutdownOutput()`/`shutdownInput()` ở phần sau.

### Ví dụ sai khi đang chờ phản hồi

~~~java
// Minh họa lỗi logic trong một phương thức đã có Socket socket.
try (OutputStream out = socket.getOutputStream()) {
    out.write("REQUEST".getBytes(StandardCharsets.US_ASCII));
} // out.close() -> đóng luôn socket!

// Lỗi: socket đã bị đóng, không thể tiếp tục đọc phản hồi bình thường.
InputStream in = socket.getInputStream();
~~~

Ở đây `try-with-resources` tự hoạt động **đúng như hợp đồng**, nhưng phạm vi tài nguyên bị chọn sai. Không thể sửa bằng cách bỏ `try-with-resources` rồi quên đóng socket; cần thiết kế rõ ownership và thời điểm đóng.

### Mẫu khuyến nghị: để `Socket` làm owner chính

~~~java
try (Socket socket = new Socket()) {
    socket.connect(address, 2_000);
    socket.setSoTimeout(3_000);

    BufferedReader in = new BufferedReader(new InputStreamReader(
            socket.getInputStream(), StandardCharsets.UTF_8));
    BufferedWriter out = new BufferedWriter(new OutputStreamWriter(
            socket.getOutputStream(), StandardCharsets.UTF_8));

    out.write("PING\n");
    out.flush();
    String response = in.readLine();
    // Phân tích response, sau đó ra khỏi scope.
} // socket.close() đóng kết nối và các stream liên quan.
~~~

Đây là **mảnh code trong một phương thức**: `address` cần là `SocketAddress` đã tạo, và method phải `throws IOException` hoặc có `catch`. Các import cần dùng: `java.net.Socket`, `java.net.SocketAddress`, `java.io.*`, `java.nio.charset.StandardCharsets`. Khi wrapper được giữ trong cùng một scope và `flush()` chủ động, quản lý bằng **một socket owner** tránh việc wrapper đóng socket quá sớm.

Lưu ý: vì các wrapper không được khai báo là resource riêng ở ví dụ này, nếu còn byte đang nằm trong **buffer phía Java** mà chưa `flush()`, `socket.close()` không có nghĩa bắt buộc wrapper sẽ tự flush. Phải hoàn thành việc ghi/flush theo protocol trước khi đóng. Khi chỉ dùng một hướng (ví dụ đọc hết một response rồi đóng kết nối), đưa wrapper vào `try-with-resources` cũng có thể hợp lý **nếu chấp nhận rằng đóng wrapper là kết thúc socket**.

## 5. Cách `try-with-resources` bảo đảm cleanup

Từ Java 7, `try-with-resources` tự gọi `close()` đối với đối tượng thực hiện `AutoCloseable`. Từ Java 9 có thể đặt biến resource đã khai báo trước vào `try (socket)` nếu biến đó final hoặc effectively final.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("127.0.0.1", 9000), 2_000);
    // Dù thân try chạy xong, return hay ném exception, socket vẫn được close.
}
~~~

Đây là đoạn minh họa trong phương thức khai báo/catch `IOException`. Không có listener ở cổng 9000 trong bài này nên không kỳ vọng chạy riêng đoạn code đó thành công. Dùng `new Socket()` rồi `connect()` bên **trong** khối try có lợi: socket đã được tạo sẽ được đóng ngay cả khi `connect()` hoặc thao tác sau đó thất bại.

### 5.1. Thứ tự đóng khi có nhiều resource

Các resource được đóng theo **thứ tự ngược với thứ tự khai báo**:

~~~java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    doWork(a, b);
}
// close(b) chạy trước close(a).
~~~

Đây là mã **giả lập kiểu**, không phải một chương trình Java chạy độc lập vì `ResourceA`, `ResourceB`, `openA` và `doWork` chưa được khai báo. Với socket và wrapper, ví dụ:

~~~java
try (Socket socket = connect();
     BufferedReader reader = new BufferedReader(
             new InputStreamReader(socket.getInputStream(), UTF_8));
     BufferedWriter writer = new BufferedWriter(
             new OutputStreamWriter(socket.getOutputStream(), UTF_8))) {
    // Giao tiếp hai chiều trong scope.
}
// close(writer) -> close(reader) -> close(socket)
~~~

Đây cũng là **mảnh minh họa** với `connect()`, `UTF_8` chưa định nghĩa. Về mặt ngôn ngữ, cấu trúc hợp lệ khi thay các identifier đó; nhưng đóng `writer` sẽ đóng socket trước khi đóng `reader`, khiến việc đóng lặp lại là dư thừa. Hãy **chọn một mô hình ownership nhất quán**; không cần đưa mọi stream wrapper vào resource list cho đúng hình thức.

### 5.2. Exception xảy ra trong thân try và khi close

Nếu thân `try` ném exception, còn `close()` cũng ném exception, **exception trong thân try vẫn là exception chính**, và các exception khi đóng được gắn dạng **suppressed**. Trường hợp không có exception trong thân mà `close()` lỗi, lỗi đóng có thể trở thành exception được ném ra.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, 2_000);
    performExchange(socket);
} catch (IOException e) {
    reportFailure(e); // lỗi chính
    for (Throwable suppressed : e.getSuppressed()) {
        reportFailure(suppressed); // lỗi xảy ra khi close resource
    }
}
~~~

Đây là đoạn mã minh họa trong phương thức; `endpoint`, `performExchange`, `reportFailure` do ứng dụng định nghĩa. Không nên `catch (Exception e) {}` rồi bỏ qua lỗi: khi đó có thể mất thông tin về cả giao dịch lẫn cleanup. Trong hệ thống thực tế, log exception với context cần thiết nhưng tránh ghi password, token hoặc dữ liệu người dùng nhạy cảm.

### 5.3. So với `finally` thủ công

~~~java
Socket socket = null;
try {
    socket = new Socket();
    // ...
} finally {
    if (socket != null) socket.close();
}
~~~

Đoạn trên có thể dùng nhưng cần tự xử lý việc `close()` ném `IOException` và có nguy cơ **che mất lỗi chính** nếu cleanup cũng thất bại. `try-with-resources` đơn giản hơn và có quy tắc suppressed exception rõ ràng. `finally` vẫn hữu ích cho việc khác, ví dụ gọi `executor.shutdownNow()` sau khi listener/socket đã đóng; đừng dùng một `finally` thừa chỉ để đóng lại socket đã nằm trong resource list.

## 6. `flush()`, EOF và thời điểm đóng: phải tuân theo giao thức

### 6.1. `flush()` không phải `close()`

`BufferedWriter`, `BufferedOutputStream` hoặc các tầng buffering khác có thể giữ byte **trong bộ nhớ ứng dụng** trước khi chuyển xuống stream nền. `flush()` đẩy những byte đang được buffer xuống stream bên dưới, **không có nghĩa peer đã nhận hoặc xử lý xong**. Với dữ liệu cần đáp ứng ngay, phải `flush()` trước khi chờ response.

~~~java
BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(
        socket.getOutputStream(), StandardCharsets.UTF_8));
writer.write("HELLO\n");
writer.flush();     // Gửi byte đã buffer sang socket trước khi chờ peer.
~~~

Nếu bỏ `flush()`, phía client có thể chờ server trả lời trong khi server lại chờ byte request chưa được đẩy khỏi buffer: tạo deadlock logic. `flush()` sau khi đã đóng stream/socket không khôi phục được kết nối.

### 6.2. TCP là một dòng byte, không có “mỗi read là một message”

`InputStream.read()` trả số byte đã đọc, hoặc `-1` khi gặp EOF và không còn byte dữ liệu trong stream; nó có thể trả ít hơn kích thước buffer mong muốn. `BufferedReader.readLine()` đọc đến ký tự xuống dòng hoặc EOF; nếu peer không bao giờ gửi newline và cũng không kết thúc hướng gửi, `readLine()` có thể tiếp tục đợi.

Do đó giao thức phải định nghĩa **ranh giới thông điệp**. Một số cách:

- Line-delimited: `PING\n`, `PONG\n`. Cần thống nhất charset và giới hạn độ dài dòng.
- Length-prefixed: gửi số byte của payload trước rồi đọc đúng số byte đó.
- Đọc tới EOF: chỉ phù hợp khi người gửi **báo hết dữ liệu** bằng việc đóng hướng gửi/kết nối, và người nhận có quy tắc kết thúc rõ ràng.

Không dùng `InputStream.available() == 0` để suy luận đã hết thông điệp: 0 chỉ nói không có byte nào sẵn để đọc ngay trong điều kiện hiện tại.

### 6.3. Đóng sau khi ghi không chứng minh peer đã xử lý thành công

Chuỗi `write(...) -> flush() -> close()` cho biết ứng dụng đã giao byte cho các lớp I/O theo hợp đồng của từng phương thức rồi kết thúc kết nối; nó không tạo ra **acknowledgement ở tầng ứng dụng**. Peer có thể mất kết nối, từ chối request hoặc lỗi trước khi commit dữ liệu.

Nếu cần đảm bảo nghiệp vụ, thiết kế **response/ACK**, timeout, retry và idempotency. Với lệnh thanh toán, ghi dữ liệu, xóa tài nguyên..., không tự suy rằng “close không ném lỗi” đồng nghĩa giao dịch hoàn tất.

## 7. `close()` và half-close: khác nhau ở đâu?

TCP có hai chiều độc lập. `Socket.shutdownOutput()` kết thúc **chiều gửi** của socket và cho phép tiếp tục **đọc chiều nhận**. Đây là công cụ hữu ích với giao thức “client gửi hết request rồi server trả kết quả”.

| Thao tác | Hướng gửi | Hướng nhận | Socket còn dùng để giao tiếp không? |
| --- | --- | --- | --- |
| `socket.close()` | Đóng | Đóng | **Không**, socket bị đóng toàn bộ |
| `socket.shutdownOutput()` | Đóng gửi; không ghi thêm | Vẫn có thể đọc | **Có**, dùng để đọc response; đóng socket sau đó |
| `socket.shutdownInput()` | Vẫn có thể gửi | Kết thúc nhận cục bộ; đọc tiếp báo EOF | **Có** về mặt đối tượng, nhưng dữ liệu nhận tiếp sẽ bị bỏ qua |
| `output.flush()` | Đẩy dữ liệu buffered xuống dưới | Không đổi | **Có**, không kết thúc chiều nào |
| `output.close()` trên stream từ socket | Đóng **cả socket** | Cũng bị đóng | **Không**, vì close stream đóng socket |

Với TCP, `shutdownOutput()` tạo tín hiệu kết thúc chiều gửi theo ngữ nghĩa của TCP (FIN sau dữ liệu đã viết), không phải “gửi một message rỗng”. Sau đó, gọi `getOutputStream().write(...)` tiếp sẽ ném `IOException`. `shutdownOutput()` **không đóng đối tượng socket hoàn toàn**; vẫn phải dùng `try-with-resources` hoặc `close()` khi đọc xong.

`shutdownInput()` là thao tác có tác dụng khác: JDK cho biết đọc sau đó trả `-1`, và dữ liệu phía kia tiếp tục gửi tới hướng nhận sẽ bị xác nhận rồi bỏ. Nó không phải biện pháp mặc định để kết thúc giao dịch; rất dễ đánh mất phản hồi nếu gọi nhầm.

**Điểm thực hành quan trọng:** Nếu đang dùng `BufferedWriter`, cần `writer.flush()` **trước** `socket.shutdownOutput()`. Việc chỉ gọi `shutdownOutput()` không thể tự flush nội dung vẫn nằm trong bộ đệm của `BufferedWriter`.

## 8. Ví dụ 1: Client và server dùng `try-with-resources` an toàn

Chương trình sau chạy cả TCP listener và client trên máy cục bộ. Server nhận đúng một dòng `PING`, trả `PONG`, rồi đóng accepted socket. Client đợi phản hồi, thoát scope `try` và xác nhận `isClosed()`. Cả server/client dùng **socket làm owner**. Wrapper đọc/ghi ở trong cùng scope và `flush()` trước khi chờ phản hồi.

Tạo file **`SocketCloseDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.setSoTimeout(3_000);

            Future<?> serverTask = workers.submit(() -> {
                try (Socket accepted = listener.accept()) {
                    accepted.setSoTimeout(3_000);

                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(
                                    accepted.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(
                                    accepted.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String request = input.readLine();
                    if (!"PING".equals(request)) {
                        throw new IOException("Unexpected request");
                    }
                    output.write("PONG\n");
                    output.flush();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            Socket client = new Socket();
            try (client) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(3_000);

                BufferedReader input = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter output = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));

                output.write("PING\n");
                output.flush();
                System.out.println("Client received: " + input.readLine());
            }
            System.out.println("Client closed: " + client.isClosed());
            serverTask.get(5, TimeUnit.SECONDS);
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 SocketCloseDemo.java
java SocketCloseDemo
~~~

**Stdout đã kiểm chứng với Java 24** (ứng xử của API được dùng cũng áp dụng cho Java 17+):

~~~text
Client received: PONG
Client closed: true
~~~

Giải thích:

1. `listener.bind(..., 0)` để OS chọn một cổng còn trống; dùng loopback để không cần mạng bên ngoài. `ServerSocket` nằm trong resource list và sẽ đóng cuối scope.
2. `workers.submit(...)` chạy server handler; `listener.accept()` tạo **Socket mới**. `try (Socket accepted = ...)` đóng riêng kết nối này kể cả khi handler ném `IOException`.
3. `BufferedReader.readLine()` đợi đến newline. Client gửi `PING\n` và **flush**; server gửi `PONG\n` và **flush**.
4. `Socket client = new Socket(); try (client)` dùng cú pháp Java 9+, đảm bảo đóng ngay cả khi `connect()`, `readLine()` hay logic xử lý ném exception.
5. Sau khi ra khỏi `try (client)`, `client.isClosed()` là `true`. Không cần đóng từng stream riêng.
6. `serverTask.get(...)` đợi handler kết thúc và chuyển exception của task về caller nếu có. `finally` shutdown executor; việc đóng listener và accepted socket được xử lý bởi các scope riêng.

Ví dụ chỉ xử lý **một** kết nối, một dòng request và một dòng response. Đây là code học tập về lifecycle; dịch vụ thực phải có giới hạn request, chính sách concurrency, logging, authentication khi phù hợp và quản lý stop/shutdown có kiểm soát. Timeout vài giây là giá trị phục vụ demo, cần được thiết kế theo môi trường thực tế.

## 9. Ví dụ 2: `shutdownOutput()` để báo hết request và vẫn nhận ACK

Ví dụ này minh họa giao thức **đọc đến EOF**: client gửi `HELLO`, báo đã gửi xong bằng `shutdownOutput()`, server đọc hết request rồi trả `ACK:5`. Client tiếp tục đọc ACK trước khi socket được đóng. Nếu gọi `client.getOutputStream().close()` thay cho `shutdownOutput()`, cả socket bị đóng và không còn dùng được để đọc ACK.

Tạo file **`SocketHalfCloseDemo.java`**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketHalfCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            Future<?> serverTask = workers.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3_000);
                    byte[] request = peer.getInputStream().readAllBytes();
                    String reply = "ACK:" + request.length + "\n";
                    peer.getOutputStream().write(
                            reply.getBytes(StandardCharsets.US_ASCII));
                    peer.getOutputStream().flush();
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort()), 2_000);
                client.setSoTimeout(3_000);
                client.getOutputStream().write(
                        "HELLO".getBytes(StandardCharsets.US_ASCII));
                client.shutdownOutput();
                byte[] reply = client.getInputStream().readAllBytes();
                System.out.print(new String(
                        reply, StandardCharsets.US_ASCII));
            }
            serverTask.get(5, TimeUnit.SECONDS);
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SocketHalfCloseDemo.java
java SocketHalfCloseDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
ACK:5
~~~

Ở đây server `readAllBytes()` biết khi nào dừng vì client đã **half-close chiều gửi**; sau khi server ghi ACK, server đóng accepted socket, nên client nhận được EOF và kết thúc `readAllBytes()`. Nếu client chỉ `flush()` mà không `shutdownOutput()`, server đang chờ EOF có thể tiếp tục đợi; hai bên có nguy cơ mắc kẹt. 

**Giới hạn của ví dụ:** `readAllBytes()` có thể dùng bộ nhớ theo kích thước dữ liệu nhận. Nó chỉ phù hợp ở đây vì input là chuỗi `HELLO` tự tạo và rất ngắn. Với dữ liệu mạng không tin cậy, cần giới hạn byte, quota, protocol framing và deadline. Trong giao thức hai chiều sản xuất, thường dùng frame length hoặc delimiter rõ ràng thay vì buộc mỗi request phải kết thúc bằng EOF.

## 10. Timeout, cancellation và xử lý lỗi khi đóng

Dùng `try-with-resources` để ngăn rò rỉ, nhưng cleanup **không tự giải quyết** tất cả những lần blocking vô hạn.

| Cấu hình/thao tác | Giới hạn hoặc tác dụng | Điều không được suy diễn |
| --- | --- | --- |
| `socket.connect(endpoint, 2_000)` | Timeout bước thiết lập TCP connection | Không giới hạn toàn bộ request/response |
| `socket.setSoTimeout(3_000)` | Timeout cho thao tác **đọc blocking** trên socket | Không phải timeout cho mọi lần `write()` hay tổng giao dịch |
| `listener.setSoTimeout(3_000)` | Giới hạn một lần blocking `accept()` | Không tự đóng listener sau timeout |
| `socket.close()` | Đóng socket; đánh thức thread đang kẹt trong socket I/O bằng exception theo hợp đồng | Không xác nhận nghiệp vụ peer hoàn tất |
| `listener.close()` | Dừng listener; làm `accept()` đang chờ bị lỗi | Không tự đóng các accepted socket đã giao cho worker |
| `executor.shutdown()` | Không nhận task mới, cho task cũ có cơ hội hoàn tất | Không tự đóng các socket đang nằm trong task |
| `executor.shutdownNow()` | Yêu cầu ngắt/cancel các task đang chạy | Không phải cơ chế đóng socket đáng tin cậy trong mọi cách triển khai I/O |

Trong server có thread pool, cần theo dõi accepted socket còn sống hoặc có một cơ chế hủy phù hợp; khi cần dừng cưỡng bức, **đóng những socket do server sở hữu** để giải phóng blocking I/O. Không giả định `Thread.interrupt()` trên mọi kiểu Socket/JDK đều có cùng hiệu lực như `Socket.close()`.

### Xử lý `SocketTimeoutException`

`SocketTimeoutException` là một `IOException`; timeout đọc thường không khiến socket tự bị đóng. Nhưng việc có thể tiếp tục dùng hay phải bỏ kết nối phụ thuộc **trạng thái framing của protocol**: có thể đã nhận một phần message. Trường hợp không thể khôi phục một frame nhất quán, nên đóng socket và bắt đầu một kết nối/giao dịch mới theo quy định.

### Khi `close()` cũng thất bại

`close()` có thể ném `IOException`. Đừng viết `finally` cố nuốt lỗi, hoặc ném exception mới che mất nguyên nhân ban đầu. `try-with-resources` giữ exception chính và gắn lỗi cleanup vào `getSuppressed()`. Với số lượng tài nguyên lớn, ghi lỗi ở mức phù hợp nhưng tránh log lặp/thiếu context. Một exception trên close không có nghĩa caller nên tiếp tục dùng cùng socket; thiết kế an toàn là coi scope đã kết thúc.

### `SO_LINGER` và kết thúc bất thường

`setSoLinger(true, 0)` có thể biến close thành kết thúc dạng reset/abort thay vì đóng TCP thông thường, có nguy cơ làm mất dữ liệu chưa được bên kia đọc. Giá trị `SO_LINGER` dương có thể ảnh hưởng thời gian block khi đóng. Đừng tùy tiện bật linger hoặc dựa vào thời điểm giải phóng port để chứng minh giao dịch hoàn tất. Nếu cần xác nhận xử lý ở peer, hãy dùng **ACK của giao thức ứng dụng**.

## 11. Quy tắc ownership trong ứng dụng lớn

### 11.1. Client tự tạo socket để thực hiện một giao dịch

Mẫu cơ bản:

~~~java
try (Socket socket = new Socket()) {
    socket.connect(endpoint, connectTimeoutMillis);
    socket.setSoTimeout(readTimeoutMillis);
    exchange(socket);
}
~~~

Là **mảnh code minh họa**; `endpoint`, `connectTimeoutMillis`, `readTimeoutMillis` và `exchange` do caller định nghĩa. Phương thức gọi khai báo/catch `IOException`. Nếu `exchange()` quản lý được cả hai chiều, **caller là owner** và đóng ở ranh giới giao dịch; helper không tự đóng socket trước khi caller kết thúc.

### 11.2. Handler nhận accepted socket

~~~java
while (running) {
    Socket accepted = listener.accept();
    handleOneConnection(accepted); // Phải có hợp đồng: chuyển ownership.
}
~~~

Đây là đoạn **mô tả luồng control**, không phải chương trình chạy độc lập (biến/method cần khai báo). Nếu `handleOneConnection` sở hữu socket, đặt `try (accepted)` **bên trong handler**. Nếu caller còn sở hữu, caller phải đóng. Không để cả hai bên nghĩ bên kia chịu trách nhiệm. Với `ExecutorService.submit(() -> handle(accepted))`, nếu `submit` bị từ chối vì executor shutdown, caller vẫn phải **đóng accepted socket** vì chưa chuyển ownership thành công.

### 11.3. Socket được quản lý bởi connection pool

Khi client dùng abstraction/pool tái sử dụng kết nối, `close()` trên đối tượng wrapper có thể trả kết nối về pool thay vì đóng TCP thật, tùy thư viện. Đối với **`java.net.Socket` trực tiếp**, `close()` đóng kết nối như API đã định nghĩa. Đừng áp dụng nguyên xi quy tắc socket trực tiếp sang các wrapper/pool mà chưa đọc hợp đồng ownership của thư viện.

### 11.4. Lưu ý với TLS

`SSLSocket` cũng thuộc họ socket, nhưng TLS có handshake và thủ tục đóng bảo mật riêng. Nếu ứng dụng dùng `SSLSocket`, cần theo tài liệu JSSE và semantics TLS; không tự coi `shutdownOutput()` trên raw TCP là một kết thúc TLS hợp lệ cho mọi trường hợp. Bài này tập trung vào `java.net.Socket` thuần.

## 12. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Giải pháp |
| --- | --- | --- |
| Chỉ tạo `new Socket()` rồi quên `close()` khi lỗi | Descriptor và kết nối có thể tồn tại ngoài thời gian mong muốn | `try (Socket socket = ...)` bao trùm `connect()` và giao dịch |
| Đóng `InputStream` để “chỉ ngừng đọc” | Đóng stream từ socket làm **đóng cả socket** | Dùng `shutdownInput()` chỉ khi protocol yêu cầu; thường chỉ đọc xong rồi `close()` |
| `try (OutputStream out = socket.getOutputStream())` xong vẫn muốn đọc response | `out.close()` đóng socket trước khi đọc | Cho socket làm owner; nếu cần EOF một chiều, `flush()` rồi `shutdownOutput()` |
| Đóng `BufferedWriter` trước khi server phản hồi | Wrapper close lan đến socket | `flush()` writer, đọc response, rồi kết thúc socket scope |
| Tưởng `socket.close()` tự `flush()` mọi buffer ở wrapper | Wrapper có thể còn byte trong bộ nhớ Java | Flush theo protocol trước khi đóng |
| Tưởng `flush()` bảo đảm peer đã xử lý request | Flush chỉ đẩy dữ liệu qua các tầng buffer | Chờ response/ACK hợp lệ nếu cần xác nhận |
| Bỏ qua delimiter và chờ `readLine()` | Peer chờ newline/EOF nên có thể treo | Xác định framing, gửi newline, flush |
| Coi `read() == -1` là đồng nghĩa request thành công | EOF chỉ báo kết thúc stream; peer có thể ngắt sớm | Kiểm tra đủ frame, trạng thái và ACK |
| Dựa vào `isConnected()` để kiểm tra socket đang sống | Nó có thể true sau khi close | Quản lý lifecycle với `isClosed()`, thao tác I/O và protocol |
| Đóng `ServerSocket` và nghĩ tất cả client đã bị ngắt | Accepted socket độc lập | Quản lý danh sách connection/worker và đóng riêng |
| Đóng socket ở caller khi task vẫn đang dùng | Worker nhận `SocketException`, mất message | Quy định rõ điểm chuyển ownership và thời điểm close |
| Chỉ `shutdownNow()` executor | Interrupt không luôn giải phóng blocked socket I/O | Có timeout, đóng listener/accepted sockets theo chính sách |
| Nuốt `IOException` hoặc suppressed exceptions | Mất thông tin về lỗi giao dịch và cleanup | Ghi nhận/cung cấp context, giữ root cause |
| Dùng `readAllBytes()` với payload tùy ý từ mạng | Có thể dùng quá nhiều bộ nhớ hoặc chờ EOF vô hạn | Giới hạn kích thước, dùng frame và deadline |
| Bật `SO_LINGER` không có lý do | Có thể reset connection hoặc làm close block | Giữ mặc định trừ khi có yêu cầu và kiểm thử rõ |

## 13. Checklist kiểm tra trước khi đưa code vào chạy

- [ ] Đã xác định **owner** cho listener, client socket và từng accepted socket.
- [ ] Mỗi socket do mình sở hữu nằm trong `try-with-resources` hoặc có cleanup tương đương với một vòng đời rõ ràng.
- [ ] `connect()` được thực hiện **trong** resource scope để kết nối lỗi vẫn được close.
- [ ] Stream wrappers không bị đóng trước khi trao đổi hai chiều hoàn tất.
- [ ] Byte ghi qua `BufferedWriter`/`BufferedOutputStream` được `flush()` vào thời điểm protocol yêu cầu.
- [ ] Giao thức có **framing** và điều kiện kết thúc; không chờ `readLine()`/EOF vô hạn.
- [ ] Nếu cần half-close, tôi dùng `shutdownOutput()` sau khi ghi/flush và vẫn đóng socket khi đọc xong.
- [ ] Có timeout kết nối, timeout đọc và deadline nghiệp vụ hợp lý.
- [ ] Accepted sockets vẫn được quản lý khi listener/executor dừng.
- [ ] Error path giữ nguyên nhân gốc và kiểm tra suppressed exceptions khi có vấn đề cleanup.
- [ ] Tôi không dùng `close()`, `flush()` hay TCP FIN như bằng chứng ứng dụng bên kia đã xử lý thành công.
- [ ] Test có cả trường hợp happy path, timeout, peer đóng sớm, lỗi xử lý và hủy kết nối.

## 14. Bài tập tự kiểm tra kèm lời giải

**Bài 1.** Một TCP client ghi request qua `BufferedWriter`, gọi `writer.close()` rồi gọi `reader.readLine()` trên cùng socket. Vì sao có thể hỏng?

**Đáp án:** `BufferedWriter.close()` đóng chuỗi writer/output stream bên dưới; đóng output stream lấy từ `Socket` sẽ đóng **toàn bộ socket**, nên chiều đọc cũng mất hiệu lực. Nên giữ socket làm owner, `flush()` rồi đọc response; nếu server yêu cầu EOF mới xử lý, dùng `shutdownOutput()` sau khi flush.

**Bài 2.** `ServerSocket.close()` có đảm bảo các accepted sockets đã nhận cũng đóng không?

**Đáp án:** Không. Listener chỉ dừng lắng nghe/accept. Mỗi accepted socket có vòng đời riêng, cần handler hoặc server shutdown manager đóng.

**Bài 3.** Thân `try-with-resources` ném `IOException A`; lúc `close()` cũng ném `IOException B`. Lỗi nào là exception chính?

**Đáp án:** A là exception chính; B được gắn trong `A.getSuppressed()`. Nếu chỉ close thất bại mà thân try không ném lỗi, exception close có thể là lỗi chính.

**Bài 4.** Server `readAllBytes()` đợi đến EOF; client đã `write()`, `flush()` rồi vẫn chờ server trả kết quả. Hai bên có thể kẹt không?

**Đáp án:** Có. Nếu giao thức server đọc đến EOF, `flush()` không báo EOF. Client cần `shutdownOutput()` để hoàn tất chiều gửi rồi đọc kết quả; sau đó `close()` socket. Tốt hơn nữa là dùng một framing rõ ràng nếu muốn nhiều giao dịch trên một kết nối.

**Bài 5.** `isConnected()` trả `true` nghĩa là socket còn có thể gửi dữ liệu?

**Đáp án:** Không. Nó ghi nhận đối tượng từng kết nối; có thể vẫn `true` sau `close()`. Cần quản lý lifecycle và xử lý lỗi I/O/timeout theo giao thức.

**Bài 6.** `Socket.setSoTimeout(3000)` có buộc mọi lần `write()` và `close()` xong trong 3 giây không?

**Đáp án:** Không. `SO_TIMEOUT` trong `Socket` dùng cho thao tác **đọc** blocking. Kết nối có timeout riêng trong `connect(endpoint, timeout)`; deadline toàn giao dịch, write và close cần chính sách/kiến trúc phù hợp, không quy đồng vào read timeout.

## 15. Tài liệu tra cứu chính thức

- [JDK 17 — `java.net.Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `close()`, `getInputStream()`, `getOutputStream()`, `shutdownInput()`, `shutdownOutput()`, `isClosed()`, `isConnected()`, `setSoTimeout()`.
- [JDK 17 — `java.net.ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): listener, `accept()`, `close()`, `setSoTimeout()`.
- [Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): đóng resource theo thứ tự ngược và suppressed exceptions.
- [JDK 17 — `java.io.BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `flush()`, `close()`.
- [JDK 17 — `java.io.Closeable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): hợp đồng đóng tài nguyên.
- [JDK 17 — `java.util.concurrent.ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý công việc song song và shutdown.

**Nguyên tắc cần giữ khi lập trình TCP:** cho mỗi socket một owner rõ ràng; đặt phạm vi `try-with-resources` bao trùm toàn bộ cuộc trao đổi; flush dữ liệu buffered đúng lúc; chỉ dùng `shutdownOutput()` khi protocol yêu cầu kết thúc một chiều; luôn đóng socket cuối vòng đời và xác nhận hoàn tất bằng giao thức ứng dụng nếu cần.
