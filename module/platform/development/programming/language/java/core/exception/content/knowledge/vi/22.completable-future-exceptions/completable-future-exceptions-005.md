# CompletableFuture.exceptionally: phục hồi bằng một kết quả

Trong Java, một `CompletableFuture<T>` có thể **hoàn thành bình thường** với giá trị kiểu `T`, hoặc **hoàn thành bất thường** (*exceptional completion*) với một nguyên nhân lỗi. Phương thức `exceptionally` cho phép đăng ký một hàm xử lý nhánh lỗi và **biến nhánh lỗi ấy thành một giá trị thay thế**. Nếu việc phục hồi thành công, stage do `exceptionally` trả về hoàn thành bình thường với giá trị fallback.

Đây là một công cụ quan trọng để xây dựng luồng bất đồng bộ dễ đọc: thay vì để mọi sự cố đều tràn tới điểm `join()` hoặc `get()`, ứng dụng có thể quyết định một lỗi cụ thể có thể được chuyển thành **kết quả có nghĩa**. Tuy nhiên, cần phân biệt **phục hồi để tiếp tục** với **chỉ ghi nhận lỗi**, **thử lại tác vụ** hoặc **che giấu một lỗi nghiêm trọng**.

Bài thuộc chủ đề *Java core - exception*, trong nhóm `CompletableFuture`. Các ví dụ sử dụng Java 17 trở lên, không cần thư viện bên ngoài.

## 1. Cơ chế nền tảng: hoàn thành bình thường và hoàn thành bất thường

Một `CompletableFuture` là đối tượng đại diện cho một kết quả có thể xuất hiện sau này. Nó có thể ở trạng thái chưa hoàn thành, hoàn thành bình thường hoặc hoàn thành exceptional. Ví dụ:

```java
CompletableFuture<Integer> success =
        CompletableFuture.completedFuture(100);

CompletableFuture<Integer> failure =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));
```

Đây là **mảnh minh họa**, cần import `java.util.concurrent.CompletableFuture` khi đặt vào một chương trình Java. Hai factory method trên lần lượt tạo future đã hoàn thành với `100` và future đã hoàn thành bất thường với `IllegalStateException`.

Với một chuỗi xử lý:

```text
Đọc dữ liệu → Biến đổi → Kiểm tra → Trả về
       |           |          |
       +-----------+----------+---- có thể lỗi
                                      |
                                      v
                                exceptionally
                                      |
                                      v
                             giá trị fallback kiểu T
                                      |
                                      v
                              stage tiếp tục bình thường
```

`exceptionally` chỉ chạy khi **stage ngay trước nó hoàn thành bất thường**. Nếu stage trước thành công, `exceptionally` chuyển tiếp giá trị thành công và **không gọi hàm xử lý lỗi**.

Điều này cũng cho thấy vì sao **vị trí đặt `exceptionally` trong chuỗi** quan trọng. Nó chỉ có thể phục hồi lỗi của các stage ở phía **trước** nó, không tự động bắt lỗi phát sinh trong các stage đặt **sau** nó.

## 2. Chữ ký API và kiểu dữ liệu

Trong `CompletionStage<T>`, ý nghĩa chính của phương thức là:

```java
CompletionStage<T> exceptionally(
        Function<Throwable, ? extends T> fn);
```

Đây là chữ ký rút gọn để giải thích kiểu, không phải khai báo lớp độc lập; kiểu `Function` thuộc `java.util.function`. Trên `CompletableFuture<T>`, phương thức trả về `CompletableFuture<T>`.

Đối số `fn` là hàm nhận một `Throwable` đại diện cho thất bại của stage nguồn, rồi trả về một **giá trị tương thích kiểu `T`**. Ví dụ, nếu stage có kiểu `CompletableFuture<Integer>`, hàm phục hồi phải trả giá trị kiểu `Integer` hoặc tương thích; không thể trả một chuỗi tùy ý.

```java
CompletableFuture<Integer> safe = source.exceptionally(error -> 0);
```

Đây là snippet giả định `source` có kiểu `CompletableFuture<Integer>`. Khi `source` lỗi, `safe` có thể hoàn thành bình thường với `0`. Khi `source` thành công với `42`, `safe` nhận `42` và lambda không chạy.

Cần phân biệt hai đối tượng:

- **`source`:** stage gốc, giữ nguyên trạng thái thành công hoặc thất bại của nó.
- **`safe`:** stage phụ thuộc **mới** được `exceptionally` trả về; stage này có thể hoàn thành bình thường nhờ giá trị fallback.

`exceptionally` **không sửa trạng thái đã hoàn thành của stage gốc**. Nó tạo một nhánh kết quả mới. Nếu giữ cả hai reference, code khác vẫn có thể quan sát lỗi trên `source` trong khi code dùng `safe` đã nhận fallback.

## 3. Ví dụ Java 17 chạy độc lập: phục hồi về giá trị mặc định

Tạo file `ExceptionallyDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ExceptionallyDemo {

    private static CompletableFuture<Integer> loadPrice(boolean fail) {
        if (fail) {
            return CompletableFuture.failedFuture(
                    new IllegalStateException("service unavailable"));
        }
        return CompletableFuture.completedFuture(120);
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> failed = loadPrice(true);

        CompletableFuture<Integer> recovered = failed.exceptionally(error -> {
            System.out.println("recover: " + error.getClass().getSimpleName());
            return 0;
        });

        System.out.println("result: " + recovered.join());
        System.out.println("source failed: " + failed.isCompletedExceptionally());
        System.out.println("recovered failed: "
                + recovered.isCompletedExceptionally());

        CompletableFuture<Integer> success = loadPrice(false);
        CompletableFuture<Integer> untouched = success.exceptionally(error -> {
            System.out.println("should not run");
            return -1;
        });

        System.out.println("success: " + untouched.join());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ExceptionallyDemo.java
java ExceptionallyDemo
```

Stdout chính xác:

```text
recover: IllegalStateException
result: 0
source failed: true
recovered failed: false
success: 120
```

Phân tích từng dòng:

1. `loadPrice(true)` tạo một future đã failed với `IllegalStateException`.
2. `failed.exceptionally(...)` thấy stage nguồn đã exceptional, nên gọi lambda và nhận giá trị `0`.
3. `recovered.join()` trả `0` bình thường vì **stage phục hồi đã thành công**.
4. `failed.isCompletedExceptionally()` vẫn là `true`; `exceptionally` không xóa lỗi khỏi nguồn.
5. `recovered.isCompletedExceptionally()` là `false` vì lambda đã trả về một giá trị.
6. `loadPrice(false)` đã thành công với `120`; lambda trong `exceptionally` của nhánh này không chạy, vì thế không có dòng `should not run`.

Ví dụ dùng các future đã hoàn thành sẵn nên không có sự không chắc chắn do lập lịch luồng, và output có thứ tự xác định.

## 4. exceptionally có thể phục hồi những lỗi nào?

`exceptionally` kích hoạt khi stage nguồn hoàn thành exceptional; nó không chỉ bắt một loại exception cụ thể. Những tình huống có thể dẫn đến exceptional completion gồm:

- Supplier hoặc function ở upstream ném `RuntimeException` hay một `Throwable` khác.
- Upstream được hoàn thành bằng `completeExceptionally(cause)` hoặc `failedFuture(cause)`.
- Một stage phụ thuộc kế thừa trạng thái lỗi từ stage trước đó.
- Một `CompletableFuture` bị hủy, vì cancellation được phản ánh như exceptional completion.
- Upstream được làm cho hoàn thành exceptional bởi cơ chế timeout như `orTimeout`.

Tham số mà hàm phục hồi nhận là `Throwable`. Tùy cách upstream được hoàn thành và cách stage được tạo, nó có thể là exception gốc hoặc một lớp bao như `CompletionException`. **Không nên mặc định `error.getClass()` luôn đúng bằng kiểu exception ném trong lambda nguồn**.

Ví dụ:

```java
CompletableFuture<String> pipeline =
        CompletableFuture.completedFuture("abc")
                .thenApply(value -> {
                    throw new IllegalArgumentException("bad transform");
                })
                .exceptionally(error -> "fallback");
```

Đây là snippet có thể đặt trong một phương thức với import phù hợp. `exceptionally` nhận lỗi của stage `thenApply` và có thể trả `"fallback"`. Nếu logic cần phân loại exception nghiệp vụ, cần làm rõ hình dạng wrapper của chuỗi trước khi kiểm tra cause.

**Lưu ý:** lỗi do `NullPointerException` hoặc bug ở upstream có thể kích hoạt `exceptionally`; điều đó **không có nghĩa mọi lỗi đều thích hợp để chuyển thành giá trị bình thường**. Thường chỉ nên phục hồi những lỗi mà nghiệp vụ đã xác định trước là có thể chấp nhận fallback.

## 5. Phục hồi có chọn lọc, tránh che lỗi lập trình

Không nên dùng một giá trị fallback bất kể nguyên nhân khi hậu quả của lỗi không giống nhau.

Ví dụ: tính giá bán khuyến nghị có thể dùng giá cache khi dịch vụ giá tạm thời không khả dụng. Nhưng nếu code vừa lỗi vì dữ liệu bị sai định dạng nghiêm trọng, tự ý trả giá `0` có thể dẫn đến giao dịch sai.

Một hướng xử lý là phân loại exception:

```java
CompletableFuture<Integer> safe = upstream.exceptionally(error -> {
    Throwable cause = unwrapCompletion(error);

    if (cause instanceof PriceServiceUnavailableException) {
        return cachedPrice;
    }

    throw new CompletionException(cause);
});
```

Đây là **mảnh minh họa chưa độc lập**: `upstream`, `cachedPrice`, `unwrapCompletion` và `PriceServiceUnavailableException` là thành phần giả định; cần import `CompletionException`. Với lỗi đúng chính sách, hàm trả fallback. Với lỗi còn lại, nó **ném** exception để stage phục hồi tiếp tục exceptional; việc không có fallback là một quyết định đúng đắn.

Khi muốn giữ nguyên phân loại lỗi, đừng bọc thành một `RuntimeException("failed")` không có cause. Nếu phải chuyển sang abstraction lỗi khác, hãy giữ `cause` và tài liệu hóa hợp đồng công khai.

### Bóc lớp bao có kiểm soát

Trong code cần đọc nguyên nhân phía sau `CompletionException` và `ExecutionException`, có thể dùng helper:

```java
static Throwable unwrapCompletion(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là phương thức minh họa, cần import `CompletionException` và `ExecutionException` và phải đặt trong class. Chỉ bóc những wrapper mà tầng xử lý thực sự hiểu; **đừng xóa sạch mọi lớp cause**, vì một cause có thể biểu diễn ranh giới quan trọng của ứng dụng. Khi truyền lại lỗi, vẫn giữ thông tin nguyên nhân để chẩn đoán.

Trong nhiều trường hợp, thiết kế tốt hơn là upstream đã chuyển lỗi vendor thành **kiểu lỗi ổn định của ứng dụng** trước khi đến `exceptionally`.

## 6. Phân biệt exceptionally, handle và whenComplete

Ba phương thức này thường bị nhầm vì đều có thể nhìn thấy lỗi.

| Phương thức | Khi upstream thành công | Khi upstream thất bại | Mục đích chính |
| --- | --- | --- | --- |
| `exceptionally(error -> fallback)` | Chuyển tiếp giá trị; không gọi hàm | Gọi hàm và có thể biến lỗi thành giá trị kiểu `T` | **Phục hồi riêng nhánh lỗi** bằng giá trị cùng kiểu |
| `handle((value, error) -> result)` | Hàm được gọi với giá trị và lỗi thường là `null` | Hàm được gọi với lỗi và giá trị thường là `null` | **Biến đổi cả hai nhánh**, có thể đổi kiểu kết quả |
| `whenComplete((value, error) -> ...)` | Callback quan sát kết quả | Callback quan sát lỗi | **Quan sát/ghi nhận tác dụng phụ**, thường giữ nguyên outcome |

`handle` có thể trả về một kiểu mới `U`, hữu ích khi muốn biến lỗi thành một đối tượng báo cáo hoặc kết quả mang trạng thái:

```java
CompletableFuture<String> labeled = source.handle((value, error) -> {
    if (error != null) {
        return "FAILED";
    }
    return "VALUE=" + value;
});
```

Đây là snippet minh họa, giả định `source` là `CompletableFuture<Integer>`. Kết quả `labeled` có kiểu `CompletableFuture<String>`; trong khi `exceptionally` giữ cùng kiểu giá trị như nguồn.

`whenComplete` thường được dùng để log:

```java
CompletableFuture<Integer> observed =
        source.whenComplete((value, error) -> {
            if (error != null) {
                logFailure(error);
            }
        });
```

Đây là snippet minh họa, `logFailure` do ứng dụng định nghĩa. Nếu nguồn failed và callback `whenComplete` hoàn tất bình thường, `observed` **vẫn failed**; nó không biến lỗi thành một giá trị fallback. Nếu callback cũng ném exception, cách ưu tiên lỗi tuân theo hợp đồng của `whenComplete`; đừng dùng callback logging có thể ném bừa.

Nếu muốn vừa ghi nhận lỗi vừa trả fallback, có thể làm theo thứ tự:

```java
CompletableFuture<Integer> safe = source
        .whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        })
        .exceptionally(error -> 0);
```

Các ký hiệu `source` và `recordFailure` cần được khai báo ở nơi khác. Cách này hợp lý khi logging không làm thay đổi định nghĩa lỗi hoặc khi đã có xử lý phù hợp cho lỗi logging.

## 7. Ví dụ Java 17: so sánh ba thao tác bằng kết quả xác định

Tạo `RecoveryMethodsDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryMethodsDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("unavailable"));

        CompletableFuture<Integer> observed =
                failed.whenComplete((value, error) -> {
                    System.out.println("whenComplete observed: " + (error != null));
                });

        CompletableFuture<Integer> recovered =
                failed.exceptionally(error -> 10);

        CompletableFuture<String> mapped =
                failed.handle((value, error) ->
                        error == null ? "OK=" + value : "FAILED");

        try {
            observed.join();
        } catch (CompletionException ex) {
            System.out.println("observed still failed");
        }

        System.out.println("exceptionally: " + recovered.join());
        System.out.println("handle: " + mapped.join());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 RecoveryMethodsDemo.java
java RecoveryMethodsDemo
```

Stdout:

```text
whenComplete observed: true
observed still failed
exceptionally: 10
handle: FAILED
```

Tại sao đúng?

- `failed` đã completed exceptionally, nên `whenComplete` được gọi và in `true`.
- `observed.join()` vẫn báo lỗi bằng `CompletionException` vì `whenComplete` không thay kết quả lỗi khi callback hoàn tất bình thường.
- `exceptionally` biến lỗi thành `Integer 10`.
- `handle` tạo ra `String "FAILED"`, minh họa khả năng đổi kiểu.
- Dùng `failedFuture` để loại bỏ ảnh hưởng lập lịch của executor và dễ kiểm chứng output.

Không cần sử dụng đồng thời cả ba trong mọi pipeline. Chọn theo mục đích: **phục hồi lỗi**, **biến đổi hai nhánh** hoặc **quan sát mà giữ outcome**.

## 8. Vị trí đặt exceptionally quyết định vùng lỗi có thể phục hồi

Xét hai chuỗi:

**Phục hồi trước, rồi biến đổi:**

```java
CompletableFuture<Integer> value = upstream
        .exceptionally(error -> 0)
        .thenApply(x -> 100 / x);
```

Nếu upstream lỗi, `exceptionally` trả `0`. Stage `thenApply` tiếp theo ném `ArithmeticException` vì phép chia cho 0. `exceptionally` đã chạy trước đó **không quay lại bắt lỗi mới** này. Chuỗi kết quả vẫn exceptional.

**Biến đổi trước, rồi phục hồi:**

```java
CompletableFuture<Integer> value = upstream
        .thenApply(x -> 100 / x)
        .exceptionally(error -> 0);
```

Ở đây `exceptionally` nằm **sau** phép chia; nó có thể trả `0` khi upstream failed hoặc `thenApply` ném. Tuy nhiên, cách bắt rộng như vậy có thể che lỗi lập trình, nên cần phân loại nguyên nhân để tránh biến chia cho 0 thành kết quả hợp lệ sai nghiệp vụ.

Hai snippet chỉ minh họa cấu trúc, giả định `upstream` có kiểu `CompletableFuture<Integer>`. Điều cần nhớ: đặt recovery ở **ranh giới mà bạn muốn chuyển lỗi thành kết quả**, và tránh bao phủ nhiều stage hơn chính sách cho phép.

### Khi một stage thành công, exceptionally không chạy

```java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture(5)
                .thenApply(x -> x * 2)
                .exceptionally(error -> -1);

// result.join() == 10, hàm phục hồi không được gọi.
```

`exceptionally` không dùng để chuẩn hóa giá trị thành công. Đối với giá trị thành công, dùng `thenApply`; đối với cả hai nhánh, dùng `handle`.

## 9. Nếu hàm phục hồi tự ném exception thì sao?

`exceptionally` là **hàm ứng dụng**, nên nó cũng có thể thất bại. Nếu callback phục hồi ném exception, stage mới hoàn thành exceptional; không có giá trị fallback. Điều này là bình thường và có thể được dùng để **từ chối phục hồi** đối với lỗi không thuộc chính sách.

Tạo `RecoveryFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class RecoveryFailureDemo {

    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.failedFuture(
                        new IllegalStateException("upstream failed"));

        CompletableFuture<Integer> recovered = source.exceptionally(error -> {
            throw new IllegalArgumentException("fallback failed", error);
        });

        try {
            recovered.join();
        } catch (CompletionException ex) {
            Throwable cause = ex.getCause();
            System.out.println(cause.getClass().getSimpleName());
            System.out.println(cause.getMessage());
            System.out.println(cause.getCause().getClass().getSimpleName());
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 RecoveryFailureDemo.java
java RecoveryFailureDemo
```

Stdout:

```text
IllegalArgumentException
fallback failed
IllegalStateException
```

`recovered` thất bại bằng `IllegalArgumentException("fallback failed")`, trong khi nguyên nhân gốc vẫn được giữ làm `cause`. Khi `join()` được gọi, exception của stage xuất hiện qua `CompletionException`. Phần in ở đây dùng `getCause()` để lấy lỗi ứng dụng, sau đó lấy `getCause()` tiếp theo để kiểm tra lỗi upstream.

Một ví dụ thực tế là fallback cache cũng lỗi. Nếu trả dữ liệu dự phòng không thành công, cần truyền lỗi mới có ngữ cảnh và giữ nguyên nhân liên quan để hệ thống phân biệt nguồn lỗi; không mặc định in lỗi và trả `null` để tiếp tục như thể thành công.

## 10. Giá trị fallback phải đúng nghĩa nghiệp vụ

Không phải mọi `T` đều có một giá trị fallback an toàn.

Ví dụ:

| Loại tác vụ | Fallback có thể hợp lý | Fallback dễ gây lỗi nghiệp vụ |
| --- | --- | --- |
| Lấy cấu hình UI tùy chọn | Cấu hình mặc định đã được kiểm duyệt | Một đối tượng thiếu trường bắt buộc |
| Gợi ý sản phẩm không thiết yếu | Danh sách trống, đồng thời ghi nhận dịch vụ gợi ý unavailable | Danh sách giả mạo là kết quả cá nhân hóa chính xác |
| Lấy giá trị metric trang dashboard | Giá trị dự phòng được gắn nhãn `stale` | Tự biến mọi giá trị lỗi thành `0`, khiến người đọc nghĩ không có hoạt động |
| Đọc báo cáo từ cache | Dữ liệu cache còn trong ngưỡng chấp nhận | Dữ liệu quá cũ nhưng được xem là dữ liệu mới |
| Xử lý thanh toán hoặc giao dịch tài chính | Thường cần kết quả failed/pending có cấu trúc | Trả `true` hoặc `SUCCESS` khi giao dịch thực sự chưa xác minh |
| Đăng nhập/ủy quyền | Thường thất bại an toàn và báo lỗi phù hợp | Tự cho phép truy cập khi hệ thống xác thực không khả dụng |

`exceptionally(error -> null)` được cho phép khi kiểu `T` là kiểu tham chiếu. Khi đó future phục hồi **hoàn thành bình thường với `null`**, nhưng các stage phía sau có thể ném `NullPointerException`. `null` chỉ là fallback hợp lệ nếu contract nêu rõ và mọi consumer biết xử lý.

Với collection, `List.of()` có thể là fallback tốt khi “không có gợi ý” là ý nghĩa được chấp nhận. Nếu “không có dữ liệu” khác với “dịch vụ gợi ý đang lỗi”, hãy dùng một kiểu kết quả biểu diễn hai trạng thái hoặc kèm metadata; việc trả list rỗng làm mất dấu hiệu lỗi có thể gây quyết định sai.

### Recovery không phải retry

`exceptionally` **không tự gọi lại supplier hoặc phép I/O đã thất bại**. Callback chỉ chạy khi stage nguồn exceptional và nhận `Throwable` để tính fallback. Nếu nghiệp vụ cần retry, phải chủ động thiết kế lịch thử lại, số lần, backoff, timeout và tính idempotent.

Đừng viết:

```java
return serviceCall()
        .exceptionally(error -> serviceCall().join());
```

Đây là snippet minh họa một mẫu **dễ gây vấn đề**: `serviceCall` giả định trả `CompletableFuture<T>`. Việc gọi `join()` bên trong handler có thể chặn thread đang chạy callback, gây nghẽn executor hoặc deadlock trong cấu hình thiếu worker. Nó cũng có thể lặp side effect nếu lần gọi đầu đã xử lý một phần.

Một chiến lược retry async đúng thường dùng composition (`thenCompose`/`exceptionallyCompose` khi phù hợp với JDK và contract), giới hạn lần thử, deadline và giám sát từng attempt. Nếu chỉ muốn **giá trị dự phòng đã có sẵn**, `exceptionally` là lựa chọn gọn hơn.

## 11. exceptionally có chạy trên một thread riêng không?

Không nên giả định lambda trong `exceptionally` luôn chạy bất đồng bộ hoặc luôn chạy trên một pool riêng.

Khi stage nguồn đã hoàn thành trước lúc đăng ký, việc xử lý dependent stage có thể diễn ra ngay trên thread gọi method. Khi nguồn hoàn thành sau, callback có thể chạy trong thread thực hiện việc completion hoặc theo cơ chế thực thi của implementation.

Vì vậy:

- Không dùng `exceptionally` không async để làm một phép đọc mạng blocking lâu hoặc truy vấn database lớn.
- Không giả định bên trong callback luôn được phép truy cập UI thread, request context hoặc thread-local state của caller.
- Nếu recovery thật sự là một công việc bất đồng bộ, chọn API phục hồi/composition async phù hợp (ví dụ `exceptionallyCompose` và biến thể async trong các JDK hỗ trợ), cùng executor quản lý rõ ràng.
- Với stage nguồn đã hoàn thành, callback có thể chạy trước khi dòng code ngay sau `exceptionally` được thực thi; đừng dựa vào thời điểm callback vì logic nghiệp vụ.

`CompletableFuture` trên Java 17 cung cấp các phương thức recovery async thích hợp trong nhóm `exceptionallyAsync`/`exceptionallyCompose`. Dù vậy, việc chọn executor phải dựa vào đặc tính workload (CPU/I/O), policy timeout và vòng đời executor. Tạo executor vô hạn cho mỗi recovery là thiết kế không tốt.

### Ví dụ về logging và context

`ThreadLocal` có thể không có giá trị như mong đợi khi callback chạy trên thread khác. Nếu phải ghi correlation ID, tenant hay request ID, hãy truyền các giá trị cần thiết như dữ liệu bất biến vào closure hoặc qua cơ chế context propagation được quản lý; tránh lấy ngầm toàn bộ context từ một thread khác rồi kết luận đó là request ban đầu.

## 12. exceptionally và cancellation

Một `CompletableFuture` bị cancel được xem là completed exceptionally; bởi vậy `exceptionally` có thể quan sát một `CancellationException` và **trả fallback**:

```java
CompletableFuture<String> original = new CompletableFuture<>();
original.cancel(false);

CompletableFuture<String> fallback =
        original.exceptionally(error -> "cancelled-fallback");
```

Đây là snippet với import `CompletableFuture` phù hợp. `original` vẫn canceled, nhưng `fallback` có thể hoàn thành bình thường với `"cancelled-fallback"`. Điều này hợp lệ về API song có thể **không phù hợp** với ý định dừng của caller.

Nếu cancellation là tín hiệu cần được bảo tồn, nên phân loại rõ:

```java
CompletableFuture<String> safe = original.exceptionally(error -> {
    if (error instanceof CancellationException) {
        throw (CancellationException) error;
    }
    return "fallback";
});
```

Đây là snippet minh họa, cần import `CancellationException` và `original`. Với một chuỗi stage có thể có `CompletionException` bọc cause, việc phân loại hủy thực tế cần tuân theo hình dạng lỗi tại boundary.

Không tự biến mọi cancellation thành dữ liệu thành công khi tầng điều phối đang dựa vào trạng thái hủy để ngừng workflow. Ngược lại, nếu UI chỉ muốn một thông điệp “đã hủy” cho một hoạt động tùy chọn, biểu diễn nó thành kết quả domain rõ ràng có thể phù hợp hơn một chuỗi fallback dễ nhầm với dữ liệu thật.

Cần nhớ `CompletableFuture.cancel(true)` không có nghĩa một worker bên dưới chắc chắn bị interrupt theo cách `FutureTask.cancel(true)` có thể yêu cầu. Cancellation của future và việc dừng thực tế của tác vụ là hai trách nhiệm cần xem xét riêng.

## 13. Timeout và nguồn lỗi

Có hai tình huống “timeout” dễ nhầm:

1. `future.get(timeout, unit)` có thể ném `TimeoutException` **ngay tại thread đang chờ** vì caller không muốn chờ thêm. Điều này **không tự tạo exceptional completion** cho `future` nên `future.exceptionally(...)` không tự chạy chỉ vì lời gọi `get(timeout)` hết hạn.
2. `future.orTimeout(timeout, unit)` sắp đặt để chính `CompletableFuture` hoàn thành exceptional bằng `TimeoutException` nếu đến hạn mà chưa hoàn thành. Khi đó `exceptionally` gắn sau `orTimeout` có thể chạy và trả fallback.

Lưu ý `orTimeout` **thay đổi chính CompletableFuture** được gọi, không tạo một nguồn độc lập; nếu future được nhiều consumer dùng chung, deadline do một consumer đặt có thể tác động người khác.

Một ví dụ minh họa chuỗi:

```java
CompletableFuture<String> safe = fetchRemote()
        .orTimeout(2, TimeUnit.SECONDS)
        .exceptionally(error -> "temporarily-unavailable");
```

Đây là snippet chưa độc lập, giả định `fetchRemote()` trả `CompletableFuture<String>` và cần import `TimeUnit`. Nó áp dụng fallback cho **mọi** exceptional completion, không chỉ timeout. Nếu cần fallback riêng cho timeout, hãy phân loại lỗi trước khi trả giá trị dự phòng.

`orTimeout` làm future completed exceptionally nhưng **không bảo đảm dừng công việc nền** đang xử lý. Nếu tác vụ có side effect, giá trị fallback chỉ là kết quả quan sát ở tầng CompletableFuture, không khẳng định bên ngoài chưa thực hiện thao tác.

## 14. Khi nào cần dùng exceptionallyCompose?

`exceptionally` mong đợi callback trả **một giá trị `T`**. Nếu fallback của bạn là một **tác vụ bất đồng bộ khác** (ví dụ đọc từ cache từ xa), một hàm kiểu `Throwable -> CompletableFuture<T>` không khớp trực tiếp với yêu cầu `Throwable -> T`.

`exceptionallyCompose` (có trong Java 17) dành cho recovery bằng một stage khác, có chữ ký ý tưởng:

```java
CompletableFuture<T> recovered =
        primary.exceptionallyCompose(error -> fallbackAsync());
```

Đây là snippet minh họa, giả định `primary` có kiểu `CompletableFuture<T>` và `fallbackAsync()` trả `CompletionStage<T>` phù hợp. Method tạo một stage kết quả theo stage được callback trả về mà không cần gọi `join()` blocking.

So sánh:

- `exceptionally(error -> cachedValue)`: có **giá trị dự phòng sẵn có**, tính nhanh.
- `exceptionallyCompose(error -> fetchFromBackup())`: cần **tác vụ async dự phòng** và đợi nó theo cơ chế composition.
- `exceptionally(error -> fetchFromBackup().join())`: có thể **block** một thread và phá ưu điểm của pipeline async.

Nếu upstream thành công, các phương thức recovery không cần gọi fallback. Nếu chính fallback async thất bại, stage kết quả tiếp tục exceptional; nó không trở thành thành công chỉ vì đã có recovery handler.

Cách lựa chọn còn phụ thuộc việc API có muốn thực sự thử lại cùng thao tác hay chuyển qua dịch vụ khác. Dù dùng composition, giới hạn vòng lặp retry và kiểm soát side effect vẫn rất quan trọng.

## 15. Phối hợp với thenApply, thenCompose và nhánh kết quả

Một pipeline điển hình:

```java
CompletableFuture<String> display = fetchUserId()
        .thenCompose(id -> fetchUserName(id))
        .thenApply(name -> name.trim())
        .exceptionally(error -> "Khách");
```

Đây là snippet minh họa, với `fetchUserId()`/`fetchUserName(...)` giả định có kiểu tương thích và cần được khai báo trong ứng dụng. `exceptionally` có thể biến lỗi ở bất kỳ stage **trước nó** thành chuỗi `"Khách"`.

Tuy nhiên, nếu chuỗi này được dùng để kiểm toán hoạt động hoặc xác nhận danh tính thì fallback “Khách” có thể vi phạm nghiệp vụ. Hãy đặt recovery tại boundary có hợp đồng cho phép kết quả dự phòng, ví dụ hiển thị nickname tùy chọn của UI.

Sau khi phục hồi, các stage tiếp theo coi `"Khách"` như kết quả thành công bình thường. Nếu muốn phân biệt “giá trị thực” và “giá trị dự phòng”, nên giữ metadata:

```java
record DisplayName(String text, boolean fallback) {}

CompletableFuture<DisplayName> value =
        fetchName().thenApply(name -> new DisplayName(name, false))
                .exceptionally(error -> new DisplayName("Khách", true));
```

Đây là snippet minh họa, `fetchName()` giả định trả `CompletableFuture<String>`. `record` hỗ trợ từ Java 16 nên phù hợp Java 17. Mã gọi có thể đọc `fallback()` để biết nội dung được thay thế vì lỗi, thay vì tự đoán từ chuỗi `"Khách"`.

## 16. Hai lỗi khác nhau: lỗi upstream và lỗi recovery

Khi phục hồi cũng thất bại, muốn chẩn đoán tốt cần giữ hai thông tin:

- **Upstream failure:** lý do cần recovery ban đầu.
- **Recovery failure:** lý do không tạo được giá trị dự phòng.

Trong ví dụ `RecoveryFailureDemo`, `IllegalArgumentException("fallback failed", error)` giữ nguyên exception upstream làm cause. Nhưng nếu fallback async thất bại ở một stage khác, tùy API bạn có thể cần xây dựng exception domain với cause và thông tin correlation phù hợp.

Không nên vô tình **double-log** cùng một exception ở mọi stage; ghi tại một ranh giới quan sát có ownership rõ ràng và thêm ngữ cảnh nếu thực sự cần. Nếu recovery biến lỗi thành kết quả bình thường, các consumer của stage mới sẽ không tự thấy exception cũ. Muốn thống kê tỷ lệ dùng fallback thì callback recovery có thể ghi metric/counter, nhưng không nên để metric system failure làm hỏng recovery nếu policy không yêu cầu.

Bảo mật cũng quan trọng: `Throwable.getMessage()` từ HTTP/SQL/SDK có thể chứa URL nội bộ, token hoặc dữ liệu nhạy cảm. Đừng ghép thẳng message vendor vào kết quả fallback trả client; dùng thông điệp/loại lỗi do API kiểm soát.

## 17. Kiểm thử đúng hành vi phục hồi

Kiểm thử `exceptionally` nên bao gồm đường thành công, đường lỗi có thể phục hồi, lỗi không được phép phục hồi và lỗi của chính fallback.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Upstream thành công với `10` | Lambda trong `exceptionally` **không chạy**, stage mới nhận `10`. |
| Upstream failed với lỗi cho phép fallback | Callback chạy một lần cho stage phụ thuộc tương ứng; stage mới trả fallback hợp lệ. |
| Upstream failed với lỗi phải truyền tiếp | Callback phân loại và ném lại/bao lỗi; stage mới vẫn exceptional. |
| Recovery callback tự ném exception | Stage recovery exceptional, nguyên nhân cần được bảo toàn để chẩn đoán. |
| Recovery trả `null` cho kiểu tham chiếu | Stage hoàn thành bình thường với `null`; downstream phải xử lý theo contract. |
| Upstream bị cancel | Callback có thể nhận exceptional completion; không vô tình xóa trạng thái cancellation của workflow khi policy yêu cầu. |
| Lỗi xảy ra ở `thenApply` **sau** recovery | `exceptionally` ở trước **không bắt** lỗi của stage phía sau. |
| Lỗi xảy ra ở `thenApply` **trước** recovery | `exceptionally` ở sau có thể xử lý lỗi ấy. |
| `get(timeout)` chỉ hết hạn chờ | Future nguồn không tự exceptional chỉ vì caller timeout; không tự kích hoạt recovery. |
| `orTimeout` hoàn thành exceptional | `exceptionally` sau đó có thể chạy và trả fallback. |

Đối với test nhỏ, dùng `completedFuture`/`failedFuture` để giảm phụ thuộc vào scheduling. Với test cần chứng minh pipeline thực sự async, dùng `CountDownLatch` để kiểm soát thứ tự thay vì chỉ `Thread.sleep` cố đoán thời gian.

Một anti-pattern của test là chỉ assert `recovered.join() == fallback` rồi bỏ qua trạng thái nguồn. Nên kiểm tra cả `source.isCompletedExceptionally()` khi muốn bảo đảm phục hồi **không sửa lỗi gốc**, và bảo đảm các stage đặt sau recovery nhận kết quả phù hợp.

## 18. Lỗi thường gặp và cách sửa

**1. Tưởng `exceptionally` chạy ở cả đường thành công.** Nó chỉ gọi callback khi upstream exceptional. Dùng `handle` nếu phải biến đổi cả thành công lẫn thất bại.

**2. Tưởng `exceptionally` chỉ log mà giữ lỗi.** Nếu callback trả một giá trị, stage mới bình thường. Dùng `whenComplete` khi mục tiêu chỉ là quan sát; muốn ghi log rồi tiếp tục thất bại thì phải có lựa chọn rõ ràng.

**3. Trả fallback cho mọi `Throwable`.** Cách này có thể che bug, lỗi bảo mật, lỗi dữ liệu và sự cố nghiêm trọng. Phân loại nguyên nhân và chỉ phục hồi trong những trường hợp được phép.

**4. Bỏ qua `CompletionException` wrapper.** Kiểu exception mà handler nhận có thể khác kiểu mà stage trước ném trực tiếp. Bóc lớp bao có kiểm soát và dựa vào hợp đồng lỗi ổn định.

**5. Đặt `exceptionally` quá sớm.** Nó không phục hồi những lỗi xảy ra ở các stage được nối sau đó. Đặt recovery đúng boundary.

**6. Đặt `exceptionally` quá muộn và bắt cả bug.** Một fallback rộng ở cuối pipeline có thể che lỗi từ nhiều bước không tương đương. Chọn vị trí và quy tắc phân loại phù hợp.

**7. Dùng `join()` để gọi tác vụ async dự phòng ngay trong lambda.** Dễ block thread quan trọng; dùng composition async khi fallback cần thời gian.

**8. Dùng `null` hoặc `0` như thể đó luôn là dữ liệu thật.** Caller có thể diễn giải sai. Trả kết quả có metadata hay trạng thái fallback nếu điều đó quan trọng.

**9. Tưởng recovery sửa source future.** Không: stage mới có thể thành công trong khi nguồn vẫn exceptional.

**10. Xem timeout của `get(timeout)` là sự cố của upstream.** Timeout tại waiter không làm future hoàn thành exceptional. Phân biệt với `orTimeout`.

**11. Phục hồi cancellation trái ý định của workflow.** Nếu hệ thống cần hủy, biến nó thành kết quả “thành công” có thể làm tác vụ tiếp tục ngoài mong đợi.

**12. Giả định callback luôn chạy trên một executor.** Non-async continuations có thể chạy trên thread hoàn thành future hoặc thread gắn callback; tránh blocking và phụ thuộc thread-local.

**13. Không kiểm tra khi fallback cũng lỗi.** Callback phục hồi có thể ném exception, stage mới vẫn exceptional. Test và theo dõi nhánh này.

## 19. Bài tập tự kiểm tra

**Câu 1:** `CompletableFuture.completedFuture(5).exceptionally(error -> 0).join()` trả gì? Lambda recovery có chạy không?

**Trả lời:** Trả `5`; lambda không chạy vì upstream thành công.

**Câu 2:** Một future đã failed với `IllegalStateException`. Sau `exceptionally(error -> 10)`, trạng thái future gốc và future trả về khác nhau như thế nào?

**Trả lời:** Future gốc vẫn completed exceptionally, còn stage mới thành công với giá trị `10` nếu callback không ném exception.

**Câu 3:** `upstream.exceptionally(error -> 0).thenApply(x -> 10 / x)` có bảo đảm thành công khi upstream failed không?

**Trả lời:** Không. Recovery trả `0`, stage `thenApply` phía sau có thể ném `ArithmeticException`. `exceptionally` ở phía trước không phục hồi lỗi mới.

**Câu 4:** Muốn vừa nhìn thấy lỗi vừa giữ nguyên exceptional completion, nên chọn `whenComplete` hay `exceptionally`?

**Trả lời:** Thường chọn `whenComplete` với callback quan sát không ném. `exceptionally` trả fallback sẽ chuyển nhánh lỗi thành giá trị bình thường.

**Câu 5:** Khi fallback là một `CompletableFuture<T>` khác, có nên viết `exceptionally(error -> backup().join())` không?

**Trả lời:** Nên ưu tiên `exceptionallyCompose(error -> backup())` để kết hợp stage bất đồng bộ mà không block thread hiện tại, đồng thời thiết kế timeout và quyền sở hữu tác vụ.

**Câu 6:** Caller gọi `future.get(100, MILLISECONDS)` và bị `TimeoutException`, hàm `exceptionally` gắn trên chính future có tự chạy không?

**Trả lời:** Không chỉ vì lời gọi `get` hết hạn. `get(timeout)` giới hạn một lần chờ, không tự thay đổi trạng thái future.

**Câu 7:** Nếu một `CompletableFuture` bị cancel, nên tự động chuyển `CancellationException` thành chuỗi `"OK"` không?

**Trả lời:** Chỉ khi hợp đồng sản phẩm cố ý coi hủy là một kết quả bình thường như vậy. Nếu workflow dùng cancellation để yêu cầu dừng, “OK” có thể che mất tín hiệu quan trọng.

## 20. Checklist khi chọn exceptionally

Trước khi thêm `exceptionally` vào pipeline, hãy tự trả lời:

1. **Stage nào có thể thất bại?** Handler đang nằm sau đúng những stage cần phục hồi chưa?
2. **Lỗi nào được phép biến thành kết quả?** Có phân loại được lỗi dự kiến và bug/hủy không?
3. **Fallback có ý nghĩa nghiệp vụ không?** `0`, `null`, list rỗng hoặc thông điệp mặc định có làm caller hiểu sai?
4. **Fallback là giá trị sẵn có hay tác vụ async?** Nếu là async, nên dùng composition để tránh blocking.
5. **Callback có thể ném lỗi không?** Khi nó thất bại, cause có được giữ và trạng thái được giám sát không?
6. **Có consumer khác đang quan sát future gốc không?** Recovery tạo stage mới, không xóa lỗi của nguồn.
7. **Có chính sách về cancellation, timeout, retry và idempotency không?** Recovery không tự dừng tác vụ nền và không tự thực hiện lại công việc đã thất bại.
8. **Có cần quan sát tỷ lệ fallback không?** Hãy ghi nhận số lần dùng fallback tại boundary thích hợp, tránh log lặp.
9. **Đã kiểm thử cả thành công, lỗi và lỗi trong recovery chưa?** Đừng chỉ kiểm tra một đường happy path.

`exceptionally` là cách biểu diễn rõ ràng câu **“nếu bước trước thất bại theo điều kiện có thể phục hồi, hãy dùng giá trị thay thế cùng kiểu và tiếp tục”**. Dùng nó đúng boundary, với fallback có ý nghĩa và phân loại lỗi rõ ràng, sẽ giúp chương trình bất đồng bộ duy trì hợp đồng nhất quán mà vẫn giữ được khả năng quan sát những thất bại thật sự.