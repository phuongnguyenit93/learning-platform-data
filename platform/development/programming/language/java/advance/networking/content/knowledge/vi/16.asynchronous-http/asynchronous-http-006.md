# Giới hạn số yêu cầu HTTP đồng thời thay vì tạo không giới hạn Future trong Java

**`HttpClient.sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>` ngay khi yêu cầu được khởi tạo, nhưng không tự giới hạn số lời gọi mà ứng dụng submit.** Nếu chạy một vòng lặp trên hàng trăm nghìn phần tử rồi tạo Future cho tất cả trước khi chờ kết quả, ta có thể gây quá tải đối với client, máy chủ đích, mạng, bộ nhớ hoặc hệ thống điều phối.

Cách đúng khi số request lớn là **bounded concurrency (giới hạn in-flight)**: chỉ cho phép nhiều nhất `K` HTTP operations đang chờ xử lý. Khi một operation kết thúc — thành công **hoặc** lỗi — mới cấp chỗ cho request tiếp theo. Với stream công việc liên tục, còn cần giới hạn **hàng đợi chờ** và một chính sách từ chối/chờ rõ ràng để tránh chuyển việc quá tải từ mạng sang RAM.

Bài Knowledge này nằm trong chủ đề **HTTP bất đồng bộ**. Nội dung tập trung vào giới hạn số HTTP requests đồng thời, phân biệt Future và operation thực tế, các cách cấp phát slot, xử lý success/error/timeout/cancel, backpressure, fairness, giới hạn theo host và quan trắc. Hai chương trình Java 17+ hoàn chỉnh sẽ minh họa:

1. **`SemaphoreHttpDemo.java`:** luồng producer lấy permit trước khi gọi `sendAsync`, callback trả permit; 12 HTTP requests, tối đa 3 outstanding, không giữ danh sách 12 futures.
2. **`AsyncWindowDemo.java`:** một cửa sổ bất đồng bộ (sliding window) duy trì tối đa 3 request bằng event dispatcher, **không block producer/event-loop trong `Semaphore.acquire()`** và cũng không tạo sẵn future cho toàn bộ dữ liệu.

Các ví dụ dùng HTTP server trong chính chương trình, bind `127.0.0.1` và cổng động; không cần Internet, không gửi traffic tới dịch vụ ngoài. Độ trễ giữa các response có thể khác nhau, nên chỉ khẳng định những output xác định từ các counters/invariants, **không dựa vào thứ tự response hoàn thành**.

## 1. Vì sao “async” không đồng nghĩa “không có giới hạn”?

Xem đoạn mã minh họa sau (cần `client` và tập `urls` được khai báo):

~~~java
List<CompletableFuture<HttpResponse<String>>> futures =
        new ArrayList<>();

for (URI uri : urls) {
    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    futures.add(client.sendAsync(
            request, HttpResponse.BodyHandlers.ofString()));
}

CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])).join();
~~~

Đây là **phản ví dụ cho tập dữ liệu không giới hạn**, không phải code khuyến nghị khi số URL rất lớn. `sendAsync` không block tới khi response hoàn tất, nên vòng lặp có thể submit một lượng request rất lớn trước khi network có cơ hội xử lý xong. `allOf(...).join()` chỉ chờ **sau khi tất cả futures đã được tạo**; nó không làm số request in-flight nhỏ đi.

Hệ quả có thể gồm:

- **Client:** phát sinh nhiều kết nối/streams HTTP, TLS handshakes, I/O tasks, headers, body subscribers, ByteBuffers và dữ liệu trong heap.
- **Máy chủ đích:** quá nhiều requests cùng lúc gây hàng đợi, timeouts, rate limiting, mã 429/503, hoặc overload.
- **Ứng dụng:** danh sách `futures` và các lambda giữ reference tới request/response/attachments, làm tăng GC pressure và thậm chí OOM.
- **Hệ thống ngoài:** database, API gateway và downstream của server cũng có thể bị kéo quá tải.
- **Khả năng kiểm soát:** khó biết request nào còn active, khi nào được phép submit tiếp, bao nhiêu đã fail và khi nào dừng.
- **Retry:** nếu mọi request thất bại cùng lúc rồi retry ngay, rất dễ hình thành **retry storm**.

**`CompletableFuture` là cách biểu diễn một kết quả đến sau, không phải bộ điều tiết tài nguyên.** `CompletableFuture.allOf(...)` giúp *phối hợp chờ*, không phải *giới hạn concurrency*. Tương tự, `client.sendAsync(...)` thuận tiện nhưng không tự kiểm soát số request nghiệp vụ mà bạn muốn in-flight.

## 2. Một request “in-flight” được tính từ đâu tới đâu?

Hãy định nghĩa rõ **đơn vị đang bị giới hạn**:

> Một request logic chiếm **một slot** từ ngay trước khi ứng dụng submit `HttpClient.sendAsync` cho đến khi operation kết thúc và callback xử lý kết quả đã hoàn tất đủ để nhả slot.

Trong hai ví dụ, body handler là `HttpResponse.BodyHandlers.ofString(UTF_8)`, nên Future hoàn tất sau khi response body đã được thu và chuyển thành String. Nhờ vậy, mỗi slot bao trùm giai đoạn nhận **toàn bộ** response text.

~~~text
                     Application request #17
                             |
                     acquire one slot
                             |
                             v
                    HttpClient.sendAsync(...)
                             |
                     request in-flight
                             |
               +-------------+-------------+
               |                           |
          HTTP response                  exception
               |                           |
          inspect status                inspect cause
               |                           |
               +-------------+-------------+
                             |
                    completion handler
                             |
                      release one slot
                             |
                    admit next request
~~~

**Hai điểm cần phân biệt:**

1. *In-flight logical requests* khác với **số TCP sockets**, số HTTP/2 streams, số thread trong executor hoặc số Future objects đã từng được tạo. Một HTTP/2 connection có thể mang nhiều requests; một logical request có thể gặp redirect/retry và tạo thêm network activity. Bài này giới hạn số operations ở **tầng ứng dụng**.
2. Nếu dùng streaming body handler như `BodyHandlers.ofInputStream()`, Future có thể hoàn tất **trước khi stream body được đọc hết**. Nếu nhả permit ngay lúc có `HttpResponse<InputStream>`, limit chỉ còn khống chế giai đoạn nhận headers/khởi tạo stream, **không khống chế số active downloads**. Trong trường hợp streaming, giữ slot tới khi consumer đọc xong/đóng stream hoặc dùng cơ chế accounting riêng.

**Invariant phải giữ:**

~~~text
0 <= inFlight <= MAX_IN_FLIGHT

slot lấy trước submit
slot trả đúng một lần khi terminal outcome
không lấy slot --> không submit
slot đã nhả --> cho phép request tiếp theo
~~~

Một operation thất bại **vẫn phải trả slot**. Nếu callback chỉ nhả khi status 200, một lỗi 500 hoặc exception có thể khiến hệ thống kẹt mãi (permit leak).

## 3. Ba giới hạn khác nhau: concurrency, rate và hàng đợi

| Loại giới hạn | Ví dụ | Điều kiểm soát | Không thay thế cho |
| --- | --- | --- | --- |
| **Concurrency limit** | Tối đa 3 HTTP requests in-flight | Bao nhiêu operation cùng đang chờ network/response | Rate limit dài hạn và backlog |
| **Rate limit** | Tối đa 20 request/giây | Tốc độ trung bình/phát request theo thời gian | Số outstanding khi server phản hồi chậm |
| **Backlog / queue bound** | Tối đa 100 jobs chờ | Số công việc chưa được gửi đang giữ trong bộ nhớ | Concurrency đang hoạt động |

Giới hạn 3 requests không đảm bảo tối đa 3 requests/giây: nếu server trả nhanh, một giây có thể hoàn thành rất nhiều requests. Ngược lại, rate limit 20 requests/giây không đảm bảo chỉ có ít requests in-flight: khi mỗi request chờ 30 giây, nhiều yêu cầu vẫn tích tụ.

Một pipeline an toàn thường kết hợp:

~~~text
Incoming work
      |
      v
[bounded backlog <= Q] -- full --> wait / reject / shed load
      |
      v
[rate limiter if remote API has RPS quota]
      |
      v
[concurrency limiter <= K]
      |
      v
   HttpClient.sendAsync(...)
      |
      v
   response or error
      |
      +-----> release K slot
      +-----> record metrics / result
~~~

Việc giảm request concurrency **không đủ** khi một producer có thể nhét hàng triệu jobs vào queue chờ. Nếu công việc được lưu bền trên DB/message broker, dispatcher có thể chỉ load một batch nhỏ vào RAM. Nếu là stream trực tiếp, có thể dùng backpressure cho upstream hoặc trả `429`/`503` khi queue đầy theo SLA.

## 4. Vì sao giới hạn thread pool không đủ?

Một ngộ nhận phổ biến là:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(3);
HttpClient client = HttpClient.newBuilder()
        .executor(pool).build();
~~~

Đây là snippet minh họa và **không phải** concurrency limiter cho HTTP requests. `HttpClient.Builder.executor(...)` chỉ cung cấp executor cho những tác vụ asynchronous/dependent mà client triển khai theo contract; `sendAsync` vẫn có thể được gọi **rất nhiều lần** trước khi các tasks hoàn tất. Ngoài ra:

- Một request HTTP có thể đang chờ I/O mà không chiếm một platform thread trong toàn bộ khoảng chờ.
- HTTP/2 có thể multiplex nhiều streams trên một kết nối.
- `newFixedThreadPool(3)` giới hạn worker threads của executor, **không tự bảo đảm chỉ có ba network operations outstanding**.
- Default `newFixedThreadPool` dùng **hàng đợi công việc không bị chặn kích thước**, nên bản thân queue có thể phình nếu submit quá nhiều tasks.
- Với `CompletableFuture.thenApplyAsync(...)` mà không chỉ định executor, Java có thể sử dụng `ForkJoinPool.commonPool()`; chuyện này cũng không tạo concurrency cap cho HTTP requests.

**Giải pháp:** đặt giới hạn **trước khi submit `sendAsync`**, hoặc điều khiển một cửa sổ request đang in-flight. Executor có thể được dùng bổ trợ để chạy callback/CPU tasks nhưng không thay thế **admission control**.

## 5. Mẫu đơn giản: Semaphore cấp permits cho những request đang chạy

`java.util.concurrent.Semaphore` duy trì số permits. Khi tạo:

~~~java
Semaphore permits = new Semaphore(3);
~~~

chỉ có tối đa ba luồng/đơn vị công việc có thể giữ permit cùng lúc, nếu **mọi đường submit đều tuân thủ** cùng Semaphore.

Luồng hợp lệ:

~~~text
Producer                Semaphore(3)             HttpClient
   |                         |                      |
   | acquire()               |                      |
   |------------------------>| take 1               |
   |                         |                      |
   | sendAsync() ----------------------------------> |
   |                         |                      |
   | attach completion callback                      |
   |                         |          HTTP in-flight ...
   |                         |                      |
   |                   whenComplete                  |
   |                         | <--- completed/failed |
   |                         |                      |
   | <--- callback releases  | permit returned      |
   |                         |                      |
   +----> next request (if any)                      |
~~~

Ưu điểm: rất dễ hiểu, không cần quản lý queue phức tạp cho một producer chạy trong **thread chuyên dụng**.

Lưu ý:
- **`acquire()` block thread producer** khi hết slot. Đừng gọi nó trực tiếp trên UI thread, selector event loop, hoặc callback thread đang cần tiến triển để trả permits.
- Có thể dùng `tryAcquire(timeout, unit)` để từ chối/chờ có thời hạn khi hạn mức đầy.
- Có thể cấu hình `new Semaphore(K, true)` (fairness) nếu thứ tự chờ cần gần FIFO; `tryAcquire()` không thời hạn có semantics fairness riêng theo Javadoc.
- Một permit do request nào giữ được thì **trả đúng một lần** sau khi operation terminal. Nếu `sendAsync` ném RuntimeException ngay lúc khởi tạo, phải trả permit ở nhánh catch.
- Nếu một request bị timeout hoặc cancel, **không** tùy tiện `release` khi I/O vẫn còn thật sự chạy; phải xác định chính sách hủy và terminal state để giữ nghĩa concurrency cap.
- Producer không cần lưu **mọi Future**: có thể giữ một `CountDownLatch` cho batch hữu hạn hoặc bộ đếm/streaming result sink.

## 6. Ví dụ hoàn chỉnh 1 — Semaphore chặn producer, tối đa 3 HTTP requests

Chương trình **`SemaphoreHttpDemo.java`** gửi tổng cộng **12 GET requests** đến HTTP server local. Server trả `"item-N"` với độ trễ nhỏ để tạo overlap. Client khởi tạo request bất đồng bộ nhưng producer gọi `permits.acquire()` trước mỗi lần submit.

Cấu trúc:
- Một `HttpClient` được tái sử dụng cho tất cả requests.
- Một `Semaphore(3)` cấp đúng ba permits cho request đang in-flight.
- `AtomicInteger active` theo dõi operations đã submit mà callback chưa hoàn tất; `peak` ghi mức cao nhất đã quan sát.
- `whenComplete(...)` kiểm tra status/body, và trong `finally` luôn giảm counter, trả permit và đếm `CountDownLatch`.
- Không có `List<CompletableFuture<?>>` gồm 12 phần tử; Futures không được giữ sau khi callback đã đăng ký.
- Nếu lời gọi `sendAsync` ném đồng bộ, nhánh `catch(RuntimeException)` vẫn dọn slot.

Tạo file **`SemaphoreHttpDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreHttpDemo {
    static void reply(HttpExchange exchange) throws IOException {
        try {
            Thread.sleep(60); // Chỉ để mô phỏng server xử lý một lúc.
            String suffix = exchange.getRequestURI().getPath()
                    .substring("/item/".length());

            byte[] body = ("item-" + suffix)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            exchange.close();
        }
    }

    public static void main(String[] args) throws Exception {
        final int total = 12;
        final int limit = 3;

        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverWorkers);
        server.createContext("/item/", exchange -> {
            try {
                reply(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            int port = server.getAddress().getPort();
            Semaphore permits = new Semaphore(limit);
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();
            AtomicInteger succeeded = new AtomicInteger();
            AtomicInteger failed = new AtomicInteger();
            CountDownLatch done = new CountDownLatch(total);

            for (int id = 1; id <= total; id++) {
                // Chặn CHỈ producer thread nếu đủ 3 requests in-flight.
                permits.acquire();

                int item = id;
                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);

                try {
                    HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/" + item))
                            .timeout(Duration.ofSeconds(3))
                            .GET()
                            .build();

                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                            .whenComplete((response, error) -> {
                                try {
                                    if (error == null
                                            && response.statusCode() == 200
                                            && ("item-" + item)
                                            .equals(response.body())) {
                                        succeeded.incrementAndGet();
                                    } else {
                                        failed.incrementAndGet();
                                    }
                                } finally {
                                    active.decrementAndGet();
                                    permits.release();
                                    done.countDown();
                                }
                            });

                } catch (RuntimeException e) {
                    // Chỉ xử lý lỗi xảy ra khi tạo/submit request.
                    failed.incrementAndGet();
                    active.decrementAndGet();
                    permits.release();
                    done.countDown();
                }
            }

            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }

            System.out.println("Total requests: " + total);
            System.out.println("Successful: " + succeeded.get());
            System.out.println("Failed: " + failed.get());
            System.out.println("Peak <= limit: " + (peak.get() <= limit));
            System.out.println("Active after completion: " + active.get());

        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 SemaphoreHttpDemo.java
java SemaphoreHttpDemo
~~~

**Đầu ra trên môi trường localhost hoạt động bình thường:**

~~~text
Total requests: 12
Successful: 12
Failed: 0
Peak <= limit: true
Active after completion: 0
~~~

### Điều gì đảm bảo không vượt quá 3?

1. `permits.acquire()` xảy ra **trước** `sendAsync`.
2. Khi ba requests chưa terminal, `Semaphore` còn 0 permits, producer dừng ở `acquire`; không submit request thứ tư.
3. Callback `whenComplete` chạy dù Future normal hay exceptional, vì vậy nhánh `finally` trả permit.
4. Producer nhận permit trở lại mới gửi thêm request.
5. Vì có một producer duy nhất và mỗi request thành công lấy/trả đúng một permit, `active` không vượt `limit`.

**Điều gì không được đảm bảo?**
- Không có bảo đảm **`peak == 3`** trên mọi máy: network/server có thể hoàn tất nhanh trước khi đạt ba outstanding.
- Không có bảo đảm HTTP server thực thi đồng thời ba handler tại mọi thời điểm: server fixture có pool 4 threads nhưng scheduler có thể chạy theo thứ tự khác.
- Không chứng minh thông lượng production tốt nhất ở `K=3`.
- Không đảm bảo remote xử lý hoàn toàn chỉ một lần nếu có redirect/retry ở tầng giao thức hoặc ứng dụng.
- `done.await(10, SECONDS)` là timeout ở thread chờ; nếu timeout ném exception thì server đóng trong `finally`, **không** nên diễn giải rằng mọi operation HTTP đã bị dừng tức thì.

**Quan trọng về thực tế:** Code này là mô hình **bounded producer** và dùng một thread có thể block trên `acquire()`. Không đưa nguyên vòng submit vào `CompletableFuture.whenComplete(...)` của một HTTP client có completion threads hạn chế rồi block trên semaphore: nếu callback bị kẹt chờ permit nhưng chính callback cần được thực thi để release, dễ gây starvation/deadlock. Ví dụ 2 xử lý bằng cửa sổ bất đồng bộ.

## 7. Sliding window: tránh producer block và tránh tạo mọi Future

Nếu thread gọi gửi HTTP là event loop, một API async hoặc pipeline có nhiều producer, ta có thể dùng **window scheduler**:

~~~text
Tổng 12 công việc, giới hạn K=3

Cửa sổ lúc đầu:
    [request 1]  [request 2]  [request 3]

request 2 hoàn tất:
    [request 1]  [request 4]  [request 3]

request 1 hoàn tất:
    [request 5]  [request 4]  [request 3]

request 4 hoàn tất:
    [request 5]  [request 6]  [request 3]

... tiếp tục cho tới khi hết công việc.

Số Future đang được giữ để quản lý HTTP active
không vượt quá K theo invariant của application scheduler.
~~~

**Thuật toán:** Ban đầu gửi tới `K` requests. Mỗi khi một Future hoàn tất, một callback:
1. Ghi nhận kết quả/lỗi.
2. Giảm biến đếm in-flight.
3. Lấy job kế tiếp từ nguồn (nếu còn) và submit để bù một slot.
4. Khi hết nguồn và in-flight bằng 0 thì báo hoàn thành.

Với việc đồng bộ trạng thái, dùng một **single-thread dispatcher** sở hữu `nextId`, `active`, result counters. Completion callback của `HttpClient` chỉ **enqueue một sự kiện ngắn** tới dispatcher; không tự sửa các counters hoặc submit lại từ nhiều threads cùng lúc.

**Lợi ích:** Không cần producer block trên semaphore; tối đa `K` network requests được khởi tạo và chưa được ghi nhận terminal. Nguồn công việc có thể là iterator/DB cursor; không nhất thiết materialize một danh sách `CompletableFuture` dài bằng số jobs.

**Cảnh báo về nguồn dữ liệu liên tục:** Bản demo có đúng 12 job, không có backlog ngoài. Trong server production, dispatcher chỉ giải quyết “số in-flight”; input queue từ API/Kafka/DB vẫn phải có giới hạn riêng.

## 8. Ví dụ hoàn chỉnh 2 — event dispatcher giữ tối đa 3 request

Chương trình **`AsyncWindowDemo.java`** giữ window size = 3. Nó khác ví dụ Semaphore:
- `Window.start()` chỉ enqueue lần chạy đầu vào một executor đơn luồng.
- `fill()` submit thêm request **chỉ khi `active < LIMIT`**.
- Callback `whenComplete` gọi `events.execute(...)` để việc cập nhật state luôn thực hiện trên **thread dispatcher duy nhất**.
- `fill()` chạy lại sau mỗi completion, không giữ toàn bộ Future, không dùng `Semaphore.acquire()`.
- Một `CountDownLatch(1)` cho main chờ khi tất cả đã terminal; không có `CountDownLatch(12)` hoặc array of futures là điều kiện bắt buộc.
- Một request báo HTTP status khác 200 hoặc Future lỗi đều được tính thất bại rồi giải phóng slot, tránh starvation.

Tạo file **`AsyncWindowDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class AsyncWindowDemo {
    static final int TOTAL = 12;
    static final int LIMIT = 3;

    static final class Window {
        final HttpClient client;
        final int port;

        // CHỈ dispatcher thread sửa các fields phía dưới.
        final ExecutorService events =
                Executors.newSingleThreadExecutor();
        final CountDownLatch finished = new CountDownLatch(1);

        int next = 1;
        int active = 0;
        int peak = 0;
        int succeeded = 0;
        int failed = 0;

        Window(HttpClient client, int port) {
            this.client = client;
            this.port = port;
        }

        void start() {
            events.execute(this::fill);
        }

        void fill() {
            while (active < LIMIT && next <= TOTAL) {
                final int id = next++;
                active++;
                peak = Math.max(peak, active);

                try {
                    HttpRequest request = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/" + id))
                            .timeout(Duration.ofSeconds(3))
                            .GET()
                            .build();

                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8))
                            .whenComplete((resp, error) ->
                                    events.execute(() -> {
                                        active--;
                                        if (error == null
                                                && resp.statusCode() == 200
                                                && ("item-" + id)
                                                .equals(resp.body())) {
                                            succeeded++;
                                        } else {
                                            failed++;
                                        }
                                        fill();
                                    }));

                } catch (RuntimeException ex) {
                    // Nếu khởi tạo/submit lỗi đồng bộ, xử lý qua
                    // cùng dispatcher, không để active bị kẹt.
                    events.execute(() -> {
                        active--;
                        failed++;
                        fill();
                    });
                }
            }

            if (next > TOTAL && active == 0) {
                finished.countDown();
            }
        }
    }

    static void reply(HttpExchange ex) throws IOException {
        try {
            Thread.sleep(60);
            byte[] body = ("item-" + ex.getRequestURI().getPath()
                    .substring("/item/".length()))
                    .getBytes(StandardCharsets.UTF_8);
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            ex.close();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService serverWorkers =
                Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverWorkers);
        server.createContext("/item/", ex -> {
            try {
                reply(ex);
            } catch (IOException e) {
                ex.close();
            }
        });
        server.start();

        Window window = null;
        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            window = new Window(client, server.getAddress().getPort());
            window.start();

            if (!window.finished.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out");
            }

            System.out.println("Submitted: " + (window.next - 1));
            System.out.println("Succeeded: " + window.succeeded);
            System.out.println("Failed: " + window.failed);
            System.out.println("Max active <= limit: "
                    + (window.peak <= LIMIT));
            System.out.println("Remaining active: " + window.active);

        } finally {
            if (window != null) {
                window.events.shutdownNow();
            }
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac -encoding UTF-8 AsyncWindowDemo.java
java AsyncWindowDemo
~~~

Đầu ra khi máy cho phép TCP loopback:

~~~text
Submitted: 12
Succeeded: 12
Failed: 0
Max active <= limit: true
Remaining active: 0
~~~

### Vì sao đây là “async sliding window”?

- `fill()` ở dispatcher chạy nhanh để submit tối đa ba requests; nó **không chờ network bằng `Future.get()` hoặc `Semaphore.acquire()`**.
- Khi HTTP operation hoàn thành, `whenComplete` được gọi; callback này **không chỉnh state trực tiếp** mà chỉ submit `onCompletion` logic vào `events`.
- Vì chỉ dispatcher được sửa `active` và `next`, invariant có thể kiểm tra bằng mã tuần tự, tránh race giữa các callbacks.
- `active--` và xử lý kết quả diễn ra **trước** `fill()`; một slot vừa được giải phóng có thể sử dụng ngay cho item tiếp theo.
- `finish.countDown()` (trong code là `finished.countDown()`) chỉ xảy ra khi **đã submit hết 12 items và active == 0**.
- Không có danh sách 12 Futures; lifetime của các Future chưa hoàn tất gắn với HTTP client/provider và callback của từng operation, còn dispatcher chỉ có số lượng operation cần thiết đang in-flight.

**Một số giới hạn của demo:** `events` là một executor riêng cho đúng một window để tiện trình bày; production có thể dùng một event loop chung hoặc một dispatcher cho nhiều windows. Nếu dừng dispatcher khi callbacks vẫn có thể gọi `events.execute`, callback có thể nhận `RejectedExecutionException`; cần shutdown protocol, drain/cancel, timeout và state CLOSED rõ ràng. Ví dụ chỉ shutdown sau khi `finished` đã về 0 trên đường chạy thành công và không đưa việc kiểm soát retry/cancel phức tạp vào bài thực hành.

### So sánh với Semaphore

| Tiêu chí | Semaphore producer | Async window dispatcher |
| --- | --- | --- |
| Lấy slot | `permits.acquire()` trước `sendAsync` | `fill()` chỉ submit khi `active < LIMIT` |
| Khi hết slot | **Block** producer thread | Return; callback completion kích hoạt request tiếp |
| Thread quản lý trạng thái | Producer + callbacks, dùng AtomicInteger/Semaphore | Một dispatcher thread sở hữu state |
| Phù hợp | Batch nhỏ/vừa, producer riêng có thể chờ | Async service/event loop, nguồn jobs có iterator |
| Futures cần giữ | Không cần giữ toàn bộ; handler nhận completion | Không cần giữ toàn bộ; chỉ active window |
| Rủi ro | Block event-loop nếu dùng sai chỗ | Phải quản lý dispatcher shutdown và event ordering |

Không cần kết hợp cả hai cùng lúc cho mọi hệ thống. Dùng một admission-control model nhất quán, dễ quan sát, phù hợp lifecycle ứng dụng.

## 9. Micro-batch có giới hạn: cách đơn giản nhưng tạo khoảng trống

Một cách khác là chia công việc thành **batch có size K**, gửi cùng lúc `K` requests, đợi cả batch hoàn tất rồi mới sang batch tiếp. Ví dụ **pseudocode**:

~~~text
for each batch of K jobs:
    futures = submit each job in batch using sendAsync
    await CompletableFuture.allOf(futures)
    handle results, successes, errors
    clear references
~~~

Ưu điểm: rất đơn giản, tối đa `K` in-flight, số Future giữ trong RAM cũng chỉ tương ứng một batch. Nhược điểm: khi một request trong batch chậm, các requests khác đã xong **không được thay bằng job mới** cho tới khi cả batch kết thúc. Đây là **head-of-line blocking ở mức batch**, không phải lỗi HTTP.

**Sliding window** tận dụng slot ngay khi có completion riêng lẻ, nên thường giữ concurrency ổn định hơn khi latency không đồng đều. Với N rất nhỏ, micro-batch vẫn có thể là lựa chọn hợp lý và đơn giản.

**Không nhầm:** Việc **lập danh sách tất cả N futures rồi gọi allOf một lần** không phải micro-batch. Batch phải được submit từng nhóm có **giới hạn kích thước**, và chỉ chuyển sang nhóm tiếp sau khi nhóm trước đã được xử lý.

## 10. Callback phải release slot trên mọi đường kết thúc

Một mẫu lỗi gây treo hệ thống:

~~~java
// PHẢN VÍ DỤ — không release khi response lỗi.
client.sendAsync(request, BodyHandlers.ofString())
        .thenAccept(response -> {
            if (response.statusCode() == 200) {
                permits.release();
            }
        });
~~~

Nếu Future hoàn tất lỗi, `thenAccept` sẽ không được gọi. Nếu HTTP status là 429, 500 hoặc 404, callback có thể chạy nhưng không release. Sau khi đủ `K` permits bị giữ, tất cả request tương lai có thể dừng ở admission control.

Mẫu chính xác hơn:

~~~java
permits.acquire();
try {
    client.sendAsync(request, BodyHandlers.ofString())
            .whenComplete((response, error) -> {
                try {
                    if (error != null) {
                        recordFailure(error);
                    } else {
                        handleHttpStatus(response.statusCode());
                    }
                } finally {
                    permits.release();
                }
            });
} catch (RuntimeException submitFailure) {
    permits.release();
    throw submitFailure;
}
~~~

Đây là **snippet**, cần `client`, `request`, `permits` và hai hàm nghiệp vụ `recordFailure`, `handleHttpStatus` đã khai báo. Nếu `whenComplete` được gắn thành công, chính callback sở hữu nghĩa vụ release; nhánh catch chỉ áp dụng cho lỗi khởi tạo/submit đồng bộ. **Không release lần thứ hai ở một chỗ khác** khi callback cũng chạy.

**Dấu hiệu tốt:** `inFlight = submitted - terminalCallbacks`, theo accounting của ứng dụng, phải luôn nằm trong dải 0..K. Nếu sau khi hết jobs mà `inFlight != 0`, hãy tìm permit leak, callback bị chặn, Future chưa terminal hoặc shutdown sai.

## 11. Vì sao không block trong callback hoặc event loop?

`CompletableFuture.whenComplete(...)` không nhất thiết chạy trên một thread riêng dành cho việc của bạn; Java có thể thực thi dependent non-async actions ngay trên thread hoàn tất Future hoặc thread gọi method tương ứng. Vì vậy:

~~~java
// KHÔNG NÊN: callback completion có thể chặn đợi permit.
future.whenComplete((result, error) -> {
    permits.acquireUninterruptibly();
    submitMoreWork();
});
~~~

Đoạn trên là **phản ví dụ**. Nếu các completion threads bị chiếm để chờ permit, còn logic trả permit cũng cần completion callback, có thể gây starvation/deadlock. Tránh:
- Gọi `Thread.sleep` dài, truy vấn DB blocking hoặc CPU công việc lớn trong callback chạy trên I/O/completion threads.
- Chờ `join()/get()` của Future khác khi làm việc đó ngăn các Futures ấy hoàn thành.
- Gọi `Semaphore.acquire()` trong một thread không được phép block, như JavaFX UI hoặc selector/event loop.

Thay bằng:
1. **Callback ngắn** chỉ ghi nhận terminal outcome và phát event cho scheduler.
2. Đưa business logic nặng tới executor có giới hạn và queue có giới hạn.
3. Dùng một event-loop/actor sở hữu state, hoặc synchronization cẩn thận nếu có nhiều producers.
4. Với việc tiếp tục bằng `thenApplyAsync/whenCompleteAsync`, **chọn executor và bounded queue phù hợp**; đừng giả định async callback tự nhiên miễn phí.

Nếu business work (ví dụ parse 10 MB JSON) cũng cần bị giới hạn, tạo **budget riêng cho post-processing**. Khi bạn release HTTP permit trước khi xử lý logic nặng, HTTP concurrency vẫn được bảo vệ nhưng CPU/backlog có thể tăng; tách metrics và budgets cho từng tầng.

## 12. Với streaming body, khi nào nhả permit?

Hai ví dụ dùng `BodyHandlers.ofString(UTF_8)`. Với handler này, `HttpResponse<String>` đã có body text theo contract trước khi Future hoàn tất; slot giữ tới callback có thể đại diện cho thời gian download của response.

Nhưng với:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, BodyHandlers.ofInputStream());
~~~

Future có thể hoàn tất khi response headers có, trong khi `InputStream` còn dữ liệu **chưa đọc**. Nếu nhả một permit ngay khi future.complete, bạn có thể mở rất nhiều download streams mà không bị số permit chặn.

Mẫu đúng về ý tưởng (pseudocode):

~~~text
acquire download slot
sendAsync(..., ofInputStream())
when response stream becomes available:
    hand off stream to a bounded consumer executor
    consumer reads/copies with byte limits and timeout
    finally:
        close stream
        release download slot
if sendAsync failed before stream exists:
    release download slot
~~~

Đây không phải full runnable Java code; dùng để chỉ ra **lifetime** của tài nguyên, không phải chỉ một API method. Với `BodyHandlers.ofFile(path)`, Future thành công thường biểu thị body đã ghi vào file, nhưng bạn vẫn phải cleanup file partial khi gặp lỗi và giữ quota disk riêng. Với `BodyHandlers.discarding()`, không giữ body nhưng vẫn có I/O, nên cũng phải limit in-flight nếu gọi API hàng loạt.

## 13. Giới hạn theo host, tenant và tổng hệ thống

Một `Semaphore(10)` global giới hạn tối đa 10 jobs HTTP của **toàn ứng dụng**, nhưng một service có thể phải gọi nhiều loại endpoint với SLA khác nhau:

~~~text
                     Global budget: 20
                           |
            +--------------+--------------+
            |              |              |
       Service A        Service B      Service C
       per-host 5       per-host 8     per-host 7
            |              |              |
         sendAsync       sendAsync       sendAsync
~~~

Một thiết kế có thể dùng:
- **Global** concurrency limit bảo vệ RAM, file descriptors và tổng khả năng gửi.
- **Per-host/per-service** limit để một downstream chậm không chiếm toàn bộ slots.
- **Per-tenant** limit để tránh một người dùng độc chiếm dung lượng.
- **Rate limiting** theo API quota của provider (requests/second hoặc token bucket).
- **Bộ đếm byte/body** tách khỏi request count khi payload khác nhau rất nhiều.

**Tránh deadlock khi lấy nhiều permits:** Chọn một thứ tự acquire nhất quán, release chắc chắn, hoặc dùng một scheduler thống nhất cấp cả hai ngân sách cùng lúc. Không để luồng A giữ global permit rồi chờ host permit trong khi một thao tác khác giữ host permit và chờ global theo chiều ngược lại.

**Tránh starvation:** Một queue công bằng hoặc scheduler theo tenant có thể cần thiết nếu một host nhanh luôn “cướp” slots của host chậm. Semaphore có tùy chọn fairness, nhưng fairness của một semaphore không tự giải quyết mọi chính sách ưu tiên/hạn mức nghiệp vụ.

## 14. Chọn K dựa trên latency, throughput và tài nguyên

Không có giá trị `K` tốt nhất cho mọi hệ thống. Cần xem:
- Thời gian request trung bình và P95/P99.
- Kích thước response, kiểu BodyHandler và heap/disk budget.
- Quota/rate-limit của remote API.
- HTTP protocol behavior, connection reuse, HTTP/2 multiplexing.
- Chi phí TLS/DNS/proxy và giới hạn connection/file descriptor.
- Khả năng downstream và CPU xử lý body.

Một công thức trực giác từ **Little’s Law**, khi hệ thống tương đối ổn định:

\[
L \approx \lambda W
\]

Trong đó:
- `L`: số requests trung bình đang in-flight.
- `λ`: số requests hoàn tất trung bình mỗi giây.
- `W`: thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ *minh họa*, nếu mục tiêu là 40 requests/giây và thời gian hoàn tất trung bình là 0,2 giây, số request concurrent trung bình cỡ `40 × 0,2 = 8`. Đó **không phải khuyến nghị máy móc chọn K=8**: P99 latency, spikes, retries, connection setup, queueing và budget RAM có thể đòi hỏi giá trị khác.

**Tuning an toàn:**
1. Bắt đầu với một `K` bảo thủ theo hạn mức API và tài nguyên.
2. Đo in-flight, completion rate, queue wait time, P50/P95/P99 latency, 429/503/5xx, timeouts, heap và CPU.
3. Tăng dần khi throughput thật sự cải thiện mà error/latency không tăng bất thường.
4. Giảm khi thấy rate limiting, tăng queue wait, lỗi hoặc tải xuống vượt budget.
5. Có thể cân nhắc adaptive concurrency, nhưng vẫn cần upper bound cứng và chính sách ổn định.

**Concurrency cap không thay circuit breaker.** Khi downstream liên tục lỗi, một circuit breaker có thể ngừng gửi trong một khoảng thời gian, còn concurrency cap chỉ giới hạn số operations đang đi qua.

## 15. Backpressure: không dồn công việc chờ vào RAM

Một semaphore với `acquire()` sẽ chặn producer, nhưng nếu producer **đã** đọc toàn bộ 1 triệu jobs vào `List` thì bạn vẫn tiêu tốn bộ nhớ. Tương tự, sliding window giới hạn request in-flight nhưng không bảo vệ một `ConcurrentLinkedQueue` vô hạn phía trước.

Chính sách xử lý khi full:

| Chính sách | Cơ chế | Dùng khi |
| --- | --- | --- |
| Backpressure lên producer | Không đọc thêm jobs từ upstream khi hết slot/queue đầy | Streaming iterator, batch loader, message broker có pause |
| Bounded queue | Chỉ giữ tối đa Q job metadata; producer chờ hoặc bị từ chối | Service có luồng công việc liên tục |
| Fail fast / shed load | Trả 429/503 hoặc kết quả “busy” | API không thể chờ vô hạn và cần bảo vệ SLA |
| Durable queue | Lưu job ra broker/DB và chỉ đọc batch nhỏ | Công việc dài, cần retry/recovery |
| Coalescing/dedup | Gộp nhiều yêu cầu giống nhau | Refresh/cache/polling cùng resource |

**Không cần một future cho mọi job** chỉ để “nhớ sẽ xử lý”. Trạng thái chờ có thể ở iterator, broker hoặc bảng DB. Chỉ khi slot trống mới tạo `HttpRequest` và `sendAsync` theo bộ đếm được kiểm soát.

Với scheduler không giới hạn nguồn đầu vào, cần đảm bảo cơ chế nhận job **dừng hoặc trả lỗi khi queue đầy**. Không tạo một `CompletableFuture` chưa hoàn tất cho từng job rồi treo hàng triệu future ở queue nội bộ; điều đó vẫn là một loại unbounded memory growth.

## 16. Timeout, cancellation và điều kiện terminal

**Timeout của `HttpRequest`:**

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Giúp operation không chờ vô hạn theo request timeout policy (kết quả lỗi có thể là `HttpTimeoutException`). Ngoài ra cấu hình connect timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

**`CompletableFuture.orTimeout(...)` khác request timeout.** Nó biến Future thành exceptional completion sau thời hạn nếu chưa xong, nhưng không nên coi đây là bằng chứng remote đã dừng xử lý hoặc mọi network/tài nguyên đã lập tức được giải phóng. Tương tự `future.cancel(...)` ảnh hưởng Future completion/cancellation theo implementation và không phải giao thức “rollback HTTP request”.

Quyết định **khi nhả slot** tùy semantics:
- Với `sendAsync(..., BodyHandlers.ofString())` và callback terminal, slot đại diện cho request đến khi toàn body response đã được xử lý.
- Với `ofInputStream`, phải tính thêm giai đoạn consumer đọc/đóng body.
- Nếu hủy request, app phải có shutdown/cancel protocol rõ ràng, theo dõi thực tế active network resources, tránh nhả slot quá sớm rồi cho phép vượt K requests còn thực sự chạy.
- Khi dùng retry, lựa chọn budget: giữ **cùng logical slot** trong toàn bộ chuỗi attempts, hoặc trả slot giữa attempts nhưng đưa retry vào queue **có giới hạn**. Cách nào cũng phải chống double release và retry storm.

**HTTP status không phải exceptional completion mặc định.** Một response 429/500 hợp lệ vẫn là `HttpResponse<T>`; callback `error == null` nhưng application phải kiểm tra `statusCode()` để biết nghiệp vụ thất bại. Nếu đợi Future bằng `join()` thì `CompletionException` bọc lỗi; với `get()` là `ExecutionException`. Không nuốt nguyên nhân gốc.

## 17. Cần tính cả retry và redirects như thế nào?

Giới hạn “3 logical requests” không bảo đảm “chính xác 3 HTTP transmissions trong mọi khoảnh khắc”:
- Một request logic có thể follow redirect từ URL ban đầu sang URL khác.
- Authentication challenge có thể dẫn đến exchange bổ sung.
- Retry do ứng dụng hoặc implementation có thể tạo thêm attempt, tùy failure và policy.
- HTTP/2 có thể gửi nhiều streams trên một connection, HTTP/1.1 có mô hình sử dụng connection khác.

Với backoff:
- Khi một request thất bại 429/503, không retry lập tức và không bỏ qua hạn mức.
- Đọc `Retry-After` nếu service contract có quy định, giới hạn attempts và tổng deadline.
- Dùng idempotency key cho operations có side effects khi phía server hỗ trợ.
- Không tạo một Future mới cho mỗi attempt **ngoài admission-control** rồi coi là request độc lập hoàn toàn không có budget.

**Đề xuất:** coi `K` là budget của **các logical exchanges được ứng dụng quản lý**. Theo dõi riêng attempts, redirects và thực tế TCP/HTTP resources nếu SLA cần. Khi có retry scheduler, backoff queue cũng cần bounded capacity.

## 18. Lỗi đồng bộ khi submit và lỗi bất đồng bộ khi completion

`sendAsync` có thể thất bại theo hai thời điểm:

**A. Trước khi trả về Future**: tham số không hợp lệ hoặc một RuntimeException phát sinh ngay trong quá trình thiết lập call. Vì đã lấy permit rồi, code phải release trong `catch`.

**B. Sau khi đã trả về Future**: DNS, kết nối, TLS, timeouts, I/O, body processing... làm Future hoàn tất exceptional; callback `whenComplete((response, error) -> ...)` nhận `error != null`.

Điểm kiểm tra cần có ở cả hai:
- Mỗi request đã được cấp slot có **đúng một đường terminal cleanup**.
- Nhánh success kiểm tra HTTP status; `error == null` không đồng nghĩa status 2xx.
- Callback exceptions không được làm mất thao tác `release`; đặt release vào `finally`.
- Đừng release ở cả callback và catch cho **cùng một request đã được gắn callback thành công**.
- Với retry hoặc cancellation, xác định ai sở hữu cleanup (request state machine, không phải nhiều callbacks tự do).

Thêm metrics để thấy leaks:

~~~text
submitted        số requests đã thực sự khởi tạo
completed2xx     terminal HTTP status 2xx
completed4xx     terminal HTTP status 4xx
completed5xx     terminal HTTP status 5xx
failedTransport  Future exceptional / network error
inFlight         submitted - terminal callbacks
queueDepth       số jobs chưa gửi (giới hạn Q)
acquireWaitMs    thời gian chờ slot
peakInFlight     đỉnh active, phải <= K
~~~

Đối với ứng dụng lâu dài, lưu ý counters chỉ meaningful khi cùng một định nghĩa nghiệp vụ và cùng khoảng đo. Một request có thể có nhiều redirects/attempts nhưng một logical terminal callback.

## 19. Shutdown đúng cách khi còn HTTP requests đang chạy

Với Java 17, `HttpClient` **không có** phương thức lifecycle `close()`/`shutdown()` kiểu các JDK mới hơn. Không viết `try (HttpClient client = ...)` rồi khẳng định ví dụ Java 17 biên dịch được.

Khi cần dừng bounded scheduler:
1. Ngừng nhận jobs mới và đánh dấu state `CLOSING`.
2. Đừng submit requests mới từ callbacks sau khi shutdown bắt đầu.
3. Chờ các HTTP operations in-flight hoàn tất trong một grace period đã định.
4. Đặt timeout/cancel policy cho những công việc còn lại, nhưng không giả định cancel lập tức rollback network.
5. Đóng/kết thúc response streams và file downloads đang giữ tài nguyên.
6. Chỉ đóng dispatcher executor **sau** khi không còn callbacks cần enqueue kết quả hoặc đã có nhánh xử lý rejected submissions an toàn.
7. Flush metrics, thông báo kết quả thất bại/đã hủy và dọn bounded queue.

Trong `AsyncWindowDemo`, `finished.await(...)` đạt 0 trên đường thành công trước khi đóng dispatcher, cho phép ví dụ ngắn. Production cần xử lý thêm nhánh timeout/failure/shutdown: nếu gọi `events.shutdownNow()` khi HTTP completion callbacks còn đang `events.execute(...)`, các callbacks có thể bị `RejectedExecutionException` và công việc chưa được accounting. Đừng chỉ copy shutdown demo rồi dùng cho dịch vụ sống lâu.

## 20. Thử nghiệm giới hạn concurrency mà không phụ thuộc timing

Kiểm thử hữu ích nhất là **bất biến**, không phải thứ tự output:

- Tất cả jobs đã được submit/hoàn tất đúng một lần theo test fixture.
- Số active luôn nằm trong `0..K`.
- Peak observed `<= K`, kể cả khi mỗi request chậm hoặc lỗi.
- Các nhánh HTTP 200, 404, 429, 500 và transport error đều giải phóng slot.
- Không còn queued jobs không được submit khi mọi active jobs đã xong và producer đã đóng.
- Với source vô hạn, queueDepth không vượt Q.
- Kết thúc (shutdown) không để callbacks vô hạn giữ tham chiếu.
- Với body streaming, slot chỉ được release sau khi resource được consume/close theo định nghĩa.
- Nếu producer là event loop, test rằng admission control **không block** event-loop thread.

Các cách tạo test deterministic:
1. Server localhost dùng `CountDownLatch` để giữ một vài responses **chưa hoàn tất** thay vì phụ thuộc `Thread.sleep` để tạo đúng thứ tự.
2. Cho K jobs đầu vào và xác minh job K+1 chưa được submit khi các requests đầu chưa release.
3. Chủ động cho một response 500 và một request timeout để kiểm tra cleanup.
4. Dùng atomic counters gắn quanh admission/terminal callback và assert `max <= K`.
5. Với `ExecutorService`, mô phỏng callbacks trên nhiều threads để phát hiện race.
6. Không ép assertion `peak == K` trên mọi run của network test; nếu cần, kiểm soát server barrier/latch.

Hai demo ở đây dùng `Thread.sleep(60)` **chỉ để có overlap dễ quan sát**, nhưng stdout kiểm tra các invariant và số thành công; chúng không khẳng định thời gian/thứ tự hoàn thành nhất định.

## 21. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Submit N Future rồi `allOf` một lần | N requests có thể in-flight cùng lúc | Sliding window, Semaphore trước `sendAsync`, micro-batches |
| Nghĩ `sendAsync` tự giới hạn số requests | Client hoặc downstream quá tải | Tự đặt cap K và backlog Q |
| Chỉ giới hạn thread pool client | Vẫn có thể có nhiều requests waiting on I/O | Giới hạn application request operations |
| `Semaphore.acquire()` trong callback cần release permits | Starvation/deadlock | Producer riêng hoặc event dispatcher nonblocking |
| Chỉ `release()` khi HTTP 200 | Permit leak khi 404/500/exception | `whenComplete` + `finally` cho mọi terminal outcome |
| `release()` cả ở callback và catch sau khi callback đã nhận ownership | Double release, K bị vượt | Một owner cleanup, state machine rõ ràng |
| Xây unbounded queue phía trước Semaphore | OOM trước khi request được submit | Bounded queue/backpressure/reject |
| Giữ `List<Future>` của hàng triệu jobs | Giữ references/heap lâu | Window K, streaming result sink |
| Tin K requests = K TCP connections | Sai với HTTP/2, keep-alive và redirects | Phân biệt logical in-flight và transports |
| Dùng `thenApplyAsync` không giới hạn CPU work | Thread pool/queue quá tải | Bounded worker pool và separate budget |
| Release slot ngay khi `ofInputStream()` future xong | Nhiều active response streams vượt budget | Giữ slot đến khi stream đóng/tiêu thụ |
| Không tính request timeout | Jobs treo chiếm slot quá lâu | Timeout policy, cancellation/shutdown rõ ràng |
| Tưởng timeout/cancel đảm bảo remote dừng xử lý | Double-processing khi retry | Idempotency key, bounded attempts |
| Retry ngay mọi request status 500/429 | Retry storm | Exponential backoff + jitter + Retry-After |
| Không cleanup khi `sendAsync` throw đồng bộ | Permit bị mất, scheduler ngừng tiến | Catch release đúng một lần |
| Dispatcher shutdown khi callbacks vẫn đến | RejectedExecutionException, lost accounting | Graceful drain và CLOSED state |
| Dùng một cap toàn hệ thống cho nhiều tenant không công bằng | Tenant lớn chiếm slots | Per-tenant/per-host caps và fairness |
| In log body/secrets khi HTTP lỗi | Lộ thông tin nhạy cảm | Sanitize logs, giới hạn nội dung |

## 22. Bài tập tự kiểm tra

**1.** Vì sao `CompletableFuture.allOf(allFutures)` không giới hạn số HTTP requests concurrent?  
**Đáp án:** Vì tất cả `sendAsync` có thể đã được gọi và nhiều operations đang chạy trước khi `allOf` bắt đầu chờ. `allOf` chỉ gộp điều kiện hoàn tất.

**2.** Concurrency limit K=3 có phải tối đa 3 requests/giây không?  
**Đáp án:** Không. K giới hạn số outstanding ở cùng thời điểm; rate phụ thuộc latency và tốc độ hoàn tất.

**3.** Tại sao không chỉ đặt `HttpClient.Builder.executor(Executors.newFixedThreadPool(3))`?  
**Đáp án:** Giới hạn thread không đồng nghĩa giới hạn số HTTP operations in-flight hoặc hàng đợi; cần admission control riêng.

**4.** Cần lấy permit trước hay sau `sendAsync`?  
**Đáp án:** **Trước** khi submit. Lấy sau có thể cho phép hàng loạt requests khởi tạo vượt K.

**5.** `whenComplete` cần release permit ở những trường hợp nào?  
**Đáp án:** Mọi terminal outcomes: HTTP status 2xx, 4xx, 5xx và exceptional completion. Dùng `finally` để chắc chắn release.

**6.** Vì sao không block ở `Semaphore.acquire()` trong callback completion?  
**Đáp án:** Callback có thể chạy trên thread cần thiết để xử lý completion/release; chặn nó có thể gây starvation/deadlock.

**7.** Sliding window khác micro-batch thế nào?  
**Đáp án:** Sliding window bù slot ngay khi một request hoàn tất; micro-batch thường chờ cả nhóm trước khi submit nhóm kế.

**8.** Với `BodyHandlers.ofInputStream()`, Future xong đã chắc response body được nhận hết chưa?  
**Đáp án:** Chưa. Có thể chỉ mới nhận headers; phải giữ budget cho đến khi stream được tiêu thụ/đóng.

**9.** Khi producer có 1 triệu jobs nhưng K=3, có cần tạo 1 triệu Futures rồi để chúng chờ permit không?  
**Đáp án:** Không. Chỉ tạo/send request khi slot trống, giữ job còn lại ở nguồn/bounded queue/durable broker.

**10.** Có thể dùng một Semaphore global và một Semaphore per-host không?  
**Đáp án:** Có, nhưng phải tổ chức acquire/release cùng thứ tự hoặc dùng scheduler thống nhất, tránh deadlock và fairness issues.

**11.** Client nhận 429 trong HTTP response; Future mặc định có phải exceptional không?  
**Đáp án:** Không. Đó thường là response hợp lệ với `statusCode()==429`; cần tự quyết định retry/backoff và release slot đúng.

**12.** `future.cancel(true)` có chứng minh remote chưa xử lý POST không?  
**Đáp án:** Không. Cancellation là tín hiệu/lifecycle ở client; server có thể đã nhận và thực thi request.

**13.** Khi một callback throw exception trước khi release, hệ quả?  
**Đáp án:** Permit leak. Dùng `try/finally` hoặc state machine terminal cleanup bảo đảm release đúng một lần.

**14.** Làm sao test K không bị vượt mà không phụ thuộc timing?  
**Đáp án:** Dùng controlled server/latches để giữ K responses, xác minh request K+1 chưa submit, theo dõi atomic peak và thử các nhánh success/failure.

**15.** Vì sao kết quả peak in-flight có thể là 2 dù LIMIT=3?  
**Đáp án:** Một request có thể xong trước khi cả ba được submit hoặc concurrency thực tế thấp hơn; invariant quan trọng là `peak <= K`, không phải bắt buộc đạt K.

## Tài liệu chính thức và đọc thêm

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` trả `CompletableFuture<HttpResponse<T>>`, client reuse, cấu hình executor và HTTP requests.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout, URI, method, body publishers.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString` và streaming body handlers, khác nhau về completion/lifetime.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `whenComplete`, `allOf`, `join/get`, exceptional completion và cancellation.
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): permits, `acquire()`, `release()` và fairness.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): chờ một số terminal events.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): chạy tasks, shutdown và thread lifecycle.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): HTTP server localhost phục vụ hai chương trình test.
