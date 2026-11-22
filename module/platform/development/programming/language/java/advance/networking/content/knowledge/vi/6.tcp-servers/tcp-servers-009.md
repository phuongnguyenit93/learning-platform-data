# Ngừng accept, hoàn thành yêu cầu đang chạy và đóng máy chủ TCP có thứ tự

## 1. Vì sao tắt server không chỉ là gọi `close()`?

Một máy chủ Java dùng `ServerSocket` thường vận hành vòng lặp: chờ kết nối bằng `accept()`, trao socket vừa nhận cho một handler, đọc thông điệp, xử lý và trả phản hồi. Khi cần dừng dịch vụ (deploy, bảo trì, thu hồi tài nguyên, hết thời hạn chạy), một thao tác tắt vội có thể tạo ra tình huống:

- Server ngừng ngay khi client vừa gửi yêu cầu, khiến request đang xử lý dở dang.
- Client đợi mãi phản hồi, hoặc thấy kết nối bị đóng mà không biết server đã thực hiện nghiệp vụ chưa.
- Worker thread tiếp tục chạy vì `ServerSocket.close()` **không tự đóng** những socket đã được `accept()` trước đó.
- `accept()` bị chặn, executor chưa được kết thúc, hoặc luồng đọc của client handler chờ vô hạn nên JVM không thoát.
- Server vẫn nhận thêm kết nối trong lúc worker pool đã bị shutdown, dẫn đến từ chối task mới và khó quản lý socket.

**Graceful shutdown (dừng có thứ tự)** là quá trình đưa dịch vụ khỏi trạng thái nhận việc mới, **cho công việc đang thực hiện hoàn tất trong một khoảng thời gian giới hạn**, rồi đóng kết nối, executor và các tài nguyên phụ trợ. Nó **không đồng nghĩa** chờ vô hạn, và không thể bảo đảm mọi request hoàn thành trước một deadline cứng.

Mục tiêu của bài: biết **ngừng `accept` trước**, phân biệt **listener socket với accepted client socket**, tổ chức **drain các handler đang chạy**, thiết lập **timeout và phương án cưỡng bức**, viết mã Java 17 thực thi được, và tránh nhầm lẫn “server tắt” với “mọi client chắc chắn đã nhận phản hồi”.

## 2. Ba lớp vòng đời khác nhau

| Thành phần | API Java điển hình | Vai trò | Khi shutdown |
|---|---|---|---|
| **Listening socket** | `ServerSocket` và `accept()` | Lắng nghe trên IP:port, chấp nhận kết nối TCP mới | **Đóng listener** để không tiếp tục accept |
| **Accepted client socket** | `Socket` được `accept()` trả về | Kênh trao đổi byte với một client đã kết nối | Cho request đang chạy hoàn tất trong thời hạn, rồi đóng riêng từng socket |
| **Handler / thread pool** | `ExecutorService`, `Future`, task | Đọc frame, validate, xử lý nghiệp vụ, ghi response | Không nhận thêm task sau khi vòng accept dừng, đợi các task đang chạy, rồi xử lý timeout/force |

Hai câu lệnh sau có ngữ nghĩa hoàn toàn khác:

- `serverSocket.close()`: dừng listening socket; một thread đang block tại `ServerSocket.accept()` thường được đánh thức bằng `SocketException`. **Các socket đã accept vẫn tồn tại độc lập**.
- `clientSocket.close()`: đóng một kết nối client đã được chấp nhận. Nếu handler còn đang đọc/ghi, nó có thể gặp EOF, `SocketException` hoặc lỗi I/O và không hoàn tất request.

Vì vậy gọi `close()` trên listener **không tự làm sạch mọi thứ**, còn đóng tất cả client socket ngay lập tức có thể cắt ngang công việc muốn hoàn tất.

### Các trạng thái nên có trong thiết kế

```text
RUNNING
  | đang nhận kết nối và xử lý request
  v
QUIESCING / STOP_ACCEPTING
  | từ chối công việc mới, đóng listener, cho accept loop kết thúc
  v
DRAINING
  | chờ các handler đã được nhận hoàn tất trong deadline
  |                  \
  | mọi việc xong      \ quá hạn
  v                    v
TERMINATED          FORCED_STOP
  |                    | đóng socket còn tồn tại, yêu cầu hủy task
  +--------------------+
           |
     đóng tài nguyên cuối
```

**QUIESCING** là tạm ngừng nhận thêm việc; **DRAINING** là hoàn thành phần đang chạy. Trong giao thức giữ kết nối lâu dài (keep-alive), “không nhận thêm kết nối TCP” **chưa đủ**: trên những socket đã tồn tại, server cũng cần quy định không bắt đầu request mới sau khi vào trạng thái draining, nhưng vẫn cho request đang xử lý kết thúc.

## 3. Thứ tự shutdown đúng và lý do

Một chuỗi hành động có thể kiểm soát được:

1. **Đánh dấu đang dừng**: đặt trạng thái `accepting=false` (hoặc chuyển trạng thái qua `AtomicBoolean`/state machine), ngăn logic tiếp tục đăng ký công việc mới. Trên hệ thống thực, đồng thời cập nhật readiness hoặc cơ chế rút lưu lượng khỏi load balancer.
2. **Đóng `ServerSocket`**: giải phóng listener để thread đang chặn ở `accept()` thức dậy. Nếu bị `SocketException` **vì ta chủ động đóng**, đây là kết quả shutdown dự kiến, không nên log như một lỗi không kiểm soát.
3. **Đợi vòng `accept` kết thúc**: dùng `Future.get()`/`join()` phù hợp. Bước này bảo đảm không còn đường code tiếp tục gửi kết nối mới cho worker pool trước khi ta khóa pool.
4. **Ngừng nhận handler mới bằng `ExecutorService.shutdown()`**: những task đã submit tiếp tục chạy; task mới sẽ bị từ chối. **Không dùng `shutdownNow()` ngay** nếu mục tiêu là hoàn tất yêu cầu đang chạy.
5. **Drain có deadline** bằng `awaitTermination(timeout, unit)` hoặc cơ chế đợi các in-flight request. Bảo đảm handler biết khi nào phải hoàn thành, phản hồi, đóng socket và giải phóng DB/lock.
6. **Nếu quá hạn**, hủy theo chính sách: đóng những accepted sockets còn hoạt động để giải phóng I/O đang block, dùng `shutdownNow()` để yêu cầu interrupt, đợi thêm một khoảng ngắn rồi báo rõ phần còn sót. Đây là *forced shutdown*, không được trình bày như đã drain hoàn tất.
7. **Giải phóng phần cuối**: đóng các tài nguyên độc lập (selector nếu dùng NIO, thread executor, connection pool/DB khi handler không còn sử dụng, metrics/logging sau cùng), báo trạng thái cuối và kết thúc tiến trình.

### Vì sao không `shutdown()` pool trước khi dừng accept?

Có một race:

```text
Thread A (shutdown): workers.shutdown()
Thread B (accept):   socket = listener.accept()
Thread B:            workers.execute(handle(socket))
                   -> RejectedExecutionException
```

Server vừa accept một client nhưng không thể chạy handler. Nếu không đóng socket đó, tài nguyên sẽ rò rỉ; nếu client đang chờ kết quả, nó có thể timeout. Thiết kế cần **dừng/đợi accept loop trước**, sau đó shutdown worker pool; và **dù vậy vẫn phải xử lý `RejectedExecutionException`** cho nhánh từ chối do giới hạn tài nguyên hoặc race.

### Race giữa cờ dừng và `accept()`

Một socket có thể được trả về từ `accept()` ngay khi thread khác bắt đầu shutdown. Do đó không chỉ kiểm tra `accepting` trước lời gọi: **kiểm tra lại sau khi `accept()` trả về**, nếu đã shutdown thì đóng socket vừa nhận thay vì submit handler mới. Cách làm này thu hẹp cửa sổ nhận việc sau khi đã quyết định dừng.

Không có cách nào biến toàn bộ TCP/network, queue và code ứng dụng thành một thao tác nguyên tử chỉ bằng một boolean. Tầng load balancer, reverse proxy và ứng dụng cần phối hợp cùng chính sách dừng nhận việc mới.

## 4. API Java cho graceful shutdown

| API | Tác động chính | Lưu ý |
|---|---|---|
| `AtomicBoolean.compareAndSet` hoặc `set` | Công bố cờ trạng thái shutdown cho các thread | Cần đồng bộ với thứ tự accept/submit; không tự ngắt blocking I/O |
| `ServerSocket.close()` | Đóng listener, khiến blocking `accept()` báo lỗi khi socket bị đóng | Chỉ ảnh hưởng listening socket, không đóng hết accepted sockets |
| `Future.get(timeout, unit)` | Đợi nhiệm vụ điều phối accept hoàn tất hoặc báo exception/timeout | Nếu task lỗi ngoài dự kiến, `ExecutionException` cho phép phát hiện |
| `ExecutorService.shutdown()` | Không nhận task mới; task đã submit được phép chạy | Không tự hủy công việc đang chạy |
| `ExecutorService.awaitTermination(...)` | Chờ các task hoàn tất sau khi đã shutdown | Trả `false` khi hết hạn; không tự force stop |
| `ExecutorService.shutdownNow()` | Cố gắng dừng công việc bằng ngắt thread; trả về task chưa bắt đầu | **Không bảo đảm** một handler đang block trên I/O sẽ dừng ngay |
| `Socket.close()` | Đóng accepted connection và giải phóng tài nguyên | Có thể làm `read/write` đang block ném exception |
| `Socket.setSoTimeout(...)` | Giới hạn thời gian chờ một số thao tác đọc socket | Không giới hạn tổng thời gian handler hoặc `accept()` |
| `CountDownLatch` | Đồng bộ hóa điểm bắt đầu/kết thúc trong ví dụ/test | Không phải thành phần bắt buộc của server production |

**Phân biệt `shutdown` với `shutdownNow`:** tên `shutdownNow` dễ gây hiểu nhầm; API đưa ra *best-effort interruption*, không phải biện pháp “kill thread” đáng tin cậy. Với classic blocking socket I/O, **đóng socket** thường cần thiết để giải phóng các handler đang chờ dữ liệu từ client. Với handler đang chạy logic CPU hoặc gọi thư viện ngoài, phải có thiết kế cancellation/deadline riêng.

**Thứ tự đóng DB pool:** không đóng pool dữ liệu trong khi handler còn commit/rollback giao dịch. Nếu bắt buộc force, phải có chính sách nhất quán cho transaction và recovery; graceful TCP shutdown tự nó không bảo đảm dữ liệu đã lưu bền vững.

## 5. Java 17+: chương trình chạy được, dừng accept nhưng hoàn tất request đang chạy

Ví dụ chạy trên **loopback**, không cần DNS, Internet, framework hay thư viện ngoài. Có hai executor: một executor cho vòng `accept()` và một pool cho các handler. Một client gửi `WORK`; handler xác nhận rằng đã bắt đầu xử lý nhưng chờ một latch để mô phỏng công việc chưa hoàn tất. Main thread chủ động **ngừng accept trước**, rồi cho handler chạy nốt và đợi pool drain. Nhờ `CountDownLatch`, ví dụ không dựa vào `Thread.sleep` hay “đợi may rủi”.

Tạo file **`GracefulTcpStopDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketException;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class GracefulTcpStopDemo {
    static final class TcpService implements AutoCloseable {
        private final ServerSocket listener;
        private final ExecutorService acceptExecutor =
                Executors.newSingleThreadExecutor();
        private final ExecutorService workers =
                Executors.newFixedThreadPool(2);
        private final Set<Socket> activeSockets =
                ConcurrentHashMap.newKeySet();
        private final AtomicBoolean accepting =
                new AtomicBoolean(true);
        private final AtomicReference<Throwable> handlerFailure =
                new AtomicReference<>();
        private Future<?> acceptFuture;

        final CountDownLatch jobStarted = new CountDownLatch(1);
        final CountDownLatch releaseJob = new CountDownLatch(1);

        TcpService() throws IOException {
            listener = new ServerSocket(
                    0, 8, InetAddress.getLoopbackAddress());
        }

        int port() {
            return listener.getLocalPort();
        }

        void start() {
            acceptFuture = acceptExecutor.submit(() -> {
                try {
                    while (accepting.get()) {
                        Socket socket = listener.accept();
                        if (!accepting.get()) {
                            socket.close();
                            break;
                        }
                        activeSockets.add(socket);
                        try {
                            workers.execute(() -> handle(socket));
                        } catch (RejectedExecutionException rejected) {
                            activeSockets.remove(socket);
                            try {
                                socket.close();
                            } catch (IOException ignored) {
                                // Best effort cleanup.
                            }
                            if (accepting.get()) {
                                throw rejected;
                            }
                        }
                    }
                } catch (SocketException error) {
                    // Đóng listener khi shutdown sẽ đánh thức accept().
                    if (accepting.get()) {
                        throw new UncheckedIOException(error);
                    }
                } catch (IOException error) {
                    throw new UncheckedIOException(error);
                }
            });
        }

        private void handle(Socket socket) {
            try (socket) {
                socket.setSoTimeout(5_000);
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                socket.getInputStream(),
                                StandardCharsets.UTF_8));
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                socket.getOutputStream(),
                                StandardCharsets.UTF_8));

                String request = in.readLine();
                if (!"WORK".equals(request)) {
                    throw new IllegalArgumentException("Bad request");
                }

                jobStarted.countDown();
                if (!releaseJob.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Work deadline");
                }

                out.write("OK COMPLETED\n");
                out.flush();
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                handlerFailure.compareAndSet(null, error);
            } catch (Exception error) {
                handlerFailure.compareAndSet(null, error);
            } finally {
                activeSockets.remove(socket);
            }
        }

        void stopAccepting()
                throws IOException, InterruptedException,
                       ExecutionException, TimeoutException {
            accepting.set(false);
            listener.close();
            // Đợi accept loop rời khỏi listener trước khi khóa pool.
            acceptFuture.get(5, TimeUnit.SECONDS);
            acceptExecutor.shutdown();
            workers.shutdown();
        }

        boolean awaitDrain(long timeoutMillis)
                throws InterruptedException {
            if (workers.awaitTermination(
                    timeoutMillis, TimeUnit.MILLISECONDS)) {
                return true;
            }

            // Quá deadline: đây là forced shutdown, không còn graceful.
            for (Socket socket : activeSockets) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // Best effort cleanup.
                }
            }
            workers.shutdownNow();
            return false;
        }

        void checkHandler() {
            Throwable error = handlerFailure.get();
            if (error != null) {
                throw new IllegalStateException("Handler failed", error);
            }
        }

        @Override
        public void close() {
            accepting.set(false);
            releaseJob.countDown();
            try {
                listener.close();
            } catch (IOException ignored) {
                // Closing twice is harmless.
            }
            for (Socket socket : activeSockets) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                    // Best effort cleanup.
                }
            }
            acceptExecutor.shutdownNow();
            workers.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        try (TcpService server = new TcpService()) {
            server.start();

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.port())) {
                client.setSoTimeout(5_000);
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(
                                client.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(
                                client.getInputStream(),
                                StandardCharsets.UTF_8));

                out.write("WORK\n");
                out.flush();

                if (!server.jobStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Job did not start");
                }
                System.out.println("Request is in flight");

                server.stopAccepting();
                System.out.println("Accept loop stopped");

                // Cho yêu cầu đã nhận hoàn tất SAU khi ngừng accept.
                server.releaseJob.countDown();
                boolean drained = server.awaitDrain(5_000);
                if (!drained) {
                    throw new IllegalStateException(
                            "Drain deadline exceeded");
                }
                server.checkHandler();
                System.out.println("Existing request completed");

                System.out.println(
                        "Client response: " + in.readLine());
            }
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**, trong thư mục chứa file:

```bash
javac -encoding UTF-8 GracefulTcpStopDemo.java
java GracefulTcpStopDemo
```

Đầu ra trên hệ thống cho phép dùng TCP loopback:

```text
Request is in flight
Accept loop stopped
Existing request completed
Client response: OK COMPLETED
```

### Tại sao ví dụ chứng minh đúng thứ tự?

1. `new ServerSocket(0, ..., loopback)` mở một listener trên cổng tạm; client dùng đúng cổng đó. `ExecutorService` riêng chạy vòng `accept()`.
2. Sau khi `accept()` tạo socket client, `workers.execute(...)` giao nó cho handler. Handler đọc dòng `WORK`, đếm xuống `jobStarted`, rồi **chưa trả response** vì còn đợi `releaseJob`.
3. Main chỉ chuyển sang shutdown sau khi `jobStarted.await(...)` thành công: tức một yêu cầu thực sự **đang ở trong handler**. Dòng “Request is in flight” vì thế không phụ thuộc vào một `sleep` ngẫu nhiên.
4. `stopAccepting()` đặt `accepting=false`, **đóng listener**, đợi `acceptFuture.get(...)` kết thúc, sau đó mới gọi `workers.shutdown()`. `ServerSocket.accept()` bị đánh thức do đóng listener; `SocketException` do việc đóng chủ động được nhận diện là dự kiến.
5. Client socket **đã được accept không bị đóng** ở bước trên. Khi main gọi `releaseJob.countDown()`, handler mới ghi `OK COMPLETED\n`, flush và đóng socket.
6. `awaitDrain(...)` đợi các handler đã nhận chạy xong. Nếu quá deadline, nó đóng socket còn hoạt động và gọi `shutdownNow()`, trả `false` để caller phân biệt **forced** với **graceful**. Đường chạy bình thường trả `true`.
7. Main kiểm tra không có lỗi handler, rồi client đọc `OK COMPLETED`. `try-with-resources` cuối cùng đóng cả client socket và wrapper service, với cleanup lặp lại an toàn.

**Độ chắc chắn của output:** các latch bảo đảm thứ tự *handler bắt đầu → accept dừng → handler hoàn thành*. Test không phải là mô phỏng nhiều client hoặc đo lường một service thực đang chịu tải. Tùy cấu hình bảo mật và mạng, socket loopback vẫn có thể bị cấm; khi đó chương trình báo lỗi môi trường thay vì cố giả lập một kết quả không xảy ra.

### Những gì ví dụ cố ý không làm

- Không nhận yêu cầu mới trên cùng một kết nối lâu dài: handler chỉ đọc **một** frame trên mỗi socket.
- Không nhận hoặc theo dõi hàng nghìn client, không có backpressure/bounded task queue mạnh; `newFixedThreadPool` có thể dùng queue nội bộ không giới hạn, **không phải** kiến trúc tối ưu cho traffic không tin cậy.
- Không xử lý TLS, authentication, database, transaction, metrics, readiness hay hệ điều phối.
- Không bảo đảm client đã đọc response ngay khi worker đã flush; thông báo đó được xác nhận riêng khi client thực sự gọi `readLine()`.
- Không cam kết handler đã gửi thành công mọi byte khi bị forced stop. Đường force được báo rõ và có thể mất request đang xử lý.

## 6. Điều kiện để drain thực sự hoàn tất

Trước khi chờ task, cần xác định **đơn vị công việc**: một socket, một request hay một transaction? Đây không phải lúc nào cũng là một.

### Một kết nối chứa nhiều request

Nếu server cho phép nhiều request trên một TCP connection (giao thức kiểu keep-alive hoặc request pipeline), dừng nhận **kết nối mới** không đồng nghĩa dừng nhận **request mới trên socket cũ**. Có thể áp dụng chính sách:

- Từ lúc **QUIESCING**, không bắt đầu request mới, kể cả qua socket đã mở; hoặc áp dụng ranh giới giao thức như thông báo `GOAWAY` (nếu giao thức hỗ trợ).
- Cho request **đã được nhận và đánh dấu đang xử lý** hoàn tất với deadline.
- Gửi thông báo đóng/phản hồi cuối theo hợp đồng giao thức rồi đóng kết nối khi thích hợp.
- Với client kết nối nhưng **chưa gửi đủ frame**, cần giới hạn thời gian chờ và kích thước frame; không cho một kết nối rảnh hoặc gửi chậm giữ tiến trình mãi.

Nếu chương trình có 10 client đang mở nhưng chỉ 3 request đã vào logic nghiệp vụ, “drain connection” khác với “drain in-flight request”. Với API quan trọng, in-flight counter và protocol state sẽ biểu diễn chính xác tiến độ hơn chỉ đếm socket.

### Công việc bất đồng bộ và queue

Nếu handler ném việc xuống executor khác, message queue hoặc database async call, handler kết thúc **không tự chứng minh** việc downstream đã hoàn tất. Cần định nghĩa rõ mốc “hoàn thành” (đã nhận, đã enqueue, đã commit hay đã ghi nhận tại hệ thống khác), rồi đợi hoặc chuyển giao trách nhiệm phù hợp.

**Không được đóng DB connection pool quá sớm** khi các handler còn đang commit. Theo chiều ngược lại, cũng không thể đợi vô hạn nếu một transaction hoặc external API bị treo; cần timeout/cancellation ở từng tầng.

## 7. Drain timeout, forced shutdown và tính đúng đắn nghiệp vụ

Đặt thời gian chờ tổng thể theo **shutdown budget**, ví dụ 30 giây cho rút lưu lượng và xử lý, thêm khoảng nhỏ để cleanup. Những con số đó là **quyết định vận hành**, không phải mặc định Java. Một cấu hình sản xuất có thể dài hoặc ngắn hơn tùy SLA, đặc điểm request và thời gian cho phép của orchestrator.

| Tình huống | Phản ứng hợp lý |
|---|---|
| Mọi handler hoàn tất trước deadline | Ghi nhận graceful drain, đóng kết nối/pool liên quan và kết thúc |
| Một client chưa gửi đủ request | Áp dụng read timeout, giới hạn frame, có thể đóng kết nối đó theo policy |
| Một handler gọi service ngoài quá lâu | Kích hoạt timeout/cancellation riêng; không chỉ đợi `awaitTermination` |
| Quá hạn drain | Đóng active sockets, gọi `shutdownNow()`, ghi những task chưa kết thúc, chuyển sang trạng thái forced |
| Handler không phản ứng với interrupt | Không coi `shutdownNow()` là thành công; cần ngắt I/O bằng close/cancellation hoặc để hệ điều phối xử lý tiến trình |
| Tiến trình bị kill đột ngột hoặc mất điện | Không có bảo đảm graceful; transaction/recovery/idempotency phải chịu được gián đoạn |

**Đặc biệt:** Khi client không nhận được phản hồi trước lúc server dừng, trạng thái xử lý có thể **không xác định đối với client**. Server có thể đã cập nhật DB rồi mất kết nối trước khi response được đọc; client retry mù quáng có thể tạo kết quả trùng. Với lệnh có side effect, cần idempotency key, giao dịch bền vững và API tra cứu/đối soát theo yêu cầu nghiệp vụ.

### Đóng socket có nghĩa gì?

- `ServerSocket.close()` dừng listener, không đợi toàn bộ client handler hoàn tất.
- `Socket.close()` giải phóng endpoint phía server; nó có thể làm phía client thấy EOF/lỗi, **không phải thông báo nghiệp vụ rằng thao tác thất bại hay thành công**.
- `Socket.shutdownOutput()` half-close chiều gửi nếu giao thức cần thông báo không còn byte theo chiều đó, nhưng **FIN không thay thế một response/ACK ứng dụng**.
- Không dùng `SO_LINGER` một cách tùy tiện để “bảo đảm gửi xong”; cấu hình linger, RST và thời gian close có hành vi hệ điều hành riêng. Muốn client biết nghiệp vụ thành công phải có cơ chế xác nhận ở tầng ứng dụng.

## 8. Tích hợp vào vòng đời ứng dụng thật

### 8.1. Tín hiệu dừng và readiness

Một dịch vụ container thường nhận tín hiệu kết thúc hoặc sự kiện từ framework/orchestrator. Quá trình thường cần phối hợp:

1. Chuyển readiness sang **không nhận lưu lượng mới** để load balancer dừng đưa request vào.
2. Có một khoảng cho trạng thái readiness lan truyền qua hệ thống điều phối, đồng thời/tiếp theo dừng accept theo policy.
3. Stop accept và các entrypoint khác (HTTP listener, queue consumer, scheduled job).
4. Drain in-flight request trong thời gian cho phép.
5. Đóng DB/queue clients, executor, logging và phần còn lại theo phụ thuộc.
6. Thoát với mã trạng thái và telemetry thích hợp.

Chỉ đóng listener nội bộ khi proxy vẫn tiếp tục gửi traffic tới instance sẽ tạo lỗi kết nối cho client. Vì vậy lifecycle server **không tách rời** load balancing và cơ chế định tuyến.

### 8.2. JVM shutdown hook

Java hỗ trợ `Runtime.getRuntime().addShutdownHook(Thread)` để chạy mã cleanup khi JVM đi qua luồng shutdown bình thường. Tuy nhiên:

- Hook không bảo đảm chạy khi `SIGKILL`, mất điện hay process bị terminate cưỡng bức ở mức hệ điều hành.
- Shutdown hook có ngân sách thời gian hạn chế từ môi trường; không nên giả định có thể chờ vô hạn.
- Không tạo deadlock: hook không được chờ một thread mà bản thân thread ấy đang chờ hook hoặc tài nguyên hook đã khóa.
- Nên có **một lifecycle controller** và cách stop idempotent. Không để nhiều hook cùng đóng một resource một cách thiếu thứ tự.
- Bài demo chủ động gọi `stopAccepting()` trong `main` để chứng minh kết quả ổn định; không cần gửi signal hay phụ thuộc thời gian tắt JVM.

Trong ứng dụng Spring/Netty/Servlet container, ưu tiên cơ chế lifecycle/graceful shutdown được framework hỗ trợ thay vì tự can thiệp `ServerSocket` mà framework đang quản lý.

### 8.3. Backpressure và giới hạn tài nguyên

Không dùng `new Thread` vô hạn cho mỗi kết nối. Dùng pool/queue có kích thước được kiểm soát hoặc cơ chế async I/O phù hợp; khi quá tải cần chính sách từ chối rõ ràng và **đóng socket bị từ chối**. Trong shutdown, phải ngăn việc submit task sau khi `shutdown` đã bắt đầu. Các kết nối chờ `accept` trong backlog của hệ điều hành không đồng nghĩa đã được ứng dụng nhận làm in-flight work.

### 8.4. Logging, metrics và quan sát tiến độ

Các chỉ số hữu ích: trạng thái `RUNNING/QUIESCING/DRAINING/TERMINATED`, listener open/closed, active TCP connections, in-flight requests, queued requests, số task hoàn thành/đứt quãng, thời gian drain và tỷ lệ forced shutdown. Log lý do đóng socket nhưng tránh tiết lộ dữ liệu nhạy cảm trong payload.

## 9. Những lỗi thiết kế phổ biến

| Làm sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Gọi `ServerSocket.close()` rồi coi server đã kết thúc | Accepted sockets và handler vẫn hoạt động | Theo dõi active sockets/tasks, shutdown executor, drain |
| Gọi `workers.shutdownNow()` ngay khi có tín hiệu dừng | Cắt ngang request đang xử lý | Stop accept trước, `shutdown` pool, chờ trong deadline |
| `workers.shutdown()` trước khi accept loop rời đi | Socket mới có thể bị nhận nhưng submit bị reject | Ngừng và join accept loop rồi shutdown pool; bắt `RejectedExecutionException` |
| Chỉ set `running=false` khi thread đang block `accept()` | Vòng accept có thể không thức dậy | Đóng listener để đánh thức `accept()` |
| Không kiểm tra cờ sau khi `accept()` trả về | Nhận thêm việc ngay lúc shutdown | Kiểm tra trạng thái lần nữa; nếu đang dừng thì đóng socket vừa accept |
| Gọi mọi `SocketException` trong shutdown là lỗi hệ thống | Báo lỗi giả cho việc close listener chủ động | Phân biệt expected-close với lỗi accept bất thường |
| Không đặt deadline | Một client chậm hoặc handler treo giữ process vô hạn | Read timeout, cancellation và overall shutdown budget |
| Chỉ dùng `shutdownNow()` để dừng I/O | Blocking socket I/O có thể không phản ứng như mong muốn | Đóng active sockets khi buộc force, kiểm tra task còn sống |
| Đếm hết socket là đếm hết giao dịch | Không xét queue/async work/in-flight requests | Định nghĩa mốc hoàn thành ở tầng ứng dụng |
| Đóng DB pool trước khi handler hoàn tất | Handler lỗi giữa transaction | Drain worker/commit theo contract rồi mới đóng dependencies |
| Cho rằng `flush()` xong nghĩa client nhận response | Client vẫn có thể mất kết nối/timeout | Thiết kế ứng dụng xác nhận và idempotency nếu cần |
| Không rút instance khỏi load balancer | Proxy tiếp tục đưa traffic vào server đang dừng | Điều phối readiness và traffic drain |

## 10. Bài tập tự kiểm tra

**Câu 1.** Sau khi gọi `serverSocket.close()`, có còn socket từ `accept()` trước đó hoạt động không?

**Trả lời:** Có. Listening socket và accepted client sockets là các socket khác nhau. Phải quản lý vòng đời client socket riêng.

**Câu 2.** Vì sao cần đợi accept loop dừng trước khi `workers.shutdown()`?

**Trả lời:** Để tránh vòng accept tiếp tục submit task mới khi pool đã từ chối, gây `RejectedExecutionException` và có thể bỏ sót đóng socket vừa nhận.

**Câu 3.** `ExecutorService.shutdown()` có hủy các request đang chạy không?

**Trả lời:** Không. Nó không nhận thêm task, nhưng task đã được submit được tiếp tục chạy. `awaitTermination` cho phép đợi chúng sau shutdown.

**Câu 4.** `awaitTermination(5, SECONDS)` trả `false` có nghĩa là server đã tắt chưa?

**Trả lời:** Chưa chắc. Nó chỉ cho biết các task chưa hoàn tất trong hạn; cần chính sách forced stop/đóng socket và báo rõ task còn lại.

**Câu 5.** Tại sao phải đóng accepted sockets trong nhánh forced stop dù đã gọi `shutdownNow()`?

**Trả lời:** Interrupt không bảo đảm giải phóng mọi classic blocking socket read/write. Đóng socket có thể đánh thức I/O đang chờ, cho phép handler thoát.

**Câu 6.** Nếu server còn keep-alive connections nhưng không accept socket mới, có thể coi là không nhận request mới không?

**Trả lời:** Không. Các socket đã có vẫn có thể nhận request mới nếu handler còn đọc thêm. Cần áp dụng quy tắc không nhận request mới trên các kết nối đó, hoặc gửi thông báo drain theo giao thức.

**Câu 7.** Một lệnh đã commit DB nhưng client mất response khi server shutdown. Có thể retry ngay mà không có idempotency không?

**Trả lời:** Không nên. Trạng thái client có thể là unknown; lệnh có side effect cần nhận diện request, idempotency và khả năng tra cứu/đối soát.

**Câu 8.** Trong ví dụ, vì sao kết quả chạy được xác định rõ mà không dùng `Thread.sleep`?

**Trả lời:** `jobStarted` bảo đảm handler đã thực sự vào công việc, `releaseJob` ngăn hoàn tất trước khi stop accept, và `Future.get`/`awaitTermination` xác nhận điều phối accept/worker đã kết thúc.

## 11. Ghi nhớ

**Dừng TCP server đúng thứ tự = ngừng nhận việc mới → ngắt blocking accept → xác nhận accept loop đã dừng → không submit thêm handler → đợi request đang chạy hoàn tất trong deadline → xử lý phần còn lại bằng forced stop nếu cần → đóng tài nguyên.**

`ServerSocket.close()` **không** tự đóng các `Socket` client đã accept. `ExecutorService.shutdown()` **khác** `shutdownNow()`. `Socket.close()` và TCP FIN **không** chứng minh một lệnh nghiệp vụ đã thành công hoặc client đã đọc được response. Với giao thức nhiều request trên một kết nối, phải phân biệt rõ **ngừng accept kết nối** và **ngừng nhận request mới**. Trong vận hành thật, phối hợp lifecycle của ứng dụng, timeouts, readiness, idempotency và lưu trữ để việc deploy/tắt server vừa an toàn vừa có thể quan sát.

Tài liệu tham khảo: Java SE 17 API `java.net.ServerSocket`, `java.net.Socket`, `java.util.concurrent.ExecutorService`, `java.util.concurrent.Future`; RFC 9293 (*Transmission Control Protocol*).