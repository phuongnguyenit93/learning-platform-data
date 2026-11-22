# Kiểm thử lỗi giữa chừng, đóng có thứ tự và không để rò socket hoặc luồng

**Một kết nối thành công không chứng minh chương trình Java networking đúng.** Các lỗi khó nhất thường xuất hiện khi server đã nhận một phần request rồi ngắt, response thiếu bytes, một thread đóng socket mà thread khác vẫn đang đọc, hoặc executor chưa dừng khi ứng dụng cho rằng đã shutdown.

Bài Knowledge thuộc **Java Advance - networking → Thực nghiệm mạng**, hướng dẫn tạo các phép thử **có thể lặp lại**, **không dùng Internet**, chủ động chèn lỗi và kiểm tra toàn bộ lifecycle trên Java 17+. Nội dung ưu tiên kiểm chứng bằng API/observable state thay vì đoán từ thông điệp `SocketException: Broken pipe` hay `Connection reset` vốn phụ thuộc OS và thời điểm I/O.

**Bốn bất biến cần chấm:**
1. **Protocol completeness**: không đưa frame bị cắt giữa chừng vào business layer.
2. **Ordered close**: hoàn tất ghi/flush, đóng đúng chiều TCP khi protocol cho phép, đọc nốt response rồi đóng toàn socket.
3. **Failure-safe cleanup**: dù handler ném IOException, accepted socket và các tài nguyên do test sở hữu vẫn được giải phóng.
4. **No surviving workers**: listener đóng; executor terminated; thread do test tạo không còn sống và các active sockets được đếm về 0.

Bài cung cấp ba chương trình Java 17+ hoàn chỉnh:
- `TruncatedFrameDemo.java`: length-prefix 12 bytes, server chỉ gửi 5 rồi FIN; kiểm chứng thiếu dữ liệu bằng `readNBytes` và `readFully`.
- `OrderedShutdownDemo.java`: PING/PONG, `shutdownOutput()` hai phía, close đúng thứ tự và kiểm tra thread/socket lifecycle.
- `SocketLeakAuditDemo.java`: 12 requests, bốn lỗi IOException được inject sau khi đọc request; accepted=closed=12, active=0, executor terminated.

Các chương trình đã được chạy trên loopback bằng JDK dùng API tương thích Java 17; không cần server bên ngoài, dependency bổ sung, password hoặc token.

## 1. Kiểm thử network cần đo hơn dữ liệu đầu ra

Một chương trình echo có thể in PONG trong khi vẫn bị rò thread, socket hoặc body parser sai. Ví dụ:
- Client nhận nửa body rồi thấy EOF, nhưng code vẫn trả object “thành công”.
- Server đọc request xong rồi gặp exception và bỏ qua việc close accepted Socket.
- Client dùng `Future.get(3,SECONDS)`; test thread thoát sau ba giây nhưng worker vẫn block mãi ở `ServerSocket.accept()`.
- Một response được gửi nhưng `ExecutorService` chưa shutdown, non-daemon thread khiến JVM không kết thúc.
- Test chỉ chờ một giây bằng `Thread.sleep` rồi xem số Thread.activeCount; kết quả nhiễu bởi JVM GC/JIT và scheduling.

Đối với thí nghiệm, phải tách **functional result**, **network failure semantics** và **resource ownership**:

| Tầng | Vấn đề | Tiêu chí |
| --- | --- | --- |
| Byte stream | Đã nhận đủ bytes theo frame? | declaredLength == receivedLength |
| Protocol | EOF ở boundary hợp lệ hay giữa message? | complete hoặc TRUNCATED_FRAME |
| Socket | Client/accepted/listener đóng ở mọi nhánh? | isClosed, accepted/closed counts |
| Task | Future thành công, lỗi hay cancellation? | Terminal result, preserved cause |
| Executor | Còn worker sống sau shutdown? | awaitTermination/isTerminated, tracked thread dead |
| System | Resource usage tăng dài hạn? | OS handles/FDs và soak tests |

Một bài test đáng tin **phải fail khi resource chưa giải phóng**, không chỉ assert response body.

## 2. Ma trận lỗi trước khi viết code

| Trường hợp | Fault injection | Điều mong đợi |
| --- | --- | --- |
| Bình thường | Không lỗi | Đủ body, close hoàn tất |
| EOF hợp lệ | Peer flush, `shutdownOutput` sau message | Read tới EOF mà không mất payload |
| Frame thiếu | Prefix 12 bytes, body 5 rồi FIN | Phát hiện truncated |
| IOException trong handler | Throw sau khi đọc request byte | Socket vẫn close, active giảm |
| Early close | Peer đóng không gửi response | Client nhận EOF hoặc error, không treo |
| Read timeout | Peer im lặng giữ socket mở | `SocketTimeoutException`, không đồng nhất EOF |
| Accept timeout | Không có client mới | Timeout có giới hạn, listener không tự hỏng |
| Abortive reset | `SO_LINGER=0` trong test riêng | Lỗi quan sát được; không assert text |
| Half-close | Client flush và shutdown chiều gửi | Server vẫn reply ở chiều ngược |
| Executor shutdown | Ngừng tasks mới, await | Terminated hoặc test FAIL |
| Concurrent shutdown | Thread khác đóng SocketChannel | Cleanup, phân loại local close |
| Leak audit | N connections, một số exception | accepted==closed, active==0 |

Không bắt mọi IOException rồi coi là “lỗi được inject”. Với test nghiêm ngặt, dùng **custom marker exception** cho lỗi giả lập; lỗi khác phải được propagate. Cũng không đặt `SO_LINGER=0` trên mọi socket để cố tạo một chuỗi Broken pipe cố định.

## 3. Fixture TCP loopback ổn định

Dùng `ServerSocket` bind loopback và chọn port 0:

~~~java
ServerSocket listener = new ServerSocket(
        0, 4, InetAddress.getByName("127.0.0.1"));
listener.setSoTimeout(3000);
int port = listener.getLocalPort();
~~~

Đây chỉ là snippet. Cần close listener trong try-with-resources hoặc finally. Port 0 yêu cầu hệ điều hành cấp cổng rảnh, tránh test xung đột khi CI chạy song song. Địa chỉ 127.0.0.1 không mở cổng công khai.

Ba giới hạn khác nhau:
- `ServerSocket.setSoTimeout(3000)`: giới hạn thời gian **một lần accept** đang chờ.
- `Socket.setSoTimeout(2000)`: giới hạn thời gian **một blocking read** từ Socket InputStream.
- `Future.get(3, TimeUnit.SECONDS)`: giới hạn thời gian test thread chờ worker Future.

**Không có giới hạn nào tự động là total deadline cho toàn transaction.** Và Future.get(timeout) **không tự dừng worker**: khi timeout phải có cleanup/cancellation chính xác.

Khi fixture mở một thread để accept, bind listener **trước** khi start client. Đừng dựa vào sleep để đoán server đã sẵn sàng: hãy dùng đồng bộ qua Future, latch hoặc protocol handshake khi cần.

## 4. TCP là byte stream, không phải danh sách message

Một giao thức đơn giản có thể gửi **4 bytes số nguyên length (big-endian)** trước body. Ví dụ:

~~~text
00 00 00 0C | h e l l o w o r l d ! ! 
  12 bytes  |       body dự kiến 12 bytes
~~~

Nếu server chỉ gửi:

~~~text
00 00 00 0C | h e l l o | FIN
 length=12  | 5 bytes  | end of stream
~~~

thì TCP kết thúc chiều gửi bằng FIN bình thường, **nhưng frame của application bị thiếu**. Client phải nhận diện lỗi thay vì trả thành công.

JDK cung cấp hai cách:
- `InputStream.readNBytes(expected)`: trả **tối đa** expected bytes, có thể trả array **ngắn hơn** nếu EOF đến sớm. Phải so sánh array.length.
- `DataInputStream.readFully(byte[expected])`: yêu cầu đủ bytes, nếu gặp EOF sớm thì ném `EOFException`.

Không đồng nhất:
- `read()==-1` là EOF của stream.
- `read()==0` với SocketChannel nonblocking có thể là chưa có bytes hoặc buffer đầy; không phải EOF.
- EOF xảy ra sau dữ liệu đầy đủ là bình thường nếu protocol thiết kế như vậy.
- EOF xảy ra giữa frame là **truncated message**, dù không có TCP RST.

**Giới hạn kích thước:** Bên nhận phải validate declaredLength trong khoảng hợp lệ trước khi cấp phát mảng. Không bao giờ lấy một số nguyên tùy ý từ peer rồi dùng thẳng làm `new byte[declared]`.

## 5. Ví dụ Java 17+ số 1: lỗi giữa chừng bằng partial FIN

**TruncatedFrameDemo.java** tạo server đọc hai connections tuần tự:
- Server ghi int 12 rồi năm byte của chuỗi hello, flush và `shutdownOutput()`.
- Client thứ nhất dùng `readNBytes(12)`; trả năm bytes nên test đánh dấu truncated.
- Client thứ hai dùng `readFully(new byte[12])`; bắt EOFException.
- Client/accepted sockets nằm trong try-with-resources, server task dùng Future và pool shutdown.

Tạo file **TruncatedFrameDemo.java**:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TruncatedFrameDemo {
    static final int EXPECTED = 12;

    static void serve(ServerSocket listener) throws Exception {
        for (int i = 0; i < 2; i++) {
            try (Socket peer = listener.accept()) {
                DataOutputStream out =
                        new DataOutputStream(peer.getOutputStream());
                out.writeInt(EXPECTED);
                out.write("hello".getBytes(StandardCharsets.UTF_8));
                out.flush();
                peer.shutdownOutput();
            }
        }
    }

    static Socket connect(ServerSocket listener) throws Exception {
        Socket client = new Socket(
                "127.0.0.1", listener.getLocalPort());
        client.setSoTimeout(2000);
        return client;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(
                0, 4, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(3000);

            Future<?> server = executor.submit(() -> {
                try {
                    serve(listener);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try (Socket client = connect(listener)) {
                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                int expected = in.readInt();
                byte[] got = in.readNBytes(expected);

                System.out.println(
                        "Declared frame bytes: " + expected);
                System.out.println(
                        "Received frame bytes: " + got.length);
                System.out.println(
                        "Truncated: " + (got.length != expected));
            }

            boolean caught = false;
            try (Socket client = connect(listener)) {
                DataInputStream in =
                        new DataInputStream(client.getInputStream());
                int expected = in.readInt();
                in.readFully(new byte[expected]);
            } catch (EOFException eof) {
                caught = true;
            }

            System.out.println(
                    "readFully raised EOFException: " + caught);
            server.get(3, TimeUnit.SECONDS);
        } finally {
            executor.shutdown();
            boolean done = executor.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!done) executor.shutdownNow();
            System.out.println("Executor terminated: " + done);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 TruncatedFrameDemo.java
java TruncatedFrameDemo
~~~

Kết quả đã kiểm thử:

~~~text
Declared frame bytes: 12
Received frame bytes: 5
Truncated: true
readFully raised EOFException: true
Executor terminated: true
~~~

**Kết luận:** Cùng một lỗi frame thiếu bytes có hai cách nhận diện: length mismatch hoặc EOFException. Nếu code không kiểm tra số bytes readNBytes trả về, một response bị cắt vẫn có thể bị coi là thành công. Fixture gửi FIN, không chủ động reset; phải ghi log **TRUNCATED_FRAME**, không tự gọi nó là Connection reset.

Các socket trong code được đóng bằng try-with-resources. Tuy nhiên giá trị Executor terminated phải được **assert true** trong test tự động; nếu false, fallback shutdownNow chưa chứng minh worker đã dừng. Trong code production, kiểm tra và dọn thêm cho trường hợp đó.

## 6. Đóng socket có thứ tự: ngừng gửi nhưng tiếp tục nhận

Với giao thức PING/PONG dùng EOF để đánh dấu hết request:

~~~text
Client                                      Server
  |                                            |
  |---------- PING + newline ---------------->|
  |-------- shutdownOutput / FIN ------------>|
  |                                            | readLine -> PING
  |                                            | readLine -> null (EOF)
  |<---------------- PONG + newline -----------|
  |<----------- shutdownOutput / FIN ----------|
  | readLine -> PONG                           |
  | readLine -> null                           |
  |                                            |
  | close Socket                        close accepted Socket
  | close listener                      complete Future
  | pool.shutdown + awaitTermination          |
~~~

**Socket.shutdownOutput() là half-close**: chiều gửi kết thúc, chiều đọc vẫn hoạt động. Do đó client có thể gửi hết request rồi tiếp tục chờ PONG.

Bẫy rất quan trọng: nếu BufferedWriter được tạo từ socket.getOutputStream, gọi writer.close ngay sau PING có thể đóng **toàn Socket**, làm mất khả năng đọc PONG. Thay bằng:
1. write PING.
2. writer.flush().
3. socket.shutdownOutput().
4. Đọc response và EOF.
5. Cuối cùng socket.close().

Không phải protocol nào cũng dùng half-close kiểu này: HTTP keep-alive, TLS và WebSocket có shutdown/framing semantics riêng. Không đưa raw FIN vào giao thức khi nó kỳ vọng connection tiếp tục.

## 7. Ví dụ Java 17+ số 2: PING/PONG và kiểm tra tài nguyên

**OrderedShutdownDemo.java** có một worker được đặt tên bằng ThreadFactory. Server đọc PING/EOF rồi trả PONG/EOF. Client chỉ đóng sau khi đọc response. Cuối cùng code kiểm tra client socket, accepted server socket, listener, executor và tracked worker.

Tạo file **OrderedShutdownDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class OrderedShutdownDemo {
    static String handle(
            ServerSocket listener,
            AtomicReference<Socket> accepted) throws Exception {

        try (Socket peer = listener.accept()) {
            accepted.set(peer);
            peer.setSoTimeout(3000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            peer.getInputStream(),
                            StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            peer.getOutputStream(),
                            StandardCharsets.UTF_8));

            String first = in.readLine();
            boolean requestEof = in.readLine() == null;

            out.write("PONG\n");
            out.flush();
            peer.shutdownOutput();

            return "Server request: " + first
                    + "|EOF=" + requestEof;
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Thread> workerThread =
                new AtomicReference<>();
        AtomicReference<Socket> accepted = new AtomicReference<>();

        ExecutorService pool = Executors.newSingleThreadExecutor(
                task -> {
                    Thread t = new Thread(
                            task, "ordered-demo-worker");
                    workerThread.set(t);
                    return t;
                });

        ServerSocket listener = new ServerSocket(
                0, 2, InetAddress.getByName("127.0.0.1"));
        listener.setSoTimeout(3000);

        Socket client = null;
        boolean terminated = false;

        try {
            Future<String> outcome =
                    pool.submit(() -> handle(listener, accepted));

            client = new Socket(
                    "127.0.0.1", listener.getLocalPort());
            client.setSoTimeout(3000);

            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(),
                            StandardCharsets.UTF_8));
            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(),
                            StandardCharsets.UTF_8));

            out.write("PING\n");
            out.flush();
            client.shutdownOutput();

            String answer = in.readLine();
            boolean responseEof = in.readLine() == null;

            System.out.println("Client response: " + answer);
            System.out.println(
                    "Client response EOF: " + responseEof);
            System.out.println(
                    outcome.get(3, TimeUnit.SECONDS));

        } finally {
            if (client != null) client.close();
            listener.close();
            pool.shutdown();
            terminated = pool.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!terminated) pool.shutdownNow();
        }

        System.out.println("Client closed: " + client.isClosed());
        System.out.println(
                "Accepted socket closed: " + accepted.get().isClosed());
        System.out.println("Listener closed: " + listener.isClosed());
        System.out.println("Executor terminated: " + terminated);
        System.out.println(
                "Worker alive: " + workerThread.get().isAlive());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OrderedShutdownDemo.java
java OrderedShutdownDemo
~~~

Stdout đã kiểm tra:

~~~text
Client response: PONG
Client response EOF: true
Server request: PING|EOF=true
Client closed: true
Accepted socket closed: true
Listener closed: true
Executor terminated: true
Worker alive: false
~~~

Dòng đầu và thứ hai xác nhận client **không đóng quá sớm**, nên vẫn đọc được PONG. Dòng thứ ba xác nhận server đã thấy EOF chiều request. Những dòng cuối chứng minh cleanup đúng cho resources mà **fixture tự theo dõi**. Trong server nhiều client, còn phải thu thập mọi accepted sockets và pending tasks, không chỉ một.

## 8. Stop order: lý do phải đóng từng loại tài nguyên

Một service mạng có thể áp mô hình dừng:
1. Đánh dấu state STOPPING và ngừng nhận công việc mới.
2. Ngừng accept hoặc đóng listener, tránh connection mới vào lúc dọn.
3. Chờ một khoảng hữu hạn để inflight requests hoàn tất protocol.
4. Sau deadline, đóng các active sockets/channels còn lại.
5. Fail/cancel mọi queued futures và dọn request contexts.
6. Gọi ExecutorService.shutdown(), chờ awaitTermination().
7. Nếu timeout, shutdownNow() theo policy rồi kiểm tra lại.
8. Assert listener closed, active socket registry empty, executor terminated và owned worker threads stopped.

**Thứ tự có thể đổi tùy protocol.** Ví dụ một HTTP server có thể cần chờ in-flight responses trước khi đóng sockets, còn một server đọc raw PING sẽ chủ động half-close sau message. Quan trọng là đặt **grace period và deadline hữu hạn**, không để shutdown treo mãi.

Phân biệt:
- shutdown() không đợi.
- awaitTermination() mới đợi có hạn.
- shutdownNow() chỉ best effort.
- Future.get(timeout) chỉ timeout chờ, không tự hủy task.
- Future.cancel(true) có thể interrupt nhưng không chắc chắn unblock mọi blocking socket I/O.
- Đóng Socket/ServerSocket thuộc ownership đúng có thể giúp blocked read/accept kết thúc bằng exception.

## 9. Các resource cần một owner chịu trách nhiệm

| Resource | Tạo bởi ai | Dọn bởi ai |
| --- | --- | --- |
| ServerSocket listener | Test server/bootstrap | Server lifecycle owner |
| Accepted Socket | ServerSocket.accept | Connection handler trong try-with-resources |
| Outbound client Socket | Client factory/request | Client scope |
| Input/output streams | Socket | Stream owner hoặc Socket owner theo protocol |
| ExecutorService | Test/service coordinator | Coordinator shutdown + await |
| Future | Submitter | Caller theo dõi result/cancel |
| SocketChannel/Selector | Event loop | Event-loop lifecycle owner |
| AsynchronousSocketChannel | Async connection manager | Connection context |

Một lỗi thiết kế: parent đóng Socket bằng try-with-resources trong khi worker còn dùng reference đó. Lúc này worker nhận IOException do **local lifecycle race**, không phải luôn do peer.

Với Socket, đóng InputStream/OutputStream được lấy từ socket thường đóng cả socket. Vì vậy không dùng close writer như dấu kết thúc chiều gửi nếu client còn cần đọc response; dùng flush + shutdownOutput cho protocol phù hợp.

## 10. Thực nghiệm không rò tài nguyên phải có counters

Đừng chỉ so sánh Thread.activeCount() trước và sau: background threads của JVM/GC/JIT hoặc framework có thể thay đổi độc lập, và thread count không đo socket file descriptors.

Cách đo tốt hơn:
- **accepted** tăng sau accept thành công.
- **active** tăng khi handler bắt đầu sở hữu socket.
- **closed** tăng ở finally sau khi socket được đóng.
- **injected** tăng khi expected injected failure thật sự được bắt.
- **successful replies** và **early closes** đếm luồng client đã quan sát.
- **executor terminated** xác minh shutdown hoàn tất.
- **Tracked ThreadFactory** giữ reference thread do test tạo để kiểm tra `!isAlive()`.
- **isClosed()** trên client/accepted/listener thật.
- Với soak test, kết hợp OS open FD/handle counts, active connections và JVM thread dumps.

**Giới hạn của counter:** accepted=closed và active=0 cho biết các sockets *được fixture đếm* đã đi qua cleanup. Chúng không chứng minh tuyệt đối không có một socket khác bị bỏ quên ngoài registry. TIME_WAIT là TCP state ở OS có thể tồn tại sau Java Socket.close mà không phải leak.

## 11. Fault injection deterministic trong handler

Giả sử server xử lý 12 requests theo thứ tự; các index chia hết cho 3 (0,3,6,9) được inject lỗi sau khi đọc một byte:

~~~java
active.incrementAndGet();
try (socket) {
    socket.setSoTimeout(2000);
    int requestByte = socket.getInputStream().read();
    if (requestByte == -1) {
        throw new EOFException("missing request");
    }
    if (index % 3 == 0) {
        throw new IOException("injected failure");
    }
    socket.getOutputStream().write(66);
    socket.shutdownOutput();
} finally {
    closed.incrementAndGet();
    active.decrementAndGet();
}
~~~

Đây là **snippet**, cần định nghĩa counters, Socket và index. Try-with-resources bảo đảm Socket.close khi IOException xảy ra; finally vẫn giảm active. Đây là cách test cleanup logic chắc hơn việc cố tạo một OS Broken pipe message.

Nếu handler chủ động throw một IOException thường, catch ở server nên phân biệt **marker lỗi inject** với network IOException bất ngờ. Không coi bất cứ IOException nào xảy ra ở index thứ 3 là expected mà bỏ qua.

## 12. Ví dụ Java 17+ số 3: 12 requests và 4 lỗi giữa chừng

Tạo file **SocketLeakAuditDemo.java**:

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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class SocketLeakAuditDemo {
    static final int REQUESTS = 12;

    static final AtomicInteger accepted = new AtomicInteger();
    static final AtomicInteger closed = new AtomicInteger();
    static final AtomicInteger active = new AtomicInteger();
    static final AtomicInteger injected = new AtomicInteger();

    static void handle(Socket socket, int index)
            throws IOException {
        active.incrementAndGet();

        try (socket) {
            socket.setSoTimeout(2000);
            int input = socket.getInputStream().read();

            if (input == -1) {
                throw new EOFException("missing request byte");
            }
            if (index % 3 == 0) {
                throw new IOException(
                        "injected failure after receiving request byte");
            }

            socket.getOutputStream().write(66);
            socket.shutdownOutput();
        } finally {
            closed.incrementAndGet();
            active.decrementAndGet();
        }
    }

    static void serve(ServerSocket listener)
            throws IOException {
        for (int i = 0; i < REQUESTS; i++) {
            Socket socket = listener.accept();
            accepted.incrementAndGet();

            try {
                handle(socket, i);
            } catch (IOException expected) {
                if (i % 3 == 0) {
                    injected.incrementAndGet();
                } else {
                    throw expected;
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Thread> worker =
                new AtomicReference<>();

        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> {
                    Thread thread = new Thread(
                            task, "leak-audit-worker");
                    worker.set(thread);
                    return thread;
                });

        ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getByName("127.0.0.1"));
        listener.setSoTimeout(3000);

        int ok = 0;
        int failed = 0;
        boolean terminated = false;

        try {
            Future<?> future = executor.submit(() -> {
                try {
                    serve(listener);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });

            for (int i = 0; i < REQUESTS; i++) {
                try (Socket client = new Socket(
                        "127.0.0.1",
                        listener.getLocalPort())) {
                    client.setSoTimeout(2000);
                    client.getOutputStream().write(i);

                    int answer = client.getInputStream().read();
                    if (answer == 66) {
                        ok++;
                    } else if (answer == -1) {
                        failed++;
                    } else {
                        throw new AssertionError(
                                "unexpected byte " + answer);
                    }
                }
            }

            future.get(3, TimeUnit.SECONDS);
        } finally {
            listener.close();
            executor.shutdown();
            terminated = executor.awaitTermination(
                    3, TimeUnit.SECONDS);
            if (!terminated) {
                executor.shutdownNow();
            }
        }

        System.out.println("Requests: " + REQUESTS);
        System.out.println("Successful replies: " + ok);
        System.out.println("Expected early closes: " + failed);
        System.out.println("Faults injected: " + injected.get());
        System.out.println(
                "Server sockets accepted: " + accepted.get());
        System.out.println(
                "Server sockets closed: " + closed.get());
        System.out.println(
                "Active server sockets: " + active.get());
        System.out.println(
                "Listener closed: " + listener.isClosed());
        System.out.println(
                "Executor terminated: " + terminated);
        System.out.println(
                "Tracked worker alive: "
                + worker.get().isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SocketLeakAuditDemo.java
java SocketLeakAuditDemo
~~~

Stdout đã kiểm thử:

~~~text
Requests: 12
Successful replies: 8
Expected early closes: 4
Faults injected: 4
Server sockets accepted: 12
Server sockets closed: 12
Active server sockets: 0
Listener closed: true
Executor terminated: true
Tracked worker alive: false
~~~

**Đọc kết quả:**
- 12/12 accepted sockets đã qua close path.
- Active handler/socket counter trở về 0.
- 8 replies thành công, 4 early closes chứng minh failure injection thực sự chạy.
- Listener được đóng, executor terminated và worker thread do test tạo đã ngừng.

**Giới hạn:** Server tuần tự, request body một byte. Đây là fixture đo cleanup code path, không phải bài load test cho server công khai. Với production, cần bounded concurrency, limits và registry cho mọi connection.

## 13. Try-with-resources và finally: khác vai trò

~~~java
Socket peer = listener.accept();
try (peer) {
    process(peer);
} finally {
    recordFinished();
}
~~~

Đây là snippet: `process` và `recordFinished` là helpers ứng dụng. Khi process ném IOException, Java vẫn gọi close Socket trước khi vào finally. Trong code thật, hạn chế những thao tác có thể ném exception **giữa accept và điểm bắt đầu ownership scope**, vì đó là khoảng có nguy cơ leak.

Try-with-resources không tự shutdown ExecutorService trên **Java 17** (lúc đó ExecutorService chưa AutoCloseable). Coordinator vẫn phải có finally cho pool shutdown/await, pending Futures, listener và resources ngoài lexical scope.

Khi exception xảy ra cả ở body và close, Java có thể gắn exception đóng vào Throwable.getSuppressed(). Log root cause cùng suppressed exceptions trong diagnostics; không làm mất nguyên nhân lỗi.

## 14. Read timeout, accept timeout và total deadline

| API | Giới hạn | Không giới hạn |
| --- | --- | --- |
| ServerSocket.setSoTimeout(ms) | Một lần accept đang chờ | Toàn server lifetime |
| Socket.setSoTimeout(ms) | Một lần blocking read | Tổng thời gian body/transaction |
| Socket.connect(address,timeout) | Bước connect | Response read |
| Future.get(timeout) | Caller chờ Future | Worker task hoặc socket |
| ExecutorService.awaitTermination(timeout) | Caller đợi shutdown | Force stop khi trả false |
| Thread.join(timeout) | Caller chờ thread | Thread tự dừng |

Nếu worker đang chờ read, việc caller hết hạn Future.get không tự dừng worker. Cần signal cancellation, close socket do owner quản lý, và shutdown executor có giới hạn. Không in PASS khi executor vẫn sống.

Nếu server gửi một byte trước mỗi read timeout, tổng request có thể kéo dài rất lâu. Với ứng dụng thật, thêm **end-to-end deadline**, payload length cap, connection cap và giới hạn queue/concurrency.

## 15. Test Connection reset hoặc Broken pipe như thế nào?

**Broken pipe** thường là message OS khi ghi vào socket không còn nhận, không phải Java exception class riêng. **Connection reset** là tín hiệu TCP abort; Java thường ném IOException/SocketException với message thay đổi theo OS/provider/timing.

Không làm automated CI phụ thuộc:
- Chuỗi lỗi chính xác bằng tiếng Anh.
- Phải thấy Broken pipe ở **lần write đầu tiên** sau peer-close.
- Phải luôn có RST thay vì FIN khi process đóng.
- Một lần write success tức peer đã xử lý request.

Test được OS hỗ trợ có thể dùng `Socket.setSoLinger(true,0)` rồi close để thử abortive termination, nhưng không hard-code class/message và không dùng hành vi này làm close strategy trong production.

Quan trọng: nếu client gửi POST có side effects, server có thể đã commit rồi connection reset trước response. Retry tự động có thể thực thi trùng. Cần idempotency key/status query/reconciliation theo contract của API.

**Fault injection deterministic** trong handler/transport adapter là lựa chọn tốt hơn để test app cleanup, trong khi RST/FIN packet evidence cần kiểm thử riêng ở tầng network.

## 16. NIO, Selector và Async I/O lifecycle

Với SocketChannel + Selector:
- Khi nonblocking read trả 0, không coi là EOF; chờ OP_READ readiness.
- Khi read trả -1, đó là EOF; tùy protocol, half-close hoặc cancel selection key/close channel.
- SelectionKey.cancel không tự đóng SocketChannel.
- Selector.wakeup giúp event loop thoát select để quan sát stop flag; đóng Selector cuối lifecycle.
- Đóng SocketChannel từ thread khác khi blocked I/O có thể tạo AsynchronousCloseException.
- Interrupt blocked NIO I/O có thể đóng channel và tạo ClosedByInterruptException.
- Đừng dùng channel đã terminal cho I/O mới.

Với AsynchronousSocketChannel, completion handler có thể nhận completed(-1) khi EOF hoặc failed(exception) khi lỗi. Hủy Future/đóng channel cần quản lý callback lifecycle, không reuse ByteBuffer khi một operation cũ còn có thể hoàn tất.

Một lỗi race phổ biến: watchdog đóng socket khi writer đang gửi response; writer ném IOException. Đó có thể là **local cancellation**, không nhất thiết peer reset. Ghi closeReason và owner, tránh retry/double response.

## 17. Quy trình kiểm tra leak sau test

**Trước khi assert**:
1. Đợi mọi server/client Futures hoàn thành hoặc timeout.
2. Đóng listeners và mọi active sockets còn được registry quản lý.
3. Shutdown executor, awaitTermination có hạn và kiểm tra kết quả.
4. Kiểm tra accepted/closed/active counters khi không còn handlers đang chạy.
5. Kiểm tra tracked Thread objects và concrete Socket.isClosed.
6. Nếu test dài, theo dõi process FDs/handles, thread dumps, heap và TCP states để phát hiện xu hướng dài hạn.

**Không dùng một snapshot Thread.activeCount** làm kết luận. Nó có thể thay đổi vì JVM hoặc libraries khác. **Không coi TIME_WAIT là Java leak:** TIME_WAIT là trạng thái TCP ở kernel có thể tiếp tục sau close.

Các phép đo fixture không chứng minh toàn JVM tuyệt đối không leak; chúng chứng minh nguồn tài nguyên được fixture sở hữu đã đi theo cleanup contract.

## 18. Checklist code review

| Câu hỏi | Kết quả cần |
| --- | --- |
| Có testcase lỗi giữa chừng, không chỉ success? | Có |
| Có validate framing khi EOF? | Có |
| Có MAX_FRAME_BYTES/body cap? | Có ở production |
| Socket listener bind loopback port 0 trong CI? | Có |
| Accept/read có timeout? | Có |
| Future.get có deadline và cleanup fallback? | Có |
| Accepted socket được close cả khi handler throw? | Có |
| Client socket close sau khi đã đọc response? | Có |
| Half-close có đúng protocol? | Có |
| Executor.shutdown + awaitTermination? | Có |
| isTerminated và tracked worker dead? | Có |
| accepted==closed và active==0? | Có |
| Có phân biệt injected exception với I/O bất ngờ? | Có |
| Không dựa vào exact Broken pipe string? | Có |
| Không auto-retry non-idempotent request sau reset? | Có |
| NIO selector key/channel closure đúng owner? | Có |
| Logs có cause, suppressed, operation, bytes, closeReason? | Có |
| Không log payload/token/password nhạy cảm? | Có |

## 19. Những lỗi thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Chỉ test echo thành công | Không biết failure path | Inject partial frame/handler throw |
| Bỏ qua length của readNBytes | Silent truncation | Compare expected/actual |
| Catch EOFException rồi trả thành công | Trả partial message | Báo truncated protocol error |
| Không đặt timeout | Test treo | Accept/read/Future deadlines |
| Nghĩ Future.get(timeout) sẽ kill task | Worker vẫn sống | Close owned resources + cancel |
| Quên shutdown executor | Non-daemon worker giữ JVM | shutdown/await/verify |
| Đóng writer trước khi đọc reply | Có thể close socket sớm | Flush + shutdownOutput |
| Dùng port cố định | Conflict CI song song | Port 0 |
| Bind 0.0.0.0 | Mở fixture ra LAN | Loopback |
| Dùng Thread.activeCount trước/sau | Nhiễu JVM threads | Custom ThreadFactory |
| Counter đóng tăng trước close | False PASS | Count sau actual close |
| Bắt IOException quá rộng | Nuốt lỗi bất ngờ | Marker exception cho injection |
| Không giới hạn frame length | OOM | Validate trước allocate |
| Cancel key nhưng giữ channel | Leak | Close channel riêng |
| Retry mọi POST lỗi transport | Side effects trùng | Idempotency keys |
| Dựa vào Broken pipe message | Không portable | Class/phase/protocol diagnostics |
| Coi TIME_WAIT là leak | Phân tích sai | OS FD/handle process metrics |
| Assertions trước khi Futures xong | False leak | Join rồi assert |
| Đóng resources ngoài ownership | Race và AsynchronousCloseException | Một owner/lifecycle rõ |

## 20. Câu hỏi tự kiểm tra

**1.** Vì sao test nhận được PONG chưa chứng minh ứng dụng không leak?  
**Đáp án:** Chưa kiểm tra close sockets, executor termination và threads.

**2.** Frame khai báo 12 bytes nhưng chỉ nhận 5 rồi FIN có thành công không?  
**Đáp án:** Không, đây là truncated frame.

**3.** readNBytes(12) có tự ném EOFException khi thiếu không?  
**Đáp án:** Không nhất thiết; nó có thể trả mảng ngắn.

**4.** readFully(new byte[12]) khi thiếu dữ liệu phản ứng sao?  
**Đáp án:** Ném EOFException.

**5.** Vì sao loopback/port 0 hữu ích?  
**Đáp án:** Test độc lập Internet, ít xung đột port và không mở public.

**6.** Socket.setSoTimeout có tạo total deadline cho request không?  
**Đáp án:** Không, chỉ blocking read.

**7.** Future.get(timeout) tự close Socket không?  
**Đáp án:** Không; cần cancellation/cleanup rõ ràng.

**8.** shutdown khác awaitTermination?  
**Đáp án:** Shutdown ngừng nhận tasks, await đợi pool chấm dứt.

**9.** shutdownNow có guarantee task dừng không?  
**Đáp án:** Không; best effort.

**10.** Vì sao flush và shutdownOutput trước khi đọc PONG?  
**Đáp án:** Server biết client đã gửi hết request, nhưng chiều response còn mở.

**11.** Đóng BufferedWriter từ socket quá sớm có thể gây gì?  
**Đáp án:** Đóng toàn socket, làm mất response.

**12.** accepted=closed=12 và active=0 chứng minh tuyệt đối JVM không leak?  
**Đáp án:** Không; chỉ phần resources được fixture theo dõi.

**13.** Vì sao không dùng Thread.activeCount để assert leak?  
**Đáp án:** Các threads nền JVM không thuộc fixture thay đổi độc lập.

**14.** Broken pipe là Java exception class cố định không?  
**Đáp án:** Không, thường là OS message.

**15.** Retry POST sau reset có nguy cơ gì?  
**Đáp án:** Server có thể đã xử lý request, retry gây duplicate side effects.

**16.** SelectionKey.cancel có tự đóng channel?  
**Đáp án:** Không.

**17.** Với executor chưa terminated sau deadline, test nên làm gì?  
**Đáp án:** Fail test, cleanup fallback và xác minh worker thực tế.

**18.** EOF giữa message có đồng nghĩa TCP reset?  
**Đáp án:** Không; có thể TCP FIN graceful nhưng application frame incomplete.

## 21. Tài liệu chính thức Java SE 17

- [ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): accept, setSoTimeout, close.
- [Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): input/output streams, shutdownOutput, close.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): readFully và EOFException.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): readNBytes.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow, awaitTermination.
- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): get(timeout) và cancel.
- [ThreadFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadFactory.html): worker identity.
- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): NIO lifecycle.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): select/wakeup/close.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): async completion/close.
