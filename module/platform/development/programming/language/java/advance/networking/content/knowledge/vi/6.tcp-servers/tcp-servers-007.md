# Giới hạn kết nối đang hoạt động và tách công việc CPU khỏi chờ I/O

## Mục tiêu bài học

Một máy chủ TCP thường phải làm ba việc có bản chất khác nhau: **chấp nhận kết nối**, **chờ đọc/ghi dữ liệu mạng** và **xử lý dữ liệu bằng CPU**. Nếu mọi kết nối đều tạo thread mới hoặc CPU task dùng chung pool với những thread đang kẹt ở `read()`, tài nguyên có thể cạn ngay cả khi CPU còn rảnh.

Sau bài này, bạn có thể:

- Phân biệt **backlog chờ `accept()`** với **số kết nối đã được ứng dụng chấp nhận phục vụ**.
- Giới hạn số kết nối đang hoạt động bằng `Semaphore`, hiểu rõ ai mượn/trả permit và tại sao phải trả **chính xác một lần**.
- Tách **acceptor**, nhóm **I/O worker** và nhóm **CPU worker**; giới hạn thread, hàng đợi và xử lý khi pool đầy.
- Sử dụng timeout, giới hạn kích thước request và chính sách backpressure để tránh client chậm hoặc công việc CPU dài chiếm tài nguyên vô hạn.
- Chạy ví dụ Java 17+ có TCP server và client sử dụng hai executor độc lập; hiểu giới hạn của `Future.get()` trên I/O thread.
- Chọn khi nào đủ dùng blocking I/O, khi nào cần mô hình nonblocking với `Selector`/`SocketChannel`.

## 1. Vì sao không nên xử lý mọi việc trong một thread pool chung?

Giả sử một server dùng bốn thread để phục vụ bốn kết nối:

~~~text
I/O thread 1  → Socket A: chờ read()
I/O thread 2  → Socket B: chờ read()
I/O thread 3  → Socket C: chờ read()
I/O thread 4  → Socket D: chờ read()

CPU task đã có đầy đủ dữ liệu → vẫn nằm trong queue
~~~

Bốn thread đều đang **chờ I/O**, nên một công việc CPU mới dù đã có dữ liệu vẫn không có worker. Đây là dạng **thread starvation**. Nếu dùng `newCachedThreadPool()` để tránh chờ, pool lại có thể sinh quá nhiều thread khi số client tăng, gây áp lực lên memory, context switching và scheduler.

Một kiến trúc dễ hiểu hơn:

~~~text
TCP clients
    │
    ▼
ServerSocket.accept()     ← acceptor thread, không xử lý nghiệp vụ dài
    │
    ▼
Semaphore admission       ← đủ slot mới phục vụ
    │
    ├── full → đóng socket mới (theo chính sách quá tải)
    │
    ▼
I/O executor              ← đọc header/payload, chờ mạng, ghi phản hồi
    │
    └── dữ liệu đã có → CPU executor ← tính toán không gọi socket.read()
                            │
                            └── result → I/O handler → ghi và đóng socket
                                                    → release permit
~~~

Tách trách nhiệm giúp kiểm soát độc lập hai loại tài nguyên:
- **I/O-bound**: nhiều thời gian nằm chờ byte từ client; rủi ro chính là quá nhiều socket, thread đang chờ và các timeout kéo dài.
- **CPU-bound**: parse nặng, mã hóa, nén, tính toán; rủi ro chính là CPU saturation, contention và hàng đợi chờ lâu.

Tách CPU ra pool khác **không tự động khiến I/O nonblocking**. Trong ví dụ blocking bên dưới, I/O handler còn chờ kết quả CPU bằng `Future.get()`. Lợi ích trước mắt là CPU task không chạy trực tiếp trong I/O worker và các giới hạn rõ ràng. Với hàng chục nghìn kết nối lâu dài, cần cân nhắc NIO hoặc async I/O.

## 2. Ba khái niệm kết nối không được nhầm lẫn

| Thuật ngữ | Ý nghĩa | Ai kiểm soát? |
|---|---|---|
| **Listen backlog** | Dung lượng/hint liên quan tới các kết nối đang chờ được `accept()` | OS và socket listen; tham số `backlog` là gợi ý |
| **Accepted socket** | `ServerSocket.accept()` đã trả về một đối tượng `Socket` | Acceptor ứng dụng |
| **Admitted active connection** | Ứng dụng đã cho phép socket được phục vụ và còn giữ tài nguyên cho nó | `Semaphore` và lifecycle handler |

Ví dụ `new ServerSocket(0, 32, InetAddress.getLoopbackAddress())` có `backlog=32`, **không** nghĩa là cho phép tối đa 32 kết nối đang phục vụ. Nếu giới hạn ứng dụng là bốn permit, có tối đa bốn phiên được xử lý đồng thời; socket thứ năm có thể vừa được `accept()` nhưng sẽ bị đóng ngay nếu không lấy được permit.

**Cổng 0** yêu cầu hệ điều hành chọn cổng đang rảnh. **Loopback** giữ bài thực hành trên máy cục bộ. Đây không phải cấu hình công khai cho mọi interface.

Không có một con số đủ để bảo vệ server: cần kiểm soát số connection, số I/O thread, số CPU task, kích thước queue, bytes request/response và thời gian sống của phiên.

## 3. Giới hạn active connection với `Semaphore`

`Semaphore` quản lý một lượng permit. Với `new Semaphore(4)`, tối đa bốn lần `tryAcquire()` thành công khi chưa có permit nào được trả về:

~~~java
Semaphore active = new Semaphore(4);
Socket socket = listener.accept();

if (!active.tryAcquire()) {
    socket.close();       // Chưa sở hữu permit.
} else {
    // Giao socket cho handler.
    // Sau khi socket thật sự kết thúc: active.release().
}
~~~

Đây là **đoạn mã minh họa**, đặt trong lớp có import `java.util.concurrent.Semaphore` và `java.net.Socket`/`ServerSocket`, không phải chương trình độc lập.

Các quy tắc quan trọng:

1. `tryAcquire()` trả `false`: **không** gọi `release()`. Trả permit chưa từng lấy sẽ làm giới hạn bị vượt.
2. `tryAcquire()` thành công: giữ permit từ lúc ứng dụng chấp nhận phục vụ đến lúc socket kết thúc. Không release chỉ vì đã gửi task CPU đi.
3. Handler kết thúc thành công, timeout, EOF, client reset hoặc xử lý thất bại: **đều phải trả permit**. Đặt `release()` trong `finally`.
4. Nếu đã lấy permit nhưng **I/O executor từ chối nhận task**, acceptor phải đóng socket và trả permit ngay.
5. Mỗi permit có **một chủ sở hữu việc trả**. Không để cả acceptor và handler cùng release cho một task đã nhận.

Luồng ownership:

~~~text
accept → tryAcquire()
             │
      ┌──────┴────────┐
      │ false         │ true
      ▼               ▼
   close            io.execute(task)
   không release       │
                     ┌─┴──────────────────┐
                     │ accepted           │ rejected
                     ▼                    ▼
               handler finally:     acceptor close
                 release()          + release()
~~~

`Semaphore.acquire()` có thể block acceptor đến khi có permit; điều đó thay đổi chiến lược overload và khả năng `accept()` socket mới. Với chính sách **bận thì từ chối nhanh**, `tryAcquire()` sau `accept()` dễ mô hình hóa hơn. Một ứng dụng muốn chờ có thời hạn có thể dùng `tryAcquire(timeout, unit)`, nhưng cần thiết kế rõ giới hạn chờ.

## 4. Giới hạn executor và hàng đợi

Một semaphore chỉ giới hạn connection đang phục vụ. Nó **không** tự giới hạn CPU queue, thread hay request in-flight. Bài này chọn ngân sách thử nghiệm:

| Thành phần | Giá trị minh họa | Mục đích |
|---|---|---|
| `MAX_ACTIVE` | 4 | Tối đa bốn connection được phục vụ |
| I/O executor | 4 worker, `SynchronousQueue` | Không để socket xếp hàng lâu chờ một I/O worker |
| CPU executor | 2 worker, `ArrayBlockingQueue<>(1)` | Tối đa hai CPU task chạy và một task đang chờ |
| `MAX_BODY` | 1024 byte | Từ chối header khai báo payload quá lớn |
| Socket read timeout | 5 giây | Không chờ vô hạn trong một thao tác đọc |
| CPU future timeout | 2 giây | Giới hạn thời gian I/O handler chờ CPU result |

Đây là các tham số **để học**, không phải sizing chung cho sản phẩm. Hãy chọn bằng đo throughput, tail latency, CPU, file descriptor, memory và thời gian sống connection.

Cần hiểu các factory thường dùng:

- `Executors.newCachedThreadPool()` không đặt một giới hạn thread cố định thích hợp cho overload TCP.
- `Executors.newFixedThreadPool(n)` chỉ giới hạn số worker, còn task queue mặc định là dạng không giới hạn dung lượng. Nếu nộp task nhanh hơn xử lý, độ dài queue có thể tăng gây trễ và tiêu tốn bộ nhớ.
- `ThreadPoolExecutor` kết hợp pool size, queue có giới hạn và `RejectedExecutionHandler` làm ngân sách tài nguyên rõ hơn.
- Với `ThreadPoolExecutor.AbortPolicy`, task bị từ chối bằng `RejectedExecutionException` khi executor không còn nhận task được.

**Không vô tư dùng `CallerRunsPolicy` cho CPU pool:** task bị từ chối sẽ chạy ngay trên thread gọi `submit`, có thể là I/O handler. CPU nặng lúc đó quay về chặn I/O thread. Nếu áp dụng CallerRuns cho I/O executor từ acceptor, acceptor có thể trực tiếp chạy handler và kẹt ở socket.

## 5. Server Java 17+ có giới hạn kết nối và hai pool tách biệt

Giao thức ví dụ dùng **một request mỗi TCP connection**. Request và response có format:

~~~text
[4 byte length, big-endian][length byte payload UTF-8]
~~~

Phía gửi dùng `DataOutputStream.writeInt(length)`, phía nhận dùng `DataInputStream.readInt()`. `length` là **số byte UTF-8**, không phải `String.length()`. Sau khi đọc đủ request, server nộp một phép chuyển text thành chữ hoa qua CPU executor, gửi response và đóng connection.

Lưu file **`BoundedTcpServer.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.*;

public class BoundedTcpServer {
    private static final int MAX_ACTIVE = 4;
    private static final int MAX_BODY = 1024;

    static void closeQuietly(Socket socket) {
        try {
            socket.close();
        } catch (IOException ignored) {
        }
    }

    static void handle(Socket socket, ExecutorService cpu) {
        try (socket) {
            socket.setSoTimeout(5_000);

            DataInputStream in = new DataInputStream(
                new BufferedInputStream(socket.getInputStream()));
            int length = in.readInt();
            if (length < 0 || length > MAX_BODY) {
                throw new IOException("Invalid payload length");
            }

            byte[] request = in.readNBytes(length);
            if (request.length != length) {
                throw new EOFException("Truncated request");
            }

            Future<byte[]> job;
            try {
                job = cpu.submit(() -> {
                    String text = new String(
                        request, StandardCharsets.UTF_8);
                    return text.toUpperCase(Locale.ROOT)
                        .getBytes(StandardCharsets.UTF_8);
                });
            } catch (RejectedExecutionException e) {
                throw new IOException("CPU executor overloaded", e);
            }

            byte[] response;
            try {
                response = job.get(2, TimeUnit.SECONDS);
            } catch (TimeoutException e) {
                job.cancel(true);
                throw new IOException("CPU work timed out", e);
            } catch (InterruptedException e) {
                job.cancel(true);
                Thread.currentThread().interrupt();
                throw new IOException("I/O handler interrupted", e);
            } catch (ExecutionException e) {
                throw new IOException("CPU work failed", e.getCause());
            }

            if (response.length > MAX_BODY) {
                throw new IOException("Response too large");
            }

            DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(socket.getOutputStream()));
            out.writeInt(response.length);
            out.write(response);
            out.flush();
        } catch (IOException e) {
            System.err.println(
                "Client request failed: " + e.getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        Semaphore active = new Semaphore(MAX_ACTIVE);

        ThreadPoolExecutor io = new ThreadPoolExecutor(
            MAX_ACTIVE, MAX_ACTIVE, 0, TimeUnit.SECONDS,
            new SynchronousQueue<>(),
            new ThreadPoolExecutor.AbortPolicy());

        ThreadPoolExecutor cpu = new ThreadPoolExecutor(
            2, 2, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        try (ServerSocket listener = new ServerSocket(
                0, 32, InetAddress.getLoopbackAddress())) {
            System.out.println("Port: " + listener.getLocalPort());

            while (!Thread.currentThread().isInterrupted()) {
                Socket socket = listener.accept();

                if (!active.tryAcquire()) {
                    closeQuietly(socket);
                    continue;
                }

                try {
                    io.execute(() -> {
                        try {
                            handle(socket, cpu);
                        } finally {
                            active.release();
                        }
                    });
                } catch (RejectedExecutionException e) {
                    closeQuietly(socket);
                    active.release();
                }
            }
        } finally {
            io.shutdownNow();
            cpu.shutdownNow();
        }
    }
}
~~~

### Giải thích trách nhiệm và xử lý lỗi

**Acceptor:** `accept()` lấy socket, `tryAcquire()` xét admission. Nó không đọc request hay chạy phép xử lý CPU. Nếu server đủ bốn permit, socket tiếp theo bị đóng; không tự phát ra một HTTP status vì demo dùng giao thức TCP tự định nghĩa.

**I/O pool:** bốn thread, `SynchronousQueue` không giữ backlog task ứng dụng. Handler được nhận mới chạy `handle`; nếu `io.execute` không nhận task, acceptor đóng socket và trả permit. Handler được nhận thì `finally` của handler trả permit, kể cả lỗi.

**I/O handler:** `try (socket)` bảo đảm đóng socket; `setSoTimeout(5_000)` giới hạn thao tác đọc blocking. `readInt` đọc header bốn byte; `readNBytes(length)` có thể trả mảng ngắn ở EOF nên bắt buộc so sánh độ dài. Length âm/quá 1024 bị từ chối trước khi tạo payload lớn.

**CPU pool:** hai worker thực hiện phép `toUpperCase(Locale.ROOT)`. Đây chỉ là phép tính nhỏ để minh họa đường đi; CPU work thực có thể là parse nặng, chuẩn hóa dữ liệu hoặc thuật toán. CPU worker không gọi `read()` hoặc `write()` trên socket.

**Future result:** I/O handler chờ `job.get(2, TimeUnit.SECONDS)`; nếu CPU quá chậm thì hủy bằng `cancel(true)` và đóng socket. `cancel(true)` chỉ phát yêu cầu interruption, **không cam kết** dừng tác vụ nếu nó không kiểm tra/tuân thủ ngắt. Nếu `submit` bị `RejectedExecutionException`, handler báo lỗi theo chính sách và đóng socket.

**Ghi response:** kết quả chữ hoa được chuyển lại thành byte UTF-8, đo `response.length`, ghi header rồi payload bằng `DataOutputStream`, gọi `flush()`. Một chuỗi Unicode sau uppercase có thể đổi số byte; không tái sử dụng length của request.

**Ranh giới demo:** chương trình chạy cho đến khi được dừng, dùng blocking streams và chỉ xử lý **một request trên một connection**. Trong hệ thống thực phải bổ sung cơ chế graceful shutdown (ngừng accept, theo dõi/đóng active sockets, chờ/cancel task có deadline). `shutdownNow()` không bảo đảm tự đóng các socket đang nằm trong handler bị block.

## 6. Client để thử nghiệm cùng máy

Lưu thành **`TcpProbe.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

public class TcpProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java TcpProbe <port>");
        }

        int port = Integer.parseInt(args[0]);
        try (Socket socket = new Socket(
                InetAddress.getLoopbackAddress(), port)) {
            socket.setSoTimeout(5_000);

            byte[] data = "hello".getBytes(StandardCharsets.UTF_8);
            DataOutputStream out = new DataOutputStream(
                socket.getOutputStream());
            out.writeInt(data.length);
            out.write(data);
            out.flush();

            DataInputStream in = new DataInputStream(
                socket.getInputStream());
            int length = in.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid response size");
            }
            byte[] reply = in.readNBytes(length);
            if (reply.length != length) {
                throw new EOFException("Incomplete response");
            }
            System.out.println(
                new String(reply, StandardCharsets.UTF_8));
        }
    }
}
~~~

Terminal A:

~~~bash
javac -encoding UTF-8 BoundedTcpServer.java TcpProbe.java
java BoundedTcpServer
~~~

Server in `Port: 53123` **chẳng hạn**; cổng thực tế thay đổi do dùng cổng `0`. Ở terminal B, dùng chính số cổng server vừa in:

~~~bash
java TcpProbe 53123
~~~

Khi server còn hoạt động và chấp nhận kết nối, **stdout client** là:

~~~text
HELLO
~~~

Đây là kết quả đã kiểm tra với socket loopback: request `hello` qua TCP, CPU worker đổi thành `HELLO`, I/O handler gửi lại. Trường hợp server đã dừng hoặc đang đầy slot có thể cho EOF/IOException và sẽ **không** in dòng này.

### Kiểm tra giới hạn kết nối

Mở **4 TCP client** giữ socket mở mà chưa gửi đủ bốn byte header. Các I/O handler sẽ chờ đọc, giữ permit. Khi client thứ năm kết nối:

- `accept()` có thể trả socket thứ năm, nhưng `active.tryAcquire()` trả `false`.
- Server đóng socket đó và **không** gọi `release()` cho nó.
- Khi một trong bốn handler gặp EOF/timeout hoặc hoàn tất, `finally` release một permit.
- Một client đến sau đó lại có thể được phục vụ.

Thời điểm accept, EOF và timeout phụ thuộc lịch chạy; không viết kiểm thử khẳng định một thứ tự log hay khoảng thời gian tuyệt đối. Trong unit/load test, dùng `CountDownLatch`/`CyclicBarrier` giữ các worker ở trạng thái biết trước để kiểm tra đầy pool thay vì dựa vào `Thread.sleep` không ổn định.

## 7. CPU và I/O tách nhau nhưng còn một nút chờ

Trong demo, CPU task chạy ở pool riêng, nhưng dòng:

~~~java
byte[] response = job.get(2, TimeUnit.SECONDS);
~~~

vẫn **block I/O handler** cho đến khi CPU task hoàn thành hoặc timeout. Số I/O threads có thể bị giữ bởi các client chậm hoặc đang chờ CPU, nên tối đa bốn request vẫn đang được handler xử lý. Đây là một **chủ ý đơn giản hóa** để minh họa cách tách CPU execution và quản lý tài nguyên.

Khi số kết nối lớn, kéo dài hoặc nhiều yêu cầu trên cùng socket, xem xét:
- **Java NIO**: dùng `SocketChannel.configureBlocking(false)`, `Selector` và một hoặc vài I/O event-loop threads theo dõi channel sẵn sàng đọc/ghi. Tác vụ CPU đưa vào bounded CPU pool, kết quả chuyển về một outbound queue; event loop nhận tín hiệu `selector.wakeup()` và ghi khi channel writable. Không chạy CPU nặng trực tiếp trên event loop.
- **`AsynchronousSocketChannel`**: phối hợp callbacks/futures cho I/O; vẫn phải quản lý buffer, thứ tự phản hồi, số request in-flight và bộ nhớ hàng đợi.
- **Virtual threads**: là lựa chọn ổn định từ **Java 21**, không phải tính năng Java 17 tiêu chuẩn. Giúp code blocking dễ mở rộng hơn, nhưng vẫn cần giới hạn connection/CPU/downstream resource.

Đối với giao thức persistent connection, không được trả connection permit sau mỗi CPU task nếu socket vẫn mở. Nếu chạy nhiều CPU task song song, response có thể hoàn thành không theo thứ tự request: cần quy ước giao thức, single writer hoặc outbound queue đảm bảo ghi không bị xen byte/đổi thứ tự ngoài ý muốn.

## 8. Backpressure: phản ứng khi từng ngân sách đầy

| Điểm quá tải | Dấu hiệu | Cách ứng xử |
|---|---|---|
| Hết connection permit | `tryAcquire() == false` | Đóng socket mới hoặc gửi phản hồi bận theo giao thức đã thiết kế |
| I/O pool kín | `io.execute` ném `RejectedExecutionException` | Đóng socket và trả permit đã lấy |
| CPU pool + queue kín | `cpu.submit` ném `RejectedExecutionException` | Từ chối xử lý, giải phóng tài nguyên; không chạy CPU ngay trên acceptor |
| Client gửi chậm | `SocketTimeoutException` hoặc deadline tổng | Dừng chờ và trả tài nguyên |
| Header quá lớn/sai | `length < 0` hoặc `length > MAX_BODY` | Từ chối trước khi cấp phát payload |
| Client nhận phản hồi chậm | `write` có thể block | Giới hạn outbound buffer, thời hạn gửi hoặc đóng kết nối |
| Shutdown | Executor không nhận task mới | Ngừng accept, drain/cancel có thời hạn, đóng các active sockets |

**CPU queue ở ví dụ có sức chứa 1:** nếu 2 CPU workers đều bận và đã có một task chờ, task CPU mới có thể bị reject theo `AbortPolicy`. Điều này làm overload **lộ rõ**, thay vì âm thầm lưu hàng nghìn task. Với công việc `toUpperCase` rất nhanh, khó tái hiện reject trong một lần chạy bình thường; kiểm thử có kiểm soát cần giữ worker bận bằng latch để xác minh.

**Không retry ngay lập tức hàng loạt:** nếu clients liên tục mở kết nối mới sau khi bị từ chối, retry đồng loạt có thể làm tăng overload. Ứng dụng có thể dùng backoff + jitter và tín hiệu bận theo protocol khi phù hợp.

**Đừng chỉ giới hạn request length:** số connection, số request in-flight, CPU queue và outbound queue đều có thể gây áp lực bộ nhớ. Với I/O nonblocking, khi queue CPU đầy có thể tạm ngừng đăng ký đọc thêm dữ liệu, hoặc áp quota/đóng socket tùy hợp đồng dịch vụ.

## 9. Timeout và vòng đời cần tách rõ

- **`socket.setSoTimeout(5_000)`**: giới hạn thời gian một lần đọc blocking trên `Socket.getInputStream()`. Nó **không** đặt deadline 5 giây cho toàn connection/request.
- Một client có thể gửi từng ít byte ngay trước khi timeout lặp lại, nên request tổng thể kéo dài rất lâu. Nếu có yêu cầu chống slow sender, dùng **deadline tổng**, tốc độ tối thiểu hay quota số byte/chunk.
- **`Future.get(2, SECONDS)`**: đợi kết quả CPU tối đa 2 giây kể từ lúc bắt đầu chờ, bao gồm thời gian task ở queue. Hủy bằng `cancel(true)` không đảm bảo tác vụ bất hợp tác dừng ngay.
- **`ServerSocket.accept()`**: là thao tác chờ kết nối; timeout của listener (nếu cấu hình) là chính sách khác với `SO_TIMEOUT` của socket đã được accept.
- **`Socket.close()`**: giải phóng socket khi handler xong; chỉ release permit sau khi vòng đời được xử lý theo contract. Với persistent connection, permit kéo dài tới lúc kết nối kết thúc.
- **Graceful shutdown**: dừng acceptor, không nhận task mới, theo dõi active sockets, đóng socket nếu quá deadline rồi mới dọn pool. `shutdownNow()` không đủ bảo đảm mọi `read()` đang block được giải phóng trên mọi môi trường.

## 10. Chọn kích thước thread pool bằng số liệu

Không có công thức cố định cho mọi TCP server:

**CPU workers** nên thử từ số CPU thực JVM được cấp (`Runtime.getRuntime().availableProcessors()` là một gợi ý), rồi benchmark throughput, p95/p99 latency, context switch và contention. Thêm worker CPU quá nhiều thường chỉ tăng áp lực scheduling.

**I/O workers** có thể nhiều hơn lõi CPU nếu phần lớn thời gian chờ mạng, nhưng mỗi platform thread và socket vẫn dùng bộ nhớ/tài nguyên OS. Với Java 17 platform thread, hàng nghìn kết nối chờ lâu có thể khiến mô hình thread-per-connection đắt; khi cần mức concurrency cao nên xem NIO.

**Connection permits** phải dựa trên thời gian sống trung bình, số socket/FD có sẵn, heap/buffer và ngân sách downstream. Một kết nối nhàn rỗi vẫn giữ permit, vì vậy read idle timeout, heartbeat và chính sách max lifetime có giá trị.

**Queue capacity** quá dài có thể giấu overload và tăng tail latency. Queue quá ngắn có thể reject burst ngắn. Hãy đo thực tế và chọn độ dài, thời gian chờ, rejection policy phù hợp thay vì mặc định không giới hạn.

Các metrics hữu ích:
- `active_connections` / permit còn lại; tổng `accept`/reject/close.
- `io_pool_active_threads`, `cpu_pool_active_threads`, `cpu_queue_size`, số CPU reject.
- `requests_in_flight`, read timeout, CPU timeout, bytes request/response.
- CPU processing time, thời gian trong CPU queue, response latency p50/p95/p99.

Nếu CPU 100%, CPU queue đầy mà active connections còn chỗ, tăng connection cap có thể chỉ làm latency tệ hơn. Nếu CPU rảnh nhưng I/O threads đều block ở slow clients, xử lý timeout, concurrency model hoặc cơ chế đọc trước khi tăng CPU pool.

## 11. Lỗi phổ biến

| Lỗi | Hệ quả và cách sửa |
|---|---|
| Cho rằng `ServerSocket` backlog là giới hạn client đang phục vụ | Backlog thuộc hàng chờ accept ở OS, khác semaphore active |
| `tryAcquire()` thất bại vẫn `release()` | Thừa permit, giới hạn không còn đúng |
| Chỉ `release()` trên đường thành công | Timeout/exception làm rò permit; dùng `finally` và ownership rõ |
| Đã `submit` CPU task thì release connection permit | Socket vẫn mở nên số connection thực vượt budget |
| Dùng `Executors.newFixedThreadPool` và cho rằng task queue bounded | Fixed thread mặc định có queue không giới hạn dung lượng |
| Dùng `CallerRunsPolicy` trên CPU pool | CPU task có thể chạy trong I/O thread, gây starvation |
| Để CPU worker trực tiếp `socket.read()` | CPU worker thành thread chờ mạng, phá sự tách biệt |
| `future.get()` nghĩa là I/O đã nonblocking | I/O handler vẫn chờ CPU result; nonblocking cần mô hình I/O khác |
| Mã hóa frame length bằng `String.length()` | Unicode UTF-8 có số byte khác số đơn vị UTF-16 |
| Chỉ dùng `SO_TIMEOUT` và nghĩ đã có deadline tổng | Đọc rải rác có thể kéo dài request |
| Nhiều CPU tasks cùng ghi một socket không phối hợp | Byte/response có thể xen/đảo; dùng single writer hoặc queue |
| `shutdownNow()` sẽ đóng mọi socket | Không đảm bảo; phải quản lý socket và shutdown lifecycle |

## 12. Bài tập tự kiểm tra

1. Listener có `backlog=128` và `Semaphore(10)`. Ứng dụng có thể chủ động phục vụ cùng lúc tối đa bao nhiêu connection theo semaphore? Backlog có làm số ấy thành 128 không?
2. `MAX_ACTIVE=4`, bốn client đã có permit, client thứ năm vừa được `accept()`. Điều gì phải xảy ra nếu `tryAcquire()` trả false? Có gọi `release()` không?
3. Một socket đã mượn permit nhưng `io.execute` từ chối task. Hai hành động quan trọng nào phải xảy ra?
4. Với 2 CPU worker và queue 1, khi cả hai worker đang chạy và queue đã đầy, `AbortPolicy` xử lý `submit` mới ra sao?
5. Tại sao `CallerRunsPolicy` có thể phá mục tiêu “CPU tách khỏi chờ I/O”?
6. I/O handler gọi `Future.get()`. CPU có đang chạy trên I/O thread không? I/O thread có còn bị block không?
7. Client gửi một byte mỗi 4 giây trong khi `SO_TIMEOUT=5_000`. Có thể kết luận server sẽ đóng sau đúng 5 giây tính từ lúc bắt đầu request không?
8. Nếu giao thức dùng nhiều request trên cùng TCP connection, khi nào trả connection permit? Cần làm gì nếu CPU responses kết thúc không theo thứ tự?

**Đáp án trọng tâm:** (1) 10 phiên được nhận phục vụ; backlog không thay đổi cap đó; (2) đóng socket mới, không release; (3) đóng socket và trả permit đúng một lần; (4) ném `RejectedExecutionException`; (5) CPU task chạy ngay trên thread nộp; (6) CPU ở pool riêng nhưng I/O thread vẫn chờ; (7) không, cần deadline tổng; (8) giữ permit tới khi socket kết thúc và quản lý thứ tự response/outbound queue.

## 13. Ghi nhớ

- **Cap connection** bằng admission/permit rõ nghĩa, khác với backlog; luôn đóng socket và trả đúng một permit ở các nhánh thích hợp.
- **Tách CPU pool khỏi I/O pool**, giới hạn worker lẫn queue và xác định chiến lược reject, timeout, backpressure.
- **Không đồng nhất CPU offload với nonblocking I/O**: ví dụ vẫn có `Future.get()` trên I/O handler; tải lớn với nhiều socket chờ cần xem NIO.
- **Đo để chọn ngân sách**: active connections, CPU queue, số reject và latency giúp tìm đúng nút thắt.
- **Đảm bảo toàn bộ lifecycle**: timeout, input size, phản hồi, đóng socket, release, shutdown; giới hạn giấy tờ không có tác dụng nếu một nhánh lỗi rò tài nguyên.

### Tài liệu đối chiếu

- [Oracle Java SE 17 — ServerSocket, backlog và accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Oracle Java SE 17 — Socket.setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Oracle Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Oracle Java SE 17 — ThreadPoolExecutor, bounded queues, RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle Java SE 17 — Future.get, cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle Java SE 17 — NIO Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
