# Kiểm thử nhiều kết nối đồng thời và dọn tài nguyên khi xử lý thất bại

## 1. Tại sao TCP server phải được kiểm thử cả đồng thời lẫn thất bại?

Một TCP server có thể nhận nhiều kết nối tại cùng thời điểm. **ServerSocket.accept()** trả về một **Socket mới** cho mỗi kết nối, trong khi ServerSocket tiếp tục có vai trò lắng nghe. Sau đó server phân công socket cho worker để đọc request, xử lý, ghi response và đóng kết nối.

Ví dụ khi tám client tới gần nhau:

~~~text
                     ServerSocket (lắng nghe)
                                |
                           accept()
                                |
        +-----------------------+----------------------+
        |                       |                      |
    Socket A                 Socket B               Socket C  ...
        |                       |                      |
     Worker A                Worker B                Worker C
    thành công              ném exception           thành công
        |                       |                      |
    đóng Socket A          đóng Socket B           đóng Socket C
                                |
                       server vẫn phục vụ A, C
~~~

Hai tiêu chí quan trọng:

- **Tính đúng đắn khi đồng thời:** request/response không bị lẫn, nhiều handler thật sự xử lý chồng lấn, server có giới hạn tài nguyên, một request bị chậm hoặc lỗi không làm đình trệ mọi request khác.
- **Tính đúng đắn khi lỗi:** ngay cả khi IOException, RuntimeException, read timeout, client ngắt kết nối, executor từ chối task hoặc server shutdown, socket và executor vẫn có người chịu trách nhiệm đóng; không bỏ sót thread, task hoặc tài nguyên.

Chạy tám request **nối tiếp** rồi thấy đủ tám response không chứng minh server phục vụ đồng thời. Chạy tám client **cùng khởi động** cũng chưa đủ: có thể server vẫn xử lý chúng lần lượt. Test cần một điểm đồng bộ để chứng minh **ít nhất hai handler cùng ở vùng xử lý**.

## 2. Lập hợp đồng tài nguyên và các bất biến cần kiểm tra

Tài nguyên phải có **chủ sở hữu rõ ràng**:

| Tài nguyên | Ai sở hữu? | Khi nào phải giải phóng? |
| --- | --- | --- |
| **ServerSocket** | Thành phần quản lý server | Khi server ngừng tiếp nhận kết nối |
| **Socket do accept trả về** | Worker sau khi submit thành công | Khi request thành công **hoặc** thất bại |
| **Accepted Socket chưa giao được cho worker** | Accept loop | Ngay khi executor từ chối task |
| **Stream đọc/ghi** | Handler thông qua Socket | Kết thúc phiên; đóng Socket cũng đóng stream tương ứng |
| **ThreadPoolExecutor** | Server | Shutdown, chờ chấm dứt, xử lý các task còn kẹt |
| **Thread của accept loop** | Server | Sau khi listener đóng và thread kết thúc |
| **Socket phía client** | Tác vụ client/test | try-with-resources kể cả khi test thất bại |
| **ExecutorService chạy client test** | Test harness | finally: shutdown và awaitTermination |

Một số **bất biến** (invariants) cần theo dõi:

- **accepted:** tổng Socket được accept.
- **active:** số handler đang chạy, cuối test phải trở về **0**.
- **peakActive:** số handler đồng thời lớn nhất; nếu muốn chứng minh concurrency thì phải **≥ 2**.
- **successful / failed:** số xử lý thành công/thất bại có kiểm soát. Cần định nghĩa mỗi handler được ghi nhận **đúng một lần**.
- **closed:** số Socket phía server đã được đóng theo trạng thái API.
- **finished:** số handler đã tới cuối vòng đời; phải khớp kịch bản đã nhận quyền sở hữu.
- **terminated:** worker pool và các thread điều phối kết thúc sau shutdown.

**accepted không tự bằng successful**: kết nối có thể lỗi khi chưa gửi request, bị overload hoặc đang nằm trong queue. **Socket.isClosed()** chỉ xác nhận object Socket phía JVM được đóng; nó không tự chứng minh peer đã nhận/commit response hoặc mọi TCP state của kernel đã biến mất.

### Chuyển quyền sở hữu sau accept

Code dễ sai:

~~~java
// SAI: vòng lặp accept đóng socket ngay khi ra khỏi block,
// dù worker có thể còn đang xử lý nó.
try (Socket peer = listener.accept()) {
    pool.execute(() -> handle(peer));
}
~~~

Code đúng về quyền sở hữu:

~~~java
// Minh họa; các biến listener, pool và phương thức handle đã được khai báo.
Socket peer = listener.accept();
try {
    pool.execute(() -> handle(peer)); // Worker nhận ownership.
} catch (RejectedExecutionException ex) {
    peer.close(); // Submit thất bại: accept loop vẫn sở hữu socket.
    throw ex;
}
~~~

Và handler sở hữu socket:

~~~java
// Minh họa phương thức; Java 17 cho phép dùng biến effectively final.
static void handle(Socket peer) throws IOException {
    try (peer) {
        // Đọc, xử lý, phản hồi.
    } // Java đóng Socket khi thành công hoặc ném exception.
}
~~~

Trong hệ thống thật, hãy log lỗi đóng socket, lưu trạng thái request và xử lý suppressed exception khi cần. Không nên tăng bộ đếm **closed** ngay khi accept, vì lúc đó tài nguyên chưa hề được đóng.

## 3. Kiến trúc đồng thời phổ biến ở Java 17

~~~text
acceptor thread
    |
ServerSocket.accept()
    |
    +-- Socket 1 ----\
    +-- Socket 2 -----+--> ThreadPoolExecutor
    +-- Socket 3 ----/       |             |
    +-- Socket N          workers     bounded queue
                            |
                         handler
                            |
                    try-with-resources
                            |
                       close socket
~~~

Với pool cố định bốn worker, tối đa **bốn handler** làm việc đồng thời. Các task khác có thể nằm trong hàng đợi chờ. Queue có giới hạn giúp tránh tích tụ vô hạn. Nếu worker và queue đều hết chỗ, **execute() có thể ném RejectedExecutionException**.

Các API có ý nghĩa:

- **ServerSocket(0, backlog, loopback):** dùng cổng do hệ điều hành chọn; test lấy cổng thật bằng **getLocalPort()**, tránh tranh cổng cố định trên CI.
- **ExecutorService / ThreadPoolExecutor:** thực hiện các handler có kiểm soát và quản lý vòng đời.
- **CountDownLatch:** làm nhiều client cùng khởi động, hoặc giữ các handler ở một điểm đồng bộ để chứng minh overlap.
- **Future.get(timeout):** chờ từng client hoàn tất và phát hiện task bị kẹt.
- **AtomicInteger:** đếm active, peakActive, successful, failed, closed an toàn giữa nhiều worker.
- **Socket.setSoTimeout(n):** giới hạn thời gian chặn của thao tác đọc; **không phải deadline tổng của request**.
- **try-with-resources:** bảo đảm gọi close() trên socket dù code ném IOException hay RuntimeException.

### Vì sao chỉ dùng Thread.sleep() là test kém?

~~~java
// Sai về mặt kiểm thử: sleep không chứng minh handler chạy chồng lấn.
startClients();
Thread.sleep(100);
check(serverIsConcurrent());
~~~

Trên CI chậm, 100 ms có thể quá ngắn; trên máy mạnh, kết quả có thể tình cờ đúng. Thay bằng **barrier/latch và timeout rõ ràng**:

~~~java
// Trong handler:
twoActive.countDown();
letHandlersRun.await();

// Trong thread test:
require(twoActive.await(10, TimeUnit.SECONDS),
        "fewer than 2 handlers started");
letHandlersRun.countDown();
~~~

Khi hai handler đều đã giảm latch, nhưng chưa được release, test **biết rằng hai handler tồn tại đồng thời trong vùng xử lý**. Latch phải được mở cả trong **finally** để tránh deadlock nếu assertion trước đó fail.

## 4. Chương trình tích hợp Java 17+ chạy được

Chương trình này là một **integration test tự chạy**, không cần JUnit, Maven, dịch vụ ngoài hay Internet:

1. Server bind loopback TCP trên cổng tạm được hệ điều hành cấp.
2. Tám client task chờ một latch rồi bắt đầu gần như cùng lúc.
3. Server dùng **4 worker**, bounded queue chứa tối đa tám task, đợi ít nhất hai handler đi vào vùng xử lý rồi release.
4. Sáu client gửi các request **C2** đến **C7**, nhận đúng phản hồi **ACK:C2** đến **ACK:C7**.
5. Hai client gửi **FAIL_IO** và **FAIL_RUNTIME**. Worker gửi **ERROR** rồi cố ý ném **IOException** hoặc **IllegalStateException**; try-with-resources vẫn đóng socket.
6. Test xác nhận 8 accept, ≥2 handler chồng lấn, 6 xử lý thành công, 2 lỗi được ghi nhận, 8 accepted socket đóng, active=0.
7. Test shutdown client executor, server listener, acceptor thread và worker pool, rồi kiểm tra trạng thái kết thúc.

Giao thức demo chỉ là **một dòng UTF-8 cho mỗi request/response**. Dữ liệu test là hữu hạn và cố định. Nếu dùng giao thức dòng cho traffic không tin cậy, server thật cần **giới hạn độ dài dòng**, xác thực, TLS và kiểm soát tài nguyên bổ sung.

### Tệp TcpConcurrentCleanupDemo.java

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class TcpConcurrentCleanupDemo {
    private static final int CLIENTS = 8;
    private static final int WORKERS = 4;

    static final class Server implements AutoCloseable {
        final ServerSocket listener;
        final Thread acceptor;
        final ThreadPoolExecutor pool = new ThreadPoolExecutor(
                WORKERS, WORKERS, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(CLIENTS),
                new ThreadPoolExecutor.AbortPolicy());

        final CountDownLatch twoActive = new CountDownLatch(2);
        final CountDownLatch letHandlersRun = new CountDownLatch(1);
        final CountDownLatch handled = new CountDownLatch(CLIENTS);

        final AtomicInteger accepted = new AtomicInteger();
        final AtomicInteger active = new AtomicInteger();
        final AtomicInteger peak = new AtomicInteger();
        final AtomicInteger ok = new AtomicInteger();
        final AtomicInteger failed = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();
        volatile Throwable acceptFailure;

        Server() throws IOException {
            listener = new ServerSocket(
                    0, 50, InetAddress.getLoopbackAddress());
            acceptor = new Thread(this::acceptLoop, "tcp-acceptor");
            acceptor.start();
        }

        void acceptLoop() {
            try {
                for (int i = 0; i < CLIENTS; i++) {
                    Socket peer = listener.accept();
                    accepted.incrementAndGet();
                    try {
                        pool.execute(() -> handle(peer));
                    } catch (RejectedExecutionException ex) {
                        try {
                            peer.close();
                        } catch (IOException ignored) {
                            // Đóng best effort trong nhánh đã có lỗi.
                        }
                        acceptFailure = ex;
                        handled.countDown();
                    }
                }
            } catch (IOException ex) {
                if (!listener.isClosed()) {
                    acceptFailure = ex;
                }
            }
        }

        void handle(Socket socket) {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            twoActive.countDown();

            try (socket) {
                socket.setSoTimeout(10000);
                if (!letHandlersRun.await(10, TimeUnit.SECONDS)) {
                    throw new IOException("start barrier timeout");
                }

                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                socket.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                socket.getOutputStream(),
                                StandardCharsets.UTF_8));

                String command = in.readLine();
                if (command == null) {
                    throw new EOFException("empty request");
                }

                if ("FAIL_IO".equals(command) ||
                        "FAIL_RUNTIME".equals(command)) {
                    out.write("ERROR");
                    out.newLine();
                    out.flush();

                    if ("FAIL_IO".equals(command)) {
                        throw new IOException("injected failure");
                    }
                    throw new IllegalStateException(
                            "injected runtime failure");
                }

                out.write("ACK:" + command);
                out.newLine();
                out.flush();
                ok.incrementAndGet();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                failed.incrementAndGet();
            } catch (IOException | RuntimeException ex) {
                failed.incrementAndGet();
            } finally {
                if (socket.isClosed()) {
                    closed.incrementAndGet();
                }
                active.decrementAndGet();
                handled.countDown();
            }
        }

        @Override
        public void close() throws Exception {
            letHandlersRun.countDown();
            listener.close();
            acceptor.join(5000);

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "worker pool did not terminate");
                }
            }
            if (acceptor.isAlive()) {
                throw new IllegalStateException("acceptor did not stop");
            }
        }
    }

    static String send(int port, String command) throws IOException {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port), 3000);
            s.setSoTimeout(10000);

            BufferedWriter out = new BufferedWriter(
                    new OutputStreamWriter(
                            s.getOutputStream(), StandardCharsets.UTF_8));
            BufferedReader in = new BufferedReader(
                    new InputStreamReader(
                            s.getInputStream(), StandardCharsets.UTF_8));

            out.write(command);
            out.newLine();
            out.flush();
            return in.readLine();
        }
    }

    static void require(boolean condition, String reason) {
        if (!condition) {
            throw new AssertionError(reason);
        }
    }

    public static void main(String[] args) throws Exception {
        Server server = new Server();
        ExecutorService clients = Executors.newFixedThreadPool(CLIENTS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> replies = new ArrayList<>();

        try {
            for (int i = 0; i < CLIENTS; i++) {
                final int number = i;
                replies.add(clients.submit(() -> {
                    start.await();
                    String command = number == 0 ? "FAIL_IO"
                            : number == 1 ? "FAIL_RUNTIME" : "C" + number;
                    return send(server.listener.getLocalPort(), command);
                }));
            }

            start.countDown();
            require(server.twoActive.await(10, TimeUnit.SECONDS),
                    "fewer than 2 handlers started");
            server.letHandlersRun.countDown();

            for (int i = 0; i < CLIENTS; i++) {
                String expected = i < 2 ? "ERROR" : "ACK:C" + i;
                String actual = replies.get(i).get(10, TimeUnit.SECONDS);
                require(Objects.equals(expected, actual),
                        "wrong response for client " + i);
            }

            require(server.handled.await(10, TimeUnit.SECONDS),
                    "some handlers did not finish");
            require(server.acceptFailure == null,
                    "accept or submit failed");
            require(server.accepted.get() == CLIENTS,
                    "wrong accept count");
            require(server.peak.get() >= 2,
                    "no overlapping handlers");
            require(server.ok.get() == 6, "wrong success count");
            require(server.failed.get() == 2, "wrong failure count");
            require(server.closed.get() == CLIENTS,
                    "accepted socket was not closed");
            require(server.active.get() == 0,
                    "handler remains active");
        } finally {
            start.countDown();
            server.letHandlersRun.countDown();
            clients.shutdownNow();
            try {
                require(clients.awaitTermination(5, TimeUnit.SECONDS),
                        "client pool did not terminate");
            } finally {
                server.close();
            }
        }

        require(server.pool.isTerminated(),
                "worker pool still running");
        require(server.listener.isClosed(), "listener still open");
        require(!server.acceptor.isAlive(),
                "accept thread still running");

        System.out.println("PASS: 8 connections accepted");
        System.out.println("PASS: at least 2 handlers overlapped");
        System.out.println("PASS: 6 successes, 2 injected failures");
        System.out.println("PASS: 8 accepted sockets closed, 0 active");
        System.out.println("PASS: client and worker pools terminated");
    }
}
~~~

### Biên dịch, chạy, kết quả mong đợi

Tạo đúng một file **TcpConcurrentCleanupDemo.java**. Cần **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 TcpConcurrentCleanupDemo.java
java TcpConcurrentCleanupDemo
~~~

**Stdout của lần chạy thành công** (logic được kiểm tra bằng Java runtime):

~~~text
PASS: 8 connections accepted
PASS: at least 2 handlers overlapped
PASS: 6 successes, 2 injected failures
PASS: 8 accepted sockets closed, 0 active
PASS: client and worker pools terminated
~~~

Các thứ tự **accept**, **bắt đầu xử lý** và **hoàn tất** của từng client là không xác định; chương trình không in thứ tự phụ thuộc scheduler. Nó in kết luận sau khi đã kiểm tra các **bất biến**, nên khi thành công stdout là xác định. Nếu một assert sai, một Future gặp lỗi, hoặc deadline hết, chương trình ném exception và **không in kết quả PASS giả**.

### Vì sao thử nghiệm này thực sự kiểm chứng concurrency?

Mỗi worker tăng **active** rồi giảm latch **twoActive** trước khi chờ **letHandlersRun**. Test chỉ mở latch xử lý sau khi đã quan sát đủ hai handler. Trong khoảng này hai handler cùng hiện diện và chưa rời vùng xử lý; do đó **peakActive ≥ 2** không chỉ dựa vào việc tám client cùng start.

Các Future được lưu **theo số client**; test so sánh **ACK:C2** với client C2, không so sánh với response xuất hiện đầu tiên. Đây là cách tránh phụ thuộc thứ tự network/CPU khi test nhiều kết nối.

### Vì sao hai request lỗi vẫn dọn socket?

Handler gọi **try (socket)**. Sau khi gửi ERROR và flush, nhánh FAIL_IO ném **IOException**; nhánh FAIL_RUNTIME ném **IllegalStateException**. Các catch ghi nhận failed, nhưng thao tác close xảy ra khi thoát try-with-resources **trước** khi finally đánh dấu closed và giảm active. Các worker khác tiếp tục phục vụ request thành công.

Trong sản phẩm, thay vì im lặng trong catch như fixture này, cần ghi log và metrics có request ID, đồng thời quyết định chính sách response/retry. Bộ đếm trong fixture chỉ dùng để chứng minh nhánh lỗi đã xảy ra mà không làm nhiễu stdout.

### Những giới hạn cố ý của fixture

Server chấp nhận **đúng tám kết nối** rồi kết thúc accept loop vì mục đích test, không phải thiết kế một server chạy liên tục. Queue của worker có giới hạn 8 task, nhưng kịch bản này **không cố làm đầy queue** để thử overload; cần test quá tải riêng. **Socket.isClosed()** là chứng cứ đóng socket cục bộ, không chứng minh trạng thái TIME_WAIT trong kernel đã kết thúc tức thì. Test dùng đầu vào ngắn cố định; code sản phẩm cần giới hạn kích thước thông điệp và xử lý protocol đầy đủ.

## 5. Xây dựng một ma trận test đầy đủ

Một integration test quan trọng chưa thay thế được toàn bộ các trường hợp lỗi thực tế. Những ca nên bổ sung:

| Ca kiểm thử | Cách tạo tình huống | Điều cần kiểm tra |
| --- | --- | --- |
| **Burst nhiều client hợp lệ** | N client đồng bộ khởi động | Response đúng theo ID, không lẫn dữ liệu, active về 0 |
| **Thực sự song song** | Hai hoặc nhiều handler chờ latch | peakActive ≥ 2 khi latch chưa mở |
| **IOException trong handler** | Inject exception sau khi nhận socket | Socket đóng, failed tăng đúng, client khác vẫn hoạt động |
| **RuntimeException** | Inject lỗi nghiệp vụ | Socket vẫn đóng, worker pool còn xử lý được request mới |
| **Client ngắt sớm** | Close hoặc shutdownOutput giữa message | Server xử lý EOF theo framing, không treo |
| **Client gửi chậm** | Gửi một phần rồi giữ socket mở | Read timeout/deadline, cleanup diễn ra |
| **Message vượt giới hạn** | Gửi length lớn hoặc dòng quá dài | Server từ chối/hủy an toàn, không cạn heap |
| **Task bị reject** | Giữ worker, làm đầy bounded queue, submit thêm | Socket chưa được worker sở hữu được đóng; rejection được ghi nhận |
| **Shutdown khi accept đang chờ** | Đóng listener khi không có client mới | Acceptor thoát, thread kết thúc |
| **Shutdown khi request đang chạy** | Dừng server trong lúc worker block | Chính sách drain/cancel, socket/worker được giải phóng |
| **Lặp 100 lượt start/stop** | Mỗi lượt tạo/đóng server trên port 0 | Không tăng không giới hạn thread, FD, handle |
| **Tải kéo dài** | Chạy N client qua nhiều đợt | Peak concurrency giới hạn, không tăng backlog vô hạn, latency ổn định trong mức mục tiêu |

Ở bài kiểm thử dùng JUnit 5, có thể đặt server fixture trong **@BeforeEach** và cleanup trong **@AfterEach** (hoặc try/finally của chính test), chia mỗi trường hợp thành một test có assertion riêng. Ví dụ một test chỉ xác minh lỗi được cô lập, một test xác minh shutdown có deadline, một test tạo áp lực lớn lên bounded queue.

**Không dùng một kiểu lỗi để mô phỏng mọi lỗi.** Client chủ động đóng socket khác với server parse exception; queue rejection khác với read timeout; shutdown khác với xử lý request thành công.

## 6. Kiểm soát trạng thái khi shutdown server

### Đóng listener chưa đủ

**ServerSocket.close()** chấm dứt lắng nghe và làm accept() đang chặn thoát theo hợp đồng, nhưng **không tự động đóng mọi Socket đã được accept trước đó**. Handler phải đóng socket do nó sở hữu; nếu shutdown khẩn cấp, server có thể cần theo dõi và đóng các active socket để đánh thức worker bị block.

Một shutdown có trật tự thường gồm:

1. Ngừng nhận kết nối mới: chuyển trạng thái server, đóng listener.
2. Chờ acceptor thread dừng bằng join với deadline.
3. Ngừng nhận task mới; quyết định xử lý task đang chờ theo chính sách.
4. Chờ worker đang xử lý hoàn tất trong deadline.
5. Khi hết deadline, yêu cầu cancel/interruption và **đóng các socket còn đang block** nếu cần.
6. Xác minh executor terminated, active 0 và không còn tài nguyên do server giữ.

### Shutdown executor với Java 17

**ExecutorService của Java 17 cần được dọn bằng shutdown/awaitTermination**, không sử dụng try-with-resources như thể nó là AutoCloseable trên mọi phiên bản JDK.

~~~java
// Minh họa, đặt bên trong vòng đời server.
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Pool did not terminate");
    }
}
~~~

**shutdownNow() không kill thread ngay lập tức.** Nó cố interrupt task đang chạy và trả danh sách task còn trong queue chưa bắt đầu; code đang block ở Socket I/O truyền thống có thể cần **socket timeout hoặc chủ động close socket** để thoát. Với mỗi queued task bị hủy, cũng phải xét **socket nào nó đang giữ** để tránh leak.

Trong fixture, các request đều hoàn tất bình thường/qua inject trước shutdown; đây là lý do test có thể xác nhận worker pool đã terminated. Tình huống shutdown khi worker thực sự đang block cần test riêng với active socket tracking.

### Timeout đọc khác timeout tổng request

**socket.setSoTimeout(10000)** giới hạn thời gian chờ của mỗi lệnh đọc blocking, không phải deadline tổng từ khi accept đến khi response hoàn thành. Một client có thể gửi mỗi vài giây một byte, khiến từng read không timeout nhưng request kéo dài vô hạn.

Khi phục vụ traffic không tin cậy, cần kết hợp:

- Giới hạn kích thước frame/line và tổng byte.
- Deadline tổng thời gian cho request.
- Read timeout; connect timeout ở phía client.
- Số active connection và bounded queue.
- Chính sách hủy/đóng khi quá tải hoặc shutdown.
- Observability để phát hiện những client luôn giữ slot mà không hoàn thành.

## 7. Đo rò rỉ tài nguyên và phân tích lỗi

**Trong JVM:** theo dõi active, accepted, closed, queued, failed, số thread và heap sau nhiều vòng chạy. Với thread stuck, dùng thread dump hoặc Java Flight Recorder khi phù hợp.

**Ở hệ điều hành:** theo dõi số file descriptor/handle, socket **ESTABLISHED**, **CLOSE_WAIT**, số thread và sự thay đổi qua nhiều đợt mở/đóng. Ví dụ:

~~~bash
# Linux: quan sát các trạng thái TCP.
ss -tan

# Linux/macOS: tài nguyên tiến trình (thay PID ví dụ bằng PID thật).
lsof -p 12345
~~~

~~~powershell
# Windows: các kết nối TCP.
Get-NetTCPConnection

# Windows: các Java process và số handle hiện tại.
Get-Process java | Select-Object Id, ProcessName, HandleCount
~~~

**TIME_WAIT không mặc nhiên là leak.** Đây có thể là trạng thái TCP bình thường sau đóng kết nối. Phân biệt socket object/FD còn bị ứng dụng giữ với trạng thái TCP mà kernel duy trì trong vòng đời giao thức. Nhiều kết nối ở **CLOSE_WAIT** kéo dài mới đặc biệt đáng kiểm tra: peer đã đóng chiều gửi nhưng ứng dụng cục bộ chưa hoàn tất đóng socket.

Đo **trước tải, trong tải và sau khi hết tải**, rồi so sánh nhiều chu kỳ. Một lần đo đơn lẻ có thể bị ảnh hưởng bởi GC, chính sách giữ thread, hệ điều hành và những tiến trình khác.

## 8. Những lỗi thiết kế/test thường gặp

**Lỗi 1: Chỉ gửi nhiều request nối tiếp.** Số request thành công lớn không chứng minh đồng thời. Cần khẳng định overlap và response đúng theo ID.

**Lỗi 2: Sleep vài mili-giây để “đảm bảo” thread chạy cùng lúc.** Lịch chạy không xác định, dễ gây flaky test. Dùng CountDownLatch, Future với timeout.

**Lỗi 3: Giao Socket cho worker rồi đóng ngay tại accept loop.** Worker có thể dùng Socket đã đóng. Sau khi submit thành công, quyền sở hữu thuộc worker.

**Lỗi 4: Quên đóng Socket khi execute() bị reject.** Connection đã accept sẽ không có worker xử lý, có nguy cơ giữ FD/handle. Bắt RejectedExecutionException và đóng tại bên còn sở hữu Socket.

**Lỗi 5: Bắt IOException nhưng bỏ qua RuntimeException.** Những lỗi xử lý ngoài dự đoán vẫn có thể xuất hiện. Đưa Socket vào try-with-resources và cập nhật trạng thái trong finally giúp cleanup nhất quán.

**Lỗi 6: Dùng thread pool không giới hạn queue cho server đối mặt tải lớn.** Một lượng request tăng đột biến có thể tích tụ bộ nhớ và tăng latency; chọn bounded queue và overload policy.

**Lỗi 7: Chỉ đóng ServerSocket khi shutdown.** Accepted sockets và worker pool có vòng đời riêng; đóng listener không giải phóng tự động các accepted socket.

**Lỗi 8: Gọi shutdownNow rồi tin rằng blocking I/O đã dừng.** Interrupt có thể không đủ; cần timeout/close socket và quan sát terminated.

**Lỗi 9: Không đặt timeout cho Future.get().** Nếu một handler mắc kẹt, cả test có thể treo vô hạn. Dùng timeout và finally luôn giải phóng latch/pool.

**Lỗi 10: Tăng closed trước khi gọi close.** Counter khi đó chỉ đếm ý định dọn, không kiểm chứng trạng thái sau cleanup.

**Lỗi 11: Coi Socket.isClosed() là bằng chứng peer nhận được response.** Cần response/acknowledgment tầng ứng dụng và kiểm soát retry nếu nghiệp vụ có tác dụng phụ.

**Lỗi 12: Test dùng cổng cố định.** Nhiều CI job có thể tranh cổng; nên bind port 0 và lấy giá trị cổng thực tế.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Tám client chạy gần như cùng lúc có đảm bảo tám handler cùng hoạt động không?  
**Trả lời:** Không. Số worker, queue và scheduling quyết định. Phải đo active/peakActive hoặc dùng latch để chứng minh overlap.

**Câu 2.** Handler ném IllegalStateException khi đang giữ Socket. Ai chịu trách nhiệm đóng?  
**Trả lời:** Worker đã nhận quyền sở hữu Socket, thường đóng bằng try-with-resources. Không trông chờ accept loop còn giữ Socket.

**Câu 3.** Server vừa accept một kết nối nhưng pool từ chối task. Hành động đầu tiên nào tránh leak?  
**Trả lời:** Bên đang giữ Socket phải đóng nó, sau đó ghi nhận rejection và áp dụng overload policy.

**Câu 4.** Đóng listener có kết thúc toàn bộ kết nối đang chạy không?  
**Trả lời:** Không. ServerSocket là listening socket, mỗi accepted Socket cần chủ sở hữu xử lý riêng.

**Câu 5.** Hai request lỗi FAIL_IO, FAIL_RUNTIME có buộc sáu request khác phải thất bại không?  
**Trả lời:** Không. Fixture chứng minh exception trong một handler được cô lập, socket của handler đó được đóng và các client khác vẫn nhận đúng ACK.

**Câu 6.** Vì sao TIME_WAIT xuất hiện sau test chưa đủ kết luận leak?  
**Trả lời:** TCP có thể giữ trạng thái TIME_WAIT hợp lệ sau khi socket Java được đóng. Cần kiểm tra FD/handle, CLOSE_WAIT, active và các vòng test.

**Câu 7.** setSoTimeout(10_000) có bảo đảm toàn request kết thúc sau mười giây không?  
**Trả lời:** Không. Nó giới hạn thao tác đọc blocking riêng lẻ, không giới hạn toàn request nếu dữ liệu vẫn đến từ từ.

**Câu 8.** Điều gì khiến test không bị kẹt nếu assertion thất bại khi hai handler đang đợi?  
**Trả lời:** finally đếm ngược latch để mở barrier, shutdown client executor và close server với các deadline phù hợp.

## Kết luận

Kiểm thử TCP server nhiều kết nối đòi hỏi **chứng minh handler thực sự chồng lấn**, đối chiếu response theo từng client và bảo đảm lỗi của một kết nối không ảnh hưởng kết nối độc lập. Kiểm thử cleanup đòi hỏi **quyền sở hữu Socket/ExecutorService rõ ràng**, đóng ở mọi nhánh thành công/lỗi/rejection/shutdown, cùng các bất biến có thể đo như **active = 0**, số socket đóng và trạng thái executor terminated.

Một bài test đáng tin dùng **latch thay cho sleep**, **cổng tạm thay cho cổng cố định**, **timeout thay cho chờ vô hạn**, **failure injection thay cho đoán lỗi mạng** và **finally để dọn tài nguyên kể cả khi chính test thất bại**.

### Tài liệu tham khảo

- [Java 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): accept(), bind(), close().
- [Java 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): socket I/O, close() và read timeout.
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown(), shutdownNow(), awaitTermination().
- [Java 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded pool, queue và RejectedExecutionException.
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ thực thi và kiểm chứng overlap.
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): kết quả từng client và deadline.
- [Java 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): bộ đếm thread-safe.
