# CompletableFuture: thenApply(), thenAccept(), thenRun()

## 1. Tại sao cần ba phương thức khác nhau?

`CompletableFuture<T>` trong `java.util.concurrent` đại diện cho một phép tính có thể hoàn tất sau và hỗ trợ **xây dựng chuỗi xử lý phụ thuộc** (dependent stages). Thay vì chặn thread gọi bằng `get()` ngay sau khi gửi task, bạn có thể đăng ký bước tiếp theo sẽ chạy **khi stage trước hoàn tất bình thường**.

Ba phương thức thường gặp là:

- **`thenApply(Function<? super T, ? extends U>)`**: nhận kết quả `T`, **biến đổi** thành giá trị `U`, trả về `CompletableFuture<U>`.
- **`thenAccept(Consumer<? super T>)`**: nhận kết quả `T` và **tiêu thụ** nó bằng side effect, không tạo giá trị đầu ra mới; trả về `CompletableFuture<Void>`.
- **`thenRun(Runnable)`**: chạy thao tác **không nhận kết quả `T`** và không trả giá trị, sau khi stage trước hoàn tất bình thường; trả về `CompletableFuture<Void>`.

Điểm phân biệt chính là **callback nhận gì và stage mới trả gì**, không phải việc callback có chạy trên một thread mới hay không. Cả ba bản **không có hậu tố Async** đều có thể chạy bởi thread vừa hoàn thành stage nguồn hoặc bởi thread khác đang gọi phương thức completion; không được dựa vào một thread name cụ thể.

~~~text
CompletableFuture<T> hoàn tất bình thường với giá trị T
         |
         +--- thenApply(T -> U) ----> CompletableFuture<U>
         |
         +--- thenAccept(T -> void) -> CompletableFuture<Void>
         |
         +--- thenRun(() -> void) --> CompletableFuture<Void>
~~~

**Ghi nhớ nhanh:** cần giá trị để tiếp tục xử lý → `thenApply`; cần dùng kết quả nhưng không phát sinh giá trị stage mới → `thenAccept`; chỉ cần biết bước trước hoàn tất → `thenRun`.

Bài học sử dụng **Java Concurrency chuẩn** và các ví dụ JDK 17+, không đi vào tích hợp framework.

## 2. Callback và generic: một bảng so sánh

| API | Functional interface | Tham số callback | Callback trả về | Stage trả về |
|---|---|---|---|---|
| `thenApply(fn)` | `Function<T,U>` | Kết quả `T` của stage nguồn | `U` | `CompletableFuture<U>` |
| `thenAccept(action)` | `Consumer<T>` | Kết quả `T` của stage nguồn | `void` | `CompletableFuture<Void>` |
| `thenRun(action)` | `Runnable` | **Không nhận kết quả** của stage nguồn | `void` | `CompletableFuture<Void>` |

Ví dụ chữ ký ở dạng rút gọn (không phản ánh toàn bộ wildcard generic của thư viện):

~~~java
CompletableFuture<U> next = previous.thenApply(value -> transform(value));
CompletableFuture<Void> consumed = previous.thenAccept(value -> consume(value));
CompletableFuture<Void> finished = previous.thenRun(() -> notifyFinished());
~~~

Ba dòng trên là **minh họa** với các biến và hàm giả định đã khai báo, không phải class biên dịch độc lập.

**Lưu ý quan trọng về `Void`:** Stage từ `thenAccept` và `thenRun` vẫn là một CompletableFuture thực sự, có thể gọi `join()`, `get()`, `isDone()`, `thenRun()`, `whenComplete()` hoặc gắn xử lý lỗi. Nếu nó hoàn tất bình thường, **`join()` trả `null`** vì không có giá trị nghiệp vụ được sinh ra, chứ không phải vì stage không tồn tại.

`thenApply` có thể trả `null` từ lambda và tạo `CompletableFuture<U>` hoàn tất bình thường với giá trị `null`; điều này khác với `CompletableFuture<Void>` dùng để chỉ không có giá trị đầu ra. Nếu pipeline không chấp nhận null, hãy kiểm tra/biểu diễn kết quả bằng kiểu thích hợp (ví dụ `Optional<T>`) thay vì suy luận null là failure.

## 3. Ví dụ Java 17: một chuỗi tuần tự

Ví dụ dùng `completedFuture(10)` để stage đầu đã hoàn tất. Nhờ đó có thể học đúng kiểu dữ liệu và kết quả mà không bị nhiễu bởi lịch thực thi đa luồng.

Lưu file **CompletableFutureChainDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureChainDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(10);

        CompletableFuture<String> mapped = source.thenApply(
                number -> "value=" + (number * 2));

        CompletableFuture<Void> consumed = mapped.thenAccept(
                value -> System.out.println("accept=" + value));

        CompletableFuture<Void> finished = consumed.thenRun(
                () -> System.out.println("run=completed"));

        finished.join();

        System.out.println("source=" + source.join());
        System.out.println("mapped=" + mapped.join());
        System.out.println("consumed result=" + consumed.join());
        System.out.println("finished result=" + finished.join());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac CompletableFutureChainDemo.java
java CompletableFutureChainDemo
~~~

Stdout:

~~~text
accept=value=20
run=completed
source=10
mapped=value=20
consumed result=null
finished result=null
~~~

**Đọc chuỗi theo thứ tự:**

1. Source là `CompletableFuture<Integer>` với kết quả `10`.
2. `thenApply` nhận `10`, biến đổi thành chuỗi `"value=20"`; biến `mapped` có kiểu `CompletableFuture<String>`.
3. `thenAccept` nhận chuỗi và in một dòng; stage `consumed` có kiểu `CompletableFuture<Void>`.
4. `thenRun` chỉ biết stage `consumed` đã hoàn thành bình thường; callback không nhận chuỗi `"value=20"`.
5. `finished.join()` đợi toàn bộ chuỗi; `join()` của hai stage `Void` trả `null` khi thành công.

Các callback được đăng ký trên một `completedFuture` nên ở ví dụ này chúng có thể chạy ngay trong lúc đăng ký. **Đừng suy luận rằng mọi `thenApply` trong ứng dụng luôn chạy trên main thread**; điều kiện hoàn tất ở runtime quyết định thread thực thi với bản non-Async.

## 4. Ba nhánh độc lập từ cùng một nguồn

`thenApply`, `thenAccept` và `thenRun` có thể **cùng phụ thuộc vào một stage nguồn** thay vì nối thành một chuỗi. Khi đó chúng là các dependent stages độc lập và có thể thực thi theo thứ tự khác nhau nếu nguồn hoàn tất bất đồng bộ.

Ví dụ dùng `completedFuture` và chỉ in kết quả **sau khi `allOf(...).join()`**, vì vậy stdout không phụ thuộc vào thứ tự callback:

Lưu **CompletableFutureBranchesDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureBranchesDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(7);

        CompletableFuture<Integer> square =
                source.thenApply(value -> value * value);

        AtomicInteger observed = new AtomicInteger(-1);
        CompletableFuture<Void> accepted =
                source.thenAccept(observed::set);

        AtomicBoolean notification = new AtomicBoolean();
        CompletableFuture<Void> ran =
                source.thenRun(() -> notification.set(true));

        CompletableFuture.allOf(square, accepted, ran).join();

        System.out.println("square=" + square.join());
        System.out.println("observed=" + observed.get());
        System.out.println("notification=" + notification.get());
        System.out.println("source=" + source.join());
    }
}
~~~

Chạy:

~~~bash
javac CompletableFutureBranchesDemo.java
java CompletableFutureBranchesDemo
~~~

Stdout:

~~~text
square=49
observed=7
notification=true
source=7
~~~

**Giải thích:** `thenApply` tạo stage mới chứa `49`; `thenAccept` ghi kết quả vào `AtomicInteger`; `thenRun` chỉ đánh dấu sự kiện hoàn tất bằng `AtomicBoolean`. Cả ba phụ thuộc vào cùng source `7`, nhưng **không phụ thuộc lẫn nhau**. `CompletableFuture.allOf(...)` dùng để đợi cả ba hoàn tất. Bài toán thực tế cần cân nhắc xử lý lỗi của `allOf` nếu một nhánh thất bại.

`thenRun` không nhận giá trị từ source qua tham số. Nếu lambda đọc biến ngoài được capture, đó là dữ liệu từ môi trường bao quanh (closure), **không phải tham số của API `thenRun`**; cần đảm bảo quy tắc đồng bộ và tính đúng đắn khi truy cập shared state.

## 5. Kết quả gốc có bị thay đổi không?

**Không.** `thenApply`, `thenAccept` và `thenRun` đều **tạo ra một dependent CompletableFuture mới**. Gắn callback không thay thế kết quả của source. Ví dụ sau:

~~~java
// MINH HỌA: source là CompletableFuture<Integer>.
CompletableFuture<String> derived =
        source.thenApply(value -> "ID-" + value);
~~~

Nếu source hoàn tất với `42`, source vẫn mang `Integer 42`; derived mang `String "ID-42"` khi callback thành công. Nếu callback ném lỗi, **derived** hoàn tất bất thường còn source đã thành công vẫn thành công.

Đây là tính chất cần thiết cho pipeline: bạn có thể gắn các nhánh xử lý khác nhau lên cùng source. Tuy nhiên **side effect trên object mà source chứa** (ví dụ callback sửa một `List` mutable được chia sẻ) vẫn có thể thay đổi trạng thái quan sát được. Không nên đồng nhất “source Future không đổi” với “toàn bộ dữ liệu tham chiếu tuyệt đối bất biến”.

## 6. thenApply(): biến đổi kết quả và giữ khả năng kết hợp

`thenApply` phù hợp khi bước sau cần **kết quả mới**:

- Ánh xạ DTO → domain model hoặc domain → view model.
- Chuyển `String` → `Integer` sau khi parse hợp lệ.
- Tính toán hoặc chuẩn hóa một kết quả đã nhận.
- Chuyển từ kiểu `T` sang kiểu `U` cho bước tiếp theo.

Ví dụ:

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("123")
                .thenApply(Integer::parseInt);
int answer = parsed.join(); // 123.
~~~

Đây là **đoạn minh họa** có thể đặt trong một phương thức và có import phù hợp.

Nếu `Integer.parseInt` ném `NumberFormatException`, stage `parsed` hoàn tất bất thường, không có `Integer` được phát ra. Không có phép biến đổi ngầm thành `null` hoặc 0 khi lambda lỗi.

### Không nhầm thenApply với thenCompose

Nếu callback **trả về một Future khác**:

~~~java
// lookupAsync: giả định trả CompletableFuture<User>.
// idStage: giả định là CompletableFuture<Long>.
CompletableFuture<CompletableFuture<User>> nested =
        idStage.thenApply(id -> lookupAsync(id));
~~~

`thenApply` **không tự làm phẳng** `CompletableFuture<CompletableFuture<User>>`. Nếu ý định là gọi một thao tác async thứ hai rồi nối phẳng kết quả, dùng:

~~~java
CompletableFuture<User> flat =
        idStage.thenCompose(id -> lookupAsync(id));
~~~

Hai đoạn trên là **mã minh họa** với `User` và `lookupAsync` giả định; không phải lớp độc lập. `thenCompose` cần một hàm trả `CompletionStage<U>`, còn `thenApply` chỉ cần trả `U`; đối với lambda trả Future, `U` của thenApply chính là kiểu Future đó.

**Không dùng `thenApply(f -> f.join())` như cách thay thế thenCompose một cách máy móc**: chờ đồng bộ trong callback có thể chiếm worker và tạo tắc nghẽn nếu tác vụ đợi phụ thuộc vào cùng executor.

## 7. thenAccept(): tiêu thụ kết quả, thường là side effect

`thenAccept` phù hợp cho hành động không cần phát sinh giá trị đầu ra:

- Ghi kết quả vào bộ lưu trữ hoặc vùng kết quả đã có giao thức đồng bộ.
- Cập nhật metrics/log/audit sau khi tính toán thành công.
- Gửi thông báo hoặc thực hiện bước xử lý cuối yêu cầu một `T`.
- Đẩy một giá trị sang sink, nếu sink có cách xử lý lỗi và giới hạn tải phù hợp.

`Consumer<T>.accept(T)` có kiểu `void`, nên callback này không thể trả `U` cho stage kế tiếp. Sau `thenAccept`, kiểu stage là `CompletableFuture<Void>`.

~~~java
// MINH HỌA: source là CompletableFuture<String>.
CompletableFuture<Void> logged =
        source.thenAccept(message -> System.out.println(message));
CompletableFuture<Void> afterLog =
        logged.thenRun(() -> System.out.println("log step finished"));
~~~

Nếu muốn **vừa có side effect vừa giữ lại giá trị** cho stage kế tiếp, có thể dùng `thenApply` trả về giá trị ban đầu sau khi đã thực hiện tác động, nhưng cần cân nhắc thiết kế hàm có side effect:

~~~java
CompletableFuture<String> unchangedValue =
        source.thenApply(message -> {
            recordMetric(message); // Minh họa một hàm ứng dụng đã định nghĩa.
            return message;
        });
~~~

Khi nghiệp vụ chỉ cần quan sát mà muốn giữ nguyên kết quả/exception cho các bước khác, có thể cân nhắc `whenComplete` — API này có ngữ nghĩa khác và được trình bày ở phần xử lý lỗi.

**Side effect có thể chạy trên thread hoàn tất source** với bản non-Async; do đó thao tác nặng, blocking I/O hoặc logging đồng bộ dài có thể làm chậm thread đang complete Future. Nên chọn executor và giới hạn concurrency rõ ràng nếu sink có tải đáng kể.

## 8. thenRun(): tín hiệu hoàn thành, không nhận giá trị

`thenRun` phù hợp khi hành động sau không phụ thuộc vào dữ liệu trả về, ví dụ thông báo một bước thành công, cập nhật một cờ giai đoạn hoặc đánh dấu kết thúc phần việc. Nó có điều kiện chạy giống hai phương thức còn lại: **stage trước hoàn tất bình thường**.

Ví dụ:

~~~java
CompletableFuture<Void> notified =
        CompletableFuture.completedFuture("ready")
                .thenRun(() -> System.out.println("finished"));
~~~

`thenRun` không nhận tham số, nhưng không có nghĩa “chạy ngay lập tức và độc lập”. Khi source đang pending, nó đợi source thành công. Nếu source lỗi, callback **không chạy**, trừ khi bạn đã tạo một stage recovery bình thường trước nó.

Nếu cần xử lý **dù source thành công hay thất bại**, `thenRun` không phải lựa chọn đúng cho cleanup. Cân nhắc `whenComplete((value,error) -> ...)` để quan sát cả hai kết cục, hoặc tổ chức cleanup trong task thật sự bằng `try/finally`.

## 9. Non-Async và Async: callback chạy ở thread nào?

Mỗi phương thức có biến thể:

| Dùng theo stage trước | Async mặc định | Async với executor chỉ định |
|---|---|---|
| `thenApply(fn)` | `thenApplyAsync(fn)` | `thenApplyAsync(fn, executor)` |
| `thenAccept(action)` | `thenAcceptAsync(action)` | `thenAcceptAsync(action, executor)` |
| `thenRun(action)` | `thenRunAsync(action)` | `thenRunAsync(action, executor)` |

### Không có Async

Các callback **không được đảm bảo** chạy trên thread gọi phương thức đăng ký, cũng không luôn chạy trên thread thực hiện source. Theo chính sách của `CompletableFuture`, hành động phụ thuộc không-Async có thể được thực thi bởi thread hoàn tất current CompletableFuture hoặc bởi thread khác gọi completion method. Với source đã completed, callback có thể chạy đồng bộ ngay khi đăng ký; nếu có nhiều nhánh, không có lời hứa về thứ tự thực thi giữa chúng.

Không nên ghi code có giả định thread-local transaction/context sẽ tự động truyền qua các stage. Nếu cần context, truyền hoặc quản lý nó theo cơ chế tường minh.

### Async không truyền executor

Với `CompletableFuture` chuẩn, các phương thức async **không được truyền executor** thường dùng `ForkJoinPool.commonPool()` trong cấu hình thông thường. Tài liệu JDK cũng mô tả ngoại lệ khi common pool không hỗ trợ mức song song tối thiểu, implementation có thể tạo thread mới cho mỗi task; vì vậy không nên dùng một tên thread cố định như một hợp đồng.

### Async có executor

Truyền một `Executor` cụ thể giúp kiểm soát policy, concurrency, queue, rejection và lifecycle của callback. **Async không có nghĩa là tạo một thread riêng cho mỗi stage**; executor có quyền quyết định cách thực thi. Nếu executor đã shutdown hoặc từ chối task, dependent stage có thể hoàn tất bất thường; cần xử lý failure.

### Ví dụ Java 17: executor riêng để kiểm chứng tên thread

Lưu file **CompletableFutureAsyncDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletableFutureAsyncDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "lesson-worker"));

        try {
            CompletableFuture<Void> chain =
                    CompletableFuture.supplyAsync(
                            () -> "java", executor)
                    .thenApplyAsync(String::toUpperCase, executor)
                    .thenAcceptAsync(
                            value -> System.out.println(
                                    "accept=" + value + " on "
                                    + Thread.currentThread().getName()),
                            executor)
                    .thenRunAsync(
                            () -> System.out.println(
                                    "run on "
                                    + Thread.currentThread().getName()),
                            executor);

            chain.join();
            System.out.println("completed=" + chain.isDone());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac CompletableFutureAsyncDemo.java
java CompletableFutureAsyncDemo
~~~

Stdout:

~~~text
accept=JAVA on lesson-worker
run on lesson-worker
completed=true
~~~

Vì mỗi stage async trong chuỗi dùng đúng single-thread executor với tên thread đã chỉ định, ví dụ kiểm chứng được thread thực thi. Lời gọi `chain.join()` ở main chờ chuỗi hoàn tất; điều này **không biến callback thành synchronous API** mà chỉ đồng bộ ở boundary của chương trình mẫu.

**Không đóng executor quá sớm:** nếu shutdown trước khi các dependent stage đã được sắp lịch, một số stage có thể bị từ chối. Trong ví dụ, main đợi `chain.join()` xong mới shutdown. Trong ứng dụng thực, cần sở hữu executor rõ và quản lý cả trường hợp lỗi/cancellation trước khi đóng.

## 10. Khi source hoặc callback thất bại

Cả `thenApply`, `thenAccept` và `thenRun` đều chỉ thực thi callback khi source hoàn tất **bình thường**. Khi source hoàn tất **exceptionally**, callback không được chạy; dependent stage hoàn tất exceptionally và phản ánh lỗi. Nếu callback tự ném lỗi, **dependent stage** trở thành exceptional, còn source đã hoàn tất thành công không bị thay đổi hồi tố.

| Trường hợp | Callback trên source được chạy? | Kết quả dependent |
|---|---|---|
| Source thành công | Có | Kết quả `U` hoặc `Void` nếu callback thành công |
| Source thành công, callback ném exception | Có | Dependent exceptional |
| Source exceptional | Không | Dependent exceptional |
| Source bị cancel | Không | Dependent exceptional (có thể quan sát `CompletionException` chứa `CancellationException`) |
| Stage trước đã recovery thành công | Có | Chạy trên kết quả recovery bình thường |

**`join()` khác `get()`:** `join()` thường ném `CompletionException` (unchecked) khi stage lỗi; `get()` ném `ExecutionException` (checked) với nguyên nhân; khi Future bị cancel trực tiếp, `CancellationException` có thể được ném thay cho wrapper tùy stage và đường propagation. Cần kiểm tra `getCause()` thay vì coi mọi lỗi là timeout.

### Ví dụ Java 17: lỗi nguồn và lỗi callback

Lưu file **CompletableFutureErrorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureErrorDemo {
    public static void main(String[] args) {
        AtomicInteger callbacks = new AtomicInteger();

        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("source failed"));

        CompletableFuture<String> mapped = source.thenApply(value -> {
            callbacks.incrementAndGet();
            return "value=" + value;
        });

        CompletableFuture<Void> consumed = mapped.thenAccept(value ->
                callbacks.incrementAndGet());

        CompletableFuture<Void> finished = consumed.thenRun(
                callbacks::incrementAndGet);

        try {
            finished.join();
        } catch (CompletionException error) {
            System.out.println("source failure="
                    + error.getCause().getClass().getSimpleName());
        }

        System.out.println("callbacks=" + callbacks.get());
        System.out.println("source exceptional="
                + source.isCompletedExceptionally());

        CompletableFuture<Integer> successful =
                CompletableFuture.completedFuture(3);
        CompletableFuture<Integer> broken = successful.thenApply(value -> {
            throw new IllegalArgumentException("transform failed");
        });

        try {
            broken.join();
        } catch (CompletionException error) {
            System.out.println("callback failure="
                    + error.getCause().getClass().getSimpleName());
        }
        System.out.println("original exceptional="
                + successful.isCompletedExceptionally());
        System.out.println("derived exceptional="
                + broken.isCompletedExceptionally());
    }
}
~~~

Chạy:

~~~bash
javac CompletableFutureErrorDemo.java
java CompletableFutureErrorDemo
~~~

Stdout:

~~~text
source failure=IllegalStateException
callbacks=0
source exceptional=true
callback failure=IllegalArgumentException
original exceptional=false
derived exceptional=true
~~~

**Phân tích:** stage nguồn đầu tiên đã lỗi, nên cả ba callback đều bị bỏ qua: `callbacks=0`. Ở nhánh thứ hai, source thành công với 3, nhưng `thenApply` tự ném `IllegalArgumentException`; chỉ stage mới `broken` thất bại. Điều này cũng cho thấy **lỗi trong callback không được nuốt tự động**.

**Lưu ý về trạng thái:** `isDone() == true` gồm cả success/failure/cancel; không thể dùng riêng `isDone()` để kết luận pipeline thành công. `isCompletedExceptionally()` phản ánh trạng thái exceptional, còn `isCancelled()` phản ánh cancel trực tiếp ở Future tương ứng.

## 11. Các API xử lý lỗi liên quan

Ba phương thức chính **không thay thế** API recovery/observation:

| API | Dùng khi nào | Kết quả cơ bản |
|---|---|---|
| `exceptionally(fn)` | Muốn cung cấp giá trị dự phòng khi stage lỗi | Có thể đưa pipeline về normal completion nếu fallback thành công |
| `handle((value, error) -> result)` | Muốn tính một giá trị mới cho **cả** success và failure | Dependent có thể hoàn tất bình thường với giá trị xử lý, hoặc lỗi nếu handler lỗi |
| `whenComplete((value, error) -> ...)` | Muốn quan sát kết quả/lỗi như log hoặc metric | Bảo toàn kết quả/lỗi gốc khi observer không ném lỗi |
| `thenCompose(fn)` | Callback trả một CompletionStage khác | Flatten kết quả async thay vì nested future |

Ví dụ nối recovery trước khi dùng thenApply:

~~~java
CompletableFuture<Integer> recovered =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("bad"))
                .exceptionally(error -> 0);
CompletableFuture<String> text = recovered.thenApply(
        value -> "count=" + value);
System.out.println(text.join()); // count=0
~~~

Đây là **đoạn minh họa** trong ngữ cảnh class đã import CompletableFuture. `exceptionally` phục hồi thành giá trị 0, nên `thenApply` chạy. Nhưng chỉ dùng fallback nếu nghiệp vụ cho phép; trả 0 cho lỗi dữ liệu nghiêm trọng có thể khiến hệ thống công bố kết quả sai.

**`whenComplete` có thể chạy cả khi lỗi**; `thenRun` chỉ chạy nếu trước đó thành công. Không đặt cleanup bắt buộc khi lỗi vào `thenRun` rồi nghĩ mọi trường hợp sẽ được dọn dẹp. Với tài nguyên mở/đóng bên trong một tác vụ, sử dụng `try/finally` hoặc `try-with-resources` theo ownership là cách bảo đảm quan trọng.

## 12. Nối chuỗi tuần tự và tạo nhánh song song khác nhau

Ví dụ:

~~~text
Chuỗi:
source -> thenApply -> thenAccept -> thenRun
Bước sau chỉ chạy khi stage ngay trước hoàn tất bình thường.

Các nhánh:
                 +-> thenApply
source ----------+-> thenAccept
                 +-> thenRun
Mỗi nhánh phụ thuộc vào source, không phụ thuộc vào nhánh kia.
~~~

**Trong chuỗi**, nếu `thenAccept` lỗi, `thenRun` sau nó không chạy. Nếu nguồn thành công nhưng callback `thenApply` lỗi, những bước phụ thuộc tiếp theo cũng nhận exceptional completion.

**Ở dạng nhánh**, một nhánh thất bại không tự biến source thành thất bại, và không nhất thiết làm nhánh khác thất bại. Muốn một quyết định tổng hợp, dùng `allOf`, `anyOf`, `thenCombine` hoặc một coordinator/chiến lược cancellation phù hợp với yêu cầu nghiệp vụ.

### Không nhầm thenRun với runAsync

`thenRun(runnable)` là bước **phụ thuộc vào thành công** của một stage đã có. `CompletableFuture.runAsync(runnable)` là cách **khởi tạo một tác vụ async mới** mà không cần stage nguồn. Tương tự, `supplyAsync(supplier)` tạo một tác vụ async trả giá trị.

`runAsync` không tương đương với `thenRunAsync`: phương thức thứ hai chỉ được sắp lịch khi stage trước hoàn tất bình thường.

## 13. Blocking, I/O và việc chọn executor

Các stage của CompletableFuture không tự động bảo đảm non-blocking toàn pipeline. Một lambda có thể gọi database, ngủ, chờ khóa, dùng `join()`, `get()` hoặc I/O blocking; hành động đó **vẫn chiếm thread thực thi callback**.

Hướng dẫn thiết kế:

1. Với biến đổi **CPU-bound ngắn**, `thenApply` hoặc `thenApplyAsync` trên executor CPU có thể phù hợp tùy nguồn và latency.
2. Với callback có **blocking I/O**, cân nhắc executor phù hợp I/O hoặc API bất đồng bộ thật sự; tránh dùng common pool cho blocking dài không kiểm soát.
3. Với downstream có giới hạn kết nối, thêm **bounded concurrency** (ví dụ Semaphore) và timeout, không tạo Future không giới hạn chỉ vì API dễ nối.
4. Với executor riêng, định nghĩa **queue capacity, rejection policy, lifecycle**; `thenApplyAsync` chỉ định executor không tự tạo backpressure đầu vào.
5. Đừng đặt `join()` ngay trong callback chờ một tác vụ cần chính executor single-thread đang bị bạn chiếm: dễ deadlock khi có phụ thuộc vòng.
6. Khi cần chờ ở boundary đồng bộ, dùng `get(timeout, unit)` hoặc chiến lược timeout phù hợp để tránh chờ vô hạn.

**Thao tác `thenApply` không nhất thiết là thao tác chạy song song.** Nếu mong muốn giảm latency, đo số stage, chi phí callback, thời gian chờ executor và tổng thời gian request; tạo nhiều stage hơn có thể tăng overhead mà không tăng throughput.

## 14. Tính đúng đắn của side effect và shared state

Trong `thenAccept` và `thenRun`, code thường thực hiện side effect, nên cần chú ý:

- **Ghi vào biến chung:** nếu nhiều callback chạy đồng thời, sử dụng dữ liệu bất biến, thread confinement, Atomic types hoặc đồng bộ phù hợp. CompletableFuture không làm cho `ArrayList`, `HashMap` hoặc `counter++` tự động an toàn.
- **Idempotency:** callback thành công không đồng nghĩa side effect có thể lặp lại tùy ý khi caller retry cả pipeline. Với ghi dữ liệu, gửi message hoặc thanh toán, cần key idempotency và xử lý kết quả theo nghiệp vụ.
- **Error handling:** nếu side effect thất bại, stage `thenAccept` exceptional; nhưng thao tác bên ngoài có thể đã thực hiện một phần. Không tự động rollback database/file/HTTP.
- **Không đảm bảo thứ tự nhánh:** nhiều callback cùng đăng ký trên source không có thứ tự chạy toàn cục cố định. Nếu bước B **phải** sau A, hãy nối chuỗi thay vì gắn hai nhánh rồi đoán thứ tự.
- **Memory visibility:** các cơ chế completion cung cấp quan hệ đồng bộ cho việc tiêu thụ kết quả đã hoàn tất; nhưng không xóa data race khi callback đồng thời sửa state khác mà không phối hợp.

Với dữ liệu qua nhiều stage, nếu có thể hãy dùng **transformations trả giá trị mới** thay vì nhiều tác động lên shared mutable object. Chọn `thenAccept` cho sink thực sự, và xử lý lỗi sink rõ ràng.

## 15. Cancellation, timeout và shutdown

`CompletableFuture.cancel(...)` hoàn tất Future bằng trạng thái canceled, **không đảm bảo interrupt task đang chạy**: đối với CompletableFuture, tham số `mayInterruptIfRunning` không dùng để điều khiển interruption của tác vụ như FutureTask. Các dependent stage quan sát cancellation ở source như một exceptional completion và callback thành công `thenApply/thenAccept/thenRun` không chạy.

Điểm cần phân biệt:

- **Cancel source:** source ở trạng thái canceled; các dependent chưa hoàn tất có thể hoàn tất exceptional, nhưng không tự “kill” mọi thao tác khác hoặc undo side effect.
- **Cancel dependent:** không mặc nhiên cancel source hay mọi sibling.
- **`orTimeout(timeout, unit)`**: có thể hoàn tất Future bằng `TimeoutException` nếu chưa xong; không tự bảo đảm công việc nền dừng.
- **`completeOnTimeout(value, timeout, unit)`**: hoàn tất bằng fallback theo timeout, nhưng không tự hủy downstream đang chạy.
- **Shutdown executor:** nên xảy ra khi owner không còn cần gửi dependent stage; executor đã shutdown có thể từ chối các callback async tiếp theo.

**Không coi cancellation/timeout là cơ chế kiểm soát tải duy nhất.** Khi upstream vẫn gửi liên tục, một loạt công việc đã timeout có thể tiếp tục chiếm CPU/I/O nếu task nền không hợp tác dừng. Cần deadline ở từng dependency, bounded concurrency và admission policy phù hợp.

## 16. Bẫy về kiểu, exception và tổ chức code

| Sai lầm | Hệ quả | Cách đúng |
|---|---|---|
| Mong `thenAccept` trả giá trị `U` | Sai kiểu; callback là Consumer | Dùng `thenApply` |
| Mong `thenRun` nhận giá trị nguồn | Runnable không có tham số | Dùng `thenAccept` hoặc `thenApply` |
| Sau `thenAccept` lại biến đổi như còn `T` | Stage mới có kiểu `Void` | Giữ một stage `T` riêng hoặc dùng thenApply trả giá trị |
| Dùng `thenApply` với hàm trả Future và mong flatten | Thành `CompletableFuture<CompletableFuture<U>>` | Dùng `thenCompose` |
| Tin callback không-Async luôn chạy trên main | Phụ thuộc thread hoàn tất source và lịch runtime | Không phụ thuộc tên thread; dùng Async + executor khi cần |
| Tin Async tạo thread mới cho mỗi callback | Executor có thể tái sử dụng worker | Chọn executor rõ ràng |
| Dùng `thenRun` làm cleanup cho cả success/failure | Không chạy khi source exceptional | Dùng `whenComplete`/try-finally phù hợp |
| Gọi `join()` giữa mọi stage | Dễ block và mất cấu trúc bất đồng bộ | Nối stages, chờ ở boundary |
| Bỏ qua Future trả về từ `thenAccept` | Lỗi sink có thể không ai quan sát | Giữ và await/handle returned Future |
| Không xử lý RejectedExecutionException | Stage async có thể exceptional | Quản lý executor capacity/lifecycle |
| Gắn nhánh lên source rồi giả định thứ tự | Các callback độc lập có thể đổi thứ tự | Nối chuỗi khi có dependency |
| Coi timeout là task nền đã dừng | Có thể vẫn chạy và gây side effect | Dùng cancellation hợp tác, timeout I/O |
| Gọi `isDone()` và coi là success | Done bao gồm failure/cancel | Kiểm tra result/exception |

## 17. Checklist trước khi dùng ba phương thức

Hãy xác định:

1. Bước mới **cần giá trị nguồn** hay chỉ cần thông báo đã hoàn tất?
2. Có cần phát ra **kiểu kết quả mới** cho stage tiếp theo không?
3. Callback có thể thất bại không, và ai **xử lý dependent Future trả về**?
4. Tác vụ có blocking I/O hoặc tính toán dài không? Chọn executor nào?
5. Các bước là **chuỗi có thứ tự** hay **nhánh độc lập**?
6. Nếu source hoặc callback exceptional, luồng recovery dùng `exceptionally`, `handle` hay `whenComplete`?
7. Khi task bị cancel/timeout, downstream và side effect được dừng/xử lý ra sao?
8. Có chia sẻ mutable state giữa các callback không?
9. Có nguy cơ chờ vòng/deadlock nếu một callback `join()` task khác trên cùng executor?
10. Đã kiểm thử success, failure, timeout và shutdown chưa?

**Kết luận:** `thenApply()` **nhận T và trả U**; `thenAccept()` **nhận T nhưng không trả giá trị nghiệp vụ**; `thenRun()` **không nhận T và không trả giá trị nghiệp vụ**. Chúng tạo dependent Future mới và chỉ chạy callback trên đường hoàn tất bình thường. Chọn biến thể `Async`/executor khi cần kiểm soát thread, quản lý lỗi ở stage trả về và tránh hiểu nhầm side effect với biến đổi kết quả.

## 18. Tài liệu tham khảo Java SE

- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 – CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
