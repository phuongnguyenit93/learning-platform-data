# Thiết lập Executor trước khi start() và quản lý việc dừng các luồng do ứng dụng sở hữu

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18; HttpServer cho phép ứng dụng chọn Executor để thực thi các HTTP exchange và quản lý tài nguyên đồng thời trên JDK hiện đại.  
> **Mục tiêu:** Cấu hình Executor đúng thời điểm, hiểu khác biệt giữa Executor và ExecutorService, dừng HttpServer theo thứ tự an toàn rồi giải phóng thread pool do ứng dụng tạo.

## 1. Vì sao HttpServer có Executor?

HttpServer nhận kết nối HTTP, định tuyến request đến HttpContext, rồi gọi HttpHandler để xử lý exchange. Việc thực thi handler có thể được giao cho một Executor. Nhờ đó ứng dụng kiểm soát cách các request được chạy, chẳng hạn dùng thread pool thay vì để server dùng cơ chế mặc định.

Một server phát triển có thể cần:

- Xử lý nhiều request cùng lúc.
- Giới hạn số worker thread cho các handler.
- Đặt tên thread để dễ quan sát log và thread dump.
- Quản lý thời điểm ngừng nhận request và giải phóng worker.
- Chọn executor phù hợp với đặc điểm I/O của handler.

HttpServer.setExecutor(Executor) là API nền tảng của module jdk.httpserver. Nếu ứng dụng không cấu hình executor, server dùng implementation mặc định. Nếu tự truyền executor, ứng dụng cần quản lý vòng đời của executor đó.

## 2. Hợp đồng của setExecutor()

Chữ ký API:

~~~java
public abstract void setExecutor(Executor executor)
~~~

Phải gọi setExecutor(...) **trước server.start()**. Nếu gọi sau khi server đã start, API ném IllegalStateException.

Trình tự cấu hình thông thường:

~~~java
HttpServer server = HttpServer.create(address, 0);
ExecutorService executor = Executors.newFixedThreadPool(4);

server.setExecutor(executor); // Cấu hình trước start().
server.createContext("/", handler);
server.start();
~~~

Đừng nhầm việc tạo server với việc bắt đầu phục vụ:

1. HttpServer.create(address, backlog) tạo và bind server vào địa chỉ.
2. setExecutor(executor) chọn cách thực thi exchange.
3. createContext(...) đăng ký route và handler.
4. start() bắt đầu nhận và xử lý request.

Executor phải được cấu hình trước khi server bắt đầu. Nên hoàn tất cả context và filter trước start() để cấu hình dễ kiểm soát.

Trong ứng dụng dùng named module, khai báo phụ thuộc:

~~~java
module demo.fileserver {
    requires jdk.httpserver;
}
~~~

Các API Executor và ExecutorService thuộc module java.base nên không cần khai báo module riêng.

## 3. Executor và ExecutorService khác nhau thế nào?

Executor chỉ cần phương thức execute(Runnable). Interface này không định nghĩa cách shutdown, chờ hoàn tất hay hủy task.

ExecutorService mở rộng Executor và bổ sung lifecycle:

| API | Ý nghĩa |
| --- | --- |
| execute(Runnable) | Gửi một task để executor thực thi. |
| shutdown() | Ngừng nhận task mới, tiếp tục chạy task đã được submit. |
| shutdownNow() | Cố gắng dừng task đang chạy và trả về task đang chờ chưa được bắt đầu. |
| awaitTermination(timeout, unit) | Chờ executor kết thúc trong thời gian giới hạn. |
| isShutdown() | Kiểm tra đã yêu cầu shutdown hay chưa. |
| isTerminated() | Kiểm tra mọi task đã kết thúc sau shutdown hay chưa. |

Nếu truyền một ExecutorService do ứng dụng tạo vào HttpServer, server không thay thế quyền quản lý lifecycle của ứng dụng. Ứng dụng phải shutdown executor khi không còn server/task nào cần dùng nó.

Nếu truyền một implementation chỉ có Executor, hãy dùng cơ chế lifecycle riêng mà implementation đó cung cấp. Không thể gọi shutdown() trên biến có kiểu Executor nếu đối tượng không triển khai ExecutorService.

## 4. Khi không cấu hình Executor

Nếu không gọi setExecutor(...), HttpServer dùng executor mặc định của implementation. Cách thực thi cụ thể không nên được xem là một cam kết về số lượng thread, tên thread hoặc chiến lược scheduling mà ứng dụng có thể dựa vào.

Ví dụ:

~~~java
HttpServer server = HttpServer.create(address, 0);
server.createContext("/", SimpleFileServer.createFileHandler(root));
server.start();
~~~

Đây là cách ngắn gọn phù hợp với file server thử nghiệm đơn giản. Nếu cần kiểm soát thread pool, giới hạn đồng thời hoặc quan sát worker, cấu hình executor tường minh trước start().

Không cần tự shutdown một executor mà ứng dụng chưa tạo và chưa sở hữu. Chỉ quản lý lifecycle của tài nguyên mà ứng dụng thực sự đã tạo hoặc nhận trách nhiệm quản lý.

## 5. Chọn thread pool phù hợp

### 5.1. Fixed thread pool cho ví dụ phát triển

Executors.newFixedThreadPool(n) tạo pool có số worker thread cố định:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
server.setExecutor(executor);
~~~

Ưu điểm:

- Giới hạn số handler chạy đồng thời theo số worker.
- Dễ giải thích và quan sát trong ví dụ.
- Có thể shutdown và chờ kết thúc bằng ExecutorService.

Lưu ý: newFixedThreadPool dùng hàng đợi task không giới hạn. Nếu request đến nhanh hơn khả năng xử lý trong thời gian dài, số task chờ có thể tăng và tiêu thụ bộ nhớ. Vì vậy đây là lựa chọn đơn giản cho demo/tải có kiểm soát; dịch vụ chịu tải thực tế cần cân nhắc hàng đợi có giới hạn, chính sách quá tải, timeout và giới hạn request.

Thread được tạo bởi thread factory mặc định của Executors là non-daemon. Vì vậy, sau khi server dừng, JVM vẫn có thể tiếp tục chạy nếu executor còn worker sống. Đây là một lý do thực tế để gọi shutdown() và chờ executor kết thúc.

### 5.2. ThreadPoolExecutor với hàng đợi có giới hạn

Khi cần giới hạn cả worker lẫn số task chờ, có thể tạo ThreadPoolExecutor trực tiếp:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ExecutorService executor = new ThreadPoolExecutor(
        4,                              // corePoolSize
        4,                              // maximumPoolSize
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(100),  // tối đa 100 task chờ
        new ThreadPoolExecutor.AbortPolicy());
~~~

Ví dụ trên giới hạn bốn worker và một trăm task chờ. Khi cả worker lẫn queue đều đầy, AbortPolicy từ chối task mới bằng RejectedExecutionException. Ứng dụng phải thiết kế cách quan sát và xử lý tình trạng quá tải phù hợp; không nên giả định HttpServer tự chuyển mọi lần từ chối thành response HTTP có status code mà ứng dụng mong muốn.

Hàng đợi có giới hạn không thay thế rate limit, request timeout hoặc kiểm soát kích thước body. Cần thiết kế các giới hạn này theo workload thực tế.

### 5.3. Virtual thread trên JDK 21 trở lên

Nếu ứng dụng chạy JDK 21 trở lên, có thể cân nhắc:

~~~java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
server.setExecutor(executor);
~~~

Virtual thread được finalized trong JDK 21. Đây là lựa chọn hiện đại cho workload có nhiều tác vụ blocking I/O, nhưng không phải API có sẵn khi biên dịch source target Java 18. Mã cần tương thích Java 18 nên dùng executor truyền thống hoặc cung cấp lựa chọn theo phiên bản runtime.

Virtual thread không làm cho CPU-bound handler chạy nhanh hơn một cách tự động và cũng không loại bỏ nhu cầu giới hạn tài nguyên như số kết nối, request body, database connection hoặc thời gian chờ.

## 6. Handler phải an toàn khi có nhiều request đồng thời

Khi executor có nhiều worker, nhiều handler có thể chạy cùng lúc. Một instance HttpHandler thường được đăng ký vào context và có thể được gọi cho nhiều exchange. Vì vậy không nên giả định mỗi request có một handler instance riêng.

Ví dụ không an toàn:

~~~java
public class CountingHandler implements HttpHandler {
    private int count = 0;

    @Override
    public void handle(HttpExchange exchange) throws IOException {
        count++; // Race condition nếu nhiều request cùng cập nhật.
        // Gửi response...
    }
}
~~~

Nếu cần bộ đếm dùng chung, dùng cơ chế đồng bộ phù hợp:

~~~java
private final AtomicInteger count = new AtomicInteger();

@Override
public void handle(HttpExchange exchange) throws IOException {
    int current = count.incrementAndGet();
    // Dùng current để tạo response.
}
~~~

Các lưu ý khác:

- Không giữ HttpExchange, request stream hoặc response stream trong field dùng chung.
- Không dùng một mutable buffer chung cho nhiều request nếu không đồng bộ.
- Đặt timeout cho thao tác I/O ra ngoài như database hoặc HTTP client.
- Không giữ lock trong lúc chờ network I/O nếu không cần thiết.
- Luôn đóng request/response stream để exchange hoàn tất.
- Nếu handler có state, dùng immutable object, atomic variable, lock hoặc cấu trúc thread-safe thích hợp.

## 7. Vì sao phải dừng server trước khi shutdown ExecutorService?

Thứ tự shutdown quan trọng:

~~~text
Client request mới
       |
       v
HttpServer còn đang nhận request
       |
       v
HttpServer giao exchange cho Executor
       |
       v
Worker thread chạy handler
~~~

Nếu shutdown executor trước, server vẫn có thể nhận request và cố submit task vào executor đã ngừng nhận task. Kết quả có thể là task bị từ chối hoặc exchange không được xử lý như mong muốn.

Thứ tự nên dùng:

~~~text
1. server.stop(delay)
          |
          v
2. Ngừng nhận exchange mới và chờ exchange hiện tại trong giới hạn delay
          |
          v
3. executor.shutdown()
          |
          v
4. executor.awaitTermination(timeout)
          |
          +---- hoàn tất ----> kết thúc
          |
          +---- hết timeout --> executor.shutdownNow()
                                  |
                                  v
                             chờ thêm có giới hạn
~~~

HttpServer.stop(delay) đóng listening socket và không nhận exchange mới. Phương thức chờ các exchange hiện tại đóng hoặc đến khi khoảng thời gian delay giây hết, tùy điều kiện nào đến trước; sau đó đóng các TCP connection còn mở và trả về. delay tính bằng giây.

Nếu delay quá ngắn, exchange đang chạy có thể chưa hoàn tất response trước khi connection bị đóng. Chọn delay theo thời gian xử lý tối đa mà ứng dụng chấp nhận; đừng dùng một giá trị lớn tùy tiện để che giấu handler bị treo.

Sau khi server dừng, ứng dụng gọi shutdown() trên executor do mình tạo. shutdown() không hủy task đang chạy; nó cho task đã submit cơ hội kết thúc. Nếu hết thời gian chờ, shutdownNow() yêu cầu interrupt các task đang chạy và trả về các task chưa bắt đầu. Interrupt là yêu cầu hợp tác, không đảm bảo một handler đang mắc kẹt trong mã không phản hồi interrupt sẽ dừng ngay.

## 8. Mẫu shutdown có timeout

Helper sau phù hợp với ExecutorService do ứng dụng sở hữu:

~~~java
static void shutdownExecutor(
        ExecutorService executor,
        long timeout,
        TimeUnit unit) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(timeout, unit)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(timeout, unit)) {
                System.err.println("Executor chưa kết thúc sau shutdownNow()");
            }
        }
    } catch (InterruptedException e) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Điểm cần nhớ:

- shutdown() được gọi trước để ngừng nhận task mới.
- awaitTermination() chờ trong thời gian hữu hạn, tránh chờ vô hạn.
- shutdownNow() chỉ cố gắng interrupt; handler phải phản hồi interrupt và có timeout cho I/O blocking.
- Khi bắt InterruptedException, khôi phục interrupt status bằng Thread.currentThread().interrupt().
- Không bỏ qua danh sách task trả về từ shutdownNow() nếu ứng dụng cần ghi nhận công việc bị bỏ dở.

## 9. Ví dụ hoàn chỉnh: file server dùng fixed thread pool và shutdown đúng thứ tự

Ví dụ tự tạo thư mục tạm, phục vụ hello.txt, gửi request bằng HttpClient, rồi dừng server trước khi shutdown executor.

Lưu thành ExecutorManagedFileServer.java:

~~~java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;

import java.net.InetAddress;
import java.net.Inet6Address;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorManagedFileServer {
    private static URI uri(InetSocketAddress address, String path) {
        InetAddress ip = address.getAddress();
        String host = ip.getHostAddress();
        if (ip instanceof Inet6Address) {
            host = "[" + host + "]";
        }
        return URI.create(
                "http://" + host + ":" + address.getPort() + path);
    }

    private static void shutdownExecutor(ExecutorService executor) {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println("Executor chưa kết thúc");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("executor-file-server-")
                .toAbsolutePath().normalize();
        ExecutorService executor = null;
        HttpServer server = null;
        boolean started = false;

        try {
            Files.writeString(
                    root.resolve("hello.txt"),
                    "Hello from HttpServer executor",
                    StandardCharsets.UTF_8);

            executor = Executors.newFixedThreadPool(4);
            server = HttpServer.create(
                    new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
                    0);

            // Phải thiết lập executor trước server.start().
            server.setExecutor(executor);
            server.createContext(
                    "/", SimpleFileServer.createFileHandler(root));

            server.start();
            started = true;

            URI fileUri = uri(server.getAddress(), "/hello.txt");
            HttpResponse<String> response = HttpClient.newHttpClient().send(
                    HttpRequest.newBuilder(fileUri).GET().build(),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            if (response.statusCode() != 200
                    || !response.body().equals("Hello from HttpServer executor")) {
                throw new AssertionError("Response không hợp lệ");
            }

            System.out.println("URL: " + fileUri);
            System.out.println("HTTP " + response.statusCode());
            System.out.println(response.body());
        } finally {
            // Ngừng nhận exchange trước khi executor ngừng nhận task.
            if (started) {
                server.stop(2);
            }
            if (executor != null) {
                shutdownExecutor(executor);
            }

            try (var paths = Files.walk(root)) {
                for (Path path : paths
                        .sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac ExecutorManagedFileServer.java
java ExecutorManagedFileServer
~~~

Kết quả có dạng:

~~~text
URL: http://127.0.0.1:54321/hello.txt
HTTP 200
Hello from HttpServer executor
~~~

Cổng thay đổi theo hệ điều hành. Nếu địa chỉ loopback được chọn là IPv6, URL sẽ dùng dấu ngoặc vuông quanh host.

Ví dụ này dùng fixed thread pool bốn worker để minh họa cấu hình và lifecycle. Trong ứng dụng thực tế, hãy chọn số worker, queue và timeout theo đặc điểm handler; không sao chép con số bốn như một cấu hình tối ưu chung.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| IllegalStateException khi gọi setExecutor | Server đã được start. | Cấu hình executor trước start(). |
| Request không được xử lý sau khi executor shutdown | Server vẫn nhận request nhưng executor không còn nhận task. | Gọi server.stop(delay) trước executor.shutdown(). |
| JVM không thoát sau khi server dừng | Worker thread của executor vẫn sống. | Shutdown executor và chờ awaitTermination. |
| Một handler giữ thread quá lâu | Blocking I/O không có timeout hoặc handler không phản hồi interrupt. | Đặt timeout, kiểm tra interrupt và giới hạn thời gian xử lý. |
| Bộ nhớ tăng khi tải cao | Fixed thread pool có queue không giới hạn và request đến nhanh hơn xử lý. | Dùng queue có giới hạn, overload policy và giới hạn request. |
| Bộ đếm request sai khi chạy song song | Mutable state được cập nhật không đồng bộ. | Dùng atomic/concurrent structure hoặc lock. |
| Một số exchange bị ngắt khi shutdown | stop(delay) hết thời gian trước khi exchange hoàn tất. | Chọn delay phù hợp và làm handler có thời gian xử lý hữu hạn. |
| shutdownNow() nhưng thread vẫn chạy | Task không phản hồi interrupt hoặc bị block trong thao tác không có timeout. | Thiết kế cooperative cancellation và timeout cho I/O. |
| Dùng newVirtualThreadPerTaskExecutor khi target Java 18 | API này chỉ có từ JDK 21. | Chỉ dùng khi build/runtime target JDK 21 trở lên. |

## 11. Nguyên tắc vận hành

1. **Chỉ cấu hình một lần trước start:** gọi setExecutor trước server.start().
2. **Biết ai sở hữu executor:** nếu ứng dụng tạo ExecutorService, ứng dụng phải shutdown nó.
3. **Dừng server trước executor:** ngừng nhận exchange mới trước khi ngừng nhận task.
4. **Chờ có giới hạn:** dùng awaitTermination và có kế hoạch khi hết timeout.
5. **Làm handler có thể dừng:** timeout cho I/O, xử lý interrupt và đóng exchange trong mọi nhánh.
6. **Thiết kế đồng thời:** handler và state dùng chung phải thread-safe.
7. **Kiểm soát quá tải:** cân nhắc queue giới hạn, số worker, request size và timeout.
8. **Không mặc định executor nào cũng cần shutdown:** chỉ shutdown tài nguyên có ownership thuộc ứng dụng.
9. **Không restart server đã stop:** tạo HttpServer mới cho một lifecycle mới.
10. **Phân biệt Java 18 với JDK mới hơn:** setExecutor và ExecutorService dùng được trên Java 18; virtual-thread-per-task executor chỉ dùng từ JDK 21.

## 12. Câu hỏi tự kiểm tra

1. Vì sao phải gọi setExecutor() trước server.start()?
2. Nếu không gọi setExecutor(), HttpServer dùng cơ chế nào?
3. Khác biệt giữa Executor và ExecutorService là gì?
4. Vì sao newFixedThreadPool() có thể tích lũy task chờ khi tải tăng kéo dài?
5. Vì sao handler phải an toàn khi nhiều request chạy đồng thời?
6. server.stop(delay) chờ điều gì và thời gian delay được tính theo đơn vị nào?
7. Vì sao nên gọi server.stop() trước executor.shutdown()?
8. shutdown() khác shutdownNow() như thế nào?
9. Vì sao shutdownNow() không đảm bảo mọi handler dừng tức thì?
10. newVirtualThreadPerTaskExecutor() có sẵn từ JDK nào?
11. Nếu dùng executor do thư viện khác quản lý, có nên tự ý shutdown nó không?
12. Vì sao cần timeout cho handler và thao tác I/O trong quá trình shutdown?

**Bài thực hành:** chạy ExecutorManagedFileServer, quan sát request được xử lý và chương trình thoát sau khi server dừng rồi executor kết thúc. Thử gọi setExecutor sau start() để quan sát IllegalStateException; khôi phục thứ tự đúng. Sau đó tạo nhiều request đồng thời và thay fixed pool bằng một pool nhỏ hơn, quan sát thời gian chờ. Cuối cùng thử một handler có thời gian xử lý dài để so sánh stop(0) với stop(2), rồi khôi phục handler nhanh và timeout hợp lý.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — HttpServer](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): cấu hình executor và yêu cầu gọi trước start(); đóng listening socket, thời gian chờ exchange hiện tại và đóng TCP connection.
- [Oracle JDK 27 — Executor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng thực thi Runnable.
- [Oracle JDK 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, shutdownNow và awaitTermination.
- [Oracle JDK 27 — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): factory tạo thread pool và virtual-thread-per-task executor.
- [Oracle JDK 27 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker pool, queue và rejection policy.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread được finalized từ JDK 21.
- [Oracle JDK 18 — HttpServer](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): đối chiếu API executor và server lifecycle từ phiên bản Java 18.
