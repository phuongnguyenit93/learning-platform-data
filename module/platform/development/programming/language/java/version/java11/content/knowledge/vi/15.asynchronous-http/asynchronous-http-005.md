# Java 11+ — HTTP bất đồng bộ: Tách công việc CPU dài khỏi luồng xử lý I/O

## 1. Vì sao phải tách CPU-bound work khỏi quá trình nhận HTTP?

Với `java.net.http.HttpClient`, phương thức `sendAsync` gửi HTTP request và trả về `CompletableFuture<HttpResponse<T>>` mà không bắt luồng gọi chờ đến khi response hoàn thành. Điều này cho phép xử lý nhiều request đồng thời mà không cần đặt một thao tác blocking `send` trong mỗi luồng ứng dụng.

Tuy nhiên, **nhận response không đồng nghĩa xử lý nghiệp vụ đã xong**. Khi body được nhận, ứng dụng thường còn phải giải mã cấu trúc, validate dữ liệu, tính toán, chuyển đổi hình ảnh, tổng hợp thống kê hoặc thực hiện thuật toán nặng. Những tác vụ này có thể dùng CPU lâu hơn nhiều so với bước nhận I/O.

Nếu đặt phép tính dài trong callback tiếp nối không có chính sách executor rõ ràng, có nguy cơ giữ bận luồng đang hoàn tất tác vụ HTTP, tăng độ trễ các response khác và làm giảm khả năng phục vụ tải đồng thời. Với Java 11, cách thường dùng là:

1. Khởi tạo và gửi request bằng `HttpClient.sendAsync(...)`.
2. Chuyển các bước **CPU-bound tốn thời gian** sang một `Executor` riêng thông qua `thenApplyAsync(function, cpuExecutor)` hoặc biến thể async thích hợp.
3. Xử lý thành công/thất bại trong chuỗi `CompletableFuture`, tránh gọi `join()` hoặc `get()` trên luồng điều phối I/O.
4. Giới hạn số tác vụ CPU đồng thời, hàng đợi, thời gian xử lý và kích thước input để tránh tạo một nút nghẽn mới.

Những API này có từ Java 11 hoặc sớm hơn và **vẫn phù hợp trong Java hiện đại**. Không cần xây dựng một “event loop” thủ công chỉ để tách CPU work khỏi kết quả HTTP bất đồng bộ.

## 2. Hiểu đúng luồng xử lý

Xem chuỗi logic:

```text
Luồng gọi API / application thread
         |
         | client.sendAsync(request, handler)
         v
CompletableFuture<HttpResponse<String>>
         |
         | Hoạt động HTTP / nhận response / BodyHandler
         | được điều phối bởi HttpClient
         v
Khi response future hoàn thành
         |
         | thenApplyAsync(response -> compute(response), cpuExecutor)
         | chỉ xếp lịch CPU work lên cpuExecutor
         v
Nhóm luồng CPU riêng (giới hạn số worker)
         |
         | parse / validate / biến đổi / tính toán
         v
CompletableFuture<Result>
         |
         v
Kết quả nghiệp vụ hoặc exceptional completion
```

Phần `HttpClient` chịu trách nhiệm về I/O và hoàn tất future; phần `cpuExecutor` chịu trách nhiệm về phép tính dài. **Không dựa vào tên luồng nội bộ của HttpClient**: thread thực thi có thể tùy implementation và cấu hình. Điều cần kiểm soát là phép tính nặng **được lập lịch trên executor mà ứng dụng tự chỉ định**.

Các bước nhỏ như lấy `statusCode()`, đọc một cờ hoặc ánh xạ tham chiếu có thể thực hiện nhanh. Nhưng một callback xử lý hàng triệu phần tử, parse dữ liệu lớn, nén hoặc tính hash dung lượng lớn không nên nằm trên đường hoàn tất I/O mà không có giới hạn.

## 3. `thenApply` khác `thenApplyAsync` thế nào?

`CompletableFuture` và `CompletionStage` có các biến thể để xử lý một kết quả sau khi stage trước đó hoàn tất:

| Phương thức | Nơi callback có thể chạy | Nên dùng khi nào? |
| --- | --- | --- |
| `thenApply(fn)` | Có thể chạy trên **luồng hoàn tất stage trước** hoặc một luồng gọi phương thức liên quan đến completion; nếu stage đã hoàn tất, có thể chạy ngay trên luồng đăng ký callback. | Phép biến đổi **rất ngắn**, không chờ và không dùng nhiều CPU. |
| `thenApplyAsync(fn)` | Theo **default async executor** của `CompletableFuture` (thông thường `ForkJoinPool.commonPool()` với quy tắc dự phòng theo JDK). | Công việc cần async nhưng **có chủ ý** dùng tài nguyên chung. |
| **`thenApplyAsync(fn, cpuExecutor)`** | Executor **được chỉ định rõ** trong đối số. | Phép tính tốn CPU cần tách nhóm luồng, giới hạn song song và giám sát tải. |
| `thenAcceptAsync(action, executor)` | Executor chỉ định; không có giá trị kết quả trả ra từ action. | Tác vụ cuối có side effect cần chạy riêng. |
| `thenComposeAsync(fn, executor)` | Chạy hàm tạo stage con trên executor; kết quả **làm phẳng** nested stage. | Hàm xử lý tạo ra một `CompletionStage<U>` mới thay vì giá trị `U` trực tiếp. |

### Ví dụ dễ nhầm

```java
// Giả sử client, request và cpuExecutor đã được khởi tạo.
// Phản ví dụ: phép tính rất dài có thể chạy ngay trên luồng hoàn tất HTTP.
CompletableFuture<Result> risky = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> expensiveCpuComputation(response));

// Phù hợp khi cần tách CPU work:
CompletableFuture<Result> isolated = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(response -> expensiveCpuComputation(response), cpuExecutor);
```

Đoạn trên **minh họa cấu trúc**, không phải chương trình độc lập vì `Result`, `expensiveCpuComputation` và các biến chưa được định nghĩa. Mục 6 có chương trình hoàn chỉnh chạy được.

**Điểm cốt lõi:** `sendAsync` không biến toàn bộ các phép `thenApply` nối sau thành thao tác CPU chạy trên nhóm luồng riêng. Một `thenApply` không có hậu tố `Async` **không mang bảo đảm** callback được tách khỏi luồng hoàn tất HTTP.

Ngược lại, `thenApplyAsync(fn)` không truyền executor cũng **không có nghĩa** sẽ chạy trên một “CPU pool chuyên biệt” mà ứng dụng quản lý. Nếu nhiều bộ phận cùng dùng default/common pool, có thể xảy ra tranh chấp tài nguyên và khó dự báo độ trễ. Với tải CPU đáng kể, dùng executor explicit để kiểm soát.

## 4. `HttpClient.Builder.executor` không thay thế CPU executor của ứng dụng

Java 11 cho phép tạo client:

```java
HttpClient client = HttpClient.newBuilder()
        .executor(httpExecutor)
        .build();
```

Đây là **executor của HttpClient**, phục vụ các tác vụ bất đồng bộ và phụ thuộc theo hợp đồng của client. Nó không phải lời khuyên rằng nên gửi các tác vụ nghiệp vụ CPU dài vào cùng pool đó.

Phương án dễ kiểm soát hơn:

```java
HttpClient client = HttpClient.newBuilder()
        // Có thể để client dùng executor mặc định của chính nó.
        .build();

CompletableFuture<Result> future = client.sendAsync(request, handler)
        .thenApplyAsync(response -> compute(response), cpuExecutor);
```

Ở hai đoạn này, `httpExecutor`, `request`, `handler`, `cpuExecutor`, `Result` và `compute` là các phần phải được định nghĩa khi ghép vào ứng dụng. Nếu ứng dụng đã tùy chỉnh `HttpClient.Builder.executor`, cần biết đó là chính sách dành cho hoạt động của HTTP client, **không trộn vào pool chuyên tính toán** nếu mong muốn cô lập.

Trong JDK, client có thể sử dụng những luồng khác nhau ở các giai đoạn hoạt động; không nên dựa vào kết quả của `Thread.currentThread().getName()` ở một callback không-async để suy luận vĩnh viễn kiến trúc runtime. Điều chắc chắn trong ví dụ chính là callback `thenApplyAsync(..., cpuPool)` được thực thi bởi executor riêng đã cung cấp.

## 5. Thiết kế CPU pool có giới hạn

Đừng đặt mặc định mỗi response một `new Thread(...)` hoặc một `newFixedThreadPool` không có chính sách hàng đợi. Với tải liên tục, hàng đợi không giới hạn có thể tăng bộ nhớ và thời gian chờ vô hạn. Một cách kiểm soát cơ bản bằng Java 11:

```java
// Cần import java.util.concurrent.* và java.util.concurrent.atomic.AtomicInteger.
AtomicInteger nextId = new AtomicInteger();
ThreadFactory factory = task ->
        new Thread(task, "cpu-worker-" + nextId.incrementAndGet());

ThreadPoolExecutor cpuPool = new ThreadPoolExecutor(
        2, 2, 0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(8),
        factory,
        new ThreadPoolExecutor.AbortPolicy());
```

Điểm cần hiểu:

- `corePoolSize = maximumPoolSize = 2` giới hạn cùng lúc hai tác vụ CPU chạy trong pool demo.
- `ArrayBlockingQueue<>(8)` giới hạn tối đa tám tác vụ **đang chờ** trong queue, không bao gồm hai tác vụ đang chạy.
- `AbortPolicy` từ chối tác vụ mới khi không còn sức chứa, thay vì lặng lẽ chiếm CPU trên luồng đang hoàn tất I/O.
- Số worker và độ dài queue **là ví dụ**, không phải công thức cho mọi dịch vụ. Cần đo năng lực CPU thực tế, số core, giới hạn container, chi phí mỗi request và SLA.
- Nếu workload thực sự là **blocking I/O** (ví dụ DB call đồng bộ), không nên dùng chung CPU pool chuyên tính toán. Blocking chờ khác hẳn CPU-bound work; cần thiết kế pool, client hoặc API async phù hợp.

### Chọn rejection policy cẩn thận

- `AbortPolicy`: báo quá tải bằng `RejectedExecutionException`/exceptional completion theo nơi lập lịch; giúp ứng dụng nhìn thấy tình trạng thiếu công suất và có thể giảm tải.
- `CallerRunsPolicy`: **có thể làm công việc CPU chạy ngay trên luồng gọi `execute`**, chẳng hạn luồng đang hoàn tất HTTP. Điều này phá vỡ mục tiêu “CPU không chạy trên đường I/O” khi pool quá tải; chỉ dùng nếu thật sự muốn cơ chế backpressure đó và hiểu hậu quả.
- Queue không giới hạn: tránh từ chối sớm nhưng dễ dẫn đến latency tăng và rủi ro thiếu RAM khi tốc độ nhận response cao hơn tốc độ xử lý CPU.

Không nên chỉ tăng số thread gấp hàng chục lần số core để “chạy CPU nhanh hơn”. Với công việc CPU-bound thuần túy, nhiều thread hơn thường tăng tranh chấp và context switching; hãy benchmark, giới hạn lượng công việc nhận vào và đo queue latency.

## 6. Chương trình Java 11 hoàn chỉnh, chạy độc lập

Ví dụ sử dụng `com.sun.net.httpserver.HttpServer` trên **loopback** (module JDK `jdk.httpserver`) để cung cấp hai endpoint:

- `/ok` trả HTTP 200 với body `n=1000`.
- `/error` trả HTTP 503 với body `unavailable`.

Client gọi `sendAsync`, sau đó chuyển thao tác parse body và tính tổng bình phương từ 1 đến `n` sang **`ThreadPoolExecutor` có tên luồng `cpu-worker-*`**. Ví dụ cố ý tính `n = 1000` để chạy nhanh và có stdout xác định; với phép tính CPU dài hơn, cấu trúc offload vẫn tương tự.

Lưu tệp **`CpuOffloadHttpDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CpuOffloadHttpDemo {
    static final class Result {
        final long sum;
        final String workerThread;
        Result(long sum, String workerThread) {
            this.sum = sum;
            this.workerThread = workerThread;
        }
    }

    private static void reply(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static Result compute(HttpResponse<String> response) {
        if (response.statusCode() != 200) {
            throw new IllegalStateException("HTTP " + response.statusCode());
        }
        String text = response.body();
        if (!text.matches("n=[0-9]+")) {
            throw new IllegalArgumentException("Invalid body: " + text);
        }
        int limit = Integer.parseInt(text.substring(2));
        if (limit > 100_000) {
            throw new IllegalArgumentException("Too much work");
        }
        long sum = 0L;
        for (int i = 1; i <= limit; i++) {
            sum += (long) i * i;
        }
        return new Result(sum, Thread.currentThread().getName());
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ok", exchange -> reply(exchange, 200, "n=1000"));
        server.createContext("/error", exchange -> reply(exchange, 503, "unavailable"));

        AtomicInteger nextId = new AtomicInteger();
        ThreadFactory cpuThreads =
                runnable -> new Thread(runnable, "cpu-worker-" + nextId.incrementAndGet());
        ThreadPoolExecutor cpuPool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(8),
                cpuThreads, new ThreadPoolExecutor.AbortPolicy());

        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2)).build();

            HttpRequest successRequest = HttpRequest.newBuilder(base.resolve("/ok"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            CompletableFuture<Result> processed =
                    client.sendAsync(successRequest,
                                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                            .thenApplyAsync(CpuOffloadHttpDemo::compute, cpuPool);

            System.out.println("request-submitted=true");
            Result result = processed.join(); // Only main/demo thread waits.
            System.out.println("sum-squares=" + result.sum);
            System.out.println("ran-on-cpu-executor=" +
                    result.workerThread.startsWith("cpu-worker-"));

            HttpRequest errorRequest = HttpRequest.newBuilder(base.resolve("/error"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            CompletableFuture<Result> failing = client
                    .sendAsync(errorRequest,
                            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                    .thenApplyAsync(CpuOffloadHttpDemo::compute, cpuPool);
            try {
                failing.join();
                System.out.println("http-error=unexpected-success");
            } catch (CompletionException ex) {
                System.out.println("http-error=" + ex.getCause().getMessage());
            }
        } finally {
            server.stop(0);
            cpuPool.shutdown();
            if (!cpuPool.awaitTermination(5, TimeUnit.SECONDS)) {
                cpuPool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy với **JDK 11 trở lên**. Cờ `--release 11` kiểm tra API và cú pháp Java 11; `jdk.httpserver` chỉ dùng cho fixture server cục bộ:

```bash
javac -encoding UTF-8 --release 11 --add-modules jdk.httpserver CpuOffloadHttpDemo.java
java --add-modules jdk.httpserver CpuOffloadHttpDemo
```

Kết quả stdout chính xác trong môi trường kiểm chứng:

```text
request-submitted=true
sum-squares=333833500
ran-on-cpu-executor=true
http-error=HTTP 503
```

Giải thích:

1. `request-submitted=true` chỉ xác nhận luồng chính đã tạo chain bất đồng bộ và tiếp tục đến lệnh in. Nó **không** khẳng định request HTTP đã hoàn thành tại thời điểm đó.
2. `sum-squares=333833500` là tổng `1² + 2² + ... + 1000²`, tính bằng `long` trong phương thức `compute`.
3. `ran-on-cpu-executor=true` dựa trên tên luồng mà **chính chương trình đặt** cho `cpuPool`. Đây là kiểm chứng có chủ đích rằng stage CPU chạy trên pool riêng; không suy đoán tên luồng của HttpClient.
4. `http-error=HTTP 503` minh họa status HTTP lỗi **không tự động biến `sendAsync` thành future thất bại**. `compute` kiểm tra `statusCode()` rồi ném `IllegalStateException`; `join()` trên main thread nhìn thấy `CompletionException` và nguyên nhân.
5. `processed.join()` và `failing.join()` chỉ xuất hiện trong **main demo** để chương trình in stdout theo thứ tự. Không sao chép lệnh chờ này vào callback của HTTP, UI thread hoặc event loop.
6. `reply` gửi response UTF-8 với byte count đã biết; server chạy trên `127.0.0.1` và dùng port 0 để hệ điều hành tự chọn cổng. Không cần kết nối Internet.
7. `server.stop(0)` và `cpuPool.shutdown()` giải phóng tài nguyên sau test; `awaitTermination` có giới hạn và dùng `shutdownNow` nếu pool chưa ngừng. Trong service thực tế, executor thường sống cùng vòng đời dịch vụ, không được tạo/tắt trên từng HTTP request.

**Giới hạn của fixture:** sử dụng `HttpServer` từ JDK cần môi trường cho phép mở socket loopback. Một sandbox hạn chế socket có thể từ chối server dù mã vẫn biên dịch đúng. Test không dùng host bên ngoài hoặc gửi dữ liệu thật.

## 7. Tại sao không gọi `join()` hoặc `get()` trong completion callback?

`CompletableFuture.join()` và `get()` là thao tác **chờ kết quả** khi future chưa hoàn tất. Việc dùng chúng trên đường xử lý I/O có thể chặn luồng đang cần hoàn tất các tác vụ khác.

```java
// Phản ví dụ: đoạn minh họa, không nên dùng trong đường completion I/O.
client.sendAsync(request, handler).thenApply(response -> {
    return startAnotherAsyncTask(response).join(); // Chờ blocking!
});
```

Ngoài chậm, nếu tác vụ mới phải dùng lại một executor/luồng đang bị chiếm bởi callback chờ, mã có thể bị **starvation hoặc deadlock**.

Hướng tiếp cận:

```java
// Cần startAnotherAsyncTask(response) trả CompletableFuture<Result>.
CompletableFuture<Result> result = client
        .sendAsync(request, handler)
        .thenCompose(response -> startAnotherAsyncTask(response));
```

`thenCompose` kết hợp chuỗi futures mà **không gọi `join` để lấy dữ liệu**. Nếu chính việc tạo task tiếp theo là thao tác nặng, cân nhắc `thenComposeAsync(..., appropriateExecutor)`. Nếu callback chỉ gọi một API async và trả ngay stage, `thenCompose` có thể đủ; không cần tự động biến mọi khâu thành một thread hop.

Các snippet trong mục này chỉ minh họa sự khác nhau; tên biến và phương thức giả định phải được định nghĩa ở ứng dụng. Với code chạy độc lập, xem mục 6.

## 8. Dữ liệu HTTP lớn: đừng quên `BodyHandler`

Trong ví dụ, `HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)` chỉ phù hợp vì body là vài byte. Factory này thu toàn bộ body và giải mã thành một `String` **trước khi response future chứa `String` hoàn tất**. Tách phép xử lý CPU sang `thenApplyAsync` **không làm biến mất chi phí nhận và giữ cả response body trong RAM**.

Khi response có thể là hàng trăm MB hoặc do nguồn không tin cậy cung cấp:

- `BodyHandlers.ofByteArray()` cũng giữ body trong mảng byte; không phải lựa chọn streaming an toàn cho nội dung vô hạn.
- `BodyHandlers.ofFile(path)` có thể ghi body ra tệp, phù hợp khi cần xử lý tệp có giới hạn thay vì lưu toàn bộ trong RAM; phải quản lý đường dẫn và vòng đời file.
- `BodyHandlers.ofInputStream()` trả một `InputStream` để đọc dần; thao tác đọc stream có thể **blocking**, cần xử lý/đóng đúng và không đưa việc đọc chờ I/O lâu vào **CPU pool chuyên tính toán**.
- `BodyHandlers.ofPublisher()` cung cấp một publisher dữ liệu theo `Flow`, phù hợp thiết kế có **backpressure**, nhưng tăng độ phức tạp về subscription, lifecycle và failure/cancellation.

Với tệp/stream lớn, pipeline có thể gồm ba miền tài nguyên: **network I/O**, **streaming/blocking I/O hoặc decode**, và **CPU work**. Không buộc mọi thứ chạy chung trong một CPU pool chỉ vì đã dùng `thenApplyAsync`.

Giới hạn input và request timeouts cũng cần thiết khi dùng `ofString`: body đã được tích lũy trước khi CPU stage khởi chạy, nên giới hạn bằng cách kiểm tra `response.body().length()` **sau khi nhận** không ngăn được một response quá lớn tiêu tốn bộ nhớ. Với input không tin cậy, cân nhắc BodySubscriber/streaming có quota để chặn quá trình nhận ngay khi vượt mức.

## 9. Tải đồng thời, backpressure và bài toán quá tải

Giả sử ứng dụng nhận 1.000 HTTP responses/s nhưng CPU pool chỉ xử lý được 100 bodies/s. Nếu cứ thêm vô hạn vào queue, hệ thống sẽ có:

- Latency xử lý tăng dần do mỗi response phải chờ trong queue;
- Bộ nhớ tăng nếu mỗi tác vụ còn giữ tham chiếu `HttpResponse`/`String`/`byte[]` lớn;
- Giảm hiệu quả do GC và tranh chấp, có thể hết RAM;
- Khó phát hiện lỗi vì HTTP request có thể đã thành công nhưng việc xử lý chưa xong.

**Một CPU pool có giới hạn chưa phải backpressure hoàn chỉnh đối với mạng.** Khi pool từ chối tác vụ, ứng dụng cần chính sách có chủ đích:

1. Hạn chế số HTTP requests đang in-flight bằng semaphore hoặc hàng đợi đầu vào **có giới hạn**; chỉ khởi động request mới khi có công suất cho pipeline.
2. Quy định kích thước hàng đợi CPU và số worker; chọn cách xử lý `RejectedExecutionException` (từ chối, trả lỗi hệ thống, retry có backoff phù hợp hoặc đánh dấu quá tải) ở tầng điều phối.
3. Không chọn `CallerRunsPolicy` chỉ vì muốn “không mất tác vụ”: nếu stage được lập lịch từ completion thread, chính thread đó có thể bị bắt xử lý CPU dài.
4. Đo `pool.getActiveCount()`, `pool.getQueue().size()`, số lần từ chối, p95/p99 latency, thời gian chờ queue, CPU saturation và bộ nhớ giữ bởi response body.
5. Nếu nguồn trả dữ liệu có thể rất lớn, kết hợp hạn mức byte/stream và chính sách huỷ. Tính toán CPU không thể tự bảo vệ ứng dụng khỏi một response vô hạn được buffer trước đó.

**Không retry mù quáng** khi CPU pool bão hòa: phát lại HTTP request không làm CPU có thêm công suất, thậm chí tăng tải và có thể gây side effect (đặc biệt với request không idempotent).

## 10. Timeout, cancellation và lỗi trong chuỗi future

### 10.1. Timeout request không phải timeout tính toán CPU

`HttpRequest.Builder.timeout(Duration)` dùng để hạn thời gian hoàn thành HTTP request theo hợp đồng request. Một phép CPU chạy sau khi response hoàn tất **không trở thành một phần của timeout HTTP đó**.

```java
// Snippet minh họa trong code đã có request, client và cpuExecutor:
CompletableFuture<Result> pipeline = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(response -> compute(response), cpuExecutor)
        .orTimeout(10, TimeUnit.SECONDS);
```

`orTimeout` (có trong Java 11) khiến `pipeline` hoàn tất ngoại lệ nếu vẫn chưa hoàn tất đến deadline. Nhưng điều này **không bảo đảm** tác vụ CPU đang chạy sẽ bị interrupt hoặc dừng ngay; chỉ hoàn tất future bằng lỗi timeout theo hợp đồng. Với tính toán dài, cần cơ chế dừng hợp tác: kiểm tra cờ hủy, chia công việc thành khối, dùng interruption khi thích hợp hoặc quản lý tác vụ qua `Future`/executor theo chính sách ứng dụng.

Đừng nhầm **timeout báo lỗi cho caller** với **thu hồi ngay CPU và bộ nhớ**.

### 10.2. Transport error, HTTP status và lỗi CPU khác nhau

| Nguồn lỗi | Biểu hiện thường gặp | Cách xử lý |
| --- | --- | --- |
| DNS, socket, timeout trong `sendAsync` | Future HTTP hoàn tất ngoại lệ, downstream CPU stage thường không chạy. | Phân loại nguyên nhân I/O và chính sách retry phù hợp. |
| HTTP 4xx/5xx | Thường vẫn có `HttpResponse<T>` bình thường với `statusCode()`. | Tự kiểm tra mã; có thể đọc error payload theo schema riêng. |
| Payload giải mã được nhưng sai định dạng | Parser/validator ném ngoại lệ như `IllegalArgumentException`. | Báo dữ liệu không hợp lệ; không cho rằng network failed. |
| Tác vụ CPU thất bại | Future downstream hoàn tất ngoại lệ. | Ghi nhận nguyên nhân, truy vết request và giới hạn log dữ liệu. |
| CPU pool quá tải | Executor có thể từ chối scheduling. | Giảm lượng công việc nhận vào hoặc báo quá tải; không xử lý CPU dài ngay trong callback I/O. |

Khi dùng `join()` ở ranh giới đồng bộ, lỗi downstream có thể được bọc trong `CompletionException`. Với `get()` thì thường gặp `ExecutionException`; không nên chỉ đọc `ex.getMessage()` rồi làm mất nguyên nhân.

Đối với `whenComplete(...)`, `handle(...)` và `exceptionally(...)` **không có hậu tố Async**, chính callback xử lý lỗi cũng có thể chạy trên luồng hoàn tất. Chỉ dùng chúng cho thao tác nhẹ. Nếu phải tạo báo cáo lỗi nặng hoặc ghi log/DB chậm, chuyển sang executor phù hợp hoặc cơ chế event/queue không chặn.

### 10.3. Cancellation lan truyền tới đâu?

Hủy một `CompletableFuture` ở giữa pipeline **không phải hợp đồng rằng mọi HTTP request upstream và mọi phép tính downstream đều dừng ngay**. Việc hủy stage và hủy exchange HTTP có các quy tắc riêng tùy future mà HttpClient trả và cách triển khai. Đừng mặc định gọi `processed.cancel(true)` trên result đã map sẽ luôn đóng kết nối và interrupt CPU worker.

Đặt ra cơ chế hủy có chủ đích: giữ tham chiếu future gốc của `sendAsync` nếu cần hủy request, đặt cờ để phép tính kiểm tra và dừng hợp tác, xử lý đóng stream/file, ghi nhận tác vụ đã vượt deadline. Với dữ liệu quan trọng, hiểu rõ tác dụng của retry sau khi đã hủy.

## 11. Kiểm thử thiết kế offload mà không phụ thuộc tên luồng của JDK

Một bài unit/integration test tốt nên kiểm tra:

| Trường hợp | Assertion cần có |
| --- | --- |
| HTTP 200 trả body đúng | Kết quả CPU đúng với dữ liệu mẫu, không chỉ có status 200. |
| Tính toán nằm trên CPU executor riêng | Trong stage CPU, lưu/kiểm tra tên luồng do **chính app đặt**, hoặc dùng test executor quan sát được lịch chạy. |
| HTTP 503 | Tầng nghiệp vụ phân loại status lỗi; không parse body như thành công. |
| Body sai cấu trúc | Parser báo lỗi rõ; không dùng CPU trên dữ liệu không hợp lệ và không nhầm thành lỗi network. |
| Network failure | Future báo lỗi transport; CPU stage không được thực thi khi upstream failed. |
| CPU pool bị bão hòa | Có backpressure hoặc exceptional completion/từ chối **được xử lý**, không đẩy tác vụ nặng chạy vô hạn trên luồng I/O. |
| Nhiều request cùng lúc | Theo dõi công suất CPU, queue và độ trễ; không chỉ kiểm tra “có dùng Async” là đủ. |
| Shutdown/timeout | Tài nguyên được đóng, không còn worker/task tồn đọng ngoài chính sách. |

Không assert tên thread nội bộ như `HttpClient-1-Worker-0` vì JDK, môi trường và cấu hình có thể thay đổi. Trong ví dụ mục 6, `cpu-worker-*` là tên **do fixture tự đặt**, do đó assert này có ý nghĩa. Tránh test `Thread.sleep(100)` rồi khẳng định chính xác thứ tự thread khi chưa đồng bộ; dùng `CountDownLatch` hoặc futures để phối hợp khi cần.

### Unit test đơn giản cho phép tính (không cần HTTP server)

Tách `compute(HttpResponse<String>)` và phần parse/thuật toán thành hàm có thể test trực tiếp, hoặc đưa phép tính thành hàm thuần `sumSquares(int n)`:

```java
static long sumSquares(int n) {
    if (n < 0 || n > 100_000) {
        throw new IllegalArgumentException("n out of range");
    }
    long sum = 0;
    for (int i = 1; i <= n; i++) {
        sum += (long) i * i;
    }
    return sum;
}
```

Đây là đoạn minh họa trong một lớp Java; kết quả `sumSquares(1_000)` là `333_833_500L`. Tách hàm thuần giúp test riêng công thức và input validation; integration test HTTP chỉ cần kiểm chứng orchestration/cross-thread/offload và xử lý status.

**Không tạo CPU benchmark bằng vòng lặp vô hạn trong CI.** Nếu cần kiểm tra tác động concurrency, dùng workload có giới hạn và threshold phù hợp môi trường; kết quả latency tuyệt đối phụ thuộc CPU, JVM warmup và tải hệ thống.

## 12. Những hiểu lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`sendAsync` tự chuyển mọi việc CPU vào một thread riêng.” | Chỉ request chạy bất đồng bộ; các dependent stage cần chính sách executor rõ ràng. |
| “`thenApply` luôn chạy trên luồng người dùng.” | Có thể chạy trên luồng hoàn tất upstream; không bảo đảm tách khỏi I/O. |
| “Thêm `Async` nhưng không truyền executor là có CPU pool độc lập.” | Thường dùng default async executor; muốn cô lập, chỉ định executor. |
| “`HttpClient.Builder.executor` là nơi nên chạy mọi thuật toán CPU.” | Đây là executor phục vụ client; không dùng chung nếu muốn tránh CPU work ảnh hưởng I/O. |
| “Chỉ cần `Thread.sleep` trong callback để nhường CPU.” | `sleep` chặn luồng callback, không giúp offload. |
| “`join()` trong callback là async vì future vốn async.” | `join()` **chờ blocking** khi chưa có kết quả, có thể gây starvation/deadlock. |
| “Một số thread thật lớn sẽ làm CPU-bound nhanh hơn.” | Bị giới hạn bởi CPU cores, contention và scheduling. |
| “Queue vô hạn không có rủi ro.” | Latency và bộ nhớ có thể tăng không giới hạn. |
| “`CallerRunsPolicy` giữ CPU luôn tách khỏi I/O.” | Không: có thể chạy CPU ngay trên thread gọi `execute`. |
| “Timeout HTTP cũng giới hạn luôn phép CPU sau response.” | Không; request timeout và computation timeout là hai miền khác nhau. |
| “`orTimeout` chắc chắn dừng task đang chạy.” | Không bảo đảm interrupt/thu hồi ngay công việc. |
| “Future trả lỗi thì chắc chắn HTTP status là 500.” | Network failure, parser error và CPU error khác với HTTP status. |
| “`ofString` dùng an toàn cho body nhiều GB miễn có CPU pool.” | Response có thể bị buffer trước khi CPU stage chạy; cần giới hạn/streaming. |
| “Hủy downstream future sẽ chắc chắn hủy upstream HTTP.” | Không có bảo đảm tổng quát như vậy; thiết kế cancellation ở đúng tầng. |

## 13. Checklist áp dụng cho dự án Java 11+

1. **Xác định việc CPU-heavy thật sự:** parse/validate body lớn, nén, xử lý ảnh, tính toán/transform; đo bằng profiler và latency metrics.
2. **Giữ I/O async:** dùng `HttpClient.sendAsync` và xử lý bằng `CompletionStage` thay vì gọi `send`/`get` trên event loop.
3. **Giữ callback nhanh:** `thenApply`, `whenComplete`, `exceptionally` không async chỉ nên làm thao tác nhẹ.
4. **Offload rõ ràng:** dùng `thenApplyAsync(fn, cpuExecutor)` khi phép tính cần tài nguyên CPU và không nên ảnh hưởng completion thread.
5. **Chọn pool có giới hạn:** số worker theo công suất, hàng đợi có giới hạn và chính sách quá tải rõ; không dùng `CallerRunsPolicy` nếu mục tiêu là tách hoàn toàn CPU khỏi luồng I/O.
6. **Giảm dữ liệu giữ trong queue:** chuyển thông tin cần thiết sang cấu trúc nhỏ sau khi xác thực; không giữ nguyên response body lớn nếu không cần.
7. **Phân biệt nguồn lỗi:** network vs HTTP status vs parse/validation vs CPU rejection; bảo toàn nguyên nhân và thông tin chẩn đoán an toàn.
8. **Xử lý timeout/hủy có chủ ý:** request timeout không bao trùm CPU stage, `orTimeout` không tự dừng phép tính; dùng cơ chế dừng hợp tác.
9. **Đọc body hợp lý:** `ofString` cho nội dung nhỏ, streaming/quota cho input lớn hoặc không tin cậy, tránh blocking reads trong CPU pool.
10. **Đo tải thực tế:** CPU usage, active workers, queue depth, queue wait, response latency, error/rejection rate và memory.
11. **Test bằng server local và executor do app định danh:** tránh dựa vào tên luồng JDK, Internet hoặc thời gian tuyệt đối.
12. **Đóng tài nguyên đúng vòng đời:** executor theo vòng đời service, không tạo pool mới theo từng request; dừng server/test pool và các stream khi kết thúc.

### Tài liệu chính thức

- [Oracle Java SE 11 — `HttpClient.sendAsync` và `HttpClient.Builder.executor`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 11 — `HttpClient.Builder.executor`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java SE 11 — `CompletableFuture`, `thenApplyAsync`, `thenCompose`, `orTimeout`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 11 — `HttpResponse.BodyHandlers` và cách nhận body](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 11 — `ThreadPoolExecutor` và `RejectedExecutionHandler`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle Java SE 25 — `HttpClient` và `CompletableFuture` còn được hỗ trợ](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html)
