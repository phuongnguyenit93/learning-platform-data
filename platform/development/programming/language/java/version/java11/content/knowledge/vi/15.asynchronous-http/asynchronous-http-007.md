# HttpTimeoutException và HttpConnectTimeoutException trong HTTP bất đồng bộ (Java 11+)

## Mục tiêu

Khi ứng dụng gọi API bằng `HttpClient.sendAsync(...)`, một yêu cầu có thể mất thời gian vì **chưa thiết lập được kết nối** hoặc vì **đã gửi yêu cầu nhưng chưa nhận được phản hồi đúng hạn**. Java 11 cung cấp hai ngoại lệ thuộc `java.net.http` để phân biệt các tình huống timeout này:

- `HttpConnectTimeoutException`: quá thời gian được cấu hình cho **việc thiết lập kết nối mới**.
- `HttpTimeoutException`: quá thời gian chờ **response của một HTTP request** theo cấu hình request; đây cũng là **lớp cha** của ngoại lệ connect-timeout.

Hai API tiếp tục được hỗ trợ trong Java hiện đại. Chúng đặc biệt quan trọng với HTTP **bất đồng bộ**, bởi lỗi thường đi qua `CompletableFuture` thay vì xuất hiện trong câu lệnh `sendAsync(...)`.

Sau bài này, bạn sẽ:

1. Đặt timeout đúng **cấp client** và **cấp request** bằng `Duration`.
2. Phân biệt hai loại ngoại lệ, hiểu quan hệ kế thừa và thứ tự kiểm tra đúng.
3. Bắt lỗi bất đồng bộ với `handle(...)`/`whenComplete(...)`, cũng như `join()`/`get()`.
4. Viết ví dụ Java 11 chạy được, tạo response-timeout thật bằng HTTP server nội bộ.
5. Không nhầm **timeout của HTTP Client** với `java.util.concurrent.TimeoutException` khi chờ một future.
6. Thiết kế retry, cancellation, deadline và logging an toàn cho các request sản xuất.

**Phiên bản:** mã trong bài biên dịch bằng `javac --release 11`; không phụ thuộc thư viện HTTP bên ngoài, không dùng API thử nghiệm hoặc cách làm đã lỗi thời.

## 1. Sơ đồ vòng đời của một yêu cầu HTTP

Một lượt gọi HTTP thường trải qua nhiều giai đoạn:

```text
Ứng dụng tạo HttpRequest
       |
       v
client.sendAsync(request, bodyHandler)
       |
       +-- Cần tạo kết nối mới?
       |       |
       |       +-- Có: thiết lập connection (TCP, TLS/proxy tùy đường đi)
       |       |             |
       |       |             +-- vượt connectTimeout
       |       |                      -> HttpConnectTimeoutException
       |       |
       |       +-- Không: có thể tái sử dụng connection
       |                     (connectTimeout không áp dụng lượt này)
       v
Gửi HTTP request / chờ response
       |
       +-- response chưa nhận kịp hạn request.timeout
       |             -> HttpTimeoutException
       |
       +-- response có mặt đúng hạn
                     -> BodyHandler xử lý body
                     -> CompletableFuture hoàn thành theo kiểu body
```

Sơ đồ là **mô hình khái niệm**, không khẳng định mọi bước của DNS, proxy và TLS được tính thời gian giống nhau trên tất cả triển khai/JDK. Timeout có thể có sự giao thoa, và ngoại lệ thực nhận phụ thuộc nơi nào lỗi trước. Cần dựa vào loại ngoại lệ thực tế, không suy đoán chỉ từ số giây đã trôi qua.

Đặc biệt, một API với response body **streaming** có thể hoàn thành việc trả `HttpResponse<InputStream>` khi headers/stream đã sẵn sàng **trước khi người gọi đọc hết body**. Do đó không nên mặc định `request.timeout(...)` thay thế mọi loại **read-idle timeout, deadline cho business workflow hoặc giới hạn kích thước body**.

## 2. Hai loại timeout được cấu hình ở hai nơi

| Thuộc tính | Connection timeout | Request/response timeout |
| --- | --- | --- |
| Cấu hình | `HttpClient.newBuilder().connectTimeout(duration)` | `HttpRequest.newBuilder(uri).timeout(duration)` |
| Phạm vi | **Client**; chỉ khi cần thiết lập một connection mới | **Request** riêng; thời hạn chờ response theo hợp đồng HTTP Client |
| Ngoại lệ đặc trưng | `HttpConnectTimeoutException` | `HttpTimeoutException` |
| Nếu client tái sử dụng connection | Không có thao tác connect mới để giới hạn | Vẫn có thể timeout khi response chậm |
| Khi không cấu hình | Không đặt một timeout kết nối tường minh qua builder | Java 11 coi như không đặt giới hạn chờ response của request |
| Có tự giới hạn tổng bytes/giây? | Không | Không |

### 2.1. `HttpClient.Builder.connectTimeout`

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
```

Đây là đoạn **minh họa**; cần import `java.net.http.HttpClient` và `java.time.Duration`.

Theo Javadoc, nếu **cần tạo một connection mới**, nhưng không hoàn thành thiết lập trong khoảng `Duration` đã đặt, `send(...)` ném `HttpConnectTimeoutException` hoặc `sendAsync(...)` hoàn thành **exceptionally** với loại ngoại lệ ấy.

**Connect timeout không phải “timeout của mọi request”.** Nếu cùng client có kết nối đủ điều kiện để tái sử dụng, không phải tạo connection mới, thời hạn này **không có hiệu lực** trong lần gọi đó. Vì vậy với hệ thống keep-alive/HTTP/2, vẫn cần timeout ở request.

Có thể phải tạo kết nối mới khi gọi origin khác, kết nối cũ đóng, pool quyết định mở thêm connection hoặc proxy/tầng mạng thay đổi. Không có bảo đảm “mỗi request = một connection” và cũng không thể buộc mọi lần gọi phát sinh connect timeout bằng cách giữ nguyên một client.

### 2.2. `HttpRequest.Builder.timeout`

```java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
```

Đây là đoạn **minh họa** với `URI uri` đã xác định và import `HttpRequest`, `Duration`. Nếu response chưa nhận trong hạn đã cấu hình thì `send(...)` có thể ném `HttpTimeoutException`, còn `sendAsync(...)` hoàn thành exceptionally với `HttpTimeoutException`.

Giá trị timeout được gắn với **request đã build**, không phải toàn bộ client. Một `HttpClient` dùng chung có thể gửi request nhanh với timeout ngắn và request báo cáo với timeout dài.

Cả hai builder ở trên yêu cầu `Duration` **dương**. Truyền `Duration.ZERO` hoặc thời gian âm sẽ gặp `IllegalArgumentException`. Không coi `Duration.ZERO` là “chờ vô hạn”; nếu thật sự không đặt timeout, **bỏ lời gọi** thay vì nhập 0.

### 2.3. Cấu hình đồng thời cả hai

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(6))
        .GET()
        .build();
```

Đoạn này minh họa cấu hình; phụ thuộc `URI uri` và import phù hợp. Cách đặt thời hạn trên phù hợp khi muốn giới hạn việc mở connection và cả việc chờ response. **Số 2 và 6 chỉ là ví dụ**, không phải SLA mặc định cho mọi hệ thống.

Nếu hai hạn có thể kết thúc gần nhau, **không bảo đảm bạn luôn nhận được ngoại lệ “đúng cái timeout ngắn hơn” theo một thứ tự cứng**. Giai đoạn request và giai đoạn kết nối có thể chồng lấn; đường đi HTTP, proxy và thứ tự callback cũng tác động. Hãy phân loại theo ngoại lệ thực tế khi nó được báo.

## 3. Cây kế thừa: bắt connect-timeout trước

Chữ ký API Java 11:

```text
java.lang.Throwable
  -> java.lang.Exception
     -> java.io.IOException
        -> java.net.http.HttpTimeoutException
           -> java.net.http.HttpConnectTimeoutException
```

Nói cách khác:

- `HttpTimeoutException extends IOException`.
- `HttpConnectTimeoutException extends HttpTimeoutException`.
- Bất cứ `HttpConnectTimeoutException` nào cũng là một `HttpTimeoutException` khi kiểm tra `instanceof`.
- Một `HttpTimeoutException` thông thường **không** nhất thiết là connect-timeout.

**Với HTTP đồng bộ `send()`**, thứ tự `catch` đúng:

```java
try {
    HttpResponse<Void> response = client.send(
            request, HttpResponse.BodyHandlers.discarding());
    System.out.println(response.statusCode());
} catch (HttpConnectTimeoutException ex) {
    System.err.println("Connect timeout");
} catch (HttpTimeoutException ex) {
    System.err.println("Request timeout");
} catch (IOException ex) {
    System.err.println("HTTP I/O error");
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("Interrupted");
}
```

Đây là **đoạn minh họa trong một method** đã có `client` và `request`. Cần các import `java.io.IOException`, `java.net.http.*`. Nếu đặt `catch(HttpTimeoutException)` trước `catch(HttpConnectTimeoutException)`, nhánh sau sẽ **không thể tới được** và trình biên dịch báo lỗi. Với đồng bộ, nhớ phục hồi interrupt flag khi bắt `InterruptedException` nếu phương thức không ném tiếp nó.

Ở nhánh `IOException` khác, có thể là lỗi network, DNS, TLS, kết nối bị từ chối, đóng stream, v.v. **Không phải mọi lỗi kết nối đều là `HttpConnectTimeoutException`.**

## 4. Trong `sendAsync`: ngoại lệ đi qua `CompletableFuture`

Lời gọi:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString());
```

Đây là đoạn minh họa, cần `client`/`request` và các import liên quan. `sendAsync(...)` trả về một `CompletableFuture` để ứng dụng có thể tiếp tục làm việc khác thay vì chặn luồng gọi.

Khi lỗi timeout xảy ra **bất đồng bộ**:

- Future hoàn thành **exceptionally** với nguyên nhân thuộc họ `HttpTimeoutException`.
- `future.join()` khi lấy kết quả có thể ném `CompletionException` (unchecked), với ngoại lệ HTTP ở `getCause()` hoặc sâu hơn.
- `future.get()` dùng API `Future` và có thể ném `ExecutionException` (checked), cũng cần mở nguyên nhân.
- Callback của `handle((value, failure) -> ...)`, `whenComplete(...)` hoặc `exceptionally(...)` có thể nhận Throwable đã được bọc; xử lý cả wrapper thay vì chỉ `instanceof HttpTimeoutException` trên wrapper ngoài cùng.
- Các lỗi hợp lệ ngay khi gọi API (chẳng hạn request argument không hợp lệ) vẫn có thể xuất hiện **đồng bộ**, nên không giả định mọi sai sót đều được đẩy qua future.

### Gỡ lớp bọc của `CompletionException`

Một helper đơn giản:

```java
private static Throwable rootCause(Throwable error) {
    while (error instanceof CompletionException
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
```

Đây là phương thức minh họa đặt trong một class Java, cần import `java.util.concurrent.CompletionException`. Nếu cũng muốn xử lý `future.get()`, mở thêm `ExecutionException` hoặc lấy `e.getCause()` trong catch riêng. **Không tự động bỏ qua mọi `cause` đến mức mất ngữ cảnh lỗi**; chỉ mở các wrapper của future đã xác định rõ.

Vì `HttpConnectTimeoutException` là subclass của `HttpTimeoutException`, cả callback lẫn nhánh catch nên kiểm tra connect trước:

```java
Throwable cause = rootCause(failure);
if (cause instanceof HttpConnectTimeoutException) {
    // Kết nối mới không hoàn tất trước connectTimeout.
} else if (cause instanceof HttpTimeoutException) {
    // Hết hạn request/response timeout.
} else {
    // Lỗi khác, không tùy tiện phân loại là timeout.
}
```

Đây là đoạn minh họa dùng `failure` đã tồn tại, cần import các class exception. Không in/ghi những thông tin bảo mật trong URI, headers hoặc body khi log lỗi.

## 5. Chương trình Java 11 chạy được: response chậm và phân loại lỗi

Để có kết quả **lặp lại tương đối ổn định mà không phụ thuộc mạng Internet**, chương trình tạo HTTP server trên `127.0.0.1` với cổng ngẫu nhiên:

- `/fast` trả ngay body `OK` và HTTP 200.
- `/slow` cố ý ngủ khoảng 1.000 ms trước khi trả body.
- Client dùng `connectTimeout(2 giây)` và gửi một request `/slow` với `timeout(150 ms)`. Vì kết nối loopback thường tạo nhanh, **request timeout** sẽ xảy ra.
- Nhánh callback kiểm tra `HttpConnectTimeoutException` **trước** `HttpTimeoutException`. Nó không cố tạo một connect-timeout giả bằng cách truy cập một host không ổn định.
- Dòng cuối kiểm tra quan hệ kiểu của hai class qua `isAssignableFrom(...)`, không ngụy tạo ngoại lệ trong quá trình kết nối.

**Tệp `AsyncTimeoutDemo.java` — Java 11+**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncTimeoutDemo {
    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    private static Throwable rootCause(Throwable error) {
        while (error instanceof CompletionException
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/fast",
                exchange -> respond(exchange, "OK"));
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_000);
                respond(exchange, "TOO LATE");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } catch (IOException ex) {
                // Client có thể đã hết hạn và đóng exchange.
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest fast = HttpRequest.newBuilder(
                    URI.create(base + "/fast"))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();
            CompletableFuture<HttpResponse<String>> okFuture =
                    client.sendAsync(fast,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));
            HttpResponse<String> ok = okFuture.join();
            System.out.println(
                    "fast=" + ok.statusCode() + " " + ok.body());

            HttpRequest slow = HttpRequest.newBuilder(
                    URI.create(base + "/slow"))
                    .timeout(Duration.ofMillis(150))
                    .GET()
                    .build();
            String outcome = client.sendAsync(slow,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                    .handle((response, failure) -> {
                        if (failure == null) {
                            return "unexpected="
                                    + response.statusCode();
                        }
                        Throwable cause = rootCause(failure);
                        if (cause instanceof
                                HttpConnectTimeoutException) {
                            return "connect-timeout";
                        }
                        if (cause instanceof HttpTimeoutException) {
                            return "request-timeout";
                        }
                        throw new CompletionException(cause);
                    }).join();
            System.out.println("slow=" + outcome);
            System.out.println("connectSubtype="
                    + HttpTimeoutException.class.isAssignableFrom(
                            HttpConnectTimeoutException.class));
        } finally {
            server.stop(0);
        }
    }
}
```

### Biên dịch và chạy

Lưu đúng tên `AsyncTimeoutDemo.java`; từ thư mục chứa file:

```bash
javac -encoding UTF-8 AsyncTimeoutDemo.java
java AsyncTimeoutDemo
```

Nếu đang dùng JDK mới hơn và muốn kiểm tra API tương thích Java 11:

```bash
javac --release 11 -encoding UTF-8 AsyncTimeoutDemo.java
java AsyncTimeoutDemo
```

**Stdout đã kiểm tra thực tế:**

```text
fast=200 OK
slow=request-timeout
connectSubtype=true
```

Chương trình đã được **biên dịch thành công với `--release 11`** và chạy trên JDK cài đặt, trả đúng ba dòng trên. Kết quả phụ thuộc hệ thống có thể lập lịch server/client đúng thời điểm; môi trường quá tải bất thường có thể tạo khác biệt, vì vậy trong test tự động quan trọng hãy thiết kế đồng bộ trạng thái và khoảng chênh thời gian đủ lớn.

### Giải thích chi tiết

1. `HttpServer` thuộc module `jdk.httpserver` của JDK, là server nhẹ phục vụ ví dụ **nội bộ**, không cần Internet hay credential. Trong môi trường module tùy chỉnh phải bảo đảm module này sẵn có.
2. `/fast` trả HTTP 200 và `OK`. `okFuture.join()` lấy `HttpResponse<String>` khi body được `BodyHandlers.ofString(UTF_8)` xử lý.
3. `/slow` chờ 1.000 ms, lâu hơn request timeout 150 ms. Với kết nối loopback tạo nhanh, client thường báo `HttpTimeoutException`.
4. Bất đồng bộ khác đồng bộ: `sendAsync` trả Future, còn lỗi đi vào `failure` của `handle`. Helper mở lớp bọc `CompletionException`, sau đó kiểm tra ngoại lệ con trước ngoại lệ cha.
5. `handle` chuyển kết quả lỗi thành **một chuỗi outcome** để chương trình có thể in. Trong sản phẩm, bạn có thể quyết định truyền tiếp lỗi, ghi metrics hoặc retry có kiểm soát; **không nên biến mọi lỗi thành “thành công” chỉ để pipeline hết đỏ**.
6. `connectSubtype=true` chỉ xác nhận **quan hệ kế thừa**. Demo **không** phát sinh connect-timeout thật, vì tạo timeout kết nối lặp lại ổn định không dễ chỉ bằng một địa chỉ IP mạng công cộng.
7. Khi client timeout và hủy exchange, server vẫn đang ngủ và có thể gặp `IOException` lúc cố ghi phản hồi. Demo bắt lỗi mạng phía server cho test gọn; trong hệ thống thật phải log/đo lỗi theo chính sách vận hành.
8. `server.stop(0)` dừng server trong `finally`. Mẫu nhỏ không cần `client.close()` vì API vòng đời kiểu đó chỉ được bổ sung từ Java 21; trong Java 11 bạn thường quản lý client dùng chung theo vòng đời ứng dụng.

**Đừng hiểu stdout `slow=request-timeout` là bằng chứng server đã dừng xử lý.** Timeout phía client không có nghĩa server chưa xử lý hoặc không tạo side effect; điều này rất quan trọng với POST/PUT.

## 6. Vì sao không nên cố tạo `HttpConnectTimeoutException` bằng một IP bất kỳ?

Nhiều ví dụ trên mạng dùng một IP “có vẻ không trả lời” và đặt `connectTimeout(100 ms)` để minh họa. Phương pháp này **không đáng tin để làm test tự động**:

- Hệ điều hành hoặc router có thể báo “Network unreachable” ngay, thay vì treo đến connect timeout.
- Firewall có thể gửi TCP reset, làm `ConnectException: Connection refused` hoặc lỗi I/O khác.
- Proxy, VPN, DNS và chính sách mạng của máy chạy test có thể đổi đường đi.
- Một địa chỉ hôm nay không phản hồi có thể ngày mai phản hồi, khiến test không còn đúng.
- Nếu một connection được tái sử dụng, không có pha mở connection mới, nên `connectTimeout` không áp dụng lần đó.

Nếu cần kiểm tra tình huống connect-timeout **thực sự**, hãy thiết lập môi trường network test có thể kiểm soát việc drop/drop-delay connection (container/network namespace/test proxy/firewall của bạn) và đặt client timeout phù hợp. Trong pipeline CI thông thường, ưu tiên **kiểm tra logic phân loại bằng subclass và unit test có mô phỏng** thay vì phụ thuộc một host Internet bất định.

**Trường hợp kết nối bị từ chối không đồng nghĩa kết nối timeout.** Ví dụ server không lắng nghe tại cổng của loopback thường phát sinh `ConnectException` nhanh chóng, không phải `HttpConnectTimeoutException`.

## 7. Xử lý ngoại lệ bất đồng bộ theo từng kiểu callback

### 7.1. `handle(...)`: biến kết quả hoặc lỗi thành giá trị khác

```java
CompletableFuture<String> label = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString())
        .handle((response, error) -> {
            if (error == null) {
                return "HTTP " + response.statusCode();
            }
            Throwable cause = rootCause(error);
            if (cause instanceof HttpConnectTimeoutException) {
                return "CONNECT_TIMEOUT";
            }
            if (cause instanceof HttpTimeoutException) {
                return "REQUEST_TIMEOUT";
            }
            return "OTHER_FAILURE";
        });
```

Đây là đoạn **minh họa** bên trong class có helper `rootCause(Throwable)` của ví dụ hoàn chỉnh và `client`/`request` đã tồn tại. `handle` chạy trên cả nhánh thành công và thất bại, trả một future mới kiểu `String`. Nó có thể thuận tiện cho UI/status, nhưng nếu bỏ mọi Throwable vào `OTHER_FAILURE` rồi coi như thành công thì sẽ che lỗi thực tế.

### 7.2. `whenComplete(...)`: quan sát kết quả/lỗi, không tự chuyển trạng thái

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> logged =
        future.whenComplete((response, error) -> {
            if (error != null) {
                Throwable cause = rootCause(error);
                System.err.println(
                        "HTTP failed: " + cause.getClass().getSimpleName());
            }
        });
```

Đây là đoạn minh họa với `rootCause` và biến đã có. `whenComplete` phù hợp để **ghi metrics/log** mà không cần đổi kiểu body. Trừ khi chính callback ném lỗi mới, một future đã lỗi thường vẫn đi tiếp ở trạng thái lỗi; do đó muốn **phục hồi** bằng fallback phải dùng `handle` hoặc `exceptionally` theo chính sách.

Không log đầy đủ URI query, bearer token, cookie hay response body khi chúng có thể chứa dữ liệu nhạy cảm.

### 7.3. `exceptionally(...)`: fallback cùng kiểu

```java
CompletableFuture<HttpResponse<String>> recovered =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
        .exceptionally(error -> {
            Throwable cause = rootCause(error);
            // Có thể quyết định retry/fallback theo cause.
            // Ở đây ném tiếp lỗi, không tạo phản hồi giả.
            throw new CompletionException(cause);
        });
```

Đây là đoạn minh họa, **không tự thực hiện retry**. `exceptionally` nhận lỗi và có thể trả giá trị thay thế **cùng kiểu** hoặc ném tiếp; chỉ trả response giả khi hợp đồng nghiệp vụ thật sự cho phép. Với timeout của một lệnh ghi dữ liệu, “fallback = đã thành công” có thể làm sai trạng thái.

### 7.4. `join()` và `get()` ở ranh giới đồng bộ

```java
try {
    HttpResponse<String> response = future.join();
} catch (CompletionException ex) {
    Throwable cause = rootCause(ex);
    // Phân loại HttpConnectTimeoutException trước HttpTimeoutException.
}
```

Đây là đoạn minh họa với `future` đã có; `join()` vẫn **chặn** thread gọi nếu future chưa hoàn tất. Nếu xử lý trong UI/event loop, thường nên kết hợp callback async thay vì gọi `join()` ngay.

`future.get()` ném `ExecutionException` khi future lỗi, và có thể ném `InterruptedException`. Nếu dùng `get(timeout, TimeUnit)`, còn có một loại timeout khác được giải thích ở phần sau.

## 8. Ba khái niệm timeout khác nhau: đừng bắt nhầm

Có ít nhất **ba** kiểu timeout liên quan CompletableFuture và HTTP:

| Tình huống | API đặt hạn | Ngoại lệ thường thấy |
| --- | --- | --- |
| Thiết lập kết nối mới quá lâu | `HttpClient.Builder.connectTimeout(Duration)` | `HttpConnectTimeoutException` (thuộc họ `HttpTimeoutException`) |
| HTTP response chưa nhận đúng hạn | `HttpRequest.Builder.timeout(Duration)` | `HttpTimeoutException` |
| Thread/caller đợi `Future` quá lâu | `future.get(timeout, TimeUnit)` hoặc `future.orTimeout(timeout, TimeUnit)` | `java.util.concurrent.TimeoutException` (khác họ HTTP exception) |

### 8.1. `Future.get(timeout, unit)`

```java
try {
    HttpResponse<String> result =
            future.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    // Chính caller đã hết kiên nhẫn trong khi chờ future.
    future.cancel(true); // Yêu cầu hủy, không bảo đảm dừng tức thì.
}
```

Đây là đoạn minh họa có `future` đã tạo, import `TimeUnit`/`TimeoutException` và **chưa hiển thị** các nhánh bắt `InterruptedException`, `ExecutionException` (phải xử lý trong mã đầy đủ).

Nếu `get(500, ...)` hết hạn, **future gốc không tự động bị hủy**. Nó có thể vẫn chạy và gửi dữ liệu sau khi caller đã bỏ chờ. Do đó code minh họa yêu cầu `cancel(true)` theo chính sách hủy, nhưng cancellation của HTTP exchange chỉ là **best effort**.

### 8.2. `CompletableFuture.orTimeout(...)`

```java
CompletableFuture<HttpResponse<String>> limited =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString())
        .orTimeout(500, TimeUnit.MILLISECONDS);
```

Đây là đoạn minh họa. `orTimeout(...)` (đã có trước Java 11) sẽ làm future hoàn thành exceptionally bằng **`java.util.concurrent.TimeoutException`** nếu chưa xong vào lúc hết hạn. Nó **không** biến lỗi đó thành `HttpTimeoutException`.

Hơn nữa, hoàn thành future vì timeout ở tầng ứng dụng không đồng nghĩa bảo đảm tác vụ HTTP và I/O nền đã bị hủy/đóng. Nếu cần chủ động hủy HTTP exchange, thiết kế cancellation và theo dõi tài nguyên riêng. Khi `orTimeout` áp lên chính future nhận từ `sendAsync`, nó tác động **future đó**, không phải chỉ tạo một watcher độc lập; tránh dùng cùng future ở nhiều nơi khi các bên có chính sách timeout không thống nhất.

### 8.3. Timeout request không phải “idle timeout” tự động

Một HTTP response streaming có thể được trao cho caller **trước khi tất cả byte được đọc**. Nếu yêu cầu nghiệp vụ là “mỗi khối dữ liệu phải đến trong vòng 3 giây” hoặc “tải 10 GB phải hoàn tất trong 30 phút”, hãy thiết kế **idle timeout, deadline toàn công việc, giới hạn byte, backpressure và hủy** ở lớp streaming thích hợp. Không suy diễn rằng `HttpRequest.timeout(...)` tự thực hiện mọi SLA này trong mọi loại `BodyHandler`.

## 9. Retry sau timeout: chỉ thực hiện khi thực sự an toàn

Một timeout **không xác nhận server chưa xử lý request**. Request có thể đã được gửi, thậm chí server đã cập nhật dữ liệu, nhưng response đến muộn hoặc mất. Vì vậy:

- **GET** thông thường có tính safe/idempotent theo ngữ nghĩa HTTP, nhưng vẫn phải kiểm tra quota, mục tiêu dữ liệu, retry limit và backoff.
- **PUT** thường idempotent theo HTTP semantics khi cùng tài nguyên/nội dung, nhưng workflow ứng dụng có thể thêm side effect; phải hiểu hợp đồng API.
- **POST** không được mặc định gửi lại vô điều kiện. Với thanh toán, tạo đơn, ghi log nghiệp vụ, upload, cần **idempotency key**, request ID hoặc cơ chế xác minh trạng thái đã tạo.
- Nếu body dùng `BodyPublisher` từ một nguồn stream chỉ đọc được một lần, retry có thể không thể gửi lại chính nội dung đó; cần nguồn có thể replay khi chính sách cho phép.
- Chỉ retry khi lỗi được phân loại phù hợp, sau **exponential backoff + jitter**, với số lần và **tổng deadline** hữu hạn.
- Không tạo client mới cho mọi retry: một `HttpClient` dùng chung có thể quản lý tài nguyên kết nối tốt hơn, miễn nhóm cấu hình/chính sách bảo mật cho phép.

**Không retry mọi `IOException`:** lỗi chứng thực, dữ liệu sai, chứng chỉ TLS hoặc đường dẫn không hợp lệ thường cần xử lý khác với sự cố tạm thời của network.

Một quy trình retry an toàn:

```text
1. Đánh giá request có an toàn để phát lại không?
2. Kiểm tra idempotency key / server-side operation ID.
3. Tính tổng thời gian còn lại trong deadline nghiệp vụ.
4. Xác định lỗi cụ thể và khả năng phục hồi.
5. Chờ backoff có jitter (nếu được phép).
6. Gửi lại với giới hạn attempt và timeout được tính lại phù hợp.
7. Kiểm tra status cuối, body và trạng thái server.
```

Không nhất thiết retry được `HttpConnectTimeoutException` thì retry `HttpTimeoutException` cũng an toàn: ở lỗi response timeout, request **có thể đã đến server**, nên rủi ro lặp tác dụng phụ lớn hơn.

## 10. Cancellation và tài nguyên sau timeout

Khi một future không còn cần kết quả, có thể gọi:

```java
future.cancel(true);
```

Đây là đoạn minh họa trên future trả từ `sendAsync()`. Theo tài liệu Java HTTP Client, hủy exchange là **nỗ lực best effort**, không phải lệnh thu hồi giao dịch phía server:

- Request có thể đã được gửi hoặc server vẫn tiếp tục xử lý.
- Với HTTP/1.1, hủy có thể khiến connection bị đóng đột ngột.
- Với HTTP/2, hủy có thể reset stream hoặc trong một số trường hợp ảnh hưởng connection.
- Các stream response từ `BodyHandlers.ofInputStream()` hoặc publisher liên quan vẫn cần quản lý vòng đời/đóng/hủy phù hợp; timeout của future không tự chứng minh mọi tài nguyên đã được giải phóng.

Tránh mở hàng chục nghìn request async cùng lúc mà không có giới hạn concurrency. Timeout ngắn không bù cho việc không có queue/backpressure: phần lớn request có thể đã chiếm socket, thread và memory trước khi timeout.

**Java 11 vs Java 21+:** `HttpClient` tại Java 11 không có `close()/shutdown()` công khai kiểu API bổ sung từ Java 21. Không chép `try (HttpClient client = ...)` dùng `AutoCloseable` từ mã Java 21 vào một dự án cần biên dịch `--release 11`. Đây là chú thích tương thích, không có nghĩa API Java 11 bị lỗi thời.

## 11. Ghi log và metrics theo đúng nguyên nhân

Những thông tin hữu ích khi đánh giá timeout trong hệ thống:

| Nhóm | Metric/log nên thu thập | Không được suy đoán |
| --- | --- | --- |
| Connect timeout | Tên exception, đích (đã ẩn dữ liệu nhạy cảm), khoảng thời gian cấu hình, lần mở kết nối mới | Mọi lần gọi đều đã trải qua một connect mới |
| Request timeout | Thời hạn request, method, endpoint đã chuẩn hóa, số lần thử, latency | Server chắc chắn chưa nhận/ghi request |
| Other I/O error | `ConnectException`, DNS error, `SSLException`, EOF/reset... | Tất cả đều là timeout và có thể retry |
| Async wrapper | Class nguyên nhân bên dưới `CompletionException`/`ExecutionException` | Tên wrapper ngoài cùng mô tả đủ bản chất lỗi |
| Tài nguyên | Concurrency, queue depth, open connections, body hoàn tất/hủy | Timeout tự giới hạn số socket đang dùng |
| Kết quả nghiệp vụ | Operation ID/idempotency key, status cuối khi có, trạng thái xác minh ở server | HTTP 200 hoặc thiếu response luôn nói hết trạng thái của giao dịch |

Không gửi bearer token, cookie, mật khẩu hoặc payload cá nhân vào log. Một vài URI có query chứa secret; cần mask trước khi ghi. Metrics nên phân biệt `connect_timeout`, `response_timeout`, `future_wait_timeout` và `other_io_error` để tránh chẩn đoán sai.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ đặt `connectTimeout` rồi nghĩ mọi request đã có timeout | Server có thể phản hồi rất chậm trên connection đã có | Đặt thêm `HttpRequest.timeout` thích hợp |
| Coi connect timeout có hiệu lực khi dùng lại connection | Không có pha connect mới để giới hạn | Hiểu connection pooling; đo giai đoạn thực tế |
| Đặt `Duration.ZERO` để “không chờ” | `IllegalArgumentException` từ builder | Dùng Duration dương; bỏ cấu hình nếu chủ đích không đặt hạn |
| Bắt `HttpTimeoutException` trước `HttpConnectTimeoutException` | Nhánh connect sẽ không thể tới được trong `catch` hoặc bị phân loại sai với `instanceof` | Kiểm tra subclass trước |
| Chỉ bắt `HttpTimeoutException` ngay quanh câu lệnh `sendAsync(...)` | Lỗi bất đồng bộ đi qua future, không phải câu lệnh khởi tạo | Dùng `handle/whenComplete/exceptionally` hoặc lấy cause ở `join/get` |
| Kiểm tra `failure instanceof HttpTimeoutException` khi failure là `CompletionException` | Không nhận diện loại lỗi bên dưới | Mở wrapper an toàn và phân loại cause |
| Coi `ConnectException: Connection refused` là timeout | Chẩn đoán sai mạng | Phân biệt kết nối bị từ chối với hết thời gian kết nối |
| Cố tái tạo connect timeout bằng địa chỉ Internet ngẫu nhiên trong CI | Test flakey, lúc lỗi DNS/route, lúc được kết nối | Unit test phân loại, integration test qua network harness |
| Nhầm `future.get(timeout)` với `HttpRequest.timeout` | Bắt nhầm `TimeoutException` và không hủy HTTP exchange | Phân biệt timeout chờ future với HTTP timeout |
| Nghĩ `orTimeout` chắc chắn hủy socket/server operation | Tài nguyên và side effect có thể tiếp diễn | Quản lý cancellation/deadline/response body độc lập |
| Retry POST khi `HttpTimeoutException` mà không có idempotency | Có thể tạo giao dịch trùng | Idempotency key và xác minh trạng thái |
| Coi timeout là nguyên nhân mọi lỗi I/O | Bỏ sót TLS, DNS, auth, protocol và server errors | Phân loại exception và status chính xác |
| Tạo client mới cho mỗi request để “reset timeout” | Mất cơ hội reuse connection, tăng tài nguyên | Giữ client dùng chung theo cấu hình phù hợp |
| Không đóng streaming response body sau khi bỏ chờ | Có thể giữ connection/response exchange | Tiêu thụ/đóng/cancel đúng hợp đồng handler |
| Dùng giá trị timeout quá ngắn rồi kết luận API chậm | Lỗi giả do cold start, TLS, network jitter | Đặt timeout theo SLO thực tế và đo percentile |
| Nuốt `InterruptedException` trong `send()` | Luồng bị gián đoạn nhưng trạng thái bị che mất | Propagate hoặc phục hồi interrupt flag |

## 13. Bài tập và câu hỏi kiểm tra

**Bài 1 — Phân biệt cấu hình.** Có `connectTimeout = 2s` và `request.timeout = 8s`. Nếu client dùng lại connection đã có nhưng server phản hồi sau 20s, timeout nào có ý nghĩa trực tiếp? **Đáp án:** request timeout 8s; connect timeout không được áp dụng cho lần request không cần tạo kết nối mới.

**Bài 2 — Quan hệ kế thừa.** Với đoạn kiểm tra:

```java
Throwable cause = new HttpConnectTimeoutException("connect too slow");

System.out.println(cause instanceof HttpTimeoutException);
System.out.println(cause instanceof IOException);
```

Đây là đoạn minh họa cần import phù hợp, không mô phỏng một lỗi mạng thật. **Stdout:** `true` ở cả hai dòng. Lý do: `HttpConnectTimeoutException extends HttpTimeoutException extends IOException`.

**Bài 3 — Future wrapper.** `sendAsync(...)` hết hạn chờ response. Vì sao `future.join()` có thể ném `CompletionException` thay vì `HttpTimeoutException` trực tiếp? **Đáp án:** `join()` trình bày lỗi của `CompletableFuture` qua wrapper unchecked; cần kiểm tra cause bên trong.

**Bài 4 — Kiểu timeout.** `future.get(300, TimeUnit.MILLISECONDS)` hết hạn chờ nhưng request không có `HttpRequest.timeout`. Loại exception nào từ lệnh `get`? **Đáp án:** `java.util.concurrent.TimeoutException`; việc `get` hết hạn **không** tự hủy request.

**Bài 5 — Thay thời hạn.** Trong `AsyncTimeoutDemo`, đổi timeout request `/slow` từ 150ms thành 3s. Trên môi trường bình thường, kết quả dự kiến chuyển thành `slow=unexpected=200` vì server trả sau 1s, nhưng lưu ý stdout đo đạc có thể thay đổi nếu hệ thống quá tải. Giải thích tại sao không phải connect-timeout.

**Bài 6 — Thứ tự catch.** Thử đổi vị trí hai nhánh `catch(HttpConnectTimeoutException)` và `catch(HttpTimeoutException)` trong ví dụ đồng bộ. Trình biên dịch báo lỗi gì? **Đáp án:** nhánh catch subclass không thể tới được, vì superclass đã bắt mọi ngoại lệ kiểu con.

**Bài 7 — Xử lý nghiệp vụ.** Một request POST tạo hóa đơn bị `HttpTimeoutException`. Có được tự gửi lại ngay không? **Không** nếu chưa biết server đã tạo hóa đơn hay chưa. Đề xuất dùng idempotency key và API truy vấn trạng thái.

**Bài 8 — Tự kiểm thử.** Bổ sung test `/fast`, `/slow` có delay được kiểm soát, timeout ở mức request và unit test cho helper `rootCause`. Không phụ thuộc địa chỉ mạng bên ngoài để ép `HttpConnectTimeoutException`; nếu cần integration test cho connect timeout, dùng môi trường mạng mô phỏng chủ động.

### Checklist trước khi đưa vào production

1. Đã cấu hình `connectTimeout` cho kết nối **mới**, `request.timeout` cho response, cả hai với `Duration` dương?
2. Khi phân loại, có ưu tiên `HttpConnectTimeoutException` trước `HttpTimeoutException`?
3. Với `sendAsync`, có mở `CompletionException`/`ExecutionException` và tách `TimeoutException` của Future?
4. Có giới hạn retry, backoff+jitter và **deadline tổng** của workflow?
5. Retry POST/PUT có hiểu idempotency, khả năng phát lại body và trạng thái server?
6. Có giới hạn concurrency, quản lý cancel và đóng streaming body?
7. Metrics phân biệt connect timeout, request timeout, wait timeout và lỗi I/O khác?
8. Có bảo vệ dữ liệu nhạy cảm khi log exception/URI?
9. Test không dựa vào một IP công cộng “chắc chắn sẽ timeout”?
10. Code dùng API đúng với **JDK tối thiểu** của dự án và vẫn còn áp dụng trong Java hiện đại?

## Tài liệu chính thức

- [Oracle Java SE 11 — HttpClient.Builder.connectTimeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration)): cấu hình thời hạn thiết lập **kết nối mới**, ngoại lệ connect-timeout và trường hợp tái sử dụng connection.
- [Oracle Java SE 11 — HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)): thời hạn nhận response của request, `HttpTimeoutException`, yêu cầu thời lượng dương.
- [Oracle Java SE 11 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpTimeoutException.html): `HttpTimeoutException extends IOException`.
- [Oracle Java SE 11 — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): `HttpConnectTimeoutException extends HttpTimeoutException`.
- [Oracle Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync`, CompletionStage, tài nguyên HTTP và cancellation.
- [Oracle Java SE 25 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): API kết nối tiếp tục hỗ trợ trên JDK hiện đại.
- [Oracle Java SE 25 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout trong Java hiện đại.
- [Oracle Java SE 11 — CompletableFuture](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `join`, `handle`, `whenComplete`, `orTimeout` và exceptional completion.
- [OpenJDK JEP 321 — HTTP Client (Standard)](https://openjdk.org/jeps/321): API HTTP Client chuẩn từ Java 11.

**Kết luận:** `HttpConnectTimeoutException` cho biết **pha kết nối mới** không hoàn tất trong hạn, còn `HttpTimeoutException` phản ánh hết hạn **chờ response của request**. Trong `sendAsync()`, cả hai thường nằm **bên trong lỗi của `CompletableFuture`**, nên phải mở wrapper và kiểm tra **subclass trước superclass**. Kết hợp timeout đúng cấp với idempotency, retry hữu hạn, cancellation và quản lý streaming body mới tạo một hệ thống HTTP bất đồng bộ đáng tin cậy.