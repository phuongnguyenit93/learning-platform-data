# invokeAll() và invokeAny() có thời hạn: xử lý tác vụ chưa hoàn tất

## 1. Đặt thời hạn cho một nhóm Callable

`ExecutorService` cho phép giao một tập `Callable<T>` để chạy trên pool. Đôi khi chúng ta cần tất cả kết quả; đôi khi chỉ cần một kết quả thành công từ nhiều phương án tương đương. Trong cả hai trường hợp, một tác vụ chậm hoặc bị kẹt có thể làm thread gọi chờ quá lâu. Hai overload có timeout giúp đặt **ngân sách chờ chung cho cả batch**:

```java
<T> List<Future<T>> invokeAll(
    Collection<? extends Callable<T>> tasks,
    long timeout, TimeUnit unit) throws InterruptedException;

<T> T invokeAny(
    Collection<? extends Callable<T>> tasks,
    long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;
```

Đây là chữ ký API minh họa, không phải chương trình Java độc lập. Các bản không có timeout cũng tồn tại. Timeout tính cho toàn lời gọi (gồm giao task và chờ), **không phải timeout riêng cho từng task**. Các overload có timeout sử dụng `TimeUnit` như `MILLISECONDS` hoặc `SECONDS`.

Phân biệt hai câu hỏi:

- `invokeAll`: “Đến deadline, mỗi task đã tạo được kết quả, thất bại hay bị hủy?”
- `invokeAny`: “Có **một** task hoàn tất **thành công** trước deadline hay không?”

Bài này chỉ nói về Java Concurrency chuẩn trong `java.util.concurrent`, độc lập với các framework.

## 2. Bảng so sánh hợp đồng quan trọng

| Tình huống | `invokeAll(tasks, timeout, unit)` | `invokeAny(tasks, timeout, unit)` |
| --- | --- | --- |
| Giá trị trả về bình thường | Danh sách `Future<T>`, đúng thứ tự task đầu vào | Một giá trị `T` của một task hoàn thành thành công |
| Khi deadline hết | Trả danh sách, yêu cầu hủy task chưa xong | Ném `TimeoutException` nếu chưa có thành công |
| Task A lỗi, B thành công | Future A báo `ExecutionException` tại `get()`, B có giá trị | Có thể trả giá trị của B |
| Tất cả task đều lỗi | Trả Future của từng task, mỗi `get()` có thể báo lỗi | Ném `ExecutionException` |
| Khi caller bị interrupt | Ném `InterruptedException`; các task chưa xong được yêu cầu hủy | Ném `InterruptedException`; các task chưa xong được yêu cầu hủy |
| Khi đã có một task thành công | Vẫn chờ các task còn lại hoặc hết hạn | Có thể trả kết quả và hủy các task khác |
| Quan sát kết quả một phần | Có, duyệt Future | Không nhận danh sách Future qua API này |

`invokeAll` không đảm bảo mọi task **thành công** trước khi trả về. Nó bảo đảm khi trả về bình thường, **tất cả Future trong danh sách đều `isDone() == true`**: thành công, lỗi hoặc hủy. Khi deadline hết, executor yêu cầu hủy những task chưa hoàn thành.

`invokeAny` chỉ quan tâm một **kết quả thành công**; một task thất bại sớm chưa đủ để kết thúc nếu còn ứng viên. Nếu tất cả thất bại, phương thức ném `ExecutionException`. Nếu chưa có thành công lúc deadline hết, nó ném `TimeoutException`. Khi có kết quả hoặc khi kết thúc bất thường, các task chưa cần thiết được yêu cầu hủy.

Cả hai API đều có thể phát sinh `RejectedExecutionException` do executor không nhận việc, tùy `RejectedExecutionHandler` được cấu hình. Đó là lỗi tiếp nhận công việc, khác lỗi thực thi của `Callable`.

## 3. invokeAll có timeout: điều gì xảy ra với task chưa xong?

Giả sử gọi `invokeAll` với A, B, C trong ngân sách 500 ms:

1. Các `Callable` được chuyển thành công việc để executor thực thi. Pool nhỏ có thể khiến một số task phải chờ queue.
2. `invokeAll` chờ tất cả hoàn thành hoặc hết thời hạn chung.
3. A có thể đã trả giá trị, B có thể đã ném ngoại lệ, còn C đang chạy/chờ khi deadline hết.
4. API yêu cầu `cancel(true)` đối với tác vụ chưa hoàn tất và trả danh sách `Future` tương ứng A, B, C.
5. Caller phân loại từng Future: thành công, thất bại hoặc hủy.

Trình tự trên là ví dụ minh họa; thực tế phụ thuộc lịch chạy. Danh sách Future được trả theo **thứ tự collection đầu vào**, không theo thứ tự hoàn thành. Nếu dữ liệu có ID, giữ một danh sách ID theo cùng thứ tự để ghép đúng kết quả.

| Trạng thái | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Hoàn thành thành công | `true` | `false` | Trả kết quả `T` (có thể là `null`) |
| Hoàn thành với exception | `true` | `false` | Ném `ExecutionException`; lấy lỗi gốc bằng `getCause()` |
| Bị hủy | `true` | `true` | Ném `CancellationException` |

**Hủy Future không đồng nghĩa task đã dừng thực sự**. `cancel(true)` chỉ cố gửi tín hiệu interrupt đến thread đang chạy; code không hợp tác có thể tiếp tục giữ tài nguyên hoặc gây side effect.

### Ví dụ chạy độc lập: các task hết hạn

Lưu thành `TimedInvokeAllDemo.java`. Một `CountDownLatch` không được mở khiến hai task không thể trả kết quả bình thường; ngay cả task chưa được chạy cũng sẽ được hủy khi hết hạn.

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class TimedInvokeAllDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch gate = new CountDownLatch(1);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> { gate.await(); return 1; },
                    () -> { gate.await(); return 2; });
            List<Future<Integer>> futures =
                    pool.invokeAll(tasks, 200, TimeUnit.MILLISECONDS);

            for (int i = 0; i < futures.size(); i++) {
                Future<Integer> f = futures.get(i);
                System.out.println("task " + (i + 1)
                        + " done=" + f.isDone()
                        + " cancelled=" + f.isCancelled());
                try {
                    System.out.println("value=" + f.get());
                } catch (CancellationException expected) {
                    System.out.println("no result: cancelled");
                } catch (java.util.concurrent.ExecutionException failed) {
                    System.out.println("failure=" + failed.getCause());
                }
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers still running");
            }
        }
    }
}
```

Chạy bằng Java 17+:

```bash
javac TimedInvokeAllDemo.java
java TimedInvokeAllDemo
```

Stdout:

```text
task 1 done=true cancelled=true
no result: cancelled
task 2 done=true cancelled=true
no result: cancelled
```

`gate` không bao giờ được `countDown()`, vì vậy task đã chạy sẽ chờ tại `await()` đến khi bị interrupt, còn task chưa bắt đầu vẫn có thể bị hủy. Cả hai Future trở thành `done` và `cancelled`. Trong ví dụ này, `await()` hỗ trợ interruption để worker thoát; đó không phải thuộc tính của mọi thao tác I/O.

## 4. Giữ lại partial results từ invokeAll

Timed `invokeAll` là lựa chọn hữu ích khi muốn giữ những kết quả đã có trước deadline. Đừng vứt cả batch chỉ vì một task không hoàn tất, trừ khi nghiệp vụ bắt buộc mọi kết quả cùng hợp lệ.

Đoạn minh họa sau giả định `futures` là danh sách được trả về bình thường từ timed `invokeAll`, `taskIds` tương ứng đúng thứ tự và các hàm `record...` do ứng dụng cung cấp:

```java
for (int i = 0; i < futures.size(); i++) {
    Future<Result> f = futures.get(i);
    String id = taskIds.get(i);

    if (f.isCancelled()) {
        recordMissing(id);
        continue;
    }

    try {
        Result value = f.get(); // invokeAll return: Future đã done.
        recordSuccess(id, value);
    } catch (java.util.concurrent.ExecutionException failure) {
        recordFailure(id, failure.getCause());
    } catch (java.util.concurrent.CancellationException cancelled) {
        recordMissing(id);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        break;
    }
}
```

Đây là **fragment**, không phải chương trình độc lập vì `Result` và các hàm phụ trợ chưa được khai báo. Mỗi Future trong list sau `invokeAll` bình thường đã `done`, vì vậy `get()` không đợi task chạy tiếp, nhưng vẫn phải xử lý exception theo chữ ký Java. Nếu thread đọc bị interrupt, khôi phục interrupt flag hoặc truyền exception lên caller theo hợp đồng của ứng dụng.

Phân biệt **thất bại thực thi** (`ExecutionException`), **hết hạn/bị hủy** (`CancellationException`), và **kết quả nghiệp vụ không hợp lệ** (Future thành công nhưng dữ liệu không đạt yêu cầu). Có thể biểu diễn mỗi kết quả bằng một record chứa task ID, status, value, error để tránh nhầm vị trí khi tổng hợp.

Nếu caller bị interrupt ngay trong `invokeAll`, phương thức ném `InterruptedException` và **không trả list Future**; đừng giả định có thể truy hồi partial results qua giá trị trả về khi đã ném lỗi.

## 5. invokeAny có timeout: một thành công là đủ

`invokeAny` phù hợp khi nhiều task thực hiện các phương án tương đương và chỉ cần **một** kết quả thành công. Nó không chọn “task đầu tiên trong danh sách”, cũng không trả kết quả lỗi đầu tiên như một thành công.

- Nếu một task trả `T` trước deadline, `invokeAny` có thể trả ngay `T` và yêu cầu hủy các task khác.
- Nếu vài task ném exception, phương thức tiếp tục thử các task khác khi còn khả năng có kết quả thành công và còn thời gian.
- Nếu tất cả đều thất bại, `ExecutionException` thể hiện không có thành công.
- Nếu deadline hết trước khi có thành công, `TimeoutException` được ném.
- API **không trả `Future` của các task thua**. Nếu cần thông tin chi tiết của mọi task, quản lý Futures riêng hoặc dùng `ExecutorCompletionService`.

Không dùng `invokeAny` trên các tác vụ gây side effect không idempotent một cách tùy tiện: nhiều task có thể đã bắt đầu gửi request, ghi file hoặc ghi dữ liệu **trước khi** tìm ra task thắng. Hủy sau khi một task thắng không hoàn tác tác động đã xảy ra.

### Ví dụ chạy độc lập: kết quả thành công và timeout

Lưu thành `TimedInvokeAnyDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimedInvokeAnyDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch neverOpen = new CountDownLatch(1);

        try {
            String winner = pool.invokeAny(
                    List.<Callable<String>>of(
                            () -> { neverOpen.await(); return "never"; },
                            () -> "ready"),
                    5, TimeUnit.SECONDS);
            System.out.println("winner=" + winner);

            try {
                pool.invokeAny(
                        List.<Callable<String>>of(
                                () -> { neverOpen.await(); return "never"; }),
                        200, TimeUnit.MILLISECONDS);
                System.out.println("unexpected success");
            } catch (TimeoutException expected) {
                System.out.println("timed out");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers still running");
            }
        }
    }
}
```

Chạy:

```bash
javac TimedInvokeAnyDemo.java
java TimedInvokeAnyDemo
```

Stdout khi executor được lập lịch trong ngân sách 5 giây:

```text
winner=ready
timed out
```

Task thứ nhất không có đường trả `"never"` bởi latch không bao giờ mở; task thứ hai trả `"ready"`, nên đó là kết quả thành công duy nhất của cuộc đua đầu tiên. Ở cuộc đua thứ hai, không task nào có thể hoàn tất trước hạn, vì vậy `TimeoutException` đúng. Cả hai nhánh đều có xử lý shutdown trong `finally`.

## 6. Timeout không bảo đảm dừng thread hoặc hoàn tác side effect

Cần tách ba thời điểm: **deadline của caller**, **Future chuyển sang canceled**, và **mã task thực sự ngừng thực thi/giải phóng tài nguyên**. Hai thời điểm sau không nhất thiết trùng nhau.

`cancel(true)` cố interrupt worker đang chạy. `CountDownLatch.await()`, `Thread.sleep()` và nhiều API blocking có thể ném `InterruptedException`. Một vòng lặp CPU không kiểm tra interrupt hoặc I/O không hỗ trợ interruption có thể tiếp tục chạy. Future đã canceled có thể khiến `get()` ném `CancellationException` trong khi worker vẫn thực hiện side effect.

Ví dụ fragment `Callable` có kiểm tra interrupt trong xử lý lặp:

```java
Callable<Integer> job = () -> {
    int count = 0;
    for (Item item : items) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("cancelled");
        }
        process(item); // Cần timeout I/O riêng nếu có.
        count++;
    }
    return count;
};
```

`Item`, `items` và `process` là phần ứng dụng tự định nghĩa. Nếu `process` gọi I/O có timeout quá dài, kiểm tra interrupt ở đầu vòng lặp có thể chưa đủ. Cần cấu hình timeout ở lớp socket/client hoặc cơ chế hủy thực sự hỗ trợ bởi dependency.

`Callable.call()` cho phép ném `InterruptedException`. Nếu `Runnable` bắt ngoại lệ này, hãy thoát theo hợp đồng và thường khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`; không nên nuốt rồi tiếp tục vô hạn.

Resource bên trong task nên có `try/finally` hoặc `try-with-resources`. Tuy nhiên, task **chưa từng bắt đầu** sẽ không thực hiện cleanup trong body. Resource cấp phát trước khi gửi task phải có owner chịu trách nhiệm khác. Cần thiết kế side effect idempotent và cơ chế đối chiếu kết quả nếu công việc đã gửi sang một hệ thống ngoài JVM.

## 7. Deadline tổng và timeout của từng dependency

Timeout của `invokeAll`/`invokeAny` giới hạn **thời gian chờ của caller ở cấp batch**. Nó không tự cấu hình read timeout của socket, query timeout hoặc hạn xử lý của service bên ngoài.

Ví dụ request có deadline 2 giây, nhưng một Callable chờ network response tối đa 60 giây và không phản ứng interrupt. Sau 2 giây, `invokeAny` ném `TimeoutException` hoặc `invokeAll` trả các Future canceled; worker vẫn có thể chiếm thread trong nhiều giây tiếp theo. Khi xảy ra thường xuyên, thread pool bị cạn dù code phía caller nghĩ đã “timeout”.

Thiết kế nên có:
1. Deadline cho toàn request/batch.
2. Timeout cho từng I/O phù hợp với **thời gian còn lại**.
3. Cancellation hợp tác tại ranh giới blocking.
4. Chính sách cho kết quả đến muộn và side effect đã xảy ra.
5. Đo thời gian thực thi, pending queue, rejection, timeout và worker bị kẹt.

Khi nhiều bước xử lý chung một deadline, tránh tự cộng thêm timeout đầy đủ ở từng bước. `System.nanoTime()` hữu ích để đo khoảng thời gian tương đối, thay vì dùng wall clock có thể điều chỉnh; việc tính và truyền ngân sách còn lại cần được chuẩn hóa theo logic ứng dụng.

## 8. Những tình huống ngoại lệ và dọn dẹp

| Sự kiện | API thể hiện | Hành động của caller |
| --- | --- | --- |
| `invokeAll` hết hạn | Danh sách Future, một số canceled | Gom phần thành công, ghi nhận phần timeout |
| `invokeAll` có một task lỗi | `get()` trên Future lỗi ném `ExecutionException` | Xem `getCause()`, không đánh đồng với timeout |
| `invokeAny` hết hạn | `TimeoutException` | Báo deadline, biết rằng tác vụ chưa chắc dừng ngay |
| `invokeAny` không có task thành công | `ExecutionException` | Ghi nhận thất bại, cân nhắc fallback đúng nghiệp vụ |
| Caller bị interrupt | `InterruptedException` | Truyền tiếp hoặc khôi phục interrupt flag và thoát |
| Executor từ chối nhận task | Thường `RejectedExecutionException` theo handler | Admission control/backpressure, xử lý tải |
| Task đã bị cancel nhưng có ghi dữ liệu | Future không rollback dữ liệu | Idempotency key, xác minh trạng thái bên ngoài |

`shutdown()` chỉ ngừng nhận task mới và để task đã nhận hoàn tất; `shutdownNow()` cố interrupt các worker đang chạy và trả về các task còn chờ nhưng không bảo đảm dừng tức thì. Không tạo executor mới cho mỗi batch rồi bỏ quên; quản lý vòng đời pool và cleanup khi ứng dụng kết thúc.

## 9. Khi nào nên chọn một công cụ khác?

`invokeAll` chỉ trả kết quả sau khi tất cả đã xong hoặc deadline đã qua. Nếu muốn xử lý **từng kết quả ngay khi task nào đó hoàn tất**, `ExecutorCompletionService` có `take()` và `poll(timeout, unit)`, nhưng caller phải tự theo dõi Future và hủy task còn lại đúng thời điểm.

Nếu cần điều phối không chặn, `CompletableFuture` là một lựa chọn khác. Tuy nhiên, `CompletableFuture.anyOf(...)` hoàn tất khi một future **bất kỳ** hoàn tất (có thể lỗi), không tương đương semantics “một thành công” của `invokeAny`. `allOf(...)` cũng không tự cung cấp hành vi timed `invokeAll` về hủy task chưa hoàn tất. Phải thiết kế timeout, lỗi và hủy riêng.

Với tác vụ dài hoặc cần tồn tại qua JVM restart, một queue/job store bền vững phù hợp hơn thao tác Future chỉ trong bộ nhớ.

## 10. Lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng timed `invokeAll` ném `TimeoutException` | Xử lý sai API | Đọc list và phân loại canceled |
| Tưởng mỗi task có nguyên một `timeout` | Batch có deadline bị hiểu sai | Dùng ngân sách chung |
| Coi `isDone() == true` là thành công | Task lỗi hoặc bị hủy vẫn done | Kiểm tra canceled và `get()` |
| Coi `invokeAny` chọn task đầu tiên | Sai mục đích chọn một thành công | Không dựa vào thứ tự đầu vào |
| Dùng `invokeAny` cho nhiều tác vụ ghi không idempotent | Có thể gây side effect nhiều lần | Dùng idempotency, coordination |
| Nghĩ `cancel(true)` cưỡng ép dừng Java code | Worker còn chạy và giữ tài nguyên | Hỗ trợ interrupt và timeout I/O |
| Nuốt `InterruptedException` | Không phản ứng khi bị hủy | Truyền lại hoặc khôi phục flag rồi thoát |
| Bỏ kết quả thành công khi một phần timeout | Mất thông tin có ích | Tổng hợp partial result theo ID |
| Không shutdown executor | Rò thread/tài nguyên | Quản lý lifecycle và shutdown có kiểm soát |
| Dùng queue vô hạn dù batch có timeout | Task vẫn tích tụ và latency cao | Bounded queue và admission control |

## 11. Câu hỏi tự kiểm tra

**1. `invokeAll(tasks, 1, SECONDS)` hết hạn ném `TimeoutException`?** Không. Nó trả về danh sách Future, đồng thời yêu cầu hủy task chưa hoàn tất.

**2. Future của timed `invokeAll` có thể chưa done khi phương thức trả về bình thường?** Không. Mọi Future đều done, nhưng có thể canceled hoặc failed.

**3. `invokeAny` có trả kết quả của task lỗi đầu tiên?** Không. Nó cần một task thành công; khi tất cả thất bại ném `ExecutionException`.

**4. Khi timed `invokeAny` hết hạn, ta có Future list để lấy partial results không?** Không. API chỉ trả giá trị `T` khi thành công hoặc ném exception. Nếu cần chi tiết từng task, sử dụng cơ chế quản lý Future riêng.

**5. `cancel(true)` thành công có chắc worker đã ngừng ghi dữ liệu?** Không. Interrupt mang tính hợp tác; side effect có thể đã xảy ra hoặc vẫn tiếp tục.

**6. Vì sao task I/O nên có timeout riêng?** Vì timeout của batch chỉ giới hạn chờ của caller, không tự đặt timeout cho socket hoặc các tài nguyên ngoài JVM.

**7. Sau khi `invokeAll` trả về, ghép Future với request gốc như thế nào?** Dùng chỉ số trong danh sách: Future được trả theo thứ tự collection đầu vào.

## Tài liệu tham khảo

- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Future — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Callable — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html)
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [ExecutorCompletionService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
