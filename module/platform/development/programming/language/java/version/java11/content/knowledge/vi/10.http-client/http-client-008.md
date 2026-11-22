# Gửi HTTP bất đồng bộ bằng HttpClient.sendAsync trong Java 11

## Mục tiêu bài học

Ứng dụng gọi REST API hoặc nhiều dịch vụ HTTP có thể cần chờ mạng trong khi vẫn tiếp tục xử lý công việc khác. Từ **Java 11**, module chuẩn **`java.net.http`** cung cấp `HttpClient` với phương thức `sendAsync(...)`: gửi yêu cầu và trả về một `CompletableFuture` để chương trình đăng ký các bước tiếp theo thay vì chặn luồng gọi như `send(...)`.

Bài này tập trung vào **`sendAsync`** và các thao tác thực tế khi nhận phản hồi, xử lý lỗi và ghép tác vụ. Sau bài học, bạn có thể:

1. Tạo, gửi yêu cầu **GET/POST bất đồng bộ** bằng API `HttpClient` hiện hành.
2. Hiểu kiểu `CompletableFuture<HttpResponse<T>>`, vai trò `BodyHandler<T>` và dữ liệu phản hồi `statusCode()`, `headers()`, `body()`.
3. Dùng `thenApply`, `thenCompose`, `thenCombine` / `allOf`, `whenComplete` và `exceptionally` đúng mục đích; phân biệt bước xử lý không chặn và bước thực sự chờ kết quả.
4. Xử lý **HTTP 4xx/5xx**, lỗi I/O, timeout, cancellation và vòng đời executor mà không nhầm chúng là một loại lỗi.
5. Kiểm thử một chuỗi HTTP thực trên **server loopback**, gồm nội dung Unicode, POST, 404, xử lý song song, chuỗi phụ thuộc và phản hồi bị trì hoãn; không phụ thuộc Internet hay dịch vụ bên ngoài.
6. Áp dụng những API còn được hỗ trợ, tránh mã incubator HTTP Client trước Java 11 và không vô tình dùng phương thức mới hơn baseline Java 11.

## 1. Từ `send` đồng bộ đến `sendAsync` bất đồng bộ

### 1.1. Luồng xử lý đồng bộ

Với API HTTP Client chính thức:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
~~~

`send(...)` **chặn luồng gọi** trong thời gian cần để nhận phản hồi và phần body theo `BodyHandler`. Nó trả trực tiếp `HttpResponse<String>` và có thể ném `IOException` hoặc `InterruptedException`. Đoạn trên chỉ minh họa sau khi đã tạo `client` và `request`.

Dùng `send` là hợp lý ở tác vụ command-line tuần tự hoặc những đoạn code đã có thiết kế chặn rõ ràng, nhưng không phù hợp nếu luồng gọi cần tiếp tục xử lý nhiều yêu cầu hoặc phải duy trì tính đáp ứng của UI/event loop.

### 1.2. Luồng xử lý bất đồng bộ

Cú pháp `sendAsync`:

~~~java
public abstract <T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
~~~

Ví dụ:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenApply(HttpResponse::body)
      .thenAccept(System.out::println);
~~~

`sendAsync` trả về **ngay một đối tượng future**, không cần đợi server trả nội dung. Khi request được hoàn tất thành công, future chứa `HttpResponse<T>`; nếu tác vụ gửi/nhận xảy ra lỗi, future được **complete exceptionally**. Các hàm `thenApply`/`thenAccept` đăng ký bước xử lý để thực hiện sau khi future sẵn sàng.

**Lưu ý:** `sendAsync` là bất đồng bộ, nhưng gọi `future.join()` hoặc `future.get()` ở ngay luồng hiện tại vẫn **chặn luồng đó đến khi có kết quả**. Ta chỉ nên chờ ở ranh giới thật sự cần, chẳng hạn cuối một chương trình kiểm thử/CLI. Trong server/UI không nên gọi `join` ngay sau `sendAsync` rồi nghĩ rằng toàn bộ chuỗi vẫn non-blocking.

### 1.3. Những thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| `HttpClient` | Client dùng lại cho nhiều request; cấu hình redirect, phiên bản HTTP ưu tiên, connect timeout, executor... |
| `HttpRequest` | Request được dựng bằng builder; chứa URI, method, headers, request body, timeout riêng. |
| `HttpRequest.BodyPublishers` | Chuyển dữ liệu ứng dụng thành body gửi, ví dụ `ofString(text, UTF_8)` hoặc `noBody()`. |
| `HttpResponse.BodyHandlers` | Quy định cách tiêu thụ body phản hồi, như `ofString(UTF_8)`, `ofByteArray()`, `ofFile(...)`, `discarding()`. |
| `HttpResponse<T>` | Đưa ra `statusCode()`, `headers()`, `body()` và request tương ứng. |
| `CompletableFuture<HttpResponse<T>>` | Đại diện cho phản hồi sẽ có trong tương lai hoặc kết quả lỗi bất đồng bộ. |
| `CompletionStage` | Các phép ghép tác vụ kế tiếp, không nhất thiết thực hiện trong luồng gọi. |

`HttpClient` được tạo bằng `HttpClient.newHttpClient()` hoặc `HttpClient.newBuilder().build()`; sau khi tạo nó là đối tượng cấu hình bất biến và có thể **tái sử dụng cho nhiều request**. Không cần tạo một client mới cho từng URL; việc tái sử dụng giúp tận dụng tài nguyên và connection reuse.

## 2. Tạo request và gửi `sendAsync` đúng chuẩn

### 2.1. Client và request GET

~~~java
// Đoạn minh họa: đặt trong phương thức hoặc class đã có import.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/status"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Hai timeout **khác nhau**:

- `HttpClient.Builder.connectTimeout`: giới hạn thời gian **thiết lập kết nối mới**; nếu connection đang được tái sử dụng thì timeout này không có tác dụng. Khi lỗi kết nối quá thời hạn, `sendAsync` complete exceptionally với `HttpConnectTimeoutException`.
- `HttpRequest.Builder.timeout`: thời hạn áp dụng cho **request HTTP** theo hợp đồng Javadoc; khi không nhận response trong thời hạn đó, `sendAsync` complete exceptionally với `HttpTimeoutException`.

Nên cấu hình timeout hữu hạn theo yêu cầu ứng dụng, thay vì giả định mọi server luôn trả lời. `followRedirects(NORMAL)` là ví dụ chính sách; với hệ thống cần kiểm soát redirect hoặc chuyển tiếp thông tin xác thực, lựa chọn policy riêng và kiểm tra đích. Trong bài kiểm thử cục bộ, chúng ta dùng `Redirect.NEVER` để kết quả rõ ràng.

Để gửi request body bằng POST:

~~~java
HttpRequest post = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/messages"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8))
        .build();

CompletableFuture<HttpResponse<String>> sent =
        client.sendAsync(post,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Đây là đoạn minh họa **không tự chạy độc lập** và chỉ cho thấy cách xây dựng POST, không phải lời khuyên gửi dữ liệu đến một URL thực trong bài tập. Với API JSON, thay `Content-Type`/dữ liệu tương ứng và dùng thư viện JSON khi cần; `BodyPublishers.ofString` tự nó **không serialize object thành JSON**.

### 2.2. `BodyHandler<T>` quyết định kiểu `T`

~~~java
CompletableFuture<HttpResponse<String>> textFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<byte[]>> bytesFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<HttpResponse<Void>> ignoredFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
~~~

`BodyHandlers.ofString(StandardCharsets.UTF_8)` là lựa chọn rõ ràng khi API trả về văn bản UTF-8. Overload `ofString()` không truyền charset có thể xác định charset từ header `Content-Type` và fallback UTF-8 theo Javadoc; khi giao thức đã có charset cố định, truyền rõ giúp giảm nhầm lẫn. `ofByteArray()` trả bytes, hữu ích với dữ liệu nhị phân hoặc khi cần tự giải mã.

Các handler như `ofFile(Path)` và `ofInputStream()` cũng được hỗ trợ. **Cẩn thận:** với `ofInputStream()`, future có thể complete trước khi toàn bộ nội dung đã được tiêu thụ; ứng dụng có trách nhiệm đọc/đóng stream để giải phóng tài nguyên. Không suy ra rằng mọi `sendAsync` hoàn tất đồng nghĩa mọi stream dữ liệu đều được đọc hết.

## 3. Compose với CompletableFuture thay vì chặn

### 3.1. `thenApply`: biến đổi giá trị đã có

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApply(response -> {
                  if (response.statusCode() != 200) {
                      throw new IllegalStateException(
                              "HTTP " + response.statusCode());
                  }
                  return response.body();
              });
~~~

`thenApply` biến `HttpResponse<String>` thành `String`, **không** tự phát sinh HTTP request thứ hai. Nếu lambda ném ngoại lệ, stage phụ thuộc được complete exceptionally.

### 3.2. `thenCompose`: một request phụ thuộc kết quả request trước

~~~java
CompletableFuture<HttpResponse<String>> secondFuture =
        client.sendAsync(firstRequest, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8))
              .thenCompose(firstResponse -> {
                  // Chỉ xây dựng/gửi request thứ hai sau khi phản hồi đầu đã tới.
                  return client.sendAsync(secondRequest,
                          HttpResponse.BodyHandlers.ofString(
                                  StandardCharsets.UTF_8));
              });
~~~

Đoạn này giả định `client`, `firstRequest`, `secondRequest` đã được tạo. `thenCompose` **làm phẳng future lồng nhau**: bạn nhận `CompletableFuture<HttpResponse<String>>`, không phải `CompletableFuture<CompletableFuture<HttpResponse<String>>>`.

Nếu dùng `thenApply` với một lambda trả về future khác, kết quả thường là future **lồng nhau**, khó xử lý và dễ nhầm tình trạng hoàn tất. Dùng `thenCompose` cho chuỗi HTTP phụ thuộc; kiểm status và tạo request kế tiếp theo dữ liệu thật từ phản hồi trước nếu nghiệp vụ cần.

### 3.3. `allOf` / `thenCombine`: yêu cầu độc lập

Khi hai request **không phụ thuộc** nhau, có thể khởi động cả hai rồi chờ tổng hợp:

~~~java
CompletableFuture<HttpResponse<String>> a =
        client.sendAsync(firstRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
CompletableFuture<HttpResponse<String>> b =
        client.sendAsync(secondRequest,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

CompletableFuture<Void> both = CompletableFuture.allOf(a, b);
~~~

`allOf` hoàn tất khi **tất cả** future đầu vào đã hoàn tất; nếu một future lỗi, future tổng hợp cũng có thể hoàn tất theo trạng thái lỗi. `allOf` có kiểu `Void`, nên để lấy dữ liệu của từng request sau khi tổng hợp, dùng `a.join()` và `b.join()` **sau** khi `both` hoàn thành thành công. Đừng nhầm `allOf` tự tạo danh sách response.

`thenCombine` phù hợp khi muốn kết hợp kết quả của hai future thành một giá trị:

~~~java
CompletableFuture<String> combined =
        a.thenCombine(b,
                (left, right) -> left.body() + " | " + right.body());
~~~

Cả hai cách đều cho phép các request tiến triển độc lập. Không bảo đảm server thực sự xử lý song song ở mọi tình huống, không dựa vào thứ tự callback hoặc thời điểm phản hồi để xác nhận tính đúng.

### 3.4. `whenComplete`, `exceptionally` và `handle`

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `thenApply(value -> ...)` | Biến đổi giá trị khi thành công. | Lambda có lỗi thì stage tiếp theo lỗi. |
| `thenAccept(value -> ...)` | Xử lý giá trị mà không trả kết quả có nghĩa. | Trả `CompletableFuture<Void>`. |
| `thenCompose(value -> future)` | Chạy tác vụ phụ thuộc và làm phẳng kết quả. | Dùng cho request tiếp theo. |
| `whenComplete((value, error) -> ...)` | Quan sát kết quả/thất bại, thường để logging hoặc metrics. | Không mặc định chuyển exception thành success. |
| `exceptionally(error -> fallback)` | Phục hồi lỗi bằng một giá trị thay thế. | Có thể che mất lỗi nghiêm trọng nếu dùng quá rộng. |
| `handle((value, error) -> ...)` | Tạo giá trị mới cho cả hai nhánh success/failure. | Cần chủ động phân biệt `error == null`. |
| `orTimeout(duration, unit)` | Hoàn tất future bằng lỗi timeout nếu chưa hoàn tất đúng hạn. | Không tự chứng minh remote server đã dừng xử lý request. |

Các dạng không có hậu tố `Async`, như `thenApply`, có thể chạy trong luồng hoàn tất giai đoạn trước hoặc luồng đang đăng ký handler nếu kết quả đã sẵn. **Không được giả định callback luôn chạy trên một luồng cố định**. Nếu cần dùng executor riêng cho công việc CPU nặng hoặc blocking, cân nhắc `thenApplyAsync(..., executor)` với executor được quản lý rõ vòng đời.

## 4. Chương trình thực hành độc lập, dùng HTTP server cục bộ

Ví dụ dưới đây kiểm tra **HTTP request thật** nhưng không phụ thuộc mạng ngoài. Nó dùng `HttpServer` của module JDK `jdk.httpserver` chỉ để cung cấp test server trên loopback `127.0.0.1`; phần client sử dụng `java.net.http.HttpClient` của Java 11. `jdk.httpserver` là module đi kèm JDK, không phải thư viện HTTP Client bên thứ ba. Vì chương trình test import `com.sun.net.httpserver.HttpServer`, lệnh biên dịch và chạy sẽ khai báo module này tường minh.

**Các case được kiểm:**

1. GET trả text Unicode và stage `whenComplete` chạy thành công.
2. POST body UTF-8 được server nhận và echo đúng.
3. HTTP **404 là một response bình thường về tầng giao vận**, không tự trở thành exceptional future.
4. `thenCompose` gửi request thứ hai sau request đầu.
5. `CompletableFuture.allOf` tập hợp hai request khởi động độc lập.
6. Tầng ứng dụng chuyển HTTP status xấu thành ngoại lệ rồi phục hồi với `exceptionally`.
7. Server giữ response bằng `CountDownLatch`: xác nhận `sendAsync` đã trả future **trước khi** response sẵn, sau đó cho phép response hoàn tất.

Tạo file **SendAsyncDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class SendAsyncDemo {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    private static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static HttpRequest get(URI base, String endpoint) {
        return HttpRequest.newBuilder(base.resolve(endpoint))
                .timeout(Duration.ofSeconds(6))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        String vietnamese = "Ti\u1EBFng Vi\u1EC7t "
                + new String(Character.toChars(0x1F642));
        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch allowResponse = new CountDownLatch(1);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverThreads = Executors.newFixedThreadPool(4);
        server.setExecutor(serverThreads);

        server.createContext("/hello", ex -> reply(ex, 200, vietnamese));
        server.createContext("/next", ex -> reply(ex, 200, "next"));
        server.createContext("/missing", ex -> reply(ex, 404, "not found"));
        server.createContext("/echo", ex -> {
            String body = new String(ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(ex, "POST".equals(ex.getRequestMethod()) ? 200 : 405,
                    "echo:" + body);
        });
        server.createContext("/hold", ex -> {
            handlerStarted.countDown();
            try {
                if (!allowResponse.await(5, TimeUnit.SECONDS)) {
                    reply(ex, 503, "too slow");
                    return;
                }
                reply(ex, 200, "released");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                reply(ex, 503, "interrupted");
            }
        });

        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            AtomicBoolean callbackSawSuccess = new AtomicBoolean(false);
            CompletableFuture<String> greeting = client
                    .sendAsync(get(base, "/hello"),
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                    .thenApply(response -> {
                        check(response.statusCode() == 200, "GET status");
                        return response.body();
                    })
                    .whenComplete((body, failure) -> {
                        if (failure == null && vietnamese.equals(body)) {
                            callbackSawSuccess.set(true);
                        }
                    });
            check(vietnamese.equals(greeting.join()), "GET UTF-8 body");
            check(callbackSawSuccess.get(), "whenComplete callback");
            System.out.println("PASS GET Unicode pipeline");

            HttpRequest post = HttpRequest.newBuilder(base.resolve("/echo"))
                    .timeout(Duration.ofSeconds(6))
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            vietnamese, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> posted = client.sendAsync(post,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).join();
            check(posted.statusCode() == 200, "POST status");
            check(("echo:" + vietnamese).equals(posted.body()),
                    "POST UTF-8 echo");
            System.out.println("PASS POST request body");

            HttpResponse<String> missing = client.sendAsync(
                    get(base, "/missing"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)).join();
            check(missing.statusCode() == 404
                    && "not found".equals(missing.body()),
                    "HTTP 404 is a completed response");
            System.out.println("PASS HTTP 404 is response");

            CompletableFuture<String> chained = client.sendAsync(
                    get(base, "/hello"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .thenCompose(response -> {
                        check(response.statusCode() == 200,
                                "first request status");
                        return client.sendAsync(get(base, "/next"),
                                HttpResponse.BodyHandlers.ofString(
                                        StandardCharsets.UTF_8));
                    })
                    .thenApply(HttpResponse::body);
            check("next".equals(chained.join()), "thenCompose chain");
            System.out.println("PASS thenCompose");

            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    get(base, "/hello"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            CompletableFuture<HttpResponse<String>> second = client.sendAsync(
                    get(base, "/next"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            CompletableFuture.allOf(first, second).join();
            check(vietnamese.equals(first.join().body())
                    && "next".equals(second.join().body()),
                    "allOf results");
            System.out.println("PASS allOf parallel");

            String recovered = client.sendAsync(get(base, "/missing"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .thenApply(response -> {
                        if (response.statusCode() >= 400) {
                            throw new IllegalStateException(
                                    "HTTP " + response.statusCode());
                        }
                        return response.body();
                    })
                    .exceptionally(failure -> "fallback")
                    .join();
            check("fallback".equals(recovered), "application error mapping");
            System.out.println("PASS status error recovery");

            CompletableFuture<HttpResponse<String>> held = client.sendAsync(
                    get(base, "/hold"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            try {
                check(handlerStarted.await(3, TimeUnit.SECONDS),
                        "server must enter deferred handler");
                check(!held.isDone(),
                        "sendAsync must return before body is available");
            } finally {
                allowResponse.countDown();
            }
            check("released".equals(held.orTimeout(5, TimeUnit.SECONDS)
                    .join().body()), "released response body");
            System.out.println("PASS asynchronous completion");
            System.out.println("ALL SENDASYNC TESTS PASSED");
        } finally {
            allowResponse.countDown();
            server.stop(0);
            serverThreads.shutdownNow();
        }
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 11** hoặc JDK mới hơn có thể biên dịch target Java 11. Trong thư mục chứa file nguồn:

~~~bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 SendAsyncDemo.java
java --add-modules jdk.httpserver -cp . SendAsyncDemo
~~~

Đầu ra của chương trình khi chạy thành công:

~~~text
PASS GET Unicode pipeline
PASS POST request body
PASS HTTP 404 is response
PASS thenCompose
PASS allOf parallel
PASS status error recovery
PASS asynchronous completion
ALL SENDASYNC TESTS PASSED
~~~

Chương trình sử dụng cổng loopback tự cấp (port 0) để giảm xung đột với ứng dụng khác; không gọi API công khai ngoài Internet. `CountDownLatch` đảm bảo test `/hold` không dựa trên phỏng đoán thời gian response: handler phải báo đã bắt đầu nhưng chưa được phép trả lời, lúc đó `held.isDone()` phải là `false`; sau khi thả latch, future trả response `released`. Các giá trị timeout chỉ để test không treo mãi nếu có lỗi môi trường.

Lệnh `javac --release 11` xác nhận cú pháp và API nằm trong phạm vi Java 11. `jdk.httpserver` là module **phụ trợ làm server cho test**, không phải yêu cầu cài thêm thư viện để **dùng `HttpClient.sendAsync`** ở ứng dụng thật. Việc gọi `.join()` sau mỗi giai đoạn trong chương trình **test** nhằm chờ và kiểm kết quả có trật tự để in stdout xác định; các yêu cầu HTTP được gửi bằng `sendAsync`.

## 5. Xử lý lỗi: HTTP status khác exception

### 5.1. HTTP 404/500 không tự làm future thất bại

`BodyHandlers.ofString(...)` nhận response body ngay cả khi status là 404 hoặc 500; bản thân `sendAsync` có thể hoàn thành **thành công về mặt giao vận** với một `HttpResponse` có `statusCode() == 404`. Đây không phải là kết quả thành công về nghiệp vụ.

Mẫu kiểm tra rõ ràng:

~~~java
CompletableFuture<String> result =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApply(response -> {
                  int status = response.statusCode();
                  if (status < 200 || status >= 300) {
                      throw new IllegalStateException("HTTP " + status);
                  }
                  return response.body();
              });
~~~

Hàm `thenApply` chuyển HTTP status không nằm trong nhóm 2xx thành **ngoại lệ ứng dụng**; stage sau đó complete exceptionally. Mã thực tế cần chọn loại exception có ngữ nghĩa, chính sách retry, và cách lưu thông tin status/body phù hợp, không chỉ dùng `IllegalStateException` cho mọi nghiệp vụ.

### 5.2. Lỗi giao vận và unwrap CompletableFuture

Nếu lỗi I/O, timeout, DNS hoặc kết nối xảy ra, future có thể hoàn tất bằng ngoại lệ, thường có `IOException` hoặc ngoại lệ chuyên biệt trong nguyên nhân. Các trường hợp như request không hợp lệ có thể phát sinh ngoại lệ **ngay lúc gọi API** (ví dụ `IllegalArgumentException` theo hợp đồng `sendAsync`), khác với lỗi khi tác vụ đang chạy.

- `future.join()` chờ và ném `CompletionException` nếu stage hoàn tất lỗi; xem `getCause()` để hiểu nguyên nhân.
- `future.get()` chờ và sử dụng `ExecutionException` khi stage lỗi; có thể ném `InterruptedException` vì luồng đang chờ bị ngắt.
- `whenComplete((response, error) -> ...)` ghi nhận outcome và thường để **giữ nguyên outcome**. Nếu callback tự ném lỗi, cũng cần xử lý.
- `exceptionally(error -> fallback)` là **phục hồi bằng giá trị**. Không dùng fallback chung để biến mọi lỗi mạng, lỗi parse hoặc bug code thành một response có vẻ hợp lệ.
- `handle((value, error) -> ...)` dùng khi cần chuyển cả hai nhánh thành một kết quả có kiểu nhất quán.

Nếu hệ thống cần trả ra kết quả dạng `Result<Success, Failure>`, nên mô hình hóa trạng thái và error code rõ ràng thay vì chỉ log rồi nuốt mọi exception.

### 5.3. Timeout: giới hạn thời gian không đồng nghĩa giao dịch bị rollback

Có ba phạm vi cần tách:

| Cơ chế | Đặt ở đâu | Điều được bảo đảm |
| --- | --- | --- |
| `connectTimeout(Duration)` | `HttpClient.Builder` | Khi **thiết lập kết nối mới** vượt hạn, gửi bất đồng bộ complete exceptionally (ví dụ `HttpConnectTimeoutException`). |
| `timeout(Duration)` | `HttpRequest.Builder` | Deadline cho request theo Java HTTP Client; khi phản hồi không tới trong thời hạn, future complete exceptionally với `HttpTimeoutException`. |
| `future.orTimeout(n, TimeUnit.SECONDS)` | `CompletableFuture` | Giới hạn thời gian chờ hoàn tất của **future đó**; chưa hoàn tất đúng hạn thì complete exceptionally với `TimeoutException`. |

`orTimeout` được hỗ trợ từ Java 9, dùng được với Java 11; nó thay đổi chính future đang gọi, không tạo một API HTTP mới. **Không coi timeout/cancellation là bảo đảm request chưa đến server hoặc server không thay đổi trạng thái.** Với POST thay đổi dữ liệu, retry phải xét tính idempotent và idempotency key (nếu API hỗ trợ), tránh tạo bản ghi trùng.

## 6. Executor, luồng và quản lý tài nguyên

### 6.1. `sendAsync` không tạo «một thread riêng cố định» cho mỗi request

`HttpClient` dùng cơ chế executor và I/O bất đồng bộ của runtime. Không nên dựa trên tên/loại thread cụ thể để viết logic. Một stage không có hậu tố `Async` có thể chạy trên luồng hoàn tất giai đoạn trước hoặc ở luồng gọi nếu future đã completed trước khi callback được đăng ký.

Nếu xử lý JSON lớn, mã hóa, ghi file hoặc thao tác blocking ở callback, hãy cân nhắc tách khỏi luồng I/O:

~~~java
// Đoạn minh họa: cpuPool phải được ứng dụng tạo và đóng đúng vòng đời.
CompletableFuture<String> processed =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
              .thenApplyAsync(response -> heavyTransform(response.body()),
                              cpuPool);
~~~

`heavyTransform` là hàm nghiệp vụ **minh họa**, không phải method trong JDK. Một `ExecutorService` do ứng dụng quản lý phải được shutdown ở thời điểm phù hợp. Đừng tạo pool mới cho mỗi callback hoặc chạy tác vụ CPU lâu trong event loop.

### 6.2. Tái sử dụng client và khác biệt vòng đời giữa các phiên bản Java

`HttpClient` được thiết kế để dùng lại; thường nên giữ một client trong phạm vi dịch vụ thay vì tạo/loại bỏ mỗi request.

**Lưu ý tương thích Java 11:** `HttpClient.close()`/`shutdown()` là các API được bổ sung ở JDK **21**, **không có trong Java 11**. Vì vậy ví dụ target Java 11 **không** đặt `HttpClient` trong try-with-resources hoặc gọi `client.close()`. Từ các JDK mới có API lifecycle mới, dự án có thể tận dụng chúng khi nâng baseline; vẫn phải kiểm tra phiên bản Java nhỏ nhất mà sản phẩm hỗ trợ. Trên Java 11, xử lý đúng vòng đời những tài nguyên bạn chủ động tạo (executor riêng, stream body, file output) và chờ kết thúc các future cần thiết.

### 6.3. Cancellation chỉ nên xem như nỗ lực dừng

`CompletableFuture.cancel(...)` cho phép đánh dấu stage bị hủy, nhưng không được mặc định hành động phía server chắc chắn bị ngắt hoặc dữ liệu chưa được xử lý. Hành vi hủy I/O phía dưới tùy phiên bản và implementation; cần bảo đảm quy tắc nghiệp vụ vẫn đúng nếu server đã nhận POST, đã thực thi một phần, hoặc response đến muộn.

Đối với HTTP body đọc theo luồng như `BodyHandlers.ofInputStream()`, hãy tiêu thụ hoặc đóng `InputStream` đúng lúc. Với `BodyHandlers.ofFile(...)`, quản lý đường dẫn và quyền ghi theo yêu cầu an toàn. Không log access token, payload cá nhân hoặc thông tin xác thực chỉ để debug future.

## 7. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `sendAsync(...).join()` ngay trong UI/event loop. | Chặn luồng gọi; mất lợi ích bất đồng bộ. | Chaining `thenApply/thenCompose`, chờ tại ranh giới phù hợp. |
| Coi mọi HTTP 4xx/5xx là exceptional future. | Bỏ sót lỗi nghiệp vụ dù HTTP transport bình thường. | Kiểm `statusCode()` và ánh xạ thành lỗi ứng dụng. |
| Dùng `thenApply` để trả một future HTTP khác. | Tạo future lồng nhau, khó quản lý. | Dùng `thenCompose` để làm phẳng chuỗi phụ thuộc. |
| Gửi các request độc lập tuần tự bằng cách `join` từng lần. | Không tận dụng khả năng overlap. | Khởi tạo tất cả future trước, rồi dùng `allOf`/`thenCombine`. |
| Không cấu hình timeout hoặc trộn connect/request/future timeout. | Chờ quá lâu hoặc báo lỗi thiếu chính xác. | Chọn timeout theo từng tầng và xử lý cause. |
| Chạy xử lý nặng trong `thenApply` trên thread không kiểm soát. | Chặn task bất đồng bộ khác. | Dùng `thenApplyAsync(..., executor)` cho tác vụ phù hợp. |
| Nuốt mọi exception bằng một `exceptionally(... -> null)`. | Che lỗi giao vận, lỗi parse hoặc bug ứng dụng. | Phân loại và ghi nhận lỗi, chỉ fallback khi được phép. |
| Giả định `HttpResponse<String>` luôn chứa UTF-8. | Có thể giải mã sai văn bản. | Chọn đúng charset theo hợp đồng server/API. |
| Dùng API `HttpClient.close` khi vẫn compile `--release 11`. | Không biên dịch được. | Dùng API có trong baseline Java 11; quản lý executor/stream riêng. |
| Tạo một `HttpClient` cho mỗi request. | Mất cơ hội tái sử dụng kết nối, tốn tài nguyên. | Tái sử dụng client theo phạm vi dịch vụ. |
| Dựa vào thứ tự callback hay thời gian ngủ cố định trong test. | Test flaky, khó tái hiện. | Dùng latch/fixture và kiểm outcome rõ ràng. |
| Retry POST tự động sau timeout. | Có thể làm nghiệp vụ chạy hai lần. | Kiểm idempotency và hợp đồng endpoint trước khi retry. |

## 8. Câu hỏi tự đánh giá

**Câu 1.** `sendAsync(...)` trả về kiểu gì khi handler là `BodyHandlers.ofString(UTF_8)`?

**Đáp án:** `CompletableFuture<HttpResponse<String>>`. Tương tự, handler `ofByteArray()` tạo future của `HttpResponse<byte[]>`.

**Câu 2.** API trả HTTP 404 nhưng TCP/network hoạt động và body được nhận đầy đủ. Future nhất thiết phải complete exceptionally không?

**Đáp án:** Không. Một `HttpResponse` với `statusCode() == 404` vẫn có thể là kết quả completed normally. Ứng dụng phải xét status để quyết định nghiệp vụ có thất bại hay không.

**Câu 3.** Vì sao `sendAsync(...).join()` ngay sau đó không giúp tránh blocking?

**Đáp án:** `sendAsync` khởi tạo I/O bất đồng bộ, nhưng `join` chặn luồng gọi tới khi stage hoàn tất. Để giữ luồng gọi không chờ, đăng ký callback/composition và chỉ đợi kết quả khi thật sự cần.

**Câu 4.** Hai request B chỉ được gửi sau khi request A thành công; chọn `thenCompose` hay `allOf`?

**Đáp án:** `thenCompose` nếu B **phụ thuộc** A. Nếu A và B độc lập, có thể khởi động song song rồi dùng `allOf` hoặc `thenCombine`.

**Câu 5.** `BodyHandlers.ofInputStream()` có cùng đặc tính hoàn tất body như `ofString` không?

**Đáp án:** Không. Future có thể trả response cùng stream trước khi người dùng đọc hết bytes. Ứng dụng phải đọc/đóng stream để giải phóng tài nguyên.

**Câu 6.** Timeout HTTP có bảo đảm POST chưa được thực thi ở server không?

**Đáp án:** Không. Timeout chỉ nói về việc hoàn tất/chờ/nhận response tại client theo cơ chế áp dụng; request có thể đã được server xử lý. Retry phải xét tính idempotent.

**Câu 7.** Vì sao ví dụ dùng `--add-modules jdk.httpserver` nhưng ứng dụng HTTP Client thực tế không cần module đó?

**Đáp án:** Module `jdk.httpserver` chỉ cung cấp server cục bộ cho **kiểm thử**. Bản thân `HttpClient.sendAsync` thuộc module chuẩn `java.net.http`.

**Câu 8.** Gọi `client.close()` trên Java 11 có hợp lệ không?

**Đáp án:** Không. API quản lý vòng đời đó được bổ sung sau Java 11 (JDK 21). Khi compile target 11, cần dùng những phương thức có mặt trong JDK 11.

## Checklist hoàn thành

- [ ] Dùng đúng `HttpClient`/`HttpRequest` của `java.net.http` (Java 11) và `BodyHandlers` phù hợp.
- [ ] Phân biệt API **`send` blocking** và **`sendAsync` trả CompletableFuture**.
- [ ] Đặt timeout cho kết nối mới và request theo yêu cầu hệ thống.
- [ ] Kiểm `statusCode()`, không nhầm HTTP 404/500 với lỗi giao vận.
- [ ] Dùng `thenApply` để biến đổi, `thenCompose` cho chuỗi phụ thuộc, `allOf`/`thenCombine` cho yêu cầu độc lập.
- [ ] Có chính sách rõ cho `CompletionException`/`ExecutionException`, timeout, cancellation và retry.
- [ ] Không giả định callback chạy trên thread cố định, tránh blocking lâu trong callback.
- [ ] Tái sử dụng `HttpClient` và giữ tương thích với API của baseline Java 11.
- [ ] Chạy được **SendAsyncDemo.java** với `javac --release 11 --add-modules jdk.httpserver` và xác minh đủ bảy nhóm PASS.
- [ ] Có thể viết test thêm cho endpoint thực bằng mock server, kiểm status/body/headers/error và không phụ thuộc Internet bên ngoài.

## Tài liệu tham khảo chính thức

1. [Java SE 11 — java.net.http.HttpClient: send và sendAsync](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
2. [Java SE 11 — HttpRequest và Builder: timeout, GET, POST](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html)
3. [Java SE 11 — HttpResponse và BodyHandlers: ofString, ofByteArray, ofInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
4. [Java SE 11 — HttpClient.Builder: connectTimeout, executor và followRedirects](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
5. [Java SE 11 — CompletableFuture: thenApply, thenCompose, allOf, exceptionally](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
6. [Java SE 11 — HttpTimeoutException và HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
7. [JDK 26 — HttpClient (đối chiếu API hiện hành và khác biệt lifecycle so với Java 11)](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
