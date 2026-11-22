# `send()` với virtual thread và `sendAsync()` theo nhu cầu xử lý

## Mục tiêu

Java 21 cung cấp `java.net.http.HttpClient` với hai cách gửi HTTP request chính: `send()` thực hiện lời gọi đồng bộ và `sendAsync()` trả về `CompletableFuture` để xử lý bất đồng bộ. Khi kết hợp với virtual threads, ứng dụng có thể giữ cách viết blocking tuần tự dễ đọc mà vẫn phục vụ nhiều request đồng thời. Với `sendAsync()`, ứng dụng có thể ghép nối nhiều lời gọi HTTP mà không chặn thread gọi trong lúc chờ phản hồi.

Không có cách nào luôn tốt hơn cách còn lại. Lựa chọn phụ thuộc vào mô hình xử lý của ứng dụng, cách kết hợp kết quả, yêu cầu streaming, timeout và nơi đang chạy đoạn code. Bài học này trình bày hai cách tiếp cận trên Java 21, cách quản lý lỗi và cancellation, cùng các tình huống nên chọn từng API.

## 1. Phân biệt `send()` và `sendAsync()`

Hai phương thức nhận một `HttpRequest` và một `BodyHandler` để xác định cách xử lý response body:

| API | Giá trị trả về | Hành vi của thread gọi |
|---|---|---|
| `send(request, bodyHandler)` | `HttpResponse<T>` | Chờ response; lời gọi là blocking |
| `sendAsync(request, bodyHandler)` | `CompletableFuture<HttpResponse<T>>` | Trả về future để tiếp tục xử lý khi response hoàn tất |

`send()` phù hợp khi code có thể chờ kết quả tại vị trí gọi. Nếu chạy `send()` trên virtual thread, thread gọi có thể chờ I/O theo mô hình blocking mà không cần giữ một platform thread riêng trong toàn bộ thời gian chờ trên các đường blocking được JVM hỗ trợ.

`sendAsync()` phù hợp khi muốn kết hợp nhiều request, tạo pipeline bằng `CompletableFuture`, hoặc trả quyền điều khiển về event loop/caller ngay sau khi gửi request. Bản thân `sendAsync()` không yêu cầu ứng dụng phải dùng virtual thread.

## 2. Tạo và tái sử dụng `HttpClient`

`HttpClient` là đối tượng có thể dùng chung cho nhiều request. Nên tạo client một lần ở phạm vi ứng dụng hoặc service, cấu hình các tùy chọn chung rồi tái sử dụng, thay vì tạo client mới cho từng request.

```java
import java.net.http.HttpClient;
import java.time.Duration;

class SharedHttpClient {
    static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .followRedirects(HttpClient.Redirect.NORMAL)
            .build();
}
```

Trong ví dụ, `connectTimeout` giới hạn thời gian thiết lập kết nối. Nó không thay thế timeout cho toàn bộ request. Timeout cho từng request được đặt trên `HttpRequest` bằng `timeout(Duration)`.

Có thể cấu hình thêm proxy, authenticator, cookie handler, SSL context, phiên bản HTTP mong muốn hoặc executor cho các tác vụ bất đồng bộ. Hãy cấu hình theo yêu cầu của service và tái sử dụng client để tận dụng connection management của nó.

## 3. Gửi request đồng bộ bằng `send()`

`send()` trả về `HttpResponse<T>` khi response đã sẵn sàng. Với `BodyHandlers.ofString()`, response body được đọc thành `String`:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

class SynchronousHttpCall {
    static String fetch() throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/profile/101"))
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();

        HttpResponse<String> response = SharedHttpClient.CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("HTTP status: " + response.statusCode());
        }

        return response.body();
    }
}
```

`send()` có thể ném `IOException` khi có lỗi I/O và `InterruptedException` khi thread gọi bị interrupt trong lúc chờ. Trong ứng dụng thực tế, cần quyết định cách xử lý status code, response header, body và lỗi theo hợp đồng của API.

Lời gọi là blocking đối với thread gọi. Nếu gọi từ một platform thread trong request handler, platform thread đó sẽ chờ. Nếu gọi từ virtual thread, virtual thread chờ kết quả; điều này cho phép code giữ cấu trúc tuần tự mà vẫn tận dụng khả năng xử lý nhiều tác vụ I/O đồng thời của virtual threads.

## 4. Chạy `send()` trên virtual thread

Khi một request cần gọi nhiều endpoint độc lập và codebase đang dùng phong cách blocking, có thể tạo một virtual thread cho mỗi lời gọi. `Executors.newVirtualThreadPerTaskExecutor()` là cách thuận tiện để quản lý các task này:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class VirtualThreadHttpCalls {
    static List<String> fetchAll(List<URI> endpoints)
            throws InterruptedException, ExecutionException {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> tasks = endpoints.stream()
                    .map(uri -> executor.submit(() -> fetch(uri)))
                    .toList();

            try {
                List<String> results = new ArrayList<>();
                for (Future<String> task : tasks) {
                    results.add(task.get());
                }
                return List.copyOf(results);
            } catch (InterruptedException | ExecutionException e) {
                tasks.forEach(task -> task.cancel(true));
                throw e;
            }
        }
    }

    private static String fetch(URI uri) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(4))
                .GET()
                .build();

        HttpResponse<String> response = SharedHttpClient.CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException("Unexpected status " + response.statusCode());
        }
        return response.body();
    }
}
```

Mỗi lời gọi `send()` chạy trong virtual thread của task tương ứng. Caller có thể viết code như một chuỗi thao tác đồng bộ và xử lý exception bằng `try/catch`. Khi một task chờ network, virtual thread có thể nhường carrier trên các thao tác blocking được hỗ trợ.

Ví dụ này minh họa cách tổ chức. `Future.get()` có thể ném `InterruptedException` hoặc `ExecutionException`; caller cần xử lý hai trường hợp này theo chính sách hủy và lỗi của ứng dụng. Với ứng dụng cần một deadline chung hoặc cần hủy các request còn lại khi một request lỗi, hãy giữ các `Future`, tính thời gian còn lại cho từng lần chờ và gọi `cancel(true)` cho task không còn cần thiết. Timeout của từng `HttpRequest` vẫn nên được cấu hình riêng.

## 5. Gửi request bất đồng bộ bằng `sendAsync()`

`sendAsync()` trả về `CompletableFuture<HttpResponse<T>>` gần như ngay sau khi đăng ký request. Ứng dụng có thể tiếp tục làm việc khác và gắn callback xử lý response khi future hoàn tất.

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

class AsynchronousHttpCall {
    static CompletableFuture<String> fetch() {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/profile/101"))
                .timeout(Duration.ofSeconds(5))
                .header("Accept", "application/json")
                .GET()
                .build();

        return SharedHttpClient.CLIENT
                .sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() < 200 || response.statusCode() >= 300) {
                        throw new IllegalStateException(
                                "HTTP status: " + response.statusCode());
                    }
                    return response.body();
                });
    }
}
```

Method `fetch()` trả về future của body. Caller có thể ghép future này vào một pipeline khác, hoặc chờ ở ranh giới phù hợp bằng `join()`/`get()` nếu luồng nghiệp vụ yêu cầu kết quả ngay tại đó.

Nếu gọi `sendAsync()` rồi lập tức gọi `join()` mà không làm công việc nào khác, caller vẫn phải chờ. Lợi ích bất đồng bộ rõ nhất xuất hiện khi ứng dụng tiếp tục xử lý công việc khác hoặc kết hợp nhiều future trước khi chờ kết quả cuối cùng.

## 6. Kết hợp nhiều HTTP request với `CompletableFuture`

Khi nhiều endpoint độc lập, có thể gửi tất cả bằng `sendAsync()` rồi kết hợp kết quả bằng `CompletableFuture.allOf()`:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;

class AsyncFanOutExample {
    static CompletableFuture<List<String>> fetchAll(List<URI> endpoints) {
        List<CompletableFuture<HttpResponse<String>>> responses = endpoints.stream()
                .map(AsyncFanOutExample::send)
                .toList();

        CompletableFuture<Void> allCompleted = CompletableFuture.allOf(
                responses.toArray(CompletableFuture[]::new));

        return allCompleted.thenApply(ignored -> responses.stream()
                .map(CompletableFuture::join)
                .map(HttpResponse::body)
                .toList());
    }

    private static CompletableFuture<HttpResponse<String>> send(URI uri) {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(4))
                .GET()
                .build();

        return SharedHttpClient.CLIENT.sendAsync(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
```

`allOf()` hoàn tất khi tất cả future đầu vào hoàn tất. Nếu một future hoàn tất exceptionally, future tổng hợp cũng hoàn tất exceptionally và bước `thenApply()` không chạy. Khi tất cả thành công, `join()` trên từng future đã hoàn tất sẽ lấy response mà không phải chờ thêm.

`allOf()` chỉ phối hợp trạng thái hoàn tất; nó không tự hủy các request còn lại khi một request thất bại. Nếu chính sách nghiệp vụ yêu cầu dừng phần việc còn lại, cần giữ danh sách future và chủ động yêu cầu cancellation trong nhánh xử lý lỗi.

## 7. Xử lý callback và executor cho tác vụ phụ thuộc

Các method không có hậu tố `Async`, chẳng hạn `thenApply()` hoặc `thenAccept()`, có thể chạy action trên thread hoàn tất future hoặc thread gọi khi future đã hoàn tất. Vì vậy, callback không nên thực hiện công việc blocking dài hoặc tính toán nặng.

Nếu muốn chỉ định executor cho bước xử lý tiếp theo, dùng các method có hậu tố `Async` và truyền executor:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;

class AsyncContinuationExample {
    static void process(URI uri) {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            CompletableFuture<String> result = SharedHttpClient.CLIENT
                    .sendAsync(request, HttpResponse.BodyHandlers.ofString())
                    .thenApplyAsync(response -> parseBody(response.body()), executor);

            System.out.println(result.join());
        }
    }

    private static String parseBody(String body) {
        // Thay bằng bước chuyển đổi hoặc xử lý body thực tế.
        return body.trim();
    }
}
```

Executor được truyền vào `thenApplyAsync()` quyết định nơi chạy bước xử lý phụ thuộc. Ví dụ dùng virtual thread executor để minh họa một bước xử lý blocking hoặc cần thread-per-task. Nếu callback chủ yếu làm tính toán CPU-bound, hãy cân nhắc executor có số worker giới hạn phù hợp với năng lực CPU thay vì tạo vô hạn tác vụ tính toán.

Nếu cấu hình executor trên `HttpClient.Builder.executor(executor)`, executor đó được dùng cho các tác vụ bất đồng bộ và tác vụ phụ thuộc của client. Chỉ đóng executor sau khi các exchange và callback cần nó đã hoàn tất. Không tạo executor cho từng callback nhỏ nếu không cần thiết.

## 8. Timeout kết nối và timeout request

Có hai phạm vi timeout thường cần cấu hình:

- `HttpClient.Builder.connectTimeout(Duration)`: giới hạn thời gian thiết lập kết nối.
- `HttpRequest.Builder.timeout(Duration)`: giới hạn thời gian cho một request cụ thể.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

class HttpTimeoutExample {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    static HttpResponse<String> fetch() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/api/data"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        return CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
```

Nếu request vượt quá timeout đã cấu hình, `send()` có thể ném `HttpTimeoutException`; với `sendAsync()`, future hoàn tất exceptionally với lỗi tương ứng. Timeout của request nên được tính trong ngân sách deadline tổng thể của request nghiệp vụ.

Không nên chỉ đặt timeout ở `Future.get()` hoặc `CompletableFuture.orTimeout()` rồi cho rằng HTTP exchange chắc chắn đã dừng. Hãy cấu hình timeout ngay trên `HttpRequest` và xử lý cancellation theo nhu cầu của ứng dụng.

## 9. Cancellation và giới hạn của nó

Với `send()` chạy trong virtual thread, caller có thể bị interrupt khi đang chờ. `send()` khai báo `InterruptedException`; nếu bắt exception mà không truyền tiếp, hãy khôi phục interrupt status bằng `Thread.currentThread().interrupt()`.

Với `sendAsync()`, có thể gọi `cancel(true)` trên future được trả về. `HttpClient` cố gắng hủy exchange tương ứng, nhưng cancellation là best effort. Nếu request đã được gửi đến server, server có thể vẫn tiếp tục xử lý nó dù client đã ngừng chờ response.

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

class CancelAsyncHttpCall {
    static void cancelWhenNoLongerNeeded() {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api/long-running-operation"))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> responseFuture =
                SharedHttpClient.CLIENT.sendAsync(
                        request, HttpResponse.BodyHandlers.ofString());

        // Khi request nghiệp vụ không còn cần response:
        boolean cancellationRequested = responseFuture.cancel(true);
        System.out.println("Cancellation requested: " + cancellationRequested);
    }
}
```

Giá trị boolean cho biết future đã chuyển sang trạng thái cancelled hay chưa; không nên diễn giải nó như xác nhận server đã dừng xử lý. Với request có side effect như tạo đơn hàng hoặc thanh toán, cần thiết kế idempotency key, trạng thái nghiệp vụ và cơ chế đối soát phù hợp. Cancellation ở client không thể thay thế bảo đảm giao dịch ở server.

## 10. Xử lý lỗi trong `CompletableFuture`

Lỗi khi tạo request, lỗi mạng, timeout hoặc lỗi xử lý response có thể khiến future hoàn tất exceptionally. Dùng `exceptionally()`, `handle()` hoặc `whenComplete()` tùy mục tiêu:

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

class AsyncErrorHandlingExample {
    static CompletableFuture<String> fetch() {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api/status"))
                .GET()
                .build();

        return SharedHttpClient.CLIENT
                .sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(response -> {
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException(
                                "Unexpected status " + response.statusCode());
                    }
                    return response.body();
                })
                .exceptionally(error -> {
                    // Chuyển lỗi thành kết quả dự phòng theo hợp đồng ứng dụng.
                    return "Không lấy được dữ liệu: " + error.getMessage();
                });
    }
}
```

`exceptionally()` biến lỗi thành một kết quả thay thế. Chỉ nên dùng fallback nếu nghiệp vụ cho phép; nếu không, hãy để future tiếp tục exceptional hoặc chuyển đổi sang exception nghiệp vụ có ý nghĩa. Khi cần log lỗi nhưng vẫn giữ nguyên kết quả/lỗi, `whenComplete()` thường phù hợp hơn.

Lỗi HTTP status như 404 hoặc 500 không tự làm `send()` hay `sendAsync()` thất bại. Đây vẫn là một HTTP response bình thường; ứng dụng phải kiểm tra `statusCode()` và quyết định cách xử lý.

## 11. Chọn `BodyHandler` theo kích thước và cách sử dụng response

`BodyHandlers.ofString()` tiện lợi cho JSON hoặc response nhỏ, nhưng đọc toàn bộ body vào bộ nhớ. Với response lớn hoặc dữ liệu cần xử lý theo luồng, hãy chọn handler phù hợp như `ofInputStream()` hoặc body subscriber chuyên biệt.

```java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

class StreamingResponseExample {
    static void fetchStream() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/large-file"))
                .GET()
                .build();

        HttpResponse<InputStream> response = SharedHttpClient.CLIENT.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            // Đọc theo từng phần và ghi vào đích phù hợp.
            body.transferTo(System.out);
        }
    }
}
```

Khi dùng `ofInputStream()`, ứng dụng chịu trách nhiệm đóng stream để giải phóng tài nguyên. Cần kiểm tra status code trước khi xử lý body theo định dạng mong đợi và không giữ stream lâu hơn cần thiết.

## 12. Khi nào chọn cách nào?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Code xử lý request theo trình tự, chờ nhiều I/O và muốn dễ đọc | `send()` trên virtual thread | Giữ phong cách blocking đơn giản với concurrency cao cho workload I/O |
| Cần ghép nhiều HTTP call độc lập và tổng hợp kết quả | `sendAsync()` | Dùng `allOf`, `thenCombine`, `thenCompose` để phối hợp future |
| Đang ở event loop hoặc thread không được phép blocking | `sendAsync()` | Trả quyền điều khiển về caller thay vì chờ response |
| Pipeline đã dùng `CompletableFuture` | `sendAsync()` | Tích hợp trực tiếp vào chuỗi xử lý bất đồng bộ |
| Cần streaming hoặc body lớn | Chọn `BodyHandler` phù hợp; có thể kết hợp với cả hai API | Quyết định xử lý body quan trọng không kém cách gửi request |
| Cần xử lý CPU-bound sau response | Chuyển bước xử lý sang executor phù hợp | Tránh làm nghẽn thread hoàn tất HTTP exchange |

Không nên chọn `sendAsync()` chỉ vì tên gọi có vẻ hiện đại hơn. Nếu ứng dụng đã dùng virtual threads và code blocking dễ hiểu, `send()` có thể là lựa chọn đơn giản. Ngược lại, nếu cần composition bất đồng bộ hoặc đang chạy trong môi trường yêu cầu không blocking, `sendAsync()` phù hợp hơn.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi `send()` trên event loop hoặc thread không được phép blocking | Chặn xử lý các event khác | Dùng `sendAsync()` hoặc chuyển blocking call sang worker phù hợp |
| Gọi `sendAsync()` rồi `join()` ngay lập tức ở cùng luồng | Mất phần lớn lợi ích composition bất đồng bộ | Tiếp tục pipeline hoặc chỉ chờ ở ranh giới cần kết quả |
| Tạo `HttpClient` mới cho từng request | Không tận dụng tốt việc tái sử dụng client và connection management | Dùng client dùng chung theo service/app |
| Nghĩ HTTP status 4xx/5xx tự tạo exception | Bỏ sót lỗi nghiệp vụ trong response | Kiểm tra `statusCode()` |
| Chỉ đặt timeout ở `Future.get()` | HTTP exchange có thể vẫn tiếp tục | Cấu hình timeout trên `HttpRequest` và xử lý cancellation |
| Nghĩ `cancel(true)` chắc chắn dừng server | Server có thể đã nhận và tiếp tục xử lý request | Dùng idempotency và cơ chế nghiệp vụ phía server |
| Chạy callback blocking dài bằng `thenApply()` | Có thể chiếm thread hoàn tất future | Dùng `thenApplyAsync()` với executor phù hợp |
| Đọc response lớn bằng `ofString()` | Tăng áp lực heap | Chọn streaming `BodyHandler` và đóng stream |

## 14. Checklist trước khi đưa vào production

1. `HttpClient` có được tái sử dụng thay vì tạo mới cho từng request không?
2. Đã chọn `send()` trên virtual thread hay `sendAsync()` dựa trên mô hình xử lý chưa?
3. Có cấu hình connect timeout và request timeout phù hợp không?
4. Có kiểm tra status code, header và body theo hợp đồng API không?
5. Với `sendAsync()`, callback có tránh blocking dài trên thread hoàn tất future không?
6. Nếu cần executor riêng cho callback, executor có được quản lý vòng đời đúng không?
7. Cancellation có được hiểu là best effort và side effect có idempotency phù hợp không?
8. Response body lớn có được xử lý streaming và đóng tài nguyên đúng cách không?
9. Deadline của HTTP call có nằm trong deadline tổng thể của request nghiệp vụ không?
10. Có giới hạn concurrency và backpressure phù hợp với dịch vụ phía sau không?

## Kết luận

`HttpClient.send()` là API blocking, phù hợp với code tuần tự chạy trên virtual thread khi muốn xử lý I/O theo phong cách dễ đọc. `sendAsync()` trả về `CompletableFuture`, phù hợp khi cần composition, fan-out nhiều request hoặc tích hợp với luồng xử lý không blocking. Cả hai đều cần timeout, kiểm tra status code, xử lý lỗi và giới hạn tài nguyên phù hợp. Cancellation chỉ là yêu cầu best effort đối với HTTP exchange; ứng dụng vẫn phải bảo vệ side effect và quản lý vòng đời response body. Hãy chọn API theo mô hình xử lý thực tế thay vì mặc định rằng bất đồng bộ luôn tốt hơn blocking trên virtual thread.
