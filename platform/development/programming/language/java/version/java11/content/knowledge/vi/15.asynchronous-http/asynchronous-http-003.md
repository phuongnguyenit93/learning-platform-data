# Ghép các yêu cầu HTTP độc lập bằng `CompletableFuture.allOf` (Java 11 trở lên)

## 1. Bài toán: gọi nhiều endpoint độc lập mà không đợi tuần tự

Giả sử màn hình tổng quan cần ba nguồn dữ liệu:

- `GET /profile` — hồ sơ người dùng;
- `GET /orders` — danh sách đơn hàng;
- `GET /settings` — cấu hình hiển thị.

Ba endpoint này **không cần kết quả của nhau** để tạo request. Nếu thực hiện tuần tự bằng `HttpClient.send(...)`, ứng dụng phải hoàn thành request trước rồi mới gửi request sau:

```java
// Cách đồng bộ, tuần tự: mỗi send(...) chờ phản hồi.
HttpResponse<String> profile = client.send(
        profileRequest, HttpResponse.BodyHandlers.ofString());
HttpResponse<String> orders = client.send(
        ordersRequest, HttpResponse.BodyHandlers.ofString());
HttpResponse<String> settings = client.send(
        settingsRequest, HttpResponse.BodyHandlers.ofString());
```

Đoạn mã trên là **minh họa đặt trong phương thức có khai báo exception**, không phải một chương trình độc lập. Thời gian chờ end-to-end có thể gần tổng các lần gọi mạng, cộng thời gian xử lý.

Trong Java 11, `HttpClient.sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Ta có thể khởi phát ba request **trước khi chờ kết quả**, rồi ghép các future bằng:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(
        profileFuture, ordersFuture, settingsFuture);
```

`allOf` tạo một **điểm đồng bộ hóa**: future tổng hợp hoàn thành khi **tất cả** các future đầu vào hoàn thành. Nếu không có lỗi, từ thời điểm đó có thể lấy từng kết quả riêng lẻ để tạo DTO, danh sách hoặc phản hồi tổng hợp.

**Mấu chốt:** `allOf` không tự gửi HTTP request, không tự chạy song song bằng cách tạo thread và **không tự trả một danh sách kết quả**. Tính bất đồng bộ đến từ những request đã được khởi phát bằng `sendAsync`; `allOf` chỉ kết hợp trạng thái hoàn thành của chúng.

## 2. Phân biệt ba việc: khởi phát, chờ đủ, lấy kết quả

Có thể mô tả luồng như sau:

```text
                 ┌── sendAsync(GET /profile) ── futureProfile ─┐
Main thread ─────┼── sendAsync(GET /orders)  ── futureOrders  ─┼── allOf
                 └── sendAsync(GET /settings)── futureSettings─┘     |
                                                                    v
                                                          when all complete
                                                                    |
                                                                    v
                                                          thenApply / results
```

Các bước đúng:

1. Xây `HttpRequest` cho từng endpoint.
2. Gọi `sendAsync(...)` cho **tất cả** request độc lập. Mỗi lời gọi trả một `CompletableFuture` tương ứng.
3. Gọi `CompletableFuture.allOf(...)` với những future đã được tạo.
4. Xây một dependent stage bằng `thenApply`, `thenAccept` hoặc `thenRun` để xử lý khi cả nhóm hoàn tất.
5. Chỉ ở ranh giới cần chờ trong ứng dụng CLI/test, gọi `join()` hoặc `get()` trên future tổng hợp. Trong ứng dụng bất đồng bộ thuần túy, nên trả về stage thay vì chặn thread hiện tại.

Đừng làm thế này:

```java
// SAI mục tiêu song hành: join ngay sau mỗi sendAsync.
String profile = client.sendAsync(profileRequest, textHandler)
        .thenApply(HttpResponse::body).join();

String orders = client.sendAsync(ordersRequest, textHandler)
        .thenApply(HttpResponse::body).join();
```

Bởi vì lời gọi `join()` đầu tiên chặn luồng hiện tại trước khi `sendAsync` thứ hai được thực hiện. Nếu yêu cầu độc lập, cách này làm mất lợi ích của việc khởi phát chúng sớm.

Một phiên bản đúng ở mức ý tưởng:

```java
CompletableFuture<HttpResponse<String>> profileFuture =
        client.sendAsync(profileRequest, textHandler);
CompletableFuture<HttpResponse<String>> ordersFuture =
        client.sendAsync(ordersRequest, textHandler);

CompletableFuture<Void> both =
        CompletableFuture.allOf(profileFuture, ordersFuture);

CompletableFuture<String> combined = both.thenApply(ignored ->
        profileFuture.join().body() + " | " +
        ordersFuture.join().body());
```

Phần trên sử dụng các biến đã khởi tạo (client, request, handler), nên là **code minh họa**. Đọc `join()` trong `thenApply` của một `allOf` đã hoàn thành **bình thường** là phù hợp, vì lúc đó các future thành phần đều đã hoàn tất bình thường; không có bước chờ mạng tuần tự mới.

## 3. Hợp đồng `CompletableFuture.allOf` trong Java 11

Chữ ký API:

```java
public static CompletableFuture<Void> allOf(
        CompletableFuture<?>... cfs)
```

| Trường hợp | Hành vi chính thức |
| --- | --- |
| Tất cả các future đầu vào hoàn thành bình thường | Future do `allOf` trả về hoàn thành bình thường, giá trị là `null` vì kiểu `Void` |
| Có ít nhất một future hoàn thành exceptionally | Future tổng hợp hoàn thành exceptionally; `join()` thường ném `CompletionException` chứa nguyên nhân |
| Một future vẫn đang chạy | `allOf` chưa hoàn thành theo hợp đồng "khi tất cả hoàn thành" |
| Mảng đầu vào rỗng | Trả một future **đã hoàn thành bình thường** với `null` |
| Mảng đầu vào hoặc một phần tử là `null` | Ném `NullPointerException` |
| Các future có kiểu kết quả khác nhau | Được chấp nhận qua `CompletableFuture<?>...`; vẫn cần lấy kết quả từ từng future |

Theo Javadoc, **kết quả của các future thành phần không xuất hiện trong kết quả của `allOf`**. Vì vậy không thể gán:

```java
// KHÔNG BIÊN DỊCH:
// CompletableFuture<List<String>> results =
//         CompletableFuture.allOf(futureA, futureB);
```

`allOf` chỉ cho ta `CompletableFuture<Void>`. Nếu cần `List<String>`, phải tạo thêm stage chuyển các future thành phần thành danh sách **sau khi tất cả đã hoàn tất**.

### `allOf` không có nghĩa là "thành công HTTP"

`HttpClient.sendAsync` hoàn thành **bình thường** khi nhận một `HttpResponse<T>` hợp lệ, ngay cả khi server trả status `404` hoặc `500`. HTTP status không tự động biến thành exception Java.

Do đó phải định nghĩa thế nào là response hợp lệ cho nghiệp vụ:

```java
CompletableFuture<String> task =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8))
        .thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }
            return response.body();
        });
```

Trong ví dụ, response khác `200` khiến future kết quả hoàn thành exceptionally. Nếu chỉ ghép các future `sendAsync` gốc mà **không kiểm tra status**, `allOf` có thể hoàn thành bình thường dù một endpoint trả `404`.

Cũng cần phân biệt **lỗi transport** (DNS, timeout, kết nối, TLS, I/O...) với **status HTTP do server trả**. Lỗi transport có thể khiến future `sendAsync` hoàn thành exceptionally; status `4xx/5xx` chỉ là dữ liệu của response cho đến khi code chủ động diễn giải nó.

## 4. Mẫu triển khai chuẩn: `sendAsync` + kiểm tra status + `allOf` + `thenApply`

Một phương thức gọi API trả `CompletableFuture<String>` có thể được viết như sau (đây là **method đặt trong một lớp**, đã import các API cần dùng):

```java
static CompletableFuture<String> fetch(
        HttpClient client, URI base, String path) {

    HttpRequest request = HttpRequest.newBuilder(base.resolve(path))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

    return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
            .thenApply(response -> {
                if (response.statusCode() != 200) {
                    throw new IllegalStateException(
                            path + ": HTTP " + response.statusCode());
                }
                return response.body();
            });
}
```

`HttpClient` là đối tượng có thể tái sử dụng cho nhiều request; Java 11 không yêu cầu phải tạo client mới cho mỗi endpoint. Builder nhận URI đã xác định, timeout và phương thức HTTP. `BodyHandlers.ofString(StandardCharsets.UTF_8)` giải mã response body bằng UTF-8 theo hợp đồng của ví dụ.

Sau đó tạo ba request độc lập:

```java
CompletableFuture<String> profile = fetch(
        client, base, "/profile");
CompletableFuture<String> orders = fetch(
        client, base, "/orders");
CompletableFuture<String> settings = fetch(
        client, base, "/settings");

CompletableFuture<Void> all =
        CompletableFuture.allOf(profile, orders, settings);

CompletableFuture<String> dashboard = all.thenApply(ignored ->
        "profile=" + profile.join()
        + ", orders=" + orders.join()
        + ", settings=" + settings.join());
```

Ở đây `dashboard` là một future mới chứa **kết quả ứng dụng**, không phải future mà `allOf` trực tiếp trả về. Khi tất cả thành công, thứ tự hiển thị `profile, orders, settings` do **code ghép chuỗi** quyết định, không phải thứ tự hoàn thành trên mạng.

Nếu một request lỗi, `all` hoàn thành exceptionally và `thenApply` của nó **không được chạy**. Tùy hợp đồng của ứng dụng, bạn có thể để lỗi lan truyền hoặc chuyển từng lỗi thành một kết quả fallback trước khi ghép. Hai chiến lược có ngữ nghĩa khác nhau, sẽ được phân tích bên dưới.

## 5. Chương trình đầy đủ, chạy được trên Java 11: ba request độc lập và một request lỗi

Ví dụ tạo một HTTP server **nội bộ** bằng module `jdk.httpserver` để bảo đảm có thể chạy/test mà không cần Internet. Nó không phải lời khuyên dùng `HttpServer` làm production server; mục đích chỉ là có endpoint deterministic.

Tạo file **`AllOfIndependentRequestsDemo.java`**:

```java
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
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllOfIndependentRequestsDemo {
    static void respond(HttpExchange exchange, int status, String content)
            throws IOException {
        byte[] payload = content.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, payload.length);
        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(payload);
        }
    }

    static CompletableFuture<String> fetch(
            HttpClient client, URI base, String path) {
        HttpRequest request = HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        return client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() != 200) {
                        throw new IllegalStateException(
                                path + ": HTTP " + response.statusCode());
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/profile",
                exchange -> respond(exchange, 200, "PROFILE"));
        server.createContext("/orders",
                exchange -> respond(exchange, 200, "ORDERS"));
        server.createContext("/settings",
                exchange -> respond(exchange, 200, "SETTINGS"));
        server.createContext("/missing",
                exchange -> respond(exchange, 404, "NOT_FOUND"));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:" +
                    server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newHttpClient();

            // Khởi phát cả ba request mà không join từng request.
            CompletableFuture<String> profile =
                    fetch(client, base, "/profile");
            CompletableFuture<String> orders =
                    fetch(client, base, "/orders");
            CompletableFuture<String> settings =
                    fetch(client, base, "/settings");

            CompletableFuture<Void> all =
                    CompletableFuture.allOf(
                            profile, orders, settings);

            CompletableFuture<String> summary = all.thenApply(ignored ->
                    "profile=" + profile.join()
                    + ", orders=" + orders.join()
                    + ", settings=" + settings.join());

            System.out.println("allOfIsVoid=" +
                    (all.join() == null));
            System.out.println(summary.join());

            // Trường hợp một HTTP response có status 404.
            CompletableFuture<String> missing =
                    fetch(client, base, "/missing");
            CompletableFuture<String> sibling =
                    fetch(client, base, "/profile");

            try {
                CompletableFuture.allOf(missing, sibling).join();
            } catch (CompletionException ex) {
                System.out.println("failure=" +
                        ex.getCause().getClass().getSimpleName());
                System.out.println("message=" +
                        ex.getCause().getMessage());
            }

            System.out.println("sibling=" + sibling.join());
            System.out.println("emptyAllOfDone=" +
                    CompletableFuture.allOf().isDone());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch bằng JDK 11 hoặc mới hơn:

```bash
javac --release 11 --add-modules jdk.httpserver AllOfIndependentRequestsDemo.java
java --add-modules jdk.httpserver AllOfIndependentRequestsDemo
```

**Kết quả stdout đã kiểm tra:**

```text
allOfIsVoid=true
profile=PROFILE, orders=ORDERS, settings=SETTINGS
failure=IllegalStateException
message=/missing: HTTP 404
sibling=PROFILE
emptyAllOfDone=true
```

### Giải thích từng kết quả

- `allOfIsVoid=true`: giá trị trả về của `all.join()` là `null` vì future tổng hợp có kiểu `Void`. Đây **không** phải mất dữ liệu: dữ liệu vẫn nằm trong `profile`, `orders`, `settings`.
- Dòng `profile=...` in theo **thứ tự ghép trong `thenApply`**, không phụ thuộc request nào nhận được response trước.
- `failure=IllegalStateException`: `fetch` chủ động biến HTTP `404` thành lỗi nghiệp vụ; `allOf(...).join()` ném `CompletionException` bọc nguyên nhân.
- `message=/missing: HTTP 404`: message của exception gốc. Nếu không kiểm tra status trong `fetch`, một `HttpResponse` với status `404` có thể vẫn hoàn thành bình thường.
- `sibling=PROFILE`: request độc lập còn lại vẫn có thể hoàn thành dù request cùng batch lỗi. `allOf` không tự "undo" request đã hoàn thành.
- `emptyAllOfDone=true`: `allOf()` không có phần tử trả về một future đã hoàn thành bình thường theo Javadoc.

Chương trình không in log từ các request khi chúng hoàn thành vì thứ tự callback có thể thay đổi giữa các lần chạy. Các dòng stdout ở trên **ổn định** do kết quả được lấy sau barrier và in theo một thứ tự xác định.

## 6. `allOf` có tạo song song thật không?

`CompletableFuture.allOf` **không phải bộ lập lịch** và không trực tiếp tạo HTTP request. `sendAsync` trả future cho thao tác I/O bất đồng bộ; ba lời gọi được khởi phát trước khi chờ, nên các thao tác có cơ hội **overlap** về thời gian.

So sánh sơ đồ thời gian giả định:

```text
CÁCH TUẦN TỰ
GET A [------] GET B [------] GET C [------]
Tổng thời gian xấp xỉ tổng các độ trễ

CÁCH ASYNC ĐỘC LẬP
GET A [-------]
GET B [-----------]
GET C [-----]
                  ^
              allOf completed
Tổng thời gian có thể gần độ trễ của request chậm nhất
```

Đây chỉ là hình minh họa, **không phải cam kết thời gian thực thi**. Thời gian thực tế còn phụ thuộc DNS/TLS, connection pool, HTTP/1.1 hay HTTP/2, giới hạn máy chủ, băng thông, thread/executor, server xử lý song song hay tuần tự, tải máy và chính sách retry.

Mục tiêu của `allOf` là diễn đạt **"cần tất cả"**. Nó không làm những tác vụ phụ thuộc nhau trở thành độc lập, không bảo đảm giảm latency trong mọi tình huống và không thay thế giới hạn số request đồng thời.

## 7. Tập số lượng yêu cầu động: dùng `List` và `CompletableFuture<?>[]`

Khi số endpoint thay đổi theo cấu hình, thay vì truyền thủ công ba biến:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;

List<CompletableFuture<String>> futures = List.of(
        fetch(client, base, "/profile"),
        fetch(client, base, "/orders"),
        fetch(client, base, "/settings"));

CompletableFuture<Void> all =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0]));

CompletableFuture<List<String>> results = all.thenApply(ignored ->
        futures.stream()
                .map(CompletableFuture::join)
                .collect(Collectors.toList()));
```

Đây là **đoạn trong phương thức** đã có `client` và `base`. Ý nghĩa:

1. `List.of(...)` giữ ba future. Tất cả đã được tạo qua `fetch/sendAsync` trước khi gọi `allOf`.
2. `toArray(new CompletableFuture<?>[0])` đưa chúng về varargs array mà `allOf` yêu cầu.
3. `all.thenApply(...)` chỉ chạy khi tất cả hoàn thành **bình thường**.
4. `join()` lúc đó lấy dữ liệu của các future đã xong, không khởi phát thêm request.
5. `Collectors.toList()` tạo `List<String>` có kết quả theo thứ tự của danh sách `futures`, **không theo thứ tự response đến**.

Trong Java 11, dùng `collect(Collectors.toList())`. `Stream.toList()` là API được thêm ở Java 16, nên **không dùng nếu cần biên dịch `--release 11`**.

Với danh sách đã biết số lượng lớn, cần kiểm soát concurrency thay vì tạo hàng nghìn request cùng lúc. `allOf` bản thân không có mức giới hạn số future hay semaphore.

### Tập rỗng

```java
List<CompletableFuture<String>> futures = List.of();

CompletableFuture<Void> all = CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0]));

System.out.println(all.isDone()); // true
```

Nếu ứng dụng cần một danh sách kết quả rỗng, có thể tạo tiếp stage `thenApply` trả `List.of()`; không cần coi tập rỗng là lỗi trừ khi **nghiệp vụ** yêu cầu ít nhất một endpoint.

## 8. Lỗi và cách tổng hợp: fail batch hay cho phép kết quả từng phần?

### 8.1. Khi một future lỗi, `allOf` cũng lỗi

`allOf` hoàn thành **sau khi tất cả future thành phần hoàn thành**, nhưng nếu ít nhất một thành phần hoàn thành exceptionally, future tổng hợp cũng exceptionally. Khi gọi `join()`:

```java
try {
    all.join();
} catch (CompletionException ex) {
    Throwable root = ex.getCause();
    System.err.println(root);
}
```

`join()` sử dụng exception không checked; trong các tình huống bị hủy có thể gặp `CancellationException`, nên luồng xử lý lỗi thực tế cũng cần chính sách cancellation. `get()` là phương án khác nhưng ném `InterruptedException` và `ExecutionException` (checked), cần xử lý khác.

Nếu nhiều thành phần cùng lỗi, `allOf` **không tự tạo một danh sách đầy đủ tất cả lỗi**. Nguyên nhân xuất hiện trên future tổng hợp chỉ phản ánh một lỗi; khi cần chẩn đoán đầy đủ, kiểm tra outcome của **từng future**.

Không nhầm `allOf` với hệ thống transaction: request đã thành công không tự rollback khi request khác lỗi. HTTP POST/PUT có side effect càng cần cơ chế idempotency/compensation riêng do hệ thống thiết kế.

### 8.2. Ngăn HTTP status xấu đi qua nhánh thành công

`sendAsync` hoàn thành bình thường với `HttpResponse<String>` cả khi response status `404`. Để "batch thành công" có nghĩa tất cả API trả status được chấp nhận, hãy thực hiện chuyển đổi ở **mỗi request** trước `allOf`:

```java
CompletableFuture<String> profile = fetch(...);
CompletableFuture<String> orders = fetch(...);

CompletableFuture<Void> all =
        CompletableFuture.allOf(profile, orders);
```

`fetch(...)` ở ví dụ trên kiểm tra `statusCode()` và throw nếu != 200. Với API có status hợp lệ khác (201, 204, 206...), điều chỉnh điều kiện theo contract. Ví dụ `204 No Content` thường không có body; đừng áp logic `200 + body phải có` lên tất cả HTTP endpoint.

### 8.3. Kết quả từng phần bằng `exceptionally`

Nếu màn hình cho phép một phần dữ liệu thiếu nhưng vẫn hiển thị phần còn lại, chuyển lỗi của **mỗi request** thành một giá trị dự phòng:

```java
CompletableFuture<String> profile = fetch(
        client, base, "/profile");

CompletableFuture<String> optionalOrders = fetch(
        client, base, "/missing")
        .exceptionally(error -> "ORDERS_UNAVAILABLE");

CompletableFuture<Void> all =
        CompletableFuture.allOf(profile, optionalOrders);

CompletableFuture<String> overview = all.thenApply(ignored ->
        profile.join() + " | " + optionalOrders.join());
```

Khi `fetch("/missing")` hoàn thành exceptionally, `exceptionally(...)` chạy và tạo future tiếp theo **hoàn thành bình thường** với giá trị `"ORDERS_UNAVAILABLE"`. Vì thế `allOf(profile, optionalOrders)` có thể thành công.

Phải chọn rõ ngữ nghĩa:

- **Tất cả bắt buộc:** để exception lan truyền; không tạo dashboard giả đủ dữ liệu.
- **Một số nguồn tùy chọn:** dùng fallback từng nguồn, có biểu diễn rõ `unavailable`.
- **Cần biết nguồn nào lỗi và nguyên nhân:** dùng `handle((value, error) -> ...)` để chuyển mỗi future thành một đối tượng kết quả có `success/error`, rồi tổng hợp chúng.

Không nên dùng `allOf(...).exceptionally(error -> null)` và ngay sau đó `join()` toàn bộ future thành phần: bước "nuốt" lỗi của `allOf` không biến các future lỗi thành thành công; `join()` trên future lỗi vẫn ném exception.

### 8.4. Không tự động hủy request độc lập còn lại

`allOf` không tự động dừng/cancel những future HTTP đang chạy khi một thành phần gặp exception. Các request độc lập có thể tiếp tục và hoàn thành, như `sibling=PROFILE` trong chương trình mẫu.

Nếu chính sách nghiệp vụ là dừng các request không còn cần thiết, ứng dụng phải thiết kế logic cancellation/timeout phù hợp. Lưu ý cancellation của `CompletableFuture` và việc hủy I/O HTTP thực tế **không phải một transaction rollback bảo đảm**: một request có thể đã được server nhận hoặc xử lý trước thời điểm hủy.

## 9. Timeout: tổng thể batch khác timeout của từng request

Một request có thể bị treo hoặc phản hồi rất chậm. Nếu không giới hạn chờ, `allOf` cũng có thể chưa hoàn thành trong thời gian không mong muốn.

Có hai cấp timeout thường thấy.

**Timeout của mỗi HTTP request:**

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

`HttpRequest.Builder.timeout(Duration)` thiết lập giới hạn thời gian của request theo API Java. Với lỗi timeout, future `sendAsync` hoàn thành exceptionally (ví dụ `HttpTimeoutException`).

**Timeout của bước chờ batch:**

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(profile, orders, settings);

CompletableFuture<Void> bounded =
        all.orTimeout(15, TimeUnit.SECONDS);
```

`orTimeout` đã có trong Java 11. Nó có thể làm future được gọi hoàn thành exceptionally với `TimeoutException` nếu chưa xong sau thời hạn; **không đảm bảo mọi request HTTP nền đã bị hủy**. Đây là timeout ở mức future/chính sách chờ, khác với timeout vận hành của từng request.

`orTimeout` **thay đổi chính future được gọi** rồi trả lại nó; nếu muốn tạo stage có hành vi thời hạn riêng mà không chủ ý thay đổi future gốc, hãy cân nhắc thiết kế bao quanh có kiểm soát thay vì mặc định đây là phép copy.

Không áp thời hạn bất kỳ chỉ để tránh chờ: timeout phải phù hợp SLA, kích thước payload, hành vi retry và điều kiện kết nối. Với hàng nghìn request, nên giới hạn concurrency (ví dụ semaphore, bounded worker pool hoặc batching) để tránh gây tải đột biến cho client/server.

## 10. Thread, callback và lý do không block trong pipeline bất đồng bộ

Các phương thức `thenApply`, `thenAccept`, `thenRun` không có hậu tố `Async` có thể được thực thi trên thread hoàn tất stage trước đó hoặc một thread gọi hành động hoàn tất. Vì vậy, **không nên đặt công việc dài hoặc blocking I/O tùy tiện trong callback của HTTP response**.

Trong ví dụ:

```java
CompletableFuture<String> summary =
        CompletableFuture.allOf(profile, orders, settings)
                .thenApply(ignored ->
                        profile.join() + orders.join() + settings.join());
```

Các lời gọi `join()` trong callback là hợp lý vì **barrier đã hoàn thành bình thường** và các future thành phần đã có kết quả. Callback chỉ ghép dữ liệu nhỏ, không chặn chờ request còn thiếu.

Nếu sau khi nhận dữ liệu cần parse JSON rất lớn, tính toán nặng hoặc truy cập blocking service khác, hãy cân nhắc `thenApplyAsync(..., executor)` với một `Executor` được cấu hình/bounded đúng nhu cầu.

```java
// Phần minh họa: executor do ứng dụng sở hữu và quản lý.
CompletableFuture<Result> mapped = all.thenApplyAsync(
        ignored -> transform(profile.join(), orders.join()),
        executor);
```

`Result` và `transform` ở đây là **ký hiệu minh họa**, không phải code compile độc lập. `thenApplyAsync` không làm kết quả đúng hơn; nó đổi nơi chạy callback để quản lý tải, còn việc chọn executor, đóng tài nguyên và giới hạn work queue là trách nhiệm ứng dụng.

### Trong web framework hoặc UI

Nếu API của ứng dụng hỗ trợ async, thường nên **trả về `CompletionStage`/`CompletableFuture`** thay vì gọi `all.join()` bên trong thread xử lý request/UI. `join()` chỉ hợp lý ở ranh giới đồng bộ rõ ràng (lệnh CLI, test, job đồng bộ) hoặc khi các future đã biết hoàn tất.

Nếu gọi `join()` trên UI thread, có thể làm giao diện đóng băng. Nếu gọi `join()` bên trong thread pool quá nhỏ đang thực hiện chính các tác vụ cần được chờ, có thể gây nghẽn hoặc deadlock ở cấp ứng dụng.

## 11. `allOf`, `thenCombine`, `thenCompose` và `anyOf`: chọn đúng mối quan hệ

| API | Quan hệ giữa các tác vụ | Đầu ra | Khi chọn |
| --- | --- | --- | --- |
| `CompletableFuture.allOf(a,b,c)` | Cần **tất cả** hoàn thành; không tự truyền kết quả | `CompletableFuture<Void>` | Gom 3+ tác vụ độc lập hoặc tập động |
| `a.thenCombine(b, fn)` | Hai tác vụ có thể chạy độc lập; cần cả hai kết quả | `CompletableFuture<R>` | Ghép trực tiếp kết quả của đúng hai tác vụ |
| `a.thenCompose(fn)` | Tác vụ B phụ thuộc **kết quả của A** | `CompletableFuture<R>` | Phải lấy token/id ở A mới xây request B |
| `CompletableFuture.anyOf(a,b,...)` | Chỉ cần **một** future hoàn thành | `CompletableFuture<Object>` | Race/first completion theo ngữ nghĩa API; cần xử lý kiểu và exception |
| `a.thenApply(fn)` | Chuyển đổi kết quả của **một** tác vụ | `CompletableFuture<R>` | Parse body hoặc validate response của request đó |

### Độc lập: dùng `allOf`

Ba request tìm hồ sơ, cấu hình, thống kê không phụ thuộc dữ liệu nhau:

```text
profile ───┐
orders  ───┼─ allOf ── combine
settings───┘
```

### Phụ thuộc: dùng `thenCompose`

Request B phải biết ID trả về từ request A:

```java
CompletableFuture<String> result = fetchUserId(client)
        .thenCompose(id -> fetchOrdersForUser(client, id));
```

Đoạn trên **minh họa pseudocode ở cấp method**; `fetchUserId`/`fetchOrdersForUser` là các hàm ứng dụng tự định nghĩa. `thenCompose` bảo đảm request thứ hai chỉ được khởi phát sau khi có ID. Nếu cố dùng `allOf` cho hai request phụ thuộc nhau, có thể chưa có đủ dữ liệu để xây request B hoặc phải làm workaround không cần thiết.

### Hai tác vụ độc lập: `thenCombine` tiện hơn

```java
CompletableFuture<String> combined =
        futureA.thenCombine(futureB, (a, b) -> a + " / " + b);
```

Ở đây kết quả `a`, `b` đi thẳng vào function; không cần gọi `join()` thủ công. Khi số future lớn hoặc thay đổi động, `allOf` cùng bước gom `List` thường rõ ràng hơn.

### `anyOf` không có nghĩa "chỉ cần một request thành công"

`anyOf` hoàn thành khi **một future bất kỳ hoàn thành** (bình thường hoặc exceptionally). Nếu future đầu tiên hoàn thành lỗi, `anyOf` cũng có thể hoàn thành lỗi dù những future khác sau đó thành công. Nếu nghiệp vụ yêu cầu "kết quả thành công đầu tiên", phải viết cơ chế riêng để bỏ qua lỗi và xử lý cancellation thích hợp; không nhầm nó với `anyOf` mặc định.

## 12. Thiết kế aggregator HTTP đủ tin cậy

Một service tổng hợp nhiều API không chỉ cần `allOf`. Cần xác định contract tại từng tầng:

### Request

- Endpoint/URI được phép; không ghép URL từ dữ liệu không tin cậy nếu thiếu validation, tránh SSRF.
- Tái sử dụng `HttpClient` thay vì tạo một client cho từng request.
- Dùng timeout/retry phù hợp. Với request có side effect (POST/PUT), retry phải xét idempotency.
- Giới hạn request đồng thời; không gửi cùng lúc hàng chục nghìn HTTP request chỉ vì `sendAsync` hỗ trợ async.

### Response

- Đọc status code và phân biệt success/expected not-found/server failure theo từng API.
- Chọn `BodyHandler<T>` theo kiểu dữ liệu thực; `ofString(UTF_8)` chỉ dùng khi server thực sự gửi body text UTF-8.
- Giới hạn kích thước body, xử lý JSON/media type, điều kiện response rỗng.
- Không coi body được trả về là dữ liệu đã tin cậy; validate schema và quyền dữ liệu.

### Aggregation

- Xác định **all-required** hay **partial success**.
- Nếu all-required: giữ future lỗi, cho allOf lỗi, báo thông tin hữu ích.
- Nếu partial success: chuyển từng future thành outcome có success/failure và nguyên nhân, không âm thầm hợp thức hóa dữ liệu bị thiếu.
- Giữ thứ tự kết quả theo danh sách yêu cầu, không theo thời điểm hoàn thành nếu business contract cần thứ tự.
- Với nhiều lỗi, ghi nhận từng failure thay vì chỉ lấy `allOf.join().getCause()`.
- Tránh blocking trong callback; chọn executor riêng cho CPU-bound parsing nếu cần.

### Monitoring và cancellation

- Đo latency từng endpoint, tổng latency, tỉ lệ lỗi, timeouts; dữ liệu quan sát phải không lộ token/body nhạy cảm.
- Không cho rằng cancel một `CompletableFuture` có thể quay ngược request đã được server xử lý.
- Dừng/cleanup tài nguyên của ứng dụng theo vòng đời; phát hành kết quả tổng hợp sau khi đã xác định outcome toàn bộ các nhánh cần thiết.

## 13. Những lỗi hay gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Các request vẫn chạy tuần tự | Gọi `join`/`get` ngay sau mỗi `sendAsync` | Khởi phát tất cả request trước; dùng `allOf` làm barrier |
| Biến `results` không thể nhận `List` từ `allOf` | Kiểu trả về là `CompletableFuture<Void>` | Sau `allOf` dùng `thenApply` để lấy kết quả từng future |
| Batch "thành công" dù một API trả 500 | `sendAsync` vẫn trả `HttpResponse` bình thường khi có status HTTP lỗi | Xác thực status của mỗi future bằng `thenApply` trước khi `allOf` |
| `allOf.join()` ném `CompletionException` | Ít nhất một future hoàn thành exceptionally | Bắt và xử lý nguyên nhân; xác định có cho phép partial success hay không |
| Cố `join()` từng future sau khi "nuốt" lỗi của allOf | `allOf.exceptionally(...)` không biến future con thành success | Dùng `handle`/`exceptionally` trên từng thành phần trước `allOf` |
| Chỉ log một lỗi dù nhiều endpoint lỗi | Future tổng hợp không là danh sách exceptions | Thu thập outcome từng future để chẩn đoán toàn bộ |
| Chờ batch quá lâu | Một request chưa hoàn thành hoặc timeout thiếu | Đặt request timeout và batch deadline theo SLA |
| Timeout batch nhưng request vẫn hoạt động | Timeout stage không nhất thiết hủy tác vụ I/O | Thiết kế cancellation/lifecycle riêng |
| UI bị đơ | Gọi `join()` trên UI thread | Trả future và cập nhật UI trong callback phù hợp |
| CPU xử lý kết quả làm chậm I/O | Callback `thenApply` nặng trên thread hoàn tất stage | Chuyển CPU-bound work sang `thenApplyAsync` với executor kiểm soát |
| Kết quả ghép thứ tự bất định | Gom theo thứ tự callback hoàn thành | Giữ danh sách future theo thứ tự đầu vào, lấy result sau barrier |
| Chạy cùng lúc quá nhiều requests | `allOf` không giới hạn concurrency | Batching, semaphore, rate limiter, queue/executor bounded |
| Gọi `Stream.toList()` không biên dịch với Java 11 | API chỉ có từ Java 16 | Dùng `collect(Collectors.toList())` |
| Dùng `allOf` cho request phụ thuộc nhau | Request thứ hai chưa có input từ request thứ nhất | Dùng `thenCompose` |
| Nghĩ `anyOf` trả về success đầu tiên | `anyOf` trả completion đầu tiên kể cả lỗi | Viết first-success logic riêng theo business |
| Gọi `allOf` với null | Một future/mảng đầu vào là `null` | Đảm bảo mọi future được tạo hợp lệ, validate dữ liệu đầu vào |

## 14. Câu hỏi tự kiểm tra (kèm đáp án)

**1.** Tại sao ba `sendAsync` nên được gọi trước khi `join`?

**Đáp án:** Vì chúng độc lập. Khởi phát cả ba trước cho phép các hoạt động mạng overlap; `join` ngay sau request đầu sẽ chặn việc khởi phát request tiếp theo.

**2.** `CompletableFuture.allOf(a, b, c)` trả kiểu gì?

**Đáp án:** `CompletableFuture<Void>`. Khi thành công, giá trị của nó là `null`; kết quả riêng nằm trong `a`, `b`, `c`.

**3.** Một future trả `HttpResponse<String>` với status 404. `allOf` có tự lỗi không?

**Đáp án:** Không, nếu future thành phần hoàn thành bình thường. Phải chủ động kiểm tra status, ví dụ `thenApply` throw exception khi status không hợp lệ.

**4.** Nếu `b` lỗi, `allOf(a,b,c)` có tự hủy `a` và `c` không?

**Đáp án:** Không. `allOf` chỉ tổng hợp hoàn thành; cancellation/rollback phải được ứng dụng thiết kế riêng.

**5.** Sau khi `allOf(a,b,c)` hoàn thành bình thường, dùng `a.join()` bên trong `thenApply` có làm chờ mạng lâu nữa không?

**Đáp án:** Không cần chờ một request chưa hoàn thành nữa, vì barrier đã chứng minh tất cả thành phần hoàn thành bình thường. `join()` chỉ truy xuất kết quả.

**6.** Với một `List<CompletableFuture<String>>` có số phần tử động, truyền gì vào `allOf`?

**Đáp án:** `CompletableFuture.allOf(futures.toArray(new CompletableFuture<?>[0]))`.

**7.** Khi một request lỗi nhưng các request khác vẫn có dữ liệu hữu ích, chọn hướng nào?

**Đáp án:** Xác định contract partial success. Dùng `handle` hoặc `exceptionally` **trên từng future** để biến lỗi thành outcome/fallback có thể nhận diện, rồi `allOf` trên các future đã được xử lý.

**8.** `allOf(...).orTimeout(...)` có bảo đảm server đã ngừng xử lý request không?

**Đáp án:** Không. Timeout/cancel của future không đồng nghĩa thu hồi thao tác HTTP đã tới server. Cần chính sách cancellation/idempotency rõ ràng.

**9.** Hai request độc lập cần ghép trực tiếp kết quả bằng hàm `f(a,b)`, API nào gọn hơn?

**Đáp án:** `thenCombine`. Với nhiều request hoặc tập động, `allOf` kết hợp bước gom kết quả phù hợp hơn.

**10.** Request B cần ID do request A trả về. Có nên gửi B đồng thời với A bằng `allOf` không?

**Đáp án:** Không, vì B phụ thuộc A. Dùng `thenCompose` để xây và gửi B sau khi A trả ID.

**11.** `CompletableFuture.allOf()` không có đối số sẽ treo hay hoàn thành?

**Đáp án:** Hoàn thành ngay, bình thường, với giá trị `null`.

**12.** Dùng `allOf` cho 10.000 requests có bảo đảm hệ thống tự giới hạn request đồng thời không?

**Đáp án:** Không. `allOf` chỉ là barrier. Cần batching, semaphore/rate limiter hoặc scheduler giới hạn concurrency.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 11 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `allOf`, `join`, `get`, `exceptionally`, `handle`, `thenApply`, `thenCombine`, `thenCompose`, `orTimeout` và định nghĩa exceptional completion.
- [Oracle Java SE 26 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): các hợp đồng cốt lõi của `allOf` tiếp tục được duy trì ở Java hiện hành.
- [Oracle Java SE 11 — `HttpClient`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` trả `CompletableFuture<HttpResponse<T>>`; reuse client và xử lý response.
- [Oracle Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): xây request, `timeout(Duration)`, `GET()` và `build()`.
- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString(Charset)` và các cách nhận body.
- [Oracle Java SE 11 — `HttpResponse`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode()`, `body()` và headers.

**Ghi nhớ:** Với các HTTP request **độc lập**, hãy khởi phát tất cả bằng `sendAsync` trước khi chờ, dùng `CompletableFuture.allOf(...)` làm điểm đồng bộ, sau đó lấy kết quả từ từng future trong `thenApply`/`handle` theo đúng contract. `allOf` không gom kết quả, không tự kiểm tra status HTTP, không tự retry/cancel và không giới hạn concurrency.