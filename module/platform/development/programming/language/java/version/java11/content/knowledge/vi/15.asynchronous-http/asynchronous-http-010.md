# Giới hạn số yêu cầu đang xử lý đồng thời với HttpClient bất đồng bộ trong Java 11

**Chủ đề cha:** HTTP bất đồng bộ  
**Bài học:** Giới hạn số yêu cầu đang xử lý đồng thời  
**Phạm vi:** `java.net.http.HttpClient.sendAsync`, `CompletableFuture`, luồng điều phối, `Semaphore`, hàng đợi có sức chứa giới hạn và kiểm soát số HTTP request đang in-flight. Tất cả API chính trong bài có trên Java 11 và tiếp tục phù hợp với Java hiện đại.

`HttpClient.sendAsync` giúp gửi HTTP request mà không phải chặn luồng gọi để chờ phản hồi. Nhưng nếu liên tục gọi `sendAsync` cho hàng chục nghìn URL, ứng dụng vẫn có thể tạo ra hàng chục nghìn request, future, buffer, tác vụ callback và áp lực tới server downstream. **“Bất đồng bộ” không đồng nghĩa “không tốn tài nguyên”**. Cần giới hạn số yêu cầu **đã gửi nhưng chưa hoàn thành theo định nghĩa nghiệp vụ**, đồng thời quyết định làm gì với yêu cầu đến khi đã hết chỗ: **chờ có kiểm soát, xếp hàng với giới hạn, hoặc từ chối sớm**.

Java 11 không cung cấp một tham số đơn giản tên `maxInFlightRequests` trên `HttpClient.Builder`. Đặt số thread cho một `Executor` hoặc tạo một `Semaphore` mà không dùng nó ở đường gửi thực tế **không tự động giới hạn số request**. Giới hạn phải nằm trong logic điều phối **trước khi gọi `sendAsync`**, và mỗi slot/permit chỉ được trả lại ở mốc hoàn tất đã chọn.

## 1. Học xong cần làm được gì?

1. Phân biệt **concurrency (số request in-flight)**, **throughput (request/giây)**, **rate limit**, **số luồng** và **số TCP connection**.
2. Lập bất biến: tại mọi thời điểm, số request đã được chấp nhận nhưng chưa kết thúc không lớn hơn `MAX_IN_FLIGHT`.
3. Dùng một luồng điều phối cùng hàng đợi completion có giới hạn để luôn giữ tối đa `N` request HTTP bất đồng bộ đang chờ xử lý kết quả.
4. Dùng `Semaphore.tryAcquire()` cho chính sách **fail fast** khi vượt mức, hoặc dùng một hàng đợi chờ được giới hạn khi muốn backpressure.
5. Hoàn trả permit trên **cả thành công, HTTP lỗi, timeout, I/O exception và nhánh thất bại đồng bộ khi tạo/gửi**, nhưng không hoàn trả hai lần.
6. Hiểu vì sao `BodyHandlers.ofString`, `ofFile` và `ofInputStream` có **thời điểm “future hoàn tất” khác nhau**; với streaming phải giữ slot đến khi body đã được tiêu thụ/đóng theo hợp đồng.
7. Kiểm thử bằng server local có latch để xác minh peak concurrency, không dựa vào `Thread.sleep()` để đoán lịch thực thi.
8. Chọn limit và đo lường queue, số request đang hoạt động, thời gian chờ, timeout, HTTP 429/503 và lỗi downstream để điều chỉnh chính sách.

## 2. Định nghĩa chính xác số request “đang xử lý”

Trước khi viết limiter, quyết định **vòng đời của một request**:

```text
[Được đề xuất / nhận từ upstream]
          |
          v
[Đợi slot hoặc bị từ chối]  <-- chưa gọi sendAsync
          |
          v
[Giữ slot / permit]
          |
          v
[HttpClient.sendAsync được gọi]
          |
          v
[HTTP request / response diễn ra]
          |
          v
[Response body được xử lý xong HOẶC thất bại]
          |
          v
[Trả slot, ghi nhận kết quả, cho yêu cầu tiếp theo vào]
```

Trong một batch dùng `BodyHandlers.ofString(StandardCharsets.UTF_8)`, future hoàn tất thành công **sau khi body đã được nhận và tạo thành `String`**, nên có thể dùng completion làm mốc trả slot. Với `BodyHandlers.discarding()`, subscriber đọc và loại bỏ body trước khi hoàn tất. Với `BodyHandlers.ofFile(path)`, response hoàn tất khi body đã ghi xong vào file.

**Ngoại lệ rất quan trọng:** `BodyHandlers.ofInputStream()` có thể trả `HttpResponse<InputStream>` ngay sau khi headers đã đến, **trước khi body nhận đủ**. Nếu chỉ gắn `.whenComplete((response,error) -> semaphore.release())` vào future `sendAsync(...ofInputStream())`, permit có thể được trả quá sớm; số phiên đang đọc body thực tế sẽ vượt giới hạn mong muốn. `ofLines()` và `ofPublisher()` cũng có bản chất streaming. Với chúng, hãy giữ slot đến khi stream/Flow subscriber kết thúc/đóng và được xử lý đúng chính sách. Ví dụ cụ thể ở mục 7.

### Các đại lượng không được nhầm lẫn

| Đại lượng | Định nghĩa | Ví dụ |
|---|---|---|
| `maxInFlight` | Trần số request đã chấp nhận, chưa được đánh dấu hoàn tất | Tối đa 3 request |
| `requestsPerSecond` | Số request bắt đầu hoặc được xử lý trong mỗi giây | 60 req/s |
| `pendingQueueSize` | Số yêu cầu đang chờ slot, **chưa gửi** | Tối đa 100 |
| `executorThreads` | Số worker thread xử lý callback/công việc | 4 thread |
| `tcpConnections` | Số kết nối TCP vật lý | Không nhất thiết bằng số request |
| `http2Streams` | Số stream HTTP/2 đang được multiplex qua kết nối | Có thể nhiều request trên một connection |
| `connectionTimeout` | Giới hạn thời gian thiết lập kết nối | 5 giây |
| `requestTimeout` | Giới hạn thời gian request theo `HttpRequest.Builder.timeout` | 10 giây |

Một `HttpClient` có thể dùng HTTP/1.1 hoặc HTTP/2 và tái sử dụng kết nối. Một giới hạn theo **request** không tự trở thành giới hạn theo **socket**, và giới hạn 3 request không tự đảm bảo 3 request/giây. Nếu request rất nhanh, 3 slot có thể phục vụ nhiều lượt mỗi giây; nếu downstream chậm, 3 slot có thể chỉ xử lý được ít request.

**Giới hạn local hay toàn hệ thống?** Một `Semaphore(3)` trong một instance Java chỉ giới hạn những request đi qua **đúng instance và đúng semaphore đó**. Nếu deploy 10 instance, tổng hoạt động có thể tới khoảng 30 request. Nếu cần ngân sách concurrency toàn cụm hoặc theo từng tài khoản/host, phải có chiến lược phối hợp tương ứng, không giả định local limiter tự có hiệu lực toàn hệ thống.

## 3. Vì sao các cách viết tưởng đơn giản lại không giới hạn concurrency?

### 3.1 Tạo hết future rồi mới `allOf`: sai mục tiêu giới hạn

```java
// Ví dụ anti-pattern: KHÔNG giới hạn số request in-flight.
List<CompletableFuture<HttpResponse<String>>> futures =
        urls.stream()
            .map(url -> client.sendAsync(
                    HttpRequest.newBuilder(url).GET().build(),
                    HttpResponse.BodyHandlers.ofString()))
            .collect(Collectors.toList());

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])).join();
```

Đây là **trích đoạn minh họa lỗi**, thiếu imports và các biến `urls`, `client`. Nếu `urls` chứa 10000 địa chỉ, 10000 lời gọi `sendAsync` đã xảy ra **trước khi `allOf` bắt đầu chờ**. `allOf` chỉ tổng hợp kết quả, **không cấp slot, không giới hạn số request đồng thời**.

### 3.2 Dùng thread pool nhỏ không nhất thiết đủ

`HttpClient.sendAsync` nhanh chóng trả `CompletableFuture`. Một task trên fixed thread pool có thể gọi `sendAsync` rồi kết thúc ngay; thread đó được tái sử dụng để gọi request tiếp theo. Vì vậy “executor có 4 thread” **không có nghĩa** tại mọi thời điểm chỉ có 4 request HTTP in-flight.

`HttpClient.Builder.executor(...)` cũng không phải một API khai báo trần số request. Việc cấu hình executor có ảnh hưởng scheduling và tài nguyên, nhưng không thay thế việc cấp phát/hoàn trả permit ở vòng đời request.

### 3.3 Blocking ở luồng callback không phải backpressure tốt

Không gọi `semaphore.acquire()` chặn vô hạn bên trong callback nhận response hoặc những luồng mà hệ thống cần để **hoàn thành các request đang giữ permit**. Làm vậy có thể gây nghẽn worker, starvation hoặc deadlock. Nếu dùng semaphore blocking, hãy để **một luồng điều phối riêng** đợi với timeout; hoặc dùng `tryAcquire` để quyết định ngay, hoặc xây một async waiter queue có giới hạn rõ.

Không chuyển việc blocking sang `CompletableFuture.supplyAsync(() -> semaphore.acquire())` trên common pool rồi nghĩ đã giải quyết backpressure: nó chỉ di chuyển các tác vụ đang chờ sang thread pool và có thể làm pool bão hòa.

## 4. Ba chính sách được dùng trong thực tế

### 4.1 Chính sách A — backpressure tại producer/coordinator

Producer có danh sách/cursor dữ liệu công việc, chỉ gửi khi số outstanding nhỏ hơn `N`. Khi đã có `N`, nó **chờ một completion**, thu hồi slot rồi gửi tiếp. Request chưa gửi **không** nằm trong hàng đợi I/O của HttpClient.

Ưu điểm: giới hạn rõ và dễ chứng minh; không có hàng đợi request vô hạn trong chính limiter. Nhược điểm: luồng điều phối có thể chờ; không nên dùng trực tiếp trên event loop của HTTP server hoặc UI thread. Cách này đặc biệt phù hợp **batch, crawler có danh sách đầu vào, job nền hoặc producer có thể pause**.

### 4.2 Chính sách B — fail fast bằng Semaphore

Khi request được đề xuất, dùng `semaphore.tryAcquire()`:

- `true`: đã giành được một slot; gọi `sendAsync`.
- `false`: hiện không còn slot; trả kết quả **overloaded/rejected** cho caller, hoặc yêu cầu caller thử lại theo hợp đồng.
- Khi request kết thúc thành công hoặc lỗi: `semaphore.release()` **đúng một lần**.

Ưu điểm: latency xác định, không giữ vô hạn request chờ; phù hợp API inbound cần bảo vệ downstream. Nhược điểm: người gọi phải hiểu lỗi quá tải; retry thiếu kiểm soát dễ tạo bão retry. `Semaphore(true)` có thể cấp phát công bằng cho những lời gọi blocking `acquire`, nhưng `tryAcquire()` không bảo đảm FIFO ngay cả khi fairness bật.

### 4.3 Chính sách C — pending queue có giới hạn

Nếu không thể từ chối ngay, có thể lưu tối đa `Q` yêu cầu đang chờ, đồng thời chỉ gửi tối đa `N`. Khi cả `N` slot và `Q` vị trí queue đều đầy, phải có quy tắc rõ: từ chối, trả `429`/`503` theo API, chuyển sang retry sau, hoặc phát backpressure ngược lên upstream.

**Đừng chuyển từ “vô hạn request in-flight” thành “vô hạn request đang chờ”**. Queue không giới hạn có thể giữ payload, lambda, context tracing, deadline và reference tới dữ liệu lớn, dẫn đến OOM hoặc tăng thời gian chờ. Khi dequeue, hãy kiểm tra request đã hết deadline/hủy chưa để khỏi lãng phí slot.

| Chính sách | Khi hết N slot | Ai phải chịu backpressure? | Rủi ro cần quản lý |
|---|---|---|---|
| Coordinator | Producer chờ completion | Luồng điều phối/cursor | Producer bị block nếu dùng nhầm trên event loop |
| Semaphore fail fast | Không nhận thêm | Caller | Retry storm, cần overload response rõ |
| Queue giới hạn | Chờ tới khi slot trống | Hàng đợi đến tối đa Q | Trễ queue, deadline, ordering, queue full |
| Batch theo từng cửa sổ N | Chờ toàn bộ nhóm N rồi nhóm sau | Batch runner | Head-of-line blocking, tận dụng chưa tối đa |

## 5. Chương trình Java 11 hoàn chỉnh: tối đa 3 request đang chờ kết quả

Đây là mẫu **producer có backpressure**. Một `HttpServer` local trả chuỗi `"ok"`; ba request đầu được giữ bằng `CountDownLatch` đến khi cả ba đã tới server để chứng minh có thể có **đúng 3 request song song**. Client điều phối 9 request, nhưng **không gửi request thứ tư khi còn ba request chưa được xử lý completion**.

Mỗi `sendAsync(...ofString())` hoàn thành khi response body đã nhận đủ. Callback `whenComplete` chỉ đẩy một object `Outcome` vào `ArrayBlockingQueue`. Luồng main lấy result qua `poll`; nó chờ completion khi đã hết slot, và xử lý HTTP status riêng với lỗi bất đồng bộ.

**Điểm quan trọng:** `ArrayBlockingQueue<Outcome>` trong chương trình là **completion queue**, không phải pending-request queue. Dung lượng `LIMIT` đủ vì chỉ có tối đa `LIMIT` request chưa được thu hồi; callback dùng `offer` không blocking. Trong sản phẩm thật, cần ghi log/cảnh báo khi invariant của queue bị vi phạm và không làm callback thực hiện công việc nặng.

Lưu thành **`BoundedHttpDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedHttpDemo {
    static final int TOTAL = 9;
    static final int LIMIT = 3;

    static final class Outcome {
        final int id;
        final HttpResponse<String> response;
        final Throwable error;

        Outcome(int id, HttpResponse<String> response, Throwable error) {
            this.id = id;
            this.response = response;
            this.error = error;
        }

        boolean successful() {
            return error == null && response != null
                    && response.statusCode() == 200
                    && "ok".equals(response.body());
        }
    }

    static Outcome next(BlockingQueue<Outcome> done)
            throws InterruptedException {
        Outcome outcome = done.poll(10, TimeUnit.SECONDS);
        if (outcome == null) {
            throw new IllegalStateException("Completion timed out");
        }
        return outcome;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger activeServer = new AtomicInteger();
        AtomicInteger peakServer = new AtomicInteger();
        AtomicInteger arrivals = new AtomicInteger();
        CountDownLatch firstWave = new CountDownLatch(LIMIT);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService serverThreads = Executors.newFixedThreadPool(4);
        server.setExecutor(serverThreads);
        server.createContext("/work", exchange -> {
            int current = activeServer.incrementAndGet();
            peakServer.accumulateAndGet(current, Math::max);
            try {
                if (arrivals.incrementAndGet() <= LIMIT) {
                    firstWave.countDown();
                    try {
                        if (!firstWave.await(5, TimeUnit.SECONDS)) {
                            throw new IllegalStateException("First wave timeout");
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new java.io.IOException(e);
                    }
                }
                byte[] reply = "ok".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, reply.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(reply);
                }
            } finally {
                activeServer.decrementAndGet();
                exchange.close();
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(5))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/work");
            BlockingQueue<Outcome> completions =
                    new ArrayBlockingQueue<>(LIMIT);

            int outstanding = 0;
            int peakOutstanding = 0;
            int successful = 0;
            int failed = 0;

            for (int id = 1; id <= TOTAL; id++) {
                if (outstanding == LIMIT) {
                    Outcome finished = next(completions);
                    outstanding--;
                    if (finished.successful()) successful++;
                    else failed++;
                }

                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(8)).GET().build();
                outstanding++;
                peakOutstanding = Math.max(peakOutstanding, outstanding);
                final int requestId = id;

                try {
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                            .whenComplete((response, error) -> {
                                if (!completions.offer(
                                        new Outcome(requestId, response, error))) {
                                    throw new IllegalStateException(
                                            "Completion queue unexpectedly full");
                                }
                            });
                } catch (RuntimeException sendFailure) {
                    if (!completions.offer(
                            new Outcome(requestId, null, sendFailure))) {
                        throw new IllegalStateException(
                                "Completion queue unexpectedly full",
                                sendFailure);
                    }
                }
            }

            while (outstanding > 0) {
                Outcome finished = next(completions);
                outstanding--;
                if (finished.successful()) successful++;
                else failed++;
            }

            System.out.println("total=" + TOTAL);
            System.out.println("limit=" + LIMIT);
            System.out.println("peak-outstanding=" + peakOutstanding);
            System.out.println("peak-server-active=" + peakServer.get());
            System.out.println("success=" + successful);
            System.out.println("failed=" + failed);
            if (failed != 0 || successful != TOTAL
                    || peakOutstanding > LIMIT || peakServer.get() > LIMIT) {
                throw new AssertionError("Concurrency limit violated");
            }
        } finally {
            server.stop(0);
            serverThreads.shutdownNow();
        }
    }
}
```

Biên dịch/chạy (module `jdk.httpserver` chỉ phục vụ mô phỏng server; client là API chuẩn `java.net.http`):

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 BoundedHttpDemo.java
java --add-modules jdk.httpserver BoundedHttpDemo
```

**Stdout đã chạy kiểm chứng:**

```text
total=9
limit=3
peak-outstanding=3
peak-server-active=3
success=9
failed=0
```

### Vì sao limit luôn đúng?

1. `outstanding` chỉ được tăng khi coordinator đã giữ một slot cho một lời gọi `sendAsync`. Đó là **số request đã submit nhưng result chưa được coordinator thu hồi**; kể cả một request mạng vừa hoàn thành nhưng chưa được lấy kết quả, slot vẫn bị giữ, nên giới hạn luôn **bảo thủ**.
2. Trước mỗi lần submit, nếu `outstanding == LIMIT`, coordinator đợi một `Outcome`, giảm `outstanding` rồi mới được gửi tiếp. Bất biến `0 <= outstanding <= LIMIT` được giữ cho mỗi bước.
3. Callback `whenComplete` được gọi cho cả response bình thường lẫn completion lỗi. Nó chuyển `response/error` sang queue; việc xử lý kết quả được dồn về coordinator, nên không cần chia sẻ mutable `successful`/`failed` giữa nhiều luồng.
4. Khi gửi xong danh sách, vòng `while (outstanding > 0)` tiếp tục thu hồi những kết quả cuối cùng; không bỏ sót future còn treo. `poll(10, TimeUnit.SECONDS)` giới hạn **thời gian chờ completion của coordinator**, khác với timeout 8 giây đặt trên mỗi HTTP request.
5. Server kiểm tra song song thực tế bằng `AtomicInteger activeServer` và latch. Ba request đầu không trả xong trước khi cả ba tới, nên peak server trong demo là 3. Con số này phụ thuộc cơ chế test, **không** được suy thành quy tắc cho mọi server/HTTP version.

Trong demo, request body chỉ hai byte và dùng `ofString` vì nội dung nhỏ. Với response lớn, dùng `ofFile` hoặc xử lý stream có giới hạn bộ nhớ và điều chỉnh đúng mốc trả slot. Cũng không nên coi `sendAsync` và `CompletableFuture` luôn có kết quả thành công; mã ví dụ chủ động giữ cả `response` và `error`.

**Lưu ý về kiểu thành công:** HTTP status khác 200 được tính là thất bại nghiệp vụ trong demo, dù future HTTP **có thể vẫn hoàn tất bình thường**. Phân biệt failure do HTTP status với `IOException` hoặc timeout từ future.

## 6. Chương trình thứ hai: fail fast với Semaphore

Khi phía gọi không thể hoặc không nên đợi, sử dụng `tryAcquire`. Ví dụ cho **2 request đồng thời** trong số 5 yêu cầu được đề xuất. Server giữ hai request đầu bằng latch cho tới khi main đã tính xong số accepted/rejected, nên kết quả không phụ thuộc vào tốc độ máy.

Lưu thành **`FailFastLimiterDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class FailFastLimiterDemo {
    public static void main(String[] args) throws Exception {
        final int limit = 2;
        final int candidates = 5;
        Semaphore permits = new Semaphore(limit);
        CountDownLatch arrived = new CountDownLatch(limit);
        CountDownLatch releaseServer = new CountDownLatch(1);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(limit);
        server.setExecutor(workers);
        server.createContext("/small", exchange -> {
            try {
                arrived.countDown();
                try {
                    if (!releaseServer.await(5, TimeUnit.SECONDS)) {
                        throw new java.io.IOException("Server timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new java.io.IOException(e);
                }
                byte[] reply = "OK".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, reply.length);
                try (OutputStream output = exchange.getResponseBody()) {
                    output.write(reply);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/small");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();
            List<CompletableFuture<HttpResponse<String>>> inFlight =
                    new ArrayList<>();
            int accepted = 0;
            int rejected = 0;

            for (int i = 0; i < candidates; i++) {
                if (!permits.tryAcquire()) {
                    rejected++;
                    continue;
                }
                HttpRequest req = HttpRequest.newBuilder(url)
                        .timeout(Duration.ofSeconds(8)).GET().build();
                try {
                    CompletableFuture<HttpResponse<String>> task =
                            client.sendAsync(req,
                                    HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8));
                    inFlight.add(task.whenComplete((resp, error) ->
                            permits.release()));
                    accepted++;
                } catch (RuntimeException e) {
                    permits.release();
                    throw e;
                }
            }

            if (!arrived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Requests did not arrive");
            }
            System.out.println("accepted=" + accepted);
            System.out.println("rejected=" + rejected);
            System.out.println("permits-during-flight="
                    + permits.availablePermits());
            releaseServer.countDown();

            CompletableFuture.allOf(inFlight.toArray(
                    new CompletableFuture<?>[0])).join();
            boolean allOk = inFlight.stream().allMatch(f ->
                    f.join().statusCode() == 200 &&
                    "OK".equals(f.join().body()));
            System.out.println("all-success=" + allOk);
            System.out.println("permits-after=" + permits.availablePermits());

            if (accepted != limit || rejected != candidates - limit
                    || !allOk || permits.availablePermits() != limit) {
                throw new AssertionError("Unexpected permit accounting");
            }
        } finally {
            releaseServer.countDown();
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 FailFastLimiterDemo.java
java --add-modules jdk.httpserver FailFastLimiterDemo
```

```text
accepted=2
rejected=3
permits-during-flight=0
all-success=true
permits-after=2
```

### Giải thích điểm đặt `tryAcquire` và `release`

- Mỗi request phải lấy permit **trước** `sendAsync`. Nếu không lấy được, request **không** được gửi, số `rejected` tăng.
- Khi đã lấy permit, callback `whenComplete` trả lại permit khi future tương ứng hoàn tất, dù kết quả thành công hay thất bại bất đồng bộ. Nếu `sendAsync` ném lỗi **đồng bộ** trước khi trả future, nhánh `catch` cũng trả permit.
- Callback hoàn trả permit trước khi dependent future do `whenComplete` tạo ra hoàn tất, vì vậy `allOf` trên các stage này bảo đảm permit đã được trả trong demo.
- `allOf` ở đây **chỉ chờ những request đã được nhận vào hệ thống**, không quyết định limit. **Chính `tryAcquire` trước lời gọi HTTP** mới bảo đảm không gửi vượt số permit.
- `permits-after=2` xác nhận permit không bị quên hoặc nhân đôi trong đường chạy thành công. Khi đưa vào dự án, nên có metric `availablePermits` và test các nhánh lỗi/timeout để phát hiện permit leak.

**Chính sách khi bị từ chối:** Ở demo, request bị từ chối chỉ được đếm; không tự retry. Trong REST API thật, caller có thể được trả lỗi overload kèm thông tin `Retry-After` khi phù hợp với hợp đồng; worker có thể tái xếp lịch với backoff và giới hạn tổng số lần thử. Không để mỗi lần bị từ chối lập tức tạo thêm hàng loạt request mới.

**Nếu muốn chờ thay vì từ chối:** Có thể dùng `semaphore.acquire()` hoặc `tryAcquire(timeout, TimeUnit)` từ **luồng điều phối phù hợp**; nhưng bản thân các lệnh này **chặn thread**. Không chạy chúng trên HTTP callback/event loop đang cần hoàn tất những request giữ permit. Nếu lựa chọn một queue bất đồng bộ, đặt sức chứa Q và deadline rõ ràng.

## 7. Vì sao mốc trả permit phụ thuộc BodyHandler?

Trên Java 11, ý nghĩa hoàn tất của `HttpClient.sendAsync(request, handler)` phụ thuộc vào `BodySubscriber` bên trong handler:

| Handler | Khi future `HttpResponse<T>` hoàn tất thành công | Khi có thể trả permit nếu limit tính đến full body? |
|---|---|---|
| `BodyHandlers.ofString()` | Body đã tích lũy và giải mã | Khi future hoàn tất |
| `BodyHandlers.ofByteArray()` | Body đã thu đủ thành mảng | Khi future hoàn tất |
| `BodyHandlers.discarding()` | Body đã được tiêu thụ/loại bỏ | Khi future hoàn tất |
| `BodyHandlers.ofFile(path)` | Body đã được ghi xong vào file | Khi future hoàn tất và cleanup/validation theo hợp đồng |
| `BodyHandlers.ofInputStream()` | Headers đã có; body **có thể chưa nhận hết** | **Sau khi đọc/đóng** stream và xử lý kết quả |
| `BodyHandlers.ofLines()` | Cấp một `Stream<String>` có thể còn đang nhận dữ liệu | Sau khi duyệt/đóng stream |
| `BodyHandlers.ofPublisher()` | Cấp publisher; body có thể chưa được tiêu thụ | Khi subscriber đã hoàn thành/được xử lý lỗi hoặc hủy đúng cách |

### Ví dụ thứ ba — không trả slot khi chỉ vừa nhận headers

Demo cho server trả hai byte `A` và `B` nhưng giữ `B` lại. Client gọi `sendAsync(...ofInputStream())`, nhận `HttpResponse<InputStream>` **khi byte cuối chưa gửi**. Permit vẫn phải được giữ cho đến khi client đọc tới hết body và đóng stream.

Lưu thành **`StreamingPermitDemo.java`**:

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class StreamingPermitDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(1);
        CountDownLatch allowTail = new CountDownLatch(1);
        CountDownLatch tailSent = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/stream", exchange -> {
            exchange.sendResponseHeaders(200, 2);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write('A');
                out.flush();
                try {
                    if (!allowTail.await(5, TimeUnit.SECONDS)) {
                        throw new java.io.IOException("Server timeout");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new java.io.IOException(e);
                }
                out.write('B');
                out.flush();
                tailSent.countDown();
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newHttpClient();
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/stream");
            HttpRequest request = HttpRequest.newBuilder(uri).GET().build();

            slots.acquire();
            try {
                HttpResponse<InputStream> response =
                        client.sendAsync(request,
                                HttpResponse.BodyHandlers.ofInputStream())
                                .get(5, TimeUnit.SECONDS);

                System.out.println("response-status=" + response.statusCode());
                System.out.println("tail-sent-when-response-returned="
                        + (tailSent.getCount() == 0));
                System.out.println("permits-before-consuming="
                        + slots.availablePermits());

                try (InputStream body = response.body()) {
                    int first = body.read();
                    allowTail.countDown();
                    String rest = new String(body.readAllBytes(),
                            StandardCharsets.UTF_8);
                    System.out.println("complete-body=" + ((char) first) + rest);
                }
            } finally {
                allowTail.countDown();
                slots.release();
            }
            System.out.println("permits-after-body=" + slots.availablePermits());
        } finally {
            allowTail.countDown();
            server.stop(0);
        }
    }
}
```

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 StreamingPermitDemo.java
java --add-modules jdk.httpserver StreamingPermitDemo
```

```text
response-status=200
tail-sent-when-response-returned=false
permits-before-consuming=0
complete-body=AB
permits-after-body=1
```

**Diễn giải:** `response-status=200` không chứng minh body đã đầy đủ; `tail-sent-when-response-returned=false` xác nhận server chưa phát byte cuối, trong khi đã có response. `permits-before-consuming=0` cho thấy slot vẫn giữ. Chỉ sau khi đọc được `AB`, đóng stream và rời khối `finally` thì permit được trả; nếu bỏ phép giữ permit đến mốc này, giới hạn số body đang streaming sẽ không được bảo toàn.

Đây là demo **một request**, nên gọi `slots.acquire()` trên main là được. Với dịch vụ async có nhiều request, cần điều phối không blocking. Nếu xử lý streaming cần thread đọc blocking, nên dùng **executor riêng có giới hạn**, và chỉ trả permit trong `finally` của thao tác đọc/đóng đầy đủ. Không chuyển một loạt công việc đọc stream blocking lên `ForkJoinPool.commonPool` mà không giới hạn, vì số callback/thread có thể trở thành nút thắt.

Nếu client hủy một response body stream sớm, phải **đóng stream** và quyết định kết quả là hủy/chưa đầy đủ; việc hoàn trả permit sau close bảo đảm không giữ slot vô hạn. Cần lưu ý hủy future không đảm bảo các byte đã gửi trên mạng được thu hồi ngay hoặc server ngừng xử lý tức thì.

## 8. Phân biệt concurrency limit, rate limit và connection limit

Giả sử `MAX_IN_FLIGHT = 10`.

- Khi mỗi request mất khoảng **1 giây**, tốc độ hoàn tất ổn định có thể xấp xỉ **10 request/giây** nếu luôn có việc và không có bottleneck khác.
- Khi mỗi request chỉ mất **0,01 giây**, cùng 10 slot đó có thể đáp ứng hàng trăm request/giây.
- Khi server chậm còn **5 giây**, 10 slot có thể chỉ hoàn tất khoảng **2 request/giây**.

Đây là ví dụ trực quan, **không phải cam kết throughput**. Với workload đủ ổn định, quan hệ gần đúng là `concurrency ≈ throughput × average latency`. Dùng latency quan sát được để ước lượng một mức khởi điểm, rồi benchmark và điều chỉnh theo CPU, bộ nhớ, connection pool, timeout, hạn mức của downstream và lỗi thực tế.

Nếu API đối tác quy định **100 request/giây**, chỉ đặt `Semaphore(10)` chưa đảm bảo tuân thủ hạn mức này. Cần **rate limiter** (ví dụ token bucket) riêng. Ngược lại, rate limiter 100 req/s không tự đảm bảo số request in-flight khi một request mất rất nhiều giây. Hệ thống có thể cần **cả hai**.

Nếu yêu cầu “tối đa 5 connection đến host X”, đó là **connection pool/network policy**, khác với “tối đa 5 HTTP request đồng thời”. Trong HTTP/2, một TCP connection có thể mang nhiều HTTP stream. Không coi số thread, connection, request và body subscriber là cùng một biến.

### Limit theo host, endpoint, tenant hay toàn ứng dụng?

| Phạm vi | Công dụng | Điều cần cân nhắc |
|---|---|---|
| Global trong JVM | Bảo vệ tổng tài nguyên local | Mọi host chia chung ngân sách |
| Per host | Tránh gây quá tải một downstream | Cần ánh xạ host chính xác và dọn limiter ít dùng |
| Per endpoint | Endpoint chậm/nặng có ngân sách riêng | Một host có thể có nhiều route với chi phí khác nhau |
| Per tenant/customer | Công bằng đa khách hàng | Tránh khách hàng lớn chiếm hết slot |
| Cluster-wide | Giới hạn tổng nhiều service instances | Cần giải pháp phân tán/điều phối, không phải Semaphore local |

**Không tạo một Semaphore mới cho từng request** — mỗi request sẽ có riêng N permit và trần concurrency thực tế bị vô hiệu hóa. Semaphore phải **được chia sẻ** đúng phạm vi mà giới hạn có hiệu lực.

## 9. Queue, backpressure và sự công bằng

Khi số request vào nhanh hơn số request hoàn tất, ứng dụng phải chọn nơi đọng lại công việc. Một thiết kế bảo vệ tài nguyên nên có ít nhất:

- `maxInFlight`: số request đã gửi hoặc body đang xử lý.
- `maxPending`: số yêu cầu chưa được gửi và đang chờ slot.
- `maxQueueWait` hoặc deadline: thời gian tối đa chờ trước khi coi yêu cầu quá hạn.
- Chính sách queue full: từ chối, giảm tốc producer, hoặc đặt lịch thử lại.
- Chính sách sắp xếp: FIFO, ưu tiên, deadline, per-tenant fairness khi nghiệp vụ yêu cầu.

`ArrayBlockingQueue` chứa task chờ có giới hạn rõ; `offer` trả `false` khi đầy, `put` chặn luồng gọi, `poll(timeout)` chờ có giới hạn. Dùng API theo loại luồng: event-loop không nên bị chặn bởi `put`.

Với completion queue, chỉ đẩy vào những kết quả đã xong; giới hạn queue có thể nhỏ bằng max outstanding nếu mỗi request sinh **chính xác một completion**. Với pending queue, mỗi phần tử có thể là dữ liệu/payload chưa gửi; không được giả định pending queue đã giới hạn body memory, vì task chứa tham chiếu đến buffer lớn cũng chiếm tài nguyên.

**Fairness:** `new Semaphore(limit, true)` giúp những lời gọi blocking `acquire` được chọn gần FIFO ở điểm quy định của API, nhưng `tryAcquire()` không tuân thủ fairness theo cùng cách. Nếu SLA yêu cầu ưu tiên tenant hoặc tránh starvation, hãy xây scheduler theo policy thay vì kỳ vọng semaphore fairness tự giải quyết mọi vấn đề.

### Khi các request có thời gian chạy không đều

Một cách đơn giản là chia danh sách thành từng **nhóm N** rồi `allOf` từng nhóm. Nó đúng giới hạn concurrency nếu không có nguồn gửi khác qua mặt limiter, nhưng có hiện tượng **head-of-line blocking**: cả nhóm phải chờ request chậm nhất trước khi nhóm sau bắt đầu. Với queue completion như ví dụ 1, cứ **một request hoàn tất** là slot được tái sử dụng cho request tiếp theo, tận dụng tài nguyên tốt hơn khi latency biến động.

Nếu request có thời gian rất dài, một vài request chậm có thể giữ slot và giảm throughput. Đặt deadline/timeout thực tế, quan sát tail latency và tránh cấu hình quá mức khiến downstream quá tải hơn.

## 10. Xử lý ngoại lệ, timeout, retry và cancellation

### 10.1 Permit phải được trả đúng một lần

Một invariant quan trọng:

```text
permit acquired
    ├─ sendAsync ném lỗi đồng bộ
    │      └─ release đúng một lần
    └─ sendAsync trả CompletableFuture
           ├─ HTTP response hoàn thành thành công
           │      └─ release đúng một lần
           └─ Future hoàn thành ngoại lệ
                  └─ release đúng một lần
```

Với handler nhận body đầy đủ, callback `whenComplete` là nơi phù hợp vì nó chạy trên **cả nhánh success và error**. `thenApply` chỉ xử lý success, dễ gây mất permit khi future thất bại. Nhớ rằng `sendAsync` cũng có thể ném lỗi đồng bộ khi request không hợp lệ. Nếu đã nhận permit mà chưa gắn được callback, phải trả trong catch.

**Cảnh báo:** Đừng vừa `release` trong callback `whenComplete` vừa `release` lần nữa trong `finally` bao quanh code tạo future khi sendAsync đã thành công; sẽ làm số permit lớn hơn limit và phá bất biến.

### 10.2 HTTP status lỗi không nhất thiết làm future exceptional

HTTP `400`, `404`, `429`, `503` hay `500` thường vẫn trả `HttpResponse<T>` bình thường; đó là trạng thái nghiệp vụ/giao thức. Khi giới hạn concurrency, **vẫn phải trả permit** sau khi body error response được đọc/xử lý đến mốc đã quy định. Ghi số lượng response 2xx, 4xx, 5xx riêng với timeout, `IOException`, DNS/TLS và cancellation.

### 10.3 Timeout ở nhiều tầng

- `HttpClient.Builder.connectTimeout(Duration)`: timeout thiết lập kết nối.
- `HttpRequest.Builder.timeout(Duration)`: thời gian yêu cầu theo hợp đồng HTTP client.
- `completionQueue.poll(timeout)`: giới hạn **luồng điều phối** chờ completion, không tự cancel request đang chạy.
- `maxQueueWait`: thời hạn một task được phép đợi trước khi gọi `sendAsync`; không đồng nhất với request timeout vốn bắt đầu khi gửi.
- `Flow`/streaming: thời gian nhận **toàn bộ body** có thể khác thời gian response object xuất hiện. Cần deadline và cleanup theo hợp đồng.

Nếu coordinator `poll` timeout, **không** được giảm `outstanding` như thể request đã hoàn tất khi chưa có kết quả, vì request HTTP có thể vẫn đang chạy. Ví dụ 1 ném lỗi chẩn đoán và đi vào cleanup thay vì lặng lẽ tạo thêm slot. Trong sản phẩm, thiết kế timeout phải đi kèm cancel/close, tracking outstanding và xử lý completion đến muộn.

### 10.4 Retry cũng cần đi qua limiter

Nếu một request lỗi và cần retry, lần thử lại là **một request mới**; phải lấy slot trong cùng limiter. Không đặt `retry` trong callback mà bypass quyền cấp slot, vì nhiều lỗi cùng lúc có thể làm bùng nổ request. Dùng retry giới hạn số lần, exponential backoff kèm jitter khi phù hợp, xác định lỗi nào có thể thử lại, và xét idempotency của GET/PUT/POST theo API.

Khi server trả HTTP `429 Too Many Requests`, ngoài max concurrency còn có thể tồn tại hạn mức tốc độ; tôn trọng `Retry-After` và policy của provider. Khi `503 Service Unavailable`, cân nhắc circuit breaker, retry có giới hạn và trạng thái downstream. Đừng “chữa” overload bằng cách tăng limit vô hạn.

### 10.5 Cancellation và shutdown

`CompletableFuture.cancel(...)` đánh dấu completion ở phía future theo API, nhưng không đảm bảo mọi tác vụ hệ thống/mạng hoặc server dừng ngay lập tức. Trong Java 11, không nên giả định hủy đã giải phóng mọi byte/body stream. Với streaming, phải đóng response body đúng nghĩa. Khi shutdown service, dừng nhận yêu cầu mới, đợi/cancel công việc theo deadline, drain completions, đóng resource và kiểm soát các callback đến muộn.

`HttpClient` trong Java 11 không cung cấp hợp đồng `AutoCloseable` như một số API đời sau; đừng viết ví dụ `try (HttpClient client = ...)` rồi yêu cầu biên dịch với `--release 11`. Tái sử dụng một `HttpClient` cho nhiều request thường hợp lý hơn tạo client mới mỗi lần.

## 11. Theo dõi hiệu năng và chọn limit

Số limit tối ưu phụ thuộc mục tiêu latency, khả năng downstream và tài nguyên. Những metric cần có:

| Metric | Ý nghĩa | Điều cần để ý |
|---|---|---|
| `in_flight` | Request đã gửi/chưa hoàn thành | Có vượt cap không? |
| `pending_queue_size` | Số task đợi slot | Có tăng liên tục không? |
| `queue_wait_ms` | Thời gian chờ từ lúc được đề xuất tới lúc gửi | Phần lớn deadline bị tiêu trong queue? |
| `request_latency_ms` | Thời gian từ gửi tới mốc hoàn thành | Độ trễ p50/p95/p99, timeout |
| `active_permits` hoặc `availablePermits()` | Ngân sách slot đang dùng/còn trống | Có leak permit không? |
| `rejected_total` | Số request bị từ chối vì hết slot/queue | Caller có chính sách backoff không? |
| `http_status_total` | Số response theo nhóm 2xx, 4xx, 429, 5xx | Downstream có đang quá tải? |
| `transport_error_total` | DNS, TLS, IOException, timeout | Phân biệt với HTTP errors |
| `bytes_received` | Lượng body đã nhận | Streaming giữ slot bao lâu? |

Một limit quá nhỏ có thể giảm throughput và làm queue tăng; limit quá lớn có thể tăng lỗi/latency và khiến downstream **chậm hơn**. Kiểm thử tải với profile dữ liệu thật, giữ các giới hạn về số instance/host/endpoint và tài nguyên trong container. Khi tăng limit, đo thay đổi p95/p99, lỗi 429/503 và CPU/bộ nhớ thay vì chỉ nhìn tổng số request đã gửi.

**An toàn khi đo:** “peak outstanding” của ví dụ 1 đếm slot đã cấp nhưng result chưa được coordinator xử lý, nên có thể cao hơn số HTTP exchange đang dùng network đúng tại một thời điểm. Đây là một **giới hạn bảo thủ** và vẫn bảo đảm không có hơn N request network đang được bắt đầu qua coordinator; đừng gán nhãn metric này thành số TCP connections.

## 12. Ma trận kiểm thử và QA concurrency

| Tình huống | Thiết lập | Kết quả cần xác minh |
|---|---|---|
| Đúng limit | 9 request, N=3 | Peak request chưa thu hồi <=3 |
| Có song song thật | Server giữ ba request đầu bằng latch | Server peak đạt 3, không vượt 3 |
| Fail fast | 5 request, 2 permit, hai request đầu đang giữ | 2 được gửi, 3 bị từ chối |
| Permit hoàn trả | Hai request hoàn tất | `availablePermits() == 2` |
| Request bị HTTP 500 | Server trả status 500 với body hoàn chỉnh | Slot được trả, status lỗi được ghi nhận |
| Future exceptional | Server đóng/ngắt, client timeout | Slot vẫn được trả, lỗi không bị nuốt |
| sendAsync lỗi đồng bộ | Request bị từ chối trước khi tạo future | Nhánh catch trả slot |
| Body streaming | Server mới gửi header/A, chưa gửi B | `ofInputStream` future có thể xong, slot vẫn bị giữ |
| Body streaming đọc tới EOF | Server gửi nốt B | Sau đọc/đóng stream, slot mới trả |
| Queue full | N slot đang bận, Q pending đã đầy | Request mới theo chính sách reject/backpressure |
| Coordinator timeout | Không có completion trong deadline | Không tự ý tạo slot ảo; cleanup |
| Retry hàng loạt | Nhiều request gặp 503 cùng lúc | Retry cũng qua limiter, có backoff |
| Shutdown | Có request đang chạy và task đang chờ | Không nhận task mới, không rò permits |
| Nhiều caller | Cùng sử dụng chung limiter | Tổng in-flight vẫn không vượt N |
| Nhiều service instances | Mỗi instance có N permit | Nhận thức đây **không** là global limit |

Để tránh test flaky, dùng `CountDownLatch` hoặc tín hiệu từ server, không dùng `Thread.sleep(100)` làm điều kiện xác minh. Các test về lỗi mạng nên có timeout và phân biệt lỗi mong đợi với lỗi setup. Có thể dùng MockWebServer/test HTTP server tương thích dự án, nhưng ba ví dụ trên chỉ dùng API JDK 11.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tạo 10.000 `sendAsync` rồi `allOf` | 10.000 request đã được gửi trước khi chờ | Giới hạn **trước sendAsync** |
| Dùng fixed thread pool nhỏ thay limiter | Thread hoàn tất việc submit nhanh, request vẫn in-flight | Permit/queue theo vòng đời HTTP |
| Tạo `Semaphore(N)` mới mỗi request | Không có ngân sách chung | Chia sẻ limiter đúng phạm vi |
| Dùng `acquire()` blocking trong callback | Có thể nghẽn pool hoặc deadlock | Coordinator riêng, `tryAcquire` hoặc async queue |
| `thenApply(...release...)` chỉ trên success | Lỗi future làm leak permit | `whenComplete` và nhánh lỗi đồng bộ |
| `release` cả callback và `finally` vô điều kiện | Permit tăng vượt N | Quy định chính xác một nhánh sở hữu release |
| Xem HTTP 429 là exception của sendAsync | Không ghi trạng thái đúng | Kiểm tra `statusCode()` và body |
| Giải phóng slot ngay khi `ofInputStream` future xong | Body vẫn có thể truyền | Giữ tới EOF/close/validation |
| Dùng queue pending không giới hạn | RAM và latency tăng không giới hạn | Bound Q và deadline, reject rõ |
| Xem `CompletableFuture.allOf` là bộ giới hạn | Không có cơ chế cấp slot | Gắn permit trước từng lời gọi |
| Gọi `cancel` rồi cho rằng server đã ngừng ngay | Resource mạng có thể còn dùng | Theo dõi cleanup và completion muộn |
| Retry không qua limiter | Retry storm làm vượt N | Mỗi attempt chiếm slot riêng |
| Coi N slot tương đương N req/s | Request có latency khác nhau | Rate limit riêng |
| Coi N slot tương đương N connection | HTTP/2 và pooling khác | Dùng metric/limit đúng đối tượng |
| Chỉ nhìn `getNumberOfDependents()` làm số request | Đây không phải in-flight HTTP counter | Dùng counter/limiter do app quản lý |
| Không đo queue wait và tail latency | Limit có thể đẩy chậm xuống queue | Đo `queue_wait` + `request_latency` |

## 14. Bài tập có đáp án

**Bài 1 — eager scheduling.** Có 500 URL. Gọi `sendAsync` cho tất cả rồi `allOf(...).join()`. Có phải chỉ 1 request đồng thời vì thread main đang chờ?  
**Đáp án:** không. Tất cả 500 lời gọi `sendAsync` đã được thực hiện trước khi `allOf` chờ. Thread main blocking không phải giới hạn in-flight.

**Bài 2 — Semaphore.** Một limiter có 4 permit. Bốn request đã lấy hết permit, yêu cầu thứ năm gọi `tryAcquire()`. Điều gì xảy ra?  
**Đáp án:** trả `false` ngay; request thứ năm **chưa được gửi**. Caller áp dụng chính sách quá tải.

**Bài 3 — exception.** Request thứ hai timeout nhưng vẫn trả permit hay giữ mãi?  
**Đáp án:** phải trả permit sau khi future hoàn tất lỗi và tài nguyên đã được xử lý theo vòng đời chọn. `whenComplete` cần xử lý cả lỗi, đồng thời phải có timeout/cleanup tránh giữ slot vô hạn.

**Bài 4 — streaming.** `sendAsync(...ofInputStream())` đã hoàn tất, nhưng server chưa gửi byte cuối. Có nên release permit ngay?  
**Đáp án:** không nếu limit định nghĩa tới khi body hoàn tất. Giữ slot tới sau đọc/đóng stream; demo mục 7 chứng minh.

**Bài 5 — số thread.** Đặt `Executors.newFixedThreadPool(2)` để chạy code mỗi task chỉ gọi `sendAsync` rồi trả. Có chắc chỉ 2 HTTP request đang chạy?  
**Đáp án:** không. Hai thread có thể submit rất nhiều request trong một thời gian ngắn rồi quay lại lấy task mới.

**Bài 6 — rate và concurrency.** Một hệ thống có limit 5 in-flight nhưng upstream chỉ cho 20 request/giây. Có thể chỉ dùng semaphore không?  
**Đáp án:** không. Concurrency phụ thuộc thời gian thực thi; cần thêm rate limiter cho hạn mức tốc độ.

**Bài 7 — nhiều instance.** Một service có 4 instance, mỗi instance `Semaphore(3)`. Có bảo đảm toàn hệ thống <=3 request tới downstream không?  
**Đáp án:** không. Tổng có thể tới khoảng 12 request; cần điều phối ngân sách toàn cụm nếu API downstream yêu cầu.

**Bài 8 — queue và deadline.** Trong một queue dài, request đợi 30 giây dù deadline từ upstream là 5 giây. Có nên gửi tiếp khi có slot?  
**Đáp án:** không. Kiểm tra deadline/cancellation lúc dequeue, loại bỏ task đã hết hạn và cập nhật metric rejected/expired.

**Bài 9 — công bằng.** Vì sao `new Semaphore(3,true)` không có nghĩa mọi lời gọi `tryAcquire()` được xử lý FIFO?  
**Đáp án:** Javadoc nêu `tryAcquire` không tuân theo fairness; muốn chính sách ưu tiên/FIFO thực sự, cần scheduler/queue tương ứng.

## 15. Tài liệu chính thức

- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync`, `send`, kiểu `BodyHandler`, cách nhận `CompletableFuture`, executor/connection.
- [Java SE 11 — HttpRequest](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): builder và request timeout.
- [Java SE 11 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): mốc hoàn tất của handler tích lũy và streaming.
- [Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `whenComplete`, `allOf`, `anyOf`, `cancel`, completion exceptional.
- [Java SE 11 — Semaphore](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Semaphore.html): `tryAcquire`, `acquire`, `release`, fairness và memory consistency.
- [Java SE 11 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): `offer`, `poll` và queue có sức chứa cố định.
- [Java SE 11 — HttpServer](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server local phục vụ kiểm thử.
- [Java SE 11 — Flow](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/Flow.html): publisher/subscriber demand và completion trong trường hợp streaming.

**Nguyên tắc cuối:** giới hạn concurrency **trước khi gửi request** và giữ slot đến đúng mốc hoàn tất theo `BodyHandler`. Chọn chính sách backpressure rõ ràng, giới hạn cả số pending task, bảo đảm cleanup/hoàn permit trên mọi nhánh lỗi và đo lường thực tế. `sendAsync` cho khả năng đồng thời; chính ứng dụng phải quyết định **được phép đồng thời bao nhiêu**.