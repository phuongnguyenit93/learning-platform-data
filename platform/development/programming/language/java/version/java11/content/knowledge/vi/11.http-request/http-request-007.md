# Timeout theo yêu cầu với `HttpRequest` (Java 11+)

## 1. Vì sao một HTTP request cần timeout riêng?

Trong hệ thống có gọi API, không phải request nào cũng có thể chờ vô hạn. Một endpoint tra cứu thông tin hiển thị cho người dùng thường cần phản hồi nhanh; một tác vụ tạo báo cáo hoặc truyền dữ liệu lớn có thể được phép chờ lâu hơn. **Timeout theo yêu cầu (per-request timeout)** cho phép chỉ định thời hạn riêng cho từng `HttpRequest`, thay vì áp dụng cùng một khoảng thời gian cho tất cả HTTP calls.

Từ **Java 11**, package `java.net.http` cung cấp:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Khi chương trình gửi request bằng `HttpClient.send(...)` hoặc `HttpClient.sendAsync(...)`, timeout đã cấu hình trở thành một phần hợp đồng thực thi request. Nếu hết hạn trước khi nhận được response theo hợp đồng, lời gọi đồng bộ có thể ném `HttpTimeoutException` hoặc future bất đồng bộ hoàn tất với lỗi timeout.

**Phân biệt ba khái niệm:**

1. **Request timeout:** mức thời gian cho *một request cụ thể*, cấu hình ở `HttpRequest.Builder.timeout(Duration)`.
2. **Connection timeout:** mức thời gian dành cho bước thiết lập *kết nối mới*, cấu hình ở `HttpClient.Builder.connectTimeout(Duration)`.
3. **Thời hạn nghiệp vụ đầu-cuối:** toàn bộ thời gian được phép cho một workflow gồm nhiều request, retry, xử lý body, ghi database...; chương trình phải thiết kế riêng nếu cần.

Bài này tập trung vào **timeout theo `HttpRequest`** và chỉ giải thích connection timeout ở mức cần thiết để không nhầm hai cơ chế. Cả API lẫn nguyên tắc này vẫn được sử dụng trên Java hiện hành.

## 2. API `HttpRequest.Builder.timeout(Duration)`

Chữ ký Java 11+:

~~~java
HttpRequest.Builder timeout(Duration duration)
~~~

Ví dụ cấu hình:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(3))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Đây là **đoạn minh họa**, không tự liên hệ mạng; endpoint `example.com` chỉ để thể hiện cách xây request. Để gửi thật, cần `HttpClient` và một dịch vụ phù hợp.

### Những quy tắc quan trọng

- **Giá trị phải dương:** `Duration.ZERO` và duration âm đều không hợp lệ, `timeout(...)` ném `IllegalArgumentException`. Chọn `Duration.ofMillis(150)` hoặc `Duration.ofSeconds(5)` tùy thời hạn thiết kế.
- **Không gọi `timeout(...)`:** tương đương không đặt giới hạn thời gian request ở cấp API này (tài liệu mô tả như thời hạn vô hạn). Điều đó **không có nghĩa request chắc chắn chạy mãi**; các lỗi mạng, interrupt, đóng tài nguyên và chính sách bên ngoài vẫn có thể kết thúc sớm.
- **Là cấu hình của mỗi request:** hai `HttpRequest` sử dụng cùng một `HttpClient` vẫn có timeout khác nhau.
- **`build()` tạo đối tượng request bất biến:** thay đổi builder sau đó không sửa request đã tạo; muốn timeout khác, tạo một request mới.
- **Không tự gửi:** `HttpRequest.Builder.timeout(...)` và `build()` chưa mở kết nối. Timeout thực sự có ý nghĩa khi request bắt đầu được gửi.
- **`request.timeout()` trả về `Optional<Duration>`**, không phải `Duration` trực tiếp; không có cấu hình thì `Optional.empty()`.

Kiểm tra cấu hình:

~~~java
Duration limit = Duration.ofMillis(750);
HttpRequest req = HttpRequest.newBuilder(
                URI.create("https://example.com/data"))
        .timeout(limit)
        .GET()
        .build();

System.out.println(req.timeout().orElseThrow().toMillis()); // 750
~~~

Phần này là **mã minh họa** cần imports phù hợp, không phát sinh HTTP call. Không nhầm cách đọc `request.timeout()` với việc hỏi request còn bao nhiêu thời gian: API chỉ trả về *giá trị đã cấu hình*, không cung cấp một đồng hồ đếm ngược đang chạy.

### `Duration` là đơn vị thời gian, không phải số nguyên mili giây

~~~java
.timeout(Duration.ofSeconds(2))
.timeout(Duration.ofMillis(200))
.timeout(Duration.ofMinutes(1))
~~~

Các dòng trên là **những lựa chọn thay thế**, không phải mẫu gọi liên tiếp ba lần. Khi gọi lặp, builder nhận cấu hình cuối cùng. `Duration.ofMillis(200)` nghĩa là 200 mili giây; `Duration.ofSeconds(2)` nghĩa là 2.000 mili giây. Không truyền chuỗi `"2s"`, số `2000` trần hoặc `TimeUnit` vào phương thức vốn yêu cầu `Duration`.

**Đừng chọn một con số ngẫu nhiên quá nhỏ:** timer bị ảnh hưởng bởi độ trễ mạng, tải máy, bước handshake và thời gian xử lý của server. Mốc thích hợp phải dựa trên mục tiêu độ trễ, đặc điểm endpoint và đo đạc thực tế.

## 3. `HttpRequest.timeout` khác `HttpClient.connectTimeout` như thế nào?

Cấu hình một client:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
~~~

Cấu hình request riêng:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

Hai đoạn mã là **mã minh họa** (cần imports, `uri` cụ thể). Bảng sau tách đúng trách nhiệm:

| Tiêu chí | `connectTimeout` của `HttpClient` | `timeout` của `HttpRequest` |
| --- | --- | --- |
| Cấp cấu hình | Theo client | Theo từng request |
| Tập trung vào | **Thiết lập kết nối mới** tới đích/proxy/TLS theo hợp đồng và implementation | **Nhận response cho request** trong thời hạn cho phép |
| Khi tái sử dụng kết nối | Thường **không có tác dụng** do không phải kết nối mới | Vẫn có tác dụng với request gửi qua kết nối đó |
| Khi hết hạn | `HttpConnectTimeoutException` | `HttpTimeoutException` (hoặc kiểu con tùy giai đoạn lỗi) |
| Khi không cấu hình | Không giới hạn riêng về bước connect bằng setting này | Không giới hạn riêng về request bằng setting này |
| Có phải read timeout cho từng byte? | Không | Không nên suy diễn như vậy, nhất là body streaming |

**Kết nối là một phần của quá trình thực thi request**, vì thế các giới hạn có thể cùng tác động. Không được cộng cơ học `2s connect + 5s request = 7s tổng thời gian`; trên implementation hiện hành, request timeout có thể bao gồm cả thời gian cần để có kết nối.

Theo tài liệu Java hiện hành, thời gian của `HttpRequest.timeout` được tính **từ lúc request bắt đầu thực thi**, ít nhất đến khi đối tượng `HttpResponse` được xây dựng; thời gian tìm kết nối để gửi và nhận response headers nằm trong khoảng đó. JDK built-in hiện hành áp dụng timeout cho đến khi body subscriber hoàn tất. Tuy vậy, khi dùng các `BodyHandler` dạng streaming, **đừng coi timeout này là lời bảo đảm rằng toàn bộ thao tác đọc stream sau đó luôn bị giới hạn bởi đúng Duration đã đặt**. Phần 8 trình bày giới hạn này.

### Ngoại lệ connection timeout là một dạng request timeout

`java.net.http.HttpConnectTimeoutException` **kế thừa `HttpTimeoutException`**, nên nếu muốn phân biệt ở `catch`:

~~~java
try {
    // client.send(request, handler)
} catch (HttpConnectTimeoutException e) {
    // Quá hạn khi thiết lập kết nối mới.
} catch (HttpTimeoutException e) {
    // Quá hạn HTTP request ở giai đoạn khác.
}
~~~

Đây là **mẫu ý tưởng**; hai exception phải được import, đoạn `try` cần chứa lời gọi thật có thể ném lỗi. Nếu chỉ `catch(HttpTimeoutException)` trước thì nhánh `HttpConnectTimeoutException` phía sau không thể đạt tới.

## 4. Cách dùng `send()` đồng bộ và xử lý timeout

Chữ ký thường dùng:

~~~java
HttpResponse<String> response =
        client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
~~~

Lệnh `send` chặn thread đang gọi trong khi chờ response theo `BodyHandler` đã chọn. Với `BodyHandlers.ofString`, body được tích lũy thành chuỗi trước khi trả kết quả theo hợp đồng handler.

Một mẫu xử lý lỗi:

~~~java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    if (response.statusCode() >= 200 && response.statusCode() < 300) {
        // Xử lý response.body().
    } else {
        // Xử lý HTTP status 4xx/5xx theo hợp đồng API.
    }
} catch (HttpConnectTimeoutException e) {
    // Connection establishment đã vượt deadline.
} catch (HttpTimeoutException e) {
    // Request đã quá hạn.
} catch (IOException e) {
    // Lỗi mạng/I/O khác.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Trả về/truyền lỗi/hủy theo chính sách nghiệp vụ.
}
~~~

Đây là **đoạn mã minh họa**, phải khai báo `client`, `request` và imports trong lớp thực tế. Nhánh `InterruptedException` khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` khi tầng xử lý này không ném tiếp ngoại lệ; không nuốt gián đoạn một cách vô điều kiện.

**HTTP 408 (Request Timeout) và 504 (Gateway Timeout) không phải `HttpTimeoutException`.** Nếu server/proxy thực sự trả về HTTP status 408/504, chương trình có thể nhận `HttpResponse` chứa `statusCode() == 408` hoặc `504`. `HttpTimeoutException` là tình huống **client** vượt thời hạn đã cấu hình khi chờ response; có thể chưa có response để đọc status.

Cũng không được mặc định rằng sau `HttpTimeoutException` thì request “chưa đến server”: phía server **có thể đã nhận và xử lý** request, nhưng client chưa nhận được kết quả kịp thời.

## 5. Cách dùng `sendAsync()` và `CompletableFuture`

`sendAsync(...)` trả về:

~~~java
CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
~~~

Timeout ở `request` **không bị bỏ qua** khi gọi `sendAsync`. Nếu quá hạn, future có thể hoàn tất **exceptionally**, với nguyên nhân là `HttpTimeoutException`. Lời gọi tạo future không chặn cho đến khi có response; nhưng **`join()`, `get()` hoặc code phía sau có thể chặn**.

Ví dụ quan sát kết quả:

~~~java
try {
    HttpResponse<String> response = pending.join();
    System.out.println(response.statusCode());
} catch (CompletionException e) {
    Throwable cause = e.getCause();
    if (cause instanceof HttpTimeoutException) {
        System.out.println("Request timed out");
    } else {
        throw e;
    }
}
~~~

Đoạn này là **mã minh họa**; `pending` đã tạo từ `sendAsync`, cần import `CompletionException`/`HttpTimeoutException`. `join()` ném `CompletionException` bọc lỗi khi future hoàn tất thất bại (khi bị hủy có thể gặp `CancellationException`). Nếu dùng `get()`, lỗi được bọc bởi `ExecutionException` và còn có thể gặp `InterruptedException`.

Khi dùng chuỗi:

~~~java
CompletableFuture<String> result = client
        .sendAsync(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .thenApply(response -> {
            int status = response.statusCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException("HTTP " + status);
            }
            return response.body();
        });
~~~

**Lưu ý:** Exception của `thenApply` là lỗi tầng ứng dụng, khác lỗi transport và timeout. Đừng ép mọi `CompletionException` thành `HttpTimeoutException`. Trong code production nên quan sát future thất bại bằng `whenComplete`, `handle` hoặc luồng xử lý tương đương và phân loại đúng nguyên nhân.

### `CompletableFuture.orTimeout` có thay cho request timeout được không?

Không hoàn toàn. `orTimeout(Duration)` không phải chữ ký Java; `CompletableFuture.orTimeout(long, TimeUnit)` được dùng để **giới hạn thời gian future hoàn tất**:

~~~java
pending.orTimeout(3, TimeUnit.SECONDS);
~~~

Đây là mẫu minh họa, cần import `TimeUnit`. Nó có thể làm future hoàn tất với `TimeoutException` nếu chưa xong, nhưng **không tương đương** với việc cấu hình deadline thực thi request ở `HttpRequest.Builder.timeout`. Không mặc định rằng timeout của phép chờ `get(timeout, unit)` hoặc của future sẽ hủy sạch mọi công việc HTTP và hoàn tác tác động trên server.

Phân biệt:

- `request.timeout(Duration)` — thời hạn của **HTTP request** do Java HTTP Client xử lý.
- `pending.orTimeout(...)` — thời hạn để **future hoàn tất** theo `CompletableFuture`.
- `pending.get(timeout, unit)` — thời hạn **thread caller chờ** kết quả, không tự bảo đảm HTTP request bị hủy.
- “Timeout nghiệp vụ” — có thể phải bao gồm cả retry, parsing, streaming và các bước sau HTTP.

## 6. Ví dụ hoàn chỉnh Java 11+: mỗi request có một timeout riêng

Chương trình dưới đây chạy một HTTP server **nội bộ** trên địa chỉ loopback, tự chọn cổng còn trống. Nó tạo hai endpoint:

- `/fast` trả lời ngay với body `OK`.
- `/slow` trì hoãn khoảng một giây trước khi tạo response.

Cùng một `HttpClient` được dùng cho request nhanh timeout 5 giây và request chậm timeout 150 mili giây. Kết quả đồng bộ và bất đồng bộ được kiểm tra riêng. **Không cần internet, API key hay server công cộng.**

Tạo tệp **RequestTimeoutDemo.java**:

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
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);
        server.createContext("/fast", exchange -> respond(exchange, "OK"));
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_000);
                respond(exchange, "SLOW");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                exchange.close();
            } catch (IOException e) {
                exchange.close(); // Client may have timed out and disconnected.
            }
        });
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpRequest fast = HttpRequest.newBuilder(base.resolve("fast"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            System.out.println("fastTimeoutMs="
                    + fast.timeout().orElseThrow().toMillis());
            HttpResponse<String> response = client.send(
                    fast, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("fastStatus=" + response.statusCode());
            System.out.println("fastBody=" + response.body());

            HttpRequest slow = HttpRequest.newBuilder(base.resolve("slow"))
                    .timeout(Duration.ofMillis(150))
                    .GET()
                    .build();
            System.out.println("slowTimeoutMs="
                    + slow.timeout().orElseThrow().toMillis());
            try {
                client.send(slow,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));
                System.out.println("syncTimeout=false");
            } catch (HttpTimeoutException expected) {
                System.out.println("syncTimeout=true");
            }

            CompletableFuture<HttpResponse<String>> pending =
                    client.sendAsync(
                            slow, HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            try {
                pending.join();
                System.out.println("asyncTimeout=false");
            } catch (CompletionException e) {
                System.out.println("asyncTimeout="
                        + (e.getCause() instanceof HttpTimeoutException));
            }

            System.out.println("connectTimeoutMs="
                    + client.connectTimeout().orElseThrow().toMillis());
            HttpRequest withoutTimeout = HttpRequest.newBuilder(
                    base.resolve("fast")).GET().build();
            System.out.println("unsetTimeout="
                    + withoutTimeout.timeout().isEmpty());

            try {
                HttpRequest.newBuilder(base.resolve("fast"))
                        .timeout(Duration.ZERO);
                System.out.println("zeroRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("zeroRejected=true");
            }
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }

    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        try {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }
}
~~~

**Biên dịch và chạy** bằng JDK có module `jdk.httpserver` (một bản JDK đầy đủ thường có; runtime tùy biến có thể không có):

~~~bash
javac --release 11 --add-modules jdk.httpserver RequestTimeoutDemo.java
java --add-modules jdk.httpserver RequestTimeoutDemo
~~~

**Stdout đã kiểm chứng** trên JDK hiện đại với biên dịch tương thích Java 11:

~~~text
fastTimeoutMs=5000
fastStatus=200
fastBody=OK
slowTimeoutMs=150
syncTimeout=true
asyncTimeout=true
connectTimeoutMs=2000
unsetTimeout=true
zeroRejected=true
~~~

### Tại sao kết quả này đúng?

1. `fastTimeoutMs=5000`: `HttpRequest fast` có deadline 5 giây; `request.timeout()` đọc lại cấu hình dưới dạng `Optional<Duration>`.
2. `fastStatus=200` và `fastBody=OK`: server trả lời ngay và request hoàn tất trong khoảng thời gian cho phép.
3. `slowTimeoutMs=150`: request thứ hai dùng cùng client nhưng timeout chỉ 150 mili giây. Nó **không kế thừa** 5 giây từ request thứ nhất.
4. `syncTimeout=true`: server cố ý ngủ khoảng 1.000 mili giây trước khi trả response, nên lời gọi `client.send(slow, ...)` vượt mức 150 mili giây và ném `HttpTimeoutException`.
5. `asyncTimeout=true`: `sendAsync` cũng chịu cùng timeout, nhưng lỗi xuất hiện qua future và `CompletionException` tại `join()`.
6. `connectTimeoutMs=2000`: timeout 2 giây thuộc cấu hình của client, chỉ liên quan bước thiết lập kết nối mới. Nó không đổi giá trị 150 mili giây của request chậm.
7. `unsetTimeout=true`: một `HttpRequest` không gọi `timeout` có `request.timeout().isEmpty() == true`.
8. `zeroRejected=true`: Java từ chối `Duration.ZERO` khi đưa vào `HttpRequest.Builder.timeout`.
9. `server.stop(0)` và `workers.shutdownNow()` kết thúc server thử nghiệm; thread pool được quản lý rõ ràng.

Server dùng HTTP bình thường trên **loopback** và một cổng tạm, không gửi dữ liệu ra Internet. Trên môi trường bị hạn chế quyền tạo socket hoặc không có module `jdk.httpserver`, ví dụ không chạy được nếu chưa điều chỉnh môi trường.

**Lưu ý độ ổn định:** Timeout là đo thời gian thực; một máy quá tải hoặc môi trường network bị can thiệp có thể làm ngay cả request nhanh thất bại. Ví dụ chọn 5 giây cho response nhanh và độ trễ 1 giây đối với request có timeout 150ms để tạo cách biệt rõ ràng. Trong bài kiểm thử tự động ở sản phẩm, ngoài kết quả mong muốn còn cần kiểm soát môi trường và chấp nhận rằng deadline trên scheduler không chính xác tuyệt đối đến từng mili giây.

## 7. Chính xác thì timeout bao phủ những giai đoạn nào?

Luồng trao đổi HTTP điển hình:

~~~text
Gọi client.send/sendAsync
         |
         v
Lấy kết nối đang có hoặc tạo kết nối mới
         |
         v
Gửi request headers / body
         |
         v
Nhận HTTP response headers
         |
         v
Tạo HttpResponse, xử lý response body theo BodyHandler
         |
         v
Hoàn tất thao tác send/future (tùy BodyHandler)
~~~

Tài liệu Java hiện hành giải thích yêu cầu tối thiểu của per-request timeout: **từ lúc request bắt đầu thực thi đến ít nhất lúc `HttpResponse` được tạo**, bao gồm việc có kết nối và nhận response headers. JDK built-in hiện hành đo đến khi **response body subscriber hoàn tất**, nếu có. Đây là mô tả của implementation, **không nên khái quát thành hợp đồng “mọi JDK và mọi kiểu BodyHandler đều tự động giới hạn mọi hoạt động sau đó”**.

### Body nhận toàn bộ vào bộ nhớ

Với:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

`BodyHandlers.ofString` xử lý body thành một `String`. Trong cách dùng thông thường, `send` hoàn tất khi dữ liệu đã được nhận/xử lý cho kiểu body đó, nên timeout giúp hạn chế việc chờ response trong phạm vi HTTP client.

Điểm yếu của việc đọc toàn bộ vào `String` hoặc `byte[]` là **kích thước phản hồi**: một endpoint phản hồi quá lớn có thể tiêu tốn nhiều bộ nhớ. Deadline không thay thế giới hạn kích thước.

### Body dạng streaming

Với:

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Đọc dữ liệu từng phần theo nhu cầu.
}
~~~

Đây là **mã minh họa**, cần import `InputStream` và xử lý `IOException`/`InterruptedException`. Với `ofInputStream`, `HttpResponse` có thể có sớm sau khi headers được nhận trong khi body còn đang được đọc qua `InputStream`. **Không nên coi per-request timeout tương đương “read idle timeout” hoặc deadline cho tất cả các lời gọi `body.read()` tùy ý về sau.**

Nếu cần giới hạn thời gian **toàn bộ việc đọc stream**, phải có chính sách độc lập về tốc độ/độ trễ, cơ chế hủy/đóng stream, giới hạn byte, và kiểm soát deadline tại ứng dụng. Mọi stream body được nhận cần **đọc đến EOF hoặc đóng đúng cách** để trả tài nguyên/kết nối theo hợp đồng.

### HTTP response status có liên quan timeout không?

Mã `200` không chứng minh body đã đọc xong nếu bạn dùng streaming handler. Mã `408` hoặc `504` cũng **không chứng minh client tự hết timeout**, mà chỉ là HTTP response status do server/proxy gửi.

Không dùng status code như công cụ thay thế xử lý `HttpTimeoutException`. Phải phân biệt **lỗi giao thức** (response đến và có status) với **lỗi transport/deadline** (có thể chưa có response).

## 8. Chọn timeout theo yêu cầu nghiệp vụ

Không có con số chung đúng cho mọi request. Một chính sách thực tế thường xem xét:

| Loại thao tác | Tiêu chí chọn thời hạn | Ghi chú |
| --- | --- | --- |
| API tra cứu phục vụ UI | SLO độ trễ người dùng; tail latency | Cân nhắc timeout ngắn và fallback rõ ràng |
| Đọc cấu hình lúc khởi động | Độ quan trọng của cấu hình và hành vi khi mất dịch vụ | Không chờ vô hạn khiến ứng dụng treo |
| POST thay đổi dữ liệu | Tính idempotent, chi phí xử lý, khả năng hoàn tất ở server | Timeout **không chứng minh thao tác thất bại** |
| Gọi phụ trợ trong batch | Deadline của toàn bộ batch và mức ưu tiên | Ngân sách timeout của các bước phải cộng được ở tầng nghiệp vụ |
| Download có body lớn | Thời gian nhận toàn bộ nội dung, giới hạn byte và throughput | Cần handler streaming/file và policy hủy nếu treo |
| Gọi qua proxy/redirect | Số chặng kết nối, DNS/TLS và chính sách redirect | Theo dõi kết quả trên từng endpoint thực |

**Quy tắc chọn:**

1. Xác định **deadline đầu-cuối** của tác vụ, ví dụ thao tác người dùng phải có kết quả trong vài giây.
2. Phân bổ ngân sách cho từng lần HTTP call, bao gồm thời gian khởi tạo kết nối, nhận response và xử lý nội dung sau đó.
3. Đặt `request.timeout(...)` bằng `Duration` dương đủ nhỏ để fail fast khi cần nhưng đủ lớn theo độ trễ bình thường/tail latency.
4. Chọn `client.connectTimeout(...)` riêng cho kết nối mới; không giả định cộng hai timeout.
5. Giới hạn **số retry**, áp dụng backoff/jitter khi phù hợp và đảm bảo tổng thời gian không vượt deadline nghiệp vụ.
6. Ghi lại latency, loại timeout và endpoint ở dạng log/metric an toàn, không in credential hoặc dữ liệu nhạy cảm.

Từ “theo yêu cầu” nghĩa là theo *mục đích của request*, không phải mỗi chỗ trong code tùy ý đặt một con số thiếu lý do.

## 9. Retry sau timeout: chú ý side effect và tính idempotent

Một timeout chỉ nói rằng **client không hoàn tất việc nhận phản hồi theo thời hạn**. Nó không thể cho biết chắc server đã làm đến bước nào. Đây là rủi ro đáng kể khi gửi POST để tạo giao dịch hoặc thay đổi trạng thái.

Ví dụ:

~~~text
Client gửi POST /orders
          |
          v
Server tạo đơn hàng thành công
          |
          v
Response bị chậm, request timeout phía client
          |
          v
Client tự gửi lại POST /orders
          |
          v
Có nguy cơ tạo đơn hàng trùng
~~~

Với GET (thường được thiết kế không gây side effect), retry có thể dễ kiểm soát hơn, nhưng vẫn cần xét tải hệ thống và chính sách lỗi. Với POST/PUT/PATCH, phải xem hợp đồng endpoint và tính idempotent thực tế.

Nếu API hỗ trợ **idempotency key**, caller có thể gắn một khóa ổn định cho cùng thao tác, để server nhận biết request lặp mà không thực hiện side effect hai lần (việc bảo đảm này thuộc hợp đồng server). Không thể “giải quyết” tình trạng trùng chỉ bằng cách tăng timeout, và cũng không thể cho rằng `HttpTimeoutException` cho phép retry vô điều kiện.

**Không chọn timeout vô hạn để tránh retry:** hệ thống có thể bị giữ thread/resource hoặc chờ quá lâu. Thay bằng deadline rõ ràng, trạng thái giao dịch, retry có giới hạn và cơ chế kiểm tra kết quả khi cần.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi/nhầm lẫn | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Gọi `.timeout(0)` hoặc `Duration.ZERO` | API yêu cầu `Duration` dương | Dùng `Duration.ofMillis(n)` với `n > 0` |
| Không đặt timeout vì nghĩ connect timeout đã đủ | `connectTimeout` không giới hạn việc chờ response trên kết nối đã có | Cấu hình thêm `request.timeout` nếu muốn giới hạn request |
| Hiểu timeout là “thời gian server xử lý” | Còn có kết nối, gửi request, truyền headers/body và xử lý subscriber | Tính theo hợp đồng HTTP client |
| Cộng `connectTimeout` + `request.timeout` thành tổng deadline | Hai cơ chế có thể chạy chồng lên nhau | Thiết kế deadline tổng riêng |
| Catch `IOException` trước `HttpTimeoutException` | `HttpTimeoutException` kế thừa `IOException`, nhánh sau unreachable | Catch loại cụ thể trước |
| Catch `HttpTimeoutException` trước `HttpConnectTimeoutException` | Loại connect kế thừa loại timeout | Catch connect timeout trước khi cần phân biệt |
| Xem HTTP 408/504 là Java exception | Đây là HTTP response status | Xử lý `response.statusCode()` và lỗi client riêng |
| `sendAsync` không catch lỗi | Timeout hoàn tất future thất bại | Quan sát `CompletionException`/`ExecutionException` hoặc pipeline lỗi |
| Đặt `pending.orTimeout(...)` rồi nghĩ HTTP hủy hoàn toàn | Future deadline không tương đương HTTP request deadline | Dùng `HttpRequest.timeout` và chính sách cancellation riêng |
| Quên stream body sau `ofInputStream` | Có thể giữ kết nối/resource | Đọc hết hoặc đóng stream |
| Cho rằng timeout chứng minh POST chưa chạy | Server có thể đã xử lý trước khi client hết hạn | Xác minh trạng thái/idempotency key |
| Mỗi request đều tạo client mới | Mất cơ hội tái sử dụng kết nối/config | Tái sử dụng `HttpClient` khi phù hợp |
| Không có timeout cho request quan trọng | Nguy cơ chờ rất lâu | Đặt policy cho từng loại request |
| Timeout rất thấp mà không đo đạc | Request khỏe có thể lỗi do scheduler/mạng | Dựa SLO và kiểm thử độ trễ thực |
| Log toàn bộ URI có token/header bí mật | Rò rỉ thông tin | Chỉ log mã trạng thái, loại lỗi, endpoint đã lọc, duration |
| Nhầm `request.timeout().isEmpty()` với request đã hết hạn | `Optional.empty()` chỉ nghĩa là chưa cấu hình | Đọc đúng `Optional<Duration>` |

### Nếu debug request timeout, bắt đầu từ đâu?

1. In/quan sát `request.method()`, `request.uri()` (đã ẩn tham số nhạy cảm), `request.timeout()` và `client.connectTimeout()`.
2. Phân biệt exception `HttpConnectTimeoutException`, `HttpTimeoutException`, `IOException` khác với response 408/504.
3. Đo **thời gian thật** từ lúc bắt đầu gọi, cùng log phía server/proxy nếu có quyền truy cập.
4. Kiểm tra kết nối cũ có tái sử dụng không, proxy/redirect, TLS, tải server và dung lượng response.
5. Kiểm tra handler loại `ofString`/`ofByteArray` hay streaming `ofInputStream`; body đang được xử lý đến bước nào?
6. Nếu có retry, kiểm tra deadline tổng, số lần thử và nguy cơ tạo side effect lặp.
7. Viết test có server cố ý trì hoãn phản hồi như `RequestTimeoutDemo` để tái hiện lỗi mà không phụ thuộc Internet.

## 11. Checklist trước khi đưa vào production

- [ ] `HttpRequest` đã được tạo bằng `HttpRequest.newBuilder(uri).timeout(Duration d).build()`, với `d` dương và có lý do nghiệp vụ.
- [ ] `HttpClient.connectTimeout` được cấu hình riêng (nếu cần) và không bị nhầm với per-request timeout.
- [ ] Code dùng `send()` có catch `HttpTimeoutException`/`HttpConnectTimeoutException`/`IOException`/`InterruptedException` đúng thứ tự và vai trò.
- [ ] Code dùng `sendAsync()` có kiểm soát future thất bại, `CompletionException` và các lỗi khác.
- [ ] HTTP 408/504 được xử lý bằng `statusCode()`, không đánh đồng với exception do client.
- [ ] Với `BodyHandlers.ofInputStream()` hoặc handler streaming, có giới hạn và phương án đóng/hủy body riêng.
- [ ] Deadline bao gồm những bước **ngoài HTTP** như parsing, mapping dữ liệu, retry hoặc giao dịch liên quan.
- [ ] Retry không gây side effect trùng đối với thao tác ghi; đã có idempotency strategy nếu cần.
- [ ] Có logging/metric theo loại lỗi và timeout, không rò rỉ dữ liệu nhạy cảm.
- [ ] Kiểm thử có cả request nhanh, request chậm, timeout đồng bộ, bất đồng bộ, duration = 0 và trường hợp không cấu hình timeout.

**Ghi nhớ:** `HttpRequest.Builder.timeout(Duration)` giới hạn thời gian chờ response cho **một request**, `HttpClient.Builder.connectTimeout(Duration)` giới hạn **việc thiết lập kết nối mới**, còn deadline tổng của nghiệp vụ và việc đọc body streaming cần được thiết kế phù hợp. Hết hạn phía client **không có nghĩa server chưa xử lý request**.

## Tài liệu chính thức còn áp dụng

- [Oracle Java SE 11 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): `timeout(Duration)` và `IllegalArgumentException` khi duration không dương.
- [Oracle Java SE 11 — `HttpRequest`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.html): `timeout()` trả `Optional<Duration>`, request bất biến.
- [Oracle Java SE 11 — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): ngoại lệ request quá hạn.
- [Oracle Java SE 11 — `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): timeout thiết lập kết nối, là kiểu con của `HttpTimeoutException`.
- [Oracle Java SE 26 — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): phạm vi request timeout và ghi chú về response/body subscriber của implementation.
- [Oracle Java SE 26 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `connectTimeout(Duration)` chỉ liên quan kết nối mới.
- [Oracle Java SE 26 — `HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): `send`/`sendAsync`, body handler và quản lý tài nguyên streaming.
- [Oracle Java SE 26 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): stream response có thể sẵn sớm sau headers; cần đọc đến EOF hoặc đóng.

Các ví dụ dựa trên API chuẩn từ Java 11 vẫn hiện hành, không dùng API incubator cũ. Những điểm về implementation và body streaming được phân biệt rõ với hợp đồng `HttpRequest.timeout`, tránh khẳng định sai rằng một deadline bao trùm mọi thao tác ứng dụng.