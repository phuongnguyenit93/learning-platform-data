# applyToEither() và acceptEither() khi cạnh tranh kết quả trong Java CompletableFuture

> **Phạm vi:** Java SE 17, nhóm kiến thức **CompletableFuture**, tập trung vào việc phối hợp hai nguồn bất đồng bộ cạnh tranh để cung cấp kết quả. Bài giải thích chính xác `applyToEither`, `acceptEither` và các biến thể `Async`, completion bình thường/bất thường, callback, executor, cancellation, timeout, side effect và cách tự thiết kế “first successful” khi cần. Đây là **Java concurrency nói chung**; không sử dụng API riêng của Spring vì đã có chương riêng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu rõ `applyToEither` trả một kết quả **được biến đổi** qua `Function<T,U>`, trong khi `acceptEither` thực thi `Consumer<T>` và trả `CompletableFuture<Void>`.
2. Hiểu các phương thức hoạt động dựa trên **một trong hai stage hoàn thành bình thường**, nhưng **không đồng nghĩa** với một bộ chọn luôn đợi “thành công đầu tiên” dưới mọi race có lỗi.
3. Phân biệt completion thông thường, completion bằng exception, cancellation và timeout của các nguồn.
4. Hiểu callback có thể chạy trên thread hoàn tất nguồn hoặc thread đăng ký callback; biến thể `Async` có thể dùng common pool hoặc executor được chỉ định.
5. Biết rằng nguồn còn lại **không tự bị cancel** và vẫn có thể thực thi side effect sau khi dependent đã hoàn tất.
6. Tránh nhầm `applyToEither` với `thenCombine`, `thenAcceptBoth`, `anyOf`, `runAfterEither` và `CompletableFuture.allOf`.
7. Sử dụng `ExecutorService`, deadline, logging và exception policy để điều phối hai phép gọi song song mà không làm block sai chỗ.
8. Kiểm thử Java 17 với `complete(...)`/`completeExceptionally(...)` để tạo lịch thứ tự xác định, không dựa vào `Thread.sleep`.
9. Xây một helper riêng có semantics **first successful, chỉ thất bại khi cả hai nguồn thất bại**, nếu đó mới là yêu cầu thực sự.
10. Nhận biết giới hạn của completion stage: việc source future đã hoàn tất không có nghĩa giao dịch bên ngoài JVM đã commit, và hủy Future không hứa dừng thread/HTTP call thật.

**Ý chính:** khi một trong hai nguồn hoàn thành bình thường và kích hoạt được combinator, `applyToEither` tạo kết quả biến đổi còn `acceptEither` tạo stage Void sau khi consumer chạy. Tuy nhiên, với những **exceptional completions cạnh tranh**, cần đọc hợp đồng/kiểm thử JDK đang dùng và **không coi either-combinator là first-success-failover tuyệt đối**.

## 2. Tình huống thực tế: hai nguồn cùng trả dữ liệu

Giả sử ứng dụng có hai nhà cung cấp dữ liệu độc lập:

- Nguồn A có thể trả một cấu hình, giá trị tồn kho hoặc metadata.
- Nguồn B có thể trả cùng loại dữ liệu từ một vùng khác.
- Bạn muốn **sử dụng kết quả đến trước** thay vì luôn đợi cả hai.
- Có khi bạn muốn **biến đổi** kết quả thành một object mới.
- Có khi bạn chỉ muốn **tiêu thụ** kết quả để log, ghi metric hoặc chuyển tới một kênh khác.

Nếu kết quả thuộc cùng kiểu `T`, `CompletableFuture` có một nhóm combinator theo semantics “either”:

```java
CompletableFuture<String> left = fetchFromLeft();
CompletableFuture<String> right = fetchFromRight();

CompletableFuture<Integer> length =
        left.applyToEither(right, String::length);

CompletableFuture<Void> published =
        left.acceptEither(right, this::publishValue);
```

Đây là **đoạn minh họa trong một method**: `fetchFromLeft`, `fetchFromRight`, `publishValue` do ứng dụng định nghĩa. Không phải tệp Java độc lập; cần imports và một object `this` có method thích hợp.

Khi một nguồn **được chọn và hoàn tất bình thường**, dependent stage chạy callback tương ứng. `length` cung cấp số nguyên; `published` không chứa giá trị nghiệp vụ vì kết quả kiểu `Void`.

### Cảnh báo về ý nghĩa “nguồn nhanh nhất”

“Đến trước” là thứ tự **completion được quan sát trong một execution**, không phải một ranking cố định của nhà cung cấp. Hai futures có thể hoàn tất gần như đồng thời. Nếu cả hai đã hoàn tất trước khi đăng ký callback, không viết business rule phụ thuộc vào “luôn chọn bên trái” hoặc “luôn chọn timestamp nhỏ nhất”. Phương thức không thiết kế như một comparator timestamp.

## 3. Chữ ký API của hai phương thức

Các chữ ký rút gọn trên `CompletionStage<T>` / `CompletableFuture<T>`:

```java
<U> CompletableFuture<U> applyToEither(
        CompletionStage<? extends T> other,
        Function<? super T, U> fn);

CompletableFuture<Void> acceptEither(
        CompletionStage<? extends T> other,
        Consumer<? super T> action);
```

Đây là **chữ ký API minh họa**, không phải code khai báo lại phương thức trong dự án. Khi gọi trên `CompletableFuture`, kiểu kết quả là `CompletableFuture<U>` hoặc `CompletableFuture<Void>` tương ứng với API class.

- `T`: kiểu giá trị mà hai nguồn cung cấp, tương thích với `this` stage.
- `U`: kiểu kết quả **sau biến đổi** bởi `Function<T,U>`.
- `CompletionStage<? extends T> other`: nguồn thứ hai có kiểu giá trị có thể dùng như T.
- `Function<? super T,U>`: nhận kết quả T và **trả về U**.
- `Consumer<? super T>`: nhận kết quả T và **không trả lại U**.
- Return type là **dependent CompletableFuture**, không phải chính một trong hai futures gốc.

**Lưu ý quan trọng:** vì các methods là instance methods, `left.applyToEither(right, fn)` tạo một stage mới. Nó **không gộp object left và right thành một future chung có quyền kiểm soát vòng đời của cả hai**. Hai nguồn có thể tiếp tục độc lập.

## 4. applyToEither(): biến đổi dữ liệu từ nguồn được chọn

Ví dụ:

```java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> backup = new CompletableFuture<>();

CompletableFuture<String> result = primary.applyToEither(
        backup, value -> "hello " + value);

backup.complete("B");
primary.complete("A");
System.out.println(result.join()); // hello B
```

Đây là **snippet trong method**, cần `CompletableFuture` import. Lịch completion do main chủ động điều khiển: `backup.complete("B")` được gọi trước `primary.complete("A")` nên dependent nhận giá trị backup. Callback có thể chạy ngay trong lời `complete` trên thread main, không cần thread khác.

### Điều gì được bảo đảm?

Với một source hoàn thành bình thường và dependent callback được kích hoạt thành công:

1. `Function` nhận value của source được chọn.
2. Nếu `Function` trả U bình thường, dependent hoàn tất với U.
3. `result.join()` trả U hoặc ném exception nếu dependent hoàn tất bất thường.
4. Source còn lại không bị tự hủy; nó vẫn có thể hoàn tất về sau.
5. Completion của dependent và completion của hai sources là các sự kiện **khác nhau**.

### Function có thể ném lỗi

```java
CompletableFuture<Integer> parsed = primary.applyToEither(
        backup, Integer::parseInt);
```

Đây là code minh họa nếu hai nguồn là `CompletableFuture<String>`. Khi nguồn được chọn trả chuỗi không phải số, `NumberFormatException` của `Integer.parseInt` làm dependent hoàn tất bất thường. Source đã hoàn thành bình thường **không biến lỗi transformation thành thành công**.

Đây là lý do cần phân biệt lỗi ở **nguồn dữ liệu** với lỗi ở **callback biến đổi dữ liệu**. Nếu callback cần validate trước khi nhận, bạn có thể chủ động chuyển về outcome thành công/thất bại theo business rules, nhưng đừng giả định `applyToEither` tự thử callback lần nữa với giá trị nguồn còn lại khi callback đầu ném exception.

### Function trả null có hợp lệ không?

Có. `CompletableFuture<U>` có thể hoàn tất bình thường với `null` khi function trả null. Không giống `ConcurrentHashMap`, `CompletableFuture` không cấm null làm kết quả. Nhưng nếu business code cần phân biệt “không tìm thấy” và “chưa hoàn tất”, nên dùng `Optional<U>` hoặc result type rõ ràng, thay vì suy từ null của `join`.

## 5. acceptEither(): xử lý kết quả nhưng không tạo U mới

Ví dụ:

```java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> backup = new CompletableFuture<>();

AtomicReference<String> consumed = new AtomicReference<>();
CompletableFuture<Void> done =
        primary.acceptEither(backup, consumed::set);

backup.complete("B");
done.join();
System.out.println(consumed.get()); // B
```

Đây là **snippet trong method**, import `CompletableFuture` và `AtomicReference`. `Consumer<String>` ghi giá trị vào holder; dependent `done` có kiểu `CompletableFuture<Void>`.

**Không viết `String answer = done.join()`.** `done.join()` có kiểu `Void`, bình thường trả null, không trả bản thân chuỗi B.

### Side effect của Consumer

`acceptEither` hay được dùng với side effect:

- Gửi dữ liệu sang một pipeline khác.
- Cập nhật UI state qua executor thích hợp.
- Log lần nhận kết quả đầu tiên.
- Tăng metric/counter hoặc ghi một record.

Nhưng callback được thực hiện trên thread do semantics của dependent stage quyết định, **không phải một transaction exactly-once với hệ thống ngoài JVM**. Nếu Consumer gửi message rồi ném exception do network timeout, dependent có thể failed trong khi message thực tế đã được phía nhận xử lý. Cần idempotency/outbox/acknowledgment policy nếu công việc quan trọng.

### Consumer ném exception

```java
CompletableFuture<Void> sent = primary.acceptEither(
        backup, value -> {
            if (value.isBlank()) {
                throw new IllegalArgumentException("empty value");
            }
            publish(value);
        });
```

Đây là đoạn minh họa với `publish` tự định nghĩa. Nếu callback throw, stage `sent` hoàn tất bất thường. **Không suy rằng hệ thống tự chạy Consumer một lần nữa với nguồn thua** chỉ vì callback đã thất bại.

## 6. So sánh applyToEither và acceptEither

| Tiêu chí | `applyToEither(other, fn)` | `acceptEither(other, action)` |
|---|---|---|
| Loại callback | `Function<T,U>` | `Consumer<T>` |
| Callback trả gì? | Giá trị U | `void` |
| Dependent type | `CompletableFuture<U>` | `CompletableFuture<Void>` |
| Mục tiêu | Transform/map dữ liệu nguồn được chọn | Tiêu thụ dữ liệu nguồn được chọn |
| Quan sát completion | `join()/get()` nhận U hoặc lỗi | `join()/get()` bình thường nhận null hoặc lỗi |
| Exception từ callback | Dependent hoàn tất bất thường | Dependent hoàn tất bất thường |
| Nguồn thua tự cancel? | Không | Không |
| Mặc định phải đợi cả hai sources? | Không | Không |
| Tự retry khi callback lỗi? | Không | Không |

**Quy tắc chọn:** cần một giá trị đầu ra mới → `applyToEither`; chỉ cần hoàn thành side effect và muốn stage đánh dấu xong → `acceptEither`.

Không nên chọn `acceptEither` rồi giữ kết quả bằng mutable field chỉ vì không biết `applyToEither`. Nếu muốn pipeline thuần biến đổi, `applyToEither` thường rõ nghĩa hơn và giảm nguy cơ shared mutable state.

## 7. Định nghĩa “either” so với “both”

Các combinators dễ nhầm:

```java
left.applyToEither(right, mapper);
left.acceptEither(right, consumer);
left.runAfterEither(right, runnable);

left.thenCombine(right, combiner);
left.thenAcceptBoth(right, biConsumer);
left.runAfterBoth(right, runnable);
```

Đây là **danh sách lời gọi minh họa**, với callbacks và futures tương thích đã định nghĩa.

- `applyToEither`: phụ thuộc một nguồn được chọn, transform value.
- `acceptEither`: phụ thuộc một nguồn được chọn, consume value.
- `runAfterEither`: hành động `Runnable` **không nhận value** từ nguồn; trả `CompletableFuture<Void>`.
- `thenCombine`: cần giá trị bình thường từ **cả hai**, rồi `BiFunction<T,U,V>` kết hợp.
- `thenAcceptBoth`: cần **cả hai** và `BiConsumer<T,U>` tiêu thụ chúng.
- `runAfterBoth`: chạy `Runnable` sau khi **cả hai** hoàn tất bình thường theo contract.

### So với anyOf()

`CompletableFuture.anyOf(left,right)` tạo `CompletableFuture<Object>` hoàn thành khi **một source bất kỳ** hoàn tất — **bình thường hoặc bất thường**. Nếu nguồn đầu tiên lỗi, `anyOf` có thể hoàn tất bất thường ngay.

```java
CompletableFuture<Object> any =
        CompletableFuture.anyOf(left, right);
```

Đây là snippet trong method với `left/right` kiểu CompletableFuture. `anyOf` không phải “đợi một success”: cần phân biệt semantics với first-success policy và xử lý cast/type vì return type Object.

### So với allOf()

`CompletableFuture.allOf(left,right)` trả `CompletableFuture<Void>` và dùng khi muốn đợi hai nguồn (hoặc nhiều nguồn) kết thúc, kể cả khi có failure cần aggregate/inspect. `allOf` không tự tổng hợp các giá trị T; phải đọc từng source sau barrier phù hợp.

## 8. Ba biến thể thực thi của mỗi combinator

Cả hai có các biến thể tương ứng:

```java
left.applyToEither(right, fn);
left.applyToEitherAsync(right, fn);
left.applyToEitherAsync(right, fn, executor);

left.acceptEither(right, action);
left.acceptEitherAsync(right, action);
left.acceptEitherAsync(right, action, executor);
```

Đây là **danh sách API minh họa** (không phải file độc lập); `executor` cần là `Executor`.

### Biến thể không Async

Callback có thể chạy trên thread đang gọi `complete` của một nguồn, hoặc thread đang đăng ký dependent nếu kết quả đã sẵn có, hoặc một thread tham gia completion. Không được giả định callback sẽ luôn chạy trên một thread worker riêng hay UI thread.

Vì vậy một callback CPU-heavy hoặc block I/O trong `applyToEither` không Async có thể làm lời gọi `source.complete(...)` hay callback chain bị kéo dài.

### Biến thể Async không chỉ định Executor

`applyToEitherAsync(other, fn)` và `acceptEitherAsync(other, action)` thường dùng default asynchronous execution facility của `CompletableFuture` (thông thường `ForkJoinPool.commonPool()`, trừ điều kiện runtime/implementation được JavaDoc nêu). Không suy rằng đây là pool do ứng dụng tự shutdown hay cấu hình.

Đừng đưa blocking I/O dài lên common pool vô hạn mà không hiểu resource contention/capacity.

### Biến thể Async có Executor riêng

`applyToEitherAsync(other, fn, executor)` và `acceptEitherAsync(other, action, executor)` gửi callback tới executor đã chỉ định. Dùng khi cần cô lập workload, kiểm soát thread name/capacity hoặc bảo đảm callback chạy trong một execution context cụ thể.

```java
ExecutorService mapperPool = Executors.newFixedThreadPool(2);
try {
    CompletableFuture<String> result =
            left.applyToEitherAsync(right, String::trim, mapperPool);
    System.out.println(result.join());
} finally {
    mapperPool.shutdown();
}
```

Đây là **snippet trong method**, cần imports `ExecutorService`, `Executors`. Để dùng thực tế cần deadline/shutdown policy nếu callback có thể block. Executor có thể từ chối task, làm dependent completed exceptionally; biến thể Async không miễn trừ `RejectedExecutionException` hay shutdown races.

**Một hiểu nhầm:** chữ “Async” chủ yếu quy định nơi/lúc callback được dispatch, không tự khiến hai sources đã async trở nên “async hơn”, và không tạo cancellation propagation tự động.

## 9. Ví dụ Java 17 runnable: thắng bình thường, Async, exception, cancellation

Chương trình hoàn chỉnh dưới đây chạy hai sources bằng `CompletableFuture` chủ động hoàn tất để **tạo một lịch xác định**. Sau đó kiểm tra biến thể Async trên executor tên `either-worker`, tình huống một nguồn thất bại trước, và nguồn thua không tự bị hủy.

Tạo file **`EitherCombinatorsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class EitherCombinatorsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> primary = new CompletableFuture<>();
        CompletableFuture<String> fallback = new CompletableFuture<>();
        AtomicReference<String> consumed = new AtomicReference<>("none");

        CompletableFuture<String> converted = primary.applyToEither(
                fallback, value -> "mapped=" + value.toUpperCase());
        CompletableFuture<Void> observed = primary.acceptEither(
                fallback, value -> consumed.set("accepted=" + value));

        fallback.complete("backup");
        primary.complete("primary");
        System.out.println(converted.join());
        observed.join();
        System.out.println(consumed.get());
        System.out.println("primaryValue=" + primary.join());

        ExecutorService custom = Executors.newSingleThreadExecutor(
                job -> new Thread(job, "either-worker"));
        try {
            CompletableFuture<String> left = new CompletableFuture<>();
            CompletableFuture<String> right = new CompletableFuture<>();
            CompletableFuture<String> async = left.applyToEitherAsync(
                    right, value -> value + "@" + Thread.currentThread().getName(), custom);
            right.complete("fast");
            System.out.println("async=" + async.join());
            left.complete("slow");
        } finally {
            custom.shutdown();
        }

        CompletableFuture<String> broken = new CompletableFuture<>();
        CompletableFuture<String> eventual = new CompletableFuture<>();
        CompletableFuture<String> dependent =
                broken.applyToEither(eventual, value -> "ok:" + value);
        broken.completeExceptionally(new IllegalArgumentException("first failed"));
        System.out.println("earlyExceptional=" + dependent.isCompletedExceptionally());
        eventual.complete("later success");
        try {
            System.out.println(dependent.join());
        } catch (CompletionException ex) {
            System.out.println("failureCause=" + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("eventualValue=" + eventual.join());

        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<Void> notifier = first.acceptEither(second, s -> { });
        first.complete("done");
        notifier.join();
        System.out.println("acceptResultIsVoid=" + (notifier.join() == null));
        System.out.println("otherStillPending=" + !second.isDone());
        second.cancel(false);
        System.out.println("otherCancelled=" + second.isCancelled());
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 EitherCombinatorsDemo.java
java EitherCombinatorsDemo
```

**Stdout kiểm thử thực tế Java 17:**

```text
mapped=BACKUP
accepted=backup
primaryValue=primary
async=fast@either-worker
earlyExceptional=true
failureCause=IllegalArgumentException
eventualValue=later success
acceptResultIsVoid=true
otherStillPending=true
otherCancelled=true
```

### Phân tích phần chọn kết quả bình thường

`fallback.complete("backup")` diễn ra trước `primary.complete("primary")`, và cả hai callback đã được đăng ký trước. Vì vậy `converted` dùng backup và biến đổi thành `mapped=BACKUP`, còn `observed` ghi `accepted=backup`.

Sau khi fallback đã thắng, primary vẫn có thể được hoàn tất bằng `"primary"` và `primary.join()` cho ra `primaryValue=primary`. Kết quả dependent **không thay đổi theo giá trị thua đến muộn**.

### Phân tích Async với Executor được chỉ định

`left.applyToEitherAsync(right, ..., custom)` dùng executor `custom` khi thực thi callback. `right.complete("fast")` được gọi trước `left.complete("slow")`; callback trả một chuỗi gắn thread name. Vì executor có ThreadFactory đặt tên, output `async=fast@either-worker` là kết quả kiểm chứng.

**Không rút ra rằng mọi lời gọi Async luôn chạy trên thread có tên này.** Tên thread này do **chính ví dụ tự tạo**. Trong application khác, executor/thread name phụ thuộc cấu hình.

### Phân tích exception của source

`broken.completeExceptionally(new IllegalArgumentException(...))` được gọi **trước** khi `eventual` hoàn thành. Trên Java 17 được kiểm thử, dependent `applyToEither` đã completed exceptionally: `earlyExceptional=true`. Khi eventual hoàn tất bình thường về sau, dependent **không được đảo lại thành success**. `join()` ném `CompletionException` với cause `IllegalArgumentException`.

Đây là phản ví dụ thực thi cho giả định sai **“applyToEither luôn chờ source thành công đầu tiên dù source khác đã lỗi”**. Đặc tả method nói về trigger hoàn thành bình thường; với exceptional completion cạnh tranh cần đọc hợp đồng và không tự áp chính sách failover mà nó không hứa. Hành vi test đặc biệt trên Java 17 không nên dùng để suy một thứ tự tuyệt đối của mọi race giữa hai nguồn cùng hoàn tất bất thường.

### Phân tích nhánh thua và cancellation

`first.complete("done")` làm `notifier` hoàn tất bình thường với giá trị `Void`, tức `notifier.join()==null`. Trong lúc đó `second.isDone()==false`; nó **không tự bị cancel** vì một nguồn đã thắng. Application gọi `second.cancel(false)` riêng rồi thấy `otherCancelled=true`.

Ngay cả khi cancel CompletableFuture thành công, điều đó **không bảo đảm** một công việc HTTP, database hoặc computation liên quan đã bị ngắt ở tầng thực thi. Cancellation của Future và lifecycle của tác vụ nền cần được thiết kế riêng.

## 10. “Either” không phải “first successful” dưới mọi lỗi

Đây là phần dễ sai nhất của chủ đề.

Một người có thể định nghĩa mục tiêu như sau:

> Gọi hai endpoint A và B. Nếu A trả thành công trước, dùng A. Nếu A lỗi, **tiếp tục chờ B**. Chỉ báo lỗi khi **cả A và B đều thất bại**.

Đó là **first-success-failover policy**, không đồng nghĩa với semantics có thể suy giản đơn từ `applyToEither`/`acceptEither`.

### Thí nghiệm tại Java 17

Trong ví dụ trên:

1. `broken` được completed exceptionally.
2. `dependent.isCompletedExceptionally()` đã true ngay.
3. `eventual` sau đó complete bình thường.
4. `dependent` **vẫn failed**, không đổi.

Vì vậy code:

```java
CompletableFuture<String> answer =
        primary.applyToEither(backup, value -> value);
```

không phải giải pháp có cam kết “luôn thử backup khi primary lỗi”. Nếu yêu cầu thật là **chỉ kết thúc lỗi khi cả hai nguồn thất bại**, hãy tự viết một helper có policy rõ hoặc dùng một abstraction chuyên dụng được kiểm chứng.

### Đừng đánh đồng exception với null/empty

Một nguồn hoàn thành **bình thường** với giá trị null hoặc chuỗi rỗng vẫn là **normal completion**. `applyToEither` không tự biết null/empty là “không có dữ liệu tốt”; callback có thể cần validate, nhưng callback throw không có nghĩa stage tự thử lại bằng source khác.

Nếu muốn race theo **valid business result**, hãy chuẩn hóa mỗi source thành một outcome có success/failure rõ, rồi áp một coordinator hiểu tiêu chí success đó.

## 11. Ví dụ Java 17: tự tạo firstSuccessful()

Helper dưới đây nhận hai `CompletableFuture<? extends T>`, hoàn tất result ở **lần normal completion đầu tiên**. Nếu một nguồn lỗi, helper ghi nhận lỗi và tiếp tục chờ nguồn còn lại; **chỉ khi hai nguồn đều lỗi** mới cho result completed exceptionally.

Đây là một chính sách **khác** với built-in either combinators. Nó hữu ích khi muốn “success-over-failure” thật sự.

Tạo file **`FirstSuccessDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class FirstSuccessDemo {
    static <T> CompletableFuture<T> firstSuccessful(
            CompletableFuture<? extends T> left,
            CompletableFuture<? extends T> right) {
        CompletableFuture<T> winner = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();
        AtomicReference<Throwable> firstFailure = new AtomicReference<>();

        left.whenComplete((value, error) -> {
            if (error == null) {
                winner.complete(value);
            } else {
                firstFailure.compareAndSet(null, error);
                if (failures.incrementAndGet() == 2) {
                    winner.completeExceptionally(firstFailure.get());
                }
            }
        });
        right.whenComplete((value, error) -> {
            if (error == null) {
                winner.complete(value);
            } else {
                firstFailure.compareAndSet(null, error);
                if (failures.incrementAndGet() == 2) {
                    winner.completeExceptionally(firstFailure.get());
                }
            }
        });
        return winner;
    }

    public static void main(String[] args) {
        CompletableFuture<String> left = new CompletableFuture<>();
        CompletableFuture<String> right = new CompletableFuture<>();
        CompletableFuture<String> successful = firstSuccessful(left, right);
        left.completeExceptionally(new IllegalStateException("left error"));
        System.out.println("stillWaitingAfterOneFailure=" + !successful.isDone());
        right.complete("right succeeded");
        System.out.println("selected=" + successful.join());

        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();
        CompletableFuture<String> bothFailed = firstSuccessful(a, b);
        a.completeExceptionally(new IllegalArgumentException("a"));
        b.completeExceptionally(new IllegalStateException("b"));
        try {
            bothFailed.join();
        } catch (CompletionException e) {
            System.out.println("bothFailedCause=" + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 FirstSuccessDemo.java
java FirstSuccessDemo
```

**Stdout đã kiểm chứng trên Java 17:**

```text
stillWaitingAfterOneFailure=true
selected=right succeeded
bothFailedCause=IllegalArgumentException
```

### Tại sao helper có semantics khác?

- Mỗi source gọi `whenComplete` khi có outcome, bao gồm success/failure.
- Nếu `error == null`, source bình thường, helper thử `winner.complete(value)`. Chỉ completion đầu tiên thành công vì `complete` trên CompletableFuture là thao tác nguyên tử.
- Nếu source lỗi, helper ghi nhận throwable đầu tiên rồi tăng `failures`. Khi mới có 1 failure, **không hoàn tất winner**.
- Khi có 2 failures, không còn nguồn nào có thể thành công, nên helper gọi `winner.completeExceptionally(...)`.
- Nếu cả hai sources thành công gần như đồng thời, hai callbacks có thể cùng thử `complete` nhưng chỉ một lần thành công.
- Nếu success xảy ra trước khi nguồn còn lại thất bại, result đã completed bình thường; failure đến sau không thay đổi result.

### Caveats cần biết trước khi dùng production

1. **Không hủy nguồn thua.** Helper giống các either combinators ở chỗ completion của winner không tự gửi cancellation vào sources.
2. **Không gắn deadline.** Nếu một nguồn failed, nguồn kia bị treo mãi, winner cũng có thể chờ mãi. Cần orTimeout/cancellation/I/O deadlines theo contract.
3. **Không thu cả hai exceptions thành một aggregate.** Demo trả cause đầu tiên. Nếu muốn forensic detail, lưu hai failures theo nguồn và tạo một exception tổng hợp có `addSuppressed`, đồng thời bảo vệ thứ tự/ownership.
4. **Nguồn success có thể là null.** `error == null` vẫn coi là success, kể cả value null; nếu null là business failure, phải chuẩn hóa outcome trước callback.
5. **Callback khiCompletes có thể chạy ở thread hoàn tất nguồn.** Chỉ dùng logic nhẹ, không block; nếu cần scheduling tách biệt, cân nhắc `whenCompleteAsync` với executor có capacity.
6. **Hủy winner không tự hủy source futures**, trừ khi bạn thêm policy propagation riêng.
7. **Cancellation của source** xuất hiện qua error và được helper tính như một failure. Có hợp lý hay không phụ thuộc domain; cần policy riêng nếu cancellation nên hủy toàn bộ race.
8. **Giới hạn 2 sources.** Muốn N sources, cần bộ đếm và lỗi tổng hợp rõ theo số participants; không mặc định một helper hai nguồn scale đúng khi được copy-paste.
9. **Không có exactly-once side effect** với các external calls; source chưa thắng vẫn có thể đã ghi dữ liệu ra bên ngoài.

Mẫu này minh họa thành phần **first-success orchestration**. Khi triển khai production cần monitoring, timeout, thread pool capacity, exception policy và cleanup phù hợp.

## 12. Completion bình thường và bất thường ảnh hưởng thế nào?

Một `CompletableFuture<T>` có thể:

- Hoàn tất bình thường với T.
- Hoàn tất bình thường với null.
- Hoàn tất bất thường bằng throwable.
- Bị canceled, một dạng completion bất thường.
- Chưa hoàn tất; có thể vẫn đang chạy hoặc đang chờ I/O/queue.

### Một source bình thường trước

Khi `left.complete(value)` là sự kiện khiến dependent chọn một kết quả bình thường, callback có thể được kích hoạt. Nếu callback trả bình thường, dependent complete normally. Source còn lại không cần complete trước khi dependent có kết quả.

### Một source exceptional trước

**Không mặc định** dependent sẽ chờ source kia thành công. Ví dụ Java 17 trong bài xác nhận dependent `applyToEither` có thể completed exceptionally sớm. Kiểm thử hành vi JDK cụ thể nếu policy phụ thuộc chi tiết exception races, và nếu requirement là failover thật sự hãy dùng helper có contract riêng.

### Cả hai sources exceptional

Dependent không có normal value để truyền cho Function/Consumer. Nó có thể completed exceptionally. **Không giả định throwable chọn từ bên trái, bên phải hoặc bên nào fail trước trong mọi lịch cạnh tranh**. Nếu cần biết cả hai lỗi, quan sát chúng riêng bằng `handle`/`whenComplete` thay vì chỉ đọc exception của dependent.

### Callback ném exception

Ngay cả khi source đã complete normally, callback có thể fail và làm dependent complete exceptionally. Hai lớp failure cần tách trong logs:

- Source failure: HTTP request, computation, validation của nguồn.
- Dependent callback failure: mapping/conversion/consumer side effect.

### Cancellation

`future.cancel(true)` trên CompletableFuture hoàn tất nó bằng `CancellationException`; theo API của `CompletableFuture`, parameter `mayInterruptIfRunning` **không có tác dụng điều khiển interrupt** đối với CompletableFuture như đối với một số `FutureTask`. Không suy từ `cancel(true)` rằng underlying HTTP client thread bị interrupt.

## 13. get(), join(), CompletionException và ExecutionException

Sau khi tạo dependent:

```java
CompletableFuture<Integer> mapped = left.applyToEither(
        right, String::length);
```

Đây là snippet trong method, `left/right` kiểu String futures.

Cách lấy kết quả:

- `mapped.join()`: chờ và trả `Integer`; nếu dependent failed, thường ném `CompletionException` chứa cause; nếu canceled, có thể ném `CancellationException`.
- `mapped.get()`: chờ và trả `Integer`; nếu failed, ném `ExecutionException`, nếu canceled ném `CancellationException`; method có checked `InterruptedException`.
- `mapped.get(timeout, unit)`: có thể ném `TimeoutException`; **timeout ở lời get không tự cancel future**.
- `mapped.isDone()`: true khi success, failure hoặc cancel; không khẳng định kết quả hợp lệ.
- `mapped.isCompletedExceptionally()`: true khi completed exceptionally, bao gồm cancellation.
- `mapped.isCancelled()`: chỉ trạng thái canceled của chính future đó theo contract.

### Bắt exception ở đâu?

```java
try {
    int size = mapped.get(2, TimeUnit.SECONDS);
    use(size);
} catch (TimeoutException e) {
    onTimeout(e);
} catch (ExecutionException e) {
    onFailure(e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    onInterrupted(e);
}
```

Đây là code minh họa với `mapped`, `use`, `onTimeout`, `onFailure`, `onInterrupted` do caller cung cấp; cũng có thể cần xử lý `CancellationException` unchecked nếu cancellation hợp lệ trong workflow.

**Lưu ý:** hủy dependent không cam kết cancel upstream. Timeout của `get` cũng không tự thực hiện cancellation. Xử lý riêng “caller không muốn đợi nữa” và “source operation cần dừng”.

## 14. Race thật sự: hai HTTP calls, cái nào thắng?

Một ứng dụng có thể chạy hai HTTP calls song song:

```java
CompletableFuture<Payload> east =
        CompletableFuture.supplyAsync(() -> fetchEast(), ioExecutor);
CompletableFuture<Payload> west =
        CompletableFuture.supplyAsync(() -> fetchWest(), ioExecutor);

CompletableFuture<Response> result =
        east.applyToEither(west, payload -> validateAndConvert(payload));
```

Đây là **đoạn minh họa**, cần types/methods `Payload`, `Response`, `fetchEast`, `fetchWest`, `validateAndConvert` và `ioExecutor`. `supplyAsync` sẽ giao suppliers tới executor, còn `applyToEither` không có `Async` có thể thực thi callback trên thread hoàn tất nguồn.

### Những việc ứng dụng phải tự quyết định

- Nếu cả hai HTTP calls trả 200 với dữ liệu hợp lệ, chọn value được combinator quan sát theo cuộc đua.
- Nếu một call fail trước và call kia success sau, **không mặc định** built-in either combinator đảm bảo success thắng; dùng custom first-success policy nếu đó là requirement.
- Nếu một endpoint trả dữ liệu stale/invalid nhưng complete normally, combinator không tự biết nó kém chất lượng; validate trước khi đưa vào race hoặc dùng custom outcome orchestration.
- Nếu callback mapping gửi một side effect, không được coi “lần nào trả trước” là transaction đảm bảo side effect chưa từng được thực thi từ nguồn khác.
- Nếu một source chậm nhưng vẫn chạy, nó có thể tiêu tốn connection, CPU, memory và downstream quota sau khi result đã available.
- Nếu cần cancel loser, phải dùng API của HTTP client/task thực tế và hiểu cancellation semantics của nó; `CompletableFuture.cancel` không phải luôn giải pháp đủ.
- Nếu endpoint rate limits, chạy đồng thời hai calls cho mọi request có thể **nhân đôi tải**. Hãy đo cost/latency tradeoff.

## 15. Hedged requests và speculative execution

“Hedged request” là gửi một request thứ hai để giảm tail latency nếu request đầu chậm. Nó có ý tưởng liên quan either-combinator nhưng không hoàn toàn đồng nghĩa:

- **Parallel race ngay lập tức:** phát cả A và B cùng lúc; latency thấp hơn khi có nguồn nhanh, nhưng chi phí gần gấp đôi.
- **Delayed hedge:** gửi A trước, chỉ gửi B nếu A chưa hoàn tất sau một ngưỡng; cần timer, cancellation và coordinator riêng.
- **First-success:** nếu A lỗi, chờ B có thể success; cần chính sách xử lý exceptional completions như helper ở trên.
- **First-completion:** bất kỳ kết quả/lỗi nào đến trước thắng; gần với `anyOf`, không nhất thiết là policy mong muốn.
- **First-valid-response:** chỉ chọn response vượt qua validation; cần phối hợp validation với failure count và timeout.

`applyToEither`/`acceptEither` chỉ giải quyết một phần **dependent stage execution**. Hedging production còn cần retry budget, idempotency, overload protection, deadlines, observability và quyết định xử lý loser.

### Ví dụ về side effect

Không dùng hai speculative operations ghi tiền/trừ tồn kho lên cùng một business entity và tưởng “chỉ kết quả đầu tiên được đọc” có nghĩa thao tác thua bị rollback. Nếu hai sources đã thực thi side effect, cả hai vẫn có thể commit. Dùng race cho **read-only/idempotent requests** là điểm bắt đầu an toàn hơn, rồi đánh giá domain contract.

## 16. Thread nào chạy callback?

Đây là vấn đề quan trọng về hiệu năng và deadlock.

### Không Async

`applyToEither(other, fn)` và `acceptEither(other, consumer)` không cam kết callback chạy trên một pool bạn tự chọn. Ví dụ một thread gọi `fallback.complete(...)` có thể đồng thời chạy dependent callback ngay trong đường completion.

Nếu callback gọi `Thread.sleep`, query database hoặc đợi một Future khác, thread đang hoàn tất source có thể bị chiếm dụng lâu. Với một single-thread executor, callback lại chờ một task cần chính executor ấy có thể gây **thread starvation deadlock**.

### Async không chỉ định executor

Default asynchronous execution facility có thể dùng common pool. Nếu callback chạy I/O lâu và common pool còn các computations khác, bạn có thể gây contention/starvation. Khi workload cần isolation, dùng executor riêng.

### Async có executor

`applyToEitherAsync(other, fn, executor)` tách callback khỏi thread hoàn tất nguồn, nhưng bạn phải:

- Cấu hình worker count/queue capacity/rejection policy.
- Chủ động shutdown executor do application sở hữu.
- Tránh đợi nguồn khác trên cùng pool có thể bị đầy.
- Xử lý callback failure/exception.
- Không tạo một executor mới cho từng request mà không có lifecycle owner.

### Không dùng ThreadLocal như context tự truyền

Context trong `ThreadLocal` của thread tạo future không tự xuất hiện trong callback chạy trên worker khác. Nếu cần trace ID, security context hoặc tenant ID, dùng **explicit context propagation**/wrapper phù hợp, không dựa vào ngẫu nhiên callback chạy trên thread nào.

## 17. Thứ tự completion và thứ tự callback có thể khác nhau

Một phụ thuộc dễ gây bug:

```java
CompletableFuture<String> left = ...
CompletableFuture<String> right = ...
CompletableFuture<String> mapped = left.applyToEither(right, mapper);
```

Đây là snippet giả mã đặt trong method, với `mapper` và futures đã định nghĩa.

Nếu cả hai nguồn hoàn tất rất gần nhau:

- Source completion có một thứ tự thực tế ở mức state của từng Future, nhưng dependent có một cuộc đua để claim completion.
- Không nên dùng `mapped` để xác định “thứ tự tuyệt đối” giữa hai network events nếu không có timestamp/correlation/cause tracking riêng.
- Callback của `applyToEither` và callback của `acceptEither` được đăng ký riêng trên cùng cặp sources **không nhất thiết cùng chọn một bên** khi hai sources complete gần đồng thời. Ví dụ chính buộc backup hoàn tất trước, nên cả hai cùng thấy backup; đó là tính xác định của ví dụ, **không phải tính liên kết giữa hai combinators**.

Nếu bạn cần **cùng một winner cho cả transform lẫn consume**, hãy tạo **một stage winner** rồi chain các thao tác sau nó:

```java
CompletableFuture<Payload> winner =
        left.applyToEither(right, value -> value);
CompletableFuture<View> mapped = winner.thenApply(this::render);
CompletableFuture<Void> observed = winner.thenAccept(this::audit);
```

Đây là đoạn minh họa trong method. Cả `mapped` và `observed` nhận cùng kết quả nguồn đã được winner chọn, nhưng thứ tự callbacks `thenApply` và `thenAccept` **không được cam kết** nếu bạn đăng ký riêng. Nếu cần audit chỉ sau render, chain một chuỗi có phụ thuộc rõ.

## 18. Biến thể acceptEitherAsync và UI/event loop

Nếu callback cập nhật UI, hãy đảm bảo executor phù hợp với UI framework hoặc event loop; không nên gọi code UI từ một common-pool thread tùy ý. `acceptEitherAsync(other, action, uiExecutor)` có thể phù hợp nếu framework thực sự cung cấp một Executor đại diện UI thread.

Ví dụ trong Java console:

```java
ExecutorService consumerExecutor =
        Executors.newSingleThreadExecutor();
try {
    CompletableFuture<Void> processed =
            left.acceptEitherAsync(right, this::consume, consumerExecutor);
    processed.join();
} finally {
    consumerExecutor.shutdown();
}
```

Đây là code minh họa, không gắn với framework UI hay Spring. `this::consume` là method do class định nghĩa. Trong application dài hạn, nên tái sử dụng executor thay vì tạo/đóng mỗi callback.

**Không đặt event loop/UI thread chờ bằng `join()`** nếu source cũng cần event loop đó hoàn tất; đây có thể là deadlock. Đăng ký continuation và trả quyền điều khiển cho event loop thay vì block.

## 19. Timeout cho cả cuộc đua

Một either-dependent có thể bị treo nếu hai sources đều không tiến triển và không có timeout/cancellation policy.

`CompletableFuture` có:

- `orTimeout(timeout, unit)`: có thể complete future exceptionally bằng `TimeoutException` khi deadline qua.
- `completeOnTimeout(value, timeout, unit)`: có thể complete normally bằng fallback value khi timeout.
- `get(timeout, unit)`: timeout chỉ giới hạn **thời gian caller chờ**, không làm future tự complete.
- `cancel(...)`: đánh dấu completion bằng cancellation, không đồng nghĩa dừng underlying work.

Ví dụ:

```java
CompletableFuture<String> raced =
        primary.applyToEither(backup, value -> value);
raced.orTimeout(250, TimeUnit.MILLISECONDS);
```

Đây là code minh họa, unit/time budget chỉ là ví dụ. `orTimeout` **thay đổi cùng future** được gọi (trả lại reference đó), không tạo transaction timeout cho cả hai upstream sources. Sau khi raced timeout, primary/backup vẫn có thể chạy.

### Deadline end-to-end

Một request có deadline 250 ms có thể cần:

1. Deadline tại I/O operations nguồn, không chỉ Future.get.
2. Deadline trên dependent/winner.
3. Cancellation/cleanup của losers nếu platform hỗ trợ.
4. Metrics phân biệt timeout, source failure và callback failure.
5. Backpressure để tránh pool queue tiếp tục tích tụ work khi người dùng đã hết thời gian chờ.

Không dùng một timeout cho every stage rồi cộng chúng thành chuỗi kéo dài vượt SLO end-to-end.

## 20. Cancellation của nguồn thua: phải tự làm có policy

Sau khi winner được chọn, một ứng dụng có thể cố hủy loser để tiết kiệm tài nguyên. Nhưng cần phân biệt:

- `CompletableFuture.cancel(true)` đánh dấu future là canceled và các dependents tương ứng có thể complete exceptionally, **không cam kết ngắt computation underlying**.
- Một task được khởi chạy qua `ExecutorService.submit` trả `FutureTask`; `cancel(true)` của FutureTask có thể yêu cầu interrupt nếu task đang chạy. Đây là một handle khác với CompletableFuture trả về từ `supplyAsync`.
- HTTP client/network library có thể hỗ trợ cancellation qua request handle/token riêng; hành vi thực tế phụ thuộc client.
- Nếu loser đã thực thi side effect, cancel không rollback.
- Nếu loser đã complete, gọi cancel thường không làm thay đổi kết quả.
- Nếu cả hai sources chia sẻ upstream computation, hủy loser bừa bãi có thể làm hỏng người dùng khác.

**Không viết code mặc định `winner.thenRun(() -> left.cancel(true); right.cancel(true))`** vì có thể hủy cả source đã thắng (mặc dù đã completed) và ảnh hưởng những dependents khác. Cần biết chính xác source nào thắng và owner của source, đồng thời xác định việc hủy có hợp lệ hay không.

Nếu muốn theo dõi winner identity, có thể gắn nguồn vào một immutable outcome object riêng trước khi race, ví dụ `record Sourced<T>(String source, T value) {}`, sau đó xét candidate.source thay vì đoán.

## 21. Exception handling: exceptionally(), handle(), whenComplete()

Bạn có thể chain trên dependent:

```java
CompletableFuture<Integer> mapped =
        left.applyToEither(right, String::length);

CompletableFuture<Integer> recovered =
        mapped.exceptionally(error -> 0);
```

Đây là code minh họa, `left/right` kiểu CompletableFuture<String>. Nếu mapped failed, recovered có thể trả 0; nhưng điều này **không tự retry nguồn thua**. `exceptionally` chỉ cung cấp cách biến outcome thất bại thành fallback cho stage tiếp theo.

### handle()

`handle((value, error) -> ...)` chạy cho cả bình thường và bất thường, có thể biến chúng thành một result type thống nhất:

```java
CompletableFuture<String> description = mapped.handle(
        (size, error) -> error == null
                ? "size=" + size
                : "failed=" + error.getClass().getSimpleName());
```

Đây là snippet trong method. `error` có thể là wrapper CompletionException; muốn root cause cần unwrap cẩn thận theo policy. `handle` không tự chọn source khác để retry.

### whenComplete()

`whenComplete((value, error) -> ...)` phù hợp khi cần metrics/logging outcome, thường giữ outcome gốc (trừ exception do action itself theo contract), thay vì transform thành một type khác.

```java
CompletableFuture<String> observed = result.whenComplete(
        (value, error) -> logOutcome(value, error));
```

Đây là snippet, `logOutcome` được định nghĩa. Nếu logging function ném exception, dependent observational stage có thể hoàn tất bất thường. Không đặt blocking I/O dài hay secrets vào telemetry callback.

### Đừng recover bằng fallback mà nuốt lỗi nghiệp vụ

Nếu business contract là “chỉ dùng dữ liệu đã validate”, một `exceptionally(error -> defaultValue)` vô điều kiện có thể che lỗi critical. Fallback phải có provenance và trạng thái freshness phù hợp. Hãy ghi metric xác định nguồn nào thất bại, nguyên nhân và fallback được dùng có hợp lệ không.

## 22. Scope của Java Memory Model và visibility

`CompletableFuture` là một completion mechanism có synchronization. Khi một stage hoàn tất bình thường sau khi tạo result, dependent stage và thread gọi `join()/get()` quan sát state theo memory consistency contract liên quan đến `Future`/completion.

Tuy nhiên:

- Hai suppliers cùng sửa một shared `int counter++` có thể race **trước khi either-combinator chọn winner**. Completion không sửa lost update.
- Nếu sources trả reference đến một object mutable mà threads khác tiếp tục thay đổi, dependent callback không tự bảo vệ mọi future mutation. Ưu tiên immutable DTO/record hoặc ownership/locks.
- `thenApply`/`acceptEither` không biến database write cùng Future completion thành một atomic distributed transaction.
- `AtomicReference` của demo giữ trạng thái consumed an toàn; `observed.join()` đợi callback đã chạy trước khi main đọc.
- Nếu đã đăng ký hai independent either-combinators, không có shared linearization point buộc cả hai đọc cùng value trong mọi race gần đồng thời.

### Minh họa immutable result

```java
record Price(String source, long cents) {}

CompletableFuture<Price> first = ...;
CompletableFuture<Price> second = ...;

CompletableFuture<Long> cheapestAvailableSoon =
        first.applyToEither(second, Price::cents);
```

Đây là code minh họa. Tên `cheapestAvailableSoon` **chưa đúng về semantics**: giá được trả bởi source hoàn tất trước, không chắc là giá rẻ nhất. Nên đặt tên `firstAvailablePrice` nếu đó là ý định. Nếu muốn **min price**, phải chờ đủ hai và `thenCombine` để so sánh.

## 23. Giới hạn khi một nguồn hoàn thành sớm nhưng trả dữ liệu xấu

Một source có thể complete normally với JSON parseable nhưng stale. `applyToEither` chọn nó theo completion, còn callback check freshness thấy invalid và ném. Không có built-in guarantee rằng nguồn khác sẽ tự được thử lại như một alternative.

Hai cách tiếp cận:

1. **Validate trong từng source pipeline** để output source là một future failed nếu dữ liệu không hợp lệ, rồi dùng **firstSuccessful helper** như ở trên.
2. **Dùng một outcome coordinator** nhận `Result.Success(value)`/`Result.Failure(error)`, chỉ hoàn tất winner khi có Success; aggregate Failure khi không còn nguồn nào.

Không nên biến invalid value thành null rồi trông chờ either-combinator bỏ qua; null vẫn là normal completion của CompletableFuture.

### Business tie-breaking

Nếu hai sources thành công gần như đồng thời nhưng bạn cần ưu tiên primary khi cùng deadline, either-combinator không cam kết policy đó. Bạn cần explicit decision rule dựa trên:

- Priority level và deadline window.
- Timestamp được đo nhất quán/monotonic.
- Data freshness/version.
- Latency budget và quality score.

Một phép race theo completion không thay thế thuật toán ranking.

## 24. Khi nào nên dùng thenCombine thay either?

Ví dụ bạn cần **cả giá và phí vận chuyển**:

```java
CompletableFuture<Long> price = ...;
CompletableFuture<Long> shipping = ...;
CompletableFuture<Long> total =
        price.thenCombine(shipping, Long::sum);
```

Đây là code minh họa. `thenCombine` chờ hai sources bình thường, kết hợp price + shipping. Dùng `applyToEither` ở đây sẽ sai: nó chỉ chọn một trong hai giá trị, không cộng chúng.

Ví dụ kiểm tra hai nhà cung cấp đều đồng ý một version: dùng `thenCombine` để đối chiếu, không dùng either.

### Khi nào nên dùng anyOf?

Nếu requirement thực sự là **first completion, kể cả lỗi**, `anyOf` có semantics khác. Nhưng return Object và exception handling cần định nghĩa. Không nên chọn `anyOf` chỉ để tránh quyết định giữa `applyToEither` và `acceptEither` khi bạn biết hai nguồn cùng kiểu T và cần mapping/consumption.

## 25. Backpressure và resource ownership khi race

Hai nguồn cùng chạy thường tăng lượng công việc so với một nguồn:

- Gấp đôi HTTP requests có thể tăng p99 latency ở downstream dù latency riêng của caller giảm.
- Hai tasks có thể chiếm hai worker threads/connection slots.
- Nếu caller đã timeout nhưng sources vẫn chạy, backlog và work queue có thể tích tụ.
- Common pool có thể bị ảnh hưởng khi bạn đặt blocking callbacks vào đó.
- Cancellation không chắc giải phóng socket/thread/connection ngay.
- Error metrics có thể mất nếu chỉ quan sát dependent winner, bỏ qua loser failure.

Một system production nên có:

1. Concurrency limit cho speculative tasks.
2. Timeout riêng của I/O và deadline end-to-end.
3. Metrics source A/B, winner distribution, failed/timeout/canceled, callback latency.
4. Idempotency policy cho repeated operations.
5. Circuit breaker/rate limits khi một nguồn thường lỗi.
6. Ownership của executors và cancellation handles.
7. Shutdown logic bảo đảm không còn resource leak.

Nếu traffic thấp và yêu cầu đơn giản, một source với fallback tuần tự có thể đủ tốt hơn việc fan-out mọi request. Chọn race khi latency benefit thực sự đáng chi phí.

## 26. Bẫy thread starvation deadlock

Một sai lầm:

```java
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> slowA(), single);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> slowB(), single);
CompletableFuture<String> winner =
        a.applyToEither(b, value -> value);
```

Đây là code minh họa, `slowA/slowB` cần khai báo. Dùng một worker duy nhất khiến hai suppliers thường **không chạy song song**, nên không tạo một race thật sự: B nằm trong queue khi A đang chạy.

Nguy hiểm hơn nếu một callback trên chính worker ấy gọi `winner.join()` trước khi bất kỳ supplier có worker để hoàn tất: một thread có thể block đang chiếm slot duy nhất, khiến tasks nguồn không có worker tiến triển.

**Giải pháp:** thiết kế resource capacity đủ cho những tasks phải đồng thời hoàn tất, tránh gọi `join()/get()` trong callback phụ thuộc vào cùng pool nhỏ, và dùng async continuations thay blocking waits.

“Có hai CompletableFuture” **không có nghĩa thực sự có hai computations song song**, nhất là khi cả hai dùng cùng executor một worker hoặc logic nguồn thực ra chạy tuần tự.

## 27. Lỗi khi cancellation hoặc timeout xảy ra trước mapping

Tình huống:

- Dependent đã đăng ký.
- Một source bị `cancel`, source còn lại chưa hoàn tất.
- Dependent có thể bị affected bởi exceptional outcome theo JDK behavior, không mặc định “đợi success của còn lại”.
- Caller gọi `dependent.orTimeout(...)` và dependent timed out.
- Source còn lại sau đó complete normal, nhưng dependent đã hoàn tất bất thường nên **không thể đổi kết quả**.

Do đó cần ba lớp policy riêng:

- **Source cancellation:** source operation có thể ngừng? Khi nào?
- **Race selection:** success/failure/timeout nào được coi là winning result?
- **Caller cancellation:** caller không cần kết quả nữa; có cần cancel nguồn và side effects không?

Trong first-success helper, source cancellation hiện được tính là một failure. Nếu domain muốn “canceled one source => cancel entire race”, helper phải sửa. Không sửa semantics theo cảm tính sau khi test pass.

## 28. Debugging và kiểm thử xác định

### Test callback value, không test sleep

Một test tốt tạo hai `CompletableFuture` chưa hoàn tất, đăng ký dependent, rồi chủ động gọi `right.complete("R")` trước `left.complete("L")`. Sau đó assert mapped value là R. Không cần sleep, không phụ thuộc scheduler.

### Test both-completion gần đồng thời

Dùng `CountDownLatch`/`CyclicBarrier` để cho hai threads complete gần nhau và xác nhận result thuộc **một trong hai values hợp lệ**, không hard-code bên nào thắng. Nếu cần exact priority, hãy kiểm thử một coordinator có tie-break explicit.

### Test exception behavior

- Source A complete exceptionally, B pending.
- Kiểm tra dependent outcome theo policy đã chọn.
- B complete normally sau đó, kiểm tra dependent có đổi được không (CompletableFuture chỉ complete một lần).
- Nếu yêu cầu success-over-error, dùng firstSuccessful helper rồi assert dependent còn pending sau A failure và sau B success trả B.
- Cả A/B fail: assert cause/aggregate failure theo contract.
- Callback throw: assert dependent failed, không suy source failed.
- Cancellation: assert loser vẫn pending nếu chưa cancel, sau explicit cancel mới canceled.
- Timeout: kiểm tra deadline của caller và resource cleanup riêng.

### Race detector tư duy

Khi review code, hỏi:

1. **Có bao nhiêu nguồn?** Hai hay N, có thực sự chạy song song không?
2. **Stage nào là nguồn?** `CompletableFuture<T>` gốc hay stage đã transform/validate?
3. **Điều kiện thắng là gì?** First completion, first normal, first valid, first successful over errors hay priority-based?
4. **Tại sao callback chạy?** Source completion đã bình thường hay dependent đang phục hồi exception?
5. **Callback chạy ở đâu?** Calling thread, common pool, executor riêng?
6. **Ai sở hữu cancellation?** Winner có quyền dừng loser không?
7. **Cần đúng một side effect hay chỉ một chosen result?** Hai ý này khác nhau.
8. **Có timeout/backpressure/metrics không?** Race không tự giải quyết chúng.

## 29. Những hiểu lầm thường gặp

1. **“applyToEither và acceptEither đều trả giá trị U mới.”** Sai: `acceptEither` trả `CompletableFuture<Void>`.
2. **“applyToEither có nghĩa kết quả nhanh hơn luôn tốt hơn.”** Không; nó chọn theo completion, không kiểm tra chất lượng business.
3. **“Either luôn chờ success đầu tiên dù bên kia đã failed.”** Không được dựa vào điều này; Java17 demo chứng minh early exceptional dependent.
4. **“Callback biến đổi lỗi thì tự thử source khác.”** Không: exception của Function/Consumer làm dependent failed.
5. **“Chỉ bên thắng chạy; bên thua tự dừng.”** Sai: cả sources có thể tiếp tục side effects.
6. **“CompletableFuture.cancel(true) giết thread xử lý HTTP.”** Không: mayInterruptIfRunning không có tác dụng ở CompletableFuture theo API.
7. **“Future.get(timeout) làm source bị cancel.”** Sai: nó chỉ giới hạn thời gian đợi của caller.
8. **“AcceptEither đã hoàn tất nghĩa là Consumer không thể ném lỗi.”** Nếu Consumer ném, dependent failed.
9. **“Async luôn tạo thread mới.”** Không: nó dùng một executor, có thể reuse workers.
10. **“Không Async luôn chạy trên main thread.”** Không; callback có thể chạy ở thread hoàn tất một source.
11. **“thenCombine giống applyToEither.”** Không; thenCombine cần cả hai sources bình thường.
12. **“anyOf chờ first success.”** Không; nó có thể hoàn thành bằng exception đầu tiên.
13. **“Hai either callbacks trên cùng sources luôn cùng chọn winner.”** Không bảo đảm nếu cạnh tranh gần đồng thời; chain một winner stage để nhất quán.
14. **“Đã có result thì nguồn loser có thể bỏ qua lỗi mà không log.”** Không, loser còn có thể fail/giữ resource và cần metrics/cleanup.
15. **“Value null nghĩa future chưa hoàn thành.”** Không: CompletableFuture có thể completed normally với null.
16. **“Hủy dependent tự động hủy upstream.”** Không có auto propagation nói chung.
17. **“Mapped stage successful nghĩa external side effect commit exactly once.”** Sai; stage completion là trạng thái in-process.
18. **“Hai source futures trên một single-thread executor chắc chắn race thật.”** Không; một task có thể nằm trong queue.
19. **“Function không Async có thể làm I/O lâu không ảnh hưởng producer thread.”** Sai, callback có thể chạy inline trong completion thread.
20. **“First-success helper không cần xử lý nguồn treo mãi.”** Sai; nếu một failure và một pending vĩnh viễn thì result cũng pending mãi nếu không timeout.
21. **“Bắt Exception rồi trả fallback luôn là đúng.”** Có thể che lỗi validation, security hoặc data integrity.
22. **“Một winner nghĩa không tốn tài nguyên của loser.”** Sai; fan-out có thể nhân đôi tải upstream.
23. **“Source A luôn thắng nếu đăng ký applyToEither từ A.”** Không, other có thể thắng theo completion.
24. **“Nếu both complete trước thì Java luôn chọn left.”** Không nên phụ thuộc implementation scheduling; đừng sử dụng làm tie-break.
25. **“Đo kết quả race bằng Thread.sleep sẽ tái hiện mọi interleaving.”** Sai; dùng explicit completion/latches và assert invariants.
26. **“Tự dùng source.complete có nghĩa đang có network concurrency.”** Không: đó là cách test completion semantics xác định.
27. **“Một source failure sẽ làm source kia tự failure.”** Không mặc định; sources là các stage độc lập.
28. **“Timeout của dependent sẽ làm I/O timeout.”** Không, cần deadline trên underlying operation.
29. **“Using join trong UI thread an toàn vì Future là async.”** Sai: join blocking nếu chưa completed, có thể freeze UI/deadlock.
30. **“CompletionStage methods giống nhau trên mọi Java implementation và mọi exceptional interleaving.”** Chỉ dựa vào API contract chính thức và policy do mình tự thiết kế khi correctness phụ thuộc.

## 30. Checklist áp dụng trong dự án

Trước khi đưa `applyToEither` hoặc `acceptEither` vào code, xác minh:

- **Requirement:** lấy U hay chạy side effect Void? Chọn `Function` hoặc `Consumer` phù hợp.
- **Winner semantics:** first normal value, first completion, first valid response hay first successful after failures?
- **Failure:** một nguồn lỗi trước có làm dependent thất bại sớm không; test JDK đang triển khai?
- **Data validation:** nguồn normal nhưng value không hợp lệ có được coi success không?
- **Tie-break:** hai nguồn gần đồng thời có cần priority/source preference?
- **Executor:** callback synchronous có block completion thread? Cần Async với executor bounded?
- **Capacity:** hai tasks có thực sự chạy đồng thời hay bị queue một-worker?
- **Resource:** loser còn chạy; có cancellation/cleanup được thực hiện hợp lệ không?
- **I/O deadlines:** timeout của underlying calls có tương thích end-to-end SLO?
- **Callback errors:** Function/Consumer throw được log và xử lý ở dependent?
- **Context:** trace/tenant/user context được propagate có chủ đích?
- **Side effects:** có idempotency, ack và transaction phù hợp nếu Consumer ghi data?
- **Testing:** normal left/right, callback throw, one source error, both error, canceled, timeout, simultaneous completions?
- **Observability:** track winner distribution, loser failures, p95/p99, speculative request cost?
- **Shutdown:** executor do ai sở hữu, có ngừng nhận việc và đợi/cleanup task không?
- **Java version:** sample chạy JDK 17; API được dùng có tồn tại trong deployment runtime không?
- **Module scope:** chỉ áp dụng Java concurrency, tránh trộn với scheduling/framework riêng không thuộc mục tiêu.

## 31. Câu hỏi ôn tập và đáp án

**Câu 1.** Khác biệt chính giữa `applyToEither` và `acceptEither` là gì?  
**Đáp án:** `applyToEither` dùng `Function<T,U>` và trả `CompletableFuture<U>`; `acceptEither` dùng `Consumer<T>` và trả `CompletableFuture<Void>`.

**Câu 2.** Nếu backup complete normal trước primary, dependent có nhất thiết chờ primary không?  
**Đáp án:** Không; khi backup được chọn và callback hoàn tất, dependent có kết quả mà không cần primary hoàn tất trước.

**Câu 3.** Callback `applyToEither` có được tự động chạy lần thứ hai với source khác nếu callback đầu ném exception không?  
**Đáp án:** Không có retry/fallback như vậy theo contract; dependent có thể completed exceptionally.

**Câu 4.** `acceptEither` consumer chạy xong bình thường thì `done.join()` trả gì?  
**Đáp án:** Một giá trị `Void`, bình thường là null; source value không được trả từ dependent.

**Câu 5.** Sau `applyToEither` có winner, source thua có tự canceled không?  
**Đáp án:** Không; nó có thể vẫn pending, running và hoàn tất về sau.

**Câu 6.** `applyToEitherAsync(other, fn, executor)` khác bản không Async thế nào?  
**Đáp án:** Callback được dispatch qua executor chỉ định; bản không Async có thể chạy trong thread hoàn tất nguồn/đăng ký callback.

**Câu 7.** Dùng `applyToEither` để lấy giá thấp nhất giữa hai nhà cung cấp có đúng không?  
**Đáp án:** Không. Nó chọn theo completion, không so sánh giá; dùng `thenCombine` nếu cần cả hai để chọn min.

**Câu 8.** `CompletableFuture.anyOf` có luôn chọn success đầu tiên không?  
**Đáp án:** Không; nó hoàn tất khi một nguồn bất kỳ hoàn tất, kể cả bằng exception.

**Câu 9.** Một source failed sớm, source khác success sau: có được đảm bảo built-in either sẽ trả success không?  
**Đáp án:** Không. Java17 test cho thấy dependent có thể failed sớm; muốn always prefer success, tự dùng helper firstSuccessful.

**Câu 10.** FirstSuccessful helper trong bài báo lỗi khi nào?  
**Đáp án:** Khi cả hai sources đã failed. Một failure đơn lẻ khiến helper vẫn đợi source còn lại.

**Câu 11.** Nếu một source failed và source còn lại treo mãi, firstSuccessful helper có tự complete không?  
**Đáp án:** Không. Phải thêm deadline/timeouts/cancellation policy.

**Câu 12.** `cancel(true)` trên CompletableFuture có chắc interrupt underlying work không?  
**Đáp án:** Không. Theo CompletableFuture API, mayInterruptIfRunning không có tác dụng tương tự FutureTask.

**Câu 13.** Hai independent callbacks `applyToEither` và `acceptEither` có chắc luôn chọn cùng nguồn không?  
**Đáp án:** Không nếu sources hoàn tất gần nhau; muốn same winner, tạo một winner stage và chain các callbacks từ nó.

**Câu 14.** Gọi `get(100, MILLISECONDS)` timeout có tự cancel dependent không?  
**Đáp án:** Không; timeout chỉ giới hạn chờ của caller.

**Câu 15.** Có thể nhận kết quả nguồn qua `acceptEither` không?  
**Đáp án:** Không trực tiếp; callback là Consumer, dependent kiểu Void. Dùng `applyToEither` nếu cần return value.

**Câu 16.** Callback ném `IllegalArgumentException` làm source đang complete normal trở thành failed không?  
**Đáp án:** Không. Dependent callback stage có thể failed; nguồn gốc vẫn giữ trạng thái riêng.

**Câu 17.** Vì sao speculative requests có thể làm throughput toàn hệ thống xấu đi?  
**Đáp án:** Gửi hai request thay một, tăng CPU/network/connections/downstream load, nhất là khi losers không dừng.

**Câu 18.** Làm sao kiểm thử winner bình thường một cách xác định mà không dùng sleep?  
**Đáp án:** Đăng ký dependent trên hai incomplete futures rồi gọi `right.complete("R")` trước `left.complete("L")`; assert dependent nhận R.

**Câu 19.** Nếu một supplier trả null, CompletableFuture có coi đó là normal completion không?  
**Đáp án:** Có. Null không tự bị xem là failure; nếu business yêu cầu non-null, validate riêng.

**Câu 20.** Completion của một CompletableFuture có bảo đảm external transaction đã commit không?  
**Đáp án:** Không; đây là outcome in-process. Cần ack/transaction/idempotency đối với side effects ngoài JVM.

## 32. Bài tập thực hành

### Bài tập A — mapping trước, consumer sau

Tạo hai `CompletableFuture<String>` và đăng ký `applyToEither` biến đổi chuỗi thành record `Result(String source, int length)`. Đăng ký `thenAccept` từ winner stage để log kết quả, đảm bảo cả biến đổi và consumer dùng **cùng winner**. Hoàn tất backup trước, xác minh output và source identity.

### Bài tập B — exceptional loser

Đăng ký built-in `applyToEither`, rồi làm A `completeExceptionally` và B `complete` về sau. Quan sát trạng thái dependent trên JDK 17 và giải thích vì sao không được coi nó là first-success policy. Sau đó thay bằng `firstSuccessful` và assert result trả B.

### Bài tập C — two failures

Dùng `firstSuccessful` cho hai nguồn cùng failed. Mở rộng helper để tạo `AggregateFailure` lưu cả hai causes qua `addSuppressed`, đặt tên nguồn và phân biệt cancellation với lỗi nghiệp vụ.

### Bài tập D — timeout và winner

Tạo một source complete sau deadline (bằng test scheduler có kiểm soát), một source treo. Áp `orTimeout` lên dependent và xác minh dependent failed do TimeoutException. Sau đó xác minh source tardy vẫn có thể complete; cân nhắc cancellation thật của underlying I/O.

### Bài tập E — Executor overload

Dùng executor bounded và một callback `acceptEitherAsync` làm I/O chậm; tạo nhiều races để thấy queue tăng hoặc callback bị reject. Thêm rejection/timeout policy để không treo caller vô hạn.

### Bài tập F — near-simultaneous completions

Dùng hai threads và `CountDownLatch` cho phép complete A/B gần nhau. Không assert cố định A hoặc B thắng; chỉ assert winner thuộc tập {A,B} và callback được ghi nhận đúng theo một stage winner duy nhất.

### Bài tập G — business validity

Mỗi nguồn trả `Response(data, isFresh)`. Thiết kế coordinator để chỉ chọn response có `isFresh=true`; nếu một response stale thì ghi lỗi logic và đợi nguồn còn lại; nếu cả hai stale/failed thì tạo aggregate failure. Giải thích vì sao đơn thuần applyToEither không tự hiểu business validity.

## 33. Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `applyToEither`, `acceptEither`, `Async` variants, cancellation, `orTimeout`, `completeOnTimeout`, `join`, `whenComplete`.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): completion-stage combinator contracts, normal/exceptional completions.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, `isDone` và memory consistency.
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): nơi thực thi callback/task.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future và shutdown.
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper exception khi async pipeline hoàn tất bất thường.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp test cạnh tranh completion.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): memory ordering, happens-before và data races.

**Tổng kết:** `applyToEither` lấy một kết quả nguồn được chọn để **biến đổi thành U**; `acceptEither` lấy một kết quả nguồn được chọn để **thực hiện Consumer rồi trả Void**. Cả hai hữu ích khi hai sources cạnh tranh, nhưng **không tự cancel loser**, không tạo transactional side effects và không là first-success-failover tuyệt đối khi exceptional completions xảy ra. Hãy xác định chính xác chính sách thắng, dùng `Async`/executor đúng workload, deadline/cancellation rõ ràng, quan sát exception, và dùng **firstSuccessful helper** khi yêu cầu là “chờ thành công đầu tiên; chỉ thất bại khi cả hai nguồn thất bại”.