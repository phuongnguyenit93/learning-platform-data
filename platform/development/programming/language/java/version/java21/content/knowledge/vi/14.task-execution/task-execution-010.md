# Kết hợp virtual thread với `CompletableFuture` qua executor tường minh

## 1. Vì sao cần truyền executor tường minh?

`CompletableFuture` biểu diễn một kết quả có thể hoàn tất trong tương lai và cho phép nối các bước xử lý thành một pipeline bất đồng bộ. Virtual thread trong Java 21 là lựa chọn phù hợp để chạy các tác vụ có blocking I/O, chẳng hạn gọi dịch vụ, truy vấn database hoặc đọc file.

Hai API này giải quyết hai phần khác nhau:

- `CompletableFuture` mô tả quan hệ phụ thuộc, kết hợp kết quả và truyền lỗi giữa các bước.
- `Executor` quyết định nơi các tác vụ bất đồng bộ được thực thi. Một executor tạo virtual thread sẽ chạy các tác vụ được gửi đến nó trên virtual thread.

Không phải mọi `CompletableFuture` đều tự động chạy trên virtual thread. Các overload bất đồng bộ không nhận executor, như `supplyAsync(supplier)` hoặc `thenApplyAsync(function)`, sử dụng default asynchronous execution facility của `CompletableFuture` (thông thường là `ForkJoinPool.commonPool()`). Các method không có hậu tố `Async`, như `thenApply`, có thể chạy trên thread hoàn tất stage trước đó hoặc thread gọi thao tác hoàn tất.

Muốn kiểm soát rõ executor, hãy truyền nó vào các overload có tham số `Executor`:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    CompletableFuture<String> result = CompletableFuture
            .supplyAsync(() -> loadFromDatabase(), executor)
            .thenApplyAsync(this::formatResult, executor);

    System.out.println(result.join());
}
```

Trong ví dụ, cả tác vụ tải dữ liệu và bước định dạng đều được gửi đến executor tạo virtual thread. Việc truyền executor ở từng stage là chủ đích; executor của một stage không tự động trở thành executor mặc định cho toàn bộ pipeline.

## 2. Tạo executor dùng virtual thread

Java 21 cung cấp `Executors.newVirtualThreadPerTaskExecutor()` để tạo `ExecutorService` khởi chạy một virtual thread mới cho mỗi task được submit.

```java
ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
```

Đây là executor theo mô hình *thread-per-task*, không phải một thread pool giữ sẵn một số lượng virtual thread cố định để tái sử dụng. Khi task được gửi đến executor, một virtual thread mới được tạo để chạy task đó.

Executor triển khai `ExecutorService`, vì vậy có thể truyền trực tiếp vào các method của `CompletableFuture` nhận `Executor`:

```java
CompletableFuture<User> userFuture =
        CompletableFuture.supplyAsync(() -> userRepository.findById("u-42"), executor);
```

Lời gọi `supplyAsync` lập lịch Supplier trên executor rồi trả về `CompletableFuture`. Caller có thể tiếp tục xây dựng pipeline mà không phải tự tạo và quản lý từng `Thread`.

### 2.1. Quản lý vòng đời executor

Trong Java 21, `ExecutorService` có thể được dùng với try-with-resources. Khi khối `try` kết thúc, `close()` đóng executor và chờ các task đã được submit hoàn tất.

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    CompletableFuture<String> future = CompletableFuture.supplyAsync(
            () -> callRemoteService(), executor);

    String response = future.join();
    System.out.println(response);
}
```

Hãy hoàn tất hoặc chờ pipeline trước khi đóng executor. Trong ứng dụng server, executor có thể được tạo ở cấp application/service và đóng khi thành phần dừng; không nhất thiết phải tạo một executor mới cho từng request. Khi chia sẻ executor, cần xác định rõ thành phần nào sở hữu và chịu trách nhiệm đóng nó.

## 3. Đưa blocking I/O vào `supplyAsync`

`CompletableFuture.supplyAsync` phù hợp với tác vụ trả về kết quả. Khi truyền virtual-thread executor, Supplier chạy trên virtual thread và có thể gọi API blocking theo cách tuần tự quen thuộc.

```java
CompletableFuture<Customer> customerFuture = CompletableFuture.supplyAsync(
        () -> customerRepository.loadCustomer(customerId), virtualExecutor);
```

Ví dụ này hữu ích khi thư viện database hoặc HTTP client đang dùng cung cấp API blocking. Với các thao tác blocking mà JVM có thể unmount virtual thread, platform thread có thể được giải phóng để chạy virtual thread khác trong thời gian chờ. Nếu virtual thread bị pin, carrier thread vẫn bị giữ; vì vậy không nên giả định mọi lời gọi blocking đều giải phóng carrier trong mọi tình huống.

Không cần biến một API vốn đã bất đồng bộ thành một tác vụ blocking chỉ để chạy nó trên virtual thread. Nếu HTTP client trả về `CompletableFuture` hoặc `CompletionStage` sẵn, có thể kết hợp trực tiếp stage đó. Executor được truyền cho continuation sẽ quyết định nơi chạy continuation; nó không thay đổi executor nội bộ mà HTTP client đã dùng để thực hiện request.

## 4. Truyền cùng executor cho từng asynchronous stage

Mỗi nhóm method bất đồng bộ của `CompletableFuture` thường có overload nhận executor. Ví dụ:

| Method | Vai trò |
|---|---|
| `supplyAsync(supplier, executor)` | Chạy Supplier và tạo kết quả ban đầu |
| `runAsync(runnable, executor)` | Chạy Runnable không trả về kết quả |
| `thenApplyAsync(function, executor)` | Biến đổi kết quả của stage trước |
| `thenComposeAsync(function, executor)` | Tạo và nối tiếp một stage khác |
| `thenCombineAsync(other, function, executor)` | Kết hợp hai stage độc lập khi cả hai hoàn tất |
| `thenAcceptAsync(action, executor)` | Tiêu thụ kết quả mà không tạo giá trị mới |
| `handleAsync(function, executor)` | Xử lý cả kết quả thành công và lỗi |
| `whenCompleteAsync(action, executor)` | Thực hiện hành động quan sát khi stage hoàn tất |
| `exceptionallyAsync(function, executor)` | Phục hồi hoặc chuyển đổi lỗi bất đồng bộ |

Ví dụ, nếu muốn bước định dạng chạy trên virtual thread, dùng `thenApplyAsync` với executor:

```java
CompletableFuture<String> formatted = CompletableFuture
        .supplyAsync(() -> loadData(), virtualExecutor)
        .thenApplyAsync(data -> format(data), virtualExecutor);
```

Nếu bỏ executor ở stage thứ hai:

```java
CompletableFuture<String> formatted = CompletableFuture
        .supplyAsync(() -> loadData(), virtualExecutor)
        .thenApplyAsync(data -> format(data));
```

thì `thenApplyAsync` dùng default asynchronous execution facility, không mặc nhiên dùng virtual-thread executor của stage đầu.

## 5. Phân biệt method có `Async` và không có `Async`

Các method không có hậu tố `Async`, chẳng hạn `thenApply`, `thenAccept`, `thenCombine` hoặc `thenCompose`, không đảm bảo callback chạy trên virtual thread. Callback có thể được thực thi bởi thread hoàn tất stage trước hoặc thread gọi thao tác hoàn tất nếu stage trước đã hoàn tất.

```java
CompletableFuture<String> result = CompletableFuture
        .supplyAsync(() -> loadData(), virtualExecutor)
        .thenApply(data -> format(data)); // Không chỉ định executor
```

Supplier đầu tiên chạy trên virtual thread. Nhưng không nên kết luận rằng callback `format` cũng chắc chắn chạy trên virtual thread. Nếu vị trí thực thi là yêu cầu của thiết kế, hãy viết:

```java
CompletableFuture<String> result = CompletableFuture
        .supplyAsync(() -> loadData(), virtualExecutor)
        .thenApplyAsync(data -> format(data), virtualExecutor);
```

Không phải lúc nào cũng cần dùng method `Async`. Với callback ngắn, không blocking và chỉ thực hiện một phép biến đổi nhỏ, method không có `Async` có thể giảm việc lập lịch không cần thiết. Tuy nhiên, callback không nên thực hiện I/O blocking hoặc công việc nặng nếu thread thực thi nó không được kiểm soát.

## 6. Kết hợp nhiều tác vụ độc lập với `thenCombineAsync`

Một tình huống phổ biến là tải hai nguồn dữ liệu độc lập rồi kết hợp kết quả. Có thể khởi chạy cả hai tác vụ bằng cùng virtual-thread executor và kết hợp chúng khi cả hai hoàn tất.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

record User(String id, String name) {}
record Preferences(String theme) {}
record Dashboard(User user, Preferences preferences) {}

interface UserRepository {
    User findById(String id);
}

interface PreferencesRepository {
    Preferences findByUserId(String id);
}

static Dashboard loadDashboard(
        String userId,
        UserRepository users,
        PreferencesRepository preferences) {

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        CompletableFuture<User> userFuture = CompletableFuture.supplyAsync(
                () -> users.findById(userId), executor);

        CompletableFuture<Preferences> preferencesFuture = CompletableFuture.supplyAsync(
                () -> preferences.findByUserId(userId), executor);

        CompletableFuture<Dashboard> dashboardFuture = userFuture.thenCombineAsync(
                preferencesFuture,
                Dashboard::new,
                executor);

        return dashboardFuture.join();
    }
}
```

Hai truy vấn độc lập có thể tiến hành đồng thời. `thenCombineAsync` chỉ chạy hàm tạo `Dashboard` sau khi cả `userFuture` và `preferencesFuture` hoàn tất thành công; hàm kết hợp được gửi đến executor đã chỉ định.

Nếu một trong hai future hoàn tất exceptional, hàm kết hợp thông thường không chạy và future kết quả cũng hoàn tất exceptional. Có thể dùng `handleAsync` hoặc `exceptionallyAsync` để xác định chính sách xử lý lỗi.

## 7. Dùng `thenComposeAsync` để nối tác vụ phụ thuộc

`thenCompose` và `thenComposeAsync` phù hợp khi một bước trả về một `CompletionStage` khác. Chúng giúp tránh cấu trúc lồng `CompletableFuture<CompletableFuture<T>>`.

Ví dụ, sau khi tải user, gọi một client bất đồng bộ để tải quyền truy cập:

```java
CompletableFuture<User> userFuture = CompletableFuture.supplyAsync(
        () -> userRepository.findById(userId), virtualExecutor);

CompletableFuture<Permissions> permissionsFuture = userFuture.thenComposeAsync(
        user -> permissionsClient.fetchAsync(user.id()),
        virtualExecutor);
```

`thenComposeAsync` chạy function lấy user và gọi `fetchAsync` trên executor được truyền. Tuy nhiên, phần thực hiện request của `permissionsClient` thuộc implementation của client và có thể sử dụng executor hoặc event loop riêng. Executor truyền vào `thenComposeAsync` không tự chuyển toàn bộ hoạt động nội bộ của client sang virtual thread.

Nếu client chỉ có API blocking, có thể dùng `thenApplyAsync` hoặc `thenComposeAsync` để gọi API đó trên virtual-thread executor, tùy kiểu kết quả trả về. Chỉ dùng `thenComposeAsync` khi function trả về một `CompletionStage`.

## 8. Xử lý lỗi trong pipeline

Exception phát sinh bên trong Supplier, Function hoặc Runnable được chuyển thành exceptional completion của stage tương ứng. Khi gọi `join()`, lỗi thường được ném ra dưới dạng `CompletionException`; nguyên nhân gốc nằm trong `getCause()`.

```java
CompletableFuture<String> result = CompletableFuture
        .supplyAsync(() -> loadData(), virtualExecutor)
        .thenApplyAsync(data -> transform(data), virtualExecutor)
        .exceptionallyAsync(error -> {
            Throwable cause = error.getCause() != null ? error.getCause() : error;
            logFailure(cause);
            return "fallback";
        }, virtualExecutor);
```

`exceptionallyAsync` chỉ chạy khi stage trước hoàn tất exceptional. Nó có thể trả về giá trị thay thế để hoàn tất pipeline thành công. Nếu muốn xử lý cả trường hợp thành công và thất bại trong cùng một function, dùng `handleAsync`.

```java
CompletableFuture<String> result = source.handleAsync((value, error) -> {
    if (error != null) {
        return "failed: " + error.getMessage();
    }
    return "value: " + value;
}, virtualExecutor);
```

`whenCompleteAsync` phù hợp với logging, metrics hoặc quan sát kết quả mà không thay đổi kết quả thành công/lỗi ban đầu. Nếu callback của `whenCompleteAsync` tự ném exception, stage được trả về có thể hoàn tất exceptional.

## 9. `join`, `get`, timeout và cancellation

`join()` chờ kết quả và ném unchecked `CompletionException` khi future hoàn tất exceptional. `get()` cũng chờ kết quả nhưng khai báo `InterruptedException` và `ExecutionException`, phù hợp khi caller cần xử lý interruption theo hợp đồng của `Future`.

Không nên gọi `join()` hoặc `get()` quá sớm giữa các bước nếu có thể nối stage bằng `thenApplyAsync`, `thenComposeAsync` hoặc `thenCombineAsync`. Việc chờ chỉ nên diễn ra ở ranh giới cần kết quả đồng bộ, ví dụ tầng gọi cuối hoặc nơi trả response.

Có thể đặt giới hạn thời gian bằng `orTimeout` hoặc cung cấp giá trị thay thế bằng `completeOnTimeout`:

```java
import java.util.concurrent.TimeUnit;

CompletableFuture<Response> responseFuture = CompletableFuture
        .supplyAsync(() -> callService(), virtualExecutor)
        .orTimeout(2, TimeUnit.SECONDS);
```

`orTimeout` làm future hoàn tất exceptional với `TimeoutException` nếu thời hạn hết trước khi có kết quả. Nó không phải cơ chế bảo đảm rằng hoạt động I/O bên dưới đã bị dừng.

Tương tự, `CompletableFuture.cancel(true)` hoàn tất future bằng `CancellationException`; tham số `mayInterruptIfRunning` không được dùng để điều khiển việc interrupt task đang chạy trong triển khai `CompletableFuture`. Vì vậy, không nên dựa vào `cancel(true)` để dừng một virtual thread đang thực hiện I/O blocking. Nếu cần dừng công việc, hãy thiết kế timeout và cancellation theo API I/O, interruption hoặc cancellation token mà tác vụ thực sự kiểm tra.

## 10. Virtual thread phù hợp với I/O, không làm CPU nhanh hơn

Virtual thread giúp mở rộng số lượng tác vụ đồng thời khi nhiều tác vụ thường xuyên chờ I/O. Chúng không làm tăng năng lực tính toán CPU. Nếu một stage thực hiện nén dữ liệu, mã hóa hoặc tính toán nặng liên tục, chạy stage đó trên virtual thread không tự tạo thêm CPU core.

Một thiết kế thường gặp là:

- Dùng virtual-thread executor cho tác vụ blocking I/O.
- Dùng executor có giới hạn phù hợp với số lõi CPU cho công việc CPU-bound.
- Dùng semaphore, connection pool, rate limiter hoặc giới hạn ở tầng dịch vụ để bảo vệ database và dịch vụ bên ngoài.

`newVirtualThreadPerTaskExecutor()` không phải giới hạn concurrency. Nó có thể tạo rất nhiều virtual thread nếu ứng dụng submit rất nhiều task. Virtual thread có chi phí thấp hơn platform thread nhưng vẫn sử dụng tài nguyên, và các dịch vụ downstream vẫn có giới hạn thực tế.

## 11. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Chỉ truyền executor cho `supplyAsync`, rồi dùng `thenApplyAsync` không có executor | Stage sau dùng default async facility | Truyền executor tường minh vào từng async stage cần kiểm soát |
| Cho rằng `thenApply` luôn chạy trên virtual thread | Non-async stage có thể chạy trên thread hoàn tất hoặc thread gọi | Dùng `thenApplyAsync(..., executor)` khi cần chỉ định executor |
| Dùng virtual thread cho mọi phép tính CPU-bound | Virtual thread không tăng năng lực CPU | Dùng executor phù hợp cho CPU-bound work |
| Dùng virtual-thread executor như pool giới hạn số task | Executor tạo một virtual thread cho mỗi task | Giới hạn concurrency ở tài nguyên downstream hoặc bằng semaphore |
| Tạo executor cho từng bước nhỏ rồi không đóng | Có thể rò rỉ tài nguyên và khó quản lý vòng đời | Quản lý executor ở scope phù hợp và đóng đúng lúc |
| Gọi `join()` giữa từng stage | Làm pipeline mất tính bất đồng bộ và có thể chặn thread gọi | Nối các stage rồi chờ ở ranh giới cuối |
| Dựa vào `cancel(true)` để ngắt I/O đang chạy | `CompletableFuture` không dùng cờ này để interrupt task | Dùng timeout/cancellation theo API thực thi và thiết kế task hợp tác dừng |
| Kỳ vọng executor của continuation điều khiển cả HTTP client async | Client có thể dùng executor/event loop riêng | Kiểm tra hợp đồng executor của client; phân biệt callback với hoạt động I/O bên trong |

## 12. Tài liệu tham khảo chính thức

- [Java SE 21 API — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): các method async, overload nhận executor, default async facility, completion, timeout và cancellation.
- [Java SE 21 API — `Executor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng thực thi task.
- [Java SE 21 API — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý vòng đời executor và `close()`.
- [Java SE 21 API — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()` và các factory executor.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): thiết kế và trạng thái chính thức của virtual thread trong Java 21.

Khi kết hợp `CompletableFuture` với virtual thread, hãy xem executor là lựa chọn thực thi cho từng asynchronous stage. Truyền virtual-thread executor vào các overload `Async` cần kiểm soát, dùng composition để mô tả phụ thuộc, kết hợp các tác vụ độc lập bằng `thenCombineAsync`, và quản lý vòng đời executor rõ ràng. Điều đó giúp tận dụng virtual thread cho blocking I/O mà vẫn giữ được luồng xử lý lỗi, timeout và giới hạn tài nguyên của ứng dụng.
