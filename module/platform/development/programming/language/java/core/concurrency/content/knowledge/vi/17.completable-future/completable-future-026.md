# Thời hạn HTTP request so với timeout và cancellation của CompletableFuture

## Mục tiêu và phạm vi

Trong Java, một lệnh HTTP bất đồng bộ thường tạo ra **CompletableFuture**, nhưng việc một future hết thời gian chờ **không đồng nghĩa** kết nối HTTP đã dừng, và việc hủy future **không đồng nghĩa** server đã ngừng xử lý request. Bài này phân biệt ba quyết định độc lập: **đợi bao lâu**, **giới hạn hoạt động HTTP bao lâu**, và **cố gắng dừng tài nguyên đang chạy như thế nào**. Phạm vi là Java 17+ với **java.net.http.HttpClient** và **java.util.concurrent.CompletableFuture**, không phụ thuộc framework.

Sau bài học, bạn có thể chọn timeout đúng tầng, giữ quyền hủy HTTP exchange khi tầng ứng dụng hết hạn, đọc đúng exception và thiết kế một deadline xuyên suốt chuỗi xử lý.

## 1. Ba chiếc đồng hồ khác nhau

| Cơ chế | Tác động trực tiếp | Khi hết hạn/hủy | Có dừng HTTP đang chạy không? |
| --- | --- | --- | --- |
| **HttpClient.Builder.connectTimeout(Duration)** | Thời gian thiết lập kết nối mới | Lỗi kết nối, có thể là **HttpConnectTimeoutException** | Giới hạn giai đoạn kết nối; không phải toàn bộ request |
| **HttpRequest.Builder.timeout(Duration)** | Timeout ở mức thực thi request HTTP | Future từ **sendAsync** hoàn tất ngoại lệ **HttpTimeoutException** nếu phản hồi không đến kịp | HttpClient xử lý timeout của chính exchange; server vẫn có thể đã nhận/xử lý request |
| **CompletableFuture.orTimeout(t, unit)** | Thời gian để *future đó* hoàn tất | Chính future bị hoàn tất ngoại lệ **TimeoutException** | **Không mặc nhiên** gọi cancel lên HTTP exchange |
| **CompletableFuture.completeOnTimeout(value, t, unit)** | Giá trị dự phòng của future đó | Chính future hoàn tất bình thường với **value** | **Không mặc nhiên** dừng hoạt động nguồn |
| **future.get(t, unit)** | Thời gian thread gọi **get** chịu chờ | Thread nhận **TimeoutException** | Future nguồn vẫn có thể tiếp tục; không tự cancel |
| **future.cancel(true)** | Yêu cầu hủy future | Future bị hủy, thường quan sát **CancellationException** | Phụ thuộc future/nguồn; future từ **HttpClient mặc định** hỗ trợ cố gắng hủy HTTP exchange khi dùng **cancel(true)** |

Điểm cần nhớ: **timeout quan sát** (không chờ kết quả nữa) khác **timeout vận chuyển** (HTTP client áp chính sách lên exchange), khác **cancellation** (yêu cầu dừng, không bảo đảm hệ thống bên ngoài đã ngừng).

Ví dụ về trục thời gian:

~~~text
t=0 ms         t=80 ms                    t=800 ms
|--------------|--------------------------|
sendAsync()    tầng CF hết hạn            server dự kiến phản hồi
    |          |
    |          +-- observer: TimeoutException
    +------------------------------------- HTTP có thể vẫn chạy
               |
               +-- nếu gọi transport.cancel(true):
                   HttpClient thử hủy exchange, không bảo đảm server rollback
~~~

**Không có thứ tự ưu tiên cố định** giữa timeout của HTTP, timeout của future và hủy: sự kiện nào hoàn tất future trước thì quyết định kết quả quan sát được. Khi deadline gần nhau, các kết quả hợp lệ có thể khác nhau giữa các lần chạy.

## 2. Timeout của chính HTTP request

Java 17 có HTTP client chuẩn:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.org/resource"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> exchange =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

Đoạn trên là **trích đoạn đặt trong một phương thức phù hợp**, không phải chương trình Java độc lập. Hai timeout có nghĩa khác nhau:

- **connectTimeout** áp cho việc lập kết nối mới; khi tái sử dụng kết nối có sẵn, timeout kết nối không thay thế request timeout.
- **request.timeout** đặt giới hạn của request HTTP. Theo API Java 17, nếu response chưa nhận được trong thời gian này, **sendAsync** hoàn tất ngoại lệ với **HttpTimeoutException**. Nếu không đặt timeout, request không có deadline mặc định từ cấu hình này.
- Một response HTTP với mã **408**, **429** hoặc **504** vẫn là *response HTTP*; không tự động tương đương **HttpTimeoutException**. Muốn coi mã trạng thái là lỗi nghiệp vụ, bạn phải kiểm tra **response.statusCode()**.
- **BodyHandlers.ofString()** thu nhận body thành chuỗi trước khi future hoàn tất; với handler dạng stream, ví dụ **ofInputStream()**, thời điểm future hoàn tất và việc ứng dụng tiêu thụ/đóng stream là hai việc cần quản lý riêng.

Không nên hứa rằng request timeout là SLA tuyệt đối cho *mọi việc* sau HTTP: giải mã JSON, xử lý business, đợi trong executor, ghi database và các retry không nằm trong timeout của một request đơn lẻ.

## 3. Timeout và cancellation ở tầng CompletableFuture

**orTimeout** và **completeOnTimeout** (Java 9+) **trả về chính instance CompletableFuture được gọi**, không tạo ra một wrapper timeout mới. Chúng thay đổi trạng thái hoàn tất của future đó:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

// Tạo một stage quan sát riêng; không đổi trạng thái của source.
CompletableFuture<String> observer =
        source.thenApply(value -> value).orTimeout(100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Nếu 100 ms trôi qua mà **observer** chưa hoàn tất, **observer** nhận **TimeoutException**; **source** vẫn có thể chưa hoàn tất. Ngược lại, nếu gọi **source.orTimeout(...)**, chính **source** bị đánh dấu hoàn tất ngoại lệ. Điều này có thể làm mất cơ hội dùng **source.cancel(true)** về sau vì source đã hoàn tất.

**completeOnTimeout** dùng để trả giá trị dự phòng:

~~~java
CompletableFuture<String> fallback =
        source.thenApply(value -> value)
              .completeOnTimeout("Tạm thời chưa có dữ liệu",
                      100, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Giá trị dự phòng **không xác nhận** request mạng đã kết thúc. Nó còn có thể che đi sự thật rằng một tác vụ phía sau vẫn tiêu tốn băng thông/CPU. Chỉ sử dụng fallback khi nghiệp vụ thực sự cho phép kết quả suy giảm và bạn đã có chính sách dọn dẹp thích hợp.

**get(100, MILLISECONDS)** còn hẹp hơn: nó chỉ giới hạn thời gian thread chờ. Khi **get** ném **TimeoutException**, future có thể tiếp tục hoàn tất sau đó. Trừ khi chủ ý ngắt công việc, không nên coi **get** timeout là hủy.

**cancel(true)** với **CompletableFuture** thông thường đưa future vào trạng thái hủy; bản thân **mayInterruptIfRunning** không khiến CompletableFuture tự ngắt thread thực thi. Tuy nhiên, **CompletableFuture do HttpClient mặc định trả về từ sendAsync có hợp đồng bổ sung**: gọi **cancel(true)** khi chưa hoàn tất sẽ *cố gắng* hủy HTTP exchange để giải phóng tài nguyên. Kết quả hủy là best effort; HTTP/1.1 có thể đóng kết nối, HTTP/2 có thể reset stream, và server có thể đã xử lý request. Không nên suy từ **isCancelled()** rằng thao tác trên server đã được hoàn tác.

## 4. Mẫu phối hợp: deadline HTTP + deadline quan sát + hủy nguồn

Khi một lời gọi phải tuân thủ cả HTTP timeout và ngân sách của tầng gọi, hãy **giữ tham chiếu riêng đến future HTTP gốc**, tạo stage quan sát độc lập, và cố gắng hủy exchange gốc khi tầng quan sát tự hết hạn.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Function;

// Trích đoạn trong phương thức, giả sử client và uri đã được tạo.
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(900))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> transport =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

// thenApply tạo stage phụ; orTimeout thay đổi stage phụ đó.
CompletableFuture<HttpResponse<String>> observed =
        transport.thenApply(Function.identity())
                 .orTimeout(1000, TimeUnit.MILLISECONDS);

observed.whenComplete((response, failure) -> {
    Throwable cause = failure;
    while (cause instanceof CompletionException && cause.getCause() != null) {
        cause = cause.getCause();
    }
    if (cause instanceof TimeoutException) {
        transport.cancel(true); // HttpClient cố gắng abort exchange còn chạy.
    }
});
~~~

Ở mẫu trên, **900 ms** là giới hạn request HTTP; **1000 ms** là giới hạn stage quan sát. Nếu HTTP hết hạn trước, lỗi thường là **HttpTimeoutException** đi qua stage phụ. Nếu stage quan sát hết hạn trước (ví dụ do lịch thực thi/các stage bổ sung), **TimeoutException** kích hoạt yêu cầu hủy exchange gốc. **Không cần dùng cả hai mốc chỉ để “chắc ăn”**: chọn mỗi mốc theo ngữ nghĩa thực tế của hệ thống.

Lưu ý: mẫu này chỉ hủy khi timeout của **observed** được nhận diện. Nếu người dùng chủ động bỏ thao tác hoặc caller hủy một future khác, cần nối tín hiệu hủy đó về **transport** theo chính sách riêng. Tùy triển khai, một future được dẫn xuất trực tiếp từ future có khả năng hủy của HttpClient cũng có thể hỗ trợ hủy exchange; việc giữ handle **transport** giúp đường điều khiển rõ ràng và dễ kiểm thử.

## 5. Chương trình Java 17+ chạy độc lập, không cần Internet

Ví dụ dùng HTTP server cục bộ từ module JDK **jdk.httpserver**. Server cố tình trả lời chậm, nên bạn sẽ thấy một future quan sát hết hạn trước khi exchange HTTP hoàn tất, rồi thấy request timeout do chính HttpClient phát hiện.

Lưu đoạn sau thành **HttpDeadlineDemo.java**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

public class HttpDeadlineDemo {
    static String causeName(Throwable error) {
        while ((error instanceof CompletionException || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error.getClass().getSimpleName();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(800);
                byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } catch (IOException ignored) {
                // Client may have abandoned the exchange.
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/slow");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(1))
                    .build();

            HttpRequest withoutDeadline = HttpRequest.newBuilder(uri).GET().build();
            CompletableFuture<HttpResponse<String>> transport = client.sendAsync(
                    withoutDeadline, HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> observer =
                    transport.thenApply(Function.identity());
            observer.orTimeout(80, TimeUnit.MILLISECONDS);

            try {
                observer.join();
            } catch (CompletionException error) {
                System.out.println("CF observer: " + causeName(error));
            }
            System.out.println("HTTP transport đang chạy: " + !transport.isDone());
            transport.cancel(true); // Best effort: request exchange cancellation.

            HttpRequest withDeadline = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofMillis(150))
                    .GET()
                    .build();
            try {
                client.sendAsync(withDeadline, HttpResponse.BodyHandlers.ofString()).join();
            } catch (CompletionException error) {
                System.out.println("HTTP request: " + causeName(error));
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac --add-modules jdk.httpserver HttpDeadlineDemo.java
java --add-modules jdk.httpserver HttpDeadlineDemo
~~~

Kết quả thông thường trên môi trường cục bộ:

~~~text
CF observer: TimeoutException
HTTP transport đang chạy: true
HTTP request: HttpTimeoutException
~~~

Mô phỏng này đã được biên dịch và chạy với JDK 21 (tương thích cú pháp Java 17). Dòng thứ hai cho biết **orTimeout** trên observer chưa hủy **transport**; sau đó code chủ động gọi **transport.cancel(true)**. Giá trị log có thể khác nếu có lỗi môi trường hoặc lịch thực thi bất thường; đây là ví dụ kiểm chứng cơ chế, không phải cam kết thời gian của hệ điều hành.

## 6. Xử lý exception chính xác

| Tình huống | Dấu hiệu cần nhận diện | Ý nghĩa |
| --- | --- | --- |
| Request timeout từ HttpClient | **HttpTimeoutException**, có thể là **HttpConnectTimeoutException** khi liên quan kết nối | Request HTTP không hoàn thành đúng hạn |
| Stage bị **orTimeout** đánh dấu hết hạn | **TimeoutException** | Stage quan sát hết hạn; nguồn HTTP chưa chắc dừng |
| **get(timeout)** hết hạn | **TimeoutException** do chính lời gọi **get** ném | Người chờ hết kiên nhẫn; future không nhất thiết đã hoàn tất |
| Future bị hủy | **CancellationException** | Future đã nhận tín hiệu hủy; không chứng minh rollback |
| Lỗi I/O, TLS, DNS, remote disconnect | Các lỗi như **IOException**, **SSLException** hoặc nguyên nhân liên quan | Lỗi vận chuyển; không nên tự gán tất cả thành timeout |
| Server trả HTTP 408/429/503/504 | **HttpResponse.statusCode()** | HTTP có response và mã trạng thái; cần chính sách nghiệp vụ riêng |

Với **join()**, một lỗi bất đồng bộ thường đến trong **CompletionException** có **cause** là lỗi gốc; việc hủy chính future có thể ném trực tiếp **CancellationException**. Với **get()**, lỗi bất đồng bộ thường nằm trong **ExecutionException**; còn **get(timeout)** có thể ném **TimeoutException** từ chính thao tác chờ. Vì vậy hãy phân loại theo **cause** sau khi bóc các wrapper phù hợp và **đừng nuốt lỗi** bằng fallback cho mọi loại exception.

Ví dụ bóc nguyên nhân khi xử lý callback:

~~~java
static Throwable unwrap(Throwable error) {
    while ((error instanceof java.util.concurrent.CompletionException
            || error instanceof java.util.concurrent.ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

Đây là phương thức trợ giúp độc lập, có thể đặt trong một class Java. Kiểm tra **instanceof HttpTimeoutException** trước khi quy kết đây là timeout **do HTTP**; một **TimeoutException** thông thường có thể chỉ đến từ tầng CompletableFuture.

## 7. Thiết kế deadline tổng, tránh cộng dồn timeout

Giả sử API phải trả lời trong **1.500 ms**, nhưng một luồng xử lý có thể có: lấy kết nối, một hoặc nhiều request HTTP, parse response, tính toán, retry và backoff. Nếu mỗi bước tự cấp lại 1.500 ms, tổng thời gian có thể vượt xa deadline ban đầu.

Một cách thiết kế hợp lý là lưu **thời điểm hết hạn tuyệt đối của toàn bộ thao tác** bằng đồng hồ đơn điệu **System.nanoTime()**. Trước *mỗi* lần thử, tính lại thời gian còn lại và dùng mức nhỏ hơn giữa giới hạn mỗi HTTP attempt và ngân sách còn lại.

~~~java
// Trích đoạn minh họa logic ngân sách; không phải toàn bộ chương trình.
long deadlineNanos = System.nanoTime()
        + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(1500);

// Ngay trước một HTTP attempt:
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0) {
    throw new java.util.concurrent.TimeoutException("Deadline tổng đã hết");
}
long perAttemptNanos = Math.min(
        remainingNanos,
        java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(700));

HttpRequest attemptRequest = HttpRequest.newBuilder(uri)
        .timeout(java.time.Duration.ofNanos(perAttemptNanos))
        .GET()
        .build();
~~~

**System.nanoTime()** thích hợp để đo khoảng thời gian vì nó không lệ thuộc chỉnh đồng hồ hệ thống như **currentTimeMillis()**. Mẫu cộng số nano ở trên giả định ngân sách ngắn, có giới hạn thực tế; với deadline cực lớn cần lưu ý phép cộng **long** có thể tràn. Khi lập lịch retry/backoff, hãy kiểm tra lại **remainingNanos** và **không tạo request mới** nếu ngân sách đã cạn. Khi request timeout, đừng âm thầm retry vô hạn: phải có giới hạn số lần, backoff và chính sách chỉ retry khi phù hợp tính idempotent.

Nếu tầng giao diện/caller ngừng quan tâm, có thể dùng một tín hiệu cancellation riêng để gọi **transport.cancel(true)** ngay, thay vì chỉ chờ deadline. Tín hiệu đó nên được truyền rõ ràng qua các tầng; hoàn tất một future phụ không tự chứng minh rằng toàn bộ chuỗi xử lý đã được dọn dẹp.

## 8. Tình huống thực tế: lựa chọn đúng cơ chế

**A. Ứng dụng gọi một endpoint đọc dữ liệu và cần giới hạn hoạt động mạng.** Đặt **HttpRequest.timeout** phù hợp, có thể thêm **connectTimeout**. Nếu tầng caller có deadline tổng, tính phần thời gian còn lại và quản lý cancellation qua handle gốc.

**B. Giao diện cần hiển thị dữ liệu cache sau 100 ms.** Một stage quan sát dùng **completeOnTimeout(cacheValue, 100, MILLISECONDS)** có thể hợp lý khi việc cập nhật cache nền được **chủ ý** cho phép tiếp tục. Nếu không muốn yêu cầu ngầm tiếp tục chạy, phải có chính sách hủy riêng.

**C. Người dùng bấm “Hủy”.** Nếu request chưa hoàn tất, gọi **cancel(true)** trên future HTTP gốc. Hiển thị trạng thái “đã gửi yêu cầu hủy” theo đúng ngữ nghĩa; tránh khẳng định server chưa nhận hoặc đã rollback giao dịch.

**D. Gửi POST tạo đơn hàng, client timeout.** Server có thể đã tạo đơn trước khi client nhận response. Retry ngay có thể tạo bản ghi trùng. Dùng **idempotency key** hoặc cơ chế dò trạng thái theo giao thức của dịch vụ; timeout/cancellation phía client không thay thế xử lý nhất quán ở server.

**E. Có thể nhận response sớm nhưng ứng dụng xử lý lâu.** Request timeout không bao trùm toàn bộ parse/transform/sau xử lý. Dùng deadline tổng cho pipeline, đưa xử lý CPU nặng sang executor thích hợp khi cần, và thiết kế tác vụ có điểm kiểm tra cancellation nếu muốn dừng hợp tác.

## 9. Các lỗi thường gặp và cách tránh

1. **Gọi orTimeout trực tiếp trên future HTTP gốc rồi cho rằng đã dừng request.** orTimeout chỉ hoàn tất future ngoại lệ. Hãy quản lý handle HTTP gốc và cơ chế hủy riêng.
2. **Gọi cancel(true) rồi cho rằng server chắc chắn chưa xử lý.** Hủy là best effort. Giao dịch có tác dụng phụ phải có idempotency/đối soát.
3. **Dùng get(timeout) làm HTTP timeout.** get chỉ giới hạn thời gian thread chờ; phải đặt request timeout hoặc tự xử lý cancellation.
4. **Coi connectTimeout là timeout của toàn request.** Nó chỉ giới hạn bước kết nối mới.
5. **Dùng completeOnTimeout để trả thành công giả.** Giá trị fallback cần được đánh dấu/hiểu là dữ liệu dự phòng, không phải response HTTP xác thực.
6. **Gom tất cả CompletionException thành TimeoutException.** Luôn bóc cause; có thể là lỗi I/O, DNS, TLS, bug xử lý hoặc cancellation.
7. **Tạo retry với timeout đầy đủ cho mỗi lượt.** Tính lại ngân sách còn lại từ deadline tổng; ngăn retry sau khi hết hạn.
8. **Không dọn body dạng stream hoặc tác vụ tiếp theo.** Với **ofInputStream()** và publisher/subscriber tùy chỉnh, hoàn tất future không thay trách nhiệm đóng/từ chối tiêu thụ tài nguyên phù hợp.

## 10. Checklist khi review code

- Deadline cần ràng buộc **HTTP request**, **thời gian chờ của caller**, hay **toàn bộ nghiệp vụ**?
- Đã cấu hình **connectTimeout** và **HttpRequest.timeout** theo mục đích riêng chưa?
- **orTimeout/completeOnTimeout** có đang làm thay đổi chính future mà code khác cần hủy không?
- Có giữ handle để gọi **cancel(true)** cho request đang chạy khi deadline tổng/caller yêu cầu hủy không?
- Sau cancellation, code có thừa nhận server vẫn có thể hoàn tất tác dụng phụ không?
- Lỗi đã được phân loại theo **HttpTimeoutException**, **TimeoutException**, **CancellationException**, lỗi I/O và HTTP status chưa?
- Mọi retry và backoff có dùng **thời gian còn lại**, giới hạn số lượt và cơ chế idempotency phù hợp không?
- Có test cả trường hợp thành công trước deadline, timeout HTTP, timeout tầng future, user cancel và race đúng sát deadline không?

## Tài liệu chuẩn

- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): **sendAsync**, future có thể hủy và tính best effort của cancellation.
- [Java 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): timeout của request.
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): **orTimeout**, **completeOnTimeout**, **cancel**.
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): **get(timeout)** và **cancel**.

**Thông điệp cốt lõi:** **Không chờ nữa** là quyết định của tầng quan sát; **hết hạn HTTP** là quyết định của tầng vận chuyển; **hủy** là yêu cầu thu hồi công việc/tài nguyên với kết quả best effort. Thiết kế đúng phải chọn rõ từng tầng và đo tất cả theo cùng deadline nghiệp vụ khi cần.
