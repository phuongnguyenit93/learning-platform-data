# Chọn executor cho công việc tiếp nối và tránh chặn luồng xử lý I/O

## 1. Vì sao một HTTP client bất đồng bộ vẫn có thể bị chậm hoặc nghẽn?

**HttpClient.sendAsync(...)** trong Java trả về **CompletableFuture<HttpResponse<T>>**. Lời gọi không yêu cầu thread đang gọi đứng chờ toàn bộ response như **send(...)**. Tuy nhiên điều đó **không bảo đảm mọi callback tiếp nối đều không chặn**, cũng không bảo đảm chúng chạy trên thread do bạn mong muốn.

Một ứng dụng có thể viết:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .thenApply(response -> expensiveCalculation(response.body()));
~~~

Nếu expensiveCalculation ngốn CPU hoặc đợi database, nó có thể chạy ngay trên thread đang hoàn tất một future hoặc thread đăng ký stage. Thread đó **có thể liên quan đến việc thực hiện các tác vụ bất đồng bộ của HTTP client**; nếu bị chiếm lâu, tiến độ những tác vụ khác có thể bị ảnh hưởng.

**Mục tiêu của bài**: chọn đúng executor cho công việc tiếp nối (continuation), để **I/O progress không phải đợi nghiệp vụ nặng**, đồng thời không chuyển vấn đề sang một thread pool/queue không giới hạn.

Một cách thiết kế rõ ràng:

~~~text
                         HttpClient.sendAsync(...)
                                  |
                  Nhiệm vụ HTTP: network, headers, body
                                  |
                     CompletableFuture<HttpResponse>
                                  |
                thenApplyAsync(transform, businessPool)
                                  |
                   Executor nghiệp vụ riêng
                                  |
                     CompletableFuture<Result>
                                  |
              thenCompose / handle / whenComplete ...
                                  |
               Boundary của API/test nhận kết quả
~~~

**Lưu ý quan trọng:** API không cam kết tên một thread nào, cũng không nói tất cả I/O đều thực thi trên những thread được cấu hình qua Builder.executor. Phải dựa vào **hợp đồng executor và CompletionStage**, không dựa vào suy đoán “callback chắc chắn chạy trên event loop X”.

## 2. Hiểu đúng ba nơi công việc có thể chạy

### 2.1. Thread gọi sendAsync

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());
~~~

sendAsync trả một future biểu diễn kết quả; lời gọi có thể thực hiện một số công việc khởi tạo ngay trong thread caller. Bản thân response/body chưa được đảm bảo hoàn tất khi hàm trả về.

Không viết code **future.join()** ngay sau sendAsync trong request-handling/event-loop thread nếu mục tiêu là không chặn: join làm thread caller **đợi** future hoàn tất và biến luồng bất đồng bộ thành một chỗ chờ đồng bộ.

### 2.2. Executor do HttpClient.Builder.executor(...) cấu hình

~~~java
ExecutorService clientTasks = Executors.newFixedThreadPool(4);

HttpClient client = HttpClient.newBuilder()
        .executor(clientTasks)
        .build();
~~~

Theo Javadoc Java 17, **Builder.executor(Executor)** đặt executor dùng cho **các tác vụ asynchronous và dependent của HTTP client**. Khi không chỉ định, mỗi HttpClient mới có executor mặc định riêng do implementation tạo. **HttpClient.executor()** trả Optional có thể rỗng nếu không cấu hình explicit; điều đó **không có nghĩa HttpClient thiếu thread/executor nội bộ**.

Không nên mặc định rằng việc truyền clientTasks vào HttpClient sẽ khiến **mọi** lambda .thenApply, .thenApplyAsync hay những stage do người dùng gắn vào luôn chạy trên clientTasks. Quy tắc của **CompletableFuture** vẫn quyết định nơi thực thi dependent stage.

### 2.3. Executor dành riêng cho continuation

~~~java
ExecutorService businessPool = Executors.newFixedThreadPool(2);

CompletableFuture<String> processed =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .thenApplyAsync(
                    response -> transform(response.body()),
                    businessPool);
~~~

Đây là cách **nêu rõ nơi chạy transform**: CompletableFuture sắp xếp callback **trên businessPool được truyền vào**. Nó tách các công việc nặng khỏi executor do HTTP client sử dụng cho tiến độ asynchronous.

Trong sản phẩm, businessPool nên được định cỡ theo loại công việc và kiểm soát tải; newFixedThreadPool có số thread cố định nhưng hàng đợi **không giới hạn mặc định**, nên ví dụ đầy đủ bên dưới dùng **ThreadPoolExecutor với bounded queue**.

## 3. thenApply khác thenApplyAsync như thế nào?

Java 17 CompletableFuture quy định hành vi thực thi dependent stages như sau:

| API | Executor được sử dụng theo hợp đồng | Điều cần ghi nhớ |
| --- | --- | --- |
| **thenApply(fn)** | Không chỉ định executor; action có thể chạy trên thread hoàn tất stage trước hoặc thread caller liên quan đến completion | **Không đặt công việc nặng/blocking** nếu thread chạy không được kiểm soát |
| **thenAccept(fn)**, **whenComplete(fn)**, **handle(fn)** | Các dạng không có Async có cùng rủi ro affinity tới completing/calling thread | Callback có tác dụng phụ cũng có thể chiếm thread |
| **thenApplyAsync(fn)** | Dùng default asynchronous execution facility của CompletableFuture | Mặc định thường là **ForkJoinPool.commonPool()** với CompletableFuture thông thường; không phải tên pool của HttpClient.Builder.executor |
| **thenApplyAsync(fn, executor)** | Dùng **Executor do ứng dụng cung cấp** | Lựa chọn rõ ràng cho business work cần kiểm soát |
| **thenCompose(fn)** | Tạo một stage mới và **flatten** CompletionStage mà fn trả về; không tự bật một thread mới | Phù hợp khởi động một thao tác async tiếp theo nếu callback nhẹ |
| **thenComposeAsync(fn, executor)** | Hàm tạo stage tiếp theo được chạy trên executor chỉ định | Hữu ích khi bước quyết định/chuẩn bị tiếp theo nặng |
| **whenCompleteAsync(action, executor)** | Action quan sát thành công/thất bại chạy trên executor | Không biến kết quả lỗi thành thành công |
| **handleAsync(fn, executor)** | Fn xử lý cả result và exception trên executor | Có thể chuyển lỗi thành giá trị hoặc đổi lỗi; thiết kế rõ chính sách |

**Hai điểm dễ nhầm:**

1. **thenApply không có nghĩa luôn chạy trên I/O thread.** Nếu stage nguồn đã hoàn tất trước khi đăng ký, thread đang gọi thenApply có thể chạy lambda ngay; nếu chưa hoàn tất, một thread hoàn tất stage có thể chạy nó. Chính vì **không có cam kết thread cụ thể**, không đặt tác vụ nặng tại đây.
2. **thenApplyAsync không truyền executor không có nghĩa chắc chắn dùng clientTasks của HttpClient.** Theo CompletionStage/CompletableFuture, nó dùng **default asynchronous execution facility** của future. Với CompletableFuture chuẩn, đó thường là **ForkJoinPool.commonPool()**; một implementation/subclass có thể có biến thể. Muốn chắc chắn, **truyền executor explicit**.

### Một ví dụ khái niệm về non-async continuation

~~~java
// Snippet Java 17; thread thực thi lambda không được cố định bởi API.
CompletableFuture<String> response = new CompletableFuture<>();

response.thenApply(value -> {
    // Nếu complete() xảy ra từ một thread xử lý HTTP, lambda có thể
    // chạy ở thread đó; nếu future đã complete, caller cũng có thể chạy.
    return value.toUpperCase(Locale.ROOT);
});
~~~

Không ép đo thread bằng Thread.sleep(...) rồi suy diễn từ tên; scheduler, thời điểm hoàn tất stage và implementation có thể thay đổi qua các lần chạy.

## 4. Chọn executor theo loại công việc

Không có một cấu hình pool “tối ưu chung” cho mọi ứng dụng. Cần phân loại workload:

| Công việc tiếp nối | Khuyến nghị | Vì sao |
| --- | --- | --- |
| **Chọn một field, đọc status, đổi kiểu nhỏ, tính toán rất ngắn** | Có thể dùng thenApply nếu biết chắc callback đủ nhẹ | Chi phí chuyển thread có thể không đáng, nhưng vẫn cần nhớ thread affinity không xác định |
| **Parse JSON lớn, nén, băm, tính điểm, xử lý dữ liệu tốn CPU** | **thenApplyAsync(fn, cpuExecutor)** | Không chiếm thread làm HTTP tiến triển; pool CPU cỡ phù hợp số lõi |
| **Gọi JDBC blocking hoặc thư viện I/O đồng bộ** | **thenApplyAsync(fn, blockingExecutor)**; giới hạn đồng thời theo connection pool | Chờ I/O có thể lâu; tách khỏi HTTP/client executor và pool CPU |
| **Gọi API HTTP khác qua sendAsync** | **thenCompose(...)** để nối hai future, không .join() ở giữa | Không tiêu tốn thread đứng đợi request thứ hai |
| **Ghi log/telemetry rất nhẹ** | thenAccept/whenComplete ngắn; nếu phức tạp, dùng executor riêng | Logger đồng bộ chậm vẫn có thể chặn thread |
| **Đợi user, file lớn hoặc stream phản hồi** | Phương pháp streaming/backpressure; xử lý blocking ở worker riêng | Không kéo dài callback subscriber/I/O |
| **Bắt lỗi/retry và tính toán chính sách** | handle/exceptionally hoặc handleAsync(..., executor) | Tách phần nghiệp vụ và kiểm soát số lần retry |

**Executor không tự động làm thao tác synchronous thành asynchronous non-blocking**; nó chỉ di chuyển chỗ bị block sang thread khác. Nếu thao tác JDBC/legacy I/O vẫn block, cần giới hạn concurrent tasks, thời gian chờ và backpressure.

### Tách transport executor và business executor

Một mô hình nhiều tầng:

~~~text
HTTP request (sendAsync)
    |
    +-- HttpClient executor: các task asynchronous/dependent nội bộ
    |   -> giữ đủ năng lực để network/body tiến triển
    |
    +-- Business CPU executor: parse/tính toán lớn
    |   -> số thread thường cân theo CPU, bounded queue
    |
    +-- Blocking I/O executor (nếu có): JDBC/legacy I/O
    |   -> số task đồng thời cân theo connection pool/deadline
    |
    +-- Event loop/caller/API boundary: không join/get tại hot path
~~~

Đừng gắn cùng một **pool rất nhỏ và có công việc chặn dài** cho cả HttpClient tasks và business tasks; khi business chiếm hết worker, client có thể mất năng lực tiến hành những bước asynchronous khác. Cũng đừng biến mọi continuation rất nhỏ thành một task thread-pool mới mà không có lý do: context switching và queue cũng tốn chi phí.

## 5. Các anti-pattern và cách sửa

### Anti-pattern A — blocking trong thenApply không có executor

~~~java
// BAD: dao.findById(...) là JDBC blocking.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApply(response -> dao.findById(response.body()));
~~~

**Vấn đề:** JDBC có thể mất hàng trăm ms/giây. Stage không được gắn executor explicit nên nó có thể giữ thread đang hoàn tất HTTP future, làm giảm throughput của các tác vụ khác.

~~~java
// BETTER: dành riêng pool cho I/O đồng bộ, có giới hạn.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApplyAsync(
            response -> dao.findById(response.body()),
            jdbcExecutor);
~~~

Các biến dao, req, jdbcExecutor là **snippet minh họa**, không phải file độc lập. Pool cần được quản lý vòng đời và capacity, không chỉ tạo một newCachedThreadPool không giới hạn.

### Anti-pattern B — sendAsync xong join trong callback

~~~java
// BAD: dùng thread của continuation chỉ để chờ HTTP call thứ hai.
client.sendAsync(req1, HttpResponse.BodyHandlers.ofString())
      .thenApply(first -> client.sendAsync(
                buildSecondRequest(first.body()),
                HttpResponse.BodyHandlers.ofString()).join());
~~~

Khi join chờ request thứ hai, một thread bị giữ mà không làm việc hữu ích. Nếu callback chạy trên executor dành cho HttpClient, rủi ro starvation tăng lên.

~~~java
// BETTER: trả CompletionStage và flatten với thenCompose.
client.sendAsync(req1, HttpResponse.BodyHandlers.ofString())
      .thenCompose(first ->
            client.sendAsync(
                buildSecondRequest(first.body()),
                HttpResponse.BodyHandlers.ofString()));
~~~

**thenCompose không bắt buộc spawn thread**; nó chỉ tạo composition của hai thao tác đã async. Hàm buildSecondRequest nên nhẹ; nếu cần CPU nặng để xây request, dùng **thenComposeAsync(..., businessExecutor)**.

### Anti-pattern C — tưởng thenApplyAsync không có executor luôn là app pool

~~~java
// Không cung cấp app executor: default CF async facility được dùng.
client.sendAsync(req, HttpResponse.BodyHandlers.ofString())
      .thenApplyAsync(resp -> cpuHeavy(resp.body()));
~~~

Không dựa vào suy đoán pool. Nếu cần tải và latency được quản trị, gọi overload có **Executor explicit**.

### Anti-pattern D — CallerRunsPolicy trên business pool

~~~java
// Có rủi ro khi full queue:
new ThreadPoolExecutor.CallerRunsPolicy();
~~~

Khi pool và queue đã bão hòa, **CallerRunsPolicy** chạy task ngay trên **thread gọi executor.execute(...)**. Với CompletableFuture continuation, caller có thể là thread đang hoàn tất HTTP future. Vô tình chạy business task tại đó sẽ **đưa công việc nặng trở lại đường xử lý I/O/completion**, đánh mất mục tiêu tách luồng.

Với pool xử lý continuation, **AbortPolicy** có thể phù hợp hơn: khi overload, nó **ném RejectedExecutionException**, để hệ thống ghi nhận và thực hiện backpressure/fail fast. Nhưng phải xử lý failed futures đúng, không bỏ mặc hoặc làm mất request. Rejection policy là quyết định thiết kế, không phải chỉ đổi tên một class.

### Anti-pattern E — newCachedThreadPool không giới hạn

~~~java
// Phải đánh giá kỹ khi có tải không tin cậy / blocking kéo dài.
ExecutorService pool = Executors.newCachedThreadPool();
~~~

Pool có thể tăng số thread theo lượng công việc chậm, tiêu thụ memory/stack và tăng context switching. **newFixedThreadPool(n)** giới hạn số thread nhưng **queue mặc định không giới hạn**, cũng có thể dồn request vô tận. Production thường cần **giới hạn cả worker lẫn hàng đợi**.

## 6. Ví dụ tích hợp Java 17+ chạy được: hai HTTP request và executor riêng

Ví dụ **AsyncContinuationDemo.java** chạy hoàn toàn trên **127.0.0.1**:

1. Tạo một local HTTP server từ module **jdk.httpserver**, trả body **value-1** hoặc **value-2**. Server dùng **webServerPool** dành riêng cho test fixture.
2. Tạo **clientTasks** bốn thread và cấu hình qua **HttpClient.Builder.executor(clientTasks)**. Đây là executor phục vụ những tác vụ bất đồng bộ của client.
3. Tạo **businessPool** hai worker, queue tối đa 16 task, **AbortPolicy**. Đây là executor xử lý stage nghiệp vụ.
4. Gửi **hai request độc lập** bằng **HttpClient.sendAsync**.
5. Gắn **thenApplyAsync(..., businessPool)**, biến response body thành chữ in hoa. Mỗi callback **assert thread name bắt đầu bằng business-**, chứng minh công việc đã được giao tới pool mong muốn.
6. Ở **main thread của chương trình thử nghiệm**, đợi cả hai future bằng **allOf(...).get(timeout)**. Không có join/get trong I/O callback hay business stage.
7. Dùng finally để stop HTTP fixture và shutdown/awaitTermination ba executor. In kết quả chỉ sau khi xác minh.

Đây là một integration test thật, không phải giả lập output của sendAsync. Không cần Internet hoặc máy chủ ngoài; **j​​dk.httpserver** là module có trong JDK 17. Ví dụ không gọi phần mềm repo hay file người dùng.

### Tệp AsyncContinuationDemo.java

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncContinuationDemo {
    static ThreadFactory named(String prefix) {
        AtomicInteger sequence = new AtomicInteger();
        return task -> new Thread(
                task, prefix + "-" + sequence.incrementAndGet());
    }

    static CompletableFuture<String> fetch(
            HttpClient client, int port, int id,
            Executor businessPool, AtomicInteger checked) {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port +
                        "/item?id=" + id))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8))
                .thenApplyAsync(response -> {
                    if (!Thread.currentThread().getName()
                            .startsWith("business-")) {
                        throw new IllegalStateException(
                                "Continuation ran on unexpected executor");
                    }
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException("HTTP status");
                    }
                    checked.incrementAndGet();
                    return response.body()
                            .toUpperCase(Locale.ROOT);
                }, businessPool);
    }

    static void shutdown(ExecutorService pool)
            throws InterruptedException {
        pool.shutdown();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService webServerPool =
                Executors.newFixedThreadPool(
                        2, named("loopback-server"));
        ExecutorService clientTasks =
                Executors.newFixedThreadPool(
                        4, named("http-client"));
        ThreadPoolExecutor businessPool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(16),
                named("business"),
                new ThreadPoolExecutor.AbortPolicy());

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/item", exchange -> {
            try {
                String query =
                        exchange.getRequestURI().getRawQuery();
                if (!"id=1".equals(query) &&
                        !"id=2".equals(query)) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }

                byte[] bytes = ("value-" + query.substring(3))
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.getResponseHeaders().set(
                        "Connection", "close");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(webServerPool);

        try {
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .executor(clientTasks)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            AtomicInteger checked = new AtomicInteger();
            CompletableFuture<String> first = fetch(
                    client, server.getAddress().getPort(), 1,
                    businessPool, checked);
            CompletableFuture<String> second = fetch(
                    client, server.getAddress().getPort(), 2,
                    businessPool, checked);

            // Boundary của chương trình test, KHÔNG phải HTTP callback.
            CompletableFuture.allOf(first, second)
                    .get(10, TimeUnit.SECONDS);

            String value1 = first.join();
            String value2 = second.join();

            if (!"VALUE-1".equals(value1) ||
                    !"VALUE-2".equals(value2) ||
                    checked.get() != 2 ||
                    client.executor().orElseThrow() != clientTasks) {
                throw new AssertionError("Unexpected result");
            }

            System.out.println(
                    "Values: " + value1 + ", " + value2);
            System.out.println(
                    "Business callbacks verified: " +
                    (checked.get() == 2));
            System.out.println(
                    "Client executor configured: " +
                    client.executor().isPresent());
        } finally {
            server.stop(0);
            try {
                shutdown(businessPool);
            } finally {
                try {
                    shutdown(clientTasks);
                } finally {
                    shutdown(webServerPool);
                }
            }
        }

        if (!businessPool.isTerminated() ||
                !clientTasks.isTerminated() ||
                !webServerPool.isTerminated()) {
            throw new AssertionError("Executor leak");
        }
        System.out.println("Executor shutdown verified: true");
    }
}
~~~

### Biên dịch và chạy

Tạo file **AsyncContinuationDemo.java**, dùng **JDK 17+**. Do dùng local test server từ module jdk.httpserver, ghi rõ module trong lệnh:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 AsyncContinuationDemo.java
java --add-modules jdk.httpserver AsyncContinuationDemo
~~~

**Stdout chính xác của một lần PASS đã được biên dịch bằng --release 17 và chạy trên OpenJDK 24.0.2:**

~~~text
Values: VALUE-1, VALUE-2
Business callbacks verified: true
Client executor configured: true
Executor shutdown verified: true
~~~

**Giải thích vì sao stdout có thể ổn định:** thứ tự hoàn thành hai HTTP requests không được bảo đảm, nhưng chương trình giữ riêng future cho id=1 và id=2 rồi in theo **thứ tự id**; nó không in tên thread thực tế (có thể khác số thứ tự do scheduler). Thay vào đó, stage assert **thread-name prefix business-** rồi tăng biến đếm khi thành công. Bốn dòng PASS chỉ được in khi hai kết quả và các kiểm tra tương ứng đúng.

**Tại sao đoạn get/join trong main không mâu thuẫn với bài học?** Đây là ranh giới test CLI cần đợi kết quả để xác nhận. Nó **không chạy bên trong HTTP client completion thread**. Sau allOf.get(...) trả thành công, hai join() tiếp theo đã có kết quả, không còn đứng đợi network. Trong một HTTP server/event-loop thật, request handler nên **trả CompletionStage** hoặc tiếp tục bằng callback thay vì gọi get/join ngay.

**Vì sao code dùng HTTP/1.1?** Để local integration test thật đơn giản, không cần HTTPS certificate hay HTTP/2 server; mục đích kiểm chứng **executor/continuation**, không phải benchmark protocol. Quy tắc CompletableFuture và lựa chọn executor vẫn có ý nghĩa khi HttpClient xử lý HTTPS/HTTP2; không suy ra kết quả scheduling từ giao thức của ví dụ.

**Lưu ý về fixture:** newFixedThreadPool dành cho local server và client tasks giúp demo ngắn; chúng có unbounded queue. Trong production cần đo/tune capacity và backpressure cho load thực tế. **businessPool** ở ví dụ đã có queue hữu hạn và AbortPolicy. Nếu cần gửi hàng nghìn requests cùng lúc, cần thêm giới hạn requests in-flight (ví dụ Semaphore) và cơ chế xử lý rejection, không chỉ dựa vào queue=16.

## 7. Không chặn BodyHandler, BodySubscriber và thread xử lý dữ liệu

### 7.1. Body handler được gọi khi có response headers

**HttpResponse.BodyHandler.apply(ResponseInfo)** được gọi sau khi có status/headers nhưng **trước khi nhận toàn bộ body**. Nó chọn một **BodySubscriber**. BodySubscriber tiêu thụ các byte của response; subscriber có thể liên quan trực tiếp tới tiến độ pipeline HTTP.

Một handler hoặc subscriber có thể vô tình thực hiện I/O blocking trong callback:

~~~java
// Minh họa anti-pattern, KHÔNG dùng cho response streaming thực tế.
// Hàm parseHugeBody và dao.save là công việc nặng/blocking.
BodyHandler<Result> handler = info -> customBodySubscriber(
        bytes -> dao.save(parseHugeBody(bytes)));
~~~

Đoạn này là **pseudocode**, các tên Result/customBodySubscriber/dao không phải API có sẵn. Ý tưởng: nếu mapping của subscriber chạy lâu, thread được dùng để xử lý delivery có thể bị chiếm. Không được tự ý chặn **onNext**, **onSubscribe** hoặc mapping callback của client.

**Javadoc BodySubscribers.mapping(...)** còn cảnh báo mapper chạy bằng **client's executor** và blocking có thể làm pool thiếu thread. Với một InputStream lớn, nên map thành Supplier/đối tượng trì hoãn rồi thực hiện **thao tác blocking sau** trên executor phù hợp, thay vì đọc toàn stream ngay trong mapper. Đọc streaming phải đi kèm đóng stream và backpressure.

### 7.2. BodyHandlers.ofString không có nghĩa mọi response đều nên nằm trong RAM

BodyHandlers.ofString(...) nhận body thành String trước khi future response tương ứng hoàn tất. Thích hợp payload nhỏ. Với download lớn/stream dài, chọn BodyHandlers phù hợp (file, InputStream, publisher) và xử lý vòng đời rõ; **đừng đưa toàn bộ dữ liệu vào một String lớn rồi parse/block trong completion thread**.

Một số BodyHandler như ofInputStream có quy tắc hoàn tất future và ownership của stream riêng; cần **close InputStream** sau khi tiêu thụ, không bỏ quên socket/resource. Dùng custom subscriber cần tuân thủ Flow demand, cancellation, lỗi và giới hạn buffer.

### 7.3. Tránh block bằng async composition

Nếu một continuation muốn gọi HTTP request thứ hai, dùng **thenCompose** thay vì tự join. Nếu bước tiếp là CPU-heavy, dùng **thenComposeAsync(..., businessExecutor)** để chạy phần chuẩn bị trên pool. Nếu bước tiếp là JDBC blocking, chuyển sang executor cho JDBC, giới hạn theo JDBC pool.

**Không chỉ nhìn tên API chứa chữ Async để kết luận operation sẽ không block.** Một lambda có thể gọi Thread.sleep, JDBC, synchronized lock, file I/O, hoặc chờ Future.get; nếu chạy trên business executor thì thread của business executor vẫn bị giữ. Mục tiêu là ngăn chặn **starvation lan sang HTTP progress**, và thiết kế giới hạn phù hợp cho từng loại công việc.

## 8. Bounded queue, backpressure và chính sách rejection

Tách executor là bước đầu; nếu business chạy chậm hơn tốc độ HTTP responses hoàn tất, queue có thể tăng liên tục. Công thức trực giác:

~~~text
Tốc độ tạo continuation  >  tốc độ business pool xử lý
                    |
               Hàng đợi tăng
                    |
      latency tăng, memory bị giữ lâu, có thể OOM
~~~

Với pool hai thread và **ArrayBlockingQueue<>(16)**, số task **đang hoạt động + đang chờ** có trần theo khả năng của pool/queue tại thời điểm submit. Nhưng khi queue đầy, cần chính sách xử lý **thất bại có thể quan sát**.

### Các rejection policy

| Policy | Khi pool đầy | Phù hợp/rủi ro |
| --- | --- | --- |
| **AbortPolicy** | Ném RejectedExecutionException | Fail-fast, caller phải quan sát future exception/translate overload |
| **CallerRunsPolicy** | Chạy ngay trong thread submit task | Có thể giảm tốc producer, **nhưng rủi ro kéo business code về HTTP completion thread** |
| **DiscardPolicy** | Bỏ task âm thầm | Nguy hiểm với future: có thể không bao giờ được hoàn tất đúng kỳ vọng |
| **DiscardOldestPolicy** | Bỏ task chờ cũ và thử lại | Dễ làm mất request/correlation, cần chính sách hủy/telemetry mạnh |

Đối với HTTP pipeline, **AbortPolicy + giới hạn in-flight + trả lỗi overload rõ ràng** thường dễ kiểm soát hơn CallerRunsPolicy nếu mục tiêu chính là không chặn completion threads. Nhưng không có policy nào tự tạo backpressure trên toàn hệ thống: cần **đặt trần requests in-flight** trước khi gọi sendAsync và giải phóng permit khi request + business continuation kết thúc.

### Semaphore cho giới hạn in-flight (snippet)

~~~java
// Minh họa cho tầng nhận request; permit chỉ được acquire ở nơi
// được phép chờ hoặc dùng tryAcquire để fail fast.
Semaphore permits = new Semaphore(50);

if (!permits.tryAcquire()) {
    // Từ chối/queue ở lớp ứng dụng theo quy định overload.
} else {
    client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
          .thenApplyAsync(resp -> transform(resp.body()), businessExecutor)
          .whenComplete((value, error) -> permits.release());
}
~~~

Các biến request, businessExecutor, transform được định nghĩa ở ứng dụng; đây không phải file độc lập. Callback release cần **cực ngắn**, không làm công việc blocking; **whenComplete** ở đây chỉ release permit và không cản trở I/O đáng kể. Nếu trước khi tạo future có exception synchronous, phải có nhánh release riêng. Không cấp phép vô hạn hoặc giữ permit khi callback bị bỏ.

**Quan trọng về hai loại trần:** in-flight requests giới hạn số HTTP operations đang sống; bounded executor queue giới hạn business continuations đang chờ. Chúng giải quyết những phần khác nhau, nên cần cả hai nếu hệ thống dễ overload.

## 9. Xử lý exception, timeout và hủy đúng cách

### 9.1. Quan sát cả network failure lẫn business failure

~~~java
// Snippet: đặt business logic trên executor explicit.
CompletableFuture<Result> pipeline =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .thenApplyAsync(resp -> parseAndValidate(resp),
                              businessExecutor);

pipeline.whenComplete((result, error) -> {
    if (error != null) {
        recordFailure(error); // Nên nhanh và non-blocking.
    }
});
~~~

Các định danh Result, parseAndValidate, recordFailure là code ứng dụng minh họa. Nếu lỗi HTTP/TLS/timeout xảy ra trước stage xử lý, **thenApplyAsync không chạy**, và pipeline hoàn tất lỗi. Nếu business callback ném RuntimeException, pipeline cũng lỗi. Khi cần hồi phục có chủ đích, có thể dùng **exceptionally**, **handleAsync** hoặc **exceptionallyCompose** (Java 12+), nhưng không được vô tình nuốt lỗi rồi báo thành công.

**CompletionException** thường bao nguyên nhân thực. Với **get()**, caller nhận **ExecutionException** khi future lỗi; với **join()**, caller thường nhận CompletionException. Log nguyên nhân/correlation ID mà không lộ token/cookie.

### 9.2. Timeout có nhiều lớp

- **HttpClient.Builder.connectTimeout(...)**: timeout thiết lập kết nối.
- **HttpRequest.Builder.timeout(...)**: timeout request theo hợp đồng HttpClient, có thể dẫn đến **HttpTimeoutException**.
- **CompletableFuture.orTimeout(...)**: hoàn tất future lỗi sau deadline nếu chưa xong; **không đảm bảo** mọi hoạt động I/O hoặc business task nền bị dừng ngay.
- **get(timeout, unit)**: giới hạn thời gian **thread caller chờ**, không tự đồng nghĩa request đã bị cancel ở server.
- **Deadline nghiệp vụ**: thường cần thời gian tổng cho network + parse + database + downstream.

Không nên dùng **orTimeout(5s)** rồi tin rằng CPU-heavy callback hoặc JDBC đã bị interrupt. Cơ chế cancellation trên CompletableFuture và HTTP client có những quy tắc riêng; muốn giải phóng tài nguyên sớm cần thiết kế cancellation/deadline ở từng tầng.

### 9.3. Retry không phải cứ lỗi là gửi lại

Khi async request lỗi, retry có thể làm tăng tải đúng lúc business pool hoặc server đang quá tải. Chỉ retry với request có tính idempotent/theo hợp đồng; giới hạn attempts, backoff/jitter và tổng deadline. Nếu cần delay, dùng **ScheduledExecutorService** hoặc cơ chế scheduling thích hợp, **không Thread.sleep trong completion callback**.

### 9.4. Dọn executor theo vòng đời Java 17

Trong Java 17, **ExecutorService không dùng try-with-resources như một AutoCloseable phổ quát**; cần shutdown và awaitTermination. **HttpClient của Java 17 cũng không phải một AutoCloseable để bao trong try-with-resources như các bản JDK mới**. Nên tạo một HttpClient dùng lại, quản lý executor custom theo application lifecycle.

~~~java
// Minh họa shutdown; nếu đặt trong finally thì cần bảo đảm
// vẫn xử lý InterruptedException và dọn tài nguyên còn lại.
pool.shutdown();
if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
    pool.shutdownNow();
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new IllegalStateException("Pool did not terminate");
    }
}
~~~

**shutdownNow() chỉ yêu cầu ngắt worker, không chắc chấm dứt mọi block ngay**. Không shutdown business executor khi các continuation của các request còn sống chưa được lập lịch, vì những stage đó có thể bị rejected. Trình tự thường là ngừng nhận request mới, xử lý/cancel in-flight, đợi các stage cần thiết, rồi shutdown executor theo ownership.

## 10. Đo đạc và chẩn đoán thread starvation

Đừng chỉ thấy CPU cao rồi kết luận HttpClient lỗi. Cần có bằng chứng từ thread dumps, timers và queue.

| Chỉ số / quan sát | Diễn giải khả dĩ |
| --- | --- |
| **HTTP request latency** tăng | Network, server, DNS/proxy hoặc client executor thiếu năng lực |
| **Network response nhận nhanh nhưng business stage chậm** | Business pool bão hòa, queue delay hoặc callback nặng |
| **businessPool.getActiveCount()** gần tối đa lâu | Worker thường xuyên bận |
| **businessPool.getQueue().size()** tăng | Producer nhanh hơn consumer; nguy cơ latency/memory |
| **businessPool.getCompletedTaskCount()** không tăng | Task có thể đang block, deadlock hoặc không tiến triển |
| **RejectedExecutionException** tăng | Queue/worker đã đầy, cần throttle/backpressure |
| **Thread dump: http-client-* bị block ở JDBC/lock** | Có khả năng business logic đang chạy trên executor không phù hợp |
| **ForkJoinPool.commonPool-worker-* bận với business** | Có thể có thenApplyAsync không truyền executor |
| **Connection leak / file descriptor tăng** | Cần kiểm tra BodySubscriber/InputStream, cancellation, response lifecycle |

**Giới hạn của metrics:** getActiveCount, getQueue().size và getCompletedTaskCount là snapshot gần đúng trong hệ thống đang chạy; không dùng chúng như invariant tuyệt đối tại mọi thời điểm. Nên đo percentiles p50/p95/p99 latency, số in-flight, queue wait time, throughput và rejection rate qua nhiều đợt tải.

### Bài test để phát hiện blocking callback

Một kịch bản load test hữu ích:

1. Dùng local test server có thể trả response nhỏ ở mức concurrency nhất định.
2. Đặt callback biến đổi mất nhiều thời gian trên business executor, nhưng không để HttpClient executor chạy callback đó.
3. Đo response progress, business queue, complete time và timeout. Nếu tách pool đúng, một callback nghiệp vụ chậm **không trực tiếp chiếm** thread được dùng cho HTTP progress.
4. Tăng tải tới ngưỡng bounded queue; xác minh overload được báo rõ và không có request treo vô hạn.
5. Shutdown; xác minh thread pool terminated, in-flight về 0 và không có tài nguyên bị bỏ quên.

Không dựa vào **Thread.sleep(100)** để chứng minh thread nào chạy callback. Ví dụ Java ở phần 6 kiểm tra tên thread **ngay bên trong stage**, cho kết quả kiểm chứng cụ thể thay vì đoán từ lịch chạy.

## 11. Checklist áp dụng vào dự án

1. Xác định rõ **HttpClient executor** và **executor nghiệp vụ**, không gộp tùy tiện khi business tasks có blocking/CPU nặng.
2. Nhớ **thenApply/whenComplete không Async** có thể chạy trên completing/calling thread.
3. Dùng **thenApplyAsync(..., explicitExecutor)** cho công việc nặng cần kiểm soát pool.
4. Dùng **thenCompose** cho chuỗi các API đã trả future thay vì gọi join/get ở giữa.
5. Dùng **thenComposeAsync** nếu việc chuẩn bị request/downstream stage có công việc nặng.
6. Không đặt blocking JDBC, parse nặng hoặc sleep trong **BodyHandler/BodySubscriber mapping callbacks**.
7. Chọn CPU pool theo số lõi và blocking pool theo concurrency/connection limits.
8. Giới hạn **worker threads, task queue và HTTP requests in-flight**; có overload policy có thể quan sát.
9. Cảnh giác **CallerRunsPolicy** vì có thể đưa công việc nặng về lại completion thread.
10. Có timeout/cancellation theo từng tầng; không tin get(timeout) sẽ tự dừng background work.
11. Khi shutdown, đợi stage đang xử lý kết thúc rồi dọn executor; Java17 không dùng try-with-resources cho HttpClient.
12. Đo thread dump, queue wait, active count, response latency, completed tasks, rejection và cleanup.
13. Kiểm thử exception từ HTTP và business callback để bảo đảm pipeline trả lỗi đúng.
14. Không giả định async luôn nhanh hơn sync; hiệu năng phụ thuộc tải, pool sizing, deadline và backpressure.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** sendAsync trả CompletableFuture thì callback thenApply có chắc chạy trên thread của business pool không?  
**Trả lời:** Không. thenApply không có executor explicit; nó có thể chạy trên completing/calling thread tùy thời điểm completion.

**Câu 2.** thenApplyAsync(fn) không truyền executor sẽ chạy trên pool do HttpClient.Builder.executor chọn?  
**Trả lời:** Không thể mặc định như vậy. Nó dùng default asynchronous execution facility của CompletableFuture; với CompletableFuture thông thường thường là commonPool. Muốn chọn rõ dùng thenApplyAsync(fn, businessExecutor).

**Câu 3.** Vì sao không gọi dao.findById(...) ngay trong thenApply của HTTP future?  
**Trả lời:** DAO blocking có thể chiếm completion thread, làm chậm tiến độ các tác vụ HTTP bất đồng bộ khác. Đặt JDBC ở blocking executor phù hợp.

**Câu 4.** CompletableFuture.allOf(...).get(...) trong demo có sai không?  
**Trả lời:** Không, vì đó là ranh giới chương trình test CLI đứng đợi kết quả. Tránh gọi get/join trong event-loop thread hoặc callback cần giữ non-blocking.

**Câu 5.** thenCompose giúp gì so với thenApply kết hợp join?  
**Trả lời:** Nó flatten một CompletionStage được trả về từ function, nối hai thao tác async mà không giữ một thread chờ Future tiếp theo.

**Câu 6.** Tại sao CallerRunsPolicy có thể phản tác dụng?  
**Trả lời:** Khi pool full, nó chạy rejected task trong thread submit; thread đó có thể đang xử lý HTTP completion, khiến business work chặn đường xử lý I/O.

**Câu 7.** newFixedThreadPool(4) có tự tạo bounded queue không?  
**Trả lời:** Không. Mặc định queue của newFixedThreadPool là unbounded, nên cần thiết kế bounded queue/backpressure nếu tải cao.

**Câu 8.** Một callback đã đăng ký thenApplyAsync nhưng business executor shutdown thì sao?  
**Trả lời:** Scheduling có thể bị reject và pipeline lỗi; phải quản lý lifecycle, tránh shutdown trước khi các in-flight stages hoàn tất.

**Câu 9.** BodySubscribers.mapping chạy ở đâu và có được đọc InputStream blocking lâu không?  
**Trả lời:** Mapper chạy bằng client executor theo tài liệu JDK17; việc đọc blocking lâu có thể gây starvation. Đưa việc đọc/parse nặng sang nơi phù hợp và đóng stream.

**Câu 10.** orTimeout(...) có chắc interrupt cả HTTP request và JDBC đang chờ?  
**Trả lời:** Không. Nó ảnh hưởng trạng thái future sau deadline; xử lý hủy hoạt động nền tùy tầng cần thiết kế riêng.

**Câu 11.** Vì sao demo có ba executor?  
**Trả lời:** webServerPool phục vụ fixture HTTP loopback; clientTasks là executor của HttpClient; businessPool chạy explicit continuation. Việc tách rõ cho thấy continuation không dựa vào thread của HttpClient.

**Câu 12.** Khi nào dùng whenComplete thay handle?  
**Trả lời:** whenComplete chủ yếu quan sát result/error và giữ outcome gốc; handle có thể biến outcome thành giá trị khác. Với callback nặng, dùng biến thể Async và explicit executor.

## Kết luận

Với HTTP bất đồng bộ Java 17, **sendAsync** chỉ giải quyết khía cạnh gửi request không chặn caller; **công việc tiếp nối vẫn cần được thiết kế và đặt lịch đúng**. Một stage không Async có thể chạy trên thread hoàn tất request. Một stage Async không truyền executor dùng default asynchronous facility, không phải mặc định business executor. **thenApplyAsync(..., businessExecutor)** và **thenCompose(...)** là hai công cụ then chốt để vừa giữ I/O progress, vừa xử lý nghiệp vụ có giới hạn.

Để tránh chỉ chuyển nghẽn từ thread I/O sang một queue khác, cần **bounded executor, in-flight limit, overload policy, deadline, kiểm soát cancellation và cleanup**. Đo thực tế, không suy diễn từ tên phương thức hay số lượng thread.

### Tài liệu tham khảo chính thức

- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): executor(...) và default executor.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): sendAsync, executor() và client lifecycle.
- [Java SE 17 — java.net.http package](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/package-summary.html): callback scheduling và dependent tasks.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): non-async/async policies, thenApplyAsync, thenCompose, completion errors.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): composition và handling.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue bounds, sizing và rejection.
- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded task queue.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): mapping và blocking mapper caveat.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): xử lý response body.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local loopback server trong integration test.
