# close và quá trình chờ hoàn tất request đã gửi

Từ Java 21, `java.net.http.HttpClient` triển khai `AutoCloseable` và cung cấp các phương thức quản lý vòng đời như `shutdown()`, `shutdownNow()`, `awaitTermination(Duration)`, `isTerminated()` và `close()`. Nhờ đó, ứng dụng có thể chủ động kết thúc một HTTP client khi không còn cần gửi request, đồng thời quyết định có chờ các request đã gửi hoàn tất hay không.

`close()` thực hiện **orderly shutdown**: client ngừng nhận request mới, cho các request đã gửi qua `send` hoặc `sendAsync` chạy đến khi hoàn tất, rồi chờ client kết thúc. Điều này không đồng nghĩa mọi response body tự được tiêu thụ. Nếu ứng dụng nhận body dạng streaming nhưng không đọc hết, đóng stream hoặc hủy subscription, request có thể vẫn được xem là chưa hoàn tất và làm `close()` chờ lâu.

## 1. Vì sao HttpClient cần vòng đời rõ ràng?

Một `HttpClient` không chỉ là đối tượng tạo request. Nó giữ cấu hình dùng chung và thường quản lý pool kết nối để tái sử dụng kết nối cho nhiều request. Các client khác nhau thường không chia sẻ connection pool. Vì vậy, tạo một client mới cho mỗi request thường làm mất lợi ích tái sử dụng kết nối và có thể tăng chi phí thiết lập kết nối.

Thông thường, ứng dụng nên dùng một client cho một phạm vi công việc hoặc vòng đời dịch vụ phù hợp, gửi nhiều request qua client đó, rồi đóng client khi phạm vi sử dụng kết thúc. Với Java 21, `close()` giúp thể hiện rõ thời điểm thu hồi sớm tài nguyên do client quản lý.

Các phương thức lifecycle của `HttpClient` được bổ sung từ Java 21. Khi biên dịch và chạy ứng dụng với Java 21 trở lên, có thể dùng `HttpClient` trong try-with-resources:

```java
import java.net.http.HttpClient;

try (HttpClient client = HttpClient.newHttpClient()) {
    // Gửi các request thuộc phạm vi sử dụng của client.
}
```

Khi rời khỏi khối `try`, Java gọi `client.close()`. Lệnh này có thể chờ các request đã gửi trong phạm vi client hoàn tất, nên không nên đặt một client dùng chung toàn ứng dụng trong try-with-resources của từng request.

## 2. close() thực hiện điều gì?

Theo API Java 21, `HttpClient.close()`:

1. Khởi tạo orderly shutdown.
2. Không chấp nhận request mới gửi qua `send` hoặc `sendAsync`.
3. Cho các request đã được submit trước đó chạy đến hoàn tất, bao gồm các thao tác nền cần thiết như chờ response được chuyển đến.
4. Chờ mọi operation liên quan hoàn tất và client chuyển sang trạng thái terminated.

Nếu client đã terminated, gọi `close()` lần nữa không tạo thêm tác động. `close()` không có tham số timeout và không trả về trạng thái hoàn tất; phương thức sẽ chờ cho đến khi client kết thúc theo hợp đồng của nó.

Điểm quan trọng là request được xem là hoàn tất theo quá trình xử lý response body, không chỉ khi đã nhận response headers. Với body handler trả về một giá trị đã được đọc đầy đủ như `String` hoặc `byte[]`, quá trình xử lý thường hoàn tất trước khi future hoặc `send()` trả kết quả. Với body streaming, ứng dụng còn phải tiêu thụ hoặc hủy luồng dữ liệu.

## 3. Phân biệt shutdown, shutdownNow, awaitTermination và close

Java 21 cung cấp các phương thức với mức độ chờ và mức độ can thiệp khác nhau:

| Phương thức | Tác dụng | Có chờ không? |
|---|---|---|
| `shutdown()` | Ngừng nhận request mới; cho request đã gửi chạy đến hoàn tất | Không |
| `awaitTermination(duration)` | Chờ client đã shutdown kết thúc trong khoảng thời gian tối đa | Có; trả `true` nếu kết thúc, `false` nếu hết thời gian |
| `isTerminated()` | Kiểm tra client đã hoàn tất các operation sau shutdown hay chưa | Không |
| `shutdownNow()` | Cố gắng bắt đầu shutdown ngay; implementation có thể cố interrupt operation đang chạy | Không bảo đảm operation sẽ dừng |
| `close()` | Orderly shutdown và chờ các operation hoàn tất | Có; không có timeout |

`isTerminated()` chỉ có thể trả về `true` sau khi đã gọi `shutdown()` hoặc `shutdownNow()`. Trước khi bắt đầu shutdown, `false` không có nghĩa là client đang gặp lỗi; client đơn giản vẫn đang ở trạng thái hoạt động.

### shutdown(): ngừng nhận việc mới, không đợi việc cũ

`shutdown()` là lựa chọn khi muốn đánh dấu client không còn nhận request mới nhưng cần tiếp tục chờ các request đã gửi. Phương thức trả về ngay sau khi khởi tạo shutdown; nó không chờ request hoàn tất.

Sau khi shutdown, các lời gọi `send` mới có thể thất bại bằng `IOException`; `sendAsync` có thể hoàn tất bất thường với `IOException`. Do đó, cần ngừng điều phối request mới trước hoặc cùng thời điểm bắt đầu shutdown.

### awaitTermination(Duration): chờ có giới hạn

`awaitTermination` chỉ có ý nghĩa sau khi shutdown đã được yêu cầu. Phương thức chờ đến khi một trong các điều kiện xảy ra:

- Tất cả operation cần thiết cho request đã gửi hoàn tất và client terminated.
- Hết khoảng thời gian `Duration` được truyền vào.
- Thread đang chờ bị interrupt.

Kết quả `true` nghĩa là client đã terminated; `false` nghĩa là hết thời gian chờ mà client chưa kết thúc. Nếu `Duration` bằng hoặc nhỏ hơn zero, phương thức chỉ kiểm tra trạng thái hiện tại mà không chờ.

### shutdownNow(): yêu cầu dừng khẩn cấp theo best effort

`shutdownNow()` cố gắng khởi tạo immediate shutdown. Implementation có thể thử interrupt các operation đang chạy, nhưng API không bảo đảm các operation đó sẽ kết thúc hoặc các thread đang đợi sẽ được thông báo. Vì vậy, không nên xem `shutdownNow()` là cách chắc chắn hủy mọi request tức thì.

Việc hủy một HTTP exchange có thể ảnh hưởng kết nối hoặc stream tùy HTTP/1.1 hay HTTP/2. Nếu cần hủy một request cụ thể, có thể dùng `CompletableFuture.cancel(true)` với future trả về từ `sendAsync`; đây cũng là nỗ lực hủy, không bảo đảm request chưa được gửi đến server hoặc server chưa bắt đầu xử lý.

## 4. close() và try-with-resources

Với một nhóm request hữu hạn, try-with-resources là cách đơn giản để bảo đảm client được đóng sau khi các request trong phạm vi đó hoàn tất:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpClientScope {
    public static void main(String[] args) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());

            System.out.println("Status: " + response.statusCode());
            System.out.println(response.body());
        }
        // close() được gọi khi rời khỏi khối try.
    }
}
```

`BodyHandlers.ofString()` đọc response body thành chuỗi trước khi `send()` trả response. Khi thoát khối try, không còn body stream nào từ ví dụ này đang chờ ứng dụng tiêu thụ.

Đối với client được chia sẻ bởi nhiều service hoặc component, hãy đặt vòng đời client ở phạm vi quản lý chung và gọi `close()` khi ứng dụng hoặc service dừng. Không đóng client ngay sau một request nếu các component khác còn cần sử dụng nó.

## 5. Request đã gửi qua sendAsync vẫn được chờ hoàn tất

`sendAsync()` trả về `CompletableFuture<HttpResponse<T>>` ngay để theo dõi request đang được xử lý bất đồng bộ. Nếu request đã được submit trước khi gọi `shutdown()` hoặc `close()`, client sẽ cố gắng cho request đó chạy đến hoàn tất theo orderly shutdown.

Ví dụ:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

try (HttpClient client = HttpClient.newHttpClient()) {
    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/"))
            .timeout(Duration.ofSeconds(15))
            .GET()
            .build();

    CompletableFuture<HttpResponse<String>> future = client.sendAsync(
            request, HttpResponse.BodyHandlers.ofString());

    // Rời khỏi khối try sẽ gọi close(). Request đã submit được chờ hoàn tất.
    HttpResponse<String> response = future.join();
    System.out.println(response.statusCode());
}
```

Trong ví dụ, `join()` chờ future hoàn tất trước khi rời khối try. `close()` sau đó thực hiện orderly shutdown và chờ các operation còn lại của client. Trong ứng dụng thực tế có thể có nhiều future; cần quản lý chúng để biết request nào đã submit và xử lý kết quả hoặc lỗi phù hợp.

Nếu không muốn chờ từng future theo cách tuần tự, có thể kết hợp nhiều future bằng `CompletableFuture.allOf(...)`, chờ nhóm công việc hoàn tất, rồi đóng client. Dù chọn cách nào, điều quan trọng là không submit request mới sau khi đã bắt đầu shutdown.

## 6. Response body streaming có thể làm close() chờ mãi

Đây là điểm cần chú ý nhất khi dùng `HttpClient.close()`. Một response có thể được trả về trước khi toàn bộ body được đọc, tùy `BodyHandler`.

Các body handler streaming phổ biến:

| Body handler | Kiểu body | Việc ứng dụng cần làm |
|---|---|---|
| `BodyHandlers.ofInputStream()` | `InputStream` | Đọc đến hết hoặc đóng stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | Tiêu thụ đến hết hoặc đóng stream |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Subscribe và yêu cầu dữ liệu, hoặc hủy subscription |
| Custom `BodySubscriber` | Do ứng dụng định nghĩa | Tiếp tục request data đến `onComplete`/`onError`, hoặc cancel subscription |

Nếu nhận `InputStream` nhưng không đọc hoặc đóng nó, request có thể vẫn mở. Tương tự, nếu subscriber không request thêm dữ liệu và cũng không cancel, việc chuyển body có thể bị dừng. Khi đó orderly shutdown có thể không hoàn tất và `close()` tiếp tục chờ.

### Đóng InputStream đúng cách

```java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;

try (HttpClient client = HttpClient.newHttpClient()) {
    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/archive.bin"))
            .GET()
            .build();

    HttpResponse<InputStream> response = client.send(
            request, HttpResponse.BodyHandlers.ofInputStream());

    try (InputStream body = response.body()) {
        Files.copy(body, Path.of("archive.bin"));
    }
}
```

`InputStream` được đóng trước khi client đóng. Nếu không cần lưu nội dung, có thể đọc đến hết và bỏ dữ liệu; nếu không muốn tiếp tục nhận body, hãy đóng stream để giải phóng tài nguyên.

### Đóng Stream<String> từ ofLines()

```java
HttpResponse<java.util.stream.Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (var lines = response.body()) {
    lines.forEach(System.out::println);
}
```

`Stream` ở đây gắn với response body và phải được đóng. Dùng try-with-resources bảo đảm đóng stream ngay cả khi xử lý một dòng phát sinh exception.

### Với ofPublisher() hoặc BodySubscriber tùy chỉnh

Với publisher, subscriber cần thực hiện flow control đúng cách: gọi `Subscription.request(n)` để nhận dữ liệu tiếp theo và tiếp tục cho đến khi nhận `onComplete` hoặc `onError`. Nếu không muốn nhận tiếp, gọi `Subscription.cancel()`. Custom `BodySubscriber` cũng cần request dữ liệu cho đến khi hoàn tất hoặc cancel subscription; nếu dừng giữa chừng mà không thực hiện một trong hai, shutdown có thể bị stall.

## 7. close() bị interrupt xử lý như thế nào?

`HttpClient.close()` không khai báo `throws InterruptedException`. Tuy vậy, quá trình chờ bên trong có thể bị interrupt.

Theo hợp đồng Java 21, nếu thread gọi `close()` bị interrupt trong lúc chờ, implementation có thể cố dừng các operation bằng cách gọi `shutdownNow()`. Sau đó, `close()` tiếp tục chờ cho đến khi các operation đang thực thi hoàn tất. Trước khi trả về, phương thức khôi phục interrupt status của thread gọi.

Điều này có nghĩa `close()` không phải API chờ có timeout. Ngay cả khi thread bị interrupt, nó vẫn có thể tiếp tục chờ các operation đang chạy kết thúc. Nếu ứng dụng cần một thời hạn chờ rõ ràng, hãy dùng `shutdown()` kết hợp `awaitTermination(Duration)` và quyết định bước tiếp theo khi hết thời gian.

## 8. Shutdown có thời hạn

Một quy trình dừng client có giới hạn thời gian có thể dùng `shutdown()` trước, đợi trong khoảng thời gian xác định, rồi thử `shutdownNow()` nếu chưa hoàn tất:

```java
import java.net.http.HttpClient;
import java.time.Duration;

static void stopClient(HttpClient client) {
    client.shutdown();

    try {
        boolean terminated = client.awaitTermination(Duration.ofSeconds(10));

        if (!terminated) {
            client.shutdownNow();

            boolean stopped = client.awaitTermination(Duration.ofSeconds(5));
            if (!stopped) {
                System.err.println("HttpClient still has active operations");
            }
        }
    } catch (InterruptedException ex) {
        client.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

Ví dụ minh họa chiến lược chờ có giới hạn. `shutdownNow()` chỉ là nỗ lực dừng; nếu `awaitTermination` vẫn trả `false`, ứng dụng phải ghi nhận rằng client còn operation chưa kết thúc và xử lý theo chính sách shutdown của hệ thống. Không được coi lời gọi `shutdownNow()` là bằng chứng mọi request đã bị hủy.

Nếu thread đang thực hiện `awaitTermination` bị interrupt, phương thức ném `InterruptedException` và xóa interrupt status theo quy tắc Java. Ví dụ khôi phục status bằng `Thread.currentThread().interrupt()` sau khi yêu cầu shutdown khẩn cấp.

## 9. Cancel một request khác với đóng toàn bộ client

`HttpClient.close()` quản lý vòng đời của cả client và các request đã submit. Nếu chỉ muốn hủy một request bất đồng bộ, có thể hủy future tương ứng:

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

// Khi không còn cần request này:
future.cancel(true);
```

Với implementation mặc định của JDK, future trả về từ `sendAsync` có thể hủy được. Gọi `cancel(true)` trên future chưa hoàn tất sẽ cố gắng hủy HTTP exchange và giải phóng tài nguyên sớm nhất có thể. Tuy nhiên, không có bảo đảm chính xác thời điểm hủy được áp dụng; request có thể đã được gửi và server có thể đã bắt đầu xử lý.

Với HTTP/1.1, việc hủy có thể khiến kết nối bên dưới bị đóng đột ngột. Với HTTP/2, stream có thể bị reset. Do đó, cancellation không thay thế idempotency, timeout hay cơ chế xử lý kết quả không chắc chắn ở tầng nghiệp vụ.

## 10. Default implementation và JDK built-in HttpClient

`HttpClient` là abstract class. Các client được tạo bằng `HttpClient.newHttpClient()` hoặc `HttpClient.newBuilder().build()` dùng implementation mặc định của JDK. Implementation này override `close`, `shutdown`, `shutdownNow`, `awaitTermination` và `isTerminated` để cung cấp hành vi best effort.

Các phương thức lifecycle có implementation mặc định trong abstract class với hành vi tối thiểu: `shutdown()` mặc định không làm gì, `shutdownNow()` mặc định gọi `shutdown()`, `awaitTermination()` mặc định trả `true` sau kiểm tra đối số, và `isTerminated()` mặc định trả `false`. Nếu tự xây dựng subclass của `HttpClient`, cần override các phương thức lifecycle để cung cấp hành vi đúng; không giả định implementation mặc định đã quản lý tài nguyên cho subclass.

## 11. Lựa chọn cách quản lý vòng đời

| Tình huống | Cách phù hợp |
|---|---|
| Một nhóm request hữu hạn, body được đọc đầy đủ | `try (HttpClient client = ...)` |
| Client dùng chung trong suốt vòng đời ứng dụng | Giữ client ở service/application scope; gọi `close()` khi shutdown |
| Muốn ngừng nhận request mới nhưng chờ request cũ | `shutdown()` rồi `awaitTermination(...)` |
| Cần chờ có giới hạn | `shutdown()` + `awaitTermination(Duration)` |
| Cần thử dừng khẩn cấp | `shutdownNow()`, hiểu rằng đây là best effort |
| Chỉ cần hủy một request bất đồng bộ | `CompletableFuture.cancel(true)` trên future của request |
| Dùng streaming response body | Đọc hết, đóng stream hoặc cancel subscription trước khi chờ client kết thúc |

## 12. Những lỗi thường gặp

- **Đóng client sau mỗi request trong khi client được chia sẻ:** các request sau không thể dùng client đã shutdown; đồng thời mất lợi ích tái sử dụng connection pool.
- **Nghĩ rằng `shutdown()` chờ request hoàn tất:** phương thức này chỉ khởi tạo orderly shutdown và trả về; dùng `awaitTermination` hoặc `close` để chờ.
- **Nghĩ `shutdownNow()` chắc chắn hủy mọi request:** API chỉ cam kết nỗ lực tốt nhất; operation có thể vẫn tiếp tục.
- **Không đóng `InputStream` từ `ofInputStream()`:** request có thể vẫn mở và làm orderly shutdown bị stall.
- **Không request hoặc cancel custom BodySubscriber:** body không được tiêu thụ và client không thể hoàn tất operation tương ứng.
- **Dùng `close()` khi cần deadline nghiêm ngặt:** `close()` không có timeout; dùng `shutdown()` và `awaitTermination(Duration)` nếu cần giới hạn thời gian chờ.
- **Nhầm cancellation với việc server chưa xử lý request:** hủy future không bảo đảm request chưa đến server hoặc chưa tạo side effect.

## 13. Tổng kết

Trong Java 21, `HttpClient` triển khai `AutoCloseable` và hỗ trợ quản lý vòng đời tường minh. `close()` khởi tạo orderly shutdown, từ chối request mới, chờ request đã gửi qua `send` hoặc `sendAsync` hoàn tất rồi chờ client terminated. `shutdown()` chỉ bắt đầu quá trình đó; `awaitTermination(Duration)` cho phép chờ có giới hạn; `shutdownNow()` cố gắng dừng operation nhưng không bảo đảm thành công.

Để shutdown hoàn tất, ứng dụng phải quản lý response body đúng cách. Body đã được đọc thành `String` thường không còn stream mở, nhưng `InputStream`, `Stream<String>`, publisher và custom subscriber cần được đọc đến hết, đóng hoặc cancel/request đúng giao thức. Hãy chọn phạm vi sống của client phù hợp với connection pooling, đóng client khi service thực sự kết thúc và dùng API chờ có giới hạn khi hệ thống cần deadline shutdown.

## Tài liệu tham khảo

- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html) — `close`, `shutdown`, `shutdownNow`, `awaitTermination`, `isTerminated`, request completion và implementation note về streaming bodies.
- [Java SE 21 API — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) — body handlers có buffer và streaming.
- [Java SE 21 API — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html) — subscriber, flow control và xử lý body.
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — completion và cancellation của future trả về từ `sendAsync`.
- [JEP 321: HTTP Client API](https://openjdk.org/jeps/321) — HTTP Client API chuẩn hóa trong Java 11; các phương thức quản lý vòng đời `HttpClient` được bổ sung sau đó trong Java 21.
