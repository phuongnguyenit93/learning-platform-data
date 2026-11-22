# Phân biệt connect timeout, request timeout và deadline nghiệp vụ trong HTTP bất đồng bộ (Java 11+)

## 1. Bài toán: ba giới hạn thời gian không thay thế nhau

Khi sử dụng `java.net.http.HttpClient`, một ứng dụng có thể phải kết nối tới dịch vụ, gửi request, nhận response, phân tích nội dung, gọi thêm API khác và quyết định có retry hay không. Mỗi bước có nguy cơ kéo dài ngoài mong muốn. Từ **Java 11**, HTTP Client API hỗ trợ hai cấu hình timeout khác nhau; ngoài ra ứng dụng thường cần một **deadline nghiệp vụ** bao trùm *toàn bộ* quy trình.

Ba khái niệm:

1. **Connect timeout — giới hạn tạo kết nối mới.** Đặt trên `HttpClient.Builder.connectTimeout(Duration)`; chỉ có tác dụng khi client thực sự cần thiết lập kết nối mới.
2. **Request timeout — giới hạn một HTTP request.** Đặt trên `HttpRequest.Builder.timeout(Duration)`; áp dụng cho từng yêu cầu riêng khi gọi `send` hoặc `sendAsync`.
3. **Deadline nghiệp vụ — thời điểm muộn nhất toàn bộ công việc còn giá trị.** Do ứng dụng xác định, tính cả nhiều HTTP requests, retry/backoff, xử lý response, truy xuất dữ liệu và các bước ngoài HTTP. Java HTTP Client **không có một cấu hình built-in tự động bao trùm tất cả bước này**.

Hãy tưởng tượng một màn hình tra cứu cần hoàn tất trong tối đa 800 ms. Màn hình gọi dịch vụ A, xử lý JSON rồi gọi dịch vụ B. Nếu mỗi request có `timeout(700 ms)`, ứng dụng vẫn có thể vượt 800 ms vì hai request chạy nối tiếp và còn thời gian xử lý khác. **Deadline đầu-cuối** là hợp đồng của toàn workflow, không phải bản sao của một request timeout.

~~~text
Bắt đầu workflow                         Deadline nghiệp vụ
        |                                       |
        v                                       v
     Tạo/gửi request A ---> parse A ---> request B ---> lưu kết quả
         |                         |
         |--- Request timeout A ---|
                                    |--- Request timeout B ---|
       |--- Connect timeout khi tạo kết nối mới ---|
        <------ Toàn bộ thời gian phải nằm trong deadline -------->
~~~

Sơ đồ chỉ minh họa: connect timeout có thể chạy trong khoảng một request, và kết nối đã tồn tại có thể không cần kết nối mới. **Không cộng cơ học** các timeout như những pha bắt buộc nối tiếp.

## 2. Connect timeout thuộc `HttpClient`

API:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
~~~

Đây là **đoạn minh họa**, cần import `java.net.http.HttpClient` và `java.time.Duration`. Khi client cần tạo một kết nối mới và không thể thiết lập nó trong thời hạn đã cấu hình, API có thể báo **`HttpConnectTimeoutException`**:

- Với `client.send(...)`: ngoại lệ được ném trực tiếp.
- Với `client.sendAsync(...)`: `CompletableFuture` có thể hoàn tất thất bại, với `HttpConnectTimeoutException` làm nguyên nhân.
- Nếu đã có kết nối trong pool được tái sử dụng, **`connectTimeout` không có hiệu lực** cho lần request đó vì không có bước tạo kết nối mới.
- `HttpClient.Builder.connectTimeout` nhận **`Duration` dương**; zero và âm ném `IllegalArgumentException`.
- `client.connectTimeout()` trả **`Optional<Duration>`**; không cấu hình thì `Optional.empty()`.

**Ý nghĩa chính xác:** connect timeout bảo vệ riêng công đoạn thiết lập *kết nối mới*. Nó **không phải giới hạn tổng thời gian từ lúc gửi đến lúc nhận body**, không được bảo đảm là “DNS timeout”, “TLS timeout” hay “read timeout” độc lập ở mọi implementation. Nếu kết nối thành công nhưng server giữ request lâu không phản hồi, connect timeout không đủ.

### Vì sao không nên dùng một kết nối giả để thử connect timeout?

Kết nối đến một cổng đóng có thể thất bại ngay với `ConnectException: Connection refused`, **không** nhất thiết đợi hết timeout. Địa chỉ IP không truy cập được có thể bị từ chối bởi route, proxy hoặc firewall theo cách khác nhau. Không nên xây unit test cho `HttpConnectTimeoutException` bằng cách hardcode một IP công cộng “không phản hồi”.

Để kiểm thử đáng tin, có thể dùng **network fault injection/test environment** được kiểm soát; phần ví dụ ở mục 7 sẽ chỉ **in cấu hình connect timeout** và kiểm chứng request timeout/deadline qua một server loopback, không giả tạo connect-timeout exception.

## 3. Request timeout thuộc `HttpRequest`

Mỗi request có thể có thời hạn riêng:

~~~java
HttpRequest quick = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(250))
        .GET()
        .build();

HttpRequest slowAllowed = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();
~~~

Đây là **mã minh họa**, cần import `java.net.http.HttpRequest`, `java.time.Duration` và khai báo `URI uri`.

`HttpRequest.Builder.timeout(Duration)` đã có từ **Java 11**, vẫn được hỗ trợ. Theo API, nếu response không được nhận trong thời gian đã chỉ định thì `send()` ném **`HttpTimeoutException`**, còn `sendAsync()` hoàn tất future một cách ngoại lệ với nguyên nhân `HttpTimeoutException`.

Những điểm phải nhớ:

- Giới hạn thuộc *request*, không nằm trong một biến thời gian toàn cục của `HttpClient`. Hai request cùng client có thể có thời hạn khác nhau.
- `request.timeout()` trả `Optional<Duration>`. Không đặt timeout tương đương **không có giới hạn riêng bằng setting đó**; không có nghĩa ứng dụng không thể lỗi/hủy do nguyên nhân khác.
- `Duration.ZERO` hoặc duration âm bị từ chối bằng `IllegalArgumentException`.
- Khi gửi qua kết nối đã tái sử dụng, request timeout vẫn có ý nghĩa dù connect timeout không còn tác động.
- Timeout có thể hoàn tất request thất bại sau khi server **đã nhận và xử lý** yêu cầu. Nó không phải xác nhận rollback và không đảm bảo request chưa tạo side effect.
- HTTP status 408 hoặc 504 là **phản hồi HTTP do server/proxy gửi**, còn `HttpTimeoutException` là **lỗi client không nhận kịp response theo giới hạn đã cấu hình**. Hai trường hợp có thể cần chính sách xử lý riêng.

### Request timeout bao phủ đến đâu?

Tài liệu API xác định thời hạn chờ response. Trong hành vi HTTP Client built-in hiện hành, request timeout liên quan quá trình lấy kết nối, nhận response và xử lý response body theo `BodySubscriber`, nhưng **không được suy diễn** rằng nó là deadline bất biến cho toàn bộ mã ứng dụng chạy sau đó.

Với `BodyHandlers.ofString()`/`ofByteArray()`, handler tích lũy body vào kiểu kết quả trước khi future thành công. Nhưng với `BodyHandlers.ofInputStream()`, `ofLines()` hoặc `ofPublisher()`, đối tượng `HttpResponse` có thể được trả về sau khi nhận headers trong khi body **vẫn còn đang được nhận hoặc tiêu thụ**. Những thao tác đọc, phân tích, ghi file hoặc downstream processing của ứng dụng sau đó có thể cần timeout riêng.

**Không nhầm `request.timeout(Duration)` với per-read timeout của từng byte**. Nếu nghiệp vụ cần phát hiện một luồng streaming bị treo, ngoài deadline tổng còn cần thiết kế idle timeout/rate limit, giới hạn kích thước và cancel/close body theo hợp đồng.

## 4. Deadline nghiệp vụ không thuộc riêng HTTP API

**Deadline** là một *mốc thời gian cuối cùng*, không phải chỉ một thời lượng. Khi workflow bắt đầu, ứng dụng xác định ngân sách, ví dụ:

~~~text
Budget ban đầu: 800 ms
  |
  +-- gọi API A đã dùng: 260 ms
  +-- parse/validate A đã dùng: 80 ms
  |
  +-- còn tối đa: 460 ms cho B và các bước kết thúc
~~~

Nếu lúc bắt đầu request B chỉ còn 460 ms, không được reset workflow thành “B có 800 ms mới” rồi mặc nhiên cho phép toàn bộ thao tác kéo dài hơn ngân sách. Một **request timeout tĩnh** không biết các bước trước đó đã tiêu tốn bao nhiêu.

Mẫu thực tế:

1. Ghi nhận deadline một lần khi nhận tác vụ.
2. Trước mỗi hoạt động có thể chặn, tính **remaining time**.
3. Nếu thời gian còn lại `<= 0`, không khởi động tác vụ mới; chuyển sang timeout nghiệp vụ/fallback.
4. Nếu còn thời gian, đặt timeout của request mới bằng **min(per-attempt cap, remaining time)**, với `Duration` dương.
5. Giới hạn thao tác chờ kết quả và downstream work theo **cùng deadline**, không tạo lại deadline mỗi lần retry.
6. Khi hết hạn, dừng lên lịch các bước tiếp theo, cố gắng cancel request đang đợi, dọn resource, trả lỗi/tín hiệu timeout cho tầng gọi.

### Dùng đồng hồ đơn điệu cho khoảng thời gian

`System.nanoTime()` thích hợp để đo thời lượng và tính timeout trong một JVM process; không dùng `System.currentTimeMillis()` để tính một khoảng thời gian cần chính xác trước tác động điều chỉnh đồng hồ hệ thống.

~~~java
long deadlineNanos =
        System.nanoTime() + Duration.ofSeconds(2).toNanos();

long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Business deadline exceeded");
}
~~~

Đây là **mã minh họa**, cần import `Duration` và `TimeoutException`, đặt trong method có `throws`/`catch` thích hợp. `nanoTime()` biểu diễn độ chênh lệch tương đối, **không** phải timestamp Unix; deadline kiểu này chỉ có ý nghĩa **trong cùng tiến trình** và cần xử lý overflow khi thiết kế duration rất lớn. Ví dụ ở mục 7 dùng ngân sách ngắn nên không gặp overflow.

Nếu cần **truyền deadline qua nhiều service**, cần quy ước rõ ràng ở giao thức (ví dụ truyền remaining budget/deadline đã chuẩn hóa và chống clock skew). Không truyền raw `System.nanoTime()` sang process khác vì mốc nanoTime không có ý nghĩa chung giữa JVM.

### Phân bổ ngân sách cho từng attempt

Có thể quyết định timeout request mới theo:

~~~text
requestLimit = min(
    maximumTimeForThisAttempt,
    businessDeadline - now
)
~~~

Ví dụ:

~~~java
static Duration selectRequestLimit(
        long deadlineNanos, Duration perAttemptCap)
        throws TimeoutException {
    long remaining = deadlineNanos - System.nanoTime();
    if (remaining <= 0) {
        throw new TimeoutException("No remaining business budget");
    }
    Duration left = Duration.ofNanos(remaining);
    return left.compareTo(perAttemptCap) < 0 ? left : perAttemptCap;
}
~~~

Đây là **hàm tiện ích độc lập minh họa**; cần import `Duration`, `TimeoutException`. Caller phải truyền `perAttemptCap` dương và xét độ phân giải/tính khả thi của timeout quá nhỏ. Nếu chỉ còn 1 ms nhưng request bình thường cần 100 ms, thường nên fail fast thay vì gửi một request hầu như chắc chắn hết hạn.

Quan trọng: giới hạn **trên request** không tự bao trùm thời gian chờ trong queue, retry backoff hay việc parse/sử dụng dữ liệu. Vẫn phải kiểm tra deadline ở ranh giới khác.

## 5. Cách phân biệt lỗi trong `sendAsync()`

Với Java 11:

~~~java
CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Mẫu trên minh họa cách khởi tạo; cần `client`, `request` và các imports. Future trả về gần như ngay, còn HTTP được tiến hành bất đồng bộ. Khi kết quả chưa sẵn sàng, caller có thể xử lý các tác vụ khác; nhưng `pending.join()` hoặc `pending.get(...)` **lại có thể chặn thread gọi**.

Nếu phép gửi thất bại, `join()` thường ném `CompletionException` với nguyên nhân trong `getCause()`. Với `get()`, tương ứng là `ExecutionException`. Cần phân loại **lỗi gốc**, không chỉ thông báo của wrapper.

| Trường hợp | Dấu hiệu điển hình | Tầng xử lý |
| --- | --- | --- |
| Tạo kết nối mới vượt connect timeout | `HttpConnectTimeoutException` (kiểu con của `HttpTimeoutException`) | Client HTTP, giai đoạn kết nối |
| Request vượt request timeout | `HttpTimeoutException` | Client HTTP, giai đoạn chờ response |
| Gọi `future.get(remaining, unit)` vượt thời hạn chờ | `TimeoutException` trực tiếp | Caller/workflow điều phối chờ |
| `future.orTimeout(delay, unit)` kích hoạt | Future hoàn tất ngoại lệ với `TimeoutException` | `CompletableFuture` / timeout composition |
| Request bị cancel | `CancellationException` | Cơ chế hủy future/tác vụ |
| Kết nối reset, DNS lỗi, TLS lỗi... | `IOException` hoặc kiểu liên quan | Transport/HTTP runtime |
| HTTP 408/429/500/504 | `HttpResponse.statusCode()` | Server/proxy trả HTTP response bình thường |
| Parse body lỗi hoặc validation thất bại | Ngoại lệ của parser/logic ứng dụng | Tầng ứng dụng, không tự động là HTTP timeout |

**Thứ tự phân loại trong Java:**

~~~java
static String classify(Throwable cause) {
    if (cause instanceof HttpConnectTimeoutException) {
        return "CONNECT_TIMEOUT";
    }
    if (cause instanceof HttpTimeoutException) {
        return "REQUEST_TIMEOUT";
    }
    if (cause instanceof TimeoutException) {
        return "WORKFLOW_WAIT_TIMEOUT";
    }
    if (cause instanceof CancellationException) {
        return "CANCELLED";
    }
    return "OTHER_ERROR";
}
~~~

Đây là **hàm minh họa**; cần import `java.net.http.HttpConnectTimeoutException`, `HttpTimeoutException` và `java.util.concurrent.TimeoutException`/`CancellationException`. Kiểu connect timeout cần được kiểm tra **trước** `HttpTimeoutException` vì nó kế thừa exception này. Cần nhận ra rằng timeout từ `orTimeout` có thể mang kiểu `TimeoutException` tương tự timeout khi chờ, nhưng hai đường phát sinh có semantics và ownership khác nhau; hãy phân biệt bằng ngữ cảnh thực thi/metric.

### Ví dụ catch từ `join()`

~~~java
try {
    HttpResponse<String> response = pending.join();
    int status = response.statusCode();
    // Kiểm tra status, sau đó xử lý body theo hợp đồng.
} catch (CompletionException e) {
    Throwable root = e.getCause();
    if (root instanceof HttpConnectTimeoutException) {
        // Không thiết lập được kết nối mới trong giới hạn.
    } else if (root instanceof HttpTimeoutException) {
        // Request vượt thời hạn chờ response.
    } else {
        // Lỗi transport hoặc tầng xử lý khác; không ép thành timeout.
        throw e;
    }
}
~~~

Đây là **đoạn minh họa**, `pending` đã được tạo ở nơi khác. Trong code thật cần xử lý `CancellationException` và đưa lỗi trở lại tầng điều phối theo quy định. Không coi mọi `CompletionException` là timeout.

## 6. `get(timeout)`, `orTimeout` và `HttpRequest.timeout` không giống nhau

Sự khác biệt thường gây bug khi lập trình bất đồng bộ:

| API | Nó giới hạn gì? | Khi hết hạn | Có tự rollback/cancel HTTP hoàn toàn? |
| --- | --- | --- | --- |
| `HttpClient.Builder.connectTimeout(d)` | Thiết lập kết nối **mới** | `HttpConnectTimeoutException` | Không |
| `HttpRequest.Builder.timeout(d)` | Thời gian đợi response của **một request** | `HttpTimeoutException` | Không rollback công việc server |
| `future.get(t, TimeUnit)` | Thời gian **thread gọi đang chờ future** | `TimeoutException` (trực tiếp) | **Không**; future có thể vẫn đang chạy |
| `future.orTimeout(t, TimeUnit)` | Thời gian để **future hoàn tất** | Hoàn tất exceptionally với `TimeoutException` | Không có bảo đảm hủy I/O underlying |
| Deadline tổng do ứng dụng định nghĩa | Toàn bộ workflow nhiều bước | Tín hiệu lỗi/fallback theo nghiệp vụ | Phải thiết kế hủy/cleanup riêng |

### Lưu ý về `CompletableFuture.orTimeout`

~~~java
pending.orTimeout(800, TimeUnit.MILLISECONDS);
~~~

Đây là **mã minh họa**, cần import `TimeUnit`. `orTimeout` (có từ Java 9) sửa **chính future đó**: nếu chưa hoàn tất đúng hạn, nó hoàn tất ngoại lệ bằng `TimeoutException`. Phương thức **không** tạo một future độc lập mới; nó trả lại cùng `CompletableFuture`.

Quan trọng: completion exception của future **không đồng nghĩa HTTP exchange đã bị hủy**. Nếu gọi `orTimeout` lên future do `sendAsync` trả về rồi nó đã bị timeout, việc gọi `cancel(true)` sau đó có thể không còn chuyển một future *chưa hoàn tất* sang trạng thái cancel được nữa. Vì vậy, nếu cần cố gắng giải phóng tài nguyên HTTP khi business timeout, hãy quản lý **original HTTP future** và một cơ chế deadline/cancellation phù hợp thay vì chỉ trông chờ `orTimeout`.

### `get(timeout)` hữu ích khi nào?

~~~java
try {
    HttpResponse<String> response =
            pending.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    pending.cancel(true); // Cố gắng hủy HTTP exchange nếu còn đang chạy.
    throw timeout;
}
~~~

Đây là **mã minh họa**; còn cần xử lý `InterruptedException`/`ExecutionException`, và phải quyết định cancel thuộc quyền của caller hay không. `get` chỉ dừng *việc chờ của thread*, không tự ngừng HTTP. `cancel(true)` trên future chưa hoàn tất của JDK HTTP Client cố gắng hủy trao đổi HTTP, nhưng **không bảo đảm dừng ngay**, cũng không bảo đảm server chưa nhận request.

Trong pipeline hoàn toàn non-blocking, có thể dùng scheduler/deadline future và gắn hành động cancel lên original HTTP future. Nhưng phải triển khai đúng race giữa completion, cancellation, timeout signal, và quản lý streaming body; không tự tạo timer riêng cho từng bước khiến deadline bị reset.

## 7. Ví dụ Java 11 hoàn chỉnh: ba tầng timeout trên HTTP bất đồng bộ

Ví dụ sau tạo server HTTP loopback bằng `jdk.httpserver`, không cần Internet hay token. Có hai endpoint:

- `/fast` trả text `FAST` ngay.
- `/slow` chờ khoảng 1.200 ms trước khi gửi text `SLOW`.

Một `HttpClient` cấu hình `connectTimeout = 2 giây` được dùng cho cả hai endpoint. Sau đó chương trình:

1. Gửi `/slow` có **request timeout 150 ms**; chờ future để nhận `HttpTimeoutException`.
2. Mở một **deadline chung 500 ms** cho workflow gồm request `/fast` và `/slow`.
3. Cả hai request của workflow đều có **request timeout riêng 3 giây**, nhưng lần thứ hai không được đợi quá ngân sách chung còn lại. Chương trình chờ bằng `future.get(remaining, TimeUnit.NANOSECONDS)` và cố gắng cancel future chưa hoàn tất sau khi business deadline hết.
4. Chỉ in các kết quả có ý nghĩa cố định; không in số millisecond thực tế vì lịch chạy thread và network loopback không phải thời gian thực tuyệt đối.

Tạo file **AsyncTimeoutLayersDemo.java**:

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
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AsyncTimeoutLayersDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newCachedThreadPool();
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);
        server.createContext("/fast", e -> respond(e, "FAST"));
        server.createContext("/slow", e -> {
            try {
                Thread.sleep(1_200);
                respond(e, "SLOW");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                e.close();
            } catch (IOException disconnected) {
                e.close();
            }
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
            System.out.println("clientConnectTimeoutMs=" +
                    client.connectTimeout().orElseThrow().toMillis());

            HttpRequest shortRequest = HttpRequest.newBuilder(
                    base.resolve("slow"))
                    .timeout(Duration.ofMillis(150)).GET().build();
            System.out.println("requestTimeoutMs=" +
                    shortRequest.timeout().orElseThrow().toMillis());
            try {
                client.sendAsync(shortRequest,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8)).join();
                System.out.println("requestTimedOut=false");
            } catch (CompletionException e) {
                System.out.println("requestTimedOut=" +
                        (e.getCause() instanceof HttpTimeoutException));
            }

            Duration workflowBudget = Duration.ofMillis(500);
            long deadline = System.nanoTime() + workflowBudget.toNanos();
            System.out.println("workflowBudgetMs=" + workflowBudget.toMillis());

            HttpRequest fast = HttpRequest.newBuilder(base.resolve("fast"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(fast,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            HttpResponse<String> firstResponse;
            try {
                firstResponse = awaitBefore(first, deadline);
            } finally {
                if (!first.isDone()) first.cancel(true);
            }
            System.out.println("firstStatus=" + firstResponse.statusCode());

            HttpRequest slow = HttpRequest.newBuilder(base.resolve("slow"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            CompletableFuture<HttpResponse<String>> second =
                    client.sendAsync(slow,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            try {
                awaitBefore(second, deadline);
                System.out.println("workflowTimedOut=false");
            } catch (TimeoutException expected) {
                System.out.println("workflowTimedOut=true");
            } finally {
                if (!second.isDone()) second.cancel(true);
            }
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }

    private static <T> T awaitBefore(
            CompletableFuture<T> future, long deadlineNanos)
            throws InterruptedException, ExecutionException, TimeoutException {
        long remaining = deadlineNanos - System.nanoTime();
        if (remaining <= 0) throw new TimeoutException("workflow expired");
        return future.get(remaining, TimeUnit.NANOSECONDS);
    }

    private static void respond(HttpExchange exchange, String content)
            throws IOException {
        byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

Biên dịch/chạy bằng **JDK 11 trở lên có module `jdk.httpserver`**. Dùng `--release 11` khi kiểm chứng trên JDK mới để buộc kiểm tra API và cú pháp sẵn có ở Java 11:

~~~bash
javac --release 11 --add-modules jdk.httpserver AsyncTimeoutLayersDemo.java
java --add-modules jdk.httpserver AsyncTimeoutLayersDemo
~~~

**Stdout đã kiểm chứng** với JDK 24 và `javac --release 11`:

~~~text
clientConnectTimeoutMs=2000
requestTimeoutMs=150
requestTimedOut=true
workflowBudgetMs=500
firstStatus=200
workflowTimedOut=true
~~~

### Đọc từng dòng kết quả

1. `clientConnectTimeoutMs=2000`: giá trị cấu hình được đọc từ `HttpClient.connectTimeout()`. **Không có thử nghiệm thực sự làm timeout kết nối** ở đây, vì lỗi connect phụ thuộc network và routing.
2. `requestTimeoutMs=150`: `HttpRequest shortRequest` có timeout riêng; không phụ thuộc vào client connect timeout 2.000 ms.
3. `requestTimedOut=true`: server `/slow` chờ khoảng 1.200 ms, dài hơn request timeout 150 ms. `sendAsync` hoàn tất future thất bại và `join()` bọc `HttpTimeoutException` trong `CompletionException`.
4. `workflowBudgetMs=500`: deadline được tạo **một lần** trước khi workflow bắt đầu; các bước sau dùng **cùng timestamp` deadline`** và `System.nanoTime()` để tính phần thời gian còn lại.
5. `firstStatus=200`: `/fast` phản hồi ngay, kịp thời hạn chung trong môi trường kiểm thử.
6. `workflowTimedOut=true`: `/slow` có request timeout riêng đến **3 giây**, nhưng workflow chỉ còn chưa đầy 500 ms. `awaitBefore` ném `TimeoutException` khi hết phần ngân sách còn lại; `finally` cố gắng cancel HTTP future đang chạy.

**Mức độ ổn định:** Đây là ví dụ mô phỏng thời gian. Trên máy cực kỳ quá tải hoặc môi trường hạn chế loopback, ngay request `/fast` cũng có thể không hoàn tất trước 500 ms. Với kiểm thử production, dùng môi trường điều khiển độ trễ và đưa ra ngưỡng phù hợp; không khẳng định scheduler luôn chính xác tới từng mili giây.

**Giới hạn của ví dụ:** `awaitBefore` dùng `future.get(...)` để thể hiện deadline rõ ràng khi in stdout, nên thread chạy chương trình demo **có chặn** trong lúc chờ, mặc dù request được gửi bằng `sendAsync`. Ứng dụng async thực sự có thể thay phần chờ này bằng deadline signal phối hợp qua `CompletionStage`/executor nhưng phải đảm bảo cancel/cleanup original HTTP future. Server chỉ là test fixture, không phải HTTP server cho production.

## 8. Kết hợp timeout với nhiều request và retry

Giả sử workflow budget là 1.000 ms:

~~~text
t=0         Bắt đầu deadline 1.000 ms
t=200       Request A thành công
t=300       Validate/parse A xong
t=450       Request B lần 1 báo lỗi có thể retry
t=650       Backoff xong
t=650       Chỉ còn 350 ms trước deadline
t=1.000     Deadline kết thúc, không được đợi B quá thời điểm này
~~~

Nếu cho mỗi attempt của B một timeout 700 ms, attempt cuối có thể vượt ngân sách tổng. Cách đúng là **tính lại remaining time trước khi bắt đầu attempt**, rồi chọn:

~~~java
Duration remaining = Duration.ofNanos(deadlineNanos - System.nanoTime());
if (remaining.isZero() || remaining.isNegative()) {
    throw new TimeoutException("business deadline reached");
}
Duration perAttemptMax = Duration.ofMillis(700);
Duration requestLimit = remaining.compareTo(perAttemptMax) < 0
        ? remaining : perAttemptMax;

HttpRequest nextAttempt = HttpRequest.newBuilder(uri)
        .timeout(requestLimit)
        .GET().build();
~~~

Đây là **đoạn mã minh họa**, cần imports và biến `deadlineNanos`/`uri` hợp lệ. Trong sản phẩm, cần xét độ phân giải deadline, thời gian chuẩn bị request, thread scheduling, body streaming và giữ nguyên deadline tổng trong retry. Nếu cần trừ thời gian dự phòng cho validation, hãy để buffer trước khi hết ngân sách.

### Retry không phải câu trả lời mặc định cho timeout

Sau một timeout, server có thể đã xử lý xong POST nhưng client chưa nhận response. Nếu gửi lại POST tùy ý, có thể gây side effect trùng như tạo đơn hàng/giao dịch hai lần. Cần hợp đồng endpoint về idempotency, idempotency key, kiểm tra trạng thái giao dịch hoặc chính sách retry đã được thiết kế.

Với GET thường không có side effect, retry vẫn phải có giới hạn số lần và backoff/jitter để tránh tăng tải khi dịch vụ đang lỗi. **Không reset deadline nghiệp vụ khi retry**.

### Các request chạy song song

Nếu A và B độc lập, có thể gửi đồng thời bằng `sendAsync` và kết hợp qua `CompletableFuture.allOf(...)`. Nhưng `allOf` chỉ biết các futures hoàn tất; nó **không tự thực thi deadline nghiệp vụ**. Khi timeout tổng xảy ra, quản lý **danh sách original HTTP futures** để cố gắng cancel những request chưa xong, dọn response body streaming và thông báo đúng nguyên nhân.

Không nên tính “tổng timeout = A.timeout + B.timeout” với hai request chạy song song; thời gian tổng còn phụ thuộc thời gian gửi, xếp hàng, tốc độ network, xử lý kết quả và các yếu tố khác.

## 9. Cancellation không đồng nghĩa dừng server ngay

Trong Java HTTP Client implementation tiêu chuẩn, `CompletableFuture` trả về từ `sendAsync` có thể được hủy bằng `cancel(true)` khi **chưa hoàn tất**. JDK cố gắng hủy HTTP exchange và giải phóng tài nguyên, nhưng **không có bảo đảm hủy được ngay**: request có thể đã được gửi, server có thể vẫn đang xử lý, và kết nối có thể chỉ được dọn bất đồng bộ.

- Với HTTP/1.1, nỗ lực cancel có thể đóng đột ngột kết nối underlying.
- Với HTTP/2, nỗ lực cancel có thể reset stream.
- `cancel(true)` không phải transaction rollback trên server. Nếu request thay đổi dữ liệu, cần thiết kế idempotency và cơ chế kiểm tra kết quả.
- Dù future đã bị cancel, callback hoặc resource tầng ứng dụng có thể cần cleanup riêng.
- Nếu dùng `BodyHandlers.ofInputStream()` hoặc `ofPublisher()`, **future có thể đã hoàn tất sau khi nhận headers trong khi body còn được tiêu thụ**; khi đó cancel future đã hoàn tất không thay thế việc đóng `InputStream` hoặc hủy `Flow.Subscription`.

Đối với deadline nghiệp vụ, khái niệm đúng là **“ngừng dùng kết quả muộn + yêu cầu hủy hoạt động nền + giải phóng tài nguyên”**, thay vì “timeout chắc chắn khiến server ngừng thực hiện”.

### Tránh hủy nhầm một resource được dùng chung

`HttpClient` thường được tái sử dụng cho nhiều request và có thể chia sẻ pool kết nối. Khi một workflow timeout, đừng tùy tiện đóng toàn bộ client dùng chung; điều đó có thể làm hỏng những request hợp lệ của người khác. Quản lý cancellation **theo từng request/stream** và ownership rõ ràng. Với Java 11, `HttpClient` không có hợp đồng `AutoCloseable` như các JDK mới; không viết `try (HttpClient client = ...)` trong ví dụ cần chạy Java 11.

## 10. Vòng đời của body streaming và deadline tổng

`HttpResponse<T>` không đồng nghĩa body luôn có đủ dữ liệu để xử lý ngay. Tùy `BodyHandler<T>`:

| Handler | `T` | Quan hệ với deadline |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Tích lũy body thành chuỗi trước khi response future hoàn tất thành công |
| `BodyHandlers.ofByteArray()` | `byte[]` | Đợi bytes cho body; cần giới hạn dung lượng RAM |
| `BodyHandlers.ofFile(path)` | `Path` | Ghi body xuống file, cần kiểm soát file dở dang nếu timeout |
| `BodyHandlers.ofInputStream()` | `InputStream` | Response có thể được tạo sớm; đọc stream sau đó cần deadline và đóng tài nguyên |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Subscriber phải `request(n)`/`cancel()` và hoàn tất theo policy riêng |
| `BodyHandlers.ofLines()` | `Stream<String>` | Tiêu thụ stream và đóng; không mặc định nội dung hoàn tất khi nhận response |

Khi nghiệp vụ cần đọc toàn bộ body trong deadline, bạn phải quản lý **cả giai đoạn sau khi `HttpResponse` đã sẵn sàng**. Nếu chỉ đặt request timeout, rồi parse hoặc ghi file vô hạn, deadline đầu-cuối vẫn có thể bị vi phạm.

Đặc biệt, không nên làm một callback `thenApply(response -> parseLargeJson(response.body()))` dài nhiều giây mà không tính vào deadline. Việc xử lý trên thread nào và thời điểm nào phụ thuộc completion chain/executor; nên giới hạn CPU, memory và thời gian parser theo nhu cầu.

## 11. Quan sát thời gian: metric và log nào có ích?

Một lần HTTP request bất đồng bộ có thể cần các metric độc lập:

- **Connect failures / connect timeout:** có phát sinh kết nối mới không, `HttpConnectTimeoutException` hay một lỗi kết nối khác?
- **Request timeout:** thời lượng request khi đợi response, `HttpTimeoutException`.
- **Business timeout:** deadline ban đầu, remaining budget trước các bước, step đang thực hiện khi vượt hạn.
- **HTTP status:** mã 2xx/4xx/5xx được trả (không thay thế exception).
- **Cancellation attempted/completed:** code đã yêu cầu cancel future/subscription hay chưa; không suy ra server đã dừng.
- **Streaming body completion:** byte thực nhận, thời điểm EOF/`onComplete`, lỗi/hủy khi nhận.
- **Retry:** attempt index, backoff, nguyên nhân retry, còn bao nhiêu deadline.
- **Tail latency:** các phân vị độ trễ như p95/p99 theo loại endpoint và outcome.

Đừng đưa token, header `Authorization`, cookie, dữ liệu bí mật hoặc URI chứa credentials vào log. Nếu cần correlation, dùng request ID an toàn và log có cấu trúc, tránh in nguyên request/response body nhạy cảm.

### Phân biệt exception khi đo đạc

Với `sendAsync`, khi dùng `join()`, kiểm tra `getCause()` của `CompletionException`. Với `future.get(...)`, kiểm tra `getCause()` của `ExecutionException`. Với `get(timeout, unit)`, chính `TimeoutException` **có thể là timeout của caller đang chờ**, không có nghĩa HTTP client đã phát ra `HttpTimeoutException`.

Không đo latency dựa vào chuỗi `e.getMessage()`; dùng kiểu exception và đồng hồ đơn điệu. Khi `Future` bị hủy, phân loại `CancellationException` riêng.

## 12. Các lỗi thực tế thường gặp

| Ngộ nhận / lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| “`connectTimeout` = toàn bộ thời gian chờ API.” | Kết nối có thể xong nhưng response treo | Đặt request timeout và deadline tổng |
| “Đã tái dùng kết nối vẫn bị connect timeout.” | Sai phạm vi cấu hình | Connect timeout chỉ dùng khi tạo kết nối mới |
| “Request timeout của mỗi lời gọi chính là workflow deadline.” | Nhiều request nối tiếp vượt SLO | Tạo deadline một lần và tính remaining |
| “`sendAsync` có nghĩa không còn chỗ nào block.” | `join`/`get`/downstream block vẫn làm chờ | Phân biệt async send với await/processing |
| “`orTimeout` chắc chắn cancel underlying HTTP.” | Có thể chỉ hoàn tất future ngoại lệ | Quản lý cancellation/cleanup original HTTP future |
| “`future.get(timeout)` sẽ hủy future.” | Future có thể còn tiếp tục hoàn tất | Quyết định `cancel(true)` khi hết hạn |
| “`request.timeout(Duration.ZERO)` là không chờ.” | Ném `IllegalArgumentException` | Duration dương hoặc không đặt |
| “HTTP 504 là `HttpTimeoutException`.” | Hai tầng lỗi khác nhau | Kiểm tra status và exception riêng |
| “Mọi connect failure đều là connect timeout.” | Connection refused/DNS/TLS có thể thất bại sớm | Phân loại `IOException` phù hợp |
| “`HttpConnectTimeoutException` không phải request timeout.” | Nó kế thừa `HttpTimeoutException` | Catch loại con trước |
| “Timeout chứng minh POST chưa thực hiện.” | Có thể trùng giao dịch nếu retry | Dùng idempotency/check-status |
| “Hết timeout thì có thể bỏ mặc response stream.” | Rò rỉ connection/resources | Đóng stream hoặc cancel subscription |
| “`request.timeout` giới hạn mọi parse/DB call.” | Phần việc sau HTTP vẫn chạy lâu | Deadline tổng phải bao trùm downstream |
| “Mỗi retry tạo lại budget đầy đủ.” | Workflow kéo dài vô hạn | Giữ một deadline chung |
| “Đóng `HttpClient` dùng chung khi một call quá hạn.” | Ảnh hưởng request khác | Cancel theo request, quản lý ownership |
| “Timeout luôn chính xác từng ms.” | Scheduler/network gây jitter | Thiết kế budget có dự phòng, kiểm thử tải |
| “Đã có request timeout thì không cần byte budget.” | Response khổng lồ vẫn tốn RAM | Giới hạn byte/streaming/cancel |
| “Dùng `System.currentTimeMillis()` để đo chênh lệch chuẩn.” | Clock wall có thể bị điều chỉnh | Dùng `System.nanoTime()` trong cùng JVM |
| “Có thể truyền raw `nanoTime()` qua server khác.” | Mốc nanoTime không dùng chung | Truyền remaining budget/deadline chuẩn hóa |

## 13. Checklist để thiết kế HTTP bất đồng bộ có deadline

1. **Mục tiêu nghiệp vụ:** workflow cần trả kết quả/fallback trong bao lâu? Có SLO rõ không?
2. **Client:** `connectTimeout` có được đặt dương, hợp với mạng kết nối mới và chính sách proxy/TLS không?
3. **Request:** mỗi `HttpRequest` có `timeout(Duration)` hợp lý? Khi bắt đầu mỗi attempt có lấy `min(cap, remaining)` không?
4. **Deadline chung:** có ghi một lần rồi truyền qua các bước, retry và downstream processing không?
5. **Monotonic:** đo remaining qua `System.nanoTime()` hoặc một cơ chế clock thích hợp, tránh wall-clock jump?
6. **Async future:** phân biệt thời gian HTTP với `get(timeout)`/`orTimeout`/`join()` và hiểu kết quả của future?
7. **Exception:** nhận ra `HttpConnectTimeoutException`, `HttpTimeoutException`, `TimeoutException`, `CancellationException` và HTTP 408/504 khác nhau?
8. **Cancellation:** khi quá hạn có cố gắng cancel những original HTTP futures còn chạy, đồng thời không kỳ vọng rollback server?
9. **Streaming body:** có đọc/đóng/hủy body sau headers và kiểm soát giới hạn bytes, idle, xử lý downstream?
10. **Retry:** có giới hạn số lần/backoff và không tạo side effect trùng do timeout trên POST?
11. **Concurrency:** nếu workflow gọi nhiều API song song, có dùng chung deadline và cancel các nhánh quá hạn mà không ảnh hưởng request không thuộc workflow?
12. **Observability:** có ghi nhận loại timeout, step, elapsed/remaining, metric, không log dữ liệu nhạy cảm?
13. **Java compatibility:** có dùng API Java 11 thật sự tồn tại, tránh dùng `HttpClient.close()` trực tiếp trong mã phải chạy `--release 11`?
14. **Kiểm thử:** có test request nhanh/chậm, hủy, future error, body streaming và deadline nhiều bước bằng server được kiểm soát?

**Kết luận:** `HttpClient.connectTimeout` chỉ bảo vệ **bước tạo kết nối mới**; `HttpRequest.timeout` bảo vệ **một request HTTP**; còn **deadline nghiệp vụ** ràng buộc **toàn bộ chuỗi công việc**, thường phải tự điều phối bằng remaining budget, future timeout/cancellation và cleanup tài nguyên. Ba giới hạn cần phối hợp chứ không thay thế nhau.

## Tài liệu tham khảo chính thức (còn áp dụng)

- [Oracle Java SE 11 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `connectTimeout(Duration)` cho kết nối mới.
- [Oracle Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `timeout(Duration)` cho một request.
- [Oracle Java SE 11 — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): request timeout.
- [Oracle Java SE 11 — `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): connect timeout, là kiểu con của `HttpTimeoutException`.
- [Oracle Java SE 11 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `get(timeout, unit)`, `orTimeout`, `cancel`, `CompletionException`.
- [Oracle Java SE 25 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): hợp đồng connect timeout và tái sử dụng connection hiện hành.
- [Oracle Java SE 25 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): hợp đồng thời hạn request.
- [Oracle Java SE 25 — `HttpClient`](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): sendAsync, completion, cancel best-effort, response streaming.
- [Oracle Java SE 25 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `get(timeout)`/`orTimeout` và trạng thái future.
- [Oracle Java SE 11 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/module-summary.html): HTTP test server loopback cho ví dụ.

Bài học tập trung vào API chuẩn còn hỗ trợ từ Java 11 đến JDK hiện hành; không dùng HTTP Client incubator, không nhầm timeout của HTTP với thời hạn nghiệp vụ và không dựa vào hành vi “hủy chắc chắn” mà thư viện không bảo đảm.