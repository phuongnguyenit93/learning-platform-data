# CompletableFuture.runAsync và supplyAsync trong Java

`CompletableFuture` là API lập trình bất đồng bộ trong `java.util.concurrent`, được giới thiệu từ **Java 8** và vẫn được hỗ trợ trên các phiên bản Java hiện đại. Hai phương thức tĩnh thường dùng nhất để **khởi tạo một tác vụ bất đồng bộ** là `runAsync(...)` và `supplyAsync(...)`:

- **`runAsync(Runnable)`**: chạy một hành động **không sinh giá trị trả về** cho future. Kết quả là `CompletableFuture<Void>`, hoàn thành bình thường với `null`.
- **`supplyAsync(Supplier<U>)`**: chạy một hàm **sinh giá trị kiểu U**. Kết quả là `CompletableFuture<U>` chứa giá trị do supplier trả về.

Cả hai có overload nhận thêm `Executor` để điều khiển nơi thực thi tác vụ. Nếu không truyền executor, chúng dùng chính sách thực thi bất đồng bộ mặc định của `CompletableFuture`, thông thường là `ForkJoinPool.commonPool()`.

~~~java
CompletableFuture<Void> action =
    CompletableFuture.runAsync(
        () -> System.out.println("Đã ghi nhật ký")
    );

CompletableFuture<Integer> answer =
    CompletableFuture.supplyAsync(() -> 21 * 2);
~~~

Đây là đoạn minh họa, cần import `java.util.concurrent.CompletableFuture`. Tác vụ có thể được lên lịch và chạy ở thread khác; **không giả định** hai dòng output nào sẽ xuất hiện trước nếu các thread cùng in ra console. Trong ứng dụng thực tế, cần **giữ reference của future** để xử lý thành công, lỗi và thời điểm hoàn tất.

Bài này thuộc phần **CompletableFuture** của Java 8, giải thích đầy đủ cách chọn `runAsync`/`supplyAsync`, hợp đồng executor, nhận kết quả, nối chuỗi xử lý, lỗi, timeout, hủy, giới hạn thread pool, an toàn dữ liệu chia sẻ và ví dụ Java hoàn chỉnh. Những kiến thức dưới đây vẫn có giá trị hiện tại, không dựa trên API đã lỗi thời.

## 1. Bảng đối chiếu nhanh hai phương thức

| Tiêu chí | `runAsync` | `supplyAsync` |
| --- | --- | --- |
| Hàm nhận vào | `Runnable` | `Supplier<U>` |
| Phương thức chức năng | `void run()` | `U get()` |
| Future trả về | `CompletableFuture<Void>` | `CompletableFuture<U>` |
| Giá trị khi thành công | `null`, vì kiểu `Void` không chứa kết quả tác vụ | Giá trị `U` do supplier trả, **có thể là null** |
| Tác vụ thích hợp | Gửi tín hiệu, ghi log/metric, hành động không cần trả kết quả | Tính toán, tải dữ liệu, gọi dịch vụ cần trả response |
| Có overload `Executor`? | Có | Có |
| Nếu callback ném lỗi | Future hoàn thành **exceptionally** | Future hoàn thành **exceptionally** |
| Kết hợp với bước sau | `thenRun`, `thenCompose`, `whenComplete`... | `thenApply`, `thenCompose`, `thenAccept`, `thenCombine`... |

Bốn chữ ký API cơ bản:

~~~java
static CompletableFuture<Void> runAsync(Runnable runnable)
static CompletableFuture<Void> runAsync(
    Runnable runnable, Executor executor)

static <U> CompletableFuture<U> supplyAsync(
    Supplier<U> supplier)
static <U> CompletableFuture<U> supplyAsync(
    Supplier<U> supplier, Executor executor)
~~~

Các chữ ký trên là **mô tả API**, không phải mã có thể khai báo tự do ở bên ngoài một class. `Runnable` thuộc `java.lang`; `Supplier` thuộc `java.util.function`; `Executor` và `CompletableFuture` thuộc `java.util.concurrent`.

**Câu hỏi thực hành:** khi phần việc kết thúc, bước tiếp theo có cần **dữ liệu do nó tạo ra** không? Nếu có, chọn `supplyAsync`. Nếu chỉ cần biết tác vụ **đã hoàn tất hoặc thất bại**, `runAsync` rõ ý hơn.

## 2. `runAsync`: thực thi hành động, kết quả `Void`

Một tác vụ không cần trả dữ liệu:

~~~java
AtomicInteger sent = new AtomicInteger();

CompletableFuture<Void> sendTask =
    CompletableFuture.runAsync(() -> {
        sent.incrementAndGet();
    });

sendTask.join(); // Chờ hoàn tất hoặc ném CompletionException.
System.out.println(sent.get()); // 1 nếu không có writer khác.
~~~

Đây là **mã minh họa**, cần import `CompletableFuture` và `AtomicInteger`. `AtomicInteger` được dùng vì nếu nhiều task cập nhật cùng một biến thì phép tăng phải có cơ chế thread-safe; tính an toàn của `CompletableFuture` **không** tự làm phép tăng của biến nguyên thông thường thành atomic.

### 2.1. Vì sao `CompletableFuture<Void>`?

`runAsync` nhận `Runnable` có phương thức `run()` trả `void`. Không có kiểu kết quả nghiệp vụ để lưu trong future, nên future được khai báo `CompletableFuture<Void>`. Khi hoàn thành **bình thường**:

~~~java
CompletableFuture<Void> done =
    CompletableFuture.runAsync(() -> { });

Void result = done.join();
// result == null
~~~

`null` ở đây là kết quả đúng của kiểu `Void`, không phải dấu hiệu task chưa chạy. Phân biệt:

- **Chưa hoàn tất:** `isDone() == false`.
- **Thành công:** `join()` trả `null`.
- **Thất bại:** `join()` ném `CompletionException` mang cause gốc (với một số trường hợp hủy có `CancellationException`).

Không dùng `join() == null` để kết luận ngay rằng một future chưa hoàn tất; bản thân `join()` sẽ chờ nếu cần.

### 2.2. Side effect không có nghĩa “fire and forget” an toàn

Nếu công việc là ghi audit, gửi email hay cập nhật dữ liệu quan trọng, **không thể chỉ gọi `runAsync` rồi bỏ qua future** và tin rằng tác vụ đã hoàn tất trước khi process/request kết thúc.

~~~java
// Thiết kế cần tránh khi kết quả tác vụ quan trọng:
CompletableFuture.runAsync(() -> writeAuditRecord());
~~~

Đây là phản ví dụ không độc lập; `writeAuditRecord` do ứng dụng định nghĩa. Nếu callback ném exception, future có trạng thái thất bại nhưng ứng dụng không giữ reference để quan sát. Nếu JVM kết thúc hoặc request bị hủy, việc submit tác vụ không phải cam kết nó sẽ hoàn tất, không tự retry, không tự tạo giao dịch hay xác nhận từ hệ thống bên ngoài.

Nếu hành động cần bảo đảm giao hàng hoặc bền vững, hãy cân nhắc hàng đợi/job system, transactional outbox, idempotency và giám sát phù hợp, ngoài `CompletableFuture` trong một JVM.

## 3. `supplyAsync`: tính và trả giá trị qua future

Khi công việc cần tạo dữ liệu:

~~~java
CompletableFuture<Integer> result =
    CompletableFuture.supplyAsync(() -> 40 + 2);

int value = result.join();
// value == 42
~~~

`Supplier<U>.get()` trả một giá trị kiểu `U`. Java suy luận tham số kiểu từ lambda hoặc ngữ cảnh của lời gọi.

~~~java
CompletableFuture<String> account =
    CompletableFuture.supplyAsync(() -> "A-100");

CompletableFuture<List<String>> names =
    CompletableFuture.supplyAsync(
        () -> Arrays.asList("An", "Bình", "Chi"));
~~~

Đây là các đoạn minh họa, cần import `CompletableFuture`, `List` và `Arrays`. `CompletableFuture<U>` chứa **giá trị được tạo ra trong tương lai**, không phải `U` có sẵn khi gọi phương thức.

### 3.1. Supplier trả `null` vẫn có thể là thành công

~~~java
CompletableFuture<String> empty =
    CompletableFuture.supplyAsync(() -> null);

boolean normal = empty.join() == null;
// normal == true; supplier đã hoàn thành bình thường.
~~~

Đừng dùng `future.join() == null` làm trạng thái “chưa có kết quả” nếu supplier được phép trả null. Nếu nghiệp vụ cần phân biệt “không tìm thấy dữ liệu” với “chưa hoàn tất”, định nghĩa kiểu kết quả phù hợp như `Optional<T>`, sealed result model hoặc trạng thái domain rõ ràng; `CompletableFuture` chỉ biểu diễn **việc tính toán**, không tự định nghĩa nghĩa nghiệp vụ của `null`.

### 3.2. Không dùng `runAsync` chỉ để lén xuất dữ liệu ra shared field

~~~java
// Phản ví dụ: side effect lên biến được chia sẻ khó quản lý.
AtomicReference<String> holder = new AtomicReference<>();

CompletableFuture<Void> task =
    CompletableFuture.runAsync(
        () -> holder.set("loaded"));
~~~

Đoạn này dùng `AtomicReference` để tránh một phần vấn đề visibility nhưng thiết kế vẫn có **hai nơi** cần đọc: future và holder. Nếu mục đích là lấy `"loaded"`, dùng:

~~~java
CompletableFuture<String> task =
    CompletableFuture.supplyAsync(() -> "loaded");
~~~

Khi `join()` trả về, kết quả đã nằm trong chính future. Việc luân chuyển dữ liệu qua pipeline rõ ràng hơn và ít state shared mutable hơn.

## 4. Nơi thực thi tác vụ: default commonPool hay Executor riêng?

### 4.1. Không truyền `Executor`

~~~java
CompletableFuture<Integer> work =
    CompletableFuture.supplyAsync(() -> 42);
~~~

Với `CompletableFuture` chuẩn, các phương thức `*Async` không có executor tường minh thường dùng `ForkJoinPool.commonPool()`. Tài liệu class còn quy định trường hợp common pool không hỗ trợ mức song song lớn hơn một có thể dùng **thread mới cho mỗi async task**. Vì vậy **đừng hứa** một tên thread, một pool size hay một thứ tự chạy tuyệt đối chỉ từ việc gọi `supplyAsync`.

`ForkJoinPool.commonPool()` là pool dùng chung trong JVM, cũng được dùng bởi nhiều tác vụ/framework khác. Nó phù hợp nhiều công việc tính toán ngắn, nhưng không phải một “thread vô hạn” để đẩy mọi tác vụ blocking vào.

### 4.2. Truyền `Executor` tường minh

~~~java
ExecutorService ioPool =
    Executors.newFixedThreadPool(4);

try {
    CompletableFuture<String> task =
        CompletableFuture.supplyAsync(
            () -> "data", ioPool);

    System.out.println(task.join()); // data
} finally {
    ioPool.shutdown();
}
~~~

Mã minh họa này cần import `ExecutorService`, `Executors` và `CompletableFuture`. Dùng `Executor` riêng có thể giúp:

- Kiểm soát **mức độ song song**, tránh một thành phần chiếm hết commonPool.
- Phân tách nhóm việc CPU-bound và blocking I/O.
- Đặt quy tắc đặt tên thread, quản lý exception, metrics, queue và rejection policy qua executor phù hợp.
- Có điểm rõ ràng để quản lý **lifecycle** và shutdown ở cấp ứng dụng.

**Đừng tạo một `newFixedThreadPool` mới mỗi request rồi quên shutdown**. Trong dịch vụ, executor thường được quản lý ở cấp component/application, có cấu hình capacity, backpressure và lifecycle rõ ràng.

### 4.3. Các trường hợp blocking I/O

`supplyAsync(() -> jdbcCall())` về mặt API có thể chạy, nhưng khi `jdbcCall()` chặn thread lâu, đẩy hàng nghìn lời gọi vào commonPool có thể tạo contention hoặc starvation với công việc khác. Cấu hình một executor phù hợp cho blocking I/O, giới hạn số kết nối/đồng thời, timeout và cơ chế từ chối tải.

Với **Java 21+**, virtual threads là lựa chọn hiện hành đáng cân nhắc cho nhiều tác vụ blocking I/O khi thư viện tương thích, ví dụ executor `Executors.newVirtualThreadPerTaskExecutor()`. Đây là API **không có trong Java 8**; phần ví dụ chạy được của bài vẫn dùng executor Java 8. Virtual threads cũng không xóa giới hạn database/network, không biến task thành non-blocking I/O và không tự tạo backpressure.

### 4.4. CommonPool có daemon workers: phải quan sát việc hoàn tất

ForkJoinPool worker thông thường là daemon thread. Chương trình Java có thể kết thúc nếu main không còn giữ tiến trình hoạt động, dù tác vụ async chưa xong. Vì vậy trong ví dụ command-line, nên `join()`/`get()` trước khi thoát; trong service, quản lý task lifetime theo lifecycle và yêu cầu độ bền của công việc.

**Không gọi `ForkJoinPool.commonPool().shutdown()` để “dọn dẹp riêng” các task của mình.** Common pool là tài nguyên toàn cục, các lời gọi shutdown bình thường không có tác dụng giống pool do ứng dụng tự tạo.

## 5. Bất đồng bộ lúc khởi tạo không có nghĩa mọi bước sau đều chạy trên thread khác

Một future trả về nhanh và đại diện cho tác vụ còn đang chạy hoặc đã hoàn tất. Nhưng mã gọi `join` sẽ **chặn đến khi có kết quả** nếu chưa hoàn tất:

~~~java
CompletableFuture<Integer> future =
    CompletableFuture.supplyAsync(() -> expensiveCalculation());

// Làm việc độc lập trong khi task tính toán.
doOtherWork();

// Tới đây mới chờ nếu vẫn chưa hoàn tất.
int value = future.join();
~~~

Đây là đoạn minh họa không độc lập; `expensiveCalculation`/`doOtherWork` do ứng dụng định nghĩa. Nếu ngay lập tức gọi `join()` thì quy trình quan sát từ caller có thể gần như đồng bộ: không tự có lợi thế concurrency nếu chẳng có việc gì để chồng lấp.

### 5.1. `thenApply` khác `thenApplyAsync`

~~~java
CompletableFuture<Integer> number =
    CompletableFuture.supplyAsync(() -> 21);

CompletableFuture<Integer> doubled =
    number.thenApply(x -> x * 2);
~~~

`thenApply` là một **dependent stage** thực hiện khi source stage hoàn thành bình thường. Nó **không tự bảo đảm** một thread khác được tạo hay task được lên lịch lên pool riêng. Hành động non-async có thể được thực hiện bởi thread hoàn thành stage trước hoặc thread gọi phương thức completion liên quan. Tránh suy luận về thread name hoặc thứ tự timing.

Nếu muốn hành động continuation được **lên lịch bất đồng bộ**:

~~~java
CompletableFuture<Integer> doubledAsync =
    number.thenApplyAsync(x -> x * 2);
~~~

Overload không có executor dùng default asynchronous execution facility của stage đó; overload có executor giúp chọn nơi chạy:

~~~java
CompletableFuture<Integer> doubledOnPool =
    number.thenApplyAsync(x -> x * 2, executor);
~~~

Đây là đoạn minh họa; `executor` phải được cung cấp. Không mặc định callback của `thenApply`/`thenAccept`/`whenComplete` luôn chạy ở commonPool; nếu policy thread quan trọng, chọn các overload `Async(..., executor)` thích hợp.

## 6. Cách nối các bước tiếp theo với `runAsync` và `supplyAsync`

### 6.1. Nối sau `runAsync`

~~~java
CompletableFuture<Void> action =
    CompletableFuture.runAsync(() -> saveMessage());

CompletableFuture<Void> after =
    action.thenRun(() -> recordCompletion());
~~~

Mã minh họa, `saveMessage` và `recordCompletion` thuộc ứng dụng. `thenRun` không nhận giá trị đầu vào, phù hợp vì upstream `runAsync` không sinh kết quả. Nếu `action` hoàn thành exceptional, dependent `thenRun` thường không được chạy và downstream sẽ ở trạng thái lỗi theo hợp đồng `CompletionStage`.

### 6.2. Biến đổi kết quả `supplyAsync` với `thenApply`

~~~java
CompletableFuture<String> upper =
    CompletableFuture.supplyAsync(() -> "java")
        .thenApply(String::toUpperCase);
// Kết quả sau khi hoàn tất: "JAVA"
~~~

`thenApply` nhận giá trị upstream và trả giá trị mới. Kiểu của future downstream có thể khác upstream:

~~~java
CompletableFuture<Integer> length =
    CompletableFuture.supplyAsync(() -> "java")
        .thenApply(String::length);
// Kết quả: 4
~~~

Không cần `join` ở giữa hai bước. Chỉ `join/get` tại **ranh giới thật sự cần đồng bộ**, hoặc tiếp tục trả future cho tầng gọi cao hơn.

### 6.3. Dùng `thenAccept` khi chỉ tiêu thụ kết quả

~~~java
CompletableFuture<Void> printed =
    CompletableFuture.supplyAsync(() -> "ready")
        .thenAccept(value -> System.out.println(value));
~~~

`thenAccept` nhận kết quả upstream rồi thực hiện hành động kiểu `Consumer<T>`, trả future `Void`. Còn `thenRun` chỉ chạy hành động **không nhận** kết quả, phù hợp khi không cần value.

Với side effect quan trọng, vẫn cần giữ/quan sát `printed` để biết downstream đã hoàn thành và có lỗi hay không; một `thenAccept` không biến việc gửi dữ liệu ra hệ thống ngoài thành giao dịch.

### 6.4. `thenCompose` cho bước trả thêm một future

Giả sử sau khi có userId, cần gọi một API bất đồng bộ để lấy hồ sơ:

~~~java
CompletableFuture<String> profile =
    CompletableFuture.supplyAsync(() -> "user-7")
        .thenCompose(userId ->
            CompletableFuture.supplyAsync(
                () -> "profile:" + userId
            )
        );
~~~

`thenCompose` **flatten** một `CompletionStage<U>` được trả từ callback thành `CompletableFuture<U>` downstream. Nếu dùng `thenApply` với callback trả future, kiểu sẽ thành **`CompletableFuture<CompletableFuture<String>>`**, thường khó dùng hơn nếu không có ý định giữ future lồng.

**Không gọi `join` bên trong `thenCompose` chỉ để lấy kết quả của tác vụ thứ hai**. Trả future để pipeline tự ghép, giảm nguy cơ block thread xử lý stage.

### 6.5. `thenCombine` và `allOf` cho tác vụ độc lập

Nếu cần hai kết quả độc lập:

~~~java
CompletableFuture<String> a =
    CompletableFuture.supplyAsync(() -> "JAVA");

CompletableFuture<Integer> b =
    CompletableFuture.supplyAsync(() -> 42);

CompletableFuture<String> combined =
    a.thenCombine(b, (text, num) -> text + ":" + num);
// Kết quả: "JAVA:42"
~~~

`thenCombine` chờ **hai stage cùng hoàn tất bình thường**, rồi kết hợp kết quả.

Khi có nhiều tác vụ khác kiểu, `CompletableFuture.allOf(a, b, ...)` trả **`CompletableFuture<Void>`** hoàn tất sau khi tất cả future đưa vào hoàn tất; nếu một future lỗi, kết quả chung cũng lỗi. `allOf` **không tự tổng hợp giá trị**; sau khi barrier thành công, truy cập `a.join()`, `b.join()` hoặc kết hợp chúng bằng stage phù hợp.

## 7. Xử lý ngoại lệ: task thất bại không biến mất chỉ vì chạy async

Cả `Runnable.run` và `Supplier.get` nếu ném exception trong task thì future thường hoàn thành **exceptionally**. Future có thể được truyền qua pipeline, nơi downstream không có handler thích hợp cũng có thể hoàn thành lỗi.

~~~java
CompletableFuture<Integer> future =
    CompletableFuture.supplyAsync(() -> {
        throw new IllegalArgumentException("bad input");
    });
~~~

Đoạn trên là minh họa: vì lambda chỉ ném lỗi, khi cần chắc chắn về kiểu generic có thể viết `CompletableFuture.<Integer>supplyAsync(...)`.

**Không thấy stack trace trên console không có nghĩa task thành công.** Nếu bạn không quan sát future, lỗi có thể bị bỏ qua ở tầng nghiệp vụ.

### 7.1. `join` và `get` khác nhau như thế nào?

| Phương thức | Nếu thành công | Khi future chưa xong | Khi task lỗi |
| --- | --- | --- | --- |
| `join()` | Trả `T` hoặc `null` với `Void` | Chờ | Ném unchecked `CompletionException` chứa cause gốc; cancellation có `CancellationException` |
| `get()` | Trả `T` | Chờ, có thể bị interrupt | Ném checked `ExecutionException`; có `InterruptedException` |
| `get(timeout, unit)` | Trả `T` | Chờ tối đa một khoảng thời gian | Có thể ném checked `TimeoutException`/`ExecutionException`/`InterruptedException` |

`get(timeout, unit)` là API có từ Java 8 và là cách hạn chế **thời gian chờ của caller**, không tự bảo đảm tác vụ nền được dừng. Khi catch `InterruptedException`, thường cần khôi phục cờ interrupt của thread hoặc truyền lỗi lên tầng phù hợp, tùy chính sách ứng dụng.

### 7.2. `exceptionally`: thay kết quả lỗi bằng fallback

~~~java
CompletableFuture<String> safe =
    CompletableFuture.<String>supplyAsync(() -> {
        throw new IllegalStateException("service unavailable");
    }).exceptionally(error -> "fallback");

// safe.join() == "fallback"
~~~

Callback của `exceptionally` chỉ chạy khi upstream hoàn thành exceptional, nhận một `Throwable` và trả fallback **cùng kiểu T**. Nó không retry tác vụ gốc; chỉ chuyển kết quả lỗi thành kết quả fallback theo logic bạn viết.

Với `runAsync` trả `CompletableFuture<Void>`, handler của `exceptionally` phải trả `Void`, thường là `null` nếu muốn đánh dấu đã xử lý lỗi:

~~~java
CompletableFuture<Void> safeRun =
    CompletableFuture.runAsync(() -> {
        throw new IllegalStateException("failed");
    }).exceptionally(error -> {
        System.err.println("Action failed: " + error);
        return null;
    });
~~~

Đây là minh họa về cách xử lý một failure; khi sản phẩm cần audit, hãy ghi lỗi có ngữ cảnh, tránh trả `null` rồi che mọi thất bại quan trọng.

### 7.3. `handle` và `whenComplete`

- **`handle((value, error) -> ...)`** chạy trên cả thành công và thất bại, có thể **tạo kết quả mới** và chuyển từ exceptional sang normal nếu handler trả thành công.
- **`whenComplete((value, error) -> ...)`** cũng chạy trong cả hai tình huống để **quan sát** hoặc thực hiện side effect. Nó **không phải** cơ chế phục hồi mặc định; downstream tiếp tục mang kết quả hoặc lỗi của upstream, ngoại trừ quy tắc khi chính callback cũng ném lỗi.
- **`exceptionally`** xử lý nhánh thất bại và cung cấp fallback cùng kiểu.

~~~java
CompletableFuture<Integer> parsed =
    CompletableFuture.supplyAsync(() -> 5)
        .handle((value, error) ->
            error == null ? value * 2 : -1);
// Kết quả thành công: 10
~~~

Không đặt side effect không thể lặp lại vào các callbacks khi có retry ở tầng nghiệp vụ; `CompletableFuture` không tự đảm bảo exactly-once end-to-end với database hoặc dịch vụ từ xa.

### 7.4. Checked exceptions trong lambda

`Runnable.run` và `Supplier.get` **không khai báo checked exceptions**. Lambda trực tiếp gọi `Files.readAllBytes(...)` hoặc một API `throws IOException` cần tự xử lý hoặc bọc checked exception vào unchecked exception.

~~~java
CompletableFuture<String> text =
    CompletableFuture.supplyAsync(() -> {
        try {
            return Files.readString(path);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }, executor);
~~~

**Đây là minh họa dành cho Java 11+**, không phải mã Java 8 vì `Files.readString` xuất hiện sau Java 8. Nếu cần tương thích Java 8, dùng `new String(Files.readAllBytes(path), StandardCharsets.UTF_8)` hoặc API phù hợp. `path` và `executor` do ứng dụng cung cấp; cần imports tương ứng. Khi lỗi, outer future vẫn có thể mang `CompletionException` chứa cause bên trong là `UncheckedIOException`.

Đối với mã mới chạy trên JDK 17+, `Files.readString` là hiện hành và hợp lệ, nhưng phải ghi rõ mốc phiên bản thay vì gán nhầm mọi API cho Java 8.

## 8. Timeout, cancellation và giới hạn của việc “hủy task”

### 8.1. Java 8: thời hạn chờ bằng `get(timeout, unit)`

~~~java
try {
    String value = future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Caller đã chờ quá thời hạn cho phép.
}
~~~

Đoạn này là minh họa, cần biến `future` cùng imports; checked exceptions `InterruptedException` và `ExecutionException` cũng phải được xử lý hoặc khai báo ở method chứa nó. `get(timeout)` **chỉ giới hạn thời gian chờ**; nó không tự đặt timeout cho toàn bộ I/O bên trong supplier và không bảo đảm task đã dừng.

### 8.2. Java 9+ có `orTimeout` và `completeOnTimeout`

Từ **Java 9**, `CompletableFuture` có thêm:

~~~java
future.orTimeout(2, TimeUnit.SECONDS);

future.completeOnTimeout(
    fallbackValue, 2, TimeUnit.SECONDS);
~~~

Đây là mã minh họa Java 9+, không phải API Java 8. `orTimeout` khiến **chính future đó** hoàn thành exceptional với `TimeoutException` nếu chưa xong trong thời hạn. `completeOnTimeout` khiến future hoàn thành bình thường với fallback value nếu chưa xong. Hai phương thức trả lại `this CompletableFuture`.

**Quan trọng:** việc future kết thúc bởi timeout **không có nghĩa** tác vụ đang chạy, socket, database query hay request HTTP đã được ngắt/dừng. Timeout cấp future khác với timeout ở tầng I/O. Cần cấu hình timeout/cancel đúng ở thư viện I/O và có chiến lược quản lý tài nguyên.

### 8.3. `cancel(true)` không có nghĩa thread sẽ bị interrupt

Tài liệu `CompletableFuture.cancel(boolean mayInterruptIfRunning)` cho biết tham số `mayInterruptIfRunning` **không có tác dụng trong implementation này**, bởi interruption không được dùng làm cơ chế điều khiển xử lý. Nếu future chưa hoàn tất, cancel khiến future hoàn thành exceptional với `CancellationException`, và dependent stages quan sát trạng thái đó.

Vì vậy, **không thiết kế**:

~~~java
future.cancel(true);
// Sai nếu suy: chắc chắn supplier đã ngừng ngay lập tức.
~~~

Đây là mã minh họa. Nếu muốn dừng công việc thực, task và thư viện I/O phải hỗ trợ cancellation hợp tác, timeout ở nguồn, hoặc cơ chế interrupt trên executor phù hợp; không dựa vào `CompletableFuture.cancel` như một lệnh “kill thread”.

### 8.4. Không tự retry khi lỗi

`runAsync` và `supplyAsync` submit công việc theo một lời gọi; chúng không tự chạy lại khi callback thất bại. Nếu nghiệp vụ cần retry, phải thiết kế rõ số lần, backoff, giới hạn đồng thời và idempotency. Với hành động có side effect như thanh toán/gửi email, retry không kiểm soát có thể gây trùng sự kiện.

## 9. An toàn luồng của dữ liệu bên trong task

`CompletableFuture` là đối tượng phối hợp hoàn tất thread-safe, nhưng **callback do bạn viết** có thể thao tác trên trạng thái bất kỳ:

~~~java
int[] counter = {0};

CompletableFuture<Void> a =
    CompletableFuture.runAsync(() -> counter[0]++);

CompletableFuture<Void> b =
    CompletableFuture.runAsync(() -> counter[0]++);

CompletableFuture.allOf(a, b).join();
~~~

Đây là phản ví dụ về shared mutable state: `counter[0]++` là thao tác đọc–tăng–ghi không nguyên tử. Hai task có thể cùng thấy 0 và ghi 1, làm mất một lần tăng. Chờ bằng `allOf` bảo đảm task đã xong nhưng **không sửa lại race condition đã xảy ra trước đó**.

Một cách thay thế:

~~~java
AtomicInteger counter = new AtomicInteger();

CompletableFuture<Void> a =
    CompletableFuture.runAsync(counter::incrementAndGet);

CompletableFuture<Void> b =
    CompletableFuture.runAsync(counter::incrementAndGet);

CompletableFuture.allOf(a, b).join();
// counter.get() == 2 nếu không có thao tác khác.
~~~

`AtomicInteger.incrementAndGet` là thao tác cập nhật nguyên tử. Phương thức tham chiếu trả int nhưng có thể dùng trong ngữ cảnh `Runnable`, nơi giá trị trả bị bỏ qua; nếu muốn rõ ràng, viết `() -> counter.incrementAndGet()`.

**Thiết kế ưu tiên:** thay vì shared mutable state, trả kết quả từ `supplyAsync` rồi kết hợp qua `thenCombine`/`allOf` hoặc collector an toàn. Khi nhiều task cùng sửa file, map, list, database hay socket, mỗi tài nguyên vẫn có hợp đồng concurrency riêng.

### 9.1. `List`/`Map` shared không tự thread-safe

~~~java
List<String> results = new ArrayList<>();

CompletableFuture<Void> task =
    CompletableFuture.runAsync(() -> results.add("value"));
~~~

Nếu chỉ một task sử dụng list và main đọc sau khi join, tình huống có thể hợp lệ; nhưng **nhiều task đồng thời gọi `add` trên cùng `ArrayList`** không được đảm bảo an toàn. Có thể để mỗi task trả kết quả riêng qua `supplyAsync`, dùng cấu trúc concurrent hoặc thu thập kết quả trong một stage sau khi tất cả upstream hoàn tất.

### 9.2. Không block pool bằng cách đợi các task cùng pool

Một thiết kế dễ gây deadlock/starvation khi executor bị giới hạn:

~~~java
// PHẢN VÍ DỤ: pool một thread và task A chờ task B
// trong khi B cũng cần chính thread của pool đó.
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<String> a =
    CompletableFuture.supplyAsync(() -> {
        CompletableFuture<String> b =
            CompletableFuture.supplyAsync(
                () -> "B", single);
        return b.join(); // Có thể chờ vô hạn.
    }, single);
~~~

Đây là phản ví dụ, **không chạy để demo** vì có thể treo nếu không có cơ chế giới hạn và cleanup. Pool chỉ có một worker; A chiếm worker và chờ B, còn B không thể bắt đầu khi A chưa nhả worker.

Dùng `thenCompose` để kết nối future, thiết kế task không blocking, hoặc tổ chức executor phù hợp. Việc có nhiều thread hơn có thể tránh một ví dụ cụ thể nhưng **không thay thế thiết kế tránh dependency cycle**.

## 10. Chương trình Java hoàn chỉnh, kết quả không phụ thuộc lịch thread

Lưu chương trình thành **`RunSupplyAsyncDemo.java`**. Mã chỉ dùng API có từ Java 8, nên có thể biên dịch/chạy với JDK 17+; không dùng `now()`, sleep hoặc tên thread trong expected stdout.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class RunSupplyAsyncDemo {

    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newFixedThreadPool(3);

        AtomicInteger actions = new AtomicInteger();
        AtomicInteger handledErrors = new AtomicInteger();

        try {
            // runAsync: làm việc không sinh kết quả.
            CompletableFuture<Void> action =
                    CompletableFuture.runAsync(
                        () -> actions.incrementAndGet(),
                        executor
                    );

            // supplyAsync: sinh một kết quả kiểu Integer.
            CompletableFuture<Integer> number =
                    CompletableFuture.supplyAsync(
                        () -> 21 * 2,
                        executor
                    );

            // Sau supplyAsync, thenApply biến đổi giá trị.
            CompletableFuture<String> upper =
                    CompletableFuture.supplyAsync(
                        () -> "java",
                        executor
                    ).thenApply(String::toUpperCase);

            // thenCombine: ghép hai future độc lập.
            CompletableFuture<String> combined =
                    upper.thenCombine(
                        number,
                        (word, n) -> word + ":" + n
                    );

            // thenCompose: nối tác vụ tiếp theo mà không
            // tạo CompletableFuture<CompletableFuture<String>>.
            CompletableFuture<String> composed =
                    number.thenCompose(n ->
                        CompletableFuture.supplyAsync(
                            () -> "value=" + n,
                            executor
                        )
                    );

            // Khôi phục lỗi của một supplier bằng fallback.
            CompletableFuture<String> recovered =
                    CompletableFuture.<String>supplyAsync(
                        () -> {
                            throw new IllegalArgumentException(
                                "unavailable");
                        },
                        executor
                    ).exceptionally(error -> "fallback");

            // Cả runAsync cũng có thể báo lỗi.
            CompletableFuture<Void> handledAction =
                    CompletableFuture.runAsync(
                        () -> {
                            throw new IllegalStateException(
                                "cannot-write");
                        },
                        executor
                    ).exceptionally(error -> {
                        handledErrors.incrementAndGet();
                        return null;
                    });

            // Mỗi future trong barrier đã được xử lý
            // hoặc dự kiến hoàn tất bình thường.
            CompletableFuture<Void> barrier =
                    CompletableFuture.allOf(
                        action,
                        number,
                        upper,
                        combined,
                        composed,
                        recovered,
                        handledAction
                    );

            barrier.join();

            System.out.println("actionCount="
                    + actions.get());
            System.out.println("runValueIsNull="
                    + (action.join() == null));
            System.out.println("number=" + number.join());
            System.out.println("upper=" + upper.join());
            System.out.println("combined="
                    + combined.join());
            System.out.println("composed="
                    + composed.join());
            System.out.println("recovered="
                    + recovered.join());
            System.out.println("handledErrors="
                    + handledErrors.get());
            System.out.println("barrierValueIsNull="
                    + (barrier.join() == null));

            // Ví dụ không truyền executor: dùng
            // chính sách async mặc định của CompletableFuture.
            CompletableFuture<String> defaultTask =
                    CompletableFuture.supplyAsync(
                        () -> "default");
            System.out.println("defaultResult="
                    + defaultTask.join());

            // Xác minh lỗi gốc qua CompletionException.
            CompletableFuture<String> failed =
                    CompletableFuture.<String>supplyAsync(
                        () -> {
                            throw new IllegalArgumentException(
                                "invalid");
                        },
                        executor
                    );

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println("failureCause="
                    + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RunSupplyAsyncDemo.java
java RunSupplyAsyncDemo
~~~

**Đầu ra xác định** sau khi chờ các future hoàn thành:

~~~text
actionCount=1
runValueIsNull=true
number=42
upper=JAVA
combined=JAVA:42
composed=value=42
recovered=fallback
handledErrors=1
barrierValueIsNull=true
defaultResult=default
failureCause=IllegalArgumentException
~~~

### Giải thích chính xác từng kết quả

1. `actionCount=1`: một `runAsync` gọi `AtomicInteger.incrementAndGet`; `barrier.join` bảo đảm cập nhật đã hoàn tất trước khi in.
2. `runValueIsNull=true`: `CompletableFuture<Void>` từ `runAsync` hoàn thành bình thường với `null`; không có giá trị `U`.
3. `number=42`: `supplyAsync` chạy supplier trả `21*2`, và future lưu giá trị Integer.
4. `upper=JAVA`: `thenApply(String::toUpperCase)` nhận kết quả supplier `"java"`; không phải một `runAsync` tự có giá trị.
5. `combined=JAVA:42`: `thenCombine` đợi hai nguồn rồi ghép; thứ tự task kết thúc không ảnh hưởng chuỗi cuối cùng.
6. `composed=value=42`: `thenCompose` khởi chạy supplier thứ hai sau khi nhận số 42 và trả future phẳng.
7. `recovered=fallback`: supplier cố ý ném `IllegalArgumentException`, `exceptionally` trả String thay thế. Exception không bị coi là thành công “nguyên bản”.
8. `handledErrors=1`: lỗi của tác vụ `runAsync` được quan sát bằng `exceptionally` trên đúng future của nó, rồi handler trả `null` để stage phục hồi hoàn thành bình thường.
9. `barrierValueIsNull=true`: `allOf` trả `CompletableFuture<Void>` làm barrier, không tổng hợp danh sách giá trị.
10. `defaultResult=default`: task không truyền executor trả một String cố định; không in tên thread vì cách lên lịch phụ thuộc runtime.
11. `failureCause=IllegalArgumentException`: `join` của future bị lỗi ném `CompletionException`, và `getCause()` mang exception mà supplier đã ném.

**Điểm an toàn:** chương trình in stdout chỉ ở main sau khi cần thiết đã `join`. Executor tự tạo được `shutdown` ở `finally`. Không có chờ future bên trong worker của cùng pool gây deadlock; các callback có nội dung ngắn và dữ liệu được truyền qua future thay vì sửa một `ArrayList` chung.

Đây là minh họa về **tính đúng của API**, không phải benchmark tốc độ. Việc không thấy lỗi concurrency trong một lượt chạy không phải bằng chứng hệ thống khác chắc chắn thread-safe.

## 11. Vòng đời ứng dụng và tài nguyên

### 11.1. Bounded concurrency và backpressure

Nếu một dịch vụ nhận lượng request lớn rồi mỗi request gọi nhiều `supplyAsync`, hàng đợi task có thể tăng nhanh. `Executors.newFixedThreadPool(n)` cố định số worker nhưng thường dùng **queue không giới hạn** trong implementation chuẩn; không vì số thread cố định mà số tác vụ chờ tự bị giới hạn.

Trong production, nên xem xét:

- Số task đồng thời phù hợp với CPU, kết nối DB hoặc quota dịch vụ.
- Executor/ThreadPoolExecutor có queue giới hạn và rejection policy rõ.
- Giới hạn request/concurrency, backpressure và queue monitoring.
- Timeout phía thư viện I/O chứ không chỉ future completion.
- Thông tin trace/context cần được truyền hợp lệ vào task.
- Cơ chế graceful shutdown và đợi task quan trọng hoàn tất.

Không dùng `CompletableFuture` làm một **job queue bền vững**: nó phối hợp tính toán trong runtime hiện tại, không tự persist task qua process crash.

### 11.2. Error handling phải có chỗ kết thúc

Nếu một future lỗi mà không ai `join/get` hoặc attach error handler, business error có thể bị bỏ quên. Thiết kế nên xác định ai chịu trách nhiệm quan sát error: tầng service, API controller, batch job hay scheduler.

Một cách phổ biến là trả `CompletableFuture<T>` cho caller để caller quyết định hồi phục/timeout/chuyển sang HTTP error; không nhất thiết `join` ngay trong service rồi làm mất tính bất đồng bộ ở tầng gọi.

### 11.3. Context, transaction và security

Task bất đồng bộ có thể chạy trên thread khác. Các giá trị dựa vào `ThreadLocal` như một số request/security/transaction context **không tự được truyền đầy đủ** sang worker. Khi cần trace ID, tenant ID, user identity hoặc scope giao dịch, hãy truyền dữ liệu an toàn và rõ ràng vào callback hoặc dùng cơ chế propagation được framework hỗ trợ.

Không giả định giao dịch của thread gọi tự bao phủ mọi thao tác DB được submit qua `supplyAsync`. Kiểm tra contract của transaction manager và resource; có thể phải mở transaction tại worker hoặc cấu trúc lại boundary.

## 12. Các lỗi thực hành thường gặp

### Lỗi 1 — Chọn `runAsync` khi cần giá trị trả về

Nếu muốn tải profile, đừng đặt profile vào shared field rồi tạo `CompletableFuture<Void>`. Dùng `supplyAsync` trả kiểu `CompletableFuture<Profile>`, giúp stage sau nhận profile trực tiếp.

### Lỗi 2 — Nghĩ `supplyAsync` trả ngay `T`

~~~java
// Sai kiểu:
// String text = CompletableFuture.supplyAsync(() -> "data");

// Đúng:
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(() -> "data");
~~~

Lúc gọi, chỉ có **future của kết quả**. Giá trị thật có thể chưa được tính xong.

### Lỗi 3 — Nghĩ mọi stage `thenApply` chạy ở thread khác

`thenApply` không cam kết executor riêng. Nếu stage callback có chi phí lớn và cần policy scheduling riêng, dùng `thenApplyAsync(..., executor)`, đồng thời cân nhắc chi phí context-switch.

### Lỗi 4 — Gọi `join()` ở mọi bước

~~~java
// Dễ biến pipeline thành tuần tự/chặn:
String a = CompletableFuture
    .supplyAsync(() -> fetchA()).join();

String b = CompletableFuture
    .supplyAsync(() -> fetchB()).join();
~~~

Đây là mã minh họa, `fetchA`/`fetchB` do ứng dụng định nghĩa. Task B chỉ được submit sau khi A hoàn tất. Nếu chúng độc lập, submit cả hai future trước rồi dùng `thenCombine`/`allOf`; chỉ join khi thực sự cần kết quả ở boundary.

### Lỗi 5 — Submit blocking I/O không giới hạn vào commonPool

Tác vụ blocking dài có thể chiếm worker và ảnh hưởng các tác vụ khác dùng commonPool. Dùng executor phù hợp cho blocking, kết hợp timeouts, connection pool và backpressure.

### Lỗi 6 — Bỏ qua future của `runAsync`

Một action thất bại có thể để future exceptional mà caller không hề quan sát. Nếu side effect quan trọng, phải theo dõi failure, có retry/idempotency hoặc job system phù hợp; đừng cho rằng submit = hoàn tất.

### Lỗi 7 — Đoán thứ tự in console từ thứ tự gọi `runAsync`

Hai tác vụ async được submit theo thứ tự không có nghĩa thread xử lý/hoàn thành đúng thứ tự đó. Nếu cần thứ tự nghiệp vụ, nối stage có dependency hoặc dùng một executor/queue với semantics phù hợp.

### Lỗi 8 — Dùng `ArrayList` hoặc biến `int` chung không đồng bộ

Tính thread-safe của `CompletableFuture` chỉ bảo vệ cơ chế future, không bảo vệ trạng thái ứng dụng. Dùng `AtomicInteger`, immutable data, collection concurrent, proper locking hoặc kết quả riêng theo future.

### Lỗi 9 — Cho rằng `allOf` tự trả danh sách kết quả

`allOf` trả `CompletableFuture<Void>`. Sau barrier thành công, truy cập từng future hoặc tạo một stage kết hợp giá trị; xử lý exception của từng thành phần theo nghiệp vụ.

### Lỗi 10 — Dùng `thenApply` với hàm trả một future rồi quên flatten

Khi callback trả `CompletableFuture<U>`, `thenApply` có thể tạo future lồng. `thenCompose` làm pipeline phẳng hơn mà không cần block một worker bằng `join`.

### Lỗi 11 — Tưởng `get(timeout)` dừng task hoặc `cancel(true)` luôn interrupt

`get(timeout)` giới hạn chờ caller; `cancel` của CompletableFuture hoàn thành future theo trạng thái hủy và không dùng boolean argument để interrupt task. Muốn dừng I/O, cần hỗ trợ cancellation ở nguồn và chính sách tài nguyên.

### Lỗi 12 — Retry side effect mà không có idempotency

Nếu task gửi thanh toán rồi timeout ở tầng future, gửi lại có thể gây hai giao dịch ngay cả khi lần đầu vẫn chạy. Dùng idempotency keys, timeout I/O và xử lý outcome chưa rõ.

### Lỗi 13 — Cho rằng `Runnable`/`Supplier` nhận checked exception trực tiếp

Các functional interface này không khai báo checked exceptions. Cần xử lý hoặc wrap đúng, và giữ nguyên root cause để báo lỗi/gỡ lỗi.

### Lỗi 14 — Quên shutdown executor do mình tạo

Ứng dụng có thể giữ thread sống hoặc rò tài nguyên. Tái sử dụng executor ở cấp ứng dụng và shutdown theo lifecycle; không tạo pool mới vô hạn cho từng request.

### Lỗi 15 — Đồng nhất bất đồng bộ với không chặn

Mã submit async có thể không chặn tại thời điểm khởi tạo, nhưng `join/get` chặn caller. Blocking I/O trong callback vẫn chặn worker thread. Không coi `CompletableFuture` tự biến JDBC đồng bộ thành non-blocking driver.

### Lỗi 16 — Không biết mốc phiên bản của tiện ích mới

`runAsync/supplyAsync/thenCompose/allOf` có từ Java 8. `orTimeout`, `completeOnTimeout`, `delayedExecutor` có từ Java 9; executor virtual-thread-per-task thuộc Java 21+. Khi viết module dạy Java 8, ghi rõ API mới chỉ dùng ở phần mở rộng, không nhét vào mã tuyên bố chạy được Java 8.

## 13. Gợi ý thiết kế ứng dụng thực tế

### 13.1. Một phép tính CPU-bound

~~~java
CompletableFuture<Long> hash =
    CompletableFuture.supplyAsync(
        () -> calculateHash(input),
        cpuExecutor);
~~~

Đây là minh họa, `calculateHash`, `input`, `cpuExecutor` do ứng dụng cung cấp. Kiểm soát concurrency theo số core và chi phí thuật toán; không mặc định thêm nhiều worker hơn luôn nhanh.

### 13.2. Một truy vấn blocking có kết quả

~~~java
CompletableFuture<Customer> customer =
    CompletableFuture.supplyAsync(
        () -> repository.findCustomer(customerId),
        ioExecutor);
~~~

Đây là ví dụ pseudocode với các kiểu của ứng dụng. Kết quả future biểu diễn value trả về của truy vấn. Cấu hình timeout, transaction và connection pool ở phía truy vấn; nếu repository trả null khi không có khách, định nghĩa policy null rõ ràng.

### 13.3. Một hành động không trả kết quả

~~~java
CompletableFuture<Void> persisted =
    CompletableFuture.runAsync(
        () -> metrics.incrementCounter("accepted"),
        executor);
~~~

Đây là minh họa với `metrics` do ứng dụng cung cấp. Nếu hoàn thành bình thường, future không có result; nếu thất bại, phải xác định chính sách log/observe của caller. Không gọi `persisted.join()` ngay nếu tầng gọi muốn giữ bất đồng bộ.

### 13.4. Hai tác vụ độc lập với kết quả cần kết hợp

~~~java
CompletableFuture<User> user =
    CompletableFuture.supplyAsync(
        () -> loadUser(id), executor);

CompletableFuture<List<Order>> orders =
    CompletableFuture.supplyAsync(
        () -> loadOrders(id), executor);

CompletableFuture<UserView> view =
    user.thenCombine(orders,
        (u, list) -> new UserView(u, list));
~~~

Ví dụ này là pseudocode với kiểu miền ứng dụng. Hai task có thể được submit trước, pipeline kết hợp sau. Không tự tuyên bố chúng chắc chắn thực thi cùng lúc; concurrency thực tế phụ thuộc executor capacity và tài nguyên.

### 13.5. Dùng một task tiếp theo phụ thuộc kết quả trước

~~~java
CompletableFuture<Order> created =
    lookupCustomerAsync(customerId)
        .thenCompose(customer -> createOrderAsync(customer));
~~~

Ví dụ này là pseudocode. `thenCompose` thể hiện phụ thuộc và tránh lấy future lồng. Mỗi async method có thể chọn executor riêng, và các tầng caller có thể tiếp tục compose mà không phải block ngay.

## 14. Kiểm thử mà không phụ thuộc thời gian/thứ tự thread

Một test tốt nên kiểm tra **giá trị và trạng thái hoàn tất**, không hardcode tên thread hoặc thứ tự log từ nhiều worker.

- **`runAsync`:** assert một hành động thread-safe được thực thi sau `join()`; assert future hoàn thành bình thường và result `null`.
- **`supplyAsync`:** assert giá trị trả về đúng, và kiểu result như mong đợi.
- **Ngoại lệ:** assert `join` ném `CompletionException` với cause phù hợp, kiểm tra fallback `exceptionally` khi có/không có lỗi.
- **Chuỗi stage:** kiểm tra `thenApply`, `thenCompose`, `thenCombine` cho dữ liệu xác định; không giả định scheduler order.
- **Đa luồng:** dùng `CountDownLatch` để đồng bộ thời điểm bắt đầu nếu cần kiểm tra contention; không dùng sleep như biện pháp xác nhận completion.
- **Executor:** dùng test executor hoặc một pool nhỏ được quản lý; luôn cleanup, không để non-daemon thread treo test.
- **Timeout:** dùng nguồn công việc kiểm soát được và thời hạn hợp lý; kiểm tra cả trạng thái future lẫn hủy I/O nếu ứng dụng cần.
- **Side effects:** tránh test “không có exception” như bằng chứng task chỉ chạy đúng một lần trong hệ thống phân tán.
- **Khả năng tái lập:** dùng dữ liệu bất biến/counter atomic; đợi bằng Future/barrier; không yêu cầu hai worker in console theo một thứ tự bất kỳ.

Nếu một test concurrency chỉ thỉnh thoảng fail, không “chữa” bằng tăng `Thread.sleep`; cần tìm phụ thuộc chưa đồng bộ, executor starvation hoặc race condition thực tế.

## 15. Checklist trước khi sử dụng trong production

1. **Task có trả kết quả không?** Không → `runAsync` với `CompletableFuture<Void>`; có → `supplyAsync` với `CompletableFuture<U>`.
2. **Ai chịu trách nhiệm theo dõi future?** Không bỏ qua lỗi của action quan trọng.
3. **Executor nào?** Common pool hay executor tách theo loại workload? Đã giới hạn concurrency/queue chưa?
4. **Có blocking I/O không?** Cần I/O timeout, connection limits và pool/lifecycle thích hợp.
5. **Có gọi `join/get` quá sớm không?** Chỉ block tại ranh giới cần kết quả, tránh block worker chờ task cùng pool.
6. **Sau task sẽ làm gì?** `thenApply`, `thenAccept`, `thenRun`, `thenCompose`, `thenCombine` hay `allOf`?
7. **Cần điều khiển thread callback không?** Dùng `...Async(..., executor)` khi policy scheduling quan trọng.
8. **Lỗi được xử lý ra sao?** `exceptionally`/`handle`/`whenComplete`, logging có context và domain-specific fallback.
9. **Có checked exceptions?** Xử lý hoặc wrap nhưng vẫn giữ nguyên cause.
10. **Timeout/hủy đang bảo đảm điều gì?** Phân biệt timeout của caller, completion của future và task/I/O thực sự bị dừng.
11. **Có shared mutable state?** `CompletableFuture` không thay `AtomicInteger`, concurrent collection hoặc transaction.
12. **Task có cần bền vững qua restart?** Nếu có, dùng scheduler/queue/outbox chuyên dụng, không chỉ CompletableFuture trong heap.
13. **Lifecycle executor?** Không tạo/shutdown common pool tùy tiện; pool riêng phải được quản lý và đóng đúng lúc.
14. **API có từ phiên bản nào?** Phần Java 8 và phần Java 9+/21+ phải phân biệt.
15. **Đã đo thực tế?** Việc dùng async không tự tăng throughput, đặc biệt khi bottleneck nằm ở DB/network. Kiểm tra latency, throughput, queue, thread utilization và backpressure.

**Ghi nhớ:** `runAsync` biểu diễn **hành động hoàn thành không có giá trị trả về**, `supplyAsync` biểu diễn **phép tính sinh một giá trị bất đồng bộ**. Cả hai trả `CompletableFuture` để quan sát hoàn tất, nhận lỗi và compose pipeline. Sự an toàn và hiệu năng phụ thuộc vào **executor, workload, side effects, cách chờ, resource lifecycle và cách xử lý lỗi**, chứ không chỉ từ chữ “Async”. Đây là những nguyên tắc vẫn còn đúng trong Java hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 26 — CompletableFuture: runAsync, supplyAsync, dependent stages, completion, cancellation và timeouts](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 26 — CompletionStage: hợp đồng thenApply/thenCompose/thenCombine, normal và exceptional completion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 26 — ForkJoinPool: commonPool, worker threads và giới hạn của blocking I/O](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Oracle Java SE 26 — ExecutorService: lifecycle, shutdown, Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 26 — Runnable và Supplier](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html)
- [Oracle Java SE 26 — Executors: available factory methods, bao gồm virtual-thread executor trên Java mới](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Executors.html)
