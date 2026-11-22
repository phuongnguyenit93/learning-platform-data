# CompletableFuture.thenCombine() khi cần phối hợp hai kết quả trong Java

## 1. Bài toán: hai tác vụ độc lập, một kết quả tổng hợp

Khi một kết quả nghiệp vụ phải được tạo từ **hai phép tính độc lập**, cách viết tuần tự thường là tính A, chờ A xong, tính B, chờ B xong, rồi phối hợp A và B. Nếu A và B có thể tiến hành độc lập, cách đó có thể làm tăng thời gian phản hồi không cần thiết.

Ví dụ:

- Đọc giá sản phẩm và đọc số lượng tồn kho độc lập, rồi tạo bản tóm tắt hiển thị.
- Tính tiền hàng và chi phí vận chuyển độc lập, rồi tính tổng thanh toán.
- Lấy hồ sơ người dùng và danh sách quyền độc lập, rồi ghép thành một đối tượng kết quả.
- Phân tích hai phần dữ liệu riêng, sau đó kết hợp thành báo cáo.

`CompletableFuture.thenCombine()` biểu đạt quan hệ **AND**: chỉ chạy hàm phối hợp **sau khi cả hai giai đoạn đầu vào hoàn tất thành công**. Nó trả về một `CompletableFuture<V>` mới đại diện cho kết quả tổng hợp; caller không phải tự gọi `get()`/`join()` lần lượt trên từng đầu vào để phối hợp.

```text
futureA: ----------- A thành công ----┐
                                    ├── thenCombine(A, B) ──> C
futureB: ----- B thành công ---------┘

C chỉ được tính khi có cả A và B.
Thứ tự A/B hoàn tất không quyết định thứ tự tham số trong hàm phối hợp.
```

Bài này chỉ sử dụng **Java Concurrency nói chung** (JDK `java.util.concurrent`), không phụ thuộc Spring hoặc cách tích hợp CompletableFuture của bất kỳ framework nào.

## 2. Kiểu dữ liệu và chữ ký thenCombine

`CompletableFuture<T>` là một implementation của `CompletionStage<T>` và `Future<T>`. Nó cho phép tạo pipeline xử lý mà mỗi bước có thể hoàn thành trong tương lai.

Các overload quan trọng khi gọi từ một `CompletableFuture<T>`:

```java
<U, V> CompletableFuture<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);

<U, V> CompletableFuture<V> thenCombineAsync(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);

<U, V> CompletableFuture<V> thenCombineAsync(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn,
        Executor executor);
```

Đây là **đoạn chữ ký API minh họa**, không phải một interface Java độc lập.

- `T`: kiểu kết quả của stage bên trái, tức đối tượng nhận lời gọi.
- `U`: kiểu kết quả của stage `other`.
- `V`: kiểu kết quả sau khi kết hợp.
- `BiFunction<T, U, V>`: hàm nhận **hai giá trị đã thành công**, trả về **một giá trị mới**.
- `other`: một `CompletionStage`, không nhất thiết đúng kiểu triển khai `CompletableFuture`.
- Kiểu trả về khi gọi từ `CompletableFuture` là một `CompletableFuture<V>` **mới**. Hai future đầu vào không bị thay đổi kết quả chỉ vì ghép.

Ví dụ tối giản:

```java
CompletableFuture<Integer> price =
        CompletableFuture.completedFuture(100);
CompletableFuture<Integer> shipping =
        CompletableFuture.completedFuture(20);

CompletableFuture<String> invoice = price.thenCombine(
        shipping,
        (p, s) -> "Total = " + (p + s));

System.out.println(invoice.join()); // Total = 120
```

Đoạn này là fragment; muốn chạy độc lập cần `import java.util.concurrent.CompletableFuture;` và một `main` phù hợp.

**Quan trọng:** `thenCombine` **không tự tạo ra hai tác vụ**. Nó chỉ gắn bước phối hợp vào hai stage đã có. Nếu cả hai được tạo bằng `completedFuture` như ví dụ, hàm kết hợp có thể chạy ngay trên thread đang gọi; không có song song hóa nào được sinh ra. Song song xảy ra khi các nguồn A và B đã được bố trí chạy độc lập, chẳng hạn bằng `supplyAsync`.

## 3. Trình tự thực thi và điều kiện kích hoạt

Giả sử:

```java
CompletableFuture<String> a = ...;
CompletableFuture<Integer> b = ...;

CompletableFuture<String> combined =
        a.thenCombine(b, (name, count) -> name + ":" + count);
```

Đây là fragment với hai nguồn `a` và `b` do ứng dụng định nghĩa.

Có ba loại kết thúc cần phân biệt:

| Trạng thái của A | Trạng thái của B | Hành vi của stage kết hợp |
| --- | --- | --- |
| Thành công | Thành công | Gọi `BiFunction` đúng một lần và hoàn thành bằng giá trị `V`, trừ khi hàm ném lỗi |
| Thành công | Thất bại | Không gọi hàm phối hợp; stage kết hợp kết thúc bất thường |
| Thất bại | Thành công | Không gọi hàm phối hợp; stage kết hợp kết thúc bất thường |
| Một/both bị hủy | Bên kia bất kỳ | Cancellation là hoàn tất bất thường; stage phụ thuộc không tạo giá trị phối hợp thành công |
| Cả hai thành công nhưng `BiFunction` ném lỗi | Thành công ở hai nguồn | Stage kết hợp hoàn tất bất thường với lỗi của chính hàm phối hợp |

Không nên giả định `thenCombine` có semantics **fail-fast** như một cơ chế race. Khi một đầu vào lỗi, Java không bảo đảm dependent kết thúc ngay lập tức nếu đầu vào còn lại vẫn đang pending; implementation có thể chỉ kích hoạt hành vi phụ thuộc sau khi cả hai đầu vào đã hoàn tất theo hợp đồng “both”. Vì vậy, hãy đặt deadline tổng hoặc xử lý lỗi/hủy chủ động nếu không thể chờ nguồn còn lại.

Hai stage thành công có thể hoàn tất theo bất kỳ thứ tự nào. Tuy nhiên, trong `a.thenCombine(b, (x, y) -> ...)`, `x` luôn là kết quả của `a`, `y` luôn là kết quả của `b`. Đừng nhầm “bên hoàn tất trước” với tham số thứ nhất.

### Phân biệt kết quả null và thất bại

Một stage có thể hoàn tất thành công với `null`. `thenCombine` vẫn có thể gọi `BiFunction` với tham số `null`; nếu callback không xử lý null, nó có thể ném `NullPointerException`, khiến **stage kết hợp** thất bại. Một giá trị thành công bằng `null` **không giống** trạng thái exceptional completion.

Nếu cần ràng buộc non-null, xác thực đầu vào, dùng kiểu Optional hoặc chuyển lỗi đúng ở ranh giới ứng dụng, thay vì mặc định kết quả stage luôn khác null.

## 4. Ví dụ Java 17 độc lập: chạy hai công việc, rồi tính hóa đơn

Chương trình tạo hai `CompletableFuture` bằng `supplyAsync` trên một `ExecutorService` có hai worker. Hai nhiệm vụ không phụ thuộc nhau. `thenCombine` ghép kết quả thành chuỗi và `join()` được dùng **một lần tại ranh giới main** để lấy kết quả cuối.

Lưu file `ThenCombineDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenCombineDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> productCost =
                    CompletableFuture.supplyAsync(() -> 180, pool);

            CompletableFuture<Integer> shippingCost =
                    CompletableFuture.supplyAsync(() -> 20, pool);

            CompletableFuture<String> bill =
                    productCost.thenCombine(
                            shippingCost,
                            (product, shipping) ->
                                    "Total = " + (product + shipping));

            System.out.println(bill.join());
            System.out.println("Product = " + productCost.join());
            System.out.println("Shipping = " + shippingCost.join());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ThenCombineDemo.java
java ThenCombineDemo
```

Stdout:

```text
Total = 200
Product = 180
Shipping = 20
```

Tại sao stdout xác định? Các callback không in trực tiếp từ worker. Main in lần lượt sau khi `bill.join()` trả kết quả, lúc đó cả hai nguồn đã hoàn tất thành công. Dù thứ tự hai nguồn xong trước/sau thay đổi, giá trị và thứ tự ba dòng in không đổi.

**Đừng tự kết luận hai phép tính chắc chắn chạy song song chỉ từ việc có hai `supplyAsync`.** Executor có thể lập lịch chúng nối tiếp khi thiếu worker hoặc khi tài nguyên máy bị hạn chế. Điều chắc chắn là hai nguồn được **lập lịch độc lập** và stage ghép phụ thuộc kết quả của cả hai.

### Biến thể dùng kiểu dữ liệu khác nhau

`thenCombine` không đòi hỏi hai nguồn có cùng kiểu:

```java
record User(long id, String name) {}
record Plan(String title, int quota) {}
record View(String name, String plan, int quota) {}

// Fragment: hai stage có thể đến từ hai nguồn bất đồng bộ.
CompletableFuture<User> userFuture = ...;
CompletableFuture<Plan> planFuture = ...;

CompletableFuture<View> viewFuture =
        userFuture.thenCombine(planFuture,
                (user, plan) ->
                        new View(user.name(), plan.title(), plan.quota()));
```

Đây là **fragment**; `record` có thể khai báo trong một class hoặc cùng file nguồn khi biên dịch, còn hai source future cần được khởi tạo. Hàm phối hợp nên tập trung vào biến đổi dữ liệu; tránh blocking và side effect khó kiểm soát trong callback.

## 5. thenCombine, thenApply và thenCompose khác nhau ở đâu?

Ba thao tác thường bị nhầm:

| API | Số đầu vào thực tế | Khi dùng | Kiểu quan hệ |
| --- | --- | --- | --- |
| `thenApply(fn)` | Một stage có kết quả | Biến đổi `T → V` sau khi một nguồn thành công | Chuỗi tuyến tính |
| `thenCompose(fn)` | Một stage, hàm trả về stage khác | Khi bước sau **phụ thuộc** kết quả bước trước và tự là bất đồng bộ | Phụ thuộc tuần tự / flatten |
| `thenCombine(other, fn)` | Hai stage độc lập | Khi cần **cả hai** kết quả để tính `V` | Kết hợp AND |
| `thenAcceptBoth(other, action)` | Hai stage độc lập | Khi cần sử dụng hai kết quả nhưng **không cần trả giá trị V** | Hai đầu vào → `Void` |
| `runAfterBoth(other, runnable)` | Hai stage | Khi chỉ cần biết cả hai thành công, **không dùng giá trị** | Hai đầu vào → `Void` |
| `allOf(a,b,...)` | N stage | Đợi nhiều stage và thiết kế cách đọc từng kết quả | N đầu vào → `CompletableFuture<Void>` |
| `anyOf(a,b,...)` | N stage | Kết thúc khi **bất kỳ** stage nào hoàn tất, kể cả lỗi | OR, không phải “một thành công” |

### thenApply: biến đổi một kết quả

```java
CompletableFuture<Integer> base =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> doubled =
        base.thenApply(x -> x * 2);
```

Kết quả `doubled.join()` là 20. Không có nguồn độc lập thứ hai cần ghép.

### thenCompose: bước sau phụ thuộc bước trước

```java
CompletableFuture<String> orderId =
        CompletableFuture.completedFuture("O-7");

CompletableFuture<Integer> amount =
        orderId.thenCompose(id ->
                CompletableFuture.supplyAsync(() -> id.length() * 10));
```

Đoạn fragment này tạo một stage bên trong chỉ **sau khi** biết `id`. `thenCompose` sẽ “làm phẳng” `CompletableFuture<CompletableFuture<Integer>>` về `CompletableFuture<Integer>`. Không dùng `thenCombine` nếu B **cần đầu ra của A mới có thể bắt đầu**.

### thenCombine: hai nguồn đã có hoặc có thể bắt đầu độc lập

```java
CompletableFuture<Integer> subtotal = ...;
CompletableFuture<Integer> tax = ...;

CompletableFuture<Integer> total =
        subtotal.thenCombine(tax, Integer::sum);
```

Các dấu `...` ở hai dòng đầu là placeholder cho snippet minh họa, **không phải chương trình độc lập**. Điểm khác biệt: `subtotal` và `tax` là hai stage **có thể được khởi tạo trước nhau hoặc song song**, và chỉ bước ghép mới cần cả hai.

### Không lạm dụng allOf cho đúng hai nguồn

`CompletableFuture.allOf(a, b)` trả `CompletableFuture<Void>`; muốn lấy hai giá trị vẫn phải truy cập `a.join()` và `b.join()` sau khi allOf thành công. Với đúng hai stage và một `BiFunction` rõ ràng, `thenCombine` thường ngắn gọn, dễ giữ kiểu hơn.

## 6. thenCombine() và thenCombineAsync(): callback chạy ở đâu?

Đây là nguồn hiểu nhầm lớn. Cả hai đều cần hai kết quả thành công, nhưng khác **chính sách thực thi callback**:

- `thenCombine(other, fn)` (không có `Async`): callback có thể chạy bởi thread đang hoàn tất một trong hai input, hoặc thread gọi phương thức phối hợp nếu các nguồn đã hoàn tất. **Không đảm bảo thread cụ thể**.
- `thenCombineAsync(other, fn)`: callback được thực thi bất đồng bộ bằng **default asynchronous execution facility** của stage; với `CompletableFuture` chuẩn, thông thường đó là `ForkJoinPool.commonPool()` (với quy tắc fallback của implementation khi common pool không có đủ parallelism).
- `thenCombineAsync(other, fn, executor)`: callback được gửi đến `executor` được chỉ định. Đây là cách thể hiện rõ tài nguyên thực thi khi muốn kiểm soát pool và thread.

**Async ở đây không có nghĩa hai nguồn tự chạy lại hoặc tự được chuyển sang cùng executor.** Nó chỉ điều khiển **bước ghép**. Hai nguồn có thể được tạo từ những executor khác nhau.

```java
CompletableFuture<Integer> a = CompletableFuture.completedFuture(2);
CompletableFuture<Integer> b = CompletableFuture.completedFuture(3);

CompletableFuture<Integer> c = a.thenCombineAsync(
        b,
        (x, y) -> x + y,
        combineExecutor); // Executor do ứng dụng tạo và quản lý.
```

Đây là fragment; `combineExecutor` phải là `Executor` được khởi tạo hợp lệ.

### Nên chọn overload nào?

Nếu phép ghép rất nhẹ (cộng hai số, tạo DTO, format chuỗi), overload không `Async` thường phù hợp để tránh thêm một lần scheduling. Nếu callback tốn CPU đáng kể, cần tách tải hoặc kiểm soát tài nguyên, cân nhắc `thenCombineAsync(..., executor)`. Nếu callback là I/O blocking dài, không nên mặc định dùng common pool mà không cân nhắc contention và giới hạn tải.

Lưu ý nguy cơ: overload không Async có thể khiến **thread hoàn tất input** phải làm thêm công việc ghép. Nếu callback chậm, nó làm chậm thread vốn được dùng để xử lý các tác vụ khác; với GUI/event-loop hoặc executor có số worker nhỏ, có thể gây latency hoặc reentrancy không mong muốn.

Đối với executor do ứng dụng quản lý, hãy chủ động shutdown đúng vòng đời và xử lý từ chối task. Nếu executor bị shutdown trước khi callback được nộp, stage phụ thuộc có thể hoàn tất bất thường với lỗi từ `RejectedExecutionException`.

## 7. Cách xử lý lỗi: một nguồn lỗi thì không có kết quả ghép

Hàm `BiFunction` **chỉ có thể tính toán đúng khi cả hai stage hoàn tất bình thường**. Vì thế khi một nguồn thất bại, callback không được gọi; stage phụ thuộc kết thúc bất thường. Tương tự, khi callback tự ném exception, `thenCombine` trả về một future hoàn tất bất thường.

Ví dụ Java 17 độc lập, lưu file `ThenCombineFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class ThenCombineFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> ok =
                CompletableFuture.completedFuture(10);

        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("price unavailable"));

        CompletableFuture<Integer> result =
                ok.thenCombine(failed, Integer::sum);

        try {
            System.out.println(result.join());
        } catch (CompletionException exception) {
            System.out.println(
                    "Combined failed: "
                    + exception.getCause().getClass().getSimpleName());
        }

        CompletableFuture<Integer> recovered =
                result.exceptionally(error -> -1);

        System.out.println("Recovered value: " + recovered.join());
    }
}
```

Chạy:

```bash
javac ThenCombineFailureDemo.java
java ThenCombineFailureDemo
```

Stdout:

```text
Combined failed: IllegalStateException
Recovered value: -1
```

Giải thích: `failedFuture` tạo sẵn một nguồn thất bại, nên hàm `Integer::sum` không chạy. `result.join()` ném `CompletionException`, và `getCause()` là `IllegalStateException` tương ứng trong trường hợp minh họa này. Sau đó `exceptionally` chuyển thất bại của **stage kết hợp** thành giá trị dự phòng `-1`.

`exceptionally(error -> fallback)` không sửa `result` gốc; nó tạo **stage mới**. Các phụ thuộc khác vẫn có thể quan sát lỗi của stage gốc nếu chưa gắn recovery.

### Kiểm tra lỗi bằng get() và join()

| Phương thức | Nhận kết quả | Ngoại lệ thường gặp |
| --- | --- | --- |
| `join()` | Trả `T` hoặc throw unchecked | `CompletionException` nếu stage tính toán lỗi; `CancellationException` nếu chính future bị hủy |
| `get()` | Trả `T`, khai báo checked exceptions | `ExecutionException`, `InterruptedException`, `CancellationException` |
| `get(timeout, unit)` | Chờ tối đa một hạn | Thêm `TimeoutException`; không tự cancel |

Với stage phụ thuộc vào một nguồn bị hủy, có thể thấy `CompletionException` bọc `CancellationException` thay vì `CancellationException` trực tiếp. Vì thế logic chẩn đoán nên kiểm tra nguyên nhân, không chỉ so lớp ngoại lệ của `join()`.

### Lỗi của callback

```java
CompletableFuture<Integer> badCombine =
        CompletableFuture.completedFuture(3).thenCombine(
                CompletableFuture.completedFuture(0),
                (x, divisor) -> x / divisor);
```

Đoạn này hợp lệ; `badCombine.join()` ném `CompletionException` với `ArithmeticException` là nguyên nhân. Hai nguồn đều thành công, lỗi thuộc **bước phối hợp**. Vì thế khi log, nên tách “nguồn A hỏng”, “nguồn B hỏng” và “biFunction hỏng” nếu nghiệp vụ cần chẩn đoán.

## 8. Recover trước khi ghép hay sau khi ghép?

Hai lựa chọn tạo ra hành vi khác nhau.

**Recover sau khi ghép:** một nguồn lỗi khiến toàn phép ghép thất bại, sau đó trả fallback cho **toàn bộ kết quả**.

```java
CompletableFuture<Integer> total =
        priceFuture.thenCombine(shippingFuture, Integer::sum)
                .exceptionally(error -> 0);
```

Đây là fragment; `priceFuture` và `shippingFuture` phải được khai báo. Trong ví dụ, 0 là fallback minh họa; không nên trả 0 cho hóa đơn thật khi giá không có, vì dễ che giấu lỗi nghiệp vụ.

**Recover từng nguồn trước khi ghép:** mỗi nguồn có giá trị thay thế riêng; phép ghép có thể vẫn thành công khi một nguồn lỗi.

```java
CompletableFuture<Integer> safePrice =
        priceFuture.exceptionally(error -> 100);
CompletableFuture<Integer> safeShipping =
        shippingFuture.exceptionally(error -> 0);

CompletableFuture<Integer> total =
        safePrice.thenCombine(safeShipping, Integer::sum);
```

Đây cũng là fragment. Chọn fallback phải dựa trên nghiệp vụ: phí vận chuyển lỗi không mặc nhiên bằng 0, và dữ liệu giá lỗi không nên thành giá giả nếu điều đó có thể khiến thu tiền sai. Có thể dùng `handle` để tạo một kết quả có trạng thái nguồn, ví dụ record `Success/Failure`, rồi ghép có chủ đích.

### Quan sát cả hai lỗi

`thenCombine` không phải một bộ thu thập **tất cả lỗi**. Nếu cả hai nguồn thất bại, future tổng hợp chỉ có một kết quả exceptional và không hứa sẽ chứa đầy đủ cả hai cause. Khi cần log hai lỗi riêng biệt, gắn `whenComplete` vào từng nguồn hoặc chuyển mỗi nguồn sang một giá trị kết quả có cấu trúc:

```java
CompletableFuture<Integer> a = ...;
CompletableFuture<Integer> b = ...;

a.whenComplete((value, error) -> {
    if (error != null) {
        recordFailure("A", error);
    }
});
b.whenComplete((value, error) -> {
    if (error != null) {
        recordFailure("B", error);
    }
});
```

`recordFailure` là hàm ứng dụng, vì vậy đoạn trên là fragment. `whenComplete` thiên về quan sát/side effect; lỗi ném trong callback cũng cần được kiểm soát. Không mặc định dùng `exceptionally` chỉ để log rồi vô tình thay đổi hợp đồng kết quả.

## 9. Timeout: đặt deadline cho kết quả cuối, không chỉ từng nguồn

`thenCombine` không có overload nhận timeout trực tiếp. Có thể đặt timeout cho **stage kết hợp** (Java 9+):

```java
CompletableFuture<Integer> combined =
        a.thenCombine(b, Integer::sum);

CompletableFuture<Integer> timed =
        combined.orTimeout(800, TimeUnit.MILLISECONDS);
```

Đây là fragment; `a` và `b` là `CompletableFuture<Integer>`, cần import `TimeUnit`. `orTimeout(...)` hoàn tất **chính CompletableFuture được gọi** một cách bất thường bằng `TimeoutException` nếu nó chưa xong đúng hạn, và **trả về cùng future**, không tạo bản sao độc lập. Vì thế `timed == combined` là `true` trong ví dụ này.

Khi một bên xong sớm, bên kia chậm, deadline tổng giúp caller không phải chờ vô hạn. Tuy nhiên:

- `orTimeout` **không tự cancel** các nguồn A và B; tác vụ ở phía nguồn có thể tiếp tục.
- `CompletableFuture.completeOnTimeout(value, timeout, unit)` cũng hoàn tất **chính future đó** bằng giá trị dự phòng khi tới hạn, không tự ngắt công việc gốc.
- `get(timeout, unit)` chỉ giới hạn **thời gian đợi của caller**, không thay đổi trạng thái future khi hết hạn.
- Nếu nhiều người giữ tham chiếu cùng `combined`, việc gọi `orTimeout` hoặc `completeOnTimeout` làm thay đổi ngữ nghĩa của future **chung**. Khi cần timeout chỉ cho một nhánh sử dụng, tạo stage phụ thuộc riêng rồi đặt timeout trên stage đó hoặc thiết kế lớp bọc có ownership rõ.

Một cách tổ chức thường dùng: đặt deadline request tổng, quản lý `Future` của các tác vụ nguồn nếu phải hủy chúng, và cấu hình timeout ở network/database client cho từng I/O. Chỉ timeout của CompletableFuture không tự bảo đảm các worker đã dừng/giải phóng tài nguyên.

## 10. Cancellation: kết quả tổng hợp bị hủy có hủy nguồn không?

**Không được giả định cancellation tự lan xuống các nguồn.** Với `CompletableFuture`, `cancel(boolean mayInterruptIfRunning)` tương đương hoàn tất future một cách bất thường bằng `CancellationException`; tham số `mayInterruptIfRunning` **không điều khiển interrupt** đối với implementation này.

Vì vậy:

- Hủy stage `combined` không đảm bảo task chạy `a` và `b` bị dừng.
- Hủy một nguồn có thể khiến stage phụ thuộc hoàn tất bất thường, nhưng không tự đảm bảo hủy nguồn còn lại.
- `isDone()` là true cho cả thành công, thất bại và hủy; không được coi đó là kết quả nghiệp vụ thành công.
- Việc nguồn bị hủy, future kết hợp bị hủy, callback không còn chạy và thread thực thi thực sự thoát là **những khái niệm khác nhau**.

Nếu hệ thống cần hủy cả hai tác vụ nền khi deadline hết, nên giữ các handle hủy riêng từ API thực thi nền (ví dụ `Future<?>` của `ExecutorService.submit`) và yêu cầu hủy theo chính sách. Điều đó vẫn chỉ gửi tín hiệu hợp tác: tác vụ phải hỗ trợ interruption, timeout I/O và cleanup. `CompletableFuture.supplyAsync` bản thân không đưa ra handle có khả năng interrupt task đang chạy như `FutureTask.cancel(true)`.

### Ví dụ quan sát cancellation mà không giả định tự lan

```java
CompletableFuture<Integer> a = new CompletableFuture<>();
CompletableFuture<Integer> b = new CompletableFuture<>();
CompletableFuture<Integer> both =
        a.thenCombine(b, Integer::sum);

both.cancel(true);

System.out.println(both.isCancelled()); // true
System.out.println(a.isCancelled());    // false
System.out.println(b.isCancelled());    // false
```

Đây là fragment hợp lệ khi có import `CompletableFuture`. Nó minh họa trạng thái của những future độc lập chưa hoàn thành. Không dùng `both.isCancelled()` như bằng chứng hai công việc thực đã bị ngắt.

## 11. Tránh blocking bên trong callback kết hợp

Một sai lầm là gọi `join()` của một tác vụ khác ngay trong `BiFunction`:

```java
// Phản ví dụ: task thứ ba được chờ trong callback, không phải
// phối hợp hai giá trị đã có; dễ làm nghẽn worker.
CompletableFuture<Integer> result =
        a.thenCombine(b,
                (x, y) -> x + y + thirdFuture.join());
```

Đây là fragment mô tả lỗi thiết kế. `thirdFuture` có thể được lên lịch trên chính pool ít worker đang bị callback chiếm giữ; có nguy cơ thread starvation, tăng latency hoặc deadlock theo phụ thuộc. Hãy biểu diễn phụ thuộc qua composition, chẳng hạn thêm `thenCombine` với future thứ ba sau khi đã ghép hai kết quả đầu tiên:

```java
CompletableFuture<Integer> total =
        a.thenCombine(b, Integer::sum)
         .thenCombine(thirdFuture, Integer::sum);
```

Đoạn này giả định tất cả là `CompletableFuture<Integer>` và `thirdFuture` đã được tạo. Cách này đưa quan hệ phụ thuộc vào graph, thay vì chiếm worker để block.

Nếu cần phối hợp một số lượng thay đổi theo runtime, `allOf` hoặc thiết kế thu thập kết quả dạng collection có thể phù hợp hơn so với chuỗi `thenCombine` cố định. Tuy nhiên `allOf` chỉ cho một `CompletableFuture<Void>` để đợi hoàn tất; cần đọc từng kết quả và xử lý lỗi sau đó.

## 12. Memory visibility và dữ liệu có thể thay đổi

`CompletableFuture` thực hiện công bố trạng thái hoàn tất với cơ chế đồng bộ thích hợp; code nhận kết quả sau khi stage hoàn tất có thể sử dụng dữ liệu được tạo ra trước khi hoàn tất theo hợp đồng concurrent của API. Tuy nhiên, điều đó **không khiến mọi object mutable được chia sẻ giữa các nguồn trở nên thread-safe**.

Ví dụ không nên để hai nguồn cùng sửa một `HashMap` thường mà không khóa. Dù bước `thenCombine` chỉ chạy sau khi hai nguồn thành công, data race giữa hai nguồn **đã xảy ra trước đó**.

Tốt hơn là để mỗi nguồn trả một kết quả độc lập/immutable, và hàm `BiFunction` kết hợp các giá trị:

```java
record Money(long cents) {}

CompletableFuture<Money> merchandise = ...;
CompletableFuture<Money> delivery = ...;

CompletableFuture<Money> payable =
        merchandise.thenCombine(
                delivery,
                (m, d) -> new Money(m.cents() + d.cents()));
```

Đây là fragment; `Money` là record Java 17 và hai stage do ứng dụng khởi tạo. Cần xử lý số tiền/currency/overflow theo nghiệp vụ thực; code chỉ minh họa cách kết hợp immutable result.

Hàm phối hợp nên **thuần và ngắn** nếu có thể: đầu vào như nhau → kết quả như nhau, không sửa state dùng chung, không gọi I/O hoặc lock chồng chéo. Khi cần I/O, cân nhắc tách bước xử lý với executor thích hợp.

## 13. Tốc độ thực tế: song song không tự động nhanh hơn

Nếu hai tác vụ độc lập mất lần lượt \(T_A\) và \(T_B\):

- Chạy tuần tự có chi phí xấp xỉ \(T_A + T_B\).
- Nếu có đủ tài nguyên và không tranh chấp, chạy song song có thể tiến gần \(max(T_A, T_B)\) cộng overhead lập lịch và ghép.
- Nếu chỉ có một worker, cả hai vẫn có thể nối tiếp trên queue và tổng thời gian không giảm.
- Nếu cùng tranh I/O, CPU, lock hoặc băng thông bộ nhớ, song song có thể còn **chậm hơn**.

Không đưa phép đo `System.nanoTime()` vào callback rồi giả định chỉ số đó đại diện latency toàn request. Hãy đo từ lúc tạo/giao các nguồn tới lúc stage cuối hoàn tất, gồm queuing và overhead; kiểm tra throughput, p95/p99, pool saturation, exception và timeout.

`thenCombineAsync` thêm bước scheduling callback; nó hữu ích khi cần tách tải, nhưng với callback chỉ cộng hai số, overhead có thể lớn hơn công việc. Tối ưu hóa dựa trên benchmark của workload thật, không coi `Async` là lời hứa chạy nhanh hơn.

## 14. Ví dụ Java 17: tổng hợp hai nguồn có timeout và recovery

Ví dụ tiếp theo có chủ đích dùng hai future đã hoàn tất và tạo một future bất thường để minh họa policy khi một nguồn lỗi. Không dựa vào `sleep()` hay thời điểm scheduler, nên kết quả ổn định.

Lưu file `ThenCombineRecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ThenCombineRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> price =
                CompletableFuture.completedFuture(500);

        CompletableFuture<Integer> shippingError =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("shipping unavailable"));

        CompletableFuture<Integer> strict =
                price.thenCombine(shippingError, Integer::sum);

        CompletableFuture<String> strictMessage =
                strict.handle((value, error) ->
                        error == null ? "Strict: " + value
                                      : "Strict: failed");

        CompletableFuture<Integer> fallbackShipping =
                shippingError.exceptionally(error -> 30);

        CompletableFuture<Integer> fallbackTotal =
                price.thenCombine(fallbackShipping, Integer::sum);

        System.out.println(strictMessage.join());
        System.out.println("Fallback total: " + fallbackTotal.join());
        System.out.println("Original shipping failed: "
                + shippingError.isCompletedExceptionally());
    }
}
```

Chạy:

```bash
javac ThenCombineRecoveryDemo.java
java ThenCombineRecoveryDemo
```

Stdout:

```text
Strict: failed
Fallback total: 530
Original shipping failed: true
```

Hai chính sách khác nhau:

- `strict` giữ ngữ nghĩa “không có đủ hai nguồn thành công thì không có kết quả tổng”. `handle` biến kết quả cuối thành thông điệp phục vụ demo.
- `fallbackShipping` tạo **future mới** thành công bằng giá trị thay thế 30; `price.thenCombine(fallbackShipping, ...)` sau đó trả 530.
- `shippingError` gốc **vẫn thất bại**. Việc recover trên một nhánh không thay đổi lỗi gốc cho các nhánh khác.

Ở ứng dụng thật, giá trị 30 phải là fallback có cơ sở nghiệp vụ; nếu phí vận chuyển không xác định, cách an toàn hơn có thể là báo lỗi hoặc trả trạng thái “chưa thể tính tổng” thay vì tự điền phí.

## 15. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Cho rằng `thenCombine` tự khởi động hai nguồn | Nó chỉ nối hai `CompletionStage` đã có | Tạo/lập lịch hai nguồn độc lập trước |
| Nhầm `thenCombine` với `thenCompose` | Compose dùng khi bước sau phụ thuộc kết quả bước trước | Kết hợp hai nguồn độc lập bằng combine |
| Dùng `join()` lần lượt từng future trước khi tạo graph | Block thread điều phối, che mất lợi ích phối hợp bất đồng bộ | Xây dựng pipeline rồi `join/get` ở ranh giới cần kết quả |
| Cho rằng callback luôn chạy trên worker riêng | Bản không Async có thể chạy trên thread hoàn tất nguồn/caller | Nếu cần định rõ tài nguyên, dùng `thenCombineAsync(..., executor)` |
| Cho rằng `thenCombineAsync` làm hai nguồn song song | Async chỉ điều phối callback kết hợp | Thiết kế executor/source concurrency độc lập |
| Cho rằng một nguồn lỗi luôn khiến kết quả fail-fast ngay | Completion của dependent trong mô hình “both” không phải cơ chế race fail-fast | Có deadline tổng và xử lý failure/cancellation |
| Cho rằng callback nhận cả exception để ghép | `BiFunction` chỉ nhận hai **giá trị thành công** | Dùng `handle`, `exceptionally`, `whenComplete` theo nhu cầu |
| Bỏ qua việc null là kết quả thành công | Callback có thể ném NPE | Xác thực null hoặc dùng kiểu kết quả tường minh |
| Coi `join()` và `get()` ném cùng loại lỗi | `join` thường ném unchecked CompletionException, `get` ném ExecutionException | Phân biệt contract |
| Dùng `orTimeout` rồi cho rằng A/B bị dừng | Timeout stage không tự hủy các nguồn | Quản lý task và deadline I/O riêng |
| Gọi `cancel(true)` trên CompletableFuture và đợi thread bị interrupt | `mayInterruptIfRunning` không có tác dụng interrupt trong implementation này | Dùng handle thực thi riêng khi cần yêu cầu hủy |
| Cho rằng cancel combined tự cancel cả A/B | Cancellation không có bảo đảm tự lan xuống nguồn | Định nghĩa ownership và cancellation propagation |
| Đưa I/O blocking vào `BiFunction` trên common pool | Có thể giữ worker lâu và tăng contention | Dùng executor thích hợp, timeout và callback ngắn |
| Các nguồn cùng sửa một object mutable không khóa | Data race xảy ra trước bước combine | Trả kết quả độc lập/immutable rồi kết hợp |
| Recover bằng giá trị mặc định không hợp lệ | Có thể che lỗi nghiệp vụ | Fallback có hợp đồng hoặc result type nêu rõ thiếu dữ liệu |

## 16. Checklist áp dụng thenCombine trong dự án

1. **Hai nguồn độc lập thật không?** Nếu B cần A mới bắt đầu, dùng `thenCompose` thay vì `thenCombine`.
2. **Có phải cần cả hai thành công?** Nếu không, xem xét recovery từng nguồn trước khi ghép hoặc mô hình result envelope.
3. **Đúng kiểu dữ liệu không?** `T` và `U` có thể khác; chọn `V` là kiểu kết quả nghiệp vụ.
4. **Ai sở hữu executor?** Xác định nguồn sử dụng pool nào và callback kết hợp có cần executor riêng hay không.
5. **Hàm phối hợp có thuần/ngắn không?** Tránh blocking, chia sẻ mutable state, lock kéo dài và side effect khó rollback.
6. **Deadline tổng là bao lâu?** Phân biệt `get(timeout)` với `orTimeout/completeOnTimeout`, chú ý hai phương thức sau thay đổi chính future được gọi.
7. **Một nguồn lỗi thì sao?** Quyết định strict failure, fallback riêng từng nguồn hay báo partial result.
8. **Có cần thu đủ các lỗi?** Ghi nhận tại từng nguồn, đừng trông chờ future kết hợp chứa toàn bộ causes.
9. **Nếu user hủy request?** Cancellation của CompletableFuture không bảo đảm dừng các tác vụ đã giao; quản lý tín hiệu hủy và cleanup riêng.
10. **Kiểm thử thứ tự hoàn tất:** thử A xong trước, B xong trước, A lỗi, B lỗi, cả hai lỗi, callback ném lỗi, giá trị null, timeout/cancel.
11. **Đo hiệu năng thật:** kiểm tra cả thời gian chờ nguồn, callback, queue và latency end-to-end, không mặc định `Async` nhanh hơn.
12. **Giữ phạm vi Java chuẩn:** không cần framework để hiểu hợp đồng thenCombine/CompletionStage.

## 17. Câu hỏi tự kiểm tra

**1. `thenCombine` chạy khi một trong hai future thành công hay khi cả hai cùng thành công?**  
Chỉ khi **cả hai** hoàn tất thành công, nó mới gọi `BiFunction` để tạo kết quả.

**2. Nếu B hoàn tất trước A thì tham số đầu của `BiFunction` có trở thành giá trị B không?**  
Không. Trong `a.thenCombine(b, (x, y) -> ...)`, `x` luôn là giá trị A, `y` luôn là giá trị B.

**3. `thenCombineAsync` có tự đưa task A và B sang executor cung cấp trong overload ba tham số không?**  
Không. Executor đó điều phối **callback kết hợp**; nơi A/B chạy do cách tạo các stage nguồn quyết định.

**4. Khi nào chọn `thenCompose` thay vì `thenCombine`?**  
Khi tác vụ kế tiếp phải dùng kết quả bước trước để **tạo stage bất đồng bộ mới**, ví dụ có user ID rồi mới truy vấn quyền của user.

**5. Nếu một nguồn thất bại, `BiFunction` có được gọi với exception như tham số không?**  
Không. Nó không được gọi khi hai nguồn không thành công; recovery và error handling dùng stage khác.

**6. `exceptionally` gắn vào combined có sửa hai nguồn ban đầu không?**  
Không. Nó tạo stage phục hồi riêng dựa trên kết quả exceptional của combined.

**7. `combined.orTimeout(...)` có tạo CompletableFuture mới không?**  
Không. Nó trả cùng `combined` và có thể hoàn tất chính đối tượng đó bất thường khi hết hạn.

**8. Hủy combined có đảm bảo interrupt hai task đã chạy bằng `supplyAsync` không?**  
Không. CompletableFuture cancellation không tự bảo đảm interrupt/cancel các nguồn.

**9. Khi cần chờ nhiều hơn hai nguồn, có thể nối nhiều thenCombine không?**  
Có với số lượng nhỏ và kiểu rõ ràng. Với tập nguồn động, cân nhắc `allOf` và cơ chế tổng hợp phù hợp.

**10. Với callback chỉ cộng hai số, có phải dùng `thenCombineAsync` luôn tốt hơn?**  
Không. Scheduling bổ sung có overhead; `thenCombine` thường đơn giản hơn nếu callback nhẹ và không cần kiểm soát thread riêng.

## Tài liệu tham khảo

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
