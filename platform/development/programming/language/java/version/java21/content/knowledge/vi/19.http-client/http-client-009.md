# Kiểm thử request chưa hoàn tất, lỗi mạng và rò rỉ tài nguyên

## 1. Vì sao cần kiểm thử các tình huống không thành công?

Khi tích hợp `java.net.http.HttpClient` trong Java 21, một request thành công với server khỏe mạnh chỉ kiểm tra được một phần hành vi. Ứng dụng còn phải xử lý các tình huống như server phản hồi chậm, request body chưa gửi xong, response body bị ngắt giữa chừng, kết nối bị từ chối, timeout, task bị hủy hoặc stream không được đóng.

Những lỗi này có thể khiến request treo lâu, giữ socket hoặc tài nguyên mạng, làm client không thể shutdown đúng lúc, hoặc khiến số tác vụ đang chờ tăng dần. Vì vậy, test HTTP nên bao gồm cả trường hợp thành công, lỗi giao thức, lỗi transport, timeout, cancellation và cleanup.

Trong Java 21, `HttpClient` hỗ trợ cả `send()` đồng bộ và `sendAsync()` bất đồng bộ. Các test cần phân biệt cách lỗi được báo ở hai API này và không giả định mọi lỗi mạng đều tạo ra cùng một exception cụ thể.

## 2. Phân biệt các loại request chưa hoàn tất

Một request có thể chưa hoàn tất ở nhiều giai đoạn khác nhau:

1. **Request chưa kết nối được**: DNS, TCP connect, proxy hoặc TLS handshake thất bại hoặc kéo dài.
2. **Request body chưa gửi xong**: `BodyPublisher` chưa phát hết dữ liệu hoặc nguồn dữ liệu đầu vào chưa kết thúc.
3. **Server chưa gửi response**: request đã được gửi nhưng server đang xử lý hoặc không trả header.
4. **Response body chưa đọc xong**: response header đã đến nhưng body stream vẫn còn dữ liệu hoặc chưa kết thúc.
5. **Async operation chưa hoàn tất**: `CompletableFuture` vẫn pending vì một trong các giai đoạn trên chưa kết thúc.

Không nên gom tất cả thành “request bị treo”. Hãy xác định giai đoạn đang chờ để chọn timeout, công cụ quan sát và cách cleanup tương ứng.

## 3. Phân biệt timeout ở cấp client và request

`HttpClient.Builder.connectTimeout(Duration)` giới hạn thời gian thiết lập kết nối khi cần tạo connection mới. `HttpRequest.Builder.timeout(Duration)` đặt timeout cho request cụ thể.

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

Hai timeout bảo vệ các giai đoạn khác nhau. Connect timeout không phải deadline tổng cho toàn bộ xử lý nghiệp vụ; request timeout cũng không thay thế timeout ở database, body processing hoặc các bước tiếp theo sau khi response đã được trả về cho ứng dụng.

Nếu không cấu hình request timeout, ứng dụng không có deadline request do `HttpRequest` đặt ra. Hãy chọn thời hạn theo SLA và thời gian xử lý thực tế của dịch vụ, thay vì dựa vào một timeout mặc định giả định.

Khi timeout xảy ra, `HttpTimeoutException` là một dạng `IOException`. Với `send()`, exception được ném trực tiếp. Với `sendAsync()`, future hoàn tất exceptional; khi gọi `get()` hoặc `join()`, lỗi có thể được bọc trong `ExecutionException` hoặc `CompletionException`.

```java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());
} catch (HttpTimeoutException e) {
    // Request không nhận được response trong thời hạn đã đặt.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Hoặc truyền InterruptedException lên caller.
} catch (IOException e) {
    // Lỗi kết nối, TLS, đọc/ghi hoặc lỗi I/O khác.
}
```

Nếu bắt `InterruptedException` mà không truyền tiếp, hãy khôi phục interrupt status bằng `Thread.currentThread().interrupt()` trước khi trả về hoặc tiếp tục xử lý.

## 4. Dùng local HTTP server để kiểm thử có kiểm soát

Không nên phụ thuộc vào một website công cộng để kiểm tra timeout hoặc lỗi mạng. Mạng Internet, DNS, proxy và tải của server thay đổi theo thời điểm, khiến test không ổn định. Có thể dựng HTTP server cục bộ bằng `com.sun.net.httpserver.HttpServer` trong module `jdk.httpserver`.

Một server local cho phép test chủ động điều khiển:

- Khi nào nhận request.
- Khi nào gửi response header/body.
- Có trả response hay đóng kết nối đột ngột.
- Body có đầy đủ hay bị cắt giữa chừng.
- Server xử lý đồng thời bao nhiêu request.

Ví dụ tạo server có endpoint chờ một latch trước khi gửi response:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

static HttpServer startDelayedServer(
        ExecutorService serverExecutor,
        CountDownLatch requestArrived,
        CountDownLatch allowResponse) throws IOException {

    HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
    server.setExecutor(serverExecutor);
    server.createContext("/delayed", exchange -> {
        requestArrived.countDown();
        try {
            if (!allowResponse.await(5, TimeUnit.SECONDS)) {
                exchange.sendResponseHeaders(504, -1);
                return;
            }

            byte[] body = "ready".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            exchange.close();
        }
    });
    server.start();
    return server;
}
```

Server bind vào port `0` để hệ điều hành cấp một cổng khả dụng. Test lấy cổng thực tế qua `server.getAddress().getPort()`. Dùng `CountDownLatch` giúp điều khiển thời điểm response mà không cần dựa vào `Thread.sleep()`.

Khi dùng `HttpServer`, module cần quyền truy cập module `jdk.httpserver`; trong project modular, khai báo `requires jdk.httpserver;` ở module test hoặc module phù hợp.

## 5. Kiểm thử request đang pending rồi hoàn tất bình thường

Test đầu tiên xác minh rằng `sendAsync()` chưa hoàn tất khi server cố ý giữ response, rồi hoàn tất sau khi test cho phép server gửi dữ liệu.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

static void testPendingRequestCompletes() throws Exception {
    try (ExecutorService serverExecutor = Executors.newVirtualThreadPerTaskExecutor();
         HttpClient client = HttpClient.newHttpClient()) {

        CountDownLatch arrived = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = startDelayedServer(serverExecutor, arrived, release);

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/delayed");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> future = client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString());

            if (!arrived.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Server did not receive the request");
            }
            if (future.isDone()) {
                throw new AssertionError("Response completed before server was released");
            }

            release.countDown();
            HttpResponse<String> response = future.get(2, TimeUnit.SECONDS);

            if (response.statusCode() != 200 || !response.body().equals("ready")) {
                throw new AssertionError("Unexpected response: " + response);
            }
        } finally {
            release.countDown();
            server.stop(0);
        }
    }
}
```

Test kiểm tra cả ba điều: server đã nhận request, future thực sự pending khi server chưa trả lời và future hoàn tất với response đúng sau khi latch được mở. Đây là cách kiểm tra hành vi chưa hoàn tất mà không cần đoán thời gian bằng sleep.

## 6. Kiểm thử request timeout

Có thể dùng endpoint delayed ở trên để xác minh `HttpRequest.timeout`:

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(300))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

try {
    future.get(2, TimeUnit.SECONDS);
    throw new AssertionError("Expected request timeout");
} catch (ExecutionException e) {
    if (!hasCause(e, HttpTimeoutException.class)) {
        throw new AssertionError("Unexpected failure", e);
    }
}
```

`hasCause` là helper duyệt chuỗi cause để tránh phụ thuộc vào việc lỗi được bọc bao nhiêu lớp:

```java
static boolean hasCause(Throwable error, Class<? extends Throwable> type) {
    for (Throwable current = error; current != null; current = current.getCause()) {
        if (type.isInstance(current)) {
            return true;
        }
    }
    return false;
}
```

Trong test hoàn chỉnh, cần chờ latch `requestArrived` để chắc chắn server đã nhận request trước khi đánh giá timeout. Luôn mở latch trong `finally` và gọi `server.stop(0)` để handler không bị giữ lại nếu assertion thất bại.

Timeout của request không thay thế việc cleanup phía server. Sau khi client timeout, server có thể vẫn đang chạy handler hoặc đang ghi response; server test phải có thời hạn chờ riêng và đường cleanup rõ ràng.

## 7. Kiểm thử request body chưa gửi xong

Request có body streaming có thể bị kẹt nếu nguồn dữ liệu không phát EOF hoặc `BodyPublisher` không hoàn tất. Có thể kiểm thử bằng `BodyPublishers.ofInputStream` với một pipe mà đầu ghi vẫn mở:

```java
static void testIncompleteRequestBody(HttpClient client, URI uri) throws Exception {
    PipedInputStream bodySource = new PipedInputStream();
    PipedOutputStream bodyWriter = new PipedOutputStream(bodySource);

    bodyWriter.write("partial-body".getBytes(StandardCharsets.UTF_8));
    bodyWriter.flush();
    // Giữ bodyWriter mở: InputStream chưa phát EOF.

    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(1))
            .header("Content-Type", "application/octet-stream")
            .POST(HttpRequest.BodyPublishers.ofInputStream(() -> bodySource))
            .build();

    try {
        client.send(request, HttpResponse.BodyHandlers.ofString());
        throw new AssertionError("Expected request timeout");
    } catch (HttpTimeoutException expected) {
        // Request body chưa hoàn tất trong thời hạn cho phép.
    } finally {
        bodyWriter.close();
        bodySource.close();
    }
}
```

Phía server cần có handler đọc request body đến EOF để test phản ánh đúng tình huống upload chưa kết thúc. Trong ví dụ này, pipe được giữ mở để publisher chưa thể đọc hết body. Timeout và cleanup phải có giới hạn; không để test giữ pipe hoặc handler vô thời hạn.

`BodyPublishers.ofInputStream` nhận một `Supplier<InputStream>`. Nếu publisher cần subscribe lại, supplier phải cung cấp một stream mới có thể đọc lại cùng nội dung; không trả lại một stream đã tiêu thụ hoặc đã đóng. Với body có thể retry, hãy xác định rõ tính lặp lại của nguồn dữ liệu.

## 8. Kiểm thử lỗi mạng và lỗi giao thức

Các lỗi mạng thường được biểu diễn bằng `IOException` hoặc subclass. Một số trường hợp có thể gặp:

| Tình huống | Dạng lỗi có thể gặp |
|---|---|
| Không có server lắng nghe tại địa chỉ/cổng | `ConnectException` hoặc `IOException` phù hợp với hệ điều hành |
| DNS không phân giải được | `UnknownHostException` hoặc lỗi I/O liên quan |
| Kết nối bị đóng trước khi response hợp lệ đến | `IOException` |
| TLS handshake hoặc xác thực chứng chỉ thất bại | `SSLHandshakeException` hoặc lỗi SSL/I/O khác |
| Request hết thời hạn | `HttpTimeoutException` |
| Thread gọi `send()` bị interrupt | `InterruptedException` |
| Future bất đồng bộ bị hủy | `CancellationException` khi quan sát future |

Không nên assert một subclass quá cụ thể cho mọi môi trường nếu test không kiểm soát được lớp lỗi. Ví dụ, lỗi kết nối có thể được bọc khác nhau tùy proxy, TLS, DNS hoặc nền tảng. Hãy kiểm tra cause chain và loại lỗi ở mức hợp đồng mà ứng dụng cần xử lý.

### 8.1. Phân biệt lỗi mạng với HTTP status lỗi

HTTP status `400`, `404`, `429` hoặc `500` không tự động làm `HttpClient.send()` ném exception. Đây vẫn là một HTTP response hợp lệ ở tầng transport; ứng dụng phải kiểm tra status code và áp dụng chính sách nghiệp vụ.

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

if (response.statusCode() >= 400) {
    // Ghi nhận lỗi HTTP và xử lý theo status/header/body.
}
```

Không viết test mong `send()` ném `IOException` chỉ vì server trả `503`. Hãy assert `response.statusCode() == 503` và kiểm tra nội dung body nếu đó là hợp đồng API.

### 8.2. Mô phỏng kết nối bị đóng đột ngột

Một test có thể mở socket loopback, chấp nhận kết nối rồi đóng ngay mà không gửi HTTP response. Client phải xử lý như lỗi I/O:

```java
static void testAbruptDisconnect() throws Exception {
    try (ExecutorService peer = Executors.newSingleThreadExecutor();
         ServerSocket listener = new ServerSocket(
                 0, 1, InetAddress.getByName("127.0.0.1"));
         HttpClient client = HttpClient.newHttpClient()) {

        peer.submit(() -> {
            try (Socket ignored = listener.accept()) {
                // Đóng socket mà không gửi HTTP response.
            } catch (IOException ignored) {
                // Listener có thể bị đóng trong cleanup.
            }
        });

        URI uri = URI.create("http://127.0.0.1:"
                + listener.getLocalPort() + "/cut-connection");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();

        try {
            client.send(request, HttpResponse.BodyHandlers.ofString());
            throw new AssertionError("Expected an I/O failure");
        } catch (IOException expected) {
            // Không có response HTTP hợp lệ.
        }
    }
}
```

Đây là test transport ở loopback, không phụ thuộc Internet. Nếu cần kiểm tra TLS handshake, hãy dùng test certificate và local HTTPS server riêng; không dùng endpoint công cộng hoặc certificate hết hạn làm test ổn định.

### 8.3. Response body bị cắt giữa chừng

Có thể mô phỏng server khai báo một `Content-Length` lớn hơn số byte thực sự gửi. Khi client dùng body handler cần đọc toàn bộ body, response không thể hoàn tất bình thường:

```java
server.createContext("/truncated", exchange -> {
    byte[] partial = "short".getBytes(StandardCharsets.UTF_8);
    exchange.sendResponseHeaders(200, 100); // Khai báo 100 byte
    try (OutputStream output = exchange.getResponseBody()) {
        output.write(partial);               // Chỉ gửi 5 byte rồi đóng
    }
});

try {
    client.send(requestToTruncatedPath,
            HttpResponse.BodyHandlers.ofByteArray());
    throw new AssertionError("Expected an incomplete-body I/O failure");
} catch (IOException expected) {
    // Response body kết thúc trước Content-Length đã khai báo.
}
```

Đây là lỗi response body, khác với HTTP status lỗi. Test nên xác minh client không trả về một body được xem là hoàn chỉnh khi số byte thực nhận không đáp ứng framing của response.

## 9. Kiểm thử `sendAsync`, lỗi bọc và cancellation

`sendAsync()` trả về `CompletableFuture<HttpResponse<T>>`. Lỗi phát sinh khi gửi request hoặc nhận response sẽ làm future hoàn tất exceptional. Khi gọi `get()`, caller nhận `ExecutionException`; khi gọi `join()`, caller nhận `CompletionException`.

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

future.whenComplete((response, error) -> {
    if (error != null) {
        Throwable cause = error;
        while (cause.getCause() != null) {
            cause = cause.getCause();
        }
        logFailure(cause);
    } else {
        logStatus(response.statusCode());
    }
});
```

Khi test cancellation:

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        slowRequest, HttpResponse.BodyHandlers.ofString());

if (!requestArrived.await(2, TimeUnit.SECONDS)) {
    throw new AssertionError("Server did not receive request");
}

boolean cancelled = future.cancel(true);
if (!cancelled || !future.isCancelled()) {
    throw new AssertionError("Future was not cancelled");
}
```

`CompletableFuture.cancel(true)` hoàn tất future bằng trạng thái cancelled. Với `HttpClient`, cancellation cố gắng hủy HTTP exchange tương ứng, nhưng ứng dụng không nên coi đây là bảo đảm rằng mọi hoạt động I/O hoặc handler phía server đã dừng ngay lập tức. Server có thể vẫn đang xử lý; test phải mở latch và dọn server trong `finally`.

Tương tự, `orTimeout(...)` làm future hoàn tất exceptional khi hết thời hạn nhưng không nên dùng nó như bằng chứng rằng tác vụ mạng bên dưới chắc chắn đã được giải phóng. Dùng request timeout để đặt giới hạn cho request và cleanup/cancellation rõ ràng cho phần việc còn lại.

## 10. Response body streaming và nguy cơ rò rỉ tài nguyên

`HttpResponse.BodyHandlers` quyết định cách body được tiếp nhận. Một số handler đọc toàn bộ body trước khi hoàn tất response; một số trả stream để ứng dụng tự quản lý.

| Body handler | Kiểu body | Trách nhiệm của caller |
|---|---|---|
| `ofString()` | `String` | Body được gom vào bộ nhớ; phù hợp với body có kích thước hợp lý |
| `ofByteArray()` | `byte[]` | Body được gom vào bộ nhớ; cân nhắc giới hạn kích thước |
| `discarding()` | `Void` | Dùng khi không cần nội dung body |
| `ofInputStream()` | `InputStream` | Đọc và đóng stream, kể cả khi dừng đọc sớm |
| `ofLines()` | `Stream<String>` | Đóng stream bằng try-with-resources |
| `ofFile(path)` | `Path` | Kiểm tra file đích và dọn file một phần nếu test thất bại |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Subscribe, request dữ liệu theo backpressure và cancel khi không cần tiếp tục |

Với `ofInputStream()`, response có thể được trả về ngay khi stream sẵn sàng, trong khi dữ liệu body vẫn đang được nhận và đọc. `ofPublisher()` cũng cung cấp publisher để caller tự subscribe và tiêu thụ dữ liệu. Vì vậy, việc `send()` trả về hoặc future của `sendAsync()` hoàn tất không nhất thiết có nghĩa body streaming đã được đọc hết. Request timeout không nên được dùng làm read timeout cho mọi lần đọc stream sau khi response đã được giao cho ứng dụng; cần có deadline đọc, chính sách cancel và đóng stream riêng.

Ví dụ an toàn với `InputStream`:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    body.transferTo(destination);
}
```

Nếu chỉ cần đọc một phần body, vẫn phải đóng stream sau khi dừng. Không để stream sống lâu hơn phạm vi cần thiết hoặc lưu nó trong field mà không có chủ sở hữu rõ ràng.

Với `ofLines()`:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.limit(100).forEach(this::processLine);
}
```

Đóng stream quan trọng ngay cả khi `limit`, exception hoặc điều kiện nghiệp vụ khiến ứng dụng không đọc hết body.

## 11. BodySubscriber và backpressure

Khi dùng `BodyHandlers.ofPublisher()` hoặc custom `BodySubscriber`, việc tiêu thụ body tuân theo Reactive Streams/`Flow` backpressure. Subscriber phải yêu cầu dữ liệu qua `Subscription.request(n)`; nếu không request thêm dữ liệu, publisher có thể dừng phát và response body không hoàn tất.

Một subscriber tùy chỉnh phải xử lý đúng các callback:

- `onSubscribe`: lưu subscription và yêu cầu lượng dữ liệu phù hợp.
- `onNext`: xử lý buffer, không giữ tham chiếu lâu hơn cần thiết.
- `onError`: ghi nhận lỗi và hoàn tất xử lý cleanup.
- `onComplete`: đánh dấu body đã được tiêu thụ xong.

Nếu ứng dụng không còn cần dữ liệu, gọi `Subscription.cancel()` và giải phóng tài nguyên mà subscriber đang giữ. Không giữ `ByteBuffer` hoặc buffer lớn trong hàng đợi vô hạn; điều đó có thể gây tăng bộ nhớ dù số request đồng thời không cao.

Với custom subscriber, hãy test cả trường hợp body bình thường, `onError`, subscriber cancel sớm, server đóng kết nối và subscriber không request thêm dữ liệu. Mục tiêu là bảo đảm `getBody()` hoàn tất đúng hợp đồng và không giữ request ở trạng thái pending vô thời hạn.

## 12. Đóng `HttpClient` và quản lý executor

Trong Java 21, `HttpClient` triển khai `AutoCloseable`. Client dùng lâu dài nên được đóng khi thành phần sở hữu kết thúc vòng đời, không đóng sau từng request.

Các API lifecycle gồm:

- `shutdown()`: ngừng nhận request mới và cho phép hoạt động đã gửi hoàn tất.
- `awaitTermination(Duration)`: chờ có giới hạn để xác định client đã kết thúc hay chưa.
- `isTerminated()`: kiểm tra trạng thái kết thúc.
- `shutdownNow()`: cố gắng hủy hoạt động đang tồn tại và bắt đầu shutdown ngay.
- `close()`: thực hiện orderly shutdown và chờ client kết thúc.

Ví dụ dùng client trong test ngắn hạn:

```java
try (HttpClient client = HttpClient.newHttpClient()) {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    assert response.statusCode() == 200;
}
```

Với client dùng chung trong application, đóng nó trong lifecycle hook sau khi ngừng nhận công việc mới và xử lý các request đang chạy. Nếu request hoặc body stream chưa hoàn tất, orderly shutdown có thể phải chờ. Vì vậy, cần timeout cho request và cleanup body đúng cách.

Nếu truyền executor do ứng dụng tạo vào `HttpClient.Builder.executor(...)`, chủ sở hữu của executor phải quản lý vòng đời executor đó. Đừng giả định đóng client sẽ đóng mọi executor bên ngoài mà ứng dụng đã cung cấp.

## 13. Phát hiện rò rỉ tài nguyên trong test và production

Một lần test thành công không chứng minh không có leak. Hãy quan sát xu hướng qua nhiều vòng gửi request và cleanup.

### 13.1. Những tài nguyên cần kiểm tra

- Response `InputStream` hoặc `Stream<String>` chưa đóng.
- Custom `BodySubscriber` chưa hoàn tất hoặc không cancel subscription.
- `HttpClient` tạo liên tục nhưng không đóng theo lifecycle.
- Executor được tạo nhưng không shutdown/close.
- Request future vẫn pending sau khi test kết thúc.
- File tạm hoặc file response còn sót lại sau test lỗi.
- Server test chưa stop hoặc handler vẫn chờ latch.

### 13.2. Metrics và công cụ quan sát

`HttpClient` không cung cấp API công khai để đọc trực tiếp số connection trong pool. Không dùng reflection hoặc internal JDK API để phụ thuộc vào cấu trúc pool nội bộ.

Có thể kết hợp:

- Metrics của server: số request đang xử lý, connection mở, response chưa hoàn tất và thời gian phục vụ.
- Metrics của HTTP client hoặc thư viện wrapper: request đang chạy, timeout, lỗi kết nối và thời gian chờ.
- Hệ điều hành: số socket/file descriptor đang mở và trạng thái TCP khi cần điều tra sâu.
- `jcmd <pid> Thread.print`: quan sát thread và stack khi ứng dụng có dấu hiệu giữ tác vụ.
- JFR: theo dõi socket I/O, thread park, virtual thread pinning và các sự kiện runtime liên quan.

Không kết luận leak từ một snapshot đơn lẻ. Chụp metrics trước/sau một đợt test lặp, đợi cleanup hoàn tất rồi xem số socket, thread, file descriptor và request pending có trở về mức ổn định không.

## 14. Quy tắc viết test HTTP ổn định

1. Dùng loopback server hoặc mock server do test kiểm soát; tránh gọi Internet thật trong test unit/integration cơ bản.
2. Dùng port `0` để lấy cổng động, tránh hard-code port dễ xung đột.
3. Dùng `CountDownLatch`, `CompletableFuture` và timed wait để đồng bộ test; hạn chế `Thread.sleep()`.
4. Đặt timeout cho cả request lẫn thao tác chờ của test để test không treo vô hạn.
5. Luôn giải phóng latch, đóng stream, stop server và đóng executor trong `finally` hoặc try-with-resources.
6. Assert riêng transport error, timeout, cancellation và HTTP status 4xx/5xx.
7. Kiểm tra cause chain thay vì phụ thuộc một lớp exception bọc cố định.
8. Không assert rằng nhiều request bắt buộc dùng cùng một TCP socket; connection reuse là quyết định của implementation và điều kiện giao thức.
9. Với body lớn, dùng streaming handler và test việc đóng/cancel; tránh đọc toàn bộ vào memory nếu đó không phải mục tiêu.
10. Với retry, chỉ retry theo chính sách rõ ràng và xem xét idempotency; không tự động lặp lại POST hoặc thao tác có side effect nếu không có bảo đảm nghiệp vụ.

## 15. Tài liệu tham khảo chính thức

- [Java SE 21 API — `HttpClient`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, timeout, cancellation và lifecycle.
- [Java SE 21 API — `HttpRequest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout và body publisher.
- [Java SE 21 API — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): các cách tiếp nhận response body.
- [Java SE 21 API — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): subscriber có sẵn cho body processing.
- [Java SE 21 API — `HttpResponse.BodySubscriber`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): hợp đồng subscriber và hoàn tất body.
- [Java SE 21 API — `HttpServer`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): dựng HTTP server cục bộ để kiểm thử.
- [Java SE 21 API — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý executor và đóng tài nguyên.

Một test HTTP đáng tin cậy phải kiểm tra cả đường đi chưa hoàn tất và đường cleanup sau lỗi. Hãy mô phỏng server chậm hoặc ngắt kết nối bằng local server, đặt timeout có giới hạn, phân biệt exception mạng với HTTP status, và đóng response body, client, server cùng executor đúng lifecycle. Với Java 21, các API `HttpClient` và `BodyHandlers` đã cung cấp đủ điểm kiểm soát để kiểm thử các tình huống này mà không cần phụ thuộc vào API nội bộ của JDK.
