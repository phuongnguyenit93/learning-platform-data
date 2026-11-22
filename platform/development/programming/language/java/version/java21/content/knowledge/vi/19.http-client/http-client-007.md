# Timeout, interruption và hủy yêu cầu HTTP

Java 21 `HttpClient` cung cấp nhiều cơ chế để giới hạn thời gian chờ và dừng công việc HTTP. Cần phân biệt timeout khi thiết lập kết nối, timeout của từng request, interruption của thread gọi `send()` và cancellation của `CompletableFuture` trả về từ `sendAsync()`.

Các cơ chế này tác động ở những lớp khác nhau. Timeout giúp giới hạn thời gian client chờ; interruption báo cho thao tác đồng bộ rằng thread gọi đã bị ngắt; cancellation yêu cầu client dừng xử lý một exchange bất đồng bộ. Không cơ chế nào bảo đảm server chưa nhận hoặc chưa thực hiện request.

## 1. Bốn khái niệm cần phân biệt

| Cơ chế | Phạm vi | API thường dùng | Kết quả quan sát được |
|---|---|---|---|
| Connect timeout | Thiết lập kết nối mới đến server | `HttpClient.Builder.connectTimeout(Duration)` | `HttpConnectTimeoutException` nếu không kết nối kịp |
| Request timeout | Thời gian hoàn tất một request | `HttpRequest.Builder.timeout(Duration)` | `HttpTimeoutException` nếu request vượt thời hạn |
| Interruption | Thread đang thực hiện thao tác đồng bộ hoặc đang chờ | `HttpClient.send(...)`, `Future.get()` | `InterruptedException` tại thao tác interruptible |
| Cancellation | Một tác vụ HTTP bất đồng bộ | `CompletableFuture.cancel(...)` từ `sendAsync(...)` | Future chuyển sang trạng thái cancelled; `get()` ném `CancellationException` |

Timeout không đồng nghĩa cancellation do người gọi chủ động. Interruption của thread chờ một `CompletableFuture` cũng không tự động có nghĩa request HTTP nền đã bị hủy.

## 2. Connect timeout: giới hạn thời gian thiết lập kết nối

`HttpClient.Builder.connectTimeout(Duration)` cấu hình thời gian tối đa client chờ thiết lập một kết nối mới. Nếu không thiết lập, client không áp dụng connect timeout riêng.

```java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Connect timeout chỉ liên quan đến việc tạo kết nối mới. Nếu client có thể tái sử dụng một kết nối đã được thiết lập, connect timeout không được áp dụng cho request đó.

Khi không thiết lập kết nối trong thời hạn, thao tác có thể thất bại với `HttpConnectTimeoutException`. Lớp này kế thừa `HttpTimeoutException`, vì vậy có thể bắt riêng để phân biệt lỗi kết nối với timeout tổng quát của request.

## 3. Request timeout: giới hạn thời gian cho từng request

`HttpRequest.Builder.timeout(Duration)` đặt thời hạn cho một request cụ thể. Nếu request không hoàn tất trong thời hạn, client báo `HttpTimeoutException`.

```java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/orders/42"))
        .timeout(Duration.ofSeconds(8))
        .GET()
        .build();
```

Request timeout thuộc về `HttpRequest`, nên mỗi request có thể đặt một thời hạn phù hợp với nghiệp vụ. Nếu không gọi `timeout(...)`, request không có timeout riêng và có thể chờ vô thời hạn.

Thời hạn phải là một `Duration` dương; giá trị không hợp lệ sẽ bị từ chối khi xây dựng request. Không dùng timeout rất ngắn chỉ để che giấu một dịch vụ chậm hoặc cấu hình kết nối sai.

## 4. Kết hợp connect timeout và request timeout

Connect timeout và request timeout giải quyết hai giới hạn khác nhau. Có thể cấu hình cả hai trên cùng một client/request:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/products"))
        .timeout(Duration.ofSeconds(7))
        .GET()
        .build();
```

Trong ví dụ, client giới hạn thời gian tạo kết nối mới ở 2 giây; request có thời hạn 7 giây cho toàn bộ quá trình xử lý request theo hợp đồng của `HttpRequest.timeout`. Connect timeout không phải một khoảng thời gian được cộng thêm vào request timeout.

`HttpClient` có thể được tái sử dụng cho nhiều request. Connect timeout là cấu hình của client; request timeout được đặt riêng cho từng request. Hãy chọn giá trị theo SLA, độ trễ mạng, kích thước response và thời gian xử lý mà ứng dụng chấp nhận.

## 5. Xử lý timeout khi gọi send() đồng bộ

`HttpClient.send(request, bodyHandler)` thực hiện request đồng bộ. Thread gọi chờ cho đến khi response được xử lý theo `BodyHandler`, hoặc thao tác thất bại.

```java
import java.io.IOException;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;

static HttpResponse<String> fetch(
        HttpClient client, HttpRequest request)
        throws IOException {
    try {
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    } catch (HttpConnectTimeoutException e) {
        throw new IOException("Could not connect to the HTTP server in time", e);
    } catch (HttpTimeoutException e) {
        throw new IOException("HTTP request exceeded its timeout", e);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IOException("HTTP request was interrupted", e);
    }
}
```

`HttpConnectTimeoutException` được bắt trước `HttpTimeoutException` vì nó là lớp con. `InterruptedException` biểu thị thread gọi bị interrupt trong khi chờ thao tác đồng bộ; nếu không truyền exception lên tầng gọi mà chuyển thành lỗi khác, hãy khôi phục interrupt status bằng `Thread.currentThread().interrupt()`.

Khi `send()` bị interrupt, thao tác gửi request bị hủy ở phía client theo hợp đồng của API. Tuy nhiên, nếu request đã được gửi đến server, server vẫn có thể đã nhận hoặc đang xử lý nó.

## 6. Dùng sendAsync() và xử lý lỗi bất đồng bộ

`HttpClient.sendAsync()` trả về `CompletableFuture<HttpResponse<T>>`. Caller có thể tiếp tục công việc khác và xử lý response hoặc exception khi future hoàn tất.

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.concurrent.CompletableFuture;

CompletableFuture<HttpResponse<String>> responseFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

responseFuture.whenComplete((response, error) -> {
    if (error != null) {
        System.err.println("HTTP exchange failed: " + error);
        return;
    }

    System.out.println("HTTP status: " + response.statusCode());
});
```

Khi request có `timeout(...)`, future hoàn tất bất thường nếu request vượt thời hạn. Với `whenComplete`, lỗi có thể xuất hiện dưới dạng `CompletionException` bao quanh nguyên nhân; cần kiểm tra cause để nhận diện `HttpTimeoutException` hoặc `HttpConnectTimeoutException`.

Ví dụ chờ kết quả bằng `get()` và phân loại lỗi:

```java
import java.net.http.HttpTimeoutException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

try {
    HttpResponse<String> response = responseFuture.get();
    System.out.println(response.statusCode());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting for HTTP response was interrupted", e);
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    if (cause instanceof HttpTimeoutException timeout) {
        throw new IllegalStateException("HTTP request timed out", timeout);
    }
    throw new IllegalStateException("HTTP request failed", cause);
}
```

`Future.get()` có thể bị interrupt khi thread gọi đang chờ. Khi đó `get()` ném `InterruptedException`; việc ngừng chờ không tự động hủy `responseFuture` hoặc request HTTP. Nếu muốn yêu cầu hủy exchange, cần gọi `cancel(...)` trên future một cách tường minh.

## 7. Hủy request bất đồng bộ bằng cancel()

Future do `sendAsync()` trả về có thể được hủy bằng `cancel(boolean mayInterruptIfRunning)`:

```java
CompletableFuture<HttpResponse<String>> responseFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

// Khi nghiệp vụ không còn cần response:
boolean accepted = responseFuture.cancel(true);
System.out.println("Cancellation accepted: " + accepted);
```

Khi cancellation được chấp nhận, future chuyển sang trạng thái cancelled. Những thao tác chờ kết quả bằng `get()` sẽ ném `CancellationException`; các stage phụ thuộc có thể hoàn tất theo quy tắc của `CompletableFuture`.

Đối với `HttpClient`, cancellation yêu cầu client hủy xử lý request đang diễn ra, nhưng việc hủy có thể không tức thì. Request có thể đã được gửi hoặc server đã bắt đầu xử lý trước khi client nhận yêu cầu hủy. Tham số `mayInterruptIfRunning` không phải cam kết rằng server bị interrupt hoặc công việc phía server dừng lại.

Không dùng `cancel(true)` như một cơ chế rollback nghiệp vụ. Nếu request có thể tạo tác dụng phụ, server cần có cơ chế idempotency, kiểm tra trạng thái hoặc API hủy nghiệp vụ riêng.

## 8. Phân biệt timeout, interruption và cancellation

| Tình huống | Điều xảy ra | Điều cần làm |
|---|---|---|
| Kết nối mới không thiết lập kịp | `HttpConnectTimeoutException` | Kiểm tra DNS, mạng, endpoint và connect timeout |
| Request vượt thời hạn | `HttpTimeoutException` | Đánh giá SLA, server latency và request timeout |
| Thread gọi `send()` bị interrupt | `InterruptedException`; thao tác đồng bộ bị hủy ở phía client | Truyền tiếp hoặc khôi phục interrupt status |
| Thread gọi `responseFuture.get()` bị interrupt | `get()` ngừng chờ và ném `InterruptedException` | Quyết định riêng có cần `responseFuture.cancel(...)` hay không |
| Caller gọi `responseFuture.cancel(...)` | Future chuyển sang trạng thái cancelled nếu yêu cầu được chấp nhận | Xử lý `CancellationException`; không giả định server đã dừng |

Timeout là giới hạn thời gian do request/client cấu hình. Interruption là tín hiệu dành cho thread. Cancellation là thay đổi trạng thái future và yêu cầu dừng exchange phía client. Chúng có thể xuất hiện gần nhau nhưng không thay thế lẫn nhau.

## 9. Timeout và retry: tránh gửi lặp tác vụ có tác dụng phụ

Khi timeout xảy ra, client có thể không biết server đã nhận request hay chưa. Ví dụ, client gửi lệnh tạo đơn hàng, server xử lý thành công nhưng response bị chậm hoặc thất lạc. Client nhận timeout rồi gửi lại có thể tạo hai đơn hàng.

Trước khi retry, cần xem xét:

- Request có idempotent theo hợp đồng HTTP và nghiệp vụ hay không.
- Server có hỗ trợ idempotency key hoặc request identifier để nhận diện lần gửi lặp hay không.
- Lỗi là timeout kết nối, timeout response, lỗi tạm thời hay lỗi nghiệp vụ không thể retry.
- Số lần retry, exponential backoff, jitter và tổng deadline của toàn bộ operation.
- Body của request có thể gửi lại an toàn hay không; publisher hoặc stream có thể không tái sử dụng được.

Với thao tác ghi dữ liệu, hãy thiết kế idempotency ở phía server trước khi tự động retry. Không retry vô hạn và không cộng dồn timeout mỗi lần thử mà vượt quá deadline nghiệp vụ.

## 10. Thiết kế deadline theo nghiệp vụ

Một request HTTP thường nằm trong một operation lớn hơn gồm nhiều bước: lấy token, gọi một hoặc nhiều endpoint, chuyển đổi dữ liệu và ghi kết quả. Nếu mỗi bước có timeout độc lập quá dài, tổng thời gian có thể vượt SLA của request bên ngoài.

Hãy xác định deadline tổng ở tầng nghiệp vụ, sau đó phân bổ thời gian còn lại cho từng lời gọi HTTP. Mỗi `HttpRequest` có thể được tạo với timeout tương ứng. Khi deadline đã hết, không tiếp tục gửi các request không còn giá trị; nếu request đang chạy bất đồng bộ, cân nhắc hủy future và xử lý khả năng server đã nhận request.

Không đặt một timeout duy nhất cho mọi endpoint. API nội bộ nhanh, dịch vụ bên ngoài, upload lớn và tải báo cáo có đặc tính khác nhau; timeout cần dựa trên dữ liệu vận hành và yêu cầu sản phẩm.

## 11. Lưu ý khi dùng virtual thread

`HttpClient.send()` là API đồng bộ và có thể dùng từ virtual thread. Khi thread phải chờ thao tác blocking được hỗ trợ, JVM có thể unmount virtual thread khỏi carrier; không cần chuyển sang `sendAsync()` chỉ vì ứng dụng đang dùng virtual thread.

`sendAsync()` hữu ích khi ứng dụng muốn ghép nhiều thao tác bằng `CompletableFuture`, xây dựng pipeline bất đồng bộ hoặc tránh giữ luồng gọi chờ kết quả. Chọn đồng bộ hay bất đồng bộ theo cấu trúc ứng dụng, cách xử lý lỗi và cách quản lý vòng đời công việc.

Không dùng số lượng virtual thread để giới hạn số request đến dịch vụ ngoài. Nếu cần giới hạn concurrency hoặc quota, dùng semaphore, rate limiter hoặc cơ chế điều tiết phù hợp; timeout và cancellation không thay thế giới hạn tải.

## 12. Các nguyên tắc triển khai

1. Dùng `connectTimeout` để giới hạn việc thiết lập kết nối mới.
2. Dùng `HttpRequest.timeout` để đặt thời hạn cho từng request.
3. Phân loại `HttpConnectTimeoutException` trước `HttpTimeoutException` nếu cần thông báo khác nhau.
4. Với `send()`, xử lý `InterruptedException` đúng cách và không nuốt interrupt.
5. Với `sendAsync()`, phân biệt lỗi hoàn tất future, interruption của thread chờ và cancellation tường minh.
6. Không cho rằng timeout hoặc cancellation có thể thu hồi tác dụng phụ đã xảy ra trên server.
7. Chỉ retry khi request và nghiệp vụ cho phép; dùng idempotency key cho thao tác ghi cần bảo vệ khỏi gửi lặp.
8. Thiết kế timeout theo deadline/SLA và đo đạc latency thực tế.

## 13. Biên dịch với Java 21

`HttpClient`, `HttpRequest`, `HttpResponse`, `HttpTimeoutException` và `CompletableFuture` là API đã hoàn thiện trong Java 21. Các ví dụ không yêu cầu bật Preview.

```bash
javac --release 21 -d out src/HttpTimeoutDemo.java
java -cp out HttpTimeoutDemo
```

Đặt compiler release hoặc toolchain về Java 21 để xác nhận cú pháp và API mục tiêu. Runtime thực tế vẫn do lệnh `java` hoặc cấu hình triển khai quyết định.

## 14. Tài liệu tham khảo

- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API — HttpClient.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 21 API — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 21 API — HttpTimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpTimeoutException.html)
- [Java SE 21 API — HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html)
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
