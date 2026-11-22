# HTTP bất đồng bộ trong Java: handle, exceptionally và tìm lỗi gốc sau CompletionException

## 1. Bối cảnh: gửi HTTP bất đồng bộ, lỗi xuất hiện ở đâu?

Java 17 cung cấp `java.net.http.HttpClient.sendAsync(...)` trả về `CompletableFuture<HttpResponse<T>>`. Sau khi gọi `sendAsync`, thread gọi có thể tiếp tục làm việc; đến khi kết quả HTTP, body và handler tương ứng hoàn tất, future mới hoàn thành bình thường hoặc thất bại. Bạn có thể ghép các bước `thenApply`, `thenCompose`, `handle`, `exceptionally`, `whenComplete` để giải mã, kiểm tra status, lấy fallback và báo lỗi.

Một bài toán điển hình: ứng dụng gọi API để lấy dữ liệu. Nếu server phản hồi hợp lệ, dùng body; nếu server tạm thời trả **HTTP 503**, có thể chọn bản cache hoặc thông báo “thử lại sau”; nếu có **TLS/certificate error**, không nên che giấu như lỗi 503; nếu người dùng **hủy tác vụ**, không được tự làm nó “thành công” bằng fallback.

~~~text
HttpClient.sendAsync(...)
         |
         v
CompletableFuture<HttpResponse<String>>
         |
         | HTTP 200/404/503 đều có thể là kết quả HTTP bình thường
         v
thenApply(response -> kiểm tra status và body)
         |
         +---- bình thường ---> thenApply / handle / whenComplete ---> body
         |
         +---- exceptional --> handle / exceptionally / whenComplete
                                      |
                                      +-- recovery có chủ đích ---> fallback value
                                      |
                                      +-- không thể recover ------> exceptional future

Ở ranh giới đợi kết quả:
    future.join() -> CompletionException thường bọc nguyên nhân
    future.get()  -> ExecutionException thường bọc nguyên nhân
    cancel        -> CancellationException có thể xuất hiện trực tiếp
~~~

**Mục tiêu:** nắm chính xác khi nào `handle` và `exceptionally` chạy, chọn recovery hay chỉ quan sát bằng `whenComplete`, hiểu `CompletionException`/`ExecutionException`, tìm **lỗi gốc** để phân loại HTTP/network/timeout/cancellation, tránh nuốt lỗi và không tự động retry request có side effects. Bài này đặt trong ngữ cảnh **HTTP bất đồng bộ** và sử dụng **Java 17+**.

## 2. Một CompletableFuture có những trạng thái gì?

`CompletableFuture<T>` đại diện cho **kết quả T có thể đến trong tương lai**. Nó có thể:

1. **Hoàn thành bình thường:** mang giá trị T, kể cả `null` nếu contract cho phép.
2. **Hoàn thành đặc biệt (exceptionally completed):** mang một nguyên nhân lỗi để các stage phụ thuộc xử lý; các stage thành công-only thường không chạy.
3. **Bị hủy:** `cancel(...)` khiến future hoàn tất với `CancellationException` theo cơ chế CompletableFuture. Các stage phụ thuộc cũng có thể hoàn tất đặc biệt, có thể nhìn thấy wrapper.

Ví dụ:

~~~java
CompletableFuture<String> good =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> bad =
        CompletableFuture.failedFuture(
                new IllegalStateException("service failed"));
~~~

Đây là đoạn minh họa cần import `java.util.concurrent.CompletableFuture`; API `failedFuture` có từ Java 9. `good.join()` trả `"OK"`; `bad.join()` ném lỗi theo quy tắc wrapping của `join`. Lúc này **không có HTTP request nào** — chỉ minh họa trạng thái.

### 2.1. Lỗi ở upstream ảnh hưởng những stage nào?

~~~java
CompletableFuture<String> future =
        CompletableFuture.<String>failedFuture(
                        new IllegalArgumentException("bad input"))
                .thenApply(s -> s.toUpperCase());
~~~

`thenApply` **không chạy** vì upstream không có giá trị thành công. Future mới vẫn exceptional. Đây là khác biệt với `handle` và `exceptionally`: hai API đó có thể biến đường lỗi thành giá trị mới.

Nếu trong `thenApply` bạn tự ném `RuntimeException`, stage được trả về sẽ hoàn thành **exceptionally**, dù upstream `sendAsync` đã nhận HTTP response thành công. Vì vậy **nguồn lỗi** có thể là network, body handler, logic status-check, parser JSON, mapper, hoặc recovery handler — không chỉ từ máy chủ.

### 2.2. HTTP 404/500/503 không tự động là exceptional completion

Khi `HttpClient` nhận một phản hồi HTTP hoàn chỉnh, ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: text/plain

maintenance
~~~

`sendAsync(request, BodyHandlers.ofString())` thông thường vẫn **hoàn thành bình thường** với `HttpResponse<String>` có `statusCode()==503`. Đây là **HTTP application response**, không phải Java exception do mạng.

Vì vậy:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .exceptionally(error -> {
          // KHÔNG tự chạy chỉ vì server trả HTTP 503.
          return fallbackResponse;
      });
~~~

đoạn này không phải cách tổng quát để bắt status 503. Để xử lý 4xx/5xx như **exceptional branch**, bạn cần chuyển một status không chấp nhận thành ngoại lệ có kiểu hoặc dùng `handle` để kiểm tra response lẫn error:

~~~java
CompletableFuture<String> checked =
        client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString())
              .thenApply(response -> {
                  if (response.statusCode() >= 400) {
                      throw new HttpStatusException(response.statusCode());
                  }
                  return response.body();
              });
~~~

Đây là **mã minh họa**; `HttpStatusException` là class tự định nghĩa, sẽ có trong chương trình chạy được ở mục 8. Quy tắc “status >=400 là thất bại” chỉ là policy ví dụ; thực tế có thể xem 404 là hợp lệ cho một nghiệp vụ tra cứu, hoặc cần xử lý riêng 429/503/409.

## 3. `handle`: xử lý cả thành công và thất bại

### 3.1. Ý nghĩa và kiểu trả về

Phương thức `CompletionStage.handle(BiFunction<T, Throwable, U>)` tạo một stage mới kiểu `U`. Hàm được gọi khi upstream hoàn tất, **bất kể thành công hay thất bại**:

- Bình thường: `value` có giá trị kết quả; `error` thường là `null`.
- Thất bại: `error` là `Throwable` mô tả lỗi; `value` thường là `null`.
- Hàm `handle` có thể trả giá trị fallback hoặc biến đổi kết quả; stage mới sẽ **hoàn thành bình thường** với giá trị trả về.
- Nếu chính hàm `handle` ném lỗi, stage mới hoàn thành đặc biệt bằng lỗi đó.

Mẫu an toàn khi có policy fallback:

~~~java
CompletableFuture<String> safe =
        checkedGet(client, uri)
                .handle((body, error) -> {
                    if (error == null) {
                        return body;
                    }
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return "cached-copy";
                    }
                    throw new CompletionException(cause);
                });
~~~

Đây là đoạn minh họa nằm trong một lớp có `checkedGet`, `root` và `HttpStatusException` được định nghĩa ở mục 8. Điểm mấu chốt: **chỉ recover lỗi được phép**, không biến mọi loại lỗi thành “cached-copy”. Trong API thật, fallback có thể chứa metadata `stale` để downstream không nhầm dữ liệu mới với dữ liệu cũ.

### 3.2. `handle` có thể đổi kiểu dữ liệu

Giả sử upstream là `CompletableFuture<HttpResponse<String>>`, bạn có thể dùng `handle` để trả một DTO có thông tin outcome:

~~~java
record ApiResult(boolean ok, int status, String body, String errorType) {}

CompletableFuture<ApiResult> result =
        rawHttpFuture.handle((response, error) -> {
            if (error != null) {
                Throwable cause = root(error);
                return new ApiResult(
                        false, -1, "", cause.getClass().getSimpleName());
            }
            return new ApiResult(
                    response.statusCode() < 400,
                    response.statusCode(),
                    response.body(),
                    "");
        });
~~~

Đây là đoạn code minh họa trong class có `rawHttpFuture` và `root`; không phải file standalone. `handle` có thể đổi từ `HttpResponse<String>` sang `ApiResult` — ngược lại `exceptionally` phải trả một giá trị tương thích với kiểu upstream.

**Cẩn thận:** trong ví dụ `ApiResult`, lỗi được **biến thành dữ liệu** (normal completion). Điều đó phù hợp nếu API công khai trả một result object kiểu “thành công/thất bại”, nhưng các stage `exceptionally` phía sau **sẽ không thấy lỗi cũ**. Nếu vẫn muốn luồng exception, phải rethrow hoặc biểu diễn trạng thái thất bại thật rõ trong DTO.

### 3.3. Những lỗi phổ biến với `handle`

~~~java
// RỦI RO: biến mọi lỗi thành chuỗi rỗng.
.handle((body, error) -> error != null ? "" : body)

// RỦI RO: không kiểm tra error trước khi dùng body.
.handle((body, error) -> body.length())

// RỦI RO: trả null khi có lỗi nhưng downstream tưởng có String.
.handle((body, error) -> error == null ? body : null)
~~~

Với trường hợp đầu tiên, lỗi xác thực TLS hoặc người dùng hủy tác vụ có thể bị ngụy trang thành response rỗng. Trường hợp thứ hai có thể tạo thêm `NullPointerException`, làm mất khả năng nhìn thấy lỗi ban đầu. Trường hợp thứ ba biến thất bại thành **thành công với null**, khiến downstream dễ lỗi trễ hơn.

## 4. `exceptionally`: chỉ can thiệp khi upstream thất bại

`CompletionStage.exceptionally(Function<Throwable, ? extends T>)` hoạt động như đường recovery:

- Upstream **thành công**: callback không chạy; giá trị thành công được chuyển tiếp.
- Upstream **thất bại**: callback nhận lỗi, được quyền trả **giá trị fallback T** để hoàn thành bình thường.
- Nếu callback ném exception: stage sau đó tiếp tục thất bại.

Ví dụ:

~~~java
CompletableFuture<String> text =
        checkedGet(client, uri)
                .exceptionally(error -> {
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return "retry-later";
                    }
                    throw new CompletionException(cause);
                });
~~~

Mã minh họa dùng helper từ mục 8. Khi HTTP thành công với body `"ready"`, callback `exceptionally` không chạy, và kết quả vẫn là `"ready"`. Nếu stage trước đã biến HTTP 503 thành `HttpStatusException`, callback chọn fallback `"retry-later"`.

### 4.1. `exceptionally` không phải `catch` tự động cho status HTTP

Đây là quy tắc quan trọng cần nhắc lại: `sendAsync` nhận **response 503 hợp lệ về mặt HTTP** thì future gốc thường **không exceptional**. Muốn `exceptionally` xử lý HTTP status, trước tiên cần stage `thenApply`/`thenCompose` phân loại status và tạo lỗi theo contract của ứng dụng.

Một implementation khác có thể không cần ném ngoại lệ cho status, ví dụ:

~~~java
CompletableFuture<String> result =
        client.sendAsync(request,
                        HttpResponse.BodyHandlers.ofString())
              .thenApply(response ->
                      response.statusCode() == 404
                              ? "not-found"
                              : response.body());
~~~

Đây là cách xử lý **404 là kết quả nghiệp vụ** nếu API thiết kế như vậy. Nhưng đoạn minh họa chưa xử lý các 500/503 khác — tùy protocol phải bổ sung policy. Không có luật Java rằng **mọi HTTP >=400 phải là Throwable**.

### 4.2. Khi nào nên dùng `exceptionally` thay `handle`?

Dùng `exceptionally` khi bạn **muốn giữ nguyên đường thành công** và chỉ thay thế **một số lỗi**. Dùng `handle` khi cần **nhìn cả value và error**, chuẩn hóa thành một kiểu result khác, hoặc thực hiện transformation tùy cả hai trạng thái.

So sánh:

| Tình huống | `handle` | `exceptionally` |
| --- | --- | --- |
| Chạy khi upstream thành công | Có | Không |
| Chạy khi upstream thất bại | Có | Có |
| Đầu vào callback | `(T value, Throwable error)` | `(Throwable error)` |
| Kiểu đầu ra | `U`, có thể đổi kiểu | `T`, tương thích upstream |
| Return fallback khi lỗi | Có | Có |
| Cho lỗi lan tiếp | Ném exception | Ném exception |
| Dùng để chỉ ghi log mà giữ nguyên kết quả | Có thể nhưng không phải lựa chọn tối ưu | Chỉ thấy lỗi, dễ vô ý recover |
| Phù hợp quan sát cả hai đường không đổi dữ liệu | Thường dùng `whenComplete` | Không |

### 4.3. Recovery không biến HTTP request thành idempotent

Nếu một `POST` đã gửi tới server, kết nối đứt trước khi nhận response, `exceptionally` có thể thấy `IOException`. **Không suy ra server chưa xử lý POST**. Tự gọi gửi lại ngay trong callback mà không có idempotency key có thể tạo hai giao dịch. Recovery bằng cách trả dữ liệu cached/local khác với retry cùng một request side effect; cần chính sách riêng.

## 5. `whenComplete`: quan sát hai đường nhưng không thay thế kết quả

`whenComplete(BiConsumer<T, Throwable>)` nhận cả `value` và `error` như `handle`, nhưng **không có giá trị trả về để làm fallback**. Nó phù hợp logging, metrics, trace cleanup:

~~~java
CompletableFuture<String> observed =
        checkedGet(client, uri)
                .whenComplete((body, error) -> {
                    if (error == null) {
                        metricsRecordSuccess();
                    } else {
                        metricsRecordFailure(root(error));
                    }
                });
~~~

Đây là pseudocode trong app có `metricsRecordSuccess`/`metricsRecordFailure`. Nếu callback `whenComplete` chạy bình thường, stage mới phản ánh **cùng kết quả thành công hoặc thất bại của upstream**. Nếu callback tự ném khi upstream đang thành công, stage mới có thể chuyển thành lỗi của callback. Nếu upstream vốn thất bại và callback cũng ném, đặc tả ưu tiên chuyển tiếp **lỗi upstream** cho dependent stage; nhưng vẫn nên bảo đảm logging/metrics không ném để tránh rối nguồn lỗi.

So sánh:

~~~text
1) thenApply:      chỉ chạy khi có value thành công, có thể đổi value.
2) handle:         chạy cả success/failure, có thể đổi sang value U, recover.
3) exceptionally:  chỉ chạy failure, có thể recover sang value T.
4) whenComplete:   chạy cả success/failure để quan sát, KHÔNG recover.
~~~

**Đừng dùng `whenComplete` để “nuốt” exception**:

~~~java
// SAI kỳ vọng: chỉ log và return bình thường thì lỗi sẽ biến mất.
checkedGet(client, uri)
        .whenComplete((body, error) -> {
            if (error != null) System.err.println(error);
        });
// Future trả về vẫn exceptional nếu upstream exceptional.
~~~

Nếu muốn xử lý sau bước quan sát, bạn có thể ghép:

~~~java
CompletableFuture<String> result =
        checkedGet(client, uri)
                .whenComplete((body, error) -> logOutcome(body, error))
                .exceptionally(error -> chooseFallback(root(error)));
~~~

Đoạn minh họa dùng hai hàm ứng dụng giả định. Logging ở `whenComplete`, recovery ở `exceptionally`; nên cẩn thận việc `chooseFallback` không vô tình che giấu lỗi quan trọng.

## 6. CompletionException là gì? Vì sao cần tìm lỗi gốc?

`CompletionException` thuộc `java.util.concurrent` là **unchecked wrapper** thường xuất hiện khi một stage hoàn thành đặc biệt hoặc khi gọi `CompletableFuture.join()`. Nó không tự nói được HTTP endpoint bị lỗi gì. Nguyên nhân đáng phân tích thường nằm ở `getCause()`, ví dụ:

~~~text
CompletionException
  └─ HttpStatusException("HTTP 503")     <-- app tự ném sau status-check

CompletionException
  └─ HttpTimeoutException                 <-- request vượt timeout

CompletionException
  └─ ConnectException                     <-- không kết nối được

CompletionException
  └─ SSLHandshakeException                <-- TLS handshake lỗi

ExecutionException
  └─ CompletionException?
       └─ IllegalStateException          <-- mapper/logic lỗi
~~~

Đây là **các ví dụ chuỗi nguyên nhân có thể gặp**, không phải cam kết tất cả provider/JDK đều bọc lỗi đúng một cấp như sơ đồ. Một số lỗi mạng có thêm wrappers/cause/suppressed exceptions; không nên code dựa vào đúng số lớp `CompletionException`.

### 6.1. `join()` và `get()` khác nhau

| API | Khi thành công | Khi thất bại |
| --- | --- | --- |
| `future.join()` | Trả T; không bắt khai báo checked exception | Thường ném `CompletionException` (unchecked) chứa nguyên nhân |
| `future.get()` | Trả T; có thể chờ | Ném `ExecutionException` (checked) chứa nguyên nhân; `InterruptedException` khi bị interrupt |
| `future.get(timeout, unit)` | Trả T nếu kịp | Thêm `TimeoutException` (checked) nếu chờ quá hạn |
| `future.cancel(true)` | Hoàn thành cancellation nếu thành công | `join()/get()` trên future bị cancel trực tiếp có thể ném `CancellationException` |

**Cẩn thận:** `get(timeout)` hết thời gian chờ có thể **chỉ là chờ chưa xong**, không tự chứng minh request HTTP đã bị hủy. `join()` cũng **không tự có timeout**. Muốn request có deadline, dùng `HttpRequest.Builder.timeout`, hoặc quản lý timeout của CompletableFuture có hiểu biết về việc underlying I/O có còn đang chạy.

### 6.2. Helper unwrap chỉ bỏ các wrapper cơ chế async

Một cách thực dụng:

~~~java
static Throwable root(Throwable problem) {
    while ((problem instanceof CompletionException
            || problem instanceof ExecutionException)
            && problem.getCause() != null) {
        problem = problem.getCause();
    }
    return problem;
}
~~~

Đoạn này cần import `java.util.concurrent.CompletionException` và `ExecutionException`. Nó **chỉ bóc các wrapper async đã biết**, dừng tại nguyên nhân đầu tiên không phải hai wrapper đó. Đây là chiến lược ưu tiên **giữ lỗi có ý nghĩa**: một `IOException` hoặc `HttpStatusException` bên trong có thể có message/cause/suppressed quan trọng, không nên xóa chúng.

Không có nghĩa mọi Throwable cần lột đến `getCause()==null`. Một ngoại lệ nghiệp vụ có thể bọc một lỗi kỹ thuật nhưng bản thân nó chính là ngữ nghĩa mà caller cần xử lý. Ví dụ `PaymentRejectedException(cause=IOException)` thì “lỗi gốc kỹ thuật” không tự quan trọng hơn lỗi từ chối thanh toán khi quyết định policy.

**Đừng viết vòng `while (error.getCause() != null) error = error.getCause()` không kiểm soát** để ra quyết định recovery: nó có thể làm mất context, sai phân loại và có nguy cơ vòng lặp trong những Throwable tùy biến bất thường. Nếu cần root kỹ thuật sâu hơn, làm việc đó ở logging/diagnostics với chống vòng và giữ exception gốc.

### 6.3. Đừng bỏ stack trace và suppressed exceptions khi unwrap

Một helper trả `Throwable` để phân loại **không nên vứt wrapper gốc khỏi log**. Bạn có thể log cả:

- **operation/request ID**, phương thức, endpoint đã lọc thông tin nhạy cảm, elapsed time;
- **wrapper** mà stage nhận và **unwrapped cause**;
- **full stack trace** và `suppressed`, nguyên nhân exception chain;
- trạng thái HTTP nếu server thực sự có response;
- policy recovery/retry decision.

Không log Authorization header, cookie, bearer token, body nhạy cảm hoặc query string chứa secret. `cause.getMessage()` cũng có thể chứa URL hoặc thông tin hạ tầng; lọc/redact khi xuất sang hệ quan sát.

## 7. Tự tạo HttpStatusException để tách HTTP status khỏi network exception

Vì HTTP 503 là response bình thường ở tầng client, muốn mô hình `exceptionally` xử lý cần một **bước validate status**:

~~~java
static final class HttpStatusException extends RuntimeException {
    final int status;

    HttpStatusException(int status) {
        super("HTTP " + status);
        this.status = status;
    }
}

static CompletableFuture<String> checkedGet(
        HttpClient client, URI uri) {

    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
            .thenApply(response -> {
                if (response.statusCode() >= 400) {
                    throw new HttpStatusException(response.statusCode());
                }
                return response.body();
            });
}
~~~

Đây là **các phương thức trong ngữ cảnh một class**, không phải file độc lập. Chương trình đầy đủ ở mục 8 dùng chính thiết kế này. Nếu `sendAsync` hoàn tất HTTP 503, `thenApply` chạy, phát hiện status, ném `HttpStatusException`, khiến **stage mới** trở nên exceptional. Một `exceptionally` gắn vào **stage mới** sẽ nhìn được lỗi; nhưng gắn trực tiếp vào future HTTP gốc sẽ **không chạy vì 503**, do đó phân biệt vị trí móc stage rất quan trọng.

Việc biến 4xx/5xx thành exception là **quy ước ứng dụng**. Có hệ thống không muốn ném exception cho 404 mà trả `Optional.empty()`; có hệ thống parse JSON error body để tạo typed error. Hãy chọn policy nhất quán, giới hạn body lỗi và tránh phát tán dữ liệu nhạy cảm.

## 8. Ví dụ Java 17+ hoàn chỉnh: HTTP 503, handle, exceptionally, join/get và cancel

Chương trình sử dụng **HTTP server trong JDK** (`com.sun.net.httpserver.HttpServer`) chạy trên loopback IPv4 `127.0.0.1` với cổng ngẫu nhiên và hai endpoint:

- `GET /ok` trả `200 OK`, body `ready`.
- `GET /busy` trả `503 Service Unavailable`, body `unavailable`.

Client `HttpClient.sendAsync` gửi GET và xây các stage theo những hướng khác nhau. Server loopback giúp bài kiểm thử **không phụ thuộc Internet** và cho kết quả đầu ra ổn định. Ví dụ này chỉ mô phỏng **HTTP status 503** và hủy future thủ công; nó **không mô phỏng mất mạng, TLS lỗi hay retry production**.

Lưu nội dung sau vào file **HttpFailureStagesDemo.java**:

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
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class HttpFailureStagesDemo {
    static final class HttpStatusException extends RuntimeException {
        final int status;

        HttpStatusException(int status) {
            super("HTTP " + status);
            this.status = status;
        }
    }

    static Throwable root(Throwable problem) {
        while ((problem instanceof CompletionException
                || problem instanceof ExecutionException)
                && problem.getCause() != null) {
            problem = problem.getCause();
        }
        return problem;
    }

    static void send(HttpExchange exchange, int status, String body)
            throws IOException {
        try (exchange) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    static CompletableFuture<String> checkedGet(
            HttpClient client, URI uri) {

        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        return client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8))
                .thenApply(response -> {
                    if (response.statusCode() >= 400) {
                        throw new HttpStatusException(response.statusCode());
                    }
                    return response.body();
                });
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/ok",
                e -> send(e, 200, "ready"));
        server.createContext("/busy",
                e -> send(e, 503, "unavailable"));
        server.start();

        try {
            URI base = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newHttpClient();

            // HTTP status 503 vẫn là response bình thường.
            HttpRequest request = HttpRequest.newBuilder(
                    base.resolve("busy")).GET().build();
            int rawCode = client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString())
                    .join().statusCode();
            System.out.println("Raw HTTP status: " + rawCode);

            String success = checkedGet(client, base.resolve("ok"))
                    .handle((body, failure) ->
                            failure == null ? body : "unexpected")
                    .join();
            System.out.println("handle success: " + success);

            String recovered = checkedGet(
                    client, base.resolve("busy"))
                    .handle((body, failure) -> {
                        if (failure == null) return body;
                        Throwable underlying = root(failure);
                        if (underlying instanceof HttpStatusException status
                                && status.status == 503) {
                            return "cached";
                        }
                        throw new CompletionException(underlying);
                    })
                    .join();
            System.out.println("handle recovery: " + recovered);

            String fallback = checkedGet(
                    client, base.resolve("busy"))
                    .exceptionally(failure -> {
                        Throwable underlying = root(failure);
                        if (underlying instanceof HttpStatusException status
                                && status.status == 503) {
                            return "retry-later";
                        }
                        throw new CompletionException(underlying);
                    })
                    .join();
            System.out.println("exceptionally recovery: " + fallback);

            String onlyFailure = checkedGet(
                    client, base.resolve("ok"))
                    .exceptionally(failure -> "unexpected")
                    .join();
            System.out.println("exceptionally success: " + onlyFailure);

            CompletableFuture<String> broken =
                    checkedGet(client, base.resolve("busy"))
                            .thenApply(s -> s + "!");

            try {
                broken.join();
            } catch (CompletionException failure) {
                System.out.println("join: "
                        + failure.getClass().getSimpleName()
                        + " -> "
                        + root(failure).getClass().getSimpleName());
            }

            try {
                broken.get();
            } catch (ExecutionException failure) {
                System.out.println("get: "
                        + failure.getClass().getSimpleName()
                        + " -> "
                        + root(failure).getClass().getSimpleName());
            }

            String observed = checkedGet(
                    client, base.resolve("busy"))
                    .whenComplete((body, failure) -> {
                        if (failure != null) {
                            System.out.println("whenComplete saw: "
                                    + root(failure)
                                            .getClass().getSimpleName());
                        }
                    })
                    .exceptionally(failure ->
                            "fallback-after-observe")
                    .join();
            System.out.println("after observation: " + observed);

            CompletableFuture<String> cancelled =
                    new CompletableFuture<>();
            cancelled.cancel(true);
            try {
                cancelled.join();
            } catch (CancellationException failure) {
                System.out.println("cancel: "
                        + failure.getClass().getSimpleName());
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy với JDK 17+ có module `jdk.httpserver`:

~~~bash
javac -encoding UTF-8 HttpFailureStagesDemo.java
java HttpFailureStagesDemo
~~~

Kết quả đã được kiểm tra bằng JShell trên Java 17:

~~~text
Raw HTTP status: 503
handle success: ready
handle recovery: cached
exceptionally recovery: retry-later
exceptionally success: ready
join: CompletionException -> HttpStatusException
get: ExecutionException -> HttpStatusException
whenComplete saw: HttpStatusException
after observation: fallback-after-observe
cancel: CancellationException
~~~

### 8.1. Giải thích từng dòng đầu ra

1. **`Raw HTTP status: 503`**: `sendAsync` trả `HttpResponse` bình thường; mã 503 tự nó không phải future exception.
2. **`handle success: ready`**: HTTP 200 được chuyển qua `thenApply` thành body; `handle` nhận `error==null` và giữ nguyên `ready`.
3. **`handle recovery: cached`**: `checkedGet` ném `HttpStatusException(503)` ở stage status-check; `handle` được gọi trên đường lỗi, bóc wrapper và trả `cached`.
4. **`exceptionally recovery: retry-later`**: callback chỉ chạy trên stage exceptional, xác định đây là 503 đã được ứng dụng phân loại và thay bằng fallback.
5. **`exceptionally success: ready`**: khi upstream thành công, `exceptionally` **không chạy**; nó không sửa body.
6. **`join: CompletionException -> HttpStatusException`**: lỗi đi tới biên `join`, nơi caller thấy wrapper unchecked; helper chọn cause nghiệp vụ đúng.
7. **`get: ExecutionException -> HttpStatusException`**: `get` dùng checked wrapper khác. Dù gọi trên cùng broken future, unwrap giúp nhận cùng loại lỗi.
8. **`whenComplete saw: HttpStatusException`**: callback quan sát lỗi nhưng **không recover**. Stage `exceptionally` phía sau mới tạo fallback.
9. **`after observation: fallback-after-observe`**: kết quả của stage recovery chạy sau `whenComplete`.
10. **`cancel: CancellationException`**: một future được hủy trực tiếp có thể làm `join` ném CancellationException, không nhất thiết đi qua CompletionException.

Trong demo, các lệnh `join` được gọi ở **main** để ra stdout xác định và dạy semantics. Trong server/web event loop production, **không chặn thread phục vụ I/O** bằng `join`/`get` nếu bạn có thể nối tiếp bằng CompletionStage.

### 8.2. Tại sao chọn server loopback?

`127.0.0.1` là địa chỉ loopback IPv4, server bind cổng 0 để hệ điều hành cấp cổng khả dụng. Client và server nằm trong **cùng tiến trình Java**; không đụng Internet, DNS công cộng hoặc API thật. Nhờ vậy có thể xác minh chắc chắn **HTTP status → exceptional status check → recovery** mà không bị biến số về mạng bên ngoài. Code đóng `HttpExchange`, dừng server trong `finally` và không yêu cầu file/tài khoản khác.

### 8.3. Demo có gì chưa phải production?

- `HttpStatusException` chỉ giữ status, không kèm trace ID, response headers hoặc body lỗi bị giới hạn dung lượng.
- `checkedGet` xem mọi status >=400 là exceptional theo policy demo; ứng dụng thực tế có thể xử lý 404/409/429/503 khác nhau.
- `"cached"` và `"retry-later"` là giá trị minh họa, chưa tích hợp cache thật, TTL hay metrics.
- Demo **không xử lý network timeout, TLS identity, redirects, retry/backoff và cancellation propagation** trên một HTTP exchange đang hoạt động.
- `HttpServer` demo không có auth/TLS và dùng loopback; không triển khai một server production trên Internet.

Hãy xem chương trình như bài thử **ngữ nghĩa CompletionStage**, không như thư viện HTTP có đầy đủ policy lỗi.

## 9. Lỗi của HttpClient.sendAsync thường đến từ những tầng nào?

Một async HTTP pipeline có nhiều nguồn lỗi:

| Nguồn | Dấu hiệu có thể thấy | Nên xử lý thế nào |
| --- | --- | --- |
| Không phân giải được host | `UnknownHostException` hoặc cause liên quan DNS | Kiểm tra URI/DNS; retry có giới hạn nếu hợp lý |
| Không kết nối được | `ConnectException`/`IOException` | Kiểm tra server, routing, port, firewall, điều kiện transient |
| Kết nối/TLS không an toàn | `SSLHandshakeException` hoặc lỗi TLS khác | **Không bypass trust/certificate verification** để cho qua |
| Request quá hạn | `HttpTimeoutException`, `HttpConnectTimeoutException` | Phân biệt timeout connect vs toàn request, deadline và policy |
| Response body decoding thất bại | `IOException` hoặc exception của BodySubscriber | Xử lý body size/encoding, kiểm tra contract |
| Mapper tự ném | `IllegalArgumentException`, `IllegalStateException` hoặc custom type | Sửa contract/parse/input; không mặc định retry network |
| HTTP trả status 4xx/5xx | `HttpResponse.statusCode()`, **không tự là exception** | Phân loại status trong stage ứng dụng |
| Future bị cancel | `CancellationException` có thể trực tiếp hoặc trong cause | Dừng downstream, cleanup, không tự hồi sinh tác vụ |
| Callback recovery ném lỗi | Lỗi mới của handler | Bảo toàn nguyên nhân/log, định nghĩa fallback có thể thất bại |

Các loại exception và chain thực tế thay đổi theo JDK, provider, proxy, HTTP version và vị trí callback. **Đừng viết `if (error instanceof ConnectException)` duy nhất** rồi bỏ qua việc stage có thể cung cấp `CompletionException` bọc bên ngoài; nhưng cũng **đừng tự chuyển mọi lỗi mạng thành “HTTP 503”** nếu server chưa từng trả 503.

### 9.1. HTTP 503 và `HttpTimeoutException` không phải một thứ

- **HTTP 503**: server hoặc intermediary thực sự trả một HTTP response; có thể có header `Retry-After`. 503 tự nó là một status **trong HttpResponse**.
- **`HttpTimeoutException`**: client hết thời hạn request, có thể chưa hề nhận HTTP response; không được bịa ra status 503 từ exception.
- **`HttpConnectTimeoutException`**: lỗi timeout giai đoạn thiết lập kết nối (là subtype của `HttpTimeoutException` trong Java).
- **`TimeoutException` của `CompletableFuture.orTimeout`**: deadline do tầng future đặt, không mặc định đồng nghĩa với timeout nội bộ HTTP.

Phân loại đúng giúp metrics và chính sách retry chính xác. Một dashboard báo “HTTP status=503” cho các request DNS failed là sai, vì không có response status.

### 9.2. HTTP 4xx không phải tất cả đều nên retry

Thông thường:

- **400/422**: request/schema lỗi; retry y hệt sẽ không giúp.
- **401/403**: vấn đề credential/authorization; phải giải quyết theo policy, không thử vô hạn.
- **404**: có thể là trạng thái nghiệp vụ hợp lệ; có thể dùng result type thay vì exception.
- **409/412**: trạng thái cạnh tranh/xung đột; cần đọc lại state, hợp nhất hoặc báo user, không chỉ gửi lại nguyên request.
- **429**: rate limit; xem `Retry-After`/quota và chính sách backoff.
- **503**: tạm thời không khả dụng; có thể retry **GET idempotent** có giới hạn nếu budget cho phép.

Đây là định hướng, không phải quy tắc cứng của mọi API. Retry phải dựa HTTP method, idempotency, deadline và hành vi server cụ thể.

## 10. Bóc wrapper và phân loại nguyên nhân không làm mất thông tin

Một pattern đơn giản:

~~~java
static String classify(Throwable error) {
    Throwable cause = root(error);

    if (cause instanceof CancellationException) {
        return "CANCELLED";
    }
    if (cause instanceof HttpConnectTimeoutException) {
        return "CONNECT_TIMEOUT";
    }
    if (cause instanceof HttpTimeoutException) {
        return "REQUEST_TIMEOUT";
    }
    if (cause instanceof SSLHandshakeException) {
        return "TLS_FAILURE";
    }
    if (cause instanceof HttpStatusException status) {
        return "HTTP_" + status.status;
    }
    if (cause instanceof IOException) {
        return "NETWORK_OR_IO";
    }
    return "OTHER";
}
~~~

Đây là **mã minh họa trong class có `root` và `HttpStatusException`**, cần imports `java.io.IOException`, `javax.net.ssl.SSLHandshakeException`, `java.net.http.HttpTimeoutException`/`HttpConnectTimeoutException` và `CancellationException`. **Thứ tự subtype quan trọng**: `HttpConnectTimeoutException` phải được kiểm tra trước `HttpTimeoutException`. Nhóm `IOException` là umbrella rộng, không phải mọi IO error được retry.

### 10.1. Đặc biệt xử lý cancellation

Nếu `cause instanceof CancellationException`, đừng mặc định trả một cached value “như thể request thành công” nếu thao tác đã bị người dùng chủ động hủy. Với hệ thống ứng dụng, cancellation thường là **tín hiệu kết thúc pipeline**; hãy propagate/hủy các tác vụ liên quan và dọn tài nguyên theo policy.

Ví dụ:

~~~java
.exceptionally(error -> {
    Throwable cause = root(error);
    if (cause instanceof CancellationException) {
        throw (CancellationException) cause;
    }
    if (cause instanceof HttpStatusException status
            && status.status == 503) {
        return "stale-ok-by-policy";
    }
    throw new CompletionException(cause);
})
~~~

Đây là fragment gắn vào `CompletableFuture<String>`. Nếu callback ném `CancellationException`, dependent stage bị exceptional; **không nhất thiết có flag `isCancelled()==true` giống trực tiếp gọi `cancel` trên chính dependent future**. Khi quan sát exception, phân biệt lỗi cancel và cách cancellation được lan theo chain.

### 10.2. Giữ exception gốc khi rethrow

Trong handler có thể:

~~~java
throw new CompletionException(root(error));
~~~

Cách này tạo failure mới với cause để downstream vẫn phân loại. Không xây `new RuntimeException("something went wrong")` rồi bỏ cause — sẽ làm mất stack trace cũ và đường dẫn chẩn đoán. Trong app thật còn nên giữ correlation ID, request ID và original error object trong logging.

**Không bắt `Throwable` rồi recover mọi thứ vô điều kiện**. Một lỗi nghiêm trọng của runtime hoặc bug logic không nên tự coi là “network transient” chỉ vì nó xuất hiện trong callback `exceptionally`.

## 11. `handle` hay `exceptionally` trong một chuỗi có nhiều bước?

Ví dụ pipeline có ba bước:

~~~text
sendAsync
    |
    v
thenApply(validate HTTP status)
    |
    v
thenApply(parse body)
    |
    +--> exceptionally(recover only approved failures)
    |
    v
thenApply(consume result)
~~~

Nếu parser JSON lỗi sau một HTTP 200, exceptional stage sẽ đến `exceptionally` như network failure. Vì vậy handler không được check đơn giản “error != null -> dùng cache” cho mọi lỗi: JSON schema mismatch có thể là lỗi triển khai hoặc contract, không nên che giấu.

### 11.1. Đặt recover ở đâu ảnh hưởng nguyên nhân được thấy

~~~java
// A: chỉ bắt lỗi từ network/HTTP exchange ở đúng thời điểm.
CompletableFuture<HttpResponse<String>> raw =
        client.sendAsync(request, BodyHandlers.ofString());

// B: mapper status có thể tạo HttpStatusException.
CompletableFuture<String> validated =
        raw.thenApply(HttpResponse::body); // chưa kiểm tra status.

// C: parse body có thể ném JSON parsing exception.
CompletableFuture<Model> parsed =
        validated.thenApply(MyParser::parse);
~~~

Đoạn trên là minh họa; `MyParser`, `Model` là class giả định và đoạn `validated` chưa check status. **Vị trí `exceptionally`** quyết định nó có nhìn được lỗi của parser hay không: móc trước parser thì không thấy lỗi parser; móc sau parser thì có thể thấy cả network, status và parse errors. Đặt recovery ở nơi **đủ thông tin để phân loại nhưng chưa tạo ra tác dụng phụ**.

### 11.2. Tách transport result và business result

Một thiết kế dễ kiểm thử là tách:

- **Transport/HTTP stage:** thành công với `HttpResponse`, hoặc exception khi network/transport thất bại.
- **Status validation stage:** phân biệt status được chấp nhận và status được định nghĩa là lỗi.
- **Decode stage:** chuyển body thành domain object; schema invalid là một loại lỗi riêng.
- **Recovery stage:** chỉ fallback với lỗi mà policy cho phép.
- **Observation stage:** log/metrics của kết quả cuối cùng, nhưng không “nói dối” rằng đã nhận fresh response nếu thật ra dùng cache.

Có thể dùng sealed interfaces/record `Result` mang `source=LIVE/CACHE` và `stale` để thể hiện fallback rõ ràng. Khi dùng `handle` chuyển lỗi thành giá trị, hãy giữ dấu hiệu đã recovery cho logging thay vì coi đó là cùng loại thành công với HTTP 200 fresh.

## 12. Recovery bằng một future khác: `exceptionallyCompose`

`exceptionally` trả một **giá trị T**, không trả `CompletableFuture<T>` để tự compose. Nếu fallback phải gọi API thứ hai, lấy dữ liệu từ cache bất đồng bộ hoặc tra downstream khác, nên sử dụng `exceptionallyCompose` trên Java 17+ hoặc thiết kế `handle` trả future rồi `thenCompose`.

Minh họa **không độc lập**, giả định `readCacheAsync(key)` trả `CompletableFuture<String>`:

~~~java
CompletableFuture<String> result =
        checkedGet(client, uri)
                .exceptionallyCompose(error -> {
                    Throwable cause = root(error);
                    if (cause instanceof HttpStatusException status
                            && status.status == 503) {
                        return readCacheAsync(key);
                    }
                    return CompletableFuture.failedFuture(cause);
                });
~~~

`exceptionallyCompose` (Java 12+) tạo continuation bất đồng bộ trên đường failure và **flatten** future dự phòng. Với `exceptionally`, viết `return readCacheAsync(key);` sẽ sai kiểu: handler phải trả `String` chứ không phải `CompletableFuture<String>`.

**Không gọi `readCacheAsync(key).join()` bên trong callback** chỉ để ép lấy String nếu có thể compose: làm vậy **chặn thread chạy completion**, gây nghẽn khi tải cao. Nếu fallback bản thân là một tác vụ CPU/DB blocking, hãy dùng executor được quản lý phù hợp để không chiếm worker I/O.

### 12.1. Chú ý executor của callback

Các callback không có hậu tố `Async` thường có thể chạy trên thread hoàn tất stage upstream hoặc thread đang đăng ký nếu stage đã hoàn thành; **không được giả định chúng chạy trên main thread**. Các biến thể `handleAsync`, `whenCompleteAsync` và `exceptionallyAsync` có thể chuyển sang một executor phù hợp.

Ví dụ:

~~~java
Executor executor = Executors.newFixedThreadPool(4);
CompletableFuture<String> f = checkedGet(client, uri)
        .handleAsync((body, error) -> {
            // Việc recovery CPU-bound vừa phải.
            return error == null ? body : "fallback";
        }, executor);
~~~

Đây là **mã minh họa**, cần import `Executor`/`Executors`, và production phải **đóng/shutdown executor** theo vòng đời ứng dụng. Không tạo một thread pool mới **cho mỗi request**; dùng pool được quản lý và giới hạn queue. Nếu fallback là I/O chậm, chuyển tiếp bằng future không chặn thường hợp lý hơn.

## 13. Timeout trong HttpClient và CompletableFuture

### 13.1. Timeout kết nối và timeout request

`HttpClient` cho phép đặt connect timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

`HttpRequest.Builder` cho phép đặt timeout cho request:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

Các đoạn này cần import `java.time.Duration` và types HTTP; chưa phải chương trình độc lập. Timeout của HTTP client có thể dẫn tới `HttpTimeoutException` (hoặc `HttpConnectTimeoutException` cho connect) bên trong exceptional completion. **Không có HTTP status để đọc nếu client chưa có response hợp lệ.**

### 13.2. `orTimeout` và `completeOnTimeout`

Hai cách tùy biến future:

~~~java
CompletableFuture<String> timed =
        checkedGet(client, uri)
                .orTimeout(2, TimeUnit.SECONDS);

CompletableFuture<String> defaulted =
        checkedGet(client, uri)
                .completeOnTimeout("fallback", 2, TimeUnit.SECONDS);
~~~

Đây là những request **khác nhau** trong minh họa. `orTimeout` làm future nhận `TimeoutException` nếu quá thời hạn; `completeOnTimeout` làm future hoàn thành **bình thường** với fallback khi timeout. Cả hai thao tác **có thể tác động trực tiếp lên chính CompletableFuture mà chúng được gọi** — không nên giả định chúng tạo ra một dependent stage độc lập để người khác vẫn chờ request cũ không đổi.

**Quan trọng:** timeout của một stage không tự cam kết underlying network I/O đã bị dừng ngay; cần quản lý cancellation/resource theo contract `HttpClient`, và không phát thêm request nếu deadline tổng đã hết. Nếu cần hủy HTTP exchange đang chạy, xem hành vi `cancel` của `sendAsync` trên JDK đang dùng; nó có thể yêu cầu hủy nhưng không bảo đảm peer chưa nhận hoặc xử lý byte.

### 13.3. `get(timeout)` không phải `orTimeout`

~~~java
String value = future.get(2, TimeUnit.SECONDS);
~~~

Nếu `get` ném `TimeoutException`, **future có thể vẫn đang chạy**; lời gọi chờ bị giới hạn, không nhất thiết làm future hoàn thành exceptionally hay cancel. Với `orTimeout`, future bị hoàn tất đặc biệt theo deadline nếu chưa có kết quả. Hai API giống từ “timeout” nhưng khác **thứ bị tác động**.

### 13.4. Không recover timeout vô hạn

Ví dụ sai:

~~~text
request timeout -> exceptionally -> retry ngay
retry timeout   -> exceptionally -> retry ngay
... không có max attempts hoặc overall deadline ...
~~~

Dù retry được GET, phải có **tổng deadline**, giới hạn số lần, backoff/jitter, kiểm tra `Retry-After` khi có, tôn trọng rate limits và tránh retry storms. Với POST/PUT có side effects, cần idempotency/transaction semantics trước khi tự replay.

## 14. Hủy request, interrupt và cleanup

### 14.1. Cancellation không nhất thiết là một lỗi mà có thể fallback

Khi người dùng rời màn hình, đóng app hoặc hủy tác vụ, tương lai có thể bị `cancel(true)`. Nếu các nhánh `exceptionally` đều trả cached value, bạn có thể khiến pipeline **hiển thị kết quả sau khi user đã hủy**. Do đó nên phân loại `CancellationException`, đánh dấu canceled và không tạo side effects trong callback tiếp theo.

`CompletableFuture.cancel(true)` làm future chuyển sang trạng thái canceled nếu chưa xong; giá trị `mayInterruptIfRunning` **không bảo đảm một thread cụ thể của CompletableFuture sẽ bị interrupt**, vì CompletableFuture không nhất thiết dùng interrupt để kiểm soát tiến trình. Khi áp dụng với `HttpClient.sendAsync`, hành vi cancel exchange còn phụ thuộc implementation và timing; **không thể kết luận dữ liệu chưa đến server**.

### 14.2. Khi dùng `get()` và bị interrupt

~~~java
try {
    return future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Dừng/propagate theo hợp đồng thread của ứng dụng.
    throw interrupted;
}
~~~

Đây là fragment đặt trong phương thức `throws InterruptedException, ExecutionException` hoặc khai báo tương đương. Khi bắt `InterruptedException`, **khôi phục interrupt flag** nếu không hoàn tất nhiệm vụ tại đây, giúp tầng trên biết thread đã bị yêu cầu dừng. `join` ném unchecked wrappers cho exceptional completion nhưng không thay thế việc quản lý interrupt khi bạn dùng blocking `get`.

### 14.3. Cleanup quan sát thất bại

Một kết nối/file/stream do ứng dụng sở hữu cần được đóng khi pipeline hoàn tất, thất bại hoặc cancel theo semantics. `whenComplete` phù hợp làm hook:

~~~java
CompletableFuture<String> result = checkedGet(client, uri)
        .whenComplete((body, error) -> {
            if (error != null) {
                logSafeFailure(root(error));
            }
            releaseRequestResources();
        });
~~~

Đây là mã minh họa có `logSafeFailure`/`releaseRequestResources` do ứng dụng định nghĩa. Trong ứng dụng thật, việc release cần **idempotent** nếu timer/cancel/completion tranh nhau, và không được đóng tài nguyên trước khi publisher/body subscriber thực sự ngừng sử dụng.

## 15. Thiết kế policy retry/recovery cho HTTP bất đồng bộ

Một policy vững thường xét **bốn chiều**:

1. **Loại lỗi:** status 429/503, network transient, TLS trust error, validation bug, timeout, cancel.
2. **Method/idempotency:** GET thường có thể retry; POST tạo đơn hàng không nên tự retry nếu không có idempotency key.
3. **Ngân sách:** số lần tối đa, overall deadline, delay/backoff/jitter và server `Retry-After`.
4. **Tác động đến người dùng:** fallback có được phép stale không, có cần cảnh báo dữ liệu cache, hay phải báo lỗi rõ?

Ví dụ bảng policy có tính minh họa:

| Lỗi / trạng thái | Recovery hợp lý? | Lưu ý |
| --- | --- | --- |
| GET gặp HTTP 503 | Có thể trả cache stale hoặc retry có giới hạn | Phải theo TTL/độ tin cậy của cache |
| HTTP 429 | Có thể chờ theo Retry-After, quota và deadline | Không retry storm |
| HTTP 404 | Có thể trả “không có dữ liệu” như một kết quả | Tùy API, không luôn là failure |
| HTTP 400/422 | Thường không retry y nguyên | Kiểm tra request/schema |
| TLS certificate verification lỗi | **Không** tự bypass xác thực | Kiểm tra cấu hình trust/hostname |
| DNS/ConnectException | Có thể retry có giới hạn tùy hoàn cảnh | Không tự khẳng định service đã xử lý gì |
| Parse error trên HTTP 200 | Thường cần fail/alert để điều tra | Không che giấu mọi schema mismatch |
| Cancellation | Không recover mặc định | Tôn trọng ý định hủy |
| Timeout sau POST side effect | Chưa chắc server chưa xử lý | Cần idempotency/đối soát |

**Đừng ghép `exceptionally` vô điều kiện cuối mọi pipeline chỉ để return “OK”**. Khi mọi lỗi thành công giả, metrics/tracing không phát hiện sự cố, người dùng thấy dữ liệu sai và hệ thống có thể thực thi nghiệp vụ lặp.

### 15.1. Fallback không có nghĩa đã đọc dữ liệu mới

Một DTO tốt có thể nói rõ:

~~~java
record ReadOutcome(String value, boolean fromCache, boolean stale) {}
~~~

Khi fallback do 503, trả `new ReadOutcome(cachedBody, true, true)`; khi HTTP 200 fresh, trả `new ReadOutcome(body, false, false)`. Đây là đoạn minh họa, chưa có phương thức lấy cachedBody. Cách biểu diễn này tránh “nói dối” downstream rằng dữ liệu cached là response mới từ origin.

### 15.2. `Retry-After` là metadata response, không luôn có trong Throwable

Nếu bạn ném `HttpStatusException(status)` nhưng không giữ response headers, thì đến `exceptionally` bạn sẽ không còn `Retry-After`. Một thiết kế production có thể lưu **status + giới hạn error body + headers cần thiết + request ID** trong custom error. Tuy nhiên không được giữ nguyên toàn bộ sensitive headers hoặc body không giới hạn dung lượng trong exception. Có thể chọn biến HTTP status thành một kiểu result thay vì exception nếu workflow cần metadata phong phú.

## 16. Test đúng các nhánh và log không làm mất lỗi

Một bộ kiểm thử quan trọng nên có:

- **HTTP 200**: `handle` chạy với `error==null`, `exceptionally` không chạy.
- **HTTP 503**: raw `sendAsync` **thành công** với `statusCode()==503`; status-check mới ném custom exception.
- **Custom status error**: `handle`/`exceptionally` chỉ recover mã được phép; mã khác vẫn exceptional.
- **`join` và `get`**: nhận wrapper đúng, helper tìm custom error.
- **`whenComplete`**: chỉ log; stage vẫn exceptional nếu không có recovery sau đó.
- **Thrown callback**: `handle` hoặc `exceptionally` tự ném thì dependent stage thất bại.
- **Cancel**: nhận `CancellationException`; không bị biến thành “thành công rỗng”.
- **Timeout**: phân biệt request `HttpTimeoutException` với future `TimeoutException`, `get(timeout)`.
- **TLS/network failures**: không coi như HTTP 503; không tắt kiểm tra chứng chỉ.
- **Unknown JSON/body shape**: lỗi parser không bị nuốt.
- **Concurrent requests**: không dùng biến shared mutable không đồng bộ để ghi exception hoặc kết quả của request khác.

Nên dùng **HTTP test server** tại loopback hoặc mock server để tạo status codes ổn định, thay vì phụ thuộc vào API công khai có thể đổi hoặc mạng không đáng tin. Ví dụ phần 8 làm đúng điều này cho những nhánh logic chính.

### 16.1. Một ca kiểm thử nhỏ về `whenComplete`

~~~java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));

CompletableFuture<String> watched =
        failed.whenComplete((v, e) -> {
            System.out.println("observed: " + root(e).getMessage());
        });

// watched vẫn thất bại; watched.join() sẽ ném.
~~~

Đoạn này là ví dụ trong class có `root`; nó cho thấy logging và recovery là hai hành động khác. Nếu thay `whenComplete` bằng `exceptionally(e -> "fallback")`, một stage mới có thể hoàn thành bình thường với String `fallback`.

## 17. Những lỗi thường gặp khi ghép các stage

| Sai lầm | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Cho rằng HTTP 503 tự kích hoạt `exceptionally` | Handler không chạy vì future gốc thành công | Đọc statusCode; tạo typed status failure nếu cần |
| Dùng `handle((value,error)->value)` không xét error | Biến lỗi thành normal null | Kiểm tra error và rethrow nếu không recover |
| `exceptionally(e -> "")` cho mọi lỗi | Che giấu TLS/cancel/parser bug | Phân loại nguyên nhân và có fallback policy |
| Nghĩ `whenComplete` return bình thường là đã bắt lỗi | Future vẫn exceptional | Dùng handle/exceptionally nếu muốn recover |
| Chỉ check `error instanceof HttpStatusException` | Bỏ sót wrapper CompletionException | Unwrap có kiểm soát |
| Luôn unwrap tất cả `getCause()` đến null | Mất context typed business error | Chỉ bỏ wrapper async, giữ nguyên lỗi nghiệp vụ |
| Bắt `Exception` từ `join` nhưng log mỗi message wrapper | Không biết nguyên nhân rõ | Log root + wrapper và stack |
| Trộn `get()` với `join()` và xử lý một kiểu exception duy nhất | Bỏ sót ExecutionException/checked flow | Phân biệt API boundary |
| `handle` trả null cho lỗi | NPE ở stage sau, che giấu nguyên nhân | Typed Result, fallback hợp lệ hoặc rethrow |
| Callback recovery tự ném nhưng không được monitor | Lỗi mới không được quan sát | Test failure path và nối terminal observer |
| Gọi `join()` trong completion callback để fallback async | Chặn worker, nguy cơ nghẽn | `exceptionallyCompose`/`thenCompose` |
| `sendAsync` trả 500 nhưng vẫn parse như 200 | Parser lỗi khó hiểu, mất HTTP context | Validate status trước parse theo contract |
| Phát lại POST sau TimeoutException không có idempotency | Có thể tạo side effect đôi | Chính sách retry/idempotency key |
| Trả cache nhưng metrics ghi live 200 success | Mất observability và stale data | Outcome ghi rõ source, stale/fallback |
| Bắt cancellation rồi trả cached body | Tiếp tục công việc đã bị hủy | Propagate CancellationException |
| Coi `get(timeout)` timeout là HTTP exchange đã bị cancel | Request có thể vẫn chạy | Quản lý future/network lifecycle riêng |
| Nuốt `InterruptedException` khi `get()` | Thread không còn tín hiệu dừng | Restore interrupt flag và propagate |
| Log đầy đủ bearer token, URL chứa secret | Rò rỉ dữ liệu | Redact, log correlation ID/summary |
| Chạy blocking DB trong `exceptionally` trên I/O completion thread | Chậm completions khác | Compose async hoặc dùng bounded executor |
| Dùng một `CompletableFuture` cho nhiều request không liên quan | Trộn kết quả và trạng thái | Mỗi operation có future/state riêng |

## 18. Bài tập tình huống

### Bài A — HTTP 500 đi qua `exceptionally`?

Code:

~~~java
client.sendAsync(request, BodyHandlers.ofString())
      .exceptionally(error -> fallbackResponse);
~~~

Server trả response HTTP 500 hợp lệ, không có transport exception. `exceptionally` có chạy không?

**Đáp án:** thường **không**. `HttpClient` trả `HttpResponse` có `statusCode()==500`; cần check status hoặc map sang một lỗi typed trước khi `exceptionally` xử lý. Lỗi callback/body handler vẫn có thể làm stage exceptional, nhưng chỉ status 500 thì không.

### Bài B — `handle` nhận thành công

Upstream trả String `"A"`. Callback:

~~~java
.handle((value, error) -> error == null ? value + "!" : "FALLBACK")
~~~

**Đáp án:** `handle` chạy cả thành công, nhận `value="A"`, `error=null` và trả `"A!"`. Nếu dùng `exceptionally` thay thế, callback không chạy và kết quả vẫn `"A"`.

### Bài C — `handle` vô tình che lỗi

`CompletableFuture<String>` thất bại do `SSLHandshakeException`, nhưng code dùng `handle((body, err) -> err == null ? body : "OK")`.

**Đáp án:** stage sau sẽ hoàn thành bình thường với `"OK"`, che giấu lỗi TLS và làm downstream tưởng nhận response tốt. Cần rethrow nguyên nhân hoặc dùng typed result thất bại; không bỏ qua trust/certificate failure.

### Bài D — join vs get

Một stage thất bại do `HttpStatusException(503)`. `join()` và `get()` đưa ra exception giống nhau?

**Đáp án:** thường `join()` ném `CompletionException` (unchecked), còn `get()` ném `ExecutionException` (checked). Unwrap hai wrapper đó để lấy typed HTTP exception. Với cancellation direct, `CancellationException` có thể xuất hiện trực tiếp.

### Bài E — Lỗi gốc dưới hai wrapper

Callback nhận `CompletionException(ExecutionException(ConnectException))`. Phân loại gì?

**Đáp án:** helper `root` bóc hai wrapper async và trả `ConnectException`. Không coi là HTTP status 503; nếu chưa có response, không tự bịa HTTP status code.

### Bài F — `whenComplete` ghi log xong

Future thất bại với `IllegalArgumentException`. Callback `whenComplete` in log và return bình thường. Stage mới thành công không?

**Đáp án:** không. Nếu callback không ném thêm, lỗi upstream vẫn được truyền tới stage mới. Chỉ `handle` hoặc `exceptionally` có thể chuyển sang giá trị bình thường một cách rõ ràng.

### Bài G — request bị hủy

Người dùng bấm Cancel; một dependent stage nhận cause `CancellationException`. Policy currently recover mọi exception bằng cached body.

**Đáp án:** nên tôn trọng cancellation; không tự hồi sinh pipeline bằng cached body. Truyền trạng thái canceled/failure và dọn resources theo thiết kế.

### Bài H — Timeout từ `get(timeout)`

Caller dùng `future.get(500, MILLISECONDS)` và nhận `TimeoutException`. Có chắc future đã kết thúc hay HTTP request đã cancel?

**Đáp án:** không. Chỉ **lượt chờ** bị timeout, future có thể hoàn tất sau. Cần deadline/cancel riêng và tránh làm side effects sau khi user đã bỏ tác vụ.

### Bài I — Retry POST có thể gây trùng

Client POST tạo order, socket mất trước khi nhận response; `exceptionally` nhận `IOException`. Có thể chắc chắn retry sẽ không tạo hai order?

**Đáp án:** không. Server có thể đã ghi order trước khi mạng lỗi. Cần idempotency key, query trạng thái giao dịch hoặc cơ chế retry đã được API thỏa thuận.

### Bài J — Fallback async cần gọi API thứ hai

Một chuỗi `exceptionally(error -> backupService.fetchAsync())` không compile vì future chính có kiểu `CompletableFuture<String>`.

**Đáp án:** `exceptionally` phải trả `String`, không phải `CompletableFuture<String>`. Dùng `exceptionallyCompose` nếu backupService trả future, hoặc `handle` tạo future rồi `thenCompose` để flatten.

### Bài K — Exception do parser

HTTP 200 trả text `"not-json"`, `thenApply(parser::parse)` ném `JsonParsingException`. Có nên retry network mãi?

**Đáp án:** không tự động. Đây có thể là lỗi contract/schema/bug parser, không phải mạng tạm thời. Phân loại typed exception, log status/body có giới hạn và phản hồi theo policy.

### Bài L — TimeoutException không giống HttpTimeoutException

`future.orTimeout(...)` hết hạn, nhưng `HttpRequest.timeout(...)` không bật. Stage có thể thấy loại exception nào?

**Đáp án:** `TimeoutException` từ cơ chế CompletableFuture, thường xuất hiện qua wrapper trong stage khác; không nhất thiết là `HttpTimeoutException`. Khác nguồn timeout dẫn tới cách metrics và lifecycle khác nhau.

## 19. Checklist dùng CompletableFuture cho HTTP bất đồng bộ

- [ ] Đã phân biệt **HTTP error status** (HttpResponse) với **exceptional completion** (network/callback/mapper)?
- [ ] `handle` được dùng khi thật sự muốn xử lý cả success lẫn failure, có typed fallback rõ ràng?
- [ ] `exceptionally` chỉ recovery những error types được phép, không blanket-success mọi Throwable?
- [ ] Nếu chỉ log/metrics, dùng `whenComplete` và không vô tình tin rằng nó nuốt lỗi?
- [ ] Đã kiểm tra vị trí `thenApply(status-check)` để lỗi status được convert trước stage recovery?
- [ ] Có helper unwrap `CompletionException`/`ExecutionException` một cách kiểm soát, không xóa typed root?
- [ ] Đã phân biệt `join` (unchecked wrapper), `get` (checked wrapper, interrupt) và cancellation direct?
- [ ] Đã xử lý `CancellationException` và không thực hiện tác vụ đã bị hủy?
- [ ] Timeout của HTTP request, CompletableFuture và việc chờ get(timeout) có được phân biệt?
- [ ] Nếu fallback cũng async, dùng compose thay vì blocking `join()` trong completion worker?
- [ ] Có tổng deadline, giới hạn retry, backoff/jitter, idempotency key với side-effect requests?
- [ ] Có rõ status 404/409/429/503 nào là kết quả nghiệp vụ hợp lệ và status nào cần tạo custom error?
- [ ] Xử lý TLS verification errors an toàn, không tự sửa bằng cách tắt SSL checks?
- [ ] Không nuốt exception từ parse/mapping logic thành empty/default value không mong muốn?
- [ ] Có record success/live vs fallback/cache/stale để observability không bị lệch?
- [ ] Logs có stack + correlation ID cần thiết nhưng không lộ secrets?
- [ ] Các resources, futures và executors được cleanup đúng vòng đời cả normal/error/cancel?
- [ ] Test cả raw HTTP 503, converted status exception, handle success/recovery, exceptionally success/recovery, join/get và whenComplete propagation?

**Kết luận:** Với HTTP bất đồng bộ trong Java, `handle` chạy cho **cả giá trị và lỗi** và có thể đổi kiểu; `exceptionally` chạy **chỉ khi stage trước thất bại** và có thể thay bằng fallback; `whenComplete` chủ yếu **quan sát kết quả** mà không recover. `CompletionException`/`ExecutionException` thường là các wrapper khi lỗi đi qua CompletableFuture — hãy tìm đúng nguyên nhân bên trong để phân loại, nhưng **không vứt context**. Một HTTP status 503 không tự là Java exception; muốn recovery theo status cần kiểm tra status ở stage ứng dụng. Recovery chính xác là **có điều kiện, có deadline, tôn trọng cancellation và semantics HTTP**, chứ không phải trả default cho mọi lỗi.

## 20. Tài liệu API để đối chiếu

- **Java 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Java 17 — CompletionStage:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **Java 17 — CompletionException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html
- **Java 17 — ExecutionException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpRequest:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- **Java 17 — HttpResponse:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- **Java 17 — HttpTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- **RFC 9110 — HTTP Semantics (status codes):** https://www.rfc-editor.org/rfc/rfc9110

Các quyết định status-error, fallback và retry là **chính sách của ứng dụng**, không có một cách mặc định áp dụng an toàn cho mọi HTTP API. Khi xây production system, hãy tách transport errors, HTTP statuses và domain failures, kiểm thử đúng môi trường Java và giữ thông tin chẩn đoán từ cause chain.