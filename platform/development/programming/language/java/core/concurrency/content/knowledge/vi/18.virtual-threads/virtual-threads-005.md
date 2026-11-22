# Thread-per-request cho I/O blocking bằng Virtual Threads (Java 21+)

## 1. Bài toán và mục tiêu

**Thread-per-request** là mô hình xử lý trong đó mỗi yêu cầu độc lập được giao cho một luồng thực thi riêng. Luồng nhận yêu cầu, thực hiện các bước tuần tự (đọc đầu vào, gọi dịch vụ hoặc cơ sở dữ liệu, chờ I/O, tạo phản hồi) rồi kết thúc. Mô hình này dễ đọc, dễ debug vì mã xử lý giữ phong cách đồng bộ, tuyến tính.

Với **platform thread** truyền thống (luồng Java thường gắn với luồng hệ điều hành trong lúc chạy), việc giữ hàng nghìn luồng chỉ để chờ socket, file hoặc kết quả từ hệ thống bên ngoài tiêu tốn bộ nhớ và chi phí lập lịch. Một cách đối phó là giới hạn thread pool, nhưng khi mọi worker bị kẹt ở I/O, yêu cầu mới phải xếp hàng dù CPU còn rảnh.

Từ **Java 21**, virtual thread (JEP 444) là tính năng chính thức. Một virtual thread vẫn là đối tượng `Thread` và cung cấp cách lập trình đồng bộ quen thuộc, nhưng Java runtime có thể cho nó **tạm ngừng và nhường platform thread đang chạy hộ** khi gặp nhiều thao tác chờ được hỗ trợ. Nhờ vậy có thể dùng **một virtual thread cho mỗi request** với độ đồng thời rất lớn mà không cần giữ một OS thread cho mỗi request đang đợi.

Sau bài này, bạn cần:
- Mô tả được luồng xử lý một request và vì sao I/O blocking làm nghẽn platform-thread pool.
- Viết được mã Java 21+ xử lý mỗi kết nối/yêu cầu trên một virtual thread.
- Phân biệt **số request đồng thời**, **số platform thread**, **throughput** và **latency**.
- Áp dụng timeout, backpressure và giới hạn tài nguyên thực; nhận ra các tình huống pinning và lỗi triển khai thường gặp.

## 2. Mô hình hoạt động

### 2.1. Với platform thread

Ví dụ một worker xử lý request theo thứ tự:

1. Nhận yêu cầu.
2. Đọc dữ liệu từ socket (có thể đợi).
3. Gọi một hệ thống bên ngoài bằng API đồng bộ (có thể đợi).
4. Tính toán kết quả và ghi phản hồi.
5. Kết thúc yêu cầu.

Khi thao tác I/O chờ, platform thread cũng thường bị chặn. Nếu pool có 200 thread, 200 request đang đợi có thể chiếm toàn bộ pool, khiến request thứ 201 phải đứng trong hàng đợi. Tăng kích thước pool vô hạn không giải quyết bền vững vì mỗi OS thread có chi phí riêng.

### 2.2. Với virtual thread

Virtual thread được **mount** lên một platform thread gọi là **carrier** để thực thi. Khi gặp thao tác blocking mà JDK hỗ trợ, virtual thread có thể **unmount**, lưu trạng thái cần thiết và nhường carrier cho virtual thread khác. Khi I/O sẵn sàng, nó được lên lịch chạy tiếp, có thể trên carrier khác.

```text
Request A → Virtual thread A ──[đọc socket, chờ]──┐
                                                   │ unmount
                                                   ▼
                              Carrier thread → chạy request B/C/...
                                                   │
                          I/O của A hoàn tất ──────┘
                                                   ▼
                        Virtual thread A được mount lại
                                                   ▼
                                      Ghi phản hồi A
```

Đây vẫn là **blocking ở góc nhìn mã ứng dụng**: lệnh `readLine()` chỉ trả về khi có dữ liệu, EOF, lỗi hoặc timeout. Điểm thay đổi nằm ở cách JVM sử dụng carrier trong thời gian chờ. Không phải mọi thao tác native, thư viện cũ hay lời gọi blocking đều bảo đảm unmount.

### 2.3. Điều gì cải thiện, điều gì không?

| Đặc tính | Platform thread-per-request | Virtual thread-per-request |
|---|---|---|
| Đơn vị lập trình | Một request trên một luồng | Một request trên một virtual thread |
| Khi đợi I/O phù hợp | Thường giữ OS thread | Có thể nhường carrier |
| Số task cùng chờ khả thi | Bị ràng buộc mạnh bởi OS thread | Thường cao hơn nhiều nếu tài nguyên khác cho phép |
| Mã nghiệp vụ đồng bộ | Có | Có |
| Tăng tốc tác vụ CPU-bound | Không tự động | Không tự động |
| Kết nối, heap, downstream, quota | Vẫn là giới hạn | **Vẫn là giới hạn** |

Virtual threads chủ yếu giúp **khả năng phục vụ nhiều tác vụ I/O đang chờ (throughput/scalability)**. Chúng **không làm một lần truy vấn mạng vốn mất 300 ms tự biến thành 3 ms**, không tạo thêm CPU và cũng không loại bỏ giới hạn kết nối.

## 3. API Java 21+ để tạo một thread cho mỗi tác vụ

Cách phổ biến là dùng `Executors.newVirtualThreadPerTaskExecutor()`. Mỗi lần `submit` hoặc `execute` sẽ tạo một virtual thread mới để chạy task; executor này **không phải một pool tái sử dụng một số virtual thread cố định**.

Ví dụ đầu tiên dùng `Thread.sleep` mô phỏng thời gian chờ để thấy cấu trúc xử lý độc lập. Đây **không phải ví dụ network I/O thật**; phần 4 sẽ dùng socket thực.

**Tệp `VirtualIoBatch.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualIoBatch {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                final int requestId = id;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Mô phỏng thời gian chờ
                    return "request " + requestId
                            + ", virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Lấy theo thứ tự submit để stdout xác định.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac VirtualIoBatch.java
java VirtualIoBatch
```

Stdout:

```text
request 1, virtual=true
request 2, virtual=true
request 3, virtual=true
```

Ba tác vụ có thể chờ **đồng thời**, nhưng kết quả được in đúng thứ tự vì vòng lặp gọi `Future.get()` theo thứ tự đã lưu. `get()` chờ hoàn thành và có thể ném `ExecutionException` hoặc `InterruptedException` (ví dụ khai báo `throws Exception` chỉ nhằm giữ ví dụ ngắn). `try` với `ExecutorService` đóng executor và chờ các task đã gửi hoàn thành; điều này đòi hỏi task phải có khả năng kết thúc.

Có thể tạo trực tiếp bằng `Thread.ofVirtual().start(runnable)` hoặc tạo `ThreadFactory` bằng `Thread.ofVirtual().factory()`. Khi xử lý nhiều request độc lập và cần lấy kết quả, executor per-task thường dễ quản lý hơn.

## 4. Ví dụ thực tế: một virtual thread cho mỗi kết nối TCP

Ví dụ gồm một server và một client thuần Java, sử dụng socket blocking. Mỗi lần `accept()` trả về một kết nối, server gửi công việc xử lý kết nối đó cho một **virtual thread mới**. Đoạn `BufferedReader.readLine()` trong handler thực sự chờ dữ liệu mạng. Ở ví dụ này, **mỗi kết nối chỉ gửi một dòng và nhận một dòng**; coi một kết nối tương đương một request để minh họa mô hình.

### 4.1. Server

**Tệp `VirtualEchoServer.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualEchoServer {
    public static void main(String[] args) throws IOException {
        try (ServerSocket server = new ServerSocket()) {
            // Chỉ lắng nghe trên máy hiện tại.
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090));

            try (ExecutorService requests =
                         Executors.newVirtualThreadPerTaskExecutor()) {
                System.out.println("Listening on loopback port 9090");

                while (true) {
                    Socket client = server.accept();
                    requests.execute(() -> handle(client));
                }
            }
        }
    }

    private static void handle(Socket client) {
        try (client) {
            client.setSoTimeout(5_000); // Giới hạn thời gian read bị chờ.
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(), StandardCharsets.UTF_8));

            String line = input.readLine(); // Blocking socket I/O
            if (line != null) {
                output.write("echo: " + line);
                output.newLine();
                output.flush();
            }
        } catch (IOException exception) {
            System.err.println("Request failed: " + exception.getMessage());
        }
    }
}
```

Server giữ một platform thread (luồng `main`) để `accept()`, sau đó xử lý **từng kết nối trên virtual thread riêng**. Nó không giữ một platform thread chờ dữ liệu từ mỗi client. `setSoTimeout(5_000)` giới hạn thời gian một thao tác đọc socket chờ trước khi ném `SocketTimeoutException`; đây không phải tổng deadline cho toàn bộ request.

Vòng `while (true)` là vòng phục vụ liên tục, chủ động dừng ứng dụng bằng Ctrl+C. Đây là demo tối giản, chưa có shutdown mềm, xác thực, giới hạn số kết nối hoặc chính sách chống client gửi dữ liệu quá chậm.

### 4.2. Client

**Tệp `EchoClient.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class EchoClient {
    public static void main(String[] args) throws Exception {
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 9090), 3_000);
        socket.setSoTimeout(5_000);

        try (socket) {
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));

            output.write("xin chao");
            output.newLine();
            output.flush();
            System.out.println(input.readLine());
        }
    }
}
```

Trong thư mục chứa hai tệp, biên dịch:

```bash
javac VirtualEchoServer.java EchoClient.java
```

Terminal 1:

```bash
java VirtualEchoServer
```

Stdout ban đầu của server:

```text
Listening on loopback port 9090
```

Terminal 2:

```bash
java EchoClient
```

Stdout của client:

```text
echo: xin chao
```

Mở nhiều client đồng thời: mỗi kết nối có một handler riêng, nên một client còn đang chờ gửi trọn dòng sẽ không bắt các handler khác chờ theo. Thứ tự hoàn thành giữa những client **không được bảo đảm**. Cổng 9090 phải rảnh, và server phải được chạy trước client.

### 4.3. Theo dõi một request qua các trạng thái

1. `ServerSocket.accept()` trả về `Socket` mới.
2. `requests.execute(...)` khởi tạo virtual thread cho handler.
3. Handler tạo reader/writer và gọi `readLine()`, có thể bị chờ vì chưa đủ dữ liệu.
4. Khi thao tác socket này có thể unmount, carrier sẵn sàng chạy virtual thread khác.
5. Khi dữ liệu đến, handler tiếp tục ngay sau `readLine()`, tạo phản hồi và `flush()`.
6. `try (client)` đóng socket kể cả khi có lỗi I/O; virtual thread kết thúc.

Mô hình giữ mã handler tuyến tính như xử lý một request thông thường, nhưng tăng số request đang chờ I/O có thể phục vụ trên cùng một số carrier.

## 5. Khi áp dụng vào code ứng dụng

Một handler đồng bộ có thể được hình dung như sau (đây là **pseudocode**, không phải chương trình Java độc lập):

```java
Response handle(Request request) {
    Input input = validate(request);       // CPU, ngắn
    Data data = blockingFetch(input);      // I/O waiting
    Result result = transform(data);       // CPU
    blockingWrite(result);                 // I/O waiting
    return Response.ok(result);
}
```

Khi mỗi request có virtual thread, không cần tách thủ công mọi điểm chờ thành callback, nhưng vẫn phải tuân thủ hợp đồng của từng API, kiểm tra timeout và xử lý lỗi. `blockingFetch`, `blockingWrite` ở đây là các hàm minh họa chưa định nghĩa; ứng dụng phải cung cấp implementation thực tế.

Một quyết định triển khai quan trọng: **đơn vị concurrency nên phản ánh một tác vụ nghiệp vụ** (một request, một job độc lập) chứ không phải tạo virtual thread tùy tiện cho từng phép toán nhỏ. Nếu một request cần gọi song song hai nguồn dữ liệu độc lập, có thể dùng hai task/future rồi ghép kết quả; phải tính đến hủy công việc còn lại nếu một nguồn lỗi hoặc timeout.

## 6. Giới hạn tài nguyên: nhiều virtual thread không đồng nghĩa vô hạn request

`newVirtualThreadPerTaskExecutor()` không giới hạn lượng task nộp vào. Virtual thread rẻ hơn platform thread, nhưng **request vẫn giữ object, buffer, socket, bộ nhớ và có thể chiếm kết nối downstream**. Một server nhận thêm 100.000 kết nối đến cơ sở dữ liệu chỉ vì có 100.000 virtual thread có thể làm hệ thống phía sau sụp đổ.

Dùng **backpressure/admission control** trước khi bắt đầu công việc đắt đỏ hoặc truy cập tài nguyên hữu hạn:

- **Semaphore** giới hạn số tác vụ cùng dùng một tài nguyên; permit được trả trong `finally`.
- **Connection pool** điều tiết số kết nối thực tới downstream (giới hạn phải dựa vào khả năng phục vụ, không theo số virtual thread).
- **Timeout/deadline** cho kết nối, đọc, gọi API và toàn bộ nghiệp vụ; trả lỗi hoặc từ chối sớm khi quá tải.
- **Bounded queue / rejection** ở ranh giới nhận request khi cần bảo vệ hệ thống; tránh xếp hàng vô hạn khiến latency tăng và tốn heap.

Ví dụ sau là **đoạn mã đặt trong một handler**, giới hạn tối đa 20 lần đồng thời vào tài nguyên `slowDependency`, giả sử `Semaphore permits` được chia sẻ và `slowDependency.call()` là lời gọi I/O có timeout:

```java
if (!permits.tryAcquire()) {
    throw new IllegalStateException("Dependency is busy");
}
try {
    return slowDependency.call();
} finally {
    permits.release();
}
```

Không đặt `new Semaphore(20)` bên trong **mỗi** handler; làm vậy mỗi request lại có bộ permit riêng và giới hạn không có tác dụng toàn cục. Với API thật, hãy thiết kế mức chờ permit, xử lý interrupt, mã lỗi quá tải và cleanup tài nguyên phù hợp.

**Hai giới hạn khác nhau:** virtual thread cho phép nhiều request đồng thời *đang đợi*, còn semaphore/pool xác định có bao nhiêu request được *sử dụng tài nguyên hạn chế*. Không cần biến virtual threads thành một pool kích thước cố định để bảo vệ downstream.

## 7. Pinning, blocking và khác biệt giữa phiên bản JDK

Một virtual thread chỉ nhường được carrier nếu runtime có thể unmount tại điểm chờ đó. **Pinning** là lúc virtual thread không thể nhả carrier trong một số đoạn chờ, khiến số carrier khả dụng giảm.

- Trên **JDK 21–23**, blocking lâu và lặp lại trong `synchronized` có thể pin carrier. Tránh giữ monitor khi gọi I/O dài; nếu cần khóa quanh hoạt động đó, đánh giá dùng `ReentrantLock` hoặc thu hẹp critical section.
- Từ **JDK 24**, JEP 491 thay đổi cơ chế monitor để virtual threads có thể đồng bộ hóa mà không bị pin bởi `synchronized` theo kiểu cũ. Đừng áp dụng nguyên xi lời cảnh báo của JDK 21 cho mọi JDK mới.
- Blocking trong một số **native/foreign-function** vẫn có thể pin carrier; hành vi tùy phiên bản và thư viện. Việc có virtual thread không biến mọi thư viện blocking thành nonblocking ở cấp runtime.
- `Thread.sleep` là ví dụ chờ được runtime virtual-thread hỗ trợ; với các thư viện I/O cụ thể, hãy đo thay vì mặc định chúng luôn nhường carrier.

Trên JDK 21, có thể kiểm tra `jdk.VirtualThreadPinned` qua JDK Flight Recorder (JFR) khi chẩn đoán pinning. Có thể dùng tùy chọn `-Djdk.tracePinnedThreads=full` để in stack trace trong JDK 21; các công cụ/tùy chọn và ý nghĩa phải đối chiếu phiên bản JDK đang chạy.

Quan trọng: pinning **không mặc nhiên gây sai kết quả**. Nó chủ yếu ảnh hưởng đến khả năng mở rộng khi xuất hiện nhiều lần và mỗi lần kéo dài đáng kể.

## 8. Timeout, interruption và lỗi

- **Blocking không có timeout:** có thể để một virtual thread, socket và các object liên quan tồn tại vô hạn; quá nhiều tác vụ treo vẫn gây cạn heap hoặc tài nguyên ngoài JVM.
- **`Future.cancel(true)`:** yêu cầu interrupt task; không bảo đảm mọi thư viện hoặc I/O sẽ hủy đúng lúc. Thiết kế kết thúc tác vụ và đóng tài nguyên rõ ràng.
- **`InterruptedException`:** nếu bắt để dọn dẹp mà không ném lại, thường cần `Thread.currentThread().interrupt()` để giữ tín hiệu; đừng âm thầm nuốt interrupt.
- **Task lỗi:** khi dùng `submit`, ngoại lệ của task xuất hiện qua `Future.get()` dưới `ExecutionException`. Khi dùng `execute`, xử lý và log ngoại lệ tại ranh giới handler.
- **`ExecutorService.close()`:** chờ các task hoàn thành; nếu task bị kẹt dài, shutdown cũng có thể bị kẹt. Tạo cơ chế deadline/đóng socket/hủy task cho server production.
- **ThreadLocal:** virtual threads vẫn hỗ trợ `ThreadLocal` nhưng đừng dùng nó như cache dung lượng lớn cho mỗi thread; số virtual thread lớn sẽ nhân chi phí heap. Dữ liệu request nên có vòng đời rõ ràng.

Với TCP demo, `setSoTimeout` giới hạn từng thao tác đọc, **không** tự giới hạn toàn bộ vòng đời kết nối hoặc thời gian ghi. Hệ thống thực cần kiểm soát cả kích thước bản tin, tổng deadline, idle time, memory buffer và số kết nối.

## 9. Anti-pattern thường gặp

| Sai lầm | Vì sao gây vấn đề | Hướng xử lý |
|---|---|---|
| Pool cố định 50 virtual thread vì sợ tạo nhiều thread | Dùng giới hạn thread để che giới hạn tài nguyên khác; request lại xếp hàng | Một virtual thread mỗi request, giới hạn downstream bằng pool/permit |
| Tăng virtual thread để tăng tốc CPU-heavy workload | CPU cores vẫn hữu hạn | Đo CPU, tối ưu thuật toán hoặc giới hạn CPU jobs phù hợp |
| Bỏ mọi timeout vì virtual thread rẻ | Tác vụ vẫn giữ bộ nhớ/socket/kết nối | Timeout, deadline và cleanup |
| Mở hàng nghìn kết nối tới tài nguyên chỉ chịu nổi 100 | Quá tải downstream dù JVM còn tài nguyên | Admission control, bounded pool và backpressure |
| Cho rằng mọi lệnh blocking đều nhả carrier | Pinning/native blocking tùy JDK và thư viện | Kiểm tra runtime bằng profiling/JFR và load test |
| Dùng `ThreadLocal` để cache object lớn mỗi request | Không có thread reuse như pool; tốn heap | Truyền context rõ ràng, thu gọn dữ liệu theo request |
| Không thu thập `Future` hoặc bỏ qua lỗi task | Lỗi bị mất/khó phát hiện | Chờ, tổng hợp kết quả và ghi lỗi có context |

## 10. Đo hiệu quả đúng cách

Chạy load test với **cùng nghiệp vụ và cùng giới hạn tài nguyên** khi so sánh platform-thread pool với virtual-thread-per-task. Tăng dần request đồng thời và đo:

1. **Throughput**: request/giây hoàn thành thực sự.
2. **Latency p50/p95/p99**: gồm thời gian xếp hàng, chờ I/O và xử lý.
3. **CPU, heap/GC, số kết nối, file descriptors** và mức sử dụng của downstream.
4. **Timeout, lỗi, rejected requests** và số task đang chờ; quan sát pinning nếu dùng JDK liên quan.

Ví dụ, một request tốn khoảng 10 ms CPU và 300 ms đợi I/O có thể hưởng lợi rõ khi tăng concurrency. Nếu mỗi request chỉ làm 300 ms CPU thì virtual threads không làm CPU nhanh lên. Mức cải thiện phải được **đo trong điều kiện thực**, không suy từ tỷ lệ 300/10 thành cam kết hiệu năng.

## 11. Checklist áp dụng

- [ ] Đã xác định request/job độc lập và các điểm I/O blocking.
- [ ] Chạy JDK 21+ và chọn `newVirtualThreadPerTaskExecutor()` hoặc `Thread.ofVirtual()` đúng nhu cầu.
- [ ] Mỗi tác vụ có vòng đời, đầu ra và xử lý lỗi xác định.
- [ ] Có timeout/deadline và giải phóng socket, stream, connection trong mọi đường đi.
- [ ] Có giới hạn tài nguyên hữu hạn (downstream, database, connection pool, bộ nhớ).
- [ ] Đã xem pinning theo **đúng phiên bản JDK**, không suy diễn từ tài liệu phiên bản khác.
- [ ] Đã thử tải và kiểm tra throughput, latency, tài nguyên, thất bại khi quá tải.

## 12. Tự kiểm tra

1. Nếu 2.000 request cùng đợi I/O trong 500 ms, vì sao platform thread pool 200 worker có thể sinh hàng đợi dù CPU chưa bận?
2. Khi handler gọi `readLine()` trên một virtual thread, **mã nguồn** có còn blocking không? Carrier có luôn bị giữ không?
3. Vì sao không cần tạo pool 100 virtual threads để giới hạn 100 kết nối tới database? Cơ chế nào thể hiện giới hạn đúng?
4. Hai biến thể của một nghiệp vụ: chờ API 300 ms và tính toán 300 ms. Biến thể nào dễ có lợi hơn khi chuyển sang virtual thread, và vì sao?
5. Vì sao cảnh báo pinning của `synchronized` trong JDK 21 cần được đánh giá lại khi ứng dụng nâng lên JDK 24+?

**Đáp án định hướng:** (1) worker chờ I/O vẫn chiếm slot; (2) handler vẫn viết blocking, carrier có thể được nhả nếu điểm chờ được hỗ trợ và không pin; (3) dùng semaphore/connection pool cho tài nguyên có giới hạn; (4) workload nhiều thời gian chờ I/O; (5) JEP 491 thay đổi hành vi monitor.

## Tài liệu gốc để tra cứu

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) (tính năng chính thức ở Java 21).
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) (mô hình, scheduling, ví dụ client/server, pinning theo JDK 21).
- [Java 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html) (`newVirtualThreadPerTaskExecutor()`).
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) (thay đổi từ JDK 24).

> **Ghi nhớ:** Virtual threads cho phép viết code **đồng bộ, rõ ràng** và phục vụ nhiều request **đang chờ I/O** với chi phí thread thấp hơn. Chúng không thay thế timeout, giới hạn tài nguyên, backpressure và kiểm thử tải.