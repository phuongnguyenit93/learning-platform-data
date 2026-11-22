# CompletableFuture, callback và truyền lỗi về phía kiểm thử

Trong Spring Boot, chương trình bất đồng bộ thường trả về một `CompletableFuture`, đăng ký callback bằng `thenApply`/`thenAccept`/`whenComplete` hoặc dùng `@Async` để chạy trên executor. Bẫy nguy hiểm là **test có thể PASS trước khi công việc kết thúc**. Một assertion ném lỗi trong callback ở thread khác không tự động làm JUnit test thất bại nếu test không **đợi và kiểm tra đúng completion stage**.

Ví dụ một test sai:

```java
@Test
void testXanhGia() {
    CompletableFuture.supplyAsync(() -> "wrong")
            .thenAccept(value -> assertEquals("expected", value));

    // Test method kết thúc ngay; chưa có ai quan sát future
    // của thenAccept. AssertionError có thể bị giữ trong
    // exceptional completion của stage bị bỏ rơi.
}
```

Mã trên chỉ là snippet để minh họa anti-pattern (cần imports). Cách đúng là **giữ stage trả về từ callback** và đợi stage đó hoàn thành bằng `get(timeout, unit)`, hoặc dùng `join()` với một deadline được quản lý rõ:

```java
@Test
void testThucSuChoCallback() throws Exception {
    CompletableFuture<Void> checked =
            CompletableFuture.completedFuture("expected")
                    .thenAccept(value ->
                            assertEquals("expected", value));

    checked.get(5, TimeUnit.SECONDS);
    // Nếu callback ném AssertionError, get() ném
    // ExecutionException và JUnit báo test FAILED.
}
```

Bài thuộc nhóm **Bất đồng bộ và lịch chạy** của **Spring Boot - testing**. Ta sẽ học các phép ghép `CompletableFuture`, semantics callback khi thành công/thất bại, cách nhận lỗi bằng `get` và `join`, điều gì bị che bởi `exceptionally`/`handle`, timeout/cancellation, proxy `@Async`, executor và scheduled jobs. Phần thực hành có dự án **Java 17 + Spring Boot 3.5 + JUnit Jupiter**, gồm các unit tests thuần Java và integration tests với Spring `@Async` thật, **không cần Docker hay truy cập Internet**.

## 1. CompletableFuture khác Thread và Future truyền thống như thế nào?

`CompletableFuture<T>` vừa là một `Future<T>` (có thể chờ kết quả) vừa là một `CompletionStage<T>` (có thể ghép các bước xử lý). Nó có các trạng thái quan sát được:

- **Incomplete**: chưa có kết quả. `isDone() == false`.
- **Completed normally**: có giá trị, kể cả giá trị `null`; `get()/join()` trả giá trị.
- **Completed exceptionally**: lỗi được lưu trong future. `get()/join()` ném exception tương ứng.
- **Cancelled**: trạng thái hủy, cũng được xem là exceptional completion; `isCancelled() == true`.

`isDone() == true` **không đồng nghĩa thành công**: một future bị exception hoặc cancel cũng đã kết thúc. Để biết outcome phải quan sát `get()/join()`, `isCompletedExceptionally()` hoặc kiểm định stage đã được kết thúc hợp lệ.

```text
CompletableFuture<T>
       |
       +-- incomplete
       |       |
       |       +-- complete(value) ------------> normal completion
       |       |
       |       +-- completeExceptionally(ex) --> exceptional completion
       |       |
       |       +-- cancel(...) ----------------> cancelled
       |
       +-- dependent stages:
               thenApply / thenCompose / thenCombine
               thenAccept / whenComplete
               exceptionally / handle
```

Một stage có thể hoàn thành bất đồng bộ do executor/thread khác thực thi hoặc được hoàn tất ngay bởi code gọi `complete`. `thenApply` **không bảo đảm chạy trên thread riêng**: callback có thể chạy trong thread hoàn tất upstream hoặc thread đăng ký callback nếu stage đã xong. Dùng `thenApplyAsync` với một `Executor` được chỉ định khi cần kiểm soát nơi chạy, và nhớ rằng overload `Async` không truyền executor thường dùng default asynchronous facility (hay common pool trong CompletableFuture tiêu chuẩn).

**Không đồng nhất CompletableFuture với Spring `@Async`**:

- `CompletableFuture.supplyAsync(...)` dùng Java executor, không cần Spring.
- `@Async` là AOP/proxy interceptor của Spring; method được gửi tới Spring `TaskExecutor` khi được gọi qua proxy.
- Một method `@Async` có thể **trả về `CompletableFuture.completedFuture(...)` ở bên trong worker thread**. Caller nhận một future đại diện việc executor thực thi, không phải “đã xong ngay vì nội bộ trả completedFuture”.
- `@Scheduled` là cơ chế gọi task theo lịch, không tự đưa lỗi vào future trả về cho một JUnit test.

## 2. Lỗi ở một stage lan truyền thế nào?

### 2.1. Pipeline thành công

```java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("  order-7  ")
                .thenApply(String::trim)
                .thenApply(String::toUpperCase);

assertEquals("ORDER-7", ready.join());
```

Các callback `thenApply` chỉ chạy khi upstream hoàn thành bình thường. Nếu có stage upstream lỗi, các callback `thenApply` phía sau **không chạy** và dependent stage thường cũng exceptional completion. Nếu chính callback throw, lỗi không nhất thiết xuất hiện tại dòng đăng ký callback; nó được giữ trong **stage được trả về**.

### 2.2. Callback tự throw

```java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("invoice-A");

CompletableFuture<String> mapped =
        source.thenApply(value -> {
            throw new IllegalArgumentException("mapping-invalid");
        });

assertEquals("invoice-A", source.join());

CompletionException failure = assertThrows(
        CompletionException.class, mapped::join);
assertInstanceOf(
        IllegalArgumentException.class, failure.getCause());
```

**Lỗi thuộc stage nào?** `source` vẫn thành công; **`mapped`** thất bại. Nếu test chỉ gọi `source.join()` rồi bỏ qua `mapped`, assertion ở callback hoặc lỗi mapping sẽ bị che khuất. Đây là cơ chế phổ biến gây test xanh giả.

### 2.3. `thenApply`, `thenCompose`, `thenCombine`

| API | Khi chạy? | Kết quả | Khi upstream lỗi |
|---|---|---|---|
| `thenApply(fn)` | Upstream thành công | `CompletableFuture<U>` của giá trị chuyển đổi | Callback không chạy; downstream exception |
| `thenAccept(consumer)` | Upstream thành công | `CompletableFuture<Void>` | Callback không chạy; downstream exception |
| `thenRun(runnable)` | Upstream thành công | `CompletableFuture<Void>` | Callback không chạy; downstream exception |
| `thenCompose(fn)` | Upstream thành công | Flatten một stage tiếp theo thành một future | Chuỗi lỗi được chuyển tiếp |
| `thenCombine(other, fn)` | Hai upstream cùng thành công | Ghép kết quả của hai stages | Nếu một lỗi, combined stage lỗi |
| `allOf(stages...)` | Tất cả stages hoàn tất | `CompletableFuture<Void>`, không chứa danh sách kết quả | Nếu có stage lỗi, allOf hoàn tất exceptionally |
| `anyOf(stages...)` | Stage đầu tiên hoàn tất | `CompletableFuture<Object>` | Có thể thành công hoặc lỗi tùy stage đầu tiên |

`thenCompose` thường được dùng khi callback trả thêm một `CompletableFuture` và bạn không muốn có kiểu `CompletableFuture<CompletableFuture<T>>`:

```java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("O-1")
                .thenCompose(id ->
                        CompletableFuture.completedFuture("DONE:" + id));
assertEquals("DONE:O-1", result.join());
```

Dùng `allOf` khi muốn đợi **tất cả nhánh**, nhưng phải xử lý một nhánh lỗi và thu kết quả từng nhánh sau đó. Đừng tự giả định `allOf` trả về `List<T>` hoặc dừng mọi task còn lại ngay khi một nhánh fail. Kiểm tra từng stage và có deadline khi cần.

## 3. `get`, `join`, `ExecutionException` và `CompletionException`

Đây là phần đặc biệt quan trọng trong JUnit.

| Phương thức | Khi bình thường | Khi stage lỗi | Timeout? | Checked exceptions |
|---|---|---|---|---|
| `future.get()` | Trả T, chờ vô hạn nếu chưa xong | `ExecutionException` có `getCause()` là lỗi nguồn | Không | `InterruptedException`, `ExecutionException` |
| `future.get(5, SECONDS)` | Trả T trước deadline | `ExecutionException` | **Có**, ném `TimeoutException` nếu chỉ hết thời gian chờ | Thêm `TimeoutException` |
| `future.join()` | Trả T, chờ vô hạn nếu chưa xong | Thường `CompletionException` có cause gốc | Không | Không bắt buộc khai báo checked |
| `future.orTimeout(...).join()` | Kết quả hoặc lỗi gốc | `CompletionException` (có thể cause là TimeoutException) | Có, **thay đổi trạng thái future** | Unchecked |
| `future.completeOnTimeout(default, ...)` | Kết quả hoặc fallback | Có thể hoàn thành **bình thường** bằng fallback | Có, **hoàn thành future bằng giá trị** | Không |

### 3.1. JUnit với `get(timeout)`

```java
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalStateException("no-stock"));

ExecutionException error = assertThrows(
        ExecutionException.class,
        () -> failed.get(5, TimeUnit.SECONDS));

assertInstanceOf(
        IllegalStateException.class, error.getCause());
assertEquals("no-stock", error.getCause().getMessage());
```

`failedFuture` có từ Java 9. Dùng `get(timeout)` giúp lỗi thực sự xuất hiện **trong test thread** và không để test treo vô hạn nếu producer không bao giờ complete. Khi callback ném `AssertionError`, `get` vẫn có thể ném `ExecutionException`, nguyên nhân là assertion failure.

### 3.2. JUnit với `join()`

```java
CompletionException error = assertThrows(
        CompletionException.class,
        () -> CompletableFuture.<String>failedFuture(
                new IllegalStateException("no-stock")).join());

assertInstanceOf(
        IllegalStateException.class, error.getCause());
```

`join` tiện cho code nhưng **không có timeout mặc định**; test tích hợp với hệ mạng/scheduler không nên dùng một `join` vô thời hạn. Có thể dùng `get(5, SECONDS)` ở boundary test, hoặc `orTimeout(5, SECONDS)` khi **muốn chính future đó** hoàn thành exceptionally vì deadline.

### 3.3. Gỡ lớp wrapper đúng cách

Một chuỗi Future/stage có thể bọc exception trong `CompletionException` hoặc `ExecutionException`. Có thể có nhiều lớp wrapper khi code bắt rồi ném lại. Đừng hardcode một stack trace string hay luôn ép `getCause().getCause()` nếu API có thể thay đổi.

```java
static Throwable unwrap(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Snippet cần imports `java.util.concurrent.CompletionException` và `ExecutionException`. Chỉ gỡ đúng loại wrapper cần thiết; đừng nuốt toàn bộ `Throwable` một cách mù quáng. Trong demo dưới đây ta assert trực tiếp các causes biết trước, thay vì ẩn failure sau helper phức tạp.

### 3.4. Phân biệt timeout chờ và timeout của computation

`future.get(100, MILLISECONDS)` ném `TimeoutException` **cho người đợi**, nhưng future **có thể vẫn đang chạy**; sau đó gọi `get(5, SECONDS)` có thể trả kết quả.

`future.orTimeout(100, MILLISECONDS)` đặt lịch **complete chính future đó exceptionally** nếu chưa xong. Nó không bảo đảm hủy TCP operation hay interrupt worker đang tính.

`future.completeOnTimeout("fallback", 100, MILLISECONDS)` hoàn thành **chính future** bằng giá trị fallback khi trễ; vì thế test nhận fallback và future không báo lỗi, nhưng backend/worker vẫn có thể tiếp tục tạo side effects. Đừng dùng fallback để tuyên bố một request đã được hủy hoặc rollback.

`cancel(true)` đối với `CompletableFuture` đặt trạng thái cancelled nếu chưa xong, nhưng Java 17 Javadoc nói `mayInterruptIfRunning` **không có tác dụng interrupt trong implementation này**. Muốn dừng tài nguyên thật phải thiết kế cancellation/interrupt/timeout ở executor, HTTP/DB client và business layer.

## 4. Callback quan sát, callback chuyển đổi và callback phục hồi

### 4.1. `whenComplete`: quan sát, không phải recovery

`whenComplete((value, error) -> ...)` nhận cả thành công và lỗi. Nó trả về **một stage mới** có cùng outcome như upstream nếu callback không throw. Nếu callback throw khi upstream đã thành công, **stage trả về** hoàn thành exceptionally vì lỗi callback. Nếu upstream vốn lỗi rồi callback lại throw, theo Java 17 API, outcome lỗi của upstream **được ưu tiên** trong returned stage.

```java
CompletableFuture<String> upstream =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> observed =
        upstream.whenComplete((value, failure) -> {
            if (failure == null) {
                throw new IllegalArgumentException("observer-broken");
            }
        });

assertEquals("OK", upstream.join());

CompletionException error = assertThrows(
        CompletionException.class, observed::join);
assertInstanceOf(
        IllegalArgumentException.class, error.getCause());
```

**Sai thường gặp:** gọi `upstream.whenComplete(logOrAssert)` rồi bỏ result, sau đó chỉ `upstream.join()`. Nếu callback ném lỗi, test sẽ không kiểm được stage lỗi của observer.

### 4.2. `exceptionally`: recover khi lỗi

```java
CompletableFuture<String> upstream =
        CompletableFuture.failedFuture(
                new IllegalStateException("gateway-down"));

CompletableFuture<String> recovered =
        upstream.exceptionally(ex -> "FALLBACK");

assertEquals("FALLBACK", recovered.join());
assertTrue(upstream.isCompletedExceptionally());
assertFalse(recovered.isCompletedExceptionally());
```

`exceptionally` tạo một **future mới đã thành công** nếu recovery function trả giá trị. Khi production code chỉ log và trả fallback, test chỉ assert fallback có thể che lỗi upstream nếu business bắt buộc phải fail. Hãy kiểm cả **lý do fallback có được phép không**, metric/retry/alerting và trạng thái service.

### 4.3. `handle`: chuyển cả success và failure

```java
CompletableFuture<String> outcome =
        CompletableFuture.<String>failedFuture(
                new IllegalArgumentException("bad-input"))
            .handle((value, error) ->
                    error == null ? "OK:" + value : "FAILED");

assertEquals("FAILED", outcome.join());
```

`handle` luôn chạy khi upstream hoàn tất (bình thường/lỗi), có thể chuyển lỗi thành giá trị thành công. Nếu chính handler ném exception, **returned stage** lại lỗi. Dùng `whenComplete` cho logging/metrics/observation; `handle` khi chủ đích biến outcome thành giá trị; `exceptionally` khi chỉ muốn recovery ở nhánh lỗi.

### 4.4. `thenAccept` và assertion trong callback

Một assertion JUnit ném `AssertionError`, không phải `Exception` thông thường; CompletableFuture sẽ complete dependent stage exceptionally.

```java
CompletableFuture<Void> checked =
        CompletableFuture.completedFuture("actual")
                .thenAccept(value ->
                        assertEquals("expected", value));

// BẮT BUỘC chờ stage returned từ thenAccept.
ExecutionException failure = assertThrows(
        ExecutionException.class,
        () -> checked.get(5, TimeUnit.SECONDS));
assertInstanceOf(AssertionError.class, failure.getCause());
```

Đây là **một test có chủ đích mong callback fail**, không phải khuyến nghị dùng assertion sai. Trong test thông thường, viết assertion đúng và gọi `checked.get(5, SECONDS)`; lúc ấy callback thất bại làm test fail tự nhiên.

## 5. Tránh false positive khi test bất đồng bộ

### 5.1. Một `@Test void` kết thúc không đồng nghĩa worker đã kết thúc

```java
@Test
void khongNenViet() {
    service.runAsync().thenAccept(result -> {
        assertEquals("expected", result);
    });
    // Không chờ returned future -> JUnit có thể báo PASS sai.
}
```

Mã này là anti-pattern (service giả định). Khi test method return, JUnit coi body đã chạy xong. Nó không tự join mọi future, không đợi thread pool rỗng và không tự nhận lỗi của callback bị bỏ đi.

Cách đúng:

```java
@Test
void dung() throws Exception {
    CompletableFuture<Void> assertionStage =
            service.runAsync().thenAccept(result ->
                    assertEquals("expected", result));

    assertionStage.get(5, TimeUnit.SECONDS);
}
```

### 5.2. Dùng `CountDownLatch` thay vì ngủ để đoán

Để test một task đang bị chặn, dùng **hai latch**:

```text
JUnit thread                Worker thread
     |                           |
     +--- call async method ---->|
     |                           +-- started.countDown()
     |                           +-- release.await()
     |
     +--- started.await(...)  <--+
     +--- assert get(timeout) throws TimeoutException
     +--- release.countDown() ---> worker resumes
     +--- assert get(5s) returns actual result
```

Điểm mạnh: test biết worker **đã vào vùng cần kiểm** trước khi thử timeout. Dùng `finally` để release latch ngay cả khi assertion fail, tránh worker treo và ảnh hưởng các tests sau. Chỉ sử dụng timeout có giới hạn; không sleep 2 giây chỉ để “chắc worker đã chạy”.

### 5.3. `assertTimeoutPreemptively` không phải giải pháp mặc định

JUnit `assertTimeoutPreemptively` có thể chạy executable ở thread khác, tạo vấn đề với Spring TestContext dùng **ThreadLocal-bound test-managed transaction**: thao tác DB của thread mới có thể không tham gia transaction rollback của test thread. Với Spring integration tests, thường nên dùng **future.get(timeout)** để chờ trên test thread, hoặc `assertTimeout` (non-preemptive) cho code chắc chắn có thể kết thúc.

`assertTimeout` không cắt sớm được một operation bị treo vô hạn; vì vậy với async/network call nên dùng **deadline ở future/client** thay vì chỉ timeout assertion bên ngoài.

### 5.4. Không coi một đếm ngược latch là lỗi đã được truyền

`latch.countDown()` chỉ đánh dấu một sự kiện. Nó không tự truyền `Throwable` của worker. Với callback cần test, tốt hơn đưa outcome vào `CompletableFuture` rồi await stage. Nếu chỉ có callback-style API, tạo một future bridge:

```java
CompletableFuture<String> bridge = new CompletableFuture<>();

legacyApi.fetch(
        value -> bridge.complete(value),
        error -> bridge.completeExceptionally(error));

assertEquals("value", bridge.get(5, TimeUnit.SECONDS));
```

Đây là snippet: `legacyApi` là API giả định có callbacks success/error; không chạy độc lập. Bridge nên có timeout và exactly-once completion policy; nếu API có callback trả về nhiều lần, chỉ một lần `complete` thành công. Nếu callback có thể bị gọi từ event-loop, không block event-loop bằng `join()` bên trong callback.

## 6. Spring `@Async`: proxy, executor và lỗi thật

### 6.1. Khi nào `@Async` có hiệu lực?

Trong Spring Boot, `@EnableAsync` kích hoạt async interception. Một public Spring bean method được gọi **qua Spring proxy** có thể được submit vào executor:

```text
JUnit / Controller
      |
      v
Injected Spring bean proxy
      |
      v
@Async("demoExecutor")
      |
      +--- returns CompletableFuture<T> to caller
      |
      v
TaskExecutor worker thread
      |
      +--- perform business operation
      +--- return CompletableFuture.completedFuture(value)
      |    or throw IllegalStateException
      |
      +--- proxy future complete normally/exceptionally
```

Nếu gọi `this.asyncMethod()` ngay trong cùng bean khi sử dụng Spring AOP proxy mode, call thường **bypass proxy**, không được gửi đi bất đồng bộ. Tương tự `new AsyncGateway()` không nhận Spring interception. Test cần inject bean từ context và gọi qua bean hoặc bean khác.

### 6.2. Nên trả Future/CompletableFuture thay vì `void` khi caller cần biết lỗi

Theo tài liệu Spring Framework, method `@Async` có return type `Future` (hoặc `CompletableFuture`) có thể truyền lỗi qua future. Với **`@Async void`**, exception không thể gửi ngược qua return value; Spring dùng `AsyncUncaughtExceptionHandler` để ghi log/xử lý exception, mặc định thường log.

```java
@Async("demoExecutor")
public void fireAndForget() {
    throw new IllegalStateException("async-void-failed");
}
```

Đây là snippet trong Spring bean, **không** phải standalone class. Một test chỉ gọi `bean.fireAndForget()` rồi kết thúc **không có future để await**. Nếu contract yêu cầu phát hiện lỗi, đổi API thành `CompletableFuture<Void>` hoặc truyền event/result sink được đồng bộ rõ; nếu bắt buộc `void`, đăng ký `AsyncUncaughtExceptionHandler` có sink test và đợi sink bằng latch/future, không dựa vào log stdout.

### 6.3. Tránh vô tình dùng executor không kiểm soát

- Định nghĩa executor bean với tên rõ và gọi `@Async("demoExecutor")`.
- Cấu hình core/max pool size, queue capacity, thread name, rejection và shutdown policy phù hợp môi trường.
- Không dùng unbounded queue/pool vô tội vạ trong production.
- Nếu executor bị bão hòa, lỗi submit/rejection có thể xuất hiện **ngay tại lời gọi** hoặc được thể hiện qua future tùy phiên bản/setup. Test cần kiểm theo contract thật và log queue metrics.
- `thenApplyAsync` không truyền executor có thể sử dụng default/common pool thay vì `demoExecutor` của Spring. Nếu cần cùng executor, truyền explicit `Executor` vào stage async.
- Khi context đóng, dọn executor/threads; không để thread không dừng làm Maven test runner treo.

### 6.4. Context không tự truyền giữa các threads

Spring transaction thường thread-bound; `@Async` chạy thread khác nên **không tự kế thừa transaction của caller**. `SecurityContext`, MDC/tracing, RequestContext và ThreadLocal khác cũng không tự được bảo đảm. Nếu cần, dùng cơ chế propagation chính thức (`TaskDecorator`, security-aware executor, explicit context), hoặc truyền business ID vào method. Đừng dựa vào một test cùng-thread để kết luận behavior thread pool production.

Lỗi hay gặp là tạo test @Transactional, gọi async write, rồi mong test rollback xóa mọi DB row của worker. Không có guarantee này khi thread khác dùng transaction riêng. Cần test DB isolation/cleanup đúng.

### 6.5. `@Scheduled` và lỗi callback

Method `@Scheduled` thường không trả `CompletableFuture` cho JUnit test; exceptions của scheduled repeating tasks có thể bị scheduler error handler **log và suppress**, cho phép lần chạy sau tiếp tục. Test trực tiếp business service/future của job; dùng fake clock/controlled trigger hoặc in-memory scheduler khi cần kiểm lịch, không chờ mốc cron thật. Với fixed-rate/fixed-delay, kiểm failure recovery và không cho phép lỗi bị log rồi coi test PASS.

## 7. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.5 + JUnit Jupiter

Ví dụ có **Spring async proxy thật** và **unit tests của CompletionStage**:

- `AsyncGateway` chạy `@Async("demoExecutor")`, trả `CompletableFuture<String>`; có case thành công, throw và đợi latch.
- `OrderWorkflow` inject `AsyncGateway` từ container và tạo callbacks bằng `thenApply`/`whenComplete`/`exceptionally`/`handle`.
- `AsyncWorkflowIntegrationTest` kiểm Spring proxy, lỗi từ worker, lỗi callback, recovery, timeout chờ, và assertion callback được await.
- `CompletableFutureUnitTest` kiểm quy tắc Java thuần không cần Spring: composition, exception wrapping, observer exception, recovery, allOf, timeout và cancellation.
- Không có database/network ngoài; cả hai classes test chạy bằng `mvn test`.

### 7.1. Cây thư mục

```text
async-callback-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/asyncdemo/
    │   ├── AsyncDemoApplication.java
    │   ├── AsyncGateway.java
    │   └── OrderWorkflow.java
    └── test/java/com/example/asyncdemo/
        ├── AsyncWorkflowIntegrationTest.java
        └── CompletableFutureUnitTest.java
```

### 7.2. Maven POM

File **`pom.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-callback-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` cung cấp core Spring context/AOP infrastructure cho `@EnableAsync`; `spring-boot-starter-test` cung cấp JUnit Jupiter và assertion dependencies. Không cần Spring Web, database hay Testcontainers. Trong dự án khác, nếu dùng Spring Boot 4/Spring Framework 7, đối chiếu các module/test libraries tương ứng; ví dụ này cố định **Boot 3.5.0 + Java 17**.

### 7.3. Spring Boot application + executor bean

File **`src/main/java/com/example/asyncdemo/AsyncDemoApplication.java`**:

```java
package com.example.asyncdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncDemoApplication {

    @Bean("demoExecutor")
    ThreadPoolTaskExecutor demoExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("demo-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    public static void main(String[] args) {
        SpringApplication.run(AsyncDemoApplication.class, args);
    }
}
```

Spring quản lý lifecycle của bean `ThreadPoolTaskExecutor` (khởi tạo và destroy). `@Async("demoExecutor")` ở bean khác chỉ định rõ pool này, tránh phụ thuộc executor mặc định. Với production, chọn queue/pool/shutdown policy theo throughput/retry SLA; với test này tối đa hai worker đã đủ.

### 7.4. AsyncGateway: method thành công, exception và gate

File **`src/main/java/com/example/asyncdemo/AsyncGateway.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncGateway {

    @Async("demoExecutor")
    public CompletableFuture<String> authorize(
            String orderId, boolean fail) {

        if (fail) {
            throw new IllegalStateException(
                    "gateway-unavailable:" + orderId);
        }

        return CompletableFuture.completedFuture(
                "auth-" + orderId);
    }

    @Async("demoExecutor")
    public CompletableFuture<String> awaitGate(
            CountDownLatch started,
            CountDownLatch release) {

        started.countDown();

        try {
            if (!release.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("gate-timeout");
            }
            return CompletableFuture.completedFuture("released");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "worker-interrupted", interrupted);
        }
    }
}
```

Tại sao method `authorize` trả `completedFuture` trong worker? Spring `@Async` hỗ trợ method trả Future/CompletableFuture để proxy gửi execution sang executor; body method có thể tạo completedFuture ở worker, còn **caller-side proxy future** sẽ complete sau khi worker hoàn thành hoặc ném lỗi. Ném `IllegalStateException` bên trong worker được gửi về future của caller, không tự nhảy vào stack frame test trước khi gọi `get`.

Method `awaitGate` chỉ phục vụ demo; một latch chặn worker 30 giây là giới hạn phòng treo. **Không dùng latch như thế trong service nghiệp vụ production.** Test luôn release gate trong `finally`.

### 7.5. OrderWorkflow: các callback có behavior khác nhau

File **`src/main/java/com/example/asyncdemo/OrderWorkflow.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class OrderWorkflow {

    private final AsyncGateway gateway;

    public OrderWorkflow(AsyncGateway gateway) {
        this.gateway = gateway;
    }

    public CompletableFuture<String> submit(
            String orderId, boolean fail) {
        return gateway.authorize(orderId, fail)
                .thenApply(value -> "READY:" + value);
    }

    public CompletableFuture<String> callbackFails(
            String orderId) {
        return gateway.authorize(orderId, false)
                .thenApply(value -> {
                    throw new IllegalArgumentException(
                            "callback-invalid:" + orderId);
                });
    }

    public CompletableFuture<String> observerFails(
            String orderId) {
        return gateway.authorize(orderId, false)
                .whenComplete((value, error) -> {
                    if (error == null) {
                        throw new IllegalArgumentException(
                                "observer-invalid:" + orderId);
                    }
                });
    }

    public CompletableFuture<String> recover(
            String orderId) {
        return gateway.authorize(orderId, true)
                .exceptionally(error -> "FALLBACK:" + orderId);
    }

    public CompletableFuture<String> classify(
            String orderId, boolean fail) {
        return gateway.authorize(orderId, fail)
                .handle((value, error) ->
                        error == null
                                ? "READY:" + value
                                : "FAILED:" + orderId);
    }
}
```

Vì `OrderWorkflow` được Spring inject một **AsyncGateway proxy**, lời gọi `gateway.authorize` không phải self-invocation. Nó thật sự được chạy qua executor. Năm methods trả **đúng dependent stage**, nên caller/JUnit có thể quan sát:

- `submit`: worker lỗi → returned stage lỗi.
- `callbackFails`: worker thành công nhưng `thenApply` throw → returned stage lỗi.
- `observerFails`: worker thành công, `whenComplete` throw → returned stage lỗi.
- `recover`: worker lỗi → `exceptionally` đưa về giá trị fallback.
- `classify`: `handle` chuyển cả success/failure thành chuỗi kết quả theo chính sách demo.

Nếu `OrderWorkflow.submit` thay bằng lời gọi `gateway.authorize(...).thenApply(...)` nhưng **trả future của `gateway.authorize` thay vì future của `thenApply`**, lỗi mapping callback sẽ bị bỏ rơi. Đây là lý do quan trọng để return **stage cuối đã chứa cả callback assertions/transformations**.

### 7.6. Integration JUnit: test `@Async` thật, 9 phương thức

File **`src/test/java/com/example/asyncdemo/AsyncWorkflowIntegrationTest.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AsyncWorkflowIntegrationTest {

    @Autowired
    private AsyncGateway gateway;

    @Autowired
    private OrderWorkflow workflow;

    @Test
    void asyncSuccessIsAwaitedAndReturned() throws Exception {
        String value = workflow.submit("A1", false)
                .get(5, TimeUnit.SECONDS);

        assertEquals("READY:auth-A1", value);
    }

    @Test
    void exceptionFromAsyncWorkerIsDeliveredByGet() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.submit("A2", true)
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
        assertEquals(
                "gateway-unavailable:A2",
                failure.getCause().getMessage());
    }

    @Test
    void exceptionFromAsyncWorkerIsWrappedByJoin() {
        CompletionException failure = assertThrows(
                CompletionException.class,
                () -> workflow.submit("A3", true)
                        .orTimeout(5, TimeUnit.SECONDS).join());

        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
    }

    @Test
    void exceptionThrownInsideThenApplyReachesJUnit() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.callbackFails("A4")
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
        assertEquals(
                "callback-invalid:A4",
                failure.getCause().getMessage());
    }

    @Test
    void exceptionThrownInsideWhenCompleteReachesJUnit() {
        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> workflow.observerFails("A5")
                        .get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void exceptionallyReturnsFallbackButHidesUpstreamFailure()
            throws Exception {
        CompletableFuture<String> result = workflow.recover("A6");

        assertEquals(
                "FALLBACK:A6", result.get(5, TimeUnit.SECONDS));
        assertFalse(result.isCompletedExceptionally());
    }

    @Test
    void handleCanClassifySuccessAndFailure() throws Exception {
        assertEquals(
                "READY:auth-A7",
                workflow.classify("A7", false)
                        .get(5, TimeUnit.SECONDS));
        assertEquals(
                "FAILED:A7",
                workflow.classify("A7", true)
                        .get(5, TimeUnit.SECONDS));
    }

    @Test
    void assertionInThenAcceptMustBeAwaited() throws Exception {
        CompletableFuture<Void> checked =
                gateway.authorize("A8", false)
                        .thenAccept(value ->
                                assertEquals("auth-A8", value));

        // Đợi stage của thenAccept, không chỉ source future.
        checked.get(5, TimeUnit.SECONDS);
    }

    @Test
    void getTimeoutDoesNotCancelBlockedWorker() throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CompletableFuture<String> running =
                gateway.awaitGate(started, release);

        try {
            assertTrue(started.await(5, TimeUnit.SECONDS));
            assertThrows(
                    TimeoutException.class,
                    () -> running.get(80, TimeUnit.MILLISECONDS));
            assertFalse(running.isDone());
        } finally {
            release.countDown();
        }

        assertEquals(
                "released", running.get(5, TimeUnit.SECONDS));
    }
}
```

**Test #9 có hai tầng timeout khác nhau**: `started.await(5s)` để chắc worker đã chạy, `running.get(80ms)` mong timeout vì worker đang chờ release, rồi `release.countDown()` trong finally để worker kết thúc. Assert `get(5s) == "released"` chứng minh **hết thời gian chờ không có nghĩa computation bị cancel**.

**Test #3 dùng `orTimeout(5s)`** để tránh `join` treo vô thời hạn. Nếu worker deadlock, cause sẽ là TimeoutException thay vì IllegalStateException; assertion nguyên nhân fail, giúp phát hiện lỗi thay vì xanh giả.

### 7.7. Unit JUnit: 11 phương thức của CompletableFuture Java 17

File **`src/test/java/com/example/asyncdemo/CompletableFutureUnitTest.java`**:

```java
package com.example.asyncdemo;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CompletableFutureUnitTest {

    @Test
    void thenApplyAndThenComposeProduceValue() {
        CompletableFuture<Integer> value =
                CompletableFuture.completedFuture("10")
                        .thenApply(Integer::parseInt)
                        .thenCompose(number ->
                                CompletableFuture.completedFuture(
                                        number * 2));

        assertEquals(20, value.join());
    }

    @Test
    void thenCombineWaitsForBothValues() {
        CompletableFuture<String> combined =
                CompletableFuture.completedFuture("A")
                        .thenCombine(
                                CompletableFuture.completedFuture("B"),
                                (a, b) -> a + b);

        assertEquals("AB", combined.join());
    }

    @Test
    void thenApplyExceptionBelongsToReturnedStage() {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> derived =
                source.thenApply(value -> {
                    throw new IllegalArgumentException("bad-callback");
                });

        assertEquals("OK", source.join());

        CompletionException failure = assertThrows(
                CompletionException.class, derived::join);
        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void whenCompleteFailureDoesNotChangeOriginalStage() {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("OK");

        CompletableFuture<String> observed =
                source.whenComplete((value, error) -> {
                    throw new IllegalStateException("observer-error");
                });

        assertEquals("OK", source.join());

        CompletionException failure = assertThrows(
                CompletionException.class, observed::join);
        assertInstanceOf(
                IllegalStateException.class, failure.getCause());
    }

    @Test
    void exceptionallyConvertsFailureToFallback() {
        CompletableFuture<String> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("failed"));

        CompletableFuture<String> recovered =
                source.exceptionally(error -> "FALLBACK");

        assertEquals("FALLBACK", recovered.join());
        assertTrue(source.isCompletedExceptionally());
        assertFalse(recovered.isCompletedExceptionally());
    }

    @Test
    void handleProcessesSuccessAndFailure() {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("VALUE")
                        .handle((value, error) ->
                                error == null ? value : "ERROR");

        CompletableFuture<String> failed =
                CompletableFuture.<String>failedFuture(
                        new IllegalStateException("failed"))
                        .handle((value, error) ->
                                error == null ? value : "ERROR");

        assertEquals("VALUE", success.join());
        assertEquals("ERROR", failed.join());
    }

    @Test
    void allOfPropagatesAFailedBranch() {
        CompletableFuture<String> first =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<String> second =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad"));

        CompletionException failure = assertThrows(
                CompletionException.class,
                () -> CompletableFuture.allOf(first, second).join());

        assertInstanceOf(
                IllegalArgumentException.class, failure.getCause());
    }

    @Test
    void failingAssertionInCallbackIsObservable() {
        CompletableFuture<Void> checked =
                CompletableFuture.completedFuture("actual")
                        .thenAccept(value ->
                                assertEquals("expected", value));

        CompletionException failure = assertThrows(
                CompletionException.class, checked::join);

        assertInstanceOf(AssertionError.class, failure.getCause());
    }

    @Test
    void orTimeoutFailsPendingFuture() {
        CompletableFuture<String> pending = new CompletableFuture<>();
        pending.orTimeout(30, TimeUnit.MILLISECONDS);

        ExecutionException failure = assertThrows(
                ExecutionException.class,
                () -> pending.get(5, TimeUnit.SECONDS));

        assertInstanceOf(
                TimeoutException.class, failure.getCause());
        assertTrue(pending.isCompletedExceptionally());
    }

    @Test
    void completeOnTimeoutReturnsFallback() throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        pending.completeOnTimeout(
                "DEFAULT", 30, TimeUnit.MILLISECONDS);

        assertEquals(
                "DEFAULT", pending.get(5, TimeUnit.SECONDS));
        assertFalse(pending.isCompletedExceptionally());
    }

    @Test
    void cancelCompletesFutureExceptionally() {
        CompletableFuture<String> pending = new CompletableFuture<>();

        assertTrue(pending.cancel(true));
        assertTrue(pending.isCancelled());
        assertTrue(pending.isCompletedExceptionally());
        assertThrows(
                CancellationException.class, pending::join);
    }
}
```

**Đếm JUnit tests:** integration class **9**, unit class **11**, tổng **20 `@Test`**. Unit tests dùng `completedFuture`/`failedFuture` và không tạo thread/đụng network. Những bài timeout trong unit class dùng timer của CompletableFuture (30ms) với deadline đợi tới 5 giây; negative assertions dùng `assertThrows` nên thành công khi lỗi mong đợi được quan sát, không phải test đang lỗi.

### 7.8. Chạy Maven và kết quả kỳ vọng

Từ thư mục có `pom.xml`, yêu cầu JDK 17+ và Maven:

```bash
mvn test
```

Chạy riêng một test class:

```bash
mvn -Dtest=CompletableFutureUnitTest test
mvn -Dtest=AsyncWorkflowIntegrationTest test
```

Nếu có Maven Wrapper đã được tạo trước: `./mvnw test` (Linux/macOS) hoặc `mvnw.cmd test` (Windows).

Kỳ vọng trên môi trường phù hợp: **20 test methods chạy, 0 failures, 0 errors**. Khi một assertion callback được thiết kế cố ý thất bại trong `failingAssertionInCallbackIsObservable`, test method vẫn **PASS** vì nó xác nhận `CompletionException` có cause `AssertionError`. Một future với lỗi không được quan sát thì không đủ bằng chứng để cho test PASS.

Mã minh họa đã được rà soát về imports, API và exception semantics theo Java 17/Spring Boot 3.5, **không phải tuyên bố đã chạy Maven trong quá trình viết bài**. Khi tích hợp vào project thật cần chạy test trên JDK/CI và điều chỉnh executor/timeout theo môi trường.

## 8. Những lỗi test bị che hoặc sai tầng

### 8.1. Bắt exception rồi bỏ qua

```java
return gateway.authorize(orderId, true)
        .exceptionally(error -> {
            log.warn("Async failed", error);
            return "OK";
        });
```

Snippet giả định `gateway` và `log` tồn tại, không standalone. Nếu business contract bắt buộc propagate failure, trả `"OK"` là **che lỗi**. Khi test chỉ kiểm kết quả `OK`, nó có thể cho false positive dù nghiệp vụ đã lỗi. Phải chọn rõ recovery hay failure propagation, kiểm cả metrics/audit và các downstream side effects.

### 8.2. Callback có assertion nhưng không return/await stage của callback

```java
CompletableFuture<String> original = service.loadAsync();

original.thenAccept(value ->
        assertEquals("expected", value));

original.get(5, TimeUnit.SECONDS); // SAI: chỉ chờ ORIGINAL
```

Đây là anti-pattern, `service` giả định. Nếu `thenAccept` ném lỗi, `original` vẫn có thể thành công. Đúng là:

```java
CompletableFuture<Void> checked =
        original.thenAccept(value ->
                assertEquals("expected", value));
checked.get(5, TimeUnit.SECONDS);
```

### 8.3. Callback lỗi nhưng test chỉ assert `isDone()`

`isDone()` true với normal/exceptional/cancelled. Thay bằng `get(timeout)`, `join` hoặc assert trạng thái và nguyên nhân. Nếu test quan tâm toàn bộ pipeline, chờ **terminal stage** chứ không chỉ upstream source.

### 8.4. Dùng `@Async void` và mong test nhận exception

`@Async void` không có Future để caller nhận lỗi. Dùng `CompletableFuture<Void>` khi contract cần biết thành công/thất bại, hoặc cấu hình `AsyncUncaughtExceptionHandler` có test sink được đồng bộ, không rely vào log. Tránh fire-and-forget cho logic cần transactional integrity/important delivery guarantees nếu không có hàng đợi/retry/monitoring.

### 8.5. Gọi self-invocation và tưởng method chạy trên pool

`this.doAsync()` trong cùng bean bỏ qua proxy-based Spring `@Async`. Method có thể chạy **synchronously**, làm test đôi khi pass vì assertion chạy ngay, còn production call qua proxy lại async và fail. Tách sang bean khác hoặc gọi qua proxy đúng thiết kế; integration test nên kiểm thread/latch ở boundary quan trọng.

### 8.6. Test tự đợi bằng `Thread.sleep(1000)`

Khi CI chậm, 1 giây không đủ; khi máy nhanh, 1 giây là lãng phí. Dùng `CompletableFuture.get(timeout)`, `CountDownLatch`, barrier, Awaitility (nếu được cài) với bounded polling, hoặc test executor/fake scheduler. Cần clean up worker trong `finally` sau timeout.

### 8.7. Không phân biệt lỗi nguồn và lỗi callback

Nếu upstream đã lỗi và `whenComplete` cũng throw, returned stage có thể vẫn giữ **lỗi upstream** theo Java semantics. Nếu upstream thành công nhưng callback throw, returned stage mang lỗi callback. Muốn chắc chắn cái gì fail, test các case riêng; đừng kết luận chỉ từ thông báo lỗi trên console.

### 8.8. `allOf` có một nhánh lỗi nhưng các nhánh khác vẫn đang chạy

`CompletableFuture.allOf(a,b,c)` giúp chờ tất cả hoàn tất; khi một lỗi, combined future lỗi. Nó không có nghĩa framework đã rollback/cancel mọi nhánh khác. Dùng test state isolation, cancellation/compensation tùy nghiệp vụ. Nếu làm database writes từ các nhánh async, có thể xảy ra partial effects; không kỳ vọng outer test transaction rollback tự bao phủ.

### 8.9. Chạy callback trên executor khác với callback đăng ký

`thenApply` có thể chạy trên thread hoàn tất upstream hoặc thread gọi nếu source đã xong; không assert “callback luôn chạy trên pool-1-thread-1”. `thenApplyAsync` với explicit executor khi thread affinity quan trọng. Với ThreadLocal request/security/transaction context, kiểm propagation riêng.

### 8.10. Timeouts không tự rollback công việc bên ngoài

`get(timeout)` chỉ timeout của caller. `orTimeout`/`cancel` đổi trạng thái future nhưng không chắc dừng underlying I/O/job. Nếu timeout dẫn tới retry, backend có thể xử lý lệnh cũ song song lệnh mới. Dùng **idempotency key** và reconciliation cho side effects như payment/message publish, không suy từ future timeout rằng operation chưa xảy ra.

## 9. Lịch chạy Spring và cách đưa lỗi về test

Spring `@Scheduled` có thể kích hoạt background job theo fixedDelay/fixedRate/cron. Phần “lịch chạy” liên quan trực tiếp đến cùng vấn đề: **lỗi xảy ra ngoài JUnit test method**.

Một cấu trúc khuyến nghị:

```text
Scheduler (chỉ quyết định khi nào kích hoạt)
       |
       v
Job adapter (ghi correlation ID, metrics, error log)
       |
       v
BusinessWorker.runOneCycle(): CompletableFuture<Result>
       |
       +-- thenApply/thenCompose/handle
       +-- outcome / error / retry decision
       |
       v
Test gọi business worker trực tiếp
       |
       +-- await CompletableFuture.get(timeout)
       +-- assert result/error/callback
```

Với `@Scheduled void`, caller JUnit không có returned future. Không test cron bằng cách `Thread.sleep(60_000)` rồi kiểm log. Thay vào đó:

1. **Tách logic** chạy một chu kỳ thành service nhận dependencies/time source.
2. **Unit/integration test** logic đó qua method trả Future hoặc method synchronous rõ.
3. **Test adapter scheduling** riêng để chắc annotation/config thực kích hoạt đúng lịch, dùng fake clock/scheduler/triggers nếu phù hợp.
4. Khi scheduled job lỗi, quan sát metric/error handler/outbox hoặc bounded sink, không coi “không thấy exception trong test thread” là PASS.
5. Với job idempotent hoặc có overlap, kiểm concurrent invocations, uniqueness locks và eventual consistency.
6. Khi task bị hủy/interrupted, giữ đúng interrupt flag và cleanup external resources.

Lỗi của repeating scheduled task thường được scheduler error handler ghi log và xử lý để lịch chạy tiếp; do đó **không nên tin rằng exception sẽ bay lên JUnit thread**. Với job nghiệp vụ quan trọng, có callback/sink riêng thể hiện trạng thái thành công/thất bại và cảnh báo.

## 10. Bảng test matrix nên dùng trong dự án

| Case | Setup | Bằng chứng/expected |
|---|---|---|
| Async happy path | Worker trả success | Await terminal stage, assert giá trị |
| Worker throw | `@Async` ném unchecked exception | `get(timeout)` ném `ExecutionException` có cause đúng |
| Callback transform throw | Upstream success, `thenApply` throw | Returned dependent stage lỗi, source có thể vẫn success |
| Observer throw | `whenComplete` throw | Returned observed stage lỗi, không bỏ stage |
| Callback assertion fail | `thenAccept` assert sai | Await returned `CompletableFuture<Void>`, JUnit thấy cause là `AssertionError` |
| Recovery có chủ đích | `exceptionally` trả fallback | Terminal stage success, upstream error vẫn được ghi nhận |
| Classify both outcomes | `handle` với success/error | Assert cả hai nhánh |
| Multiple futures | `thenCombine`/`allOf` | Không mất lỗi ở bất cứ nhánh nào |
| Slow/blocking worker | Latch chặn worker | `get(timeout)` timeout, release rồi get thành công |
| Future cancellation | `cancel(true)` | Future cancelled; không tuyên bố worker đã interrupted |
| Executor saturation | Queue đầy / rejection | Submit error quan sát theo contract, cleanup pool |
| `@Async void` | Method throw | Handler/sink nhận lỗi, test không dựa vào returned future |
| Scheduled job throw | Trigger job qua fake scheduler | Error handler/event sink nhận lỗi |
| Caller transaction rollback | Worker write DB thread khác | Đọc committed state đúng boundary, cleanup theo test ID |
| Concurrent callbacks | Race hai completions | Chỉ một outcome thắng, invariant không vi phạm |
| Timeout rồi retry | Underlying side effect có thể vẫn chạy | Idempotency / duplicate suppression, không double-write |

## 11. Checklist trước khi đánh dấu QA PASS cho async test

- [ ] Test **đợi terminal future/stage** chứa tất cả callbacks muốn kiểm.
- [ ] `get(timeout)` được dùng tại boundary test thay vì chờ vô hạn.
- [ ] Khi future lỗi, test kiểm **cause thực**, không chỉ một `isDone()`.
- [ ] Tôi phân biệt `ExecutionException`, `CompletionException`, `CancellationException` và `TimeoutException`.
- [ ] Assertions trong `thenAccept`/`whenComplete` không bị bỏ rơi.
- [ ] `whenComplete` chỉ quan sát; `exceptionally` và `handle` có thể biến failure thành success.
- [ ] Test biết callback nào chạy khi upstream thành công/lỗi.
- [ ] Tôi không giả định `thenApply` luôn chạy trên executor riêng.
- [ ] `thenApplyAsync` truyền explicit executor nếu cần kiểm thread/Context.
- [ ] `@Async` được gọi qua Spring bean proxy, không qua `new` hay self-invocation.
- [ ] Executor size/queue/shutdown/rejection phù hợp test và production.
- [ ] Không dùng `Thread.sleep` như cách chờ work hoàn tất.
- [ ] Với timeout test, sử dụng latch/barrier và release trong `finally`.
- [ ] Tôi hiểu `get(timeout)` không tự cancel computation, `cancel(true)` không đảm bảo interrupt.
- [ ] `@Async void` có handler/sink riêng hoặc được thay bằng `CompletableFuture<Void>` khi cần truyền lỗi.
- [ ] `@Scheduled` được test theo logic cycle và error signaling, không chờ cron bằng sleep.
- [ ] ThreadLocal transaction/security/MDC được xử lý theo đúng executor/context.
- [ ] Async DB writes có fixture cleanup riêng; không suy rollback test bao phủ worker thread.
- [ ] Có negative tests kiểm worker throw, callback throw và explicit recovery.
- [ ] Đã chạy `mvn test` trên JDK 17+ và không có background task leak ảnh hưởng suite.
- [ ] Không suy từ test pass rằng retry, compensation, side effects của hệ ngoài đã hoàn tất.

**Kết luận:** Để kiểm thử bất đồng bộ đáng tin, hãy **trả về đúng completion stage, đợi stage cuối với deadline, kiểm nguyên nhân exception và dùng điều phối xác định** thay cho sleep. Callback ném lỗi không tự xuất hiện trong JUnit nếu bị bỏ rơi; `@Async void` và `@Scheduled` lại càng cần cơ chế báo lỗi/sink riêng. **Kiểm thử đúng không phải chỉ “method đã được gọi”, mà là “toàn bộ pipeline đã hoàn thành với outcome được xác minh”.**

### Tài liệu chính thức

- [Java 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — CompletionStage Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Spring Framework — Task Execution and Scheduling, @Async exceptions](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Boot 3.5 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit Jupiter — Assertions and Timeouts](https://docs.junit.org/5.11.3/user-guide/index.html)
