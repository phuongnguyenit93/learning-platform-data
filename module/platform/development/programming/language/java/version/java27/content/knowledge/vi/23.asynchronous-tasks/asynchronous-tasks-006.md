# Lựa chọn giữa callback, CompletableFuture và virtual thread trong Java 27

Trong ứng dụng Java, một thao tác có thể cần gọi HTTP, đọc database, lấy cấu hình hoặc chờ phản hồi từ hệ thống ngoài. Có nhiều cách tổ chức công việc này: truyền **callback** để được gọi khi kết quả đến, trả về **`CompletableFuture<T>`** để ghép các bước xử lý, hoặc viết mã **blocking tuần tự bên trong virtual thread** để diễn đạt một tác vụ theo thứ tự tự nhiên.

Ba cách này đều hữu ích và vẫn được hỗ trợ trong **Java 27**. Không có quy tắc “mọi callback đều lỗi thời”, “mọi thứ phải là future”, hay “virtual threads thay thế tất cả các API bất đồng bộ”. Lựa chọn đúng phụ thuộc vào **kiểu API nguồn, hình dạng luồng công việc, nhu cầu cancellation, khả năng quản lý vòng đời và giới hạn tài nguyên**.

Bài thuộc chương **Tác vụ bất đồng bộ** của module **Java 27 và các kiến thức liên quan**. Nội dung chỉ dựa trên các API Java hiện hành, ổn định; các API còn ở trạng thái preview nếu có được đề cập sẽ được phân biệt rõ với giải pháp chuẩn dùng trong ví dụ.

## 1. Trước hết, phân biệt bất đồng bộ và song song

**Bất đồng bộ** (*asynchronous*) mô tả cách người gọi không nhất thiết phải chờ kết quả hoàn tất ngay ở dòng gọi. **Đồng thời** (*concurrency*) mô tả việc có nhiều công việc đang tiến triển trong cùng khoảng thời gian. **Song song** (*parallelism*) là việc có nhiều công việc thực sự chạy cùng lúc trên tài nguyên xử lý.

Một lời gọi có thể bất đồng bộ mà không tăng khả năng tính toán CPU. Ngược lại, mã blocking bên trong các virtual thread khác nhau vẫn có thể tạo ra rất nhiều tác vụ đồng thời.

Ví dụ ba hình dạng:

```text
Callback:
    bắt đầu thao tác ─────► nhận callback sau khi hoàn tất
                           └─► xử lý kết quả

CompletableFuture:
    stage A ──► thenApply B ──► thenCompose C
           └────────► kết quả/exception trong CompletionStage

Virtual thread:
    task:
       lấy hồ sơ (có thể chờ I/O)
       lấy quyền (có thể chờ I/O)
       dựng kết quả
    toàn bộ task chạy trong một virtual Thread
```

Điều cần hỏi không phải “cách nào bất đồng bộ hơn”, mà là **nơi nào phải chờ, ai giữ trạng thái và kết quả, và ai chịu trách nhiệm kết thúc hoặc hủy các công việc liên quan**.

## 2. Bảng so sánh nhanh

| Tiêu chí | Callback | `CompletableFuture` | Virtual thread |
| --- | --- | --- | --- |
| Giao diện phổ biến | `start(input, callback)` | `CompletableFuture<T>` / `CompletionStage<T>` | Hàm thường chạy trong `Thread` hoặc `ExecutorService` |
| Kết quả | Truyền qua hàm callback | Nằm trong future, lấy/ghép bằng stage | Có thể trả trực tiếp trong `Callable<T>` hoặc thông qua `Future<T>` |
| Mã ở người gọi | Đăng ký hàm xử lý thành công/thất bại | `thenApply`, `thenCompose`, `thenCombine`, `handle`... | Trình tự lệnh bình thường, `try/catch/finally` |
| Phối hợp nhiều tác vụ | Cần viết cơ chế điều phối hoặc dùng thư viện | Có stage combinators | Có thể `submit` nhiều task rồi `Future.get()` |
| Exception | Qua callback lỗi hoặc contract riêng | Exceptional completion | Exception trực tiếp trong task; qua `Future.get()` thành `ExecutionException` |
| Chờ của thread gọi | Không bắt buộc | Không bắt buộc cho tới `join/get` | Thread gọi có thể chờ; nếu là virtual thread, blocking I/O thường mở rộng tốt |
| Cancellation | Phụ thuộc API callback | Hủy trạng thái future; không mặc nhiên ngắt công việc gốc | Có thể yêu cầu interrupt bằng `Thread.interrupt`/`Future.cancel(true)` |
| Ngữ cảnh thực thi | Do API quyết định nơi gọi callback | Do phương thức stage và executor quyết định | Ngữ cảnh trong chính virtual thread |
| Phù hợp | Tích hợp nguồn sự kiện/API chỉ có callback | Pipeline, composition, fan-out/fan-in | Nhiều tác vụ blocking I/O độc lập, code tuần tự dễ đọc |
| Rủi ro | Callback lồng nhau, lỗi một lần/đa lần, callback thread | Graph phức tạp, default executor, cancellation không truyền tự động | Tạo vô hạn task, timeout, downstream overload |

**Lưu ý:** Cột “virtual thread” nói về **mô hình thực thi tác vụ**; hai cột còn lại chủ yếu nói về **cơ chế biểu diễn và nhận kết quả**. Chúng không hoàn toàn cùng một tầng trừu tượng: một `CompletableFuture` vẫn có thể được thực thi bởi một virtual-thread executor.

## 3. Callback: giao kết quả cho một hàm được gọi về sau

Callback thường xuất hiện trong thư viện có cơ chế I/O theo sự kiện, API UI, event loop, driver hoặc integration cũ chưa trả `CompletionStage`.

Một API có thể thiết kế:

```java
interface ResultCallback<T> {
    void completed(T result);
    void failed(Throwable error);
}

interface UserGateway {
    void findUser(String id, ResultCallback<String> callback);
}
```

Người gọi:

```java
gateway.findUser("u1", new ResultCallback<>() {
    @Override
    public void completed(String user) {
        System.out.println("Đã tìm: " + user);
    }

    @Override
    public void failed(Throwable error) {
        System.err.println("Không tìm được: " + error.getMessage());
    }
});
```

Lời gọi `findUser` **có thể trả về trước khi callback chạy**, nhưng điều này **không tự suy ra chỉ từ chữ ký phương thức**. Một số API được phép gọi callback ngay trên thread gọi. Phải đọc contract cụ thể về **khi nào, trên thread nào, bao nhiêu lần và với trạng thái nào** callback được gọi.

### 3.1. Một callback đúng hợp đồng cần làm rõ gì?

Với API dùng để báo **một kết quả cuối**, nên xác định:

1. Callback có được gọi **đúng một lần** hay có thể nhiều lần?
2. Nếu thao tác thất bại, dùng `failed`, ném exception từ `start`, hay cả hai trong các trường hợp khác nhau?
3. Callback được chạy trên **I/O/event-loop thread, thread-pool thread, virtual thread hay thread gọi**?
4. Callback có thể chạy **trước khi phương thức đăng ký trả về** không?
5. Điều gì xảy ra nếu chính callback ném exception?
6. Có cơ chế hủy? Hủy callback hay hủy **I/O gốc**?
7. Sau cancellation, callback có thể đến muộn không?
8. Có bảo đảm thứ tự callback khi gọi nhiều request không?

Ví dụ cách **không nên** xử lý:

```java
// Sai về ý định: ngoại lệ từ completed() lại bị coi là lỗi thao tác gốc.
// try {
//     Result result = performWork();
//     callback.completed(result);
// } catch (Exception e) {
//     callback.failed(e);
// }
```

Nếu `completed` tự ném lỗi, code trên có thể gọi `failed` sau `completed` và vi phạm hợp đồng chỉ một kết quả. Hãy tách giai đoạn **tính kết quả** khỏi giai đoạn **thông báo callback**; xử lý ngoại lệ của consumer theo chính sách riêng.

### 3.2. Callback lồng nhau và khó quản lý lỗi

```java
// Pseudocode: các phương thức sau là API callback bên ngoài.
findUser("u1", user -> {
    findOrders(user, orders -> {
        calculateTotal(orders, total -> {
            sendNotification(user, total);
        });
    });
});
```

Việc lồng nhiều tầng khiến xử lý lỗi, timeout, hủy toàn chuỗi và ghép các nhánh độc lập khó theo dõi. Không có nghĩa callback luôn không tốt: nếu sự kiện là **dòng vô hạn** (UI events, message stream), callback/listener có thể vẫn là hình thức tự nhiên.

Với công việc có **một kết quả cuối**, chuyển callback thành `CompletionStage` có thể giúp biểu diễn chuỗi tác vụ rõ ràng hơn.

## 4. CompletableFuture: một kết quả và các bước phụ thuộc

`java.util.concurrent.CompletableFuture<T>` triển khai cả `Future<T>` lẫn `CompletionStage<T>`. Nó biểu diễn một kết quả có thể:

- Chưa hoàn tất.
- Hoàn tất bình thường với giá trị `T` (giá trị này có thể là `null` theo contract).
- Hoàn tất thất bại với exception hoặc do cancellation.

Một ví dụ:

```java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> user =
        CompletableFuture.supplyAsync(() -> "Lan");

CompletableFuture<String> greeting =
        user.thenApply(name -> "Xin chào, " + name);

System.out.println(greeting.join()); // Xin chào, Lan
```

`supplyAsync` khởi tạo một tác vụ bất đồng bộ để cung cấp giá trị. `thenApply` tạo **stage phụ thuộc**, được thực hiện khi stage trước hoàn tất bình thường; `join()` chờ kết quả và có thể block người gọi.

Khác với callback tự thiết kế, `CompletionStage` đã định nghĩa sẵn các phép **biến đổi, nối tiếp, kết hợp và xử lý lỗi**. Nhưng nó không tự cung cấp timeout cho mọi I/O bên dưới, không bảo đảm tự hủy chuỗi tác vụ và không quyết định kiến trúc backpressure thay ứng dụng.

## 5. Ba phép ghép CompletableFuture quan trọng

### 5.1. `thenApply`: biến đổi giá trị của một stage

```java
CompletableFuture<Integer> length =
        CompletableFuture.completedFuture("Java 27")
                .thenApply(String::length);

System.out.println(length.join()); // 7
```

Hàm `String -> Integer` biến đổi một giá trị đã có thành giá trị mới. Nếu stage nguồn hoàn tất thất bại, hàm biến đổi không chạy và lỗi được chuyển tới stage phụ thuộc theo quy tắc exceptional completion.

### 5.2. `thenCompose`: bước sau cũng trả CompletionStage

Giả sử một hàm tra hồ sơ trả future; bước tiếp theo tra quyền cũng trả future:

```java
import java.util.concurrent.CompletableFuture;

static CompletableFuture<String> findUser(String id) {
    return CompletableFuture.completedFuture("user-" + id);
}

static CompletableFuture<String> findRole(String user) {
    return CompletableFuture.completedFuture("reader");
}

CompletableFuture<String> role =
        findUser("u1").thenCompose(user -> findRole(user));

System.out.println(role.join()); // reader
```

Nếu dùng `thenApply(user -> findRole(user))` sẽ tạo `CompletableFuture<CompletableFuture<String>>`, tức future lồng future. `thenCompose` **làm phẳng** kết quả: `T -> CompletionStage<U>` trở thành một stage của `U`.

**Quy tắc nhớ:** `thenApply` cho `T -> U`, `thenCompose` cho `T -> CompletionStage<U>`.

### 5.3. `thenCombine`: ghép hai công việc độc lập

```java
CompletableFuture<String> profile =
        CompletableFuture.completedFuture("Lan");

CompletableFuture<String> permissions =
        CompletableFuture.completedFuture("reader");

CompletableFuture<String> summary =
        profile.thenCombine(permissions,
                (name, roleName) -> name + " (" + roleName + ")");

System.out.println(summary.join()); // Lan (reader)
```

`thenCombine` chỉ chạy hàm kết hợp khi **cả hai stage hoàn tất bình thường**. Nếu chúng được khởi chạy riêng và độc lập, cả hai có thể tiến triển đồng thời.

Nhưng `thenCombine` **không tự khởi chạy** hai tác vụ: với ví dụ `completedFuture`, dữ liệu đã có sẵn. Muốn tạo hai công việc thực sự, cần dùng API bất đồng bộ từ nguồn hoặc `supplyAsync` với executor thích hợp.

## 6. `allOf`, `anyOf` và giới hạn quản lý tác vụ

`CompletableFuture.allOf(a, b, ...)` tạo future hoàn tất khi toàn bộ đầu vào hoàn tất (hoặc hoàn tất thất bại theo hợp đồng). Nó **không trả trực tiếp danh sách kết quả**; người gọi phải đọc từng future.

```java
var a = CompletableFuture.completedFuture(10);
var b = CompletableFuture.completedFuture(20);

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
all.join();

int sum = a.join() + b.join();
System.out.println(sum); // 30
```

`CompletableFuture.anyOf(a, b, ...)` tạo future hoàn tất theo stage đầu vào **được hoàn tất đầu tiên**, dù thành công hay thất bại. Kết quả có kiểu `CompletableFuture<Object>` nếu dùng API thông thường, nên cần xử lý kiểu phù hợp.

Hai điều cần cảnh giác:

- `anyOf` không đồng nghĩa với **“đợi kết quả thành công đầu tiên”**; một future thất bại trước có thể làm kết quả chung thất bại.
- Hoàn tất của `allOf`/`anyOf` **không mặc nhiên hủy các tác vụ anh em**. Nếu chọn winner rồi muốn dừng losers, ứng dụng phải có cơ chế quản lý cancellation thực sự.

Với nhiều tác vụ có quan hệ cha–con cần xử lý thất bại và hủy theo scope, phải xem xét mô hình vòng đời trước khi tạo hàng loạt future không có người sở hữu.

## 7. Tác vụ chạy trên thread/executor nào?

Đây là một trong những điểm quyết định giữa `CompletableFuture` và virtual threads.

Javadoc của `CompletableFuture` phân biệt:

- Các phương thức **không có hậu tố `Async`** như `thenApply` có thể chạy action trên thread hoàn tất future trước, hoặc thread khác tham gia quá trình completion. **Không được giả định chúng luôn chạy trên thread đăng ký callback hay một thread đặc biệt.**
- Các phương thức `...Async` **không cung cấp `Executor`** thường dùng `ForkJoinPool.commonPool()` làm default asynchronous executor của `CompletableFuture`, với quy tắc fallback khi common pool không đáp ứng mức parallelism tối thiểu.
- Các overload `...Async(..., executor)` dùng executor mà ứng dụng cung cấp, giúp quản lý rõ tài nguyên và thời điểm chạy.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.CompletableFuture;

try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    CompletableFuture<String> message =
            CompletableFuture.supplyAsync(() -> "java", executor)
                    .thenApply(String::toUpperCase)
                    .thenApplyAsync(s -> s + " 27", executor);

    System.out.println(message.join()); // JAVA 27
}
```

Không nên đặt các thao tác blocking I/O dài vào `ForkJoinPool.commonPool()` một cách vô thức. Shared pool có thể phục vụ những công việc khác của ứng dụng và không phải không gian tài nguyên dành riêng cho network/database.

Nếu thực sự cần CF để **composition** và tác vụ bên dưới dùng blocking API, có thể cấp executor phù hợp, kể cả virtual-thread-per-task executor. Nhưng nếu cả luồng công việc vốn đã là **một chuỗi blocking lệnh dễ đọc**, dùng một virtual thread và mã tuần tự thường đơn giản hơn.

### 7.1. Dùng Async hay non-Async không chỉ là lựa chọn “nhanh hơn”

```java
CompletableFuture<String> result = getProfileAsync()
        .thenApply(Profile::displayName)
        .thenApplyAsync(name -> expensiveTransform(name), cpuExecutor);
```

Đoạn này là **mã minh họa kiến trúc** (cần có `Profile`, `getProfileAsync()` và `cpuExecutor` trong dự án). `thenApply` phù hợp cho biến đổi nhỏ; `thenApplyAsync(..., cpuExecutor)` thể hiện mong muốn chạy phần chuyển đổi riêng trên executor có chính sách CPU thích hợp.

Không nên chuyển **mọi** stage thành `...Async`: việc chuyển executor tạo thêm scheduling và phức tạp hơn, trong khi lợi ích phụ thuộc workload.

## 8. Xử lý lỗi của CompletableFuture

Với CF, lỗi có thể được quan sát mà không viết callback lỗi riêng trên từng bước:

| API | Dùng khi | Kết quả |
| --- | --- | --- |
| `exceptionally(error -> fallback)` | Muốn fallback khi lỗi | Một stage với giá trị bình thường nếu handler phục hồi |
| `handle((value, error) -> ...)` | Muốn xem cả kết quả lẫn exception | Một stage có thể đổi kiểu/giá trị |
| `whenComplete((value, error) -> ...)` | Ghi log/cleanup theo completion | Thường giữ kết quả hoặc lỗi gốc nếu action bình thường |
| `get()` | Chờ và dùng checked exception | Ném `ExecutionException` khi xử lý thất bại |
| `join()` | Chờ và dùng unchecked wrapper | Ném `CompletionException` khi lỗi thích hợp |

Ví dụ phục hồi:

```java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> greeting =
        CompletableFuture.<String>failedFuture(
                new IllegalStateException("Backend không sẵn sàng"))
                .exceptionally(error -> "(đang bảo trì)");

System.out.println(greeting.join()); // (đang bảo trì)
```

Ví dụ giữ logic thành công/thất bại riêng:

```java
CompletableFuture<String> display =
        CompletableFuture.completedFuture("Lan")
                .handle((name, error) ->
                        error == null ? "Xin chào " + name : "(lỗi)");
```

**Không nuốt mọi exception bằng `exceptionally(e -> null)`** chỉ để luồng “thành công”: việc này dễ khiến lỗi hạ tầng bị diễn giải là không có dữ liệu. Cần quyết định chính sách lỗi theo nghiệp vụ, đồng thời giữ hoặc ghi nhận nguyên nhân quan trọng.

### 8.1. `get()` so với `join()`

```java
var failed = CompletableFuture.<String>failedFuture(
        new IllegalArgumentException("Sai đầu vào"));
```

- `failed.get()` báo `ExecutionException` (checked) có thể đọc `getCause()`.
- `failed.join()` báo `CompletionException` (unchecked) có thể đọc `getCause()`.
- Cả `get` và `join` đều **có thể block** khi future chưa xong.
- Với hủy, có thể gặp `CancellationException` tùy đường hoàn tất.

Chọn `get` khi muốn thể hiện hợp đồng checked exceptions; chọn `join` khi đang ở tầng code phù hợp với unchecked exception. Không gọi `join` trong các callback/event-loop threads nhạy cảm với blocking nếu future có thể chưa hoàn thành.

## 9. Timeout không đồng nghĩa với hủy tác vụ gốc

CF hỗ trợ:

```java
CompletableFuture<String> request = fetchAsync();

request.orTimeout(500, java.util.concurrent.TimeUnit.MILLISECONDS);
```

`orTimeout` hoàn tất chính **CompletableFuture đó** theo dạng exceptional completion với `TimeoutException` nếu nó chưa xong vào hạn. Nó **không bảo đảm ngắt HTTP request, transaction hoặc thread** đang làm công việc bên dưới.

Một lựa chọn khác:

```java
request.completeOnTimeout(
        "giá trị dự phòng", 500, java.util.concurrent.TimeUnit.MILLISECONDS);
```

`completeOnTimeout` cũng có tác động tới chính future nhận phương thức: nó hoàn tất bình thường với fallback nếu chưa xong vào hạn, **không đơn thuần tạo một bản sao có deadline**.

Nếu nhiều bên dùng chung một future, gắn timeout vào nó có thể ảnh hưởng tới tất cả nơi cùng chờ. Hãy xác định rõ quyền sở hữu future và trách nhiệm đặt deadline.

### 9.1. `CompletableFuture.cancel(true)` khác `Future.cancel(true)` từ executor

Đây là sự khác biệt lớn:

- Với `CompletableFuture`, `cancel(true)` được triển khai như **exceptional completion**. Theo Javadoc, tham số `mayInterruptIfRunning` **không có tác dụng**, vì interruption không được dùng để điều khiển processing của CF.
- Với `Future` nhận từ `ExecutorService.submit`, `cancel(true)` có thể **cố gắng interrupt thread** đang chạy task nếu implementation có thể làm việc đó.

Ví dụ:

```java
// CF biểu diễn việc đã bị hủy về mặt kết quả,
// nhưng không bảo đảm tác vụ I/O nguồn bị interrupt.
CompletableFuture<String> cf = new CompletableFuture<>();
cf.cancel(true);
System.out.println(cf.isCancelled()); // true
```

Trong tích hợp thực tế, muốn hủy **I/O thực** phải dùng cancellation API của HTTP client/driver hoặc giữ handle/Future tới task được thực thi. Với virtual-thread-per-task executor, `Future.cancel(true)` là một cơ chế **yêu cầu** thread dừng, nhưng vẫn phụ thuộc việc code phản hồi interruption; không phải lệnh dừng cưỡng bức tức thì.

### 9.2. Timeout chờ kết quả của virtual-thread task

```java
import java.util.concurrent.*;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> task = executor.submit(() -> {
        Thread.sleep(10_000);
        return "done";
    });

    try {
        System.out.println(task.get(100, TimeUnit.MILLISECONDS));
    } catch (TimeoutException timeout) {
        task.cancel(true);
        System.out.println("Đã yêu cầu hủy");
    }
}
```

Ở đây `get(100, ...)` chỉ giới hạn **thời gian chờ của người gọi**; `cancel(true)` là bước riêng để cố gắng dừng task. `ExecutorService.close()` tại cuối scope chờ các task theo hợp đồng shutdown, vì thế việc thiết kế timeout/cleanup vẫn cần chủ động.

## 10. Virtual thread: giữ code blocking ở dạng tuần tự

Với API Java blocking truyền thống, code thường đơn giản nhất khi thể hiện một request bằng một luồng thực thi:

```java
static OrderSummary loadSummary(String orderId) throws Exception {
    Order order = orderRepository.load(orderId);       // Blocking I/O
    Customer customer = customerGateway.load(order.customerId()); // Blocking I/O
    return summarize(order, customer);
}
```

Đoạn trên là **mã minh họa kiến trúc**; các class và component cần được cài đặt trong ứng dụng.

Nếu gọi từ một virtual thread, thread có thể chờ I/O mà runtime **thường** giải phóng carrier platform thread khi thao tác chặn hỗ trợ unmount. Code vẫn dùng `try/catch/finally`, stack trace và debugger theo dòng điều khiển thông thường.

Tạo virtual thread trực tiếp:

```java
Thread task = Thread.ofVirtual().start(() -> {
    System.out.println("virtual=" + Thread.currentThread().isVirtual());
});

task.join();
```

Khi có nhiều yêu cầu, thường dùng:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    var first = executor.submit(() -> "response-A");
    var second = executor.submit(() -> "response-B");

    System.out.println(first.get() + ", " + second.get());
}
```

Kết quả:

```text
response-A, response-B
```

**Một virtual thread cho mỗi task không phải virtual-thread pool.** Executor này tạo virtual thread mới cho mỗi task đã được chấp nhận, không tái sử dụng một nhóm worker virtual threads cố định.

Virtual threads phù hợp nhất khi có nhiều tác vụ độc lập và chủ yếu **chờ I/O**. Chúng **không làm phép tính CPU đơn lẻ chạy nhanh hơn**. Nếu CPU là điểm nghẽn, cần đo và giới hạn parallelism theo CPU hoặc dùng thiết kế phù hợp với công việc tính toán.

## 11. Khi nào chọn virtual thread thay vì chuỗi CompletableFuture?

Giả sử nghiệp vụ là:

1. Tra hồ sơ người dùng.
2. Tra trạng thái tài khoản.
3. Kiểm tra quyền và dựng response.
4. Ghi audit dù thành công hay thất bại.

Nếu các lời gọi đầu vào đều là **blocking API** và các bước phụ thuộc nhau, virtual thread thường biểu đạt tự nhiên:

```java
static Response processRequest(String userId) {
    try {
        User user = userRepository.get(userId);
        Account account = accountRepository.get(user.accountId());
        return buildResponse(user, account);
    } finally {
        auditRequest(userId);
    }
}
```

Đây là pseudocode dùng các component nghiệp vụ. Đặt nó trong virtual-thread task cho phép dùng **mã tuần tự** và `finally` mà không phải chia nghiệp vụ ra nhiều stage callback.

Nếu các nguồn dữ liệu đã trả **CompletionStage** vốn không chặn, đừng thêm một virtual thread chỉ để gọi `join()` cho từng kết quả một cách máy móc. `thenCompose`/`thenCombine` có thể giữ được composition không chặn một cách tự nhiên.

Với hai yêu cầu **độc lập**, có thể thực hiện song song bằng virtual-thread executor:

```java
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {

    var profile = executor.submit(() -> loadProfile());
    var settings = executor.submit(() -> loadSettings());

    var view = combine(profile.get(), settings.get());
}
```

Đây cũng là mã minh họa cần các hàm nghiệp vụ tương ứng. Chú ý gửi **cả hai task trước** rồi mới `get()`; nếu gửi một task và chờ xong mới gửi task thứ hai thì sẽ đánh mất khả năng chồng thời gian I/O.

## 12. Khi nào CompletableFuture tốt hơn virtual-thread workflow?

`CompletableFuture` thường hợp lý khi:

- Có API cung cấp sẵn `CompletionStage<T>` từ HTTP client hoặc thư viện event-driven.
- Cần **pipeline** biến đổi kết quả: `thenApply`, `thenCompose`.
- Cần **fan-out/fan-in** một số công việc, rồi ghép kết quả: `thenCombine`, `allOf`.
- Cần trả một handle để người gọi chọn **gắn thêm continuation** mà không chờ.
- Đang ở framework non-blocking có quy tắc rõ ràng về event loop và callback threads.
- Không có lợi khi tạo thêm thread chỉ để bridge một API đã async.

Virtual thread lại hợp lý khi:

- API hiện có là blocking JDBC, HTTP client blocking hoặc đọc/ghi I/O tuần tự.
- Mỗi request có một luồng điều khiển rõ, nhiều bước nghiệp vụ và cleanup.
- Cần giữ stack trace theo lời gọi trực tiếp cùng `try/catch/finally`.
- Có nhiều tác vụ I/O độc lập và muốn dùng API blocking quen thuộc.

**Đây không phải cuộc cạnh tranh về tốc độ tuyệt đối.** Chọn theo API thật và đo trên workload thật. Một cách có ít dòng code hơn có thể thắng về bảo trì mà không nhất thiết thắng về throughput.

## 13. Chuyển callback thành CompletableFuture khi cần composition

Nếu thư viện bên ngoài **chỉ** cung cấp callback một kết quả, có thể tạo adapter:

```java
import java.util.concurrent.CompletableFuture;

static CompletableFuture<String> findUserFuture(
        String id, UserGateway gateway) {

    CompletableFuture<String> result = new CompletableFuture<>();

    try {
        gateway.findUser(id, new ResultCallback<>() {
            @Override
            public void completed(String user) {
                result.complete(user);
            }

            @Override
            public void failed(Throwable error) {
                result.completeExceptionally(error);
            }
        });
    } catch (RuntimeException error) {
        result.completeExceptionally(error);
    }

    return result;
}
```

Hai interface `UserGateway` và `ResultCallback` là các interface minh họa ở mục 3.

Lợi ích của adapter:

- Caller có thể dùng `thenApply`/`thenCompose`/`handle` mà không viết callback lồng.
- `CompletableFuture.complete(...)` hoặc `completeExceptionally(...)` chỉ hoàn tất thành công trạng thái **một lần**; các lần hoàn tất thêm không ghi đè kết quả đầu.
- Exception ném **đồng bộ từ lời gọi đăng ký** cũng được chuyển thành kết quả lỗi, nếu contract cho phép.

Giới hạn quan trọng:

1. Adapter chỉ bảo vệ trạng thái hoàn tất của future; nó **không tự sửa** API callback có thể gọi hai lần hoặc rò rỉ tài nguyên.
2. Exception do **callback implementation bên trong SDK** xử lý thế nào tùy contract SDK.
3. `result.cancel(true)` **không tự động gọi** cơ chế hủy request của SDK. Nếu API cung cấp `cancelHandle`, adapter cần thiết kế cầu nối cancellation theo ownership cụ thể.
4. Nếu API trả dòng nhiều sự kiện, không nên ép toàn bộ vào một `CompletableFuture<T>`: nó chỉ biểu diễn **một lần hoàn tất**, không phải stream.

## 14. Kết hợp CompletableFuture với virtual-thread executor

Có trường hợp muốn giữ API trả CF để caller composition, nhưng phần triển khai sử dụng thư viện blocking.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService blockingExecutor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    CompletableFuture<String> result =
            CompletableFuture.supplyAsync(() -> "user-27", blockingExecutor)
                    .thenApply(String::toUpperCase);

    System.out.println(result.join()); // USER-27
}
```

Điều này **hợp lệ**: `CompletableFuture` là **mô hình kết quả/composition**, còn virtual thread là **cách thực thi** hàm `Supplier`.

Tuy nhiên, có hai điểm cần kiểm soát:

- Đóng executor **trước khi** các tác vụ dùng nó được gửi sẽ gây lỗi; ứng dụng phải xác định vòng đời executor.
- `CompletableFuture.cancel(true)` **không tự động interrupt virtual thread** đang thực hiện `supplyAsync`. Nếu cần cancellation thực chất, giữ handle tới tác vụ (hoặc dùng API quản lý task thích hợp) thay vì chỉ hủy wrapper.

Đừng dựng một chuỗi CF phức tạp quanh các blocking call chỉ vì muốn “trông hiện đại”. Nếu caller không cần composition và luồng thực thi đơn giản, một `Callable<T>` nộp vào virtual-thread executor có thể ít tầng trạng thái hơn.

## 15. Vòng đời cha–con, hủy các tác vụ liên quan

Một yêu cầu có thể khởi chạy hai tác vụ song song. Nếu một tác vụ thất bại, bạn có thể muốn **hủy tác vụ kia**, ngăn để request còn sống lâu hơn client hoặc deadline.

Một đoạn với Future:

```java
import java.util.concurrent.*;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<String> user = executor.submit(() -> fetchUser());
    Future<String> role = executor.submit(() -> fetchRole());

    try {
        String response = user.get() + "/" + role.get();
        System.out.println(response);
    } catch (InterruptedException error) {
        user.cancel(true);
        role.cancel(true);
        Thread.currentThread().interrupt();
        throw error;
    } catch (ExecutionException error) {
        user.cancel(true);
        role.cancel(true);
        throw error;
    }
}
```

Ví dụ cần cài đặt `fetchUser` và `fetchRole`; trong code thực phải cân nhắc cả timeout, nguyên nhân lỗi và cleanup. Đoạn mã cho thấy **người điều phối chịu trách nhiệm hủy task khác**, không tự động xảy ra chỉ vì có hai `Future`.

**Cần lưu ý:** nếu thread gọi `get()` bị interrupt, khôi phục interrupt flag có ích cho contract cao hơn, nhưng khi dùng `ExecutorService.close()` trong cùng scope, shutdown/wait cũng có thể chịu tác động của interruption. Chính sách lifecycle cần được thiết kế ở mức ứng dụng.

### 15.1. Structured concurrency và trạng thái API

Các JDK hiện đại có hướng **structured concurrency**: nhóm các tác vụ con trong một phạm vi rõ ràng, để quản lý fail-fast, cancellation và observability nhất quán. Tuy nhiên, trong các JDK đã công bố gần đây, API structured concurrency vẫn đang qua các **vòng preview**, vì vậy không nên trình bày một phiên bản preview như API mặc định ổn định của Java 27 nếu chưa xác nhận trạng thái chính thức của release mục tiêu.

Bài này dùng `ExecutorService`/`Future` và `CompletableFuture` — các API chuẩn ổn định — làm nền tảng. Với dự án muốn dùng structured concurrency, cần kiểm tra JEP và tài liệu của **đúng bản JDK đang triển khai**, bật preview theo yêu cầu của bản đó và chấp nhận khả năng API thay đổi.

## 16. Thread-local, ngữ cảnh request và continuation

Chuyển từ lời gọi tuần tự sang callback hoặc future không chỉ thay đổi cách lấy kết quả; nó còn thay đổi **thread có thể chạy logic của bạn**.

Ví dụ:

```java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();
```

Nếu bạn set `REQUEST_ID` ở thread xử lý HTTP rồi đăng ký một callback, không thể mặc định callback sẽ được gọi trong **cùng Thread** hoặc đọc được giá trị local đó. Tương tự:

- `thenApply` có thể chạy tại thread đang hoàn tất stage, không nhất thiết là thread của nơi đăng ký.
- `thenApplyAsync` dùng executor tương ứng.
- Một virtual thread có **thread-local riêng**; carrier platform thread không phải nơi lưu request context cho virtual thread.
- `InheritableThreadLocal` có quy tắc kế thừa riêng lúc tạo thread; không phải lời giải chung cho mọi cross-executor continuation.

Một cách an toàn và rõ ràng khi cần correlation ID là **truyền context tường minh**:

```java
record RequestContext(String requestId, String tenantId) {}

static String decorate(String result, RequestContext context) {
    return context.requestId() + ": " + result;
}
```

Người gọi:

```java
RequestContext context = new RequestContext("req-27", "tenant-a");

CompletableFuture<String> labeled =
        CompletableFuture.completedFuture("OK")
                .thenApply(result -> decorate(result, context));
```

Context là giá trị được capture, không phụ thuộc thread chạy stage. Với context bảo mật hoặc transaction, phải tuân theo chính sách propagation của framework; không chỉ dựa vào tên thread, carrier hoặc việc CF được tạo trong cùng HTTP request.

**Chú ý:** Capturing một mutable object không làm object đó thread-safe. Nếu callback/stage thay đổi cùng trạng thái chia sẻ, vẫn cần đồng bộ thích hợp hoặc thiết kế bất biến.

## 17. Backpressure: không mô hình nào tự tạo tài nguyên vô hạn

Giả sử ứng dụng nhận 50.000 yêu cầu và database chỉ có 30 connection:

- Callback có thể tạo hàng chục nghìn **pending callbacks**.
- CF có thể tạo hàng chục nghìn **uncompleted stages**.
- Virtual-thread executor có thể tạo hàng chục nghìn **virtual threads** đang chờ.

Tất cả vẫn giữ dữ liệu, trạng thái, timeout hoặc tài nguyên khác. Chúng chỉ khác nhau ở cách biểu diễn công việc.

Một điểm kiểm soát truy cập tài nguyên có thể dùng `Semaphore`:

```java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(30);

String query(String key) throws InterruptedException {
    permits.acquire();
    try {
        return runQuery(key);
    } finally {
        permits.release();
    }
}
```

Đây là pseudocode trong một lớp có `runQuery` phù hợp. `Semaphore` giới hạn số tác vụ **thực sự vào vùng truy vấn**, không hạn chế số task/future đã được tạo và đang chờ permit. Với tải rất lớn, cần thêm **admission control**, bounded queues, rate limits và chính sách từ chối yêu cầu tại ranh giới nhận.

**Không pool virtual threads để giới hạn database connections.** Giới hạn đúng tài nguyên cần bảo vệ. Với CF, cũng không gửi mọi blocking call vào common pool rồi kỳ vọng pool đó tự kiểm soát tải tới downstream service.

## 18. Lựa chọn mô hình theo một quy trình thực tế

Hãy đi theo các câu hỏi:

1. **API nguồn trả gì?** Nếu nó đã trả `CompletionStage<T>`, tiếp tục composition bằng CF thường tự nhiên. Nếu chỉ có callback, cân nhắc giữ callback hoặc adapter sang CF.
2. **Nguồn có phải blocking I/O?** Nếu đúng và workload cần concurrency lớn, virtual threads là ứng viên mạnh.
3. **Là một kết quả cuối hay dòng nhiều sự kiện?** Callback/listener hoặc `Flow.Publisher` phù hợp hơn CF đơn lẻ cho stream.
4. **Các bước phụ thuộc nhau hay độc lập?** Phụ thuộc: code tuần tự trong virtual thread hoặc `thenCompose`. Độc lập: gửi cùng lúc rồi `thenCombine`/`allOf` hoặc nhiều `Future`.
5. **Ai cần nhận kết quả?** Caller cần tiếp tục không chờ: CF. Caller xử lý trong cùng request thread: blocking code trên virtual thread có thể dễ hiểu hơn.
6. **Có timeout/cancellation thật không?** Phân biệt hủy trạng thái kết quả và hủy computation/I/O nguồn.
7. **Có cần giữ context xuyên nhiều thread?** Truyền tường minh hoặc dùng cơ chế propagation đã được định nghĩa.
8. **Tác vụ CPU-bound hay I/O-bound?** Virtual threads ưu tiên cho chờ I/O; CPU-bound cần giới hạn parallelism thích hợp.
9. **Có nguy cơ gửi quá nhiều công việc?** Đặt giới hạn ingress/downstream và quan sát tài nguyên.
10. **Nhóm tác vụ có phải cùng một vòng đời?** Thiết kế ownership, cleanup và khả năng hủy task anh em.
11. **Có đo được không?** Benchmark trên workload thực tế: latency, throughput, số kết nối, heap, CPU, scheduler overhead.
12. **Đội ngũ dễ bảo trì kiểu nào?** Hợp đồng rõ ràng và khả năng kiểm thử quan trọng hơn việc code dùng nhiều cú pháp bất đồng bộ.

### 18.1. Bảng quyết định ngắn

| Tình huống | Ưu tiên cân nhắc | Lý do |
| --- | --- | --- |
| SDK chỉ có callback cho một kết quả | Callback, hoặc bridge sang CF | Không cần viết lại SDK |
| API đã trả `CompletionStage<T>` | `CompletableFuture`/`CompletionStage` | Ghép các stage không chặn |
| Chuỗi thao tác JDBC blocking phụ thuộc nhau | Virtual thread | Dễ dùng `try/catch/finally` |
| Hai API async độc lập và cần kết hợp | `thenCombine`/`allOf` | Fan-out/fan-in theo stage |
| Hai blocking I/O độc lập và cần kết hợp | Virtual-thread executor + `Future` | Gửi hai task rồi chờ kết quả |
| Nhiều sự kiện liên tục | Callback/listener hoặc `Flow.Publisher` | CF đơn lẻ không đại diện cho stream |
| Tính toán CPU nặng | Executor/parallelism được giới hạn theo CPU | VT không làm CPU nhanh hơn |
| Task cần bị interrupt khi timeout | `Future.cancel(true)` với nguồn hỗ trợ interrupt | `CF.cancel(true)` không ngắt underlying task |
| Cần composition public API nhưng blocking implementation | CF với executor phù hợp hoặc tách adapter | Hai mô hình có thể kết hợp |
| Cần fail-fast và quản lý tác vụ con theo scope | Mô hình lifecycle rõ; cân nhắc structured concurrency nếu bản JDK hỗ trợ ở trạng thái chấp nhận được | Tránh orphan tasks |

## 19. Chương trình Java 27 hoàn chỉnh: cùng một nghiệp vụ theo ba cách

Ví dụ sau dùng **cùng tác vụ tìm tên và quyền** để minh họa:

- Callback thông báo một kết quả.
- CF kết hợp hai kết quả.
- Virtual-thread executor chạy hai `Callable` và chờ `Future`.

Đây là **mô phỏng trong bộ nhớ**, không phải benchmark hoặc thử tải I/O; mã được cố ý làm ngắn và tạo đầu ra xác định.

Tạo file `AsyncChoiceDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncChoiceDemo {

    interface Callback<T> {
        void completed(T value);
        void failed(Throwable error);
    }

    static String userName(String id) {
        return "user-" + id;
    }

    static String role(String id) {
        return "reader";
    }

    static void findUser(
            String id, Executor executor, Callback<String> callback) {

        executor.execute(() -> {
            String result;
            try {
                if (id.isBlank()) {
                    throw new IllegalArgumentException("ID trống");
                }
                result = userName(id);
            } catch (RuntimeException failure) {
                callback.failed(failure);
                return;
            }
            callback.completed(result);
        });
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            // Cách 1: callback, bridge sang future chỉ để main chờ in kết quả.
            CompletableFuture<String> fromCallback = new CompletableFuture<>();

            findUser("42", executor, new Callback<>() {
                @Override
                public void completed(String value) {
                    fromCallback.complete(value);
                }

                @Override
                public void failed(Throwable error) {
                    fromCallback.completeExceptionally(error);
                }
            });

            System.out.println("Callback: " + fromCallback.join());

            // Cách 2: tạo hai future độc lập, kết hợp kết quả.
            CompletableFuture<String> user =
                    CompletableFuture.supplyAsync(
                            () -> userName("42"), executor);

            CompletableFuture<String> permission =
                    CompletableFuture.supplyAsync(
                            () -> role("42"), executor);

            CompletableFuture<String> combined =
                    user.thenCombine(permission,
                            (name, p) -> name + "/" + p);

            System.out.println("CompletableFuture: " + combined.join());

            // Cách 3: mỗi Callable được chạy trong một virtual thread.
            Future<String> userTask =
                    executor.submit(() -> userName("42"));

            Future<String> roleTask =
                    executor.submit(() -> role("42"));

            System.out.println("Virtual thread: "
                    + userTask.get() + "/" + roleTask.get());
        }
    }
}
```

Biên dịch và chạy bằng JDK 27, không cần bật preview:

```bash
javac -encoding UTF-8 AsyncChoiceDemo.java
java AsyncChoiceDemo
```

Kết quả:

```text
Callback: user-42
CompletableFuture: user-42/reader
Virtual thread: user-42/reader
```

### 19.1. Phân tích ý nghĩa thay vì so tốc độ

- Callback nhận `result` qua `completed(...)`, không cung cấp handle trả về trong chữ ký ban đầu. Demo dùng `CompletableFuture` **chỉ để main chờ kết quả callback** cho dễ kiểm chứng.
- CF dùng `supplyAsync` và `thenCombine`. Hai lời gọi `userName`, `role` **không phụ thuộc nhau**.
- Executor dùng `submit` với hai `Callable`; `get()` chỉ được gọi sau khi gửi cả hai task.
- Mọi tác vụ trong ví dụ cùng sử dụng `newVirtualThreadPerTaskExecutor()`. Vì thế demo **không so sánh mức sử dụng tài nguyên** của callback event loop thật với CF trên common pool hoặc virtual-thread workflow thật.
- `try-with-resources` quản lý vòng đời executor; khi thoát scope, executor shutdown và chờ theo hợp đồng.

Khi thay hai hàm giả bằng network/database API, cần thêm **timeout, cancellation thực tế, giới hạn kết nối, retry chính sách và tracing**. Mẫu code chỉ cung cấp cách bố trí cấu trúc, không tự giải quyết những yêu cầu sản xuất đó.

## 20. Những lỗi triển khai thường gặp

| Lỗi/giả định | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Coi callback luôn chạy async và trên thread khác | API có thể gọi ngay/trên thread khác không dự đoán | Đọc contract và bảo vệ reentrancy |
| Báo lỗi trong `catch` bao luôn `callback.completed` | Có thể gọi cả success rồi failure | Tách tính toán kết quả và thông báo callback |
| Lồng callback nhiều tầng không có error/cancel path | Rất khó cleanup và xử lý lỗi | Dùng adapter CF hoặc thiết kế state machine rõ |
| Dùng `thenApply` cho hàm trả `CompletableFuture<U>` | Tạo nested future | Dùng `thenCompose` |
| Giả định `thenApply` luôn chạy trên thread đăng ký | Không được bảo đảm | Dùng `...Async(..., executor)` khi cần ràng buộc executor |
| Chạy blocking I/O lâu trên common pool | Tranh chấp pool phục vụ nhiều tác vụ | Chọn executor phù hợp hoặc virtual thread |
| Gọi `join()` trong event-loop thread | Có thể block thread điều khiển I/O | Dùng continuation hoặc chuyển sang context thích hợp |
| Dùng `anyOf` rồi tin rằng chọn success đầu tiên | Exception đầu tiên cũng có thể thắng | Thiết kế chính sách winner thành công riêng |
| Gắn `orTimeout` vào shared future mà không biết nó mutate state | Caller khác cũng bị ảnh hưởng | Rõ ownership/deadline, dùng stage riêng khi phù hợp |
| Nghĩ `CF.cancel(true)` interrupt underlying task | Tham số interrupt bị bỏ qua trong CF | Dùng cancellation của task/I/O nguồn |
| Nghĩ `Future.get(timeout)` tự hủy việc chạy | Chỉ dừng chờ | Tự quyết định `cancel(true)` và timeout I/O |
| Quên đọc Future hoặc lỗi ở CF | Lỗi task có thể không được ghi nhận | Quy định rõ ai tiêu thụ exceptional completion |
| Pool virtual threads để hạn chế DB | Giới hạn sai tài nguyên | Pool DB connection, semaphore và ingress control |
| Đưa vô hạn request vào per-task executor | VT rẻ không có nghĩa memory/I/O vô hạn | Backpressure và admission control |
| Dùng ThreadLocal của request khi continuation đổi thread | Không tự truyền context | Truyền context hoặc cơ chế propagation có contract |
| Nhầm virtual threads tăng tốc CPU | CPU vẫn có giới hạn core | Giới hạn concurrency và đo workload |
| Không đóng executor/không giới hạn task treo | Resource leaks, shutdown chờ lâu | Lifecycle, timeout, cancellation, cleanup |
| Coi preview structured concurrency là API chắc chắn ổn định | Có thể chưa final ở release mục tiêu | Kiểm tra trạng thái JEP/JDK và build flags |
| Cho rằng callback, CF và VT buộc chọn loại trừ nhau | Chúng ở các tầng trừu tượng khác nhau | Dùng bridge/adapter có chủ đích nếu hợp lý |

## 21. Checklist thiết kế và kiểm thử

Khi lựa chọn mô hình cho một tính năng bất đồng bộ:

1. Ghi rõ **đầu vào** là callback, future hay hàm blocking.
2. Xác định công việc có một kết quả cuối hay dòng sự kiện nhiều lần.
3. Đánh dấu những bước **phụ thuộc nhau** và **độc lập**.
4. Chỉ định **executor/thread policy** cho các công việc có chi phí lớn.
5. Quy định **success/error contract**: callback lỗi, exceptional completion hoặc exception qua `Future.get`.
6. Có **deadline** cho request và **timeout tại nguồn I/O**.
7. Biết hủy **kết quả** hay hủy **công việc thực**, và ai chịu trách nhiệm.
8. Chỉ cho phép số lượng công việc tới downstream phù hợp với tài nguyên thực tế.
9. Có **backpressure** khi tốc độ nhận request lớn hơn sức xử lý.
10. Không dùng ThreadLocal vô thức trong continuation chạy trên executor khác.
11. Đảm bảo cleanup luôn chạy ở các đường đi thành công, thất bại và hủy.
12. Kiểm thử callback chạy đồng bộ, bất đồng bộ, trả lỗi, đến muộn hoặc bị gọi lặp nếu API cho phép.
13. Kiểm thử CF thất bại sớm, `allOf`/`anyOf` và timeout/cancel semantics.
14. Kiểm thử virtual thread task bị interrupt khi `sleep` hoặc I/O đang chờ.
15. Xác định ai **chờ kết thúc toàn bộ nhóm task** khi request đóng hoặc ứng dụng shutdown.
16. Đo latency, throughput, memory, connections và CPU trên hệ thống thực trước khi tối ưu.

**Kết luận:** Chọn **callback** khi API nguồn và cơ chế event listener phù hợp; chọn **`CompletableFuture`** khi cần biến đổi/ghép những kết quả bất đồng bộ thành một pipeline; chọn **virtual thread** khi muốn dùng mã blocking tuần tự cho rất nhiều tác vụ chờ I/O. Có thể kết hợp chúng, nhưng luôn thiết kế rõ **vòng đời, hủy thực sự, tài nguyên và ngữ cảnh tác vụ**.

## 22. Tài liệu chính thức

- [`java.util.concurrent.CompletableFuture` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `CompletionStage`, `thenApply`, `thenCompose`, `thenCombine`, `allOf`, `anyOf`, `orTimeout`, `cancel` và executor policy.
- [`java.util.concurrent.CompletionStage` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html): hợp đồng completion stage và các continuations.
- [`java.util.concurrent.Future` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, `cancel(true)` và completion status.
- [`java.util.concurrent.ExecutorService` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý lifecycle, `submit`, `close`, `shutdownNow`.
- [`java.util.concurrent.Executors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor` và các executor factories.
- [`java.lang.Thread` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html): `ofVirtual`, `isVirtual`, interruption và thread lifecycle.
- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): thiết kế virtual threads cho nhiều blocking I/O tasks, giới hạn CPU, threading và tài nguyên.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mục đích của mô hình thread-per-task hiện đại.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): cập nhật hành vi pinning của `synchronized` từ JDK 24; tránh áp dụng khuyến nghị cũ không còn phù hợp.
