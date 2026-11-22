# thenAcceptBoth() và runAfterBoth(): phối hợp hai nhánh không cần giá trị trả về

Trong Java Concurrency, `CompletableFuture` và `CompletionStage` không chỉ giúp nhận một kết quả bất đồng bộ: chúng còn cho phép mô tả **quan hệ phụ thuộc giữa nhiều công việc**. Khi hai nhánh có thể chạy độc lập nhưng bước tiếp theo chỉ được phép thực hiện **sau khi cả hai thành công**, hai phương thức đặc biệt hữu ích là:

- **`thenAcceptBoth(other, action)`**: đợi **cả hai stage hoàn tất bình thường**, rồi gọi một `BiConsumer` **nhận kết quả của cả hai**, thực hiện một hành động và **không trả về giá trị nghiệp vụ**.
- **`runAfterBoth(other, action)`**: cũng đợi **cả hai stage hoàn tất bình thường**, nhưng gọi một `Runnable` **không nhận kết quả của hai stage**, thực hiện hành động rồi **không trả về giá trị nghiệp vụ**.

Cả hai tạo ra **dependent stage kiểu `CompletionStage<Void>`**; khi gọi trên `CompletableFuture`, kiểu trả về cụ thể thường là **`CompletableFuture<Void>`**. `Void` không có nghĩa “fire-and-forget”: stage mới vẫn mang **trạng thái hoàn tất, lỗi, hủy**, và có thể được theo dõi, kết hợp hay chờ có chủ đích.

**Tư tưởng chính:** dùng `thenAcceptBoth` khi hành động cần **hai giá trị đầu vào**, và `runAfterBoth` khi chỉ cần **hai bên hoàn tất thành công trước khi chạy**. Hai phương thức không tự khởi chạy hai task nguồn, không tự biến code thành song song và không tự xử lý lỗi hay cancellation của toàn pipeline.

Bài áp dụng cho **Java 17+ thuộc Java concurrency nói chung**, với ví dụ độc lập chạy bằng `javac`/`java`, không phụ thuộc framework bên ngoài.

## 1. Tại sao cần phối hợp hai nhánh?

Một yêu cầu có thể cần hai tác vụ độc lập:

```text
                       Bắt đầu request
                             |
                   +---------+----------+
                   |                    |
             Nhánh A                  Nhánh B
          đọc cấu hình             xác minh dữ liệu
                   |                    |
                   v                    v
              A hoàn tất           B hoàn tất
                   \                    /
                    \                  /
                   Cả hai thành công?
                             |
                             v
                      Hành động cuối
                     thông báo / ghi log
                             |
                             v
                    CompletionStage<Void>
```

Nếu chỉ dùng `Future.get()`, một thread có thể phải chờ A rồi chờ B, sau đó mới thực hiện hành động:

```java
A a = futureA.get();
B b = futureB.get();
notify(a, b);
```

Đây là **pseudocode theo cú pháp Java**, các kiểu `A`, `B` và method `notify` chưa được định nghĩa. Hai lời `get()` có thể block **thread đang orchestration** nếu kết quả chưa sẵn sàng.

Với CompletionStage, ta có thể mô tả **sẵn** phụ thuộc:

```java
CompletionStage<Void> notification =
        stageA.thenAcceptBoth(stageB, (a, b) -> notify(a, b));
```

Đây là trích đoạn: `stageA`, `stageB` là hai `CompletionStage` có kiểu phù hợp; `notify` là hành động ứng dụng tự định nghĩa. Lời gọi `thenAcceptBoth` đăng ký một dependent stage; không bắt caller phải đứng đợi hai stage tại thời điểm đăng ký.

Nếu việc thông báo cần chạy ở một executor khác, dùng overload `thenAcceptBothAsync` với `Executor` được chọn chủ động, thay vì block thread đầu vào để đợi.

## 2. Cần phân biệt “không trả kết quả” với “không có completion”

Với `thenAcceptBoth` và `runAfterBoth`, callback là **hành động trả `void`**, nhưng method vẫn **trả một stage mới** để theo dõi hành động đó:

```java
CompletableFuture<Void> afterBoth =
        first.thenAcceptBoth(second, (a, b) -> {
            System.out.println(a + " / " + b);
        });

// Ở một ranh giới cho phép chờ:
afterBoth.join();
```

Đây là trích đoạn; `first` và `second` là `CompletableFuture` đã định nghĩa. `join()` thành công trả `null` cho kiểu `Void`, nhưng điều hữu ích nhất là **sau join, hành động của dependent stage đã hoàn tất theo hợp đồng của nó**.

`CompletableFuture<Void>` có thể:

1. Hoàn tất **thành công**: callback đã chạy xong, kết quả `Void` thông thường là `null`.
2. Hoàn tất **ngoại lệ**: một input thất bại/canceled hoặc callback ném lỗi; `join()` có thể ném `CompletionException` hay `CancellationException` theo outcome.
3. Chưa hoàn tất: chưa đủ điều kiện kích hoạt hoặc callback đang chạy/chưa được scheduler thực hiện.
4. Bị hủy trực tiếp: trạng thái stage chuyển thành canceled nếu `cancel` thắng cuộc đua terminal completion; điều này **không tự đảm bảo dừng callback đã chạy**.

**Không bỏ handle** chỉ vì callback trả `void` nếu hành động như ghi log bắt buộc, gửi thông báo hay cập nhật audit phải được xác nhận và theo dõi lỗi.

## 3. Chữ ký API của thenAcceptBoth() và runAfterBoth()

Hai chữ ký quan trọng của `CompletionStage<T>` (viết rút gọn tên generic để dễ nhìn):

```java
<U> CompletionStage<Void> thenAcceptBoth(
        CompletionStage<? extends U> other,
        BiConsumer<? super T, ? super U> action);

CompletionStage<Void> runAfterBoth(
        CompletionStage<?> other,
        Runnable action);
```

Đây là **chữ ký API minh họa**, không phải code class hoàn chỉnh. `thenAcceptBoth` nhận `BiConsumer<T,U>`: callback có **hai tham số** nhưng trả `void`. `runAfterBoth` nhận `Runnable`: callback **không có tham số** và trả `void`.

Khi gọi trên `CompletableFuture<T>`, các override của nó trả `CompletableFuture<Void>`. Có các biến thể:

```java
first.thenAcceptBoth(second, (a, b) -> use(a, b));
first.thenAcceptBothAsync(second, (a, b) -> use(a, b));
first.thenAcceptBothAsync(
        second, (a, b) -> use(a, b), executor);

first.runAfterBoth(second, () -> signalReady());
first.runAfterBothAsync(second, () -> signalReady());
first.runAfterBothAsync(
        second, () -> signalReady(), executor);
```

Các dòng trên là **trích đoạn**; cần định nghĩa hai stage, `executor`, `use` và `signalReady`. `*Async` không tạo thread mới riêng cho từng callback; nó yêu cầu dùng asynchronous execution facility của implementation hoặc `Executor` được chỉ định.

### Bảng so sánh nhanh

| Tiêu chí | `thenAcceptBoth` | `runAfterBoth` |
|---|---|---|
| Điều kiện gọi action | **Cả hai stage hoàn tất bình thường**. | **Cả hai stage hoàn tất bình thường**. |
| Callback | `BiConsumer<T,U>`. | `Runnable`. |
| Nhận giá trị hai stage? | **Có**, hai tham số typed. | **Không**. |
| Kết quả của dependent stage | `Void`. | `Void`. |
| Dùng khi | Cần hai kết quả để gửi thông báo/ghi thông tin/tạo side effect. | Chỉ cần “cả hai xong” trước cleanup/đánh dấu/trigger hành động. |
| Nếu một source exceptional | Action bình thường **không chạy**; dependent stage exceptional. | Tương tự. |
| Nếu callback ném exception | Dependent stage exceptional. | Tương tự. |
| Có tự chạy đồng thời hai source? | **Không**. | **Không**. |
| Có tự chờ caller bằng blocking? | **Không** tại lúc đăng ký. | **Không** tại lúc đăng ký. |
| Có overload Async và Executor? | **Có**. | **Có**. |

## 4. Ví dụ 1 — Hai nhánh thành công, một action dùng kết quả và một action chỉ đợi

Ví dụ dùng hai `completedFuture` để không phụ thuộc vào lịch chạy. `thenAcceptBoth` nhận cả `7` và `5` để tạo một chuỗi; `runAfterBoth` chỉ ghi nhận rằng cả hai đã hoàn tất. Main đợi **hai dependent stages** trước khi in.

Tạo file **`BothBasicsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BothBasicsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> left =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> right =
                CompletableFuture.completedFuture(5);

        AtomicReference<String> description =
                new AtomicReference<>();
        AtomicBoolean barrierRan = new AtomicBoolean();

        CompletableFuture<Void> acceptsBoth =
                left.thenAcceptBoth(right, (a, b) -> {
                    description.set(a + " + " + b + " = " + (a + b));
                });

        CompletableFuture<Void> runsAfterBoth =
                left.runAfterBoth(right, () -> barrierRan.set(true));

        CompletableFuture.allOf(acceptsBoth, runsAfterBoth).join();

        System.out.println("thenAcceptBoth: " + description.get());
        System.out.println("runAfterBoth ran: " + barrierRan.get());
        System.out.println("Void result: " + acceptsBoth.join());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac BothBasicsDemo.java
java BothBasicsDemo
```

Đầu ra:

```text
thenAcceptBoth: 7 + 5 = 12
runAfterBoth ran: true
Void result: null
```

**Phân tích:**

- `left` và `right` đã hoàn tất bình thường, nên hai action đủ điều kiện chạy.
- `thenAcceptBoth` dùng hai tham số để xây chuỗi kết quả. `runAfterBoth` không hề nhìn giá trị 7 và 5; nó chỉ chờ hai stage thành công để đánh dấu.
- `CompletableFuture.allOf(...).join()` là **barrier** chờ cả hai dependent actions hoàn tất trước khi main đọc hai atomic variables.
- `acceptsBoth.join()` trả `null` vì kiểu `Void`, **không** có nghĩa action chưa chạy.
- **Không bảo đảm thứ tự thực hiện** giữa hai action: chúng độc lập, cùng phụ thuộc vào `left` và `right`. Chương trình chỉ in ở main sau barrier, nên stdout xác định.

Đây là ví dụ semantics, **không chứng minh song song** vì các source đã completed. Khi source được tạo bởi các tác vụ bất đồng bộ thật, phụ thuộc và kết quả của API vẫn tương tự.

## 5. Điều kiện “both” là hai stage bình thường, không phải “một trong hai”

Sự khác biệt dễ bỏ sót:

```text
A = completed normally, B = still incomplete
                 |
                 v
thenAcceptBoth / runAfterBoth action CHƯA chạy
                 |
        B completed normally
                 |
                 v
        action được phép chạy
                 |
                 v
       dependent stage completes
```

Nếu một trong hai source hoàn tất **ngoại lệ**, action của `thenAcceptBoth`/`runAfterBoth` **không được thực hiện như đường thành công**. Dependent stage sẽ có exceptional outcome theo contract. Không mặc định nếu A thất bại thì B bị cancel hay ngừng chạy: các input là các stage riêng.

Không nên diễn đạt “chờ A và B trả giá trị” một cách quá máy móc: một source có thể là `CompletableFuture<Void>` hoàn tất bình thường với `null`; `runAfterBoth` vẫn có thể dùng để chờ, còn `thenAcceptBoth` có thể nhận tham số null đó nếu loại stage cho phép.

`thenAcceptBoth` **không** chọn “kết quả nhanh nhất”, và `runAfterBoth` **không** tương đương `runAfterEither`. Nếu chỉ cần **một** stage hoàn tất bình thường để hành động, nghiên cứu `acceptEither`/`runAfterEither` với exception semantics riêng; đừng thay API chỉ vì tên gần giống.

## 6. Ví dụ 2 — Chứng minh chỉ một nhánh xong thì dependent chưa xong

Ta tạo hai `CompletableFuture` chưa hoàn tất và tự gọi `complete` theo trình tự xác định. Không cần `Thread.sleep()` hay dự đoán scheduler.

Tạo file **`BothCompletionGateDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BothCompletionGateDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();

        AtomicReference<String> captured = new AtomicReference<>();
        AtomicBoolean signalled = new AtomicBoolean();

        CompletableFuture<Void> accept = first.thenAcceptBoth(
                second, (a, b) -> captured.set(a + "+" + b));

        CompletableFuture<Void> run =
                first.runAfterBoth(second, () -> signalled.set(true));

        first.complete("A");

        System.out.println("Accept done after A: " + accept.isDone());
        System.out.println("Run done after A: " + run.isDone());

        second.complete("B");
        CompletableFuture.allOf(accept, run).join();

        System.out.println("Accept done after B: " + accept.isDone());
        System.out.println("Run done after B: " + run.isDone());
        System.out.println("Captured: " + captured.get());
        System.out.println("Signalled: " + signalled.get());
    }
}
```

```bash
javac BothCompletionGateDemo.java
java BothCompletionGateDemo
```

Kết quả:

```text
Accept done after A: false
Run done after A: false
Accept done after B: true
Run done after B: true
Captured: A+B
Signalled: true
```

**Vì sao?** Khi chỉ `first` được complete, `second` chưa có outcome nên hai dependent stage vẫn incomplete. Khi `second.complete("B")` thành công, điều kiện both được đáp ứng. Hai callback không nhất thiết chạy theo thứ tự `accept` trước `run`, nhưng `allOf(...).join()` xác nhận cả hai đã hoàn tất trước khi in các biến.

### Callback chạy đúng lúc nào?

Với `thenAcceptBoth`/`runAfterBoth` **không hậu tố Async**, action có thể chạy trên thread thực hiện completion của source thứ hai hoặc một thread tham gia completion khác, thậm chí ngay trong lời đăng ký nếu hai input đã completed. **Không có cam kết nó luôn chạy trên main hay một worker riêng**.

Do đó, nếu action nặng/đang làm I/O blocking, đừng tùy tiện chạy nó ở biến thể non-Async: nó có thể giữ thread hoàn tất source và kéo dài latency của pipeline. Hãy lựa chọn overload Async với executor phù hợp.

## 7. thenAcceptBoth() có thể bỏ qua kết quả trả về nhưng không bỏ qua giá trị đầu vào

Một `BiConsumer<T,U>` vẫn nhận hai kết quả **typed**:

```java
CompletableFuture<User> user = loadUser();
CompletableFuture<Settings> settings = loadSettings();

CompletableFuture<Void> recorded =
        user.thenAcceptBoth(settings, (u, s) -> {
            audit(u.id(), s.version());
        });
```

Đây là **trích đoạn**, chưa có class `User`, `Settings`, `loadUser`, `loadSettings`, `audit`; không phải chương trình độc lập. Nó minh họa: không có giá trị mới được trả từ action, nhưng hai giá trị source vẫn được truyền vào.

Không nên dùng:

```java
user.runAfterBoth(settings, () -> {
    audit(user.join().id(), settings.join().version());
});
```

khi hành động cần cả hai giá trị: tuy các source đã completed khi action chạy bình thường, việc phải `join()` bên trong để lôi giá trị ra làm code rườm rà, khó diễn đạt kiểu và lỗi hơn. `thenAcceptBoth` đã được thiết kế đúng cho việc nhận hai input.

**Lưu ý capture mutable state:** Hai source có thể chạy ở thread khác nhau. Nếu một action giữ reference tới object mutable và thread khác tiếp tục sửa nó đồng thời, việc stage đã completed không tự làm object đó thread-safe cho mọi mutation mới. Ưu tiên `record`, immutable snapshot hoặc synchronization/ownership rõ ràng.

## 8. runAfterBoth() là một completion barrier có hành động, không nhận giá trị

Hình thức hữu ích:

```java
CompletableFuture<Void> waitBoth =
        saveA.runAfterBoth(saveB, () -> {
            System.out.println("Both saves completed");
        });
```

Đây là trích đoạn, giả định `saveA` và `saveB` là các stage có thể completed bình thường. Callback không cần biết giá trị chúng trả về, nên `Runnable` là đủ.

Các tình huống thường dùng:

1. **Đánh dấu hai bước đã chuẩn bị xong** rồi giải phóng một tín hiệu chờ.
2. **Bắt đầu công việc cuối** không cần giá trị của hai source, ví dụ cập nhật một flag “ready” khi cả hai quá trình thành công.
3. **Phối hợp cleanup có thứ tự** khi hai thao tác hoàn tất bình thường và một bước tiếp theo cần chạy; phải định nghĩa riêng đường xử lý nếu một source lỗi hoặc hủy.
4. **Tạo một điểm kết thúc có thể quan sát**: dependent `CompletableFuture<Void>` được `join/get` hoặc ghép với stage khác.

**Đừng dùng `runAfterBoth` như finally.** Nếu một input failed/canceled, callback thông thường **không chạy**. Cleanup phải chạy bất kể success/failure có thể cần `handle`, `whenComplete`, `allOf` cùng xử lý lỗi, hoặc `try/finally` ngay trong task sở hữu tài nguyên.

## 9. So sánh thenAcceptBoth / runAfterBoth với các combinator khác

| Method | Dependency | Input callback | Output |
|---|---|---|---|
| `thenApply(fn)` | Một stage thành công. | Một giá trị `T`. | Stage có kết quả `U`. |
| `thenAccept(action)` | Một stage thành công. | Một giá trị `T`. | `CompletionStage<Void>`. |
| `thenRun(action)` | Một stage thành công. | Không có giá trị. | `CompletionStage<Void>`. |
| `thenCombine(other, fn)` | **Hai stage thành công.** | Hai giá trị `T,U`. | Stage có kết quả `V`. |
| **`thenAcceptBoth(other, action)`** | **Hai stage thành công.** | Hai giá trị `T,U`. | **`CompletionStage<Void>`**. |
| **`runAfterBoth(other, action)`** | **Hai stage thành công.** | Không có giá trị. | **`CompletionStage<Void>`**. |
| `acceptEither(other, action)` | Theo semantics của một trong hai stage hoàn tất bình thường. | Một kết quả của stage được chọn. | `CompletionStage<Void>`. |
| `runAfterEither(other, action)` | Theo semantics của một trong hai stage hoàn tất bình thường. | Không có giá trị. | `CompletionStage<Void>`. |
| `CompletableFuture.allOf(...)` | Tập nhiều `CompletableFuture`. | Không có callback tích hợp ở lời allOf. | `CompletableFuture<Void>` barrier. |

`thenCombine` là lựa chọn tự nhiên nếu **cần trả một giá trị tổng hợp** cho stage tiếp theo. `thenAcceptBoth` phù hợp nếu mục đích chính là **tiêu thụ hai giá trị** qua hành động. `runAfterBoth` phù hợp nếu hành động chỉ yêu cầu completion, không cần đọc hai input.

`CompletableFuture.allOf(a,b)` giúp tạo barrier cho nhiều Future (không chỉ hai), nhưng **không tự truyền hai kết quả vào một `BiConsumer`** như `thenAcceptBoth`. Nếu mỗi thao tác đã là `CompletableFuture<Void>`, `allOf` cũng hữu ích để chờ hàng loạt. Cần cân nhắc exception propagation và cancellation, không coi allOf là structured cancellation.

## 10. Async variants: ai thực thi callback?

Có ba cách:

```java
left.thenAcceptBoth(right, action);
left.thenAcceptBothAsync(right, action);
left.thenAcceptBothAsync(right, action, executor);
```

Và tương ứng:

```java
left.runAfterBoth(right, runnable);
left.runAfterBothAsync(right, runnable);
left.runAfterBothAsync(right, runnable, executor);
```

Đây là trích đoạn; cần các biến có kiểu phù hợp. Tính **đúng điều kiện both** giữ nguyên giữa ba loại overload, khác ở **chính sách thực thi action**:

- **Không Async:** action có thể chạy trên thread hoàn tất source hoặc thread thực hiện lời gắn dependent khi cả hai đã xong. Không bảo đảm thread cố định; không nhất thiết tạo một task mới trong executor.
- **Async không chỉ định Executor:** action được thực hiện bằng default asynchronous execution facility của implementation. Với `CompletableFuture` chuẩn, đó thường là `ForkJoinPool.commonPool()` (có chính sách fallback tùy cấu hình/parallelism).
- **Async có Executor:** action được gửi đến **executor chỉ định**, giúp kiểm soát resource, isolation và cách shutdown; code vẫn phải xử lý rejection và exception.

Hậu tố `Async` không tự bảo đảm hai source chạy song song; hai source phải được khởi động/hoàn tất theo cách riêng. Nó cũng không biến một callback **blocking I/O** thành non-blocking: nếu callback gọi network chặn, worker của executor được dùng cho action vẫn bị giữ lại.

### Tránh deadlock khi dùng pool nhỏ

Giả sử `thenAcceptBothAsync(..., singleThreadExecutor)` được xếp vào cùng executor một worker mà worker hiện tại đang gọi `actionStage.join()`. Nếu dependent action chỉ có thể chạy trên worker đó, việc block có thể dẫn tới **thread starvation/deadlock**. Cách tốt hơn là **trả về dependent stage**, chain tiếp qua `thenRun`/`thenCompose`, rồi chỉ `join/get` ở biên ngoài pool khi được phép chờ.

Đừng suy rằng hai stage có hai callback nên JVM sẽ tạo hai thread riêng; execution facility và scheduling quyết định.

## 11. Ví dụ 3 — Hai nhánh async chạy trên executor riêng

Chương trình này dùng `ExecutorService` do main sở hữu, cho hai source `supplyAsync` độc lập, rồi gắn **hai dependent actions Async** vào cùng executor. Để không phụ thuộc số thứ tự worker, callback chỉ lưu một boolean “tên thread có tiền tố `both-worker-`”. Main chỉ in sau khi cả hai action completed.

Tạo file **`BothAsyncExecutorDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class BothAsyncExecutorDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger nextWorker = new AtomicInteger();

        ExecutorService executor = Executors.newFixedThreadPool(
                2, runnable -> {
                    Thread thread = new Thread(
                            runnable,
                            "both-worker-" + nextWorker.incrementAndGet()
                    );
                    return thread;
                }
        );

        AtomicInteger sum = new AtomicInteger();
        AtomicBoolean acceptOnPool = new AtomicBoolean();
        AtomicBoolean runOnPool = new AtomicBoolean();

        try {
            CompletableFuture<Integer> first =
                    CompletableFuture.supplyAsync(() -> 4, executor);
            CompletableFuture<Integer> second =
                    CompletableFuture.supplyAsync(() -> 6, executor);

            CompletableFuture<Void> accept =
                    first.thenAcceptBothAsync(second, (a, b) -> {
                        sum.set(a + b);
                        acceptOnPool.set(
                                Thread.currentThread().getName()
                                        .startsWith("both-worker-")
                        );
                    }, executor);

            CompletableFuture<Void> run =
                    first.runAfterBothAsync(second, () -> {
                        runOnPool.set(
                                Thread.currentThread().getName()
                                        .startsWith("both-worker-")
                        );
                    }, executor);

            CompletableFuture.allOf(accept, run).join();
            System.out.println("Combined: " + sum.get());
            System.out.println("Accept on executor: "
                    + acceptOnPool.get());
            System.out.println("Run on executor: " + runOnPool.get());
        } finally {
            executor.shutdown();
        }

        System.out.println("Executor terminated: "
                + executor.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

```bash
javac BothAsyncExecutorDemo.java
java BothAsyncExecutorDemo
```

Đầu ra khi executor hoạt động bình thường:

```text
Combined: 10
Accept on executor: true
Run on executor: true
Executor terminated: true
```

**Phân tích:**

1. `supplyAsync` của hai nguồn nộp hai phép tính độc lập; pool có hai worker để chúng có thể chạy cạnh nhau, nhưng không cam kết lúc nào thật sự song song.
2. `thenAcceptBothAsync` chỉ được đưa vào thực thi khi hai kết quả đều có, và nhận `a=4, b=6`.
3. `runAfterBothAsync` chỉ cần biết cả hai source hoàn tất bình thường, **không được truyền 4 hay 6**.
4. Cả hai callback được yêu cầu thực thi trên executor chỉ định, nên tên thread của chúng có prefix do thread factory đặt. Chương trình in **boolean**, không in `both-worker-1` hay `both-worker-2`, vì phân phối cụ thể không cố định.
5. `allOf(accept,run).join()` là mốc cả hai action kết thúc; main đóng executor sau khi đã quan sát completion. `awaitTermination()` kiểm tra vòng đời executor.

**Phạm vi bài học:** đây là minh họa lựa chọn executor cho callback, không phải benchmark rằng `*Async` luôn nhanh hơn. Với action rất nhẹ, overhead submit/scheduling có thể lớn hơn tính toán; với action I/O blocking, cần xem xét pool thích hợp và timeout.

## 12. Nếu một trong hai source thất bại thì sao?

`thenAcceptBoth` và `runAfterBoth` là **success-dependent combinators**. Nếu một source hoàn tất ngoại lệ, callback bình thường **không được chạy**, dependent stage cũng trở thành exceptional theo completion rules. Không có cơ chế tự động:

- Khởi chạy callback với `null` cho source lỗi.
- Thử lại source đã thất bại.
- Hủy source còn lại.
- Rollback side effect mà một source đã tạo.
- Chọn một exception “ưu tiên” có thứ tự ổn định khi **cả hai** cùng thất bại.

Một stage thất bại có thể do supplier/callback ném exception, `completeExceptionally`, timeout qua `orTimeout`, hoặc cancellation. Khi inspect `CompletionException` trong `join()`, lấy `getCause()` để biết nguyên nhân phù hợp. Nếu có cả hai lỗi, không dựa vào thứ tự scheduler để đoán exception nào được chọn làm outcome của dependent stage.

### Ví dụ 4 — Lỗi chặn action; phục hồi source rồi phối hợp lại

Tạo file **`BothFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class BothFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> good =
                CompletableFuture.completedFuture(3);
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("missing value")
                );

        AtomicBoolean acceptCalled = new AtomicBoolean();
        AtomicBoolean runCalled = new AtomicBoolean();

        CompletableFuture<Void> accept = good.thenAcceptBoth(
                failed, (a, b) -> acceptCalled.set(true));

        CompletableFuture<Void> run = good.runAfterBoth(
                failed, () -> runCalled.set(true));

        try {
            accept.join();
        } catch (CompletionException e) {
            System.out.println("Failure type: "
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("Accept called: " + acceptCalled.get());
        System.out.println("Run called: " + runCalled.get());
        System.out.println("Run exceptional: "
                + run.isCompletedExceptionally());

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 7);
        AtomicInteger combined = new AtomicInteger();

        good.thenAcceptBoth(recovered,
                (a, b) -> combined.set(a + b)).join();

        System.out.println("Recovered sum: " + combined.get());
    }
}
```

```bash
javac BothFailureDemo.java
java BothFailureDemo
```

Đầu ra:

```text
Failure type: IllegalStateException
Accept called: false
Run called: false
Run exceptional: true
Recovered sum: 10
```

**Giải thích:** `failedFuture` đã exceptional nên cả hai dependent actions của `accept` và `run` **không chạy**. `accept.join()` ném `CompletionException` với cause `IllegalStateException`. Ta dùng `failed.exceptionally(...)` để tạo **stage mới** có fallback 7; khi kết hợp với `good=3`, `thenAcceptBoth` chạy bình thường và đặt tổng 10.

Việc `run.isCompletedExceptionally()` true không có nghĩa callback `run` đã chạy rồi ném: ngược lại, nó có thể thất bại do một source thất bại **trước khi Runnable được gọi**.

### Đường hủy

Khi một `CompletableFuture` nguồn bị `cancel(true)`, chính nguồn đó có thể ném `CancellationException` khi `join()`. Dependent stage cần nguồn thành công có thể nhận outcome exceptional bọc cancellation dưới `CompletionException`. `isDone()` true không đồng nghĩa thành công; `isCancelled()` của dependent không nhất thiết true dù nguyên nhân lỗi là source canceled.

Một stage bị cancel không tự interrupt underlying worker trong implementation `CompletableFuture` chuẩn. Đặc biệt, **hủy stage `accept` không tự hủy `good` và `failed` ở upstream**; nếu cần dừng công việc thật, phải có cancellation policy/ownership riêng.

## 13. Nếu action ném lỗi thì điều gì xảy ra?

Một source có thể thành công, nhưng **hành động cuối** vẫn thất bại:

```java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b =
        CompletableFuture.completedFuture(3);

CompletableFuture<Void> written = a.thenAcceptBoth(b, (x, y) -> {
    throw new IllegalStateException("audit unavailable");
});
```

Đây là trích đoạn; cần import `CompletableFuture`. Hai source vẫn thành công, nhưng dependent `written` hoàn tất **ngoại lệ** vì action ném lỗi. `written.join()` thường ném `CompletionException` bọc `IllegalStateException`. Không nhầm “hai nhánh thành công” với “action tiếp theo chắc chắn thành công”.

Với `runAfterBoth`, một `Runnable` cũng có thể ném unchecked exception. Cả hai method cho phép dùng `exceptionally`, `handle`, `whenComplete` trên **dependent stage** để quan sát hoặc phục hồi lỗi:

```java
CompletableFuture<Void> observed = written.whenComplete(
        (ignored, error) -> {
            if (error != null) {
                System.err.println("Audit failure: " + error);
            }
        });
```

Trích đoạn trên có `written` từ ví dụ trước. `whenComplete` dùng cho **observation**, không tự biến failure thành success chỉ vì đã in log. Muốn recovery có thể dùng `exceptionally(error -> null)` trên `CompletableFuture<Void>`, nhưng phải quyết định rõ việc chấp nhận một audit failure là “thành công theo fallback” có hợp lý với nghiệp vụ không.

**Một lỗi phổ biến:** đăng ký action để ghi audit, sau đó bỏ `CompletableFuture<Void>` kết quả. Nếu action thất bại mà không có terminal observer/metrics, lỗi có thể bị giữ trong dependent stage mà caller không bao giờ phát hiện.

## 14. Không có bảo đảm thứ tự giữa hai dependent độc lập

Xem hai hành động đều đợi cùng A và B:

```java
CompletableFuture<Void> first =
        a.thenAcceptBoth(b, (x, y) -> audit(x, y));

CompletableFuture<Void> second =
        a.runAfterBoth(b, () -> publishReady());
```

Đây là trích đoạn, cần `a`, `b` và hai method ứng dụng. **Không có thứ tự nhân-quả** từ `first` sang `second` chỉ vì dòng tạo `first` viết trước. Khi cả hai source completed, hai action có thể được thực thi theo thứ tự hoặc thread khác nhau.

Nếu `publishReady()` **bắt buộc chạy sau khi audit hoàn tất**, phải tạo dependency rõ:

```java
CompletableFuture<Void> audited =
        a.thenAcceptBoth(b, (x, y) -> audit(x, y));

CompletableFuture<Void> published =
        audited.thenRun(() -> publishReady());
```

Vì `published` phụ thuộc `audited`, hành động publish chỉ chạy bình thường sau khi audit stage thành công. Tương tự, có thể chain `runAfterBoth` trên một stage `Void` đã completed và một stage khác. Điều này khác hẳn việc hai action cùng đăng ký độc lập lên cùng hai source.

### Ví dụ 5 — Ép thứ tự bằng dependency, không bằng thời điểm đăng ký

Tạo file **`OrderedBothActionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class OrderedBothActionsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> first =
                CompletableFuture.completedFuture(2);
        CompletableFuture<Integer> second =
                CompletableFuture.completedFuture(3);

        List<String> events = new ArrayList<>();

        CompletableFuture<Void> audited = first.thenAcceptBoth(
                second,
                (a, b) -> events.add("audit=" + (a + b))
        );

        CompletableFuture<Void> published = audited.thenRun(
                () -> events.add("published")
        );

        CompletableFuture<Void> finished =
                published.runAfterBoth(second,
                        () -> events.add("finished"));

        finished.join();
        System.out.println("Events: " + events);
        System.out.println("Finished normally: "
                + !finished.isCompletedExceptionally());
    }
}
```

```bash
javac OrderedBothActionsDemo.java
java OrderedBothActionsDemo
```

Đầu ra:

```text
Events: [audit=5, published, finished]
Finished normally: true
```

Ở đây `ArrayList` bình thường **không bị hai callback độc lập sửa đồng thời**: các action là một chuỗi phụ thuộc `audited → published → finished`; main chỉ đọc `events` sau `finished.join()`. Ngay cả khi từng action được chuyển sang executor khác ở thiết kế mở rộng, dependency chain vẫn biểu diễn thứ tự giữa các action theo completion.

**Không mở rộng mô hình này** bằng cách tạo nhiều dependent action cùng sửa một `ArrayList` rồi cho rằng `CompletableFuture` tự đồng bộ collection. Nếu có nhiều writer không được chain theo thứ tự, dùng cấu trúc concurrent/synchronization hoặc trả kết quả immutable từ từng nhánh.

## 15. “Cả hai thành công” có nghĩa callback không phải finally

Giả sử mỗi source sử dụng network/file:

```text
Task A ----- success ----+
                         +-- runAfterBoth(cleanup)
Task B ----- failure ----+
```

Trong trường hợp này, `runAfterBoth(cleanup)` **không phải callback cleanup luôn chạy**: nếu B lỗi, Runnable bình thường không chạy. Do đó, với tài nguyên do task A/B sở hữu, đặt `try-with-resources` hoặc `finally` **bên trong chính task tương ứng**. Với tài nguyên thuộc cả operation, có thể dùng một stage tổng hợp và `whenComplete` hoặc một cơ chế lifecycle xác nhận các nhánh đã kết thúc theo hợp đồng.

**Không thay bằng `whenComplete` một cách máy móc** nếu bạn cần chờ cả hai task thật sự dừng. Outcome exceptional/canceled của một `CompletableFuture` có thể xảy ra trước khi computation nền ngừng. Nếu một source hủy trạng thái nhưng worker vẫn chạy, callback quan sát trạng thái Future không phải bằng chứng file/socket đã đóng.

Một điểm nữa: `thenAcceptBoth` và `runAfterBoth` không áp đặt thứ tự completion giữa A và B. `B` có thể xong trước `A`, rồi action chạy sau khi A cũng hoàn tất; nếu A và B thực hiện side effects cạnh tranh lên cùng resource, cần đồng bộ **bên trong các nhánh**, không đợi tới callback cuối mới xử lý data race.

## 16. So với allOf(): chọn đúng mức tổng hợp

Với đúng **hai stage** và hành động cần giá trị của cả hai, `thenAcceptBoth` thuận tiện và type-safe:

```java
CompletionStage<Void> sent =
        order.thenAcceptBoth(customer,
                (o, c) -> sendReceipt(o, c));
```

Đây là trích đoạn minh họa. Nếu chỉ chờ hai stage hoàn tất thành công rồi chạy action không cần input, `runAfterBoth` ngắn gọn:

```java
CompletionStage<Void> started =
        prepareA.runAfterBoth(prepareB, () -> startNextPhase());
```

Với **N stage**, `CompletableFuture.allOf(stages...)` tạo barrier linh hoạt hơn:

```java
CompletableFuture<Void> all =
        CompletableFuture.allOf(jobA, jobB, jobC);

CompletableFuture<Void> committed =
        all.thenRun(() -> markBatchDone());
```

Các đoạn đều giả định stage và method nghiệp vụ đã khai báo. `allOf` trả `CompletableFuture<Void>`, không tự cung cấp `List<T>` của các input. Nếu cần giá trị sau allOf, có thể lấy từng result theo contract sau barrier thành công hoặc xây một stage chuyển đổi.

**Tránh kết luận “allOf đợi mọi thread/side effect tuyệt đối”** khi một input bị complete sớm do cancellation/timeout trong lúc worker nền vẫn chạy. Stage completion và worker termination là hai mốc khác nhau. Nếu cả nhóm có lỗi, `allOf` có exceptional outcome; nó không tự cancel toàn bộ siblings theo một structured cancellation scope.

## 17. Sự khác nhau với thenCombine(): cần giá trị thì đừng dùng Void

Nếu một bước sau cần `total` làm input:

```java
CompletableFuture<Integer> total =
        price.thenCombine(tax, Integer::sum);

CompletableFuture<String> invoice =
        total.thenApply(amount -> "Total=" + amount);
```

Hai dòng là trích đoạn có `price` và `tax` thích hợp. `thenCombine` trả `Integer` để pipeline sau có thể dùng. Nếu dùng `thenAcceptBoth` rồi chỉ `System.out.println` tổng, bạn đã “tiêu thụ” kết quả bằng side effect; stage trả `Void` nên bước kế tiếp không được truyền tổng đó.

Câu hỏi chọn method:

1. **Bước tiếp theo cần giá trị mới từ hai source?** `thenCombine`.
2. **Cần xử lý/tiêu thụ trực tiếp hai giá trị nhưng không cần trả giá trị?** `thenAcceptBoth`.
3. **Chỉ cần cả hai xong, không cần bất kỳ giá trị nào?** `runAfterBoth`.
4. **Chỉ một input và side effect với giá trị của nó?** `thenAccept`.
5. **Chỉ một input và action không cần giá trị?** `thenRun`.
6. **Cần phối hợp nhiều hơn hai source?** `allOf` cùng bước sau phù hợp.

Việc chọn đúng method giúp kiểu `Void` phản ánh ý định của API, tránh tạo dependency ngầm qua biến mutable dùng chung.

## 18. Không có “hai nhánh” nếu bạn chưa bắt đầu hai công việc độc lập

Một lỗi logic thường gặp:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> loadFirst(), executor);

CompletableFuture<Integer> second =
        first.thenApply(value -> value + 1);

CompletableFuture<Void> done =
        first.runAfterBoth(second, () -> signal());
```

Đây là trích đoạn minh họa. `second` phụ thuộc vào `first`, nên hai stage **không độc lập**; `runAfterBoth` vẫn đúng về completion nhưng không biến phần thứ hai thành công việc chạy song song. Nếu hai nguồn thật sự độc lập:

```java
CompletableFuture<Integer> first =
        CompletableFuture.supplyAsync(() -> loadFirst(), executor);

CompletableFuture<Integer> second =
        CompletableFuture.supplyAsync(() -> loadSecond(), executor);
```

Đây cũng là trích đoạn. Hai source được submit độc lập và **có cơ hội song song** nếu executor có đủ worker và nguồn dữ liệu cho phép. Tuy nhiên, không có cam kết JVM luôn chạy đồng thời trên hai lõi CPU; scheduling, queueing, blocking và tài nguyên quyết định thực tế.

Không dùng việc `runAfterBoth` trả `Void` để suy hai nguồn chỉ có side effects. Source vẫn có thể trả `Integer`, `String`, record hoặc `Void`; `Runnable` đơn giản **không nhận các result đó**.

## 19. Xử lý null, generic types và lambda capture

`thenAcceptBoth` dùng `BiConsumer<? super T,? super U>`, nên generic cho phép hai source có **kiểu khác nhau**:

```java
CompletableFuture<String> name =
        CompletableFuture.completedFuture("Java");
CompletableFuture<Integer> version =
        CompletableFuture.completedFuture(17);

CompletableFuture<Void> print =
        name.thenAcceptBoth(version,
                (n, v) -> System.out.println(n + " " + v));
```

Đây là trích đoạn. Với `CompletableFuture.completedFuture(null)`, source vẫn có thể completed **thành công**, và `thenAcceptBoth` có thể được gọi với tham số null. Nếu action dereference null mà không kiểm tra, chính action có thể ném `NullPointerException`, khiến dependent stage exceptional. `null` **không đồng nghĩa** exceptional completion.

Đối với `runAfterBoth`, hai kiểu source có thể hoàn toàn khác, nhưng callback không được truyền giá trị. Nếu callback capture một object mutable từ scope ngoài, đó là reference được capture, **không phải snapshot bảo đảm immutable**. Cần xét đồng bộ và quyền sở hữu khi nhiều task có thể đọc/ghi cùng object.

Một điểm phân biệt syntax: `thenAcceptBoth` nhận `(left, right) -> { ... }`; `runAfterBoth` nhận `() -> { ... }`. Compiler sẽ không chấp nhận một `BiConsumer` ở overload nhận `Runnable` hoặc ngược lại.

## 20. Java Memory Model và happens-before

Đối với `Future`, các hành động do asynchronous computation thực hiện có quan hệ **happens-before** với những hành động xảy ra trong thread khác **sau `Future.get()`** tương ứng, theo hợp đồng memory consistency của Java. `CompletableFuture` thực hiện completion và publication để dependent actions có thể nhận kết quả của các source đã hoàn tất theo Java Memory Model.

Đối với **hai nhánh A và B**, callback `thenAcceptBoth` chỉ chạy trên đường thành công khi **hai kết quả đã được công bố qua completion**, và `runAfterBoth` chỉ chạy sau điều kiện completion tương ứng. Điều đó cho phép callback sử dụng những dữ liệu được truyền hợp lệ từ source, không cần polling một biến boolean thường để đoán hai task đã xong.

**Giới hạn quan trọng:**

- Không làm an toàn cho hai source cùng tăng một biến `int` bình thường bằng `++` trước khi callback chạy. Race đã xảy ra **trong hai source**; đợi cuối không sửa kết quả.
- Không tự đồng bộ mutation **xảy ra sau khi source đã complete** trên một mutable object đang được callback đọc.
- Không bảo đảm worker không còn chạy nếu source `CompletableFuture` đã được cancel/timeout sớm nhưng underlying supplier chưa thoát.
- Không biến `ArrayList` dùng chung cho hai dependent callbacks thành concurrent collection.
- Không thay `try/finally`, transaction hay I/O timeout trong task.

Ưu tiên **immutable result**, `record`, final fields, snapshot, hoặc các primitive `Atomic*`, lock và concurrent collection khi thực sự có mutable shared state. Việc stage thành công làm mốc dữ liệu **đã được công bố**, không phải chứng nhận toàn bộ hệ thống đã về trạng thái nhất quán ngoài JVM.

## 21. Deadline, cancellation và vòng đời Executor

Hai action đợi thành công của hai source, nhưng **không có timeout tự động**. Nếu một source không bao giờ complete, dependent stage có thể không bao giờ hoàn tất; `dependent.join()` sẽ chờ vô hạn.

Các cách quản lý:

- `dependent.get(timeout, unit)` giới hạn **lần chờ của caller**, không tự dừng hai source.
- `source.orTimeout(timeout, unit)` có thể hoàn tất chính source bằng lỗi `TimeoutException`; do đó dependent `thenAcceptBoth/runAfterBoth` **không chạy action thành công**.
- `completeOnTimeout(fallback, ...)` có thể biến source thành **hoàn tất thành công với fallback**; dependent sau đó có thể chạy với fallback — cần quyết định điều đó có phù hợp nghiệp vụ.
- `cancel(true)` của `CompletableFuture` **không bảo đảm interrupt worker** đang chạy; cần cancellation token, timeout của I/O và quản lý resource riêng.
- Dùng một **overall deadline** từ lúc nhận request nếu SLA bao gồm cả thời gian queue, hai nhánh và dependent action.
- Nếu action dùng `*Async(..., executor)`, executor phải còn hoạt động khi action được submit; shutdown quá sớm có thể làm stage exceptional do rejection.

Với executor riêng, owner nên `shutdown()` và `awaitTermination(timeout)` khi cần xác nhận worker đã kết thúc. Nếu action của hai nhánh/side effects còn đang chạy, trạng thái `isDone()` của một stage không liên quan không đủ làm bằng chứng chúng hoàn tất. Đừng tự ý shutdown `ForkJoinPool.commonPool()` như tài nguyên của một request.

## 22. Side effects: logging, gửi thông báo, cache và idempotency

Tên “Accept” và “Run” gợi ý hai method hay được dùng ở ranh giới side effect:

- `thenAcceptBoth`: gửi email/thông báo bằng hai payload nguồn, ghi audit với hai kết quả, cập nhật view khi cả giá và số lượng đã có.
- `runAfterBoth`: đánh dấu “đủ hai bước” để chuyển giai đoạn, release một tín hiệu điều phối, chạy một hành động không cần payload.
- Dùng `thenCombine` nếu việc kết hợp hai nguồn **phải trả lại một dữ liệu mới**, ví dụ đơn hàng đã tính giá.

Các hành động bên ngoài JVM không được CompletableFuture tự giao dịch hóa:

1. Action ném exception **không rollback** một phần email/file write đã thực hiện.
2. Hủy dependent stage khi action đã chạy **không chắc ngừng side effect đang diễn ra**.
3. Retry pipeline có thể gọi lại action và tạo side effect trùng nếu không có idempotency.
4. Hai callback độc lập có thể thực hiện side effect không theo thứ tự dự kiến.
5. Consumer khác có thể hủy source dùng chung; cần xác định **quyền ownership/cancellation**.

Khi yêu cầu đúng-một-lần về nghiệp vụ, cần message ID, deduplication, transaction hoặc các giao thức phù hợp. Không suy CompletableFuture tự cung cấp exactly-once cho HTTP request hay database.

## 23. Lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Dùng `thenAcceptBoth` nhưng mong stage trả giá trị tổng hợp. | Callback trả void, dependent là `Void`. | Dùng `thenCombine` nếu cần result `V`. |
| Dùng `runAfterBoth` rồi gọi `join()` trong callback để đọc hai source. | Rườm rà, dễ nhầm exception và capture state. | Dùng `thenAcceptBoth` để nhận hai giá trị typed. |
| Nghĩ `runAfterBoth` chạy nếu một source fail. | Đây là success-dependent action. | Xử lý lỗi riêng; cleanup bằng `finally`/`whenComplete` có contract phù hợp. |
| Nghĩ `Void` có nghĩa action không cần theo dõi. | Action có thể lỗi/chưa chạy. | Giữ dependent stage, quan sát success/error. |
| Dùng `thenAcceptBoth` mà hai source thực ra phụ thuộc nhau. | Không có thêm song song nếu nhánh 2 phụ thuộc nhánh 1. | Đánh giá dependency graph và chọn API rõ. |
| Giả định callback non-Async luôn chạy trên main. | Thread thực thi phụ thuộc completion/scheduler. | Dùng overload Async có Executor nếu cần điều khiển. |
| Giả định `*Async` luôn tạo thread mới. | Executor thường tái sử dụng worker. | Chọn thread pool và hiểu policy. |
| Tạo hai dependent callbacks nhưng tin chúng chạy theo thứ tự đăng ký. | Không có ordering dependency giữa chúng. | Chain `thenRun`/`thenCompose` dựa trên dependent stage trước. |
| Callback blocking I/O trên completing thread. | Có thể giữ thread nhạy latency. | Dùng executor phù hợp và I/O timeout. |
| Block một worker chờ action đang xếp hàng chính executor đó. | Có thể thread starvation/deadlock. | Dùng composition, không get/join trong worker vô cớ. |
| Đặt `source.orTimeout` rồi nghĩ worker tự dừng. | Timeout thay trạng thái source, không bảo đảm dừng computation. | Cancellation hợp tác/I/O timeout riêng. |
| Hủy dependent rồi nghĩ upstream và sibling tự hủy. | CompletableFuture không có structured cancellation tự động. | Thiết kế ownership và cancel protocol. |
| Dùng `isDone()` là thước đo action thành công. | Done cũng bao gồm exceptional/canceled. | Dùng `join/get` hoặc error observer phù hợp. |
| Đọc shared mutable object đang được hai task sửa rồi tin callback cuối sửa được race. | Data race xảy ra trước barrier. | Tách dữ liệu, immutable snapshots hoặc synchronization. |
| `whenComplete` dùng như fallback value. | Nó quan sát outcome, không tự đổi exceptional thành success. | Dùng `handle` hoặc `exceptionally` với chính sách rõ. |
| Ghi audit rồi bỏ CompletableFuture<Void> kết quả. | Callback error có thể không được quan sát. | Quản lý terminal stage và metrics/logging. |
| Shutdown executor trước khi Async dependent được submit. | Callback bị rejection/exceptional. | Chờ pipeline/có lifecycle ownership phù hợp. |

## 24. Checklist áp dụng vào dự án

1. **Mỗi source có thực sự độc lập không?** Nếu không, đừng giả định tăng tốc nhờ “both”.
2. **Hành động cần giá trị không?** Có cả hai → `thenAcceptBoth`; không cần → `runAfterBoth`.
3. **Có cần kết quả để chain tiếp không?** Dùng `thenCombine` thay vì chỉ side effect.
4. **Source đã có đường completion chưa?** Không bỏ quên CompletableFuture chưa bao giờ complete.
5. **Ai thực hiện callback?** Non-Async/Async/default executor/explicit executor; tránh block completing thread.
6. **Có yêu cầu thứ tự giữa hai callback không?** Tạo dependency rõ thay vì tin thứ tự đăng ký.
7. **Nếu một source lỗi?** Action both không chạy; có đường xử lý exception và resource cleanup.
8. **Nếu action lỗi?** Dependent stage exceptional; quan sát qua `join/get` hoặc `handle/whenComplete`.
9. **Cancellation có ý nghĩa nào?** Hủy trạng thái Future không tự dừng worker; theo dõi task thật khi cần.
10. **Có timeout tổng không?** Đặt deadline cả hai nhánh và action, không chỉ timeout của một get.
11. **Payload mutable?** Dùng immutable snapshot hoặc synchronization đúng, không lợi dụng `Void` để che race.
12. **Có side effect ngoài JVM?** Idempotency/acknowledgement/transaction riêng.
13. **Có dùng chung source giữa nhiều caller?** Xem quyền hủy nguồn và isolation cho dependent stages.
14. **Executor shutdown lúc nào?** Khi các dependent action cần thiết đã completed và worker/resource lifecycle cho phép.
15. **Có test nhánh lỗi/hủy?** Kiểm tra callback không chạy khi source exceptional, và test action tự ném lỗi.
16. **Có test thứ tự không?** Tạo chain thay vì phụ thuộc scheduler.
17. **Có test với stage chưa complete?** Dùng `new CompletableFuture<>()`, `complete()` theo kịch bản để tránh sleep.
18. **Theo dõi production:** completion latency, exceptional outcomes, rejected actions, queue depth và task timeout.

## 25. Tự kiểm tra kiến thức

1. **`thenAcceptBoth` đợi gì?** Cả hai source hoàn tất bình thường trước khi gọi BiConsumer.
2. **`runAfterBoth` khác ở đâu?** Runnable không nhận kết quả nào từ hai source.
3. **Hai method trả loại kết quả gì?** Dependent `CompletionStage<Void>` hoặc `CompletableFuture<Void>` khi gọi trên CompletableFuture.
4. **`Void` có nghĩa dependent không có trạng thái lỗi không?** Không; stage vẫn có exceptional/canceled completion.
5. **Khi chỉ source A xong, action both chạy chưa?** Chưa, nếu source B còn incomplete.
6. **Nếu B complete exceptionally?** Success action không chạy, dependent exceptional.
7. **Nếu callback thenAcceptBoth ném lỗi thì hai source có bị đổi thành failed không?** Không; lỗi thuộc dependent stage.
8. **`thenAcceptBoth` có tự chạy A và B trên hai thread không?** Không; source phải được tạo/khởi động riêng.
9. **`thenAcceptBothAsync` có cần Executor không?** Có overload mặc định và overload nhận Executor chỉ định.
10. **`runAfterBoth` và `runAfterEither` giống nhau không?** Không; both cần cả hai, either theo một nhánh theo contract của API.
11. **Hai dependent action cùng đợi A/B có thứ tự cố định không?** Không; phải chain nếu cần thứ tự.
12. **Khi nào dùng `thenCombine`?** Khi muốn tạo giá trị tổng hợp để truyền tiếp.
13. **Vì sao `allOf` không hoàn toàn giống thenAcceptBoth?** allOf là barrier cho nhiều Future, không tự cung cấp BiConsumer typed hai kết quả.
14. **`runAfterBoth` có phải finally cleanup cho source lỗi không?** Không.
15. **`acceptsBoth.join()` thành công trả gì?** `null` cho kiểu Void, nhưng xác nhận action stage completed bình thường.
16. **Hủy CompletableFuture có bảo đảm interrupt worker không?** Không.
17. **`get(timeout)` trên dependent có tự dừng hai source không?** Không, chỉ giới hạn lần chờ.
18. **Nếu A/B có data race khi chạy, barrier both có sửa được race không?** Không.
19. **Callback non-Async có thể chạy trên thread nào?** Thread hoàn tất source hoặc thread tham gia completion, không cam kết cố định.
20. **Có nên bỏ dependent stage của hành động audit bắt buộc?** Không; cần quan sát outcome để bảo đảm lỗi không bị mất.

**Ghi nhớ:** `thenAcceptBoth(other, BiConsumer)` = **cả hai thành công, lấy hai kết quả để thực hiện hành động, không trả result**. `runAfterBoth(other, Runnable)` = **cả hai thành công, chỉ chạy hành động không nhận kết quả**. Cả hai trả `CompletionStage<Void>` có thể được theo dõi; muốn giá trị mới dùng `thenCombine`, muốn thứ tự thì **chain dependent stages**, muốn chạy trên pool cụ thể thì dùng overload **Async + Executor**, và luôn xử lý lỗi/cancellation/resource ownership riêng.
