# Thực nghiệm: Kiểm thử HttpClient đồng bộ, bất đồng bộ, cookie và hủy yêu cầu

Java 17+ có HTTP client chuẩn `java.net.http.HttpClient`. Một `HttpClient` có thể gọi HTTP **đồng bộ** bằng `send()`, **bất đồng bộ** bằng `sendAsync()`, dùng `CookieManager` để quản lý cookie và thử hủy một HTTP exchange đang chờ qua `CompletableFuture.cancel(true)`. Để phân biệt hành vi API với may rủi của mạng, bài này tạo **server loopback trong cùng chương trình** rồi thực nghiệm và kiểm tra từng trường hợp.

Đề bài thuộc **Thực nghiệm mạng** và bao gồm bốn mục tiêu:

1. Gọi `HttpClient.send()` trên một endpoint trả `200 PONG`, đọc đúng status/body và phân biệt HTTP status error với I/O exception.
2. Gửi **hai request bất đồng bộ cùng lúc** bằng `sendAsync()`, dùng `CompletableFuture.allOf()` và hai `CountDownLatch` để xác minh cả hai handler ở server đã vào trạng thái chờ **trước khi** nhận lệnh cho tiếp tục.
3. Gắn `CookieManager` vào một HttpClient cụ thể; kiểm tra `Set-Cookie` được lưu, `Cookie` được gửi đúng `Path`, không được gửi ra ngoài phạm vi, không xuất hiện ở client không có cookie handler và bị từ chối khi dùng `CookiePolicy.ACCEPT_NONE`.
4. Gọi `cancel(true)` khi một request vẫn đang chờ nhưng **server đã bắt đầu xử lý**; quan sát trạng thái Future và chứng minh hủy client **không đồng nghĩa hoàn tác công việc server**.

Phần thực hành sử dụng một file **`HttpClientLab.java`** chạy được từ Java 17, không yêu cầu Maven, Gradle, JUnit, Internet hoặc bên thứ ba. Mã đã được **biên dịch bằng `javac --release 17` và chạy ba lần liên tiếp trên JDK 24**, với đầu ra được ghi chính xác trong bài. Tài liệu cũng nêu timeout, exceptions, cancellation race, cookie scope, isolation và rủi ro khi dùng các API này trong production.

## 1. Các lớp và module cần biết

| Thành phần | Module/package | Chức năng |
| --- | --- | --- |
| `HttpClient` | `java.net.http` | Client tái sử dụng connection/pool và thực hiện HTTP request |
| `HttpRequest` | `java.net.http` | URI, method, headers, body, timeout của yêu cầu |
| `HttpResponse<T>` | `java.net.http` | Status, headers, body và metadata response |
| `HttpResponse.BodyHandlers` | `java.net.http` | Chọn cách nhận body: String, byte[], InputStream, file, Publisher |
| `CompletableFuture<T>` | `java.util.concurrent` | Đại diện kết quả bất đồng bộ, ghép stage, chờ, timeout, cancel |
| `CookieManager` | `java.net` | Chính sách nhận cookie và lưu/gửi qua CookieStore |
| `CookiePolicy` | `java.net` | Ví dụ ACCEPT_ORIGINAL_SERVER, ACCEPT_NONE |
| `HttpCookie` / `CookieStore` | `java.net` | Cookie attributes và cookie đã lưu |
| `CountDownLatch` | `java.util.concurrent` | Đồng bộ các bước test, không phụ thuộc Thread.sleep |
| `HttpServer` | `jdk.httpserver` | Server HTTP/1.1 nhúng để tạo fixture kiểm thử |

Kiểm tra JDK và module:

~~~bash
java --version
java --describe-module java.net.http
java --describe-module jdk.httpserver
~~~

Hai module này khác nhau: `java.net.http` phục vụ **client** HTTP/WebSocket; `jdk.httpserver` có HTTP/HTTPS **server** nhúng. Bài dùng cả hai để kiểm thử end-to-end trên loopback.

## 2. So sánh send() và sendAsync() không suy đoán

| Đặc điểm | `send(request, handler)` | `sendAsync(request, handler)` |
| --- | --- | --- |
| Kiểu kết quả | `HttpResponse<T>` | `CompletableFuture<HttpResponse<T>>` |
| Luồng gọi | Chờ cho đến khi response được xử lý theo BodyHandler | Nhận Future ngay; HTTP tiếp tục bất đồng bộ |
| Lấy body String | `response.body()` sau khi send trả | `future.get()/join()` thành công rồi `body()` |
| Lỗi I/O | `IOException`, `InterruptedException` | Future hoàn tất exceptionally; `get()`/`join()` ném wrapper phù hợp |
| Chạy nhiều request | Gửi tuần tự nếu gọi send trên cùng thread | Có thể tạo nhiều Futures trước khi chờ |
| Trạng thái cookie | Dùng CookieHandler của HttpClient | Cùng cơ chế cookie của HttpClient |
| Hủy | Thread interrupt khiến default client thử hủy exchange | `cancel(true)` trên cancelable HTTP Future thử hủy exchange |
| Response streaming | Tùy BodyHandler, không phải body nào cũng đã được consume | Cũng tùy BodyHandler; Future xong chưa chắc stream đọc EOF |

**API bất đồng bộ không tự làm server nhanh hơn.** Nó giúp thread gọi tiếp tục làm việc trong khi I/O tiến hành. Nếu code gọi `sendAsync(request).join()` ngay lập tức và không có việc nào khác, thread vẫn block cho đến khi có kết quả.

~~~text
Đồng bộ:
  main --> send() -------- [đợi response] --------> HttpResponse<String>

Bất đồng bộ:
  main --> sendAsync() --> CompletableFuture ------> stage processing
             |
             +-- HTTP work tiếp tục trên nền
             +-- main có thể khởi tạo request khác

Hai request bất đồng bộ:
  sendAsync(A) -> futureA ---+
                            +--> allOf(A,B).get(...)
  sendAsync(B) -> futureB ---+
~~~

Khi dùng `BodyHandlers.ofString(StandardCharsets.UTF_8)`, Future thành công sau khi handler đã gom text body thành String. Nếu đổi sang `BodyHandlers.ofInputStream()` hoặc `ofPublisher()`, Future có thể hoàn thành **trước khi body đọc xong**. Bài này dùng `ofString` để mỗi scenario có một kết quả hoàn chỉnh, nhưng khi triển khai thật cần kiểm soát body size; `ofString` có thể tiêu tốn nhiều RAM cho response không giới hạn.

### Đồng bộ và kiểm tra status

~~~java
// Fragment Java 17+, request và client đã được tạo.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

if (response.statusCode() == 200) {
    System.out.println(response.body());
} else {
    System.out.println("Unexpected HTTP status: "
            + response.statusCode());
}
~~~

Một HTTP 404/500 **không mặc định làm `send()` ném IOException**: response HTTP lỗi vẫn có thể nhận thành công ở tầng transport. Hãy kiểm tra status, headers và body theo protocol nghiệp vụ. Ngược lại, connect failure, timeout hoặc TCP reset thường là lỗi I/O, có thể không có HttpResponse để đọc.

## 3. Dùng loopback server để kiểm thử thật

Gọi một API public có thể gặp DNS, proxy, TLS, CAPTCHA, rate limit, redirect và cookie policy thay đổi. Để **có thể tái hiện** hành vi cancellation và concurrency, cần tự kiểm soát server.

~~~java
// Fragment Java 17+, chưa phải chương trình độc lập.
InetAddress loopback = InetAddress.getByAddress(
        new byte[]{127, 0, 0, 1});

HttpServer server = HttpServer.create(
        new InetSocketAddress(loopback, 0), 32);
ExecutorService workers = Executors.newFixedThreadPool(8);

server.createContext("/ping", exchange -> {
    // Gửi 200 và body PONG.
});
server.setExecutor(workers);
server.start();

int actualPort = server.getAddress().getPort();
~~~

- Bind `127.0.0.1`: chỉ truy cập được trên máy/local network namespace của test. Không bind `0.0.0.0` cho bài lab.
- Port `0`: hệ điều hành chọn cổng trống, tránh đụng port đã dùng.
- `backlog=32` không phải giới hạn 32 request đồng thời; nó liên quan hàng chờ TCP accept.
- Executor tám threads giúp hai handlers có thể cùng chờ gate mà không chiếm hết worker pool.
- Mọi latch có timeout 5s và được mở trong `finally` để tránh test treo vô thời hạn.

Các context:

| Path | Phản hồi | Dùng kiểm tra |
| --- | --- | --- |
| `/ping` | `200 PONG` | send() |
| `/async/one` | `200 ONE` sau khi gate mở | sendAsync A |
| `/async/two` | `200 TWO` sau khi gate mở | sendAsync B |
| `/cookie/set` | `Set-Cookie: labToken=abc123; Path=/cookie; HttpOnly` | cookie acceptance/storage |
| `/cookie/check` | body true/false theo Cookie header | cookie được gửi đúng path |
| `/outside` | body true/false theo Cookie header | cookie không gửi ngoài path |
| `/cancel` | Chờ gate rồi thử trả TOO_LATE | client cancellation trong khi server đã làm việc |

Bài lab dùng HTTP plaintext trên loopback với **token giả**, không sử dụng cho authentication production. Khi dùng cookie phiên thật, phải có HTTPS và các thuộc tính/kiểm tra bảo mật phù hợp.

## 4. Tạo HttpClient và cấu hình cookie

~~~java
// Fragment Java 17+.
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(3))
        .cookieHandler(jar)
        .build();
~~~

Ý nghĩa:

- `HttpClient.newBuilder().build()` tạo client có thể tái sử dụng nhiều request; object HttpClient đã build là immutable về cấu hình.
- `CookieManager(null, policy)` dùng `CookieStore` mặc định **in-memory**, phù hợp lab; state trong store vẫn thay đổi theo responses.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` là chính sách cookie của JDK, giới hạn nguồn cookie được chấp nhận.
- `cookieHandler(jar)` gắn store/policy cho **client cụ thể**. Nếu tạo client **không** cấu hình CookieHandler, không nên mặc định nó sẽ tự có cùng browser session cookies.
- `version(HTTP_1_1)` chọn HTTP/1.1 preference cho thí nghiệm server nhúng JDK. Ngoài lab, version preference không tự làm client có HTTP/2 nếu server không hỗ trợ.
- `connectTimeout(3s)` chỉ chi phối **kết nối mới** cần mở. Nó không bảo đảm toàn bộ request/body kết thúc trong ba giây.
- `HttpRequest.Builder.timeout(Duration)` được đặt riêng trên request để giới hạn HTTP exchange theo API.

**Java 17 không có HttpClient.close()/shutdown()/AutoCloseable**. Đừng viết `try (HttpClient client = HttpClient.newHttpClient())` trong code có `--release 17`; các API lifecycle này chỉ xuất hiện từ Java 21. Trong Java 17 vẫn phải xử lý streaming bodies, cancel outstanding requests khi cần, và shutdown **executor của ứng dụng** riêng.

### Không dùng global cookie jar khi cần isolation

`CookieHandler.setDefault(...)` làm thay đổi default của process ở những API sử dụng global handler, khiến tests dễ rò trạng thái. Với HttpClient, builder rõ ràng hơn. Hai HttpClients được tạo khác nhau **nhưng cùng dùng một CookieManager object** có thể chia sẻ cookies; tạo cookie jar riêng cho mỗi user/test identity nếu mục tiêu là isolation.

## 5. Gửi hai request bất đồng bộ và xác nhận overlap

Một kiểm thử yếu là gọi hai lần sendAsync rồi thấy hai response. Nó chưa chắc chứng minh xử lý đồng thời, vì request B có thể chỉ khởi chạy khi A đã hoàn tất nếu code gọi join sai chỗ.

Bài này đặt `CountDownLatch(2)` ở phía server và một gate cho phép handler đi tiếp:

~~~text
Client                                       Server (8 worker threads)

sendAsync(/async/one) --------------------> handler one
                                             BOTH_ASYNC.countDown() [còn 1]
                                             RELEASE_ASYNC.await(...)

sendAsync(/async/two) --------------------> handler two
                                             BOTH_ASYNC.countDown() [còn 0]
                                             RELEASE_ASYNC.await(...)

BOTH_ASYNC.await(5s) => true
RELEASE_ASYNC.countDown() ----------------> cả hai handlers tiếp tục
                                             one trả ONE, two trả TWO

CompletableFuture.allOf(one,two).get(5s)
=> hai HttpResponse<String> đã complete
~~~

Điểm chứng minh overlap là `asyncBothReachedServer=true`: **cả hai handler đã vào gate trước khi được nhả**. Nó không phụ thuộc một Thread.sleep ước lượng. Với chỉ một worker ở server, handler đầu có thể chiếm thread và không cho handler thứ hai bắt đầu, khiến gate timeout; đây là lý do phải cấu hình pool phù hợp.

~~~java
// Fragment Java 17+, client, base, get(...), các latches đã có.
CompletableFuture<HttpResponse<String>> one =
        client.sendAsync(get(base, "/async/one"),
                HttpResponse.BodyHandlers.ofString(UTF8));

CompletableFuture<HttpResponse<String>> two =
        client.sendAsync(get(base, "/async/two"),
                HttpResponse.BodyHandlers.ofString(UTF8));

boolean bothReached = BOTH_ASYNC.await(5, TimeUnit.SECONDS);
RELEASE_ASYNC.countDown();
if (!bothReached) {
    throw new IllegalStateException("Requests did not overlap");
}
CompletableFuture.allOf(one, two).get(5, TimeUnit.SECONDS);
System.out.println(one.join().body());
System.out.println(two.join().body());
~~~

`CompletableFuture.allOf()` trả `CompletableFuture<Void>`, không trả List<HttpResponse>. Bạn vẫn lấy result từ từng Future sau khi hoàn tất. Nếu một HTTP request lỗi, `allOf.get()` có thể ném `ExecutionException`; nó **không tự cancel request còn lại**.

### Anti-pattern: submit tuần tự trá hình

~~~java
// Anti-pattern: request B chưa được tạo khi đang chờ request A.
String a = client.sendAsync(reqA, handler).join().body();
String b = client.sendAsync(reqB, handler).join().body();
~~~

Sửa bằng việc khởi tạo **cả hai futures trước**, sau đó chờ nhóm kết quả. Khi processing sau HTTP (parse JSON, ghi DB) được thực thi ở stage riêng, cần chờ **processing futures** tương ứng chứ không chỉ response futures nếu yêu cầu test là hoàn tất toàn bộ nghiệp vụ.

## 6. CookieManager: lưu, gửi đúng Path, từ chối và cách ly

Khi server gửi response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: labToken=abc123; Path=/cookie; HttpOnly
Content-Type: text/plain; charset=UTF-8

COOKIE_SET
~~~

Đây là ví dụ thể hiện các header quan trọng, **không phải bản chép chính xác mọi byte wire**. CookieHandler trong HttpClient có thể nhận `Set-Cookie`, lưu cookie theo policy/store và đính kèm `Cookie` vào request sau nếu host/path/flags phù hợp.

Kiểm thử cần **hai lượt request**:

1. `GET /cookie/set` nhận `Set-Cookie`.
2. `GET /cookie/check` kiểm tra server thực sự thấy `Cookie: labToken=abc123`.

Chỉ kiểm tra `CookieStore.getCookies()` chưa đủ: cookie có thể được lưu nhưng không được gửi do Path, Domain, Secure hoặc expiry. Bài lab kiểm tra cả store và header do server nhận.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Jar ACCEPT_ORIGINAL_SERVER sau /cookie/set | Cookie có trong store |
| Cùng client gọi /cookie/check | Có cookie: path bắt đầu bằng /cookie/ |
| Cùng client gọi /outside | Không gửi labToken do Path=/cookie |
| HttpClient mới không cookie handler | Không gửi cookie của jar cũ |
| CookieManager mới ACCEPT_NONE | Không lưu/gửi cookie từ Set-Cookie |

~~~java
// Fragment Java 17+.
CookieManager rejectingJar = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);

HttpClient rejectingClient = HttpClient.newBuilder()
        .cookieHandler(rejectingJar)
        .build();
~~~

`CookieManager` có `CookieStore` với lifetime do ứng dụng quản lý. Mặc định đây là in-memory store; đừng giả định cookie tồn tại sau process restart. Hai identity dùng chung jar có nguy cơ dùng chung session; dùng cookie jar riêng theo user và không log cookie values.

### Cookie attributes và security

| Attribute | Ý nghĩa | Lưu ý thực tế |
| --- | --- | --- |
| `Path=/cookie` | Scope URL path được gửi | Không phải security boundary thay authorization |
| `Domain` | Scope host/domain | Host-only và domain cookies khác nhau |
| `Max-Age/Expires` | Thời gian sống cookie | Cookies có thể expire, không tồn tại vô hạn |
| `Secure` | Chỉ gửi trong ngữ cảnh kết nối bảo mật theo cookie policy | Lab dùng HTTP loopback nên không đặt Secure |
| `HttpOnly` | Hạn chế truy cập từ JavaScript của browser | **Không** ngăn Java HTTP client gửi cookie hợp lệ |
| `SameSite` | Browser cross-site behavior | Java CookieManager **không phải browser**, không mặc nhiên áp đủ browser CSRF semantics |

Không nhầm Path restriction với authorization. HTTPS, cookie Secure/HttpOnly phù hợp, server-side session validation, session rotation và CSRF protection vẫn cần thiết cho hệ thống có người dùng. `CookiePolicy.ACCEPT_ALL` có thể hữu ích ở tình huống đặc biệt nhưng không nên chọn làm mặc định cho ứng dụng không đáng tin khi chưa có risk assessment.

## 7. Hủy yêu cầu: cancel Future không rollback server

Đây là điểm khó nhất. Theo Javadoc Java 17, default HttpClient trả về cancelable Futures. Gọi `cancel(true)` trên HTTP Future **chưa complete** khiến implementation **thử** hủy exchange và thu hồi tài nguyên. Không có cam kết về thời điểm hủy được áp dụng:

- HTTP/1.1 có thể bị đóng TCP connection đột ngột.
- HTTP/2 có thể reset stream và đôi khi connection.
- Server vẫn có thể đã nhận request, đang làm việc, hoặc **đã commit một side effect**.
- Cancel không phải giao thức rollback giao dịch trên server.

Bài thực nghiệm chủ động cho server thực hiện tác động mô phỏng trước cancel:

~~~text
Client                                       Server

sendAsync(GET /cancel) -------------------> handler vào /cancel
                                            SERVER_EFFECT.set(true)
                                            CANCEL_ENTERED.countDown()
                                            đợi RELEASE_CANCEL

CANCEL_ENTERED.await(5s) => true
SERVER_EFFECT.get()       => true
slow.cancel(true)
    |
    +-- Future báo exceptional/cancellation
    +-- Không khẳng định server đã rollback

RELEASE_CANCEL.countDown() --------------> server thử trả TOO_LATE
                                            (socket có thể đã bị đóng)
                                            CANCEL_FINISHED.countDown()

Client kiểm tra:
  serverEffectBeforeCancel=true
  cancelAccepted=true
  cancelFutureExceptional=true
  cancelOutcomeHasCancellation=true
  cancelHandlerFinished=true
~~~

Đặc biệt, `SERVER_EFFECT.set(true)` được thực hiện **trước** `CANCEL_ENTERED.countDown()`. Chỉ khi client chờ latch thấy true, nó mới gọi `cancel(true)`. Nhờ vậy, câu “server đã thực hiện tác động trước cancel” có cơ sở từ thứ tự đồng bộ, không dựa trên xác suất scheduling.

### Vì sao join() sau cancel có thể ném CompletionException?

Với một `CompletableFuture` thông thường, cancel được mô tả như một exceptional completion với `CancellationException`. Nhưng default Java HTTP client trả Futures có các dependent stages bên trong. Trong kiểm thử JDK 24, `slow.cancel(true)` trả true trong khi `slow.join()` ném **`CompletionException` bọc `CancellationException`**. Ở một phép thử trực tiếp, `slow.isCancelled()` còn trả false dù `cancel(true)` trả true, vì Future biểu diễn thất bại bằng wrapper.

Vì vậy **không viết test chỉ bắt trực tiếp CancellationException rồi giả định mọi implementation giống nhau**:

~~~java
// Fragment Java 17+, slow là cancelable HttpClient future.
boolean accepted = slow.cancel(true);
boolean cancellationObserved;
try {
    slow.join();
    cancellationObserved = false;
} catch (CancellationException e) {
    cancellationObserved = true;
} catch (CompletionException e) {
    cancellationObserved = hasCancellation(e); // Tìm trong cause chain.
}
~~~

Helper `hasCancellation(Throwable)` trong chương trình đầy đủ duyệt các `Throwable.getCause()` và tìm CancellationException. Chú ý hai điều:

1. `cancel(true)` trả true là outcome của lời gọi Future, **không** nói TCP packet chưa đi ra hoặc side effect của server đã được undo.
2. `isDone()/isCompletedExceptionally()/isCancelled()` là **trạng thái Future**, không phải chứng cứ server rollback. Đừng dùng `isCancelled()` đơn lẻ để chứng minh business transaction đã dừng.

### Hủy POST/PUT/PATCH trong production

Giả sử client gửi yêu cầu thanh toán và mất response hoặc cancel khi server đã nhận. Retry không có **idempotency key** có thể tạo hai giao dịch. Cần API trạng thái giao dịch, correlation ID, deduplication, transaction rollback policy và logging/audit. Không retry vô hạn chỉ vì Future hoàn tất exceptionally.

## 8. Chương trình Java 17+ hoàn chỉnh: HttpClientLab.java

File này dùng server loopback và các latches nhằm tạo thứ tự kiểm thử ổn định. Mỗi test đều thực hiện HTTP qua socket thật; không chỉ giả lập object `HttpResponse`. Đây là chương trình **tự chạy**, không cần thêm class từ project.

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class HttpClientLab {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final CountDownLatch BOTH_ASYNC =
            new CountDownLatch(2);
    private static final CountDownLatch RELEASE_ASYNC =
            new CountDownLatch(1);
    private static final CountDownLatch CANCEL_ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch RELEASE_CANCEL =
            new CountDownLatch(1);
    private static final CountDownLatch CANCEL_FINISHED =
            new CountDownLatch(1);
    private static final AtomicBoolean SERVER_EFFECT =
            new AtomicBoolean(false);

    private static void reply(
            HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(UTF8);
        try (exchange) {
            try (InputStream in = exchange.getRequestBody()) {
                in.transferTo(OutputStream.nullOutputStream());
            }
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static void gated(
            HttpExchange exchange, String answer)
            throws IOException {
        BOTH_ASYNC.countDown();
        try {
            if (!RELEASE_ASYNC.await(5, TimeUnit.SECONDS)) {
                reply(exchange, 503, "GATE_TIMEOUT");
            } else {
                reply(exchange, 200, answer);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            reply(exchange, 503, "INTERRUPTED");
        }
    }

    private static void cancelHandler(HttpExchange exchange) {
        // Server side effect da xay ra TRUOC luc client cancel.
        SERVER_EFFECT.set(true);
        CANCEL_ENTERED.countDown();

        try {
            if (RELEASE_CANCEL.await(5, TimeUnit.SECONDS)) {
                reply(exchange, 200, "TOO_LATE");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (IOException e) {
            // Client co the dong connection HTTP/1.1 khi cancel.
        } finally {
            exchange.close();
            CANCEL_FINISHED.countDown();
        }
    }

    private static void checkCookie(HttpExchange exchange)
            throws IOException {
        String cookie = exchange.getRequestHeaders()
                .getFirst("Cookie");
        boolean present = cookie != null
                && cookie.contains("labToken=abc123");
        reply(exchange, 200, Boolean.toString(present));
    }

    private static HttpRequest get(String base, String path) {
        return HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(10))
                .GET().build();
    }

    private static HttpResponse<String> send(
            HttpClient client, HttpRequest request)
            throws IOException, InterruptedException {
        return client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));
    }

    private static boolean hasCancellation(Throwable failure) {
        for (Throwable e = failure; e != null; e = e.getCause()) {
            if (e instanceof CancellationException) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 32);
        ExecutorService workers =
                Executors.newFixedThreadPool(8);

        server.createContext("/ping",
                exchange -> reply(exchange, 200, "PONG"));
        server.createContext("/async/one",
                exchange -> gated(exchange, "ONE"));
        server.createContext("/async/two",
                exchange -> gated(exchange, "TWO"));
        server.createContext("/cookie/set", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "labToken=abc123; Path=/cookie; HttpOnly");
            reply(exchange, 200, "COOKIE_SET");
        });
        server.createContext("/cookie/check",
                HttpClientLab::checkCookie);
        server.createContext("/outside",
                HttpClientLab::checkCookie);
        server.createContext("/cancel",
                HttpClientLab::cancelHandler);
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            CookieManager jar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .cookieHandler(jar)
                    .build();

            // 1. Blocking send.
            HttpResponse<String> sync =
                    send(client, get(base, "/ping"));
            System.out.println("syncStatus=" + sync.statusCode());
            System.out.println("syncBody=" + sync.body());

            // 2. Hai request bat dong bo, gate tai server.
            CompletableFuture<HttpResponse<String>> one =
                    client.sendAsync(
                            get(base, "/async/one"),
                            HttpResponse.BodyHandlers.ofString(UTF8));
            CompletableFuture<HttpResponse<String>> two =
                    client.sendAsync(
                            get(base, "/async/two"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            boolean bothReached = BOTH_ASYNC.await(
                    5, TimeUnit.SECONDS);
            RELEASE_ASYNC.countDown();
            if (!bothReached) {
                throw new IllegalStateException(
                        "Async handlers did not overlap");
            }
            CompletableFuture.allOf(one, two)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("asyncBothReachedServer=" + bothReached);
            System.out.println("asyncOne=" + one.join().body());
            System.out.println("asyncTwo=" + two.join().body());

            // 3. CookieManager nhan/luu/gui dung Path.
            HttpResponse<String> cookieSet =
                    send(client, get(base, "/cookie/set"));
            boolean stored = jar.getCookieStore().getCookies()
                    .stream().map(HttpCookie::getName)
                    .anyMatch("labToken"::equals);
            boolean matchingPath = Boolean.parseBoolean(
                    send(client, get(base, "/cookie/check")).body());
            boolean outsidePath = Boolean.parseBoolean(
                    send(client, get(base, "/outside")).body());

            HttpClient noCookies = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            boolean withoutHandler = Boolean.parseBoolean(
                    send(noCookies, get(base, "/cookie/check")).body());

            CookieManager rejectingJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_NONE);
            HttpClient rejectingClient = HttpClient.newBuilder()
                    .cookieHandler(rejectingJar)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            send(rejectingClient, get(base, "/cookie/set"));
            boolean rejected = rejectingJar.getCookieStore()
                    .getCookies().isEmpty()
                    && !Boolean.parseBoolean(
                            send(rejectingClient,
                                    get(base, "/cookie/check")).body());

            System.out.println("cookieSetStatus="
                    + cookieSet.statusCode());
            System.out.println("cookieStored=" + stored);
            System.out.println("cookieOnMatchingPath=" + matchingPath);
            System.out.println("cookieOutsidePathAbsent="
                    + !outsidePath);
            System.out.println("cookieWithoutHandlerAbsent="
                    + !withoutHandler);
            System.out.println("cookieRejectedByPolicy="
                    + rejected);

            // 4. Cancel khi server da vao handler.
            CompletableFuture<HttpResponse<String>> slow =
                    client.sendAsync(
                            get(base, "/cancel"),
                            HttpResponse.BodyHandlers.ofString(UTF8));
            boolean entered = CANCEL_ENTERED.await(
                    5, TimeUnit.SECONDS);
            if (!entered) {
                throw new IllegalStateException(
                        "Cancel endpoint not reached");
            }
            boolean sideEffect = SERVER_EFFECT.get();
            boolean accepted = slow.cancel(true);
            boolean cancelledInCause;

            try {
                slow.join();
                cancelledInCause = false;
            } catch (CancellationException e) {
                cancelledInCause = true;
            } catch (CompletionException e) {
                cancelledInCause = hasCancellation(e);
            }

            RELEASE_CANCEL.countDown();
            boolean handlerFinished = CANCEL_FINISHED.await(
                    5, TimeUnit.SECONDS);

            System.out.println("cancelHandlerReached=" + entered);
            System.out.println("serverEffectBeforeCancel="
                    + sideEffect);
            System.out.println("cancelAccepted=" + accepted);
            System.out.println("cancelFutureDone=" + slow.isDone());
            System.out.println("cancelFutureExceptional="
                    + slow.isCompletedExceptionally());
            System.out.println("cancelOutcomeHasCancellation="
                    + cancelledInCause);
            System.out.println("cancelHandlerFinished="
                    + handlerFinished);
        } finally {
            RELEASE_ASYNC.countDown();
            RELEASE_CANCEL.countDown();
            server.stop(0);
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

### Cách biên dịch/chạy Java 17+

~~~bash
javac --release 17 HttpClientLab.java
java HttpClientLab
~~~

Trong ứng dụng dùng `module-info.java`, cần `requires java.net.http; requires jdk.httpserver;`. Chương trình classpath thông thường trên JDK đầy đủ sẽ resolve được hai module. Tên file phải khớp `public class HttpClientLab`.

### Stdout đã kiểm chứng ba lần trên JDK 24

~~~text
syncStatus=200
syncBody=PONG
asyncBothReachedServer=true
asyncOne=ONE
asyncTwo=TWO
cookieSetStatus=200
cookieStored=true
cookieOnMatchingPath=true
cookieOutsidePathAbsent=true
cookieWithoutHandlerAbsent=true
cookieRejectedByPolicy=true
cancelHandlerReached=true
serverEffectBeforeCancel=true
cancelAccepted=true
cancelFutureDone=true
cancelFutureExceptional=true
cancelOutcomeHasCancellation=true
cancelHandlerFinished=true
~~~

Tất cả 18 dòng trên được quan sát ở **ba lần chạy liên tiếp** trên loopback với code biên dịch `javac --release 17`. Đây là kết quả **kiểm thử môi trường cụ thể**, không phải bảo đảm cancellation scheduling/connection cleanup trên mọi JDK/provider/OS. Một môi trường hạn chế socket hoặc tải hệ thống lớn có thể gây timeout, IOException hoặc điều kiện race khác.

### Vì sao code không in “Future.isCancelled() chắc chắn true”?

Trong một lần kiểm chứng riêng, HttpClient Future đã cho `cancel(true)==true`, `isDone()==true`, `isCompletedExceptionally()==true`, nhưng `isCancelled()==false` và `join()` ném `CompletionException` có cause chain chứa `CancellationException`. Đây là lý do ta kiểm tra **cancellation outcome** thay vì ràng buộc duy nhất một dạng exception/boolean cho tất cả HTTP implementations.

### Kiểm tra nội dung đầu ra theo từng trường hợp

- Hai dòng `syncStatus=200` và `syncBody=PONG`: chứng minh blocking HTTP request hoàn tất hợp lệ.
- `asyncBothReachedServer=true`, `asyncOne=ONE`, `asyncTwo=TWO`: chứng minh hai handlers vào server trước khi gate mở và cả hai response đã nhận.
- Sáu dòng cookie: chứng minh server cấp cookie, jar nhận được, gửi đúng path, không gửi ngoài path, client không jar không chia sẻ và policy ACCEPT_NONE từ chối.
- Bảy dòng cancel: server đã thực hiện hiệu ứng mô phỏng trước khi cancel; client đánh dấu Future exceptional/cancellation, server handler kết thúc khi gate được mở. Không có dòng nào khẳng định server side effect được rollback.

## 9. Quy tắc dùng CompletableFuture đúng khi test async

`CompletableFuture` có nhiều cách đợi/compose:

| API | Mục đích | Lưu ý |
| --- | --- | --- |
| `future.get()` | Chờ, trả kết quả hoặc ném checked exceptions | Có thể block vô thời hạn nếu không có deadline |
| `future.get(timeout, unit)` | Giới hạn thời gian thread đợi | Timeout **không tự cancel** HTTP exchange |
| `future.join()` | Chờ, dùng unchecked CompletionException | Có thể ném trực tiếp CancellationException |
| `thenApply()` | Biến đổi kết quả khi thành công | Callback có thể chạy trên thread hoàn tất stage |
| `thenCompose()` | Nối một stage bất đồng bộ khác | Phù hợp pipeline dependent HTTP/request processing |
| `whenComplete()` | Quan sát success/failure | Không làm lỗi tự biến mất |
| `exceptionally()` | Phục hồi/fallback khi lỗi | Không được tự nuốt lỗi giao dịch quan trọng |
| `allOf(a,b)` | Đợi nhiều futures kết thúc | Không gom result, không tự hủy các futures khác |
| `orTimeout(d,unit)` | Làm Future complete exceptionally khi quá hạn | Không đồng nghĩa hủy network |
| `cancel(true)` | Thử cancel HTTP exchange khi là cancelable HttpClient future | Best-effort; không rollback server |

Ví dụ xử lý callback an toàn:

~~~java
// Fragment: future đã là CompletableFuture<HttpResponse<String>>.
CompletableFuture<String> bodyFuture =
        future.thenApply(HttpResponse::body);

bodyFuture.whenComplete((body, failure) -> {
    if (failure != null) {
        reportFailure(failure); // Helper app định nghĩa.
    } else {
        recordBody(body);       // Helper app định nghĩa.
    }
});
~~~

Đừng làm tác vụ DB blocking rất lâu bên trong callback mà không cân nhắc executor/thread-pool; `thenApply/whenComplete` có thể chạy trên completion thread hoặc caller thread. Nếu cần offload, dùng `thenApplyAsync(..., boundedExecutor)` và **quản lý lifecycle executor riêng**.

## 10. Timeout khác cancellation, và cả hai khác server rollback

Phân biệt rõ:

| Cơ chế | Ranh giới | Điều không bảo đảm |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | Thiết lập kết nối mới | Không phải tổng request deadline |
| `HttpRequest.Builder.timeout(Duration)` | HTTP exchange theo hợp đồng request | Không chứng minh server chưa xử lý khi timeout |
| `future.get(2,SECONDS)` | Thread gọi chờ tối đa 2s | HTTP vẫn có thể đang chạy |
| `future.orTimeout(2,SECONDS)` | Future exceptional nếu chưa xong | Network chưa chắc đã hủy |
| `future.cancel(true)` | Nỗ lực cancel exchange | Server có thể đã nhận và commit |
| `Thread.interrupt()` lúc đang `send()` | Thử ngắt blocking call, default client cố cancel | Không bảo đảm abort/rollback ở peer |
| `InputStream.close()` | Đóng một streaming response body | Không undo yêu cầu đã gửi |

~~~java
// Fragment Java 17+: chủ động quyết định cancel khi timeout đợi.
try {
    HttpResponse<String> response =
            future.get(2, TimeUnit.SECONDS);
    handleResponse(response);
} catch (TimeoutException e) {
    future.cancel(true);
    recordTimeout(e);
}
~~~

`handleResponse/recordTimeout` là helper ứng dụng. `get(timeout)` ném TimeoutException chỉ nói **luồng đợi** chưa có kết quả đúng hạn, không nói request đã thất bại tại server. `orTimeout` là timeout của completion stage, cũng không thay server transaction. Nếu body được nhận dưới dạng `InputStream`, còn phải có deadline/cleanup **khi đọc body**, không chỉ khi Future response object xuất hiện.

Nếu handler gửi request POST tạo đơn rồi Future bị hủy, server vẫn có thể đã tạo đơn. Cần **idempotency key**, endpoint hỏi trạng thái, correlation ID và policy retry phù hợp.

## 11. Tại sao hủy Future trong một chuỗi stage có thể gây hiểu nhầm?

Một request có thể tạo nhiều công việc:

~~~text
HttpClient.sendAsync(req)
     |
     +--> responseFuture
                 |
                 +--> thenApply(parseJson) --> parseFuture
                 |
                 +--> thenCompose(saveDb)  --> processingFuture
~~~

Hủy `processingFuture` không có nghĩa đã cancel trực tiếp HTTP exchange hoặc rollback DB operation. Hủy responseFuture khi data đã gửi không xóa side effect server. Khi service dừng cần theo dõi **các futures gốc, futures phụ thuộc và body streams**; các thao tác hủy, retry và cleanup phải dựa trên ownership.

Một anti-pattern:

~~~java
// Không dùng mẫu này cho thao tác thanh toán có side effect.
CompletableFuture<HttpResponse<String>> pay =
        client.sendAsync(paymentRequest,
                HttpResponse.BodyHandlers.ofString());

pay.cancel(true);
retryWithoutIdempotencyKey(); // Nguy cơ thanh toán/tạo giao dịch trùng.
~~~

Đây là fragment minh họa lỗi thiết kế, `retryWithoutIdempotencyKey()` là helper giả định. Với POST/PUT/PATCH, phải nắm semantics của API và trạng thái giao dịch trước khi retry.

## 12. Kiểm thử âm tính và trường hợp biên cần bổ sung

Chương trình chính chứng minh bốn nhóm yêu cầu. Khi xây bộ kiểm thử thực tế, mở rộng các ca sau (các ca trong bảng là **khuyến nghị test**, không phải khẳng định đã chạy trong stdout):

| Ca | Cách thực hiện | Kỳ vọng hợp đồng |
| --- | --- | --- |
| HTTP 404 | GET path không tồn tại | Nhận HttpResponse status 404 khi transport thành công |
| Method 405 | Handler kiểm tra GET/POST, trả 405 | `send` vẫn có HttpResponse status=405 |
| Async 503 | Một handler trả 503 | Future có thể complete normally với response 503 |
| Đứt kết nối | Server đóng socket đột ngột | Future exceptional/IOException |
| Connect timeout | Trỏ IP/port phù hợp để mô phỏng timeout | Phân loại `HttpConnectTimeoutException` khi occurrence thật |
| Request timeout | Handler giữ response đến hết request deadline | Timeout theo API, không mặc định server rollback |
| Gate không được mở | Giữ server latch tới timeout 5s | Handler có response lỗi hoặc client timeout |
| Cookie expired | Set-Cookie với Max-Age=0 | Cookie không tiếp tục gửi theo policy |
| Cookie không đúng Domain/Path | Thay cookie attributes | Cookie được gửi theo scope, không phải mọi URI |
| Cookie Secure trên HTTP | Đặt Secure nhưng gửi request http:// | Cookie không được phát trên plaintext theo policy |
| Cookie jar dùng chung | Hai HttpClients trỏ cùng CookieManager | Có khả năng chia sẻ cookie |
| Cookie jar riêng | Mỗi client có CookieManager riêng | Không rò state giữa clients |
| Cancel trước khi server bắt đầu | Cancel ngay sau sendAsync | Race hợp lệ; server có thể đã/ chưa nhận |
| Cancel sau side effect | Gate đúng thứ tự như lab | Side effect đã xảy ra vẫn tồn tại |
| Cancel sau Future thành công | Gọi cancel trên Future đã complete | Không hủy kết quả đã hoàn tất |
| Cancel với BodyHandler streaming | Đọc một phần InputStream rồi close | Phải cleanup body, không tự coi response complete |
| Thread pool 1 worker | Dùng 1 thread cho hai gated handlers | Có nguy cơ starvation/deadlock ở test |
| Concurrent stress | Nhiều requests nhưng queue bounded | Quản lý deadline, tài nguyên và lỗi |

**Không viết test khẳng định server chắc chắn phải ném IOException sau cancel.** Việc đóng connection và thời điểm lỗi ở server phụ thuộc transport/OS/JDK; điều có thể chứng minh là server đã vào handler trước hủy, và client Future có outcome hủy/exceptional phù hợp.

## 13. Chuyển từ stdout sang assertion

Chương trình dùng các boolean dễ đọc để giảng dạy. Khi đưa vào CI, nên đưa điều kiện vào assertions để test **fail thật** khi expected behavior không đạt.

~~~java
// Fragment Java 17+: thêm vào cùng class nếu muốn.
private static void require(boolean condition, String label) {
    if (!condition) {
        throw new AssertionError(label);
    }
}

// Sử dụng sau khi đã có những biến từ chương trình:
require(sync.statusCode() == 200, "Sync status");
require("PONG".equals(sync.body()), "Sync body");
require(bothReached, "Async handlers did not overlap");
require(stored && matchingPath && !outsidePath,
        "Cookie path behavior");
require(!withoutHandler && rejected,
        "Cookie isolation and reject policy");
require(entered && sideEffect,
        "Server acted before cancellation");
require(accepted && cancelledInCause,
        "Cancellation outcome");
require(handlerFinished, "Server-side cleanup");
~~~

Đây là fragment bổ sung (không phải class mới độc lập); khi sử dụng cần đặt đúng vị trí biến. Với multi-test JUnit 5, tránh dùng static mutable CountDownLatch chung giữa các test: mỗi test/setup tạo server, latches và CookieManager riêng. Sử dụng port 0 và finally cleanup để tránh rò threads/connections.

### Tại sao server response body được drain?

Helper `reply()` đọc request body trước khi trả response, rồi đóng streams bằng `try-with-resources`. Trong lab GET body rỗng và mọi request được kiểm soát; với public server không nên cứ `transferTo(nullOutputStream())` vô hạn trên request không đáng tin. Cần giới hạn bytes, read deadline, slow-client protection và 413 nếu quá lớn. Server demo chỉ dùng loopback, không phải HTTP service public.

### Vì sao phải mở gates trong finally?

Nếu một test ném exception trước khi nhả latch, handler chờ có thể giữ worker thread tới timeout. Chương trình chính luôn gọi:

~~~java
RELEASE_ASYNC.countDown();
RELEASE_CANCEL.countDown();
server.stop(0);
workers.shutdownNow();
workers.awaitTermination(5, TimeUnit.SECONDS);
~~~

Đây là fragment của finally, không phải khối chạy độc lập. Nó giới hạn tài nguyên của **server test**. `shutdownNow()` chỉ là nỗ lực interrupt worker threads, không được hiểu là mọi công việc server đã hoàn tất transactional.

## 14. Các lỗi phổ biến khi chạy thí nghiệm

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| GUI/event loop đứng | Gọi send() trên thread tương tác | Đưa I/O sang worker hoặc dùng sendAsync |
| Hai sendAsync không đồng thời | Khởi tạo Future 2 sau khi join Future 1 | Tạo cả hai trước khi chờ |
| Gate timeout | Server pool quá nhỏ, request lỗi/mạng chậm | Đủ worker threads, timeout rõ và finally release |
| `CompletableFuture.join()` ném wrapper | Underlying request lỗi hoặc cancel | Phân loại CompletionException/cause chain |
| Response 503 bị coi success | Chỉ kiểm tra Future thành công | Kiểm tra statusCode và business schema |
| Cookie không xuất hiện | Không gắn CookieHandler hoặc Path/Domain/Secure không match | Cấu hình jar và kiểm tra Set-Cookie/header |
| CookieStore có cookie nhưng server không thấy | Request không thuộc scope cookie | Kiểm tra Path/Domain/Secure và expiry |
| Cookie rò giữa tests | Chia sẻ một CookieManager | Tạo jar mới per test/identity |
| HttpOnly hiểu sai | Tưởng Java client không gửi cookie HttpOnly | HttpOnly chủ yếu là hạn chế browser JS |
| SameSite bị hiểu sai | Xem CookieManager như browser | Kiểm thử browser và CSRF riêng |
| Cancel true nhưng server vẫn xử lý | Best-effort, request đã tới server | Idempotency/status API và nghiệp vụ riêng |
| `isCancelled()==false` sau cancel | HTTP Future có exceptional completion qua wrapper | Kiểm tra isCompletedExceptionally và exception cause |
| Timeout trên get nhưng request còn chạy | get(timeout) không cancel HTTP | Cancel chủ động và cleanup body/resources |
| Close stream quá sớm | BodyHandler.ofInputStream chưa EOF | Đọc hết hoặc close theo policy, báo partial |
| Java 17 báo HttpClient không AutoCloseable | Dùng API Java 21 | Không try-with-resources HttpClient trên Java 17 |
| JVM còn chạy sau test | Executor/handler latch không được giải phóng | finally release, stop server, shutdown executor |
| GET 404 làm app ném IllegalStateException | Application policy chủ động kiểm tra status | Phân biệt HTTP status và transport exception |
| Hủy POST rồi retry trùng | Server commit trước cancel | Idempotency key, correlation ID |
| Chạy test Internet không ổn định | DNS/rate limit/proxy thay đổi | Loopback server với fixtures deterministic |

## 15. Bảo mật và độ tin cậy khi áp dụng thực tế

Đây là ví dụ **Java client experiment**, không phải hệ thống cookie authentication production. Khi áp dụng vào hệ thống thật:

- **Luôn dùng HTTPS** cho token/session cookies và giữ certificate/hostname verification. Không dùng TrustManager accept-all để “sửa” lỗi TLS.
- **Cookie scope/ownership:** mỗi user/test có jar riêng khi cần isolation; kiểm soát Path/Domain/Expires/Max-Age/Secure/HttpOnly, nhưng vẫn xác thực quyền trên server.
- **Browser vs Java client:** CookieManager không mặc nhiên thực thi đầy đủ SameSite, CORS/CSRF và privacy policy của browser.
- **Không log session tokens** hoặc raw Authorization/Cookie headers. Correlation ID và route templates hữu ích hơn cho logging/metrics.
- **Kiểm soát số request pending:** giới hạn concurrency, thread pool, queue, deadlines, byte size; xử lý errors và cancel theo ownership.
- **Thống nhất retry policy:** phân biệt idempotent GET và các request có side effect; không suy ra rollback từ Future cancellation.
- **Body cleanup:** với `ofInputStream/ofPublisher/ofLines`, xử lý hết hoặc close/cancel đúng cách. Future hoàn tất không tự tiêu thụ body cho các handler streaming.
- **Lifecycle:** dùng HttpClient lâu dài khi cần, quản lý CookieManager/store riêng, shutdown các executors do ứng dụng sở hữu và giải quyết outstanding Futures.
- **Quan sát đúng:** log HTTP status, latency, cancellation attempt, outcome/cause, server requestId; đừng báo “server chưa làm” chỉ vì client không nhận response.
- **Test thực tế:** bổ sung ca timeout, redirect, proxy, TLS, expired cookies, race cancellation và lost response trong integration tests.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt chính giữa send và sendAsync?  
**Đáp án:** send blocking thread gọi và trả HttpResponse; sendAsync trả CompletableFuture ngay, có thể compose nhiều requests.

**Câu 2.** Hai Future được tạo trước rồi allOf chứng minh HTTP handlers đã chạy đồng thời chưa?  
**Đáp án:** Chưa tự chứng minh overlap tại server; lab dùng CountDownLatch ở cả hai handlers để xác nhận.

**Câu 3.** Vì sao cần server pool nhiều threads trong test gate?  
**Đáp án:** Nếu chỉ một handler thread, handler đầu chờ gate và ngăn handler thứ hai bắt đầu, gây starvation/test timeout.

**Câu 4.** `CompletableFuture.allOf(a,b)` có trả hai HttpResponse không?  
**Đáp án:** Không, trả CompletableFuture<Void>, lấy a.join()/b.join() sau khi đã hoàn thành.

**Câu 5.** HTTP 404 có bắt buộc `send()` ném IOException không?  
**Đáp án:** Không. HTTP status và network error là hai cấp khác nhau; kiểm tra statusCode.

**Câu 6.** Làm sao gắn cookie management cho Java HttpClient?  
**Đáp án:** Dùng HttpClient.Builder.cookieHandler(CookieManager) trước khi build.

**Câu 7.** CookiePolicy.ACCEPT_NONE có tác dụng gì?  
**Đáp án:** Từ chối cookies do server gửi; trong lab store vẫn trống và request sau không gửi labToken.

**Câu 8.** Có Set-Cookie rồi đã chắc server nhận lại cookie chưa?  
**Đáp án:** Chưa. Phải gửi request tiếp theo và kiểm tra server nhận Cookie header theo path/policy.

**Câu 9.** Path=/cookie có bảo vệ cookie khỏi mọi script/endpoint cùng origin không?  
**Đáp án:** Không. Path là scope gửi HTTP cookie, không phải authorization boundary.

**Câu 10.** Hai HttpClients dùng cùng một CookieManager có cô lập cookie không?  
**Đáp án:** Không; họ cố ý dùng cùng mutable jar, có thể chia sẻ cookie.

**Câu 11.** HttpOnly cấm Java CookieManager gửi cookie không?  
**Đáp án:** Không. HttpOnly chủ yếu ngăn browser JavaScript truy cập cookie, không thay TLS hoặc authorization.

**Câu 12.** Java CookieManager có đảm bảo hành vi SameSite của browser không?  
**Đáp án:** Không nên giả định; phải kiểm thử browser và thiết kế CSRF policy riêng.

**Câu 13.** Cancel true có chứng minh request chưa tới server không?  
**Đáp án:** Không. Cancel là attempt, request có thể đã được gửi hoặc server đã hoàn thành side effect.

**Câu 14.** Vì sao lab đặt SERVER_EFFECT trước CANCEL_ENTERED.countDown?  
**Đáp án:** Để client chắc chắn server đã thực hiện tác động mô phỏng trước khi gọi cancel, nhờ quan hệ đồng bộ latch.

**Câu 15.** Sau cancel, join() có thể ném lỗi nào?  
**Đáp án:** CancellationException trực tiếp hoặc CompletionException có cause CancellationException (đã quan sát trên JDK 24).

**Câu 16.** `slow.isCancelled()==false` có tự chứng minh HTTP chưa bị cancel không?  
**Đáp án:** Không. Một HTTP Future có thể exceptional qua wrapper; xem kết quả/cause và nhớ cancellation không rollback server.

**Câu 17.** `future.get(2,SECONDS)` timeout có tự hủy HTTP không?  
**Đáp án:** Không. Nó chỉ giới hạn thời gian thread đợi.

**Câu 18.** BodyHandlers.ofInputStream() Future complete có nghĩa đã đọc hết body chưa?  
**Đáp án:** Không. Phải đọc stream tới EOF hoặc đóng/cancel theo policy.

**Câu 19.** Java 17 HttpClient có AutoCloseable không?  
**Đáp án:** Không; HttpClient có close/shutdown từ Java 21. Java 17 vẫn phải cleanup body/executors.

**Câu 20.** Vì sao cancel POST thanh toán rồi retry không có key dễ lỗi?  
**Đáp án:** Server có thể đã commit giao dịch; retry có thể tạo giao dịch trùng, cần idempotency/status check.

**Câu 21.** Vì sao phải countDown gates trong finally?  
**Đáp án:** Giải phóng handler đang chờ nếu test thất bại, tránh giữ worker threads cho tới timeout.

**Câu 22.** Muốn kiểm thử async timeout mà không phụ thuộc scheduling cố định thì làm gì?  
**Đáp án:** Dùng gate/latch trên server, deadline có giới hạn, phân loại outcome; không dùng Thread.sleep làm bằng chứng duy nhất.

## 17. Tài liệu tham khảo chính thức

- Oracle Java SE 17 — `HttpClient`, send/sendAsync/cancel notes: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpClient.Builder`, cookieHandler/connectTimeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Oracle Java SE 17 — `HttpRequest.Builder`, timeout/URI/method: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Oracle Java SE 17 — `HttpResponse`, BodyHandlers, status/body: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `CompletableFuture`, allOf/get/join/cancel/orTimeout: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 17 — `CookieManager`, cookie policy/store: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html
- Oracle Java SE 17 — `CookiePolicy` ACCEPT_NONE/ACCEPT_ORIGINAL_SERVER: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html
- Oracle Java SE 17 — `CookieStore`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html
- Oracle Java SE 17 — `HttpCookie` attributes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html
- Oracle Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Oracle Java SE 17 — `HttpServer` fixture: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Oracle Java SE 17 — `HttpExchange` request/response streams/headers: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
