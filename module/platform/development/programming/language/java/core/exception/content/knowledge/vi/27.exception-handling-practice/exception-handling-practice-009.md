# So sánh phục hồi lỗi bằng `exceptionally`, `handle` và `whenComplete` trong Java

Một `CompletableFuture` có thể kết thúc **bình thường** với một giá trị hoặc **bất thường** (*exceptional completion*) vì một lỗi. Khi xây dựng pipeline bất đồng bộ, ba phương thức `exceptionally`, `handle` và `whenComplete` thường xuất hiện cạnh nhau. Tất cả đều cho phép phản ứng với lỗi, nhưng **không có cùng mục đích**:

- **`exceptionally`**: chỉ chạy khi stage trước thất bại; có thể **phục hồi bằng một giá trị** cùng kiểu kết quả.
- **`handle`**: chạy khi stage trước thành công **hoặc** thất bại; có thể **chuyển cả hai trường hợp thành một kết quả mới**, thậm chí khác kiểu.
- **`whenComplete`**: chạy khi stage trước thành công **hoặc** thất bại để **quan sát/ghi nhận**; bình thường giữ kết quả hoặc lỗi của stage trước, chứ không phải API tạo giá trị dự phòng.

Điểm dễ nhầm nhất là viết `whenComplete((value, error) -> logger.error(...))` rồi tưởng lỗi đã được xử lý xong. **Ghi log không đồng nghĩa phục hồi.** Nếu stage trước bị lỗi, stage sau `whenComplete` thường vẫn bị lỗi, và `join()`/`get()` vẫn báo thất bại.

Bài thực hành này dùng Java 17+, các chương trình có thể biên dịch và chạy độc lập, để phân biệt cách truyền trạng thái, giá trị dự phòng, callback tự ném ngoại lệ và tác động đến pipeline nhiều bước.

## 1. Mô hình: một stage hoàn tất theo một trong hai nhánh

Một `CompletableFuture<T>` đại diện cho một kết quả hoàn tất:

```text
CompletableFuture<T>
       |
       +-- Thành công ----------------> value: T
       |                                  |
       |                         thenApply / thenAccept
       |
       +-- Thất bại ------------------> error: Throwable
                                          |
                          exceptionally / handle / whenComplete
```

Không nên dùng `isDone() == true` để kết luận công việc thành công: một future hoàn tất do lỗi hoặc hủy cũng được xem là đã hoàn tất. Khi cần chẩn đoán, `join()` có thể ném `CompletionException` bọc nguyên nhân; `get()` có thể ném `ExecutionException`. Một future bị hủy trực tiếp có thể ném `CancellationException`.

Giả sử:

```java
CompletableFuture<Integer> success =
        CompletableFuture.completedFuture(7);
CompletableFuture<Integer> failure =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("bad input"));
```

Đây là hai câu lệnh minh họa trong phạm vi có `import java.util.concurrent.CompletableFuture;`. `completedFuture` và `failedFuture` có từ Java 9; trên Java 17 chúng dùng được. Khi gọi các callback bên dưới, không cần giả lập thread hay đợi tác vụ mạng: cả hai future đã có trạng thái cuối, giúp bài thực hành có kết quả xác định.

**Stage nguồn và stage mới là hai đối tượng khác nhau** đối với các phương thức trong bài. Ví dụ `CompletableFuture<Integer> recovered = failure.exceptionally(e -> -1)` không sửa trạng thái lỗi của `failure`; nó tạo một stage phụ thuộc mới có thể hoàn tất bình thường. Đừng hiểu nhầm việc stage sau phục hồi là tác vụ gốc đã thành công.

## 2. Bảng đối chiếu chính xác ba phương thức

| Tiêu chí | `exceptionally` | `handle` | `whenComplete` |
| --- | --- | --- | --- |
| Chạy khi stage trước thành công? | **Không** | **Có** | **Có** |
| Chạy khi stage trước thất bại? | **Có** | **Có** | **Có** |
| Dữ liệu callback nhận | `Throwable error` | `T value`, `Throwable error` | `T value`, `Throwable error` |
| Callback trả gì? | Giá trị `T` thay thế | Giá trị mới kiểu `U` | `void` |
| Có thể biến thất bại thành thành công? | **Có**, khi callback trả bình thường | **Có**, khi callback trả bình thường | **Không bằng cách trả một giá trị** |
| Khi callback thành công và nguồn đã lỗi | Stage mới nhận fallback | Stage mới nhận giá trị đã xử lý | Stage mới vẫn truyền lỗi cũ |
| Khi callback tự ném lỗi | Stage mới thất bại với lỗi callback | Stage mới thất bại với lỗi callback | Nếu nguồn thành công: lỗi callback làm stage mới thất bại; nếu nguồn đã thất bại: lỗi nguồn được ưu tiên |
| Đổi kiểu kết quả từ `T` sang `U`? | Không (cùng `T`) | Có | Không (giữ `T`) |
| Mục đích tiêu biểu | Phục hồi lỗi bằng fallback | Tổng hợp success/failure thành một kiểu kết quả | Logging, metrics, cleanup/quan sát |
| Đối tượng trả về | Stage mới | Stage mới | Stage mới |

**Ghi chú về lỗi trong `whenComplete`:** theo hợp đồng `CompletionStage`, nếu callback tự ném lỗi, stage trả về hoàn tất lỗi với ngoại lệ callback **trừ khi stage nguồn đã hoàn tất lỗi**. Trong tình huống cả hai đều lỗi, nguồn vẫn là lỗi quyết định trạng thái của stage trả về. Không dựa vào việc lỗi callback tự động được thêm vào `getSuppressed()` của lỗi nguồn; đó không phải một bảo đảm của API.

## 3. Chữ ký và ý nghĩa của giá trị trả về

Các chữ ký được lược bỏ một số chi tiết generic:

```java
CompletableFuture<T> exceptionally(
        Function<Throwable, ? extends T> fn);

<U> CompletableFuture<U> handle(
        BiFunction<? super T, Throwable, ? extends U> fn);

CompletableFuture<T> whenComplete(
        BiConsumer<? super T, ? super Throwable> action);
```

Đây là **mô tả API**, không phải chương trình Java độc lập; chữ ký thực tế dùng các kiểu trong `java.util.function`.

- `exceptionally` nhận một `Function` từ lỗi sang giá trị `T`. Khi nguồn thành công, callback này không chạy, và giá trị thành công tiếp tục đi qua stage mới.
- `handle` nhận `BiFunction`: với thành công thông thường, `error == null`; với thất bại, `value` thường là `null`. Nó trả một giá trị kiểu `U`, cho phép chuyển `CompletableFuture<Integer>` thành `CompletableFuture<String>` hoặc một kiểu kết quả có nhãn.
- `whenComplete` nhận `BiConsumer`: thực hiện hành động, **không có giá trị trả về** để thay kết quả stage. Dù callback có ghi log hoặc đo metric thành công, lỗi nguồn vẫn phải được xử lý ở ranh giới khác nếu ứng dụng cần phục hồi.

Cần cẩn thận với `null`: một `CompletableFuture<String>` **có thể hoàn tất thành công bằng `null`**. Do đó không dùng `value == null` làm tiêu chuẩn duy nhất để xác định thất bại trong `handle` hoặc `whenComplete`. Hãy dùng `error != null` để phân biệt nhánh lỗi theo hợp đồng callback.

## 4. Ví dụ 1 có thể chạy: cùng nguồn nhưng ba cách xử lý

Tạo tệp **`RecoveryMethodsDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class RecoveryMethodsDemo {
    static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> failure =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad input"));

        int successExceptionally =
                success.exceptionally(error -> -1).join();
        System.out.println("success.exceptionally=" + successExceptionally);

        int successHandle = success.handle(
                (value, error) -> error == null ? value * 2 : -2).join();
        System.out.println("success.handle=" + successHandle);

        int successObserved = success.whenComplete(
                (value, error) -> {}).join();
        System.out.println("success.whenComplete=" + successObserved);

        CompletableFuture<Integer> recovered = failure.exceptionally(
                error -> {
                    System.out.println("exceptionally.error="
                            + unwrap(error).getClass().getSimpleName());
                    return -1;
                });
        System.out.println("failure.exceptionally=" + recovered.join());

        int failureHandled = failure.handle((value, error) -> {
            System.out.println("handle.hasError=" + (error != null));
            return error == null ? value * 2 : -2;
        }).join();
        System.out.println("failure.handle=" + failureHandled);

        CompletableFuture<Integer> observed = failure.whenComplete(
                (value, error) -> System.out.println(
                        "whenComplete.error="
                                + unwrap(error).getClass().getSimpleName()));

        try {
            observed.join();
        } catch (CompletionException error) {
            System.out.println("failure.whenComplete.root="
                    + unwrap(error).getClass().getSimpleName());
        }

        System.out.println("source.exceptional="
                + failure.isCompletedExceptionally());
        System.out.println("recovered.exceptional="
                + recovered.isCompletedExceptionally());
    }
}
```

Biên dịch/chạy với Java 17:

```bash
javac --release 17 RecoveryMethodsDemo.java
java RecoveryMethodsDemo
```

Kết quả:

```text
success.exceptionally=7
success.handle=14
success.whenComplete=7
exceptionally.error=IllegalArgumentException
failure.exceptionally=-1
handle.hasError=true
failure.handle=-2
whenComplete.error=IllegalArgumentException
failure.whenComplete.root=IllegalArgumentException
source.exceptional=true
recovered.exceptional=false
```

**Giải thích từng nhánh:**

1. `success` đã hoàn tất bình thường bằng `7`. Callback `exceptionally` **không chạy**, nên giá trị vẫn là `7`.
2. `handle` chạy trong trường hợp thành công, nhân `7` thành `14` và tạo kết quả mới.
3. `whenComplete` ở nhánh thành công không thay `7` khi action không ném.
4. `failure` được hoàn tất bất thường bằng `IllegalArgumentException`. `exceptionally` nhận lỗi, ghi loại lỗi, rồi trả `-1`; stage `recovered` hoàn tất **bình thường** bằng `-1`.
5. `handle` cũng thấy lỗi và trả `-2`; đây là **một stage phục hồi khác**, không can thiệp vào stage `recovered`.
6. `whenComplete` quan sát lỗi và in loại lỗi nhưng không tạo fallback. Khi `observed.join()` được gọi, stage vẫn thất bại và nguyên nhân có ý nghĩa là `IllegalArgumentException`.
7. Nguồn `failure.isCompletedExceptionally()` tiếp tục là `true`, trong khi nhánh `recovered.isCompletedExceptionally()` là `false`. Hồi phục ở stage phụ thuộc **không xóa lịch sử thất bại** của stage nguồn.

Ví dụ sử dụng các future đã hoàn tất sẵn để thứ tự stdout dễ kiểm chứng; không nên dựa vào thứ tự callback khi gắn chúng lên những công việc thực sự chạy đồng thời mà không có cơ chế phối hợp.

## 5. `exceptionally`: phục hồi riêng đường lỗi

Một ứng dụng hiển thị tên người dùng có thể cho phép cache thay thế khi dịch vụ hồ sơ tạm thời không sẵn sàng:

```java
CompletableFuture<String> displayName =
        loadProfileNameAsync().exceptionally(error -> "Tên tạm thời");
```

Đây là **mã minh họa**, yêu cầu hàm `loadProfileNameAsync()` trả `CompletableFuture<String>`. Nếu nguồn thành công, callback không chạy và tên thật được giữ. Nếu nguồn lỗi, callback được gọi và trả fallback `"Tên tạm thời"`.

**Lưu ý:** mẫu trên phục hồi **mọi** lỗi. Trong ứng dụng thật, nên phân loại nếu không muốn `NullPointerException` do bug, lỗi phân quyền hoặc lỗi cấu hình cũng bị biến thành fallback bình thường.

Ví dụ lọc riêng timeout trong một `CompletableFuture<String> source` đã có:

```java
CompletableFuture<String> maybeCached = source.exceptionally(error -> {
    Throwable current = error;
    while (current instanceof CompletionException
            && current.getCause() != null) {
        current = current.getCause();
    }

    if (current instanceof java.util.concurrent.TimeoutException) {
        return "CACHED";
    }
    throw new CompletionException(current);
});
```

Đây là **đoạn minh họa trong một chương trình có `source` và import thích hợp**. Nếu lỗi thuộc timeout, stage mới nhận fallback. Nếu không, callback ném lại một `CompletionException` để tiếp tục báo thất bại. Việc bọc lại sẽ tạo đường đi lỗi bổ sung; một triển khai production có thể chọn cách chuyển tiếp giữ cause phù hợp với hợp đồng logging, không nhất thiết thêm wrapper cho mọi lỗi.

### Khi `exceptionally` không phù hợp

- Nếu cần biến cả giá trị thành công lẫn lỗi thành một kiểu kết quả khác, dùng `handle`.
- Nếu chỉ muốn ghi log mà **không** biến lỗi thành thành công, dùng `whenComplete`.
- Nếu fallback không thực sự hợp lệ với thao tác (ví dụ “thanh toán thành công”), không nên phục hồi bằng một giá trị giả.
- Nếu yêu cầu người gọi nhận biết có fallback, trả một kiểu kết quả mang thông tin như `Result<T>` hoặc một record, thay vì âm thầm đổi lỗi thành một giá trị không phân biệt được.

`exceptionally` không **thực hiện lại** thao tác đã thất bại. Nó là phép **chuyển kết quả lỗi sang một giá trị**. Nếu muốn thử lại bất đồng bộ, cần một cơ chế thực thi lại có giới hạn, hoặc API kết hợp stage thích hợp (`exceptionallyCompose` trên các JDK hỗ trợ), cùng chính sách retry an toàn.

## 6. `handle`: hợp nhất thành công/thất bại và chuyển kiểu

`handle` phù hợp khi tầng gọi không muốn nhận một ngoại lệ unchecked mà muốn một kết quả **có cấu trúc**, phân biệt thành công với thất bại:

```java
record Outcome<T>(T value, String errorCode) {
    boolean succeeded() {
        return errorCode == null;
    }
}

CompletableFuture<Outcome<Integer>> outcome =
        source.handle((value, error) -> {
            if (error != null) {
                return new Outcome<Integer>(null, "SERVICE_UNAVAILABLE");
            }
            return new Outcome<Integer>(value, null);
        });
```

Đây là **đoạn mã minh họa**, cần đặt record ở vị trí khai báo kiểu Java hợp lệ và có `CompletableFuture<Integer> source`. `Outcome` là một kiểu kết quả ví dụ; khi dùng trong API thật, nên tránh cho phép trạng thái mâu thuẫn (vừa không có value vừa không có error, hoặc cả hai có giá trị) và có thể dùng sealed types nếu cần hợp đồng chặt hơn.

Điểm nổi bật là `handle` trả `U`: stage nguồn kiểu `Integer`, stage mới kiểu `Outcome<Integer>`. Nó vẫn chạy nếu stage nguồn thành công, vì vậy phù hợp cho chuẩn hóa kết quả thành một cấu trúc chung.

### Không vô tình che cả bug

Nếu callback chỉ viết:

```java
source.handle((value, error) -> error == null ? value : 0);
```

thì mọi lỗi đều chuyển thành giá trị `0`, kể cả lỗi logic nội bộ. Chỉ dùng khi `0` là giá trị dự phòng được hợp đồng cho phép và không thể bị hiểu nhầm là kết quả thật. Với lỗi không phục hồi được, `handle` có thể ném một ngoại lệ phù hợp để stage mới tiếp tục hoàn tất lỗi.

### `null` không nhất thiết có nghĩa là thất bại

Nếu nguồn là `CompletableFuture.completedFuture(null)`, một `handle((value, error) -> ...)` có thể nhận cả `value == null` **và** `error == null`. Đó vẫn là hoàn tất thành công. Không xử lý bằng `if (value == null) { fallback; }` nếu giá trị `null` được hợp đồng cho phép.

## 7. `whenComplete`: quan sát mà không đổi kết quả

Mẫu phổ biến để ghi log ở ranh giới:

```java
CompletableFuture<Order> observed =
        source.whenComplete((order, error) -> {
            if (error != null) {
                logger.error("Order computation failed", error);
            }
        });
```

Đây là **đoạn mã minh họa** cần kiểu `Order`, `source` có kiểu `CompletableFuture<Order>` và `logger` (chẳng hạn SLF4J). Chuyển đối tượng `Throwable` cho logger giúp formatter có thể ghi stack/cause, thay vì chỉ log `error.getMessage()`.

Khi nguồn thành công và action không ném lỗi, `observed` nhận cùng giá trị. Khi nguồn thất bại và action không ném lỗi, `observed` vẫn hoàn tất thất bại. **Nhìn thấy ngoại lệ trong callback không tự nghĩa là nó đã được tiêu thụ.**

Một cách dùng khác là đo metric:

```java
CompletableFuture<String> monitored =
        source.whenComplete((value, error) -> {
            if (error == null) {
                metrics.recordSuccess();
            } else {
                metrics.recordFailure();
            }
        });
```

Đây cũng là đoạn minh họa cần `source` và `metrics`. Nếu thao tác metric tự ném ngoại lệ khi nguồn thành công, stage mới có thể chuyển từ thành công sang thất bại. Do đó callback quan sát nên **nhẹ, đáng tin cậy và không làm thay đổi nghiệp vụ**.

### `whenComplete` không phải `finally` tuyệt đối

Nó giống một hook quan sát cuối stage, nhưng không phải bản sao toàn bộ ngữ nghĩa `finally` của khối lệnh đồng bộ:

- Nó chạy khi stage nguồn **hoàn tất**; nếu stage không bao giờ hoàn tất, callback cũng có thể không chạy.
- Nó không tự đóng tài nguyên thuộc supplier đang chạy; `CompletableFuture` đã hoàn tất do timeout/hủy không đảm bảo công việc vật lý đã dừng.
- Nó không thay thế `try-with-resources` ở nơi tài nguyên được mở.
- Callback có thể chạy trên những thread khác nhau tùy cách hoàn tất và biến thể `Async`; không dùng nó để giả định một thread-local context đã được giữ nguyên.

Dùng `whenComplete` để quan sát và phát metric/log ở ranh giới thích hợp, không làm nơi thực hiện cleanup không an toàn đối với resource của worker.

## 8. Callback tự ném lỗi: hành vi khác nhau như thế nào?

Các callback có thể tự thất bại do lỗi lập trình hoặc do thao tác phụ bên trong. Đừng coi `exceptionally`, `handle`, `whenComplete` là “hàng rào không thể lỗi”.

- Với `exceptionally`: nếu recovery function ném lỗi, stage mới hoàn tất thất bại. Lỗi hồi phục không tự biến thành fallback.
- Với `handle`: nếu function ném lỗi ở nhánh thành công hoặc thất bại, stage mới hoàn tất thất bại với lỗi function.
- Với `whenComplete`: nếu nguồn **thành công** và action ném lỗi, stage mới thất bại do action. Nếu nguồn **đã thất bại** và action cũng ném lỗi, lỗi nguồn được ưu tiên theo hợp đồng; không giả định có một danh sách suppressed tự động cho lỗi action.

Để kiểm chứng, tạo tệp **`CallbackFailureDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CallbackFailureDemo {
    static String rootType(Throwable error) {
        Throwable current = error;
        while (current instanceof CompletionException
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> good =
                CompletableFuture.completedFuture(5);
        CompletableFuture<Integer> bad =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("origin failed"));

        try {
            good.whenComplete((value, error) -> {
                throw new IllegalStateException("observer failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("observerOnSuccess=" + rootType(error));
        }

        try {
            bad.whenComplete((value, error) -> {
                throw new IllegalStateException("observer failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("observerOnFailure=" + rootType(error));
        }

        try {
            bad.exceptionally(error -> {
                throw new IllegalStateException("recovery failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("failedRecovery=" + rootType(error));
        }

        try {
            good.handle((value, error) -> {
                throw new IllegalStateException("handler failed");
            }).join();
        } catch (CompletionException error) {
            System.out.println("failedHandle=" + rootType(error));
        }

        CompletableFuture<Integer> recovered =
                bad.exceptionally(error -> 100);
        System.out.println("recoveredThenApply="
                + recovered.thenApply(value -> value + 1).join());
        System.out.println("originalStillExceptional="
                + bad.isCompletedExceptionally());
    }
}
```

Chạy:

```bash
javac --release 17 CallbackFailureDemo.java
java CallbackFailureDemo
```

Đầu ra:

```text
observerOnSuccess=IllegalStateException
observerOnFailure=IllegalArgumentException
failedRecovery=IllegalStateException
failedHandle=IllegalStateException
recoveredThenApply=101
originalStillExceptional=true
```

Trong hai dòng đầu, callback `whenComplete` đều ném `IllegalStateException`; nhưng khi nguồn đã lỗi sẵn, stage mới vẫn giữ lỗi `IllegalArgumentException` từ nguồn. Dòng thứ ba và thứ tư cho thấy bản thân callback phục hồi/xử lý có thể là nguồn lỗi mới. Hai dòng cuối nhắc rằng một stage được khôi phục bằng `exceptionally` sẽ cho phép `thenApply` chạy tiếp, còn **stage gốc vẫn thất bại**.

Đây là ví dụ dùng future đã hoàn tất để minh họa ngữ nghĩa và đầu ra ổn định; trong pipeline bất đồng bộ thật, thứ tự callback không được suy ra chỉ từ thứ tự gắn chúng.

## 9. Khác biệt quan trọng giữa phục hồi và chỉ quan sát

Giả sử `CompletableFuture<Integer> failed` đã hoàn tất lỗi.

```java
CompletableFuture<Integer> withFallback =
        failed.exceptionally(error -> 0);

CompletableFuture<Integer> handled =
        failed.handle((value, error) -> error == null ? value : 0);

CompletableFuture<Integer> observed =
        failed.whenComplete((value, error) -> logError(error));
```

Đây là **đoạn minh họa** cần `failed` và `logError(Throwable)` được khai báo. Nếu callback đều chạy bình thường, hai stage đầu **phục hồi bằng `0`**, còn stage `observed` **tiếp tục thất bại**. Không được viết code phía sau giả định `observed.join()` sẽ trả `0`.

Một sơ đồ phụ thuộc:

```text
                       failed (exceptional)
                        /       |         \
                       /        |          \
             exceptionally    handle     whenComplete
                   |             |             |
               result = 0    result = 0   vẫn exceptional
                   |             |             |
                thenApply     thenApply      join() báo lỗi
                  chạy          chạy
```

Cần hiểu “phục hồi” là **stage mới hoàn tất bình thường** khi callback trả giá trị. Nó không sửa dữ liệu đã thay đổi trước lúc lỗi xảy ra, không rollback DB, không dừng một tác vụ I/O đang chạy và không làm stage nguồn thành công.

Nếu người gọi cần biết rằng kết quả là fallback, hãy đưa metadata vào kiểu kết quả, ví dụ `Outcome<T>` có trạng thái `REAL`/`FALLBACK`, thay vì chỉ trả một số có thể trùng giá trị thành công thực tế.

## 10. Thứ tự ghép stage làm thay đổi chính sách lỗi

Ba phương thức là thành phần của pipeline. **Đặt chúng trước hoặc sau một stage tính toán** có thể tạo kết quả khác.

### Phục hồi trước rồi mới biến đổi

```java
CompletableFuture<Integer> result =
        failed.exceptionally(error -> 10)
              .thenApply(value -> value * 2);
```

Đây là đoạn minh họa với `CompletableFuture<Integer> failed`. Nếu `failed` lỗi, callback trả `10` và `thenApply` nhận giá trị `10`, tạo ra `20`. Bước tính tiếp theo **không biết** `10` là fallback nếu kiểu dữ liệu không mang cờ phân biệt.

### Biến đổi trước rồi phục hồi

```java
CompletableFuture<Integer> result =
        source.thenApply(value -> transform(value))
              .exceptionally(error -> 10);
```

Đoạn này yêu cầu `source` và `transform(...)`. `exceptionally` đặt sau `thenApply` có thể phục hồi cả lỗi từ **nguồn** lẫn lỗi do `transform` ném. Nếu ứng dụng chỉ muốn fallback cho lỗi đọc nguồn mà **không** che lỗi lập trình trong bước chuyển đổi, cần điều chỉnh vị trí hoặc phân loại lỗi.

### Quan sát sau khi phục hồi

```java
CompletableFuture<Integer> observed =
        failed.exceptionally(error -> 10)
              .whenComplete((value, error) -> {
                  System.out.println("error=" + error);
              });
```

Đây là đoạn minh họa. `whenComplete` nhìn thấy kết quả của **stage ngay trước nó**; nếu `exceptionally` đã phục hồi thì `error == null`. Muốn log nguyên nhân gốc, có thể quan sát **trước khi phục hồi**:

```java
CompletableFuture<Integer> observedAndRecovered =
        failed.whenComplete((value, error) -> {
                  if (error != null) {
                      report(error);
                  }
              })
              .exceptionally(error -> 10);
```

Đoạn này cần hàm `report(Throwable)` của ứng dụng. `whenComplete` giữ lỗi, vì thế `exceptionally` phía sau vẫn nhìn được đường lỗi để xử lý. Nếu `report` ném lỗi, phải hiểu quy tắc lỗi của `whenComplete` và thiết kế logger/metric đáng tin cậy.

## 11. `CompletionException`, `ExecutionException` và cause gốc

Khi một stage thất bại, loại `Throwable` được callback nhìn thấy có thể là ngoại lệ gốc hoặc một lớp bọc kỹ thuật do pipeline tạo ra. Không phụ thuộc cứng vào việc `error.getClass()` luôn là lỗi nghiệp vụ gốc.

- `join()` có thể ném `CompletionException` (unchecked) với `getCause()` trỏ đến lỗi gốc.
- `get()` có thể ném `ExecutionException` (checked) với cause của thất bại.
- `whenComplete`, `handle`, `exceptionally` nhận đối tượng `Throwable` đại diện cho trạng thái lỗi của **stage đầu vào**. Tùy đường đi, một trong các lớp bọc có thể xuất hiện.

Ví dụ gỡ các wrapper kỹ thuật quen thuộc:

```java
Throwable meaningful(Throwable error) {
    Throwable current = error;
    while ((current instanceof java.util.concurrent.CompletionException
            || current instanceof java.util.concurrent.ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Đây là **phương thức minh họa trong một lớp Java**, không phải chương trình độc lập. Nó bỏ qua hai loại lớp bọc cụ thể để lấy ngoại lệ có ý nghĩa gần nhất, **không** tự động bỏ mọi wrapper nghiệp vụ. Nếu dùng dữ liệu lỗi từ nguồn không kiểm soát được, tiện ích tổng quát còn cần cân nhắc chuỗi cause bất thường và giới hạn độ sâu để tránh vòng lặp ngoài ý muốn.

**Ghi log cả `Throwable`**, không chỉ `getMessage()`, nếu cần stack trace, cause và suppressed exceptions. Chỉ lấy exception sâu nhất rồi bỏ qua ngữ cảnh tầng cao có thể khiến khó tìm nơi chuyển đổi lỗi.

## 12. Hủy và timeout: không tự biến lỗi thành thành công

Một future bị hủy hoặc bị timeout cũng có thể dẫn đến callback xử lý lỗi:

- `CompletableFuture.cancel(...)` có thể hoàn tất future bằng trạng thái hủy. Khi xử lý lỗi ở stage phụ thuộc, callback có thể nhận `CancellationException` hoặc một lớp bọc của nó tùy đường đi.
- `orTimeout(...)` hoàn tất future đang chờ **bất thường** với `TimeoutException` nếu deadline đến trước.
- `completeOnTimeout(fallback, ...)` hoàn tất future đang chờ **bình thường** với fallback nếu deadline đến trước; khi đó `exceptionally` phía sau sẽ không được gọi vì stage đã thành công.

Các phương thức xử lý lỗi không tự **dừng công việc thực tế**. Nếu một supplier đang ghi file hoặc gọi dịch vụ, `exceptionally(error -> defaultValue)` không hủy I/O, không bù trừ tác dụng phụ và không bảo đảm supplier đã kết thúc. Không dùng “recovered future” như chứng cứ giao dịch gốc đã hoàn tất thành công.

Chỉ trả fallback khi an toàn: timeout của một widget hiển thị có thể được phép dùng dữ liệu cache, còn timeout của giao dịch thanh toán cần trạng thái rõ ràng và có thể phải đối soát.

## 13. Synchronous và `Async` variants: callback chạy ở đâu?

Ba API có các biến thể bất đồng bộ hữu ích trong nhiều phiên bản JDK, gồm `handleAsync`, `whenCompleteAsync` và `exceptionallyAsync` trên Java 17. Với phiên bản không có hậu tố `Async`, các dependent actions **có thể chạy bởi luồng hoàn tất stage hoặc một luồng khác đang thực hiện thao tác hoàn tất**, không có bảo đảm chúng luôn chạy trên cùng worker đã chạy supplier.

Ví dụ minh họa:

```java
CompletableFuture<String> result =
        source.handleAsync((value, error) -> {
            return error == null ? value : "fallback";
        }, applicationExecutor);
```

Đoạn mã yêu cầu `source` có kiểu `CompletableFuture<String>` và `applicationExecutor` là một `Executor`. Việc cung cấp executor rõ ràng giúp chọn nơi chạy callback; vẫn phải xử lý trường hợp executor từ chối lên lịch hoặc ứng dụng shutdown.

Không thực hiện I/O chặn lâu hoặc xử lý CPU nặng trong `whenComplete` đồng bộ chỉ vì nó trông giống “callback logging”. Một callback chậm có thể làm luồng hoàn tất bị chiếm giữ; nếu dùng logging bất đồng bộ, xác định rõ tương quan lỗi và yêu cầu không làm mất dữ liệu chẩn đoán.

Dù chạy đồng bộ hay bất đồng bộ, **ngữ nghĩa phục hồi** của ba họ API vẫn theo hợp đồng: `exceptionally` có thể trả fallback khi lỗi, `handle` chuyển cả hai nhánh, `whenComplete` chủ yếu quan sát.

## 14. Test chiến lược phục hồi, không chỉ test callback đã chạy

Với hệ thống thật, test tốt phải xác nhận cả **stage nguồn** và **stage nhận kết quả**, đồng thời gây lỗi ở nhiều vị trí:

| Kịch bản | `exceptionally` | `handle` | `whenComplete` |
| --- | --- | --- | --- |
| Nguồn thành công `7` | Không chạy recovery; nhận `7` | Callback chạy, có thể nhận `14` | Callback chạy, vẫn nhận `7` |
| Nguồn lỗi | Callback chạy; có thể trả fallback | Callback chạy; có thể trả fallback/`Outcome` | Quan sát lỗi; future sau thường vẫn lỗi |
| Callback tự ném khi nguồn thành công | Không chạy callback | Stage mới lỗi | Stage mới lỗi |
| Callback tự ném khi nguồn đã lỗi | Stage mới lỗi bởi callback | Stage mới lỗi bởi callback | Lỗi nguồn được ưu tiên |
| Nguồn thành công bằng `null` | Không recovery | `error == null`, `value == null` vẫn là thành công | Tương tự, chỉ quan sát |
| Có fallback rồi `thenApply` | `thenApply` chạy với fallback | `thenApply` chạy nếu handle thành công | `thenApply` chỉ chạy khi stage được quan sát vẫn thành công |
| Có lỗi timeout/hủy | Cần phân loại trước khi fallback | Cần phân loại trước khi fallback | Quan sát và tiếp tục truyền lỗi nếu không ném |

Test không nên chỉ assert `isDone()` vì future lỗi/hủy cũng là done. Hãy kiểm tra `join()`, `isCompletedExceptionally()`, loại cause, giá trị fallback, tác dụng phụ callback và điều kiện phục hồi. Nếu một lỗi bị che thành thành công, test cần bắt được.

### Ví dụ JUnit 5 cho nguồn thất bại

Đây là **đoạn kiểm thử minh họa**, yêu cầu dependency JUnit Jupiter, import `@Test` và `Assertions.*`:

```java
@Test
void exceptionallyRecoversButSourceStaysFailed() {
    CompletableFuture<Integer> source =
            CompletableFuture.failedFuture(
                    new IllegalArgumentException("bad input"));

    CompletableFuture<Integer> recovered =
            source.exceptionally(error -> -1);

    assertEquals(-1, recovered.join());
    assertFalse(recovered.isCompletedExceptionally());
    assertTrue(source.isCompletedExceptionally());
}

@Test
void whenCompleteDoesNotConsumeFailure() {
    CompletableFuture<Integer> source =
            CompletableFuture.failedFuture(
                    new IllegalArgumentException("bad input"));

    CompletableFuture<Integer> observed =
            source.whenComplete((value, error) -> {});

    CompletionException exception =
            assertThrows(CompletionException.class, observed::join);
    assertInstanceOf(IllegalArgumentException.class,
            exception.getCause());
}
```

Đoạn test cần import các lớp concurrency; nó không chạy độc lập chỉ với JDK. Test đầu tiên kiểm tra phục hồi đúng nhưng không làm nguồn thành công. Test thứ hai kiểm tra `whenComplete` **không tự tiêu thụ** lỗi.

### Test callback ném lỗi

Nên có các ca tương ứng với `CallbackFailureDemo`:

- `whenComplete` ném trong khi nguồn thành công → stage quan sát mới thất bại.
- `whenComplete` ném trong khi nguồn đã thất bại → lỗi nguồn vẫn là lỗi được stage sau báo ra.
- `exceptionally` ném trong recovery → stage mới vẫn lỗi.
- `handle` ném khi xử lý → stage mới vẫn lỗi.
- Gắn `exceptionally` sau `thenApply` → cần kiểm tra liệu nó có vô tình che lỗi chuyển đổi không.

Khi callback chứa logic điều chỉnh trạng thái, còn phải assert DB/side effect/fallback hợp lệ, không chỉ loại `Throwable`.

## 15. Lỗi thường gặp và cách tránh

| Hiểu nhầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| “`whenComplete` đã log là lỗi đã được xử lý.” | Stage sau vẫn thất bại, `join()` vẫn ném | Dùng `exceptionally`/`handle` nếu thực sự cần phục hồi |
| “`exceptionally` luôn chạy sau mọi stage.” | Callback không chạy ở nhánh thành công | Gắn logic chung vào `handle` hoặc `whenComplete` |
| “`handle` chỉ nhận giá trị thành công.” | Không xử lý đúng `error` | Luôn kiểm tra `error != null`; value có thể `null` |
| “`value == null` nghĩa là lỗi.” | Nhầm nguồn thành công bằng `null` | Dùng trường `error` để phân biệt |
| “`whenComplete` không bao giờ thay trạng thái.” | Callback tự ném có thể biến thành công thành lỗi | Đảm bảo callback quan sát đáng tin cậy |
| “Callback action lỗi sẽ luôn thay lỗi nguồn.” | Hiểu sai ưu tiên của `whenComplete` | Nếu nguồn đã lỗi, lỗi nguồn được ưu tiên |
| “Phục hồi bằng fallback làm future gốc hết lỗi.” | Giám sát sai trạng thái | Phân biệt source stage và dependent stage |
| “Dùng `exceptionally(e -> 0)` là an toàn cho mọi lỗi.” | Che bug, lỗi phân quyền hoặc dữ liệu sai | Phân loại lỗi, chỉ fallback khi hợp đồng cho phép |
| “`whenComplete` là nơi có thể đóng mọi resource.” | Có thể đóng resource khi supplier vẫn hoạt động | Đặt cleanup trong phạm vi sở hữu tài nguyên |
| “`isDone()` nghĩa là thao tác nghiệp vụ thành công.” | Ghi nhận thành công giả | Kiểm tra trạng thái hoàn tất và hậu điều kiện |
| “Các callback luôn chạy theo thứ tự gắn.” | Race hoặc kết quả log khác kỳ vọng | Dùng quan hệ stage và đồng bộ khi cần |
| “`join()` trả lỗi gốc trực tiếp trong mọi trường hợp.” | Bắt sai exception và bỏ cause | Xét `CompletionException`, `CancellationException`, cause |
| “`get()` và `join()` giống hệt nhau.” | Bỏ sót checked exceptions ở `get()` | Phân biệt `ExecutionException`, `InterruptedException` |
| “Một `handle` trả `null` là chắc chắn lỗi.” | Nhầm giá trị null hợp lệ | Có thể hoàn tất bình thường bằng null |
| “Callback bị lỗi thì có thể bỏ qua.” | Stage mới thất bại không được quan sát | Gắn kết quả vào pipeline và có ranh giới xử lý |

## 16. Quy trình chọn API theo mục tiêu

1. **Chỉ muốn ghi log, đo metric hoặc quan sát một stage?** Chọn `whenComplete`. Đừng giả định lỗi được phục hồi.
2. **Chỉ muốn thay lỗi đã được phân loại bằng một giá trị dự phòng cùng kiểu?** Chọn `exceptionally`. Kiểm tra fallback có hợp lệ và đủ metadata không.
3. **Muốn xử lý cả hai nhánh thành công/lỗi thành kiểu kết quả mới?** Chọn `handle`. Nó hữu ích để tạo `Outcome<T>`, một mã trạng thái hoặc bản ghi kết quả chung.
4. **Muốn retry bằng một tác vụ bất đồng bộ khác?** Cần một luồng retry có giới hạn và API kết hợp stage; không coi `exceptionally` trả một `CompletableFuture` là tương đương flat-map trong mọi trường hợp.
5. **Muốn giữ lỗi để tầng khác quyết định?** Đừng ép fallback. Dùng `whenComplete` quan sát (nếu cần) rồi để exception lan truyền.
6. **Muốn chắc chắn công việc thực tế dừng?** Thiết kế cancellation/deadline ở executor/I/O; ba callback này không cung cấp bảo đảm dừng vật lý.

Đặt callback **ở đúng ranh giới**: logging trước phục hồi nếu cần thấy lỗi gốc; fallback sau bước được phép thất bại; tránh `handle` bao trùm nhiều giai đoạn khi một bug của giai đoạn cuối không nên bị che.

## 17. Bài tập thực hành

**Bài 1 — kiểm chứng fallback.** Tạo `CompletableFuture.failedFuture(new IllegalArgumentException("x"))`, gắn `exceptionally(error -> -1)`. So sánh `isCompletedExceptionally()` của nguồn và stage mới. **Kỳ vọng:** nguồn `true`, stage mới `false`, `join()` của stage mới trả `-1`.

**Bài 2 — thành công vẫn qua `handle`.** Tạo future hoàn tất với `5`, gắn `handle((value, error) -> error == null ? "OK:" + value : "FAIL")`. **Kỳ vọng:** stage mới có kiểu `CompletableFuture<String>`, `join()` trả `"OK:5"`.

**Bài 3 — quan sát không phục hồi.** Tạo future thất bại, gắn `whenComplete` chỉ ghi log. Gọi `join()` trên stage trả về. **Kỳ vọng:** vẫn nhận lỗi (thường dưới `CompletionException`).

**Bài 4 — callback tự lỗi.** Dựa trên `CallbackFailureDemo`, thay callback `whenComplete` bằng action ném `IllegalStateException` ở cả future thành công và thất bại. **Kỳ vọng:** nếu nguồn thành công, stage mới báo `IllegalStateException`; nếu nguồn đã lỗi, lỗi nguồn được ưu tiên.

**Bài 5 — giá trị thành công `null`.** Tạo `CompletableFuture.completedFuture(null)` rồi gắn `handle((value, error) -> error == null ? "SUCCESS" : "FAIL")`. **Kỳ vọng:** `"SUCCESS"` dù `value == null`.

**Bài 6 — thứ tự stage.** Một `thenApply` cố tình ném `ArithmeticException`. Gắn `exceptionally` trước hoặc sau `thenApply` rồi so sánh kết quả. **Kỳ vọng:** fallback đặt trước không nhất thiết phục hồi lỗi phát sinh ở `thenApply`; fallback đặt sau có thể nhìn thấy và phục hồi lỗi đó.

**Bài 7 — tránh che bug.** Trong `exceptionally`, chỉ phục hồi `TimeoutException`; với `NullPointerException` thì tiếp tục ném lỗi. **Kỳ vọng:** lỗi timeout nhận fallback, bug nội bộ vẫn thất bại.

**Bài 8 — outcome có metadata.** Dùng `handle` để trả một record chứa thành công thật hay thất bại cùng mã lỗi. **Kỳ vọng:** caller không phải đoán việc fallback từ một giá trị `0` hoặc chuỗi rỗng.

## 18. Tài liệu tham khảo

- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `exceptionally`, `handle`, `whenComplete`, các biến thể `Async` và trạng thái hoàn tất.
- [Java SE 17 — `CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): hợp đồng kết hợp stage, truyền exception và ưu tiên lỗi của callback.
- [Java SE 17 — `CompletionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html): lớp bọc lỗi khi quan sát bất đồng bộ.
- [Java SE 17 — `ExecutionException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): lỗi checked nhận từ `Future.get()`.
- [Java SE 17 — `TimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): phân loại thời hạn chờ và phục hồi theo timeout.

**Ghi nhớ:** `exceptionally` là **phục hồi riêng đường lỗi**; `handle` là **biến đổi cả thành công lẫn thất bại**; `whenComplete` là **quan sát mà bình thường không thay kết quả**. Việc callback trả fallback làm stage mới thành công, **không làm stage gốc hết lỗi**, không xóa tác dụng phụ và không bảo đảm công việc nền đã dừng. Viết test cho nhánh thành công, nhánh lỗi, callback tự ném và thứ tự ghép stage trước khi đưa chính sách phục hồi vào production.