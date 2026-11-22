# Máy chủ TCP Java: luồng cho mỗi kết nối, nhóm luồng và luồng ảo

## 1. Mục tiêu

Một máy chủ TCP thường lặp lại hai thao tác: **chờ kết nối mới** qua `ServerSocket.accept()`, rồi **trao đổi dữ liệu** với từng `Socket` đã được chấp nhận. Vấn đề xuất hiện khi nhiều client kết nối đồng thời: nếu máy chủ xử lý tuần tự, một client đang chờ đọc có thể khiến mọi client khác phải đợi.

Ba mô hình phổ biến để xử lý là:

1. **Thread per connection với platform thread:** mỗi kết nối có một luồng nền tảng riêng.
2. **Nhóm luồng (thread pool):** số luồng worker cố định hoặc giới hạn; các kết nối được đưa vào hàng đợi chờ worker.
3. **Virtual thread per connection:** từ **Java 21 trở lên**, có thể cấp một virtual thread nhẹ cho mỗi kết nối, cho phép rất nhiều tác vụ blocking I/O đang chờ mà không đòi hỏi một OS thread riêng cho từng tác vụ.

Cả ba có thể dùng cùng API `ServerSocket`/`Socket` và cùng một hàm xử lý giao thức; khác nhau chủ yếu ở **cách quản lý vòng đời, tài nguyên và số lượng tác vụ đồng thời**. Bài học hướng đến thiết kế máy chủ TCP, không biến việc chọn mô hình luồng thành thay thế cho framing, timeout hay bảo mật.

Sau bài này, bạn sẽ biết: vì sao blocking `accept()`/`read()` ảnh hưởng concurrency; cách dùng `Thread`, `ExecutorService` và `ThreadPoolExecutor`; cách hiểu virtual threads; xây dựng demo Java 17+ chạy được; lựa chọn và giới hạn tải; xử lý timeout, shutdown và client lỗi đúng cách.

## 2. Máy chủ TCP và đơn vị công việc “kết nối”

### 2.1. Sơ đồ xử lý

~~~text
                    ┌──────────────────────────┐
Client A ── TCP ────>│                          │──> handler(A)
Client B ── TCP ────>│  ServerSocket.accept()   │──> handler(B)
Client C ── TCP ────>│  accept loop              │──> handler(C)
                    └──────────────────────────┘
                                 │
                         dispatch handlers
                         vào thread / pool
~~~

`ServerSocket` là **listening socket** dùng để chờ kết nối. Mỗi lần `accept()` thành công, API trả về một đối tượng `Socket` khác, đại diện **một kết nối TCP đã được chấp nhận**. Việc `accept()` thành công không có nghĩa server đã nhận đủ một thông điệp ứng dụng; mọi dữ liệu trong kết nối phải được đọc từ stream theo framing của giao thức.

Một số phân biệt quan trọng:

- **Accept loop:** nhận kết nối mới và giao socket cho nơi xử lý; nên giữ đủ nhẹ để không cản trở các kết nối đến tiếp theo.
- **Connection handler:** đọc/ghi trên socket của một client, kiểm tra dữ liệu, phản hồi và đóng socket khi kết thúc.
- **Blocking I/O:** `read()` có thể chờ khi chưa có dữ liệu; `write()` có thể chờ khi luồng gửi nghẽn; `accept()` chờ kết nối mới.
- **TCP connection ≠ Java thread:** socket thuộc một kết nối mạng; thread là tài nguyên thực thi mã Java. Bạn quyết định cách ánh xạ một kết nối vào tác vụ xử lý.

Mô hình cơ bản “một handler cho mỗi kết nối” rất thuận tiện cho protocol yêu cầu đọc nhiều request trên cùng socket. Tuy nhiên, các kết nối có thể **idle** hàng phút, nên tài nguyên dùng trong lúc chờ mới là yếu tố quyết định tính mở rộng.

### 2.2. Vì sao vòng lặp tuần tự thường không đủ?

~~~java
// Minh họa đơn giản, không phải chương trình chạy độc lập.
try (ServerSocket server = new ServerSocket(9000)) {
    while (true) {
        Socket client = server.accept();
        handle(client); // Blocking ngay trên thread nhận kết nối!
    }
}
~~~

Nếu `handle(client)` chờ client gửi đủ byte, vòng lặp sẽ chưa trở lại `accept()`. TCP stack vẫn có thể giữ các kết nối đang chờ trong backlog (theo giới hạn và hành vi OS), nhưng ứng dụng không xử lý các client khác ngay. Tăng backlog **không tạo thêm worker**.

Muốn server xử lý đồng thời, accept loop phải chuyển socket vào mô hình thực thi thích hợp. Dù chọn mô hình nào, **quyền sở hữu socket** phải rõ: một khi giao cho handler, handler chịu trách nhiệm đóng socket, trừ khi tác vụ bị từ chối ngay khi dispatch.

## 3. Mô hình A — Một platform thread cho mỗi kết nối

### 3.1. Ý tưởng

Một luồng nền tảng truyền thống (`java.lang.Thread`) thường gắn với một OS thread. Mỗi lần `accept()` trả về socket, máy chủ tạo và khởi chạy một thread để xử lý socket đó:

~~~java
// Minh họa: listener đã bind, handle(Socket) đóng socket.
while (running) {
    Socket peer = listener.accept();
    Thread worker = new Thread(
            () -> handle(peer), "tcp-client-handler");
    worker.start();
}
~~~

**Phải gọi `start()`, không gọi `run()`** nếu muốn thực sự khởi chạy song song. Gọi `worker.run()` trực tiếp chỉ thực thi handler trên thread accept, quay lại vấn đề xử lý tuần tự. Tên thread nên chứa thông tin nhận dạng kết nối khi cần quan sát, nhưng tránh đưa mật khẩu hoặc dữ liệu riêng tư vào tên.

Khi `handle(peer)` thực hiện `read()` blocking, **OS thread tương ứng phải chờ**, nên tốn stack, bộ nhớ và chi phí scheduler dù handler không dùng CPU. Mô hình này dễ viết, dễ gỡ lỗi, phù hợp dịch vụ nội bộ với số kết nối đồng thời nhỏ hoặc vừa, nhưng có giới hạn khi số client idle tăng mạnh.

### 3.2. Điểm mạnh và giới hạn

**Điểm mạnh:**

- Code tuần tự dễ đọc: một handler có thể đọc header, đọc payload, xử lý và ghi response theo thứ tự.
- Isolation tương đối: một handler chờ I/O không chặn trực tiếp các handler khác (nếu không tranh chấp lock/tài nguyên chung).
- Không phải quản lý hàng đợi task của executor, nếu chỉ tạo thread đơn lẻ.

**Giới hạn:**

- Mỗi kết nối thường dùng một platform/OS thread, kể cả khi chỉ đứng chờ socket.
- Không có giới hạn số thread tự động. Tạo thread vô hạn theo số kết nối có thể cạn bộ nhớ native stack, descriptor hoặc làm scheduler quá tải.
- Không có cơ chế loại bỏ công việc khi hệ thống quá tải; cần **admission control** như giới hạn connection count hoặc semaphore.
- Tạo một thread riêng cho mỗi kết nối rất ngắn có chi phí khởi tạo/kết thúc; một pool có thể tái sử dụng platform threads.

Với `Thread` truyền thống, **không mặc định thread là daemon**. Các non-daemon thread đang sống có thể giữ JVM chưa thoát sau khi accept loop dừng. Dịch vụ phải có cơ chế dừng, đóng socket, chờ worker kết thúc hoặc force-stop an toàn theo chính sách.

### 3.3. Lỗi phổ biến: quên đóng socket sau khi handler trả về

Handler nên sở hữu và đóng socket bằng `try-with-resources`:

~~~java
// Đoạn minh họa một handler, không phải chương trình độc lập.
static void handle(Socket peer) {
    try (peer) {
        peer.setSoTimeout(5_000);
        int firstByte = peer.getInputStream().read();
        if (firstByte == -1) return; // EOF
        peer.getOutputStream().write(firstByte);
        peer.getOutputStream().flush();
    } catch (IOException ex) {
        // Ghi log lỗi có ngữ cảnh, không nuốt rồi giữ socket mãi.
    }
}
~~~

`try (peer)` hợp lệ trong Java 9+ nếu biến là effectively final. Mỗi lần accept trả một socket riêng; tránh để hai handler đồng thời đọc trên cùng socket vì chúng có thể tiêu thụ xen kẽ dữ liệu và phá trạng thái parser. Nếu nhiều tác vụ có thể ghi cùng kết nối, phải tuần tự hóa **trọn frame**.

## 4. Mô hình B — Nhóm luồng: ExecutorService và hàng đợi

### 4.1. Ý tưởng

Thay vì tạo mới platform thread với mỗi kết nối, server đưa handler vào executor. Ví dụ:

~~~java
// Mã minh họa; pool được khởi tạo ở cấp server và đóng khi shutdown.
ExecutorService pool = Executors.newFixedThreadPool(8);

while (running) {
    Socket peer = listener.accept();
    pool.execute(() -> handle(peer));
}
~~~

Với 8 worker, cùng lúc tối đa 8 handler **đang thực thi** trong pool. Những handler khác chờ tới lượt. Điều này giới hạn số platform thread của executor, nhưng **không tự giới hạn số kết nối TCP được accept** hay số task đang chờ.

Một chi tiết quan trọng: `Executors.newFixedThreadPool(n)` dùng hàng đợi có thể tăng rất lớn (thực tế là hàng đợi không giới hạn theo số lượng task ở cấu hình chuẩn). Nếu hàng chục nghìn client kết nối mà handler chờ lâu, các socket và task vẫn có thể chất đống trong queue. Do đó “đã dùng thread pool” **chưa đủ** để gọi là backpressure.

### 4.2. Pool cố định có queue giới hạn

Một cấu hình có giới hạn rõ hơn:

~~~java
// Minh họa; cần import java.util.concurrent.*
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        8, 8,                       // core và maximum platform workers
        0L, TimeUnit.MILLISECONDS,  // keepAlive không quan trọng với core cố định
        new ArrayBlockingQueue<>(32), // tối đa 32 task chờ
        new ThreadPoolExecutor.AbortPolicy());
~~~

Với cấu hình này, ta có nhiều nhất 8 worker đang chạy và 32 task đang đợi trong queue của executor. Khi không thể nhận thêm, `execute(...)` ném `RejectedExecutionException`. Máy chủ phải có cách xử lý bị từ chối:

~~~java
Socket peer = listener.accept();
try {
    pool.execute(() -> handle(peer));
} catch (RejectedExecutionException rejected) {
    try {
        peer.close(); // Bắt buộc giải phóng socket chưa được bàn giao.
    } catch (IOException closeError) {
        rejected.addSuppressed(closeError);
    }
    // Ghi metric và quyết định tiếp tục accept hay giảm tải.
}
~~~

Đây là đoạn code minh họa về **đóng socket bị reject**. Nếu handler bị xếp hàng, socket đã accept có thể chờ rất lâu **trước khi** handler gọi `setSoTimeout`. Queue bounded giúp giới hạn tài nguyên đã xếp hàng nhưng không giải quyết triệt để tình trạng client giữ kết nối lâu; cần giới hạn tổng số kết nối, timeout, max session duration và deadline.

Một số chính sách reject thường gặp:

| Chính sách | Hành vi khi quá tải | Rủi ro / điều kiện sử dụng |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Có thể chủ động đóng socket và báo quá tải; dễ quan sát |
| `CallerRunsPolicy` | Thread gọi `execute` tự chạy handler khi chưa shutdown | Nếu caller là accept thread, nó có thể bị kẹt trong I/O; tạo backpressure nhưng chặn accept |
| `DiscardPolicy` | Bỏ task mà không báo qua exception | Với socket, dễ **rò rỉ kết nối** nếu không tự đóng đúng cách; không khuyên dùng |
| `DiscardOldestPolicy` | Bỏ task cũ trong queue rồi thử lại | Task cũ có thể đang sở hữu socket; dễ rò rỉ/khó bảo đảm giao thức nếu thiếu cleanup |

Đối với TCP server, giải pháp rõ ràng thường là **bounded queue + explicit rejection handler + socket close**, kết hợp admission control ở trước hoặc sau accept. Không nên dùng `newCachedThreadPool()` như một cơ chế giới hạn tải: pool này có thể tạo nhiều platform thread khi nhu cầu tăng.

### 4.3. Pool phù hợp công việc nào?

Pool đặc biệt hữu ích khi mỗi handler tương đối ngắn, hoặc số kết nối thực sự hoạt động trong cùng thời điểm nhỏ hơn rất nhiều so với lượng client truy cập. Tuy nhiên, với protocol **kết nối sống lâu và blocking read**, một worker có thể bị giữ suốt phiên. Khi tất cả 8 worker đang chờ 8 client idle, client thứ 9 bị xếp hàng **dù CPU gần như trống**.

Không giải quyết tình huống này bằng cách chỉ tăng số thread thật lớn. Có thể chọn NIO non-blocking + event loop, hoặc Java 21 virtual threads; mô hình nào cũng cần giới hạn sockets, buffers, bộ nhớ và xử lý CPU công bằng.

## 5. Mô hình C — Virtual thread cho mỗi kết nối (Java 21+)

### 5.1. Virtual thread là gì?

**Virtual threads** được chuẩn hóa trong Java 21. Chúng là đối tượng `Thread` được JVM lên lịch trên một tập platform threads (thường gọi là **carrier threads**). Mục tiêu là cho phép code dạng **thread-per-task**, đặc biệt với I/O blocking, mở rộng tới số lượng lớn tác vụ mà không cần một OS thread riêng cho từng tác vụ đang chờ.

Khi một virtual thread chờ ở các hoạt động blocking I/O tương thích, JVM thường có thể **unmount** tác vụ khỏi carrier để carrier chạy tác vụ khác. Vì vậy:

- Một virtual thread có thể gắn với **một kết nối dài hạn** trong code đơn giản như platform thread.
- Việc tạo và chờ nhiều virtual threads thường nhẹ hơn việc tạo tương ứng nhiều platform threads.
- **Virtual threads không làm CPU nhanh hơn.** Tác vụ CPU-bound vẫn tranh các lõi CPU thực.
- Đây vẫn là mô hình *concurrency*, không biến thao tác network thành phép màu: socket descriptor, buffer, heap, cơ sở dữ liệu và giới hạn downstream vẫn là tài nguyên hữu hạn.

### 5.2. API Java 21+

Nếu dùng Java 21 hoặc mới hơn:

~~~java
// Java 21+ — đoạn minh họa, giả định listener/handle/running đã có.
// Executor kiểu này tạo một virtual thread cho mỗi tác vụ.
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    while (running) {
        Socket peer = listener.accept();
        executor.execute(() -> handle(peer));
    }
}
~~~

`Executors.newVirtualThreadPerTaskExecutor()` có từ Java 21; code này **không biên dịch trên Java 17**. Một cách trực tiếp khác là `Thread.startVirtualThread(() -> handle(peer))`. Cả hai đều theo tinh thần **một virtual thread cho mỗi connection handler**, thay vì tái sử dụng một pool nhỏ virtual threads.

`ExecutorService.close()` trong try-with-resources của Java 21 chờ các task kết thúc khi đóng. Nếu accept loop chạy mãi hoặc handler đang đợi I/O vô hạn, shutdown sẽ không thể hoàn tất chỉ bằng cách đóng executor: cần **dừng accept**, **đóng listening socket** và các connected sockets, đặt timeout/deadline, và xử lý hủy tác vụ. Đoạn trên mô tả API, không phải dịch vụ có đầy đủ lifecycle.

### 5.3. Virtual thread không nên được “pool” như platform thread

Lợi ích chính của virtual threads là **tạo một thread nhẹ theo mỗi tác vụ**. Không nên cố định 8 virtual threads rồi bắt hàng nghìn kết nối chờ queue chỉ với mục đích “tiết kiệm virtual threads”. Đó là tối ưu nhầm tài nguyên.

Nếu cần hạn chế số phiên, DB queries hoặc requests tới downstream, giới hạn **tài nguyên thực** bằng `Semaphore`, connection limiter, rate limiter, bounded request queue hoặc pool kết nối DB có kích thước hợp lý. Virtual threads giảm chi phí *thread khi đợi*, không tăng giới hạn database connections.

Ví dụ giới hạn số handler đang sở hữu kết nối:

~~~java
// Java 21+ — minh họa admission control, không phải main độc lập.
// listener, handle(Socket), running và MAX_CONNECTIONS do server quản lý.
Semaphore slots = new Semaphore(MAX_CONNECTIONS);

try (ExecutorService vexec =
             Executors.newVirtualThreadPerTaskExecutor()) {
    while (running) {
        Socket peer = listener.accept();
        if (!slots.tryAcquire()) {
            peer.close(); // Quá số phiên cho phép: từ chối và đóng.
            continue;
        }
        try {
            vexec.execute(() -> {
                try {
                    handle(peer); // Handler phải đóng peer.
                } finally {
                    slots.release();
                }
            });
        } catch (RejectedExecutionException ex) {
            slots.release();
            peer.close();
            throw ex;
        }
    }
}
~~~

Phần này là **code minh họa trong ngữ cảnh server**, cần import `java.util.concurrent.*`, xử lý `IOException` và logic shutdown phù hợp; không phải một file Java độc lập. `Semaphore` giữ giới hạn tổng phiên đang xử lý. `tryAcquire()` ở đây chủ động **từ chối kết nối** khi hết permit thay vì dồn socket chờ vô hạn. Nếu handler ném unchecked exception, `finally` vẫn trả permit. Mọi đường lỗi trước khi bàn giao socket cũng phải bảo đảm đóng socket hoặc release đúng.

### 5.4. Các giới hạn cần nhớ

- Một virtual thread blocking trên API I/O tương thích có thể nhả carrier; nhưng **native call, một số vùng khóa/monitor và API không tương thích** có thể làm nó bị *pinned* tùy phiên bản JDK. Tránh giữ khóa dài qua blocking I/O và dùng công cụ chẩn đoán JFR/thread dump để kiểm tra tình huống thực tế.
- `ThreadLocal` vẫn hoạt động với virtual threads; nhưng nếu có rất nhiều phiên, lưu buffer hoặc object lớn trong `ThreadLocal` trên từng virtual thread có thể ngốn bộ nhớ. Thiết kế state rõ ràng, ràng buộc vòng đời.
- Virtual threads chạy code blocking theo phong cách tuần tự; chúng không tự giới hạn độ dài message, timeout, tần suất tạo socket hay số tác vụ CPU đang tranh chấp.
- Virtual threads thích hợp cho **I/O-bound workloads**, không nhất thiết tối ưu cho phép tính CPU-bound dài. Với CPU-bound, cần giới hạn mức song song hợp lý.
- Java 17 LTS **không có** API virtual thread ổn định; hãy tách phần code Java 21+ khỏi class Java 17 khi biên dịch.

## 6. So sánh ba mô hình theo tài nguyên thực

| Tiêu chí | Platform thread / connection | Fixed thread pool | Virtual thread / connection |
| --- | --- | --- | --- |
| Java hỗ trợ | Java 17+ và trước đó | Java 17+ và trước đó | **Java 21+** |
| Ánh xạ kết nối | 1 platform thread/connection | Mỗi handler giữ 1 worker khi chạy; các kết nối khác chờ queue | 1 virtual thread/connection, JVM chia sẻ carriers |
| Tác vụ blocking socket read | Chiếm 1 OS thread khi chờ | Chiếm 1 worker của pool khi chờ | Thường unmount và giải phóng carrier nếu I/O tương thích |
| Giới hạn tự nhiên | Platform thread/native resources | Workers bị giới hạn; queue mặc định có thể không giới hạn | Virtual threads nhẹ nhưng không giới hạn sockets/heap |
| Quản lý overload | Phải bổ sung connection cap | Bounded queue, rejection, close socket | Semaphore/rate limit/connection cap, giới hạn downstream |
| Code handler | Tuần tự, dễ hiểu | Tuần tự, dễ hiểu | Tuần tự, dễ hiểu |
| Tình huống phù hợp | Ít kết nối hoặc kết nối ngắn | Số tác vụ blocking đồng thời kiểm soát được | Rất nhiều kết nối I/O-bound chờ, dùng Java 21+ |
| Khi không nên ưu tiên | Hàng chục nghìn phiên idle | Pool nhỏ bị các phiên dài hạn chiếm hết | Bài toán thuần CPU, phụ thuộc native blocking/pinning nhiều |

Bảng so sánh nói về **xu hướng kiến trúc**, không phải chỉ số thông lượng được bảo đảm. Hiệu năng thực tế phụ thuộc hệ điều hành, JVM, độ dài session, payload, GC, database, TLS, kernel backlog, file descriptors, tỉ lệ client idle và chính sách giới hạn tải.

## 7. Ví dụ Java 17+ hoàn chỉnh: platform thread per connection và bounded pool

Ví dụ sau dùng một TCP server trên **loopback** (không cần Internet) và ba client gửi số nguyên bằng `DataOutputStream.writeInt()`. Server nhận từng socket qua `accept()`; mô hình `platform` tạo thread mới, còn mô hình `pool` dùng 2 worker có queue giới hạn. Mỗi handler đọc một số, mô phỏng đợi 100 ms, phản hồi số đó nhân 10 rồi đóng socket. Ba client chạy đồng thời và main chờ kết quả theo thứ tự client ID để stdout ổn định.

Đây là ví dụ dạy **mô hình thực thi** chứ không phải server production. Nó dùng giao thức tối giản một request/connection, tránh parser phức tạp để tập trung vào luồng. Trong hệ thống thực tế cần thêm validation, overload handling theo chính sách và graceful shutdown.

Tạo file **TcpConcurrencyDemo.java** với nội dung sau:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class TcpConcurrencyDemo {
    static final int CLIENTS = 3;

    static void handle(Socket socket) {
        try (socket;
             DataInputStream in =
                     new DataInputStream(socket.getInputStream());
             DataOutputStream out =
                     new DataOutputStream(socket.getOutputStream())) {

            socket.setSoTimeout(3_000);
            int id = in.readInt();
            if (id < 1 || id > CLIENTS) {
                throw new IOException("Invalid id");
            }

            // Giả lập tác vụ I/O có chờ (không phải CPU-bound).
            try {
                Thread.sleep(100);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            out.writeInt(id * 10);
            out.flush();
        } catch (IOException ex) {
            System.err.println("Client handling failed: " + ex);
        }
    }

    static int call(int port, int id) throws IOException {
        try (Socket client = new Socket()) {
            client.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port), 2_000);
            client.setSoTimeout(3_000);

            DataOutputStream out =
                    new DataOutputStream(client.getOutputStream());
            DataInputStream in =
                    new DataInputStream(client.getInputStream());

            out.writeInt(id);
            out.flush();
            return in.readInt();
        }
    }

    static void runMode(String mode) throws Exception {
        ThreadPoolExecutor pool = mode.equals("pool")
                ? new ThreadPoolExecutor(
                        2, 2,
                        0L, TimeUnit.MILLISECONDS,
                        new ArrayBlockingQueue<>(3),
                        new ThreadPoolExecutor.AbortPolicy())
                : null;

        List<Thread> dedicated = new ArrayList<>();
        ExecutorService acceptor = Executors.newSingleThreadExecutor();
        ExecutorService clients = Executors.newFixedThreadPool(CLIENTS);

        try (ServerSocket server = new ServerSocket(
                0, 10, InetAddress.getLoopbackAddress())) {

            server.setSoTimeout(3_000);

            Future<?> accepting = acceptor.submit(() -> {
                try {
                    for (int i = 0; i < CLIENTS; i++) {
                        Socket peer = server.accept();

                        if (pool == null) {
                            // Mode A: mỗi connection một platform thread.
                            Thread thread = new Thread(
                                    () -> handle(peer),
                                    "client-handler-" + i);
                            dedicated.add(thread);
                            thread.start();
                        } else {
                            // Mode B: 2 platform workers, queue tối đa 3.
                            try {
                                pool.execute(() -> handle(peer));
                            } catch (RejectedExecutionException ex) {
                                peer.close(); // Không để leak socket.
                                throw ex;
                            }
                        }
                    }
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });

            List<Future<Integer>> replies = new ArrayList<>();
            for (int id = 1; id <= CLIENTS; id++) {
                final int requestId = id;
                replies.add(clients.submit(
                        () -> call(server.getLocalPort(), requestId)));
            }

            int[] values = new int[CLIENTS];
            for (int i = 0; i < CLIENTS; i++) {
                values[i] = replies.get(i).get(5, TimeUnit.SECONDS);
            }

            // Chuyển lỗi từ acceptor thread sang main (nếu có).
            accepting.get(5, TimeUnit.SECONDS);
            System.out.println(mode + " -> " + Arrays.toString(values));

        } finally {
            if (pool != null) {
                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
            for (Thread thread : dedicated) {
                thread.join(5_000);
            }
            clients.shutdownNow();
            acceptor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        runMode("platform");
        runMode("pool");
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 TcpConcurrencyDemo.java
java TcpConcurrencyDemo
~~~

Stdout khi chạy thành công:

~~~text
platform -> [10, 20, 30]
pool -> [10, 20, 30]
~~~

### 7.1. Vì sao kết quả hai mode giống nhau?

**Mô hình xử lý song song khác nhau, protocol và phép tính giống nhau.** Server nhận ID 1/2/3, nhân 10 và trả về số 10/20/30. Main lấy `Future` theo thứ tự **đã gửi request**, nên thứ tự in ra không phụ thuộc client nào hoàn tất trước. Thử đổi phép tính hoặc thêm log tên thread trong handler để quan sát rõ hơn thread count, nhưng đừng dựa vào thứ tự log giữa các worker để xác định chương trình đúng/sai.

`Thread.sleep(100)` chỉ mô phỏng khoảng chờ để minh họa: nó không thực hiện I/O thật và không chứng minh thông lượng của hai mô hình. Với **3 client**, cả hai cách đều xử lý được; đây không phải benchmark. Nếu muốn đánh giá thực tế, cần đo trên tải đủ lớn với p95/p99 latency, throughput, heap/native memory, số socket, CPU, GC, queue depth, số request reject và CPU downstream.

### 7.2. Vì sao pooled server không tạo thêm thread khi đông khách?

Ở mode `pool`, `ThreadPoolExecutor(2,2, ..., queue(3))` sử dụng tối đa 2 platform worker. Client thứ ba có thể phải chờ trong queue tới khi một worker rảnh. Queue chứa **công việc xử lý socket**, không biến socket thành bất đồng bộ. Nếu client liên tục giữ kết nối không gửi dữ liệu, worker sẽ bị giữ ở `readInt()` cho đến dữ liệu, EOF hoặc timeout.

Mode `platform` không có queue worker nhưng tạo 1 OS thread cho mỗi socket được accept. Khi có rất nhiều kết nối idle, tiêu thụ tài nguyên có thể cao hơn. Đây là đánh đổi chính mà virtual threads muốn cải thiện.

### 7.3. Điểm cần cải thiện trước production

Demo chấp nhận đúng ba kết nối để có điểm kết thúc xác định, không chạy vòng lặp vô hạn, không có TLS và chỉ phản hồi một `int`. Trong dịch vụ thực tế:

- Thay số lượng `CLIENTS` cố định bằng accept loop có cơ chế dừng chủ động.
- Khi quá tải, nên giới hạn **active connections** và số task queued; đóng socket ngay khi reject.
- Thêm deadline tổng cho request, giới hạn kích thước message và idle timeout.
- Theo dõi socket còn mở để đóng khi shutdown; không chỉ gọi `ExecutorService.shutdownNow()` và kỳ vọng mọi blocking read luôn kết thúc ngay.
- Tách CPU-heavy work khỏi luồng I/O nếu tác vụ dài; cân nhắc pipeline có mức song song hợp lý.
- Có cơ chế health checks, metrics, logging an toàn, giới hạn client, kiểm thử lỗi mạng và connection reset.

## 8. Backpressure và overload: vấn đề lớn hơn lựa chọn thread

Khi server không còn đủ khả năng xử lý kịp dữ liệu nhận vào, phải có **backpressure**, tức kiểm soát lượng công việc mới. Nếu không, tất cả ba mô hình đều có thể kiệt sức.

Ví dụ tài nguyên hữu hạn:

~~~text
Server:
  max open sockets       = 1.000
  max active DB queries  = 32
  max pending tasks      = 100
  max request payload    = 64 KiB

50.000 clients cùng connect:
  Không mô hình thread nào tự biến 1.000 socket thành 50.000 socket.
  Phải accept / reject / queue / timeout / giới hạn rõ ràng.
~~~

Các con số trên chỉ là **minh họa cách thiết lập ngân sách**, không phải thông số khuyến nghị dùng chung. Cần chọn theo tài nguyên máy, ứng dụng và SLA.

### 8.1. Bốn cấp giới hạn

1. **Socket/file descriptors:** hệ điều hành có giới hạn file descriptors, bộ nhớ kernel và socket buffers; Java thread nhẹ không giảm số descriptors của TCP connection.
2. **Active connection/session count:** dùng counter hoặc `Semaphore` để bảo đảm không nhận xử lý quá nhiều phiên.
3. **Executor/queue capacity:** với platform threads, giới hạn worker và bounded queue; với virtual threads, giới hạn tác vụ/tài nguyên downstream theo nhu cầu chứ không “pool nhỏ virtual threads”.
4. **Downstream/CPU/heap:** DB pool, HTTP upstream, business logic, việc parse payload lớn, object lifetime và GC; giới hạn trên mỗi tầng.

Sử dụng queue lớn không đồng nghĩa tăng throughput. Nó có thể chỉ tăng thời gian chờ, làm client timeout trước khi worker xử lý. Một hệ thống tốt thường **báo quá tải sớm, minh bạch** hơn là giữ hàng nghìn kết nối mở để chờ vô hạn.

### 8.2. Accept backlog không phải worker queue

Tham số backlog khi bind `ServerSocket` liên quan đến **hàng đợi kết nối chờ được accept tại hệ điều hành**, với semantics/cap thực tế tùy OS. Nó không phải queue của `ThreadPoolExecutor`. Backlog đầy có thể khiến connect chậm/thất bại; pool queue đầy là tình trạng **app đã accept** nhưng chưa xử lý kịp. Hai điểm nghẽn cần metric khác nhau.

### 8.3. Per-connection state và tính độc lập

Mỗi handler nên giữ state parser trong phạm vi connection: số byte đã nhận, frame length, quyền hạn client, hạn xử lý. Không để nhiều handler dùng cùng `DataInputStream` hay `BufferedReader` của cùng một socket khi không có protocol multiplexing rõ. Chia sẻ cache, map các session hoặc metrics giữa thread cần cơ chế an toàn như `ConcurrentHashMap`, atomics hoặc lock; nhưng hạn chế giữ lock trong khi thực hiện I/O blocking.

Với virtual thread, lưu state gắn kết nối trong biến cục bộ/đối tượng session thường dễ quản lý hơn dùng `ThreadLocal` lớn. Vì `ThreadLocal` không tự có thread pool nhỏ để tái sử dụng, state của hàng triệu virtual threads có thể làm bộ nhớ tăng đáng kể.

## 9. Timeout và shutdown trong ba mô hình

### 9.1. Read timeout áp dụng ở socket, không ở executor

`socket.setSoTimeout(5_000)` giới hạn **một lần chờ read blocking**. Nếu client không gửi byte, handler có thể nhận `SocketTimeoutException` và quyết định đóng phiên. Nhưng:

- Đây không phải giới hạn tổng thời gian tồn tại kết nối; một client gửi nhỏ giọt có thể kéo dài phiên.
- `SO_TIMEOUT` không tự giới hạn `write()` hay thời gian connect.
- Với `ServerSocket`, `listener.setSoTimeout(...)` chỉ áp dụng thời gian đợi `accept()`.
- Pool/vthread không tự thay đổi semantics của TCP timeout.

Nên có **idle timeout**, **frame deadline**, **request deadline** và số lần retry phù hợp giao thức. Deadline tổng nên đo bằng `System.nanoTime()`. Nếu kết nối giữ lâu, phát hiện client idle hoặc hủy phiên đúng lúc giúp giải phóng worker/socket, không chỉ “tăng thread”.

### 9.2. Dừng server phải có thứ tự

Một chiến lược graceful shutdown thường là:

1. Đánh dấu `running = false` để không nhận công việc mới.
2. Đóng `ServerSocket` để đánh thức `accept()` đang blocking (thường ném `SocketException`); coi đây là đường kết thúc dự kiến nếu đang shutdown.
3. Dừng nhận thêm task mới, ví dụ `executor.shutdown()`; chờ các handler hoàn tất trong thời gian cho phép.
4. Nếu quá thời hạn, hủy task, đóng các client sockets còn mở để giải phóng blocking I/O, rồi chờ dọn dẹp.
5. Đảm bảo mọi connection permit/counter được trả đúng một lần trong `finally`. Xuất metrics và log shutdown không làm mất thông tin cần đối soát.

`shutdownNow()` chỉ gửi tín hiệu ngắt/hủy theo khả năng API; **không** thay thế chắc chắn cho việc đóng tất cả sockets đang bị block trên read trong mọi tình huống. `ExecutorService.close()` cũng cần thiết kế điều kiện kết thúc các handler, nếu không có thể đợi lâu. Ở mô hình platform thread per connection không dùng executor, cần cơ chế lưu và join/hủy các thread xử lý.

### 9.3. Lỗi không được làm chết accept loop vô tình

Thông thường handler bắt và xử lý `IOException` của riêng client, đóng socket rồi kết thúc. Không nên để một client gửi request lỗi khiến **toàn bộ server** ngừng accept. Ngược lại, lỗi nghiêm trọng của listening socket hoặc shutdown phải được báo/thoát vòng lặp có kiểm soát; không dùng `while(true) { catch(Exception e) {} }` lặp mãi, gây CPU spin khi socket đã đóng.

Nếu handler chạy trong `ExecutorService.submit()`, exception có thể được giữ trong `Future` thay vì tự in ra; phải quan sát `Future.get()`/giám sát task. Với `execute()`, unchecked exception có thể đi qua thread’s uncaught exception handling. Chọn cơ chế logging/metrics có chủ đích để không mất lỗi.

## 10. Khi nào chọn mô hình nào?

### Trường hợp 1: Máy chủ quản trị nội bộ, vài chục client

Platform thread per connection đơn giản, dễ debug, miễn có connection cap và timeout. Không phải ứng dụng nào cũng cần virtual threads hoặc non-blocking NIO.

### Trường hợp 2: Nhiều request ngắn, số handler chạy đồng thời cần hạn chế

Một `ThreadPoolExecutor` bounded với số worker phù hợp CPU/downstream thường hợp lý. Chú ý queue wait, task rejection và việc server đóng socket khi không còn năng lực xử lý. Nếu task giữ socket trong suốt phiên dài, pool nhỏ có thể gây nghẽn dù CPU còn rảnh.

### Trường hợp 3: Rất nhiều kết nối đồng thời nhưng phần lớn chờ socket I/O

Trên Java 21+, virtual thread per connection giúp giữ code blocking tuần tự dễ đọc mà giảm gánh nặng platform threads. Tuy nhiên vẫn phải giới hạn **sockets và tài nguyên downstream**, cấu hình timeout, quan sát pinning, kiểm thử dưới tải thực.

### Trường hợp 4: Cần event-driven xử lý hàng loạt kết nối, kiểm soát buffer/throughput chi tiết

`SocketChannel` non-blocking + `Selector` hoặc framework event loop có thể phù hợp. Mô hình đó tách connection state khỏi thread, yêu cầu parser trạng thái và xử lý partial read/write kỹ hơn. Virtual threads không phủ nhận lợi ích của NIO trong các workload và hệ thống cụ thể.

### Trường hợp 5: CPU-bound computation nặng

Thêm platform threads không tạo thêm CPU; virtual threads cũng vậy. Dùng giới hạn concurrency hợp số lõi và tài nguyên downstream; cân nhắc đẩy tính toán nặng sang executor riêng để handler phục vụ socket không bị chiếm tài nguyên vô hạn.

## 11. Lỗi phổ biến và hướng sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `worker.run()` thay `start()` | Xử lý trên accept thread, mất concurrency | Gọi `start()` hoặc `executor.execute(...)` |
| Gọi `handle()` ngay trong vòng `accept()` | Một client blocking ngăn server xử lý client khác | Dispatch handler ra thread/task phù hợp |
| Tạo platform thread không giới hạn | Cạn OS threads/native memory | Giới hạn connections; pool hoặc virtual threads phù hợp |
| Nghĩ `newFixedThreadPool` tự chặn mọi queue | Task/socket có thể tích tụ vô hạn | Dùng bounded `ThreadPoolExecutor` và rejection policy |
| Dùng `DiscardPolicy` với socket task | Socket bị bỏ quên, rò rỉ descriptor | Rejection có tín hiệu và đóng socket ngay |
| Một pool nhỏ giữ hàng nghìn long-lived TCP sessions | Các worker bị khóa ở blocking reads, queue lớn | Giảm phiên, điều chỉnh kiến trúc, dùng virtual threads hoặc NIO |
| Pooling virtual threads chỉ vì nghĩ chúng “đắt” | Tạo bottleneck không cần thiết | Virtual thread per task; limit tài nguyên thực |
| Nghĩ virtual threads khiến CPU-bound task nhanh hơn | CPU vẫn nghẽn, throughput không tăng | Giới hạn tính toán, tối ưu thuật toán/CPU |
| Quên `setSoTimeout` và overall deadline | Client idle/slow trickle giữ handler quá lâu | Timeout đọc + deadline phiên/frame |
| Không đóng socket khi task bị reject | Kết nối mở mà không handler sở hữu | Đóng trong catch `RejectedExecutionException` |
| Đóng executor nhưng quên đóng listening socket | `accept()` vẫn blocking, server không thoát | Dừng accept, đóng listener, drain handlers |
| Dùng `shutdownNow()` như cách chắc chắn hủy read | Có thể còn I/O blocking tùy API/trạng thái | Đóng client sockets còn hoạt động |
| Bắt exception rồi bỏ qua | Lỗi client/server không được quan sát | Ghi log/metric có ngữ cảnh, dọn tài nguyên |
| Nhiều handlers đọc cùng một socket | Dữ liệu bị chia lẫn, parser sai | Một owner đọc cho mỗi connection hoặc multiplexing bài bản |
| Giữ khóa chung trong blocking I/O | Nghẽn tất cả handler khác; có thể pin carrier | Rút ngắn vùng lock, tránh I/O trong synchronized |
| Dùng thread count làm thước đo tải duy nhất | Bỏ qua socket/queue/DB/heap | Theo dõi nhiều lớp tài nguyên và p95/p99 |

## 12. Bài tập tự kiểm tra

### Bài A — Thread per connection và 1.000 client idle

Server tạo 1 platform thread cho mỗi client, mỗi client gọi `read()` rồi chờ dữ liệu lâu. Hỏi có bao nhiêu thread liên quan tới 1.000 handlers?

**Đáp án:** có thể cần khoảng 1.000 platform threads phục vụ 1.000 connection handlers, chưa kể accept/main/runtime threads. Nhiều thread trong số đó đang blocking read, tiêu tốn native thread resources dù CPU ít bận. Cần giới hạn connection, timeout và xem xét mô hình khác.

### Bài B — Pool 8 worker, 100 kết nối giữ chỗ

Giả sử `Executors.newFixedThreadPool(8)`, 8 connection handlers đều đang chờ dữ liệu. 92 handler còn lại ở đâu?

**Đáp án:** chúng chờ trong queue của executor (nếu đã được submit thành công), có thể đang giữ socket mở mà chưa được phục vụ. Không nên tin rằng fixed thread pool tự giới hạn số connection; bounded queue/admission control là trách nhiệm ứng dụng.

### Bài C — Executor từ chối socket mới

Pool có 8 workers, queue 16 task, tất cả đang kín. `execute(() -> handle(peer))` ném `RejectedExecutionException`. Phải làm gì?

**Đáp án:** **đóng `peer`** vì quyền sở hữu chưa được chuyển tới handler; ghi chỉ số overload và quyết định retry/backoff/thoát theo chính sách. Không chỉ bắt exception rồi bỏ qua.

### Bài D — Virtual threads và 100.000 client

Java 21 server dùng `newVirtualThreadPerTaskExecutor()`. Điều này có cho phép “100.000 client vô điều kiện” không?

**Đáp án:** không. Virtual threads giảm chi phí scheduling/stack cho I/O-bound tasks, nhưng file descriptors, socket buffers, heap, TCP backlog, TLS, service limits và database vẫn hữu hạn. Cần stress test, hạn chế sessions và downstream.

### Bài E — Gỡ lỗi khi shutdown treo

Server gọi `executor.close()` nhưng một handler vẫn chờ `read()` vô hạn. Vì sao shutdown chậm?

**Đáp án:** đóng executor chờ tác vụ hoàn thành; nếu connection không có deadline hoặc chưa được đóng, handler có thể chưa thoát. Phải quản lý socket đang mở, đóng khi shutdown, dừng accept và chờ với deadline hợp lý.

### Bài F — Chọn mô hình cho 5.000 phiên chat TCP

Phần lớn phiên nhàn rỗi, mỗi phiên thỉnh thoảng gửi thông điệp nhỏ, ứng dụng triển khai trên Java 21. Mô hình nào đáng thử trước?

**Đáp án:** virtual-thread-per-connection là lựa chọn đáng thử vì mỗi handler có thể dùng blocking I/O tuần tự và phần lớn thời gian chờ. Nhưng lựa chọn cuối cùng cần benchmark và cần cap sockets, buffer sizes, max session duration, parse limits, backpressure. Một event-loop NIO cũng có thể phù hợp.

## 13. Checklist triển khai server TCP nhiều kết nối

- [ ] Accept loop chỉ nhận kết nối và dispatch, không vô tình blocking lâu trong handler?
- [ ] Đã chọn rõ **platform per connection**, **bounded pool** hoặc **virtual per connection (Java 21+)**?
- [ ] Mỗi socket có một owner chịu trách nhiệm đọc, xử lý và đóng?
- [ ] Đã xác định hạn mức đồng thời: socket count, executor workers, queue depth, downstream sessions, CPU và heap?
- [ ] Khi reject hoặc task dispatch thất bại, socket có được đóng và permit được trả?
- [ ] Socket read có timeout; frame/request/session có deadline và giới hạn kích thước thích hợp?
- [ ] Có test với client idle, client chậm, disconnect, partial frame và hàng đợi đầy?
- [ ] Không dùng platform thread vô hạn hoặc unbounded pool queue như một chiến lược chịu tải?
- [ ] Với Java 21 virtual threads, đã kiểm tra blocking API tương thích, thread-local footprint và vùng monitor/lock?
- [ ] Accept loop, worker handlers, thread pool và socket đều có lộ trình shutdown và quan sát lỗi?
- [ ] Đã benchmark theo kết nối đồng thời, throughput, p95/p99, heap/native memory, queue depth, rejects và downstream load?

**Kết luận:** Một TCP connection không tự đồng nghĩa với một OS thread. **Thread per connection** dễ hiểu nhưng khó mở rộng tới nhiều client idle; **thread pool** giới hạn platform workers nhưng phải quản lý hàng đợi, socket chờ và overload; **virtual thread per connection** (Java 21+) đem lại mô hình code tuần tự với chi phí thread nhẹ hơn khi chờ I/O. Dù chọn cách nào, yếu tố quyết định độ tin cậy của máy chủ vẫn là **quyền sở hữu socket, timeout, framing, backpressure và shutdown có kiểm soát**.