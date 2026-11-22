# Gửi HTTP đồng bộ và sendAsync với CompletableFuture trong Java 17

Java 11 trở lên cung cấp HttpClient trong package java.net.http để gửi HTTP request. Với Java 17, có hai cách gọi chính:

- **send()** gửi request đồng bộ: luồng gọi chờ cho đến khi nhận response hoặc gặp lỗi.
- **sendAsync()** gửi request bất đồng bộ: phương thức trả về ngay một CompletableFuture<HttpResponse<T>> để chương trình xử lý kết quả khi hoàn tất.

Hai cách gọi dùng chung HttpClient, HttpRequest, HttpResponse và BodyHandler. Khác biệt quan trọng nằm ở **cách điều khiển luồng thực thi và xử lý kết quả**. Chọn send() khi luồng hiện tại có thể chờ và logic tuần tự dễ hiểu hơn; chọn sendAsync() khi cần phối hợp nhiều request, không muốn chặn luồng gọi hoặc muốn kết hợp kết quả bằng CompletableFuture.

sendAsync không tự làm toàn bộ chương trình nhanh hơn. Nó thay đổi cách quản lý thời gian chờ và hoàn tất tác vụ. Vẫn cần xác định timeout, executor, xử lý lỗi, giới hạn concurrency và cách tiêu thụ response body.

## 1. HttpClient trong Java 17

HttpClient là API HTTP hiện đại có sẵn trong JDK từ Java 11. Client có thể cấu hình version, redirect, proxy, authenticator, timeout kết nối và executor.

Tạo một client:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

Các cấu hình trên có ý nghĩa:

- connectTimeout giới hạn thời gian thiết lập kết nối. Đây không phải timeout tổng thể của mỗi request.
- followRedirects quyết định cách client xử lý redirect. NORMAL theo các quy tắc redirect thông thường; NEVER tắt redirect; ALWAYS cho phép mọi redirect theo chính sách API.
- version là phiên bản HTTP mong muốn. Client có thể thương lượng hoặc dùng phiên bản khác tùy khả năng của server và cấu hình.

Có thể tạo client đơn giản:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

Nên tái sử dụng một HttpClient cho nhiều request thay vì tạo mới cho mỗi lần gọi. Client quản lý kết nối và có thể tái sử dụng chúng; tạo client liên tục làm mất lợi ích pooling và tăng overhead.

## 2. Tạo HttpRequest

HttpRequest mô tả request cần gửi: URI, method, headers, body và timeout.

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/users/42"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Một request POST có body:

~~~java
String json = """
        {"name":"Lan","active":true}
        """;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/users"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(json))
        .build();
~~~

BodyPublisher tạo nội dung request. Một số publisher thường dùng:

| BodyPublisher | Khi phù hợp |
| --- | --- |
| noBody() | Request không có body |
| ofString(text) | Gửi nội dung văn bản hoặc JSON đã serialize |
| ofByteArray(bytes) | Gửi mảng byte |
| ofFile(path) | Gửi nội dung file |
| ofInputStream(supplier) | Cung cấp stream theo yêu cầu, cần quản lý việc mở và đọc stream đúng cách |

Không tự đặt Content-Length nếu không cần; BodyPublisher cung cấp thông tin về body cho client. Header Content-Type mô tả định dạng nội dung, không tự serialize object Java thành JSON. Ứng dụng cần dùng thư viện JSON hoặc cơ chế serialize đã chọn để tạo chuỗi/byte.

## 3. Gửi đồng bộ bằng send()

send() gửi request và chờ response. Ví dụ:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class SyncHttpExample {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Body: " + response.body());
    }
}
~~~

send() chỉ trả về sau khi response được xử lý theo BodyHandler. Trong lúc chờ, luồng gọi không thể tiếp tục thực hiện các câu lệnh sau send().

Phương thức có thể ném:

- IOException nếu có lỗi I/O hoặc lỗi xử lý request/response.
- InterruptedException nếu luồng đang chờ bị interrupt.

HTTP status như 404 hoặc 500 thường vẫn tạo một HttpResponse bình thường. Chúng không tự động trở thành IOException chỉ vì status là lỗi. Ứng dụng phải kiểm tra response.statusCode() theo hợp đồng API.

### Xử lý InterruptedException

Khi một phương thức không thể khai báo InterruptedException và phải chuyển lỗi sang tầng trên, nên khôi phục interrupt status trước khi chuyển tiếp:

~~~java
try {
    HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    return response.body();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP request was interrupted", ex);
}
~~~

Không nên bắt InterruptedException rồi bỏ qua. Interrupt là tín hiệu điều khiển luồng thực thi; xóa tín hiệu đó có thể làm tầng quản lý tác vụ không thể dừng công việc đúng cách.

## 4. Gửi bất đồng bộ bằng sendAsync()

sendAsync() khởi tạo request và trả về CompletableFuture ngay khi lời gọi đã được thiết lập. Kết quả HTTP sẽ có khi future hoàn tất:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString());
~~~

Kiểu trả về:

~~~java
CompletableFuture<HttpResponse<T>>
~~~

Trong đó T là kiểu body do BodyHandler chọn, ví dụ String, byte[], Path hoặc InputStream.

Ví dụ:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncHttpExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString());

        future.thenAccept(response -> {
            System.out.println("Status: " + response.statusCode());
            System.out.println("Body: " + response.body());
        }).exceptionally(error -> {
            System.err.println("Request failed: " + error);
            return null;
        });

        // Không gọi join/get ở đây nếu mục tiêu là để luồng hiện tại tiếp tục.
    }
}
~~~

Trong ứng dụng server hoặc desktop đang có event loop/lifecycle quản lý tác vụ, không cần chặn luồng chỉ để chờ future. Khi chương trình ví dụ là một main method ngắn, JVM có thể kết thúc sau khi main hoàn tất nếu không còn hoạt động giữ tiến trình; ví dụ thực tế nên được chạy trong một ứng dụng có lifecycle phù hợp hoặc chờ có chủ đích ở tầng điều phối.

### sendAsync không có nghĩa là callback luôn chạy trên một thread cụ thể

sendAsync không bắt buộc callback của mọi stage chạy trên thread gọi sendAsync. Với các phương thức CompletableFuture không có hậu tố Async như thenApply hoặc thenAccept, hành động có thể chạy trên thread hoàn tất future hoặc thread gọi đăng ký stage nếu future đã hoàn tất. Các phương thức có hậu tố Async dùng executor mặc định của CompletableFuture hoặc executor được truyền tường minh.

Do đó:

- Không giả định thenApply luôn chạy trên main thread.
- Không đặt công việc blocking hoặc CPU nặng vào callback không Async nếu không kiểm soát được thread thực thi.
- Dùng thenApplyAsync(..., executor) hoặc thenAcceptAsync(..., executor) khi cần chỉ định nơi chạy callback.

## 5. So sánh send() và sendAsync()

| Tiêu chí | send() | sendAsync() |
| --- | --- | --- |
| Kiểu trả về | HttpResponse<T> | CompletableFuture<HttpResponse<T>> |
| Luồng gọi | Chờ kết quả | Trả về future để xử lý sau |
| Lỗi I/O | Ném IOException trực tiếp | Future hoàn tất exceptional |
| Interrupt | Ném InterruptedException | Không có InterruptedException trực tiếp từ lời gọi; có thể cancel future hoặc quản lý timeout |
| Ghép nhiều request | Thường cần tự quản lý thread hoặc gọi tuần tự | Có thể dùng allOf, thenCombine, thenCompose |
| Logic đơn giản tuần tự | Dễ đọc | Có thêm khái niệm future |
| Tác vụ bất đồng bộ | Chặn luồng gọi | Không chặn luồng gọi trong lúc chờ phản hồi |
| Kết quả HTTP 4xx/5xx | Trả HttpResponse | Future hoàn tất bình thường với HttpResponse |

Không nên chọn sendAsync chỉ vì nó “mới hơn”. Nếu một command-line tool chỉ gọi một API rồi cần kết quả ngay, send() có thể đơn giản hơn. Nếu một server cần phối hợp nhiều request độc lập hoặc không muốn chặn thread xử lý request, sendAsync có thể phù hợp.

## 6. Xử lý kết quả bằng CompletableFuture

CompletableFuture biểu diễn một kết quả có thể chưa có ở thời điểm hiện tại. Khi kết quả hoàn tất, có thể nối các stage xử lý tiếp theo.

### thenApply: biến đổi kết quả

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body);
~~~

thenApply nhận kết quả của stage trước và trả về giá trị mới. Trong ví dụ, kiểu được biến đổi từ CompletableFuture<HttpResponse<String>> thành CompletableFuture<String>.

### thenAccept: tiêu thụ kết quả, không tạo giá trị mới

~~~java
CompletableFuture<Void> logged =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenAccept(response ->
                        System.out.println(response.statusCode()));
~~~

thenAccept phù hợp khi chỉ cần thực hiện hành động với kết quả.

### thenRun: chạy hành động không cần nhận kết quả

~~~java
CompletableFuture<Void> finished =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding())
                .thenRun(() -> System.out.println("Request completed"));
~~~

thenRun chỉ quan tâm stage trước hoàn tất bình thường, không nhận response làm tham số.

### thenCompose: nối một thao tác bất đồng bộ khác

Giả sử request đầu tiên lấy user ID, request thứ hai lấy chi tiết user. Không nên tạo CompletableFuture lồng nhau:

~~~java
CompletableFuture<CompletableFuture<User>> nested =
        client.sendAsync(idRequest, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> fetchUserAsync(response.body()));
~~~

Dùng thenCompose để làm phẳng:

~~~java
CompletableFuture<User> userFuture =
        client.sendAsync(idRequest, HttpResponse.BodyHandlers.ofString())
                .thenCompose(response ->
                        fetchUserAsync(response.body()));
~~~

thenCompose hữu ích khi bước tiếp theo cũng trả về CompletionStage/CompletableFuture.

### thenCombine: kết hợp hai tác vụ độc lập

Nếu hai request không phụ thuộc nhau, có thể chạy đồng thời và kết hợp kết quả:

~~~java
CompletableFuture<User> userFuture = fetchUserAsync("42");
CompletableFuture<List<Order>> ordersFuture = fetchOrdersAsync("42");

CompletableFuture<UserDashboard> dashboardFuture =
        userFuture.thenCombine(
                ordersFuture,
                UserDashboard::new);
~~~

thenCombine đợi cả hai stage hoàn tất bình thường rồi gọi hàm kết hợp.

## 7. Gửi nhiều request độc lập và đợi tất cả bằng allOf()

Ví dụ lấy thông tin nhiều endpoint:

~~~java
List<URI> uris = List.of(
        URI.create("https://example.com/a"),
        URI.create("https://example.com/b"),
        URI.create("https://example.com/c"));

List<CompletableFuture<HttpResponse<String>>> futures =
        uris.stream()
                .map(uri -> HttpRequest.newBuilder(uri).GET().build())
                .map(req -> client.sendAsync(
                        req,
                        HttpResponse.BodyHandlers.ofString()))
                .toList();

CompletableFuture<Void> all =
        CompletableFuture.allOf(
                futures.toArray(CompletableFuture[]::new));

CompletableFuture<List<HttpResponse<String>>> responses =
        all.thenApply(ignored ->
                futures.stream()
                        .map(CompletableFuture::join)
                        .toList());
~~~

allOf trả về CompletableFuture<Void>, hoàn tất khi tất cả future đầu vào hoàn tất. Sau khi all hoàn tất bình thường, có thể join từng future để lấy kết quả mà không phải chờ thêm.

Lưu ý:

- Nếu một future đầu vào hoàn tất exceptional, allOf cũng hoàn tất exceptional khi các future đầu vào đều đã hoàn tất.
- allOf không tự trả về list kết quả; cần giữ danh sách future và thu kết quả sau.
- Nếu có nhiều request, phải giới hạn số request đồng thời theo capacity của dịch vụ, connection pool và rate limit. Khởi tạo hàng trăm nghìn future cùng lúc có thể gây áp lực bộ nhớ và hệ thống.
- Không nên gọi join() trước allOf trong khi muốn chạy song song, vì join từng phần tử tuần tự có thể làm luồng điều phối chờ không cần thiết.

### allOf không tự giới hạn concurrency

Nếu danh sách request rất lớn, có thể xử lý theo batch hoặc dùng một cơ chế giới hạn số tác vụ in-flight. Ví dụ đơn giản theo batch:

~~~java
static CompletableFuture<Void> sendInBatches(
        HttpClient client,
        List<URI> uris,
        int batchSize) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    CompletableFuture<Void> chain = CompletableFuture.completedFuture(null);

    for (int start = 0; start < uris.size(); start += batchSize) {
        int from = start;
        int to = Math.min(start + batchSize, uris.size());

        chain = chain.thenCompose(ignored -> {
            List<CompletableFuture<HttpResponse<Void>>> batch =
                    uris.subList(from, to).stream()
                            .map(uri -> HttpRequest.newBuilder(uri).GET().build())
                            .map(request -> client.sendAsync(
                                    request,
                                    HttpResponse.BodyHandlers.discarding()))
                            .toList();

            return CompletableFuture.allOf(
                    batch.toArray(CompletableFuture[]::new));
        });
    }

    return chain;
}
~~~

Batch tiếp theo chỉ bắt đầu sau khi batch hiện tại hoàn tất. Đây là cách giới hạn concurrency đơn giản; nó có thể giảm throughput nếu một request chậm làm cả batch phải chờ. Hệ thống tải lớn có thể cần semaphore, bounded queue hoặc rate limiter để điều tiết mượt hơn.

## 8. Xử lý lỗi trong sendAsync

Lỗi khi gửi request bất đồng bộ thường làm future hoàn tất exceptional. Các thao tác xử lý lỗi phổ biến:

| API | Mục đích |
| --- | --- |
| exceptionally(fn) | Chuyển lỗi thành giá trị thay thế hoặc ném lại lỗi |
| handle(fn) | Xử lý cả kết quả bình thường và lỗi |
| whenComplete(fn) | Quan sát kết quả/lỗi để logging hoặc cleanup; không chủ yếu dùng để chuyển kết quả |
| exceptionallyCompose(fn) | Khi lỗi, nối một stage bất đồng bộ khác (Java 12+) |

### exceptionally

~~~java
CompletableFuture<String> body =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body)
                .exceptionally(error -> {
                    logFailure(error);
                    return "Fallback content";
                });
~~~

exceptionally biến lỗi thành kết quả bình thường nếu callback trả về fallback. Sau stage này, future có thể hoàn tất bình thường với nội dung fallback.

Nếu không muốn nuốt lỗi, ném lại:

~~~java
.exceptionally(error -> {
    throw new CompletionException(error);
});
~~~

### handle

~~~java
CompletableFuture<String> outcome =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .handle((response, error) -> {
                    if (error != null) {
                        return "Transport error: " + error.getMessage();
                    }
                    return "HTTP " + response.statusCode();
                });
~~~

handle được gọi khi stage trước hoàn tất bình thường hoặc exceptional. Nếu error khác null, response thường là null.

### whenComplete

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .whenComplete((response, error) -> {
                    if (error != null) {
                        logFailure(error);
                    } else {
                        logStatus(response.statusCode());
                    }
                });
~~~

whenComplete phù hợp cho quan sát và logging. Nếu callback whenComplete ném exception, stage được trả về có thể hoàn tất exceptional. Tránh thực hiện công việc blocking lâu trong callback này.

### Exception thường được bọc

Khi lấy kết quả bằng join(), lỗi từ pipeline thường được bọc trong CompletionException. Với get(), lỗi có thể xuất hiện dưới dạng ExecutionException; get() cũng có thể ném InterruptedException.

~~~java
try {
    HttpResponse<String> response = future.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    // Xử lý nguyên nhân thực tế.
}
~~~

Không chỉ log CompletionException rồi bỏ qua cause. Cần phân biệt lỗi mạng, timeout, lỗi body handler, cancellation và lỗi do callback nghiệp vụ.

## 9. HTTP status lỗi không đồng nghĩa future exceptional

Đây là khác biệt quan trọng khi làm việc với HttpClient:

- Lỗi kết nối, DNS, timeout hoặc I/O có thể khiến future hoàn tất exceptional.
- Server trả HTTP 404, 429 hoặc 500 vẫn là một HTTP response hợp lệ ở tầng giao thức. Future thường hoàn tất bình thường và response.statusCode() chứa mã tương ứng.

Vì vậy, phải kiểm tra status:

~~~java
CompletableFuture<String> body =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new CompletionException(
                                new IllegalStateException("Unexpected HTTP status: " + status));
                    }
                    return response.body();
                });
~~~

Có thể tạo kiểu lỗi riêng chứa status, headers và response body để tầng trên xử lý retry hoặc hiển thị thông báo. Đừng tự retry mọi status 4xx/5xx: chính sách retry phụ thuộc method, idempotency, mã status, Retry-After và hợp đồng API.

### Phân biệt transport error và application error

Một cách tổ chức:

1. Transport layer gửi request và nhận HttpResponse.
2. HTTP adapter kiểm tra status và chuyển response lỗi thành exception hoặc kiểu kết quả phù hợp.
3. Application layer xử lý lỗi theo nghiệp vụ.

Việc tách này giúp code không nhầm “không kết nối được server” với “server đã trả lời rằng tài nguyên không tồn tại”.

## 10. Timeout cho kết nối và cho từng request

Có hai timeout thường cần phân biệt:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
~~~

- connectTimeout áp dụng cho việc thiết lập kết nối nếu cần kết nối mới.
- HttpRequest.timeout giới hạn thời gian cho request; nếu response không đến trong thời gian quy định, thao tác có thể thất bại với HttpTimeoutException.

Với send(), HttpTimeoutException là một dạng IOException. Với sendAsync(), future hoàn tất exceptional và nguyên nhân có thể được bọc trong CompletionException khi dùng stage/join.

### Timeout ở CompletableFuture

Java 9 trở lên cung cấp orTimeout và completeOnTimeout:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .orTimeout(5, TimeUnit.SECONDS);
~~~

orTimeout làm future hoàn tất exceptional với TimeoutException nếu thời gian vượt quá giới hạn.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .completeOnTimeout(fallbackResponse, 5, TimeUnit.SECONDS);
~~~

completeOnTimeout hoàn tất future bình thường bằng giá trị fallback nếu timeout.

Không nhầm timeout của CompletableFuture với việc chắc chắn hủy request HTTP bên dưới. orTimeout và completeOnTimeout tác động tới future được gọi; chúng không tự bảo đảm server đã dừng xử lý hoặc request chưa được gửi. Nếu cần giới hạn request, cấu hình HttpRequest.timeout và xác định chính sách cancellation riêng.

## 11. Cancellation và giới hạn của việc hủy

Có thể yêu cầu hủy future:

~~~java
boolean cancelled = future.cancel(true);
~~~

Với future từ sendAsync, việc cancel có thể yêu cầu HttpClient hủy exchange tương ứng. Tuy nhiên:

- Không bảo đảm request chưa được gửi.
- Không bảo đảm server đã dừng xử lý.
- Không hoàn tác side effect mà server đã thực hiện.
- Không thay thế timeout, idempotency hoặc cơ chế hủy ở tầng nghiệp vụ.

Nếu request là POST tạo giao dịch, client timeout hoặc cancel không chứng minh giao dịch chưa được tạo. Muốn retry an toàn cần thiết kế idempotency key hoặc cơ chế truy vấn trạng thái giao dịch.

Cancellation trong CompletableFuture là một dạng hoàn tất exceptional; dependent stages thường quan sát lỗi qua CompletionException/CancellationException theo cách API quy định. Khi thiết kế pipeline, cần xác định stage nào chịu trách nhiệm cleanup tài nguyên và thông báo trạng thái hủy.

## 12. BodyHandler và cách đọc response body

BodyHandler quyết định cách HttpClient nhận và cung cấp body. Chọn đúng handler ảnh hưởng bộ nhớ và cách quản lý tài nguyên.

| BodyHandler | Kiểu body | Phù hợp |
| --- | --- | --- |
| ofString() | String | JSON/text nhỏ hoặc vừa |
| ofByteArray() | byte[] | Payload nhị phân vừa phải |
| ofFile(path) | Path | Tải file xuống đĩa |
| discarding() | Void | Chỉ cần status/header, bỏ qua body |
| ofInputStream() | InputStream | Đọc body theo luồng, cần tự đóng stream |
| ofLines() | Stream<String> | Body dạng văn bản theo dòng; cần quản lý stream/lifecycle |

### Tải file bằng sendAsync

~~~java
Path destination = Path.of("download.bin");

CompletableFuture<HttpResponse<Path>> download =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofFile(destination));
~~~

BodyHandler.ofFile ghi body vào file đích. Cần xác định rõ chính sách khi file đã tồn tại và xử lý lỗi ghi file. Nếu file là dữ liệu quan trọng, có thể tải vào file tạm rồi xác minh và di chuyển atomically theo khả năng filesystem.

### ofInputStream cần đóng stream

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    try (InputStream body = response.body()) {
        body.transferTo(OutputStream.nullOutputStream());
    } catch (IOException ex) {
        throw new CompletionException(ex);
    }
});
~~~

Response có thể hoàn tất khi InputStream đã sẵn sàng để đọc, trong khi việc đọc body còn tiếp tục. Phải đóng stream sau khi dùng để giải phóng tài nguyên. Nếu xử lý body lâu, hãy cân nhắc nơi chạy callback và không chặn executor dùng chung.

### Chỉ cần status/header

~~~java
CompletableFuture<HttpResponse<Void>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
~~~

discarding() bỏ qua body, thích hợp cho request mà ứng dụng chỉ quan tâm status/header hoặc không cần tải nội dung.

## 13. Chọn executor cho công việc tiếp nối

HttpClient.Builder có thể nhận executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);

HttpClient client = HttpClient.newBuilder()
        .executor(executor)
        .build();
~~~

Executor cấu hình cho HttpClient được dùng cho các tác vụ bất đồng bộ và dependent tasks theo hợp đồng của API client. Nếu tự quản lý executor, cần có chính sách shutdown phù hợp với lifecycle ứng dụng; không tạo một pool mới cho mỗi request.

Đối với CompletableFuture, các phương thức có hậu tố Async cho phép truyền executor cụ thể:

~~~java
CompletableFuture<String> parsed =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApplyAsync(
                        response -> parseLargeJson(response.body()),
                        executor);
~~~

Điều này giúp tách phần I/O HTTP khỏi phần xử lý CPU nặng. Tuy nhiên, nếu executor có quá ít thread hoặc queue không giới hạn, workload có thể bị nghẽn hoặc tăng bộ nhớ. Cần chọn kích thước và queue theo tải thực tế.

Không dùng common pool cho công việc blocking kéo dài nếu có thể làm ảnh hưởng các tác vụ khác. Với xử lý blocking, dùng executor chuyên dụng có giới hạn và quản lý backpressure.

### Đóng executor đúng vòng đời

Nếu ứng dụng tạo executor:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);
try {
    // Dùng HttpClient và các tác vụ.
} finally {
    executor.shutdown();
}
~~~

Trong ứng dụng dài hạn, executor thường là thành phần được quản lý bởi dependency injection hoặc application lifecycle. Không shutdown executor ngay sau khi gửi request nếu các tác vụ bất đồng bộ còn phụ thuộc vào nó.

## 14. Gửi request POST và xử lý kết quả bất đồng bộ

Ví dụ đầy đủ hơn:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class PostAsyncExample {

    static CompletableFuture<String> createUser(
            HttpClient client,
            String json) {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users"))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    int status = response.statusCode();
                    if (status < 200 || status >= 300) {
                        throw new CompletionException(
                                new IllegalStateException(
                                        "Create user failed with HTTP " + status
                                                + ": " + response.body()));
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        String json = "{\"name\":\"Lan\"}";

        CompletableFuture<String> result =
                createUser(client, json);

        result.whenComplete((body, error) -> {
            if (error != null) {
                System.err.println("Create failed: " + error);
            } else {
                System.out.println("Created: " + body);
            }
        });
    }
}
~~~

Đây là ví dụ minh họa; endpoint example.com không phải API tạo user thực. Ứng dụng thật cần endpoint, xác thực, serializer, chính sách retry và xử lý response phù hợp.

## 15. Kiểm thử code gọi HTTP

Không nên để unit test phụ thuộc trực tiếp vào một dịch vụ Internet công cộng. Các cách tiếp cận:

- Dùng mock server chạy cục bộ để kiểm thử request, headers, body, status, timeout và lỗi kết nối.
- Đưa HttpClient hoặc một interface adapter vào constructor để thay thế trong test.
- Dùng Clock/timeout có thể kiểm soát nếu logic có deadline.
- Tách phần xử lý HttpResponse khỏi phần gọi mạng để test bằng response giả.

### Kiểm thử hàm xử lý status độc lập

~~~java
static String requireSuccess(HttpResponse<String> response) {
    int status = response.statusCode();
    if (status < 200 || status >= 300) {
        throw new IllegalStateException("HTTP " + status);
    }
    return response.body();
}
~~~

Hàm này có thể kiểm thử mà không cần gửi request:

~~~java
// Có thể dùng Mockito hoặc một implementation HttpResponse test đơn giản.
// Kiểm tra status 200, 404, 500 theo hợp đồng.
~~~

### Kiểm thử future exceptional

Có thể dùng CompletableFuture.failedFuture (Java 9+) để test logic xử lý lỗi ở tầng trên:

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IOException("Connection refused"));

CompletableFuture<String> handled =
        failed.exceptionally(error -> "fallback");
~~~

Đây không thay thế integration test cho HttpClient, nhưng giúp kiểm tra chuỗi xử lý CompletableFuture mà không cần phụ thuộc mạng.

### Kiểm thử timeout và cancellation

Timeout/cancellation phụ thuộc scheduler và I/O thật; test nên dùng mock server hoặc server local có thể điều khiển độ trễ. Tránh dùng sleep dài tùy tiện và tránh endpoint Internet công cộng vì thời gian mạng không ổn định.

## 16. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi sendAsync rồi lập tức join | Đã biến luồng gọi thành chờ đồng bộ | Chỉ join ở tầng thực sự cần kết quả; nối các stage nếu có thể |
| Cho rằng 404/500 làm future exceptional | Nhầm HTTP status với lỗi transport | Kiểm tra response.statusCode() |
| Quên xử lý exception trong pipeline | Future có thể hoàn tất exceptional | Dùng handle/exceptionally/whenComplete phù hợp |
| Dùng thenApply cho xử lý blocking nặng | Callback có thể chạy trên thread hoàn tất future | Dùng thenApplyAsync với executor phù hợp |
| Dùng allOf và nghĩ nó trả list response | allOf chỉ trả CompletableFuture<Void> | Giữ list future và thu kết quả sau khi all hoàn tất |
| Gửi hàng nghìn request cùng lúc | Không giới hạn concurrency và bộ nhớ | Batch, semaphore hoặc bounded executor |
| Dùng orTimeout và nghĩ request chắc chắn đã dừng | Timeout future không bảo đảm server hủy xử lý | Cấu hình HttpRequest.timeout và thiết kế cancellation/idempotency |
| Retry POST sau timeout ngay lập tức | Server có thể đã thực hiện side effect | Dùng idempotency key và truy vấn trạng thái |
| Không đóng InputStream từ BodyHandlers.ofInputStream | Rò rỉ tài nguyên | Dùng try-with-resources |
| Tạo HttpClient cho từng request | Mất khả năng tái sử dụng kết nối | Tái sử dụng client |
| Dùng executor không có giới hạn cho tác vụ blocking | Queue/thread có thể tăng không kiểm soát | Executor bounded và backpressure |
| Bắt InterruptedException rồi bỏ qua | Mất tín hiệu interrupt | Khôi phục interrupt hoặc truyền tiếp |
| Nghĩ sendAsync làm callback chạy trên main thread | Thread thực thi stage phụ thuộc loại stage/executor | Chỉ định executor cho callback cần kiểm soát |
| Đưa object Java vào BodyPublisher trực tiếp | BodyPublisher nhận byte/text/stream, không tự serialize object | Serialize bằng thư viện phù hợp |

## 17. Khi nào chọn send và khi nào chọn sendAsync?

| Tình huống | Lựa chọn gợi ý |
| --- | --- |
| Một request trong CLI, cần kết quả ngay | send() |
| Batch nhỏ, xử lý tuần tự đơn giản | send() có thể đủ |
| Server cần không chặn thread điều phối trong lúc chờ mạng | sendAsync() |
| Nhiều request độc lập có thể chạy đồng thời | sendAsync() + allOf/collector phù hợp |
| Request sau phụ thuộc response request trước | sendAsync() + thenCompose() |
| Hai nguồn độc lập cần kết hợp | sendAsync() + thenCombine() |
| Body lớn cần streaming hoặc ghi file | Chọn BodyHandler phù hợp; sendAsync có thể hữu ích để điều phối |
| Công việc blocking hoặc cần executor riêng | Quản lý executor rõ ràng; cân nhắc API khác nếu phù hợp |
| Cần flow đơn giản, dễ debug và không có lợi ích concurrency | send() |

## 18. Ví dụ hoàn chỉnh: hai request song song và ghép kết quả

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class CombineRequests {

    static CompletableFuture<String> getBody(
            HttpClient client,
            URI uri) {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "text/plain")
                .GET()
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() < 200
                            || response.statusCode() >= 300) {
                        throw new CompletionException(
                                new IllegalStateException(
                                        "HTTP " + response.statusCode()));
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();

        CompletableFuture<String> first =
                getBody(client, URI.create("https://example.com"));
        CompletableFuture<String> second =
                getBody(client, URI.create("https://example.org"));

        CompletableFuture<String> combined =
                first.thenCombine(second,
                        (a, b) -> "First length=" + a.length()
                                + ", second length=" + b.length());

        combined.whenComplete((value, error) -> {
            if (error != null) {
                System.err.println("At least one request failed: " + error);
            } else {
                System.out.println(value);
            }
        });
    }
}
~~~

Ví dụ cần import java.util.concurrent.CompletionException. Hai request được khởi tạo độc lập trước khi kết hợp, nên chúng có thể tiến triển đồng thời. Khi một request lỗi transport hoặc status bị chuyển thành exception, combined cũng hoàn tất exceptional.

Trong ứng dụng thật, cần cân nhắc giới hạn thời gian tổng thể, giới hạn concurrency và việc body có kích thước lớn hay không. Không nhất thiết tải toàn bộ body thành String nếu chỉ cần metadata hoặc file.

## 19. Quy trình thiết kế một HTTP call bất đồng bộ

Khi xây dựng một client API:

1. **Tái sử dụng HttpClient** với cấu hình kết nối, redirect, proxy và executor phù hợp.
2. **Tạo HttpRequest** với URI, method, headers, body publisher và timeout rõ ràng.
3. **Chọn BodyHandler** theo kích thước và cách sử dụng body.
4. **Gọi send() hoặc sendAsync()** theo nhu cầu chặn luồng và phối hợp tác vụ.
5. **Kiểm tra status code** vì HTTP 4xx/5xx không tự động là lỗi exceptional.
6. **Nối CompletableFuture** bằng thenApply, thenCompose, thenCombine, allOf khi có dependency phù hợp.
7. **Xử lý lỗi và cancellation** ở một nơi có trách nhiệm rõ; phân biệt transport error, timeout, status error và lỗi nghiệp vụ.
8. **Giới hạn concurrency** nếu có nhiều request và quản lý executor theo lifecycle ứng dụng.
9. **Kiểm thử bằng mock/local server**, đặc biệt với timeout, status lỗi, body lớn và cancellation.

send() và sendAsync() cùng gửi HTTP request qua HttpClient nhưng phục vụ hai cách tổ chức luồng khác nhau. send() phù hợp với logic tuần tự cần kết quả ngay; sendAsync() kết hợp với CompletableFuture phù hợp khi cần tiếp tục công việc trong lúc chờ mạng, ghép nhiều request hoặc xây dựng pipeline bất đồng bộ. Thiết kế tốt phải quản lý cả response body, status, timeout, lỗi, cancellation và concurrency thay vì chỉ thay send() bằng sendAsync().
