# Truy nguyên nhân qua lớp bọc của tác vụ bất đồng bộ trong `CompletableFuture`

Một tác vụ bất đồng bộ có thể thất bại tại nơi đọc dữ liệu, chuyển đổi dữ liệu hoặc gọi dịch vụ bên ngoài, nhưng luồng chờ kết quả lại nhận được `CompletionException` hoặc `ExecutionException`. Nếu chỉ nhìn vào tên lớp ngoại lệ ngoài cùng, người lập trình dễ kết luận nhầm rằng chính `CompletableFuture` gây lỗi. Cách chẩn đoán đúng là **phân biệt lớp bọc báo thất bại bất đồng bộ với ngoại lệ gốc do nghiệp vụ hoặc mã thực thi ném ra**, rồi lần theo chuỗi `getCause()` có kiểm soát.

Bài này tập trung vào việc **truy nguyên nhân thất bại** khi dùng `CompletableFuture` trong Java: lỗi bắt đầu ở đâu, được chuyển qua các stage thế nào, xuất hiện dưới dạng nào khi gọi `join()` hoặc `get()`, và làm sao ghi log, xử lý và kiểm thử mà vẫn giữ đủ ngữ cảnh.

## 1. Mô hình tư duy: nơi lỗi sinh ra khác nơi lỗi được nhìn thấy

Giả sử luồng chính gọi `CompletableFuture.supplyAsync(...)` để tải dữ liệu. Mã bên trong supplier ném `IllegalStateException("storage unavailable")`. Tại thời điểm này có ba tầng khái niệm:

1. **Nguồn phát sinh lỗi** (*origin*): đoạn công việc thực tế thất bại, chẳng hạn supplier, lambda của `thenApply`, hoặc bước chuyển đổi trong `thenCompose`.
2. **Trạng thái của stage** (*exceptional completion*): `CompletableFuture` ghi nhận công việc đã kết thúc với lỗi. Các stage phụ thuộc có thể tiếp tục truyền tình trạng thất bại mà không thực thi các hàm chỉ xử lý giá trị thành công.
3. **Điểm quan sát** (*observation boundary*): nơi gọi `join()`, `get()`, hoặc một callback xử lý kết quả nhận thông tin lỗi, có thể thông qua ngoại lệ bọc.

Luồng nguyên nhân có thể hình dung như sau:

```text
Supplier/Stage ném IllegalStateException
                |
                v
CompletableFuture hoàn tất với lỗi
                |
        +-------+--------+
        |                |
        v                v
      join()            get()
        |                |
        v                v
 CompletionException   ExecutionException
        \                /
         \-- getCause() /
                 |
                 v
     IllegalStateException gốc
```

Sơ đồ mô tả **trường hợp phổ biến**. Chuỗi nguyên nhân thực tế có thể có nhiều tầng do ứng dụng chủ động bọc thêm ngoại lệ, hoặc có thể là một loại ngoại lệ hoàn tất đặc biệt như hủy (`CancellationException`). Không nên giả định rằng *mọi* thất bại đều có đúng một lớp bọc.

Điểm quan trọng: stack trace ở nơi gọi `join()`/`get()` cho thấy nơi **phát hiện** lỗi; stack trace của nguyên nhân sâu bên trong thường gần nơi **ném lỗi ban đầu** hơn. Cần đọc cả hai khi điều tra.

## 2. Các loại ngoại lệ dễ gặp và ý nghĩa của chúng

| Loại ngoại lệ | Vai trò thông thường | Thường xuất hiện ở đâu? |
| --- | --- | --- |
| `CompletionException` | Ngoại lệ runtime dùng để biểu diễn hoàn tất thất bại của một `CompletionStage` | `join()`, `getNow()`, hoặc được chuyển qua các stage |
| `ExecutionException` | Ngoại lệ checked dùng bởi `Future.get()` để báo rằng công việc được đợi đã thất bại | `get()` và `get(timeout, unit)` |
| Ngoại lệ nghiệp vụ/kỹ thuật gốc | Lỗi thực tế: `IllegalArgumentException`, `IOException`, `IllegalStateException`, lỗi từ SDK… | `getCause()` của lớp bọc, hoặc bên trong chuỗi cause |
| `CancellationException` | Biểu thị công việc đã bị hủy | Có thể được ném trực tiếp từ `join()`/`get()` khi chính future đó bị hủy |
| `InterruptedException` | Luồng **đang chờ** `get()` bị ngắt | `get()`, khác với việc tác vụ bất đồng bộ ném lỗi |
| `TimeoutException` | `get(timeout, unit)` hết thời gian chờ; hoặc một stage bị hoàn tất thất bại qua `orTimeout(...)` | Trường hợp đầu ném trực tiếp khi chờ; trường hợp sau có thể nằm trong cause của ngoại lệ bọc |

Đối với `CompletableFuture`, `join()` là API tiện dụng ném ngoại lệ unchecked; `get()` tuân theo hợp đồng `Future` và ném `ExecutionException` checked khi kết quả thất bại. Với một công việc ném ngoại lệ thông thường, ta thường thấy:

```text
join() --> CompletionException --> IllegalStateException
get()  --> ExecutionException  --> IllegalStateException
```

Nếu trạng thái hoàn tất đã mang `CompletionException`, `get()` thường dựng `ExecutionException` mà `cause` là **nguyên nhân được giữ trong `CompletionException`**, chứ không nhất thiết chèn thêm `CompletionException` làm một tầng trung gian. Ngược lại, ứng dụng có thể chủ động ném một ngoại lệ đã được bọc nhiều lớp; khi ấy chuỗi cause thực tế sâu hơn. Hãy kiểm tra cây nguyên nhân thay vì đoán số lớp dựa trên API.

**Đừng đồng nhất `isDone()` với thành công:** `isDone()` trả `true` khi future kết thúc bình thường, thất bại hoặc bị hủy. `isCompletedExceptionally()` có thể giúp nhận biết trạng thái bất thường, nhưng không cho biết chính xác loại lỗi hay nguồn gốc; cần nhận `Throwable` để điều tra.

## 3. Ví dụ Java 17+: lỗi gốc hiện ra khác nhau qua `join()` và `get()`

Tạo tệp **`AsyncFailureTrace.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AsyncFailureTrace {
    static Throwable unwrapAsync(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> source =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalStateException("storage unavailable");
                });

        CompletableFuture<Integer> mapped =
                source.thenApply(value -> value * 2);

        try {
            mapped.join();
        } catch (CompletionException error) {
            Throwable root = unwrapAsync(error);
            System.out.println("join wrapper=" + error.getClass().getSimpleName());
            System.out.println("join root=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }

        try {
            mapped.get();
        } catch (ExecutionException error) {
            Throwable root = unwrapAsync(error);
            System.out.println("get wrapper=" + error.getClass().getSimpleName());
            System.out.println("get root=" + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }

        CompletableFuture<Integer> recovered = mapped.exceptionally(error -> {
            Throwable root = unwrapAsync(error);
            System.out.println("callback root=" + root.getClass().getSimpleName());
            return -1;
        });

        System.out.println("fallback=" + recovered.join());
        System.out.println("source exceptional=" + source.isCompletedExceptionally());
        System.out.println("recovered exceptional="
                + recovered.isCompletedExceptionally());
    }
}
```

Chạy bằng Java 17+:

```bash
javac AsyncFailureTrace.java
java AsyncFailureTrace
```

Đầu ra:

```text
join wrapper=CompletionException
join root=IllegalStateException: storage unavailable
get wrapper=ExecutionException
get root=IllegalStateException: storage unavailable
callback root=IllegalStateException
fallback=-1
source exceptional=true
recovered exceptional=false
```

**Vì sao kết quả ổn định?** `join()` đầu tiên đợi cho `mapped` hoàn tất rồi mới đọc lỗi; `get()` sau đó đọc lại chính kết quả đã hoàn tất. Callback `exceptionally(...)` được gắn vào một stage đã thất bại và phải hoàn tất trước khi `recovered.join()` trả về. Không có thứ tự in phụ thuộc vào tốc độ của worker.

Giải thích:

- Lỗi đầu tiên sinh ra trong supplier, mang kiểu `IllegalStateException`, thông điệp `storage unavailable`.
- `mapped` không có giá trị thành công nên phép nhân trong `thenApply` không chạy. Sự thất bại tiếp tục truyền đến `mapped`.
- `mapped.join()` báo `CompletionException`, còn `mapped.get()` báo `ExecutionException`. Hàm `unwrapAsync` lấy được `IllegalStateException` trong cả hai tình huống.
- `exceptionally(...)` nhận một `Throwable` đại diện cho thất bại của stage trước và **biến lỗi thành giá trị dự phòng** `-1`. Vì vậy `source` vẫn thất bại, nhưng `recovered` hoàn tất thành công.

Hàm `unwrapAsync` được thiết kế để bỏ qua **hai lớp bọc kỹ thuật cụ thể**, giữ nguyên một ngoại lệ thuộc miền nghiệp vụ hoặc kỹ thuật khi đã gặp. Đây là cách phù hợp cho đường đi lỗi thông thường. Không nên tự động đi đến cause cuối cùng của *mọi* `Throwable`, vì một ngoại lệ nghiệp vụ có thể chủ động bọc một nguyên nhân thấp hơn nhưng vẫn là mức trừu tượng mà người gọi cần xử lý.

## 4. Đọc chuỗi `getCause()` đúng cách

Mỗi `Throwable` có thể chứa một ngoại lệ nguyên nhân thông qua `getCause()`. Để chẩn đoán đầy đủ, nên xác định:

- **Ngoại lệ ở ranh giới quan sát:** lớp ngoài cùng mà `join()`, `get()` hoặc callback cung cấp.
- **Ngoại lệ sau khi bỏ lớp bọc bất đồng bộ:** kết quả của việc gỡ `CompletionException` và `ExecutionException` nếu có.
- **Các ngoại lệ nguyên nhân sâu hơn:** ví dụ `ServiceException` được tạo với `new ServiceException("cannot fetch", sqlException)`; việc giữ `ServiceException` có thể giúp tầng nghiệp vụ hiểu ngữ cảnh, còn `sqlException` giúp chẩn đoán tầng dữ liệu.
- **Thông tin ngữ cảnh của stage:** tên thao tác, khóa yêu cầu, tham số an toàn để ghi log, bước pipeline; Java không tự ghi tên nghiệp vụ của lambda vào thông điệp lỗi.
- **Ngoại lệ bị kèm theo** qua `Throwable.getSuppressed()` nếu mã đã sử dụng `addSuppressed` hoặc có lỗi bổ sung khi đóng tài nguyên trong `try-with-resources`. Những lỗi này không nằm trong chuỗi `getCause()` chính.

Ví dụ khái niệm:

```text
CompletionException
  cause -> OrderLookupException("lookup failed")
             cause -> IOException("connection reset")
```

Nếu chỉ in `error.getMessage()`, thông tin nguồn có thể bị thiếu hoặc chỉ chứa tên lớp của lỗi bọc. Nếu chỉ lấy cause sâu nhất, ngược lại sẽ mất ngữ cảnh rằng thất bại thuộc thao tác tra cứu đơn hàng. Nên **ghi toàn bộ stack trace của `Throwable`** ở một ranh giới ghi log phù hợp, rồi chọn ngoại lệ cần xử lý theo chính sách ứng dụng.

Đây là mẫu xử lý trong callback, **đặt trong phạm vi đã có `CompletableFuture<Order> future` và logger của ứng dụng**:

```java
CompletableFuture<Order> observed = future.whenComplete((order, error) -> {
    if (error != null) {
        Throwable meaningful = unwrapAsync(error);
        logger.error("Order lookup failed", meaningful);
    }
});
```

Mẫu trên là đoạn minh họa, không phải lớp độc lập: `Order`, `future`, `logger` và `unwrapAsync` cần do ứng dụng khai báo. Lưu ý `whenComplete(...)` trả về **một stage mới** (`observed`), nên hãy dùng stage đó ở phía sau nếu việc quan sát là một phần của pipeline.

Khi ghi log trên hệ thống thật, cung cấp `Throwable` cho logger để nhận stack trace và chuỗi cause, tránh chỉ ghi `cause.toString()`. Cũng tránh đưa bí mật hoặc dữ liệu cá nhân vào thông điệp ngữ cảnh.

## 5. Ngoại lệ được truyền qua và xử lý ở từng stage ra sao?

Một chuỗi stage hoạt động theo trạng thái:

- `thenApply`, `thenAccept`, `thenRun` và các thao tác phụ thuộc chỉ chạy nhánh xử lý giá trị thành công khi stage trước hoàn tất bình thường. Nếu stage trước thất bại, stage phụ thuộc thường hoàn tất thất bại mà không chạy phần xử lý giá trị.
- `thenCompose` có thể nhận một stage con. Lỗi ở stage con trở thành thất bại của stage kết hợp; lúc truy nguyên phải biết nó đến từ stage được trả về, không chỉ từ hàm bên ngoài.
- `exceptionally(error -> fallback)` chạy khi stage trước thất bại; nếu lambda trả một giá trị bình thường thì stage mới **được phục hồi**. Nếu lambda lại ném lỗi, stage mới có thể thất bại vì lỗi trong chính bước xử lý.
- `handle((value, error) -> ...)` chạy với cả hai kiểu hoàn tất và có thể đổi giá trị/lỗi thành một kết quả mới. Với lỗi, `value` thường là `null`; với hoàn tất bình thường, `error` là `null`. Giá trị thành công hợp lệ cũng có thể là `null`, nên đừng dựa riêng vào `value == null` để kết luận thất bại.
- `whenComplete((value, error) -> ...)` phù hợp để quan sát và thêm log; bình thường nó giữ kết quả hoặc lỗi cũ cho stage trả về. Nếu callback tự ném trong khi đầu vào thành công, stage trả về sẽ thất bại. Nếu đầu vào đã thất bại và callback cũng ném lỗi, lỗi ban đầu vẫn được ưu tiên theo hợp đồng API.

Ví dụ thứ hai chỉ ra khác biệt giữa **quan sát lỗi**, **chuyển lỗi thành giá trị** và **lỗi mới do chính callback tạo ra**.

Tạo tệp **`StageObservation.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class StageObservation {
    static Throwable meaningful(Throwable error) {
        Throwable current = error;
        while (current instanceof CompletionException
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> failed = CompletableFuture.failedFuture(
                new IllegalArgumentException("invalid item"));

        CompletableFuture<Integer> observed = failed.whenComplete((value, error) -> {
            if (error != null) {
                System.out.println("observed=" + meaningful(error).getMessage());
            }
        });

        try {
            observed.join();
        } catch (CompletionException error) {
            System.out.println("observed failure="
                    + meaningful(error).getClass().getSimpleName());
        }

        CompletableFuture<Integer> handled =
                observed.handle((value, error) -> error == null ? value : 10);
        System.out.println("handle result=" + handled.join());
        System.out.println("original exceptional=" + failed.isCompletedExceptionally());

        CompletableFuture<Integer> good = CompletableFuture.completedFuture(5);
        CompletableFuture<Integer> badObserver = good.whenComplete((value, error) -> {
            throw new IllegalStateException("audit failed");
        });
        try {
            badObserver.join();
        } catch (CompletionException error) {
            System.out.println("observer failure="
                    + meaningful(error).getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac StageObservation.java
java StageObservation
```

Đầu ra:

```text
observed=invalid item
observed failure=IllegalArgumentException
handle result=10
original exceptional=true
observer failure=IllegalStateException
```

Nhánh `whenComplete` đầu tiên chỉ quan sát và giữ lỗi; vì thế `observed.join()` vẫn thất bại. Nhánh `handle` đổi lỗi đó thành kết quả `10`, còn `failed` vẫn mang trạng thái lỗi. Ở trường hợp cuối, stage gốc `good` hoàn tất thành công nhưng callback quan sát tự ném `IllegalStateException`, khiến **stage trả về** `badObserver` thất bại. Khi điều tra phải nhìn chính xác stage nào là stage được chờ.

## 6. Truy nguyên nhân trong chuỗi nhiều bước

Với pipeline dài, chỉ lấy ngoại lệ gốc đôi khi chưa đủ biết **bước nào** hỏng, nhất là khi nhiều bước cùng có thể ném `IllegalArgumentException` hoặc `IOException`.

Ví dụ minh họa (không biên dịch độc lập; `load`, `parse`, `save` và các kiểu phụ thuộc cần được định nghĩa trong ứng dụng):

```java
CompletableFuture<Result> pipeline =
        CompletableFuture.supplyAsync(() -> load(key))
                .thenApply(raw -> parse(raw))
                .thenApply(parsed -> save(parsed));
```

Có thể bổ sung ngữ cảnh **tại ranh giới bước** bằng một ngoại lệ thích hợp, nhưng phải giữ cause:

```java
.thenApply(raw -> {
    try {
        return parse(raw);
    } catch (IllegalArgumentException error) {
        throw new ParseStageException("Invalid document format", error);
    }
})
```

Đoạn trên cũng là minh họa cần một lớp `ParseStageException` và hàm `parse`. Ngoại lệ mới cho biết **vai trò bước**; `error` được truyền vào constructor làm cause để không mất dấu vết thấp hơn. Nếu không có yêu cầu đổi tầng trừu tượng, chỉ thêm callback quan sát và để lỗi lan truyền có thể đơn giản hơn.

Một mẫu đánh dấu ranh giới phù hợp là dùng `whenComplete` tại các điểm quan trọng:

```java
CompletableFuture<Data> loaded = CompletableFuture
        .supplyAsync(() -> loadData())
        .whenComplete((value, error) -> {
            if (error != null) {
                reportFailure("loadData", error);
            }
        });
```

Đây là đoạn minh họa phụ thuộc `Data`, `loadData()` và `reportFailure(...)`. Hàm `reportFailure` nên tránh tự ném lỗi; nếu nó ném, stage mới do `whenComplete` trả về có thể mang lỗi mới trong trường hợp nguồn trước đó thành công. Trong hệ thống có tracing, thêm mã tương quan yêu cầu (*correlation ID*) vào ngữ cảnh stage để liên hệ log của các worker với log ở luồng gọi.

**Không nên bọc lại lỗi ở mọi stage** chỉ để được một stack trace dài. Quá nhiều lớp bọc khó đọc và thường che loại ngoại lệ mà tầng trên cần xử lý.

## 7. Khi nhiều tác vụ cùng thất bại: `allOf` và `anyOf`

`CompletableFuture.allOf(a, b, c)` tạo một future hoàn tất khi **tất cả** các future đầu vào kết thúc. Nếu có future đầu vào thất bại, future tổng cũng hoàn tất thất bại, nhưng ngoại lệ nhận được từ `allOf(...).join()` **không phải danh sách đầy đủ mọi lỗi**. Khi nhiều tác vụ thất bại, API không bảo đảm rằng cause duy nhất ấy có thể đại diện cho tất cả nguyên nhân.

Để điều tra từng tác vụ, cần **giữ các future thành phần** và kiểm tra từng cái sau khi `allOf` hoàn tất. Ví dụ phần kiểm tra, đặt trong phương thức đã có `CompletableFuture<?>[] tasks`:

```java
CompletableFuture<Void> all = CompletableFuture.allOf(tasks);
try {
    all.join();
} catch (CompletionException | java.util.concurrent.CancellationException ignored) {
    // Không kết luận lỗi của toàn bộ các task chỉ từ ngoại lệ tổng.
}

for (int index = 0; index < tasks.length; index++) {
    try {
        tasks[index].join();
    } catch (CompletionException error) {
        System.err.println("task " + index + ": " + unwrapAsync(error));
    } catch (java.util.concurrent.CancellationException cancelled) {
        System.err.println("task " + index + ": cancelled");
    }
}
```

Đây là đoạn mã minh họa, sử dụng `unwrapAsync` ở ví dụ trước. `tasks` phải là mảng các future hợp lệ. `allOf` giúp tất cả future đầu vào đã hoàn tất trước vòng duyệt, nhờ đó `join()` ở từng phần tử không tiếp tục chờ công việc còn chạy. Khi log, nên giữ `Throwable` cùng stack trace; mã trên chỉ in tóm tắt để minh họa luồng xử lý.

`CompletableFuture.anyOf(...)` khác: future tổng hoàn tất khi có **một** thành phần hoàn tất (bình thường hoặc thất bại). Do đó trạng thái của `anyOf` chỉ mô tả kết quả đầu tiên, **không khẳng định** các future khác đã xong hay thành công. Đừng dùng lỗi của `anyOf` để kết luận về mọi tác vụ còn lại.

Nếu ứng dụng cần một báo cáo tổng hợp *tất cả* lỗi, hãy thiết kế cấu trúc thu thập từng kết quả/ngoại lệ và đặt nhãn tác vụ rõ ràng; không giả định `getSuppressed()` trên ngoại lệ tổng sẽ tự chứa đầy đủ các lỗi từ `allOf`.

## 8. Phân biệt lỗi từ tác vụ với lỗi khi chờ, hủy hoặc lên lịch

Đây là các trường hợp rất dễ gây nhầm lẫn khi chỉ nhìn vào exception ngoài cùng:

### 8.1. Hết thời gian chờ của `get(timeout, unit)`

Nếu gọi `future.get(100, TimeUnit.MILLISECONDS)` trước khi công việc kết thúc, người chờ có thể nhận `TimeoutException` **trực tiếp**. Điều đó chỉ nói rằng lần chờ này hết hạn: future vẫn có thể đang chạy và hoàn tất bình thường sau đó. Không nên ghi log “tác vụ thất bại vì TimeoutException” chỉ từ trường hợp này.

Ngược lại, `future.orTimeout(100, TimeUnit.MILLISECONDS)` thiết lập để **chính future hoàn tất thất bại với `TimeoutException`** nếu quá hạn. Khi quan sát future đã thất bại bằng `join()` hoặc `get()`, lỗi có thể xuất hiện dưới lớp bọc tương ứng. Hai trường hợp cần được phân biệt trong chẩn đoán.

### 8.2. Luồng chờ bị ngắt

`future.get()` có thể ném `InterruptedException` khi **luồng đang chờ** bị ngắt. Đây không tự động là ngoại lệ mà supplier đã ném. Nếu không truyền tiếp được, mã bắt `InterruptedException` thường nên gọi `Thread.currentThread().interrupt()` để bảo toàn tín hiệu, rồi rời luồng xử lý thích hợp. `join()` không khai báo `InterruptedException`, nhưng điều đó không có nghĩa nó có thể biến yêu cầu ngắt thành lỗi nghiệp vụ của tác vụ.

### 8.3. Hủy với `cancel(...)`

`CompletableFuture.cancel(boolean)` hoàn tất future theo trạng thái hủy nếu chưa hoàn tất. Với chính triển khai `CompletableFuture`, đối số `mayInterruptIfRunning` **không dùng để điều khiển thực thi bằng interrupt**; việc hủy future không bảo đảm dừng công việc vật lý đang chạy trong supplier. Khi gọi `join()`/`get()` trên **future đã trực tiếp bị hủy**, `CancellationException` có thể được ném trực tiếp. Một stage phụ thuộc có thể mang `CompletionException` bọc `CancellationException`. Do đó, nếu cần báo “hủy” riêng, hãy xét cả `isCancelled()` khi phù hợp và chuỗi cause.

### 8.4. Executor không nhận tác vụ

Khi gọi `CompletableFuture.supplyAsync(supplier, executor)`, executor có thể từ chối lên lịch, chẳng hạn vì đã shutdown; `RejectedExecutionException` có thể xảy ra **ngay khi gọi phương thức gửi**, trước khi trả về một `CompletableFuture`. Đây là lỗi ở giai đoạn **nộp công việc**, khác với lỗi phát sinh trong supplier rồi được lưu thành exceptional completion.

Mã gọi cần phân biệt hai ranh giới:

```java
CompletableFuture<String> future;
try {
    future = CompletableFuture.supplyAsync(() -> fetch(), executor);
} catch (java.util.concurrent.RejectedExecutionException error) {
    // Chưa nhận được future hợp lệ từ lời gọi bị từ chối.
    throw error;
}

// Tại đây mới theo dõi kết quả và lỗi của future sau khi đã được tạo.
```

Đây là mã minh họa yêu cầu `fetch` và `executor` do ứng dụng cung cấp. Không dùng `try/catch` quanh mỗi lời gọi `supplyAsync` như cách duy nhất để “bắt lỗi bên trong supplier”: lỗi trong supplier thường được quan sát qua future khi hoàn tất.

## 9. Mẫu xử lý lỗi có ngữ cảnh và không bỏ sót nguyên nhân

Một chiến lược nhất quán ở ranh giới của ứng dụng gồm:

1. **Đặt tên cho từng bước** trong pipeline để biết nơi xử lý thất bại.
2. **Giữ nguyên cause** khi chuyển một ngoại lệ kỹ thuật thành ngoại lệ có ý nghĩa nghiệp vụ.
3. **Chỉ gỡ các lớp bọc được nhận diện rõ** (`CompletionException`, `ExecutionException`) khi chọn loại lỗi để xử lý. Khi ghi log chi tiết, giữ toàn bộ exception/stack trace.
4. **Phân biệt phục hồi với quan sát:** `exceptionally` và `handle` có thể đổi trạng thái thành thành công; `whenComplete` thường dùng để quan sát mà giữ lỗi.
5. **Không bỏ quên stage cuối.** Nếu không ai chờ/quan sát stage và không có hệ thống giám sát khác, lỗi có thể bị giữ trong future mà không đến nơi xử lý.
6. **Xác định điểm ghi log chính** để tránh cùng một lỗi xuất hiện lặp lại vô ích trong nhiều callback. Log tầng bước khi cần thêm ngữ cảnh; tầng ngoài có thể ra quyết định chuyển sang phản hồi lỗi, báo động hoặc thử lại.
7. **Giữ đường đi của hủy và timeout riêng** với lỗi nghiệp vụ. Nếu cần thử lại, tránh tự động thử lại lỗi lập trình hoặc thao tác có tác dụng phụ mà không có điều kiện an toàn.

Có thể định nghĩa một helper “gỡ lớp bọc bất đồng bộ” ở vị trí dùng chung, với chú thích rõ ràng rằng kết quả trả về là *ngoại lệ có ý nghĩa gần nhất*, không bắt buộc là cause sâu nhất trong toàn bộ chuỗi. Với dữ liệu lỗi lấy từ những nguồn không kiểm soát được, cần cân nhắc chuỗi cause bất thường (vòng tham chiếu, chiều sâu quá lớn) để tránh vòng lặp không kết thúc; không nên viết hàm unwrapping tổng quát mà không nêu hợp đồng.

## 10. Lỗi thường gặp và câu hỏi tự kiểm tra

| Hiểu nhầm | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| “`CompletionException` chính là lỗi nghiệp vụ gốc.” | Chỉ thấy wrapper, bỏ qua lỗi thật | Kiểm tra `getCause()` và loại ngoại lệ bên trong |
| “`get()` với `join()` luôn tạo chuỗi cause giống nhau.” | Bắt sai lớp và chẩn đoán thiếu tầng | `get()` dùng `ExecutionException`; `join()` thường dùng `CompletionException` |
| “Một stage `thenApply` ở cuối không chạy nghĩa là chính stage đó ném lỗi.” | Quy kết sai vị trí lỗi | Lỗi có thể truyền từ stage trước khiến lambda cuối bị bỏ qua |
| “`whenComplete` đã log thì future mới chắc thành công.” | Lỗi tiếp tục truyền, nhưng bị bỏ sót | `whenComplete` thường giữ lỗi cũ; `handle`/`exceptionally` mới có thể phục hồi |
| “`allOf` trả đủ mọi lỗi.” | Bỏ sót những tác vụ cùng thất bại | Đọc từng future thành phần nếu cần tập hợp mọi nguyên nhân |
| “`isDone()` trả `true` tức tác vụ thành công.” | Nhận nhầm kết thúc thất bại thành thành công | Kiểm tra kết quả hoặc `isCompletedExceptionally()` và xử lý throwable |
| “`get(timeout)` ném TimeoutException tức supplier ném lỗi timeout.” | Nhầm timeout của luồng chờ thành lỗi của tác vụ | Phân biệt timeout ở lời gọi chờ và `orTimeout(...)` hoàn tất lỗi |
| “`cancel(true)` chắc chắn interrupt được supplier của `CompletableFuture`.” | Giả định sai về việc tác vụ thực sự dừng | Hủy future không đồng nghĩa cưỡng bức dừng công việc |
| “Cứ tìm `getCause()` sâu nhất là luôn có lỗi cần bắt.” | Mất ngữ cảnh nghiệp vụ của wrapper có ý nghĩa | Chỉ gỡ wrapper kỹ thuật, giữ toàn bộ chuỗi khi log |

Tự kiểm tra:

**Câu 1.** Supplier ném `IllegalArgumentException`, pipeline không phục hồi. Gọi `join()` thường bắt gì, và xem lỗi gốc ở đâu? **`CompletionException`**, rồi đọc `getCause()` (và các lớp kỹ thuật nếu có) để gặp `IllegalArgumentException`.

**Câu 2.** Cùng future trên, gọi `get()` báo gì? **`ExecutionException`**; `getCause()` chứa nguyên nhân khiến tác vụ hoàn tất thất bại.

**Câu 3.** `future.exceptionally(error -> 0)` trả stage mới. Nếu nguồn lỗi, stage mới có thể thành công không? **Có**, khi callback trả `0` bình thường. Future nguồn vẫn thất bại.

**Câu 4.** `allOf(a, b)` hoàn tất thất bại, cả `a` và `b` đều lỗi. Lỗi của `allOf` có đủ dữ liệu để kết luận chính xác cả hai nguyên nhân không? **Không**. Cần đọc từng future.

**Câu 5.** `future.get(100, MILLISECONDS)` báo timeout nhưng vài giây sau `future.join()` trả giá trị. Có mâu thuẫn không? **Không**: lần chờ đầu hết hạn, trong khi future vẫn có thể tiếp tục và hoàn tất thành công.

**Câu 6.** Một stage `whenComplete` tự ném khi stage nguồn thành công. Lỗi của stage mới từ đâu? **Từ chính callback quan sát**; phải kiểm tra stage nào được chờ và nơi ngoại lệ thực sự sinh ra.

Để truy được lỗi bất đồng bộ, hãy bắt đầu từ **stage đang thất bại**, kiểm tra **loại wrapper tại nơi quan sát**, gỡ đúng **lớp bọc kỹ thuật** để tìm **ngoại lệ có ý nghĩa**, rồi dùng **stack trace và ngữ cảnh của từng bước** để xác định vị trí lỗi. Cách làm này giúp giữ được cả thông tin lỗi gốc lẫn đường đi của lỗi qua chuỗi `CompletableFuture`.

## Tham khảo API

- [Java 21 API — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): hợp đồng của `get`, `join`, `handle`, `whenComplete`, `allOf`, `orTimeout` và `cancel`.
- [Java 21 API — `CompletionException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionException.html) và [Java 21 API — `ExecutionException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutionException.html): hai dạng ngoại lệ bọc thường gặp.