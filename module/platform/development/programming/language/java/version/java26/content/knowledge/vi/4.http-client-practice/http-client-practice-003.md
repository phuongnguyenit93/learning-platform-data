# Thời gian chờ kết nối, yêu cầu và xử lý hủy

Khi gọi HTTP từ Java, một thao tác có thể mất thời gian ở nhiều giai đoạn: chờ thiết lập kết nối, gửi request, chờ response header và nhận response body. `HttpClient` cung cấp hai cấu hình timeout có phạm vi khác nhau: `HttpClient.Builder.connectTimeout(...)` giới hạn thời gian thiết lập một kết nối mới, còn `HttpRequest.Builder.timeout(...)` giới hạn thời gian thực thi một request. Với request bất đồng bộ, `CompletableFuture.cancel(true)` cho phép yêu cầu hủy exchange đang chạy.

Trong JDK 26, timeout của request trong implementation `HttpClient` tích hợp đã bao gồm cả giai đoạn tiêu thụ response body, đến khi `BodySubscriber` hoàn tất. Vì vậy, khi nâng cấp hoặc cấu hình ứng dụng, cần hiểu đúng phạm vi timeout, cách xử lý body streaming và giới hạn của việc hủy request. Các ví dụ dưới đây dùng API `java.net.http` hiện hành; không cần API legacy hay bật preview.

## 1. Phân biệt timeout kết nối và timeout request

| Cấu hình | Đặt ở đâu | Phạm vi | Ngoại lệ thường gặp |
|---|---|---|---|
| Connect timeout | `HttpClient.Builder.connectTimeout(Duration)` | Thời gian thiết lập kết nối mới; implementation JDK tích hợp bao gồm TLS handshake | `HttpConnectTimeoutException` |
| Request timeout | `HttpRequest.Builder.timeout(Duration)` | Từ lúc bắt đầu thực thi request đến khi response được tạo; implementation JDK tích hợp giữ timeout đến khi response body subscriber hoàn tất | `HttpTimeoutException` |

Hai timeout có thể cùng tác động đến một request. Request timeout bao trùm quá trình thực thi rộng hơn; connect timeout đặt giới hạn riêng cho giai đoạn mở kết nối mới. Trong giai đoạn thiết lập kết nối, giới hạn nào hết trước có thể quyết định lỗi được quan sát. Ví dụ, nếu request timeout là 5 giây và connect timeout là 2 giây, kết nối mới có thể thất bại sau khoảng 2 giây. Nếu request timeout là 1 giây, request có thể hết hạn trước khi connect timeout 2 giây đến hạn.

`connectTimeout` chỉ có tác dụng khi client cần tạo kết nối mới. Nếu một kết nối phù hợp đã có trong connection pool và được tái sử dụng, timeout này không giới hạn thời gian chờ trên kết nối đó. Do vậy, không thể dùng riêng connect timeout để bảo vệ toàn bộ request khỏi việc server phản hồi chậm.

`HttpRequest.timeout` thuộc về từng request. Nếu không cấu hình, thời gian chờ được xem như vô hạn. Cả hai phương thức nhận `Duration` dương; giá trị bằng hoặc nhỏ hơn 0 gây `IllegalArgumentException`.

## 2. Đặt timeout cho client và request

Ví dụ sau giới hạn kết nối mới ở 3 giây và tổng thời gian thực thi request ở 8 giây:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class HttpTimeoutExample {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://example.com/api/status");

        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString());

                System.out.println("HTTP " + response.statusCode());
                System.out.println(response.body());
            } catch (HttpConnectTimeoutException e) {
                System.err.println("Không thiết lập được kết nối trong thời hạn cho phép");
            } catch (HttpTimeoutException e) {
                System.err.println("Request vượt quá thời hạn thực thi");
            }
        }
    }
}
```

`HttpConnectTimeoutException` là lớp con của `HttpTimeoutException`, vì vậy phải bắt loại kết nối cụ thể trước loại timeout tổng quát. Nếu bắt `HttpTimeoutException` trước, nhánh bắt `HttpConnectTimeoutException` phía sau sẽ không hợp lệ vì không thể bắt một lớp con sau lớp cha.

Timeout là giới hạn thời gian, không phải bảo đảm server đã nhận hay chưa nhận request. Khi timeout xảy ra, client không có kết quả response hợp lệ để trả về cho luồng gọi. Với các thao tác có tác dụng phụ như tạo đơn hàng hoặc trừ tiền, timeout không chứng minh thao tác phía server chưa được thực hiện. Ứng dụng cần thiết kế idempotency key, truy vấn trạng thái hoặc cơ chế đối soát phù hợp trước khi tự động gửi lại.

## 3. Phạm vi request timeout trong JDK 26

Theo hợp đồng API, timeout request đo từ thời điểm bắt đầu thực thi đến ít nhất thời điểm `HttpResponse` được tạo. Khoảng thời gian này bao gồm lấy kết nối để truyền request và nhận response header. Implementation `HttpClient` tích hợp của JDK 26 kéo dài timer đến khi `BodySubscriber` của response hoàn tất.

Điểm này có ý nghĩa với body lớn hoặc server truyền dữ liệu chậm. Ví dụ, nếu response header đến sau 1 giây nhưng body cần thêm 15 giây để tải, request có timeout 5 giây vẫn có thể hết hạn trong lúc nhận body với implementation JDK tích hợp. Không nên cấu hình timeout chỉ dựa trên thời gian server trả header.

`BodyHandlers.ofString()` và `BodyHandlers.ofByteArray()` thường hoàn tất subscriber sau khi body đã được nhận đầy đủ. Với handler streaming như `BodyHandlers.ofInputStream()`, việc nhận được `HttpResponse` không có nghĩa ứng dụng đã đọc hết body. Ứng dụng phải đọc stream đến hết, đóng hoặc hủy stream để request được xem là hoàn tất và tài nguyên được giải phóng. Không nên mặc định thời gian đọc stream ở phía ứng dụng được giới hạn giống hệt thời gian nhận body của subscriber; nếu cần deadline cho thao tác đọc stream, hãy quản lý riêng và luôn đóng stream khi kết thúc. Nếu bỏ quên stream, request có thể vẫn còn mở và việc shutdown client có thể bị đình trệ.

Ví dụ quản lý stream đúng cách:

```java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class StreamingResponseExample {
    public static void main(String[] args) throws Exception {
        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com/large-file"))
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();

            HttpResponse<InputStream> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream());

            try (InputStream body = response.body()) {
                byte[] buffer = new byte[8192];
                long totalBytes = 0;
                int count;
                while ((count = body.read(buffer)) != -1) {
                    totalBytes += count;
                }
                System.out.println("Đã đọc " + totalBytes + " byte");
            }
        }
    }
}
```

Đối với custom `BodySubscriber`, subscriber phải tiếp tục yêu cầu dữ liệu cho đến khi nhận `onComplete` hoặc `onError`, hoặc hủy subscription khi không còn cần dữ liệu. Nếu ứng dụng tự triển khai subscriber mà không tiêu thụ hay hủy dữ liệu, request và tài nguyên liên quan có thể tiếp tục tồn tại.

Timeout request chỉ kiểm soát một lần thực thi HTTP. Nếu ứng dụng thực hiện nhiều request nối tiếp, retry hoặc thêm thời gian xử lý nghiệp vụ sau response, tổng thời gian của cả quy trình có thể vượt timeout của một request. Khi cần deadline cho toàn bộ nghiệp vụ, hãy quản lý deadline ở tầng ứng dụng và truyền phần thời gian còn lại cho từng request.

## 4. Timeout với sendAsync

`sendAsync()` trả về `CompletableFuture<HttpResponse<T>>` ngay sau khi gửi yêu cầu bất đồng bộ. Nếu timeout kết nối xảy ra, future hoàn tất ngoại lệ với `HttpConnectTimeoutException`. Nếu request timeout xảy ra, future hoàn tất ngoại lệ với `HttpTimeoutException`.

Khi dùng `join()`, lỗi bất đồng bộ thường được bọc trong `CompletionException`. Cần kiểm tra `getCause()` để phân biệt timeout kết nối với timeout request:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.concurrent.CompletionException;

public class AsyncTimeoutExample {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com/api"))
                    .timeout(Duration.ofSeconds(6))
                    .GET()
                    .build();

            try {
                HttpResponse<String> response = client
                        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
                        .join();

                System.out.println(response.statusCode());
            } catch (CompletionException e) {
                Throwable cause = e.getCause();
                if (cause instanceof HttpConnectTimeoutException) {
                    System.err.println("Timeout khi thiết lập kết nối");
                } else if (cause instanceof HttpTimeoutException) {
                    System.err.println("Timeout khi thực thi request");
                } else {
                    throw e;
                }
            }
        }
    }
}
```

Nếu dùng `get()` thay cho `join()`, lỗi hoàn tất bất thường được bọc trong `ExecutionException`; luồng gọi cũng phải xử lý `InterruptedException`. Không nên bắt mọi `CompletionException` rồi coi đó là timeout, vì lỗi DNS, TLS, kết nối bị đóng và các lỗi I/O khác cũng có thể làm future hoàn tất bất thường.

## 5. Chủ động hủy một request bất đồng bộ

Khi người dùng bấm nút dừng, một màn hình không còn cần dữ liệu hoặc một tác vụ cấp cao hết deadline, ứng dụng có thể gọi `cancel(true)` trên future trả trực tiếp từ `sendAsync()`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

public class CancelHttpRequestExample {
    public static void main(String[] args) {
        try (HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build()) {

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com/slow-report"))
                    .timeout(Duration.ofSeconds(60))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> exchange =
                    client.sendAsync(
                            request,
                            HttpResponse.BodyHandlers.ofString());

            // Gọi tại thời điểm ứng dụng quyết định không cần kết quả nữa.
            boolean cancellationAccepted = exchange.cancel(true);
            System.out.println("Cancellation accepted: " + cancellationAccepted);

            try {
                exchange.join();
            } catch (CancellationException e) {
                System.out.println("Future đã bị hủy");
            }
        }
    }
}
```

Ví dụ gọi hủy ngay để minh họa API; trong ứng dụng thực tế, lệnh `cancel(true)` thường được gọi từ callback của nút dừng, khi một tác vụ khác hoàn tất hoặc khi deadline nghiệp vụ đến hạn. Giá trị trả về cho biết future có được chuyển sang trạng thái canceled hay không. Nếu future đã hoàn tất, lệnh hủy có thể trả về `false`.

Implementation `HttpClient` mặc định của JDK trả về future có thể hủy. Gọi `cancel(true)` trên future chưa hoàn tất sẽ yêu cầu hủy HTTP exchange nhằm giải phóng tài nguyên sớm. Đây là thao tác best-effort: API không bảo đảm chính xác thời điểm yêu cầu hủy có hiệu lực. Request vẫn có thể đã được gửi đến server và server có thể đã bắt đầu xử lý ở một luồng khác. Tài nguyên phía client cũng có thể chỉ được giải phóng sau đó.

Tài liệu JDK mô tả một số hệ quả theo giao thức:

- Với HTTP/1.1, hủy request có thể khiến kết nối bên dưới bị đóng đột ngột.
- Với HTTP/2, hủy request có thể khiến stream tương ứng bị reset.
- Không nên suy diễn một hành vi hủy ở tầng transport cụ thể cho HTTP/3 nếu API không cam kết điều đó.

Hủy ở client không phải lệnh rollback giao dịch trên server. Nếu request đã tạo dữ liệu, gửi email hoặc thực hiện thanh toán, việc client ngừng chờ không tự đảo ngược tác động. Với thao tác có tác dụng phụ, cần dùng idempotency key hoặc API tra cứu trạng thái để xử lý trường hợp kết quả bị mất do timeout/hủy.

## 6. Hủy request đồng bộ bằng interrupt

`HttpClient.send()` chặn luồng gọi cho đến khi nhận response. Nếu luồng bị interrupt, implementation mặc định cố gắng hủy HTTP exchange và ném `InterruptedException`. Việc hủy vẫn không có bảo đảm thời điểm chính xác; request có thể đã tới server và server có thể đang xử lý.

Nếu tầng hiện tại không thể tiếp tục xử lý interrupt và cần chuyển lỗi thành ngoại lệ khác, hãy khôi phục trạng thái interrupt trước khi rời khỏi tầng đó:

```java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());
    handle(response);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP operation was interrupted", e);
}
```

Nếu phương thức hiện tại có thể khai báo `throws InterruptedException`, hãy để ngoại lệ được truyền lên tầng gọi và để tầng đó quyết định cách xử lý. Không nên nuốt interrupt rồi tiếp tục chờ như thể không có yêu cầu dừng.

## 7. Phân biệt hủy future, timeout và shutdown client

| Thao tác | Mục đích | Phạm vi |
|---|---|---|
| `HttpRequest.Builder.timeout(...)` | Giới hạn thời gian thực thi một request | Một request |
| `CompletableFuture.cancel(true)` | Chủ động yêu cầu hủy exchange đang chạy | Request gắn với future đó |
| Interrupt luồng đang gọi `send()` | Báo luồng đồng bộ dừng chờ; `HttpClient` mặc định thử hủy exchange | Request của lần gọi đó |
| `HttpClient.close()` hoặc `shutdown()` | Ngừng nhận request mới và để các request đã gửi hoàn tất | Toàn bộ client |
| `HttpClient.shutdownNow()` | Yêu cầu shutdown tức thời và thử hủy các request chưa hoàn tất | Toàn bộ client; có thể làm gián đoạn nhiều request |

Không đóng hoặc shutdown một `HttpClient` dùng chung chỉ để hủy một request. `close()` thực hiện orderly shutdown và chờ các thao tác đã gửi hoàn tất; `shutdownNow()` có phạm vi toàn client và có thể làm gián đoạn các thao tác khác. Với request bất đồng bộ riêng lẻ, giữ lại future và hủy future đó khi không còn cần kết quả.

`CompletableFuture.orTimeout(...)` cũng cần được hiểu đúng: phương thức này làm future hoàn tất ngoại lệ sau một thời hạn, nhưng bản thân nó không thay thế timeout HTTP và không phải cam kết hủy exchange ở tầng mạng. Dùng `HttpRequest.timeout(...)` để giới hạn HTTP request; dùng `cancel(true)` khi ứng dụng cần chủ động yêu cầu hủy exchange.

## 8. Chọn giá trị timeout và xử lý retry

Không có một giá trị timeout đúng cho mọi API. Hãy dựa vào độ trễ thực tế, SLA, kích thước body, số lần retry và thời gian xử lý phía server. Một số nguyên tắc thực hành:

- Đặt connect timeout ngắn hơn giới hạn tổng nếu ứng dụng cần phát hiện sớm endpoint không thể kết nối.
- Request timeout phải đủ cho cả thời gian lấy kết nối, server xử lý, truyền response và tiêu thụ body theo cách `BodyHandler` đang dùng.
- Tạo deadline tổng cho nghiệp vụ có nhiều bước; không để mỗi lần retry bắt đầu một timeout đầy đủ khiến tổng thời gian vượt SLA.
- Chỉ retry khi lỗi có thể phục hồi và thao tác có tính idempotent hoặc có cơ chế chống lặp. Timeout không chứng minh server chưa thực hiện request.
- Dùng backoff có giới hạn và jitter khi retry để tránh tạo đợt tải dồn lên server đang gặp sự cố.
- Ghi log loại timeout, URI ở mức an toàn, thời lượng, số lần retry, giao thức thực tế và correlation/request ID; tránh ghi token, cookie hoặc dữ liệu nhạy cảm.
- Đối với body streaming, luôn đóng hoặc hủy stream khi ngừng đọc; với publisher/subscriber tự viết, hoàn tất hoặc hủy subscription đúng quy tắc.

## 9. Checklist kiểm chứng trong ứng dụng Java 26

1. Cấu hình `connectTimeout` ở `HttpClient` và `timeout` ở từng `HttpRequest`; kiểm tra cả trường hợp kết nối mới lẫn tái sử dụng connection pool.
2. Thử endpoint không phản hồi để quan sát `HttpConnectTimeoutException` và `HttpTimeoutException` theo giới hạn được đặt.
3. Thử response header đến nhanh nhưng body truyền chậm; xác nhận timeout với `BodyHandler` đang dùng.
4. Nếu dùng `InputStream` hoặc custom `BodySubscriber`, xác minh code luôn đọc hết, đóng hoặc hủy body/subscription.
5. Với `sendAsync`, kiểm tra future hoàn tất bình thường, hoàn tất ngoại lệ và bị hủy; xử lý `CompletionException` và `CancellationException` riêng.
6. Thử interrupt khi dùng `send()` và bảo toàn trạng thái interrupt nếu xử lý tại tầng hiện tại.
7. Thử hủy request đã bắt đầu gửi; xác minh ứng dụng không giả định server đã rollback tác vụ.
8. Đo thời gian đầu cuối, timeout, retry và tài nguyên còn mở trong môi trường có độ trễ hoặc lỗi mạng.

## 10. Những điểm cần nhớ

- `connectTimeout` giới hạn việc thiết lập kết nối mới; nếu tái sử dụng kết nối, timeout này không có tác dụng.
- `HttpRequest.timeout` giới hạn thực thi một request. Với implementation `HttpClient` tích hợp của JDK 26, timer tiếp tục đến khi response body subscriber hoàn tất.
- Không đặt request timeout đồng nghĩa thời gian chờ là vô hạn; duration không dương bị từ chối.
- `sendAsync()` trả về future; `cancel(true)` yêu cầu hủy exchange best-effort, không bảo đảm request chưa tới server hoặc server ngừng xử lý.
- `send()` có thể bị dừng bằng interrupt; implementation mặc định cố gắng hủy exchange và ném `InterruptedException`.
- Body streaming phải được tiêu thụ, đóng hoặc hủy để giải phóng tài nguyên; timeout của một request không tự tạo deadline cho toàn bộ quy trình nhiều bước.
- `close()` và `shutdownNow()` tác động đến toàn bộ client. Dùng hủy future cho một request cụ thể.

## Tài liệu tham khảo

- [Java SE 26 API: `HttpClient.Builder.connectTimeout`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 26 API: `HttpRequest.Builder.timeout`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 26 API: `HttpClient.send`, `sendAsync`, cancellation và shutdown](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 26 API: `HttpTimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 26 API: `HttpConnectTimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [Inside Java: HTTP Client Updates in Java 26](https://inside.java/2026/03/04/jdk-26-http-client/)
