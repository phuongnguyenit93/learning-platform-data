# Future trong Java: get(), isDone(), isCancelled()

## 1. Future đại diện cho điều gì?

Trong Java Concurrency, **java.util.concurrent.Future<V>** là một đối tượng đại diện cho kết quả của một tác vụ bất đồng bộ có thể hoàn thành trong tương lai. Khi gửi Callable<V> hoặc Runnable vào ExecutorService.submit(...), chương trình nhận lại Future để theo dõi trạng thái, đợi kết quả hoặc yêu cầu hủy công việc.

Future không đồng nghĩa với thread. Một Future đại diện cho **một phép tính/tác vụ**; ExecutorService quyết định tác vụ chạy trên worker nào và vào lúc nào. Future cũng không tự động bảo đảm tác vụ chạy thành công, không bị chặn hoặc có thể bị dừng tức thì.

Ba phương thức trọng tâm:

| Phương thức | Ý nghĩa chính | Có thể chờ? |
|---|---|---|
| **V get()** | Đợi tác vụ hoàn tất rồi trả về kết quả, hoặc ném ngoại lệ tương ứng | **Có**, có thể đợi vô thời hạn |
| **boolean isDone()** | Kiểm tra Future đã ở trạng thái hoàn tất hay chưa | **Không** |
| **boolean isCancelled()** | Kiểm tra Future đã được hủy thành công hay chưa | **Không** |

Future còn có **cancel(boolean mayInterruptIfRunning)** để yêu cầu hủy và **get(long timeout, TimeUnit unit)** để giới hạn thời gian đợi. Cần hiểu các phương thức này cùng nhau mới dùng đúng get/isDone/isCancelled.

### Kết quả của submit(...)

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> result = executor.submit(() -> 6 * 7);
    int answer = result.get(); // 42; có thể đợi nếu task chưa hoàn tất.
} finally {
    executor.shutdown();
}
~~~

Đây là **đoạn minh họa** nằm trong một phương thức có khai báo hoặc xử lý InterruptedException/ExecutionException, chưa phải lớp Java độc lập. Trong ví dụ trên, phần tính toán có thể đã xong trước khi gọi get; tính bất đồng bộ không bắt buộc get phải chờ lâu.

**Lưu ý về Callable và Runnable:**

- **submit(Callable<V>):** Future<V>.get() trả về giá trị V nếu thành công.
- **submit(Runnable):** Future<?>.get() trả về **null** khi Runnable hoàn tất bình thường.
- **submit(Runnable, V result):** get() trả về giá trị result đã cung cấp nếu Runnable hoàn tất bình thường.
- Với Executor.execute(Runnable), kiểu trả về là void: không có Future từ lời gọi execute để dùng get/isDone/isCancelled.

## 2. Hiểu đúng vòng đời và trạng thái Future

Một Future có thể đang chờ trong queue, đang chạy hoặc đã hoàn tất. Khi hoàn tất, kết cục có thể là **thành công**, **thất bại vì ngoại lệ** hoặc **được hủy thành công**.

~~~text
                         submit task
                              |
                     Chưa hoàn tất
                  (queued hoặc running)
                       /      |      \
                      /       |       \
               thành công   thất bại   hủy thành công
                    |          |              |
                 done=true   done=true     done=true
                 cancel=false cancel=false cancel=true
~~~

Bảng hành vi của Future sau khi quan sát trạng thái:

| Tình trạng | isDone() | isCancelled() | get() |
|---|---|---|---|
| Chưa hoàn tất (đang chờ/chạy) | false | false | Có thể chờ đến khi hoàn tất |
| Hoàn tất **thành công** | true | false | Trả về giá trị kết quả |
| Hoàn tất **do ngoại lệ** | true | false | Ném ExecutionException chứa nguyên nhân |
| Hủy **thành công** | true | true | Ném CancellationException |

**Kết luận rất quan trọng:** **isDone() == true không có nghĩa task thành công.** Nó chỉ nói phép tính đã hoàn tất theo hợp đồng Future, bao gồm cả trường hợp lỗi hoặc hủy. isCancelled() == false cũng **không khẳng định thành công**: task có thể chưa xong hoặc đã thất bại.

Những trạng thái trên là ảnh chụp tại **thời điểm kiểm tra**. Task có thể kết thúc ngay sau một lời gọi isDone() trả về false. Đừng ghép nhiều phép kiểm tra thành giả định về một trạng thái bất biến khi các thread khác vẫn hoạt động.

## 3. get(): chờ kết quả và cách xử lý ngoại lệ

Với **Future<V>.get()**, thread **gọi get** có thể bị chặn cho tới khi phép tính hoàn tất; worker thực thi tác vụ là thread khác do executor quản lý. Nếu công việc hoàn tất trước, get lấy kết quả ngay. Một số tình huống:

1. **Hoàn tất bình thường:** get() trả về V; với Runnable không có giá trị thì trả về null.
2. **Task ném lỗi:** get() ném **ExecutionException**; gọi getCause() để truy cập lỗi ban đầu của tác vụ.
3. **Future bị hủy thành công:** get() ném **CancellationException** (ngoại lệ không kiểm tra).
4. **Thread đang chờ bị interrupt:** get() ném **InterruptedException**; việc thread gọi get bị ngắt không mặc nhiên đồng nghĩa Future bị hủy.
5. **Task không kết thúc:** get() không có thời hạn chờ mặc định; nếu không có lối thoát, caller có thể bị chặn vô hạn.

**get(timeout, unit)** chờ tối đa thời lượng yêu cầu và có thể ném **TimeoutException** nếu chưa có kết quả. Timeout **không tự động hủy Future**: tác vụ có thể vẫn chạy và get() ở một lần gọi sau vẫn trả về kết quả thành công.

Hai overload có khai báo checked exceptions khác nhau:

~~~java
V value = future.get(); // InterruptedException, ExecutionException
V value = future.get(2, TimeUnit.SECONDS);
// InterruptedException, ExecutionException, TimeoutException
~~~

Các dòng trên chỉ minh họa chữ ký trong ngữ cảnh Future<V> và cần xử lý/khai báo ngoại lệ. CancellationException vẫn có thể xuất hiện ở cả hai overload.

### Không che giấu lỗi gốc

Nếu task ném IllegalStateException("bad input"), lời gọi get() ở caller ném ExecutionException. Trong catch (ExecutionException ex), **ex.getCause()** mới là nguyên nhân task thất bại. Đừng bắt Exception rồi coi mọi trường hợp là timeout hoặc trả về kết quả mặc định, vì sẽ bỏ qua lỗi xử lý và dữ liệu hỏng.

### Interruption khác cancellation

Khi caller bị interrupt trong lúc đợi get(), get có thể ném InterruptedException. Caller nên **truyền tiếp ngoại lệ** hoặc, nếu xử lý tại chỗ và không truyền tiếp, thường khôi phục cờ interrupt bằng Thread.currentThread().interrupt() để tầng trên biết có yêu cầu ngắt. Việc phục hồi cờ interrupt không tương đương với future.cancel(true), và không đảm bảo task phía worker ngừng.

## 4. Ví dụ Java 17: kiểm tra trước và sau khi hoàn tất

Sử dụng CountDownLatch để điều khiển đúng thời điểm quan sát. Task báo đã bắt đầu rồi chờ tín hiệu; main kiểm tra isDone()/isCancelled() khi task **chắc chắn chưa kết thúc**, sau đó mở khóa và đọc kết quả. Ví dụ này tránh phụ thuộc vào tốc độ CPU để minh họa trạng thái.

Lưu file **FutureLifecycleDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "OK";
            });

            started.await();
            System.out.println("before: done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());

            release.countDown();
            System.out.println("get=" + future.get());
            System.out.println("after: done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac FutureLifecycleDemo.java
java FutureLifecycleDemo
~~~

Stdout xác định:

~~~text
before: done=false, cancelled=false
get=OK
after: done=true, cancelled=false
~~~

Ở điểm in dòng đầu, worker đang đợi latch release nên chưa thể hoàn tất. Sau release.countDown(), get() đồng bộ với kết quả của task; vì get đã trả về bình thường nên isDone true và isCancelled false ở dòng cuối.

**Quan hệ bộ nhớ:** theo hợp đồng Future, các hành động trong phép tính bất đồng bộ **happen-before** các hành động phía thread khác diễn ra sau khi Future.get() tương ứng trả về. Vì vậy get() không chỉ lấy giá trị mà còn cung cấp một mốc đồng bộ quan trọng đối với những ghi dữ liệu do tác vụ thực hiện. Điều này không biến mọi truy cập dữ liệu chia sẻ trước khi get thành thread-safe; khi đọc/ghi đồng thời trước mốc đồng bộ vẫn cần quy tắc đồng bộ phù hợp.

## 5. isDone(): biết đã xong, không biết xong tốt hay xấu

**isDone()** là kiểm tra không blocking. Khi false, tác vụ có thể chưa bắt đầu hoặc vẫn đang chạy. Khi true, phép tính đã hoàn tất bình thường, thất bại hoặc bị hủy.

Cách dùng đúng:

- Theo dõi trạng thái ở giao diện/metric khi cần trạng thái snapshot.
- Chỉ gọi get() khi muốn lấy kết quả hoặc lỗi; nếu isDone() đã true, get() không cần đợi phép tính hoàn tất (nhưng vẫn có thể ném ExecutionException/CancellationException).
- Không dùng vòng lặp while (!future.isDone()) {} để **busy-spin**: nó tiêu tốn CPU không cần thiết. Nếu chỉ muốn chờ, hãy gọi get() hoặc get(timeout,...); nếu muốn phản ứng theo từng task hoàn thành, cân nhắc CompletionService hoặc mô hình completion phù hợp.

**isDone true nhưng get ném lỗi** là hành vi bình thường khi task thất bại. Do đó mô hình if (future.isDone()) { return future.get(); } không phải cách bỏ qua try/catch. Nó chỉ có thể tránh chờ khi phép tính còn pending; lỗi vẫn phải được xử lý.

**Tác vụ chạy lâu không có nghĩa là Future sai.** isDone vẫn false khi task đang xử lý hoặc chờ dependency. Cần đo task duration, queue wait, lock contention và I/O latency trước khi kết luận task treo.

## 6. get(timeout, unit) và lỗi tác vụ: ví dụ kiểm chứng

Ví dụ này tạo một tác vụ chờ latch để kiểm chứng chắc chắn timeout, rồi giải phóng latch để lấy kết quả. Nó cũng submit task cố ý ném lỗi để quan sát ExecutionException. Không dùng sleep để tạo timing mong manh.

Lưu file **FutureTimeoutFailureDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> slow = executor.submit(() -> {
                started.countDown();
                release.await();
                return 7;
            });

            started.await();
            try {
                slow.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException timeout) {
                System.out.println("timeout, still pending=" + !slow.isDone());
            }

            // Timeout ở caller không hủy task.
            release.countDown();
            System.out.println("slow result=" + slow.get());

            Future<Integer> failed = executor.submit(() -> {
                throw new IllegalStateException("demo failure");
            });

            try {
                failed.get();
            } catch (ExecutionException failure) {
                System.out.println("failure cause="
                        + failure.getCause().getClass().getSimpleName());
            }
            System.out.println("failed isDone=" + failed.isDone());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac FutureTimeoutFailureDemo.java
java FutureTimeoutFailureDemo
~~~

Stdout:

~~~text
timeout, still pending=true
slow result=7
failure cause=IllegalStateException
failed isDone=true
~~~

Đầu tiên, slow được bảo đảm còn đợi latch, nên get với hạn chờ 20 ms ném TimeoutException và isDone vẫn false. Sau khi mở latch, lần get tiếp theo trả về 7. Tác vụ failed ném IllegalStateException; get bọc lỗi trong ExecutionException, nhưng isDone true vì phép tính đã kết thúc.

**Thực tế khi timeout:** tùy nghiệp vụ, caller có thể retry, hủy task, trả về lỗi hoặc tiếp tục đợi; phải chọn rõ. Nếu timeout của một request không còn cần kết quả, cân nhắc future.cancel(true) và cơ chế deadline/cancellation ở cả I/O downstream. Không tự retry nhiều lần trong khi task cũ vẫn đang chạy, vì có thể nhân tải lên hệ thống.

## 7. isCancelled(): kiểm tra kết quả hủy và hiểu cancel(...)

**isCancelled()** chỉ true nếu Future **đã được hủy thành công trước khi hoàn tất bình thường**. Việc người dùng “muốn hủy” không đồng nghĩa isCancelled true; nếu task đã xong trước khi cancel, cancel thường trả về false và isCancelled vẫn false.

Phương thức **cancel(boolean mayInterruptIfRunning)** trả về boolean cho biết yêu cầu hủy thành công theo hợp đồng Future:

- **cancel(false):** cố gắng hủy mà **không gửi interrupt đến thread đang chạy**. Task đang chạy có thể vẫn tiếp tục thực thi phần thân; tuy nhiên Future đã chuyển sang trạng thái canceled, get() sẽ ném CancellationException nếu cancel thành công.
- **cancel(true):** nếu task đang chạy, implementation có thể interrupt worker đang thực thi để yêu cầu task dừng. Interrupt chỉ là tín hiệu hợp tác; code không kiểm tra interrupt hoặc I/O không interruptible có thể còn chạy tiếp.
- **cancel(...) trả false:** việc hủy không thành công, chẳng hạn phép tính đã hoàn tất hoặc Future không thể hủy. Không được tự suy ra kết quả là thành công; kiểm tra và xử lý get nếu cần.
- **isCancelled() == true:** get() ném CancellationException, đồng thời isDone() true. Tuy nhiên điều này **không chứng minh side effect bên ngoài đã dừng, đã được rollback hoặc chưa từng xảy ra**.

**Mối quan hệ quan trọng:** cancellation là trạng thái của Future; termination thực tế của task là một vấn đề khác. Đặc biệt với cancel(false) trên task đang chạy hoặc cancel(true) khi code không đáp ứng interrupt, Future có thể báo canceled trong khi một phần công việc phía sau còn tiếp tục.

### Ví dụ Java 17: hủy khi tác vụ đang đợi

Lưu file **FutureCancellationDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);

        try {
            Future<Integer> future = executor.submit(() -> {
                started.countDown();
                blocker.await();
                return 123;
            });

            started.await();
            boolean cancelled = future.cancel(true);

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get -> CancellationException");
            }
        } finally {
            blocker.countDown();
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Stdout:

~~~text
cancel accepted=true
done=true, cancelled=true
get -> CancellationException
~~~

started.await() bảo đảm worker đã vào thân tác vụ, còn blocker.await() chưa được giải phóng. cancel(true) chuyển trạng thái Future sang canceled và gửi yêu cầu interrupt đến worker; CountDownLatch.await() hỗ trợ interruption. Việc finally mở blocker là bước phòng vệ để không giữ worker kẹt nếu một nhánh khác xảy ra.

Nếu task thực hiện các thao tác ghi database, gửi HTTP hoặc ghi file, **hủy Future không tự động hoàn tác tác động đã xảy ra**. Thiết kế công việc có side effect nên cân nhắc idempotency, timeout của I/O, giao dịch và trạng thái hoàn tất nghiệp vụ.

## 8. Dùng get/isDone/isCancelled cùng nhau: mẫu xử lý hợp lý

### Khi caller thực sự cần kết quả

Gọi get(timeout,...) với một deadline phù hợp thường dễ đọc và tránh vòng lặp polling. Bắt riêng:

- **InterruptedException:** caller đang chờ bị ngắt; truyền tiếp hoặc khôi phục cờ interrupt nếu xử lý tại đây.
- **ExecutionException:** task thất bại; phân loại cause và xử lý lỗi nghiệp vụ/kỹ thuật.
- **TimeoutException:** quá hạn chờ; đánh giá có nên cancel hoặc bỏ qua kết quả.
- **CancellationException:** Future đã bị hủy; xử lý như nhánh hủy, không coi là kết quả hợp lệ.

Trong code xử lý InterruptedException tại chỗ:

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Caller interrupted", interrupted);
}
~~~

Đây là **đoạn minh họa trong một phương thức có Future<V> và kiểu trả về V**; còn phải khai báo/xử lý ExecutionException, TimeoutException, CancellationException ở mức phù hợp. Nếu phương thức có thể khai báo throws InterruptedException, truyền tiếp checked exception thường rõ ràng hơn.

### Khi chỉ muốn hiển thị trạng thái

~~~text
if (future.isCancelled()) {
    // Canceled.
} else if (future.isDone()) {
    // Completed, nhưng chưa biết success/failure.
    // Muốn biết kết quả, vẫn phải gọi get() và xử lý ngoại lệ.
} else {
    // Pending: queued hoặc running.
}
~~~

Đây là **pseudocode** minh họa các trạng thái, không phải Java class độc lập. Thứ tự kiểm tra không tạo snapshot nguyên tử: nếu một thread khác hoàn tất/hủy ngay sau lần kiểm tra, trạng thái quan sát tiếp theo có thể thay đổi. Đối với UI hoặc metrics, ghi rõ đây là snapshot.

### Khi nhận nhiều Future

Nếu có danh sách Future và gọi get() lần lượt theo thứ tự submit, một task đầu chậm có thể giữ caller dù task sau đã hoàn thành. Đừng polling liên tục cả danh sách trong một vòng lặp CPU bận. Các lựa chọn trong Java chuẩn gồm:

- **ExecutorCompletionService:** lấy Future theo thứ tự task **hoàn thành**, thay vì thứ tự submit; vẫn phải gọi get và xử lý lỗi.
- **invokeAll(collection):** đợi tập task hoàn thành theo hợp đồng; phiên bản có timeout có thể hủy các task chưa kết thúc khi hết hạn.
- **CompletableFuture:** khi cần composition, callback và chuỗi xử lý kết quả; nó triển khai Future nhưng có thêm API riêng. Với CompletableFuture, join() dùng CompletionException (unchecked) thay cho mô hình checked exceptions của get().

Các lựa chọn trên phục vụ bài toán nhiều tác vụ; để hiểu Future.get/isDone/isCancelled, hãy nắm đúng ngữ nghĩa từng Future trước.

## 9. Future trong ScheduledExecutorService

Future cũng xuất hiện trong lịch chạy Java chuẩn:

- **schedule(Callable/V hoặc Runnable, delay, unit)** trả ScheduledFuture. Trước khi task một lần chạy xong, isDone thường false; sau khi chạy thành công, get trả về kết quả (Runnable thường là null).
- **scheduleAtFixedRate** và **scheduleWithFixedDelay** trả ScheduledFuture đại diện cho chuỗi chạy **định kỳ**. Với chuỗi định kỳ vẫn đang tiếp tục bình thường, Future không được coi hoàn tất sau mỗi lượt nên isDone thường vẫn false.
- **get() trên Future định kỳ đang chạy bình thường có thể chờ mãi**, vì chuỗi chưa chấm dứt. Sau khi hủy thành công, get ném CancellationException. Nếu một lần chạy định kỳ ném ngoại lệ khiến chuỗi bị chặn chạy tiếp, Future có thể hoàn tất theo nhánh lỗi và get ném ExecutionException.
- **cancel(true)** trên ScheduledFuture không đảm bảo callback đang chạy dừng ngay; quy tắc interruption và side effect vẫn áp dụng.

Do đó không nên gọi get() vô thời hạn trên task định kỳ nếu thiết kế mong đợi “lấy kết quả mỗi lượt chạy”. Nếu muốn kết quả từng lượt, cần một cơ chế riêng để xuất sự kiện/kết quả, thay vì trông chờ Future của cả lịch định kỳ.

## 10. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Đọc isDone() == true là “thành công” | Bỏ qua nhánh failure/cancel | Gọi get() và xử lý ExecutionException/CancellationException |
| Đọc isCancelled() == false là “đã xong tốt” | Nhầm với queued, running hoặc failed | Kết hợp trạng thái và kết quả get |
| Gọi get() tùy ý trên main thread/UI/thread xử lý request | Có thể block vô thời hạn | Đặt deadline, xem xét kiến trúc async |
| Nghĩ get(timeout) tự ngừng task | Task cũ có thể tiếp tục, gây trùng xử lý khi retry | Quyết định cancel riêng; bảo đảm idempotency khi cần |
| Nghĩ cancel(true) luôn “kill” worker | Side effect hoặc code không interruptible có thể tiếp diễn | Hỗ trợ interruption, timeout I/O, rollback/compensation phù hợp |
| Busy-spin với while (!isDone()) | Đốt CPU và không xử lý lỗi | get/get(timeout), CompletionService hoặc API hoàn tất |
| Nuốt InterruptedException | Mất tín hiệu shutdown/cancel của caller | Truyền tiếp hoặc restore interrupt flag |
| Bỏ qua ExecutionException.getCause() | Ẩn lỗi thực sự xảy ra trong task | Phân loại/ghi log nguyên nhân gốc |
| Chờ get() trên scheduled task định kỳ | Có thể chờ đến lúc hủy/lỗi, không phải mỗi kỳ | Thiết kế cơ chế kết quả riêng cho mỗi lượt |
| Không shutdown ExecutorService | Worker có thể giữ JVM sống hoặc rò rỉ tài nguyên | Quản lý lifecycle, shutdown và chờ kết thúc theo chính sách |

## 11. Checklist ghi nhớ và tự kiểm tra

Sau bài học, bạn nên giải thích được:

1. Vì sao get() có thể chặn caller nhưng isDone()/isCancelled() thì không?
2. Ba kết cục **thành công, lỗi, hủy** ảnh hưởng bảng trạng thái và kết quả get() ra sao?
3. Vì sao isDone() true chưa nói task thành công và isCancelled() false chưa nói task đã hoàn tất?
4. Khi get(timeout,...) ném TimeoutException, tác vụ phía worker có tiếp tục hay không?
5. Khác biệt giữa interrupt thread **đang đợi get** và cancel(true) trên Future là gì?
6. Vì sao cancel(false) hoặc cancel(true) không mặc nhiên bảo đảm tác động bên ngoài dừng hoặc rollback?
7. Vì sao Future của tác vụ lịch **định kỳ** không hoàn tất sau mỗi lần chạy thành công?

**Ghi nhớ cốt lõi:** **get()** là cổng lấy kết quả và lỗi, có thể chờ; **isDone()** chỉ xác nhận phép tính đã kết thúc theo trạng thái Future; **isCancelled()** cho biết phép tính đã được hủy thành công. Cả ba đều phải được hiểu cùng cơ chế cancel, interruption, timeout và vòng đời executor để quản lý công việc bất đồng bộ an toàn.
