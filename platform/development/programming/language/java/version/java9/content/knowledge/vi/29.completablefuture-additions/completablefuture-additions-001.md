# Giá trị hoặc lỗi đã hoàn tất qua các factory bổ sung

## 1. Factory hoàn tất sẵn dùng để làm gì?

`CompletableFuture` thường đại diện cho một kết quả có thể xuất hiện trong tương lai. Tuy nhiên, đôi khi chương trình đã biết kết quả ngay tại thời điểm tạo API: dữ liệu đã có sẵn, hoặc một điều kiện đầu vào khiến tác vụ chắc chắn thất bại.

Trong trường hợp đó, không cần tạo một tác vụ bất đồng bộ chỉ để hoàn tất nó. Có thể tạo một future hoặc stage đã có kết quả ngay:

- Hoàn tất bình thường với một giá trị.
- Hoàn tất exceptional với một exception.

Java 9 bổ sung các factory sau trong `CompletableFuture`:

- `failedFuture(Throwable ex)`: tạo `CompletableFuture` đã hoàn tất exceptional.
- `completedStage(U value)`: tạo `CompletionStage` đã hoàn tất bình thường.
- `failedStage(Throwable ex)`: tạo `CompletionStage` đã hoàn tất exceptional.

`completedFuture(U value)` cũng tạo một future đã hoàn tất bình thường, nhưng phương thức này đã có từ Java 8. Nó thường được dùng làm đối chiếu khi học các factory bổ sung của Java 9.

Các factory này không tự chạy công việc nền, không tạo thread và không lên lịch tác vụ. Chúng chỉ tạo một đối tượng biểu diễn kết quả đã biết.

## 2. completedFuture và failedFuture

### completedFuture: kết quả bình thường có sẵn

`CompletableFuture.completedFuture(value)` trả về một `CompletableFuture` đã hoàn tất bình thường với giá trị truyền vào.

```java
CompletableFuture<String> result =
        CompletableFuture.completedFuture("ready");

System.out.println(result.isDone()); // true
System.out.println(result.join());   // ready
```

Giá trị `null` được phép. Một future hoàn tất bình thường với null vẫn là future đã hoàn tất; null là kết quả của nó, không phải trạng thái pending hay exceptional.

### failedFuture: lỗi đã biết có sẵn

Từ Java 9, `CompletableFuture.failedFuture(exception)` tạo một `CompletableFuture` đã hoàn tất exceptional với exception được cung cấp.

```java
CompletableFuture<String> result =
        CompletableFuture.failedFuture(
                new IllegalStateException("service unavailable"));

System.out.println(result.isDone());                  // true
System.out.println(result.isCompletedExceptionally()); // true
```

Future đã hoàn tất, nhưng không có giá trị bình thường để lấy. Khi gọi `join()`, nó ném `CompletionException`; nguyên nhân gốc được lấy qua `getCause()`. Khi gọi `get()`, lỗi được bọc trong `ExecutionException`.

```java
try {
    result.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    System.out.println(cause.getMessage());
}
```

Đối số exception của `failedFuture` phải khác null. Truyền null sẽ ném `NullPointerException` ngay tại lúc gọi factory.

## 3. completedStage và failedStage

Java 9 cũng bổ sung hai factory trả về kiểu `CompletionStage`:

```java
CompletionStage<String> success =
        CompletableFuture.completedStage("stage ready");

CompletionStage<String> failure =
        CompletableFuture.failedStage(
                new IllegalArgumentException("invalid input"));
```

Hai factory này có trạng thái kết quả tương tự `completedFuture` và `failedFuture`:

- `completedStage(value)` tạo stage đã hoàn tất bình thường.
- `failedStage(exception)` tạo stage đã hoàn tất exceptional.
- Giá trị hoàn tất bình thường có thể là null.
- Exception dùng để hoàn tất exceptional phải khác null.

Khác biệt quan trọng là kiểu trả về: `CompletionStage<T>`, thay vì `CompletableFuture<T>`. Stage phù hợp khi API chỉ muốn công bố một kết quả có thể nối chuỗi bằng các thao tác như `thenApply`, `thenCompose`, `handle` hoặc `exceptionally`, mà không trao cho bên gọi quyền điều khiển việc hoàn tất future gốc.

Các stage do `completedStage` và `failedStage` tạo là các minimal CompletionStage. Chúng cung cấp hợp đồng kết hợp của `CompletionStage`, không phơi bày API hoàn tất như `complete` hay `completeExceptionally`.

Nếu một API khác cần `CompletableFuture`, có thể gọi `toCompletableFuture()` để lấy một future thể hiện cùng kết quả. Việc thao tác trên future được trả về không cho phép thay đổi trạng thái của minimal stage gốc.

## 4. Chọn factory theo kiểu trả về

| Factory | Có từ | Kiểu trả về | Trạng thái ban đầu |
|---|---|---|---|
| `completedFuture(value)` | Java 8 | `CompletableFuture<T>` | Hoàn tất bình thường |
| `failedFuture(ex)` | Java 9 | `CompletableFuture<T>` | Hoàn tất exceptional |
| `completedStage(value)` | Java 9 | `CompletionStage<T>` | Hoàn tất bình thường |
| `failedStage(ex)` | Java 9 | `CompletionStage<T>` | Hoàn tất exceptional |

Chọn theo hợp đồng của API:

- Nếu phương thức khai báo trả về `CompletableFuture<T>` và cần trả ngay kết quả hoặc lỗi, dùng `completedFuture` hoặc `failedFuture`.
- Nếu phương thức khai báo trả về `CompletionStage<T>` và muốn công bố một stage chỉ để kết hợp, dùng `completedStage` hoặc `failedStage`.
- Nếu công việc thật sự cần chạy bất đồng bộ, dùng `supplyAsync`, `runAsync` hoặc một cơ chế thực thi phù hợp; factory hoàn tất sẵn không thay thế việc lên lịch công việc.
- Nếu kết quả sẽ được hoàn tất sau này bởi một callback khác, tạo `new CompletableFuture<>()` rồi hoàn tất nó bằng `complete` hoặc `completeExceptionally` khi có kết quả.

Không chọn `completedStage` chỉ vì tên của nó có chữ “stage”. Hãy xem kiểu trả về mà API cần cam kết với caller.

## 5. Lỗi được truyền qua pipeline như thế nào?

Một future đã hoàn tất exceptional vẫn có thể được nối chuỗi. Các stage tiếp theo nhận trạng thái lỗi theo quy tắc của CompletionStage:

- `thenApply` chỉ chạy khi stage trước hoàn tất bình thường.
- `thenCompose` cũng chỉ gọi hàm chuyển tiếp khi có kết quả bình thường.
- `exceptionally` có thể biến lỗi thành một giá trị dự phòng.
- `handle` được gọi cho cả kết quả bình thường và exceptional.
- `whenComplete` phù hợp để quan sát kết quả hoặc lỗi; nó không phải thao tác phục hồi lỗi theo cách của `exceptionally`.

Ví dụ phục hồi lỗi:

```java
CompletableFuture<String> request =
        CompletableFuture.failedFuture(
                new IllegalStateException("offline"));

CompletableFuture<String> recovered =
        request.exceptionally(error -> "cached value");

System.out.println(recovered.join()); // cached value
```

`exceptionally` tạo một stage tiếp theo. Nó không thay đổi lịch sử của future ban đầu: `request` vẫn hoàn tất exceptional, còn `recovered` hoàn tất bình thường với giá trị dự phòng.

Nếu không phục hồi, lỗi tiếp tục lan truyền qua các stage phụ thuộc. Khi cuối cùng gọi `join()` hoặc `get()`, caller quan sát lỗi qua wrapper tương ứng.

## 6. Ví dụ Java chạy được: cả bốn factory và phục hồi lỗi

Chương trình dưới đây so sánh factory bình thường, factory exceptional và hai factory trả về `CompletionStage`. Nó cũng kiểm tra kiểu stage tối thiểu, null và phục hồi bằng `exceptionally`.

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class CompletionFactoriesDemo {
    public static void main(String[] args) {
        CompletableFuture<String> completed =
                CompletableFuture.completedFuture("ready");
        System.out.println("completedFuture done = " + completed.isDone());
        System.out.println("completedFuture value = " + completed.join());

        CompletableFuture<String> failed = CompletableFuture.failedFuture(
                new IllegalStateException("disk unavailable"));
        System.out.println("failedFuture done = " + failed.isDone());
        System.out.println("failedFuture exceptional = "
                + failed.isCompletedExceptionally());
        try {
            failed.join();
        } catch (CompletionException ex) {
            System.out.println("failedFuture cause = "
                    + ex.getCause().getClass().getSimpleName() + ": "
                    + ex.getCause().getMessage());
        }

        CompletionStage<String> completedStage =
                CompletableFuture.completedStage("stage ready");
        CompletionStage<String> failedStage = CompletableFuture.failedStage(
                new IllegalArgumentException("invalid input"));
        System.out.println("completedStage value = "
                + completedStage.toCompletableFuture().join());
        System.out.println("failedStage exceptional = "
                + failedStage.toCompletableFuture().isCompletedExceptionally());
        try {
            failedStage.toCompletableFuture().join();
        } catch (CompletionException ex) {
            System.out.println("failedStage cause = "
                    + ex.getCause().getClass().getSimpleName() + ": "
                    + ex.getCause().getMessage());
        }

        CompletableFuture<String> stageView =
                completedStage.toCompletableFuture();
        System.out.println("stage view complete accepted = "
                + stageView.complete("replacement"));
        System.out.println("stage original value = "
                + completedStage.toCompletableFuture().join());

        String recovered = failed.exceptionally(error -> "fallback").join();
        System.out.println("recovered value = " + recovered);

        System.out.println("completedFuture null = "
                + (CompletableFuture.completedFuture(null).join() == null));
        System.out.println("completedStage null = "
                + (CompletableFuture.completedStage(null)
                        .toCompletableFuture().join() == null));

        try {
            CompletableFuture.failedFuture(null);
        } catch (NullPointerException ex) {
            System.out.println("failedFuture null cause = NullPointerException");
        }
        try {
            CompletableFuture.failedStage(null);
        } catch (NullPointerException ex) {
            System.out.println("failedStage null cause = NullPointerException");
        }
    }
}
```

Lưu mã nguồn trong `CompletionFactoriesDemo.java`, sau đó biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all CompletionFactoriesDemo.java
java CompletionFactoriesDemo
```

Kết quả:

```text
completedFuture done = true
completedFuture value = ready
failedFuture done = true
failedFuture exceptional = true
failedFuture cause = IllegalStateException: disk unavailable
completedStage value = stage ready
failedStage exceptional = true
failedStage cause = IllegalArgumentException: invalid input
stage view complete accepted = false
stage original value = stage ready
recovered value = fallback
completedFuture null = true
completedStage null = true
failedFuture null cause = NullPointerException
failedStage null cause = NullPointerException
```

Future lấy từ `completedStage.toCompletableFuture()` đã hoàn tất với giá trị stage ban đầu, nên lời gọi `complete("replacement")` trả false. Stage gốc vẫn giữ kết quả `"stage ready"`. Ví dụ đã được biên dịch bằng `javac --release 17 -Xlint:all` và stdout được kiểm tra.

## 7. So sánh factory với tự hoàn tất một CompletableFuture

Có thể tạo future pending rồi hoàn tất thủ công:

```java
CompletableFuture<String> result = new CompletableFuture<>();

if (valid) {
    result.complete("ready");
} else {
    result.completeExceptionally(
            new IllegalArgumentException("invalid"));
}
```

Cách này phù hợp khi kết quả chỉ xuất hiện sau một callback hoặc sự kiện khác. Tuy nhiên, nếu đã biết ngay kết quả ở thời điểm tạo, factory làm rõ ý định hơn:

```java
return valid
        ? CompletableFuture.completedFuture("ready")
        : CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid"));
```

Factory không tạo một khoảng thời gian pending để mã khác có thể hoàn tất sau. Đối tượng trả về đã có kết quả ngay khi caller nhận được nó.

Cũng cần phân biệt trả về một failed future với ném exception đồng bộ:

```java
CompletionStage<String> load(boolean valid) {
    if (!valid) {
        return CompletableFuture.failedStage(
                new IllegalArgumentException("invalid"));
    }
    return CompletableFuture.completedStage("ready");
}
```

Trong ví dụ này, phương thức `load` trả về bình thường với một stage đã hoàn tất exceptional. Caller có thể nối `exceptionally` hoặc `handle` vào stage đó. Nếu phương thức ném exception trực tiếp trước khi trả về, caller phải xử lý lỗi ngay tại lời gọi phương thức, trước khi nhận được stage.

## 8. Những lỗi thường gặp

- **Nhầm future hoàn tất với future thành công:** `isDone()` trả true cả với kết quả bình thường lẫn exceptional. Dùng `isCompletedExceptionally()` hoặc quan sát kết quả theo cách phù hợp.
- **Cho rằng failedFuture ném exception ngay:** factory trả về một future đã hoàn tất exceptional; lỗi được quan sát khi gọi `join`, `get` hoặc nối chuỗi.
- **Quên wrapper exception:** `join()` ném `CompletionException`, còn `get()` ném `ExecutionException`; kiểm tra nguyên nhân qua `getCause()`.
- **Dùng null làm exception:** `failedFuture(null)` và `failedStage(null)` ném `NullPointerException` ngay khi tạo.
- **Cho rằng completed factory không nhận null:** `completedFuture(null)` và `completedStage(null)` hợp lệ; cần phân biệt null là một giá trị kết quả.
- **Trả CompletableFuture khi chỉ muốn công bố CompletionStage:** API có thể vô tình để caller thấy các phương thức điều khiển hoàn tất. Nếu hợp đồng chỉ cần composition, cân nhắc trả `CompletionStage` qua `completedStage` hoặc `failedStage`.
- **Dùng factory thay cho tác vụ bất đồng bộ:** factory chỉ đóng gói kết quả có sẵn; nó không chạy công việc nền.
- **Cho rằng exceptionally sửa future ban đầu:** phương thức phục hồi tạo stage mới; future gốc vẫn giữ trạng thái exceptional.

## 9. Checklist khi chọn factory

1. Kết quả đã biết ngay hay chỉ xuất hiện sau khi một tác vụ chạy?
2. Kết quả là bình thường hay exceptional?
3. API cần trả `CompletableFuture<T>` hay chỉ cần `CompletionStage<T>`?
4. Nếu lỗi, exception có khác null và có mô tả đúng nguyên nhân không?
5. Caller cần quan sát lỗi, chuyển tiếp lỗi hay phục hồi thành giá trị?
6. Có đang kiểm tra mã thành công bằng `isDone()` thay vì kiểm tra trạng thái exceptional/kết quả không?
7. Có nhầm trả về failed stage với ném exception đồng bộ không?

Các factory Java 9 giúp biểu diễn một giá trị hoặc lỗi đã biết bằng đúng abstraction của Completion API. Dùng `failedFuture` và `completedFuture` khi hợp đồng cần một CompletableFuture; dùng `failedStage` và `completedStage` khi chỉ cần công bố một CompletionStage để caller tiếp tục kết hợp kết quả.