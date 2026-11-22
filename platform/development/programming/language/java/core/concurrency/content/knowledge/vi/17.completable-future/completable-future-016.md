# Fan-out / fan-in thực hành với nhiều tác vụ I/O bằng CompletableFuture (Java 17+)

## 1. Bài toán và kết quả học tập

Một request cần lấy thông tin người dùng từ ba hệ thống: Profile, Orders và Inventory. Nếu gọi lần lượt và chờ từng kết quả, tổng latency gần bằng tổng thời gian các API. Nếu chúng độc lập, ta có thể phát ra cả ba yêu cầu I/O trước (**fan-out**) và chỉ tổng hợp khi có đủ những kết quả bắt buộc (**fan-in**).

~~~text
                    ┌─ HTTP /profile ────> Profile
Request ─ fan-out ───┼─ HTTP /orders ─────> Orders
                    └─ HTTP /inventory ──> Inventory
                                 │
                              fan-in
                                 │
                      Validate / aggregate
                                 │
                         DashboardResponse
~~~

Giả sử các nhánh độc lập mất 120, 180 và 90 ms. Đợi tuần tự có thể gần `120+180+90=390 ms`; fan-out rồi đợi đủ có thể gần `max(120,180,90)=180 ms` **cộng overhead**. Đây là ví dụ tư duy, không phải phép đo hoặc cam kết latency. Downstream connection limits, HTTP queueing, CPU, JSON parsing, contention và retries đều có thể thay đổi kết quả.

**Fan-out** là khởi động nhiều công việc có thể tiến triển đồng thời; **fan-in** là thu, kiểm tra và gộp outcomes theo một chính sách nhất định. Có bốn điểm dễ hiểu nhầm: tạo nhiều Future chưa chắc có nhiều I/O đang chạy; `allOf` không tự trả List; một nhánh lỗi không tự hủy mọi nhánh còn lại; timeout/cancel của CompletableFuture không tự rollback remote side effects.

Sau bài học, bạn có thể:
1. Vẽ dependency graph và chỉ fan-out những nhánh thật sự độc lập.
2. Dùng `CompletableFuture.supplyAsync` cho I/O blocking hoặc `HttpClient.sendAsync` cho HTTP bất đồng bộ thực sự.
3. Kết hợp `allOf`, `thenCombine`, `thenCompose` và hiểu kiểu trả về.
4. Quyết định required/optional/partial success, xử lý exception bằng `handle`, `exceptionally`, `whenComplete`.
5. Phân biệt `get(timeout)`, `orTimeout`, `completeOnTimeout`, HTTP request timeout và overall deadline.
6. Xử lý cancellation, late results, retries và idempotency.
7. Giới hạn fan-out bằng semaphore/bounded admission thay vì tạo vô hạn tác vụ.
8. Kiểm soát executor và tránh deadlock do block chờ trong cùng pool.
9. Chạy **bảy chương trình Java 17 độc lập**; trong đó có chương trình HTTP thật trên loopback, không phụ thuộc Internet.

**Phạm vi:** mục **CompletableFuture**, bài **Fan-out / fan-in thực hành với nhiều tác vụ I/O**, trong **Java Advance - concurrency**. Bài giải thích concurrency của Java SE nói chung; **không** dùng API hay cơ chế riêng của Spring vì chúng có chương riêng.

## 2. Vẽ đồ thị phụ thuộc trước khi viết code

Một graph độc lập:

~~~text
Profile ────────────┐
Orders  ────────────┼── allOf ──> Dashboard
Inventory ──────────┘
~~~

Với graph này, gửi cả ba request gần nhau có thể giảm thời gian chờ tổng. Đừng submit A, gọi `A.get()`, rồi mới submit B: đó là lập lịch tuần tự được bọc trong Future.

Một graph có dependency:

~~~text
fetchProfile
     |
     +── fetchOrders(profile.id) ──────┐
     |                                 +── Dashboard
     +── fetchStock(profile.region) ───┘
~~~

`fetchOrders` và `fetchStock` cần kết quả của profile, vì vậy phải đợi profile trước khi khởi động hai nhánh. Phần sau profile vẫn có thể fan-out. Dùng `thenCompose` để diễn đạt quan hệ phụ thuộc.

### Xác định success policy

| Chính sách | Khi nào hợp lý | Khi một nhánh lỗi |
| --- | --- | --- |
| All-required | Mọi nguồn là bắt buộc | Aggregate thất bại và có error rõ |
| Optional branch | Một phần có thể thiếu, ví dụ recommendations | Giữ status unavailable và fallback được xác định |
| Best effort | Có thể trả kết quả một phần trước deadline | Trả partial marker, không giả làm full result |
| First usable source | Có nhiều nguồn đọc thay thế nhau | Cần first **successful** result, không mặc định `anyOf` |
| Quorum k-of-n | Kết quả đủ khi k nguồn đồng thuận/thành công | Coordinator riêng; `allOf` không tự làm k-of-n |

Đây là quyết định nghiệp vụ. Không nên chuyển lỗi Orders thành `orders=0` nếu số 0 có nghĩa thật là khách hàng chưa đặt hàng.

## 3. Các phép toán CompletableFuture quan trọng

### allOf: đợi tất cả nhưng không gom value

~~~java
CompletableFuture<A> a = ...;
CompletableFuture<B> b = ...;
CompletableFuture<C> c = ...;

CompletableFuture<Void> all =
        CompletableFuture.allOf(a, b, c);
~~~

Đây là snippet với `A/B/C` và các futures đã định nghĩa. `allOf` hoàn tất khi các futures đầu vào hoàn tất; nếu bất kỳ future hoàn tất exceptionally, future tổng hợp cũng hoàn tất exceptionally. **Kiểu giá trị của allOf là `Void`**, không phải `List<A/B/C>`.

Thu kết quả sau khi tất cả thành công:

~~~java
CompletableFuture<Dashboard> dashboard =
        CompletableFuture.allOf(profile, orders, inventory)
                .thenApply(ignored -> new Dashboard(
                        profile.join(),
                        orders.join(),
                        inventory.join()));
~~~

Đây là snippet, record `Dashboard` và các futures có kiểu phù hợp. Vì callback `thenApply` chỉ chạy sau `allOf` thành công, các lời gọi `join` ở đó đọc kết quả đã hoàn tất; không biến nó thành việc chờ từng I/O tuần tự.

### thenCombine: hai nhánh độc lập

~~~java
CompletableFuture<Integer> total =
        price.thenCombine(shipping, Integer::sum);
~~~

Giả sử `price` và `shipping` đã bắt đầu độc lập. `thenCombine` đợi cả hai, rồi kết hợp. Nó **không tự submit** các suppliers ban đầu.

### thenCompose: nhánh tiếp theo phụ thuộc kết quả

~~~java
CompletableFuture<Order> order =
        fetchProfileAsync()
                .thenCompose(profile ->
                        fetchOrderAsync(profile.id()));
~~~

Đây là snippet với methods và classes đã được định nghĩa. `thenCompose` flatten future do callback trả về. Nếu thay bằng `thenApply`, kiểu thường thành `CompletableFuture<CompletableFuture<Order>>`, tức một future chứa future.

### Bảng các operator

| Nhu cầu | Operator |
| --- | --- |
| Ghép hai kết quả độc lập | `thenCombine` |
| Đợi N nhánh | `allOf` |
| Tác vụ sau cần output trước | `thenCompose` |
| Map một kết quả | `thenApply` |
| Dùng result hoặc exception để tạo result khác | `handle` |
| Recovery chỉ khi exception | `exceptionally` |
| Quan sát/log completion mà không mặc định recover | `whenComplete` |
| Timeout completion exceptional | `orTimeout` |
| Fallback value khi timeout | `completeOnTimeout` |
| First completion thành công **hoặc thất bại** | `anyOf` |

## 4. Ví dụ 1 — HTTP thật qua loopback với sendAsync và allOf

Ví dụ dùng `com.sun.net.httpserver.HttpServer` của JDK 17 để chạy ba endpoints trên `127.0.0.1` với port ngẫu nhiên. `java.net.http.HttpClient.sendAsync` phát ba HTTP requests, không phải chỉ mô phỏng bằng `Thread.sleep`. Không cần Internet hay API key.

**Tạo file `LocalHttpFanOutDemo.java`:**

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
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class LocalHttpFanOutDemo {
    static void reply(HttpExchange exchange, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    static CompletableFuture<HttpResponse<String>> request(
            HttpClient client, String url) {
        HttpRequest req = HttpRequest.newBuilder(
                URI.create(url)).GET().build();
        return client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        ExecutorService handlers = Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(handlers);

        server.createContext(
                "/profile", e -> reply(e, "user=42"));
        server.createContext(
                "/orders", e -> reply(e, "orders=3"));
        server.createContext(
                "/inventory", e -> reply(e, "stock=8"));

        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<HttpResponse<String>> profile =
                    request(client, base + "/profile");
            CompletableFuture<HttpResponse<String>> orders =
                    request(client, base + "/orders");
            CompletableFuture<HttpResponse<String>> inventory =
                    request(client, base + "/inventory");

            CompletableFuture<List<String>> dashboard =
                    CompletableFuture.allOf(
                            profile, orders, inventory)
                    .thenApply(ignored -> List.of(
                            profile.join().body(),
                            orders.join().body(),
                            inventory.join().body()));

            System.out.println("responses="
                    + dashboard.get(5, TimeUnit.SECONDS));
        } finally {
            server.stop(0);
            handlers.shutdownNow();
            handlers.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Biên dịch và chạy trên JDK 17+ với module jdk.httpserver:**

~~~bash
javac --add-modules jdk.httpserver LocalHttpFanOutDemo.java
java --add-modules jdk.httpserver LocalHttpFanOutDemo
~~~

Stdout khi loopback được phép và ba requests hoàn tất trong thời hạn:

~~~text
responses=[user=42, orders=3, stock=8]
~~~

Phân tích:
1. Port 0 để OS cấp port rảnh; response bodies là chuỗi cố định, giúp kiểm tra output.
2. Ba lời gọi `request(...)` được thực hiện trước `dashboard.get`, nên client khởi tạo ba requests bất đồng bộ trước điểm fan-in.
3. `sendAsync` trả futures chứa `HttpResponse<String>`; không giữ ba application worker threads chỉ để gọi `HttpClient.send` đồng bộ.
4. `allOf` là barrier; sau normal completion, `thenApply` đọc `body()` của ba response theo **thứ tự logic** cố định.
5. HTTP Inventory hoàn tất sớm hay muộn không đổi thứ tự `List`. Thứ tự response arrival không phải thứ tự thu kết quả.
6. Main dùng timed get 5 giây để tránh chờ vô hạn trong demo. Đây là timeout **caller đợi aggregate**, không tự cấp deadline hay hủy riêng cho từng HTTP request.
7. `finally` dừng loopback server và các handler threads; code Java 17 không gọi `HttpClient.close()` của các phiên bản JDK khác.

**Lưu ý môi trường:** Chương trình dùng socket loopback, nên một sandbox cấm mở port hoặc máy quá chậm có thể không chạy thành công. Dòng stdout nêu trên là kết quả với môi trường bình thường, không phải bảo đảm mọi CI.

### HTTP status không đồng nghĩa thành công

`HttpClient.sendAsync` có thể complete bình thường với status 404/500, vì nhận HTTP response thành công về mặt transport. Phải tự validate:

~~~java
CompletableFuture<String> text =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
              .thenApply(resp -> {
                  if (resp.statusCode() / 100 != 2) {
                      throw new IllegalStateException(
                              "HTTP " + resp.statusCode());
                  }
                  return resp.body();
              });
~~~

Đây là snippet có `client`, `request` đã định nghĩa. Trong production còn phải validate schema/JSON, content type, auth, body size, retryability và correlation ID. Nếu chỉ `allOf` rồi lấy `body()`, một HTTP 500 có thể bị coi nhầm như dữ liệu nghiệp vụ đúng.

## 5. Ví dụ 2 — Chứng minh ba công việc I/O chờ đồng thời bằng CountDownLatch

Ví dụ sau mô phỏng I/O để kiểm chứng **concurrency của các tasks**, không cần socket. Ba tasks đều vào vùng chờ trước khi main mở latch. Đây là test coordination, không phải phép đo tốc độ thật.

**Tạo file `SimulatedIoFanOutDemo.java`:**

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class SimulatedIoFanOutDemo {
    static String waitForRelease(
            CountDownLatch started,
            CountDownLatch gate,
            String value) {
        started.countDown();
        try {
            gate.await();
            return value;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new CompletionException(e);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(3);
        CountDownLatch started = new CountDownLatch(3);
        CountDownLatch gate = new CountDownLatch(1);

        try {
            CompletableFuture<String> a =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "profile"), io);
            CompletableFuture<String> b =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "orders"), io);
            CompletableFuture<String> c =
                    CompletableFuture.supplyAsync(() ->
                            waitForRelease(started, gate, "stock"), io);

            started.await();
            gate.countDown();

            CompletableFuture<List<String>> result =
                    CompletableFuture.allOf(a, b, c)
                    .thenApply(ignored ->
                            List.of(a.join(), b.join(), c.join()));

            System.out.println("values=" + result.join());
            System.out.println("allDone=" +
                    (a.isDone() && b.isDone() && c.isDone()));
        } finally {
            gate.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac SimulatedIoFanOutDemo.java
java SimulatedIoFanOutDemo
~~~

Stdout khi không bị interruption bên ngoài:

~~~text
values=[profile, orders, stock]
allDone=true
~~~

**Vì sao kết quả đáng tin?**
- Pool có ba workers, đủ để cả ba tasks bước vào `gate.await()`.
- Mỗi task `started.countDown()` trước khi chờ; main chỉ nhả gate sau khi đủ ba tín hiệu.
- Chỉ khi đó worker tasks mới có thể trả giá trị, và `allOf` chờ cả ba.
- Các kết quả được liệt kê theo thứ tự `a,b,c`, **không** in thứ tự thread nào thức dậy trước.
- `Future.join()` sau `allOf` hoàn tất bình thường chỉ đọc kết quả đã xong, không tạo một chuỗi đợi tuần tự cho I/O.

### Anti-pattern: join ngay sau mỗi lần launch

~~~java
String a = CompletableFuture.supplyAsync(
        this::loadA, ioPool).join();
String b = CompletableFuture.supplyAsync(
        this::loadB, ioPool).join();
String c = CompletableFuture.supplyAsync(
        this::loadC, ioPool).join();
~~~

Đây là snippet trong class có `loadA/B/C` và `ioPool`. B chỉ được submit **sau khi A đã xong**, C chỉ được submit sau B. Dù có CompletableFuture, mô hình thực tế gần như tuần tự.

Cách đúng là **khởi động tất cả các nhánh độc lập trước, fan-in sau**:

~~~java
CompletableFuture<String> a =
        CompletableFuture.supplyAsync(this::loadA, ioPool);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(this::loadB, ioPool);
CompletableFuture<String> c =
        CompletableFuture.supplyAsync(this::loadC, ioPool);

CompletableFuture<List<String>> result =
        CompletableFuture.allOf(a, b, c)
        .thenApply(v -> List.of(
                a.join(), b.join(), c.join()));
~~~

Đây cũng chỉ là snippet, minh họa cấu trúc dependency.

## 6. Lỗi một nhánh: all-required hay partial success?

Khi một downstream không sẵn sàng:
- Một `CompletableFuture` có thể complete exceptionally.
- `allOf` hoàn thành exceptionally nếu có ít nhất một input exceptional (nó không tự biến lỗi thành default).
- `thenApply` phụ thuộc vào `allOf` thành công **không chạy** khi aggregate lỗi.
- `allOf` không tự cancel mọi siblings chỉ vì một nhánh thất bại.
- Các requests sibling đã khởi động có thể tiếp tục làm I/O, tiêu thụ network resources hoặc tạo side effects.

Trước khi viết recovery, cần phân loại:
- **Required:** thiếu nhánh này nghĩa là request không còn hợp lệ; aggregate phải báo failure.
- **Optional:** thiếu nhánh này vẫn có response hợp lệ, nhưng phải đánh dấu nguồn không khả dụng.
- **Partial:** lưu cả per-branch outcome, không chỉ những giá trị thành công.

### Ví dụ 3 — Partial result không che lỗi

**Tạo file `PartialFanInDemo.java`:**

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class PartialFanInDemo {
    record Slot(String source, String value, String error) {
        @Override
        public String toString() {
            return source + "="
                    + (error == null ? value : "ERR:" + error);
        }
    }

    public static void main(String[] args) {
        ExecutorService io = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<String> profile =
                    CompletableFuture.supplyAsync(
                            () -> "user=42", io);
            CompletableFuture<String> orders =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalStateException("HTTP_503");
                    }, io);
            CompletableFuture<String> stock =
                    CompletableFuture.supplyAsync(
                            () -> "stock=8", io);

            CompletableFuture<Slot> p = profile.handle(
                    (v, e) -> new Slot(
                            "profile", v,
                            e == null ? null : "unavailable"));
            CompletableFuture<Slot> o = orders.handle(
                    (v, e) -> new Slot(
                            "orders", v,
                            e == null ? null : "unavailable"));
            CompletableFuture<Slot> s = stock.handle(
                    (v, e) -> new Slot(
                            "stock", v,
                            e == null ? null : "unavailable"));

            CompletableFuture<List<Slot>> partial =
                    CompletableFuture.allOf(p, o, s)
                    .thenApply(x -> List.of(
                            p.join(), o.join(), s.join()));

            System.out.println("partial=" + partial.join());

            CompletableFuture<Void> strict =
                    CompletableFuture.allOf(
                            profile, orders, stock);
            try {
                strict.join();
            } catch (CompletionException e) {
                System.out.println("strictError="
                        + e.getCause().getClass().getSimpleName());
            }
        } finally {
            io.shutdownNow();
            try {
                io.awaitTermination(1, TimeUnit.MINUTES);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac PartialFanInDemo.java
java PartialFanInDemo
~~~

Stdout:

~~~text
partial=[profile=user=42, orders=ERR:unavailable, stock=stock=8]
strictError=IllegalStateException
~~~

Giải thích:
1. `orders` ném `IllegalStateException`, nên Future gốc trở thành exceptional.
2. `handle` chạy trên cả success và error; nó trả về `Slot` bình thường chứa trạng thái rõ. `handle` **không đổi trạng thái future gốc**.
3. `allOf(p,o,s)` nhận ba futures đều normal và thu về ba `Slot` theo thứ tự nguồn.
4. `allOf(profile,orders,stock)` vẫn lỗi; `join()` của strict aggregate ném `CompletionException` có cause từ orders.
5. Hai cách tổng hợp dùng chung một nhóm I/O, nhưng business policy khác nhau.

**Phân biệt các phép xử lý lỗi:**
- `handle((v,e)->r)`: chạy cả khi success/error, có thể đổi sang kiểu `R`.
- `exceptionally(e->fallback)`: chỉ recovery khi lỗi và giữ cùng kiểu.
- `whenComplete((v,e)->log(...))`: quan sát outcome, không mặc định recover.
- `exceptionallyCompose(...)`: recovery bằng một Future mới, có trong Java 17.

Không dùng `exceptionally(ex -> null)` tràn lan: null có thể bị hiểu là dữ liệu thật hoặc gây NPE ở tầng gộp. Nếu Orders thất bại, đừng đổi thành `orders=0` trừ khi domain thật sự quy định đó là fallback hợp lệ.

## 7. Ví dụ 4 — thenCombine và thenCompose biểu diễn graph

Giá vận chuyển không phụ thuộc giá sản phẩm: lấy price và shipping song song, sau đó tính tổng; khi đã có total mới tạo một chứng từ. Đây là ví dụ fan-out nhỏ + dependent stage.

**Tạo file `CompositionGraphDemo.java`:**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompositionGraphDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(3);
        try {
            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(
                            () -> 120, io);
            CompletableFuture<Integer> shipping =
                    CompletableFuture.supplyAsync(
                            () -> 15, io);

            CompletableFuture<Integer> total =
                    price.thenCombine(
                            shipping, Integer::sum);

            CompletableFuture<String> receipt =
                    total.thenCompose(value ->
                            CompletableFuture.supplyAsync(
                                    () -> "total=" + value, io));

            System.out.println("receipt=" + receipt.get());
        } finally {
            io.shutdown();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac CompositionGraphDemo.java
java CompositionGraphDemo
~~~

Stdout:

~~~text
receipt=total=135
~~~

`price` và `shipping` được khởi động trước; `thenCombine` chờ cả hai rồi tính 135; `thenCompose` chỉ chạy khi đã có total và flatten Future mới. Nếu phần tiếp theo là một HTTP async request, callback có thể trả trực tiếp `client.sendAsync(...)` thay vì dùng `supplyAsync`.

**Tránh deadlock:** Không nên block một worker bằng `otherFuture.join()` nếu `otherFuture` chỉ có thể chạy trên **cùng một executor một thread** và đang nằm trong queue phía sau worker đó. Mô tả dependency bằng composition thay vì bắt worker bận chờ một task chưa được chạy.

## 8. Đặt timeout đúng ba tầng

**Tầng 1 — timeout đợi ở caller:** `future.get(300, MILLISECONDS)` giới hạn khoảng caller chờ. Nếu `TimeoutException`, task có thể vẫn đang chạy; `get(timeout)` không tự gọi cancel.

**Tầng 2 — timeout completion của CompletableFuture:**
- `orTimeout(t,u)` hoàn thành Future exceptional với `TimeoutException` khi chưa hoàn tất trước hạn.
- `completeOnTimeout(fallback,t,u)` hoàn thành Future bằng fallback khi chưa hoàn tất trước hạn.

Hai method tác động đến **trạng thái của chính CompletableFuture** và không phải lệnh hệ thống để dừng mọi underlying I/O.

**Tầng 3 — timeout tại transport:** `HttpClient.Builder.connectTimeout`, `HttpRequest.Builder.timeout` hoặc timeout của JDBC/driver/socket/SDK thực tế. Chúng có semantics riêng và cần điều chỉnh theo request deadline.

### Ví dụ 5 — completeOnTimeout không làm worker tự thoát

**Tạo file `TimeoutNotStopDemo.java`:**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class TimeoutNotStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            CompletableFuture<String> request =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "REAL_RESPONSE";
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            throw new CompletionException(e);
                        } finally {
                            exited.countDown();
                        }
                    }, io);

            started.await();
            request.completeOnTimeout(
                    "FALLBACK", 20, TimeUnit.MILLISECONDS);

            String visible = request.join();

            release.countDown();
            exited.await();

            System.out.println("visible=" + visible);
            System.out.println("workerExited=" +
                    (exited.getCount() == 0));
            System.out.println("futureValue=" + request.join());
        } finally {
            release.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac TimeoutNotStopDemo.java
java TimeoutNotStopDemo
~~~

Stdout không có interruption bên ngoài:

~~~text
visible=FALLBACK
workerExited=true
futureValue=FALLBACK
~~~

Vì `release` chưa hạ, supplier không thể trả `REAL_RESPONSE` trước khi timeout. Future nhận `FALLBACK` và `join` trả ngay sau hạn. **Worker vẫn đang chờ** cho tới khi main hạ latch. Main đợi `exited` sau đó, nhưng outcome Future không đổi. Nếu dùng `orTimeout` thay `completeOnTimeout`, `join()` sẽ ném `CompletionException` với cause `TimeoutException` khi deadline thắng.

### Deadline end-to-end

Đừng tái cấp 500 ms cho mỗi stage trong cùng một request nếu caller chỉ có tổng ngân sách 500 ms. Mang remaining duration tới API cho phép timeout. Với các phép đo duration trong một JVM có thể dùng `System.nanoTime()`; nó không phải timestamp UTC để gửi nguyên sang process khác. Nếu remaining <=0, đừng khởi tạo thêm I/O mới chỉ để rồi timeout.

### HTTP request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest req = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET().build();

CompletableFuture<HttpResponse<String>> response =
        client.sendAsync(
                req, HttpResponse.BodyHandlers.ofString());
~~~

Đây là snippet với imports `java.time.Duration`, `java.net.http.*` và `java.net.URI`, biến `uri` đã xác định. Timeout tại HTTP API có phạm vi riêng; vẫn cần overall deadline/cancel policy của request.

## 9. Cancellation và I/O vẫn đang chạy

`CompletableFuture.cancel(true)` của Java 17 **không sử dụng `mayInterruptIfRunning` để điều khiển thực thi** như một số implementation của `FutureTask`. Nó có thể làm CompletableFuture chuyển sang cancelled, nhưng **không bảo đảm** runner `supplyAsync` bị interrupt.

Trong fan-out:
- Hủy Future tổng không đồng nghĩa tự hủy mọi nhánh.
- Các siblings đã bắt đầu vẫn có thể chạy.
- Những callback downstream chưa chạy có thể nhận exceptional completion do cancellation.
- Dịch vụ remote có thể đã ghi dữ liệu trước khi caller quyết định hủy.
- Khi retry, phải dùng idempotency key/reconciliation nếu có side effects.
- Để thực sự hủy I/O, dùng timeout, close, cancellation handle tương ứng **tại client API**.

Một lưu ý về `HttpClient.sendAsync`: Future do HTTP client trả có hành vi cancellation của transport cụ thể; implementation có thể cố hủy HTTP exchange khi bạn gọi cancel. Nhưng không có bảo đảm remote server đã rollback dữ liệu nó nhận. Không suy từ `isCancelled()==true` ra “request chưa được xử lý”.

### Ví dụ 6 — cancel(true) không bắt buộc interrupt supplyAsync runner

**Tạo file `CancelIsNotInterruptDemo.java`:**

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelIsNotInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "REAL";
                        } catch (InterruptedException e) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            throw new CompletionException(e);
                        } finally {
                            exited.countDown();
                        }
                    }, io);

            started.await();
            boolean accepted = future.cancel(true);

            release.countDown();
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("interrupted=" + interrupted.get());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                future.join();
            } catch (CancellationException e) {
                System.out.println("join=CancellationException");
            }
        } finally {
            release.countDown();
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac CancelIsNotInterruptDemo.java
java CancelIsNotInterruptDemo
~~~

Stdout với executor thông thường, không có external interrupt:

~~~text
cancelAccepted=true
cancelled=true
interrupted=false
workerExited=true
join=CancellationException
~~~

Main hủy Future trong khi worker đang chờ latch. `cancel(true)` làm Future cancelled nhưng **không interrupt** supplier theo contract CompletableFuture Java 17. Main sau đó chủ động hạ latch, worker thực sự thoát. `join` nhận CancellationException, dù worker có thể đã trả `REAL` sau đó. Điều này minh họa ranh giới **future outcome** khác **worker lifecycle**.

## 10. Giới hạn fan-out và backpressure

Code ngây thơ:

~~~java
List<CompletableFuture<Response>> tasks = ids.stream()
        .map(id -> CompletableFuture.supplyAsync(
                () -> blockingRemoteCall(id), ioPool))
        .toList();
~~~

Đây là snippet với `Response` và methods/variables do ứng dụng định nghĩa. Nếu `ids` chứa 100.000 phần tử, bạn có thể tạo 100.000 Future objects và 100.000 queued tasks. Một fixed thread pool giới hạn **workers**, nhưng `Executors.newFixedThreadPool(n)` thông thường dùng queue không bounded; nó **không giới hạn backlog**.

Cần phân biệt:
- **In-flight concurrency limit:** tối đa K remote calls đang hoạt động.
- **Admission/queue bound:** tối đa Q yêu cầu được chấp nhận nhưng chưa chạy.
- **Rate limit:** tối đa N khởi tạo calls trên một cửa sổ thời gian.
- **Deadline:** thời gian chờ/tổng thời gian cho một request.
- **Bulkhead:** tách downstream/resource groups để một dịch vụ yếu không chặn mọi dịch vụ.

`Semaphore` có thể giới hạn calls đang hoạt động, nhưng nếu acquire **bên trong mọi task sau khi submit**, một lượng Future/task cực lớn vẫn chiếm queue và memory. Với production nên giới hạn **trước khi submit**, chia batches, hoặc xây bounded dispatcher/async semaphore.

### Ví dụ 7 — Bounded in-flight với Semaphore

**Tạo file `BoundedFanOutDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedFanOutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newFixedThreadPool(4);
        Semaphore permits = new Semaphore(2);
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxObserved = new AtomicInteger();
        List<CompletableFuture<Integer>> tasks = new ArrayList<>();

        try {
            for (int i = 1; i <= 6; i++) {
                final int id = i;
                tasks.add(CompletableFuture.supplyAsync(() -> {
                    boolean acquired = false;
                    try {
                        permits.acquire();
                        acquired = true;

                        int count = inFlight.incrementAndGet();
                        maxObserved.accumulateAndGet(count, Math::max);

                        Thread.sleep(10); // Mô phỏng chờ I/O.
                        return id * id;
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new CompletionException(e);
                    } finally {
                        if (acquired) {
                            inFlight.decrementAndGet();
                            permits.release();
                        }
                    }
                }, io));
            }

            CompletableFuture.allOf(
                    tasks.toArray(new CompletableFuture<?>[0]))
                    .join();

            int total = tasks.stream()
                    .mapToInt(CompletableFuture::join)
                    .sum();

            System.out.println("sumSquares=" + total);
            System.out.println("withinLimit=" +
                    (maxObserved.get() <= 2));
            System.out.println("permitsRestored=" +
                    permits.availablePermits());
        } finally {
            io.shutdownNow();
            io.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac BoundedFanOutDemo.java
java BoundedFanOutDemo
~~~

Stdout không phụ thuộc thứ tự worker:

~~~text
sumSquares=91
withinLimit=true
permitsRestored=2
~~~

Sáu nhánh tính `1²+2²+3²+4²+5²+6²=91`. Chỉ task đã acquire mới tăng `inFlight`; `Semaphore(2)` bảo đảm `maxObserved<=2`. Số peak thực tế **có thể là 1 hoặc 2** tùy scheduling, vì vậy không in một số peak cố định. Các permits được trả trong `finally` và main kiểm tra sau allOf.

**Hạn chế demo:** `Thread.sleep` mô phỏng waiting và acquire bên trong worker; pattern này chưa giới hạn số Futures đã submit. Với HTTP `sendAsync` thật, nên xem connection limits và dùng bounded admission trước khi phát n requests.

## 11. Danh sách futures động và input rỗng

Khi số nhánh thay đổi theo request, cách collect thông thường:

~~~java
List<CompletableFuture<Item>> futures =
        ids.stream()
           .map(id -> fetchItemAsync(id))
           .toList();

CompletableFuture<List<Item>> combined =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0]))
        .thenApply(ignored ->
                futures.stream()
                       .map(CompletableFuture::join)
                       .toList());
~~~

Đây là snippet, với `Item`, `ids` và `fetchItemAsync` được định nghĩa. `List.toList()` đi theo **encounter order của futures input**, không theo thứ tự hoàn thành.

`CompletableFuture.allOf()` với zero arguments hoàn tất bình thường, nên List rỗng có thể trở thành kết quả rỗng hợp lệ. Nhưng nếu `ids` có hàng trăm nghìn phần tử, không nên eager-create mọi Future. Chia batches với policy về tổng số in-flight và backlog.

## 12. anyOf không đồng nghĩa first-success

`CompletableFuture.anyOf(a,b,c)` hoàn tất với **một completion đầu tiên**, kể cả exceptional. Nếu nguồn nhanh nhất trả lỗi 503, `anyOf` có thể complete exceptionally dù nguồn chậm hơn sẽ thành công. Điều này **không** đáp ứng policy “lấy kết quả thành công sớm nhất”.

Muốn first-success thực sự:
- Coordinator theo dõi failures và success của từng candidate.
- Completion normal đầu tiên chiến thắng; nếu **tất cả** fail thì mới báo thất bại.
- Khi một nguồn thắng, có policy với losers: tiếp tục/stop, cleanup, late side effects.
- Có giới hạn số request đồng thời và chi phí duplicate calls.
- Nếu operations là writes, không fan-out cùng một giao dịch tới nhiều nơi rồi chọn kết quả đầu mà thiếu idempotency/transaction policy.

Đừng dùng `applyToEither` hoặc `anyOf` như một first-success abstraction tổng quát mà không đọc kỹ exceptional completion semantics.

## 13. Threading của callbacks và nguy cơ starvation

`thenApply`, `handle`, `thenCombine` không có hậu tố Async có thể chạy callback trên thread hoàn tất stage trước, hoặc thread gọi completion, tùy timing/contract. Không mặc định callback chạy trên main hoặc trên executor mới.

`thenApplyAsync(fn, executor)` lên lịch callback trên executor bạn chọn. Nó hữu ích khi callback xử lý **CPU-heavy parsing**, nhưng cũng có scheduling overhead:
- Ghép vài immutable records rất nhanh: `thenApply` thường hợp lý.
- Parse JSON nặng, decode/compression: cân nhắc `thenApplyAsync` trong CPU pool.
- Blocking legacy API: chạy trên dedicated bounded I/O executor hoặc dùng async API thực sự.
- Không dùng Async chỉ vì tên “bất đồng bộ”: nó không làm một `Thread.sleep` trở thành nonblocking.

### Tránh chờ một Future cần chính worker đang bị block

~~~text
Single-thread executor:
  Worker đang chạy A và gọi B.join()
  B còn nằm trong queue sau A
  -> B không có worker chạy -> có thể deadlock
~~~

`CompletableFuture` được thiết kế để diễn đạt dependency bằng `thenCompose`/`thenCombine`, thay vì giữ worker ở một blocking `get/join` không cần thiết.

## 14. Timeout, retry và idempotency ở remote service

Một request có deadline 700 ms và ba downstream không nên trao cho mỗi nhánh 700 ms **mới từ lúc nó bắt đầu**, nếu nó còn phụ thuộc hai stage khác. Mang deadline/remaining budget qua toàn graph.

Với `System.nanoTime()` trong một JVM có thể đo duration; đừng gửi nguyên mốc nanoTime sang JVM khác như UTC timestamp. Đưa timeout đúng vào HTTP request/connection và những APIs downstream.

Khi retry:
- Chỉ retry lỗi được phân loại retryable.
- Cân nhắc exponential backoff, jitter, retry budget, max attempts.
- Chia ngân sách thời gian tổng giữa các attempts.
- Bảo vệ downstream khỏi retry storm khi nhiều incoming requests timeout đồng thời.
- Với write operations, dùng idempotency key ở nơi nhận để tránh duplicate side effect.

**Ví dụ:** Client gửi createOrder, server đã commit nhưng response về chậm. Caller timeout, retry. `CompletableFuture` timeout không nói liệu order trước đã được tạo; nếu không có idempotency/reconciliation, có thể tạo order trùng.

## 15. Đo hiệu năng và quan sát pipeline

Không đo speedup chỉ bằng một lần `System.currentTimeMillis()`. Độ trễ I/O biến động theo DNS, connection reuse, OS scheduler, TLS, server load, GC, retry và network.

Metrics nên có:
- End-to-end latency của request (p50/p95/p99).
- Per-branch latency và HTTP status/errors.
- Số in-flight calls mỗi downstream.
- Thread pool active count, queue wait, saturation/rejection.
- Timeout count phân theo caller/CF/transport.
- Fallback/partial-success tỷ lệ, không gộp với success đầy đủ.
- Cancellation requested vs underlying I/O completion/cleanup.
- Tổng request attempts sau retries và idempotency collisions.
- Backlog và giới hạn memory/connections.
- Trễ từ branch nhanh nhất tới branch chậm nhất.

**Kế hoạch test:**
1. Baseline tuần tự trên cùng ba endpoints, cùng input.
2. Fan-out ba nhánh độc lập, không retry, quan sát latency.
3. Thử nhánh chậm 10 lần, nhánh lỗi HTTP 500, timeout, malformed JSON.
4. Thử partial policy và all-required policy; kiểm tra schema response.
5. Thử rất nhiều requests đồng thời; đo downstream saturation và queue memory.
6. Hủy request khi mọi nhánh còn đang chạy, xác minh cleanup/late response.
7. Thử failure của một sibling khi những sibling khác đang chờ.
8. Đặt connection/rate limits sát thực tế thay vì benchmark trên server giả không giới hạn.
9. Không đưa output thời gian cố định vào ví dụ vì scheduling không được bảo đảm.
10. Với microbenchmark CPU-only, dùng JMH; end-to-end I/O nên dùng load testing thích hợp.

## 16. Các lỗi thường gặp và hướng sửa

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| `join` sau từng `supplyAsync` | Biến fan-out thành tuần tự | Launch tất cả trước, fan-in sau |
| Tưởng `allOf` trả List | Sai kiểu | Tạo List trong dependent stage sau allOf |
| Nhánh lỗi nhưng vẫn chạy `thenApply` bình thường | Không chạy; aggregate exceptional | Handle error từng nhánh theo policy |
| `exceptionally(ex -> null)` khắp nơi | Che lỗi/NPE hoặc báo success giả | Dùng result/error marker tường minh |
| HTTP 500 coi là normal business response | Báo dữ liệu sai | Validate status/schema |
| `thenApply` để return CompletableFuture | Future lồng Future | Dùng `thenCompose` |
| Bọc `sendAsync` trong blocking `supplyAsync` | Tốn thread chờ I/O | Dùng HttpClient async trực tiếp |
| Blocking I/O trong common pool mặc định | Starvation/contended pool | Dedicated bounded I/O executor |
| FixedThreadPool tưởng queue bounded | Backlog/future memory có thể tăng vô hạn | Bounded admission/queue |
| Semaphore acquire sau khi submit rất nhiều task | Giới hạn in-flight nhưng không giới hạn queue | Limit trước submit hoặc batch |
| `anyOf` cho first-success | Failure đầu tiên có thể thắng | Coordinator first-success |
| `get(timeout)` coi là auto cancel | Underlying task vẫn có thể chạy | Cancel/cleanup riêng |
| `orTimeout` coi là socket cancel | Remote I/O có thể tiếp diễn | Timeout đúng transport API |
| `CompletableFuture.cancel(true)` coi là interrupt runner | Không được bảo đảm | Theo dõi task/transport handle |
| Khi một nhánh fail tưởng siblings dừng hết | Orphan work/side effects | Ownership/cancellation policy |
| Retry không kiểm soát | Amplify traffic lúc downstream lỗi | Retry budget/backoff/jitter |
| Partial trả như full success | Sai domain semantics | Marker của từng nhánh |
| Parse JSON nặng trong completion thread | Tăng callback latency | CPU executor riêng |
| Chờ sibling Future trên một single-thread pool | Thread starvation deadlock | Composition không blocking |
| Đọc results theo completion order khi cần key order | Response không ổn định | Thu theo thứ tự input/keys |
| Cancel local Future coi như rollback remote write | Duplicate khi retry | Idempotency/reconciliation |
| Không phân biệt worker exited với isDone | Đánh giá cleanup sai | Lifecycle signal riêng |
| Shutdown shared executor cuối một request | Ảnh hưởng request khác | Service owns executor lifecycle |

## 17. Checklist production

1. Các nhánh nào độc lập thật, nhánh nào cần output nhánh trước?
2. Tất cả child futures được launch trước thời điểm fan-in chưa?
3. Kiểu kết quả của `allOf` và cách collect có đúng không?
4. Cần sorted/key order hay có thể accept completion order?
5. Có xác nhận HTTP status và body schema?
6. Error policy: all-required, optional, partial hay first-success?
7. Optional fallback có marker, không gây nhầm lẫn domain?
8. Số child mỗi request tối đa bao nhiêu?
9. Tổng in-flight theo downstream/tenant có bị giới hạn?
10. Executor queue/admission có bounded không?
11. Có deadline tổng ngoài connection/request timeout?
12. Timeout CF có bị hiểu nhầm thành dừng I/O không?
13. Ai giữ cancel handles và làm cleanup khi request hủy?
14. Late results có thể ghi đè state mới không?
15. Remote write có idempotency khi retry không?
16. Callback nhẹ hay CPU-heavy, cần executor nào?
17. Có blocking join/get trong chính pool cần hoàn tất future không?
18. Nếu một branch lỗi, siblings còn chạy thì policy gì?
19. Kết quả từ nhiều sources có cần cùng epoch/version không?
20. Có metric branch latency, exception, timeout và backlog không?
21. Có test partial/error/cancel/timeout races không?
22. Có shutdown executor thuộc đúng owner, không tạo/leak pool mỗi nhánh?
23. Empty input list có trả kết quả hợp lệ?
24. CPU/RAM/connection quotas của môi trường đã được tính vào capacity?

## 18. Tự kiểm tra

1. **Fan-out là gì?** Khởi động nhiều công việc độc lập có thể tiến triển đồng thời.
2. **Fan-in là gì?** Đồng bộ hóa và tổng hợp outcomes của các công việc.
3. **allOf trả List không?** Không, trả `CompletableFuture<Void>`.
4. **Thu List kết quả sau allOf bằng gì?** `thenApply` và `join` các child đã completed.
5. **thenCombine thích hợp lúc nào?** Có hai futures độc lập cần ghép sau khi cả hai xong.
6. **thenCompose thích hợp lúc nào?** Stage sau phụ thuộc kết quả trước và trả Future.
7. **Gọi join sau mỗi launch gây gì?** Có thể tuần tự hóa fan-out.
8. **Một child fail thì allOf thế nào?** Hoàn thành exceptionally; không tự cancel siblings.
9. **Có nên fallback Orders lỗi thành orders=0 không?** Không nếu 0 là dữ liệu thật và unavailable khác 0.
10. **HttpClient.sendAsync nhận status 500 có tự throw không?** Không nhất thiết; validate status.
11. **Danh sách trong thenApply sau allOf theo thứ tự gì?** Theo thứ tự code collect, không theo completion.
12. **Future.get(timeout) có tự cancel không?** Không.
13. **completeOnTimeout có interrupt blocking supplier không?** Không được bảo đảm.
14. **CompletableFuture.cancel(true) có bảo đảm interrupt runner không?** Không.
15. **Cancel HTTP request có chắc remote rollback không?** Không.
16. **Fixed pool 4 worker có queue chỉ 4 tasks không?** Không.
17. **Semaphore 2 bảo vệ điều gì?** Tối đa hai holders được permit đồng thời.
18. **Semaphore trong task sau submit có bound số Futures chờ không?** Không.
19. **anyOf có chờ first successful không?** Không; failure đầu tiên cũng có thể complete.
20. **Callback thenApply luôn chạy trên main thread không?** Không.
21. **Một stage nặng CPU có thể dùng gì?** `thenApplyAsync(fn,cpuPool)`.
22. **Blocking get trong single-thread pool nguy hiểm khi nào?** Khi Future cần pool đó để chạy.
23. **Tại sao cần deadline tổng?** Để không tái cấp nguyên timeout mỗi stage.
24. **Retry remote POST sau timeout nguy hiểm ở đâu?** Request cũ có thể đã commit, tạo duplicate.
25. **Phân biệt Future done và worker exited?** Done có thể do cancel/timeout trước khi task thực sự ngừng.
26. **Đo fan-out có chắc speedup không?** Không; phụ thuộc downstream capacity và overhead.
27. **Khi nào partial result hợp lệ?** Khi business contract có thể biểu diễn unavailable riêng.
28. **Phương pháp tránh fake success?** Per-branch `Result`/`Slot` chứa value/error rõ.
29. **Khi không có ids thì allOf ra sao?** `allOf()` đã completed bình thường.
30. **Điểm cốt lõi của fan-out I/O đáng tin?** Dependency graph đúng, bounded load, deadline/failure policy, cleanup và idempotency.

## 19. Kết luận

**Fan-out / fan-in hiệu quả không chỉ là gọi ba lần `supplyAsync`.** Nó cần một đồ thị công việc đúng, chính sách kết quả rõ và giới hạn tài nguyên phù hợp:

~~~text
Fan-out: start independent requests
               |
               v
Fan-in: allOf / thenCombine
               |
               v
Check HTTP status, timeout, failure, fallback
               |
               v
Build aggregate / publish with ownership policy
~~~

Dùng `thenCompose` cho dependency, `allOf` để đợi nhiều nhánh, `thenCombine` cho hai nhánh độc lập. Thu kết quả theo thứ tự nghiệp vụ. Xác định nhánh required/optional, không biến lỗi thành dữ liệu hợp lệ tùy tiện. **Timeout/cancel ở Future không phải chứng chỉ remote I/O dừng hay rollback**. Cần bounded concurrency/admission, retry có giới hạn, idempotency với remote writes và metrics của mỗi nhánh.

Với Java 17, `HttpClient.sendAsync` cho HTTP I/O bất đồng bộ, còn `CompletableFuture` giúp biểu diễn sự phối hợp; các quyết định về deadline, cancellation, backpressure và đúng đắn nghiệp vụ vẫn thuộc trách nhiệm thiết kế của ứng dụng.

## Tài liệu tham khảo Java SE 17

- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `allOf`, `thenCombine`, `thenCompose`, `handle`, `orTimeout`, `completeOnTimeout`, `cancel`.
- [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): mô hình dependent stages.
- [HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` và connect timeout.
- [HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request timeout.
- [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status và body.
- [HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): ví dụ HTTP loopback.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): worker and lifecycle.
- [Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): bounded in-flight work.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test concurrency.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool và work stealing.
