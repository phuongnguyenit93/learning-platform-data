# invokeAny() cho kết quả thành công đầu tiên trong Java

## 1. Vấn đề và mục tiêu học

Trong một số bài toán concurrency, ta có nhiều cách độc lập để tạo **một kết quả tương đương**, và chỉ cần **một** cách hoàn tất thành công. Ví dụ: truy vấn nhiều replica đọc dữ liệu giống nhau, gọi các nguồn dự phòng, hoặc chạy nhiều thuật toán cho cùng một đầu ra đã chuẩn hóa. Đợi tất cả nguồn hoàn tất có thể tốn thời gian nếu một nguồn lỗi hoặc quá chậm.

`ExecutorService.invokeAny(Collection<? extends Callable<T>> tasks)` thực thi một nhóm `Callable<T>` và **trả trực tiếp kết quả của một task hoàn tất bình thường**. Nó không đợi mọi task thành công. Khi method hoàn tất (bình thường hoặc do exception), các task **chưa hoàn tất** được **yêu cầu hủy**.

~~~java
String response = pool.invokeAny(List.of(
        () -> readReplica("east"),
        () -> readReplica("west"),
        () -> readReplica("backup")
));
~~~

Đây là **đoạn trích minh họa**, trong đó `pool` là một `ExecutorService`, `readReplica` là hàm của ứng dụng; method bao ngoài phải khai báo/handle checked exceptions. Nếu một Callable trả dữ liệu thành công, caller nhận giá trị đó mà không cần `Future.get()` cho từng nguồn.

Sau bài học, bạn sẽ:

- Giải thích đúng `invokeAny`, hai overload, kiểu trả về và checked exceptions.
- Hiểu “thành công” là **không ném exception**, kể cả khi giá trị trả về là `null`.
- Phân biệt task lỗi trước, task thành công trước, tất cả task lỗi, hết timeout và caller bị interrupt.
- Phân biệt `invokeAny` với `invokeAll`, `submit`/`Future.get`, `ExecutorCompletionService` và `CompletableFuture.anyOf`.
- Dùng interruption/cancellation và cleanup đúng cách, không nhầm “đã cancel” với “thread đã chấm dứt”.
- Thiết kế pool đủ capacity, timeout theo deadline, validation kết quả nghiệp vụ, idempotency và giới hạn fan-out.
- Chạy ví dụ Java 17+ dàn dựng thứ tự bằng `CountDownLatch` thay vì phỏng đoán scheduler.

**Phạm vi:** Java SE và Executor Framework, không phụ thuộc bất kỳ framework nào.

## 2. API và các nhánh kết quả

Hai overload chuẩn:

~~~java
<T> T invokeAny(Collection<? extends Callable<T>> tasks)
        throws InterruptedException, ExecutionException;

<T> T invokeAny(
        Collection<? extends Callable<T>> tasks,
        long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

| Trường hợp | Hành vi của invokeAny |
|---|---|
| Có task hoàn tất bình thường | Trả kết quả `T` của **một** task thành công |
| Một task ném exception, các task khác có thể thành công | Tiếp tục đợi/cạnh tranh, **không fail ngay vì lỗi đầu tiên** |
| Tất cả task đều không hoàn tất bình thường | Ném `ExecutionException` |
| Timed overload hết hạn trước khi có thành công | Ném `TimeoutException` |
| Thread gọi invokeAny bị interrupt trong khi đợi | Ném `InterruptedException` |
| Collection rỗng | `IllegalArgumentException` |
| Collection hoặc phần tử task cần thực thi là null | `NullPointerException` |
| Executor không thể tiếp nhận các task | Có thể ném `RejectedExecutionException` |

Javadoc cũng quy định **trên cả đường return bình thường lẫn đường thoát bằng exception, các task chưa hoàn tất được hủy**. Hủy không đồng nghĩa thu hồi side effects hay kill thread.

Một điểm rất quan trọng: chữ **success** được hiểu là **completion without throwing exception**, chứ không phải kết quả có status=200 hoặc dữ liệu hợp lệ theo nghiệp vụ. Nếu một Callable `return null`, `return Optional.empty()` hoặc `return Response(503)` mà không ném exception, `invokeAny` có thể chọn nó như một kết quả **thành công kỹ thuật**.

### Kết quả được chọn có thật sự là “nhanh nhất”?

Trong cách nói thông thường, người ta mô tả `invokeAny` là “lấy kết quả thành công đầu tiên”. Nhưng không nên suy rộng thành các cam kết sau:
- Chọn phần tử đầu tiên của `List`.
- Chọn task được **submit** sớm nhất.
- Chọn task có thời gian CPU ngắn nhất.
- Chọn replica có dữ liệu mới nhất/đúng nhất.
- Khởi động **tất cả** task cùng một thời điểm.
- Luôn trả cùng một winner khi chạy lại cùng input.

Scheduler, số workers, queue, thời gian hoàn tất và cách executor quan sát các completions có thể thay đổi winner. Nếu hai kết quả cùng thành công gần như đồng thời, **thứ tự chọn không nên bị kiểm thử bằng một chuỗi cố định**.

## 3. Mô phỏng cạnh tranh giữa các tác vụ

~~~text
Caller: invokeAny([A, B, C])
             |
             +--- A: ném IOException --------------------X (failure)
             |
             +--- B: xử lý rồi return "OK" -----------✓ (success)
             |
             +--- C: đang đợi remote I/O --------------------?
                          |
               B thành công, invokeAny chọn "OK"
                          |
               Task C chưa hoàn tất → yêu cầu cancel
                          |
               Caller có thể nhận "OK" dù C chưa cleanup xong
~~~

**Một failure sớm không phải lý do kết thúc nhóm**, trừ khi tất cả ứng viên đều đã thất bại. Một success đủ điều kiện mới là điểm kết thúc bình thường.

Nhiều nguồn được chạy theo `Callable.call()`:
- `call()` trả về một giá trị ⇒ success.
- `call()` ném exception ⇒ failed task.
- `call()` bị interrupt và ném `InterruptedException` ⇒ task thất bại/chấm dứt qua exception, không phải success.
- Task chưa được schedule hoặc đang chạy khi một task khác thắng ⇒ bị yêu cầu cancel theo API.

Một task có thể đã tạo hiệu ứng bên ngoài (ghi file, gửi request, commit database) trước khi được yêu cầu hủy. Vì thế nên ưu tiên các nguồn **đọc tương đương/idempotent** cho kiểu racing này.

## 4. Ví dụ Java độc lập 1: failure, winner và loser bị interrupt

Ví dụ dùng 3 workers để có khả năng đồng thời xử lý 3 ứng viên. Một ứng viên ném exception, một ứng viên chờ `CountDownLatch` không được mở, và một ứng viên trả `"OK"` **sau khi ứng viên chậm đã bắt đầu**. Kết quả cuối được kiểm soát mà **không dùng sleep**.

Lưu tệp **InvokeAnyFirstSuccessDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InvokeAnyFirstSuccessDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);

        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch slowFinished = new CountDownLatch(1);
        CountDownLatch closedGate = new CountDownLatch(1);
        AtomicBoolean slowInterrupted = new AtomicBoolean(false);

        Callable<String> fail = () -> {
            throw new IllegalStateException("replica failed");
        };

        Callable<String> slow = () -> {
            slowStarted.countDown();
            try {
                closedGate.await();
                return "SLOW";
            } catch (InterruptedException e) {
                slowInterrupted.set(true);
                Thread.currentThread().interrupt();
                throw e;
            } finally {
                slowFinished.countDown();
            }
        };

        Callable<String> winner = () -> {
            slowStarted.await();
            return "OK";
        };

        try {
            String result = pool.invokeAny(
                    List.of(fail, slow, winner));

            slowFinished.await();
            System.out.println("result=" + result);
            System.out.println(
                    "slowInterrupted=" + slowInterrupted.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Pool did not terminate");
            }
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac InvokeAnyFirstSuccessDemo.java
java InvokeAnyFirstSuccessDemo
~~~

Output trong điều kiện bình thường, không có interrupt ngoài:

~~~text
result=OK
slowInterrupted=true
~~~

**Vì sao kết quả ổn định?**

1. Task `fail` ném exception. Nó không được chọn làm winner.
2. Task `slow` báo `slowStarted` rồi chờ `closedGate`. Gate này **không bao giờ mở** trong ví dụ, nên slow không thể tự return `"SLOW"`.
3. Task `winner` chỉ return `"OK"` sau khi `slowStarted.await()` hoàn tất; bảo đảm slow đã khởi động.
4. Khi `"OK"` được chọn, `invokeAny` yêu cầu hủy task slow đang chờ; `CountDownLatch.await()` phản ứng bằng `InterruptedException`, slow set `slowInterrupted=true`.
5. `slowFinished.countDown()` trong `finally` bảo đảm main có thể chờ slow đã đi qua cleanup trước khi đọc cờ.
6. `pool.shutdownNow()` nằm trong finally để bảo vệ cleanup executor nếu có lỗi bất ngờ, không phải nguyên nhân chính tạo kết quả thành công.

Lệnh `slowFinished.await()` là **điểm quan sát bổ sung của chương trình test**. Không nên nghĩ `invokeAny` tự chờ mọi loser hoàn tất cleanup trước khi trả về: nó chỉ yêu cầu cancel khi chưa hoàn tất.

## 5. Nếu tất cả các task đều lỗi?

Ví dụ ta gọi ba nguồn:

~~~java
Callable<String> a = () -> {
    throw new IllegalArgumentException("bad input");
};
Callable<String> b = () -> {
    throw new IllegalStateException("source unavailable");
};
Callable<String> c = () -> {
    throw new java.io.IOException("remote read failed");
};
~~~

Đây là các **đoạn trích** dùng trong method có imports phù hợp. Không task nào có normal result, nên `invokeAny(List.of(a,b,c))` ném `ExecutionException`.

**Không được mặc định một exception nguyên nhân của ExecutionException chứa toàn bộ lỗi của mọi task.** Tùy implementation và thứ tự completion, cause có thể là một trong các failures. Nếu cần báo cáo từng nguồn đã lỗi gì, dùng `invokeAll` rồi đọc các Futures, hoặc dùng `ExecutorCompletionService` để thu thập riêng các outcomes.

### Trường hợp task thành công bằng null

`Callable<String>` có thể `return null` bình thường. Theo contract, đó là success; `invokeAny` có thể return `null`. Tương tự, `Optional.empty()` hay một đối tượng `Response` có trường `ok=false` vẫn được coi là normal completion.

Nếu một kết quả như vậy **không dùng được**, hãy validate **bên trong Callable** trước khi return hoặc tự viết coordinator để chọn theo business predicate. Không giao trách nhiệm validation cho `invokeAny` khi nó không có API nhận predicate.

## 6. Ví dụ Java độc lập 2: mọi task lỗi, nhưng null được coi là success

Lưu tệp **InvokeAnyFailureCasesDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class InvokeAnyFailureCasesDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Callable<String>> errors = List.of(
                    () -> {
                        throw new IllegalArgumentException("A");
                    },
                    () -> {
                        throw new IllegalStateException("B");
                    }
            );

            boolean allFailed = false;
            try {
                pool.invokeAny(errors);
            } catch (ExecutionException e) {
                allFailed = true;
            }
            System.out.println("allFailed=" + allFailed);

            String result = pool.invokeAny(
                    List.<Callable<String>>of(() -> null));
            System.out.println("nullIsSuccess=" + (result == null));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac InvokeAnyFailureCasesDemo.java
java InvokeAnyFailureCasesDemo
~~~

Output:

~~~text
allFailed=true
nullIsSuccess=true
~~~

Trong phép gọi đầu, hai task đều throw; không có normal completion nên nhận `ExecutionException`. Trong phép gọi thứ hai, Callable return null mà không throw, do đó `invokeAny` trả null. Bài test không in `e.getCause()` vì không nên cam kết thứ tự exception khi nhiều task cùng thất bại.

### Kiểm tra dữ liệu đúng nơi

~~~java
Callable<String> checked = () -> {
    String data = fetchFromReplica();
    if (data == null || data.isBlank()) {
        throw new IllegalStateException("no usable data");
    }
    return data;
};
~~~

Đoạn trích này cần định nghĩa `fetchFromReplica()` ở ứng dụng. Nếu chuỗi rỗng có nghĩa “thất bại”, xác định điều đó trước khi return. Nhưng nếu null thật sự là một kết quả hợp lệ, không nên biến nó thành lỗi chỉ vì đã chọn API; hãy chọn công cụ phối hợp phù hợp với domain.

## 7. Overload có timeout

Cú pháp:

~~~java
String result = executor.invokeAny(
        tasks, 300, TimeUnit.MILLISECONDS);
~~~

Nếu **chưa có một thành công** trước khi hết khoảng chờ, overload timed ném `TimeoutException`. Những task chưa xong được yêu cầu cancel khi method thoát.

Phân biệt ba kết quả:

| Tình huống | Exception/result |
|---|---|
| Có ít nhất một normal result trong hạn | Trả kết quả `T` |
| Tất cả candidates cùng kết thúc bằng exception trước khi hết hạn | `ExecutionException` |
| Hết hạn mà vẫn chưa có normal result | `TimeoutException` |
| Caller bị interrupt trong lúc chờ | `InterruptedException` |

Timeout ở đây là **khoảng chờ của caller cho nhóm tasks**. Nó không làm tác vụ remote I/O đang chạy tự timeout ở đúng mốc đó và không buộc worker release mọi tài nguyên ngay lập tức.

### Ví dụ Java độc lập 3: timed invokeAny hết hạn

Hai tasks chờ latch không bao giờ được đếm xuống. Vì không thể normal-complete, timed call phải hết hạn nếu không bị ngắt bởi tín hiệu ngoài.

Lưu **InvokeAnyTimeoutDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class InvokeAnyTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch closedGate = new CountDownLatch(1);

        Callable<String> blocked = () -> {
            closedGate.await();
            return "UNREACHABLE";
        };

        boolean timedOut = false;
        try {
            try {
                pool.invokeAny(
                        List.of(blocked, blocked),
                        80, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                timedOut = true;
            }

            System.out.println("timedOut=" + timedOut);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Pool did not terminate");
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac InvokeAnyTimeoutDemo.java
java InvokeAnyTimeoutDemo
~~~

Output dự kiến:

~~~text
timedOut=true
~~~

Ví dụ không dựa vào lịch chạy chính xác đến 80ms. Hai Callables không thể return nếu latch chưa mở. Khi timed `invokeAny` thoát, các task đang chờ `CountDownLatch.await()` có đường phản ứng với cancellation qua `InterruptedException`.

Nếu thay latch bằng API blocking không hỗ trợ interruption, method vẫn có thể ném timeout ở caller nhưng worker vẫn chiếm resource. Cần timeout/close/cancel riêng theo hợp đồng của từng API.

## 8. Các loại exception cần xử lý tách biệt

Mẫu caller:

~~~java
try {
    return pool.invokeAny(candidates, 500, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Chưa có normal result trong deadline.
    logTimeout();
    throw e;
} catch (ExecutionException e) {
    // Không có candidate hoàn tất thành công.
    logAllFailed(e.getCause());
    throw e;
} catch (InterruptedException e) {
    // Thread caller bị yêu cầu hủy.
    Thread.currentThread().interrupt();
    throw e;
}
~~~

Đây là **mã tích hợp**, method bao ngoài phải khai báo hoặc xử lý checked exceptions, và các hàm `logTimeout`, `logAllFailed` do ứng dụng cung cấp. Nếu propagate InterruptedException lên trên, có thể để tầng trên quyết định chính sách, không nhất thiết vừa restore vừa rethrow; việc restore thường cần khi bắt exception mà không ném tiếp.

Các thông điệp ý nghĩa nghiệp vụ:
- `ExecutionException`: **không ứng viên nào thành công**; cause là một thông tin chẩn đoán, không phải tập hợp đủ các exception.
- `TimeoutException`: **deadline của lượt đợi hết** trước success.
- `InterruptedException`: thread **đang gọi** bị interrupt khi chờ; không tự động suy tất cả worker đã dừng.
- `RejectedExecutionException`: executor không nhận một hoặc nhiều tác vụ theo admission policy (shutdown/saturation hoặc không tạo được worker).

Không dùng một `catch(Exception)` rồi trả null trong mọi trường hợp: như vậy làm mất phân biệt giữa dữ liệu null hợp lệ, all-failed và timeout, khiến hệ thống khó hồi phục/chẩn đoán.

## 9. Những task chưa hoàn tất bị hủy ra sao?

Javadoc của `ExecutorService.invokeAny` nêu rằng **upon normal or exceptional return**, các task **chưa completed** được canceled. Với implementation thông dụng, cancellation có thể yêu cầu interrupt worker đang chạy, tương tự `Future.cancel(true)`.

Quan trọng:
- **Cancel request không phải hard stop.** Một CPU-bound loop không kiểm tra interrupt có thể chạy tiếp.
- Một số blocking APIs như `sleep`, `wait`, `BlockingQueue.take`, `CountDownLatch.await` thường phản ứng bằng `InterruptedException`.
- Các I/O/native/third-party APIs không nhất thiết phản ứng nhanh hoặc phản ứng bằng `InterruptedException`; đọc contract cụ thể.
- Tác vụ đã hoàn tất không phải “unfinished”; tác dụng phụ đã commit không được tự rollback.
- Kết quả `invokeAny` đã có không có nghĩa những task thua đã cleanup hoàn toàn.
- Thread pool có thể giữ worker thread tồn tại sau khi một Callable kết thúc; **task finished** khác với **thread terminated**.
- Không nuốt `InterruptedException` rồi lặp vô hạn. Caller yêu cầu hủy mà task không hợp tác có thể làm cạn worker capacity.

Ví dụ anti-pattern:

~~~java
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Bỏ tín hiệu hủy, quay lại đợi.
    }
}
~~~

Đây là đoạn minh họa lỗi, không phải mẫu production. Nếu chính sách task là dừng khi interrupt, hãy ném tiếp `InterruptedException` hoặc khôi phục cờ rồi return, kèm cleanup trong `finally`.

## 10. invokeAny không tự đảm bảo mọi task được bắt đầu

Executor có thể có ít workers hơn số Callables. Tasks có thể xếp hàng chờ hoặc được executor submit theo chiến lược khi nó thu thập completions. Ví dụ có 2 nguồn:

- Task A đợi vô hạn một thao tác không có timeout.
- Task B có thể return "OK" ngay khi được chạy.
- Executor chỉ có **một worker** và A chiếm worker trước.

Khi đó B không có worker để chạy, và untimed `invokeAny` có thể **chờ vô thời hạn**. Chỉ vì B “có khả năng trả nhanh” không đủ nếu nó không được schedule.

~~~text
Executor: core=max=1
worker duy nhất -> A đang block
queue -> B đang đợi worker
caller -> invokeAny() đang chờ success
=> Không có success nếu A không thoát để B bắt đầu.
~~~

Đặc biệt nguy hiểm khi task đang chạy trong **chính pool đó** lại gọi `invokeAny` trên pool và chờ các tasks con: worker cha chiếm worker duy nhất, con bị queue, tạo **thread-starvation deadlock**.

Trước khi dùng:
- Pool có đủ worker capacity cho số I/O độc lập mong muốn không?
- Tasks có giữ lock/permit mà các task khác cần để chạy hay không?
- Có dependency cha-con trên cùng pool khiến mọi worker đều chờ nhau không?
- Queue capacity/rejection policy có phù hợp với fan-out không?
- Có timeout, cancellation và deadline cho các nguồn chậm không?

## 11. invokeAny vs invokeAll vs submit

| Công cụ | Return | Khi nào caller kết thúc? | Cancel những task còn dở? |
|---|---|---|---|
| `invokeAny(tasks)` | Một kết quả `T` | Khi có một **normal completion**, hoặc không ai success / bị interrupt | Có, unfinished tasks khi thoát |
| `invokeAny(tasks, timeout, unit)` | Một kết quả `T` | Như trên, hoặc đến timeout | Có, unfinished tasks khi thoát |
| `invokeAll(tasks)` | `List<Future<T>>` | Khi tất cả tasks hoàn tất (success hay exception) | Nếu caller bị interrupt, unfinished tasks bị hủy |
| `invokeAll(tasks, timeout, unit)` | `List<Future<T>>` | Khi tất cả hoàn tất hoặc hết hạn | Unfinished tasks bị hủy khi hết hạn |
| `submit(callable)` | `Future<T>` | Trả Future sau khi submit được nhận | Không tự cancel các tasks khác |

`invokeAll` giữ danh sách Futures theo **thứ tự iterator của collection input**; một Future completed không đồng nghĩa thành công, caller có thể cần `future.get()` và bắt `ExecutionException`.

Với `submit` nhiều lần rồi gọi `futureA.get()` trước, caller có thể kẹt ở A dù B đã thành công; `invokeAny` giải quyết đúng mục tiêu **any-success** mà không bắt người gọi tự quản lý winner. Nếu cần biết **lỗi từng task**, dùng `invokeAll` hoặc các Futures riêng thay vì chỉ một `ExecutionException` tổng quát.

### So với ExecutorCompletionService

`ExecutorCompletionService<T>` cho phép lấy Future theo **thứ tự hoàn tất** thông qua `take()` hoặc `poll()`. Bạn có thể kiểm tra lần lượt kết quả, ghi nhận exception của từng nguồn, chọn theo predicate, hoặc yêu cầu nhiều kết quả. Đổi lại phải tự quản lý danh sách Futures, cancellation, timeout và cleanup. `invokeAny` tiện khi chỉ cần **một normal result**.

### So với CompletableFuture.anyOf

`CompletableFuture.anyOf(a,b,c)` hoàn tất khi một CompletableFuture hoàn tất, **kể cả exceptionally**. Nếu nguồn đầu tiên ném exception, anyOf có thể hoàn thành exceptionally ngay, trong khi `invokeAny` vẫn có thể chờ nguồn khác thành công. anyOf cũng không tự hủy mọi loser theo đúng hợp đồng của `ExecutorService.invokeAny`.

Vì vậy **anyOf không phải bản sao hoàn toàn của invokeAny**. Nếu cần first-success với CompletableFuture, phải thiết kế cơ chế riêng xử lý failure, winner và cancellation.

## 12. Timed invokeAny không đồng nghĩa hard deadline cho toàn hệ thống

Ví dụ:

~~~java
String answer = pool.invokeAny(
        tasks, 250, TimeUnit.MILLISECONDS);
~~~

không hứa:
- Các nguồn remote dừng tức thì ở 250ms.
- Mọi socket/connection đã đóng trước khi caller nhận TimeoutException.
- Side effects của loser đã rollback.
- Scheduler đánh thức caller đúng chính xác ở 250ms theo wall clock.
- Từng task có ngân sách 250ms độc lập.
- Việc trả kết quả sau đó của nguồn đã bị hủy không thể tạo side effect.

Khi nghiệp vụ có deadline tổng 300ms, phải tính thời gian tạo request, queue, remote I/O, xử lý và cleanup. Nếu cần giới hạn remote requests, hãy đặt timeout ở API I/O, không chỉ ở `invokeAny`.

Nếu ứng dụng gọi hàng nghìn lượt invokeAny, mỗi lượt ba replicas, nó có thể **nhân tải downstream lên ba lần**. Đừng dùng hedged racing không giới hạn nếu remote service có quota/concurrency cap. Với nhu cầu chuyên sâu, có thể dùng **delayed hedging** (đợi nguồn chính một thời gian trước khi phát nguồn dự phòng), nhưng `invokeAny` không cung cấp thuật toán delayed hedging sẵn.

## 13. Bài toán nhiều nguồn có side effects

Một nguồn A có thể ghi cơ sở dữ liệu rồi phản hồi chậm; B có thể trả kết quả thành công sớm; sau đó A nhận yêu cầu cancel. Dù caller chỉ nhận B, thao tác ghi của A **có thể đã commit** trước khi bị cancel.

Do đó:
- Ưu tiên tasks **đọc**, pure computation hoặc các attempts idempotent.
- Nếu thao tác ghi bắt buộc, dùng idempotency key và nguồn dữ liệu có protocol chặn duplicate đúng nghiệp vụ.
- Không giả định interruption rollback transaction, email, file, socket hoặc remote request.
- Mọi `Callable` vẫn phải thread-safe với mutable shared objects; `invokeAny` chỉ điều phối completion, không tự khóa business state.
- Nếu nhiều replica có dữ liệu khác nhau, “nguồn trả đầu tiên” không nhất thiết là dữ liệu mới nhất hoặc nhất quán nhất.

Nếu yêu cầu phải chọn version cao nhất, đạt quorum, hoặc ghi nhận mọi kết quả, `invokeAny` **không đủ ngữ nghĩa**; chọn coordination API phù hợp hơn.

## 14. Không nhầm completed, cancelled và termination

Một số trạng thái:

| Sự kiện | Có thể kết luận gì? | Không thể kết luận gì? |
|---|---|---|
| `invokeAny` trả `T` | Có một task normal-complete | Các losers đã cleanup hoàn toàn |
| `TimeoutException` | Không có success trong thời hạn đợi | Mọi worker đã dừng |
| `ExecutionException` | Không task nào success | Tất cả cause chi tiết đã được báo |
| `Future.isCancelled()` | Future có trạng thái cancelled theo contract | Side effects bị đảo ngược |
| `pool.shutdown()` | Pool không nhận task mới theo policy | Mọi task đang chạy đã xong |
| `pool.awaitTermination()` trả true | Pool đã terminated | Các side effects ở hệ thống ngoài đã được rollback |

Nếu cần xác nhận loser đã hoàn tất cleanup, thiết kế latch/handle phù hợp hoặc lifecycle await riêng. Không chặn mãi ở cleanup khi chính operation đã timeout; đặt deadline cho cả phần giải phóng khi hệ thống yêu cầu.

## 15. Quản lý vòng đời executor

Trong Java 17, quản lý `ExecutorService` bằng `try/finally` và shutdown có kiểm soát:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);
try {
    String answer = pool.invokeAny(
            candidates, 1, TimeUnit.SECONDS);
    consume(answer);
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                System.err.println("Tasks still running");
            }
        }
    } catch (InterruptedException e) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là **đoạn tích hợp**, `candidates` và `consume` do ứng dụng định nghĩa, method phải khai báo hoặc xử lý checked exceptions của `invokeAny`. Nếu pool dùng chung cho nhiều request, **không shutdown sau mỗi request**; owner phải chịu trách nhiệm quản lý toàn bộ lifecycle.

`shutdownNow` **cố gắng** ngắt tasks còn chạy, không kill bắt buộc. Nếu task đang thực hiện I/O không interruptible hoặc nuốt tín hiệu hủy, pool có thể còn worker sau thời gian chờ. Đó là lý do cần theo dõi termination và thiết kế cancellation-aware code.

### Java 21+ và virtual threads

`Executors.newVirtualThreadPerTaskExecutor()` có thể giúp triển khai nhiều tác vụ blocking bằng virtual threads, nhưng không tự hạn chế số request đồng thời tới remote endpoint. Dù executor nào, `invokeAny` vẫn giữ ngữ nghĩa **một normal completion là đủ** và yêu cầu hủy unfinished tasks; việc hủy có hiệu quả hay không vẫn phụ thuộc hoạt động cụ thể. Với Java 17, dùng thread pool nền tảng như ví dụ.

## 16. Lỗi phổ biến khi review code

1. **Nhầm kết quả đầu tiên với task đầu tiên trong List.** Thứ tự collection không bảo đảm winner.
2. **Cho rằng task lỗi sớm làm toàn invokeAny thất bại.** Chỉ khi không còn candidate thành công mới ném `ExecutionException`.
3. **Quên rằng return null cũng là success.** Validation kết quả nghiệp vụ phải do caller/Callable đảm trách.
4. **Cho rằng invokeAny trả Future.** Nó trả trực tiếp `T`.
5. **Cho rằng tất cả Callables chạy song song tức thì.** Pool/queue và chiến lược scheduling quyết định.
6. **Cho rằng invokeAny trả về là mọi loser đã dừng.** Nó yêu cầu hủy nhưng không cưỡng bức thread kết thúc ngay.
7. **Dùng timed invokeAny thay timeout của network client.** Một timeout ở caller không đảm bảo remote I/O đã giải phóng resource.
8. **Lẫn `TimeoutException` với `ExecutionException`.** Hết thời hạn không giống mọi nguồn đã lỗi.
9. **Nuốt `InterruptedException` và tiếp tục.** Worker có thể bỏ qua cancellation.
10. **Dùng các tasks ghi không idempotent.** Losers có thể đã commit.
11. **Dùng pool quá nhỏ với task chờ vô hạn.** Candidate khác có thể không được schedule.
12. **Task cha chờ tasks con trong cùng pool không còn worker rảnh.** Có nguy cơ thread-starvation deadlock.
13. **Dựa vào `ExecutionException.getCause` để suy toàn bộ lỗi nguồn.** Nó không là aggregation đầy đủ.
14. **Sửa collection tasks trong lúc invokeAny chạy.** Javadoc nói kết quả undefined.
15. **Bỏ qua rejection và lifecycle.** Executor đã shutdown có thể không nhận task mới.
16. **Chỉ quan sát throughput mà không đo fan-out.** Racing có thể tăng tải và giảm độ ổn định tổng thể.
17. **Chọn replica thắng dựa trên thời gian nhưng cần dữ liệu mới nhất.** Fastest không đồng nghĩa correct/latest.
18. **Dùng `CompletableFuture.anyOf` như if nó là first-success.** anyOf có thể hoàn tất exceptionally từ nguồn lỗi đầu tiên.
19. **Tuyên bố cancel=true là “kill task”.** Cancellation thường là cơ chế hợp tác dựa trên interrupt.
20. **Không đóng executor mình sở hữu.** Workers/resources có thể bị giữ lâu không cần thiết.

## 17. Checklist trước khi dùng invokeAny

- [ ] Các `Callable<T>` thực sự độc lập và cùng kiểu kết quả không?
- [ ] Một normal result có đủ đáp ứng yêu cầu nghiệp vụ không?
- [ ] Có cần reject `null`/empty/error-status trong Callable không?
- [ ] Collection có không rỗng, không chứa null và không bị mutate trong lúc gọi?
- [ ] Pool có đủ worker để nguồn nhanh có cơ hội chạy không?
- [ ] Có timeout tổng cho lượt gọi khi cần SLA không?
- [ ] Mỗi remote/I/O operation có timeout/cancel phù hợp không?
- [ ] Tasks có phản hồi interrupt và cleanup tài nguyên trong finally không?
- [ ] Các tasks có gây side effects không idempotent không?
- [ ] Có xử lý riêng `ExecutionException`, `TimeoutException` và `InterruptedException` không?
- [ ] Có xử lý tình huống `RejectedExecutionException` không?
- [ ] Ai chịu trách nhiệm shutdown executor; có bị dùng chung không?
- [ ] Có cần thu thập **tất cả lỗi** hoặc chọn theo business predicate khác không?
- [ ] Đã test task thắng với latch/control thay vì dựa vào sleep chưa?
- [ ] Đã đo remote fan-out, queue latency, cancellation effectiveness và tải downstream chưa?

## 18. Bài tập tự kiểm tra

**Câu 1.** Task A ném exception sau 10ms, task B return "OK" sau 20ms. Với executor đủ workers, `invokeAny` nên trả gì?

**Đáp án:** "OK"; failure sớm của A không phải normal result.

**Câu 2.** Hai tasks đều throw, không có normal result. Kết quả?

**Đáp án:** `ExecutionException`.

**Câu 3.** Task A return null, task B return "data". Null có bị bỏ qua không?

**Đáp án:** Không. Null là một normal completion, có thể là winner.

**Câu 4.** Timed invokeAny hết hạn nhưng một worker đang block ở API không interruptible. Worker có chắc đã dừng chưa?

**Đáp án:** Không. Phương thức yêu cầu hủy unfinished tasks nhưng worker có thể tiếp tục; cần timeout/cancel riêng tại tài nguyên.

**Câu 5.** `invokeAny` trả `T` hay `List<Future<T>>`?

**Đáp án:** Trả `T`. `invokeAll` trả `List<Future<T>>`.

**Câu 6.** Caller bị interrupt khi đang đợi invokeAny. Exception gì?

**Đáp án:** `InterruptedException`; unfinished tasks được yêu cầu hủy. Caller cần xử lý interruption theo lifecycle.

**Câu 7.** Tại sao `Executors.newSingleThreadExecutor()` với task đầu block mãi làm invokeAny có thể kẹt?

**Đáp án:** Task tiếp theo có thể chỉ nằm trong queue, không có worker để chạy và tạo success.

**Câu 8.** `Future.get(timeout)` có tự hủy Future khi timeout không?

**Đáp án:** Không. Khác timed invokeAny, Future.get timeout chỉ ảnh hưởng người đợi, cancellation phải gọi riêng nếu muốn.

**Câu 9.** Vì sao không nên dùng invokeAny cho ba tác vụ ghi cùng một giao dịch?

**Đáp án:** Nhiều tasks có thể đã ghi trước khi loser bị hủy, và cancellation không rollback writes. Cần idempotency và transaction protocol.

**Câu 10.** `CompletableFuture.anyOf` với một future fail sớm, một future success muộn có chắc bỏ qua failure sớm không?

**Đáp án:** Không. anyOf có thể hoàn tất exceptionally ngay khi future lỗi đầu tiên hoàn tất; không tương đương first-success của invokeAny.

## 19. Tài liệu chính thức

- **ExecutorService, hai overload invokeAny — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **Callable — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html
- **Future — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- **AbstractExecutorService — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html
- **ExecutorCompletionService — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html
- **CompletableFuture — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Thread interrupt — Java 17:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

**Điểm cốt lõi:** `invokeAny` lấy **một kết quả từ một Callable hoàn tất bình thường**, bỏ qua failures sớm khi còn cơ hội thành công, và **yêu cầu hủy các tasks chưa hoàn tất** khi trả về hoặc ném exception. Nếu mọi tác vụ thất bại, nhận `ExecutionException`; nếu overload timed hết hạn trước success, nhận `TimeoutException`. Kết quả null vẫn là thành công kỹ thuật. Để ứng dụng đúng, phải thiết kế **business validation, executor capacity, deadline, interruption, idempotency và cleanup**.
