# Thời gian chờ kết nối, thời gian chờ yêu cầu và xử lý lỗi trong Java 17

## 1. Vì sao ứng dụng mạng cần timeout?

Một lời gọi mạng có thể bị chậm hoặc không bao giờ nhận được dữ liệu vì máy chủ quá tải, DNS không phân giải được tên miền, đường truyền gặp sự cố, firewall chặn kết nối hoặc đối tác ngừng phản hồi. Nếu chương trình chờ vô hạn, thread có thể bị giữ lâu, tài nguyên bị chiếm dụng và các yêu cầu phía sau bị ảnh hưởng.

**Timeout** quy định khoảng thời gian tối đa mà một thao tác chờ ở một giai đoạn cụ thể. Trong Java, cần phân biệt:

- **Connect timeout:** giới hạn thời gian thiết lập kết nối mạng.
- **Read timeout:** giới hạn thời gian chờ dữ liệu tiếp theo khi đang đọc từ kết nối.
- **Request/response timeout:** giới hạn thời gian chờ phản hồi cho một yêu cầu ở API cấp cao như Java HttpClient.
- **Overall deadline:** ngân sách thời gian tổng thể mà ứng dụng tự đặt cho toàn bộ công việc, có thể gồm nhiều lần thử và nhiều giai đoạn.

Các khái niệm này không thay thế cho nhau. Một kết nối TCP có thể được thiết lập nhanh nhưng máy chủ xử lý yêu cầu rất lâu; ngược lại, kết nối có thể không thiết lập được ngay từ đầu.

Trong Java 17, có thể cấu hình timeout bằng các API như `Socket.connect`, `Socket.setSoTimeout`, `URLConnection` và `java.net.http.HttpClient`. Bài học chỉ sử dụng API còn áp dụng trong Java 17.

## 2. Phân biệt các giai đoạn của một lần gọi mạng

Một lần gọi HTTP đơn giản thường trải qua các giai đoạn:

~~~text
Ứng dụng
  |
  | 1. Phân giải tên máy chủ (DNS)
  v
Địa chỉ IP
  |
  | 2. Thiết lập kết nối TCP
  v
Kết nối TCP
  |
  | 3. TLS handshake (nếu dùng HTTPS)
  v
Kênh bảo mật
  |
  | 4. Gửi HTTP request
  v
Máy chủ xử lý
  |
  | 5. Nhận status, headers và body
  v
Ứng dụng xử lý response
~~~

Một timeout ở một giai đoạn không nhất thiết bao phủ mọi giai đoạn còn lại:

| Loại timeout | Câu hỏi được giới hạn | Ví dụ lỗi có thể gặp |
|---|---|---|
| DNS resolution | Tên host có được phân giải thành địa chỉ không? | `UnknownHostException` |
| Connect timeout | Có thiết lập được kết nối tới endpoint trong thời gian cho phép không? | `ConnectException` hoặc timeout riêng của API |
| Read timeout | Có nhận được dữ liệu tiếp theo trong khoảng chờ cho phép không? | `SocketTimeoutException` |
| Request timeout | Yêu cầu có nhận được phản hồi theo thời hạn đã đặt không? | `HttpTimeoutException` |
| Overall deadline | Toàn bộ workflow có hoàn tất trước deadline không? | Lỗi deadline do ứng dụng định nghĩa |

Không nên xem bảng này như một ánh xạ một-một tuyệt đối: loại exception cụ thể còn phụ thuộc API, hệ điều hành, TLS, DNS và thời điểm lỗi xảy ra.

## 3. Connect timeout và read timeout với Socket

`Socket` là API mức thấp để làm việc với kết nối TCP. Hai cấu hình thường bị nhầm là `connect timeout` và `SO_TIMEOUT`.

### 3.1. `Socket.connect(endpoint, timeout)`

Phương thức:

~~~java
socket.connect(new InetSocketAddress(host, port), timeoutMillis);
~~~

giới hạn thời gian chờ thiết lập kết nối:

- `timeoutMillis > 0`: thời gian tối đa tính bằng milliseconds.
- `timeoutMillis == 0`: chờ vô hạn.
- `timeoutMillis < 0`: không hợp lệ, ném `IllegalArgumentException`.

Ví dụ:

~~~java
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.io.IOException;

String host = "example.com";
int port = 443;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 3_000);
    System.out.println("Connected");
} catch (SocketTimeoutException ex) {
    System.err.println("Connection timed out: " + ex.getMessage());
} catch (IOException ex) {
    System.err.println("Connection failed: " + ex.getMessage());
}
~~~

Timeout ở đây chỉ điều khiển thao tác kết nối của Socket. Nó không đặt giới hạn cho toàn bộ thời gian đọc response hoặc xử lý dữ liệu sau khi kết nối thành công.

### 3.2. `Socket.setSoTimeout(timeoutMillis)`

`setSoTimeout` cấu hình thời gian chờ cho thao tác đọc trên `InputStream` của socket:

~~~java
socket.setSoTimeout(5_000);
int value = socket.getInputStream().read();
~~~

Nếu không có dữ liệu để đọc trong thời gian chờ, thao tác đọc ném `SocketTimeoutException`.

- `timeoutMillis > 0`: giới hạn thời gian chờ cho một thao tác đọc.
- `timeoutMillis == 0`: chờ đọc vô hạn.
- Giá trị âm không hợp lệ.

Điểm quan trọng: `SO_TIMEOUT` **không phải deadline tổng cho toàn bộ response**. Nếu ứng dụng đọc nhiều lần và mỗi lần đều nhận được một ít dữ liệu trước khi timeout, tổng thời gian đọc có thể dài hơn giá trị đã cấu hình.

Ví dụ, timeout đọc là 5 giây không có nghĩa toàn bộ tệp phải được truyền xong trong 5 giây. Nó giới hạn khoảng chờ cho một lần đọc bị block.

### 3.3. Kết hợp connect và read timeout

~~~java
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.SocketTimeoutException;

try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("example.com", 80), 3_000);
    socket.setSoTimeout(5_000);

    try (InputStream input = socket.getInputStream()) {
        int firstByte = input.read();
        System.out.println(firstByte);
    }
}
~~~

Ở đây:

- Kết nối TCP được giới hạn 3 giây.
- Mỗi lần đọc có thể chờ tối đa 5 giây.
- Việc đóng Socket giải phóng kết nối khi không còn sử dụng.

Nếu cần deadline tổng, ứng dụng phải tự tính ngân sách còn lại và điều chỉnh timeout hoặc hủy thao tác khi hết hạn.

### 3.4. Timeout đọc không đóng socket tự động

Khi một thao tác đọc ném `SocketTimeoutException`, socket không nhất thiết bị đóng. Ứng dụng có thể xử lý, thử đọc lại hoặc đóng kết nối tùy giao thức. Tuy nhiên, việc thử đọc lại chỉ hợp lý nếu trạng thái giao thức vẫn còn đồng bộ và dữ liệu chưa bị mất hoặc xử lý dở.

Không bắt timeout rồi tiếp tục sử dụng kết nối một cách mù quáng; cần hiểu giao thức và trạng thái parser trước khi tiếp tục.

## 4. Timeout với URLConnection và HttpURLConnection

`URLConnection` là API truyền thống để truy cập tài nguyên qua URL. Nó cung cấp hai cấu hình:

- `setConnectTimeout(int timeout)`.
- `setReadTimeout(int timeout)`.

Cả hai nhận milliseconds. Giá trị 0 có nghĩa không giới hạn thời gian chờ; giá trị âm không hợp lệ.

### 4.1. Ví dụ đọc HTTP bằng HttpURLConnection

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

URL url = new URL("https://example.com/");
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(3_000);
connection.setReadTimeout(5_000);
connection.setRequestMethod("GET");

try {
    int status = connection.getResponseCode();
    InputStream body = status >= 400
            ? connection.getErrorStream()
            : connection.getInputStream();

    if (body != null) {
        try (body) {
            String text = new String(
                    body.readAllBytes(),
                    StandardCharsets.UTF_8);
            System.out.println(text);
        }
    }
} finally {
    connection.disconnect();
}
~~~

Đây là ví dụ tối giản cho một response văn bản nhỏ. Với response lớn, nên đọc theo buffer thay vì dùng `readAllBytes` để tránh nạp toàn bộ body vào bộ nhớ.

### 4.2. Read timeout không phải tổng thời gian request

`setReadTimeout` giới hạn thời gian chờ đọc dữ liệu khi không có dữ liệu sẵn. Nếu máy chủ gửi dữ liệu nhỏ giọt nhưng mỗi lần đọc đều nhận được dữ liệu trước timeout, tổng thời gian xử lý có thể vượt nhiều lần timeout.

`HttpURLConnection` không cung cấp một cấu hình request deadline tổng quát tương đương `HttpRequest.Builder.timeout`. Nếu cần giới hạn tổng thời gian, ứng dụng phải quản lý deadline, việc hủy và đóng tài nguyên phù hợp.

### 4.3. Phân biệt HTTP status với lỗi mạng

HTTP 404, 429 hoặc 500 là **HTTP response hợp lệ về mặt giao thức**, không tự động đồng nghĩa với exception mạng. Với `HttpURLConnection`, cần đọc response code và chọn `getInputStream` hoặc `getErrorStream` theo status.

Một lỗi kết nối, timeout hoặc lỗi TLS thường được báo qua exception. Không nên chỉ bắt `IOException` rồi coi mọi status HTTP là lỗi kết nối.

## 5. HttpClient hiện đại trong Java 17

`java.net.http.HttpClient` được chuẩn hóa từ Java 11 và có sẵn trong Java 17. Đây thường là lựa chọn phù hợp cho HTTP client mới vì API hỗ trợ request/response, timeout, redirect, đồng bộ và bất đồng bộ.

Hai cấu hình quan trọng:

- `HttpClient.Builder.connectTimeout(Duration)`: giới hạn thời gian thiết lập kết nối.
- `HttpRequest.Builder.timeout(Duration)`: giới hạn thời gian chờ phản hồi cho request.

Ví dụ:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/status"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.body());
~~~

### 5.1. Connect timeout

`connectTimeout` đặt trên `HttpClient.Builder`, không đặt trên từng request builder. Nó được dùng khi client cần thiết lập một kết nối mới. Nếu kết nối có thể được tái sử dụng từ connection pool, thao tác đó có thể không cần thiết lập kết nối mới nên connect timeout không nhất thiết được áp dụng cho request đó.

Nếu không cấu hình connect timeout, client không đặt giới hạn thời gian kết nối riêng ở mức API này.

Nếu thời gian thiết lập kết nối vượt giới hạn, có thể nhận `HttpConnectTimeoutException` (một dạng `HttpTimeoutException`).

### 5.2. Request timeout

`HttpRequest.Builder.timeout(Duration)` đặt timeout cho một request:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

Nếu không đặt timeout, API không giới hạn thời gian chờ phản hồi bằng cấu hình request timeout này. Nếu response không được nhận trong thời hạn đã đặt, client có thể ném `HttpTimeoutException`.

`Duration` phải là khoảng thời gian dương; giá trị zero hoặc âm không hợp lệ cho timeout của request. Nên cấu hình một thời hạn rõ ràng thay vì dựa vào mặc định không giới hạn.

### 5.3. Request timeout và connect timeout cùng tồn tại

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(6))
        .GET()
        .build();
~~~

Hai cấu hình bảo vệ hai khía cạnh:

- Kết nối mới phải được thiết lập trong ngân sách connect timeout.
- Request phải nhận response trong ngân sách request timeout.

Đây không phải hai khoảng thời gian luôn được cộng lại thành một deadline cố định 8 giây. Chúng có thể chạy trong cùng một request; giới hạn nào hết trước sẽ quyết định lỗi timeout tương ứng. Ứng dụng vẫn nên có deadline tổng riêng nếu cần kiểm soát cả các bước trước/sau HTTP hoặc nhiều lần retry.

### 5.4. Response body dạng streaming

Với `BodyHandlers.ofString()`, `send` hoàn tất sau khi body được thu thập thành String. Với `BodyHandlers.ofInputStream()`, response có thể được trả về kèm một `InputStream` để ứng dụng đọc body sau đó.

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    // Đọc và xử lý body.
}
~~~

Khi dùng body streaming, cần quản lý việc đọc và đóng stream. Không nên giả định request timeout là deadline cho mọi công việc ứng dụng thực hiện sau khi đã nhận response object; nếu cần giới hạn thời gian đọc body hoặc xử lý tiếp theo, hãy thiết kế deadline/timeout phù hợp cho giai đoạn đó.

## 6. Xử lý exception của HttpClient

Các exception quan trọng:

| Exception | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `HttpConnectTimeoutException` | Hết thời gian thiết lập kết nối mới | Kiểm tra endpoint, mạng, tải và connect timeout |
| `HttpTimeoutException` | Request không nhận được response trong thời hạn | Kiểm tra server, request timeout và deadline |
| `ConnectException` | Kết nối bị từ chối hoặc không thiết lập được | Kiểm tra host, port, dịch vụ và firewall |
| `UnknownHostException` | Không phân giải được hostname | Kiểm tra DNS, tên host và cấu hình mạng |
| `SSLException` | Lỗi trong quá trình TLS/SSL | Kiểm tra chứng chỉ, trust store, hostname và cấu hình TLS |
| `IOException` | Lỗi I/O tổng quát | Xem nguyên nhân cụ thể và trạng thái tài nguyên |
| `InterruptedException` | Thread đang chờ bị interrupt | Khôi phục interrupt hoặc truyền tiếp theo hợp đồng |

`HttpConnectTimeoutException` là lớp con của `HttpTimeoutException`, vì vậy nếu muốn xử lý riêng thì phải bắt lớp con trước:

~~~java
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    System.out.println(response.statusCode());
} catch (HttpConnectTimeoutException ex) {
    System.err.println("Connect timed out: " + ex.getMessage());
} catch (HttpTimeoutException ex) {
    System.err.println("Request timed out: " + ex.getMessage());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Request interrupted", ex);
} catch (IOException ex) {
    System.err.println("HTTP I/O failed: " + ex.getMessage());
}
~~~

Trong code thư viện hoặc service layer, có thể khai báo phương thức ném tiếp `IOException` và `InterruptedException` thay vì chuyển mọi lỗi thành `IllegalStateException`. Ví dụ trên chỉ minh họa cách khôi phục trạng thái interrupt khi không truyền exception ra ngoài.

### 6.1. HTTP error status không phải exception tự động

`HttpClient.send` trả về `HttpResponse` ngay cả khi server phản hồi status 400 hoặc 500. Ứng dụng cần kiểm tra:

~~~java
int status = response.statusCode();
if (status >= 200 && status < 300) {
    // Thành công theo chính sách của ứng dụng.
} else {
    // Phân loại 4xx, 5xx hoặc các status khác.
}
~~~

Không dùng exception timeout để biểu diễn mọi lỗi HTTP. Một response 503 cho biết server đã phản hồi; một timeout cho biết client không nhận được response trong thời hạn.

### 6.2. Giữ nguyên trạng thái interrupt

`InterruptedException` báo hiệu thread bị yêu cầu dừng chờ hoặc hủy công việc. Nếu bắt exception rồi bỏ qua, hệ thống có thể mất tín hiệu hủy:

~~~java
try {
    client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Trong nhiều ứng dụng, cách tốt hơn là truyền `InterruptedException` lên tầng gọi để tầng đó quyết định dừng workflow. Chỉ khôi phục cờ interrupt khi bạn đã bắt exception và không truyền nó tiếp.

## 7. Gửi request bất đồng bộ và hủy công việc

`HttpClient.sendAsync` trả về `CompletableFuture`:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenApply(HttpResponse::statusCode)
        .thenAccept(System.out::println)
        .exceptionally(ex -> {
            System.err.println("Request failed: " + ex.getMessage());
            return null;
        });
~~~

Request timeout vẫn được cấu hình trên `HttpRequest`. Khi cần hủy tác vụ, có thể gọi `future.cancel(true)`; việc hủy là best-effort theo API và không có nghĩa máy chủ chắc chắn đã ngừng xử lý request.

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

// Khi workflow không còn cần kết quả:
future.cancel(true);
~~~

Không dùng `CompletableFuture.orTimeout` như một sự thay thế hoàn toàn cho timeout của HttpRequest mà không hiểu hệ quả: việc hoàn tất một future bằng timeout không nhất thiết tương đương với việc hủy exchange mạng bên dưới. Hãy đặt timeout ở API HTTP và quản lý cancellation theo nhu cầu ứng dụng.

## 8. Deadline tổng và ngân sách thời gian

Một workflow có thể gồm nhiều bước:

1. Gọi dịch vụ xác thực.
2. Gọi dịch vụ dữ liệu.
3. Gọi dịch vụ thanh toán.
4. Retry một số bước khi gặp lỗi tạm thời.

Nếu mỗi bước đều được phép chờ 10 giây và có ba lần retry, tổng thời gian có thể dài hơn rất nhiều thời hạn mà người dùng chấp nhận. Do đó, cần phân biệt **timeout cho từng thao tác** và **deadline tổng cho workflow**.

### 8.1. Dùng System.nanoTime để đo thời gian trôi qua

Để đo deadline nội bộ, dùng đồng hồ đơn điệu `System.nanoTime()` thay vì `System.currentTimeMillis()`. Wall clock có thể bị điều chỉnh bởi đồng bộ thời gian hoặc cấu hình hệ thống; deadline tương đối cần đo thời gian trôi qua.

~~~java
long timeoutNanos = Duration.ofSeconds(10).toNanos();
long deadline = System.nanoTime() + timeoutNanos;

long remainingNanos = deadline - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Overall deadline exceeded");
}
~~~

Trong code sản xuất, cần tránh overflow khi cộng thời hạn cực lớn và kiểm tra ngân sách trước mỗi bước. Với thời hạn thực tế ngắn, phép tính dạng hiệu `deadline - System.nanoTime()` là cách phổ biến để tính thời gian còn lại.

### 8.2. Truyền thời gian còn lại vào từng request

~~~java
Duration remaining = Duration.ofNanos(remainingNanos);

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(remaining)
        .GET()
        .build();
~~~

Không đặt lại một timeout đầy đủ cho mỗi lần retry nếu tổng deadline đã gần hết. Mỗi thao tác nên nhận ngân sách còn lại.

### 8.3. Không phải timeout nào cũng kiểm soát DNS

Phân giải hostname có thể diễn ra qua resolver của hệ điều hành hoặc runtime. Không nên khẳng định connect timeout của mọi API luôn giới hạn chính xác toàn bộ thời gian DNS trong mọi môi trường. Nếu DNS là phần quan trọng của deadline, cần hiểu resolver và cơ chế mạng của môi trường triển khai, đồng thời đo thực tế.

## 9. Retry sau timeout và lỗi mạng

Timeout thường là lỗi tạm thời, nhưng **không phải lúc nào cũng an toàn để retry**. Máy chủ có thể đã nhận và thực hiện request nhưng response bị thất lạc hoặc đến trễ. Nếu gửi lại một thao tác tạo giao dịch, tạo đơn hàng hoặc trừ tiền, có thể thực hiện hành động hai lần.

### 9.1. Retry có giới hạn

Một chính sách retry nên có:

- Số lần thử tối đa.
- Backoff giữa các lần thử.
- Jitter để tránh nhiều client retry đồng loạt.
- Deadline tổng.
- Danh sách lỗi được phép retry.
- Quy tắc idempotency hoặc idempotency key với thao tác có side effect.

Không retry vô hạn.

### 9.2. Exponential backoff

Một dạng backoff tăng theo số lần thử:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Trong đó `d0` là thời gian chờ ban đầu, `dmax` là giới hạn. Có thể thêm jitter ngẫu nhiên để giảm hiện tượng nhiều client cùng gọi lại vào một thời điểm.

Ví dụ minh họa đơn giản:

~~~java
static Duration backoff(int attempt) {
    long baseMillis = 200;
    long capMillis = 5_000;
    int exponent = Math.min(attempt, 10);
    long delay = Math.min(capMillis, baseMillis * (1L << exponent));
    return Duration.ofMillis(delay);
}
~~~

Đoạn này chỉ tính khoảng chờ; code gọi thực tế còn phải kiểm tra deadline còn đủ không và thêm jitter phù hợp.

### 9.3. Lỗi nào có thể retry?

| Tình huống | Quyết định thường gặp |
|---|---|
| Connect timeout hoặc lỗi kết nối tạm thời | Có thể retry nếu còn deadline và endpoint có thể phục hồi |
| Read/request timeout | Chỉ retry nếu thao tác an toàn hoặc có idempotency bảo đảm |
| DNS hostname không tồn tại | Thường không retry liên tục; kiểm tra cấu hình |
| TLS certificate invalid | Không retry như lỗi tạm thời; sửa trust/certificate |
| HTTP 400/401/403 | Thường không retry nếu request hoặc quyền truy cập không thay đổi |
| HTTP 429 | Tuân theo rate limit và `Retry-After` nếu có |
| HTTP 500/502/503/504 | Có thể retry tùy ngữ nghĩa thao tác, chính sách server và deadline |

Các quyết định trên là hướng dẫn chung. Mã ứng dụng cần dựa vào đặc tả API và tính idempotent của từng thao tác.

### 9.4. POST và idempotency

Một request POST có thể tạo side effect. Nếu client timeout sau khi gửi request, không thể kết luận server chưa xử lý. Trước khi retry:

1. Xác định endpoint có idempotent hay không.
2. Nếu server hỗ trợ, gửi cùng idempotency key cho các lần thử của cùng một thao tác.
3. Không tạo key mới cho mỗi lần retry nếu mục tiêu là nhận diện cùng một thao tác.
4. Nếu không có cơ chế idempotency, cần thiết kế đối soát hoặc truy vấn trạng thái trước khi gửi lại.

## 10. Quản lý tài nguyên khi xảy ra lỗi

Timeout không tự thay thế trách nhiệm đóng tài nguyên. Với Socket, reader, writer và stream body, hãy đóng bằng try-with-resources hoặc cơ chế sở hữu tài nguyên phù hợp.

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress(host, port), 2_000);
    socket.setSoTimeout(3_000);

    try (var input = socket.getInputStream()) {
        // Đọc dữ liệu.
    }
}
~~~

Với HttpURLConnection, gọi `disconnect()` trong `finally` khi kết thúc sử dụng. Với HttpClient Java 17, không cần và không thể dùng try-with-resources cho `HttpClient` như các lớp AutoCloseable ở phiên bản Java mới hơn; hãy dùng client theo vòng đời ứng dụng và đóng body stream nếu chọn streaming handler.

Không giữ connection, stream hoặc thread chờ vô thời hạn khi lỗi đã được xác định. Đồng thời, tránh đóng tài nguyên dùng chung mà một thành phần khác vẫn sở hữu.

## 11. Ví dụ tổng hợp với HttpClient Java 17

Chương trình dưới đây cấu hình connect timeout và request timeout, phân biệt timeout với HTTP status, đồng thời khôi phục trạng thái interrupt:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class Main {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "text/html")
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            int status = response.statusCode();
            if (status >= 200 && status < 300) {
                System.out.println("Success: " + status);
            } else {
                System.out.println("HTTP response: " + status);
            }
        } catch (HttpConnectTimeoutException ex) {
            System.err.println("Connect timeout: " + ex.getMessage());
        } catch (HttpTimeoutException ex) {
            System.err.println("Request timeout: " + ex.getMessage());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.err.println("Request interrupted");
        } catch (IOException ex) {
            System.err.println("Network or I/O error: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

Thời gian thực tế phụ thuộc mạng, DNS, TLS và máy chủ. Không dùng kết quả chạy thành công trên một mạng cụ thể để kết luận timeout luôn xảy ra đúng đến từng mili giây; timeout là giới hạn chờ theo API và môi trường thực thi.

## 12. Những lỗi thường gặp

### 12.1. Chỉ đặt connect timeout

Kết nối có thể thành công nhưng server không trả response. Nếu không có request/read timeout, thread vẫn có thể chờ rất lâu.

**Cách xử lý:** đặt cả timeout kết nối và timeout chờ response phù hợp với API đang dùng.

### 12.2. Nghĩ read timeout là deadline tổng

Read timeout trên Socket/URLConnection thường giới hạn khoảng chờ cho thao tác đọc, không phải tổng thời gian của cả response.

**Cách xử lý:** tạo deadline tổng bằng đồng hồ đơn điệu, tính thời gian còn lại cho mỗi giai đoạn.

### 12.3. Để timeout mặc định không giới hạn

Nhiều API có mặc định timeout bằng 0 hoặc không đặt timeout, nghĩa là chờ vô hạn theo hợp đồng API.

**Cách xử lý:** đặt giá trị cụ thể dựa trên SLA, trải nghiệm người dùng và thời gian xử lý thực tế.

### 12.4. Bắt mọi lỗi rồi retry

Lỗi TLS, lỗi xác thực, HTTP 400 hoặc request sai định dạng không được giải quyết bằng retry liên tục.

**Cách xử lý:** phân loại exception và HTTP status, chỉ retry lỗi tạm thời được phép.

### 12.5. Retry request có side effect mà không có idempotency

Timeout không chứng minh server chưa thực hiện request.

**Cách xử lý:** dùng idempotency key hoặc kiểm tra trạng thái trước khi gửi lại thao tác.

### 12.6. Nuốt InterruptedException

Bắt exception rồi bỏ qua khiến tín hiệu dừng thread bị mất.

**Cách xử lý:** truyền tiếp exception hoặc gọi `Thread.currentThread().interrupt()` trước khi kết thúc.

### 12.7. Nhầm HTTP 500 với IOException

HTTP status là phản hồi từ server, không phải lúc nào cũng là exception.

**Cách xử lý:** kiểm tra `response.statusCode()` hoặc `getResponseCode()`.

### 12.8. Quên đóng response body stream

Với body handler streaming, không đóng stream có thể giữ tài nguyên hoặc ảnh hưởng việc tái sử dụng kết nối.

**Cách xử lý:** dùng try-with-resources và tuân thủ quyền sở hữu tài nguyên.

## 13. Bài tập thực hành

### Bài 1 — Socket connect và read timeout

Viết client TCP kết nối tới host/port được cấu hình với connect timeout 2 giây và read timeout 4 giây. Bắt riêng `SocketTimeoutException` và `IOException`. Giải thích hai timeout giới hạn hai giai đoạn khác nhau.

### Bài 2 — HttpClient timeout

Tạo `HttpClient` với connect timeout 2 giây và `HttpRequest` với timeout 5 giây. Gửi GET tới endpoint thử nghiệm. Phân biệt `HttpConnectTimeoutException`, `HttpTimeoutException` và HTTP 503.

### Bài 3 — Xử lý interrupt

Viết phương thức gọi `client.send`. Nếu bắt `InterruptedException`, khôi phục interrupt flag rồi truyền exception tiếp hoặc kết thúc theo hợp đồng. Giải thích vì sao không nên nuốt exception.

### Bài 4 — Deadline tổng

Đặt deadline tổng 10 giây bằng `System.nanoTime()`. Trước mỗi request, tính thời gian còn lại rồi đặt `HttpRequest.timeout(remaining)`. Không bắt đầu lần thử mới khi ngân sách đã hết.

### Bài 5 — Retry có kiểm soát

Thiết kế tối đa ba lần thử cho một GET khi gặp timeout hoặc lỗi kết nối tạm thời. Thêm exponential backoff có giới hạn và jitter. Không retry HTTP 400/401 hoặc lỗi TLS certificate. Giải thích vì sao cùng chính sách không thể áp dụng máy móc cho POST tạo giao dịch.

### Bài 6 — Phân biệt read timeout và tổng thời gian

Mô phỏng server gửi một phần dữ liệu trước mỗi khoảng read timeout. Giải thích vì sao client có thể tiếp tục đọc lâu hơn tổng thời gian timeout nếu mỗi lần đọc đều nhận dữ liệu kịp thời. Đề xuất deadline tổng để giới hạn toàn bộ quá trình.

## 14. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Phân biệt connect timeout, read timeout, request timeout và deadline tổng.
2. Dùng `Socket.connect` để giới hạn thời gian thiết lập kết nối và `Socket.setSoTimeout` để giới hạn thao tác đọc.
3. Cấu hình `URLConnection`/`HttpURLConnection` bằng `setConnectTimeout` và `setReadTimeout`.
4. Dùng `HttpClient.Builder.connectTimeout` và `HttpRequest.Builder.timeout` trong Java 17.
5. Giải thích mặc định không đặt timeout và ý nghĩa của giá trị 0 ở các API dùng milliseconds.
6. Phân biệt exception mạng/timeout với HTTP status code.
7. Xử lý `HttpConnectTimeoutException`, `HttpTimeoutException`, `IOException` và `InterruptedException` đúng thứ tự và đúng ý nghĩa.
8. Quản lý cancellation, body stream và tài nguyên sau lỗi.
9. Thiết kế retry giới hạn, backoff, deadline và idempotency phù hợp.
10. Biết timeout ở client không bảo đảm server đã dừng xử lý request.

## 15. Tài liệu chính thức

- [Java SE 17 API — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `connect`, `setSoTimeout` và hành vi timeout của socket.
- [Java SE 17 API — `URLConnection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): `setConnectTimeout` và `setReadTimeout`.
- [Java SE 17 API — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client đồng bộ/bất đồng bộ và cấu hình kết nối.
- [Java SE 17 API — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html#connectTimeout(java.time.Duration)): timeout kết nối.
- [Java SE 17 API — `HttpRequest.Builder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html#timeout(java.time.Duration)): timeout cho request.
- [Java SE 17 API — `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) và [`HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): các loại timeout của HttpClient.
- [Java SE 17 API — `SocketTimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): lỗi khi thao tác đọc socket hết thời gian chờ.

**Ghi nhớ:** connect timeout bảo vệ lúc thiết lập kết nối; read timeout bảo vệ khoảng chờ của thao tác đọc; request timeout bảo vệ thời gian chờ phản hồi ở HTTP client; deadline tổng bảo vệ toàn bộ workflow. Phân loại lỗi đúng, đóng tài nguyên, giữ trạng thái interrupt và retry có điều kiện giúp ứng dụng mạng không bị treo vô hạn hoặc lặp side effect.
