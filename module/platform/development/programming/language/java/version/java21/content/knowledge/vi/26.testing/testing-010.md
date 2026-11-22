# Kiểm thử tài nguyên HttpClient, Unicode và biên của API mới

Java 21 bổ sung các API vòng đời cho `java.net.http.HttpClient`, gồm `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, `isTerminated()` và `close()`. Khi kiểm thử client, cần xác nhận request đang chạy được xử lý theo chính sách shutdown, request mới bị từ chối sau shutdown, body stream được tiêu thụ hoặc đóng đúng cách và tài nguyên test được giải phóng. Với dữ liệu Unicode, cần kiểm tra byte encoding, code point và normalization riêng biệt; một chuỗi nhìn giống nhau chưa chắc có cùng biểu diễn UTF-8 hoặc cùng dãy code point.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), bài học tập trung vào kiểm thử các API ổn định, đặc biệt là lifecycle API của HttpClient được thêm từ Java 21. Ví dụ dùng JUnit Jupiter và `com.sun.net.httpserver.HttpServer` làm server cục bộ để không phụ thuộc dịch vụ bên ngoài. `jdk.httpserver` là module JDK; nếu dự án dùng `module-info.java`, test source cần quyền đọc module này. Các ví dụ không cần bật preview.

## Tổ chức tài nguyên trong test

Một test HTTP nên tạo server cục bộ trên cổng động, tạo `HttpClient` riêng cho test và đóng cả hai sau khi assertion hoàn tất. Cổng `0` yêu cầu hệ điều hành chọn cổng trống, tránh xung đột giữa test chạy song song hoặc giữa các lần chạy.

Ví dụ fixture JUnit Jupiter:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

abstract class HttpClientTestSupport {
    HttpServer server;
    ExecutorService serverExecutor;
    HttpClient client;
    URI baseUri;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverExecutor = Executors.newFixedThreadPool(2);
        server.setExecutor(serverExecutor);

        server.createContext("/echo", exchange -> {
            try {
                byte[] requestBytes;
                try (InputStream body = exchange.getRequestBody()) {
                    requestBytes = body.readAllBytes();
                }
                writeResponse(exchange, requestBytes, 200);
            } finally {
                exchange.close();
            }
        });

        server.start();
        baseUri = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
        client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
    }

    static void writeResponse(HttpExchange exchange, byte[] bytes, int status)
            throws IOException {
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    @AfterEach
    void stopResources() throws Exception {
        if (client != null) {
            client.close();
        }
        if (server != null) {
            server.stop(0);
        }
        if (serverExecutor != null) {
            serverExecutor.shutdown();
            if (!serverExecutor.awaitTermination(2, TimeUnit.SECONDS)) {
                serverExecutor.shutdownNow();
            }
        }
    }
}
```

Trong một dự án thực tế, fixture thường là lớp cha test hoặc extension để các test class tái sử dụng. Mỗi test vẫn cần sở hữu rõ client/server của nó. Nếu `@AfterEach` gọi `client.close()`, test có thể đã gọi `shutdown()` trước đó; `close()` là thao tác an toàn sau khi client đã terminated.

`HttpClient` nên được tái sử dụng trong phạm vi component hoặc test case. Không tạo và đóng client sau từng request trong production chỉ để kiểm thử được cleanup. Test cần xác minh ranh giới sở hữu: component nào tạo client thì component đó chịu trách nhiệm đóng client.

## Kiểm thử shutdown và awaitTermination

`shutdown()` bắt đầu orderly shutdown. Các request đã được gửi bằng `send()` hoặc `sendAsync()` được phép chạy đến hoàn tất; request mới không được chấp nhận. Phương thức không đợi các request cũ hoàn tất. `awaitTermination(Duration)` chờ tối đa thời lượng chỉ định và trả về `true` nếu mọi hoạt động đã kết thúc, `false` nếu hết thời gian trước khi client terminated.

Test quan trọng là giữ một request đang hoạt động, gọi shutdown, xác nhận client chưa terminated, sau đó giải phóng server và chờ client kết thúc:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class HttpClientLifecycleTest extends HttpClientTestSupport {
    @Test
    void shutdownWaitsForAnAlreadySubmittedExchange() throws Exception {
        CountDownLatch requestArrived = new CountDownLatch(1);
        CountDownLatch releaseResponse = new CountDownLatch(1);

        server.createContext("/hold", exchange -> {
            requestArrived.countDown();
            try {
                if (releaseResponse.await(3, TimeUnit.SECONDS)) {
                    writeResponse(exchange, "done".getBytes(StandardCharsets.UTF_8), 200);
                } else {
                    writeResponse(exchange, new byte[0], 504);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });

        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/hold"))
                .GET()
                .build();
        CompletableFuture<HttpResponse<String>> pending = client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        try {
            assertTrue(requestArrived.await(2, TimeUnit.SECONDS));

            client.shutdown();
            assertFalse(client.isTerminated());
            assertFalse(client.awaitTermination(Duration.ofMillis(100)));

            releaseResponse.countDown();
            assertEquals(200, pending.get(3, TimeUnit.SECONDS).statusCode());
            assertTrue(client.awaitTermination(Duration.ofSeconds(3)));
            assertTrue(client.isTerminated());
        } finally {
            releaseResponse.countDown();
        }
    }
}
```

`CountDownLatch` làm cho test kiểm soát được thời điểm server đã nhận request. Không dùng `Thread.sleep()` để đoán request đã bắt đầu hay chưa vì cách đó dễ tạo test chập chờn. Timeout ngắn trong `awaitTermination()` chỉ kiểm tra rằng exchange đang bị giữ chưa thể kết thúc; sau khi mở latch, test chờ response và termination với giới hạn rõ ràng.

`isTerminated()` không phải cờ “đã gọi shutdown”. API `HttpClient` không có `isShutdown()` tương tự `ExecutorService`. `isTerminated()` chỉ trả `true` sau khi đã gọi shutdown hoặc shutdownNow và tất cả hoạt động liên quan đã hoàn tất. Vì vậy, đừng dùng `isTerminated()` để phân biệt client đang hoạt động với client vừa bắt đầu shutdown nhưng vẫn còn request.

## Kiểm thử request mới sau shutdown

Sau `shutdown()`, request mới không được chấp nhận. Với JDK built-in HttpClient, các phương thức gửi request thể hiện lỗi này qua `IOException` (đối với `sendAsync()`, future hoàn tất exceptional). Test nên xác nhận lỗi ở ranh giới public API:

```java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.ExecutionException;
import org.junit.jupiter.api.Test;

class HttpClientRejectAfterShutdownTest extends HttpClientTestSupport {
    @Test
    void rejectsNewAsyncRequestAfterShutdown() {
        client.shutdown();

        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/echo"))
                .GET()
                .build();

        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                        .get(2, java.util.concurrent.TimeUnit.SECONDS));

        assertInstanceOf(IOException.class, failure.getCause());
    }
}
```

Nếu dùng `join()` thay cho `get()`, lỗi được bọc trong `CompletionException` thay vì `ExecutionException`. Test cần kiểm tra cause thay vì phụ thuộc vào cách wrapper được chọn. Không bắt buộc kiểm tra chính xác message vì message có thể thay đổi giữa các bản JDK/provider.

## Kiểm thử shutdownNow mà không giả định dừng tức thời

`shutdownNow()` cố gắng khởi tạo immediate shutdown. Implementation có thể thử interrupt các operation đang hoạt động, nhưng đặc tả không bảo đảm chúng sẽ kết thúc hoặc thread đang chờ chúng sẽ luôn được thông báo. Vì vậy, test không nên khẳng định mọi future bị hủy ngay lập tức hoặc mọi request phía server đã rollback.

Với client không còn request đang chạy, có thể kiểm tra trạng thái kết thúc:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class HttpClientShutdownNowTest extends HttpClientTestSupport {
    @Test
    void shutdownNowTerminatesAnIdleClient() throws InterruptedException {
        client.shutdownNow();

        assertTrue(client.awaitTermination(Duration.ofSeconds(2)));
        assertTrue(client.isTerminated());
    }
}
```

Đây là test cho JDK built-in implementation khi client idle. Với request đang chạy, chỉ kiểm tra các bảo đảm được tài liệu hóa và chấp nhận rằng việc dừng là best effort. Nếu nghiệp vụ cần biết server đã thực hiện side effect hay chưa, phải kiểm tra trạng thái nghiệp vụ hoặc dùng idempotency key; trạng thái future ở client không chứng minh server đã rollback.

## Kiểm thử close và quyền sở hữu tài nguyên

`HttpClient` triển khai `AutoCloseable` trong Java 21. `close()` bắt đầu orderly shutdown và chờ các hoạt động đã gửi hoàn tất. Nếu thread gọi bị interrupt trong khi close đang chờ, implementation có thể gọi `shutdownNow()`, tiếp tục chờ hoạt động đang chạy kết thúc và khôi phục interrupt status trước khi trả về.

Với client có vòng đời ngắn và chỉ phục vụ một thao tác, try-with-resources giúp thể hiện quyền sở hữu:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

static int fetchStatus() throws Exception {
    try (HttpClient client = HttpClient.newHttpClient()) {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/health"))
                .GET()
                .build();

        return client.send(request, HttpResponse.BodyHandlers.discarding())
                .statusCode();
    }
}
```

Với client dùng chung cho toàn service, không đặt client trong try-with-resources của mỗi request. Hãy đóng nó ở lifecycle của service. Test nên xác nhận service gọi close khi dừng và không đóng client dùng chung trong lúc request khác còn cần sử dụng.

## Kiểm thử response body stream để không làm shutdown bị treo

JDK built-in HttpClient cần request được xem là hoàn tất trước khi orderly shutdown có thể kết thúc. Khi dùng `BodyHandlers.ofInputStream()`, `ofLines()` hoặc publisher/streaming subscriber, ứng dụng phải đọc body đến hết, đóng stream hoặc hủy subscription. Nếu bỏ quên, request có thể vẫn mở và `awaitTermination()` có thể chờ lâu.

Ví dụ đọc stream và đóng tài nguyên:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class HttpClientBodyResourceTest extends HttpClientTestSupport {
    @Test
    void closesStreamingResponseBody() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/echo"))
                .GET()
                .build();

        HttpResponse<InputStream> response = client.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            assertEquals("", new String(body.readAllBytes(), StandardCharsets.UTF_8));
        }

        client.shutdown();
        assertTrue(client.awaitTermination(Duration.ofSeconds(2)));
    }
}
```

Với `BodyHandlers.ofString()` hoặc `ofByteArray()`, body được thu thập trước khi response hoàn tất, nên không có stream mà caller phải đóng. Với `ofLines()`, dùng try-with-resources cho `Stream<String>`. Với custom `BodySubscriber`, phải request dữ liệu cho đến `onComplete()`/`onError()` hoặc cancel subscription khi không cần nữa.

## Kiểm thử Unicode qua HTTP

HTTP truyền byte; `String` trong Java biểu diễn chuỗi bằng UTF-16 code unit. Khi gửi hoặc nhận text, test cần xác định charset ở cả hai phía. UTF-8 là lựa chọn phổ biến và nên được ghi rõ trong `BodyPublisher`, `BodyHandler` và `Content-Type`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import org.junit.jupiter.api.Test;

class HttpClientUnicodeTest extends HttpClientTestSupport {
    @Test
    void roundTripsUtf8WithoutChangingCodePoints() throws Exception {
        String nfc = "\u00E9";
        String nfd = "e\u0301";
        String payload = "Xin chào, Việt Nam — " + nfc + " / " + nfd + " / 😀 / 漢字";

        assertNotEquals(nfc, nfd);
        assertEquals(nfc, Normalizer.normalize(nfd, Normalizer.Form.NFC));
        assertEquals(2, "😀".length());
        assertEquals(1, "😀".codePointCount(0, "😀".length()));

        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/echo"))
                .header("Content-Type", "text/plain; charset=utf-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        payload, StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(200, response.statusCode());
        assertEquals(payload, response.body());
        assertEquals(payload.getBytes(StandardCharsets.UTF_8).length,
                response.body().getBytes(StandardCharsets.UTF_8).length);
    }
}
```

Test này xác nhận server echo trả lại đúng chuỗi sau khi encode UTF-8 và decode UTF-8. Hai chuỗi `é` dạng NFC và `e` cộng combining acute dạng NFD nhìn có thể giống nhau nhưng `String.equals()` trả về `false` vì dãy code unit khác nhau. Java không tự động normalize Unicode khi gửi HTTP; nếu hợp đồng nghiệp vụ yêu cầu canonical equivalence, ứng dụng phải normalize rõ ràng và test riêng.

Ký tự ngoài Basic Multilingual Plane như emoji được biểu diễn bằng surrogate pair trong UTF-16, nên `String.length()` đếm hai code unit trong khi `codePointCount()` đếm một code point. Không dùng `length()` như số ký tự hiển thị cho mọi văn bản Unicode.

## Kiểm thử mã hóa query parameter

Khi đưa text Unicode vào query string, cần percent-encode giá trị theo UTF-8 thay vì nối chuỗi thô. `URLEncoder` và `URLDecoder` dùng quy tắc form encoding, trong đó dấu cách được biểu diễn bằng `+`; chúng phù hợp cho query/form value nhưng không phải encoder chung cho path segment.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class UnicodeQueryTest extends HttpClientTestSupport {
    @Test
    void encodesAndDecodesUnicodeQueryValue() throws Exception {
        String original = "Đà Nẵng & C++ 😀";
        String encoded = URLEncoder.encode(original, StandardCharsets.UTF_8);

        server.createContext("/query", exchange -> {
            try {
                String rawQuery = exchange.getRequestURI().getRawQuery();
                String decoded = URLDecoder.decode(
                        rawQuery.substring("q=".length()), StandardCharsets.UTF_8);
                writeResponse(exchange, decoded.getBytes(StandardCharsets.UTF_8), 200);
            } finally {
                exchange.close();
            }
        });

        URI uri = baseUri.resolve("/query?q=" + encoded);
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals("q=" + encoded, uri.getRawQuery());
        assertEquals(200, response.statusCode());
        assertEquals(original, response.body());
    }
}
```

Test integration trên kiểm tra cả raw query được tạo ra lẫn round-trip qua HTTP server. Handler chỉ decode phần value sau tiền tố `q=`; với query có nhiều tham số, cần tách từng cặp key/value trước khi decode. Không decode toàn bộ raw query trước khi tách cặp vì ký tự `&` đã encode trong value phải được giữ như dữ liệu.

## Kiểm thử Unicode normalization và dữ liệu không hợp lệ

Unicode có thể có nhiều biểu diễn cho cùng nội dung nhìn thấy. Ví dụ NFC dùng ký tự dựng sẵn, còn NFD dùng base character cộng combining mark. Nếu API lưu hoặc so sánh định danh, cần xác định hợp đồng:

- Nếu API bảo toàn nguyên văn, test phải xác nhận code point sequence được round-trip mà không tự normalize.
- Nếu API yêu cầu canonical equivalence, normalize ở ranh giới được chỉ định, thường là NFC, rồi test cả NFC và NFD cho cùng kết quả nghiệp vụ.
- Nếu API từ chối chuỗi có surrogate không hợp lệ, kiểm tra trước khi encode và trả lỗi validation rõ ràng.

Java `String` có thể chứa unpaired surrogate dù đó không phải chuỗi Unicode scalar hợp lệ. Các tiện ích chuyển đổi như `String.getBytes(UTF_8)` thay thế input malformed bằng replacement bytes; nếu hợp đồng cần từ chối dữ liệu đó, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` và kiểm thử validation riêng. Không giả định `String.getBytes(UTF_8)` luôn ném lỗi với mọi malformed surrogate.

## Kiểm thử biên của HttpRequest.Builder

API mới hoặc API có nhiều overload cần được test ở ranh giới hợp đồng: URI phải hợp lệ, timeout phải dương và header phải có tên/giá trị hợp lệ. Các trường hợp sai nên được kiểm tra tại nơi builder tạo request, thay vì chờ gửi mạng mới phát hiện.

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class HttpRequestBoundaryTest {
    @Test
    void rejectsRelativeUri() {
        assertThrows(IllegalArgumentException.class,
                () -> HttpRequest.newBuilder(URI.create("relative/path")));
    }

    @Test
    void rejectsZeroTimeout() {
        assertThrows(IllegalArgumentException.class,
                () -> HttpRequest.newBuilder()
                        .uri(URI.create("https://example.com"))
                        .timeout(Duration.ZERO));
    }

    @Test
    void rejectsInvalidHeaderName() {
        assertThrows(IllegalArgumentException.class,
                () -> HttpRequest.newBuilder()
                        .uri(URI.create("https://example.com"))
                        .header("Bad Header", "value"));
    }
}
```

Các test trên kiểm tra các input không hợp lệ của builder. Với request hợp lệ, hãy kiểm thử thêm timeout, method, header và body theo hợp đồng API của ứng dụng. Không phụ thuộc vào message exception; chỉ kiểm tra loại exception hoặc kết quả đã được tài liệu hóa.

## Phân biệt HTTP status với lỗi transport

`HttpClient.send()` không tự ném exception chỉ vì server trả HTTP 4xx hoặc 5xx. Đó vẫn là một `HttpResponse`; ứng dụng phải kiểm tra `statusCode()` theo chính sách. Exception thường phản ánh lỗi gửi/nhận như I/O, timeout hoặc interruption.

```java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

assertEquals(404, response.statusCode());
```

Test nên tách ít nhất ba nhóm: response HTTP thành công, response HTTP lỗi nhưng transport hoàn tất, và lỗi transport/timeout. Nếu gộp tất cả thành “request thất bại”, test có thể bỏ sót khác biệt quan trọng giữa server từ chối request và client không nhận được response.

Ví dụ, server cục bộ không có context `/missing` sẽ trả 404; client vẫn nhận một response bình thường:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class HttpClientStatusTest extends HttpClientTestSupport {
    @Test
    void treatsNotFoundAsAnHttpResponse() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(baseUri.resolve("/missing"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        assertEquals(404, response.statusCode());
    }
}
```

## Kiểm thử HttpClient API với custom implementation

`HttpClient` là abstract class. Các lifecycle method có implementation mặc định trong lớp cơ sở; một số mặc định không thực hiện shutdown thực sự (`shutdown()` mặc định không làm gì, `awaitTermination()` mặc định trả `true`, `isTerminated()` mặc định trả `false`, `shutdownNow()` mặc định gọi `shutdown()`). JDK built-in implementation override các method này để cung cấp hành vi thực tế.

Nếu ứng dụng hoặc test framework tạo custom subclass/fake của `HttpClient`, đừng giả định các lifecycle method mặc định mô phỏng được hành vi của client JDK. Fake cần override các method liên quan nếu test đang kiểm tra lifecycle. Với test integration về shutdown, ưu tiên client thật từ `HttpClient.newBuilder().build()` và server cục bộ.

## Những lỗi test thường gặp

- **Dùng server internet công cộng:** test phụ thuộc DNS, mạng, TLS và trạng thái dịch vụ; ưu tiên server loopback cho test chức năng.
- **Dùng sleep để chờ request:** tạo race condition; dùng `CountDownLatch` hoặc một tín hiệu đồng bộ rõ ràng.
- **Không đóng client:** có thể để lại hoạt động nền và làm chậm hoặc treo quá trình test.
- **Không đọc/đóng streaming body:** có thể khiến request chưa hoàn tất và `awaitTermination()` không kết thúc.
- **Giả định shutdownNow chắc chắn dừng mọi request:** đặc tả chỉ đảm bảo nỗ lực best-effort đối với operation đang chạy.
- **Chỉ kiểm tra Unicode bằng mắt:** NFC/NFD hoặc surrogate pair có thể không được phân biệt bằng cách nhìn chuỗi.
- **Dùng `String.length()` làm số ký tự:** đây là số UTF-16 code unit, không phải số code point hay grapheme cluster.
- **Giả định 4xx/5xx là exception:** đó là HTTP response; phải assert status code.
- **Dựa vào exception message:** message có thể khác theo JDK/provider; kiểm tra loại exception và cause.

## Quy trình kiểm thử trong dự án Java 21

1. **Tạo fixture độc lập.** Dùng HttpServer loopback với cổng động và một HttpClient riêng cho test.
2. **Đóng tài nguyên có chủ đích.** Dừng server, shutdown executor test và close client trong lifecycle hook.
3. **Kiểm tra graceful shutdown.** Giữ request đang chạy bằng latch, gọi `shutdown()`, xác nhận chưa terminated rồi giải phóng request và chờ `awaitTermination()`.
4. **Kiểm tra request mới bị từ chối.** Sau shutdown, xác nhận `sendAsync()` hoàn tất exceptional với lỗi I/O theo hợp đồng JDK built-in.
5. **Kiểm tra shutdownNow theo best effort.** Không khẳng định operation đang chạy chắc chắn dừng ngay hoặc server rollback side effect.
6. **Kiểm tra body resource.** Đọc đến hết hoặc đóng InputStream/Stream; custom subscriber phải request dữ liệu hoặc cancel.
7. **Kiểm tra Unicode theo byte và code point.** Chỉ định UTF-8 ở request/response, kiểm tra round-trip, NFC/NFD và supplementary code point.
8. **Kiểm tra API boundary.** Bao phủ URI, timeout, header, status code và lỗi transport.
9. **Tách test đơn vị và integration.** Test builder/normalization không cần mạng; test lifecycle và encoding dùng server loopback.
10. **Chạy với JDK 21.** Dùng API ổn định của Java 21; không bật preview cho các nội dung trong bài.

Kiểm thử tốt cho `HttpClient` không chỉ xác nhận status code. Nó còn xác nhận ai sở hữu client, request nào được phép hoàn tất khi shutdown, body stream có được giải phóng, và test có tự dọn server/executor hay không. Với Unicode, cần kiểm tra đúng charset, byte sequence, code point và normalization theo hợp đồng. Tách các ranh giới này giúp test ổn định, không phụ thuộc mạng ngoài và phát hiện lỗi tài nguyên trước khi triển khai.

## Tài liệu tham khảo

- [Oracle Java 21 API: HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java 21 API: HttpRequest](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java 21 API: HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java 21 API: String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 API: Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html)
- [Oracle Java 21 API: HttpServer](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
