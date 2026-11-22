# CompletableFuture: `orTimeout()`, `completeOnTimeout()` và fallback

## 1. Vì sao cần timeout khi xử lý bất đồng bộ?

Một `CompletableFuture<T>` đại diện cho kết quả có thể xuất hiện trong tương lai. Nó có thể hoàn thành thành công, hoàn thành với lỗi, hoặc **chưa bao giờ hoàn thành** nếu công việc bị treo, phản hồi quá lâu hay nhà cung cấp không báo kết quả. Nếu các bước tiếp theo chỉ chờ future đó, toàn bộ luồng xử lý có thể chậm theo.

**Timeout** là giới hạn thời gian chờ *một kết quả bất đồng bộ*. **Fallback** là cách ứng xử thay thế khi kết quả không có kịp hoặc bị lỗi, chẳng hạn dùng dữ liệu cache, trả kết quả mặc định có kiểm soát, hay chuyển sang một nguồn dự phòng. Hai quyết định này liên quan nhưng không đồng nhất: timeout xác định *khi nào ngừng chờ*; fallback xác định *trả gì hoặc làm gì sau đó*.

Trong Java 9+, `CompletableFuture` cung cấp hai phương thức trực tiếp:

~~~java
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit)
CompletableFuture<T> completeOnTimeout(T value, long timeout, TimeUnit unit)
~~~

Cả hai đều **trả về chính instance `CompletableFuture` đang gọi**, lên lịch xử lý timeout nếu future còn pending, và **không chặn thread đang gọi**. Chúng không tạo request mới, không tự động dừng việc tính toán nền, và không biến toàn bộ chuỗi lệnh thành một giao dịch có khả năng rollback.

## 2. Hai cách kết thúc khi hết hạn

| Khía cạnh | `orTimeout(t, unit)` | `completeOnTimeout(value, t, unit)` |
|---|---|---|
| Nếu hoàn thành trước hạn | Giữ nguyên giá trị hoặc lỗi đã có | Giữ nguyên giá trị hoặc lỗi đã có |
| Nếu vẫn pending tại hạn | Hoàn thành **exceptionally** với `TimeoutException` | Hoàn thành **normally** với `value` dự phòng |
| `join()` sau khi timeout | Ném `CompletionException` có nguyên nhân là `TimeoutException` | Trả về `value` |
| `thenApply(...)` | Không chạy trên kết quả bị timeout; chuyển lỗi xuống stage sau | Chạy tiếp trên giá trị dự phòng |
| `exceptionally(...)` | Có thể bắt lỗi timeout để phục hồi | Không được gọi chỉ vì default đã được trả thành công |
| Có tự hủy công việc gốc? | Không | Không |
| Có tạo future mới? | Không, trả `this` | Không, trả `this` |

Hình dung một future đang pending tại `t = 0`, timeout đặt là 200 ms:

~~~text
t = 0 ms                 t = 200 ms                   t = 500 ms
  |--------------------------|-----------------------------|
  bắt đầu tác vụ            hết hạn                       tác vụ nền trả về muộn

orTimeout:                  TimeoutException              kết quả muộn không đổi được future
completeOnTimeout("cache"): giá trị "cache"                kết quả muộn không đổi được future
~~~

Nếu tương lai đã hoàn thành trước 200 ms (bằng thành công, lỗi, hoặc bị hủy), lịch timeout không thay thế trạng thái đó. Đây là cuộc đua hoàn thành: **lần hoàn thành có hiệu lực đầu tiên thắng**. Ví dụ, gọi `complete("muộn")` sau khi timeout đã kết thúc future sẽ trả `false`.

**Lưu ý về đơn vị:** `unit` là `TimeUnit` như `MILLISECONDS` hoặc `SECONDS`. Cần đặt timeout theo ngân sách độ trễ thực tế; mốc hẹn giờ của hệ thống không bảo đảm chính xác tuyệt đối từng mili giây do việc lập lịch thread và tải máy.

## 3. Ví dụ Java 17 chạy độc lập: so sánh ba kịch bản

Tạo file `TimeoutDemo.java` với đúng nội dung:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimeoutDemo {

    public static void main(String[] args) {
        // 1) Không có ai complete: orTimeout kết thúc bằng lỗi.
        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> same = first.orTimeout(30, TimeUnit.MILLISECONDS);
        System.out.println(first == same);

        try {
            first.join();
        } catch (CompletionException ex) {
            System.out.println(ex.getCause() instanceof TimeoutException);
        }
        System.out.println(first.isCompletedExceptionally());
        System.out.println(first.complete("kết quả quá muộn"));

        // 2) Vẫn pending khi hết hạn: completeOnTimeout cho giá trị mặc định.
        CompletableFuture<String> second = new CompletableFuture<>();
        String defaultResult = second
                .completeOnTimeout("cache", 30, TimeUnit.MILLISECONDS)
                .join();
        System.out.println(defaultResult);
        System.out.println(second.isCompletedExceptionally());

        // 3) orTimeout tạo lỗi; exceptionally chọn riêng fallback cho timeout.
        CompletableFuture<String> third = new CompletableFuture<>();
        String recovered = third
                .orTimeout(30, TimeUnit.MILLISECONDS)
                .exceptionally(error -> {
                    Throwable cause = unwrap(error);
                    if (cause instanceof TimeoutException) {
                        return "fallback timeout";
                    }
                    throw new CompletionException(cause);
                })
                .join();
        System.out.println(recovered);
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac TimeoutDemo.java
java TimeoutDemo
~~~

Kết quả chuẩn:

~~~text
true
true
true
false
cache
false
fallback timeout
~~~

Giải thích theo thứ tự:

1. `first == same` in `true`: `orTimeout()` trả về cùng object, không phải một future độc lập.
2. `join()` đợi future và ném `CompletionException`; `getCause()` là `TimeoutException`. `first` ở trạng thái hoàn thành với lỗi (`isCompletedExceptionally() == true`).
3. `complete("kết quả quá muộn")` trả `false` vì trạng thái cuối đã được quyết định.
4. `second` hoàn thành bình thường bằng `"cache"`; `isCompletedExceptionally()` là `false`.
5. `third` bị timeout, nhưng stage **mới** do `exceptionally()` trả về phục hồi thành `"fallback timeout"`; lỗi khác được ném tiếp.

Ví dụ chủ động để các future pending mà không tạo tác vụ I/O, giúp thấy rõ semantics của API và có stdout ổn định; nó không ngụ ý timeout sẽ dừng một cuộc gọi mạng hoặc công việc đang chạy.

## 4. Fallback khác nhau thế nào?

### 4.1. Default cố định bằng `completeOnTimeout`

~~~java
CompletableFuture<String> result = remoteFuture
        .completeOnTimeout("Chưa có dữ liệu, dùng bản cache", 800, TimeUnit.MILLISECONDS);
~~~

`remoteFuture` là một `CompletableFuture<String>` đã tồn tại trong ứng dụng (đoạn trên minh họa một bước, không phải chương trình độc lập). Nếu hoàn thành trước 800 ms, giá trị/lỗi của nó được giữ nguyên; nếu vẫn pending, future hoàn thành **thành công** bằng chuỗi mặc định. Người dùng downstream không phân biệt được dữ liệu thật và fallback chỉ từ trạng thái hoàn thành. Khi cần phân biệt, nên thiết kế kiểu kết quả có trường `source`/`isFallback` hoặc dùng kiểu dữ liệu riêng.

Nếu nguồn thất bại sớm bằng `IOException` hay `IllegalStateException`, `completeOnTimeout` **không** biến lỗi đó thành default: phương thức chỉ xử lý trạng thái chưa hoàn thành khi hết thời gian.

### 4.2. Timeout thành lỗi, rồi phục hồi có điều kiện

~~~java
CompletableFuture<String> result = remoteFuture
        .orTimeout(800, TimeUnit.MILLISECONDS)
        .exceptionally(error -> {
            Throwable cause = unwrap(error);
            if (cause instanceof TimeoutException) {
                return "cache";
            }
            throw new CompletionException(cause);
        });
~~~

`unwrap` là hàm trong ví dụ độc lập ở phần 3. Cách này cho phép **chỉ fallback khi lỗi là timeout**; lỗi lập trình, dữ liệu không hợp lệ và lỗi hệ thống khác vẫn truyền xuống downstream. Đây là khác biệt đáng kể với:

~~~java
.exceptionally(error -> "cache")
~~~

Câu lệnh ngắn này nuốt **mọi** lỗi, dễ che giấu lỗi lập trình hoặc lỗi hạ tầng. Chỉ dùng khi hợp đồng nghiệp vụ thực sự chấp nhận một giá trị dự phòng cho bất kỳ lỗi nào.

**Về `CompletionException`:** `join()` thường gói lỗi trong `CompletionException`; ở callback của một stage, nguyên nhân có thể là `TimeoutException` trực tiếp hoặc đã được bọc qua stage khác. Vì thế ví dụ xử lý cả hai. `get()` khác `join()`: `get()` là API checked exception, có thể ném `ExecutionException` và `InterruptedException`. Không dùng `exception.getClass() == TimeoutException.class` trên mọi tầng vì dễ bỏ sót lỗi đã bọc.

### 4.3. Fallback thực hiện một tác vụ bất đồng bộ khác

Nếu fallback cần đọc cache bất đồng bộ hoặc thử nhà cung cấp thứ hai, `exceptionally()` nhận callback trả về **giá trị `T`**, không trả về một `CompletableFuture<T>` đã được tự động làm phẳng. Từ Java 12, sử dụng `exceptionallyCompose()` để trả về một future dự phòng:

~~~java
// Ví dụ minh họa trong một service đã có remoteFuture, cacheExecutor,
// readCache() và unwrap() của phần 3.
CompletableFuture<String> result = remoteFuture
        .orTimeout(800, TimeUnit.MILLISECONDS)
        .exceptionallyCompose(error -> {
            Throwable cause = unwrap(error);
            if (cause instanceof TimeoutException) {
                return CompletableFuture.supplyAsync(this::readCache, cacheExecutor);
            }
            return CompletableFuture.failedFuture(cause);
        });
~~~

Ở đây `readCache()` trả về `String`. Khi timeout, nhánh dự phòng chạy trên `cacheExecutor`; khi lỗi khác xảy ra, future kết quả vẫn thất bại. `failedFuture` có từ Java 9, `exceptionallyCompose` có từ Java 12. Đoạn code chỉ minh họa các thành phần của service, nên không chạy riêng nếu chưa định nghĩa `remoteFuture`, `cacheExecutor` và `readCache()`. Nếu không có API `exceptionallyCompose`, có thể kết hợp `handle()` tạo future rồi `thenCompose(f -> f)` để làm phẳng.

**Không đánh đồng fallback với retry:** fallback có thể trả dữ liệu cũ, dùng nguồn thứ hai, hoặc báo trạng thái tạm thời. Retry sẽ khởi chạy tác vụ mới, cần có giới hạn số lần và ngân sách thời gian riêng. Trong các thao tác có side effect, retry có thể gây gọi lặp nếu không bảo đảm tính idempotent.

## 5. Tác động của timeout lên chuỗi stage

`CompletableFuture` gồm các stage phụ thuộc. Timeout là một cách **hoàn thành future đang gọi**, do đó ảnh hưởng đến downstream:

~~~java
CompletableFuture<Integer> length = pendingText
        .orTimeout(500, TimeUnit.MILLISECONDS)
        .thenApply(String::length);
~~~

Nếu `pendingText` hết hạn, `length` hoàn thành exceptional, `String::length` không chạy. Với giá trị mặc định:

~~~java
CompletableFuture<Integer> length = pendingText
        .completeOnTimeout("N/A", 500, TimeUnit.MILLISECONDS)
        .thenApply(String::length);
~~~

Nếu chưa hoàn thành khi hết hạn, `thenApply` nhận `"N/A"` và trả `3`. Nếu tác vụ ban đầu thất bại trước hạn, `thenApply` vẫn không chạy. Các đoạn trên giả định `pendingText` là future chưa được hoàn thành từ nơi khác; chúng là ví dụ ghép chuỗi trong một ứng dụng, không phải chương trình độc lập.

### Ba toán tử xử lý kết quả thường bị nhầm

| Toán tử | Chạy khi thành công? | Chạy khi lỗi? | Có thể phục hồi thành giá trị mới? |
|---|---|---|---|
| `exceptionally(fn)` | Không | Có | Có, bằng `T` |
| `handle((value, error) -> ...)` | Có | Có | Có, bằng giá trị trả về của callback |
| `whenComplete((value, error) -> ...)` | Có | Có | **Không**; chủ yếu quan sát/log, giữ kết quả/lỗi đầu vào nếu callback không ném lỗi |

Ví dụ dùng `handle` khi muốn ghi rõ cả hai trạng thái:

~~~java
CompletableFuture<String> display = timedFuture.handle((value, error) -> {
    if (error == null) {
        return value;
    }
    if (unwrap(error) instanceof TimeoutException) {
        return "đang dùng cache";
    }
    throw new CompletionException(unwrap(error));
});
~~~

Với `whenComplete`, code như `whenComplete((v, e) -> log(e))` chỉ **quan sát**; việc log không khiến future bị lỗi chuyển thành thành công. Để phục hồi phải dùng `exceptionally`, `handle` hoặc `exceptionallyCompose`.

### Đừng vô tình đặt timeout lên future chia sẻ

Vì `orTimeout` và `completeOnTimeout` sửa trạng thái của **future gốc đang gọi**, cùng một `CompletableFuture` được nhiều nơi sử dụng sẽ có thể bị timeout theo ngân sách của một người tiêu thụ:

~~~java
CompletableFuture<String> shared = loadSharedValue();

// View là một dependent stage riêng; timeout chỉ đặt trên view.
CompletableFuture<String> view = shared
        .thenApply(value -> value)
        .orTimeout(200, TimeUnit.MILLISECONDS)
        .exceptionally(error -> {
            if (unwrap(error) instanceof TimeoutException) {
                return "fallback riêng";
            }
            throw new CompletionException(unwrap(error));
        });
~~~

Ví dụ trên là đoạn minh họa khi `loadSharedValue()` trả về `CompletableFuture<String>`. `shared` không bị `orTimeout` hoàn thành cưỡng bức; `view` có timeout riêng. Java 9+ cũng có `shared.copy()` để tạo dependent `CompletableFuture` với giá trị/lỗi được truyền từ nguồn; có thể gắn timeout vào bản sao thay vì lên `shared`. Việc tạo view **không nhân bản hoặc hủy công việc nền**. Nếu ứng dụng gọi hai cơ chế timeout trực tiếp trên cùng một instance, chúng sẽ cùng cạnh tranh hoàn thành instance đó; cơ chế thắng phụ thuộc thứ tự thời điểm thực tế.

## 6. Timeout bất đồng bộ không có nghĩa là hủy tác vụ

Giả sử một `CompletableFuture` bắt nguồn từ `supplyAsync(() -> slowOperation(), executor)`. Khi `orTimeout` hết hạn, future có thể báo lỗi trong lúc `slowOperation()` **vẫn chạy** trên executor. Khi `completeOnTimeout` hết hạn, người tiêu thụ có thể nhận fallback nhưng tác vụ cũ vẫn làm việc và tạo side effect. Kết quả trả về muộn không thể ghi đè trạng thái future đã hoàn thành.

Điều này dẫn đến ba trách nhiệm khác nhau:

1. **Giới hạn thời gian nhìn từ caller:** `orTimeout` / `completeOnTimeout` quyết định trạng thái future sau hạn.
2. **Giới hạn tác vụ thực tế:** thư viện I/O, HTTP, JDBC, socket hay tác vụ nền có cơ chế timeout/hủy riêng. Cần thiết lập timeout thích hợp ở lớp thực hiện công việc (ví dụ connect/read timeout) nếu muốn hạn chế tài nguyên.
3. **Dọn dẹp tài nguyên và tính đúng đắn:** công việc nền phải đóng tài nguyên, kiểm soát số lượng công việc đồng thời, và cân nhắc side effect xuất hiện sau khi caller đã dùng fallback.

Ngay cả `CompletableFuture.cancel(true)` cũng không bảo đảm ngắt thread của tác vụ `supplyAsync`: đối số `mayInterruptIfRunning` không làm cơ chế này tự động điều khiển việc ngắt xử lý. Nếu bắt buộc hủy vật lý, cần thiết kế giao thức hủy và/hoặc cơ chế hủy riêng do nguồn công việc hỗ trợ.

`orTimeout` có thể giúp caller phản hồi sớm, nhưng **không thay thế** timeout cấp I/O và kiểm soát tài nguyên executor.

## 7. So với `get(timeout, unit)` và `join()`

Ba cách sau khác nhau về ý nghĩa:

| Cách gọi | Thread gọi có chờ không? | Tự kết thúc future nếu quá hạn? | Kết quả khi quá hạn |
|---|---|---|---|
| `future.get(200, MILLISECONDS)` | Có, tối đa thời gian chờ | Không | `TimeoutException` được ném cho thread gọi; future có thể vẫn pending |
| `future.join()` | Có, đến khi hoàn thành | Không | Không có timeout tự thân |
| `future.orTimeout(200, MILLISECONDS)` | Không khi gọi phương thức này | Có, nếu future còn pending | Future hoàn thành exceptional với `TimeoutException`; `join()` sau đó có thể ném `CompletionException` |
| `future.completeOnTimeout(fallback, 200, MILLISECONDS)` | Không khi gọi phương thức này | Có, nếu future còn pending | Future hoàn thành normally với `fallback` |

Ví dụ: nếu `get(200, MILLISECONDS)` ném `TimeoutException`, code khác vẫn có thể gọi `future.complete("xong")` thành công sau đó. Ngược lại, nếu chính `future.orTimeout(...)` đã kích hoạt, future được hoàn thành exceptional và không chấp nhận một `complete` đến muộn.

Gọi `join()` ở cuối ví dụ phần 3 là để demo và kiểm tra đầu ra. Trong ứng dụng bất đồng bộ, nếu không cần chuyển sang xử lý đồng bộ, ưu tiên ghép các stage thay vì chặn thread bằng `join()` hay `get()`.

## 8. Thiết kế fallback theo loại lỗi và yêu cầu nghiệp vụ

Không có một fallback đúng cho mọi tình huống. Quyết định phù hợp thường dựa trên:

- **Độ tin cậy của kết quả dự phòng:** cache có thể cũ; cần quyết định thời gian dữ liệu còn chấp nhận được. Với phép tính đòi hỏi tính chính xác cao, một giá trị mặc định có thể gây hiểu nhầm.
- **Độ rõ ràng của nguồn dữ liệu:** nếu người gọi cần biết đang dùng cache, nên trả kiểu như `Result(value, source)`, thay vì cố giấu fallback vào chuỗi kết quả bình thường.
- **Lỗi nào được phục hồi:** timeout, thất bại tạm thời hay tất cả lỗi? Không nên nuốt `NullPointerException` hoặc lỗi validation chỉ để trả thông báo thành công.
- **Tổng ngân sách độ trễ:** nếu timeout chính là 800 ms và fallback lại có thể tốn 2 giây, toàn bộ tác vụ vẫn có thể vượt kỳ vọng. Tách hạn cho nhánh dự phòng khi cần.
- **Tác vụ nền và side effect:** nếu request gốc vẫn ghi dữ liệu sau khi caller trả fallback, cần cơ chế tránh xử lý trùng/lỗi trạng thái.
- **Khả năng quan sát:** ghi nhận số lần timeout, tỷ lệ fallback và độ trễ; phân biệt kết quả thật với fallback, đồng thời tránh log dữ liệu nhạy cảm.

Một cấu trúc phục hồi thực dụng khi cùng một future được dùng ở nhiều nơi:

~~~java
// Hàm minh họa có thể đặt trong class utility Java 17+.
// unwrap(Throwable) giống ví dụ chạy độc lập ở phần 3.
static <T> CompletableFuture<T> withTimeoutFallback(
        CompletableFuture<T> source,
        T fallback,
        long timeout,
        TimeUnit unit) {

    return source.copy()
            .orTimeout(timeout, unit)
            .exceptionally(error -> {
                Throwable cause = unwrap(error);
                if (cause instanceof TimeoutException) {
                    return fallback;
                }
                throw new CompletionException(cause);
            });
}
~~~

Hàm trên chỉ fallback khi nhận `TimeoutException`; lỗi khác được truyền tiếp. `source.copy()` tạo bản sao stage để tránh thay đổi trạng thái `source` khi timeout và cho phép caller dùng chính sách timeout riêng. Tuy nhiên, vì chỉ nhìn vào loại `TimeoutException`, nó cũng sẽ fallback nếu nguồn đã thất bại với loại lỗi đó do một nguyên nhân khác; nếu cần phân biệt **chính xác** timeout do policy này với timeout nội bộ của nguồn, phải có cơ chế đánh dấu nguyên nhân hoặc phối hợp chính sách lỗi cụ thể.

Giá trị fallback được truyền vào hàm trên là giá trị **đã tính sẵn**. Nếu tính fallback tốn kém, nên khởi động nó có điều kiện khi lỗi xảy ra bằng `exceptionallyCompose` (như phần 4.3), tránh làm việc dư thừa ở trường hợp thành công bình thường.

## 9. Lỗi hay gặp và cách tự kiểm tra

1. **Tưởng `orTimeout` tự trả giá trị mặc định.** Thực tế nó tạo kết quả exceptional; dùng `exceptionally`/`handle` để phục hồi, hoặc dùng `completeOnTimeout` nếu default cố định phù hợp.
2. **Tưởng `completeOnTimeout` xử lý cả lỗi xảy ra trước hạn.** Nó chỉ áp dụng khi future còn pending tại thời điểm timeout; lỗi sớm vẫn là lỗi.
3. **Dùng `exceptionally(error -> fallback)` mà không phân loại lỗi.** Nhánh này che cả lỗi lập trình; nên kiểm tra nguyên nhân và ném tiếp lỗi không muốn phục hồi.
4. **Gắn timeout trực tiếp lên future được chia sẻ.** Người tiêu thụ khác cũng thấy future đó bị kết thúc; tạo dependent stage hoặc `copy()` nếu cần ngân sách độc lập.
5. **Cho rằng timeout đã giải phóng thread hoặc hủy I/O.** Future có thể đã kết thúc nhưng tác vụ vẫn chạy; cần timeout của nguồn, hủy hợp tác và quản lý executor riêng.
6. **Gọi `join()`/`get()` liên tục trong xử lý bất đồng bộ.** Điều này có thể chặn thread và giảm khả năng mở rộng; ưu tiên ghép stage với `thenApply`, `thenCompose`, `handle`.
7. **Không kiểm soát đường fallback.** Fallback quá chậm, bị lỗi, dữ liệu quá cũ hoặc tạo side effect cũng làm hệ thống không đáp ứng hợp đồng; cần thiết kế và đo riêng.
8. **Đặt nhiều deadline trực tiếp trên cùng future.** Các hành động cạnh tranh trạng thái; chỉ lần hoàn thành có hiệu lực đầu tiên thắng và kết quả thực tế có thể phụ thuộc lịch chạy.

Tự kiểm tra:

- Future hoàn thành thành công ở 100 ms, `completeOnTimeout("cache", 200, MILLISECONDS)` trả gì? **Giá trị thật** vì future đã hoàn thành trước hạn.
- Future hoàn thành exceptionally ở 50 ms, `completeOnTimeout("cache", 200, MILLISECONDS)` có che lỗi không? **Không**, lỗi sớm được giữ nguyên.
- `get(200, MILLISECONDS)` ném timeout thì future đã chuyển sang exceptional chưa? **Chưa chắc và không do lời gọi `get`**; timeout đó giới hạn riêng thao tác chờ của caller.
- Tác vụ `supplyAsync` chạy lâu hơn `orTimeout` thì có chắc dừng không? **Không**; deadline của future và vòng đời thực thi của tác vụ là hai chuyện riêng.

## 10. Chọn API cho từng mục đích

- Muốn **báo timeout là lỗi** để caller quyết định: dùng `orTimeout()` và để exception truyền xuống.
- Muốn **trả một giá trị dự phòng cố định chỉ khi quá hạn**: dùng `completeOnTimeout(value, ...)`, cân nhắc cách đánh dấu nguồn fallback.
- Muốn **fallback theo loại lỗi**: dùng `orTimeout(...).exceptionally(...)` hoặc `handle(...)` và giữ nguyên lỗi không thuộc diện phục hồi.
- Muốn **fallback là một tác vụ async khác**: dùng `exceptionallyCompose(...)` (Java 12+) và quản lý timeout riêng của fallback nếu cần.
- Muốn **mỗi caller có deadline khác nhau** trên cùng một nguồn: tạo dependent stage/`copy()` trước khi đặt timeout.

Điểm mấu chốt: **`orTimeout()` hoàn thành exceptional; `completeOnTimeout()` hoàn thành normal bằng default; cả hai tác động đến chính future được gọi và không tự hủy tác vụ đang chạy.** Thiết kế fallback đúng nghĩa phải xác định loại lỗi được chấp nhận, chất lượng giá trị dự phòng và cách kiểm soát công việc còn chạy sau deadline.
