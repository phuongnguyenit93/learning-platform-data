# Kiểu trả về void, Future và CompletableFuture của @Async trong Spring Framework

`@Async` cho phép Spring chuyển một lời gọi phương thức sang executor để thực thi công việc theo cơ chế bất đồng bộ. Nhưng **kiểu trả về** của phương thức quyết định caller có nhận được tín hiệu hoàn thành, kết quả và exception hay không. Với Spring Framework, ba kiểu phổ biến nhất là **`void`**, **`Future<T>`** và **`CompletableFuture<T>`**. Chúng không chỉ khác cú pháp mà còn khác cách tổ chức luồng xử lý, quan sát lỗi, timeout, cancellation và phối hợp nhiều tác vụ.

Bài học này thuộc nhóm **Bật `@Async`**: tập trung vào hợp đồng kiểu trả về khi sử dụng Spring proxy, cách triển khai đúng và cách caller tiêu thụ kết quả. Các ví dụ sử dụng Java 17+ và Spring Framework 6.x; code Spring cần dependency `spring-context`, còn ví dụ Java thuần có thể biên dịch bằng JDK.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích tại sao phương thức `@Async` chỉ nên khai báo `void` hoặc kiểu `Future` được Spring hỗ trợ, và không thể đổi trực tiếp thành `String`, `int`, `ResponseEntity` rồi kỳ vọng proxy hoạt động như một lời gọi async trả giá trị.
- Chọn `void` cho tình huống không cần trả kết quả, hiểu cách báo lỗi qua `AsyncUncaughtExceptionHandler`.
- Trả về `Future<T>` khi caller cần nhận kết quả bằng `get()`, và xử lý `ExecutionException`, `TimeoutException`, `InterruptedException`.
- Dùng `CompletableFuture<T>` để áp dụng `thenApply`, `thenCompose`, `thenCombine`, `allOf`, `handle`, `exceptionally` và quan sát thất bại.
- Hiểu sự khác biệt giữa **Future tạm trong target method** và **Future thực từ Spring proxy**.
- Phân biệt lỗi **tại thời điểm gửi task** với lỗi **xảy ra trong task**, cùng tác động của timeout, cancellation và executor bão hòa.
- Tránh tự gọi `@Async` trong cùng bean, tránh block thread không cần thiết và tránh hiểu nhầm `CompletableFuture.completedFuture` hoặc `supplyAsync`.

## 2. Điều kiện để @Async thật sự hoạt động

`@Async` là một annotation của Spring, không phải từ khóa Java tự tạo thread. Trong cách dùng phổ biến, Spring đăng ký interceptor thông qua `@EnableAsync` rồi tạo proxy quanh bean. Khi bean khác gọi method **qua proxy**, interceptor quyết định executor và gửi một tác vụ tới executor đó. Lời gọi từ client thông thường trở về mà không đợi phần việc trên worker hoàn thành; ngoại lệ gồm executor chạy trực tiếp trên caller hoặc cấu hình policy đặc biệt.

Mô hình khái niệm:

~~~text
Caller thread
  |
  | gọi asyncService.compute(...)
  v
Spring proxy / @Async interceptor
  |
  | submit Callable/Runnable tới executor
  +-------------------------------+
  |                               |
  | trả về void hoặc Future        v
  |                          Worker thread
  |                           chạy target method
  |                           hoàn thành hoặc lỗi
  v                               |
Caller có thể làm việc khác       |
  |                               |
  +---- Future / callback <-------+
~~~

Để mô hình này đúng:

1. Bật `@EnableAsync` ở phần cấu hình ứng dụng (Spring Boot cũng có thể dùng nó để kích hoạt annotation-driven async).
2. Sử dụng một bean được Spring quản lý và gọi qua proxy; method `public`, có thể được override/intercept là lựa chọn dễ hiểu nhất.
3. Đặt cấu hình executor rõ ràng; có thể chỉ định bằng `@Async("reportExecutor")`.
4. Tránh `this.methodAsync()` trong cùng bean theo proxy mode mặc định: lời gọi nội bộ bỏ qua proxy và chạy như method Java bình thường.
5. Tránh đặt `@Async` trên method `private` hoặc `final` rồi kỳ vọng proxy mode thông thường chặn được lời gọi. `@Async` không hỗ trợ method khai báo trong `@Configuration` class.

**Giới hạn hợp đồng kiểu trả về:** với `@Async` theo Spring Framework 6.x, khai báo method nên là `void` hoặc một kiểu `java.util.concurrent.Future` được framework hỗ trợ, bao gồm `CompletableFuture`. Spring một số phiên bản cũ còn hỗ trợ `ListenableFuture` (API đã lỗi thời); trong code Java hiện đại, `CompletableFuture` thường phù hợp hơn. Một method đồng bộ có thể tự trả `String`; nhưng method đó không phải một chữ ký hợp lệ cho interceptor `@Async` trả giá trị bất đồng bộ.

## 3. Ba kiểu trả về: bảng so sánh nhanh

| Tiêu chí | `@Async void` | `@Async Future<T>` | `@Async CompletableFuture<T>` |
| --- | --- | --- | --- |
| Caller nhận ngay | Không có handle kết quả | Một `Future<T>` | Một `CompletableFuture<T>` |
| Đọc giá trị cuối | Không thể qua lời gọi này | `get()` | `get()`, `join()` hoặc callback |
| Quan sát kết thúc | Cần log/metric/state hoặc tín hiệu ngoài | `isDone()`, `get()` | `isDone()`, `whenComplete()`, chuỗi completion |
| Quan sát exception trong body | `AsyncUncaughtExceptionHandler` | `get()` ném `ExecutionException` | Hoàn thành exceptionally; `join()` thường ném `CompletionException` |
| Chuỗi biến đổi không chặn caller | Không có kết quả để nối | Không có API chaining chuẩn | `thenApply`, `thenCompose`, `thenCombine`, ... |
| Hủy | Không có `Future` để hủy từ caller | `cancel(...)` | `cancel(...)` và các completion method |
| Rủi ro chính | Lỗi không đến caller; dễ “fire-and-forget” mất dấu | `get()` có thể block | Callback/exception chain phức tạp; vẫn có nguy cơ block |
| Tình huống tiêu biểu | Telemetry/báo hiệu best-effort | Tích hợp API cũ cần nhận kết quả | Orchestrate nhiều bước async, trả kết quả cho dịch vụ khác |

Đừng chọn `void` chỉ để tránh viết mã xử lý lỗi. Với công việc phải đảm bảo hoàn thành, dù chọn kiểu nào bạn vẫn cần lưu trạng thái và cơ chế retry/khôi phục phù hợp.

## 4. @Async void: không có kênh kết quả cho caller

Method dạng:

~~~java
@Async("lessonExecutor")
public void sendAudit(String event) {
    auditRepository.save(event);
}
~~~

Đây là **đoạn minh họa** trong một Spring-managed bean có `auditRepository`; nó không tự chạy độc lập. Khi caller gọi qua proxy và executor nhận việc, caller thường không đợi repository lưu xong. Method trả về `void` nên caller không có `get()`, `join()`, `isDone()` hay API cancellation.

Một lỗi trong body, ví dụ `auditRepository.save` ném exception, sẽ xảy ra trong quá trình chạy tác vụ. Với `void`, Spring không có Future nào để trả lỗi cho caller nên chuyển exception chưa được xử lý tới **`AsyncUncaughtExceptionHandler`**. Mặc định lỗi thường được log; có thể cung cấp handler riêng bằng `AsyncConfigurer`.

### Cấu hình handler cho lỗi của void

~~~java
import java.lang.reflect.Method;
import org.springframework.aop.interceptor.AsyncUncaughtExceptionHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.AsyncConfigurer;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncErrorConfiguration implements AsyncConfigurer {
    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (Throwable exception, Method method, Object... params) -> {
            System.err.println(
                    "Async void failed in " + method.getName()
                    + ": " + exception.getClass().getSimpleName());
        };
    }
}
~~~

Đây là **Spring configuration class** cần các thư viện Spring; không phải Java SE độc lập. Ứng dụng thật nên dùng logging/metrics/correlation ID có kiểm soát, không in toàn bộ params nếu chúng chứa dữ liệu nhạy cảm. Handler nên xử lý nhanh và không ném lỗi thứ cấp.

**`AsyncUncaughtExceptionHandler` không biến exception thành response cho caller.** Nếu API cần báo “job thành công/thất bại” cho người dùng, sử dụng `Future`/`CompletableFuture` hoặc một job ID trỏ tới trạng thái bền vững. Handler cũng không thay thế đường xử lý **TaskRejectedException khi không gửi được task**: rejection có thể xảy ra ngay lúc proxy submit công việc, trước khi body chạy.

### Khi nào void phù hợp?

- Công việc rất ngắn, có thể mất theo hợp đồng và đã có logging/metrics.
- Phát một sự kiện nội bộ best-effort có đường xử lý lỗi độc lập.
- Khởi động một quy trình mà trạng thái được quản lý ở một nơi khác, ví dụ job table; lúc đó `void` chỉ là giao diện dispatch chứ không phải bằng chứng hoàn thành.

Không dùng `@Async void` để hứa giao dịch tài chính, email quan trọng hoặc cập nhật đơn hàng được thực hiện chắc chắn. Một hàng đợi executor ở RAM không tạo bảo đảm durability.

## 5. @Async Future<T>: nhận handle và chủ động chờ kết quả

`Future<T>` của Java biểu diễn một phép tính có kết quả trong tương lai. Caller có thể sử dụng:

- `get()`: chờ vô hạn cho tới khi hoàn thành; khi task lỗi, ném `ExecutionException` có `getCause()` là lỗi gốc.
- `get(timeout, unit)`: chờ tối đa khoảng cho trước; khi hết thời gian, ném `TimeoutException`.
- `isDone()`: cho biết Future đã kết thúc theo một cách nào đó (thành công, lỗi hoặc bị cancel), **không** cho biết chỉ riêng thành công.
- `cancel(mayInterruptIfRunning)` và `isCancelled()`: yêu cầu/cung cấp trạng thái hủy; kết quả thực tế còn phụ thuộc implementation và việc task có hợp tác dừng.

Với `@Async Future<T>`, caller nhận một Future từ **proxy**. Target method phải giữ đúng chữ ký `Future<T>`, nên bên trong target method trả một **Future tạm** chứa giá trị vừa tính xong. Một cách đơn giản trong Java 17 là `CompletableFuture.completedFuture(value)`, có thể gán cho `Future<T>`.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class UserLookupService {

    @Async("lessonExecutor")
    public Future<String> lookup(int userId) {
        // Giả lập công việc blocking thực sự; ở đây chỉ tính chuỗi.
        String value = "user-" + userId;
        return CompletableFuture.completedFuture(value);
    }
}
~~~

**Quan trọng:** câu lệnh `completedFuture(value)` trên được thực hiện **bên trong thread xử lý target method**; nó làm phần target thỏa chữ ký kiểu trả về. Future mà **caller nhìn thấy thông qua Spring proxy** là handle đại diện cho tác vụ thực sự được submit tới executor và có thể chưa hoàn thành. Nó không phải lời cam kết rằng toàn bộ lời gọi `@Async` đã hoàn tất đồng bộ ngay tại caller.

Một cách làm ở mã Spring cũ là `new AsyncResult<>(value)`; trong tài liệu hiện đại, `CompletableFuture.completedFuture(value)` thường đủ rõ và không cần thêm lớp helper.

### Caller lấy kết quả và xử lý exception

Đoạn dưới là **mã minh họa trong một service/controller khác** đã inject `UserLookupService userLookupService`, không phải code độc lập:

~~~java
Future<String> future = userLookupService.lookup(7);

try {
    String user = future.get(2, TimeUnit.SECONDS);
    System.out.println(user);
} catch (TimeoutException ex) {
    // Timeout chỉ giới hạn thời gian chờ; không tự dừng worker.
    future.cancel(true);
} catch (ExecutionException ex) {
    // Lỗi trong worker nằm ở ex.getCause().
    throw new IllegalStateException("Lookup failed", ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Trả quyền quyết định hủy/thoát cho tầng gọi.
}
~~~

Cần import `java.util.concurrent.*` hoặc các lớp cụ thể. `Future.get()` là **blocking**: nếu gọi ngay sau `lookup()` trên request thread rồi chờ cho tới khi xong, bạn vẫn chặn thread đang phục vụ request. Việc chuyển công việc sang worker không đồng nghĩa toàn bộ request trở thành non-blocking.

`get(timeout)` ném `TimeoutException` không có nghĩa task bị hủy hoặc không bao giờ thành công; timeout là trạng thái của **người chờ**, không phải trạng thái thực thi của công việc. `cancel(true)` có thể yêu cầu interrupt task đang chạy với Future dạng thông thường, nhưng task phải phản hồi interruption và các thư viện blocking phải hỗ trợ; không có bảo đảm dừng side effect đã bắt đầu.

### Future<T> không có chaining trực tiếp

`Future` chỉ có API chờ, kiểm tra và hủy. Nó không trực tiếp cung cấp `thenApply` hoặc `thenCompose`. Vì vậy khi cần nhiều phép biến đổi liên tiếp, caller thường phải block bằng `get()` hoặc tự quản lý callback/worker bổ sung. Đây là lý do `CompletableFuture` thường tiện hơn cho code Spring hiện đại.

## 6. @Async CompletableFuture<T>: kết quả và composition

`CompletableFuture<T>` vừa triển khai `Future<T>` vừa triển khai `CompletionStage<T>`. Nó cho phép mô tả **cần làm gì khi có kết quả**, thay vì luôn buộc caller chờ.

Mẫu method Spring:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    @Async("lessonExecutor")
    public CompletableFuture<Integer> doublePrice(int price) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        int calculated = price * 2;
        return CompletableFuture.completedFuture(calculated);
    }
}
~~~

Đây là **Spring service** cần proxy và executor hợp lệ. Trong target method, `completedFuture(calculated)` chỉ tạo handle tạm đúng chữ ký. Khi gọi từ một bean khác qua proxy:

~~~java
CompletableFuture<Integer> result = pricingService.doublePrice(21);

CompletableFuture<String> rendered =
        result.thenApply(value -> "price=" + value);
~~~

`rendered` biểu diễn phép tính nối tiếp; caller có thể trả nó cho tầng khác thay vì block. Giá trị thành công sau khi hoàn tất sẽ là `price=42`. Nếu `doublePrice(-1)` ném exception trong worker, future từ proxy sẽ hoàn thành **exceptionally**, không trả về một giá trị `Integer` thành công.

### Vì sao không nên luôn gọi supplyAsync trong @Async?

Đây là cách làm dễ gây nhầm:

~~~java
@Async("lessonExecutor")
public CompletableFuture<String> fetch() {
    return CompletableFuture.supplyAsync(() -> remoteCall());
}
~~~

Đoạn trên là **mã minh họa không độc lập**, với `remoteCall()` do ứng dụng cung cấp. `@Async` đã giao target method cho một executor. Gọi `supplyAsync` không truyền executor lại gửi tiếp công việc lên **ForkJoinPool.commonPool()** theo mặc định, tạo thêm một tầng scheduling, làm việc kiểm soát thread pool, context, cancellation và quan sát lỗi phức tạp hơn. Nếu cần compose nhiều công đoạn, hãy thiết kế rõ mỗi executor và lý do chuyển thread; nếu chỉ tính một kết quả trong `@Async` method, thường trả `CompletableFuture.completedFuture(value)` sau khi tính xong là đủ.

Điều này **không** có nghĩa `CompletableFuture.supplyAsync` luôn sai. Nó rất hữu ích trong code Java thuần hoặc trong service không dùng `@Async`, khi bạn chủ động sở hữu executor và muốn tạo một chuỗi công việc bất đồng bộ.

## 7. Các phép kết hợp CompletableFuture quan trọng

| API | Hợp đồng | Khi nên dùng |
| --- | --- | --- |
| `thenApply(fn)` | Biến đổi giá trị `T -> U`; kết quả là stage mới | Mapping, formatting, tính toán ngắn |
| `thenCompose(fn)` | Chờ một stage do `fn` trả về rồi ghép phẳng kết quả | Bước sau phụ thuộc kết quả bước trước và chính nó async |
| `thenCombine(other, fn)` | Kết hợp hai future độc lập khi cả hai hoàn thành bình thường | Ghép profile và preferences |
| `allOf(f1, f2, ...)` | Future tổng hoàn tất khi tất cả future đã hoàn tất | Đợi một tập job; tự đọc từng kết quả sau khi thành công |
| `anyOf(f1, f2, ...)` | Hoàn tất theo future đầu tiên hoàn thành | Đua các tác vụ; không tự hủy các tác vụ còn lại |
| `whenComplete((v, ex) -> ...)` | Thực hiện callback quan sát giá trị/lỗi, giữ nguyên kết quả gốc nếu callback không lỗi | Metrics, logging, cleanup quan sát |
| `handle((v, ex) -> r)` | Biến đổi cả đường thành công lẫn lỗi sang kết quả mới | Chuyển lỗi sang giá trị fallback có chủ đích |
| `exceptionally(ex -> fallback)` | Cung cấp giá trị thay thế khi lỗi | Fallback an toàn khi nghiệp vụ cho phép |

### thenApply và thenCompose: tránh Future lồng nhau

Giả sử `profileService.load(id)` trả `CompletableFuture<Profile>` và `scoreService.score(profile)` trả `CompletableFuture<Integer>`. Các kiểu `Profile`, service ở đây là **placeholder khái niệm** của hệ thống, không phải ví dụ chạy độc lập.

Sai ý định khi muốn chỉ một future cuối:

~~~java
CompletableFuture<CompletableFuture<Integer>> nested =
        profileService.load(id)
                .thenApply(profile -> scoreService.score(profile));
~~~

`thenApply` chỉ biến đổi giá trị và giữ Future mới thành **giá trị** của stage ngoài. Dùng `thenCompose` để ghép phẳng:

~~~java
CompletableFuture<Integer> score =
        profileService.load(id)
                .thenCompose(profile -> scoreService.score(profile));
~~~

Nếu hai tác vụ độc lập, có thể thực thi đồng thời rồi kết hợp:

~~~java
CompletableFuture<String> description =
        nameService.loadName(id)
                .thenCombine(scoreService.loadScore(id),
                        (name, score) -> name + ":" + score);
~~~

Các đoạn này dùng service giả định, minh họa API composition; cần các interface/service tương ứng mới biên dịch. Chú ý quan sát exception từ **cả hai nguồn** và tránh tự chặn bằng `join()` bên trong callback đang chạy trên cùng executor có ít worker.

### allOf không tạo List<T> tự động

`CompletableFuture.allOf(a, b)` trả `CompletableFuture<Void>`: nó là tín hiệu tổng hợp, không phải `List<T>`. Khi tất cả hoàn thành thành công, có thể lấy kết quả từng future. Nếu một future hoàn thành exceptionally, future tổng cũng có thể hoàn thành exceptionally. Nếu muốn hiển thị lỗi riêng từng job, hãy handle chúng trước khi ghép.

Ví dụ chỉ minh họa với future `a` và `b` có kiểu `CompletableFuture<String>`:

~~~java
CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
CompletableFuture<String> summary =
        all.thenApply(ignored -> a.join() + ", " + b.join());
~~~

`join()` bên trong callback chỉ đọc kết quả đã hoàn tất thành công do `allOf` đứng trước; không dùng `join()` bừa bãi trong worker khi nó có thể phải chờ task khác chưa được lịch chạy.

## 8. Exception: void, Future và CompletableFuture truyền lỗi qua những kênh khác nhau

Ta có một target method ném `IllegalArgumentException`. Hình thức quan sát từ caller phụ thuộc kiểu trả về:

| Method | Kênh quan sát lỗi từ body | Cách xử lý |
| --- | --- | --- |
| `@Async void` | `AsyncUncaughtExceptionHandler` khi task chạy qua interceptor | Log, metrics, lưu trạng thái nghiệp vụ |
| `@Async Future<T>` | Future hoàn thành lỗi; `get()` ném `ExecutionException` | Đọc `getCause()`, phân loại lỗi, fallback hoặc fail |
| `@Async CompletableFuture<T>` | Future hoàn thành exceptionally | `handle`, `exceptionally`, `whenComplete`, hoặc `join/get` |
| Rejection trước khi task chạy | Có thể ném `TaskRejectedException` ngay tại lời gọi qua proxy | Xử lý từ chối submit, thông báo overload/persist retry |

Ví dụ xử lý lỗi với `CompletableFuture`:

~~~java
CompletableFuture<Integer> future = pricingService.doublePrice(-1);

CompletableFuture<String> message =
        future.handle((value, error) -> {
            if (error != null) {
                return "calculation failed";
            }
            return "result=" + value;
        });
~~~

Đây là **đoạn minh họa**, cần `pricingService` là Spring bean đã inject. `handle` chuyển cả đường lỗi thành một chuỗi thành công; điều này chỉ nên làm nếu fallback là một hành vi nghiệp vụ được phép. Nếu cần giữ lỗi cho tầng trên, `whenComplete` thường phù hợp hơn để log/metric mà không cố nuốt exception.

### get() và join(): khác loại exception

`Future.get()` (kể cả khi gọi trên `CompletableFuture`) có thể ném:

- `InterruptedException` nếu thread đang chờ bị interrupt.
- `ExecutionException` nếu phép tính lỗi; nguyên nhân nằm trong `getCause()`.
- `TimeoutException` với overload `get(timeout, unit)` nếu quá thời hạn chờ.
- `CancellationException` nếu future đã bị hủy.

`CompletableFuture.join()` không khai báo checked exceptions; khi tính toán thất bại thường ném `CompletionException` với cause là lỗi gốc, và khi hủy thì ném `CancellationException`. **Không nên coi `join()` là “non-blocking”**: nó vẫn chờ cho đến khi hoàn tất nếu future chưa done.

Mẫu bắt lỗi:

~~~java
try {
    int result = future.join();
    System.out.println(result);
} catch (CompletionException ex) {
    Throwable original = ex.getCause();
    System.err.println("Task failed: " + original);
} catch (CancellationException ex) {
    System.err.println("Task was cancelled");
}
~~~

Đây là **đoạn minh họa** với biến `future` kiểu `CompletableFuture<Integer>`; cần import `java.util.concurrent.CompletionException` và `CancellationException`.

### Lỗi có thể đến ngay lúc gọi @Async

Nếu executor quá tải và dùng `AbortPolicy`, `ThreadPoolTaskExecutor` của Spring thường thông báo `TaskRejectedException` **ngay lúc submit qua proxy**, trước khi có `Future` cho caller. Vì vậy nếu caller cần xử lý tình huống không tiếp nhận công việc, hãy bắt ở ranh giới gọi method:

~~~java
try {
    CompletableFuture<Integer> result = pricingService.doublePrice(21);
    // Chỉ xử lý result sau khi đã nhận được Future.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Executor không tiếp nhận tác vụ theo policy đang dùng.
}
~~~

Đoạn này không chạy độc lập và không được nhầm với lỗi `IllegalArgumentException` xuất hiện **trong body** của `doublePrice`. Nếu policy là `CallerRunsPolicy`, việc gửi có thể chạy inline và khiến caller block; nếu là `DiscardPolicy`, tác vụ có thể bị bỏ im lặng. Kiểu Future không sửa được sự mơ hồ do một policy bỏ task không báo lỗi.

## 9. Timeout, cancellation và interruption: các mức bảo đảm

| Công cụ | Ý nghĩa | Điều không được suy diễn |
| --- | --- | --- |
| `future.get(2, SECONDS)` | Người chờ tối đa hai giây | Không có nghĩa worker dừng ở giây thứ hai |
| `future.cancel(true)` | Yêu cầu hủy; với một số Future có thể đề nghị interrupt task | Không chắc side effect đã dừng |
| `future.isCancelled()` | Future được đánh dấu hủy | Không chứng minh I/O đã rollback |
| `CompletableFuture.orTimeout(2, SECONDS)` | Hoàn thành chính CompletableFuture đó exceptionally nếu chưa xong sau thời gian quy định | Không tự ngắt công việc chạy trên executor |
| `CompletableFuture.completeOnTimeout(default, 2, SECONDS)` | Hoàn thành bằng giá trị mặc định nếu quá hạn | Không chắc tác vụ nền không tiếp tục chạy |
| `CompletableFuture.cancel(true)` | Đánh dấu `CompletableFuture` là cancelled | `mayInterruptIfRunning` không được dùng để điều khiển interruption của worker |

`CompletableFuture` là một mô hình completion; việc gắn timeout/cancel trên handle **không đồng nghĩa** đang nắm quyền ngừng thread thực tế. Với tác vụ cần dừng đúng hạn, áp deadline vào I/O client, transaction và logic xử lý; thiết kế cancellation token, interruption hợp tác hoặc khả năng idempotent nếu phù hợp.

Lưu ý: `orTimeout` và `completeOnTimeout` thay đổi/trả về **cùng CompletableFuture** theo hợp đồng API, nên nhiều consumer chia sẻ một future có thể bị ảnh hưởng bởi timeout đó. Khi không muốn thay đổi nguồn, tạo stage riêng một cách có chủ đích, nhưng cần hiểu propagation/cancellation semantics của các stage.

### Nếu bạn chờ Future trong request thread

Một lời gọi `@Async` rồi `future.get()` ngay tại controller có thể làm cả request chờ. Có thể có lý do khi cần giới hạn timeout và trả kết quả trong request, nhưng hãy đo thread occupancy và deadline. Nếu ứng dụng dùng cơ chế HTTP asynchronous response, cân nhắc trả `CompletableFuture` qua integration được framework hỗ trợ thay vì tự block; đó là chủ đề tương tác web riêng, không tự động áp cho mọi phương thức.

## 10. Mã Java 17+ độc lập để thực hành Future và CompletableFuture

Ví dụ dưới đây dùng `ExecutorService` thuần Java, **không dùng Spring**, nhằm kiểm chứng chắc chắn semantics `Future`, `CompletableFuture` và một task không trả kết quả cho caller. Sau đó sẽ đối chiếu với `@Async` trong Spring.

Tệp **FutureModesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureModesDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "ready";
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            System.out.println("pending=" + !future.isDone());
            release.countDown();
            System.out.println("future=" + future.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> doubled =
                    CompletableFuture.supplyAsync(() -> 21, executor)
                            .thenApply(value -> value * 2);
            System.out.println("composed=" + doubled.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> failed =
                    CompletableFuture.supplyAsync(() -> {
                        throw new IllegalArgumentException("invalid");
                    }, executor);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println(
                        "cause=" + ex.getCause().getClass().getSimpleName());
            }

            CountDownLatch voidCompleted = new CountDownLatch(1);
            executor.execute(voidCompleted::countDown);
            if (!voidCompleted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Void task did not finish");
            }
            System.out.println("voidTaskDone=true");
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FutureModesDemo.java
java FutureModesDemo
~~~

Stdout xác định trong điều kiện chạy thành công:

~~~text
pending=true
future=ready
composed=42
cause=IllegalArgumentException
voidTaskDone=true
~~~

Giải thích:

1. `started.await()` chứng minh task đã được worker nhận và đang chờ `release`, nên khi đọc `future.isDone()` kết quả chưa thể hoàn tất: `pending=true`.
2. `release.countDown()` cho phép worker trả `"ready"`, `future.get(5,...)` trả giá trị đúng.
3. `supplyAsync` chạy một phép tính trong executor được truyền vào; `thenApply` biến `21` thành `42`.
4. Một phép tính ném `IllegalArgumentException` khiến future hoàn thành exceptionally; `join()` bọc lỗi trong `CompletionException`, cause phản ánh lỗi gốc.
5. Task truyền cho `execute` không có giá trị trả về; ví dụ dùng latch độc lập để xác minh `voidTaskDone=true`, vì bản thân `execute` không cung cấp Future.

Nếu chuyển sang Spring, phần `@Async` đóng vai trò đưa lời gọi method qua proxy và gửi task tới executor, còn hợp đồng `Future`/`CompletableFuture` của JDK vẫn được dùng để quan sát kết quả. **Đừng copy nguyên `supplyAsync` vào mọi `@Async` method chỉ vì đây là demo Java thuần.**

## 11. Cấu hình Spring cho ví dụ ba kiểu trả về

Dưới đây là cấu hình gọn cho một ứng dụng Spring Framework có `spring-context`. Kích thước thread pool chỉ để minh họa; khi triển khai thực phải đo tải và giới hạn queue/rejection cho phù hợp.

Tệp **LessonAsyncConfig.java**:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class LessonAsyncConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("lesson-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Tệp **LessonAsyncService.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class LessonAsyncService {

    @Async("lessonExecutor")
    public void publishNotice(String text) {
        if (text.isBlank()) {
            throw new IllegalArgumentException("blank notice");
        }
        System.out.println("Notice: " + text);
    }

    @Async("lessonExecutor")
    public Future<String> loadName(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("invalid id");
        }
        return CompletableFuture.completedFuture("user-" + id);
    }

    @Async("lessonExecutor")
    public CompletableFuture<Integer> calculateScore(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value");
        }
        return CompletableFuture.completedFuture(value * 10);
    }
}
~~~

Đây là **hai file Java Spring riêng**, không có `main` và cần được Spring component-scan/import từ một ApplicationContext. Nhờ `@EnableAsync` và `@Async("lessonExecutor")`, lời gọi qua bean proxy sẽ submit công việc vào executor có tên `lessonExecutor`. `publishNotice` phù hợp cho demo tác vụ không kết quả; `loadName` trả giá trị thông qua Future; `calculateScore` trả CompletableFuture để tiếp tục composition. Ví dụ cố ý đơn giản nên không chứa truy vấn database hay side effect cần bền vững.

Tệp **LessonAsyncConsumer.java** cho một bean khác gọi service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class LessonAsyncConsumer {

    private final LessonAsyncService worker;

    public LessonAsyncConsumer(LessonAsyncService worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> start(int id) {
        return worker.calculateScore(id)
                .thenApply(score -> "score=" + score);
    }
}
~~~

`start(3)` cho caller một future mà khi hoàn thành thành công có giá trị `"score=30"`. Nó không gọi `get()` hay `join()` trong service, nên không tự block để chờ kết quả. Mỗi file có tên class đúng như ví dụ. Khi chạy trong Spring Boot, cần đặt chúng trong package được component-scan, hoặc khai báo/import bean tương ứng.

**Để dùng kiểu Future thường:** một bean khác có thể gọi `worker.loadName(3)` rồi `get(timeout)` ở ranh giới thật sự cần giá trị. Không gọi `get` ngay trong cùng worker thread khi việc chờ phụ thuộc vào task khác đang chờ chính pool đó; với pool nhỏ, có thể xảy ra starvation hoặc deadlock.

## 12. “Future tạm” và “Future của proxy” không phải một đối tượng

Một điểm thường gây hiểu sai là code target:

~~~java
@Async("lessonExecutor")
public CompletableFuture<String> greeting() {
    String value = slowOperation();
    return CompletableFuture.completedFuture(value);
}
~~~

`slowOperation()` ở đây là **method giả định** được gọi trong worker của executor; đoạn này không độc lập. Có hai giai đoạn:

1. **Caller** gọi proxy `greeting()`; Spring tạo/gửi một task và trả về **Future đại diện cho công việc đó**.
2. **Worker** chạy target method, gọi `slowOperation()`, tạo `completedFuture(value)` tạm. Spring lấy giá trị/trạng thái từ handle tạm rồi hoàn thành handle đại diện mà caller đang giữ.

Trong một hệ thống có công việc chạy lâu, caller có thể thấy `future.isDone()==false` ngay cả khi dòng `return CompletableFuture.completedFuture(value)` xuất hiện trong code target. Dòng return chưa chạy cho đến khi work bên trong method hoàn tất.

Cần tránh sai lầm “Spring @Async vô dụng vì method trả completedFuture”. `completedFuture` đúng vai trò **thỏa chữ ký ở target**, còn việc gọi qua proxy mới tạo hợp đồng async cho client.

Nếu tự gọi `this.greeting()` trong chính class target, **proxy bị bỏ qua**; lúc này bạn nhận trực tiếp completedFuture do target tạo, và `slowOperation()` chạy ngay trên thread gọi, không có tính async như dự kiến.

## 13. Chaining đồng bộ hay bất đồng bộ: thenApply và thenApplyAsync

`CompletableFuture.thenApply(fn)` không yêu cầu tạo thread mới. Callback có thể chạy trên thread hoàn thành stage trước hoặc thread đăng ký callback khi stage đã hoàn tất; không dựa vào tên thread cụ thể. Nếu callback nặng, nó có thể chiếm worker đang hoàn thành việc khác.

`thenApplyAsync(fn)` lịch callback sang một executor. Nếu **không truyền executor**, Java thường sử dụng `ForkJoinPool.commonPool` cho async completion methods; điều này có thể khác pool `@Async` đã cấu hình.

~~~java
CompletableFuture<String> formatted =
        worker.calculateScore(3)
                .thenApplyAsync(
                        score -> "score=" + score,
                        formattingExecutor);
~~~

Đây là đoạn minh họa trong bean có `worker` và `formattingExecutor` (kiểu `Executor`) được inject. Khi chọn executor riêng, bạn phải quản lý pool size, queue, rejection, shutdown và context propagation ở **cả hai**. Nếu callback ngắn, `thenApply` có thể đủ. Nếu callback blocking hoặc CPU nặng, cân nhắc `thenApplyAsync` với executor phù hợp.

Không mặc định rằng `thenApplyAsync` luôn nhanh hơn; nó có thêm chi phí scheduling, có thể gặp `RejectedExecutionException` khi executor dùng để chạy callback không nhận việc, và có thể tăng tổng concurrency ngoài dự kiến.

## 14. @Async và transaction, ThreadLocal, MDC

Thực thi trên thread khác có nghĩa nhiều ngữ cảnh gắn với thread gửi **không tự kế thừa**:

- Transaction resource/`@Transactional` thường gắn với thread; method `@Async` chạy trong thread riêng không tự thừa hưởng transaction của caller. Nếu cần transaction riêng ở worker, định nghĩa boundary phù hợp cho công việc đó.
- Security context, MDC/trace context và các `ThreadLocal` khác thường cần truyền theo cách có chủ đích (`TaskDecorator`, cơ chế của framework, hoặc dữ liệu bất biến qua tham số).
- Một callback `thenApply` có thể chạy ở thread khác với chỗ đăng ký; đừng dùng ThreadLocal ngầm để quyết định nghiệp vụ quan trọng.

Nếu gọi `@Async` trong một transaction trước khi commit, worker có thể chạy trước khi dữ liệu cần đọc đã commit. Với yêu cầu “chỉ làm sau khi giao dịch đã thành công”, cân nhắc after-commit event processing hoặc **transactional outbox** nếu cần độ bền khi ứng dụng crash.

Một lỗi khác: đặt `@Transactional` vào method `@Async` rồi nghĩ transaction của caller tự được truyền. Trên thực tế việc intercept, mở transaction và thread chạy phải được thiết kế/kiểm thử theo thứ tự advice; đừng dựa vào giả định.

## 15. Khi tải tăng: kiểu trả về không bảo đảm tác vụ được nhận

`@Async` cần executor đủ sức xử lý. Nếu pool bão hòa hoặc đã shutdown:

- `AbortPolicy` thường gây `TaskRejectedException` qua `ThreadPoolTaskExecutor` khi submit; caller phải xử lý tình huống **không nhận được việc**, và có thể chưa có `Future` nào để đợi.
- `CallerRunsPolicy` có thể làm tác vụ chạy **ngay trên caller thread** khi pool bão hòa: kể cả method có `@Async`, việc gọi có thể mất thời gian tương ứng với body, phá kỳ vọng phản hồi nhanh.
- `DiscardPolicy` có thể bỏ task im lặng; `Future` có thể không bao giờ hoàn thành nếu bị discard mà không hủy.
- Khi shutdown, `CallerRunsPolicy` có thể bỏ task im lặng theo JDK, không chạy trên caller nữa.

**Không nhầm một `Future` với lời hứa bền vững.** Một task được nhận vào queue RAM có thể mất khi tiến trình chết. Nếu cần đảm bảo xử lý báo cáo, thông báo quan trọng hoặc đơn hàng, dùng job table/queue bền vững, retry, idempotency và trạng thái để truy vấn.

Đặc biệt với HTTP 202 Accepted: chỉ xác nhận “đã nhận” ở mức mà ứng dụng thật sự bảo đảm. Nếu không có job store bền vững thì response không nên hứa chắc sẽ xử lý sau restart.

## 16. Test @Async có đáng tin hay không?

Đừng dùng `Thread.sleep(100)` rồi giả định worker đã hoàn thành. Các phương án tốt hơn:

1. **Đúng proxy**: inject bean có `@Async` từ bean/test khác; không gọi trực tiếp method trên `new LessonAsyncService()` rồi tưởng đã kiểm thử Spring.
2. **Future/CompletableFuture**: kiểm tra giá trị bằng `get(timeout, unit)` để test không treo; assert nguyên nhân lỗi khi `get` ném `ExecutionException` hoặc `join` ném `CompletionException`.
3. **void**: dùng `CountDownLatch` hoặc một recorder thread-safe/metric để xác nhận completion; kiểm thử đường `AsyncUncaughtExceptionHandler` riêng.
4. **Lỗi submit**: tạo pool 1 worker + queue 1, dùng latch giữ worker để bảo đảm queue đầy, sau đó submit thêm và xác minh rejection tại caller.
5. **Timeout/cancel**: khống chế bằng latch, xác định future chuyển trạng thái thế nào và task thực sự có dừng hay không.
6. **Thread context**: xác minh transaction/MDC/security context theo cả đường worker, caller-runs hoặc callback thread đã chọn.
7. **Shutdown**: kiểm thử đã nhận nhưng chưa chạy, hủy, drain queue và retry từ nơi lưu bền vững.

Ví dụ JUnit 5 **minh họa** (cần lớp Spring bean, test context và imports tương ứng):

~~~java
CompletableFuture<Integer> task = lessonAsyncService.calculateScore(4);
assertEquals(40, task.get(2, TimeUnit.SECONDS));

CompletableFuture<Integer> bad = lessonAsyncService.calculateScore(-1);
ExecutionException error = assertThrows(
        ExecutionException.class,
        () -> bad.get(2, TimeUnit.SECONDS));
assertInstanceOf(IllegalArgumentException.class, error.getCause());
~~~

Ví dụ cần `assertEquals`, `assertThrows`, `assertInstanceOf` từ JUnit Jupiter và biến `lessonAsyncService` được inject **qua Spring context**. Đây không phải file JUnit đầy đủ, nên không có lệnh `javac` độc lập. Mục tiêu là assert kết quả/lỗi thay vì phụ thuộc thời gian ngủ.

## 17. Lỗi phổ biến và cách sửa

1. **Đánh dấu `@Async` rồi khai báo trả `String`.** Kiểu trả về không phù hợp với interceptor; trả `Future<String>` hoặc `CompletableFuture<String>`.
2. **Không bật `@EnableAsync`, không dùng Spring bean hoặc gọi nội bộ `this.method()`.** Proxy không chạy, lời gọi có thể trở thành đồng bộ.
3. **Dùng `void` cho công việc cần biết kết quả.** Caller không nhận tín hiệu; thay bằng Future hoặc job status bền vững.
4. **Cho rằng exception của `@Async void` sẽ ném về controller như lỗi đồng bộ.** Lỗi body đi qua `AsyncUncaughtExceptionHandler` trong đường thông thường.
5. **Gọi `get()` ngay sau submit tại request thread.** Caller lại bị block; chỉ chờ khi thật sự cần và dùng deadline.
6. **Không xử lý `InterruptedException` đúng cách.** Thường khôi phục cờ bằng `Thread.currentThread().interrupt()` nếu không ném tiếp, rồi hủy/thoát theo hợp đồng.
7. **Đánh đồng `isDone()` với thành công.** Future hoàn thành lỗi hoặc bị hủy vẫn có thể `isDone()==true`.
8. **Nhầm `TimeoutException` với việc worker bị dừng.** Timeout của người chờ không tự hủy hoặc rollback task.
9. **Nhầm `cancel(true)` của `CompletableFuture` với interrupt chắc chắn.** Tham số này không điều khiển interruption như một `FutureTask` truyền thống.
10. **Dùng `supplyAsync` bên trong mọi `@Async` method.** Có thể tạo scheduling hai tầng và dùng nhầm commonPool.
11. **Dùng `thenApply` cho hàm trả Future rồi nhận Future lồng nhau.** Dùng `thenCompose` khi bước sau cũng async.
12. **Dùng `exceptionally` trả fallback cho mọi lỗi và che mất sự cố nghiệp vụ.** Fallback phải được thiết kế, log/metric và phân loại hợp lý.
13. **Block `join()` trong callback chạy trên executor ít thread.** Có thể chặn toàn bộ pool khi đang đợi task cũng cần chính pool đó.
14. **Dựa vào context/transaction của request trong worker.** Thread-bound state không tự truyền theo.
15. **Bỏ qua `TaskRejectedException` ở ranh giới gọi.** Task có thể chưa được nhận; không trả “đã xử lý” giả.
16. **Mặc định CompletableFuture làm mọi thứ non-blocking.** Future là handle; body vẫn có thể block một worker, callback có thể chạy inline, `join/get` vẫn block caller.
17. **Không đo queue, active threads, timeout, completion failure.** Khi overload, biến động latency và lost task có thể xuất hiện trước khi metrics tổng thể báo vấn đề.
18. **Cho rằng một exception từ task Future sẽ đi qua `AsyncUncaughtExceptionHandler` như `void`.** Với Future, lỗi được lưu vào Future và nên được consumer xử lý.

## 18. Chọn kiểu nào trong thực tế?

| Yêu cầu | Kiểu phù hợp ban đầu | Lưu ý |
| --- | --- | --- |
| Ghi telemetry best-effort, không cần trả kết quả | `void` | Phải quan sát lỗi và chính sách mất event |
| Trả kết quả từ một API legacy cần chờ | `Future<T>` | Caller dùng `get(timeout)`; tránh block luồng nhạy latency |
| Biến đổi kết quả trong pipeline nhiều bước | `CompletableFuture<T>` | `thenApply/thenCompose` và xử lý exceptional completion |
| Ghép hai nguồn dữ liệu độc lập | `CompletableFuture<T>` | `thenCombine` hoặc `allOf`, quản lý lỗi cả hai nhánh |
| Hệ thống cần hủy/timeout rõ ràng | `Future` hoặc `CompletableFuture` cùng cancellation protocol | Handle không tự đảm bảo thread dừng hoặc side effect rollback |
| Job bắt buộc không mất qua restart | Job ID + durable queue/job store, có thể bổ sung `CompletableFuture` cho request hiện tại | Future trong RAM không phải nguồn sự thật |
| API muốn trả kết quả HTTP bất đồng bộ | `CompletableFuture<T>` trong integration phù hợp | Cần xét behavior web framework và deadline client |

Không có kiểu trả về duy nhất phù hợp cho mọi bài toán. Lựa chọn nên dựa trên **nghĩa của kết quả**, **ai phải biết lỗi**, **cách caller chờ hay compose**, **deadline**, và **hợp đồng khi task không được executor tiếp nhận**.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `@Async public String load()` không phải một chữ ký trả kết quả bất đồng bộ hợp lệ của Spring proxy?
2. Với `@Async void`, exception trong worker được quan sát ở đâu? Vì sao controller thường không bắt được trực tiếp?
3. Bên trong target method, tại sao có thể trả `CompletableFuture.completedFuture(value)` nhưng caller vẫn nhận Future chưa hoàn thành?
4. `Future.get(2, SECONDS)` timeout có chắc task đã dừng không?
5. Sự khác nhau giữa `Future.get()` và `CompletableFuture.join()` về kiểu exception khi task lỗi là gì?
6. Khi nào dùng `thenCompose` thay vì `thenApply`?
7. Vì sao `CompletableFuture.supplyAsync(...)` không truyền executor trong method đã `@Async` có thể làm code khó kiểm soát?
8. Nếu `@Async("lessonExecutor")` bị pool rejection trước khi submit, Future sẽ xuất hiện ở caller không? Bạn sẽ báo lỗi thế nào?
9. Vì sao gọi `this.calculateScore(3)` trong cùng bean không chứng minh method chạy async?
10. Nếu method `@Async CompletableFuture` cần transaction và truy cập security context, bạn kiểm tra những ranh giới nào?
11. `CompletableFuture.cancel(true)` có đảm bảo ngắt một HTTP call đang chạy không?
12. Với job cần bảo đảm hoàn thành sau khi ứng dụng restart, Future phải kết hợp thêm thành phần nào?

## 20. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.1 — @Async API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework 6.1 — @EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.1 — AsyncConfigurer API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/annotation/AsyncConfigurer.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

**Ghi nhớ:** `void` không cho caller một kênh kết quả; `Future` cung cấp handle để chờ, xem trạng thái và hủy; `CompletableFuture` bổ sung composition và xử lý lỗi bằng callback. **`@Async` quyết định cách chuyển lời gọi qua executor, kiểu trả về quyết định hợp đồng quan sát kết quả.** Muốn có semantics đáng tin cậy, cần thêm timeout, error handling, thread context và admission/durability đúng yêu cầu nghiệp vụ.