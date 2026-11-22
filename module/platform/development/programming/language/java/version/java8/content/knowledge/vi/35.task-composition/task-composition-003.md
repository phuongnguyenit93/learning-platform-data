# applyToEither, acceptEither và runAfterEither trong CompletableFuture

Trong Java 8, `CompletableFuture` và giao diện `CompletionStage` hỗ trợ ghép nhiều tác vụ bất đồng bộ. Nhóm phương thức **`Either`** cho phép tạo bước xử lý tiếp theo phụ thuộc vào **một trong hai** stage nguồn, khác với nhóm `Both` đợi **cả hai**. Ba phương thức chính của bài này là:

- **`applyToEither(other, fn)`**: lấy một giá trị `T` của nguồn hoàn thành bình thường, gọi `Function<T,U>` để **tạo giá trị U**, trả `CompletableFuture<U>`.
- **`acceptEither(other, action)`**: lấy một giá trị `T` của nguồn hoàn thành bình thường, gọi `Consumer<T>` để **tiêu thụ giá trị**, trả `CompletableFuture<Void>`.
- **`runAfterEither(other, action)`**: kích hoạt `Runnable` khi một trong hai stage hoàn thành bình thường, **không nhận giá trị nguồn**, trả `CompletableFuture<Void>`.

Cả ba có các overload `...Async`, gồm biến thể nhận một `Executor`. Nhờ đó chương trình có thể tạo pipeline bất đồng bộ, điều khiển thread thực thi bước sau, và mô tả rõ khi nào một bước đã hoàn tất.

**Giới hạn quan trọng:** *Either* không phải phép “luôn lấy kết quả thành công đầu tiên, bỏ qua lỗi của nguồn còn lại”. Tài liệu chính thức của `CompletionStage` nói rằng **nếu stage phụ thuộc vào một trong hai nguồn và một nguồn hoàn thành exceptional, không có bảo đảm dependent stage kết thúc bình thường hay exceptional**. Không xây dựng failover production dựa trên giả định mạnh hơn hợp đồng đó. Ngoài ra, chọn được một kết quả **không tự hủy** tác vụ nguồn còn lại.

Các API này có từ **Java 8** và **vẫn hiện hành trong Java hiện đại**. Bài sử dụng đúng ngữ nghĩa hiện tại của Oracle Java SE, có mã Java chỉ dùng API có từ Java 8, chạy được với JDK 17+, và tách riêng các tiện ích mới hơn khi cần nói đến.

## 1. Hình dung một pipeline Either

Hai nguồn có thể chạy song song để tạo ra thông tin cùng kiểu:

~~~java
CompletableFuture<String> cache = new CompletableFuture<>();
CompletableFuture<String> service = new CompletableFuture<>();

CompletableFuture<Integer> answer =
    cache.applyToEither(service, String::length);
~~~

Đây là **mã minh họa**; cần import `java.util.concurrent.CompletableFuture`. `answer` sẽ nhận độ dài chuỗi của một nguồn được chọn theo quy tắc completion, nếu Function chạy bình thường.

~~~text
cache ----[value T]----\
                        +---- Function<T,U> ---> CompletableFuture<U>
service --[value T]----/
~~~

Nếu hai nguồn đã hoàn tất rất gần nhau, **không có ưu tiên cố định cho bên trái hoặc bên phải**. Không viết logic phụ thuộc tên biến `cache`/`service` hay thứ tự xuất hiện trong mã để dự đoán winner.

Ba nguyên tắc cần phân biệt:

1. Hai nguồn là các stage độc lập về tiến độ; `Either` chỉ tạo **stage phụ thuộc mới**.
2. Stage phụ thuộc hoàn tất khi **callback** của nó hoàn tất thành công hoặc khi quy tắc exceptional completion có hiệu lực.
3. Các nguồn không tự bị cancel sau khi stage phụ thuộc đã có kết quả.

Vì vậy, ngay cả khi response từ cache được dùng, request service có thể vẫn chạy, giữ network connection hoặc hoàn thành muộn hơn.

## 2. Bảng đối chiếu ba API

| API | Callback | Đọc giá trị nguồn? | Trả dữ liệu nghiệp vụ? | Kiểu future đầu ra |
| --- | --- | --- | --- | --- |
| `applyToEither` | `Function<? super T,U>` | Có | Có, kiểu `U` | `CompletableFuture<U>` |
| `acceptEither` | `Consumer<? super T>` | Có | Không | `CompletableFuture<Void>` |
| `runAfterEither` | `Runnable` | Không | Không | `CompletableFuture<Void>` |

**Quy tắc chọn:**

- Cần biến đổi dữ liệu thành giá trị mới, chẳng hạn `String -> Integer` hoặc `Response -> View` → **`applyToEither`**.
- Cần nhận dữ liệu để ghi metrics, gửi thông báo, xuất log hoặc cập nhật state hợp lệ → **`acceptEither`**.
- Chỉ cần biết “một stage đã hoàn tất bình thường”, không cần đọc kết quả → **`runAfterEither`**.

`Void` không có nghĩa là “tác vụ không biết khi nào hoàn thành”. Một `CompletableFuture<Void>` vẫn cho biết completion/error và có thể được nối `thenRun`/`whenComplete`. Nếu hoàn tất bình thường, `join()` trả `null`.

## 3. Chữ ký và quy tắc generic của Java 8

Các chữ ký rút gọn tương ứng trên `CompletableFuture<T>`:

~~~java
<U> CompletableFuture<U> applyToEither(
    CompletionStage<? extends T> other,
    Function<? super T,U> fn);

CompletableFuture<Void> acceptEither(
    CompletionStage<? extends T> other,
    Consumer<? super T> action);

CompletableFuture<Void> runAfterEither(
    CompletionStage<?> other,
    Runnable action);
~~~

Đây là **chữ ký để tham khảo**, không phải chương trình độc lập. Các interface nằm ở `java.util.concurrent` và `java.util.function`.

**Lý do có sự khác biệt generic:** `applyToEither` và `acceptEither` phải truyền một giá trị `T` vào Function/Consumer, nên hai nguồn cần kiểu dữ liệu tương thích. `runAfterEither` không truyền giá trị, vì vậy overload nhận `CompletionStage<?>` cho phép hai nguồn **khác kiểu**.

~~~java
CompletableFuture<Integer> count = new CompletableFuture<>();
CompletableFuture<String> ready = new CompletableFuture<>();

CompletableFuture<Void> flag =
    count.runAfterEither(
        ready, () -> System.out.println("one ready"));
~~~

Hợp lệ: Runnable không cần biết count là Integer hay ready là String.

Ngược lại:

~~~java
// PHẢN VÍ DỤ: Không tương thích kiểu.
// ready.applyToEither(count, String::length);
~~~

Nếu hai API thực tế trả kiểu khác nhau nhưng bạn muốn chọn chung, chuẩn hóa chúng trước thành một domain model hoặc `CompletionStage<CommonType>` qua `thenApply` có type safety. Đừng dùng raw type và ép kiểu mù chỉ để bỏ lỗi của compiler.

## 4. applyToEither — dùng một giá trị T để tạo U

Ví dụ thứ tự hoàn tất do main điều khiển, không phụ thuộc scheduler:

~~~java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> replica = new CompletableFuture<>();

CompletableFuture<String> transformed =
    primary.applyToEither(
        replica, value -> "chosen:" + value);

replica.complete("CACHE");
primary.complete("DB");

System.out.println(transformed.join());
// chosen:CACHE
~~~

`replica.complete("CACHE")` được gọi trước `primary.complete("DB")`; callback là loại non-Async nên có thể được thực thi ngay trên thread complete nguồn. Đây là minh họa ổn định về **nguồn hoàn thành bình thường trước**. Khi hai request thật chạy đồng thời, việc chọn stage nào không được bảo đảm bởi thứ tự khai báo.

### 4.1. Thay đổi kiểu kết quả

~~~java
CompletableFuture<String> first =
    CompletableFuture.completedFuture("java");

CompletableFuture<String> second = new CompletableFuture<>();

CompletableFuture<Integer> length =
    first.applyToEither(second, String::length);

// length.join() == 4
~~~

Đầu vào là String, đầu ra là Integer. Future mới có kiểu `CompletableFuture<Integer>`, nên bước sau có thể dùng `thenApply(n -> n * 2)` mà không cần cast.

### 4.2. Function có thể thất bại

~~~java
CompletableFuture<String> source =
    CompletableFuture.completedFuture("bad");

CompletableFuture<String> other = new CompletableFuture<>();

CompletableFuture<Integer> invalid =
    source.applyToEither(other, value -> {
        throw new IllegalArgumentException("cannot map");
    });
~~~

`invalid.join()` sẽ ném `CompletionException` với nguyên nhân `IllegalArgumentException`. Nguồn hoàn thành bình thường **không** đồng nghĩa Function do bạn cung cấp luôn thành công.

### 4.3. Nối pipeline mà không block

~~~java
CompletableFuture<Integer> finalLength =
    primary.applyToEither(replica, String::trim)
           .thenApply(String::length);
~~~

Đây là minh họa dựa trên hai future String ở đầu phần. Không gọi `join()` giữa các bước nếu bạn vẫn muốn pipeline bất đồng bộ; chỉ chờ khi caller thật sự cần kết quả hoặc trả tiếp future ra ngoài.

Nếu bước sau cũng sinh `CompletionStage<U>`, sử dụng `thenCompose` để tránh `CompletableFuture<CompletableFuture<U>>`.

## 5. acceptEither — nhận T, thực hiện Consumer, trả Void

`acceptEither` thích hợp khi cần xử lý payload nhưng không trả giá trị nghiệp vụ tiếp:

~~~java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();
AtomicReference<String> seen = new AtomicReference<>("none");

CompletableFuture<Void> accepted =
    a.acceptEither(b, text -> seen.set("accepted:" + text));

a.complete("A");
b.complete("B");

accepted.join();
System.out.println(seen.get()); // accepted:A
~~~

Đây là đoạn minh họa, cần import `AtomicReference`. `accepted.join()` chỉ trả `null` khi consumer hoàn tất bình thường; nó **không trả chuỗi "A"**.

### 5.1. Side effect quan trọng phải được theo dõi

Consumer có thể ghi log, cập nhật màn hình, gửi thông báo, lưu dữ liệu hoặc phát một message. Nếu consumer tự ném lỗi, future `accepted` hoàn thành exceptional. Không bỏ qua `accepted` khi side effect quan trọng.

~~~java
CompletableFuture<String> ready =
    CompletableFuture.completedFuture("data");

CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<Void> failedConsumer =
    ready.acceptEither(pending, text -> {
        throw new IllegalStateException("write failed");
    });
~~~

Nguồn thành công, **Consumer thất bại**. Cần xử lý exception ở stage phụ thuộc, thay vì đoán “chọn được nguồn thì chắc chắn đã gửi thành công”.

### 5.2. Giá trị nguồn không còn trong Void future

Nếu downstream cần dùng kết quả nguồn, `applyToEither` phù hợp hơn. Đừng ghi một giá trị vào shared field chỉ để stage sau đọc nó mà không có đồng bộ:

~~~java
CompletableFuture<String> chosen =
    a.applyToEither(b, text -> text);

// chosen chứa payload, có thể dùng thenApply/thenCompose.
~~~

Trong ví dụ này `a` và `b` là hai `CompletableFuture<String>`. Truyền dữ liệu qua future giúp giảm shared mutable state, tăng khả năng compose và test.

### 5.3. Một Consumer không làm hai upstream thành exactly-once

Nếu hai task nguồn **đều gửi email hoặc ghi database** rồi mới trả kết quả, việc `acceptEither` chỉ tiêu thụ một response không làm side effect của nguồn kia biến mất. Với thao tác không idempotent, cần transaction, idempotency key và cơ chế deduplication ở nơi thực hiện side effect.

## 6. runAfterEither — chỉ chạy Runnable, không nhận kết quả

`runAfterEither` có callback `Runnable` không có tham số, phù hợp khi chỉ cần một tín hiệu completion:

~~~java
CompletableFuture<Integer> numbers = new CompletableFuture<>();
CompletableFuture<String> statuses = new CompletableFuture<>();
AtomicInteger notifications = new AtomicInteger();

CompletableFuture<Void> notified =
    numbers.runAfterEither(
        statuses, () -> notifications.incrementAndGet());

statuses.complete("ready");
numbers.complete(7);

notified.join();
System.out.println(notifications.get()); // 1
~~~

Đây là đoạn minh họa. Hai nguồn có thể khác kiểu vì Runnable không đọc dữ liệu của nguồn.

**Phân biệt rõ:**

- `runAfterEither` không đợi **cả hai** nguồn hoàn thành.
- Không nhận `Integer` hay `String`, cũng không cho biết source nào thắng.
- Không tự cancel nhánh còn lại.
- Không phải handler luôn chạy bất kể lỗi; nếu muốn một finally-style observation của một stage, dùng `whenComplete`.
- Khi Runnable ném exception, dependent future hoàn thành exceptional.

Nếu cần cả hai nguồn hoàn thành bình thường, dùng `runAfterBoth`. Nếu cần quan sát nguồn A kể cả lỗi, dùng `a.whenComplete((value,error) -> ...)`. Nếu cần thu thập trạng thái của cả hai kể cả lỗi, tạo mô hình kết quả và điều phối rõ ràng.

## 7. Async overload: nơi chạy callback không phải nơi chạy nguồn

Cả ba nhóm có ba biến thể:

~~~java
applyToEither(other, fn)
applyToEitherAsync(other, fn)
applyToEitherAsync(other, fn, executor)

acceptEither(other, action)
acceptEitherAsync(other, action)
acceptEitherAsync(other, action, executor)

runAfterEither(other, action)
runAfterEitherAsync(other, action)
runAfterEitherAsync(other, action, executor)
~~~

Các dòng này là **tên API mang tính minh họa**, không phải Java statements độc lập.

| Cách dùng | Callback chạy ở đâu? |
| --- | --- |
| Không có hậu tố Async | Có thể do thread hoàn thành source hoặc thread thực hiện completion liên quan chạy; không có cam kết một thread riêng |
| Async không truyền executor | Dùng default asynchronous execution facility của stage; `CompletableFuture` chuẩn thường dùng `ForkJoinPool.commonPool()` |
| Async có executor | Lên lịch qua `Executor` được chọn; thích hợp để tách workload và quản lý concurrency |

Ví dụ với executor riêng:

~~~java
ExecutorService pool = Executors.newSingleThreadExecutor();

try {
    CompletableFuture<String> fast =
        CompletableFuture.completedFuture("FAST");
    CompletableFuture<String> slow =
        new CompletableFuture<>();

    CompletableFuture<String> processed =
        fast.applyToEitherAsync(
            slow,
            text -> text.toLowerCase(Locale.ROOT),
            pool);

    System.out.println(processed.join()); // fast
} finally {
    pool.shutdown();
}
~~~

Trong ví dụ, fast đã completed còn slow pending nên callback được lên lịch với kết quả fast. Nhưng **không** suy rằng lời gọi Async luôn tạo một thread mới, hoặc rằng hai task thật chạy cạnh tranh sẽ theo thứ tự viết trong code.

### 7.1. Executor phải được chọn theo workload

Một Function/Consumer/Runnable có thể chứa việc blocking I/O. Nếu đưa mọi I/O blocking vào commonPool, bạn có nguy cơ làm nghẽn pool dùng chung. Tạo executor có **giới hạn concurrency, queue/rejection policy và lifecycle** phù hợp với DB/network. `Executors.newFixedThreadPool` giới hạn số worker, nhưng hàng chờ trong implementation chuẩn có thể lớn/không giới hạn; một dịch vụ bận cần backpressure rõ ràng.

Một executor đã shutdown có thể từ chối callback Async và khiến dependent stage exceptional. Đây là **lỗi lên lịch continuation** dù source đã hoàn thành bình thường. Đừng tạo một thread pool mới cho mỗi request rồi quên shutdown; thường quản lý executor ở cấp ứng dụng.

### 7.2. Async không có nghĩa non-blocking I/O

`CompletableFuture.supplyAsync(() -> jdbcCall())` chỉ chuyển lời gọi blocking sang worker; JDBC đồng bộ vẫn **block worker**. `applyToEitherAsync` chỉ điều chỉnh nơi chạy *continuation*, không thay đổi bản chất I/O của nguồn.

Từ Java 21 trở đi, virtual threads là lựa chọn hiện hành cho nhiều kiểu blocking I/O, nhưng **không làm đổi ngữ nghĩa Either hoặc exceptional completion**; mã mẫu bên dưới chỉ dùng API Java 8.

## 8. Exceptional completion: bẫy quan trọng nhất

Theo hợp đồng `CompletionStage`, các lời gọi *Either* được mô tả ở **nhánh hoàn thành bình thường**; đồng thời tài liệu nêu:

> Nếu một dependent stage phụ thuộc vào một trong hai stage, và chỉ một trong hai stage hoàn thành exceptional, không bảo đảm dependent stage sẽ kết thúc bình thường hay exceptional.

Đây là quy tắc quan trọng và vẫn có trong tài liệu Java SE hiện hành.

### 8.1. Các kịch bản cần phân biệt

| Trạng thái hai nguồn | Có thể kết luận gì? |
| --- | --- |
| A hoàn tất bình thường; B chưa hoàn tất | Callback có thể chạy với A; B không phải bị hủy |
| B hoàn tất bình thường; A chưa hoàn tất | Callback có thể chạy với B; A không phải bị hủy |
| Hai nguồn hoàn tất bình thường gần nhau | Không bảo đảm cố định nguồn nào được dùng |
| A exceptional; B sau đó normal | **Không có bảo đảm chung** dependent stage sẽ lấy B hay kết thúc exceptional |
| A normal; B exceptional | Không dùng quy tắc “bỏ qua lỗi” như cam kết độc lập của framework; quan sát stage thực |
| Cả hai exceptional | Không có giá trị bình thường để truyền callback; dependent có thể báo lỗi, không dựa vào thứ tự ưu tiên exception |
| Callback được chọn tự ném exception | Dependent stage exceptional, dù source bình thường |

**Sai lầm cần tránh:**

~~~java
CompletableFuture<String> first =
    CompletableFuture.supplyAsync(() -> {
        throw new IllegalStateException("A down");
    });

CompletableFuture<String> second =
    CompletableFuture.supplyAsync(() -> "B works");

CompletableFuture<String> result =
    first.applyToEither(second, value -> value);

// KHÔNG được assert result.join() luôn là "B works".
~~~

Đây là **mã minh họa có kết quả không xác định**, không phải ví dụ đầu ra đáng tin. Sự cố có thể phụ thuộc timing, scheduling và implementation. Thêm `Thread.sleep` không tạo bảo đảm mới.

### 8.2. Khi callback tự ném lỗi

`applyToEither`, `acceptEither` và `runAfterEither` đều có thể thất bại vì callback, ngay cả khi nguồn thành công. `join()` trên future lỗi thường ném unchecked `CompletionException` với nguyên nhân gốc. `get()` có thể ném checked `ExecutionException`; riêng hủy có thể biểu hiện qua `CancellationException`. Đừng bắt tất cả lỗi rồi tự động trả success mà không ghi nguyên nhân.

### 8.3. `exceptionally` không phải phép retry

`exceptionally(error -> fallback)` có thể chuyển exceptional completion của **dependent stage** thành một giá trị fallback, nhưng nó **không chạy lại nguồn** và không giúp chọn một success thật của nguồn khác nếu future Either đã exceptional. Cân nhắc fallback theo domain.

~~~java
CompletableFuture<String> safe =
    chosen.exceptionally(error -> "unavailable");
~~~

Trong đoạn minh họa, `chosen` là một `CompletableFuture<String>` được tạo trước. Giá trị `"unavailable"` là fallback nghiệp vụ, **không phải bằng chứng một replica đã trả dữ liệu đúng**.

## 9. Khi cần “first successful”: một helper Java 8 có hợp đồng rõ ràng

Nếu yêu cầu là **“chỉ thất bại khi cả hai nguồn thất bại; một nguồn lỗi không được đánh bại nguồn còn lại sẽ thành công”**, bạn cần điều phối thành công/lỗi rõ hơn nhóm Either.

Mẫu đơn giản:

~~~java
static <T> CompletableFuture<T> firstSuccessful(
        CompletableFuture<T> left,
        CompletableFuture<T> right) {

    CompletableFuture<T> result = new CompletableFuture<>();
    AtomicInteger failures = new AtomicInteger();

    BiConsumer<T, Throwable> observe = (value, error) -> {
        if (error == null) {
            result.complete(value);
        } else if (failures.incrementAndGet() == 2) {
            result.completeExceptionally(error);
        }
    };

    left.whenComplete(observe);
    right.whenComplete(observe);
    return result;
}
~~~

Đây là **phương thức độc lập để đặt trong class**, không phải API `firstSuccessful` sẵn có trên `CompletableFuture`. Cần import `AtomicInteger`, `BiConsumer` và `CompletableFuture`.

- Khi một nguồn **normal**, dùng `result.complete(value)`. Giá trị `null` vẫn là kết quả bình thường.
- Khi nguồn lỗi, tăng số lỗi nguyên tử nhưng **chưa** đánh dấu result thất bại nếu mới một lỗi.
- Khi **cả hai lỗi**, lần ghi nhận thứ hai gọi `result.completeExceptionally(error)`.
- Hai callback chạy cạnh tranh thì chỉ một lời gọi `complete/completeExceptionally` thắng trạng thái kết quả.
- Nếu source đã completed trước khi đăng ký callback, thứ tự **quan sát** khác thứ tự vật lý trước đó; helper đảm bảo **first observed success/only both errors fail**, không khẳng định truy vết thời gian thực đến từng nanosecond.

Ví dụ:

~~~java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();

CompletableFuture<String> result = firstSuccessful(a, b);

a.completeExceptionally(
    new IllegalStateException("A down"));

System.out.println(result.isDone()); // false

b.complete("B ok");
System.out.println(result.join()); // B ok
~~~

Bài toán này **không được bảo đảm chỉ bằng một `applyToEither`**. Khi dùng trong production, hãy thêm timeout, error aggregation, logging, và chính sách kiểm soát các nguồn.

### 9.1. Giới hạn của helper

- Nếu A lỗi và B **treo mãi**, result cũng có thể treo. Phải đặt timeout ở tầng I/O và timeout cho toàn bộ cuộc đua.
- Nếu các nguồn có dữ liệu khác version, “success trước” chưa chắc là kết quả đúng; cần kiểm tra freshness.
- Nếu hai nguồn cùng tạo side effect, helper không hủy/rollback việc đã làm.
- Nếu muốn lưu đủ hai lỗi, mở rộng cách lưu lỗi; ở mẫu cơ bản, cause khi cả hai lỗi là lỗi quan sát thứ hai.
- Callback `whenComplete` non-Async nên giữ ngắn và không blocking; nếu cần xử lý nặng, cân nhắc stage Async/executor phù hợp.
- Mở rộng lên N nguồn cần bộ đếm tổng nguồn và quy tắc success/error rõ, không dùng boolean đơn giản rồi quên race.

### 9.2. Fallback từ `exceptionally` trước Either có phải giải pháp?

~~~java
CompletableFuture<String> safeA =
    a.exceptionally(error -> "fallback-A");

CompletableFuture<String> safeB =
    b.exceptionally(error -> "fallback-B");

CompletableFuture<String> selected =
    safeA.applyToEither(safeB, value -> value);
~~~

Cách này biến **lỗi** thành **giá trị bình thường**. Nhưng nếu A lỗi rất nhanh, `"fallback-A"` có thể thắng B vốn sắp trả thành công thật. Chỉ dùng khi fallback **được xem là kết quả hợp lệ để chọn sớm**; đừng gọi đó là bảo đảm “success thật đầu tiên”.

## 10. So với anyOf, allOf và nhóm Both

| API | Kích hoạt/bộ dữ liệu | Kết quả |
| --- | --- | --- |
| `applyToEither` | Một trong hai nguồn bình thường, Function nhận một T | Future U |
| `acceptEither` | Một trong hai nguồn bình thường, Consumer nhận một T | Future Void |
| `runAfterEither` | Một trong hai nguồn bình thường, Runnable không nhận T | Future Void |
| `thenCombine` | Cả hai nguồn bình thường, BiFunction nhận T và U | Future V |
| `thenAcceptBoth` | Cả hai nguồn bình thường, BiConsumer nhận T và U | Future Void |
| `runAfterBoth` | Cả hai nguồn bình thường, Runnable không nhận dữ liệu | Future Void |
| `CompletableFuture.anyOf` | Một future trong tập đã hoàn tất, **kể cả exceptional** | Future Object |
| `CompletableFuture.allOf` | Tất cả future trong tập đã hoàn tất | Future Void, không tổng hợp list giá trị |

### 10.1. `anyOf` khác rõ ở lỗi và kiểu dữ liệu

~~~java
CompletableFuture<Integer> fast = new CompletableFuture<>();
CompletableFuture<String> slow = new CompletableFuture<>();

CompletableFuture<Object> any =
    CompletableFuture.anyOf(fast, slow);

fast.complete(7);
slow.complete("late");

System.out.println(any.join()); // 7
~~~

`anyOf` cho phép các future khác kiểu nhưng trả `Object`; cần type safety khi đọc. Nếu nguồn hoàn tất đầu tiên bằng exception, `anyOf` có thể hoàn thành exceptional ngay. Nó **không** có hợp đồng “đợi một kết quả normal”.

### 10.2. `allOf` không trả các giá trị nguồn

~~~java
CompletableFuture<String> x =
    CompletableFuture.completedFuture("X");

CompletableFuture<String> y =
    CompletableFuture.completedFuture("Y");

CompletableFuture<Void> barrier =
    CompletableFuture.allOf(x, y);

barrier.join(); // Trả null khi hoàn tất bình thường.
~~~

Nếu cần một giá trị kết hợp, `x.thenCombine(y, (a,b) -> a+b)` diễn đạt ý định tốt hơn. Nếu cần lỗi và kết quả từ nhiều nguồn, dùng `handle` để tạo outcome model rồi phối hợp.

## 11. Lựa chọn bài toán: đọc một bản sao hay đợi cả hai?

### 11.1. Hai dịch vụ trả cùng kiểu response

~~~java
CompletableFuture<Response> primary =
    CompletableFuture.supplyAsync(
        () -> readFromPrimary(), ioExecutor);

CompletableFuture<Response> backup =
    CompletableFuture.supplyAsync(
        () -> readFromBackup(), ioExecutor);

CompletableFuture<View> view =
    primary.applyToEither(
        backup, response -> toView(response));
~~~

Đây là **pseudocode** (các kiểu `Response`, `View` và hàm do ứng dụng cung cấp). Phải đánh giá failure policy. Nếu một nguồn lỗi nhanh còn nguồn kia có thể success, hãy cân nhắc firstSuccessful helper thay vì hiểu sai `applyToEither`.

### 11.2. Kiểm tra bảo mật cần cả hai kết quả

Nếu cần hai điều kiện kiểm tra bắt buộc, `runAfterEither` là **sai** vì chỉ cần một normal stage; dùng `thenCombine`, `thenAcceptBoth` hoặc `runAfterBoth` theo việc có cần giá trị hay không.

### 11.3. Sự kiện chỉ cần một tín hiệu

Hai stage có thể trả kiểu khác nhau, nhưng downstream chỉ cần biết một trong hai hoàn tất bình thường: `runAfterEither` phù hợp. Nếu downstream cần biết nguồn nào và payload, hãy **gắn nhãn nguồn vào kiểu T** rồi dùng `acceptEither`/`applyToEither`, không đoán từ tên thread.

## 12. Null và Void trong Either

Một `CompletableFuture<String>` có thể hoàn thành **bình thường với null**:

~~~java
CompletableFuture<String> nullable =
    CompletableFuture.completedFuture(null);
CompletableFuture<String> pending =
    new CompletableFuture<>();

CompletableFuture<String> result =
    nullable.applyToEither(
        pending,
        s -> s == null ? "NULL" : s);

// result.join() là "NULL".
~~~

Ở đây null **không phải** lỗi hoặc chưa completed. `acceptEither` có thể nhận null, nên Consumer phải kiểm tra nếu null không phù hợp. `runAfterEither` không đọc T nên không quan tâm giá trị nguồn có null hay không.

`Void` của `acceptEither`/`runAfterEither` biểu diễn future của hành động; `join() == null` là bình thường khi action thành công. Để kiểm tra trạng thái trước khi join, dùng `isDone`/`isCompletedExceptionally` tùy mục tiêu, không suy từ null.

## 13. Cancellation, timeout và nhánh thua

### 13.1. Không có tự động hủy nguồn còn lại

Khi dependent đã hoàn thành, hai nguồn vẫn là các future độc lập. Một nguồn chậm có thể tiếp tục sử dụng CPU, DB connection, network hoặc hoàn thành với exception sau khi bạn đã có kết quả mong muốn.

`CompletableFuture.cancel(true)` có thể hoàn thành chính future với `CancellationException`. Tuy nhiên, theo hợp đồng của `CompletableFuture`, tham số `mayInterruptIfRunning` **không điều khiển interruption của computation**. Vì vậy nó **không chắc làm ngừng tác vụ I/O thật** hoặc rollback một request đã gửi. Muốn dừng nguồn cần API cancellation/timeout hợp tác của client/driver và quản lý side effect phù hợp.

### 13.2. Timeout chờ không phải timeout task

Java 8 có `get(timeout, TimeUnit.SECONDS)`:

~~~java
try {
    String response = result.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Caller không đợi thêm nữa.
}
~~~

Đây là đoạn minh họa cần `result` là future String, và method chứa đoạn code phải xử lý/khai báo thêm `InterruptedException` và `ExecutionException`. `get(timeout)` **chỉ giới hạn thời gian chờ caller**; nó không hủy hai nguồn.

Từ **Java 9** có `orTimeout` và `completeOnTimeout`, nhưng hai phương thức này tác động đến **trạng thái future** khi hết hạn, không hứa dừng tác vụ underlying. Không đưa chúng vào mã tuyên bố chỉ dùng API Java 8.

### 13.3. Future đã chọn không bảo đảm exactly-once trong hệ phân tán

Nếu hai nguồn đều **ghi đơn hàng** hoặc **chuyển tiền**, việc chọn một response không tự ngăn nguồn còn lại hoàn tất side effect. Với hedged requests cho thao tác đọc idempotent, hãy kiểm soát latency, quota và tải; với thao tác ghi, cần idempotency key và transaction/outbox policy rõ ràng.

## 14. Shared mutable state, happens-before và deadlock

`CompletableFuture` bảo vệ trạng thái hoàn tất của chính nó; `CompletionStage` có các quan hệ happens-before giữa việc submit stage và xử lý dependent stage theo hợp đồng. Nhưng nó **không làm một `ArrayList` hoặc phép `counter++` dùng chung trở nên thread-safe**.

~~~java
int[] counter = {0};

CompletableFuture<Void> one =
    CompletableFuture.runAsync(() -> counter[0]++);

CompletableFuture<Void> two =
    CompletableFuture.runAsync(() -> counter[0]++);

CompletableFuture.allOf(one, two).join();
~~~

Đây là **phản ví dụ**. Hai task có thể đọc cùng counter rồi ghi đè, nên kết quả có thể thiếu lần tăng.

Thay thế:

~~~java
AtomicInteger counter = new AtomicInteger();

CompletableFuture<Void> one =
    CompletableFuture.runAsync(() -> counter.incrementAndGet());

CompletableFuture<Void> two =
    CompletableFuture.runAsync(() -> counter.incrementAndGet());

CompletableFuture.allOf(one, two).join();
// counter.get() == 2 nếu không có writer khác.
~~~

Trong `acceptEither` và `runAfterEither`, callbacks cũng cần tuân thủ tính an toàn luồng của tài nguyên được ghi. Với một biến local chỉ được callback cập nhật, có thể trả kết quả qua future thay vì tạo shared state.

### Tránh block pool bằng chờ task cùng pool

~~~java
// PHẢN VÍ DỤ — không chạy nguyên văn:
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<String> outer =
    CompletableFuture.supplyAsync(() -> {
        CompletableFuture<String> inner =
            CompletableFuture.supplyAsync(
                () -> "inner", single);
        return inner.join();
    }, single);
~~~

Outer giữ worker duy nhất và chờ inner cần chính worker đó, nên có thể deadlock. Dùng `thenCompose` hoặc tổ chức dependency không blocking. Một phương thức Either **không tự sửa** chu trình chờ trên executor nhỏ.

## 15. Chương trình Java hoàn chỉnh và đầu ra xác định

Lưu chương trình thành **`EitherStageDemo.java`**. Chương trình dùng API Java 8, biên dịch với JDK 17+. Nó chủ động dùng `complete` theo thứ tự trong main, không dùng sleep hay giả định về tốc độ thread. Phần `applyToEitherAsync` dùng executor riêng và một nguồn đã hoàn thành, cho đầu ra tái lập được.

~~~java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BiConsumer;

public class EitherStageDemo {

    static <T> CompletableFuture<T> firstSuccessful(
            CompletableFuture<T> left,
            CompletableFuture<T> right) {
        CompletableFuture<T> result = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();

        BiConsumer<T, Throwable> observer = (value, error) -> {
            if (error == null) {
                result.complete(value);
            } else if (failures.incrementAndGet() == 2) {
                result.completeExceptionally(error);
            }
        };

        left.whenComplete(observer);
        right.whenComplete(observer);
        return result;
    }

    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            // 1. applyToEither: biến T thành U.
            CompletableFuture<String> primary =
                    new CompletableFuture<>();
            CompletableFuture<String> replica =
                    new CompletableFuture<>();

            CompletableFuture<String> applied =
                    primary.applyToEither(
                        replica,
                        s -> "chosen:"
                            + s.toUpperCase(Locale.ROOT));

            replica.complete("cache");
            primary.complete("db");

            System.out.println("apply=" + applied.join());
            System.out.println("sources="
                    + primary.join() + "/" + replica.join());

            // 2. acceptEither: Consumer<T>, trả Void.
            CompletableFuture<String> a =
                    new CompletableFuture<>();
            CompletableFuture<String> b =
                    new CompletableFuture<>();
            AtomicReference<String> seen =
                    new AtomicReference<>("none");

            CompletableFuture<Void> accepted =
                    a.acceptEither(
                        b, s -> seen.set("received:" + s));

            a.complete("A");
            b.complete("B");

            System.out.println("acceptNull="
                    + (accepted.join() == null));
            System.out.println("acceptSeen=" + seen.get());

            // 3. runAfterEither: nguồn có kiểu khác nhau.
            CompletableFuture<Integer> countStage =
                    new CompletableFuture<>();
            CompletableFuture<String> statusStage =
                    new CompletableFuture<>();
            AtomicInteger runs = new AtomicInteger();

            CompletableFuture<Void> ran =
                    countStage.runAfterEither(
                        statusStage, () -> runs.incrementAndGet());

            statusStage.complete("ready");
            countStage.complete(7);

            System.out.println("runNull=" + (ran.join() == null));
            System.out.println("runCount=" + runs.get());

            // 4. Async: callback được thực thi qua executor.
            CompletableFuture<String> fast =
                    CompletableFuture.completedFuture("FAST");
            CompletableFuture<String> pending =
                    new CompletableFuture<>();

            CompletableFuture<String> async =
                    fast.applyToEitherAsync(
                        pending,
                        s -> s.toLowerCase(Locale.ROOT),
                        executor);

            System.out.println("async=" + async.join());
            pending.complete("LATE");

            // 5. Null là kết quả normal hợp lệ.
            CompletableFuture<String> nullable =
                    CompletableFuture.completedFuture(null);
            CompletableFuture<String> never =
                    new CompletableFuture<>();

            System.out.println("nullResult="
                    + nullable.applyToEither(
                        never,
                        s -> s == null ? "NULL" : s).join());

            // 6. First-success custom: lỗi một nguồn
            // chưa khiến result thành lỗi.
            CompletableFuture<String> fail =
                    new CompletableFuture<>();
            CompletableFuture<String> healthy =
                    new CompletableFuture<>();
            CompletableFuture<String> robust =
                    firstSuccessful(fail, healthy);

            fail.completeExceptionally(
                new IllegalStateException("down"));

            System.out.println("robustWaiting="
                    + !robust.isDone());

            healthy.complete("RECOVERED");
            System.out.println("robust=" + robust.join());

            // 7. Khi cả hai lỗi, helper báo lỗi thứ hai.
            CompletableFuture<String> failA =
                    new CompletableFuture<>();
            CompletableFuture<String> failB =
                    new CompletableFuture<>();
            CompletableFuture<String> bothFailed =
                    firstSuccessful(failA, failB);

            failA.completeExceptionally(
                new IllegalStateException("A down"));
            failB.completeExceptionally(
                new IllegalArgumentException("B down"));

            System.out.println("bothFailed="
                    + bothFailed.isCompletedExceptionally());

            try {
                bothFailed.join();
            } catch (CompletionException ex) {
                System.out.println("failureCause="
                    + ex.getCause().getClass().getSimpleName());
            }

            // 8. anyOf không cần cùng kiểu.
            CompletableFuture<Integer> firstAny =
                    new CompletableFuture<>();
            CompletableFuture<String> secondAny =
                    new CompletableFuture<>();
            CompletableFuture<Object> any =
                    CompletableFuture.anyOf(firstAny, secondAny);

            firstAny.complete(7);
            secondAny.complete("late");
            System.out.println("anyResult=" + any.join());

            // 9. thenCombine cần hai kết quả.
            CompletableFuture<String> x =
                    CompletableFuture.completedFuture("X");
            CompletableFuture<String> y =
                    CompletableFuture.completedFuture("Y");

            System.out.println("bothCombined="
                    + x.thenCombine(y, (l, r) -> l + r).join());

            // 10. Consumer tự ném lỗi.
            CompletableFuture<String> ready =
                    CompletableFuture.completedFuture("ok");
            CompletableFuture<String> waiting =
                    new CompletableFuture<>();

            CompletableFuture<Void> bad =
                    ready.acceptEither(waiting, value -> {
                        throw new IllegalArgumentException(
                            "consumer failed");
                    });

            try {
                bad.join();
            } catch (CompletionException ex) {
                System.out.println("consumerError="
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
javac -encoding UTF-8 EitherStageDemo.java
java EitherStageDemo
~~~

**Đầu ra kỳ vọng:**

~~~text
apply=chosen:CACHE
sources=db/cache
acceptNull=true
acceptSeen=received:A
runNull=true
runCount=1
async=fast
nullResult=NULL
robustWaiting=true
robust=RECOVERED
bothFailed=true
failureCause=IllegalArgumentException
anyResult=7
bothCombined=XY
consumerError=IllegalArgumentException
~~~

### Giải thích vì sao output ổn định

1. `replica.complete("cache")` diễn ra trước `primary.complete("db")` trên main; kết quả apply là `chosen:CACHE`.
2. Nguồn primary vẫn được hoàn tất, nên `sources=db/cache` chứng minh stage Either không tự hủy nhánh còn lại.
3. A hoàn thành trước B; Consumer của `acceptEither` ghi `received:A`. Future trả Void nên `acceptNull=true`.
4. `runAfterEither` của Integer/String kích hoạt Runnable khi status hoàn thành. Counter được tăng một lần; `ran.join()` trả null bình thường.
5. `fast` đã completed còn `pending` chưa; biến thể Async chạy callback qua executor để đổi `FAST` thành `fast`.
6. Một nguồn hoàn thành normal với null; Function kiểm tra null và trả `NULL`.
7. Helper `firstSuccessful` thấy một exception nên vẫn pending; sau thành công của healthy nó trả `RECOVERED`.
8. Với hai lỗi được main complete tuần tự, helper lấy cause từ lỗi thứ hai `IllegalArgumentException`. **Đây là chính sách helper**, không phải thứ tự error được hứa bởi nhóm Either dựng sẵn.
9. `anyOf` trả Integer 7 ở dạng Object; `thenCombine` trả `XY` vì nhận đủ hai chuỗi.
10. Consumer của `acceptEither` tự ném IllegalArgumentException; lỗi nằm trong CompletionException của dependent future.

Ví dụ dùng `try/finally` để đóng executor và chỉ in kết quả khi đã có completion cần thiết. Nó **không tạo phép race phụ thuộc `Thread.sleep`** và cố ý không tuyên bố output của tình huống một nguồn exceptional còn nguồn kia normal khi dùng directly `applyToEither`.

## 16. Các lỗi thường gặp

1. **Coi `applyToEither` là “first successful” không điều kiện.** Khi một nguồn exceptional, tài liệu không bảo đảm dependent bình thường; dùng helper có chính sách rõ nếu cần.
2. **Dùng `acceptEither` rồi đòi Future trả T.** Nó trả `Void`; muốn giữ T/U, dùng `applyToEither`.
3. **Dùng `runAfterEither` để đọc nguồn thắng.** Runnable không nhận T; gắn nhãn vào payload rồi dùng Consumer/Function.
4. **Dùng `runAfterEither` khi cần cả hai xong.** Dùng `runAfterBoth` hoặc `thenCombine`.
5. **Truyền hai nguồn khác kiểu vào `applyToEither`.** Chúng cần tương thích T; `runAfterEither` có kiểu `CompletionStage<?>`.
6. **Cho rằng bên trái luôn thắng.** Không có ưu tiên khi race; test theo kết quả thực và giới hạn nghiệp vụ.
7. **Dùng `Thread.sleep` để “điều khiển” completion order.** Sleep không tạo bảo đảm; tạo future chưa complete và gọi `complete` có kiểm soát trong unit test.
8. **Cho rằng hậu tố Async tạo một thread mới mỗi lần.** Nó dùng facility/executor; có thể là pool chung và có policy riêng.
9. **Block executor bằng `join` của task trong cùng executor nhỏ.** Có thể starvation/deadlock; dùng composition không blocking.
10. **Bỏ qua future mà Consumer/Runnable trả về.** Callback có thể lỗi; cần theo dõi result/exception.
11. **Coi `anyOf` là “first success”.** Nó có thể hoàn thành exceptional ngay bởi một nguồn lỗi.
12. **Tưởng `allOf` tự trả list kết quả.** Nó trả Future Void; kết hợp hoặc đọc từng result sau barrier thành công.
13. **Tin rằng source thua sẽ tự cancel.** Không; cần quản lý I/O timeout/cancellation và tài nguyên.
14. **Tin rằng `cancel(true)` chắc interrupt task.** Với CompletableFuture, boolean không có hiệu lực điều khiển interruption; cancellation thường được quan sát như `CancellationException`.
15. **Nhân đôi side effect không idempotent.** Hai request vẫn có thể đều thực hiện thao tác dù chỉ một response được dùng; cần transaction/idempotency.
16. **Nhầm null với chưa completed.** Future có thể hoàn thành normal với null; xử lý theo quy tắc domain.
17. **Lạm dụng commonPool cho blocking I/O.** Tách executor và áp dụng giới hạn concurrency/backpressure.
18. **Không có timeout.** Nếu một nguồn lỗi, nguồn kia treo, helper first-success có thể đợi mãi; timeout từ caller không tự dừng I/O.
19. **Shared mutable state không đồng bộ.** CompletableFuture thread-safe không bảo vệ `HashMap`/`ArrayList`/counter của bạn.
20. **Dùng hedging cho dữ liệu khác version.** Fastest không luôn đúng nhất; nếu cần quorum/freshness, phải phối hợp đủ dữ liệu hoặc xác minh thêm.

## 17. Checklist thiết kế và kiểm thử

- Có xác định rõ nghiệp vụ cần **Either**, **Both**, **anyOf** hay **first successful** chưa?
- Hai nguồn của `applyToEither` và `acceptEither` có kiểu T tương thích không?
- Callback sau khi một nguồn complete có cần nhận T không? Nó tạo U hay chỉ side effect?
- Có hiểu rõ `CompletableFuture<Void>` là future của sự hoàn tất, không phải future chứa T không?
- Có kiểm thử A normal trước B, B normal trước A, hai nguồn normal gần như đồng thời không?
- Có kiểm thử một nguồn exceptional rồi nguồn kia normal, và cả hai exceptional theo policy thực tế không?
- Có xử lý trường hợp Function/Consumer/Runnable của continuation tự ném lỗi không?
- Có dùng `join/get` đúng tại ranh giới mà caller cần kết quả, thay vì block tùy tiện ở giữa pipeline không?
- Có chọn executor phù hợp cho callback nặng hoặc blocking và quản lý lifecycle/rejection không?
- Khi cần first-success thật, helper có giới hạn thời gian chờ, quan sát lỗi và không mất các lỗi quan trọng không?
- Các task nguồn còn lại sau winner được giải quyết/cancel thế nào? Việc hủy có thực sự ngắt I/O không?
- Dữ liệu trả về của hai nguồn có tương đương về ngữ nghĩa và độ mới không?
- Có phòng ngừa nhân đôi thao tác side effect qua idempotency key không?
- Có test một nguồn normal với null, vì null không phải dấu hiệu exceptional không?
- Có dùng counter/collection an toàn luồng trong callback và tránh ghi đồng thời vào cùng mutable buffer không?
- Có hiểu rằng `orTimeout` và `completeOnTimeout` thuộc Java 9+, trong khi nhóm Either có từ Java 8 không?
- Có kiểm thử output đúng bằng các future tự hoàn thành theo thứ tự xác định, thay vì lệ thuộc tên thread hoặc sleep không?

**Kết luận:** `applyToEither` **biến đổi kết quả từ một trong hai nguồn**, `acceptEither` **tiêu thụ kết quả từ một trong hai nguồn**, còn `runAfterEither` **chạy hành động không cần dữ liệu nguồn**. Chúng là công cụ ghép tác vụ hữu ích, nhưng không phải primitive đầy đủ cho “first-success failover” khi có ngoại lệ. Sự chính xác phụ thuộc vào hợp đồng exceptional completion, lựa chọn executor, trạng thái side effect, timeout và việc quản lý nhánh thua. Những nguyên tắc này vẫn áp dụng cho Java hiện đại.

## Tài liệu chính thức

- [Oracle Java SE 26 — CompletionStage: Either/Both, exceptional completion và memory consistency](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 26 — CompletableFuture: applyToEither, acceptEither, runAfterEither, Async, anyOf, allOf, cancel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 26 — ExecutorService: executor lifecycle và quản lý tài nguyên](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java SE 26 — ForkJoinPool và commonPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Oracle Java SE 26 — Function/Consumer/BiConsumer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/package-summary.html)
