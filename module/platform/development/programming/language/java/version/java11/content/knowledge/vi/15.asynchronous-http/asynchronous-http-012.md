# Kiểm thử máy chủ chậm, mất kết nối và lỗi một phần với HTTP bất đồng bộ trong Java 11+

## 1. Vì sao phải kiểm thử nhiều loại lỗi?

`HttpClient.sendAsync(...)` (module `java.net.http`, từ Java 11) trả về `CompletableFuture<HttpResponse<T>>`. Không phải mọi tình huống “request thất bại” đều có hình thức giống nhau: một máy chủ có thể trả về HTTP 503 hợp lệ; có thể không kịp gửi phản hồi; có thể đóng kết nối trước headers; hoặc gửi headers 200 nhưng mới gửi một phần body rồi ngắt. Khi nhiều request chạy đồng thời, một request lỗi cũng không nhất thiết có nghĩa mọi kết quả khác đều vô dụng.

Phân biệt các lớp tình huống:

1. **HTTP status lỗi** (`404`, `429`, `503`...): `sendAsync` thường **hoàn thành bình thường** với đối tượng `HttpResponse` nếu nhận được phản hồi hợp lệ. Ứng dụng tự đọc `response.statusCode()` và đánh giá theo nghiệp vụ.
2. **Timeout**: request không nhận được phản hồi trong thời hạn cho phép; future có thể **hoàn thành exceptionally** với `HttpTimeoutException`.
3. **Mất kết nối**: socket bị đóng/reset trong quá trình gửi hoặc nhận, thường dẫn đến lỗi I/O. Không được suy đoán rằng server chưa hề xử lý request.
4. **Response body chưa đầy đủ**: nhận một phần nội dung rồi hết kết nối, không đủ byte như protocol yêu cầu. Với `BodyHandlers.ofByteArray()` hoặc `ofString()`, lỗi đọc có thể làm future thất bại; với `ofInputStream()`, response có thể đã hoàn thành sau headers nhưng lỗi xuất hiện về sau trong `InputStream.read()`.
5. **Lỗi một phần trong nhóm request**: một số future hoàn thành thành công, số khác gặp lỗi mạng hoặc status không đạt yêu cầu. Cần chọn chính sách tổng hợp, retry hoặc hiển thị dữ liệu từng phần.

**Nguyên tắc kiểm thử:** quan sát *hợp đồng và trạng thái có ý nghĩa* (status code, loại throwable, đầy đủ body, kết quả từng nhánh), không khóa assertion vào thông báo exception hoặc thời gian chạy chính xác đến mili-giây. Các API và cách tư duy này vẫn áp dụng trên JDK hiện đại.

## 2. Ma trận tình huống cần có

| Ca thử | Cách mô phỏng bằng server kiểm thử | Điều cần assert |
| --- | --- | --- |
| Bình thường | Trả `200 OK`, body `OK` | Future thành công, status và body đúng |
| HTTP 503 | Trả `503 Service Unavailable`, body hợp lệ | Có `HttpResponse`, `statusCode()==503`; không nhầm với exception |
| Chậm | Cố ý chưa gửi response headers | Future lỗi timeout theo deadline |
| Ngắt sớm | Đóng exchange trước khi gửi headers | Future lỗi transport, không nhận response hợp lệ |
| Body bị cắt | Khai báo `Content-Length` dài hơn số byte được gửi | Handler cần toàn bộ body phát hiện dữ liệu thiếu |
| Nhiều request | Gửi đồng thời cả ca tốt và lỗi | Thu được kết quả riêng của từng nhánh; không làm mất thông tin |

Nên dùng **loopback server** trong cùng chương trình hoặc môi trường staging được kiểm soát. Không tạo lỗi giả bằng cách ngắt mạng thật hoặc dội nhiều request lỗi vào hệ thống production.

## 3. Timeout của kết nối, request và future khác nhau

Ví dụ cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();
```

Đây là đoạn minh họa có biến `uri` và import `HttpClient`, `HttpRequest`, `Duration`.

- **`connectTimeout`** ở client giới hạn thời gian **thiết lập một kết nối mới**. Khi kết nối quá hạn, `HttpConnectTimeoutException` có thể được dùng; lớp này kế thừa `HttpTimeoutException`.
- **`HttpRequest.Builder.timeout`** đặt timeout ở cấp request. Nếu response không nhận được trong thời hạn theo hợp đồng API, `sendAsync` hoàn thành exceptionally với `HttpTimeoutException`. Với handler streaming như `ofInputStream()`, ứng dụng còn phải quản lý quá trình đọc body *sau khi* nhận stream.
- **`CompletableFuture.orTimeout(timeout, unit)`** áp dụng deadline **cho future**, có thể tạo `java.util.concurrent.TimeoutException`. Đó **không phải** cùng API hay loại exception với `HttpTimeoutException`, và không nên mặc định network request đã thực sự bị hủy.

`sendAsync` không chặn để đợi response như `send`; tuy nhiên, gọi `join()`/`get()` trên một future chưa hoàn thành sẽ chặn thread đang đợi. Khi future thất bại, `join()` thường ném `CompletionException` bọc nguyên nhân bên trong; `get()` thường báo `ExecutionException`. Khi phân loại timeout, duyệt chuỗi `getCause()` hoặc xử lý type gốc, thay vì so sánh message tùy implementation.

Chọn thời hạn hợp lý theo SLO của ứng dụng, kích thước response và khả năng server. Deadline test cũng phải có biên an toàn: nếu server chậm 200 ms nhưng timeout 201 ms, bài test dễ flaky do OS scheduling.

## 4. Ví dụ Java hoàn chỉnh: tự dựng máy chủ 200/503/chậm/ngắt/bị cắt

Chương trình sử dụng module `jdk.httpserver` có trong JDK để tạo server tại `127.0.0.1` và cổng được hệ điều hành cấp tự động. Nó **không cần Internet** và không truy cập hệ thống bên ngoài.

Năm endpoint:

- `/ok`: trả 200 và `OK`.
- `/status`: trả 503 và `BUSY`.
- `/slow`: chờ một `CountDownLatch`, chưa gửi headers; client dùng timeout 250 ms.
- `/drop`: đóng exchange trước khi trả HTTP headers hợp lệ.
- `/partial`: tuyên bố body dài 20 byte, nhưng chỉ gửi 4 byte `PART` rồi đóng. Theo hợp đồng `HttpExchange`, đóng output stream của response độ dài cố định khi chưa ghi đủ sẽ abort kết nối.

Đối với từng request, `handle(...)` chuyển thành `CompletableFuture<Boolean>`. Nhờ đó, `CompletableFuture.allOf(...)` có thể đợi cả các nhánh tốt và lỗi mà không làm mất kết quả riêng. Dùng `BodyHandlers.ofByteArray()` cho ca ngắt/cắt body để handler phải đọc trọn response.

Lưu tệp **`AsyncHttpFaultTest.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncHttpFaultTest {
    public static void main(String[] args) throws Exception {
        CountDownLatch releaseSlow = new CountDownLatch(1);
        ExecutorService serverPool = Executors.newCachedThreadPool();
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(serverPool);

        server.createContext("/ok", ex -> reply(ex, 200, "OK"));
        server.createContext("/status", ex -> reply(ex, 503, "BUSY"));

        server.createContext("/slow", ex -> {
            try {
                releaseSlow.await(4, TimeUnit.SECONDS);
                reply(ex, 200, "LATE");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (IOException expectedAfterTimeout) {
                // Client có thể đã hủy exchange.
            } finally {
                ex.close();
            }
        });

        server.createContext("/drop", HttpExchange::close);

        server.createContext("/partial", ex -> {
            try {
                ex.sendResponseHeaders(200, 20);
                try (OutputStream output = ex.getResponseBody()) {
                    output.write("PART".getBytes(StandardCharsets.UTF_8));
                }
            } catch (IOException expectedTruncation) {
                // Đóng fixed-length body còn thiếu byte sẽ abort exchange.
            } finally {
                ex.close();
            }
        });

        server.start();
        try {
            URI base = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort() + "/");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            CompletableFuture<Boolean> ok = client.sendAsync(
                    get(base.resolve("ok"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofString())
                    .handle((res, error) ->
                            error == null && res.statusCode() == 200
                                    && "OK".equals(res.body()));

            CompletableFuture<Boolean> serviceUnavailable = client.sendAsync(
                    get(base.resolve("status"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofString())
                    .handle((res, error) ->
                            error == null && res.statusCode() == 503
                                    && "BUSY".equals(res.body()));

            CompletableFuture<Boolean> slow = client.sendAsync(
                    get(base.resolve("slow"), Duration.ofMillis(250)),
                    HttpResponse.BodyHandlers.ofString())
                    .handle((res, error) -> hasHttpTimeout(error));

            CompletableFuture<Boolean> disconnected = client.sendAsync(
                    get(base.resolve("drop"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofByteArray())
                    .handle((res, error) -> error != null);

            CompletableFuture<Boolean> truncated = client.sendAsync(
                    get(base.resolve("partial"), Duration.ofSeconds(3)),
                    HttpResponse.BodyHandlers.ofByteArray())
                    .handle((res, error) -> error != null);

            CompletableFuture.allOf(
                    ok, serviceUnavailable, slow, disconnected, truncated)
                    .join();

            releaseSlow.countDown();

            System.out.println("ok=" + ok.join());
            System.out.println("http503IsResponse=" +
                    serviceUnavailable.join());
            System.out.println("slowTimedOut=" + slow.join());
            System.out.println("disconnectDetected=" + disconnected.join());
            System.out.println("truncatedBodyDetected=" + truncated.join());
            System.out.println("batchCompleted=true");
        } finally {
            releaseSlow.countDown();
            server.stop(0);
            serverPool.shutdownNow();
        }
    }

    private static HttpRequest get(URI uri, Duration timeout) {
        return HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .GET()
                .build();
    }

    private static void reply(
            HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static boolean hasHttpTimeout(Throwable error) {
        for (Throwable t = error; t != null; t = t.getCause()) {
            if (t instanceof HttpTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
```

**Biên dịch/chạy với JDK 17+; mã cũng dùng được trên Java 11:**

```bash
javac --add-modules jdk.httpserver AsyncHttpFaultTest.java
java --add-modules jdk.httpserver AsyncHttpFaultTest
```

**Stdout kỳ vọng khi môi trường cho phép loopback và không bị nghẽn scheduling nghiêm trọng:**

```text
ok=true
http503IsResponse=true
slowTimedOut=true
disconnectDetected=true
truncatedBodyDetected=true
batchCompleted=true
```

Những dòng trên phản ánh **kết quả của điều kiện kiểm thử**, không phải các chuỗi được in cứng cho mọi kết quả. Với môi trường cấm socket loopback, proxy can thiệp hoặc máy chạy quá tải bất thường, có thể có giá trị `false` hoặc lỗi thiết lập server; cần coi đó là dấu hiệu để điều tra điều kiện kiểm thử, không che giấu nó.

**Giải thích:**

1. `ok=true`: nhận được `HttpResponse` status 200, body `OK`; future thành công.
2. `http503IsResponse=true`: đã nhận được status 503 và body `BUSY` **như response hợp lệ**; `sendAsync` không ném exception chỉ vì là 5xx. Nếu nghiệp vụ yêu cầu 2xx thì status này vẫn là lỗi nghiệp vụ.
3. `slowTimedOut=true`: endpoint chờ latch nên không trả headers trong deadline 250 ms; client nhận lỗi `HttpTimeoutException`. Hàm `hasHttpTimeout` duyệt toàn bộ cause chain, tránh phụ thuộc bọc `CompletionException`.
4. `disconnectDetected=true`: đóng exchange trước headers, future cuối cùng phát hiện lỗi transport. Một HTTP client có thể thử lại GET idempotent trong một số tình huống; test không giả định chính xác số lượt server nhìn thấy.
5. `truncatedBodyDetected=true`: server khai báo 20 byte nhưng chỉ gửi 4 byte. Đóng fixed-length response bị thiếu sẽ abort exchange; `ofByteArray()` chờ đủ body và báo lỗi đọc thiếu.
6. `batchCompleted=true`: vì các nhánh đều được `handle` thành giá trị boolean, `allOf` đã đợi xong toàn bộ và các kết quả tốt/lỗi đều được xem xét.

Server dùng executor riêng để nhánh `/slow` không ngăn các request khác. `server.stop(0)` và `serverPool.shutdownNow()` dọn tài nguyên của test. HTTP client trong Java 11 không triển khai `AutoCloseable`, nên không viết `try (HttpClient client = ...)` nếu muốn mã biên dịch trên Java 11.

## 5. Lỗi một phần trong nhóm `CompletableFuture`

Nếu gửi ba request đồng thời:

```java
CompletableFuture<HttpResponse<String>> a =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> b =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> c =
        client.sendAsync(requestC, HttpResponse.BodyHandlers.ofString());

CompletableFuture.allOf(a, b, c).join();
```

Đây là **đoạn minh họa**, cần `client` và ba request đã tạo. Khi một nhánh hoàn thành exceptionally, future `allOf` cũng sẽ hoàn thành exceptionally, dù các nhánh còn lại có thể đã thành công. `allOf` **không tự hủy** những request khác và **không tự trả mảng `HttpResponse`**; nó có kết quả kiểu `Void` và từng response nằm trong các future thành viên.

Nếu muốn xử lý độc lập và tổng hợp đầy đủ, chuyển mỗi kết quả thành một kiểu outcome có cấu trúc:

```java
CompletableFuture<String> outcome =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
              .handle((response, error) -> {
                  if (error != null) {
                      return "transport-error";
                  }
                  if (response.statusCode() >= 500) {
                      return "server-error-" + response.statusCode();
                  }
                  return "ok-" + response.statusCode();
              });
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Trong production nên dùng một class/record chứa endpoint, HTTP status, body cần thiết, throwable, khả năng retry và correlation ID; chuỗi ở đây chỉ giúp thấy ba nhánh.

Các stage khác nhau:

- `handle((value,error)->...)` chạy với **cả** trạng thái thành công và exceptional, có thể biến lỗi thành giá trị dự phòng.
- `exceptionally(error->...)` chỉ chạy khi future exceptional; **không** tự phát hiện response 503.
- `whenComplete((value,error)->...)` hữu ích để ghi log/metrics, không tự biến lỗi thành thành công.
- `thenApply(value->...)` chỉ xử lý giá trị bình thường; nếu giai đoạn trước exceptional, nó không chạy như một nhánh thành công.

Nếu chọn “fail-fast” theo nghiệp vụ, ứng dụng phải tự thiết kế hủy/đợi các request khác và quản lý kết quả; không coi `allOf` là cơ chế tự động fail-fast cancel.

## 6. Mất kết nối ở thời điểm nào?

| Điểm đứt | Dấu hiệu thường thấy | Không được suy luận |
| --- | --- | --- |
| Chưa thiết lập TCP/TLS | Lỗi connect hoặc connect timeout | Không có cơ sở cho rằng server nghiệp vụ đã nhận request |
| Sau gửi request nhưng trước headers | Reset/EOF, future exceptional | Không chứng minh server chưa thực hiện side effect |
| Sau headers nhưng giữa response body | Truncated/IOException, hoặc lỗi khi đọc `InputStream` | Không được gọi là thành công chỉ vì thấy status 200 |
| Trong lúc upload request body | Publisher/ghi socket lỗi, có thể chỉ gửi được một phần | Không biết chắc server đã nhận bao nhiêu byte |
| Server đã xử lý nhưng response không về client | Client báo lỗi mặc dù server có thể đã commit | Không tự động retry POST tạo đơn/giao dịch |

Không có **một** loại exception hay message đại diện mọi lần ngắt kết nối. `IOException` và các lớp con có thể khác nhau theo JDK, proxy, HTTP/1.1 hoặc HTTP/2 và thời điểm đứt. Với `sendAsync`, callback thường nhận throwable qua biến `error`; `join` có thể bọc nguyên nhân bằng `CompletionException`. Nên phân loại theo exception hierarchy/causal chain, ghi thêm trace ID và giai đoạn xử lý.

Đặc biệt, với `BodyHandlers.ofInputStream()`, future có thể thành công sau khi nhận headers. Khi ứng dụng đọc body mới phát sinh `IOException`; bắt lỗi trong vòng đọc và **luôn đóng stream** qua `try-with-resources` nếu không tiêu thụ tới EOF. Với `ofString()`/`ofByteArray()`, handler cần đọc hết body trước khi hoàn tất bình thường.

## 7. Timeout, cancellation và retry: ba vấn đề tách biệt

**Timeout HTTP:** đặt bằng `HttpRequest.Builder.timeout(Duration)`. Test nên assert loại `HttpTimeoutException`, không assert “chính xác sau 250 ms”.

**Timeout future:** `future.orTimeout(...)` tạo lỗi `TimeoutException` ở tầng future; đừng coi nó mặc định đã dừng I/O hay đã đóng kết nối. Nếu muốn hủy request đang chạy, cần cơ chế cancellation phù hợp.

**Cancellation:** future do HTTP client mặc định trả về trên các JDK hiện đại có thể `cancel(true)` để *cố gắng* hủy HTTP exchange. Đây là **best effort**: không bảo đảm server chưa xử lý, không bảo đảm kết nối đóng ngay lập tức. Hủy HTTP/1.1 có thể đóng connection; với HTTP/2 có thể reset stream. Không viết assertion dựa vào thời điểm socket đóng tuyệt đối.

**Retry:** không phải lỗi nào cũng đáng retry:

- GET thường an toàn/idempotent về ngữ nghĩa HTTP, có thể thử lại có giới hạn khi lỗi tạm thời và hợp đồng endpoint cho phép.
- 429/503 có thể cần áp dụng `Retry-After`, giới hạn số lượt, backoff, jitter và tổng deadline.
- POST tạo tài nguyên/giao dịch **có thể đã được thực thi** trước khi client nhìn thấy timeout. Không retry tự động nếu thiếu idempotency key hoặc cách xác minh trạng thái.
- PUT theo ngữ nghĩa HTTP là idempotent; PATCH không mặc định idempotent; vẫn phải kiểm tra hợp đồng API thực tế.
- Với lỗi một phần, thường chỉ cân nhắc retry **nhánh lỗi**, không phát lại tất cả request đã thành công.
- Nếu request body dùng nguồn streaming không thể phát lại, việc retry có thể thất bại hoặc sai nội dung; cần thiết kế replayability.

Không viết `while(true)` retry không giới hạn, nhất là khi server đang quá tải.

## 8. Làm test ổn định và an toàn trong CI

1. **Cô lập nguồn lỗi:** server loopback có endpoint riêng; tránh dùng mạng Internet hoặc production làm nguồn kiểm thử.
2. **Điều khiển slow bằng latch:** chặn response trước headers, chọn timeout có khoảng cách lớn với thời gian chờ. Test sát ranh giới vài mili-giây rất dễ flaky.
3. **Tách lỗi HTTP và transport:** 503 phải là response hợp lệ, còn `/drop` và `/partial` cố ý vi phạm truyền tải.
4. **Kiểm tra kết quả không phụ thuộc message:** assertion trên `HttpTimeoutException`, status code, có/không exception, số byte hợp lệ. Thông báo tiếng Anh có thể thay đổi.
5. **Không bỏ sót future:** quan sát hoặc đợi từng nhánh; future exceptional không được “nuốt” mà không có log/counter.
6. **Dọn dẹp:** stop server và shutdown executor do bài test sở hữu. Khi dùng response streaming, đóng/cancel body nếu không đọc hết.
7. **Có giới hạn thời gian của cả bài test:** tránh CI treo do lỗi môi trường; dùng timeout phù hợp và log kịch bản đang chạy.
8. **Tách unit và integration:** unit test có thể kiểm thử classifier/trình tổng hợp outcome bằng dữ liệu giả; integration test mới xác minh hành vi mạng, đóng socket và body bị cắt.

Test ở ví dụ dùng `jdk.httpserver`, một module JDK vẫn được hỗ trợ. Trong môi trường không thể mở cổng loopback, có thể chuyển integration test sang một môi trường cho phép socket, nhưng không giả định vì thế logic xử lý HTTP sai.

## 9. Những lỗi thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| Status 503 làm `sendAsync` tự ném exception | 503 có thể là response bình thường; ứng dụng kiểm tra `statusCode()`. |
| `orTimeout` giống `HttpRequest.timeout` | Khác tầng, khác exception và không đồng nghĩa đã cancel network. |
| Thấy headers 200 thì luôn có body đầy đủ | Body có thể bị cắt giữa chừng; cần handler/consumer xác minh quá trình đọc. |
| `allOf` tự hủy mọi nhánh còn lại khi một future lỗi | Không; cần chính sách điều phối/hủy riêng. |
| Retry POST khi bị reset là chắc chắn an toàn | Server có thể đã commit. Cần idempotency key hoặc đối soát. |
| So sánh toàn bộ exception message để assert | Dễ lệ thuộc JDK/OS; dùng hierarchy/cause chain và trạng thái. |
| `read()==-1` ngay sau headers là bình thường với Content-Length dương chưa đủ | EOF sớm thể hiện body thiếu; cần phân biệt và báo lỗi. |
| Gọi `close()` mà quên xử lý streaming response còn dang dở | Phải quản lý close/EOF, có thể ảnh hưởng kết nối và tài nguyên. |
| Dùng `Thread.sleep` sát deadline làm test luôn chính xác | Scheduling biến động; latch và biên timeout an toàn hơn. |
| Không shutdown executor của test | Có thể giữ process hoặc rò tài nguyên. |

## 10. Tự kiểm tra

**Câu 1:** Một server trả `503` với body `BUSY` đầy đủ. `sendAsync(..., ofString())` bắt buộc exceptional không?

**Đáp án:** Không. Client có thể nhận được `HttpResponse` với `statusCode()==503`; tầng nghiệp vụ mới quyết định thất bại hoặc retry.

**Câu 2:** Vì sao timeout của POST không chứng minh giao dịch chưa được tạo?

**Đáp án:** Server có thể đã xử lý và commit, nhưng response bị trễ/mất trên đường về. Retry cần bảo vệ chống tác động lặp.

**Câu 3:** `CompletableFuture.allOf(a,b,c)` có tự trả ba response không?

**Đáp án:** Không. Nó trả `CompletableFuture<Void>`; kết quả phải lấy từ từng future, và một future exceptional có thể khiến `allOf` exceptional.

**Câu 4:** Với Content-Length 20 mà server chỉ gửi 4 byte rồi đóng, vì sao không chỉ assert status 200?

**Đáp án:** Vì headers không chứng minh body đã nhận đầy đủ. Cần handler đọc hết body, hoặc đọc streaming có kiểm tra lỗi/EOF và đóng stream.

**Câu 5:** `request.timeout(...)` và `future.orTimeout(...)` có luôn tạo cùng exception không?

**Đáp án:** Không. Một bên là `HttpTimeoutException` của HTTP client, bên kia thường là `TimeoutException` của CompletableFuture.

**Câu 6:** Trong năm request chỉ một request mất kết nối, có bắt buộc bỏ bốn response tốt còn lại không?

**Đáp án:** Không. Đây là quyết định nghiệp vụ; có thể giữ từng outcome, đánh dấu phần thiếu, retry nhánh lỗi hoặc từ chối toàn bộ nếu tính nhất quán yêu cầu.

**Ghi nhớ:** Kiểm thử HTTP bất đồng bộ cần phân biệt **HTTP status**, **transport exception**, **timeout**, **ngắt giữa body** và **lỗi một phần của nhóm request**. Dùng server fault injection có kiểm soát, `CompletableFuture.handle` cho từng nhánh, `allOf` để đợi tổng hợp, cấu hình timeout/hủy đúng tầng và retry có giới hạn, có xét tác động nghiệp vụ.

**Nguồn API chính thức:** [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html), [HttpRequest.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html), [HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html), [CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html), [Java SE 25 — HttpExchange](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html).
